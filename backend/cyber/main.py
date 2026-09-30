import argparse
import json

from hash_service import calculate_sha256
from file_validator import validate_image
from exif_service import extract_exif
from metadata_analyzer import analyze_metadata
from image_forensics import analyze_image_forensics
from reliability_engine import compute_reliability
from geoclip_service import DEFAULT_TOP_K, MAX_TOP_K, geolocate_image
from consensus_service import (
    DEFAULT_CLUSTER_RADIUS_KM,
    build_consensus,
    exif_location_result,
)
from local_clue_service import extract_local_clues
from text_location_service import extract_text_location_candidates


def analyze_text_evidence(
    context_text: str,
    *,
    consensus_radius_km: float = DEFAULT_CLUSTER_RADIUS_KM,
) -> dict:
    """Analyze social-post text when no supporting image was supplied."""

    provider_results = {
        "exif": {
            "status": "skipped",
            "provider": "EXIF GPS",
            "reason": "No image was supplied",
            "candidates": [],
        },
        "geoclip": {
            "status": "skipped",
            "model": "GeoCLIP",
            "reason": "No image was supplied",
            "candidates": [],
        },
        "text_gazetteer": extract_text_location_candidates(context_text),
    }
    consensus = build_consensus(provider_results, radius_km=consensus_radius_km)
    return {
        "status": "success",
        "sha256": None,
        "file": {
            "valid": None,
            "status": "not_provided",
            "reason": "Social-media evidence was analyzed without an image",
        },
        "metadata": {},
        "visual_clues": {
            "processing": "not_available_without_image",
            "ocr": {
                "status": "skipped",
                "reason": "No image was supplied",
                "combined_text": "",
                "indian_scripts": [],
            },
            "image_characteristics": {},
        },
        "geolocation": {
            "status": consensus["status"],
            "providers": provider_results,
            "consensus": consensus,
            "privacy": {
                "processing_mode": "local_only",
                "image_shared_externally": False,
            },
        },
    }


def analyze_image(
    file_path: str,
    *,
    include_geolocation: bool = True,
    include_ocr: bool = True,
    top_k: int = DEFAULT_TOP_K,
    consensus_radius_km: float = DEFAULT_CLUSTER_RADIUS_KM,
    context_text: str = "",
) -> dict:

    file_info = validate_image(file_path)

    if not file_info["valid"]:
        return {
            "status": "rejected",
            "file": file_info
        }

    sha256 = calculate_sha256(file_path)

    raw_exif = extract_exif(file_path)

    meta_analysis = analyze_metadata(raw_exif)

    img_analysis = analyze_image_forensics(file_path)

    # Merge indicators from Phase 2 (metadata) and Phase 3 (image)
    all_indicators = (
        meta_analysis["forensics"]["indicators"]
        + img_analysis["indicators"]
    )

    # Phase 4: compute reliability score
    reliability = compute_reliability(
        indicators=all_indicators,
        image_forensics=img_analysis["image_forensics"],
    )

    visual_clues = extract_local_clues(file_path, include_ocr=include_ocr)
    ocr_text = visual_clues.get("ocr", {}).get("combined_text", "")
    text_locations = extract_text_location_candidates(context_text, ocr_text)

    provider_results = {
        "exif": exif_location_result(raw_exif),
        "geoclip": (
            geolocate_image(file_path, top_k=top_k)
            if include_geolocation
            else {
                "status": "skipped",
                "model": "GeoCLIP",
                "reason": "Disabled for this analysis",
                "candidates": [],
            }
        ),
        "text_gazetteer": text_locations,
    }

    consensus = build_consensus(
        provider_results,
        radius_km=consensus_radius_km,
    )
    geolocation = {
        "status": consensus["status"],
        "providers": provider_results,
        "consensus": consensus,
        "privacy": {
            "processing_mode": "local_only",
            "image_shared_externally": False,
        },
    }

    return {
        "status": "success",

        "sha256": sha256,

        "file": file_info,

        "raw_exif": raw_exif,

        "metadata": meta_analysis["metadata"],

        "image_forensics": img_analysis["image_forensics"],

        "forensics": {
            "indicators": all_indicators,
            "indicator_count": len(all_indicators),
            "reliability_score": reliability["reliability_score"],
            "reliability_level": reliability["reliability_level"],
            "tampering_suspected": reliability["tampering_suspected"],
            "scored_indicators": reliability["scored_indicators"],
            "continuous_adjustments": reliability["continuous_adjustments"],
            "total_penalty": reliability["total_penalty"],
        },

        "visual_clues": visual_clues,

        "geolocation": geolocation,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validate and analyze an image with the GeoTrace pipeline."
    )
    parser.add_argument("image_path", help="Path to a JPEG, PNG, or WebP image")
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        choices=range(1, MAX_TOP_K + 1),
        metavar=f"1-{MAX_TOP_K}",
        help="Number of GeoCLIP location candidates to return",
    )
    parser.add_argument(
        "--skip-geoclip",
        action="store_true",
        help="Run validation, hashing, and EXIF extraction without GeoCLIP",
    )
    parser.add_argument(
        "--skip-ocr",
        action="store_true",
        help="Skip local Apple Vision text and Indian-script recognition",
    )
    parser.add_argument(
        "--consensus-radius-km",
        type=float,
        default=DEFAULT_CLUSTER_RADIUS_KM,
        help="Maximum distance between candidates considered to agree",
    )
    arguments = parser.parse_args()

    result = analyze_image(
        arguments.image_path,
        include_geolocation=not arguments.skip_geoclip,
        include_ocr=not arguments.skip_ocr,
        top_k=arguments.top_k,
        consensus_radius_km=arguments.consensus_radius_km,
    )

    print(json.dumps(result, indent=4))
