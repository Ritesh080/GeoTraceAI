import unittest
from unittest.mock import patch

from text_location_service import _candidate_phrases, extract_text_location_candidates


class TextLocationServiceTests(unittest.TestCase):
    def test_expands_hashtags_and_camel_case(self):
        phrases = _candidate_phrases("Trip to #NewDelhi and #Mumbai_Diaries")
        self.assertIn("new delhi", phrases)
        self.assertIn("mumbai diaries", phrases)

    @patch("text_location_service.DATABASE_PATH")
    def test_extracts_explicit_coordinates_without_index(self, database_path):
        database_path.is_file.return_value = False
        result = extract_text_location_candidates("Location: 28.6139, 77.2090")

        self.assertEqual(result["candidates"][0]["latitude"], 28.6139)
        self.assertEqual(
            result["candidates"][0]["evidence_type"], "explicit_coordinates"
        )


if __name__ == "__main__":
    unittest.main()
