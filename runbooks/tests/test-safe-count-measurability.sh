#!/usr/bin/env bash
# Regression tests for safe_count() in runbooks/health-check.sh (2026-08-22).
#
# The previous body was:
#     local result=$(eval "$1" 2>/dev/null | head -1 || echo "0")
# which returns "0" for a genuine zero, a missing binary, an unreachable
# cluster and a failed query alike — verified: all four produced exactly "0".
# 57 call sites depended on it, and essentially every silent-green defect in
# docs/sops/audit-script-correctness.md is a variation on that collapse.
#
# Two things make the fix work, and both are tested here:
#
#   1. The real exit status is PIPESTATUS[0] evaluated INSIDE the eval. Taking
#      the pipeline's own status is useless: in `kubectl ... | wc -l` the status
#      belongs to wc, which succeeds while printing 0.
#   2. The failure register is FILE-backed, because safe_count is called as
#      `VAR=$(safe_count ...)` — a subshell. Appending to a bash array from
#      there is discarded silently when the subshell exits.
#
# Run: bash runbooks/tests/test-safe-count-measurability.sh
set -uo pipefail
HC="$(cd "$(dirname "$0")/.." && pwd)/health-check.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

python3 - "$HC" "$TMP/f.sh" <<'PY'
import sys
src, out = sys.argv[1], sys.argv[2]
s = open(src).read()
i = s.index('UNMEASURED_LOG="${TMPDIR:-/tmp}/_hc_unmeasured.$$"')
j = s.index('\n}\n', s.index('report_unmeasured() {')) + 3
open(out, 'w').write(s[i:j])
PY

log_warning() { :; }
MAJOR_ISSUES_LIST=()
add_major_issue() { MAJOR_ISSUES_LIST+=("$1"); }
source "$TMP/f.sh"

PASS=0; FAIL=0
check() {
    if [ "$2" == "$3" ]; then echo "  PASS  $1"; PASS=$((PASS+1))
    else echo "  FAIL  $1 (got '$2' want '$3')"; FAIL=$((FAIL+1)); fi
}
reset() { : > "$UNMEASURED_LOG"; MAJOR_ISSUES_LIST=(); }
nrec() { wc -l < "$UNMEASURED_LOG" | tr -d ' '; }

echo "safe_count measurability tests"

reset
check "genuine zero returns 0"                 "$(safe_count 'echo 0' z)"        "0"
check "  ...and is NOT recorded as unmeasured" "$(nrec)"                          "0"

reset
check "real count is returned"                 "$(safe_count 'printf 7' c)"      "7"
check "  ...and is not recorded"               "$(nrec)"                          "0"

# The critical case: the caller's pipeline ends in wc, which succeeds.
reset
v=$(safe_count 'kubectl-does-not-exist get pods | wc -l' missing)
check "missing binary behind a pipe returns 0" "$v"                               "0"
check "  ...but IS recorded as unmeasured"     "$(nrec)"                          "1"

reset
v=$(safe_count 'kubectl --kubeconfig=/nonexistent get pods --no-headers 2>/dev/null | wc -l' unreach)
check "unreachable cluster is recorded"        "$(nrec)"                          "1"

# Denominator floor: a zero where zero is impossible.
reset
v=$(safe_count 'echo 0' denom 1)
check "zero below floor is recorded"           "$(nrec)"                          "1"
reset
v=$(safe_count 'echo 5' denom 1)
check "value above floor is not recorded"      "$(nrec)"                          "0"
reset
v=$(safe_count 'echo 0' nofloor)
check "zero with NO floor is not recorded"     "$(nrec)"                          "0"

# Subshell survival — the whole reason the register is a file.
reset
X=$(safe_count 'false | wc -l' subshell-case)
report_unmeasured
check "finding raised from a \$( ) call reaches the main shell" \
      "${#MAJOR_ISSUES_LIST[@]}"                                                   "1"

# report_unmeasured must be quiet when everything measured cleanly.
reset
X=$(safe_count 'echo 3' fine)
report_unmeasured
check "clean run raises no findings"           "${#MAJOR_ISSUES_LIST[@]}"         "0"

echo ""
echo "  $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
