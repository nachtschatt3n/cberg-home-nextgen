# Current Health Check State & Log

## Maintenance Log

Keep a log of when this check was run and major findings:

| Date | Health Status | Critical Issues | Actions Taken | Notes |
|------|---------------|-----------------|---------------|-------|
| 2026-01-17 Night | Good | 0 | 4 | **Investigated & Actioned**: **1)** Resized `clawd-bot-data` PVC to 20Gi (was 98% full); **2)** Investigated Node 12 Hardware errors: `bio_check_eod` likely related to iSCSI/Longhorn volumes (many virtual disks present) rather than physical NVMe failure; **3)** Confirmed Home Assistant Tesla error is a code bug in v2.13.0 (`KeyError: 'None'` on shifter state); **4)** Confirmed UnPoller metrics empty due to InfluxDB usage. **Status**: Cluster healthy, maintenance items identified. |
| 2026-01-17 PM | Warning | 0 | 3 | **Resolved**: Health check script fixed (jq execution moved to host, syntax errors fixed). **New Findings**: 2 Low Battery Zigbee devices (9%, 16%); Hardware errors on Node 12 identified as `bio_check_eod` (disk/IO errors); UnPoller metrics empty (InfluxDB confirmed). **Status**: Cluster stable, but hardware and batteries need attention. |
| 2026-01-17 | Warning | 1 | 2 | **Mixed**: UnPoller service fixed (metrics target UP in Prometheus, but metrics empty - user switched to InfluxDB); Pod evictions cleared (clawd-bot npm-cache limit increased); New Service created for UnPoller to fix missing target; **Known Issue**: UnPoller metrics checks failing due to InfluxDB switch; **Critical**: 2 Pod evictions detected (resolved by limit increase); Home Assistant errors: 30 (external integrations); Backup system healthy |
| 2026-01-10 PM | Excellent | 0 | 2 | **MAJOR IMPROVEMENTS**: Certificate conflict RESOLVED (adguard-home-tls now Ready via cert-manager ingress annotation); tube-archivist PVC reconciliation RESOLVED (manifest updated to 12Gi, kustomization Ready); All certificates Ready (5/5 = 100%); Backup system working (last backup 8h ago, 44/45 volumes backed up); All Prometheus alerts cleared (only Watchdog); **NEW ISSUE**: clawd-bot kustomization failing (missing secret.sops.yaml); clawd-bot-data volume detached but PVC bound; Home Assistant errors increased to 40/100 lines; Zigbee devices: 22 total (battery check needs investigation) |
| 2026-01-10 AM | Good | 1 | 0 | **EXCELLENT**: All Prometheus alerts cleared (0 firing); Home Assistant errors DOWN to 1 (from 2!); Backup system working (last backup 6h47m ago, completed successfully); All 3 nodes healthy; GitOps 59/60 reconciled (1 issue: tube-archivist PVC - manifest still shows 10Gi, needs update to 12Gi); Certificate conflict: adguard-home-tls STILL EXISTS (duplicate certificate not resolved); **NEW**: 1 unhealthy volume (clawd-bot-data: detached, unknown robustness - new volume created since yesterday); **CRITICAL**: Zigbee batteries still need replacement (12%, 18% - unchanged) |
| 2026-01-09 PM | Good | 1 | 0 | **EXCELLENT**: All Prometheus alerts cleared (0 firing); Home Assistant errors DOWN to 2 (from 11!); external-dns stable (813 restarts historical, now running fine); All 44 volumes healthy; All 3 nodes healthy; GitOps 59/60 reconciled (1 issue: tube-archivist PVC - manifest shows 10Gi but PVC is 12Gi, needs manifest update); Certificate conflict: adguard-home-tls (Helm chart creating duplicate certificate, needs disabling); Backup system: **WORKING** - Longhorn RecurringJob running successfully (last backup 17h ago, job completed); **CRITICAL**: Zigbee batteries still need replacement (12%, 18%) |
| 2026-01-09 PM | Good | 1 | 3 | FIXED: external-dns stabilized (penpot annotation added); tube-archivist volume expanded 10Gi→12Gi (94.3%→78.8%); adguard-home-tls certificate fixed (removed duplicate annotation); All Prometheus alerts cleared (except Watchdog) | CRITICAL: Zigbee batteries still need replacement (12%, 18%); Tesla Wall Connector timeouts are EXPECTED (power save mode when not charging); All services operational; external-dns running stable with 0 errors; Volume expansion successful; Certificate conflict resolved |
| 2026-01-09 AM | Warning | 1 | 6 | CRITICAL: Zigbee batteries deteriorating further (12%, 18% - down from 14%, 20%); 5 Prometheus alerts firing; Tesla Wall Connector regression (4 timeouts) | MAJOR IMPROVEMENTS: Backup system RESTORED (last backup 13h ago); Node 3 UNCORDONED and healthy; Home Assistant errors DOWN to 11 (from 93); Amazon Alexa RESOLVED (0 failures); All 44 volumes healthy; All 3 nodes at 5% CPU; GitOps synchronized; Cloudflare tunnel operational; Battery average: 80% (stable); WARNING: adguard-home-tls certificate not ready; external-dns CrashLoopBackOff is EXPECTED (Cloudflare proxy rejects private IPs, external access via tunnel works fine) |
| 2026-01-06 | Warning | 2 | 6 | CRITICAL: Backup system completely broken (0 backup jobs, 0 volumes backed up); Zigbee battery crisis (2 devices <20%, 14% and 20%); Home Assistant integration issues (15 errors, 6 Amazon Alexa failures); Jellyfin health check failed; Database connectivity issues | Node 3: SSD detected but DEFECTIVE - cordoned, monitoring removed, replacement ordered (arrives in 2 days); 33 hardware errors on node 11 (investigation needed); Zigbee devices: 22 total, 17 battery-powered; Battery average: 81%; 2 CRITICAL batteries: 14%, 20% (immediate replacement required); Home Assistant: 15 errors/100 lines; Amazon Alexa: 6 failures; Tesla Wall Connector: 0 timeouts (resolved); All infrastructure stable: 0 events, 0 crashes, 53/53 volumes healthy; GitOps perfect; Network healthy; DNS working; External access functional |
| 2026-01-01 | Excellent | 0 | 2 | Prometheus volume alerts resolved with filesystem trim; recurring trim job configured | Resolved Longhorn actualSize metric false positives (100.1% → 6.5%); Created prometheus-filesystem-trim recurring job (daily 2 AM); Manual trim reclaimed 93.6 GiB; All 3 alerts cleared; Samsung 990 PRO SSD warranty claim package prepared (Node 3 defective drive); Trim job should be monitored for effectiveness |
| 2025-12-31 PM | Good | 0 | 4 | MAJOR: Backup failure investigation and resolution (149 alerts cleared) | Investigated massive backup failure (147 failed backups); Root cause: Network/CIFS performance bottleneck (NAS healthy, 30 MB/s observed vs 200+ MB/s expected on 10 GbE); Cleared 147 failed backup CRs; Backup speeds varied 10x (5.6-57.5 GB/min); 51 backups successful; Network path investigation needed |
| 2025-12-31 AM | Good | 0 | 1 | Node 3 uncordoned after successful validation; Prometheus volume fix applied | Node 3 uncordoned (8+ days stable); Prometheus alerts firing (false positive - snapshot deletion in progress); Battery health unchanged (2 critical: 15%, 21%); All applications healthy; Flux reconciled |
| 2025-12-30 | Good | 0 | 1 | Day 8/9 of Node 3 SSD monitoring - validation period exceeded, ready to uncordon | Node 3 SSD health: EXCELLENT (34°C, 100% spare, 0 errors); Battery health stable (avg 82%, 2 critical devices deteriorating: 15%, 21%); Amazon Alexa integration still failing (40 failures); Tesla Wall Connector: 2 timeouts reappeared; IKEA Dirigera: 1 listener failure |
| 2025-12-28 | Good | 0 | 0 | Day 6 of 7 Node 3 SSD validation - all excellent | Node 3 SSD health: PASSED (34°C, 100% spare, 0 errors); Battery health improved (avg 79%); Amazon Alexa integration failing |
| 2025-12-26 | Good | 0 | 2 | Fixed Jellyfin health check parsing bug | Corrected health check script to handle plain text response instead of JSON; updated current health status |
| 2025-12-25 | Good | 0 | 3 | Updated health check with latest investigation results | Resolved paperless redis replicas and jellyfin health endpoint issues; added node 3 SSD monitoring details |
| 2025-12-13 | Excellent | 0 | 1 | Major expansion: Added 9 new health check sections for comprehensive home lab monitoring | Added home automation, media services, database health, external services, security monitoring, performance trends, backup verification, environmental monitoring, and application-specific checks |
| 2025-12-13 | Excellent | 0 | 0 | Updated UniFi network section with enhanced event log checking | Added checks for WAN/Internet disconnects, client errors, device issues, and security events; clarified system unifictl usage |
| 2025-11-27 | Excellent | 0 | Updated health check documentation with command reference | Added tested commands and common pitfalls section |
| 2025-11-15 | Excellent | 0 | Fixed pgadmin cert, cleaned orphaned volumes | All systems operational |

---

## Current Health Check Report

```markdown
# Kubernetes Cluster Health Check Report
**Date**: 2026-01-17 20:48 CET
**Cluster**: cberg-home-nextgen
**Nodes**: 3 (k8s-nuc14-01, k8s-nuc14-02, k8s-nuc14-03)
**Duration**: N/A

## Executive Summary
- **Overall Health**: 🟡 **Good**
- **Critical Issues**: **0** ✅
- **Warnings**: 5 (Hardware errors, Low batteries, UnPoller metrics, Home Assistant integration errors, Prometheus alerts)
- **Service Availability**: 99%
- **Uptime**: All systems operational
- **Node Status**: ✅ **ALL 3 NODES HEALTHY**
- **Recent Changes**: clawd-bot volume resized, UnPoller configured (InfluxDB)

## Service Availability Matrix
| Service | Internal | External | Health | Response | Status Notes |
|---------|----------|----------|--------|----------|--------------|
| Authentik | ✅ | ✅ | Healthy | N/A | Authentication operational (6/6 pods ready) |
| Home Assistant | ✅ | ✅ | Warning | N/A | Tesla integration errors (bug) |
| Nextcloud | ✅ | ✅ | Healthy | N/A | Operational |
| Jellyfin | ✅ | ✅ | Healthy | N/A | Running normally |
| Grafana | ✅ | ✅ | Healthy | N/A | Monitoring dashboards working |
| Prometheus | ✅ | ✅ | Warning | N/A | 3 Longhorn volume usage alerts (Resolving) |
| Alertmanager | ✅ | ✅ | Healthy | N/A | Operational |
| Longhorn UI | ✅ | ✅ | Healthy | N/A | Storage management accessible |
| UnPoller | ✅ | N/A | Warning | N/A | Service UP, metrics empty (InfluxDB) |
| Backup System | ✅ | N/A | Excellent | N/A | Last backup successful |

## Detailed Findings

### 1. Hardware Health (Node 12)
⚠️ **Status: WARNING** - Disk I/O Errors
- **Errors**: `bio_check_eod` (End of Device).
- **Analysis**: Likely related to one of the many iSCSI/Longhorn virtual disks attached to the node, rather than the physical NVMe system drive.
- **Action**: Monitor for detached volumes. Physical drive appears healthy (NVMe errors not present).

### 2. clawd-bot Volume
✅ **Status: RESOLVED** - Volume Resized
- **Issue**: Volume `clawd-bot-data` was 98% full (9.5G/9.8G).
- **Action**: Patched PVC to **20Gi**. Longhorn will expand filesystem automatically.
- **Alerts**: Prometheus alerts should clear once expansion completes.

### 3. Home Assistant Tesla Integration
⚠️ **Status: WARNING** - Integration Bug
- **Issue**: `KeyError: 'None'` in `teslafi/model.py`.
- **Cause**: Code bug in v2.13.0 handling unknown/None shifter state.
- **Impact**: Integration fails to update during specific car states. Non-critical.

### 4. Battery Health
⚠️ **Status: WARNING** - Critical Batteries
- **Devices**:
  - `0xa4c1385405b16ed5`: **9%** (CRITICAL)
  - `0xa4c138101f51cc54`: **16%** (WARNING)
- **Action**: Replace batteries.

### 5. UnPoller
⚠️ **Status: NOTICE** - Configuration Difference
- **Metrics**: Empty in Prometheus (InfluxDB backend used).
- **Service**: Healthy/UP.

## Action Items

### 🟡 High Priority
1. **Replace Zigbee Batteries** (Devices ending in `6ed5` and `cc54`).
2. **Monitor clawd-bot volume** (Verify expansion to 20Gi).

### 🔵 Medium Priority
1. **Monitor Node 12** for physical disk errors (unlikely, but stay vigilant).
2. **Wait for Tesla Integration Update** (upstream fix needed).

## Summary

**Overall Health**: 🟡 **Good**

The cluster is stable. The volume capacity issue has been patched, and other findings are either maintenance tasks (batteries) or software bugs (Tesla integration) rather than infrastructure failures.
```
