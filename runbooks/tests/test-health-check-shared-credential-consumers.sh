#!/usr/bin/env bash
# Regression tests for the Shared API Credentials probe in
# runbooks/health-check.sh (F-b5ac6c77).
#
# The probe used to exec into openclaw only and only check liveness. A pod
# rolled minutes BEFORE Flux rewrote its Secret keeps the old value for as
# long as it lives (mcpo, 2026-09-14: a day on a deleted token, undetected).
# Now every Secret-backed consumer is probed and each probe first compares
# the sha256 prefix of the in-pod env value with the live Secret's, naming
# the pod's startTime and the Secret's last write in the finding.
#
# Hermetic: kubectl is a stub. The two in-pod scripts (hash + liveness) are
# the REAL scripts, executed locally by the stub with a fake curl/sha256sum
# on PATH, so URL trimming and the stdin-config header path are exercised.
# Run directly:  bash runbooks/tests/test-health-check-shared-credential-consumers.sh
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
open(out, "w").write("\n\n".join(grab(n) for n in (
    "_iso_to_epoch", "_secret_sha8", "_secret_last_write", "_pod_env_sha8", "check_api_credential")))
PY

# Fake in-pod tools: curl records its stdin config + argv and answers
# FAKE_HTTP_CODE; sha256sum maps onto macOS shasum.
FAKEBIN="$TMP/bin"; mkdir -p "$FAKEBIN"
cat > "$FAKEBIN/curl" <<'SH'
#!/bin/sh
cat > "$FAKE_CURL_LOG.cfg"
printf '%s\n' "$@" > "$FAKE_CURL_LOG.args"
printf '%s' "${FAKE_HTTP_CODE:-200}"
SH
cat > "$FAKEBIN/sha256sum" <<'SH'
#!/bin/sh
if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$@"; else /usr/bin/sha256sum "$@"; fi
SH
chmod +x "$FAKEBIN/curl" "$FAKEBIN/sha256sum"
export FAKE_CURL_LOG="$TMP/curl" FAKE_HTTP_CODE=200

# Fixture knobs (exported so the locally-executed in-pod scripts see them)
SECRET_VALUE="secret-value-current"; POD_VALUE="secret-value-current"
POD_URL="http://paperless.example/api"; POD_START="2026-09-15T06:56:00Z"; SECRET_WRITE="2026-09-14T06:53:38Z"
SECRET_READABLE=1

kubectl() {
    case "$*" in
        *"get pods"*)                 echo "fake-pod-1   1/1   Running   0   3d" ;;
        *"--show-managed-fields"*)    printf '{"metadata":{"creationTimestamp":"2026-01-01T00:00:00Z","managedFields":[{"manager":"kustomize-controller","time":"%s","fieldsV1":{"f:data":{}}}]}}' "$SECRET_WRITE" ;;
        *"get secret"*)               [ "$SECRET_READABLE" -eq 1 ] && printf '%s' "$SECRET_VALUE" | base64 ;;
        *"get pod "*startTime*)       printf '%s' "$POD_START" ;;
        exec\ *)
            # Run the REAL in-pod script locally with the pod's env.
            local args=("$@") i=0
            while [ $i -lt ${#args[@]} ]; do [ "${args[$i]}" = "--" ] && break; i=$((i+1)); done
            local rest=("${args[@]:$((i+1))}")
            env PATH="$FAKEBIN:$PATH" PAPERLESS_TOKEN="$POD_VALUE" PAPERLESS_URL="$POD_URL" "${rest[@]}"
            ;;
        *) return 1 ;;
    esac
}
source "$TMP/funcs.sh"

CRIT=(); MAJOR=(); MINOR=(); WARN=(); OUT=""; CHECKS_PASSED=0
log_warning()  { WARN+=("$1"); }
log_critical() { :; }
add_critical_issue() { CRIT+=("$1"); }
add_major_issue()    { MAJOR+=("$1"); }
add_minor_issue()    { MINOR+=("$1"); }
reset() { CRIT=(); MAJOR=(); MINOR=(); WARN=(); rm -f "$FAKE_CURL_LOG".*; }
run() { check_api_credential "Paperless (test)" ai "app.kubernetes.io/instance=test" app PAPERLESS_TOKEN "$1" "/api/documents/?page_size=1" test-secret PAPERLESS_TOKEN > "$TMP/out" 2>&1; OUT=$(cat "$TMP/out"); }
sha8() { printf %s "$1" | "$FAKEBIN/sha256sum" | cut -c1-8; }

PASS=0; FAIL=0
check() { if [ "$2" -eq 0 ]; then echo "  PASS  $1"; PASS=$((PASS+1)); else echo "  FAIL  $1"; [ -n "${3:-}" ] && printf '        %s\n' "$3"; FAIL=$((FAIL+1)); fi; }
joined() { printf '%s\n' "$@"; }

echo "shared credential consumers"

# 1. Fresh pod, valid token: no issues, hash reported as matching.
reset; POD_VALUE="$SECRET_VALUE"; FAKE_HTTP_CODE=200; run PAPERLESS_URL
check "matching hash + 200 -> no issues" $([ ${#CRIT[@]} -eq 0 ] && [ ${#MAJOR[@]} -eq 0 ] && [ ${#MINOR[@]} -eq 0 ] && echo 0 || echo 1) "$OUT"
check "output names the matching sha prefix" $(printf '%s' "$OUT" | grep -q "matches Secret test-secret.PAPERLESS_TOKEN ($(sha8 "$SECRET_VALUE"))" && echo 0 || echo 1) "$OUT"
check "URL ending in /api is trimmed before the probe path" \
    $(grep -qx 'http://paperless.example/api/documents/?page_size=1' "$FAKE_CURL_LOG.args" && echo 0 || echo 1) "$(cat "$FAKE_CURL_LOG.args" 2>/dev/null)"
check "token reaches curl via stdin config, never argv" \
    $(grep -q "Authorization: Token $POD_VALUE" "$FAKE_CURL_LOG.cfg" && ! grep -q "$POD_VALUE" "$FAKE_CURL_LOG.args" && echo 0 || echo 1)

# 2. THE REGRESSION: pod holds an OLD value (rolled before the Secret rewrite).
reset; POD_VALUE="secret-value-deleted"; FAKE_HTTP_CODE=401; run PAPERLESS_URL
want_pod=$(sha8 "$POD_VALUE"); want_sec=$(sha8 "$SECRET_VALUE")
check "stale pod value -> MAJOR stale-credential finding" $([ ${#MAJOR[@]} -eq 1 ] && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"
check "MAJOR names both sha prefixes, pod startTime and Secret write" \
    $(joined "${MAJOR[@]:-}" | grep -q "$want_pod" && joined "${MAJOR[@]:-}" | grep -q "$want_sec" && joined "${MAJOR[@]:-}" | grep -q "$POD_START" && joined "${MAJOR[@]:-}" | grep -q "$SECRET_WRITE" && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"
check "401 on a stale pod is attributed to the pod, not the Secret" \
    $([ ${#CRIT[@]} -eq 1 ] && joined "${CRIT[@]}" | grep -q 'STALE' && ! joined "${CRIT[@]}" | grep -q 'All consumers' && echo 0 || echo 1) "$(joined "${CRIT[@]:-none}")"

# 3. Fresh pod but the Secret's value itself is rejected -> every consumer broken.
reset; POD_VALUE="$SECRET_VALUE"; FAKE_HTTP_CODE=401; run PAPERLESS_URL
check "401 with matching hash -> CRITICAL 'All consumers'" \
    $([ ${#MAJOR[@]} -eq 0 ] && [ ${#CRIT[@]} -eq 1 ] && joined "${CRIT[@]}" | grep -q 'All consumers' && echo 0 || echo 1) "$(joined "${CRIT[@]:-none}")"

# 4. Unreadable Secret must not read as "fresh".
reset; SECRET_READABLE=0; POD_VALUE="$SECRET_VALUE"; FAKE_HTTP_CODE=200; run PAPERLESS_URL; SECRET_READABLE=1
check "unreadable Secret -> MINOR 'freshness not compared'" \
    $([ ${#MINOR[@]} -eq 1 ] && joined "${MINOR[@]}" | grep -q 'freshness not compared' && echo 0 || echo 1) "$(joined "${MINOR[@]:-none}")"

# 5. Pod older than the Secret's last write but the value is unchanged: info only.
reset; POD_VALUE="$SECRET_VALUE"; POD_START="2026-09-10T00:00:00Z"; FAKE_HTTP_CODE=200; run PAPERLESS_URL; POD_START="2026-09-15T06:56:00Z"
check "older pod + matching hash -> info line, no issue" \
    $([ ${#MAJOR[@]} -eq 0 ] && [ ${#MINOR[@]} -eq 0 ] && printf '%s' "$OUT" | grep -q 'value unchanged' && echo 0 || echo 1) "$OUT"

# 6. A literal in-cluster URL (consumer without a URL env var) is used as-is.
reset; POD_VALUE="$SECRET_VALUE"; FAKE_HTTP_CODE=200; run "http://paperless-ngx.office.svc:8000"
check "literal URL -> probe path appended to it" \
    $(grep -qx 'http://paperless-ngx.office.svc:8000/api/documents/?page_size=1' "$FAKE_CURL_LOG.args" && echo 0 || echo 1) "$(cat "$FAKE_CURL_LOG.args" 2>/dev/null)"

# 7. Section wiring: every Secret-backed consumer is called, before the
#    issue-count freeze, in the main shell.
wiring() { # $1 = script file
    grep -q '"app.kubernetes.io/instance=openclaw" "app"' "$1" &&
    grep -q '"app.kubernetes.io/instance=mcpo" "app"' "$1" &&
    grep -q '"mcpo-api-key" "paperless-api-key"' "$1" &&
    grep -q '"app.kubernetes.io/instance=arag-web" "app"' "$1" &&
    grep -q '"arag-web-secret" "PAPERLESS_API_KEY"' "$1"
}
check "openclaw, mcpo and arag-web are all probed" $(wiring "$HC" && echo 0 || echo 1)
sec_line=$(grep -n 'log_section "Shared API Credentials"' "$HC" | cut -d: -f1)
freeze_line=$(grep -n '^# Generate Issues Summary' "$HC" | cut -d: -f1)
check "credential section runs BEFORE the issue-count freeze" $([ -n "$sec_line" ] && [ -n "$freeze_line" ] && [ "$sec_line" -lt "$freeze_line" ] && echo 0 || echo 1) "section=$sec_line freeze=$freeze_line"
sec_block=$(awk -v s="$sec_line" 'NR>=s' "$HC" | awk '/^\{$/{p=1} p{print} /^\} (>>|\|)/{if(p) exit}')
check "credential section is a >> block (main shell), not a | tee subshell" \
    $(printf '%s' "$sec_block" | tail -1 | grep -q '^} >> "\$OUTPUT_FILE"' && echo 0 || echo 1) "$(printf '%s' "$sec_block" | tail -1)"

# --- COMMISSIONING STRAW ------------------------------------------------------
# (a) Pre-fix probe, transcribed: liveness only, no freshness comparison. It
#     must NOT raise the stale-credential MAJOR for case 2.
echo "commissioning straw (pre-fix logic must FAIL cases 2 and 7)"
straw_check_api_credential() {
    local label="$1" ns="$2" sel="$3" ctr="$4" tokenv="$5" urlenv="$6" path="$7"
    local pod code
    pod=$(kubectl get pods -n "$ns" -l "$sel" --no-headers 2>/dev/null | awk '$3=="Running"{print $1; exit}')
    [ -z "$pod" ] && return 0
    code="$FAKE_HTTP_CODE"
    case "$code" in
        200) CHECKS_PASSED=$((CHECKS_PASSED + 1)) ;;
        401|403) add_critical_issue "$label API token invalid ($code): $ns/secret.key is rejected. All consumers are broken until it is re-minted." ;;
    esac
}
reset; POD_VALUE="secret-value-deleted"; FAKE_HTTP_CODE=401
straw_check_api_credential "Paperless (test)" ai "sel" app PAPERLESS_TOKEN PAPERLESS_URL "/p" >/dev/null
check "STRAW a: pre-fix probe raises no stale-credential MAJOR (test would fail -> witness is real)" \
    $([ ${#MAJOR[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"
# (b) Pre-fix wiring: the openclaw call alone. The wiring check must reject it.
grep -v 'instance=mcpo\|instance=arag-web' "$HC" > "$TMP/straw-script.sh"
check "STRAW b: openclaw-only wiring is rejected by the coverage check" $(wiring "$TMP/straw-script.sh" && echo 1 || echo 0)

echo ""
echo "  $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
