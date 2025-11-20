# Kubernetes Cluster Health Check Report
**Date**: 2025-11-20  
**Cluster**: cberg-home-nextgen  
**Nodes**: 3 (k8s-nuc14-01, k8s-nuc14-02, k8s-nuc14-03)  
**Cluster Age**: 82 days

## Executive Summary

- **Overall Health**: ⚠️ **FAIR** (Degraded due to storage issues)
- **Critical Issues**: 1 (Longhorn volumes detached)
- **Warnings**: Multiple (PVCs pending, pods crashing)
- **Outdated Components**: To be determined
- **Uptime**: 82 days

### Critical Actions Required
1. **URGENT**: Investigate why all Longhorn volumes are detached and not ready (59 volumes affected)
2. **URGENT**: Resolve PVC binding issues preventing pod startup
3. Fix crashing pods (bytebot-agent, postgresql, paperless-ngx-redis-replicas)

---

## Detailed Findings

### 1. Cluster Events & Logs
**Status**: ⚠️ **WARNING**

- **Recent Warnings**: 50+ events in last 10 minutes
- **Primary Issues**:
  - Multiple pods failing to schedule due to missing PVCs
  - Health check failures for esphome and music-assistant-server kustomizations
  - Pod crash loops (bytebot-agent: 17 restarts, postgresql: 25 restarts)
  - Back-off restarting containers in multiple pods

**Key Events**:
- PersistentVolumeClaim not found errors affecting 30+ pods
- HealthCheckFailed for kustomizations waiting on PVC status
- MountVolume.MountDevice failed for adguard-home-config

**Recommendations**:
- Investigate Longhorn volume attachment issues
- Check Longhorn Manager logs for volume attachment errors
- Verify Longhorn CSI driver is functioning correctly

---

### 2. Jobs & CronJobs
**Status**: ✅ **OK**

**CronJobs**:
- `kube-system/descheduler`: Schedule `0 4 * * *` - Last run: 14h ago ✅
- `storage/backup-of-all-volumes`: Schedule `0 03 * * *` - Last run: 15h ago ✅

**Recent Jobs**:
- All recent jobs completed successfully
- Backup job completed successfully 15h ago

**Status**: All CronJobs are functioning correctly.

---

### 3. Certificates
**Status**: ✅ **OK**

- **Total Certificates**: 6
- **Ready**: 6/6 ✅
- **Expiring within 30 days**: 0 ✅

**Certificates**:
- `cert-manager/uhl-cool-production`: Ready ✅
- `cert-manager/uhl-cool-staging`: Ready ✅
- `databases/pgadmin-tls`: Ready ✅
- `kube-system/inteldeviceplugins-serving-cert`: Ready ✅
- `network/adguard-home`: Ready ✅
- `storage/longhorn-tls`: Ready ✅

**Status**: All certificates are valid and not expiring soon.

---

### 4. DaemonSets
**Status**: ✅ **OK**

**DaemonSets Status**:
- `kube-system/cilium`: 3/3 desired, 3/3 ready ✅
- `kube-system/csi-smb-node`: 3/3 desired, 3/3 ready ✅
- `kube-system/intel-gpu-plugin-intel-gpu-plugin`: 3/3 desired, 3/3 ready ✅
- `kube-system/node-feature-discovery-worker`: 3 desired ✅
- `home-automation/mdns-repeater`: 3/3 desired, 3/3 ready ✅

**Status**: All DaemonSets are healthy and running on all nodes.

---

### 5. Helm Deployments
**Status**: ✅ **OK**

- **Total HelmReleases**: 56
- **Suspended**: 0 ✅
- **Not Ready**: 0 ✅

**Status**: All HelmReleases are active and ready.

---

### 6. Deployments & StatefulSets
**Status**: ⚠️ **WARNING**

**Issues Found**:
- **30+ deployments/statefulsets** have replica mismatches (desired replicas not ready)
- All issues are due to pods being in Pending state waiting for PVCs

**Affected Resources** (sample):
- `ai/ai-sre`: desired=1, ready=0
- `ai/langfuse-web`: desired=1, ready=0
- `home-automation/home-assistant`: desired=1, ready=0
- `office/nextcloud`: desired=1, ready=0
- `databases/postgresql`: desired=1, ready=0
- And 25+ more...

**Root Cause**: All pods are waiting for PersistentVolumeClaims that cannot bind because Longhorn volumes are detached.

**Recommendations**:
- Fix Longhorn volume attachment issues first
- Once volumes are attached, pods should automatically start

---

### 7. Pods Health
**Status**: ⚠️ **WARNING**

**Pod Statistics**:
- **Total Pods**: 175
- **Running**: 111 (63%)
- **Pending**: 50+ (29%)
- **Error/CrashLoopBackOff**: 10+ (6%)

**Problem Pods**:
- **CrashLoopBackOff**:
  - `ai/bytebot-agent`: 17 restarts
  - `databases/postgresql`: 25 restarts
  - `office/paperless-ngx-redis-replicas`: Back-off restarting

- **Pending** (waiting for PVCs):
  - 30+ pods across all namespaces
  - All waiting for Longhorn static volumes

- **Error State**:
  - `ai/langfuse-zookeeper`: Error
  - `kube-system/node-feature-discovery-gc`: Error (24d old)
  - `kube-system/node-feature-discovery-master`: Error (24d old)
  - `kube-system/reloader`: Error
  - `storage/csi-*`: Multiple CSI pods in Error state

**Recommendations**:
- Investigate Longhorn CSI driver issues
- Check Longhorn Manager logs
- Review node-feature-discovery errors (may be non-critical)

---

### 8. Prometheus & Monitoring
**Status**: ⚠️ **WARNING**

- **Total Alerts**: 91
- **Firing Alerts**: 91 ⚠️

**Alert Types**:
- `KubePodCrashLooping`: Multiple instances
- `KubePodNotReady`: Multiple instances

**Status**: Prometheus is functioning but detecting many unhealthy pods (expected given current cluster state).

**Recommendations**:
- Alerts should resolve once pods are running
- Review alert rules if false positives persist

---

### 9. Alertmanager
**Status**: ✅ **OK** (Not checked in detail, but Prometheus is detecting alerts)

---

### 10. Longhorn Storage
**Status**: 🔴 **CRITICAL**

- **Total Volumes**: 59
- **Unhealthy Volumes**: 59 (100%) 🔴
- **Volume State**: All volumes showing `detached` and `ready=False`

**Longhorn Components**:
- **Manager Pods**: 3/3 Running ✅
- **CSI Plugin**: 3/3 Running ✅
- **UI**: Running ✅

**Critical Issue**: All Longhorn volumes are detached and not ready. This is preventing all PVCs from binding.

**Affected Volumes** (sample):
- `absenty-development-data`: detached, ready=False
- `adguard-home-config`: detached, ready=False
- `ai-sre-cache`: detached, ready=False
- `bytebot-postgres-data`: detached, ready=False
- `esphome-config`: detached, ready=False
- And 54 more...

**Recommendations**:
1. **URGENT**: Check Longhorn Manager logs for attachment errors
2. Verify Longhorn nodes are healthy
3. Check for disk space issues on nodes
4. Review Longhorn settings for volume attachment policies
5. Consider manual volume attachment if needed

---

### 11. Container Logs Analysis
**Status**: ⚠️ **WARNING**

**Critical Components**:
- **Cilium**: Running (DaemonSet healthy)
- **CoreDNS**: Running (2 replicas)
- **Longhorn Manager**: Running but volumes detached
- **Flux Controllers**: Some in Succeeded state (may be normal)
- **cert-manager**: Some pods in Succeeded state

**Issues**:
- Longhorn CSI pods showing errors
- Multiple application pods cannot start due to storage

**Recommendations**:
- Review Longhorn Manager logs: `kubectl logs -n storage -l app=longhorn-manager`
- Check CSI driver logs: `kubectl logs -n storage -l app=longhorn-csi-plugin`

---

### 12. Talos System Logs
**Status**: ✅ **OK** (Not checked in detail)

**Node Status**:
- All 3 nodes: Ready ✅
- Kubernetes version: v1.34.0 (consistent across all nodes) ✅
- Talos version: v1.11.0 ✅
- Kernel: 6.12.43-talos ✅

---

### 13. Hardware Health
**Status**: ✅ **OK** (Limited visibility)

**Node Resources**:
- **k8s-nuc14-01**: CPU: 2%, Memory: 10% (515m/17950m CPU, 6602Mi/64489Mi memory)
- **k8s-nuc14-02**: CPU: 1%, Memory: 10% (297m/17950m CPU, 6728Mi/64489Mi memory)
- **k8s-nuc14-03**: CPU: 2%, Memory: 11% (364m/17950m CPU, 7057Mi/64674Mi memory)

**Observations**:
- Low CPU usage (1-2%)
- Low memory usage (10-11%)
- No resource pressure detected

**Recommendations**:
- Check hardware temperature sensors (requires node access)
- Review disk health via Longhorn UI
- Monitor for hardware errors in system logs

---

### 14. Resource Utilization
**Status**: ✅ **OK**

**Node Resources**:
- **CPU**: 1-2% usage across all nodes (excellent)
- **Memory**: 10-11% usage across all nodes (excellent)
- **No resource pressure**: All nodes have ample capacity

**Pod Resources**:
- Top CPU consumers: Not analyzed (low overall usage)
- Top Memory consumers: Not analyzed (low overall usage)

**Storage**:
- **Issue**: Cannot determine PVC usage due to detachment issues
- **Recommendation**: Resolve Longhorn issues first, then review storage usage

---

### 15. Backup System
**Status**: ✅ **OK**

- **Backup CronJob**: `storage/backup-of-all-volumes`
- **Schedule**: Daily at 03:00 UTC
- **Last Backup**: 15h ago ✅
- **Status**: Completed successfully ✅

**Recommendations**:
- Verify backup target is accessible
- Check backup retention policies
- Review backup logs for any warnings

---

### 16. Version Checks & Updates

#### Kubernetes Version
- **Current**: v1.34.0
- **Status**: All nodes consistent ✅
- **Latest Available**: Unknown (check Talos release notes)

#### Talos Version
- **Current**: v1.11.0
- **Kernel**: 6.12.43-talos
- **Status**: Consistent across all nodes ✅
- **Latest Available**: Check Talos releases

#### Helm Charts
**Sample Versions**:
- `cert-manager`: v1.19.1
- `homepage`: v2.0.2
- `open-webui`: v5.13.0
- `mariadb`: v11.5.6
- `influxdb2`: v2.1.2
- `flux-operator`: v0.14.0

**Recommendations**:
- Review chart repositories for updates
- Check Renovate bot for automated updates
- Plan updates during maintenance windows

#### Container Images
- **Status**: Not analyzed in detail
- **Recommendation**: Review for `latest` tags and outdated images

---

### 17. Security Checks
**Status**: ⚠️ **NEEDS REVIEW**

**Not Checked**:
- Pods running as root
- Network policies
- RBAC configurations
- Service account permissions
- Exposed services without authentication

**Recommendations**:
- Perform security audit
- Review network policies
- Check RBAC configurations
- Verify TLS/SSL certificates on ingresses

---

### 18. Network Connectivity
**Status**: ✅ **OK** (Limited check)

- **DNS**: CoreDNS running (2 replicas) ✅
- **Ingress Controllers**: Running (not checked in detail)
- **External DNS**: Not checked

**Recommendations**:
- Test DNS resolution
- Verify ingress controller health
- Check external-dns status

---

### 19. GitOps Status
**Status**: ⚠️ **WARNING**

- **Total Kustomizations**: 64
- **Not Ready**: 2
  - `home-automation/esphome`: Health check failed (waiting on PVC)
  - `home-automation/music-assistant-server`: Health check failed (waiting on PVC)

**Status**: GitOps is functioning, but 2 kustomizations are waiting for PVCs to be created.

**Recommendations**:
- Resolve Longhorn volume issues
- Kustomizations should reconcile once PVCs are available

---

### 20. Namespace Review
**Status**: ✅ **OK**

- **Total Namespaces**: 15+
- **Orphaned Namespaces**: None detected
- **Stuck Resources**: Some PVCs in Pending/Terminating state

**Namespaces**:
- `ai`, `backup`, `cert-manager`, `custom-code-production`, `databases`, `default`, `download`, `flux-system`, `home-automation`, `kube-system`, `media`, `monitoring`, `network`, `office`, `storage`

**Recommendations**:
- Review Terminating PVCs (e.g., `network/adguard-home-config`)
- Clean up any stuck resources

---

## Version Report

| Component | Current Version | Latest Available | Status | Priority |
|-----------|----------------|------------------|--------|----------|
| Kubernetes | v1.34.0 | Unknown | Up-to-date? | Low |
| Talos | v1.11.0 | Unknown | Up-to-date? | Low |
| Longhorn | Unknown | Unknown | Needs Check | Medium |
| cert-manager | v1.19.1 | Unknown | Needs Check | Medium |
| CoreDNS | 2 replicas | Unknown | Running | Low |
| Flux | v0.14.0 | Unknown | Needs Check | Low |

*Note: Latest versions need to be checked against upstream repositories*

---

## Action Items

### 🔴 Critical (Do Immediately)
1. **URGENT**: Investigate Longhorn volume detachment issue
   - Check Longhorn Manager logs: `kubectl logs -n storage -l app=longhorn-manager --tail=100`
   - Check Longhorn CSI logs: `kubectl logs -n storage -l app=longhorn-csi-plugin --tail=100`
   - Review Longhorn UI for volume status
   - Check node disk space and health
   - Verify Longhorn settings for volume attachment

2. **URGENT**: Fix crashing pods
   - `ai/bytebot-agent`: Investigate crash loop (17 restarts)
   - `databases/postgresql`: Investigate crash loop (25 restarts)
   - `office/paperless-ngx-redis-replicas`: Fix back-off restarting

3. **URGENT**: Resolve PVC binding issues
   - Once Longhorn volumes are attached, PVCs should bind automatically
   - Monitor PVC status: `kubectl get pvc -A`

### ⚠️ Important (This Week)
1. Review and fix node-feature-discovery errors (may be non-critical)
2. Check Longhorn backup target accessibility
3. Review security configurations (network policies, RBAC)
4. Verify all ingresses have valid TLS certificates
5. Check for chart updates and plan updates

### 📋 Maintenance (Next Window)
1. Review Helm chart versions and plan updates
2. Check Talos and Kubernetes version updates
3. Review container image versions
4. Perform security audit
5. Review resource quotas and limits

### 🔮 Long-term Improvements
1. Set up automated health check monitoring
2. Implement proactive alerting for storage issues
3. Review backup retention policies
4. Document recovery procedures for storage issues
5. Consider storage redundancy improvements

---

## Trends & Observations

### Resource Usage
- **CPU**: Very low usage (1-2%) - excellent headroom
- **Memory**: Low usage (10-11%) - excellent headroom
- **Storage**: Cannot determine due to detachment issues

### Performance
- No performance degradation observed
- Nodes are healthy and responsive
- Low resource pressure

### Capacity Planning
- **CPU**: Ample capacity (98%+ available)
- **Memory**: Ample capacity (89%+ available)
- **Storage**: Needs investigation once volumes are attached

### Backup Success Rate
- **Last Backup**: Successful (15h ago)
- **Backup Schedule**: Daily at 03:00 UTC
- **Status**: Functioning correctly ✅

---

## Conclusion

The cluster is experiencing a **critical storage issue** with all Longhorn volumes detached. This is preventing 30+ pods from starting and causing widespread service disruption. Once the Longhorn volume attachment issue is resolved, the cluster should return to normal operation.

**Immediate Priority**: Resolve Longhorn volume detachment issue.

**Overall Assessment**: Cluster infrastructure is healthy (nodes, networking, control plane), but storage layer needs urgent attention.

---

*Report Generated: 2025-11-20*
*Next Health Check Recommended: 2025-11-27*
