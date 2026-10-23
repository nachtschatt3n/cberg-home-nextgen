#!/usr/bin/env bash
# F-737d8339: the Section 34 ES probe helper must print "unknown" (never 0) on a
# dead forward or a hung listener, within a bounded time. The helper is
# extracted from health-check.sh so the shipped code is what is tested.
# Works under bash and zsh invocations (script itself is bash). BSD-safe: no
# `timeout`, no \s.
set -u
HC="$(cd "$(dirname "$0")/.." && pwd)/health-check.sh"
fail=0
check() { if [ "$2" = "$3" ]; then echo "  PASS  $1"; else echo "  FAIL  $1 got [$2] want [$3]"; fail=1; fi; }

fn=$(awk '/^es_probe_val\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$HC")
[ -n "$fn" ] || { echo "  FAIL  es_probe_val not found"; exit 1; }
eval "$fn"

# 1. dead forward (nothing listening)
port=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1])")
t0=$(date +%s)
v=$(es_probe_val pw "https://localhost:$port/_cluster/health" status)
t1=$(date +%s)
check "dead forward -> unknown" "$v" "unknown"
[ $((t1 - t0)) -lt 60 ] && echo "  PASS  dead forward finished in $((t1 - t0))s (<60)" || { echo "  FAIL  too slow"; fail=1; }

# 2. hung listener: accepts TCP, never answers (the trustd-hang shape)
python3 - "$port" <<'PY' &
import socket, sys, time
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", int(sys.argv[1]))); s.listen(5)
c = []
t = time.time()
while time.time() - t < 60:
    s.settimeout(1)
    try: c.append(s.accept()[0])
    except Exception: pass
PY
srv=$!
sleep 1
t0=$(date +%s)
v=$(es_probe_val pw "https://localhost:$port/logs-generic-default/_count" count)
t1=$(date +%s)
kill $srv 2>/dev/null; wait $srv 2>/dev/null
check "hung listener -> unknown" "$v" "unknown"
[ $((t1 - t0)) -lt 60 ] && echo "  PASS  hung listener bounded at $((t1 - t0))s (<60)" || { echo "  FAIL  not bounded"; fail=1; }

# 3. static: no unguarded curl to 9201 and no lsof kill on 9201 remain
check "no lsof kill on 9201" "$(grep -c 'lsof -ti:9201' "$HC")" "0"
check "no curl against ES_PROBE_PORT/9201" "$(grep -c 'curl.*localhost:\(9201\|\${ES_PROBE_PORT}\)' "$HC")" "0"
check "9200 curls carry --max-time" "$(grep 'curl.*localhost:9200' "$HC" | grep -vc -- '--max-time 20 --connect-timeout 5')" "0"
exit $fail
