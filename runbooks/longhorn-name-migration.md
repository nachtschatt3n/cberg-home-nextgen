# Longhorn Compliant Volume Name Migration Runbook

## Purpose
Migrate non-compliant dynamic Longhorn volumes (UUID-style `pvc-*` PV names from `storageClassName: longhorn`) to compliant static names using `longhorn-static` and GitOps-only changes.

## Policy Summary
- Use `longhorn-static` when you need clean, human-readable PV names.
- For `longhorn-static`, create and manage three resources:
  - Longhorn `Volume` (`longhorn.io/v1beta2`) in namespace `storage`
  - Kubernetes `PersistentVolume` with `volumeHandle` matching Longhorn volume name
  - Kubernetes `PersistentVolumeClaim` with `volumeName` matching PV name
- Do not directly patch cluster objects manually outside GitOps.
- Do not migrate StatefulSet data volumes to static as a default path.

## When To Use
Use this runbook when:
- A live PV is named `pvc-<uuid>` and backed by `storageClassName: longhorn`
- You want deterministic volume names for lifecycle and operations

Do not use this runbook when:
- The workload is a StatefulSet volumeClaimTemplate (keep dynamic provisioning unless you redesign the workload)

## Prerequisites
- Cluster access (`kubectl` context configured)
- Flux/GitOps flow operational
- Planned maintenance window (data-copy cutover requires short downtime)
- Backup validated for the source volume

## 1. Identify Non-Compliant Candidates
```bash
# Longhorn PVs with UUID names (non-compliant by naming policy)
kubectl get pv -o custom-columns=PV:.metadata.name,SC:.spec.storageClassName,CLAIMNS:.spec.claimRef.namespace,CLAIM:.spec.claimRef.name --no-headers \
  | awk '$2=="longhorn" && $1 ~ /^pvc-/'
```

## 2. Confirm Workload Type
```bash
# Find PVC references and owning workloads
kubectl get pvc -A | grep '<claim-name>'
kubectl get deploy,statefulset -A | grep -i '<app-or-claim>'
```

If claim is owned by a StatefulSet `volumeClaimTemplate`, stop here and track as policy exception or redesign separately.

## 3. Plan Target Names
Use `{app}-{purpose}` naming.

Example mapping:
- Source PVC: `databases/redis-data`
- Source PV: `pvc-77167e86-f960-4f51-8ec1-c79c82684b06`
- Target Longhorn Volume/PV/PVC: `redis-data`

## 4. Add Static Volume Manifests In Git
In the app directory, add:
- `longhorn-volume.yaml`
- `pv.yaml`
- `pvc.yaml` (or update existing claim)
- include files in local `kustomization.yaml`

Template:
```yaml
---
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: redis-data
  namespace: storage
spec:
  size: "10737418240"  # 10Gi in bytes
  numberOfReplicas: 3
  dataEngine: v1
  accessMode: rwo
  frontend: blockdev
  migratable: false
  encrypted: false
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: redis-data
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
      numberOfReplicas: "3"
      staleReplicaTimeout: "30"
    volumeHandle: redis-data
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: redis-data
  namespace: databases
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: longhorn-static
  volumeName: redis-data
```

## 5. Switch Workload To New PVC Name (If Needed)
If PVC name is unchanged, no chart value changes are needed.

If you rename claim:
- update `existingClaim` or volume claim reference in `HelmRelease` / workload manifests
- commit and push via GitOps

## 6. Data Migration Cutover
1. Scale application down to zero replicas.
2. Start a one-off migration pod mounting both old and new PVCs.
3. Copy data with preserved attributes.
4. Scale app back up.

Example migration pod:
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: pvc-migrate-redis-data
  namespace: databases
spec:
  restartPolicy: Never
  containers:
    - name: migrate
      image: alpine:3.22
      command:
        - /bin/sh
        - -c
        - |
          set -e
          apk add --no-cache rsync
          rsync -aHAX --numeric-ids /src/ /dst/
      volumeMounts:
        - name: old
          mountPath: /src
        - name: new
          mountPath: /dst
  volumes:
    - name: old
      persistentVolumeClaim:
        claimName: redis-data-old
    - name: new
      persistentVolumeClaim:
        claimName: redis-data
```

## 7. Validate
```bash
# PV should now be cleanly named and static
kubectl get pv redis-data
kubectl get pvc -n databases redis-data -o wide

# Check binding details
kubectl get pv redis-data -o jsonpath='{.spec.storageClassName}{"\n"}{.spec.csi.volumeHandle}{"\n"}{.spec.claimRef.namespace}{"/"}{.spec.claimRef.name}{"\n"}'

# Confirm app health
kubectl get pods -n databases
kubectl logs -n databases deploy/redis --tail=100
```

## 8. Compliance Check (Cluster-Wide)
```bash
# Remaining non-compliant Longhorn dynamic UUID PVs
kubectl get pv -o custom-columns=PV:.metadata.name,SC:.spec.storageClassName,CLAIMNS:.spec.claimRef.namespace,CLAIM:.spec.claimRef.name --no-headers \
  | awk '$2=="longhorn" && $1 ~ /^pvc-/'

# Sanity: longhorn-static should not have UUID PV names
kubectl get pv -o custom-columns=PV:.metadata.name,SC:.spec.storageClassName --no-headers \
  | awk '$2=="longhorn-static" && $1 ~ /^pvc-/'
```

## Rollback Plan
If workload fails after cutover:
1. Scale workload down.
2. Revert Git commit that switched claim/storage.
3. Push revert and wait for Flux reconciliation.
4. Scale workload back up on old PVC.
5. Keep new static volume for forensic comparison until issue is resolved.

## Troubleshooting
- PVC Pending on static claim:
  - Confirm `Volume` exists in `storage` namespace.
  - Confirm PV `csi.volumeHandle` exactly matches Longhorn `Volume.metadata.name`.
  - Confirm PVC `volumeName` exactly matches PV `metadata.name`.
- App starts but data missing:
  - Verify migration pod copied expected paths.
  - Re-run `rsync -aHAX --numeric-ids` with app scaled down.
- Flux applies fail:
  - Check `kustomization.yaml` includes all new files.
  - Validate manifests before commit.

## Validation Commands Before Commit
```bash
# Template and schema checks from repo standards
task template:configure -- --strict
kubeconform -summary -fail-on error kubernetes/apps/
```

## Notes
- Keep old PVC/PV until post-cutover validation is complete.
- Remove old resources in a separate cleanup PR after a stable observation window.
