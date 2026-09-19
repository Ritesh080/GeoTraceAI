"""Build a privacy-preserving OSINT handoff from normalized image evidence.

This stage does not upload the image to third-party services. It prepares
manual verification actions, keeps observations from the submitted asset in
one dependency group, and abstains until independent sources are collected.
"""
from __future__ import annotations

from urllib.parse import quote_plus


def build_osint_assessment(sha256: str, metadata: dict) -> dict:
    gps_present = bool(metadata.get("gps_present"))
    latitude = metadata.get("latitude")
    longitude = metadata.get("longitude")
    coordinates_valid = bool(metadata.get("coordinates_valid"))

    clues = [
        {
            "id": "asset_sha256",
            "kind": "asset_fingerprint",
            "label": "Exact file fingerprint",
            "value": sha256,
            "source_group": "submitted_asset",
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
                "source_group": "submitted_asset",
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
                    "source_group": "submitted_asset",
                }
            )

    reasons = [
        "No independent web source has been collected yet.",
        "Reverse-image matches require a manual provider search or configured API adapter.",
    ]
    if not gps_usable:
        reasons.append("No valid embedded GPS coordinate is available for map verification.")

    return {
        "status": "ready_for_review",
        "privacy": {
            "automatic_external_upload": False,
            "note": "GeoTrace AI does not send the submitted image to OSINT providers automatically.",
        },
        "clues": clues,
        "actions": actions,
        "dependency_groups": [
            {
                "id": "submitted_asset",
                "label": "Submitted image",
                "member_ids": [clue["id"] for clue in clues],
                "explanation": "Hash, EXIF, and file-forensic observations share one origin and count as one source group.",
            }
        ],
        "conflicts": [],
        "uncertainty": {
            "outcome": "insufficient_evidence",
            "confidence": None,
            "calibrated": False,
            "abstention_reasons": reasons,
        },
    }
