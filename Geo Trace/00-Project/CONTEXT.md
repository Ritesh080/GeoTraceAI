# Current context

Updated: 2026-10-01
Workspace verification marker: GEOTRACE-SHARED-CONTEXT-20260919

## Verified baseline
- Existing repository contains `backend/cyber/main.py`, `file_validator.py`, `hash_service.py`, and `exif_service.py`.
- Main pipeline validates the image, computes SHA-256, and extracts metadata through the external `exiftool` command.
- Allowed MIME types are JPEG, PNG, and WebP.
- `datasets/test_images/` exists; `tests/` exists but no test files were observed during setup.
- Existing Obsidian notes were preserved.
- GeoTrace's active CLI and browser use local-only processing: EXIF, GeoCLIP,
  image characteristics, perceptual hashing, Apple Vision OCR, and
  Indian-script detection.
- The browser includes social-media evidence intake for operator-supplied
  public-source provenance plus an uploaded screenshot or video frame.
- Social-media intake can automatically collect a public page's preview image
  without a platform API or account login and preserves acquisition provenance.
- Caption, hashtags, displayed location, structured page data, explicit
  coordinates, and OCR are resolved against a local 660,000-feature India
  gazetteer and fused with GeoCLIP as independent evidence.
- The unit suite and a live local GeoCLIP run pass on the existing sample image.
- A localhost web interface is running at `http://127.0.0.1:8787`; its upload
  API completed a real GeoCLIP analysis of the repository sample image.

## Current focus
The local `/osint` case workspace supports CSV/JSON imports, source and access
provenance, exact normalized phone search, exact/partial name leads, case-scoped
viewer/editor/owner keys, revocation and a hash-chained audit trail. It searches
only records imported into that case. No external sources are connected. Keys
are stored only as hashes, and private case storage is ignored by Git.

Build an India-specific, locally owned geotagged image gallery and visual
retrieval index for street-level matching. Agent connection checks and
developer-handbook review remain separate open work.

## Open questions
- What is the first end-to-end product milestone?
- Which dependencies and versions should be pinned?
- What tests and sample images are appropriate for acceptance?

## Session handoff
Read [[PROJECT]], [[ARCHITECTURE]], [[DECISIONS]], and [[TASKS]] before making project changes. Record findings and pending work in `03-Agent-Notes/`.
