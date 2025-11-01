# PV/PVC Migration Status

**Last Updated**: 2025-11-01 16:50 UTC
**Session**: Phase 1 completed
**Status**: PHASE 1 COMPLETE ✅

## Overview

Migrating Longhorn volumes from UUID-based PV names to clean naming standard.

**Total volumes identified**: 23 with UUID PV names
**Volumes to migrate**: 18 (Deployment-based only)
**Volumes skipped**: 5 (StatefulSet-based - too complex)
**Completed**: 4 ✅
**In Progress**: Phase 1 complete, ready for Phase 2
**Failed**: 0

## Completed Migrations ✅

### Phase 1: Small Volumes (COMPLETE)

1. ✅ **ai/ai-sre-cache** (2Gi)
   - Old PV: `pvc-4b56f40c-1ca9-4c4a-983c-298ea068da6c`
   - New PV: `ai-sre-cache`
   - Storage Class: `longhorn-static`
   - Status: Application running, old resources cleaned up

2. ✅ **ai/ai-sre-logs** (5Gi)
   - Old PV: `pvc-ec7762c0-cbbc-4a06-afd2-344950fe0159`
   - New PV: `ai-sre-logs`
   - Storage Class: `longhorn-static`
   - Status: Application running, old resources cleaned up

3. ✅ **ai/open-webui-pipelines** (2Gi)
   - Old PV: `pvc-20be0f47-56a5-447a-9a98-1e56c1713e35`
   - New PV: `open-webui-pipelines`
   - Storage Class: `longhorn-static`
   - Status: Application running, old resources cleaned up

4. ✅ **media/makemkv-config** (2Gi)
   - Old PV: `pvc-ce4c31cb-e83a-41b8-8f31-bd9b34d622f3`
   - New PV: `makemkv-config`
   - Storage Class: `longhorn-static`
   - Status: Application running, old resources cleaned up

**Phase 1 Total**: 4 volumes, 11Gi migrated, ~90 minutes elapsed

## Current Task

**Phase 1: COMPLETE** ✅

**Next: Phase 2 - Application Data (5 volumes, 10Gi each)**

## Volumes Queued for Migration

### Phase 2: Application Data (5 volumes)
- ai/ai-sre-storage (10Gi)
- custom-code-production/absenty-development-data (5Gi)
- custom-code-production/absenty-development-storage (10Gi)
- custom-code-production/absenty-production-data (5Gi)
- custom-code-production/absenty-production-storage (10Gi)

### Phase 3: Databases (5 volumes)
- ai/bytebot-postgres-data (10Gi)
- ai/langfuse-postgresql-pvc → langfuse-postgresql-data (10Gi)
- ai/langfuse-minio-data (10Gi)
- download/tube-archivist-redis-data (10Gi)
- databases/mariadb-data (20Gi)

### Phase 4: Large Databases (4 volumes)
- ai/bytebot-desktop-data (20Gi)
- ai/langfuse-clickhouse-pvc → langfuse-clickhouse-data (20Gi)
- download/tube-archivist-elasticsearch-data (20Gi)
- download/tube-archivist-cache (50Gi)

## Volumes Skipped (StatefulSets)

These require HelmRelease changes, not live migration:
- ❌ monitoring/alertmanager-kube-prometheus-stack-db-alertmanager-kube-prometheus-stack-0 (1Gi)
- ❌ monitoring/prometheus-kube-prometheus-stack-db-prometheus-kube-prometheus-stack-0 (60Gi)
- ❌ kube-system/data-authentik-postgresql-0 (8Gi)
- ❌ kube-system/redis-data-authentik-redis-master-0 (8Gi)
- ❌ office/redis-data-nextcloud-redis-master-0 (8Gi)

## Migration Script

Location: `/kubernetes/migrations/migrate-volume.sh`

Usage:
```bash
./migrate-volume.sh <namespace> <old-pvc> <new-pvc> <size-gi> <app-name>
```

Example:
```bash
./migrate-volume.sh ai ai-sre-cache ai-sre-cache 2 ai-sre
```

## Post-Migration Steps (Per Volume)

After each migration job completes:

1. **Verify migration completed**:
   ```bash
   kubectl get job -n <namespace> migrate-<app>
   kubectl logs -n <namespace> job/migrate-<app>
   ```

2. **Update application to use new PVC**:
   - Edit HelmRelease or deployment manifest
   - Change PVC name from old to `<new-pvc>-new`
   - Commit and push changes

3. **Scale up application**:
   ```bash
   kubectl scale deployment/<app> -n <namespace> --replicas=1
   ```

4. **Verify application works**:
   ```bash
   kubectl get pods -n <namespace> | grep <app>
   kubectl logs -n <namespace> <pod-name>
   ```

5. **Clean up old resources**:
   ```bash
   kubectl delete pvc -n <namespace> <old-pvc>
   kubectl delete job -n <namespace> migrate-<app>
   ```

6. **Rename PVC** (optional - for cleaner naming):
   - Delete deployment
   - Rename PVC from `<new-pvc>-new` to `<new-pvc>`
   - Update manifest to use `<new-pvc>`
   - Redeploy

## Issues Encountered

### Cleaned Up Issues:
1. **open-webui-10g-new** - Orphaned PVC detected and deleted (detached volume freed)
2. **alertmanager migration** - Attempted but rolled back due to StatefulSet complexity

### Active Issues:
None currently.

## Time Estimates

- Small volumes (2-5Gi): ~20 minutes each
- Medium volumes (10Gi): ~30 minutes each
- Large volumes (20-50Gi): ~45-60 minutes each

**Estimated total time remaining**: ~7 hours

## Notes for Continuation

If resuming in a new session:

1. **Read this file first** to understand current status
2. **Check completed migrations** section to see what's done
3. **Verify last migration** if one was in progress:
   ```bash
   kubectl get jobs -A | grep migrate
   kubectl get pvc -A | grep -E "new$"
   ```
4. **Continue with next volume** in the queue
5. **Update this file** after each migration

## Git Commits

Track migration progress with commits after each phase:
- Phase 1 complete: Commit message describing small volumes migrated
- Phase 2 complete: Commit message describing app data migrated
- etc.

## References

- Original migration guide: `/docs/migration/pv-pvc-naming-migration.md`
- Lessons learned: `/docs/migration/pv-pvc-migration-lessons-learned.md`
- Revised plan: `/docs/migration/migration-plan-revised.md`
