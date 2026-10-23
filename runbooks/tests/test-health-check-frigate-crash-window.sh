#!/usr/bin/env bash
# F-fe94e75c: the Frigate crash-loop detector must key on watchdog.<camera>
# crash lines over a 6h TIME window (not --tail=500) so it re-emits while crash
# lines exist. The sed expression is extracted from health-check.sh. BSD sed.
set -u
HC="$(cd "$(dirname "$0")/.." && pwd)/health-check.sh"
fail=0
check() { if [ "$2" = "$3" ]; then echo "  PASS  $1"; else echo "  FAIL  $1 got [$2] want [$3]"; fail=1; fi; }
check "uses --since=6h" "$(grep -c 'frigate --since=6h' "$HC")" "1"
check "no --tail=500 crash window" "$(grep -c 'tail=500 2>&1 | grep "crashed' "$HC")" "0"
expr=$(grep -o "sed -n 's/.*watchdog[^']*'" "$HC" | head -1 | sed "s/^sed -n '//; s/'\$//")
[ -n "$expr" ] || { echo "  FAIL  sed expr not found"; exit 1; }
LOG='2026-10-19 01:00:00  [2026-10-19 03:00:00] watchdog.kids                 ERROR   : Ffmpeg process crashed unexpectedly for kids.
2026-10-19 01:00:01  [2026-10-19 03:00:01] watchdog.kids                 INFO    : The following ffmpeg logs include the last 100 lines
2026-10-19 01:10:00  [2026-10-19 03:10:00] watchdog.kids                 ERROR   : Ffmpeg process crashed unexpectedly for kids.
2026-10-19 01:10:00  [2026-10-19 03:10:00] watchdog.living_room          INFO    : Terminating the existing ffmpeg process...
2026-10-19 01:20:00  [2026-10-19 03:20:00] watchdog.front-door           ERROR   : Ffmpeg process crashed unexpectedly for front-door.'
got=$(printf '%s\n' "$LOG" | sed -n "$expr" | sort | uniq -c | sort -rn | awk '{print $2":"$1}' | tr '\n' ' ')
check "kids x2 and front-door x1 detected; living_room terminate is not a crash" "$got" "kids:2 front-door:1 "
check "no crash lines -> empty" "$(printf 'x watchdog.kids INFO : ok\n' | sed -n "$expr")" ""
exit $fail
