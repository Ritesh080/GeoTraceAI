# GeoTrace AI website and analysis service

The hero and product concept are now connected to a working image-analysis interface backed by the Python cyber pipeline from https://github.com/Ritesh080/GeoTraceAI at commit `9ab9438a824bb67dbce805020483f5e6d6e2cf7f`.

Frontend:

```sh
npm install
npm run dev
```

Backend:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm run backend:dev
```

The frontend uses `NEXT_PUBLIC_GEOTRACE_API_URL`, defaulting to `http://127.0.0.1:8000`. Copy `.env.example` to `.env.local` when using another API origin. See `backend/README.md` for CORS and deployment configuration. Validate with `npm run build` and `npm run typecheck`.

Next.js 15 App Router, TypeScript, Tailwind 4, shadcn-style Radix Button, Framer Motion, Lucide, React Dropzone, Axios, and a FastAPI bridge around the existing Python pipeline.

Design tokens are centralized in `app/globals.css`. The hero workspace remains illustrative. The live analyzer reports file integrity, normalized metadata, image-forensic indicators, and the repository's forensic reliability score. Its OSINT handoff generates exact-hash, reverse-image, and coordinate-verification actions; ranks normalized location candidates; records supports and contradictions per candidate; groups dependent clues under their common source; and abstains when no independent external evidence has been collected. It does not upload images to third-party OSINT providers automatically.

`backend/geolocation.py` is the provider-neutral normalization boundary for visual-geolocation services. It turns valid embedded GPS, permitted platform location claims, and provider results into ranked candidate records; detects large cross-candidate conflicts; and leaves GeoTrace's own location confidence unscored until a benchmark can calibrate it. `GET /capabilities` reports which geolocation features are active, missing configuration, manual, or still require benchmarking.

## GeoTrace Visual v0

Visual geolocation is first-party and local. `backend/local_visual_model.py` extracts transparent scene descriptors—color distribution, spatial appearance, edge orientation, and low-frequency structure—and ranks places from a locally trained reference index. It makes no provider API calls and sends neither images nor descriptors to third parties.

Create a CSV based on `backend/training_manifest.example.csv`, using properly licensed reference images with known coordinates, then train the model:

```sh
.venv/bin/python -m backend.train_visual_model path/to/training_manifest.csv
npm run backend:dev
```

The default output is `backend/models/geotrace_visual_v0.npz`; set `GEOTRACE_VISUAL_MODEL_PATH` to use another location. The interface enables visual geolocation only when this file exists. Visual-similarity values are supporting evidence, not calibrated probabilities. A useful global model requires geographically diverse training data and a separate, deduplicated evaluation set.

## Offline map-context verification

GeoTrace can verify candidate coordinates against its own local place index—without sending coordinates or images to a geocoding provider. Download an official GeoNames cities dump, extract it, and build the index:

```sh
.venv/bin/python -m backend.build_map_index path/to/cities5000.txt \
  --country-info path/to/countryInfo.txt
npm run backend:dev
```

The analyzer can then compare candidate labels and OCR text with the nearest indexed place, record map-context support, and distinguish a simple map lookup from stronger OCR corroboration. Place data is from GeoNames under CC BY 4.0; manual review links use OpenStreetMap with its contributor attribution.

## Street-level imagery comparison

GeoTrace Street Compare v0 is a first-party, local retrieval engine. It compares the evidence image with licensed reference photographs near each coordinate candidate. It does not send the evidence image or its descriptor to an imagery provider, and it preserves each reference image's source, licence, attribution, capture time, heading, and coordinates.

Create a CSV based on `backend/street_manifest.example.csv`, then build the reference index:

```sh
.venv/bin/python -m backend.build_street_index path/to/street_manifest.csv
npm run backend:dev
```

The default output is `backend/models/geotrace_street_v0.npz`; set `GEOTRACE_STREET_INDEX_PATH` to use another location and `GEOTRACE_STREET_RADIUS_KM` to change the nearby-reference radius (default 10 km). The interface enables the option only when the index exists.

Reference images may be your own or properly licensed public street imagery. KartaView's official terms license its public street images under CC BY-SA 4.0 and require the credit `© Grab and KartaView Contributors`; keep the attribution and source URL in every manifest row. Do not mix sources whose licences do not permit local analysis or derived indexes.

The comparison reports similarity and geographic distance for review. Similarity is not a probability, a low score is not a contradiction, and even a strong match is only partial corroboration until a human confirms shared landmarks and rules out duplicates or scene changes.

## Reverse-image and source provenance

GeoTrace Provenance v0 privately checks an image against a local, licensed source index. It combines exact file and normalized-pixel fingerprints, perceptual hashing for resized or re-encoded copies, and crop-tolerant local image features. The evidence image and its descriptors never leave the backend.

Create a CSV based on `backend/provenance_manifest.example.csv`, assigning reposts or derivatives of one original to the same `origin_group`, then build the index:

```sh
.venv/bin/python -m backend.build_provenance_index path/to/provenance_manifest.csv
npm run backend:dev
```

The default index is `backend/models/geotrace_provenance_v0.npz`; use `GEOTRACE_PROVENANCE_INDEX_PATH` to select another location. Results include exact and near-duplicate matches, declared origin groups, licences, attributions, and an ordered publication timeline. The earliest result means the earliest occurrence in the local index—not the first publication anywhere on the internet. Perceptual and crop matches always require human review.

## Benchmark-calibrated location confidence

GeoTrace never converts raw visual similarity into a confidence percentage by assumption. Confidence becomes available only after the exact visual-model build is evaluated on at least 50 held-out, geographically labelled images that are not present in its training set.

Create a benchmark CSV based on `backend/benchmark_manifest.example.csv`, covering representative regions, urban/rural scenes, lighting, weather, and image quality, then run:

```sh
.venv/bin/python -m backend.calibrate_location_model path/to/benchmark_manifest.csv \
  --distance-km 25
npm run backend:dev
```

The evaluator rejects exact training-image leakage and duplicate benchmark files. It records Top-1 and Top-5 accuracy, median and 90th-percentile geographic error, and separate scene/condition metrics. It then fits empirical score bins with minimum sample requirements and Laplace smoothing. The calibration artifact is tied to the visual model fingerprint; retraining the model automatically makes older calibration stale.

Runtime confidence means: **the observed chance that a candidate was within the configured distance threshold on held-out images with a comparable retrieval score**. It is not certainty, does not replace independent corroboration, and triggers abstention below 60%. Sparse or missing benchmark bins remain unscored.

The OSINT handoff is an investigation aid rather than an automated web crawler. GeoTrace searches only the licensed sources deliberately added to its local indexes; broader coverage requires additional validated source ingestion. Location confidence remains uncalibrated.

When no hosted Python API is configured, the public frontend runs a private browser pipeline. It computes SHA-256 and image dimensions, extracts EXIF/GPS with `exifr`, performs English OCR with `tesseract.js`, identifies the dominant writing system, and creates coordinate or text-search evidence. The selected image is not automatically uploaded. The local visual model, calibrated confidence, map index, street reference comparison, and forensic reliability score require the Python backend.

The Python API accepts JPG, PNG, and WebP images up to 20 MB and deletes temporary files after each request. GitHub stores the backend source; it does not run the API. Internet deployment requires a Python-capable runtime and a corresponding frontend API URL.

## Production reference coverage

`backend/build_reference_bundle.py` is the production ingestion entry point. It builds the visual, place, street, provenance, and calibration artifacts as one licensed bundle; audits exact duplicates; and swaps the new files into service only after the complete requested build succeeds. Start from `backend/reference_bundle.example.json` and keep `source_id` in every image manifest.

The API exposes `/ready` and `/coverage`. The website shows the active dataset count, indexed references, geographic cells, and origin groups whenever the hosted backend is connected. “Service ready” means analysis can run; it does not mean worldwide coverage. Full reference coverage is reported only when all indexes are active and calibration matches the current visual-model fingerprint.

## Experimental Instagram import

The analyzer can import one explicitly requested, permitted, public single-image Instagram post and run the downloaded image through the same hash, EXIF, image-forensics, reliability, and OSINT pipeline. It does not crawl profiles, hashtags, followers, or stories. Instagram publication metadata and the downloaded image are kept in one provenance group and do not count as independent corroboration.

Install dependencies, then create an Instaloader session interactively (never put the password in source code or shell history):

```sh
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/instaloader --login YOUR_INSTAGRAM_USERNAME
```

Start the backend with the reusable session:

```sh
export INSTAGRAM_USERNAME="YOUR_INSTAGRAM_USERNAME"
export INSTALOADER_SESSION_FILE="$HOME/.config/instaloader/session-YOUR_INSTAGRAM_USERNAME"
npm run backend:dev
```

The website exposes an **Instagram experiment** field when the backend is available. The API endpoint is `POST /analyze/instagram` with JSON fields `url` and `consent`. Anonymous public-post lookup is attempted when no session variables are configured, but authenticated sessions are generally more reliable. The experiment currently rejects video and sidecar posts.

Remaining website sections still require the user's section-by-section approval: problem framing; full evidence-fusion demo; capabilities; forensic rigor; final CTA/footer.
