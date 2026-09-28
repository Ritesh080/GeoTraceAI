"""Explicit Instagram-post ingestion for the GeoTrace forensic pipeline.

The adapter accepts only a single Instagram post URL. It does not crawl
profiles, hashtags, followers, stories, or arbitrary URLs. Authentication is
optional and, when configured, is loaded from an Instaloader session file.
"""
from __future__ import annotations

import base64
import binascii
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import instaloader

CYBER_DIR = Path(__file__).resolve().parent / "cyber"
if str(CYBER_DIR) not in sys.path:
    sys.path.insert(0, str(CYBER_DIR))

from main import analyze_image  # noqa: E402


MAX_REMOTE_MEDIA_BYTES = 20 * 1024 * 1024
MAX_CAPTION_CHARS = 10_000
MAX_ACCESSIBILITY_CHARS = 2_000
MAX_CAPTION_TERMS = 100
SHORTCODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
ALLOWED_HOSTS = {"instagram.com", "www.instagram.com"}


class InstagramImportError(ValueError):
    """The requested Instagram resource cannot be safely imported."""


class InstagramProviderError(RuntimeError):
    """Instagram or Instaloader could not satisfy the request."""


def extract_shortcode(url: str) -> str:
    """Return a validated shortcode from an Instagram post URL."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in ALLOWED_HOSTS:
        raise InstagramImportError("Use a complete instagram.com post URL.")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0] not in {"p", "reel"}:
        raise InstagramImportError("Use an Instagram post or reel URL.")

    shortcode = parts[1]
    if not SHORTCODE_PATTERN.fullmatch(shortcode):
        raise InstagramImportError("The Instagram shortcode is invalid.")
    return shortcode


def build_loader() -> instaloader.Instaloader:
    """Create an Instaloader client and load an optional saved session."""
    loader = instaloader.Instaloader(
        quiet=True,
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_comments=False,
        save_metadata=False,
        request_timeout=30,
        max_connection_attempts=2,
    )

    username = os.getenv("INSTAGRAM_USERNAME", "").strip()
    session_file = os.getenv("INSTALOADER_SESSION_FILE", "").strip()
    session_base64 = os.getenv("INSTALOADER_SESSION_BASE64", "").strip()
    if session_base64 and not username:
        loader.close()
        raise InstagramImportError("INSTAGRAM_USERNAME is required with the saved Instagram session.")
    if session_base64:
        try:
            session_bytes = base64.b64decode(session_base64, validate=True)
        except (ValueError, binascii.Error) as error:
            loader.close()
            raise InstagramImportError("The configured Instagram session secret is invalid.") from error
        if not session_bytes or len(session_bytes) > 1024 * 1024:
            loader.close()
            raise InstagramImportError("The configured Instagram session secret has an invalid size.")
        session_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, prefix="geotrace-instagram-session-") as temporary:
                temporary.write(session_bytes)
                session_path = Path(temporary.name)
            session_path.chmod(0o600)
            loader.load_session_from_file(username, str(session_path))
        finally:
            if session_path:
                session_path.unlink(missing_ok=True)
    elif username and session_file:
        session_path = Path(session_file).expanduser()
        if not session_path.is_file():
            loader.close()
            raise InstagramImportError("The configured Instaloader session file was not found.")
        loader.load_session_from_file(username, str(session_path))
    return loader


def instagram_provider_status() -> dict:
    """Describe availability without exposing credentials or session material."""
    enabled = os.getenv("GEOTRACE_INSTAGRAM_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    username = os.getenv("INSTAGRAM_USERNAME", "").strip()
    session_base64 = os.getenv("INSTALOADER_SESSION_BASE64", "").strip()
    session_file = os.getenv("INSTALOADER_SESSION_FILE", "").strip()
    session_file_ready = bool(username and session_file and Path(session_file).expanduser().is_file())
    authenticated = bool(username and session_base64) or session_file_ready
    return {
        "status": "active" if enabled else "disabled",
        "enabled": enabled,
        "authenticated": authenticated,
        "mode": "authenticated_session" if authenticated else "public_post_lookup",
        "supports": "single_image_posts",
    }


def _valid_coordinate_pair(latitude: object, longitude: object) -> bool:
    return (
        isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
        and -90 <= float(latitude) <= 90
        and -180 <= float(longitude) <= 180
    )


def _public_location_claim(post: instaloader.Post) -> dict | None:
    """Recover the public place label already present in the post payload.

    Instaloader intentionally returns ``None`` from ``Post.location`` while
    logged out because Instagram requires authentication for its location
    detail request. The post payload can still contain the public location
    name. Preserve that label, but never invent coordinates when the detail
    lookup is unavailable.
    """
    node = getattr(post, "_node", None)
    raw_location = node.get("location") if isinstance(node, dict) else None
    if not isinstance(raw_location, dict) or not raw_location.get("name"):
        return None

    latitude = raw_location.get("lat")
    longitude = raw_location.get("lng")
    coordinates_available = _valid_coordinate_pair(latitude, longitude)
    return {
        "name": str(raw_location["name"])[:240],
        "latitude": float(latitude) if coordinates_available else None,
        "longitude": float(longitude) if coordinates_available else None,
    }


def _location_lookup(post: instaloader.Post) -> dict:
    """Return the exact post claim plus an explicit lookup outcome."""
    public_claim = _public_location_claim(post)
    authenticated = bool(getattr(getattr(post, "_context", None), "is_logged_in", False))
    try:
        location = post.location
    except instaloader.exceptions.InstaloaderException as error:
        return {
            "status": "public_label_only" if public_claim else "lookup_failed",
            "authenticated": authenticated,
            "location": public_claim,
            "detail": (
                "The public post label was recovered, but Instagram blocked the coordinate lookup."
                if public_claim
                else f"Instagram location lookup failed: {type(error).__name__}."
            ),
        }
    if not location:
        return {
            "status": "public_label_only" if public_claim else "not_present" if authenticated else "authentication_required",
            "authenticated": authenticated,
            "location": public_claim,
            "detail": (
                "The post exposes a public place label; sign in to request its coordinates."
                if public_claim
                else "The post has no visible location claim."
                if authenticated
                else "An authenticated Instagram session is required to distinguish no location from a blocked lookup."
            ),
        }

    latitude = location.lat
    longitude = location.lng
    coordinates_available = _valid_coordinate_pair(latitude, longitude)
    return {
        "status": "available",
        "authenticated": authenticated,
        "location": {
            "name": str(location.name)[:240],
            "latitude": float(latitude) if coordinates_available else None,
            "longitude": float(longitude) if coordinates_available else None,
        },
        "detail": "Exact location claim attached to this Instagram post.",
    }


def _post_attribute(post: instaloader.Post, name: str, default: object = None) -> object:
    """Read one Instaloader property without losing the rest of the report."""
    try:
        return getattr(post, name)
    except (instaloader.exceptions.InstaloaderException, AttributeError, KeyError, TypeError, ValueError):
        return default


def _nonnegative_integer(value: object) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _post_metadata(post: instaloader.Post, location_lookup: dict) -> dict:
    """Normalize bounded public post metadata for the forensic response."""
    node = getattr(post, "_node", None)
    dimensions = node.get("dimensions", {}) if isinstance(node, dict) else {}
    if not isinstance(dimensions, dict):
        dimensions = {}

    published_at = _post_attribute(post, "date_utc")
    caption = _post_attribute(post, "caption")
    accessibility_caption = _post_attribute(post, "accessibility_caption")
    hashtags = _post_attribute(post, "caption_hashtags", [])
    mentions = _post_attribute(post, "caption_mentions", [])

    return {
        "shortcode": str(_post_attribute(post, "shortcode", ""))[:120] or None,
        "owner_username": str(_post_attribute(post, "owner_username", ""))[:120] or None,
        "published_at_utc": published_at.isoformat() if isinstance(published_at, datetime) else None,
        "media_type": str(_post_attribute(post, "typename", ""))[:80] or None,
        "media_count": _nonnegative_integer(_post_attribute(post, "mediacount")),
        "is_video": bool(_post_attribute(post, "is_video", False)),
        "width": _nonnegative_integer(dimensions.get("width")),
        "height": _nonnegative_integer(dimensions.get("height")),
        "likes": _nonnegative_integer(_post_attribute(post, "likes")),
        "comments": _nonnegative_integer(_post_attribute(post, "comments")),
        "caption": str(caption)[:MAX_CAPTION_CHARS] if caption else None,
        "hashtags": [str(value)[:100] for value in hashtags[:MAX_CAPTION_TERMS]] if isinstance(hashtags, list) else [],
        "mentions": [str(value)[:100] for value in mentions[:MAX_CAPTION_TERMS]] if isinstance(mentions, list) else [],
        "accessibility_caption": (
            str(accessibility_caption)[:MAX_ACCESSIBILITY_CHARS]
            if accessibility_caption else None
        ),
        "location": location_lookup.get("location"),
        "location_status": location_lookup.get("status"),
        "authenticated_lookup": bool(location_lookup.get("authenticated")),
        "evidence_note": (
            "Platform-supplied post metadata captured at retrieval time; engagement counts can change "
            "and location remains an unverified platform claim."
        ),
    }


def analyze_instagram_post(url: str) -> dict:
    """Fetch one Instagram image post and run the existing GeoTrace pipeline."""
    shortcode = extract_shortcode(url)
    loader = build_loader()
    temporary_path: str | None = None

    try:
        try:
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
        except instaloader.exceptions.InstaloaderException as error:
            raise InstagramProviderError(f"Instagram post lookup failed: {error}") from error

        if post.typename != "GraphImage":
            raise InstagramImportError(
                "This experiment currently supports single-image Instagram posts only."
            )

        try:
            response = loader.context.get_raw(post.url)
        except instaloader.exceptions.InstaloaderException as error:
            raise InstagramProviderError(f"Instagram media download failed: {error}") from error

        payload = response.content
        if not payload:
            raise InstagramProviderError("Instagram returned an empty media file.")
        if len(payload) > MAX_REMOTE_MEDIA_BYTES:
            raise InstagramImportError("The Instagram image exceeds the 20 MB limit.")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temporary:
            temporary.write(payload)
            temporary_path = temporary.name

        result = analyze_image(temporary_path)
        if result.get("status") == "rejected":
            reason = result.get("file", {}).get("reason", "Instagram returned an invalid image.")
            raise InstagramImportError(reason)

        # Avoid returning temporary server paths and the large raw ExifTool dump.
        result.pop("raw_exif", None)
        location_lookup = _location_lookup(post)
        post_metadata = _post_metadata(post, location_lookup)
        result["source"] = {
            "platform": "instagram",
            "source_group": f"instagram:{shortcode}",
            "canonical_url": f"https://www.instagram.com/p/{shortcode}/",
            "shortcode": shortcode,
            "owner_username": post.owner_username,
            "published_at": post.date_utc.isoformat(),
            "caption": post.caption,
            "media_type": post.typename,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "location": location_lookup["location"],
            "location_lookup": {
                "status": location_lookup["status"],
                "authenticated": location_lookup["authenticated"],
                "detail": location_lookup["detail"],
            },
            "post_metadata": post_metadata,
        }
        return result
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
        loader.close()
