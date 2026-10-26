#!/usr/bin/env bash
# 2026-10-26: the Frigate recording-coverage detector. The Reolink record path
# lost 13-19% of every day while camera_fps stayed > 0 and the crash scan was
# clean, so health-check.sh now scores seconds-recorded / window from Frigate's
# /api/<camera>/recordings. This test runs the SHIPPED frigate_coverage_scan
# (extracted from health-check.sh) against a fake curl serving fixtures built
# around "now", and checks: a camera at ~80% is LOW, a full camera is not,
# segments are clipped to the window (7h of segments never score > 100% and a
# 6h-old gap still counts), motion-only cameras are not scored, and every
# unreadable input is UNMEASURED (exit 2), never a clean zero.
# BSD-safe (no \s, no GNU-only flags). Bash script; callers may be zsh.
set -u
HC="$(cd "$(dirname "$0")/.." && pwd)/health-check.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
fail=0
check() { if [ "$2" = "$3" ]; then echo "  PASS  $1"; else echo "  FAIL  $1 got [$2] want [$3]"; fail=1; fi; }

fn=$(awk '/^frigate_coverage_scan\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$HC")
[ -n "$fn" ] || { echo "  FAIL  frigate_coverage_scan not found in health-check.sh"; exit 1; }
eval "$fn"

# Fake curl: serves $FIX/config.json for /api/config and $FIX/<cam>.json for
# /api/<cam>/recordings, writing to the -o path; FAKE_FAIL=<substring> makes a
# matching URL fail like curl -f on a 5xx.
mkdir -p "$TMP/bin" "$TMP/fix"
cat > "$TMP/bin/curl" <<'EOF'
#!/usr/bin/env bash
out=""; url=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    --max-time) shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
[ -n "${FAKE_FAIL:-}" ] && case "$url" in *"$FAKE_FAIL"*) exit 22 ;; esac
case "$url" in
  */api/config) src="$FIX/config.json" ;;
  */recordings\?*) cam="${url#*/api/}"; cam="${cam%%/*}"; src="$FIX/$cam.json" ;;
  *) exit 22 ;;
esac
[ -f "$src" ] || exit 22
cat "$src" > "$out"
EOF
chmod +x "$TMP/bin/curl"
export PATH="$TMP/bin:$PATH" FIX="$TMP/fix"

# Fixtures relative to now: 10 s segments over the last 7 h (wider than the
# 6 h window, so clipping is exercised). entry: every segment. kitchen: every
# 5th segment missing (~80%). heater: motion-only retention (continuous 0) and
# no segments at all -- must NOT be scored.
python3 - "$TMP/fix" <<'PY'
import json, sys, time
fix = sys.argv[1]
now = time.time()
def segs(skip_every=0):
    out, t, i = [], now - 7 * 3600, 0
    while t < now:
        if not (skip_every and i % skip_every == 0):
            out.append({"id": f"{t}", "start_time": t, "end_time": t + 10.0, "duration": 10.0})
        t += 10.0; i += 1
    return out
json.dump(segs(), open(f"{fix}/entry.json", "w"))
json.dump(segs(skip_every=5), open(f"{fix}/kitchen.json", "w"))
json.dump([], open(f"{fix}/heater.json", "w"))
cam = lambda days: {"enabled": True, "record": {"enabled": True, "continuous": {"days": days}}}
json.dump({"cameras": {"entry": cam(3.0), "kitchen": cam(3.0), "heater": cam(0.0)}},
          open(f"{fix}/config.json", "w"))
PY

# 1. Measured: kitchen LOW, entry not, heater unscored, entry clipped to <= 100.
out=$(frigate_coverage_scan 1 6 90); rc=$?
check "measured exit 0" "$rc" "0"
check "LOW names only kitchen" "$(printf '%s\n' "$out" | sed -n 's/^LOW.//p')" "kitchen"
entry=$(printf '%s\n' "$out" | awk -F'\t' '$1=="entry"{print $2}')
kitchen=$(printf '%s\n' "$out" | awk -F'\t' '$1=="kitchen"{print $2}')
check "entry scores ~100 (clipped, not >100)" "$(python3 -c "print(99.0 <= float('$entry') <= 100.0)")" "True"
check "kitchen scores ~80" "$(python3 -c "print(78.0 <= float('$kitchen') <= 82.0)")" "True"
check "motion-only heater not scored" "$(printf '%s\n' "$out" | grep -c '^heater')" "0"

# 2. Threshold is a parameter: at 75% nothing is LOW.
out=$(frigate_coverage_scan 1 6 75); rc=$?
check "75% threshold exit 0" "$rc" "0"
check "75% threshold no LOW line" "$(printf '%s\n' "$out" | grep -c '^LOW')" "0"

# 3. Unreadable config -> UNMEASURED, exit 2.
out=$(FAKE_FAIL=/api/config frigate_coverage_scan 1 6 90); rc=$?
check "config unreadable exit 2" "$rc" "2"
check "config unreadable says UNMEASURED" "$(printf '%s\n' "$out" | grep -c '^UNMEASURED')" "1"

# 4. One camera's recordings unreadable -> UNMEASURED, never a partial clean.
out=$(FAKE_FAIL=/api/kitchen/ frigate_coverage_scan 1 6 90); rc=$?
check "recordings unreadable exit 2" "$rc" "2"
check "recordings unreadable no LOW line" "$(printf '%s\n' "$out" | grep -c '^LOW')" "0"

# 5. Recordings not a list (error object) -> UNMEASURED.
cp "$TMP/fix/kitchen.json" "$TMP/kitchen.bak"
echo '{"success": false, "message": "boom"}' > "$TMP/fix/kitchen.json"
out=$(frigate_coverage_scan 1 6 90); rc=$?
check "error object exit 2" "$rc" "2"
cp "$TMP/kitchen.bak" "$TMP/fix/kitchen.json"

# 6. No camera with continuous recording -> UNMEASURED (not "all fine").
echo '{"cameras": {"heater": {"enabled": true, "record": {"enabled": true, "continuous": {"days": 0}}}}}' > "$TMP/fix/config.json"
out=$(frigate_coverage_scan 1 6 90); rc=$?
check "no scored camera exit 2" "$rc" "2"

# 7. Straw: the pre-fix caller hit 127.0.0.1:5000 = AirPlay 403 and parsed it
# as SUMMARY:0/0. The caller must no longer hardcode that port.
check "caller no longer forwards a fixed 5000" "$(grep -c 'svc/frigate 5000:5000' "$HC")" "0"
check "caller uses a private port" "$(grep -c 'svc/frigate "${FRIGATE_PORT}:5000"' "$HC")" "1"

[ "$fail" -eq 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
