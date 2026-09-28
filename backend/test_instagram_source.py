import base64
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backend.instagram_source import (
    InstagramImportError,
    _location_lookup,
    _post_metadata,
    build_loader,
    extract_shortcode,
    instagram_provider_status,
)


class InstagramSourceTests(unittest.TestCase):
    def test_normalizes_bounded_instagram_post_metadata(self):
        post = type("Post", (), {
            "_node": {"dimensions": {"width": 1080, "height": 1350}},
            "shortcode": "AbC123",
            "owner_username": "example",
            "date_utc": datetime(2026, 9, 28, 10, 30, tzinfo=timezone.utc),
            "typename": "GraphImage",
            "mediacount": 1,
            "is_video": False,
            "likes": 42,
            "comments": 3,
            "caption": "Photograph from Delhi #Delhi @friend",
            "caption_hashtags": ["delhi"],
            "caption_mentions": ["friend"],
            "accessibility_caption": "A public square",
        })()
        location_lookup = {
            "status": "available",
            "authenticated": True,
            "location": {"name": "New Delhi", "latitude": 28.6139, "longitude": 77.209},
        }

        result = _post_metadata(post, location_lookup)

        self.assertEqual(result["width"], 1080)
        self.assertEqual(result["likes"], 42)
        self.assertEqual(result["hashtags"], ["delhi"])
        self.assertEqual(result["location"]["name"], "New Delhi")
        self.assertTrue(result["authenticated_lookup"])

    def test_exact_post_location_is_preserved(self):
        location = type("Location", (), {"name": "New Delhi", "lat": 28.6139, "lng": 77.209})()
        post = type("Post", (), {
            "_node": {"location": {"name": "New Delhi", "id": "1"}},
            "_context": type("Context", (), {"is_logged_in": True})(),
            "location": location,
        })()

        result = _location_lookup(post)

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["location"]["name"], "New Delhi")
        self.assertEqual(result["location"]["latitude"], 28.6139)

    def test_public_post_label_survives_logged_out_lookup(self):
        post = type("Post", (), {
            "_node": {"location": {"name": "Connaught Place", "id": "2"}},
            "_context": type("Context", (), {"is_logged_in": False})(),
            "location": None,
        })()

        result = _location_lookup(post)

        self.assertEqual(result["status"], "public_label_only")
        self.assertEqual(result["location"]["name"], "Connaught Place")
        self.assertIsNone(result["location"]["latitude"])

    def test_logged_out_post_without_public_claim_reports_auth_requirement(self):
        post = type("Post", (), {
            "_node": {},
            "_context": type("Context", (), {"is_logged_in": False})(),
            "location": None,
        })()

        result = _location_lookup(post)

        self.assertEqual(result["status"], "authentication_required")
        self.assertIsNone(result["location"])

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
