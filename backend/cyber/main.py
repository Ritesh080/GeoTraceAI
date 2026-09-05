import json
import sys

from hash_service import calculate_sha256
from file_validator import validate_image
from exif_service import extract_exif


def analyze_image(file_path: str) -> dict:

    file_info = validate_image(file_path)

    if not file_info["valid"]:
        return {
            "status": "rejected",
            "file": file_info
        }

    sha256 = calculate_sha256(file_path)

    metadata = extract_exif(file_path)

    return {
        "status": "success",

        "sha256": sha256,

        "file": file_info,

        "metadata": metadata
    }


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print("Usage: python main.py <image_path>")
        sys.exit(1)

    result = analyze_image(sys.argv[1])

    print(json.dumps(result, indent=4))