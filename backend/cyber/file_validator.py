import magic
from pathlib import Path


ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp"
}


def validate_image(file_path: str) -> dict:

    path = Path(file_path)

    if not path.exists():
        return {
            "valid": False,
            "reason": "File does not exist"
        }

    mime_type = magic.from_file(str(path), mime=True)

    return {
        "valid": mime_type in ALLOWED_MIME_TYPES,
        "mime_type": mime_type,
        "extension": path.suffix.lower()
    }
