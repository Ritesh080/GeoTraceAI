"""Local visual clues for GeoTrace without commercial provider APIs."""

from __future__ import annotations

import json
import statistics
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat


OCR_SCRIPT = Path(__file__).with_name("vision_ocr.swift")
OCR_BINARY = Path(tempfile.gettempdir()) / "geotrace-vision-ocr"
_OCR_BUILD_LOCK = threading.Lock()
INDIAN_SCRIPT_RANGES = {
    "Devanagari": (0x0900, 0x097F),
    "Bengali-Assamese": (0x0980, 0x09FF),
    "Gurmukhi": (0x0A00, 0x0A7F),
    "Gujarati": (0x0A80, 0x0AFF),
    "Odia": (0x0B00, 0x0B7F),
    "Tamil": (0x0B80, 0x0BFF),
    "Telugu": (0x0C00, 0x0C7F),
    "Kannada": (0x0C80, 0x0CFF),
    "Malayalam": (0x0D00, 0x0D7F),
}


def detect_indian_scripts(text: str) -> list[dict[str, Any]]:
    counts = {}
    for name, (start, end) in INDIAN_SCRIPT_RANGES.items():
        count = sum(start <= ord(character) <= end for character in text)
        if count:
            counts[name] = count
    return [
        {"script": name, "character_count": count}
        for name, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
    ]


def _average_hash(image: Image.Image, size: int = 8) -> str:
    grayscale = image.convert("L").resize((size, size))
    pixels = list(grayscale.getdata())
    average = statistics.fmean(pixels)
    bits = "".join("1" if pixel >= average else "0" for pixel in pixels)
    return f"{int(bits, 2):0{size * size // 4}x}"


def _image_characteristics(image: Image.Image) -> dict:
    rgb = image.convert("RGB")
    reduced = rgb.copy()
    reduced.thumbnail((512, 512))
    stat = ImageStat.Stat(reduced)
    brightness = sum(stat.mean) / 3
    contrast = sum(stat.stddev) / 3
    edges = reduced.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_density = ImageStat.Stat(edges).mean[0] / 255
    width, height = image.size
    return {
        "width": width,
        "height": height,
        "aspect_ratio": round(width / height, 4) if height else None,
        "brightness": round(brightness / 255, 4),
        "contrast": round(contrast / 255, 4),
        "edge_density": round(edge_density, 4),
        "average_rgb": [round(value, 2) for value in stat.mean],
        "perceptual_average_hash": _average_hash(reduced),
    }


def _ocr_binary() -> Path:
    with _OCR_BUILD_LOCK:
        if OCR_BINARY.is_file() and OCR_BINARY.stat().st_mtime >= OCR_SCRIPT.stat().st_mtime:
            return OCR_BINARY
        subprocess.run(
            ["/usr/bin/swiftc", str(OCR_SCRIPT), "-o", str(OCR_BINARY)],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        return OCR_BINARY


def _recognize_text(file_path: str, timeout: int = 45) -> dict:
    if not OCR_SCRIPT.is_file():
        return {"status": "unavailable", "reason": "Local OCR script is missing", "lines": []}
    try:
        completed = subprocess.run(
            [str(_ocr_binary()), file_path],
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
        lines = json.loads(completed.stdout)
    except FileNotFoundError:
        return {"status": "unavailable", "reason": "Apple Swift runtime is unavailable", "lines": []}
    except subprocess.TimeoutExpired:
        return {"status": "error", "reason": "Local OCR timed out", "lines": []}
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        return {"status": "error", "reason": detail.strip()[:300], "lines": []}

    visible_lines = [line for line in lines if line.get("text", "").strip()]
    combined_text = "\n".join(line["text"].strip() for line in visible_lines)
    return {
        "status": "success",
        "engine": "Apple Vision on-device OCR",
        "lines": visible_lines,
        "combined_text": combined_text,
        "indian_scripts": detect_indian_scripts(combined_text),
        "interpretation_note": (
            "Recognized text and script are investigative clues, not proof of location."
        ),
    }


def extract_local_clues(file_path: str, *, include_ocr: bool = True) -> dict:
    """Extract reproducible image characteristics and on-device text clues."""

    try:
        with Image.open(file_path) as image:
            characteristics = _image_characteristics(image)
    except (OSError, ValueError) as exc:
        return {
            "status": "error",
            "engine": "GeoTrace Local Clues",
            "reason": f"Image clue extraction failed: {exc}",
        }

    return {
        "status": "success",
        "engine": "GeoTrace Local Clues",
        "processing": "on_device",
        "image_characteristics": characteristics,
        "ocr": (
            _recognize_text(file_path)
            if include_ocr
            else {"status": "skipped", "reason": "OCR disabled", "lines": []}
        ),
    }
