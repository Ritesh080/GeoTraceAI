import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "cyber"))

from micro_osint import attach_micro_osint_workspace, build_micro_osint_ledger


def clue(**overrides):
    record = {
        "id": "road-edge-line",
        "category": "road_system",
        "source_group": "submitted_asset",
        "observation": "A solid yellow line is visible along the outer road edge.",
        "region": {"x": 0.1, "y": 0.55, "width": 0.7, "height": 0.2},
        "inference": {
            "claim": "The road convention is compatible with candidate A.",
            "relationship": "supports",
            "candidate_ids": ["candidate-a"],
            "rationale": "The cited road manual documents this convention.",
            "method_maturity": "validated",
        },
        "verification": {
            "status": "verified",
            "analyst": "analyst-17",
            "references": [{
                "id": "road-manual",
                "title": "Official road-marking manual",
                "uri": "https://example.gov/road-manual",
            }],
        },
    }
    record.update(overrides)
    return record


class MicroOsintTests(unittest.TestCase):
    def test_separates_observation_inference_and_verification(self):
        result = build_micro_osint_ledger([clue()], ["candidate-a"])
        record = result["clues"][0]
        self.assertEqual(record["observation"]["description"], clue()["observation"])
        self.assertEqual(record["inference"]["relationship"], "supports")
        self.assertEqual(record["verification"]["status"], "verified")
        self.assertTrue(record["eligible_for_candidate_filter"])

    def test_clues_from_same_asset_count_as_one_source_group(self):
        second = clue(id="pole-shape", observation="A concrete utility pole has evenly spaced rectangular openings.")
        result = build_micro_osint_ledger([clue(), second], ["candidate-a"])
        self.assertEqual(result["assessment"]["independent_source_groups"], 1)
        self.assertEqual(result["dependency_groups"][0]["independent_source_count"], 1)

    def test_exclusion_is_explicit_but_missing_clue_is_not(self):
        negative = clue(
            inference={
                "claim": "The official convention conflicts with candidate A.",
                "relationship": "excludes",
                "candidate_ids": ["candidate-a"],
                "method_maturity": "validated",
            }
        )
        result = build_micro_osint_ledger([negative], ["candidate-a", "candidate-b"])
        filters = result["candidate_filters"]["candidates"]
        self.assertEqual(filters["candidate-a"]["excludes"], ["road-edge-line"])
        self.assertEqual(filters["candidate-b"]["excludes"], [])

    def test_experimental_method_remains_research_lead(self):
        experimental = clue()
        experimental["inference"]["method_maturity"] = "experimental"
        result = build_micro_osint_ledger([experimental], ["candidate-a"])
        filters = result["candidate_filters"]["candidates"]["candidate-a"]
        self.assertEqual(filters["supports"], [])
        self.assertEqual(filters["research_leads"], ["road-edge-line"])

    def test_rejects_uncalibrated_probability(self):
        invalid = clue(confidence=0.91)
        with self.assertRaisesRegex(ValueError, "Uncalibrated numeric certainty"):
            build_micro_osint_ledger([invalid], ["candidate-a"])

    def test_verified_clue_requires_reference(self):
        invalid = clue()
        invalid["verification"]["references"] = []
        with self.assertRaisesRegex(ValueError, "must cite"):
            build_micro_osint_ledger([invalid], ["candidate-a"])

    def test_region_must_stay_inside_image(self):
        invalid = clue(region={"x": 0.8, "y": 0.2, "width": 0.4, "height": 0.2})
        with self.assertRaisesRegex(ValueError, "inside the image"):
            build_micro_osint_ledger([invalid], ["candidate-a"])

    def test_workspace_does_not_change_location_candidates(self):
        osint = {"candidates": [{"id": "candidate-a", "label": "A"}]}
        result = attach_micro_osint_workspace(osint)
        self.assertEqual(result["candidates"], osint["candidates"])
        self.assertFalse(result["micro_osint"]["assessment"]["formal_location_conclusion"])


if __name__ == "__main__":
    unittest.main()
