"""Describe social-evidence coverage without presenting it as location confidence."""

from __future__ import annotations


def assess_social_evidence(result: dict, source: dict) -> dict:
    providers = result.get("geolocation", {}).get("providers", {})
    consensus = result.get("geolocation", {}).get("consensus", {})
    selected = consensus.get("selected", {})
    ocr = result.get("visual_clues", {}).get("ocr", {})
    collection = source.get("automatic_collection", {})
    generic_preview_rejected = (
        collection.get("media_status") == "generic_platform_preview_rejected"
    )

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
        "generic_platform_preview_rejected": generic_preview_rejected,
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
        "generic_platform_preview_rejected": 0,
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
    if generic_preview_rejected:
        cautions.append(
            "Instagram returned generic platform artwork instead of the requested "
            "post image. GeoTrace excluded it from visual geolocation."
        )
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

    show_location = (
        signals["embedded_gps"] or signals["independent_provider_agreement"]
    ) and not generic_preview_rejected
    if not show_location and location_signal_count:
        cautions.append(
            "GeoTrace is withholding a location conclusion because the available "
            "location signal is not independently corroborated."
        )

    return {
        "level": level,
        "show_location": show_location,
        "display_status": (
            "corroborated_location_lead" if show_location else "abstained_unverified"
        ),
        "display_message": (
            "Location lead is supported by independent evidence channels."
            if show_location
            else "No location is shown because the available evidence is insufficient or uncorroborated."
        ),
        "evidence_coverage_score": coverage_score,
        "score_note": (
            "Coverage measures which evidence channels were available. It is not the "
            "probability that the selected location is correct."
        ),
        "signals": signals,
        "cautions": cautions,
    }
