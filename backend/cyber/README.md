# GeoTrace cyber image pipeline

The pipeline validates an image, calculates its SHA-256 digest, extracts EXIF
metadata, and combines available geolocation evidence:

1. embedded EXIF GPS coordinates;
2. local GeoCLIP candidates;
3. on-device Apple Vision OCR and Indian-script detection;
4. local image characteristics and a perceptual hash;
5. a distance-based consensus that preserves the underlying evidence.

Consensus favors independent provider agreement. It does not turn retrieval
scores or provider agreement into a synthetic confidence percentage.

## Setup

GeoCLIP supports Python 3.10 through 3.13. From the repository root:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/cyber/requirements.txt
```

The first GeoCLIP run can download model assets. Later calls reuse one model
instance for the lifetime of the Python process.

## Run

```sh
.venv/bin/python backend/cyber/main.py datasets/test_images/image.png
```

### Local web interface

The [OSINT case workspace](OSINT_CASES.md) is available at `/osint` on the local
server. It supports sourced CSV/JSON records, name/phone search, case roles,
revocation, and an audit trail. Case records and keys are excluded from Git.

Start the dependency-free browser interface from the repository root:

```sh
.venv/bin/python backend/cyber/web_app.py
```

Then open `http://127.0.0.1:8787`. The server accepts JPEG, PNG, and WebP
uploads up to 20 MB, deletes its temporary upload after analysis, and listens
only on the local machine by default. GeoCLIP is enabled in the interface;
all analysis remains local. The **Social media evidence** tab records the
public source URL, platform, account reference, case reference, capture time,
and collection note. The image is optional for social-media evidence: GeoTrace
can analyze the caption, hashtags, displayed location, and collection note as
text-only evidence. Add an image when visual, OCR, EXIF, or hashing evidence is
available. GeoTrace does not log into the platform or fetch private content.

For a public post, leave **Analyze public link automatically** selected.
GeoTrace reads public page metadata and, when exposed, downloads its Open Graph
or Twitter preview image. It records the resolved page and image URLs plus
collection time, analyzes any temporary image, and deletes it. If the page has
no public preview image, its available title, description, hashtags, and
structured location can still enter text analysis. The collector rejects local/private network destinations,
credential-bearing URLs, unsupported image formats, and oversized responses.
Pages that require login, client-side rendering, or do not publish a preview
image must still be supplied as an operator-captured screenshot or frame.

Instagram may return its generic login-page artwork instead of the requested
post image. GeoTrace detects that fallback, excludes it from GeoCLIP and OCR,
and records an abstention. For social evidence, coordinates are displayed only
when independent evidence channels agree or embedded GPS is available.

Social evidence is analyzed multimodally. GeoTrace combines the displayed
location tag, caption, hashtags, public-page title/description, structured page
location, explicit coordinates, and on-image OCR with GeoCLIP. A local
GeoNames India index resolves textual place mentions and participates in the
same geographic consensus as visual candidates.

Build or refresh the local India index:

```sh
.venv/bin/python backend/cyber/build_india_gazetteer.py --refresh
```

The current generated database contains about 660,000 Indian geographic
features and more than one million names and aliases. Generated data is kept
outside Git. Place data is provided by GeoNames under CC BY 4.0.

The interface reports **evidence coverage**, which describes the available
evidence channels. It is not a probability that a location is correct. A
caption, hashtag, or displayed location may refer to somewhere other than the
image's capture location.

Use another local port if needed:

```sh
.venv/bin/python backend/cyber/web_app.py --port 8788
```

Return a different number of candidates:

```sh
.venv/bin/python backend/cyber/main.py datasets/test_images/image.png --top-k 10
```

Run only the lightweight cyber stages:

```sh
.venv/bin/python backend/cyber/main.py datasets/test_images/image.png --skip-geoclip
```

Skip local OCR when it is not needed:

```sh
.venv/bin/python backend/cyber/main.py datasets/test_images/image.png --skip-ocr
```

The JSON result reports `geolocation.privacy.processing_mode: local_only` and
`geolocation.privacy.image_shared_externally: false`. The initial OCR run
compiles a small Apple Vision helper into the operating-system temporary
directory; later runs reuse that local binary.

Set `GEOTRACE_GEOCLIP_DEVICE` to `cpu`, `mps`, or `cuda` to override automatic
device selection. GeoCLIP scores are useful for ranking its candidates, but
they are not calibrated real-world confidence estimates.

## Tests

```sh
cd backend/cyber
../../.venv/bin/python -m unittest discover -p 'test_*.py'
```
