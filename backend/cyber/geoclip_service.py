"""GeoCLIP inference for the GeoTrace image-analysis pipeline.

The heavyweight model is imported and initialized only when geolocation is
requested. This keeps validation, hashing, and EXIF extraction usable on
machines where the optional ML dependencies are not installed.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any


DEFAULT_TOP_K = 5
MAX_TOP_K = 20

_MODEL: Any | None = None
_MODEL_DEVICE: str | None = None
_MODEL_LOCK = threading.Lock()


class GeoClipUnavailableError(RuntimeError):
    """Raised when GeoCLIP cannot be imported or initialized."""


def _select_device(torch_module: Any) -> str:
    requested = os.getenv("GEOTRACE_GEOCLIP_DEVICE", "auto").strip().lower()

    if requested == "auto":
        if torch_module.cuda.is_available():
            return "cuda"
        if (
            hasattr(torch_module.backends, "mps")
            and torch_module.backends.mps.is_available()
        ):
            return "mps"
        return "cpu"

    if requested not in {"cpu", "cuda", "mps"}:
        raise GeoClipUnavailableError(
            "GEOTRACE_GEOCLIP_DEVICE must be one of: auto, cpu, cuda, mps"
        )

    if requested == "cuda" and not torch_module.cuda.is_available():
        raise GeoClipUnavailableError("CUDA was requested but is not available")
    if requested == "mps" and not (
        hasattr(torch_module.backends, "mps")
        and torch_module.backends.mps.is_available()
    ):
        raise GeoClipUnavailableError("Apple MPS was requested but is not available")

    return requested


def _get_model() -> tuple[Any, str]:
    global _MODEL, _MODEL_DEVICE

    if _MODEL is not None and _MODEL_DEVICE is not None:
        return _MODEL, _MODEL_DEVICE

    with _MODEL_LOCK:
        if _MODEL is not None and _MODEL_DEVICE is not None:
            return _MODEL, _MODEL_DEVICE

        try:
            import torch
            from geoclip import GeoCLIP
        except ImportError as exc:
            raise GeoClipUnavailableError(
                "GeoCLIP dependencies are not installed. Run "
                "`.venv/bin/python -m pip install -r backend/cyber/requirements.txt`."
            ) from exc

        device = _select_device(torch)

        try:
            model = GeoCLIP()
            model.eval()
            model.to(device)
        except Exception as exc:
            raise GeoClipUnavailableError(
                f"GeoCLIP could not be initialized: {exc}"
            ) from exc

        _MODEL = model
        _MODEL_DEVICE = device
        return _MODEL, _MODEL_DEVICE


def _format_candidates(gps_values: Any, probability_values: Any) -> list[dict]:
    coordinates = gps_values.tolist()
    probabilities = probability_values.tolist()

    return [
        {
            "rank": rank,
            "latitude": round(float(latitude), 6),
            "longitude": round(float(longitude), 6),
            # This is GeoCLIP's retrieval probability, not a calibrated
            # real-world confidence estimate.
            "score": round(float(probability), 8),
            "map_url": (
                "https://www.openstreetmap.org/"
                f"?mlat={float(latitude):.6f}&mlon={float(longitude):.6f}"
                f"#map=10/{float(latitude):.6f}/{float(longitude):.6f}"
            ),
        }
        for rank, ((latitude, longitude), probability) in enumerate(
            zip(coordinates, probabilities), start=1
        )
    ]


def geolocate_image(file_path: str, top_k: int = DEFAULT_TOP_K) -> dict:
    """Return ranked worldwide GPS candidates for an image.

    Results intentionally use ``score`` rather than ``confidence`` because the
    model probabilities are relative to its GPS gallery and are not calibrated
    estimates of how likely the real-world location is to be correct.
    """

    if not 1 <= top_k <= MAX_TOP_K:
        raise ValueError(f"top_k must be between 1 and {MAX_TOP_K}")

    image_path = Path(file_path)
    if not image_path.is_file():
        return {
            "status": "error",
            "model": "GeoCLIP",
            "reason": "Image file does not exist",
            "candidates": [],
        }

    try:
        model, device = _get_model()
        predicted_gps, predicted_probabilities = model.predict(
            str(image_path), top_k=top_k
        )
        candidates = _format_candidates(predicted_gps, predicted_probabilities)
    except GeoClipUnavailableError as exc:
        return {
            "status": "unavailable",
            "model": "GeoCLIP",
            "reason": str(exc),
            "candidates": [],
        }
    except Exception as exc:
        return {
            "status": "error",
            "model": "GeoCLIP",
            "reason": f"Inference failed: {exc}",
            "candidates": [],
        }

    return {
        "status": "success",
        "model": "GeoCLIP",
        "device": device,
        "top_k": top_k,
        "candidates": candidates,
        "score_note": (
            "Scores rank candidates within GeoCLIP's GPS gallery and should "
            "not be treated as calibrated certainty."
        ),
    }
