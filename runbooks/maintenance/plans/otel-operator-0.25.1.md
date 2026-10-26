---
plan_id: otel-operator-0.25.1
component: otel-operator               # HelmRelease monitoring/otel-operator; CHART is the umbrella
                                       # opentelemetry-kube-stack (subcharts otel-crds, prometheus-crds,
                                       # opentelemetry-operator)
pr: 351                                # "feat(helm): update opentelemetry-kube-stack ( 0.24.3 → 0.25.1 )",
                                       # one-line diff to helmrelease.yaml; CI green (Flate Render Gate,
                                       # Flux Local Diff hr+ks), checked 2026-10-17
kind: chart
current: "0.24.3"                      # MEASURED 2026-10-17: HR spec 0.24.3, history[0] 0.24.3/deployed
target: "0.25.1"
update_type: minor
risk: medium                           # Unlike 0.24.4 this is NOT a label-only bump: the operator binary
                                       # moves 0.159.0 -> 0.161.0 (subchart 0.123.0 -> 0.126.0) and, through
                                       # the operator's --collector-image default, the COLLECTOR binary moves
                                       # 0.159.0 -> 0.161.0 on all 3 nodes. Collector 0.161 flips a beta gate
                                       # that silently STOPS emitting container.image.tag (§1.3) - a feature
                                       # loss this plan pins away. Plus the RollbackFailed failure shape this
                                       # HR has shown once (F-97c88a5c).
est_duration_min: 55                   # 10 pre-checks + 10 Step A (args commit, 3-pod roll, gate)
                                       # + 10 Step B (merge, operator + 3-pod roll) + 15 SETTLE before the ES
                                       # gate + 8 verification + 2 buffer
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:                           # every object verified to EXIST live 2026-10-17
    - helmrelease/otel-operator                         # git edits: chart version + collectors.daemon.args
    - deployment/otel-operator-opentelemetry-operator   # ROLLS: image 0.159.0 -> 0.161.0, new arg
                                                        # --target-allocator-image (inert, no TA CR)
    - opentelemetrycollector/otel-operator-daemon       # spec.args gains feature-gates; spec.upgradeStrategy
                                                        # automatic -> operator bumps it to 0.161.0
    - daemonset/otel-operator-daemon-collector          # ROLLS (likely twice: Step A args, Step B image);
                                                        # updateStrategy maxSurge 0 / maxUnavailable 1
    - clusterrole/otel-operator-opentelemetry-operator-manager  # gains `watch` on discovery.k8s.io
                                                        # endpointslices (required by operator 0.161)
    - secret/otel-operator-opentelemetry-operator-controller-manager-service-cert  # pre-upgrade hook,
                                                        # regenerated every upgrade (autoGenerateCert.recreate)
    - mutatingwebhookconfiguration/otel-operator-opentelemetry-operator-mutation      # caBundle
    - validatingwebhookconfiguration/otel-operator-opentelemetry-operator-validation  # caBundle
    - "crd/{opentelemetrycollectors,targetallocators,instrumentations,opampbridges}.opentelemetry.io
       — CreateReplace; ADDITIVE schema only (enableServiceLinks, imagePullSecrets, revisionHistoryLimit),
       controller-gen v0.21 -> v0.22"
    - "networkpolicy/otel-operator-daemon-collector-networkpolicy — NOT edited; asserted UNCHANGED in §4.3"
  shared:
    - monitoring                       # the cluster's ONLY pod-log / host-metric / kubelet-stats / k8s-event
                                       # collection path into edot-collector -> Elasticsearch. Each node loses
                                       # ~10-30 s of pod logs per collector roll (filelog start_at end, no
                                       # storage extension), and this plan rolls them twice.
depends_on: []
conflicts_with:                        # ONLY this field is honoured by window-scheduler.py.
  - grafana-14.1.0   # reciprocal, added 2026-10-26 (sweep a1721200 plan review)
  # 2026-10-25: pruned dead refs flux-distribution-2.9.6 (executed/retired)
  - edot-collector-0.163.2             # Daemon collectors export OTLP into edot-collector.monitoring.svc:4317 and
                                       # §4.4 proves this plan via docs landing in ES THROUGH edot - a same-night
                                       # edot roll makes both plans' ES gates unattributable. SEQUENCE: this plan
                                       # FIRST, edot in a SEPARATE later slot (operator 2026-10-23).
  - flux-oci-chart-sources             # edits the SAME helmrelease.yaml (spec.chart -> chartRef)
  - helm-drift-detection               # writes spec.driftDetection into this same HelmRelease
  - talos-linux-1.14.2                 # node roll re-creates every collector pod; §4.4 per-node gate
  - talos-linux-1.14.4                 # cannot attribute a missing node (same reason)
  - home-assistant-2026.10.2           # its gates read the same log/metric path
exclusive: false
security_ref: null                     # not security-driven. Side effect: the collector image moves off
                                       # collector-k8s 0.159.0, the subject of AR-accepted F-369edfe8 -
                                       # the sweep re-scores it; this plan does not claim it.
capability_change: false               # same pipelines, same receivers/exporters, same CR spec except one
                                       # feature-gate arg whose PURPOSE is to keep today's attribute set;
                                       # new CRD fields are unused; operator NetworkPolicy stays pinned off
rollback_class: git-revert             # nothing forward-only: CRD changes are additive (older schema prunes
                                       # unknown fields on read), no data, no migrations
autonomy_override: human-gated         # REQUIRED by the deny rule's removal condition
                                       # (auto-update-policy.yaml `*opentelemetry-kube-stack*`): "the bump goes
                                       # through an attended window". §5.3 also holds a break-glass direct
                                       # mutation only an operator may authorize.
finding_refs: [F-61e4d5b6, F-e918a007] # VERIFIED 2026-10-17 via `policy-cli.py finding list --grep otel-operator`
                                       # / `--grep opentelemetry-kube-stack` / `--grep 0.25.1`:
                                       # F-61e4d5b6 (plan, AR-072): "any re-attempt ... must handle the
                                       # operator.networkpolicy feature gate ... in a plan" - this plan.
                                       # F-e918a007 (version, 0.24.3 -> 0.24.4): carried over from the
                                       # superseded otel-operator-0.24.4 plan - landing 0.25.1 answers it.
                                       # No finding exists for 0.25.1 itself.
review: ready-for-go@2026-10-23
status: vetted
window: "sat-attended:2026-11-07"      # attended slot only; assigned 2026-10-23 (coordinator), runs BEFORE edot-collector-0.163.2
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-17"
premises:
  - id: live-chart-is-0.24.3
    why: "`current:` claims 0.24.3. If the HR moved, the render diff in §1.2 and the rollback target in §5 are stale."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "0.24.3"
  - id: otel-hr-ready
    why: "Never stack a chart bump on a failing release; with remediation strategy rollback a pre-existing failure re-enters the RollbackFailed trap."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: last-release-deployed-0.24.3
    why: "The §5 rollback depends on helm's newest revision being a deployed 0.24.3."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.status.history[0].chartVersion}/{.status.history[0].status}'
    expect_exact: "0.24.3/deployed"
  - id: gate-pin-in-values
    why: "Load-bearing: operator 0.160 moved operator.networkpolicy back to alpha/off, but the pin must stay as the belt to that brace. If removed AND a later operator re-enables it, the 2026-10-12 deadlock returns."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.spec.values.opentelemetry-operator.manager.featureGatesMap}'
    expect_contains: '"operator.networkpolicy":false'
  - id: operator-image-0.159.0
    why: "§1.2's binary-delta analysis (0.159 -> 0.161 release notes) is only valid from 0.159.0."
    run: kubectl get deploy otel-operator-opentelemetry-operator -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/open-telemetry/opentelemetry-operator/opentelemetry-operator:0.159.0"
  - id: collector-image-0.159.0
    why: "§1.3's collector breaking-change analysis covers 0.160 + 0.161 only, i.e. from 0.159.0."
    run: kubectl get ds otel-operator-daemon-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "otel/opentelemetry-collector-k8s:0.159.0"
  - id: collector-args-baseline
    why: "Step A adds the feature-gate arg; if args already differ, someone changed the collector out of band and §3.2's expectation is wrong."
    run: kubectl get ds otel-operator-daemon-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].args}'
    expect_exact: '["--config=/conf/collector.yaml"]'
  - id: monitoring-netpols-exactly-collector
    why: "Baseline for §4.3: an `opentelemetry-operator` entry means the deadlock is already live; a missing collector entry means the baseline moved."
    run: kubectl get networkpolicy -n monitoring -o jsonpath='{.items[*].metadata.name}'
    expect_exact: "otel-operator-daemon-collector-networkpolicy"
---

# otel-operator — opentelemetry-kube-stack 0.24.3 → 0.25.1

**Supersedes `otel-operator-0.24.4`** (uncommitted draft of 2026-10-15, never
reviewed; do not run it). Renovate has since split the line: PR #356 targeted
0.24.6 and PR #351 first targeted 0.25.0, then **re-targeted to 0.25.1 on
2026-10-23**. Landing 0.25.1 makes #356 moot; Renovate closes it once main is
past 0.24.x. The 0.24.4 research that still holds is
reused below: the deadlock mechanism, the RollbackFailed trap, and the
render-gate method. The 0.24.4 plan was a label-only patch. This plan moves two
binaries, so the README's "different job entirely" rule applies and this is a
new file, not a refresh in place. Its `finding_refs` (F-e918a007) and
cross-references are carried over by hand.

## 1) Summary & why held

### 1.1 What changes (upstream)

`opentelemetry-kube-stack-0.25.0` release notes (PR #351 body / GitHub release; 0.25.1 is a chart re-release, see below):

> chore(opentelemetry-kube-stack): bump operator to 0.126.0 and update crds
> (open-telemetry/opentelemetry-helm-charts#2469) … **App Version: 0.161.0**

The release covers 0.24.4–0.24.6 (OpAMP Bridge env, instrumentation defaults,
apacheHttpd render fix). None of them apply here: no OpAMPBridge or
Instrumentation CR is rendered with our values, and none exists live (measured).

### 1.2 Measured render delta (with our live values)

**0.25.1 delta vs 0.25.0 (measured 2026-10-23):** `helm template` of both charts with the HEAD values renders 20 551 lines each; the only differences are the random cert material and the `helm.sh/chart` label (0.25.0 vs 0.25.1); appVersion stays 0.161.0, the OpenTelemetryCollector CR specs are identical (`CR_SPEC_IDENTICAL True`) and the gate counts are `gate_arg=1 operator_img=1 collector_img=1`. All analysis below therefore carries over unchanged. Original delta (0.24.3 vs 0.25.0) — `helm template` of 0.24.3 and 0.25.0 with the `spec.values` from HEAD
(2026-10-17). The renders are 20 510 and 20 551 lines. After stripping the random
cert material and `helm.sh/chart`, the delta is 87 lines:

- **operator Deployment**: image `opentelemetry-operator:0.159.0` → `:0.161.0`,
  `--collector-image=otel/opentelemetry-collector-k8s:0.159.0` → `:0.161.0`, and a new
  `--target-allocator-image=…:0.161.0` (inert: no TargetAllocator). The
  `--feature-gates=-operator.networkpolicy` arg is still rendered (count 1).
- **ClusterRole `…-manager`**: `endpointslices` gains `watch`. Operator 0.161
  requires it ("The operator now requires the `watch` permission on
  `endpointslices`", 0.161.0 notes).
- **CRDs**: additive only. `enableServiceLinks`, `imagePullSecrets`,
  `revisionHistoryLimit`, and the controller-gen annotation.
- **OpenTelemetryCollector CR spec: byte-identical** (python diff of both
  rendered specs, `CR_SPEC_IDENTICAL`). No `image:` is set in the CR, so the
  collector image comes from the operator's `--collector-image`. The live CR has
  `upgradeStrategy: automatic`, so **the collector binary moves 0.159.0 →
  0.161.0 on all three nodes** even though the CR did not change.
- Zero `kind: NetworkPolicy` in either render. As the 0.24.4 plan established,
  that proves nothing: the operator policy is created at runtime by the binary,
  not by the chart.
- Target images are published as multi-arch indexes (registry query
  2026-10-17): collector-k8s 0.161.0 and operator 0.161.0 both have amd64. The
  edot-0.162.0 "per-arch tags only" trap does not apply.

### 1.3 Why it was held, and what actually breaks

1. **Deny rule `*opentelemetry-kube-stack*`** (HELD 2026-10-12, F-c01269d5,
   resolved). Its removal condition is "rendered offline … or the policy disabled
   in values, and the bump goes through an attended window". The policy is
   disabled in values (`featureGatesMap: {operator.networkpolicy: false}`,
   0e976cf5). §3.1 proves offline that the pin reaches the rendered operator
   args. `autonomy_override: human-gated` makes the run attended.
   **Upstream also fixed it:** operator 0.160.0 🛑 *"The `operator.networkpolicy`
   and `operand.networkpolicy` feature gates are moved back to alpha and are
   disabled by default. The generated network policies can block API server
   access on some clusters."* The v0.161.0 source (`pkg/featuregate/featuregate.go`)
   still registers `operator.networkpolicy` at `StageAlpha`. So our `-` pin is
   still a valid gate name. It does not trip the "cannot disable a stable gate"
   startup error, which is the failure that would have mattered on this bump.
2. **The 0.x minor axis.** Two binaries cross two minors each. The breaking
   changes that hit our config, from the 0.160/0.161 release notes checked
   against the live CR config:
   - **FEATURE LOSS, pinned away by this plan.** contrib 0.161.0 🛑
     `processor/k8s_attributes`: *"Promote … `processor.k8sattributes.EmitV1K8sConventions`
     … `processor.k8sattributes.DontEmitV0K8sConventions` (enabled by default)"*. One
     of the V0→V1 renames is `container.image.tag` → `container.image.tags`. The
     chart's kubernetesAttributes preset (`_config.tpl:301`, unchanged in 0.25.1)
     configures `container.image.tag` only. In v0.161.0, `processor.go:75-81` logs
     *"container.image.tag is configured but will NOT be emitted"* and
     `processor.go:417` drops it. `container.image.tags` is emitted only when it is
     configured, and it is not. Net effect: the image tag silently disappears from
     every log and metric document. Measured 2026-10-17: in the last 15 min, **391 219
     `metrics-*` docs carry `resource.attributes.container.image.tag` and 0 carry
     `container.image.tags`**. **Remedy (from the upstream README "Semantic Conventions
     Compatibility", v0.161.0):** disable `DontEmitV0K8sConventions`. The gate has been
     registered since v0.145.0 (metadata.yaml), so the arg is also accepted by the
     0.159 binary. That allows Step A to land first and on its own.
   - contrib 0.160.0 🛑 `k8s_attributes`: `deployment_name_from_replicaset` removed.
     Not in our config (grep of the live CR config: absent). No action.
   - contrib 0.160.0 🛑 `k8s_attributes` internal telemetry switches to the new
     metric format. The daemon collectors' :8888 has no ServiceMonitor, and the
     `otelcol_*` alerts in `otel-collector-alerts.yaml` read edot's
     `elasticsearch/*` exporters. No consumer, no action.
   - contrib 0.161.0 🛑 `kubelet_stats`: `cpuUsageScrapeBased` goes beta. `*.cpu.usage`
     is now a rate of `*.cpu.time`, and it is absent on the first scrape after
     start. The metric names are unchanged and the values become more accurate. No
     repo consumer was found (`grep -rn 'k8s.pod.cpu.usage\|container.cpu.usage'
     kubernetes runbooks docs/sops` returned 0). **Accepted, not pinned.** Pinning it
     would add a second gate that will one day go stable and crash the collector
     (see §6).
   - operator 0.161.0 🛑 `--create-rbac-permissions` removed (not in our args).
     OpAMP Bridge instance IDs change (no bridge). No action.
   - The ottl / kafka / signalfx / adaptive_tail_sampling breaks do not apply: none
     of those components is in our pipelines (receivers: file_log, host_metrics,
     k8s_cluster, k8s_objects, kubelet_stats, otlp, prometheus; processors: batch,
     k8s_attributes, memory_limiter, resource/hostname, resource_detection/env;
     exporters: otlp, debug).

### 1.4 Operand NetworkPolicy — expected to stay, by code path

`otel-operator-daemon-collector-networkpolicy` (ingress-only, ports
8888/4317/4318) exists because the live CR carries `spec.networkPolicy.enabled:
true`. The 0.159 defaulter wrote it while `operand.networkpolicy` was beta.
v0.161.0 `internal/webhook/collector_webhook.go:107` defaults the field only when
it is `nil`. `internal/manifests/collector/networkpolicy.go:16` builds the policy
when the field is `true`. helm-controller writes the CR with `Update` (client-side
3-way merge, managedFields measured). It neither sets the field nor removes it,
because the field is absent from both chart renders. **Expected: the policy is
unchanged.** If it disappears, telemetry is not harmed (it is an allow-list on
ingress only), but the prediction was wrong, so §4.3 records it as a WARN for a
finding. It does not trigger a rollback.

## 2) Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` in zsh on the Mac mini.

```bash
# (a) premises
.venv/bin/python3 runbooks/plan-premises.py otel-operator-0.25.1
# PASS: all 8 premises OK. Any FAIL = stop; do not "fix" a premise to proceed.

# (b) Flux + helm not mid-flight
flux get hr otel-operator -n monitoring
helm -n monitoring history otel-operator --max 3
# PASS: Ready True, newest revision `deployed`. A `pending-*` = stop.

# (c) PR #351 still the one-line bump, CI green
gh pr view 351 --json state,files,statusCheckRollup \
  -q '.state, [.files[].path], [.statusCheckRollup[]|.name+"="+.conclusion]'
gh pr diff 351 | grep '^[-+] '
# PASS: OPEN; files == [kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml];
# all checks SUCCESS; diff exactly `-      version: 0.24.3` / `+      version: 0.25.1`.

# (d) baselines (record in the run log)
kubectl -n monitoring get pods -l app.kubernetes.io/component=opentelemetry-collector \
  -o 'custom-columns=N:.metadata.name,NODE:.spec.nodeName,START:.status.startTime,R:.status.containerStatuses[0].restartCount'
kubectl -n monitoring get pods -l app.kubernetes.io/name=opentelemetry-operator \
  -o 'custom-columns=N:.metadata.name,START:.status.startTime,R:.status.containerStatuses[0].restartCount'
kubectl get netpol -A -o name | wc -l
# 2026-10-17: 3 collector pods (nuc14-01/02/03, R=0); operator pod ...-lggtf R=0;
# 5 NetworkPolicies cluster-wide.
```

## 3) Steps

### 3.1 GATE — offline render proof (deny-rule removal condition). Must print `GATE PASS`.

```bash
REPO=/Users/mu/code/cberg-home-nextgen
G=$(mktemp -d /tmp/otel-0250-gate.XXXXXX)
cd "$G" || exit 1
helm pull opentelemetry-kube-stack --repo https://open-telemetry.github.io/opentelemetry-helm-charts \
  --version 0.25.1 --untar --untardir c || { echo "GATE FAIL: pull"; exit 1; }
python3 -c "
import yaml
d=[x for x in yaml.safe_load_all(open('$REPO/kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml')) if x and x.get('kind')=='HelmRelease'][0]
yaml.safe_dump(d['spec']['values'],open('values.yaml','w'))"
helm template otel-operator c/opentelemetry-kube-stack -n monitoring -f values.yaml --include-crds > r.yaml \
  || { echo "GATE FAIL: render"; exit 1; }
GATE=$(grep -c -- '- --feature-gates=-operator.networkpolicy$' r.yaml)
IMG=$(grep -c 'opentelemetry-operator/opentelemetry-operator:0.161.0"' r.yaml)
COLIMG=$(grep -c -- '--collector-image=otel/opentelemetry-collector-k8s:0.161.0$' r.yaml)
CARGS=$(python3 -c "
import yaml
for d in yaml.safe_load_all(open('r.yaml')):
    if d and d.get('kind')=='OpenTelemetryCollector': print((d['spec'].get('args') or {}).get('feature-gates',''))")
echo "gate_arg=$GATE operator_img=$IMG collector_img=$COLIMG collector_gate='$CARGS' dir=$G"
if [ "$GATE" = 1 ] && [ "$IMG" = 1 ] && [ "$COLIMG" = 1 ] && [ "$CARGS" = "-processor.k8sattributes.DontEmitV0K8sConventions" ]; then echo "GATE PASS"; else echo "GATE FAIL"; fi
cd "$REPO"
```

Run this gate **after Step A is pushed and before Step B**. `collector_gate` reads
HEAD values, so before Step A it prints `''` and `GATE FAIL`. That is the
negative control, and it shows the gate can fail. Measured 2026-10-17 with
HEAD values: `gate_arg=1 operator_img=1 collector_img=1 collector_gate=''`
(FAIL, as expected pre-Step-A). With the Step-A edit applied to a scratch copy,
the rendered CR prints `args= {'feature-gates': '-processor.k8sattributes.DontEmitV0K8sConventions'}`.
**FAILS AS:** `gate_arg=0`: the pin was lost or the subchart renamed
`featureGatesMap`. STOP. `operator_img=0` or `collector_img=0`: the chart moved
under the same version, or someone pinned the images. STOP and re-plan, because
the §1.3 analysis covers 0.161.0 only. `collector_gate` empty or wrong: Step A
did not land. STOP.

### 3.2 Step A — pin the k8s_attributes legacy-semconv gate (lands on the 0.159 collector first)

Dry-tested 2026-10-17 with BSD sed on a scratch copy (`/tmp/otel-0250-plan/hr.s2.yaml`). The
diff was exactly `66a67,69` (the three lines below). A YAML re-parse gave
`collectors.daemon.args = {'feature-gates': '-processor.k8sattributes.DontEmitV0K8sConventions'}`,
`mode: daemonset` was intact, and blank lines were preserved. (yq was rejected
because it strips the file's blank lines.)

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml
grep -c '^        mode: daemonset$' "$F"        # MUST print 1 before editing
sed -i '' -e '/^        mode: daemonset$/a\
        args:\
          # collector 0.161 turns k8s_attributes legacy semconv OFF (beta gate); keep container.image.tag\
          feature-gates: "-processor.k8sattributes.DontEmitV0K8sConventions"
' "$F"
git diff "$F"          # expect +3 lines under collectors.daemon, nothing else
git commit --only "$F" -m "otel-operator: keep container.image.tag across collector 0.161 (k8s_attributes DontEmitV0 gate off)

Prep for opentelemetry-kube-stack 0.25.1 (plan otel-operator-0.25.1 §3.2).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git log -1 --format=%s     # MUST be the subject above (shared worktree)
git show --stat HEAD       # only helmrelease.yaml
git push
STEP_A_SHA=$(git rev-parse HEAD); echo "$STEP_A_SHA"
kubectl -n monitoring rollout status daemonset/otel-operator-daemon-collector --timeout=10m
kubectl get ds otel-operator-daemon-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.template.spec.containers[0].args}'; echo
```
PASS: image still `…collector-k8s:0.159.0`. Args are
`["--config=/conf/collector.yaml","--feature-gates=-processor.k8sattributes.DontEmitV0K8sConventions"]`
(the order may differ). All 3 pods are Ready with R=0.
FAILS AS: pods CrashLoop with `no such feature gate`. That would contradict
metadata.yaml at v0.159.0, which registers the gate. Revert `$STEP_A_SHA` (§5.1)
and STOP. Args unchanged after 10 min: the HR has not reconciled. Check
`flux get hr`. Do not proceed to Step B.

### 3.3 Step B — run the §3.1 gate, then merge the Renovate PR (attended, operator GO recorded)

```bash
cd /Users/mu/code/cberg-home-nextgen
# §3.1 must print GATE PASS now
gh pr update-branch 351 2>/dev/null || true     # rebase onto Step A if GitHub reports it behind
gh pr merge 351 --squash --delete-branch
git pull --ff-only
git log -1 --format='%h %s'          # must be the #351 squash
grep -n 'version: 0.25.1' kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml
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
ROLLOUT_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "ROLLOUT_TS=$ROLLOUT_TS"
flux get hr otel-operator -n monitoring
```
Expect `Ready True`, `Helm upgrade succeeded … 0.25.1`. While §3.4 runs, run the
§4.3 netpol check once **immediately** (do not wait for the HR timeout). An
`opentelemetry-operator` policy appearing means go to §5.3 now.

## 4) Verification

### Floor (shape — necessary, not sufficient)

```bash
kubectl get hr otel-operator -n monitoring \
  -o jsonpath='{.status.history[0].chartVersion}/{.status.history[0].status} ready={.status.conditions[?(@.type=="Ready")].status}'; echo
kubectl get opentelemetrycollector otel-operator-daemon -n monitoring \
  -o jsonpath='ver={.status.version} scale={.status.scale.statusReplicas}'; echo
```
PASS: `0.25.1/deployed ready=True`; `ver=0.161.0 scale=3/3`.

### 4.1 CONTENTS ASSERTION — both binaries are the target, gate still off in the operator

```
CONTENTS ASSERTION: the RUNNING operator pod is image 0.161.0 with
  --feature-gates=-operator.networkpolicy, and every RUNNING collector pod is
  collector-k8s:0.161.0 — measured on live pods (not the template; see
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
PASS: one operator pod with `…opentelemetry-operator:0.161.0`, ready `true`,
R=0. The grep prints `"--feature-gates=-operator.networkpolicy"`. Three collector
pods on nuc14-01/02/03, each `…collector-k8s:0.161.0`, R=0. `avail= ['1']`.
FAILS AS: any pod still on 0.159.0 (the roll stalled, so the generation is old).
Operator R>0 or not ready: go to 4.3, then §5.3. The grep prints nothing: the
gate was lost. `avail= EMPTY`: the instrument is blind, and that counts as a
FAIL (verified non-empty on 2026-10-15).

### 4.2 CONTENTS ASSERTION — container.image.tag is still emitted (the §1.3 feature-loss guard)

```
CONTENTS ASSERTION: after the 0.161 roll, metrics documents still carry
  resource.attributes.container.image.tag (non-zero floor), AND no collector
  logged the upstream "will NOT be emitted" warning — measured in ES and in the
  collector's own startup log (code path processor.go:75-89 @ contrib v0.161.0),
  compared to the 2026-10-17 baseline (391 219 docs / 15 min, 0 `.tags`).
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
PASS: every pod prints `notemitted=0` and `renamed>=1` (expected `renamed=3`: the
`k8s_attributes` processor is instantiated once in each of the 3 pipelines and logs
the warning once per instance; corrected 2026-10-23 per delta review). The "renamed"
warning is the one the code logs when the legacy gate is OFF and the tag is
configured. Its presence proves the code path ran and our gate took effect, so
`renamed=0` is not a pass.
`container.image.tag` count **> 0**. `container.image.tags` count is 0, which is
expected because the plural is not configured.
FAILS AS: `notemitted=1`: the gate arg did not reach the binary, and the tag is
being dropped. That is feature loss, so go to §5.1. `renamed=0` and
`notemitted=0`: the version is not 0.161 or the warning text changed, so the gate
is inconclusive. Treat that as FAIL and check §4.1. `renamed=3` is NOT a failure. Tag count `0`: feature loss,
go to §5.1. A curl timeout / empty output: the instrument is blind, so re-run with
a narrower window. This `metrics-*` exists-count returned in under 2 min on
2026-10-17, while the same count on `logs-*` timed out. That is why the gate
reads metrics.

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
PASS: count `5`; the list is exactly `otel-operator-daemon-collector-networkpolicy`; `np=[true]`.
FAILS AS: an `opentelemetry-operator` entry. The deadlock policy exists, so go to
§5.3 immediately. The collector policy missing (count 4, `np=[]`) is a **WARN,
not a rollback**: §1.4's prediction was wrong. Telemetry is unaffected. File a
finding.

### 4.4 CONTENTS ASSERTION — telemetry flows from every node (load-bearing)

Run **≥15 min after `$ROLLOUT_TS`**.

```
CONTENTS ASSERTION: pod-log documents from ALL THREE nodes land in Elasticsearch
  in a window that starts after the roll — measured in ES (not at the exporter;
  _bulk returns 200 even when items are rejected), compared to the §2(d) node set.
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
PASS: three buckets, `k8s-nuc14-01/02/03`, each **> 0**. The 0.24.4 plan's dry
run on 2026-10-15 over 15 min gave 6 784 / 6 254 / 7 010. `ready= ['3']`. No
`OtelDaemonCollectorDown`, and nothing new compared with the pre-window alert list.
This is a **presence check, not a volume check**: a node missing or at 0 is the failure.
FAILS AS: a missing node bucket means a collector is Ready but shipping nothing,
and no alert catches that. Total `[]` or `ready= EMPTY` means the instrument is
blind. Negative control (2026-10-15): the same aggregation on a non-existent
field returns `[]`.

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
This is safe while the operator is Ready. The operator goes back to 0.159.0 and
sets `--collector-image` back to 0.159.0. `upgradeStrategy: automatic` never
*downgrades* a CR's recorded version, but the DaemonSet image follows the
operator's `--collector-image`, so the collectors return to 0.159.0. Confirm that
on the pods in §5.2. The CRDs revert to the 0.24.3 schema. The fields added in
0.25.1 are unused and would be pruned on read, and nothing is forward-only. The
Step A arg can **stay**: the gate exists in 0.159, where it is a no-op. Revert
`$STEP_A_SHA` only if Step A itself is the fault (§3.2).

### 5.2 Confirm the cluster is back

```bash
kubectl get hr otel-operator -n monitoring -o jsonpath='{.status.history[0].chartVersion}/{.status.history[0].status}'; echo   # 0.24.3/deployed
kubectl -n monitoring get pods -l app.kubernetes.io/component=opentelemetry-collector \
  -o 'custom-columns=N:.metadata.name,IMG:.status.containerStatuses[0].image'                                                 # all :0.159.0
kubectl -n monitoring get ds otel-operator-daemon-collector -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled}'; echo  # 3/3
```
If the collector pods stay on 0.161.0 after the operator is back on 0.159.0, the
operator kept the CR's recorded version. This is **not** an emergency: 0.161 plus
the Step A arg is the state §4 already verified. Record it, and handle the
re-pin in a follow-up plan. Then re-run §4.3 and §4.4 with a fresh `ROLLOUT_TS`.

### 5.3 The RollbackFailed trap — if the operator is NOT Ready

Symptom: the operator pod is in CrashLoopBackOff or not Ready, the HR shows
`UpgradeFailed` then `RollbackFailed`, and helm history shows `failed` revisions.
A `git revert` alone will NOT converge, because every upgrade and rollback waits
on a CR that only a Ready operator can settle.

1. **Diagnose (read-only):**
   ```bash
   kubectl -n monitoring get pods -l app.kubernetes.io/name=opentelemetry-operator
   kubectl -n monitoring logs deploy/otel-operator-opentelemetry-operator --tail=80 | grep -iE 'networkpolicy|i/o timeout|dial tcp|feature gate|forbidden|endpointslices'
   kubectl get netpol -n monitoring -o wide
   helm -n monitoring history otel-operator --max 5
   ```
   `forbidden … endpointslices … watch` means the ClusterRole did not get `watch`.
   It is a different cause from the netpol, but the recovery path below is the same.
2. **Unblock the operator (BREAK-GLASS, direct mutation, needs operator
   approval recorded in the run log).** Only if `kubectl get netpol -n monitoring`
   lists `opentelemetry-operator`:
   `kubectl delete netpol opentelemetry-operator -n monitoring`. Do NOT delete the
   operator Deployment. Wait with
   `kubectl -n monitoring rollout status deploy/otel-operator-opentelemetry-operator --timeout=5m`.
3. **Revert in git** (§5.1) if you have not already pushed the revert.
4. **Clear Flux's exhausted retry counter and re-drive** (operator-approved; the SOP's wedge
   path, `docs/sops/application-update.md` §11):
   ```bash
   flux reconcile hr otel-operator -n monitoring --reset
   flux reconcile hr otel-operator -n monitoring --force
   ```
   If helm is left `pending-upgrade`/`pending-rollback`, record the last
   `deployed` 0.24.3 revision from `helm history` **before Step B** (§2b), roll
   back to it with `helm rollback otel-operator <that-rev> -n monitoring --wait=false`,
   then run `flux reconcile hr otel-operator -n monitoring --force`. NEVER use a
   revision older than the 0e976cf5 roll-forward, because those predate the gate pin.
5. Confirm with §5.2, then file a finding.

## 6) Interference notes

- **Attended slot only** (`autonomy_override: human-gated`): sat-attended or
  sun-attended. No reboot is needed, and the plan does not need to be exclusive.
- **edot-collector-0.163.2: separate slots, either
  order.** Both plans gate on ES ingestion through the same edot hop. Recommended
  order: run **this plan first**. Its §4.4 then validates the producer side on the
  current edot, and the edot plan's gate afterwards sees an already-0.161 daemon
  fleet. The reciprocal `conflicts_with: [otel-operator-0.25.1]` is on the edot plan.
- **Log gap:** each node loses ~10–30 s of pod logs per collector roll, and this
  plan rolls twice (Step A, Step B). Other same-window plans whose gates read ES
  log continuity must read outside those minutes.
- **Future hazard of the Step A pin:** when contrib promotes
  `processor.k8sattributes.DontEmitV0K8sConventions` to **stable**, `-gate` becomes
  a startup error. The collector would then crash-loop on that bump, the same
  failure shape as the operator gate. Before that happens, the proper fix is to
  move off the legacy name: configure `container.image.tags` (via
  `collectors.daemon.config` or a preset override), migrate any Kibana consumer
  of `container.image.tag`, then drop the pin. This needs a follow-up plan or
  finding, and is out of scope here.
- **Deny rule stays.** Narrowing `*opentelemetry-kube-stack*` (for example to
  hold only bumps that move the operator subchart or appVersion) is a separate
  operator decision, made after this lands.
- **AR-124 / F-369edfe8:** the collector image change (collector-k8s 0.159.0 -> 0.161.0)
  will make the sweep re-score that accepted row on its next scan. Let the sweep
  re-sweep it (run a sweep after the window); do not close or renew it by hand.
- **Prometheus is read by §4:** no `kube-prometheus-stack` plan is open today
  (2026-10-23). If one is added for the same night, serialize it in a separate slot.
