#!/usr/bin/env bash
# Regression tests for the Flux not-Ready persistence gate in
# runbooks/health-check.sh (F-accbce1b).
#
# A point-in-time sample of `kustomizations -A` taken while Flux re-reconciles
# onto a fresh commit catches dependency-ordered Kustomizations in their
# normal seconds-to-minutes "dependency X is not ready" window; that used to
# be scored as a standing MAJOR. The gate scores only what persists: hard
# failures at once, dependency/health-check/progressing waits only once older
# than the grace, with ONE bounded re-sample for the young ones.
#
# Hermetic: kubectl and sleep are stubs serving crafted samples.
# Run directly:  bash runbooks/tests/test-health-check-flux-notready-persistence.sh
set -uo pipefail
HC="$(cd "$(dirname "$0")/.." && pwd)/health-check.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

# Extract the functions under test verbatim so the test cannot drift.
python3 - "$HC" "$TMP/funcs.sh" <<'PY'
import sys
src, out = sys.argv[1], sys.argv[2]
s = open(src).read()
def grab(name):
    i = s.index(f"{name}() {{")
    j = s.index("\n}\n", i) + 3
    return s[i:j]
open(out, "w").write("\n\n".join(grab(n) for n in (
    "_iso_to_epoch", "flux_notready_list", "flux_notready_class",
    "flux_notready_verdict", "flux_notready_scan")))
PY

UNMEASURED=()
_record_unmeasured() { UNMEASURED+=("$1: $2"); }
SLEPT=()
sleep() { SLEPT+=("$1"); }
# kubectl stub: the Nth listing call serves $TMP/sampleN.json; a missing
# sample file means "the listing failed".
kubectl() {
    local n
    n=$(cat "$TMP/calls" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$TMP/calls"
    [ -f "$TMP/sample$n.json" ] || return 1
    cat "$TMP/sample$n.json"
}
source "$TMP/funcs.sh"
FLUX_NOTREADY_GRACE_S=600
FLUX_NOTREADY_RESAMPLE_S=45

# mksample N "python list of (ns, name, status, reason, age_s, message)"
mksample() {
    python3 - "$2" > "$TMP/sample$1.json" <<'PY'
import sys, json, datetime
now = datetime.datetime.now(datetime.timezone.utc)
def ago(sec):
    if sec is None: return "not-a-timestamp"
    return (now - datetime.timedelta(seconds=sec)).strftime('%Y-%m-%dT%H:%M:%SZ')
items = []
for ns, name, status, reason, age, msg in eval(sys.argv[1]):
    items.append({"metadata": {"namespace": ns, "name": name},
                  "status": {"conditions": [{"type": "Ready", "status": status,
                                             "reason": reason, "message": msg,
                                             "lastTransitionTime": ago(age)}]}})
print(json.dumps({"items": items}))
PY
}
reset() { rm -f "$TMP"/sample*.json "$TMP/calls"; SLEPT=(); UNMEASURED=(); }

PASS=0; FAIL=0
check() { # name, condition-result (0/1), detail
    if [ "$2" -eq 0 ]; then echo "  PASS  $1"; PASS=$((PASS+1))
    else echo "  FAIL  $1"; [ -n "${3:-}" ] && printf '        %s\n' "$3"; FAIL=$((FAIL+1)); fi
}
verdict_of() { printf '%s\n' "$1" | awk -F'\t' -v k="$2" '$3==k{print $1}'; }
class_of()   { printf '%s\n' "$1" | awk -F'\t' -v k="$2" '$3==k{print $2}'; }

echo "flux not-ready persistence gate"
DEP_MSG="dependency storage/longhorn is not ready"
READY_MSG="Applied revision: refs/heads/main@sha1:0000000"

# 1. THE REGRESSION: a 90s-old dependency wait that is gone at re-sample.
reset
mksample 1 "[('home-automation','frigate','False','DependencyNotReady',90,'$DEP_MSG')]"
mksample 2 "[]"
flux_notready_scan > "$TMP/out"; rc=$?; out=$(cat "$TMP/out")
check "young dependency wait, gone at re-sample -> RESOLVED, rc 0" \
    $([ "$rc" -eq 0 ] && [ "$(verdict_of "$out" home-automation/frigate)" = "RESOLVED" ] && echo 0 || echo 1) "$out"
check "class is 'dependency'" $([ "$(class_of "$out" home-automation/frigate)" = "dependency" ] && echo 0 || echo 1) "$out"
check "re-sample waited FLUX_NOTREADY_RESAMPLE_S once" $([ "${#SLEPT[@]}" -eq 1 ] && [ "${SLEPT[0]}" = "45" ] && echo 0 || echo 1) "slept: ${SLEPT[*]:-none}"

# 2. Young dependency wait still present at re-sample -> PENDING, not scored.
reset
mksample 1 "[('home-automation','frigate','False','DependencyNotReady',90,'$DEP_MSG')]"
mksample 2 "[('home-automation','frigate','False','DependencyNotReady',135,'$DEP_MSG')]"
flux_notready_scan > "$TMP/out"; out=$(cat "$TMP/out")
check "young dependency wait, still there -> PENDING" $([ "$(verdict_of "$out" home-automation/frigate)" = "PENDING" ] && echo 0 || echo 1) "$out"

# 3. Old dependency wait -> STANDING, and no re-sample is needed.
reset
mksample 1 "[('home-automation','frigate','False','DependencyNotReady',1200,'$DEP_MSG')]"
flux_notready_scan > "$TMP/out"; out=$(cat "$TMP/out")
check "dependency wait older than grace -> STANDING" $([ "$(verdict_of "$out" home-automation/frigate)" = "STANDING" ] && echo 0 || echo 1) "$out"
check "no sleep when nothing is PENDING" $([ "${#SLEPT[@]}" -eq 0 ] && echo 0 || echo 1) "slept: ${SLEPT[*]:-none}"

# 4. A hard failure gets no grace, however young.
reset
mksample 1 "[('kube-system','broken','False','BuildFailed',30,'kustomize build failed: sops decryption error')]"
flux_notready_scan > "$TMP/out"; out=$(cat "$TMP/out")
check "BuildFailed 30s old -> STANDING (class failure)" \
    $([ "$(verdict_of "$out" kube-system/broken)" = "STANDING" ] && [ "$(class_of "$out" kube-system/broken)" = "failure" ] && echo 0 || echo 1) "$out"

# 5. Health-check-in-progress: young PENDING, old STANDING, class healthcheck.
reset
mksample 1 "[('media','plex','False','Progressing',120,'running health checks with timeout of 10m0s'),('media','jellyfin','False','Progressing',900,'running health checks with timeout of 10m0s')]"
mksample 2 "[('media','plex','False','Progressing',165,'running health checks with timeout of 10m0s'),('media','jellyfin','False','Progressing',945,'running health checks with timeout of 10m0s')]"
flux_notready_scan > "$TMP/out"; out=$(cat "$TMP/out")
check "young health check -> PENDING (healthcheck)" \
    $([ "$(verdict_of "$out" media/plex)" = "PENDING" ] && [ "$(class_of "$out" media/plex)" = "healthcheck" ] && echo 0 || echo 1) "$out"
check "old health check -> STANDING (healthcheck)" \
    $([ "$(verdict_of "$out" media/jellyfin)" = "STANDING" ] && [ "$(class_of "$out" media/jellyfin)" = "healthcheck" ] && echo 0 || echo 1) "$out"

# 6. Unreadable timestamp must not become a silent pass.
reset
mksample 1 "[('ai','openclaw','False','DependencyNotReady',None,'$DEP_MSG')]"
flux_notready_scan > "$TMP/out"; out=$(cat "$TMP/out")
check "unreadable lastTransitionTime -> STANDING" $([ "$(verdict_of "$out" ai/openclaw)" = "STANDING" ] && echo 0 || echo 1) "$out"

# 7. Listing failure is loud (rc 2), not empty-equals-clean.
reset
flux_notready_scan > "$TMP/out"; rc=$?; out=$(cat "$TMP/out")
check "listing failure -> rc 2" $([ "$rc" -eq 2 ] && echo 0 || echo 1) "rc=$rc out=$out"

# 8. Re-sample failure keeps PENDING and records the gap.
reset
mksample 1 "[('home-automation','frigate','False','DependencyNotReady',90,'$DEP_MSG')]"
flux_notready_scan > "$TMP/out"; out=$(cat "$TMP/out")
check "re-sample failure -> still PENDING + unmeasured recorded" \
    $([ "$(verdict_of "$out" home-automation/frigate)" = "PENDING" ] && [ "${#UNMEASURED[@]}" -eq 1 ] && echo 0 || echo 1) "unmeasured: ${UNMEASURED[*]:-none}"

# 9. All Ready -> empty output, rc 0.
reset
mksample 1 "[('a','b','True','ReconciliationSucceeded',5,'$READY_MSG')]"
flux_notready_scan > "$TMP/out"; rc=$?; out=$(cat "$TMP/out")
check "all Ready -> empty, rc 0" $([ "$rc" -eq 0 ] && [ -z "$out" ] && echo 0 || echo 1) "rc=$rc out=$out"

# 10. Section 5 wiring: scoring is gated on STANDING counts, not the raw sample.
sec5=$(awk '/log_section "Section 5: Helm Deployments"/{p=1} /log_section "Section 6:/{p=0} p' "$HC")
check "Section 5 calls flux_notready_scan" $(printf '%s' "$sec5" | grep -q 'FLUX_NR_SCAN=$(flux_notready_scan)' && echo 0 || echo 1)
check "dependency MAJOR is gated on FLUX_STANDING_DEP" \
    $(printf '%s' "$sec5" | grep -B2 'add_major_issue "Kustomizations blocked by dependencies' | grep -q 'FLUX_STANDING_DEP" -gt 0' && echo 0 || echo 1)
check "raw NOT_RECONCILED no longer drives the healthy/unhealthy branch" \
    $(printf '%s' "$sec5" | grep -q '"\$FLUX_STANDING" -eq 0 \] && \[ "\$FAILED_HELMREPOS" -eq 0' && echo 0 || echo 1)

# --- COMMISSIONING STRAW ------------------------------------------------------
# Pre-fix logic, transcribed: any not-Ready condition in the single sample was
# scored ("Kustomizations blocked by dependencies: N"). If that logic passed
# case 1, this file would be blind to the very regression it exists to catch.
echo "commissioning straw (pre-fix logic must FAIL case 1)"
straw_verdict() { echo STANDING; }   # single sample, no persistence, no grace
reset
mksample 1 "[('home-automation','frigate','False','DependencyNotReady',90,'$DEP_MSG')]"
mksample 2 "[]"
saved=$(declare -f flux_notready_verdict)
eval "flux_notready_verdict() { straw_verdict; }"
flux_notready_scan > "$TMP/out"; straw_out=$(cat "$TMP/out")
eval "$saved"
check "STRAW: pre-fix scoring turns the transient into STANDING (test would fail -> witness is real)" \
    $([ "$(verdict_of "$straw_out" home-automation/frigate)" = "STANDING" ] && echo 0 || echo 1) "$straw_out"

echo ""
echo "  $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
