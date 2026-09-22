"""First-party, local visual-geolocation model for GeoTrace AI.

The model is a transparent nearest-neighbour image index trained from a CSV of
location-labelled reference images. It makes no network calls and never sends
submitted images or descriptors outside the GeoTrace backend.
"""
from __future__ import annotations

import csv
import hashlib
import os
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


MODEL_SCHEMA_VERSION = 1
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "models" / "geotrace_visual_v0.npz"


class LocalVisualModelError(RuntimeError):
    """The local visual model could not be trained, loaded, or queried."""


class LocalVisualModelNotTrained(LocalVisualModelError):
    """No trained local model is available yet."""


def configured_model_path() -> Path:
    configured = os.getenv("GEOTRACE_VISUAL_MODEL_PATH", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_MODEL_PATH


def is_trained() -> bool:
    return configured_model_path().is_file()


def _image_array(image_path: str | Path) -> np.ndarray:
    try:
        with Image.open(image_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((512, 512), Image.Resampling.LANCZOS)
            return np.asarray(image, dtype=np.uint8)
    except (OSError, ValueError) as error:
        raise LocalVisualModelError(f"Could not read training image: {image_path}") from error


def extract_descriptor(image_path: str | Path) -> np.ndarray:
    """Extract a compact scene descriptor using only bundled OpenCV/NumPy."""
    rgb = _image_array(image_path)
    resized = cv2.resize(rgb, (256, 256), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(resized, cv2.COLOR_RGB2HSV)

    histogram_parts = []
    for channel, bins, value_range in ((0, 24, (0, 180)), (1, 16, (0, 256)), (2, 16, (0, 256))):
        histogram = cv2.calcHist([hsv], [channel], None, [bins], value_range).flatten()
        histogram_parts.append(histogram / max(float(histogram.sum()), 1.0))

    spatial_parts = []
    for row in range(4):
        for column in range(4):
            cell = resized[row * 64 : (row + 1) * 64, column * 64 : (column + 1) * 64]
            spatial_parts.extend(cell.mean(axis=(0, 1)) / 255.0)
            spatial_parts.extend(cell.std(axis=(0, 1)) / 255.0)

    gray = cv2.cvtColor(resized, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    gradient_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude, angle = cv2.cartToPolar(gradient_x, gradient_y, angleInDegrees=True)
    orientation_histogram, _ = np.histogram(angle, bins=18, range=(0, 360), weights=magnitude)
    orientation_histogram = orientation_histogram / max(float(orientation_histogram.sum()), 1.0)

    low_resolution = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
    frequency = cv2.dct(low_resolution)[:8, :8].flatten()
    frequency[0] = 0.0
    frequency = frequency / max(float(np.linalg.norm(frequency)), 1e-8)

    descriptor = np.concatenate(
        [*histogram_parts, np.asarray(spatial_parts), orientation_histogram, frequency]
    ).astype(np.float32)
    return descriptor / max(float(np.linalg.norm(descriptor)), 1e-8)


def train_from_manifest(manifest_path: str | Path, output_path: str | Path) -> dict:
    """Build a local reference model from a labelled CSV manifest."""
    manifest = Path(manifest_path).resolve()
    if not manifest.is_file():
        raise LocalVisualModelError("Training manifest was not found.")

    features = []
    labels = []
    latitudes = []
    longitudes = []
    precision_tiers = []
    reference_hashes = []
    with manifest.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"image_path", "label", "latitude", "longitude"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise LocalVisualModelError(
                "Manifest columns must include image_path,label,latitude,longitude."
            )
        for line_number, row in enumerate(reader, start=2):
            image_path = Path(row["image_path"])
            if not image_path.is_absolute():
                image_path = manifest.parent / image_path
            try:
                latitude = float(row["latitude"])
                longitude = float(row["longitude"])
            except (TypeError, ValueError) as error:
                raise LocalVisualModelError(f"Invalid coordinates on manifest line {line_number}.") from error
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise LocalVisualModelError(f"Coordinates are out of range on manifest line {line_number}.")
            label = row["label"].strip()
            if not label:
                raise LocalVisualModelError(f"Location label is empty on manifest line {line_number}.")
            features.append(extract_descriptor(image_path))
            reference_hashes.append(hashlib.sha256(image_path.read_bytes()).hexdigest())
            labels.append(label)
            latitudes.append(latitude)
            longitudes.append(longitude)
            precision_tiers.append((row.get("precision_tier") or "reference_area").strip())

    if len(features) < 2:
        raise LocalVisualModelError("Add at least two labelled reference images before training.")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        schema_version=np.asarray([MODEL_SCHEMA_VERSION], dtype=np.int16),
        features=np.stack(features),
        labels=np.asarray(labels),
        latitudes=np.asarray(latitudes, dtype=np.float64),
        longitudes=np.asarray(longitudes, dtype=np.float64),
        precision_tiers=np.asarray(precision_tiers),
        reference_hashes=np.asarray(reference_hashes),
    )
    return {
        "model_path": str(output.resolve()),
        "reference_images": len(features),
        "locations": len(set(zip(labels, latitudes, longitudes))),
        "descriptor_dimensions": int(features[0].shape[0]),
    }


def _load_model(model_path: Path) -> dict:
    if not model_path.is_file():
        raise LocalVisualModelNotTrained(
            "GeoTrace's local visual model needs training data before visual geolocation can run."
        )
    try:
        with np.load(model_path, allow_pickle=False) as archive:
            schema_version = int(archive["schema_version"][0])
            if schema_version != MODEL_SCHEMA_VERSION:
                raise LocalVisualModelError("The local model schema is incompatible; retrain it.")
            return {key: archive[key].copy() for key in archive.files}
    except (OSError, ValueError, KeyError) as error:
        raise LocalVisualModelError("The local visual model is invalid; retrain it.") from error


def predict_locations(
    image_path: str | Path,
    top_k: int = 3,
    model_path: str | Path | None = None,
) -> dict:
    """Return ranked locations from the locally trained reference index."""
    selected_model_path = Path(model_path) if model_path else configured_model_path()
    model = _load_model(selected_model_path)
    query = extract_descriptor(image_path)
    features = model["features"].astype(np.float32)
    similarities = features @ query

    grouped: dict[tuple, list[float]] = defaultdict(list)
    for index in np.argsort(similarities)[::-1][: min(50, len(similarities))]:
        key = (
            str(model["labels"][index]),
            float(model["latitudes"][index]),
            float(model["longitudes"][index]),
            str(model["precision_tiers"][index]),
        )
        grouped[key].append(float(similarities[index]))

    ranked = sorted(
        grouped.items(),
        key=lambda item: (max(item[1]), sum(item[1][:3]) / min(3, len(item[1]))),
        reverse=True,
    )[: max(1, min(top_k, 10))]
    model_fingerprint = hashlib.sha256(selected_model_path.read_bytes()).hexdigest()[:12]
    source_group = f"geotrace_visual_model:{model_fingerprint}"
    candidates = []
    for rank, ((label, latitude, longitude, precision_tier), scores) in enumerate(ranked, start=1):
        similarity = max(scores)
        candidates.append(
            {
                "id": f"geotrace_visual_candidate_{rank}",
                "label": label,
                "latitude": latitude,
                "longitude": longitude,
                "precision_tier": precision_tier,
                "basis": "GeoTrace local visual similarity model",
                "provider": "GeoTrace Visual v0",
                "source_group": source_group,
                "confidence": None,
                "calibrated": False,
                "retrieval_score": round(similarity, 6),
                "reference_matches": len(scores),
                "supports": [
                    {
                        "evidence_id": f"local_visual_similarity_{rank}",
                        "summary": f"Nearest reference similarity: {similarity:.3f} across {len(scores)} matching reference image(s).",
                        "source_group": source_group,
                    }
                ],
                "contradictions": [],
                "verification_status": "experimental_local_model",
            }
        )
    return {
        "model": "GeoTrace Visual v0",
        "model_fingerprint": model_fingerprint,
        "reference_images": int(len(features)),
        "reference_hashes_available": "reference_hashes" in model,
        "candidates": candidates,
    }
