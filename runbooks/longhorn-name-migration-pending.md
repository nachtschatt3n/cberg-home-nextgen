# Longhorn Name Migration Pending

## Snapshot
- Date: 2026-03-09
- Source: live cluster query (`kubectl get pv`) for `storageClassName=longhorn` and PV name `pvc-*`
- Total pending: 10

## Migration Queue

### Ready For Migration (Deployment/PVC based)
1. `my-software-production/absenty-data`
- Current PV: `pvc-c0e52c2a-91b1-4f72-ac57-cc1f5719fe41`
- Manifest reference: `kubernetes/apps/my-software-production/absenty/app/helmrelease.yaml:136`
- Suggested target name: `absenty-data`

2. `my-software-production/absenty-storage`
- Current PV: `pvc-07220c82-2c71-4a3a-ae8c-a04e558d0f21`
- Manifest reference: `kubernetes/apps/my-software-production/absenty/app/helmrelease.yaml:144`
- Suggested target name: `absenty-storage`

3. `my-software-development/absenty-data`
- Current PV: `pvc-fdc34672-c53a-41fe-a2d3-21125d0cac72`
- Manifest reference: `kubernetes/apps/my-software-development/absenty/app/helmrelease.yaml:155`
- Suggested target name: `absenty-data`

4. `my-software-development/absenty-storage`
- Current PV: `pvc-af6e749e-1ca8-433b-8a10-f3cc5b41ed53`
- Manifest reference: `kubernetes/apps/my-software-development/absenty/app/helmrelease.yaml:163`
- Suggested target name: `absenty-storage`

5. `my-software-development/absenty-bundle`
- Current PV: `pvc-5182e7fc-2993-43a1-b64d-e5aa1edea8d2`
- Manifest reference: `kubernetes/apps/my-software-development/absenty/app/helmrelease.yaml:181`
- Suggested target name: `absenty-bundle`

6. `home-automation/matter-server-data`
- Current PV: `pvc-626c58f8-d889-4bda-9056-a8509ce202d4`
- Manifest reference: `kubernetes/apps/home-automation/matter-server/app/pvc.yaml:13`
- Suggested target name: `matter-server-data`

7. `home-automation/scrypted-data`
- Current PV: `pvc-bd13d22f-9885-4d47-958e-07507a06d6ac`
- Manifest reference: `kubernetes/apps/home-automation/scrypted-nvr/app/pvc.yaml:12`
- Suggested target name: `scrypted-data`

8. `databases/redis-data`
- Current PV: `pvc-77167e86-f960-4f51-8ec1-c79c82684b06`
- Manifest reference: `kubernetes/apps/databases/redis/app/pvc.yaml:13`
- Suggested target name: `redis-data`

9. `databases/redisinsight-data`
- Current PV: `pvc-a545f6e7-2134-4b43-98b5-f0e8a3c1fe69`
- Manifest reference: `kubernetes/apps/databases/redisinsight/app/pvc.yaml:13`
- Suggested target name: `redisinsight-data`

### Policy Exception / Separate Design Track
10. `monitoring/elasticsearch-data-elasticsearch-es-default-0`
- Current PV: `pvc-b2d0193f-4a12-4b38-95c2-66283163cce0`
- Manifest reference: `kubernetes/apps/monitoring/elasticsearch/app/elasticsearch.yaml:45`
- Reason: created via `volumeClaimTemplates` (StatefulSet-style behavior)
- Action: keep dynamic `longhorn` unless workload architecture is redesigned

## Suggested Execution Order
1. `databases/redisinsight-data` (smallest, low risk)
2. `home-automation/matter-server-data`
3. `databases/redis-data`
4. `home-automation/scrypted-data`
5. `my-software-development/absenty-*`
6. `my-software-production/absenty-*`
7. StatefulSet exception review (`monitoring/elasticsearch-*`)

## Tracking Checklist
- [ ] `redisinsight-data`
- [ ] `matter-server-data`
- [ ] `redis-data`
- [ ] `scrypted-data`
- [ ] `absenty-dev-data`
- [ ] `absenty-dev-storage`
- [ ] `absenty-dev-bundle`
- [ ] `absenty-prod-data`
- [ ] `absenty-prod-storage`
- [ ] `elasticsearch exception decision`

## Recheck Command
```bash
kubectl get pv -o custom-columns=PV:.metadata.name,SC:.spec.storageClassName,CLAIMNS:.spec.claimRef.namespace,CLAIM:.spec.claimRef.name --no-headers \
  | awk '$2=="longhorn" && $1 ~ /^pvc-/'
```
