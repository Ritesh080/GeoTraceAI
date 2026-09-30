"""Build GeoTrace's local India place-name index from the GeoNames dump."""

from __future__ import annotations

import argparse
import re
import sqlite3
import tempfile
import unicodedata
import urllib.request
import zipfile
from pathlib import Path


SOURCE_URL = "https://download.geonames.org/export/dump/IN.zip"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = REPOSITORY_ROOT / "datasets" / "geonames"
ARCHIVE_PATH = DATA_DIRECTORY / "IN.zip"
DATABASE_PATH = DATA_DIRECTORY / "india_places.sqlite3"


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))


def _download() -> None:
    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {SOURCE_URL}")
    with tempfile.NamedTemporaryFile(
        dir=DATA_DIRECTORY, prefix="IN-", suffix=".zip", delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        urllib.request.urlretrieve(SOURCE_URL, temporary_path)
        temporary_path.replace(ARCHIVE_PATH)
    finally:
        temporary_path.unlink(missing_ok=True)


def build_index(*, refresh: bool = False) -> Path:
    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    if refresh or not ARCHIVE_PATH.is_file():
        _download()

    temporary_database = DATABASE_PATH.with_suffix(".sqlite3.tmp")
    temporary_database.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary_database)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode = OFF;
            PRAGMA synchronous = OFF;
            CREATE TABLE places (
                geoname_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                feature_class TEXT,
                feature_code TEXT,
                population INTEGER NOT NULL,
                timezone TEXT
            );
            CREATE TABLE names (
                place_id INTEGER NOT NULL,
                alias TEXT NOT NULL,
                compact TEXT NOT NULL,
                kind TEXT NOT NULL,
                UNIQUE(place_id, alias)
            );
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        place_batch = []
        name_batch = []
        with zipfile.ZipFile(ARCHIVE_PATH) as archive:
            with archive.open("IN.txt") as source:
                for raw_line in source:
                    columns = raw_line.decode("utf-8").rstrip("\n").split("\t")
                    if len(columns) < 19:
                        continue
                    place_id = int(columns[0])
                    primary_name = columns[1]
                    place_batch.append(
                        (
                            place_id,
                            primary_name,
                            float(columns[4]),
                            float(columns[5]),
                            columns[6],
                            columns[7],
                            int(columns[14] or 0),
                            columns[17],
                        )
                    )
                    aliases = [(primary_name, "primary"), (columns[2], "ascii")]
                    aliases.extend(
                        (alias, "alternate")
                        for alias in columns[3].split(",")
                        if alias
                    )
                    seen = set()
                    for alias_value, kind in aliases:
                        alias = normalize_name(alias_value)
                        if len(alias) < 3 or alias in seen:
                            continue
                        seen.add(alias)
                        name_batch.append(
                            (place_id, alias, alias.replace(" ", ""), kind)
                        )

                    if len(place_batch) >= 5000:
                        connection.executemany(
                            "INSERT INTO places VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            place_batch,
                        )
                        connection.executemany(
                            "INSERT OR IGNORE INTO names VALUES (?, ?, ?, ?)",
                            name_batch,
                        )
                        place_batch.clear()
                        name_batch.clear()

        if place_batch:
            connection.executemany(
                "INSERT INTO places VALUES (?, ?, ?, ?, ?, ?, ?, ?)", place_batch
            )
            connection.executemany(
                "INSERT OR IGNORE INTO names VALUES (?, ?, ?, ?)", name_batch
            )
        connection.executescript(
            """
            CREATE INDEX names_alias_idx ON names(alias);
            CREATE INDEX names_compact_idx ON names(compact);
            CREATE INDEX names_place_idx ON names(place_id);
            """
        )
        connection.executemany(
            "INSERT INTO metadata VALUES (?, ?)",
            [
                ("source", SOURCE_URL),
                ("license", "Creative Commons Attribution 4.0"),
                ("attribution", "GeoNames — https://www.geonames.org/"),
                ("country", "India"),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    temporary_database.replace(DATABASE_PATH)
    print(f"Created {DATABASE_PATH}")
    return DATABASE_PATH


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    options = parser.parse_args()
    build_index(refresh=options.refresh)
