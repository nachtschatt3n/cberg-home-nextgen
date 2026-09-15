---
plan_id: kube-prometheus-stack-91.4.0
component: kube-prometheus-stack
pr: null                              # no Renovate PR — coverage.py direct-bump lane
                                      # routed it to PLAN ("major — needs an assessed
                                      # window plan"). Sweep finding F-f1e564f2 was
                                      # filed at 91.2.1; the target has since moved to
                                      # 91.4.0 (2026-09-14). If a later 91.x exists at
                                      # window time, re-read its release notes and
                                      # bump `target:` — the 90.0.0 premise still holds.
kind: chart
current: "90.0.0"                     # live: helm revision 39, operator v0.93.1
target: "91.4.0"                      # released 2026-09-14, operator v0.94.0
update_type: major
risk: medium                          # shared monitoring infra: Prometheus AND
                                      # Alertmanager pods restart once (config-reloader
                                      # sidecar image moves), 10 cluster-scoped CRDs are
                                      # REPLACED, and the window's own health gate reads
                                      # this Prometheus. No reboot, no data migration,
                                      # Prometheus/Alertmanager engine images unchanged,
                                      # rollback is a real git revert (§5).
est_duration_min: 35
needs_reboot: false
touches:
  namespaces:
    - monitoring
  resources:
    - helmrelease/kube-prometheus-stack
    - deployment/kube-prometheus-stack-operator            # v0.93.1 -> v0.94.0
    - clusterrole/kube-prometheus-stack-operator           # wildcard verbs -> explicit
    - statefulset/prometheus-kube-prometheus-stack         # restarts (reloader sidecar)
    - statefulset/alertmanager-kube-prometheus-stack       # restarts (reloader sidecar)
    - deployment/kube-prometheus-stack-kube-state-metrics  # subchart 8.4.2 -> 8.5.0, image unchanged
    - daemonset/kube-prometheus-stack-prometheus-node-exporter  # subchart 4.56.3 -> 4.57.0, image unchanged
    - "crd/*.monitoring.coreos.com (10, CLUSTER-SCOPED, replaced by Flux CreateReplace)"
    - pvc/prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0  # RWO longhorn-static PV prometheus-tsdb; NOT modified, re-attached on restart
  shared:
    - monitoring                      # every alert, every SLO, the sweep alert-watcher
                                      # and the window health gates ride on this stack.
                                      # Prometheus is blind for ~2-5 min during its
                                      # restart; Alertmanager for ~1 min.
depends_on:
  - prometheus-crd-ownership          # otel-operator must STOP writing the four shared
                                      # monitoring.coreos.com CRDs before this plan stamps
                                      # all ten to 0.94.0; otherwise the next nightly
                                      # otel patch bump re-stamps four back to 0.92.0 and
                                      # §4.3 holds only until then (CRD planner,
                                      # 2026-09-15). window-scheduler.py will not place
                                      # this plan until that one is `executed`.
conflicts_with:                       # HARD slot exclusions — window-scheduler.py keys on
                                      # this field only; the shared:[monitoring] overlap
                                      # is a post-placement warning (2026-09-15 review).
  - otel-operator-0.21.0              # both CreateReplace the same four CRDs (last writer
                                      # wins, 0.94.0 vs 0.92.0), and landing THIS plan
                                      # first flips their helm.toolkit.fluxcd.io/name
                                      # label to kube-prometheus-stack — §6 states the
                                      # effect on that plan. Its own §6 forbids sharing a
                                      # window with a kps chart bump.
  - unpoller-v5.2.5                   # its §4 verification queries THIS Prometheus over a
                                      # ≥5-min settle; the 2-5 min restart blind spot reads
                                      # as "no data" → a needless unpoller revert.
  - prometheus-crd-ownership          # (also the dependency above) two CreateReplace
                                      # writers of the same ten CRDs in one window is the
                                      # race that plan exists to end; it runs in an EARLIER
                                      # window, never this one.
security_ref: null                    # no security driver
capability_change: false              # operator 0.94.0 adds CRD fields (retentionPercentage,
                                      # clusterPeerName) we do not set; alerts, rules and
                                      # receivers render identically. 10 of the 28
                                      # grafana_dashboard ConfigMaps this chart ships
                                      # (forceDeployDashboards: true) get an upstream mixin
                                      # content refresh — dashboard JSON, not a capability
                                      # (§1, §4.7).
rollback_class: git-revert            # Flux CreateReplace re-applies the 90.0.0 CRD files
                                      # on the revert (operator-version 0.93.1); helm
                                      # maxHistory: 2 keeps revision 39 reachable. §5.
finding_refs:
  - F-f1e564f2                        # "kube-prometheus-stack: chart 90.0.0 → 91.2.1 (major)"
status: draft
window: null
premises:
  - id: hr-still-on-90.0.0
    why: >-
      `current:` claims 90.0.0. If the HelmRelease already moved (a later plan,
      a hand bump, or a 91.x that slipped through Step 0), this plan's baseline
      and its rollback target are both stale.
    run: kubectl get helmrelease -n monitoring kube-prometheus-stack -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "90.0.0"
  - id: operator-live-is-0.93.1
    why: >-
      The whole risk assessment is "operator 0.93.1 -> 0.94.0, CRDs replaced".
      If the running operator is something else, the release-notes delta in §1
      is not the delta this window would apply.
    run: kubectl get deploy -n monitoring kube-prometheus-stack-operator -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: quay.io/prometheus-operator/prometheus-operator:v0.93.1
  - id: crds-applied-by-flux-createreplace
    why: >-
      §3 relies on Flux applying the chart's `crds/` directory on upgrade
      (install AND upgrade policy CreateReplace). With `Skip` or `Create` the
      CRDs would silently stay at 0.93.1 under a 0.94.0 operator and the
      upstream UPGRADE.md `kubectl apply --server-side` step would be required.
    run: kubectl get helmrelease -n monitoring kube-prometheus-stack -o jsonpath='{.spec.install.crds}/{.spec.upgrade.crds}'
    expect_exact: CreateReplace/CreateReplace
  - id: bundled-grafana-stays-disabled
    why: >-
      Grafana is a SEPARATE HelmRelease (grafana-community 13.2.4, 69cf5388).
      91.4.0 adds GrafanaDatasource provisioning under the bundled grafana
      subchart; that must stay inert. If someone flipped `grafana.enabled`,
      this bump would ALSO roll out a second Grafana on the same hostname.
    run: kubectl get configmap -n monitoring kube-prometheus-stack-values -o jsonpath='{.data.values\.yaml}' | grep -A1 '^grafana:' | tail -1 | tr -d ' '
    expect_exact: "enabled:false"
  - id: no-bundled-grafana-deployment-exists
    why: >-
      The values premise above checks intent; this checks outcome. A
      kube-prometheus-stack-grafana Deployment would mean the subchart is live
      regardless of what the ConfigMap says.
    run: kubectl get deploy -n monitoring -o name | grep -c kube-prometheus-stack-grafana
    expect_exact: "0"
  - id: prometheus-engine-unchanged-by-this-bump
    why: >-
      91.4.0 ships prometheus v3.14.0-distroless — the SAME image that is live —
      so this plan claims no Prometheus engine change (no TSDB format risk).
      If the live Prometheus image differs, that claim is stale and the WAL /
      TSDB compatibility question must be re-asked.
    run: kubectl get prometheus -n monitoring kube-prometheus-stack -o jsonpath='{.spec.image}'
    expect_exact: quay.io/prometheus/prometheus:v3.14.0-distroless
  - id: tsdb-pvc-bound-to-static-pv
    why: >-
      The Prometheus pod restarts and must re-attach the SAME volume. The PVC
      is pinned to the speaking-name static PV `prometheus-tsdb`; if that pin
      is gone the StatefulSet could regenerate an EMPTY dynamic volume on
      restart and the "TSDB floor unchanged" verification in §4 has no meaning.
    run: kubectl get pvc -n monitoring prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0 -o jsonpath='{.spec.volumeName}/{.status.phase}'
    expect_exact: prometheus-tsdb/Bound
  - id: alertmanagerconfig-api-still-v1alpha1
    why: >-
      Three AlertmanagerConfig objects (monitoring/telegram, monitoring/
      claude-watch-webhook, storage/telegram) and three ScrapeConfigs are
      v1alpha1. Operator 0.94.0's CRDs still serve ONLY v1alpha1 for both
      (verified against the 91.4.0 chart files), so no API migration is
      needed. If a served version other than v1alpha1 appears, re-check.
    run: kubectl get crd alertmanagerconfigs.monitoring.coreos.com -o jsonpath='{.spec.versions[*].name}'
    expect_exact: v1alpha1
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
generated: "2026-09-15"
---

# kube-prometheus-stack chart 90.0.0 → 91.4.0 (prometheus-operator v0.93.1 → v0.94.0)

## 1) Summary & why held

Bump the `kube-prometheus-stack` HelmRelease in `monitoring` from chart **90.0.0**
to **91.4.0**. This is the cluster's Prometheus / Alertmanager / prometheus-operator
stack — every PrometheusRule (86), ServiceMonitor (49), PodMonitor (3), Probe (4),
ScrapeConfig (3) and AlertmanagerConfig (3) in the cluster is interpreted by it, and
the maintenance-window health gate, the sweep's alert-watcher and all five SLOs read
from it.

Held because it is a chart **major**. Upstream bumps the major exactly when the
CRDs change, and this one does:

> **From 90.x to 91.x**
> This version upgrades Prometheus-Operator to v0.94.0
> The operator's ClusterRole no longer grants wildcard verbs, following the tightened RBAC shipped upstream in v0.94.0.
> Since 68.4.0 it is also possible to use `crds.upgradeJob.enabled` for upgrading the CRDs.
> For traditional upgrades, please run these commands to update the CRDs before applying the upgrade.
>
> (verbatim from `charts/kube-prometheus-stack/UPGRADE.md` at tag
> `kube-prometheus-stack-91.4.0`, followed by the ten `kubectl apply --server-side -f
> …/prometheus-operator/v0.94.0/example/prometheus-operator-crd/monitoring.coreos.com_*.yaml`
> commands — which Flux `CreateReplace` performs for us, premise
> `crds-applied-by-flux-createreplace`)

**What actually changes, measured against the two chart tags (not the summary):**

| | 90.0.0 (live) | 91.4.0 | Effect here |
|---|---|---|---|
| prometheus-operator (appVersion) | v0.93.1 | **v0.94.0** | operator Deployment rolls; config-reloader sidecar in BOTH StatefulSets moves → **Prometheus and Alertmanager pods restart once** |
| prometheus image | v3.14.0-distroless | v3.14.0-distroless | **unchanged** — no TSDB/WAL format risk |
| alertmanager image | v0.34.0 | v0.34.0 | **unchanged** |
| kube-state-metrics subchart | 8.4.2 (image v2.20.0) | 8.5.0 (image v2.20.0) | chart-only; image identical |
| node-exporter subchart | 4.56.3 (image v1.12.1) | 4.57.0 (image v1.12.1) | chart-only; image identical |
| grafana subchart | 13.2.2 | 13.2.4 | subchart **workloads inert** (`grafana.enabled: false`, premise) — **but** `grafana.forceDeployDashboards: true` (`helmvalues.yaml`) makes the kps chart itself render **28** `grafana_dashboard=1` ConfigMaps (live count 2026-09-15) that the separate Grafana's `grafana-sc-dashboard` sidecar loads, and **10 of them change content** in 91.4.0 (upstream kube-prometheus mixin refresh, commit `f3f97b1` in the template header). Dashboard JSON only — harmless; §4.7 checks the sidecar picked them up and the count did not move |
| CRDs (`operator.prometheus.io/version`) | 0.93.1 | **0.94.0** | all 10 replaced by Flux `CreateReplace` |
| values.yaml (non-comment diff) | — | only ADDED keys: `clusterPeerName`, `datasourcesEnabled`, `retentionPercentage`, `tsdb.chunkEncoding`, `staleSeriesCompactionThreshold`, `prometheusSpec.rules` (a new template branch — the top-level `rules:`/`defaultRules` keys already existed at 90.0.0), `schedulerName`; one type change `admissionWebhooks.matchConditions: {}` → `[]` | **no removed or renamed values**; we set none of the changed keys |

Per-release content of the 91.x line (GitHub releases, 2026-09-13/14): 91.0.0 = the
operator bump (PR 7269); 91.1.0 = `retentionPercentage` + `clusterPeerName` values;
91.2.0 = `rules`/`tsdb`/thanosRuler spec gaps; 91.2.1 = webhook `matchConditions`
rendered as a list; 91.2.2/91.2.3 = docs + CRD-upgrade-job labels; 91.3.0 = ksm
subchart; 91.4.0 = optional `GrafanaDatasource` provisioning (default off).

Prometheus-operator **v0.94.0** (2026-09-09) changes that could bite, checked against
our objects:

- *[CHANGE] discard zero-value duration fields (`retention`, `clusterGossipInterval`,
  `clusterPushpullInterval`, `clusterPeerTimeout`) in Alertmanager resources instead
  of passing them as CLI flags … Ignored fields are reported via the `IgnoredFields`
  status condition.* — our `alertmanagerSpec` sets none of these. The regenerated
  Alertmanager StatefulSet may differ in flags; that is the restart, not a failure.
- *[CHANGE] Reject empty strings in `namespaceDiscovery.names`, `consulSDConfig.*`
  … in the ScrapeConfig CRD; named enums for Hetzner/DockerSwarm/OpenStack.* — our
  three ScrapeConfigs (`macos-scrapeconfigs.yaml`: static macOS targets) use none of
  those blocks.
- *[ENHANCEMENT] Tighten the operator's ClusterRole by replacing wildcard verbs with
  explicit permissions per resource.* — the chart ships the matching ClusterRole. The
  residual risk is an upstream omission; §4.6 checks the new operator's log for
  `forbidden`.
- *[FEATURE] Expose status conditions as Prometheus metrics* — new series appear
  (`prometheus_operator_*_status_condition`-style); head-series count rises slightly.

**Not a false positive, but not dramatic either.** The hold is correct because the
CRD replace and the double restart are real, and because this is the one component
whose failure blinds every other verification in the window. It is `risk: medium`
because nothing migrates, the engine images do not move, and the revert is genuine.

**Retention (F-741361a7) is untouched.** `retention: 7d` / `retentionSize: 20GB` live
in our values ConfigMap and this bump does not alter them. 91.1.0 does expose the
new `retentionPercentage` field, which is a possible lever for that finding's
option (b) — a separate operator decision, not part of this plan.

### The CRD-ownership contention this plan must live with (read before executing)

The ten `monitoring.coreos.com` CRDs are written by **two** HelmReleases, both with
`crds: CreateReplace`, and the last one to upgrade wins:

```
alertmanagerconfigs / alertmanagers / prometheusagents / prometheuses /
prometheusrules / thanosrulers         -> helm.toolkit.fluxcd.io/name=kube-prometheus-stack, opver 0.93.1
podmonitors / probes / scrapeconfigs /
servicemonitors                        -> helm.toolkit.fluxcd.io/name=otel-operator,          opver 0.92.0  (generation 30)
```

`otel-operator` is the `opentelemetry-kube-stack` chart (0.20.9, upgraded by Step 0 on
2026-09-14 05:45) whose values default to `crds.installPrometheus: true`. It bundles an
older copy of four of these CRDs, and each of its near-weekly patch bumps stamps them
back to 0.92.0 — which is why they read 0.92.0 today six days after kps 90.0.0 wrote
0.93.1. Consequences for this plan:

1. After this upgrade all ten will read **0.94.0** (§4.3 asserts it). The 0.94.0
   operator runs fine against the older 0.92.0 schemas too (we use no 0.93+/0.94+
   fields on those four kinds); what the contention costs is validation of new
   fields, not function.
2. **The durable fix is its own plan, and this plan depends on it:
   `prometheus-crd-ownership` (`depends_on`, sweep record F-a85e8943).** It sets
   `crds.installPrometheus: false` on the otel-operator HelmRelease. The
   cascade-delete question that made this a "must investigate first" item has been
   answered in that plan with three-sourced proof: the four CRDs come from a
   `crds/` directory in the condition-gated `prometheus-crds` subchart, they are
   not Helm release resources (`helm get manifest` has zero CRDs; no release
   annotation on the objects), and helm-controller prunes `condition: false`
   subcharts before collecting `crds/` and never deletes on `CreateReplace`. So the
   flip removes a *writer* and deletes nothing. **Ordering:** that plan runs in an
   earlier window (its human-gated first execution), then this one — after which
   all ten CRDs are written by kube-prometheus-stack alone and §4.3 holds
   permanently instead of until the next otel patch bump. It does NOT rewrite the
   four CRDs itself, so §2.5's expected pre-state is unchanged by it.
3. **Effect on `otel-operator-0.21.0`.** This upgrade re-stamps all ten CRDs and
   the `helm.toolkit.fluxcd.io/name` label follows the last applier (observed: the
   four flipped to `otel-operator` on the 2026-09-14 otel Step-0 bump). Landing this
   plan first therefore changes the four's label to `kube-prometheus-stack`; the otel
   plan measures that in its §2.6 instead of gating on it (its former premise
   `this-hr-owns-the-prometheus-crds` was removed for exactly this reason). The
   preferred order is still otel-operator-0.21.0 **before** this plan (§6).

## 2) Pre-checks

Run inside the window, **after Step 0 has finished and its health gate has passed**
(§6). Every check has a pass condition; a fail is a no-go.

```bash
cd /Users/mu/code/cberg-home-nextgen
export KUBECONFIG="$PWD/kubeconfig"
```

**2.1 — Premises hold (the scheduler ran them at placement; re-run now).**

```bash
python3 runbooks/plan-premises.py kube-prometheus-stack-91.4.0 --require-premises
```
**PASS:** exit 0, 8/8 premises pass.

**2.2 — Flux fully green, nothing mid-upgrade in `monitoring`, and the dependency
has landed.** A concurrent otel-operator upgrade would race the CRD write; and
`prometheus-crd-ownership` (`depends_on`) must already be `executed` — the
scheduler enforces that at placement, this re-checks the cluster-side fact.

```bash
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'
kubectl get helmrelease -n monitoring otel-operator kube-prometheus-stack \
  -o custom-columns='NAME:.metadata.name,CHART:.status.history[0].chartVersion,READY:.status.conditions[?(@.type=="Ready").status]'
kubectl get helmrelease -n monitoring otel-operator -o jsonpath='installPrometheus=[{.spec.values.crds.installPrometheus}]{"\n"}'
```
**PASS:** both `flux get` commands print only the header; both HRs `READY=True`,
kps at `90.0.0`; `installPrometheus=[false]` (the otel HR no longer writes the
four shared CRDs). `installPrometheus=[]` = the dependency has not landed:
**no-go**, regardless of what the scheduler believed.

**2.3 — Target chart exists at the OCI source, with a negative control.**

```bash
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:prometheus-community/charts/kube-prometheus-stack:pull&service=ghcr.io" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for TAG in 91.4.0 99.99.99; do
  printf "%-10s HTTP %s\n" "$TAG" "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.manifest.v1+json" \
    "https://ghcr.io/v2/prometheus-community/charts/kube-prometheus-stack/manifests/$TAG")"
done
```
**PASS — EXACTLY:** `91.4.0 -> 200` and `99.99.99 -> 404`. *(Measured 2026-09-15:
200 / 404.)* Both 200 = intercepting proxy, result invalid.

**2.4 — Observability baseline. Write these numbers down; §4 diffs against them.**

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9099:9090 >/dev/null 2>&1 & PF1=$!
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF2=$!
sleep 4
curl -s localhost:9099/api/v1/targets | python3 -c "
import sys,json
t=json.load(sys.stdin)['data']['activeTargets']
print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))
print('down:',[(x['labels'].get('job'),x['labels'].get('instance')) for x in t if x['health']!='up'])"
curl -s localhost:9099/api/v1/rules | python3 -c "
import sys,json; g=json.load(sys.stdin)['data']['groups']
print('groups',len(g),'rules',sum(len(x['rules']) for x in g))"
curl -s localhost:9099/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)['data']['alerts'] if x['state']=='firing'
   and x['labels'].get('alertname') not in ('Watchdog','InfoInhibitor')]
print('firing:',len(a),sorted(set(x['labels'].get('alertname') for x in a)))"
curl -s -G localhost:9099/api/v1/query --data-urlencode 'query=prometheus_tsdb_head_series' \
  | python3 -c "import sys,json;print('head_series',json.load(sys.stdin)['data']['result'][0]['value'][1])"
curl -s -G localhost:9099/api/v1/query --data-urlencode 'query=prometheus_tsdb_lowest_timestamp_seconds' \
  | python3 -c "import sys,json,datetime;v=float(json.load(sys.stdin)['data']['result'][0]['value'][1]);print('tsdb_floor',datetime.datetime.fromtimestamp(v,datetime.timezone.utc))"
curl -s 'localhost:9093/api/v2/alerts?filter=alertname%3DWatchdog' | python3 -c "
import sys,json;a=json.load(sys.stdin);print('watchdog_in_AM',len(a),[x['status']['state'] for x in a])"
curl -s localhost:9093/api/v2/silences | python3 -c "
import sys,json;print('active_silences',len([x for x in json.load(sys.stdin) if x['status']['state']=='active']))"
kill $PF1 $PF2 2>/dev/null
```
**Baseline measured 2026-09-15 01:58Z:** `targets 98 up 98` · `down: []` ·
`groups 117 rules 474` · `firing: 1 ['LonghornVolumeAllocationHigh']` ·
`head_series 353092` · `tsdb_floor 2026-09-08 00:00Z` · `watchdog_in_AM 1 ['active']` ·
`active_silences 0`.
**PASS:** targets all up, `watchdog_in_AM` = 1 active. Any target down is a no-go
(the post-upgrade count comparison would be ambiguous).

**2.5 — CRD pre-state (so §4.3 is a diff, not a guess).**

```bash
kubectl get crd -o json | python3 -c "
import sys,json
for c in json.load(sys.stdin)['items']:
    n=c['metadata']['name']
    if n.endswith('monitoring.coreos.com'):
        print(f\"{n:45s} opver={c['metadata'].get('annotations',{}).get('operator.prometheus.io/version')} hr={c['metadata'].get('labels',{}).get('helm.toolkit.fluxcd.io/name')}\")"
```
**Expected (2026-09-15):** 6 × `0.93.1 hr=kube-prometheus-stack`, 4 × `0.92.0
hr=otel-operator` (the contention in §1). Ten CRDs total. This picture is
**unchanged** by `prometheus-crd-ownership` (it removes the writer without
rewriting the objects) and by `otel-operator-0.21.0` having run before it (a
byte-identical 0.92.0 re-apply; only the generation moves). Any other picture:
stop and re-derive §1 before proceeding.

**2.6 — Storage: the TSDB volume is healthy and backed up.**

```bash
kubectl get volume -n storage prometheus-tsdb -o jsonpath='{.status.state}/{.status.robustness}/{.status.lastBackupAt}{"\n"}'
```
**PASS:** `attached/healthy/<timestamp within 48h>`.

## 3) Steps

GitOps only. Nothing here touches the cluster directly; Flux does the apply.

**3.1 — Silence rollout noise (SOP §4 Step 1) and drop the active-update marker.**
Prometheus cannot fire while it restarts, but the Alertmanager restart and the
operator's outgoing-pod teardown (see `docs/sops/monitoring.md` "Chart-bump rollout
noise") produce `KubePod*`/`KubeStatefulSet*`/`TargetDown` transients. 1-hour TTL.

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF=$!
sleep 3
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"monitoring","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"KubePod.*|KubeStatefulSet.*|KubeDeployment.*|TargetDown|PrometheusOperator.*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window",
  "comment":"kube-prometheus-stack chart 90.0.0->91.4.0 rollout. auto-expires 1h"}'
kill $PF 2>/dev/null
runbooks/update-marker.sh add kube-prometheus-stack monitoring 1 "chart 90.0.0->91.4.0"
```

Do **not** silence `Watchdog`, `Prometheus*` or `Alertmanager*` alerts — those are the
signals §4 reads. Leave `upgrade.remediation` at `retries: 3` (rollback on failure is
the desired behaviour here: there is no init migration to protect).

**3.2 — The bump. One line, one file.**

```bash
sed -i '' 's/^      version: 90\.0\.0$/      version: 91.4.0/' \
  kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml
git --no-pager diff kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml
```
**Expected diff:** exactly `-      version: 90.0.0` / `+      version: 91.4.0`. No
values change: `helmvalues.yaml` needs nothing for 91.x (no removed/renamed keys, §1).

**3.3 — Commit and push (`--only`, shared worktree).**

```bash
cat > /tmp/kps-msg.txt <<'EOF'
chore(monitoring)!: kube-prometheus-stack chart 90.0.0 -> 91.4.0 (operator v0.94.0)

Chart major: prometheus-operator v0.93.1 -> v0.94.0 with the matching CRD set
(applied by Flux CreateReplace) and the tightened operator ClusterRole.
Prometheus (v3.14.0) and Alertmanager (v0.34.0) images are unchanged; both
pods restart once for the config-reloader sidecar. kube-state-metrics and
node-exporter subcharts move without image changes. Bundled grafana stays
disabled; grafana is its own HelmRelease. Values untouched.

Plan: runbooks/maintenance/plans/kube-prometheus-stack-91.4.0.md
Finding: F-f1e564f2

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012bXdxrZGGHNy5e4RnF6seD
EOF
git fetch origin main && git merge --ff-only origin/main
git commit --only kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml -F /tmp/kps-msg.txt
git show --stat HEAD          # exactly ONE file
git push origin main
```

**3.4 — Watch the rollout (no manual reconcile; the webhook drives it).** The
Kustomization applies the new HR spec and helm-controller upgrades immediately on
the spec change. Expected sequence, ~5-8 min end to end: HR `Reconciling` → CRDs
replaced → operator Deployment rolls → operator regenerates both StatefulSets →
`prometheus-kube-prometheus-stack-0` and `alertmanager-kube-prometheus-stack-0`
terminate and come back (Prometheus replays WAL; with ~350k head series budget
1-3 min before `2/2 Ready`).

```bash
kubectl get helmrelease -n monitoring kube-prometheus-stack -w      # until Ready=True with 91.4.0
kubectl get pods -n monitoring -l 'app.kubernetes.io/name in (prometheus,alertmanager)' -w
```

If the HR has not started reconciling 5 minutes after the push (webhook missed):
`mise exec -- flux reconcile source git flux-system` — that is the one manual
reconcile the SOP allows, and it only re-fetches git.

**Expected noise, NOT a failure** (`docs/sops/monitoring.md` §Troubleshooting):
`InvalidConfiguration … context canceled` and readiness `connection refused` from the
**outgoing** operator pod. Do not revert on those; run §4.

**3.5 — On success:** clear the marker, delete the silence early if §4 is green
before it expires, and retire this plan file in the same commit series
(`README.md`: plans are transient).

```bash
runbooks/update-marker.sh clear kube-prometheus-stack
```

## 4) Verification

Floor: HR Ready, pods healthy. The section is the alert pipeline end to end and
the CRD contents.

**4.1 — HelmRelease and images.**

```bash
kubectl get helmrelease -n monitoring kube-prometheus-stack \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion} {.status.history[0].appVersion}{"\n"}'
kubectl get deploy -n monitoring kube-prometheus-stack-operator -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl get sts -n monitoring prometheus-kube-prometheus-stack alertmanager-kube-prometheus-stack \
  -o jsonpath='{range .items[*]}{.metadata.name}: {range .spec.template.spec.containers[*]}{.image} {end}{"\n"}{end}'
kubectl get pods -n monitoring -l 'app.kubernetes.io/name in (prometheus,alertmanager,kube-prometheus-stack-prometheus-operator)'
helm history kube-prometheus-stack -n monitoring | tail -2
```
**PASS:** `True 91.4.0 v0.94.0`; operator image `…prometheus-operator:v0.94.0`;
each StatefulSet lists `prometheus-config-reloader:v0.94.0` next to the UNCHANGED
`prometheus:v3.14.0-distroless` / `alertmanager:v0.34.0`; all pods `Running`, `2/2`,
0 restarts after settle; helm shows revision 40 `deployed` and 39 `superseded`.

**4.2 — Bundled grafana still absent; separate grafana untouched.**

```bash
kubectl get deploy -n monitoring -o name | grep -c kube-prometheus-stack-grafana   # 0
kubectl get helmrelease -n monitoring grafana -o jsonpath='{.status.history[0].chartVersion} {.status.conditions[?(@.type=="Ready")].status}{"\n"}'  # 13.2.4 True
```

**4.3 — CRDs: all ten at 0.94.0, and served versions unchanged.**

```bash
kubectl get crd -o json | python3 -c "
import sys,json
rows=[c for c in json.load(sys.stdin)['items'] if c['metadata']['name'].endswith('monitoring.coreos.com')]
for c in rows:
    print(f\"{c['metadata']['name']:45s} opver={c['metadata'].get('annotations',{}).get('operator.prometheus.io/version')} served={[v['name'] for v in c['spec']['versions'] if v.get('served')]}\")
print('total',len(rows),'at 0.94.0:',sum(1 for c in rows if c['metadata'].get('annotations',{}).get('operator.prometheus.io/version')=='0.94.0'))"
```
**PASS:** `total 10 at 0.94.0: 10`; served versions identical to §2.5 (`v1` for
alertmanagers/podmonitors/probes/prometheuses/prometheusrules/servicemonitors/
thanosrulers, `v1alpha1` for alertmanagerconfigs/prometheusagents/scrapeconfigs).
**If exactly the four formerly otel-owned CRDs read 0.92.0:** an otel-operator
upgrade ran after ours (check `helm history otel-operator -n monitoring`) **while
still collecting the Prometheus CRDs** — with `prometheus-crd-ownership` executed
(`depends_on`, §2.2) that cannot happen, so it means that fix was reverted or did
not take. Record it as a finding against `prometheus-crd-ownership`; it is the §1
contention, not a failed kps apply — do not retry the kps upgrade.

**4.4 — Alert pipeline end to end (the load-bearing section).**

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9099:9090 >/dev/null 2>&1 & PF1=$!
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & PF2=$!
sleep 4
# (a) scrape target count unchanged, all up
curl -s localhost:9099/api/v1/targets | python3 -c "
import sys,json
t=json.load(sys.stdin)['data']['activeTargets']
print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))
print('down:',[(x['labels'].get('job'),x['labels'].get('instance')) for x in t if x['health']!='up'])"
# (b) rules loaded via /api/v1/rules — same group/rule count as baseline
curl -s localhost:9099/api/v1/rules | python3 -c "
import sys,json; g=json.load(sys.stdin)['data']['groups']
print('groups',len(g),'rules',sum(len(x['rules']) for x in g))
print('Watchdog rule present:', any(r.get('name')=='Watchdog' for x in g for r in x['rules']))"
# (c) Watchdog is firing in Prometheus AND has reached Alertmanager AFTER the restart
curl -s localhost:9099/api/v1/alerts | python3 -c "
import sys,json
a=json.load(sys.stdin)['data']['alerts']
print('Watchdog firing in Prometheus:', any(x['labels'].get('alertname')=='Watchdog' and x['state']=='firing' for x in a))
f=[x['labels'].get('alertname') for x in a if x['state']=='firing' and x['labels'].get('alertname') not in ('Watchdog','InfoInhibitor')]
print('other firing:',sorted(set(f)))"
curl -s 'localhost:9093/api/v2/alerts?filter=alertname%3DWatchdog' | python3 -c "
import sys,json;a=json.load(sys.stdin)
print('watchdog_in_AM',len(a),[(x['status']['state'],x['updatedAt']) for x in a])"
# (d) Alertmanager loaded OUR config (telegram receiver from the AlertmanagerConfig CRs)
curl -s localhost:9093/api/v2/status | python3 -c "
import sys,json;d=json.load(sys.stdin)
print('AM',d['versionInfo']['version'],'telegram receiver in config:', 'telegram' in d['config']['original'])"
kill $PF1 $PF2 2>/dev/null
```
**PASS:** (a) `targets 98 up 98`, `down: []` — same count as §2.4 (a ±1 drift is
acceptable ONLY if explained by a pod that legitimately came or went during the
window; a lower count with `down:` entries is a fail). (b) `groups 117 rules 474`
(baseline) — an equal-or-higher count; a LOWER count means PrometheusRules stopped
being selected (the `release: kube-prometheus-stack` ruleSelector still applies —
check the operator log for rejected rules). `Watchdog rule present: True`.
(c) `Watchdog firing in Prometheus: True`; `watchdog_in_AM 1` with state `active`
and an `updatedAt` **later than the Alertmanager pod's start time** — that is the
proof the pipeline re-established itself post-restart, not a stale reading. `other
firing` equals the §2.4 set (today: `['LonghornVolumeAllocationHigh']`) plus at most
the transients the §3.1 silence covers. (d) `AM 0.34.0`, `telegram receiver in
config: True`.

**4.5 — CONTENTS ASSERTIONS (chart bump on the thing that IS the scraper).**

```
CONTENTS ASSERTION 1: series still ARRIVE after the restart — measured by
  count(up == 1) and a representative series evaluated over a range that starts
  AFTER the Prometheus pod's new start time; compared to the §2.4 target count.
CONTENTS ASSERTION 2: the TSDB the new pod mounted is the OLD one — measured by
  prometheus_tsdb_lowest_timestamp_seconds; compared to the §2.4 tsdb_floor
  (2026-09-08 00:00Z at plan time; must be unchanged, never "now").
CONTENTS ASSERTION 3: alerts still TRAVERSE Prometheus -> Alertmanager — measured
  by increase(alertmanager_alerts_received_total[5m]) > 0 on the new Alertmanager
  pod; compared to zero.
```

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9099:9090 >/dev/null 2>&1 & PF=$!
sleep 4
START=$(kubectl get pod -n monitoring prometheus-kube-prometheus-stack-0 -o jsonpath='{.status.startTime}')
echo "prometheus pod started: $START"
curl -s -G localhost:9099/api/v1/query --data-urlencode 'query=count(up == 1)' \
  | python3 -c "import sys,json;print('up==1 now:',json.load(sys.stdin)['data']['result'][0]['value'][1])"
curl -s -G localhost:9099/api/v1/query --data-urlencode "query=count_over_time(node_load1{job=\"node-exporter\"}[2m])" \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('node-exporter samples last 2m per node:',[(x['metric'].get('instance'),x['value'][1]) for x in r])"
curl -s -G localhost:9099/api/v1/query --data-urlencode 'query=prometheus_tsdb_lowest_timestamp_seconds' \
  | python3 -c "import sys,json,datetime;v=float(json.load(sys.stdin)['data']['result'][0]['value'][1]);print('tsdb_floor',datetime.datetime.fromtimestamp(v,datetime.timezone.utc))"
curl -s -G localhost:9099/api/v1/query --data-urlencode 'query=prometheus_tsdb_head_series' \
  | python3 -c "import sys,json;print('head_series',json.load(sys.stdin)['data']['result'][0]['value'][1])"
curl -s -G localhost:9099/api/v1/query --data-urlencode 'query=sum(increase(alertmanager_alerts_received_total[5m]))' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('AM alerts received 5m:',r[0]['value'][1] if r else 'NO DATA')"
kill $PF 2>/dev/null
```
**PASS:** `up==1 now` == the §4.4(a) up count (98); every node shows ≥ 3 samples in
the last 2 m (≥ 5 min after the pod start — wait if not); `tsdb_floor` **identical**
to §2.4 (a floor equal to the pod start time means an EMPTY volume was mounted —
STOP, §5, and check the PVC binding); `head_series` within ~±10 % of 353092 (a
small rise from the new status-condition metrics is expected; a collapse to a few
thousand means targets are not being scraped); `AM alerts received 5m` > 0 and not
`NO DATA`.

**4.6 — Operator RBAC tightening did not break the operator.**

```bash
kubectl logs -n monitoring deploy/kube-prometheus-stack-operator --since=15m | grep -ciE 'forbidden|cannot (list|watch|get|update|patch|create|delete)' 
kubectl logs -n monitoring deploy/kube-prometheus-stack-operator --since=15m | grep -iE 'level=(error|warn)' | grep -v 'context canceled' | tail -20
kubectl get prometheus,alertmanager -n monitoring -o jsonpath='{range .items[*]}{.kind}/{.metadata.name}: {range .status.conditions[*]}{.type}={.status} {end}{"\n"}{end}'
```
**PASS:** first command prints `0` (grep -c exits 1 on zero matches — that is the
pass); no error lines from the NEW pod other than the documented teardown noise;
both CRs `Available=True Reconciled=True`.

**4.7 — Grafana still reads this Prometheus, and picked up the refreshed dashboards**
(the separate HelmRelease's datasource points at
`kube-prometheus-stack-prometheus.monitoring.svc:9090`; its `grafana-sc-dashboard`
sidecar loads the 28 `grafana_dashboard=1` ConfigMaps this chart ships, 10 of which
change content in 91.4.0 — §1).

```bash
kubectl port-forward -n monitoring svc/grafana 3000:80 >/dev/null 2>&1 & PF=$!
sleep 3
curl -s -o /dev/null -w '%{http_code}\n' localhost:3000/api/health
kill $PF 2>/dev/null
kubectl get cm -n monitoring -l grafana_dashboard=1 -o json | python3 -c "
import sys,json; i=json.load(sys.stdin)['items']
print('kps dashboard ConfigMaps:', sum(1 for x in i if x['metadata'].get('annotations',{}).get('meta.helm.sh/release-name')=='kube-prometheus-stack'), 'of', len(i), 'total')"
kubectl logs -n monitoring deploy/grafana -c grafana-sc-dashboard --since=30m | grep -ciE 'writing|placing|updated' || true
```
**PASS:** `200`; `kps dashboard ConfigMaps: 28 of 33 total` (same as 2026-09-15 — a
lower kps count means the chart stopped rendering a dashboard, a higher one is a
new upstream dashboard to look at, neither is a rollback trigger on its own); the
sidecar log shows ≥ 1 write/placing line since the upgrade (it re-reads the changed
ConfigMaps — `0` means the sidecar did not see them; check the sidecar's
`--since` window covers the HR upgrade time before reading it as a fault). A
datasource query via the UI is the operator's optional extra.

## 5) Rollback

Trigger: any §4 fail that a second read 5 minutes later does not clear, or Flux
remediation already rolled the release back on its own (`helm history` shows a
`rollback` revision) — in which case the git revert is still required so the
manifest matches the cluster.

**5.1 — Git revert (the real rollback).**

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
git revert --no-edit <sha-of-3.3-commit>
git show --stat HEAD          # exactly helmrelease.yaml
git push origin main
```

Flux upgrades the release to chart 90.0.0 — a "downgrade" is just an upgrade
action with an older chart, so `upgrade.crds: CreateReplace` **re-applies the
90.0.0 CRD files (`operator.prometheus.io/version: 0.93.1`) in the same action**.
The CRD downgrade is safe because no CR uses a 0.94.0-only field (`retentionPercentage`,
`clusterPeerName` — premise-level fact: we set neither); Kubernetes prunes unknown
fields on the next write of an object, it does not reject the CRD update. Operator
returns to v0.93.1, both StatefulSets regenerate with the v0.93.1 reloader and
restart once more (same ~3-5 min blind spot).

**5.2 — If helm is wedged `pending-upgrade`** (crash-loop during `--wait`):

```bash
helm history kube-prometheus-stack -n monitoring          # revision 39 = 90.0.0 must still be present (maxHistory: 2)
helm rollback kube-prometheus-stack 39 -n monitoring --wait=false
mise exec -- flux reconcile helmrelease -n monitoring kube-prometheus-stack --force
```
The `flux reconcile helmrelease --force` here is a **deliberate exception** to the
SOP's "source git only" allowance (§3.4): it exists only to un-wedge a
`pending-upgrade` release that the git revert alone cannot, and it is the
break-glass path, not a step. `helm rollback` restores release resources but
**does NOT touch CRDs** — after it,
either leave the CRDs at 0.94.0 (harmless under a 0.93.1 operator: superset schema)
or let the git revert's Flux upgrade re-stamp them to 0.93.1. Do not
`kubectl apply --server-side` the 0.93.1 CRD files by hand while a helm-controller
reconcile is in flight.

**5.3 — Confirm the cluster is back.**

```bash
kubectl get helmrelease -n monitoring kube-prometheus-stack -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion} {.status.history[0].appVersion}{"\n"}'   # True 90.0.0 v0.93.1
kubectl get deploy -n monitoring kube-prometheus-stack-operator -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'  # :v0.93.1
kubectl get crd prometheuses.monitoring.coreos.com -o jsonpath='{.metadata.annotations.operator\.prometheus\.io/version}{"\n"}'  # 0.93.1 (after the git-revert path)
```
Then re-run §4.4 and §4.5 in full — the rollback restarted Prometheus and
Alertmanager too, and the same "Watchdog reached AM after the restart" and
"tsdb_floor unchanged" proofs apply. Clear the marker
(`runbooks/update-marker.sh clear kube-prometheus-stack`), keep the plan file with
`status: blocked` and the failure quoted.

## 6) Interference notes

- **This stack IS the window's instrument — this plan MUST run LAST in its
  window, or alone. A constraint, not a preference.** The maintenance-window
  health gate, Step 0's auto-revert decision, the window agent's Step 4 "never
  start the next plan on a degraded cluster" check, the sweep alert-watcher and all
  SLO burn-rate reads come from this Prometheus, which is blind for 2-5 min during
  §3.4. **Order rule:** run this plan only AFTER Step 0 (safe-update batch) has
  been applied AND its health gate has PASSED on the old stack, and run **no other
  plan** — not its steps, not its verification — after §3.2 in the same window: a
  verification that queries Prometheus while it replays its WAL reads "no data" as
  failure, and a Step-4 gate that reads it mid-restart would refuse to continue or
  misread the restart as a regression. The derived class is AUTO-NIGHT, so this
  can run unattended: the sequencer has to honour "last or alone" without a human
  in the loop.
- **Blind spot:** ~2-5 min with no scraping/evaluation while
  `prometheus-kube-prometheus-stack-0` restarts, ~1 min with no routing while
  `alertmanager-kube-prometheus-stack-0` restarts. Alerts that would have fired in
  that gap fire late, not never; `absent()`-guarded rules
  (`absenty-alerts.yaml` et al.) may need one extra evaluation cycle to settle.
- **Cluster-scoped CRD replace.** Every namespace holding a ServiceMonitor /
  PrometheusRule / Probe / ScrapeConfig / AlertmanagerConfig is touched in the
  schema sense (no object is rewritten). No other plan should be adding or
  changing those objects in the same window — a `PrometheusRule` applied during the
  CRD swap can land on the old or new schema unpredictably (identical for our
  fields, but the apply can transiently 404 during the Update).
- **otel-operator (`opentelemetry-kube-stack`) shares four of these CRDs.** With
  `prometheus-crd-ownership` executed first (`depends_on`), its near-weekly Step 0
  patch bumps no longer write them, so a Step 0 otel bump in the same window is
  harmless as long as it finishes BEFORE this plan (Step 0 ordering already ensures
  that), and later otel bumps cannot revert the four to 0.92.0 any more. If §2.2
  shows `installPrometheus=[]`, the dependency has not landed — no-go.
- **`otel-operator-0.21.0` — hard conflict (`conflicts_with`), and this plan should
  run AFTER it.** Both HRs `CreateReplace` the same four CRDs, so never the same
  window. Ordering effect if THIS plan lands first: all ten CRDs read 0.94.0 and the
  four's `helm.toolkit.fluxcd.io/name` label flips from `otel-operator` to
  `kube-prometheus-stack` (the label follows the last applier). The otel plan no
  longer gates on that label (its former premise `this-hr-owns-the-prometheus-crds`
  was removed and replaced by an in-window measurement, §1 point 3), so it stays
  schedulable either way — but if it then runs *without* the ownership fix it
  downgrades the four to 0.92.0 (the accepted contention F-a85e8943). Preferred
  sequence: otel-operator-0.21.0 (nightly) → prometheus-crd-ownership (attended) →
  this plan (a later nightly, alone).
- **`unpoller-v5.2.5` — hard conflict (`conflicts_with`).** Its §4 verification
  port-forwards and queries this Prometheus over a ≥5-min settle; the restart blind
  spot would read as an unpoller regression and trigger a needless revert. Never the
  same window.
- **Grafana.** Separate HelmRelease (`grafana`, chart 13.2.4). Its datasource and
  its `ServiceMonitor` are consumers of this stack; it does not restart. The bundled
  grafana subchart is disabled and stays disabled (two premises).
- **Storage.** `prometheus-tsdb` is an RWO `longhorn-static` volume on a
  StatefulSet — immune to the Deployment multi-attach lottery
  (`docs/sops/longhorn-rwo-multi-attach.md`). The Longhorn `daily-backup-all-volumes`
  CronJob (ns `storage`; `backup-of-all-volumes` does not exist — verified
  2026-09-15) runs 03:00; the `nightly` window starts 03:30, so a backup may still be
  finishing snapshots on this volume while the pod restarts — harmless (snapshot
  then attach), but do not run this plan concurrently with a Longhorn engine/manager
  plan.
- **Why `conflicts_with` and `depends_on` are set (2026-09-15 review):** three
  live plans touch `monitoring` — `otel-operator-0.21.0` and `unpoller-v5.2.5` are
  both AUTO-NIGHT with `window: null`, exactly like this one, so the scheduler
  could pack all three into one unattended nightly; `window-scheduler.py` keys slot
  exclusion on `conflicts_with` only, and the `shared: [monitoring]` intersection is
  a shallow post-placement warning. The prose "serialize" rules that earlier drafts
  relied on are not read by the scheduler. `prometheus-crd-ownership` is both a
  dependency (ordering) and a conflict (never the same window). `grafana-chart-13.2.3`
  is superseded and not a constraint.
- **Future patch/minor bumps of this chart are Step 0 material** — the chart is
  not on the deny-list; only the major crosses into PLAN. After this lands, 91.x
  patches will auto-apply nightly under the normal gates.
