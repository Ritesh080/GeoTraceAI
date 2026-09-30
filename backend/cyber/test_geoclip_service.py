import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from geoclip_service import geolocate_image


class FakeTensor:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class FakeModel:
    def predict(self, image_path, top_k):
        assert Path(image_path).is_file()
        assert top_k == 2
        return (
            FakeTensor([[12.9716, 77.5946], [28.6139, 77.2090]]),
            FakeTensor([0.6, 0.25]),
        )


class GeoClipServiceTests(unittest.TestCase):
    @patch("geoclip_service._get_model", return_value=(FakeModel(), "cpu"))
    def test_formats_ranked_candidates(self, _mock_get_model):
        with NamedTemporaryFile(suffix=".png") as image:
            result = geolocate_image(image.name, top_k=2)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["device"], "cpu")
        self.assertEqual(result["candidates"][0]["rank"], 1)
        self.assertEqual(result["candidates"][0]["latitude"], 12.9716)
        self.assertEqual(result["candidates"][1]["longitude"], 77.209)
        self.assertIn("openstreetmap.org", result["candidates"][0]["map_url"])

    def test_rejects_unbounded_candidate_count(self):
        with self.assertRaises(ValueError):
            geolocate_image("unused.png", top_k=21)


if __name__ == "__main__":
    unittest.main()
