import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "cyber"))

from evidence_fusion import fuse_evidence


def cyber(score=0.9, suspected=False):
    return {"forensics": {"reliability_score": score, "reliability_level": "high", "tampering_suspected": suspected}}


def candidate(confidence=0.8, calibrated=True, contradictions=None):
    return {
        "id": "candidate-1",
        "rank": 1,
        "label": "Example City",
        "confidence": confidence,
        "calibrated": calibrated,
        "source_group": "visual_model:abc",
        "supports": [
            {"source_group": "visual_model:abc"},
            {"source_group": "map_index:xyz"},
        ],
        "contradictions": contradictions or [],
    }


class EvidenceFusionTests(unittest.TestCase):
    def test_keeps_forensic_and_location_scores_separate(self):
        result = fuse_evidence(cyber(score=0.93), {"candidates": [candidate(confidence=0.72)], "conflicts": []})
        record = result["location_assessment"]["candidates"][0]
        self.assertEqual(record["forensic_reliability"], 0.93)
        self.assertEqual(record["location_confidence"], 0.72)
        self.assertTrue(record["eligible_for_location_conclusion"])

    def test_does_not_treat_clean_file_as_location_proof(self):
        result = fuse_evidence(cyber(score=1.0), {"candidates": [candidate(confidence=None, calibrated=False)], "conflicts": []})
        record = result["location_assessment"]["candidates"][0]
        self.assertIsNone(record["location_confidence"])
        self.assertIn("location_confidence_is_not_calibrated", record["blockers"])
        self.assertEqual(result["decision"], "location_candidate_needs_more_evidence")

    def test_low_forensic_reliability_forces_abstention(self):
        result = fuse_evidence(cyber(score=0.4, suspected=True), {"candidates": [candidate()], "conflicts": []})
        self.assertEqual(result["decision"], "abstain_asset_integrity_concern")
        self.assertFalse(result["location_assessment"]["candidates"][0]["eligible_for_location_conclusion"])

    def test_conflicting_location_evidence_forces_abstention(self):
        result = fuse_evidence(cyber(), {"candidates": [candidate()], "conflicts": [{"id": "conflict-1"}]})
        self.assertEqual(result["decision"], "abstain_conflicting_location_evidence")

    def test_dependent_submitted_asset_clues_are_not_independent_sources(self):
        item = candidate()
        item["source_group"] = "submitted_asset"
        item["supports"] = [{"source_group": "submitted_asset"}, {"source_group": "instagram:abc"}]
        result = fuse_evidence(cyber(), {"candidates": [item], "conflicts": []})
        record = result["location_assessment"]["candidates"][0]
        self.assertEqual(record["independent_location_source_groups"], [])
        self.assertIn("insufficient_independent_location_sources", record["blockers"])


if __name__ == "__main__":
    unittest.main()
