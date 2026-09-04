#!/usr/bin/env bash
# Re-vendor the CSI external-snapshotter CRDs.
#
# Run from the repo root, pinning the SAME version as the csi-snapshotter
# sidecar Longhorn runs (check it, do not assume):
#   kubectl get deploy -n storage csi-snapshotter \
#     -o jsonpath='{.spec.template.spec.containers[0].image}'
#
#   mise exec -- bash kubernetes/apps/storage/snapshot-controller/crds/revendor.sh v8.6.0
#
# Vendored rather than pulled at apply time so the cluster's snapshot API is
# reproducible from git alone — the previous state (installed out-of-band,
# owned by nothing) is exactly how they silently disappeared on 2026-08-20.
set -euo pipefail
VERSION="${1:?usage: revendor.sh <version, e.g. v8.6.0>}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="https://raw.githubusercontent.com/kubernetes-csi/external-snapshotter/${VERSION}/client/config/crd"

{
  echo "# VENDORED — do not hand-edit. Regenerate with ./revendor.sh."
  echo "# Source: kubernetes-csi/external-snapshotter ${VERSION} (client/config/crd)"
  for f in volumesnapshotclasses volumesnapshotcontents volumesnapshots; do
    echo "---"
    curl -sfL "${BASE}/snapshot.storage.k8s.io_${f}.yaml"
  done
} > "$DIR/external-snapshotter.yaml"

echo "re-vendored external-snapshotter ${VERSION} into $DIR"
