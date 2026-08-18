# SOP: Log-Volume Runaway

> Description: How to attribute a sudden jump in Elasticsearch log ingest to a namespace, pod and single log line; how to tell a mislabelled deprecation stream from a real error stream; how to price it against the 14-day DLM window; and the ordered remediation menu (fix at source → change the probe path → drop at the collector, last resort).
> Version: `2026.08.18`
> Last Updated: `2026-08-18`
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

- Scope: the `logs-generic-default` OTel data stream in the `monitoring`
  namespace; any workload shipping container logs through `edot-collector`.
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
   appear on the Service or the ingress (§10).
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
  the Service and not on the ingress:
  ```bash
  mise exec -- kubectl get svc,ingress -n <ns> <app> -o yaml | grep -nE "port|path:"
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
| `2026.08.18` | 2026-08-18 | Initial SOP, written from the CakePHP probe-storm incident (58% of cluster ingest from one app's health probes). Diagnose Examples are the ~15 queries that characterised it. |
