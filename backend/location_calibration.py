"""Held-out benchmarking and empirical confidence calibration for GeoTrace.

Calibration is tied to one exact visual-model fingerprint. Confidence means
the observed probability that a candidate fell within the configured distance
threshold on held-out benchmark images with a comparable retrieval score.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import os
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import numpy as np

from backend.local_visual_model import _load_model, configured_model_path, predict_locations


CALIBRATION_SCHEMA_VERSION = 1
DEFAULT_CALIBRATION_PATH = Path(__file__).resolve().parent / "models" / "geotrace_calibration_v0.npz"
DEFAULT_REPORT_PATH = Path(__file__).resolve().parent / "models" / "geotrace_benchmark_report_v0.json"
MIN_BENCHMARK_QUERIES = 50
MIN_BIN_SAMPLES = 8


class CalibrationError(RuntimeError):
    """The benchmark or calibration artifact is invalid."""


def configured_calibration_path() -> Path:
    configured = os.getenv("GEOTRACE_CALIBRATION_PATH", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_CALIBRATION_PATH


def _distance_km(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    lat1, lon1 = radians(latitude_a), radians(longitude_a)
    lat2, lon2 = radians(latitude_b), radians(longitude_b)
    delta_latitude = lat2 - lat1
    delta_longitude = lon2 - lon1
    value = sin(delta_latitude / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_longitude / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(value))


def _model_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _metrics(records: list[dict], distance_threshold_km: float) -> dict:
    if not records:
        return {
            "queries": 0, "top1_accuracy": None, "top5_accuracy": None,
            "median_error_km": None, "p90_error_km": None,
        }
    top1_distances = [record["predictions"][0]["distance_km"] for record in records if record["predictions"]]
    top1_hits = [distance <= distance_threshold_km for distance in top1_distances]
    top5_hits = [
        any(prediction["distance_km"] <= distance_threshold_km for prediction in record["predictions"][:5])
        for record in records
    ]
    return {
        "queries": len(records),
        "top1_accuracy": round(sum(top1_hits) / len(records), 4),
        "top5_accuracy": round(sum(top5_hits) / len(records), 4),
        "median_error_km": round(float(np.median(top1_distances)), 2),
        "p90_error_km": round(float(np.percentile(top1_distances, 90)), 2),
    }


def _fit_bins(
    records: list[dict],
    distance_threshold_km: float,
    max_rank: int,
    bins: int,
    min_bin_samples: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    upper_edges = np.full((max_rank, bins), np.nan, dtype=np.float32)
    probabilities = np.full((max_rank, bins), np.nan, dtype=np.float32)
    counts = np.zeros((max_rank, bins), dtype=np.int32)
    for rank_index in range(max_rank):
        samples = []
        for record in records:
            if len(record["predictions"]) <= rank_index:
                continue
            prediction = record["predictions"][rank_index]
            samples.append((prediction["retrieval_score"], prediction["distance_km"] <= distance_threshold_km))
        samples.sort(key=lambda sample: sample[0])
        for bin_index, indexes in enumerate(np.array_split(np.arange(len(samples)), bins)):
            if not len(indexes):
                continue
            selected = [samples[int(index)] for index in indexes]
            count = len(selected)
            correct = sum(1 for _, is_correct in selected if is_correct)
            upper_edges[rank_index, bin_index] = max(score for score, _ in selected)
            counts[rank_index, bin_index] = count
            if count >= min_bin_samples:
                # Laplace smoothing avoids absolute 0/1 claims on small samples.
                probabilities[rank_index, bin_index] = (correct + 1) / (count + 2)
        # Empirical probabilities should not decrease as retrieval score rises.
        valid = np.flatnonzero(~np.isnan(probabilities[rank_index]))
        if len(valid):
            probabilities[rank_index, valid] = np.maximum.accumulate(probabilities[rank_index, valid])
    return upper_edges, probabilities, counts


def build_calibration_from_records(
    records: list[dict],
    model_fingerprint: str,
    output_path: str | Path,
    report_path: str | Path,
    distance_threshold_km: float = 25.0,
    max_rank: int = 3,
    bins: int = 5,
    min_queries: int = MIN_BENCHMARK_QUERIES,
    min_bin_samples: int = MIN_BIN_SAMPLES,
) -> dict:
    """Fit a calibration artifact from held-out prediction records."""
    if len(records) < min_queries:
        raise CalibrationError(
            f"Calibration requires at least {min_queries} held-out benchmark images; received {len(records)}."
        )
    if not 0 < distance_threshold_km <= 1000:
        raise CalibrationError("Distance threshold must be between 0 and 1,000 km.")
    upper_edges, probabilities, counts = _fit_bins(
        records, distance_threshold_km, max_rank, bins, min_bin_samples
    )
    if np.isnan(probabilities[0]).all():
        raise CalibrationError("The benchmark did not produce enough top-ranked samples for calibration.")

    overall = _metrics(records, distance_threshold_km)
    segments = {}
    for field in ("scene", "condition"):
        values = sorted({str(record.get(field) or "unspecified") for record in records})
        segments[field] = {
            value: _metrics(
                [record for record in records if str(record.get(field) or "unspecified") == value],
                distance_threshold_km,
            )
            for value in values
        }
    report = {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "model_fingerprint": model_fingerprint,
        "distance_threshold_km": distance_threshold_km,
        "minimum_bin_samples": min_bin_samples,
        "overall": overall,
        "segments": segments,
        "limitations": [
            "Confidence is valid only for the exact visual-model fingerprint and comparable data distribution.",
            "Accuracy outside represented regions, scenes, and conditions is unknown.",
            "A calibrated candidate still requires independent corroboration.",
        ],
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        schema_version=np.asarray([CALIBRATION_SCHEMA_VERSION], dtype=np.int16),
        model_fingerprint=np.asarray([model_fingerprint]),
        distance_threshold_km=np.asarray([distance_threshold_km], dtype=np.float32),
        query_count=np.asarray([len(records)], dtype=np.int32),
        max_rank=np.asarray([max_rank], dtype=np.int16),
        bin_upper_edges=upper_edges,
        bin_probabilities=probabilities,
        bin_counts=counts,
        metrics_json=np.asarray([json.dumps(report, sort_keys=True)]),
    )
    report_output = Path(report_path)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"calibration_path": str(output.resolve()), "report_path": str(report_output.resolve()), **report}


def benchmark_and_calibrate(
    manifest_path: str | Path,
    output_path: str | Path = DEFAULT_CALIBRATION_PATH,
    report_path: str | Path = DEFAULT_REPORT_PATH,
    model_path: str | Path | None = None,
    distance_threshold_km: float = 25.0,
    min_queries: int = MIN_BENCHMARK_QUERIES,
) -> dict:
    """Evaluate held-out images, reject leakage, and build calibration data."""
    manifest = Path(manifest_path).resolve()
    selected_model = Path(model_path) if model_path else configured_model_path()
    model = _load_model(selected_model)
    if "reference_hashes" not in model:
        raise CalibrationError("Retrain GeoTrace Visual v0 before calibration so reference leakage can be checked.")
    training_hashes = {str(value) for value in model["reference_hashes"]}
    records = []
    seen_query_hashes = set()
    with manifest.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"image_path", "latitude", "longitude", "scene", "condition"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise CalibrationError("Benchmark columns must include image_path,latitude,longitude,scene,condition.")
        for line_number, row in enumerate(reader, start=2):
            image_path = Path(row["image_path"])
            if not image_path.is_absolute():
                image_path = manifest.parent / image_path
            query_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
            if query_hash in training_hashes:
                raise CalibrationError(f"Benchmark leakage detected on line {line_number}: image is in training data.")
            if query_hash in seen_query_hashes:
                raise CalibrationError(f"Duplicate benchmark image detected on line {line_number}.")
            seen_query_hashes.add(query_hash)
            try:
                latitude = float(row["latitude"])
                longitude = float(row["longitude"])
            except ValueError as error:
                raise CalibrationError(f"Invalid benchmark coordinates on line {line_number}.") from error
            prediction = predict_locations(image_path, top_k=5, model_path=selected_model)
            candidates = []
            for candidate in prediction["candidates"]:
                candidates.append({
                    "rank": len(candidates) + 1,
                    "retrieval_score": float(candidate["retrieval_score"]),
                    "distance_km": _distance_km(
                        latitude, longitude, float(candidate["latitude"]), float(candidate["longitude"])
                    ),
                })
            if not candidates:
                raise CalibrationError(f"The visual model returned no candidate on line {line_number}.")
            records.append({
                "image_sha256": query_hash,
                "scene": (row.get("scene") or "unspecified").strip(),
                "condition": (row.get("condition") or "unspecified").strip(),
                "predictions": candidates,
            })
    return build_calibration_from_records(
        records=records,
        model_fingerprint=_model_fingerprint(selected_model),
        output_path=output_path,
        report_path=report_path,
        distance_threshold_km=distance_threshold_km,
        min_queries=min_queries,
    )


def _load_calibration(path: Path | None = None) -> dict:
    selected = path or configured_calibration_path()
    if not selected.is_file():
        raise CalibrationError("No location calibration artifact is available.")
    try:
        with np.load(selected, allow_pickle=False) as archive:
            if int(archive["schema_version"][0]) != CALIBRATION_SCHEMA_VERSION:
                raise CalibrationError("The location calibration schema is incompatible; rebuild it.")
            return {key: archive[key].copy() for key in archive.files}
    except (OSError, ValueError, KeyError) as error:
        raise CalibrationError("The location calibration artifact is invalid; rebuild it.") from error


def calibration_is_ready() -> bool:
    try:
        calibration = _load_calibration()
        return str(calibration["model_fingerprint"][0]) == _model_fingerprint(configured_model_path())
    except (CalibrationError, OSError):
        return False


def apply_location_calibration(provider_result: dict) -> dict:
    """Apply matching empirical bins, or preserve honest uncalibrated output."""
    enriched = copy.deepcopy(provider_result)
    path = configured_calibration_path()
    if not path.is_file():
        enriched["calibration"] = {
            "status": "benchmark_required",
            "calibrated": False,
            "reason": "No held-out calibration artifact is installed for this visual model.",
        }
        return enriched
    calibration = _load_calibration(path)
    expected = str(calibration["model_fingerprint"][0])
    if expected != provider_result.get("model_fingerprint"):
        enriched["calibration"] = {
            "status": "stale_model",
            "calibrated": False,
            "reason": "The benchmark belongs to a different visual-model build; recalibration is required.",
        }
        return enriched

    upper_edges = calibration["bin_upper_edges"]
    probabilities = calibration["bin_probabilities"]
    counts = calibration["bin_counts"]
    calibrated_count = 0
    for rank_index, candidate in enumerate(enriched.get("candidates", [])):
        if rank_index >= upper_edges.shape[0]:
            continue
        score = float(candidate.get("retrieval_score", -1))
        valid = np.flatnonzero(~np.isnan(probabilities[rank_index]))
        if not len(valid):
            continue
        selected_bin = int(valid[-1])
        for bin_index in valid:
            if score <= float(upper_edges[rank_index, bin_index]):
                selected_bin = int(bin_index)
                break
        confidence = float(probabilities[rank_index, selected_bin])
        candidate["confidence"] = round(confidence, 4)
        candidate["calibrated"] = True
        candidate["calibration_samples"] = int(counts[rank_index, selected_bin])
        candidate["verification_status"] = (
            "calibrated_candidate_needs_corroboration"
            if confidence >= 0.6 else "calibrated_low_confidence_abstain"
        )
        calibrated_count += 1

    report = json.loads(str(calibration["metrics_json"][0]))
    enriched["calibration"] = {
        "status": "active" if calibrated_count else "insufficient_rank_coverage",
        "calibrated": bool(calibrated_count),
        "model_fingerprint": expected,
        "distance_threshold_km": float(calibration["distance_threshold_km"][0]),
        "query_count": int(calibration["query_count"][0]),
        "overall": report["overall"],
        "segments": report["segments"],
        "reason": None if calibrated_count else "No benchmark bin covers the returned candidate ranks.",
    }
    return enriched
