#!/bin/bash
# Init container: shallow-fetch exactly one commit of the private repo into the
# shared /work volume. The ONLY place the git credential is mounted.
set -euo pipefail
: "${REF:?REF (full commit sha or branch) is required}"
: "${REPO_URL:?}"
export HOME=/work/home GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/opt/ci/git-askpass.sh
mkdir -p "$HOME"
t0=$(date +%s)
git init -q /work/src
cd /work/src
git remote add origin "$REPO_URL"
git -c credential.helper= fetch -q --depth 1 origin "$REF"
git checkout -q --detach FETCH_HEAD
echo "[clone] $(git rev-parse HEAD) ($(( $(date +%s) - t0 ))s)"
