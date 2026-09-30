"""Combine geolocation evidence without inventing calibrated confidence."""

from __future__ import annotations

import math
import re
from typing import Any


EARTH_RADIUS_KM = 6371.0088
DEFAULT_CLUSTER_RADIUS_KM = 50.0


def _haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    value = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(value))


def _centroid(evidence: dict[str, dict]) -> tuple[float, float]:
    values = list(evidence.values())
    return (
        sum(float(item["latitude"]) for item in values) / len(values),
        sum(float(item["longitude"]) for item in values) / len(values),
    )


def _decimal_coordinate(value: Any, reference: Any = None) -> float | None:
    if isinstance(value, (int, float)):
        coordinate = float(value)
    elif isinstance(value, str):
        try:
            coordinate = float(value.strip())
        except ValueError:
            parts = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", value)]
            if not parts:
                return None
            coordinate = parts[0]
            if len(parts) > 1:
                coordinate += parts[1] / 60
            if len(parts) > 2:
                coordinate += parts[2] / 3600
            if any(direction in value.upper() for direction in ("S", "W")):
                coordinate *= -1
    else:
        return None

    if str(reference or "").upper() in {"S", "W"}:
        coordinate = -abs(coordinate)
    return coordinate


def exif_location_result(metadata: dict) -> dict:
    """Normalize common ExifTool GPS fields as a high-precision provider."""

    latitude = _decimal_coordinate(metadata.get("GPSLatitude"), metadata.get("GPSLatitudeRef"))
    longitude = _decimal_coordinate(
        metadata.get("GPSLongitude"), metadata.get("GPSLongitudeRef")
    )
    if latitude is None or longitude is None:
        return {
            "status": "unavailable",
            "provider": "EXIF GPS",
            "reason": "No usable GPS coordinates were found in image metadata",
            "candidates": [],
        }
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return {
            "status": "error",
            "provider": "EXIF GPS",
            "reason": "Metadata GPS coordinates are outside valid ranges",
            "candidates": [],
        }
    return {
        "status": "success",
        "provider": "EXIF GPS",
        "candidates": [
            {
                "rank": 1,
                "latitude": round(latitude, 6),
                "longitude": round(longitude, 6),
                "source": "embedded_metadata",
            }
        ],
    }


def build_consensus(
    provider_results: dict[str, dict],
    *,
    radius_km: float = DEFAULT_CLUSTER_RADIUS_KM,
) -> dict:
    """Cluster provider candidates and select the strongest agreement.

    A provider contributes at most one candidate to a cluster. Ranking favors
    independent provider agreement, then reciprocal candidate rank. The result
    deliberately avoids reporting a synthetic confidence percentage.
    """

    if radius_km <= 0:
        raise ValueError("Consensus radius must be greater than zero")

    clusters: list[dict[str, dict]] = []
    for provider_key, result in provider_results.items():
        if result.get("status") != "success":
            continue
        provider_name = result.get("provider") or result.get("model") or provider_key
        for candidate in result.get("candidates", []):
            try:
                coordinate = (
                    float(candidate["latitude"]),
                    float(candidate["longitude"]),
                )
            except (KeyError, TypeError, ValueError):
                continue

            nearest = None
            nearest_distance = None
            for cluster in clusters:
                distance = _haversine_km(coordinate, _centroid(cluster))
                if distance <= radius_km and (
                    nearest_distance is None or distance < nearest_distance
                ):
                    nearest = cluster
                    nearest_distance = distance

            evidence = {**candidate, "provider": provider_name}
            if nearest is None:
                clusters.append({provider_key: evidence})
            elif provider_key not in nearest or candidate.get("rank", 999) < nearest[
                provider_key
            ].get("rank", 999):
                nearest[provider_key] = evidence

    if not clusters:
        return {
            "status": "unavailable",
            "reason": "No provider returned a valid location candidate",
            "clusters": [],
        }

    ranked = sorted(
        clusters,
        key=lambda cluster: (
            len(cluster),
            sum(1 / max(int(item.get("rank", 1)), 1) for item in cluster.values()),
        ),
        reverse=True,
    )
    formatted = []
    for rank, cluster in enumerate(ranked, start=1):
        latitude, longitude = _centroid(cluster)
        evidence = sorted(cluster.values(), key=lambda item: item["provider"])
        formatted.append(
            {
                "rank": rank,
                "latitude": round(latitude, 6),
                "longitude": round(longitude, 6),
                "provider_count": len(cluster),
                "providers": [item["provider"] for item in evidence],
                "agreement": "multi_provider" if len(cluster) > 1 else "single_provider",
                "evidence": evidence,
            }
        )

    return {
        "status": "success",
        "selected": formatted[0],
        "clusters": formatted,
        "radius_km": radius_km,
        "confidence_note": (
            "Provider agreement improves ranking but is not a calibrated probability. "
            "Review the underlying evidence before relying on the selected location."
        ),
    }
