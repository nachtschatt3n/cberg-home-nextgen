# SOP: Longhorn RWO Multi-Attach on Rollout

> Description: Diagnosing and permanently fixing `FailedAttachVolume` / `Multi-Attach error` stalls when a single-replica Deployment that mounts a ReadWriteOnce Longhorn PVC is rolled.
> Version: `2026.08.15`
> Last Updated: `2026-08-15`
> Owner: `Platform`

---

## 1) Description

This SOP covers the rollout stall that occurs when a **Deployment with `replicas: 1`
mounting a ReadWriteOnce (RWO) Longhorn PVC** is updated under the default
`RollingUpdate` strategy. The new pod cannot attach a volume the old pod still
holds, and the old pod is not permitted to terminate until the new one is Ready —
a circular wait.

The important operational property, and the reason this SOP exists: **it is not a
permanent deadlock.** It resolves nondeterministically, on a scheduling lottery.
That makes it *worse* to operate than a clean failure — it presents differently on
each occurrence, sometimes clearing in seconds and sometimes in ten minutes, so it
repeatedly burns triage time and gets misdiagnosed as a storage, Flux, or image
problem.

- Scope: all namespaces; any `Deployment` with `replicas: 1` mounting an RWO PVC on
  storage class `longhorn` or `longhorn-static`.
- Prerequisites: repo `/Users/mu/code/cberg-home-nextgen`, `mise exec --` tooling,
  cluster read access.
- Out of scope:
  - **StatefulSets** — immune to the deadlock (see §2.3).
  - **CIFS/SMB PVCs** — the `smb.csi.k8s.io` driver has `attachRequired: false`, so
    no `VolumeAttachment` exists and Multi-Attach cannot occur. This is why
    `office/nextcloud` and `office/nextcloud-notify-push` can share the RWO PVC
    `nextcloud-data` concurrently today.
  - Multi-replica Deployments on RWO — a different (and always-broken) design.

---

## 2) Overview

### 2.1 The signature

| Setting | Value |
|---------|-------|
| Event reason | `FailedAttachVolume` |
| Event message | `Multi-Attach error for volume "<pv>" ...` |
| New pod | `ContainerCreating`, never Ready |
| Old pod | **`Running`, and still serving traffic** |
| User-facing outage | **None** — the old pod keeps answering |
| Affected driver | `driver.longhorn.io` (`attachRequired: true`) |
| Source of truth | app `helmrelease.yaml` / `deployment.yaml` under `kubernetes/apps/` |

Because the old pod keeps serving, **this is not a user-visible outage**. It is a
stuck rollout. Do not page on it; do not hand-intervene (§4.4).

There are two message variants, and **both mean the same thing** — the volume is
attached to a *different node* than the one the new pod was scheduled onto:

```text
Multi-Attach error for volume "pvc-629c…" Volume is already used by pod(s) librechat-librechat-66f96695f8-7xrqp
Multi-Attach error for volume "plex-config" Volume is already exclusively attached to one node and can't be attached to another
```

The first form appears when the attach/detach controller can resolve *which* pods
hold the volume on the other node; the second when it cannot. **Do not read
"used by pod(s)" as a same-node conflict** — it is still cross-node. Two pods on
the *same* node can share an RWO volume without error; that fact is the whole
basis of the nondeterministic resolution below.

### 2.2 The arithmetic that causes it

Kubernetes defaults an unspecified Deployment strategy to:

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 25%
    maxUnavailable: 25%
```

Kubernetes rounds **`maxSurge` UP** and **`maxUnavailable` DOWN** (deliberately, so
a percentage never yields zero capacity on a large Deployment). At `replicas: 1`
those two roundings combine into the worst possible case:

| Field | Computation at `replicas: 1` | Result |
|-------|------------------------------|--------|
| `maxSurge: 25%` | `ceil(0.25 × 1)` | **1** → a second pod *is* created |
| `maxUnavailable: 25%` | `floor(0.25 × 1)` | **0** → the old pod *may not* be taken down |

So the rollout is required to bring a second pod to Ready **before** it is allowed
to remove the first — while the second pod cannot start, because the RWO volume is
attached to the node running the first. Circular wait.

### 2.3 Why StatefulSets are immune (to the deadlock, not the message)

A StatefulSet with the default `podManagementPolicy: OrderedReady` and
`updateStrategy: RollingUpdate` **has no surge concept**. It deletes `pod-N` and
waits for the replacement to be Running and Ready. The old pod is therefore always
gone before the new one is scheduled, so the volume is guaranteed to detach.

A StatefulSet **can still log `Multi-Attach error`** — as a short transient while
Longhorn finishes detaching from the old node — but it always self-heals in
seconds, because nothing is holding the volume. See the plex timeline in §5.2.

**Summary:** StatefulSet → guaranteed-progress transient. Deployment +
`RollingUpdate` → circular wait that clears only by luck.

### 2.4 Why it resolves nondeterministically — the scheduling lottery

Longhorn attaches an RWO volume **to a node**, not to a pod. Multiple pods on that
*same* node may mount it concurrently.

So on each retry (Flux/Helm remediation, or the ReplicaSet recreating the pending
pod) the scheduler re-rolls the dice:

- Replacement lands on a **different** node → `Multi-Attach`, stall continues.
- Replacement lands on the **same** node that holds the attachment → it shares the
  existing attachment, becomes Ready, the old pod is torn down, rollout completes.

Nothing in the system drives toward the second outcome; it is chance plus whatever
the scheduler's spread/affinity scoring happens to prefer. That is why the same bug
looks like "cleared instantly" one week and "hung for ten minutes" the next, and
why it must be fixed structurally rather than waited out.

---

## 3) Blueprints

The durable fix is one field: `spec.strategy.type: Recreate` on the Deployment.

```yaml
spec:
  replicas: 1
  strategy:
    type: Recreate   # tears the old pod down FIRST, releasing the RWO volume
```

**Trade-off, accepted deliberately:** `Recreate` means a brief outage on *every*
future rollout of that app (single replica, no surge, so there is a gap between old
pod termination and new pod Ready). That gap is inherent to a ReadWriteOnce volume —
a RollingUpdate could only avoid it by running two pods at once, which RWO forbids.
A short deterministic gap is strictly better than a nondeterministic multi-minute
stall. Accept it.

### 3.1 Values path differs per chart — this is the main trap

For chart-based apps this is a **values** change, and the values key is **not**
consistent across chart families. A pin at the wrong path **silently no-ops** — the
render simply ignores it and you ship a fix that does nothing.

| Chart family | Values path | Renders into |
|---|---|---|
| Plain manifest (in-repo `deployment.yaml`) | `spec.strategy` | `spec.strategy` |
| bjw-s `app-template`, `open-webui` | `strategy` (or `controllers.*.strategy`) | `spec.strategy` |
| `librechat` (parent Deployment) | `updateStrategy` | `spec.strategy` |
| bitnami `mongodb` (standalone) | `mongodb.updateStrategy` | `spec.strategy` |

Note the bitnami case: `templates/standalone/dep-sts.yaml` branches on
`.Values.useStatefulSet` and emits the key `strategy:` for a Deployment and
`updateStrategy:` for a StatefulSet — but reads **`.Values.updateStrategy`** in both
cases. The values key name does not tell you the rendered key name.

**Therefore: never trust the path. Verify by render (§6.1).**

---

## 4) Operational Instructions

### 4.1 Enumerate exposed workloads

Run the sweep in §9. It lists every single-replica Deployment mounting an RWO PVC
and flags those not on `Recreate`.

### 4.2 Classify each hit before changing it

Not every `RollingUpdate` is exposed. A Deployment is **only** exposed when *all* of:

1. `replicas: 1` (or any value where `maxUnavailable` floors to 0), **and**
2. the effective `maxSurge` is **> 0**, **and**
3. at least one mounted PVC is RWO on `driver.longhorn.io`.

An explicit `maxUnavailable: 1, maxSurge: 0` is **already safe** — it scales the old
pod down before creating the new one, exactly like `Recreate`. Leave those alone and
note them; converting them buys nothing and churns unrelated apps.

### 4.3 Apply, validate, ship (GitOps only)

```bash
cd /Users/mu/code/cberg-home-nextgen
# 1. edit the manifest or HelmRelease values
# 2. PROVE the change renders (see §6.1) -- do not skip
# 3. validate
mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas \
  kubernetes/apps/<namespace>/<app>
mise exec -- task kubeconform
# 4. commit + push; Flux's webhook reconciles
git add kubernetes/apps/<namespace>/<app>
git commit -m "fix(<app>): Recreate strategy — RWO PVC deadlocks RollingUpdate"
git push
```

`spec.strategy` is **outside the pod template**, so applying this change does **not**
restart anything. It takes effect at the next rollout.

### 4.4 What NOT to do when you find one live

**Do not "fix" a live Multi-Attach by hand.** Specifically, do not:

- `kubectl delete pod <old-pod>` — the old pod is the one **still serving users**.
  Deleting it converts a zero-impact stuck rollout into a real outage, and force-
  detaches a volume with an active writer.
- `kubectl scale deploy/<app> --replicas=0` — same, plus it can leave Longhorn
  reconciling a detach while Flux races to scale back up.
- Delete or edit the `VolumeAttachment`, or force-detach in the Longhorn UI — this
  is a live read-write volume with a running process on it. Forced detach of an
  attached RWO volume risks data-path surprises (unflushed writes, filesystem
  inconsistency) on databases in particular.

**Correct response:** confirm the old pod is still serving, then **wait**. It clears
on retry. Afterwards, fix it permanently in git per §4.3. If it has not cleared
after ~15 minutes, escalate per §7 rather than intervening on the volume.

---

## 5) Examples

### 5.1 Example A — `ai/librechat` (chart values, the deadlock case)

Confirmed occurrence during the 2.0.2 → 2.0.7 chart upgrade on 2026-08-14.

**Timeline (the worked example):**

| Time (UTC) | Event |
|---|---|
| `23:09:46Z` | New pod `librechat-librechat-79fd4c448-kd52d` scheduled to a node that does not hold the volume. `FailedAttachVolume`: `Multi-Attach error for volume "pvc-629c…" Volume is already used by pod(s) librechat-librechat-66f96695f8-7xrqp` |
| `23:09Z–23:20Z` | New pod stuck `ContainerCreating`. **Old pod `…-7xrqp` stays `Running` and keeps serving LibreChat.** No user impact. |
| `~23:20:03Z` | **Clears unaided (~10 min).** Helm upgrade remediation retried; the old pod was torn down and the replacement happened to be scheduled onto the node holding the attachment. `upgradeFailures=1`. |
| end state | HelmRelease `Ready=True / UpgradeSucceeded`, chart `librechat@2.0.7`. |

Nobody fixed it. It won the lottery.

**Fix applied** — note two Deployments in this release needed it, at two different
values paths:

```yaml
# kubernetes/apps/ai/librechat/app/helmrelease.yaml
spec:
  values:
    updateStrategy:            # parent librechat Deployment
      type: Recreate
    mongodb:
      updateStrategy:          # bitnami mongodb subchart Deployment
        type: Recreate
```

### 5.2 Example B — `media/plex` (StatefulSet, the benign transient)

Same event reason, same night, completely different mechanism — this is the contrast
that tells you which one you are looking at:

| Time (UTC) | Event |
|---|---|
| `22:35:07Z` | `Killing` — StatefulSet terminates the old pod **first** (no surge) |
| `22:35:17Z` | `FailedAttachVolume`: `Multi-Attach error for volume "plex-config" Volume is already exclusively attached to one node and can't be attached to another` — Longhorn has not finished detaching yet |
| `22:35:32Z` | `SuccessfulAttachVolume` — **self-healed after 15 s** |
| `22:35:39Z` | Container started. Total kill→start: **32 seconds.** |

No fix required, and none should be applied. `plex-plex-media-server` is a
StatefulSet (`replicas: 1`, `podManagementPolicy: OrderedReady`).

**Rule of thumb:** Multi-Attach that clears in seconds and was preceded by a
`Killing` event = benign detach transient. Multi-Attach that persists for minutes
while an old pod is still `Running` = the Deployment deadlock.

### 5.3 Example C — `databases/postgresql` (plain in-repo manifest)

```yaml
# kubernetes/apps/databases/postgresql/app/deployment.yaml
spec:
  replicas: 1
  strategy:
    type: Recreate
```

---

## 6) Verification Tests

### Test 1: Prove the values path actually rendered (chart apps)

The single most important test. A wrong values path is silent.

```bash
cd /Users/mu/code/cberg-home-nextgen
eval "$(mise env -s bash)"
# Chart artifacts are cached by Flux; ghcr anonymous pull may be blocked from the LAN.
kubectl -n flux-system port-forward svc/source-controller 18080:80 &
curl -sS -o chart.tgz "$(kubectl -n flux-system get helmchart <ns>-<app> -o jsonpath='{.status.artifact.url}' \
  | sed 's#http://source-controller.flux-system.svc.cluster.local.#http://127.0.0.1:18080#')"
tar xzf chart.tgz
# render with the HelmRelease's own values block, then assert
helm template <app> ./<chart> -n <ns> -f vals.yaml \
  | python3 -c "
import sys,yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d.get('kind') in ('Deployment','StatefulSet'):
        pvcs=[v['persistentVolumeClaim']['claimName'] for v in (d['spec']['template']['spec'].get('volumes') or []) if v.get('persistentVolumeClaim')]
        print(d['kind'], d['metadata']['name'], d['spec'].get('strategy') or d['spec'].get('updateStrategy'), pvcs)"
```

Expected:
- Every RWO-mounting `Deployment` prints `{'type': 'Recreate'}`.

If failed:
- The values path is wrong. Grep the chart template for `Strategy` and check which
  `.Values.*` key it reads — do not guess from the rendered key name (§3.1).

### Test 2: Prove it landed on the live object

```bash
mise exec -- kubectl -n <ns> get deploy <name> -o jsonpath='{.spec.strategy}{"\n"}'
```

Expected:
- `{"type":"Recreate"}` — and **no** `rollingUpdate` sub-block.

If failed:
- Flux has not reconciled yet: `mise exec -- flux get helmreleases -n <ns>`.

### Test 3: Prove nothing else regressed

```bash
mise exec -- kubectl -n <ns> get pods -l app=<name>
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
```

Expected:
- Target pods `Running` / Ready; the touched app's Flux resources `Ready=True`.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `Multi-Attach`, old pod still `Running`, minutes elapsed | The Deployment deadlock | **Wait** — it clears on retry. Then apply §3 in git. Never delete the old pod. |
| `Multi-Attach` cleared in <30 s, preceded by `Killing` | Benign detach transient (StatefulSet or `Recreate`) | None. Expected behaviour. |
| Fix committed but Deployment still shows `RollingUpdate` | Wrong values path — silently no-oped | Re-run Test 1; grep the chart for `.Values.*Strategy` |
| `Multi-Attach` persists >15 min with no old pod running | Stale `VolumeAttachment` / Longhorn stuck detaching — a real storage fault, not this SOP | Check §8.2; escalate. Do not force-detach blindly. |
| PVC `Pending`, no Multi-Attach at all | Missing Longhorn `Volume` CR for a `longhorn-static` PV | See `docs/sops/longhorn.md` — the `Volume` CR needs a manual apply |

---

## 8) Diagnose Examples

### Diagnose Example 1: Confirm it is the deadlock (not a storage fault)

```bash
eval "$(mise env -s bash)"
NS=ai; APP=librechat-librechat
# 1. The event and its exact wording
kubectl -n $NS describe pod -l app.kubernetes.io/name=$APP | sed -n '/Events:/,$p'
# 2. THE decisive check: is an OLD pod still Running?
kubectl -n $NS get pods -l app.kubernetes.io/name=$APP -o wide
# 3. The arithmetic that caused it
kubectl -n $NS get deploy $APP -o jsonpath='{.spec.replicas}{" "}{.spec.strategy}{"\n"}'
```

Expected (confirms the deadlock):
- One pod `ContainerCreating` + one **older pod `Running` on a different node**.
- `1 {"rollingUpdate":{"maxSurge":"25%","maxUnavailable":"25%"},"type":"RollingUpdate"}`

If unclear:
- If no old pod is `Running`, this is **not** the deadlock — it is a detach
  transient or a genuine storage fault. Go to Example 2.

### Diagnose Example 2: Correlate pod node vs volume attachment node

This is the check that proves "the volume is on the wrong node".

```bash
eval "$(mise env -s bash)"
NS=ai; PVC=librechat-librechat-images
PV=$(kubectl -n $NS get pvc $PVC -o jsonpath='{.spec.volumeName}')
echo "PV: $PV"
# Which node does Longhorn have it attached to?
kubectl get volume -n storage "$PV" \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,NODE:.status.currentNodeID
# Which node is each pod on?
kubectl -n $NS get pods -o wide | grep "${PVC%%-images}"
# The attachment object itself
kubectl get volumeattachment -o json | python3 -c "
import sys,json
for a in json.load(sys.stdin)['items']:
    if a['spec']['source'].get('persistentVolumeName')=='$PV':
        print(a['metadata']['name'],'node=',a['spec']['nodeName'],'attached=',a['status'].get('attached'))"
```

Expected:
- `STATE=attached`, `NODE=<node A>`, while the pending pod is scheduled on node B.
  That mismatch **is** the diagnosis.

If unclear:
- `STATE=detaching` for more than a minute → Longhorn-side fault; see
  `docs/sops/longhorn.md`.

> **Triage note (house naming policy pays off here):** the Multi-Attach event prints
> the **PV name**. `plex-config` identified itself instantly; `pvc-629cc62f-96ea-…`
> required a `claimRef` lookup first. This is exactly the argument for the
> speaking-name `longhorn-static` rule in `docs/sops/longhorn.md`.

---

## 9) Health Check

Recurring sweep — enumerate every exposed workload cluster-wide. Safe, read-only.

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- kubectl get deploy -A -o json > /tmp/d.json
mise exec -- kubectl get pvc    -A -o json > /tmp/p.json
python3 - <<'EOF'
import json
D=json.load(open('/tmp/d.json'))['items']
pvc={(p['metadata']['namespace'],p['metadata']['name']):
     (p['spec'].get('accessModes',[]), p['spec'].get('storageClassName'))
     for p in json.load(open('/tmp/p.json'))['items']}
risk=ok=0
for d in D:
    ns,n = d['metadata']['namespace'], d['metadata']['name']
    if d['spec'].get('replicas',1)!=1: continue
    st = d['spec'].get('strategy',{}); ru = st.get('rollingUpdate',{})
    rwo=[(c,sc) for c,sc in
         ((v['persistentVolumeClaim']['claimName'],None) for v in
          (d['spec']['template']['spec'].get('volumes') or []) if v.get('persistentVolumeClaim'))
         for am,sc in [pvc.get((ns,c),([],'?'))] if 'ReadWriteOnce' in am]
    # only longhorn enforces attach; smb.csi.k8s.io has attachRequired=false
    rwo=[(c,sc) for c,sc in rwo if str(sc).startswith('longhorn')]
    if not rwo: continue
    surges = st.get('type')!='Recreate' and str(ru.get('maxSurge','25%'))not in ('0','0%')
    if surges:
        risk+=1; print(f"RISK {ns}/{n} strategy={st.get('type')} maxSurge={ru.get('maxSurge')} pvcs={[c for c,_ in rwo]}")
    else: ok+=1
print(f"\n{risk} exposed, {ok} safe (Recreate or maxSurge=0)")
EOF
```

Expected:
- `0 exposed`. Any `RISK` line is a latent stall waiting for the next image bump.

---

## 10) Security Check

This change alters rollout ordering only — no secret, RBAC, network, or storage
policy surface is touched. Confirm no collateral drift:

```bash
cd /Users/mu/code/cberg-home-nextgen
# The diff must contain ONLY strategy/updateStrategy keys
git diff HEAD~1 -- kubernetes/apps/ | grep '^[+-]' | grep -vE '^(\+\+\+|---)' | grep -vE '^\s*[+-]\s*#'
# No plaintext secrets introduced
mise exec -- grep -rIl "BEGIN .*PRIVATE KEY\|password:" kubernetes/apps/<ns>/<app>/ || echo "clean"
# SOPS files still encrypted
head -5 kubernetes/apps/<ns>/<app>/*.sops.yaml 2>/dev/null | grep -q "ENC\[" && echo "sops intact"
```

Expected:
- Diff contains only `strategy:` / `updateStrategy:` / `type: Recreate` plus comments.
- No decrypted secret material, no `replicas` change, no image change.
- **`replicas` must not be modified** — raising replicas on an RWO volume does not
  fix this and cannot work.

---

## 11) Rollback Plan

`strategy` lives outside the pod template, so reverting does not restart anything;
it only restores the previous (deadlock-prone) rollout ordering.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert <sha>
git push
# verify
mise exec -- flux get helmreleases -A | awk 'NR==1 || $5 != "True"'
mise exec -- kubectl -n <ns> get deploy <name> -o jsonpath='{.spec.strategy}{"\n"}'
```

Never `git reset --hard` or force-push (house rule). If a rollout is mid-flight and
wedged, the correct action is still to **wait** (§4.4), not to intervene on the
volume.

---

## 12) References

- `docs/sops/longhorn.md` — storage classes, static vs dynamic, speaking-name rule,
  volume lifecycle and detach/reattach procedures
- `docs/sops/storage-safety.md` — destructive PVC operations (CIFS/SMB/NFS)
- `docs/sops/new-deployment-blueprint.md` — default rollout SOP; new single-replica
  apps on RWO must ship `strategy: Recreate` from day one
- `kubernetes/apps/ai/open-webui/app/helmrelease.yaml` — earliest in-repo instance of
  this pattern (pipelines block)
- `kubernetes/apps/ai/librechat/app/helmrelease.yaml` — parent + bitnami subchart
  variant, two different values paths
- `kubernetes/apps/databases/postgresql/app/deployment.yaml` — plain-manifest variant
- Kubernetes: `maxSurge` rounds up, `maxUnavailable` rounds down —
  `pkg/controller/deployment/util/deployment_util.go` (`ResolveFenceposts`)
