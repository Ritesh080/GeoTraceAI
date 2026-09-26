#!/bin/sh
set -eu

SESSION_PATH="/opt/osintgram/config/instagrapi_session.json"
if [ -n "${OSINTGRAM_INSTAGRAPI_SESSION_BASE64:-}" ]; then
  python - <<'PY'
import base64
import binascii
import os
from pathlib import Path

payload = os.environ["OSINTGRAM_INSTAGRAPI_SESSION_BASE64"]
try:
    decoded = base64.b64decode(payload, validate=True)
except (ValueError, binascii.Error) as error:
    raise SystemExit(f"Invalid OSINTgram session secret: {error}") from error
if not decoded or len(decoded) > 2 * 1024 * 1024:
    raise SystemExit("OSINTgram session secret has an invalid size")
path = Path("/opt/osintgram/config/instagrapi_session.json")
path.write_bytes(decoded)
path.chmod(0o600)
PY
fi

cd /opt/osintgram
uvicorn src.web.app:app --host 127.0.0.1 --port 8010 &
OSINTGRAM_PID=$!
trap 'kill "$OSINTGRAM_PID" 2>/dev/null || true' EXIT INT TERM

cd /app
exec uvicorn backend.api:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
