#!/usr/bin/env bash
# Regression tests for the Zigbee staleness classification in
# runbooks/health-check.sh Sections 22 + 32 (F-ae98282d).
#
# A fixed "baseline 23 decommissioned devices" used to explain every stale
# state.json entry; by 2026-09 it exceeded the whole population and labelled
# enabled, interview-complete devices (one dark three weeks on a flat battery)
# as removed hardware. Each stale address is now looked up in the LIVE
# registry (zigbee2mqtt/bridge/devices): LIVE member -> warning + minor issue
# naming the device; ORPHAN -> info; registry unavailable -> unmeasured, never
# "decommissioned".
#
# Hermetic: fixtures only.
# Run directly:  bash runbooks/tests/test-health-check-z2m-stale-registry.sh
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
open(out, "w").write("\n\n".join(grab(n) for n in ("z2m_classify_stale", "z2m_score_stale")))
PY

WARN=(); INFO=(); MINOR=(); MAJOR=(); UNMEASURED=()
log_warning() { WARN+=("$1"); }
log_info()    { INFO+=("$1"); }
add_minor_issue() { MINOR+=("$1"); }
add_major_issue() { MAJOR+=("$1"); }
_record_unmeasured() { UNMEASURED+=("$1: $2"); }
_noise_tag() { case "$1" in *"Synthetic Flaky"*) printf ' [noise: known flaky]' ;; esac; }
source "$TMP/funcs.sh"
reset() { WARN=(); INFO=(); MINOR=(); MAJOR=(); UNMEASURED=(); Z2M_STALE_SCORED=0; }

REGISTRY='[
  {"ieee_address":"0x00124b00deadc0de","friendly_name":"Coordinator","type":"Coordinator","disabled":false,"interview_completed":true},
  {"ieee_address":"0xa4c1380000000001","friendly_name":"Synthetic Soil Probe","type":"EndDevice","disabled":false,"interview_completed":true},
  {"ieee_address":"0x00158d0000000002","friendly_name":"Synthetic Flaky Sensor","type":"EndDevice","disabled":false,"interview_completed":true},
  {"ieee_address":"0x00158d0000000003","friendly_name":"Synthetic Parked Plug","type":"Router","disabled":true,"interview_completed":true}
]'
STALE=$'STALE:0xa4c1380000000001:21.6d\nSTALE:0x00158d0000000002:18.2d\nSTALE:0x00158d0000000003:40.0d\nSTALE:0x0000000000000bad:200.0d'

PASS=0; FAIL=0
check() { if [ "$2" -eq 0 ]; then echo "  PASS  $1"; PASS=$((PASS+1)); else echo "  FAIL  $1"; [ -n "${3:-}" ] && printf '        %s\n' "$3"; FAIL=$((FAIL+1)); fi; }
joined() { printf '%s\n' "$@"; }
cls_of() { printf '%s\n' "$1" | awk -F'\t' -v k="$2" '$2==k{print $1}'; }

echo "zigbee stale-entry classification against the live registry"

# 1. Classification.
cls=$(z2m_classify_stale "$STALE" "$REGISTRY")
check "enabled registry member -> LIVE"       $([ "$(cls_of "$cls" 0xa4c1380000000001)" = "LIVE" ] && echo 0 || echo 1) "$cls"
check "disabled registry member -> DISABLED" $([ "$(cls_of "$cls" 0x00158d0000000003)" = "DISABLED" ] && echo 0 || echo 1) "$cls"
check "address absent from registry -> ORPHAN" $([ "$(cls_of "$cls" 0x0000000000000bad)" = "ORPHAN" ] && echo 0 || echo 1) "$cls"
check "friendly name carried on LIVE lines" $(printf '%s\n' "$cls" | grep -q $'^LIVE\t0xa4c1380000000001\t21.6\tSynthetic Soil Probe$' && echo 0 || echo 1) "$cls"
check "empty registry -> every entry UNKNOWN" $([ "$(z2m_classify_stale "$STALE" "" | grep -c '^UNKNOWN')" -eq 4 ] && echo 0 || echo 1)
check "unparseable registry -> every entry UNKNOWN" $([ "$(z2m_classify_stale "$STALE" '{"not":"a list"' | grep -c '^UNKNOWN')" -eq 4 ] && echo 0 || echo 1)
check "no stale lines -> no output" $([ -z "$(z2m_classify_stale "" "$REGISTRY")" ] && echo 0 || echo 1)

# 2. Scoring: LIVE devices are a warning + a minor issue NAMING each device.
reset
z2m_score_stale "$cls" > "$TMP/out"; out=$(cat "$TMP/out")
check "LIVE entries -> exactly one minor issue" $([ ${#MINOR[@]} -eq 1 ] && [ ${#MAJOR[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${MINOR[@]:-none}")"
check "minor issue names the device, its IEEE and the dark age" \
    $(joined "${MINOR[@]:-}" | grep -q 'Synthetic Soil Probe \[0xa4c1380000000001\] 21.6d' && joined "${MINOR[@]:-}" | grep -q 'Synthetic Flaky Sensor \[0x00158d0000000002\] 18.2d' && echo 0 || echo 1) "$(joined "${MINOR[@]:-none}")"
check "disabled + orphan entries are NOT in the issue" \
    $(! joined "${MINOR[@]:-}" | grep -q 'Parked Plug' && ! joined "${MINOR[@]:-}" | grep -q '0x0000000000000bad' && echo 0 || echo 1) "$(joined "${MINOR[@]:-none}")"
check "orphan entries are an info line" $(joined "${INFO[@]:-}" | grep -q 'orphan state entries (not in registry): 1' && echo 0 || echo 1) "$(joined "${INFO[@]:-none}")"
check "printed LIVE line carries the noise tag" $(printf '%s' "$out" | grep -q 'Synthetic Flaky Sensor \[0x00158d0000000002\]: dark 18.2d -- LIVE registry member \[noise: known flaky\]' && echo 0 || echo 1) "$out"
check "the word 'decommissioned' is gone from the scoring" $(! printf '%s\n' "$out" "${INFO[@]:-}" "${WARN[@]:-}" | grep -qi 'decommissioned' && echo 0 || echo 1)

# 3. One dark device is one finding, not two (Section 22 then Section 32).
z2m_score_stale "$cls" > "$TMP/out"; out2=$(cat "$TMP/out")
check "second scoring call does not double-count" $([ ${#MINOR[@]} -eq 1 ] && printf '%s' "$out2" | grep -q 'already scored' && echo 0 || echo 1) "$(joined "${MINOR[@]:-none}")"

# 4. Registry unavailable: unmeasured, never a quiet pass or a decommissioned label.
reset
z2m_score_stale "$(z2m_classify_stale "$STALE" "")" > "$TMP/out"; out=$(cat "$TMP/out")
check "UNKNOWN entries -> unmeasured recorded, no minor issue" \
    $([ ${#UNMEASURED[@]} -eq 1 ] && [ ${#MINOR[@]} -eq 0 ] && joined "${UNMEASURED[@]}" | grep -q 'zigbee-stale-registry' && echo 0 || echo 1) "$(joined "${UNMEASURED[@]:-none}")"
check "UNKNOWN does not consume the scored flag (a later section may still score)" $([ "${Z2M_STALE_SCORED:-0}" -eq 0 ] && echo 0 || echo 1)

# 5. Script text: the baseline constant is retired from BOTH sections.
check "Z2M_OFFLINE_BASELINE no longer exists in health-check.sh" $(! grep -q 'Z2M_OFFLINE_BASELINE' "$HC" && echo 0 || echo 1)
check "Section 22 and Section 32 both call z2m_classify_stale" $([ "$(grep -c 'z2m_classify_stale "$(echo' "$HC")" -eq 2 ] && echo 0 || echo 1)

# --- COMMISSIONING STRAW ------------------------------------------------------
# Pre-fix logic, transcribed from Section 32: a count against baseline 23+5,
# else an info line calling the entries decommissioned. With our four stale
# entries (three of them live devices) it must raise NO issue -- proving the
# assertion in case 2 would fail against the old code.
echo "commissioning straw (pre-fix baseline logic must FAIL case 2)"
straw_score() {
    local n="$1" total="$2" Z2M_OFFLINE_BASELINE=23
    if [ -n "$n" ] && [ "${n:-0}" -gt $((Z2M_OFFLINE_BASELINE + 5)) ] 2>/dev/null; then
        add_minor_issue "Zigbee devices offline >5 days: $n/$total (baseline $Z2M_OFFLINE_BASELINE)"
    elif [ -n "$n" ] && [ "${n:-0}" -gt 0 ] 2>/dev/null; then
        log_info "Zigbee stale state entries: $n (baseline $Z2M_OFFLINE_BASELINE — decommissioned devices)"
    fi
}
reset
straw_score 4 24
check "STRAW: baseline logic files no device-scoped issue and calls them decommissioned (test would fail -> witness is real)" \
    $([ ${#MINOR[@]} -eq 0 ] && joined "${INFO[@]:-}" | grep -q 'decommissioned' && echo 0 || echo 1) "$(joined "${INFO[@]:-none}")"

echo ""
echo "  $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
