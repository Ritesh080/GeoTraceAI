"""Structured Micro-OSINT evidence ledger for analyst-led geolocation.

The ledger separates three activities which must not be collapsed:

1. observation: what is visible in a bounded image region;
2. inference: which location claim the observation may support or exclude;
3. verification: which reference and analyst review tested that inference.

This module does not manufacture a location probability.  It produces
auditable candidate filters and keeps every clue derived from the submitted
asset in the same dependency group unless a different origin is explicit.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "micro-osint-ledger-v1"

CATEGORIES = {
    "utility_infrastructure": "Poles, insulators, transformers, wiring, and service equipment",
    "street_furniture": "Bollards, hydrants, barriers, lamps, bins, and guardrails",
    "road_system": "Markings, signs, chevrons, traffic control, and driving-side cues",
    "vehicle_registration": "Plate format, colors, stickers, and vehicle-region conventions",
    "built_environment": "Architecture, materials, roofs, drainage, and construction practice",
    "language_and_text": "Scripts, words, abbreviations, domains, and public identifiers",
    "flora_and_land_use": "Vegetation, crops, phenology, landscaping, and agricultural practice",
    "terrain_and_geology": "Landform, exposed rock, soil appearance, and horizon geometry",
    "weather_and_light": "Weather, illumination, shadow, and seasonal indicators",
    "commercial_and_civic": "Brands, uniforms, transit systems, agencies, and public services",
    "other": "A documented clue outside the current taxonomy",
}

METHOD_MATURITY = {"unvalidated", "experimental", "validated"}
REVIEW_STATES = {"observed", "reviewed", "verified", "rejected"}
RELATIONSHIPS = {"supports", "excludes", "neutral"}


def _text(value: Any, field: str, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    result = str(value or "").strip()
    if required and not result:
        raise ValueError(f"{field} is required.")
    return result or None


def _region(value: Any) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("region must be an object with normalized x, y, width, and height values.")
    result = {}
    for field in ("x", "y", "width", "height"):
        number = value.get(field)
        if not isinstance(number, (int, float)) or isinstance(number, bool):
            raise ValueError(f"region.{field} must be numeric.")
        result[field] = float(number)
    if not all(0 <= result[field] <= 1 for field in result):
        raise ValueError("region values must be normalized between 0 and 1.")
    if result["width"] <= 0 or result["height"] <= 0:
        raise ValueError("region width and height must be greater than zero.")
    if result["x"] + result["width"] > 1 or result["y"] + result["height"] > 1:
        raise ValueError("region must stay inside the image boundary.")
    return result


def _references(value: Any) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("verification.references must be a list.")
    records = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError("Each verification reference must be an object.")
        records.append({
            "id": _text(raw.get("id") or f"reference-{index + 1}", "reference.id"),
            "title": _text(raw.get("title"), "reference.title"),
            "uri": _text(raw.get("uri"), "reference.uri"),
            "publisher": _text(raw.get("publisher"), "reference.publisher", required=False),
            "license": _text(raw.get("license"), "reference.license", required=False),
            "retrieved_at": _text(raw.get("retrieved_at"), "reference.retrieved_at", required=False),
        })
    return records


def _normalize_clue(raw: dict, known_candidates: set[str]) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Each Micro-OSINT clue must be an object.")
    forbidden_probability_fields = {"confidence", "probability", "score"} & set(raw)
    if forbidden_probability_fields:
        fields = ", ".join(sorted(forbidden_probability_fields))
        raise ValueError(f"Uncalibrated numeric certainty is not accepted in Micro-OSINT clues: {fields}.")

    clue_id = _text(raw.get("id"), "id")
    category = _text(raw.get("category"), "category")
    if category not in CATEGORIES:
        raise ValueError(f"Unknown Micro-OSINT category: {category}.")
    source_group = _text(raw.get("source_group") or "submitted_asset", "source_group")

    inference_raw = raw.get("inference") or {}
    if not isinstance(inference_raw, dict):
        raise ValueError("inference must be an object.")
    forbidden_inference_fields = {"confidence", "probability", "score"} & set(inference_raw)
    if forbidden_inference_fields:
        fields = ", ".join(sorted(forbidden_inference_fields))
        raise ValueError(f"Inference cannot contain uncalibrated numeric certainty: {fields}.")
    relationship = _text(inference_raw.get("relationship") or "neutral", "inference.relationship")
    if relationship not in RELATIONSHIPS:
        raise ValueError(f"Unknown inference relationship: {relationship}.")
    candidate_ids = [str(item).strip() for item in inference_raw.get("candidate_ids") or [] if str(item).strip()]
    unknown_candidates = sorted(set(candidate_ids) - known_candidates)
    if unknown_candidates:
        raise ValueError(f"Inference references unknown candidate IDs: {', '.join(unknown_candidates)}.")
    if relationship in {"supports", "excludes"} and not candidate_ids:
        raise ValueError(f"A {relationship} inference must name at least one candidate ID.")

    method_maturity = _text(inference_raw.get("method_maturity") or "unvalidated", "inference.method_maturity")
    if method_maturity not in METHOD_MATURITY:
        raise ValueError(f"Unknown method maturity: {method_maturity}.")

    verification_raw = raw.get("verification") or {}
    if not isinstance(verification_raw, dict):
        raise ValueError("verification must be an object.")
    review_state = _text(verification_raw.get("status") or "observed", "verification.status")
    if review_state not in REVIEW_STATES:
        raise ValueError(f"Unknown verification status: {review_state}.")
    references = _references(verification_raw.get("references"))
    if review_state == "verified" and not references:
        raise ValueError("A verified clue must cite at least one reference.")

    eligible = (
        review_state == "verified"
        and method_maturity == "validated"
        and relationship in {"supports", "excludes"}
        and bool(candidate_ids)
    )
    limitations = [str(item).strip() for item in raw.get("limitations") or [] if str(item).strip()]
    return {
        "id": clue_id,
        "category": category,
        "category_label": CATEGORIES[category],
        "source_group": source_group,
        "observation": {
            "description": _text(raw.get("observation"), "observation"),
            "region": _region(raw.get("region")),
            "capture_note": _text(raw.get("capture_note"), "capture_note", required=False),
        },
        "inference": {
            "claim": _text(inference_raw.get("claim"), "inference.claim", required=False),
            "relationship": relationship,
            "candidate_ids": sorted(set(candidate_ids)),
            "rationale": _text(inference_raw.get("rationale"), "inference.rationale", required=False),
            "method_maturity": method_maturity,
        },
        "verification": {
            "status": review_state,
            "analyst": _text(verification_raw.get("analyst"), "verification.analyst", required=False),
            "reviewed_at": _text(verification_raw.get("reviewed_at"), "verification.reviewed_at", required=False),
            "references": references,
            "notes": _text(verification_raw.get("notes"), "verification.notes", required=False),
        },
        "limitations": limitations,
        "eligible_for_candidate_filter": eligible,
        "certainty": {
            "numeric_probability": None,
            "calibrated": False,
            "note": "This clue is categorical evidence, not a calibrated location probability.",
        },
    }


def build_micro_osint_ledger(
    clues: list[dict] | None,
    candidate_ids: list[str] | None = None,
) -> dict:
    """Validate clues and produce an advisory, dependency-aware evidence ledger."""
    known_candidates = {str(item).strip() for item in candidate_ids or [] if str(item).strip()}
    normalized = []
    seen_ids = set()
    for raw in clues or []:
        clue = _normalize_clue(raw, known_candidates)
        if clue["id"] in seen_ids:
            raise ValueError(f"Duplicate Micro-OSINT clue ID: {clue['id']}.")
        seen_ids.add(clue["id"])
        normalized.append(clue)

    source_members: dict[str, list[str]] = defaultdict(list)
    filters = {
        candidate_id: {"supports": [], "excludes": [], "research_leads": []}
        for candidate_id in sorted(known_candidates)
    }
    for clue in normalized:
        source_members[clue["source_group"]].append(clue["id"])
        relationship = clue["inference"]["relationship"]
        for candidate_id in clue["inference"]["candidate_ids"]:
            if clue["eligible_for_candidate_filter"]:
                filters[candidate_id][relationship].append(clue["id"])
            else:
                filters[candidate_id]["research_leads"].append(clue["id"])

    dependency_groups = [
        {
            "id": source_group,
            "member_ids": sorted(member_ids),
            "independent_source_count": 1,
            "explanation": (
                "All clues in this group share one origin. Repeated features do not become independent corroboration."
            ),
        }
        for source_group, member_ids in sorted(source_members.items())
    ]
    active_filters = sum(
        bool(record["supports"] or record["excludes"])
        for record in filters.values()
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready_for_analyst_input" if not normalized else "analyst_review_in_progress",
        "taxonomy": [{"id": key, "description": value} for key, value in CATEGORIES.items()],
        "workflow": ["observation", "inference", "verification", "candidate_filter", "independent_corroboration"],
        "clues": normalized,
        "dependency_groups": dependency_groups,
        "candidate_filters": {
            "mode": "advisory_only",
            "candidates": filters,
            "active_candidate_count": active_filters,
            "rules": [
                "Only verified clues using validated methods enter candidate filters.",
                "Unvalidated and experimental methods remain research leads.",
                "Missing clues are never treated as contradictions.",
                "Supports and exclusions do not create a location probability.",
            ],
        },
        "assessment": {
            "formal_location_conclusion": False,
            "numeric_location_probability": None,
            "eligible_clue_count": sum(clue["eligible_for_candidate_filter"] for clue in normalized),
            "independent_source_groups": len(source_members),
            "requires_analyst_review": True,
            "requires_independent_corroboration": True,
        },
    }


def attach_micro_osint_workspace(osint: dict) -> dict:
    """Attach an empty ledger to an OSINT result without changing candidates."""
    enriched = deepcopy(osint)
    candidate_ids = [str(item.get("id")) for item in enriched.get("candidates") or [] if item.get("id")]
    enriched["micro_osint"] = build_micro_osint_ledger([], candidate_ids)
    return enriched
