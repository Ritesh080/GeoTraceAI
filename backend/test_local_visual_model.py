import csv
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from backend.local_visual_model import predict_locations, train_from_manifest


class LocalVisualModelTests(unittest.TestCase):
    def test_trains_and_predicts_from_local_reference_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            red = root / "red.jpg"
            blue = root / "blue.jpg"
            Image.new("RGB", (96, 96), (220, 30, 30)).save(red)
            Image.new("RGB", (96, 96), (30, 30, 220)).save(blue)
            manifest = root / "manifest.csv"
            with manifest.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["image_path", "label", "latitude", "longitude", "precision_tier"],
                )
                writer.writeheader()
                writer.writerow({"image_path": red.name, "label": "Red Place", "latitude": 10, "longitude": 20, "precision_tier": "test"})
                writer.writerow({"image_path": blue.name, "label": "Blue Place", "latitude": 30, "longitude": 40, "precision_tier": "test"})
            model = root / "model.npz"
            summary = train_from_manifest(manifest, model)
            self.assertEqual(summary["reference_images"], 2)

            import os
            previous = os.environ.get("GEOTRACE_VISUAL_MODEL_PATH")
            os.environ["GEOTRACE_VISUAL_MODEL_PATH"] = str(model)
            try:
                result = predict_locations(red, top_k=2)
            finally:
                if previous is None:
                    os.environ.pop("GEOTRACE_VISUAL_MODEL_PATH", None)
                else:
                    os.environ["GEOTRACE_VISUAL_MODEL_PATH"] = previous
            self.assertEqual(result["candidates"][0]["label"], "Red Place")
            self.assertEqual(result["candidates"][0]["provider"], "GeoTrace Visual v0")
            self.assertIsNone(result["candidates"][0]["confidence"])


if __name__ == "__main__":
    unittest.main()
