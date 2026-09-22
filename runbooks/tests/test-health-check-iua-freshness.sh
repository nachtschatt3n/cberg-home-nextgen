#!/usr/bin/env bash
# Regression tests for the Flux image-automation FRESHNESS assertion in
# runbooks/health-check.sh Section 20 (F-8d4645f6 residual).
#
# The existing push assertion keys on lastPushCommit being NON-NULL. A PAT
# expiry never disturbs that: the commit of the last good push stays in
# status forever while every later run silently fails, and Ready flaps back
# to True/"repository up-to-date". The freshness scan keys on time and
# ancestry instead: an unsuspended automation whose lastAutomationRunTime is
# older than FLUX_IUA_STALE_MULT x interval -> MAJOR; a lastPushCommit that
# is not an ancestor of origin/main -> MAJOR; suspended -> listed, not
# scored; commit not judgeable (missing object, clone behind remote) ->
# unmeasured; empty listing -> unmeasured.
#
# Hermetic: flux_iua_ancestor is a stub keyed on the commit.
# Run directly:  bash runbooks/tests/test-health-check-iua-freshness.sh
set -uo pipefail
HC="$(cd "$(dirname "$0")/.." && pwd)/health-check.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

python3 - "$HC" "$TMP/funcs.sh" <<'PY'
import sys, re
src, out = sys.argv[1], sys.argv[2]
s = open(src).read()
def grab(name):
    i = s.index(f"{name}() {{")
    j = s.index("\n}\n", i) + 3
    return s[i:j]
m = re.search(r'^FLUX_IUA_STALE_MULT=.*$', s, re.M)
open(out, "w").write((m.group(0) if m else "") + "\n\n" + grab("flux_iua_score"))
PY

WARN=(); OK=(); MAJOR=(); MINOR=(); UNMEASURED=()
log_warning() { WARN+=("$1"); }
log_success() { OK+=("$1"); }
add_major_issue() { MAJOR+=("$1"); }
add_minor_issue() { MINOR+=("$1"); }
_record_unmeasured() { UNMEASURED+=("$1: $2"); }
flux_iua_ancestor() {
    case "$1" in
        aaaa*) echo yes ;;
        bbbb*) echo no ;;
        cccc*) echo missing ;;
        dddd*) echo stale-clone ;;
        *)     echo yes ;;
    esac
}
source "$TMP/funcs.sh"
reset() { WARN=(); OK=(); MAJOR=(); MINOR=(); UNMEASURED=(); }

PASS=0; FAIL=0
check() { if [ "$2" -eq 0 ]; then echo "  PASS  $1"; PASS=$((PASS+1)); else echo "  FAIL  $1"; [ -n "${3:-}" ] && printf '        %s\n' "$3"; FAIL=$((FAIL+1)); fi; }
joined() { printf '%s\n' "$@"; }

# ns name suspended interval_s run_age_s push_age_s commit branch
LIVE_OK=$'synthetic-prod\tsynthetic-updates\t0\t1800\t600\t3000000\taaaa1111\tmain'
STALE=$'synthetic-dev\tsynthetic-updates\t0\t1800\t169275\t3000000\taaaa2222\tmain'        # 47h since the last run, 30m interval
NEVER_RAN=$'synthetic-dev\tsynthetic-never\t0\t1800\t-\t-\t-\tmain'
ORPHAN=$'synthetic-prod\tsynthetic-orphan\t0\t1800\t600\t120\tbbbb3333\tmain'
SUSPENDED_STALE=$'synthetic-dev\tsynthetic-paused\t1\t1800\t169275\t3000000\taaaa4444\tmain'
MISSING_OBJ=$'synthetic-prod\tsynthetic-unfetched\t0\t1800\t600\t120\tcccc5555\tmain'
BEHIND=$'synthetic-prod\tsynthetic-behind\t0\t1800\t600\t120\tdddd6666\tmain'
NO_INTERVAL=$'synthetic-prod\tsynthetic-nointerval\t0\t-\t600\t120\taaaa7777\tmain'

echo "flux image-automation freshness"

check "staleness multiplier is 3x the interval" $([ "${FLUX_IUA_STALE_MULT:-}" = "3" ] && echo 0 || echo 1)

reset; flux_iua_score "$LIVE_OK" > /dev/null
check "fresh run + push on main -> success, no issue" $([ ${#OK[@]} -eq 1 ] && [ ${#MAJOR[@]} -eq 0 ] && [ ${#UNMEASURED[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${OK[@]:-none}")"

reset; flux_iua_score "$STALE" > "$TMP/out"
check "run older than 3x interval -> MAJOR naming the automation and the ages" $([ ${#MAJOR[@]} -eq 1 ] && joined "${MAJOR[@]}" | grep -q 'synthetic-dev/synthetic-updates (last run 169275s ago, interval 1800s)' && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"
check "stale MAJOR says a non-null lastPushCommit is no evidence" $(joined "${MAJOR[@]:-}" | grep -q 'a non-null lastPushCommit says nothing here' && echo 0 || echo 1)
check "stale automation with a push on main gets no ancestry issue" $(! joined "${MAJOR[@]:-}" | grep -q 'pushed off main' && [ ${#OK[@]} -eq 0 ] && echo 0 || echo 1)

reset; flux_iua_score "$NEVER_RAN" > /dev/null
check "unsuspended with no lastAutomationRunTime -> MAJOR (never ran)" $([ ${#MAJOR[@]} -eq 1 ] && joined "${MAJOR[@]}" | grep -q 'synthetic-never (no lastAutomationRunTime)' && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"

reset; flux_iua_score "$ORPHAN" > /dev/null
check "lastPushCommit not an ancestor of origin/main -> MAJOR naming commit and branch" $([ ${#MAJOR[@]} -eq 1 ] && joined "${MAJOR[@]}" | grep -q 'pushed off main: synthetic-prod/synthetic-orphan (bbbb3333 -> main)' && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"

reset; flux_iua_score "$SUSPENDED_STALE" > "$TMP/out"; out=$(cat "$TMP/out")
check "suspended + stale -> listed as SUSPENDED, no MAJOR" $([ ${#MAJOR[@]} -eq 0 ] && printf '%s' "$out" | grep -q 'synthetic-dev/synthetic-paused: SUSPENDED (spec.suspend)' && echo 0 || echo 1) "$out"
check "suspended automation still has its push ancestry checked" $(printf '%s' "$out" | grep -q 'lastPushCommit aaaa4444 is on origin/main' && echo 0 || echo 1) "$out"
check "success line counts it as suspended, not live" $(joined "${OK[@]:-}" | grep -q '0 live, 1 suspended' && echo 0 || echo 1) "$(joined "${OK[@]:-none}")"

reset; flux_iua_score "$MISSING_OBJ" > /dev/null
check "commit object not in the local clone -> unmeasured, no MAJOR" $([ ${#MAJOR[@]} -eq 0 ] && joined "${UNMEASURED[@]:-}" | grep -q 'flux-image-automation-push-ancestry: synthetic-prod/synthetic-unfetched lastPushCommit cccc5555 is not in the local clone' && echo 0 || echo 1) "$(joined "${UNMEASURED[@]:-none}")"
reset; flux_iua_score "$BEHIND" > /dev/null
check "clone behind the remote -> unmeasured, not 'pushed off main'" $([ ${#MAJOR[@]} -eq 0 ] && joined "${UNMEASURED[@]:-}" | grep -q 'behind the remote' && echo 0 || echo 1) "$(joined "${UNMEASURED[@]:-none}")"
reset; flux_iua_score "$NO_INTERVAL" > /dev/null
check "unparseable interval -> unmeasured for that automation" $(joined "${UNMEASURED[@]:-}" | grep -q 'spec.interval unparseable' && [ ${#MAJOR[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${UNMEASURED[@]:-none}")"
reset; flux_iua_score "" > /dev/null
check "empty listing -> unmeasured (there ARE automations in git)" $([ ${#UNMEASURED[@]} -eq 1 ] && [ ${#OK[@]} -eq 0 ] && echo 0 || echo 1)

# Mixed listing: one issue per class, not per line.
reset; flux_iua_score "$STALE"$'\n'"$LIVE_OK"$'\n'"$SUSPENDED_STALE" > /dev/null
check "mixed listing -> one stale MAJOR, no success" $([ ${#MAJOR[@]} -eq 1 ] && [ ${#OK[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"

# Script text: CRD absent is unmeasured; the block lives in Section 20 before report_unmeasured.
check "CRD absent is recorded as unmeasured" $(grep -q '_record_unmeasured "flux-image-automation-freshness" "imageupdateautomations CRD absent' "$HC" && echo 0 || echo 1)
check "freshness block sits before report_unmeasured" $([ "$(grep -n 'Image-automation LIVENESS by freshness' "$HC" | head -1 | cut -d: -f1)" -lt "$(grep -n '^report_unmeasured$' "$HC" | cut -d: -f1)" ] && echo 0 || echo 1)
check "ancestry uses merge-base --is-ancestor against origin/main" $(grep -q 'merge-base --is-ancestor "\$c" origin/main' "$HC" && echo 0 || echo 1)

# --- COMMISSIONING STRAW ------------------------------------------------------
# Pre-fix logic, transcribed from Section 20's push assertion (2): an
# automation is skipped outright when lastPushCommit is non-null, and skipped
# again when its last run is older than 24h. The STALE fixture (47h since the
# last run, commit from a push weeks ago) must raise NOTHING -- proving the
# stale case above would fail against the old code.
echo "commissioning straw (pre-fix non-null-commit logic must FAIL the stale case)"
straw_section20() {
    local run_age_s="$1" commit="$2"
    [ "$run_age_s" -gt 86400 ] && return 0          # "if now - run_dt > 24h: continue"
    [ "$commit" != "-" ] && return 0                # "if st.get('lastPushCommit'): continue"
    add_major_issue "Flux image automation stuck: lastPushCommit null"
}
reset
straw_section20 169275 aaaa2222
check "STRAW: a 47h-stale automation with an old non-null push is skipped by the old logic (test would fail -> witness is real)" \
    $([ ${#MAJOR[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"

echo ""
echo "  $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
