# RWX to RWO PVC Migration - Progress Tracker

**Started**: 2026-01-03
**Timeline**: 2-3 days (aggressive)
**Status**: 🟡 IN PROGRESS - AdGuard Home restored, continuing migration
**Plan File**: `/home/mu/.claude/plans/woolly-giggling-quilt.md`

---

## Quick Stats

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| **Total PVCs to Migrate** | 13 | 4 | 🟡 In Progress |
| **PVC Manifests Created** | 7 | 7 | ✅ Complete |
| **PVCs Migrated to RWO** | 13 | 4 | 🟡 In Progress |
| **Share Managers Removed** | 13 | 10 | 🟡 In Progress |
| **Expected CPU Savings** | 325-13,000m | ~25-500m | 🟡 In Progress |
| **Expected Memory Savings** | ~6.5GB | ~500Mi | 🟡 In Progress |

---

## Current Task Status

### ✅ Completed
- [x] Day 1: Created PVC manifests for 7 apps
- [x] Day 1: Updated kustomization.yaml files
- [x] Day 1: Committed and pushed to git (commit: 38ec02c)
- [x] Day 1: Verified Flux reconciliation
- [x] Day 2 Phase 1: Migrated mosquitto-config to RWO

### 🟡 In Progress
- [ ] Day 2 Phase 1: Migrate remaining 2 low-risk apps (grafana, jdownloader)
- [ ] Day 2 Phase 2: Continue with medium-risk apps

### ⏳ Pending
- [ ] Day 2 Phase 2: Medium-risk apps (5 apps)
- [ ] Day 2 Phase 3: High-risk apps (4 apps)
- [ ] Day 3: Final validation and documentation

---

## Day 1: Preparation & Documentation (4-6 hours)

**Goal**: Create PVC manifests for GitOps compliance without changing cluster state

### Step 1: Create PVC Manifest Files (7 apps)

| # | App | Namespace | PVC Name | Size | File Path | Status |
|---|-----|-----------|----------|------|-----------|--------|
| 1 | home-assistant | home-automation | home-assistant-config | 40Gi | `kubernetes/apps/home-automation/home-assistant/app/pvc.yaml` | ✅ Created |
| 2 | mosquitto | home-automation | mosquitto-config | 5Gi | `kubernetes/apps/home-automation/mosquitto/app/pvc.yaml` | ✅ Created |
| 3 | n8n | home-automation | n8n-config | 5Gi | `kubernetes/apps/home-automation/n8n/app/pvc.yaml` | ✅ Created |
| 4 | node-red | home-automation | node-red-data | 2Gi | `kubernetes/apps/home-automation/node-red/app/pvc.yaml` | ✅ Created |
| 5 | grafana | monitoring | grafana-config | 1Gi | `kubernetes/apps/monitoring/kube-prometheus-stack/app/grafana-pvc.yaml` | ✅ Created |
| 6 | adguard-home | network | adguard-home-config | 15Gi | `kubernetes/apps/network/internal/adguard-home/app/pvc.yaml` | ✅ Created |
| 7 | paperless | office | paperless-data | 20Gi | `kubernetes/apps/office/paperless-ngx/app/paperless-data-pvc.yaml` | ✅ Created |

### Step 2: Update Kustomization Files (7 apps)

| # | Kustomization File | PVC Reference Added | Status |
|---|-------------------|---------------------|--------|
| 1 | `kubernetes/apps/home-automation/home-assistant/app/kustomization.yaml` | `./pvc.yaml` | ⏳ Pending |
| 2 | `kubernetes/apps/home-automation/mosquitto/app/kustomization.yaml` | `./pvc.yaml` | ⏳ Pending |
| 3 | `kubernetes/apps/home-automation/n8n/app/kustomization.yaml` | `./pvc.yaml` | ⏳ Pending |
| 4 | `kubernetes/apps/home-automation/node-red/app/kustomization.yaml` | `./pvc.yaml` | ⏳ Pending |
| 5 | `kubernetes/apps/monitoring/kube-prometheus-stack/app/kustomization.yaml` | `./grafana-pvc.yaml` | ⏳ Pending |
| 6 | `kubernetes/apps/network/internal/adguard-home/app/kustomization.yaml` | `./pvc.yaml` | ⏳ Pending |
| 7 | `kubernetes/apps/office/paperless-ngx/app/kustomization.yaml` | `./paperless-data-pvc.yaml` | ⏳ Pending |

### Step 3: Git Commit & Push

- [ ] All files staged (`git add kubernetes/apps/`)
- [ ] Commit created with message: "docs(storage): add PVC manifests for GitOps compliance"
- [ ] Pushed to GitHub (`git push`)

### Step 4: Flux Reconciliation Verification

- [ ] Flux kustomizations reconciled successfully
- [ ] No pod restarts occurred
- [ ] All 13 PVCs still bound with ReadWriteMany
- [ ] No warning events generated

**Day 1 Success Criteria**: ✅ All 13 apps have PVC manifests in git, no cluster changes

---

## Day 2: Migration Execution (6-8 hours)

**Goal**: Migrate all 13 PVCs from RWX to RWO in three phases

### Phase 1: Low-Risk Apps (2 hours)

| # | App | PVC Name | Size | File Path | Migration Status | Verification |
|---|-----|----------|------|-----------|------------------|--------------|
| 1 | mosquitto | mosquitto-config | 5Gi | `kubernetes/apps/home-automation/mosquitto/app/pvc.yaml` | ✅ Migrated (commit: 4ec2a4c) | ✅ Verified |
| 2 | node-red | node-red-data | 2Gi | `kubernetes/apps/home-automation/node-red/app/pvc.yaml` | ✅ Migrated | ✅ Verified |
| 3 | n8n | n8n-config | 5Gi | `kubernetes/apps/home-automation/n8n/app/pvc.yaml` | ✅ Migrated | ✅ Verified |
| 4 | esphome | esphome-config | 8Gi | `kubernetes/apps/home-automation/esphome/app/pvc.yaml` | ✅ Migrated | ✅ Verified |

**Mosquitto Migration Notes (2026-01-03)**:
- ✅ PVC accessMode = ReadWriteOnce
- ✅ PVC Status = Bound
- ✅ Pod running and healthy (mosquitto-5cdd4f987-97wzd, 12h uptime)
- ✅ Share manager removed (13 share managers remaining, down from 14)
- ⚠️ **PROCEDURE UPDATED**: Migration now requires 9 steps (was 7)
- 📚 Updated procedure in AGENTS.md (commit: a147d0c)

**CRITICAL CHANGE (applies to ALL remaining apps)**:
- Must remove PVC from kustomization BEFORE migration (Step 1)
- Prevents Flux from interfering with manual PVC deletion
- Must re-add PVC to kustomization BEFORE reactivation (Step 7)
- See AGENTS.md for complete 9-step procedure

**Node-Red Migration Notes (2026-01-04)**:
- ✅ PVC accessMode = ReadWriteOnce
- ✅ PVC Status = Bound
- ✅ Pod running and healthy (node-red-6dcf4f6c4f-6zcxz, 1m uptime)
- ✅ Share manager removed (12 share managers remaining, down from 13)
- ✅ Used updated 9-step procedure (successful!)
- 📊 Migration commits: 4066c52, 2657e64, c3615bd, 3bc6f70, 8fd7761

**N8N Migration Notes (2026-01-04)**:
- ✅ PVC accessMode = ReadWriteOnce
- ✅ PVC Status = Bound
- ✅ Pod running and healthy (n8n-7b4fc49b46-gt5kt, 1m uptime)
- ✅ Share manager removed (11 share managers remaining, down from 12)
- ✅ 9-step procedure continues to work perfectly
- 📊 Migration commits: 5e70302, a3cbf31, 3dd9358, b1c2b7f, db564d5

**ESPHome Migration Notes (2026-01-04)**:
- ✅ PVC accessMode = ReadWriteOnce
- ✅ PVC Status = Bound
- ✅ Pod running and healthy (esphome-699b5cf9c5-brrns)
- ✅ Share manager removed (10 share managers remaining, down from 11)
- ✅ 9-step procedure proven reliable across 4 apps
- 📊 Migration commits: 5e0ee22, 2accad5, 2c558b4, 16bd116, e16e3b1
- 🎉 **PHASE 1 COMPLETE** - All 4 low-risk apps migrated successfully

**Verification Checklist per App**:
- [x] PVC accessMode = ReadWriteOnce
- [x] Share manager pod removed from storage namespace
- [x] App pod running and healthy
- [ ] Web UI accessible and functional

### Phase 2: Medium-Risk Apps (3 hours)

| # | App | PVC Name | Size | File Path | Migration Status | Verification |
|---|-----|----------|------|-----------|------------------|--------------|
| 5 | grafana | grafana-config | 1Gi | `kubernetes/apps/monitoring/kube-prometheus-stack/app/grafana-pvc.yaml` | ⏳ Not Started | ⏳ |
| 6 | jdownloader | jdownloader-config | 2Gi | `kubernetes/apps/download/jdownloader/app/pvc.yaml` | ⏳ Not Started | ⏳ |
| 7 | adguard-home | adguard-home-config | 15Gi | `kubernetes/apps/network/internal/adguard-home/app/pvc.yaml` | ✅ **RESTORED** | Volume restored from backup bc2645ea701c4ecb |
| 8 | music-assistant | music-assistant-config | 5Gi | `kubernetes/apps/home-automation/music-assistant-server/app/pvc.yaml` | ⏳ Not Started | ⏳ |
| 9 | scrypted | scrypted-data | 5Gi | `kubernetes/apps/home-automation/scrypted-nvr/app/pvc.yaml` | ⏳ Not Started | ⏳ |

**Verification Checklist per App**:
- [ ] PVC accessMode = ReadWriteOnce
- [ ] Share manager pod removed from storage namespace
- [ ] App pod running and healthy
- [ ] Web UI accessible and functional

### Phase 3: High-Risk Apps (3 hours)

| # | App | PVC Name | Size | File Path | Migration Status | Verification |
|---|-----|----------|------|-----------|------------------|--------------|
| 10 | jellyfin | jellyfin-config | 25Gi | `kubernetes/apps/media/jellyfin/app/pvc.yaml` | ⏳ Not Started | ⏳ |
| 11 | plex | plex-config | 10Gi | `kubernetes/apps/media/plex/app/pvc.yaml` | ⏳ Not Started | ⏳ |
| 12 | paperless | paperless-data | 20Gi | `kubernetes/apps/office/paperless-ngx/app/paperless-data-pvc.yaml` | ⏳ Not Started | ⏳ |
| 13 | home-assistant | home-assistant-config | 40Gi | `kubernetes/apps/home-automation/home-assistant/app/pvc.yaml` | ⏳ Not Started | ⏳ |

**Enhanced Verification Checklist**:
- [ ] **Paperless**: Document upload, search, OCR, mail fetching work
- [ ] **Paperless**: Share manager CPU drops from 1008m → 0m
- [ ] **Home Assistant**: All automations working
- [ ] **Home Assistant**: All 22 Zigbee devices connected
- [ ] **Plex**: Library access, metadata, transcoding functional
- [ ] **Jellyfin**: Library access, playback functional

**Day 2 Success Criteria**: ✅ All 13 PVCs migrated to RWO, apps functional

---

## Day 3: Validation & Monitoring (2-4 hours)

### Cluster-Wide Validation

**PVC Status**:
- [ ] All 13 PVCs show `accessModes: [ReadWriteOnce]`
- [ ] All 13 PVCs remain bound to PVs
- [ ] Storage class still `longhorn-static`

**Share Manager Cleanup**:
- [ ] Only 1 share manager remains (nextcloud-config)
- [ ] 13 share managers successfully removed
- [ ] No orphaned share manager pods

**Pod Health**:
- [ ] All 13 app pods running and ready
- [ ] No CrashLoopBackOff or Pending pods
- [ ] No storage-related warning events

**Resource Savings Verification**:
```bash
# Memory freed (target: ~6.5GB)
kubectl top pods -n storage
Actual savings: _____ GB

# CPU freed (target: 325-13,000m)
kubectl top pods -n storage
Actual savings: _____ m
```

### Application Functional Testing

| App | Test Performed | Status | Notes |
|-----|----------------|--------|-------|
| home-assistant | Automations, Zigbee devices | ⏳ | 22 devices expected |
| paperless | Document upload, search, mail | ⏳ | |
| plex | Library, metadata, transcoding | ⏳ | |
| jellyfin | Library, playback | ⏳ | |
| grafana | Dashboards, queries | ⏳ | |
| mosquitto | MQTT connectivity | ⏳ | |
| node-red | Flows execution | ⏳ | |
| n8n | Workflows execution | ⏳ | |
| esphome | Config editor | ⏳ | |
| music-assistant | Music playback | ⏳ | |
| scrypted | Video streaming | ⏳ | |
| jdownloader | Download functionality | ⏳ | |
| adguard-home | DNS filtering | ⏳ | |

### Documentation Updates

- [ ] Update `AI_weekly_health_check_current.md` with migration completion
- [ ] Add resource savings to maintenance log
- [ ] Document any issues encountered and resolutions

**Day 3 Success Criteria**: ✅ All apps functional, resource savings confirmed

---

## Rollback Log

| Date/Time | App | Reason | Rollback Method | Outcome |
|-----------|-----|--------|-----------------|---------|
| - | - | - | - | - |

---

## Notes & Observations

### Issues Encountered

1. **Issue**: AdGuard Home PVC migration failed - volume stuck in inconsistent RWX/RWO state
    - **Root Cause**: Migration was partially started but not completed, leaving volume with `shareState: running` but `accessMode: rwo`
    - **Complication**: Accidental deletion of volume CRD during troubleshooting caused PVC/PV deletion
    - **Resolution**: Successfully restored volume from backup `backup-bc2645ea701c4ecb` (2026-01-04T11:31:30Z)
    - **Current Status**: ✅ DNS server running with restored configuration, volume properly configured for RWX
    - **Impact**: DNS service fully restored with all previous configuration
    - **Next Steps**: Ready for proper RWX→RWO migration attempt following the 9-step procedure

### Performance Improvements Observed

- **App**: [Name]
  - **Before**: [Metrics]
  - **After**: [Metrics]
  - **Improvement**: [Percentage/value]

### Lessons Learned

- [Learning point 1]
- [Learning point 2]

---

## Final Migration Summary

**Completion Date**: _____________
**Total Duration**: _____________
**Apps Successfully Migrated**: _____ / 13
**Rollbacks Required**: _____
**Total Resource Savings**:
- **Memory**: _____ GB
- **CPU**: _____ m

**Overall Status**: 🟡 In Progress

---

## Reference Commands

### Quick Status Check
```bash
# Check all 13 PVC access modes
kubectl get pvc -A -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,ACCESS:.spec.accessModes | grep -E "home-assistant|mosquitto|n8n|node-red|grafana|adguard-home|paperless-data|jdownloader|esphome|music-assistant|scrypted|jellyfin|plex"

# Count share managers
kubectl get pods -n storage | grep share-manager | wc -l
# Expected after migration: 1 (nextcloud only)

# Check app pod health
kubectl get pods -A | grep -E "home-assistant|mosquitto|n8n|node-red|grafana|adguard-home|paperless|jdownloader|esphome|music-assistant|scrypted|jellyfin|plex"
```

### Monitor During Migration
```bash
# Terminal 1: Watch pods
watch "kubectl get pods -A | grep -E 'home-assistant|mosquitto|n8n|node-red|grafana|adguard-home|paperless|jdownloader|esphome|music-assistant|scrypted|jellyfin|plex'"

# Terminal 2: Watch events
kubectl get events -A --watch

# Terminal 3: Watch share managers
watch "kubectl get pods -n storage | grep share-manager"

# Terminal 4: Watch Flux
flux get kustomizations --watch
```

### Rollback Single App
```bash
# Find migration commit
git log --oneline kubernetes/apps/{namespace}/{app}/app/pvc.yaml

# Revert
git revert <commit-hash>
git push
```

---

**Last Updated**: 2026-01-04 (AdGuard Home restored)
**Updated By**: Claude Code
**Next Review**: Continue with remaining migrations
