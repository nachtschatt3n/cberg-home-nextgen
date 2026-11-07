---
plan_id: otel-operator-0.27.0
component: otel-operator               # HelmRelease monitoring/otel-operator; CHART is the umbrella
                                       # opentelemetry-kube-stack (subcharts otel-crds, prometheus-crds,
                                       # opentelemetry-operator)
pr: 472                                # "feat(helm): update opentelemetry-kube-stack ( 0.26.1 → 0.27.0 )",
                                       # branch renovate/opentelemetry-kube-stack-0.x. OPEN, MERGEABLE, diff is
                                       # exactly `-version: 0.26.1` / `+version: 0.27.0` in helmrelease.yaml; all
                                       # 4 checks SUCCESS incl. Flate Render Gate (measured 2026-11-06).
kind: chart
current: "0.26.1"                      # MEASURED 2026-11-06: HR spec 0.26.1, history[0] 0.26.1/deployed (rev 72,
                                       # 2026-11-02 23:48, landed by plan otel-operator-0.26.1 via 5aa609d5)
target: "0.27.0"                       # newest in the chart index (published 2026-11-02 21:21Z); also present as
                                       # the OCI chart on ghcr (helm show chart, 2026-11-06)
update_type: minor
risk: low                              # The hold is a 0.x-minor false positive. 0.27.0 is ONE upstream PR (#2510,
                                       # optional collector readinessProbe/startupProbe passthrough, default {}).
                                       # appVersion 0.162.0 and operator subchart 0.128.0 are UNCHANGED, CRDs are
                                       # byte-identical, and the render with our live values differs from 0.26.1
                                       # ONLY in two `helm.sh/chart` label lines plus regenerated webhook cert
                                       # material (§1.2). No binary moves. Side effect: the 3 collector pods roll
                                       # once (the CR label propagates into the DaemonSet pod template).
est_duration_min: 40                   # 8 pre-checks + 3 merge + <=5 reconcile + ~2 collector roll + 15 SETTLE
                                       # before the ES gate + 7 verification. Fits a nightly (90 - 20 Step 0 = 70).
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:                           # every object verified to EXIST live 2026-11-06
    - helmrelease/otel-operator                         # chart version only (via PR #472)
    - opentelemetrycollector/otel-operator-daemon       # metadata.labels helm.sh/chart 0.26.1 -> 0.27.0; spec
                                                        # byte-identical (no probe keys rendered)
    - daemonset/otel-operator-daemon-collector          # ROLLS once (pod-template label), maxUnavailable 1,
                                                        # image stays collector-k8s:0.162.0
    - secret/otel-operator-opentelemetry-operator-controller-manager-service-cert  # pre-upgrade HOOK,
                                                        # deleted + regenerated on every upgrade (autoGenerateCert.recreate)
    - mutatingwebhookconfiguration/otel-operator-opentelemetry-operator-mutation      # caBundle (new CA)
    - validatingwebhookconfiguration/otel-operator-opentelemetry-operator-validation  # caBundle (new CA)
    - "deployment/otel-operator-opentelemetry-operator — NOT changed (render byte-identical; its helm.sh/chart
       label is the SUBCHART's opentelemetry-operator-0.128.0). Does NOT roll; asserted in §4.1"
    - "crd/{opentelemetrycollectors,targetallocators,instrumentations,opampbridges}.opentelemetry.io —
       CreateReplace re-applies them; content byte-identical 0.26.1 vs 0.27.0"
    - "networkpolicy/otel-operator-daemon-collector-networkpolicy — NOT edited; asserted unchanged in §4.3"
  shared:
    - monitoring                       # the cluster's ONLY pod-log / host-metric / kubelet-stats / k8s-event
                                       # collection path into edot-collector -> Elasticsearch. Each node loses
                                       # ~10-30 s of pod logs during its collector roll (filelog start_at end).
depends_on: []
conflicts_with:                        # ONLY this field is honoured by window-scheduler.py. Built from every open
                                       # plan's frontmatter on 2026-11-06.
  # 2026-11-06: removed edot-collector-0.164.0 - plan executed in the NOW run 2026-11-06 and retired (dead ref in maintenance-plan.py --validate).
                                       # edot-collector.monitoring.svc:4317 and §4.4 proves THIS plan by docs landing
                                       # in ES through edot; a same-night edot roll makes both ES gates unattributable.
  - helm-drift-detection               # writes spec.driftDetection into this same HelmRelease (sat-attended:2026-11-28)
  - flux-oci-chart-sources             # re-sources this same HelmRelease (spec.chart -> chartRef) in its stage 5
                                       # (sun-attended:2026-12-13); its census pins otel at 0.26.1 (see §6)
  - talos-linux-1.14.5                 # sun-attended:2026-11-22; a node roll re-creates every collector pod, so the
                                       # §4.4 per-node gate could not attribute a missing node
  - grafana-14.1.0                     # vetted, unwindowed; soft attribution hygiene (both gate on ns monitoring);
                                       # it carried the same reciprocal with otel-operator-0.26.1
  - redis-fleet-8.10.3                 # sun-attended:2026-11-29; carried the reciprocal with 0.26.1 ("§4 reads
                                       # Prometheus too") — kept so neither gate set is read mid-roll of the other
  # kube-prometheus-stack: no plan file exists (2026-11-06). Renovate PR #428 (92.11.1 -> 92.21.1) is HELD by the
  # time-boxed `*kube-prometheus-stack*` deny rule in auto-update-policy.yaml (revisit by 2026-11-30), so it cannot
  # land at Step 0 under this plan. If a kube-prometheus-stack plan is written, it MUST be added here (§4 reads
  # Prometheus). §2(e) still checks the instrument.
exclusive: false
security_ref: null                     # Not security-driven; no image moves, so no CVE posture change.
capability_change: false               # Same operator binary, same collector binary, same CR spec, same pipelines.
                                       # The new chart keys (collectors.*.readinessProbe/startupProbe) are not set
                                       # in our values and render nothing (`with` on an empty map). Version bump of a
                                       # label, nothing more.
rollback_class: git-revert             # Nothing is forward-only: no CRD change, no data, no migration; revert
                                       # re-labels the CR and rolls the collectors once more.
finding_refs: [F-60ebcdb5]             # VERIFIED 2026-11-06 via `policy-cli.py finding list --grep` for
                                       # otel-operator / opentelemetry-kube-stack / 0.27.0: F-60ebcdb5 (version,
                                       # "otel-operator: chart 0.26.1 → 0.27.0 (minor)") is the only match. The
                                       # 0.26.1 plan's F-61e4d5b6 and F-3b519d4a are `resolved`; PR #356 is CLOSED.
review: ready-for-go@2026-11-06   # sweep 471de4f9 plan-reviewer: 0 blocking (render diff re-proven: label-only); nonblocking: add mutating-webhook failurePolicy premise, pin .venv/bin/python3 in §2(d), take MERGE_SHA from `gh pr view 472`, declare python-fleet-3.15.2-alpine conflict
status: vetted   # AUTO-NIGHT; reviewer recommends nightly:2026-11-11+ (not 11-09 gha-fleet, 11-10 edot, 11-22 talos)
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-06"
premises:
  - id: live-chart-is-0.26.1
    why: "`current:` claims 0.26.1. If the HR moved, the render diff in §1.2 and the rollback target in §5 are stale."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "0.26.1"
  - id: otel-hr-ready
    why: "Never stack a chart bump on a failing release. With remediation strategy rollback, a pre-existing failure re-enters the 2026-10-12 RollbackFailed trap."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: last-release-deployed-0.26.1
    why: "The §5 rollback depends on helm's newest revision being a deployed 0.26.1."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.status.history[0].chartVersion}/{.status.history[0].status}'
    expect_exact: "0.26.1/deployed"
  - id: gate-pin-in-values
    why: "The deny rule's hazard (operator default-deny NetworkPolicy, F-c01269d5) stays pinned off. If the pin vanished, this plan is no longer a label-only bump."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.spec.values.opentelemetry-operator.manager.featureGatesMap}'
    expect_contains: '"operator.networkpolicy":false'
  - id: operator-image-0.162.0
    why: "§1.2 proves the operator Deployment render is byte-identical at 0.162.0. A different live image means the baseline moved and the no-roll claim is unverified."
    run: kubectl get deploy otel-operator-opentelemetry-operator -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/open-telemetry/opentelemetry-operator/opentelemetry-operator:0.162.0"
  - id: collector-image-0.162.0
    why: "The collector binary must stay 0.162.0 across this bump (§4.1). The k8s_attributes gate pin is valid at 0.162.0 (beta stage), re-verified for the 0.26.1 plan."
    run: kubectl get ds otel-operator-daemon-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "otel/opentelemetry-collector-k8s:0.162.0"
  - id: collector-gate-arg-live
    why: "§4.2 asserts container.image.tag survives the roll; it can only hold if the DontEmitV0K8sConventions pin is already on the running DaemonSet."
    run: kubectl get ds otel-operator-daemon-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].args}'
    expect_contains: "-processor.k8sattributes.DontEmitV0K8sConventions"
  - id: collector-cr-label-0.26.1
    why: "The CR's helm.sh/chart label is the ONLY change this bump makes to a workload input; it is what rolls the collectors. If it already reads something else, the roll prediction is wrong."
    run: kubectl get opentelemetrycollector otel-operator-daemon -n monitoring -o jsonpath='{.metadata.labels.helm\.sh/chart}'
    expect_exact: "opentelemetry-kube-stack-0.26.1"
  - id: webhooks-fail-open
    why: "Load-bearing for the cert race (§1.3): the pre-upgrade hook regenerates the webhook cert while the operator pod does NOT restart. With failurePolicy Ignore the CR label patch cannot fail on a CA mismatch. If any webhook became Fail, re-assess."
    run: kubectl get validatingwebhookconfiguration otel-operator-opentelemetry-operator-validation -o jsonpath='{.webhooks[*].failurePolicy}'
    expect_exact: "Ignore Ignore Ignore Ignore"
  - id: monitoring-netpols-exactly-collector
    why: "Baseline for §4.3. An `opentelemetry-operator` entry would mean the deadlock policy is already live."
    run: kubectl get networkpolicy -n monitoring -o jsonpath='{.items[*].metadata.name}'
    expect_exact: "otel-operator-daemon-collector-networkpolicy"
---

# otel-operator — opentelemetry-kube-stack 0.26.1 → 0.27.0

**Held as a false positive, in effect.** coverage/auto-update held it as a 0.x
release-line move (the minor is the breaking axis at major 0), and the
`*opentelemetry-kube-stack*` deny rule (F-c01269d5) holds every bump of this chart.
Measured here: **no binary, CRD, or operator object changes.** The only workload
effect is one rolling restart of the three daemon-collector pods, caused by a
`helm.sh/chart` label. The closest precedent is `9a35168fc` (chart 0.20.9 → 0.21.0,
"label-only for our values", 2026-09-17). It ran in an unattended nightly and had
exactly this shape.

## 1) Summary & why held

### 1.1 What changes upstream

Renovate's PR body mislinks the release again: it points at `opentelemetry-demo-0.27.0`.
The real release is `opentelemetry-kube-stack-0.27.0` (GitHub release, published
2026-11-02T21:21Z). It contains one change:

> feat(opentelemetry-kube-stack): add readinessProbe and startupProbe options for collectors — open-telemetry/opentelemetry-helm-charts#2510

I checked this against the published tarballs (`helm pull … --version 0.26.1 / 0.27.0`,
scratch dir `/tmp/otel-0270-plan`, 2026-11-06). `diff -r` of the two chart trees
shows only these differences:
- `Chart.yaml` `version:`
- README rows
- `values.schema.json`: two `$ref: Probe` keys
- `values.yaml`: `readinessProbe: {}` and `startupProbe: {}` under `defaultCRConfig`
- `templates/collector.yaml`: two `{{- with $collector.readinessProbe }}` /
  `{{- with $collector.startupProbe }}` blocks

`appVersion` stays **0.162.0** and the `opentelemetry-operator` subchart stays **0.128.0**.
The `charts/` subtrees (operator, otel-crds, prometheus-crds, kube-state-metrics,
node-exporter) are identical.

### 1.2 Measured render delta (with our live values)

`helm template otel-operator <chart> -n monitoring -f values.yaml --include-crds` for
both versions. `values.yaml` was extracted from the HEAD HelmRelease `spec.values`,
2026-11-06. Both renders are 21 034 lines. `diff` shows 10 hunks:

- 8 hunks are regenerated cert material (`caBundle` ×7, `tls.crt/tls.key/ca.crt` in the
  webhook cert Secret). These differ between ANY two renders, including two renders of
  the same version (`genCA` is random).
- `OpenTelemetryCollector/otel-operator-daemon` `metadata.labels.helm.sh/chart`:
  `opentelemetry-kube-stack-0.26.1` → `-0.27.0`.
- The pre-delete hook Job's `-l helm.sh/chart=…` selector, with the same change. This is a
  hook that runs only on uninstall.

After filtering cert lines and `helm.sh/chart`, the diff has **0 lines**. So:
- The **CR spec is byte-identical.** No `readinessProbe`/`startupProbe` key is rendered,
  because the defaults are `{}` and `with` skips them.
- The **operator Deployment is byte-identical.** Its `helm.sh/chart` label is the
  subchart's `opentelemetry-operator-0.128.0`, and its pod template has no checksum
  annotation (live: only `kubectl.kubernetes.io/default-container`). **The operator does
  not roll.** The operator NetworkPolicy hazard behind the deny rule cannot newly arise,
  because the operator binary, args and pod are unchanged. The
  `--feature-gates=-operator.networkpolicy` arg was shown rendered in the 0.26.1 plan,
  and it is unchanged here.
- **CRDs are byte-identical.** `CreateReplace` re-applies the same content.

**Why the collectors still roll.** The live DaemonSet pod template carries
`helm.sh/chart: opentelemetry-kube-stack-0.26.1` (measured 2026-11-06). The operator
copies the CR's labels into the pod template, so the label change rewrites the
template. Update strategy (live): `RollingUpdate maxSurge 0 maxUnavailable 1`, which
rolls one node at a time. The 0.21.0 precedent commit records the same effect: "the 3
collector DaemonSet pods roll one node at a time (CR label -> pod template) … No
operator rollout."

### 1.3 Why it was held, and what can actually go wrong

1. **0.x minor axis.** This is a false positive for this release: the change is a
   values passthrough we do not use (§1.1).
2. **Deny rule `*opentelemetry-kube-stack*`.** The rule's hazard is the operator's
   default-deny NetworkPolicy (operator 0.24.x-era chart), and it is pinned off in
   values. This bump does not touch the operator. See §6 for the rule's wording.
3. **Webhook cert race (the only real mechanism).** The webhook cert Secret is a
   `pre-install,pre-upgrade` hook (`before-hook-creation`), and it is regenerated on
   every upgrade. The operator pod does not restart here. It keeps serving the old cert
   until kubelet syncs the replaced Secret into its volume, and then controller-runtime's
   cert watcher reloads it. During that gap, the API server (now holding the new
   `caBundle`) cannot verify the webhook. **This cannot fail the upgrade.** All 7 webhooks
   are `failurePolicy: Ignore` (measured, and premise `webhooks-fail-open`), so the CR
   label PATCH is admitted without the webhook. Live precedent: helm rev 71 (2026-11-02
   23:44, the 0.26.1 plan's Step A args change at chart 0.24.3) was exactly this case:
   cert regenerated, operator not restarted, CR patched. It reached
   `Upgrade complete` on the first attempt, with no `failed` revision in between
   (`helm history`: 70 superseded → 71 superseded → 72 deployed). §4.1(b) proves that the
   served cert verifies against the new `caBundle` after the settle.
4. **Collector roll = brief log gap** on each node (~10–30 s, no filelog storage
   extension). This is expected, and it is the reason this is a planned change rather than a no-op.

The edot-collector compatibility question from the brief: the daemon collectors stay on
0.162.0 and speak plain OTLP/gRPC to `edot-collector` (live
`otel/opentelemetry-collector-contrib:0.161.0`; plan edot-collector-0.164.0 targets
0.164.0). Nothing in that path changes, and OTLP needs no version coordination in either
order.

The `processor.k8sattributes.DontEmitV0K8sConventions` pin (`-gate`) must stay
non-stable at the collector tag. The collector tag does not change (0.162.0, beta), so
no re-check is needed for this plan. The next plan that moves the collector image must
re-check it (see §6).

## 2) Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` in zsh on the Mac mini.

```bash
# (a) premises
.venv/bin/python3 runbooks/plan-premises.py otel-operator-0.27.0
# PASS: all 10 premises OK. Any FAIL = stop; do not "fix" a premise to proceed.

# (b) Flux + helm not mid-flight; RECORD the deployed 0.26.1 revision for §5.3
flux get hr otel-operator -n monitoring
helm -n monitoring history otel-operator --max 3
# PASS: Ready True, newest revision `deployed` 0.26.1 (rev 72 on 2026-11-06). A `pending-*` = stop.

# (c) PR #472 still the one-line bump to EXACTLY 0.27.0, CI green
gh pr view 472 --json state,files,statusCheckRollup \
  -q '.state, [.files[].path], [.statusCheckRollup[]|.name+"="+.conclusion]'
gh pr diff 472 | grep '^[-+] '
# PASS: OPEN; files == [kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml]; all checks SUCCESS;
# diff exactly `-      version: 0.26.1` / `+      version: 0.27.0` (measured 2026-11-06).
# FAILS AS: any other `+ version:` = Renovate re-targeted (it did this to #351 once) -> STOP and re-plan;
# §1.2 covers 0.27.0 only.

# (d) re-prove the render delta at execution time (the chart could be republished under the same version)
(
G=$(mktemp -d /tmp/otel-0270-gate.XXXXXX); cd "$G" || exit 1
REPO=/Users/mu/code/cberg-home-nextgen
for v in 0.26.1 0.27.0; do
  helm pull opentelemetry-kube-stack --repo https://open-telemetry.github.io/opentelemetry-helm-charts \
    --version $v --untar --untardir c$v || { echo "GATE FAIL: pull $v"; exit 1; }
done
python3 -c "
import yaml
d=[x for x in yaml.safe_load_all(open('$REPO/kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml')) if x and x.get('kind')=='HelmRelease'][0]
yaml.safe_dump(d['spec']['values'],open('values.yaml','w'))"
for v in 0.26.1 0.27.0; do
  helm template otel-operator c$v/opentelemetry-kube-stack -n monitoring -f values.yaml --include-crds > r$v.yaml \
    || { echo "GATE FAIL: render $v"; exit 1; }
done
N=$(diff r0.26.1.yaml r0.27.0.yaml | grep '^[<>]' | grep -vE 'tls\.(crt|key)|ca\.crt|caBundle|helm.sh/chart' | wc -l | tr -d ' ')
L=$(diff r0.26.1.yaml r0.27.0.yaml | grep -c '^>.*helm.sh/chart')
echo "non_label_lines=$N chart_label_lines=$L dir=$G"
if [ "$N" = 0 ] && [ "$L" = 2 ]; then echo "GATE PASS"; else echo "GATE FAIL"; fi
)
# PASS: `non_label_lines=0 chart_label_lines=2` + `GATE PASS` (measured 2026-11-06 exactly so).
# FAILS AS: non_label_lines>0 = the chart or our values moved (e.g. someone set collectors.daemon.startupProbe,
# or the 0.27.0 tarball was republished) -> STOP and re-plan. Negative control: rendering 0.26.1 against itself
# gives chart_label_lines=0 -> GATE FAIL, so the gate can fail.

# (e) baselines + the Prometheus instrument §4 reads (RECORD in the run log)
kubectl -n monitoring get pods -l app.kubernetes.io/component=opentelemetry-collector \
  -o 'custom-columns=N:.metadata.name,NODE:.spec.nodeName,START:.status.startTime,R:.status.containerStatuses[0].restartCount'
kubectl -n monitoring get pods -l app.kubernetes.io/name=opentelemetry-operator \
  -o 'custom-columns=N:.metadata.name,START:.status.startTime,R:.status.containerStatuses[0].restartCount'
kubectl get netpol -A -o name | wc -l
kubectl get hr kube-prometheus-stack -n monitoring
kubectl get pod prometheus-kube-prometheus-stack-0 -n monitoring
kubectl get --raw "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/alerts" \
  | grep -o '"alertname":"[^"]*"' | grep -vE 'Watchdog|InfoInhibitor' | sort | uniq -c
# 2026-11-06: collectors np8w8 (nuc14-02) / twws4 (nuc14-01) / wpzjx (nuc14-03), all started 2026-11-02T23:49Z,
# R=0; operator pod ...-66b76bbb9f-2h72p started 2026-11-02T23:48:42Z, R=0; 5 NetworkPolicies cluster-wide.
# PASS: kube-prometheus-stack HR Ready True and pod 2/2 Running, not freshly restarted (PR #428 is deny-held;
# if it nonetheless moved, wait for Prometheus to settle). The alert list returns without error (empty is legit).
```

## 3) Steps

### 3.1 Merge the Renovate PR (only after §2(c) and §2(d) PASS)

```bash
cd /Users/mu/code/cberg-home-nextgen
gh pr update-branch 472 2>/dev/null || true     # rebase if GitHub reports it behind
gh pr diff 472 | grep '^[-+] '                   # re-check AFTER update-branch: still exactly 0.26.1 -> 0.27.0
gh pr merge 472 --squash --delete-branch
git pull --ff-only
git log -1 --format='%h %s'                      # must be the #472 squash
grep -n 'version: 0.27.0' kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml
grep -c 'DontEmitV0K8sConventions' kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml   # 1
MERGE_SHA=$(git rev-parse HEAD); echo "$MERGE_SHA"
```
Do not run a manual `flux reconcile`. The push webhook drives the source. Only if
`flux get hr otel-operator -n monitoring` still shows 0.26.1 after 10 min, run
`flux reconcile hr otel-operator -n monitoring --with-source`.

### 3.2 Watch the rollout

```bash
kubectl -n monitoring rollout status daemonset/otel-operator-daemon-collector --timeout=10m
flux get hr otel-operator -n monitoring
kubectl -n monitoring get pods -l helm.sh/chart=opentelemetry-kube-stack-0.27.0 -o name | wc -l    # 3
ROLLOUT_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "ROLLOUT_TS=$ROLLOUT_TS"
```
Expect HR `Ready True` with `Helm upgrade succeeded … 0.27.0`. `rollout status` can
return before the operator has rewritten the DaemonSet, so trust the label count. If it
prints fewer than 3, wait, and re-stamp `ROLLOUT_TS` once it prints 3.

### 3.3 After §4 passes — bookkeeping

F-60ebcdb5 (section `version`, sweep-owned) clears on the next sweep's version scan.
Do not close it by hand.

## 4) Verification

### Floor (shape — necessary, not sufficient)

```bash
kubectl get hr otel-operator -n monitoring \
  -o jsonpath='{.status.history[0].chartVersion}/{.status.history[0].status} ready={.status.conditions[?(@.type=="Ready")].status}'; echo
kubectl get opentelemetrycollector otel-operator-daemon -n monitoring \
  -o jsonpath='ver={.status.version} scale={.status.scale.statusReplicas} label={.metadata.labels.helm\.sh/chart}'; echo
```
PASS: `0.27.0/deployed ready=True` and `ver=0.162.0 scale=3/3 label=opentelemetry-kube-stack-0.27.0`.
FAILS AS: `history[0]` is `failed`, or there is a second new revision, which means a retry
happened. Read `kubectl describe hr` events before going on. A `ver` other than 0.162.0
means the collector binary moved, which contradicts §1.2. That is a FAIL, go to §5.1.

### 4.1 CONTENTS ASSERTION — nothing but the label moved; webhook serves the new CA

```
CONTENTS ASSERTION: (a) the operator pod is the SAME pod as the §2(e) baseline (name + startTime,
  R=0, image 0.162.0, -operator.networkpolicy still in args), and all 3 RUNNING collector pods are
  collector-k8s:0.162.0, labelled 0.27.0, started after the merge, R=0;
  (b) the certificate the operator webhook SERVES verifies against the caBundle now in BOTH webhook
  configurations (the §1.3.3 cert race has converged).
CONTROL: metric kube_deployment_status_replicas_available — otel-operator-opentelemetry-operator must be 1
CONTROL: metric kube_daemonset_status_number_ready — otel-operator-daemon-collector must be 3
```
```bash
# (a)
kubectl -n monitoring get pods -l app.kubernetes.io/name=opentelemetry-operator \
  -o 'custom-columns=N:.metadata.name,START:.status.startTime,IMG:.status.containerStatuses[0].image,R:.status.containerStatuses[0].restartCount'
kubectl get pod -n monitoring -l app.kubernetes.io/name=opentelemetry-operator \
  -o 'jsonpath={.items[0].spec.containers[0].args}' | tr ',' '\n' | grep -i feature-gates
kubectl -n monitoring get pods -l app.kubernetes.io/component=opentelemetry-collector \
  -o 'custom-columns=N:.metadata.name,NODE:.spec.nodeName,START:.status.startTime,IMG:.status.containerStatuses[0].image,R:.status.containerStatuses[0].restartCount,CHART:.metadata.labels.helm\.sh/chart'
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
for q in 'kube_deployment_status_replicas_available%7Bnamespace%3D%22monitoring%22%2Cdeployment%3D%22otel-operator-opentelemetry-operator%22%7D' \
         'kube_daemonset_status_number_ready%7Bnamespace%3D%22monitoring%22%2Cdaemonset%3D%22otel-operator-daemon-collector%22%7D'; do
  kubectl get --raw "${P}?query=${q}" \
    | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print([x['value'][1] for x in r] or 'EMPTY')"
done

# (b) run >= 3 min after the HR went Ready (kubelet secret sync + cert-watcher reload)
(
D=$(mktemp -d /tmp/otel-0270-cert.XXXXXX); cd "$D" || exit 1
kubectl port-forward -n monitoring svc/otel-operator-opentelemetry-operator-webhook 19443:443 >/dev/null 2>&1 & PF=$!
sleep 4
kubectl get mutatingwebhookconfiguration otel-operator-opentelemetry-operator-mutation \
  -o jsonpath='{.webhooks[0].clientConfig.caBundle}' | base64 -d > ca-m.pem
kubectl get validatingwebhookconfiguration otel-operator-opentelemetry-operator-validation \
  -o jsonpath='{.webhooks[0].clientConfig.caBundle}' | base64 -d > ca-v.pem
openssl s_client -connect 127.0.0.1:19443 -servername otel-operator-opentelemetry-operator-webhook.monitoring.svc \
  </dev/null 2>/dev/null | openssl x509 > served.pem
openssl verify -CAfile ca-m.pem served.pem
openssl verify -CAfile ca-v.pem served.pem
kill $PF
)
```
PASS:
- (a) The operator pod name and START are **identical** to §2(e) (`…-66b76bbb9f-2h72p`,
  `2026-11-02T23:48:42Z` as of 2026-11-06). IMG is `…opentelemetry-operator:0.162.0`, R=0,
  and the grep prints `"--feature-gates=-operator.networkpolicy"`. There are 3 collector
  pods, one on each of nuc14-01/02/03, each `docker.io/otel/opentelemetry-collector-k8s:0.162.0`,
  `CHART=opentelemetry-kube-stack-0.27.0`, START after the merge, R=0. The two queries
  print `['1']` and `['3']`.
- (b) Both lines print `served.pem: OK`.

FAILS AS:
- The operator pod changed (a new name or START): the operator rolled, which contradicts
  §1.2. Run §4.3 immediately. If an `opentelemetry-operator` NetworkPolicy exists, go to §5.3.
- A collector pod is still on the 0.26.1 label or an old START: the roll stalled.
- `EMPTY`: the instrument is blind. Re-run §2(e) and retry after Prometheus settles. Only a
  persistent EMPTY with a settled Prometheus counts as a FAIL.
- (b) `verification failed: 20 (unable to get local issuer certificate)` means the served cert
  is not signed by the new CA. Dry-tested 2026-11-06: against the live caBundle it prints
  `OK` twice, and against a freshly generated foreign CA it prints exactly this error, so the
  gate can fail. Re-run after 5 more minutes. If it still fails, CR create/update admission is
  being **silently skipped** (failurePolicy Ignore), not blocked. This is a WARN with a finding, and
  the fix is a planned operator pod restart in a later slot. It is not a §5 rollback, because
  rolling back regenerates the cert again and the race comes back.

### 4.2 CONTENTS ASSERTION — container.image.tag is still emitted after the roll

```
CONTENTS ASSERTION: every re-started collector logs the upstream "is being renamed" warning
  (gate-OFF path) and none logs "will NOT be emitted" (gate-ON path), and metrics documents
  ingested after ROLLOUT_TS still carry resource.attributes.container.image.tag (non-zero floor).
  Code path: processor/k8sattributesprocessor processor.go Start() @ contrib v0.162.0 (#51188
  made both warnings reachable; analysed in the 0.26.1 plan §4.2).
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
curl -k -s --max-time 240 -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
  "https://localhost:19200/metrics-*/_count" -d '{"query":{"bool":{"filter":[
    {"range":{"@timestamp":{"gte":"'"$ROLLOUT_TS"'"}}},{"exists":{"field":"resource.attributes.container.image.tag"}}]}}}'; echo
kill $PF 2>/dev/null
```
PASS: every pod prints `notemitted=0 renamed=3` (one `k8s_attributes` instance per
logs/metrics/traces pipeline). The `_count` is **> 0**.

**Run the log half within an hour of the roll.** kubelet rotates the container log, and
`kubectl logs` only reads the current file. Measured 2026-11-06 on the 4-day-old pods:
`twws4`/`wpzjx` print `renamed=3`, while `np8w8` prints `renamed=0` because its current
log starts at 2026-11-05T10:12Z. A late read gives a false FAIL.

FAILS AS:
- `notemitted>=1`: the pin is not reaching the binary and the tag is being dropped. This is
  feature loss, go to §5.1.
- `renamed=0 notemitted=0` on a fresh pod: the upstream text or the binary changed (check
  §4.1). This is INCONCLUSIVE and counts as FAIL until the ES half is checked.
- `_count` 0: feature loss, go to §5.1.
- Timeout or empty output: the instrument is blind. Re-run.

### 4.3 CONTENTS ASSERTION — no operator NetworkPolicy; operand policy unchanged

```
CONTENTS ASSERTION: the NetworkPolicies in monitoring are exactly
  {otel-operator-daemon-collector-networkpolicy}, with a cluster-wide positive control.
```
```bash
kubectl get netpol -A -o name | wc -l
kubectl get netpol -n monitoring -o jsonpath='{.items[*].metadata.name}'; echo
```
PASS: the count equals the §2(e) baseline (`5` on 2026-11-06), and the list is exactly
`otel-operator-daemon-collector-networkpolicy`.
FAILS AS:
- An `opentelemetry-operator` entry: go to §5.3 at once.
- The collector policy is missing: WARN with a finding (the CR spec did not change, so this
  should not happen).

### 4.4 CONTENTS ASSERTION — pod logs flow from every node (load-bearing)

Run **≥15 min after `$ROLLOUT_TS`**.

```
CONTENTS ASSERTION: pod-log documents from ALL THREE nodes land in Elasticsearch in a window
  that starts after the roll. Measured in ES (not at the exporter; _bulk returns 200 even when
  items are rejected), compared to the §2(e) node set and alert list.
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
kubectl get --raw "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/alerts" \
  | grep -o '"alertname":"[^"]*"' | grep -vE 'Watchdog|InfoInhibitor' | sort | uniq -c
```
PASS:
- Three buckets, `k8s-nuc14-01/02/03`, each **> 0**. For reference, the 0.26.1 plan's
  15-minute baseline was 5 016 / 8 411 / 6 191. This is a presence check, not a volume check.
- No `OtelDaemonCollectorDown`. The rule exists in PrometheusRule `otel-collector-alerts`
  (verified 2026-11-06). No alertname appears beyond the §2(e) list (diff the two outputs by name).

FAILS AS:
- A missing node bucket: that collector is Ready but shipping nothing, and no alert
  catches it. Go to §5.1.
- `[]`: the instrument is blind, or nothing at all is flowing. Check edot-collector
  (`kubectl -n monitoring get deploy edot-collector`) before deciding.
- A new alertname: investigate before calling it a pass. `OtelDaemonCollectorDown` is a FAIL.

## 5) Rollback

### 5.1 Expected path — revert the merge

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit "$MERGE_SHA"
git log -1 --format=%s     # confirm the subject is THIS revert (shared worktree; amend before push if not)
git show --stat HEAD       # only kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml
git push
kubectl -n monitoring rollout status daemonset/otel-operator-daemon-collector --timeout=10m
```
The revert relabels the CR back to 0.26.1 and rolls the collectors once more. It
regenerates the webhook cert once more, and the same failurePolicy-Ignore reasoning applies.
No CRD or binary changes, and nothing is forward-only. If Renovate re-opens #472, leave it
open and do not re-merge outside a window.

### 5.2 Confirm the cluster is back

```bash
kubectl get hr otel-operator -n monitoring -o jsonpath='{.status.history[0].chartVersion}/{.status.history[0].status}'; echo   # 0.26.1/deployed
kubectl -n monitoring get pods -l helm.sh/chart=opentelemetry-kube-stack-0.26.1 -o name | wc -l                                # 3
kubectl -n monitoring get ds otel-operator-daemon-collector -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled}'; echo  # 3/3
```
Then re-run §4.3 and §4.4 with a fresh `ROLLOUT_TS`.

### 5.3 The RollbackFailed trap — only if the operator is NOT Ready

This is not expected, because the operator is not touched (§1.2). It is kept because this
HR has shown the shape once (2026-10-12, helm revs 68/69 `failed`, "timeout waiting for …
OpenTelemetryCollector … InProgress").

1. **Diagnose (read-only):**
   ```bash
   kubectl -n monitoring get pods -l app.kubernetes.io/name=opentelemetry-operator
   kubectl -n monitoring logs deploy/otel-operator-opentelemetry-operator --tail=80 | grep -iE 'networkpolicy|i/o timeout|dial tcp|feature gate|forbidden|x509'
   kubectl get netpol -n monitoring -o wide
   helm -n monitoring history otel-operator --max 5
   ```
2. **BREAK-GLASS (direct mutation; record the operator's approval in the run log).** Only if
   `kubectl get netpol -n monitoring` lists `opentelemetry-operator`, run
   `kubectl delete netpol opentelemetry-operator -n monitoring`. Do not delete the operator
   Deployment. Then run
   `kubectl -n monitoring rollout status deploy/otel-operator-opentelemetry-operator --timeout=5m`.
3. Revert in git (§5.1) if you have not already pushed the revert.
4. Clear Flux's exhausted retry counter (SOP `docs/sops/application-update.md` §11 wedge path):
   `flux reconcile hr otel-operator -n monitoring --reset`, then `--force`. If helm is left in
   `pending-*`, roll back to the deployed 0.26.1 revision recorded in §2(b) (rev 72 as of
   2026-11-06): `helm rollback otel-operator <that-rev> -n monitoring --wait=false`, then
   `flux reconcile hr otel-operator -n monitoring --force`. Never use a revision older than 70,
   because those predate the networkpolicy gate pin.
5. Confirm with §5.2, then file a finding.

## 6) Interference notes

- **Execution class.** `capability_change: false` + `rollback_class: git-revert` →
  derives AUTO-NIGHT. No `autonomy_override` is set. **Recommended slot: a nightly that is
  not 2026-11-10.** That night holds `edot-collector-0.164.0` (a conflict, because both ES
  gates read through edot). The natural choice is `nightly:2026-11-11` or later, so that
  edot's roll has a day to settle and a failure stays attributable. Do not use
  `nightly:2026-11-09` (gha-fleet-0.15.1, 35 min; 35 + 40 > 70). Do not use 2026-11-22
  (Talos node roll).
- **The deny rule's wording.** The `*opentelemetry-kube-stack*` reason in
  `runbooks/auto-update-policy.yaml` says "REMOVE THIS RULE only when … the policy is
  disabled in values, and the bump goes through an attended window". That is the condition
  for *removing the rule*, not a requirement that every planned bump runs attended. The
  0.26.1 plan satisfied it (attended, run 2026-11-03). The hazard the rule names lives in
  the operator, and this bump leaves the operator byte-identical, so I see no basis for
  `human-gated` here. If the reviewer or operator reads the rule as binding per bump,
  adding `autonomy_override: human-gated` is a one-line restriction. Retiring or narrowing
  the rule (e.g. to subchart/appVersion moves) is a separate operator decision, and is now
  arguably due.
- **flux-oci-chart-sources (sun-attended:2026-12-13).** Its stage-5 census pins this HR at
  `0.26.1` ("0.26.1 yes", OCI presence confirmed). After this plan lands, that line is stale.
  The OCI chart `ghcr.io/open-telemetry/opentelemetry-helm-charts/opentelemetry-kube-stack:0.27.0`
  exists (verified 2026-11-06), so stage 5 is not blocked, but its premises and roll
  prediction for otel must be re-measured at 0.27.0. It is listed in `conflicts_with` (same file).
- **helm-drift-detection (sat-attended:2026-11-28)** writes `spec.driftDetection` into this
  HelmRelease. Use separate slots. Note for that plan: every chart upgrade regenerates the
  webhook cert and caBundle (§1.3.3), which matches its own table row "otel-operator webhook
  caBundle … YES after any hand rotation".
- **Log gap.** Each node loses ~10–30 s of pod logs during its collector roll. Other
  same-window plans whose gates read ES log continuity must read outside those minutes.
- **Reciprocity.** None of edot-collector-0.164.0, helm-drift-detection,
  flux-oci-chart-sources, talos-linux-1.14.5, grafana-14.1.0 or redis-fleet-8.10.3 names
  `otel-operator-0.27.0` yet. Their 0.26.1 refs were pruned as dead on 2026-11-03. The
  orchestrator should add the reciprocal entries. This planner writes only this file.
- **Future hazard (carried forward).** When contrib promotes
  `processor.k8sattributes.DontEmitV0K8sConventions` to **stable**, the `-gate` pin becomes a
  startup error. This plan does not move the collector, but the next otel-operator plan that
  changes `appVersion` must re-check the gate's `stage:` in
  `processor/k8sattributesprocessor/metadata.yaml` at the target tag.
- **No reboot, no shared infra beyond `monitoring`.** No gateway, cert-manager, Cilium,
  storage or database is touched.
