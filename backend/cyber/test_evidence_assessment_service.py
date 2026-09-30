import unittest

from evidence_assessment_service import assess_social_evidence


class EvidenceAssessmentServiceTests(unittest.TestCase):
    def test_marks_independent_agreement_as_corroborated(self):
        result = {
            "geolocation": {
                "providers": {
                    "geoclip": {"status": "success"},
                    "text_gazetteer": {"status": "success"},
                    "exif": {"status": "unavailable"},
                },
                "consensus": {"selected": {"provider_count": 2}},
            },
            "visual_clues": {"ocr": {"combined_text": "New Delhi"}},
        }
        source = {"public_source_url": "https://example.com/post"}

        assessment = assess_social_evidence(result, source)

        self.assertEqual(assessment["level"], "corroborated_lead")
        self.assertTrue(assessment["signals"]["independent_provider_agreement"])
        self.assertTrue(assessment["show_location"])
        self.assertIn("not the probability", assessment["score_note"])

    def test_marks_unclustered_sources_as_conflicting(self):
        result = {
            "geolocation": {
                "providers": {
                    "geoclip": {"status": "success"},
                    "text_gazetteer": {"status": "success"},
                    "exif": {"status": "unavailable"},
                },
                "consensus": {"selected": {"provider_count": 1}},
            },
            "visual_clues": {"ocr": {"combined_text": ""}},
        }

        assessment = assess_social_evidence(result, {"public_source_url": "https://example.com"})

        self.assertEqual(assessment["level"], "conflicting_or_unclustered_leads")
        self.assertFalse(assessment["show_location"])

    def test_explains_when_a_link_contains_no_location_signal(self):
        result = {
            "geolocation": {
                "providers": {
                    "geoclip": {"status": "skipped"},
                    "text_gazetteer": {"status": "unavailable"},
                    "exif": {"status": "skipped"},
                },
                "consensus": {},
            },
            "visual_clues": {"ocr": {"combined_text": ""}},
        }

        assessment = assess_social_evidence(
            result, {"public_source_url": "https://example.com/post"}
        )

        self.assertEqual(assessment["level"], "insufficient_location_evidence")
        self.assertTrue(any("no usable location signal" in value for value in assessment["cautions"]))

    def test_abstains_after_rejecting_generic_instagram_preview(self):
        result = {
            "geolocation": {
                "providers": {
                    "geoclip": {"status": "skipped"},
                    "text_gazetteer": {"status": "unavailable"},
                    "exif": {"status": "skipped"},
                },
                "consensus": {},
            },
            "visual_clues": {"ocr": {"combined_text": ""}},
        }
        source = {
            "public_source_url": "https://www.instagram.com/p/example/",
            "automatic_collection": {
                "media_status": "generic_platform_preview_rejected"
            },
        }

        assessment = assess_social_evidence(result, source)

        self.assertFalse(assessment["show_location"])
        self.assertEqual(assessment["display_status"], "abstained_unverified")
        self.assertTrue(any("generic platform artwork" in value for value in assessment["cautions"]))


if __name__ == "__main__":
    unittest.main()
