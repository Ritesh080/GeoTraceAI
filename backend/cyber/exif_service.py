import subprocess
import json


def extract_exif(file_path: str) -> dict:

    try:
        result = subprocess.run(
            ["exiftool", "-json", file_path],
            capture_output=True,
            text=True,
            check=True
        )

        data = json.loads(result.stdout)

        if not data:
            return {}

        return data[0]

    except Exception as e:
        return {
            "error": str(e)
        }