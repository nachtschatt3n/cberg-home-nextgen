#!/usr/bin/env bash
# UniFi reboot detector, 24h window (2026-10-26). The raw 24h uptime series was
# pulled through an influx_query with no --max-time and parsed client-side, so a
# failed / truncated / error read while the 15-min baseline worked produced
# resets([]) -> "None detected". Now: reset detection runs server-side in Flux,
# influx_query is bounded (--max-time) and fails on HTTP errors (--fail), and a
# zero-row / failed / error-table 24h read is WINDOW-UNMEASURED.
# This runs the SHIPPED verdict (INFLUX_BY_HEADER + UNIFI_REBOOT_VERDICT_PY,
# extracted from health-check.sh) against fixtures. The Flux rule itself was
# parity-checked against resets() on 30d of live data (218/218 events); the
# rule's semantics stay pinned by test-unifi-reboot-{zero-blips,guard}.py.
# BSD-safe; bash script, callers may be zsh.
set -u
HC="$(cd "$(dirname "$0")/.." && pwd)/health-check.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
fail=0
check() { if [ "$2" = "$3" ]; then echo "  PASS  $1"; else echo "  FAIL  $1 got [$2] want [$3]"; fail=1; fi; }

python3 - "$HC" "$TMP/verdict.py" <<'PY' || { echo "  FAIL  could not extract verdict code"; exit 1; }
import re, sys
s = open(sys.argv[1]).read()
a = re.search(r'INFLUX_BY_HEADER="(.*?)\n"\n', s, re.S)
b = re.search(r'UNIFI_REBOOT_VERDICT_PY="(.*?)\n"\n', s, re.S)
if not (a and b):
    sys.exit(1)
open(sys.argv[2], "w").write(a.group(1) + "\n" + b.group(1) + "\n")
PY

BASE=',result,table,_value,name
,_result,0,3196800,Basement-AP-U6+
,_result,1,600,Guest Room USW SW-8'
COUNTS=',result,table,_value,name,_measurement
,_result,0,719,Basement-AP-U6+,uap
,_result,1,719,Guest Room USW SW-8,usw'
RESETS_HDR=',result,table,_measurement,_time,name'
RESETS="$RESETS_HDR
,_result,0,uap,2026-10-26T01:00:00Z,Basement-AP-U6+
,_result,1,usw,2026-10-26T03:50:00Z,Guest Room USW SW-8"
ERRTAB='#datatype,string,string
#group,true,true
#default,,
,error,reference
,"runtime error @1:1-1:2: query terminated",'

run() {  # UPTIME COUNTS COUNTS_RC RESETS RESETS_RC
  UPTIME_CSV="$1" REBOOT_COUNTS_CSV="$2" REBOOT_COUNTS_RC="$3" \
  REBOOT_RESETS_CSV="$4" REBOOT_RESETS_RC="$5" python3 "$TMP/verdict.py" 2>&1
}
has() { printf '%s\n' "$1" | grep -c -- "$2"; }

o=$(run "$BASE" "$COUNTS" 0 "$RESETS_HDR" 0)
check "healthy window, no resets -> None detected" "$(has "$o" '^None detected')" "1"
check "None detected states coverage" "$(has "$o" '2 device series covered')" "1"

o=$(run "$BASE" "$COUNTS" 0 "$RESETS" 0)
check "real reset on a fresh device is reported" "$(has "$o" 'Guest Room USW SW-8 rebooted around')" "1"
check "reset on a >24h-uptime device is dropped as scrape gap" "$(has "$o" 'Basement-AP-U6+ rebooted')" "0"
check "dropped candidate is disclosed" "$(has "$o" '1 uptime-dip candidate')" "1"

o=$(run "$BASE" "" 0 "$RESETS_HDR" 0)
check "24h window ZERO rows, baseline fine -> WINDOW-UNMEASURED" "$(has "$o" 'WINDOW-UNMEASURED')" "1"
check "  ...and never None detected" "$(has "$o" 'None detected')" "0"

o=$(run "$BASE" "" 28 "" 28)
check "24h read timed out (curl 28) -> WINDOW-UNMEASURED" "$(has "$o" 'WINDOW-UNMEASURED: query failed (curl exit 28)')" "1"

o=$(run "$BASE" "$COUNTS" 0 "" 22)
check "reset query HTTP error (curl 22) -> WINDOW-UNMEASURED" "$(has "$o" 'WINDOW-UNMEASURED')" "1"

o=$(run "$BASE" "$COUNTS" 0 "$ERRTAB" 0)
check "Flux in-band error table -> WINDOW-UNMEASURED" "$(has "$o" 'WINDOW-UNMEASURED: InfluxDB returned an error table')" "1"

o=$(run "$BASE" "$ERRTAB" 0 "$RESETS_HDR" 0)
check "error table in the coverage read -> WINDOW-UNMEASURED" "$(has "$o" 'WINDOW-UNMEASURED')" "1"

o=$(run "" "" 7 "" 7)
check "baseline empty -> BASELINE-UNAVAILABLE (unchanged contract)" "$(has "$o" 'BASELINE-UNAVAILABLE')" "1"
check "  ...reset count reported as unknown when the reset read failed" "$(has "$o" 'unknown number of')" "1"

o=$(run "" "$COUNTS" 0 "$RESETS" 0)
check "baseline empty with resets -> candidates counted, not dropped" "$(has "$o" '2 uptime reset')" "1"

# Static: the live path is bounded and filtered server-side, and the shell
# routes WINDOW-UNMEASURED to unmeasured + an issue.
block=$(awk '/^    influx_query\(\) \{/{p=1} p{print} p&&/^    \}/{exit}' "$HC")
check "influx_query curl has --max-time" "$(printf '%s\n' "$block" | grep 'curl ' | grep -c -- '--max-time [0-9]')" "1"
check "influx_query curl has --fail" "$(printf '%s\n' "$block" | grep 'curl ' | grep -c -- '--fail')" "1"
check "Flux skips uptime<=0 blips server-side" "$(grep -c 'REBOOT_FLUX_SERIES=.*r._value > 0' "$HC")" "1"
check "Flux truncates time to whole seconds (parity with resets())" "$(grep -c 'int(v: r._time) / 1000000000)' "$HC")" "1"
check "Flux reset rule: difference() then > 60.0" "$(grep -c 'difference() |> filter(fn: (r) => r._value > 60.0)' "$HC")" "1"
check "raw 24h series is no longer pulled" "$(grep -c 'range(start: -24h) |> filter(fn: (r) => (r._measurement == "uap" or r._measurement == "usw") and r._field == "uptime") |> keep(' "$HC")" "0"
check "WINDOW-UNMEASURED recorded as unmeasured" "$(grep -c '_record_unmeasured "unifi-reboots-24h"' "$HC")" "2"
exit $fail
