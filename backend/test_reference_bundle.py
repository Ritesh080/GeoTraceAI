from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.build_reference_bundle import ReferenceBundleError, build_reference_bundle


def geonames_row(name: str = "Delhi") -> str:
    fields = ["1", name, name, "", "28.6139", "77.2090", "P", "PPLC", "IN", "", "", "", "", "", "20000000", "", "", "Asia/Kolkata", "2026-01-01"]
    return "\t".join(fields) + "\n"


class ReferenceBundleTests(unittest.TestCase):
    def _config(self, root: Path, map_name: str) -> Path:
        config = root / "bundle.json"
        config.write_text(json.dumps({
            "bundle_id": "test-bundle",
            "source_ledger": [{
                "source_id": "geonames",
                "name": "GeoNames",
                "license": "CC BY 4.0",
                "attribution": "GeoNames",
                "terms_url": "https://www.geonames.org/",
            }],
            "map_source": map_name,
        }), encoding="utf-8")
        return config

    def test_builds_map_and_report_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "models"
            (root / "places.txt").write_text(geonames_row(), encoding="utf-8")
            report = build_reference_bundle(self._config(root, "places.txt"), output)
            self.assertEqual(report["bundle_id"], "test-bundle")
            self.assertTrue((output / "geotrace_places_v0.npz").is_file())
            self.assertTrue((output / "geotrace_reference_bundle_report.json").is_file())

    def test_failed_refresh_preserves_previous_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "models"
            output.mkdir()
            target = output / "geotrace_places_v0.npz"
            target.write_bytes(b"previous-working-index")
            (root / "bad.txt").write_text("not-a-geonames-row\n", encoding="utf-8")
            with self.assertRaises(Exception):
                build_reference_bundle(self._config(root, "bad.txt"), output)
            self.assertEqual(target.read_bytes(), b"previous-working-index")
            self.assertFalse((output / ".geotrace-reference-build.lock").exists())

    def test_rejects_incomplete_source_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "bundle.json"
            config.write_text(json.dumps({"bundle_id": "bad", "source_ledger": [{"source_id": "x"}]}), encoding="utf-8")
            with self.assertRaises(ReferenceBundleError):
                build_reference_bundle(config, root / "models")


if __name__ == "__main__":
    unittest.main()
