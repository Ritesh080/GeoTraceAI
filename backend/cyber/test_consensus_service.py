import unittest

from consensus_service import build_consensus, exif_location_result


class ConsensusServiceTests(unittest.TestCase):
    def test_groups_nearby_independent_providers(self):
        results = {
            "geoclip": {
                "status": "success",
                "model": "GeoCLIP",
                "candidates": [
                    {"rank": 1, "latitude": 12.9716, "longitude": 77.5946}
                ],
            },
            "oceanir": {
                "status": "success",
                "provider": "Oceanir",
                "candidates": [
                    {"rank": 1, "latitude": 12.9810, "longitude": 77.6000}
                ],
            },
            "geospy": {
                "status": "success",
                "provider": "GeoSpy/Graylark",
                "candidates": [
                    {"rank": 1, "latitude": 48.8566, "longitude": 2.3522}
                ],
            },
        }

        consensus = build_consensus(results, radius_km=10)

        self.assertEqual(consensus["status"], "success")
        self.assertEqual(consensus["selected"]["provider_count"], 2)
        self.assertEqual(consensus["selected"]["agreement"], "multi_provider")
        self.assertEqual(len(consensus["clusters"]), 2)

    def test_one_provider_cannot_outvote_others_with_nearby_candidates(self):
        results = {
            "geoclip": {
                "status": "success",
                "model": "GeoCLIP",
                "candidates": [
                    {"rank": 1, "latitude": 12.9716, "longitude": 77.5946},
                    {"rank": 2, "latitude": 12.9720, "longitude": 77.5950},
                ],
            }
        }

        consensus = build_consensus(results, radius_km=10)

        self.assertEqual(consensus["selected"]["provider_count"], 1)
        self.assertEqual(len(consensus["selected"]["evidence"]), 1)
        self.assertEqual(consensus["selected"]["evidence"][0]["rank"], 1)

    def test_extracts_decimal_and_dms_exif_coordinates(self):
        decimal = exif_location_result(
            {"GPSLatitude": 28.6139, "GPSLongitude": 77.2090}
        )
        dms = exif_location_result(
            {
                "GPSLatitude": "33 deg 52' 8.4\" S",
                "GPSLongitude": "151 deg 12' 34.2\" E",
            }
        )

        self.assertEqual(decimal["status"], "success")
        self.assertAlmostEqual(dms["candidates"][0]["latitude"], -33.869, places=3)
        self.assertAlmostEqual(dms["candidates"][0]["longitude"], 151.2095, places=3)


if __name__ == "__main__":
    unittest.main()
