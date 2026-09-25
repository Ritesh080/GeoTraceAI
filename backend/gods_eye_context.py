"""God's Eye View compatibility adapter for GeoTrace location candidates."""
from __future__ import annotations

import copy
import os
from urllib.parse import urlencode, urlsplit, urlunsplit


def configured_viewer_url() -> str | None:
    raw = os.getenv("GEOTRACE_GODS_EYE_URL", "").strip().rstrip("/")
    if not raw:
        return None
    parsed = urlsplit(raw)
    is_local = parsed.hostname in {"127.0.0.1", "localhost"}
    if parsed.scheme not in ({"http", "https"} if is_local else {"https"}) or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def build_area_view_url(latitude: float, longitude: float, *, altitude_m: int = 5000) -> str | None:
    """Create an upstream version-2 share URL centered on valid coordinates."""
    base_url = configured_viewer_url()
    if base_url is None:
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Coordinates are outside the valid latitude/longitude range.")
    if not 250 <= altitude_m <= 2_000_000:
        raise ValueError("Area-view altitude must be between 250 and 2,000,000 metres.")
    fragment = urlencode({
        "v": "2", "lat": f"{latitude:.4f}", "lon": f"{longitude:.4f}",
        "alt": str(int(altitude_m)), "heading": "0", "pitch": "-35", "roll": "0",
        "style": "normal", "hud": "tactical", "hv": "0", "dm": "OFF", "map": "photoreal",
    })
    return f"{base_url}/#{fragment}"


def attach_area_view_links(osint: dict) -> dict:
    """Add optional companion-view links without changing evidence ranking."""
    enriched = copy.deepcopy(osint)
    enabled = configured_viewer_url() is not None
    linked = 0
    for candidate in enriched.get("candidates") or []:
        latitude, longitude = candidate.get("latitude"), candidate.get("longitude")
        if not isinstance(latitude, (int, float)) or isinstance(latitude, bool):
            continue
        if not isinstance(longitude, (int, float)) or isinstance(longitude, bool):
            continue
        url = build_area_view_url(float(latitude), float(longitude))
        if url:
            candidate["area_view"] = {
                "provider": "God's Eye View companion",
                "url": url,
                "purpose": "Explore public spatial context around this candidate.",
                "evidence_status": "investigative_context_only",
            }
            linked += 1
    enriched["area_view"] = {
        "status": "ready" if enabled else "not_configured",
        "candidate_links": linked,
        "note": "Live layers are investigative context. They do not confirm where the submitted image was captured.",
    }
    return enriched


def area_view_status() -> dict:
    return {
        "enabled": configured_viewer_url() is not None,
        "provider": "God's Eye View",
        "upstream": "https://github.com/bilawalsidhu/gods-eye-view",
        "mode": "separate_companion_viewer",
    }
