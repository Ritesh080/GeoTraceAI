"""Phase 6: explain conflicts across cyber, metadata, and location evidence."""
from __future__ import annotations

import copy
from math import asin, cos, radians, sin, sqrt


LOCATION_CONFLICT_KM = 25.0
CRITICAL_DISTANCE_KM = 1000.0
HIGH_DISTANCE_KM = 100.0


def _coordinate(candidate: dict) -> tuple[float, float] | None:
    latitude = candidate.get("latitude")
    longitude = candidate.get("longitude")
    if (
        isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):
        return float(latitude), float(longitude)
    return None


def _distance_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = radians(first[0]), radians(first[1])
    lat2, lon2 = radians(second[0]), radians(second[1])
    delta_latitude = lat2 - lat1
    delta_longitude = lon2 - lon1
    haversine = (
        sin(delta_latitude / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_longitude / 2) ** 2
    )
    return 6371.0088 * 2 * asin(sqrt(haversine))


def _severity(distance_km: float) -> str:
    if distance_km >= CRITICAL_DISTANCE_KM:
        return "critical"
    if distance_km >= HIGH_DISTANCE_KM:
        return "high"
    return "medium"


def _append_contradiction(candidate: dict, conflict: dict) -> None:
    contradictions = candidate.setdefault("contradictions", [])
    if any(record.get("evidence_id") == conflict["id"] for record in contradictions):
        return
    contradictions.append({
        "evidence_id": conflict["id"],
        "summary": conflict["summary"],
        "source_group": "phase6_conflict_analysis",
        "conflict_type": conflict["type"],
        "severity": conflict["severity"],
    })
    candidate["verification_status"] = "conflicting_evidence"


def analyze_conflicts(cyber_result: dict, osint: dict) -> dict:
    """Return OSINT evidence enriched with typed, source-aware conflicts."""
    enriched = copy.deepcopy(osint)
    candidates = enriched.get("candidates") or []
    conflicts = []
    seen_pairs = set()

    for left_index, left in enumerate(candidates):
        left_coordinate = _coordinate(left)
        if left_coordinate is None:
            continue
        for right in candidates[left_index + 1:]:
            right_coordinate = _coordinate(right)
            if right_coordinate is None:
                continue
            distance = _distance_km(left_coordinate, right_coordinate)
            if distance < LOCATION_CONFLICT_KM:
                continue
            pair = tuple(sorted((str(left.get("id")), str(right.get("id")))))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            conflict = {
                "id": f"phase6_location_conflict_{len(conflicts) + 1}",
                "type": "coordinate_disagreement",
                "severity": _severity(distance),
                "summary": (
                    f"{left.get('label', 'Candidate')} and {right.get('label', 'candidate')} "
                    f"are approximately {distance:,.0f} km apart."
                ),
                "candidate_ids": [left.get("id"), right.get("id")],
                "source_groups": sorted({str(left.get("source_group") or "unknown"), str(right.get("source_group") or "unknown")}),
                "distance_km": round(distance, 1),
                "forces_abstention": True,
            }
            conflicts.append(conflict)
            _append_contradiction(left, conflict)
            _append_contradiction(right, conflict)

    forensics = cyber_result.get("forensics") or {}
    score = forensics.get("reliability_score")
    unreliable = bool(forensics.get("tampering_suspected")) or (
        isinstance(score, (int, float)) and not isinstance(score, bool) and score < 0.55
    )
    embedded_gps = next((candidate for candidate in candidates if candidate.get("id") == "embedded_gps"), None)
    if unreliable and embedded_gps:
        conflict = {
            "id": f"phase6_integrity_conflict_{len(conflicts) + 1}",
            "type": "asset_integrity_vs_embedded_location",
            "severity": "high",
            "summary": "Embedded GPS is present, but the submitted asset has significant forensic reliability concerns.",
            "candidate_ids": [embedded_gps.get("id")],
            "source_groups": [str(embedded_gps.get("source_group") or "submitted_asset")],
            "distance_km": None,
            "forces_abstention": True,
        }
        conflicts.append(conflict)
        _append_contradiction(embedded_gps, conflict)

    prior_conflicts = enriched.get("conflicts") or []
    evaluated = {
        "coordinate_candidates": sum(_coordinate(candidate) is not None for candidate in candidates),
        "prior_conflict_records": len(prior_conflicts),
        "map_records": len((enriched.get("map_verification") or {}).get("records") or []),
        "street_records": len((enriched.get("street_imagery_comparison") or {}).get("records") or []),
        "ocr_available": bool((cyber_result.get("metadata") or {}).get("ocr_text")),
    }
    enriched["conflicts"] = conflicts
    enriched["conflict_analysis"] = {
        "status": "conflicts_detected" if conflicts else "no_explicit_conflicts_detected",
        "blocking_conflicts": sum(bool(conflict["forces_abstention"]) for conflict in conflicts),
        "conflicts": conflicts,
        "evaluated": evaluated,
        "limitations": [
            "Missing evidence and low street-image similarity are not treated as contradictions.",
            "OCR is considered contradictory only when a future language-aware place extractor produces an explicit competing location.",
            "A conflict explains disagreement; it does not identify which source is correct.",
        ],
    }
    if conflicts:
        uncertainty = enriched.setdefault("uncertainty", {})
        uncertainty["outcome"] = "conflicting_evidence"
        uncertainty["confidence"] = None
        uncertainty["calibrated"] = False
        reasons = uncertainty.setdefault("abstention_reasons", [])
        reason = "Phase 6 detected explicit conflicts between evidence sources."
        if reason not in reasons:
            reasons.append(reason)
    return enriched
