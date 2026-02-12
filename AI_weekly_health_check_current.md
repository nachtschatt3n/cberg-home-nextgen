# Current Health Check State & Log

## Maintenance Log

Keep a log of when this check was run and major findings:

| Date | Health Status | Critical Issues | Actions Taken | Notes |
|------|---------------|-----------------|---------------|-------|
| 2026-02-12 | Good | 0 | 0 | **Overall**: 🟡 **GOOD** (0 Critical, 2 Major, 2 Minor). **Cluster**: All 3 nodes healthy (v1.34.0, CPU 4-6%, Memory 27-37%), 0 warning events, 0 OOM kills, 0 pod evictions. **GitOps**: 82/82 kustomizations reconciled, 72/72 HelmReleases ready, all HelmRepositories healthy, 7/7 Flux controllers running. **Storage**: 58/58 Longhorn volumes healthy, autoDeletePod=false, 74 PVCs all Bound. **Backups**: daily-backup-all-volumes completed successfully (12h ago, 17m duration), 4/5 recent jobs successful. **Certificates**: 8/8 ready. **DaemonSets**: All healthy. **Monitoring**: Prometheus & Alertmanager running, 1 firing alert (LonghornVolumeUsageWarning: influxdb2-data-10g). **Pods**: 0 CrashLoopBackOff, 0 Pending; 2 pods with elevated restarts (clawd-bot: 82, external-dns: 6 - historical). **Network**: UnPoller healthy (10 devices, 105-106 clients, 0 export errors), MQTT broker healthy (46/54 clients connected, 26 Shelly devices, 0 auth failures, 0 errors). **Home Automation**: HA running (95 major errors - almost entirely Bermuda metadevice bugs from Entry SW02 + Tesla Wall Connector timeouts + 1 Shelly reconnection error), Zigbee2MQTT healthy (23 devices, 0 errors), Mosquitto healthy. **Batteries**: All 20 battery devices healthy (avg 82%, 0 critical, 0 warning). **Elasticsearch Logs**: 10,000 errors/day (mostly fluent-bit self-referential logs in monitoring namespace: 39,075; kube-apiserver: 10,510; home-automation: 3,096 - no FATAL/OOM errors). **ShellyWallDisplay-000822A9320E**: Still rapid reconnection cycling every ~5 seconds from 192.168.33.47. **Ingress**: 11 Authentik outpost services showing no backends (ExternalName services, expected behavior). **Webhooks**: 11 configured (7 validating, 4 mutating), all healthy. **Minor Issues**: 1) talosctl unavailable; 2) Elevated log error count: 10,000. |
| 2026-02-09 | Excellent | 0 | 0 | **Overall**: ✅ **EXCELLENT** (0 Critical, 0 Major, 4 Minor). **Cluster**: All 3 nodes healthy (v1.34.0, CPU 5-7%, Memory 27-34%), 0 warning events, 0 OOM kills, 0 pod evictions. **GitOps**: 82/82 kustomizations reconciled, 72/72 HelmReleases ready, all HelmRepositories healthy, 7/7 Flux controllers running. **Storage**: 58/58 Longhorn volumes healthy, autoDeletePod=false, 0 PVC issues. **Backups**: daily-backup-all-volumes completed successfully (11h ago, 18m duration), 4/5 recent jobs successful. **Certificates**: 8/8 ready. **DaemonSets**: All healthy. **Monitoring**: Prometheus & Alertmanager running, 0 firing alerts. **Pods**: 0 CrashLoopBackOff, 0 Pending; 2 pods with elevated restarts (clawd-bot: 22, external-dns: 6 - historical). **Network**: UnPoller healthy (10 devices, 104-105 clients, 0 export errors), MQTT broker healthy (46/54 clients connected, 0 auth failures, 0 errors). **Home Automation**: HA running (10 errors - external integrations: TeslaFi read errors, Shelly Entry Window Blinds, Dirigera hub disconnects, Wyze camera API 504, Tesla Wall Connector timeouts), Zigbee2MQTT healthy (23 devices, 0 errors), Mosquitto healthy. **Batteries**: All 20 battery devices healthy (avg 82%, 0 critical, 0 warning). **Elasticsearch Logs**: 10,000 errors/day (mostly fluent-bit self-referential logs in monitoring namespace: 36,914; kube-apiserver: 9,777; home-automation: 1,433 - no FATAL/OOM errors). **ShellyWallDisplay-000822A9320E**: Rapid reconnection cycling every ~5 seconds from 192.168.33.47 (investigate keepalive/firmware). **Minor Issues**: 1) talosctl unavailable; 2) HA integration errors: 10; 3) Elevated log error count: 10,000; 4) UnPoller minor errors: 1. |
| 2026-02-06 | Good | 0 | 0 | **Overall**: ✅ **GOOD** (0 Critical, 2 Major, 2 Minor). **Major Issues**: 1) scrypted HelmRelease failed (install timeout - pod running 25d, stale failure state); 2) Flic Hub offline at 192.168.33.133 (not reachable, HA connection errors). **Minor Issues**: 1) Prometheus & InfluxDB volume alerts (high usage warnings, but under 75%); 2) Home Assistant errors: 371 (mostly Bermuda metadevice bugs, Flic Hub, Tibber token invalid). **Positive**: All 3 nodes healthy (v1.34.0), all pods running (181/199 Running), all 8 certificates ready, 82/82 kustomizations ready, 71/72 HelmReleases ready, 58 Longhorn volumes healthy, backup successful (6h ago), DaemonSets healthy, no hardware errors, no pod evictions, Zigbee batteries all healthy (lowest 63%), teslamate resolved & running, zigbee2mqtt MQTT connected. **Status**: Cluster healthy, investigate Flic Hub offline, Tibber token needs refresh. |
| 2026-01-26 | Excellent | 0 | 4 | **Overall**: ✅ **EXCELLENT** (0 Critical, 0 Major, 0 Minor). **MAJOR SUCCESS**: Shelly MQTT infrastructure completely resolved! **Accomplishments**: 1) Fixed Cilium v1.18.6 LoadBalancer issue (restarted DaemonSet, restored connectivity to MQTT broker at 192.168.55.15); 2) Comprehensive Shelly device audit completed (scanned 192.168.32.0/23, found 39 physical devices vs 74 cloud entries); 3) Fixed 4 Shelly devices: 3 Wall Displays (192.168.33.42, 43, 47) + Fridge (192.168.32.149) - all configured with MQTT credentials; 4) Added Section 22a to health check documentation and script for ongoing MQTT/Shelly monitoring. **Results**: 38/39 devices connected to MQTT (97.4% success rate), only 1 device offline (Dining Room wall display confirmed offline in cloud). **Mystery Solved**: "36 missing devices" explained - 28 virtual i4 inputs, 10 battery sensors (sleeping), 2 server VLAN devices, 4 actually offline, 1 virtual thermostat. **Documentation**: Updated AI_weekly_health_check.MD (35 sections), health-check.sh script, comprehensive reports generated. **Status**: All critical systems operational, smart home infrastructure healthy, monitoring enhanced. |
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
**Date**: 2026-02-12 17:00 CET
**Cluster**: cberg-home-nextgen
**Nodes**: 3 (k8s-nuc14-01, k8s-nuc14-02, k8s-nuc14-03)
**Kubernetes Version**: v1.34.0

## Executive Summary
- **Overall Health**: 🟡 **GOOD**
- **Critical Issues**: 0
- **Major Issues**: 2 (1 Prometheus alert firing, Home Assistant high error count)
- **Minor Issues**: 2 (talosctl unavailable, elevated log errors)
- **Service Availability**: 99%+
- **Uptime**: All systems operational
- **Node Status**: ✅ **ALL 3 NODES HEALTHY**

## Service Availability Matrix
| Service | Internal | External | Health | Status Notes |
|---------|----------|----------|--------|--------------|
| Authentik | ✅ | ✅ | Healthy | 6 pods (3 server + 3 worker) |
| Home Assistant | ✅ | ✅ | Healthy | Running 5d6h (95 errors - Bermuda/Tesla) |
| zigbee2mqtt | ✅ | ✅ | Healthy | 23 devices, MQTT connected, 0 errors |
| Mosquitto MQTT | ✅ | N/A | Healthy | 46 active clients, 26 Shelly devices, 0 errors |
| Jellyfin | ✅ | ✅ | Healthy | Running 5d |
| Tube Archivist | ✅ | ✅ | Healthy | Running 3d19h |
| Grafana | ✅ | ✅ | Healthy | 1 pod running |
| Prometheus | ✅ | ✅ | Healthy | 1 alert firing (volume usage) |
| Alertmanager | ✅ | ✅ | Healthy | Operational |
| Longhorn UI | ✅ | ✅ | Healthy | 58/58 volumes healthy, all attached |
| Frigate | ✅ | ✅ | Healthy | Top CPU consumer (297m), 4780Mi memory |
| Backup System | ✅ | N/A | Excellent | Last backup 12h ago, 17m duration |
| UnPoller | ✅ | N/A | Healthy | 10 UniFi devices, 106 clients, 0 errors |
| Elasticsearch | ✅ | N/A | Healthy | 4448Mi memory, logs indexed |

## Detailed Findings

### 1. Prometheus Alert: InfluxDB Volume Usage
🟡 **Status: MAJOR** - LonghornVolumeUsageWarning firing
- **Volume**: influxdb2-data-10g in databases namespace
- **Issue**: PVC usage high (10Gi allocation)
- **Action**: Monitor usage, consider PVC expansion if needed

### 2. Home Assistant Bermuda Integration Bug
🟡 **Status: MAJOR** - 95 errors in last 100 log lines
- **Primary Source**: `custom_components.bermuda` - "Calling process_advertisement on a metadevice (Entry SW02)" bug
- **Volume**: Hundreds of errors per minute across ~25 BLE devices
- **Secondary**: Tesla Wall Connector timeouts (192.168.32.146 - expected when not charging)
- **Secondary**: Shelly Entry SW02 reconnection error (1 occurrence)
- **Impact**: Log noise, no functional impact
- **Action**: Update Bermuda custom component when fix available

### 3. Shelly Wall Display Reconnection Cycling
🔵 **Status: MINOR** - Persistent from previous checks
- **Device**: ShellyWallDisplay-000822A9320E at 192.168.33.47
- **Issue**: Reconnecting every ~5 seconds to MQTT broker
- **Impact**: MQTT log noise, no functional impact
- **Action**: Investigate keepalive settings or firmware update

### 4. Elevated Elasticsearch Error Count
🔵 **Status: MINOR** - 10,000 errors/day
- **Top Sources**: fluent-bit pods (22,801 + 9,309 + 6,926) - self-referential log collection
- **kube-apiserver**: 3,498 + 3,454 errors (normal operational noise)
- **home-automation**: 3,096 (Bermuda bug)
- **No FATAL/OOM errors detected**
- **Action**: Mostly noise, monitor for trend changes

### 5. Pod Restart Counts
🔵 **Status: INFORMATIONAL**
- **clawd-bot**: 82 restarts (historical, currently running)
- **external-dns**: 6 restarts (historical, currently running)
- **No pods currently in CrashLoopBackOff or Pending**

### 6. Battery Health
✅ **Status: EXCELLENT** - All batteries healthy
- **Total battery-powered devices**: 20
- **CRITICAL (<15%)**: 0
- **WARNING (15-30%)**: 0
- **MONITOR (30-50%)**: 0
- **GOOD (>50%)**: 19 devices
- **Average battery level**: 82%

### 7. Infrastructure Health
✅ **Status: EXCELLENT**
- **Nodes**: All 3 Ready (v1.34.0)
- **CPU Usage**: k8s-nuc14-01: 4%, k8s-nuc14-02: 5%, k8s-nuc14-03: 4%
- **Memory Usage**: k8s-nuc14-01: 27%, k8s-nuc14-02: 37%, k8s-nuc14-03: 34%
- **Certificates**: 8/8 ready (100%)
- **DaemonSets**: 11/11 healthy (including csi-smb-node-win 0/0 expected)
- **GitOps**: 82/82 kustomizations reconciled, 72/72 HelmReleases ready
- **HelmRepositories**: All healthy, 0 failures
- **Flux Controllers**: 7/7 running (38d uptime)
- **Volumes**: 58/58 attached and healthy
- **PVCs**: 74/74 Bound
- **Backup**: Last successful 12h ago (daily-backup-all-volumes, 17m duration)
- **OOM Kills**: 0
- **Pod Evictions**: 0
- **Warning Events**: 0
- **Webhooks**: 11 configured (7 validating, 4 mutating), all healthy
- **Namespaces**: 20 total, 0 terminating

### 8. Network & MQTT
✅ **Status: HEALTHY**
- **UnPoller**: 10 UniFi devices (1 GW, 4 APs, 5 switches), 105-106 clients, 0 errors
- **MQTT Broker**: 54 total clients (46 active, 8 inactive)
- **Shelly Devices**: 26 identified in recent logs
- **MQTT Auth Failures**: 0
- **Ingress Controllers**: Internal + External running, external-dns healthy

### 9. Ingress Backends
✅ **Status: EXPECTED** - 11 Authentik outpost services show no backends
- These are ExternalName services pointing to Authentik outposts in kube-system
- Services: nocodb, phpmyadmin, homepage, esphome, frigate, alertmanager, headlamp, prometheus, uptime-kuma (x2), longhorn
- **No ingress controller errors** in last hour

## Action Items

### 🟡 High Priority
1. **Monitor InfluxDB volume** (influxdb2-data-10g alert firing - consider expansion or cleanup)
2. **Update Bermuda component** (metadevice bug generating ~95 errors/minute)

### 🔵 Medium Priority
1. **Investigate ShellyWallDisplay reconnection cycling** (firmware update or keepalive tuning)
2. **Install talosctl** on management host for hardware health monitoring

### ✅ Resolved Since Last Check (2026-02-09)
1. **scrypted HelmRelease** - No longer showing failed (was stale failure state)
2. **Flic Hub** - No longer generating HA errors (resolved or removed from integrations)
3. **Tibber Token** - No longer showing invalid token errors
4. **All HelmReleases** - Now 72/72 healthy (was 71/72)

## Summary

**Overall Health**: 🟡 **GOOD**

The cluster is fundamentally healthy with all core infrastructure operating normally. All 3 nodes running Kubernetes v1.34.0, 72/72 HelmReleases ready, 82/82 kustomizations reconciled, 58/58 Longhorn volumes healthy, backups running successfully. The two major issues are: 1) InfluxDB volume usage alert (needs monitoring/expansion), and 2) Home Assistant Bermuda custom component generating excessive error logs (a bug in the component, no functional impact). The elevated Elasticsearch error count (10,000/day) is mostly self-referential fluent-bit logs and kube-apiserver operational noise with zero FATAL/OOM errors. Battery health is excellent across all 20 devices (average 82%). Several issues from the previous check have been resolved including the scrypted HelmRelease, Flic Hub, and Tibber token problems.
```
