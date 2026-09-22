"""Phase 5: combine cyber and location evidence without conflating scores.

Forensic reliability describes the submitted asset. Location confidence
describes a candidate and is retained only when it was independently
calibrated. Neither score is converted into the other.
"""
from __future__ import annotations

from typing import Any


SUBMITTED_ASSET_GROUPS = {"submitted_asset"}
MIN_LOCATION_CONFIDENCE = 0.60
MIN_INDEPENDENT_LOCATION_GROUPS = 2


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _candidate_source_groups(candidate: dict) -> list[str]:
    groups = set()
    candidate_group = str(candidate.get("source_group") or "").strip()
    if candidate_group:
        groups.add(candidate_group)
    for collection in ("supports", "contradictions"):
        for record in candidate.get(collection, []):
            source_group = str(record.get("source_group") or "").strip()
            if source_group:
                groups.add(source_group)
    return sorted(groups)


def _independent_groups(groups: list[str], submitted_source_group: str) -> list[str]:
    excluded = SUBMITTED_ASSET_GROUPS | {submitted_source_group}
    return [group for group in groups if group not in excluded and not group.startswith("instagram:")]


def fuse_evidence(cyber_result: dict, osint: dict) -> dict:
    """Build a transparent Phase-5 decision from cyber and location records."""
    forensics = cyber_result.get("forensics") or {}
    forensic_score = _number(forensics.get("reliability_score"))
    tampering_suspected = bool(forensics.get("tampering_suspected"))
    asset_integrity_concern = tampering_suspected or (forensic_score is not None and forensic_score < 0.55)

    submitted_source_group = str(
        (cyber_result.get("source") or {}).get("source_group") or "submitted_asset"
    )
    conflicts = list(osint.get("conflicts") or [])
    candidate_records = []
    for candidate in osint.get("candidates") or []:
        groups = _candidate_source_groups(candidate)
        independent = _independent_groups(groups, submitted_source_group)
        confidence = _number(candidate.get("confidence")) if candidate.get("calibrated") else None
        blockers = []
        if asset_integrity_concern:
            blockers.append("submitted_asset_has_forensic_reliability_concerns")
        if candidate.get("contradictions"):
            blockers.append("candidate_has_contradictory_evidence")
        if confidence is None:
            blockers.append("location_confidence_is_not_calibrated")
        elif confidence < MIN_LOCATION_CONFIDENCE:
            blockers.append("calibrated_location_confidence_below_threshold")
        if len(independent) < MIN_INDEPENDENT_LOCATION_GROUPS:
            blockers.append("insufficient_independent_location_sources")
        candidate_records.append({
            "candidate_id": candidate.get("id"),
            "rank": candidate.get("rank"),
            "label": candidate.get("label"),
            "forensic_reliability": forensic_score,
            "location_confidence": confidence,
            "location_confidence_calibrated": confidence is not None,
            "source_groups": groups,
            "independent_location_source_groups": independent,
            "support_count": len(candidate.get("supports") or []),
            "contradiction_count": len(candidate.get("contradictions") or []),
            "eligible_for_location_conclusion": not blockers,
            "blockers": blockers,
        })

    top = candidate_records[0] if candidate_records else None
    if not top:
        decision = "abstain_no_location_candidate"
    elif asset_integrity_concern:
        decision = "abstain_asset_integrity_concern"
    elif conflicts:
        decision = "abstain_conflicting_location_evidence"
    elif top["eligible_for_location_conclusion"]:
        decision = "location_candidate_supported_for_review"
    else:
        decision = "location_candidate_needs_more_evidence"

    return {
        "phase": "ai_cyber_evidence_integration",
        "decision": decision,
        "forensic_reliability": {
            "score": forensic_score,
            "level": forensics.get("reliability_level"),
            "tampering_suspected": tampering_suspected,
            "meaning": "Trust estimate for the submitted file and its forensic signals; not location confidence.",
        },
        "location_assessment": {
            "candidate_count": len(candidate_records),
            "conflict_count": len(conflicts),
            "minimum_calibrated_confidence": MIN_LOCATION_CONFIDENCE,
            "minimum_independent_source_groups": MIN_INDEPENDENT_LOCATION_GROUPS,
            "candidates": candidate_records,
        },
        "separation_rule": "Forensic reliability never raises location confidence, and location confidence never clears forensic concerns.",
    }
