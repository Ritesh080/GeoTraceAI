"""Infer India location candidates from public post text and image OCR."""

from __future__ import annotations

import math
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Iterable


DATABASE_PATH = Path(__file__).resolve().parents[2] / "datasets" / "geonames" / "india_places.sqlite3"
MAX_CANDIDATES = 8
MAX_PHRASES = 4000


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))


def _candidate_phrases(text: str) -> set[str]:
    expanded = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    hashtag_values = [
        re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value.replace("_", " "))
        for value in re.findall(r"#([^\s#]+)", text)
    ]
    normalized = _normalize(expanded)
    tokens = normalized.split()
    phrases: set[str] = set()
    for size in range(1, 6):
        for start in range(0, max(len(tokens) - size + 1, 0)):
            phrase = " ".join(tokens[start : start + size])
            if len(phrase) >= 4:
                phrases.add(phrase)
            if len(phrases) >= MAX_PHRASES:
                break
        if len(phrases) >= MAX_PHRASES:
            break
    for hashtag in hashtag_values:
        normalized_hashtag = _normalize(hashtag)
        if len(normalized_hashtag) >= 3:
            phrases.add(normalized_hashtag)
            phrases.add(normalized_hashtag.replace(" ", ""))
    return phrases


def _chunks(values: list[str], size: int = 400) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _map_url(latitude: float, longitude: float) -> str:
    return (
        "https://www.openstreetmap.org/"
        f"?mlat={latitude:.6f}&mlon={longitude:.6f}"
        f"#map=11/{latitude:.6f}/{longitude:.6f}"
    )


def _explicit_coordinates(text: str) -> list[dict]:
    results = []
    pattern = re.compile(
        r"(?<!\d)(-?(?:[0-8]?\d(?:\.\d+)?|90(?:\.0+)?))\s*[,;/]\s*"
        r"(-?(?:1[0-7]\d(?:\.\d+)?|\d?\d(?:\.\d+)?|180(?:\.0+)?))(?!\d)"
    )
    for match in pattern.finditer(text):
        latitude, longitude = map(float, match.groups())
        if -90 <= latitude <= 90 and -180 <= longitude <= 180:
            results.append(
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "name": "Coordinates stated in post evidence",
                    "matched_terms": [match.group(0)],
                    "evidence_strength": 1.0,
                    "evidence_type": "explicit_coordinates",
                }
            )
    return results


def extract_text_location_candidates(context_text: str, ocr_text: str = "") -> dict:
    combined_text = "\n".join(value for value in (context_text, ocr_text) if value)
    explicit = _explicit_coordinates(combined_text)
    if not DATABASE_PATH.is_file():
        return {
            "status": "success" if explicit else "unavailable",
            "provider": "GeoTrace India Text Gazetteer",
            "reason": (
                "Local India gazetteer is not built. Run "
                "`.venv/bin/python backend/cyber/build_india_gazetteer.py`."
            ),
            "candidates": explicit,
        }

    phrases = sorted(_candidate_phrases(combined_text), key=len, reverse=True)
    if not phrases and not explicit:
        return {
            "status": "unavailable",
            "provider": "GeoTrace India Text Gazetteer",
            "reason": "No place-like text or coordinates were found",
            "candidates": [],
        }

    matches: dict[int, dict] = {}
    connection = sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        for chunk in _chunks(phrases):
            placeholders = ",".join("?" for _ in chunk)
            rows = connection.execute(
                f"""
                SELECT n.alias, n.compact, n.kind, p.*
                FROM names n JOIN places p ON p.geoname_id = n.place_id
                WHERE n.alias IN ({placeholders}) OR n.compact IN ({placeholders})
                """,
                [*chunk, *[value.replace(" ", "") for value in chunk]],
            )
            for row in rows:
                alias = row["alias"]
                token_count = len(alias.split())
                population = int(row["population"] or 0)
                if token_count == 1 and population < 50000 and row["feature_class"] not in {"A"}:
                    continue
                specificity = min(token_count / 3, 1.0)
                population_signal = min(math.log10(max(population, 1)) / 7, 1.0)
                feature_signal = 1.0 if row["feature_class"] in {"A", "P"} else 0.6
                strength = round(
                    0.45 * specificity + 0.35 * population_signal + 0.20 * feature_signal,
                    4,
                )
                existing = matches.setdefault(
                    row["geoname_id"],
                    {
                        "latitude": float(row["latitude"]),
                        "longitude": float(row["longitude"]),
                        "name": row["name"],
                        "feature_class": row["feature_class"],
                        "feature_code": row["feature_code"],
                        "population": population,
                        "timezone": row["timezone"],
                        "matched_terms": set(),
                        "evidence_strength": strength,
                        "evidence_type": "place_name_mention",
                    },
                )
                existing["matched_terms"].add(alias)
                existing["evidence_strength"] = max(
                    existing["evidence_strength"], strength
                )
    finally:
        connection.close()

    ranked = explicit + sorted(
        matches.values(),
        key=lambda item: (
            item["evidence_strength"],
            len(item["matched_terms"]),
            item["population"],
        ),
        reverse=True,
    )
    candidates = []
    for rank, item in enumerate(ranked[:MAX_CANDIDATES], start=1):
        candidate = dict(item)
        candidate["rank"] = rank
        candidate["latitude"] = round(candidate["latitude"], 6)
        candidate["longitude"] = round(candidate["longitude"], 6)
        candidate["matched_terms"] = sorted(candidate["matched_terms"])
        candidate["map_url"] = _map_url(
            candidate["latitude"], candidate["longitude"]
        )
        candidates.append(candidate)

    if not candidates:
        return {
            "status": "unavailable",
            "provider": "GeoTrace India Text Gazetteer",
            "reason": "No reliable Indian place-name match was found",
            "candidates": [],
        }
    return {
        "status": "success",
        "provider": "GeoTrace India Text Gazetteer",
        "candidates": candidates,
        "source_note": (
            "Place mentions, hashtags, and OCR text can be stale, fictional, or unrelated "
            "to where the image was captured. Treat them as leads requiring visual corroboration."
        ),
        "attribution": "Place data © GeoNames, CC BY 4.0 — https://www.geonames.org/",
    }
