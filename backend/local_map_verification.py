"""Offline map-context verification for GeoTrace location candidates.

The runtime reads a locally built GeoNames place index. It makes no geocoding
API requests and sends neither images nor candidate coordinates to a service.
"""
from __future__ import annotations

import copy
import os
import re
from pathlib import Path

import numpy as np


MAP_SCHEMA_VERSION = 1
DEFAULT_MAP_INDEX_PATH = Path(__file__).resolve().parent / "models" / "geotrace_places_v0.npz"
EARTH_RADIUS_KM = 6371.0088
TOKEN_PATTERN = re.compile(r"[^\W\d_]{3,}", re.UNICODE)
STOP_WORDS = {
    "city", "district", "state", "province", "county", "region", "road",
    "street", "the", "and", "near", "place", "united",
}


class LocalMapError(RuntimeError):
    """The local place index could not be built, loaded, or queried."""


class LocalMapNotBuilt(LocalMapError):
    """The local place index has not been generated yet."""


def configured_map_path() -> Path:
    configured = os.getenv("GEOTRACE_MAP_INDEX_PATH", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_MAP_INDEX_PATH


def is_built() -> bool:
    return configured_map_path().is_file()


def _country_names(country_info_path: str | Path | None) -> dict[str, str]:
    if not country_info_path:
        return {}
    names = {}
    with Path(country_info_path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) > 4:
                names[parts[0]] = parts[4]
    return names


def build_map_index(
    geonames_path: str | Path,
    output_path: str | Path,
    country_info_path: str | Path | None = None,
) -> dict:
    """Build a compact offline place index from a GeoNames dump."""
    source = Path(geonames_path)
    if not source.is_file():
        raise LocalMapError("GeoNames source file was not found.")
    country_names = _country_names(country_info_path)
    geoname_ids = []
    names = []
    country_codes = []
    countries = []
    latitudes = []
    longitudes = []
    populations = []
    with source.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 19:
                raise LocalMapError(f"Invalid GeoNames row on line {line_number}.")
            try:
                latitude = float(parts[4])
                longitude = float(parts[5])
                population = int(parts[14] or 0)
            except ValueError as error:
                raise LocalMapError(f"Invalid GeoNames values on line {line_number}.") from error
            geoname_ids.append(parts[0])
            names.append(parts[1])
            latitudes.append(latitude)
            longitudes.append(longitude)
            country_codes.append(parts[8])
            countries.append(country_names.get(parts[8], parts[8]))
            populations.append(population)
    if not names:
        raise LocalMapError("The GeoNames source contains no places.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        schema_version=np.asarray([MAP_SCHEMA_VERSION], dtype=np.int16),
        geoname_ids=np.asarray(geoname_ids),
        names=np.asarray(names),
        country_codes=np.asarray(country_codes),
        countries=np.asarray(countries),
        latitudes=np.asarray(latitudes, dtype=np.float64),
        longitudes=np.asarray(longitudes, dtype=np.float64),
        populations=np.asarray(populations, dtype=np.int64),
    )
    return {"map_index": str(output.resolve()), "places": len(names)}


def _load_map_index() -> dict:
    path = configured_map_path()
    if not path.is_file():
        raise LocalMapNotBuilt(
            "GeoTrace's local place index must be built before automated map verification can run."
        )
    try:
        with np.load(path, allow_pickle=False) as archive:
            if int(archive["schema_version"][0]) != MAP_SCHEMA_VERSION:
                raise LocalMapError("The local place index is incompatible; rebuild it.")
            return {key: archive[key].copy() for key in archive.files}
    except (OSError, ValueError, KeyError) as error:
        raise LocalMapError("The local place index is invalid; rebuild it.") from error


def nearest_place(latitude: float, longitude: float) -> dict:
    """Find the nearest indexed populated place using haversine distance."""
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise LocalMapError("Candidate coordinates are out of range.")
    index = _load_map_index()
    latitudes = np.radians(index["latitudes"])
    longitudes = np.radians(index["longitudes"])
    query_latitude = np.radians(latitude)
    query_longitude = np.radians(longitude)
    delta_latitude = latitudes - query_latitude
    delta_longitude = longitudes - query_longitude
    haversine = (
        np.sin(delta_latitude / 2) ** 2
        + np.cos(query_latitude) * np.cos(latitudes) * np.sin(delta_longitude / 2) ** 2
    )
    distances = EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(np.clip(haversine, 0, 1)))
    nearest = int(np.argmin(distances))
    return {
        "geoname_id": str(index["geoname_ids"][nearest]),
        "name": str(index["names"][nearest]),
        "country_code": str(index["country_codes"][nearest]),
        "country": str(index["countries"][nearest]),
        "latitude": float(index["latitudes"][nearest]),
        "longitude": float(index["longitudes"][nearest]),
        "population": int(index["populations"][nearest]),
        "distance_km": round(float(distances[nearest]), 2),
    }


def _tokens(value: object) -> set[str]:
    if not value:
        return set()
    return {token for token in TOKEN_PATTERN.findall(str(value).casefold()) if token not in STOP_WORDS}


def verify_map_context(osint: dict, ocr_text: str | None = None) -> dict:
    """Enrich ranked candidates with offline, independently sourced place context."""
    enriched = copy.deepcopy(osint)
    records = []
    any_ocr_match = False
    any_label_match = False
    for candidate in enriched.get("candidates", []):
        latitude = candidate.get("latitude")
        longitude = candidate.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            continue
        place = nearest_place(float(latitude), float(longitude))
        map_tokens = _tokens(place["name"]) | _tokens(place["country"]) | _tokens(place["country_code"])
        label_matches = sorted(_tokens(candidate.get("label")) & map_tokens)
        ocr_matches = sorted(_tokens(ocr_text) & map_tokens)
        source_group = f"geonames:{place['geoname_id']}"
        context_summary = (
            f"Nearest indexed place is {place['name']}, {place['country']} "
            f"({place['distance_km']} km from the candidate coordinate)."
        )
        candidate.setdefault("supports", []).append(
            {
                "evidence_id": f"map_context_{candidate['id']}",
                "summary": context_summary,
                "source_group": source_group,
                "evidence_role": "map_context",
            }
        )
        if ocr_matches:
            candidate["verification_status"] = "partially_corroborated_by_map_and_ocr"
            candidate["supports"].append(
                {
                    "evidence_id": f"map_ocr_match_{candidate['id']}",
                    "summary": f"Visible text matches map context: {', '.join(ocr_matches)}.",
                    "source_group": source_group,
                    "evidence_role": "independent_corroboration",
                }
            )
            any_ocr_match = True
        elif label_matches:
            candidate["verification_status"] = "map_context_consistent"
            any_label_match = True
        else:
            candidate["verification_status"] = "map_context_collected"

        records.append(
            {
                "candidate_id": candidate["id"],
                "status": candidate["verification_status"],
                "place": place,
                "label_matches": label_matches,
                "ocr_matches": ocr_matches,
                "map_url": f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map=14/{latitude}/{longitude}",
            }
        )
        enriched.setdefault("actions", []).append(
            {
                "id": f"map_review_{candidate['id']}",
                "label": f"Review map context for candidate #{candidate.get('rank', '?')}",
                "provider": "OpenStreetMap",
                "url": records[-1]["map_url"],
                "sends_image": False,
            }
        )

    enriched["map_verification"] = {
        "status": "complete" if records else "no_coordinate_candidates",
        "mode": "offline_place_index",
        "records": records,
        "attribution": "Place data © GeoNames, CC BY 4.0. Map review links © OpenStreetMap contributors.",
    }
    if records:
        privacy_note = " Candidate coordinates were checked against GeoTrace's local place index; no coordinates or images were sent to a geocoding service."
        enriched["privacy"]["note"] = f"{enriched['privacy']['note']}{privacy_note}"
        source_groups = {
            candidate.get("source_group")
            for candidate in enriched.get("candidates", [])
            if candidate.get("source_group")
        }
        source_groups.update(
            support.get("source_group")
            for candidate in enriched.get("candidates", [])
            for support in candidate.get("supports", [])
            if support.get("source_group")
        )
        enriched["uncertainty"]["independent_source_groups"] = len(source_groups)
        if any_ocr_match:
            enriched["uncertainty"]["outcome"] = "candidate_partially_corroborated"
        elif any_label_match:
            enriched["uncertainty"]["outcome"] = "candidate_map_context_consistent"
    return enriched
