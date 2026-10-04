# SOP: Monitoring & Observability

> Standard Operating Procedures for the cluster monitoring stack.
> Stack: Prometheus + Alertmanager + Grafana + ELK (Elasticsearch + Kibana + edot-collector).
> Description: Operating, validating, and troubleshooting metrics/logging/alerting components.
> Version: `2026.10.04`
> Last Updated: `2026-10-04`
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
| prometheus-blackbox-exporter | Synthetic DNS + HTTPS probes (`probe_success`) — the DNS/routing SLI | monitoring |

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

### Push-based Metrics (Pushgateway)

Batch jobs that are not alive long enough to be scraped PUSH instead, to
`prometheus-pushgateway.monitoring:9091` (ClusterIP only, no HTTPRoute). It is a
permanent always-up scrape target, which is why it replaced the racy per-pod
Service+ServiceMonitor on short-lived CronJobs.

| Pusher | Job label | Cadence | Metrics | Alert rules |
|--------|-----------|---------|---------|-------------|
| `home-automation/pallet-price-monitor` | `pellet-price-monitor` | twice daily (08:00/20:00) | `pellet_*` | `pallet-price-monitor-alerts.yaml` |
| `kube-system/authentik-db-probe` | `authentik-db-probe` | hourly at :17 | `authentik_audit_*`, `authentik_db_connections_*`, `authentik_db_probe_last_success_timestamp_seconds` | `authentik-alerts.yaml` (`authentik.audit.freshness`) |
| `backup/icloud-backup-freshness` | `icloud-backup-freshness` | hourly at :23 | `icloud_backup_newest_file_timestamp_seconds{account}`, `icloud_backup_probe_last_success_timestamp_seconds` | `icloud-backup-alerts.yaml` (`icloud-backup.freshness`, 14-day backstop) |
| `backup/icloud-sync-probe` | `icloud-sync-probe` (grouped by `account`) | every 10 min | `icloud_sync_last_success_timestamp_seconds{account}`, `icloud_auth_required{account}`, `icloud_sync_items_failed{account}`, `icloud_sync_failing_item_since_timestamp_seconds{account}`, `icloud_sync_probe_last_success_timestamp_seconds{account}`, `icloud_drive_sync_last_success_timestamp_seconds{account}`, `icloud_drive_items_failed{account}`, `icloud_drive_failing_item_since_timestamp_seconds{account}` | `icloud-backup-alerts.yaml` (`icloud-backup.sync`, `icloud-backup.drive`) |
| `media/media-intake-watcher` | `media-intake-watcher` | every 30 min | `media_intake_items{state}`, `media_intake_ambiguous_items{reason}`, `media_intake_ambiguous_oldest_first_seen_timestamp_seconds`, `media_intake_run_actions`, `media_intake_actions_24h`, `media_intake_run_aborted{reason}`, `media_intake_apply_enabled`, `media_intake_last_run_timestamp_seconds` | `media-intake-alerts.yaml` (`media-intake.watcher`) |

Three rules, each of which has already cost real time:

1. **Push a TIMESTAMP, never a pre-computed age.** Pushgateway is in-memory and
   has **no TTL** — it serves the last value pushed, forever. An age gauge
   therefore FREEZES at its last value the moment the pusher dies, silently
   disarming the very alert that reads it. A timestamp keeps ageing in PromQL
   (`time() - max(<metric>)`) whether or not the pusher still runs. The house
   examples are `pellet_last_run_timestamp_seconds` and
   `authentik_db_probe_last_success_timestamp_seconds`.

2. **The POST body MUST end with a newline.** The Prometheus text format requires
   the final line to be newline-terminated; pushgateway answers an unterminated
   body with `HTTP 400 Bad Request` and stores **nothing**. This is nasty because
   shell command substitution *strips* trailing newlines, so the natural-looking
   construction is always wrong:

   ```sh
   # WRONG — $(...) strips the trailing newline -> HTTP 400, nothing stored
   PAYLOAD=$(printf '%s\n' "# TYPE x gauge" "x 1")
   wget -q -O - --post-data "$PAYLOAD" "$PGW/metrics/job/myjob"

   # RIGHT — the file keeps exactly what printf wrote -> HTTP 200
   printf '%s\n' "# TYPE x gauge" "x 1" > /tmp/p.prom
   wget -q -O - --post-file /tmp/p.prom "$PGW/metrics/job/myjob"
   ```

   The script reads correctly either way and only the wire format objects, so
   this is invisible at review time. It killed the first scheduled run of
   `authentik-db-probe` (2026-09-12). Note `busybox wget` (alpine) has no `curl`
   but does support `--post-file`; it cannot issue `DELETE`.

3. **A push replaces a grouping WHOLESALE.** Pushing a partial metric set to
   `/metrics/job/<name>` deletes the gauges you left out. So on failure, push
   **nothing** rather than a partial set — the stale-but-present snapshot keeps
   timestamp-based staleness rules ageing correctly, whereas a partial push
   blinds them. Pair every pushed gauge with an `absent()` guard, because
   "pusher removed" and "pusher never ran" both present as no series.

Verify what is currently stored, and clear a test grouping:

```bash
kubectl port-forward -n monitoring svc/prometheus-pushgateway 9191:9091 &
curl -s http://localhost:9191/metrics | grep '^push_time_seconds{'   # one line per grouping
curl -X DELETE http://localhost:9191/metrics/job/<job-name>          # 202 Accepted
```

> Note: prometheus-operator sets the `job` label on `ScrapeConfig` targets to
> `scrapeConfig/<namespace>/<name>` (e.g. `scrapeConfig/monitoring/arag-scrape`),
> not the bare app name. `up{job="<app>"}`-style exprs will not match; use the
> full operator-generated label. `AragScrapeDown` uses the correct form; the
> older FindMyTraccarSyncDown / BankRefreshDown `up{job="..."}` exprs are known
> to be latent no-ops (metric-based rules still work).

The arag-scrape app also ships OTLP/HTTP JSON logs (`service.name=arag-scrape`)
to the edot-collector via the internal route `otlp.${SECRET_DOMAIN}` (HTTPRoute `monitoring/edot-collector` on `envoy-internal`; backend
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

# Longhorn — FILL alerting keys on the kubelet metrics, not the Longhorn ones
kubelet_volume_stats_used_bytes       # what LonghornVolumeFilesystemUsageHigh measures
kubelet_volume_stats_capacity_bytes
longhorn_volume_actual_size_bytes     # ALLOCATION (incl. stale + snapshot blocks) — NOT the fill signal
longhorn_snapshot_actual_size_bytes   # drives LonghornVolumeSnapshotChainNotPruned
longhorn_volume_state
```

### CRD ownership: `monitoring.coreos.com` has TWO writers (proven 2026-09-15)

The ten `monitoring.coreos.com` CRDs are not written by kube-prometheus-stack
alone. Four of them — `podmonitors`, `probes`, `scrapeconfigs`,
`servicemonitors` — are ALSO written by the **otel-operator** HelmRelease
(`kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml`): the
`opentelemetry-kube-stack` umbrella carries a `prometheus-crds` subchart
(Chart.yaml condition `crds.install,crds.installPrometheus`, values default
`true`) that ships exactly those four from a **`crds/` directory** — it has no
`templates/`, so they are applied by helm-controller's CRD path and are **not
release resources** (no `meta.helm.sh/release-name`, no
`app.kubernetes.io/managed-by: Helm` on the live objects). Both HelmReleases run
Flux `install.crds`/`upgrade.crds: CreateReplace`, so the last chart to upgrade
wins: after every otel-operator bump the four re-read
`operator.prometheus.io/version: 0.92.0` (the copy vendored in that subchart) and
`helm.toolkit.fluxcd.io/name: otel-operator`, while the other six carry the
kube-prometheus-stack operator version (`0.93.1` as of 2026-09-15). This is the
state the sweep keeps re-discovering as "four CRDs read 0.92.0 under a newer
operator" — it is **provenance, not corruption**, and no ScrapeConfig here uses
a field newer than 0.92.0.

Proof from the live objects (empty `release-name`/`managed-by` on all ten = the
`crds/` path; `hr=` shows the last writer):

```bash
for c in podmonitors probes scrapeconfigs servicemonitors prometheuses alertmanagers; do
  echo -n "$c: "
  kubectl get crd "$c.monitoring.coreos.com" \
    -o jsonpath='opver={.metadata.annotations.operator\.prometheus\.io/version} hr={.metadata.labels.helm\.toolkit\.fluxcd\.io/name} release-name=[{.metadata.annotations.meta\.helm\.sh/release-name}] managed-by=[{.metadata.labels.app\.kubernetes\.io/managed-by}]{"\n"}'
done
```

The durable fix is `crds.installPrometheus: false` in the otel-operator
HelmRelease values — plan `runbooks/maintenance/plans/prometheus-crd-ownership.md`
(sweep record `F-a85e8943`; its `[AR-072]` title prefix is needle noise, that
AR's substring is the bare `opentelemetry`). helm-controller then stops
collecting the subchart's `crds/` on install and upgrade, and
kube-prometheus-stack becomes the single writer of all ten from its next upgrade.
**There is no cascade-delete risk in that change**: Helm never deletes
`crds/`-directory CRDs, and Flux `CreateReplace` only creates or replaces — the
four CRDs, and every ServiceMonitor/PodMonitor/Probe/ScrapeConfig under them,
are untouched. Do not re-litigate that fear at the next otel bump; verify with
the loop above instead.

---

## Collector OOM and memory_limiter (otel-operator DaemonSet)

The ES side above is only half the pipeline. The per-node **otel-operator
daemon collectors** (`otel-operator-daemon-collector-*`, 512Mi limit) can be
OOMKilled on their own: on 2026-09-24 two of three were killed at the limit
(F-4c13797f) while the central edot-collector, which already had a limiter,
survived. An OOMKill drops whatever the pod had buffered for that node.

Rule: **every collector pipeline starts with `memory_limiter`**. The daemon
config in `kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml` uses
`check_interval: 1s`, `limit_percentage: 80`, `spike_limit_percentage: 20`
(percent of the cgroup limit, so it follows any future limit change). Above the
soft limit the receivers refuse data and the pod stays alive.

Chart trap (opentelemetry-kube-stack): the `kubernetesAttributes` preset
PREPENDS `k8s_attributes` to any processor list that lacks it, and a
user-supplied list REPLACES the chart defaults (`resource_detection/env`,
`resource/hostname`). So write the full list, `memory_limiter` first, and
check the rendered `OpenTelemetryCollector` with `helm template` before you
commit.

Checks:

```bash
# Restarts / last termination reason per daemon pod
kubectl -n monitoring get pods -l app.kubernetes.io/component=opentelemetry-collector \
  -o custom-columns=POD:.metadata.name,NODE:.spec.nodeName,RESTARTS:.status.containerStatuses[0].restartCount,LAST:.status.containerStatuses[0].lastState.terminated.reason
# Limiter is loaded (live config); refusals show up in the pod log as "memory usage is above soft limit"
kubectl -n monitoring get otelcol otel-operator-daemon -o yaml | grep -A4 memory_limiter
kubectl -n monitoring logs ds/otel-operator-daemon-collector --since=1h | grep -i "memory_limiter\|soft limit"
```

If the limiter keeps refusing data, raise the container limit. Do not remove
the limiter, and do not raise `limit_percentage` above 80.

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
     `cumulative_to_delta/es-histograms` include list in
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

   # which histogram families — add each to cumulative_to_delta/es-histograms
   kubectl logs -n monitoring deploy/edot-collector --since=1h \
     | grep -oE 'histogram \\"[a-zA-Z0-9_]+' | sed 's/^histogram \\"//' | sort -u
   ```

### Metric-based rejection assertion (Prometheus, since 2026-08-18)

The log-grep checks above only see **1h of the current pod's logs** — a
restart wipes the evidence, and `otelcol_exporter_send_failed_*` stays at 0
during per-doc rejections because the bulk *request* returns 200 while ES
rejects individual *documents* inside it. That combination is exactly how the
managedFields incident stayed invisible for weeks. `health-check.sh`
(Section 34, "OTel Pipeline Metrics") therefore also asserts on the
elasticsearchexporter's own per-document outcome counter, which survives pod
restarts:

```promql
# every exported document, labeled by outcome:
#   success | failed_client (per-doc 4xx mapping/parse rejection — the
#   incident class) | failed_server | too_many | retried
sum by (outcome) (increase({__name__="otelcol.elasticsearch.docs.processed_total",outcome!~"success|retried"}[6h]))
```

Thresholds (6h window):

- **> 3000 rejected docs → CRITICAL** (≈500/h sustained; the managedFields
  incident ran at ~750 rejected docs/h, so it trips within ~4h). Normal state
  is exactly 0 — matching `docs.received_total` — so no headroom is needed.
- **> 60 → WARNING** (≥10/h, same sensitivity as the 1h log-grep threshold).
- **Metric entirely absent → WARNING** ("rejection SLI blind"): failure-outcome
  series are only born on the first rejection, so *empty* means 0 (healthy),
  but a missing `success` series means edot self-telemetry itself is broken
  and the assertion is blind.

Triage on a trip: identify the rejected doc class via the failure store
(subsection 1 above) or the collector logs, then fix at the transform/filter
processor in `kubernetes/apps/monitoring/edot-collector/app/configmap.yaml`.
Distinguish from the *ingestion-stall* mode: a stalled TSDB rollover
(`timestamp_error` outside the write window, see
`docs/troubleshooting`/memory `project_es_otel_tsdb_recovery`) halts metric
ingestion and is handled by the **obs-recovery CronJob** + ingestion-stall
alerts — that shows up as `failed_client` rejections on the metrics stream
too, so check `_data_stream` rollover state before hunting for a mapping bug.

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

### Image variants: plain vs `-slim` — do NOT use `-slim` on 13.x

> **Changing the Grafana image?** The reusable pre-flight gate — including the
> throwaway-pod check that the PVC-leftover trap cannot fool — is
> [grafana-image-changes.md](grafana-image-changes.md). This section is the
> evidence for one rejected variant; that SOP is the procedure for any change.

Tested and rejected 2026-08-18. Recording it because the reasoning is not
derivable from the manifests and will otherwise be re-litigated at the next
Grafana CVE bump. Scan figures stay on the finding record: `security_ref:
F-de4d92cd`.

- **`-slim` ships `data/plugins-bundled` EMPTY.** That is its entire difference
  from the plain tag (`SLIM=true` in the upstream `grafana-plugins` build
  stage). Same base image, same Grafana build.
- **Those binaries are not redundant.** From 13.2.0, upstream expanded the
  bundled catalog-plugin set from 2 entries to 13 (prep for extracting core
  datasources from the monolith, PR #129593). The bundled binary **is** the
  delivery mechanism for the core datasource — it is not a duplicate of a
  compiled-in one. On the slim pod `/api/plugins?type=datasource` returned 6
  plugins against 18 on plain, all 6 being leftovers persisted on the
  `grafana-config` PVC, and Grafana logged
  `reason="plugin prometheus not found"`. Six of seven provisioned datasources
  would have been dead.
- **`GF_PLUGINS_PREINSTALL_DISABLED=true` is load-bearing if you ever do try
  slim.** Upstream also grew `defaultPreinstallPlugins` from 6 to 18, so
  without it the container re-downloads the identical binaries from grafana.com
  at startup, so the shipped image and the running container no longer match.
  That is worse than not making the change: the scan would describe something
  other than what is running. It also adds an egress dependency on grafana.com
  at pod start.
- **`-slim` / `-distroless` are published for every 13.x but are UNDOCUMENTED
  upstream** (the v13.2.0 docs describe only Alpine and Ubuntu variants), so any
  future attempt needs its own datasource re-verification, not a one-time sign-off.
- **Rollback direction:** plain `13.2.0`, never a chart revert or a downgrade to
  13.1.x — Grafana 13 migrates the sqlite schema on boot and that is
  forward-only. (Both the slim boot and the revert boot logged
  `migrations completed performed=0` and left `grafana.db` byte-identical, so
  the migration risk did not materialise — but it is the reason a version
  rollback is the wrong lever.)

**Verification gate for any Grafana image change** — every provisioned
datasource must resolve *and return data* before the change is considered done:

```bash
kubectl -n monitoring port-forward svc/grafana 33001:80 &
# health API per datasource
curl -su "$U:$P" -X POST localhost:33001/api/datasources/uid/<uid>/health
# alertmanager implements no backend health check — use the proxy instead
curl -su "$U:$P" localhost:33001/api/datasources/proxy/uid/alertmanager/api/v2/status
# and a real query through the data path
curl -su "$U:$P" -X POST localhost:33001/api/ds/query -H 'Content-Type: application/json' \
  -d '{"queries":[{"refId":"A","datasource":{"uid":"prometheus","type":"prometheus"},"expr":"count(kube_pod_info)","instant":true}]}'
```

### Access

```bash
# Via its HTTPRoute (envoy-internal)
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

## Alert Authoring Rules

Five rules, each of which exists because an alert can be **loaded, healthy, and
completely useless** — and look identical on every dashboard to one that works.
A rule matching no series sits at `state=inactive`, which is the same thing a
quiet, working rule looks like. All figures below were measured 2026-09-20.

**1. `release: kube-prometheus-stack` or it never loads.** A PrometheusRule
without that label is silently ignored — no error, no event, nothing. Verify
through the rules API, never from the HelmRelease's Ready status:

```bash
curl -s http://localhost:9090/api/v1/rules | python3 -c "
import sys,json; g=json.load(sys.stdin)['data']['groups']
print(len(g),'groups', sum(len(x.get('rules',[])) for x in g),'rules')"
```

Measured: 57 PrometheusRule objects in the repo, **0** missing the label; 119
groups / 412 alerting rules loaded, **0** with `health != ok`.

**2. Pair every group with an `absent()` guard.** The guard is what distinguishes
"quiet because healthy" from "quiet because the series vanished". Without it, a
collector that stays pod-Ready while its exporters disappear takes the whole
group silently off-duty.

**3. When AND-ing an `absent()` guard with a labelled vector, it MUST be
`and on()`.** This is the trap that motivated this section. `absent()` emits a
sample with an **empty label set**, and PromQL `and` matches on labels, so:

```promql
absent(my_metric) and up{job="exporter"} == 1      # PERMANENTLY INERT — 0 samples, always
absent(my_metric) and on() up{job="exporter"} == 1 # correct: on() collapses to the empty label set
```

The inert form loads cleanly, reports `health=ok`, and sits `inactive` forever.
It is proposed in good faith — "the guard should only fire when the exporter is
known up" — and it silently blinds the detector it was meant to strengthen.

**4. Prove non-inertness with a positive AND a negative control.** Never accept
"it returns nothing" as evidence; that is what both a working guard and a dead one
do. Evaluate the expression twice:

```promql
absent(metric{label="DOES-NOT-EXIST"})   # positive control -> MUST return 1 sample (and propagate label=)
absent(metric{label="<the real one>"})   # negative control -> MUST return 0 samples
```

If the positive control returns nothing, the guard can never fire. Set thresholds
from measured data for the same reason — a threshold no series can reach is inert
in exactly the same way.

**Audit (2026-09-20): no live rule carries the broken form.** Across 57
PrometheusRule files and 268 rules: 25 bare `absent()` guards (the correct
default), 0 using `and on()`, **0 AND-ed without `on()`**. So rule 3 is
preventive, not remedial — it was caught in review before shipping.

**5. Aggregate the one side of a join with `max by (...)` first — duplicate series
appear during exporter overlaps.** When an exporter's pod is replaced (a chart bump
rolling kube-state-metrics, a node drain), the old and new pods are scraped together for
a few minutes and every series exists **twice**, differing only in `instance` /
`kubernetes_node` / `pod`. A bare one-to-one or `group_left` join needs the "one" side
unique per match group, so the whole rule errors with `found duplicate series for the
match group ... on the right hand-side` and evaluates to nothing — the rule is blind
during exactly the changes that most often move the thing it watches (2026-09-26:
16 evaluation failures, 05:00–05:03Z, every `ContainerMemory*` rule blind; fixed in
`c430a771`).

```promql
# fragile: breaks while two kube-state-metrics pods overlap
container_memory_working_set_bytes / on(namespace,pod,container) group_left
  kube_pod_container_resource_limits{resource="memory"}
# robust: collapse the duplicate first (both copies carry the same value, so max changes nothing)
container_memory_working_set_bytes / on(namespace,pod,container) group_left
  max by (namespace,pod,container) (kube_pod_container_resource_limits{resource="memory"})
```

Generic rule: the `by (...)` list is exactly the `on(...)` list, and the aggregator must
be value-preserving for identical duplicates (`max`/`min`, never `sum`, which doubles the
value during the overlap). Leave `absent()` guards on the bare selector. Check a rule
for this with `/api/v1/rules`: `health: err` with `lastError` containing `duplicate
series` during a rollout is this trap.

> **Audit it by PARSING, not grepping.** Six alert files contain the string
> `and on()` only inside comments warning about this trap, and four quote the
> broken form as an example. A grep reports those as hits; loading the YAML and
> inspecting each rule's `expr` reports the truth, which is zero of each.

---

## NUC Thermals (CPU package, throttling, NVMe, RAPL power)

Added 2026-10-04. Rules: `kubernetes/apps/monitoring/kube-prometheus-stack/app/node-thermal-alerts.yaml`.
Tests (promtool, both ways + 11 mutants): `python3 runbooks/tests/test-node-thermal-alerts.py`.

### Where the metrics come from

All from the kube-prometheus-stack `prometheus-node-exporter` DaemonSet (`job="node-exporter"`, `instance=<node-ip>:9100`).

| Signal | Metric | Notes |
|---|---|---|
| CPU package temp | `node_hwmon_temp_celsius{chip="platform_coretemp_0",sensor="temp1"}` | "Package id 0"; same sensor as `node_thermal_zone_temp{type="x86_pkg_temp"}`. Tjmax/crit 110 °C |
| Thermal throttling | `node_cpu_package_throttles_total` | PROCHOT package-throttle **events** (not CFS throttling, which is `CPUThrottlingHigh`) |
| NVMe temp | `node_hwmon_temp_celsius{chip="nvme_nvme0",sensor="temp1"}` | "Composite". `node_hwmon_temp_max_celsius` on the same sensor is the drive's WCTEMP (81.85 °C), `_crit_` is CCTEMP (84.85 °C) |
| Package power | `rate(node_rapl_package_joules_total[5m])` (W) | also `node_rapl_core_*` (cores) and `node_rapl_psys_*` (platform) |

**RAPL needs a permission fix.** Since Linux 5.10 every powercap `energy_uj` is
`0400 root:root`. The exporter runs as uid 65534, gets EACCES, and node-exporter
swallows it: `node_scrape_collector_success{collector="rapl"}` stays `1` while
`node_rapl_*` is simply absent. The fix (in `helmvalues.yaml`,
`prometheus-node-exporter.permissionInitContainer`) is a one-shot init
container (uid 0, all capabilities dropped except `CHOWN`) that chgrps only the
`energy_uj` files to gid 9100 and adds `g+r`; the exporter runs with
`runAsGroup: 9100` and stays non-root. Non-root + `CAP_DAC_READ_SEARCH` does not
work (Kubernetes grants no ambient capabilities), and running the exporter as
root would expose every root-only host file under its `/host/root` mount.
Sysfs ownership resets at reboot; the init container re-runs when the pod
sandbox is recreated. `NodeRAPLMetricsMissing` fires if it ever stops working.

### Baseline at authoring (2026-09-28 .. 10-04, nodes 01/02/03)

| | p50 | p95 | p99 | max |
|---|---|---|---|---|
| Package temp °C | 51 / 67 / 64 | 68 / 88 / 77 | 79 / 96 / 87 | 95 / 102 / 103 |
| NVMe composite °C (max) | | | | 44.85 / 47.85 / 44.85 |

Package peaks are **spikes**: the longest unbroken run above 90 °C was 2.5 min,
above 100 °C 1 min. Throttle events per 24 h: node 01 ~60-280, node 02 32 to
32 000 (bursty), node 03 <= 11. Package power at idle: ~15 W per node (psys ~30 W).
PL1 = PL2 = 64 W on all three nodes (`constraint_{0,1}_power_limit_uw`).

### Rules and thresholds

| Alert | Condition | Severity | 7-day backtest |
|---|---|---|---|
| `NodeCPUPackageHot` | 5m-avg package > 90 °C for 10m | warning | 0 |
| `NodeCPUPackageHot` | 2m-avg package > 100 °C for 5m | critical | 0 |
| `NodeCPUThermalCritAlarm` | `node_hwmon_temp_crit_alarm_celsius == 1` for 1m | critical | 0 |
| `NodeCPUThermalThrottling` | `increase(..._throttles_total[15m]) > 100` for 30m, `keep_firing_for: 30m` | warning | 5 episodes, all node 02 |
| `NodeNVMeHot` | composite > 65 °C for 10m | warning | 0 |
| `NodeNVMeHot` | composite >= the drive's WCTEMP for 5m | critical | 0 |
| `NodeCPUPackagePowerAtCap` | package > 58 W (90 % of the 64 W cap) for 15m | info | n/a (no RAPL history) |
| `NodeRAPLMetricsMissing` / `NodeCoretempMetricsMissing` / `NodeNVMeTempMetricsMissing` | node-exporter up on a node but the series absent, 30m | warning | 0 (RAPL guard: would have fired on all 3 nodes for the whole window before the fix) |

Why the temperature rules average: on a sensor this spiky, a raw
`> 90 for: 10m` never fires, because one dipped sample resets the pending
timer. Averaging bridges single dips; a sustained hot period still fires.
`NodeCPUPackageHot` replaced `NodeCPUTemperatureHigh`/`Critical` (raw
`x86_pkg_temp`, same sensor), so a hot package pages once.

`NodeCPUThermalThrottling` is expected to fire on node 02 until the power
caps land. That is a true signal. The fix is power or cooling, not a pod limit.

### Follow-ups

- **Power caps:** a `talos-sysfs-power-caps` maintenance plan (not yet
  written as of 2026-10-04) will lower PL1. Retune `NodeCPUPackagePowerAtCap`
  to ~90 % of the new cap **in the same commit**.
- **BIOS:** a BIOS-level fan/power-limit follow-up for the NUCs (node 02
  in particular) after the caps are measured.

### Diagnose

```bash
# Package watts / temps / throttle events per node
rate(node_rapl_package_joules_total[5m])
node_hwmon_temp_celsius{chip="platform_coretemp_0",sensor="temp1"}
increase(node_cpu_package_throttles_total[15m])
# RAPL permission state on a node (expect -r--r----- 0 9100)
talosctl -n <node-ip> ls -l /sys/class/powercap/intel-rapl:0/ | grep energy_uj
# Current power limits
talosctl -n <node-ip> read /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw
```

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
# Via its HTTPRoute (envoy-internal)
# https://kibana.${SECRET_DOMAIN}

# Via port-forward
kubectl port-forward -n monitoring svc/kibana-kb-http 5601:5601 &
# Open http://localhost:5601
```

### Log Investigation Workflow

> **Pipeline healthy but one producer is drowning it?** That is a different
> problem from the ingestion failures below, and it has its own SOP:
> [`docs/sops/log-volume-runaway.md`](log-volume-runaway.md) — attributing volume
> by namespace/pod, telling a mislabelled deprecation stream from a real error
> stream, pricing it against the 14d DLM window, and the ordered remediation menu.

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
# Access via its HTTPRoute (envoy-external)
# https://kuma.${SECRET_DOMAIN}

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

## Blackbox Exporter (synthetic DNS + HTTPS route probes)

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
# Access via its HTTPRoute (envoy-internal)
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

Known CronJobs in this cluster (this list has drifted before — `kubectl get
cronjobs -A` is the source of truth; ~22 manifests exist under
`kubernetes/apps/`):
- `storage/daily-backup-all-volumes` (Longhorn backups, daily 3:00 AM; owned by the
  Longhorn RecurringJob of the same name, `kubernetes/apps/storage/longhorn/app/recurring-backup-job.yaml`)
- `kube-system/descheduler` (rescheduling optimization)
- `kube-system/authentik-channels-cleanup` (django-channels message prune, every 6h)
- `kube-system/authentik-db-probe` (audit-log freshness gauges → Pushgateway, hourly :17)
- `backup/icloud-backup-freshness` (iCloud photo-backup file-recency gauges → Pushgateway, hourly :23)
- `backup/icloud-sync-probe` (iCloud sync-health from icloud-docker pod logs → Pushgateway, every 10 min)
- `media/media-intake-watcher` (automatic JDownloader intake, every 30 min → Pushgateway)
- `databases/sweep-heartbeat`, `monitoring/obs-recovery`, `ai/openclaw-probe`,
  `ai/paperclip-backup-cleanup`, `home-automation/frigate-nvr` restart,
  `office/mealie` shopping-sync, tube-archivist maintenance

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

### Chart-bump rollout noise — expected transient signals, NOT a broken chart

`security_ref: F-23caf8d0`

**Every kube-prometheus-stack chart bump emits warnings that look like a
configuration break and are not one.** The risk this subsection exists to
prevent is a *false rollback*: reverting a perfectly healthy chart because the
rollout narrated itself alarmingly.

Observed on the `nightly:2026-09-07` window applying chart `89.2.2 → 89.2.3`
(`85a1dc6c`), and expected on every subsequent bump:

| Signal | Where | What it actually is |
|---|---|---|
| `InvalidConfiguration ... context canceled` on ServiceMonitors (seen on `kube-prometheus-stack-operator` and `uptime-kuma`) | operator log / events | the **outgoing** pod's client teardown — its watch context is cancelled mid-reconcile as it shuts down. No ServiceMonitor was edited |
| readiness-probe connection refused | events on the old operator pod | the same teardown: the probe races the terminating pod |

Both are emitted by the pod that is **going away**, not by the incoming one.
Neither indicates that any `ServiceMonitor` is malformed.

**Do not revert on these alone. Verify the outcome instead** — the rule is
`verification-contents-not-shape`: assert the stack's post-roll state, not the
absence of scary log lines.

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &

# 1. The two ServiceMonitors that warned must be scraping. Expect health=up.
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import sys, json
t = json.load(sys.stdin)['data']['activeTargets']
print(f'targets {len(t)} total, {sum(1 for x in t if x[\"health\"]==\"up\")} up')
for x in t:
    j = x['labels'].get('job','')
    if 'kube-prometheus-stack-operator' in j or 'uptime-kuma' in j:
        print(' ', j, x['health'])"

# 2. The rule set must be intact and every group healthy.
curl -s http://localhost:9090/api/v1/rules | python3 -c "
import sys, json
g = json.load(sys.stdin)['data']['groups']
r = [x for gg in g for x in gg['rules']]
print('groups', len(g), 'rules', len(r), 'health!=ok', sum(1 for x in r if x.get('health') != 'ok'))"
```

Healthy result: **every** target `up`, and `health!=ok` is **0**.

Measured at the 89.2.2→89.2.3 bump: 97/97 targets up, 113 groups / 456 rules,
0 unhealthy. Re-measured 2026-09-07 after the roll settled: 99/99 up, still 113
groups / 456 rules, 0 unhealthy. **Treat the totals as drifting baselines, not
constants** — targets legitimately grow as apps are added. The invariants are
"all up" and "0 unhealthy", not any particular count.

Escalate only if a ServiceMonitor is still `down` after the new operator pod is
`Ready`, or if the rule-group count drops — those are real breaks, and the
transient warnings above are not.

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

---

## Version History

- `2026.09.28`: Pushgateway pusher table + Known CronJobs: added `media/media-intake-watcher` (automatic JDownloader intake, `media-intake-alerts.yaml`).
- `2026.09.28`: Alert Authoring Rules #5 — duplicate series during an exporter overlap
  (e.g. two kube-state-metrics pods mid-rollout) break bare `on()`/`group_left` joins with
  "found duplicate series for the match group"; aggregate the one side with
  `max by (<on-labels>)` first (`c430a771`).
- `2026.09.20`: Added "Alert Authoring Rules" — the four ways an alert can be
  loaded, healthy and useless (missing `release` label; no `absent()` guard;
  `absent()` AND-ed with a labelled vector without `on()`, which is permanently
  inert; and accepting an empty result as proof). Includes the repo-wide audit
  (57 rule files / 268 rules: 25 bare guards, 0 broken) and why it must be run by
  parsing the YAML rather than grepping (F-91a99762).
- `2026.09.15`: CronJob name corrected — `storage/daily-backup-all-volumes`
  (owned by the Longhorn RecurringJob of the same name; `backup-of-all-volumes`
  returns `NotFound`). Added "CRD ownership: `monitoring.coreos.com` has TWO
  writers" under Prometheus: otel-operator's `prometheus-crds` subchart
  (`crds/`-dir provenance, not release resources) re-stamps four CRDs to
  operator-version 0.92.0 on every bump; durable fix `crds.installPrometheus:
  false` on the otel HR, no cascade-delete risk (plan
  `prometheus-crd-ownership`, F-a85e8943).
- earlier: `git log -- docs/sops/monitoring.md`.
