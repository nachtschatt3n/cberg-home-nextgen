#!/bin/bash
# Restore actual domain in blueprint files for cluster deployment
# This script is meant to be run locally before flux reconciliation
# Blueprint files in git use "example.com" for security

set -e

DOMAIN="example.com"
# Read actual domain from cluster secret
ACTUAL_DOMAIN=$(kubectl get secret -n kube-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)

if [ -z "$ACTUAL_DOMAIN" ]; then
    echo "Error: Could not read SECRET_DOMAIN from cluster"
    exit 1
fi

echo "Replacing $DOMAIN with $ACTUAL_DOMAIN in blueprint files..."

# Find and replace in all blueprint YAML files
find kubernetes/apps -name "*-blueprint.yaml" -type f -exec sed -i "s/$DOMAIN/$ACTUAL_DOMAIN/g" {} \;

echo "Done! Blueprint files now use $ACTUAL_DOMAIN"
echo ""
echo "IMPORTANT: These changes are LOCAL ONLY and should NOT be committed to git"
echo "The .gitignore will help prevent accidental commits"
