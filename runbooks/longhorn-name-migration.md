# Longhorn Name Migration Runbook

## Purpose
Procedure for migrating a `longhorn-static` PV that was incorrectly created with a UUID name to a properly named PV/PVC pair.

**When to use:** Only when a `longhorn-static` PV has a `pvc-*` UUID name. Dynamic `longhorn` PVs with UUID names are expected and do NOT require migration.

## Prerequisites
- `kubectl` access to the cluster
- Longhorn UI or `kubectl` access to the `storage` namespace
- The app using the PVC must be safely scalable to 0

## Procedure

### Step 1: Identify the volume to migrate
```bash
# Find longhorn-static PVs with UUID names (should be empty in a compliant cluster)
kubectl get pv -o custom-columns=PV:.metadata.name,SC:.spec.storageClassName --no-headers \
  | awk '$2=="longhorn-static" && $1 ~ /^pvc-/'
```

### Step 2: Scale down the workload
```bash
kubectl scale deployment {app} -n {namespace} --replicas=0
# Or for StatefulSets:
kubectl scale statefulset {app} -n {namespace} --replicas=0
```

### Step 3: Create a new Longhorn volume with a clean name
```yaml
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: {clean-name}    # e.g., "my-app-data" instead of "pvc-uuid"
  namespace: storage
spec:
  size: "{size-in-bytes}"
  numberOfReplicas: 2
  dataEngine: v1
  accessMode: rwo
  frontend: blockdev
  migratable: false
  encrypted: false
```

### Step 4: Backup data from old volume
Use Longhorn backup/restore or create a temporary pod to copy data.

### Step 5: Create new PV and PVC
```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: {clean-name}
spec:
  capacity:
    storage: {size}
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: longhorn-static
  csi:
    driver: driver.longhorn.io
    fsType: ext4
    volumeHandle: {clean-name}    # Must match Longhorn volume name
    volumeAttributes:
      numberOfReplicas: "2"
      staleReplicaTimeout: "30"
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {app}-data
  namespace: {namespace}
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: {size}
  storageClassName: longhorn-static
  volumeName: {clean-name}
```

### Step 6: Update app manifests to reference new PVC name
Edit the Deployment/StatefulSet to use the new PVC name.

### Step 7: Scale back up and verify
```bash
kubectl scale deployment {app} -n {namespace} --replicas=1
kubectl get pods -n {namespace} -w
```

### Step 8: Remove old PV/PVC
```bash
kubectl delete pvc {old-uuid-pvc} -n {namespace}
kubectl delete pv {old-uuid-pv}
```

### Step 9: Update tracking
Remove migrated entries from `runbooks/longhorn-name-migration-pending.md`.

## Rollback
Scale down the app, re-patch the PVC reference back to the old UUID PVC name, scale back up.

## See Also
- `runbooks/longhorn-name-migration-pending.md` — current list of UUID PVs
- `docs/sops/longhorn.md` — Longhorn storage class policy
