---
plan_id: otel-operator-0.27.1
component: otel-operator               # HelmRelease monitoring/otel-operator; CHART is the umbrella
                                       # opentelemetry-kube-stack (subcharts otel-crds, prometheus-crds,
                                       # opentelemetry-operator 0.128.0, kube-state-metrics, node-exporter)
pr: 513                                # "fix(helm): update opentelemetry-kube-stack ( 0.27.0 → 0.27.1 )", one-line diff to
                                       # helmrelease.yaml; CI green (Flate Render Gate, Flux Local Diff hr+ks), checked 2026-11-16
kind: chart
current: "0.27.0"                      # MEASURED 2026-11-16: HR spec 0.27.0, helm revision 73 deployed (2026-11-07)
target: "0.27.1"
update_type: patch
risk: low                              # measured: the 0.27.0 vs 0.27.1 render with OUR live values is identical apart from
                                       # random cert material and the helm.sh/chart label (section 1.2). appVersion stays 0.162.0, so
                                       # operator AND collector binaries do not move. The one live effect is a 3-pod DaemonSet
                                       # roll, because the chart label is copied onto the collector pods.
est_duration_min: 25                   # 5 pre-checks + 3 merge + 8 roll (3 pods, maxUnavailable 1) + 5 settle + 4 verification
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:                           # every object verified to EXIST live 2026-11-16
    - helmrelease/otel-operator                         # git edit: chart version only (PR 513)
    - opentelemetrycollector/otel-operator-daemon       # label helm.sh/chart 0.27.0 -> 0.27.1; spec unchanged
    - daemonset/otel-operator-daemon-collector          # ROLLS ONCE (pod label change): maxSurge 0 / maxUnavailable 1
    - secret/otel-operator-opentelemetry-operator-controller-manager-service-cert  # pre-upgrade hook regenerates it
    - mutatingwebhookconfiguration/otel-operator-opentelemetry-operator-mutation      # caBundle
    - validatingwebhookconfiguration/otel-operator-opentelemetry-operator-validation  # caBundle
    - "deployment/otel-operator-opentelemetry-operator — NOT expected to roll (pod template labels carry the SUBCHART
       version opentelemetry-operator-0.128.0, unchanged); asserted in 4.1"
  shared:
    - monitoring                       # the cluster's ONLY pod-log / host-metric / kubelet-stats / k8s-event collection
                                       # path into edot-collector -> Elasticsearch; each node loses ~10-30 s of pod logs
                                       # during its collector roll (filelog, no storage extension)
depends_on: []
conflicts_with:                        # ONLY this field is honoured by window-scheduler.py.
                                       # Built 2026-11-16 from every non-terminal plan in `maintenance-plan.py --open`.
  - kube-prometheus-stack-93.3.0       # section 4 reads Prometheus (shared window instrument); a same-night bump of it makes the
                                       # metric controls unattributable
  - talos-linux-1.14.6                 # the roll of record (supersedes 1.14.5): re-creates every collector pod; 4.4 per-node gate
                                       # cannot attribute a node; also monitoring is in its touches.shared
  - talos-linux-1.14.5                 # same roll, previous target (vetted, still holds sun-attended:2026-11-22 until superseded)
  - longhorn-1.13.0                    # storage-engine move re-attaches the ES / Prometheus volumes this plan reads in section 4
  - helm-drift-detection               # writes spec.driftDetection into every HelmRelease incl. this one
  - flux-oci-chart-sources             # rewrites spec.chart -> chartRef in this same helmrelease.yaml
  - coredns-1.50.5                     # DNS restart in the window: collectors resolve edot-collector.monitoring.svc
  - envoy-gateway-1.10.0               # data-plane roll; kubectl port-forward / ES reads in section 4 are the instrument
  - flux-reconciler-impersonation      # EXCLUSIVE, touches flux + monitoring: changes how every HelmRelease (this one) is applied
  - etcd-timeouts-5000-500             # etcd/apiserver disturbance during a Flux apply is the 5.3 trap on this HR (blocked today)
  - talos-power-tuning-ab              # EXCLUSIVE machine-config apply on every node: restarts the collector DaemonSet pods
exclusive: false
security_ref: null                     # not security-driven
capability_change: false               # same appVersion, same CR spec, same pipelines; the new chart field
                                       # (opAMPBridge.podSecurityContext) is only rendered for an OpAMPBridge, none exists
rollback_class: git-revert             # nothing forward-only: no CRD, schema or data change in the render
autonomy_override: human-gated         # the deny rule `*opentelemetry-kube-stack*` (auto-update-policy.yaml) requires "an
                                       # attended window"; its offline-render condition is re-proven in 3.1
finding_refs: [F-e918a007]             # RE-VERIFIED 2026-11-16 07:00Z (`policy-cli.py finding list --grep otel --all`, `finding show`):
                                       # F-e918a007 (version, "otel-operator: chart 0.27.0 -> 0.27.1 (patch)", status unchanged, open,
                                       # first_seen 2026-11-15; the id was RESOLVED on 2026-11-14 and re-opened for this bump, so an
                                       # earlier read of "resolved" is the stale one). Also reads as F-e918a007 for the earlier
                                       # 0.24.3 -> 0.24.4 bump (resolved 2026-10-15): the id is per-component, not per-version.
                                       # NOT referenced, on purpose: F-51ed9a3a (AR-124, collector-k8s 0.162.0 CVEs: the image does
                                       # not move), F-76387378 (edot ES drops, a baseline in 4.4), and the RESOLVED F-60ebcdb5
                                       # (0.26.1 -> 0.27.0, already deployed rev 73), F-c01269d5, F-97c88a5c, F-61e4d5b6.
status: vetted
superseded_by: null
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-16"
premises:
  - id: live-chart-is-0.27.0
    why: "`current:` claims 0.27.0. If the HR moved, the render comparison in 1.2 and the rollback target in 5 are stale."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "0.27.0"
  - id: otel-hr-ready
    why: "Never stack a chart bump on a failing release; with remediation strategy rollback a pre-existing failure re-enters the RollbackFailed trap (F-97c88a5c shape)."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: last-release-deployed-0.27.0
    why: "The section 5 rollback depends on helm's newest revision being a deployed 0.27.0."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.status.history[0].chartVersion}/{.status.history[0].status}'
    expect_exact: "0.27.0/deployed"
  - id: gate-pin-in-values
    why: "Load-bearing: the operator.networkpolicy pin is the belt to the upstream alpha/off default; the 2026-10-12 deadlock returns if it is lost."
    run: kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.spec.values.opentelemetry-operator.manager.featureGatesMap}'
    expect_contains: '"operator.networkpolicy":false'
  - id: operator-image-0.162.0
    why: "1.2 proves the 0.27.1 render keeps appVersion 0.162.0; the 'no binary moves' claim only holds from 0.162.0."
    run: kubectl get deploy otel-operator-opentelemetry-operator -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/open-telemetry/opentelemetry-operator/opentelemetry-operator:0.162.0"
  - id: collector-image-0.162.0
    why: "Same claim for the collector binary."
    run: kubectl get ds otel-operator-daemon-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "otel/opentelemetry-collector-k8s:0.162.0"
  - id: monitoring-netpols-exactly-collector
    why: "Baseline for 4.3: an `opentelemetry-operator` entry means the deadlock is already live; a missing collector entry means the baseline moved."
    run: kubectl get networkpolicy -n monitoring -o jsonpath='{.items[*].metadata.name}'
    expect_exact: "otel-operator-daemon-collector-networkpolicy"
---

# otel-operator — opentelemetry-kube-stack 0.27.0 → 0.27.1

## 1) Summary & why held

### 1.1 Why it was held

Two independent holds, neither a technical objection to this release:

1. **Release notes unavailable.** Renovate's PR body links the wrong release: its
   "Release Notes" section points at `opentelemetry-demo-0.27.1` (a different chart in the
   same repo, "fix grafana dashboards") because the tag numbers collide. The auto-updater therefore
   could not verify anything and routed it here. **This is a repo/Renovate defect, not a property of the
   release.** The real notes were read for this plan (upstream tag `opentelemetry-kube-stack-0.27.1`):
   > "[opentelemetry-kube-stack] Render opAMPBridge.podSecurityContext by @henriquesantanati in #2552"
   That is the entire change list.
2. **Deny rule `*opentelemetry-kube-stack*`** (HELD 2026-10-12, F-c01269d5) requires that a chart bump go
   through an attended window. Its offline-render condition is met by the gate pin in values (0e976cf5)
   and re-proven in 3.1.

### 1.2 Measured render delta (with our live values), 2026-11-16

`helm pull` of both charts, then `helm template ... -f <spec.values from HEAD> --include-crds`:
both render 21 034 lines. After removing the random cert material (`caBundle`, `tls.crt`, `tls.key`,
`ca.crt`) and the `helm.sh/chart` label, the diff is **empty**. The chart-source diff is exactly two
files:

- `Chart.yaml`: `version: 0.27.0` → `0.27.1` (appVersion stays `0.162.0`, subchart `opentelemetry-operator`
  stays `0.128.0`).
- `templates/bridge.yaml`: adds `podSecurityContext: {{ toYaml $.Values.opAMPBridge.podSecurityContext }}`
  to the OpAMPBridge spec. **No OpAMPBridge is rendered** with our values and none exists live
  (`kubectl get opampbridge -A` → "No resources found").

Rendered images: operator `:0.162.0`, `--collector-image=otel/opentelemetry-collector-k8s:0.162.0`,
`--feature-gates=-operator.networkpolicy` count 1. All identical to what is live.

### 1.3 What actually happens at apply time (the part that is not zero)

- The rendered OpenTelemetryCollector CR carries `helm.sh/chart: opentelemetry-kube-stack-<chart version>`
  as a label. The operator copies CR labels onto the DaemonSet pod template, so
  **the label change rolls all 3 collector pods once** (updateStrategy RollingUpdate,
  `maxSurge 0 / maxUnavailable 1`, so one node at a time). Same binary, same config; each node loses
  ~10-30 s of pod logs during its own roll.
- The operator Deployment's pod template carries only the SUBCHART label (`opentelemetry-operator-0.128.0`),
  unchanged, so it is **not expected to roll**. The pre-upgrade hook still regenerates the webhook cert
  Secret and both webhook `caBundle` fields, exactly as in the 0.27.0 upgrade on 2026-11-07 (helm
  revision 73 "Upgrade complete").
- No CRD content changed (CRDs are in the render and the diff is empty).

### 1.4 Verdict

`risk: low`, no reboot, nothing forward-only. The hold was a false positive on the technical axis (wrong
release notes linked) plus a procedural hold from the deny rule. The plan still routes through an attended
slot because the deny rule's text demands it; narrowing that rule is a separate operator decision.

## 2) Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` in zsh on the Mac mini. **etcd note (2026-11-16):** etcd was
flapping (~12 leader changes that day). Every apply step below is a Flux apply through the API server. If
`talosctl etcd status` (or the window agent's etcd gate) shows a leader change in the last 15 min, defer.

```bash
# (a) premises
.venv/bin/python3 runbooks/plan-premises.py otel-operator-0.27.1
# PASS: all 7 premises OK. Any FAIL = stop; do not "fix" a premise to proceed.

# (b) Flux + helm not mid-flight
flux get hr otel-operator -n monitoring
helm -n monitoring history otel-operator --max 3
# PASS: Ready True, newest revision `deployed` (73 / 0.27.0 on 2026-11-16). A `pending-*` = stop.

# (c) PR 513 is still the one-line bump, CI green
gh pr view 513 --json state,files,statusCheckRollup \
  -q '.state, [.files[].path], [.statusCheckRollup[]|.name+"="+.conclusion]'
gh pr diff 513 | grep '^[-+] '
# PASS: OPEN; files == [kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml]; all checks SUCCESS;
# diff exactly `-      version: 0.27.0` / `+      version: 0.27.1`.
# FAILS AS: a different version line (Renovate re-targeted, as it did for #351 and #324) -> STOP, plan is stale.

# (d) baselines (record in the run log)
kubectl -n monitoring get pods -l app.kubernetes.io/component=opentelemetry-collector \
  -o 'custom-columns=N:.metadata.name,NODE:.spec.nodeName,START:.status.startTime,R:.status.containerStatuses[0].restartCount,CHART:.metadata.labels.helm\.sh/chart'
kubectl -n monitoring get pods -l app.kubernetes.io/name=opentelemetry-operator \
  -o 'custom-columns=N:.metadata.name,START:.status.startTime,R:.status.containerStatuses[0].restartCount'
kubectl get netpol -A -o name | wc -l
# 2026-11-16: 3 collector pods (CHART column shows opentelemetry-kube-stack-0.27.0), 1 operator pod, 5 NetworkPolicies cluster-wide.
```

## 3) Steps

### 3.1 GATE — offline render proof (deny-rule removal condition). Must print `GATE PASS`.

```bash
REPO=/Users/mu/code/cberg-home-nextgen
G=$(mktemp -d /tmp/otel-0271-gate.XXXXXX)
cd "$G" || exit 1
helm pull opentelemetry-kube-stack --repo https://open-telemetry.github.io/opentelemetry-helm-charts \
  --version 0.27.1 --untar --untardir c || { echo "GATE FAIL: pull"; exit 1; }
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
NPOL=$(grep -c '^kind: NetworkPolicy' r.yaml)
echo "gate_arg=$GATE operator_img=$IMG collector_img=$COLIMG collector_gate='$CARGS' chart_netpol=$NPOL dir=$G"
if [ "$GATE" = 1 ] && [ "$IMG" = 1 ] && [ "$COLIMG" = 1 ] && [ "$CARGS" = "-processor.k8sattributes.DontEmitV0K8sConventions" ]; then echo "GATE PASS"; else echo "GATE FAIL"; fi
cd "$REPO"
```

Measured 2026-11-16 against the 0.27.1 chart: `gate_arg=1 operator_img=1 collector_img=1`, and the diff
against the 0.27.0 render is empty (1.2). **FAILS AS:** `gate_arg=0` — the pin was lost or the subchart
renamed `featureGatesMap` (STOP). `operator_img=0` / `collector_img=0` — the chart moved under the same version
or someone pinned images; the 0.162.0 analysis no longer holds (STOP, re-plan). `collector_gate` empty — the
`collectors.daemon.args` pin was lost from HEAD values, so the collector would drop `container.image.tag` (STOP).
Negative control: running the gate with `--version 0.25.1` and a `0.162.0` expectation prints `GATE FAIL`
(0.25.1 renders 0.161.0).
`chart_netpol` is informational only: the operator NetworkPolicy is created at runtime by the binary, not the
chart (see 4.3), so a 0 here proves nothing and is not part of the pass condition.

### 3.2 Merge PR 513 (attended; operator GO recorded)

```bash
cd /Users/mu/code/cberg-home-nextgen
gh pr merge 513 --squash --delete-branch
git pull --ff-only
git log -1 --format='%h %s'          # must be the #513 squash
grep -n 'version: 0.27.1' kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml    # MUST match 1 line
grep -n 'DontEmitV0K8sConventions' kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml   # args pin survived
W="$HOME/.cache/otel-0271"; mkdir -p "$W"; chmod 700 "$W"
MERGE_SHA=$(git rev-parse HEAD); echo "$MERGE_SHA" | tee "$W/merge-sha.txt"      # shell state does not survive between Bash calls: 5.1 reads this file
```

No manual `flux reconcile`: the push webhook drives the source. Only if
`flux get hr otel-operator -n monitoring` still shows 0.27.0 after 10 min, run
`flux reconcile hr otel-operator -n monitoring --with-source`.

### 3.3 Watch the rollout, THEN stamp ROLLOUT_TS (not before)

`rollout status` can return at once on the OLD generation (Flux has not reconciled yet; see 4.1), so a timestamp taken
after it can predate the roll, and every ES window that starts at it would then count pre-roll documents. The stamp is
therefore taken only inside a loop that proves the NEW generation is live: HelmRelease history says `0.27.1/deployed`
AND all three collector pods carry the `0.27.1` chart label AND are Ready.

```bash
W="$HOME/.cache/otel-0271"; mkdir -p "$W"
rm -f "$W/rollout-ts.txt"      # never inherit a stamp from an earlier run
OK=no
for i in $(seq 1 60); do
  HR=$(kubectl get hr otel-operator -n monitoring -o jsonpath='{.status.history[0].chartVersion}/{.status.history[0].status}')
  NEW=$(kubectl -n monitoring get pods -l app.kubernetes.io/component=opentelemetry-collector \
    -o jsonpath='{range .items[*]}{.metadata.labels.helm\.sh/chart}{" "}{.status.containerStatuses[0].ready}{"\n"}{end}' \
    | grep -c '^opentelemetry-kube-stack-0.27.1 true$')
  echo "poll $i: hr=$HR new-generation-ready=$NEW/3"
  if [ "$HR" = "0.27.1/deployed" ] && [ "$NEW" = "3" ]; then OK=yes; break; fi
  sleep 30
done
if [ "$OK" = yes ]; then
  date -u +%Y-%m-%dT%H:%M:%SZ | tee "$W/rollout-ts.txt"          # ROLLOUT_TS: the LAST collector pod just became Ready on 0.27.1
else
  rm -f "$W/rollout-ts.txt"; echo "ROLL NOT COMPLETE after 30 min: NO ROLLOUT_TS written; go to 5.3 diagnostics"
fi
flux get hr otel-operator -n monitoring
```

**PASS:** the loop ends with `hr=0.27.1/deployed new-generation-ready=3/3` and writes `rollout-ts.txt`. **FAILS AS:** 60 polls
without the pair (prints `ROLL NOT COMPLETE`, deletes the stamp file, so 4.2 and 4.4 refuse to run: they `exit 1` on a
missing file). Dry-tested read-only against the live 0.27.0 cluster 2026-11-16: the pod read printed
`new-generation-ready=3` for the label `0.27.0` (the positive control: the jsonpath and the grep both work) and `0` for
`0.27.1`, so before the roll the loop cannot succeed. Later steps read the stamp with
`ROLLOUT_TS=$(cat "$HOME/.cache/otel-0271/rollout-ts.txt")` (shell state does not persist between calls).

Expect `Ready True`, `Helm upgrade succeeded ... 0.27.1`. Run the 4.3 netpol check once **immediately** (do
not wait for the HR timeout): an `opentelemetry-operator` policy appearing means go to 5.3 now.

## 4) Verification

### Floor (shape — necessary, not sufficient)

```bash
kubectl get hr otel-operator -n monitoring \
  -o jsonpath='{.status.history[0].chartVersion}/{.status.history[0].status} ready={.status.conditions[?(@.type=="Ready")].status}'; echo
kubectl get opentelemetrycollector otel-operator-daemon -n monitoring \
  -o jsonpath='ver={.status.version} scale={.status.scale.statusReplicas}'; echo
```

PASS: `0.27.1/deployed ready=True`; `ver=0.162.0 scale=3/3`. FAILS AS: `0.27.0/deployed` (the upgrade did not
land; 3.2 grep line passed but Flux has not reconciled) or `UpgradeFailed`/`RollbackFailed` (go to 5.3).

### 4.1 CONTENTS ASSERTION — the roll happened, nothing else moved

```
CONTENTS ASSERTION: every RUNNING collector pod carries label helm.sh/chart=opentelemetry-kube-stack-0.27.1
  (proves the 3-pod roll took the new generation), is still collector-k8s:0.162.0 with the
  DontEmitV0K8sConventions arg, and the RUNNING operator pod is unchanged (same pod name and start time as
  2(d)), image 0.162.0, with --feature-gates=-operator.networkpolicy. Measured on live pods, not the template.
CONTROL: kube_deployment_status_replicas_available otel-operator-opentelemetry-operator must be 1
```
```bash
kubectl -n monitoring get pods -l app.kubernetes.io/component=opentelemetry-collector \
  -o 'custom-columns=N:.metadata.name,NODE:.spec.nodeName,IMG:.status.containerStatuses[0].image,R:.status.containerStatuses[0].restartCount,CHART:.metadata.labels.helm\.sh/chart'
kubectl get ds otel-operator-daemon-collector -n monitoring -o jsonpath='{.spec.template.spec.containers[0].args}'; echo
kubectl -n monitoring get pods -l app.kubernetes.io/name=opentelemetry-operator \
  -o 'custom-columns=N:.metadata.name,START:.status.startTime,IMG:.status.containerStatuses[0].image,R:.status.containerStatuses[0].restartCount,READY:.status.containerStatuses[0].ready'
kubectl get pod -n monitoring -l app.kubernetes.io/name=opentelemetry-operator \
  -o 'jsonpath={.items[0].spec.containers[0].args}' | tr ',' '\n' | grep -i feature-gates
P=/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query
kubectl get --raw "${P}?query=kube_deployment_status_replicas_available%7Bnamespace%3D%22monitoring%22%2Cdeployment%3D%22otel-operator-opentelemetry-operator%22%7D" \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('avail=',[x['value'][1] for x in r] or 'EMPTY')"
```

PASS: three collector pods on nuc14-01/02/03, each `CHART=opentelemetry-kube-stack-0.27.1`,
`...collector-k8s:0.162.0`, R=0. DaemonSet args contain `--feature-gates=-processor.k8sattributes.DontEmitV0K8sConventions`.
One operator pod, START equals the 2(d) baseline, image `...:0.162.0`, ready `true`; the grep prints
`"--feature-gates=-operator.networkpolicy"`. `avail= ['1']`.
FAILS AS: any pod still `CHART=...0.27.0` (the roll stalled or `rollout status` read the old generation) -> FAIL.
Operator START newer than baseline or R>0 -> the cert/webhook hook disturbed it; check 4.3 then 5.3. The grep prints
nothing -> the gate was lost. `avail= EMPTY` -> the instrument is blind, which counts as FAIL.

### 4.2 CONTENTS ASSERTION — container.image.tag is still emitted (feature-loss guard; carried over)

```
CONTENTS ASSERTION: after the roll, metrics documents still carry resource.attributes.container.image.tag
  (count > 0) in a window starting at ROLLOUT_TS, and no collector logged the upstream "will NOT be emitted"
  warning. Measured in ES and in the collector's own startup log.
```
```bash
for p in $(kubectl -n monitoring get pods -l app.kubernetes.io/component=opentelemetry-collector -o name); do
  printf "%s notemitted=%s renamed=%s\n" "$p" \
    "$(kubectl -n monitoring logs "$p" | grep -ci 'container.image.tag is configured but will NOT be emitted')" \
    "$(kubectl -n monitoring logs "$p" | grep -ci 'container.image.tag is being renamed')"
done
ROLLOUT_TS=$(cat "$HOME/.cache/otel-0271/rollout-ts.txt") || exit 1; [ -n "$ROLLOUT_TS" ] || { echo "no ROLLOUT_TS: 3.3 did not complete"; exit 1; }
echo "ROLLOUT_TS=$ROLLOUT_TS"
ES_PW=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)
kubectl port-forward -n monitoring svc/elasticsearch-es-http 19200:9200 >/dev/null 2>&1 & PF=$!
sleep 5
curl -k -s --max-time 240 -u "elastic:$ES_PW" -H 'Content-Type: application/json' \
  "https://localhost:19200/metrics-*/_count" -d '{"query":{"bool":{"filter":[
    {"range":{"@timestamp":{"gte":"'"$ROLLOUT_TS"'"}}},{"exists":{"field":"resource.attributes.container.image.tag"}}]}}}'; echo
kill $PF 2>/dev/null
```

Run >= 3 min after ROLLOUT_TS (one metrics export interval must land inside the window).

PASS: every pod `notemitted=0` and `renamed>=1` (the "renamed" warning is logged when the legacy gate is OFF and
the tag is configured, so it proves our arg took effect; `renamed=0` is **inconclusive = FAIL**). ES count > 0.
FAILS AS: `notemitted>=1` -> the arg did not reach the binary and the tag is being dropped (5.1). Count 0 ->
feature loss. A curl timeout or empty output -> instrument blind, rerun with a narrower window.

### 4.3 CONTENTS ASSERTION — no operator NetworkPolicy; operand policy unchanged

```
CONTENTS ASSERTION: NetworkPolicies in monitoring are exactly {otel-operator-daemon-collector-networkpolicy},
  with a cluster-wide positive control (5).
```
```bash
kubectl get netpol -A -o name | wc -l                              # positive control: 5
kubectl get netpol -n monitoring -o jsonpath='{.items[*].metadata.name}'; echo
kubectl get opentelemetrycollector otel-operator-daemon -n monitoring -o jsonpath='np=[{.spec.networkPolicy.enabled}]'; echo
```

PASS: count `5`; list exactly `otel-operator-daemon-collector-networkpolicy`; `np=[true]`.
FAILS AS: an `opentelemetry-operator` entry -> the deadlock policy exists, go to 5.3 immediately. The collector policy
missing (count 4, `np=[]`) is a WARN, not a rollback (telemetry is unaffected; ingress allow-list only): file a finding.

### 4.4 CONTENTS ASSERTION — telemetry flows from every node (load-bearing)

Run **>= 10 min after ROLLOUT_TS** (the stamp is taken when the LAST collector pod became Ready on 0.27.1, so the window holds only post-roll documents).

```
CONTENTS ASSERTION: pod-log documents from ALL THREE nodes land in Elasticsearch in a window starting at
  ROLLOUT_TS - measured in ES (not at the exporter; _bulk returns 200 even when items are rejected).
CONTROL: kube_daemonset_status_number_ready otel-operator-daemon-collector must be 3
CONTROL: alertname OtelDaemonCollectorDown must NOT be firing
```
```bash
ROLLOUT_TS=$(cat "$HOME/.cache/otel-0271/rollout-ts.txt") || exit 1; [ -n "$ROLLOUT_TS" ] || { echo "no ROLLOUT_TS: 3.3 did not complete"; exit 1; }
echo "ROLLOUT_TS=$ROLLOUT_TS (now $(date -u +%H:%M:%SZ); must be >= 10 min later)"
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

PASS: three buckets `k8s-nuc14-01/02/03`, each `> 0`; `ready= ['3']`; no `OtelDaemonCollectorDown` and nothing new vs the
pre-window alert list (alert rule exists: `kubernetes/apps/monitoring/kube-prometheus-stack/app/otel-collector-alerts.yaml`,
fires after 5 min below desired). This is a presence check, not a volume check.
FAILS AS: a missing node bucket (a collector Ready but shipping nothing, which no alert catches); total `[]` or
`ready= EMPTY` (instrument blind = FAIL). Negative control: the same aggregation on a non-existent field returns `[]`.
Note: the edot ES-drop finding F-76387378 (~360 metric points/h, `otelcol` families) is a pre-existing baseline;
do not read it as a regression from this plan. Compare against the pre-window alert list, not zero.

## 5) Rollback

### 5.1 Expected path — revert the merge

```bash
cd /Users/mu/code/cberg-home-nextgen
MERGE_SHA=$(cat "$HOME/.cache/otel-0271/merge-sha.txt"); [ -n "$MERGE_SHA" ] || { echo "no merge sha recorded: find the #513 squash with git log --oneline -5 -- kubernetes/apps/monitoring/otel-operator"; exit 1; }
git revert --no-edit "$MERGE_SHA"
git log -1 --format=%s     # confirm the subject is THIS revert (shared worktree)
git show --stat HEAD       # only helmrelease.yaml
git push
kubectl -n monitoring rollout status daemonset/otel-operator-daemon-collector --timeout=10m
```

Safe while the operator is Ready. Nothing is forward-only (no CRD or schema change, no data). The revert rolls
the 3 collector pods once more (label back to 0.27.0).

### 5.2 Confirm the cluster is back

```bash
kubectl get hr otel-operator -n monitoring -o jsonpath='{.status.history[0].chartVersion}/{.status.history[0].status}'; echo   # 0.27.0/deployed
kubectl -n monitoring get pods -l app.kubernetes.io/component=opentelemetry-collector \
  -o 'custom-columns=N:.metadata.name,IMG:.status.containerStatuses[0].image,CHART:.metadata.labels.helm\.sh/chart'            # 0.162.0, chart 0.27.0
kubectl -n monitoring get ds otel-operator-daemon-collector -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled}'; echo  # 3/3
```
Then re-run 4.3 and 4.4 with a fresh stamp: repeat the 3.3 loop with `0.27.0` in the two places it names `0.27.1` (the `HR` test and the label grep) (the stamp file is overwritten).

### 5.3 The RollbackFailed trap — if the operator is NOT Ready

Symptom: operator pod CrashLoopBackOff / not Ready, HR `UpgradeFailed` then `RollbackFailed`, `failed` revisions in
helm history. A `git revert` alone will NOT converge, because every upgrade and rollback waits on a CR that only a Ready
operator can settle. (This shape has occurred once on this HR: F-97c88a5c.)

1. **Diagnose (read-only):**
   ```bash
   kubectl -n monitoring get pods -l app.kubernetes.io/name=opentelemetry-operator
   kubectl -n monitoring logs deploy/otel-operator-opentelemetry-operator --tail=80 | grep -iE 'networkpolicy|i/o timeout|dial tcp|feature gate|forbidden|certificate|webhook'
   kubectl get netpol -n monitoring -o wide
   helm -n monitoring history otel-operator --max 5
   ```
2. **Unblock the operator (BREAK-GLASS direct mutation; needs operator approval recorded in the run log).** Only if
   `kubectl get netpol -n monitoring` lists `opentelemetry-operator`:
   `kubectl delete netpol opentelemetry-operator -n monitoring`. Do NOT delete the operator Deployment. Then
   `kubectl -n monitoring rollout status deploy/otel-operator-opentelemetry-operator --timeout=5m`.
3. **Revert in git** (5.1) if not already pushed.
4. **Clear Flux's exhausted retry counter and re-drive** (operator-approved; `docs/sops/application-update.md` wedge path):
   ```bash
   flux reconcile hr otel-operator -n monitoring --reset
   flux reconcile hr otel-operator -n monitoring --force
   ```
   If helm is left `pending-upgrade`/`pending-rollback`, record the last `deployed` revision (73, 0.27.0) from
   `helm history` **before the merge** (2b), then `helm rollback otel-operator 73 -n monitoring --wait=false` followed by
   `flux reconcile hr otel-operator -n monitoring --force`. Never roll back to a revision older than 72 (0.26.1): revision 71
   (0.24.3) predates the 0.26.1 args pin.
5. Confirm with 5.2, then file a finding.

## 6) Interference notes

- **Attended slot** (`autonomy_override: human-gated`, per the deny rule): sat-attended or sun-attended. No reboot,
  not exclusive. It is short (~25 min) and can share a slot with plans that do not read monitoring.
- **Prometheus and ES are read by 4:** serialize against any `kube-prometheus-stack` bump (plan
  `kube-prometheus-stack-93.3.0` is a draft today; it is in `conflicts_with`). A Longhorn or Talos plan the same night
  makes the 4.4 per-node gate unattributable (also in `conflicts_with`).
- **Log gap:** ~10-30 s of pod logs per node during its collector roll (once, three nodes in sequence). Other same-window
  plans whose gates read ES log continuity must read outside those minutes.
- **etcd instability (2026-11-16, ~12 leader changes):** this plan does not touch etcd or nodes, but a Flux apply during a
  leader election can fail transiently and trigger helm remediation (rollback), which is the 5.3 trap on this HR. Do not start
  while the window agent's etcd gate is red; the 2(b) helm-history check is the second line.
- **Renovate defect (repo correction):** Renovate's release-notes source for this package resolves to the wrong chart
  (`opentelemetry-demo-<same version>`), so every future `opentelemetry-kube-stack` PR will show unrelated notes and fail the
  auto-updater's "verifiable notes" gate. Suggest a `packageRules` override (`changelogUrl` / `sourceUrl` with tag prefix
  `opentelemetry-kube-stack-`) as a follow-up; out of scope here. The deny rule stays regardless.
- **AR-124 / F-51ed9a3a:** the collector image does not move (0.162.0), so this plan neither fixes nor affects that row.
- **Future hazard of the args pin** (carried over): when contrib promotes `processor.k8sattributes.DontEmitV0K8sConventions`
  to stable, `-gate` becomes a startup error and the collector crash-loops on that bump. Needs its own plan/finding before
  that happens; not touched here.
