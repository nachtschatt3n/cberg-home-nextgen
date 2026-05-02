#!/usr/bin/env bash

# Kubernetes Cluster Health Check Script
# Executes all operational health checks from runbooks/health-check.md
# Scope: operational correctness only — does not flag newer upstream versions
# Usage: ./runbooks/health-check.sh [--prev <prior-report>] [output-file]

# Self-activate mise toolchain so kubectl/talosctl/flux/sops + KUBECONFIG/etc are set
# regardless of how the script is invoked (cron, sub-agent, fresh shell). Idempotent.
if [ -z "${_MISE_ACTIVATED:-}" ]; then
    _REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    if [ -f "$_REPO_ROOT/.mise.toml" ] && command -v mise >/dev/null 2>&1; then
        export _MISE_ACTIVATED=1
        exec mise -C "$_REPO_ROOT" exec -- bash "$0" "$@"
    fi
fi

set -uo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# --- CLI arg parsing (positional output-file preserved; --prev is optional) ---
PREV_FILE=""
POSITIONAL_ARGS=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        --prev)
            PREV_FILE="${2:-}"
            shift 2
            ;;
        --prev=*)
            PREV_FILE="${1#--prev=}"
            shift
            ;;
        *)
            POSITIONAL_ARGS+=("$1")
            shift
            ;;
    esac
done
# Restore positional args so existing "${1:-...}" semantics work below
# (bash 3.2: cannot reference empty array directly under set -u, so guard length)
if [ "${#POSITIONAL_ARGS[@]}" -gt 0 ]; then
    set -- "${POSITIONAL_ARGS[@]}"
else
    set --
fi

# Resolve repository root (parent of runbooks/) for git operations
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Allowlist of known-recurring noise (consumed by _noise_tag below)
NOISE_ALLOWLIST="$SCRIPT_DIR/noise_allowlist.yaml"

# Output file
OUTPUT_FILE="${1:-/tmp/health-check-$(date +%Y%m%d-%H%M%S).txt}"
SUMMARY_FILE="/tmp/health-check-summary-$(date +%Y%m%d-%H%M%S).txt"
ISSUES_FILE="/tmp/health-check-issues-$(date +%Y%m%d-%H%M%S).txt"

echo "========================================" | tee "$OUTPUT_FILE"
echo "Kubernetes Cluster Health Check" | tee -a "$OUTPUT_FILE"
echo "Date: $(date)" | tee -a "$OUTPUT_FILE"
echo "Output: $OUTPUT_FILE" | tee -a "$OUTPUT_FILE"
echo "========================================" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# --- Section 0: Convergence (local git HEAD vs Flux source revision) ---
echo "=== Section 0: Convergence ===" | tee -a "$OUTPUT_FILE"
{
    local_head=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)
    flux_rev=$(kubectl -n flux-system get gitrepository flux-system \
        -o jsonpath='{.status.artifact.revision}' 2>/dev/null || echo "")
    # Strip optional "sha1:" prefix
    flux_rev="${flux_rev#sha1:}"
    # Some flux versions use "<branch>@sha1:<hash>" — keep just the hash
    flux_rev="${flux_rev##*:}"

    local_short="${local_head:0:8}"
    flux_short=""
    if [ -n "$flux_rev" ] && [ "$flux_rev" != "unknown" ]; then
        flux_short="${flux_rev:0:8}"
    else
        flux_short="unknown"
    fi

    if [ "$local_head" != "unknown" ] && [ -n "$flux_rev" ] && [ "$local_head" = "$flux_rev" ]; then
        converged="yes"
    else
        converged="no"
    fi

    printf '  Local HEAD:    %s\n' "$local_short"
    printf '  Flux source:   %s\n' "$flux_short"
    printf '  CONVERGED:     %s\n' "$converged"

    if [ "$converged" = "no" ] && [ "$local_head" != "unknown" ] && [ -n "$flux_rev" ]; then
        ahead=$(git -C "$REPO_ROOT" rev-list --count "$flux_rev..$local_head" 2>/dev/null || echo "")
        if [ -n "$ahead" ]; then
            printf '  Commits ahead: %s\n' "$ahead"
        fi
    fi
} | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# --- Dependency check ---
echo "=== Dependency Check ===" | tee -a "$OUTPUT_FILE"
REQUIRED_TOOLS="kubectl python3 curl jq"
OPTIONAL_TOOLS="unifictl talosctl flux sops nc"
MISSING_REQUIRED=()
MISSING_OPTIONAL=()
for tool in $REQUIRED_TOOLS; do
    if ! command -v "$tool" &>/dev/null; then
        MISSING_REQUIRED+=("$tool")
        echo "  ❌ MISSING (required): $tool" | tee -a "$OUTPUT_FILE"
    else
        echo "  ✅ $tool" | tee -a "$OUTPUT_FILE"
    fi
done
for tool in $OPTIONAL_TOOLS; do
    if ! command -v "$tool" &>/dev/null; then
        MISSING_OPTIONAL+=("$tool")
        echo "  ⚠️  MISSING (optional): $tool — some checks will be skipped" | tee -a "$OUTPUT_FILE"
    else
        echo "  ✅ $tool" | tee -a "$OUTPUT_FILE"
    fi
done
if [ "${#MISSING_REQUIRED[@]}" -gt 0 ]; then
    echo "  ❌ Missing required tools: ${MISSING_REQUIRED[*]} — install before running" | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
    exit 1
fi
echo "" | tee -a "$OUTPUT_FILE"

# Counters for summary
CRITICAL_ISSUES=0
WARNINGS=0
CHECKS_PASSED=0
CHECKS_FAILED=0

# Arrays to store issues
declare -a CRITICAL_ISSUES_LIST
declare -a MAJOR_ISSUES_LIST
declare -a MINOR_ISSUES_LIST

# Helper functions
log_section() {
    echo -e "\n${BLUE}=== $1 ===${NC}" | tee -a "$OUTPUT_FILE"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}" | tee -a "$OUTPUT_FILE"
    ((CHECKS_PASSED++))
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}" | tee -a "$OUTPUT_FILE"
    ((WARNINGS++))
}

log_critical() {
    echo -e "${RED}❌ $1${NC}" | tee -a "$OUTPUT_FILE"
    ((CRITICAL_ISSUES++))
    ((CHECKS_FAILED++))
}

log_info() {
    echo "ℹ️  $1" | tee -a "$OUTPUT_FILE"
}

add_critical_issue() {
    CRITICAL_ISSUES_LIST+=("$1")
}

add_major_issue() {
    MAJOR_ISSUES_LIST+=("$1")
}

add_minor_issue() {
    MINOR_ISSUES_LIST+=("$1")
}

# _noise_tag: Tag finding lines that match the recurring-noise allowlist.
# Usage:
#   tag=$(_noise_tag "Active alert line text...")
#   echo "  - finding${tag}"
# Returns " [noise: <note>]" if a substring from noise_allowlist.yaml is
# present in the input line; empty string otherwise. YAML is grep-scanned,
# not parsed. Fails silently (empty output) if allowlist is missing.
_noise_tag() {
    local line="$1"
    [ -z "$line" ] && return 0
    [ -f "$NOISE_ALLOWLIST" ] || return 0

    # Extract candidate substrings from the allowlist:
    #   - quoted strings ("Soil sensor 3")
    #   - YAML scalar values after known keys (alertname/namespace/workload/pod/prefix)
    # Then test each candidate against the finding line. First match wins;
    # we then look up the nearest "note:" in the allowlist for context.
    local match=""
    local note=""
    local cand
    # Quoted substrings: e.g. "Soil sensor 3"
    while IFS= read -r cand; do
        [ -z "$cand" ] && continue
        if printf '%s' "$line" | grep -qF -- "$cand"; then
            match="$cand"
            break
        fi
    done < <(grep -oE '"[^"]+"' "$NOISE_ALLOWLIST" 2>/dev/null | sed 's/^"//;s/"$//')

    # Key-based substrings if no quoted hit
    if [ -z "$match" ]; then
        while IFS= read -r cand; do
            [ -z "$cand" ] && continue
            if printf '%s' "$line" | grep -qF -- "$cand"; then
                match="$cand"
                break
            fi
        done < <(grep -E '^[[:space:]]*(- )?(alertname|namespace|workload|pod|prefix):' "$NOISE_ALLOWLIST" 2>/dev/null \
                    | sed -E 's/^[[:space:]]*(- )?[a-z]+:[[:space:]]*//' \
                    | sed -E 's/^"//;s/"$//')
    fi

    [ -z "$match" ] && return 0

    # Best-effort note lookup. Find the line number of the match, then look
    # for a "note:" line in the same YAML list entry — i.e. a "note:" that
    # appears AFTER the match but BEFORE the next "- " bullet or top-level
    # YAML key. If no note is found in-block, emit a generic [noise] tag
    # (do NOT borrow a note from a different block — it would be misleading).
    local match_ln
    match_ln=$(grep -nF -- "$match" "$NOISE_ALLOWLIST" 2>/dev/null | head -1 | cut -d: -f1)
    if [ -n "$match_ln" ]; then
        note=$(awk -v start="$match_ln" '
            NR > start {
                # Stop at the next list-entry bullet or a new top-level key
                if ($0 ~ /^[[:space:]]*-[[:space:]]/) exit;
                if ($0 ~ /^[A-Za-z0-9_]+:/) exit;
                if ($0 ~ /^[[:space:]]*note:/) {
                    sub(/^[[:space:]]*note:[[:space:]]*/, "");
                    print; exit;
                }
            }' "$NOISE_ALLOWLIST" 2>/dev/null)
    fi
    if [ -n "$note" ]; then
        printf ' [noise: %s]' "$note"
    else
        printf ' [noise]'
    fi
}

# Helper to safely get integer count
safe_count() {
    local result=$(eval "$1" 2>/dev/null | head -1 || echo "0")
    # Remove any non-digit characters
    result=$(echo "$result" | tr -cd '0-9' || echo "0")
    # If empty, return 0
    if [ -z "$result" ]; then
        echo "0"
    else
        echo "$result"
    fi
}

# =========================================
# KNOWN FALSE POSITIVES
# =========================================
# Centralized list of known benign patterns that should be excluded from error counts.
# Each entry is a grep-compatible pattern. Add new entries here when a pattern is
# confirmed as a false positive, with a comment explaining why.
#
# To add a new exclusion:
#   1. Add the grep pattern to the appropriate array below
#   2. Add a comment with the date confirmed and reason
#   3. Document in AI_weekly_health_check.MD (Section 31 for HA, relevant section for others)

# Home Assistant log patterns that are not real errors
# See docs/troubleshooting/ha-upstream-integration-issues.md for upstream issues
HA_FALSE_POSITIVES=(
    "Flic Hub"                      # Expected offline device (no longer in use)
    "dynamic_energy_cost"           # Transient startup warning - Tibber JWT init delay (confirmed 2026-02-15)
    "does not generate unique IDs"  # music_assistant duplicate entity IDs - cosmetic, no functional impact (confirmed 2026-02-15)
    "tesla_wall_connector"          # Device on WiFi edge - intermittent timeouts, accepted (2026-04-17)
    "WallConnectorConnectionTimeout" # Same as above - backoff library error form
    "pymiele.pymiele"               # Upstream Miele Cloud SSE bug (pymiele 0.6.1 latest, no fix yet, 2026-04-17)
    "miele.coordinator.*Timeout"    # Secondary coordinator timeout from pymiele SSE issue
    "tibber.realtime"               # Tibber backend 502s - not a local issue (2026-04-17)
    "tibber.home.*Error in rt_subscribe" # Same Tibber backend issue
    "disconnected due to inactivity" # Benign websocket inactivity disconnects
    "hatch_rest_api.util_bootstrap" # ha_hatch custom integration — upstream signature mismatch, no fix yet (2026-04-19)
    "ha_hatch.hatch_data_update_coordinator" # Same — secondary coordinator error from hatch_rest_api
)

# Kubernetes event patterns that are normal operations (not actionable warnings)
K8S_EVENT_FALSE_POSITIVES=(
    "BackOff"                       # Normal pod restart backoff
    "Pulling"                       # Normal image pulling
    "FailedScheduling"              # Transient scheduling delays
    "Unhealthy"                     # Transient probe failures during rolling updates
)

# Infrastructure log patterns that are not real errors
INFRA_LOG_FALSE_POSITIVES=(
    "Err: 0"                        # Status field showing zero errors (not an actual error)
)

# Build a combined grep exclusion pattern from an array
# Usage: exclude_pattern=$(build_grep_exclude "${ARRAY[@]}")
build_grep_exclude() {
    local patterns=("$@")
    local result=""
    for pattern in "${patterns[@]}"; do
        if [ -n "$result" ]; then
            result="$result|$pattern"
        else
            result="$pattern"
        fi
    done
    echo "$result"
}

# Filter out false positives from piped input
# Usage: echo "$LOGS" | filter_ha_false_positives
filter_ha_false_positives() {
    local exclude
    exclude=$(build_grep_exclude "${HA_FALSE_POSITIVES[@]}")
    grep -vE "$exclude"
}

# Filter out false positives from infrastructure logs
filter_infra_false_positives() {
    local exclude
    exclude=$(build_grep_exclude "${INFRA_LOG_FALSE_POSITIVES[@]}")
    grep -vE "$exclude"
}

# ── Elasticsearch enrichment helpers ──────────────────────────────────────────
# Shared ES session for supplementary log analysis (7-day window).
# All ES enrichment is informational only — never creates critical/major issues.
ES_AVAILABLE="false"
ES_PF_PID=""
ES_PASSWORD_SHARED=""
ES_PORT=9202

es_init() {
    # Kill any leftover port-forward on our port
    lsof -ti:${ES_PORT} 2>/dev/null | xargs kill 2>/dev/null || true
    sleep 0.3

    # Get password
    ES_PASSWORD_SHARED=$(kubectl get secret elasticsearch-es-elastic-user -n monitoring \
        -o jsonpath='{.data.elastic}' 2>/dev/null | base64 -d 2>/dev/null)
    if [ -z "$ES_PASSWORD_SHARED" ]; then
        echo "  ES enrichment: password unavailable, skipping"
        return
    fi

    # Start port-forward
    kubectl port-forward -n monitoring svc/elasticsearch-es-http ${ES_PORT}:9200 \
        >/dev/null 2>&1 &
    ES_PF_PID=$!

    # Wait for port to open (max 10 attempts)
    for i in $(seq 1 10); do
        if curl -k -s -m 2 -u "elastic:${ES_PASSWORD_SHARED}" \
            "https://localhost:${ES_PORT}/" >/dev/null 2>&1; then
            ES_AVAILABLE="true"
            echo "  ES enrichment: connected on port ${ES_PORT}"
            return
        fi
        sleep 1
    done
    echo "  ES enrichment: connection failed, skipping"
}

es_query() {
    local query_body="$1"
    if [ "$ES_AVAILABLE" != "true" ]; then
        echo ""
        return 1
    fi
    curl -k -s -m 15 -u "elastic:${ES_PASSWORD_SHARED}" \
        -X POST "https://localhost:${ES_PORT}/logs-generic-default/_search" \
        -H 'Content-Type: application/json' \
        -d "$query_body" 2>/dev/null || { echo ""; return 1; }
}

es_cleanup() {
    if [ -n "$ES_PF_PID" ]; then
        kill "$ES_PF_PID" 2>/dev/null || true
        wait "$ES_PF_PID" 2>/dev/null || true
    fi
    lsof -ti:${ES_PORT} 2>/dev/null | xargs kill 2>/dev/null || true
}

# ── Prometheus enrichment helpers ─────────────────────────────────────────────
# Shared Prometheus session for metric queries. Informational only.
PROM_AVAILABLE="false"
PROM_PF_PID=""
PROM_PORT=9094

prom_init() {
    lsof -ti:${PROM_PORT} 2>/dev/null | xargs kill 2>/dev/null || true
    sleep 0.3

    kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus \
        ${PROM_PORT}:9090 >/dev/null 2>&1 &
    PROM_PF_PID=$!

    for i in $(seq 1 10); do
        if curl -s -m 2 "http://localhost:${PROM_PORT}/-/healthy" >/dev/null 2>&1; then
            PROM_AVAILABLE="true"
            echo "  Prometheus enrichment: connected on port ${PROM_PORT}"
            return
        fi
        sleep 1
    done
    echo "  Prometheus enrichment: connection failed, skipping"
}

prom_query() {
    local promql="$1"
    if [ "$PROM_AVAILABLE" != "true" ]; then
        echo ""
        return 1
    fi
    local encoded
    encoded=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$promql")
    curl -s -m 10 "http://localhost:${PROM_PORT}/api/v1/query?query=${encoded}" \
        2>/dev/null || { echo ""; return 1; }
}

prom_cleanup() {
    if [ -n "$PROM_PF_PID" ]; then
        kill "$PROM_PF_PID" 2>/dev/null || true
        wait "$PROM_PF_PID" 2>/dev/null || true
    fi
    lsof -ti:${PROM_PORT} 2>/dev/null | xargs kill 2>/dev/null || true
}

# Combined cleanup — replaces the es_cleanup trap
_all_cleanup() {
    es_cleanup
    prom_cleanup
}
trap _all_cleanup EXIT

# Verify cluster access
log_section "Phase 1: Preparation"
if kubectl cluster-info >> "$OUTPUT_FILE" 2>&1; then
    log_success "Cluster access verified"
else
    log_critical "Cannot access cluster"
    add_critical_issue "Cannot access Kubernetes cluster"
    exit 1
fi

# Get node list for later use
NODE_IPS=$(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}')
log_info "Nodes: $(kubectl get nodes -o jsonpath='{.items[*].metadata.name}' | tr ' ' ', ')"

# Initialize ES and Prometheus enrichment sessions
es_init
prom_init

echo "" | tee -a "$OUTPUT_FILE"

#######################################
# Phase 2: Core Infrastructure Checks
#######################################

log_section "Section 1: Cluster Events & Logs"
{
    echo "Recent events (last 50):"
    kubectl get events -A --sort-by='.lastTimestamp' | tail -50
    echo ""

    K8S_EXCLUDE=$(build_grep_exclude "${K8S_EVENT_FALSE_POSITIVES[@]}")
    WARNING_COUNT=$(safe_count "kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | grep -v 'NAMESPACE' | grep -vE '($K8S_EXCLUDE)' | wc -l")
    echo "Warning events: $WARNING_COUNT"

    OOM_COUNT=$(safe_count "kubectl get events -A --field-selector reason=OOMKilled 2>/dev/null | grep -v 'NAMESPACE' | wc -l")
    echo "OOM kills: $OOM_COUNT"

    EVICTED_COUNT=$(safe_count "kubectl get events -A --field-selector reason=Evicted 2>/dev/null | grep -v 'NAMESPACE' | wc -l")
    echo "Pod evictions: $EVICTED_COUNT"

    if [ "$WARNING_COUNT" -gt 10 ]; then
        log_warning "High warning count: $WARNING_COUNT events"
        add_minor_issue "High warning event count: $WARNING_COUNT"
    elif [ "$WARNING_COUNT" -gt 0 ]; then
        log_info "Warning events: $WARNING_COUNT"
    else
        log_success "No warning events"
    fi

    if [ "$OOM_COUNT" -gt 0 ]; then
        log_critical "OOM kills detected: $OOM_COUNT"
        add_critical_issue "OOM kills detected: $OOM_COUNT pods"
    else
        log_success "No OOM kills"
    fi

    if [ "$EVICTED_COUNT" -gt 0 ]; then
        log_critical "Pod evictions detected: $EVICTED_COUNT"
        add_critical_issue "Pod evictions detected: $EVICTED_COUNT pods"
    else
        log_success "No pod evictions"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 2: Jobs & CronJobs"
{
    echo "All CronJobs:"
    kubectl get cronjobs -A
    echo ""

    echo "Recent jobs:"
    kubectl get jobs -A --sort-by='.status.startTime' | tail -20
    echo ""

    FAILED_JOBS=$(safe_count "kubectl get jobs -A 2>/dev/null | grep -E '(0/1|Failed)' | wc -l")
    echo "Failed jobs (last 7 days): $FAILED_JOBS"

    # Check backup job
    BACKUP_JOB=$(kubectl get jobs -n storage --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null | grep -o 'daily-backup-all-volumes[^ ]*' | head -1 || echo "")
    if [ -n "$BACKUP_JOB" ]; then
        BACKUP_STATUS=$(kubectl get job -n storage "$BACKUP_JOB" -o jsonpath='{.status.succeeded}' 2>/dev/null || echo "0")
        BACKUP_TIME=$(kubectl get job -n storage "$BACKUP_JOB" -o jsonpath='{.status.completionTime}' 2>/dev/null || echo "Not completed")
        echo "Last backup job: $BACKUP_JOB (Succeeded: $BACKUP_STATUS, Time: $BACKUP_TIME)"

        if [ "$BACKUP_STATUS" == "1" ]; then
            log_success "Backup system operational"
        else
            log_warning "Backup status unclear: $BACKUP_STATUS"
            add_minor_issue "Backup job status unclear"
        fi
    else
        log_warning "No backup jobs found"
        add_minor_issue "No backup jobs found in storage namespace"
    fi

    if [ "$FAILED_JOBS" -gt 0 ]; then
        log_warning "Failed jobs detected: $FAILED_JOBS"
        add_minor_issue "Failed jobs: $FAILED_JOBS"
    else
        log_success "No failed jobs"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 3: Certificates"
{
    echo "All certificates:"
    kubectl get certificates -A
    echo ""

    TOTAL_CERTS=$(safe_count "kubectl get certificates -A --no-headers 2>/dev/null | wc -l")
    READY_CERTS=$(kubectl get certificates -A -o json 2>/dev/null | jq '[.items[] | select(.status.conditions[]? | select(.type=="Ready" and .status=="True"))] | length' || echo "0")

    echo "Certificates: $READY_CERTS/$TOTAL_CERTS ready"

    if [ "$READY_CERTS" == "$TOTAL_CERTS" ] && [ "$TOTAL_CERTS" -gt 0 ]; then
        log_success "All certificates ready ($TOTAL_CERTS/$TOTAL_CERTS)"
    else
        log_warning "Some certificates not ready: $READY_CERTS/$TOTAL_CERTS"
        add_major_issue "Certificates not ready: $READY_CERTS/$TOTAL_CERTS"
        echo "Not ready certificates:"
        kubectl get certificates -A -o json | jq -r '.items[] | select(.status.conditions[]? | select(.type=="Ready" and .status!="True")) | "\(.metadata.namespace)/\(.metadata.name)"'
    fi

    # Check for certificates expiring within 14 days
    echo ""
    echo "Checking for certificates expiring within 14 days..."
    EXPIRING_SOON=$(kubectl get certificates -A -o json 2>/dev/null | jq -r '
        .items[] |
        select(.status.notAfter != null) |
        select(
            (.status.notAfter | fromdateiso8601) - now < 1209600
        ) |
        "\(.metadata.namespace)/\(.metadata.name): expires \(.status.notAfter)"
    ' || echo "")
    if [ -n "$EXPIRING_SOON" ]; then
        echo "Certificates expiring within 14 days:"
        echo "$EXPIRING_SOON"
        EXPIRY_COUNT=$(echo "$EXPIRING_SOON" | grep -c "/" || echo "0")
        log_warning "Certificates expiring within 14 days: $EXPIRY_COUNT"
        add_major_issue "Certificates expiring within 14 days: $EXPIRY_COUNT"
    else
        log_success "No certificates expiring within 14 days"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 4: DaemonSets"
{
    echo "All DaemonSets:"
    kubectl get daemonsets -A
    echo ""

    MISMATCHED=$(kubectl get daemonsets -A -o json | jq -r '.items[] | select(.status.desiredNumberScheduled != .status.currentNumberScheduled or .status.desiredNumberScheduled != .status.numberReady) | "\(.metadata.namespace)/\(.metadata.name): desired=\(.status.desiredNumberScheduled) current=\(.status.currentNumberScheduled) ready=\(.status.numberReady)"')

    if [ -z "$MISMATCHED" ]; then
        log_success "All DaemonSets healthy"
    else
        log_warning "DaemonSets with mismatched counts:"
        echo "$MISMATCHED"
        add_major_issue "DaemonSets not at desired state: $MISMATCHED"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 5: Helm Deployments"
{
    echo "HelmReleases:"
    flux get helmreleases -A | head -20
    echo ""

    TOTAL_HELM=$(safe_count "flux get helmreleases -A 2>/dev/null | grep -v 'NAMESPACE' | wc -l")
    FAILED_HELM=$(safe_count "flux get helmreleases -A 2>/dev/null | grep -E '(Failed|Error|Unknown)' | wc -l")

    echo "HelmReleases: $((TOTAL_HELM - FAILED_HELM))/$TOTAL_HELM ready"

    echo ""
    echo "HelmRepositories:"
    flux get sources helm -A | head -30
    echo ""

    # Check for failed HelmRepositories (READY column = False)
    FAILED_HELMREPOS=$(safe_count "flux get sources helm -A 2>/dev/null | awk '\$5 == \"False\"' | wc -l")
    echo "Failed HelmRepositories: $FAILED_HELMREPOS"

    if [ "$FAILED_HELMREPOS" -gt 0 ]; then
        echo ""
        echo "Failed HelmRepository details:"
        flux get sources helm -A 2>/dev/null | awk '$5 == "False"' | while read line; do
            echo "  - $line"
            # Extract namespace and name for detailed info
            REPO_NS=$(echo "$line" | awk '{print $1}')
            REPO_NAME=$(echo "$line" | awk '{print $2}')
            kubectl get helmrepository "$REPO_NAME" -n "$REPO_NS" -o jsonpath='{.status.conditions[?(@.type=="Ready")].message}' 2>/dev/null | sed 's/^/    Error: /' || true
            echo ""
        done
    fi

    echo ""
    echo "Kustomizations:"
    flux get kustomizations -A | head -20

    TOTAL_KUST=$(safe_count "flux get kustomizations -A 2>/dev/null | grep -v 'NAMESPACE' | wc -l")
    # Count kustomizations where READY column (col 5) is not True — resilient to mid-reconciliation message changes
    NOT_RECONCILED=$(safe_count "flux get kustomizations -A 2>/dev/null | grep -v 'NAMESPACE' | awk '\$5 != \"True\"' | wc -l")

    echo ""
    echo "Kustomizations: $((TOTAL_KUST - NOT_RECONCILED))/$TOTAL_KUST reconciled"

    # Check for specific kustomization issues
    if [ "$NOT_RECONCILED" -gt 0 ]; then
        echo ""
        echo "Kustomization issues:"
        flux get kustomizations -A 2>/dev/null | grep -v 'Applied revision' | grep -v 'NAMESPACE' | while read line; do
            echo "  - $line"
            # Extract namespace and name for detailed info
            KUST_NS=$(echo "$line" | awk '{print $1}')
            KUST_NAME=$(echo "$line" | awk '{print $2}')

            # Check for dependency issues
            DEP_MSG=$(kubectl get kustomization "$KUST_NAME" -n "$KUST_NS" -o jsonpath='{.status.conditions[?(@.type=="Ready")].message}' 2>/dev/null || echo "")
            if [[ "$DEP_MSG" == *"dependency"* ]]; then
                echo "    Status: Dependency issue - $DEP_MSG"
            elif [[ "$DEP_MSG" == *"health check"* ]]; then
                echo "    Status: Health check issue - $DEP_MSG"
            elif [[ "$DEP_MSG" == *"Reconciliation in progress"* ]]; then
                echo "    Status: Reconciliation in progress"
            else
                echo "    Status: $DEP_MSG"
            fi
        done
    fi

    # Evaluate issues
    CRITICAL_FLUX_ISSUES=0

    if [ "$FAILED_HELM" -eq 0 ] && [ "$NOT_RECONCILED" -eq 0 ] && [ "$FAILED_HELMREPOS" -eq 0 ]; then
        log_success "All Helm releases, repositories, and Kustomizations healthy"
    else
        if [ "$FAILED_HELMREPOS" -gt 0 ]; then
            log_warning "Failed HelmRepositories detected: $FAILED_HELMREPOS (may block kustomizations)"
            add_major_issue "Failed HelmRepositories: $FAILED_HELMREPOS (check for broken URLs or network issues)"
            ((CRITICAL_FLUX_ISSUES++))
        fi

        if [ "$FAILED_HELM" -gt 0 ]; then
            log_warning "HelmRelease failures: $FAILED_HELM"
            add_major_issue "HelmRelease failures: $FAILED_HELM"
        fi

        if [ "$NOT_RECONCILED" -gt 0 ]; then
            # Check if stuck due to dependencies
            DEPENDENCY_STUCK=$(flux get kustomizations -A 2>/dev/null | grep -c "dependency.*not ready" || echo "0")
            HEALTHCHECK_STUCK=$(kubectl get kustomizations -A -o json 2>/dev/null | jq -r '[.items[] | select(.status.conditions[]? | select(.type=="Ready" and .reason=="Progressing" and (.message | contains("health check"))))] | length' || echo "0")

            if [ "$DEPENDENCY_STUCK" -gt 0 ]; then
                log_warning "Kustomizations blocked by dependencies: $DEPENDENCY_STUCK"
                add_major_issue "Kustomizations blocked by dependencies: $DEPENDENCY_STUCK (check for failed HelmRepositories)"
            elif [ "$HEALTHCHECK_STUCK" -gt 0 ]; then
                log_warning "Kustomizations stuck in health checks: $HEALTHCHECK_STUCK"
                add_major_issue "Kustomizations stuck in health checks: $HEALTHCHECK_STUCK (may timeout after 30 minutes)"
            else
                log_warning "Kustomizations not reconciled: $NOT_RECONCILED"
                add_minor_issue "Kustomizations not reconciled: $NOT_RECONCILED"
            fi
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 6: Deployments & StatefulSets"
{
    echo "Deployments not at desired replicas:"
    kubectl get deployments -A -o json | jq -r '.items[] | select(.spec.replicas != (.status.readyReplicas // 0)) | "\(.metadata.namespace)/\(.metadata.name): \(.status.readyReplicas // 0)/\(.spec.replicas)"' | head -20
    echo ""

    echo "StatefulSets:"
    kubectl get statefulsets -A
    echo ""

    BAD_DEPLOYS=$(kubectl get deployments -A -o json | jq '[.items[] | select(.spec.replicas != (.status.readyReplicas // 0))] | length')
    BAD_STS=$(kubectl get statefulsets -A -o json | jq '[.items[] | select(.spec.replicas != (.status.readyReplicas // 0))] | length')

    if [ "$BAD_DEPLOYS" -eq 0 ] && [ "$BAD_STS" -eq 0 ]; then
        log_success "All deployments and StatefulSets healthy"
    else
        log_warning "Workloads not at desired replicas - Deployments: $BAD_DEPLOYS, StatefulSets: $BAD_STS"
        add_major_issue "Workloads not ready - Deployments: $BAD_DEPLOYS, StatefulSets: $BAD_STS"
    fi

    # Prometheus enrichment: unavailable replicas detail
    PROM_UNAVAIL=$(prom_query 'kube_deployment_status_replicas_unavailable > 0')
    if [ -n "$PROM_UNAVAIL" ]; then
        PROM_UNAVAIL_SUMMARY=$(echo "$PROM_UNAVAIL" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    results = d['data']['result']
    if results:
        parts = [f\"{r['metric'].get('namespace','?')}/{r['metric'].get('deployment','?')}({r['value'][1]})\" for r in results[:10]]
        print('Prom: unavailable replicas — ' + ', '.join(parts))
    else:
        print('Prom: all deployments at desired replica count')
except: pass
" 2>/dev/null)
        if [ -n "$PROM_UNAVAIL_SUMMARY" ]; then
            echo "  $PROM_UNAVAIL_SUMMARY"
            log_info "$PROM_UNAVAIL_SUMMARY"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 7: Pods Health"
{
    echo "Pod status summary:"
    NON_RUNNING=$(safe_count "kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded --no-headers 2>/dev/null | wc -l")
    echo "Non-running pods: $NON_RUNNING"
    echo ""

    echo "Pods with high restart counts (>5):"
    kubectl get pods -A -o json | jq -r '.items[] | select(.status.containerStatuses[]? | select(.restartCount > 5)) | "\(.metadata.namespace)/\(.metadata.name): \(.status.containerStatuses[0].restartCount) restarts"' | head -20
    echo ""

    # Stable totals line consumed by the --prev drift extractor.
    TOTAL_RESTARTS=$(kubectl get pods -A -o json 2>/dev/null \
        | jq '[.items[].status.containerStatuses[]?.restartCount // 0] | add // 0' 2>/dev/null \
        || echo 0)
    echo "Total restartCount (cluster-wide): ${TOTAL_RESTARTS:-0}"
    echo ""

    CRASH_LOOP=$(safe_count "kubectl get pods -A 2>/dev/null | grep -c 'CrashLoopBackOff'")
    PENDING=$(safe_count "kubectl get pods -A 2>/dev/null | grep -c 'Pending'")

    echo "CrashLoopBackOff pods: $CRASH_LOOP"
    echo "Pending pods: $PENDING"

    if [ "$CRASH_LOOP" -eq 0 ] && [ "$PENDING" -eq 0 ]; then
        log_success "No pods in CrashLoopBackOff or Pending"
    else
        log_critical "Pod issues - CrashLoopBackOff: $CRASH_LOOP, Pending: $PENDING"
        if [ "$CRASH_LOOP" -gt 0 ]; then
            add_critical_issue "Pods in CrashLoopBackOff: $CRASH_LOOP"
        fi
        if [ "$PENDING" -gt 0 ]; then
            add_critical_issue "Pods Pending: $PENDING"
        fi
    fi

    # Prometheus enrichment: pod restart rate (catches churn before hitting crash loop threshold)
    PROM_RESTARTS=$(prom_query 'topk(10, sum by (namespace, pod) (rate(kube_pod_container_status_restarts_total[15m]))) > 0')
    if [ -n "$PROM_RESTARTS" ]; then
        RESTART_SUMMARY=$(echo "$PROM_RESTARTS" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    results = d['data']['result']
    if results:
        parts = [f\"{r['metric'].get('namespace','?')}/{r['metric'].get('pod','?')}(\" + f\"{float(r['value'][1])*60:.2f}/min)\" for r in results[:5]]
        print('Prom: pods restarting (15m rate) — ' + ', '.join(parts))
    else:
        print('Prom: no pod restart churn detected (15m)')
except: pass
" 2>/dev/null)
        if [ -n "$RESTART_SUMMARY" ]; then
            echo "  $RESTART_SUMMARY"
            log_info "$RESTART_SUMMARY"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 8: Prometheus & Monitoring"
{
    echo "Prometheus pods:"
    kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus
    echo ""

    echo "Alertmanager pods:"
    kubectl get pods -n monitoring -l app.kubernetes.io/name=alertmanager
    echo ""

    PROM_RUNNING=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus -o json | jq '[.items[] | select(.status.phase=="Running")] | length')
    AM_RUNNING=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=alertmanager -o json | jq '[.items[] | select(.status.phase=="Running")] | length')

    if [ "$PROM_RUNNING" -gt 0 ] && [ "$AM_RUNNING" -gt 0 ]; then
        log_success "Prometheus and Alertmanager running"
    else
        log_critical "Monitoring issue - Prometheus: $PROM_RUNNING, Alertmanager: $AM_RUNNING"
        add_critical_issue "Monitoring system not running - Prom: $PROM_RUNNING, AM: $AM_RUNNING"
    fi

    # Prometheus enrichment: scrape target health (up == 0)
    # Only flag if a critical job is down (allowlist prevents false positives from optional targets)
    PROM_DOWN=$(prom_query 'up == 0')
    if [ -n "$PROM_DOWN" ]; then
        DOWN_SUMMARY=$(echo "$PROM_DOWN" | python3 -c "
import sys, json
CRITICAL_JOBS = {'kubelet','kube-state-metrics','edot-collector','findmy-traccar-sync','bank-refresh','kube-apiserver','cilium-operator'}
try:
    d = json.load(sys.stdin)
    results = d['data']['result']
    critical = [r for r in results if r['metric'].get('job','') in CRITICAL_JOBS]
    all_down = [f\"{r['metric'].get('job','?')}({r['metric'].get('instance','?')})\" for r in results[:10]]
    if results:
        print(f\"Prom: {len(results)} scrape target(s) down — \" + ', '.join(all_down))
        if critical:
            names = ', '.join(f\"{r['metric'].get('job','?')}\" for r in critical)
            print(f\"CRITICAL_JOBS_DOWN:{names}\")
except: pass
" 2>/dev/null)
        if [ -n "$DOWN_SUMMARY" ]; then
            FIRST_LINE=$(echo "$DOWN_SUMMARY" | head -1)
            CRIT_LINE=$(echo "$DOWN_SUMMARY" | grep "CRITICAL_JOBS_DOWN:" | head -1)
            echo "  $FIRST_LINE"
            log_info "$FIRST_LINE"
            if [ -n "$CRIT_LINE" ]; then
                CRIT_JOBS=${CRIT_LINE#CRITICAL_JOBS_DOWN:}
                log_warning "Critical scrape targets down: $CRIT_JOBS"
                add_minor_issue "Prometheus scrape targets down: $CRIT_JOBS"
            fi
        fi
    else
        log_success "All Prometheus scrape targets healthy"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 9: Alertmanager Alerts"
{
    echo "Checking Alertmanager alerts via Prometheus API..."
    echo ""

    # Port-forward in background
    kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 > /dev/null 2>&1 &
    PF_PID=$!
    sleep 3

    ALERT_CHECK=$(curl -s 'http://localhost:9090/api/v1/alerts' 2>/dev/null || echo '{"status":"error"}')

    if echo "$ALERT_CHECK" | jq -e '.status == "success"' > /dev/null 2>&1; then
        echo "Alert data retrieved successfully"
        echo ""

        # Get all firing alerts excluding Watchdog
        FIRING_ALERTS=$(echo "$ALERT_CHECK" | jq -r '[.data.alerts[] | select(.state == "firing" and .labels.alertname != "Watchdog" and .labels.alertname != "InfoInhibitor")] | length')

        echo "Firing alerts (excluding Watchdog): $FIRING_ALERTS"
        echo ""

        if [ "$FIRING_ALERTS" -gt 0 ]; then
            echo "Active Alerts:"
            # Tag each alert with [noise: ...] when it matches noise_allowlist.yaml
            # (alertname + namespace are included in the line so substring match works).
            echo "$ALERT_CHECK" | jq -r '.data.alerts[] | select(.state == "firing" and .labels.alertname != "Watchdog" and .labels.alertname != "InfoInhibitor") | "  - \(.labels.alertname) [ns=\(.labels.namespace // "?")] (\(.labels.severity // "unknown")): \(.annotations.summary // .annotations.description // "No description")"' | head -20 \
                | while IFS= read -r _alert_line; do
                    tag=$(_noise_tag "$_alert_line")
                    printf '%s%s\n' "$_alert_line" "$tag"
                done

            log_warning "Active alerts firing: $FIRING_ALERTS"
            add_major_issue "Prometheus alerts firing: $FIRING_ALERTS"
        else
            log_success "No alerts firing"
        fi
    else
        log_warning "Unable to retrieve alert data from Prometheus"
        add_minor_issue "Could not check Prometheus alerts"
    fi

    # Kill port-forward
    kill $PF_PID 2>/dev/null || true
    wait $PF_PID 2>/dev/null || true
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 10: Longhorn Storage"
{
    echo "Longhorn volumes:"
    kubectl get volumes -n storage -o wide | head -20
    echo ""

    TOTAL_VOLUMES=$(safe_count "kubectl get volumes -n storage --no-headers 2>/dev/null | wc -l")
    UNHEALTHY_VOLUMES=$(kubectl get volumes -n storage -o json 2>/dev/null | jq '[.items[] | select(.status.state != "attached" or .status.robustness != "healthy")] | length')

    echo "Volumes: $((TOTAL_VOLUMES - UNHEALTHY_VOLUMES))/$TOTAL_VOLUMES healthy"

    if [ "$UNHEALTHY_VOLUMES" -gt 0 ]; then
        echo "Unhealthy volumes:"
        kubectl get volumes -n storage -o json | jq -r '.items[] | select(.status.state != "attached" or .status.robustness != "healthy") | "\(.metadata.name): state=\(.status.state) robustness=\(.status.robustness)"'
    fi

    echo ""
    echo "PVC status:"
    PENDING_PVC=$(safe_count "kubectl get pvc -A 2>/dev/null | grep -E '(Pending|Lost|Unknown)' | wc -l")
    echo "Pending/Lost/Unknown PVCs: $PENDING_PVC"

    echo ""
    AUTO_DELETE=$(kubectl get settings.longhorn.io auto-delete-pod-when-volume-detached-unexpectedly -n storage -o jsonpath='{.value}' 2>/dev/null || echo "unknown")
    echo "autoDeletePodWhenVolumeDetachedUnexpectedly: $AUTO_DELETE (should be false)"

    # Check volume replica count mismatches via robustness field
    # NOTE: currentNumberOfReplicas is often null in the status API even when healthy;
    # use the robustness field as the authoritative health indicator instead.
    echo ""
    echo "Volume replica mismatches (non-healthy robustness):"
    REPLICA_MISMATCHES=$(kubectl get volumes -n storage -o json 2>/dev/null | jq -r '
        .items[] |
        select(.status.robustness != null and .status.robustness != "healthy") |
        "\(.metadata.name): robustness=\(.status.robustness) state=\(.status.state)"
    ' || echo "")
    if [ -n "$REPLICA_MISMATCHES" ]; then
        echo "$REPLICA_MISMATCHES"
        MISMATCH_COUNT=$(echo "$REPLICA_MISMATCHES" | grep -c "robustness=" || echo "0")
        echo "Total volumes with unhealthy robustness: $MISMATCH_COUNT"
    else
        echo "None"
    fi
    echo ""

    # Check for recent unexpected volume detachment events (last 24h)
    DETACH_EVENTS=$(safe_count "kubectl get events -n storage --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | grep -i 'DetachedUnexpectedly' | wc -l")
    echo "Unexpected volume detachment events (recent): $DETACH_EVENTS"

    # Check for Flux/Longhorn admission webhook conflicts
    ADMISSION_CONFLICTS=$(safe_count "kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | grep -i 'admission webhook.*longhorn.*denied' | wc -l")
    echo "Longhorn admission webhook conflicts: $ADMISSION_CONFLICTS"

    if [ "$UNHEALTHY_VOLUMES" -eq 0 ] && [ "$PENDING_PVC" -eq 0 ] && [ "$AUTO_DELETE" == "false" ] && [ -z "$REPLICA_MISMATCHES" ]; then
        log_success "Longhorn storage healthy"
    else
        log_warning "Storage issues - Unhealthy volumes: $UNHEALTHY_VOLUMES, Pending PVCs: $PENDING_PVC, AutoDelete: $AUTO_DELETE"
        if [ "$UNHEALTHY_VOLUMES" -gt 0 ]; then
            add_major_issue "Unhealthy Longhorn volumes: $UNHEALTHY_VOLUMES"
        fi
        if [ "$PENDING_PVC" -gt 0 ]; then
            add_major_issue "Pending PVCs: $PENDING_PVC"
        fi
        if [ "$AUTO_DELETE" != "false" ]; then
            add_minor_issue "AutoDelete setting is $AUTO_DELETE (should be false)"
        fi
        if [ -n "$REPLICA_MISMATCHES" ]; then
            add_minor_issue "Longhorn volumes with unhealthy robustness: $MISMATCH_COUNT"
        fi
    fi
    if [ "$DETACH_EVENTS" -gt 5 ]; then
        log_warning "High volume detachment event count: $DETACH_EVENTS"
        add_major_issue "Unexpected volume detachments: $DETACH_EVENTS events"
    fi
    if [ "$ADMISSION_CONFLICTS" -gt 0 ]; then
        log_warning "Longhorn admission webhook conflicts detected: $ADMISSION_CONFLICTS"
        add_minor_issue "Longhorn admission webhook conflicts: $ADMISSION_CONFLICTS"
    fi

    # Check Longhorn node disk capacity (storageAvailable vs storageMaximum)
    echo ""
    echo "Longhorn node disk capacity:"
    kubectl get nodes.longhorn.io -n storage -o json 2>/dev/null | jq -r '
        .items[] |
        (.spec.disks // {}) | to_entries[] |
        select(.value.storageMaximum > 0) |
        "\(env.LONGHORN_NODE // "node")/\(.key): \((.value.storageAvailable / .value.storageMaximum * 100 | floor))% free (\(.value.storageAvailable / 1073741824 | floor)Gi free of \(.value.storageMaximum / 1073741824 | floor)Gi)"
    ' 2>/dev/null | tee /tmp/_lh_disk_check.txt || echo "Unable to retrieve Longhorn disk data"
    DISK_CRITICAL=$(grep -c ' [0-9]\b\| [1-9]\b' /tmp/_lh_disk_check.txt 2>/dev/null || echo "0")
    LH_DISK_LOW=$(kubectl get nodes.longhorn.io -n storage -o json 2>/dev/null | jq '
        [.items[].spec.disks // {} | to_entries[] |
        select(.value.storageMaximum > 0 and (.value.storageAvailable / .value.storageMaximum) < 0.15)] | length
    ' 2>/dev/null || echo "0")
    LH_DISK_WARN=$(kubectl get nodes.longhorn.io -n storage -o json 2>/dev/null | jq '
        [.items[].spec.disks // {} | to_entries[] |
        select(.value.storageMaximum > 0 and (.value.storageAvailable / .value.storageMaximum) >= 0.15 and (.value.storageAvailable / .value.storageMaximum) < 0.25)] | length
    ' 2>/dev/null || echo "0")
    rm -f /tmp/_lh_disk_check.txt
    if [ "${LH_DISK_LOW:-0}" -gt 0 ] 2>/dev/null; then
        log_critical "Longhorn disk(s) critically low (<15% free): $LH_DISK_LOW disk(s)"
        add_critical_issue "Longhorn storage critically low: $LH_DISK_LOW disk(s) have <15% free space"
    elif [ "${LH_DISK_WARN:-0}" -gt 0 ] 2>/dev/null; then
        log_warning "Longhorn disk(s) running low (15-25% free): $LH_DISK_WARN disk(s)"
        add_major_issue "Longhorn storage low: $LH_DISK_WARN disk(s) have 15-25% free space"
    else
        log_success "Longhorn disk capacity healthy"
    fi
} >> "$OUTPUT_FILE" 2>&1

#######################################
# Phase 3: Application & Service Checks
#######################################

log_section "Section 11: Container Logs Analysis"
{
    echo "Checking infrastructure logs for errors..."

    INFRA_EXCLUDE=$(build_grep_exclude "${INFRA_LOG_FALSE_POSITIVES[@]}")

    CILIUM_ERRORS=$(safe_count "kubectl logs -n kube-system -l app.kubernetes.io/name=cilium --tail=100 --since=24h 2>&1 | grep -E 'level=(error|fatal|critical)|\[(ERROR|FATAL|CRITICAL)\]' | grep -vE '$INFRA_EXCLUDE' | wc -l")
    echo "Cilium errors (24h): $CILIUM_ERRORS"

    COREDNS_ERRORS=$(safe_count "kubectl logs -n kube-system -l k8s-app=kube-dns --tail=100 --since=24h 2>&1 | grep -E 'level=(error|fatal)|\[(ERROR|FATAL)\]' | grep -vE '$INFRA_EXCLUDE' | wc -l")
    echo "CoreDNS errors (24h): $COREDNS_ERRORS"

    FLUX_ERRORS=$(safe_count "kubectl logs -n flux-system deployment/kustomize-controller --tail=50 --since=24h 2>&1 | grep -E 'level=(error|fatal)|\[(ERROR|FATAL)\]|error:' | grep -vE '$INFRA_EXCLUDE' | wc -l")
    echo "Flux controller errors (24h): $FLUX_ERRORS"

    CERT_ERRORS=$(safe_count "kubectl logs -n cert-manager deployment/cert-manager --tail=50 --since=24h 2>&1 | grep -E 'level=error|\[ERROR\]|error:' | grep -vE '$INFRA_EXCLUDE' | wc -l")
    echo "cert-manager errors (24h): $CERT_ERRORS"

    TOTAL_ERRORS=$((CILIUM_ERRORS + COREDNS_ERRORS + FLUX_ERRORS + CERT_ERRORS))

    if [ "$TOTAL_ERRORS" -lt 10 ]; then
        log_success "Infrastructure logs clean (total errors: $TOTAL_ERRORS)"
    elif [ "$TOTAL_ERRORS" -lt 50 ]; then
        log_warning "Infrastructure errors detected: $TOTAL_ERRORS"
        add_minor_issue "Infrastructure log errors: $TOTAL_ERRORS"
    else
        log_critical "High error count in infrastructure logs: $TOTAL_ERRORS"
        add_critical_issue "High infrastructure error count: $TOTAL_ERRORS"
    fi

    # ES enrichment: 7-day error context for infra namespaces
    ES_INFRA=$(es_query '{
      "size": 0,
      "query": {"bool": {
        "should": [
          {"wildcard": {"body.text": "*ERROR*"}},
          {"wildcard": {"body.text": "*FATAL*"}}
        ],
        "minimum_should_match": 1,
        "filter": [
          {"range": {"@timestamp": {"gte": "now-7d"}}},
          {"terms": {"resource.attributes.k8s.namespace.name": ["kube-system", "flux-system", "cert-manager", "monitoring"]}}
        ]
      }},
      "aggs": {"by_ns": {"terms": {"field": "resource.attributes.k8s.namespace.name", "size": 10}}}
    }')
    if [ -n "$ES_INFRA" ]; then
        ES_INFRA_SUMMARY=$(echo "$ES_INFRA" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    total = d['hits']['total']['value']
    parts = [f\"{b['key']}:{b['doc_count']}\" for b in d['aggregations']['by_ns']['buckets']]
    print(f'ES 7d context: {total} total errors — ' + ', '.join(parts))
except: print('')
" 2>/dev/null)
        if [ -n "$ES_INFRA_SUMMARY" ]; then
            echo "  $ES_INFRA_SUMMARY"
            log_info "$ES_INFRA_SUMMARY"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 12: Talos System Health"
{
    echo "Checking Talos node health..."

    if command -v talosctl &> /dev/null; then
        TOTAL_TALOS_ISSUES=0
        for node in $NODE_IPS; do
            echo "=== Node $node ==="
            SERVICES_OUTPUT=$(talosctl services --nodes "$node" 2>&1 || echo "Failed to get services for $node")
            echo "$SERVICES_OUTPUT" | head -20

            # Count non-running services (exclude header line)
            NOT_RUNNING=$(echo "$SERVICES_OUTPUT" | grep -v "^NODE" | grep -v "^$" | grep -v "Running" | wc -l | tr -cd '0-9')
            if [ "${NOT_RUNNING:-0}" -gt 0 ]; then
                echo "  Non-running services on $node: $NOT_RUNNING"
                TOTAL_TALOS_ISSUES=$((TOTAL_TALOS_ISSUES + NOT_RUNNING))
            fi
            echo ""
        done

        if [ "$TOTAL_TALOS_ISSUES" -gt 0 ]; then
            log_warning "Talos services not running across all nodes: $TOTAL_TALOS_ISSUES"
            add_major_issue "Talos services not in Running state: $TOTAL_TALOS_ISSUES"
        else
            log_success "All Talos services running on all nodes"
        fi
    else
        log_warning "talosctl not available, skipping Talos checks"
        add_minor_issue "talosctl not available for Talos health checks"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 13: Hardware Health"
{
    echo "Checking hardware health..."

    if command -v talosctl &> /dev/null; then
        for node in $NODE_IPS; do
            echo "=== Hardware errors on $node ==="
            # Filter to actual hardware faults only; exclude known software/service error messages
        ERRORS=$(safe_count "talosctl dmesg --nodes '$node' 2>&1 | grep -iE '(hardware|ecc|mce|edac|uncorrected|corrected error|pcie.*error|disk error|bad sector|ata.*error|nvme.*error)' | grep -viE '(DiscoveryService|controller-runtime|rpc error|context deadline|connection refused|EOF|dialing)' | wc -l")
            echo "Hardware errors: $ERRORS"
            if [ "$ERRORS" -gt 10 ]; then
                add_minor_issue "High hardware errors on $node: $ERRORS"
            fi
        done

        # Talos discovery service errors (DiscoveryServiceController / hello failed)
        # A short burst (up to ~25) is normal during a transient upstream outage at discovery.talos.dev;
        # only alert if the count is high enough to indicate a sustained or recurring connectivity problem.
        for node in $NODE_IPS; do
            DISC_COUNT=$(safe_count "talosctl dmesg --nodes '$node' 2>&1 | grep -iE '(DiscoveryServiceController|hello failed)' | wc -l")
            echo "Talos discovery service errors on $node: $DISC_COUNT"
            if [ "$DISC_COUNT" -gt 30 ]; then
                add_minor_issue "Talos discovery service errors on $node: $DISC_COUNT (discovery.talos.dev unreachable)"
            fi
        done

        log_success "Hardware health check completed"
    else
        log_warning "talosctl not available, skipping hardware checks"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 14: Resource Utilization"
{
    echo "Node resource usage:"
    kubectl top nodes
    echo ""

    echo "Top 10 CPU consuming pods:"
    kubectl top pods -A --sort-by=cpu 2>/dev/null | head -15 || echo "Metrics not available"
    echo ""

    echo "Top 10 memory consuming pods:"
    kubectl top pods -A --sort-by=memory 2>/dev/null | head -15 || echo "Metrics not available"
    echo ""

    PRESSURE=$(kubectl get nodes -o json | jq -r '.items[] | select(.status.conditions[] | select(.type=="DiskPressure" or .type=="MemoryPressure") | .status=="True") | .metadata.name')

    if [ -z "$PRESSURE" ]; then
        log_success "No resource pressure detected"
    else
        log_critical "Resource pressure detected on: $PRESSURE"
        add_critical_issue "Resource pressure on nodes: $PRESSURE"
    fi

    # Prometheus enrichment: per-node CPU and memory via kubelet metrics (informational)
    PROM_NODE_CPU=$(prom_query 'sum by (node) (rate(container_cpu_usage_seconds_total{container!=""}[5m])) / on(node) group_left() sum by (node) (kube_node_status_capacity{resource="cpu"}) * 100')
    if [ -n "$PROM_NODE_CPU" ]; then
        CPU_SUMMARY=$(echo "$PROM_NODE_CPU" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    results = d['data']['result']
    parts = [f\"{r['metric'].get('node','?')}:{float(r['value'][1]):.1f}%\" for r in results]
    if parts:
        print('Prom node CPU (5m): ' + ', '.join(parts))
except: pass
" 2>/dev/null)
        if [ -n "$CPU_SUMMARY" ]; then
            echo "  $CPU_SUMMARY"
            log_info "$CPU_SUMMARY"
        fi
    fi

    PROM_NODE_MEM=$(prom_query 'sum by (node) (container_memory_working_set_bytes{container!=""}) / on(node) group_left() sum by (node) (kube_node_status_capacity{resource="memory"}) * 100')
    if [ -n "$PROM_NODE_MEM" ]; then
        MEM_SUMMARY=$(echo "$PROM_NODE_MEM" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    results = d['data']['result']
    parts = [f\"{r['metric'].get('node','?')}:{float(r['value'][1]):.1f}%\" for r in results]
    if parts:
        print('Prom node memory: ' + ', '.join(parts))
except: pass
" 2>/dev/null)
        if [ -n "$MEM_SUMMARY" ]; then
            echo "  $MEM_SUMMARY"
            log_info "$MEM_SUMMARY"
        fi
    fi

    # Check for nodes not in Ready condition (kubelet stopped, network partition, etc.)
    echo ""
    echo "Node Ready conditions:"
    NOT_READY_NODES=$(kubectl get nodes -o json | jq -r '.items[] | select(.status.conditions[] | select(.type=="Ready" and .status!="True")) | .metadata.name')
    if [ -z "$NOT_READY_NODES" ]; then
        log_success "All nodes Ready"
    else
        log_critical "Nodes not Ready: $NOT_READY_NODES"
        add_critical_issue "Nodes not in Ready state: $NOT_READY_NODES"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 15: Backup System"
{
    echo "Backup system status:"
    kubectl get cronjob -n storage daily-backup-all-volumes 2>/dev/null || echo "Backup CronJob not found"
    echo ""

    BACKUP_JOB=$(kubectl get jobs -n storage --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null | grep -o 'daily-backup-all-volumes[^ ]*' | head -1 || echo "")
    if [ -n "$BACKUP_JOB" ]; then
        echo "Last backup job:"
        kubectl get job -n storage "$BACKUP_JOB" 2>/dev/null || echo "Job details not available"

        # Check staleness: flag if last successful backup completed more than 48 hours ago
        LAST_BACKUP_TIME=$(kubectl get job -n storage "$BACKUP_JOB" -o jsonpath='{.status.completionTime}' 2>/dev/null || echo "")
        if [ -n "$LAST_BACKUP_TIME" ]; then
            # date -d is GNU only; use python3 for portable ISO8601 parsing
            LAST_BACKUP_EPOCH=$(python3 -c "import datetime,sys; t=sys.argv[1].rstrip('Z'); print(int(datetime.datetime.fromisoformat(t).replace(tzinfo=datetime.timezone.utc).timestamp()))" "$LAST_BACKUP_TIME" 2>/dev/null || echo "0")
            NOW_EPOCH=$(date +%s)
            BACKUP_AGE_HOURS=$(( (NOW_EPOCH - LAST_BACKUP_EPOCH) / 3600 ))
            echo "Last successful backup completed: ${BACKUP_AGE_HOURS}h ago ($LAST_BACKUP_TIME)"
            if [ "$BACKUP_AGE_HOURS" -gt 48 ]; then
                log_warning "Last backup is stale: ${BACKUP_AGE_HOURS}h ago (threshold: 48h)"
                add_major_issue "Backup stale: last successful backup was ${BACKUP_AGE_HOURS}h ago (expected daily)"
            else
                log_success "Backup system operational (last: ${BACKUP_AGE_HOURS}h ago)"
            fi
        else
            log_warning "Backup job found but no completion time recorded"
            add_minor_issue "Backup job has no completion timestamp - may still be running or failed"
        fi
    else
        log_warning "No backup jobs found"
        add_minor_issue "No backup jobs found"
    fi

    # iCloud sync check
    echo ""
    echo "iCloud sync (icloud-docker-mu):"
    ICLOUD_POD=$(kubectl get pods -n backup -l app.kubernetes.io/name=icloud-docker-mu -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$ICLOUD_POD" ]; then
        ICLOUD_PHASE=$(kubectl get pod -n backup "$ICLOUD_POD" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
        ICLOUD_RESTARTS=$(kubectl get pod -n backup "$ICLOUD_POD" -o jsonpath='{.status.containerStatuses[0].restartCount}' 2>/dev/null || echo "0")
        echo "  iCloud pod: $ICLOUD_POD, phase: $ICLOUD_PHASE, restarts: $ICLOUD_RESTARTS"
        if [ "$ICLOUD_PHASE" != "Running" ]; then
            log_warning "iCloud sync pod is not running (phase: $ICLOUD_PHASE)"
            add_minor_issue "icloud-docker-mu pod not running (phase: $ICLOUD_PHASE)"
        else
            # Filter out known Apple API flakiness (throttles, 530 CF errors, PCS cookie refresh — all normal for iCloud)
            # Scope to last 24h only; iCloud-docker has sparse logs and old errors shouldn't keep reappearing.
            ICLOUD_LOG_ERRORS=$(safe_count "kubectl logs -n backup '$ICLOUD_POD' --since=24h 2>/dev/null | grep -iE '(error|ERROR|failed|FAILED)' | grep -viE '429|503|530|throttl|retry|connection reset|rate limit|PCS_KEY|cookie pcs' | wc -l")
            echo "  iCloud log errors (last 24h, filtered): $ICLOUD_LOG_ERRORS"
            if [ "$ICLOUD_LOG_ERRORS" -gt 5 ]; then
                log_warning "iCloud sync pod has errors in recent logs: $ICLOUD_LOG_ERRORS"
                add_minor_issue "icloud-docker-mu recent log errors: $ICLOUD_LOG_ERRORS"
            else
                log_success "iCloud sync pod running (restarts: $ICLOUD_RESTARTS)"
            fi
        fi
    else
        echo "  iCloud sync pod not found (namespace: backup)"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 17: Security Checks"
{
    echo "Security posture check..."

    ROOT_PODS=$(kubectl get pods -A -o json | jq '[.items[] | select(.spec.securityContext.runAsUser == 0 or (.spec.containers[].securityContext.runAsUser // 0) == 0)] | length')
    echo "Pods running as root: $ROOT_PODS"

    LB_SERVICES=$(safe_count "kubectl get svc -A --field-selector spec.type=LoadBalancer --no-headers 2>/dev/null | wc -l")
    echo "LoadBalancer services: $LB_SERVICES"

    INGRESSES=$(safe_count "kubectl get ingress -A --no-headers 2>/dev/null | wc -l")
    echo "Total ingresses: $INGRESSES"

    if [ "$ROOT_PODS" -eq 0 ]; then
        log_success "No pods running as root"
    else
        log_info "Pods running as root: $ROOT_PODS (review for security)"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 18: Network Infrastructure (UniFi)"
{
    echo "Checking UniFi network..."
    UNIFI_ISSUES=0

    # --- Live controller check via unifictl (optional) ---
    if command -v unifictl &> /dev/null; then
        echo "=== Controller Health ==="
        unifictl local health get 2>&1 || echo "UniFi controller not accessible"
        echo ""

        echo "=== Devices ==="
        unifictl local devices 2>/dev/null || echo "Unable to list devices"
        echo ""

        OFFLINE_DEVICES=$(unifictl local devices -o json 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    items = d.get('data', d) if isinstance(d, dict) else d
    offline = [x.get('name','?') for x in items if x.get('state') != 1]
    print(len(offline))
    for o in offline: print(' ', o)
except: print(0)
" 2>/dev/null | head -1 | tr -d '\r\n' || echo "0")

        if [ "${OFFLINE_DEVICES:-0}" -gt 0 ] 2>/dev/null; then
            log_warning "UniFi offline devices: $OFFLINE_DEVICES"
            add_major_issue "UniFi devices offline: $OFFLINE_DEVICES"
            UNIFI_ISSUES=$((UNIFI_ISSUES + 1))
        fi

        echo "=== Clients ==="
        WIRED=$(unifictl local clients --wired -o json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('data',d)))" 2>/dev/null || echo "?")
        WIRELESS=$(unifictl local clients --wireless -o json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('data',d)))" 2>/dev/null || echo "?")
        echo "Wired clients: $WIRED  |  Wireless clients: $WIRELESS"
        echo ""
    else
        echo "(unifictl not available — skipping live controller checks)"
        echo ""
    fi

    # --- Historical data from InfluxDB (UnPoller) ---
    echo "=== UnPoller / InfluxDB Historical Data ==="

    # Fetch InfluxDB token from Kubernetes secret at runtime
    INFLUX_TOKEN=$(kubectl get secret -n monitoring unpoller-credentials \
        -o jsonpath='{.data.upConfig}' 2>/dev/null \
        | base64 -d 2>/dev/null \
        | python3 -c "import sys; cfg=sys.stdin.read(); lines=[l for l in cfg.split('\n') if 'auth_token' in l]; print(lines[0].split('=',1)[1].strip().strip('\"') if lines else '')" 2>/dev/null)

    INFLUX_URL="http://influxdb-influxdb2.databases.svc.cluster.local:80"
    INFLUX_ORG="influxdata"
    INFLUX_BUCKET="default"

    # Port-forward to InfluxDB for external access
    INFLUX_PORT=18086
    kubectl port-forward -n databases svc/influxdb-influxdb2 "${INFLUX_PORT}:80" > /dev/null 2>&1 &
    INFLUX_PF_PID=$!
    sleep 2

    influx_query() {
        curl -s --connect-timeout 5 \
            -H "Authorization: Token ${INFLUX_TOKEN}" \
            -H "Content-Type: application/vnd.flux" \
            "http://localhost:${INFLUX_PORT}/api/v2/query?org=${INFLUX_ORG}" \
            --data "$1" 2>/dev/null
    }

    # Check UnPoller pod health
    UNPOLLER_POD=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=unpoller \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -z "$UNPOLLER_POD" ]; then
        log_warning "UnPoller pod not found"
        add_major_issue "UnPoller pod not found - no UniFi metrics being collected"
        UNIFI_ISSUES=$((UNIFI_ISSUES + 1))
    else
        UNPOLLER_RESTARTS=$(kubectl get pod -n monitoring "$UNPOLLER_POD" \
            -o jsonpath='{.status.containerStatuses[0].restartCount}' 2>/dev/null || echo "0")
        echo "UnPoller pod: $UNPOLLER_POD (restarts: $UNPOLLER_RESTARTS)"
        if [ "$UNPOLLER_RESTARTS" -gt 20 ]; then
            log_warning "UnPoller has high restart count: $UNPOLLER_RESTARTS"
            add_minor_issue "UnPoller restart count high: $UNPOLLER_RESTARTS"
            UNIFI_ISSUES=$((UNIFI_ISSUES + 1))
        fi
        echo ""
    fi

    if [ -n "$INFLUX_TOKEN" ]; then
        # CSV column layout after keep():
        #   uap/usw uptime+num_sta: ,result,table,_value,_field,model,name
        #   usw uptime only:        ,result,table,_value,model,name
        #   usg_wan_ports speed:    ,result,table,_value,ifname
        #   reboots keep(_measurement,name,_time): ,result,table,_measurement,name,_time

        # Helper: parse InfluxDB annotated CSV, stripping \r and skipping annotation/header rows
        # Data rows start with ',_result'; header rows start with ',result'; annotations start with '#'
        PYPARSE="import sys, collections
def rows(text):
    for l in text.replace('\r','').split('\n'):
        l = l.strip()
        if l and not l.startswith('#') and not l.startswith(',result'):
            yield [c.strip() for c in l.split(',')]
"

        # Access Points: name, model, uptime, client count
        # CSV cols: ,_result,table,_value,_field,model,name  (indices 3,4,5,6)
        echo "--- Access Points (from InfluxDB) ---"
        influx_query 'from(bucket:"default") |> range(start: -10m) |> filter(fn: (r) => r._measurement == "uap" and (r._field == "uptime" or r._field == "num_sta")) |> last() |> keep(columns: ["_field","_value","name","model"])' \
        | python3 -c "
${PYPARSE}
devices = collections.defaultdict(dict)
for c in rows(sys.stdin.read()):
    if len(c) >= 7:
        val, field, model, name = c[3], c[4], c[5], c[6]
        devices[name]['model'] = model
        devices[name][field] = val
for name, d in sorted(devices.items()):
    uptime_s = int(d.get('uptime', 0) or 0)
    print(f'  {name} ({d.get(\"model\",\"?\")}): uptime={uptime_s//86400}d  clients={d.get(\"num_sta\",\"?\")}')
"
        echo ""

        # Switches: name, model, uptime
        # CSV cols: ,_result,table,_value,model,name  (indices 3,4,5)
        echo "--- Switches (from InfluxDB) ---"
        influx_query 'from(bucket:"default") |> range(start: -10m) |> filter(fn: (r) => r._measurement == "usw" and r._field == "uptime") |> last() |> keep(columns: ["_value","name","model"])' \
        | python3 -c "
${PYPARSE}
for c in rows(sys.stdin.read()):
    if len(c) >= 5:
        val, model, name = int(c[3] or 0), c[4], c[5]
        print(f'  {name} ({model}): uptime={val//86400}d')
"
        echo ""

        # WAN link speeds
        # CSV cols: ,_result,table,_value,ifname  (indices 3,4)
        echo "--- WAN Ports (from InfluxDB) ---"
        influx_query 'from(bucket:"default") |> range(start: -10m) |> filter(fn: (r) => r._measurement == "usg_wan_ports" and r._field == "speed") |> last() |> keep(columns: ["_value","ifname"])' \
        | python3 -c "
${PYPARSE}
for c in rows(sys.stdin.read()):
    if len(c) >= 4:
        speed, iface = c[3], c[4] if len(c) > 4 else '?'
        print(f'  {iface}: {speed} Mbps')
"
        echo ""

        # Device reboots in last 24h (uptime regression)
        # CSV cols after keep(name,_time): ,_result,table,name,_time  (indices 3,4)
        echo "--- Device Reboots (last 24h, from InfluxDB) ---"
        REBOOT_OUTPUT=$(influx_query 'from(bucket:"default") |> range(start: -24h) |> filter(fn: (r) => (r._measurement == "uap" or r._measurement == "usw") and r._field == "uptime") |> derivative(unit: 30s, nonNegative: false) |> filter(fn: (r) => r._value < -1000) |> keep(columns: ["name","_time"])' \
        | python3 -c "
${PYPARSE}
data = list(rows(sys.stdin.read()))
if not data:
    print('None detected')
else:
    for c in data:
        if len(c) >= 4:
            print(f'  {c[3]} rebooted around {c[4] if len(c) > 4 else \"?\"}')
    print(f'Total reboots: {len(data)}')
")
        echo "$REBOOT_OUTPUT"
        REBOOT_COUNT=$(echo "$REBOOT_OUTPUT" | grep -c "rebooted" || true)
        if [ "$REBOOT_COUNT" -gt 0 ]; then
            log_warning "$REBOOT_COUNT UniFi device reboot(s) detected in last 24h"
            add_minor_issue "UniFi device reboots in last 24h: $REBOOT_COUNT"
            UNIFI_ISSUES=$((UNIFI_ISSUES + 1))
        else
            echo ""
        fi

        # AP/SW device count sanity check — count data rows
        AP_COUNT=$(influx_query 'from(bucket:"default") |> range(start: -10m) |> filter(fn: (r) => r._measurement == "uap" and r._field == "uptime") |> last() |> keep(columns: ["name"])' \
        | python3 -c "${PYPARSE}
print(len(list(rows(sys.stdin.read()))))" 2>/dev/null || echo "0")

        SW_COUNT=$(influx_query 'from(bucket:"default") |> range(start: -10m) |> filter(fn: (r) => r._measurement == "usw" and r._field == "uptime") |> last() |> keep(columns: ["name"])' \
        | python3 -c "${PYPARSE}
print(len(list(rows(sys.stdin.read()))))" 2>/dev/null || echo "0")

        echo "Device counts visible to UnPoller: ${AP_COUNT} APs, ${SW_COUNT} switches"

        if [ "${AP_COUNT}" -lt 3 ]; then
            log_warning "UnPoller seeing fewer APs than expected: ${AP_COUNT} (expected 4)"
            add_minor_issue "UnPoller AP count low: ${AP_COUNT}/4"
            UNIFI_ISSUES=$((UNIFI_ISSUES + 1))
        fi
        if [ "${SW_COUNT}" -lt 4 ]; then
            log_warning "UnPoller seeing fewer switches than expected: ${SW_COUNT} (expected 6)"
            add_minor_issue "UnPoller switch count low: ${SW_COUNT}/6"
            UNIFI_ISSUES=$((UNIFI_ISSUES + 1))
        fi
    else
        log_warning "InfluxDB token not available — skipping historical UniFi checks"
        add_minor_issue "Could not read UnPoller InfluxDB token from secret"
        UNIFI_ISSUES=$((UNIFI_ISSUES + 1))
    fi

    kill "$INFLUX_PF_PID" 2>/dev/null || true

    if [ "$UNIFI_ISSUES" -eq 0 ]; then
        log_success "UniFi network infrastructure healthy"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 19: Network Connectivity"
{
    echo "Ingress controllers:"
    kubectl get svc -n network | grep ingress || echo "No ingress services found"
    echo ""

    echo "external-dns status:"
    kubectl get deployment -n network external-dns 2>/dev/null || echo "external-dns not found"
    echo ""

    # Check external-dns restart count
    EXTDNS_RESTARTS=$(kubectl get deployment -n network external-dns -o jsonpath='{.status.conditions}' 2>/dev/null | jq -r '.' 2>/dev/null || echo "")
    EXTDNS_PODS_READY=$(kubectl get deployment -n network external-dns -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    EXTDNS_PODS_DESIRED=$(kubectl get deployment -n network external-dns -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "1")
    echo "external-dns pods: $EXTDNS_PODS_READY/$EXTDNS_PODS_DESIRED ready"

    # Check Cloudflare tunnel
    echo ""
    echo "Cloudflare tunnel:"
    kubectl get pods -n network -l app.kubernetes.io/name=cloudflared 2>/dev/null || echo "Cloudflare tunnel not found"
    CLOUDFLARED_RUNNING=$(kubectl get pods -n network -l app.kubernetes.io/name=cloudflared -o json 2>/dev/null | jq '[.items[] | select(.status.phase=="Running")] | length' || echo "0")
    echo "cloudflared running pods: $CLOUDFLARED_RUNNING"

    # Check ingress-nginx error rate
    echo ""
    INGRESS_ERRORS=$(safe_count "kubectl logs -n network -l app.kubernetes.io/name=ingress-nginx --tail=100 --since=1h 2>&1 | grep -E '\[error\]|\[emerg\]' | wc -l")
    echo "Ingress controller errors (last hour): $INGRESS_ERRORS"

    # Check NAS connectivity (important for storage)
    # Use curl (HTTP) as primary check — more reliable than ping across all platforms
    # (macOS/Linux/WSL all support curl; ping -W semantics differ between platforms)
    echo ""
    echo "NAS connectivity (192.168.31.230):"
    curl -s --connect-timeout 2 http://192.168.31.230/ -o /dev/null 2>/dev/null && echo "NAS reachable" || { nc -z -w 2 192.168.31.230 22 2>/dev/null && echo "NAS reachable (SSH)"; } || echo "NAS unreachable - check storage integration"

    NETWORK_ISSUES=0
    if [ "$EXTDNS_PODS_READY" != "$EXTDNS_PODS_DESIRED" ]; then
        log_warning "external-dns not fully ready: $EXTDNS_PODS_READY/$EXTDNS_PODS_DESIRED"
        add_major_issue "external-dns pods not ready: $EXTDNS_PODS_READY/$EXTDNS_PODS_DESIRED"
        NETWORK_ISSUES=$((NETWORK_ISSUES + 1))
    fi
    if [ "$CLOUDFLARED_RUNNING" -eq 0 ]; then
        log_warning "Cloudflare tunnel not running"
        add_major_issue "Cloudflare tunnel pods not running - external access may be broken"
        NETWORK_ISSUES=$((NETWORK_ISSUES + 1))
    fi
    if [ "$INGRESS_ERRORS" -gt 10 ]; then
        log_warning "High ingress controller error rate: $INGRESS_ERRORS in last hour"
        add_minor_issue "Ingress controller errors: $INGRESS_ERRORS in last hour"
        NETWORK_ISSUES=$((NETWORK_ISSUES + 1))
    fi
    if ! { curl -s --connect-timeout 2 http://192.168.31.230/ -o /dev/null 2>/dev/null || nc -z -w 2 192.168.31.230 22 2>/dev/null; }; then
        log_warning "NAS (192.168.31.230) not reachable from cluster"
        add_major_issue "NAS not reachable - storage backup integration may be broken"
        NETWORK_ISSUES=$((NETWORK_ISSUES + 1))
    fi

    if [ "$NETWORK_ISSUES" -eq 0 ]; then
        log_success "Network connectivity healthy"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 20: GitOps Status"
{
    echo "Git sources:"
    flux get sources git -A
    echo ""

    # Check Git source status (READY column = False)
    FAILED_GIT=$(safe_count "flux get sources git -A 2>/dev/null | awk '\$5 == \"False\"' | wc -l")
    if [ "$FAILED_GIT" -gt 0 ]; then
        echo "Failed Git sources: $FAILED_GIT"
        flux get sources git -A | awk '$5 == "False"' | while read line; do
            echo "  - $line"
        done
        echo ""
    fi

    # Check OCI sources (used for Flux operator bootstrap charts)
    echo "OCI sources:"
    flux get sources oci -A 2>/dev/null || echo "No OCI sources found"
    FAILED_OCI=$(safe_count "flux get sources oci -A 2>/dev/null | awk '\$5 == \"False\"' | wc -l")
    if [ "$FAILED_OCI" -gt 0 ]; then
        log_warning "Failed OCI sources: $FAILED_OCI"
        add_major_issue "Failed Flux OCI sources: $FAILED_OCI (may block bootstrap chart deployments)"
    fi
    echo ""

    echo "Flux controllers status:"
    kubectl get pods -n flux-system
    echo ""

    # Check Flux controllers health
    FLUX_CONTROLLERS=$(safe_count "kubectl get pods -n flux-system --no-headers 2>/dev/null | wc -l")
    FLUX_RUNNING=$(safe_count "kubectl get pods -n flux-system --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l")
    echo "Flux controllers: $FLUX_RUNNING/$FLUX_CONTROLLERS running"
    echo ""

    echo "Kustomizations summary:"
    flux get kustomizations -A | head -30
    echo ""

    # Count kustomizations where READY column (col 5) is not True — resilient to mid-reconciliation message changes
    NOT_RECONCILED=$(safe_count "flux get kustomizations -A 2>/dev/null | grep -v 'NAMESPACE' | awk '\$5 != \"True\"' | wc -l")
    TOTAL_KUST=$(safe_count "flux get kustomizations -A 2>/dev/null | grep -v 'NAMESPACE' | wc -l")
    echo "Kustomization status: $((TOTAL_KUST - NOT_RECONCILED))/$TOTAL_KUST reconciled"

    # Check for specific GitOps issues
    if [ "$FAILED_GIT" -eq 0 ] && [ "$FAILED_OCI" -eq 0 ] && [ "$NOT_RECONCILED" -eq 0 ] && [ "$FLUX_RUNNING" -eq "$FLUX_CONTROLLERS" ]; then
        log_success "GitOps fully synchronized - All sources and kustomizations healthy"
    else
        if [ "$FLUX_RUNNING" -ne "$FLUX_CONTROLLERS" ]; then
            log_critical "Flux controllers not running: $FLUX_RUNNING/$FLUX_CONTROLLERS"
            add_critical_issue "Flux controllers down: $((FLUX_CONTROLLERS - FLUX_RUNNING)) controllers not running"
        fi

        if [ "$FAILED_GIT" -gt 0 ]; then
            log_warning "Git source failures: $FAILED_GIT"
            add_major_issue "Git source failures: $FAILED_GIT (check repository access and credentials)"
        fi

        if [ "$NOT_RECONCILED" -gt 0 ]; then
            log_warning "GitOps reconciliation issues: $NOT_RECONCILED kustomizations not reconciled"
            add_minor_issue "Kustomizations not reconciled: $NOT_RECONCILED (see Section 5 for details)"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

#######################################
# Phase 4: Advanced Monitoring
#######################################

log_section "Section 21: Namespace Review"
{
    TOTAL_NS=$(safe_count "kubectl get namespaces --no-headers | wc -l")
    echo "Total namespaces: $TOTAL_NS"

    TERMINATING_NS=$(safe_count "kubectl get namespaces 2>/dev/null | grep 'Terminating' | wc -l")
    echo "Terminating namespaces: $TERMINATING_NS"

    TERMINATING_PODS=$(safe_count "kubectl get pods -A 2>/dev/null | grep 'Terminating' | wc -l")
    echo "Terminating pods: $TERMINATING_PODS"

    if [ "$TERMINATING_NS" -eq 0 ] && [ "$TERMINATING_PODS" -eq 0 ]; then
        log_success "No stuck resources"
    else
        log_warning "Stuck resources - NS: $TERMINATING_NS, Pods: $TERMINATING_PODS"
        add_minor_issue "Stuck resources - NS: $TERMINATING_NS, Pods: $TERMINATING_PODS"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 22: Home Automation Health"
{
    echo "Home Assistant:"
    kubectl get pods -n home-automation -l app.kubernetes.io/name=home-assistant
    echo ""

    echo "Home Assistant detailed logs (last 100 lines):"
    HA_LOGS=$(kubectl logs -n home-automation deployment/home-assistant --since=24h 2>&1 || echo "Unable to get logs")
    echo "$HA_LOGS"
    echo ""

    # Categorize errors by severity (excludes known false positives via HA_FALSE_POSITIVES array)
    CRITICAL_HA_ERRORS=$(echo "$HA_LOGS" | grep -cE "FATAL|CRITICAL" || true)
    MAJOR_HA_ERRORS=$(echo "$HA_LOGS" | grep -E "ERROR" | grep -v "Failed to connect" | filter_ha_false_positives | wc -l || true)
    MINOR_HA_ERRORS=$(echo "$HA_LOGS" | grep -cE "WARNING|Failed to connect" || true)

    # Total errors (excluding known false positives)
    HA_ERRORS=$(echo "$HA_LOGS" | grep -E "(ERROR|error|Failed|failed)" | filter_ha_false_positives | wc -l || true)

    echo "Home Assistant error severity:"
    echo "  - Critical: $CRITICAL_HA_ERRORS"
    echo "  - Major: $MAJOR_HA_ERRORS"
    echo "  - Minor: $MINOR_HA_ERRORS"
    echo "  - Total (filtered): $HA_ERRORS"
    echo ""

    # Integration-specific errors
    DIRIGERA_ERRORS=$(echo "$HA_LOGS" | grep -c "dirigera" || true)
    TIBBER_ERRORS=$(echo "$HA_LOGS" | grep -c "tibber" || true)
    RESMED_ERRORS=$(echo "$HA_LOGS" | grep -c "resmed" || true)
    SHELLY_ERRORS=$(echo "$HA_LOGS" | grep -c "shelly" || true)
    TESLA_ERRORS=$(echo "$HA_LOGS" | grep -c "tesla" || true)
    FLIC_ERRORS=$(echo "$HA_LOGS" | grep -c "Flic Hub" || true)

    echo "Integration error breakdown:"
    echo "  - Dirigera hub: $DIRIGERA_ERRORS"
    echo "  - Tibber API: $TIBBER_ERRORS"
    echo "  - ResMed MyAir: $RESMED_ERRORS"
    echo "  - Shelly devices: $SHELLY_ERRORS"
    echo "  - Tesla: $TESLA_ERRORS"
    echo "  - Flic Hub (offline - expected): $FLIC_ERRORS"
    echo ""

    echo "Zigbee2MQTT:"
    kubectl get pods -n home-automation -l app.kubernetes.io/name=zigbee2mqtt
    echo ""

    # --- Zigbee coordinator connectivity (network-based, not USB) ---
    # Coordinator is a network device at tcp://192.168.32.20:6638 (IoT VLAN)
    echo "Zigbee coordinator (192.168.32.20:6638):"
    Z2M_POD=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=zigbee2mqtt -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$Z2M_POD" ]; then
        # Test coordinator TCP reachability from inside the pod (nc available in z2m container)
        COORD_REACHABLE=$(kubectl exec -n home-automation "$Z2M_POD" -- sh -c \
            'nc -z -w 2 192.168.32.20 6638 2>/dev/null && echo reachable || echo unreachable' 2>/dev/null \
            || echo "unknown (nc not available in pod)")
        echo "  TCP connectivity: $COORD_REACHABLE"
        if [ "$COORD_REACHABLE" = "unreachable" ]; then
            log_critical "Zigbee coordinator not reachable at 192.168.32.20:6638"
            add_critical_issue "Zigbee coordinator unreachable - all Zigbee devices offline"
        elif [ "$COORD_REACHABLE" = "reachable" ]; then
            log_success "Zigbee coordinator reachable"
        fi
    else
        echo "  Cannot check — Zigbee2MQTT pod not running"
    fi
    echo ""

    # --- Zigbee device offline detection via state.json ---
    echo "Zigbee device health (from state.json):"
    Z2M_DEVICE_STATS=$(kubectl exec -n home-automation "$Z2M_POD" -- sh -c 'cat /data/state.json 2>/dev/null' 2>/dev/null \
        | python3 - <<'PYEOF'
import sys, json, datetime
try:
    d = json.load(sys.stdin)
    now = datetime.datetime.now(datetime.timezone.utc)
    total = len(d)
    offline_5d, offline_1d = [], []
    for addr, v in d.items():
        ls = v.get('last_seen')
        if ls:
            try:
                t = datetime.datetime.fromisoformat(ls.rstrip('Z')).replace(tzinfo=datetime.timezone.utc)
                age_d = (now - t).total_seconds() / 86400
                if age_d > 5:
                    offline_5d.append((addr, round(age_d, 1)))
                elif age_d > 1:
                    offline_1d.append((addr, round(age_d, 1)))
            except: pass
    print(f"TOTAL={total}")
    print(f"OFFLINE_5D={len(offline_5d)}")
    print(f"OFFLINE_1D={len(offline_1d)}")
    for addr, days in sorted(offline_5d, key=lambda x: -x[1]):
        print(f"STALE:{addr}:{days}d")
except Exception as e:
    print(f"ERROR={e}")
PYEOF
    )
    Z2M_TOTAL=$(echo "$Z2M_DEVICE_STATS" | grep "^TOTAL=" | cut -d= -f2)
    Z2M_OFFLINE_5D=$(echo "$Z2M_DEVICE_STATS" | grep "^OFFLINE_5D=" | cut -d= -f2)
    Z2M_OFFLINE_1D=$(echo "$Z2M_DEVICE_STATS" | grep "^OFFLINE_1D=" | cut -d= -f2)
    echo "  Total devices: ${Z2M_TOTAL:-?}"
    echo "  Offline >5 days: ${Z2M_OFFLINE_5D:-?}"
    echo "  Offline 1-5 days: ${Z2M_OFFLINE_1D:-?}"
    if [ -n "$Z2M_OFFLINE_5D" ] && [ "$Z2M_OFFLINE_5D" -gt 0 ]; then
        echo "  Stale devices:"
        echo "$Z2M_DEVICE_STATS" | grep "^STALE:" | while IFS=: read _ addr days; do
            echo "    $addr ($days)"
        done
    fi
    echo ""

    # Baseline: 23 stale entries from decommissioned devices (as of 2026-04-17) — see docs/troubleshooting/ha-upstream-integration-issues.md
    # These are state.json records of physically removed/replaced devices, not live Zigbee failures.
    # Trip only if count exceeds baseline by a clear margin OR increases unexpectedly.
    Z2M_OFFLINE_BASELINE=23
    if [ -n "$Z2M_OFFLINE_5D" ] && [ "$Z2M_OFFLINE_5D" -gt $((Z2M_OFFLINE_BASELINE + 5)) ]; then
        log_warning "Zigbee devices offline >5 days above baseline: $Z2M_OFFLINE_5D (baseline: $Z2M_OFFLINE_BASELINE)"
        add_major_issue "Zigbee devices offline >5 days: $Z2M_OFFLINE_5D/${Z2M_TOTAL} (baseline $Z2M_OFFLINE_BASELINE)"
    elif [ -n "$Z2M_OFFLINE_5D" ] && [ "$Z2M_OFFLINE_5D" -gt 0 ]; then
        log_info "Zigbee stale state entries: $Z2M_OFFLINE_5D (baseline $Z2M_OFFLINE_BASELINE — decommissioned devices)"
    fi

    echo "Zigbee2MQTT logs (last 50 lines):"
    Z2M_LOGS=$(kubectl logs -n home-automation deployment/zigbee2mqtt --tail=50 2>&1 || echo "Unable to get logs")
    echo "$Z2M_LOGS"
    echo ""

    Z2M_ERRORS=$(echo "$Z2M_LOGS" | grep -cE "(error|ERROR|warn|WARN)" || true)
    echo "Zigbee2MQTT errors/warnings: $Z2M_ERRORS"
    echo ""

    echo "Mosquitto MQTT Broker:"
    kubectl get pods -n home-automation -l app.kubernetes.io/name=mosquitto
    echo ""

    echo "Mosquitto logs (last 50 lines):"
    MQTT_LOGS=$(kubectl logs -n home-automation deployment/mosquitto --tail=50 2>&1 || echo "Unable to get logs")
    echo "$MQTT_LOGS"
    echo ""

    MQTT_ERRORS=$(echo "$MQTT_LOGS" | grep -cE "(error|ERROR)" || true)
    echo "Mosquitto errors: $MQTT_ERRORS"

    # Assess Home Assistant health by severity
    if [ "$CRITICAL_HA_ERRORS" -gt 0 ]; then
        log_critical "Home Assistant critical errors: $CRITICAL_HA_ERRORS"
        add_critical_issue "Home Assistant critical errors: $CRITICAL_HA_ERRORS"
    elif [ "$MAJOR_HA_ERRORS" -gt 50 ]; then
        log_warning "High Home Assistant major error count: $MAJOR_HA_ERRORS"
        add_major_issue "High Home Assistant error count: $MAJOR_HA_ERRORS"
    elif [ "$MAJOR_HA_ERRORS" -gt 10 ]; then
        log_warning "Home Assistant errors: $MAJOR_HA_ERRORS (mostly external integrations)"
        add_minor_issue "Home Assistant integration errors: $MAJOR_HA_ERRORS"
    elif [ "$HA_ERRORS" -lt 10 ] && [ "$Z2M_ERRORS" -lt 5 ] && [ "$MQTT_ERRORS" -eq 0 ]; then
        log_success "Home automation healthy"
    else
        log_info "Home Assistant minor issues: $MINOR_HA_ERRORS (external services, expected offline devices)"
    fi

    if [ "$Z2M_ERRORS" -gt 10 ]; then
        add_minor_issue "Zigbee2MQTT errors/warnings: $Z2M_ERRORS"
    fi

    if [ "$MQTT_ERRORS" -gt 0 ]; then
        add_minor_issue "Mosquitto MQTT broker errors: $MQTT_ERRORS"
    fi

    # OTBR (OpenThread Border Router) — Thread/Matter network bridge
    echo ""
    echo "OTBR (OpenThread Border Router):"
    OTBR_POD=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=otbr -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$OTBR_POD" ]; then
        OTBR_RESTARTS=$(kubectl get pod -n home-automation "$OTBR_POD" -o jsonpath='{.status.containerStatuses[0].restartCount}' 2>/dev/null || echo "0")
        echo "  OTBR pod: $OTBR_POD, restarts: $OTBR_RESTARTS"
        if [ "$OTBR_RESTARTS" -gt 3 ]; then
            log_warning "OTBR pod has restarted $OTBR_RESTARTS times"
            add_minor_issue "OTBR (OpenThread Border Router) pod restarts: $OTBR_RESTARTS"
        else
            log_success "OTBR pod healthy (restarts: $OTBR_RESTARTS)"
        fi
    else
        echo "  OTBR pod not found"
    fi

    # ES enrichment: 7-day HA error trends by pod
    ES_HA=$(es_query '{
      "size": 0,
      "query": {"bool": {
        "should": [
          {"wildcard": {"body.text": "*ERROR*"}},
          {"wildcard": {"body.text": "*FATAL*"}}
        ],
        "minimum_should_match": 1,
        "filter": [
          {"range": {"@timestamp": {"gte": "now-7d"}}},
          {"term": {"resource.attributes.k8s.namespace.name": "home-automation"}}
        ]
      }},
      "aggs": {
        "by_pod": {"terms": {"field": "resource.attributes.k8s.pod.name", "size": 10}},
        "last_24h": {"filter": {"range": {"@timestamp": {"gte": "now-24h"}}}},
        "per_day": {"date_histogram": {"field": "@timestamp", "calendar_interval": "day"}}
      }
    }')
    if [ -n "$ES_HA" ]; then
        ES_HA_SUMMARY=$(echo "$ES_HA" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    total = d['hits']['total']['value']
    last24 = d['aggregations']['last_24h']['doc_count']
    days = d['aggregations']['per_day']['buckets']
    daily_avg = total / max(len(days), 1)
    trend = 'stable'
    if last24 > daily_avg * 1.5 and last24 > 50:
        trend = 'UP ↑'
    elif last24 < daily_avg * 0.5:
        trend = 'down ↓'
    pods = ', '.join(f\"{b['key'].split('-')[0]}:{b['doc_count']}\" for b in d['aggregations']['by_pod']['buckets'][:5])
    print(f'ES 7d trend: {total} total, {int(daily_avg)}/day avg, last 24h: {last24} ({trend})')
    if pods:
        print(f'  Top error sources: {pods}')
except: pass
" 2>/dev/null)
        if [ -n "$ES_HA_SUMMARY" ]; then
            echo ""
            echo "  $ES_HA_SUMMARY" | head -2
            while IFS= read -r line; do log_info "$line"; done <<< "$ES_HA_SUMMARY"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 22a: MQTT Connectivity & Shelly Devices"
{
    echo "=== MQTT Broker Statistics (Real-time) ==="
    # Use Mosquitto's $SYS topics for accurate connected client count
    MQTT_CONNECTED=$(kubectl exec -n home-automation deployment/mosquitto -c app -- timeout 5 mosquitto_sub -h localhost -t '$SYS/broker/clients/connected' -C 1 2>/dev/null || echo "0")
    MQTT_TOTAL=$(kubectl exec -n home-automation deployment/mosquitto -c app -- timeout 5 mosquitto_sub -h localhost -t '$SYS/broker/clients/total' -C 1 2>/dev/null || echo "0")
    MQTT_INACTIVE=$(kubectl exec -n home-automation deployment/mosquitto -c app -- timeout 5 mosquitto_sub -h localhost -t '$SYS/broker/clients/inactive' -C 1 2>/dev/null || echo "0")

    echo "Total clients: $MQTT_TOTAL"
    echo "Connected/Active: $MQTT_CONNECTED"
    echo "Inactive: $MQTT_INACTIVE"
    echo ""

    echo "=== Recent MQTT Clients (from logs) ==="
    # Fixed parsing: extract client ID properly (field after "as", before space)
    kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=20000 2>&1 | grep "New client connected" | grep -v "<unknown>" | sed 's/.* as //' | sed 's/ .*//' | sort -u | head -20
    echo ""

    echo "=== Shelly MQTT Connections ==="
    # Fixed: increase log window to 20000 and use correct parsing
    SHELLY_COUNT=$(safe_count "kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=20000 2>&1 | grep 'New client connected' | grep -v '<unknown>' | sed 's/.* as //' | sed 's/ .*//' | grep -i shelly | sort -u | wc -l")
    echo "Shelly devices identified (recent reconnections): $SHELLY_COUNT"
    echo ""
    echo "Note: MQTT clients maintain persistent connections. This count shows devices"
    echo "that reconnected recently. Stable devices won't appear in recent logs."
    echo ""

    echo "=== MQTT Authentication Issues ==="
    AUTH_FAILURES=$(safe_count "kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=100 2>&1 | grep -E '(not authorised|authentication|Connection refused)' | wc -l")
    echo "Authentication failures: $AUTH_FAILURES"
    echo ""

    echo "=== MQTT Connection Errors ==="
    MQTT_CONN_ERRORS=$(safe_count "kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=100 2>&1 | grep -i error | wc -l")
    echo "Connection errors: $MQTT_CONN_ERRORS"
    echo ""

    echo "=== MQTT Service Status ==="
    kubectl get svc -n home-automation mosquitto-internal -o wide 2>/dev/null || echo "Service not found"
    kubectl get endpoints -n home-automation mosquitto-internal 2>/dev/null || echo "Endpoints not found"
    echo ""

    # Health assessment - use real-time connected count instead of log-based count
    EXPECTED_CLIENTS_MIN=40
    EXPECTED_CLIENTS_MAX=60

    if [ "$AUTH_FAILURES" -gt 5 ]; then
        log_critical "High MQTT authentication failures: $AUTH_FAILURES"
        add_critical_issue "MQTT authentication failures: $AUTH_FAILURES"
    elif [ "$AUTH_FAILURES" -gt 0 ]; then
        log_warning "MQTT authentication failures detected: $AUTH_FAILURES"
        add_minor_issue "MQTT authentication failures: $AUTH_FAILURES"
    fi

    # Check total connected clients instead of just Shelly devices
    if [ "$MQTT_CONNECTED" -lt 20 ]; then
        log_critical "Low MQTT client count: $MQTT_CONNECTED (expected: $EXPECTED_CLIENTS_MIN-$EXPECTED_CLIENTS_MAX)"
        add_critical_issue "Only $MQTT_CONNECTED MQTT clients connected (expected $EXPECTED_CLIENTS_MIN-$EXPECTED_CLIENTS_MAX)"
    elif [ "$MQTT_CONNECTED" -lt 40 ]; then
        log_warning "Below expected MQTT client count: $MQTT_CONNECTED (expected: $EXPECTED_CLIENTS_MIN-$EXPECTED_CLIENTS_MAX)"
        add_minor_issue "MQTT client count below expected: $MQTT_CONNECTED (expected $EXPECTED_CLIENTS_MIN-$EXPECTED_CLIENTS_MAX)"
    else
        log_success "MQTT clients connected: $MQTT_CONNECTED (expected: $EXPECTED_CLIENTS_MIN-$EXPECTED_CLIENTS_MAX)"
    fi

    # Informational check for Shelly devices (not critical since it's based on logs)
    if [ "$SHELLY_COUNT" -lt 10 ]; then
        log_info "Few Shelly devices in recent logs: $SHELLY_COUNT (may indicate stable connections)"
    else
        log_info "Shelly devices in recent logs: $SHELLY_COUNT"
    fi

    if [ "$MQTT_CONN_ERRORS" -gt 10 ]; then
        log_warning "High MQTT connection errors: $MQTT_CONN_ERRORS"
        add_minor_issue "MQTT connection errors: $MQTT_CONN_ERRORS"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 22b: Frigate NVR & Camera Health"
{
    echo "=== Frigate Pod Status ==="
    kubectl get pods -n home-automation -l app.kubernetes.io/name=frigate
    echo ""

    FRIGATE_RUNNING=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=frigate -o json 2>/dev/null | jq '[.items[] | select(.status.phase=="Running")] | length' || echo "0")

    if [ "$FRIGATE_RUNNING" -eq 0 ]; then
        log_critical "Frigate NVR is not running"
        add_critical_issue "Frigate NVR pod not running - all cameras offline"
    else
        log_success "Frigate NVR pod running"

        # Check camera streaming status via Frigate API
        echo "=== Camera Streaming Status (Frigate API) ==="
        kubectl port-forward -n home-automation svc/frigate 5000:5000 > /dev/null 2>&1 &
        PF_PID=$!
        sleep 3

        CAMERA_STATS=$(curl -s http://localhost:5000/api/stats 2>/dev/null || echo "{}")

        CAMERA_RESULTS=$(echo "$CAMERA_STATS" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    cameras = data.get('cameras', {})
    total = len(cameras)
    streaming = 0
    detecting = 0
    down_cameras = []
    for cam, info in cameras.items():
        fps = info.get('camera_fps', 0)
        det_fps = info.get('detection_fps', 0)
        status = 'OK' if fps > 0 else 'DOWN'
        if fps > 0:
            streaming += 1
        else:
            down_cameras.append(cam)
        print(f'  {cam}: fps={fps}, detection_fps={det_fps} [{status}]')
    print(f'SUMMARY:{streaming}/{total}')
    if down_cameras:
        print(f'DOWN:{\"|\".join(down_cameras)}')
except Exception as e:
    print(f'Error: {e}')
    print('SUMMARY:0/0')
" 2>/dev/null || echo "SUMMARY:0/0")

        echo "$CAMERA_RESULTS" | grep -v "^SUMMARY:" | grep -v "^DOWN:"
        echo ""

        STREAMING_COUNT=$(echo "$CAMERA_RESULTS" | grep "^SUMMARY:" | sed 's/SUMMARY://' | cut -d'/' -f1)
        TOTAL_CAMERAS=$(echo "$CAMERA_RESULTS" | grep "^SUMMARY:" | sed 's/SUMMARY://' | cut -d'/' -f2)
        DOWN_CAMERAS=$(echo "$CAMERA_RESULTS" | grep "^DOWN:" | sed 's/DOWN://' | tr '|' ', ')

        [ -z "$STREAMING_COUNT" ] && STREAMING_COUNT=0
        [ -z "$TOTAL_CAMERAS" ] && TOTAL_CAMERAS=0

        # Cameras under hardware maintenance (won't be counted as failures)
        # See docs/troubleshooting/ha-upstream-integration-issues.md for rationale
        CAMERA_MAINTENANCE="guest_room"  # Hardware maintenance through 2026-04-30

        # Filter out maintenance cameras from the DOWN list
        DOWN_CAMERAS_REAL=""
        CAMERAS_DOWN_REAL=0
        if [ -n "$DOWN_CAMERAS" ]; then
            for cam in $(echo "$DOWN_CAMERAS" | tr ',' ' '); do
                cam=$(echo "$cam" | xargs)
                if echo "$CAMERA_MAINTENANCE" | grep -qw "$cam"; then
                    log_info "Camera under maintenance (skipped): $cam"
                else
                    DOWN_CAMERAS_REAL="${DOWN_CAMERAS_REAL:+$DOWN_CAMERAS_REAL, }$cam"
                    CAMERAS_DOWN_REAL=$((CAMERAS_DOWN_REAL + 1))
                fi
            done
        fi

        echo "Cameras streaming: $STREAMING_COUNT/$TOTAL_CAMERAS"

        if [ "$CAMERAS_DOWN_REAL" -eq 0 ] && [ "$TOTAL_CAMERAS" -gt 0 ]; then
            log_success "All expected cameras streaming ($STREAMING_COUNT/$TOTAL_CAMERAS — maintenance excluded)"
        elif [ "$STREAMING_COUNT" -gt 0 ]; then
            log_warning "Cameras down: $CAMERAS_DOWN_REAL/$TOTAL_CAMERAS ($DOWN_CAMERAS_REAL)"
            add_major_issue "Frigate cameras not streaming: $DOWN_CAMERAS_REAL ($CAMERAS_DOWN_REAL of $TOTAL_CAMERAS)"
        elif [ "$TOTAL_CAMERAS" -gt 0 ]; then
            log_critical "All $TOTAL_CAMERAS cameras are down"
            add_critical_issue "All Frigate cameras are down (0/$TOTAL_CAMERAS streaming)"
        fi

        kill $PF_PID 2>/dev/null || true
        wait $PF_PID 2>/dev/null || true

        # Check Frigate MQTT availability (critical for HA integration)
        echo ""
        echo "=== Frigate MQTT Availability ==="
        FRIGATE_AVAILABLE=$(kubectl exec -n home-automation deployment/mosquitto -c app -- timeout 5 mosquitto_sub -t 'frigate/available' -C 1 2>/dev/null || echo "unknown")
        echo "frigate/available: $FRIGATE_AVAILABLE"

        if [ "$FRIGATE_AVAILABLE" == "online" ]; then
            log_success "Frigate MQTT availability: online"
        elif [ "$FRIGATE_AVAILABLE" == "offline" ]; then
            log_critical "Frigate MQTT reports offline - ALL cameras unavailable in Home Assistant"
            add_critical_issue "Frigate MQTT availability is 'offline' (stale retained message) - all HA cameras show unavailable. Fix: mosquitto_pub -t 'frigate/available' -m 'online' -r"
        else
            log_warning "Frigate MQTT availability: $FRIGATE_AVAILABLE"
            add_major_issue "Frigate MQTT availability unknown: $FRIGATE_AVAILABLE"
        fi

        # Check for camera crash loops in logs (skip cameras under maintenance)
        echo ""
        echo "=== Camera Crash Loops (recent logs) ==="
        CRASH_CAMERAS=$(kubectl logs -n home-automation -l app.kubernetes.io/name=frigate --tail=500 2>&1 | grep "crashed unexpectedly" | sed 's/.*for //' | sed 's/\..*//' | sort | uniq -c | sort -rn)
        if [ -n "$CRASH_CAMERAS" ]; then
            echo "$CRASH_CAMERAS"
            # Filter out maintenance cameras
            CRASH_NAMES=$(echo "$CRASH_CAMERAS" | awk '{print $2}')
            CRASH_REAL=""
            for cam in $CRASH_NAMES; do
                if echo "$CAMERA_MAINTENANCE" | grep -qw "$cam"; then
                    log_info "Camera crash loop (maintenance, skipped): $cam"
                else
                    CRASH_REAL="${CRASH_REAL:+$CRASH_REAL,}$cam"
                fi
            done
            if [ -n "$CRASH_REAL" ]; then
                add_minor_issue "Frigate camera crash loops detected: $CRASH_REAL"
            fi
        else
            echo "  No crash loops detected"
        fi

        # Check RTSP connection timeouts
        echo ""
        echo "=== RTSP Connection Timeouts ==="
        RTSP_TIMEOUTS=$(kubectl logs -n home-automation -l app.kubernetes.io/name=frigate --tail=500 2>&1 | grep "Connection to tcp://" | sed 's/.*Connection to tcp:\/\///' | sed 's/?.*//' | sort | uniq -c | sort -rn)
        if [ -n "$RTSP_TIMEOUTS" ]; then
            echo "$RTSP_TIMEOUTS"
        else
            echo "  No RTSP timeouts"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 23: Media Services Health"
{
    echo "Jellyfin status:"
    kubectl get pods -n media -l app.kubernetes.io/name=jellyfin
    echo ""
    JELLYFIN_RUNNING=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o json 2>/dev/null | jq '[.items[] | select(.status.phase=="Running")] | length' || echo "0")

    echo "Plex status:"
    kubectl get pods -n media -l app.kubernetes.io/name=plex 2>/dev/null || echo "Plex not found"
    echo ""
    PLEX_RUNNING=$(kubectl get pods -n media -l app.kubernetes.io/name=plex -o json 2>/dev/null | jq '[.items[] | select(.status.phase=="Running")] | length' || echo "0")

    echo "Tube Archivist:"
    kubectl get pods -n download -l app.kubernetes.io/name=tube-archivist 2>/dev/null || echo "Tube Archivist not found"
    echo ""
    TA_ERRORS=$(safe_count "kubectl logs -n download deployment/tube-archivist --tail=20 --since=1h 2>&1 | grep -iE '\[ERROR\]|error:' | wc -l")
    echo "Tube Archivist errors (last hour): $TA_ERRORS"

    echo "JDownloader:"
    kubectl get pods -n download -l app.kubernetes.io/name=jdownloader 2>/dev/null || echo "JDownloader not found"
    echo ""

    MEDIA_ISSUES=0
    if [ "$JELLYFIN_RUNNING" -eq 0 ]; then
        log_warning "Jellyfin not running"
        add_major_issue "Jellyfin pod not running"
        MEDIA_ISSUES=$((MEDIA_ISSUES + 1))
    fi
    if [ "$TA_ERRORS" -gt 10 ]; then
        log_warning "Tube Archivist has errors: $TA_ERRORS in last hour"
        add_minor_issue "Tube Archivist errors: $TA_ERRORS"
        MEDIA_ISSUES=$((MEDIA_ISSUES + 1))
    fi

    if [ "$MEDIA_ISSUES" -eq 0 ]; then
        log_success "Media services healthy"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 23a: Office Services Health"
{
    OFFICE_ISSUES=0

    # Vaultwarden — password manager, externally exposed and business-critical
    echo "Vaultwarden:"
    kubectl get pods -n office -l app.kubernetes.io/name=vaultwarden 2>/dev/null || echo "Vaultwarden not found"
    VAULT_RUNNING=$(kubectl get pods -n office -l app.kubernetes.io/name=vaultwarden -o json 2>/dev/null | jq '[.items[] | select(.status.phase=="Running")] | length' || echo "0")
    echo "Vaultwarden running: $VAULT_RUNNING"
    if [ "$VAULT_RUNNING" -eq 0 ]; then
        log_critical "Vaultwarden is not running - password manager unavailable"
        add_critical_issue "Vaultwarden pod not running - users cannot access passwords"
        OFFICE_ISSUES=$((OFFICE_ISSUES + 1))
    fi
    echo ""

    # Nextcloud — self-hosted cloud storage, externally exposed
    echo "Nextcloud:"
    kubectl get pods -n office -l app.kubernetes.io/name=nextcloud 2>/dev/null || echo "Nextcloud not found"
    NEXTCLOUD_RUNNING=$(kubectl get pods -n office -l app.kubernetes.io/name=nextcloud -o json 2>/dev/null | jq '[.items[] | select(.status.phase=="Running")] | length' || echo "0")
    echo "Nextcloud running: $NEXTCLOUD_RUNNING"
    if [ "$NEXTCLOUD_RUNNING" -eq 0 ]; then
        log_warning "Nextcloud is not running"
        add_major_issue "Nextcloud pod not running - cloud storage and collaboration unavailable"
        OFFICE_ISSUES=$((OFFICE_ISSUES + 1))
    fi
    echo ""

    # Paperless-ngx — document management (data loss risk if down during OCR)
    echo "Paperless-ngx:"
    PAPERLESS_RUNNING=$(kubectl get pods -n office -l app.kubernetes.io/name=paperless-ngx -o json 2>/dev/null | jq '[.items[] | select(.status.phase=="Running")] | length' || echo "0")
    echo "Paperless-ngx running: $PAPERLESS_RUNNING"
    if [ "$PAPERLESS_RUNNING" -eq 0 ]; then
        log_warning "Paperless-ngx is not running"
        add_minor_issue "Paperless-ngx pod not running"
        OFFICE_ISSUES=$((OFFICE_ISSUES + 1))
    fi
    echo ""

    if [ "$OFFICE_ISSUES" -eq 0 ]; then
        log_success "Office services healthy"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 24: Database Health"
{
    echo "PostgreSQL:"
    kubectl get pods -n databases -l app=postgresql 2>/dev/null || echo "PostgreSQL not found"
    echo ""
    PG_RUNNING=$(kubectl get pods -n databases -l app=postgresql -o json 2>/dev/null | jq '[.items[] | select(.status.phase=="Running")] | length' || echo "0")
    PG_LOCKS="0"

    # Check PostgreSQL active connections
    if [ "$PG_RUNNING" -gt 0 ]; then
        PG_CONNECTIONS=$(kubectl exec -n databases -l app=postgresql -- psql -U postgres -t -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';" 2>/dev/null | tr -d ' ' || echo "unavailable")
        echo "PostgreSQL active connections: $PG_CONNECTIONS"

        # Check for databases with bloat or lock contention (quick check)
        PG_LOCKS=$(kubectl exec -n databases -l app=postgresql -- psql -U postgres -t -c "SELECT count(*) FROM pg_locks WHERE NOT granted;" 2>/dev/null | tr -d ' ' || echo "0")
        echo "PostgreSQL waiting locks: $PG_LOCKS"
    fi
    echo ""

    echo "MariaDB:"
    kubectl get statefulsets -n databases mariadb 2>/dev/null || echo "MariaDB not found"
    echo ""
    MARIADB_READY=$(kubectl get statefulset -n databases mariadb -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    MARIADB_DESIRED=$(kubectl get statefulset -n databases mariadb -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "1")
    echo "MariaDB pods: $MARIADB_READY/$MARIADB_DESIRED ready"

    DB_ISSUES=0
    if [ "$PG_RUNNING" -eq 0 ]; then
        log_critical "PostgreSQL not running"
        add_critical_issue "PostgreSQL pod not running - all dependent services may be affected"
        DB_ISSUES=$((DB_ISSUES + 1))
    fi
    if [ -n "$PG_LOCKS" ] && [ "$PG_LOCKS" != "unavailable" ] && [ "$PG_LOCKS" -gt 10 ] 2>/dev/null; then
        log_warning "PostgreSQL has $PG_LOCKS waiting lock(s)"
        add_minor_issue "PostgreSQL lock contention: $PG_LOCKS waiting locks"
        DB_ISSUES=$((DB_ISSUES + 1))
    fi
    if [ "$MARIADB_READY" != "$MARIADB_DESIRED" ]; then
        log_warning "MariaDB not fully ready: $MARIADB_READY/$MARIADB_DESIRED"
        add_major_issue "MariaDB pods not ready: $MARIADB_READY/$MARIADB_DESIRED"
        DB_ISSUES=$((DB_ISSUES + 1))
    fi

    if [ "$DB_ISSUES" -eq 0 ]; then
        log_success "Databases healthy"
    fi

    # Redis health (shared cache used by multiple apps including langfuse)
    # Deployed as a Deployment (not StatefulSet) named "redis" in databases namespace
    echo ""
    echo "Redis:"
    kubectl get deployments -n databases redis 2>/dev/null || echo "Redis not found"
    REDIS_READY=$(kubectl get deployment -n databases redis -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    REDIS_DESIRED=$(kubectl get deployment -n databases redis -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "1")
    echo "Redis pods: $REDIS_READY/$REDIS_DESIRED ready"
    if [ "$REDIS_READY" != "$REDIS_DESIRED" ]; then
        log_warning "Redis not fully ready: $REDIS_READY/$REDIS_DESIRED"
        add_major_issue "Redis pods not ready: $REDIS_READY/$REDIS_DESIRED (affects langfuse and other cache-dependent apps)"
        DB_ISSUES=$((DB_ISSUES + 1))
    fi

    # InfluxDB health (used by home automation dashboards and UnPoller metrics)
    # Deployed as StatefulSet named "influxdb-influxdb2" in databases namespace
    echo ""
    echo "InfluxDB:"
    kubectl get statefulsets -n databases influxdb-influxdb2 2>/dev/null || echo "InfluxDB not found"
    INFLUXDB_READY=$(kubectl get statefulset -n databases influxdb-influxdb2 -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    INFLUXDB_DESIRED=$(kubectl get statefulset -n databases influxdb-influxdb2 -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "1")
    echo "InfluxDB pods: ${INFLUXDB_READY:-0}/${INFLUXDB_DESIRED:-1} ready"
    if [ "${INFLUXDB_READY:-0}" != "${INFLUXDB_DESIRED:-1}" ] && [ "${INFLUXDB_DESIRED:-1}" -gt 0 ] 2>/dev/null; then
        log_warning "InfluxDB not fully ready: ${INFLUXDB_READY:-0}/${INFLUXDB_DESIRED:-1}"
        add_major_issue "InfluxDB pods not ready: ${INFLUXDB_READY:-0}/${INFLUXDB_DESIRED:-1} (affects UnPoller metrics and home automation dashboards)"
        DB_ISSUES=$((DB_ISSUES + 1))
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 24a: Network Infrastructure Services"
{
    INFRA_SVC_ISSUES=0

    # AdGuard Home — cluster DNS + ad-blocking at 192.168.55.5
    # If down, DNS resolution for IoT and internal LAN clients breaks.
    echo "AdGuard Home:"
    kubectl get pods -n network -l app.kubernetes.io/name=adguard-home 2>/dev/null || echo "AdGuard Home not found"
    ADGUARD_RUNNING=$(kubectl get pods -n network -l app.kubernetes.io/name=adguard-home -o json 2>/dev/null | jq '[.items[] | select(.status.phase=="Running")] | length' || echo "0")
    echo "AdGuard pods running: $ADGUARD_RUNNING"
    if [ "$ADGUARD_RUNNING" -eq 0 ]; then
        log_critical "AdGuard Home is not running - internal DNS and ad-blocking unavailable"
        add_critical_issue "AdGuard Home pod not running (cluster DNS for IoT/LAN clients at 192.168.55.5 is down)"
        INFRA_SVC_ISSUES=$((INFRA_SVC_ISSUES + 1))
    else
        # Functional DNS check: exec into AdGuard pod and verify HTTP service responds
        # (API requires auth so we check for any HTTP response — 302/401 means AdGuard is running)
        ADGUARD_POD=$(kubectl get pods -n network -l app.kubernetes.io/name=adguard-home -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        if [ -n "$ADGUARD_POD" ]; then
            ADGUARD_HTTP=$(kubectl exec -n network "$ADGUARD_POD" -- wget -O/dev/null --server-response http://127.0.0.1:80/ 2>&1 | grep "HTTP/" | head -1 | awk '{print $2}' || echo "000")
            echo "AdGuard HTTP response code: $ADGUARD_HTTP"
            if [ "$ADGUARD_HTTP" = "000" ] || [ -z "$ADGUARD_HTTP" ]; then
                log_warning "AdGuard Home HTTP service not responding inside pod"
                add_major_issue "AdGuard Home DNS resolution failing at 192.168.55.5 (no HTTP response from pod)"
                INFRA_SVC_ISSUES=$((INFRA_SVC_ISSUES + 1))
            else
                log_success "AdGuard Home DNS functional (HTTP response: $ADGUARD_HTTP)"
            fi
        fi
    fi
    echo ""

    # Ollama Mac Mini AI inference backend at 192.168.30.111
    # All AI apps (open-webui, langfuse, openclaw) depend on this host.
    # Use curl to Ollama API — more accurate than ping (checks actual service availability)
    echo "Ollama AI backend (Mac Mini at 192.168.30.111):"
    if curl -s --connect-timeout 2 http://192.168.30.111:11434/api/version -o /dev/null 2>/dev/null; then
        echo "Ollama host reachable"
        log_success "Ollama AI backend (192.168.30.111) reachable"
    else
        echo "Ollama host unreachable"
        log_warning "Ollama AI backend (192.168.30.111) not reachable - AI features (open-webui, langfuse) may be broken"
        add_major_issue "Ollama host 192.168.30.111 not reachable from cluster - AI inference unavailable"
        INFRA_SVC_ISSUES=$((INFRA_SVC_ISSUES + 1))
    fi

    # Ollama (single instance, gemma 4 — no separate reason/vision ports needed)
    if curl -s --connect-timeout 2 http://192.168.30.111:11434/api/version -o /dev/null 2>/dev/null; then
        echo "Ollama (port 11434) reachable"
        log_success "Ollama (192.168.30.111:11434) reachable"
    else
        echo "Ollama (port 11434) unreachable"
        log_warning "Ollama (192.168.30.111:11434) not reachable"
        add_major_issue "Ollama port 11434 not reachable at 192.168.30.111"
        INFRA_SVC_ISSUES=$((INFRA_SVC_ISSUES + 1))
    fi
    echo ""

    # k8s-gateway — internal DNS for *.internal.${SECRET_DOMAIN} (cluster-local DNS)
    echo "k8s-gateway:"
    kubectl get pods -n network -l app.kubernetes.io/name=k8s-gateway 2>/dev/null || echo "k8s-gateway not found"
    K8SGW_ENDPOINTS=$(kubectl get endpoints -n network k8s-gateway -o jsonpath='{.subsets[0].addresses[0].ip}' 2>/dev/null || echo "")
    if [ -n "$K8SGW_ENDPOINTS" ]; then
        echo "k8s-gateway endpoints: $K8SGW_ENDPOINTS"
        log_success "k8s-gateway has active endpoints ($K8SGW_ENDPOINTS)"
    else
        echo "k8s-gateway: no endpoints found"
        log_warning "k8s-gateway has no active endpoints - internal DNS resolution may be broken"
        add_major_issue "k8s-gateway service has no endpoints (internal DNS for cluster services unavailable)"
        INFRA_SVC_ISSUES=$((INFRA_SVC_ISSUES + 1))
    fi
    echo ""

    if [ "$INFRA_SVC_ISSUES" -eq 0 ]; then
        log_success "Network infrastructure services healthy"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 25: External Services & Connectivity"
{
    # Cloudflare tunnel status (covered in Section 19, summarize here)
    echo "Cloudflare tunnel pods:"
    kubectl get pods -n network -l app=cloudflared 2>/dev/null || echo "Cloudflare tunnel not found"
    echo ""

    # Check Authentik readiness (auth gateway for all external services)
    echo "Authentik server:"
    kubectl get pods -n kube-system -l app.kubernetes.io/name=authentik 2>/dev/null || echo "Authentik not found"
    echo ""
    AUTHENTIK_RUNNING=$(kubectl get pods -n kube-system -l app.kubernetes.io/name=authentik,app.kubernetes.io/component=server -o json 2>/dev/null | jq '[.items[] | select(.status.phase=="Running")] | length' || echo "0")
    echo "Authentik server running pods: $AUTHENTIK_RUNNING"

    # Check SOPS age key secret exists (required for Flux to decrypt secrets)
    echo ""
    echo "SOPS age key secret:"
    kubectl get secret sops-age -n flux-system 2>/dev/null && echo "sops-age secret present" || echo "WARNING: sops-age secret missing - Flux cannot decrypt secrets"
    SOPS_SECRET=$(kubectl get secret sops-age -n flux-system 2>/dev/null && echo "present" || echo "missing")

    EXT_ISSUES=0
    if [ "$AUTHENTIK_RUNNING" -eq 0 ]; then
        log_critical "Authentik server not running - all external auth will fail"
        add_critical_issue "Authentik server pod not running"
        EXT_ISSUES=$((EXT_ISSUES + 1))
    fi
    if [ "$SOPS_SECRET" = "missing" ]; then
        log_critical "SOPS age key secret missing in flux-system - Flux cannot decrypt secrets"
        add_critical_issue "sops-age secret missing from flux-system namespace"
        EXT_ISSUES=$((EXT_ISSUES + 1))
    fi

    if [ "$EXT_ISSUES" -eq 0 ]; then
        log_success "External services connectivity healthy"
    fi

    # Production app health checks (my-software-production namespace)
    echo ""
    echo "=== Production App Health ==="
    PROD_INGRESSES=$(kubectl get ingress -n my-software-production -o json 2>/dev/null | python3 -c "
import sys, json
try:
    ing = json.load(sys.stdin)['items']
    for i in ing:
        name = i['metadata']['name']
        for rule in i.get('spec', {}).get('rules', []):
            host = rule.get('host', '')
            if host:
                print(f'{name}:{host}')
except:
    pass
" 2>/dev/null || echo "")
    PROD_ISSUES=0
    if [ -z "$PROD_INGRESSES" ]; then
        echo "  No ingresses found in my-software-production namespace"
    else
        for entry in $PROD_INGRESSES; do
            APP_NAME="${entry%%:*}"
            HOST="${entry##*:}"
            echo "Checking $APP_NAME ($HOST):"
            # External check (full stack via Cloudflare)
            EXT_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 "https://$HOST" 2>/dev/null || echo "000")
            echo "  External (https://$HOST): HTTP $EXT_CODE"
            if [[ "$EXT_CODE" == "000" ]] || [[ "$EXT_CODE" == "5"* ]]; then
                log_warning "$APP_NAME external endpoint failing: HTTP $EXT_CODE"
                add_major_issue "Production app $APP_NAME unreachable externally (https://$HOST): HTTP $EXT_CODE"
                PROD_ISSUES=$((PROD_ISSUES + 1))
            fi
            # Internal check (bypasses Cloudflare, tests ingress → pod)
            INT_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 --max-time 5 \
                -H "Host: $HOST" "http://192.168.55.102" 2>/dev/null || echo "000")
            echo "  Internal ingress (192.168.55.102, Host: $HOST): HTTP $INT_CODE"
            if [[ "$INT_CODE" == "000" ]] || [[ "$INT_CODE" == "5"* ]]; then
                log_warning "$APP_NAME internal ingress failing: HTTP $INT_CODE"
                add_major_issue "Production app $APP_NAME internal ingress failing (Host: $HOST): HTTP $INT_CODE"
                PROD_ISSUES=$((PROD_ISSUES + 1))
            fi
        done
        if [ "$PROD_ISSUES" -eq 0 ]; then
            log_success "Production apps healthy"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 26: Security & Access Monitoring"
{
    echo "Authentik server:"
    kubectl get pods -n kube-system -l app.kubernetes.io/name=authentik
    echo ""

    # Check Authentik auth failure rate
    AUTH_FAILURES=$(safe_count "kubectl logs -n kube-system -l app.kubernetes.io/name=authentik,app.kubernetes.io/component=server --tail=200 --since=24h 2>&1 | grep -iE 'authentication.*failed|login.*failed|invalid.*credentials' | wc -l")
    echo "Authentik auth failures (last 24h): $AUTH_FAILURES"
    echo ""

    # Check for RBAC permission errors in audit/controller logs
    RBAC_ERRORS=$(safe_count "kubectl logs -n kube-system -l component=kube-apiserver --tail=100 --since=1h 2>&1 | grep -i 'RBAC.*denied\|forbidden.*reason' | wc -l")
    echo "RBAC denied events (last hour, apiserver): $RBAC_ERRORS"

    if [ "$AUTH_FAILURES" -gt 20 ]; then
        log_warning "High authentication failure count: $AUTH_FAILURES in 24h (possible brute-force or misconfiguration)"
        add_minor_issue "High Authentik auth failure count: $AUTH_FAILURES"
    else
        log_success "Security monitoring check completed"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 27: Performance & Trends"
{
    echo "Current performance snapshot:"
    kubectl top nodes 2>/dev/null || echo "Metrics not available"

    log_success "Performance check completed"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 28: Backup & Recovery Verification"
{
    BACKUP_JOBS=$(safe_count "kubectl get jobs -n storage --sort-by=.metadata.creationTimestamp 2>/dev/null | tail -5 | grep '1/1' | wc -l")
    echo "Recent successful backups (last 5): $BACKUP_JOBS"

    if [ "$BACKUP_JOBS" -ge 1 ]; then
        log_success "Backup verification passed"
    else
        log_warning "Backup verification issues (recent successes: $BACKUP_JOBS)"
        add_major_issue "No recent successful backups found"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 29: Environmental & Power Monitoring"
{
    echo "System load:"
    kubectl top nodes 2>/dev/null | awk 'NR>1 {print $1 ": CPU=" $3 ", Memory=" $5}' || echo "Metrics not available"

    log_success "Environmental monitoring completed"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 30: Application-Specific Checks"
{
    echo "Authentik:"
    AUTH_PODS=$(safe_count "kubectl get pods -n kube-system -l app.kubernetes.io/name=authentik | grep 'Running' | wc -l")
    echo "Running pods: $AUTH_PODS"
    echo ""

    echo "Grafana:"
    GRAF_PODS=$(safe_count "kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana | grep 'Running' | wc -l")
    echo "Running pods: $GRAF_PODS"
    echo ""

    echo "Longhorn:"
    LH_PODS=$(safe_count "kubectl get pods -n storage -l app.kubernetes.io/name=longhorn-manager | grep 'Running' | wc -l")
    echo "Running manager pods: $LH_PODS"

    log_success "Application-specific checks completed"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 31: Home Assistant Integration Health"
{
    echo "Already covered in Section 22"
    log_info "See Section 22 for detailed Home Assistant integration analysis"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 32: Zigbee2MQTT Device Monitoring"
{
    echo "Zigbee2MQTT status:"
    kubectl get pods -n home-automation -l app.kubernetes.io/name=zigbee2mqtt
    echo ""

    Z2M_RUNNING=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=zigbee2mqtt -o json 2>/dev/null | jq '[.items[] | select(.status.phase=="Running")] | length' || echo "0")

    if [ "$Z2M_RUNNING" -eq 0 ]; then
        log_critical "Zigbee2MQTT is not running"
        add_critical_issue "Zigbee2MQTT pod not running - Zigbee devices unavailable"
    else
        Z2M_POD32=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=zigbee2mqtt \
            -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

        # --- Coordinator connectivity (network device at tcp://192.168.32.20:6638) ---
        echo "Zigbee coordinator (192.168.32.20:6638):"
        if [ -n "$Z2M_POD32" ]; then
            COORD32=$(kubectl exec -n home-automation "$Z2M_POD32" -- sh -c \
                'nc -z -w 2 192.168.32.20 6638 2>/dev/null && echo reachable || echo unreachable' 2>/dev/null \
                || echo "unknown")
            echo "  TCP connectivity: $COORD32"
            if [ "$COORD32" = "unreachable" ]; then
                log_critical "Zigbee coordinator not reachable at 192.168.32.20:6638"
                add_critical_issue "Zigbee coordinator unreachable - all Zigbee devices offline"
            fi
        fi
        echo ""

        # --- Device count and offline detection (via Python for reliable ISO8601 parsing) ---
        echo "Checking device count..."
        Z2M_STATS=$(kubectl exec -n home-automation "$Z2M_POD32" -- sh -c \
            'cat /data/state.json 2>/dev/null' 2>/dev/null \
            | python3 -c "
import sys, json, datetime
try:
    d = json.load(sys.stdin)
    now = datetime.datetime.now(datetime.timezone.utc)
    total = len(d)
    offline_5d = []
    for addr, v in d.items():
        ls = v.get('last_seen')
        if ls:
            try:
                t = datetime.datetime.fromisoformat(ls.rstrip('Z')).replace(tzinfo=datetime.timezone.utc)
                if (now - t).total_seconds() > 86400 * 5:
                    offline_5d.append((addr, round((now - t).total_seconds() / 86400, 1)))
            except: pass
    print(f'TOTAL={total}')
    print(f'OFFLINE_5D={len(offline_5d)}')
    for a, d in sorted(offline_5d, key=lambda x: -x[1]):
        print(f'STALE:{a}:{d}d')
except Exception as e:
    print(f'ERROR={e}')
" 2>/dev/null)
        Z2M_TOTAL32=$(echo "$Z2M_STATS" | grep "^TOTAL=" | cut -d= -f2)
        Z2M_OFFLINE32=$(echo "$Z2M_STATS" | grep "^OFFLINE_5D=" | cut -d= -f2)
        echo "Total Zigbee devices: ${Z2M_TOTAL32:-?}"
        echo ""

        echo "Devices offline >5 days:"
        if [ -n "$Z2M_OFFLINE32" ] && [ "$Z2M_OFFLINE32" -gt 0 ] 2>/dev/null; then
            # Tag flaky-known devices via noise_allowlist.yaml
            echo "$Z2M_STATS" | grep "^STALE:" | cut -d: -f2- | head -10 \
                | while IFS= read -r _stale_line; do
                    tag=$(_noise_tag "$_stale_line")
                    printf '%s%s\n' "$_stale_line" "$tag"
                done
            echo "Total offline >5 days: $Z2M_OFFLINE32"
        else
            echo "None"
        fi
        echo ""

        # Check Zigbee coordinator/controller errors in logs
        Z2M_COORD_ERRORS=$(safe_count "kubectl logs -n home-automation deployment/zigbee2mqtt --tail=100 --since=24h 2>&1 | grep -iE '(error|ERROR)' | grep -v 'WARN' | wc -l")
        echo "Zigbee2MQTT errors (24h): $Z2M_COORD_ERRORS"

        Z2M_ISSUES=0
        # Baseline: 23 stale entries from decommissioned devices — see docs/troubleshooting/ha-upstream-integration-issues.md
        Z2M_OFFLINE_BASELINE=23
        if [ -n "$Z2M_OFFLINE32" ] && [ "${Z2M_OFFLINE32:-0}" -gt $((Z2M_OFFLINE_BASELINE + 5)) ] 2>/dev/null; then
            log_warning "Zigbee devices offline >5 days above baseline: $Z2M_OFFLINE32 (baseline: $Z2M_OFFLINE_BASELINE)"
            add_minor_issue "Zigbee devices offline >5 days: $Z2M_OFFLINE32/${Z2M_TOTAL32} (baseline $Z2M_OFFLINE_BASELINE)"
            Z2M_ISSUES=$((Z2M_ISSUES + 1))
        elif [ -n "$Z2M_OFFLINE32" ] && [ "${Z2M_OFFLINE32:-0}" -gt 0 ] 2>/dev/null; then
            log_info "Zigbee stale state entries: $Z2M_OFFLINE32 (baseline $Z2M_OFFLINE_BASELINE — decommissioned devices)"
        fi
        if [ "$Z2M_COORD_ERRORS" -gt 20 ]; then
            log_warning "High Zigbee2MQTT error count: $Z2M_COORD_ERRORS in 24h"
            add_minor_issue "Zigbee2MQTT coordinator errors: $Z2M_COORD_ERRORS"
            Z2M_ISSUES=$((Z2M_ISSUES + 1))
        fi
        if [ "$Z2M_ISSUES" -eq 0 ]; then
            log_success "Zigbee2MQTT healthy (${Z2M_TOTAL32:-?} devices)"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 33: Battery Health Monitoring"
{
    echo "Checking battery status across all Zigbee devices..."
    echo ""

    # Get battery data (IEEE addresses and levels)
    BATTERY_DATA=$(kubectl exec -n home-automation deployment/zigbee2mqtt -- cat /data/state.json 2>/dev/null | jq -r 'to_entries[] | select(.value | has("battery")) | "\(.key)|\(.value.battery)"' 2>/dev/null || echo "")

    # Get device friendly names mapping
    CONFIG_DATA=$(kubectl exec -n home-automation deployment/zigbee2mqtt -- cat /data/configuration.yaml 2>/dev/null | grep -A1 "'0x" | grep -E "^  '0x|friendly_name:" | sed "s/'//g" | paste - - | awk -F: '{gsub(/^[ \t]+/, "", $1); gsub(/^[ \t]+/, "", $3); print $1"|"$3}' 2>/dev/null || echo "")

    # Create combined list with friendly names
    BATTERY_LIST=""
    while IFS='|' read -r ieee battery; do
        if [ -n "$ieee" ] && [ -n "$battery" ]; then
            # Look up friendly name
            friendly=$(echo "$CONFIG_DATA" | grep "^$ieee|" | cut -d'|' -f2-)
            [ -z "$friendly" ] && friendly="$ieee"
            BATTERY_LIST="${BATTERY_LIST}${friendly}|${battery}"$'\n'
        fi
    done <<< "$BATTERY_DATA"

    if [ -z "$BATTERY_LIST" ]; then
        echo "⚠️  Unable to retrieve battery data"
        log_warning "Unable to retrieve Zigbee battery data"
        add_minor_issue "Cannot retrieve Zigbee battery status"
    else
        # Count total battery devices
        TOTAL_BATTERY=$(echo "$BATTERY_LIST" | wc -l)
        echo "Total battery-powered devices: $TOTAL_BATTERY"
        echo ""

        # Initialize counters
        CRITICAL_COUNT=0
        WARNING_COUNT=0
        MONITOR_COUNT=0
        GOOD_COUNT=0

        # Categorize by battery level
        CRITICAL_BATTERIES=""
        WARNING_BATTERIES=""
        MONITOR_BATTERIES=""

        while IFS='|' read -r friendly battery; do
            if [ -n "$friendly" ] && [ -n "$battery" ]; then
                # Remove any decimal points
                battery_int=$(echo "$battery" | awk '{print int($1)}')

                if [ "$battery_int" -lt 15 ]; then
                    CRITICAL_BATTERIES="${CRITICAL_BATTERIES}  - ${friendly} (${battery}%)\n"
                    CRITICAL_COUNT=$((CRITICAL_COUNT + 1))
                elif [ "$battery_int" -lt 30 ]; then
                    WARNING_BATTERIES="${WARNING_BATTERIES}  - ${friendly} (${battery}%)\n"
                    WARNING_COUNT=$((WARNING_COUNT + 1))
                elif [ "$battery_int" -lt 50 ]; then
                    MONITOR_BATTERIES="${MONITOR_BATTERIES}  - ${friendly} (${battery}%)\n"
                    MONITOR_COUNT=$((MONITOR_COUNT + 1))
                else
                    GOOD_COUNT=$((GOOD_COUNT + 1))
                fi
            fi
        done <<< "$BATTERY_LIST"

        # Display categorized results
        # Helper: tag known-flaky zigbee devices from noise_allowlist.yaml
        _print_battery_block() {
            local block="$1"
            # echo -e expands the literal \n separators we built earlier
            echo -e "$block" | while IFS= read -r _bat_line; do
                [ -z "$_bat_line" ] && continue
                tag=$(_noise_tag "$_bat_line")
                printf '%s%s\n' "$_bat_line" "$tag"
            done
        }

        echo "🔴 CRITICAL (<15%) - Replace Immediately:"
        if [ "$CRITICAL_COUNT" -gt 0 ]; then
            _print_battery_block "$CRITICAL_BATTERIES"
        else
            echo "  None"
        fi
        echo ""

        echo "🟡 WARNING (15-30%) - Replace Soon:"
        if [ "$WARNING_COUNT" -gt 0 ]; then
            _print_battery_block "$WARNING_BATTERIES"
        else
            echo "  None"
        fi
        echo ""

        echo "🔵 MONITOR (30-50%) - Watch Closely:"
        if [ "$MONITOR_COUNT" -gt 0 ]; then
            _print_battery_block "$MONITOR_BATTERIES"
        else
            echo "  None"
        fi
        echo ""

        echo "✅ GOOD (>50%):"
        echo "  $GOOD_COUNT devices"
        echo ""

        # Calculate average battery level
        AVG_BATTERY=$(echo "$BATTERY_LIST" | awk -F'|' '{sum+=$2; count++} END {if(count>0) print int(sum/count); else print 0}')
        echo "Average battery level: ${AVG_BATTERY}%"
        echo ""

        # Add issues based on severity
        if [ "$CRITICAL_COUNT" -gt 0 ]; then
            log_warning "CRITICAL: $CRITICAL_COUNT devices with batteries <15%"
            add_major_issue "Critical battery levels (<15%): $CRITICAL_COUNT devices need immediate replacement"
        fi

        if [ "$WARNING_COUNT" -gt 0 ]; then
            log_warning "WARNING: $WARNING_COUNT devices with batteries 15-30%"
            add_minor_issue "Low batteries (15-30%): $WARNING_COUNT devices need replacement soon"
        fi

        if [ "$CRITICAL_COUNT" -eq 0 ] && [ "$WARNING_COUNT" -eq 0 ]; then
            log_success "All Zigbee device batteries above 30%"
        fi

        # Show recommendations
        echo "📋 Recommendations:"
        if [ "$CRITICAL_COUNT" -gt 0 ]; then
            echo "  🔴 URGENT: Replace batteries in $CRITICAL_COUNT devices immediately"
        fi
        if [ "$WARNING_COUNT" -gt 0 ]; then
            echo "  🟡 Replace batteries in $WARNING_COUNT devices within 1-2 weeks"
        fi
        if [ "$MONITOR_COUNT" -gt 0 ]; then
            echo "  🔵 Monitor $MONITOR_COUNT devices, plan battery replacement"
        fi
        if [ "$CRITICAL_COUNT" -eq 0 ] && [ "$WARNING_COUNT" -eq 0 ] && [ "$MONITOR_COUNT" -eq 0 ]; then
            echo "  ✅ All devices have healthy battery levels"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 34: Elasticsearch & OTel Pipeline Health"
{
    echo "Checking Elasticsearch cluster, OTel pipeline, and application log error patterns..."
    echo ""

    # --- OTel Pipeline Component Health (edot-collector + otel-operator) ---
    echo "=== OTel Pipeline Health ==="

    # edot-collector gateway deployment
    EDOT_READY=$(kubectl get deployment edot-collector -n monitoring -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    EDOT_DESIRED=$(kubectl get deployment edot-collector -n monitoring -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "1")
    echo "edot-collector: ${EDOT_READY}/${EDOT_DESIRED} ready"
    if [ "${EDOT_READY}" = "${EDOT_DESIRED}" ] && [ "${EDOT_DESIRED}" != "0" ]; then
        log_success "edot-collector gateway is running (${EDOT_READY}/${EDOT_DESIRED})"
    else
        log_critical "edot-collector gateway not ready (${EDOT_READY}/${EDOT_DESIRED})"
        add_critical_issue "edot-collector gateway not ready: ${EDOT_READY}/${EDOT_DESIRED}"
    fi

    # edot-collector pod restarts
    EDOT_RESTARTS=$(kubectl get pods -n monitoring -l app=edot-collector -o json 2>/dev/null | python3 -c "
import sys, json
try:
    pods = json.load(sys.stdin)['items']
    restarts = [cs.get('restartCount', 0) for p in pods for cs in p.get('status', {}).get('containerStatuses', [])]
    print(max(restarts) if restarts else 0)
except:
    print(0)
" 2>/dev/null || echo "0")
    echo "edot-collector pod restarts: $EDOT_RESTARTS"
    if [ "$EDOT_RESTARTS" -gt 5 ]; then
        log_warning "edot-collector has $EDOT_RESTARTS restarts"
        add_minor_issue "edot-collector restart count high: $EDOT_RESTARTS"
    fi

    # otel-operator DaemonSet (daemon collectors per node)
    OTEL_DAEMON_READY=$(kubectl get daemonset -n monitoring -l app.kubernetes.io/managed-by=opentelemetry-operator -o json 2>/dev/null | python3 -c "
import sys, json
try:
    items = json.load(sys.stdin)['items']
    for ds in items:
        desired = ds['status'].get('desiredNumberScheduled', 0)
        ready = ds['status'].get('numberReady', 0)
        name = ds['metadata']['name']
        print(f'{name}: {ready}/{desired}')
except:
    print('not found')
" 2>/dev/null || echo "not found")
    echo "OTel DaemonSet collectors: $OTEL_DAEMON_READY"
    if echo "$OTEL_DAEMON_READY" | grep -qE "^[^:]+: [0-9]+/[0-9]+$"; then
        OTEL_R=$(echo "$OTEL_DAEMON_READY" | python3 -c "import sys; parts=sys.stdin.read().strip().split('/'); print(parts[0].split(': ')[1])" 2>/dev/null || echo "0")
        OTEL_D=$(echo "$OTEL_DAEMON_READY" | python3 -c "import sys; parts=sys.stdin.read().strip().split('/'); print(parts[1])" 2>/dev/null || echo "1")
        if [ "$OTEL_R" = "$OTEL_D" ] && [ "$OTEL_D" != "0" ]; then
            log_success "OTel DaemonSet collectors running on all nodes ($OTEL_DAEMON_READY)"
        else
            log_warning "OTel DaemonSet collectors not covering all nodes: $OTEL_DAEMON_READY"
            add_major_issue "OTel DaemonSet not fully ready: $OTEL_DAEMON_READY"
        fi
    else
        log_warning "OTel DaemonSet collectors not found or not running"
        add_major_issue "OTel DaemonSet collectors not found"
    fi
    echo ""

    # --- Prometheus enrichment: OTel pipeline metrics ---
    echo "=== OTel Pipeline Metrics (Prometheus) ==="
    OTEL_FAIL=$(prom_query 'sum(rate(otelcol_exporter_send_failed_metric_points[5m])) + sum(rate(otelcol_exporter_send_failed_log_records[5m]))')
    FAIL_RATE="0"
    if [ -n "$OTEL_FAIL" ]; then
        FAIL_RATE=$(echo "$OTEL_FAIL" | python3 -c "
import sys, json
try:
    r = json.load(sys.stdin)['data']['result']
    if r and len(r) > 0:
        print(f'{float(r[0][\"value\"][1]):.3f}')
    else:
        print('0')
except: print('0')
" 2>/dev/null)
    fi
    echo "OTel export failure rate (5m): ${FAIL_RATE}/sec"
    if [ "$(echo "$FAIL_RATE > 0" | bc 2>/dev/null)" = "1" ]; then
        log_warning "OTel exporter has failures: $FAIL_RATE/sec"
        add_minor_issue "OTel exporter failures: $FAIL_RATE/sec over 5m"
    else
        log_success "OTel exporter has no failures (5m)"
    fi

    # Queue saturation (any exporter >80% full)
    OTEL_QUEUE=$(prom_query 'max(otelcol_exporter_queue_size / otelcol_exporter_queue_capacity) > 0.8')
    if [ -n "$OTEL_QUEUE" ]; then
        QUEUE_HIGH=$(echo "$OTEL_QUEUE" | python3 -c "
import sys, json
try:
    r = json.load(sys.stdin)['data']['result']
    if r:
        print(f'{float(r[0][\"value\"][1])*100:.1f}')
except: pass
" 2>/dev/null)
        if [ -n "$QUEUE_HIGH" ]; then
            echo "OTel exporter queue saturation: ${QUEUE_HIGH}%"
            log_warning "OTel exporter queue >80% full: ${QUEUE_HIGH}%"
            add_minor_issue "OTel exporter queue saturation: ${QUEUE_HIGH}%"
        fi
    fi

    # Dropped logs (memory limiter kicking in)
    OTEL_DROP=$(prom_query 'sum(rate(otelcol_processor_dropped_log_records_total[5m]))')
    if [ -n "$OTEL_DROP" ]; then
        DROP_RATE=$(echo "$OTEL_DROP" | python3 -c "
import sys, json
try:
    r = json.load(sys.stdin)['data']['result']
    if r:
        print(f'{float(r[0][\"value\"][1]):.3f}')
except: print('0')
" 2>/dev/null)
        if [ -n "$DROP_RATE" ] && [ "$(echo "$DROP_RATE > 0" | bc 2>/dev/null)" = "1" ]; then
            echo "OTel dropped log rate (5m): $DROP_RATE/sec"
            log_info "OTel processor dropping logs: $DROP_RATE/sec"
        fi
    fi
    echo ""

    # --- Elasticsearch Cluster Health ---
    echo "=== Elasticsearch Cluster Health ==="
    ES_PW_EARLY=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' 2>/dev/null | base64 -d || echo "")
    if [ -n "$ES_PW_EARLY" ]; then
        kubectl port-forward -n monitoring svc/elasticsearch-es-http 9201:9200 > /dev/null 2>&1 &
        ES_PF_PID=$!
        sleep 3

        ES_STATUS=$(curl -k -s -u "elastic:$ES_PW_EARLY" "https://localhost:9201/_cluster/health" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
        echo "Elasticsearch cluster status: $ES_STATUS"
        if [ "$ES_STATUS" = "red" ]; then
            log_critical "Elasticsearch cluster status is RED - data loss or unavailability"
            add_critical_issue "Elasticsearch cluster health is RED"
        elif [ "$ES_STATUS" = "yellow" ]; then
            log_warning "Elasticsearch cluster status is YELLOW - some replicas unavailable"
            add_minor_issue "Elasticsearch cluster health is YELLOW (replica shards unassigned)"
        elif [ "$ES_STATUS" = "green" ]; then
            log_success "Elasticsearch cluster status is GREEN"
        else
            log_warning "Elasticsearch cluster status unknown: $ES_STATUS"
        fi

        # --- OTel data stream ingestion check ---
        echo ""
        echo "=== OTel Data Stream Ingestion Check ==="

        LOGS_COUNT=$(curl -k -s -u "elastic:$ES_PW_EARLY" "https://localhost:9201/logs-generic-default/_count" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('count',0))" 2>/dev/null || echo "0")
        echo "logs-generic-default document count: $LOGS_COUNT"
        LOGS_COUNT_INT=$(echo "$LOGS_COUNT" | tr -cd '0-9' || echo "0")
        [ -z "$LOGS_COUNT_INT" ] && LOGS_COUNT_INT=0
        if [ "$LOGS_COUNT_INT" -eq 0 ]; then
            log_warning "No OTel log documents found in logs-generic-default"
            add_major_issue "OTel: no documents in logs-generic-default data stream"
        else
            log_success "OTel log documents present in logs-generic-default: $LOGS_COUNT_INT"
        fi

        METRICS_COUNT=$(curl -k -s -u "elastic:$ES_PW_EARLY" "https://localhost:9201/metrics-generic.otel-default/_count" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('count',0))" 2>/dev/null || echo "0")
        echo "metrics-generic.otel-default document count: $METRICS_COUNT"
        METRICS_COUNT_INT=$(echo "$METRICS_COUNT" | tr -cd '0-9' || echo "0")
        [ -z "$METRICS_COUNT_INT" ] && METRICS_COUNT_INT=0
        if [ "$METRICS_COUNT_INT" -eq 0 ]; then
            log_warning "No OTel metric documents found in metrics-generic.otel-default"
            add_major_issue "OTel: no documents in metrics-generic.otel-default data stream"
        else
            log_success "OTel metric documents present in metrics-generic.otel-default: $METRICS_COUNT_INT"
        fi

        # ES metric ingestion verification: how many distinct metric names in last 5 minutes?
        METRIC_NAMES=$(curl -k -s -u "elastic:$ES_PW_EARLY" "https://localhost:9201/metrics-generic.otel-default/_search?size=0" \
            -H 'Content-Type: application/json' \
            -d '{"query":{"range":{"@timestamp":{"gte":"now-5m"}}},"aggs":{"names":{"cardinality":{"field":"_metric_names_hash"}}}}' 2>/dev/null | \
            python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('aggregations',{}).get('names',{}).get('value', 0))
except: print(0)
" 2>/dev/null || echo "0")
        echo "Distinct metric names arriving (5m): $METRIC_NAMES"
        METRIC_NAMES_INT=$(echo "$METRIC_NAMES" | tr -cd '0-9' || echo "0")
        [ -z "$METRIC_NAMES_INT" ] && METRIC_NAMES_INT=0
        if [ "$METRIC_NAMES_INT" -lt 5 ]; then
            log_warning "Only $METRIC_NAMES_INT distinct metric names in last 5m (ingestion may be stalled)"
            add_minor_issue "ES metric ingestion appears stalled: $METRIC_NAMES_INT distinct names in 5m"
        else
            log_success "ES metric ingestion healthy: $METRIC_NAMES_INT distinct metric names in 5m"
        fi

        # Recent ingestion check (last 5 minutes)
        RECENT_LOGS=$(curl -k -s -u "elastic:$ES_PW_EARLY" "https://localhost:9201/logs-generic-default/_count" \
            -H 'Content-Type: application/json' \
            -d '{"query":{"range":{"@timestamp":{"gte":"now-5m"}}}}' 2>/dev/null | \
            python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('count',0))" 2>/dev/null || echo "0")
        echo "Logs ingested in last 5 minutes: $RECENT_LOGS"
        RECENT_LOGS_INT=$(echo "$RECENT_LOGS" | tr -cd '0-9' || echo "0")
        [ -z "$RECENT_LOGS_INT" ] && RECENT_LOGS_INT=0
        if [ "$RECENT_LOGS_INT" -eq 0 ] && [ "$EDOT_READY" = "$EDOT_DESIRED" ]; then
            log_warning "No OTel logs ingested in the last 5 minutes (edot-collector is up)"
            add_major_issue "OTel log ingestion stalled: 0 logs in last 5 minutes"
        elif [ "$RECENT_LOGS_INT" -gt 0 ]; then
            log_success "OTel logs flowing: $RECENT_LOGS_INT documents in last 5 minutes"
        fi

        kill $ES_PF_PID 2>/dev/null || true
        wait $ES_PF_PID 2>/dev/null || true
    else
        log_warning "Elasticsearch password not accessible - skipping cluster health check"
    fi

    # Get Elasticsearch password for log error analysis
    ES_PASSWORD=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' 2>/dev/null | base64 -d || echo "")

    if [ -z "$ES_PASSWORD" ]; then
        log_warning "Cannot retrieve Elasticsearch password"
        add_major_issue "Elasticsearch password not accessible"
    else
        kubectl port-forward -n monitoring svc/elasticsearch-es-http 9200:9200 > /dev/null 2>&1 &
        PF_PID=$!
        sleep 3

        # OTel log data stream -- replaces per-day fluent-bit-YYYY.MM.DD index
        LOG_DS="logs-generic-default"
        echo "Querying OTel log data stream: $LOG_DS (last 24h)"
        echo ""

        # Query using OTel severity_text (structured) with body fallback
        ERROR_DATA=$(curl -k -u "elastic:$ES_PASSWORD" -X GET "https://localhost:9200/${LOG_DS}/_search" -H 'Content-Type: application/json' -d '{
          "size": 0,
          "query": {
            "bool": {
              "should": [
                {"terms": {"severity_text": ["ERROR", "FATAL", "CRITICAL", "error", "fatal", "critical"]}},
                {"match": {"body": "error"}},
                {"match": {"body": "ERROR"}},
                {"match": {"body": "fatal"}},
                {"match": {"body": "FATAL"}}
              ],
              "minimum_should_match": 1,
              "filter": [{"range": {"@timestamp": {"gte": "now-24h"}}}]
            }
          },
          "aggs": {
            "by_namespace": {
              "terms": {"field": "resource.attributes.k8s.namespace.name", "size": 10}
            },
            "by_pod": {
              "terms": {"field": "resource.attributes.k8s.pod.name", "size": 10}
            }
          }
        }' 2>/dev/null || echo '{"hits":{"total":{"value":0}}}')

        TOTAL_ERRORS=$(echo "$ERROR_DATA" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['hits']['total']['value'])
except:
    print('0')
" || echo "0")

        echo "Total error-level logs in last 24h: $TOTAL_ERRORS"
        echo ""

        if [ "$TOTAL_ERRORS" -gt 0 ] && [ "$TOTAL_ERRORS" != "0" ]; then
            echo "Top 5 namespaces with errors:"
            echo "$ERROR_DATA" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for bucket in data['aggregations']['by_namespace']['buckets'][:5]:
        print(f\"  {bucket['key']}: {bucket['doc_count']}\")
except:
    print('  Unable to parse data')
"
            echo ""
            echo "Top 5 pods with errors:"
            echo "$ERROR_DATA" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for bucket in data['aggregations']['by_pod']['buckets'][:5]:
        print(f\"  {bucket['key']}: {bucket['doc_count']}\")
except:
    print('  Unable to parse data')
"
            echo ""
        fi

        # Critical pattern check -- FATAL severity_text + OOMKilled in body
        echo "Checking for critical error patterns..."
        FATAL_COUNT=$(curl -k -u "elastic:$ES_PASSWORD" -X GET "https://localhost:9200/${LOG_DS}/_search" -H 'Content-Type: application/json' -d '{
          "size": 0,
          "query": {
            "bool": {
              "should": [
                {"terms": {"severity_text": ["FATAL", "fatal"]}},
                {"match": {"body": "OOMKilled"}},
                {"match": {"body": "out of memory"}}
              ],
              "minimum_should_match": 1,
              "filter": [{"range": {"@timestamp": {"gte": "now-24h"}}}]
            }
          }
        }' 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['hits']['total']['value'])
except:
    print('0')
" || echo "0")

        echo "  FATAL/OOMKilled errors (last 24h): $FATAL_COUNT"
        echo ""

        kill $PF_PID 2>/dev/null || true
        wait $PF_PID 2>/dev/null || true

        TOTAL_ERRORS_INT=$(echo "$TOTAL_ERRORS" | tr -cd '0-9' || echo "0")
        [ -z "$TOTAL_ERRORS_INT" ] && TOTAL_ERRORS_INT=0
        FATAL_COUNT_INT=$(echo "$FATAL_COUNT" | tr -cd '0-9' || echo "0")
        [ -z "$FATAL_COUNT_INT" ] && FATAL_COUNT_INT=0

        if [ "$FATAL_COUNT_INT" -gt 0 ]; then
            log_critical "FATAL/OOM errors detected in logs: $FATAL_COUNT_INT"
            add_critical_issue "FATAL/OOM errors in Elasticsearch logs: $FATAL_COUNT_INT"
        elif [ "$TOTAL_ERRORS_INT" -gt 10000 ]; then
            log_warning "High error count in logs: $TOTAL_ERRORS_INT (>10,000 threshold)"
            add_major_issue "High error count in logs: $TOTAL_ERRORS_INT"
        elif [ "$TOTAL_ERRORS_INT" -gt 5000 ]; then
            log_warning "Elevated error count in logs: $TOTAL_ERRORS_INT"
            add_minor_issue "Elevated error count in logs: $TOTAL_ERRORS_INT"
        elif [ "$TOTAL_ERRORS_INT" -lt 1000 ]; then
            log_success "Log error count within normal range: $TOTAL_ERRORS_INT"
        else
            log_info "Log error count: $TOTAL_ERRORS_INT (monitor for trends)"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1


log_section "Section 35: Ingress Backend Health"
{
    echo "Checking ingress backend health..."

    # Check for ingresses with no backend endpoints
    MISSING_BACKENDS=0
    kubectl get ingress -A -o json 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for ing in data.get('items', []):
        ns = ing['metadata']['namespace']
        name = ing['metadata']['name']
        rules = ing.get('spec', {}).get('rules', [])
        for rule in rules:
            host = rule.get('host', 'unknown')
            paths = rule.get('http', {}).get('paths', [])
            for path in paths:
                backend = path.get('backend', {})
                svc_name = backend.get('service', {}).get('name')
                if svc_name:
                    print(f'{ns}|{host}|{svc_name}')
except Exception as e:
    pass
" 2>/dev/null | while IFS='|' read ns host svc; do
        if [ -n "$ns" ] && [ -n "$svc" ]; then
            # Check if this is an ExternalName service (Authentik outposts) - these resolve via DNS, not Endpoints
            SVC_TYPE=$(kubectl get svc "$svc" -n "$ns" -o jsonpath='{.spec.type}' 2>/dev/null || echo "")
            if [ "$SVC_TYPE" = "ExternalName" ]; then
                echo "ℹ️  ExternalName service $ns/$svc (DNS-resolved, no Endpoints object expected)"
            else
                ENDPOINTS=$(kubectl get endpoints "$svc" -n "$ns" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null || echo "")
                if [ -z "$ENDPOINTS" ]; then
                    echo "⚠️  No backends for $host (service: $ns/$svc)"
                    MISSING_BACKENDS=$((MISSING_BACKENDS + 1))
                fi
            fi
        fi
    done

    # Check ingress controller errors
    INGRESS_ERRORS=$(safe_count "kubectl logs -n network -l app.kubernetes.io/name=ingress-nginx --tail=200 --since=1h 2>&1 | grep -E '\[error\]|\[emerg\]' | wc -l")
    echo "Ingress controller errors (last hour): $INGRESS_ERRORS"

    if [ "$MISSING_BACKENDS" -gt 0 ]; then
        log_warning "Ingresses with missing backends: $MISSING_BACKENDS"
        add_major_issue "Ingress backends unavailable: $MISSING_BACKENDS services"
    elif [ "$INGRESS_ERRORS" -gt 10 ]; then
        log_warning "High ingress controller error count: $INGRESS_ERRORS"
        add_minor_issue "Ingress controller errors: $INGRESS_ERRORS in last hour"
    else
        log_success "All ingress backends healthy"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 36: PVC Capacity Monitoring"
{
    echo "Checking PVC status..."

    # --- CSI SMB / NAS mount check ---
    echo "=== CSI SMB (NAS) Volume Check ==="
    SMB_PV_INFO=$(kubectl get pv -o json 2>/dev/null | python3 -c "
import sys, json
try:
    pvs = json.load(sys.stdin)['items']
    smb = [p['metadata']['name'] for p in pvs if p.get('spec',{}).get('csi',{}).get('driver','') == 'smb.csi.k8s.io']
    print(len(smb))
    for s in smb:
        print(' ', s)
except Exception as e:
    print(0)
" 2>/dev/null || echo "0")
    SMB_COUNT=$(echo "$SMB_PV_INFO" | head -1 | tr -d ' ' || echo "0")
    echo "SMB PV count: $SMB_COUNT"
    if [ "$SMB_COUNT" -gt 0 ]; then
        echo "$SMB_PV_INFO" | tail -n +2

        # Check if any SMB PVCs are not bound
        SMB_UNBOUND=$(kubectl get pv -o json 2>/dev/null | python3 -c "
import sys, json
try:
    pvs = json.load(sys.stdin)['items']
    unbound = [p['metadata']['name'] for p in pvs
               if p.get('spec',{}).get('csi',{}).get('driver','') == 'smb.csi.k8s.io'
               and p.get('status',{}).get('phase','') != 'Bound']
    print(len(unbound))
    for s in unbound:
        print(' ', s)
except:
    print(0)
" 2>/dev/null || echo "0")
        SMB_UNBOUND_COUNT=$(echo "$SMB_UNBOUND" | head -1 | tr -d ' ' || echo "0")
        if [ "$SMB_UNBOUND_COUNT" -gt 0 ]; then
            log_warning "SMB PVs not in Bound state: $SMB_UNBOUND_COUNT"
            add_major_issue "CSI SMB NAS PVs not bound: $SMB_UNBOUND_COUNT volume(s) unbound"
        else
            log_success "All SMB PVs bound ($SMB_COUNT volumes)"
        fi

        # Check csi-driver-smb daemonset health
        CSI_SMB_DS_DESIRED=$(kubectl get daemonset -n kube-system csi-smb-node -o jsonpath='{.status.desiredNumberScheduled}' 2>/dev/null || echo "0")
        CSI_SMB_DS_READY=$(kubectl get daemonset -n kube-system csi-smb-node -o jsonpath='{.status.numberReady}' 2>/dev/null || echo "0")
        echo "csi-smb-node daemonset: $CSI_SMB_DS_READY/$CSI_SMB_DS_DESIRED ready"
        if [ "$CSI_SMB_DS_DESIRED" -gt 0 ] && [ "$CSI_SMB_DS_READY" != "$CSI_SMB_DS_DESIRED" ]; then
            log_warning "csi-smb-node daemonset not fully ready: $CSI_SMB_DS_READY/$CSI_SMB_DS_DESIRED"
            add_major_issue "csi-driver-smb daemonset unhealthy: $CSI_SMB_DS_READY/$CSI_SMB_DS_DESIRED nodes ready"
        fi
    else
        echo "  No SMB CSI PVs found"
    fi
    echo ""

    # Count PVCs by status
    BOUND_PVCS=$(safe_count "kubectl get pvc -A --no-headers 2>/dev/null | grep Bound | wc -l")
    PENDING_PVCS=$(safe_count "kubectl get pvc -A --no-headers 2>/dev/null | grep Pending | wc -l")
    LOST_PVCS=$(safe_count "kubectl get pvc -A --no-headers 2>/dev/null | grep Lost | wc -l")

    echo "PVC Status:"
    echo "  - Bound: $BOUND_PVCS"
    echo "  - Pending: $PENDING_PVCS"
    echo "  - Lost: $LOST_PVCS"
    echo ""

    # List PVC allocations
    echo "PVC Allocations (top 20 by size):"
    kubectl get pvc -A -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,SIZE:.spec.resources.requests.storage,STATUS:.status.phase' --no-headers 2>/dev/null | sort -k3 -h -r | head -20
    echo ""
    echo "Note: Actual disk usage requires metrics-server or Prometheus"

    if [ "$LOST_PVCS" -gt 0 ]; then
        log_critical "PVCs in Lost state: $LOST_PVCS"
        add_critical_issue "PVCs in Lost state: $LOST_PVCS volumes"
    elif [ "$PENDING_PVCS" -gt 0 ]; then
        log_warning "PVCs in Pending state: $PENDING_PVCS"
        add_major_issue "PVCs not bound: $PENDING_PVCS volumes"
    else
        log_success "All PVCs bound (total: $BOUND_PVCS)"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 37: Service Endpoint Health"
{
    echo "Checking services without endpoints..."

    # Find services without endpoints
    SERVICES_NO_ENDPOINTS=$(kubectl get endpoints -A -o json 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for ep in data.get('items', []):
        if not ep.get('subsets'):
            ns = ep['metadata']['namespace']
            name = ep['metadata']['name']
            print(f'{ns}/{name}')
except Exception as e:
    pass
")

    # Filter out known services that shouldn't have endpoints
    # Includes: headless services, metrics services, controller managers, webhooks, and replica services (commonly scaled to 0)
    PROBLEMATIC_SERVICES=$(echo "$SERVICES_NO_ENDPOINTS" | grep -vE "(headless|metrics-service|controller-manager|webhook|replica)" | grep -v "^$" || echo "")

    if [ -n "$PROBLEMATIC_SERVICES" ]; then
        echo "Services without endpoints:"
        echo "$PROBLEMATIC_SERVICES"
        echo ""

        SERVICE_COUNT=$(echo "$PROBLEMATIC_SERVICES" | grep -c "/" || echo "0")

        if [ "$SERVICE_COUNT" -gt 5 ]; then
            log_warning "Multiple services without endpoints: $SERVICE_COUNT"
            add_major_issue "Services without endpoints: $SERVICE_COUNT"
        elif [ "$SERVICE_COUNT" -gt 0 ]; then
            log_info "Services without endpoints: $SERVICE_COUNT (may be expected)"
            add_minor_issue "Services without endpoints: $SERVICE_COUNT"
        fi
    else
        log_success "All services have endpoints"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 38: Admission Webhook Health"
{
    echo "Checking admission webhooks..."

    # Check for webhook failures in events
    WEBHOOK_FAILURES=$(safe_count "kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | grep -i 'webhook' | grep -iE 'failed|error|timeout' | wc -l")

    # List configured webhooks
    VALIDATING_WEBHOOKS=$(safe_count "kubectl get validatingwebhookconfigurations --no-headers 2>/dev/null | wc -l")
    MUTATING_WEBHOOKS=$(safe_count "kubectl get mutatingwebhookconfigurations --no-headers 2>/dev/null | wc -l")
    TOTAL_WEBHOOKS=$((VALIDATING_WEBHOOKS + MUTATING_WEBHOOKS))

    echo "Webhook Configuration:"
    echo "  - Validating webhooks: $VALIDATING_WEBHOOKS"
    echo "  - Mutating webhooks: $MUTATING_WEBHOOKS"
    echo "  - Total: $TOTAL_WEBHOOKS"
    echo ""

    if [ "$WEBHOOK_FAILURES" -gt 10 ]; then
        log_warning "High webhook failure count: $WEBHOOK_FAILURES"
        add_major_issue "Admission webhook failures: $WEBHOOK_FAILURES"
    elif [ "$WEBHOOK_FAILURES" -gt 0 ]; then
        log_info "Webhook failures detected: $WEBHOOK_FAILURES"
        add_minor_issue "Admission webhook failures: $WEBHOOK_FAILURES"
    else
        log_success "All webhooks healthy ($TOTAL_WEBHOOKS configured)"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "UnPoller Status (Current Investigation)"
{
    echo "UnPoller deployment:"
    kubectl get deployment -n monitoring unpoller 2>/dev/null || echo "UnPoller not found"
    echo ""

    echo "UnPoller pods:"
    kubectl get pods -n monitoring -l app.kubernetes.io/name=unpoller
    echo ""

    UNPOLLER_POD=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=unpoller -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$UNPOLLER_POD" ]; then
        echo "Recent UnPoller logs (last 50 lines):"
        kubectl logs -n monitoring "$UNPOLLER_POD" --tail=50 2>&1 || echo "Unable to get logs"
        echo ""

        # Check for errors using structured pattern
        UNPOLLER_ERRORS=$(safe_count "kubectl logs -n monitoring '$UNPOLLER_POD' --tail=100 2>&1 | grep '\[ERROR\]' | wc -l")
        echo "UnPoller errors (last 100 lines): $UNPOLLER_ERRORS"

        # Check for recent successful operations to detect recovery
        UNPOLLER_SUCCESS=$(safe_count "kubectl logs -n monitoring '$UNPOLLER_POD' --tail=20 2>&1 | grep 'Err: 0' | wc -l")
        echo "UnPoller recent successful operations (last 20 lines): $UNPOLLER_SUCCESS"

        UNPOLLER_STATUS=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=unpoller -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Unknown")

        if [ "$UNPOLLER_STATUS" == "Running" ] && [ "$UNPOLLER_ERRORS" -eq 0 ]; then
            log_success "UnPoller is running successfully"
        elif [ "$UNPOLLER_STATUS" == "Running" ] && [ "$UNPOLLER_ERRORS" -gt 0 ] && [ "$UNPOLLER_SUCCESS" -gt 5 ]; then
            log_info "UnPoller had transient errors but is currently healthy (recent operations successful)"
        elif [ "$UNPOLLER_STATUS" == "Running" ] && [ "$UNPOLLER_ERRORS" -gt 0 ]; then
            log_warning "UnPoller has errors without recent recovery: $UNPOLLER_ERRORS"
            add_minor_issue "UnPoller has persistent errors: $UNPOLLER_ERRORS"
        else
            log_critical "UnPoller is not running properly (Status: $UNPOLLER_STATUS)"
            add_critical_issue "UnPoller not running (Status: $UNPOLLER_STATUS)"
        fi
    else
        log_warning "UnPoller pod not found"
        add_minor_issue "UnPoller pod not found"
    fi
} >> "$OUTPUT_FILE" 2>&1

#######################################
# Generate Issues Summary
#######################################

# Calculate counts outside subshell to avoid unbound variable errors
# Temporarily disable strict mode for array length checks
set +u
CRIT_COUNT="${#CRITICAL_ISSUES_LIST[@]}"
MAJOR_COUNT="${#MAJOR_ISSUES_LIST[@]}"
MINOR_COUNT="${#MINOR_ISSUES_LIST[@]}"
set -u

echo "" | tee -a "$OUTPUT_FILE"
log_section "ES Log Insights (7-day analysis)"
{
    if [ "$ES_AVAILABLE" = "true" ]; then
        echo "=== Top Error Producers (7d) ==="
        ES_TOP=$(es_query '{
          "size": 0,
          "query": {"bool": {
            "should": [
              {"wildcard": {"body.text": "*ERROR*"}},
              {"wildcard": {"body.text": "*FATAL*"}}
            ],
            "minimum_should_match": 1,
            "filter": [{"range": {"@timestamp": {"gte": "now-7d"}}}]
          }},
          "aggs": {
            "by_namespace": {
              "terms": {"field": "resource.attributes.k8s.namespace.name", "size": 15},
              "aggs": {
                "last_24h": {"filter": {"range": {"@timestamp": {"gte": "now-24h"}}}}
              }
            }
          }
        }')
        if [ -n "$ES_TOP" ]; then
            echo "$ES_TOP" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    total = d['hits']['total']['value']
    buckets = d['aggregations']['by_namespace']['buckets']
    print(f'Total errors (7d): {total}')
    print()
    print(f'{\"Namespace\":<30} {\"7d total\":>10} {\"Last 24h\":>10} {\"Trend\":>10}')
    print('-' * 65)
    for b in buckets:
        ns = b['key']
        ns_total = b['doc_count']
        ns_24h = b['last_24h']['doc_count']
        daily_avg = ns_total / 7
        if ns_24h > daily_avg * 2 and ns_24h > 20:
            trend = '↑ SPIKE'
        elif ns_24h < daily_avg * 0.3:
            trend = '↓ low'
        else:
            trend = '→ stable'
        print(f'{ns:<30} {ns_total:>10,} {ns_24h:>10,} {trend:>10}')
except Exception as e:
    print(f'ES query parse error: {e}')
" 2>/dev/null
            log_info "ES Log Insights completed"
        else
            echo "  ES query failed"
        fi
    else
        echo "  Elasticsearch unavailable — skipping log insights"
    fi
    echo ""
} >> "$OUTPUT_FILE" 2>&1

echo "" | tee -a "$OUTPUT_FILE"
log_section "Section 40: Infrastructure Device Health (Kuma)"
{
    echo "=== Querying Uptime Kuma via Prometheus ==="

    # Category map — hostname/name patterns → category + severity
    # CRITICAL (major issue): named infra that breaks the house
    # BRIDGE (minor): smart home bridges (usability, not essential)
    # SHELLY (info): individual Shelly devices
    # CAMERA (minor): security cameras
    # TEMP (info): synthetic temperature probes
    # OTHER (info): unclassified

    DOWN=$(prom_query 'monitor_status{monitor_type!="group"} == 0')
    if [ -z "$DOWN" ]; then
        log_info "Kuma query failed — skipping infrastructure device check"
    else
        echo "$DOWN" | python3 -c "
import sys, json, re

CATEGORY_RULES = [
    (r'Solarfocus|openDTU|Tibber Pulse|Zigbee (Router|coordinator)|SLZB|UNAS|NUC Talos|DreamMachine|Switch (48|24|5|8)|AP (Hallway|Upstairs|Basement)|Pi-KVM', 'CRITICAL', 'major'),
    (r'Homatic|DIRIGERA|Philips Hue|Nuki|Somfy|Harmony|Pioneer', 'BRIDGE', 'minor'),
    (r'^Shelly', 'SHELLY', 'info'),
    (r'Wyze Cam', 'CAMERA', 'minor'),
    (r'Temp|CPU Temp|GPU Temp|SSD Temp', 'TEMP', 'info'),
]

def classify(name):
    for pat, cat, sev in CATEGORY_RULES:
        if re.search(pat, name, re.I):
            return cat, sev
    return 'OTHER', 'info'

try:
    d = json.load(sys.stdin)
    results = d['data']['result']
    by_cat = {}
    for r in results:
        name = r['metric'].get('monitor_name', '?')
        host = r['metric'].get('monitor_hostname') or r['metric'].get('monitor_url') or '?'
        cat, sev = classify(name)
        by_cat.setdefault(cat, []).append((name, host, sev))

    for cat in ['CRITICAL', 'BRIDGE', 'CAMERA', 'SHELLY', 'TEMP', 'OTHER']:
        if cat in by_cat:
            print(f'CATEGORY:{cat}:{len(by_cat[cat])}')
            for name, host, sev in by_cat[cat][:10]:
                # sanitize colons in fields to keep downstream IFS=: parsing intact
                safe_name = name.replace(':', '-')
                safe_host = host.replace(':', '-')
                print(f'  DOWN:{sev}:{safe_name}:{safe_host}')
except Exception as e:
    print(f'parse_error: {e}')
" > /tmp/kuma_down.txt 2>/dev/null

        CRIT_CNT=$(grep -c "^  DOWN:major:" /tmp/kuma_down.txt 2>/dev/null; true)
        BRIDGE_CNT=$(grep -c "^  DOWN:minor:" /tmp/kuma_down.txt 2>/dev/null; true)
        INFO_CNT=$(grep -c "^  DOWN:info:" /tmp/kuma_down.txt 2>/dev/null; true)
        CRIT_CNT=${CRIT_CNT:-0}
        BRIDGE_CNT=${BRIDGE_CNT:-0}
        INFO_CNT=${INFO_CNT:-0}

        cat /tmp/kuma_down.txt
        echo ""

        if [ "${CRIT_CNT:-0}" -gt 0 ]; then
            while IFS=: read -r _ _ name host; do
                name="${name# }"
                add_major_issue "Kuma: $name down ($host)"
                log_warning "Critical device down: $name ($host)"
            done < <(grep "^  DOWN:major:" /tmp/kuma_down.txt)
        fi

        if [ "${BRIDGE_CNT:-0}" -gt 0 ]; then
            while IFS=: read -r _ _ name host; do
                name="${name# }"
                add_minor_issue "Kuma: $name down ($host)"
            done < <(grep "^  DOWN:minor:" /tmp/kuma_down.txt)
        fi

        if [ "${INFO_CNT:-0}" -gt 0 ]; then
            log_info "Kuma: $INFO_CNT Shelly/temp/other devices down (informational)"
        fi

        if [ "${CRIT_CNT:-0}" -eq 0 ] && [ "${BRIDGE_CNT:-0}" -eq 0 ] && [ "${INFO_CNT:-0}" -eq 0 ]; then
            log_success "All Kuma monitors healthy"
        fi
        rm -f /tmp/kuma_down.txt
    fi
    echo ""
} >> "$OUTPUT_FILE" 2>&1

echo "" | tee -a "$OUTPUT_FILE"
log_section "Issues Summary by Severity"

{
    echo "========================================="
    echo "ISSUES SUMMARY"
    echo "========================================="
    echo ""

    echo "🔴 CRITICAL ISSUES ($CRIT_COUNT):"
    if [ "$CRIT_COUNT" -eq 0 ]; then
        echo "  None - Excellent!"
    else
        for issue in "${CRITICAL_ISSUES_LIST[@]}"; do
            echo "  - $issue"
        done
    fi
    echo ""

    echo "🟡 MAJOR ISSUES ($MAJOR_COUNT):"
    if [ "$MAJOR_COUNT" -eq 0 ]; then
        echo "  None"
    else
        for issue in "${MAJOR_ISSUES_LIST[@]}"; do
            echo "  - $issue"
        done
    fi
    echo ""

    echo "🔵 MINOR ISSUES ($MINOR_COUNT):"
    if [ "$MINOR_COUNT" -eq 0 ]; then
        echo "  None"
    else
        for issue in "${MINOR_ISSUES_LIST[@]}"; do
            echo "  - $issue"
        done
    fi
    echo ""

    echo "========================================="
    echo "RECOMMENDATIONS"
    echo "========================================="
    echo ""

    if [ "$CRIT_COUNT" -gt 0 ]; then
        echo "⚠️  IMMEDIATE ACTION REQUIRED:"
        echo "   Address all critical issues immediately"
        echo ""
    fi

    if [ "$MAJOR_COUNT" -gt 0 ]; then
        echo "📋 HIGH PRIORITY:"
        echo "   Review and address major issues within 24-48 hours"
        echo ""
    fi

    if [ "$MINOR_COUNT" -gt 0 ]; then
        echo "📝 MONITOR:"
        echo "   Minor issues should be reviewed during regular maintenance"
        echo ""
    fi

    if [ "$CRIT_COUNT" -eq 0 ] && [ "$MAJOR_COUNT" -eq 0 ]; then
        echo "✅ CLUSTER STATUS: HEALTHY"
        echo "   No critical or major issues detected"
        echo "   Continue regular monitoring and maintenance"
        echo ""
    fi

} | tee -a "$OUTPUT_FILE" "$ISSUES_FILE"

#######################################
# Generate Final Summary
#######################################

echo "" | tee -a "$OUTPUT_FILE"
log_section "Health Check Summary"

{
    echo "========================================="
    echo "HEALTH CHECK SUMMARY"
    echo "========================================="
    echo "Date: $(date)"
    echo "Duration: N/A (full scan)"
    echo ""
    echo "Status Counts:"
    echo "  ✅ Checks Passed: $CHECKS_PASSED"
    echo "  ⚠️  Warnings: $WARNINGS"
    echo "  ❌ Critical Issues: $CRITICAL_ISSUES"
    echo "  ❌ Checks Failed: $CHECKS_FAILED"
    echo ""
    echo "Issue Breakdown:"
    echo "  🔴 Critical: $CRIT_COUNT"
    echo "  🟡 Major: $MAJOR_COUNT"
    echo "  🔵 Minor: $MINOR_COUNT"
    echo ""

    if [ "$CRIT_COUNT" -eq 0 ] && [ "$WARNINGS" -le 2 ]; then
        echo "Overall Health: 🟢 EXCELLENT"
    elif [ "$CRIT_COUNT" -eq 0 ] && [ "$WARNINGS" -le 5 ]; then
        echo "Overall Health: 🟡 GOOD"
    elif [ "$CRIT_COUNT" -le 2 ]; then
        echo "Overall Health: 🟠 WARNING"
    else
        echo "Overall Health: 🔴 CRITICAL"
    fi

    echo ""
    echo "Reports Generated:"
    echo "  - Full report: $OUTPUT_FILE"
    echo "  - Issues summary: $ISSUES_FILE"
    echo "========================================="
} | tee -a "$OUTPUT_FILE" "$SUMMARY_FILE"

# --- Drift vs prior run (only when --prev is set and file exists) ---
if [ -n "$PREV_FILE" ] && [ -f "$PREV_FILE" ]; then
    {
        echo ""
        echo "## Drift vs prior run"
        echo "Prior report: $PREV_FILE"
        echo ""

        # Helper: print " <metric>: <prev> → <now> (Δ <signed>)" or "no change",
        # or skip silently if either extraction failed.
        _drift_line() {
            local label="$1" prev="$2" now="$3"
            if [ -z "$prev" ] || [ -z "$now" ]; then
                return 0
            fi
            if [ "$prev" = "$now" ]; then
                printf '  %s: no change (%s)\n' "$label" "$now"
                return 0
            fi
            local delta
            delta=$(awk -v a="$prev" -v b="$now" 'BEGIN {
                d = b - a;
                if (d > 0) printf "+%g", d; else printf "%g", d;
            }' 2>/dev/null)
            printf '  %s: %s → %s (Δ %s)\n' "$label" "$prev" "$now" "$delta"
        }

        # --- Per-node CPU% (from "Prom node CPU (5m): nuc14-01:5.6%, ...") ---
        _extract_node_cpu() {
            local file="$1" node="$2"
            grep -E '^[[:space:]]*Prom node CPU' "$file" 2>/dev/null \
                | head -1 \
                | grep -oE "${node}:[0-9.]+%" \
                | head -1 \
                | sed -E "s/^${node}://;s/%$//"
        }
        for node in nuc14-01 nuc14-02 nuc14-03; do
            prev=$(_extract_node_cpu "$PREV_FILE" "$node")
            now=$(_extract_node_cpu "$OUTPUT_FILE" "$node")
            _drift_line "${node} cpu%" "$prev" "$now"
        done

        # --- Per-node mem% (from "Prom node memory: nuc14-01:48.4%, ...") ---
        _extract_node_mem() {
            local file="$1" node="$2"
            grep -E '^[[:space:]]*Prom node memory' "$file" 2>/dev/null \
                | head -1 \
                | grep -oE "${node}:[0-9.]+%" \
                | head -1 \
                | sed -E "s/^${node}://;s/%$//"
        }
        for node in nuc14-01 nuc14-02 nuc14-03; do
            prev=$(_extract_node_mem "$PREV_FILE" "$node")
            now=$(_extract_node_mem "$OUTPUT_FILE" "$node")
            _drift_line "${node} mem%" "$prev" "$now"
        done

        # --- Longhorn used % (100 - free%) per node/disk ---
        # Source line: "<node>/<disk>: <NN>% free (<X>Gi free of <Y>Gi)"
        _extract_lh_used_lines() {
            # Emit "<node>/<disk> <usedPct>" pairs.
            local file="$1"
            grep -E '^[A-Za-z0-9_-]+/[A-Za-z0-9_-]+: [0-9]+% free ' "$file" 2>/dev/null \
                | awk -F': ' '{
                    key = $1;
                    rest = $2;
                    n = split(rest, a, "%");
                    free = a[1] + 0;
                    used = 100 - free;
                    print key, used;
                }'
        }
        # Build key→used maps via temp files (bash 3.2 — no associative arrays).
        _LH_PREV=$(mktemp 2>/dev/null) || _LH_PREV=/tmp/_lh_prev.$$
        _LH_NOW=$(mktemp 2>/dev/null) || _LH_NOW=/tmp/_lh_now.$$
        _extract_lh_used_lines "$PREV_FILE"   > "$_LH_PREV" 2>/dev/null || true
        _extract_lh_used_lines "$OUTPUT_FILE" > "$_LH_NOW"  2>/dev/null || true
        # Iterate keys present in the new run; look up the prior value
        if [ -s "$_LH_NOW" ]; then
            while IFS=' ' read -r key now; do
                prev=$(awk -v k="$key" '$1 == k { print $2; exit }' "$_LH_PREV" 2>/dev/null)
                _drift_line "longhorn ${key} used%" "$prev" "$now"
            done < "$_LH_NOW"
        fi
        rm -f "$_LH_PREV" "$_LH_NOW" 2>/dev/null || true

        # --- Total restartCount (from "Total restartCount (cluster-wide): N") ---
        _extract_restart_total() {
            grep -E '^[[:space:]]*Total restartCount \(cluster-wide\):' "$1" 2>/dev/null \
                | head -1 \
                | sed -E 's/.*: *([0-9]+).*/\1/'
        }
        prev=$(_extract_restart_total "$PREV_FILE")
        now=$(_extract_restart_total "$OUTPUT_FILE")
        _drift_line "total restarts" "$prev" "$now"

        # --- Alert count (from "Firing alerts (excluding Watchdog): N") ---
        _extract_alert_count() {
            grep -E '^[[:space:]]*Firing alerts \(excluding Watchdog\):' "$1" 2>/dev/null \
                | head -1 \
                | sed -E 's/.*: *([0-9]+).*/\1/'
        }
        prev=$(_extract_alert_count "$PREV_FILE")
        now=$(_extract_alert_count "$OUTPUT_FILE")
        _drift_line "firing alerts" "$prev" "$now"

        echo ""
    } >> "$OUTPUT_FILE" 2>&1
fi

echo ""
echo -e "${GREEN}Health check complete!${NC}"
echo "Full report: $OUTPUT_FILE"
echo "Summary: $SUMMARY_FILE"
echo "Issues: $ISSUES_FILE"
echo ""
echo "Next steps:"
echo "  - Review full output: cat $OUTPUT_FILE"
echo "  - Check summary: cat $SUMMARY_FILE"
echo "  - Review issues: cat $ISSUES_FILE"
echo "  - Save snapshot: cp $SUMMARY_FILE runbooks/health-check-current.md"
