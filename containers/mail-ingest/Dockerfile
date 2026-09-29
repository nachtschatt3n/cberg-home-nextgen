# syntax=docker/dockerfile:1.7
# mail-ingest — HTTPS -> SMTP shim: Cloudflare Email Worker POSTs raw RFC 822
# here, it re-injects into Stalwart on in-cluster port 25. See app/main.py.
#
# Build:
#   docker buildx build -t ghcr.io/nachtschatt3n/mail-ingest:dev \
#     -f containers/mail-ingest/Dockerfile .

# python:3.12-slim-bookworm, pinned by index digest (multi-arch). The weekly
# scheduled rebuild pulls this exact base and re-runs apt upgrade; bump the
# digest to move the base itself.
FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e

RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 ingest \
    && useradd  --uid 1000 --gid 1000 --shell /usr/sbin/nologin --home-dir /home/ingest --create-home ingest

COPY containers/mail-ingest/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY --chown=ingest:ingest containers/mail-ingest/app /app
WORKDIR /app

USER 1000:1000
EXPOSE 8080

ENV PYTHONUNBUFFERED=1 \
    LISTEN_HOST=0.0.0.0 \
    LISTEN_PORT=8080

ENTRYPOINT ["python", "/app/main.py"]
