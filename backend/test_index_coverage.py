from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.index_coverage import coverage_report


class IndexCoverageTests(unittest.TestCase):
    def test_reports_counts_spatial_cells_and_missing_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            visual = root / "visual.npz"
            np.savez_compressed(
                visual,
                labels=np.asarray(["Delhi", "Delhi", "Paris"]),
                latitudes=np.asarray([28.61, 28.62, 48.85]),
                longitudes=np.asarray([77.20, 77.21, 2.35]),
            )
            report = coverage_report({
                "visual": visual,
                "map": root / "missing-map.npz",
                "street": root / "missing-street.npz",
                "provenance": root / "missing-provenance.npz",
                "calibration": root / "missing-calibration.npz",
            })
            dataset = report["datasets"][0]
            self.assertEqual(dataset["status"], "active")
            self.assertEqual(dataset["reference_count"], 3)
            self.assertEqual(dataset["one_degree_cells"], 2)
            self.assertFalse(report["full_reference_coverage"])
            self.assertTrue(report["analysis_operational"])


if __name__ == "__main__":
    unittest.main()
