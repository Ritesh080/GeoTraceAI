# GeoTrace local visual model

For production updates, prefer the atomic bundle workflow in `backend/README.md` instead of replacing these files one by one. It preserves the last working set if a build fails and records source licences, duplicate hashes, counts, and spatial coverage.

The generated `geotrace_visual_v0.npz` file belongs here by default. It is not
included because a useful model must be trained from a geographically diverse,
properly licensed set of reference images.

Use `backend/training_manifest.example.csv` as the manifest format, then run:

```sh
.venv/bin/python -m backend.train_visual_model path/to/manifest.csv
```

For meaningful evaluation, keep test images and near-duplicates out of the
training set and score distance thresholds on a separate labelled test set.

## Offline place index

`geotrace_places_v0.npz` is the local map-context index. Build it from a
GeoNames `cities*.txt` dump and optional `countryInfo.txt` file:

```sh
.venv/bin/python -m backend.build_map_index path/to/cities5000.txt \
  --country-info path/to/countryInfo.txt
```

GeoNames data is licensed under CC BY 4.0. Keep the attribution shown by the
GeoTrace interface when presenting map-verification results.

## Street-level imagery index

`geotrace_street_v0.npz` is built from a CSV based on
`backend/street_manifest.example.csv`:

```sh
.venv/bin/python -m backend.build_street_index path/to/street_manifest.csv
```

Every row must include the reference image's licence, attribution, source URL,
coordinates, and a unique ID. The generated index is intentionally ignored by
Git because imagery rights and distribution conditions vary by corpus. If the
corpus contains KartaView imagery, preserve `© Grab and KartaView Contributors`
and comply with CC BY-SA 4.0 when storing or sharing the corpus and index.

## Source-provenance index

`geotrace_provenance_v0.npz` is the private reverse-image index. Build it from
a CSV based on `backend/provenance_manifest.example.csv`:

```sh
.venv/bin/python -m backend.build_provenance_index path/to/provenance_manifest.csv
```

Each row requires a stable reference ID, source URL, publication time, licence,
attribution, and origin group. Put reposts and derivatives of one original in
the same origin group. The generated index is ignored by Git because source
corpora have different distribution rights.

## Location calibration

`geotrace_calibration_v0.npz` and `geotrace_benchmark_report_v0.json` are built
from a held-out manifest based on `backend/benchmark_manifest.example.csv`:

```sh
.venv/bin/python -m backend.calibrate_location_model path/to/benchmark_manifest.csv
```

Use at least 50 geographically diverse examples with no training-image overlap.
The evaluator segments results by `scene` and `condition`; use concrete values
such as `urban`, `rural`, `indoor`, `daylight`, `night`, `rain`, or `low_quality`.
Calibration is valid only for the exact visual-model fingerprint it records.
