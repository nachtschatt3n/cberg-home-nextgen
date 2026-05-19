# syntax=docker/dockerfile:1.7
# sweep-collector — in-cluster audit script runner.
#
# Bundles runbooks/{security,version,doc,health}-check + the shared
# findings-writer library, plus the toolchain those scripts need
# (kubectl, flux, jq, git, psql client, trivy). Runs daily via a
# Kubernetes CronJob (see kubernetes/apps/monitoring/sweep-collector/).
#
# Build:
#   docker buildx build -t ghcr.io/nachtschatt3n/sweep-collector:dev \
#     -f containers/sweep-collector/Dockerfile .

ARG PYTHON_VERSION=3.12
ARG KUBECTL_VERSION=v1.36.0
ARG FLUX_VERSION=2.8.0
ARG TRIVY_VERSION=0.70.0

# ---------------------------------------------------------------------------
# Tool downloads (kept in a builder stage so the final image stays slim)
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS tools

ARG KUBECTL_VERSION
ARG FLUX_VERSION
ARG TRIVY_VERSION

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/tools

# kubectl
RUN arch=$(dpkg --print-architecture) \
    && curl -fsSL -o kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${arch}/kubectl" \
    && chmod +x kubectl

# flux CLI
RUN arch=$(dpkg --print-architecture) \
    && curl -fsSL "https://github.com/fluxcd/flux2/releases/download/v${FLUX_VERSION}/flux_${FLUX_VERSION}_linux_${arch}.tar.gz" \
        | tar -xzf - flux \
    && chmod +x flux

# trivy
RUN arch=$(dpkg --print-architecture) \
    && case "$arch" in amd64) trivy_arch=64bit;; arm64) trivy_arch=ARM64;; *) echo "unsupported arch: $arch" && exit 1;; esac \
    && curl -fsSL "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-${trivy_arch}.tar.gz" \
        | tar -xzf - trivy \
    && chmod +x trivy

# ---------------------------------------------------------------------------
# Final image
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        jq \
        postgresql-client \
        gh \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 sweep \
    && useradd  --uid 1000 --gid 1000 --shell /usr/sbin/nologin --home-dir /home/sweep --create-home sweep

COPY --from=tools /tmp/tools/kubectl /usr/local/bin/kubectl
COPY --from=tools /tmp/tools/flux    /usr/local/bin/flux
COPY --from=tools /tmp/tools/trivy   /usr/local/bin/trivy

# Python dependencies — copy first so Docker caches the install layer.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Audit scripts + supporting docs the scripts read at runtime.
COPY --chown=sweep:sweep runbooks/         /opt/sweep/runbooks/
COPY --chown=sweep:sweep docs/             /opt/sweep/docs/
COPY --chown=sweep:sweep kubernetes/       /opt/sweep/kubernetes/
COPY --chown=sweep:sweep CLAUDE.md         /opt/sweep/CLAUDE.md
COPY --chown=sweep:sweep AGENTS.md         /opt/sweep/AGENTS.md
COPY --chown=sweep:sweep containers/sweep-collector/entrypoint.sh /usr/local/bin/sweep-run
RUN chmod +x /usr/local/bin/sweep-run

USER sweep
WORKDIR /opt/sweep

ENTRYPOINT ["/usr/local/bin/sweep-run"]
CMD ["all"]
