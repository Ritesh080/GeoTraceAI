"""Bounded OSINTgram adapter for automatic Instagram-link evaluation.

GeoTrace talks to a separately running OSINTgram service instead of copying
its GPL-licensed implementation. Only a small, read-only command set is run,
and only normalized public fields are returned to the GeoTrace report.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._]{1,30}$")
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
PROFILE_FIELDS = {
    "username", "full_name", "biography", "follower_count", "following_count",
    "media_count", "is_private", "is_business", "is_verified", "category_name",
    "public_email", "public_phone_country_code", "public_phone_number",
    "business_contact_method", "address_street", "city_name", "zip", "latitude",
    "longitude", "external_url", "bio_links", "pronouns",
}
ACCOUNT_FIELDS = {
    "username", "is_verified", "country", "date_joined",
    "former_usernames_count", "former_usernames",
}


def osintgram_provider_status() -> dict:
    base_url = os.getenv("GEOTRACE_OSINTGRAM_URL", "").strip().rstrip("/")
    parsed = urlparse(base_url) if base_url else None
    configured = bool(
        parsed
        and parsed.scheme in {"http", "https"}
        and parsed.hostname
        and not parsed.username
        and not parsed.password
    )
    return {
        "status": "active" if configured else "not_configured",
        "enabled": configured,
        "mode": "automatic_profile_context",
        "commands": ["get_user_info", "get_account_about", "get_hashtags", "get_addrs"],
        "note": "Runs automatically for Instagram post links; the image is not sent to OSINTgram.",
    }


def _request_osintgram(username: str) -> dict:
    base_url = os.getenv("GEOTRACE_OSINTGRAM_URL", "").strip().rstrip("/")
    timeout = max(5, min(int(os.getenv("GEOTRACE_OSINTGRAM_TIMEOUT_SECONDS", "75")), 180))
    payload = json.dumps({
        "target": username,
        "max_items": 24,
        "cache_ttl_seconds": 3600,
        "calls": [
            {"name": "get_user_info"},
            {"name": "get_account_about"},
            {"name": "get_hashtags", "args": {"limit_posts": 24}},
            {"name": "get_addrs", "args": {"limit_posts": 24}},
        ],
    }).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    token = os.getenv("GEOTRACE_OSINTGRAM_BEARER_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{base_url}/api/run", data=payload, headers=headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("OSINTgram response exceeded the safe size limit.")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("OSINTgram returned an invalid response.")
    return data


def _clean_profile(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    return {
        key: field for key, field in value.items()
        if key in PROFILE_FIELDS and field not in (None, "", [], {})
    }


def _clean_account_about(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    return {
        key: field for key, field in value.items()
        if key in ACCOUNT_FIELDS and field not in (None, "", [], {})
    }


def _clean_hashtags(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value[:12]:
        if not isinstance(item, dict) or not item.get("hashtag"):
            continue
        cleaned.append({
            "hashtag": str(item["hashtag"])[:100],
            "count": int(item.get("count") or 0),
        })
    return cleaned


def _clean_locations(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value[:20]:
        if not isinstance(item, dict):
            continue
        latitude, longitude = item.get("lat"), item.get("lng")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            continue
        if abs(latitude) > 90 or abs(longitude) > 180:
            continue
        cleaned.append({
            "name": str(item.get("name") or "Tagged location")[:160],
            "address": str(item.get("address") or "")[:300] or None,
            "latitude": float(latitude),
            "longitude": float(longitude),
            "posted_at": str(item.get("time") or "")[:40] or None,
        })
    return cleaned


def analyze_osintgram_account(username: str) -> dict:
    """Run the safe automatic command set and return a normalized report."""
    username = username.strip().lstrip("@")
    if not USERNAME_PATTERN.fullmatch(username):
        return {
            "status": "unavailable", "provider": "OSINTgram",
            "username": username, "errors": ["Invalid Instagram username."],
        }
    if not osintgram_provider_status()["enabled"]:
        return {
            "status": "not_configured", "provider": "OSINTgram",
            "username": username, "errors": [],
        }

    try:
        response = _request_osintgram(username)
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
        return {
            "status": "unavailable",
            "provider": "OSINTgram",
            "username": username,
            "errors": [f"Automatic OSINTgram lookup failed: {str(error)[:240]}"],
        }

    results: dict[str, object] = {}
    errors: list[str] = []
    for call in response.get("tool_calls", []):
        if not isinstance(call, dict):
            continue
        name = str(call.get("name") or "")
        result = call.get("result")
        if call.get("is_error") or (isinstance(result, dict) and result.get("error")):
            detail = result.get("error") if isinstance(result, dict) else result
            errors.append(f"{name}: {str(detail)[:200]}")
            continue
        results[name] = result

    profile = _clean_profile(results.get("get_user_info"))
    account_about = _clean_account_about(results.get("get_account_about"))
    hashtags = _clean_hashtags(results.get("get_hashtags"))
    locations = _clean_locations(results.get("get_addrs"))
    available = bool(profile or account_about or hashtags or locations)
    return {
        "status": "ready" if available and not errors else "partial" if available else "unavailable",
        "provider": "OSINTgram",
        "username": username,
        "backend": response.get("backend"),
        "profile": profile,
        "account_about": account_about,
        "hashtags": hashtags,
        "locations": locations,
        "errors": errors,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "evidence_note": "Public Instagram account context; it does not independently prove the image location.",
    }
