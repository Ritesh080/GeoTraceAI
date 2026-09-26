"""Build a privacy-preserving OSINT handoff from normalized image evidence.

This stage does not upload the image to third-party services. It prepares
manual verification actions, keeps observations from the submitted asset in
one dependency group, and abstains until independent sources are collected.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from backend.geolocation import build_location_assessment, provider_capabilities


def build_osint_assessment(
    sha256: str,
    metadata: dict,
    source: dict | None = None,
    provider_candidates: list[dict] | None = None,
    provider_context: dict | None = None,
) -> dict:
    source_group = source.get("source_group", "submitted_asset") if source else "submitted_asset"
    gps_present = bool(metadata.get("gps_present"))
    latitude = metadata.get("latitude")
    longitude = metadata.get("longitude")
    coordinates_valid = bool(metadata.get("coordinates_valid"))
    location = build_location_assessment(metadata, source, provider_candidates)

    clues = [
        {
            "id": "asset_sha256",
            "kind": "asset_fingerprint",
            "label": "Exact file fingerprint",
            "value": sha256,
            "source_group": source_group,
        }
    ]
    actions = [
        {
            "id": "hash_search",
            "label": "Search the exact SHA-256 fingerprint",
            "provider": "Google Search",
            "url": f'https://www.google.com/search?q=%22{quote_plus(sha256)}%22',
            "sends_image": False,
        },
        {
            "id": "lens_review",
            "label": "Run a visual-match search manually",
            "provider": "Google Lens",
            "url": "https://lens.google.com/",
            "sends_image": True,
        },
        {
            "id": "tineye_review",
            "label": "Check publication and repost history",
            "provider": "TinEye",
            "url": "https://tineye.com/",
            "sends_image": True,
        },
    ]

    gps_usable = gps_present and coordinates_valid and latitude is not None and longitude is not None
    if gps_usable:
        coordinate_value = f"{latitude}, {longitude}"
        clues.append(
            {
                "id": "embedded_gps",
                "kind": "geographic_reference",
                "label": "Embedded GPS coordinates",
                "value": coordinate_value,
                "source_group": source_group,
            }
        )
        actions.extend(
            [
                {
                    "id": "osm_map_check",
                    "label": "Inspect the coordinate context",
                    "provider": "OpenStreetMap",
                    "url": f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map=16/{latitude}/{longitude}",
                    "sends_image": False,
                },
                {
                    "id": "google_maps_check",
                    "label": "Cross-check nearby landmarks",
                    "provider": "Google Maps",
                    "url": f"https://www.google.com/maps/search/?api=1&query={latitude}%2C{longitude}",
                    "sends_image": False,
                },
            ]
        )

    for key, label in (
        ("datetime_original", "Original capture time"),
        ("camera", "Camera maker"),
        ("model", "Camera model"),
        ("software", "Editing software"),
    ):
        value = metadata.get(key)
        if value:
            clues.append(
                {
                    "id": key,
                    "kind": "metadata_context",
                    "label": label,
                    "value": str(value),
                    "source_group": source_group,
                }
            )

    osintgram_clue_ids = []
    if source and source.get("platform") == "instagram":
        for clue_id, kind, label, value in (
            ("instagram_post", "publication_source", "Instagram post", source.get("canonical_url")),
            ("instagram_owner", "account_context", "Instagram account", source.get("owner_username")),
            ("instagram_published_at", "publication_time", "Instagram publication time", source.get("published_at")),
        ):
            if value:
                clues.append(
                    {
                        "id": clue_id,
                        "kind": kind,
                        "label": label,
                        "value": str(value),
                        "source_group": source_group,
                    }
                )

        claimed_location = source.get("location")
        if claimed_location and claimed_location.get("name"):
            clues.append(
                {
                    "id": "instagram_location_claim",
                    "kind": "platform_location_claim",
                    "label": "Instagram location claim",
                    "value": str(claimed_location["name"]),
                    "source_group": source_group,
                }
            )

        osintgram = source.get("osintgram") or {}
        if osintgram.get("status") in {"ready", "partial"}:
            account_about = osintgram.get("account_about") or {}
            profile = osintgram.get("profile") or {}
            for clue_id, kind, label, value in (
                ("osintgram_account_country", "account_context", "Account country", account_about.get("country")),
                ("osintgram_account_created", "account_context", "Account creation month", account_about.get("date_joined")),
                ("osintgram_business_city", "account_context", "Public business city", profile.get("city_name")),
            ):
                if value:
                    clues.append({
                        "id": clue_id,
                        "kind": kind,
                        "label": label,
                        "value": str(value),
                        "source_group": f"instagram_account:{source.get('owner_username', 'unknown')}",
                    })
                    osintgram_clue_ids.append(clue_id)
            for index, tagged_location in enumerate((osintgram.get("locations") or [])[:5]):
                clue_id = f"osintgram_tagged_location_{index + 1}"
                clues.append({
                    "id": clue_id,
                    "kind": "platform_location_history",
                    "label": "Tagged post location",
                    "value": str(tagged_location.get("address") or tagged_location.get("name")),
                    "source_group": f"instagram_account:{source.get('owner_username', 'unknown')}",
                })
                osintgram_clue_ids.append(clue_id)

    reasons = [
        "No independent web source has been collected yet.",
        "Reverse-image matches require a manual provider search or configured API adapter.",
    ]
    if not gps_usable:
        reasons.append("No valid embedded GPS coordinate is available for map verification.")
    if osintgram_clue_ids:
        reasons.append("OSINTgram profile and post-history clues come from the same Instagram account and are not independent location confirmation.")

    dependency_groups = [
        {
            "id": source_group,
            "label": "Instagram post" if source and source.get("platform") == "instagram" else "Submitted image",
            "member_ids": [clue["id"] for clue in clues if clue["id"] not in osintgram_clue_ids],
            "explanation": "Hash, EXIF, and file-forensic observations share one origin and count as one source group.",
        }
    ]
    if osintgram_clue_ids:
        dependency_groups.append({
            "id": f"instagram_account:{source.get('owner_username', 'unknown')}",
            "label": "OSINTgram public account context",
            "member_ids": osintgram_clue_ids,
            "explanation": "Profile and tagged-post observations are related Instagram account evidence and do not count as independent confirmation.",
        })

    return {
        "status": "ready_for_review",
        "privacy": {
            "automatic_external_upload": False,
            "external_processing": bool(provider_context and provider_context.get("external_processing")),
            "external_provider": provider_context.get("provider") if provider_context else None,
            "note": (
                str(provider_context["privacy_note"])
                if provider_context
                else
                "GeoTrace retrieved this user-requested Instagram post for analysis; it did not send the image to other OSINT providers."
                if source and source.get("platform") == "instagram"
                else "GeoTrace AI does not send the submitted image to OSINT providers automatically."
            ),
        },
        "clues": clues,
        "actions": actions,
        "dependency_groups": dependency_groups,
        "candidates": location["candidates"],
        "conflicts": location["conflicts"],
        "provider_status": provider_capabilities(),
        "calibration": provider_context.get("calibration") if provider_context else None,
        "uncertainty": {
            "outcome": location["outcome"],
            "confidence": location["confidence"],
            "calibrated": location["calibrated"],
            "independent_source_groups": location["independent_source_groups"],
            "abstention_reasons": reasons,
        },
    }
