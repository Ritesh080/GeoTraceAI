"""Local reverse-image and source-provenance matching for GeoTrace AI.

The index stores exact hashes, perceptual hashes, crop-tolerant ORB features,
and explicit source records. Runtime matching is offline and never uploads the
submitted image or any derived descriptor.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import cv2
import numpy as np
from PIL import Image, ImageOps


PROVENANCE_SCHEMA_VERSION = 1
MAX_ORB_FEATURES = 128
DEFAULT_PROVENANCE_INDEX_PATH = Path(__file__).resolve().parent / "models" / "geotrace_provenance_v0.npz"
BIT_COUNTS = np.asarray([int(value).bit_count() for value in range(256)], dtype=np.uint8)


class LocalProvenanceError(RuntimeError):
    """The local provenance index could not be built, loaded, or queried."""


class LocalProvenanceNotBuilt(LocalProvenanceError):
    """No local source-provenance index is available."""


def configured_provenance_index_path() -> Path:
    configured = os.getenv("GEOTRACE_PROVENANCE_INDEX_PATH", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_PROVENANCE_INDEX_PATH


def is_built() -> bool:
    return configured_provenance_index_path().is_file()


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _valid_timestamp(value: str) -> bool:
    if not value:
        return True
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _image_data(image_path: str | Path) -> tuple[np.ndarray, bytes, str, str]:
    path = Path(image_path)
    try:
        file_bytes = path.read_bytes()
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            rgb = np.asarray(image, dtype=np.uint8)
    except (OSError, ValueError) as error:
        raise LocalProvenanceError(f"Could not read provenance image: {path}") from error
    pixel_hash = hashlib.sha256(
        rgb.shape[0].to_bytes(4, "big") + rgb.shape[1].to_bytes(4, "big") + rgb.tobytes()
    ).hexdigest()
    return rgb, file_bytes, hashlib.sha256(file_bytes).hexdigest(), pixel_hash


def _perceptual_hash(rgb: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    compact = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    frequency = cv2.dct(compact)[:8, :8]
    threshold = float(np.median(frequency.flatten()[1:]))
    bits = (frequency.flatten() > threshold).astype(np.uint8)
    return np.packbits(bits)


def _orb_features(rgb: np.ndarray) -> tuple[np.ndarray, int]:
    height, width = rgb.shape[:2]
    scale = min(1.0, 640 / max(height, width))
    if scale < 1:
        rgb = cv2.resize(rgb, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    detector = cv2.ORB_create(nfeatures=MAX_ORB_FEATURES, fastThreshold=12)
    _, descriptors = detector.detectAndCompute(gray, None)
    padded = np.zeros((MAX_ORB_FEATURES, 32), dtype=np.uint8)
    if descriptors is None:
        return padded, 0
    count = min(len(descriptors), MAX_ORB_FEATURES)
    padded[:count] = descriptors[:count]
    return padded, count


def extract_provenance_features(image_path: str | Path) -> dict:
    rgb, _, file_sha256, pixel_sha256 = _image_data(image_path)
    orb, orb_count = _orb_features(rgb)
    return {
        "file_sha256": file_sha256,
        "pixel_sha256": pixel_sha256,
        "phash": _perceptual_hash(rgb),
        "orb": orb,
        "orb_count": orb_count,
    }


def build_provenance_index(manifest_path: str | Path, output_path: str | Path) -> dict:
    """Build a local source index from images with explicit provenance records."""
    manifest = Path(manifest_path).resolve()
    if not manifest.is_file():
        raise LocalProvenanceError("Source-provenance manifest was not found.")

    feature_rows = []
    metadata: dict[str, list[str]] = {
        "reference_ids": [], "titles": [], "source_names": [], "source_urls": [],
        "published_at": [], "licenses": [], "attributions": [], "origin_groups": [],
    }
    manifest_keys = {
        "reference_ids": "reference_id",
        "titles": "title",
        "source_names": "source_name",
        "source_urls": "source_url",
        "published_at": "published_at",
        "licenses": "license",
        "attributions": "attribution",
        "origin_groups": "origin_group",
    }
    with manifest.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "image_path", "reference_id", "title", "source_name", "source_url",
            "published_at", "license", "attribution", "origin_group",
        }
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise LocalProvenanceError(
                "Manifest columns must include image_path,reference_id,title,source_name,source_url,published_at,license,attribution,origin_group."
            )
        for line_number, row in enumerate(reader, start=2):
            image_path = Path(row["image_path"])
            if not image_path.is_absolute():
                image_path = manifest.parent / image_path
            values = {key: (row.get(manifest_keys[key]) or "").strip() for key in metadata}
            if not all(values.values()):
                raise LocalProvenanceError(f"Required provenance is missing on manifest line {line_number}.")
            if not _valid_url(values["source_urls"]):
                raise LocalProvenanceError(f"Source URL is invalid on manifest line {line_number}.")
            if not _valid_timestamp(values["published_at"]):
                raise LocalProvenanceError(f"Publication time is invalid on manifest line {line_number}.")
            feature_rows.append(extract_provenance_features(image_path))
            for key in metadata:
                metadata[key].append(values[key])

    if not feature_rows:
        raise LocalProvenanceError("Add at least one licensed source image before building the index.")
    if len(metadata["reference_ids"]) != len(set(metadata["reference_ids"])):
        raise LocalProvenanceError("Each provenance reference_id must be unique.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        schema_version=np.asarray([PROVENANCE_SCHEMA_VERSION], dtype=np.int16),
        file_sha256=np.asarray([row["file_sha256"] for row in feature_rows]),
        pixel_sha256=np.asarray([row["pixel_sha256"] for row in feature_rows]),
        phashes=np.stack([row["phash"] for row in feature_rows]),
        orb_descriptors=np.stack([row["orb"] for row in feature_rows]),
        orb_counts=np.asarray([row["orb_count"] for row in feature_rows], dtype=np.int16),
        **{key: np.asarray(values) for key, values in metadata.items()},
    )
    return {
        "index_path": str(output.resolve()),
        "reference_images": len(feature_rows),
        "origin_groups": len(set(metadata["origin_groups"])),
    }


def _load_index() -> tuple[dict, Path]:
    path = configured_provenance_index_path()
    if not path.is_file():
        raise LocalProvenanceNotBuilt(
            "Build GeoTrace's licensed source-provenance index before running reverse-image matching."
        )
    try:
        with np.load(path, allow_pickle=False) as archive:
            if int(archive["schema_version"][0]) != PROVENANCE_SCHEMA_VERSION:
                raise LocalProvenanceError("The provenance index is incompatible; rebuild it.")
            return {key: archive[key].copy() for key in archive.files}, path
    except (OSError, ValueError, KeyError) as error:
        raise LocalProvenanceError("The provenance index is invalid; rebuild it.") from error


def _orb_support(query: np.ndarray, query_count: int, reference: np.ndarray, reference_count: int) -> tuple[int, float]:
    if query_count < 2 or reference_count < 2:
        return 0, 0.0
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = matcher.knnMatch(query[:query_count], reference[:reference_count], k=2)
    good = sum(1 for pair in pairs if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance)
    return good, good / max(1, min(query_count, reference_count))


def match_source_provenance(image_path: str | Path, osint: dict, limit: int = 12) -> dict:
    """Find exact and near-duplicate indexed sources and construct a timeline."""
    index, index_path = _load_index()
    query = extract_provenance_features(image_path)
    xor = np.bitwise_xor(index["phashes"], query["phash"])
    phash_distances = BIT_COUNTS[xor].sum(axis=1)
    matches = []
    for position in range(len(index["reference_ids"])):
        exact_file = str(index["file_sha256"][position]) == query["file_sha256"]
        exact_pixels = str(index["pixel_sha256"][position]) == query["pixel_sha256"]
        phash_distance = int(phash_distances[position])
        orb_matches, orb_ratio = _orb_support(
            query["orb"], query["orb_count"],
            index["orb_descriptors"][position], int(index["orb_counts"][position]),
        )
        if exact_file:
            match_type, strength = "exact_file_match", 4
        elif exact_pixels:
            match_type, strength = "exact_pixel_match", 3
        elif phash_distance <= 6:
            match_type, strength = "strong_near_duplicate", 2
        elif phash_distance <= 14 or (orb_matches >= 15 and orb_ratio >= 0.1):
            match_type, strength = "likely_edited_or_cropped_copy", 1
        elif phash_distance <= 22 or orb_matches >= 8:
            match_type, strength = "possible_visual_match", 0
        else:
            continue
        matches.append({
            "reference_id": str(index["reference_ids"][position]),
            "title": str(index["titles"][position]),
            "source_name": str(index["source_names"][position]),
            "source_url": str(index["source_urls"][position]),
            "published_at": str(index["published_at"][position]),
            "license": str(index["licenses"][position]),
            "attribution": str(index["attributions"][position]),
            "origin_group": str(index["origin_groups"][position]),
            "match_type": match_type,
            "perceptual_distance": phash_distance,
            "perceptual_similarity": round(1 - phash_distance / 64, 4),
            "local_feature_matches": orb_matches,
            "local_feature_ratio": round(orb_ratio, 4),
            "_strength": strength,
        })

    matches.sort(
        key=lambda item: (-item["_strength"], item["perceptual_distance"], -item["local_feature_matches"], item["published_at"])
    )
    matches = matches[: max(1, min(limit, 50))]
    for match in matches:
        match.pop("_strength", None)
    timeline = sorted(matches, key=lambda item: item["published_at"])
    for sequence, entry in enumerate(timeline, start=1):
        entry["timeline_role"] = "earliest_indexed_occurrence" if sequence == 1 else "later_indexed_occurrence"

    enriched = copy.deepcopy(osint)
    fingerprint = hashlib.sha256(index_path.read_bytes()).hexdigest()[:12]
    origin_groups = sorted({match["origin_group"] for match in matches})
    enriched["source_provenance"] = {
        "status": "matches_found" if matches else "no_indexed_match",
        "engine": "GeoTrace Provenance v0",
        "mode": "local_exact_perceptual_and_feature_index",
        "index_fingerprint": fingerprint,
        "reference_images": int(len(index["reference_ids"])),
        "matches": matches,
        "timeline": timeline,
        "independent_origin_groups": len(origin_groups),
        "method_note": (
            "The timeline shows the earliest occurrence in this local index, not the first publication on the internet. "
            "Similarity values are retrieval signals and every non-exact match requires human review."
        ),
    }
    enriched["privacy"]["note"] += (
        " Reverse-image matching ran against GeoTrace's local source index; the evidence image and descriptors were not uploaded."
    )
    if matches:
        enriched.setdefault("clues", []).append({
            "id": "local_provenance_matches",
            "kind": "source_provenance",
            "label": "Indexed source matches",
            "value": f"{len(matches)} match(es) across {len(origin_groups)} origin group(s)",
            "source_group": "geotrace_provenance_index",
        })
        existing_groups = {group.get("id") for group in enriched.get("dependency_groups", [])}
        for origin_group in origin_groups:
            if origin_group in existing_groups:
                continue
            member_ids = [match["reference_id"] for match in matches if match["origin_group"] == origin_group]
            enriched.setdefault("dependency_groups", []).append({
                "id": origin_group,
                "label": "Indexed publication family",
                "member_ids": member_ids,
                "explanation": "These matching publications share one declared origin group and do not count as independent sources.",
            })
        enriched["uncertainty"]["abstention_reasons"] = [
            reason for reason in enriched["uncertainty"].get("abstention_reasons", [])
            if "Reverse-image matches require" not in reason
        ]
    return enriched
