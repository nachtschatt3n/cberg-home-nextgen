# SOP: Log-Volume Runaway

> Description: How to attribute a sudden jump in Elasticsearch ingest to a namespace, pod and single log line; how to tell a mislabelled deprecation stream from a real error stream; how to price it against the 14-day DLM window; and the ordered remediation menu (fix at source → change the probe path → drop at the collector, last resort). Covers **both** runaway shapes: a LOG-volume runaway (§1–§4) and a METRICS-cardinality runaway (§4b), which is the one currently dominating this cluster's Elasticsearch disk.
> Version: `2026.09.22`
> Last Updated: `2026-09-22`
> Owner: `cberg-agent` / platform operator

---

## 1) Description

A **log-volume runaway** is a single producer emitting log lines fast enough to
dominate the cluster's ingest, storage and error signal. It is not an outage:
the app usually keeps serving perfectly. The damage is (a) ES disk consumed
across the whole retention window, (b) every volume-based audit assertion
drowned, and (c) real errors from every other app buried under the noise.

This SOP exists because the first real instance took ~15 ad-hoc Elasticsearch
queries to characterise from scratch. Section 8 is those queries, so the next
one takes five minutes.

- Scope: **both** OTel data streams in the `monitoring` namespace —
  `logs-generic-default` (§1–§4, any workload shipping container logs through
  `edot-collector`) and `metrics-generic.otel-default` (**§4b**, any workload
  or receiver emitting metrics through it). The two have the same *shape* — one
  producer dominating the bill — but different attribution ladders and
  different remedies, because a metrics runaway is driven by **cardinality**
  (distinct time series), not by line count.
- Prerequisites: `mise exec --` shell in `/Users/mu/code/cberg-home-nextgen`;
  `kubectl` access; the `elasticsearch-es-elastic-user` secret.
- Out of scope: Elasticsearch cluster health / TSDB rollover stalls
  (`docs/sops/monitoring.md` and the OTel-TSDB recovery notes) — a runaway
  *fills* ES, it does not break it.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `monitoring` (ES), producer can be any namespace |
| Data stream | `logs-generic-default` |
| Retention (DLM) | `14d` — verify, do not assume |
| Backing-index roll | ~daily, one `.ds-logs-generic-default-YYYY.MM.DD-NNNNNN` per day |
| Healthy baseline (2026-08-18) | ~3.1–3.5M docs/day, **736–882 MB/day**, ~250 bytes/doc |
| Attribution fields | `resource.attributes.k8s.namespace.name`, `.k8s.pod.name`, `.k8s.container.name` |
| Body field | `body.text` — **wildcards only**; see the trap in §7 |
| Source of truth for probes | `kubernetes/apps/{namespace}/{app}/app/helmrelease.yaml` |
| Audit assertion | `runbooks/health-check.sh` §34, per-namespace floors 40k / 100k / 500k |

**Rule of thumb for pricing:** `bytes/day ≈ lines/day × 250`, and the bill is
`bytes/day × 14`, because DLM keeps every one of those days.

---

## 3) Blueprints

- Probe definitions: `kubernetes/apps/{namespace}/{app}/app/helmrelease.yaml`
  under `controllers.<c>.containers.<c>.probes`.
- Additive nginx probe endpoint (reference implementation):
  `kubernetes/apps/my-software-showcase/ibgastro/app/configmap-nginx-healthz.yaml`
- Audit assertion + calibrated floors: `runbooks/health-check.sh`, Section 34.
- Collector config (last-resort drop filters only):
  `kubernetes/apps/monitoring/edot-collector/`
- Defect-class register: `docs/sops/audit-script-correctness.md`

---

## 4) Operational Instructions

### Step 0 — Open a port-forward and export the credential

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- bash -c '
  # umask 077: this is the elastic SUPERUSER password. Never leave it 0644.
  ( umask 077; kubectl get secret -n monitoring elasticsearch-es-elastic-user \
      -o jsonpath="{.data.elastic}" | base64 -d > /tmp/.espw )
  kubectl port-forward -n monitoring svc/elasticsearch-es-http 9299:9200 >/dev/null 2>&1 &
  echo $! > /tmp/.espf
  sleep 5
'
```

**You are now holding the Elasticsearch superuser password in a file.** Step 7
tears it down; do not end the investigation without running it.

Use a non-default local port (`9299`, not `9200`/`9201`). A leaked port-forward
from a previous sweep holding the default port makes the new one fail silently
and every query return nothing — the "stale process answers" class in
`docs/sops/audit-script-correctness.md`.

### Step 1 — Confirm there IS a runaway, and size it

Compare today's backing index against the previous ones (§8.1). A runaway shows
as a doc count and store size 2×+ the trailing days. If every index is within
±20% of its neighbours, this is not a runaway — stop here.

### Step 2 — Attribute: namespace → pod → app → line

Run §8.2, §8.3, §8.4, §8.5 in order. Do not skip levels: the namespace tells
you the owner, the **pod** tells you whether it is one app or the whole
namespace, and pod-generation names tell you whether the rate is traffic-driven
or machine-driven (§8.5).

### Step 3 — Classify: real error stream, or mislabelled deprecation stream?

This determines whether you have an incident or a hygiene problem. Run §8.6 and
§8.7. See §5 for the decision table. **Do not skip this.** Treating a
deprecation stream as an outage wastes a night; treating a real error stream as
noise loses data.

### Step 4 — Determine the driver: traffic or the kubelet?

Run §8.8 (per-minute histogram) and §8.9 (probe arithmetic). A **machine-flat**
rate that is identical across pod generations and survives out of business
hours is the kubelet, not users. Reconcile it against the probe periods:

```
probes/hour = 3600/readinessPeriod + 3600/livenessPeriod (+ startup while starting)
lines/hour  = probes/hour x lines-per-probe
```

If those two numbers agree to within ~10%, the probes are the driver and the
fix is in §4 Step 6.

### Step 5 — Price it

```
lines/day x ~250 bytes = bytes/day
bytes/day x 14 (DLM)   = total window cost
```
Express it as a share of ES disk (§8.10) and of total ingest (§8.11). A runaway
that costs <1% of disk is a hygiene ticket; one that moves disk by 20 points is
tonight's work.

### Step 6 — Remediate, IN THIS ORDER

The order is not negotiable. Each later option loses more information than the
one before it.

1. **Fix at source (best).** Stop the lines being emitted at all.
   - Wrong log level: a deprecation/notice stream should not be on stderr.
     For PHP: `error_reporting = E_ALL & ~E_STRICT & ~E_DEPRECATED & ~E_NOTICE`
     in the image's php.ini — **keep `E_ERROR`/`E_WARNING`/`E_PARSE`**, that is
     load-bearing, do not silence everything.
   - Double-logging: check whether the runtime AND the web server both log the
     same event (php-fpm `catch_workers_output` + nginx FastCGI `error_log` is
     the classic pair).
   - This needs an image change, so it lands on the next tag. Do it anyway.
2. **Change the probe path (immediate, loses nothing).** If the driver is the
   kubelet, point readiness and startup at a **static** endpoint the web server
   answers itself, and keep the deep framework health route for **liveness
   only**. See §5 for the reference implementation. Typical cut: 75%.
3. **Reduce probe frequency — only alongside 2, never instead of it.** This is
   palliative: it buys a linear reduction and pays in failure-detection
   latency. Never the sole fix.
4. **Drop at the collector (LAST RESORT).** An `edot-collector` filter/transform
   that discards the lines. This **masks rather than fixes**: the app then has
   no way to report a real error on that stream, and the next person to
   investigate it sees a silent app and believes it. Only acceptable when the
   producer is third-party, unpatchable, and the pattern is provably
   information-free. Record it as an accepted risk
   (`runbooks/policy-cli.py risk`).

### Step 7 — Tear down, then re-verify and re-baseline

**Always, before anything else:**

```bash
kill $(cat /tmp/.espf) 2>/dev/null; rm -f /tmp/.espw /tmp/.espf /tmp/esq.py
```

Leaving `/tmp/.espw` behind parks the `elastic` superuser password in cleartext
on the workstation indefinitely. The port-forward left running is the "stale
process answers" trap in §7 for whoever investigates next.

Run §6. Then check whether the *audit assertion* that surfaced this is itself
calibrated against the new baseline — a runaway often reveals that a threshold
was never reachable (see §7, "the assertion could never clear").

---

## 4b) Metrics-cardinality runaway — different stream, different remedy

Everything above attributes **log lines**. It does not work on the metrics
stream, and reaching for it wastes the first hour. A metrics runaway is driven
by **cardinality** — the number of distinct time series — not by verbosity, so
the unit of blame is a *label*, not a log line.

**This is the runaway currently dominating this cluster's Elasticsearch disk.**

### The shape (measured 2026-09-22)

| Signal | Value |
|---|---|
| ES data volume | **64.1 GB used of 83.1 GB — 77%** (`_cat/allocation`) |
| `metrics-generic.otel-default` | **50.68 GiB**, 15 backing indices, **1.48 billion docs** |
| `logs-generic-default` | **13.34 GiB**, 15 backing indices, 54.4 M docs |
| Metrics share of all index bytes | **79%** |
| Top 15 indices by store | **all 15 are `.ds-metrics-generic.otel-default-*`**, ~3.4–4.2 GB each |
| Largest logs backing index | ~1.02 GB — under a quarter of a single metrics day |
| Growth | **+1.47 GiB/day** (`deriv(kubelet_volume_stats_used_bytes[7d])*86400`) |
| Retention (both streams) | DSL `data_retention: 14d`, `effective_retention: 14d` |
| `index_mode` | metrics = **`time_series` (TSDB)**; logs = `standard` |

> **Do not confuse the two 79%/77% numbers.** *Disk* is at 77%; *79%* is the
> metrics stream's share of index bytes. They are different denominators and
> they drift apart — always say which one you mean, and re-measure rather than
> quoting this table, which is a point-in-time snapshot.

Note the docs-per-byte tell: metrics carry ~29 M docs per GiB against ~4 M for
logs. Metrics documents are *tiny and innumerable*. That is the fingerprint of
a cardinality problem, and it is why "find the noisy log line" finds nothing.

### Step M1 — Confirm and size it

Use the §8 Step 0 port-forward and credential, then:

```bash
PW=$(cat /tmp/.espw)
# Is the pressure on disk real?
curl -sk -u "elastic:$PW" "https://localhost:9299/_cat/allocation?v&h=disk.used,disk.avail,disk.total,disk.percent,node"

# Which indices actually hold the bytes? If the top of this list is one
# data stream repeated once per day, you have a stream-level runaway.
curl -sk -u "elastic:$PW" \
  "https://localhost:9299/_cat/indices?v&bytes=b&s=store.size:desc&h=index,docs.count,store.size" | head -20
```

Roll the per-day backing indices up per stream so the comparison is honest
(15 indices of 3 GB each is a very different story from one 45 GB index):

```bash
curl -sk -u "elastic:$PW" "https://localhost:9299/_cat/indices?bytes=b&h=index,docs.count,store.size&format=json" \
 > /tmp/esidx.json
python3 -c "
import json, re, collections
agg = collections.defaultdict(lambda: [0,0,0])
for i in json.load(open('/tmp/esidx.json')):
    m = re.match(r'\.ds-(.+?)-\d{4}\.\d{2}\.\d{2}-\d+\$', i['index'])
    k = m.group(1) if m else i['index']
    agg[k][0] += 1
    agg[k][1] += int(i['docs.count'] or 0)
    agg[k][2] += int(i['store.size'] or 0)
for k, v in sorted(agg.items(), key=lambda x: -x[1][2])[:10]:
    print(f'{v[2]/2**30:8.2f} GiB  idx={v[0]:3d}  docs={v[1]:>14,}  {k}')
"
```

### Step M2 — Attribute: receiver → namespace → service

The logs ladder is namespace → pod → line. The metrics ladder starts one level
higher, at the **receiver**, because the producer is usually a scraper rather
than the app itself. All three aggregations run in one pass:

```bash
curl -sk -u "elastic:$PW" "https://localhost:9299/metrics-generic.otel-default/_search?size=0" \
  -H 'Content-Type: application/json' -d '{
   "aggs":{
     "by_scope":{"terms":{"field":"scope.name","size":15}},
     "by_ns":{"terms":{"field":"resource.attributes.k8s.namespace.name","size":15}},
     "by_svc":{"terms":{"field":"resource.attributes.service.name","size":15}}
   }}' | python3 -c "
import sys, json
d = json.load(sys.stdin)
for a in ('by_scope','by_ns','by_svc'):
    print('---', a)
    for b in d['aggregations'][a]['buckets']:
        print(f\"  {b['doc_count']:>14,}  {b['key']}\")
"
```

Measured 2026-09-22 — this is what a localised runaway looks like:

| Dimension | Top buckets (doc count) |
|---|---|
| `scope.name` (receiver) | `prometheusreceiver` **486.6 M**, `kubeletstatsreceiver` 370.9 M, `k8sclusterreceiver` 340.4 M, `hostmetrics/disk` 151.7 M, `hostmetrics/cpu` 107.7 M |
| `k8s.namespace.name` | `monitoring` 476.2 M, **`network` 408.0 M**, `kube-system` 135.6 M |
| `service.name` | **`envoy` 360.5 M** — the single largest producer — then `node-exporter` 116.8 M |

That reads as: the **Envoy Gateway proxies in namespace `network`, scraped by
the Prometheus receiver**, are the dominant source. One `service.name` bucket
holding ~24% of 1.48 billion documents *is* the finding.

### Step M3 — Separate the TWO multipliers (do not skip this)

A metrics step change almost always has two independent causes multiplied
together, and fixing the wrong one achieves nothing:

1. **Replica count** — more pods emitting the same series set.
2. **Per-pod emission** — each pod emitting more series than it used to.

Finding `F-4221190f` records the reference case: `envoy-internal` went
**1 → 3 replicas** *and* **703 k → 6.0 M points/pod/day** in the same window.
Scaling back the replicas would have cut a third of a problem whose real driver
was a ~8.5× rise in per-pod emission. **Always divide by the pod count** before
concluding anything:

```bash
# points/pod/day — the number that actually moved
curl -sk -u "elastic:$PW" "https://localhost:9299/metrics-generic.otel-default/_search?size=0" \
  -H 'Content-Type: application/json' -d '{
   "query":{"bool":{"filter":[
     {"term":{"resource.attributes.service.name":"<service>"}},
     {"range":{"@timestamp":{"gte":"now-1d"}}}]}},
   "aggs":{"pods":{"terms":{"field":"resource.attributes.k8s.pod.name","size":20}}}}' \
  | python3 -c "
import sys, json
for b in json.load(sys.stdin)['aggregations']['pods']['buckets']:
    print(f\"  {b['doc_count']:>12,}  {b['key']}\")
"
```

Compare the **per-pod** figures across pod generations. Flat per-pod with more
pods = a scaling event (usually legitimate). Rising per-pod = a cardinality
regression, which is the real defect.

### Step M4 — Find the unbounded label

This stream is **TSDB** (`index_mode: time_series`), so every distinct
combination of *dimension* fields is a separate time series. The index settings
name the dimensions explicitly:

```bash
curl -sk -u "elastic:$PW" \
  "https://localhost:9299/.ds-metrics-generic.otel-default-<YYYY.MM.DD>-<NNNNNN>/_settings?filter_path=**.routing_path"
```

**The trap: a label with no ceiling.** A histogram labelled by user agent,
request path, response-code-with-detail, or any caller-supplied string has
*unbounded* cardinality — it grows with traffic diversity forever, and no
retention setting bounds it. A single such label on a histogram (which is
already many series per label set, one per bucket) is the classic way a stream
triples in a week. Check any suspicious metric's label set for a field whose
distinct-value count is not obviously finite:

```bash
curl -sk -u "elastic:$PW" "https://localhost:9299/metrics-generic.otel-default/_search?size=0" \
  -H 'Content-Type: application/json' -d '{
   "aggs":{"c":{"cardinality":{"field":"<attributes.suspect_label>"}}}}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['aggregations']['c'])"
```

### Step M5 — Price it

Same arithmetic as §4 Step 5, different inputs: the bill is
`bytes/day × 14`, because DSL keeps every one of those days. At the measured
~3.6 GiB/day for this stream, **each day of retention costs ~3.6 GiB**, and the
stream's steady-state footprint is ~50 GiB.

> **Check `prefer_ilm` before blaming retention.** On 2026-05-29 both OTel
> streams carried `index.lifecycle.prefer_ilm: true` under the Elastic built-in
> `logs`/`metrics` ILM policies, which have **no delete phase** — so the DSL
> `data_retention` was silently ignored and indices accumulated for ~48 days.
> If the index count exceeds the retention window in days, that is the cause,
> not cardinality. See `docs/sops/longhorn.md` and
> `kubernetes/apps/monitoring/elasticsearch/app/otel-ilm-job.yaml`.

### Step M6 — Remediate, IN THIS ORDER

The order matters for the same reason as §4 Step 6: each later option destroys
more information than the one before it.

1. **Reduce what is emitted, at the source (best).** Drop the unbounded label,
   or stop emitting the offending histogram. For the Envoy case this means the
   proxy's telemetry/stats configuration — **verify the exact key against the
   `EnvoyProxy` CRD in use before changing it**; do not copy a stats-matcher
   snippet from upstream docs unverified. This is the only option that fixes
   cardinality rather than hiding it.
2. **Filter/transform at the collector.** An `edot-collector` processor that
   drops the metric or strips the high-cardinality attribute
   (`kubernetes/apps/monitoring/edot-collector/`). Cheaper to land than a
   source change and fully reversible — but it makes the signal invisible
   without making the producer correct, so record it with
   `runbooks/policy-cli.py risk` and state what is now unobservable.
3. **Cut retention — LAST, and it is not a fix.** Lowering the 14 d DSL window
   shrinks the disk immediately and proportionally, which makes it seductive
   during a disk alert. It destroys historical comparison — including the
   ability to prove whether the cardinality change is still getting worse — and
   the stream resumes growing at the same rate the next day. Use it only to buy
   time for option 1, and say so explicitly when you do.

**Never "fix" this by deleting backing indices by hand.** On a TSDB stream the
backing indices are time-bounded and managed by DSL; deleting them out from
under the lifecycle leaves gaps that look like ingestion failure to every later
investigation.

### Detector gap — there is still no alert on this

**Nothing alerts on metrics-stream growth.** The 2026-09-06 step change was
found *by hand* on 2026-09-13, a week later, and only because someone looked at
disk. The logs side has `health-check.sh` §34; the metrics side has no
equivalent assertion and no Prometheus rule. Until one exists, this section is
reached only by a human noticing ES disk — treat that as a known blind spot
rather than assuming silence means health. Tracked as `F-4221190f`.

> When adding such a rule, pair it with an `absent()` guard: a rule matching no
> series sits at `state=inactive` forever and reports nothing, which is
> indistinguishable from "healthy" on a dashboard.

---

## 5) Examples

### 5.1 Decision table: deprecation stream vs. real error stream

| Signal | Deprecation / mislabelled | Real error stream |
|---|---|---|
| Rate shape | machine-flat, identical across pod generations | bursty, correlates with traffic or an event |
| Text | `Strict Standards`, `Deprecated`, `Notice`, `WARNING: ... said into stderr` | `Fatal error`, `Exception`, `500`, stack traces |
| `Fatal`-class count | zero | non-zero |
| Why it scored as an error | substring `error` inside an identifier — `handleError`, `icon_fatalerror.gif`, `fatal_neterrors=` | the word `error` is the log level |
| HTTP status of the request that produced it | 200 | 5xx |
| App behaviour | perfect | degraded |
| Correct response | hygiene: fix the log level, cut the driver | incident |

### 5.2 Reference incident (2026-08-18) — the numbers

`my-software-showcase/ibgastro`, a legacy CakePHP 1.x app on php-fpm + nginx.

| Measure | Value |
|---|---|
| Namespace share of all cluster log ingest | **4,759,211 / 8,166,265 docs = 58.3%** |
| The one app | 4,402,206 docs/24h = **183,425/hour** |
| Share of the cluster "error" metric | 4,320,202 / 4,370,396 = **98.8%** |
| `PHP Fatal error` in the same window | **0** |
| Lines per single probe | ~382 |
| Probes/hour (readiness 10s + liveness 30s + startup 5s) | ~480 |
| Backing index, storm day vs baseline | 7,394,370 docs / **1,334 MB** vs ~3.2M / ~800 MB |
| DLM window cost | ~1.1 GB/day x 14d ≈ **15 GB** |
| ES disk | 37.5 / 83.1 GB = 45%, heading for ~63% |

Mechanism: `/health` was a **CakePHP route**, not a file. php-fpm boots the
whole framework per request; CakePHP 1.x calls a long list of methods
statically, which modern PHP flags as `E_STRICT`/`E_DEPRECATED`, so one boot
emitted ~370 `PHP Strict Standards:` notices — each double-logged by php-fpm's
`catch_workers_output` and nginx's FastCGI `error_log`. Onset was the commit
that *enabled* the probes and moved them off `/`. Nothing was broken; the
health check was the incident.

### 5.3 Reference fix: split the probes

Additive nginx server block, mounted by `subPath` so it does **not** shadow the
image's own `conf.d/default.conf`:

```nginx
server {
    listen 8080;
    listen [::]:8080;
    server_name _;
    access_log off;                 # the whole point: probes emit nothing

    location = /healthz {
        add_header Content-Type text/plain always;
        return 200 "ok\n";
    }
    location / { return 404; }      # probe-only port, not in the Service
}
```

```yaml
probes:
  liveness:   # framework route: DB + TMP writability, returns a real 503
    spec: { httpGet: { path: /health,  port: 80   }, periodSeconds: 30 }
  readiness:  # static, never reaches the app runtime
    spec: { httpGet: { path: /healthz, port: 8080 }, periodSeconds: 10 }
  startup:
    spec: { httpGet: { path: /healthz, port: 8080 }, periodSeconds: 5  }
```

**Validate the snippet before committing** — a bad nginx config takes the app
down on the next roll:

```bash
mise exec -- kubectl exec -n <ns> <pod> -c app -- sh -c '
  T=/var/www/html/app/tmp   # any writable emptyDir
  printf "events { worker_connections 64; }\nhttp { include $T/snippet.conf; }\n" > $T/v.conf
  nginx -t -c $T/v.conf; rm -f $T/v.conf'
```

`nginx -t` only parses; it does not reload, so this touches nothing live.

**Accepted trade-off to state explicitly in the commit:** readiness no longer
proves the app runtime is alive, so a dead runtime stays in the Service for up
to one liveness window. With a single replica there is no healthy peer to shift
to, so that window is identical either way. With multiple replicas, weigh it.

---

## 6) Verification Tests

0. **Tear down first** (Step 7) — then verify. A verification run that reuses a
   stale port-forward is not a verification.
1. **The producer went quiet.** Per-minute histogram for the NEW pod (§8.12),
   over a window that starts at least 2 minutes after the pod became Ready —
   the first boots are startup noise and will mislead you.
   - Expect: `lines/hour ≈ liveness probes/hour × lines-per-probe` after a
     probe-path fix, and ≈0 after a fix at source.
2. **The 7-day per-day histogram** (§8.13) shows the namespace returning to its
   pre-incident level.
3. **The whole-stream 24h error count** (§8.6) returns to the measured
   non-storm baseline (~44k at the time of writing). Note this takes a full 24h
   to fall, because the window is trailing — do not call it failed at T+10min.
4. **The app is still healthy**: pod `1/1 Running`, `RESTARTS 0`, and the deep
   liveness endpoint still returns 200:
   ```bash
   mise exec -- kubectl exec -n <ns> <pod> -c app -- wget -qO- http://127.0.0.1:8080/healthz
   mise exec -- kubectl get pods -n <ns> -l app.kubernetes.io/name=<app>
   ```
5. **The probe-only port is not reachable from outside**: `/healthz` must not
   appear on the Service or the app's HTTPRoute (§10).
6. **Backing-index size** for the next full day is back in the 736–882 MB band
   (§8.1). This is the only test that proves the storage bill is actually gone.

---

## 7) Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Every ES query returns 0 hits | `match` on `body.text` is exact-equality against a keyword field | use `wildcard` with `case_insensitive: true` — **always** |
| `severity_text` / `severity_number` filter matches nothing | both are dead in this pipeline (28 of 3.49M docs, all INFO); the receiver does not parse levels | filter on `body.text`, not severity |
| Port-forward "works" but returns nothing | a leaked port-forward from an earlier run owns the port | use a unique local port; `lsof -i :9200` |
| The count did not drop after the fix | you are reading a trailing 24h window | measure the new pod over a fresh short window (§8.12) first |
| Rate fell but not to zero | you fixed the driver, not the source | liveness still boots the framework — land the source fix (§4 Step 6.1) |
| A namespace shows huge volume but no app owns it | log lines are attributed to a DaemonSet (`otel-operator-daemon`) or an init/schema Job | aggregate by pod, then by container |
| The audit assertion that found this could never have been green | threshold set without measuring the baseline | re-calibrate against the measured window and record the row in `docs/sops/audit-script-correctness.md` |
| Fix "landed" but the numbers did not move | the manifest edit hit an anchor mismatch, or Flux has not reconciled | `git show --stat HEAD`, `flux get kustomizations -A`, and check the pod hash changed |

---

## 8) Diagnose Examples

Set up once (Step 0), then use this helper — **Python, not `jq`**; jq's
shell-escaping rules bite every time:

```bash
cat > /tmp/esq.py <<'PY'
import json, urllib3, requests
urllib3.disable_warnings()
PW = open('/tmp/.espw').read().strip()
def q(body, path="/logs-generic-default/_search"):
    r = requests.get("https://localhost:9299" + path, auth=("elastic", PW),
                     verify=False, headers={"Content-Type": "application/json"},
                     data=json.dumps(body), timeout=60)
    return r.json()
def cat(path):
    return requests.get("https://localhost:9299" + path, auth=("elastic", PW),
                        verify=False, timeout=60).text
PY
```

Common fragments used below:

```python
NS   = lambda n: {'term': {'resource.attributes.k8s.namespace.name': n}}
LAST = lambda w: {'range': {'@timestamp': {'gte': w}}}
ERRQ = {'bool': {
    'should': [{'wildcard': {'body.text': {'value': '*error*', 'case_insensitive': True}}},
               {'wildcard': {'body.text': {'value': '*fatal*', 'case_insensitive': True}}}],
    'minimum_should_match': 1,
    'must_not': [{'wildcard': {'body.text': {'value': '*noerror*', 'case_insensitive': True}}}],
    'filter': [{'range': {'@timestamp': {'gte': 'now-24h'}}}]}}
```

**8.1 — Is there a runaway? Per-day backing index size (docs AND megabytes).**
The single most informative query. Storage, not doc count, is the bill.
```python
print(cat('/_cat/indices/.ds-logs-generic-default*'
          '?h=index,docs.count,store.size&s=creation.date&bytes=mb'))
```

**8.2 — Total ingest by namespace, 24h.** Who owns the volume.
```python
q({'size': 0, 'track_total_hits': True,
   'query': {'bool': {'filter': [LAST('now-24h')]}},
   'aggs': {'ns': {'terms': {'field': 'resource.attributes.k8s.namespace.name', 'size': 25}}}})
```

**8.3 — Same, by pod, inside the loud namespace.** Separates one app from many.
```python
q({'size': 0, 'track_total_hits': True,
   'query': {'bool': {'filter': [NS('<ns>'), LAST('now-24h')]}},
   'aggs': {'p': {'terms': {'field': 'resource.attributes.k8s.pod.name', 'size': 200}}}})
```

**8.4 — Roll pod names up to apps.** Pods churn; apps are what you fix.
```python
import re, collections
agg = collections.Counter()
for b in r['aggregations']['p']['buckets']:
    agg[re.sub(r'-[a-z0-9]{6,10}-[a-z0-9]{5}$', '', b['key'])] += b['doc_count']
for k, v in agg.most_common():
    print('%-30s %9d  %7d/h' % (k, v, v / 24))
```

**8.5 — Is the rate machine-driven?** If several pod GENERATIONS of the same app
each show the same per-hour rate, no human is causing it. Divide each pod's
count by its lifetime rather than by 24h.

**8.6 — The cluster-wide "error" count, exactly as the audit computes it.**
Reproduce the assertion before you trust it.
```python
q({'size': 0, 'track_total_hits': True, 'query': ERRQ,
   'aggs': {'ns': {'terms': {'field': 'resource.attributes.k8s.namespace.name', 'size': 25}}}})
```

**8.7 — Is it actually errors? Count the fatal-class separately.** A stream with
millions of "errors" and zero fatals is a mislabelled stream.
```python
for pat in ['*Fatal error*', '*Strict Standards*', '*Deprecated*', '*Exception*']:
    r = q({'size': 0, 'track_total_hits': True, 'query': {'bool': {'filter': [
        NS('<ns>'), LAST('now-24h'),
        {'wildcard': {'body.text': {'value': pat, 'case_insensitive': True}}}]}}})
    print(pat, r['hits']['total']['value'])
```

**8.8 — Per-minute histogram for one pod.** Flat = machine. Spiky = traffic.
```python
q({'size': 0, 'query': {'bool': {'filter': [NS('<ns>'),
      {'term': {'resource.attributes.k8s.pod.name': '<pod>'}}, LAST('now-60m')]}},
   'aggs': {'m': {'date_histogram': {'field': '@timestamp', 'fixed_interval': '60s'}}}})
```

**8.9 — Read the actual lines, newest first.** Ten lines usually ends the
investigation. Look for the requesting user-agent: `kube-probe/1.xx` names the
kubelet as the caller outright.
```python
r = q({'size': 10, 'sort': [{'@timestamp': 'desc'}], '_source': ['body.text'],
       'query': {'bool': {'filter': [NS('<ns>'),
          {'term': {'resource.attributes.k8s.pod.name': '<pod>'}}, LAST('now-30m')]}}})
for h in r['hits']['hits']:
    print(str(h['_source']['body']['text'])[:180])
```

**8.10 — ES disk headroom.** Turns lines into a decision.
```python
print(cat('/_cat/allocation?h=disk.used,disk.avail,disk.total,disk.percent'))
```

**8.11 — Confirm the retention window before pricing it.** Never assume 14d.
```python
d = q({}, '/_data_stream/logs-generic-default')['data_streams'][0]
print(d['lifecycle'])   # -> {'enabled': True, 'data_retention': '14d', ...}
```

**8.12 — Post-fix verification on the NEW pod only.** Start the window at least
2 minutes after Ready; the first framework boots are startup noise.
```python
for w in ['now-2m', 'now-5m', 'now-15m']:
    r = q({'size': 0, 'track_total_hits': True, 'query': {'bool': {'filter': [
        NS('<ns>'), {'term': {'resource.attributes.k8s.pod.name': '<new-pod>'}}, LAST(w)]}}})
    print(w, r['hits']['total']['value'])
```
Also check ingest lag before believing a zero — compare the newest document's
timestamp against wall clock (`date -u`).

**8.13 — 7-day per-day histogram, with and without the suspect namespace.**
This is the query that proves onset and that establishes the true baseline for
re-calibrating the audit threshold.
```python
def daily(extra_must_not):
    body = json.loads(json.dumps(ERRQ))
    body['bool']['must_not'] += extra_must_not
    body['bool']['filter'] = [LAST('now-7d')]
    return q({'size': 0, 'query': body,
              'aggs': {'d': {'date_histogram': {'field': '@timestamp',
                                                'calendar_interval': 'day'}}}})
for label, mn in [('ALL', []), ('EXCL-suspect', [NS('<ns>')])]:
    print('==', label)
    for b in daily(mn)['aggregations']['d']['buckets']:
        print(' ', b['key_as_string'][:10], b['doc_count'])
```

**8.14 — Correlate onset with a commit.** The histogram gives you a day; git
gives you the cause.
```bash
git log --since="<onset date>" --until="<onset date + 1 day>" --oneline -- kubernetes/apps/<ns>/
```

**8.15 — Read the probe definition and do the arithmetic.**
```bash
grep -n -A4 "readiness:\|liveness:\|startup:" \
  kubernetes/apps/<ns>/<app>/app/helmrelease.yaml | grep -E "path:|port:|periodSeconds:"
```
Then: `probes/hour = 3600/readiness + 3600/liveness`, and
`lines-per-probe = observed lines/hour ÷ probes/hour`. If lines-per-probe is in
the hundreds, the probe is booting a framework.

**8.16 — Is `/health` a route or a file?** The whole distinction.
```bash
mise exec -- kubectl exec -n <ns> <pod> -c app -- sh -c 'ls -la <webroot>'
mise exec -- kubectl exec -n <ns> <pod> -c app -- sh -c 'cat /etc/nginx/conf.d/default.conf'
```
No `health` file in the webroot, plus a catch-all `try_files ... /index.php`,
means every probe is a full application request.

---

## 9) Health Check

```bash
mise exec -- ./runbooks/health-check.sh
```

Section 34 owns this assertion. Since 2026-08-18 it is **per-namespace
relative**, so one chatty app cannot own the cluster verdict:

| Per-namespace matches / 24h | Verdict |
|---|---|
| ≥ 500,000 | CRITICAL — log-volume runaway |
| ≥ 100,000 | MAJOR |
| ≥ 40,000 and ≥ 40% of the cluster total | MAJOR — concentration |
| ≥ 40,000 | MINOR |
| below | silent |

The cluster-wide total is **display-only**, with a single broad backstop at
≥ 1,000,000 that fires only when no individual namespace already explains it.
Floors were calibrated against the measured window in §5.2; re-measure before
changing them, and record any change in the SOP's version history.

Post-change, also run `health-check-agent`, `security-agent` and `doc-agent`.

---

## 10) Security Check

- **A probe-only port must stay probe-only.** Confirm the new port is not on
  the Service and not on the HTTPRoute (ingress-nginx was deleted 2026-09-07,
  `ad1ea7c2`, so `get ingress` returns nothing for every app and cannot fail):
  ```bash
  mise exec -- kubectl get svc,httproute -n <ns> <app> -o yaml | grep -nE "port|path:"
  ```
  The reference implementation returns `404` for every path except `/healthz`
  and never serves application content.
- **A health endpoint must not leak.** `return 200 "ok\n"` is the whole body.
  Never expose version strings, hostnames, DB names or stack details on an
  unauthenticated endpoint.
- **Never silence all PHP diagnostics.** `error_reporting = 0` or
  `display_errors`-only fixes destroy the ability to see a real fault. Drop
  `E_STRICT`/`E_DEPRECATED`/`E_NOTICE`, keep `E_ERROR`/`E_WARNING`/`E_PARSE`.
- **A collector drop filter is a monitoring-coverage reduction.** If you take
  option 4, record it with `runbooks/policy-cli.py risk` and state what signal
  is now invisible.
- **Redaction.** Log samples pasted into findings or commits must not carry
  internal domains, public IPs, credentials or personal data. Quote the message
  shape, not a full request line.
- **The credential file is gone.** This procedure writes the Elasticsearch
  superuser password to `/tmp/.espw`. Confirm teardown ran:
  ```bash
  ls -l /tmp/.espw 2>/dev/null && echo "STILL PRESENT - rm it now" || echo "clean"
  ```
  Create it under `umask 077` and delete it in Step 7. It must never outlive the
  investigation, and it must never be written inside the repo tree.
- **Private-repo detail.** If the fix lives in a private image repo, keep
  branch names, commit SHAs and CI script names out of plans committed here.
  Reference the PR by URL and describe the root cause in terms of upstream,
  publicly-documented framework behaviour.

---

## 11) Rollback Plan

Every remediation in §4 Step 6 is a plain GitOps change:

```bash
git revert <sha> && git push
```

Then confirm Flux rolled the pod back and the app is Ready:

```bash
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- kubectl get pods -n <ns> -l app.kubernetes.io/name=<app>
```

Reverting restores the noisy-but-working state — the pre-fix condition was
never an outage, so a rollback is always safe. Never `git reset --hard` or
force-push.

If a bad nginx snippet takes the app down before you can revert, the
HelmRelease's `upgrade.remediation.strategy: rollback` handles it
automatically; `strategy: Recreate` means there is a brief gap either way.

---

## 12) References

- `docs/sops/monitoring.md` — Prometheus / ES / Grafana access patterns
- `docs/sops/audit-script-correctness.md` — the defect-class register; three
  rows relate to this incident
- `docs/sops/new-deployment-blueprint.md` — probe conventions for new apps
- `runbooks/health-check.sh` §34 — the calibrated assertion
- `kubernetes/apps/my-software-showcase/ibgastro/app/configmap-nginx-healthz.yaml`
  — reference implementation of a silent probe endpoint

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| `2026.09.22` | 2026-09-22 | **Scope widened to metrics.** The SOP covered only `logs-generic-default`, so the runaway actually consuming the ES filesystem — a *metrics-cardinality* runaway — had no procedure, and every §8 query hardcoded the logs stream. Added **§4b** with the measured 2026-09-22 state (metrics = 50.68 GiB / 79% of index bytes vs logs 13.34 GiB; top 15 indices all `.ds-metrics-generic.otel-default-*`; disk 77%; +1.47 GiB/day), the receiver → namespace → service attribution ladder (localising it to Envoy Gateway in `network` via the Prometheus receiver), the two-multiplier rule (replica count vs per-pod emission), the unbounded-label/TSDB cardinality trap, the `prefer_ilm` retention caveat, the remediation order (source → collector → retention last) and the standing detector gap. Updated the §1 scope and description accordingly. |
| `2026.08.18` | 2026-08-18 | Initial SOP, written from the CakePHP probe-storm incident (58% of cluster ingest from one app's health probes). Diagnose Examples are the ~15 queries that characterised it. |
