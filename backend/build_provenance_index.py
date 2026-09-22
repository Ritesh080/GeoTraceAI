"""Build GeoTrace's local reverse-image and source-provenance index."""
from __future__ import annotations

import argparse
import json

from backend.local_source_provenance import DEFAULT_PROVENANCE_INDEX_PATH, build_provenance_index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="CSV manifest containing licensed images and source records")
    parser.add_argument("--output", default=str(DEFAULT_PROVENANCE_INDEX_PATH), help="Output .npz index path")
    arguments = parser.parse_args()
    print(json.dumps(build_provenance_index(arguments.manifest, arguments.output), indent=2))


if __name__ == "__main__":
    main()
