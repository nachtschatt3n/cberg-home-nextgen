#!/usr/bin/env bash
# Regression tests for the log-shipping coverage check in
# runbooks/health-check.sh (F-a49c67c3, "running pods shipping zero log
# documents").
#
# Four showcase pods ran 1/1 for 13h while every request log went to an
# emptyDir file and nothing reached Elasticsearch -- and no check noticed,
# because every ES assertion counted documents that exist. The check now
# enumerates the ABSENCE: each Running pod older than the window without a
# per-pod bucket is cross-checked against the kubelet, and classified
#   GAP           stdout exists (older than the lag guard), ES has nothing
#                 -> MAJOR naming the pods (the pipeline drops them)
#   LAG           newest stdout line younger than the guard -> info
#   REPLICA-IDLE  a sibling replica of the same controller logs -> info
#   SILENT        no stdout at all -> one MINOR with the list, never excluded
#   UNPROBED      kubelet query failed -> unmeasured
#
# Hermetic: logship_kubelet_newest is a stub keyed on the pod name.
# Run directly:  bash runbooks/tests/test-health-check-logship-zero-docs.sh
set -uo pipefail
HC="$(cd "$(dirname "$0")/.." && pwd)/health-check.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

python3 - "$HC" "$TMP/funcs.sh" <<'PY'
import sys
src, out = sys.argv[1], sys.argv[2]
s = open(src).read()
def grab(name):
    i = s.index(f"{name}() {{")
    j = s.index("\n}\n", i) + 3
    return s[i:j]
open(out, "w").write("\n\n".join(grab(n) for n in ("logship_candidates", "logship_classify", "logship_score")))
PY

WARN=(); INFO=(); OK=(); MINOR=(); MAJOR=(); UNMEASURED=()
log_warning() { WARN+=("$1"); }
log_info()    { INFO+=("$1"); }
log_success() { OK+=("$1"); }
add_minor_issue() { MINOR+=("$1"); }
add_major_issue() { MAJOR+=("$1"); }
_record_unmeasured() { UNMEASURED+=("$1: $2"); }
NOW=$(date +%s)
# kubelet stub: newest stdout epoch per pod; "" = nothing in window; rc 1 = query failed
logship_kubelet_newest() {
    case "$2" in
        synthetic-gapper-*)  echo $((NOW - 3600)) ;;
        synthetic-lagger-*)  echo $((NOW - 60)) ;;
        synthetic-broken-*)  return 1 ;;
        *)                   echo "" ;;
    esac
}
source "$TMP/funcs.sh"
reset() { WARN=(); INFO=(); OK=(); MINOR=(); MAJOR=(); UNMEASURED=(); }

PASS=0; FAIL=0
check() { if [ "$2" -eq 0 ]; then echo "  PASS  $1"; PASS=$((PASS+1)); else echo "  FAIL  $1"; [ -n "${3:-}" ] && printf '        %s\n' "$3"; FAIL=$((FAIL+1)); fi; }
joined() { printf '%s\n' "$@"; }
cls_of() { printf '%s\n' "$1" | awk -F'\t' -v k="$2" '$3==k{print $1}'; }

# Running pods (ns, name, owner, age): the showcase shape, a leader-elected
# pair, an idle cache, a chatty collector, a pod the pipeline drops, one
# inside the ingestion lag, one the kubelet cannot answer for.
RUNNING=$'showcase\tsynthetic-rails-7bcddcfd8d-t59f4\tReplicaSet/synthetic-rails\t90000
kube-system\tsynthetic-sched-node-a\tNode/synthetic-sched\t90000
kube-system\tsynthetic-sched-node-b\tNode/synthetic-sched\t90000
db\tsynthetic-cache-5887bddf8-qmvk9\tReplicaSet/synthetic-cache\t90000
monitoring\tsynthetic-otel-d8976b86d-khq6h\tReplicaSet/synthetic-otel\t90000
office\tsynthetic-gapper-69c97d9c68-sn94c\tReplicaSet/synthetic-gapper\t90000
db\tsynthetic-lagger-d65f4857b-8xckg\tReplicaSet/synthetic-lagger\t90000
ai\tsynthetic-broken-56676987dd-c5h6c\tReplicaSet/synthetic-broken\t90000'
ES=$'POD\tsynthetic-sched-node-a\t1\nPOD\tsynthetic-otel-d8976b86d-khq6h\t100\nOTHER\t0'

echo "log-shipping coverage: zero-document pods"

# 1. Candidates: only pods without a bucket; sibling flag from the owner group.
cands=$(logship_candidates "$RUNNING" "$ES")
check "pods with a bucket are not candidates" $(! printf '%s\n' "$cands" | grep -q 'synthetic-otel\|synthetic-sched-node-a' && echo 0 || echo 1) "$cands"
check "six zero-document pods are candidates" $([ "$(printf '%s\n' "$cands" | grep -c '^CAND')" -eq 6 ] && echo 0 || echo 1) "$cands"
check "leader-elected sibling carries sibling_logs=1" $(printf '%s\n' "$cands" | grep -q $'^CAND\tkube-system\tsynthetic-sched-node-b\t1$' && echo 0 || echo 1) "$cands"
check "single-replica silent pod carries sibling_logs=0" $(printf '%s\n' "$cands" | grep -q $'^CAND\tshowcase\tsynthetic-rails-7bcddcfd8d-t59f4\t0$' && echo 0 || echo 1) "$cands"
check "truncated aggregation -> OVERFLOW line" $(logship_candidates "$RUNNING" $'POD\tx\t1\nOTHER\t12' | grep -q '^OVERFLOW' && echo 0 || echo 1)

# 2. Classification against the kubelet.
classes=$(logship_classify "$cands" 24 900)
check "stdout older than the guard, no ES bucket -> GAP" $([ "$(cls_of "$classes" synthetic-gapper-69c97d9c68-sn94c)" = "GAP" ] && echo 0 || echo 1) "$classes"
check "stdout inside the guard -> LAG" $([ "$(cls_of "$classes" synthetic-lagger-d65f4857b-8xckg)" = "LAG" ] && echo 0 || echo 1) "$classes"
check "no stdout, logging sibling -> REPLICA-IDLE" $([ "$(cls_of "$classes" synthetic-sched-node-b)" = "REPLICA-IDLE" ] && echo 0 || echo 1) "$classes"
check "no stdout, no sibling -> SILENT" $([ "$(cls_of "$classes" synthetic-rails-7bcddcfd8d-t59f4)" = "SILENT" ] && [ "$(cls_of "$classes" synthetic-cache-5887bddf8-qmvk9)" = "SILENT" ] && echo 0 || echo 1) "$classes"
check "kubelet query failure -> UNPROBED" $([ "$(cls_of "$classes" synthetic-broken-56676987dd-c5h6c)" = "UNPROBED" ] && echo 0 || echo 1) "$classes"

# 3. Scoring.
reset; logship_score "$classes" 8 24 > "$TMP/out"; out=$(cat "$TMP/out")
check "GAP -> exactly one MAJOR naming the pod" $([ ${#MAJOR[@]} -eq 1 ] && joined "${MAJOR[@]}" | grep -q 'office/synthetic-gapper-69c97d9c68-sn94c' && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"
check "SILENT -> one MINOR with count and namespace breakdown" $([ ${#MINOR[@]} -eq 1 ] && joined "${MINOR[@]}" | grep -q 'silent on stdout for 24h: 2 (db=1, showcase=1)' && echo 0 || echo 1) "$(joined "${MINOR[@]:-none}")"
check "LAG and REPLICA-IDLE are not in any issue" $(! joined "${MAJOR[@]:-}" "${MINOR[@]:-}" | grep -q 'synthetic-lagger\|synthetic-sched' && echo 0 || echo 1)
check "UNPROBED -> unmeasured, and no success line" $(joined "${UNMEASURED[@]:-}" | grep -q 'log-shipping-coverage' && [ ${#OK[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${UNMEASURED[@]:-none}")"
check "report body lists every class with its pod" $(printf '%s' "$out" | grep -q '^    GAP .*synthetic-gapper' && printf '%s' "$out" | grep -q '^    SILENT .*synthetic-rails' && printf '%s' "$out" | grep -q 'zero-document pods: gap 1, lag 1, replica-idle 1, silent 2, unprobed 1' && echo 0 || echo 1) "$out"

# 4. Clean run: no gap, nothing unprobed -> success; silent pods still reported.
reset; logship_score "$(printf '%s\n' "$classes" | grep -v '^GAP\|^UNPROBED')" 8 24 > /dev/null
check "no GAP and nothing UNPROBED -> success line" $([ ${#OK[@]} -eq 1 ] && [ ${#MAJOR[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${OK[@]:-none}")"
check "silent pods are still a MINOR on a clean run (never excluded)" $([ ${#MINOR[@]} -eq 1 ] && echo 0 || echo 1)

# 5. Script text: the section sits before report_unmeasured and gates on ES.
check "Log Shipping section sits before report_unmeasured" $([ "$(grep -n '^log_section "Log Shipping Coverage"' "$HC" | cut -d: -f1)" -lt "$(grep -n '^report_unmeasured$' "$HC" | cut -d: -f1)" ] && echo 0 || echo 1)
check "ES unavailable is recorded as unmeasured in logship_run" $(grep -q '_record_unmeasured "log-shipping-coverage" "Elasticsearch enrichment session unavailable"' "$HC" && echo 0 || echo 1)

# --- COMMISSIONING STRAW ------------------------------------------------------
# Pre-fix logic, transcribed from Section 34: the only absence check was the
# CLUSTER-WIDE document count on logs-generic-default. With 101 documents in
# the fixture (all from two pods) it must raise NOTHING about the gapper or
# the four silent pods -- proving case 3 would fail against the old code.
echo "commissioning straw (pre-fix cluster-wide count must FAIL case 3)"
straw_section34() {
    local logs_count="$1"
    if [ "${logs_count:-0}" -eq 0 ]; then
        add_major_issue "OTel: no documents in logs-generic-default data stream"
    else
        log_success "OTel log documents present in logs-generic-default: $logs_count"
    fi
}
reset
straw_section34 101
check "STRAW: 101 documents cluster-wide reads as a pass while one pod is dropped and two are silent (test would fail -> witness is real)" \
    $([ ${#MAJOR[@]} -eq 0 ] && [ ${#MINOR[@]} -eq 0 ] && [ ${#OK[@]} -eq 1 ] && echo 0 || echo 1) "$(joined "${OK[@]:-none}")"

echo ""
echo "  $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
