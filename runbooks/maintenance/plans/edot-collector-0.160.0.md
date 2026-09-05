---
plan_id: edot-collector-0.160.0
component: edot-collector
pr: null                          # Renovate PR number not supplied with this
                                  # held update; verify against an open PR
                                  # titled "otel/opentelemetry-collector-contrib"
                                  # before executing — merge that PR instead of
                                  # a hand-edit if one exists, same verification.
kind: image
current: "0.158.0"
target: "0.160.0"
update_type: minor                # 0.x line: minor digit is semver-major-equivalent
risk: medium
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - deployment/edot-collector
    - configmap/edot-collector-config      # inspected only, not edited by this plan
    - pvc/edot-collector-queue              # RWO Longhorn, Recreate strategy already set
  shared: []                        # edot-collector does not restart another
                                    # piece of shared infra (ingress/cert-manager/
                                    # cni/coredns/shared-db/longhorn control plane)
                                    # BUT it IS itself the sole log+metric+trace
                                    # ingestion path for every namespace in the
                                    # cluster — see Interference notes.
depends_on: []
conflicts_with: []
security_ref: null                # no CVE driver; AR-072 is a house-rule gate,
                                  # not a vulnerability finding — see Summary
capability_change: false          # no user-visible behaviour change; internal
                                  # ingestion pipeline only
rollback_class: git-revert        # image tag only; config unchanged; bbolt queue
                                  # schema unchanged between 0.158/0.159/0.160
finding_refs: []
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md         # "ES Rejected Documents" + edot-collector recipes
generated: "2026-09-05"
---

# edot-collector: image 0.158.0 → 0.160.0 (0.x minor-line move)

## 1) Summary & why held

The auto-updater held this because at the `0.x` release line the **minor**
digit is OpenTelemetry Collector's breaking-change digit (there is no separate
major yet) — `0.158.0 → 0.160.0` crosses two such minors (`0.159.0`,
`0.160.0`), so `auto-update.py`'s policy correctly treats it as non-safe and
routes it here rather than auto-merging.

**Investigation finding: this specific bump is low-risk in practice.** I read
the upstream `CHANGELOG.md` for both `v0.159.0` and `v0.160.0`
(open-telemetry/opentelemetry-collector-contrib) against every component our
`otel.yml` actually uses — `elasticsearchexporter`, `transformprocessor`,
`filterprocessor`, `cumulativetodeltaprocessor`, `otlpreceiver`,
`countconnector`, `prometheusexporter`, `extension/file_storage`,
`memorylimiterprocessor`, `batchprocessor` — and found **zero breaking changes
or config-key renames/removals** touching any of them. The only breaking
entries in either release are unrelated to our config: dynamic-sampling
processor rule-name reservation, `fileconsumer`'s `ordering_criteria::top_n: 0`
semantics, and removal of the deprecated `kafkatopicsobserver` extension — we
run none of these. `0.160.0`'s only cross-cutting change is "Increase minimum
Go version to 1.26" (build-time only, no runtime effect).

**One directly relevant, net-positive change** — `extension/file_storage`
(0.160.0, PR #49735):

> "Fix nil pointer crash when bbolt database compaction fails during startup
> after database corruption. The file_storage extension now catches panics
> during on_start compaction and returns an error instead of crashing the
> collector."

Our `file_storage/queue` extension (`configmap.yaml` lines 22-37) runs
`compaction.on_start: true` specifically because the sending-queue exists to
survive an ES outage without data loss (2026-08-16 incident, see the comment
block at the top of the configmap) — this fix directly hardens the failure
mode our own design leans on. It is a reason to take the bump, not a new risk.

**Relationship to AR-072**: AR-072 ("opentelemetry", accepted 2026-08-17,
review-by 2026-09-15) is a **house-rule gate**, not a CVE/vulnerability
acceptance — its justification text is: *"otel operator + collector 0.154.0
CVE rows: edot config must be re-validated before every roll (house rule);
bump is window-work."* This plan **runs under AR-072**, it does not supersede
it: the pre-check in §2 is exactly the re-validation AR-072 requires, and
routing this through the window system (rather than auto-merge) is what
satisfies "bump is window-work." Nothing here changes AR-072's scope or
review-by date.

**Risk is set to `medium`, not `low`**, despite the clean release-note diff,
because of blast radius and failure *mode*, not likelihood: edot-collector is
the only ingestion path for every namespace's logs/metrics/traces into
Elasticsearch, it is a single replica, and its failure mode is **silent** — a
bad config or a subtly-changed exporter default does not page, it just stops
counting (see `docs/sops/monitoring.md` "ES Rejected Documents"). A
config-validation pre-check and a contents-based (not shape-based)
post-verification are mandatory regardless of how clean the changelog reads.

## 2) Pre-checks

```bash
# 2.1 — confirm target tag is published (already verified during planning:
# otel/opentelemetry-collector-contrib:0.160.0, digest
# sha256:799dc6cf12c96192af37b5bdba804da8c10b3bc563b43cb90c3f3c58d9572ad6,
# pushed 2026-09-02)
curl -s "https://hub.docker.com/v2/repositories/otel/opentelemetry-collector-contrib/tags/0.160.0" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['name'],d['last_updated'],d['digest'])"

# 2.2 — cluster is currently healthy on 0.158.0 (baseline before touching anything)
kubectl get deployment edot-collector -n monitoring
kubectl get pods -n monitoring -l app=edot-collector
kubectl logs -n monitoring -l app=edot-collector --tail=5

# 2.3 — HARD PRE-CHECK: validate the (unchanged) live config against the NEW
# binary before rolling anything. A bad config crashloops the entire
# observability ingest path (logs+metrics+traces, cluster-wide) — this is
# non-negotiable, not a nice-to-have.
kubectl get configmap edot-collector-config -n monitoring -o jsonpath='{.data.otel\.yml}' > /tmp/edot-otel.yml
kubectl run edot-validate-0160 --rm -i --restart=Never \
  --image=otel/opentelemetry-collector-contrib:0.160.0 \
  --overrides='{"spec":{"containers":[{"name":"edot-validate-0160","image":"otel/opentelemetry-collector-contrib:0.160.0","command":["/otelcol-contrib","validate","--config=/config/otel.yml"],"env":[{"name":"ES_PASSWORD","value":"dummy-validate-only"}],"volumeMounts":[{"name":"cfg","mountPath":"/config"}]}],"volumes":[{"name":"cfg","configMap":{"name":"edot-collector-config"}}]}}'
# Expect: process exits 0, no "invalid configuration" errors. If it fails, STOP —
# do not proceed to §3. (This also re-confirms AR-072's "re-validate before
# every roll" house rule.)

# 2.4 — capture a pre-change baseline for the CONTENTS assertion in §4
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/tmp/pf-prom.log 2>&1 &
sleep 2
curl -s 'http://localhost:9090/api/v1/query' --data-urlencode \
  'query=sum(increase(otelcol_exporter_sent_log_records_total{exporter="elasticsearch/logs"}[15m]))' \
  | python3 -m json.tool   # record this number as PRE_LOGS_BASELINE
curl -s 'http://localhost:9090/api/v1/query' --data-urlencode \
  'query=sum(increase(otelcol_exporter_sent_metric_points_total{exporter="elasticsearch/metrics"}[15m]))' \
  | python3 -m json.tool   # record this number as PRE_METRICS_BASELINE
kill %1 2>/dev/null
```

If §2.3 fails, this plan is blocked — do not bump. If it passes, the config is
compatible with 0.160.0 and only the image tag needs to change.

## 3) Steps (GitOps)

1. Silence expected rollout noise (4h TTL) before touching anything:
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/tmp/pf-am.log 2>&1 &
   NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
   END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
   curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
     "matchers":[{"name":"namespace","value":"monitoring","isRegex":false,"isEqual":true},
                 {"name":"alertname","value":"EdotCollectorDown|OtelDaemonCollectorDown|OtelCollectorExportFailed|OtelCollectorRecordsRefused|OtelCollectorQueueFull|EdotCollectorESAuthError|EsMetricsIngestionStalled|EsLogIngestionStalled|EsExportQueueStuckFull","isRegex":true,"isEqual":true}],
     "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"operator",
     "comment":"edot-collector 0.158.0->0.160.0 upgrade — suppressing expected rollout noise. auto-expires 4h"}'
   runbooks/update-marker.sh add edot-collector monitoring 4 "0.158.0->0.160.0 upgrade"
   ```

2. Edit the image tag (only change — config is validated compatible in §2.3):
   ```
   kubernetes/apps/monitoring/edot-collector/app/deployment.yaml
     image: otel/opentelemetry-collector-contrib:0.158.0
   ->
     image: otel/opentelemetry-collector-contrib:0.160.0
   ```
   Also bump the rollout-revision annotation for traceability:
   ```
   cberg.dev/rollout-revision: "2026-08-16.1"
   ->
   cberg.dev/rollout-revision: "<today's date>.1"
   ```

3. Commit and push (GitOps only — no direct cluster edit):
   ```bash
   git add kubernetes/apps/monitoring/edot-collector/app/deployment.yaml
   git commit -m "chore(monitoring): edot-collector 0.158.0 -> 0.160.0 (window plan edot-collector-0.160.0)"
   git push
   ```

4. Let Flux reconcile (interval 30m on this Kustomization, or force it since
   this is an attended window action):
   ```bash
   flux reconcile kustomization edot-collector -n flux-system --with-source
   ```

5. Watch the `Recreate` rollout (single replica, RWO Longhorn PVC — the pod
   MUST fully terminate and release the volume before the new one starts;
   this is by design, see the `strategy` comment in `deployment.yaml`):
   ```bash
   kubectl rollout status deployment/edot-collector -n monitoring --timeout=180s
   kubectl get pods -n monitoring -l app=edot-collector -o wide
   ```

## 4) Verification

Floor checks (shape — necessary but not sufficient):
```bash
kubectl get deployment edot-collector -n monitoring -o jsonpath='{.status.readyReplicas}{"\n"}'
kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='{.items[0].spec.containers[0].image}{"\n"}'
# confirm running image is actually 0.160.0 (imageID, not just the tag string)
kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'
kubectl logs -n monitoring -l app=edot-collector --tail=30    # no crashloop, no "invalid configuration"
POD=$(kubectl get pod -n monitoring -l app=edot-collector -o name | head -1)
kubectl port-forward -n monitoring ${POD} 13133:13133 >/tmp/pf-edot.log 2>&1 &
sleep 2
curl -s http://localhost:13133/    # health_check extension: expect 200
kill %1 2>/dev/null
```

**CONTENTS ASSERTION (mandatory — this is an ingestion pipeline; a healthy pod
shipping nothing is a silent-blind failure, not a pass):**

```bash
# 1) Self-telemetry: exporter is actively SENDING, post-rollout, non-zero —
# compare against PRE_LOGS_BASELINE / PRE_METRICS_BASELINE from §2.4
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/tmp/pf-prom.log 2>&1 &
sleep 2
curl -s 'http://localhost:9090/api/v1/query' --data-urlencode \
  'query=sum(increase(otelcol_exporter_sent_log_records_total{exporter="elasticsearch/logs"}[15m]))' \
  | python3 -m json.tool
curl -s 'http://localhost:9090/api/v1/query' --data-urlencode \
  'query=sum(increase(otelcol_exporter_sent_metric_points_total{exporter="elasticsearch/metrics"}[15m]))' \
  | python3 -m json.tool
# PASS: both > 0 and within a plausible band of the pre-bump baseline
# (not just "> 0" — a trickle would still be a regression from a healthy rate).

# 2) Per-document outcome — proves ES is not silently REJECTING what arrives
# (the managedFields-class failure: bulk request 200s, individual docs 4xx).
# This is the metric class the 0.159/0.160 changelog gave no reason to expect
# a regression in, but it is exactly the SOP's contents assertion for this
# component (docs/sops/monitoring.md "Metric-based rejection assertion"):
curl -s 'http://localhost:9090/api/v1/query' --data-urlencode \
  'query=sum by (outcome) (increase(otelcol_elasticsearch_docs_processed_total{outcome!~"success|retried"}[15m]))'
kill %1 2>/dev/null
# PASS: 0 (or absent, since failure-outcome series are only born on first
# rejection). A non-zero "failed_client"/"failed_server" here means the
# transform/strip-k8s-managedfields path stopped matching under 0.160 (the
# known repo trap) even though the changelog gave no reason to expect it —
# STOP and roll back, do not investigate live with logs going blind further.

# 3) Ground truth in Elasticsearch itself — new documents actually landed
# with a timestamp AFTER the rollout (not just "the exporter said it sent"):
kubectl port-forward -n monitoring svc/elasticsearch-es-http 9200:9200 >/tmp/pf-es.log 2>&1 &
sleep 2
ROLLOUT_TS="<fill in: kubectl get pod ... -o jsonpath='{.status.startTime}' from the new pod>"
curl -s -u elastic:$(kubectl get secret elasticsearch-es-elastic-user -n monitoring -o jsonpath='{.data.elastic}' | base64 -d) \
  -k "https://localhost:9200/logs-generic-default/_count" -H 'Content-Type: application/json' -d '{
  "query": {"range": {"@timestamp": {"gte": "'"$ROLLOUT_TS"'"}}}
}'
kill %1 2>/dev/null
# PASS: count > 0. A zero here is a hard fail regardless of what the pod/health
# endpoint say — this is the actual "are we blind" question.

# 4) k8s Event managedFields transform still applies (the named repo trap) —
# confirm no fresh document_parsing_exception since rollout:
kubectl logs -n monitoring -l app=edot-collector --since=10m | grep -c "document_parsing_exception\|failed to index document"
# PASS: 0
```

## 5) Rollback

Image-tag-only change, same config, same bbolt queue schema across
0.158/0.159/0.160 — a clean git revert:

```bash
git revert --no-edit <bump-commit-sha>
git push
flux reconcile kustomization edot-collector -n flux-system --with-source
kubectl rollout status deployment/edot-collector -n monitoring --timeout=180s
# confirm rollback landed
kubectl get pods -n monitoring -l app=edot-collector -o jsonpath='{.items[0].spec.containers[0].image}{"\n"}'
```

The persistent sending-queue (Longhorn PVC `edot-collector-queue`) is
untouched by either direction of this change — nothing needs to be drained or
recreated. After rollback, re-run the §4 CONTENTS ASSERTION block to confirm
ingestion resumed on 0.158.0.

On success: restore alert state —
```bash
runbooks/update-marker.sh clear edot-collector
# delete the Alertmanager silence created in §3.1 (curl -X DELETE .../silences/<id>)
```

## 6) Interference notes

- **This component IS the cluster's shared observability ingestion path**,
  even though `touches.shared` lists nothing else it *restarts*: every
  namespace's OTLP logs/metrics/traces and the Talos kmsg UDP stream funnel
  through this single Deployment. A bad rollout does not just affect
  "monitoring" — it silently blinds alerting/debugging for every other app in
  the cluster for the duration. Schedule with nothing else risky in the same
  window if avoidable, so that if something else misbehaves during the window,
  the observability path used to diagnose it is not also mid-upgrade.
- **Single replica + `Recreate` strategy + RWO Longhorn PVC**: the old pod
  must fully terminate before the new one starts. Expect a genuine ingestion
  gap of tens of seconds during the swap — this is normal and is what the
  on-disk sending-queue (bbolt, `file_storage/queue`) exists to absorb on the
  OTLP-producer side; producers see backpressure/refused, not silent drop
  (`block_on_overflow: true` in every ES exporter's `sending_queue`).
- **edot images are minimal (no `cat`/`curl`/`wget`)** — every verification
  step above uses `kubectl port-forward` + local `curl`, never `kubectl exec`.
- **`otel-operator` (the OpenTelemetry Operator / `opentelemetry-kube-stack`
  chart) and its DaemonSet collector (`otel-operator-daemon`) are a separate
  HelmRelease and are NOT touched by this plan** — confirmed only one
  reference to `otel/opentelemetry-collector-contrib:0.158.0` in the repo
  (`edot-collector/app/deployment.yaml`), so there is no second collector
  instance to keep in lockstep with this bump.
- No node reboot, no shared ingress/cert-manager/CNI/CoreDNS/shared-DB
  perturbation — this Kustomization only `dependsOn: [elasticsearch]`, which
  is unaffected by this change.
- AR-072 review-by date is 2026-09-15 — if this plan slips past that date,
  re-run `policy-cli.py risk show AR-072` before executing in case the
  operator re-scoped or retired it at review.
