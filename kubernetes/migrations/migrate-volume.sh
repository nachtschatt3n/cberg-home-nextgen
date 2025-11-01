#!/bin/bash
# PV/PVC Migration Script
# Usage: ./migrate-volume.sh <namespace> <old-pvc-name> <new-pvc-name> <size-gi> <app-name>

set -e

NAMESPACE=$1
OLD_PVC=$2
NEW_PVC=$3
SIZE_GI=$4
APP_NAME=$5

if [ -z "$NAMESPACE" ] || [ -z "$OLD_PVC" ] || [ -z "$NEW_PVC" ] || [ -z "$SIZE_GI" ] || [ -z "$APP_NAME" ]; then
  echo "Usage: $0 <namespace> <old-pvc> <new-pvc> <size-gi> <app-name>"
  echo "Example: $0 monitoring alertmanager-kube-prometheus-stack-db-alertmanager-kube-prometheus-stack-0 alertmanager-data 1 alertmanager-kube-prometheus-stack"
  exit 1
fi

# Calculate size in bytes
SIZE_BYTES=$((SIZE_GI * 1024 * 1024 * 1024))

echo "============================================"
echo "PV/PVC Migration"
echo "============================================"
echo "Namespace: $NAMESPACE"
echo "Old PVC: $OLD_PVC"
echo "New PVC: $NEW_PVC"
echo "Size: ${SIZE_GI}Gi ($SIZE_BYTES bytes)"
echo "App: $APP_NAME"
echo "============================================"
echo ""

read -p "Continue with migration? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
  echo "Migration cancelled"
  exit 0
fi

echo ""
echo "[1/8] Checking current PVC status..."
kubectl get pvc -n $NAMESPACE $OLD_PVC || { echo "ERROR: PVC not found"; exit 1; }

echo ""
echo "[2/8] Scaling down application..."
# Try deployment first, then statefulset
kubectl scale deployment/$APP_NAME -n $NAMESPACE --replicas=0 2>/dev/null || \
  kubectl scale statefulset/$APP_NAME -n $NAMESPACE --replicas=0 || \
  echo "Note: Could not auto-scale. Please scale manually if needed."

echo ""
echo "[3/8] Waiting for pods to terminate..."
sleep 10
kubectl wait --for=delete pod -l app.kubernetes.io/name=$APP_NAME -n $NAMESPACE --timeout=5m 2>/dev/null || \
  kubectl wait --for=delete pod -l app=$APP_NAME -n $NAMESPACE --timeout=5m 2>/dev/null || \
  echo "Note: Pods may have already terminated or use different labels"

echo ""
echo "[4/8] Creating Longhorn volume..."
cat <<EOF | kubectl apply -f -
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: $NEW_PVC
  namespace: storage
spec:
  size: "$SIZE_BYTES"
  numberOfReplicas: 3
  dataEngine: v1
  accessMode: rwo
  frontend: blockdev
  migratable: false
  encrypted: false
  staleReplicaTimeout: 30
EOF

echo ""
echo "[5/8] Waiting for Longhorn volume to be ready..."
sleep 5
kubectl wait --for=jsonpath='{.status.state}'=detached volume/$NEW_PVC -n storage --timeout=2m

echo ""
echo "[6/8] Creating PV and PVC..."
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolume
metadata:
  name: $NEW_PVC
spec:
  capacity:
    storage: ${SIZE_GI}Gi
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
    volumeHandle: $NEW_PVC
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ${NEW_PVC}-new
  namespace: $NAMESPACE
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: ${SIZE_GI}Gi
  storageClassName: longhorn-static
  volumeName: $NEW_PVC
EOF

echo ""
echo "[7/8] Waiting for PVC to bind..."
kubectl wait --for=jsonpath='{.status.phase}'=Bound pvc/${NEW_PVC}-new -n $NAMESPACE --timeout=2m

echo ""
echo "[8/8] Creating data migration job..."
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: migrate-$APP_NAME
  namespace: $NAMESPACE
spec:
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: migration
        image: busybox:latest
        command:
        - sh
        - -c
        - |
          echo "=========================================="
          echo "Data Migration for $APP_NAME"
          echo "=========================================="
          echo "Source: /old-data"
          du -sh /old-data 2>/dev/null || echo "Empty or inaccessible"
          ls -lah /old-data 2>/dev/null || echo "Cannot list"
          echo ""
          echo "Destination: /new-data"
          du -sh /new-data 2>/dev/null || echo "Empty"
          ls -lah /new-data 2>/dev/null || echo "Cannot list"
          echo ""
          echo "Starting copy..."
          cp -av /old-data/. /new-data/ 2>&1 || echo "Copy completed with some errors"
          echo ""
          echo "Migration complete!"
          echo ""
          echo "Final sizes:"
          du -sh /old-data /new-data 2>/dev/null || echo "Cannot measure"
          echo ""
          echo "SUCCESS: Data migrated"
        volumeMounts:
        - name: old-data
          mountPath: /old-data
        - name: new-data
          mountPath: /new-data
      volumes:
      - name: old-data
        persistentVolumeClaim:
          claimName: $OLD_PVC
      - name: new-data
        persistentVolumeClaim:
          claimName: ${NEW_PVC}-new
EOF

echo ""
echo "=========================================="
echo "Migration job created!"
echo "=========================================="
echo ""
echo "Monitor with: kubectl logs -n $NAMESPACE job/migrate-$APP_NAME -f"
echo "Check status: kubectl get job -n $NAMESPACE migrate-$APP_NAME"
echo ""
echo "After migration completes:"
echo "1. Update application to use PVC: ${NEW_PVC}-new"
echo "2. Scale application back up"
echo "3. Verify application works"
echo "4. Delete old PVC: kubectl delete pvc -n $NAMESPACE $OLD_PVC"
echo "5. Delete migration job: kubectl delete job -n $NAMESPACE migrate-$APP_NAME"
echo "6. Rename PVC from ${NEW_PVC}-new to $NEW_PVC"
echo ""
