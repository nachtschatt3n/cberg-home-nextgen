# SOP: Bitnami Subchart Resource Override via Flux postRenderer

> Description: Workaround for Bitnami subcharts that ignore explicit `resources` values when a `resourcesPreset` is active, hardcoding limits via the preset. Use a Flux HelmRelease postRenderer kustomize JSON patch to override the rendered StatefulSet or Deployment directly.
> Version: `2026.05.03`
> Last Updated: `2026-05-03`
> Owner: `Platform`

---

## Description

Some Bitnami subcharts (valkey, redis, postgresql, etc.) apply a built-in `resourcesPreset` (e.g. `micro`, `small`) that overrides the explicit `resources` block in Helm values. Setting `resourcesPreset: "none"` disables the preset in theory, but certain chart versions (confirmed: Bitnami valkey subchart v3.0.31 embedded in penpot 0.40.0) compute the resources at template render time and the live StatefulSet generation never increments — Helm sees no diff and makes no change.

The reliable fix is a Flux Kustomize postRenderer JSON patch that directly overwrites the resource fields on the rendered StatefulSet or Deployment after Helm renders the manifests.

---

## Overview

| Problem | Bitnami subchart `resourcesPreset` overrides `master.resources` |
|---------|----------------------------------------------------------------|
| Symptom | `kubectl get statefulset <name> -o jsonpath='{...resources}'` shows preset values (e.g. `cpu: 150m`) despite correct Helm values |
| Diagnosis | `helm get values <release> -n <ns>` shows values deployed; StatefulSet `generation=1` (never updated) |
| Fix | Flux postRenderer kustomize JSON patch on the StatefulSet |
| Pattern | Used for: penpot-valkey-primary (confirmed 2026-05-03) |

---

## Blueprints

N/A — no Authentik blueprints involved.

Declarative source: HelmRelease `postRenderers` block in the affected app's `helmrelease.yaml`.

---

## Operational Instructions

### Step 1 — Diagnose

```bash
# Confirm values are deployed correctly (preset shown as "none")
helm get values <release-name> -n <namespace>

# Confirm StatefulSet still shows preset values
kubectl get statefulset <sts-name> -n <namespace> \
  -o jsonpath='{.spec.template.spec.containers[0].resources}' | python3 -m json.tool

# Confirm generation never incremented (Helm saw no diff)
kubectl get statefulset <sts-name> -n <namespace> \
  -o jsonpath='{.metadata.generation} {.status.observedGeneration}'
# If generation=1 after multiple reconciles: Helm computed same spec → postRenderer needed
```

### Step 2 — Add postRenderer patch to HelmRelease

Add to the `postRenderers[0].kustomize.patches` list (create `postRenderers` if absent):

```yaml
postRenderers:
  - kustomize:
      patches:
        # Bitnami <subchart> v<X.Y.Z> ignores <key>.resources when a
        # resourcesPreset is active. Patch the rendered StatefulSet directly.
        - target:
            kind: StatefulSet
            name: <statefulset-name>
          patch: |
            - op: replace
              path: /spec/template/spec/containers/0/resources/limits/cpu
              value: "<desired-cpu>"
            - op: replace
              path: /spec/template/spec/containers/0/resources/limits/memory
              value: "<desired-memory>"
```

**Notes:**
- Use `op: replace` (not `add`) — the resources path already exists from the preset.
- Container index `0` is correct for single-container StatefulSets. Verify with `kubectl get sts <name> -o jsonpath='{.spec.template.spec.containers[*].name}'`.
- The patch runs after Helm renders manifests. Flux treats the postRenderer output as the desired state for all subsequent reconciles — the patch is sticky.
- If existing `postRenderers` already patch the same HelmRelease (e.g. for Ingress labels or Deployment initContainers), add this patch to the same `patches` list — do not create a second `postRenderers` entry.

### Step 3 — Also set `resourcesPreset: "none"` in values

Even though `resourcesPreset: "none"` alone doesn't fix the live StatefulSet, keep it in the Helm values as the declarative intent. The postRenderer enforces it on the rendered output.

```yaml
values:
  <subchart-key>:
    master:
      resourcesPreset: "none"
      resources:
        requests:
          cpu: <req-cpu>
          memory: <req-memory>
        limits:
          cpu: <limit-cpu>
          memory: <limit-memory>
```

### Step 4 — Commit, push, reconcile

```bash
git add <helmrelease-path>
git commit -m "fix(<app>): patch <subchart> StatefulSet resource limits via postRenderer"
git push origin main
mise exec -- flux reconcile helmrelease <release> -n <namespace> --with-source
```

### Step 5 — Verify

```bash
kubectl get statefulset <sts-name> -n <namespace> \
  -o jsonpath='{.spec.template.spec.containers[0].resources}' | python3 -m json.tool
# Expected: limits.cpu = <desired-cpu>, limits.memory = <desired-memory>

kubectl get statefulset <sts-name> -n <namespace> \
  -o jsonpath='{.metadata.generation}'
# Expected: generation > 1 (Flux applied a change)
```

---

## Examples

### Example 1: penpot-valkey-primary (confirmed pattern)

```yaml
# kubernetes/apps/office/penpot/app/helmrelease.yaml
postRenderers:
  - kustomize:
      patches:
        - target:
            kind: StatefulSet
            name: penpot-valkey-primary
          patch: |
            - op: replace
              path: /spec/template/spec/containers/0/resources/limits/cpu
              value: "500m"
            - op: replace
              path: /spec/template/spec/containers/0/resources/limits/memory
              value: "256Mi"
```

Bitnami valkey subchart v3.0.31 in penpot chart 0.40.0. `resourcesPreset: "none"` + explicit `resources` in values had no effect on the live StatefulSet. postRenderer resolved it — StatefulSet moved to generation 2, limits confirmed at 500m/256Mi.

---

## Verification Tests

```bash
# Test 1: StatefulSet generation > 1 (Helm applied update)
kubectl get statefulset <sts-name> -n <namespace> -o jsonpath='{.metadata.generation}'

# Test 2: Resource limits match patch values
kubectl get statefulset <sts-name> -n <namespace> \
  -o jsonpath='{.spec.template.spec.containers[0].resources.limits}'

# Test 3: HelmRelease Ready=True
mise exec -- flux get helmrelease <release> -n <namespace>
```

---

## Troubleshooting

### `op: replace` fails silently (StatefulSet unchanged)

**Cause:** Path doesn't exist. The preset may generate `limits: {}` rather than setting values, making `replace` invalid (it requires the key to exist).

**Fix:** Use `op: add` instead:
```yaml
- op: add
  path: /spec/template/spec/containers/0/resources/limits/cpu
  value: "500m"
```

### Wrong container index

**Cause:** StatefulSet has multiple containers (e.g. a sidecar). Container 0 might not be the main app.

**Fix:** Check container order:
```bash
kubectl get sts <name> -n <ns> -o jsonpath='{.spec.template.spec.containers[*].name}'
```

Adjust the index accordingly (`containers/1/resources/...`).

---

## Diagnose Examples

### Diagnose Example 1: Confirm patch is not applying

```bash
# Step 1: Check StatefulSet generation
kubectl get sts penpot-valkey-primary -n office \
  -o jsonpath='{.metadata.generation} {.status.observedGeneration}'

# Step 2: Force reconcile
mise exec -- flux reconcile helmrelease penpot -n office --with-source

# Step 3: Re-check resources
kubectl get sts penpot-valkey-primary -n office \
  -o jsonpath='{.spec.template.spec.containers[0].resources}' | python3 -m json.tool
```

---

## Health Check

```bash
# Verify all patched StatefulSets have correct limits
kubectl get statefulset -A -o json | python3 -c "
import sys, json
data = json.load(sys.stdin)
for sts in data['items']:
    for c in sts['spec']['template']['spec']['containers']:
        limits = c.get('resources', {}).get('limits', {})
        if limits.get('cpu') in ('150m', '100m') and 'valkey' in sts['metadata']['name']:
            print(f'WARN: {sts[\"metadata\"][\"namespace\"]}/{sts[\"metadata\"][\"name\"]} still at preset cpu={limits[\"cpu\"]}')
"
```

---

## Security Check

N/A — this SOP modifies resource limits only, not security posture.

---

## Rollback Plan

Remove the `postRenderers` patch block from the HelmRelease, commit, push, and reconcile. Helm will restore the preset-driven limits on the next reconcile cycle.
