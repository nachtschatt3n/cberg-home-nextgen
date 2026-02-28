#!/bin/bash
# Kubernetes Version Check Script
# Checks for updates to Helm charts and container images

set -e

COLOR_RESET='\033[0m'
COLOR_RED='\033[0;31m'
COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_BLUE='\033[0;34m'

# Resolve repo root and output directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCS_DIR="${REPO_ROOT}/runbooks"
OUTPUT_FILE="${DOCS_DIR}/version-check-current.md"

mkdir -p "${DOCS_DIR}"

echo -e "${COLOR_BLUE}=== Kubernetes Cluster Version Check ===${COLOR_RESET}"
echo "Date: $(date)"
echo "Output: ${OUTPUT_FILE}"
echo ""

# Function to check GitHub releases
check_github_release() {
    local repo=$1
    local name=$2

    echo -en "${COLOR_YELLOW}Checking ${name}...${COLOR_RESET} "
    version=$(curl -s "https://api.github.com/repos/${repo}/releases/latest" | jq -r '.tag_name // "N/A"')
    echo -e "${COLOR_GREEN}${version}${COLOR_RESET}"
    echo "${name}|${version}"
}

# Function to check Helm chart in cluster
check_helm_chart() {
    local namespace=$1
    local release=$2

    current=$(kubectl get helmrelease -n "${namespace}" "${release}" -o jsonpath='{.spec.chart.spec.version}' 2>/dev/null || echo "N/A")
    echo "${release}|${current}"
}

echo -e "${COLOR_BLUE}Checking GitHub Releases...${COLOR_RESET}"
echo ""

# Core Infrastructure
check_github_release "cilium/cilium" "Cilium" > /tmp/version-cilium.txt
check_github_release "cert-manager/cert-manager" "cert-manager" > /tmp/version-cert-manager.txt
check_github_release "longhorn/longhorn" "Longhorn" > /tmp/version-longhorn.txt
check_github_release "kubernetes-sigs/metrics-server" "metrics-server" > /tmp/version-metrics-server.txt

# Applications
check_github_release "goauthentik/authentik" "Authentik" > /tmp/version-authentik.txt
check_github_release "home-assistant/core" "Home Assistant" > /tmp/version-homeassistant.txt
check_github_release "open-webui/open-webui" "Open WebUI" > /tmp/version-openwebui.txt
check_github_release "blakeblackshear/frigate" "Frigate" > /tmp/version-frigate.txt
check_github_release "jellyfin/jellyfin" "Jellyfin" > /tmp/version-jellyfin.txt
check_github_release "grafana/grafana" "Grafana" > /tmp/version-grafana.txt
check_github_release "esphome/esphome" "ESPHome" > /tmp/version-esphome.txt

echo ""
echo -e "${COLOR_BLUE}Current Cluster Versions...${COLOR_RESET}"
echo ""

# Get current versions from cluster
kubectl get helmreleases -A -o json | jq -r '.items[] | "\(.metadata.namespace)|\(.metadata.name)|\(.spec.chart.spec.version)"' | column -t -s'|'

echo ""
echo -e "${COLOR_GREEN}Version check complete!${COLOR_RESET}"
echo "Results saved to: ${OUTPUT_FILE}"
echo "Raw release data in: /tmp/version-*.txt"
