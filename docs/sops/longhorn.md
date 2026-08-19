# SOP: Longhorn Storage

> Standard Operating Procedures for Longhorn distributed storage management.
> Reference: `docs/infrastructure.md` for storage overview, `docs/integration.md` for storage class selection.
> Description: Operating Longhorn storage classes, volumes, backups, and lifecycle workflows.
> Version: `2026.08.19`
> Last Updated: `2026-08-19`
> Owner: `Platform`

---

## Description

This SOP defines storage class usage, volume provisioning and troubleshooting for Longhorn-managed
persistent storage in the cluster.

> **Scope note**: this SOP covers Longhorn-only (block-level, single-PVC blast radius). For CIFS / SMB / NFS storage classes (which can wipe an entire shared filesystem on `kubectl delete pvc`), the governing SOP is `docs/sops/storage-safety.md`. Read that before any destructive operation on a CIFS/SMB/NFS PVC.

---

## Overview

Longhorn v1.11.2 provides distributed block storage with replication across all 3 cluster nodes.

| Setting | Value |
|---------|-------|
| Namespace | `storage` |
| Default replicas | 2 |
| Backup target | UNAS-CBERG (192.168.55.240) |
| Backup schedule | Daily CronJob at 3:00 AM |
| Storage classes | `longhorn` (dynamic), `longhorn-static` (manual) |
| Default disk reserve | `storageReservedPercentageForDefaultDisk: 20` (was 30; lowered 2026-05-01 in `kubernetes/apps/storage/longhorn/app/helmrelease.yaml` to free scheduling headroom on nuc14-03 — see commit `a48ef1c2`). Changing the helm value only affects newly-discovered disks; existing disks need a per-node `kubectl -n storage patch nodes.longhorn.io <node> --type=merge -p '{"spec":{"disks":{"default-disk-...":{"storageReserved":<bytes>}}}}'`. |

---

## Blueprints

N/A for dedicated Authentik-style blueprints.

Declarative source-of-truth:
- Longhorn deployment config: `kubernetes/apps/storage/longhorn/`
- Application PVC/PV manifests: `kubernetes/apps/**/app/`

---

## Operational Instructions

1. Default to `longhorn-static` with a speaking name; use `longhorn` only
   where a name is impossible (StatefulSet volumeClaimTemplates).
2. Apply the PV + PVC through GitOps. The Longhorn `Volume` CR must be applied
   MANUALLY (`kubectl apply -f .../longhorn-volume.yaml`) and kept OUT of
   `app/kustomization.yaml` — Flux's `targetNamespace` would override its
   `namespace: storage` and create a broken duplicate.
3. Validate attachment, mount, and workload readiness.
4. Verify backups and health before major upgrades.

---

## Examples

### Example 1: Dynamic PVC

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-app-data
  namespace: my-namespace
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 10Gi
  storageClassName: longhorn
```

### Example 2: Static PVC Binding

```yaml
spec:
  storageClassName: longhorn-static
  volumeName: my-app-config
```

---

## Verification Tests

### Test 1: Volume Health and Binding

```bash
kubectl get volumes -n storage
kubectl get pv,pvc -A | grep {app-name}
```

Expected:
- Volume robustness/health is normal and PVCs are bound.

If failed:
- Check troubleshooting and event logs.

### Test 2: Backup State

```bash
kubectl get cronjob backup-of-all-volumes -n storage
kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt
```

Expected:
- Backup job exists and volumes show recent backup timestamps.

> **Caveat:** `lastBackupAt` can lag a full backup cycle even when the backup
> succeeded (backup-store `volume.cfg` rewrite lost under parallel load) —
> confirm via the volume's Completed Backup CRs before declaring it stale.
> See `docs/sops/backup.md` → Troubleshooting: "lastBackupAt Can Lag".

If failed:
- Check Longhorn backup target and controller logs.

---

## Access Longhorn UI

```bash
# Port-forward to Longhorn UI
kubectl port-forward -n storage svc/longhorn-frontend 8080:80 &
# Open http://localhost:8080
```

---

## Storage Class Selection

### Default: `longhorn-static` — volumes MUST have speaking names

**Use `longhorn-static` unless a name is technically impossible.** This is the
house standard and the cluster majority (50 static / 33 dynamic, 48 named PVs).

Why the PV name matters more than it looks: the Longhorn UI, the backup list,
and every restore/DR procedure are keyed on the **PV** name, not the PVC. A
`pvc-<uuid>` PV means that when a volume is degraded or you are restoring from
backup at 02:00, you cannot tell what you are looking at without a `claimRef`
lookup — precisely when you least want an extra indirection.

Applies to: configuration directories, application databases, any volume you
would want to find in a backup list, anything that should survive a namespace
deletion, anything needing specific Longhorn settings.

**PV naming:** human-readable, and the **same identifier everywhere** — the
Longhorn `Volume`, the `PV`, the PVC's `volumeName`, the PV's `volumeHandle`
and the PVC name are all `{app}-{purpose}`.

### Use `longhorn` (Dynamic, UUID PV) only when a name is impossible

- **StatefulSet `volumeClaimTemplates`** — one PVC is generated per replica at
  scale time, so you cannot pre-create PVs for replicas that do not exist yet.
  This is the main legitimate case.
- Genuinely ephemeral or trivially recreatable scratch/cache data.

**PV naming:** auto-generated UUID (e.g. `pvc-df1999c2-…`) — unavoidable here,
and only here.

### The one cost of a static volume — do not let it push you back to dynamic

The Longhorn `Volume` CR needs **one manual `kubectl apply`**. Flux cannot own
it: the app Kustomization's `targetNamespace` silently overrides the CR's
`namespace: storage`, producing a duplicate in the app namespace that Longhorn
does not manage. Keep `longhorn-volume.yaml` in the app folder as
version-controlled source, apply it by hand once, and let Flux manage `pv.yaml`
and the PVC.

If you skip it the PVC sits `Pending` — that is the expected failure mode and a
prompt to apply the Volume, **not** a reason to switch to dynamic provisioning.

### Naming Standards

For new PVCs, use descriptive names: `{app}-{purpose}`.

- ✅ `home-assistant-config` (`longhorn-static` → clean PV name) — the default
- ✅ `data-authentik-postgresql-0` (StatefulSet template → UUID PV is expected)
- ❌ Reaching for `longhorn` just to avoid the manual Volume-CR apply
- ❌ Manually creating UUID-like PV names for static volumes

---

## Creating a Dynamic Volume (longhorn)

Simply create a PVC — Longhorn provisions the volume automatically:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-app-data
  namespace: my-namespace
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: longhorn
```

---

## Creating a Static Volume (longhorn-static)

Static volumes require 3 steps: Longhorn Volume → PersistentVolume → PersistentVolumeClaim.

### Step 1: Create Longhorn Volume (via UI or CRD)

```yaml
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: my-app-config
  namespace: storage
spec:
  size: "10737418240"    # 10Gi in bytes (N * 1024^3)
  numberOfReplicas: 2
  dataEngine: v1
  accessMode: rwo        # rwo = ReadWriteOnce, rw = ReadWriteMany
  frontend: blockdev     # Required!
  migratable: false
  encrypted: false
```

Wait for volume to be in `detached` or `available` state before proceeding.

### Step 2: Create PersistentVolume

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: my-app-config    # Must match Longhorn volume name
spec:
  capacity:
    storage: 10Gi
  volumeMode: Filesystem
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: longhorn-static
  csi:
    driver: driver.longhorn.io
    fsType: ext4
    volumeAttributes:
      numberOfReplicas: "2"
      staleReplicaTimeout: "30"
    volumeHandle: my-app-config    # Must exactly match Longhorn volume name!
```

### Step 3: Create PersistentVolumeClaim

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-app-config
  namespace: my-namespace
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: longhorn-static
  volumeName: my-app-config    # Bind to specific PV
```

---

## Volume Operations

### Expand a Volume

1. Edit the PVC to increase `resources.requests.storage`
2. Longhorn will expand the underlying volume online (no downtime for Filesystem volumes)
3. The pod may need to be restarted for the OS to recognize the new size

```bash
kubectl patch pvc {pvc-name} -n {namespace} \
  -p '{"spec":{"resources":{"requests":{"storage":"20Gi"}}}}'
```

### Detach and Reattach a Volume

```bash
# Check current attachment
kubectl get volume {volume-name} -n storage -o jsonpath='{.status.state}'

# Detach: scale down the workload first
kubectl scale deployment {name} -n {namespace} --replicas=0

# Volume should auto-detach after pod terminates
# Re-attach by scaling back up
kubectl scale deployment {name} -n {namespace} --replicas=1
```

### RWO Multi-Attach on Rollout — see dedicated SOP

A single-replica **Deployment** mounting a ReadWriteOnce volume will stall on
`FailedAttachVolume` / `Multi-Attach error` when rolled under the default
`RollingUpdate` strategy: at `replicas: 1`, `maxSurge: 25%` rounds **up** to 1
(a second pod is created) while `maxUnavailable: 25%` rounds **down** to 0 (the
old pod may not be released) — a circular wait on the volume.

It clears **nondeterministically** (the retry has to land the new pod on the node
already holding the attachment), so it looks different every time. The old pod
keeps serving throughout, so it is a stuck rollout, not an outage.

Durable fix is `spec.strategy.type: Recreate`. StatefulSets are immune to the
deadlock (they terminate before recreating).

**Do not** delete the old pod, scale to 0, or force-detach the volume to "unstick"
it — the old pod is the one still serving, and forcing a detach on a live
read-write volume risks data-path damage.

Full procedure, per-chart values paths, diagnose flows and the cluster-wide sweep:
**[`docs/sops/longhorn-rwo-multi-attach.md`](longhorn-rwo-multi-attach.md)**.

### Delete a Volume

⚠️ **Irreversible if reclaimPolicy is Delete.** Always verify backups first.

```bash
# For dynamic volumes (longhorn): deleting PVC deletes PV and data
kubectl delete pvc {pvc-name} -n {namespace}

# For static volumes (longhorn-static): PV reclaimPolicy is Retain
# Must delete PV and Longhorn volume separately
kubectl delete pvc {pvc-name} -n {namespace}
kubectl delete pv {pv-name}
kubectl delete volume {volume-name} -n storage
```

---

## Backup Procedures

### Recurring Jobs (Longhorn-native, not Kubernetes CronJobs)

Longhorn's own RecurringJob CRDs handle backup, snapshot-cleanup, and
filesystem-trim. They live in `kubernetes/apps/storage/longhorn/recurringjobs/`
and apply to every volume in Longhorn's `default` group (which is every
volume by default — no explicit `recurring-job-selector` annotation needed).

Daily schedule (UTC):

| Time  | Job                       | Effect |
|-------|---------------------------|--------|
| 02:00 | `global-filesystem-trim`  | `fstrim` inside every volume — releases freed-but-still-allocated blocks back to Longhorn |
| 02:30 | `global-snapshot-cleanup` | Deletes user-created snapshots that aren't kept by `retain` rules — picks up orphans the per-backup auto-cleanup misses |
| 03:00 | `daily-backup-all-volumes`| Backs up all volumes to the CIFS target (`192.168.55.240/backups`), `retain: 1` |

```bash
# Inspect the recurring job pipeline
kubectl get recurringjobs.longhorn.io -n storage

# View recent backup CR state
kubectl get backups.longhorn.io -n storage --sort-by='.status.snapshotCreatedAt' | tail -10

# Check the auto-cleanup setting that complements snapshot-cleanup
kubectl get setting.longhorn.io -n storage auto-cleanup-recurring-job-backup-snapshot
```

> **`filesystem-trim` only reclaims space the *application* has freed.**
> A `LonghornVolumeUsage{Warning,Critical,Emergency}` alert (thresholds
> 80/90/99% of `actualSize / capacity`) on a high-churn volume usually
> means the app isn't deleting its own data — trim then has nothing to
> release and the volume legitimately fills with live data. Diagnose
> with `df -h` inside the pod vs Longhorn's `actualSize`:
>
> - **`df` high AND actualSize high** → real data; fix the app's
>   retention (don't just trim). 2026-05-29 incident: the ES OTel
>   datastreams (`metrics-generic.otel-default`, `logs-generic-default`)
>   carried `index.lifecycle.prefer_ilm: true` under the Elastic built-in
>   `logs`/`metrics` ILM policies (no delete phase), so their DSL
>   `data_retention` was silently ignored and indices grew unbounded back
>   ~48 days. Fix: `prefer_ilm: false` so Data Stream Lifecycle governs
>   deletion (see `kubernetes/apps/monitoring/elasticsearch/app/otel-ilm-job.yaml`).
> - **`df` low BUT actualSize high** → data already deleted, blocks not
>   yet reclaimed. The 02:00 `global-filesystem-trim` fixes this nightly;
>   for an immediate reclaim, trigger it via the Longhorn API:
>   `POST /v1/volumes/<pv-name>?action=trimFilesystem` (port-forward
>   `svc/longhorn-frontend:80`). In-pod `fstrim` fails — the workload
>   container lacks `CAP_SYS_ADMIN`.

### Manual Backup (via UI)

1. Open Longhorn UI: `kubectl port-forward -n storage svc/longhorn-frontend 8080:80`
2. Navigate to Volumes → select volume → Create Backup
3. Verify backup appears in Backup page

### Check Backup Status

```bash
# Volume backup timestamps (NOTE: lastBackupAt can lag one cycle — cross-check
# Backup CRs, see docs/sops/backup.md "lastBackupAt Can Lag")
kubectl get volumes -n storage \
  -o custom-columns=NAME:.metadata.name,SIZE:.spec.size,LAST_BACKUP:.status.lastBackupAt

# List all backups (via Longhorn CLI or UI)
kubectl exec -n storage deploy/longhorn-manager -- \
  longhorn-manager backup list 2>/dev/null || echo "Use UI instead"
```

### Restore a Volume from Backup

1. Open Longhorn UI
2. Navigate to Backup
3. Select backup → Restore → provide new volume name
4. After restore, create PV and PVC pointing to the restored volume

---

## Troubleshooting

### PV `Released` / PVC `Pending` — "volume already bound to a different claim"

Happens when the PVC was deleted+recreated (helm chart renamed the generated
PVC, a rollback recreated it, etc.): the PV keeps the DELETED claim's uid in
`spec.claimRef`, so the same-named new PVC cannot bind. With `Retain` PVs the
data is safe; the fix is one patch — clear the stale binding, never delete:

```bash
kubectl patch pv <pv-name> --type json \
  -p '[{"op":"remove","path":"/spec/claimRef/uid"},{"op":"remove","path":"/spec/claimRef/resourceVersion"}]'
# PV -> Available; the Pending PVC (with matching volumeName/name) binds within seconds.
```

Prevention: chart-generated PVC names can CHANGE across chart majors
(app-template 5.x drops `-<key>` for single-item persistence — pin with
`persistence.<key>.suffix`). Flux-static PVC manifests are immune and match
the house speaking-name convention — prefer them. Details:
`docs/sops/application-update.md` §7b.

### Volume Stuck in Attaching State

```bash
# Check pod events
kubectl describe pod {pod-name} -n {namespace} | grep -A10 "Events:"

# Check volume state
kubectl get volume {volume-name} -n storage -o yaml | grep -A5 "status:"

# Force detach (use with care)
# Via Longhorn UI: Volume → Force Detach
```

### Volume Not Mounting (Access Mode Mismatch)

```bash
# Check PVC access modes
kubectl get pvc {pvc-name} -n {namespace} -o jsonpath='{.spec.accessModes}'

# Check Longhorn volume access mode
kubectl get volume {volume-name} -n storage -o jsonpath='{.spec.accessMode}'

# PV and PVC access modes must match the Longhorn volume access mode
```

### Common Mistakes

| Mistake | Error | Fix |
|---------|-------|-----|
| Creating PV before Longhorn Volume | "volume not found" | Create Longhorn Volume first |
| Mismatched `volumeHandle` | Volume fails to attach | PV's `volumeHandle` must exactly match Longhorn volume name |
| Missing `frontend: blockdev` | "invalid volume frontend" | Add `frontend: blockdev` to Volume spec |
| StatefulSet with `longhorn-static` | Provisioning fails | Use `longhorn` (dynamic) for StatefulSets |

### Debugging Commands

```bash
# All volumes with status
kubectl get volumes -n storage

# PV/PVC binding overview
kubectl get pv,pvc -A | grep {app-name}

# Volume detail
kubectl describe volume {volume-name} -n storage

# Storage events
kubectl get events -n {namespace} --field-selector type=Warning

# Volume attachment to pod
kubectl describe pod {pod-name} -n {namespace} | grep -A10 "Volumes:"

# Longhorn manager logs
kubectl logs -n storage -l app=longhorn-manager --tail=50 | grep -i error
```

### Replica Rebuild Loop (cleanupReplicaInUnstableEnv)

**Symptom:** A volume has more replicas than `numberOfReplicas` specifies, or a replica is repeatedly rebuilt, deleted, and rebuilt on the same node.

**Root cause:** When a cluster node experiences a Kubernetes Ready condition transition (even a brief blip), Longhorn marks that node as "unstable" by comparing the `lastTransitionTime` of each node's Ready condition. Any replica on a node whose Ready transition is 30+ minutes newer than the oldest-transitioned node is considered suspect and deleted by `cleanupReplicaInUnstableEnv`. If auto-balance then places a new replica on a node that already has a healthy replica (because the "unstable" node is the only remaining option), a duplicate forms — which triggers another cleanup cycle.

**Identify the loop:**

```bash
# List all replicas and their current state
kubectl get replicas.longhorn.io -n storage | grep -E "stopped|error"

# See which volumes have extra/duplicate replicas (more than spec)
kubectl get replicas.longhorn.io -n storage -o json | python3 -c "
import sys, json
from collections import defaultdict
data = json.load(sys.stdin)
vol = defaultdict(list)
for r in data['items']:
    vol[r['spec']['volumeName']].append((r['metadata']['name'], r['spec']['nodeID'], r['status'].get('currentState','?')))
for v, replicas in vol.items():
    nodes = [r[1] for r in replicas if r[2] == 'running']
    if len(nodes) != len(set(nodes)):
        print(f'{v}: DUPLICATE NODE - {[(r[0], r[1], r[2]) for r in replicas]}')
"

# Check Longhorn manager logs for cleanup trigger
kubectl logs -n storage -l app=longhorn-manager --tail=200 | grep -i "cleanupReplicaInUnstableEnv\|kube node ready transition"
```

**Fix — delete the duplicate replica:**

```bash
# Identify which replica is the duplicate (same node as another healthy replica)
kubectl get replicas.longhorn.io -n storage -l longhornvolume={volume-name} \
  -o custom-columns=NAME:.metadata.name,NODE:.spec.nodeID,STATE:.status.currentState

# Delete the stopped/duplicate replica (NOT the healthy running one)
kubectl delete replica.longhorn.io {replica-name} -n storage

# Longhorn will then rebuild one healthy replica per node (no duplicate = no cleanup loop)
```

**Confirm rebuild completion:**

```bash
# Wait for volume to return to healthy/robust state
kubectl get volume {volume-name} -n storage -o jsonpath='{.status.robustness}'
# Expected: "healthy"

# Verify replica count matches spec (one per distinct node)
kubectl get replicas.longhorn.io -n storage -l longhornvolume={volume-name} \
  -o custom-columns=NAME:.metadata.name,NODE:.spec.nodeID,STATE:.status.currentState
# Expected: numberOfReplicas rows, each on a distinct node, all state=running
```

### Chart Upgrade Storm — dozens of Kustomizations go not-Ready at once

**Symptom.** Minutes into a routine Longhorn chart upgrade, `flux get
kustomizations -A` shows a cluster-wide failure — 60 Kustomizations not-Ready
in the 2026-08-19 window — across namespaces that have nothing to do with each
other:

```
databases    memgraph        False   dependency 'storage/longhorn' is not ready
monitoring   grafana         False   dependency 'storage/longhorn' is not ready
office       vaultwarden     False   dependency 'storage/longhorn' is not ready
...
```

with `storage` events showing:

```
Warning  Unhealthy  pod/longhorn-manager-<id>  Readiness probe failed:
         Get "https://10.x.x.x:9502/v1/healthz": connect: connection refused
Warning  FailedPreStopHook  pod/longhorn-csi-plugin-<id>  PreStopHook failed
```

**This is expected and self-clearing. Do not roll it back.** Nothing is
broken, no PVC is lost, and no running workload is evicted.

**Why it happens.** The Longhorn **admission webhook is served by
`longhorn-manager` itself on port 9502** — there is no separate webhook
Deployment to check (`kubectl get deploy -n storage | grep webhook` returns
nothing, which misleads people into thinking the webhook is gone). A chart
upgrade rolls the `longhorn-manager` **DaemonSet**, so for the span of that
roll the `longhorn-admission-webhook` Service has **no healthy endpoints**, and
`longhorn-webhook-validator` / `longhorn-webhook-mutator` have nothing to call.

That produces a two-layer cascade, and the second layer is what makes it look
catastrophic:

1. Manager pods fail readiness → the `storage/longhorn` HelmRelease and
   Kustomization go not-Ready.
2. **36 Kustomizations declare `dependsOn: storage/longhorn`**, and Flux fans
   the failure out to every one of them plus their transitive dependents
   (`monitoring/grafana` → `monitoring/unpoller`, and so on). Those downstream
   Kustomizations never touched a Longhorn object — they are reporting their
   *dependency's* state, which is why the blast radius looks unrelated to
   storage.

**Confirm it is CLEARING, not wedged.** Check the storage layer first, then
judge recovery by REVISION CONVERGENCE — not by the not-Ready count:

```bash
# 1) The webhook must repopulate to one endpoint per node (3 here).
mise exec -- kubectl get endpoints -n storage longhorn-admission-webhook
#    healthy: 10.69.0.157:9502,10.69.1.246:9502,10.69.2.183:9502
#    mid-roll: fewer, or <none>  -> still rolling, keep waiting

# 2) The DaemonSet must converge to DESIRED == READY.
mise exec -- kubectl get ds -n storage longhorn-manager

# 3) The HelmRelease.
mise exec -- flux get helmrelease -n storage longhorn

# 4) THE clearing test: how many Kustomizations are not yet at HEAD.
HEAD=$(git rev-parse --short HEAD)
mise exec -- flux get kustomizations -A | grep -cv "$HEAD"
```

**Steps 1-3 are necessary but NOT sufficient, and the gap is large enough to
fool you.** Measured in the 2026-08-19 window: the manager pods came up at
05:55:36Z and the webhook endpoints were fully repopulated within a minute —
yet **27 Kustomizations were still not-Ready at 06:09, and 26 at 06:10**. The
storm ran for roughly **15 minutes after the "load-bearing" signal went
green.** An operator who expects the dependents to follow the endpoints
promptly will read that tail as wedged and roll back a healthy cluster.

**Do not use the not-Ready COUNT as the clearing test.** It does not fall
monotonically — it churns, with near-total membership turnover between polls.
Across one 90-second interval in that window, 12 Kustomizations left the
not-Ready set and 12 *different* ones entered it, while the count moved only
27 → 26. Kustomizations were going not-Ready **while the webhook was already
healthy**, which is the observation that exposes a second mechanism:

> **Flux's `dependsOn` is revision-gated, not merely readiness-gated**, and a
> new revision makes every Kustomization re-reconcile — including the ones
> others depend on. A dependent will not proceed until its dependency has
> applied *the same source revision the dependent is at*, and any dependent
> that evaluates the gate while the dependency is mid-reconcile records a
> failure. **Both** `revision is not up to date` **and** `is not ready` appear
> during this, and neither implies a fault: the messages are last-attempt
> snapshots, so a healthy `storage/longhorn` can be advertised as broken by a
> dozen dependents for a full reconcile interval. Never triage on the
> dependents' text — ask `storage/longhorn` itself. So **every new commit you
> push re-arms the gate** for all
> 36 direct dependents plus their transitive dependents, staggered by each
> one's own reconcile interval. Three commits in 190 seconds (as happened here)
> will keep the set rotating long after Longhorn is fine — with *zero* Longhorn
> involvement. Full mechanism, including why this is not Longhorn-specific:
> [`docs/sops/flux-dependency-revision-gate.md`](flux-dependency-revision-gate.md).

Practical consequence: **stop pushing commits while you are trying to judge
whether the storm has cleared**, or you are re-arming the thing you are
measuring. Revision convergence (step 4) is monotonic per-revision and is the
signal to trust.

Flux retries dependents on its own interval, so they recover without
intervention — resist the urge to `flux reconcile` each one, which only adds
load while the webhook is still down.

**When it IS wedged** (act only if these hold):

- `longhorn-manager` DaemonSet stuck below DESIRED for **more than ~10 minutes**
  with no progress, or
- the webhook endpoint list stays empty while manager pods report Ready
  (a Service selector / label mismatch, not an upgrade artefact), or
- the not-Ready set stops *changing membership* between polls (a static set is
  a stall; a rotating set is progress) **and** manager pods are
  `CrashLoopBackOff` rather than `Terminating`/`ContainerCreating`.

Then diagnose the manager roll itself (`kubectl -n storage logs ds/longhorn-manager
--previous`), not the downstream Kustomizations — every one of those is a
symptom.

**`FailedPreStopHook` on `longhorn-csi-plugin` is noise here.** The plugin pods
are being replaced in the same roll and their pre-stop hook tries to reach the
manager that is already gone. It does not indicate data-path damage.

**Planning note.** Because the dependency fan-out is this wide, a Longhorn
chart upgrade is not a "storage-only" window — schedule it where a 5-15 minute
cluster-wide Flux amber is acceptable, and tell whoever is watching the board,
or they will page on a healthy cluster.

### Stale Stopped Replicas

After a node failure or replacement, stopped replicas may accumulate on the old node without triggering an active rebuild loop.

```bash
# Find all stopped replicas
kubectl get replicas.longhorn.io -n storage | grep stopped

# Identify the volume and node for each stopped replica
kubectl get replicas.longhorn.io -n storage -o custom-columns=\
NAME:.metadata.name,VOLUME:.spec.volumeName,NODE:.spec.nodeID,STATE:.status.currentState \
| grep stopped

# Delete stopped replica — Longhorn will schedule a rebuild on a healthy node
kubectl delete replica.longhorn.io {replica-name} -n storage
```

Only delete replicas whose volume still has `numberOfReplicas` healthy `running` replicas elsewhere — otherwise deleting a stopped replica reduces redundancy below spec and Longhorn will immediately begin a rebuild, which is fine if you have healthy replicas remaining.

---

## Maintenance

### Pre-upgrade Checks (before Longhorn upgrade)

```bash
# Ensure all volumes are healthy
kubectl get volumes -n storage | grep -v healthy

# Ensure no degraded replicas
kubectl get volumes -n storage -o jsonpath='{.items[*].status.robustness}' | tr ' ' '\n' | sort | uniq -c

# Take manual backups of critical volumes
# Run backup-of-all-volumes job manually if needed
kubectl create job --from=cronjob/backup-of-all-volumes manual-backup-$(date +%Y%m%d) -n storage
```

### Longhorn Version Upgrade via Flux

1. Update chart version in HelmRelease: `kubernetes/apps/storage/longhorn/app/helmrelease.yaml`
2. Commit and push — Flux will apply the upgrade
3. Monitor: `kubectl rollout status -n storage deployment/longhorn-manager`
4. Verify volumes return to healthy state after upgrade

---

## Diagnose Examples

### Diagnose Example 1: Volume Stuck Attaching

```bash
kubectl describe pod {pod-name} -n {namespace} | rg -A10 "Events:"
kubectl get volume {volume-name} -n storage -o yaml | rg -A8 "status:"
```

Expected:
- Events/status point to node, access mode, or attachment conflict.

If unclear:
- Check `longhorn-manager` logs for attach/detach errors.

### Diagnose Example 2: PVC Not Binding

```bash
kubectl get pv {pv-name} -o yaml | rg "storageClassName|volumeHandle|accessModes"
kubectl get pvc {pvc-name} -n {namespace} -o yaml | rg "storageClassName|volumeName|accessModes"
```

Expected:
- Matching storageClass/access modes and valid `volumeHandle`.

If unclear:
- Validate Longhorn volume exists and is ready.

### Diagnose Example 3: Replica Rebuild Loop After Node Readiness Blip

**Incident (2026-04-30):** Volumes `memgraph-data` and `otbr-data` entered a rebuild loop after node `k8s-nuc14-02` had a brief Ready condition transition at 20:08:30Z.

```bash
# Step 1: Identify duplicate replicas
kubectl get replicas.longhorn.io -n storage | grep -v running

# Step 2: Confirm it's a duplicate (same volume, same node, two replicas)
kubectl get replicas.longhorn.io -n storage -l longhornvolume=memgraph-data \
  -o custom-columns=NAME:.metadata.name,NODE:.spec.nodeID,STATE:.status.currentState

# Step 3: Confirm loop in manager logs
kubectl logs -n storage -l app=longhorn-manager --tail=200 \
  | grep "kube node ready transition"
# Output: "Deleting replica ... on node k8s-nuc14-02 since its kube node ready
#          transition time 2026-04-30T20:08:30Z is over 30 minutes later than others"

# Step 4: Delete the stopped duplicate (the one on nuc14-03 created by auto-balance)
kubectl delete replica.longhorn.io pvc-2455ee11...-r-6ab39efe -n storage
kubectl delete replica.longhorn.io pvc-e90ffdf6...-r-1bb03f00 -n storage

# Step 5: Verify loop broken — all volumes reach robustness=healthy within ~30s
kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,ROBUSTNESS:.status.robustness
```

---

## Health Check

```bash
kubectl get volumes -n storage
kubectl get jobs -n storage --sort-by='.status.startTime' | tail -10
kubectl get events -n storage --field-selector type=Warning --sort-by='.lastTimestamp' | tail -20
```

Expected:
- Volumes healthy, recent backup jobs successful, and no unresolved warning events.

---

## Security Check

```bash
# Ensure Longhorn-related secrets remain encrypted in Git
find kubernetes/apps/storage/longhorn -name '*.sops.yaml' -print
```

Expected:
- Sensitive credentials/config remain SOPS-encrypted.

---

## Rollback Plan

```bash
# Revert Longhorn config changes if storage regressions occur
git log -- kubernetes/apps/storage/longhorn
git revert <commit-sha>
git push
```

Rollback validation:
- Re-run `Verification Tests` and `Health Check`.
