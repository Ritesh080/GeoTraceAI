# GeoTrace AI — Cyber Pipeline Documentation

## AI-Assisted Image Geolocation & Digital Forensics using RAG

**Repository:** https://github.com/Ritesh080/GeoTraceAI
**Team:** 4 members (2 AI/ML + 2 Cybersecurity)
**This document covers:** Cybersecurity / Digital Forensics pipeline

---

## Architecture Overview

The system runs two parallel pipelines on every submitted image:

```
IMAGE
  ├── AI Pipeline: OCR → Visual Analysis → Geolocation → RAG → AI Result
  └── Cyber Pipeline: Validation → Hashing → EXIF → Forensics → Cyber Result
                                                                    │
                              AI Result + Cyber Result ─────────────┘
                                        │
                              Evidence Fusion → Conflict Resolution
                                        │
                              Final Location + Confidence + Report
```

### Cyber Pipeline Detail

```
Image
  → File Validation (python-magic)
  → SHA-256 Hashing (hashlib)
  → EXIF Extraction (ExifTool)
  → Metadata Forensic Analysis        ← Phase 2
  → Image Forensic Indicators         ← Phase 3 (upcoming)
  → Forensic Reliability Engine        ← Phase 4
  → AI/Cyber Evidence Integration      ← Phase 5
  → Conflict Detection                 ← Phase 6
  → Final Forensic Report              ← Phase 7
```

### Target Output Format

```json
{
  "image_id": "IMG001",
  "sha256": "...",
  "mime_type": "image/jpeg",
  "file_valid": true,
  "metadata": {
    "gps_present": true,
    "latitude": 28.6139,
    "longitude": 77.2090,
    "camera": "...",
    "timestamp": "...",
    "software": "..."
  },
  "forensics": {
    "tampering_suspected": false,
    "reliability_score": 0.91,
    "indicators": []
  }
}
```

### Design Principles

1. Editing software (Photoshop, Lightroom) is NOT automatic proof of tampering.
2. Forensic features are indicators, not absolute proof.
3. The original image is never modified.
4. SHA-256 is used for file integrity and evidence chain.
5. EXIF GPS is never blindly trusted — it is cross-verified against OCR, visual clues, geolocation model, and RAG evidence.
6. Conflicting evidence is resolved by a reliability-aware fusion mechanism.

---

## Project Structure

```
GeoTraceAI/
├── .gitignore
├── CYBER_PIPELINE.md              ← this file
├── backend/
│   └── cyber/
│       ├── file_validator.py      ← Phase 1
│       ├── hash_service.py        ← Phase 1
│       ├── exif_service.py        ← Phase 1
│       ├── metadata_analyzer.py   ← Phase 2
│       └── main.py                ← orchestrator
├── datasets/
│   └── test_images/
│       └── image.png              ← test image
└── tests/
    └── test_metadata_analyzer.py  ← Phase 2 tests
```

### Tools & Dependencies

| Tool | Purpose |
|------|---------|
| Python 3 | Core language |
| python-magic / libmagic | True MIME type detection (not extension-based) |
| hashlib | SHA-256 file hashing |
| ExifTool | Metadata extraction |
| Pillow | Image processing |
| OpenCV | Image forensics (Phase 3+) |

---

## Phase 1 — File Validation + SHA-256 + EXIF Extraction

**Status:** COMPLETED
**Commit:** initial repository setup

### What was built

Three modules that form the intake stage of the cyber pipeline.

### 1.1 file_validator.py

**Purpose:** Verify the uploaded file is a genuine image, not a renamed executable or corrupted file.

**How it works:**
- Uses `python-magic` (libmagic) to read the file's magic bytes and determine the true MIME type.
- Compares against an allowlist: `image/jpeg`, `image/png`, `image/webp`.
- Returns `valid: true/false`, the detected `mime_type`, and the file `extension`.

**Why magic bytes matter:**
A file named `payload.jpg` could actually be a PHP script or executable. Checking the extension alone is not forensically sound. libmagic reads the file header bytes to determine the real type.

```python
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

def validate_image(file_path: str) -> dict:
    path = Path(file_path)
    if not path.exists():
        return {"valid": False, "reason": "File does not exist"}
    mime_type = magic.from_file(str(path), mime=True)
    return {
        "valid": mime_type in ALLOWED_MIME_TYPES,
        "mime_type": mime_type,
        "extension": path.suffix.lower()
    }
```

### 1.2 hash_service.py

**Purpose:** Generate a SHA-256 hash of the image file for evidence integrity.

**How it works:**
- Reads the file in 8KB chunks to handle large files without loading them fully into memory.
- Returns a hex digest string.

**Forensic role:**
The hash serves as a digital fingerprint. If the image is later modified (even by one byte), the hash changes. This establishes chain of custody and proves the analyzed image is identical to the submitted one.

```python
def calculate_sha256(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
```

### 1.3 exif_service.py

**Purpose:** Extract all embedded metadata from the image using ExifTool.

**How it works:**
- Shells out to `exiftool -json <file>` via subprocess.
- Parses the JSON output and returns the first element (ExifTool returns an array).
- Returns an error dict if ExifTool fails.

**Why ExifTool over Pillow:**
Pillow can read basic EXIF but misses many fields (XMP, IPTC, MakerNotes). ExifTool is the industry standard and extracts hundreds of metadata fields from all image formats.

```python
def extract_exif(file_path: str) -> dict:
    result = subprocess.run(
        ["exiftool", "-json", file_path],
        capture_output=True, text=True, check=True
    )
    data = json.loads(result.stdout)
    return data[0] if data else {}
```

### 1.4 main.py (Phase 1 version)

Orchestrated the three modules in sequence:

```
validate_image → calculate_sha256 → extract_exif → JSON output
```

### Phase 1 Test Results

```
image.png:
  status = success
  SHA-256 = generated
  file.valid = true
  mime_type = image/png
  extension = .png
  ExifTool metadata = successfully extracted
```

---

## Phase 2 — Metadata Forensic Analyzer

**Status:** COMPLETED
**Commit:** `feat: Phase 2 — metadata forensic analyzer`

### What was built

`metadata_analyzer.py` — takes raw ExifTool JSON and produces normalized metadata + forensic indicators.

### Pipeline

```
ExifTool Raw JSON
       │
       ▼
metadata_analyzer.py
       │
       ├── Normalized Metadata (GPS, camera, timestamps, software)
       ├── Consistency Checks (timestamp mismatches, missing fields)
       └── Forensic Indicators (flags for downstream fusion)
       │
       ▼
Structured JSON
```

### 2.1 GPS Extraction & Normalization

**Problem:** ExifTool returns GPS coordinates in inconsistent formats:
- Decimal: `28.6139`
- String decimal: `"77.209"`
- DMS string: `"28 deg 36' 50.04\" N"`

**Solution:** `_parse_gps_coordinate()` handles all three formats, parses DMS components, applies N/S/E/W direction, and returns a standard decimal float.

**Coordinate validation:** Checks that latitude is within [-90, 90] and longitude within [-180, 180].

**Zero-value bug fix:** The initial implementation used `raw.get("GPSLatitude") or raw.get("GPS:GPSLatitude")`. This silently dropped `0.0` coordinates because `0.0` is falsy in Python. Fixed by introducing `_get_first()` which checks `is not None` instead of truthiness.

```python
def _get_first(raw: dict, *keys):
    for k in keys:
        val = raw.get(k)
        if val is not None:
            return val
    return None
```

### 2.2 Timestamp Extraction

Extracts and normalizes three EXIF timestamps:

| Field | EXIF Key | Meaning |
|-------|----------|---------|
| `datetime_original` | DateTimeOriginal | When the photo was taken |
| `create_date` | CreateDate | When the digital file was created |
| `modify_date` | ModifyDate | Last modification time |

Supports multiple datetime formats ExifTool may return:
- `2024:06:15 10:30:00` (EXIF standard)
- `2024-06-15 10:30:00`
- ISO 8601 variants with timezone

### 2.3 Camera & Software Extraction

Extracts `Make`, `Model`, and `Software` fields. Checks both standard and namespaced ExifTool keys (e.g., `EXIF:Make`, `XMP:CreatorTool`).

### 2.4 Forensic Indicator Engine

Produces a list of string indicators. Each is evidence, never a verdict.

#### Timestamp Consistency Checks

| Indicator | Trigger |
|-----------|---------|
| `modify_date_before_original` | ModifyDate is earlier than DateTimeOriginal — unusual, suggests metadata was altered |
| `original_create_date_mismatch` | DateTimeOriginal and CreateDate differ by more than 1 second — may indicate re-processing |

#### Missing Field Checks

| Indicator | Trigger |
|-----------|---------|
| `missing_datetime_original` | No DateTimeOriginal field — common in screenshots, downloads, stripped images |
| `missing_camera_info` | No Make or Model — image may be synthetic, a screenshot, or metadata-stripped |

#### Suspicious Metadata Checks

| Indicator | Trigger |
|-----------|---------|
| `software_detected:<name>` | Software field is present (e.g., Photoshop, Lightroom). Noted as context, NOT treated as tampering evidence |
| `unusual_gps_altitude` | GPS altitude below -100 meters — physically implausible in most cases |
| `gps_null_island` | Coordinates are (0, 0) — almost always a default/error value, not a real location |
| `metadata_extraction_failed` | ExifTool returned an error or None — no metadata to analyze |

### 2.5 Updated main.py

The orchestrator now runs Phase 2 after Phase 1:

```
validate_image → calculate_sha256 → extract_exif → analyze_metadata → JSON output
```

Output structure:

```json
{
  "status": "success",
  "sha256": "...",
  "file": { "valid": true, "mime_type": "...", "extension": "..." },
  "raw_exif": { ... },
  "metadata": {
    "gps_present": true,
    "latitude": 28.6139,
    "longitude": 77.209,
    "coordinates_valid": true,
    "camera": "NIKON CORPORATION",
    "model": "NIKON D850",
    "datetime_original": "2024:03:10 14:22:05",
    "create_date": "2024:03:10 14:22:05",
    "modify_date": "2024:03:10 14:22:05",
    "software": "Adobe Lightroom Classic 13.1"
  },
  "forensics": {
    "indicators": ["software_detected:Adobe Lightroom Classic 13.1"],
    "indicator_count": 1
  }
}
```

### 2.6 Tests

**File:** `tests/test_metadata_analyzer.py`
**Test count:** 11 (6 named test functions covering GPS parsing, full metadata, empty metadata, timestamp inconsistency, software detection, null island, and error handling)

```
PASS: full metadata
PASS: empty metadata
PASS: modify before original
PASS: software noted (not auto-tampered)
PASS: null island detected
PASS: error input handled

=== ALL PHASE 2 TESTS PASSED ===
```

---

## Upcoming Phases

### Phase 3 — Image Forensic Indicators (OpenCV / Pillow)
Pixel-level analysis: ELA (Error Level Analysis), noise inconsistency, clone detection hints. These feed into the indicator list alongside metadata indicators.

### Phase 4 — Forensic Reliability Engine
Weighs all indicators and produces a single `reliability_score` (0.0–1.0) for the image's metadata trustworthiness.

### Phase 5 — AI/Cyber Evidence Integration
Bridges the cyber pipeline output with the AI pipeline output. Defines the shared data contract.

### Phase 6 — Conflict Detection
Compares EXIF GPS vs. AI-predicted location vs. OCR clues. Flags contradictions.

### Phase 7 — Final Forensic Report
Generates the complete `cyber_result.json` with all findings, scores, and a human-readable summary.

---

## Changelog

| Date | Phase | Description |
|------|-------|-------------|
| 2026-09-05 | 1 | File validation, SHA-256 hashing, ExifTool extraction |
| 2026-09-05 | 2 | Metadata forensic analyzer with GPS normalization, timestamp checks, forensic indicators |
