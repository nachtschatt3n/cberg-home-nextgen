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

# Allowlist of known-recurring noise (consumed by _noise_tag below).
# Sourced from the noise_suppressions table of sweep_history Postgres since
# Plan Phase 1.6. The dump_noise_yaml.py helper regenerates this tmp YAML
# at script startup so the existing bash grep logic is unchanged.
NOISE_ALLOWLIST="/tmp/noise_allowlist.yaml"
if [ -n "${SWEEP_PG_DSN:-}" ]; then
    if ! python3 "$SCRIPT_DIR/lib/dump_noise_yaml.py" "$NOISE_ALLOWLIST" 2>/dev/null; then
        echo "  ⚠ noise allowlist dump failed; tagging will be skipped" >&2
        # Legacy fallback: if the source YAML is still in repo (Phase 1↔2),
        # use it directly so the bash logic still has something to grep.
        [ -f "$SCRIPT_DIR/noise_allowlist.yaml" ] && \
            NOISE_ALLOWLIST="$SCRIPT_DIR/noise_allowlist.yaml"
    fi
else
    # No DSN → legacy YAML path. Removed in Plan Phase 2 when the source
    # file is deleted from git.
    [ -f "$SCRIPT_DIR/noise_allowlist.yaml" ] && \
        NOISE_ALLOWLIST="$SCRIPT_DIR/noise_allowlist.yaml"
fi

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
# Register of measurements that could not be taken. FILE-backed on purpose:
# safe_count is almost always invoked as `VAR=$(safe_count ...)`, which runs in
# a SUBSHELL, so appending to MAJOR_ISSUES_LIST from in there would be silently
# discarded when the subshell exits. A file append survives. Drained into real
# findings by report_unmeasured() from the main shell.
UNMEASURED_LOG="${TMPDIR:-/tmp}/_hc_unmeasured.$$"
: > "$UNMEASURED_LOG" 2>/dev/null || true

_record_unmeasured() {   # label, reason  — subshell-safe
    printf '%s\t%s\n' "$1" "$2" >> "$UNMEASURED_LOG" 2>/dev/null || true
}

# safe_count CMD [LABEL] [FLOOR]
#
# Counts something, and — unlike the version this replaces — can tell a
# measurement of zero apart from a measurement that did not happen.
#
# The old body was `eval "$1" 2>/dev/null | head -1 || echo "0"`, which returns
# 0 for a genuine zero, a missing binary, an unreachable cluster and a failed
# query alike. Verified: `echo 0`, `kubectl-does-not-exist ... | wc -l`, `false`
# and an unreachable kubeconfig all produced exactly "0". 57 call sites, and
# every silent-green defect in docs/sops/audit-script-correctness.md is a
# variation on that collapse. `|| echo "0"` inside the caller cannot help
# either: in `kubectl ... | wc -l` the pipeline's status is wc's, and wc happily
# succeeds while printing 0.
#
# The real status is recovered with PIPESTATUS[0] evaluated INSIDE the eval, so
# it refers to the head of the caller's pipeline rather than to eval itself.
#
# FLOOR is the denominator control: pass it when a zero is impossible in a
# working cluster (there ARE certificates, HelmReleases, flux controllers). A
# count below the floor is recorded as unmeasured even when the command exited 0
# — that is exactly how the Longhorn disk-capacity check, which had queried a
# path holding no data since it was written, was finally caught.
#
# Returns the count. A failed measurement still returns its numeric fallback so
# the 57 existing guards keep their arithmetic and cannot be broken by this
# change; the difference is that the run can no longer be reported clean,
# because report_unmeasured() raises a MAJOR issue naming what did not run.
safe_count() {
    local cmd="$1" label="${2:-}" floor="${3:-}"
    local out rc result
    out=$(eval "$cmd"'; printf "\n__RC:%s" "${PIPESTATUS[0]}"' 2>/dev/null)
    rc="${out##*__RC:}"
    out="${out%$'\n'__RC:*}"
    result=$(printf '%s' "$out" | head -1 | tr -cd '0-9')
    [ -z "$result" ] && result="0"

    if [ "${rc:-1}" != "0" ]; then
        _record_unmeasured "${label:-$cmd}" "command failed (rc=${rc:-?})"
    elif [ -n "$floor" ] && [ "$result" -lt "$floor" ] 2>/dev/null; then
        _record_unmeasured "${label:-$cmd}" \
            "returned $result, below the floor of $floor expected in a working cluster"
    fi
    echo "$result"
}

# Drain the register into findings. MUST run in the main shell.
report_unmeasured() {
    [ -s "$UNMEASURED_LOG" ] || return 0
    local label reason n=0
    while IFS=$'\t' read -r label reason; do
        [ -n "$label" ] || continue
        n=$((n+1))
        log_warning "NOT MEASURED — ${label}: ${reason}"
        add_major_issue "Measurement did not run — ${label}: ${reason} (a count that could not be taken is not a count of zero)"
    done < <(sort -u "$UNMEASURED_LOG")
    [ "$n" -gt 0 ] && log_warning "$n measurement(s) did not run; their assertions cannot be treated as clean"
    rm -f "$UNMEASURED_LOG" 2>/dev/null || true
}

# Authoritative backup-freshness signal, judged PER VOLUME. For each Longhorn
# volume the freshest evidence wins: the newest Completed Backup CR carrying
# its backup-volume label OR volume.status.lastBackupAt — whichever is newer.
# Why: under parallel backup load the CIFS backup store's volume.cfg rewrite
# can be lost, so lastBackupAt lags a full backup cycle even though the
# Backup CR Completed; the status only self-corrects at the NEXT backup.
# Judging from lastBackupAt alone therefore produces false "stale backup"
# findings (2026-08-18: 16/93 volumes lagged a day). See docs/sops/backup.md.
# Default output: age in whole hours of the STALEST volume's freshest signal
# (any volume without a recent backup drives the number up), or "NONE" if no
# volume has any backup evidence at all. Used when the backup Job object has
# been TTL-reaped (expected after a successful run) so absence of the Job
# doesn't read as "no backups". With --per-volume, prints one line per volume
# instead: "<volume> <age>h <FRESH|STALE> (<source>)" against a 25h cutoff —
# for standalone verification.
longhorn_backup_age_hours() {
    local mode="${1:-}"
    { kubectl get volumes -n storage -o json 2>/dev/null; \
      kubectl get backups -n storage -o json 2>/dev/null; } | python3 -c "
import sys, json, datetime
mode = '$mode'
raw = sys.stdin.read()
dec = json.JSONDecoder()
docs, idx = [], 0
try:
    while idx < len(raw):
        while idx < len(raw) and raw[idx].isspace():
            idx += 1
        if idx >= len(raw):
            break
        obj, idx = dec.raw_decode(raw, idx)
        docs.append(obj)
except Exception:
    pass
vols = docs[0].get('items', []) if len(docs) > 0 else []
backups = docs[1].get('items', []) if len(docs) > 1 else []
now = datetime.datetime.now(datetime.timezone.utc)
def age_h(ts):
    t = datetime.datetime.fromisoformat(ts.rstrip('Z')).replace(tzinfo=datetime.timezone.utc)
    return (now - t).total_seconds() / 3600.0
newest_cr = {}
for b in backups:
    if b.get('status', {}).get('state') != 'Completed':
        continue
    vol = b.get('metadata', {}).get('labels', {}).get('backup-volume')
    ts = b.get('metadata', {}).get('creationTimestamp')
    if not vol or not ts:
        continue
    if ts > newest_cr.get(vol, ''):
        newest_cr[vol] = ts
rows = []
idle = []
for v in vols:
    name = v.get('metadata', {}).get('name', '')
    cands = []
    if name in newest_cr:
        cands.append((age_h(newest_cr[name]), 'backup-cr'))
    lb = v.get('status', {}).get('lastBackupAt')
    if lb:
        cands.append((age_h(lb), 'lastBackupAt'))
    if not cands:
        continue
    # A DETACHED volume's content cannot change, so however old its newest
    # backup is, that backup still captures everything in it -- staleness is
    # not data risk there. Counting them in the stalest-volume max() made the
    # deliberate rollback volumes (detached since a migration) read as a
    # backup failure. Reported separately rather than hidden.
    if v.get('status', {}).get('state') == 'attached':
        rows.append((name,) + min(cands))
    else:
        idle.append((name,) + min(cands))
if not rows and not idle:
    print('NONE'); sys.exit()
if mode == '--per-volume':
    for name, a, srcname in sorted(rows, key=lambda r: -r[1]):
        print(f'{name} {int(a)}h ' + ('FRESH' if a < 25 else 'STALE') + f' ({srcname})')
    for name, a, srcname in sorted(idle, key=lambda r: -r[1]):
        print(f'{name} {int(a)}h IDLE-DETACHED ({srcname})')
elif mode == '--idle-stale-count':
    print(sum(1 for _n, a, _s in idle if a > 48))
elif not rows:
    print('NONE')
else:
    print(int(max(r[1] for r in rows)))
" 2>/dev/null || echo "NONE"
}

# Verdict on backup health. The PER-VOLUME Longhorn age is AUTHORITATIVE and is
# ALWAYS evaluated; the backup Job is CONTEXT ONLY.
# Why: the daily-backup Job exits 0 once it has DISPATCHED backups, not once
# every volume actually has a fresh one. Until 2026-08-22 a present, succeeded
# Job short-circuited straight to "Backup system operational" with no age
# assertion at all (and a second copy of this block derived the age from the
# Job's completionTime), so a volume that had not backed up for a week was
# invisible whenever the Job object happened to still be inside its TTL. The
# Job now only refines the wording; it can no longer manufacture a pass.
assess_backup_freshness() {
    local job="$1"
    local age idle jobnote status
    age=$(longhorn_backup_age_hours)
    idle=$(longhorn_backup_age_hours --idle-stale-count)

    if [ -n "$job" ]; then
        status=$(kubectl get job -n storage "$job" -o jsonpath='{.status.succeeded}' 2>/dev/null || echo "0")
        if [ "$status" == "1" ]; then
            jobnote="job $job succeeded"
        else
            jobnote="job $job NOT succeeded (succeeded=$status)"
            log_warning "Backup job status unclear: $status"
            add_minor_issue "Backup job status unclear"
        fi
    else
        # Absence is EXPECTED: successful backup Jobs are TTL-reaped.
        jobnote="job TTL-reaped"
    fi

    # Detached volumes are excluded from the age above on purpose: their content
    # cannot change, so an old backup still captures all of it. Reported, never
    # silently dropped.
    if [ "$idle" != "0" ] && [ -n "$idle" ]; then
        echo "Note: $idle detached volume(s) have backups older than 48h - content frozen, not a data risk (see --per-volume)"
    fi

    if [ "$age" == "NONE" ]; then
        log_warning "No Longhorn backup evidence on any volume ($jobnote)"
        add_major_issue "Backup evidence absent: no Backup CR or lastBackupAt on any Longhorn volume ($jobnote)"
    elif [ "$age" -gt 48 ]; then
        log_warning "Stalest attached Longhorn volume's newest backup is ${age}h old ($jobnote)"
        add_major_issue "Backup stale: stalest ATTACHED Longhorn volume's newest backup evidence (Backup CR / lastBackupAt) was ${age}h ago (expected daily; $jobnote)"
    else
        log_success "Backups fresh - stalest attached volume ${age}h ago ($jobnote)"
    fi
}

# check_icloud_instance <deployment-name>
# Health for ONE icloud-docker-* instance in the `backup` namespace. Called once
# per instance discovered in Section 16, so adding a third Apple ID needs no
# change here.
#
# Finding titles (add_minor_issue) MUST keep the instance name as the leading
# token: runbooks/health-check.py routes them into the `icloud_docker`
# subsection by prefix, and accepted-risk / noise needles substring-match on
# them. For icloud-docker-mu the strings produced are byte-identical to the
# pre-2026-08-08 single-instance version.
check_icloud_instance() {
    local app="$1"
    local pod phase restarts log_errors auth_errors

    echo ""
    echo "iCloud sync ($app):"
    pod=$(kubectl get pods -n backup -l "app.kubernetes.io/name=$app" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -z "$pod" ]; then
        echo "  iCloud sync pod not found (namespace: backup, app: $app)"
        return 0
    fi

    phase=$(kubectl get pod -n backup "$pod" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
    restarts=$(kubectl get pod -n backup "$pod" -o jsonpath='{.status.containerStatuses[0].restartCount}' 2>/dev/null || echo "0")
    echo "  iCloud pod: $pod, phase: $phase, restarts: $restarts"

    if [ "$phase" != "Running" ]; then
        log_warning "iCloud sync pod is not running ($app, phase: $phase)"
        add_minor_issue "$app pod not running (phase: $phase)"
        return 0
    fi

    # Filter out known-benign, recurring noise so the count reflects REAL
    # problems (tightened 2026-07-08 — was flagging ~78/24h of pure noise):
    #  - Apple API flakiness (throttles, CF 5xx, PCS cookie refresh)
    #  - INFO progress summaries that merely contain "failed"
    #    ("N successful, M failed") — these are not errors
    #  - Apple "package" bundles (.numbers/.app) icloud-docker can't unpack,
    #    plus per-file package-type probes — benign tool limitations
    # Scope to last 24h; icloud-docker has sparse logs.
    log_errors=$(safe_count "kubectl logs -n backup '$pod' --since=24h 2>/dev/null | grep -iE '(error|ERROR|failed|FAILED)' | grep -viE '410|429|503|530|throttl|retry|connection reset|rate limit|PCS_KEY|cookie pcs|successful, [0-9]+ failed|cannot unpack the package|unhandled file type|check package type' | wc -l" "log-errors")
    echo "  iCloud log errors (last 24h, filtered): $log_errors"

    # Auth/session errors are the ones that actually need operator action
    # (interactive re-auth per docs/sops/icloud-docker-reauth.md). Count
    # them SEPARATELY and NEVER filter them, anchored to real signatures.
    # Use [(]421[)] not a bare 421 — a bare 421 matches the ',421' in a
    # millisecond timestamp (false positive). This dedicated check means a
    # genuine session expiry is always surfaced with a clear "re-auth"
    # title even when the generic filtered count is quiet, and must never
    # be swallowed by a broad accepted-risk needle.
    auth_errors=$(safe_count "kubectl logs -n backup '$pod' --since=24h 2>/dev/null | grep -icE 'authentication required for account|[(]421[)]|2fa is required|2fa.*please|please log in|session (has )?expired|invalid session|missing.*bearer token'" "auth-errors")
    echo "  iCloud auth/session errors (last 24h): $auth_errors"

    if [ "$auth_errors" -gt 0 ]; then
        log_warning "iCloud session/auth errors ($app) — re-auth likely needed: $auth_errors"
        add_minor_issue "$app auth/session errors (re-auth needed): $auth_errors"
    elif [ "$log_errors" -gt 25 ]; then
        log_warning "iCloud sync pod has elevated errors in recent logs ($app): $log_errors"
        add_minor_issue "$app recent log errors: $log_errors"
    else
        log_success "iCloud sync pod running ($app, restarts: $restarts)"
    fi
    return 0
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

# Extract "integration:" pattern values from the known_ha_error_sources
# section of NOISE_ALLOWLIST (DB-backed via `policy-cli.py noise add`).
# _noise_tag() (below) only ANNOTATES matched alert/stale-pod/battery lines —
# it never touches HA_ERRORS/RESMED_ERRORS etc. Those counters filter
# exclusively via the hardcoded HA_FALSE_POSITIVES array, so an operator
# adding a `known_ha_error_sources` row (e.g. resmed_myair, miele) had zero
# effect on the actual error count — confirmed 2026-07-05. This wires the DB
# entries into filter_ha_false_positives so `noise add` takes effect without
# a manual HA_FALSE_POSITIVES edit + code deploy.
ha_noise_patterns_from_db() {
    [ -f "$NOISE_ALLOWLIST" ] || return 0
    awk '/^known_ha_error_sources:/{f=1; next} /^[^ ]/{f=0} f' "$NOISE_ALLOWLIST" 2>/dev/null \
        | grep -oE 'integration:[[:space:]]*"[^"]+"' \
        | sed -E 's/^integration:[[:space:]]*"//; s/"$//'
}

# Filter out false positives from piped input
# Usage: echo "$LOGS" | filter_ha_false_positives
filter_ha_false_positives() {
    local exclude
    local db_patterns
    db_patterns=$(ha_noise_patterns_from_db)
    if [ -n "$db_patterns" ]; then
        exclude=$(build_grep_exclude "${HA_FALSE_POSITIVES[@]}" $db_patterns)
    else
        exclude=$(build_grep_exclude "${HA_FALSE_POSITIVES[@]}")
    fi
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
    WARNING_COUNT=$(safe_count "kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | grep -v 'NAMESPACE' | grep -vE '($K8S_EXCLUDE)' | wc -l" "warning-count")
    echo "Warning events: $WARNING_COUNT"

    OOM_COUNT=$(safe_count "kubectl get events -A --field-selector reason=OOMKilled 2>/dev/null | grep -v 'NAMESPACE' | wc -l" "oom-count")
    OOM_COUNT=$((10#${OOM_COUNT:-0}))   # strip leading zeros: "010" must not parse as octal
    echo "OOM kills (events reason=OOMKilled): $OOM_COUNT"

    # Second authoritative control. Events age out of etcd, so a pod that was
    # OOMKilled hours ago can have no surviving event while its containerStatus
    # still records it. Neither control is a log line -- OOMKilled is a pod-status
    # reason and NEVER appears in log text, which is why grepping logs for it
    # always returns 0 and proves nothing.
    OOM_LASTSTATE=$(kubectl get pods -A -o json 2>/dev/null | python3 -c "
import sys, json
n = 0
try:
    for p in json.load(sys.stdin).get('items', []):
        for cs in (p.get('status', {}).get('containerStatuses') or []):
            if (cs.get('lastState', {}).get('terminated', {}) or {}).get('reason') == 'OOMKilled':
                n += 1
                print('  OOMKilled lastState: %s/%s [%s]' % (p['metadata']['namespace'], p['metadata']['name'], cs['name']))
except Exception:
    pass
print(n)
" 2>/dev/null || echo "0")
    echo "$OOM_LASTSTATE" | sed '$d'
    OOM_LASTSTATE=$(echo "$OOM_LASTSTATE" | tail -1 | tr -cd '0-9'); [ -z "$OOM_LASTSTATE" ] && OOM_LASTSTATE=0
    OOM_LASTSTATE=$((10#$OOM_LASTSTATE))
    echo "OOM kills (pods with OOMKilled lastState): $OOM_LASTSTATE"

    # Third control, added 2026-08-18: OOMKilled lastState RESTRICTED TO THE LAST
    # 24 HOURS, so it is window-aligned with the 24h Elasticsearch OOM_TEXT query
    # in Section 34.
    #
    # WHY: Section 34's CRITICAL OOM branch corroborates ES log text against a
    # pod-state control, but the two were measuring different windows.
    #   OOM_COUNT     - kubectl events, which age out of etcd after ~1h
    #   OOM_TEXT      - Elasticsearch, 24h
    #   OOM_LASTSTATE - unbounded, but only for pods that still EXIST
    # A real OOM 3 hours ago whose pod has since been replaced left the event
    # expired and no surviving lastState, so a genuine 24h OOM could only ever
    # reach MINOR. Comparing a 1h control against a 24h query is the same
    # window-mismatch defect class as the thresholds fixed in 83d97de0.
    # lastState.terminated.finishedAt is the OOM's own timestamp and survives as
    # long as the pod object does, so it gives a control on exactly the ES window.
    OOM_LASTSTATE_24H=$(kubectl get pods -A -o json 2>/dev/null | python3 -c "
import sys, json
from datetime import datetime, timedelta, timezone
cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
n = 0
try:
    for p in json.load(sys.stdin).get('items', []):
        for cs in (p.get('status', {}).get('containerStatuses') or []):
            t = (cs.get('lastState', {}).get('terminated', {}) or {})
            if t.get('reason') != 'OOMKilled':
                continue
            fin = t.get('finishedAt')
            if not fin:
                continue
            try:
                when = datetime.fromisoformat(fin.replace('Z', '+00:00'))
            except Exception:
                continue
            if when >= cutoff:
                n += 1
except Exception:
    pass
print(n)
" 2>/dev/null || echo "0")
    OOM_LASTSTATE_24H=$(echo "$OOM_LASTSTATE_24H" | tail -1 | tr -cd '0-9'); [ -z "$OOM_LASTSTATE_24H" ] && OOM_LASTSTATE_24H=0
    OOM_LASTSTATE_24H=$((10#$OOM_LASTSTATE_24H))
    echo "OOM kills (OOMKilled lastState finished within 24h): $OOM_LASTSTATE_24H"

    EVICTED_COUNT=$(safe_count "kubectl get events -A --field-selector reason=Evicted 2>/dev/null | grep -v 'NAMESPACE' | wc -l" "evicted-count")
    # Same `|| echo 0` append trap as OOM_COUNT above: safe_count can emit "00".
    EVICTED_COUNT=$(echo "$EVICTED_COUNT" | tail -1 | tr -cd '0-9'); [ -z "$EVICTED_COUNT" ] && EVICTED_COUNT=0
    EVICTED_COUNT=$((10#$EVICTED_COUNT))
    echo "Pod evictions: $EVICTED_COUNT"

    if [ "$WARNING_COUNT" -gt 10 ]; then
        log_warning "High warning count: $WARNING_COUNT events"
        add_minor_issue "High warning event count: $WARNING_COUNT"
    elif [ "$WARNING_COUNT" -gt 0 ]; then
        log_info "Warning events: $WARNING_COUNT"
    else
        log_success "No warning events"
    fi

    if [ "$OOM_COUNT" -gt 0 ] || [ "$OOM_LASTSTATE" -gt 0 ]; then
        log_critical "OOM kills detected: $OOM_COUNT event(s), $OOM_LASTSTATE pod(s) with OOMKilled lastState"
        add_critical_issue "OOM kills detected: $OOM_COUNT event(s), $OOM_LASTSTATE pod(s) with OOMKilled lastState"
    else
        log_success "No OOM kills (events=0, lastState=0, lastState within 24h=$OOM_LASTSTATE_24H)"
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

    # Count only GENUINELY failed jobs (a Failed condition set True). The old
    # `grep '0/1'` also matched in-flight/running jobs (0 completions so far)
    # and TTL-reaped ones, producing false "Failed jobs: 1" warnings.
    FAILED_JOBS=$(kubectl get jobs -A -o json 2>/dev/null | python3 -c "
import sys, json
try:
    items = json.load(sys.stdin).get('items', [])
except Exception:
    print(0); sys.exit()
print(sum(1 for j in items
          if any(c.get('type') == 'Failed' and c.get('status') == 'True'
                 for c in (j.get('status', {}).get('conditions') or []))))
" 2>/dev/null || echo 0)
    echo "Failed jobs (Failed condition): $FAILED_JOBS"

    # Check backup job. Filter ALL storage jobs by the backup name (newest
    # first) — the old code grepped only the single most-recent storage job, so
    # an in-flight trim job made it miss the backup and warn "no backup jobs".
    BACKUP_JOB=$(kubectl get jobs -n storage -o json 2>/dev/null | python3 -c "
import sys, json
try:
    items = json.load(sys.stdin).get('items', [])
except Exception:
    print(''); sys.exit()
b = [j for j in items if j['metadata']['name'].startswith('daily-backup-all-volumes')]
b.sort(key=lambda j: j['metadata'].get('creationTimestamp', ''), reverse=True)
print(b[0]['metadata']['name'] if b else '')
" 2>/dev/null || echo "")
    if [ -n "$BACKUP_JOB" ]; then
        BACKUP_TIME=$(kubectl get job -n storage "$BACKUP_JOB" -o jsonpath='{.status.completionTime}' 2>/dev/null || echo "Not completed")
        echo "Last backup job: $BACKUP_JOB (Time: $BACKUP_TIME)"
    fi
    assess_backup_freshness "$BACKUP_JOB"

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

    TOTAL_CERTS=$(safe_count "kubectl get certificates -A --no-headers 2>/dev/null | wc -l" "total-certs" 1)
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
        EXPIRY_COUNT=$(echo "$EXPIRING_SOON" | grep -c "/" || true)
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

    TOTAL_HELM=$(safe_count "flux get helmreleases -A 2>/dev/null | grep -v 'NAMESPACE' | wc -l" "total-helm" 1)
    FAILED_HELM=$(safe_count "flux get helmreleases -A 2>/dev/null | grep -E '(Failed|Error|Unknown)' | wc -l" "failed-helm")

    echo "HelmReleases: $((TOTAL_HELM - FAILED_HELM))/$TOTAL_HELM ready"

    echo ""
    echo "HelmRepositories:"
    flux get sources helm -A | head -30
    echo ""

    # Check for failed HelmRepositories (READY column = False)
    FAILED_HELMREPOS=$(safe_count "flux get sources helm -A 2>/dev/null | awk '\$5 == \"False\"' | wc -l" "failed-helmrepos")
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

    TOTAL_KUST=$(safe_count "flux get kustomizations -A 2>/dev/null | grep -v 'NAMESPACE' | wc -l" "total-kust" 1)
    # Count kustomizations where READY column (col 5) is not True — resilient to mid-reconciliation message changes
    # Count DISTINCT not-Ready kustomizations from the API, not table lines: a
    # single failing kustomization wraps its multi-line MESSAGE (e.g. a SOPS
    # decryption stack trace) across ~12 table rows, and `awk '$5 != "True"'`
    # counted each wrapped row as a separate "not reconciled" entry (false 12).
    NOT_RECONCILED=$(safe_count "kubectl get kustomizations -A -o json 2>/dev/null | jq -r '[.items[] | select(.status.conditions[]? | select(.type==\"Ready\" and .status!=\"True\"))] | length'" "not-reconciled")

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
            DEPENDENCY_STUCK=$(flux get kustomizations -A 2>/dev/null | grep -c "dependency.*not ready" || true)
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
    NON_RUNNING=$(safe_count "kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded --no-headers 2>/dev/null | wc -l" "non-running")
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

    CRASH_LOOP=$(safe_count "kubectl get pods -A 2>/dev/null | grep -c 'CrashLoopBackOff'" "crash-loop")
    PENDING=$(safe_count "kubectl get pods -A 2>/dev/null | grep -c 'Pending'" "pending")

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

    # Blackbox synthetic probes (added 2026-08-15, N-15). The DNS/ingress SLI.
    # Deliberately asserts on the PROBE RESULT, not on the exporter's pod state:
    # on 2026-08-15 internal DNS SERVFAILed every name twice while Flux was green
    # and every pod was Running, so anything derived from pod/controller health
    # still read 100%. The Alertmanager rules page on this, but without an
    # assertion here a probe that fails BETWEEN sweeps leaves no trace in
    # health-check-current.md.
    PROBE_DOWN=$(prom_query 'probe_success == 0')
    PROBE_ANY=$(prom_query 'probe_success')
    PROBE_DOWN_SUMMARY=$(echo "$PROBE_DOWN" | python3 -c "
import sys, json
try:
    r = json.load(sys.stdin)['data']['result']
    if r:
        print(', '.join(f\"{x['metric'].get('probe_component','?')}({x['metric'].get('probe_class','?')})\" for x in r))
except: pass
" 2>/dev/null)
    PROBE_COUNT=$(echo "$PROBE_ANY" | python3 -c "
import sys, json
try: print(len(json.load(sys.stdin)['data']['result']))
except: print(0)
" 2>/dev/null)
    PROBE_COUNT=${PROBE_COUNT:-0}
    if [ -n "$PROBE_DOWN_SUMMARY" ]; then
        log_critical "Blackbox probe(s) FAILING: $PROBE_DOWN_SUMMARY — internal DNS or ingress is not serving valid answers"
        add_critical_issue "Blackbox probe failure: $PROBE_DOWN_SUMMARY (SOP: k8s-gateway-dns.md / monitoring.md 'Blackbox Exporter')"
    elif [ "$PROBE_COUNT" -eq 0 ]; then
        # absent(probe_success) — the SLI is SILENT, which reads as 100% in the
        # SLO calculator. This is the exact blind spot N-15 was opened for.
        log_warning "Blackbox probe results ABSENT — the DNS/ingress SLI is blind (SLOs will read 100%)"
        add_minor_issue "Blackbox probe_success absent — DNS/ingress SLI blind (SOP: monitoring.md 'Blackbox Exporter')"
    else
        log_success "Blackbox probes healthy ($PROBE_COUNT probe(s) returning valid answers)"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 9: Alertmanager Alerts"
{
    echo "Checking alerts via Alertmanager API..."
    echo ""

    # Source the count from Alertmanager (not Prometheus): Alertmanager is the
    # only component that knows about silences/inhibitions. A silenced alert is
    # still "firing" in Prometheus /api/v1/alerts but is state="suppressed" in
    # Alertmanager — counting from Prometheus produced false-positive findings
    # for alerts an operator had already acknowledged via an AM silence (AR-044).
    kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 > /dev/null 2>&1 &
    PF_PID=$!
    sleep 3

    ALERT_CHECK=$(curl -s 'http://localhost:9093/api/v2/alerts' 2>/dev/null || echo 'ERROR')

    # Parse with python3, not jq: Alertmanager annotations can carry raw control
    # characters (e.g. the Watchdog description) that jq rejects as invalid JSON
    # but python3 tolerates — and CLAUDE.md mandates python over jq in pipes.
    if printf '%s' "$ALERT_CHECK" | python3 -c "import sys,json; sys.exit(0 if isinstance(json.load(sys.stdin),list) else 1)" 2>/dev/null; then
        echo "Alert data retrieved successfully"
        echo ""

        # Active = not silenced and not inhibited (suppressed alerts are excluded
        # by Alertmanager's own per-alert .status.state). Watchdog/InfoInhibitor
        # are meta-alerts and never actionable.
        SUPPRESSED_COUNT=$(printf '%s' "$ALERT_CHECK" | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(1 for a in d if a.get('status',{}).get('state')=='suppressed'))")
        FIRING_ALERTS=$(printf '%s' "$ALERT_CHECK" | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(1 for a in d if a.get('status',{}).get('state')=='active' and a['labels'].get('alertname') not in ('Watchdog','InfoInhibitor')))")

        echo "Suppressed (silenced/inhibited, excluded): $SUPPRESSED_COUNT"
        echo "Active alerts firing (excluding Watchdog): $FIRING_ALERTS"
        echo ""

        if [ "$FIRING_ALERTS" -gt 0 ]; then
            echo "Active Alerts:"
            # Tag each alert with [noise: ...] when it matches noise_allowlist.yaml
            # (alertname + namespace are included in the line so substring match works).
            printf '%s' "$ALERT_CHECK" | python3 -c "
import sys, json
for a in json.load(sys.stdin):
    if a.get('status', {}).get('state') == 'active' and a['labels'].get('alertname') not in ('Watchdog', 'InfoInhibitor'):
        l = a['labels']; an = a.get('annotations', {})
        print('  - {} [ns={}] ({}): {}'.format(
            l.get('alertname'), l.get('namespace', '?'),
            l.get('severity', 'unknown'),
            (an.get('summary') or an.get('description') or 'No description').replace(chr(10), ' ')))
" | head -20 \
                | while IFS= read -r _alert_line; do
                    tag=$(_noise_tag "$_alert_line")
                    printf '%s%s\n' "$_alert_line" "$tag"
                done

            log_warning "Active alerts firing: $FIRING_ALERTS"
            add_major_issue "Prometheus alerts firing: $FIRING_ALERTS"
        else
            log_success "No active (non-silenced) alerts firing"
        fi
    else
        log_warning "Unable to retrieve alert data from Alertmanager"
        add_minor_issue "Could not check Alertmanager alerts"
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

    TOTAL_VOLUMES=$(safe_count "kubectl get volumes -n storage --no-headers 2>/dev/null | wc -l" "total-volumes" 1)
    # A DETACHED volume is idle, not unhealthy: Longhorn reports
    # robustness=unknown for every detached volume, so the old
    # `state != attached OR robustness != healthy` test flagged each
    # intentionally-unmounted volume (bitnamilegacy migration rollback PVs,
    # scaled-to-zero apps) as a storage failure. Real replica damage is
    # degraded/faulted and is still caught while detached; an unexpected
    # detach is caught by DETACH_EVENTS below and by pod-level assertions.
    UNHEALTHY_VOLUMES=$(kubectl get volumes -n storage -o json 2>/dev/null | jq '[.items[] | select((.status.robustness == "degraded" or .status.robustness == "faulted") or (.status.state == "attached" and .status.robustness != "healthy"))] | length')
    # Per-volume detail so each unhealthy volume becomes its own finding with
    # the volume name in the title — lets an accepted-risk match a specific
    # volume (e.g. an intentionally scaled-down app's detached session PVC)
    # without masking an unrelated real failure on a different volume.
    UNHEALTHY_DETAIL=$(kubectl get volumes -n storage -o json 2>/dev/null | jq -r '.items[] | select((.status.robustness == "degraded" or .status.robustness == "faulted") or (.status.state == "attached" and .status.robustness != "healthy")) | "\(.metadata.name): state=\(.status.state) robustness=\(.status.robustness)"')

    echo "Volumes: $((TOTAL_VOLUMES - UNHEALTHY_VOLUMES))/$TOTAL_VOLUMES healthy"

    if [ "$UNHEALTHY_VOLUMES" -gt 0 ]; then
        echo "Unhealthy volumes:"
        kubectl get volumes -n storage -o json | jq -r '.items[] | select((.status.robustness == "degraded" or .status.robustness == "faulted") or (.status.state == "attached" and .status.robustness != "healthy")) | "\(.metadata.name): state=\(.status.state) robustness=\(.status.robustness)"'
    fi

    echo ""
    echo "PVC status:"
    PENDING_PVC=$(safe_count "kubectl get pvc -A 2>/dev/null | grep -E '(Pending|Lost|Unknown)' | wc -l" "pending-pvc")
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
        select(.status.robustness == "degraded" or .status.robustness == "faulted") |
        "\(.metadata.name): robustness=\(.status.robustness) state=\(.status.state)"
    ' || echo "")
    if [ -n "$REPLICA_MISMATCHES" ]; then
        echo "$REPLICA_MISMATCHES"
        MISMATCH_COUNT=$(echo "$REPLICA_MISMATCHES" | grep -c "robustness=" || true)
        echo "Total volumes with unhealthy robustness: $MISMATCH_COUNT"
    else
        echo "None"
    fi
    echo ""

    # Check for recent unexpected volume detachment events (last 24h)
    DETACH_EVENTS=$(safe_count "kubectl get events -n storage --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | grep -i 'DetachedUnexpectedly' | wc -l" "detach-events")
    echo "Unexpected volume detachment events (recent): $DETACH_EVENTS"

    # Check for Flux/Longhorn admission webhook conflicts
    ADMISSION_CONFLICTS=$(safe_count "kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | grep -i 'admission webhook.*longhorn.*denied' | wc -l" "admission-conflicts")
    echo "Longhorn admission webhook conflicts: $ADMISSION_CONFLICTS"

    if [ "$UNHEALTHY_VOLUMES" -eq 0 ] && [ "$PENDING_PVC" -eq 0 ] && [ "$AUTO_DELETE" == "false" ] && [ -z "$REPLICA_MISMATCHES" ]; then
        log_success "Longhorn storage healthy"
    else
        log_warning "Storage issues - Unhealthy volumes: $UNHEALTHY_VOLUMES, Pending PVCs: $PENDING_PVC, AutoDelete: $AUTO_DELETE"
        if [ "$UNHEALTHY_VOLUMES" -gt 0 ]; then
            while IFS= read -r vline; do
                [ -n "$vline" ] && add_major_issue "Unhealthy Longhorn volume: $vline"
            done <<< "$UNHEALTHY_DETAIL"
        fi
        if [ "$PENDING_PVC" -gt 0 ]; then
            add_major_issue "Pending PVCs: $PENDING_PVC"
        fi
        if [ "$AUTO_DELETE" != "false" ]; then
            add_minor_issue "AutoDelete setting is $AUTO_DELETE (should be false)"
        fi
        # No finding emitted here: REPLICA_MISMATCHES (degraded/faulted) is a
        # strict subset of UNHEALTHY_DETAIL above, so emitting it again produced
        # two findings per volume - one major, one minor - for one condition.
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
    # storageMaximum / storageAvailable live under .status.diskStatus. Until
    # 2026-08-22 all four queries here read .spec.disks, which carries only
    # allowScheduling / path / storageReserved and has NEVER had those fields —
    # so `select(.value.storageMaximum > 0)` matched nothing, the capacity table
    # printed empty, and both threshold counts were 0 on every run. The chain
    # below therefore reported "Longhorn disk capacity healthy" unconditionally:
    # a green verdict no disk state could ever change. Real usage when this was
    # found was 32-48% free, so nothing was hiding behind it, but node storage
    # exhaustion was entirely unmonitored here.
    echo "Longhorn node disk capacity:"
    kubectl get nodes.longhorn.io -n storage -o json 2>/dev/null | jq -r '
        .items[] | .metadata.name as $node |
        (.status.diskStatus // {}) | to_entries[] |
        select(.value.storageMaximum > 0) |
        "\($node)/\(.key): \((.value.storageAvailable / .value.storageMaximum * 100 | floor))% free (\(.value.storageAvailable / 1073741824 | floor)Gi free of \(.value.storageMaximum / 1073741824 | floor)Gi)"
    ' 2>/dev/null | tee /tmp/_lh_disk_check.txt || echo "Unable to retrieve Longhorn disk data"
    # CONTROL: how many disks did we actually see? A dead kubectl makes the two
    # threshold queries return EMPTY, which `${VAR:-0}` turns into 0 and the
    # chain below then reports "disk capacity healthy" — a green verdict from a
    # probe that never ran. Count the denominator and refuse to score without it.
    LH_DISK_TOTAL=$(kubectl get nodes.longhorn.io -n storage -o json 2>/dev/null | jq '
        [.items[].status.diskStatus // {} | to_entries[] | select(.value.storageMaximum > 0)] | length
    ' 2>/dev/null || echo "")
    LH_DISK_LOW=$(kubectl get nodes.longhorn.io -n storage -o json 2>/dev/null | jq '
        [.items[].status.diskStatus // {} | to_entries[] |
        select(.value.storageMaximum > 0 and (.value.storageAvailable / .value.storageMaximum) < 0.15)] | length
    ' 2>/dev/null || echo "")
    LH_DISK_WARN=$(kubectl get nodes.longhorn.io -n storage -o json 2>/dev/null | jq '
        [.items[].status.diskStatus // {} | to_entries[] |
        select(.value.storageMaximum > 0 and (.value.storageAvailable / .value.storageMaximum) >= 0.15 and (.value.storageAvailable / .value.storageMaximum) < 0.25)] | length
    ' 2>/dev/null || echo "")
    rm -f /tmp/_lh_disk_check.txt
    if [ -z "$LH_DISK_TOTAL" ] || [ "$LH_DISK_TOTAL" -eq 0 ] 2>/dev/null; then
        log_warning "Longhorn disk capacity NOT MEASURED (0 disks visible - kubectl or jq failed)"
        add_major_issue "Longhorn disk capacity assertions did not run: 0 disks visible from nodes.longhorn.io"
    elif [ "${LH_DISK_LOW:-0}" -gt 0 ] 2>/dev/null; then
        log_critical "Longhorn disk(s) critically low (<15% free): $LH_DISK_LOW disk(s)"
        add_critical_issue "Longhorn storage critically low: $LH_DISK_LOW disk(s) have <15% free space"
    elif [ "${LH_DISK_WARN:-0}" -gt 0 ] 2>/dev/null; then
        log_warning "Longhorn disk(s) running low (15-25% free): $LH_DISK_WARN disk(s)"
        add_major_issue "Longhorn storage low: $LH_DISK_WARN disk(s) have 15-25% free space"
    else
        log_success "Longhorn disk capacity healthy ($LH_DISK_TOTAL disks examined)"
    fi
} >> "$OUTPUT_FILE" 2>&1

#######################################
# Phase 3: Application & Service Checks
#######################################

log_section "Section 11: Container Logs Analysis"
{
    echo "Checking infrastructure logs for errors..."

    INFRA_EXCLUDE=$(build_grep_exclude "${INFRA_LOG_FALSE_POSITIVES[@]}")

    CILIUM_ERRORS=$(safe_count "kubectl logs -n kube-system -l app.kubernetes.io/name=cilium --tail=100 --since=24h 2>&1 | grep -E 'level=(error|fatal|critical)|\[(ERROR|FATAL|CRITICAL)\]' | grep -vE '$INFRA_EXCLUDE' | wc -l" "cilium-errors")
    echo "Cilium errors (24h): $CILIUM_ERRORS"

    COREDNS_ERRORS=$(safe_count "kubectl logs -n kube-system -l k8s-app=kube-dns --tail=100 --since=24h 2>&1 | grep -E 'level=(error|fatal)|\[(ERROR|FATAL)\]' | grep -vE '$INFRA_EXCLUDE' | wc -l" "coredns-errors")
    echo "CoreDNS errors (24h): $COREDNS_ERRORS"

    FLUX_ERRORS=$(safe_count "kubectl logs -n flux-system deployment/kustomize-controller --tail=50 --since=24h 2>&1 | grep -E 'level=(error|fatal)|\[(ERROR|FATAL)\]|error:' | grep -vE '$INFRA_EXCLUDE' | wc -l" "flux-errors")
    echo "Flux controller errors (24h): $FLUX_ERRORS"

    CERT_ERRORS=$(safe_count "kubectl logs -n cert-manager deployment/cert-manager --tail=50 --since=24h 2>&1 | grep -E 'level=error|\[ERROR\]|error:' | grep -vE '$INFRA_EXCLUDE' | wc -l" "cert-errors")
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
          {"bool": {"must_not": {"wildcard": {"body.text": "*NOERROR*"}}}},   # CoreDNS logs a SUCCESSFUL answer as "NOERROR", which *ERROR* matches.
          # 22.9%% of all counted "errors" were healthy DNS responses (network ns:
          # 224 real, not 24,223). A success counted as a failure is the same
          # defect family as a silent zero — see docs/sops/audit-script-correctness.md.
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
        # 'edac' alone matches driver init (EDAC MC: Ver, igen6_edac load) — require 'edac.*error' for actual faults.
        # 'ecc' alone matches PCI device IDs (e.g. 7ecc) — require 'ecc error'. 'bare hardware' is a boot string.
        ERRORS=$(safe_count "talosctl dmesg --nodes '$node' 2>&1 | grep -iE '(bare hardware error|ecc error|mce|edac.*error|uncorrected|corrected error|pcie.*error|disk error|bad sector|ata.*error|nvme.*error)' | grep -viE '(DiscoveryService|controller-runtime|rpc error|context deadline|connection refused|EOF|dialing)' | wc -l" "errors")
            echo "Hardware errors: $ERRORS"
            if [ "$ERRORS" -gt 10 ]; then
                add_minor_issue "High hardware errors on $node: $ERRORS"
            fi
        done

        # Talos discovery service errors (DiscoveryServiceController / hello failed)
        # A short burst (up to ~25) is normal during a transient upstream outage at discovery.talos.dev;
        # only alert if the count is high enough to indicate a sustained or recurring connectivity problem.
        for node in $NODE_IPS; do
            DISC_COUNT=$(safe_count "talosctl dmesg --nodes '$node' 2>&1 | grep -iE '(DiscoveryServiceController|hello failed)' | wc -l" "disc-count")
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

    # --- Per-container memory headroom (added 2026-08-24) -------------------
    # Node-level memory says nothing about a single container walking into its
    # OWN cgroup limit, and nothing else in this script or in the alert rules
    # covers it (105 rule groups, 8 memory rules, none per-container-vs-limit).
    # Found the hard way: frigate leaked 5683 -> 8078 MiB against an 8Gi limit
    # over 7 days. It never OOMKilled -- the main process is not what trips the
    # cgroup -- so `restarts: 0` and "No OOM kills" both stayed green while its
    # ffmpeg children died with ENOMEM ("Cannot allocate memory") and camera
    # detect threads dropped. The only trace was 6 log lines scored MINOR.
    #
    # LEVEL ALONE IS NOT THE SIGNAL. penpot-frontend sits flat at 98.5% of a
    # 512Mi limit forever -- reclaimable page cache, entirely benign. Asserting
    # on the ratio by itself would have made that a permanent unclearable
    # finding, which is the anti-pattern in docs/sops/audit-script-correctness.md.
    # The discriminator is level AND 24h GROWTH: a plateau is fine, a climb is
    # a leak with a deadline.
    MEM_RATIO_JSON=$(prom_query 'container_memory_working_set_bytes{container!="",container!="POD"} / on(namespace,pod,container) group_left kube_pod_container_resource_limits{resource="memory"} * 100')
    MEM_DELTA_JSON=$(prom_query 'container_memory_working_set_bytes{container!="",container!="POD"} - container_memory_working_set_bytes{container!="",container!="POD"} offset 24h')
    MEM_LIMIT_JSON=$(prom_query 'kube_pod_container_resource_limits{resource="memory"}')
    MEM_HEADROOM=$(MEM_RATIO_JSON="$MEM_RATIO_JSON" MEM_DELTA_JSON="$MEM_DELTA_JSON" MEM_LIMIT_JSON="$MEM_LIMIT_JSON" python3 -c "
import json, os

def series(raw):
    out = {}
    try:
        d = json.loads(raw)
        if d.get('status') != 'success':
            return None
        for r in d['data']['result']:
            m = r['metric']
            key = (m.get('namespace',''), m.get('pod',''), m.get('container',''))
            out[key] = float(r['value'][1])
    except Exception:
        return None
    return out

ratio = series(os.environ.get('MEM_RATIO_JSON',''))
delta = series(os.environ.get('MEM_DELTA_JSON',''))
limit = series(os.environ.get('MEM_LIMIT_JSON',''))
if ratio is None or limit is None:
    print('NOT-MEASURED query-failed')
    raise SystemExit(0)
if not ratio:
    print('NOT-MEASURED no-container-has-a-memory-limit')
    raise SystemExit(0)
if delta is None:
    delta = {}

crit, major, blind = [], [], 0
for key, pct in sorted(ratio.items(), key=lambda kv: -kv[1]):
    if pct < 90:
        continue
    ns, pod, container = key
    # IDENTITY IS namespace/container, NOT the pod. A pod name carries the
    # ReplicaSet hash, so keying a finding on it forks a brand-new row on every
    # restart -- the exact churn strip_ar_tags/_normalize exist to prevent, and
    # digit-stripping does not save it because the hash is alphanumeric.
    ident = ns + '/' + container
    lim = limit.get(key)
    d = delta.get(key)
    if not lim or d is None:
        # No 24h baseline (pod younger than the window) -> trend unknown.
        blind += 1
        if pct >= 95:
            major.append('%s|%.1f%% of its memory limit (pod %s; no 24h baseline, trend unknown)' % (ident, pct, pod))
        continue
    growth = d / lim * 100.0
    label = '%s|%.1f%% of its memory limit, +%.1f%% in 24h (pod %s)' % (ident, pct, growth, pod)
    if pct >= 95 and growth >= 1.0:
        crit.append(label)
    elif growth >= 2.0:
        major.append(label)

print('EXAMINED %d %d %d' % (len(ratio), len(crit), len(major)))
for c in crit:
    print('CRIT ' + c)
for m in major:
    print('MAJOR ' + m)
if blind:
    print('INFO %d container(s) at/above 90%% have no 24h baseline yet' % blind)
" 2>/dev/null || echo "NOT-MEASURED python-failed")

    echo ""
    echo "Per-container memory headroom (working set vs its own limit):"
    if echo "$MEM_HEADROOM" | grep -q '^NOT-MEASURED'; then
        log_warning "Per-container memory headroom NOT measured ($(echo "$MEM_HEADROOM" | head -1))"
        add_minor_issue "Per-container memory-limit check could not run ($(echo "$MEM_HEADROOM" | head -1 | cut -d' ' -f2)) - leak-into-limit unverified this cycle"
    else
        MEM_EXAMINED=$(echo "$MEM_HEADROOM" | awk '/^EXAMINED/{print $2}')
        echo "  containers with a memory limit examined: ${MEM_EXAMINED:-0}"
        echo "$MEM_HEADROOM" | grep -E '^(CRIT|MAJOR|INFO) ' | sed 's/^/  /' || true
        # The finding is keyed on the backticked namespace/container so it keeps
        # one identity across pod restarts and across changing percentages.
        while IFS='|' read -r ident detail; do
            [ -z "$ident" ] && continue
            log_critical "Container walking into its memory limit: $ident $detail"
            add_critical_issue "Container \`$ident\` is walking into its memory limit: $detail — no OOMKill yet, child allocations fail with ENOMEM first"
        done < <(echo "$MEM_HEADROOM" | sed -n 's/^CRIT //p')
        while IFS='|' read -r ident detail; do
            [ -z "$ident" ] && continue
            log_warning "Container memory rising toward its limit: $ident $detail"
            add_major_issue "Container \`$ident\` memory is rising toward its limit: $detail"
        done < <(echo "$MEM_HEADROOM" | sed -n 's/^MAJOR //p')
        if ! echo "$MEM_HEADROOM" | grep -qE '^(CRIT|MAJOR) '; then
            log_success "No container is climbing into its memory limit (${MEM_EXAMINED:-0} limited containers examined)"
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

    # Filter storage jobs by the backup name (newest first) rather than grepping
    # only the single most-recent job — avoids a false "no backup jobs" when an
    # in-flight trim job is newest or the backup Job was TTL-reaped after success.
    BACKUP_JOB=$(kubectl get jobs -n storage -o json 2>/dev/null | python3 -c "
import sys, json
try:
    items = json.load(sys.stdin).get('items', [])
except Exception:
    print(''); sys.exit()
b = [j for j in items if j['metadata']['name'].startswith('daily-backup-all-volumes')]
b.sort(key=lambda j: j['metadata'].get('creationTimestamp', ''), reverse=True)
print(b[0]['metadata']['name'] if b else '')
" 2>/dev/null || echo "")
    if [ -n "$BACKUP_JOB" ]; then
        echo "Last backup job:"
        kubectl get job -n storage "$BACKUP_JOB" 2>/dev/null || echo "Job details not available"
    fi
    # Per-volume freshness, not the Job's completionTime (a Job can exit 0 in
    # seconds while a volume goes a week without a backup).
    assess_backup_freshness "$BACKUP_JOB"
    echo "Per-volume backup freshness:"
    longhorn_backup_age_hours --per-volume | grep -Ev ' FRESH ' || echo "  all attached volumes fresh"

    # iCloud sync check — every icloud-docker-* instance in the `backup` ns.
    # Discovered from live Deployments rather than a hardcoded list or a repo
    # scan: the Deployment name equals the app.kubernetes.io/name label value,
    # so one query yields both the iteration key and the pod selector, and a
    # new Apple ID needs no change here.
    ICLOUD_INSTANCES=$(kubectl get deploy -n backup -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null \
        | grep '^icloud-docker-' | sort || true)
    if [ -z "$ICLOUD_INSTANCES" ]; then
        echo ""
        echo "iCloud sync: no icloud-docker-* deployments found (namespace: backup)"
    else
        for ICLOUD_APP in $ICLOUD_INSTANCES; do
            check_icloud_instance "$ICLOUD_APP"
        done
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 17: Security Checks"
{
    echo "Security posture check..."

    ROOT_PODS=$(kubectl get pods -A -o json | jq '[.items[] | select(.spec.securityContext.runAsUser == 0 or (.spec.containers[].securityContext.runAsUser // 0) == 0)] | length')
    echo "Pods running as root: $ROOT_PODS"

    LB_SERVICES=$(safe_count "kubectl get svc -A --field-selector spec.type=LoadBalancer --no-headers 2>/dev/null | wc -l" "lb-services" 1)
    echo "LoadBalancer services: $LB_SERVICES"

    INGRESSES=$(safe_count "kubectl get ingress -A --no-headers 2>/dev/null | wc -l" "ingresses" 1)
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

        # The subcommands are `device list` / `client list`, NOT `devices` /
        # `clients`. Until 2026-08-24 this block called the plural forms, which
        # unifictl rejects with "unrecognized subcommand". stderr was sent to
        # /dev/null and the JSON parse fell into a bare `except: print(0)`, so
        # the offline-device check reported ZERO OFFLINE DEVICES on every run
        # since it was written — a green verdict no device state could change —
        # and the client counts printed "?" forever. Verify with:
        #   unifictl local device list -o json | python3 -c 'import sys,json;
        #     print(len(json.load(sys.stdin)["data"]))'
        echo "=== Devices ==="
        unifictl local device list 2>/dev/null || echo "Unable to list devices"
        echo ""

        # Emit "total offline" so an empty/failed response is distinguishable
        # from a genuine 0. A count alone cannot tell those apart, and that is
        # exactly how the previous version scored green while blind.
        UNIFI_DEV_TALLY=$(unifictl local device list -o json 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    items = d.get('data', d) if isinstance(d, dict) else d
    if not isinstance(items, list):
        raise ValueError('unexpected payload shape')
except Exception:
    print('QUERY-FAILED')
    raise SystemExit(0)
offline = [x.get('name', '?') for x in items if x.get('state') != 1]
print(str(len(offline)) + ' ' + str(len(items)))
for o in offline:
    print('  offline: ' + o, file=sys.stderr)
" 2>/dev/null | head -1 | tr -d '\r\n' || echo "QUERY-FAILED")

        if [ "$UNIFI_DEV_TALLY" = "QUERY-FAILED" ] || [ -z "$UNIFI_DEV_TALLY" ]; then
            log_warning "UniFi device query failed - offline-device check did NOT run"
            add_minor_issue "UniFi offline-device check could not run (unifictl device list returned nothing) - device state unverified this cycle"
            UNIFI_ISSUES=$((UNIFI_ISSUES + 1))
        else
            OFFLINE_DEVICES=${UNIFI_DEV_TALLY%% *}
            UNIFI_DEV_TOTAL=${UNIFI_DEV_TALLY##* }
            echo "Devices seen by unifictl: ${UNIFI_DEV_TOTAL} (offline: ${OFFLINE_DEVICES})"
            if [ "${UNIFI_DEV_TOTAL:-0}" -eq 0 ] 2>/dev/null; then
                log_warning "UniFi controller returned an EMPTY device list - nothing was measured"
                add_minor_issue "UniFi device list empty - offline-device check has no denominator this cycle"
                UNIFI_ISSUES=$((UNIFI_ISSUES + 1))
            elif [ "${OFFLINE_DEVICES:-0}" -gt 0 ] 2>/dev/null; then
                log_warning "UniFi offline devices: $OFFLINE_DEVICES/$UNIFI_DEV_TOTAL"
                add_major_issue "UniFi devices offline: $OFFLINE_DEVICES of $UNIFI_DEV_TOTAL"
                UNIFI_ISSUES=$((UNIFI_ISSUES + 1))
            fi
        fi
        echo ""

        # --limit defaults to 30, which silently truncates the wireless list on
        # this site (74+ IoT clients on one SSID alone) and made the printed
        # count a cap, not a measurement.
        echo "=== Clients ==="
        WIRED=$(unifictl local client list --wired --limit 500 -o json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('data',d)))" 2>/dev/null || echo "?")
        WIRELESS=$(unifictl local client list --wireless --limit 500 -o json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('data',d)))" 2>/dev/null || echo "?")
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
        echo "--- Device Reboots (last 24h, from InfluxDB) ---"
        # A SCRAPE GAP is indistinguishable from a reboot in derivative(uptime):
        # the series just restarts lower. Cross-check every candidate against the
        # device's CURRENT uptime — if that already exceeds the 24h window, no
        # reboot can have happened inside it and the dip was a collection
        # artifact. (2026-08-14: two APs "rebooted" 10 ms apart during a UniFi
        # controller flap; their real uptimes were 659h and 179h.)
        #
        # PARSE BY CSV HEADER NAME, NEVER BY COLUMN INDEX. Flux orders keep()
        # output by its own rules, not by the order you asked for:
        #   keep(["name"])          -> ,result,table,name          (name at 3)
        #   keep(["name","_time"])  -> ,result,table,_time,name    (name at 4)
        # The 2026-08-14 guard read index 3 for the name in BOTH queries, so on
        # the two-column one it compared a TIMESTAMP against a set of device
        # names. Nothing ever matched, nothing was ever dropped, and the guard
        # was 100% inert from the day it shipped — while the printed line read
        # "<timestamp> rebooted around <name>", backwards, which was the visible
        # tell. Found 2026-08-24: 3 APs with 37d/37d/17d uptime reported as
        # having rebooted, all at the same nanosecond.
        INFLUX_BY_HEADER="import sys
def table(text):
    hdr = None
    for l in (text or '').replace('\r', '').split('\n'):
        l = l.strip()
        if not l or l.startswith('#'):
            continue
        cells = [c.strip() for c in l.split(',')]
        if l.startswith(',result'):
            hdr = cells
            continue
        if hdr is not None:
            yield dict(zip(hdr, cells))
"
        # Baseline uptimes are fetched WITHOUT the >24h Flux filter so that an
        # empty result is unambiguously a MEASUREMENT FAILURE (InfluxDB down,
        # UnPoller not writing) and not "every device is freshly booted". With
        # the filter pushed into Flux those two cases are identical, and the
        # first one would silently turn the guard off again.
        UPTIME_CSV=$(influx_query 'from(bucket:"default") |> range(start: -15m) |> filter(fn: (r) => (r._measurement == "uap" or r._measurement == "usw") and r._field == "uptime") |> last() |> keep(columns: ["name","_value"])' 2>/dev/null || true)
        export UPTIME_CSV
        REBOOT_OUTPUT=$(influx_query 'from(bucket:"default") |> range(start: -24h) |> filter(fn: (r) => (r._measurement == "uap" or r._measurement == "usw") and r._field == "uptime") |> derivative(unit: 30s, nonNegative: false) |> filter(fn: (r) => r._value < -1000) |> keep(columns: ["name","_time"])' \
        | python3 -c "
${INFLUX_BY_HEADER}
import os
base = [r for r in table(os.environ.get('UPTIME_CSV', '')) if r.get('name')]
stable = set()
for r in base:
    try:
        if float(r.get('_value') or 0) > 86400:
            stable.add(r['name'])
    except ValueError:
        pass
raw = [r for r in table(sys.stdin.read()) if r.get('name')]
data = [r for r in raw if r['name'] not in stable]
dropped = len(raw) - len(data)
if not base:
    print('  BASELINE-UNAVAILABLE: InfluxDB returned no current uptimes, so the')
    print('  ' + str(len(raw)) + ' uptime dip(s) in the window could NOT be cross-checked')
elif not data:
    print('None detected')
else:
    for r in data:
        nm = r['name']
        ts = r.get('_time', '?')
        print('  ' + nm + ' rebooted around ' + ts)
    print('Total reboots: ' + str(len(data)))
if dropped:
    print('  (' + str(dropped) + ' uptime-dip candidate(s) ignored: device uptime already exceeds 24h -> scrape gap, not a reboot)')
")
        echo "$REBOOT_OUTPUT"
        if echo "$REBOOT_OUTPUT" | grep -q "BASELINE-UNAVAILABLE"; then
            log_warning "UniFi reboot detection did not run - no current uptimes from InfluxDB"
            add_minor_issue "UniFi reboot check could not run (InfluxDB uptime baseline empty) - reboots unverified this cycle"
            UNIFI_ISSUES=$((UNIFI_ISSUES + 1))
        else
            REBOOT_COUNT=$(echo "$REBOOT_OUTPUT" | grep -c "rebooted around" || true)
            if [ "$REBOOT_COUNT" -gt 0 ]; then
                log_warning "$REBOOT_COUNT UniFi device reboot(s) detected in last 24h"
                add_minor_issue "UniFi device reboots in last 24h: $REBOOT_COUNT"
                UNIFI_ISSUES=$((UNIFI_ISSUES + 1))
            else
                echo ""
            fi
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
    INGRESS_ERRORS=$(safe_count "kubectl logs -n network -l app.kubernetes.io/name=ingress-nginx --tail=100 --since=1h 2>&1 | grep -E '\[error\]|\[emerg\]' | wc -l" "ingress-errors")
    echo "Ingress controller errors (last hour): $INGRESS_ERRORS"

    # Check NAS connectivity (important for storage)
    # Use curl (HTTP) as primary check — more reliable than ping across all platforms
    # (macOS/Linux/WSL all support curl; ping -W semantics differ between platforms)
    echo ""
    echo "NAS connectivity (192.168.55.240, SMB 445):"
    nc -z -w 2 192.168.55.240 445 2>/dev/null && echo "NAS reachable (SMB)" || { nc -z -w 2 192.168.55.240 22 2>/dev/null && echo "NAS reachable (SSH)"; } || echo "NAS unreachable - check storage integration"

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
    if ! { nc -z -w 2 192.168.55.240 445 2>/dev/null || nc -z -w 2 192.168.55.240 22 2>/dev/null; }; then
        log_warning "NAS (192.168.55.240) not reachable from cluster"
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
    # NOT `flux get sources git -A`: flux exits 1 when the inventory is simply
    # EMPTY, which is indistinguishable from a real failure and made this raise
    # a false "measurement did not run" (2026-08-22). kubectl returns rc 0 with
    # "No resources found" for empty and non-zero only for an actual problem.
    FAILED_GIT=$(safe_count "kubectl get gitrepositories -A -o json 2>/dev/null | jq '[.items[] | select(.status.conditions[]? | select(.type==\"Ready\" and .status!=\"True\"))] | length'" "failed-git")
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
    # Same reason as failed-git above. This cluster currently has zero
    # OCIRepository objects, so the flux form exited 1 on every run.
    FAILED_OCI=$(safe_count "kubectl get ocirepositories -A -o json 2>/dev/null | jq '[.items[] | select(.status.conditions[]? | select(.type==\"Ready\" and .status!=\"True\"))] | length'" "failed-oci")
    if [ "$FAILED_OCI" -gt 0 ]; then
        log_warning "Failed OCI sources: $FAILED_OCI"
        add_major_issue "Failed Flux OCI sources: $FAILED_OCI (may block bootstrap chart deployments)"
    fi
    echo ""

    # --- Flux image-automation family (added 2026-08-18) ---
    # Gap closed: this script had 17 Flux assertions and ZERO for the
    # image-reflector / image-automation controllers. The failure found on
    # 2026-08-18 is a SILENT one: an ImageUpdateAutomation can scan fine
    # (ImageRepository Ready), resolve a new tag fine (ImagePolicy Ready), and run
    # on schedule -- while never pushing a single commit, because its sourceRef
    # GitRepository is an https URL with no secretRef. Anonymous READ succeeds, so
    # the GitRepository is Ready and nothing else complains; but automation must
    # PUSH, and anonymous https has no write path. The tell is `lastPushCommit`
    # staying null while `lastAutomationRunTime` keeps advancing.
    # Full SOP: docs/sops/flux-image-automation-push-auth.md
    #
    # Severity note: silent-no-push is MAJOR, not CRITICAL. Remediation needs
    # operator-owned credentials (a write-capable deploy key/PAT), so a CRITICAL
    # here would pin the sweep red for days -- the same anti-pattern this file
    # just removed from the fatal-log assertion.
    echo "Flux image automation:"
    if kubectl get crd imageupdateautomations.image.toolkit.fluxcd.io >/dev/null 2>&1; then
        kubectl get imageupdateautomation -A 2>/dev/null || true
        echo ""

        # (1) not-Ready across all three kinds
        IMG_NOT_READY_OUT=$(python3 -c "
import json, subprocess, sys
bad = []
for kind in ('imageupdateautomation', 'imagepolicy', 'imagerepository'):
    try:
        out = subprocess.run(['kubectl', 'get', kind, '-A', '-o', 'json'],
                             capture_output=True, text=True, timeout=60).stdout
        items = json.loads(out).get('items', [])
    except Exception:
        continue
    for it in items:
        conds = it.get('status', {}).get('conditions', []) or []
        ready = next((c for c in conds if c.get('type') == 'Ready'), None)
        if ready is None or ready.get('status') != 'True':
            m = it['metadata']
            reason = ready.get('reason') if ready else 'NoReadyCondition'
            bad.append(f\"{kind}/{m['namespace']}/{m['name']} (reason={reason})\")
for b in bad:
    print('  NOT-READY: ' + b)
print(len(bad))
" 2>/dev/null || echo "ERR")
        # Last line is the count; everything before it is per-object detail.
        # (Deliberately NOT `tee /dev/stderr`: when stderr is an append-redirected
        # regular file, Linux reopens /dev/fd/2 at offset 0 and clobbers the report.)
        echo "$IMG_NOT_READY_OUT" | sed '$d'
        if echo "$IMG_NOT_READY_OUT" | tail -1 | grep -q ERR; then
            log_warning "Image-automation readiness query failed - assertion did NOT run"
            add_major_issue "Flux image-automation readiness assertion did not run (kubectl/python failure)"
        fi
        IMG_NOT_READY=$(echo "$IMG_NOT_READY_OUT" | tail -1 | tr -cd '0-9'); [ -z "$IMG_NOT_READY" ] && IMG_NOT_READY=0

        # (2) SILENT-FAILURE SHAPE: automation runs on schedule but has NEVER
        #     pushed, AND there is genuinely something for it to push.
        #
        #     The second half is load-bearing. "lastPushCommit is null" ALONE is not
        #     a fault: an automation whose policy tag already matches what is
        #     deployed has simply never had a change to make, and would report null
        #     forever while being perfectly healthy. Escalating on that would be the
        #     same "can never clear" anti-pattern removed from the fatal-log check.
        #     Verified live 2026-08-18: my-software-production/absenty-image-updates
        #     is null-but-healthy (policy tag == deployed tag), while
        #     my-software-development was null-and-broken (policy tag NOT deployed).
        #
        #     Note the Ready condition is NOT usable as the discriminator: it flaps
        #     to True/"repository up-to-date" on every reconcile where the tag has
        #     not moved since the last failed attempt. See the SOP.
        IMG_SILENT_OUT=$(python3 -c "
import json, subprocess, sys
from datetime import datetime, timezone, timedelta

def kget(kind, ns=None):
    cmd = ['kubectl', 'get', kind] + (['-n', ns] if ns else ['-A']) + ['-o', 'json']
    try:
        return json.loads(subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout).get('items', [])
    except Exception:
        return []

# tags actually deployed, per namespace
deployed = {}
for kind in ('deployments', 'statefulsets', 'daemonsets'):
    for w in kget(kind):
        ns = w['metadata']['namespace']
        spec = w.get('spec', {}).get('template', {}).get('spec', {})
        for c in (spec.get('containers') or []) + (spec.get('initContainers') or []):
            if c.get('image'):
                deployed.setdefault(ns, set()).add(c['image'])

# policies with an update still pending (resolved tag not deployed anywhere in ns)
pending = {}
for pol in kget('imagepolicy'):
    ns, name = pol['metadata']['namespace'], pol['metadata']['name']
    ref = (pol.get('status', {}) or {}).get('latestRef') or {}
    img, tag = ref.get('name'), ref.get('tag')
    if not img or not tag:
        continue
    pending[(ns, name)] = f'{img}:{tag}' not in deployed.get(ns, set())

now = datetime.now(timezone.utc)
silent, unproven = [], []
for it in kget('imageupdateautomation'):
    m, st, sp = it['metadata'], it.get('status', {}) or {}, it.get('spec', {}) or {}
    if sp.get('suspend') is True:
        continue
    run = st.get('lastAutomationRunTime')
    if not run:
        continue
    try:
        run_dt = datetime.fromisoformat(run.replace('Z', '+00:00'))
    except Exception:
        continue
    if now - run_dt > timedelta(hours=24):
        continue
    if st.get('lastPushCommit'):
        continue
    ns = m['namespace']
    pols = list((st.get('observedPolicies') or {}).keys()) or [p[1] for p in pending if p[0] == ns]
    blocked = [p for p in pols if pending.get((ns, p))]
    if blocked:
        silent.append(f\"{ns}/{m['name']} ran {run}, lastPushCommit null, and policy \"
                      f\"{','.join(blocked)} resolved a tag that is NOT deployed -- the \"
                      f\"update is stuck\")
    else:
        unproven.append(f'{ns}/{m[\"name\"]} (never pushed, but nothing pending -- push path unproven)')
for u in unproven:
    print('  NEVER-PUSHED-BUT-IDLE: ' + u)
for x in silent:
    print('  SILENT-NO-PUSH: ' + x)
print(len(silent))
" 2>/dev/null || echo "ERR")
        echo "$IMG_SILENT_OUT" | sed '$d'
        if echo "$IMG_SILENT_OUT" | tail -1 | grep -q ERR; then
            log_warning "Image-automation push query failed - assertion did NOT run"
            add_major_issue "Flux image-automation push assertion did not run (kubectl/python failure)"
        fi
        IMG_SILENT=$(echo "$IMG_SILENT_OUT" | tail -1 | tr -cd '0-9'); [ -z "$IMG_SILENT" ] && IMG_SILENT=0

        if [ "$IMG_SILENT" -gt 0 ]; then
            log_warning "Image automations with a STUCK update: $IMG_SILENT (lastPushCommit null, resolved tag not deployed)"
            add_major_issue "Flux image automation stuck: $IMG_SILENT automation(s) resolved a new tag but never pushed it (lastPushCommit null) - image updates are not reaching git (docs/sops/flux-image-automation-push-auth.md)"
        else
            if echo "$IMG_SILENT_OUT" | grep -q "NEVER-PUSHED-BUT-IDLE"; then
                log_info "No stuck image updates (some automations have never had a change to push - push path unproven, see detail above)"
            else
                log_success "All active Flux image automations have pushed at least once"
            fi
        fi

        if [ "$IMG_NOT_READY" -gt 0 ]; then
            log_warning "Not-Ready Flux image-automation objects: $IMG_NOT_READY"
            add_major_issue "Flux image automation/policy/repository not Ready: $IMG_NOT_READY object(s)"
        else
            log_success "Flux image automation/policy/repository objects all Ready"
        fi
    else
        echo "  image-automation CRDs not installed - skipping"
    fi
    echo ""

    # -----------------------------------------------------------------------
    # (3) AVAILABILITY COUPLING introduced by 505fefa4.
    #
    #     Before that commit the flux-system GitRepository carried NO credential
    #     and cloned this public repo anonymously, so a broken token could not
    #     stop reconciliation -- it could only stop image-automation PUSH. Now
    #     that sync.pullSecret is set, source-controller authenticates and does
    #     NOT fall back to anonymous. A revoked or expired PAT therefore halts
    #     the artifact that all ~135 Kustomizations read from: the WHOLE GitOps
    #     loop stops taking new commits, not just image automation. Availability
    #     was traded for the push capability; this asserts on the trade.
    #
    #     Three signals, because they fail at different times:
    #       (a) structural -- the credential silently vanished from the
    #           GitRepository again (the 505fefa4 pruning trap, recurring)
    #       (b) reactive   -- the source is already failing to authenticate
    #       (c) proactive  -- the PAT has an expiry date that is approaching
    #     (c) is the one that matters most: expiry is otherwise SILENT, because
    #     lastPushCommit stays non-null from the pre-expiry pushes and so
    #     assertion (2) above keeps reading healthy right through the outage.
    echo "Flux sync-source credential (single point of failure for all of GitOps):"
    GITREPO_STATE=$(kubectl get gitrepository -n flux-system flux-system -o json 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print('QUERY-FAILED||'); raise SystemExit
conds = ((d.get('status', {}) or {}).get('conditions') or [])
ready = next((c for c in conds if c.get('type') == 'Ready'), None)
secret = ((d.get('spec', {}) or {}).get('secretRef') or {}).get('name', '')
print('|'.join([
    (ready.get('status') if ready else 'Unknown'),
    secret,
    ((ready.get('message') if ready else 'no Ready condition') or '').replace('|', '/')[:200],
]))
" 2>/dev/null || echo "QUERY-FAILED||")
    GITREPO_READY=$(echo "$GITREPO_STATE" | cut -d'|' -f1)
    GITREPO_SECRET=$(echo "$GITREPO_STATE" | cut -d'|' -f2)
    GITREPO_MSG=$(echo "$GITREPO_STATE" | cut -d'|' -f3)

    if [ "$GITREPO_READY" = "QUERY-FAILED" ]; then
        log_warning "flux-system GitRepository query failed - credential assertion did NOT run"
        add_major_issue "Flux sync-source credential assertion did not run (kubectl/python failure)"
    elif [ -z "$GITREPO_SECRET" ]; then
        # This is the 505fefa4 regression shape, and it is INVISIBLE otherwise:
        # anonymous read keeps the GitRepository Ready=True while every push dies.
        log_warning "flux-system GitRepository has NO secretRef - git push capability is gone"
        add_major_issue "Flux sync source has no credential (secretRef empty) - image automation cannot push; check FluxInstance spec.sync.pullSecret was not silently pruned again (docs/sops/flux-image-automation-push-auth.md)"
    else
        echo "  secretRef: $GITREPO_SECRET (present)"
        if [ "$GITREPO_READY" != "True" ] && echo "$GITREPO_MSG" | grep -qiE "auth|credential|401|403|unauthorized|denied"; then
            log_error "flux-system GitRepository FAILING AUTH: $GITREPO_MSG"
            add_critical_issue "Flux sync source cannot authenticate to git - the ENTIRE GitOps loop is stalled (no new commits reach the cluster), not just image automation. Rotate the credential per docs/sops/flux-image-automation-push-auth.md section 10."
        elif [ "$GITREPO_READY" != "True" ]; then
            log_warning "flux-system GitRepository not Ready: $GITREPO_MSG"
            add_major_issue "Flux sync source not Ready: $GITREPO_MSG"
        else
            log_success "flux-system GitRepository Ready and carrying a credential"
        fi

        # (c) proactive expiry. GitHub returns the token's expiry on ANY
        #     authenticated API call via the github-authentication-token-expiration
        #     header. Absent header => a credential that never expires (classic PAT
        #     with no expiry, or a deploy key) - good for availability, and the
        #     scope question is handled in the SOP's Security Check instead.
        #     Token is piped via `curl -K -` so it never lands in argv/`ps`.
        GH_TOKEN=$(kubectl get secret -n flux-system flux-system-git-auth -o jsonpath='{.data.password}' 2>/dev/null | base64 -d 2>/dev/null || echo "")
        if [ -z "$GH_TOKEN" ]; then
            log_info "Sync credential secret unreadable from here - skipping token-expiry check"
        else
            GH_RESP=$(printf 'header = "Authorization: Bearer %s"\nurl = "https://api.github.com/"\nsilent\noutput = "/dev/null"\ndump-header = "-"\nconnect-timeout = 5\nmax-time = 15\n' "$GH_TOKEN" \
                | curl -K - 2>/dev/null | tr -d '\r' || echo "")
            # ^ the 2>/dev/null on curl is LOAD-BEARING, not tidiness. This whole section
            #   is wrapped in `>> "$OUTPUT_FILE" 2>&1`, and curl's -K config-parse warnings
            #   quote the offending config line -- i.e. the full Authorization header. Drop
            #   the suppression and the token lands in the report file.
            unset GH_TOKEN
            # tolower(), not gawk's IGNORECASE: this runs on macOS/BSD awk,
            # where IGNORECASE is silently a no-op. HTTP/2 lowercases header
            # names anyway, but do not depend on the wire version for this.
            GH_CODE=$(echo "$GH_RESP" | awk '/^HTTP\// {c=$2} END {print c+0}')
            GH_EXPIRY=$(echo "$GH_RESP" | awk 'tolower($0) ~ /^github-authentication-token-expiration:/ {sub(/^[^:]*:[ \t]*/, ""); print; exit}')
            # SCOPE, not just expiry. Only classic PATs advertise x-oauth-scopes; a
            # fine-grained PAT returns none. A non-empty list therefore means the
            # credential is account-wide rather than scoped to this repository -- which
            # matters far more now that it is actually mounted and used. Without this the
            # finding is undetectable on a recurring basis: the expiry ladder above takes
            # the "non-expiring" branch and raises nothing at all.
            GH_SCOPES=$(echo "$GH_RESP" | awk 'tolower($0) ~ /^x-oauth-scopes:/ {sub(/^[^:]*:[ \t]*/, ""); print; exit}')
            if [ -n "$GH_SCOPES" ]; then
                SCOPE_N=$(echo "$GH_SCOPES" | tr ',' '\n' | grep -c '[a-z]')
                log_warning "Sync credential is account-wide scoped (classic PAT, $SCOPE_N scopes) - not repo-scoped"
                add_major_issue "Flux git credential is an account-wide classic PAT ($SCOPE_N scopes), not a repository-scoped fine-grained PAT. It is now actively mounted and used by source-controller and image-automation-controller. Rotate per security_ref: F-13845dda / docs/sops/flux-image-automation-push-auth.md section 10."
            fi
            if [ "${GH_CODE:-0}" = "0" ]; then
                log_info "GitHub unreachable - token-expiry check skipped (not a cluster fault)"
            elif [ "${GH_CODE}" = "401" ] || [ "${GH_CODE}" = "403" ]; then
                log_error "Sync credential REJECTED by GitHub (HTTP $GH_CODE) - it is revoked or expired"
                add_critical_issue "Flux git credential is rejected by GitHub (HTTP $GH_CODE). Because the sync source no longer falls back to anonymous, the ENTIRE GitOps loop stops taking new commits. Rotate per docs/sops/flux-image-automation-push-auth.md section 10."
            elif [ -z "$GH_EXPIRY" ]; then
                log_info "Sync credential accepted by GitHub; no expiry advertised (non-expiring credential)"
                add_minor_issue "Flux git credential does not expire - no natural rotation trigger, and a leak stays valid until manually revoked (security_ref: F-13845dda)"
            else
                GH_DAYS=$(python3 -c "
import sys
from datetime import datetime, timezone
raw = sys.argv[1].strip().replace(' UTC', '')
for f in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d'):
    try:
        d = datetime.strptime(raw, f).replace(tzinfo=timezone.utc); break
    except ValueError:
        continue
else:
    print('NA'); raise SystemExit
print(int((d - datetime.now(timezone.utc)).total_seconds() // 86400))
" "$GH_EXPIRY" 2>/dev/null || echo "NA")
                if [ "$GH_DAYS" = "NA" ]; then
                    log_info "Sync credential expiry advertised but unparseable: $GH_EXPIRY"
                elif [ "$GH_DAYS" -le 0 ]; then
                    log_error "Sync credential EXPIRED ($GH_EXPIRY)"
                    add_critical_issue "Flux git credential expired on $GH_EXPIRY - the entire GitOps loop is stalled. Rotate per docs/sops/flux-image-automation-push-auth.md section 10."
                elif [ "$GH_DAYS" -le 14 ]; then
                    log_warning "Sync credential expires in $GH_DAYS day(s) ($GH_EXPIRY)"
                    add_major_issue "Flux git credential expires in $GH_DAYS day(s) ($GH_EXPIRY). On expiry the WHOLE GitOps loop stops, not just image automation - rotate now (docs/sops/flux-image-automation-push-auth.md section 10)."
                elif [ "$GH_DAYS" -le 45 ]; then
                    log_warning "Sync credential expires in $GH_DAYS day(s) ($GH_EXPIRY)"
                    add_minor_issue "Flux git credential expires in $GH_DAYS day(s) ($GH_EXPIRY) - schedule a rotation."
                else
                    log_success "Sync credential valid for $GH_DAYS more day(s)"
                fi
            fi
        fi
    fi
    echo ""

    # -----------------------------------------------------------------------
    # (4) IS THE CONFUSED-DEPUTY GUARDRAIL STILL EFFECTIVE?
    #
    #     A ValidatingAdmissionPolicy with no ValidatingAdmissionPolicyBinding is
    #     100% inert -- and `kubectl get validatingadmissionpolicy` still lists it,
    #     cheerfully, forever. "Applied" and "effective" are different claims. This
    #     is the same silent-no-op class as the pruned FluxInstance field that
    #     started this whole incident, which is exactly why it gets an assertion
    #     rather than a line in a SOP: the owning Kustomization runs prune: true,
    #     so the Binding can disappear without anything going red.
    #
    #     Deliberately asserts the LINKAGE (binding.policyName resolves, action is
    #     Deny), not merely that two objects exist.
    echo "Flux confused-deputy guardrail:"
    VAP_OUT=$(python3 -c "
import json, subprocess

NAME = 'flux-imageupdateautomation-sourceref'

def get(kind, name):
    r = subprocess.run(['kubectl', 'get', kind, name, '-o', 'json'],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None

pol = get('validatingadmissionpolicy', NAME)
bnd = get('validatingadmissionpolicybinding', NAME)

if pol is None:
    print('  MISSING-POLICY: ValidatingAdmissionPolicy ' + NAME + ' is absent')
    print(1); raise SystemExit
if bnd is None:
    print('  INERT-POLICY: ' + NAME + ' exists but has NO Binding -- it enforces NOTHING')
    print(1); raise SystemExit

bad = 0
bspec = bnd.get('spec', {}) or {}
if bspec.get('policyName') != NAME:
    print('  BROKEN-LINK: Binding.policyName=' + str(bspec.get('policyName')) + ' does not resolve to ' + NAME)
    bad += 1
actions = bspec.get('validationActions') or []
if 'Deny' not in actions:
    print('  NOT-ENFORCING: Binding validationActions=' + str(actions) + ' (Audit/Warn does not block)')
    bad += 1
if (pol.get('spec', {}) or {}).get('failurePolicy') != 'Fail':
    print('  FAIL-OPEN: policy failurePolicy is not Fail')
    bad += 1
warns = ((pol.get('status', {}) or {}).get('typeChecking', {}) or {}).get('expressionWarnings')
if warns:
    print('  CEL-TYPECHECK-WARN: ' + str(warns)[:200])
    bad += 1

# ALLOWLIST DRIFT. The two absenty ImageUpdateAutomations are not standalone -- each is
# owned by its app's Kustomization, so a denial on the IUA fails the ENTIRE absenty
# Kustomization, not just its image updates. A namespace rename or a new automation in an
# unlisted namespace therefore takes down a whole application. Catch it here, before Flux
# does. Parse the allowlist out of the live policy so this can never disagree with what
# the apiserver is actually enforcing.
allowed = []
for v in (pol.get('spec', {}) or {}).get('variables', []) or []:
    if v.get('name') == 'allowed_namespaces':
        # split on the single-quote char (chr(39)); odd-indexed segments are the
        # quoted namespace literals. Avoids embedding a double quote, which would
        # terminate the enclosing bash string.
        allowed = v.get('expression', '').split(chr(39))[1::2]
if not allowed:
    print('  ALLOWLIST-UNREADABLE: could not parse allowed_namespaces from the live policy')
    bad += 1
else:
    r = subprocess.run(['kubectl', 'get', 'imageupdateautomation', '-A', '-o', 'json'],
                       capture_output=True, text=True, timeout=60)
    try:
        items = json.loads(r.stdout).get('items', [])
    except Exception:
        items = []
    for it in items:
        ns = it['metadata']['namespace']
        ref_ns = ((it.get('spec', {}) or {}).get('sourceRef') or {}).get('namespace') or ns
        if ref_ns != ns and ns not in allowed:
            print('  ALLOWLIST-DRIFT: ' + ns + '/' + it['metadata']['name'] +
                  ' uses a cross-namespace sourceRef but ' + ns + ' is NOT allowlisted -- '
                  'its OWNING Kustomization will fail entirely, not just image updates')
            bad += 1
print(bad)
" 2>/dev/null || echo "ERR")
    echo "$VAP_OUT" | sed '$d'
    if echo "$VAP_OUT" | tail -1 | grep -q ERR; then
        log_warning "Guardrail query failed - assertion did NOT run"
        add_major_issue "Flux confused-deputy guardrail assertion did not run (kubectl/python failure)"
    else
        VAP_BAD=$(echo "$VAP_OUT" | tail -1 | tr -cd '0-9'); [ -z "$VAP_BAD" ] && VAP_BAD=0
        if [ "$VAP_BAD" -gt 0 ]; then
            log_error "Confused-deputy guardrail is NOT effective ($VAP_BAD problem(s))"
            add_critical_issue "Flux cross-namespace image-automation guardrail is not enforcing - any namespace can again reference the write-capable flux-system GitRepository and drive a git push (docs/sops/flux-image-automation-push-auth.md section 3)"
        else
            log_success "Cross-namespace image-automation guardrail bound and enforcing (Deny)"
        fi
    fi
    echo ""
    echo "Flux controllers status:"
    kubectl get pods -n flux-system
    echo ""

    # Check Flux controllers health
    # Denominator excludes Succeeded pods. flux-system accumulates one-off
    # throwaway pods (chart fetches, debug shells) that complete and linger;
    # counting them as controllers made FLUX_RUNNING < FLUX_CONTROLLERS and
    # manufactured a CRITICAL out of a pod that had done its job and exited.
    # Seen 2026-08-15 with `lc-chart-fetch2`. Failed/Pending are deliberately
    # STILL counted -- a controller that crashed is exactly what this check is
    # for. Note we cannot filter on the `part-of=flux` label instead: the
    # flux-operator pod does not carry it and is a real controller.
    FLUX_CONTROLLERS=$(safe_count "kubectl get pods -n flux-system --field-selector=status.phase!=Succeeded --no-headers 2>/dev/null | wc -l" "flux-controllers" 1)
    FLUX_RUNNING=$(safe_count "kubectl get pods -n flux-system --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l" "flux-running" 1)
    FLUX_LEFTOVER=$(safe_count "kubectl get pods -n flux-system --field-selector=status.phase=Succeeded --no-headers 2>/dev/null | wc -l" "flux-leftover")
    if [ "${FLUX_LEFTOVER:-0}" -gt 0 ]; then
        echo "Note: $FLUX_LEFTOVER completed one-off pod(s) left in flux-system (not controllers; safe to delete)"
    fi
    echo "Flux controllers: $FLUX_RUNNING/$FLUX_CONTROLLERS running"
    echo ""

    echo "Kustomizations summary:"
    flux get kustomizations -A | head -30
    echo ""

    # Count kustomizations where READY column (col 5) is not True — resilient to mid-reconciliation message changes
    # Count DISTINCT not-Ready kustomizations from the API, not table lines: a
    # single failing kustomization wraps its multi-line MESSAGE (e.g. a SOPS
    # decryption stack trace) across ~12 table rows, and `awk '$5 != "True"'`
    # counted each wrapped row as a separate "not reconciled" entry (false 12).
    NOT_RECONCILED=$(safe_count "kubectl get kustomizations -A -o json 2>/dev/null | jq -r '[.items[] | select(.status.conditions[]? | select(.type==\"Ready\" and .status!=\"True\"))] | length'" "not-reconciled")
    TOTAL_KUST=$(safe_count "flux get kustomizations -A 2>/dev/null | grep -v 'NAMESPACE' | wc -l" "total-kust" 1)
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
            # Section 5 already emitted the DB row for this exact condition; a second
            # add_minor_issue here forked duplicate findings (F-359d4bdf/F-a2726bda,
            # 2026-08-17). Log-only in this summary section.
            log_warning "GitOps reconciliation issues: $NOT_RECONCILED kustomizations not reconciled"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

#######################################
# Phase 4: Advanced Monitoring
#######################################

log_section "Section 21: Namespace Review"
{
    TOTAL_NS=$(safe_count "kubectl get namespaces --no-headers | wc -l" "total-ns" 1)
    echo "Total namespaces: $TOTAL_NS"

    TERMINATING_NS=$(safe_count "kubectl get namespaces 2>/dev/null | grep 'Terminating' | wc -l" "terminating-ns")
    echo "Terminating namespaces: $TERMINATING_NS"

    TERMINATING_PODS=$(safe_count "kubectl get pods -A 2>/dev/null | grep 'Terminating' | wc -l" "terminating-pods")
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

    # Recent-window (last 1h) major-error count. Distinguishes an ONGOING error
    # storm from one that's already fixed but whose pre-fix ERROR lines still
    # linger in the --since=24h window above. Without this, a resolved storm
    # (e.g. a Shelly that was power-cycled out of setup_retry) keeps the major
    # finding open for up to 24h while its old log lines age out. Same filtering
    # as MAJOR_HA_ERRORS so the two are directly comparable.
    HA_LOGS_RECENT=$(kubectl logs -n home-automation deployment/home-assistant --since=1h 2>&1 || echo "")
    MAJOR_HA_ERRORS_RECENT=$(echo "$HA_LOGS_RECENT" | grep -E "ERROR" | grep -v "Failed to connect" | filter_ha_false_positives | wc -l || true)

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
    # NOTE: previously this piped state.json into `python3 - <<heredoc` — but the
    # heredoc TAKES OVER stdin, so the piped JSON never reached json.load(sys.stdin)
    # and the check printed "Total devices: ?" on every run since it was written.
    # A pass asserted on a measurement that structurally cannot see (the silent-
    # unknown class, docs/sops/audit-script-correctness.md). Temp file instead.
    Z2M_STATE_TMP=$(mktemp)
    kubectl exec -n home-automation "$Z2M_POD" -- sh -c 'cat /data/state.json 2>/dev/null' > "$Z2M_STATE_TMP" 2>/dev/null
    Z2M_DEVICE_STATS=$(python3 - "$Z2M_STATE_TMP" <<'PYEOF'
import sys, json, datetime
try:
    d = json.load(open(sys.argv[1]))
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
    rm -f "$Z2M_STATE_TMP"
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

    # --- Z2M bridge state via MQTT (added 2026-06-04 post-incident) ---
    # Catches the failure modes we hit on 2026-06-04: a Router silently
    # dropping out of the database (only EndDevices remain), devices stuck
    # with interview_completed=false (e.g. CC2652-class router Node
    # Descriptor bug — see docs/sops/zigbee2mqtt.md §4d), and permit_join
    # left open after pairing. Queries the broker directly so the check
    # works even when the Z2M pod logs look benign.
    #
    # NB: subscribe to each retained topic SEPARATELY (each with -C 1)
    # rather than a combined -t a -t b -C 2. The latter approach is racy
    # because z2m republishes bridge/info frequently (every device interaction);
    # under load the subscriber can satisfy -C 2 with two bridge/info messages
    # before the larger bridge/devices payload arrives, producing a false
    # "coordinator missing" critical (real cause of the F-bfb57b26 false
    # positive observed 2026-06-04 after the version 2.11.0 bump).
    echo "Zigbee2MQTT bridge state (via MQTT):"
    Z2M_BRIDGE_DEVICES_RAW=$(kubectl exec -n home-automation deployment/mosquitto -c app -- \
        mosquitto_sub -h 127.0.0.1 -p 1883 -t zigbee2mqtt/bridge/devices -C 1 -W 12 2>/dev/null)
    Z2M_BRIDGE_INFO_RAW=$(kubectl exec -n home-automation deployment/mosquitto -c app -- \
        mosquitto_sub -h 127.0.0.1 -p 1883 -t zigbee2mqtt/bridge/info -C 1 -W 10 2>/dev/null)

    Z2M_BRIDGE_STATE=$(python3 - "$Z2M_BRIDGE_DEVICES_RAW" "$Z2M_BRIDGE_INFO_RAW" <<'PYEOF'
import json, sys
devices_raw = sys.argv[1] if len(sys.argv) > 1 else ""
info_raw    = sys.argv[2] if len(sys.argv) > 2 else ""
got_devices = bool(devices_raw.strip())
got_info    = bool(info_raw.strip())
out = {"got_devices": got_devices, "got_info": got_info,
       "by_type": {}, "failed_interview": [], "unknown": [],
       "permit_join": None, "count": None}
if got_devices:
    try:
        devs = json.loads(devices_raw)
        out['count'] = len(devs)
        for x in devs:
            t = x.get('type', '?')
            out['by_type'][t] = out['by_type'].get(t, 0) + 1
            if x.get('interview_completed') is False:
                out['failed_interview'].append(x.get('ieee_address', '?'))
            if x.get('type') == 'Unknown':
                out['unknown'].append(x.get('ieee_address', '?'))
    except Exception as e:
        out['got_devices'] = False
        print(f"PARSE_ERROR:devices:{e}")
if got_info:
    try:
        d = json.loads(info_raw)
        out['permit_join'] = d.get('permit_join')
    except Exception as e:
        out['got_info'] = False
        print(f"PARSE_ERROR:info:{e}")
print(f"GOT_DEVICES={out['got_devices']}")
print(f"GOT_INFO={out['got_info']}")
print(f"COUNT={out['count'] if out['count'] is not None else ''}")
print(f"PERMIT_JOIN={out['permit_join']}")
for t, n in sorted(out['by_type'].items()):
    print(f"TYPE:{t}:{n}")
for ieee in out['failed_interview']:
    print(f"FAILED:{ieee}")
for ieee in out['unknown']:
    print(f"UNKNOWN:{ieee}")
PYEOF
        )

    Z2M_GOT_DEVICES=$(echo "$Z2M_BRIDGE_STATE" | awk -F= '/^GOT_DEVICES=/{print $2}')
    Z2M_GOT_INFO=$(echo "$Z2M_BRIDGE_STATE" | awk -F= '/^GOT_INFO=/{print $2}')
    Z2M_BRIDGE_COUNT=$(echo "$Z2M_BRIDGE_STATE" | awk -F= '/^COUNT=/{print $2}')
    Z2M_PERMIT_JOIN=$(echo "$Z2M_BRIDGE_STATE" | awk -F= '/^PERMIT_JOIN=/{print $2}')
    Z2M_FAILED_COUNT=$(echo "$Z2M_BRIDGE_STATE" | grep -c "^FAILED:" || true)
    Z2M_ROUTER_COUNT=$(echo "$Z2M_BRIDGE_STATE" | awk -F: '/^TYPE:Router:/{print $3}')
    Z2M_COORD_COUNT=$(echo "$Z2M_BRIDGE_STATE" | awk -F: '/^TYPE:Coordinator:/{print $3}')

    echo "  bridge/devices received: ${Z2M_GOT_DEVICES:-False}"
    echo "  bridge/info received:    ${Z2M_GOT_INFO:-False}"
    echo "  Total entries: ${Z2M_BRIDGE_COUNT:-N/A}"
    echo "  By type:"
    echo "$Z2M_BRIDGE_STATE" | grep "^TYPE:" | sed 's/^TYPE:/    /'
    echo "  permit_join: ${Z2M_PERMIT_JOIN:-unknown}"
    echo "  Devices with failed interview: $Z2M_FAILED_COUNT"
    if [ "$Z2M_FAILED_COUNT" -gt 0 ]; then
        echo "$Z2M_BRIDGE_STATE" | grep "^FAILED:" | sed 's/^FAILED:/    /'
    fi

    # If we couldn't get bridge/devices at all, downgrade to warning (NOT critical).
    # Most common cause: warm broker is busy enumerating ~800 retained
    # messages and the larger bridge/devices payload didn't arrive in time.
    # Re-running the sweep usually clears it.
    if [ "${Z2M_GOT_DEVICES}" != "True" ]; then
        log_warning "Z2M bridge/devices not received in time — broker busy or z2m offline; skipping coordinator/router/interview checks this sweep"
    else
        # Critical: bridge/devices arrived AND coordinator is absent → mesh broken
        if [ "${Z2M_COORD_COUNT:-0}" = "0" ]; then
            log_critical "Z2M has 0 coordinators in bridge/devices — Zigbee mesh broken"
            add_critical_issue "Z2M coordinator missing from bridge/devices"
        fi
        # Major: router count dropped below baseline (SLZB-06P7 ground-floor router)
        Z2M_ROUTER_BASELINE=1
        if [ -n "$Z2M_ROUTER_COUNT" ] && [ "$Z2M_ROUTER_COUNT" -lt "$Z2M_ROUTER_BASELINE" ]; then
            log_warning "Z2M router count below baseline: $Z2M_ROUTER_COUNT (expected ≥ $Z2M_ROUTER_BASELINE) — see docs/sops/zigbee2mqtt.md §4d for recovery"
            add_major_issue "Z2M routers: $Z2M_ROUTER_COUNT (baseline $Z2M_ROUTER_BASELINE)"
        fi
        # Major: any device stuck with interview_completed=false. Baseline 0
        # since the SLZB-06P7 was DB-injected on 2026-06-04.
        Z2M_FAILED_BASELINE=0
        if [ "$Z2M_FAILED_COUNT" -gt "$Z2M_FAILED_BASELINE" ]; then
            log_warning "Z2M devices with failed interview: $Z2M_FAILED_COUNT (baseline $Z2M_FAILED_BASELINE) — see docs/sops/zigbee2mqtt.md §4d"
            add_major_issue "Z2M failed-interview devices: $Z2M_FAILED_COUNT"
        fi
    fi
    # Minor: permit_join left open at sweep time = pairing window not closed.
    # Only meaningful if bridge/info actually arrived.
    if [ "${Z2M_GOT_INFO}" = "True" ] && [ "${Z2M_PERMIT_JOIN}" = "True" ]; then
        log_warning "Z2M permit_join is OPEN at sweep time — pairing window left open?"
        add_minor_issue "Z2M permit_join open during daily sweep"
    fi
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
        # Recency gate: only hold a MAJOR while the storm is still active
        # (>=5 ERRORs in the last 1h). If recent activity has subsided, the
        # device/integration is fixed and the high 24h count is just pre-fix
        # log lines aging out — downgrade to a transient minor that clears on
        # its own, instead of a stale major that lingers up to 24h.
        if [ "${MAJOR_HA_ERRORS_RECENT:-0}" -ge 5 ]; then
            log_warning "High Home Assistant major error count: $MAJOR_HA_ERRORS ($MAJOR_HA_ERRORS_RECENT in last 1h, ongoing)"
            add_major_issue "High Home Assistant error count: $MAJOR_HA_ERRORS"
        else
            log_warning "Home Assistant 24h error count high ($MAJOR_HA_ERRORS) but subsided — only ${MAJOR_HA_ERRORS_RECENT:-0} in last 1h"
            add_minor_issue "Home Assistant errors subsided: $MAJOR_HA_ERRORS in 24h, ${MAJOR_HA_ERRORS_RECENT:-0} in last 1h (aging out)"
        fi
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
          {"bool": {"must_not": {"wildcard": {"body.text": "*NOERROR*"}}}},   # CoreDNS logs a SUCCESSFUL answer as "NOERROR", which *ERROR* matches.
          # 22.9%% of all counted "errors" were healthy DNS responses (network ns:
          # 224 real, not 24,223). A success counted as a failure is the same
          # defect family as a silent zero — see docs/sops/audit-script-correctness.md.
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
    SHELLY_COUNT=$(safe_count "kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=20000 2>&1 | grep 'New client connected' | grep -v '<unknown>' | sed 's/.* as //' | sed 's/ .*//' | grep -i shelly | sort -u | wc -l" "shelly-count")
    echo "Shelly devices identified (recent reconnections): $SHELLY_COUNT"
    echo ""
    echo "Note: MQTT clients maintain persistent connections. This count shows devices"
    echo "that reconnected recently. Stable devices won't appear in recent logs."
    echo ""

    echo "=== MQTT Authentication Issues ==="
    AUTH_FAILURES=$(safe_count "kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=100 2>&1 | grep -E '(not authorised|authentication|Connection refused)' | wc -l" "auth-failures")
    echo "Authentication failures: $AUTH_FAILURES"
    echo ""

    echo "=== MQTT Connection Errors ==="
    MQTT_CONN_ERRORS=$(safe_count "kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=100 2>&1 | grep -i error | wc -l" "mqtt-conn-errors")
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
    TA_ERRORS=$(safe_count "kubectl logs -n download deployment/tube-archivist --tail=20 --since=1h 2>&1 | grep -iE '\[ERROR\]|error:' | wc -l" "ta-errors")
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
    else
        # Google Calendar sync (google_synchronization app) — the imported
        # Google calendar goes silently stale when a user's OAuth token stops
        # refreshing (token revoked/expired). A healthy sync bumps
        # token_expires_at to ~now+1h on each run, so a token that hasn't
        # refreshed in >2 days means the sync is dead. (2026-03→05: it broke
        # for 81 days unnoticed — this check exists so it can't happen again.)
        NC_POD=$(kubectl get pod -n office -l app.kubernetes.io/name=nextcloud \
            -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
        if [ -n "$NC_POD" ]; then
            GSYNC_STALE=""
            NOW_TS=$(date +%s)
            for u in $(kubectl exec -n office "$NC_POD" -c nextcloud -- \
                    su -s /bin/sh www-data -c 'php occ user:list 2>/dev/null' 2>/dev/null \
                    | sed -n 's/^[[:space:]]*-[[:space:]]*\([^:]*\):.*/\1/p'); do
                EXP=$(kubectl exec -n office "$NC_POD" -c nextcloud -- \
                    su -s /bin/sh www-data -c "php occ user:setting $u google_synchronization token_expires_at 2>/dev/null" \
                    2>/dev/null | tr -d '[:space:]')
                case "$EXP" in
                    ''|*[!0-9]*) : ;;  # no google sync for this user, or non-numeric
                    *)
                        AGE_DAYS=$(( (NOW_TS - EXP) / 86400 ))
                        echo "  google_synchronization $u: token age ${AGE_DAYS}d"
                        if [ "$AGE_DAYS" -gt 2 ]; then
                            GSYNC_STALE="$GSYNC_STALE ${u}(${AGE_DAYS}d)"
                        fi
                        ;;
                esac
            done
            if [ -n "$GSYNC_STALE" ]; then
                log_warning "Nextcloud Google Calendar sync stale:$GSYNC_STALE"
                add_major_issue "Nextcloud google_synchronization OAuth token not refreshing — Google Calendar import is stale for:$GSYNC_STALE. Reconnect via Nextcloud Settings → Google synchronization."
                OFFICE_ISSUES=$((OFFICE_ISSUES + 1))
            fi
        fi
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

    # Redis health (shared cache used by multiple apps)
    # Deployed as a Deployment (not StatefulSet) named "redis" in databases namespace
    echo ""
    echo "Redis:"
    kubectl get deployments -n databases redis 2>/dev/null || echo "Redis not found"
    REDIS_READY=$(kubectl get deployment -n databases redis -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    REDIS_DESIRED=$(kubectl get deployment -n databases redis -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "1")
    echo "Redis pods: $REDIS_READY/$REDIS_DESIRED ready"
    if [ "$REDIS_READY" != "$REDIS_DESIRED" ]; then
        log_warning "Redis not fully ready: $REDIS_READY/$REDIS_DESIRED"
        add_major_issue "Redis pods not ready: $REDIS_READY/$REDIS_DESIRED (affects cache-dependent apps)"
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
    # All AI apps (open-webui, openclaw, mcpo) depend on this host.
    # Use curl to Ollama API — more accurate than ping (checks actual service availability)
    echo "Ollama AI backend (Mac Mini at 192.168.30.111):"
    if curl -s --connect-timeout 2 http://192.168.30.111:11434/api/version -o /dev/null 2>/dev/null; then
        echo "Ollama host reachable"
        log_success "Ollama AI backend (192.168.30.111) reachable"
    else
        echo "Ollama host unreachable"
        log_warning "Ollama AI backend (192.168.30.111) not reachable - AI features (open-webui, openclaw) may be broken"
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

    # openclaw codex OAuth — the agent's "openai-codex" provider depends on
    # tokens written by `codex login` into ~/.codex/auth.json. ChatGPT-mode
    # tokens (`auth_mode: chatgpt`) rotate organically for a while via the
    # refresh_token, but the refresh chain has a finite lifetime — when it
    # stops rolling we get "Missing API key for provider openai-codex" on
    # every dispatch (FailoverError, lastErrorReason="auth"). Symptom matches
    # the 2026-05-27 and 2026-06-06 incidents (10-day cycle).
    #
    # Two signals:
    #   1. last_refresh stale → proactive nudge to re-run device-auth
    #   2. Daily Morning Briefing cron lastErrorReason == "auth" → already broken
    echo "openclaw codex OAuth:"
    OC_POD=$(kubectl get pod -n ai -l app.kubernetes.io/instance=openclaw \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -z "$OC_POD" ]; then
        echo "openclaw pod not found — skipping codex OAuth check"
    else
        # Signal 1: last_refresh age (warning at 7d, fail at 14d)
        CODEX_REFRESH=$(kubectl exec -n ai "$OC_POD" -c app -- \
            cat /home/node/.codex/auth.json 2>/dev/null \
            | jq -r '.last_refresh // empty' 2>/dev/null)
        if [ -n "$CODEX_REFRESH" ]; then
            # ISO8601 → epoch (BSD date and GNU date both accept -d with this format)
            REFRESH_TS=$(date -d "$CODEX_REFRESH" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "${CODEX_REFRESH%%.*}Z" +%s 2>/dev/null || echo "")
            if [ -n "$REFRESH_TS" ]; then
                AGE_DAYS=$(( ($(date +%s) - REFRESH_TS) / 86400 ))
                echo "  codex auth last_refresh: $CODEX_REFRESH (age ${AGE_DAYS}d)"
                if [ "$AGE_DAYS" -ge 14 ]; then
                    log_warning "codex auth last_refresh is ${AGE_DAYS}d old — refresh chain likely dead"
                    add_major_issue "openclaw codex OAuth tokens not refreshed in ${AGE_DAYS} days — provider auth will fail. Run: kubectl -n ai exec -it $OC_POD -c app -- codex login --device-auth, then delete the pod."
                    INFRA_SVC_ISSUES=$((INFRA_SVC_ISSUES + 1))
                elif [ "$AGE_DAYS" -ge 7 ]; then
                    log_warning "codex auth last_refresh is ${AGE_DAYS}d old — proactive re-auth recommended"
                fi
            fi
        else
            echo "  codex auth.json missing or unreadable"
        fi

        # --- openclaw dispatch integrity ---
        # The 2026-06-15 outage proved the old single-signal check (cron
        # lastErrorReason=="auth", hardcoded cron id) was blind: the cron had
        # *vanished* (get returned nothing → silent pass) and the real failure was
        # a codex-harness/model mismatch, not "auth". These checks catch agent-turn
        # failures regardless of root cause.

        # Signal 2a: managed-plugin version skew. openclaw's managed plugin store
        # (~/.openclaw/npm) does NOT auto-refresh on host upgrades. A stale
        # @openclaw/codex whose harness pins providerIds=["codex"] rejects
        # openai/gpt-5.5 ("provider is not one of: codex") and breaks every
        # dispatch (incident 2026-06-15, upstream openclaw#87650).
        OC_HOST_VER=$(kubectl exec -n ai "$OC_POD" -c app -- bash -lc \
            'jq -r .version /home/node/.openclaw/lib/node_modules/openclaw/package.json 2>/dev/null' 2>/dev/null)
        OC_CODEX_PLUGIN_VER=$(kubectl exec -n ai "$OC_POD" -c app -- bash -lc \
            'jq -r .version /home/node/.openclaw/npm/node_modules/@openclaw/codex/package.json 2>/dev/null' 2>/dev/null)
        echo "  versions: host=$OC_HOST_VER managed @openclaw/codex=$OC_CODEX_PLUGIN_VER"
        if [ -n "$OC_HOST_VER" ] && [ -n "$OC_CODEX_PLUGIN_VER" ] && [ "$OC_HOST_VER" != "$OC_CODEX_PLUGIN_VER" ]; then
            log_critical "openclaw managed @openclaw/codex ($OC_CODEX_PLUGIN_VER) != host ($OC_HOST_VER) — codex harness will reject openai/* dispatch"
            add_critical_issue "openclaw host/plugin skew: @openclaw/codex $OC_CODEX_PLUGIN_VER vs host $OC_HOST_VER. The init script realigns it on boot — delete the pod to re-run init."
            INFRA_SVC_ISSUES=$((INFRA_SVC_ISSUES + 1))
        fi

        # Signal 2b: morning-briefing cron presence + last result. Looked up BY
        # NAME, not a hardcoded id — the id changes whenever the cron is recreated
        # (it was rm+re-added 2026-06-18 to fix a false "couldn't generate a
        # response" error), and a vanished cron must still be detectable (the
        # 2026.6.6 upgrade dropped it once → silent miss with the old id check).
        BRIEF_STATUS=$(kubectl exec -n ai "$OC_POD" -c app -- \
            bash -lc 'openclaw cron list --json 2>/dev/null' 2>/dev/null \
            | sed -n '/[[{]/,$p' \
            | jq -r 'if type=="array" then . else (.jobs // .crons // []) end
                     | map(select((.name // "") | test("Morning Briefing"; "i")))
                     | (.[0].state.lastRunStatus // "MISSING")' 2>/dev/null)
        echo "  Morning Briefing cron lastRunStatus=${BRIEF_STATUS:-unknown}"
        if [ -z "$BRIEF_STATUS" ] || [ "$BRIEF_STATUS" = "MISSING" ]; then
            log_critical "openclaw Daily Morning Briefing cron is MISSING — briefing will not run"
            add_critical_issue "openclaw morning-briefing cron (name ~ 'Daily Morning Briefing') not found — re-add it (openclaw cron add). It vanished during the 2026.6.6 upgrade once."
            INFRA_SVC_ISSUES=$((INFRA_SVC_ISSUES + 1))
        elif [ "$BRIEF_STATUS" = "error" ]; then
            log_critical "openclaw Morning Briefing cron last run errored"
            add_critical_issue "openclaw briefing cron lastRunStatus=error — check the dispatch canary below and pod logs for FailoverError / 'couldn't generate a response' / 'provider is not one of' / 'Missing bearer'."
            INFRA_SVC_ISSUES=$((INFRA_SVC_ISSUES + 1))
        elif [ "$BRIEF_STATUS" = "ok" ]; then
            log_success "openclaw Morning Briefing cron last run: ok"
        fi

        # Signal 2c: dispatch canary — the catch-all. Actually runs one agent turn
        # through the default model/harness. A failure means the agent cannot
        # answer, whatever the cause (auth drift, harness/model mismatch, stale
        # plugin, provider cooldown). No --deliver, throwaway session, short timeout.
        # Uses a distinctive sentinel (not "OK") so a CLI usage/parse error that
        # echoes the prompt back cannot be mistaken for a real reply. Failure
        # detection also catches usage errors ("Usage:" / "Try: openclaw" /
        # "unknown option") — a wrong flag must fail loudly, not silently pass.
        # (--light-context is NOT a valid `openclaw agent` flag — do not add it.)
        # Timeout is 300s, NOT 90s: since the model failover chain landed
        # (2026-08-18, agents.defaults.model.fallbacks) a codex-side outage
        # degrades to ollama/gemma4:26b on the Mac mini, and a COLD 26b can
        # exceed the 120s LLM idle timeout before the chain moves to
        # gemma4:e2b-mlx. At 90s this reported a false critical while the agent
        # was in fact answering.
        CANARY_OUT=$(kubectl exec -n ai "$OC_POD" -c app -- bash -lc \
            'openclaw agent -m "Reply with exactly this token and nothing else: CANARY7F3" --session-id healthcheck-canary --timeout 300 2>&1' 2>/dev/null | tail -4)
        # Success is checked FIRST. With a fallback chain the run can emit
        # intermediate failover/auth noise on its way to a good answer, so the
        # sentinel — not the absence of scary strings — is the pass condition.
        if printf '%s' "$CANARY_OUT" | grep -q 'CANARY7F3'; then
            # The chain means "it replied" no longer implies "codex is healthy":
            # a dead primary is invisible here because the local model answers.
            # Ask the gateway log which candidate actually served the turn, so a
            # silent permanent degrade still surfaces.
            CANARY_SERVED=$(kubectl logs -n ai "$OC_POD" -c app --tail=400 2>/dev/null \
                | grep 'model-fallback/decision' | grep 'decision=candidate_succeeded' | tail -1)
            CANARY_REQ=$(printf '%s' "$CANARY_SERVED" | grep -oE 'requested=[^ ]+' | cut -d= -f2)
            CANARY_CAND=$(printf '%s' "$CANARY_SERVED" | grep -oE 'candidate=[^ ]+' | cut -d= -f2)
            if [ -n "$CANARY_CAND" ] && [ -n "$CANARY_REQ" ] && [ "$CANARY_CAND" != "$CANARY_REQ" ]; then
                log_warning "openclaw dispatch canary: agent replied but DEGRADED — served by fallback ${CANARY_CAND} instead of ${CANARY_REQ}"
                # Classify the degrade HERE rather than telling the operator to run
                # `codex login status` and look for "usage limit". That command prints
                # only "Logged in using ChatGPT" — it reports the OAuth state and says
                # nothing about quota, so the old instruction could not discriminate
                # and pointed at a browser re-login for what is usually a quota reset.
                # The gateway already logs the real reason on the candidate_failed line.
                CANARY_FAIL=$(kubectl logs -n ai "$OC_POD" -c app --tail=800 2>/dev/null \
                    | grep 'model-fallback/decision' | grep 'decision=candidate_failed' \
                    | grep -F "candidate=${CANARY_REQ}" | tail -1)
                CANARY_REASON=$(printf '%s' "$CANARY_FAIL" | grep -oE 'reason=[^ ]+' | cut -d= -f2)
                CANARY_RESET=$(printf '%s' "$CANARY_FAIL" | grep -oE 'Next reset[^."]*' | head -1)
                if [ "$CANARY_REASON" = "rate_limit" ]; then
                    # Expected and self-healing: the Codex subscription window refills.
                    # Minor so it does not read as an outage, but still reported — a
                    # rate_limit that shows up EVERY cycle is a real capacity problem.
                    add_minor_issue "openclaw is on model fallback ${CANARY_CAND}: the Codex subscription usage limit is exhausted (reason=rate_limit). Self-heals at the reset. ${CANARY_RESET:-reset time not in the last 800 log lines}. No operator action unless this recurs every cycle. See docs/sops/ai-integration.md."
                else
                    add_major_issue "openclaw is running on model fallback ${CANARY_CAND} (primary ${CANARY_REQ} failing, reason=${CANARY_REASON:-unknown}). Chat/skills/briefing still work, but on the local model. NOT a quota exhaustion — that reports reason=rate_limit. Check the codex OAuth refresh chain: 'codex login status' shows the login state, and the pod log carries the raw provider error. Recovery is 'codex login --device-auth' plus a pod restart. See docs/sops/ai-integration.md."
                fi
            else
                log_success "openclaw dispatch canary: agent replied (Codex/OAuth path healthy)"
            fi
        elif printf '%s' "$CANARY_OUT" | grep -qiE 'FailoverError|does not support|provider is not one of|Missing bearer|No API key|Unauthorized|failed before reply|Usage:|Try: openclaw|unknown option'; then
            CANARY_ERR=$(printf '%s' "$CANARY_OUT" | grep -oiE 'FailoverError[^<]*|does not support [^.]*|Missing bearer[^,]*|No API key[^"]*|unknown option[^ ]*|Try: openclaw[^|]*' | head -1)
            log_critical "openclaw dispatch canary FAILED: ${CANARY_ERR:-see pod logs}"
            add_critical_issue "openclaw agent dispatch canary failed — the agent cannot answer (chat, skills, briefing all affected), and the model fallback chain did not save it. Reason: ${CANARY_ERR:-unknown}. Catch-all signal for auth/harness/model/provider failure."
            INFRA_SVC_ISSUES=$((INFRA_SVC_ISSUES + 1))
        else
            log_warning "openclaw dispatch canary inconclusive: $(printf '%s' "$CANARY_OUT" | tr '\n' ' ' | tail -c 100)"
        fi

        # Signal 2d: daily-operation sweep cron cadence. The in-cluster OpenClaw
        # cron ("Daily Operation Sweep …", every 48h @ 04:00 Europe/Berlin) is the
        # ONLY automated trigger for the Mac-side daily sweep; if it stalls, the
        # sweep runs only when the operator asks. Looked up BY NAME (id changes on
        # recreate, like 2b). Uses the cron's OWN state.lastRunAtMs/lastRunStatus
        # (authoritative gateway record) — NOT a sweep_cycles trigger heuristic.
        # A sweep_cycles-trigger check mis-fires when the daily-operation routine
        # doesn't propagate SWEEP_TRIGGER=cron (cron cycles get stamped 'manual'),
        # which is what produced a false "sweep cron dead since 2026-07-17"
        # finding during the 2026-07-17 power-outage recovery. That finding was a
        # one-off manual insert (section=infra) with no recurring detector, so it
        # never auto-resolved after the cron recovered on 07-27. THIS check is the
        # durable fix: it runs every sweep and its section=health finding
        # auto-resolves once the cron fires again.
        SWEEP_CRON_JSON=$(kubectl exec -n ai "$OC_POD" -c app -- \
            bash -lc 'openclaw cron list --json 2>/dev/null' 2>/dev/null \
            | sed -n '/[[{]/,$p' \
            | jq -r 'if type=="array" then . else (.jobs // .crons // []) end
                     | map(select((.name // "") | test("Operation Sweep"; "i")))
                     | (.[0] // {})
                     | "\(.state.lastRunStatus // "MISSING")|\(.state.lastRunAtMs // 0)"' 2>/dev/null)
        SWEEP_CRON_STATUS="${SWEEP_CRON_JSON%%|*}"
        SWEEP_CRON_LASTMS="${SWEEP_CRON_JSON##*|}"
        if [ -z "$SWEEP_CRON_STATUS" ] || [ "$SWEEP_CRON_STATUS" = "MISSING" ]; then
            log_critical "openclaw Daily Operation Sweep cron is MISSING — the daily sweep has no automated trigger"
            add_critical_issue "openclaw daily-operation sweep cron (name ~ 'Operation Sweep') not found — re-add it (openclaw cron add). Without it the sweep only runs when manually triggered."
            INFRA_SVC_ISSUES=$((INFRA_SVC_ISSUES + 1))
        else
            SWEEP_AGE_H=""
            if [ -n "$SWEEP_CRON_LASTMS" ] && [ "$SWEEP_CRON_LASTMS" -gt 0 ] 2>/dev/null; then
                SWEEP_AGE_H=$(( ($(date +%s) - SWEEP_CRON_LASTMS/1000) / 3600 ))
            fi
            echo "  Operation Sweep cron lastRunStatus=$SWEEP_CRON_STATUS lastRun=${SWEEP_AGE_H:-?}h ago"
            if [ "$SWEEP_CRON_STATUS" = "error" ]; then
                log_critical "openclaw Daily Operation Sweep cron last run errored"
                add_critical_issue "openclaw daily-operation sweep cron lastRunStatus=error — the autonomous sweep trigger failed; check its lastErrorReason (openclaw cron show <id>). Without it the sweep only runs when manually triggered."
                INFRA_SVC_ISSUES=$((INFRA_SVC_ISSUES + 1))
            elif [ -n "$SWEEP_AGE_H" ] && [ "$SWEEP_AGE_H" -gt 100 ]; then
                log_warning "openclaw Daily Operation Sweep cron last fired ${SWEEP_AGE_H}h ago (>100h; every-48h schedule) — automated trigger may be stalled"
                add_major_issue "openclaw daily-operation sweep cron last fired ${SWEEP_AGE_H}h ago (expected every 48h) — the automated sweep trigger may be stalled; sweeps run only when manually invoked until it recovers."
            else
                log_success "openclaw Daily Operation Sweep cron: last run ok (${SWEEP_AGE_H:-recent}h ago)"
            fi
        fi

        # openclaw voice — the morning-briefing voice note is generated by the
        # local Qwen3-TTS server (OPENCLAW_TTS_FALLBACK_URL points at <host>/v1 so
        # the health endpoint is <host>/health). The paid ElevenLabs fallback was
        # retired 2026-06-15 — local generation is the only path now, so local TTS
        # down means voice is fully broken (no fallback to degrade to).
        echo "openclaw voice:"
        TTS_HEALTH=$(kubectl exec -n ai "$OC_POD" -c app -- bash -lc \
            'u="${OPENCLAW_TTS_FALLBACK_URL%/v1}"; curl -fsS -m5 "$u/health" 2>/dev/null' 2>/dev/null)
        TTS_OK=0
        if printf '%s' "$TTS_HEALTH" | grep -q '"status"[: ]*"ok"'; then
            TTS_OK=1
            TTS_MODEL_LOADED=$(printf '%s' "$TTS_HEALTH" | jq -r '.model_loaded // empty' 2>/dev/null)
            echo "  local TTS: ok (model_loaded=$TTS_MODEL_LOADED)"
        else
            echo "  local TTS: unreachable"
        fi

        if [ "$TTS_OK" -eq 0 ]; then
            log_critical "openclaw voice: local TTS unreachable — no voice path"
            add_critical_issue "openclaw voice broken — local Qwen3-TTS (192.168.30.111:8000) unreachable; morning-briefing voice will fail. Restart the mlx-tts server."
            INFRA_SVC_ISSUES=$((INFRA_SVC_ISSUES + 1))
        else
            log_success "openclaw voice: local TTS ok"
        fi

        # Last morning-briefing voice outcome — catches voice breakage even when
        # codex auth is healthy (the briefing log records 'voice sent' on success).
        BRIEF_LOG=$(kubectl exec -n ai "$OC_POD" -c app -- bash -lc \
            'tail -40 ~/clawd/state/morning-briefing/briefing.log 2>/dev/null; tail -40 ~/clawd/.tmp/morning-briefing/*.log 2>/dev/null' 2>/dev/null)
        if [ -n "$BRIEF_LOG" ]; then
            LAST_VOICE_SENT=$(printf '%s' "$BRIEF_LOG" | grep -E "voice sent" | tail -1)
            if [ -n "$LAST_VOICE_SENT" ]; then
                VTS_RAW=$(printf '%s' "$LAST_VOICE_SENT" | awk '{print $1}')
                VTS=$(date -d "$VTS_RAW" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "${VTS_RAW%%+*}" +%s 2>/dev/null || echo "")
                if [ -n "$VTS" ]; then
                    VAGE_H=$(( ($(date +%s) - VTS) / 3600 ))
                    echo "  last briefing voice sent ${VAGE_H}h ago"
                    if [ "$VAGE_H" -gt 26 ]; then
                        log_warning "openclaw morning briefing: last voice sent ${VAGE_H}h ago (>26h)"
                        add_major_issue "openclaw morning-briefing voice last delivered ${VAGE_H}h ago — daily briefing may be failing."
                    else
                        log_success "openclaw morning briefing: voice delivered ${VAGE_H}h ago"
                    fi
                else
                    log_success "openclaw morning briefing: voice sent (timestamp unparsed)"
                fi
            else
                echo "  no 'voice sent' line in recent briefing log"
                log_warning "openclaw morning briefing: no recent 'voice sent' confirmation"
                add_major_issue "openclaw morning-briefing voice not confirmed sent — check ~/clawd/state/morning-briefing/briefing.log"
            fi
        fi

        # openclaw skills + tool deps (shallow presence check)
        echo "openclaw skills:"
        SKILLS_PROBE=$(kubectl exec -n ai "$OC_POD" -c app -- bash -lc '
            miss=""
            for s in say ha mail sure paperless nc contacts pallet; do
                [ -x "$HOME/.openclaw/bin/$s" ] || miss="$miss $s"
            done
            echo "SKILLS:$miss"
            tmiss=""
            for t in kubectl ffmpeg jq hactl; do
                command -v "$t" >/dev/null 2>&1 || tmiss="$tmiss $t"
            done
            if [ -n "$PLAYWRIGHT_BROWSERS_PATH" ]; then
                ls "$PLAYWRIGHT_BROWSERS_PATH"/chromium*/chrome-linux*/chrome >/dev/null 2>&1 || tmiss="$tmiss chromium"
            fi
            echo "TOOLS:$tmiss"
        ' 2>/dev/null)
        SK_MISS=$(printf '%s' "$SKILLS_PROBE" | sed -n 's/^SKILLS://p' | xargs)
        TL_MISS=$(printf '%s' "$SKILLS_PROBE" | sed -n 's/^TOOLS://p' | xargs)
        if [ -n "$SK_MISS" ]; then
            log_warning "openclaw skills missing: $SK_MISS"
            add_major_issue "openclaw skill binaries missing in ~/.openclaw/bin: $SK_MISS — re-check skills-configmap seeding."
            INFRA_SVC_ISSUES=$((INFRA_SVC_ISSUES + 1))
        elif [ -n "$SKILLS_PROBE" ]; then
            log_success "openclaw skills: all present (say ha mail sure paperless nc contacts pallet)"
        fi
        if [ -n "$TL_MISS" ]; then
            log_warning "openclaw tool deps missing: $TL_MISS"
            add_minor_issue "openclaw tool deps not resolvable in-pod: $TL_MISS — dependent skills will fail."
        elif [ -n "$SKILLS_PROBE" ]; then
            echo "  tool deps: kubectl ffmpeg jq hactl chromium ok"
        fi
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
    AUTH_FAILURES=$(safe_count "kubectl logs -n kube-system -l app.kubernetes.io/name=authentik,app.kubernetes.io/component=server --tail=200 --since=24h 2>&1 | grep -iE 'authentication.*failed|login.*failed|invalid.*credentials' | wc -l" "auth-failures")
    echo "Authentik auth failures (last 24h): $AUTH_FAILURES"
    echo ""

    # Check for RBAC permission errors in audit/controller logs
    RBAC_ERRORS=$(safe_count "kubectl logs -n kube-system -l component=kube-apiserver --tail=100 --since=1h 2>&1 | grep -i 'RBAC.*denied\|forbidden.*reason' | wc -l" "rbac-errors")
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
    BACKUP_JOBS=$(safe_count "kubectl get jobs -n storage --sort-by=.metadata.creationTimestamp 2>/dev/null | tail -5 | grep '1/1' | wc -l" "backup-jobs")
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
    # This section counted pods for three apps and then logged success
    # unconditionally — it asserted NOTHING, so all three could report zero
    # running pods and the section still ended green. LH_PODS did exactly that:
    # its selector was app.kubernetes.io/name=longhorn-manager, but that label
    # is "longhorn" on those pods (app=longhorn-manager is the right one), so it
    # read 0 with three managers running and nothing noticed (fixed 2026-08-22).
    APP_DOWN=0
    for _spec in \
        "Authentik|kube-system|app.kubernetes.io/name=authentik" \
        "Grafana|monitoring|app.kubernetes.io/name=grafana" \
        "Longhorn manager|storage|app=longhorn-manager"; do
        _name="${_spec%%|*}"; _rest="${_spec#*|}"
        _ns="${_rest%%|*}"; _sel="${_rest#*|}"
        _n=$(safe_count "kubectl get pods -n $_ns -l $_sel --no-headers 2>/dev/null | grep -c 'Running'" \
                        "app-pods-${_ns}-${_sel}")
        echo "$_name: $_n Running pod(s) [ns=$_ns selector=$_sel]"
        if [ "${_n:-0}" -eq 0 ] 2>/dev/null; then
            APP_DOWN=$((APP_DOWN+1))
            log_critical "$_name has NO Running pods (ns=$_ns, selector=$_sel)"
            add_critical_issue "$_name has no Running pods (ns=$_ns, selector=$_sel) — app down, or the selector no longer matches"
        fi
    done

    if [ "$APP_DOWN" -eq 0 ]; then
        log_success "Application-specific checks: all 3 apps have Running pods"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 31: Home Assistant Integration Health"
{
    echo "Already covered in Section 22"
    log_info "See Section 22 for detailed Home Assistant integration analysis"
} >> "$OUTPUT_FILE" 2>&1

log_section "Home Assistant Health (via hactl doctor)"
{
    # Wires the hactl `doctor` checks that don't overlap the bash sections
    # above (config_entries = failed-setup integrations, zombie_devices =
    # orphan/stalled/disabled/restored device-registry entries).
    #
    # Defensive by design: if hactl, mise, or HASS creds are missing, this
    # section logs a single skip line and continues — it is informational
    # enrichment, never a script-fatal dependency.

    # 1. Resolve how to invoke hactl. hactl lives in its OWN repo
    #    (/Users/mu/code/hactl) with a separate mise-pinned Python. The bare
    #    `hactl` PATH shim FAILS with "No version is set for shim" when run
    #    from THIS repo, because cberg's .mise.toml doesn't define hactl — so
    #    `command -v hactl` is a trap (it resolves the broken shim). Invoke
    #    via `mise exec` from the hactl repo so mise picks the right version;
    #    fall back to a direct install path. run_hactl() is the single entry.
    HACTL_DIR=/Users/mu/code/hactl
    HACTL_OK=0
    if [ -f "$HACTL_DIR/.mise.toml" ] && command -v mise >/dev/null 2>&1 \
        && (cd "$HACTL_DIR" && mise which hactl) >/dev/null 2>&1; then
        run_hactl() { (cd "$HACTL_DIR" && mise exec -- hactl "$@"); }
        HACTL_OK=1
    else
        for cand in \
            /Users/mu/.local/share/mise/installs/python/3.13.13/bin/hactl \
            /Users/mu/.local/bin/hactl \
            /opt/homebrew/bin/hactl; do
            if [ -x "$cand" ]; then
                HACTL_CAND="$cand"
                run_hactl() { "$HACTL_CAND" "$@"; }
                HACTL_OK=1
                break
            fi
        done
    fi

    # 2. Source HASS creds from the hactl repo's .env if not already in env.
    #    Use ${VAR:-} expansion because `set -u` is active script-wide.
    if [ -z "${HASS_URL:-}" ] || [ -z "${HASS_TOKEN:-}" ]; then
        if [ -r /Users/mu/code/hactl/.env ]; then
            set -a
            # shellcheck disable=SC1091
            . /Users/mu/code/hactl/.env
            set +a
        fi
    fi

    if [ "$HACTL_OK" -eq 0 ] || [ -z "${HASS_URL:-}" ] || [ -z "${HASS_TOKEN:-}" ]; then
        echo "hactl unavailable, skipping HA-side health check"
    else
        # First: apply haghs_ignore labels to known-flaky devices from
        # noise_allowlist.yaml so the doctor's unavailable_entity count
        # reflects suppressions. Idempotent — already-labeled devices are
        # no-ops. Failures are non-fatal: doctor still runs.
        allowlist_path="$NOISE_ALLOWLIST"
        if [ -r "$allowlist_path" ]; then
            label_output=$(run_hactl label apply --from-allowlist "$allowlist_path" --label haghs_ignore --yes 2>&1)
            label_rc=$?
            if [ "$label_rc" -eq 0 ]; then
                applied=$(printf '%s\n' "$label_output" | grep -c '^[[:space:]]*+label haghs_ignore on device' || true)
                noop=$(printf '%s\n' "$label_output" | awk '/^Result:/{for(i=1;i<=NF;i++) if($i=="no-op."){print $(i-1); exit}}')
                noop=${noop:-0}
                echo "label apply: ${applied} new, ${noop} already-labeled (no-op)"
            else
                echo "label apply: rc=$label_rc — skipping (doctor still runs)"
                printf '%s\n' "$label_output" | head -5
            fi
        fi

        # hactl `doctor` exits non-zero when a single check's HA API call
        # transiently blips (a ClickException bubbles up), NOT only when it
        # finds real problems — and the old combined `--check a --check b`
        # form silently ran only the LAST check (hactl's --check is
        # single-valued). That pairing produced a recurring, non-actionable
        # "hactl doctor exited with rc=1" finding while config_entries was
        # never actually checked. Fix: run each scoped check on its own,
        # retry with backoff to ride out a transient blip, and route on the
        # Summary block — a run that printed a Summary is a real result (parse it for
        # genuine HA findings regardless of exit code); only a persistent
        # no-Summary failure across both checks is surfaced.
        hactl_summaries=""
        hactl_bodies=""
        for chk in config_entries zombie_devices; do
            chk_out=""
            # Up to 3 attempts with progressive backoff (5s, 10s ≈ 15s/check) so
            # a longer transient HA API blip — the cause of the recurring
            # false-positive no-report finding — is ridden out before flagging.
            # A genuinely unreachable API still fails all 3 and surfaces it.
            for attempt in 1 2 3; do
                chk_out=$(run_hactl doctor --check "$chk" 2>&1)
                printf '%s\n' "$chk_out" | grep -q '^=== Summary ===' && break
                [ "$attempt" -lt 3 ] && sleep $((attempt * 5))
            done
            if printf '%s\n' "$chk_out" | grep -q '^=== Summary ==='; then
                hactl_summaries="${hactl_summaries}${chk_out}"$'\n'
                hactl_bodies="${hactl_bodies}$(printf '%s\n' "$chk_out" | awk '/^=== Summary ===/{exit} /^---/{p=1} p')"$'\n'
            else
                echo "hactl doctor --check $chk: no summary after retry (transient HA API?) — first 10 lines:"
                printf '%s\n' "$chk_out" | head -10
            fi
        done

        if [ -z "$hactl_summaries" ]; then
            # Both checks failed to produce any report across retries — a
            # genuine, persistent hactl/HA-API problem worth a minor flag.
            add_minor_issue "hactl doctor produced no report (HA API unreachable?)"
        else
            # Echo the Integrations + Zombie Devices section bodies inline so a
            # human reading health-check-current.md sees actual findings.
            echo "--- hactl doctor findings ---"
            printf '%s\n' "$hactl_bodies"
            echo ""

            # Sum Critical/Warnings across each scoped check's Summary block.
            crit_count=$(printf '%s\n' "$hactl_summaries" \
                | awk '/^=== Summary ===/{s=1;next} s&&/^[[:space:]]+Critical:/{c+=$2} s&&/^[[:space:]]+Warnings:/{w+=$2;s=0} END{print c+0}')
            warn_count=$(printf '%s\n' "$hactl_summaries" \
                | awk '/^=== Summary ===/{s=1;next} s&&/^[[:space:]]+Critical:/{c+=$2} s&&/^[[:space:]]+Warnings:/{w+=$2;s=0} END{print w+0}')
            crit_count=${crit_count:-0}
            warn_count=${warn_count:-0}
            overall=OK
            [ "$warn_count" -gt 0 ] 2>/dev/null && overall=WARNING
            [ "$crit_count" -gt 0 ] 2>/dev/null && overall=CRITICAL

            echo "hactl summary: critical=$crit_count warnings=$warn_count overall=$overall"

            if [ "$crit_count" -gt 0 ] 2>/dev/null; then
                log_critical "HA: $crit_count critical hactl finding(s)"
                add_major_issue "HA: $crit_count critical hactl finding(s) — run \`hactl doctor\` for detail"
            elif [ "$warn_count" -gt 0 ] 2>/dev/null; then
                log_warning "HA: $warn_count warning hactl finding(s)"
                add_minor_issue "HA: $warn_count warning hactl finding(s) — run \`hactl doctor\` for detail"
            else
                log_success "hactl doctor: HA integrations + zombie devices clean"
            fi
        fi
    fi
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
        Z2M_COORD_ERRORS=$(safe_count "kubectl logs -n home-automation deployment/zigbee2mqtt --tail=100 --since=24h 2>&1 | grep -iE '(error|ERROR)' | grep -v 'WARN' | wc -l" "z2m-coord-errors")
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

                if [ "$battery_int" -lt 10 ]; then
                    CRITICAL_BATTERIES="${CRITICAL_BATTERIES}  - ${friendly} (${battery}%)\n"
                    CRITICAL_COUNT=$((CRITICAL_COUNT + 1))
                elif [ "$battery_int" -lt 10 ]; then
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

        echo "🔴 CRITICAL (<10%) - Replace Immediately:"
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

        echo "🔵 MONITOR (10-50%) - Watch Closely:"
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
            log_warning "CRITICAL: $CRITICAL_COUNT devices with batteries <10%"
            add_major_issue "Critical battery levels (<10%): $CRITICAL_COUNT devices need immediate replacement"
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

    # ES exporter REJECTION rate (added 2026-08-07 — closes the silent-drop gap:
    # readiness/restarts/volume said "healthy" while ES rejected ~750 docs/hr).
    # Two silent-loss classes in the edot logs:
    #   - "failed to index document" / document_parsing_exception  (whole doc lost)
    #   - "validation errors"  (metric points dropped: cumulative histograms,
    #     Empty-ValueType) — see docs/sops/monitoring.md "ES rejected documents"
    # NOTE: `grep -c ... || true` is WRONG here. grep -c already prints 0 and
    # then exits 1 on no-match, so the fallback APPENDS a second zero, yielding
    # "0\n0" — and the `-gt` tests below then abort with "integer expression
    # expected". Net effect: whenever the count was genuinely zero, this
    # silent-telemetry-loss detector could not evaluate at all. Use `|| true` to
    # swallow grep's exit status without adding output, and strip any newline.
    EDOT_REJECTS=$(kubectl logs -n monitoring deploy/edot-collector --since=1h 2>/dev/null | \
        grep -cE "document_parsing_exception|failed to index document" || true)
    EDOT_REJECTS=$(printf '%s' "${EDOT_REJECTS:-0}" | tr -d '\n')
    EDOT_VALIDATION=$(kubectl logs -n monitoring deploy/edot-collector --since=1h 2>/dev/null | \
        grep -c "validation errors" || true)
    EDOT_VALIDATION=$(printf '%s' "${EDOT_VALIDATION:-0}" | tr -d '\n')
    # Count dropped POINTS, not warn LINES. The exporter batches every rejected
    # point of a flush into ONE "validation errors" line (~18 reasons per line),
    # so the LINE count barely moves no matter how much telemetry is lost.
    # That is exactly how Envoy Gateway phase 0 silently added 6720 dropped
    # points/h (34 histogram families across envoy-{internal,external} and the
    # envoy-gateway control plane) on 2026-08-15 while EDOT_VALIDATION stayed
    # flat at ~362/h and this check reported healthy. Count the reasons.
    EDOT_DROPPED_POINTS=$(kubectl logs -n monitoring deploy/edot-collector --since=1h 2>/dev/null | \
        grep -oE "dropping [a-z]+ [a-z]+|invalid number data point" | wc -l | tr -d ' \n')
    EDOT_DROPPED_POINTS=${EDOT_DROPPED_POINTS:-0}
    # Distinct metric families behind the drops — naming them makes the fix
    # obvious: add each to cumulativetodelta/es-histograms in
    # kubernetes/apps/monitoring/edot-collector/app/configmap.yaml
    EDOT_DROPPED_NAMES=$(kubectl logs -n monitoring deploy/edot-collector --since=1h 2>/dev/null | \
        grep -oE 'histogram \\"[a-zA-Z0-9_]+' | sed 's/^histogram \\"//' | sort -u | head -8 | tr '\n' ' ')
    echo "edot-collector ES rejections last 1h: parse=${EDOT_REJECTS} validation_lines=${EDOT_VALIDATION} dropped_points=${EDOT_DROPPED_POINTS}"
    if [ "${EDOT_REJECTS:-0}" -gt 10 ]; then
        log_warning "edot-collector: ES rejecting documents (${EDOT_REJECTS}/h document_parsing) — telemetry silently lost"
        add_minor_issue "edot ES document rejections: ${EDOT_REJECTS}/h (SOP: monitoring.md 'ES rejected documents')"
    fi
    # 100/h threshold: one un-converted histogram family on a single 30s-scraped
    # target produces ~120 dropped points/h, so this trips on the FIRST new
    # rejected family rather than waiting for a component to add dozens.
    if [ "${EDOT_DROPPED_POINTS:-0}" -gt 100 ]; then
        log_warning "edot-collector: ${EDOT_DROPPED_POINTS} metric points/h silently dropped by ES (families: ${EDOT_DROPPED_NAMES:-unknown})"
        add_minor_issue "edot ES dropped metric points: ${EDOT_DROPPED_POINTS}/h across families [${EDOT_DROPPED_NAMES:-unknown}] (SOP: monitoring.md 'ES rejected documents')"
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

    # ES-side per-DOCUMENT rejection rate (added 2026-08-18, closes backlog
    # item edot-rejection-monitoring-gap). The send_failed_* check above only
    # counts whole requests the exporter gave up on; during the k8s-Event
    # managedFields "." incident every bulk request returned 200 while ES
    # rejected individual documents (document_parsing_exception), so
    # send_failed stayed 0 through weeks of silent telemetry loss. The
    # elasticsearchexporter labels every document's outcome on
    # otelcol.elasticsearch.docs.processed_total:
    #   success | failed_client (per-doc 4xx mapping/parse rejection — the
    #   incident class) | failed_server | too_many | retried.
    # Failure-outcome series are only born on the first rejection, so an empty
    # increase() result means 0 (healthy) — while an ABSENT success series
    # means the SLI itself is blind (edot self-telemetry not scraped), which
    # is a warning, not a pass. Complements the log-grep in this section:
    # that covers 1h of the CURRENT pod's logs only; this counter survives
    # pod restarts and covers 6h. SOP: monitoring.md 'ES Rejected Documents'.
    ES_DOC_REJECTS=$(prom_query 'sum by (outcome) (increase({__name__="otelcol.elasticsearch.docs.processed_total",outcome!~"success|retried"}[6h]))')
    ES_DOC_PROCESSED=$(prom_query 'sum(rate({__name__="otelcol.elasticsearch.docs.processed_total"}[15m]))')
    REJECT_SUMMARY=$(echo "$ES_DOC_REJECTS" | python3 -c "
import sys, json
try:
    r = json.load(sys.stdin)['data']['result']
    total = sum(float(x['value'][1]) for x in r)
    parts = ', '.join(f\"{x['metric'].get('outcome','?')}={float(x['value'][1]):.0f}\" for x in r if float(x['value'][1]) > 0)
    print(f'{total:.0f}|{parts}')
except: print('0|')
" 2>/dev/null)
    REJECT_TOTAL=${REJECT_SUMMARY%%|*}
    REJECT_PARTS=${REJECT_SUMMARY#*|}
    REJECT_TOTAL=${REJECT_TOTAL:-0}
    PROCESSED_RATE=$(echo "$ES_DOC_PROCESSED" | python3 -c "
import sys, json
try:
    r = json.load(sys.stdin)['data']['result']
    print(f'{float(r[0][\"value\"][1]):.1f}' if r else 'absent')
except: print('absent')
" 2>/dev/null)
    echo "ES per-doc rejections (6h, docs.processed outcome!=success): ${REJECT_TOTAL} (ingest rate: ${PROCESSED_RATE} docs/sec)"
    if [ "$PROCESSED_RATE" = "absent" ]; then
        log_warning "otelcol.elasticsearch.docs.processed absent from Prometheus — the ES rejection SLI is blind (edot self-telemetry not scraped)"
        add_minor_issue "edot ES rejection SLI blind: docs.processed metric absent from Prometheus (SOP: monitoring.md 'ES Rejected Documents')"
    elif [ "${REJECT_TOTAL}" -gt 3000 ]; then
        # ≈500 docs/h sustained. The managedFields incident ran at ~750
        # rejected docs/h, so it trips this within ~4h instead of after weeks;
        # normal state is exactly 0, so no false-positive headroom is needed.
        log_critical "ES rejecting documents at incident scale: ${REJECT_TOTAL} docs in 6h [${REJECT_PARTS}] — telemetry silently lost (SOP: monitoring.md 'ES Rejected Documents')"
        add_critical_issue "edot ES per-doc rejections: ${REJECT_TOTAL}/6h [${REJECT_PARTS}] (SOP: monitoring.md 'ES Rejected Documents')"
    elif [ "${REJECT_TOTAL}" -gt 60 ]; then
        # ≥10/h — same sensitivity as the 1h log-grep parse threshold above
        log_warning "ES rejecting documents: ${REJECT_TOTAL} docs in 6h [${REJECT_PARTS}]"
        add_minor_issue "edot ES per-doc rejections: ${REJECT_TOTAL}/6h [${REJECT_PARTS}] (SOP: monitoring.md 'ES Rejected Documents')"
    else
        log_success "ES per-doc rejection rate healthy (${REJECT_TOTAL} non-success docs in 6h, ingest ${PROCESSED_RATE} docs/sec)"
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
        # Free the port first: leaked port-forwards from prior/crashed runs (or a
        # concurrent sweep sibling) leave 9201 bound, so a fresh `kubectl
        # port-forward 9201:9200` fails with "address already in use" and the
        # health probe reports "unknown" forever. Same preflight the 9202
        # enrichment block already uses. (Guard below still degrades safely.)
        lsof -ti:9201 2>/dev/null | xargs kill 2>/dev/null || true
        kubectl port-forward -n monitoring svc/elasticsearch-es-http 9201:9200 > /dev/null 2>&1 &
        ES_PF_PID=$!

        # Poll for port-forward + ES readiness instead of a fixed sleep. A fixed
        # `sleep 3` races the port-forward: when ES/PF isn't ready in time the
        # health probe returns empty ("unknown") AND every subsequent _count
        # falls through to `|| echo 0`, emitting FALSE "0 documents / ingestion
        # stalled" majors while ingestion is actually live. Retry the health
        # probe up to ~20s; only trust the ingestion checks once ES answered.
        ES_STATUS="unknown"
        for _es_try in $(seq 1 20); do
            ES_STATUS=$(curl -k -s -u "elastic:$ES_PW_EARLY" "https://localhost:9201/_cluster/health" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
            case "$ES_STATUS" in green|yellow|red) break ;; esac
            sleep 1
        done
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

        if [ "$ES_STATUS" = "unknown" ]; then
            log_warning "ES health probe did not respond within timeout - skipping OTel ingestion measurement (measurement error, not a confirmed outage)"
        else
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
        fi  # end ES_STATUS != unknown guard

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

        # Query error-level logs by body.text WILDCARD (case-insensitive) minus NOERROR.
        # Do NOT use severity_text/severity_number: BOTH are dead in this pipeline —
        # 28 of 3.49M docs, all INFO (verified 2026-08-16); the OTel receiver is not
        # parsing levels into structured severity. Two prior attempts failed SILENTLY:
        # `body` is an object (matched nothing); `match` on the body.text KEYWORD is
        # exact-equality (matched only literal "error", ~0). That false 0 hid two DNS
        # outages this week. The count is noisy (benign substrings + the Frigate camera,
        # a tracked finding) and is display-only — the per-namespace breakdown is what
        # makes it useful. A clean signal needs the edot severity-parse fix (separate).
        # As of 2026-08-18 the VERDICT honours that comment: the cluster-wide total no
        # longer raises an issue on its own; the per-namespace buckets do. See the
        # rationale block at the verdict itself.
        ERROR_DATA=$(curl -k -u "elastic:$ES_PASSWORD" -X GET "https://localhost:9200/${LOG_DS}/_search" -H 'Content-Type: application/json' -d '{
          "size": 0,
            "track_total_hits": true,
          "query": {
            "bool": {
              "should": [
                  {"wildcard": {"body.text": {"value": "*error*", "case_insensitive": true}}},
                  {"wildcard": {"body.text": {"value": "*fatal*", "case_insensitive": true}}}
                ],
                "minimum_should_match": 1,
                "must_not": [
                  {"wildcard": {"body.text": {"value": "*noerror*", "case_insensitive": true}}}
                ],
                "filter": [{"range": {"@timestamp": {"gte": "now-24h"}}}]
            }
          },
          "aggs": {
            "by_namespace": {
              "terms": {"field": "resource.attributes.k8s.namespace.name", "size": 25}
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

          # --- Fatal / connection-exhaustion / OOM log TEXT via body.text wildcard ---
          #
          # severity_text is dead (see §34); `match` on the `body` object matched 0,
          # so wildcards on body.text are the only working path.
          #
          # REWRITTEN 2026-08-18 (finding F-d97cfe78). The old single "FATAL/OOM"
          # counter was ~93% false positive and STRUCTURALLY COULD NEVER CLEAR: its
          # threshold was `>0 => CRITICAL`, but its match set was dominated by
          # noise that recurs on every ordinary pod restart. Measured composition of
          # the 215 hits in the 24h window on 2026-08-18:
          #     100  Rails empty-message FATAL headers ("... FATAL -- :", no message)
          #      50  "FATAL SignalException: SIGTERM"  (clean shutdown, showcase pods)
          #      36  postgres "sorry, too many clients already" (restart-tied bursts)
          #      16  "GET /typo3/gfx/icon_fatalerror.gif" -- a GIF FILENAME that
          #          happens to contain the substring "fatalerror". Not an error at all.
          #       9  role/database "... does not exist" (probe misconfiguration)
          #       1  password authentication failed (real, minor)
          #       0  "out of memory"
          # Two authoritative controls both read 0 at the same instant:
          #   kubectl get events -A --field-selector reason=OOMKilled  -> 0
          #   pods with containerStatuses[].lastState.terminated.reason=OOMKilled -> 0
          # i.e. the assertion titled "FATAL/OOM" was reporting a CRITICAL OOM
          # condition while zero OOMs existed. The title was also wrong: OOM is
          # measured separately and authoritatively (OOM_COUNT, §above).
          #
          # It is now THREE independent assertions with honest titles and floors:
          #   A) FATAL_TEXT_COUNT  - fatal-level log text, benign classes excluded,
          #                          tiered thresholds (pod-restart noise can no
          #                          longer pin a permanent CRITICAL)
          #   B) CONN_EXHAUST_COUNT- DB connection-exhaustion, its own lower severity
          #   C) OOM_TEXT_COUNT    - out-of-memory log text, corroborates OOM_COUNT
          #
          # Exclusion classes and WHY each is safe (validated 2026-08-18):
          #   *icon_fatalerror*        filename substring collision, never an error
          #   *SignalException: SIGTERM* / *FATAL SIGTERM*   clean shutdown signal
          #   *FATAL -- :  (END-ANCHORED, no trailing *)     Rails logger emits the
          #       FATAL header and the message on separate records; the header alone
          #       carries ZERO information. End-anchoring is load-bearing: a real
          #       "FATAL -- : ActionView::Template::Error ..." still matches and is
          #       still counted. Do NOT add a trailing wildcard here.
          # Deliberately NOT excluded (genuine signals that must still surface):
          #   out of memory / OutOfMemoryError / Cannot allocate memory
          #   password authentication failed, role/database does not exist
        echo "Checking for critical error patterns..."

        # Shared benign-class exclusions (see rationale above)
        BENIGN_EXCL='
                  {"term": {"resource.attributes.k8s.namespace.name": "flux-system"}},
                  {"wildcard": {"body.text": {"value": "*database system is shutting down*", "case_insensitive": true}}},
                  {"wildcard": {"body.text": {"value": "*terminating connection due to administrator command*", "case_insensitive": true}}},
                  {"wildcard": {"body.text": {"value": "*not a git repository*", "case_insensitive": true}}},
                  {"wildcard": {"body.text": {"value": "*fatal_neterrors=*", "case_insensitive": true}}},
                  {"wildcard": {"body.text": {"value": "*icon_fatalerror*", "case_insensitive": true}}},
                  {"wildcard": {"body.text": {"value": "*SignalException: SIGTERM*", "case_insensitive": true}}},
                  {"wildcard": {"body.text": {"value": "*FATAL SIGTERM*", "case_insensitive": true}}},
                  {"wildcard": {"body.text": {"value": "*FATAL -- :", "case_insensitive": true}}}'

        # Connection-exhaustion class (counted separately in B, excluded from A)
        CONN_EXCL='
                  {"wildcard": {"body.text": {"value": "*too many clients already*", "case_insensitive": true}}},
                  {"wildcard": {"body.text": {"value": "*too many connections*", "case_insensitive": true}}},
                  {"wildcard": {"body.text": {"value": "*remaining connection slots*", "case_insensitive": true}}}'

        es_count() {
            # $1 = should-clause JSON array body, $2 = must_not-clause JSON array body
            curl -k -u "elastic:$ES_PASSWORD" -X GET "https://localhost:9200/${LOG_DS}/_search" \
              -H 'Content-Type: application/json' -d "{
              \"size\": 0,
              \"track_total_hits\": true,
              \"query\": {
                \"bool\": {
                  \"should\": [ $1 ],
                  \"minimum_should_match\": 1,
                  \"must_not\": [ $2 ],
                  \"filter\": [{\"range\": {\"@timestamp\": {\"gte\": \"now-24h\"}}}]
                }
              }
            }" 2>/dev/null | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin)['hits']['total']['value'])
except Exception:
    print('ERR')
" || echo "ERR"
        }

        # A) Fatal-level log text, benign + connection-exhaustion classes removed
        FATAL_TEXT_COUNT=$(es_count \
            '{"wildcard": {"body.text": {"value": "*fatal*", "case_insensitive": true}}}' \
            "${BENIGN_EXCL},${CONN_EXCL}")

        # B) DB connection exhaustion (own assertion, lower severity)
        CONN_EXHAUST_COUNT=$(es_count "$CONN_EXCL" \
            '{"term": {"resource.attributes.k8s.namespace.name": "flux-system"}},
             {"wildcard": {"body.text": {"value": "*database system is shutting down*", "case_insensitive": true}}}')

        # C) Out-of-memory log text. Corroborates the AUTHORITATIVE OOM_COUNT
        # (events reason=OOMKilled) -- OOMKilled is a pod-status reason, never a
        # log line, so this is a second, independent view. The mosquitto
        # "Client <id> disconnected due to out of memory" line is about the IoT
        # CLIENT device's memory, not ours -- excluded (498 vs 501 over 30d).
        OOM_SHOULD='
                  {"wildcard": {"body.text": {"value": "*out of memory*", "case_insensitive": true}}},
                  {"wildcard": {"body.text": {"value": "*OutOfMemoryError*", "case_insensitive": true}}},
                  {"wildcard": {"body.text": {"value": "*Cannot allocate memory*", "case_insensitive": true}}}'
        OOM_TEXT_COUNT=$(es_count "$OOM_SHOULD" \
            '{"term": {"resource.attributes.k8s.namespace.name": "flux-system"}},
             {"wildcard": {"body.text": {"value": "*disconnected due to out of memory*", "case_insensitive": true}}}')

        # A failed query must NOT read as a clean zero. es_count emits ERR on any
        # parse/transport failure; surface it instead of silently scoring green.
        if echo "${FATAL_TEXT_COUNT}${CONN_EXHAUST_COUNT}${OOM_TEXT_COUNT}" | grep -q ERR; then
            log_warning "Elasticsearch fatal/OOM queries failed - these three assertions did NOT run"
            add_major_issue "Elasticsearch log assertions did not run (query failure) - fatal/connection/OOM coverage is blind for this cycle"
            FATAL_TEXT_COUNT=0; CONN_EXHAUST_COUNT=0; OOM_TEXT_COUNT=0
            ES_LOG_ASSERTIONS_FAILED=1
        fi
        echo "  Fatal-level log lines, benign classes excluded (24h): $FATAL_TEXT_COUNT"
        echo "  DB connection-exhaustion log lines (24h):             $CONN_EXHAUST_COUNT"
        echo "  Out-of-memory log lines (24h):                        $OOM_TEXT_COUNT"
        echo "  (authoritative OOM controls: lastState within 24h=${OOM_LASTSTATE_24H:-0} [window-aligned], events=${OOM_COUNT:-0} [~1h TTL], pod lastState any age=${OOM_LASTSTATE:-0})"
        echo ""

        kill $PF_PID 2>/dev/null || true
        wait $PF_PID 2>/dev/null || true

        TOTAL_ERRORS_INT=$(echo "$TOTAL_ERRORS" | tr -cd '0-9' || echo "0")
        [ -z "$TOTAL_ERRORS_INT" ] && TOTAL_ERRORS_INT=0
        FATAL_TEXT_INT=$(echo "$FATAL_TEXT_COUNT" | tr -cd '0-9' || echo "0")
        [ -z "$FATAL_TEXT_INT" ] && FATAL_TEXT_INT=0
        CONN_EXHAUST_INT=$(echo "$CONN_EXHAUST_COUNT" | tr -cd '0-9' || echo "0")
        [ -z "$CONN_EXHAUST_INT" ] && CONN_EXHAUST_INT=0
        OOM_TEXT_INT=$(echo "$OOM_TEXT_COUNT" | tr -cd '0-9' || echo "0")
        [ -z "$OOM_TEXT_INT" ] && OOM_TEXT_INT=0

        if [ "${ES_LOG_ASSERTIONS_FAILED:-0}" -eq 1 ]; then
            log_info "Skipping fatal/connection/OOM verdicts - the queries did not run (see warning above)"
        else

        # A) Fatal-level text -- TIERED, not >0. Floors chosen against the measured
        # 24h baseline of 14 residual hits so ordinary pod-restart noise cannot pin
        # a permanent CRITICAL, while a genuine fatal storm still escalates.
        if [ "$FATAL_TEXT_INT" -ge 100 ]; then
            log_critical "Fatal-level log lines (excl. benign classes): $FATAL_TEXT_INT in 24h"
            add_critical_issue "Fatal-level log lines in Elasticsearch: $FATAL_TEXT_INT in 24h"
        elif [ "$FATAL_TEXT_INT" -ge 25 ]; then
            log_warning "Elevated fatal-level log lines: $FATAL_TEXT_INT in 24h"
            add_major_issue "Elevated fatal-level log lines: $FATAL_TEXT_INT in 24h"
        elif [ "$FATAL_TEXT_INT" -gt 0 ]; then
            log_info "Fatal-level log lines: $FATAL_TEXT_INT in 24h (below action floor of 25)"
        else
            log_success "No fatal-level log lines in 24h"
        fi

        # B) Connection exhaustion -- its own, lower-severity assertion. These come
        # in restart-tied bursts (a pool reconnecting), so they are a capacity/pool
        # signal, not a fatal-error signal.
        if [ "$CONN_EXHAUST_INT" -ge 5000 ]; then
            log_critical "DB connection exhaustion at outage scale: $CONN_EXHAUST_INT in 24h"
            add_critical_issue "DB connection exhaustion: $CONN_EXHAUST_INT log lines in 24h (sustained pool exhaustion is an availability outage)"
        elif [ "$CONN_EXHAUST_INT" -ge 500 ]; then
            log_warning "DB connection exhaustion sustained: $CONN_EXHAUST_INT in 24h"
            add_major_issue "DB connection exhaustion: $CONN_EXHAUST_INT log lines in 24h"
        elif [ "$CONN_EXHAUST_INT" -ge 100 ]; then
            log_warning "DB connection-exhaustion bursts: $CONN_EXHAUST_INT in 24h"
            add_minor_issue "DB connection-exhaustion bursts: $CONN_EXHAUST_INT log lines in 24h"
        elif [ "$CONN_EXHAUST_INT" -gt 0 ]; then
            log_info "DB connection-exhaustion log lines: $CONN_EXHAUST_INT in 24h (restart-tied burst range)"
        else
            log_success "No DB connection-exhaustion log lines in 24h"
        fi

        # C) OOM log text. The CRITICAL OOM verdict belongs to OOM_COUNT (events)
        # above; this corroborates it and catches in-process OOM that never
        # produces an OOMKilled pod status (JVM heap, ffmpeg allocation failures).
        # WINDOW ALIGNMENT (2026-08-18). OOM_TEXT_INT is a 24h Elasticsearch count,
        # so it must be corroborated by a 24h pod-state control. OOM_COUNT reads
        # kubectl events, which age out of etcd after ~1h; requiring it meant a
        # genuine OOM older than an hour could only ever reach MINOR here.
        # OOM_LASTSTATE_24H (lastState.terminated.finishedAt within 24h) is the
        # window-matched control and is now the primary corroborator; the other two
        # are kept as additional, narrower evidence.
        if [ "$OOM_TEXT_INT" -gt 0 ] && { [ "${OOM_LASTSTATE_24H:-0}" -gt 0 ] || [ "${OOM_COUNT:-0}" -gt 0 ] || [ "${OOM_LASTSTATE:-0}" -gt 0 ]; }; then
            log_critical "OOM confirmed by both controls: $OOM_TEXT_INT log lines (24h), lastState24h=${OOM_LASTSTATE_24H:-0} events=${OOM_COUNT:-0} lastState=${OOM_LASTSTATE:-0}"
            add_critical_issue "OOM: $OOM_TEXT_INT OOM log lines in 24h with window-aligned pod-state confirmation (lastState within 24h=${OOM_LASTSTATE_24H:-0}, events=${OOM_COUNT:-0}, lastState any age=${OOM_LASTSTATE:-0})"
        elif [ "$OOM_TEXT_INT" -ge 100 ]; then
            log_warning "In-process OOM log lines (no OOMKilled events): $OOM_TEXT_INT in 24h"
            add_major_issue "In-process OOM log lines: $OOM_TEXT_INT in 24h"
        elif [ "$OOM_TEXT_INT" -gt 0 ]; then
            log_warning "OOM log lines present (no OOMKilled events): $OOM_TEXT_INT in 24h"
            add_minor_issue "OOM log lines: $OOM_TEXT_INT in 24h"
        elif [ "${OOM_LASTSTATE_24H:-0}" -gt 0 ] || [ "${OOM_COUNT:-0}" -gt 0 ] || [ "${OOM_LASTSTATE:-0}" -gt 0 ]; then
            # Pod state says OOM, log text does not. Section 1 already raised the
            # CRITICAL; do not print a success line next to a live OOM.
            log_info "No OOM log text, but a pod-state control is non-zero (lastState24h=${OOM_LASTSTATE_24H:-0}, events=${OOM_COUNT:-0}, lastState=${OOM_LASTSTATE:-0}) - see Section 1"
        else
            log_success "No out-of-memory log lines in 24h (all three pod-state controls also 0)"
        fi

        fi  # end ES_LOG_ASSERTIONS_FAILED guard

        # ------------------------------------------------------------------
        # Log error-count verdict. REWRITTEN 2026-08-18 (finding F-log-volume).
        #
        # THIRD instance of the structurally-unclearable-assertion class, after
        # the "FATAL/OOM" counter (83d97de0) and icon_fatalerror.gif. Registered
        # in docs/sops/audit-script-correctness.md.
        #
        # What was wrong: `> 10,000 => MAJOR` against a MEASURED 7-day baseline of
        # 113,571-133,922 hits/day. It could never have gone green — not tonight,
        # not before the ibgastro storm existed, not on any day in the retained
        # window. Even with the whole my-software-showcase namespace excluded the
        # floor is 43,882-44,517/day, still 4.4x the escalation threshold.
        # Measured over now-7d on 2026-08-18 (per-day, cluster-wide):
        #     08-12 131,715   08-13 133,922   08-14 132,519   08-15 131,071
        #     08-16 113,571   08-17 379,367   08-18 4,030,722
        #   same, excluding my-software-showcase:
        #     08-16 113,571   08-17  44,517   08-18    43,882
        # The pre-08-17 113-134k tier was a home-automation storm (151,014 over
        # 08-14+08-15, ~75k/day) that has since been resolved; steady state is
        # ~44k/day. The wildcard also over-counts by construction: it matches the
        # substring "error" anywhere in body.text, so `handleError`,
        # `icon_fatalerror.gif` and `fatal_neterrors=0` all score.
        #
        # Worse, the assertion contradicted its own code comment above, which says
        # the count is "display-only ... the per-namespace breakdown is what makes
        # it useful" — and then called add_major_issue on the total anyway.
        #
        # What it is now: PER-NAMESPACE-RELATIVE, so one chatty app can no longer
        # own the whole cluster's verdict. That is the right shape rather than just
        # a higher floor, because the total is a sum over independent producers —
        # raising the floor to clear ibgastro would have hidden a genuine 10x
        # regression in any quieter namespace behind the noise of the loud one.
        # The cluster-wide total keeps only a BROAD-runaway backstop, and only when
        # no single namespace already accounts for it.
        #
        # Floors, calibrated against the measured window above:
        #   worst namespace today ...... kube-system 12,530/24h
        #   worst namespace measured ... home-automation ~75,000/24h (real, fixed)
        #   the storm .................. my-software-showcase 4,320,202/24h
        #   40,000  MINOR      3.2x today's worst namespace
        #   40,000 + >=40% share  MAJOR concentration (catches the ~75k/57% episode)
        #  100,000  MAJOR
        #  500,000  CRITICAL   6.6x the worst legitimate namespace-day on record
        # Every namespace is below 40,000 in the current window, so this CAN and
        # does read green once the storm is fixed — the property the old one lacked.
        # ------------------------------------------------------------------

        # A failed ERROR_DATA query must not read as a clean zero (same trap the
        # es_count ERR guard closes above): the curl fallback is a synthetic
        # zero-hit document, so detect the missing aggregation rather than
        # scoring green on a transport failure.
        HAS_NS_AGG=$(echo "$ERROR_DATA" | python3 -c "
import sys, json
try:
    print(1 if 'by_namespace' in json.load(sys.stdin).get('aggregations', {}) else 0)
except Exception:
    print(0)
" 2>/dev/null || echo 0)

        if [ "$HAS_NS_AGG" != "1" ]; then
            log_warning "Elasticsearch error-count query failed - the log-volume assertion did NOT run"
            add_major_issue "Elasticsearch log-volume assertion did not run (query failure) - per-namespace error-volume coverage is blind for this cycle"
        else
            echo "Cluster-wide error-substring matches (24h, display-only): $TOTAL_ERRORS_INT"

            NS_ERROR_ROWS=$(echo "$ERROR_DATA" | python3 -c "
import sys, json
try:
    for b in json.load(sys.stdin)['aggregations']['by_namespace']['buckets']:
        print('%s\t%d' % (b['key'], b['doc_count']))
except Exception:
    pass
" 2>/dev/null || echo "")

            NS_FLAGGED=0
            # here-string, NOT a pipe: a pipeline runs the loop in a subshell and
            # the add_*_issue bash arrays would be silently discarded.
            while IFS=$'\t' read -r NS_NAME NS_HITS; do
                [ -z "$NS_NAME" ] && continue
                NS_HITS=$((10#${NS_HITS:-0}))
                if [ "$TOTAL_ERRORS_INT" -gt 0 ]; then
                    NS_SHARE=$(( NS_HITS * 100 / TOTAL_ERRORS_INT ))
                else
                    NS_SHARE=0
                fi

                if [ "$NS_HITS" -ge 500000 ]; then
                    NS_FLAGGED=1
                    log_critical "Log-volume runaway in namespace $NS_NAME: $NS_HITS error-substring matches in 24h (${NS_SHARE}% of cluster)"
                    add_critical_issue "Log-volume runaway in namespace $NS_NAME: $NS_HITS error-substring matches in 24h (${NS_SHARE}% of the cluster total) - see docs/sops/log-volume-runaway.md"
                elif [ "$NS_HITS" -ge 100000 ]; then
                    NS_FLAGGED=1
                    log_warning "High error-log volume in namespace $NS_NAME: $NS_HITS in 24h (${NS_SHARE}% of cluster)"
                    add_major_issue "High error-log volume in namespace $NS_NAME: $NS_HITS in 24h (${NS_SHARE}% of the cluster total)"
                elif [ "$NS_HITS" -ge 40000 ] && [ "$NS_SHARE" -ge 40 ]; then
                    NS_FLAGGED=1
                    log_warning "Error-log volume concentrated in namespace $NS_NAME: $NS_HITS in 24h (${NS_SHARE}% of cluster)"
                    add_major_issue "Error-log volume concentrated in namespace $NS_NAME: $NS_HITS in 24h (${NS_SHARE}% of the cluster total)"
                elif [ "$NS_HITS" -ge 40000 ]; then
                    NS_FLAGGED=1
                    log_warning "Elevated error-log volume in namespace $NS_NAME: $NS_HITS in 24h"
                    add_minor_issue "Elevated error-log volume in namespace $NS_NAME: $NS_HITS in 24h"
                fi
            done <<< "$NS_ERROR_ROWS"

            # An aggregation that EXISTS but has zero buckets is the same silent-green
            # trap as a failed query, one level down: if the namespace field is
            # unmapped or renamed (this pipeline has a documented history of edot/ES
            # mapping churn), ES returns by_namespace with buckets: [] and every
            # per-namespace verdict below is skipped over nothing at all.
            NS_BUCKET_COUNT=$(printf '%s\n' "$NS_ERROR_ROWS" | grep -c . || true)
            NS_BUCKET_COUNT=$((10#${NS_BUCKET_COUNT:-0}))
            if [ "$NS_BUCKET_COUNT" -eq 0 ] && [ "$TOTAL_ERRORS_INT" -ge 1000 ]; then
                log_warning "Namespace breakdown returned ZERO buckets for $TOTAL_ERRORS_INT matches - the per-namespace assertion measured nothing"
                add_major_issue "Log-volume per-namespace breakdown returned no buckets for $TOTAL_ERRORS_INT matches in 24h (likely a k8s.namespace.name mapping change) - the assertion did not run"
                NS_FLAGGED=1
            fi

            # Broad backstop: a cluster-wide regression that no SINGLE namespace
            # explains. Gated on NS_FLAGGED so it can never double-count a namespace
            # finding that already says the same thing.
            #
            # TIERED, not a lone 1,000,000 floor. With 22 namespaces and a 40,000
            # per-namespace floor, the arithmetic worst case is 22 x 39,999 = 879,978
            # matches in 24h -- a 20x cluster-wide regression -- scoring fully green.
            # That gap is not a contrived shape: it is the CHARACTERISTIC shape of a
            # cluster-wide cause (CoreDNS/AdGuard failure, apiserver or etcd flap, the
            # NAS/CIFS path dropping so every mounted app logs at once, a cert expiry,
            # an ES/OTel ingestion stall). Those spread errors across namespaces
            # without any one dominating, which is exactly what the per-namespace
            # floors are blind to. Tiers are set against the measured storm-free
            # cluster steady state of ~44,000/day:
            #    120,000  MINOR     2.7x steady state
            #    250,000  MAJOR     5.7x
            #  1,000,000  CRITICAL  22.7x
            # Steady state still reads green, so the assertion stays clearable.
            #
            # KNOWN LIMITATION, deliberately not papered over: the per-namespace tiers
            # are ABSOLUTE, not relative to each namespace's own history. A namespace
            # going 50 -> 30,000/day is a 600x regression that still reads green. Doing
            # this properly needs a trailing per-namespace baseline (date_histogram
            # over now-8d/now-1d, flag at >= 5x the namespace's own median). That is a
            # follow-up, not a claim this check already makes.
            if [ "$NS_FLAGGED" -eq 0 ] && [ "$TOTAL_ERRORS_INT" -ge 1000000 ]; then
                log_critical "Broad cluster-wide log-volume runaway: $TOTAL_ERRORS_INT error-substring matches in 24h across namespaces, none dominant"
                add_critical_issue "Broad cluster-wide log-volume runaway: $TOTAL_ERRORS_INT error-substring matches in 24h with no single dominant namespace"
            elif [ "$NS_FLAGGED" -eq 0 ] && [ "$TOTAL_ERRORS_INT" -ge 250000 ]; then
                log_warning "Broad cluster-wide error-log increase: $TOTAL_ERRORS_INT in 24h across namespaces, none dominant (~5.7x baseline)"
                add_major_issue "Broad cluster-wide error-log increase: $TOTAL_ERRORS_INT matches in 24h with no single dominant namespace (measured baseline ~44,000/day)"
            elif [ "$NS_FLAGGED" -eq 0 ] && [ "$TOTAL_ERRORS_INT" -ge 120000 ]; then
                log_warning "Cluster-wide error-log volume above baseline: $TOTAL_ERRORS_INT in 24h, none dominant (~2.7x baseline)"
                add_minor_issue "Cluster-wide error-log volume above baseline: $TOTAL_ERRORS_INT matches in 24h with no single dominant namespace (measured baseline ~44,000/day)"
            elif [ "$NS_FLAGGED" -eq 0 ]; then
                log_success "Error-log volume within range in every namespace (cluster total $TOTAL_ERRORS_INT in 24h; highest namespace below the 40,000 floor)"
            fi
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
    INGRESS_ERRORS=$(safe_count "kubectl logs -n network -l app.kubernetes.io/name=ingress-nginx --tail=200 --since=1h 2>&1 | grep -E '\[error\]|\[emerg\]' | wc -l" "ingress-errors")
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
    BOUND_PVCS=$(safe_count "kubectl get pvc -A --no-headers 2>/dev/null | grep Bound | wc -l" "bound-pvcs" 1)
    PENDING_PVCS=$(safe_count "kubectl get pvc -A --no-headers 2>/dev/null | grep Pending | wc -l" "pending-pvcs")
    LOST_PVCS=$(safe_count "kubectl get pvc -A --no-headers 2>/dev/null | grep Lost | wc -l" "lost-pvcs")

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

        SERVICE_COUNT=$(echo "$PROBLEMATIC_SERVICES" | grep -c "/" || true)

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
    WEBHOOK_FAILURES=$(safe_count "kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | grep -i 'webhook' | grep -iE 'failed|error|timeout' | wc -l" "webhook-failures")

    # List configured webhooks
    VALIDATING_WEBHOOKS=$(safe_count "kubectl get validatingwebhookconfigurations --no-headers 2>/dev/null | wc -l" "validating-webhooks" 1)
    MUTATING_WEBHOOKS=$(safe_count "kubectl get mutatingwebhookconfigurations --no-headers 2>/dev/null | wc -l" "mutating-webhooks" 1)
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
        UNPOLLER_ERRORS=$(safe_count "kubectl logs -n monitoring '$UNPOLLER_POD' --tail=100 2>&1 | grep '\[ERROR\]' | wc -l" "unpoller-errors")
        echo "UnPoller errors (last 100 lines): $UNPOLLER_ERRORS"

        # Check for recent successful operations to detect recovery
        UNPOLLER_SUCCESS=$(safe_count "kubectl logs -n monitoring '$UNPOLLER_POD' --tail=20 2>&1 | grep 'Err: 0' | wc -l" "unpoller-success")
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

# Convert any measurement that could not be taken into findings BEFORE the
# counts below are read — otherwise a run whose probes all died reports zero
# issues, which is the exact failure this register exists to prevent.
report_unmeasured

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
          {"bool": {"must_not": {"wildcard": {"body.text": "*NOERROR*"}}}},   # CoreDNS logs a SUCCESSFUL answer as "NOERROR", which *ERROR* matches.
          # 22.9%% of all counted "errors" were healthy DNS responses (network ns:
          # 224 real, not 24,223). A success counted as a failure is the same
          # defect family as a silent zero — see docs/sops/audit-script-correctness.md.
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
log_section "Section 41: Alert Bridge Liveness"
{
    # The alert-bridge (launchd com.cberg.alert-bridge on this Mac) is the ONLY
    # path from Alertmanager to the operator session: Alertmanager posts to
    # http://192.168.30.111:8788/alertmanager and the bridge fans out over a
    # local websocket. Until 2026-08-20 nothing checked it, and it could not be
    # checked: its GET handler answered "alert-bridge ok" whenever the PROCESS
    # was alive, and it logs only startups -- never a forwarded alert. So a dead
    # bridge looked exactly like a quiet cluster. That is the silent-zero class
    # from docs/sops/audit-script-correctness.md, applied to the pager itself.
    # It is not hypothetical: the log holds 4,582 "alert-bridge up" lines from a
    # bind crash-loop, during which alerts were dropped and nothing said so.
    #
    # The bridge now records the Watchdog it already receives and discards
    # (Watchdog is the always-firing dead-man's switch; the claude route has no
    # matchers so it arrives here) and reports it on GET /.
    AB_URL="http://127.0.0.1:8788/"
    AB_JSON=$(curl -sS --max-time 5 "$AB_URL" 2>/dev/null || echo "")

    if [ -z "$AB_JSON" ]; then
        log_critical "alert-bridge is NOT answering on $AB_URL — Alertmanager alerts are not reaching the operator session"
        add_critical_issue "alert-bridge unreachable on 127.0.0.1:8788 — every Alertmanager page is being dropped silently. Check: launchctl list | grep cberg.alert-bridge; log at ~/.claude/logs/alert-bridge.log"
    else
        AB_WD=$(echo "$AB_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); v=d.get('last_watchdog_age_s'); print(-1 if v is None else int(v))" 2>/dev/null || echo "-1")
        AB_UP=$(echo "$AB_JSON" | python3 -c "import sys,json; print(int(json.load(sys.stdin).get('uptime_s',0)))" 2>/dev/null || echo "0")
        AB_CLIENTS=$(echo "$AB_JSON" | python3 -c "import sys,json; print(int(json.load(sys.stdin).get('ws_clients',0)))" 2>/dev/null || echo "0")
        echo "alert-bridge: uptime=${AB_UP}s ws_clients=${AB_CLIENTS} last_watchdog_age=${AB_WD}s"

        # Alertmanager re-sends Watchdog on the claude route's repeat_interval
        # (4h). Stale threshold is 5h to leave headroom; "never seen" is only
        # conclusive once the process has outlived one full repeat interval,
        # otherwise a recent restart would read as a failure.
        AB_STALE=18000   # 5h
        AB_GRACE=16200   # 4.5h
        if [ "$AB_WD" -lt 0 ]; then
            if [ "$AB_UP" -gt "$AB_GRACE" ]; then
                log_critical "alert-bridge has NEVER received a Watchdog in ${AB_UP}s of uptime — Alertmanager is not reaching it"
                add_critical_issue "alert-bridge reachable but has received no Watchdog heartbeat in ${AB_UP}s (> one 4h repeat_interval): Alertmanager cannot post to it, so pages are being lost. Check the claude-watch-webhook receiver URL and the Mac's firewall."
            else
                log_info "alert-bridge restarted ${AB_UP}s ago; no Watchdog yet (expected — repeat_interval is 4h)"
            fi
        elif [ "$AB_WD" -gt "$AB_STALE" ]; then
            log_critical "alert-bridge last heard from Alertmanager ${AB_WD}s ago (> 5h)"
            add_critical_issue "alert-bridge Watchdog heartbeat is ${AB_WD}s stale (> 5h, repeat_interval is 4h) — Alertmanager has stopped reaching the bridge and pages are being lost silently."
        else
            log_success "alert-bridge healthy (heartbeat ${AB_WD}s ago, ${AB_CLIENTS} ws client(s))"
        fi

        # A bridge with no websocket consumer still accepts alerts and drops
        # them on the floor -- reachable, heartbeating, and useless.
        if [ "$AB_CLIENTS" -eq 0 ]; then
            log_warning "alert-bridge has no websocket consumer — alerts are received but nothing is listening"
            add_minor_issue "alert-bridge has 0 websocket clients: Alertmanager alerts arrive but no operator session is attached to receive them."
        fi
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

# Auto-write the snapshot so doc-check's `health-check-current.md` freshness
# check stays green without operator intervention. Same pattern the Python
# *-check.py scripts use (OUTPUT path in each script).
SNAPSHOT_DIR="${SWEEP_SNAPSHOTS_DIR:-$SCRIPT_DIR}"
if [ -w "$SNAPSHOT_DIR" ] && [ -s "$SUMMARY_FILE" ]; then
    cp "$SUMMARY_FILE" "$SNAPSHOT_DIR/health-check-current.md" 2>/dev/null && \
        echo "Snapshot: $SNAPSHOT_DIR/health-check-current.md"
fi

echo ""
echo "Next steps:"
echo "  - Review full output: cat $OUTPUT_FILE"
echo "  - Check summary: cat $SUMMARY_FILE"
echo "  - Review issues: cat $ISSUES_FILE"
