"""
Phase 2 — Metadata Forensic Analyzer

Takes raw ExifTool JSON and produces:
  1. Normalized metadata (GPS, camera, timestamps, software)
  2. Consistency checks (timestamp mismatches, missing fields)
  3. Forensic indicators (flags, not verdicts)

Design principle: indicators are evidence, not proof.
Editing software is NOT treated as automatic tampering.
"""

from datetime import datetime
from typing import Optional


# ── GPS helpers ──────────────────────────────────────────────────

def _parse_gps_coordinate(raw) -> Optional[float]:
    """Convert ExifTool GPS value to decimal degrees.

    ExifTool may return:
      - A float or int already in decimal (e.g. 28.6139)
      - A string like '28 deg 36\' 50.04" N'  or  "28 36 50.04"
      - A DMS string like "77 deg 12' 32.40"
    Returns None on failure.
    """
    if raw is None:
        return None

    # Already numeric
    if isinstance(raw, (int, float)):
        return float(raw)

    raw_str = str(raw).strip()
    if not raw_str:
        return None

    # Try direct float parse (ExifTool sometimes gives plain decimals)
    try:
        return float(raw_str)
    except ValueError:
        pass

    # Parse DMS: strip letters/symbols, split on whitespace
    cleaned = raw_str.replace("deg", " ").replace("'", " ").replace('"', " ")
    cleaned = cleaned.replace("°", " ").replace(",", " ")

    parts = cleaned.split()
    numeric = []
    direction = None
    for p in parts:
        try:
            numeric.append(float(p))
        except ValueError:
            if p.upper() in ("N", "S", "E", "W"):
                direction = p.upper()

    if not numeric:
        return None

    degrees = numeric[0]
    minutes = numeric[1] if len(numeric) > 1 else 0.0
    seconds = numeric[2] if len(numeric) > 2 else 0.0

    decimal = degrees + minutes / 60.0 + seconds / 3600.0

    if direction in ("S", "W"):
        decimal = -decimal

    return round(decimal, 6)


def _validate_coordinates(lat: Optional[float], lon: Optional[float]) -> bool:
    """Check whether lat/lon fall within valid geographic bounds."""
    if lat is None or lon is None:
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def _get_first(raw: dict, *keys):
    """Return the first non-None value for the given keys (zero-safe)."""
    for k in keys:
        val = raw.get(k)
        if val is not None:
            return val
    return None


def _extract_gps(raw: dict) -> dict:
    """Pull GPS fields from raw ExifTool output."""
    lat_raw = _get_first(raw, "GPSLatitude", "GPS:GPSLatitude")
    lon_raw = _get_first(raw, "GPSLongitude", "GPS:GPSLongitude")

    # ExifTool ref tags (N/S, E/W) sometimes arrive separately
    lat_ref = _get_first(raw, "GPSLatitudeRef", "GPS:GPSLatitudeRef")
    lon_ref = _get_first(raw, "GPSLongitudeRef", "GPS:GPSLongitudeRef")

    lat = _parse_gps_coordinate(lat_raw)
    lon = _parse_gps_coordinate(lon_raw)

    # Apply ref sign if coordinate was positive and ref says S/W
    if lat is not None and lat > 0 and lat_ref and lat_ref.upper() == "S":
        lat = -lat
    if lon is not None and lon > 0 and lon_ref and lon_ref.upper() == "W":
        lon = -lon

    gps_present = lat is not None and lon is not None
    coords_valid = _validate_coordinates(lat, lon) if gps_present else False

    return {
        "gps_present": gps_present,
        "latitude": lat,
        "longitude": lon,
        "coordinates_valid": coords_valid,
    }


# ── Timestamp helpers ────────────────────────────────────────────

# Common ExifTool datetime formats
_DT_FORMATS = [
    "%Y:%m:%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y:%m:%d %H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
]


def _parse_datetime(raw) -> Optional[datetime]:
    """Try multiple formats ExifTool might return."""
    if raw is None:
        return None
    raw_str = str(raw).strip()
    if not raw_str or raw_str in ("0000:00:00 00:00:00",):
        return None
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(raw_str, fmt)
        except ValueError:
            continue
    return None


def _extract_timestamps(raw: dict) -> dict:
    """Pull and normalize the three main EXIF timestamps."""
    fields = {
        "datetime_original": _get_first(raw, "DateTimeOriginal", "EXIF:DateTimeOriginal"),
        "create_date": _get_first(raw, "CreateDate", "EXIF:CreateDate"),
        "modify_date": _get_first(raw, "ModifyDate", "File:FileModifyDate", "FileModifyDate"),
    }
    return {k: (str(v) if v else None) for k, v in fields.items()}


# ── Camera / software helpers ───────────────────────────────────

def _extract_camera(raw: dict) -> dict:
    return {
        "make": _get_first(raw, "Make", "EXIF:Make"),
        "model": _get_first(raw, "Model", "EXIF:Model"),
    }


def _extract_software(raw: dict) -> Optional[str]:
    return _get_first(raw, "Software", "EXIF:Software", "XMP:CreatorTool")


# ── Forensic indicator engine ───────────────────────────────────

def _check_timestamp_consistency(timestamps: dict) -> list[str]:
    """Flag inconsistencies across the three timestamps."""
    indicators = []
    parsed = {}
    for key, raw_val in timestamps.items():
        dt = _parse_datetime(raw_val)
        if dt is not None:
            parsed[key] = dt

    dto = parsed.get("datetime_original")
    cd = parsed.get("create_date")
    md = parsed.get("modify_date")

    # ModifyDate before DateTimeOriginal is unusual
    if dto and md:
        md_naive = md.replace(tzinfo=None)
        dto_naive = dto.replace(tzinfo=None)
        if md_naive < dto_naive:
            indicators.append("modify_date_before_original")

    # Large gap between DateTimeOriginal and CreateDate (>1 second)
    if dto and cd:
        cd_naive = cd.replace(tzinfo=None)
        dto_naive = dto.replace(tzinfo=None)
        diff = abs((cd_naive - dto_naive).total_seconds())
        if diff > 1:
            indicators.append("original_create_date_mismatch")

    return indicators


def _check_missing_fields(gps: dict, camera: dict, timestamps: dict) -> list[str]:
    """Flag important metadata that is absent."""
    indicators = []

    if timestamps.get("datetime_original") is None:
        indicators.append("missing_datetime_original")

    if camera.get("make") is None and camera.get("model") is None:
        indicators.append("missing_camera_info")

    # Missing GPS is noted but NOT treated as suspicious on its own
    # (many legitimate images lack GPS)

    return indicators


def _check_suspicious_metadata(raw: dict, software: Optional[str], gps: dict) -> list[str]:
    """Flag metadata patterns worth noting. These are indicators, not proof."""
    indicators = []

    # Software field present — note it, do NOT call it tampering
    if software:
        indicators.append(f"software_detected:{software}")

    # GPS altitude is negative (below sea level) — unusual but possible
    alt = raw.get("GPSAltitude") or raw.get("GPS:GPSAltitude")
    if alt is not None:
        try:
            alt_val = float(str(alt).split()[0])
            if alt_val < -100:
                indicators.append("unusual_gps_altitude")
        except (ValueError, IndexError):
            pass

    # GPS coordinates at exactly 0,0 (Null Island) — almost always a default/error
    if gps.get("gps_present"):
        lat = gps.get("latitude")
        lon = gps.get("longitude")
        if lat is not None and lon is not None:
            if abs(lat) < 0.001 and abs(lon) < 0.001:
                indicators.append("gps_null_island")

    return indicators


# ── Public API ───────────────────────────────────────────────────

def analyze_metadata(raw_exif: dict) -> dict:
    """Main entry point.

    Parameters
    ----------
    raw_exif : dict
        Raw ExifTool JSON (the dict returned by exif_service.extract_exif).

    Returns
    -------
    dict
        Structured forensic metadata ready for downstream consumption.
    """
    if raw_exif is None or "error" in raw_exif:
        return {
            "metadata": {
                "gps_present": False,
                "latitude": None,
                "longitude": None,
                "coordinates_valid": False,
                "camera": None,
                "model": None,
                "datetime_original": None,
                "create_date": None,
                "modify_date": None,
                "software": None,
            },
            "forensics": {
                "indicators": ["metadata_extraction_failed"],
                "indicator_count": 1,
            },
        }

    gps = _extract_gps(raw_exif)
    camera = _extract_camera(raw_exif)
    timestamps = _extract_timestamps(raw_exif)
    software = _extract_software(raw_exif)

    # Collect forensic indicators
    indicators = []
    indicators.extend(_check_timestamp_consistency(timestamps))
    indicators.extend(_check_missing_fields(gps, camera, timestamps))
    indicators.extend(_check_suspicious_metadata(raw_exif, software, gps))

    return {
        "metadata": {
            "gps_present": gps["gps_present"],
            "latitude": gps["latitude"],
            "longitude": gps["longitude"],
            "coordinates_valid": gps["coordinates_valid"],
            "camera": camera["make"],
            "model": camera["model"],
            "datetime_original": timestamps["datetime_original"],
            "create_date": timestamps["create_date"],
            "modify_date": timestamps["modify_date"],
            "software": software,
        },
        "forensics": {
            "indicators": indicators,
            "indicator_count": len(indicators),
        },
    }
