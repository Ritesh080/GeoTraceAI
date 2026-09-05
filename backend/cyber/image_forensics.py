"""
Phase 3 — Image Forensic Indicators

Pixel-level forensic analysis using Pillow and OpenCV.
Produces numeric measurements and string indicators that feed
into the same forensics.indicators list from Phase 2.

Analyses performed:
  1. Image structure    — dimensions, resolution, aspect ratio
  2. ELA               — Error Level Analysis (JPEG re-compression diff)
  3. Noise analysis     — block-wise noise consistency
  4. Channel statistics — per-channel mean/std, detect anomalies
  5. JPEG quality       — estimate quantization quality

Design principle: every output is an indicator, never a verdict.
"""

import io
import math
import tempfile
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image


# ── 1. Image structure ──────────────────────────────────────────

def _analyze_structure(img: Image.Image) -> dict:
    """Basic image properties that may be forensically relevant."""
    width, height = img.size
    megapixels = round((width * height) / 1_000_000, 2)
    aspect = round(width / height, 3) if height > 0 else 0

    return {
        "width": width,
        "height": height,
        "megapixels": megapixels,
        "aspect_ratio": aspect,
        "mode": img.mode,
    }


def _structure_indicators(structure: dict) -> list[str]:
    """Flag unusual image structure."""
    indicators = []

    # Very small images are often crops, thumbnails, or synthetic
    if structure["megapixels"] < 0.1:
        indicators.append("very_low_resolution")

    # Non-standard mode (L = grayscale, P = palette, RGBA = transparency)
    if structure["mode"] not in ("RGB", "RGBA"):
        indicators.append(f"unusual_color_mode:{structure['mode']}")

    return indicators


# ── 2. Error Level Analysis (ELA) ────────────────────────────────

def _compute_ela(img: Image.Image, quality: int = 90) -> dict:
    """Re-save as JPEG at known quality, compute pixel difference.

    Regions edited after the last JPEG save will show higher error
    levels than the rest of the image. We return summary statistics;
    the raw ELA map is not stored.
    """
    # Convert to RGB if needed (JPEG doesn't support alpha)
    rgb = img.convert("RGB")

    # Re-compress to memory buffer
    buffer = io.BytesIO()
    rgb.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    resaved = Image.open(buffer)

    # Compute absolute difference
    original_arr = np.array(rgb, dtype=np.float64)
    resaved_arr = np.array(resaved, dtype=np.float64)
    diff = np.abs(original_arr - resaved_arr)

    # Scale to 0-255 for interpretability
    scale_factor = 255.0 / (quality if quality > 0 else 1)
    ela_map = np.clip(diff * scale_factor, 0, 255)

    mean_err = float(np.mean(ela_map))
    max_err = float(np.max(ela_map))
    std_err = float(np.std(ela_map))

    return {
        "ela_mean": round(mean_err, 2),
        "ela_max": round(max_err, 2),
        "ela_std": round(std_err, 2),
        "ela_quality_used": quality,
    }


def _ela_indicators(ela: dict) -> list[str]:
    """Flag ELA anomalies."""
    indicators = []

    # Very high standard deviation suggests uneven compression — some
    # regions were saved at a different quality than others
    if ela["ela_std"] > 60:
        indicators.append("ela_high_variance")

    # Very high max with low mean suggests a localized hotspot
    if ela["ela_max"] > 200 and ela["ela_mean"] < 30:
        indicators.append("ela_localized_hotspot")

    return indicators


# ── 3. Noise consistency analysis ────────────────────────────────

def _analyze_noise(img: Image.Image, block_size: int = 64) -> dict:
    """Split image into blocks, measure noise level per block.

    Tampered regions often have a different noise profile than the
    surrounding area. We measure the coefficient of variation of
    block-wise noise levels.
    """
    gray = np.array(img.convert("L"), dtype=np.float64)
    h, w = gray.shape

    if h < block_size or w < block_size:
        return {"noise_cv": 0.0, "block_count": 0}

    block_noises = []
    for y in range(0, h - block_size + 1, block_size):
        for x in range(0, w - block_size + 1, block_size):
            block = gray[y:y + block_size, x:x + block_size]
            # Noise estimated as std dev of Laplacian (edge-free noise)
            laplacian = cv2.Laplacian(block, cv2.CV_64F)
            block_noises.append(float(np.std(laplacian)))

    if not block_noises:
        return {"noise_cv": 0.0, "block_count": 0}

    noise_arr = np.array(block_noises)
    mean_noise = float(np.mean(noise_arr))
    std_noise = float(np.std(noise_arr))

    # Coefficient of variation: how inconsistent is the noise?
    cv = round(std_noise / mean_noise, 4) if mean_noise > 0 else 0.0

    return {
        "noise_mean": round(mean_noise, 2),
        "noise_std": round(std_noise, 2),
        "noise_cv": cv,
        "block_count": len(block_noises),
    }


def _noise_indicators(noise: dict) -> list[str]:
    """Flag noise inconsistencies."""
    indicators = []

    # High coefficient of variation means some blocks are much noisier
    # than others — possible splice or clone-stamp
    if noise["noise_cv"] > 0.7:
        indicators.append("noise_inconsistency_high")
    elif noise["noise_cv"] > 0.5:
        indicators.append("noise_inconsistency_moderate")

    return indicators


# ── 4. Channel statistics ────────────────────────────────────────

def _analyze_channels(img: Image.Image) -> dict:
    """Per-channel mean and standard deviation."""
    rgb = np.array(img.convert("RGB"), dtype=np.float64)

    stats = {}
    for i, name in enumerate(["red", "green", "blue"]):
        channel = rgb[:, :, i]
        stats[name] = {
            "mean": round(float(np.mean(channel)), 2),
            "std": round(float(np.std(channel)), 2),
        }

    return stats


def _channel_indicators(channels: dict) -> list[str]:
    """Flag channel anomalies."""
    indicators = []

    # Near-zero std in any channel means it's essentially flat — possible
    # synthetic fill or solid overlay
    for name, s in channels.items():
        if s["std"] < 1.0:
            indicators.append(f"flat_channel:{name}")

    return indicators


# ── 5. JPEG quality estimation ───────────────────────────────────

def _estimate_jpeg_quality(file_path: str) -> Optional[int]:
    """Attempt to read the JPEG quantization table quality.

    Returns estimated quality (1-100) or None for non-JPEG / unreadable.
    """
    try:
        with Image.open(file_path) as img:
            qtables = img.quantization
            if not qtables:
                return None
            # Standard JPEG quality estimation from luminance table
            # Average the quantization values; lower average = higher quality
            table = list(qtables[0])  # Luminance table
            avg_q = sum(table) / len(table)
            # Rough mapping: avg_q ~1 = quality 100, avg_q ~50 = quality 50
            estimated = max(1, min(100, int(100 - (avg_q - 1) * 1.5)))
            return estimated
    except Exception:
        return None


# ── Public API ───────────────────────────────────────────────────

def analyze_image_forensics(file_path: str) -> dict:
    """Main entry point for Phase 3.

    Parameters
    ----------
    file_path : str
        Path to the image file (already validated by Phase 1).

    Returns
    -------
    dict
        {
            "image_forensics": { structure, ela, noise, channels, jpeg_quality },
            "indicators": [ ... ]
        }
    """
    try:
        img = Image.open(file_path)
    except Exception as e:
        return {
            "image_forensics": {},
            "indicators": [f"image_open_failed:{e}"],
        }

    # Run all analyses
    structure = _analyze_structure(img)
    ela = _compute_ela(img)
    noise = _analyze_noise(img)
    channels = _analyze_channels(img)
    jpeg_quality = _estimate_jpeg_quality(file_path)

    # Collect all indicators
    indicators = []
    indicators.extend(_structure_indicators(structure))
    indicators.extend(_ela_indicators(ela))
    indicators.extend(_noise_indicators(noise))
    indicators.extend(_channel_indicators(channels))

    return {
        "image_forensics": {
            "structure": structure,
            "ela": ela,
            "noise": noise,
            "channels": channels,
            "jpeg_quality": jpeg_quality,
        },
        "indicators": indicators,
    }
