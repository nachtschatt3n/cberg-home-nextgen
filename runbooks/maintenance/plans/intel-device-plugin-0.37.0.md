---
plan_id: intel-device-plugin-0.37.0
component: intel-device-plugin          # three lockstep HelmReleases in kube-system:
                                        # intel-device-plugin-operator, -gpu, -npu
pr: null                                # no Renovate PR; dispatched by the nightly window
                                        # 2026-09-25 Step 0.5 (coverage needs_plan:
                                        # "0.x release-line move — at major 0 the minor IS
                                        # the breaking axis; needs an assessed window plan")
kind: chart
current: "0.36.0"                       # all three charts AND all three images, live
                                        # (re-measured 2026-09-25, see premises)
target: "0.37.0"                        # charts published 2026-09-21 (intel helm index);
                                        # images intel/intel-{deviceplugin-operator,gpu-plugin,
                                        # npu-plugin}:0.37.0 on Docker Hub since 2026-09-16
update_type: minor
risk: medium                            # NOT low, for two measured reasons (§1): (a) a bare
                                        # version bump FAILS — the operator HR's JSON-patch
                                        # post-renderer tests /webhooks/8/name, and 0.37.0
                                        # renders only 7 webhooks; (b) every GPU/NPU consumer
                                        # in the cluster (7 pods, incl. frigate NVR) depends on
                                        # the plugin DaemonSets re-registering. Running pods
                                        # keep their devices; only NEW scheduling is at risk.
est_duration_min: 30                    # edit+commit 5, operator+2 DS rolls (maxUnavailable 1,
                                        # 3 nodes each) ~8, verification incl. two probe pods ~12,
                                        # slack 5
needs_reboot: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/intel-device-plugin-operator
    - helmrelease/intel-device-plugin-gpu
    - helmrelease/intel-device-plugin-npu
    - deployment/inteldeviceplugins-controller-manager
    - daemonset/intel-gpu-plugin-intel-gpu-plugin
    - daemonset/intel-npu-plugin-intel-npu-plugin
    - gpudeviceplugin/intel-gpu-plugin
    - npudeviceplugin/intel-npu-plugin
    - mutatingwebhookconfiguration/inteldeviceplugins-mutating-webhook-configuration
    - validatingwebhookconfiguration/inteldeviceplugins-validating-webhook-configuration
    - "crd/*.deviceplugin.intel.com (CreateReplace)"
  shared:
    - igpu-i915                         # gpu.intel.com/i915 on all 3 nodes: frigate, scrypted,
                                        # immich-server, immich-machine-learning, jellyfin,
                                        # makemkv, plex
    - npu-accel                         # npu.intel.com/accel on all 3 nodes: frigate
    - admission-webhooks                # the mutating webhook config is consulted on pod
                                        # CREATE cluster-wide (failurePolicy Ignore)
depends_on: []
conflicts_with:
  - talos-1.14.1                        # node roll re-registers device plugins and swaps the
                                        # i915/npu kernel modules; a failure could not be
                                        # attributed, and a node drain during this plan's DS
                                        # roll would evict consumers onto nodes whose plugin is
                                        # mid-restart (0 allocatable)
  - jellyfin-12.1                       # i915 consumer; its verification (HW transcode) would
                                        # read this plan's DS roll as a jellyfin regression
  - helm-drift-detection                # its P2 §3.2.0 hand-re-applies GpuDevicePlugin and
                                        # rolls the same DaemonSet; its analysis is pinned to
                                        # intel-device-plugin-gpu Helm rev 5 / chart 0.36.0,
                                        # which this plan moves (see §6)
  - flux-oci-chart-sources              # moves the `intel` HelmRepository to OCI and its matrix
                                        # asserts "0.36.0 (all 3)"; same three HRs
  - kube-prometheus-stack-91.4.1        # §4 reads kube-state-metrics through this Prometheus
exclusive: false
autonomy_override: human-gated          # RESTRICTS only. Derived class was AUTO-NIGHT (igpu-i915/
                                        # npu-accel are not in the shared-infra floor), but the
                                        # frigate NVR dependency and the §4.5 probe pod need an
                                        # operator-present slot (§6).
security_ref: F-cc5b464c                # image-currency security rows exist for all three
                                        # images (F-cc5b464c gpu, F-bb3a90aa npu, F-97cb1e88
                                        # operator). Detail stays on the finding records.
capability_change: false                # same devices (gpu, npu), same sharedDevNum, same
                                        # resource names; removed code paths (FPGA, DLB) were
                                        # never enabled here
rollback_class: git-revert              # but TWO-PHASE — see §5 (operator webhook rejects a
                                        # plugin image older than its own version)
finding_refs: [F-b6b925de, F-e99826d8, F-4aebf29c, F-cc5b464c, F-bb3a90aa, F-97cb1e88]
status: vetted   # 2026-09-26 plan-reviewer needs-fix -> B1-B6 + N1-N3 applied verbatim (fixed state dir, file-carried rollback sha, pod-level phase-A gate, exact webhook set, autonomy_override human-gated, optional 4.8 CRD removal gated in code)
window: "now:2026-09-26"   # ON-DEMAND NOW run 2026-09-26 (run-now.py stamp; was None)
premises:
  - id: operator-chart-0360
    why: "`current:` claims chart 0.36.0 on the operator HR; if it moved, this plan is stale."
    run: kubectl get helmrelease -n kube-system intel-device-plugin-operator -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "0.36.0"
  - id: gpu-chart-0360
    why: "Same, GPU plugin HR."
    run: kubectl get helmrelease -n kube-system intel-device-plugin-gpu -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "0.36.0"
  - id: npu-chart-0360
    why: "Same, NPU plugin HR."
    run: kubectl get helmrelease -n kube-system intel-device-plugin-npu -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "0.36.0"
  - id: operator-image-0360
    why: >-
      The live operator must still be 0.36.0. If it were already 0.37.0 its
      auto-upgrade (UpgradeImages, ImageMinVersion 0.37.0) would already have
      moved the plugin CR images, and §5's rollback ordering would start from
      a different state.
    run: kubectl get deploy -n kube-system inteldeviceplugins-controller-manager -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "intel/intel-deviceplugin-operator:0.36.0"
  - id: git-postrender-webhook-patch-present
    why: >-
      §3's edit removes the index-based MutatingWebhookConfiguration patch. If
      someone already removed or changed it, the edit script's exact-match
      asserts fail — re-derive §3 instead of forcing it.
    run: "git show HEAD:kubernetes/apps/kube-system/intel-device-plugin/app/helmrelease.yaml | grep -c 'value: fpga.mutator.webhooks.intel.com'"
    expect_exact: "1"
  - id: live-webhooks-already-trimmed
    why: >-
      The 0.36.0 post-render patch is in effect: the live mutating config
      carries 8 entries and no pod-scoped *.mutator entry. This is the baseline
      §4.4 compares against.
    run: kubectl get mutatingwebhookconfigurations inteldeviceplugins-mutating-webhook-configuration -o jsonpath='{.webhooks[*].name}' | tr ' ' '\n' | grep -c -i 'mutator.webhooks'
    expect_exact: "0"
  - id: all-three-hr-ready
    why: "Do not stack a chart bump on an already-failing release."
    run: kubectl get helmrelease -n kube-system intel-device-plugin-operator intel-device-plugin-gpu intel-device-plugin-npu -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True True True"
  - id: gpu-ds-ready-3
    why: "GPU plugin must be registered on all 3 nodes before the roll, or §4's per-node comparison has no baseline."
    run: kubectl get ds -n kube-system intel-gpu-plugin-intel-gpu-plugin -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled}'
    expect_exact: "3/3"
  - id: npu-ds-ready-3
    why: "Same for the NPU plugin."
    run: kubectl get ds -n kube-system intel-npu-plugin-intel-npu-plugin -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled}'
    expect_exact: "3/3"
  - id: i915-allocatable-5-per-node
    why: "Baseline for the §4 contents assertion: sharedDevNum 5 on all three nodes."
    run: kubectl get nodes -o jsonpath='{.items[*].status.allocatable.gpu\.intel\.com/i915}'
    expect_exact: "5 5 5"
  - id: npu-allocatable-1-per-node
    why: "Baseline for the §4 contents assertion: one NPU per node."
    run: kubectl get nodes -o jsonpath='{.items[*].status.allocatable.npu\.intel\.com/accel}'
    expect_exact: "1 1 1"
  - id: probe-node-has-free-npu
    why: >-
      §4.5's probe pod claims npu.intel.com/accel on k8s-nuc14-01. NPU is
      sharedDevNum 1, so the node's NPU must be unclaimed (frigate, the only
      NPU consumer, runs on nuc14-02 today). If this reads 1, pick the node
      with no NPU claim and edit the probe's nodeName. (Control measured
      2026-09-25: the same command against k8s-nuc14-02 reads 1 — frigate.)
    run: kubectl get pods -A --field-selector spec.nodeName=k8s-nuc14-01,status.phase=Running -o jsonpath='{range .items[*].spec.containers[*]}{.resources.limits}{"\n"}{end}' | grep -c 'npu.intel.com/accel'
    expect_exact: "0"
  - id: probe-node-has-free-i915
    why: "Probe also claims one i915 share on nuc14-01; at most 4 of 5 may be used."
    run: kubectl get pods -A --field-selector spec.nodeName=k8s-nuc14-01,status.phase=Running -o jsonpath='{range .items[*].spec.containers[*]}{.resources.limits}{"\n"}{end}' | grep -c 'gpu.intel.com/i915'
    expect_matches: "^[0-4]$"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/maintenance-windows.md
generated: "2026-09-25"
---

# intel-device-plugin 0.36.0 -> 0.37.0 (operator + gpu + npu, lockstep)

## 1. Summary & why held

Three Flux HelmReleases in `kube-system`, all from the `intel` HelmRepository
(`https://intel.github.io/helm-charts`), move 0.36.0 -> 0.37.0 together:

| HelmRelease | chart | workload |
|---|---|---|
| `intel-device-plugin-operator` | `intel-device-plugins-operator` | `deployment/inteldeviceplugins-controller-manager` + CRDs + webhooks |
| `intel-device-plugin-gpu` | `intel-device-plugins-gpu` | `GpuDevicePlugin/intel-gpu-plugin` -> `ds/intel-gpu-plugin-intel-gpu-plugin` |
| `intel-device-plugin-npu` (dir `vpu/`) | `intel-device-plugins-npu` | `NpuDevicePlugin/intel-npu-plugin` -> `ds/intel-npu-plugin-intel-npu-plugin` |

**Held because** coverage treats a 0.x minor as the breaking axis. The hold was
correct. Upstream release notes for v0.37.0 (GitHub release, 2026-09-16):

> *"DLB and FGPA plugins, and their collateral were removed from the project."*
> *"Operator: Increase plugin Pod memory limits (#2331)"*
> *"GPU: Allow changing which health severity is considered Unhealthy (#2318)"* / *"Add B-series NFD node labeling (#2332)"*

### 1.1 The breaking change that matters HERE: our own post-renderer

I pulled both chart versions and diffed them, then rendered the operator
chart with our values (`helm template`, 2026-09-25):

```
0.36.0 + current values: 10 mutating webhooks, index 8 = fpga.mutator.webhooks.intel.com, 9 = sgx.mutator.webhooks.intel.com
0.37.0 + current values:  7 mutating webhooks, index 5 = msgxdeviceplugin.kb.io, 6 = sgx.mutator.webhooks.intel.com (no index 8)
0.37.0 + manager.devices{gpu,npu}: 6 mutating webhooks, NO *.mutator.webhooks.intel.com entry
```

`app/helmrelease.yaml` carries a kustomize JSON-patch post-renderer that
`op: test`s `/webhooks/8/name == fpga.mutator…` and `/webhooks/9/name == sgx.mutator…`
before removing them (commit `6bcc1c83`). On 0.37.0 index 8 no longer exists
and the FPGA mutator is gone, so a **bare version bump fails post-render**. The
HR goes NotReady and stays on 0.36.0. That does not cause an outage, but the
auto-updater cannot land it and the window would record a failed plan.

Upstream 0.37.0 also added the gate the old comment said was missing: the sgx
pod mutator is now wrapped in
`{{- if or (empty $devices) (index $devices "sgx") }}` where
`$devices := .Values.manager.devices`. So the remedy comes from the chart
template itself, not from a SOP. Enable devices via `manager.devices` instead
of `controllerExtraArgs` and drop the webhook patch. The rendered args stay
exactly the same (`--devices=gpu`, `--devices=npu`; the template ranges the map
in sorted order, and I verified this by render). Both unwanted pod-scoped
mutators stay absent, which is the same end state the patch produced.

The metrics-Service bug (`targetPort: https`, where no port has that name) is
**still present in 0.37.0** (template lines 245-248), so the first post-render
patch stays.

### 1.2 The rest of the rendered delta (with our values)

- Operator: image `0.36.0 -> 0.37.0`. It drops RBAC and webhooks for
  `dlbdeviceplugins`, `fpgadeviceplugins`, `fpga.intel.com/*`. It drops the CRD
  files `deviceplugin.intel.com_{dlb,fpga}deviceplugins` and
  `fpga.intel.com_{acceleratorfunctions,fpgaregions}`. **Helm never deletes CRDs
  from `crds/`**, so those 4 CRDs stay in the cluster, unused and inert (none
  has any object). Removing them is the OPTIONAL, operator-approved step 4.8.
- GPU chart: only `spec.image` changes on the CR. The new B-series
  NodeFeatureRules are behind `nodeFeatureRule`, which is `false` here, so they
  do not render.
- NPU chart: only `spec.image`.

### 1.3 Operator behaviour that sets the ORDER (upstream source, tag v0.37.0)

- `pkg/controllers/reconciler.go:40`: `ImageMinVersion = "0.37.0"`.
  `UpgradeImages()` rewrites any CR `spec.image` whose semver tag is **lower**
  than that to `name:0.37.0`, then `r.Update()`s the CR. **So the moment
  operator 0.37.0 runs, it rolls both plugin DaemonSets to 0.37.0 on its own**,
  whatever the gpu/npu HRs say. The gpu/npu HR bumps then just make git match
  the live state. They produce no second roll IF the operator lands first. dependsOn is
  satisfied by the still-Ready 0.36.0 operator HR, so a gpu/npu Kustomization can
  apply first: operator 0.36.0 then rolls the DS to image 0.37.0 and operator
  0.37.0 rolls it once more for its new memory limits (up to two ~1 min/node
  admission gaps per DaemonSet; running consumers unaffected).
- `pkg/apis/deviceplugin/v1/webhook_common.go` `validatePluginImage()`: the
  validating webhook **rejects any plugin image older than ImageMinVersion**
  (*"version … is too low. Should be at least …"*).
  - Going forward, order does not matter. Operator 0.36.0 accepts a 0.37.0
    plugin image, and operator 0.37.0 upgrades the images itself. One commit
    covering all three is safe, and HR `dependsOn` puts the operator first on a
    best-effort basis.
  - **Rollback is order-sensitive.** While operator 0.37.0 is running, reverting
    the gpu/npu HRs to chart 0.36.0 (image 0.36.0) is **denied by admission**.
    See §5.

### 1.4 Blast radius (measured live 2026-09-25)

Allocatable per node, all three nodes (`k8s-nuc14-01..03`):
`gpu.intel.com/i915=5`, `gpu.intel.com/monitoring=1`, `npu.intel.com/accel=1`.
Consumers:

| ns | pod | resources | node |
|---|---|---|---|
| home-automation | frigate | i915 + npu accel | nuc14-02 |
| home-automation | scrypted | i915 | nuc14-03 |
| media | immich-server | i915 | nuc14-01 |
| media | immich-machine-learning | i915 | nuc14-03 |
| media | jellyfin | i915 | nuc14-03 |
| media | makemkv | i915 | nuc14-03 |
| media | plex (sts) | i915 | nuc14-01 |

No Ollama in-cluster consumer: Ollama runs on the Mac mini. Both plugin
DaemonSets use `RollingUpdate maxUnavailable: 1, maxSurge: 0`. While a node's
plugin pod restarts, kubelet keeps existing device assignments, so running
containers keep `/dev/dri` and `/dev/accel`. But **a consumer pod created on
that node during the gap cannot be admitted** (allocatable reads 0 until the
new plugin re-registers). nuc14-03 already carries 4 of its 5 i915 shares.
Frigate (the NVR) is the one consumer where a failed re-registration plus a
crash would be user-visible: cameras stop recording. That is why §4 proves a
*fresh* allocation of both resources, not just DS readiness.

## 2. Pre-checks

Run from repo root on the Mac mini (zsh).

```bash
cd /Users/mu/code/cberg-home-nextgen
mkdir -p /private/tmp/claude-501/intel-037    # fixed scratch dir: agent Bash calls share no shell variables
# 2.1 premises (all must PASS)
.venv/bin/python3 runbooks/plan-premises.py intel-device-plugin-0.37.0

# 2.2 flux healthy for the three HRs and their Kustomizations
flux get helmreleases -n kube-system | grep -i intel
flux get kustomizations -n kube-system | grep -i intel      # expect 3 x Ready True

# 2.3 no GPU/NPU consumer mid-rollout (a consumer Pending now would be misattributed)
kubectl get pods -A -o json | jq -r '.items[] | select(.status.phase!="Running" and .status.phase!="Succeeded") | select([.spec.containers[].resources.limits // {} | keys[]] | any(test("intel.com"))) | .metadata.namespace+"/"+.metadata.name+" "+.status.phase'
#   expect: empty output

# 2.4 record the consumer baseline for §4.6
kubectl get pods -A -o json | jq -r '.items[] | select([.spec.containers[].resources.limits // {} | keys[]] | any(test("intel.com"))) | .metadata.namespace+"/"+.metadata.name+" "+.status.phase+" "+(.status.containerStatuses[0].restartCount|tostring)' | sort > "/private/tmp/claude-501/intel-037/intel-consumers-before.txt"
wc -l < "/private/tmp/claude-501/intel-037/intel-consumers-before.txt"    # expect 7 (1.4); a different number -> re-derive 1.4 first

# 2.5 NEGATIVE CONTROL for §4.5, run BEFORE the change: an UNPRIVILEGED pod with
#     NO device request must NOT see /dev/dri. This proves the probe in 4.5 can fail
#     (the device nodes it lists come from the plugin allocation, not the image/host).
kubectl run intel-dev-negctl --rm -i --restart=Never -n kube-system \
  --image=busybox:1.37.0 --pod-running-timeout=120s \
  --overrides='{"apiVersion":"v1","spec":{"nodeName":"k8s-nuc14-01","containers":[{"name":"intel-dev-negctl","image":"busybox:1.37.0","command":["sh","-c","ls /dev/dri/ /dev/accel/ 2>&1; true"]}]}}' \
  2>&1 | tee "/private/tmp/claude-501/intel-037/intel-negctl.txt"
grep -c -i 'no such file' "/private/tmp/claude-501/intel-037/intel-negctl.txt"      # expect 2 (both paths absent)
kubectl delete pod -n kube-system intel-dev-negctl --ignore-not-found
```

If 2.5 prints `renderD128` or `accel0`, the probe design is invalid (the
namespace's pods see host devices anyway). STOP and redesign §4.5 before
continuing. Do not proceed on a probe that cannot fail.

## 3. Steps (GitOps, one commit)

3.1 Apply the edit with an exact-match script. Every replacement asserts that
it matched exactly once, so drift in the file aborts the step instead of
producing a wrong edit. I dry-tested it on a scratch copy of HEAD `4be4922d`.
It produced the diff in 3.2 and all three files parse as YAML.

```bash
cd /Users/mu/code/cberg-home-nextgen
cat > "/private/tmp/claude-501/intel-037/intel-037-edit.py" <<'EOF'
import pathlib, sys
root = pathlib.Path(sys.argv[1]) / "kubernetes/apps/kube-system/intel-device-plugin"
def sub1(text, old, new, path):
    n = text.count(old)
    assert n == 1, f"{path}: expected exactly 1 match for {old[:60]!r}, got {n}"
    return text.replace(old, new)
for rel in ("gpu/helmrelease.yaml", "vpu/helmrelease.yaml"):
    p = root / rel; t = p.read_text()
    p.write_text(sub1(t, "      version: 0.36.0\n", "      version: 0.37.0\n", rel))
p = root / "app/helmrelease.yaml"; t = p.read_text()
t = sub1(t, "      version: 0.36.0\n", "      version: 0.37.0\n", "app")
start = t.index("  #\n  # SECOND UPSTREAM CHART BUG:")
end = t.index("  postRenderers:\n")
t = t[:start] + (
    "  #\n"
    "  # (0.37.0) The former second post-render patch -- removing the\n"
    "  # fpga/sgx pod-mutator webhooks by index -- is gone: upstream 0.37.0\n"
    "  # deleted the FPGA plugin entirely and gates the sgx pod mutator on\n"
    "  # `manager.devices`, so enabling devices via `manager.devices` below\n"
    "  # renders neither entry. Re-check on every chart bump that\n"
    "  # `kubectl get mutatingwebhookconfigurations\n"
    "  # inteldeviceplugins-mutating-webhook-configuration` lists no\n"
    "  # `*.mutator.webhooks.intel.com` entry.\n"
) + t[end:]
wh = t.index("          - target:\n              group: admissionregistration.k8s.io")
vals = t.index("  values:\n")
t = t[:wh] + t[vals:]
t = sub1(t,
    "  values:\n    controllerExtraArgs: |\n      - --devices=gpu\n      - --devices=npu\n",
    "  values:\n    # Renders exactly `--devices=gpu --devices=npu` (same args as the old\n"
    "    # controllerExtraArgs) AND, since chart 0.37.0, suppresses the sgx pod\n"
    "    # mutator webhook. Do not also set controllerExtraArgs -- the flags\n"
    "    # would be passed twice.\n"
    "    manager:\n      devices:\n        gpu: true\n        npu: true\n", "app")
p.write_text(t)
print("ok")
EOF
python3 "/private/tmp/claude-501/intel-037/intel-037-edit.py" .          # must print: ok
git diff --stat -- kubernetes/apps/kube-system/intel-device-plugin
#   expect exactly: app/helmrelease.yaml | ~50 +++---, gpu/helmrelease.yaml | 2 +-, vpu/helmrelease.yaml | 2 +-
```

3.2 Expected diff, abridged. This is the output of the scratch dry-test.

```diff
-      version: 0.36.0            (x3: app/, gpu/, vpu/)
+      version: 0.37.0
-  # SECOND UPSTREAM CHART BUG: ... (29 comment lines)
+  # (0.37.0) The former second post-render patch ... (8 comment lines)
-          - target:
-              group: admissionregistration.k8s.io
-              ... MutatingWebhookConfiguration test/test/remove/remove (16 lines)
-    controllerExtraArgs: |
-      - --devices=gpu
-      - --devices=npu
+    manager:
+      devices:
+        gpu: true
+        npu: true
```

The Service `targetPort: 8443` post-render patch stays untouched.

3.3 Render-check the new operator values offline before pushing. This catches
a typo in `manager.devices`.

```bash
D=$(mktemp -d); helm pull intel-device-plugins-operator --repo https://intel.github.io/helm-charts --version 0.37.0 --untar --untardir "$D" \
 || (curl -sL https://github.com/intel/helm-charts/releases/download/intel-device-plugins-operator-0.37.0/intel-device-plugins-operator-0.37.0.tgz | tar xz -C "$D")
yq '.spec.values' kubernetes/apps/kube-system/intel-device-plugin/app/helmrelease.yaml > "$D/v.yaml"
helm template intel-device-plugin-operator "$D/intel-device-plugins-operator" -n kube-system -f "$D/v.yaml" \
 | python3 -c "
import sys,yaml
for d in yaml.safe_load_all(sys.stdin):
  if d and d.get('kind')=='Deployment': print('ARGS',[a for a in d['spec']['template']['spec']['containers'][0]['args'] if 'devices' in a])
  if d and d.get('kind')=='MutatingWebhookConfiguration': print('MUTATORS',[w['name'] for w in d['webhooks'] if 'mutator.webhooks' in w['name']])"
#   expect: ARGS ['--devices=gpu', '--devices=npu']   and   MUTATORS []
```

(`helm pull --repo` failed on this Mac on 2026-09-25 with a helm cache error.
The curl fallback is the path that worked.)

3.4 Commit ONLY these three files and push:

```bash
M=/private/tmp/claude-501/intel-037/msg-intel-device-plugin-0.37.0-$(date +%s).txt
cat > "$M" <<'EOF'
feat(intel-device-plugin): 0.36.0 -> 0.37.0 (operator, gpu, npu lockstep)

0.37.0 removed the FPGA plugin, so the index-based JSON-patch that stripped
fpga/sgx pod mutators (tests /webhooks/8/name) would fail post-render.
Enable devices via manager.devices instead of controllerExtraArgs: same
--devices=gpu --devices=npu args, and 0.37.0 now gates the sgx pod mutator
on it, so neither mutator renders. Metrics Service targetPort patch kept
(bug still present upstream).

Plan: runbooks/maintenance/plans/intel-device-plugin-0.37.0.md
EOF
git commit --only \
  kubernetes/apps/kube-system/intel-device-plugin/app/helmrelease.yaml \
  kubernetes/apps/kube-system/intel-device-plugin/gpu/helmrelease.yaml \
  kubernetes/apps/kube-system/intel-device-plugin/vpu/helmrelease.yaml \
  -F "$M"
git log -1 --format=%s        # must be the subject above (EDITMSG race guard)
git show --stat HEAD          # exactly the 3 files
git log -1 --format=%H -- kubernetes/apps/kube-system/intel-device-plugin/app/helmrelease.yaml > /private/tmp/claude-501/intel-037/bad-sha.txt
cat /private/tmp/claude-501/intel-037/bad-sha.txt   # the 3.4 commit sha; §5 reads it from this file
git push
```

Let the Flux webhook reconcile. Do not run a manual `flux reconcile` unless
nothing has moved after 10 minutes. `application-update.md` allows a reconcile
of the Kustomizations in that case.

3.5 Watch the roll. The operator goes first, and it rolls both DaemonSets itself (§1.3).

```bash
kubectl rollout status -n kube-system deploy/inteldeviceplugins-controller-manager --timeout=180s
kubectl rollout status -n kube-system ds/intel-gpu-plugin-intel-gpu-plugin --timeout=300s
kubectl rollout status -n kube-system ds/intel-npu-plugin-intel-npu-plugin --timeout=300s
```

`rollout status` can green-light the OLD generation. §4.2 checks the live
images; treat this step as progress only.

## 4. Verification

4.1 HRs on 0.37.0 and Ready:

```bash
kubectl get helmrelease -n kube-system intel-device-plugin-operator intel-device-plugin-gpu intel-device-plugin-npu \
  -o jsonpath='{range .items[*]}{.metadata.name} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
# expect: 3 lines "... 0.37.0 True"
```

Failure it guards against: the post-render failure from §1.1. It shows as
`Ready False` with `lastAttemptedRevision 0.37.0` and a message containing
`test operation failed` / `post-render`.

4.2 Live images, read from the pods themselves and not from the specs:

```bash
kubectl get pods -n kube-system -o json | jq -r '.items[] | select(.metadata.name|test("^(inteldeviceplugins-controller-manager|intel-gpu-plugin-intel-gpu-plugin|intel-npu-plugin-intel-npu-plugin)")) | .metadata.name+" "+.spec.nodeName+" "+.status.containerStatuses[0].image+" ready="+(.status.containerStatuses[0].ready|tostring)'
# expect: 1 operator + 3 gpu + 3 npu lines, ALL image ...:0.37.0, ALL ready=true
kubectl get gpudeviceplugin intel-gpu-plugin -o jsonpath='{.spec.image} {.status.numberReady}/{.status.desiredNumberScheduled}{"\n"}'   # intel/intel-gpu-plugin:0.37.0 3/3
kubectl get npudeviceplugin intel-npu-plugin -o jsonpath='{.spec.image} {.status.numberReady}/{.status.desiredNumberScheduled}{"\n"}'   # intel/intel-npu-plugin:0.37.0 3/3
```

4.3 **CONTENTS ASSERTION: every node still advertises the same device
capacity**. Measured two ways: from the node objects, and from the
kube-state-metrics series. Compare against the premise baseline (`5 5 5`,
`1 1 1`, monitoring `1 1 1`).

```bash
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name} i915={.status.allocatable.gpu\.intel\.com/i915} mon={.status.allocatable.gpu\.intel\.com/monitoring} npu={.status.allocatable.npu\.intel\.com/accel}{"\n"}{end}'
# expect 3 lines: i915=5 mon=1 npu=1. An EMPTY value or 0 = plugin did not re-register on that node -> FAIL

kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s --get http://localhost:19090/api/v1/query \
  --data-urlencode 'query=sum by (node, resource) (kube_node_status_allocatable{resource=~"gpu_intel_com_i915|npu_intel_com_accel"})' \
 | python3 -c "
import sys,json
r=json.load(sys.stdin)['data']['result']
got={(x['metric']['node'],x['metric']['resource']):float(x['value'][1]) for x in r}
want={(n,'gpu_intel_com_i915'):5.0 for n in ('k8s-nuc14-01','k8s-nuc14-02','k8s-nuc14-03')}
want.update({(n,'npu_intel_com_accel'):1.0 for n in ('k8s-nuc14-01','k8s-nuc14-02','k8s-nuc14-03')})
assert len(r)>0, 'EMPTY RESULT - instrument blind, not a pass'
bad={k:(got.get(k),v) for k,v in want.items() if got.get(k)!=v}
print('ALLOCATABLE_OK' if not bad else 'ALLOCATABLE_FAIL '+str(bad))"
kill $PF 2>/dev/null
```

CONTROL: metric kube_node_status_allocatable — per-node `resource="gpu_intel_com_i915"` must be 5 and `resource="npu_intel_com_accel"` must be 1 on all 3 nodes. Series measured live 2026-09-25 (6 series present). An empty result is an explicit assertion failure, not a pass.

This gate can fail. When a device plugin stops advertising, kubelet reports
the extended resource at 0 in allocatable, and kube-state-metrics reports that
0. The node-object read prints an empty value or `0`.

4.4 **CONTENTS ASSERTION: the admission surface is what we intended.** No
pod-scoped mutator is present, and the gpu/npu CR webhooks are present:

```bash
kubectl get mutatingwebhookconfigurations inteldeviceplugins-mutating-webhook-configuration -o jsonpath='{.webhooks[*].name}' | tr ' ' '\n'
# expect exactly: mdsadeviceplugin.kb.io mgpudeviceplugin.kb.io miaadeviceplugin.kb.io mnpudeviceplugin.kb.io mqatdeviceplugin.kb.io msgxdeviceplugin.kb.io
kubectl get mutatingwebhookconfigurations inteldeviceplugins-mutating-webhook-configuration -o jsonpath='{.webhooks[*].name}' | python3 -c "
import sys
got=sorted(sys.stdin.read().split())
want=sorted('mdsadeviceplugin.kb.io mgpudeviceplugin.kb.io miaadeviceplugin.kb.io mnpudeviceplugin.kb.io mqatdeviceplugin.kb.io msgxdeviceplugin.kb.io'.split())
print('WEBHOOKS_OK' if got==want else 'WEBHOOKS_FAIL got=%s' % got)"
# expect WEBHOOKS_OK. Set EQUALITY, not an absence count: it fails on sgx.mutator returning,
# on a leftover mdlb/mfpga entry, AND on a wrong object name (empty set). Demonstrated failure:
# the identical command read WEBHOOKS_FAIL (8 names incl. mdlb/mfpga) against the live 0.36.0
# config on 2026-09-26, and WEBHOOKS_OK against the offline 0.37.0 render with the new values.
kubectl get deploy -n kube-system inteldeviceplugins-controller-manager -o jsonpath='{.spec.template.spec.containers[0].args}'
# expect --devices=gpu and --devices=npu, each exactly ONCE
kubectl get endpointslices -n kube-system -l kubernetes.io/service-name=inteldeviceplugins-controller-manager-metrics-service -o jsonpath='{.items[*].ports[*].port}'
# expect 8443 (the kept Service patch); empty = metrics Service regression
```

4.5 **CONTENTS ASSERTION: a NEW pod actually gets both devices.** This is the
property the upgrade could break while every object above looks healthy. An
unprivileged throwaway pod claims one i915 share and one NPU on nuc14-01 (free
capacity asserted by premises). It lists the device nodes the plugins injected.
Compare with the 2.5 negative control, which printed `No such file` for both
paths.

```bash
kubectl run intel-dev-probe --rm -i --restart=Never -n kube-system \
  --image=busybox:1.37.0 --pod-running-timeout=120s \
  --overrides='{"apiVersion":"v1","spec":{"nodeName":"k8s-nuc14-01","containers":[{"name":"intel-dev-probe","image":"busybox:1.37.0","command":["sh","-c","ls /dev/dri/ /dev/accel/ 2>&1; true"],"resources":{"limits":{"gpu.intel.com/i915":"1","npu.intel.com/accel":"1"}}}]}}' \
  2>&1 | tee "/private/tmp/claude-501/intel-037/intel-probe.txt"
grep -c -E '^renderD[0-9]+$' "/private/tmp/claude-501/intel-037/intel-probe.txt"   # expect 1
grep -c -E '^accel[0-9]+$'   "/private/tmp/claude-501/intel-037/intel-probe.txt"   # expect 1
grep -c -i 'no such file'    "/private/tmp/claude-501/intel-037/intel-probe.txt"   # expect 0
kubectl delete pod -n kube-system intel-dev-probe --ignore-not-found
```

What failure prints: if the plugin on nuc14-01 is not advertising, kubelet
admission rejects the `nodeName`-pinned pod (`UnexpectedAdmissionError` /
`OutOf…` in `kubectl get events -n kube-system`), and `kubectl run` reports
the pod failed. If allocation succeeds but device injection broke, the
`ls` prints `No such file` exactly as in 2.5. The server-side dry-run of this
exact manifest was accepted by admission on 2026-09-25.

Optionally repeat 4.5 on nuc14-03 with only the i915 limit (i915 only, since
the NPU check already passed on nuc14-01). That covers a second node and the
fullest one. Premise first: that node must have at most 4 i915 claims.

4.6 Consumers unharmed:

```bash
kubectl get pods -A -o json | jq -r '.items[] | select([.spec.containers[].resources.limits // {} | keys[]] | any(test("intel.com"))) | .metadata.namespace+"/"+.metadata.name+" "+.status.phase+" "+(.status.containerStatuses[0].restartCount|tostring)' | sort > "/private/tmp/claude-501/intel-037/intel-consumers-after.txt"
diff "/private/tmp/claude-501/intel-037/intel-consumers-before.txt" "/private/tmp/claude-501/intel-037/intel-consumers-after.txt" && echo CONSUMERS_UNCHANGED
```

Expect `CONSUMERS_UNCHANGED`: the same 7 pods, same names, Running, restart
counts unchanged. A consumer restart is not automatically this plan's fault,
but it must be explained before closing. A changed pod name means the pod was
recreated, so confirm it is Running and was admitted.

Frigate spot-check, because it is the only NPU consumer and the NVR:

```bash
kubectl logs -n home-automation deploy/frigate -c frigate --since=15m | grep -i -E 'openvino|npu|detector.*(error|fail)|no such device' | tail -20
# INFORMATIONAL ONLY, not a gate: an empty result is also what a never-matching grep prints
# (and frigate is not restarted by this plan). The gating consumer checks are 4.6 (frigate
# restartCount unchanged) and 4.5 (a fresh NPU allocation on a node).
```

CONTROL: metric kube_pod_container_resource_limits — the consumer set, read through kube-state-metrics (8 series measured live 2026-09-25: 7 i915 + 1 npu). This is a cross-check for 4.6 if the jq read is disputed.

4.7 Close-out: once 4.1-4.6 pass, `finding close` the three version rows
(`F-b6b925de`, `F-e99826d8`, `F-4aebf29c`) with the commit sha if they do not
auto-close on the next sweep. Leave the three security rows to the next
security-check re-scan: the re-scan decides them, not this plan. Delete this
plan file in the close-out commit. Expect F-695ff83e (webhook routes unreachable,
currently 12) to re-read 8 on the next sweep: the dlb+fpga validating/mutating
entries are gone, dsa/iaa/qat/sgx remain. That is this change, not a regression.

4.8 **OPTIONAL (operator-approved on the day): delete the 4 CRDs 0.37.0 no
longer ships.** Helm never deletes `crds/` objects and no Kustomization owns
them (live 2026-09-26: label `helm.toolkit.fluxcd.io/name=intel-device-plugin-operator`
only, no ownerReferences, no finalizers, 0 objects each), so there is no GitOps
path and this is an explicit plan step. Run ONLY after 4.1-4.6 passed.

```bash
kubectl get helmrelease -n kube-system intel-device-plugin-operator -o jsonpath='{.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # must read: 0.37.0 True, else STOP
kubectl get crd -o name | grep -c -E 'dlbdeviceplugins|fpgadeviceplugins|fpga\.intel\.com'   # BEFORE: expect 4
# ONE Bash call: the delete is GATED IN CODE on the check (4 x DELETE-OK on the retired CRDs
# AND a STOP on the in-use positive control gpudeviceplugins). Anything else -> no delete.
OK=0; CTRL=0
for c in dlbdeviceplugins.deviceplugin.intel.com fpgadeviceplugins.deviceplugin.intel.com acceleratorfunctions.fpga.intel.com fpgaregions.fpga.intel.com gpudeviceplugins.deviceplugin.intel.com; do
  out=$(kubectl get "$c" -A -o name 2>/dev/null); rc=$?
  lbl=$(kubectl get crd "$c" -o jsonpath='{.metadata.labels.helm\.toolkit\.fluxcd\.io/name}' 2>/dev/null)
  if [ $rc -ne 0 ] || [ -n "$out" ] || [ "$lbl" != intel-device-plugin-operator ]; then
    echo "STOP $c rc=$rc objs=[$out] owner=[$lbl]"; [ "$c" = gpudeviceplugins.deviceplugin.intel.com ] && CTRL=1
  else
    echo "DELETE-OK $c"; [ "$c" != gpudeviceplugins.deviceplugin.intel.com ] && OK=$((OK+1))
  fi
done
echo "retired_ok=$OK control_stop=$CTRL"
if [ "$OK" = 4 ] && [ "$CTRL" = 1 ]; then
  kubectl delete crd dlbdeviceplugins.deviceplugin.intel.com fpgadeviceplugins.deviceplugin.intel.com acceleratorfunctions.fpga.intel.com fpgaregions.fpga.intel.com
else
  echo "CRD DELETE SKIPPED (check not clean) - report, do not force"
fi
kubectl get crd -o name | grep -c -E 'dlbdeviceplugins|fpgadeviceplugins|fpga\.intel\.com'   # AFTER: expect 0 (read 4 above)
kubectl get crd -o name | grep -c -E '(gpu|npu)deviceplugins\.deviceplugin\.intel\.com'       # expect 2 (in-use CRDs untouched)
```

Rollback of 4.8: §5 phase A re-creates all four from the 0.36.0 chart's `crds/`.

## 5. Rollback (two-phase — ORDER IS MANDATORY)

Operator 0.37.0's validating webhook denies any plugin image below 0.37.0
(§1.3). A single `git revert` of the whole commit can race: the gpu/npu
Kustomizations may apply their 0.36.0 HRs while operator 0.37.0 is still
serving the webhook. That upgrade is then rejected (`version "0.36.0" is too
low`), and the HR sits in failed remediation. Revert in two commits:

**Phase A: operator only.**

```bash
cd /Users/mu/code/cberg-home-nextgen
BAD=$(cat /private/tmp/claude-501/intel-037/bad-sha.txt); echo "BAD=$BAD"   # must print the 3.4 sha; empty -> STOP, find it with: git log --oneline -3 -- kubernetes/apps/kube-system/intel-device-plugin/app/helmrelease.yaml
git checkout "$BAD"~1 -- kubernetes/apps/kube-system/intel-device-plugin/app/helmrelease.yaml
git commit --only kubernetes/apps/kube-system/intel-device-plugin/app/helmrelease.yaml \
  -m "revert(intel-device-plugin): operator back to 0.36.0 (phase A of plan rollback)"
git log -1 --format=%s; git show --stat HEAD; git push
# wait until ALL THREE hold (the third is the one that matters: phase B is denied
# while ANY 0.37.0 operator pod still serves the webhook Service):
kubectl get helmrelease -n kube-system intel-device-plugin-operator -o jsonpath='{.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # 0.36.0 True
kubectl get deploy -n kube-system inteldeviceplugins-controller-manager -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'                                     # ...:0.36.0
kubectl rollout status -n kube-system deploy/inteldeviceplugins-controller-manager --timeout=180s
kubectl get pods -n kube-system -o json | jq -r '.items[] | select(.metadata.name|startswith("inteldeviceplugins-controller-manager-")) | .status.containerStatuses[0].image' | sort | uniq -c
# must print exactly ONE line ending ':0.36.0' (e.g. "1 docker.io/intel/intel-deviceplugin-operator:0.36.0").
# Any line ending ':0.37.0' = the old webhook server is still up -> wait and re-run; do NOT start phase B.
```

Operator 0.36.0 leaves plugin images at 0.37.0 alone. `UpgradeImages` only
raises versions. So after phase A the plugins still run 0.37.0 under a 0.36.0
operator. That combination is valid. If the fault was the operator itself
(for example the webhook), you can stop here.

**Phase B: plugins** (only if the plugin images are the fault):

```bash
BAD=$(cat /private/tmp/claude-501/intel-037/bad-sha.txt); echo "BAD=$BAD"   # same sha as phase A; empty -> STOP
git checkout "$BAD"~1 -- kubernetes/apps/kube-system/intel-device-plugin/gpu/helmrelease.yaml kubernetes/apps/kube-system/intel-device-plugin/vpu/helmrelease.yaml
git commit --only kubernetes/apps/kube-system/intel-device-plugin/gpu/helmrelease.yaml kubernetes/apps/kube-system/intel-device-plugin/vpu/helmrelease.yaml \
  -m "revert(intel-device-plugin): gpu/npu plugins back to 0.36.0 (phase B of plan rollback)"
git log -1 --format=%s; git show --stat HEAD; git push
```

Helm's 3-way merge sets `spec.image` back to `:0.36.0` on both CRs (old
manifest 0.37.0, new 0.36.0). Operator 0.36.0 accepts that (min 0.36.0) and
rolls the DaemonSets.

**Confirm the cluster is back:** re-run the premises. `operator-chart-0360`,
`gpu-chart-0360`, `npu-chart-0360`, `operator-image-0360`,
`i915-allocatable-5-per-node` and `npu-allocatable-1-per-node` must pass.
`live-webhooks-already-trimmed` must read 0, because the restored index patch
applies again to the 0.36.0 render. Then re-run §4.5 with 0.36.0 expected.

Nothing in this plan is forward-only. There is no data or PVC, and CRDs are
CreateReplace in both directions; if 4.8 deleted the 4 retired CRDs, phase A
re-creates them from the 0.36.0 chart's `crds/` (CreateReplace creates missing
CRDs). They hold no objects, so nothing is lost.
Rolling back restores the 0.36.0 CRD schemas.

**If an HR is stuck after a failed forward attempt** (§1.1 failure mode, e.g.
the edit was skipped): the HR stays on revision 0.36.0 with Ready False.
Nothing in the cluster changed. Revert the commit (a single revert is safe in
this case, because the operator never moved), or fix forward with §3.

## 6. Interference notes

- **Shared device surface.** Seven pods across `media` and `home-automation`
  hold `gpu.intel.com/i915`, and frigate also holds `npu.intel.com/accel`
  (§1.4). Running pods are unaffected by the roll. During each node's roll
  (about a minute per node, 3 nodes, each DaemonSet in turn) **no new GPU/NPU
  pod can be admitted on that node**. Do not co-schedule anything that
  restarts those consumers: `jellyfin-12.1`, and any media/frigate/immich plan.
  `conflicts_with` carries the ones that exist today.
- **`talos-1.14.1`** (sun-attended 2026-09-27) rolls all nodes and changes
  kernel modules and extensions under the i915/NPU drivers. Its own plan notes
  that the NPU extension differs from the repo's Talos patch. Never the same
  window. Preferably run this plan first, in a separate window, so a Talos
  failure is not confounded with a plugin change.
- **`helm-drift-detection`**: its §1.2 analysis is pinned to
  `intel-device-plugin-gpu` Helm rev 5 / chart 0.36.0, and to the
  `GpuDevicePlugin` `spec.monitoringMode` drift. This plan does not fix that
  drift: 0.37.0 renders `monitoringMode: single` identically, so Helm's 3-way
  merge again sends no change. The rev number will move (rev 6), and so will
  line numbers in its stored-manifest citations. Whichever runs second must
  re-measure.
- **`flux-oci-chart-sources`** moves the `intel` HelmRepository to OCI and
  lists these three HRs at 0.36.0. Whichever runs second must retarget.
- **`kube-prometheus-stack-91.4.1`**: §4.3 reads kube-state-metrics through
  Prometheus. A Prometheus restart in the same window reads as an empty or
  stale result.
- **Cluster-wide admission.** The mutating config is consulted on pod CREATE
  across the cluster. After this change it contains only CRD-scoped entries,
  the same end state as today, but reached without the patch. The operator
  Deployment restarts once, and its webhooks are `failurePolicy: Fail` for
  device-plugin CRs only. No pod admission depends on it.
- **Stale CRDs** (`dlbdeviceplugins`, `fpgadeviceplugins`,
  `acceleratorfunctions.fpga.intel.com`, `fpgaregions.fpga.intel.com`) remain
  after the upgrade, inert, unless the optional step 4.8 (zero-CR pre-check with a
  positive control) removes them.
- **Repo correction (not done by this plan):** `runbooks/health-check.sh`
  ~L6780 describes the webhook set as "dlb/dsa/fpga/iaa/qat/sgx … 14" entries.
  After 0.37.0 it is dsa/gpu/iaa/npu/qat/sgx, 6 mutating. It is comment-only
  and does not change the check's logic, but should be refreshed in the
  close-out commit.
- Not reboot-capable and does not need it. Fits any attended window. Because
  of the frigate/NVR dependency, prefer an operator-present slot over the
  unattended nightly.
