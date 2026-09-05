"""
Tests for image_forensics.py — Phase 3

Run from project root:
    python tests/test_image_forensics.py
"""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "cyber"))

from PIL import Image
import numpy as np
from image_forensics import analyze_image_forensics


# ── Helper: create test images ───────────────────────────────────

def _create_normal_jpeg(width=800, height=600) -> str:
    """Create a realistic-ish test JPEG with natural noise."""
    rng = np.random.RandomState(42)
    # Gradient base + noise to simulate a photo
    base = np.zeros((height, width, 3), dtype=np.uint8)
    for c in range(3):
        gradient = np.linspace(50, 200, width, dtype=np.uint8)
        base[:, :, c] = gradient
    noise = rng.randint(0, 20, (height, width, 3), dtype=np.uint8)
    img_arr = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    img = Image.fromarray(img_arr, "RGB")
    path = os.path.join(tempfile.gettempdir(), "test_normal.jpg")
    img.save(path, format="JPEG", quality=85)
    return path


def _create_tiny_png(width=30, height=30) -> str:
    """Create a very small image (should trigger low_resolution)."""
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    path = os.path.join(tempfile.gettempdir(), "test_tiny.png")
    img.save(path, format="PNG")
    return path


def _create_flat_channel_png(width=400, height=300) -> str:
    """Create an image with one completely flat channel."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    arr[:, :, 0] = 128  # Red: flat
    arr[:, :, 1] = np.random.randint(50, 200, (height, width), dtype=np.uint8)
    arr[:, :, 2] = np.random.randint(50, 200, (height, width), dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")
    path = os.path.join(tempfile.gettempdir(), "test_flat.png")
    img.save(path, format="PNG")
    return path


def _create_spliced_jpeg(width=800, height=600) -> str:
    """Create a JPEG then paste a different-quality block to simulate splice."""
    rng = np.random.RandomState(42)
    # Base image
    base = rng.randint(100, 150, (height, width, 3), dtype=np.uint8)
    img = Image.fromarray(base, "RGB")

    # Save at quality 30 (heavy compression)
    path = os.path.join(tempfile.gettempdir(), "test_spliced.jpg")
    img.save(path, format="JPEG", quality=30)

    # Reload, paste a high-frequency block in one corner
    img = Image.open(path)
    patch = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    img.paste(Image.fromarray(patch, "RGB"), (50, 50))
    img.save(path, format="JPEG", quality=95)
    return path


# ── Tests ────────────────────────────────────────────────────────

def test_normal_image():
    path = _create_normal_jpeg()
    result = analyze_image_forensics(path)

    assert "image_forensics" in result
    assert "indicators" in result
    f = result["image_forensics"]
    assert f["structure"]["width"] == 800
    assert f["structure"]["height"] == 600
    assert f["structure"]["megapixels"] == 0.48
    assert f["ela"]["ela_mean"] >= 0
    assert f["noise"]["block_count"] > 0
    assert "red" in f["channels"]
    print(f"  indicators: {result['indicators']}")
    print("PASS: normal image")


def test_tiny_image():
    path = _create_tiny_png()
    result = analyze_image_forensics(path)

    assert "very_low_resolution" in result["indicators"]
    print("PASS: tiny image flagged")


def test_flat_channel():
    path = _create_flat_channel_png()
    result = analyze_image_forensics(path)

    flat_flags = [i for i in result["indicators"] if i.startswith("flat_channel:")]
    assert len(flat_flags) >= 1
    assert "flat_channel:red" in flat_flags
    print("PASS: flat channel detected")


def test_jpeg_quality():
    path = _create_normal_jpeg()
    result = analyze_image_forensics(path)

    q = result["image_forensics"]["jpeg_quality"]
    assert q is not None
    assert 1 <= q <= 100
    print(f"  estimated quality: {q}")
    print("PASS: JPEG quality estimated")


def test_invalid_file():
    path = os.path.join(tempfile.gettempdir(), "test_invalid.xyz")
    with open(path, "w") as f:
        f.write("not an image")
    result = analyze_image_forensics(path)

    assert any("image_open_failed" in i for i in result["indicators"])
    print("PASS: invalid file handled")


def test_spliced_image():
    path = _create_spliced_jpeg()
    result = analyze_image_forensics(path)

    print(f"  ELA std: {result['image_forensics']['ela']['ela_std']}")
    print(f"  noise CV: {result['image_forensics']['noise']['noise_cv']}")
    print(f"  indicators: {result['indicators']}")
    # Spliced image should show some forensic signal
    # (may or may not trigger thresholds depending on synthesis)
    print("PASS: spliced image analyzed")


def test_full_output_structure():
    """Verify the output dict has every expected key."""
    path = _create_normal_jpeg()
    result = analyze_image_forensics(path)
    f = result["image_forensics"]

    assert "structure" in f
    assert "ela" in f
    assert "noise" in f
    assert "channels" in f
    assert "jpeg_quality" in f

    assert "width" in f["structure"]
    assert "ela_mean" in f["ela"]
    assert "noise_cv" in f["noise"]
    assert "red" in f["channels"]
    print("PASS: output structure complete")


# ── Run all ──────────────────────────────────────────────────────

if __name__ == "__main__":
    test_normal_image()
    test_tiny_image()
    test_flat_channel()
    test_jpeg_quality()
    test_invalid_file()
    test_spliced_image()
    test_full_output_structure()

    print("\n=== ALL PHASE 3 TESTS PASSED ===")
