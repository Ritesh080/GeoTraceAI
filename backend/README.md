# GeoTrace AI backend bridge

This directory contains a snapshot of `backend/cyber` from `Ritesh080/GeoTraceAI` commit `9ab9438a824bb67dbce805020483f5e6d6e2cf7f`, plus `api.py`, a FastAPI adapter for the website.

Requirements: Python 3.11+, ExifTool, and libmagic. From the website project root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

Set `GEOTRACE_ALLOWED_ORIGINS` to a comma-separated list before starting the API in another environment. The API accepts JPG, PNG, and WebP files up to 20 MB, writes a temporary file for the existing pipeline, deletes it after analysis, and does not persist uploads.

Endpoints:

- `GET /health`
- `GET /ready` for operational readiness without pretending optional indexes are present
- `GET /coverage` for reference counts, spatial coverage, fingerprints, and calibration status
- `GET /instagram/status` for enabled/authenticated import status without exposing session data
- `GET /capabilities`
- `POST /analyze` with multipart field `file` and optional booleans `visual_geolocation`, `map_verification`, `street_imagery_comparison`, and `source_provenance`
- `POST /analyze/instagram` for one consented, permitted single-image post

`POST /analyze` includes an `osint` object with manual search and map-verification actions, ranked candidates, supports and contradictions, source-dependency groups, privacy state, and an uncertainty decision. Without an explicitly selected external provider, images are never uploaded to OSINT providers by this API.

To enable first-party visual geolocation, train GeoTrace Visual v0 from a CSV of labelled reference images. Start with `backend/training_manifest.example.csv` and run `.venv/bin/python -m backend.train_visual_model path/to/manifest.csv`. When `visual_geolocation=true`, the backend compares the submitted image with that local model; it makes no external request. Visual similarity is not a calibrated probability and must be corroborated before use.

To enable offline map context, build `backend/models/geotrace_places_v0.npz` from a GeoNames cities dump using `.venv/bin/python -m backend.build_map_index path/to/cities5000.txt --country-info path/to/countryInfo.txt`. Pass `map_verification=true` with `/analyze` to compare candidate coordinates, labels, and OCR against the local index. GeoTrace keeps map-context consistency distinct from independent visual proof.

To enable street-level comparison, create a provenance-complete CSV from `backend/street_manifest.example.csv`, then run `.venv/bin/python -m backend.build_street_index path/to/street_manifest.csv`. Pass `street_imagery_comparison=true` with `/analyze`. GeoTrace filters references by distance from each candidate, ranks them with its own local scene descriptor, and returns the best matches with source and licence records. The submitted image stays inside the backend. Similarity is an uncalibrated retrieval signal and always requires visual review.

To enable private reverse-image matching, create a CSV from `backend/provenance_manifest.example.csv`, then run `.venv/bin/python -m backend.build_provenance_index path/to/provenance_manifest.csv`. Pass `source_provenance=true` with `/analyze`. Exact hashes, perceptual hashes, and local ORB features detect exact files, re-encodes, resizes, and possible crops. Every result retains its source URL, publication time, licence, attribution, and declared origin group so reposts are not miscounted as independent sources.

To calibrate location confidence, first retrain GeoTrace Visual v0 so its model contains training-image hashes. Prepare at least 50 held-out examples using `backend/benchmark_manifest.example.csv`, then run `.venv/bin/python -m backend.calibrate_location_model path/to/benchmark_manifest.csv --distance-km 25`. The generated report contains Top-1/Top-5 accuracy, distance errors, and scene/condition breakdowns. The runtime applies empirical confidence only when the calibration fingerprint matches the active model and enough samples support the score bin; otherwise candidates remain unscored. Confidence below 60% causes an explicit abstention.

The GitHub repository is source control, not an API host. Deploy this service to a Python-capable runtime, then build the frontend with `NEXT_PUBLIC_GEOTRACE_API_URL` set to its HTTPS origin.

## Atomic production data ingestion

For a production refresh, use one JSON bundle based on `backend/reference_bundle.example.json`. Every image manifest must include `source_id`, and every source must declare its exact licence, attribution, and terms URL in `source_ledger`. Then run:

```sh
.venv/bin/python -m backend.build_reference_bundle path/to/reference_bundle.json \
  --output-dir backend/models
```

The bundle builder validates source records, detects duplicate image hashes across manifests, rejects conflicting licence records, builds into a staging directory, and only replaces live artifacts after every requested build succeeds. A failed refresh leaves the last working indexes in place. It writes `geotrace_reference_bundle_report.json` with the build audit and measured coverage. Keep corpus files and generated indexes out of Git unless their redistribution licences explicitly allow inclusion.

## Container deployment

The root `Dockerfile` packages FastAPI, ExifTool, libmagic, Pillow, NumPy, and OpenCV. It runs as a non-root user, honors the host-provided `PORT`, uses `/ready` for its container check, and defaults CORS to the production GeoTrace AI site plus local development. Mount production indexes read-only and point the `GEOTRACE_*_PATH` variables in `.env.example` to them.

Build and run it on any Docker-compatible host:

```sh
docker build -t geotrace-analysis .
docker run --rm -p 8000:8000 \
  -e GEOTRACE_ALLOWED_ORIGINS=https://geotrace-ai-forensics.riteshbhardwaj364.chatgpt.site \
  geotrace-analysis
```

After deployment, rebuild the frontend with `NEXT_PUBLIC_GEOTRACE_API_URL=https://YOUR-API-HOST` and publish it. Keep the API on HTTPS; browsers will block an HTTP API from the HTTPS website.

## Hosted Instagram session

Never deploy an Instagram password. Create the Instaloader session interactively on a trusted computer, encode that session file as base64, and store the encoded value as a sealed hosting secret named `INSTALOADER_SESSION_BASE64`. Set `INSTAGRAM_USERNAME` and `GEOTRACE_INSTAGRAM_ENABLED=true` alongside it. The service writes the session to a permission-restricted temporary file only long enough for Instaloader to load it, then deletes that temporary file. `railway.json` configures Docker deployment and checks `/ready` before new releases receive traffic.
