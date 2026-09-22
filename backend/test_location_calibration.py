import os
import tempfile
import unittest
from pathlib import Path

from backend.location_calibration import apply_location_calibration, build_calibration_from_records


class LocationCalibrationTests(unittest.TestCase):
    def test_builds_empirical_bins_and_calibrates_matching_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = []
            for index in range(60):
                score = index / 59
                records.append({
                    "scene": "urban" if index % 2 else "rural",
                    "condition": "daylight" if index % 3 else "night",
                    "predictions": [
                        {"retrieval_score": score, "distance_km": 5 if score >= 0.6 else 400},
                        {"retrieval_score": score * 0.9, "distance_km": 20 if score >= 0.8 else 600},
                        {"retrieval_score": score * 0.8, "distance_km": 800},
                    ],
                })
            calibration_path = root / "calibration.npz"
            report_path = root / "report.json"
            result = build_calibration_from_records(
                records,
                model_fingerprint="model-test-1",
                output_path=calibration_path,
                report_path=report_path,
            )
            self.assertEqual(result["overall"]["queries"], 60)
            self.assertTrue(report_path.is_file())

            previous = os.environ.get("GEOTRACE_CALIBRATION_PATH")
            os.environ["GEOTRACE_CALIBRATION_PATH"] = str(calibration_path)
            try:
                calibrated = apply_location_calibration({
                    "model": "GeoTrace Visual v0",
                    "model_fingerprint": "model-test-1",
                    "candidates": [{
                        "id": "candidate-1", "retrieval_score": 0.95,
                        "confidence": None, "calibrated": False,
                        "verification_status": "experimental_local_model",
                    }],
                })
            finally:
                if previous is None:
                    os.environ.pop("GEOTRACE_CALIBRATION_PATH", None)
                else:
                    os.environ["GEOTRACE_CALIBRATION_PATH"] = previous
            self.assertEqual(calibrated["calibration"]["status"], "active")
            self.assertTrue(calibrated["candidates"][0]["calibrated"])
            self.assertGreater(calibrated["candidates"][0]["confidence"], 0.6)
            self.assertGreaterEqual(calibrated["candidates"][0]["calibration_samples"], 8)

    def test_rejects_stale_model_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = [{
                "scene": "urban", "condition": "daylight",
                "predictions": [{"retrieval_score": index / 59, "distance_km": 5}],
            } for index in range(60)]
            calibration_path = root / "calibration.npz"
            build_calibration_from_records(
                records, "old-model", calibration_path, root / "report.json",
            )
            previous = os.environ.get("GEOTRACE_CALIBRATION_PATH")
            os.environ["GEOTRACE_CALIBRATION_PATH"] = str(calibration_path)
            try:
                result = apply_location_calibration({
                    "model_fingerprint": "new-model",
                    "candidates": [{"retrieval_score": 0.9, "confidence": None, "calibrated": False}],
                })
            finally:
                if previous is None:
                    os.environ.pop("GEOTRACE_CALIBRATION_PATH", None)
                else:
                    os.environ["GEOTRACE_CALIBRATION_PATH"] = previous
            self.assertEqual(result["calibration"]["status"], "stale_model")
            self.assertFalse(result["candidates"][0]["calibrated"])


if __name__ == "__main__":
    unittest.main()
