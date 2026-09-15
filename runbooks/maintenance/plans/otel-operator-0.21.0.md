---
plan_id: otel-operator-0.21.0
component: otel-operator               # HelmRelease name. The CHART is the umbrella
                                       # `opentelemetry-kube-stack` (subcharts: otel-crds,
                                       # prometheus-crds, opentelemetry-operator 0.119.0);
                                       # coverage.py keys the item on the HR name.
pr: null                               # no Renovate PR (checked `gh pr list --search
                                       # opentelemetry` 2026-09-15: none open)
kind: chart
current: "0.20.9"                      # helm release v23, deployed 2026-09-14 (961f0863)
target: "0.21.0"                       # released 2026-09-14 18:01 UTC, same day
update_type: minor
risk: low                              # HONEST, MEASURED: appVersion 0.154.0 and the
                                       # opentelemetry-operator subchart 0.119.0 are
                                       # IDENTICAL on both sides; all 8 CRDs byte-identical;
                                       # the rendered diff with OUR values is exactly two
                                       # `helm.sh/chart` label lines. See §1.
est_duration_min: 30                   # 5 pre-checks + 2 edit/commit + 5 reconcile & DS
                                       # roll + 10 settle (the ES contents assertion needs
                                       # a window that STARTS after the last pod is Ready)
                                       # + 8 verification
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/otel-operator
    - opentelemetrycollector/otel-operator-daemon          # gets the new helm.sh/chart label
    - daemonset/otel-operator-daemon-collector             # ROLLS: operator propagates CR
                                                           # labels into the pod template
                                                           # (measured: pod template carries
                                                           # helm.sh/chart=…-0.20.9 today)
    - deployment/otel-operator-opentelemetry-operator      # NOT rolled — its labels come
                                                           # from the SUBCHART (0.119.0,
                                                           # unchanged); pod is 7d old while
                                                           # the collector pods are 20h old,
                                                           # i.e. it did not roll on 0.20.9
                                                           # either. Hot-reloads the cert.
    - secret/otel-operator-opentelemetry-operator-controller-manager-service-cert  # REGENERATED
                                                           # on every helm upgrade
                                                           # (autoGenerateCert.recreate: true)
    - mutatingwebhookconfiguration/otel-operator-opentelemetry-operator-mutation    # caBundle
    - validatingwebhookconfiguration/otel-operator-opentelemetry-operator-validation
    - crd/{instrumentations,opampbridges,opentelemetrycollectors,targetallocators}.opentelemetry.io   # byte-identical
    - crd/{servicemonitors,podmonitors,probes,scrapeconfigs}.monitoring.coreos.com   # ORDERING-DEPENDENT
                                                           # (§2.6, §4.6, §6). 0.20.9 and 0.21.0
                                                           # ship byte-identical 0.92.0 copies, and
                                                           # this HR re-applies them via CreateReplace
                                                           # ONLY while `crds.installPrometheus` is
                                                           # unset — i.e. until plan
                                                           # prometheus-crd-ownership lands; after it
                                                           # this HR does not write them at all.
                                                           # Live 2026-09-15: 0.92.0, generation 30,
                                                           # origin otel-operator → a no-op re-apply.
                                                           # If kube-prometheus-stack-91.4.0 landed
                                                           # first (without that fix) the re-apply is
                                                           # a 0.94.0→0.92.0 DOWNGRADE: the accepted
                                                           # contention F-a85e8943 (AR-072),
                                                           # functionally harmless — recorded by
                                                           # §2.6/§4.6, never discovered.
  shared:
    - monitoring                       # the cluster's log/metric collection pipeline:
                                       # 3 daemon-collector pods roll one node at a time
                                       # -> a ~10-30 s pod-log gap PER NODE (file_log
                                       # start_at: end, no storeCheckpoints). Any other
                                       # plan whose verification reads ES log continuity
                                       # in those minutes sees a hole. Prometheus scrapes
                                       # and edot-collector are NOT perturbed.
depends_on: []
conflicts_with:                        # HARD slot exclusions — window-scheduler.py honours
                                       # only this field; the shared:[monitoring] overlap is
                                       # a post-placement warning (2026-09-15 review).
  - kube-prometheus-stack-91.4.0       # both CreateReplace the same four monitoring.coreos.com
                                       # CRDs (last writer wins, 0.92.0 vs 0.94.0). §6 already
                                       # said "never the same window"; both plans are
                                       # AUTO-NIGHT with window null, so only the field keeps
                                       # them out of one nightly. Preferred order: THIS plan
                                       # first (§6).
  - prometheus-crd-ownership           # edits the SAME HelmRelease spec (a values key); its §4
                                       # asserts "CRD generation unchanged across ONE helm
                                       # upgrade" — two otel-operator upgrades in one window
                                       # confound that. Either order across windows is fine
                                       # (§6).
security_ref: null                     # no security driver. This bump does NOT move the
                                       # operator or collector image (both stay 0.154.0),
                                       # so it does not touch the AR-072-accepted image
                                       # findings; the kube-stack release that moves the
                                       # opentelemetry-operator SUBCHART is the one that
                                       # will, and that will be its own plan.
capability_change: false               # appVersion identical; the only new capability
                                       # (presets.profiling) is opt-in, default false,
                                       # NOT enabled here; rendered objects identical
rollback_class: git-revert             # no data, no migration, CRDs identical both ways
finding_refs:
  - F-60ebcdb5                         # "otel-operator: chart 0.20.9 → 0.21.0 (minor)" —
                                       # section version, severity monitor, filed by the
                                       # 2026-09-15 02:15Z sweep (F-e918a007 is the EXECUTED
                                       # 0.20.9 patch). Its Action text, "batch with other
                                       # minor bumps", is the generic version-section text
                                       # and is WRONG for this item: a 0.x line move that
                                       # coverage.py holds — PLAN lane, never Step 0. This
                                       # ref joins the finding to the plan and supersedes
                                       # that action.
status: vetted   # REVIEWED 2026-09-15 (plan-reviewer fan-out, corrections applied in c36388bc)
window: "nightly:2026-09-17"   # 2026-09-15: moved off 09-16: reconciler INTERFERENCE with unpoller-v5.2.5 (shared monitoring); unpoller runs 09-16, otel the night after, kps waits for prometheus-crd-ownership
                                       # no reboot, git-revert, no capability change).
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
premises:
  - id: live-chart-still-0.20.9
    why: >-
      `current:` claims chart 0.20.9 (helm v23). If the cluster already moved,
      the render-diff baseline and the rollback target in this plan are stale.
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "0.20.9"
  - id: helmrelease-ready
    why: "Do not stack a bump on top of an already-failing release."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: live-operator-image-0.154.0
    why: >-
      The whole low-risk argument is "appVersion unchanged". It is only true
      if the RUNNING operator is the chart-default 0.154.0 with no tag override.
    run: kubectl get deploy otel-operator-opentelemetry-operator -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/open-telemetry/opentelemetry-operator/opentelemetry-operator:0.154.0"
  - id: live-collector-image-0.154.0
    why: >-
      Same claim for the collector image the operator stamps on the DaemonSet
      (`--collector-image=otel/opentelemetry-collector-k8s:0.154.0`).
    run: kubectl get daemonset otel-operator-daemon-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "otel/opentelemetry-collector-k8s:0.154.0"
  - id: daemon-collector-3-of-3
    why: >-
      §4's per-node contents assertion compares against a healthy 3/3
      baseline; starting from a degraded DaemonSet makes that diff
      uninterpretable.
    run: kubectl get daemonset otel-operator-daemon-collector -n monitoring -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled}'
    expect_exact: "3/3"
  - id: profiling-preset-not-enabled
    why: >-
      EVERY template change in 0.21.0 is gated on the new
      `presets.profiling.enabled` key (default false). If someone enabled it
      in the HR values since this plan was written, the render is no longer
      a 2-line label diff: it adds hostPID, an eBPF capability set, a tracefs
      hostPath mount and a `profiles` pipeline — and the chart FAILS the
      render on our community image. Asserts the preset map is non-empty and
      contains no `profiling` key.
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.spec.values.collectors.daemon.presets}'
    expect_matches: '^(?!.*profiling).*"logsCollection":\{"enabled":true\}.*$'
  - id: no-instrumentation-crs
    why: >-
      The Instrumentation webhook/CRD surface is inert only while no
      Instrumentation objects exist (the operator also runs an
      "instrumentation-upgrade" pass on start). `-o name | wc -l` prints 0,
      never empty, so the checker cannot read silence as consent.
    run: kubectl get instrumentation -A -o name | wc -l
    expect_exact: "0"
  - id: operator-manages-no-deployment
    why: >-
      edot-collector must still be a plain Kustomize Deployment, NOT an
      operator-managed one — otherwise this bump would roll the ES gateway
      too and §6's "edot is untouched" claim is false.
    run: kubectl get deploy -n monitoring -l app.kubernetes.io/managed-by=opentelemetry-operator -o name | wc -l
    expect_exact: "0"
  # NOTE (2026-09-15 review): the former premise `this-hr-owns-the-prometheus-crds`
  # (servicemonitors CRD label == otel-operator) was REMOVED on purpose. It fails
  # BY DESIGN once kube-prometheus-stack-91.4.0 lands (that plan re-stamps all ten
  # CRDs and the label follows the last applier), which would silently drop this
  # plan out of every later sequence. The ordering fact is now MEASURED in-window
  # by §2.6 and asserted by §4.6 instead of gating placement.
generated: "2026-09-15"
---

# otel-operator (opentelemetry-kube-stack): chart 0.20.9 → 0.21.0

## 1) Summary & why held

Bump the `otel-operator` HelmRelease (`kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml`)
from **opentelemetry-kube-stack 0.20.9 → 0.21.0**. That HelmRelease is the umbrella
chart, not the operator chart directly: it carries subcharts `otel-crds`,
`prometheus-crds`, and `opentelemetry-operator 0.119.0` (`kube-state-metrics` and
`prometheus-node-exporter` are disabled here — the render contains neither). It
renders **one** `OpenTelemetryCollector` CR, `otel-operator-daemon`, which the
operator materialises as the 3-pod DaemonSet `otel-operator-daemon-collector`
(logs / kubeletstats / hostmetrics / k8s events / cluster metrics per node), all
exported over OTLP to `edot-collector.monitoring.svc:4317`. `edot-collector`
itself is a plain Kustomize Deployment (`kubernetes/apps/monitoring/edot-collector/`)
and is **not** managed by the operator.

### Why it was held

`runbooks/coverage.py` (line ~1457): *"0.x release-line move (0.20 -> 0.21) — at
major 0 the minor IS the breaking axis; needs an assessed window plan."* Correct
policy: on a 0.x chart a minor is where renames, image jumps and CRD changes are
allowed to land. The hold is the rule working as designed.

### What 0.21.0 actually is — measured, not assumed

Upstream release `opentelemetry-kube-stack-0.21.0` (published 2026-09-14 18:01 UTC)
lists **one** chart change: **PR #2396 "[opentelemetry-kube-stack] add profiling
support"** (merged 18:01:13 UTC; the other item, #2401, is a CI-runner change).
The PR ports the eBPF-profiler preset from the `opentelemetry-collector` chart.

`helm` index + tarball comparison, 0.20.9 vs 0.21.0:

| Property | 0.20.9 | 0.21.0 |
|---|---|---|
| `appVersion` | 0.154.0 | **0.154.0 (unchanged)** |
| dep `opentelemetry-operator` | 0.119.0 | **0.119.0 (unchanged)** — subchart directory byte-identical |
| `charts/otel-crds/crds/*` (4 CRDs) | — | **byte-identical** |
| `charts/prometheus-crds/crds/*` (4 CRDs) | — | **byte-identical** |
| `Chart.yaml` diff | — | the `version:` line only |
| files changed | — | `values.yaml`, `values.schema.json`, `templates/{NOTES.txt,_config.tpl,_helpers.tpl,collector.yaml}`, `ci/isolated-distribution-host-profiler.yaml` (new) |

Every template hunk is gated on the **new** value `collectors.<name>.presets.profiling.enabled`
(default `false`). When it is true, the chart adds `hostPID: true`, a `tracefs`
hostPath mount, a root `securityContext` with `BPF/PERFMON/SYS_PTRACE/…`
capabilities, a `profiles` pipeline with a `profiling` receiver, a `container.id`
pod-association rule in `k8sattributes`, and a `NOTES.txt` `fail` when the image is
a community distribution. The new `values.yaml` text is explicit:

> *"Warning: The profiling receiver requires elevated capabilities and hostPID, so
> it should be used with a dedicated collector distribution (e.g. otelcol-ebpf-profiler)
> rather than the general-purpose k8s distribution."*

We do **not** set that key (premise `profiling-preset-not-enabled` proves it live).

**Render diff with OUR HelmRelease values** (`helm template otel-operator <chart>
-n monitoring -f <HR .spec.values> --include-crds --kube-version 1.36.0`, both
versions, 29 objects / 38 211 lines each, cert material masked):

```
37426c37426
<     helm.sh/chart: opentelemetry-kube-stack-0.20.9      # OpenTelemetryCollector/otel-operator-daemon
>     helm.sh/chart: opentelemetry-kube-stack-0.21.0
38211c38211
<           - "helm.sh/chart=opentelemetry-kube-stack-0.20.9"   # Job/opentelemetry-kube-stack-pre-delete-job (uninstall hook only)
>           - "helm.sh/chart=opentelemetry-kube-stack-0.21.0"
```

Nothing else. Operator Deployment, RBAC, Services, both webhook configurations and
all 8 CRDs render identically. The webhook `Secret`/`caBundle` differ between any
two renders because `admissionWebhooks.autoGenerateCert.recreate: true` mints a new
self-signed cert on every `helm upgrade` — that is per-reconcile behaviour, not a
0.21.0 change, and it happened on the 0.20.9 bump too.

**Verdict: the hold is a policy true-positive and a content false-positive.** For
our values 0.21.0 is a label bump. `risk: low`, `git-revert`. This plan still
exists because the window agent — not the planner — decides, and because the
things that DO move on the cluster (below) deserve their verification.

### What moves on the cluster, and what does not

Moves — all observed on the 0.20.9 bump on 2026-09-14 and expected identically here:

1. **The 3 collector DaemonSet pods roll, one node at a time.** The operator copies
   the CR's labels into the pod template (the live template carries
   `helm.sh/chart: opentelemetry-kube-stack-0.20.9`), so the label bump is a pod
   template change. `file_log` runs `start_at: end` with no `storeCheckpoints`, so
   each node loses the pod-log lines written during its own pod's restart (~10-30 s).
   The `k8s_cluster` and `k8s_objects` receivers are leader-elected
   (`k8s_leader_elector`, lease duration 15 s) — the new pod set re-acquires both
   leases within seconds; §4 asserts that rather than assuming it.
2. **The webhook serving cert is regenerated.** For the seconds between the new
   Secret landing and the webhook configs' `caBundle` being updated, the operator
   logs `http: TLS handshake error … bad certificate` (2026-09-14: 05:45:10 →
   05:45:24, then `certwatcher: Updated current TLS certificate`). Both webhook
   configs are `failurePolicy: Ignore`, so no admission is blocked; the operator
   hot-reloads the cert without a restart. §4 asserts `caBundle == ca.crt` at the
   end, because a stale bundle under `Ignore` would fail **silently**.

Does not move: the operator Deployment (subchart unchanged → identical pod
template → no rollout; its pod is 7d21h old today, 20h for the collector pods),
the four `opentelemetry.io` CRDs (`crds: CreateReplace` re-applies byte-identical
documents), RBAC, `edot-collector`, Prometheus scrape targets (only
`edot-collector` has a ServiceMonitor; the daemon collector is not scraped by
Prometheus at all — its own telemetry goes to ES via edot).

**The four `monitoring.coreos.com` CRDs — an ordering caveat, not a change.**
0.20.9 and 0.21.0 ship byte-identical copies of `servicemonitors`, `podmonitors`,
`probes`, `scrapeconfigs` (prometheus-operator **0.92.0**, from the
`charts/prometheus-crds/crds/` subchart directory). Today (2026-09-15) the live
objects ARE that copy — `operator.prometheus.io/version 0.92.0`, generation 30,
origin label `otel-operator` — so this bump's CreateReplace is a no-op re-apply.
Two sibling plans change that picture, and this plan does not assume either
has or has not run; §2.6 measures it and §4.6 asserts the matching post-state:

- **`prometheus-crd-ownership` landed first** (`crds.installPrometheus: false`
  on this HR): helm-controller no longer collects that subchart's `crds/`, so
  this bump does **not** write the four at all. Generation and version stay
  whatever they were.
- **`kube-prometheus-stack-91.4.0` landed first, without that fix:** the four
  read 0.94.0 and this bump **downgrades** them to 0.92.0. That is the accepted
  contention **F-a85e8943** (AR-072): functionally harmless because no CR of
  those kinds uses a 0.93+/0.94+ field, but it must be *recorded* by §4.6, not
  discovered by the next sweep. `conflicts_with` keeps both plans out of the
  same window; the preferred order is this plan **before** kps (§6).

Context for the window agent: upstream `opentelemetry-operator` chart is already at
0.122.1 / appVersion 0.158.0 while kube-stack still pins 0.119.0 / 0.154.0. **This
bump does not close that gap.** The kube-stack release that bumps the subchart will
move both images and is a separate plan with a real changelog to read.

## 2) Pre-checks

Run inside the window. Each has a pass condition; a fail is a no-go.

```bash
cd /Users/mu/code/cberg-home-nextgen
export KUBECONFIG="$PWD/kubeconfig"
```

**2.1 — Premises** (the frontmatter block, run by the scheduler; re-run here):

```bash
.venv/bin/python3 runbooks/plan-premises.py otel-operator-0.21.0 --require-premises
```
**PASS:** all 8 premises pass.

**2.2 — Flux green, release history sane.**

```bash
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'
kubectl get hr -n monitoring otel-operator -o jsonpath='{.status.history[0].chartVersion} {.status.history[0].version} {.status.history[0].status}{"\n"}'
```
**PASS:** header rows only; `0.20.9 23 deployed` *(baseline 2026-09-15)*.

**2.3 — Pipeline healthy, and RECORD the baselines §4 diffs against.**

```bash
kubectl get pods -n monitoring -l app.kubernetes.io/instance=monitoring.otel-operator-daemon -o wide
kubectl get pods -n monitoring -l app.kubernetes.io/name=opentelemetry-operator -o wide   # NOTE the pod NAME
kubectl get pods -n monitoring -l app=edot-collector -o wide

kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9299:9090 >/dev/null 2>&1 & PF=$!
sleep 4
for q in 'sum(rate(otelcol_receiver_accepted_log_records_total{receiver="otlp"}[5m]))' \
         'sum(rate(otelcol_receiver_accepted_metric_points_total{receiver="otlp"}[5m]))'; do
  curl -s --get localhost:9299/api/v1/query --data-urlencode "query=$q" \
    | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print('$q'[:60], round(float(r[0]['value'][1]),1) if r else 'EMPTY')"
done
curl -s localhost:9299/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)['data']['alerts'] if x['state']=='firing' and x['labels'].get('alertname') not in ('Watchdog','InfoInhibitor')]
print('firing:',len(a),[x['labels'].get('alertname') for x in a])"
kill $PF 2>/dev/null
```
**PASS:** 3 collector pods `Running`, 0 restarts; operator 1/1; edot 1/1. Inflow
into edot from the daemon collectors is the shape signal that the daemon is
alive — *baseline 2026-09-15 03:55: logs ≈ 40/s, metric points ≈ 3 560/s;
firing: 1 (`LonghornVolumeAllocationHigh`, unrelated)*. Any `Otel*`/`Edot*` alert
firing is a no-go.

**2.4 — ES per-node baseline (the CONTENTS floor).** Same query §4 re-runs.

```bash
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 9261:9200 >/dev/null 2>&1 & PF=$!
sleep 4
# pod logs per node, last 15 min
curl -k -s -u "elastic:$ES_PW" -X POST "https://localhost:9261/logs-generic-default/_search" -H 'Content-Type: application/json' -d '{"size":0,"query":{"bool":{"filter":[{"range":{"@timestamp":{"gte":"now-15m"}}},{"exists":{"field":"resource.attributes.k8s.pod.name"}}]}},"aggs":{"node":{"terms":{"field":"resource.attributes.k8s.node.name","size":5}}}}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('pod-log docs/node 15m:',[(b['key'],b['doc_count']) for b in d['aggregations']['node']['buckets']])"
# kubeletstats per node, last 15 min
curl -k -s -u "elastic:$ES_PW" -X POST "https://localhost:9261/metrics-generic.otel-default/_search" -H 'Content-Type: application/json' -d '{"size":0,"query":{"bool":{"filter":[{"range":{"@timestamp":{"gte":"now-15m"}}},{"exists":{"field":"metrics.k8s.pod.cpu.usage"}}]}},"aggs":{"node":{"terms":{"field":"resource.attributes.k8s.node.name","size":5}}}}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('k8s.pod.cpu.usage docs/node 15m:',[(b['key'],b['doc_count']) for b in d['aggregations']['node']['buckets']])"
# hostmetrics floor + k8s events (leader-elected receiver), last 15 / 60 min
curl -k -s -u "elastic:$ES_PW" -X POST "https://localhost:9261/metrics-generic.otel-default/_count" -H 'Content-Type: application/json' -d '{"query":{"bool":{"filter":[{"range":{"@timestamp":{"gte":"now-15m"}}},{"exists":{"field":"metrics.system.cpu.utilization"}}]}}}' | python3 -c "import sys,json; print('system.cpu.utilization docs 15m:', json.load(sys.stdin)['count'])"
curl -k -s -u "elastic:$ES_PW" -X POST "https://localhost:9261/logs-generic-default/_count" -H 'Content-Type: application/json' -d '{"query":{"bool":{"filter":[{"range":{"@timestamp":{"gte":"now-60m"}}},{"term":{"attributes.k8s.resource.name":"events"}}]}}}' | python3 -c "import sys,json; print('k8s event docs 60m:', json.load(sys.stdin)['count'])"
kill $PF 2>/dev/null; unset ES_PW
```
**PASS / baseline measured 2026-09-15 03:55:** pod-log docs/node 15m
`03=27 608, 02=9 316, 01=7 751` (all three nodes present, thousands each);
`k8s.pod.cpu.usage` docs/node 15m `03=5 821, 01=5 700, 02=4 563`;
`system.cpu.utilization` 15m `38 736`; k8s event docs 60m `1 138`. Any node
missing from either per-node aggregation is a no-go — the plan would then be
verifying against a pipeline that is already broken.

**2.5 — Target chart is what this plan analysed.** The analysis holds for
**0.21.0 exactly**. If the index now also lists 0.21.1+, do **not** silently take
it — re-diff first (§3.2), or stay on 0.21.0.

```bash
curl -sL https://open-telemetry.github.io/opentelemetry-helm-charts/index.yaml | python3 -c "
import sys,yaml
ks=yaml.safe_load(sys.stdin)['entries']['opentelemetry-kube-stack']
for e in ks[:4]: print(e['version'],'appVersion',e['appVersion'],'operator-dep',[d['version'] for d in e['dependencies'] if d['name']=='opentelemetry-operator'])"
```
**PASS:** the `0.21.0` row shows `appVersion 0.154.0` and `operator-dep ['0.119.0']`.
If either moved, **STOP** — this plan's central claim is void and it must be
re-planned as an image-moving bump.

> Local tooling note: `helm show chart --repo …` / `helm pull --repo …` fail on
> this Mac with *"no cached repo found … temp-2248-index.yaml"* (a stale
> `temp-2248` entry in `~/Library/Preferences/helm/repositories.yaml`). That is why
> the premises are kubectl-only and this check uses the raw index. Downloading the
> release tarball directly (§3.2) works.

**2.6 — Prometheus-CRD pre-state (RECORD it; §4.6 asserts the matching post-state).**
The four `monitoring.coreos.com` CRDs this chart bundles are written by two
HelmReleases (F-a85e8943, §1). Which sibling plans have landed decides what this
bump does to them, so measure instead of assuming:

```bash
kubectl get helmrelease -n monitoring otel-operator -o jsonpath='installPrometheus=[{.spec.values.crds.installPrometheus}]{"\n"}'
kubectl get crd servicemonitors.monitoring.coreos.com podmonitors.monitoring.coreos.com probes.monitoring.coreos.com scrapeconfigs.monitoring.coreos.com \
  -o 'custom-columns=NAME:.metadata.name,GEN:.metadata.generation,OPVER:.metadata.annotations.operator\.prometheus\.io/version,ORIGIN:.metadata.labels.helm\.toolkit\.fluxcd\.io/name'
```
**Baseline 2026-09-15:** `installPrometheus=[]` (unset → chart default `true`);
all four `GEN 30`, `OPVER 0.92.0`, `ORIGIN otel-operator`. Write the four rows
down. Interpretation — every row is a PASS, but it fixes what §4.6 must see:

| `installPrometheus` | four CRDs read | meaning | §4.6 expects after this bump |
|---|---|---|---|
| `[]` | 0.92.0 / otel-operator | today's picture; neither sibling has run | 0.92.0, GEN +1, origin otel-operator (byte-identical re-apply) |
| `[false]` | anything | `prometheus-crd-ownership` landed; this HR no longer writes them | GEN, OPVER, ORIGIN **unchanged** |
| `[]` | 0.94.0 / kube-prometheus-stack | `kube-prometheus-stack-91.4.0` landed first without the ownership fix | 0.92.0, GEN +1, origin otel-operator — the documented DOWNGRADE (F-a85e8943); proceed, and say so in the window record |
| mixed values across the four | — | a third writer; **STOP** and re-derive §1 | — |

## 3) Steps

**3.1 — Drop an active-update marker** (so the alert-triage agent treats a
`KubeDaemonSetRolloutStuck` / `KubePodNotReady` blip on the collector as expected).
A 4h Alertmanager silence is NOT needed for a low-risk bump per
`application-update.md` §2; the marker alone is proportionate.

```bash
runbooks/update-marker.sh add otel-operator monitoring 2 "chart 0.20.9->0.21.0"
```

**3.2 — Re-run the render diff as a gate** (the exact procedure that produced §1;
~1 min). Optional but cheap, and it is what turns "the planner said so" into
"measured in this window".

```bash
SP=$(mktemp -d)
python3 -c "
import yaml; hr=yaml.safe_load(open('kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml'))
open('$SP/values.yaml','w').write(yaml.safe_dump(hr['spec']['values'], sort_keys=False))"
for v in 0.20.9 0.21.0; do
  curl -sSL -o $SP/ks-$v.tgz "https://github.com/open-telemetry/opentelemetry-helm-charts/releases/download/opentelemetry-kube-stack-$v/opentelemetry-kube-stack-$v.tgz"
  mkdir -p $SP/src-$v && tar -xzf $SP/ks-$v.tgz -C $SP/src-$v
  helm template otel-operator $SP/src-$v/opentelemetry-kube-stack -n monitoring -f $SP/values.yaml --include-crds --kube-version 1.36.0 > $SP/render-$v.yaml
done
diff <(sed -E 's/(tls\.crt|tls\.key|ca\.crt|caBundle): .*/\1: <masked>/' $SP/render-0.20.9.yaml) \
     <(sed -E 's/(tls\.crt|tls\.key|ca\.crt|caBundle): .*/\1: <masked>/' $SP/render-0.21.0.yaml)
```
**PASS — EXACTLY:** two changed lines, both `helm.sh/chart: …-0.20.9 → …-0.21.0`
(one on `OpenTelemetryCollector/otel-operator-daemon`, one in the pre-delete hook
Job's args). **Any other line — a new volume, `hostPID`, a capability, a
`profiles` pipeline, a CRD hunk — means the premise `profiling-preset-not-enabled`
or §2.5 is wrong: STOP.**

**3.3 — Bump the chart version.**

```bash
sed -i '' 's/^      version: 0\.20\.9$/      version: 0.21.0/' kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml
git --no-pager diff kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml
```
**PASS:** exactly one hunk, `-      version: 0.20.9` / `+      version: 0.21.0`.

**3.4 — Commit and push** (shared worktree: `--only`, explicit path).

```bash
cat > /tmp/otel-msg.txt <<'EOF'
chore(otel-operator): chart 0.20.9 -> 0.21.0 (kube-stack minor, label-only for our values)

Held by coverage.py as a 0.x release-line move. Assessed in plan
runbooks/maintenance/plans/otel-operator-0.21.0.md: upstream 0.21.0 is one
PR (#2396, profiling preset), entirely gated on presets.profiling.enabled
(default false, not set here). appVersion 0.154.0 and the
opentelemetry-operator subchart 0.119.0 are unchanged; all 8 CRDs
byte-identical; render diff with our HR values is exactly the two
helm.sh/chart label lines. Operator and collector images do not change.

Expected side effects, as on the 0.20.9 bump: the 3 collector DaemonSet
pods roll one node at a time (CR label -> pod template), and the webhook
cert is regenerated (autoGenerateCert.recreate). No operator rollout.

Rollback: git revert this commit (HR remediation: rollback, retries 3).
EOF
git commit --only kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml -F /tmp/otel-msg.txt
git show --stat HEAD            # MUST list exactly this one file
git push origin main
```

**3.5 — Let Flux land it** (webhook fires on push; no manual reconcile needed —
`flux reconcile` only if the HR has not picked up the new revision after ~3 min).

```bash
# HR moves through Reconciling -> Ready with the new chart
for i in $(seq 1 30); do
  kubectl get hr -n monitoring otel-operator -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion} {.status.history[0].version}{"\n"}'
  sleep 10
done | uniq
# the collector roll
kubectl rollout status ds/otel-operator-daemon-collector -n monitoring --timeout=5m
```
**PASS:** ends at `True 0.21.0 <v+1>` — `24` if v23 is still the newest revision at
window time; the number is informational (any other reconcile of this HR first
shifts it), the assertion is `True` + chart `0.21.0`; rollout status
`successfully rolled out`.

**3.6 — Wait 10 minutes** before §4's ES assertions (they need a window that starts
after the LAST collector pod became Ready). Use the time for §4.1-4.3.

**3.7 — On success:** `runbooks/update-marker.sh clear otel-operator`.

## 4) Verification

### 4.1 — Release + workloads (the floor)

```bash
kubectl get hr -n monitoring otel-operator -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion} {.status.history[0].version} {.status.history[0].status}{"\n"}'
kubectl get opentelemetrycollector -n monitoring otel-operator-daemon -o jsonpath='{.metadata.labels.helm\.sh/chart} {.status.version} {.status.scale.statusReplicas}{"\n"}'
kubectl get ds -n monitoring otel-operator-daemon-collector -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled} {.spec.template.spec.containers[0].image} {.spec.template.metadata.labels.helm\.sh/chart}{"\n"}'
kubectl get pods -n monitoring -l app.kubernetes.io/instance=monitoring.otel-operator-daemon -o 'custom-columns=NAME:.metadata.name,NODE:.spec.nodeName,RESTARTS:.status.containerStatuses[0].restartCount,AGE:.metadata.creationTimestamp'
kubectl get pods -n monitoring -l app.kubernetes.io/name=opentelemetry-operator -o 'custom-columns=NAME:.metadata.name,AGE:.metadata.creationTimestamp,IMAGE:.spec.containers[0].image'
```
(The `custom-columns=` arguments are single-quoted on purpose: under zsh an
unquoted `[0]` is a glob and aborts with `no matches found`, and a verification
step that cannot run reads as a failed window.)

**PASS:** `True 0.21.0 <v+1> deployed` (revision informational, §3.5); CR label
`opentelemetry-kube-stack-0.21.0`,
`status.version 0.154.0`, `3/3`; DaemonSet `3/3`, image
`otel/opentelemetry-collector-k8s:0.154.0`, template label `…-0.21.0`; three NEW
collector pods (creation time inside the window, one per node, `RESTARTS 0`);
**operator pod NAME identical to the §2.3 baseline** and image still `0.154.0` —
an operator restart here is unexpected and must be explained before the window
closes.

### 4.2 — Webhook cert consistency (the thing that fails SILENTLY)

Both webhook configurations are `failurePolicy: Ignore`. If `caBundle` does not
match the regenerated serving cert, every CR admission call fails TLS and the API
server just… proceeds. Nothing pages. The operator log is the only place it shows.

```bash
CA=$(kubectl get secret -n monitoring otel-operator-opentelemetry-operator-controller-manager-service-cert -o jsonpath='{.data.ca\.crt}')
for w in mutatingwebhookconfiguration/otel-operator-opentelemetry-operator-mutation validatingwebhookconfiguration/otel-operator-opentelemetry-operator-validation; do
  kubectl get $w -o json | python3 -c "
import sys,json; ca='$CA'; d=json.load(sys.stdin)
print(d['metadata']['name'], 'webhooks', len(d['webhooks']), 'caBundle==ca.crt:', all(h['clientConfig'].get('caBundle')==ca for h in d['webhooks']))"
done
kubectl logs -n monitoring deploy/otel-operator-opentelemetry-operator --since=15m | grep -c 'bad certificate' || true
kubectl logs -n monitoring deploy/otel-operator-opentelemetry-operator --since=15m | grep -c 'Updated current TLS certificate' || true
```
**PASS:** both configs `caBundle==ca.crt: True` (3 and 4 webhooks respectively);
`Updated current TLS certificate` ≥ 1; `bad certificate` lines exist only in the
~30 s around the upgrade — **none in the last 5 minutes** (re-run `--since=5m`
and expect 0).

### 4.3 — Leader-elected receivers re-acquired their leases

`k8s_cluster` (cluster metrics) and `k8s_objects` (k8s events) run on exactly one
of the three pods via `k8s_leader_elector`. Lease duration is 15 s; a lease whose
`renewTime` is stale means the new pod set failed to take over and events +
cluster metrics have silently stopped.

```bash
kubectl get lease -n monitoring k8s.cluster.receiver.opentelemetry.io k8s.objects.receiver.opentelemetry.io \
  -o custom-columns=NAME:.metadata.name,HOLDER:.spec.holderIdentity,RENEWED:.spec.renewTime
date -u +%Y-%m-%dT%H:%M:%SZ
```
**PASS:** both `RENEWED` timestamps within **60 s** of `date -u`.

### 4.4 — CONTENTS ASSERTIONS (per README: chart bump on something that ships telemetry)

Run **≥ 10 min after the last collector pod became Ready** (§3.6), with the same
port-forward as §2.4. Measured over `now-10m`, i.e. a window that begins after the
change — a window overlapping the pre-change period would credit the old pods.

> **CONTENTS ASSERTION 1 (pod logs — every node still ships).** Measured by the
> §2.4 per-node `logs-generic-default` aggregation over `now-10m`. Compared to the
> §2.4 baseline. **PASS:** all three node names present, each with **> 500**
> documents (baseline was 7.7k-27.6k per 15 min; a node at 0 or a node missing
> from the buckets is a FAIL even with the DaemonSet 3/3 — it means that pod's
> `file_log` is not tailing).

> **CONTENTS ASSERTION 2 (kubeletstats — every node still scrapes its kubelet).**
> Measured by the §2.4 `metrics.k8s.pod.cpu.usage` per-node aggregation over
> `now-10m`. **PASS:** all three nodes present, each **> 1 000** (baseline
> 4.5k-5.8k / 15 min).

> **CONTENTS ASSERTION 3 (hostmetrics + k8s events — the leader-elected path
> produces).** Measured by the §2.4 counts: `metrics.system.cpu.utilization` over
> `now-10m` and `attributes.k8s.resource.name: events` over `now-10m`. **PASS:**
> cpu.utilization **> 10 000** (baseline 38.7k / 15 min) **and** events **> 0**.
> A cluster with three collector pods up and zero event documents is exactly the
> failure §4.3 guards against; this is the floor under it.

```bash
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 9261:9200 >/dev/null 2>&1 & PF=$!
sleep 4
for spec in 'logs-generic-default|resource.attributes.k8s.pod.name|pod-log docs/node' 'metrics-generic.otel-default|metrics.k8s.pod.cpu.usage|k8s.pod.cpu.usage docs/node'; do
  IFS='|' read -r ds field label <<< "$spec"
  curl -k -s -u "elastic:$ES_PW" -X POST "https://localhost:9261/$ds/_search" -H 'Content-Type: application/json' -d '{"size":0,"query":{"bool":{"filter":[{"range":{"@timestamp":{"gte":"now-10m"}}},{"exists":{"field":"'"$field"'"}}]}},"aggs":{"node":{"terms":{"field":"resource.attributes.k8s.node.name","size":5}}}}' \
    | python3 -c "import sys,json; d=json.load(sys.stdin); b=d['aggregations']['node']['buckets']; print('$label 10m:',[(x['key'],x['doc_count']) for x in b], 'NODES:',len(b))"
done
curl -k -s -u "elastic:$ES_PW" -X POST "https://localhost:9261/metrics-generic.otel-default/_count" -H 'Content-Type: application/json' -d '{"query":{"bool":{"filter":[{"range":{"@timestamp":{"gte":"now-10m"}}},{"exists":{"field":"metrics.system.cpu.utilization"}}]}}}' | python3 -c "import sys,json; print('system.cpu.utilization docs 10m:', json.load(sys.stdin)['count'])"
curl -k -s -u "elastic:$ES_PW" -X POST "https://localhost:9261/logs-generic-default/_count" -H 'Content-Type: application/json' -d '{"query":{"bool":{"filter":[{"range":{"@timestamp":{"gte":"now-10m"}}},{"term":{"attributes.k8s.resource.name":"events"}}]}}}' | python3 -c "import sys,json; print('k8s event docs 10m:', json.load(sys.stdin)['count'])"
kill $PF 2>/dev/null; unset ES_PW
```

### 4.5 — Prometheus side: inflow back, nothing refused, alerts at baseline

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9299:9090 >/dev/null 2>&1 & PF=$!
sleep 4
for q in 'sum(rate(otelcol_receiver_accepted_log_records_total{receiver="otlp"}[5m]))' \
         'sum(rate(otelcol_receiver_accepted_metric_points_total{receiver="otlp"}[5m]))' \
         'sum(increase(otelcol_receiver_refused_log_records_total[15m])) + sum(increase(otelcol_receiver_refused_metric_points_total[15m]))' \
         'sum(increase(otelcol_exporter_send_failed_log_records_total[15m]))'; do
  curl -s --get localhost:9299/api/v1/query --data-urlencode "query=$q" \
    | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print('$q'[:70], round(float(r[0]['value'][1]),1) if r else 'EMPTY')"
done
curl -s localhost:9299/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)['data']['alerts'] if x['state']=='firing' and x['labels'].get('alertname') not in ('Watchdog','InfoInhibitor')]
print('firing:',len(a),[x['labels'].get('alertname') for x in a])"
kill $PF 2>/dev/null
```
**PASS:** OTLP inflow into edot ≥ **half** the §2.3 baseline (logs ≥ 20/s, metric
points ≥ 1 800/s — the daemon sends in batches, so a short window is noisy;
zero or `EMPTY` is a FAIL); refused **= 0**; send_failed **= 0**; the firing set
equals the §2.3 baseline (no `Otel*`, `Edot*`, `KubeDaemonSet*` alert).

**A ceiling without a floor is a shape check:** "no alerts firing" alone would be
green with all three collectors silently idle. Assertions 1-3 are the floor.

### 4.6 — Prometheus-CRD post-state matches the §2.6 row

```bash
kubectl get crd servicemonitors.monitoring.coreos.com podmonitors.monitoring.coreos.com probes.monitoring.coreos.com scrapeconfigs.monitoring.coreos.com \
  -o 'custom-columns=NAME:.metadata.name,GEN:.metadata.generation,OPVER:.metadata.annotations.operator\.prometheus\.io/version,ORIGIN:.metadata.labels.helm\.toolkit\.fluxcd\.io/name'
for k in servicemonitors podmonitors probes scrapeconfigs; do printf '%-16s %s\n' $k "$(kubectl get $k.monitoring.coreos.com -A --no-headers | wc -l | tr -d ' ')"; done
```
**PASS:** all four rows EXIST and read exactly what the §2.6 table's last column
predicts for the pre-state you recorded (today: `0.92.0`, `GEN 31`, origin
`otel-operator`); the per-kind CR counts equal the pre-window counts (a CRD
delete would cascade them to 0 — 49/3/4/3 on 2026-09-15). **If the row was the
0.94.0 one:** the four now read 0.92.0 — record "downgraded per F-a85e8943" in
the window record; it is not a rollback trigger. **FAIL:** any CRD missing, or a
write on the four when `installPrometheus=[false]` was recorded (the ownership
fix did not take — that is `prometheus-crd-ownership`'s §5, not this plan's).

## 5) Rollback

`rollback_class: git-revert` — no data, no schema, no migration; both chart
versions render the same CRDs, so a downgrade replaces byte-identical documents
(for the four Prometheus CRDs: the same §2.6/§4.6 ordering rule applies to the
revert's re-apply as to the forward one).

**5.1 — Flux does the first tier itself.** `upgrade.remediation: {strategy:
rollback, retries: 3}` — if the helm upgrade to 0.21.0 fails (e.g. a CRD apply
error), helm-controller rolls the release back to v23 automatically. Check
`kubectl describe hr -n monitoring otel-operator` for `Rollback` events before
doing anything by hand.

**5.2 — Revert the commit** if §4 fails after a *successful* upgrade:

```bash
git revert --no-edit <sha-of-§3.4-commit>
git show --stat HEAD            # exactly kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml
git push origin main
kubectl rollout status ds/otel-operator-daemon-collector -n monitoring --timeout=5m
```
Expect helm revision **v+2** at chart 0.20.9 (v25 if nothing else reconciled the
HR; informational). The revert is itself a label change
plus a cert regeneration, so **the DaemonSet rolls again** (a second ~10-30 s
log gap per node) and the webhook cert is minted again — re-run §4.2 and §4.3,
then §4.4 after 10 min.

**Confirm the cluster is back** by cluster state, never by `git log`:

```bash
kubectl get hr -n monitoring otel-operator -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion} {.status.history[0].version}{"\n"}'   # True 0.20.9 <v+2>
kubectl get ds -n monitoring otel-operator-daemon-collector -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled} {.spec.template.metadata.labels.helm\.sh/chart}{"\n"}'   # 3/3 …-0.20.9
```
plus §4.4's three contents assertions. Then `runbooks/update-marker.sh clear otel-operator`.

**5.3 — What rollback does NOT need:** no `kubectl delete` of anything, no PVC
work (the collector has none), no CRD surgery. If a CRD ever looks wrong, the
cause is not this bump — both versions ship identical CRDs. The one CRD state
change this bump CAN cause is the four Prometheus CRDs flipping 0.94.0 → 0.92.0
when `kube-prometheus-stack-91.4.0` ran first (§2.6 row 3): that is the
documented contention F-a85e8943, not a fault, and it is not undone by this
revert (the revert re-applies the same 0.92.0 copies).

## 6) Interference notes

- **Shared surface = the observability pipeline itself.** The three collector
  pods roll one node at a time; each node's pod logs have a ~10-30 s hole during
  its own restart (`file_log` `start_at: end`, no checkpoints — a pre-existing
  property of this deployment, not new in 0.21.0). **Schedule this plan FIRST or
  LAST in the window, never interleaved** with a plan whose verification reads
  ES log continuity (the README's "anything log-emitting" class) — its floor
  assertion could dip in exactly those seconds and be misread as that plan's
  regression.
- **Do not run in the same window as an `edot-collector` change.** The daemon
  exports to edot over OTLP with the default in-memory sending queue; a
  simultaneous edot restart is buffered for seconds and lost past that, and it
  makes any gap in §4.4 unattributable. If Step 0's safe-update lane bumps
  `edot-collector` (image) in this window, run this plan only after edot's own
  verification has passed.
- **`kube-prometheus-stack-91.4.0` — hard conflict (`conflicts_with`), and an
  ORDER.** The cluster's `monitoring.coreos.com` CRDs are split between two
  HelmReleases (sweep record **F-a85e8943**, AR-072 — cited, not re-described):
  `servicemonitors`, `podmonitors`, `probes`, `scrapeconfigs` were last written
  by **this** HR (0.92.0), the other six by kube-prometheus-stack (0.93.1). Both
  use `crds: CreateReplace`; the last writer wins and the origin label follows
  it. Two consequences: (1) never the same window — two HRs replacing overlapping
  CRD sets in the same minutes is a race worth not having; (2) **run this plan
  BEFORE kps-91.4.0** (e.g. an earlier nightly). In that order this bump is a
  no-op re-apply (0.92.0 → 0.92.0) and kps's later "`total 10 at 0.94.0`"
  assertion holds as written. In the other order this bump downgrades four CRDs
  0.94.0 → 0.92.0 — harmless (§1) but it must be recorded (§2.6/§4.6), and the
  former premise `this-hr-owns-the-prometheus-crds` would have FAILED by design,
  which is why it was replaced by the §2.6 measurement.
- **`prometheus-crd-ownership` — hard conflict (`conflicts_with`), any order
  across windows.** It sets `crds.installPrometheus: false` on this same
  HelmRelease so this HR stops writing the four CRDs (proven `crds/`-directory
  provenance — no delete risk). Not the same window because two otel-operator
  helm upgrades confound its "generation unchanged across one upgrade" proof.
  If it lands first, this bump touches only the four `opentelemetry.io` CRDs
  (§2.6 row 2). If this plan lands first, nothing changes for it.
- **`talos-1.14.0` (node roll) must not share the window** — it evicts every pod
  including these; every assertion above would be measuring a cluster in motion.
- **No reboot, no capability change, git-revert, ~30 min:** fits `nightly`
  (90 min, `allow_reboot: false`). The execution class is derived by
  `runbooks/autonomy-policy.yaml` from `capability_change: false` +
  `rollback_class: git-revert`; this plan does not claim it.
- **Alert noise expected during the roll:** `KubeDaemonSetRolloutStuck` /
  `KubePodNotReady` on `otel-operator-daemon-collector` for < 2 min, and up to
  ~30 s of `bad certificate` lines in the operator log. The §3.1 marker covers
  the alert-triage path; nothing else needs silencing.
- **What this plan does NOT do, on purpose:** it does not enable
  `presets.profiling` (the chart's own warning says not to on the k8s
  distribution, and it needs `hostPID` + eBPF capabilities on every node), it does
  not bump the operator/collector images (unchanged upstream at this chart
  version), and it does not touch `edot-collector`.
