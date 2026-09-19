"""HTTP adapter for the GeoTraceAI cyber pipeline from GitHub.

Run from the project root with:
    uvicorn backend.api:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


CYBER_DIR = Path(__file__).resolve().parent / "cyber"
sys.path.insert(0, str(CYBER_DIR))

from main import analyze_image  # noqa: E402
from backend.osint_stage import build_osint_assessment


MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "GEOTRACE_ALLOWED_ORIGINS",
        "https://geotrace-ai-forensics.riteshbhardwaj364.chatgpt.site,http://127.0.0.1:3000,http://localhost:3000",
    ).split(",")
    if origin.strip()
]

ANALYSIS_SEMAPHORE = asyncio.Semaphore(max(1, int(os.getenv("GEOTRACE_ANALYSIS_CONCURRENCY", "2"))))

app = FastAPI(title="GeoTrace AI Analysis API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/", include_in_schema=False)
def root() -> JSONResponse:
    return JSONResponse({"service": "GeoTrace AI Analysis API", "docs": "/docs", "health": "/health"})


@app.get("/health")
def health() -> dict:
    return {
        "status": "ready",
        "service": "geotrace-cyber-pipeline",
        "source": "github.com/Ritesh080/GeoTraceAI",
    }


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, "Upload a JPG, PNG, or WebP image.")

    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image exceeds the 20 MB upload limit.")
    if not payload:
        raise HTTPException(400, "The uploaded image is empty.")

    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
            temporary.write(payload)
            temporary_path = temporary.name
        async with ANALYSIS_SEMAPHORE:
            result = await asyncio.to_thread(analyze_image, temporary_path)
        if result.get("status") == "rejected":
            raise HTTPException(415, result.get("file", {}).get("reason", "Invalid image."))
        # The raw extractor output contains temporary server paths and can be
        # very large. Keep the normalized fields in the public response.
        result.pop("raw_exif", None)
        result["osint"] = build_osint_assessment(
            sha256=result["sha256"],
            metadata=result["metadata"],
        )
        return result
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
