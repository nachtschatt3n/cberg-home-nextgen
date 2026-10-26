#!/usr/bin/env bash
# ninth-banner-logs.sh - recover CI pod logs / k8s events from Elasticsearch after
# the Job TTL has deleted the pods.
#
#   ninth-banner-logs.sh <pod-prefix> <from> <to>
#   ninth-banner-logs.sh --events ci-runner <from> <to> [pod-prefix]
#
# <from>/<to>: ISO-8601 UTC, e.g. 2026-10-20T08:50:00Z
# <pod-prefix>: must start with "tnb-" (the reader role cannot see anything else).
#
# Uses the read-only user ci-runner-reader (role ci-runner-logs-ro) through the
# filtered alias ci-runner-logs; see docs/sops/monitoring.md. The password is read
# from the cluster secret into an UNEXPORTED shell variable and handed only to the
# python3 reader's environment, never to the long-running kubectl port-forward
# (or any other child); it is never printed or put on a command line.
# Env: ES_LOCAL_PORT (default: a free port), MAX_LINES (default: unlimited).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

usage() {
    sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2
    exit 2
}

MODE=logs
if [ "${1:-}" = "--events" ]; then
    MODE=events
    shift
fi
[ "$#" -ge 3 ] || usage
TARGET="$1"   # pod prefix (logs) or namespace (events)
FROM="$2"
TO="$3"
EVENT_PREFIX="${4:-tnb-}"

KUBECTL=(mise exec -- kubectl)

ES_USER="$("${KUBECTL[@]}" -n monitoring get secret ci-runner-reader -o jsonpath='{.data.username}' | base64 -d)"
ES_PASS="$("${KUBECTL[@]}" -n monitoring get secret ci-runner-reader -o jsonpath='{.data.password}' | base64 -d)"
[ -n "$ES_USER" ] && [ -n "$ES_PASS" ] || { echo "FAIL: reader credentials missing in secret monitoring/ci-runner-reader" >&2; exit 1; }
# Deliberately NOT exported: an exported ES_PASS would sit in the environment of
# the port-forward below for its whole lifetime (readable via ps eww / procfs).

WORK="$(mktemp -d)"
PF_PID=""
cleanup() {
    [ -n "$PF_PID" ] && kill "$PF_PID" 2>/dev/null || true
    rm -rf "$WORK"
}
trap cleanup EXIT INT TERM

"${KUBECTL[@]}" -n monitoring get secret elasticsearch-es-http-certs-public \
    -o jsonpath='{.data.ca\.crt}' | base64 -d > "$WORK/ca.crt"
export ES_CA="$WORK/ca.crt"

PORT="${ES_LOCAL_PORT:-$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')}"
"${KUBECTL[@]}" -n monitoring port-forward svc/elasticsearch-es-http "${PORT}:9200" >"$WORK/pf.log" 2>&1 &
PF_PID=$!
PF_UP=0
for _ in $(seq 1 30); do
    if python3 -c "import socket,sys; socket.create_connection(('127.0.0.1',$PORT),1)" 2>/dev/null; then PF_UP=1; break; fi
    kill -0 "$PF_PID" 2>/dev/null || { echo "FAIL: port-forward died: $(cat "$WORK/pf.log")" >&2; exit 1; }
    sleep 1
done
if [ "$PF_UP" != 1 ]; then
    echo "FAIL: port-forward to monitoring/svc/elasticsearch-es-http did not accept connections on 127.0.0.1:${PORT} within 30 s" >&2
    echo "      port-forward log: $(cat "$WORK/pf.log" 2>/dev/null)" >&2
    exit 1
fi
export ES_URL="https://127.0.0.1:${PORT}"
export MODE TARGET FROM TO EVENT_PREFIX MAX_LINES="${MAX_LINES:-0}"

# Credentials go to this one process only (command-prefix assignment: in its
# environment, not on its command line, not exported to the shell).
ES_USER="$ES_USER" ES_PASS="$ES_PASS" python3 -I - <<'PY'
import base64, datetime as dt, json, os, ssl, sys, urllib.request

URL = os.environ["ES_URL"]
AUTH = "Basic " + base64.b64encode(
    f"{os.environ['ES_USER']}:{os.environ['ES_PASS']}".encode()).decode()
CTX = ssl.create_default_context(cafile=os.environ["ES_CA"])
CTX.check_hostname = False  # reached via port-forward on 127.0.0.1; chain still verified
ALIAS = "ci-runner-logs"
mode, target = os.environ["MODE"], os.environ["TARGET"]
frm, to = os.environ["FROM"], os.environ["TO"]
max_lines = int(os.environ["MAX_LINES"])


def req(method, path, body=None):
    r = urllib.request.Request(
        URL + path, method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": AUTH, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, context=CTX, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"FAIL: HTTP {e.code} on {method} {path}: {e.read()[:300].decode(errors='replace')}",
              file=sys.stderr)
        sys.exit(1)


def iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def get(src, path):
    for part in path:
        if not isinstance(src, dict):
            return None
        src = src.get(part)
    return src


def ingest_control():
    """Newest doc visible to the reader at all: proves ingestion + alias + auth work."""
    r = req("POST", f"/{ALIAS}/_search", {
        "size": 1, "sort": [{"@timestamp": "desc"}], "_source": False})
    hits = r["hits"]["hits"]
    if not hits:
        return "CONTROL: alias ci-runner-logs returns NO document at all (alias missing/empty or ingestion down)"
    return f"CONTROL: newest ci-runner doc visible to reader is {iso(hits[0]['sort'][0])} (cluster ingests; alias+auth OK)"


rng = {"range": {"@timestamp": {"gte": frm, "lte": to}}}
if mode == "logs":
    if not target.startswith("tnb-"):
        print("FAIL: pod prefix must start with 'tnb-'", file=sys.stderr)
        sys.exit(2)
    flt = [{"term": {"resource.attributes.k8s.namespace.name": "ci-runner"}},
           {"prefix": {"resource.attributes.k8s.pod.name": target}}, rng]
else:
    flt = [{"term": {"body.structured.object.regarding.namespace": target}},
           {"prefix": {"body.structured.object.regarding.name": os.environ["EVENT_PREFIX"]}}, rng]

total = 0
scroll_id = None
try:
    while True:
        if scroll_id is None:
            r = req("POST", f"/{ALIAS}/_search?scroll=2m", {
                "size": 5000, "sort": [{"@timestamp": "asc"}],
                "query": {"bool": {"filter": flt}}})
        else:
            r = req("POST", "/_search/scroll", {"scroll": "2m", "scroll_id": scroll_id})
        scroll_id = r.get("_scroll_id", scroll_id)
        hits = r["hits"]["hits"]
        if not hits:
            break
        for h in hits:
            s = h["_source"]
            ts = iso(h["sort"][0])
            if mode == "logs":
                pod = get(s, ["resource", "attributes", "k8s.pod.name"])
                line = get(s, ["body", "text"])
                print(f"{pod}\t{ts}\t{line}")
            else:
                o = get(s, ["body", "structured", "object"]) or {}
                reg = o.get("regarding") or {}
                note = (o.get("note") or "").replace("\n", " ")
                print(f"{ts}\t{get(s, ['body', 'structured', 'type'])}\t{o.get('type')}\t"
                      f"{reg.get('kind')}/{reg.get('name')}\t{o.get('reason')}\t{note}")
            total += 1
            if max_lines and total >= max_lines:
                raise SystemExit(0)
finally:
    if scroll_id:
        try:
            req("DELETE", "/_search/scroll", {"scroll_id": scroll_id})
        except SystemExit:
            pass

if total == 0:
    print(f"FAIL: zero {mode} for '{target}' between {frm} and {to}. A silent zero is not a pass.",
          file=sys.stderr)
    print(ingest_control(), file=sys.stderr)
    sys.exit(3)
print(f"# {total} {mode} returned", file=sys.stderr)
PY
