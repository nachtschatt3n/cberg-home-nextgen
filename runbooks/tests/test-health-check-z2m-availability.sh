#!/usr/bin/env bash
# Regression tests for the Zigbee availability classification in
# runbooks/health-check.sh Section 22 (F-cd07827d).
#
# state.json last_seen froze for every device at once, so Section 22's
# staleness detector recorded itself as unmeasured -- while the retained
# zigbee2mqtt/<device>/availability topics (a working measurement path the
# script never consulted) said five devices were offline and one topic had
# no device behind it at all. Each retained topic is now classified against
# the live registry: OFFLINE enabled member -> warning + minor naming the
# device (the registry path's treatment of a LIVE dark device); GHOST topic
# -> info naming it; ti.router -> UNMEASURABLE per SOP zigbee2mqtt.md §4f;
# registry unavailable or no topic at all -> unmeasured, never a pass.
#
# Hermetic: fixtures only (names synthetic, payloads in both Z2M shapes).
# Run directly:  bash runbooks/tests/test-health-check-z2m-availability.sh
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
open(out, "w").write("\n\n".join(grab(n) for n in ("z2m_classify_availability", "z2m_score_availability")))
PY

WARN=(); INFO=(); OK=(); MINOR=(); MAJOR=(); UNMEASURED=()
log_warning() { WARN+=("$1"); }
log_info()    { INFO+=("$1"); }
log_success() { OK+=("$1"); }
add_minor_issue() { MINOR+=("$1"); }
add_major_issue() { MAJOR+=("$1"); }
_record_unmeasured() { UNMEASURED+=("$1: $2"); }
_noise_tag() { case "$1" in *"Synthetic Flaky"*) printf ' [noise: known flaky]' ;; esac; }
source "$TMP/funcs.sh"
reset() { WARN=(); INFO=(); OK=(); MINOR=(); MAJOR=(); UNMEASURED=(); }

REGISTRY='[
  {"ieee_address":"0x00124b00deadc0de","friendly_name":"Coordinator","type":"Coordinator","disabled":false,"model_id":"SLZB"},
  {"ieee_address":"0xa4c1380000000001","friendly_name":"Synthetic Soil Probe","type":"EndDevice","disabled":false,"power_source":"Battery","model_id":"TS0601"},
  {"ieee_address":"0x0017880000000002","friendly_name":"Synthetic Flaky Spot","type":"Router","disabled":false,"power_source":"Mains (single phase)","model_id":"LCT003"},
  {"ieee_address":"0x00158d0000000003","friendly_name":"Synthetic Parked Plug","type":"Router","disabled":true,"power_source":"Mains (single phase)","model_id":"PLUG"},
  {"ieee_address":"0x000000020000001c","friendly_name":"Synthetic TI Router","type":"Router","disabled":false,"power_source":"Mains (single phase)","model_id":"ti.router"},
  {"ieee_address":"0x00158d0000000005","friendly_name":"Synthetic Quiet Sensor","type":"EndDevice","disabled":false,"power_source":"Battery","model_id":"WSDCGQ11LM"},
  {"ieee_address":"0x00158d0000000006","friendly_name":"Synthetic Online Sensor","type":"EndDevice","disabled":false,"power_source":"Battery","model_id":"WSDCGQ11LM"}
]'
AVAIL='zigbee2mqtt/Coordinator/availability {"state":"online"}
zigbee2mqtt/Synthetic Soil Probe/availability {"state":"offline"}
zigbee2mqtt/Synthetic Flaky Spot/availability offline
zigbee2mqtt/Synthetic Parked Plug/availability {"state":"offline"}
zigbee2mqtt/Synthetic TI Router/availability {"state":"offline"}
zigbee2mqtt/Synthetic Online Sensor/availability {"state":"online"}
zigbee2mqtt/Synthetic Ghost Door/availability {"state":"offline"}'

PASS=0; FAIL=0
check() { if [ "$2" -eq 0 ]; then echo "  PASS  $1"; PASS=$((PASS+1)); else echo "  FAIL  $1"; [ -n "${3:-}" ] && printf '        %s\n' "$3"; FAIL=$((FAIL+1)); fi; }
joined() { printf '%s\n' "$@"; }
cls_of() { printf '%s\n' "$1" | awk -F'\t' -v k="$2" '$2==k{print $1}'; }

echo "zigbee availability topics against the live registry"

# 1. Classification.
cls=$(z2m_classify_availability "$AVAIL" "$REGISTRY")
check "enabled member offline (json payload) -> OFFLINE" $([ "$(cls_of "$cls" "Synthetic Soil Probe")" = "OFFLINE" ] && echo 0 || echo 1) "$cls"
check "enabled member offline (legacy plain payload) -> OFFLINE" $([ "$(cls_of "$cls" "Synthetic Flaky Spot")" = "OFFLINE" ] && echo 0 || echo 1) "$cls"
check "enabled member online -> ONLINE" $([ "$(cls_of "$cls" "Synthetic Online Sensor")" = "ONLINE" ] && echo 0 || echo 1) "$cls"
check "disabled member -> DISABLED (never scored)" $([ "$(cls_of "$cls" "Synthetic Parked Plug")" = "DISABLED" ] && echo 0 || echo 1) "$cls"
check "ti.router -> UNMEASURABLE (SOP §4f), whatever the topic says" $([ "$(cls_of "$cls" "Synthetic TI Router")" = "UNMEASURABLE" ] && echo 0 || echo 1) "$cls"
check "coordinator topic -> COORDINATOR" $([ "$(cls_of "$cls" "Coordinator")" = "COORDINATOR" ] && echo 0 || echo 1) "$cls"
check "topic with no registry device -> GHOST" $([ "$(cls_of "$cls" "Synthetic Ghost Door")" = "GHOST" ] && echo 0 || echo 1) "$cls"
check "registry device with no topic -> MISSING" $([ "$(cls_of "$cls" "Synthetic Quiet Sensor")" = "MISSING" ] && echo 0 || echo 1) "$cls"
check "OFFLINE line carries ieee, type and power source" $(printf '%s\n' "$cls" | grep -q $'^OFFLINE\tSynthetic Soil Probe\t0xa4c1380000000001\tEndDevice\tBattery\toffline$' && echo 0 || echo 1) "$cls"
check "empty registry -> every topic UNKNOWN" $([ "$(z2m_classify_availability "$AVAIL" "" | grep -c '^UNKNOWN')" -eq 7 ] && echo 0 || echo 1)
check "unparseable registry -> every topic UNKNOWN" $([ "$(z2m_classify_availability "$AVAIL" '{"not":"a list"' | grep -c '^UNKNOWN')" -eq 7 ] && echo 0 || echo 1)

# 2. Scoring.
reset; z2m_score_availability "$cls" > "$TMP/out"; out=$(cat "$TMP/out")
check "OFFLINE devices -> exactly one minor issue, no major" $([ ${#MINOR[@]} -eq 1 ] && [ ${#MAJOR[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${MINOR[@]:-none}")"
check "minor issue names each offline device with its IEEE and type" \
    $(joined "${MINOR[@]:-}" | grep -q 'Synthetic Soil Probe \[0xa4c1380000000001\] (EndDevice, Battery)' && joined "${MINOR[@]:-}" | grep -q 'Synthetic Flaky Spot \[0x0017880000000002\] (Router, Mains' && echo 0 || echo 1) "$(joined "${MINOR[@]:-none}")"
check "disabled, ti.router and ghost are NOT in the issue" \
    $(! joined "${MINOR[@]:-}" | grep -q 'Parked Plug\|TI Router\|Ghost Door' && echo 0 || echo 1) "$(joined "${MINOR[@]:-none}")"
check "ghost topic is an info line naming it" $(joined "${INFO[@]:-}" | grep -q 'no backing device: Synthetic Ghost Door' && echo 0 || echo 1) "$(joined "${INFO[@]:-none}")"
check "device without a topic is an info line naming it" $(joined "${INFO[@]:-}" | grep -q 'no retained availability topic: Synthetic Quiet Sensor' && echo 0 || echo 1) "$(joined "${INFO[@]:-none}")"
check "ti.router line cites SOP §4f" $(printf '%s' "$out" | grep -q 'Synthetic TI Router \[0x000000020000001c\]: topic says offline but a ti.router fails Z2M availability pings by design (SOP zigbee2mqtt.md §4f)' && echo 0 || echo 1) "$out"
check "printed OFFLINE line carries the noise tag" $(printf '%s' "$out" | grep -q 'Synthetic Flaky Spot \[0x0017880000000002\]: OFFLINE by availability signal (Router, Mains (single phase)) \[noise: known flaky\]' && echo 0 || echo 1) "$out"
check "coverage line: 7 topics, 2 online, 2 offline, 1 ghost, 1 unmeasurable, 1 missing" $(printf '%s' "$out" | grep -q 'topics: 7 (online 1, offline 2, ghost 1, unmeasurable 1); registry devices without a topic: 1' && echo 0 || echo 1) "$out"

# 3. All measurable devices online -> success, no issue.
reset; z2m_score_availability "$(z2m_classify_availability 'zigbee2mqtt/Synthetic Online Sensor/availability {"state":"online"}' "$REGISTRY")" > /dev/null
check "only online topics -> success, no issue" $([ ${#OK[@]} -eq 1 ] && [ ${#MINOR[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${OK[@]:-none}")"

# 4. Registry unavailable or no topic at all: unmeasured, never a pass.
reset; z2m_score_availability "$(z2m_classify_availability "$AVAIL" "")" > /dev/null
check "UNKNOWN entries -> unmeasured, no issue, no success" $([ ${#UNMEASURED[@]} -eq 1 ] && [ ${#MINOR[@]} -eq 0 ] && [ ${#OK[@]} -eq 0 ] && joined "${UNMEASURED[@]}" | grep -q 'zigbee-availability' && echo 0 || echo 1) "$(joined "${UNMEASURED[@]:-none}")"
reset; z2m_score_availability "$(z2m_classify_availability "" "$REGISTRY")" > /dev/null
check "no topic received (registry fine) -> unmeasured, not 'all missing'" $([ ${#UNMEASURED[@]} -eq 1 ] && [ ${#OK[@]} -eq 0 ] && [ ${#INFO[@]} -eq 0 ] && echo 0 || echo 1) "$(joined "${UNMEASURED[@]:-none}")"
reset; z2m_score_availability "" > /dev/null
check "empty class lines -> unmeasured" $([ ${#UNMEASURED[@]} -eq 1 ] && echo 0 || echo 1)

# 5. Script text: Section 22 consults the availability topics next to the registry path.
check "Section 22 fetches zigbee2mqtt/+/availability" $(grep -q "mosquitto_sub -h 127.0.0.1 -p 1883 -t 'zigbee2mqtt/+/availability' -v -W 8" "$HC" && echo 0 || echo 1)
check "Section 22 scores the classification in the main shell" $(grep -q 'z2m_score_availability "$(z2m_classify_availability "$Z2M_AVAIL_RAW" "${Z2M_BRIDGE_DEVICES_RAW:-}")"' "$HC" && echo 0 || echo 1)

# --- COMMISSIONING STRAW ------------------------------------------------------
# Pre-fix logic, transcribed from Section 22's saturation control: when every
# state.json entry is stale the detector records itself unmeasured and stops.
# On 2026-09-19 that was the whole story (24/24 stale) while five availability
# topics read offline. It must raise NO device-scoped issue -- proving case 2
# would fail against the old code.
echo "commissioning straw (pre-fix saturation control must FAIL case 2)"
straw_section22() {
    local offline_5d="$1" total="$2"
    if [ -n "$offline_5d" ] && [ -n "$total" ] && [ "$total" -gt 0 ] && [ "$offline_5d" -eq "$total" ] 2>/dev/null; then
        _record_unmeasured "zigbee-staleness" "every device with a last_seen is stale ($offline_5d/$total)"
        log_warning "Zigbee staleness detector is UNUSABLE"
    fi
}
reset
straw_section22 24 24
check "STRAW: frozen state.json yields only 'unmeasured' while devices are offline by a valid signal (test would fail -> witness is real)" \
    $([ ${#MINOR[@]} -eq 0 ] && [ ${#UNMEASURED[@]} -eq 1 ] && ! joined "${UNMEASURED[@]}" | grep -q 'Soil Probe' && echo 0 || echo 1) "$(joined "${UNMEASURED[@]:-none}")"

echo ""
echo "  $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
