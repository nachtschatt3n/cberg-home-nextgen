---
plan_id: reloader-v2
component: reloader
pr: null                           # no open Renovate PR at plan time; set to the
                                   # PR number when Renovate raises the 2.2.x bump
kind: chart
current: "1.3.0"
target: "2.2.14"                   # latest 2.2.x (fixed line — see "why held";
                                   # avoid 2.1.0/2.1.1, they had a broken upgrade)
update_type: major                 # Helm CHART major (1.x → 2.x). NB the app image
                                   # inside only goes v1.3.0 → v1.4.19 (a minor)
risk: medium
est_duration_min: 20
needs_reboot: false                # → any no-reboot window (tue/thu)
touches:
  namespaces: [kube-system]        # reloader Deployment + PodMonitor + RBAC live here
  resources:
    - helmrelease/reloader
    - deployment/reloader          # DELETED + recreated (immutable-selector change)
    - serviceaccount/reloader
    - clusterrole/reloader-role
    - clusterrolebinding/reloader-role-binding
    - podmonitor/reloader
  shared: [reloader]               # reloader is cluster-wide config-reload infra:
                                   # a broken/absent reloader SILENTLY stops
                                   # ConfigMap/Secret-triggered rollouts for the
                                   # 25 workloads that annotate it (databases,
                                   # home-automation, office, ai, network, monitoring)
depends_on: []
conflicts_with: []                 # nothing else planned touches reloader; but see
                                   # Interference — do NOT co-schedule with a plan
                                   # that relies on reloader auto-rolling a workload
                                   # after a Secret/ConfigMap change in this window
status: scheduled
window: "thu-early:2026-08-06"
auto_execute: false                # chart major + delete-recreate → operator go/no-go
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/maintenance-windows.md
generated: "2026-07-31"
---

# Stakater Reloader — Helm chart 1.3.0 → 2.2.14 (chart major)

## 1. Summary & why held

**What changes.** Bump the HelmRelease chart version in
`kubernetes/apps/kube-system/reloader/app/helmrelease.yaml` from `1.3.0` to
`2.2.14` (source `oci://ghcr.io/stakater/charts`). This is a **Helm chart
major** (`1.x → 2.x`). The reloader **binary** inside only advances
`appVersion v1.3.0 → v1.4.19` (a minor app bump — `ghcr.io/stakater/reloader:v1.3.0`
→ `:v1.4.19`); the core annotation contract
(`reloader.stakater.com/auto`, `secret.reloader.stakater.com/reload`,
`configmap.reloader.stakater.com/reload`) is unchanged in the app.

**Why it was held (gate: G1 type = major).** The auto-updater denies any
`update_type: major` by policy — a chart major must be reviewed and executed in
a window, never auto-merged.

**The real breaking change (chart, not app): immutable Deployment selector.**
Chart 2.x adopted the Kubernetes/Helm recommended label scheme
(PR [#967](https://github.com/stakater/Reloader/pull/967), *"Use labels
suggested by Kubernetes and Helm best practices"*). That rewrites the reloader
Deployment's `spec.selector.matchLabels`, and a Deployment selector is
**immutable**. `helm upgrade` from a 1.x release therefore fails — this cluster
is running exactly the affected 1.x labels:

```
# in-cluster today (chart 1.3.0):
deployment/reloader  selector.matchLabels = {"app":"reloader","release":"reloader"}
```

The failure mode is documented upstream in issue
[#897](https://github.com/stakater/Reloader/issues/897):

> `Deployment.apps "reloader-reloader" is invalid:
> spec.selector … selector does not match template labels`
> (root cause: *"a Deployment's `selector.matchLabels` field is immutable after
> creation … the new 2.x labels no longer matched the existing selector"*).

This is the same class of failure as the superset 0.20.0 upgrade
(`docs/sops/application-update.md` §7) — the fix is to **delete the reloader
Deployment so Helm recreates it** with the new selector (Step 3d). Reloader is a
stateless single-replica controller (no PVC, `enableHA: false`), so a
delete + recreate is safe and fast; the only cost is a ~30–60 s gap where no
config-change rollouts fire (see Interference).

**Target the 2.2.x line specifically.** Chart `2.1.0`/`2.1.1` shipped a broken
upgrade (the very issue #897) — the release notes for 2.1.1 say *"⚠️ Avoid using
this version and version 2.1.0."* `2.2.x` is the fixed line; pin the latest,
`2.2.14`.

**Values compatibility — verified, no values migration needed.** Every value
this HelmRelease sets still exists at chart `2.2.14`
(`values.yaml @ chart-v2.2.14`): `fullnameOverride`,
`reloader.readOnlyRootFileSystem`, `reloader.podMonitor.enabled`,
`reloader.resources`. Chart 2.x adds new *optional* knobs we don't need
(`reloader.reloadStrategy` default unchanged, `reloader.enableHA`,
`reloader.namespaceSelector`, `reloader.matchLabels`). RBAC (ServiceAccount +
ClusterRole/Binding `reloader-role`) is chart-managed and Flux/Helm apply it
automatically — no manual RBAC step.

Not a false-positive hold: a chart major that rewrites an immutable selector on
a cluster-wide controller genuinely needs the deliberate delete-recreate below.

## 2. Pre-checks

Run from repo root (`cd /Users/mu/code/cberg-home-nextgen`). All must pass.

```bash
# 2.1 Confirm current state is the expected chart 1.3.0 / app v1.3.0
mise exec -- kubectl get helmrelease -n kube-system reloader \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} chart={.status.history[0].chartVersion} app={.status.history[0].appVersion}{"\n"}'
# Expected: True chart=1.3.0 app=v1.3.0

# 2.2 Capture the OLD immutable selector (so rollback/verify can compare)
mise exec -- kubectl get deploy -n kube-system reloader \
  -o jsonpath='{.spec.selector.matchLabels}{"\n"}'
# Expected: {"app":"reloader","release":"reloader"}

# 2.3 reloader pod healthy, 0 restarts, single replica
mise exec -- kubectl get pods -n kube-system -l app=reloader -o wide
# Expected: 1 Running pod, image ghcr.io/stakater/reloader:v1.3.0

# 2.4 No in-flight Flux reconcile
mise exec -- flux get kustomizations -A | grep -vE "True|^NAMESPACE"   # empty
mise exec -- flux get helmreleases   -A | grep -vE "True|^NAMESPACE"   # empty

# 2.5 Baseline: nothing is mid-rollout that reloader must finish driving
#     (avoid deleting reloader while a Secret/ConfigMap-triggered roll is in flight)
mise exec -- kubectl get pods -A | grep -vE "Running|Completed|^NAMESPACE" \
  || echo "all pods Running/Completed"

# 2.6 Zero firing alerts (Watchdog/InfoInhibitor excluded)
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &>/dev/null &
sleep 2
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)[\"data\"][\"alerts\"] if x[\"state\"]==\"firing\" and x[\"labels\"][\"alertname\"] not in (\"Watchdog\",\"InfoInhibitor\")]
print(f\"Firing: {len(a)}\")"
kill %1 2>/dev/null'
# Expected: Firing: 0
```

**Go criteria:** HR Ready on chart 1.3.0, old selector captured, reloader pod
healthy, all Flux Ready, no workloads mid-rollout, 0 firing alerts.

## 3. Steps

GitOps first; the delete-recreate is the one manual step the immutable-selector
change forces (application-update.md §4 Example B pattern). The
maintenance-window-agent delegates the git + kubectl actions to `cberg-agent`.

### 3a. (optional) silence + active-update marker

reloader restarts don't normally page, but suppress kube-system pod-churn noise
for the delete-recreate:

```bash
runbooks/update-marker.sh add reloader kube-system 1 "chart 1.3.0->2.2.14 upgrade"
```

### 3b. Land the chart bump in git

Edit `kubernetes/apps/kube-system/reloader/app/helmrelease.yaml`:

```yaml
  chart:
    spec:
      chart: reloader
      version: 2.2.14        # was 1.3.0
```

Leave the `values:` block unchanged — all four paths
(`fullnameOverride`, `reloader.readOnlyRootFileSystem`, `reloader.podMonitor`,
`reloader.resources`) are valid at 2.2.14.

```bash
cd /Users/mu/code/cberg-home-nextgen
git add kubernetes/apps/kube-system/reloader/app/helmrelease.yaml
git commit -m "feat(reloader): update chart ( 1.3.0 → 2.2.14 )"
git push
```

### 3c. Let Flux reconcile — it WILL fail on the immutable selector

```bash
mise exec -- flux reconcile helmrelease -n kube-system reloader --with-source
# EXPECTED to fail. Confirm the reason is the immutable selector:
mise exec -- kubectl get helmrelease -n kube-system reloader \
  -o jsonpath='{.status.conditions[?(@.type=="Released")].message}{"\n"}'
# Expect a message like:
#   Deployment.apps "reloader" is invalid: spec.selector: Invalid value: ...:
#   field is immutable   (or "selector does not match template labels")
```

If, instead, it reconciled Ready first try (upstream may have softened this),
skip 3d and go to Verification.

### 3d. Delete the reloader Deployment so Helm recreates it

```bash
# Stateless controller, no PVC — safe to delete. Helm re-creates it with the
# new 2.x selector on the next reconcile. This is the ~30-60s reload-gap window.
mise exec -- kubectl delete deployment -n kube-system reloader

mise exec -- flux reconcile helmrelease -n kube-system reloader --force
```

### 3e. Restore marker on success

```bash
runbooks/update-marker.sh clear reloader
```

## 4. Verification

```bash
# 4.1 HelmRelease Ready on the new chart + app version
mise exec -- kubectl get helmrelease -n kube-system reloader \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} chart={.status.history[0].chartVersion} app={.status.history[0].appVersion}{"\n"}'
# Expected: True chart=2.2.14 app=v1.4.19

# 4.2 New selector applied, pod healthy on the new image, 0 restarts
mise exec -- kubectl get deploy -n kube-system reloader -o jsonpath='{.spec.selector.matchLabels}{"\n"}'
# Expected: the new app.kubernetes.io/* scheme (NOT the old {"app","release"})
mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/name=reloader -o wide
# Expected: 1 Running pod, image ghcr.io/stakater/reloader:v1.4.19, restarts 0

# 4.3 reloader is actually watching (log line on boot)
mise exec -- kubectl logs -n kube-system deploy/reloader --tail=20 | grep -iE "started|watching|reloader"

# 4.4 FUNCTIONAL TEST — prove reloader still rolls a workload on a ConfigMap
#     change (this is the whole point; a "Ready" HR is not proof it works).
mise exec -- kubectl create configmap reloader-selftest -n default \
  --from-literal=v=1 --dry-run=client -o yaml | mise exec -- kubectl apply -f -
cat <<'EOF' | mise exec -- kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: reloader-selftest
  namespace: default
  annotations:
    configmap.reloader.stakater.com/reload: "reloader-selftest"
spec:
  replicas: 1
  selector: { matchLabels: { app: reloader-selftest } }
  template:
    metadata: { labels: { app: reloader-selftest } }
    spec:
      containers:
        - name: pause
          image: registry.k8s.io/pause:3.10
          envFrom: [ { configMapRef: { name: reloader-selftest } } ]
EOF
mise exec -- kubectl rollout status deploy/reloader-selftest -n default --timeout=60s
REV1=$(mise exec -- kubectl get deploy reloader-selftest -n default -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}')

# mutate the configmap → reloader MUST trigger a new rollout revision
mise exec -- kubectl create configmap reloader-selftest -n default \
  --from-literal=v=2 --dry-run=client -o yaml | mise exec -- kubectl apply -f -
sleep 20
REV2=$(mise exec -- kubectl get deploy reloader-selftest -n default -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}')
echo "revision before=$REV1 after=$REV2"
# PASS: after > before (reloader rolled the deployment). FAIL: unchanged.

# cleanup the self-test
mise exec -- kubectl delete deploy reloader-selftest -n default
mise exec -- kubectl delete configmap reloader-selftest -n default

# 4.5 No new firing alerts, no crashlooping kube-system pods
mise exec -- kubectl get pods -n kube-system | grep -vE "Running|Completed|^NAME" \
  || echo "all kube-system pods Running/Completed"
```

**Success = HR Ready chart=2.2.14 app=v1.4.19, reloader pod Running on
`:v1.4.19` with 0 restarts, and the 4.4 functional test shows the revision
incremented (reloader rolled the workload on a ConfigMap change).**

## 5. Rollback

reloader is stateless — rollback is a git revert plus the same delete-recreate
in reverse (the selector reverts to the 1.x scheme, which is also immutable).

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <upgrade-commit-sha>     # restores version: 1.3.0
git push

mise exec -- flux reconcile helmrelease -n kube-system reloader --with-source
# The downgrade hits the SAME immutable-selector wall in reverse — recreate:
mise exec -- kubectl delete deployment -n kube-system reloader
mise exec -- flux reconcile helmrelease -n kube-system reloader --force
```

**Confirm restored:** HR Ready `chart=1.3.0 app=v1.3.0` (4.1), selector back to
`{"app":"reloader","release":"reloader"}` (2.2), pod Running on `:v1.3.0`, and
re-run the 4.4 functional test to confirm config-reload still works on the old
version.

> If `helm` wedges `pending-upgrade` during either direction (crash mid-`--wait`):
> `mise exec -- helm history reloader -n kube-system` → find the last
> `deployed` revision → `mise exec -- helm rollback reloader <rev> -n kube-system --wait=false`
> → then `flux reconcile helmrelease -n kube-system reloader --force`
> (application-update.md §7).

## 6. Interference notes

- **No-reboot window (tue/thu).** `needs_reboot: false`; risk weight 2. Fits a
  1h Tue/Thu slot with room to spare (~20 min).
- **reloader is cluster-wide shared infra — treat the recreate as a brief
  reload-blackout.** During Step 3d (delete → Helm recreate, ~30–60 s) there is
  no reloader running, so any ConfigMap/Secret change in that gap will NOT
  trigger its dependent workload to roll. 25 workloads across `databases`,
  `home-automation`, `office`, `ai`, `network`, and `monitoring` annotate
  reloader. Nothing *breaks* (running pods keep running; the missed change is
  just not auto-rolled) — but:
  - **Do NOT co-schedule** this plan in the same window as any plan that relies
    on reloader auto-rolling a workload after a Secret/ConfigMap change (e.g. a
    secret rotation that expects the consuming pods to pick it up automatically).
    Sequence reloader FIRST, verify the 4.4 functional test passes, THEN run any
    such plan — or defer this one. That's why `shared: [reloader]` is set even
    though no currently-planned update overlaps its `touches`.
  - If a critical config change must land during the same window, apply it
    *after* 4.4 passes, or manually `kubectl rollout restart` the affected
    workload.
- **The delete-recreate is mandatory, not optional.** The immutable-selector
  failure (3c) is expected; do not treat the first failed reconcile as an abort
  signal — proceed to 3d. Only abort if 3d + `--force` still won't bring the HR
  Ready, or if the 4.4 functional test fails after a healthy-looking pod.
- **No storage / no ingress / no CNI / no DB touched.** Blast radius is confined
  to the reloader controller itself and, transiently, the config-reload feature
  cluster-wide. No PVC, no node reboot, no shared datastore.
- **cberg-agent does the GitOps + kubectl;** the operator/window agent watches
  the expected-failure → delete → recreate handoff and gates on the functional
  test before declaring success.
