import unittest

from backend.instagram_source import InstagramImportError, extract_shortcode


class InstagramSourceTests(unittest.TestCase):
    def test_extracts_post_shortcode(self):
        self.assertEqual(
            extract_shortcode("https://www.instagram.com/p/AbC_123-xY/"),
            "AbC_123-xY",
        )

    def test_extracts_reel_shortcode(self):
        self.assertEqual(
            extract_shortcode("https://instagram.com/reel/AbC123/?utm_source=test"),
            "AbC123",
        )

    def test_rejects_non_instagram_hosts(self):
        with self.assertRaises(InstagramImportError):
            extract_shortcode("https://example.com/p/AbC123/")

    def test_rejects_profile_urls(self):
        with self.assertRaises(InstagramImportError):
            extract_shortcode("https://www.instagram.com/example/")


if __name__ == "__main__":
    unittest.main()
