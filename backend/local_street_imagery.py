"""First-party street-level imagery comparison for GeoTrace AI.

The runtime compares an evidence image with a locally built, licensed reference
index. It never sends the evidence image or its descriptor to an external
service. Similarity scores are retrieval signals, not location probabilities.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import os
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

from backend.local_visual_model import extract_descriptor


STREET_SCHEMA_VERSION = 1
DEFAULT_STREET_INDEX_PATH = Path(__file__).resolve().parent / "models" / "geotrace_street_v0.npz"
EARTH_RADIUS_KM = 6371.0088
POSSIBLE_SIMILARITY = 0.82
STRONG_SIMILARITY = 0.92


class LocalStreetImageryError(RuntimeError):
    """The street reference index could not be built, loaded, or queried."""


class LocalStreetImageryNotBuilt(LocalStreetImageryError):
    """No local street-level imagery index is available."""


def configured_street_index_path() -> Path:
    configured = os.getenv("GEOTRACE_STREET_INDEX_PATH", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_STREET_INDEX_PATH


def is_built() -> bool:
    return configured_street_index_path().is_file()


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _distance_km(latitude: float, longitude: float, latitudes: np.ndarray, longitudes: np.ndarray) -> np.ndarray:
    query_latitude = radians(latitude)
    query_longitude = radians(longitude)
    indexed_latitudes = np.radians(latitudes)
    indexed_longitudes = np.radians(longitudes)
    delta_latitude = indexed_latitudes - query_latitude
    delta_longitude = indexed_longitudes - query_longitude
    haversine = (
        np.sin(delta_latitude / 2) ** 2
        + cos(query_latitude) * np.cos(indexed_latitudes) * np.sin(delta_longitude / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(np.clip(haversine, 0, 1)))


def build_street_index(manifest_path: str | Path, output_path: str | Path) -> dict:
    """Build a local reference index from a provenance-preserving CSV manifest."""
    manifest = Path(manifest_path).resolve()
    if not manifest.is_file():
        raise LocalStreetImageryError("Street imagery manifest was not found.")

    features: list[np.ndarray] = []
    columns: dict[str, list] = {
        "reference_ids": [], "labels": [], "latitudes": [], "longitudes": [],
        "headings": [], "source_urls": [], "licenses": [], "attributions": [],
        "captured_at": [],
    }
    with manifest.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "image_path", "reference_id", "label", "latitude", "longitude",
            "source_url", "license", "attribution",
        }
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise LocalStreetImageryError(
                "Manifest columns must include image_path,reference_id,label,latitude,longitude,source_url,license,attribution."
            )
        for line_number, row in enumerate(reader, start=2):
            image_path = Path(row["image_path"])
            if not image_path.is_absolute():
                image_path = manifest.parent / image_path
            try:
                latitude = float(row["latitude"])
                longitude = float(row["longitude"])
                heading = float(row["heading"]) if (row.get("heading") or "").strip() else np.nan
            except (TypeError, ValueError) as error:
                raise LocalStreetImageryError(f"Invalid numeric value on manifest line {line_number}.") from error
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise LocalStreetImageryError(f"Coordinates are out of range on manifest line {line_number}.")
            reference_id = (row.get("reference_id") or "").strip()
            label = (row.get("label") or "").strip()
            source_url = (row.get("source_url") or "").strip()
            license_name = (row.get("license") or "").strip()
            attribution = (row.get("attribution") or "").strip()
            if not all((reference_id, label, license_name, attribution)):
                raise LocalStreetImageryError(f"Required provenance is missing on manifest line {line_number}.")
            if source_url and not _valid_url(source_url):
                raise LocalStreetImageryError(f"Source URL is invalid on manifest line {line_number}.")
            features.append(extract_descriptor(image_path))
            columns["reference_ids"].append(reference_id)
            columns["labels"].append(label)
            columns["latitudes"].append(latitude)
            columns["longitudes"].append(longitude)
            columns["headings"].append(heading)
            columns["source_urls"].append(source_url)
            columns["licenses"].append(license_name)
            columns["attributions"].append(attribution)
            columns["captured_at"].append((row.get("captured_at") or "").strip())

    if not features:
        raise LocalStreetImageryError("Add at least one licensed street reference image before building the index.")
    if len(columns["reference_ids"]) != len(set(columns["reference_ids"])):
        raise LocalStreetImageryError("Each street reference_id must be unique.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        schema_version=np.asarray([STREET_SCHEMA_VERSION], dtype=np.int16),
        features=np.stack(features).astype(np.float32),
        reference_ids=np.asarray(columns["reference_ids"]),
        labels=np.asarray(columns["labels"]),
        latitudes=np.asarray(columns["latitudes"], dtype=np.float64),
        longitudes=np.asarray(columns["longitudes"], dtype=np.float64),
        headings=np.asarray(columns["headings"], dtype=np.float32),
        source_urls=np.asarray(columns["source_urls"]),
        licenses=np.asarray(columns["licenses"]),
        attributions=np.asarray(columns["attributions"]),
        captured_at=np.asarray(columns["captured_at"]),
    )
    return {
        "index_path": str(output.resolve()),
        "reference_images": len(features),
        "locations": len(set(zip(columns["latitudes"], columns["longitudes"]))),
    }


def _load_index() -> tuple[dict, Path]:
    path = configured_street_index_path()
    if not path.is_file():
        raise LocalStreetImageryNotBuilt(
            "Build GeoTrace's licensed street-image reference index before running street comparison."
        )
    try:
        with np.load(path, allow_pickle=False) as archive:
            if int(archive["schema_version"][0]) != STREET_SCHEMA_VERSION:
                raise LocalStreetImageryError("The street imagery index is incompatible; rebuild it.")
            return {key: archive[key].copy() for key in archive.files}, path
    except (OSError, ValueError, KeyError) as error:
        raise LocalStreetImageryError("The street imagery index is invalid; rebuild it.") from error


def compare_street_imagery(
    image_path: str | Path,
    osint: dict,
    radius_km: float | None = None,
    matches_per_candidate: int = 3,
) -> dict:
    """Compare an image with licensed references near each coordinate candidate."""
    index, index_path = _load_index()
    enriched = copy.deepcopy(osint)
    query = extract_descriptor(image_path)
    features = index["features"].astype(np.float32)
    similarities = features @ query
    search_radius = radius_km or float(os.getenv("GEOTRACE_STREET_RADIUS_KM", "10"))
    if not 0 < search_radius <= 100:
        raise LocalStreetImageryError("Street comparison radius must be between 0 and 100 km.")

    records = []
    strong_match = False
    possible_match = False
    for candidate in enriched.get("candidates", []):
        latitude = candidate.get("latitude")
        longitude = candidate.get("longitude")
        if not isinstance(latitude, (int, float)) or isinstance(latitude, bool):
            continue
        if not isinstance(longitude, (int, float)) or isinstance(longitude, bool):
            continue
        distances = _distance_km(
            float(latitude), float(longitude), index["latitudes"], index["longitudes"]
        )
        nearby = np.flatnonzero(distances <= search_radius)
        if not len(nearby):
            records.append({
                "candidate_id": candidate["id"],
                "status": "no_local_street_coverage",
                "radius_km": search_radius,
                "matches": [],
            })
            continue

        ordered = nearby[np.argsort(similarities[nearby])[::-1]][: max(1, min(matches_per_candidate, 10))]
        matches = []
        for reference_index in ordered:
            similarity = float(similarities[reference_index])
            reference_id = str(index["reference_ids"][reference_index])
            source_group = f"street_reference:{reference_id}"
            matches.append({
                "reference_id": reference_id,
                "label": str(index["labels"][reference_index]),
                "latitude": float(index["latitudes"][reference_index]),
                "longitude": float(index["longitudes"][reference_index]),
                "heading": None if np.isnan(index["headings"][reference_index]) else float(index["headings"][reference_index]),
                "distance_km": round(float(distances[reference_index]), 3),
                "similarity": round(similarity, 4),
                "source_url": str(index["source_urls"][reference_index]),
                "license": str(index["licenses"][reference_index]),
                "attribution": str(index["attributions"][reference_index]),
                "captured_at": str(index["captured_at"][reference_index]),
                "source_group": source_group,
            })

        best = matches[0]
        if best["similarity"] >= STRONG_SIMILARITY:
            status = "strong_street_similarity_for_review"
            candidate["verification_status"] = "street_imagery_strong_similarity"
            strong_match = True
        elif best["similarity"] >= POSSIBLE_SIMILARITY:
            status = "possible_street_similarity_for_review"
            candidate["verification_status"] = "street_imagery_possible_similarity"
            possible_match = True
        else:
            status = "street_imagery_not_supportive"

        if status != "street_imagery_not_supportive":
            candidate.setdefault("supports", []).append({
                "evidence_id": f"street_match_{candidate['id']}_{best['reference_id']}",
                "summary": (
                    f"Local street reference {best['reference_id']} is {best['distance_km']} km from the "
                    f"candidate and has visual similarity {best['similarity']:.3f}. Manual review is required."
                ),
                "source_group": best["source_group"],
                "evidence_role": "independent_street_reference",
            })
        records.append({
            "candidate_id": candidate["id"],
            "status": status,
            "radius_km": search_radius,
            "matches": matches,
        })

    fingerprint = hashlib.sha256(index_path.read_bytes()).hexdigest()[:12]
    enriched["street_imagery_comparison"] = {
        "status": "complete" if records else "no_coordinate_candidates",
        "mode": "local_licensed_reference_index",
        "engine": "GeoTrace Street Compare v0",
        "index_fingerprint": fingerprint,
        "reference_images": int(len(features)),
        "records": records,
        "method_note": (
            "Similarity is a retrieval signal, not a location probability. Low similarity is not treated as a "
            "contradiction because viewpoint, season, lighting, and scene changes can differ."
        ),
    }
    if records:
        enriched["privacy"]["note"] += (
            " Street comparison ran against a local licensed reference index; the evidence image and its "
            "descriptor were not sent to an imagery provider."
        )
        source_groups = {
            support.get("source_group")
            for candidate in enriched.get("candidates", [])
            for support in candidate.get("supports", [])
            if support.get("source_group")
        }
        source_groups.update(
            candidate.get("source_group") for candidate in enriched.get("candidates", [])
            if candidate.get("source_group")
        )
        enriched["uncertainty"]["independent_source_groups"] = len(source_groups)
        if strong_match:
            enriched["uncertainty"]["outcome"] = "candidate_partially_corroborated"
        elif possible_match:
            enriched["uncertainty"]["outcome"] = "street_similarity_needs_review"
    return enriched
