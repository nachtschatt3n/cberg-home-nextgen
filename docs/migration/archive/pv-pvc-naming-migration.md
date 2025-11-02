# PV/PVC Naming Migration Guide

## Overview

This document provides a strategy for migrating PVs/PVCs with non-standard (UUID-based) names to follow the naming convention: `{app-name}-{purpose}`.

## Standard Naming Convention

- **PVC Name**: `{app-name}-{purpose}` (e.g., `langfuse-clickhouse-data`)
- **PV Name**: Same as PVC name (using longhorn-static storage class)
- **Storage Class**: `longhorn-static` for all static volumes

## Volumes Requiring Migration

### AI Namespace (8 volumes)
- `ai-sre-cache` → PV: `pvc-4b56f40c-1ca9-4c4a-983c-298ea068da6c`
- `ai-sre-logs` → PV: `pvc-ec7762c0-cbbc-4a06-afd2-344950fe0159`
- `ai-sre-storage` → PV: `pvc-e61d2327-5207-4c77-83aa-90620762ff46`
- `bytebot-desktop-data` → PV: `pvc-bcfd3aa6-26da-4f5c-a77e-9e7f240338b8`
- `bytebot-postgres-data` → PV: `pvc-0763a3a5-047e-4037-bda3-7451c27ed4e8`
- `langfuse-clickhouse-pvc` → PV: `pvc-358a8432-1f52-4a67-bec5-266d43913213` (rename PVC to `langfuse-clickhouse-data`)
- `langfuse-minio-data` → PV: `pvc-1ba140e7-9bc4-4b2e-84d7-7f59e5ae19a6`
- `langfuse-postgresql-pvc` → PV: `pvc-df1999c2-c73c-4e54-a0a7-9f30571e8636` (rename PVC to `langfuse-postgresql-data`)

### Custom-Code-Production Namespace (4 volumes)
- `absenty-development-data` → PV: `pvc-21ce9616-5090-45c3-b361-5773b1541374`
- `absenty-development-storage` → PV: `pvc-9d2ccc74-d470-41bf-97da-f5b0b43feafa`
- `absenty-production-data` → PV: `pvc-dfc96bed-6efd-45cd-9dbd-4caf6f6b50e2`
- `absenty-production-storage` → PV: `pvc-9dabc41c-f75a-4064-a517-adae1a33addc`

### Other Namespaces (10+ volumes)
- databases/`mariadb-data` → PV: `pvc-5a16b42b-dcbe-4201-b28b-b0fea61a7bbf`
- download/`tube-archivist-*` (3 volumes)
- kube-system/authentik volumes (2 volumes)
- media/`makemkv-config` → PV: `pvc-ce4c31cb-e83a-41b8-8f31-bd9b34d622f3`
- monitoring/alertmanager, prometheus, rybbit (3 volumes - rybbit will be removed)
- office/`redis-data-nextcloud-redis-master-0` → PV: `pvc-9ffddc11-34d9-4017-b058-e70bce18fe17`

### Special Cases
- `scrypted-data` (PVC) → `scrypted-config` (PV) - naming mismatch, already being fixed

## Migration Process (Per Volume)

### Prerequisites
- Backup all data before starting
- Schedule during maintenance window
- Expect 10-30 minutes downtime per volume

### Step-by-Step Migration

#### 1. Prepare New Static PV and PVC

```yaml
# Create: kubernetes/apps/{namespace}/{app}/app/pv-{name}.yaml
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: {new-pv-name}  # e.g., langfuse-clickhouse-data
  namespace: {namespace}
spec:
  capacity:
    storage: {size}  # Match old PV size
  volumeMode: Filesystem
  accessModes:
    - ReadWriteOnce  # or ReadWriteMany based on original
  persistentVolumeReclaimPolicy: Retain
  storageClassName: longhorn-static
  csi:
    driver: driver.longhorn.io
    fsType: ext4
    volumeAttributes:
      numberOfReplicas: "3"
      staleReplicaTimeout: "30"
    volumeHandle: {new-pv-name}
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {new-pvc-name}
  namespace: {namespace}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: {size}
  storageClassName: longhorn-static
  volumeName: {new-pv-name}
```

#### 2. Create Data Migration Job

```yaml
# Create: kubernetes/apps/{namespace}/{app}/app/migration-job.yaml
---
apiVersion: batch/v1
kind: Job
metadata:
  name: migrate-{app}-{purpose}
  namespace: {namespace}
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: data-migration
        image: busybox:latest
        command:
        - sh
        - -c
        - |
          echo "Starting data migration..."
          cp -av /old-data/. /new-data/
          echo "Migration complete!"
          echo "Verifying data..."
          du -sh /old-data /new-data
          diff -r /old-data /new-data || echo "Differences found!"
        volumeMounts:
        - name: old-data
          mountPath: /old-data
        - name: new-data
          mountPath: /new-data
      volumes:
      - name: old-data
        persistentVolumeClaim:
          claimName: {old-pvc-name}
      - name: new-data
        persistentVolumeClaim:
          claimName: {new-pvc-name}
```

#### 3. Execute Migration

```bash
# 1. Scale down application
kubectl scale deployment/{app} -n {namespace} --replicas=0
# OR for StatefulSets
kubectl scale statefulset/{app} -n {namespace} --replicas=0

# 2. Apply new PV/PVC
kubectl apply -f kubernetes/apps/{namespace}/{app}/app/pv-{name}.yaml

# 3. Wait for PVC to be bound
kubectl get pvc -n {namespace} {new-pvc-name}

# 4. Run migration job
kubectl apply -f kubernetes/apps/{namespace}/{app}/app/migration-job.yaml

# 5. Monitor migration
kubectl logs -n {namespace} job/migrate-{app}-{purpose} -f

# 6. Verify migration succeeded
kubectl get job -n {namespace} migrate-{app}-{purpose}

# 7. Update deployment/statefulset to use new PVC
# Edit helmrelease.yaml or deployment manifest

# 8. Scale up application
kubectl scale deployment/{app} -n {namespace} --replicas=1

# 9. Verify application is working
kubectl get pods -n {namespace} -l app={app}

# 10. Clean up old PVC (after confirming everything works)
kubectl delete pvc -n {namespace} {old-pvc-name}

# 11. Delete migration job
kubectl delete job -n {namespace} migrate-{app}-{purpose}
```

## Priority Order for Migration

### High Priority (Do First)
1. **monitoring/** volumes (after rybbit removal completes)
   - Prometheus and AlertManager have important data

2. **databases/** volumes
   - MariaDB contains critical application data

### Medium Priority
3. **custom-code-production/** volumes
   - Absenty application data

4. **ai/** namespace PostgreSQL volumes
   - Langfuse, Bytebot databases

### Low Priority (Can wait)
5. **ai/** namespace cache/logs
   - Can be recreated if needed

6. **download/** namespace
   - Tube archivist data

## Automated Migration Script

For volumes that can tolerate downtime, use this script:

```bash
#!/bin/bash
# migrate-pvc.sh - Automated PVC migration script

set -e

NAMESPACE=$1
APP=$2
OLD_PVC=$3
NEW_PVC=$4
PV_SIZE=$5

if [ -z "$NAMESPACE" ] || [ -z "$APP" ] || [ -z "$OLD_PVC" ] || [ -z "$NEW_PVC" ] || [ -z "$PV_SIZE" ]; then
  echo "Usage: $0 <namespace> <app> <old-pvc> <new-pvc> <pv-size>"
  exit 1
fi

echo "=== Starting migration for $APP in $NAMESPACE ==="
echo "Old PVC: $OLD_PVC"
echo "New PVC: $NEW_PVC"
echo "Size: $PV_SIZE"
echo ""

read -p "Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
  echo "Migration cancelled"
  exit 0
fi

# Scale down
echo "Scaling down $APP..."
kubectl scale deployment/$APP -n $NAMESPACE --replicas=0 || \
  kubectl scale statefulset/$APP -n $NAMESPACE --replicas=0

# Wait for pods to terminate
echo "Waiting for pods to terminate..."
kubectl wait --for=delete pod -l app=$APP -n $NAMESPACE --timeout=5m || true

# Create new PVC (assume manifest exists)
echo "Creating new PVC..."
kubectl apply -f kubernetes/apps/$NAMESPACE/$APP/app/pv-new.yaml

# Wait for binding
echo "Waiting for PVC to bind..."
kubectl wait --for=jsonpath='{.status.phase}'=Bound pvc/$NEW_PVC -n $NAMESPACE --timeout=2m

# Create and run migration job
echo "Running data migration..."
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: migrate-$APP
  namespace: $NAMESPACE
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: migration
        image: busybox:latest
        command: ['sh', '-c', 'cp -av /old/. /new/ && echo "Migration complete!"']
        volumeMounts:
        - name: old
          mountPath: /old
        - name: new
          mountPath: /new
      volumes:
      - name: old
        persistentVolumeClaim:
          claimName: $OLD_PVC
      - name: new
        persistentVolumeClaim:
          claimName: $NEW_PVC
EOF

# Wait for job completion
kubectl wait --for=condition=complete job/migrate-$APP -n $NAMESPACE --timeout=30m

echo "Migration job completed!"
echo "Please verify data and update deployment to use $NEW_PVC"
echo "Then scale up with: kubectl scale deployment/$APP -n $NAMESPACE --replicas=1"
```

## Rollback Procedure

If migration fails:

1. Delete new PVC: `kubectl delete pvc -n {namespace} {new-pvc-name}`
2. Delete new PV: `kubectl delete pv {new-pv-name}`
3. Scale up application with old PVC: `kubectl scale deployment/{app} -n {namespace} --replicas=1`
4. Investigate issue and retry

## Notes

- **Downtime**: Each migration requires application downtime (10-30 minutes)
- **Data Safety**: Always backup before migration
- **Testing**: Test migration process in non-production first
- **Scheduling**: Do during maintenance window
- **Monitoring**: Watch for errors during data copy
- **Verification**: Always verify application works with new PVC before deleting old one

## Timeline Estimate

- Per volume: 30-45 minutes (including preparation and verification)
- Total for 20+ volumes: 10-15 hours
- Recommended: Migrate 2-3 volumes per maintenance window
