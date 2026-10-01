"""Local web interface for the GeoTrace image-analysis pipeline."""

from __future__ import annotations

import argparse
import ipaddress
import json
import tempfile
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from main import analyze_image, analyze_text_evidence
from evidence_assessment_service import assess_social_evidence
from social_collection_service import PublicCollectionError, collect_public_media
from case_osint_service import CaseStore, CaseError


HOST = "127.0.0.1"
DEFAULT_PORT = 8787
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
WEB_ROOT = Path(__file__).with_name("web")
CASE_STORE = CaseStore()
MAX_CASE_REQUEST_BYTES = 4 * 1024 * 1024


def _parse_multipart(content_type: str, body: bytes) -> tuple[dict[str, list[str]], dict]:
    message = BytesParser(policy=default).parsebytes(
        (
            f"Content-Type: {content_type}\r\n"
            "MIME-Version: 1.0\r\n\r\n"
        ).encode("utf-8")
        + body
    )
    fields: dict[str, list[str]] = {}
    uploaded: dict = {}
    if not message.is_multipart():
        return fields, uploaded

    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if not name:
            continue
        if filename is not None:
            uploaded = {
                "name": Path(filename).name,
                "content_type": part.get_content_type(),
                "data": payload,
            }
        else:
            fields.setdefault(name, []).append(
                payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            )
    return fields, uploaded


def _first(fields: dict[str, list[str]], key: str, fallback: str) -> str:
    values = fields.get(key)
    return values[0] if values else fallback


def _evidence_source(fields: dict[str, list[str]]) -> dict:
    source_type = _first(fields, "source_type", "direct_upload").strip()
    if source_type not in {"direct_upload", "social_media"}:
        raise ValueError("Unknown evidence source type")

    source = {
        "type": source_type,
        "case_reference": _first(fields, "case_reference", "").strip()[:120]
        or None,
        "collection_note": _first(fields, "collection_note", "").strip()[:1000]
        or None,
    }
    if source_type == "social_media":
        source_url = _first(fields, "source_url", "").strip()
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Social-media evidence requires a valid public source URL")
        if parsed.username or parsed.password:
            raise ValueError("Source URLs must not contain login credentials")
        collection_mode = _first(fields, "collection_mode", "operator_upload").strip()
        if collection_mode not in {"operator_upload", "automatic_public_collection"}:
            raise ValueError("Unknown social-media collection mode")
        source.update(
            {
                "platform": _first(fields, "platform", "other").strip()[:40],
                "public_source_url": source_url[:2048],
                "account_reference": _first(
                    fields, "account_reference", ""
                ).strip()[:200]
                or None,
                "post_text": _first(fields, "post_text", "").strip()[:10000]
                or None,
                "declared_location": _first(
                    fields, "declared_location", ""
                ).strip()[:300]
                or None,
                "captured_at": _first(fields, "captured_at", "").strip()[:40]
                or None,
                "acquisition": collection_mode,
            }
        )
    return source


def _location_context(source: dict) -> str:
    values = [
        source.get("post_text"),
        source.get("declared_location"),
        source.get("collection_note"),
    ]
    automatic = source.get("automatic_collection", {})
    page = automatic.get("page", {})
    values.extend(
        (
            page.get("title"),
            page.get("description"),
            page.get("structured_location"),
            " ".join(page.get("hashtags", [])),
        )
    )
    if page.get("latitude") and page.get("longitude"):
        values.append(f"{page['latitude']}, {page['longitude']}")
    return "\n".join(str(value) for value in values if value)


class GeoTraceHandler(BaseHTTPRequestHandler):
    server_version = "GeoTrace/0.1"

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_index(self, filename: str = "index.html") -> None:
        try:
            encoded = (WEB_ROOT / filename).read_bytes()
        except OSError as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"status": "error", "reason": f"Web interface unavailable: {exc}"},
            )
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_index()
        elif path == "/osint":
            self._send_index("osint.html")
        elif path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "GeoTrace",
                    "processing_mode": "local_only",
                    "features": [
                        "geoclip",
                        "on_device_ocr",
                        "social_evidence",
                        "automatic_public_collection",
                        "authorized_case_osint",
                    ],
                },
            )
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"status": "not_found"})

    def do_POST(self) -> None:
        if urlparse(self.path).path.startswith("/api/osint/"):
            self._handle_case_osint()
            return
        if urlparse(self.path).path != "/api/analyze":
            self._send_json(HTTPStatus.NOT_FOUND, {"status": "not_found"})
            return

        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"status": "error", "reason": "Expected multipart form data"},
            )
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_UPLOAD_BYTES:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {
                    "status": "error",
                    "reason": "Upload must be present and no larger than 20 MB",
                },
            )
            return

        fields, uploaded = _parse_multipart(
            content_type, self.rfile.read(content_length)
        )

        try:
            top_k = min(max(int(_first(fields, "top_k", "5")), 1), 20)
            radius_km = float(_first(fields, "consensus_radius_km", "50"))
            if radius_km <= 0:
                raise ValueError("Consensus radius must be positive")
            evidence_source = _evidence_source(fields)
        except ValueError as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"status": "error", "reason": f"Invalid analysis option: {exc}"},
            )
            return

        if not uploaded.get("data"):
            if evidence_source.get("type") != "social_media":
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "status": "error",
                        "reason": "Choose an image for direct image analysis",
                    },
                )
                return
            if evidence_source.get("acquisition") == "automatic_public_collection":
                try:
                    uploaded = collect_public_media(
                        evidence_source["public_source_url"]
                    )
                    evidence_source["automatic_collection"] = uploaded.pop("collection")
                except PublicCollectionError as exc:
                    self._send_json(
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                        {"status": "error", "reason": str(exc)},
                    )
                    return

        temporary_path = None
        try:
            if uploaded.get("data"):
                suffix = Path(uploaded["name"]).suffix[:12] or ".img"
                with tempfile.NamedTemporaryFile(
                    prefix="geotrace-", suffix=suffix, delete=False
                ) as temporary:
                    temporary.write(uploaded["data"])
                    temporary_path = temporary.name
                result = analyze_image(
                    temporary_path,
                    include_geolocation=_first(fields, "use_geoclip", "false")
                    == "true",
                    include_ocr=_first(fields, "use_ocr", "false") == "true",
                    top_k=top_k,
                    consensus_radius_km=radius_km,
                    context_text=_location_context(evidence_source),
                )
                result["upload"] = {
                    "provided": True,
                    "name": uploaded["name"],
                    "size_bytes": len(uploaded["data"]),
                }
            else:
                result = analyze_text_evidence(
                    _location_context(evidence_source),
                    consensus_radius_km=radius_km,
                )
                result["upload"] = {"provided": False}
            result["evidence_source"] = evidence_source
            if evidence_source.get("type") == "social_media":
                result["social_evidence_assessment"] = assess_social_evidence(
                    result, evidence_source
                )
            self._send_json(HTTPStatus.OK, result)
        except Exception as exc:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"status": "error", "reason": f"Analysis failed: {exc}"},
            )
        finally:
            if temporary_path:
                Path(temporary_path).unlink(missing_ok=True)

    def log_message(self, format_string: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {format_string % args}")

    def _handle_case_osint(self) -> None:
        try:
            # This workspace is deliberately available only through localhost.
            # Reject foreign browser origins and Host headers before creating a case.
            server_host, port = self.server.server_address[:2]
            if not ipaddress.ip_address(server_host).is_loopback:
                raise CaseError("OSINT case workspace requires a loopback server binding", 403)
            allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
            host = self.headers.get("Host", "")
            if host not in allowed_hosts:
                raise CaseError("Local case workspace Host required", 403)
            origin = self.headers.get("Origin")
            if origin is not None and origin != f"http://{host}":
                raise CaseError("Same-origin case requests required", 403)
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                raise CaseError("Cross-site case requests are not allowed", 403)
            if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                raise CaseError("Case API expects application/json", 415)
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise CaseError("Invalid content length") from exc
            if size <= 0 or size > MAX_CASE_REQUEST_BYTES:
                raise CaseError("Case request must be present and no larger than 4 MB", 413)
            try:
                payload = json.loads(self.rfile.read(size).decode("utf-8"))
            except (ValueError, UnicodeError) as exc:
                raise CaseError("Invalid JSON request") from exc
            authorization = self.headers.get("Authorization", "")
            key = authorization[7:] if authorization.startswith("Bearer ") else ""
            action = urlparse(self.path).path.removeprefix("/api/osint/")
            result = CASE_STORE.dispatch(action, payload, key)
            self._send_json(HTTPStatus.OK, result)
        except CaseError as exc:
            self._send_json(HTTPStatus(exc.status), {"status": "error", "reason": str(exc)})
        except Exception:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"status": "error", "reason": "Case workspace operation failed"})


def run_server(host: str = HOST, port: int = DEFAULT_PORT) -> None:
    server = ThreadingHTTPServer((host, port), GeoTraceHandler)
    print(f"GeoTrace web interface: http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local GeoTrace web interface")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    options = parser.parse_args()
    run_server(options.host, options.port)
