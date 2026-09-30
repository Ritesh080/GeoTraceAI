"""Collect public social-media preview images without accounts or vendor APIs."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 20
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class PublicCollectionError(RuntimeError):
    """Raised when public media cannot be safely collected."""


def validate_public_url(
    url: str,
    *,
    resolver: Callable[..., list] = socket.getaddrinfo,
) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise PublicCollectionError("A valid public HTTP or HTTPS URL is required")
    if parsed.username or parsed.password:
        raise PublicCollectionError("URLs containing login credentials are not allowed")
    if parsed.hostname.lower() == "localhost" or parsed.hostname.lower().endswith(".local"):
        raise PublicCollectionError("Local-network URLs are not allowed")

    try:
        addresses = {
            item[4][0]
            for item in resolver(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise PublicCollectionError(f"Could not resolve source host: {exc}") from exc
    if not addresses:
        raise PublicCollectionError("Source host did not resolve to an address")
    for address in addresses:
        try:
            if not ipaddress.ip_address(address).is_global:
                raise PublicCollectionError(
                    "Private, loopback, reserved, and link-local addresses are not allowed"
                )
        except ValueError as exc:
            raise PublicCollectionError("Source host returned an invalid address") from exc
    return parsed.geturl()


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _PreviewParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.canonical: str | None = None
        self.title_parts: list[str] = []
        self.json_ld_parts: list[str] = []
        self._in_title = False
        self._in_json_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs if value is not None}
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            content = values.get("content")
            if key and content and key not in self.meta:
                self.meta[key] = content
        elif tag.lower() == "link" and "canonical" in values.get("rel", "").lower():
            self.canonical = values.get("href")
        elif tag.lower() == "title":
            self._in_title = True
        elif tag.lower() == "script" and values.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
        elif tag.lower() == "script":
            self._in_json_ld = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        elif self._in_json_ld:
            self.json_ld_parts.append(data)


def _structured_location(json_ld_parts: list[str]) -> str | None:
    location_keys = {
        "contentlocation",
        "locationcreated",
        "location",
        "address",
        "placename",
    }
    values: list[str] = []

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                visit(child_value, child_key.casefold())
        elif isinstance(value, list):
            for child in value:
                visit(child, key)
        elif key in location_keys and isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text and text not in values:
                values.append(text)

    for part in json_ld_parts:
        try:
            visit(json.loads(part))
        except json.JSONDecodeError:
            continue
    return ", ".join(values[:12]) or None


def _read_limited(response, limit: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > limit:
                raise PublicCollectionError("Remote content exceeds the size limit")
        except ValueError:
            pass
    payload = response.read(limit + 1)
    if len(payload) > limit:
        raise PublicCollectionError("Remote content exceeds the size limit")
    return payload


def _request(opener, url: str, limit: int) -> tuple[bytes, str, str, Any]:
    validate_public_url(url)
    request = Request(
        url,
        headers={
            "User-Agent": "GeoTrace-Public-Evidence-Collector/0.1",
            "Accept": "text/html,image/jpeg,image/png,image/webp;q=0.9,*/*;q=0.1",
        },
    )
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            final_url = validate_public_url(response.geturl())
            content_type = response.headers.get_content_type().lower()
            return _read_limited(response, limit), content_type, final_url, response.headers
    except PublicCollectionError:
        raise
    except Exception as exc:
        raise PublicCollectionError(f"Public source could not be collected: {exc}") from exc


def _filename(url: str, content_type: str) -> str:
    stem = Path(urlparse(url).path).stem[:80] or "social-media-image"
    return f"{stem}{ALLOWED_IMAGE_TYPES[content_type]}"


def _is_generic_platform_preview(
    source_url: str,
    final_url: str,
    image_url: str,
    page_metadata: dict[str, Any],
) -> bool:
    """Reject platform/login artwork that is not media from the requested post."""

    source_host = (urlparse(source_url).hostname or "").casefold()
    if not source_host.endswith("instagram.com"):
        return False

    title = str(page_metadata.get("title") or "").strip().casefold()
    description = str(page_metadata.get("description") or "").strip().casefold()
    canonical_path = urlparse(
        str(page_metadata.get("canonical_url") or final_url)
    ).path.rstrip("/")
    image_host = (urlparse(image_url).hostname or "").casefold()
    return (
        "create an account or log in to instagram" in description
        or (title == "instagram" and not canonical_path)
        or image_host == "static.cdninstagram.com"
    )


def collect_public_media(source_url: str, *, opener=None) -> dict:
    """Return one public preview image and provenance from a public page or image URL."""

    opener = opener or build_opener(_SafeRedirectHandler())
    page_bytes, content_type, final_url, headers = _request(
        opener, source_url, MAX_IMAGE_BYTES
    )
    page_metadata: dict[str, Any] = {}

    if content_type in ALLOWED_IMAGE_TYPES:
        image_bytes = page_bytes
        image_url = final_url
        image_type = content_type
    elif content_type in {"text/html", "application/xhtml+xml"}:
        if len(page_bytes) > MAX_PAGE_BYTES:
            raise PublicCollectionError("Public page exceeds the 2 MB page limit")
        charset = headers.get_content_charset() or "utf-8"
        parser = _PreviewParser()
        parser.feed(page_bytes.decode(charset, errors="replace"))
        page_metadata = {
            "title": parser.meta.get("og:title")
            or " ".join(parser.title_parts).strip()
            or None,
            "description": parser.meta.get("og:description")
            or parser.meta.get("description"),
            "canonical_url": urljoin(final_url, parser.canonical)
            if parser.canonical
            else final_url,
            "published_time": parser.meta.get("article:published_time"),
            "structured_location": _structured_location(parser.json_ld_parts),
            "latitude": parser.meta.get("place:location:latitude")
            or parser.meta.get("og:latitude"),
            "longitude": parser.meta.get("place:location:longitude")
            or parser.meta.get("og:longitude"),
            "hashtags": sorted(
                set(
                    re.findall(
                        r"#[^\s#]+",
                        " ".join(
                            value
                            for value in (
                                parser.meta.get("og:title"),
                                parser.meta.get("og:description"),
                            )
                            if value
                        ),
                    )
                )
            ),
        }
        image_reference = next(
            (
                parser.meta[key]
                for key in (
                    "og:image:secure_url",
                    "og:image",
                    "twitter:image",
                    "twitter:image:src",
                )
                if parser.meta.get(key)
            ),
            None,
        )
        if not image_reference:
            return {
                "name": "",
                "content_type": None,
                "data": b"",
                "collection": {
                    "method": "automatic_public_page_metadata",
                    "requested_url": source_url,
                    "resolved_page_url": final_url,
                    "resolved_image_url": None,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                    "page": page_metadata,
                    "media_status": "preview_image_not_exposed",
                },
            }
        image_url = urljoin(final_url, image_reference)
        if _is_generic_platform_preview(
            source_url, final_url, image_url, page_metadata
        ):
            return {
                "name": "",
                "content_type": None,
                "data": b"",
                "collection": {
                    "method": "automatic_public_page_metadata",
                    "requested_url": source_url,
                    "resolved_page_url": final_url,
                    "resolved_image_url": image_url,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                    "page": page_metadata,
                    "media_status": "generic_platform_preview_rejected",
                },
            }
        image_bytes, image_type, image_url, _ = _request(
            opener, image_url, MAX_IMAGE_BYTES
        )
        if image_type not in ALLOWED_IMAGE_TYPES:
            raise PublicCollectionError(
                f"Preview media type {image_type!r} is not supported"
            )
    else:
        raise PublicCollectionError(
            f"Public source returned unsupported content type {content_type!r}"
        )

    return {
        "name": _filename(image_url, image_type),
        "content_type": image_type,
        "data": image_bytes,
        "collection": {
            "method": "automatic_public_preview",
            "requested_url": source_url,
            "resolved_page_url": final_url,
            "resolved_image_url": image_url,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "page": page_metadata,
            "media_status": "preview_image_collected",
        },
    }
