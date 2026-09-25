# GeoTrace + God's Eye View integration

## Decision

Use God's Eye View as a separate, optional **Area view** opened from a GeoTrace
location candidate. Keep image upload, social-link import, forensic processing,
candidate ranking, and reporting inside GeoTrace.

This preserves the simple GeoTrace workflow and prevents a large real-time
globe from slowing down the image-analysis screen. The companion viewer may be
self-hosted from the upstream MIT-licensed project:

https://github.com/bilawalsidhu/gods-eye-view

## First integration slice

GeoTrace includes `backend/gods_eye_context.py`. When
`GEOTRACE_GODS_EYE_URL` points to a reviewed companion deployment, every
coordinate-bearing candidate receives a God's Eye View version-2 camera link.
The link carries latitude, longitude, altitude, heading, pitch, visual style,
HUD state, and map choice in the URL fragment used by the upstream project.

Example configuration:

```text
GEOTRACE_GODS_EYE_URL=https://area-view.example.org
```

The adapter accepts HTTPS deployments and local HTTP development URLs. It does
not call the viewer, copy its feeds into GeoTrace, or count a live layer as
location evidence.

## Recommended product flow

1. The investigator uploads an image or imports a permitted social post.
2. GeoTrace produces candidate coordinates and its normal evidence record.
3. The result shows **Open area view** only for candidates with coordinates.
4. The separate viewer opens at that candidate.
5. The investigator records useful findings back in the Micro-OSINT ledger
   with source, retrieval time, and limitations.

## Useful layers

- satellite imagery and terrain for roads, landform, coastlines, and ridges;
- public CCTV for a current ground-level comparison;
- weather, clouds, wind, fire, and perimeter layers for time-sensitive context;
- traffic and transit for road and infrastructure checks;
- aircraft or vessel layers when the case facts make them relevant;
- recent imagery where its licence and capture time are suitable for the case.

Live feeds are investigative context. A current aircraft, camera, weather
event, or vessel does not prove the capture location or time of an older image.

## Evidence capture

For an Area-view observation retained in a case, record the candidate and
coordinates, original provider, query and provider timestamps, source URL or
record ID, attribution, licence, screenshot or exported-record hash, analyst
observation, inference, verification status, and whether the layer was live,
delayed, simulated, estimated, or reconstructed.

This belongs in GeoTrace's Micro-OSINT ledger and must not silently increase
model confidence.

## Licensing and security

God's Eye View code is MIT licensed. Its bundled and live datasets retain their
own terms. Attribution must remain visible. The upstream bundled TeleGeography
submarine-cable data is CC BY-NC-SA and must be removed or separately licensed
for commercial use.

API keys and paid-provider credentials should stay in the companion viewer's
server-side proxy. Browser-exposed Cesium or Google keys must be restricted by
origin and quota. GeoTrace should store provider references and case evidence,
not provider secrets.

## Later phases

1. Show **Open area view** in the GeoTrace result once a reviewed viewer is configured.
2. Import a cited Area-view finding into the Micro-OSINT ledger.
3. Export active layers, camera position, timestamps, attribution, and hashes.
4. Add historical playback for sources with defensible archives and clear terms.

Named-person search, face recognition, and individual tracking remain outside
this integration. The upstream project follows the same boundary.
