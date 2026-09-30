# Architecture

## Implemented pipeline as of 2026-09-30

```text
Image path
  → file_validator.py: existence + MIME validation (python-magic)
  → hash_service.py: SHA-256 over file chunks
  → exif_service.py: exiftool -json subprocess
  → geolocation providers
      → EXIF GPS: local embedded coordinates
      → GeoCLIP: local visual candidate retrieval
  → local_clue_service.py
      → image characteristics + perceptual hash
      → cached Apple Vision OCR helper
      → Indian-script detection
  → text_location_service.py
      → caption + hashtag + page metadata + OCR place extraction
      → local GeoNames India alias lookup
      → text candidates joined to geographic consensus
  → consensus_service.py: distance-clustered independent-provider agreement
  → main.py: evidence-preserving JSON result with privacy status
  → web_app.py: localhost HTTP upload/API boundary
  → social_collection_service.py: restricted public-page preview acquisition
  → web/index.html: investigator-facing upload and candidate review interface
```

`main.py` takes one image path. Rejected validation returns a rejected result;
accepted input returns hash, file information, extracted metadata, provider
results, consensus clusters, and whether the image was shared externally.

The active CLI and web paths run locally and report
`image_shared_externally: false`. The earlier commercial-provider adapters and
their tests were removed from the product source.

The consensus layer groups candidates within a configurable radius. Each
provider can contribute at most one candidate to a cluster, so one provider's
top-k list cannot manufacture agreement. Provider count is ranked before
candidate rank. The result does not claim a calibrated probability.

The local web server binds to `127.0.0.1:8787`, accepts supported images up to
20 MB, and deletes each temporary upload after analysis. Its social-media
evidence mode records operator-supplied public-source provenance alongside an
uploaded screenshot or frame. It does not log into social networks or collect
private content. Automatic mode resolves a public page's Open Graph or Twitter
preview image, validates every public URL and redirect, limits response sizes,
records provenance, and analyzes only the temporary media. The browser exposes
the full technical JSON for review.

The social workflow fuses operator-supplied caption/location text, public page
metadata, structured page coordinates, hashtags, and on-image OCR. A generated
local SQLite index contains roughly 660,000 Indian geographic features and
1.06 million names/aliases from GeoNames. Text candidates and GeoCLIP candidates
remain separate providers; nearby results can form a multi-provider cluster.
Evidence coverage reports channel availability rather than correctness.
The social UI abstains from displaying coordinates when a lead has only one
uncorroborated source. Instagram login-page/platform artwork is rejected before
visual inference so GeoCLIP cannot assign a location to a generic preview.

## Layout
- `../backend/cyber/`: current Python implementation
- `../datasets/test_images/`: local sample images
- `../tests/`: test directory
- This vault: shared planning, research, decisions, and handoffs

## Dependencies observed
Python, `python-magic`/libmagic, `exiftool`, PyTorch, GeoCLIP, Pillow, and Apple
Vision through a locally compiled Swift helper. The existing `.venv` is in the
repository root.

## Current limitation
India-specific reference imagery and a locally trained street-level retrieval
index do not yet exist. Current localization comes from the local pretrained
GeoCLIP model and text place-name matching, while OCR and image characteristics
provide reviewable clues. Broad street-level visual retrieval still requires a
lawfully sourced geotagged image gallery.
