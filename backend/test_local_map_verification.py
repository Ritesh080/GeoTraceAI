import os
import tempfile
import unittest
from pathlib import Path

from backend.local_map_verification import build_map_index, verify_map_context


def geonames_row(identifier: str, name: str, latitude: float, longitude: float, country: str, population: int) -> str:
    fields = [identifier, name, name, "", str(latitude), str(longitude), "P", "PPL", country, "", "", "", "", "", str(population), "", "", "UTC", "2026-01-01"]
    return "\t".join(fields)


class LocalMapVerificationTests(unittest.TestCase):
    def test_matches_candidate_and_ocr_against_local_place_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "cities.txt"
            source.write_text(
                geonames_row("1", "New Delhi", 28.6139, 77.2090, "IN", 249998) + "\n"
                + geonames_row("2", "Mumbai", 19.0760, 72.8777, "IN", 12442373) + "\n",
                encoding="utf-8",
            )
            countries = root / "countryInfo.txt"
            countries.write_text("IN\tIND\t356\tIN\tIndia\tNew Delhi\n", encoding="utf-8")
            model = root / "places.npz"
            build_map_index(source, model, countries)
            previous = os.environ.get("GEOTRACE_MAP_INDEX_PATH")
            os.environ["GEOTRACE_MAP_INDEX_PATH"] = str(model)
            try:
                result = verify_map_context(
                    {
                        "privacy": {"note": "Local analysis."},
                        "actions": [],
                        "uncertainty": {"outcome": "candidate_needs_corroboration"},
                        "candidates": [{
                            "id": "candidate_1", "rank": 1, "label": "New Delhi, India",
                            "latitude": 28.614, "longitude": 77.21,
                            "source_group": "visual_model", "supports": [],
                            "verification_status": "needs_review",
                        }],
                    },
                    ocr_text="Welcome to New Delhi",
                )
            finally:
                if previous is None:
                    os.environ.pop("GEOTRACE_MAP_INDEX_PATH", None)
                else:
                    os.environ["GEOTRACE_MAP_INDEX_PATH"] = previous
            self.assertEqual(result["uncertainty"]["outcome"], "candidate_partially_corroborated")
            self.assertEqual(result["map_verification"]["records"][0]["place"]["name"], "New Delhi")
            self.assertIn("delhi", result["map_verification"]["records"][0]["ocr_matches"])
            self.assertFalse(result["privacy"].get("external_processing", False))


if __name__ == "__main__":
    unittest.main()
