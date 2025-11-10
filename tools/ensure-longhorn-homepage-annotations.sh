#!/bin/bash
# Ensure Longhorn ingress has Homepage annotations
# This script can be run manually or via CronJob to ensure annotations persist
# even if Authentik Outpost overwrites them

set -euo pipefail

INGRESS_NAME="ak-outpost-longhorn-proxy-outpost"
INGRESS_NAMESPACE="kube-system"

# Check if ingress exists
if ! kubectl get ingress -n "${INGRESS_NAMESPACE}" "${INGRESS_NAME}" &>/dev/null; then
    echo "Error: Ingress ${INGRESS_NAMESPACE}/${INGRESS_NAME} not found"
    exit 1
fi

# Check if annotations already exist
CURRENT_ENABLED=$(kubectl get ingress -n "${INGRESS_NAMESPACE}" "${INGRESS_NAME}" -o jsonpath='{.metadata.annotations.gethomepage\.dev/enabled}' 2>/dev/null || echo "")

if [ "${CURRENT_ENABLED}" = "true" ]; then
    echo "✅ Homepage annotations already present on ${INGRESS_NAMESPACE}/${INGRESS_NAME}"
    exit 0
fi

# Apply patch
echo "Adding Homepage annotations to ${INGRESS_NAMESPACE}/${INGRESS_NAME}..."
kubectl patch ingress -n "${INGRESS_NAMESPACE}" "${INGRESS_NAME}" --type='json' -p='[
  {"op": "add", "path": "/metadata/annotations/gethomepage.dev~1enabled", "value": "true"},
  {"op": "add", "path": "/metadata/annotations/gethomepage.dev~1name", "value": "Longhorn"},
  {"op": "add", "path": "/metadata/annotations/gethomepage.dev~1description", "value": "Kubernetes storage management UI"},
  {"op": "add", "path": "/metadata/annotations/gethomepage.dev~1group", "value": "System"},
  {"op": "add", "path": "/metadata/annotations/gethomepage.dev~1icon", "value": "longhorn.png"}
]'

echo "✅ Successfully added Homepage annotations"
