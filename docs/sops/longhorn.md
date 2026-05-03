# SOP: Longhorn Storage

> Standard Operating Procedures for Longhorn distributed storage management.
> Reference: `docs/infrastructure.md` for storage overview, `docs/integration.md` for storage class selection.
> Description: Operating Longhorn storage classes, volumes, backups, and lifecycle workflows.
> Version: `2026.05.01`
> Last Updated: `2026-05-01`
> Owner: `Platform`

---

## Description

This SOP defines storage class usage, volume provisioning and troubleshooting for Longhorn-managed
persistent storage in the cluster.

> **Scope note**: this SOP covers Longhorn-only (block-level, single-PVC blast radius). For CIFS / SMB / NFS storage classes (which can wipe an entire shared filesystem on `kubectl delete pvc`), the governing SOP is `docs/sops/storage-safety.md`. Read that before any destructive operation on a CIFS/SMB/NFS PVC.

---

## Overview

Longhorn v1.11.1 provides distributed block storage with replication across all 3 cluster nodes.

| Setting | Value |
|---------|-------|
| Namespace | `storage` |
| Default replicas | 2 |
| Backup target | UNAS-CBERG (192.168.31.230) |
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

1. Choose `longhorn` or `longhorn-static` based on workload pattern.
2. Apply PVC/PV/Volume manifests through GitOps.
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

### Use `longhorn` (Dynamic Provisioning) For:
- Application databases (PostgreSQL, MariaDB, Redis, etc.)
- Application data that grows dynamically
- Cache volumes and StatefulSet volumes
- Any volume where automatic provisioning is preferred

**PV naming:** Auto-generated UUID (e.g., `pvc-df1999c2-c73c-4e54-a0a7-9f30571e8636`) — expected.

### Use `longhorn-static` For:
- Configuration directories with fixed, known size
- Volumes you want to manually manage and preserve
- Volumes that should survive namespace deletions
- Volumes requiring specific Longhorn settings
- Volumes where you need stable, human-readable PV names

**PV naming:** Human-readable, matching the Longhorn volume name.
**Important:** StatefulSet workloads should continue using `longhorn` dynamic provisioning.

### Naming Standards

For new PVCs, use descriptive names: `{app}-{purpose}`.

- ✅ `langfuse-postgresql-data` (`longhorn` → UUID PV is expected)
- ✅ `home-assistant-config` (`longhorn-static` → clean PV name)
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

### Automated Backups

Daily CronJob backs up all volumes at 3:00 AM:

```bash
# Check CronJob status
kubectl get cronjob backup-of-all-volumes -n storage

# View recent backup jobs
kubectl get jobs -n storage --sort-by='.status.startTime' | tail -10

# View backup job logs
kubectl logs -n storage job/{job-name} --tail=100
```

### Manual Backup (via UI)

1. Open Longhorn UI: `kubectl port-forward -n storage svc/longhorn-frontend 8080:80`
2. Navigate to Volumes → select volume → Create Backup
3. Verify backup appears in Backup page

### Check Backup Status

```bash
# Volume backup timestamps
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
