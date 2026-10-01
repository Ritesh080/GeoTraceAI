# Decisions

## 2026-09-19 — Shared workspace
Status: accepted by the user's setup request.

Use the existing Geo Trace vault within the existing repository. Agent Client connects local agents to the same Markdown notes. Preserve existing work. Ask before login, credential/API-key steps, and destructive changes.

## 2026-09-30 — Provider-based geolocation consensus
Status: superseded for the active product by the local-only decision below.

Keep EXIF GPS and GeoCLIP local. Treat Oceanir and GeoSpy/Graylark as optional,
explicitly enabled remote providers. Preserve each provider's candidates and
evidence, cluster nearby coordinates, and rank independent agreement without
inventing a confidence percentage. Keep remote credentials in environment
variables and report whether image bytes were shared externally.

Raven and GeoSpy are treated as part of Graylark's product family rather than
as two independent votes. The current public developer contract uses the
GeoSpy adapter. A separate Raven adapter should be added only when Graylark
provides a distinct endpoint and response contract.

## 2026-09-30 — Local-first GeoTrace technology
Status: accepted by the user's explicit direction not to use Oceanir, GeoSpy,
Raven, or Graylark APIs.

The active CLI and browser pipeline must process evidence locally. Use EXIF,
GeoCLIP, GeoTrace-owned clue extraction, on-device OCR, Indian-script clues,
and future India-specific models and reference imagery. Do not expose vendor
API controls in the product.

Social-media intake records provenance for an operator-supplied public post,
screenshot, or video frame. It does not bypass access controls, log into user
accounts, or treat an account association or model location as verified fact.
Automatic collection may retrieve a page's publicly exposed preview image. It
must reject private-network destinations, credential-bearing URLs, oversized
responses, unsupported formats, and pages that do not expose public media.

Social-post location inference must be multimodal. Keep caption/location tags,
page metadata, OCR, EXIF, and visual-model output as distinct evidence. Resolve
text against a local India gazetteer and call a result corroborated only when
independent evidence channels agree geographically. Never represent evidence
coverage or heuristic text strength as calibrated location probability.

Do not display a social-post coordinate as a location conclusion when only one
uncorroborated location channel returned it. Display a lead only after
independent geographic agreement or embedded GPS, and reject generic platform
or login-page artwork before visual inference.

## 2026-10-01 — Authorized case-record OSINT
Status: accepted by the user's explicit narrowed module request.

Implement name/phone searches over case-scoped authorized records and published
business contacts. Require source and access provenance on imports. Preserve
email/payment identifiers as unverified source claims, keep ambiguous records
separate, and never infer identity solely from name or phone matching. Enable
the case API only through a loopback binding. Keep keys and case records out
of Git, enforce roles server-side, and audit access. No leaked-record collection
or automatic external source search is included.

## Decision template
- Date and title:
- Status: proposed / accepted / superseded
- Context:
- Decision:
- Consequences:
- User approval or source:
