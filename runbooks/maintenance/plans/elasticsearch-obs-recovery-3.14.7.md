---
plan_id: elasticsearch-obs-recovery-3.14.7
component: elasticsearch-obs-recovery
pr: null                              # no Renovate PR — coverage.py direct-bump lane (needs_plan),
                                      # dispatched by the nightly window 2026-09-25 Step 0.5
kind: image
current: "3.12-alpine"                # docker.io/library/python:3.12-alpine (float tag, no digest,
                                      # imagePullPolicy IfNotPresent) — live on
                                      # cronjob/elasticsearch-obs-recovery, measured 2026-09-25 01:50Z.
                                      # Running pods resolve to python@sha256:236173eb… (a node-cached
                                      # older 3.12-alpine build; today's 3.12-alpine index is 4c47124a…,
                                      # which is PYTHON_VERSION 3.12.14).
target: "3.14.7-alpine"               # pinned as 3.14.7-alpine@sha256:9e9fde4d… (index digest, Docker
                                      # Hub, pushed 2026-09-21; same digest as 3.14-alpine; base
                                      # alpine-minirootfs 3.24.2 — identical base to today's 3.12-alpine)
update_type: minor
risk: low                             # Stateless, stdlib-only script (base64/json/os/ssl/sys/time/
                                      # urllib/datetime — none removed in 3.13/3.14). The one
                                      # behaviour change on its path (3.13 ssl strict-X509 defaults)
                                      # was MEASURED against the live ECK cert and passes (§1.3). The
                                      # RED/notify path cannot be forced in-cluster, so it is proven
                                      # under 3.14 by a mock harness with a working negative control
                                      # (§2.3). git-revert rollback, no forward-only step.
est_duration_min: 40                  # pre-check harness + live dry-run ~8, edit/commit/push ~3,
                                      # Flux pickup ≤5, TWO scheduled */10 runs ≤20, checks ~4
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - cronjob/elasticsearch-obs-recovery
    - kustomization/elasticsearch      # the Flux KS that applies the edit (ns monitoring). It
                                      # also owns elasticsearch.yaml (the ES CR), otel-ilm-job and
                                      # the secret — all UNCHANGED by this plan, so the reconcile
                                      # is a no-op for them.
    - "docker.io/library/python"
  shared: [monitoring]                # The job is the automated recovery path for the shared
                                      # ES OTel obs streams (metrics/logs/traces) and the ONLY
                                      # notifier for ES RED (it POSTs ElasticsearchClusterRed to
                                      # Alertmanager — there is no ES exporter). A broken job
                                      # does not break ingestion, it removes the self-heal +
                                      # the page. §4 also reads Prometheus.
depends_on: []
conflicts_with:
  - kube-prometheus-stack-91.4.1      # §4.5 reads Prometheus (kube-state-metrics series) and the
                                      # job's RED notify targets that chart's Alertmanager; a
                                      # same-night KPS restart makes an empty read look like a
                                      # regression of this bump.
  - edot-collector-0.161.0            # §4.5 gates on EsMetricsIngestionStalled/EsLogIngestionStalled
                                      # not firing; a collector bump that stalls export would trip
                                      # them for a reason unrelated to this image.
  - talos-1.14.1                      # node reboots restart the single-node ES (transient
                                      # yellow/RED, shard recovery) — exactly the state this job
                                      # acts on. Never run the first 3.14 cycles through a node roll.
  - flux-reconciler-impersonation     # changes how Flux applies namespaces; a stalled reconcile of
                                      # KS elasticsearch at §3.3 would be misread as a bad image.
exclusive: false
security_ref: null
capability_change: false              # same script, same schedule, same env; interpreter only
rollback_class: git-revert            # stateless CronJob; nothing forward-only happens
finding_refs: [F-c9568174]
status: vetted   # 2026-09-26 plan-reviewer ready-for-go (0 blocking); fixed W path, full-SHA premise, 4.4 can-fail demo, context-guard wording applied
window: "now:2026-09-26"   # ON-DEMAND NOW run 2026-09-26 (run-now.py stamp; was None)
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-25"
premises:
  - id: cronjob-still-on-3.12-alpine
    why: "`current:` claims the float tag python:3.12-alpine. Any other value means the bump already happened or the file moved."
    run: kubectl get cronjob -n monitoring elasticsearch-obs-recovery -o 'jsonpath={.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_exact: "docker.io/library/python:3.12-alpine"
  - id: script-unchanged-since-authoring
    why: "The §1.3 TLS measurement and the §2.3 mock harness were proven against the script at a21e3f8f. A newer script invalidates that evidence — re-run §2.3 and re-review before proceeding."
    run: git log -1 --format=%H -- kubernetes/apps/monitoring/elasticsearch/app/obs-recovery-configmap.yaml
    expect_exact: "a21e3f8f048fd59d29c2fec6c12e82c4c403a443"
  - id: flux-ks-elasticsearch-ready
    why: "The Flux Kustomization that applies the bump must be Ready, or §3.3 cannot tell a stalled reconcile from a bad image."
    run: kubectl get kustomization -n monitoring elasticsearch -o 'jsonpath={.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: es-cluster-green
    why: "Do not hand a RED cluster to the first run of a new interpreter — the destructive rollover+delete path would execute for real on an untested runtime. Wait for green or skip the plan."
    run: kubectl get elasticsearch -n monitoring elasticsearch -o 'jsonpath={.status.health}'
    expect_exact: "green"
  - id: last-scheduled-run-succeeded
    why: "The pre-state must be a WORKING job, else §4 has no baseline. Newest scheduled Job row must be Complete 1/1 (successfulJobsHistoryLimit is 1, so this is also the only success row)."
    run: kubectl get jobs -n monitoring --sort-by=.metadata.creationTimestamp --no-headers | grep -E '^elasticsearch-obs-recovery-[0-9]+ ' | tail -1
    expect_matches: '^elasticsearch-obs-recovery-[0-9]+ +Complete +1/1 '
---

# elasticsearch-obs-recovery: python 3.12-alpine → 3.14.7-alpine

## 1. Summary & why held

### 1.1 What changes
One line in `kubernetes/apps/monitoring/elasticsearch/app/obs-recovery-cronjob.yaml`
(line 34): the image of `cronjob/elasticsearch-obs-recovery` (ns `monitoring`, `*/10`,
`concurrencyPolicy: Forbid`) moves from the float tag `docker.io/library/python:3.12-alpine`
to `docker.io/library/python:3.14.7-alpine@sha256:9e9fde4d…` (digest-pinned, so
`IfNotPresent` can no longer serve a stale node-cached build as it does today).

The job runs `obs_recovery.py` from `configmap/elasticsearch-obs-recovery`. Each run it:
GETs `_cluster/health`; on **RED** it retries allocation, runs `allocation/explain`,
rolls over + DELETEs corrupt allow-listed `.ds-(metrics|logs|traces)-` backing indices, and
**POSTs `ElasticsearchClusterRed` to Alertmanager** (the only RED page this cluster has);
always it checks each TSDB data stream's write-window `end_time` and rolls over an expired
one (the 2026-07-17 / 2026-08-05 ingestion-stall fix). A broken interpreter does not break
ES — it silently removes this self-heal and the RED page. §4 therefore exercises the script,
not pod start.

### 1.2 Why held
Coverage reason: *"G3 could not verify the release notes — an unverified bump needs an
assessed window"*. The notes exist (`docs.python.org/3/whatsnew/3.13.html`,
`…/3.14.html`); this is a two-feature-release jump (3.12 → 3.13 → 3.14), which is why
it needs an assessment rather than a hold-lift. No Renovate PR.

### 1.3 Upstream changes on this script's execution path (assessed 2026-09-25)
- **ssl defaults (3.13) — the one real risk.** What's New 3.13, verbatim:
  > "The `create_default_context()` API now includes `VERIFY_X509_PARTIAL_CHAIN` and
  > `VERIFY_X509_STRICT` in its default flags."
  > "`VERIFY_X509_STRICT` may reject pre-RFC 5280 or malformed certificates that the
  > underlying OpenSSL implementation might otherwise accept."

  The script builds its context with `ssl.create_default_context(cafile=CA)` against the
  ECK self-signed HTTP chain (`secret/elasticsearch-es-http-certs-public` key `tls.crt`,
  mounted as `/certs/ca.crt` = leaf + CA). A strict-mode rejection would surface as an
  **uncaught `urllib.error.URLError`** (the script's `es()` only catches `HTTPError`) →
  Traceback → Job Failed every 10 min.
  **Measured**: the chain is RFC 5280-clean (CA: `basicConstraints` critical CA:TRUE,
  `keyUsage` critical certSign, SKI present; leaf: AKI present, SAN covers
  `elasticsearch-es-http.monitoring.svc`). A TLS handshake with Python 3.14.6
  (`strict=True partial=True`, OpenSSL 3.6.3) through a port-forward, SNI
  `elasticsearch-es-http.monitoring.svc`, returned `HANDSHAKE_OK TLSv1.3`; negative control
  with a wrong hostname returned `HANDSHAKE_FAIL … Hostname mismatch`. The full script also
  ran green under 3.14 against live ES in DRY_RUN (§2.4 reproduces this).
- **Image locale (docker-library, 3.13+).** The 3.14 image no longer sets `ENV LANG=C.UTF-8`
  (3.12-alpine config: `LANG=C.UTF-8`; 3.14.7-alpine config: absent — read from both image
  configs on Docker Hub). The RED/SKIP/EXPIRED log lines contain `—` (U+2014). Python's
  UTF-8 mode auto-enables in the C/POSIX locale (PEP 540), so stdout stays UTF-8; §2.2
  proves it IN THE TARGET IMAGE, because a `UnicodeEncodeError` there would crash the RED
  path *before* `notify_am()` — i.e. lose the page exactly when it matters.
- **Removed modules (PEP 594, 3.13)** — none used. No `urllib.request`/`datetime.fromisoformat`
  behaviour change on the call shapes used (the `…Z` → `+00:00` replace is already explicit).
- **Filesystem/security context**: `readOnlyRootFilesystem`, `runAsUser 1000`; the script is
  run as `python3 /script/obs_recovery.py` (a `__main__` script, no bytecode write) —
  unchanged exposure under 3.14.

Verdict: the hold was procedural (notes unverifiable by G3), the one real behaviour change
is measured-safe. `risk: low`.

## 2. Pre-checks

Run the frontmatter premises (`.venv/bin/python3 runbooks/plan-premises.py elasticsearch-obs-recovery-3.14.7`);
all five must PASS. Then, from the repo root on the Mac mini:

2.1 **Target digest still resolves unchanged** (guards a retag):
```bash
TOK=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -sI -H "Authorization: Bearer $TOK" \
  -H 'Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json' \
  https://registry-1.docker.io/v2/library/python/manifests/3.14.7-alpine | grep -i docker-content-digest
```
PASS: `sha256:9e9fde4d32eedce0b661d9ab91e826b62dddf28e928c230ec55f1866cac66b01`.
FAIL (different/empty): STOP — upstream re-published; re-plan.

2.2 **In-image locale + TLS-lib probe** (the only non-GitOps action in this plan: a throwaway
`--rm` pod, no volumes, no secrets, same uid as the CronJob; ns `monitoring` is PSA
`privileged`):
```bash
kubectl run obs-recovery-py314-probe -n monitoring --rm -i --restart=Never \
  --image=docker.io/library/python:3.14.7-alpine@sha256:9e9fde4d32eedce0b661d9ab91e826b62dddf28e928c230ec55f1866cac66b01 \
  --overrides='{"apiVersion":"v1","spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":1000,"runAsGroup":1000}}}' \
  --command -- python3 -c "import sys,ssl; c=ssl.create_default_context(); print(sys.version.split()[0], sys.stdout.encoding, 'utf8_mode=%d' % sys.flags.utf8_mode, ssl.OPENSSL_VERSION, 'strict=%s' % bool(c.verify_flags & ssl.VERIFY_X509_STRICT)); print('EMDASH_OK — done')"
```
PASS: first line starts `3.14.7 utf-8` (encoding case-insensitive), second line is
`EMDASH_OK — done`. FAIL shape: an ASCII stdout prints
`UnicodeEncodeError: 'ascii' codec can't encode character '—'` and no `EMDASH_OK` line —
STOP, the RED path would crash before paging; re-plan with `PYTHONUTF8=1` in the CronJob env.
(Record the OpenSSL version it prints; §2.4 used Homebrew 3.14.6/OpenSSL 3.6.3 as the
authoring proxy, this line is the in-image fact.)

2.3 **Mock harness: RED path + Alertmanager notify + expired-window rollover under 3.14.**
These paths cannot be forced on the live cluster, so the REAL script bytes from the manifest
are driven against a local mock ES/Alertmanager. Uses the Homebrew 3.14 interpreter
(`/opt/homebrew/opt/python@3.14/bin/python3.14`, 3.14.6 at authoring — same minor as the
target) with no `LANG`/`LC_*` (C locale, like the image), and the repo venv for YAML parsing.
```bash
cd /Users/mu/code/cberg-home-nextgen
W=/private/tmp/claude-501/obs-recovery-3.14.7; mkdir -p "$W"   # FIXED path: agent Bash calls share no shell vars; later blocks re-declare W
kubectl -n monitoring get secret elasticsearch-es-http-certs-public -o 'jsonpath={.data.tls\.crt}' | base64 -d > "$W/es-ca.crt"
cat > "$W/obs_recovery_mock.py" <<'EOF'
#!/usr/bin/env python3
"""Mock ES + Alertmanager harness for obs_recovery.py (plan elasticsearch-obs-recovery-3.14.7).
Drives the REAL script bytes (extracted from the ConfigMap manifest) through the
RED path (reroute, allocation/explain no_valid_shard_copy, rollover-before-delete,
DELETE), the Alertmanager notify, and the expired-TSDB-window rollover. Prints
MOCK_PASS only if every expected mutating call was received, else MOCK_FAIL."""
import json, os, subprocess, sys, threading, yaml
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

PY, MANIFEST = sys.argv[1], sys.argv[2]
script = next(d for d in yaml.safe_load_all(open(MANIFEST)) if d)["data"]["obs_recovery.py"]
seen = []
BAD = ".ds-metrics-generic.otel-default-2026.09.25-000042"
EXPIRED = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, obj, code=200):
        b = json.dumps(obj).encode(); self.send_response(code)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def _body(self):
        n = int(self.headers.get("Content-Length") or 0); return self.rfile.read(n) if n else b""
    def do_GET(self):
        seen.append(("GET", self.path.split("?")[0]))
        p = self.path
        if p.startswith("/_cluster/health"): return self._send({"status": "red", "unassigned_shards": 1})
        if p.startswith("/_cat/shards"): return self._send([{"index": BAD, "shard": "0", "prirep": "p", "state": "UNASSIGNED"},
                                                            {"index": ".kibana_1", "shard": "0", "prirep": "p", "state": "STARTED"}])
        if p.startswith("/_data_stream"): return self._send({"data_streams": [{"name": "metrics-generic.otel-default",
                                                            "indices": [{"index_name": ".ds-old-000041"}, {"index_name": BAD}]}]})
        if "/_settings/index.time_series.end_time" in p:
            idx = p.split("/")[1]; return self._send({idx: {"settings": {"index.time_series.end_time": EXPIRED}}})
        return self._send({}, 404)
    def do_POST(self):
        body = self._body(); seen.append(("POST", self.path.split("?")[0]))
        if self.path.startswith("/_cluster/allocation/explain"):
            return self._send({"unassigned_info": {"reason": "MANUAL_ALLOCATION", "last_allocation_status": "no_valid_shard_copy"},
                               "node_allocation_decisions": []})
        if self.path == "/api/v2/alerts":
            a = json.loads(body)[0]; seen.append(("AM", a["labels"]["alertname"])); return self._send({})
        return self._send({"acknowledged": True})
    def do_DELETE(self):
        seen.append(("DELETE", self.path)); return self._send({"acknowledged": True})

srv = HTTPServer(("127.0.0.1", 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
import tempfile
ca = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False); ca.write(open(os.environ["MOCK_CAFILE"]).read()); ca.close()  # any valid PEM; http URL ignores it
env = {"PATH": "/usr/bin:/bin", "ES_URL": f"http://127.0.0.1:{port}", "ES_CACERT": ca.name,
       "ALERTMANAGER_URL": f"http://127.0.0.1:{port}", "ELASTIC_PASSWORD": "mock", "DRY_RUN": "false"}  # no LANG/LC_*: C locale like the 3.14 image
r = subprocess.run([PY, "-c", script.replace("time.sleep(10)", "time.sleep(0)")], env=env, capture_output=True, text=True, timeout=60)
print(r.stdout, end=""); print(r.stderr, end="", file=sys.stderr)
want = [("POST", "/_cluster/reroute"), ("POST", "/_cluster/allocation/explain"), ("POST", "/metrics-generic.otel-default/_rollover"),
        ("DELETE", "/" + BAD), ("AM", "ElasticsearchClusterRed")]
missing = [w for w in want if w not in seen]
ok = r.returncode == 0 and not missing and "done" in r.stdout and seen.count(("POST", "/metrics-generic.otel-default/_rollover")) >= 2
print("MOCK_PASS" if ok else f"MOCK_FAIL rc={r.returncode} missing={missing}")
sys.exit(0 if ok else 1)
EOF
# positive run
MOCK_CAFILE="$W/es-ca.crt" .venv/bin/python3 "$W/obs_recovery_mock.py" /opt/homebrew/opt/python@3.14/bin/python3.14 \
  kubernetes/apps/monitoring/elasticsearch/app/obs-recovery-configmap.yaml > "$W/mock.out" 2>&1
grep -c '^MOCK_PASS$' "$W/mock.out"          # PASS: 1
grep -ciE 'traceback|unicodeencodeerror' "$W/mock.out"   # PASS: 0
# negative control: same harness, script with the notify call removed -> must FAIL
sed 's/^            notify_am(status, health, summary)$/            pass/' \
  kubernetes/apps/monitoring/elasticsearch/app/obs-recovery-configmap.yaml > "$W/neg-configmap.yaml"
diff kubernetes/apps/monitoring/elasticsearch/app/obs-recovery-configmap.yaml "$W/neg-configmap.yaml"
MOCK_CAFILE="$W/es-ca.crt" .venv/bin/python3 "$W/obs_recovery_mock.py" /opt/homebrew/opt/python@3.14/bin/python3.14 \
  "$W/neg-configmap.yaml" > "$W/neg.out" 2>&1
grep -c "^MOCK_FAIL rc=0 missing=\[('AM', 'ElasticsearchClusterRed')\]$" "$W/neg.out"   # PASS: 1
```
Authoring run 2026-09-25 (verbatim): positive prints the RED sequence
`POST _cluster/reroute?retry_failed` → `… is WRITE index of metrics-generic.otel-default: rollover before delete`
→ `DELETE corrupt obs backing index …` → `notified Alertmanager ElasticsearchClusterRed: HTTP 200`
→ `… write window EXPIRED 5m ago — rolling over …` → `done` → `MOCK_PASS` (identical under
3.12.13). The negative control's `diff` is exactly one line (`253c253`, `notify_am(...)` →
`pass`) and it prints `MOCK_FAIL rc=0 missing=[('AM', 'ElasticsearchClusterRed')]` — the gate
can fail. Read the verdict with `grep` as above, never `$?` after a pipe.

2.4 **Live DRY_RUN rehearsal under 3.14 against the real ES** (read-only: `DRY_RUN=true`
skips every mutating call; Alertmanager is pointed at an unreachable port so a rehearsal can
never page). Keeps the in-cluster hostname for SNI/hostname verification by pinning it to the
port-forward in `getaddrinfo`, so this exercises the strict-X509 path for real.
```bash
cd /Users/mu/code/cberg-home-nextgen
W=/private/tmp/claude-501/obs-recovery-3.14.7
cat > "$W/live_dryrun.py" <<'EOF'
"""Run the REAL obs_recovery.py with DRY_RUN=true against live ES through a port-forward
on 127.0.0.1:19200, keeping the in-cluster hostname for TLS verification (SNI + hostname
check against the ECK cert) by pinning that name to 127.0.0.1 in getaddrinfo."""
import socket, sys, os
script = open(sys.argv[1]).read()
_orig = socket.getaddrinfo
def _gai(host, port, *a, **k):
    if host == "elasticsearch-es-http.monitoring.svc":
        host = "127.0.0.1"
    return _orig(host, port, *a, **k)
socket.getaddrinfo = _gai
os.environ.update(ES_URL="https://elasticsearch-es-http.monitoring.svc:19200", DRY_RUN="true",
                  ALERTMANAGER_URL="http://127.0.0.1:1")  # unreachable on purpose: notify must never fire from a rehearsal
exec(compile(script, "obs_recovery.py", "exec"), {"__name__": "__main__"})
EOF
.venv/bin/python3 -c "import yaml,sys;sys.stdout.write(next(d for d in yaml.safe_load_all(open('kubernetes/apps/monitoring/elasticsearch/app/obs-recovery-configmap.yaml')) if d)['data']['obs_recovery.py'])" > "$W/obs_recovery.py"
kubectl -n monitoring port-forward svc/elasticsearch-es-http 19200:9200 >/dev/null 2>&1 & PF=$!; sleep 3
ELASTIC_PASSWORD="$(kubectl -n monitoring get secret elasticsearch-es-elastic-user -o 'jsonpath={.data.elastic}' | base64 -d)" \
  ES_CACERT="$W/es-ca.crt" env -u LANG -u LC_ALL -u LC_CTYPE \
  /opt/homebrew/opt/python@3.14/bin/python3.14 "$W/live_dryrun.py" "$W/obs_recovery.py" > "$W/live.out" 2>&1
kill $PF 2>/dev/null
cat "$W/live.out"
grep -cE 'cluster status=green unassigned=0 dry_run=True$' "$W/live.out"   # PASS: 1
grep -cE ': write window (healthy|EXPIRED)' "$W/live.out"                  # PASS: = N_TSDB (2.5)
grep -ciE 'traceback|certificate verify failed|cannot reach es' "$W/live.out"  # PASS: 0
```
Authoring run: `cluster status=green unassigned=0 dry_run=True` /
`metrics-generic.otel-default: write window healthy (34m left)` / `done`. FAIL shape for the
strict-X509 risk: `urllib.error.URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] …>`
Traceback (the third grep reads ≥1). The password is only ever in the process env, never printed.

2.5 **Baseline: TSDB write-window count from the last 3.12 run** (the §4.3 contents
comparison):
```bash
W=/private/tmp/claude-501/obs-recovery-3.14.7
J0=$(kubectl get jobs -n monitoring --sort-by=.metadata.creationTimestamp --no-headers -o custom-columns=N:.metadata.name | grep -E '^elasticsearch-obs-recovery-[0-9]+$' | tail -1)
kubectl -n monitoring logs job/$J0 | tee "$W/baseline.log"
N_TSDB=$(grep -cE ': write window (healthy|EXPIRED)' "$W/baseline.log"); echo "N_TSDB=$N_TSDB"; echo "$N_TSDB" > "$W/n_tsdb"
```
PASS: `N_TSDB ≥ 1` (authoring: 1 — `metrics-generic.otel-default`) and it equals the §2.4
count. `N_TSDB=0` means the baseline itself is broken: STOP, investigate before bumping.

## 3. Steps

3.1 Edit the pin (dry-tested on a scratch copy with macOS BSD sed, 2026-09-25):
```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's#image: docker.io/library/python:3.12-alpine$#image: docker.io/library/python:3.14.7-alpine@sha256:9e9fde4d32eedce0b661d9ab91e826b62dddf28e928c230ec55f1866cac66b01#' \
  kubernetes/apps/monitoring/elasticsearch/app/obs-recovery-cronjob.yaml
git diff kubernetes/apps/monitoring/elasticsearch/app/obs-recovery-cronjob.yaml
```
Expected diff (exactly one line, line 34):
```
<               image: docker.io/library/python:3.12-alpine
>               image: docker.io/library/python:3.14.7-alpine@sha256:9e9fde4d32eedce0b661d9ab91e826b62dddf28e928c230ec55f1866cac66b01
```
Do NOT touch `kubernetes/apps/kube-system/crash-ghost-reaper/app/cronjob.yaml` (same image,
separate finding F-cdcbe7ea, separate plan).

3.2 Commit (shared worktree — `--only`, then verify ownership):
```bash
git commit --only kubernetes/apps/monitoring/elasticsearch/app/obs-recovery-cronjob.yaml \
  -m "chore(elasticsearch-obs-recovery): python 3.12-alpine -> 3.14.7-alpine (plan elasticsearch-obs-recovery-3.14.7)"
git log -1 --format=%s     # must be the subject above
git show --stat HEAD       # must list ONLY obs-recovery-cronjob.yaml
git push
T0=$(date -u +%s); echo "T0=$T0"; echo "$T0" > /private/tmp/claude-501/obs-recovery-3.14.7/t0
```

3.3 Wait for Flux (webhook) and confirm the applied spec:
```bash
kubectl get kustomization -n monitoring elasticsearch -o 'jsonpath={.status.lastAppliedRevision}{"\n"}'
kubectl get cronjob -n monitoring elasticsearch-obs-recovery -o 'jsonpath={.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'
```
PASS: revision = the pushed SHA and the image ends in `@sha256:9e9fde4d…6b01`. If not picked up
after 5 min: `flux reconcile kustomization elasticsearch -n monitoring --with-source`
(application-update SOP permits it when the webhook lags). No manual Job is created — the
`*/10` schedule is the test, so the verified run is exactly what production runs.

## 4. Verification

Wait for the first TWO scheduled Jobs created after `T0` (≤ 20 min).

4.1 **The scheduled Job ran the NEW image** (guards: a Job from the old spec, or a node-cached
3.12 build as today):
```bash
kubectl get jobs -n monitoring --sort-by=.metadata.creationTimestamp --no-headers \
  -o 'custom-columns=N:.metadata.name,C:.metadata.creationTimestamp,S:.status.succeeded,F:.status.failed' \
  | grep -E '^elasticsearch-obs-recovery-[0-9]+ ' | tail -3
J1=<name of the first Job whose creationTimestamp is after T0>
kubectl -n monitoring get pods -l job-name=$J1 -o 'jsonpath={.items[0].status.containerStatuses[0].image} {.items[0].status.containerStatuses[0].imageID}{"\n"}'
```
PASS: image contains `3.14.7-alpine` and imageID contains `9e9fde4d` (index digest) — if the
runtime reports the amd64 child digest instead, confirm it matches the amd64 entry of the
index (`curl` the index as in 2.1 with a GET and read `manifests[].digest` for
`architecture: amd64`). FAIL: imageID `…236173eb…` (old build) → redo 3.3.
Note `failedJobsHistoryLimit: 3` keeps failed Jobs visible; `successfulJobsHistoryLimit: 1`
means a later success replaces J1 — read 4.1–4.3 promptly after each run.

4.2 **The script completed, not just the pod** (exit codes lie; read the log):
```bash
W=/private/tmp/claude-501/obs-recovery-3.14.7
kubectl -n monitoring logs job/$J1 | tee "$W/after.log"
grep -cE 'cluster status=(green|yellow|red) unassigned=[0-9]+ dry_run=False$' "$W/after.log"  # PASS: 1
grep -cE ' done$' "$W/after.log"                                                             # PASS: 1
grep -ciE 'traceback|error|cannot reach es|could not list shards' "$W/after.log"             # PASS: 0
```
What the guarded failures print: strict-X509 or TLS-lib regression → `Traceback … URLError …
CERTIFICATE_VERIFY_FAILED` and no `status=` line (Job Failed); ES auth/URL regression →
`cannot reach ES: …` and exit 1; locale regression on a RED/EXPIRED run →
`UnicodeEncodeError`. Each makes one of the three counts wrong.

4.3 **CONTENTS ASSERTION: every TSDB data stream's write window is still inspected** —
measured by the count of `write window (healthy|EXPIRED)` lines in the new-image Job log,
compared to `N_TSDB` from the last 3.12 run (§2.5):
```bash
W=/private/tmp/claude-501/obs-recovery-3.14.7; N_TSDB=$(cat "$W/n_tsdb")
N_AFTER=$(grep -cE ': write window (healthy|EXPIRED)' "$W/after.log"); echo "N_AFTER=$N_AFTER N_TSDB=$N_TSDB"
[ "$N_AFTER" -ge 1 ] && [ "$N_AFTER" -eq "$N_TSDB" ] && echo CONTENTS_PASS || echo CONTENTS_FAIL
```
This is the property that matters: `keep_windows_fresh()` returns silently (`continue`) when it
cannot read `index.time_series.end_time`, so a settings-parsing or response-shape regression
leaves the Job `Complete` with a clean log and ZERO stream checks — the exact silent loss of
the stall-recovery path. `N_AFTER=0` → `CONTENTS_FAIL`. (If `N_TSDB` changed because a new
OTel TSDB stream appeared between runs, cross-check with
`GET _data_stream` via the §2.4 port-forward before judging.) The RED/notify path is covered by
§2.3 (it cannot be forced live); repeat 4.1–4.3 on the SECOND post-T0 Job.

4.4 **Two consecutive clean runs, no failed Job:**
```bash
kubectl get jobs -n monitoring --no-headers -o 'custom-columns=N:.metadata.name,F:.status.failed' | grep -E '^elasticsearch-obs-recovery-[0-9]+ ' | awk '$2!="<none>"'
```
PASS: prints nothing (no Job with a `failed` count) after the second post-T0 run. Can-fail demonstration (review 2026-09-26): `max_over_time(kube_job_status_failed{namespace="monitoring",job_name=~"elasticsearch-obs-recovery-.*"}[30d]) > 0` returned Job `elasticsearch-obs-recovery-29838030` (2026-09-24 20:30Z, reason BackoffLimitExceeded, on 3.12) — this Job family does fail and the count is populated. Because a transient 3.12 failure happened ~36h before authoring (cause unknown), a printed row means: read that Job's log BEFORE blaming the image.

4.5 **Prometheus sees successful runs and ingestion is not stalled:**
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -G http://localhost:19090/api/v1/query --data-urlencode 'query=kube_cronjob_status_last_successful_time{namespace="monitoring",cronjob="elasticsearch-obs-recovery"}' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(r[0]['value'][1] if r else 'EMPTY')"
curl -s -G http://localhost:19090/api/v1/query --data-urlencode 'query=sum(kube_job_status_failed{namespace="monitoring",job_name=~"elasticsearch-obs-recovery-.*"})' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(r[0]['value'][1] if r else 'EMPTY')"
curl -s -G http://localhost:19090/api/v1/query --data-urlencode 'query=ALERTS{alertname=~"EsMetricsIngestionStalled|EsLogIngestionStalled|EsExportQueueStuckFull",alertstate="firing"}' \
  | python3 -c "import sys,json;print(len(json.load(sys.stdin)['data']['result']))"
kill $PF 2>/dev/null
```
PASS: first value `> T0` (`EMPTY` or `< T0` = FAIL — at authoring it read 1790301005, i.e. the
last 3.12 success, which is `< T0` and therefore demonstrably fails before a new-image run);
second `0`; third `0`. (The third read is a CONTEXT GUARD, not an image verdict: the three rules are loaded in group `otel-collector.es-ingestion` with `for: 15m` and their input series exist (review 2026-09-26: 1/1/3), but none fired in 30d, so no non-zero replay exists. The image verdict rests on 4.1–4.3 and the first read here.)

CONTROL: metric kube_cronjob_status_last_successful_time — must advance past T0 after the first new-image run.
CONTROL: metric kube_job_status_failed — sum over elasticsearch-obs-recovery-* Jobs must be 0.
CONTROL: alertname EsMetricsIngestionStalled — not firing.
CONTROL: alertname EsLogIngestionStalled — not firing.
CONTROL: alertname EsExportQueueStuckFull — not firing.

(`ElasticsearchClusterRed` is deliberately not a CONTROL line: it is pushed by this job to
Alertmanager, not defined in any PrometheusRule, so its absence proves nothing about a new
image.)

## 5. Rollback

Stateless CronJob; nothing forward-only happens (in green state the job performs only GETs;
the image change alters no data, index, or secret).
```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-from-3.2>
git log -1 --format=%s && git show --stat HEAD   # only obs-recovery-cronjob.yaml
git push
```
Confirm back: premise `cronjob-still-on-3.12-alpine` PASSes again, then the next scheduled Job
repeats 4.2 + 4.3 green (N_AFTER = N_TSDB). Failed `elasticsearch-obs-recovery-*` Jobs
self-delete after `ttlSecondsAfterFinished: 3600`; leave them for inspection. While rolled
back or broken, the RED self-heal + page is absent: if the window ends with the job not green
on either image, tell the operator explicitly that ES RED currently has **no pager**.

## 6. Interference notes

- **Why `shared: [monitoring]`:** this job is the RED pager and the stall-recovery for the
  shared OTel ES streams that every namespace's logs/metrics/traces ride on. It restarts
  nothing, but a regression removes a safety net for all of them.
- **conflicts_with:** `kube-prometheus-stack-91.4.1` (§4.5 reads Prometheus; RED notify targets
  its Alertmanager), `edot-collector-0.161.0` (§4.5 gates on the ES ingestion-stall alerts),
  `talos-1.14.1` (node reboots bounce the single-node ES into the states this job acts on),
  `flux-reconciler-impersonation` (Flux apply path for §3.3). 2026-09-26 NOW run: KPS (87432c93, chart 91.5.2) restarted Prometheus/Alertmanager/kube-state-metrics ~05:00Z — start this plan only after the KPS plan's verification has closed (run-now `settle_before`). Declared one-sided here; the
  scheduler honours it symmetrically.
- **Same image elsewhere:** `kube-system/crash-ghost-reaper` also runs
  `python:3.12-alpine` (finding F-cdcbe7ea, no plan yet). Deliberately not bundled: different
  namespace, different failure surface, and a combined revert would couple two unrelated
  safety jobs. That plan can reuse §2.2 (image probe) verbatim.
- **Float-tag pinning:** this plan pins by digest; `float-tag-pinning` covers the broader
  float-tag inventory, which does not list `python:3.12-alpine` (only `python:3.11-slim` /
  `python:3.12-slim`), so there is nothing to drop there.
- **Concurrency:** the CronJob is `Forbid`; no manual Job is created, so no overlap risk.
- **Repo correction (for the report):** coverage G3 marks CPython minor bumps "unverified"
  although `docs.python.org/3/whatsnew/<X.Y>.html` is a stable, fetchable source — every
  `library/python` minor bump will be held this way until G3 learns that URL.
