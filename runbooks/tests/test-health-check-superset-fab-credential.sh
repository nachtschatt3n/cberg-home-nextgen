#!/usr/bin/env bash
# Regression tests for the Superset FAB vault-only credential assertion in
# runbooks/health-check.sh (F-9d938fce).
#
# superset-secrets.MU_ADM_PASSWORD (and ADMIN_PASSWORD, since
# init.createAdmin=false) is consumed by NO workload: Superset's metadata DB
# holds the live FAB hash, so an in-app reset drifts the SOPS copy silently
# and nothing could notice -- the pod is Ready, the Secret decrypts, SSO users
# never touch the db provider. The check performs a real login
# (POST /api/v1/security/login, provider db) from inside the web pod with the
# password on stdin: 200 ok, 401 -> MAJOR drift, unreachable -> unmeasured.
#
# Hermetic: superset_fab_score is driven with the status tokens
# superset_fab_probe emits; no credential is involved.
# Run directly:  bash runbooks/tests/test-health-check-superset-fab-credential.sh
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
open(out, "w").write(grab("superset_fab_score"))
PY

WARN=(); MINOR=(); MAJOR=(); UNMEASURED=(); CHECKS_PASSED=0
log_warning() { WARN+=("$1"); }
add_minor_issue() { MINOR+=("$1"); }
add_major_issue() { MAJOR+=("$1"); }
_record_unmeasured() { UNMEASURED+=("$1: $2"); }
source "$TMP/funcs.sh"
reset() { WARN=(); MINOR=(); MAJOR=(); UNMEASURED=(); CHECKS_PASSED=0; }

PASS=0; FAIL=0
check() { if [ "$2" -eq 0 ]; then echo "  PASS  $1"; PASS=$((PASS+1)); else echo "  FAIL  $1"; [ -n "${3:-}" ] && printf '        %s\n' "$3"; FAIL=$((FAIL+1)); fi; }
joined() { printf '%s\n' "$@"; }

echo "superset FAB vault-only credential"

reset; superset_fab_score mu_adm MU_ADM_PASSWORD 200 > /dev/null
check "200 -> counted as a passed check, no issue" $([ "$CHECKS_PASSED" -eq 1 ] && [ ${#MAJOR[@]} -eq 0 ] && [ ${#MINOR[@]} -eq 0 ] && [ ${#UNMEASURED[@]} -eq 0 ] && echo 0 || echo 1)

reset; superset_fab_score mu_adm MU_ADM_PASSWORD 401 > /dev/null
check "401 -> exactly one MAJOR naming the SOPS key and the FAB user" $([ ${#MAJOR[@]} -eq 1 ] && joined "${MAJOR[@]}" | grep -q 'superset-secrets.MU_ADM_PASSWORD is rejected for FAB user mu_adm (401)' && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"
check "401 MAJOR points at the rotation SOP" $(joined "${MAJOR[@]:-}" | grep -q 'docs/sops/in-app-credential-rotation.md' && echo 0 || echo 1)

for tok in nopod nosecret unreachable ""; do
    reset; superset_fab_score mu_adm MU_ADM_PASSWORD "$tok" > /dev/null
    check "'${tok:-<empty>}' -> unmeasured, no issue, not a pass" $([ ${#UNMEASURED[@]} -eq 1 ] && [ ${#MAJOR[@]} -eq 0 ] && [ ${#MINOR[@]} -eq 0 ] && [ "$CHECKS_PASSED" -eq 0 ] && joined "${UNMEASURED[@]}" | grep -q 'superset-fab-credential-MU_ADM_PASSWORD' && echo 0 || echo 1) "$(joined "${UNMEASURED[@]:-none}")"
done

reset; superset_fab_score mu_adm MU_ADM_PASSWORD 500 > /dev/null
check "500 -> minor (reachable, auth state unclear), not a pass" $([ ${#MINOR[@]} -eq 1 ] && [ ${#MAJOR[@]} -eq 0 ] && [ "$CHECKS_PASSED" -eq 0 ] && echo 0 || echo 1)

# Script text: how the probe handles the secret and where the section sits.
check "password reaches the pod on stdin (kubectl exec -i), never argv" $(grep -q "printf '%s' \"\$pw\" | kubectl exec -i -n \"\$ns\" \"\$pod\" -c superset -- python3 -c" "$HC" && echo 0 || echo 1)
check "only the username is passed as an argument to the in-pod python" $(grep -A18 'superset_fab_probe() {' "$HC" | grep -q '^user = sys.argv\[1\]' && grep -A18 'superset_fab_probe() {' "$HC" | grep -q '^pw = sys.stdin.read()' && echo 0 || echo 1)
check "the section probes MU_ADM_PASSWORD as mu_adm" $(grep -q '"mu_adm|MU_ADM_PASSWORD"' "$HC" && echo 0 || echo 1)
check "Superset section sits before report_unmeasured" $([ "$(grep -n '^log_section "Superset FAB Credential' "$HC" | cut -d: -f1)" -lt "$(grep -n '^report_unmeasured$' "$HC" | cut -d: -f1)" ] && echo 0 || echo 1)

# --- COMMISSIONING STRAW ------------------------------------------------------
# Pre-fix logic: the only thing anything asserted about this key was that the
# SOPS Secret exists and decodes (the sops-coverage and secret-readability
# checks). A key whose value the app rejects still decodes, so on the drift
# shape (Secret readable, login 401) it must raise NOTHING -- proving the 401
# case above would fail against the old code.
echo "commissioning straw (pre-fix 'secret decodes' logic must FAIL the 401 case)"
straw_secret_readable() {
    local decoded="$1"
    if [ -z "$decoded" ]; then
        add_major_issue "superset-secrets.MU_ADM_PASSWORD unreadable"
    fi
}
reset
straw_secret_readable "a-perfectly-decodable-but-stale-value"   # login would be 401
check "STRAW: a readable Secret satisfies the old check while FAB rejects it (test would fail -> witness is real)" \
    $([ ${#MAJOR[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"

echo ""
echo "  $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
