"""Describe social-evidence coverage without presenting it as location confidence."""

from __future__ import annotations


def assess_social_evidence(result: dict, source: dict) -> dict:
    providers = result.get("geolocation", {}).get("providers", {})
    consensus = result.get("geolocation", {}).get("consensus", {})
    selected = consensus.get("selected", {})
    ocr = result.get("visual_clues", {}).get("ocr", {})

    signals = {
        "source_provenance": bool(source.get("public_source_url")),
        "automatic_collection_record": bool(source.get("automatic_collection")),
        "declared_location": bool(source.get("declared_location")),
        "caption_or_post_text": bool(source.get("post_text")),
        "embedded_gps": providers.get("exif", {}).get("status") == "success",
        "visual_geolocation": providers.get("geoclip", {}).get("status") == "success",
        "text_place_match": providers.get("text_gazetteer", {}).get("status")
        == "success",
        "recognized_scene_text": bool(ocr.get("combined_text")),
        "independent_provider_agreement": selected.get("provider_count", 0) >= 2,
    }
    weights = {
        "source_provenance": 8,
        "automatic_collection_record": 7,
        "declared_location": 5,
        "caption_or_post_text": 7,
        "embedded_gps": 20,
        "visual_geolocation": 15,
        "text_place_match": 12,
        "recognized_scene_text": 8,
        "independent_provider_agreement": 18,
    }
    coverage_score = sum(weights[name] for name, present in signals.items() if present)

    location_signal_count = sum(
        signals[name]
        for name in ("embedded_gps", "visual_geolocation", "text_place_match")
    )
    if signals["independent_provider_agreement"]:
        level = "corroborated_lead"
    elif location_signal_count >= 2:
        level = "conflicting_or_unclustered_leads"
    elif any(
        signals[name]
        for name in ("embedded_gps", "visual_geolocation", "text_place_match")
    ):
        level = "single_signal_lead"
    else:
        level = "insufficient_location_evidence"

    cautions = []
    if signals["declared_location"] and not signals["independent_provider_agreement"]:
        cautions.append("The displayed location tag has not been independently corroborated.")
    if signals["text_place_match"] and not signals["visual_geolocation"]:
        cautions.append("Text may describe another place, a past event, or an intended destination.")
    if signals["visual_geolocation"] and selected.get("provider_count", 0) < 2:
        cautions.append("The visual candidate currently has only one model source.")
    if location_signal_count >= 2 and not signals["independent_provider_agreement"]:
        cautions.append(
            "Multiple location channels returned results but did not agree within the consensus radius."
        )
    if not signals["source_provenance"]:
        cautions.append("No public source URL was recorded for this media.")
    if (
        signals["source_provenance"]
        and not any(
            signals[name]
            for name in ("embedded_gps", "visual_geolocation", "text_place_match")
        )
    ):
        cautions.append(
            "The link was recorded, but the public page and supplied text contained "
            "no usable location signal. Add the visible caption, location tag, or an "
            "authorized screenshot."
        )

    return {
        "level": level,
        "evidence_coverage_score": coverage_score,
        "score_note": (
            "Coverage measures which evidence channels were available. It is not the "
            "probability that the selected location is correct."
        ),
        "signals": signals,
        "cautions": cautions,
    }
