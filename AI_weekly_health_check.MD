# Weekly Kubernetes Cluster Health Check

## Purpose
This document contains a comprehensive health check prompt designed to be run weekly to ensure the cluster is operating optimally and all components are up-to-date.

## Frequency
**Run this check once per week** (recommended: Sunday evenings or Monday mornings)

---

## Health Check Prompt

```
Perform a comprehensive health check of my Kubernetes cluster. Check ALL of the following areas and provide a detailed report:

## 1. Cluster Events & Logs
- Check cluster events for errors, warnings, and failures (last 7 days)
- Review event log for any recurring issues
- Check for pod evictions or OOM kills

## 2. Jobs & CronJobs
- List all jobs and their status (successful/failed)
- Check all CronJobs and their schedules
- Verify last run times and success rates
- Identify any suspended or failing CronJobs

## 3. Certificates
- List all certificates across all namespaces
- Check expiration dates (flag any expiring within 30 days)
- Verify all certificates are in READY state
- Check certificate issuers and ACME challenges

## 4. DaemonSets
- Verify all DaemonSets have matching DESIRED/CURRENT/READY counts
- Check for any DaemonSets with update issues
- Review node selector configurations

## 5. Helm Deployments
- List all HelmReleases with their status
- Check for any suspended or failed releases
- Verify reconciliation status across all namespaces
- Check Flux kustomizations status

## 6. Deployments & StatefulSets
- Check all Deployments for ready replicas vs desired replicas
- Verify all StatefulSets are healthy
- Check for any deployments with mismatched replica counts
- Review pod distribution across nodes

## 7. Pods Health
- List all pods not in Running/Completed/Succeeded state
- Check for CrashLoopBackOff, ImagePullBackOff, Error, Pending pods
- Review pod restart counts (identify high restart counts)
- Check for pods stuck in Terminating state

## 8. Prometheus & Monitoring
- Check Prometheus for firing alerts
- Review alert severity and duration
- Check Prometheus logs for errors/warnings (last 24h)
- Verify all ServiceMonitors are being scraped
- Check for any targets down

## 9. Alertmanager
- List all active alerts
- Check Alertmanager configuration
- Verify alert routing is working
- Check for silenced alerts

## 10. Longhorn Storage
- Check all volume states (attached/detached/degraded/faulted)
- List any unhealthy volumes
- Check for orphaned volumes
- Verify replica counts and data locality
- Check Longhorn node status
- Review disk usage per node

## 11. Container Logs Analysis
- Check critical infrastructure component logs for errors:
  - Cilium (CNI)
  - CoreDNS
  - Longhorn Manager
  - Flux controllers
  - cert-manager
- Check application logs for critical errors (last 24h)
- Identify any components logging excessive warnings

## 12. Talos System Logs
- Check Talos system health
- Review kernel logs (dmesg) for errors
- Check for any hardware-related messages
- Verify Talos services are running

## 13. Hardware Health

### Temperature Monitoring
- Check all hardware temperature sensors
- Report min/max/average temperatures
- Flag any sensors above 80°C
- Check for thermal throttling

### Hardware Errors
- Check for disk errors (SMART status if available)
- Review memory errors (ECC if applicable)
- Check PCI device errors
- Verify all hardware is detected properly

### Network Health
- Check network interface errors (receive/transmit)
- Review network drop rates
- Check for network interface flapping
- Verify all expected interfaces are up

## 14. Resource Utilization

### Node Resources
- CPU usage per node (current and trends)
- Memory usage per node (available vs used)
- Disk usage per node (all mount points)
- System load (1m, 5m, 15m averages)
- Check for resource pressure (memory/disk/PID)

### Pod Resources
- Identify top 10 CPU consuming pods
- Identify top 10 memory consuming pods
- Check for pods exceeding resource limits
- Review resource requests vs limits ratios

### Storage
- Check for full or nearly full filesystems (>85%)
- Verify PVC status and usage
- Check for read-only filesystems (unexpected ones)

## 15. Backup System
- Check Longhorn backup target availability
- Verify last backup timestamp
- Check backup CronJob schedule and history
- Verify backup credentials are valid
- Check backup retention policies
- List recent backup job success/failure status

## 16. Version Checks & Updates

### Kubernetes Version
- Current Kubernetes version on all nodes
- Check for available Kubernetes updates
- Verify all nodes are on the same version
- Check API server, controller-manager, scheduler versions

### Talos Version
- Current Talos OS version on all nodes
- Check for available Talos updates
- Verify kernel version
- Check container runtime version

### Helm Charts
For each HelmRelease, check:
- Current chart version vs latest available version
- Chart repository status
- Flag outdated charts (>1 minor version behind)
- Check for deprecated chart versions

### Container Images
- List all container images in use
- Check for images using 'latest' tag (flag as potential issue)
- Identify images using old/outdated tags
- Check for images with known vulnerabilities (if scanning available)

### Longhorn Version
- Current Longhorn version
- Check for available Longhorn updates
- Verify all Longhorn components are same version
- Check Longhorn CSI driver version

### Core Infrastructure Versions
Check versions for:
- Cilium (CNI)
- CoreDNS
- cert-manager
- Flux (all controllers)
- Metrics Server
- Prometheus Operator
- Grafana
- Alertmanager

### Application Versions
For critical applications, check:
- Database versions (PostgreSQL, MariaDB, Redis, InfluxDB)
- Ingress controller versions
- Authentication services (Authentik)
- Monitoring stack versions
- Home automation platforms
- Media servers
- Any custom applications

## 17. Security Checks
- Check for pods running as root (if not necessary)
- Verify network policies are in place
- Check RBAC configurations
- Review service account permissions
- Check for exposed services without authentication
- Verify TLS/SSL certificate validity across ingresses

## 18. Network Connectivity
- Verify DNS resolution is working
- Check ingress controller health
- Verify external-dns is updating records
- Check Cloudflare tunnel status (if applicable)
- Test internal service discovery

## 19. GitOps Status
- Check Flux reconciliation status
- Verify Git repository connectivity
- Check for any drift between Git and cluster state
- Review webhook receiver status

## 20. Namespace Review
- List all namespaces
- Check for any orphaned namespaces
- Verify resource quotas (if set)
- Check for stuck resources in Terminating state

---

## Report Format

Provide the report in the following structure:

### Executive Summary
- Overall cluster health status (Excellent/Good/Fair/Poor)
- Number of critical issues
- Number of warnings
- Number of outdated components
- Recommended actions (prioritized)

### Detailed Findings
For each section above:
- ✅ Status: OK/Warning/Critical
- Metrics/counts
- Specific issues found (if any)
- Recommendations

### Version Report
Table format showing:
- Component Name
- Current Version
- Latest Available Version
- Status (Up-to-date/Update Available/Critical Update)
- Update Priority (High/Medium/Low)

### Action Items
Prioritized list of:
1. Critical actions (do immediately)
2. Important actions (do this week)
3. Maintenance actions (plan for next maintenance window)
4. Long-term improvements

### Trends & Observations
- Resource usage trends
- Performance observations
- Capacity planning notes

---

End of health check. Provide comprehensive output for all sections.
```

---

## Expected Output Example

The health check should produce a report similar to this structure:

```markdown
# Kubernetes Cluster Health Check Report
**Date**: 2025-11-15
**Cluster**: cberg-home-nextgen
**Nodes**: 3 (k8s-nuc14-01, k8s-nuc14-02, k8s-nuc14-03)

## Executive Summary
- **Overall Health**: ✅ Excellent
- **Critical Issues**: 0
- **Warnings**: 2
- **Outdated Components**: 5
- **Uptime**: 77 days

## Detailed Findings
[Comprehensive details for each of the 20 sections]

## Version Report
| Component | Current | Latest | Status | Priority |
|-----------|---------|--------|--------|----------|
| Kubernetes | v1.34.0 | v1.34.1 | Update Available | Medium |
| Talos | v1.11.0 | v1.11.1 | Update Available | Low |
| Longhorn | 1.9.2 | 1.9.3 | Update Available | Medium |
[etc...]

## Action Items
### Critical (Do Immediately)
- None

### Important (This Week)
1. Update Kubernetes to v1.34.1
2. Review certificate expiring in 25 days

### Maintenance (Next Window)
1. Update Longhorn to 1.9.3
2. Update Helm charts (5 updates available)

## Trends & Observations
- Memory usage stable at ~25% across nodes
- Disk usage growing ~2% per month
- No performance degradation observed
- Backup success rate: 100%
```

---

## Automation Notes

This health check can be:
1. Run manually by pasting the prompt
2. Scheduled weekly via a reminder system
3. Integrated into a monitoring dashboard
4. Extended with custom checks specific to your workloads

## Maintenance Log

Keep a log of when this check was run and major findings:

| Date | Health Status | Critical Issues | Actions Taken | Notes |
|------|---------------|-----------------|---------------|-------|
| 2025-11-15 | Excellent | 0 | Fixed pgadmin cert, cleaned orphaned volumes | All systems operational |
| | | | | |
| | | | | |

---

## Contact & Escalation

If critical issues are found:
1. Address immediately if cluster stability is at risk
2. Document the issue and resolution
3. Update monitoring/alerting to catch similar issues
4. Review root cause and implement preventive measures

---

*Last Updated: 2025-11-15*
