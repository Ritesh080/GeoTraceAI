"""
Tests for reliability_engine.py — Phase 4

Run from project root:
    python tests/test_reliability_engine.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "cyber"))

from reliability_engine import compute_reliability


# ── 1. Clean image — no indicators ───────────────────────────────

def test_clean_image():
    result = compute_reliability(indicators=[])

    assert result["reliability_score"] == 1.0
    assert result["reliability_level"] == "high"
    assert result["tampering_suspected"] is False
    assert result["total_penalty"] == 0.0
    assert len(result["scored_indicators"]) == 0
    print("PASS: clean image — score 1.0, high reliability")


# ── 2. Software only — barely penalized ──────────────────────────

def test_software_only():
    result = compute_reliability(
        indicators=["software_detected:Adobe Photoshop 25.0"]
    )

    assert result["reliability_score"] >= 0.95
    assert result["reliability_level"] == "high"
    assert result["tampering_suspected"] is False
    print(f"  score: {result['reliability_score']}")
    print("PASS: software detected — minimal penalty, still high")


# ── 3. Missing metadata — moderate penalty ───────────────────────

def test_missing_metadata():
    result = compute_reliability(
        indicators=["missing_datetime_original", "missing_camera_info"]
    )

    expected_penalty = 0.08 + 0.08  # 0.16
    assert abs(result["total_penalty"] - expected_penalty) < 0.001
    assert result["reliability_score"] == round(1.0 - expected_penalty, 4)
    assert result["reliability_level"] == "high"
    print(f"  score: {result['reliability_score']}, penalty: {result['total_penalty']}")
    print("PASS: missing metadata — moderate penalty")


# ── 4. Timestamp inconsistency + software ────────────────────────

def test_timestamp_plus_software():
    result = compute_reliability(
        indicators=[
            "modify_date_before_original",
            "original_create_date_mismatch",
            "software_detected:GIMP 2.10",
        ]
    )

    expected_penalty = 0.15 + 0.10 + 0.03  # 0.28
    assert abs(result["total_penalty"] - expected_penalty) < 0.001
    assert result["reliability_level"] == "medium"
    assert result["tampering_suspected"] is False
    print(f"  score: {result['reliability_score']}, level: {result['reliability_level']}")
    print("PASS: timestamp issues + software — medium reliability")


# ── 5. Heavy tampering indicators — low score ────────────────────

def test_heavy_tampering():
    result = compute_reliability(
        indicators=[
            "gps_null_island",
            "ela_high_variance",
            "noise_inconsistency_high",
            "ela_localized_hotspot",
            "missing_camera_info",
        ]
    )

    assert result["reliability_score"] < 0.55
    assert result["tampering_suspected"] is True
    assert result["reliability_level"] in ("low", "very_low")
    print(f"  score: {result['reliability_score']}, level: {result['reliability_level']}")
    print("PASS: heavy tampering — low score, tampering suspected")


# ── 6. Metadata extraction failed — severe ───────────────────────

def test_extraction_failed():
    result = compute_reliability(
        indicators=["metadata_extraction_failed"]
    )

    assert result["reliability_score"] == 0.75
    assert result["reliability_level"] == "medium"
    print(f"  score: {result['reliability_score']}")
    print("PASS: extraction failed — 0.25 penalty applied")


# ── 7. Continuous adjustments — ELA elevated ─────────────────────

def test_continuous_ela_elevated():
    forensics = {
        "ela": {"ela_mean": 20, "ela_max": 80, "ela_std": 50},
        "noise": {"noise_cv": 0.1},
    }
    result = compute_reliability(
        indicators=[],
        image_forensics=forensics,
    )

    assert len(result["continuous_adjustments"]) == 1
    assert result["continuous_adjustments"][0]["source"] == "ela_std_elevated"
    assert result["reliability_score"] < 1.0
    print(f"  score: {result['reliability_score']}, adjustments: {result['continuous_adjustments']}")
    print("PASS: continuous ELA adjustment applied")


# ── 8. Continuous adjustments — noise elevated ───────────────────

def test_continuous_noise_elevated():
    forensics = {
        "ela": {"ela_mean": 10, "ela_max": 50, "ela_std": 15},
        "noise": {"noise_cv": 0.42},
    }
    result = compute_reliability(
        indicators=[],
        image_forensics=forensics,
    )

    assert len(result["continuous_adjustments"]) == 1
    assert result["continuous_adjustments"][0]["source"] == "noise_cv_elevated"
    print(f"  score: {result['reliability_score']}")
    print("PASS: continuous noise adjustment applied")


# ── 9. No continuous adjustments on clean metrics ────────────────

def test_no_continuous_on_clean():
    forensics = {
        "ela": {"ela_mean": 10, "ela_max": 40, "ela_std": 8},
        "noise": {"noise_cv": 0.15},
    }
    result = compute_reliability(
        indicators=[],
        image_forensics=forensics,
    )

    assert len(result["continuous_adjustments"]) == 0
    assert result["reliability_score"] == 1.0
    print("PASS: no continuous adjustments on clean metrics")


# ── 10. Score never goes below 0.0 ───────────────────────────────

def test_score_floor():
    # Stack every possible indicator
    result = compute_reliability(
        indicators=[
            "metadata_extraction_failed",
            "gps_null_island",
            "ela_high_variance",
            "ela_localized_hotspot",
            "noise_inconsistency_high",
            "missing_datetime_original",
            "missing_camera_info",
            "modify_date_before_original",
            "original_create_date_mismatch",
            "unusual_gps_altitude",
            "very_low_resolution",
            "flat_channel:red",
            "flat_channel:green",
            "flat_channel:blue",
            "software_detected:Photoshop",
        ]
    )

    assert result["reliability_score"] >= 0.0
    assert result["reliability_level"] == "very_low"
    assert result["tampering_suspected"] is True
    print(f"  score: {result['reliability_score']}, penalty: {result['total_penalty']}")
    print("PASS: score floor at 0.0")


# ── 11. Unknown indicator gets small default penalty ─────────────

def test_unknown_indicator():
    result = compute_reliability(
        indicators=["some_future_indicator_not_yet_defined"]
    )

    assert result["total_penalty"] == 0.02
    assert result["scored_indicators"][0]["penalty"] == 0.02
    print("PASS: unknown indicator — default 0.02 penalty")


# ── 12. Custom tampering threshold ───────────────────────────────

def test_custom_threshold():
    indicators = ["modify_date_before_original"]  # penalty 0.15 → score 0.85

    # Default threshold 0.55 — not suspicious
    result_default = compute_reliability(indicators=indicators)
    assert result_default["tampering_suspected"] is False

    # Strict threshold 0.90 — now suspicious
    result_strict = compute_reliability(
        indicators=indicators, tampering_threshold=0.90
    )
    assert result_strict["tampering_suspected"] is True
    print("PASS: custom tampering threshold works")


# ── Run all ──────────────────────────────────────────────────────

if __name__ == "__main__":
    test_clean_image()
    test_software_only()
    test_missing_metadata()
    test_timestamp_plus_software()
    test_heavy_tampering()
    test_extraction_failed()
    test_continuous_ela_elevated()
    test_continuous_noise_elevated()
    test_no_continuous_on_clean()
    test_score_floor()
    test_unknown_indicator()
    test_custom_threshold()

    print("\n=== ALL PHASE 4 TESTS PASSED ===")
