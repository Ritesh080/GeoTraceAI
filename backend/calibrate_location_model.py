"""Benchmark GeoTrace Visual v0 on held-out images and build confidence calibration."""
from __future__ import annotations

import argparse
import json

from backend.location_calibration import (
    DEFAULT_CALIBRATION_PATH,
    DEFAULT_REPORT_PATH,
    benchmark_and_calibrate,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="Held-out benchmark CSV")
    parser.add_argument("--output", default=str(DEFAULT_CALIBRATION_PATH))
    parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--distance-km", type=float, default=25.0)
    arguments = parser.parse_args()
    result = benchmark_and_calibrate(
        manifest_path=arguments.manifest,
        output_path=arguments.output,
        report_path=arguments.report,
        distance_threshold_km=arguments.distance_km,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
