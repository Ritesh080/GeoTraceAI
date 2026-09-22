import csv
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from backend.local_street_imagery import build_street_index, compare_street_imagery


class LocalStreetImageryTests(unittest.TestCase):
    def test_builds_and_compares_nearby_licensed_references(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            red = root / "red.jpg"
            blue = root / "blue.jpg"
            Image.new("RGB", (128, 128), (220, 30, 30)).save(red)
            Image.new("RGB", (128, 128), (30, 30, 220)).save(blue)
            manifest = root / "street.csv"
            fields = ["image_path", "reference_id", "label", "latitude", "longitude", "heading", "source_url", "license", "attribution", "captured_at"]
            with manifest.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow({"image_path": red.name, "reference_id": "red-1", "label": "Red Road", "latitude": 28.614, "longitude": 77.209, "heading": 90, "source_url": "https://example.test/red", "license": "CC-BY-SA-4.0", "attribution": "Example contributor", "captured_at": "2026-01-01"})
                writer.writerow({"image_path": blue.name, "reference_id": "blue-1", "label": "Blue Road", "latitude": 19.076, "longitude": 72.878, "heading": "", "source_url": "https://example.test/blue", "license": "CC-BY-4.0", "attribution": "Example contributor", "captured_at": "2026-01-02"})
            index = root / "street.npz"
            summary = build_street_index(manifest, index)
            self.assertEqual(summary["reference_images"], 2)

            previous = os.environ.get("GEOTRACE_STREET_INDEX_PATH")
            os.environ["GEOTRACE_STREET_INDEX_PATH"] = str(index)
            try:
                result = compare_street_imagery(red, {
                    "privacy": {"note": "Local analysis."},
                    "uncertainty": {"outcome": "candidate_needs_corroboration"},
                    "candidates": [{
                        "id": "candidate_1", "rank": 1, "label": "New Delhi",
                        "latitude": 28.614, "longitude": 77.209,
                        "source_group": "submitted_asset", "supports": [],
                        "verification_status": "needs_review",
                    }],
                })
            finally:
                if previous is None:
                    os.environ.pop("GEOTRACE_STREET_INDEX_PATH", None)
                else:
                    os.environ["GEOTRACE_STREET_INDEX_PATH"] = previous

            record = result["street_imagery_comparison"]["records"][0]
            self.assertEqual(record["matches"][0]["reference_id"], "red-1")
            self.assertEqual(record["status"], "strong_street_similarity_for_review")
            self.assertEqual(result["uncertainty"]["outcome"], "candidate_partially_corroborated")
            self.assertIn("not sent", result["privacy"]["note"])


if __name__ == "__main__":
    unittest.main()
