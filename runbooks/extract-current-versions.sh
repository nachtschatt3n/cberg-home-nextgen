#!/bin/bash
# Extract current versions from all HelmReleases
# This is a basic version that extracts current state without checking for updates

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_FILE="${REPO_ROOT}/runbooks/version-check-current.md"
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

echo "# Kubernetes Deployment Version Status" > "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "**Generated:** $(date '+%Y-%m-%d %H:%M:%S')" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "> **Note:** This is a basic extraction. For full version checking with update detection," >> "$OUTPUT_FILE"
echo "> install Python dependencies (\`pip install pyyaml requests\`) and run \`runbooks/check-all-versions.py\`" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "## Summary" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Count deployments
TOTAL=$(find "${REPO_ROOT}/kubernetes/apps" -name "helmrelease.yaml" 2>/dev/null | wc -l)
echo "- **Total Deployments:** ${TOTAL}" >> "$OUTPUT_FILE"
echo "- **Chart Updates Available:** *Run full check to determine*" >> "$OUTPUT_FILE"
echo "- **Image Updates Available:** *Run full check to determine*" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "---" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Process each HelmRelease and group by namespace
find "${REPO_ROOT}/kubernetes/apps" -name "helmrelease.yaml" 2>/dev/null | sort | while read -r hr_file; do
    if [ ! -f "$hr_file" ]; then
        continue
    fi
    
    REL_PATH="${hr_file#${REPO_ROOT}/}"
    
    # Extract name and namespace
    NAME=$(grep -E "^  name:" "$hr_file" 2>/dev/null | head -1 | sed 's/.*name: *//' | tr -d '"' | tr -d "'" || echo "unknown")
    NAMESPACE=$(grep -E "^  namespace:" "$hr_file" 2>/dev/null | head -1 | sed 's/.*namespace: *//' | tr -d '"' | tr -d "'" || echo "default")
    
    # Extract chart info
    CHART_NAME=$(grep -A 5 "chart:" "$hr_file" 2>/dev/null | grep -E "^\s+chart:" | head -1 | sed 's/.*chart: *//' | tr -d '"' | tr -d "'" || echo "unknown")
    CHART_VERSION=$(grep -A 5 "chart:" "$hr_file" 2>/dev/null | grep -E "^\s+version:" | head -1 | sed 's/.*version: *//' | tr -d '"' | tr -d "'" || echo "unknown")
    REPO_NAME=$(grep -A 10 "sourceRef:" "$hr_file" 2>/dev/null | grep -E "^\s+name:" | head -1 | sed 's/.*name: *//' | tr -d '"' | tr -d "'" || echo "unknown")
    
    # Extract image info (basic extraction - first image found)
    IMAGE_REPO=$(grep -E "^\s+repository:" "$hr_file" 2>/dev/null | head -1 | sed 's/.*repository: *//' | tr -d '"' | tr -d "'" || echo "")
    IMAGE_TAG=$(grep -E "^\s+tag:" "$hr_file" 2>/dev/null | head -1 | sed 's/.*tag: *//' | tr -d '"' | tr -d "'" || echo "")
    
    # Write to temp file grouped by namespace
    echo "${NAMESPACE}|${NAME}|${REL_PATH}|${CHART_NAME}|${CHART_VERSION}|${REPO_NAME}|${IMAGE_REPO}|${IMAGE_TAG}" >> "${TEMP_DIR}/${NAMESPACE}.txt"
done

# Process grouped files
for ns_file in "${TEMP_DIR}"/*.txt; do
    if [ ! -f "$ns_file" ]; then
        continue
    fi
    
    NAMESPACE=$(basename "$ns_file" .txt)
    echo "## Namespace: \`${NAMESPACE}\`" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    
    while IFS='|' read -r ns name rel_path chart_name chart_version repo_name image_repo image_tag; do
        echo "### ${name}" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
        echo "- **File:** \`${rel_path}\`" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
        echo "#### Chart" >> "$OUTPUT_FILE"
        echo "- **Name:** \`${chart_name}\`" >> "$OUTPUT_FILE"
        echo "- **Repository:** \`${repo_name}\`" >> "$OUTPUT_FILE"
        echo "- **Current Version:** \`${chart_version}\`" >> "$OUTPUT_FILE"
        echo "- **Latest Version:** *Run full check to determine*" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
        
        if [ -n "$image_repo" ] && [ "$image_repo" != "unknown" ]; then
            echo "#### Container Images" >> "$OUTPUT_FILE"
            echo "- **Repository:** \`${image_repo}\`" >> "$OUTPUT_FILE"
            echo "  - **Current Tag:** \`${image_tag}\`" >> "$OUTPUT_FILE"
            echo "  - **Latest Tag:** *Run full check to determine*" >> "$OUTPUT_FILE"
            echo "" >> "$OUTPUT_FILE"
        else
            echo "*No container images found in values*" >> "$OUTPUT_FILE"
            echo "" >> "$OUTPUT_FILE"
        fi
        
        echo "---" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    done < "$ns_file"
done

echo "Report generated: $OUTPUT_FILE"
