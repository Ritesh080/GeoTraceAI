import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "cyber"))

from conflict_detection import analyze_conflicts


def candidate(identifier, label, latitude, longitude, source_group):
    return {
        "id": identifier,
        "label": label,
        "latitude": latitude,
        "longitude": longitude,
        "source_group": source_group,
        "supports": [],
        "contradictions": [],
    }


class ConflictDetectionTests(unittest.TestCase):
    def test_detects_and_explains_distant_coordinate_disagreement(self):
        osint = {"candidates": [
            candidate("embedded_gps", "Delhi", 28.6139, 77.2090, "submitted_asset"),
            candidate("visual", "Paris", 48.8566, 2.3522, "visual_model:abc"),
        ], "conflicts": [], "uncertainty": {"abstention_reasons": []}}
        result = analyze_conflicts({"forensics": {"reliability_score": 0.9}}, osint)
        conflict = result["conflicts"][0]
        self.assertEqual(conflict["type"], "coordinate_disagreement")
        self.assertEqual(conflict["severity"], "critical")
        self.assertTrue(conflict["forces_abstention"])
        self.assertGreater(conflict["distance_km"], 1000)
        self.assertEqual(result["uncertainty"]["outcome"], "conflicting_evidence")

    def test_nearby_coordinates_are_not_conflicting(self):
        osint = {"candidates": [
            candidate("one", "Delhi", 28.6139, 77.2090, "one"),
            candidate("two", "New Delhi", 28.6200, 77.2100, "two"),
        ], "conflicts": [], "uncertainty": {"abstention_reasons": []}}
        result = analyze_conflicts({"forensics": {"reliability_score": 0.9}}, osint)
        self.assertEqual(result["conflicts"], [])

    def test_low_street_similarity_is_not_a_contradiction(self):
        osint = {
            "candidates": [candidate("one", "Delhi", 28.6139, 77.2090, "one")],
            "conflicts": [],
            "uncertainty": {"abstention_reasons": []},
            "street_imagery_comparison": {"records": [{"candidate_id": "one", "status": "street_imagery_not_supportive"}]},
        }
        result = analyze_conflicts({"forensics": {"reliability_score": 0.9}}, osint)
        self.assertEqual(result["conflicts"], [])

    def test_unreliable_asset_marks_embedded_gps_as_conflicted(self):
        osint = {"candidates": [
            candidate("embedded_gps", "28.6, 77.2", 28.6, 77.2, "submitted_asset")
        ], "conflicts": [], "uncertainty": {"abstention_reasons": []}}
        result = analyze_conflicts({"forensics": {"reliability_score": 0.3, "tampering_suspected": True}}, osint)
        self.assertEqual(result["conflicts"][0]["type"], "asset_integrity_vs_embedded_location")
        self.assertEqual(result["conflicts"][0]["severity"], "high")


if __name__ == "__main__":
    unittest.main()
