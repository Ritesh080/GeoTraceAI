import csv
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from backend.local_source_provenance import build_provenance_index, match_source_provenance


class LocalSourceProvenanceTests(unittest.TestCase):
    def test_finds_reencoded_copy_and_builds_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.png"
            reencoded = root / "reencoded.jpg"
            image = Image.new("RGB", (320, 240), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((30, 30, 150, 170), fill="navy")
            draw.ellipse((170, 60, 290, 190), fill="orange")
            draw.line((0, 220, 320, 20), fill="green", width=8)
            image.save(original)
            image.resize((640, 480)).save(reencoded, quality=82)

            manifest = root / "manifest.csv"
            fields = ["image_path", "reference_id", "title", "source_name", "source_url", "published_at", "license", "attribution", "origin_group"]
            with manifest.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow({"image_path": original.name, "reference_id": "source-1", "title": "Original post", "source_name": "Archive", "source_url": "https://example.test/original", "published_at": "2025-01-01T00:00:00Z", "license": "CC-BY-4.0", "attribution": "Tester", "origin_group": "origin-1"})
                writer.writerow({"image_path": reencoded.name, "reference_id": "source-2", "title": "Repost", "source_name": "Mirror", "source_url": "https://example.test/repost", "published_at": "2025-02-01T00:00:00Z", "license": "CC-BY-4.0", "attribution": "Tester", "origin_group": "origin-1"})
            index = root / "provenance.npz"
            summary = build_provenance_index(manifest, index)
            self.assertEqual(summary["origin_groups"], 1)

            previous = os.environ.get("GEOTRACE_PROVENANCE_INDEX_PATH")
            os.environ["GEOTRACE_PROVENANCE_INDEX_PATH"] = str(index)
            try:
                result = match_source_provenance(reencoded, {
                    "privacy": {"note": "Local analysis."},
                    "clues": [],
                    "dependency_groups": [],
                    "uncertainty": {"abstention_reasons": ["Reverse-image matches require a manual provider search or configured API adapter."]},
                })
            finally:
                if previous is None:
                    os.environ.pop("GEOTRACE_PROVENANCE_INDEX_PATH", None)
                else:
                    os.environ["GEOTRACE_PROVENANCE_INDEX_PATH"] = previous

            provenance = result["source_provenance"]
            self.assertEqual(provenance["status"], "matches_found")
            self.assertEqual(provenance["independent_origin_groups"], 1)
            self.assertEqual(provenance["matches"][0]["reference_id"], "source-2")
            self.assertEqual(provenance["timeline"][0]["reference_id"], "source-1")
            self.assertEqual(provenance["timeline"][0]["timeline_role"], "earliest_indexed_occurrence")
            self.assertIn("not uploaded", result["privacy"]["note"])


if __name__ == "__main__":
    unittest.main()
