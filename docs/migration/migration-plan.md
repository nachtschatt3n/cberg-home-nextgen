# PV/PVC Migration Execution Plan

## Overview
Migrating 23 Longhorn volumes from UUID-based PV names to clean naming standard.

## Migration Order (by priority and size)

### Phase 1: Small, Low-Risk Volumes (< 5Gi)
1. **monitoring/alertmanager** (1Gi) - Can be recreated from Prometheus
2. **ai/ai-sre-cache** (2Gi) - Cache, can be recreated
3. **ai/open-webui-pipelines** (2Gi) - Pipeline data
4. **media/makemkv-config** (2Gi) - Config, backed up

### Phase 2: Medium Databases (5-10Gi)
5. **ai/ai-sre-logs** (5Gi) - Logs, less critical
6. **custom-code-production/absenty-development-data** (5Gi)
7. **custom-code-production/absenty-production-data** (5Gi)
8. **kube-system/data-authentik-postgresql-0** (8Gi) - User auth DB
9. **kube-system/redis-data-authentik-redis-master-0** (8Gi)
10. **office/redis-data-nextcloud-redis-master-0** (8Gi)
11. **ai/ai-sre-storage** (10Gi)
12. **custom-code-production/absenty-development-storage** (10Gi)
13. **custom-code-production/absenty-production-storage** (10Gi)
14. **ai/bytebot-postgres-data** (10Gi)
15. **ai/langfuse-minio-data** (10Gi)
16. **ai/langfuse-postgresql-pvc** (10Gi)
17. **download/tube-archivist-redis-data** (10Gi)

### Phase 3: Large Databases (20Gi+)
18. **ai/bytebot-desktop-data** (20Gi)
19. **ai/langfuse-clickhouse-pvc** (20Gi)
20. **databases/mariadb-data** (20Gi) - Shared MariaDB
21. **download/tube-archivist-elasticsearch-data** (20Gi)
22. **download/tube-archivist-cache** (50Gi)

### Phase 4: Critical Large Volume
23. **monitoring/prometheus** (60Gi) - Largest, most time-consuming

## Migration Template

For each volume, we'll:

1. Create migration directory structure
2. Generate Longhorn Volume, PV, and PVC manifests
3. Create data migration job
4. Execute migration
5. Update application to use new PVC
6. Verify and cleanup

## Estimated Timeline

- Small volumes (1-5Gi): ~20 minutes each = 1.5 hours
- Medium volumes (5-20Gi): ~30 minutes each = 6.5 hours
- Large volumes (20-50Gi): ~45 minutes each = 2.5 hours
- Prometheus (60Gi): ~60 minutes = 1 hour

**Total estimated time: ~12 hours**

## New PVC Naming Convention

- `ai-sre-cache` → `ai-sre-cache` (already clean)
- `ai-sre-logs` → `ai-sre-logs` (already clean)
- `langfuse-clickhouse-pvc` → `langfuse-clickhouse-data`
- `langfuse-postgresql-pvc` → `langfuse-postgresql-data`
- All others keep their current clean names

## Rollback Plan

If any migration fails:
1. Delete new PVC
2. Delete new PV
3. Delete Longhorn volume
4. Keep old PVC/PV intact
5. Application continues using old volume

## Safety Measures

- Backup verification before each migration
- One volume at a time
- Full application downtime during migration
- Data verification after copy
- Keep old volumes until confirmed working
