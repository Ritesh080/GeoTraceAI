import base64
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.instagram_source import InstagramImportError, build_loader, extract_shortcode, instagram_provider_status


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

    def test_reports_authenticated_secret_without_exposing_it(self):
        secret = base64.b64encode(b"session-cookie-data").decode()
        with patch.dict(os.environ, {
            "GEOTRACE_INSTAGRAM_ENABLED": "true",
            "INSTAGRAM_USERNAME": "example",
            "INSTALOADER_SESSION_BASE64": secret,
        }, clear=True):
            status = instagram_provider_status()
        self.assertTrue(status["enabled"])
        self.assertTrue(status["authenticated"])
        self.assertNotIn(secret, str(status))

    def test_loads_base64_session_through_temporary_file_then_deletes_it(self):
        class FakeLoader:
            def __init__(self, **_kwargs):
                self.loaded_path = None
                self.loaded_bytes = None

            def load_session_from_file(self, _username, filename):
                self.loaded_path = filename
                self.loaded_bytes = Path(filename).read_bytes()

            def close(self):
                pass

        with patch("backend.instagram_source.instaloader.Instaloader", FakeLoader), patch.dict(os.environ, {
            "INSTAGRAM_USERNAME": "example",
            "INSTALOADER_SESSION_BASE64": base64.b64encode(b"session-cookie-data").decode(),
        }, clear=True):
            loader = build_loader()
        self.assertEqual(loader.loaded_bytes, b"session-cookie-data")
        self.assertFalse(Path(loader.loaded_path).exists())


if __name__ == "__main__":
    unittest.main()
