# GeoTrace AI website and analysis service

The hero and product concept are now connected to a working image-analysis interface backed by the Python cyber pipeline from https://github.com/Ritesh080/GeoTraceAI at commit `9ab9438a824bb67dbce805020483f5e6d6e2cf7f`.

From the repository root, run the frontend with:

```sh
cd website
npm install
npm run dev
```

Backend:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

The frontend uses `NEXT_PUBLIC_GEOTRACE_API_URL`, defaulting to `http://127.0.0.1:8000` during local development. Copy `.env.example` to `.env.local` when using another API origin. See `../backend/README.md` for CORS and deployment configuration. Validate inside `website/` with `npm run build` and `npm run typecheck`.

Next.js 15 App Router, TypeScript, Tailwind 4, shadcn-style Radix Button, Framer Motion, Lucide, React Dropzone, Axios, and a FastAPI bridge around the existing Python pipeline.

Design tokens are centralized in `app/globals.css`. The hero workspace remains illustrative. The live analyzer reports file integrity, normalized metadata, image-forensic indicators, and the repository's forensic reliability score. Its OSINT handoff generates exact-hash, reverse-image, and coordinate-verification actions; groups hash, EXIF, and forensic clues under the submitted asset; and abstains when no independent external evidence has been collected. It does not upload images to third-party OSINT providers automatically.

The OSINT handoff is an investigation aid rather than an automated web crawler. Provider adapters and validated source ingestion are still required before source conflicts can be resolved or location confidence can be calibrated.

When no hosted Python API is configured, the public frontend runs a private browser pipeline. It computes SHA-256 and image dimensions, extracts EXIF/GPS with `exifr`, performs English OCR with `tesseract.js`, identifies the dominant writing system, and creates coordinate or text-search evidence. The selected image is not automatically uploaded. Landmark recognition and the forensic reliability score still require hosted providers.

The Python API accepts JPG, PNG, and WebP images up to 20 MB and deletes temporary files after each request. GitHub stores the backend source; it does not run the API. Internet deployment requires a Python-capable runtime and a corresponding frontend API URL.

Remaining website sections still require the user's section-by-section approval: problem framing; full evidence-fusion demo; capabilities; forensic rigor; final CTA/footer.
