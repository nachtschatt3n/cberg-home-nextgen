# Current Health Check State & Log

## Maintenance Log

Keep a log of when this check was run and major findings:

| Date | Health Status | Critical Issues | Actions Taken | Notes |
|------|---------------|-----------------|---------------|-------|
| 2026-02-21 (evening) | Good | 0 | 3 | **Overall**: 🟡 **GOOD** (0 Critical, 0 Major, 5 Minor/Info). **Fixes applied this session**: 1) `monitoring/elasticsearch` ILM bootstrap Job deleted → Flux recreated with curl:8.18.0, fluent-bit and kibana unblocked ✅; 2) `office/nextcloud-notify-push` binary path corrected (`notify_push/notify_push/bin/x86_64/`) + execute bit restored → pod Running 0 restarts ✅; 3) `databases/redisinsight` rollingUpdate conflict confirmed resolved (PRs #88+#89, RollingUpdate maxSurge:0) ✅. **Full 39-section health check**: Cluster: All 3 nodes healthy (v1.34.0, CPU ~6%, Memory 26-37%), 0 OOM kills, 0 evictions. GitOps: 85/85 kustomizations reconciled, 72/72 HelmReleases ready, 46/46 HelmRepositories ready, 7/7 Flux controllers running (47d uptime, 0 restarts). Storage: 68/68 Longhorn volumes attached/healthy, autoDeletePod=false ✅, 75/75 PVCs Bound. Backups: daily-backup-all-volumes completed 13h ago ✅. Certs: 8/8 Ready, renewing mid-March. DaemonSets: 12/12 healthy. Pods: 0 CrashLoopBackOff, 0 Pending, 0 Terminating. Container log errors: 0 (Cilium, CoreDNS, Flux, cert-manager). Network: UnPoller healthy (Err:0, 104-106 clients, 1 USG+5 USW+4 UAP); MQTT: 0 auth failures, 0 errors. Home Automation: HA running 6d18h, Zigbee 22/23 seen today (1 offline >7d: 0x00124b002d12beec - likely dead battery), Mosquitto healthy, Frigate running 12d 0 restarts. Databases: All 8 pods running. Media: Jellyfin 14d, Plex 41d, JDownloader 7h all running. Ingress: 0 controller errors. Webhooks: 7 validating + 4 mutating, 0 failures. **Minor/Info**: external-dns 29 restarts (diagnosed: transient Cloudflare EOF, self-healing, no action needed ✅); unpoller 11 restarts (diagnosed: healthy, Err:0, periodic re-auth normal ✅); Talos version drift client v1.11.6 vs nodes v1.11.0 (upgrade needed); music_assistant duplicate entity IDs in HA (non-critical); cloudflared 5 restarts 2d15h ago (monitoring). **Talos client/node version mismatch**: client v1.11.6, nodes v1.11.0 — upgrade nodes when convenient. |
| 2026-02-21 | Warning | 1 | 3 | **Overall**: 🟠 **WARNING** (1 real Critical - opencode OOM, 0 Major, 1 Minor - node 12 noise). **Cluster**: All 3 nodes healthy (v1.34.0, CPU 4-5%, Memory 26-38%), 0 warning events, 3 OOM kills (opencode), 0 pod evictions. **GitOps**: 83/83 kustomizations reconciled, 72/72 HelmReleases ready, all HelmRepositories healthy, 7/7 Flux controllers running. **Storage**: 58/58 Longhorn volumes healthy, autoDeletePod=false, 75 PVCs all Bound. **Backups**: daily-backup-all-volumes completed successfully (12h ago, 17m duration), 5/5 recent jobs successful. **Certificates**: 8/8 ready. **DaemonSets**: All healthy. **Monitoring**: Prometheus & Alertmanager running, 0 firing alerts. **Pods**: 0 CrashLoopBackOff, 0 Pending; 2 pods with elevated restarts (opencode-andreamosteller: 1 - recent OOM, external-dns: 28 - historical). **Network**: UnPoller healthy (10 devices, 115 clients, 0 export errors), MQTT broker healthy (46/54 clients connected, 15 Shelly devices, 0 auth failures, 0 errors). **Home Automation**: HA running (errors: Tibber 4403 Invalid Token - FALSE POSITIVE external bug, music_assistant duplicate entity IDs), Zigbee2MQTT healthy (23 devices, 0 errors), Mosquitto healthy. **Frigate**: All 6 cameras streaming, MQTT availability online, 0 crash loops. **Batteries**: 20 battery devices (avg 81%, 0 critical, 0 warning, 1 monitor: Soil Sensor 1 at 42%). **Elasticsearch Logs**: 10,000+ errors/day (fluent-bit: 40K, kube-apiserver: 11K). 3 FATAL/OOM errors: opencode OOMKilled, external-dns transient EOF. **FIXED**: Increased opencode memory limit to 2Gi; Confirmed Tibber 4403 is external platform bug. |
| 2026-02-15 | Good | 0 | 1 | **Overall**: 🟡 **GOOD** (0 real Critical, 0 Major, 2 Minor). **Cluster**: All 3 nodes healthy (v1.34.0, CPU 4-7%, Memory 29-39%), 0 warning events, 0 OOM kills, 0 pod evictions. **GitOps**: 83/83 kustomizations reconciled, 72/72 HelmReleases ready, all HelmRepositories healthy, 7/7 Flux controllers running. **Storage**: 58/58 Longhorn volumes healthy, autoDeletePod=false, 74 PVCs all Bound. **Backups**: daily-backup-all-volumes completed successfully (8h ago, 22m duration), 5/5 recent jobs successful. **Certificates**: 8/8 ready. **DaemonSets**: All healthy. **Monitoring**: Prometheus & Alertmanager running, 0 firing alerts. **Pods**: 0 CrashLoopBackOff, 0 Pending; 2 pods with elevated restarts (unpoller: 9, external-dns: 13 - historical). **Network**: UnPoller healthy (10 devices, 109 clients, 0 export errors), MQTT broker healthy (46/54 clients connected, 15 Shelly devices in recent logs, 0 auth failures, 0 errors). **Home Automation**: HA running (31 major errors - mostly music_assistant duplicate entity IDs, samsung_familyhub_fridge API error, dynamic_energy_cost unavailable, ESPHome voice device unreachable), Zigbee2MQTT healthy (23 devices, 0 errors), Mosquitto healthy. **Frigate**: All 6 cameras streaming, MQTT availability online, 0 crash loops. **Batteries**: 20 battery devices (avg 82%, 0 critical, 0 warning, 1 monitor: Soil Sensor 1 at 46%). **Elasticsearch Logs**: 10,000+ errors/day (Frigate: 36K, fluent-bit: 29K, kube-apiserver: 7.8K). 1 FATAL error: external-dns transient EOF (self-recovered). **FIXED**: Removed 2 duplicate `kids_room_ventilate_reminder` automations from HA config. **ShellyWallDisplay-000822A9320E** (WallDisplay Upper Hallway, Shelly Wall Display, upper_hallway): Still rapid MQTT reconnection cycling every ~5 seconds. **FALSE POSITIVE DOCUMENTED**: Authentik outpost ExternalName services showing "no backends" is expected - ExternalName services resolve via DNS, not Endpoints objects. Updated health-check.sh to skip ExternalName services and AI_weekly_health_check.MD to document this. **Ingress**: 87 errors at check time but cleared shortly after. **Webhooks**: 11 configured, all healthy. |
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
**Date**: 2026-02-21 ~18:00 CET
**Cluster**: cberg-home-nextgen
**Nodes**: 3 (k8s-nuc14-01, k8s-nuc14-02, k8s-nuc14-03)
**Kubernetes Version**: v1.34.0

## Executive Summary
- **Overall Health**: 🟡 **GOOD**
- **Critical Issues**: 0
- **Major Issues**: 0
- **Minor Issues**: 5 (Talos version drift, 1 Zigbee device offline, music_assistant dupes, cloudflared restarts, Soil Sensor battery)
- **Service Availability**: 99%+
- **Node Status**: ✅ ALL 3 NODES HEALTHY

## Fixes Applied This Session
| Fix | Result |
|-----|--------|
| `monitoring/elasticsearch` ILM bootstrap Job (immutable field) | Deleted old Job → Flux recreated with curl:8.18.0 → fluent-bit + kibana unblocked ✅ |
| `office/nextcloud-notify-push` binary missing (`no such file`) | Corrected path to `notify_push/notify_push/bin/x86_64/` + chmod +x → pod Running 0 restarts ✅ |
| `databases/redisinsight` rollingUpdate forbidden | Confirmed resolved via PRs #88+#89 (RollingUpdate maxSurge:0) ✅ |

## Service Availability Matrix
| Service | Internal | External | Health | Status Notes |
|---------|----------|----------|--------|--------------|
| Authentik | ✅ | ✅ | Healthy | 6 pods (3 server + 3 worker), recently recycled (44m) |
| Home Assistant | ✅ | ✅ | Healthy | Running 6d18h, Tibber 4403 FALSE POSITIVE (unchanged) |
| zigbee2mqtt | ✅ | ✅ | Healthy | 23 devices, 22/23 seen today, 2 restarts (stable) |
| Mosquitto MQTT | ✅ | N/A | Healthy | 0 auth failures, 0 errors |
| Nextcloud | ✅ | ✅ | Healthy | notify-push fixed, Running |
| Jellyfin | ✅ | ✅ | Healthy | Running 14d |
| Plex | ✅ | ✅ | Healthy | Running 41d |
| Tube Archivist | ✅ | ✅ | Healthy | Running, elasticsearch + redis healthy |
| Grafana | ✅ | ✅ | Healthy | Running |
| Prometheus | ✅ | ✅ | Healthy | Running 13d, 0 alerts firing |
| Alertmanager | ✅ | ✅ | Healthy | Running 44m |
| Longhorn UI | ✅ | ✅ | Healthy | 68/68 volumes attached and healthy |
| Frigate | ✅ | ✅ | Healthy | Running 12d, 0 restarts, 0 camera crashes |
| Backup System | ✅ | N/A | Healthy | Last backup 13h ago ✅ |
| UnPoller | ✅ | N/A | Healthy | Err:0, 104-106 clients, periodic re-auth normal |
| Elasticsearch | ✅ | N/A | Healthy | ILM Job fixed, fluent-bit + kibana now reconciled |
| fluent-bit | ✅ | N/A | Healthy | Unblocked after elasticsearch Job fix |
| external-dns | ✅ | ✅ | Healthy | 29 restarts diagnosed: transient Cloudflare EOF, self-healing ✅ |
| Cloudflared | ✅ | ✅ | Monitor | 5 restarts 2d15h ago — monitoring |
| All databases | ✅ | N/A | Healthy | postgres, mariadb, influxdb, redis, nocodb all running |

## Detailed Findings

### 1. Talos Version Drift
🔵 **Status: MINOR** — talosctl client v1.11.6 vs nodes v1.11.0
- Upgrade nodes to v1.11.6 when convenient to avoid API compatibility issues.

### 2. Zigbee Device Offline >7 Days
🔵 **Status: MINOR** — `0x00124b002d12beec` last seen 2026-02-05
- Likely dead battery or decommissioned device. Check physically or remove from config.

### 3. Home Assistant music_assistant Duplicate Entities
🔵 **Status: MINOR/INFO** — non-unique entity IDs
- Affected: Downstairs, Andrea's Family Hub, Pioneer VSX-1131 (×2), HA Voice media players.
- Entities are ignored by HA. No functional impact. Clean up duplicate names in music_assistant.

### 4. Cloudflared Restarts
🔵 **Status: MONITOR** — 5 restarts, last 2d15h ago
- External access is functional. Monitor for recurrence.

### 5. Battery Health
✅ **Status: GOOD** — all batteries acceptable
- **CRITICAL (<30%)**: 0
- **WARNING (30-50%)**: 0 (Soil Sensor 1 was 42% last check — check current level)
- **Zigbee devices**: 23 total, 0 low batteries detected

### 6. Infrastructure Health
✅ **Status: EXCELLENT**
- **Nodes**: All 3 Ready (v1.34.0), CPU ~6%, Memory 26-37%
- **Node pressure**: 0 (no DiskPressure/MemoryPressure/PIDPressure)
- **Certificates**: 8/8 ready, renewing mid-March (auto-managed)
- **DaemonSets**: 12/12 healthy
- **GitOps**: 85/85 kustomizations reconciled, 72/72 HelmReleases ready, 46/46 HelmRepositories ready
- **Flux Controllers**: 7/7 running (47d uptime, 0 restarts)
- **Volumes**: 68/68 attached and healthy, autoDeletePod=false ✅
- **PVCs**: 75/75 Bound
- **Backup**: Last successful 13h ago (daily-backup-all-volumes)
- **OOM Kills**: 0
- **Pod Evictions**: 0
- **CrashLoopBackOff**: 0
- **Pending pods**: 0
- **Terminating**: 0
- **Container log errors**: 0 (Cilium, CoreDNS, Flux, cert-manager)
- **Webhooks**: 7 validating + 4 mutating, 0 failures
- **Ingress controller errors**: 0

### 7. Network & MQTT
✅ **Status: HEALTHY**
- **UnPoller**: Err:0 every cycle, 104-106 clients, 4 UAPs, 5 USW, 1 UDM
- **MQTT**: 0 auth failures, 0 connection errors
- **external-dns**: Diagnosed — transient Cloudflare EOF causes exit, self-heals on restart. No DNS outages. No action needed.

## Action Items

### 🔵 Low Priority
1. **Upgrade Talos nodes** from v1.11.0 → v1.11.6 (match talosctl client)
2. **Check Zigbee device** `0x00124b002d12beec` — replace battery or remove from config
3. **Clean up music_assistant** — rename duplicate media player entries to get unique entity IDs
4. **Monitor Soil Sensor 1 battery** — was 42% last check

### ✅ Resolved Since Last Check (2026-02-21 morning)
1. `monitoring/elasticsearch` ILM bootstrap immutable Job — deleted and recreated ✅
2. `office/nextcloud-notify-push` binary path and permissions — fixed ✅
3. `databases/redisinsight` rollingUpdate strategy — confirmed fixed via #88+#89 ✅
4. `network/external-dns` 29 restarts — diagnosed as self-healing Cloudflare EOF, no action needed ✅
5. `monitoring/unpoller` 11 restarts — diagnosed as healthy, Err:0, no action needed ✅
6. `monitoring/fluent-bit` + `monitoring/kibana` blocked — unblocked after elasticsearch Job fix ✅
7. `opencode-andreamosteller` OOM — memory limit increased to 2Gi (prior session) ✅

## Summary

**Overall Health**: 🟡 **GOOD**

Comprehensive 39-section health check completed. Three active issues were fixed during the session (elasticsearch Job, notify-push binary, redisinsight confirmed resolved). The cluster is in excellent shape: 0 CrashLoopBackOff, 0 Pending, all 85 kustomizations and 72 HelmReleases reconciled, 68 Longhorn volumes healthy, backups running on schedule. Remaining action items are all low-priority maintenance tasks (Talos upgrade, one offline Zigbee device, music_assistant cleanup).
```
