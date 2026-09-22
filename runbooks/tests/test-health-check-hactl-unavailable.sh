#!/usr/bin/env bash
# Regression tests for the hactl doctor scope in runbooks/health-check.sh
# Section 31 (F-0a79466d).
#
# The loop ran config_entries + zombie_devices only, so the sweep never saw
# entity availability: hactl's `unavailable` check reported well over a
# hundred truly-unavailable entities while the sweep printed "2 warning hactl
# finding(s)". The scope now includes `unavailable` (the real check name --
# the finding's action text guessed `unavailable_entities`, which hactl does
# not know), and the collect/sum logic is a function this file drives with
# Summary blocks shaped exactly like hactl's.
#
# Hermetic: run_hactl and sleep are stubs.
# Run directly:  bash runbooks/tests/test-health-check-hactl-unavailable.sh
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
m = re.search(r'^HACTL_DOCTOR_CHECKS=.*$', s, re.M)
open(out, "w").write((m.group(0) if m else "") + "\n\n" +
                     "\n\n".join(grab(n) for n in ("hactl_doctor_collect", "hactl_doctor_counts")))
PY

# Fixtures in hactl's real output shape (entity names are synthetic).
summary() { printf '\n=== Summary ===\n  Critical:   %s\n  Warnings:   %s\n  Info:       %s\n  OK:         1\n  Actionable: %s\n\n  Overall Health: WARNING\n' "$1" "$2" "$3" "$2"; }
{ printf '\n=== Home Assistant Health Report ===\n  Instance: https://ha.example\n\n--- Integrations ---\n  CRIT  synthetic_integration: setup_error\n'; summary 1 0 1; } > "$TMP/config_entries.txt"
{ printf '\n=== Home Assistant Health Report ===\n  Instance: https://ha.example\n\n--- Zombie Devices ---\n  WARN  2 devices with no entities\n'; summary 0 2 27; } > "$TMP/zombie_devices.txt"
{ printf '\n=== Home Assistant Health Report ===\n  Instance: https://ha.example\n\n--- Unavailable Entities (17 found) ---\n  WARN  Truly unavailable: 182 entities across 71 device groups\n  WARN    synthetic_group_a: 17 entities\n'; summary 0 12 5; } > "$TMP/unavailable.txt"
printf 'Error: Unknown check: unavailable_entities\n' > "$TMP/unavailable_entities.txt"
printf 'Error: HTTP 502 from HA API\n' > "$TMP/flaky.txt"

SLEPT=()
calls_n() { [ -f "$TMP/calls" ] && wc -l < "$TMP/calls" | tr -d " " || echo 0; }
run_hactl() { # doctor --check NAME (runs inside $(...), so record to a file)
    echo "$3" >> "$TMP/calls"
    cat "$TMP/$3.txt" 2>/dev/null || echo "Error: Unknown check: $3"
}
sleep() { SLEPT+=("$1"); }
source "$TMP/funcs.sh"

PASS=0; FAIL=0
check() { if [ "$2" -eq 0 ]; then echo "  PASS  $1"; PASS=$((PASS+1)); else echo "  FAIL  $1"; [ -n "${3:-}" ] && printf '        %s\n' "$3"; FAIL=$((FAIL+1)); fi; }

echo "hactl doctor scope"

check "HACTL_DOCTOR_CHECKS names the real check 'unavailable'" \
    $(printf ' %s ' "${HACTL_DOCTOR_CHECKS:-}" | grep -q ' unavailable ' && echo 0 || echo 1) "HACTL_DOCTOR_CHECKS='${HACTL_DOCTOR_CHECKS:-}'"
check "HACTL_DOCTOR_CHECKS keeps config_entries + zombie_devices" \
    $(printf ' %s ' "${HACTL_DOCTOR_CHECKS:-}" | grep -q ' config_entries ' && printf ' %s ' "${HACTL_DOCTOR_CHECKS:-}" | grep -q ' zombie_devices ' && echo 0 || echo 1)
check "the guessed name 'unavailable_entities' is NOT in scope" \
    $(! printf ' %s ' "${HACTL_DOCTOR_CHECKS:-}" | grep -q ' unavailable_entities ' && echo 0 || echo 1)

# 1. Live-shaped run over the real scope: 1 critical, 14 warnings.
rm -f "$TMP/calls"; SLEPT=()
hactl_doctor_collect $HACTL_DOCTOR_CHECKS > "$TMP/out"; out=$(cat "$TMP/out")
read -r crit warn <<< "$(hactl_doctor_counts "$hactl_summaries")"
check "counts over the full scope = 1 critical, 14 warnings" $([ "$crit" = "1" ] && [ "$warn" = "14" ] && echo 0 || echo 1) "crit=$crit warn=$warn"
check "each check ran exactly once" $([ "$(calls_n)" -eq 3 ] && [ "${#SLEPT[@]}" -eq 0 ] && echo 0 || echo 1) "calls=$(cat "$TMP/calls" 2>/dev/null | tr "\n" " ")"
check "bodies include the Unavailable Entities section" $(printf '%s' "$hactl_bodies" | grep -q '^--- Unavailable Entities' && echo 0 || echo 1)
check "bodies exclude the Summary and the Instance line" $(! printf '%s' "$hactl_bodies" | grep -q 'Summary\|Instance:' && echo 0 || echo 1)

# 2. Section wiring: the loop drives HACTL_DOCTOR_CHECKS and the counts helper.
sec=$(awk '/log_section "Section 31: Home Assistant/{p=1} /log_section "Section 32:/{p=0} p' "$HC")
check "Section 31 collects via hactl_doctor_collect \$HACTL_DOCTOR_CHECKS" $(printf '%s' "$sec" | grep -q 'hactl_doctor_collect \$HACTL_DOCTOR_CHECKS' && echo 0 || echo 1)
check "Section 31 sums via hactl_doctor_counts" $(printf '%s' "$sec" | grep -q 'hactl_doctor_counts "\$hactl_summaries"' && echo 0 || echo 1)
check "no hard-coded check list remains in Section 31" $(! printf '%s' "$sec" | grep -q 'for chk in config_entries' && echo 0 || echo 1)

# 3. A transient no-Summary check is retried with backoff and reported.
rm -f "$TMP/calls"; SLEPT=()
hactl_doctor_collect flaky > "$TMP/out"; out=$(cat "$TMP/out")
check "no-Summary check: 3 attempts, backoff 5s then 10s" $([ "$(calls_n)" -eq 3 ] && [ "${SLEPT[*]:-}" = "5 10" ] && echo 0 || echo 1) "calls=$(calls_n) slept=${SLEPT[*]:-}"
check "no-Summary check is reported, not silently dropped" $(printf '%s' "$out" | grep -q 'no summary after retry' && echo 0 || echo 1) "$out"

# --- COMMISSIONING STRAW ------------------------------------------------------
# Pre-fix scope, and the misnamed check from the finding record: both must
# leave the sweep at 2 warnings, i.e. the case-1 assertion must FAIL.
echo "commissioning straw (pre-fix scope must FAIL case 1)"
rm -f "$TMP/calls"; SLEPT=()
hactl_doctor_collect config_entries zombie_devices >/dev/null
read -r crit warn <<< "$(hactl_doctor_counts "$hactl_summaries")"
check "STRAW a: pre-fix scope reports 1 critical, 2 warnings (test would fail -> witness is real)" $([ "$crit" = "1" ] && [ "$warn" = "2" ] && echo 0 || echo 1) "crit=$crit warn=$warn"
rm -f "$TMP/calls"; SLEPT=()
hactl_doctor_collect config_entries zombie_devices unavailable_entities >/dev/null
read -r crit warn <<< "$(hactl_doctor_counts "$hactl_summaries")"
check "STRAW b: the record's guessed name adds nothing (unknown check, still 2 warnings)" $([ "$crit" = "1" ] && [ "$warn" = "2" ] && echo 0 || echo 1) "crit=$crit warn=$warn"

echo ""
echo "  $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
