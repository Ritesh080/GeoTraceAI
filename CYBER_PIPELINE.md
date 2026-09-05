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
├── CYBER_PIPELINE.md                ← this file
├── backend/
│   └── cyber/
│       ├── file_validator.py        ← Phase 1
│       ├── hash_service.py          ← Phase 1
│       ├── exif_service.py          ← Phase 1
│       ├── metadata_analyzer.py     ← Phase 2
│       ├── image_forensics.py       ← Phase 3
│       ├── reliability_engine.py    ← Phase 4
│       └── main.py                  ← orchestrator
├── datasets/
│   └── test_images/
│       └── image.png                ← test image
└── tests/
    ├── test_metadata_analyzer.py    ← Phase 2 tests
    ├── test_image_forensics.py      ← Phase 3 tests
    └── test_reliability_engine.py   ← Phase 4 tests
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

## Phase 3 — Image Forensic Indicators (OpenCV / Pillow)

**Status:** COMPLETED
**Commit:** `feat: Phase 3 — image forensic indicators`

### What was built

`image_forensics.py` — pixel-level forensic analysis that produces numeric measurements and string indicators. These merge into the same `forensics.indicators` list from Phase 2.

### Pipeline

```
Image File (validated by Phase 1)
       │
       ▼
image_forensics.py
       │
       ├── Structure Analysis (dimensions, resolution, color mode)
       ├── ELA (Error Level Analysis)
       ├── Noise Consistency Analysis
       ├── Channel Statistics
       └── JPEG Quality Estimation
       │
       ▼
{ image_forensics: { ... }, indicators: [ ... ] }
```

### 3.1 Image Structure Analysis

**Purpose:** Extract basic properties that may be forensically relevant.

**Fields extracted:**
- `width`, `height` — pixel dimensions
- `megapixels` — total resolution
- `aspect_ratio` — width/height ratio
- `mode` — color mode (RGB, RGBA, L, P, etc.)

**Indicators:**

| Indicator | Trigger |
|-----------|---------|
| `very_low_resolution` | Image is below 0.1 megapixels — likely a thumbnail, crop, or synthetic image |
| `unusual_color_mode:<mode>` | Color mode is not RGB or RGBA — palette images, grayscale, or unusual encoding |

### 3.2 Error Level Analysis (ELA)

**Purpose:** Detect regions that have been modified after the last JPEG save.

**How it works:**
1. Re-save the image as JPEG at a known quality (90%).
2. Compute the absolute pixel difference between the original and re-saved version.
3. Scale the difference map for interpretability.
4. Calculate mean, max, and standard deviation of the error levels.

**Forensic logic:** When a JPEG is saved, all regions compress uniformly. If a region was pasted or edited after the last save, it will have a different compression history and show higher error levels than the surrounding area.

**Indicators:**

| Indicator | Trigger |
|-----------|---------|
| `ela_high_variance` | ELA standard deviation > 60 — some regions have very different compression levels |
| `ela_localized_hotspot` | ELA max > 200 but mean < 30 — a small area has extreme error while the rest is uniform, suggesting localized editing |

### 3.3 Noise Consistency Analysis

**Purpose:** Detect regions with different noise profiles, which may indicate splicing.

**How it works:**
1. Convert image to grayscale.
2. Split into non-overlapping 64x64 blocks.
3. For each block, compute the standard deviation of the Laplacian (measures edge-free noise).
4. Calculate the coefficient of variation (CV) across all blocks.

**Forensic logic:** A genuine photograph has a uniform noise profile across the entire image (same sensor, same ISO). If a region was pasted from a different source, its noise level will differ from the rest.

**Indicators:**

| Indicator | Trigger |
|-----------|---------|
| `noise_inconsistency_high` | Noise CV > 0.7 — strong evidence of mixed noise sources |
| `noise_inconsistency_moderate` | Noise CV > 0.5 — moderate inconsistency worth noting |

### 3.4 Channel Statistics

**Purpose:** Detect anomalous color channel distributions.

**Fields per channel (red, green, blue):**
- `mean` — average pixel value (0–255)
- `std` — standard deviation

**Indicators:**

| Indicator | Trigger |
|-----------|---------|
| `flat_channel:<name>` | Standard deviation < 1.0 in a channel — the channel is nearly uniform, suggesting synthetic fill or solid overlay |

### 3.5 JPEG Quality Estimation

**Purpose:** Estimate the JPEG quantization quality level.

**How it works:** Reads the JPEG quantization table (luminance), averages the values, and maps to an estimated 1–100 quality scale.

**Returns:** Integer quality estimate, or `null` for non-JPEG images.

**Forensic role:** Useful in later phases to detect double compression (a JPEG saved at quality 95 that has quantization artifacts of quality 60 was likely re-saved).

### 3.6 Updated main.py

The orchestrator now merges indicators from both Phase 2 and Phase 3:

```
validate → sha256 → exif → metadata_analysis → image_forensics → merged output
```

Output now includes a new `image_forensics` section:

```json
{
  "status": "success",
  "sha256": "...",
  "file": { ... },
  "raw_exif": { ... },
  "metadata": { ... },
  "image_forensics": {
    "structure": { "width": 640, "height": 480, "megapixels": 0.31, ... },
    "ela": { "ela_mean": 14.18, "ela_max": 104.83, "ela_std": 11.11, ... },
    "noise": { "noise_mean": 134.16, "noise_cv": 0.0137, ... },
    "channels": { "red": { ... }, "green": { ... }, "blue": { ... } },
    "jpeg_quality": 75
  },
  "forensics": {
    "indicators": [ ... ],
    "indicator_count": 1
  }
}
```

The `forensics.indicators` list now contains indicators from BOTH metadata analysis (Phase 2) and image analysis (Phase 3), merged in `main.py`.

### 3.7 Dependencies Added

```
opencv-python-headless   # Image processing (ELA, noise analysis)
numpy                     # Array operations
Pillow                    # Image I/O (already used in Phase 1)
```

Install on your machine:
```bash
pip install opencv-python numpy Pillow
```

### 3.8 Tests

**File:** `tests/test_image_forensics.py`
**Test count:** 7 test functions

| Test | What it verifies |
|------|-----------------|
| `test_normal_image` | Clean JPEG produces expected structure, ELA, noise, and channel stats |
| `test_tiny_image` | 30x30 PNG triggers `very_low_resolution` |
| `test_flat_channel` | Image with uniform red channel triggers `flat_channel:red` |
| `test_jpeg_quality` | Quality estimation returns a value between 1 and 100 |
| `test_invalid_file` | Non-image file returns `image_open_failed` indicator |
| `test_spliced_image` | Image with pasted block triggers `noise_inconsistency_high` |
| `test_full_output_structure` | All expected keys present in output dict |

```
  indicators: []
PASS: normal image
PASS: tiny image flagged
PASS: flat channel detected
  estimated quality: 75
PASS: JPEG quality estimated
PASS: invalid file handled
  ELA std: 4.21
  noise CV: 1.4464
  indicators: ['noise_inconsistency_high']
PASS: spliced image analyzed
PASS: output structure complete

=== ALL PHASE 3 TESTS PASSED ===
```

---

## Phase 4 — Forensic Reliability Engine

**Status:** COMPLETED
**Commit:** `feat: Phase 4 — forensic reliability engine`

### What was built

`reliability_engine.py` — takes the merged indicator list from Phase 2 + Phase 3 and the continuous image forensics measurements, and produces a single reliability score with full transparency into how it was calculated.

### Pipeline

```
Phase 2 Indicators + Phase 3 Indicators
       │
       ▼
reliability_engine.py
       │
       ├── Score each indicator (weighted penalties)
       ├── Apply continuous metric adjustments (graded ELA/noise)
       ├── Compute total penalty
       └── Classify reliability level
       │
       ▼
{
  reliability_score: 0.72,
  reliability_level: "medium",
  tampering_suspected: false,
  scored_indicators: [...],
  continuous_adjustments: [...],
  total_penalty: 0.28
}
```

### 4.1 Scoring Approach

Start at 1.0 (fully trustworthy). Each indicator subtracts a weighted penalty. Final score is clamped to [0.0, 1.0].

**Indicator Penalty Weights:**

| Indicator | Penalty | Rationale |
|-----------|---------|-----------|
| `metadata_extraction_failed` | 0.25 | No metadata to analyze at all |
| `gps_null_island` | 0.20 | Coordinates (0,0) are almost always errors |
| `ela_localized_hotspot` | 0.20 | Localized region with very different compression |
| `noise_inconsistency_high` | 0.20 | Strong noise mismatch between image regions |
| `modify_date_before_original` | 0.15 | Timestamp went backward — unusual |
| `ela_high_variance` | 0.15 | Uneven compression across the image |
| `flat_channel:<name>` | 0.12 | A color channel is nearly uniform — synthetic fill |
| `original_create_date_mismatch` | 0.10 | DateTimeOriginal and CreateDate disagree |
| `noise_inconsistency_moderate` | 0.10 | Moderate noise mismatch |
| `unusual_gps_altitude` | 0.10 | GPS altitude below -100m |
| `very_low_resolution` | 0.10 | Image below 0.1 megapixels |
| `missing_datetime_original` | 0.08 | No DateTimeOriginal field |
| `missing_camera_info` | 0.08 | No Make or Model field |
| `unusual_color_mode:<mode>` | 0.05 | Non-standard color mode |
| `software_detected:<name>` | 0.03 | Software field present — noted, barely penalized |
| `image_open_failed:<reason>` | 0.30 | Image could not be opened for analysis |
| Unknown indicator | 0.02 | Default — ensures no indicator is invisible |

### 4.2 Continuous Metric Adjustments

Binary indicators only fire at thresholds (e.g., ELA std > 60). Continuous adjustments handle the gray zone below thresholds:

| Source | Trigger | Penalty |
|--------|---------|---------|
| `ela_std_elevated` | ELA std between 40–60 | 0.07 |
| `ela_std_very_high` | ELA std > 60 (extra on top of indicator) | 0.05 |
| `noise_cv_elevated` | Noise CV between 0.35–0.5 | 0.05 |
| `noise_cv_very_high` | Noise CV > 0.7 (extra on top of indicator) | 0.05 |
| `ela_hotspot_extreme_ratio` | ELA max/mean ratio > 15 | 0.08 |

### 4.3 Reliability Levels

| Score Range | Level | Meaning |
|-------------|-------|---------|
| 0.80 – 1.00 | `high` | Metadata appears trustworthy |
| 0.55 – 0.79 | `medium` | Some concerns, use with caution |
| 0.30 – 0.54 | `low` | Significant issues detected |
| 0.00 – 0.29 | `very_low` | Strong evidence of problems |

### 4.4 Tampering Suspected

`tampering_suspected` is set to `true` when the score drops below 0.55 (configurable threshold). This is still an indicator, not proof. The downstream fusion engine uses it alongside AI pipeline confidence.

### 4.5 Updated main.py

The orchestrator now runs all four phases:

```
validate → sha256 → exif → metadata_analysis → image_forensics → reliability_engine → output
```

The `forensics` section in the output now includes:

```json
{
  "forensics": {
    "indicators": ["software_detected:Adobe Photoshop 25.0"],
    "indicator_count": 1,
    "reliability_score": 0.97,
    "reliability_level": "high",
    "tampering_suspected": false,
    "scored_indicators": [
      { "indicator": "software_detected:Adobe Photoshop 25.0", "penalty": 0.03 }
    ],
    "continuous_adjustments": [],
    "total_penalty": 0.03
  }
}
```

### 4.6 Tests

**File:** `tests/test_reliability_engine.py`
**Test count:** 12 test functions

| Test | What it verifies |
|------|-----------------|
| `test_clean_image` | No indicators → score 1.0, high, no tampering |
| `test_software_only` | Software detected → score ≥0.95, still high |
| `test_missing_metadata` | Two missing fields → correct penalty sum |
| `test_timestamp_plus_software` | Timestamp issues → medium reliability |
| `test_heavy_tampering` | Multiple severe indicators → low/very_low, tampering suspected |
| `test_extraction_failed` | Metadata extraction failed → 0.25 penalty |
| `test_continuous_ela_elevated` | ELA std 50 → continuous adjustment applied |
| `test_continuous_noise_elevated` | Noise CV 0.42 → continuous adjustment applied |
| `test_no_continuous_on_clean` | Clean metrics → no adjustments, score 1.0 |
| `test_score_floor` | All indicators stacked → score 0.0 (not negative) |
| `test_unknown_indicator` | Undefined indicator → default 0.02 penalty |
| `test_custom_threshold` | Strict threshold changes tampering_suspected |

```
PASS: clean image — score 1.0, high reliability
PASS: software detected — minimal penalty, still high
PASS: missing metadata — moderate penalty
PASS: timestamp issues + software — medium reliability
PASS: heavy tampering — low score, tampering suspected
PASS: extraction failed — 0.25 penalty applied
PASS: continuous ELA adjustment applied
PASS: continuous noise adjustment applied
PASS: no continuous adjustments on clean metrics
PASS: score floor at 0.0
PASS: unknown indicator — default 0.02 penalty
PASS: custom tampering threshold works

=== ALL PHASE 4 TESTS PASSED ===
```

---

## Upcoming Phases

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
| 2026-09-05 | 3 | Image forensic indicators: ELA, noise consistency, channel stats, JPEG quality, structure analysis |
| 2026-09-05 | 4 | Forensic reliability engine: weighted scoring, continuous adjustments, reliability levels |
