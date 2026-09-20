---
plan_id: otel-operator-0.23.0
component: otel-operator               # HelmRelease name in `monitoring`. The CHART is the
                                       # umbrella `opentelemetry-kube-stack` (subcharts:
                                       # otel-crds, prometheus-crds, opentelemetry-operator);
                                       # coverage.py keys the item on the HR name.
pr: null                               # no Renovate PR. Verified 2026-09-19: this lands via
                                       # coverage.py's direct-bump/PLAN path (a hand edit),
                                       # not by merging a PR.
kind: chart
current: "0.21.0"                      # MEASURED live 2026-09-19, not copied: HR
                                       # .spec.chart.spec.version = 0.21.0, helm revision 24
                                       # (deployed 2026-09-17T01:53:52Z, commit 9a35168f).
target: "0.23.0"                       # released 2026-09-18T18:52:35Z
update_type: minor                     # 0.x line: the MINOR digit is the breaking axis.
                                       # AND the appVersion moves underneath it:
                                       # 0.154.0 -> 0.159.0 (five operator minors), with the
                                       # opentelemetry-operator SUBCHART 0.119.0 -> 0.123.0.
                                       # A chart-level "minor" is NOT a safe minor here.
risk: high                             # NOT from the render diff (that is small and fully
                                       # measured, §1.2). From the appVersion delta and the
                                       # failure MODE: operator 0.158.0 promotes TWO
                                       # NetworkPolicy feature gates to beta = ON BY DEFAULT
                                       # (§1.3), the operator `os.Exit(1)`s if that setup
                                       # errors, the generated operator policy restricts its
                                       # OWN egress to API-server IPBlocks on a CNI whose
                                       # CIDR-vs-node-identity semantics make that rule
                                       # doubtful here (§1.4), the defaulted CR field is
                                       # forward-only (survives `git revert`, §5.3), and the
                                       # blast radius is the cluster's SOLE log/metric/trace
                                       # collection path, which fails SILENTLY.
est_duration_min: 50                   # 10 pre-checks (chart pull + render A/B + four
                                       # baselines) + 3 edit/commit/push + 6 reconcile and the
                                       # operator + 3-pod DaemonSet rolls + 15 SETTLE (the ES
                                       # per-node gate in §4.4 needs a 15m window that STARTS
                                       # after the last collector pod is Ready — that is the
                                       # measurement, not padding) + 10 verification + 6 buffer.
needs_reboot: false
touches:
  namespaces:
    - monitoring
  resources:                           # every object below verified to EXIST live
                                       # 2026-09-19 via kubectl (authoring rule 1)
    - helmrelease/otel-operator                            # the only object this plan EDITS
    - deployment/otel-operator-opentelemetry-operator      # ROLLS: image 0.154.0 -> 0.159.0.
                                                           # Single replica, RollingUpdate
                                                           # 25%/25% -> a brief webhook gap
                                                           # (harmless: failurePolicy=Ignore
                                                           # on all 7 webhooks, measured §1.5)
    - daemonset/otel-operator-daemon-collector             # ROLLS all 3 pods: the operator
                                                           # stamps --collector-image, which
                                                           # moves 0.154.0 -> 0.159.0
    - opentelemetrycollector/otel-operator-daemon          # helm re-applies it; gets the new
                                                           # helm.sh/chart label. spec.image is
                                                           # ABSENT (operator supplies it)
    - service/otel-operator-daemon-collector               # ClusterIP 10250/4317/4318
    - service/otel-operator-daemon-collector-headless      # endpoints follow the pod roll
    - service/otel-operator-daemon-collector-monitoring    # 8888; NO ServiceMonitor exists,
                                                           # so this is NOT scraped (§4.7)
    - secret/otel-operator-opentelemetry-operator-controller-manager-service-cert  # REGENERATED
                                                           # on every helm upgrade
                                                           # (autoGenerateCert.recreate: true)
    - mutatingwebhookconfiguration/otel-operator-opentelemetry-operator-mutation     # caBundle
    - validatingwebhookconfiguration/otel-operator-opentelemetry-operator-validation # caBundle
    - clusterrole/otel-operator-opentelemetry-operator-manager   # + instrumentations/status
                                                           # (the ONLY RBAC change, §1.2)
    - "crd/{opampbridges,opentelemetrycollectors,targetallocators}.opentelemetry.io — CONTENT
       CHANGES (measured +56/+424/+283 lines); Flux CreateReplace WRITES them, generation 2 -> 3.
       These are the POSITIVE CONTROL in §4.2 (see F-7235625a)"
    - "crd/instrumentations.opentelemetry.io — byte-identical 0.21.0 vs 0.23.0, so it is
       re-applied with NO trace and STAYS at generation 2. Do not expect it to move."
    - "crd/{servicemonitors,podmonitors,probes,scrapeconfigs}.monitoring.coreos.com — NOT
       written by this plan, because `depends_on: prometheus-crd-ownership` means
       crds.installPrometheus is already false and the prometheus-crds subchart is no longer
       collected. Asserted UNCHANGED in §4.2 (gen 30, opver 0.92.0). If that dependency were
       skipped, this bump WOULD re-stamp them — see §6."
  shared:
    - monitoring                       # the cluster's ONLY log/metric/trace collection path.
                                       # The 3 daemon-collector pods roll one node at a time;
                                       # file_log `start_at: end` with NO storage extension
                                       # (measured), so each node LOSES its pod logs for the
                                       # ~10-30 s it is down — a gap, never backfilled. Any
                                       # other plan whose verification reads ES log continuity
                                       # in those minutes sees a hole.
                                       # Prometheus is this plan's INSTRUMENT (§4.6) and
                                       # edot-collector is the downstream OTLP sink (§4.4).
depends_on:
  - prometheus-crd-ownership           # MECHANICAL, not stylistic. That plan's premise
                                       # `otel-chart-version-whose-layout-was-verified`
                                       # expects `^0\.(20\.9|21\.0)$`. Landing THIS bump first
                                       # makes that premise FAIL, which makes a `vetted` plan
                                       # unschedulable — and kube-prometheus-stack-91.4.0
                                       # declares `depends_on: prometheus-crd-ownership`, so
                                       # one bump would block TWO vetted plans. Running it
                                       # first also removes the four Prometheus CRDs from this
                                       # plan's write set entirely. Full reasoning in §6.
conflicts_with:                        # HARD slot exclusions — window-scheduler.py keys on
                                       # this field ONLY; a shared:[monitoring] overlap is a
                                       # post-placement warning, and §6 prose schedules nothing.
  - prometheus-crd-ownership           # edits the SAME HelmRelease spec. Two otel-operator
                                       # helm upgrades in one window confound BOTH plans' CRD
                                       # assertions (and it must run in an EARLIER window
                                       # anyway — it is the depends_on above).
  - kube-prometheus-stack-91.4.0       # (a) both write the ten monitoring.coreos.com CRDs via
                                       # CreateReplace; (b) §4.6 of THIS plan reads Prometheus,
                                       # and that plan restarts Prometheus + Alertmanager — the
                                       # window's instrument is shared infra (authoring rule 4).
  - edot-collector-0.161.0             # the daemon collectors export OTLP to
                                       # edot-collector.monitoring.svc:4317, and §4.4 proves
                                       # this plan through documents landing in ES *via edot*.
                                       # If edot rolls the same night, neither plan's ES gate
                                       # can attribute a gap to its own change. That plan does
                                       # not yet name this one — a reciprocity correction to
                                       # make when this plan is vetted (§6).
  - cilium-1.20.2                      # §1.4's whole NetworkPolicy risk assessment is a
                                       # statement about the CNI's CIDR/remote-node policy
                                       # semantics; upgrading the enforcement substrate in the
                                       # same window as the change that might depend on it is
                                       # exactly backwards. A cilium roll also perturbs every
                                       # pod's networking, confounding §4.4.
  - talos-1.14.0                       # a node roll restarts every collector pod and moves
                                       # workloads between nodes, which blows up the per-node
                                       # ES assertion in §4.4 and the 98-target baseline in §4.6.
security_ref: null                     # no security driver. NOTE: this bump DOES move the
                                       # operator and collector images off 0.154.0, which is
                                       # the tag two AR-072/AR-124-accepted image findings are
                                       # written against; that is a side benefit, not the
                                       # driver, and the counts stay on the finding records.
capability_change: true                # DELIBERATELY true. Operator 0.159.0 gains the ability
                                       # to CREATE NetworkPolicies for itself and its operands
                                       # by DEFAULT (§1.3) — a change in what the software does
                                       # to the cluster, not just its version. This plan pins
                                       # both gates OFF so the effective behaviour is unchanged,
                                       # but the decision to pin is a judgement a human should
                                       # see. Over-declaring costs one attended window;
                                       # under-declaring runs a 5-minor operator jump on the
                                       # sole telemetry path unattended. => never unattended.
rollback_class: git-revert             # the EXPECTED path: no data, no migration, helm history
                                       # keeps revision 24 (5 revisions retained, measured).
                                       # BUT §5.3 is a real procedure, not decoration: IF the
                                       # gate pin failed to render, the webhook writes
                                       # `spec.networkPolicy.enabled: true` into the stored CR
                                       # and a `git revert` does NOT remove it (Helm 3-way
                                       # merge preserves a live field absent from both
                                       # manifests, and the 0.154.0 builder honours it
                                       # identically). §4.3 is the gate that detects this.
finding_refs: []                       # QUERIED 2026-09-19 with SWEEP_PG_DSN up, four greps
                                       # (`kube-stack`, `otel-operator`, `opentelemetry`,
                                       # `0.23.0`): there is NO open sweep finding for this
                                       # chart bump. The predecessor row F-60ebcdb5
                                       # ("otel-operator: chart 0.20.9 -> 0.21.0") is RESOLVED.
                                       # F-a85e8943 (CRD ownership) is deliberately NOT claimed
                                       # here — it is owned by prometheus-crd-ownership, and
                                       # double-claiming a finding breaks the plan-or-page join.
                                       # The next sweep's version section will file a row for
                                       # 0.21.0 -> 0.23.0; add it here when it appears.
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
premises:
  - id: live-chart-is-0.21.0
    why: >-
      `current:` claims 0.21.0 (helm revision 24). If the cluster already moved —
      a nightly Step 0 patch, a hand bump — then the render diff in §1.2, the
      rollback target in §5 and the CRD expectations in §4.2 are all stale.
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "0.21.0"
  - id: otel-hr-ready
    why: "Do not stack a chart bump on an already-failing release; a failed upgrade under remediation strategy rollback would mask every §4 result."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: crd-ownership-fix-is-in-place
    why: >-
      THE machine-check of `depends_on`. This plan's §4.2 asserts the four
      monitoring.coreos.com CRDs are NOT written, which is only true once
      prometheus-crd-ownership has set crds.installPrometheus=false. EXPECTED TO
      FAIL until that plan executes — that is the point: it stops this bump being
      scheduled into the one ordering that breaks two other vetted plans (§6).
      Do not "fix" it by deleting it; wait for the dependency.
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='crds=[{.spec.values.crds}]'
    expect_contains: '"installPrometheus":false'
  - id: live-operator-image-0.154.0
    why: >-
      The appVersion delta (0.154.0 -> 0.159.0) is the core of §1.3's risk
      argument. It is only that delta if the RUNNING operator is the chart-default
      0.154.0 with no tag override.
    run: kubectl get deploy otel-operator-opentelemetry-operator -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/open-telemetry/opentelemetry-operator/opentelemetry-operator:0.154.0"
  - id: live-collector-image-0.154.0
    why: >-
      Same claim for the collector image the operator stamps on the DaemonSet via
      --collector-image. This is what makes the 3-pod roll (and its per-node log
      gap) certain rather than possible.
    run: kubectl get daemonset otel-operator-daemon-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "otel/opentelemetry-collector-k8s:0.154.0"
  - id: daemon-collector-3-of-3
    why: >-
      §4.4 compares per-node ES document counts against a healthy 3/3 baseline.
      Starting from a degraded DaemonSet makes that diff uninterpretable.
    run: kubectl get daemonset otel-operator-daemon-collector -n monitoring -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled}'
    expect_exact: "3/3"
  - id: collector-cr-networkpolicy-unset
    why: >-
      The whole §1.3 analysis and the §5.3 residue branch assume
      spec.networkPolicy.enabled is UNSET (the webhook defaulter only writes it
      when it is nil). If someone already set it, the defaulting question is moot
      and the rollback story changes — re-derive §1.3 before touching anything.
      Prints `np=[]` when unset, never empty output.
    run: kubectl get opentelemetrycollector otel-operator-daemon -n monitoring -o jsonpath='np=[{.spec.networkPolicy.enabled}]'
    expect_exact: "np=[]"
  - id: no-networkpolicies-in-monitoring
    why: >-
      The baseline for §4.3's absence assertion. `-o name | wc -l` prints 0 (never
      empty), so the checker cannot read silence as consent. If a NetworkPolicy
      already exists in this namespace, §4.3's "still zero" gate is meaningless
      and must be rewritten against the real baseline.
    run: "kubectl get netpol -n monitoring -o name | wc -l"
    expect_exact: "0"
  - id: cilium-cidr-match-mode-unset
    why: >-
      §1.4 rates the operator's generated egress rule (IPBlock -> API-server node
      IPs) as doubtful specifically because Cilium does not select node/remote-node
      identities with CIDR rules unless policy-cidr-match-mode includes `nodes`.
      If the operator has since set that key, the hazard changes shape and the gate
      pin becomes belt-and-braces rather than load-bearing — say so in the report
      rather than silently proceeding. Prints `mode=[]` when unset.
    run: kubectl get cm cilium-config -n kube-system -o jsonpath='mode=[{.data.policy-cidr-match-mode}]'
    expect_exact: "mode=[]"
  - id: otlp-sink-is-edot-collector
    why: >-
      §4.4 proves this plan by documents arriving in Elasticsearch THROUGH
      edot-collector. If the daemon's exporter endpoint has been repointed, that
      gate is measuring someone else's pipeline.
    run: kubectl get opentelemetrycollector otel-operator-daemon -n monitoring -o jsonpath='{.spec.config.exporters.otlp.endpoint}'
    expect_exact: "edot-collector.monitoring.svc:4317"
  - id: no-instrumentation-crs
    why: >-
      0.159.0 adds an instrumentations/status RBAC rule and the operator runs an
      "instrumentation-upgrade" pass on start. That whole surface is inert only
      while no Instrumentation objects exist. `-o name | wc -l` prints 0, never
      empty.
    run: "kubectl get instrumentation -A -o name | wc -l"
    expect_exact: "0"
  - id: helm-controller-is-v1.6.x
    why: >-
      §4.2's positive control depends on helm-controller collecting the chart's
      crds/ directories on upgrade (install AND upgrade policy CreateReplace) and
      on ProcessDependencies pruning condition:false subcharts BEFORE CRDObjects()
      — read from v1.6.3 internal/action/crds.go. On any other minor, re-read that
      file at the deployed tag first.
    run: kubectl get deploy -n flux-system helm-controller -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_matches: "helm-controller:v1\\.6\\."
generated: "2026-09-19"
---

# otel-operator (opentelemetry-kube-stack): chart 0.21.0 → 0.23.0

## 1) Summary & why held

Bump the `otel-operator` HelmRelease
(`kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml`) from
**opentelemetry-kube-stack 0.21.0 → 0.23.0**, and in the same commit **pin the
two NetworkPolicy feature gates off** (§1.3). That HelmRelease is the umbrella
chart: subcharts `otel-crds`, `prometheus-crds` and `opentelemetry-operator`
(`kube-state-metrics` and `prometheus-node-exporter` are disabled here — the
render contains neither). It renders **one** `OpenTelemetryCollector` CR,
`otel-operator-daemon`, which the operator materialises as the 3-pod DaemonSet
`otel-operator-daemon-collector` (file_log / kubelet_stats / host_metrics /
k8s_objects / k8s_cluster per node), all exported over OTLP to
`edot-collector.monitoring.svc:4317`, which is what puts them in Elasticsearch.

### 1.1 Why it was held

`runbooks/coverage.py`: *"0.x release-line move (0.21 -> 0.23) — at major 0 the
minor IS the breaking axis; needs an assessed window plan."* Correct policy, and
here it is not a formality. **Both axes move:**

| Axis | 0.21.0 | 0.23.0 |
|---|---|---|
| chart `version` | 0.21.0 | 0.23.0 |
| chart `appVersion` (the operator) | **0.154.0** | **0.159.0** |
| `opentelemetry-operator` subchart | 0.119.0 | 0.123.0 |
| operator image | `…/opentelemetry-operator:0.154.0` | `:0.159.0` |
| collector image (`--collector-image`) | `otel/opentelemetry-collector-k8s:0.154.0` | `:0.159.0` |

Measured from the pulled charts, not from the index. **A chart-level "minor" is
not a safe minor when the appVersion moves five operator minors underneath it** —
that is the whole reason this item is in the PLAN lane and not in Step 0.

Upstream, the two releases are:

- **0.22.0** (2026-09-17): PR #2413 *"bump operator to 0.123.0 and update crds"* —
  this is the release that carries the entire 0.154.0 → 0.159.0 jump.
- **0.23.0** (2026-09-18): PR #2416 (CI only) and PR #2409 *"add resizePolicy
  option"* — a new `collectors.<name>.resizePolicy` values key defaulting to `[]`,
  and the template is `{{- with $collector.resizePolicy }}`, so with the key unset
  it renders nothing. Inert here.

### 1.2 What actually changes in the rendered release — measured

`helm template` with **our live HR values**, 0.21.0 vs 0.23.0. Excluding the
`helm.sh/chart` / `app.kubernetes.io/version` label churn and the webhook cert
(regenerated on *every* upgrade by `autoGenerateCert.recreate: true`), the
**entire** diff is four things:

```
>       - instrumentations/status                                    # ClusterRole: new rule
<             - --collector-image=otel/opentelemetry-collector-k8s:0.154.0
>             - --collector-image=otel/opentelemetry-collector-k8s:0.159.0
>             - name: NAMESPACE                                      # new env (fieldRef)
>               valueFrom: {fieldRef: {fieldPath: metadata.namespace}}
<           image: "…/opentelemetry-operator:0.154.0"
>           image: "…/opentelemetry-operator:0.159.0"
```

The object inventory is otherwise identical. The CRDs shipped in `crds/`:

- `charts/otel-crds/crds/` — `opampbridges` **+56**, `opentelemetrycollectors`
  **+424**, `targetallocators` **+283** lines, **no removals**;
  `instrumentations` **byte-identical**. All still `controller-gen v0.21.0`.
- `charts/prometheus-crds/crds/` — **byte-identical between 0.21.0 and 0.23.0**,
  still generated from prometheus-operator **0.92.0**. The subchart still exists,
  still has **no `templates/`**, and `crds.installPrometheus` is still the
  `Chart.yaml` condition and a `values.yaml` key (default `true`). **So
  `prometheus-crd-ownership`'s mechanism is intact at 0.23.0** — see §6.

### 1.3 The breaking change that makes this non-safe, and what it requires

From the **operator CHANGELOG 0.158.0** (upstream source, not a deny-rule reason):

> `operator, collector, target allocator`: **Enable operator, collector, target
> allocator network policies by default.** (#5394) Feature gate
> `operator.networkpolicy` and `operand.networkpolicy` are **promoted to beta, and
> enabled by default.** These feature gates create network policies for the
> operator and operand components.

Confirmed in the source, which is what makes it certain rather than plausible —
`pkg/featuregate/featuregate.go`:

| gate | at **v0.154.0** (live) | at **v0.159.0** (target) |
|---|---|---|
| `operator.networkpolicy` | `StageAlpha` → **off** | `StageBeta` → **ON** |
| `operand.networkpolicy` | `StageAlpha` → **off** | `StageBeta` → **ON** |

Nothing in the chart sets `--feature-gates` (verified: absent from both renders),
so the binary's defaults decide. Two consequences follow mechanically:

**(a) The collector CR gets silently mutated, permanently.**
`internal/webhook/collector_webhook.go` (identical code in 0.154.0 and 0.159.0 —
**only the gate stage changed**):

```go
if featuregate.EnableOperandNetworkPolicy.IsEnabled() && otelcol.Spec.NetworkPolicy.Enabled == nil {
    trueVal := true
    otelcol.Spec.NetworkPolicy.Enabled = &trueVal
}
```

Our live CR has `spec.networkPolicy: {}` (i.e. `Enabled == nil`), so the next
admission of that CR under 0.159.0 writes `enabled: true` into the stored object.
Helm's 3-way merge then **preserves** that field forever (it is in neither the old
nor the new manifest), and the 0.154.0 manifest builder honours it identically —
**so a `git revert` does not undo it.** That is the forward-only residue §5.3
exists for.

**(b) Two NetworkPolicies get created in `monitoring`, where today there are
none.** From `internal/manifests/collector/networkpolicy.go` and
`internal/operatornetworkpolicy/operatornetworkpolicy.go` at v0.159.0:

| policy | selects | Ingress | Egress |
|---|---|---|---|
| collector (`operand.networkpolicy`) | the 3 collector pods | one rule, **no `from`**, ports = the container ports (live: 10250, 8888, 4317, 4318) | **none** (`PolicyTypes: [Ingress]`) |
| operator (`operator.networkpolicy`) | the operator Deployment's selector | one rule, **no `from`**, ports 9443 + 8443 | **`PolicyTypes: [Ingress, Egress]` — egress ONLY to the API-server IPs on 6443** |

The collector policy is benign: ingress-only, all sources, on exactly the ports
the pods already expose — and **egress is untouched**, so the OTLP export to
edot-collector cannot be cut by it.

The operator policy is the hazard — see §1.4.

### 1.4 Why the operator's own NetworkPolicy is rated high, honestly

`cmd/operator/operator.go` builds it from EndpointSlice discovery, i.e. for this
cluster: `IPBlock 192.168.55.11/32, .12/32, .13/32` on TCP `6443`, with
`PolicyTypes: [Ingress, Egress]`. An egress policy with one rule denies everything
else — including DNS — and the operator reaches the API server via
`KUBERNETES_SERVICE_HOST=10.96.0.1:443`, a **ClusterIP**, not those node IPs.

That normally works (the CNI translates the service IP to a backend before policy
evaluation), **but this cluster runs Cilium v1.20.1 with
`policy-cidr-match-mode` UNSET** (measured). Cilium does not select the
`host`/`remote-node` identities with CIDR/IPBlock rules unless that key includes
`nodes` — which is exactly the shape of the rule above. **I did not empirically
test Cilium's behaviour here, and I am not claiming the operator would certainly
lose API access.** I am claiming the question is open, the downside is the
operator losing the API server, and the setup path is fail-fast:

```go
if featuregate.EnableOperatorNetworkPolicy.IsEnabled() {
    errNetworkPolicy := enableOperatorNetworkPolicy(result.Config, clientset, mgr)
    if errNetworkPolicy != nil {
        setupLog.Error(errNetworkPolicy, "failed to create the Operator network policies")
        os.Exit(1)
    }
}
```

Two upstream details cut the other way and are worth recording: 0.159.0's bug fix
#5493 *"Resolve the operator's own Deployment through pod owner references instead
of a hardcoded name, so the operator NetworkPolicy no longer crashes the operator
or selects no pods when installed with custom names (e.g. via the Helm chart)"*
describes **exactly** our install (`otel-operator-opentelemetry-operator`), and
the `NAMESPACE` env the chart newly sets in 0.123.0 is required by that path
(`operatorNamespace := os.Getenv("NAMESPACE")`, else hard error). So the
chart/appVersion pair at 0.22.0+ is coherent, and **0.158.0 is the version that
must never be run here** — a point in favour of going to 0.23.0 rather than
stopping short.

### 1.5 Options considered

| Option | Verdict |
|---|---|
| Bump only, accept the default-on gates | **Rejected.** Takes the §1.4 risk for no benefit tonight, and writes the forward-only CR field in §1.3(a). |
| **Bump + pin `operand.networkpolicy` and `operator.networkpolicy` off** | **CHOSEN.** One values key, dry-rendered end-to-end (§3.1). Behaviour stays byte-identical to today; the NetworkPolicy question becomes its own plan, decided deliberately instead of by an upstream default. |
| Bump + disable only the operator gate | Rejected. The collector policy is harmless, but enabling it still writes the permanent CR field for zero benefit today. |
| Stay on 0.21.0 | Rejected. Leaves us five operator minors behind, does not clear the hold, and the next 0.2x chart carries the same jump. |

**Not a false-positive hold.** The render diff is small; the *appVersion* is not.

Other 0.155.0–0.159.0 items reviewed and found inert here: the 0.159.0 target-
allocator `filter_strategy` breaking change (no TargetAllocator CRs — 0 live);
the 0.157.0 snake_case receiver renames (our CR **already** uses `file_log`,
`host_metrics`, `k8s_cluster`, `k8s_objects`, `kubelet_stats`); and the 0.158.0
double-Prometheus-reader bug (`address already in use`) — our CR configures
`service.telemetry.metrics.readers` with exactly one pull/prometheus reader on
:8888, which is the shape that bug produced, and **0.159.0 contains the fix**, so
landing on it is the safe side of that fence.

## 2) Pre-checks

**2.1 — premises.** `.venv/bin/python3 runbooks/plan-premises.py otel-operator-0.23.0`
must pass all eleven. `crd-ownership-fix-is-in-place` failing means the dependency
has not landed: **stop, do not proceed** (§6).

**2.2 — cluster is quiet and Flux is not mid-reconcile.**

```bash
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
kubectl get pods -n monitoring -o wide | grep -vE 'Running|Completed' || echo "all monitoring pods Running"
```

**2.3 — re-verify the chart at the target version** (do not trust this file's §1.2
if the window is days later; 0.23.x may have moved):

```bash
helm repo add otel-tmp https://open-telemetry.github.io/opentelemetry-helm-charts && helm repo update otel-tmp
helm search repo otel-tmp/opentelemetry-kube-stack --versions | head -5
cd "$(mktemp -d)" && for v in 0.21.0 0.23.0; do helm pull otel-tmp/opentelemetry-kube-stack --version $v --untar --untardir ./v$v; done
# the prometheus-crds subchart must still be crds/-only and byte-identical:
diff -rq v0.21.0/opentelemetry-kube-stack/charts/prometheus-crds v0.23.0/opentelemetry-kube-stack/charts/prometheus-crds && echo "prometheus-crds IDENTICAL"
grep -rn 'installPrometheus' v0.23.0/opentelemetry-kube-stack/Chart.yaml v0.23.0/opentelemetry-kube-stack/values.yaml
```

**2.4 — render A/B with the LIVE values and confirm the §1.2 diff still holds:**

```bash
kubectl get hr otel-operator -n monitoring -o json \
  | python3 -c "import sys,json,yaml;print(yaml.safe_dump(json.load(sys.stdin)['spec']['values'],default_flow_style=False))" > /tmp/hr-values.yaml
for v in 0.21.0 0.23.0; do helm template otel-operator ./v$v/opentelemetry-kube-stack -n monitoring -f /tmp/hr-values.yaml > /tmp/render-$v.yaml; done
diff /tmp/render-0.21.0.yaml /tmp/render-0.23.0.yaml \
  | grep -E '^[<>]' | grep -vE 'helm.sh/chart|app.kubernetes.io/version|caBundle|tls\.|ca\.crt'
```
Expect exactly the four items in §1.2. **Anything else → stop and re-assess.**

**2.5 — take the four baselines §4 compares against.** Record every number.

```bash
# (a) CRD state — the CONTROL and the SUBJECT of §4.2
kubectl get crd -o json --show-managed-fields | python3 -c "
import sys,json
for c in json.load(sys.stdin)['items']:
    m=c['metadata']; n=m['name']
    if not (n.endswith('monitoring.coreos.com') or n.endswith('opentelemetry.io')): continue
    hc=[f['time'] for f in m.get('managedFields',[]) if f.get('manager')=='helm-controller']
    print(f\"{n:48s} gen={m['generation']:<3} opver={m.get('annotations',{}).get('operator.prometheus.io/version','-'):<7} origin={m.get('labels',{}).get('helm.toolkit.fluxcd.io/name')} hc_write={hc[-1] if hc else '-'}\")"

# (b) the scrape surface
for k in servicemonitors podmonitors probes scrapeconfigs; do
  printf '%-16s %s\n' $k "$(kubectl get $k.monitoring.coreos.com -A --no-headers | wc -l | tr -d ' ')"
done
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=count(up)"; echo
kubectl get --raw "${P}?query=count(up%3D%3D1)"; echo

# (c) NetworkPolicy baseline (must be 0) and the CR's networkPolicy field (must be unset)
kubectl get netpol -n monitoring -o name | wc -l
kubectl get opentelemetrycollector otel-operator-daemon -n monitoring -o jsonpath='np=[{.spec.networkPolicy.enabled}]'; echo

# (d) ES arrival, PER NODE — the floor §4.4 re-measures
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 9200:9200 >/dev/null 2>&1 & PF=$!
sleep 5
curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
  -X POST "https://localhost:9200/logs-generic-default/_search?size=0" -d '{
   "query":{"range":{"@timestamp":{"gte":"now-15m"}}},
   "aggs":{"by_node":{"terms":{"field":"resource.attributes.k8s.node.name","size":10}}}}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['aggregations']['by_node']['buckets'])"
curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
  -X POST "https://localhost:9200/metrics-generic.otel-default/_count" \
  -d '{"query":{"range":{"@timestamp":{"gte":"now-15m"}}}}'; echo
kill $PF 2>/dev/null
```

**Measured 2026-09-19 (use as the sanity range, re-take fresh in-window):**
CRDs — the four `monitoring.coreos.com` at `gen=30`, `opver=0.92.0`,
`origin=otel-operator`, `hc_write=2026-09-14T05:45:08Z`; the four
`opentelemetry.io` at `gen=2`. Scrape surface — **49 / 3 / 4 / 3**;
`count(up)=98`, `count(up==1)=98`. NetworkPolicies — **0**; `np=[]`.
ES/15m — logs `k8s-nuc14-01 12,784 · -02 14,442 · -03 32,499`; metrics
**1,100,801**.

**2.6 — silence + marker** (§1.4 of `docs/sops/application-update.md`): the
DaemonSet roll makes `OtelDaemonCollectorDown` (`for: 5m`) plausible.

```bash
runbooks/update-marker.sh add otel-operator monitoring 2 "chart 0.21.0->0.23.0 upgrade"
```

## 3) Steps

**3.1 — edit the HelmRelease.** One file,
`kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml`, two hunks. This
exact edit was **dry-tested on a scratch copy on this Mac** (authoring rule 3);
the diff below is the real output, not a sketch:

```diff
@@ -9,7 +9,7 @@
   chart:
     spec:
       chart: opentelemetry-kube-stack
-      version: 0.21.0
+      version: 0.23.0
       sourceRef:
         kind: HelmRepository
         name: opentelemetry
@@ -36,6 +36,9 @@
           enabled: true
           recreate: true
       manager:
+        featureGatesMap:
+          operand.networkpolicy: false
+          operator.networkpolicy: false
         resources:
           requests:
             cpu: 50m
```

> **TRAP, caught by the dry run — do not hand-write this.** The values block
> **already has a `manager:` key** (it carries `resources:`). Adding a second
> `manager:` under `opentelemetry-operator:` produces a **duplicate YAML key**;
> the last one wins and the gate pin is **silently dropped** while the file looks
> right and Flux reconciles happily. The `featureGatesMap:` lines must go
> **inside the existing `manager:` block**, above `resources:`, exactly as above.

**3.2 — prove the edit parsed the way you intended, before pushing:**

```bash
cd /Users/mu/code/cberg-home-nextgen
python3 - <<'EOF'
import yaml
p='kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml'
class S(yaml.SafeLoader): pass
def nodup(loader,node,deep=False):
    m={}
    for k,v in node.value:
        key=loader.construct_object(k,deep=deep)
        assert key not in m, f'DUPLICATE KEY: {key}'
        m[key]=loader.construct_object(v,deep=deep)
    return m
S.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,nodup)
d=yaml.load(open(p),Loader=S)
op=d['spec']['values']['opentelemetry-operator']
assert d['spec']['chart']['spec']['version']=='0.23.0', 'chart version not bumped'
assert op['manager']['featureGatesMap']=={'operand.networkpolicy':False,'operator.networkpolicy':False}, 'gate pin missing'
assert 'resources' in op['manager'], 'manager.resources was clobbered'
print('OK: version 0.23.0, gates pinned, resources preserved, no duplicate keys')
EOF
task kubeconform
```

**3.3 — prove the rendered operator actually receives the flag** (the flag is the
whole point; a values key that does not reach an arg is a no-op):

```bash
helm template otel-operator ./v0.23.0/opentelemetry-kube-stack -n monitoring \
  -f <(kubectl get hr otel-operator -n monitoring -o json | python3 -c "
import sys,json,yaml,copy
v=json.load(sys.stdin)['spec']['values']
v['opentelemetry-operator'].setdefault('manager',{})['featureGatesMap']={'operand.networkpolicy':False,'operator.networkpolicy':False}
print(yaml.safe_dump(v,default_flow_style=False))") \
  | grep -E 'feature-gates|opentelemetry-operator:0\.|collector-image'
```
**Must print** (verified 2026-09-19; Helm sorts map keys, so the order is stable
across renders):
```
            - --collector-image=otel/opentelemetry-collector-k8s:0.159.0
            - --feature-gates=-operand.networkpolicy,-operator.networkpolicy
          image: "ghcr.io/open-telemetry/opentelemetry-operator/opentelemetry-operator:0.159.0"
```

**3.4 — commit and push** (shared worktree: `--only`, never `git add -A`):

```bash
git commit --only kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml -F /tmp/otel-msg.txt
git log -1 --format=%s     # MUST be your subject — amend before pushing if it is not
git show --stat HEAD       # MUST be exactly the one file
git push
```

**3.5 — capture the rollout timestamp** (§4.4's window must START after this):

```bash
kubectl -n monitoring rollout status deploy/otel-operator-opentelemetry-operator --timeout=5m
kubectl -n monitoring rollout status daemonset/otel-operator-daemon-collector --timeout=10m
ROLLOUT_TS=$(kubectl get pods -n monitoring -l app.kubernetes.io/component=opentelemetry-collector \
  -o jsonpath='{range .items[*]}{.status.startTime}{"\n"}{end}' | sort | tail -1)
echo "last collector pod Ready at: $ROLLOUT_TS  — §4.4 measures from here, wait 15m"
```

> Do **not** `flux reconcile` by hand; the webhook drives it. Do not hand-delete
> collector pods mid-roll.

## 4) Verification

### Floor (shape — necessary, NOT sufficient)

```bash
kubectl get helmrelease otel-operator -n monitoring \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion} {.status.history[0].appVersion} rev={.status.history[0].version}'; echo
kubectl get daemonset otel-operator-daemon-collector -n monitoring -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled}'; echo
kubectl logs -n monitoring deploy/otel-operator-opentelemetry-operator --tail=80 \
  | grep -iE 'error|panic|failed to create the operator network policies' || echo "no startup errors"
```
**PASS:** `True 0.23.0 0.159.0 rev=25`; `3/3`; no error lines. The grep is
case-insensitive deliberately — upstream logs mixed case.

### CONTENTS ASSERTION 4.1 — the new bytes are actually running

```
CONTENTS ASSERTION: the operator and all three collector pods run the 0.159.0
  IMAGE DIGEST — measured by imageID, not the tag string, and by the CR's own
  reconciled status, compared to the §2.5 baseline of 0.154.0.
```
```bash
kubectl get pods -n monitoring -l app.kubernetes.io/name=opentelemetry-operator \
  -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID}{"\n"}{end}'
kubectl get pods -n monitoring -l app.kubernetes.io/component=opentelemetry-collector \
  -o jsonpath='{range .items[*]}{.spec.nodeName}{"  "}{.status.containerStatuses[0].imageID}{"\n"}{end}'
kubectl get opentelemetrycollector otel-operator-daemon -n monitoring \
  -o jsonpath='version={.status.version} image={.status.image}'; echo
```
**PASS:** one operator digest for `…/opentelemetry-operator:0.159.0`; **three**
collector rows (one per node) on the `0.159.0` digest; `version=0.159.0`.
**FAILS AS:** `rollout status` reporting success while a pod still runs the old
digest (`feedback_rollout_status_old_generation` — that has happened here), or
`status.version` stuck at `0.154.0`, meaning the operator never reconciled the CR.

### CONTENTS ASSERTION 4.2 — the CRD pass RAN, and touched only what it should

This is the component's signature failure mode, and it is written to answer
**F-7235625a**: an absence-of-write is *not* evidence, because a `CreateReplace`
of byte-identical content leaves no trace. So this gate pairs the subject with a
**positive control that must move**.

```
CONTENTS ASSERTION: the three CHANGED opentelemetry.io CRDs were rewritten by
  THIS upgrade (generation 2 -> 3, helm-controller write time == this upgrade),
  while the four monitoring.coreos.com CRDs were NOT (generation 30, opver
  0.92.0, write time still the §2.5 baseline) — measured together, so that
  "unchanged" is only credible because the control proves the pass ran at all.
```
```bash
UPG=$(helm history otel-operator -n monitoring -o json | python3 -c "import sys,json;print(json.load(sys.stdin)[-1]['updated'])")
echo "otel upgrade at: $UPG"
kubectl get crd -o json --show-managed-fields | python3 -c "
import sys,json
for c in json.load(sys.stdin)['items']:
    m=c['metadata']; n=m['name']
    if not (n.endswith('monitoring.coreos.com') or n.endswith('opentelemetry.io')): continue
    hc=[f['time'] for f in m.get('managedFields',[]) if f.get('manager')=='helm-controller']
    print(f\"{n:48s} gen={m['generation']:<3} opver={m.get('annotations',{}).get('operator.prometheus.io/version','-'):<7} origin={m.get('labels',{}).get('helm.toolkit.fluxcd.io/name')} hc_write={hc[-1] if hc else '-'}\")"
```
**PASS — all of:**
- **CONTROL (must MOVE):** `opampbridges`, `opentelemetrycollectors`,
  `targetallocators` `.opentelemetry.io` → `gen=3` and `hc_write` **equal to
  `$UPG`**. Their content genuinely changed (§1.2), so a write must leave a trace.
- **`instrumentations.opentelemetry.io` stays `gen=2`** — byte-identical between
  the two charts. Do **not** read this as a failure; predicting a bump for a
  byte-identical re-apply is the error F-7235625a records.
- **SUBJECT (must NOT move):** the four `monitoring.coreos.com` → `gen=30`,
  `opver=0.92.0`, `hc_write` still `2026-09-14T05:45:08Z` (the §2.5 baseline),
  and 14 rows total with none missing.

**FAIL conditions:** the control did **not** move → the CRD pass did not run at
all and the subject's "unchanged" reading proves nothing — investigate before
believing anything else in §4. Any of the four subjects moving, or `opver`
reading anything but `0.92.0` → `crds.installPrometheus` is not actually false;
stop and re-derive §6 with `prometheus-crd-ownership`. Any CRD **missing** → §5.3
immediately.

### CONTENTS ASSERTION 4.3 — the gate pin took; NO NetworkPolicy was created

```
CONTENTS ASSERTION: the two feature gates are actually disabled in the running
  process and no NetworkPolicy exists in `monitoring` — measured on the live pod
  spec AND on the API objects AND on the CR field the webhook would have written,
  compared to the §2.5 baseline of zero / unset.
```
```bash
kubectl get deploy otel-operator-opentelemetry-operator -n monitoring \
  -o jsonpath='{.spec.template.spec.containers[0].args}' | tr ',' '\n' | grep feature-gates
kubectl get netpol -n monitoring -o name | wc -l
kubectl get opentelemetrycollector otel-operator-daemon -n monitoring -o jsonpath='np=[{.spec.networkPolicy.enabled}]'; echo
```
**PASS:** the arg line reads `--feature-gates=-operand.networkpolicy,-operator.networkpolicy`;
the NetworkPolicy count is **`0`**; and `np=[]` (still unset).
**FAILS AS:** count `1` or `2` — upstream would name them `opentelemetry-operator`
(hardcoded) and the collector one after the CR — meaning the pin did not reach the
binary and §1.3/§1.4 are now live; **or** `np=[true]`, which means the webhook
defaulted the CR and **§5.3 applies even if you revert**. A count of `0` with the
arg *missing* is not a pass: it only means nothing has been admitted yet, and the
policy will appear on the next CR write.

### CONTENTS ASSERTION 4.4 — telemetry still FLOWS, from every node

The load-bearing gate. Run it **≥15 minutes after `$ROLLOUT_TS`** so the window
starts after the last pod is Ready.

```
CONTENTS ASSERTION: documents from all THREE nodes land in Elasticsearch in a
  window that starts after the roll — measured in ES itself (not at the exporter,
  because `_bulk` returns 200 even when every item is rejected), compared to the
  §2.5 per-node baseline.
```
```bash
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 9200:9200 >/dev/null 2>&1 & PF=$!
sleep 5
curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
  -X POST "https://localhost:9200/logs-generic-default/_search?size=0" -d '{
   "query":{"range":{"@timestamp":{"gte":"'"$ROLLOUT_TS"'"}}},
   "aggs":{"by_node":{"terms":{"field":"resource.attributes.k8s.node.name","size":10}}}}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['aggregations']['by_node']['buckets'])"
curl -k -s -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
  -X POST "https://localhost:9200/metrics-generic.otel-default/_count" \
  -d '{"query":{"range":{"@timestamp":{"gte":"'"$ROLLOUT_TS"'"}}}}'; echo
curl -k -s -u "elastic:$ES_PW" "https://localhost:9200/_cluster/health" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'],d['unassigned_shards'])"
kill $PF 2>/dev/null
```
**PASS:** **three** `by_node` buckets — `k8s-nuc14-01`, `-02`, `-03` — each
**> 0** and rising on a re-run, roughly in line with the §2.5 baseline
(12.8k / 14.4k / 32.5k per 15m; wide tolerance is fine, **zero is not**); the
metrics count **> 0** (baseline ~1.1M/15m); cluster `green`/`yellow` with 0
unassigned shards.
**FAILS AS:** **a missing node bucket** — one collector Ready but shipping
nothing, which is precisely what a mis-scoped NetworkPolicy or a receiver that
silently stopped looks like, and which no pod-level signal would show; or a total
of 0, the hard "are we blind" answer and a stop regardless of every green above.
A trickle is a failure, not a pass.

### CONTENTS ASSERTION 4.5 — the scrape surface the CRDs define is intact

```
CONTENTS ASSERTION: every CR of the four kinds still exists and Prometheus still
  scrapes what they generate — measured by per-kind counts and up-target counts,
  compared to the §2.5 baseline (49/3/4/3; 98/98).
```
```bash
for k in servicemonitors podmonitors probes scrapeconfigs; do
  printf '%-16s %s\n' $k "$(kubectl get $k.monitoring.coreos.com -A --no-headers | wc -l | tr -d ' ')"
done
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=count(up)"; echo
kubectl get --raw "${P}?query=count(up%3D%3D1)"; echo
```
**PASS:** `49 / 3 / 4 / 3` exactly (a CRD delete would cascade these to 0, so
"non-zero" is not enough), and `count(up==1) == count(up)` at ~98. A deviation in
the target count is acceptable **only** if another plan in the same window
legitimately added or removed targets — name it, or treat it as a failure.

### 4.6 — alerts, read honestly

```bash
kubectl get --raw "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/alerts" \
  | grep -o '"alertname":"[^"]*"' | grep -vE 'Watchdog|InfoInhibitor' | sort | uniq -c
```
**PASS:** nothing new firing 15 min after the roll.
**Do not treat this as coverage.** `OtelDaemonCollectorDown` only fires when the
DaemonSet is not Ready, and `EsLogIngestionStalled` / `EsMetricsIngestionStalled`
watch **edot-collector's** exporters, not the daemon collectors'. A daemon that is
Ready and silently ships nothing fires **none** of them (this is the gap recorded
in `F-7c88001b`). §4.4 is the only gate that catches it — which is why it, not
this, is the load-bearing one.

## 5) Rollback

**5.1 — the revert (expected path).**

```bash
git revert --no-edit <the §3.4 commit>
git log -1 --format=%s && git show --stat HEAD
git push
kubectl -n monitoring rollout status deploy/otel-operator-opentelemetry-operator --timeout=5m
kubectl -n monitoring rollout status daemonset/otel-operator-daemon-collector --timeout=10m
```
This restores chart 0.21.0 **and** removes the gate pin together — correct, since
at 0.154.0 both gates are alpha/off anyway (§1.3). The HR carries
`upgrade.remediation.strategy: rollback, retries: 3`, and helm keeps 5 revisions
(20–24 live today), so revision 24 stays reachable for a manual
`helm rollback otel-operator 24 -n monitoring` if Flux cannot converge.

**5.2 — confirm the cluster is actually back** (not just that the commit landed):

```bash
kubectl get hr otel-operator -n monitoring -o jsonpath='{.status.history[0].chartVersion} {.status.history[0].appVersion}'; echo   # 0.21.0 0.154.0
kubectl get daemonset otel-operator-daemon-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image} {.status.numberReady}/{.status.desiredNumberScheduled}'; echo
```
Then **re-run §4.4** with a fresh `$ROLLOUT_TS`: all three nodes back above zero.
A revert that restores the version but not the telemetry is not a rollback.

**5.3 — RESIDUE branch: only if §4.3 showed `np=[true]` or a NetworkPolicy exists.**

This is the forward-only part, and §5.1 **does not** clean it up:
`spec.networkPolicy.enabled: true` was written into the stored CR by the admission
webhook, so it appears in neither the old nor the new Helm manifest and the 3-way
merge preserves it — and the 0.154.0 builder honours the field identically, so the
NetworkPolicy would survive the downgrade.

1. **If the operator is wedged** (no API access / `os.Exit(1)` loop), break glass
   first — delete the operator NetworkPolicy so it can reach the API server again.
   This is a direct cluster mutation: operator-approved, recorded in the run log.
   ```bash
   kubectl get netpol -n monitoring -o wide          # identify before deleting
   kubectl delete netpol opentelemetry-operator -n monitoring
   ```
   Do **not** delete the operator Deployment to garbage-collect it via its
   ownerReference — that takes the collectors' controller with it.
2. **Then close the door in git, not by hand:** land §3.1's `featureGatesMap`
   hunk (without the chart bump) so the gates are pinned off under 0.154.0 too.
   With the gate disabled the defaulter no longer runs, and the stale
   `enabled: true` on the CR becomes inert — the builder is reached only while the
   gate is on for new admissions, but the field will still be honoured, so:
3. **Clear the CR field explicitly** once the operator is healthy, and verify:
   ```bash
   kubectl patch opentelemetrycollector otel-operator-daemon -n monitoring --type=merge -p '{"spec":{"networkPolicy":{"enabled":false}}}'
   kubectl get opentelemetrycollector otel-operator-daemon -n monitoring -o jsonpath='np=[{.spec.networkPolicy.enabled}]'; echo
   kubectl get netpol -n monitoring -o name | wc -l    # back to 0
   ```
   Note this leaves the CR differing from the chart render by one field; record it
   so the next otel plan's premise `collector-cr-networkpolicy-unset` is updated
   rather than tripping unexplained.

## 6) Interference notes

- **Ordering — `prometheus-crd-ownership` MUST run first, and it is a `depends_on`,
  not a preference.** The reason is mechanical, not aesthetic: that plan's premise
  `otel-chart-version-whose-layout-was-verified` asserts
  `^0\.(20\.9|21\.0)$` against the live chart version. Landing this bump first makes
  that premise **fail**, `plan-premises.py` then refuses a `vetted` plan, and
  `kube-prometheus-stack-91.4.0` — which declares `depends_on:
  prometheus-crd-ownership` — is blocked behind it. **One bump would strand two
  vetted plans.** Running it first also deletes the whole four-CRD question from
  this plan: with `crds.installPrometheus: false`, the prometheus-crds subchart is
  pruned before `CRDObjects()` and this upgrade never writes them.
- **The bad ordering, named:** `kube-prometheus-stack-91.4.0` → this bump, without
  `prometheus-crd-ownership`. The four CRDs would sit at 0.94.0 and this chart's
  `CreateReplace` would **downgrade them to 0.92.0** — a genuine spec change that
  *would* move generation and write-time (unlike the byte-identical case). That
  ordering is currently unreachable, because kps-91.4.0 itself depends on
  prometheus-crd-ownership; `conflicts_with` on both sides keeps it that way.
- **REPO CORRECTION (report, do not edit here — single-file rule).**
  `prometheus-crd-ownership` is **stale in one field**: its `current:` says
  *"opentelemetry-kube-stack 0.20.9"*, but commit `9a35168f` (2026-09-17) moved the
  HR to **0.21.0**, confirmed live (`.spec.chart.spec.version=0.21.0`, helm
  revision 24). **Its premise still passes** (the regex admits 0.21.0) and its
  central claim is **still true at 0.23.0** — I re-pulled the chart and verified the
  `prometheus-crds` subchart is still `crds/`-only, still byte-identical, still
  0.92.0, and `crds.installPrometheus` is still both the `Chart.yaml` condition and
  a `values.yaml` key. So the plan is sound; only its `current:` string and the
  premise regex need widening to `^0\.(20\.9|21\.0|23\.0)$` **if** the operator
  ever wants the two orderings to be interchangeable. As written, it must simply
  run first.
- **`conflicts_with` reciprocity — two corrections owed when this plan is vetted:**
  `edot-collector-0.161.0` and `cilium-1.20.2` should each name
  `otel-operator-0.23.0` in their own `conflicts_with`. `--validate` checks that
  refs *resolve*, not that they are mutual, so a one-sided declaration still lets
  the scheduler co-place them from the other side.
- **The DaemonSet roll loses logs, per node, and they are not backfilled.**
  `file_log` runs `start_at: end` with **no** storage extension (measured), so each
  node's pod logs are dropped for the ~10–30 s its collector is down, one node at a
  time. Any other plan verifying ES log continuity in that window will see a hole
  that is this plan's doing, not theirs.
- **Prometheus is this plan's instrument** (§4.5), which is why any same-night
  `kube-prometheus-stack` bump is a hard conflict rather than a warning: a restart
  of the instrument reads as "no data" on both sides of the gate.
- **edot-collector is downstream, not touched.** It is a plain Kustomize Deployment
  and this plan does not modify it — but every assertion in §4.4 travels through it,
  which is the whole reason `edot-collector-0.161.0` is a slot exclusion.
- **Window shape:** ~50 min, no reboot, but `risk: high` + `capability_change: true`
  ⇒ **attended, operator-present, never unattended**. It fits `sat-attended` /
  `sun-attended` (90 / 200 min); it must not be placed in `nightly`.
