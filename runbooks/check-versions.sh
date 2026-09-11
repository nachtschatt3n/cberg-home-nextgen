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
#
# A HelmRelease carries its chart version EITHER inline at
# .spec.chart.spec.version OR, when it uses .spec.chartRef, on the referenced
# source object (OCIRepository.spec.ref.tag / HelmChart.spec.version). The
# jsonpath below returns an EMPTY STRING for the second shape and exits 0, so
# the `|| echo N/A` never fires and the release printed a blank version that
# looked like a formatting quirk (k8s-gateway, 2026-09-11). Resolve the ref,
# and if that also fails print UNRESOLVED rather than nothing.
check_helm_chart() {
    local namespace=$1
    local release=$2
    local current ref_kind ref_name

    current=$(kubectl get helmrelease -n "${namespace}" "${release}" -o jsonpath='{.spec.chart.spec.version}' 2>/dev/null)
    if [ -z "${current}" ]; then
        ref_kind=$(kubectl get helmrelease -n "${namespace}" "${release}" -o jsonpath='{.spec.chartRef.kind}' 2>/dev/null)
        ref_name=$(kubectl get helmrelease -n "${namespace}" "${release}" -o jsonpath='{.spec.chartRef.name}' 2>/dev/null)
        if [ -n "${ref_kind}" ] && [ -n "${ref_name}" ]; then
            case "${ref_kind}" in
                # .spec.ref.tag, NOT .spec.ref.digest: the digest is an
                # immutability pin, the tag is the version.
                OCIRepository) current=$(kubectl get ocirepository -n "${namespace}" "${ref_name}" -o jsonpath='{.spec.ref.tag}' 2>/dev/null) ;;
                HelmChart)     current=$(kubectl get helmchart     -n "${namespace}" "${ref_name}" -o jsonpath='{.spec.version}' 2>/dev/null) ;;
            esac
        fi
    fi
    echo "${release}|${current:-UNRESOLVED}"
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
# Same dual-shape rule as check_helm_chart(): fall back to the chartRef target
# and label an unresolvable chart source instead of printing `null`.
kubectl get helmreleases -A -o json \
  | jq -r '.items[] as $hr
      | ($hr.spec.chart.spec.version
         // ($hr.spec.chartRef | if . then "chartRef:\(.kind)/\(.name) (see that object for the version)" else null end)
         // "UNRESOLVED") as $v
      | "\($hr.metadata.namespace)|\($hr.metadata.name)|\($v)"' \
  | column -t -s'|'

echo ""
echo -e "${COLOR_GREEN}Version check complete!${COLOR_RESET}"
echo "Results saved to: ${OUTPUT_FILE}"
echo "Raw release data in: /tmp/version-*.txt"
