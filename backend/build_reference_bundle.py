"""Atomically build GeoTrace reference indexes from a licensed data bundle."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from backend.index_coverage import coverage_report
from backend.local_map_verification import build_map_index
from backend.local_source_provenance import build_provenance_index
from backend.local_street_imagery import build_street_index
from backend.local_visual_model import train_from_manifest
from backend.location_calibration import benchmark_and_calibrate


ARTIFACTS = {
    "visual": "geotrace_visual_v0.npz",
    "map": "geotrace_places_v0.npz",
    "street": "geotrace_street_v0.npz",
    "provenance": "geotrace_provenance_v0.npz",
    "calibration": "geotrace_calibration_v0.npz",
    "benchmark_report": "geotrace_benchmark_report_v0.json",
    "bundle_report": "geotrace_reference_bundle_report.json",
}


class ReferenceBundleError(RuntimeError):
    """The licensed reference bundle is incomplete or invalid."""


def _resolve(base: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _load_config(config_path: Path) -> dict:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReferenceBundleError("Bundle configuration must be a readable JSON file.") from error
    if not isinstance(config, dict) or not str(config.get("bundle_id", "")).strip():
        raise ReferenceBundleError("Bundle configuration requires a non-empty bundle_id.")
    ledger = config.get("source_ledger")
    if not isinstance(ledger, list) or not ledger:
        raise ReferenceBundleError("Bundle configuration requires a non-empty source_ledger.")
    required = {"source_id", "name", "license", "attribution", "terms_url"}
    seen = set()
    for source in ledger:
        if not isinstance(source, dict) or not all(str(source.get(key, "")).strip() for key in required):
            raise ReferenceBundleError("Each source ledger entry needs source_id, name, license, attribution, and terms_url.")
        if source["source_id"] in seen:
            raise ReferenceBundleError(f"Duplicate source_id in ledger: {source['source_id']}")
        seen.add(source["source_id"])
    return config


def _audit_manifests(base: Path, config: dict) -> dict:
    ledger = {source["source_id"]: source for source in config["source_ledger"]}
    hashes: dict[str, list[dict]] = {}
    rows = 0
    for key in ("visual_manifest", "street_manifest", "provenance_manifest", "benchmark_manifest"):
        manifest = _resolve(base, config.get(key))
        if manifest is None:
            continue
        if not manifest.is_file():
            raise ReferenceBundleError(f"Configured {key} was not found: {manifest}")
        with manifest.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            required = {"image_path", "source_id"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ReferenceBundleError(f"{manifest.name} must include image_path and source_id for production ingestion.")
            for line_number, row in enumerate(reader, start=2):
                source_id = (row.get("source_id") or "").strip()
                if source_id not in ledger:
                    raise ReferenceBundleError(f"Unknown source_id '{source_id}' in {manifest.name} line {line_number}.")
                image = _resolve(manifest.parent, row.get("image_path"))
                if image is None or not image.is_file():
                    raise ReferenceBundleError(f"Missing image in {manifest.name} line {line_number}.")
                digest = hashlib.sha256(image.read_bytes()).hexdigest()
                hashes.setdefault(digest, []).append({"manifest": key, "line": line_number, "source_id": source_id})
                rows += 1
    duplicates = [
        {"sha256": digest, "references": references}
        for digest, references in hashes.items()
        if len(references) > 1
    ]
    for duplicate in duplicates:
        source_ids = {reference["source_id"] for reference in duplicate["references"]}
        licenses = {(ledger[source_id]["license"], ledger[source_id]["attribution"]) for source_id in source_ids}
        if len(licenses) > 1:
            raise ReferenceBundleError(
                f"One image hash has conflicting licence records: {duplicate['sha256'][:12]}."
            )
    return {"manifest_rows": rows, "unique_images": len(hashes), "duplicate_references": duplicates}


def build_reference_bundle(config_path: str | Path, output_directory: str | Path) -> dict:
    """Build configured artifacts in staging and replace live files only after success."""
    config_file = Path(config_path).resolve()
    config = _load_config(config_file)
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=True)
    lock_path = output / ".geotrace-reference-build.lock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise ReferenceBundleError("Another reference bundle build is already running.") from error
    try:
        os.write(lock_fd, str(os.getpid()).encode())
        os.close(lock_fd)
        audit = _audit_manifests(config_file.parent, config)
        build_results: dict[str, dict] = {}
        with tempfile.TemporaryDirectory(prefix="geotrace-indexes-", dir=output.parent) as temporary:
            staging = Path(temporary)
            staged_paths: dict[str, Path] = {}
            visual_manifest = _resolve(config_file.parent, config.get("visual_manifest"))
            if visual_manifest:
                staged_paths["visual"] = staging / ARTIFACTS["visual"]
                build_results["visual"] = train_from_manifest(visual_manifest, staged_paths["visual"])
            map_source = _resolve(config_file.parent, config.get("map_source"))
            if map_source:
                staged_paths["map"] = staging / ARTIFACTS["map"]
                build_results["map"] = build_map_index(
                    map_source,
                    staged_paths["map"],
                    _resolve(config_file.parent, config.get("country_info")),
                )
            street_manifest = _resolve(config_file.parent, config.get("street_manifest"))
            if street_manifest:
                staged_paths["street"] = staging / ARTIFACTS["street"]
                build_results["street"] = build_street_index(street_manifest, staged_paths["street"])
            provenance_manifest = _resolve(config_file.parent, config.get("provenance_manifest"))
            if provenance_manifest:
                staged_paths["provenance"] = staging / ARTIFACTS["provenance"]
                build_results["provenance"] = build_provenance_index(provenance_manifest, staged_paths["provenance"])
            benchmark_manifest = _resolve(config_file.parent, config.get("benchmark_manifest"))
            if benchmark_manifest:
                if "visual" not in staged_paths:
                    raise ReferenceBundleError("benchmark_manifest requires visual_manifest in the same atomic bundle.")
                staged_paths["calibration"] = staging / ARTIFACTS["calibration"]
                staged_paths["benchmark_report"] = staging / ARTIFACTS["benchmark_report"]
                build_results["calibration"] = benchmark_and_calibrate(
                    benchmark_manifest,
                    staged_paths["calibration"],
                    staged_paths["benchmark_report"],
                    model_path=staged_paths["visual"],
                    distance_threshold_km=float(config.get("distance_threshold_km", 25)),
                )
            inspection_paths = {
                key: staged_paths.get(key, output / ARTIFACTS[key])
                for key in ("visual", "map", "street", "provenance", "calibration")
            }
            report = {
                "bundle_id": config["bundle_id"],
                "built_at": datetime.now(timezone.utc).isoformat(),
                "sources": config["source_ledger"],
                "audit": audit,
                "build_results": build_results,
                "coverage": coverage_report(inspection_paths),
            }
            report_path = staging / ARTIFACTS["bundle_report"]
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            staged_paths["bundle_report"] = report_path
            for key, staged in staged_paths.items():
                os.replace(staged, output / ARTIFACTS[key])
        return report
    finally:
        lock_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="JSON bundle configuration")
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "models"))
    arguments = parser.parse_args()
    print(json.dumps(build_reference_bundle(arguments.config, arguments.output_dir), indent=2))


if __name__ == "__main__":
    main()
