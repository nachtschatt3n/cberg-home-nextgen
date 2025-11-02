# PV/PVC Migration: Lessons Learned and Updated Recommendations

## Executive Summary

After attempting PV/PVC migrations from UUID-based names to clean naming conventions, we've identified significant challenges and complexities. This document provides updated recommendations based on real-world testing.

## Key Findings

### 1. UUID PV Names Are Normal for Dynamic Provisioning

**Discovery**: When using dynamic provisioning with the `longhorn` storage class, Kubernetes automatically generates UUID-based PV names (e.g., `pvc-4b56f40c-1ca9-4c4a-983c-298ea068da6c`).

**Implication**: This is **standard Kubernetes behavior** and not a misconfiguration. Every dynamically provisioned volume will have a UUID-based PV name.

### 2. longhorn-static Requires Pre-existing Volumes

**Discovery**: The `longhorn-static` storage class requires Longhorn volumes to exist **before** creating PVs that reference them.

**Challenge**: Creating these volumes correctly requires:
- Manual creation through Longhorn UI/API, OR
- Correct Longhorn Volume CRD configuration (complex, error-prone)
- The PV's volumeHandle must exactly match the Longhorn volume name

**Error encountered**:
```
AttachVolume.Attach failed for volume "ai-sre-cache" :
rpc error: code = NotFound desc = volume ai-sre-cache not found
```

### 3. Migration Complexity vs Benefit

**Reality Check**:
- **Downtime**: Each volume migration requires application downtime (30-45 min)
- **Risk**: Data migration failures can result in data loss
- **Effort**: 20+ volumes × 45 minutes = 15+ hours of work
- **Benefit**: Purely cosmetic/organizational - UUID PV names don't affect functionality

**Conclusion**: The cost-benefit ratio doesn't justify mass migration for existing volumes.

## Updated Recommendations

### For Existing Volumes: KEEP AS-IS

**Recommendation**: **Do NOT migrate existing dynamically provisioned volumes**

**Rationale**:
1. UUID PV names are standard Kubernetes behavior
2. PVC names are already clean and meaningful
3. Migration risks outweigh aesthetic benefits
4. Applications work perfectly with current setup

**Exceptions**: Only migrate if:
- Volume is critically important and you want longhorn-static's manual control
- You're already planning maintenance/migration for other reasons
- The volume is < 5Gi and low-risk (caches, logs)

### For New Volumes: Choose Appropriately

#### Use `longhorn` (dynamic) for:
- ✅ Application databases (PostgreSQL, MariaDB, etc.)
- ✅ Application data that grows over time
- ✅ Volumes where you want automatic provisioning
- ✅ StatefulSet volumes (they require dynamic provisioning)

**Naming outcome**:
- PVC: Clean name (e.g., `langfuse-postgresql-data`)
- PV: UUID (e.g., `pvc-df1999c2-c73c-4e54-a0a7-9f30571e8636`)
- **This is perfectly fine and standard practice**

#### Use `longhorn-static` for:
- ✅ Configuration directories with fixed size (e.g., `home-assistant-config`)
- ✅ Pre-created volumes you want to manually manage
- ✅ Volumes you want to preserve across namespace deletions
- ✅ Volumes where you need specific Longhorn settings

**Naming outcome**:
- PVC: Clean name (e.g., `home-assistant-config`)
- PV: Clean name (same as PVC)
- Longhorn Volume: Clean name (same as PV)

### Current Cluster Status: ACCEPTABLE

Looking at your current volumes:

#### ✅ Already using longhorn-static (good as-is):
- Config volumes: `adguard-home-config`, `esphome-config`, `frigate-config`, etc.
- These have clean PV and PVC names - perfect!

#### ✅ Using longhorn dynamic (standard practice):
- App data: `langfuse-postgresql-pvc`, `bytebot-postgres-data`, etc.
- PV names are UUIDs - this is normal and expected!
- **No action needed**

#### 🔧 Cosmetic improvements (optional, low priority):
Some PVC names could be cleaner:
- `langfuse-clickhouse-pvc` → could be `langfuse-clickhouse-data`
- `langfuse-postgresql-pvc` → could be `langfuse-postgresql-data`
- `open-webui-10g-new` → orphaned, can be cleaned up

**How to fix**: Update Helm values or manifests to use cleaner PVC names on next deployment. No migration needed.

## Migration Guide Updates

### IF You Still Want to Migrate (Not Recommended)

For the brave souls who want clean PV names despite the effort:

#### Step 1: Create Longhorn Volume Manually

```bash
# Option A: Using Longhorn UI
# 1. Access Longhorn UI
# 2. Go to "Volume" → "Create Volume"
# 3. Set name, size, and replicas
# 4. Click "Create"

# Option B: Using kubectl (requires exact format)
kubectl create -f - <<EOF
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: my-app-data
  namespace: storage
spec:
  size: "10737418240"  # Size in bytes (10Gi)
  numberOfReplicas: 3
  dataEngine: v1
  accessMode: rwo
  frontend: blockdev  # IMPORTANT: Must specify frontend
EOF
```

#### Step 2: Wait for Volume to be Ready

```bash
kubectl wait --for=jsonpath='{.status.state}'=detached \
  volume/my-app-data -n storage --timeout=5m
```

#### Step 3: Create PV and PVC

```yaml
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: my-app-data
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
    volumeHandle: my-app-data  # Must match Longhorn volume name
---
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
  storageClassName: longhorn-static
  volumeName: my-app-data
```

#### Step 4: Run Data Migration

(Use migration job from original guide)

## Practical Next Steps

### Immediate (Done)
- ✅ Reclaimed rybbit storage (60Gi freed)
- ✅ Fixed ImageUpdateAutomation
- ✅ Optimized memory limits
- ✅ Fixed scrypted configuration

### Short-term (Recommended)
1. **Clean up orphaned PVCs**:
   ```bash
   kubectl get pvc -A | grep -E "new|old|temp"
   # Review and delete unused PVCs
   ```

2. **Standardize new deployments**: Update templates/Helm values to use consistent naming
   - PVC names: `{app}-{purpose}` (e.g., `postgres-data`, `redis-data`)
   - Use `longhorn` for dynamic provisioning
   - Use `longhorn-static` only for config volumes

3. **Monitor**: Keep an eye on storage usage and Longhorn health

### Long-term (Optional)
- **Incremental improvements**: When redeploying apps, use cleaner PVC names
- **Documentation**: Maintain naming standards for new volumes
- **Longhorn upgrades**: Follow Longhorn best practices for version upgrades

## Conclusion

**The pragmatic approach**:
- Accept UUID PV names for dynamically provisioned volumes as standard practice
- Focus on clean PVC names (which are user-facing)
- Use longhorn-static only for truly static volumes
- Don't waste time on cosmetic migrations

**Your cluster is healthy and well-organized as-is!**

The UUID PV names might look messy, but they:
- Don't affect functionality
- Are hidden from most operations
- Are standard Kubernetes practice
- Aren't worth the migration risk/effort

## References

- Original migration guide: `/docs/migration/pv-pvc-naming-migration.md`
- Longhorn documentation: https://longhorn.io/docs/
- Kubernetes PV/PVC concepts: https://kubernetes.io/docs/concepts/storage/
