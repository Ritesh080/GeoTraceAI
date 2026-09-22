"""Build GeoTrace's offline place index from GeoNames data."""
from __future__ import annotations

import argparse
import json

from backend.local_map_verification import DEFAULT_MAP_INDEX_PATH, build_map_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the GeoTrace local place index.")
    parser.add_argument("geonames_file", help="Extracted GeoNames cities*.txt file")
    parser.add_argument("--country-info", help="Optional GeoNames countryInfo.txt file")
    parser.add_argument("--output", default=str(DEFAULT_MAP_INDEX_PATH), help="Output .npz path")
    arguments = parser.parse_args()
    print(json.dumps(build_map_index(arguments.geonames_file, arguments.output, arguments.country_info), indent=2))


if __name__ == "__main__":
    main()
