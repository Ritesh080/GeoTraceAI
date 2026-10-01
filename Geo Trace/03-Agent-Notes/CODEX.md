# Codex handoffs

## 2026-10-01 · P-12 authorized-record case OSINT

- Added `case_osint_service.py`, `/osint`, and local `/api/osint/*` routes for
  CSV/JSON imports, name/phone search, case roles, revocation and audit export.
- Every import records its source, observation time, access basis, authorization
  reference, importing investigator and evidence-envelope hash. Invalid batches
  roll back; duplicate evidence is skipped. Distinct matches are never merged.
- Case keys are hashed in a mode-600 SQLite database under ignored
  `data/osint/`. Foreign browser origins and public server bindings are rejected.
- Checks: 33 cyber tests (13 OSINT-specific), 25 root tests, 30 backend tests,
  and 2 CSV parser tests pass. Syntax/compile checks pass; the browser shows the
  new case workspace without console errors. HTTP tests import and search
  synthetic business contacts and exercise authentication, isolation and roles.
- No real cases or identifiers were seeded. External sources are not connected;
  users import records they are authorized to use. This is a local prototype
  with named bearer keys, not institutional SSO or encrypted database storage.
- Next action: create the user's case, import its approved source records, and
  add an institution-specific connector only after its access contract is known.

Workspace setup created the shared notes from the observed repository. Connection verification is recorded in [[SETUP]].

## 2026-09-30 · P-04 provider integration

- Changed: `backend/cyber/main.py`, `remote_geolocation.py`,
  `consensus_service.py`, `README.md`, two new test modules, and shared project
  notes.
- Findings: GeoCLIP runs successfully on Apple MPS. Oceanir and
  GeoSpy/Graylark require provider credentials for live verification. Raven is
  represented by the Graylark provider family until a separate API is supplied.
- Checks: 8 unit tests pass; all cyber Python modules compile; CLI help works;
  a no-credential remote-provider run shared no image; a real GeoCLIP run
  returned three candidates and a valid consensus result.
- Blocker: none for local use. Live remote verification depends on the user's
  decision to configure a provider account/key.
- Next action: run one approved provider against a non-sensitive test image and
  adjust normalization only if its live response differs from the documented
  contract.

## 2026-09-30 · P-05 local web interface

- Changed: `backend/cyber/web_app.py`, `backend/cyber/web/index.html`, the
  cyber README, and shared architecture, context, tasks, and handoff notes.
- Findings: no prior web application or web-framework dependency existed.
- Checks: Python compilation passed; `/api/health` returned healthy; `/`
  served the expected title; a multipart upload without GeoCLIP completed
  locally; a second upload ran real GeoCLIP inference on Apple MPS and returned
  ranked consensus candidates. Remote credentials were absent and no image was
  shared externally.
- Runtime: server started on `http://127.0.0.1:8787` and left running for user
  review.
- Next action: use the browser to upload an authorized test image. Configure a
  remote provider only after the user approves the credential step.

## 2026-09-30 · P-06 local technology and social evidence

- Changed: removed commercial-provider controls from the active CLI and web
  interface and deleted the unused remote adapter; added
  `local_clue_service.py`, an Apple Vision OCR helper,
  Indian-script detection, image characteristics, perceptual hashing, and a
  social-media evidence intake tab.
- Social behavior: records an operator-supplied public URL, platform, account
  reference, case reference, capture time, and collection note alongside the
  uploaded screenshot/frame. It does not fetch or authenticate to a platform.
- Checks: local clue and existing tests pass; Apple Vision helper compiled and
  ran locally; health reports `local_only`; a social-media multipart upload
  preserved its provenance and returned `image_shared_externally: false`.
- Runtime: refreshed server is running at `http://127.0.0.1:8787`.
- Next action: curate lawful India-specific reference imagery and build a local
  embedding index for regional and street-level retrieval.

## 2026-09-30 · P-07 automatic public collection

- Changed: added `social_collection_service.py` and exposed **Collect public
  preview automatically** in the social-media evidence form.
- Behavior: accepts a public post or direct-image URL, resolves a public Open
  Graph/Twitter preview, records page/image URLs and UTC collection time,
  analyzes the temporary file, and deletes it afterward.
- Controls: blocks URL credentials and non-public network addresses, validates
  redirects, caps HTML at 2 MB and images at 20 MB, and accepts JPEG, PNG, or
  WebP only. It does not log in or bypass access controls.
- Checks: automatic collection unit coverage passes; a live public PNG was
  collected successfully without a platform API.
- Next action: add platform-specific public-page parsers only where permitted
  and needed because client-rendered or login-gated pages will require an
  operator-supplied capture.

## 2026-09-30 · P-08 multimodal Instagram location evidence

- Research: reviewed hierarchical visual geolocation, landmark retrieval,
  scene-text recognition, and multimodal Instagram image/caption/hashtag work.
- Changed: added a reproducible GeoNames India index builder, local text-place
  matching, explicit-coordinate parsing, caption/hashtag/location inputs,
  structured public-page clues, and an evidence-coverage assessment.
- Local data: current index contains 660,026 geographic features and 1,061,483
  aliases; the 177 MB generated SQLite database and source archive are ignored
  by Git and attributed to GeoNames under CC BY 4.0.
- Checks: all 15 unit tests pass, all cyber Python modules compile, the inline
  browser script passes `node --check`, and the local health endpoint responds.
  An end-to-end Instagram-style upload with `#NewDelhi` and `India Gate`
  produced a Delhi cluster corroborated independently by GeoCLIP and the local
  text gazetteer. The UI exposed the evidence assessment and cautions.
- Limitation: reliable street-level visual matching still depends on a large,
  lawfully sourced geotagged image gallery. No system can recover a location
  when the post contains no usable location signal.

## 2026-09-30 · P-09 optional image for social evidence

- Changed: social-media cases can now run from the public URL, caption,
  hashtags, displayed location, and collection note without an uploaded image.
- Behavior: image-only channels are marked skipped, the file is marked not
  provided, and text candidates still enter consensus and evidence assessment.
- Direct image analysis continues to require an image.
- Follow-up: public-link analysis is now the default social collection mode,
  and public page metadata is retained for text analysis even when the page
  exposes no preview image. An insufficient result explains that a link alone
  contained no usable location signal.

## 2026-09-30 · P-10 GitHub integration

- Integrated the local multimodal social-evidence implementation with the 14
  newer commits on `origin/main`.
- Preserved GitHub's normalized metadata, image-forensics, and reliability
  output while adding GeoCLIP, local OCR clues, India text-place matching, and
  evidence consensus to the same cyber result.
- Excluded generated GeoNames databases, downloaded archives, Finder metadata,
  Obsidian plugin state and agent session transcripts from version control.
- Checks: 18 cyber tests, 25 root tests, and 30 backend tests pass; Python
  compilation, TypeScript checking, and the Next.js production build pass. A
  merged live social upload returned forensic output, visual clues, a Delhi
  text candidate, consensus, and an evidence assessment.
- Next action: monitor the GitHub-triggered deployment and keep the generated
  visual/gazetteer artifacts outside Git unless their licence and size permit
  distribution.

## 2026-09-30 · P-11 false Instagram location prevention

- Finding: unauthenticated Instagram can return its generic login-page image
  and description for a post URL. The collector previously treated that image
  as post media, allowing GeoCLIP to create an unrelated coordinate.
- Changed: generic Instagram platform artwork is rejected before download and
  visual inference. Social coordinates are withheld unless independent
  providers agree or embedded GPS exists; technical candidates remain in the
  raw evidence JSON.
- Checks: 20 cyber tests pass, browser JavaScript parses, and a live request to
  Instagram's generic fallback returned `generic_platform_preview_rejected`,
  skipped GeoCLIP, and produced `abstained_unverified` with no displayed
  location.
