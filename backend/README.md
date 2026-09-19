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
- `POST /analyze` with multipart field `file`

`POST /analyze` includes an `osint` object with manual search and map-verification actions, a source-dependency group for observations derived from the submitted image, conflict placeholders, privacy state, and an uncertainty decision. The stage returns `insufficient_evidence` until independent external sources are collected. Images are never uploaded to OSINT providers by this API.

The GitHub repository is source control, not an API host. Deploy this service to a Python-capable runtime, then build the frontend with `NEXT_PUBLIC_GEOTRACE_API_URL` set to its HTTPS origin.

## Container deployment

The root `Dockerfile` packages FastAPI, ExifTool, libmagic, Pillow, NumPy, and OpenCV. It runs as a non-root user, honors the host-provided `PORT`, exposes `/health`, and defaults CORS to the production GeoTrace AI site plus local development.

Build and run it on any Docker-compatible host:

```sh
docker build -t geotrace-analysis .
docker run --rm -p 8000:8000 \
  -e GEOTRACE_ALLOWED_ORIGINS=https://geotrace-ai-forensics.riteshbhardwaj364.chatgpt.site \
  geotrace-analysis
```

After deployment, rebuild the frontend with `NEXT_PUBLIC_GEOTRACE_API_URL=https://YOUR-API-HOST` and publish it. Keep the API on HTTPS; browsers will block an HTTP API from the HTTPS website.
