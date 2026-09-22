"""Command-line trainer for the first-party GeoTrace visual model."""
from __future__ import annotations

import argparse
import json

from backend.local_visual_model import DEFAULT_MODEL_PATH, train_from_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Train GeoTrace Visual v0 from labelled images.")
    parser.add_argument("manifest", help="CSV manifest of reference images and coordinates")
    parser.add_argument("--output", default=str(DEFAULT_MODEL_PATH), help="Output .npz model path")
    arguments = parser.parse_args()
    print(json.dumps(train_from_manifest(arguments.manifest, arguments.output), indent=2))


if __name__ == "__main__":
    main()
