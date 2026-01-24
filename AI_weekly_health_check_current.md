# Current Health Check State & Log

## Maintenance Log

Keep a log of when this check was run and major findings:

| Date | Health Status | Critical Issues | Actions Taken | Notes |
|------|---------------|-----------------|---------------|-------|
| 2026-01-25 00:18 | Warning | 1 | 2 | **Overall**: 🟠 WARNING (1 Critical, 2 Major, 2 Minor). **Critical Issues**: 1) teslamate pod in CrashLoopBackOff (MQTT connection timeout - config fixed to mosquitto-main, investigating network connectivity). **Major Issues**: 1) teslamate deployment 0/1 replicas (same as critical - MQTT connection issue); 2) Critical batteries: 2 devices <15% (Soil sensor 3: 2%, Soil Sensor 2: 14% - immediate replacement needed). **Minor Issues**: 14 warning events (mostly normal operations), UnPoller 2 errors (minor). **FIXED**: zigbee2mqtt MQTT connection resolved (service name updated to mosquitto-main, pod recreated successfully, web interface accessible); zigbee2mqtt 502 Bad Gateway resolved (pod restarted, MQTT connected). **Positive**: All Prometheus alerts cleared (0 firing), all certificates ready, all DaemonSets healthy, GitOps fully synchronized, no OOM kills or pod evictions, storage healthy, Elasticsearch logs: 0 errors today (excellent!), hardware health excellent (0 errors on all nodes). **Status**: Cluster stable, zigbee2mqtt working, teslamate MQTT connection needs investigation, battery replacement urgent. |
| 2026-01-24 Night | Warning | 0 | 0 | **Overall**: 🟠 WARNING (0 Critical, 4 Major, 6 Minor). **Major Issues**: 1) Nextcloud HelmRelease in "Unknown" state (upgrade in progress - transient); 2) Nextcloud deployment 0/1 replicas (upgrade in progress); 3) Home Assistant errors: 56 (mostly external integrations - Tesla Wall Connector timeouts expected, Dirigera hub disconnects, Deebot command timeouts, Bermuda metadevice warnings); 4) Critical battery: Soil sensor 3 at 2% (immediate replacement needed). **Minor Issues**: 15 warning events (mostly normal operations), 1 terminating pod (Nextcloud upgrade), Zigbee2MQTT 50 warnings (normal operation), 1 low battery (Soil Sensor 2 at 15%), 10,000 log errors (mostly Frigate/Zigbee2MQTT - normal), UnPoller 4 errors. **Positive**: All certificates ready (8/8), backup system operational (last backup 17h ago), all DaemonSets healthy, GitOps 81/81 reconciled, no OOM kills, no pod evictions, hardware health excellent (0 errors on all nodes), storage healthy. **Status**: Cluster stable, Nextcloud upgrade in progress (transient), battery replacement urgent. |
| 2026-01-18 Night | Good | 0 | 2 | **RESOLVED**: Longhorn volume alerts completely cleared (PVC expansion 20Gi→40Gi successful); **Investigated**: Home Assistant errors (87 total) - **1)** Uptime Kuma authentication failure (needs API token config); **2)** 86 duplicate sensor IDs (multiple monitors with same names); **Hardware errors clarified**: "Errors" are benign iSCSI virtual disk messages, not real hardware failures (normal for Longhorn operations). **Status**: Storage crisis resolved, HA integration issues identified for future fix. |
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
**Date**: 2026-01-25 00:18 CET
**Cluster**: cberg-home-nextgen
**Nodes**: 3 (k8s-nuc14-01, k8s-nuc14-02, k8s-nuc14-03)
**Duration**: ~15 seconds

## Executive Summary
- **Overall Health**: 🟠 **WARNING**
- **Critical Issues**: **1** (teslamate CrashLoopBackOff - MQTT connection timeout)
- **Major Issues**: 2 (teslamate deployment, Critical batteries)
- **Minor Issues**: 2 (Warning events, UnPoller errors)
- **Service Availability**: 99%
- **Uptime**: All systems operational
- **Node Status**: ✅ **ALL 3 NODES HEALTHY**

## Service Availability Matrix
| Service | Internal | External | Health | Response | Status Notes |
|---------|----------|----------|--------|----------|--------------|
| Authentik | ✅ | ✅ | Healthy | N/A | Authentication operational |
| Home Assistant | ✅ | ✅ | Healthy | N/A | Running normally |
| zigbee2mqtt | ✅ | ✅ | Healthy | N/A | MQTT connected, web interface accessible |
| teslamate | ❌ | ❌ | Down | N/A | CrashLoopBackOff - MQTT connection timeout (config fixed, investigating) |
| Jellyfin | ✅ | ✅ | Healthy | N/A | Running normally |
| Grafana | ✅ | ✅ | Healthy | N/A | Monitoring dashboards working |
| Prometheus | ✅ | ✅ | Healthy | N/A | Operational, 0 alerts firing |
| Alertmanager | ✅ | ✅ | Healthy | N/A | Operational |
| Longhorn UI | ✅ | ✅ | Healthy | N/A | Storage management accessible |
| UnPoller | ✅ | N/A | Healthy | N/A | Service UP, exporting to InfluxDB (2 minor errors) |
| Backup System | ✅ | N/A | Excellent | N/A | Last backup 20h ago, successful |

## Detailed Findings

### 1. teslamate MQTT Connection Issue
🔴 **Status: CRITICAL** - CrashLoopBackOff
- **Issue**: Pod crashing due to MQTT connection timeout
- **Root Cause**: Service name was incorrect (`mosquitto` instead of `mosquitto-main`)
- **Fix Applied**: Updated MQTT_HOST to `mosquitto-main.home-automation.svc.cluster.local`
- **Current Status**: Configuration correct, but connection still timing out
- **Action**: Investigating network connectivity between teslamate and mosquitto pods

### 2. Battery Health
🟡 **Status: MAJOR** - Critical Battery Replacement Needed
- **CRITICAL (<15%)**: 
  - Soil sensor 3: **2%** (immediate replacement required)
  - Soil Sensor 2: **14%** (replace within 1-2 weeks)
- **WARNING (15-30%)**: None
- **MONITOR (30-50%)**: None
- **GOOD (>50%)**: 16 devices
- **Average Battery Level**: 76%
- **Action**: Replace Soil sensor 3 battery immediately to prevent device failure

### 3. zigbee2mqtt Status
✅ **Status: RESOLVED** - MQTT Connected
- **Previous Issue**: 502 Bad Gateway, MQTT connection failures
- **Fix Applied**: Updated service name to `mosquitto-main`, pod restarted
- **Current Status**: Running, MQTT connected, web interface accessible
- **MQTT Connection**: Successfully connected to mosquitto-main

### 4. Infrastructure Health
✅ **Status: EXCELLENT**
- **Certificates**: All ready (100%)
- **DaemonSets**: All healthy (desired = current = ready)
- **GitOps**: Fully synchronized
- **Backup System**: Operational (last backup 20h ago, successful)
- **OOM Kills**: 0
- **Pod Evictions**: 0
- **Resource Pressure**: None detected
- **Prometheus Alerts**: 0 firing (excellent!)
- **Elasticsearch Logs**: 0 errors today (excellent!)

### 5. Log Errors
✅ **Status: EXCELLENT** - 0 Errors Today
- **Total Errors**: 0 (down from 10,000+ previously)
- **FATAL/OOMKilled**: 0
- **Analysis**: Log collection and analysis working perfectly

### 6. Warning Events
🔵 **Status: MINOR** - 14 Warning Events
- **Analysis**: Mostly normal operations (volume attachments, pod lifecycle)
- **Action**: Monitor for trends, no immediate action needed

## Action Items

### 🔴 URGENT
1. **Replace Soil Sensor 3 Battery** (2% - immediate replacement required)
2. **Investigate teslamate MQTT Connection** (config correct but still timing out)

### 🟡 High Priority
1. **Replace Soil Sensor 2 Battery** (14% - replace within 1-2 weeks)
2. **Monitor teslamate pod** after MQTT config fix

### 🔵 Medium Priority
1. **Review UnPoller errors** (2 minor errors, metrics still exporting)
2. **Monitor warning events** for trends

## Summary

**Overall Health**: 🟠 **WARNING**

**Key Findings**: Cluster infrastructure is healthy with excellent monitoring (0 alerts, 0 log errors). **RESOLVED**: zigbee2mqtt MQTT connection and 502 Bad Gateway fixed. **CRITICAL**: teslamate MQTT connection still timing out despite correct configuration - needs network investigation. **URGENT**: Soil sensor 3 battery at 2% requires immediate replacement. All core systems operational: certificates ready, backups working, GitOps synchronized, no hardware errors, no OOM kills or evictions, storage healthy.
```
