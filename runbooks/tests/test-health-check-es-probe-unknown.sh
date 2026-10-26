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

# 3. es_http (raw-body sibling used by the error-log / es_count / es_query /
# attribution paths): same bound, and failure is EMPTY output + non-zero exit.
fn2=$(awk '/^es_http\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$HC")
[ -n "$fn2" ] || { echo "  FAIL  es_http not found"; exit 1; }
eval "$fn2"
port2=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1])")
out=$(es_http pw "https://localhost:$port2/x/_search" '{"size":0}' 10); rc=$?
check "es_http dead forward -> empty output" "$out" ""
[ "$rc" -ne 0 ] && echo "  PASS  es_http dead forward -> non-zero exit ($rc)" || { echo "  FAIL  es_http dead forward exited 0"; fail=1; }
python3 - "$port2" <<'PY2' &
import socket, sys, time
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", int(sys.argv[1]))); s.listen(5)
c = []
t = time.time()
while time.time() - t < 40:
    s.settimeout(1)
    try: c.append(s.accept()[0])
    except Exception: pass
PY2
srv2=$!
sleep 1
t0=$(date +%s)
out=$(es_http pw "https://localhost:$port2/x/_search" '{"size":0}' 8); rc=$?
t1=$(date +%s)
kill $srv2 2>/dev/null; wait $srv2 2>/dev/null
check "es_http hung listener -> empty output" "$out" ""
[ "$rc" -ne 0 ] && [ $((t1 - t0)) -lt 20 ] && echo "  PASS  es_http hung listener bounded at $((t1 - t0))s, exit $rc" || { echo "  FAIL  es_http not bounded ($((t1 - t0))s, rc=$rc)"; fail=1; }

# 4. static: no ES call goes through curl (its --max-time does not bound the
# macOS trustd hang); no fixed-port lsof kill for ES/Prometheus (it killed a
# concurrent sibling sweep's forward); a failed error-log query prints
# unknown, never 0.
check "no lsof kill on 9201" "$(grep -c 'lsof -ti:9201' "$HC")" "0"
check "no lsof kill on ES_PORT/PROM_PORT" "$(grep -cE 'lsof -ti:"?[$][{](ES_PORT|PROM_PORT)[}]' "$HC")" "0"
check "no curl against any https://localhost ES forward" "$(grep -c 'curl.*https://localhost' "$HC")" "0"
check "no fixed 9200:9200 port-forward" "$(grep -c 'port-forward.*elasticsearch-es-http 9200:9200' "$HC")" "0"
check "error-log total falls back to unknown, not 0" "$(grep -c "print('unknown')" "$HC")" "1"
# The TOTAL_ERRORS parser block must exist (fail loud if not) and carry no
# print('0') fallback.
blk=$(python3 - "$HC" <<'PY2'
import sys
s = open(sys.argv[1]).read()
i = s.find('TOTAL_ERRORS=$(printf')
j = s.find('esac', i)
print(s[i:j] if i >= 0 and j > i else "")
PY2
)
[ -n "$blk" ] && echo "  PASS  TOTAL_ERRORS parser block located" || { echo "  FAIL  TOTAL_ERRORS parser block not found"; fail=1; }
check "error-log total has no print('0') fallback" "$(printf '%s\n' "$blk" | grep -c "print('0')")" "0"
check "unknown total is recorded as unmeasured" "$(printf '%s\n' "$blk" | grep -c '_record_unmeasured "es-error-logs"')" "1"
exit $fail
