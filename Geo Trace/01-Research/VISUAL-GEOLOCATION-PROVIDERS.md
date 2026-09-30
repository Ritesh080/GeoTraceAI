# Visual geolocation providers

Updated: 2026-09-30

## Oceanir

The documented API accepts a base64-encoded image at
`POST https://oceanir.ai/api/v1/geolocate`, supports analysis depths 1 through
3, and returns coordinates plus optional reasoning and visual clues. It accepts
an API key through `x-api-key`. Remote calls may consume provider credits.

- https://docs.oceanir.ai/quickstart
- https://docs.oceanir.ai/api-reference
- https://docs.oceanir.ai/authentication

## GeoSpy and Graylark

Graylark's developer documentation exposes the GeoSpy endpoint at
`POST https://dev.geospy.ai/predict_v1` with a bearer token and base64 image.
Older documented responses use `geo_predictions` and `[latitude, longitude]`
coordinate arrays, so the adapter accepts both current single-result and legacy
multi-result shapes.

- https://dev.geospy.ai/docs/routes
- https://dev.geospy.ai/docs/api/image-geolocate-predict

## Raven

Raven is associated with Graylark's newer product offering. No separate public
developer contract was integrated. GeoTrace therefore counts the Graylark
family once through the `geospy` adapter. This prevents GeoSpy and Raven labels
from being mistaken for independent corroboration.
