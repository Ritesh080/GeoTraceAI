"""
Phase 4 — Forensic Reliability Engine

Takes the merged indicator list from Phase 2 (metadata) and Phase 3
(image forensics), plus the image_forensics measurements, and produces:

  1. reliability_score  (0.0–1.0)
  2. reliability_level  (high / medium / low / very_low)
  3. tampering_suspected (bool — crosses threshold, still not proof)
  4. scored_indicators   (each indicator with its penalty weight)

Scoring approach:
  - Start at 1.0 (fully trustworthy).
  - Each indicator subtracts a weighted penalty.
  - Continuous metrics (ELA std, noise CV) apply graded penalties.
  - Final score clamped to [0.0, 1.0].

Design principle: the score is a trust estimate, not a verdict.
Downstream fusion uses it to weight cyber evidence against AI evidence.
"""

from typing import Optional


# ── Indicator penalty weights ────────────────────────────────────
#
# Higher penalty = more impact on reliability.
# Weights are intentionally conservative — we flag, we don't accuse.

INDICATOR_PENALTIES = {
    # Phase 2 — metadata indicators
    "modify_date_before_original":     0.15,
    "original_create_date_mismatch":   0.10,
    "missing_datetime_original":       0.08,
    "missing_camera_info":             0.08,
    "gps_null_island":                 0.20,
    "unusual_gps_altitude":            0.10,
    "metadata_extraction_failed":      0.25,

    # Phase 3 — image indicators
    "very_low_resolution":             0.10,
    "ela_high_variance":               0.15,
    "ela_localized_hotspot":           0.20,
    "noise_inconsistency_high":        0.20,
    "noise_inconsistency_moderate":    0.10,
}

# Prefix-matched indicators (e.g. "software_detected:Adobe Photoshop")
PREFIX_PENALTIES = {
    "software_detected:":              0.03,  # noted, barely penalized
    "flat_channel:":                   0.12,
    "unusual_color_mode:":             0.05,
    "image_open_failed:":              0.30,
}


def _get_penalty(indicator: str) -> float:
    """Look up the penalty for an indicator by exact match or prefix."""
    if indicator in INDICATOR_PENALTIES:
        return INDICATOR_PENALTIES[indicator]

    for prefix, penalty in PREFIX_PENALTIES.items():
        if indicator.startswith(prefix):
            return penalty

    # Unknown indicator — small default penalty so nothing is invisible
    return 0.02


# ── Continuous metric adjustments ────────────────────────────────

def _continuous_adjustments(image_forensics: Optional[dict]) -> list[dict]:
    """Apply graded penalties based on continuous measurements.

    These supplement the binary indicators. For example, an ELA std of 45
    didn't trigger the >60 threshold in Phase 3, but is still elevated
    and should nudge the score down slightly.

    Returns a list of adjustment dicts for transparency.
    """
    adjustments = []

    if not image_forensics:
        return adjustments

    # ELA standard deviation — graded scale
    ela = image_forensics.get("ela", {})
    ela_std = ela.get("ela_std", 0)
    if 40 < ela_std <= 60:
        adjustments.append({
            "source": "ela_std_elevated",
            "value": round(ela_std, 2),
            "penalty": 0.07,
        })
    elif ela_std > 60:
        # Already penalized by ela_high_variance indicator, add a small extra
        adjustments.append({
            "source": "ela_std_very_high",
            "value": round(ela_std, 2),
            "penalty": 0.05,
        })

    # Noise CV — graded scale
    noise = image_forensics.get("noise", {})
    noise_cv = noise.get("noise_cv", 0)
    if 0.35 < noise_cv <= 0.5:
        adjustments.append({
            "source": "noise_cv_elevated",
            "value": round(noise_cv, 4),
            "penalty": 0.05,
        })
    elif noise_cv > 0.7:
        # Already penalized by noise_inconsistency_high, add extra
        adjustments.append({
            "source": "noise_cv_very_high",
            "value": round(noise_cv, 4),
            "penalty": 0.05,
        })

    # ELA localized hotspot severity
    ela_max = ela.get("ela_max", 0)
    ela_mean = ela.get("ela_mean", 0)
    if ela_max > 200 and ela_mean < 30:
        ratio = ela_max / max(ela_mean, 1)
        if ratio > 15:
            adjustments.append({
                "source": "ela_hotspot_extreme_ratio",
                "value": round(ratio, 1),
                "penalty": 0.08,
            })

    return adjustments


# ── Score calculation ────────────────────────────────────────────

def _classify_level(score: float) -> str:
    """Map numeric score to a human-readable level."""
    if score >= 0.80:
        return "high"
    elif score >= 0.55:
        return "medium"
    elif score >= 0.30:
        return "low"
    else:
        return "very_low"


# ── Public API ───────────────────────────────────────────────────

def compute_reliability(
    indicators: list[str],
    image_forensics: Optional[dict] = None,
    tampering_threshold: float = 0.55,
) -> dict:
    """Main entry point for Phase 4.

    Parameters
    ----------
    indicators : list[str]
        Merged indicator list from Phase 2 + Phase 3.
    image_forensics : dict, optional
        The image_forensics measurements from Phase 3 (for continuous scoring).
    tampering_threshold : float
        Score below this triggers tampering_suspected = True. Default 0.55.

    Returns
    -------
    dict
        {
            "reliability_score": 0.72,
            "reliability_level": "medium",
            "tampering_suspected": false,
            "scored_indicators": [...],
            "continuous_adjustments": [...],
            "total_penalty": 0.28
        }
    """
    scored = []
    total_penalty = 0.0

    # Score each indicator
    for indicator in indicators:
        penalty = _get_penalty(indicator)
        scored.append({
            "indicator": indicator,
            "penalty": penalty,
        })
        total_penalty += penalty

    # Apply continuous adjustments
    adjustments = _continuous_adjustments(image_forensics)
    for adj in adjustments:
        total_penalty += adj["penalty"]

    total_penalty = round(total_penalty, 4)
    score = round(max(0.0, min(1.0, 1.0 - total_penalty)), 4)
    level = _classify_level(score)
    tampering = score < tampering_threshold

    return {
        "reliability_score": score,
        "reliability_level": level,
        "tampering_suspected": tampering,
        "scored_indicators": scored,
        "continuous_adjustments": adjustments,
        "total_penalty": total_penalty,
    }
