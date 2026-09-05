#!/usr/bin/env bash
# Re-vendor the Gateway API (standard channel) + Envoy Gateway CRDs.
#
# Run from the repo root after bumping the envoy-gateway HelmRelease:
#   mise exec -- bash kubernetes/apps/network/envoy-gateway/crds/revendor.sh 1.9.0
#
# The CRDs are vendored instead of installed from the gateway-crds-helm chart
# because Helm stores the entire chart (~4.5 MB, both channels) inside its
# release Secret, which exceeds the 1 MiB Secret limit. Flux server-side
# applies these directly, so no release Secret is involved.
set -euo pipefail
VERSION="${1:?usage: revendor.sh <chart-version, e.g. 1.9.0>}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHART="oci://docker.io/envoyproxy/gateway-crds-helm"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

helm pull "$CHART" --version "$VERSION" -d "$TMP" --untar >/dev/null

{
  echo "# VENDORED — do not hand-edit. Regenerate with ./revendor.sh."
  echo "# Source: ${CHART}:${VERSION}"
  echo "#   values: crds.gatewayAPI.enabled=true, crds.gatewayAPI.channel=standard"
  helm template x "$TMP/gateway-crds-helm" \
    --set crds.gatewayAPI.enabled=true \
    --set crds.gatewayAPI.channel=standard
} > "$DIR/gateway-api-standard.yaml"

{
  echo "# VENDORED — do not hand-edit. Regenerate with ./revendor.sh."
  echo "# Source: ${CHART}:${VERSION}"
  echo "#   values: crds.envoyGateway.enabled=true"
  helm template x "$TMP/gateway-crds-helm" --set crds.envoyGateway.enabled=true
} > "$DIR/envoy-gateway.yaml"

echo "re-vendored ${CHART}:${VERSION} into $DIR"

# ---------------------------------------------------------------------------
# CHANNEL-MOVE CHECK. The question every upgrade plan actually asks here is
# "did the Gateway API CRD CHANNEL move?" -- because k8s_gateway starts
# informers for the Gateway API route family and fails CLOSED for every name
# if a version it expects is not served (docs/sops/k8s-gateway-dns.md).
#
# A plain `git diff` on gateway-api-standard.yaml CANNOT answer it: the two
# provenance lines above embed ${VERSION}, so this script rewrites them on
# EVERY run and the file always shows a diff. A plan that stops on "any diff"
# therefore stops on every re-vendor, whatever the content did -- which is
# what happened on the 1.9.0 -> 1.9.1 bump (2026-09-05): the stop condition
# fired on the header while the CRD content was byte-identical.
#
# So compare the CONTENT, skipping the header, and print the bundle-version
# set outright. Answer the question directly instead of inferring it.
if git -C "$DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo
  echo "== Gateway API channel check =="
  for f in gateway-api-standard.yaml envoy-gateway.yaml; do
    if git -C "$DIR" show "HEAD:./$f" >/dev/null 2>&1; then
      if diff -q <(git -C "$DIR" show "HEAD:./$f" | tail -n +4) \
                 <(tail -n +4 "$DIR/$f") >/dev/null 2>&1; then
        echo "  $f: content UNCHANGED (header-only diff)"
      else
        echo "  $f: content CHANGED -- review before proceeding"
      fi
    else
      echo "  $f: no committed baseline to compare against"
    fi
  done
  echo "  bundle-version(s) now vendored: $(grep -ho 'bundle-version: v[0-9.]*' \
      "$DIR/gateway-api-standard.yaml" | sort -u | tr '\n' ' ')"
  echo "  A channel move means the bundle-version above changed. A changed"
  echo "  '# Source:' line alone does NOT mean the channel moved."
fi
