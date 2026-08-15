#!/usr/bin/env bash
# Re-vendor the Gateway API (standard channel) + Envoy Gateway CRDs.
#
# Run from the repo root after bumping the envoy-gateway HelmRelease:
#   mise exec -- bash kubernetes/apps/network/envoy-gateway/crds/revendor.sh 1.8.3
#
# The CRDs are vendored instead of installed from the gateway-crds-helm chart
# because Helm stores the entire chart (~4.5 MB, both channels) inside its
# release Secret, which exceeds the 1 MiB Secret limit. Flux server-side
# applies these directly, so no release Secret is involved.
set -euo pipefail
VERSION="${1:?usage: revendor.sh <chart-version, e.g. 1.8.3>}"
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
