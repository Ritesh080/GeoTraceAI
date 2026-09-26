import os
import unittest
from unittest.mock import patch

from backend.osint_stage import build_osint_assessment
from backend.osintgram_source import analyze_osintgram_account, osintgram_provider_status


class OsintgramSourceTests(unittest.TestCase):
    def test_not_configured_is_safe_and_explicit(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(osintgram_provider_status()["enabled"])
            result = analyze_osintgram_account("public.account")
        self.assertEqual(result["status"], "not_configured")

    def test_normalizes_bounded_public_results(self):
        response = {
            "backend": "fake",
            "tool_calls": [
                {"name": "get_user_info", "result": {"username": "example", "follower_count": 42, "has_anonymous_profile_picture": True}},
                {"name": "get_account_about", "result": {"country": "India", "date_joined": "January 2020"}},
                {"name": "get_hashtags", "result": [{"hashtag": "#delhi", "count": 3}]},
                {"name": "get_addrs", "result": [{"name": "Delhi", "address": "Delhi, India", "lat": 28.6139, "lng": 77.209, "time": "2026-01-01"}]},
            ],
        }
        with patch.dict(os.environ, {"GEOTRACE_OSINTGRAM_URL": "http://127.0.0.1:8010"}, clear=True), patch(
            "backend.osintgram_source._request_osintgram", return_value=response
        ):
            result = analyze_osintgram_account("example")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["account_about"]["country"], "India")
        self.assertEqual(result["locations"][0]["latitude"], 28.6139)
        self.assertNotIn("has_anonymous_profile_picture", result["profile"])

    def test_osintgram_clues_are_grouped_as_related_account_evidence(self):
        source = {
            "platform": "instagram",
            "source_group": "instagram:abc",
            "owner_username": "example",
            "canonical_url": "https://www.instagram.com/p/abc/",
            "published_at": "2026-01-01T00:00:00Z",
            "osintgram": {
                "status": "ready",
                "profile": {},
                "account_about": {"country": "India"},
                "locations": [{"name": "Delhi", "address": "Delhi, India"}],
            },
        }
        assessment = build_osint_assessment("a" * 64, {"gps_present": False}, source=source)
        groups = {group["id"]: group for group in assessment["dependency_groups"]}
        self.assertIn("instagram_account:example", groups)
        self.assertIn("osintgram_account_country", groups["instagram_account:example"]["member_ids"])
        self.assertTrue(any("not independent" in reason for reason in assessment["uncertainty"]["abstention_reasons"]))


if __name__ == "__main__":
    unittest.main()
