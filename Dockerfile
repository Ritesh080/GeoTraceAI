FROM python:3.11-slim

ARG OSINTGRAM_COMMIT=cfb7038b6743f9ca22c58041035d27931382bfbb

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends git libimage-exiftool-perl libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# OSINTgram remains a separate localhost-only service. Pinning the upstream
# revision makes the deployment reproducible and preserves its GPL license.
RUN git clone --filter=blob:none https://github.com/Datalux/Osintgram.git /opt/osintgram \
    && git -C /opt/osintgram checkout "$OSINTGRAM_COMMIT" \
    && pip install --no-cache-dir -r /opt/osintgram/requirements.txt \
    && rm -rf /opt/osintgram/.git

COPY backend /app/backend
COPY scripts/render-start.sh /app/scripts/render-start.sh

RUN useradd --create-home --uid 10001 geotrace \
    && mkdir -p /opt/osintgram/config /tmp/osintgram-cache \
    && chown -R geotrace:geotrace /app /opt/osintgram /tmp/osintgram-cache \
    && chmod 755 /app/scripts/render-start.sh
USER geotrace

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/ready', timeout=3)"

CMD ["/app/scripts/render-start.sh"]
