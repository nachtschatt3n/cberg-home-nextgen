#!/usr/bin/env bash
# F-fe94e75c (+ 2026-10-26 follow-up): the Frigate crash-loop detector must key
# on watchdog.<camera> crash lines over a 6h TIME window, and must actually READ
# that window. With a label selector kubectl defaults --tail to 10, so
# `--since=6h` alone read at most 10 lines (10 vs 17,378 measured live). This
# test runs the SHIPPED frigate_crash_scan (extracted from health-check.sh)
# against a fake kubectl that implements that selector default, so dropping
# --tail=-1 makes the early-in-window crash vanish and the test fail.
# Also: "No resources found" / empty window / kubectl failure -> UNMEASURED.
# BSD-safe (no \s, no GNU-only flags). Bash script; callers may be zsh.
set -u
HC="$(cd "$(dirname "$0")/.." && pwd)/health-check.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
fail=0
check() { if [ "$2" = "$3" ]; then echo "  PASS  $1"; else echo "  FAIL  $1 got [$2] want [$3]"; fail=1; fi; }

fn=$(awk '/^frigate_crash_scan\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$HC")
[ -n "$fn" ] || { echo "  FAIL  frigate_crash_scan not found in health-check.sh"; exit 1; }
eval "$fn"

# Fake kubectl: records argv, emits $FAKE_LOG honouring kubectl's real tail
# default (10 with -l and no --tail, all lines with --tail=-1), or simulates
# no-match / failure.
mkdir -p "$TMP/bin"
cat > "$TMP/bin/kubectl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" > "$FAKE_ARGV"
echo 'Defaulted container "frigate" out of: frigate, copyconfig (init)' >&2
case "${FAKE_MODE:-ok}" in
  nomatch) echo "No resources found in home-automation namespace." >&2; exit 0 ;;
  fail)    echo "error: You must be logged in to the server (Unauthorized)" >&2; exit 1 ;;
  empty)   exit 0 ;;
esac
tail_n=""; sel=0
for a in "$@"; do
  case "$a" in
    -l|--selector|-l=*|--selector=*) sel=1 ;;
    --tail=*) tail_n="${a#--tail=}" ;;
  esac
done
[ -z "$tail_n" ] && { [ "$sel" -eq 1 ] && tail_n=10 || tail_n=-1; }
if [ "$tail_n" = "-1" ]; then cat "$FAKE_LOG"; else tail -n "$tail_n" "$FAKE_LOG"; fi
EOF
chmod +x "$TMP/bin/kubectl"
export PATH="$TMP/bin:$PATH" FAKE_ARGV="$TMP/argv" FAKE_LOG="$TMP/log"

# Fixture: two crash lines EARLY in the 6h window, then 40 lines of ordinary
# chatter -- a --tail=10 read sees none of the crashes.
{
  echo '2026-10-19 01:00:00  [2026-10-19 03:00:00] watchdog.kids                 ERROR   : Ffmpeg process crashed unexpectedly for kids.'
  echo '2026-10-19 01:00:01  [2026-10-19 03:00:01] watchdog.kids                 INFO    : The following ffmpeg logs include the last 100 lines'
  echo '2026-10-19 01:10:00  [2026-10-19 03:10:00] watchdog.kids                 ERROR   : Ffmpeg process crashed unexpectedly for kids.'
  echo '2026-10-19 01:10:00  [2026-10-19 03:10:00] watchdog.living_room          INFO    : Terminating the existing ffmpeg process...'
  echo '2026-10-19 01:20:00  [2026-10-19 03:20:00] watchdog.front-door           ERROR   : Ffmpeg process crashed unexpectedly for front-door.'
  i=0; while [ $i -lt 40 ]; do echo "2026-10-19 02:00:$i  frigate.app INFO : chatter $i"; i=$((i+1)); done
} > "$FAKE_LOG"

# 1. Rendered command reads the whole time window.
out=$(FAKE_MODE=ok frigate_crash_scan 6h); rc=$?
argv=$(cat "$FAKE_ARGV")
check "command carries --tail=-1" "$(printf '%s' "$argv" | grep -c -- '--tail=-1')" "1"
check "command carries --since=6h" "$(printf '%s' "$argv" | grep -c -- '--since=6h')" "1"
check "command uses the frigate label selector" "$(printf '%s' "$argv" | grep -c -- '-l app.kubernetes.io/name=frigate')" "1"
check "measured -> exit 0" "$rc" "0"
got=$(printf '%s\n' "$out" | awk 'NF{print $2":"$1}' | tr '\n' ' ')
check "early crashes found (kids x2, front-door x1; terminate is not a crash)" "$got" "kids:2 front-door:1 "

# 2. Control: the fake really implements the selector tail default, so the
# --tail=-1 above is what made case 1 pass (a 10-line read finds nothing).
ctl=$(kubectl logs -n home-automation -l app.kubernetes.io/name=frigate --since=6h 2>/dev/null | grep -c 'crashed unexpectedly')
check "control: selector read without --tail sees 0 crash lines" "$ctl" "0"

# 3. No crash lines in a non-empty window -> measured clean (empty stdout).
printf 'x watchdog.kids INFO : ok\n' > "$FAKE_LOG"
out=$(FAKE_MODE=ok frigate_crash_scan 6h); rc=$?
check "no crash lines -> exit 0" "$rc" "0"
check "no crash lines -> empty" "$out" ""

# 4. Silent-zero shapes are UNMEASURED, never clean.
for m in nomatch empty fail; do
  out=$(FAKE_MODE=$m frigate_crash_scan 6h); rc=$?
  check "$m -> exit 2 (UNMEASURED)" "$rc" "2"
  check "$m -> UNMEASURED reason line" "$(printf '%s' "$out" | grep -c '^UNMEASURED')" "1"
done
check "nomatch reason names the selector" "$(FAKE_MODE=nomatch frigate_crash_scan 6h | grep -c 'no pod matched')" "1"
check "fail reason carries kubectl's error, not the Defaulted-container note" \
  "$(FAKE_MODE=fail frigate_crash_scan 6h | grep -c 'Unauthorized')" "1"

# 5. Static: the caller routes exit 2 to _record_unmeasured, and no Frigate
# crash read without --tail=-1 remains.
check "caller records unmeasured" "$(grep -c '_record_unmeasured "frigate-crash-loops"' "$HC")" "1"
check "no --since frigate read without --tail=-1" \
  "$(grep 'name=frigate --since' "$HC" | grep -vc -- '--tail=-1')" "0"
exit $fail
