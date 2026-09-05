# SOP: JVM Fixed-Heap Memory Alerts

> Description: Why `ContainerMemoryNearLimit`/`ContainerMemoryLimitImminent` fire permanently on any JVM started with `-Xms == -Xmx`, why that is a structural property and not an incident, what to alert on instead, and how to size + suppress correctly without blinding the leak detectors.
> Version: `2026.09.05`
> Last Updated: `2026-09-05`
> Owner: `platform-monitoring`

---

## 1) Description

A JVM started with a fixed heap (`-Xms<n> -Xmx<n>`, i.e. min == max) commits and
touches that entire heap at startup, independent of load. Container RSS /
working-set then sits at a permanently high, flat ratio of the container's
memory limit — not because anything is wrong, but because that is what a fixed
heap *is*. `ContainerMemoryNearLimit` (`docs/sops/monitoring.md`,
`kubernetes/apps/monitoring/kube-prometheus-stack/app/container-memory-alerts.yaml`)
was written to catch *rising* usage against a limit; against a fixed-heap JVM
its `> 0.90` condition can be permanently true even in a container sized
correctly, and an alert that fires forever trains the operator to stop reading
it — which is the actual damage (see `F-779662fd`, and its predecessor
`F-9188fdb8` on how "the script didn't re-emit it" got mistaken for "fixed").

This SOP does not ask for a new metric pipeline to exist before it is useful:
Section 4 gives the sizing rule and the correct suppression pattern using only
signals already in this cluster; Section 4 also names the GC/latency signals
that are the *right* alert once instrumented, and flags that none of them are
wired up yet.

- Scope: any container running a JVM (or JVM-based runtime — OpenSearch is a
  JVM) started with a fixed heap, in this cluster or on adjacent
  infrastructure whose memory behaves the same way.
  - In-cluster, confirmed fixed-heap (`Xms == Xmx`) at time of writing:
    - `monitoring/elasticsearch-es-default-0` (Elasticsearch 8.19.20) — `-Xms4g -Xmx4g`, limit `8Gi`
    - `security/wazuh-indexer-0` (OpenSearch, wazuh-indexer 4.14.7) — `-Xms2g -Xmx2g`, limit `4Gi`
    - `download/tube-archivist-elasticsearch` (Elasticsearch 8.19.0) — `-Xms1g -Xmx1g`, limit `2Gi`
  - Adjacent, not a Kubernetes container: the UniFi Network-app JVM on the
    physical UDM gateway (DMP-CBERG) runs a pinned heap and shows the same
    permanently-high-and-flat memory shape. It cannot trip
    `ContainerMemoryNearLimit` (no cgroup, no cAdvisor) but it is the same
    physics, and this cluster already drew the identical structural/incident
    split for it in `kubernetes/apps/monitoring/unpoller/app/prometheusrule.yaml`
    (`UnifiDeviceHighMemory` vs `UnifiGatewayMemoryPinned`, commit `dd292afb`)
    — cited here as prior art the JVM case should match, not duplicated.
- Prerequisites: read access to `kubectl top`, Prometheus
  (`docs/sops/monitoring.md` port-forward recipe), and the container's
  `JAVA_OPTS`/`ES_JAVA_OPTS`/`OPENSEARCH_JAVA_OPTS` env var.
- Out of scope: JVMs *without* a pinned heap (default ergonomics, or
  `-XX:MaxRAMPercentage` without `Xms==Xmx`) — those legitimately grow and
  shrink, and `ContainerMemoryNearLimit`/`ContainerMemoryLeakPredicted` are
  fully meaningful for them as-is. Do not apply this SOP's suppression
  pattern to a container you haven't confirmed is fixed-heap.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace(s) | `monitoring`, `security`, `download` |
| Source of truth | `kubernetes/apps/monitoring/elasticsearch/app/elasticsearch.yaml`, `kubernetes/apps/security/wazuh/app/wazuh-indexer-statefulset.yaml`, `kubernetes/apps/download/tube-archivist/app/elasticsearch-helmrelease.yaml` |
| Alert that is structurally noisy here | `ContainerMemoryNearLimit` / `ContainerMemoryLimitImminent` (`container-memory-alerts.yaml`) |
| Alert that stays trustworthy here | `ContainerMemoryLeakPredicted` (RSS-slope based — a correctly sized fixed heap has no rising floor) |
| Sizing rule in use | container limit ≈ **2× `-Xmx`** (50% heap-to-container ratio) |
| Live snapshot 2026-09-05 (`kubectl top`) | ES(monitoring) 5874Mi/8192Mi = 71.7% · wazuh-indexer 2582Mi/4096Mi = 63.0% · tube-archivist-ES 1781Mi/2048Mi = **87.0%** (see §4, this one is under-sized) |

---

## 3) Blueprints

- `kubernetes/apps/monitoring/elasticsearch/app/elasticsearch.yaml` — `ES_JAVA_OPTS: "-Xms4g -Xmx4g"`, `resources.limits.memory: 8Gi`. The in-file comment already documents the 6Gi→8Gi fix and is the primary precedent this SOP generalizes.
- `kubernetes/apps/security/wazuh/app/wazuh-indexer-statefulset.yaml` — `OPENSEARCH_JAVA_OPTS: "-Xms2g -Xmx2g"`, `resources.limits.memory: 4Gi`.
- `kubernetes/apps/download/tube-archivist/app/elasticsearch-helmrelease.yaml` — `ES_JAVA_OPTS: "-Xms1g -Xmx1g"`, `resources.limits.memory: 2Gi`.
- `kubernetes/apps/monitoring/kube-prometheus-stack/app/container-memory-alerts.yaml` — the generic cluster-wide alert set; do not edit thresholds here to fix a single JVM (see §4).
- `kubernetes/apps/monitoring/unpoller/app/prometheusrule.yaml` — the non-container prior art (`UnifiDeviceHighMemory` / `UnifiGatewayMemoryPinned` split) this SOP's alerting split mirrors.

```yaml
# Minimal fixed-heap sizing pattern used by all three in-cluster examples
env:
  - name: ES_JAVA_OPTS        # or OPENSEARCH_JAVA_OPTS / JAVA_OPTS
    value: "-Xms<N>g -Xmx<N>g"   # min == max — this is what makes it "fixed-heap"
resources:
  requests:
    memory: "<2N>Gi"           # start at 2x heap; see §4 for the overhead math
  limits:
    memory: "<2N>Gi"
```

---

## 4) Operational Instructions

### 4a. Identify a fixed-heap JVM before applying anything in this SOP

```bash
kubectl get pod -n <ns> <pod> -o jsonpath='{.spec.containers[*].env}' | grep -io "JAVA_OPTS[^,]*"
```

If `-Xms` and `-Xmx` are equal, this SOP applies. If they differ (or only
`-Xmx` is set, or `MaxRAMPercentage` is used instead), it does not — treat
`ContainerMemoryNearLimit` there as fully meaningful.

### 4b. Why RSS-vs-limit is the wrong signal here

`container_memory_working_set_bytes / kube_pod_container_resource_limits`
answers "how full is the container", not "is the JVM healthy". A fixed-heap
JVM is *supposed* to be full — that is what committing `-Xmx` up front means.
The ratio cannot distinguish:

- **Healthy and full**: heap resident, old-gen GC reclaiming normally, no
  allocation failures, request latency flat. This is steady state for all
  three in-cluster examples today.
- **Thrashing**: the JVM is spending most of its wall-clock time in Full GC
  trying to free space it cannot free, throughput collapses, and — the
  dangerous part — **it does not OOM**, because the container was sized to
  hold the heap plus its own overhead, so RSS never actually crosses the
  cgroup limit. Kubernetes never restarts it. This is the exact shape of the
  UniFi Network-app Full-GC death spiral this cluster has already hit on the
  UDM gateway (`unpoller` `UnifiGatewayMemoryPinned` comment, commit
  `dd292afb`) — the in-cluster JVMs have not shown this yet, but nothing here
  would currently catch it if they did (see 4c).

Both states can sit at 70-90% of the limit indefinitely. Only one is a problem.

### 4c. What to alert on INSTEAD (and what is missing today)

None of these are instrumented in this cluster yet — that is a real gap this
SOP surfaces, not a claim that it's covered:

1. **GC time ratio / old-gen collection frequency** — the direct signal for
   thrash. Requires an exporter: Elasticsearch/OpenSearch expose
   `_nodes/stats/jvm` natively (`gc.collectors.old.collection_time_in_millis`,
   `collection_count`) and `prometheus-community/elasticsearch_exporter`
   turns that into `elasticsearch_jvm_gc_collection_seconds_sum{gc="old"}`.
   For a generic JVM (none of the three here are generic, but if one is added
   later) a JMX-exporter sidecar exposes the equivalent `jvm_gc_collection_seconds`.
   Recommended alert once wired: old-gen GC time consuming more than ~50% of
   wall clock over a 5m window —
   `rate(elasticsearch_jvm_gc_collection_seconds_sum{gc="old"}[5m]) > 0.5`.
2. **Allocation stall / circuit breaker trips** — ES/OpenSearch circuit
   breakers (`elasticsearch_breakers_tripped` via the exporter, or
   `_nodes/stats/breaker` directly) trip when the JVM cannot safely allocate;
   this fires *before* GC thrash becomes visible in latency and is a cleaner
   leading indicator than the heap ratio.
3. **Request/query latency and thread-pool rejections** — the application-level
   symptom of GC thrash. ES thread-pool queue/rejection counts
   (`elasticsearch_thread_pool_rejected_count`,
   `elasticsearch_thread_pool_queue_count`) turn "the JVM is unhappy" into
   "here is what users/consumers actually feel."
4. **Generic, exporter-free fallback available today**: cgroup PSI
   (`/sys/fs/cgroup/memory.pressure`, `full avg10`) inside the pod, or simply
   watching `kubectl top` for a *step change* rather than a *high plateau* —
   a fixed-heap JVM's RSS should be flat; a rising trend on a fixed heap
   (rather than a fixed offset above it) means non-heap growth, which is
   itself worth investigating (see 4d).

**`ContainerMemoryLeakPredicted` is not blinded by this and should stay ON**
for all three containers. It thresholds `predict_linear` on RSS growth, not
the static ratio — a correctly sized fixed-heap JVM has a flat RSS floor, so
the leak predictor should never trip for it. If it *does* trip on one of these
three, that is real signal (metaspace/off-heap growth — see 4d), not noise.

### 4d. Sizing the container limit relative to `-Xmx`

Limit = heap + everything the JVM allocates outside the heap:

- **Metaspace** — class metadata; default unbounded unless
  `-XX:MaxMetaspaceSize` is set (none of the three set it — check for
  class-loading leaks if this ever needs bounding).
- **Code cache** — JIT-compiled code, ~240Mi default cap since JDK 9
  (segmented code cache).
- **Direct/off-heap buffers** — for Elasticsearch/OpenSearch specifically,
  mmap'd Lucene segments (`node.store.allow_mmap`) are the dominant term:
  they are shared page cache, count toward `working_set_bytes`, and are
  reclaimable under pressure — but the kernel still has to *feel* pressure
  before reclaiming, so they read as permanently-high usage right up until
  the limit forces reclaim. This was the actual root cause the
  `elasticsearch.yaml` 6Gi→8Gi fix addressed: at 6Gi the 4Gi committed heap
  was already 67% of the limit before a single document was indexed, leaving
  no room for mmap'd segments and query/indexing buffers.
- **Thread stacks** — count × `-Xss` (1Mi default per thread); ES/OpenSearch
  run dozens of pooled threads, so tens of MiB, not negligible at the 1-2Gi
  scale these containers run at.

**The rule this cluster already converged on independently, twice**: container
limit ≈ **2× `-Xmx`** (50% heap-to-container ratio — this is also
Elasticsearch's own documented recommendation). All three in-cluster examples
sit at exactly this ratio (4g/8Gi, 2g/4Gi, 1g/2Gi) — but the live snapshot in
§2 shows it does **not** scale down safely: `tube-archivist-elasticsearch` is
at 87.0% (1781Mi/2048Mi) against the same 2× ratio that leaves the other two
at 63-72%, because metaspace/code-cache/thread-stack overhead is closer to a
*fixed absolute cost* than a fraction of heap — a 1Gi heap has much less
proportional headroom left for the same ~300-400MiB of fixed overhead than a
4Gi heap does. **Action from this SOP: raise `tube-archivist-elasticsearch`'s
limit from 2Gi to ~2.5-3Gi** (keep `-Xmx1g` — old-gen headroom is not the
problem here, container headroom is) the next time that file is touched, and
re-check the ratio with `kubectl top` after.

### 4e. Suppressing the structural alert without blinding yourself

**Do not** raise the cluster-wide `ContainerMemoryNearLimit` threshold above
0.90, and **do not** add a blanket `container!=""` exclusion for these three
names to the shared rule — both would blind the alert for every genuinely
leaking container (frigate is the reason this rule exists at all;
`docs/sops/frigate-memory-leak.md`).

Instead, scope the suppression to exactly these containers using an
Alertmanager silence/route matcher on `alertname` **and** `container`, not
`alertname` alone:

```bash
amtool silence add \
  alertname="ContainerMemoryNearLimit" \
  container=~"^(elasticsearch|wazuh-indexer|elasticsearch)$" \
  namespace=~"^(monitoring|security|download)$" \
  --comment "Fixed-heap JVM, structural per docs/sops/jvm-fixed-heap-memory-alerts.md — F-779662fd" \
  --duration 8760h
```

Record the justification in sweep policy for auditability. Note the current
limitation: `runbooks/policy-cli.py noise add --category recurring_alerts`
only matches on a single key (in practice `alertname`), so a suppression
entered there alone **would** be the blunt, blinding version — use it only as
the paper trail, with the Alertmanager silence above as the actual scoping
mechanism:

```bash
python3 runbooks/policy-cli.py noise add \
  --category recurring_alerts --match-key alertname \
  --match-value ContainerMemoryNearLimit \
  --note "Fixed-heap JVM containers only (elasticsearch/wazuh-indexer/tube-archivist-elasticsearch) — scoped via Alertmanager silence, NOT this alertname-wide entry. See docs/sops/jvm-fixed-heap-memory-alerts.md, F-779662fd."
```

If `policy-cli.py noise` ever gains multi-label matching, migrate this entry
to match `container` as well and drop the caveat.

---

## 5) Examples

### Example A: onboarding a new fixed-heap JVM

```bash
# 1. Confirm fixed heap
kubectl get pod -n <ns> <pod> -o jsonpath='{.spec.containers[*].env}' | grep -io "JAVA_OPTS[^,]*"
# -> "-Xms2g -Xmx2g" confirms fixed-heap

# 2. Size the container limit at 2x -Xmx as a starting point
#    resources.limits.memory: 4Gi

# 3. Watch working_set for 24-48h after rollout
kubectl top pod -n <ns> <pod>
# Expect: flat plateau, NOT a climb. A climb means the 2x ratio wasn't enough
# — go back to 4d, not straight to raising the limit blindly.

# 4. Scope the ContainerMemoryNearLimit suppression per 4e once confirmed flat.
```

### Example B: `tube-archivist-elasticsearch` at 87% (this cluster, today)

```bash
kubectl top pod -n download tube-archivist-elasticsearch-<hash>
# 8m   1781Mi   -> 1781/2048 = 87.0%, same 2x-heap ratio as the healthy two
# but with only ~13% headroom instead of ~28-37%.
# Fix: bump kubernetes/apps/download/tube-archivist/app/elasticsearch-helmrelease.yaml
#   resources.limits.memory: 1Gi -> ~2.5-3Gi (leave -Xmx1g alone)
```

---

## 6) Verification Tests

### Test 1: Confirm the container is genuinely flat, not climbing

```bash
# Prometheus query (port-forward per docs/sops/monitoring.md)
curl -s --data-urlencode 'query=predict_linear(container_memory_rss{namespace="monitoring",container="elasticsearch"}[24h], 48*3600) / on(namespace,pod,container) group_left kube_pod_container_resource_limits{resource="memory"}' \
  http://localhost:9090/api/v1/query | python3 -m json.tool
```

Expected:
- Projected ratio stays close to the current ratio (no meaningful growth).

If failed (projection climbs materially above current):
- `ContainerMemoryLeakPredicted` will trip on its own — do not suppress it.
  Investigate metaspace/off-heap growth per 4d before assuming it's noise.

### Test 2: Confirm the silence is scoped, not blanket

```bash
amtool silence query alertname="ContainerMemoryNearLimit"
```

Expected:
- Matcher includes `container=~"..."` restricted to the three named
  containers. A silence with only `alertname="ContainerMemoryNearLimit"` and
  no container/namespace matcher is wrong — it blinds frigate-class leaks too.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `ContainerMemoryNearLimit` fires on ES/wazuh-indexer/tube-archivist-ES | Expected — fixed heap, ratio structurally high | Confirm flat via Test 1; if flat, this is 4e's suppression case, not an incident |
| `ContainerMemoryLeakPredicted` fires on one of these three | Real: off-heap/metaspace growth on a container that should be flat | Investigate per 4d — do NOT suppress this alert, it's the one that still works |
| Request latency climbing while memory ratio flat/high | GC thrash without OOM — the dangerous case this SOP exists for | Check `_nodes/stats/jvm` GC counters directly (no exporter yet — see 4c); restart the pod to recover, then instrument GC metrics before it recurs |
| Silence expired and alert re-fires with no other symptoms | Normal — 8760h silence lapsed | Re-run 4e; confirm still flat first |

```bash
# Direct JVM GC stats without an exporter (works today, ES/OpenSearch only)
kubectl exec -n <ns> <pod> -- curl -s -k -u <user>:<pass> "https://localhost:9200/_nodes/stats/jvm?pretty" | grep -A5 '"old"'
```

---

## 8) Diagnose Examples

### Diagnose Example 1: distinguishing "healthy and full" from "thrashing"

```bash
kubectl top pod -n <ns> <pod>                      # ratio — cannot distinguish alone
kubectl exec -n <ns> <pod> -- curl -s -k -u <user>:<pass> \
  "https://localhost:9200/_nodes/stats/jvm?pretty" | grep -A6 '"old"'   # collection_count trend
kubectl logs -n <ns> <pod> --since=1h | grep -i "young\|old gc\|full gc"  # GC log lines if logged
```

Expected:
- `collection_count` for `old` GC increments slowly (single digits per hour
  at this cluster's event rate) → healthy and full.

If unclear:
- Compare against a `kubectl top` sample from an hour earlier. Ratio unchanged
  + GC count barely moving = healthy. Ratio unchanged + GC count climbing
  fast = thrashing without OOM — the case that RSS-vs-limit cannot see.

### Diagnose Example 2: UDM gateway analog (non-Kubernetes, cited for pattern parity)

```bash
unifictl local health get -o json | python3 -m json.tool
```

Expected:
- `wan`/`www`/`lan`/`wlan` subsystems all `ok`. If not, and
  `UnifiGatewayMemoryPinned` (unpoller) is also firing, follow that alert's
  documented recovery: `systemctl restart unifi.service` on the UDM.

---

## 9) Health Check

```bash
kubectl top pod -n monitoring -l app=elasticsearch --no-headers
kubectl top pod -n security -l app=wazuh-indexer --no-headers
kubectl get pods -n download -l app=tube-archivist-elasticsearch -o name 2>/dev/null \
  || kubectl get pods -n download | grep tube-archivist-elasticsearch
```

Expected:
- All three at or below their 2×-heap ratio, flat over successive checks.
  `tube-archivist-elasticsearch` specifically should move toward ~65-75%
  after the 4d limit bump lands — if it's still ~87% after that change,
  the bump didn't take (check the HelmRelease reconciled).

---

## 10) Security Check

```bash
grep -rn "Xmx\|Xms" kubernetes/ --include="*.yaml" | grep -v ".sops."
```

Expected:
- No JVM heap flags carry secrets or credentials (they never should — this is
  a sanity check that a future edit didn't inline something sensitive next to
  an env var block).
- Any Alertmanager silence created per 4e is time-bound (`--duration`, not
  indefinite) and carries a `--comment` naming this SOP and the finding ID,
  so it shows up in `amtool silence query` audits rather than aging out
  silently.

---

## 11) Rollback Plan

```bash
# Remove a silence created per 4e
amtool silence expire <silence-id>

# Revert a limit change (example: tube-archivist-elasticsearch)
git revert <commit-sha>   # or edit the HelmRelease back to the prior memory limit
git push
```

Flux reconciles the limit change automatically; no manual `kubectl edit` is
needed or permitted (GitOps-only per the repo's standard rules).

---

## 12) References

- `F-779662fd` — the finding this SOP closes.
- `F-9188fdb8` — why the earlier version of this gap was wrongly auto-closed by absence; the reason this SOP had to actually get written rather than assumed done.
- Commit `dd292afb` — `UnifiDeviceHighMemory` retune, the non-container prior art for this same structural/incident split.
- `kubernetes/apps/monitoring/elasticsearch/app/elasticsearch.yaml` — primary in-repo precedent (6Gi→8Gi fix comment).
- `kubernetes/apps/security/wazuh/app/wazuh-indexer-statefulset.yaml`
- `kubernetes/apps/download/tube-archivist/app/elasticsearch-helmrelease.yaml`
- `kubernetes/apps/monitoring/kube-prometheus-stack/app/container-memory-alerts.yaml`
- `kubernetes/apps/monitoring/unpoller/app/prometheusrule.yaml`
- `docs/sops/frigate-memory-leak.md` — why the generic alert must stay sharp for real leaks.
- `docs/sops/monitoring.md` — Prometheus/Alertmanager access patterns used throughout this SOP.
- `docs/sops/policy-cli.md` — `noise_suppressions` mechanics and its current single-key matching limitation (see 4e).

---

## Version History

- `2026.09.05`: Initial version. Closes `F-779662fd`. Documents the three in-cluster fixed-heap JVM containers, the sizing rule already converged on independently for two of them, flags `tube-archivist-elasticsearch` as under-sized against its own pattern (87% live), and defines the suppression pattern that keeps `ContainerMemoryLeakPredicted` sharp while retiring the structural noise from `ContainerMemoryNearLimit`.
