# Revised PV/PVC Migration Plan

## Key Decision: Skip StatefulSet Volumes

After testing, StatefulSets (alertmanager, prometheus, authentik, nextcloud-redis) are too complex to migrate because:
- VolumeClaimTemplates are tightly coupled to StatefulSet definitions
- Requires complete StatefulSet redeployment
- High risk for critical monitoring infrastructure

**Instead**: Focus on Deployment volumes which are straightforward to migrate.

## Volumes TO MIGRATE (Deployments only)

### AI Namespace (9 volumes)
1. ai-sre-cache (2Gi) - Deployment
2. ai-sre-logs (5Gi) - Deployment
3. ai-sre-storage (10Gi) - Deployment
4. bytebot-desktop-data (20Gi) - Deployment
5. bytebot-postgres-data (10Gi) - Deployment
6. langfuse-clickhouse-pvc → langfuse-clickhouse-data (20Gi) - Deployment
7. langfuse-minio-data (10Gi) - Deployment
8. langfuse-postgresql-pvc → langfuse-postgresql-data (10Gi) - Deployment
9. open-webui-pipelines (2Gi) - Deployment

### Custom-Code-Production (4 volumes)
10. absenty-development-data (5Gi)
11. absenty-development-storage (10Gi)
12. absenty-production-data (5Gi)
13. absenty-production-storage (10Gi)

### Databases (1 volume)
14. mariadb-data (20Gi) - Deployment

### Download (3 volumes)
15. tube-archivist-cache (50Gi)
16. tube-archivist-elasticsearch-data (20Gi)
17. tube-archivist-redis-data (10Gi)

### Media (1 volume)
18. makemkv-config (2Gi)

**Total: 18 volumes to migrate**

## Volumes TO SKIP (StatefulSets)

- ❌ monitoring/alertmanager (1Gi) - StatefulSet
- ❌ monitoring/prometheus (60Gi) - StatefulSet
- ❌ kube-system/data-authentik-postgresql-0 (8Gi) - StatefulSet
- ❌ kube-system/redis-data-authentik-redis-master-0 (8Gi) - StatefulSet
- ❌ office/redis-data-nextcloud-redis-master-0 (8Gi) - StatefulSet

For these, consider updating HelmRelease to use `longhorn-static` storage class if you really want clean PV names.

## Updated Timeline

- Small volumes (2-5Gi): ~20 min × 4 = 1.5 hours
- Medium volumes (10-20Gi): ~30 min × 10 = 5 hours
- Large volumes (50Gi): ~45 min × 1 = 0.75 hours

**Total: ~7 hours** (much more manageable)

## Migration Order

### Phase 1: Cache/Logs (Low Risk)
1. ai-sre-cache (2Gi)
2. ai-sre-logs (5Gi)
3. open-webui-pipelines (2Gi)
4. makemkv-config (2Gi)

### Phase 2: Application Data
5. ai-sre-storage (10Gi)
6. absenty-development-data (5Gi)
7. absenty-development-storage (10Gi)
8. absenty-production-data (5Gi)
9. absenty-production-storage (10Gi)

### Phase 3: Databases
10. bytebot-postgres-data (10Gi)
11. langfuse-postgresql-pvc (10Gi)
12. langfuse-minio-data (10Gi)
13. tube-archivist-redis-data (10Gi)
14. mariadb-data (20Gi)

### Phase 4: Large Databases
15. bytebot-desktop-data (20Gi)
16. langfuse-clickhouse-pvc (20Gi)
17. tube-archivist-elasticsearch-data (20Gi)
18. tube-archivist-cache (50Gi)

## Next Steps

Continue with Phase 1 using the migration script, focusing only on Deployment-based volumes.
