import os
import unittest
from unittest.mock import patch

from backend.gods_eye_context import attach_area_view_links, build_area_view_url


class GodsEyeContextTests(unittest.TestCase):
    @patch.dict(os.environ, {"GEOTRACE_GODS_EYE_URL": "https://viewer.example"})
    def test_builds_upstream_v2_camera_link(self):
        url = build_area_view_url(28.6139, 77.2090)
        self.assertTrue(url.startswith("https://viewer.example/#v=2&lat=28.6139&lon=77.2090"))
        self.assertIn("pitch=-35", url)
        self.assertIn("map=photoreal", url)

    @patch.dict(os.environ, {"GEOTRACE_GODS_EYE_URL": "https://viewer.example"})
    def test_adds_context_without_changing_candidate_evidence(self):
        osint = {"candidates": [{"id": "candidate-a", "latitude": 28.6139, "longitude": 77.209, "supports": [{"evidence_id": "one"}]}]}
        result = attach_area_view_links(osint)
        self.assertEqual(result["candidates"][0]["supports"], osint["candidates"][0]["supports"])
        self.assertEqual(result["candidates"][0]["area_view"]["evidence_status"], "investigative_context_only")

    @patch.dict(os.environ, {}, clear=True)
    def test_disabled_without_reviewed_viewer(self):
        result = attach_area_view_links({"candidates": [{"latitude": 1, "longitude": 2}]})
        self.assertEqual(result["area_view"]["status"], "not_configured")
        self.assertNotIn("area_view", result["candidates"][0])

    @patch.dict(os.environ, {"GEOTRACE_GODS_EYE_URL": "javascript:alert(1)"})
    def test_rejects_unsafe_viewer_scheme(self):
        self.assertIsNone(build_area_view_url(1, 2))


if __name__ == "__main__":
    unittest.main()
