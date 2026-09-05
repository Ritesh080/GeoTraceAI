import json
import sys

from hash_service import calculate_sha256
from file_validator import validate_image
from exif_service import extract_exif
from metadata_analyzer import analyze_metadata
from image_forensics import analyze_image_forensics
from reliability_engine import compute_reliability


def analyze_image(file_path: str) -> dict:

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
    }


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print("Usage: python main.py <image_path>")
        sys.exit(1)

    result = analyze_image(sys.argv[1])

    print(json.dumps(result, indent=4))