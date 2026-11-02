---
plan_id: otel-operator-0.26.1
component: otel-operator               # HelmRelease monitoring/otel-operator; CHART is the umbrella
                                       # opentelemetry-kube-stack (subcharts otel-crds, prometheus-crds,
                                       # opentelemetry-operator)
pr: 351                                # "feat(helm): update opentelemetry-kube-stack ( 0.24.3 → 0.26.1 )".
                                       # Renovate RE-TARGETED this PR from 0.25.1 to 0.26.1 (updatedAt
                                       # 2026-10-29). One-line diff to helmrelease.yaml; CI green (Flate
                                       # Render Gate, Flux Local Diff hr+ks, Labeler), checked 2026-10-31.
supersedes: otel-operator-0.25.1       # Its Step B merges #351, which now lands 0.26.1, not 0.25.1, so it
                                       # cannot run as written (its own §2(c) diff check would STOP it).
                                       # There is no PR left that lands 0.25.1, so chaining is not possible
                                       # without a hand-written intermediate bump (two attended slots, four
                                       # collector rolls) for a 0.161 -> 0.162 delta that is small (§1.2).
                                       # Its verified research is carried over below and re-checked at
                                       # 0.162.0. Its finding_refs and cross-references are carried over by hand.
kind: chart
current: "0.24.3"                      # MEASURED 2026-10-31: HR spec 0.24.3, history[0] 0.24.3/deployed (rev 70)
target: "0.26.1"
update_type: minor
risk: medium                           # Two binaries move across THREE minors each: operator 0.159.0 -> 0.162.0
                                       # (subchart 0.123.0 -> 0.128.0). Through the operator's --collector-image
                                       # default, the COLLECTOR moves 0.159.0 -> 0.162.0 on all 3 nodes.
                                       # Collector 0.161+ flips a beta gate that silently STOPS emitting
                                       # container.image.tag (§1.3). That is a feature loss, and this plan
                                       # pins it away. This HR has also shown the RollbackFailed failure
                                       # shape once (F-97c88a5c).
est_duration_min: 55                   # 10 pre-checks + 10 Step A (args commit, 3-pod roll, gate)
                                       # + 10 Step B (merge, operator + 3-pod roll) + 15 SETTLE before the ES
                                       # gate + 8 verification + 2 buffer. Same shape as 0.25.1. The extra
                                       # minor adds no step.
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:                           # every object verified to EXIST live 2026-10-31
    - helmrelease/otel-operator                         # git edits: chart version + collectors.daemon.args
    - deployment/otel-operator-opentelemetry-operator   # ROLLS: image 0.159.0 -> 0.162.0, new arg
                                                        # --target-allocator-image (inert, no TA CR)
    - opentelemetrycollector/otel-operator-daemon       # spec.args gains feature-gates; spec.upgradeStrategy
                                                        # automatic -> operator bumps status.version to 0.162.0
    - daemonset/otel-operator-daemon-collector          # ROLLS twice (Step A args, Step B image)
    - clusterrole/otel-operator-opentelemetry-operator-manager  # gains `watch` on discovery.k8s.io
                                                        # endpointslices (operator 0.161) + apps
                                                        # deployments/finalizers get/patch/update/watch (0.162)
    - secret/otel-operator-opentelemetry-operator-controller-manager-service-cert  # pre-upgrade hook,
                                                        # regenerated every upgrade (autoGenerateCert.recreate)
    - mutatingwebhookconfiguration/otel-operator-opentelemetry-operator-mutation      # caBundle
    - validatingwebhookconfiguration/otel-operator-opentelemetry-operator-validation  # caBundle
    - "crd/{opentelemetrycollectors,targetallocators,instrumentations,opampbridges}.opentelemetry.io
       — CreateReplace; ADDITIVE schema only (0.25: enableServiceLinks, imagePullSecrets,
       revisionHistoryLimit; 0.26: instrumentation php block, PVC-status healthConditions validation),
       controller-gen v0.21 -> v0.23"
    - "networkpolicy/otel-operator-daemon-collector-networkpolicy — NOT edited; asserted UNCHANGED in §4.3"
  shared:
    - monitoring                       # the cluster's ONLY pod-log / host-metric / kubelet-stats / k8s-event
                                       # collection path into edot-collector -> Elasticsearch. Each node loses
                                       # ~10-30 s of pod logs per collector roll (filelog start_at end, no
                                       # storage extension), and this plan rolls the collectors twice.
depends_on: []
conflicts_with:                        # ONLY this field is honoured by window-scheduler.py.
  - redis-fleet-8.10.3   # reciprocal, 2026-11-02 sweep 2ad957af
  - otel-operator-0.25.1               # SAME HelmRelease, SAME PR #351. Superseded by this plan. Listed so
                                       # the two can never share a slot while 0.25.1 is still un-retired.
  - helm-drift-detection               # writes spec.driftDetection into this same HelmRelease
  - flux-oci-chart-sources             # edits the SAME helmrelease.yaml (spec.chart -> chartRef)
  - edot-collector-0.163.2             # Daemon collectors export OTLP into edot-collector.monitoring.svc:4317,
  - edot-collector-0.164.0             # and §4.4 proves this plan by docs landing in ES THROUGH edot. A
                                       # same-night edot roll makes both plans' ES gates unattributable.
                                       # 0.164.0 is the draft that retargets 0.163.2. Its reciprocal already
                                       # names this plan (checked 2026-11-02).
  - talos-linux-1.14.5                 # exclusive draft that SUPERSEDES 1.14.4 (node roll re-creates every
                                       # collector pod; §4.4 per-node gate cannot attribute a missing node)
  - talos-linux-1.14.4                 # MISSED sun-attended:2026-11-01, superseded by the 1.14.5 draft. Keep until
                                       # 1.14.4 is retired (a retired plan still resolves, so no DEAD-REF).
  - grafana-14.1.0                     # reciprocal there (soft, attribution hygiene: both gate on ns monitoring)
  # Pruned vs 0.25.1: talos-linux-1.14.2 (superseded), home-assistant-2026.10.2 (executed).
  # No kube-prometheus-stack PLAN FILE exists (checked 2026-11-02), so none can be listed here. But
  # Renovate PR #428 (kube-prometheus-stack 92.11.1 -> 92.17.0, age cooldown, NO deny rule in
  # auto-update-policy.yaml) can auto-apply at Step 0 of a nightly or of the window itself and disturb
  # the Prometheus instrument §4 reads. Handled by the §2(f) pre-check and the §6 note, not by this field.
  # If a kube-prometheus-stack plan is ever written, it must go here.
exclusive: false
security_ref: null                     # Not security-driven. Side effect: the collector image moves off
                                       # collector-k8s 0.159.0, the subject of AR-accepted F-369edfe8. The
                                       # sweep re-scores it; this plan does not claim it.
capability_change: false               # Same pipelines, receivers and exporters. The CR spec is byte-identical
                                       # except one feature-gate arg, and its PURPOSE is to keep today's
                                       # attribute set. New CRD fields and operator features (PHP/Ruby
                                       # auto-instrumentation, TLS-profile injection) stay unused/off.
                                       # The operator NetworkPolicy stays pinned off.
rollback_class: git-revert             # Nothing is forward-only. CRD changes are additive (the older schema
                                       # prunes unknown fields on read). No data, no migrations.
autonomy_override: human-gated         # REQUIRED by the deny rule's removal condition
                                       # (auto-update-policy.yaml `*opentelemetry-kube-stack*`): "the bump goes
                                       # through an attended window". §5.3 also holds a break-glass direct
                                       # mutation that only an operator may authorize.
finding_refs: [F-60ebcdb5, F-61e4d5b6, F-3b519d4a]
                                       # VERIFIED 2026-10-31 via `policy-cli.py finding list --grep` with
                                       # otel-operator / opentelemetry-kube-stack / 0.26.1:
                                       # F-60ebcdb5 (version): "otel-operator: chart 0.24.3 → 0.26.1", i.e. this target.
                                       # F-61e4d5b6 (plan, AR-072): "any re-attempt must handle the
                                       # operator.networkpolicy feature gate in a plan". Carried from 0.25.1.
                                       # F-3b519d4a (plan): close superseded PR #356 (0.24.6). Answered in §3.5.
                                       # F-e918a007 (carried by 0.25.1) no longer lists as open.
review: ready-for-go@2026-11-02       # plan-reviewer 2026-11-02: ready-for-go, 0 blocking, premises 8/8; stale scheduling prose fixed in the same edit. HUMAN-GATED: fresh operator GO on this plan_id (the 0.25.1 GO does not carry over)
status: vetted
window: "sat-attended:2026-11-07"      # OPERATOR GO 2026-11-02: SOLO (55 of 70 min). helm-drift-detection was moved to
                                       # sat-attended:2026-11-28 the same day; fallback sat-attended:2026-12-05 solo.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-31"
premises:
  - id: live-chart-is-0.24.3
    why: "`current:` claims 0.24.3. If the HR moved, the render diff in §1.2 and the rollback target in §5 are stale."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "0.24.3"
  - id: otel-hr-ready
    why: "Never stack a chart bump on a failing release. With remediation strategy rollback, a pre-existing failure re-enters the RollbackFailed trap."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: last-release-deployed-0.24.3
    why: "The §5 rollback depends on helm's newest revision being a deployed 0.24.3."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.status.history[0].chartVersion}/{.status.history[0].status}'
    expect_exact: "0.24.3/deployed"
  - id: gate-pin-in-values
    why: "Load-bearing. Operator 0.160 moved operator.networkpolicy back to alpha/off (still alpha at v0.162.0), but the pin must stay as the second safeguard. If it is removed AND a later operator re-enables the gate, the 2026-10-12 deadlock returns."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.spec.values.opentelemetry-operator.manager.featureGatesMap}'
    expect_contains: '"operator.networkpolicy":false'
  - id: operator-image-0.159.0
    why: "The §1.2 binary-delta analysis (0.160/0.161/0.162 release notes) is only valid starting from 0.159.0."
    run: kubectl get deploy otel-operator-opentelemetry-operator -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/open-telemetry/opentelemetry-operator/opentelemetry-operator:0.159.0"
  - id: collector-image-0.159.0
    why: "The §1.3 collector breaking-change analysis covers 0.160, 0.161 and 0.162 only, i.e. starting from 0.159.0."
    run: kubectl get ds otel-operator-daemon-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "otel/opentelemetry-collector-k8s:0.159.0"
  - id: collector-args-baseline
    why: "Step A adds the feature-gate arg. If the args already differ, someone changed the collector out of band and the §3.2 expectation is wrong."
    run: kubectl get ds otel-operator-daemon-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].args}'
    expect_exact: '["--config=/conf/collector.yaml"]'
  - id: monitoring-netpols-exactly-collector
    why: "Baseline for §4.3. An `opentelemetry-operator` entry means the deadlock is already live. A missing collector entry means the baseline moved."
    run: kubectl get networkpolicy -n monitoring -o jsonpath='{.items[*].metadata.name}'
    expect_exact: "otel-operator-daemon-collector-networkpolicy"
---

# otel-operator — opentelemetry-kube-stack 0.24.3 → 0.26.1

**Supersedes `otel-operator-0.25.1`** (vetted 2026-10-23; now `status: superseded`, **do not run it**). Renovate re-targeted PR #351 from
0.25.1 to **0.26.1** (PR updated 2026-10-29). Merging #351 now lands 0.26.1, so
0.25.1's Step B would install a chart its analysis never covered. Its §2(c) PR-diff
check would STOP it, but only after the slot is spent. 0.25.1 is marked
`status: superseded` / `superseded_by: otel-operator-0.26.1` (done 2026-11-02) and this
plan holds its slot (see §6).

**Retarget, not chain.** Chaining would mean hand-writing a `version: 0.25.1` commit
(no PR exists for it any more), verifying it, then merging #351 in a second
attended slot: four collector rolls and two attended slots. The extra delta
0.25.1 → 0.26.1 is one binary minor (0.161 → 0.162) whose breaking changes do not
touch our config (§1.3), and whose render delta is RBAC + additive CRD fields
(§1.2). One step is the safer trade.

**The GO recorded for 0.25.1 does NOT carry over.** This is a different `plan_id`, the
third binary minor (0.159 -> 0.162 instead of 0.161), new ClusterRole rules, additive CRD
changes and a corrected §4.2 gate. After the independent review, the operator needs to
give a fresh one-line re-confirmation on `otel-operator-0.26.1` via
`home-operation decide`. Do not schedule or run this plan on the strength of the old GO.
`review:` stays `null` until a reviewer verdict is written; `status` stays `draft`.

What carries over from 0.25.1 unchanged and was re-verified against v0.162.0 today:
the networkpolicy deadlock mechanism, the RollbackFailed trap, the render-gate
method, the k8s_attributes feature-loss pin (Step A, byte-identical sed), and the
operand NetworkPolicy prediction. What changed: target images, two RBAC rules,
CRDs, and the §4.2 gate's expected log line (a 0.25.1 gate defect fixed here,
see §4.2).

## 1) Summary & why held

### 1.1 What changes (upstream)

Renovate's PR body mislinks the 0.26.0/0.26.1 entries to `opentelemetry-demo`
releases. The real chart contents were read from the published chart tarballs
(`helm pull … --version 0.26.0 / 0.26.1`, 2026-10-31):

| chart | appVersion | opentelemetry-operator subchart |
|---|---|---|
| 0.24.3 (live) | 0.159.0 | 0.123.0 |
| 0.25.1 | 0.161.0 | 0.126.0 |
| 0.26.0 / **0.26.1** | **0.162.0** | **0.128.0** |

0.25.0 is "bump operator to 0.126.0 and update crds" (#2469). 0.25.1 is docs only.
0.26.x carries operator 0.162.0. The 0.24.4–0.24.6 entries (OpAMP Bridge env,
instrumentation defaults, apacheHttpd render fix) do not apply: no OpAMPBridge or
Instrumentation CR is rendered with our values, and none exists live.

### 1.2 Measured render delta (with our live values)

`helm template` of 0.24.3, 0.25.1 and 0.26.1 with `spec.values` from HEAD
(2026-10-31, scratch dir `/tmp/otel-0261-plan`). The renders are 20 510 / 20 551 /
21 032 lines with **an identical object set** (the same kinds, the same counts, and
still zero `kind: NetworkPolicy`). After normalising cert material and
`helm.sh/chart`, the deltas are:

- **operator Deployment**: image `opentelemetry-operator:0.159.0` → `:0.162.0`,
  `--collector-image=otel/opentelemetry-collector-k8s:0.159.0` → `:0.162.0`, plus a new
  `--target-allocator-image=…:0.162.0` (inert: no TargetAllocator). The
  `--feature-gates=-operator.networkpolicy` arg is still rendered (count 1).
- **ClusterRole `…-manager`**: `discovery.k8s.io endpointslices` gains `watch`
  (operator 0.161 notes: "The operator now requires the `watch` permission on
  `endpointslices`"). New rule `apps deployments/finalizers [get,patch,update,watch]`
  (0.26.x).
- **CRDs**: additive only. 0.25: `enableServiceLinks`, `imagePullSecrets`,
  `revisionHistoryLimit`. 0.26: `instrumentations` gains the `php` block.
  `opentelemetrycollectors` gains `maxItems: 16` / `minLength: 1` only under
  `spec.volumeClaimTemplates[].status.healthStatus.healthConditions`, which is a PVC
  *status* field we do not set (no volumeClaimTemplates in our CR). controller-gen
  goes v0.21 → v0.23. No field was removed (a python diff of the 0.25.1 vs 0.26.1 CRD
  JSON shows only `>` additions besides the annotation).
- **OpenTelemetryCollector CR spec: byte-identical 0.24.3 vs 0.26.1** (python compare,
  `CR_SPEC_IDENTICAL True`). No `image:` is set in the CR, so the collector image
  comes from the operator's `--collector-image`. The live CR has `upgradeStrategy:
  automatic`, so **the collector binary moves 0.159.0 → 0.162.0 on all three nodes**
  even though the CR did not change.
- Target images are multi-arch indexes (registry query 2026-10-31):
  `otel/opentelemetry-collector-k8s:0.162.0` has amd64/arm64/…, and
  `opentelemetry-operator:0.162.0` (OCI index) has amd64/…. The edot-0.162.0
  "per-arch tags only" trap does not apply.

### 1.3 Why it was held, and what actually breaks

1. **Deny rule `*opentelemetry-kube-stack*`** (HELD 2026-10-12, F-c01269d5). Its
   removal condition: "rendered offline … or the policy disabled in values, and the
   bump goes through an attended window". The policy is disabled in values
   (`featureGatesMap: {operator.networkpolicy: false}`, 0e976cf5). §3.1 proves
   offline that the pin reaches the rendered operator args.
   `autonomy_override: human-gated` makes the run attended. **Upstream code at
   v0.162.0** (`pkg/featuregate/featuregate.go:36-41`) still registers
   `operator.networkpolicy` at `StageAlpha`, and `operand.networkpolicy` is likewise alpha. So
   the `-` pin is a valid gate name. It does not trip the "cannot disable a stable
   gate" startup error, which is the failure that would matter on this bump.
2. **The 0.x minor axis.** The breaking changes that hit our config, from the
   0.160/0.161/0.162 release notes, checked against the rendered CR config
   (receivers file_log, host_metrics, k8s_cluster, k8s_objects, kubelet_stats, otlp,
   prometheus; processors batch, k8s_attributes, memory_limiter,
   resource/hostname, resource_detection/env; exporters otlp, debug; extensions
   k8s_leader_elector/*):
   - **FEATURE LOSS, pinned away by Step A** (from 0.25.1, re-verified at v0.162.0).
     contrib 0.161.0 🛑 `processor/k8s_attributes` promotes
     `processor.k8sattributes.DontEmitV0K8sConventions` to beta (enabled by default).
     With the gate on, the configured `container.image.tag` is dropped (V0→V1
     rename to `container.image.tags`, which the chart preset does not configure).
     The gate is **alpha at v0.159.0** (`metadata.yaml`: `stage: alpha`,
     `from_version: v0.145.0`, off by default, so the `-gate` pin is a harmless no-op
     on the 0.159 binary that Step A lands on first) and **beta at v0.161.0 and
     v0.162.0** (`stage: beta`, same `from_version`, byte-identical at the two tags;
     re-read 2026-11-02), where the pin is the needed one. Remedy from the
     upstream README "Semantic Conventions Compatibility": disable
     `DontEmitV0K8sConventions`. Re-measured 2026-10-31: in the last 15 min,
     **385 887 `metrics-*` docs carry `resource.attributes.container.image.tag`,
     0 carry `.tags`**.
   - contrib 0.160.0 🛑 `k8s_attributes` `deployment_name_from_replicaset` removed.
     Not in our config. No action.
   - contrib 0.160.0 🛑 `k8s_attributes` internal telemetry format. The daemon
     collectors' :8888 has no consumer. No action.
   - contrib 0.161.0 🛑 `kubelet_stats` `cpuUsageScrapeBased` beta (`*.cpu.usage`
     becomes a rate and is absent on the first scrape). No repo consumer (0.25.1
     grep). **Accepted, not pinned** (a second pin is a second future crash, §6).
   - **contrib 0.162.0 (new for this plan):**
     - 🛑 `pkg/prometheus` `PermissiveLabelSanitization` → beta (`_foo` labels no
       longer prefixed `key_`). This is the OTel→Prometheus label translation used by
       Prometheus *exporters*. We have none; our `prometheus` receiver scrapes
       annotated pods into OTLP. No action.
     - 🛑 `receiver/prometheus` `IgnoreScopeInfoMetric` → stable. We do not
       set the gate, so there is no startup error. `otel_scope_info` is now converted like
       any metric. No consumer. No action.
     - 🛑 removals (`wavefront` receiver, `flush`/`num_workers` on the
       elasticsearch exporter, stable OTTL / transform gates), plus kafka,
       signal_to_metrics, adaptive_tail_sampling, signing, cardinality_guardian:
       none of these is in our pipelines. (The elasticsearch-exporter removal
       matters for **edot-collector's** own bump plans, not here. The daemon
       collectors only speak OTLP to edot.)
     - Deprecation only: `kubelet_stats` `k8s.{pod,container}.{cpu,memory}.node.utilization`.
       These are not removed yet. Our receiver config sets no `metrics:` override,
       and the deprecation does not change emission.
     - Bug fix `processor/k8s_attributes` (#51188): *"Emit the semantic
       convention deprecation warnings that were unreachable because they were
       evaluated before the extraction rules were populated"*. Source diff
       v0.161.0 → v0.162.0 `processor.go`: the `createProcessorOpts` loop moved
       ABOVE the `kp.rules.ContainerImageTag` warning block. **This changes the §4.2
       gate** (see there).
   - **operator 0.161.0** 🛑 `--create-rbac-permissions` removed (not in our args).
     OpAMP Bridge IDs change (no bridge).
   - **operator 0.162.0** 🛑 NodeJS auto-instrumentation upgrade block across
     0.79.0 (no Instrumentation CR). New: PHP/Ruby auto-instrumentation, both
     off by default and unused. Enhancement: inject the cluster TLS profile as
     `curve_preferences`. Per `internal/operator/setup.go:89` this happens only when
     `cfg.TLS.ConfigureOperands` is set (an OpenShift TLS-profile path), and it is not
     in our rendered args. Fix: `service.telemetry` is kept when unparsable (we set
     none, rendered `service.telemetry: None`).
3. **Collector-image compatibility with edot-collector.** The daemon collectors export
   plain OTLP/gRPC (`otlp` exporter, `tls.insecure`) to `edot-collector`, which
   runs `otel/opentelemetry-collector-contrib:0.161.0` live. OTLP is a stable wire
   protocol. A 0.162 sender into a 0.161 receiver needs no coordination, and
   neither do the edot-0.163.2/0.164.0 plans in either order. §4.4 measures it end-to-end.

### 1.4 Operand NetworkPolicy — expected to stay, by code path

`otel-operator-daemon-collector-networkpolicy` (ingress-only, ports
8888/4317/4318) exists because the live CR carries `spec.networkPolicy.enabled:
true` (measured `np=[true]`). At v0.162.0, `internal/webhook/collector_webhook.go:107`
still defaults the field only when it is `nil` (and only with the now-alpha
operand gate). `internal/manifests/collector/networkpolicy.go:16` builds the policy
when the field is `true`. helm-controller neither sets nor removes the field: it is
absent from all three chart renders. **Expected: the policy is unchanged.** If it
disappears, it is a WARN for a finding (§4.3), not a rollback.

## 2) Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` in zsh on the Mac mini.

```bash
# (a) premises
.venv/bin/python3 runbooks/plan-premises.py otel-operator-0.26.1
# PASS: all 8 premises OK. Any FAIL = stop; do not "fix" a premise to proceed.

# (b) Flux + helm not mid-flight; RECORD the deployed 0.24.3 revision for §5.3
flux get hr otel-operator -n monitoring
helm -n monitoring history otel-operator --max 3
# PASS: Ready True, newest revision `deployed` 0.24.3 (rev 70 on 2026-10-31). A `pending-*` = stop.

# (c) PR #351 still the one-line bump to EXACTLY 0.26.1, CI green
gh pr view 351 --json state,files,statusCheckRollup \
  -q '.state, [.files[].path], [.statusCheckRollup[]|.name+"="+.conclusion]'
gh pr diff 351 | grep '^[-+] '
# PASS: OPEN; files == [kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml];
# all checks SUCCESS; diff exactly `-      version: 0.24.3` / `+      version: 0.26.1`.
# FAILS AS: `+ version: 0.26.2` (or anything else) = Renovate re-targeted again -> STOP,
# re-plan (this happened once already, 0.25.1 -> 0.26.1). Do NOT merge a target this plan did not render.

# (d) the superseded plan is not also queued in this window
grep -m1 '^status:' runbooks/maintenance/plans/otel-operator-0.25.1.md
# PASS: `status: superseded`. If it still reads `vetted` with a window, retire it before proceeding.

# (e) baselines (record in the run log)
kubectl -n monitoring get pods -l app.kubernetes.io/component=opentelemetry-collector \
  -o 'custom-columns=N:.metadata.name,NODE:.spec.nodeName,START:.status.startTime,R:.status.containerStatuses[0].restartCount'
kubectl -n monitoring get pods -l app.kubernetes.io/name=opentelemetry-operator \
  -o 'custom-columns=N:.metadata.name,START:.status.startTime,R:.status.containerStatuses[0].restartCount'
kubectl get netpol -A -o name | wc -l
# 2026-10-31: 3 collector pods (nuc14-01/02/03, R=0, image collector-k8s:0.159.0);
# operator pod ...-lggtf R=0; 5 NetworkPolicies cluster-wide.

# (e, continued) pre-window ALERT LIST: the baseline §4.4 compares against. RECORD the output in the run log
# (§4.4 "nothing new compared with the pre-window alert list" is only checkable if this was captured).
kubectl get --raw "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/alerts" \
  | grep -o '"alertname":"[^"]*"' | grep -vE 'Watchdog|InfoInhibitor' | sort | uniq -c
# Record at execution time; do not hardcode. For orientation only, 2026-11-02 it read: AragPushMetricMissing,
# AragScrapeDown, ICloudBackupAuthRequired, ICloudBackupSyncMetricMissingAndrea, ICloudDriveSyncMetricMissingAndrea,
# LonghornVolumeSnapshotChainNotPruned, PalletCriticalSourceStale, TargetDown (arag-scrape).
# PASS: the command returns without a kubectl/grep error (an empty list is legitimate). An error means the
# instrument is blind: fix that before starting (see (f)).

# (f) the Prometheus instrument §4 reads is up and stable (Renovate PR #428 risk, see §6)
kubectl get hr kube-prometheus-stack -n monitoring
kubectl get pod prometheus-kube-prometheus-stack-0 -n monitoring
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=kube_deployment_status_replicas_available%7Bnamespace%3D%22monitoring%22%2Cdeployment%3D%22otel-operator-opentelemetry-operator%22%7D" \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('avail=',[x['value'][1] for x in r] or 'EMPTY')"
kubectl get --raw "${P}?query=kube_daemonset_status_number_ready%7Bnamespace%3D%22monitoring%22%2Cdaemonset%3D%22otel-operator-daemon-collector%22%7D" \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('ready=',[x['value'][1] for x in r] or 'EMPTY')"
# PASS: HR `READY True` (message: Helm upgrade succeeded); pod prometheus-kube-prometheus-stack-0 `2/2 Running` with
# an AGE of more than ~15 min and no fresh restart; `avail= ['1']` and `ready= ['3']`.
# FAILS AS: HR not Ready / `Unknown` (an upgrade is in flight), the pod age is minutes, or either query prints EMPTY.
# That is the signature of PR #428 (92.11.1 -> 92.17.0) auto-applying at the Step 0 of this window or a nightly
# just before it. Wait for Prometheus to settle and re-run; do not start §3.1 against a blind instrument.
# Measured 2026-11-02: HR Ready True (chart 92.11.1, release v50), pod 2/2 Running, restarts 0, age 10d.
```

## 3) Steps

### 3.1 GATE — offline render proof (deny-rule removal condition). Must print `GATE PASS`.

Paste as-is: the block runs in a subshell `( … )`, so its `exit 1` leaves only the
subshell and never closes an interactive zsh, and `cd` does not leak out.

```bash
(
REPO=/Users/mu/code/cberg-home-nextgen
G=$(mktemp -d /tmp/otel-0261-gate.XXXXXX)
cd "$G" || exit 1
helm pull opentelemetry-kube-stack --repo https://open-telemetry.github.io/opentelemetry-helm-charts \
  --version 0.26.1 --untar --untardir c || { echo "GATE FAIL: pull"; exit 1; }
python3 -c "
import yaml
d=[x for x in yaml.safe_load_all(open('$REPO/kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml')) if x and x.get('kind')=='HelmRelease'][0]
yaml.safe_dump(d['spec']['values'],open('values.yaml','w'))"
helm template otel-operator c/opentelemetry-kube-stack -n monitoring -f values.yaml --include-crds > r.yaml \
  || { echo "GATE FAIL: render"; exit 1; }
GATE=$(grep -c -- '- --feature-gates=-operator.networkpolicy$' r.yaml)
IMG=$(grep -c 'opentelemetry-operator/opentelemetry-operator:0.162.0"' r.yaml)
COLIMG=$(grep -c -- '--collector-image=otel/opentelemetry-collector-k8s:0.162.0$' r.yaml)
CARGS=$(python3 -c "
import yaml
for d in yaml.safe_load_all(open('r.yaml')):
    if d and d.get('kind')=='OpenTelemetryCollector': print((d['spec'].get('args') or {}).get('feature-gates',''))")
echo "gate_arg=$GATE operator_img=$IMG collector_img=$COLIMG collector_gate='$CARGS' dir=$G"
if [ "$GATE" = 1 ] && [ "$IMG" = 1 ] && [ "$COLIMG" = 1 ] && [ "$CARGS" = "-processor.k8sattributes.DontEmitV0K8sConventions" ]; then echo "GATE PASS"; else echo "GATE FAIL"; fi
)
```

Run it **after Step A is pushed and before Step B**. Before Step A it prints
`collector_gate=''` and `GATE FAIL`. That is the negative control, and it shows the
gate can fail. Measured 2026-10-31 with HEAD values: `gate_arg=1 operator_img=1
collector_img=1 collector_gate=''`. With the Step-A edit applied to a scratch copy:
`gate_arg=1 operator_img=1 collector_img=1` and CR `args {'feature-gates':
'-processor.k8sattributes.DontEmitV0K8sConventions'}`, i.e. PASS.
**FAILS AS:**
- `gate_arg=0`: the pin was lost, or the subchart renamed `featureGatesMap`. STOP.
- `operator_img=0` / `collector_img=0`: the chart was republished under the same
  version, or the images were pinned. STOP and re-plan, because §1.3 covers 0.162.0 only.
- `collector_gate` wrong: Step A did not land. STOP.

### 3.2 Step A — pin the k8s_attributes legacy-semconv gate (lands on the 0.159 collector first)

Dry-tested 2026-10-31 with BSD sed on a scratch copy
(`/tmp/otel-0261-plan/hr.scratch.yaml`). The diff was exactly `66a67,69` (the three
lines below). A YAML re-parse gave `collectors.daemon.args = {'feature-gates':
'-processor.k8sattributes.DontEmitV0K8sConventions'}`, with `mode: daemonset` intact.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml
grep -c '^        mode: daemonset$' "$F"        # MUST print 1 before editing
grep -c 'DontEmitV0K8sConventions' "$F"          # MUST print 0 (else Step A already landed: skip to §3.3)
sed -i '' -e '/^        mode: daemonset$/a\
        args:\
          # collector 0.161+ turns k8s_attributes legacy semconv OFF (beta gate); keep container.image.tag\
          feature-gates: "-processor.k8sattributes.DontEmitV0K8sConventions"
' "$F"
git diff "$F"          # expect +3 lines under collectors.daemon, nothing else
git commit --only "$F" -m "otel-operator: keep container.image.tag across collector 0.162 (k8s_attributes DontEmitV0 gate off)

Prep for opentelemetry-kube-stack 0.26.1 (plan otel-operator-0.26.1 §3.2).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git log -1 --format=%s     # MUST be the subject above (shared worktree)
git show --stat HEAD       # only helmrelease.yaml
git push
STEP_A_SHA=$(git rev-parse HEAD); echo "$STEP_A_SHA"
kubectl -n monitoring rollout status daemonset/otel-operator-daemon-collector --timeout=10m
kubectl get ds otel-operator-daemon-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.template.spec.containers[0].args}'; echo
```
PASS: the image is still `otel/opentelemetry-collector-k8s:0.159.0`. Args are
`["--config=/conf/collector.yaml","--feature-gates=-processor.k8sattributes.DontEmitV0K8sConventions"]`
(the order may differ). All 3 pods are Ready with R=0.
FAILS AS:
- Pods CrashLoop with `no such feature gate`. That contradicts `metadata.yaml`
  (the gate is registered, as alpha, since v0.145.0). Revert `$STEP_A_SHA` (§5.1) and STOP.
- Args are unchanged after 10 min: the HR has not reconciled. Check
  `flux get hr`. Do not proceed.

### 3.3 Step B — run the §3.1 gate, then merge the Renovate PR (attended, operator GO recorded)

```bash
cd /Users/mu/code/cberg-home-nextgen
# §3.1 must print GATE PASS now; §2(c) must still show `+      version: 0.26.1`
gh pr update-branch 351 2>/dev/null || true     # rebase onto Step A if GitHub reports it behind
gh pr diff 351 | grep '^[-+] '                   # re-check AFTER update-branch: still exactly 0.24.3 -> 0.26.1
gh pr merge 351 --squash --delete-branch
git pull --ff-only
git log -1 --format='%h %s'          # must be the #351 squash
grep -n 'version: 0.26.1' kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml
grep -n 'DontEmitV0K8sConventions' kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml   # Step A survived
MERGE_SHA=$(git rev-parse HEAD); echo "$MERGE_SHA"
```
No manual `flux reconcile`: the push webhook drives the source. Only if
`flux get hr otel-operator -n monitoring` still shows 0.24.3 after 10 min, run
`flux reconcile hr otel-operator -n monitoring --with-source`.

### 3.4 Watch the rollout

```bash
kubectl -n monitoring rollout status deploy/otel-operator-opentelemetry-operator --timeout=5m
kubectl -n monitoring rollout status daemonset/otel-operator-daemon-collector --timeout=10m
ROLLOUT_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "ROLLOUT_TS=$ROLLOUT_TS"   # rollout status can return before the operator rewrites the DaemonSet: if section 4.1 shows any pod still on 0.159.0, re-stamp ROLLOUT_TS after all three show 0.162.0
flux get hr otel-operator -n monitoring
```
Expect `Ready True` and `Helm upgrade succeeded … 0.26.1`. While §3.4 runs, run
the §4.3 netpol check once **immediately** (do not wait for the HR timeout). If an
`opentelemetry-operator` policy appears, go to §5.3 now.

### 3.5 After §4 passes — bookkeeping

```bash
gh pr view 356 --json state -q .state
# Renovate should close #356 (0.24.x line) on its next run once main is past 0.24.x.
# If still OPEN 24 h after the merge: gh pr close 356 --comment "superseded by #351 (0.26.1), plan otel-operator-0.26.1"
```
Close the agent-authored plan findings with the merge commit (they do not
auto-close): `runbooks/policy-cli.py finding close F-61e4d5b6 --commit "$MERGE_SHA"`
and `… F-3b519d4a …` once #356 is closed. F-60ebcdb5 (version) clears on the next
sweep's version scan.

## 4) Verification

### Floor (shape — necessary, not sufficient)

```bash
kubectl get hr otel-operator -n monitoring \
  -o jsonpath='{.status.history[0].chartVersion}/{.status.history[0].status} ready={.status.conditions[?(@.type=="Ready")].status}'; echo
kubectl get opentelemetrycollector otel-operator-daemon -n monitoring \
  -o jsonpath='ver={.status.version} scale={.status.scale.statusReplicas}'; echo
```
PASS: `0.26.1/deployed ready=True`; `ver=0.162.0 scale=3/3` (baseline 2026-10-31:
`ver=0.159.0 scale=3/3`).

### 4.1 CONTENTS ASSERTION — both binaries are the target, gate still off in the operator

```
CONTENTS ASSERTION: the RUNNING operator pod is image 0.162.0 with
  --feature-gates=-operator.networkpolicy, and every RUNNING collector pod is
  collector-k8s:0.162.0. Measured on live pods (not the template; see
  feedback_rollout_status_old_generation), compared to the 0.159.0 baseline.
CONTROL: metric kube_deployment_status_replicas_available — otel-operator-opentelemetry-operator must be 1
```
```bash
kubectl -n monitoring get pods -l app.kubernetes.io/name=opentelemetry-operator \
  -o 'custom-columns=N:.metadata.name,IMG:.status.containerStatuses[0].image,R:.status.containerStatuses[0].restartCount,READY:.status.containerStatuses[0].ready'
kubectl get pod -n monitoring -l app.kubernetes.io/name=opentelemetry-operator \
  -o 'jsonpath={.items[0].spec.containers[0].args}' | tr ',' '\n' | grep -i feature-gates
kubectl -n monitoring get pods -l app.kubernetes.io/component=opentelemetry-collector \
  -o 'custom-columns=N:.metadata.name,NODE:.spec.nodeName,IMG:.status.containerStatuses[0].image,R:.status.containerStatuses[0].restartCount'
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=kube_deployment_status_replicas_available%7Bnamespace%3D%22monitoring%22%2Cdeployment%3D%22otel-operator-opentelemetry-operator%22%7D" \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('avail=',[x['value'][1] for x in r] or 'EMPTY')"
```
PASS:
- One operator pod `…opentelemetry-operator:0.162.0`, ready `true`, R=0.
- The grep prints `"--feature-gates=-operator.networkpolicy"`.
- Three collector pods on nuc14-01/02/03, each `…collector-k8s:0.162.0` (the
  status image is shown as `docker.io/otel/…`), R=0.
- `avail= ['1']`.

FAILS AS:
- Any pod still on 0.159.0: the roll stalled.
- Operator R>0 / not ready: check §4.3, then go to §5.3.
- The grep is empty: the gate was lost.
- `avail= EMPTY`: the instrument is blind. Treat as FAIL **unless** a kube-prometheus-stack roll is in
  flight (§6, PR #428): then wait for Prometheus to settle and retry before judging.

### 4.2 CONTENTS ASSERTION — container.image.tag is still emitted (the §1.3 feature-loss guard)

```
CONTENTS ASSERTION: after the 0.162 roll, metrics documents still carry
  resource.attributes.container.image.tag (non-zero floor), AND every collector
  logged the upstream "is being renamed" warning (gate OFF path) and none logged
  "will NOT be emitted" (gate ON path). Code path: processor.go Start() @ contrib
  v0.162.0. Compared to the 2026-10-31 baseline (385 887 docs / 15 min, 0 `.tags`).
```
```bash
for p in $(kubectl -n monitoring get pods -l app.kubernetes.io/component=opentelemetry-collector -o name); do
  printf "%s notemitted=%s renamed=%s\n" "$p" \
    "$(kubectl -n monitoring logs "$p" | grep -ci 'container.image.tag is configured but will NOT be emitted')" \
    "$(kubectl -n monitoring logs "$p" | grep -ci 'container.image.tag is being renamed')"
done
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 19200:9200 >/dev/null 2>&1 & PF=$!
sleep 5
for f in container.image.tag container.image.tags; do printf "%s: " "$f"
  curl -k -s --max-time 240 -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
    "https://localhost:19200/metrics-*/_count" -d '{"query":{"bool":{"filter":[
      {"range":{"@timestamp":{"gte":"'"$ROLLOUT_TS"'"}}},{"exists":{"field":"resource.attributes.'"$f"'"}}]}}}'; echo
done
kill $PF 2>/dev/null
```
**Why the log half now works (correction of the 0.25.1 gate).** Up to and including
v0.161.0, `Start()` evaluated `kp.rules.ContainerImageTag` *before* the option loop
populated `kp.rules` (v0.159.0 `processor.go`: warning at :77, `allOptions :=` at
:100). Neither warning could ever print. Live negative control 2026-10-31 on the
0.159 pods: `notemitted=0 renamed=0` on all three. The 0.25.1 plan's `renamed>=1`
PASS would therefore have FAILED falsely on 0.161, and its `notemitted=0` could never
fail. contrib #51188 (v0.162.0) moved the option loop above the warnings, so on
0.162 exactly one of the two lines is logged per `k8s_attributes` instance.

PASS: every pod prints `notemitted=0` and `renamed>=1` (expected 3: one
`k8s_attributes` instance in each of the logs/metrics/traces pipelines).
`container.image.tag` count **> 0**. `container.image.tags` count is 0 (the plural is
not configured).
FAILS AS:
- `notemitted>=1`: the gate arg did not reach the binary and the tag is being
  dropped. This is feature loss, so go to §5.1.
- `renamed=0` and `notemitted=0`: the pod is not 0.162 (check §4.1), or the
  upstream text changed. INCONCLUSIVE counts as FAIL; check the ES half before deciding.
- Tag count `0`: feature loss, go to §5.1.
- curl timeout or empty output: the instrument is blind. Re-run with a narrower
  window. This `metrics-*` exists-count returned in under 2 min on 2026-10-31.

### 4.3 CONTENTS ASSERTION — no operator NetworkPolicy; operand policy unchanged

```
CONTENTS ASSERTION: the NetworkPolicies in monitoring are exactly
  {otel-operator-daemon-collector-networkpolicy}, with a cluster-wide positive control.
```
```bash
kubectl get netpol -A -o name | wc -l                              # positive control: 5
kubectl get netpol -n monitoring -o jsonpath='{.items[*].metadata.name}'; echo
kubectl get opentelemetrycollector otel-operator-daemon -n monitoring -o jsonpath='np=[{.spec.networkPolicy.enabled}]'; echo
```
PASS: count `5`; the list is exactly `otel-operator-daemon-collector-networkpolicy`;
`np=[true]` (all three measured 2026-10-31).
FAILS AS:
- An `opentelemetry-operator` entry: the deadlock policy exists. Go to §5.3 at once.
- The collector policy is missing (count 4, `np=[]`): this is a **WARN, not a
  rollback**. §1.4's prediction was wrong. File a finding.

### 4.4 CONTENTS ASSERTION — telemetry flows from every node (load-bearing)

Run **≥15 min after `$ROLLOUT_TS`**.

```
CONTENTS ASSERTION: pod-log documents from ALL THREE nodes land in Elasticsearch
  in a window that starts after the roll. Measured in ES (not at the exporter;
  _bulk returns 200 even when items are rejected), compared to the §2(e) node set and alert list.
CONTROL: metric kube_daemonset_status_number_ready — otel-operator-daemon-collector must be 3
CONTROL: alertname OtelDaemonCollectorDown — must NOT be firing
```
```bash
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 19200:9200 >/dev/null 2>&1 & PF=$!
sleep 5
curl -k -s --max-time 240 -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
  -X POST "https://localhost:19200/logs-generic-default/_search?size=0" -d '{
   "query":{"range":{"@timestamp":{"gte":"'"$ROLLOUT_TS"'"}}},
   "aggs":{"by_node":{"terms":{"field":"resource.attributes.k8s.node.name","size":10}}}}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['aggregations']['by_node']['buckets'])"
kill $PF 2>/dev/null
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=kube_daemonset_status_number_ready%7Bnamespace%3D%22monitoring%22%2Cdaemonset%3D%22otel-operator-daemon-collector%22%7D" \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('ready=',[x['value'][1] for x in r] or 'EMPTY')"
kubectl get --raw "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/alerts" \
  | grep -o '"alertname":"[^"]*"' | grep -vE 'Watchdog|InfoInhibitor' | sort | uniq -c
```
PASS:
- Three buckets, `k8s-nuc14-01/02/03`, each **> 0**. The baseline 2026-10-31 over 15 min
  was 5 016 / 8 411 / 6 191.
- `ready= ['3']`.
- No `OtelDaemonCollectorDown` (the rule exists: 1 PrometheusRule match on
  2026-10-31), and no alertname beyond the list recorded in §2(e) (diff the two `uniq -c` outputs by name).

This is a presence check, not a volume check.
FAILS AS:
- A missing node bucket: that collector is Ready but shipping nothing, and no alert
  catches it.
- `[]` or `ready= EMPTY`: the instrument is blind. If Renovate PR #428 (kube-prometheus-stack
  92.11.1 -> 92.17.0) landed in the same Step 0, an EMPTY here (and in §4.1) means **retry after
  Prometheus settles** (re-run §2(f)), not a plan failure. Only a persistent EMPTY with a settled
  Prometheus counts as FAIL.
- A new alertname versus §2(e): investigate before calling it a pass (an `OtelDaemonCollectorDown` is a FAIL).

## 5) Rollback

### 5.1 Expected path — revert the merge (and optionally Step A)

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit "$MERGE_SHA"
git log -1 --format=%s     # confirm the subject is THIS revert (shared worktree)
git show --stat HEAD       # only helmrelease.yaml
git push
kubectl -n monitoring rollout status deploy/otel-operator-opentelemetry-operator --timeout=5m
kubectl -n monitoring rollout status daemonset/otel-operator-daemon-collector --timeout=10m
```
This is safe while the operator is Ready.
- The operator goes back to 0.159.0 with `--collector-image` 0.159.0. The DaemonSet
  image follows the operator's `--collector-image`, so the collectors return to
  0.159.0. Confirm on the pods (§5.2).
- The CRDs revert to the 0.24.3 schema. The fields added since are unused and are
  pruned on read. Nothing is forward-only.
- The Step A arg can **stay**. The gate is alpha (off by default) at v0.159.0, where
  `-gate` is a harmless no-op. It becomes the needed pin at 0.161+ (beta).
  Revert `$STEP_A_SHA` only if Step A itself is the fault (§3.2).

If Renovate re-opens/re-targets #351 after the revert, leave it open. Do not
re-merge outside a window.

### 5.2 Confirm the cluster is back

```bash
kubectl get hr otel-operator -n monitoring -o jsonpath='{.status.history[0].chartVersion}/{.status.history[0].status}'; echo   # 0.24.3/deployed
kubectl -n monitoring get pods -l app.kubernetes.io/component=opentelemetry-collector \
  -o 'custom-columns=N:.metadata.name,IMG:.status.containerStatuses[0].image'                                                 # all :0.159.0
kubectl -n monitoring get ds otel-operator-daemon-collector -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled}'; echo  # 3/3
```
The collector pods may stay on 0.162.0 after the operator is back on 0.159.0 (the
operator keeps the CR's recorded version). That is **not** an emergency: 0.162 plus
the Step A arg is the state §4 verified. Record it and handle the re-pin in a
follow-up plan. Then re-run §4.3 and §4.4 with a fresh `ROLLOUT_TS`.

### 5.3 The RollbackFailed trap — if the operator is NOT Ready

Symptom: the operator pod is in CrashLoopBackOff or not Ready, the HR goes
`UpgradeFailed` then `RollbackFailed`, and helm history shows `failed` revisions (the
2026-10-12 shape: revs 68/69 `failed` "timeout waiting for … OpenTelemetryCollector
… InProgress"). A `git revert` alone will NOT converge, because every
upgrade and rollback waits on a CR that only a Ready operator can settle.

1. **Diagnose (read-only):**
   ```bash
   kubectl -n monitoring get pods -l app.kubernetes.io/name=opentelemetry-operator
   kubectl -n monitoring logs deploy/otel-operator-opentelemetry-operator --tail=80 | grep -iE 'networkpolicy|i/o timeout|dial tcp|feature gate|forbidden|endpointslices|finalizers'
   kubectl get netpol -n monitoring -o wide
   helm -n monitoring history otel-operator --max 5
   ```
   `forbidden … endpointslices … watch` or `… deployments/finalizers` means the
   ClusterRole did not get the new rule. That is a different cause, but the same
   recovery path below applies.
2. **Unblock the operator (BREAK-GLASS, direct mutation; operator approval
   recorded in the run log).** Only if `kubectl get netpol -n monitoring` lists
   `opentelemetry-operator`:
   `kubectl delete netpol opentelemetry-operator -n monitoring`. Do NOT delete the
   operator Deployment. Then wait with
   `kubectl -n monitoring rollout status deploy/otel-operator-opentelemetry-operator --timeout=5m`.
3. **Revert in git** (§5.1) if not already pushed.
4. **Clear Flux's exhausted retry counter and re-drive.** This is operator-approved
   and is the SOP's wedge path, `docs/sops/application-update.md` §11:
   ```bash
   flux reconcile hr otel-operator -n monitoring --reset
   flux reconcile hr otel-operator -n monitoring --force
   ```
   If helm is left `pending-upgrade`/`pending-rollback`, roll back to the deployed
   0.24.3 revision recorded in §2(b) (rev 70 as of 2026-10-31):
   `helm rollback otel-operator <that-rev> -n monitoring --wait=false`. Then run
   `flux reconcile hr otel-operator -n monitoring --force`. NEVER use a revision
   older than 70 (the 0e976cf5 roll-forward), because those predate the gate pin.
5. Confirm with §5.2, then file a finding.

## 6) Interference notes

- **Attended slot only** (`autonomy_override: human-gated`): sat-attended or
  sun-attended. No reboot is needed, and the plan does not need to be exclusive.
- **Scheduling (addresses the sat-attended:2026-11-07 warnings).** That slot
  held `helm-drift-detection` (60 min) + `otel-operator-0.25.1` (55 min) =
  115 min against a 70-min schedulable budget (90 − 20 Step-0) until 2026-11-02,
  when 0.25.1 was superseded and `helm-drift-detection` moved to 11-28. The slot is
  now free of conflicting plans. Options, in order of preference:
  1. **Give 11-07 to this plan SOLO** (55/70). `helm-drift-detection` (60/70; its
     own frontmatter wants to be the LAST/only plan of an attended window) is
     already on **sat-attended:2026-11-28**. This keeps the operator-chosen order
     "otel-operator before edot" (edot-collector-0.163.2 is on nightly:2026-11-10).
  2. Otherwise put this plan on **sat-attended:2026-12-05 solo** (11-28 now holds
     helm-drift-detection, a conflict). The edot plan then runs first. That is acceptable (§1.3.3: OTLP needs no ordering), but edot's
     "after otel-operator" comment becomes stale.
  - Not 11-14 (python-fleet 35 + 55 = 90 > 70) and not 11-21 (authentik 45 + 55 =
    100 > 70). sun-attended:2026-11-29 does NOT work:
    redis-fleet-8.10.3 (80 min) is slotted there and is in this plan's conflicts_with.
    Prefer a Saturday.
  - Optional shrink: Step A (§3.2) is a values-only, same-binary change. A window
    agent may land it in an earlier slot as its own unit, which leaves ~40 min for the
    attended run. Only do this if §3.2's PASS/FAILS gate is run there too.
- **Superseded plan retired (done 2026-11-02):** `otel-operator-0.25.1` is
  `status: superseded`, `superseded_by: otel-operator-0.26.1`, `window: null`, and the
  reciprocal `conflicts_with` entries in edot-collector-0.164.0, talos-linux-1.14.5 and
  grafana-14.1.0 already name `otel-operator-0.26.1`.
- **edot-collector-0.163.2 / 0.164.0: separate slots, either order.** Both gate on
  ES ingestion through the same edot hop. Note that the 0.162 elasticsearch-exporter
  breaking changes (`flush`/`num_workers` removed, profiles to 9.6 data streams)
  are edot's concern, not this plan's.
- **Log gap:** each node loses ~10–30 s of pod logs per collector roll, and this
  plan rolls them twice. Other same-window plans whose gates read ES log continuity
  must read outside those minutes.
- **Future hazard of the Step A pin:** when contrib promotes
  `processor.k8sattributes.DontEmitV0K8sConventions` to **stable**, `-gate` becomes
  a startup error, and the collector would crash-loop on that bump. It is still beta
  at v0.162.0. Every future otel-operator plan must re-check the gate's `stage:` in
  `processor/k8sattributesprocessor/metadata.yaml` at the target tag. The proper fix
  (follow-up plan/finding, out of scope here) is to configure
  `container.image.tags`, migrate Kibana consumers of `container.image.tag`, and then
  drop the pin.
- **Deny rule stays.** Narrowing `*opentelemetry-kube-stack*` is a separate
  operator decision, made after this lands.
- **AR-124 / F-369edfe8:** the collector image moves off collector-k8s 0.159.0. Let
  the next sweep re-score it. Do not close or renew it by hand.
- **Prometheus is read by §4, and PR #428 can disturb it.** No `kube-prometheus-stack` plan file
  exists (2026-11-02), but Renovate PR #428 (kube-prometheus-stack 92.11.1 -> 92.17.0) is in the
  age cooldown, has no deny rule in `runbooks/auto-update-policy.yaml`, and may auto-apply at Step 0
  of a nightly or of the window itself, restarting the Prometheus pod the §4.1/§4.4 queries read.
  Before the run, §2(f) confirms the HelmRelease is Ready and `prometheus-kube-prometheus-stack-0`
  is stable (queries non-EMPTY). If #428 lands in the same Step 0, an EMPTY in §4.1/§4.4 means retry
  after Prometheus settles, not a plan failure. If a kube-prometheus-stack plan is added for the same
  night, serialize it into a separate slot and add it to `conflicts_with`.
