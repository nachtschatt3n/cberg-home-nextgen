# syntax=docker/dockerfile:1.7
# sweep-dashboard — FastAPI + HTMX read-only view of the sweep-history
# Postgres. Reads via the sweep_reader role; never writes.
#
# Build:
#   docker buildx build -t ghcr.io/nachtschatt3n/sweep-dashboard:dev \
#     -f containers/sweep-dashboard/Dockerfile .

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 dash \
    && useradd  --uid 1000 --gid 1000 --shell /usr/sbin/nologin --home-dir /home/dash --create-home dash

COPY containers/sweep-dashboard/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY --chown=dash:dash containers/sweep-dashboard/app /app
WORKDIR /app

USER dash
EXPOSE 8000

# uvicorn worker count tuned for small dashboard load. Bump via env if needed.
ENV DASHBOARD_HOST=0.0.0.0 \
    DASHBOARD_PORT=8000 \
    DASHBOARD_WORKERS=2

ENTRYPOINT ["sh", "-c", "exec uvicorn main:app --host \"$DASHBOARD_HOST\" --port \"$DASHBOARD_PORT\" --workers \"$DASHBOARD_WORKERS\""]
