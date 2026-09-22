# SOP: Pod Security Admission (PSA)

> Description: The cluster-wide Pod Security Admission convention — `baseline` by default from the shared Flux component, per-namespace overrides applied as kustomize patches against the placeholder Namespace, the full override inventory, and the mandatory `kubectl --dry-run=server` pre-check before tightening any level.
> Version: `2026.09.22`
> Last Updated: `2026-09-22`
> Owner: `homelab-sre`

---

## 1) Description

Every namespace in this cluster gets a Pod Security Admission level whether or
not anyone thought about it, because the shared Flux component stamps
`baseline` onto all three PSA labels. Overriding that is a kustomize patch with
a non-obvious target, and **getting the target wrong fails silently** — the
patch is ignored, no error is raised, and the namespace quietly stays at
`baseline` until some workload fails to schedule.

Tightening a level is worse: **PSA only gates pod CREATION.** Raising a
namespace to a stricter level does not evict or even disturb anything already
running. The cluster looks completely healthy, and the breakage surfaces at the
*next* restart of the component — a node reboot, a Talos upgrade, a Flux-driven
rollout, possibly weeks later, with nothing linking it to the label change.

This SOP exists so that neither failure mode is discovered the hard way.

- Scope: all namespaces reconciled from `kubernetes/apps/**`, plus the
  cluster-default component at `kubernetes/flux/components/common/namespace.yaml`.
- Prerequisites: repo-pinned tooling via `mise exec --`, cluster access with
  permission to label namespaces (the pre-check uses server-side dry-run, which
  persists nothing).
- Out of scope: the pod-level `securityContext` fields themselves, Falco runtime
  detection ([`falco.md`](falco.md)), and network policy.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Cluster default | `baseline` — `enforce`, `audit` and `warn` |
| Source of truth (default) | `kubernetes/flux/components/common/namespace.yaml` |
| Override mechanism | kustomize `patches:` entry targeting `kind: Namespace, name: not-used` |
| API-server admission config | Talos' cluster-wide `PodSecurity` `admissionControl` was **removed** 2026-04-30; enforcement is per-namespace labels only (per the comment in `kubernetes/bootstrap/talos/talconfig.yaml` — *not independently verified for this SOP*) |
| Files carrying PSA labels | **15** total (measured, see §3) |
| Namespace-level overrides | **9** top-level + **3** nested re-assertions + **1** literal Namespace object |
| Live distribution | 8 `privileged`, 8 `baseline`, 1 `restricted`, 4 with no `enforce` label `[verified 2026-09-22]` |
| Mandatory pre-check | `kubectl label … --dry-run=server` before **any** tightening |
| Rollback | `git revert` — relaxing a level never evicts anything |

### Why the patch target is `name: not-used`

The shared component ships a Namespace literally named `not-used`:

```yaml
# kubernetes/flux/components/common/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: not-used
  annotations:
    kustomize.toolkit.fluxcd.io/prune: disabled
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/audit: baseline
    pod-security.kubernetes.io/warn: baseline
```

Each app-directory kustomization sets `namespace: <real-name>`, and kustomize's
**namespace transformer runs AFTER patches**. So at patch time the resource is
still called `not-used`; a patch targeting the real namespace name matches
nothing and is dropped without a warning.

> **Do not try to override PSA by adding an inline `Namespace` resource.** It
> was tried in `my-software-development` and `my-software-production` and
> kustomize **silently ignored it** — both kustomizations still carry a comment
> recording that. A patch against `name: not-used` is the only shape that works.

---

## 3) Blueprints

### The override patch (copy this shape exactly)

```yaml
# kubernetes/apps/<namespace>/kustomization.yaml
---
# yaml-language-server: $schema=https://json.schemastore.org/kustomization
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: <namespace>
components:
  - ../../flux/components/common
resources:
  - ./<app>/ks.yaml
patches:
  # Target MUST be `name: not-used` — the namespace transformer runs AFTER
  # patches, so the resource is still named `not-used` at this point.
  - target:
      kind: Namespace
      name: not-used
    patch: |-
      apiVersion: v1
      kind: Namespace
      metadata:
        name: not-used
        labels:
          pod-security.kubernetes.io/enforce: privileged
          pod-security.kubernetes.io/audit: privileged
          pod-security.kubernetes.io/warn: privileged
```

Always set **all three** labels together. Setting `enforce` alone leaves `audit`
and `warn` reporting against a different standard, which makes the API server
emit warnings for pods it is simultaneously admitting — confusing, and it trains
operators to ignore PSA warnings.

### Full override inventory `[verified 2026-09-22 — counted mechanically]`

`grep -rl "pod-security.kubernetes.io" kubernetes/ --include="*.yaml"` returns
**15 files**. Two are not overrides: the default component above, and
`kubernetes/bootstrap/talos/talconfig.yaml` (a historical comment only, no
label). The remaining **13** are:

| Namespace | Level | File | Note |
|---|---|---|---|
| `cert-manager` | `restricted` | `apps/cert-manager/kustomization.yaml` | the only namespace tightened above the default |
| `databases` | `privileged` | `apps/databases/kustomization.yaml` | |
| `download` | `privileged` | `apps/download/kustomization.yaml` | |
| `home-automation` | `privileged` | `apps/home-automation/kustomization.yaml` | |
| `kube-system` | `privileged` | `apps/kube-system/kustomization.yaml` | |
| `media` | `privileged` | `apps/media/kustomization.yaml` | |
| `monitoring` | `privileged` | `apps/monitoring/kustomization.yaml` | |
| `security` | `privileged` | `apps/security/kustomization.yaml` | |
| `storage` | `privileged` | `apps/storage/kustomization.yaml` | |
| `monitoring` | `privileged` | `apps/monitoring/eck-operator/app/kustomization.yaml` | **nested re-assertion** |
| `monitoring` | `privileged` | `apps/monitoring/elasticsearch/app/kustomization.yaml` | **nested re-assertion** |
| `monitoring` | `privileged` | `apps/monitoring/kibana/app/kustomization.yaml` | **nested re-assertion** |
| `security` | `privileged` | `apps/security/wazuh/app/namespace.yaml` | **literal Namespace object**, `enforce` + `enforce-version: latest` only — no `audit`/`warn` |

So: **9 distinct namespaces are overridden** (8 to `privileged`, `cert-manager`
to `restricted`), plus 3 nested kustomizations inside `monitoring` that
re-assert `privileged`, plus one literal Namespace for `security`.

### Why the nested re-assertions exist — do not "clean them up"

They look redundant. They are not. Each of those nested kustomizations
**includes the common component itself**, so it produces its own copy of the
`not-used` Namespace carrying the `baseline` default. Whichever Kustomization
reconciles **last** wins, so a nested one without the patch would periodically
stomp `monitoring` back down to `baseline` and break the privileged DaemonSets.
This exact failure is recorded in
[`monitoring.md`](monitoring.md) §"privileged namespace" (≈line 1066).

**Rule: any kustomization that includes `flux/components/common` for a namespace
whose level is not `baseline` must also carry that namespace's PSA patch.**

### Live state `[verified 2026-09-22]`

```
privileged (8):  databases, download, home-automation, kube-system,
                 media, monitoring, security, storage
baseline   (8):  ai, backup, default, my-software-development,
                 my-software-production, my-software-showcase, network, office
restricted (1):  cert-manager
no enforce (4):  flux-system, cilium-secrets, kube-public, kube-node-lease
```

The four unenforced namespaces are **not** managed by this convention:

- **`flux-system`** — owned by `flux-operator` (`app.kubernetes.io/managed-by:
  flux-operator`) and annotated `kustomize.toolkit.fluxcd.io/ssa: Ignore` with
  `prune: disabled`. It carries only `pod-security.kubernetes.io/warn:
  restricted` + `warn-version: latest` and **no `enforce` label at all**, even
  though `kubernetes/apps/flux-system/kustomization.yaml` includes the common
  component. Treat this as owned by the Flux operator, not by this SOP.
- **`cilium-secrets`** — created by the cilium Helm chart.
- **`kube-public`, `kube-node-lease`** — stock Kubernetes namespaces, untouched.

> ⚠️ **Known doc drift, recorded rather than silently fixed.** The comment block
> inside `kubernetes/flux/components/common/namespace.yaml` claims
> *"Privileged (7)"* and lists `cert-manager` under *"Baseline (8)"*. Both are
> stale: there are **8** privileged namespaces (it omits `security`),
> `cert-manager` is **`restricted`**, and `my-software-showcase` is missing from
> the baseline list entirely. Trust the live cluster and the table above; that
> comment is not the source of truth. Correcting it is a separate change, not
> part of this SOP.

---

## 4) Operational Instructions

### The direction of risk

| Direction | Risk | Pre-check |
|---|---|---|
| **Relaxing** (`restricted` → `baseline` → `privileged`) | Low — strictly widens what may be created. Nothing running is affected | Still confirm it is genuinely needed; `privileged` is a security decision |
| **Tightening** (`privileged` → `baseline` → `restricted`) | **High, and silently deferred** — running pods are untouched, so the breakage appears at the next restart | **MANDATORY**, see below |

### Changing a namespace's level

1. **Establish why.** `privileged` needs a named workload requiring it
   (hostPath, hostNetwork, `IPC_LOCK`, privileged containers). Record it in the
   commit message.
2. **Run the mandatory pre-check (§4a) if tightening.** Not optional.
3. Edit the namespace's `kustomization.yaml` using the §3 patch shape. If the
   namespace has nested kustomizations that include the common component, update
   **every one of them** in the same commit.
4. Commit with explicit paths — the worktree is shared:
   ```bash
   git commit --only kubernetes/apps/<ns>/kustomization.yaml -F msg.txt
   git show --stat HEAD     # confirm no foreign hunk rode along
   git push
   ```
5. Let Flux reconcile (webhook). Verify with §6.

### 4a) MANDATORY pre-check before tightening

`--dry-run=server` sends the change through real admission and **persists
nothing**. The API server replies with a warning naming every currently-running
pod that the new level would reject:

```bash
mise exec -- kubectl label --dry-run=server --overwrite ns <namespace> \
  pod-security.kubernetes.io/enforce=<level>
```

Verified output shape `[verified 2026-09-22]`, probing `network` at `restricted`:

```
Warning: existing pods in namespace "network" violate the new PodSecurity enforce level "restricted:latest"
Warning: adguard-exporter-…: seccompProfile
Warning: adguard-home-… (and 3 other pods): allowPrivilegeEscalation != false, unrestricted capabilities, runAsNonRoot != true, seccompProfile
namespace/network labeled (server dry run)
```

Nothing persisted — the namespace was still `baseline` immediately afterwards.

**Reading it:** `namespace/… labeled (server dry run)` is *not* a pass. It always
appears. **The warnings are the result.** Any warning means that many workloads
will fail to start at their next restart. Either fix their `securityContext`
first, or do not tighten.

Also check the workloads directly, because PSA evaluates pod specs and a
Deployment's template is what will be re-submitted:

```bash
mise exec -- kubectl -n <namespace> get pods -o json | python3 -c '
import sys, json
for p in json.load(sys.stdin)["items"]:
    psc = p["spec"].get("securityContext", {})
    for c in p["spec"].get("containers", []):
        sc = c.get("securityContext", {}) or {}
        caps = (sc.get("capabilities") or {}).get("add")
        flags = []
        if sc.get("privileged"): flags.append("privileged")
        if sc.get("allowPrivilegeEscalation") is not False: flags.append("allowPrivEsc!=false")
        if not (sc.get("runAsNonRoot") or psc.get("runAsNonRoot")): flags.append("runAsNonRoot!=true")
        if caps: flags.append("caps+" + ",".join(caps))
        if p["spec"].get("hostNetwork"): flags.append("hostNetwork")
        if flags:
            print(f"{p[\"metadata\"][\"name\"]}/{c[\"name\"]}: {\", \".join(flags)}")
'
```

---

## 5) Examples

### Example A: lift a namespace to `privileged`

A DaemonSet needs `hostPath` + `hostNetwork`. Add the §3 patch block with
`privileged` on all three labels, commit, push. No pre-check required
(relaxing), but state the justifying workload in the commit message.

### Example B: tighten a namespace to `restricted`

The `cert-manager` precedent. Run §4a first, confirm **zero** warnings, then
apply the patch with `restricted` on all three labels.

If §4a reports violations, the sequence is: fix each workload's
`securityContext` (add `seccompProfile: RuntimeDefault`,
`allowPrivilegeEscalation: false`, `runAsNonRoot: true`, drop `ALL`
capabilities), let those roll out, re-run §4a until clean, **then** tighten.

### Example C: a namespace with nested kustomizations

`monitoring` — the patch must appear in `apps/monitoring/kustomization.yaml`
**and** in every nested `*/app/kustomization.yaml` that pulls in
`flux/components/common`. Currently that is `eck-operator`, `elasticsearch` and
`kibana`. Miss one and the level flaps on reconcile order.

---

## 6) Verification Tests

### Test 1: the label actually landed

```bash
mise exec -- kubectl get ns <namespace> \
  -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}{"\n"}'
```

Expected:
- The level you set.

If failed:
- The patch target is almost certainly wrong. It must be
  `kind: Namespace, name: not-used` — see §3. Confirm locally before blaming
  Flux:
  ```bash
  mise exec -- kubectl kustomize kubernetes/apps/<namespace> \
    | python3 -c '
import sys, yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d.get("kind") == "Namespace":
        print(d["metadata"]["name"], d["metadata"].get("labels", {}))
'
  ```

### Test 2: all three labels agree

```bash
mise exec -- kubectl get ns <namespace> -o json | python3 -c '
import sys, json
l = json.load(sys.stdin)["metadata"]["labels"]
vals = {k.split("/")[-1]: v for k, v in l.items() if k.startswith("pod-security")}
print(vals)
print("CONSISTENT" if len(set(vals.values())) == 1 else "MISMATCH")
'
```

Expected:
- `CONSISTENT`.

If failed:
- A partial patch. Mismatched `warn`/`audit` produce warnings for pods that are
  nonetheless admitted.

### Test 3: cluster-wide inventory matches this SOP

```bash
mise exec -- kubectl get ns -o json | python3 -c '
import sys, json, collections
rows = []
for n in json.load(sys.stdin)["items"]:
    l = n["metadata"].get("labels", {})
    rows.append((n["metadata"]["name"], l.get("pod-security.kubernetes.io/enforce", "<none>")))
for name, lvl in sorted(rows):
    print(f"{name:26s} {lvl}")
print()
print(collections.Counter(l for _, l in rows))
'
```

Expected:
- 8 `privileged`, 8 `baseline`, 1 `restricted`, 4 `<none>` `[verified 2026-09-22]`.

If failed:
- A count that drifted from §3 means either an undocumented change or a patch
  that stopped applying. Reconcile against the table before assuming it is fine.

### Test 4: workloads actually start under the new level

PSA gates creation, so the only real proof is a pod creation after the change.

```bash
mise exec -- kubectl -n <namespace> rollout restart deploy/<a-representative-deploy>
mise exec -- kubectl -n <namespace> rollout status deploy/<a-representative-deploy> --timeout=180s
mise exec -- kubectl -n <namespace> get events --field-selector reason=FailedCreate \
  --sort-by='.lastTimestamp' | tail -10
```

Expected:
- Rollout completes; no `FailedCreate` events mentioning `violates PodSecurity`.

If failed:
- Relax the level immediately (§11) and fix the `securityContext` first.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---|---|---|
| Patch committed, label never changes | Patch targets the real namespace name instead of `not-used` | Retarget to `name: not-used`; §6 Test 1 |
| Inline `Namespace:` resource has no effect | kustomize silently ignores it — recorded in two kustomizations here | Use a `patches:` block instead |
| Level flaps between reconciles | A nested kustomization includes `components/common` without the PSA patch; last writer wins | Add the patch to **every** such kustomization; [`monitoring.md`](monitoring.md) §privileged namespace |
| `FailedCreate: violates PodSecurity "restricted:latest"` | A level was tightened without the §4a pre-check; surfaces only at restart | Revert the level (§11), then fix `securityContext` |
| Everything green after tightening | PSA does not touch running pods — this proves nothing | Run §6 Test 4; force a real pod creation |
| DaemonSet pods never schedule in `monitoring` | Namespace fell back to `baseline` | `kubectl get ns monitoring --show-labels`; then §6 Test 1 |
| `security` namespace level looks inconsistent | It is set in **two** places: the kustomization patch and `wazuh/app/namespace.yaml` (a literal Namespace with `enforce` only) | Change both together, or they will disagree |

```bash
# Quick debugging
mise exec -- kubectl get ns --show-labels | grep pod-security
mise exec -- kubectl get events -A --field-selector reason=FailedCreate --sort-by='.lastTimestamp' | tail -20
mise exec -- kubectl -n <ns> get events --sort-by='.lastTimestamp' | grep -i podsecurity
```

---

## 8) Diagnose Examples

### Diagnose Example 1: a workload suddenly will not start after a reboot

The classic deferred-tightening failure — the label changed weeks ago and
nothing broke until the node rebooted.

```bash
mise exec -- kubectl -n <ns> get events --sort-by='.lastTimestamp' | grep -i "PodSecurity" | tail -5
mise exec -- kubectl get ns <ns> -o jsonpath='{.metadata.labels}{"\n"}'
mise exec -- git log --oneline -S "pod-security" -- kubernetes/apps/<ns>/kustomization.yaml | head -5
```

Expected:
- An event naming the violated level and the offending field, plus a commit that
  changed the level some time earlier.

If unclear:
- Run §4a against the *current* level. If it warns about the very pods that
  cannot start, the diagnosis is confirmed.

### Diagnose Example 2: the rendered namespace does not match the repo

```bash
# What does kustomize actually produce?
mise exec -- kubectl kustomize kubernetes/apps/<ns> \
  | python3 -c '
import sys, yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d.get("kind") == "Namespace":
        print(d["metadata"]["name"], d["metadata"].get("labels", {}))
'
# Which Kustomizations could be writing this namespace?
grep -rl "flux/components/common" kubernetes/apps/<ns>/ 
```

Expected:
- Exactly one rendered Namespace, carrying your intended labels.
- Every file listed by the `grep` carries the PSA patch.

If unclear:
- A file in that grep list **without** the patch is your flapper.

---

## 9) Health Check

```bash
# 1. Full inventory (compare against §3)
mise exec -- kubectl get ns -L pod-security.kubernetes.io/enforce

# 2. Any namespace where the three labels disagree
mise exec -- kubectl get ns -o json | python3 -c '
import sys, json
for n in json.load(sys.stdin)["items"]:
    l = n["metadata"].get("labels", {})
    v = {k.split("/")[-1]: val for k, val in l.items()
         if k.startswith("pod-security") and not k.endswith("-version")}
    if v and len(set(v.values())) > 1:
        print("MISMATCH", n["metadata"]["name"], v)
'

# 3. Any recent PSA rejection anywhere
mise exec -- kubectl get events -A --field-selector reason=FailedCreate \
  --sort-by='.lastTimestamp' | grep -i podsecurity | tail -10

# 4. Every kustomization pulling in the common component for a non-baseline ns
#    must carry that namespace's patch
for ns in databases download home-automation kube-system media monitoring security storage; do
  for f in $(grep -rl "flux/components/common" kubernetes/apps/$ns/ 2>/dev/null); do
    grep -q "pod-security.kubernetes.io/enforce" "$f" || echo "MISSING PATCH: $f"
  done
done
```

Expected:
- Inventory matching §3; no `MISMATCH`; no PSA `FailedCreate` events; no
  `MISSING PATCH` lines.

---

## 10) Security Check

```bash
# 1. privileged namespaces must be justified — list what actually uses it
for ns in databases download home-automation kube-system media monitoring security storage; do
  echo "== $ns"
  mise exec -- kubectl -n $ns get pods -o json | python3 -c '
import sys, json
for p in json.load(sys.stdin)["items"]:
    s = p["spec"]
    why = []
    if s.get("hostNetwork"): why.append("hostNetwork")
    if s.get("hostPID"):     why.append("hostPID")
    if any(v.get("hostPath") for v in s.get("volumes", []) or []): why.append("hostPath")
    for c in s.get("containers", []):
        sc = c.get("securityContext") or {}
        if sc.get("privileged"): why.append("privileged")
        caps = (sc.get("capabilities") or {}).get("add") or []
        if caps: why.append("caps+" + ",".join(caps))
    if why:
        print("  ", p["metadata"]["name"], sorted(set(why)))
'
done

# 2. No namespace should be privileged without at least one such workload
```

Expected:
- Every `privileged` namespace lists at least one workload that genuinely needs
  it. A `privileged` namespace with **no** such workload is an unnecessary
  grant — candidate for tightening (via §4a, never blind).
- No unintended exposure: PSA is a workload-admission control, not a network
  control. It does not restrict what a namespace can reach.
- `security/wazuh/app/namespace.yaml` sets only `enforce` (plus
  `enforce-version: latest`). It therefore has no `audit`/`warn` signal — a
  deliberate-looking asymmetry worth re-reviewing if that namespace is ever
  tightened.

---

## 11) Rollback Plan

Relaxing a PSA level is always safe and immediate — it never evicts anything.

```bash
# Preferred: GitOps revert
git revert <sha> && git push
mise exec -- flux reconcile ks <kustomization> --with-source

# EMERGENCY ONLY — unblocks workloads now; Flux will reconcile the repo state
# back over it, so the git revert above is still required.
mise exec -- kubectl label --overwrite ns <namespace> \
  pod-security.kubernetes.io/enforce=privileged \
  pod-security.kubernetes.io/audit=privileged \
  pod-security.kubernetes.io/warn=privileged
```

After any rollback, re-run §6 Test 4 — force a real pod creation. A namespace
that merely *looks* right proves nothing about PSA.

---

## 12) References

- `kubernetes/flux/components/common/namespace.yaml` — the `baseline` default and the `not-used` placeholder
- `kubernetes/apps/cert-manager/kustomization.yaml` — the `restricted` precedent
- `kubernetes/apps/databases/kustomization.yaml` — the canonical `privileged` patch shape
- `kubernetes/apps/security/wazuh/app/namespace.yaml` — the one literal Namespace object
- `kubernetes/bootstrap/talos/talconfig.yaml` — history of the removed cluster-wide `admissionControl`
- [`monitoring.md`](monitoring.md) §"privileged namespace" — the reconcile-order flap this SOP's nested-patch rule prevents
- `docs/security.md` — overall security posture
- [`falco.md`](falco.md) — runtime detection, complementary to admission control
- [`new-deployment-blueprint.md`](new-deployment-blueprint.md) — namespace placement for new apps
- Finding: `security_ref: F-75f3dc82`
- Upstream: [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| `2026.09.22` | 2026-09-22 | Initial SOP (`F-75f3dc82`). Documents the previously-undocumented convention: `baseline` default from the shared component, the `name: not-used` patch target and why an inline Namespace is silently ignored, the mechanically-counted override inventory (15 files → 9 namespace overrides + 3 nested re-assertions + 1 literal Namespace), why the nested monitoring patches are load-bearing rather than redundant, the mandatory `--dry-run=server` pre-check with its verified output shape, and the deferred-failure property that makes tightening dangerous. Records the stale comment in `flux/components/common/namespace.yaml` as known drift rather than correcting it here. |
