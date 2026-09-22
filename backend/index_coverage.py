"""Inspect GeoTrace reference artifacts without loading untrusted pickle data."""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from backend.local_map_verification import configured_map_path
from backend.local_source_provenance import configured_provenance_index_path
from backend.local_street_imagery import configured_street_index_path
from backend.local_visual_model import configured_model_path
from backend.location_calibration import configured_calibration_path


def _iso_timestamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def _spatial(latitudes: np.ndarray, longitudes: np.ndarray) -> dict:
    if not len(latitudes):
        return {"coordinate_records": 0, "one_degree_cells": 0, "bounds": None}
    cells = {
        (math.floor(float(latitude)), math.floor(float(longitude)))
        for latitude, longitude in zip(latitudes, longitudes)
    }
    return {
        "coordinate_records": int(len(latitudes)),
        "one_degree_cells": len(cells),
        "bounds": {
            "south": round(float(np.min(latitudes)), 6),
            "west": round(float(np.min(longitudes)), 6),
            "north": round(float(np.max(latitudes)), 6),
            "east": round(float(np.max(longitudes)), 6),
        },
    }


def _missing(name: str, path: Path, purpose: str) -> dict:
    return {
        "name": name,
        "status": "not_built",
        "artifact": path.name,
        "purpose": purpose,
        "reference_count": 0,
    }


def _inspect_npz(name: str, path: Path, purpose: str, count_key: str, spatial: bool = False) -> dict:
    if not path.is_file():
        return _missing(name, path, purpose)
    try:
        with np.load(path, allow_pickle=False) as archive:
            count = int(len(archive[count_key]))
            details = _spatial(archive["latitudes"], archive["longitudes"]) if spatial else {}
            if name == "source_provenance":
                details["independent_origin_groups"] = len({str(value) for value in archive["origin_groups"]})
        return {
            "name": name,
            "status": "active",
            "artifact": path.name,
            "purpose": purpose,
            "reference_count": count,
            "fingerprint": _fingerprint(path),
            "updated_at": _iso_timestamp(path),
            **details,
        }
    except (OSError, ValueError, KeyError) as error:
        return {
            **_missing(name, path, purpose),
            "status": "invalid",
            "error": "Artifact could not be read safely.",
        }


def _inspect_calibration(path: Path) -> dict:
    if not path.is_file():
        return _missing("confidence_calibration", path, "Empirical confidence from held-out benchmarks")
    try:
        with np.load(path, allow_pickle=False) as archive:
            metrics = json.loads(str(archive["metrics_json"][0]))
            query_count = int(archive["query_count"][0])
            model_fingerprint = str(archive["model_fingerprint"][0])
        return {
            "name": "confidence_calibration",
            "status": "active",
            "artifact": path.name,
            "purpose": "Empirical confidence from held-out benchmarks",
            "reference_count": query_count,
            "query_count": query_count,
            "model_fingerprint": model_fingerprint,
            "distance_threshold_km": metrics.get("distance_threshold_km"),
            "overall": metrics.get("overall", {}),
            "fingerprint": _fingerprint(path),
            "updated_at": _iso_timestamp(path),
        }
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        return {
            **_missing("confidence_calibration", path, "Empirical confidence from held-out benchmarks"),
            "status": "invalid",
            "error": "Artifact could not be read safely.",
        }


def coverage_report(paths: dict[str, str | Path] | None = None) -> dict:
    """Return honest operational and corpus coverage for the active backend."""
    selected = paths or {}
    datasets = [
        _inspect_npz(
            "visual_geolocation",
            Path(selected.get("visual", configured_model_path())),
            "Location-labelled visual references",
            "labels",
            spatial=True,
        ),
        _inspect_npz(
            "map_context",
            Path(selected.get("map", configured_map_path())),
            "Offline populated-place context",
            "names",
            spatial=True,
        ),
        _inspect_npz(
            "street_imagery",
            Path(selected.get("street", configured_street_index_path())),
            "Licensed street-level comparison references",
            "reference_ids",
            spatial=True,
        ),
        _inspect_npz(
            "source_provenance",
            Path(selected.get("provenance", configured_provenance_index_path())),
            "Licensed publication and near-duplicate references",
            "reference_ids",
        ),
        _inspect_calibration(Path(selected.get("calibration", configured_calibration_path()))),
    ]
    active = sum(dataset["status"] == "active" for dataset in datasets)
    all_active = active == len(datasets)
    visual = datasets[0]
    calibration = datasets[-1]
    calibration_matches = (
        calibration["status"] == "active"
        and visual["status"] == "active"
        and calibration.get("model_fingerprint") == visual.get("fingerprint")
    )
    return {
        "status": "full_reference_stack" if all_active and calibration_matches else "operational_limited_coverage",
        "analysis_operational": True,
        "full_reference_coverage": bool(all_active and calibration_matches),
        "active_datasets": active,
        "total_datasets": len(datasets),
        "datasets": datasets,
        "limitations": [
            "Coverage describes indexed references, not worldwide accuracy.",
            "Unrepresented regions, scenes, and capture conditions remain unknown.",
            "Location candidates still require independent corroboration.",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "deployment_label": os.getenv("GEOTRACE_DEPLOYMENT_LABEL", "local-or-self-hosted"),
    }
