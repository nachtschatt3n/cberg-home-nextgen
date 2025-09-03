#!/bin/bash

# Script to apply pod security labels to existing namespaces
# This is needed because Flux won't update existing namespaces

set -e

# Namespaces that need privileged pod security
NAMESPACES=(
    "ai"
    "backup"
    "databases"
    "default"
    "download"
    "home-automation"
    "media"
    "monitoring"
    "network"
    "office"
    "storage"
)

# Pod security labels
LABELS=(
    "pod-security.kubernetes.io/enforce=privileged"
    "pod-security.kubernetes.io/enforce-version=latest"
    "pod-security.kubernetes.io/audit=privileged"
    "pod-security.kubernetes.io/audit-version=latest"
    "pod-security.kubernetes.io/warn=privileged"
    "pod-security.kubernetes.io/warn-version=latest"
)

echo "Applying pod security labels to namespaces..."

for namespace in "${NAMESPACES[@]}"; do
    echo "Processing namespace: $namespace"

    # Check if namespace exists
    if kubectl get namespace "$namespace" >/dev/null 2>&1; then
        echo "  - Namespace exists, applying labels..."

        # Apply all labels
        for label in "${LABELS[@]}"; do
            kubectl label namespace "$namespace" "$label" --overwrite
        done

        echo "  - Labels applied successfully"
    else
        echo "  - Namespace does not exist, skipping..."
    fi
done

echo "Done!"
