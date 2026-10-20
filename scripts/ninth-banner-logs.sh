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
# from the cluster secret into an env var and is never printed.
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
export ES_USER ES_PASS

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
for _ in $(seq 1 30); do
    if python3 -c "import socket,sys; socket.create_connection(('127.0.0.1',$PORT),1)" 2>/dev/null; then break; fi
    kill -0 "$PF_PID" 2>/dev/null || { echo "FAIL: port-forward died: $(cat "$WORK/pf.log")" >&2; exit 1; }
    sleep 1
done
export ES_URL="https://127.0.0.1:${PORT}"
export MODE TARGET FROM TO EVENT_PREFIX MAX_LINES="${MAX_LINES:-0}"

python3 -I - <<'PY'
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

pit = req("POST", f"/{ALIAS}/_pit?keep_alive=2m")["id"]
total = 0
search_after = None
try:
    while True:
        body = {"size": 5000, "pit": {"id": pit, "keep_alive": "2m"},
                "sort": [{"@timestamp": "asc"}, {"_shard_doc": "asc"}],
                "query": {"bool": {"filter": flt}}, "track_total_hits": False}
        if search_after:
            body["search_after"] = search_after
        r = req("POST", "/_search", body)
        pit = r.get("pit_id", pit)
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
        search_after = hits[-1]["sort"]
finally:
    try:
        req("DELETE", "/_pit", {"id": pit})
    except SystemExit:
        pass

if total == 0:
    print(f"FAIL: zero {mode} for '{target}' between {frm} and {to}. A silent zero is not a pass.",
          file=sys.stderr)
    print(ingest_control(), file=sys.stderr)
    sys.exit(3)
print(f"# {total} {mode} returned", file=sys.stderr)
PY
