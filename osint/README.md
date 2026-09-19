# OSINT integration

This folder explains how GeoTrace AI uses public-source evidence to verify an image-location hypothesis. OSINT is a separate evidence branch; it does not turn a search result into proof and does not treat several reposts of one image as independent confirmation.

The full architecture is documented in [`INTEGRATED_PIPELINE.md`](INTEGRATED_PIPELINE.md).

## What is implemented

The website currently performs these operations without automatically uploading the selected image:

1. Calculate the exact SHA-256 fingerprint.
2. Extract browser-side EXIF and GPS metadata.
3. Run English OCR and label the dominant writing system.
4. Generate exact-hash, text-search, map, Google Lens, and TinEye review actions.
5. Keep file, EXIF, OCR, and forensic observations in the submitted-image dependency group.
6. Return `candidate_needs_corroboration` for embedded GPS or `insufficient_evidence` when no usable coordinate exists.

The Python API adds ExifTool metadata extraction, magic-byte validation, image-forensic indicators, and a forensic reliability score. That score measures trust in the submitted file; it is not a probability that a location is correct.

## Source-dependency rule

Evidence created from one uploaded image shares one origin. Hash output, EXIF, OCR, image embeddings, crops, and forensic measurements must not be counted as separate independent sources. Reposts and pages that copy one publication belong to a common lineage group when that relationship can be established.

Independent corroboration requires a separately sourced observation, such as a verified reference image, authoritative map record, or public page with preserved provenance. Different domains alone do not establish independence.

## Contradiction handling

The planned conflict ledger records:

- GPS versus landmark or scene evidence supporting incompatible regions.
- OCR place names versus the visual environment.
- Claimed capture time versus documented publication history.
- A clue derived from a suspicious image region or questionable metadata.
- Several apparent confirmations resolving to one shared source.

Conflicts remain visible after fusion. The system must abstain when a high-impact conflict is unresolved or removing one source group changes the leading candidate.

## Uncertainty policy

GeoTrace AI currently avoids a location-confidence number unless a calibrator has been fitted on a separate labelled dataset produced by the same retrieval and fusion policy. Until that work exists, outcomes are qualitative:

- `candidate_needs_corroboration`
- `insufficient_evidence`
- future `supported_location_hypothesis`

The current browser pipeline never converts OCR confidence, forensic reliability, or embedded GPS into a calibrated location probability.

## Provider boundaries

Google Lens and TinEye are manual review links. Automated reverse-image or landmark results require an authorized provider API called from the hosted backend so credentials are not exposed in browser code. External image transmission must be explicit and recorded in the case audit trail.

## Next engineering steps

1. Deploy the containerized Python API and connect its HTTPS origin to the website.
2. Add one authorized landmark/scene provider behind a normalized adapter.
3. Add source records containing canonical URL, retrieval time, content hash, publication claim, and lineage.
4. Implement typed conflicts and leave-one-source-group-out stability.
5. Collect labelled cases, split them by original media family, and evaluate calibration and selective error.
