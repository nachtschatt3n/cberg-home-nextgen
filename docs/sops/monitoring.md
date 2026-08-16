# SOP: Monitoring & Observability

> Standard Operating Procedures for the cluster monitoring stack.
> Stack: Prometheus + Alertmanager + Grafana + ELK (Elasticsearch + Kibana + edot-collector).
> Description: Operating, validating, and troubleshooting metrics/logging/alerting components.
> Version: `2026.08.16`
> Last Updated: `2026-08-16`
> Owner: `Platform`

---

## Description

This SOP defines how to operate and validate the monitoring stack, including Prometheus scraping,
alerts, dashboards, and log pipeline health.

---

## Overview

| Component | Purpose | Namespace |
|-----------|---------|-----------|
| kube-prometheus-stack | Metrics, alerting, Prometheus rules | monitoring |
| Grafana | Dashboards and visualization | monitoring |
| Alertmanager | Alert routing and notifications | monitoring |
| Elasticsearch | Log storage (via ECK) | monitoring |
| Kibana | Log analytics UI | monitoring |
| edot-collector | Log collection and forwarding (EDOT) | monitoring |
| OTel Operator | OpenTelemetry operator for collector management | monitoring |
| Uptime Kuma | Service uptime monitoring | monitoring |
| Headlamp | Kubernetes web UI | monitoring |
| Unpoller | UniFi metrics exporter | monitoring |
| ECK Operator | Elastic Cloud on Kubernetes | monitoring |
| prometheus-blackbox-exporter | Synthetic DNS + HTTPS probes (`probe_success`) — the DNS/ingress SLI | monitoring |

---

## Blueprints

N/A for dedicated Authentik-style blueprints.

Source-of-truth manifests:
- `kubernetes/apps/monitoring/`
- Related dashboards/config in Grafana and alerting rules under the same path.

### External (macOS) Scrape Targets

Three macOS menu bar apps on the Mac Mini (`192.168.30.111`) expose Prometheus metrics.
Scraped via `ScrapeConfig` CRDs (not `additionalScrapeConfigs`):

| App | Port | Metrics path | ScrapeConfig |
|-----|------|-------------|--------------|
| findmy-traccar-sync | 9101 | `/metrics` | `macos-scrapeconfigs.yaml` |
| bank-refresh | 9100 | `/metrics` | `macos-scrapeconfigs.yaml` |
| arag-scrape | 9102 | `/metrics` | `macos-scrapeconfigs.yaml` |

Alert rules: `macos-apps-alerts.yaml` (FindMyTraccarSyncDown, BankRefreshDown,
AragScrapeDown/Stale/Failing/EmulatorDown, etc.)

> Note: prometheus-operator sets the `job` label on `ScrapeConfig` targets to
> `scrapeConfig/<namespace>/<name>` (e.g. `scrapeConfig/monitoring/arag-scrape`),
> not the bare app name. `up{job="<app>"}`-style exprs will not match; use the
> full operator-generated label. `AragScrapeDown` uses the correct form; the
> older FindMyTraccarSyncDown / BankRefreshDown `up{job="..."}` exprs are known
> to be latent no-ops (metric-based rules still work).

The arag-scrape app also ships OTLP/HTTP JSON logs (`service.name=arag-scrape`)
to the edot-collector via the internal ingress `otlp.${SECRET_DOMAIN}` (backend
`edot-collector:4318`); logs land in `logs-generic-default`.

Source: `kubernetes/apps/monitoring/kube-prometheus-stack/app/macos-scrapeconfigs.yaml`

---

## Operational Instructions

1. Validate component pod health in `monitoring`.
2. Check Prometheus targets and active alerts.
3. Validate Grafana dashboards and log ingestion path (edot-collector -> Elasticsearch -> Kibana).
4. Investigate and resolve warnings/events before closing.

---

## Examples

### Example 1: Check Prometheus Target Health

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s 'http://localhost:9090/api/v1/targets' | python3 -c \
  "import sys,json; t=json.load(sys.stdin)['data']['activeTargets']; print('total',len(t),'up',sum(1 for i in t if i['health']=='up'))"
```

### Example 2: Check Recent Warning Events

```bash
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -30
```

---

## Verification Tests

### Test 1: Core Monitoring Components Ready

```bash
kubectl get pods -n monitoring
```

Expected:
- Core components are Running/Ready (allow completed Jobs).

If failed:
- Inspect failing pod events/logs.

### Test 2: Prometheus and Elasticsearch Health

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s 'http://localhost:9090/api/v1/targets'
kubectl port-forward -n monitoring svc/elasticsearch-es-http 9200:9200 &
```

Expected:
- Prometheus API responds and Elasticsearch endpoint is reachable.

If failed:
- Validate service/pod readiness and network access.

---

## Prometheus

### Access

```bash
# Port-forward to Prometheus UI
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
# Open http://localhost:9090

# Use alternative port to avoid conflicts
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9091:9090 &

# Kill port-forwards when done
pkill -f "kubectl port-forward"
```

### Common Queries

```bash
# Check firing alerts (via API)
curl -s 'http://localhost:9090/api/v1/alerts' \
  | grep -o '"alertname":"[^"]*"' | sort -u

# Get alerts excluding Watchdog/InfoInhibitor
curl -s 'http://localhost:9090/api/v1/alerts' \
  | python3 -c "
import sys, json
alerts = json.load(sys.stdin)['data']['alerts']
for a in alerts:
    if a['state'] == 'firing' and a['labels']['alertname'] not in ['Watchdog','InfoInhibitor']:
        print(a['labels']['alertname'], a['labels'].get('namespace',''))
"

# Check scrape target health
curl -s 'http://localhost:9090/api/v1/targets' | python3 -c "
import sys, json
targets = json.load(sys.stdin)['data']['activeTargets']
total = len(targets)
up = sum(1 for t in targets if t['health'] == 'up')
print(f'Total: {total}, Up: {up}, Down: {total - up}')
"

# Node resource usage
kubectl top nodes
kubectl top pods -n {namespace}
```

### Key Metrics

```
# Node metrics
node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes
node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}
node_cpu_seconds_total

# Kubernetes
kube_pod_status_phase
kube_deployment_status_replicas_unavailable
kube_persistentvolumeclaim_status_phase

# Longhorn
longhorn_volume_actual_size_bytes
longhorn_volume_state
```

---

## ES Rejected Documents (edot-collector silent telemetry loss)

The edot-collector can look perfectly healthy (Ready, 0 restarts, ingestion
volume normal) while Elasticsearch **rejects** part of what it sends — the
docs/points are silently lost and only the collector's own logs show it.
`runbooks/health-check.sh` asserts on this hourly rate since 2026-08-07; since
2026-08-15 the metrics class counts dropped **points**, not log lines (see below).

Two rejection classes (both in `kubectl logs -n monitoring deploy/edot-collector`):

1. **`document_parsing_exception` / `failed to index document`** — the whole
   log/doc is rejected. `error.reason` is usually **empty** in the exporter log;
   to see the real reason, temporarily enable the data-stream failure store,
   read the rejected docs, then revert:
   ```bash
   # enable (diagnostic), read, disable — see memory/incident 2026-08-05
   PUT  /_data_stream/logs-generic-default/_options {"failure_store":{"enabled":true}}
   GET  /logs-generic-default::failures/_search?size=5&sort=@timestamp:desc
   DELETE /_data_stream/logs-generic-default/_options
   ```
   Known instance (fixed 2026-08-05): k8s Event `managedFields` carries a `"."`
   key → "field name cannot contain only dots" → fixed by the
   `transform/strip-k8s-managedfields` processor. NB the OTLP record path is
   `log.body["object"]…` — the `body.structured.*` seen in ES is the otel-mode
   wrapper, not the record path.

2. **`validation errors` on `elasticsearch/metrics`** — individual metric
   points dropped:
   - *"dropping cumulative temporality histogram X"* — ES otel-mode only
     accepts **delta** histograms. Fix: add X to the
     `cumulativetodelta/es-histograms` include list in
     `kubernetes/apps/monitoring/edot-collector/app/configmap.yaml`.
   - *"invalid number data point X, wrong ValueType Empty"* — untyped/info
     series ES can never store; the `filter/drop-es-invalid-metrics`
     processor (`type == METRIC_DATA_TYPE_NONE`) drops them pre-export
     (they remain in Prometheus).

   > **Count POINTS, not LINES.** The exporter batches every rejected point of a
   > flush into ONE `validation errors` line (~18 reasons per line), so the line
   > count barely moves no matter how much telemetry is lost. On 2026-08-15
   > Envoy Gateway phase 0 added 6720 dropped points/h (34 histogram families
   > across `envoy-internal`, `envoy-external` and the `envoy-gateway` control
   > plane) while the line counter sat flat at ~362/h and the check reported
   > healthy. `health-check.sh` now counts drop reasons and trips at **100/h** —
   > one un-converted family on a single 30s-scraped target is ~120 points/h, so
   > the next regression of this class surfaces on the first family instead of
   > hiding in a flat line. It also names the offending families in the finding.
   >
   > Health-check output line:
   > `edot-collector ES rejections last 1h: parse=<n> validation_lines=<n> dropped_points=<n>`
   > `validation_lines` is retained for continuity but is NOT the signal —
   > assert on `dropped_points`.

   Manual triage:
   ```bash
   # dropped POINTS in the last hour (the real loss figure)
   kubectl logs -n monitoring deploy/edot-collector --since=1h \
     | grep -oE "dropping [a-z]+ [a-z]+|invalid number data point" | wc -l

   # which histogram families — add each to cumulativetodelta/es-histograms
   kubectl logs -n monitoring deploy/edot-collector --since=1h \
     | grep -oE 'histogram \\"[a-zA-Z0-9_]+' | sed 's/^histogram \\"//' | sort -u
   ```

Always validate an edot config change before rolling (throwaway pod:
`otel/opentelemetry-collector-contrib:<ver> validate --config=...`, dummy
`ES_PASSWORD`) — a bad config crashloops the cluster-wide telemetry path.

---

## Event Log Patterns

```bash
# Recent cluster events (all namespaces)
kubectl get events -A --sort-by='.lastTimestamp' | tail -50

# Warning events only
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -30

# Events for a specific object
kubectl get events -n {namespace} \
  --field-selector involvedObject.name={name},involvedObject.kind={kind} \
  --sort-by='.lastTimestamp'
```

---

## JSON Parsing Patterns

Prefer Python over `jq` for complex `kubectl ... -o json` parsing to avoid shell escaping issues.

```bash
# Preferred pattern for complex JSON extraction
kubectl get pod {name} -n {namespace} -o json | python3 -c "
import sys, json
pod = json.load(sys.stdin)
ready = next((c for c in pod['status']['conditions'] if c['type'] == 'Ready'), None)
print(f\"Ready: {ready['status'] if ready else 'Unknown'}\")
"
```

---

## Grafana

### Access

```bash
# Via ingress (if configured)
# https://grafana.${SECRET_DOMAIN}

# Via port-forward
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80 &
# Open http://localhost:3000
```

### Default Dashboards

Key dashboards to check during health checks:
- **Kubernetes / Cluster** — overall cluster resource usage
- **Kubernetes / Nodes** — per-node CPU, memory, disk
- **Kubernetes / Pods** — pod resource usage by namespace
- **Longhorn** — volume health, capacity, backup status
- **UniFi** (via Unpoller) — network device stats, client counts
- **Node Exporter Full** — detailed node metrics

### Adding a New Dashboard

1. Export dashboard JSON from Grafana UI
2. Add as ConfigMap in `kubernetes/apps/monitoring/grafana/` or use Grafana provisioning
3. Commit and push — Reloader will restart Grafana to pick up changes

---

## Alertmanager

### AlertmanagerConfig Namespace Routing (Critical Design Constraint)

**Problem:** Prometheus Operator's default `matcherStrategy` is `OnNamespace`. It automatically
injects `namespace="<config-namespace>"` as a top-level matcher into every `AlertmanagerConfig`
route. Without overriding this, alerts from all namespaces except the config's own namespace
silently fall through to `receiver: null`.

**Example of the failure:** `KubePodCrashLooping` fired for cloudflared (62 restarts over 4 days
in the `network` namespace) and never reached Telegram because the `AlertmanagerConfig` in the
`monitoring` namespace only routed `namespace="monitoring"` alerts.

**Fix applied (2026-05-05):** `alertmanagerConfigMatcherStrategy: {type: None}` in the
kube-prometheus-stack Helm values (`helmvalues.yaml`). This removes automatic namespace injection,
making the `monitoring/telegram` AlertmanagerConfig route `severity=warning` alerts from ALL
namespaces to Telegram.

**Verify the fix is active:**
```bash
# Live config must have zero namespace= matchers at the top-level route
kubectl exec -n monitoring alertmanager-kube-prometheus-stack-0 -c alertmanager \
  -- cat /etc/alertmanager/config_out/alertmanager.env.yaml | grep -c 'namespace='
# Expected: 0 (any positive number means the fix was lost during a Helm upgrade)

# Alertmanager CRD must have the setting
kubectl get alertmanager kube-prometheus-stack -n monitoring \
  -o jsonpath='{.spec.alertmanagerConfigMatcherStrategy}'
# Expected: {"type":"None"}
```

**If the fix is lost** (e.g., after a chart upgrade that resets the spec): re-apply via
`helmvalues.yaml` → `alertmanager.alertmanagerSpec.alertmanagerConfigMatcherStrategy.type: None`
and reconcile.

### Alert Rule Authoring Gotchas

**Never compare `increase()` / `rate()` against exact integers.** PromQL
`increase()` (and `rate()`) extrapolate to the range boundaries, so a genuine
counter delta of exactly N over the window evaluates to slightly *more* than N
(e.g. a raw +3 reads as ~3.01). An `expr: increase(foo[6h]) > 3` therefore
still fires on a real +3. Allow for the boundary overshoot — use an `N.5`
threshold (`> 3.5`) or an `>= N+1` with headroom, so a single expected burst
stays silent while sustained/multi-cycle failures still trip.

This trap bit two consecutive tuning commits on the `AragScrapeFailing` rule
(`kubernetes/apps/monitoring/kube-prometheus-stack/app/macos-apps-alerts.yaml`)
before landing on `> 3.5`.

### View Active Alerts

```bash
# Via Prometheus UI: http://localhost:9090/alerts

# Via kubectl
kubectl get prometheusrule -A
kubectl get alertmanagerconfig -A
```

### Alert Silencing

```bash
# Via Alertmanager UI
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &
# Open http://localhost:9093 → Silences → Create Silence
```

### Common Alerts

| Alert | Typical Cause | Action |
|-------|-------------|--------|
| KubeJobNotCompleted | CronJob pod stuck/failing | Check job logs |
| KubePodNotReady | Pod failing to start | Check pod events/logs |
| KubePersistentVolumeFillingUp | Volume nearing capacity | Expand PVC |
| TargetDown | Scrape target unavailable | Check service/pod health |
| Watchdog | Always firing — confirms Alertmanager works | Normal |
| CloudflaredTunnelDown | 0 tunnel connections — QUIC/MTU regression | Check MTU=1500 in Cilium; see cilium/cilium#37529 |
| CloudflaredTunnelDegraded | <4 tunnel connections | Check cloudflared pod logs and restart count |

---

## ELK Stack (Elasticsearch + Kibana + edot-collector)

### Elasticsearch Access

```bash
# Port-forward to Elasticsearch
kubectl port-forward -n monitoring svc/elasticsearch-es-http 9200:9200 &

# Get elastic password
ELASTIC_PASS=$(kubectl get secret elasticsearch-es-elastic-user \
  -n monitoring -o jsonpath='{.data.elastic}' | base64 -d)

# Test connection
curl -k -u elastic:${ELASTIC_PASS} https://localhost:9200/_cluster/health?pretty

# Check index health
curl -k -u elastic:${ELASTIC_PASS} https://localhost:9200/_cat/indices?v

# Query recent logs
curl -k -u elastic:${ELASTIC_PASS} https://localhost:9200/logs-generic-default/_search \
  -H "Content-Type: application/json" \
  -d '{"query":{"range":{"@timestamp":{"gte":"now-1h"}}},"size":10,"sort":[{"@timestamp":"desc"}]}'
```

**Note:** edot-collector and similar minimal containers don't have `cat`, `curl`, or `wget`.
Always use port-forward from your local machine for Elasticsearch access.

### Kibana Access

```bash
# Via ingress
# https://kibana.${SECRET_DOMAIN}

# Via port-forward
kubectl port-forward -n monitoring svc/kibana-kb-http 5601:5601 &
# Open http://localhost:5601
```

### Log Investigation Workflow

1. Open Kibana → Discover
2. Select index pattern `logs-generic-default`
3. Set time range (e.g., last 1 hour)
4. Filter by `resource.attributes.k8s.namespace.name: {namespace}`
   (and `resource.attributes.k8s.container.name: {container}` to narrow further)
5. Search for errors with a **wildcard**: `body.text: *rror*`

> **These field names matter, and the old ones failed silently.** Until
> 2026-08-15 this workflow said to filter on `kubernetes.namespace.name` and
> search `log: error`. Neither `kubernetes.*` nor `log` exists in the current
> mapping, and `body.text` is mapped as a **`keyword`** (`ignore_above: 1024`),
> not analysed text — so `match` / `query_string` full-text searches return
> **zero hits rather than an error**. Following the old steps during an
> incident produced a confident "no errors in the logs" for a pod that was
> visibly failing. Use `wildcard` / `regexp` / `term` on `body.text`, never a
> full-text match.
>
> **Always prove the query path before trusting a zero.** Search a term you
> know is present (e.g. `body.text: *readiness*`) first; if the control also
> returns 0, the query is wrong, not the cluster.

> **`severity_text` is a dead field — do not filter on it.** In this data
> stream it is populated on roughly **28 documents out of ~3.49 million**.
> The same silent-zero failure class as the `kubernetes.*`/`log` trap above:
> `{"terms": {"severity_text": ["ERROR", "FATAL"]}}` returns near-zero hits
> and reads as "no errors", when the field is simply unpopulated on the log
> stream. The only reliable way to find error-level logs is the `body.text`
> wildcard from step 5 (e.g. `body.text: *error*`).
>
> **Companion trap: a bare `*ERROR*`/`*error*` wildcard also matches
> CoreDNS's `NOERROR` rcode** — the string it logs for a *successful* DNS
> answer — which inflates error counts with healthy DNS traffic. Fixed in
> `runbooks/health-check.sh` (commit `3af29366`) by adding a sibling clause
> that excludes `*NOERROR*`:
> ```json
> {"wildcard": {"body.text": "*ERROR*"}},
> {"bool": {"must_not": {"wildcard": {"body.text": "*NOERROR*"}}}},
> {"wildcard": {"body.text": "*FATAL*"}}
> ```
> Treat `runbooks/health-check.sh` as the working reference implementation
> rather than re-deriving the exclusion by hand.

### edot-collector

```bash
# Check edot-collector Deployment status
kubectl get deployment edot-collector -n monitoring

# Check pod
kubectl get pods -n monitoring -l app.kubernetes.io/name=edot-collector

# View logs (edot-collector has minimal utilities — use port-forward for API)
kubectl logs -n monitoring -l app.kubernetes.io/name=edot-collector --tail=20

# Check edot-collector health API (via port-forward)
POD=$(kubectl get pod -n monitoring -l app.kubernetes.io/name=edot-collector -o name | head -1)
kubectl port-forward -n monitoring ${POD} 13133:13133 &
curl http://localhost:13133/
```

---

## Uptime Kuma

Service uptime monitoring with status pages.

```bash
# Access via ingress
# https://uptime.${SECRET_DOMAIN}

# Via port-forward
kubectl port-forward -n monitoring svc/uptime-kuma 3001:3001 &
# Open http://localhost:3001
```

Add new monitors in the UI for new services. Configure notification channels for alerts.

### ⚠️ After editing/removing a monitor — restart uptime-kuma to flush stale Prometheus series

Kuma's Prometheus exporter caches each monitor's **label-set in memory** (including
`monitor_hostname`). When you **edit** a monitor's host (or remove/disable it), the
exporter keeps emitting the **old** label-set with its last status (e.g. `monitor_status=0`
for the old IP) until the pod restarts. There is **no active/paused label** to filter on,
so the health-check's `monitor_status{monitor_type!="group"} == 0` query keeps flagging the
ghost series as DOWN — producing false "Kuma: X down (old-ip)" findings that never clear.

Fix: restart the pod so the exporter re-registers only current configs.
```bash
kubectl -n monitoring rollout restart deploy/uptime-kuma
# wait ~45s for re-scrape, then confirm no stale DOWN series:
# (port-forward prometheus) curl -s 'http://localhost:9090/api/v1/query?query=monitor_status{monitor_type!="group"}==0'
```
Observed 2026-06-07 after the VLAN-55 reorg: UNAS/DreamMachine monitors were re-pointed
`.31.230`→`.55.240` / `.31.1`→`.30.1`, but the old DOWN series persisted until this restart.

---

## Blackbox Exporter (synthetic DNS + ingress probes)

Deployed 2026-08-15 (N-15) after internal DNS went down twice and produced
**zero** SLO signal — `probe_success` did not exist. Manifests:
`kubernetes/apps/monitoring/prometheus-blackbox-exporter/`.

Three things here are NOT derivable from the manifests:

1. **`Probe` CRs and `serviceMonitor.targets` are mutually exclusive.**
   Prometheus selects all Probes cluster-wide (`probeSelector={}`), so the
   Probe CRs work on their own. The chart's `serviceMonitor.enabled` generates
   per-target ServiceMonitors from `serviceMonitor.targets` — the *alternative*
   mechanism. Turning both on double-scrapes every target.
   `serviceMonitor.selfMonitor` is a different key (the exporter's own
   `/metrics`) and is intentionally on.

2. **The DNS modules assert on the ANSWER, not reachability.**
   `valid_rcodes: [NOERROR]` **plus** `validate_answer_rrs` requiring a real A
   record. Rcode alone is not enough: a resolver answering NOERROR with an
   EMPTY answer section would otherwise score healthy — verified against a
   public resolver, which returns exactly that shape for an internal name and
   correctly scores `probe_success=0`. One Probe per queried name, because the
   name lives in the blackbox module, not in the Probe target.

3. **`config.modules` is a Helm MAP MERGE.** The chart's default `http_2xx`
   module survives your `config:` block unless explicitly nulled
   (`http_2xx: null`). That default has no `fail_if_not_ssl`, no
   `valid_status_codes` and follows redirects — an unauthenticated in-cluster
   blind-SSRF / port-reachability oracle on `/probe`. Verify the live module
   list after any values change:
   ```bash
   kubectl get cm prometheus-blackbox-exporter -n monitoring -o yaml | grep -A1 "^    [a-z_]*:$"
   ```

> **Validation gotcha:** `kubeconform` SKIPS all 8 resources in this app
> (HelmRelease/Probe/PrometheusRule are CRDs), so it validates nothing here.
> That skip hid a wrong `serviceMonitor` values shape that rendered no
> ServiceMonitor at all. Always `helm template` against the pulled chart.

---

## Headlamp (Kubernetes UI)

```bash
# Access via ingress
# https://headlamp.${SECRET_DOMAIN}
```

Headlamp provides a read-only web view of Kubernetes resources. Useful for quick cluster state checks without kubectl.

---

## UniFi Monitoring (Unpoller)

Unpoller exports UniFi metrics to Prometheus.

```bash
# Check Unpoller is running
kubectl get pods -n monitoring -l app.kubernetes.io/name=unpoller

# View Unpoller logs
kubectl logs -n monitoring -l app.kubernetes.io/name=unpoller --tail=20

# Grafana dashboards use metrics from Unpoller:
# - UniFi-Poller: USG Insights
# - UniFi-Poller: UAP Insights
# - UniFi-Poller: USW Insights
```

---

## Job and CronJob Monitoring

Known CronJobs in this cluster:
- `storage/backup-of-all-volumes` (Longhorn backups, daily 3:00 AM)
- `kube-system/descheduler` (rescheduling optimization)

```bash
# List CronJobs
kubectl get cronjobs -A

# Recent jobs
kubectl get jobs -A --sort-by='.status.startTime' | tail -20

# Logs for a job
kubectl logs -n {namespace} job/{job-name} --tail=50
```

---

## Health Check

Weekly monitoring health checks:

```bash
# 1. All monitoring pods running?
kubectl get pods -n monitoring | grep -v Running | grep -v Completed

# 2. Prometheus targets healthy?
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s 'http://localhost:9090/api/v1/targets' | python3 -c "
import sys, json
targets = json.load(sys.stdin)['data']['activeTargets']
down = [t for t in targets if t['health'] != 'up']
if down:
    for t in down:
        print('DOWN:', t['labels'].get('job'), t.get('lastError',''))
else:
    print('All', len(targets), 'targets UP')
"

# 3. Any firing alerts?
curl -s 'http://localhost:9090/api/v1/alerts' \
  | python3 -c "
import sys, json
alerts = [a for a in json.load(sys.stdin)['data']['alerts']
          if a['state'] == 'firing'
          and a['labels']['alertname'] not in ['Watchdog','InfoInhibitor']]
print(f'{len(alerts)} firing alerts' if alerts else 'No alerts firing')
for a in alerts:
    print(' -', a['labels']['alertname'])
"

# 4. Elasticsearch cluster health?
kubectl port-forward -n monitoring svc/elasticsearch-es-http 9200:9200 &
PASS=$(kubectl get secret elasticsearch-es-elastic-user -n monitoring \
  -o jsonpath='{.data.elastic}' | base64 -d)
curl -sk -u elastic:${PASS} https://localhost:9200/_cluster/health | python3 -c "
import sys, json; h = json.load(sys.stdin)
print(f\"ES: {h['status']}, nodes: {h['number_of_nodes']}, shards: {h['active_shards']}\")"

pkill -f "kubectl port-forward"
```

---

## Troubleshooting

### Prometheus Not Scraping a Target

```bash
# Check ServiceMonitor exists
kubectl get servicemonitor -n {namespace}

# Check endpoint is reachable
kubectl port-forward -n {namespace} svc/{service} {port}:{port} &
curl http://localhost:{port}/metrics | head -20

# Prometheus logs
kubectl logs -n monitoring -l app.kubernetes.io/name=prometheus --tail=50 | grep -i error
```

### Grafana Dashboard Not Loading Data

```bash
# Check Grafana datasource connection
# UI: Configuration → Data Sources → Prometheus → Save & Test

# Check Grafana logs
kubectl logs -n monitoring -l app.kubernetes.io/name=grafana --tail=50
```

### edot-collector Not Shipping Logs

```bash
# Check edot-collector configmap
kubectl get configmap -n monitoring edot-collector -o yaml | grep -A20 "exporters"

# edot-collector image is minimal; avoid relying on cat/curl/wget in pod
POD=$(kubectl get pod -n monitoring -l app.kubernetes.io/name=edot-collector -o name | head -1)
kubectl port-forward -n monitoring ${POD} 13133:13133 &
curl http://localhost:13133/
kubectl logs -n monitoring ${POD} --tail=50 | grep -i "error\|warn\|fail"
```

### OtelDaemonCollectorDown — edot-collector CreateContainerConfigError (PSA label reset)

**Symptom:** `OtelDaemonCollectorDown` alert fires; edot-collector DaemonSet pods stuck in
`CreateContainerConfigError`; pod events show `unable to validate against any security policy`.

**Root cause:** The `monitoring` namespace requires `pod-security.kubernetes.io/enforce: privileged`
because edot-collector mounts `hostPath` volumes. Every Flux Kustomization scoped to the
`monitoring` namespace that carries its own namespace patch can overwrite the PSA labels.
Whichever Kustomization reconciles **last** wins — if it does not include the `privileged` patch,
the label reverts to `baseline` and the DaemonSet breaks.

**Fix:**

```bash
# 1. Verify current PSA label
kubectl get namespace monitoring -o jsonpath='{.metadata.labels}' | python3 -m json.tool | grep pod-security

# 2. Apply privileged label directly (unblocks the DaemonSet immediately)
kubectl label namespace monitoring \
  pod-security.kubernetes.io/enforce=privileged \
  pod-security.kubernetes.io/audit=privileged \
  pod-security.kubernetes.io/warn=privileged \
  --overwrite

# 3. Find which Kustomization is missing the privileged patch
grep -rL 'pod-security.kubernetes.io/enforce: privileged' \
  kubernetes/apps/monitoring/*/app/kustomization.yaml

# 4. Add the privileged namespace patch to each missing kustomization.yaml:
#    patches:
#      - target:
#          kind: Namespace
#          name: not-used
#        patch: |-
#          apiVersion: v1
#          kind: Namespace
#          metadata:
#            name: not-used
#            labels:
#              pod-security.kubernetes.io/enforce: privileged
#              pod-security.kubernetes.io/audit: privileged
#              pod-security.kubernetes.io/warn: privileged

# 5. Commit, push, wait for Flux reconciliation, verify DaemonSet recovers
kubectl rollout status daemonset/edot-collector -n monitoring
```

**Invariant:** Every `app/kustomization.yaml` under `kubernetes/apps/monitoring/` **must** include
the `pod-security.kubernetes.io/enforce: privileged` namespace patch. Adding a new app to the
`monitoring` namespace without this patch will reproduce the issue on the next Flux reconcile cycle.

---

## Diagnose Examples

### Diagnose Example 1: Prometheus Target Down

```bash
kubectl get servicemonitor -A
kubectl get endpoints -n {namespace} {service}
kubectl logs -n monitoring -l app.kubernetes.io/name=prometheus --tail=100 | rg -i "error|down|scrape"
```

Expected:
- Root cause identified as missing endpoint, bad monitor selector, or scrape error.

If unclear:
- Port-forward target service and test `/metrics` manually.

### Diagnose Example 2: edot-collector Not Shipping Logs

```bash
kubectl get deployment edot-collector -n monitoring
kubectl logs -n monitoring -l app.kubernetes.io/name=edot-collector --tail=100
kubectl port-forward -n monitoring $(kubectl get pod -n monitoring -l app.kubernetes.io/name=edot-collector -o name | head -1) 13133:13133 &
curl http://localhost:13133/
```

Expected:
- Health endpoint and logs clarify pipeline failure location.

If unclear:
- Verify Elasticsearch cluster health and index status.

### Diagnose Example 3: OtelDaemonCollectorDown — PSA Label Reset

```bash
# 1. Check DaemonSet and pod state
kubectl get daemonset edot-collector -n monitoring
kubectl get pods -n monitoring -l app.kubernetes.io/name=edot-collector

# 2. Check pod event for PSA rejection
kubectl describe pod -n monitoring \
  $(kubectl get pod -n monitoring -l app.kubernetes.io/name=edot-collector -o name | head -1) \
  | grep -A5 "Events:"
# Look for: "unable to validate against any security policy"

# 3. Confirm namespace PSA label is missing or wrong
kubectl get namespace monitoring -o jsonpath='{.metadata.labels}' | python3 -m json.tool | grep pod-security
# Expected: enforce: privileged. If missing or "baseline" → root cause confirmed.

# 4. Find kustomization(s) missing the privileged patch (whichever reconciled last reset it)
grep -rL 'pod-security.kubernetes.io/enforce: privileged' \
  kubernetes/apps/monitoring/*/app/kustomization.yaml
# Any file printed here is the culprit — add the privileged patch and commit.
```

Expected:
- Pod events show PSA rejection; namespace label is `baseline` or absent.
- `grep -rL` identifies which kustomization is missing the patch.

If unclear:
- Check Flux reconciliation timestamps: `flux get kustomizations -n flux-system | grep monitoring`
  to see which Kustomization reconciled most recently — that one reset the label.

---

## Security Check

```bash
# Ensure monitoring secrets are SOPS encrypted in Git
find kubernetes/apps/monitoring -name '*.sops.yaml' -print

# Quick scan for accidentally committed plaintext credentials
rg -n --glob '*.yaml' 'password|token|api[_-]?key|secret' kubernetes/apps/monitoring | head -40
```

Expected:
- Sensitive values remain encrypted and no plaintext credentials are introduced.

---

## Rollback Plan

```bash
# Revert monitoring stack changes causing regressions
git log -- kubernetes/apps/monitoring
git revert <commit-sha>
git push
```

Rollback validation:
- Re-run `Verification Tests` and `Health Check`.
