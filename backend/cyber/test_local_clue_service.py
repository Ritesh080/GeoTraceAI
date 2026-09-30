import unittest
from tempfile import NamedTemporaryFile

from PIL import Image

from local_clue_service import detect_indian_scripts, extract_local_clues


class LocalClueServiceTests(unittest.TestCase):
    def test_detects_indian_unicode_scripts(self):
        scripts = detect_indian_scripts("दिल्ली কলকাতা Chennai")
        self.assertEqual(scripts[0]["script"], "Devanagari")
        self.assertEqual({item["script"] for item in scripts}, {"Devanagari", "Bengali-Assamese"})

    def test_extracts_reproducible_image_characteristics(self):
        with NamedTemporaryFile(suffix=".png") as temporary:
            Image.new("RGB", (80, 40), color=(40, 100, 160)).save(temporary.name)
            result = extract_local_clues(temporary.name, include_ocr=False)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["processing"], "on_device")
        self.assertEqual(result["image_characteristics"]["aspect_ratio"], 2.0)
        self.assertEqual(len(result["image_characteristics"]["perceptual_average_hash"]), 16)
        self.assertEqual(result["ocr"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
