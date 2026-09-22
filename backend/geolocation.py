"""Normalize and rank location evidence without overstating certainty.

The first-party pipeline currently has no trained visual-geolocation model.
This module gives metadata and future provider adapters one stable result shape,
while keeping confidence uncalibrated until benchmark evidence exists.
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any

from backend.local_visual_model import is_trained as local_visual_model_is_trained
from backend.local_map_verification import is_built as local_map_index_is_built
from backend.local_street_imagery import is_built as local_street_index_is_built
from backend.local_source_provenance import is_built as local_provenance_index_is_built
from backend.location_calibration import calibration_is_ready


CONFLICT_DISTANCE_KM = 25.0


def _valid_coordinates(latitude: Any, longitude: Any) -> bool:
    return (
        isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )


def _distance_km(first: dict, second: dict) -> float | None:
    if not _valid_coordinates(first.get("latitude"), first.get("longitude")):
        return None
    if not _valid_coordinates(second.get("latitude"), second.get("longitude")):
        return None
    lat1, lon1 = radians(first["latitude"]), radians(first["longitude"])
    lat2, lon2 = radians(second["latitude"]), radians(second["longitude"])
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(haversine))


def build_location_assessment(
    metadata: dict,
    source: dict | None = None,
    provider_candidates: list[dict] | None = None,
) -> dict:
    """Create ranked candidates and an explicit evidence/uncertainty record.

    Provider candidates are accepted as an adapter boundary, but no external
    provider is called here. A future adapter must supply its own source group
    and may supply a calibrated confidence only when its benchmark supports it.
    """
    source_group = source.get("source_group", "submitted_asset") if source else "submitted_asset"
    candidates: list[dict] = []

    latitude = metadata.get("latitude")
    longitude = metadata.get("longitude")
    gps_usable = bool(metadata.get("gps_present") and metadata.get("coordinates_valid")) and _valid_coordinates(latitude, longitude)
    if gps_usable:
        candidates.append(
            {
                "id": "embedded_gps",
                "label": f"{latitude}, {longitude}",
                "latitude": latitude,
                "longitude": longitude,
                "precision_tier": "exact_coordinate",
                "basis": "Embedded EXIF GPS coordinates",
                "provider": "GeoTrace metadata extractor",
                "source_group": source_group,
                "confidence": None,
                "calibrated": False,
                "supports": [
                    {
                        "evidence_id": "embedded_gps",
                        "summary": "The submitted file contains valid GPS coordinates.",
                        "source_group": source_group,
                    }
                ],
                "contradictions": [],
                "verification_status": "needs_independent_corroboration",
                "needs_corroboration": True,
            }
        )

    claimed_location = source.get("location") if source else None
    if claimed_location and claimed_location.get("name"):
        claimed_latitude = claimed_location.get("latitude")
        claimed_longitude = claimed_location.get("longitude")
        coordinates_available = _valid_coordinates(claimed_latitude, claimed_longitude)
        candidates.append(
            {
                "id": "platform_location_claim",
                "label": str(claimed_location["name"]),
                "latitude": claimed_latitude if coordinates_available else None,
                "longitude": claimed_longitude if coordinates_available else None,
                "precision_tier": "place_claim" if coordinates_available else "named_place",
                "basis": "Location label attached to the source post",
                "provider": str(source.get("platform", "source platform")).title(),
                "source_group": source_group,
                "confidence": None,
                "calibrated": False,
                "supports": [
                    {
                        "evidence_id": "instagram_location_claim",
                        "summary": "The source post carries this location label.",
                        "source_group": source_group,
                    }
                ],
                "contradictions": [],
                "verification_status": "unverified_platform_claim",
                "needs_corroboration": True,
            }
        )

    for index, raw_candidate in enumerate(provider_candidates or []):
        label = str(raw_candidate.get("label") or f"Provider candidate {index + 1}")
        candidate_source_group = str(raw_candidate.get("source_group") or f"provider_{index + 1}")
        confidence = raw_candidate.get("confidence")
        calibrated = bool(raw_candidate.get("calibrated", False))
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            confidence = None
            calibrated = False
        candidates.append(
            {
                "id": str(raw_candidate.get("id") or f"provider_candidate_{index + 1}"),
                "label": label,
                "latitude": raw_candidate.get("latitude"),
                "longitude": raw_candidate.get("longitude"),
                "precision_tier": str(raw_candidate.get("precision_tier") or "unknown"),
                "basis": str(raw_candidate.get("basis") or "External geolocation provider result"),
                "provider": str(raw_candidate.get("provider") or "Configured provider"),
                "source_group": candidate_source_group,
                "confidence": confidence,
                "calibrated": calibrated,
                "retrieval_score": raw_candidate.get("retrieval_score"),
                "calibration_samples": raw_candidate.get("calibration_samples"),
                "supports": list(raw_candidate.get("supports") or []),
                "contradictions": list(raw_candidate.get("contradictions") or []),
                "verification_status": str(raw_candidate.get("verification_status") or "provider_candidate_needs_corroboration"),
                "needs_corroboration": True,
            }
        )

    conflicts: list[dict] = []
    for left_index, left in enumerate(candidates):
        for right in candidates[left_index + 1 :]:
            distance = _distance_km(left, right)
            if distance is None or distance < CONFLICT_DISTANCE_KM:
                continue
            conflict_id = f"location_conflict_{len(conflicts) + 1}"
            summary = f"Candidates are approximately {distance:,.0f} km apart."
            conflict = {
                "id": conflict_id,
                "summary": summary,
                "candidate_ids": [left["id"], right["id"]],
                "distance_km": round(distance, 1),
            }
            conflicts.append(conflict)
            for candidate in (left, right):
                candidate["contradictions"].append(
                    {
                        "evidence_id": conflict_id,
                        "summary": summary,
                        "source_group": "cross_candidate_check",
                    }
                )
                candidate["verification_status"] = "conflicting_evidence"

    def rank_key(candidate: dict) -> tuple:
        calibrated_confidence = candidate["confidence"] if candidate["calibrated"] and candidate["confidence"] is not None else -1
        exact_coordinate = 1 if candidate["precision_tier"] == "exact_coordinate" else 0
        return (-calibrated_confidence, -exact_coordinate, candidate["id"])

    candidates.sort(key=rank_key)
    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank

    independent_groups = {candidate["source_group"] for candidate in candidates}
    calibrated_candidates = [
        candidate for candidate in candidates
        if candidate.get("calibrated") and candidate.get("confidence") is not None
    ]
    overall_confidence = calibrated_candidates[0]["confidence"] if calibrated_candidates and not conflicts else None
    overall_calibrated = overall_confidence is not None
    if not candidates:
        outcome = "insufficient_evidence"
    elif conflicts:
        outcome = "conflicting_evidence"
    elif overall_calibrated and overall_confidence < 0.6:
        outcome = "calibrated_low_confidence_abstention"
    elif len(independent_groups) < 2:
        outcome = "candidate_needs_corroboration"
    else:
        outcome = "multiple_candidates_need_review"

    return {
        "candidates": candidates,
        "conflicts": conflicts,
        "outcome": outcome,
        "confidence": overall_confidence,
        "calibrated": overall_calibrated,
        "independent_source_groups": len(independent_groups),
    }


def provider_capabilities() -> list[dict]:
    """Expose honest capability coverage to both the API and interface."""
    return [
        {"capability": "EXIF/GPS extraction", "status": "active", "provider": "GeoTrace"},
        {"capability": "Image forensics", "status": "active", "provider": "GeoTrace"},
        {
            "capability": "Visual geolocation",
            "status": "active" if local_visual_model_is_trained() else "needs_training_data",
            "provider": "GeoTrace Visual v0",
        },
        {
            "capability": "Automated map context verification",
            "status": "active" if local_map_index_is_built() else "needs_map_index",
            "provider": "GeoTrace local place index",
        },
        {
            "capability": "Street-level imagery comparison",
            "status": "active" if local_street_index_is_built() else "needs_street_reference_data",
            "provider": "GeoTrace Street Compare v0",
        },
        {
            "capability": "Reverse-image and source provenance",
            "status": "active" if local_provenance_index_is_built() else "needs_source_reference_data",
            "provider": "GeoTrace Provenance v0",
        },
        {
            "capability": "Calibrated location confidence",
            "status": "active" if calibration_is_ready() else "benchmark_required",
            "provider": "GeoTrace held-out benchmark",
        },
    ]
