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

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


CYBER_DIR = Path(__file__).resolve().parent / "cyber"
sys.path.insert(0, str(CYBER_DIR))

from main import analyze_image  # noqa: E402
from backend.instagram_source import (  # noqa: E402
    InstagramImportError,
    InstagramProviderError,
    analyze_instagram_post,
    instagram_provider_status,
)
from backend.osint_stage import build_osint_assessment
from backend.geolocation import provider_capabilities
from backend.gods_eye_context import area_view_status, attach_area_view_links
from backend.local_visual_model import (
    LocalVisualModelError,
    LocalVisualModelNotTrained,
    predict_locations,
)
from backend.location_calibration import apply_location_calibration
from backend.local_map_verification import (
    LocalMapError,
    LocalMapNotBuilt,
    verify_map_context,
)
from backend.local_street_imagery import (
    LocalStreetImageryError,
    LocalStreetImageryNotBuilt,
    compare_street_imagery,
)
from backend.local_source_provenance import (
    LocalProvenanceError,
    LocalProvenanceNotBuilt,
    match_source_provenance,
)
from backend.index_coverage import coverage_report
from evidence_fusion import fuse_evidence
from conflict_detection import analyze_conflicts
from micro_osint import attach_micro_osint_workspace, build_micro_osint_ledger


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

app = FastAPI(title="GeoTrace AI Analysis API", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class InstagramAnalyzeRequest(BaseModel):
    url: str = Field(min_length=20, max_length=500)
    consent: bool = False


class MicroOsintRequest(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list, max_length=100)
    clues: list[dict] = Field(default_factory=list, max_length=250)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/", include_in_schema=False)
def root() -> JSONResponse:
    return JSONResponse({"service": "GeoTrace AI Analysis API", "docs": "/docs", "health": "/health", "readiness": "/ready", "coverage": "/coverage", "instagram": "/instagram/status", "area_view": "/area-view/status"})


@app.get("/health")
def health() -> dict:
    return {
        "status": "ready",
        "service": "geotrace-cyber-pipeline",
        "source": "github.com/Ritesh080/GeoTraceAI",
    }


@app.get("/ready")
def ready() -> dict:
    """Operational readiness, kept separate from optional reference coverage."""
    report = coverage_report()
    return {
        "status": "ready" if report["full_reference_coverage"] else "ready_limited",
        "analysis_operational": True,
        "full_reference_coverage": report["full_reference_coverage"],
        "active_datasets": report["active_datasets"],
        "total_datasets": report["total_datasets"],
    }


@app.get("/coverage")
def coverage() -> dict:
    return coverage_report()


@app.get("/instagram/status")
def instagram_status() -> dict:
    return instagram_provider_status()


@app.get("/area-view/status")
def get_area_view_status() -> dict:
    return area_view_status()


@app.get("/capabilities")
def capabilities() -> dict:
    """Report active, adapter-ready, and still-manual geolocation features."""
    return {"capabilities": provider_capabilities()}


@app.post("/micro-osint/evaluate")
def evaluate_micro_osint(request: MicroOsintRequest) -> dict:
    """Validate an analyst's clue ledger without issuing a location verdict."""
    try:
        return build_micro_osint_ledger(request.clues, request.candidate_ids)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    visual_geolocation: bool = Form(False),
    map_verification: bool = Form(False),
    street_imagery_comparison: bool = Form(False),
    source_provenance: bool = Form(False),
) -> dict:
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
        provider_result = None
        if visual_geolocation:
            try:
                async with ANALYSIS_SEMAPHORE:
                    provider_result = await asyncio.to_thread(predict_locations, temporary_path, 3)
                    provider_result = await asyncio.to_thread(apply_location_calibration, provider_result)
            except LocalVisualModelNotTrained as error:
                raise HTTPException(503, str(error)) from error
            except LocalVisualModelError as error:
                raise HTTPException(502, str(error)) from error
        result["osint"] = build_osint_assessment(
            sha256=result["sha256"],
            metadata=result["metadata"],
            provider_candidates=provider_result["candidates"] if provider_result else None,
            provider_context={
                "provider": "GeoTrace Visual v0",
                "external_processing": False,
                "privacy_note": "GeoTrace ran its own visual model locally. No image or descriptor was sent to a third party.",
                "model": provider_result["model"],
                "calibration": provider_result["calibration"],
            } if provider_result else None,
        )
        if map_verification and result["osint"]["candidates"]:
            try:
                result["osint"] = await asyncio.to_thread(
                    verify_map_context,
                    result["osint"],
                    result["metadata"].get("ocr_text"),
                )
            except LocalMapNotBuilt as error:
                raise HTTPException(503, str(error)) from error
            except LocalMapError as error:
                raise HTTPException(502, str(error)) from error
        if street_imagery_comparison and result["osint"]["candidates"]:
            try:
                async with ANALYSIS_SEMAPHORE:
                    result["osint"] = await asyncio.to_thread(
                        compare_street_imagery,
                        temporary_path,
                        result["osint"],
                    )
            except LocalStreetImageryNotBuilt as error:
                raise HTTPException(503, str(error)) from error
            except LocalStreetImageryError as error:
                raise HTTPException(502, str(error)) from error
        if source_provenance:
            try:
                async with ANALYSIS_SEMAPHORE:
                    result["osint"] = await asyncio.to_thread(
                        match_source_provenance,
                        temporary_path,
                        result["osint"],
                    )
            except LocalProvenanceNotBuilt as error:
                raise HTTPException(503, str(error)) from error
            except LocalProvenanceError as error:
                raise HTTPException(502, str(error)) from error
        result["osint"] = attach_area_view_links(result["osint"])
        result["osint"] = attach_micro_osint_workspace(result["osint"])
        result["osint"] = analyze_conflicts(result, result["osint"])
        result["evidence_fusion"] = fuse_evidence(result, result["osint"])
        return result
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)


@app.post("/analyze/instagram")
async def analyze_instagram(request: InstagramAnalyzeRequest) -> dict:
    """Import one user-requested Instagram image post for forensic analysis."""
    if not instagram_provider_status()["enabled"]:
        raise HTTPException(503, "Instagram import is not enabled on this deployment.")
    if not request.consent:
        raise HTTPException(400, "Confirm permission before retrieving the Instagram post.")

    try:
        async with ANALYSIS_SEMAPHORE:
            result = await asyncio.to_thread(analyze_instagram_post, request.url)
    except InstagramImportError as error:
        raise HTTPException(400, str(error)) from error
    except InstagramProviderError as error:
        raise HTTPException(502, str(error)) from error

    result["osint"] = build_osint_assessment(
        sha256=result["sha256"],
        metadata=result["metadata"],
        source=result["source"],
    )
    result["osint"] = attach_area_view_links(result["osint"])
    result["osint"] = attach_micro_osint_workspace(result["osint"])
    result["osint"] = analyze_conflicts(result, result["osint"])
    result["evidence_fusion"] = fuse_evidence(result, result["osint"])
    return result
