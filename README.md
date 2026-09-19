# GeoTrace AI

GeoTrace AI is an image-geolocation and digital-forensics research project. It combines a cyber-forensics pipeline, a browser-based investigation interface, and a dependency-aware OSINT design.

## Repository layout

```text
backend/cyber/       File validation, hashing, EXIF, image forensics, reliability
backend/api.py       FastAPI adapter used by the website
website/             Next.js frontend and private browser analysis
osint/               OSINT architecture and evidence-handling explanation
tests/               Cyber, API, and OSINT contract tests
Dockerfile           Production container for the Python analysis service
CYBER_PIPELINE.md    Original cyber-pipeline documentation
```

## Run the website

```sh
cd website
npm install
npm run dev
```

Without an API URL, the public frontend keeps images in the browser and performs SHA-256 hashing, image-dimension checks, EXIF/GPS extraction, English OCR, writing-system hints, and OSINT handoff generation. Configure `NEXT_PUBLIC_GEOTRACE_API_URL` to use the Python pipeline.

## Run the Python service

Install ExifTool and libmagic, then:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

The service accepts JPG, PNG, and WebP images up to 20 MB, removes temporary uploads after each request, and exposes `/health`, `/docs`, and `/analyze`.

## Validate

```sh
python3 -m unittest tests.test_api_contract tests.test_osint_stage -v
python3 tests/test_metadata_analyzer.py
python3 tests/test_reliability_engine.py
python3 tests/test_image_forensics.py
cd website && npm run typecheck && npm run build
```

## Current limits

Embedded GPS can produce a candidate that still requires corroboration. Images without GPS need hosted landmark/scene recognition and validated external sources before the system can support a location hypothesis. Forensic reliability and location confidence are separate measurements. See [`osint/README.md`](osint/README.md) for the evidence policy and integration status.
