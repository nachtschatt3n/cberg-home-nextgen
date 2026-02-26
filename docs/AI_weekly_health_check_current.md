# Current Health Check State & Log

## Maintenance Log

Keep a log of when this check was run and major findings:

| Date | Health Status | Critical Issues | Actions Taken | Notes |
|------|---------------|-----------------|---------------|-------|
| 2026-02-26 (afternoon) | Good | 0 | 5 | **Overall**: 🟡 **GOOD** (0 real issues). **Actions Taken**: 1) Upgraded Authentik from 2025.12.4 to 2026.2.0 (Required fixing DB expressions to use `groups` instead of deprecated `ak_groups`, and syncing `initContainers` image tag to `2026.2.0` to avoid django config crashes); 2) Applied 6 patch updates (`node-red` 4.1.6, `n8n` 2.10.1, `esphome` 2026.2.2, `mariadb` chart 25.0.1, `ai-sre` 2.1.1, `eck-operator` chart 3.3.1); 3) Investigated Longhorn 1.11.0 update - Deferred due to severe memory leak bug in instance manager (Issue #12573). **Cluster**: All 3 nodes healthy, GitOps synced. **Status**: Minor updates and major Authentik update successfully applied. |
| 2026-02-26 (midday) | Good | 0 | 2 | **Overall**: 🟡 **GOOD** (0 real issues, 3 script flags resolved/false positive). **Actions Taken**: 1) Investigated 1 FATAL log in Elasticsearch (external-dns transient EOF, self-resolved); 2) Deleted stuck 37h `descheduler-29531760` job to clear `KubeJobNotCompleted` Prometheus alert and "failed jobs" warning ✅. **Cluster**: All 3 nodes healthy, 0 active alerts (post-cleanup), backups complete (daily-backup-all-volumes succeeded 03:15 UTC). **Status**: Cluster healthy, minor job cleanup performed. |
| 2026-02-24 (evening) | Excellent | 0 | 8 | **Overall**: ✅ **EXCELLENT** (0 real issues, 2 script false positives). **Script flags**: 1) 3 FATAL errors in Elasticsearch — all from `external-dns` `level=fatal` log field (transient EOF, self-recovered); 2) 1 failed job — descheduler still running at check time (false positive). **Cert alert**: `KubeClientCertificateExpiration WARNING` on `192.168.55.11:6443` — transient histogram spike, self-resolved, all actual certs healthy (kubelet: 314d, apiserver: 181d, cert-manager: 39–50d). **Cluster**: All 3 nodes healthy, 0 active alerts, 75/75 PVCs Bound. **Patch updates applied**: cert-manager v1.19.3→v1.19.4 (CVE fix), vaultwarden 1.35.3→1.35.4, jdownloader v26.02.2→v26.02.3, open-webui chart 12.3.0→12.5.0 + image 0.8.3→0.8.5 (all pods verified running post-upgrade). **PRs merged**: #92 n8n 2.9.1→2.10.0 (v2 migration complete), #93 flux2 aqua tool 2.7.5→2.8.0. **Renovate fix**: Migrated `absenty` ImageRepository/ImagePolicy/ImageUpdateAutomation from `image.toolkit.fluxcd.io/v1beta2` → `v1` (dev+prod) — clears 3 stale Renovate dashboard items. **Tools fix**: version check output → `docs/` folder, added tag normalization (v-prefix, OS variants like `-alpine`). **Pending**: authentik 2026.2.0 (major), longhorn 1.11.0 (minor), cilium 1.19.1 (minor), ai-sre 2.1.1 (owner). |
| 2026-02-22 (evening) | Warning | 1 | 1 | **Overall**: 🟠 **WARNING** (1 real Critical - Elasticsearch FATAL logs, 1 Major - Failed Jobs, 2 Minor). **Actions Taken**: 1) Fixed `nextcloud-cron` failure by adding `securityContext` (UID 33) to the `worker` sidecar in Nextcloud HelmRelease ✅. **Health Check**: Nodes healthy, storage healthy, GitOps synchronized. **Critical/Major Issues**: 1) 6 FATAL/OOM errors in Elasticsearch logs (linked to `external-dns` transient EOF errors - self-recovered); 2) 2 failed `nextcloud-cron` jobs (UID mismatch - resolved). **Minor Issues**: 1) "Hardware errors" on node 12 (identified as opencode OOMs and benign Longhorn iSCSI noise). **Status**: Cluster stable, issues addressed or identified as transient/benign. |
| 2026-02-22 (afternoon) | Good | 0 | 2 | **Overall**: 🟡 **GOOD** (0 Critical, 0 Major, 4 Minor). **Actions Taken**: 1) Deleted stuck job `kube-system/descheduler-29528880` (8h running); 2) Fixed `absenty` Flux Kustomization failures by downgrading `ImagePolicy` manifests to `v1beta2` (API `v1` not supported); 3) Verified "hardware errors" on node 12 are transient DNS timeouts from Feb 19th (false positive). **Health Check**: Nodes healthy, storage healthy, monitoring operational. **Minor Issues**: 1) Talos version drift; 2) 1 Zigbee device offline; 3) music_assistant duplicates; 4) Soil Sensor battery monitoring. **Status**: Cluster healthy, minor issues resolved. |
| 2026-02-22 | Good | 0 | 8 | **Overall**: 🟡 **GOOD** — Major upgrade + maintenance session. **Patch updates**: authentik 2025.12.3→4, vaultwarden 1.35.2→3, adguard-home v0.107.71→72, node-red 4.1.4→5. **Minor updates**: descheduler chart 0.34.0→0.35.0, intel-device-plugin charts 0.34.1→0.35.0 (×2), unpoller v2.33.0→v2.34.0, penpot chart 0.33.0→0.35.0 — all services confirmed running post-upgrade. **open-webui 10.2.1→12.3.0**: Required deleting immutable `open-webui-pipelines` Deployment (chart 12.x changed label selectors), adding `upgrade.timeout: 15m`, explicit Redis URL `redis://open-webui-redis:6379/0`. All pods running post-upgrade. **Flux CRD API migration**: 47 files migrated from deprecated `helm.toolkit.fluxcd.io/v2beta1/v2beta2` → `/v2` and `source/image.toolkit.fluxcd.io/v1beta2` → `/v1` (stable). **Renovate ignoreDeps**: Added `nachtschatt3n/k8s-self-ai-ops` (private GitHub repo, no token access). **ECK operator 2.14.0→3.3.0**: No breaking changes for ES/Kibana 8.15.3 users. Upgrade succeeded immediately. **fluent-bit chunk retry backlog**: Diagnosed pre-existing issue — 3600+ queued retry tasks, only 2 workers, 15-retry limit. ES healthy (0 write rejections, 30% heap, logs still ingesting). Fixed by restarting DaemonSet to clear backlog. Added log pipeline monitoring to health check docs. **Deferred (require investigation)**: longhorn 1.10.1→1.11.0 (pre-upgrade volume checks needed), cilium (HA mDNS/UPnP post-validation needed), nextcloud chart 6.6.10→8.9.1, uptime-kuma 2.25.0→4.0.0, Talos/K8s cluster upgrade, n8n v2 migration (BLOCKED), mariadb chart migration (BLOCKED). |
| 2026-02-21 (evening) | Good | 0 | 3 | **Overall**: 🟡 **GOOD** (0 Critical, 0 Major, 5 Minor/Info). **Fixes applied this session**: 1) `monitoring/elasticsearch` ILM bootstrap Job deleted → Flux recreated with curl:8.18.0, fluent-bit and kibana unblocked ✅; 2) `office/nextcloud-notify-push` binary path corrected (`notify_push/notify_push/bin/x86_64/`) + execute bit restored → pod Running 0 restarts ✅; 3) `databases/redisinsight` rollingUpdate conflict confirmed resolved (PRs #88+#89, RollingUpdate maxSurge:0) ✅. **Full 39-section health check**: Cluster: All 3 nodes healthy (v1.34.0, CPU ~6%, Memory 26-37%), 0 OOM kills, 0 evictions. GitOps: 85/85 kustomizations reconciled, 72/72 HelmReleases ready, 46/46 HelmRepositories ready, 7/7 Flux controllers running (47d uptime, 0 restarts). Storage: 68/68 Longhorn volumes attached/healthy, autoDeletePod=false ✅, 75/75 PVCs Bound. Backups: daily-backup-all-volumes completed 13h ago ✅. Certs: 8/8 Ready, renewing mid-March. DaemonSets: 12/12 healthy. Pods: 0 CrashLoopBackOff, 0 Pending, 0 Terminating. Container log errors: 0 (Cilium, CoreDNS, Flux, cert-manager). Network: UnPoller healthy (Err:0, 104-106 clients, 1 USG+5 USW+4 UAP); MQTT: 0 auth failures, 0 errors. Home Automation: HA running 6d18h, Zigbee 22/23 seen today (1 offline >7d: 0x00124b002d12beec - likely dead battery), Mosquitto healthy, Frigate running 12d 0 restarts. Databases: All 8 pods running. Media: Jellyfin 14d, Plex 41d, JDownloader 7h all running. Ingress: 0 controller errors. Webhooks: 7 validating + 4 mutating, 0 failures. **Minor/Info**: external-dns 29 restarts (diagnosed: transient Cloudflare EOF, self-healing, no action needed ✅); unpoller 11 restarts (diagnosed: healthy, Err:0, periodic re-auth normal ✅); Talos version drift client v1.11.6 vs nodes v1.11.0 (upgrade needed); music_assistant duplicate entity IDs in HA (non-critical); cloudflared 5 restarts 2d15h ago (monitoring). **Talos client/node version mismatch**: client v1.11.6, nodes v1.11.0 |
| 2026-02-21 | Warning | 1 | 3 | **Overall**: 🟠 **WARNING** (1 real Critical - opencode OOM, 0 Major, 1 Minor - node 12 noise). **Cluster**: All 3 nodes healthy (v1.34.0, CPU 4-5%, Memory 26-38%), 0 warning events, 3 OOM kills (opencode), 0 pod evictions. **GitOps**: 83/83 kustomizations reconciled, 72/72 HelmReleases ready, all HelmRepositories healthy, 7/7 Flux controllers running. **Storage**: 58/58 Longhorn volumes healthy, autoDeletePod=false, 75 PVCs all Bound. **Backups**: daily-backup-all-volumes completed successfully (12h ago, 17m duration), 5/5 recent jobs successful. **Certificates**: 8/8 ready. **DaemonSets**: All healthy. **Monitoring**: Prometheus & Alertmanager running, 0 firing alerts. **Pods**: 0 CrashLoopBackOff, 0 Pending; 2 pods with elevated restarts (opencode-andreamosteller: 1 - recent OOM, external-dns: 28 - historical). **Network**: UnPoller healthy (10 devices, 115 clients, 0 export errors), MQTT broker healthy (46/54 clients connected, 15 Shelly devices, 0 auth failures, 0 errors). **Home Automation**: HA running (errors: Tibber 4403 Invalid Token - FALSE POSITIVE external bug, music_assistant duplicate entity IDs), Zigbee2MQTT healthy (23 devices, 0 errors), Mosquitto healthy. **Frigate**: All 6 cameras streaming, MQTT availability online, 0 crash loops. **Batteries**: 20 battery devices (avg 81%, 0 critical, 0 warning, 1 monitor: Soil Sensor 1 at 42%). **Elasticsearch Logs**: 10,000+ errors/day (fluent-bit: 40K, kube-apiserver: 11K). 3 FATAL/OOM errors: opencode OOMKilled, external-dns transient EOF. **FIXED**: Increased opencode memory limit to 2Gi; Confirmed Tibber 4403 is external platform bug. |

---

## Current Health Check Report

```markdown
# Kubernetes Cluster Health Check Report
**Date**: 2026-02-26 (midday) CET
**Cluster**: cberg-home-nextgen
**Nodes**: 3 (k8s-nuc14-01, k8s-nuc14-02, k8s-nuc14-03)
**Kubernetes Version**: v1.34.0

## Executive Summary
- **Overall Health**: 🟡 **GOOD**
- **Critical Issues**: 0
- **Major Issues**: 0
- **Minor Issues**: 0
- **Service Availability**: 100%
- **Node Status**: ✅ ALL 3 NODES HEALTHY
- **Script reported**: 🟠 WARNING (all flags were false positives or have been cleaned up — see findings)

## Service Availability Matrix
| Service | Internal | External | Health | Status Notes |
|---------|----------|----------|--------|--------------|
| Authentik | ✅ | ✅ | Healthy | Running |
| Home Assistant | ✅ | ✅ | Healthy | Running, 0 critical errors |
| Zigbee2MQTT | ✅ | N/A | Healthy | Running |
| Mosquitto MQTT | ✅ | N/A | Healthy | Running |
| Nextcloud | ✅ | ✅ | Healthy | Running, cron jobs completing |
| Jellyfin | ✅ | ✅ | Healthy | Running |
| Plex | ✅ | ✅ | Healthy | Running |
| Tube Archivist | ✅ | ✅ | Healthy | Running |
| Grafana | ✅ | ✅ | Healthy | Running |
| Prometheus | ✅ | ✅ | Healthy | Running |
| Alertmanager | ✅ | ✅ | Healthy | Running, 0 active alerts |
| Longhorn UI | ✅ | ✅ | Healthy | All volumes healthy |
| Frigate | ✅ | ✅ | Healthy | Running |
| Backup System | ✅ | N/A | Healthy | Completed 03:15 UTC today |
| Elasticsearch | ✅ | N/A | Healthy | Running |
| external-dns | ✅ | ✅ | Healthy | Running, logs stable ("All records up to date") |

## Detailed Findings

### 1. Script "Critical": Elasticsearch FATAL logs — FALSE POSITIVE
✅ **Status: NO ACTION REQUIRED**
- **Script detected**: 1 FATAL entry in Elasticsearch
- **Actual cause**: `external-dns` uses `level=fatal` in its structured log format for transient errors
- **Errors**: `level=fatal msg="Failed to do run once: error reading response body: unexpected EOF"` at 09:12 UTC
- **Current state**: Pod running normally, logging "All records are already up to date" every ~60s

### 2. Script "Major/Minor": Prometheus Alert / Failed Jobs count — RESOLVED
✅ **Status: RESOLVED**
- **Script detected**: `KubeJobNotCompleted` alert and 1 failed job
- **Actual cause**: `kube-system/descheduler-29531760` job was stuck in Running state for 37h
- **Resolution**: Deleted the stuck job. CronJob will automatically recreate it on the next schedule. Alert has cleared.

## Infrastructure Metrics
- **Nodes**: 3/3 healthy (Talos v1.11.0, K8s v1.34.0)
- **Pods**: 0 CrashLoopBackOff, 0 Pending, 0 Terminating
- **DaemonSets**: All healthy
- **PVCs**: All Bound
- **Active Alertmanager alerts**: 0

## Pending Updates (Deferred)

| Component | Current | Latest | Category | Blocker |
|-----------|---------|--------|----------|---------|
| longhorn | 1.10.1 | 1.11.0 | 🟡 Minor | Waiting for `1.11.1` to avoid memory leak bug (#12573) |
| cilium | 1.18.6 | 1.19.1 | 🟡 Minor | CNI upgrade needs maintenance window |
| ai-sre | 2.1.0 | 2.1.1 | 🟢 Patch | Owner will handle |
| talos | v1.11.0 | v1.11.6 | 🟡 Minor | Node OS rolling upgrade needed |

## Recurring Pattern to Monitor
- **external-dns EOF restarts**: Transient Cloudflare API connection resets. Self-healing, no impact on DNS records.
```
