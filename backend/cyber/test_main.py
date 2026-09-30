import unittest
from unittest.mock import patch

from main import analyze_text_evidence


class TextOnlyAnalysisTests(unittest.TestCase):
    @patch("main.extract_text_location_candidates")
    def test_social_text_can_be_analyzed_without_an_image(self, extract_locations):
        extract_locations.return_value = {
            "status": "success",
            "provider": "GeoTrace India Text Gazetteer",
            "candidates": [
                {"rank": 1, "latitude": 28.6139, "longitude": 77.2090}
            ],
        }

        result = analyze_text_evidence("India Gate #NewDelhi")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["file"]["status"], "not_provided")
        self.assertEqual(
            result["geolocation"]["consensus"]["selected"]["latitude"],
            28.6139,
        )
        self.assertFalse(
            result["geolocation"]["privacy"]["image_shared_externally"]
        )


if __name__ == "__main__":
    unittest.main()
