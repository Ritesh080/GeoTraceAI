import unittest

from backend.osint_stage import build_osint_assessment


class OsintStageTests(unittest.TestCase):
    def test_abstains_without_independent_sources(self):
        result = build_osint_assessment("a" * 64, {"gps_present": False})
        self.assertEqual(result["uncertainty"]["outcome"], "insufficient_evidence")
        self.assertIsNone(result["uncertainty"]["confidence"])
        self.assertFalse(result["privacy"]["automatic_external_upload"])
        self.assertEqual(len(result["dependency_groups"]), 1)
        self.assertEqual(result["candidates"], [])

    def test_adds_map_checks_for_valid_gps(self):
        result = build_osint_assessment(
            "b" * 64,
            {
                "gps_present": True,
                "coordinates_valid": True,
                "latitude": 28.6139,
                "longitude": 77.209,
            },
        )
        action_ids = {action["id"] for action in result["actions"]}
        self.assertIn("osm_map_check", action_ids)
        self.assertIn("google_maps_check", action_ids)
        self.assertIn("embedded_gps", result["dependency_groups"][0]["member_ids"])
        self.assertEqual(result["candidates"][0]["rank"], 1)
        self.assertEqual(result["candidates"][0]["precision_tier"], "exact_coordinate")
        self.assertEqual(result["candidates"][0]["verification_status"], "needs_independent_corroboration")
        self.assertEqual(result["uncertainty"]["outcome"], "candidate_needs_corroboration")

    def test_records_conflict_between_distant_independent_candidates(self):
        result = build_osint_assessment(
            "c" * 64,
            {
                "gps_present": True,
                "coordinates_valid": True,
                "latitude": 28.6139,
                "longitude": 77.209,
            },
            provider_candidates=[
                {
                    "id": "vision_candidate",
                    "label": "London, United Kingdom",
                    "latitude": 51.5072,
                    "longitude": -0.1276,
                    "provider": "Test adapter",
                    "source_group": "independent_visual_model",
                }
            ],
        )
        self.assertEqual(result["uncertainty"]["outcome"], "conflicting_evidence")
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertTrue(all(candidate["contradictions"] for candidate in result["candidates"]))


if __name__ == "__main__":
    unittest.main()
