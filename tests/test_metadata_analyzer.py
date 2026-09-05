"""
Tests for metadata_analyzer.py — Phase 2

Run from project root:
    python -m pytest tests/test_metadata_analyzer.py -v

Or standalone:
    python tests/test_metadata_analyzer.py
"""

import sys
import os
import json

# Allow imports from backend/cyber/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "cyber"))

from metadata_analyzer import analyze_metadata, _parse_gps_coordinate


# ── GPS parsing ──────────────────────────────────────────────────

def test_gps_decimal():
    assert _parse_gps_coordinate(28.6139) == 28.6139

def test_gps_string_decimal():
    assert _parse_gps_coordinate("77.209") == 77.209

def test_gps_dms_string():
    result = _parse_gps_coordinate("28 deg 36' 50.04\" N")
    assert result is not None
    assert abs(result - 28.6139) < 0.001

def test_gps_none():
    assert _parse_gps_coordinate(None) is None

def test_gps_empty():
    assert _parse_gps_coordinate("") is None


# ── Full analysis: rich EXIF ─────────────────────────────────────

def test_full_metadata():
    raw = {
        "GPSLatitude": 28.6139,
        "GPSLongitude": 77.209,
        "Make": "Canon",
        "Model": "EOS R5",
        "DateTimeOriginal": "2024:06:15 10:30:00",
        "CreateDate": "2024:06:15 10:30:00",
        "ModifyDate": "2024:06:15 10:30:00",
    }
    result = analyze_metadata(raw)

    assert result["metadata"]["gps_present"] is True
    assert result["metadata"]["latitude"] == 28.6139
    assert result["metadata"]["coordinates_valid"] is True
    assert result["metadata"]["camera"] == "Canon"
    assert result["metadata"]["model"] == "EOS R5"
    assert result["forensics"]["indicator_count"] == 0
    print("PASS: full metadata")


# ── Stripped image (no EXIF at all) ──────────────────────────────

def test_empty_metadata():
    result = analyze_metadata({})
    meta = result["metadata"]
    forensics = result["forensics"]

    assert meta["gps_present"] is False
    assert meta["camera"] is None
    assert "missing_datetime_original" in forensics["indicators"]
    assert "missing_camera_info" in forensics["indicators"]
    print("PASS: empty metadata")


# ── Timestamp inconsistency ──────────────────────────────────────

def test_modify_before_original():
    raw = {
        "DateTimeOriginal": "2024:06:15 10:30:00",
        "CreateDate": "2024:06:15 10:30:00",
        "ModifyDate": "2024:01:01 00:00:00",
        "Make": "Nikon",
        "Model": "Z6",
    }
    result = analyze_metadata(raw)
    assert "modify_date_before_original" in result["forensics"]["indicators"]
    print("PASS: modify before original")


# ── Software detection ───────────────────────────────────────────

def test_software_noted():
    raw = {
        "Software": "Adobe Photoshop 25.0",
        "DateTimeOriginal": "2024:06:15 10:30:00",
        "Make": "Sony",
        "Model": "A7IV",
    }
    result = analyze_metadata(raw)
    sw_indicators = [i for i in result["forensics"]["indicators"] if i.startswith("software_detected:")]
    assert len(sw_indicators) == 1
    assert "Adobe Photoshop" in sw_indicators[0]
    print("PASS: software noted (not auto-tampered)")


# ── Null Island GPS ──────────────────────────────────────────────

def test_null_island():
    raw = {
        "GPSLatitude": 0.0,
        "GPSLongitude": 0.0,
        "DateTimeOriginal": "2024:06:15 10:30:00",
        "Make": "Apple",
        "Model": "iPhone 15",
    }
    result = analyze_metadata(raw)
    assert "gps_null_island" in result["forensics"]["indicators"]
    print("PASS: null island detected")


# ── Error / failed extraction ────────────────────────────────────

def test_error_input():
    result = analyze_metadata({"error": "exiftool not found"})
    assert "metadata_extraction_failed" in result["forensics"]["indicators"]
    print("PASS: error input handled")


# ── Run all ──────────────────────────────────────────────────────

if __name__ == "__main__":
    test_gps_decimal()
    test_gps_string_decimal()
    test_gps_dms_string()
    test_gps_none()
    test_gps_empty()
    test_full_metadata()
    test_empty_metadata()
    test_modify_before_original()
    test_software_noted()
    test_null_island()
    test_error_input()

    print("\n=== ALL PHASE 2 TESTS PASSED ===")
