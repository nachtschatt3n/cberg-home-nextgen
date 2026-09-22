#!/usr/bin/env bash
# Regression tests for the Zigbee battery emitter in runbooks/health-check.sh
# Section 33 (F-3faa37f8).
#
# Issue titles carried only a COUNT ("Critical battery levels (<10%): 2
# devices ..."), so an accepted-risk needle -- a substring match on the title
# -- could only ever match the count and therefore masked WHICHEVER device was
# critical, not the one it was accepted for (AR-042, now disabled). Titles
# now name every device (friendly name, IEEE, level) so a needle can be
# scoped to one device. The 10-29% warning band, previously unreachable
# (its test repeated the critical `<10`), is asserted too.
#
# Hermetic: fixtures only (synthetic device names).
# Run directly:  bash runbooks/tests/test-health-check-battery-device-scope.sh
set -uo pipefail
HC="$(cd "$(dirname "$0")/.." && pwd)/health-check.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

python3 - "$HC" "$TMP/funcs.sh" <<'PY'
import sys
src, out = sys.argv[1], sys.argv[2]
s = open(src).read()
i = s.index("zigbee_battery_assess() {")
j = s.index("\n}\n", i) + 3
open(out, "w").write(s[i:j])
PY

MAJOR=(); MINOR=(); WARN=(); OK=()
log_warning() { WARN+=("$1"); }
log_success() { OK+=("$1"); }
add_major_issue() { MAJOR+=("$1"); }
add_minor_issue() { MINOR+=("$1"); }
_noise_tag() { :; }
source "$TMP/funcs.sh"
reset() { MAJOR=(); MINOR=(); WARN=(); OK=(); }

PASS=0; FAIL=0
check() { if [ "$2" -eq 0 ]; then echo "  PASS  $1"; PASS=$((PASS+1)); else echo "  FAIL  $1"; [ -n "${3:-}" ] && printf '        %s\n' "$3"; FAIL=$((FAIL+1)); fi; }
joined() { printf '%s\n' "$@"; }

LIST=$'Synthetic Soil Probe|0|0xdeadbeef00000001\nSynthetic Door Contact|7|0xdeadbeef00000002\nSynthetic Hall Sensor|25|0xdeadbeef00000003\nSynthetic Window Sensor|41|0xdeadbeef00000004\nSynthetic Healthy Sensor|88|0xdeadbeef00000005\n'

echo "battery issue titles are device-scoped"

reset; zigbee_battery_assess "$LIST" > "$TMP/out"; out=$(cat "$TMP/out")
check "one MAJOR for the two critical devices" $([ ${#MAJOR[@]} -eq 1 ] && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"
check "MAJOR title names each critical device with IEEE and level" \
    $(joined "${MAJOR[@]:-}" | grep -q 'Synthetic Soil Probe \[0xdeadbeef00000001\] 0%' && joined "${MAJOR[@]:-}" | grep -q 'Synthetic Door Contact \[0xdeadbeef00000002\] 7%' && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"
check "MAJOR title still carries the count" $(joined "${MAJOR[@]:-}" | grep -q '2 device(s) need immediate replacement' && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"
check "a device-scoped needle matches only its own device's title" \
    $(joined "${MAJOR[@]:-}" | grep -q '0xdeadbeef00000001' && ! joined "${MINOR[@]:-}" | grep -q '0xdeadbeef00000001' && echo 0 || echo 1)
check "10-29% band is reachable: one MINOR naming the 25% device" \
    $([ ${#MINOR[@]} -eq 1 ] && joined "${MINOR[@]}" | grep -q 'Synthetic Hall Sensor \[0xdeadbeef00000003\] 25%' && echo 0 || echo 1) "$(joined "${MINOR[@]:-none}")"
check "30-49% is monitor-only (no issue), >=50% is good" \
    $(! joined "${MAJOR[@]:-}" "${MINOR[@]:-}" | grep -q 'Window Sensor\|Healthy Sensor' && printf '%s' "$out" | grep -q 'Synthetic Window Sensor \[0xdeadbeef00000004\] (41%)' && echo 0 || echo 1) "$out"
check "report block lists the critical device under CRITICAL" $(printf '%s' "$out" | grep -A2 'CRITICAL (<10%)' | grep -q 'Synthetic Soil Probe' && echo 0 || echo 1)

reset; zigbee_battery_assess $'Synthetic Healthy Sensor|88|0xdeadbeef00000005\n' > "$TMP/out"; out=$(cat "$TMP/out")
check "all healthy -> no issues, success logged" $([ ${#MAJOR[@]} -eq 0 ] && [ ${#MINOR[@]} -eq 0 ] && [ ${#OK[@]} -eq 1 ] && echo 0 || echo 1)

# Section wiring: the section feeds friendly|battery|ieee into the function.
sec=$(awk '/log_section "Section 33: Battery Health/{p=1} /log_section "Section 34:/{p=0} p' "$HC")
check "Section 33 builds friendly|battery|ieee and calls zigbee_battery_assess" \
    $(printf '%s' "$sec" | grep -q 'BATTERY_LIST="${BATTERY_LIST}${friendly}|${battery}|${ieee}"' && printf '%s' "$sec" | grep -q 'zigbee_battery_assess "$BATTERY_LIST"' && echo 0 || echo 1)
check "the count-only title is gone from the script" $(! grep -q 'add_major_issue "Critical battery levels (<10%): \$CRITICAL_COUNT devices' "$HC" && echo 0 || echo 1)

# --- COMMISSIONING STRAW ------------------------------------------------------
# Pre-fix emitter, transcribed: count-only titles, and the warning band's test
# repeating `<10`. Against the same fixture it must produce a MAJOR title with
# NO device in it and NO minor for the 25% device -- so the assertions above
# would fail against the old code.
echo "commissioning straw (pre-fix emitter must FAIL the device-scope assertions)"
straw_assess() {
    local list="$1" friendly battery battery_int CRITICAL_COUNT=0 WARNING_COUNT=0
    while IFS='|' read -r friendly battery; do
        [ -n "$friendly" ] && [ -n "$battery" ] || continue
        battery_int=$(echo "$battery" | awk '{print int($1)}')
        if [ "$battery_int" -lt 10 ]; then CRITICAL_COUNT=$((CRITICAL_COUNT + 1))
        elif [ "$battery_int" -lt 10 ]; then WARNING_COUNT=$((WARNING_COUNT + 1)); fi
    done <<< "$list"
    [ "$CRITICAL_COUNT" -gt 0 ] && add_major_issue "Critical battery levels (<10%): $CRITICAL_COUNT devices need immediate replacement"
    [ "$WARNING_COUNT" -gt 0 ] && add_minor_issue "Low batteries (15-30%): $WARNING_COUNT devices need replacement soon"
    return 0
}
reset; straw_assess "$LIST"
check "STRAW: count-only title names no device (test would fail -> witness is real)" \
    $([ ${#MAJOR[@]} -eq 1 ] && ! joined "${MAJOR[@]}" | grep -q '0xdeadbeef\|Synthetic' && echo 0 || echo 1) "$(joined "${MAJOR[@]:-none}")"
check "STRAW: pre-fix warning band is dead (no MINOR for the 25% device)" $([ ${#MINOR[@]} -eq 0 ] && echo 0 || echo 1)

echo ""
echo "  $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
