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

---

## Command Reference - Tested & Working

This section contains commands that have been tested and work reliably for health checks.

### 1. Cluster Events & Logs

```bash
# Get recent events (last 50)
kubectl get events -A --sort-by='.lastTimestamp' | tail -50

# Get warning events only
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -30

# Check for specific event reasons (adjust time window as needed)
kubectl get events -A --field-selector reason=OOMKilled
kubectl get events -A --field-selector reason=Evicted
```

### 2. Jobs & CronJobs

```bash
# List all jobs
kubectl get jobs -A

# List all CronJobs with schedule info
kubectl get cronjobs -A

# Check specific CronJob last run
kubectl get cronjob -n <namespace> <cronjob-name> -o jsonpath='{.status.lastScheduleTime}'

# Get recent job logs
kubectl logs -n <namespace> job/<job-name> --tail=20
```

### 3. Certificates

```bash
# List all certificates with basic info
kubectl get certificates -A

# Get detailed certificate expiration info (WORKS)
kubectl get certificates -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}: ready={.status.conditions[?(@.type=="Ready")].status}, expires={.status.renewalTime}{"\n"}{end}'

# ❌ AVOID: Complex jq with shell quoting issues
# kubectl get certificates -A -o json | jq -r '.items[] | select(.status.renewalTime != null) | "..."'
```

### 4. DaemonSets

```bash
# List all DaemonSets with replica counts
kubectl get daemonsets -A

# Check for any DaemonSets with mismatched counts
kubectl get daemonsets -A -o json | jq -r '.items[] | select(.status.desiredNumberScheduled != .status.numberReady) | "\(.metadata.namespace)/\(.metadata.name): desired=\(.status.desiredNumberScheduled) ready=\(.status.numberReady)"'
```

### 5. Helm Deployments & Flux

```bash
# List all HelmReleases
flux get helmreleases -A

# List all Flux kustomizations
flux get kustomizations -A

# Check specific HelmRelease status
flux get helmrelease <name> -n <namespace>

# Force reconciliation if needed
flux reconcile kustomization <name> -n <namespace>
flux reconcile helmrelease <name> -n <namespace>
```

### 6. Deployments & StatefulSets

```bash
# List all deployments with details
kubectl get deployments -A -o wide

# List all StatefulSets
kubectl get statefulsets -A

# Find deployments with mismatched replicas
kubectl get deployments -A -o json | jq -r '.items[] | select(.status.replicas != .status.readyReplicas) | "\(.metadata.namespace)/\(.metadata.name): replicas=\(.status.replicas) ready=\(.status.readyReplicas)"'
```

### 7. Pods Health

```bash
# Find all non-running pods
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded

# Find pods with high restart counts (>5 restarts)
kubectl get pods -A -o wide | awk 'NR==1 || $4 > 5' | head -30

# Check for specific pod states
kubectl get pods -A --field-selector=status.phase=Pending
kubectl get pods -A --field-selector=status.phase=Failed

# Find pods stuck in Terminating
kubectl get pods -A | grep Terminating
```

### 8. Prometheus & Monitoring

```bash
# List all PrometheusRules
kubectl get prometheusrules -A

# Check Prometheus logs for errors (last 24h)
kubectl logs -n monitoring prometheus-kube-prometheus-stack-0 --tail=50 --since=24h 2>&1 | grep -iE "(error|warn|fail)" | head -20

# Check if Prometheus is running
kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus
```

### 9. Alertmanager

```bash
# Check Alertmanager logs
kubectl logs -n monitoring alertmanager-kube-prometheus-stack-0 --tail=50 --since=24h 2>&1 | grep -iE "(error|warn|fail)" | head -20

# Get Alertmanager pod status
kubectl get pods -n monitoring -l app.kubernetes.io/name=alertmanager
```

### 10. Longhorn Storage

```bash
# List all Longhorn volumes with status
kubectl get volumes -n storage -o wide

# Check for unhealthy volumes
kubectl get volumes -n storage -o json | jq -r '.items[] | select(.status.state != "attached" or .status.robustness != "healthy") | "\(.metadata.name): state=\(.status.state) robustness=\(.status.robustness)"'

# Check all PVCs for issues
kubectl get pvc -A | grep -E "(Pending|Lost|Unknown)" || echo "All PVCs are Bound"

# List PVCs with their status
kubectl get pvc -A
```

### 11. Container Logs Analysis

```bash
# Check Cilium logs for errors
kubectl -n kube-system logs -l app.kubernetes.io/name=cilium --tail=100 --since=24h 2>&1 | grep -iE "(error|fatal|critical)" | head -20

# Check CoreDNS logs
kubectl -n kube-system logs -l k8s-app=kube-dns --tail=100 --since=24h 2>&1 | grep -iE "(error|fatal)" | head -20

# Check Flux controller logs
kubectl -n flux-system logs deployment/kustomize-controller --tail=50 --since=24h 2>&1 | grep -iE "(error|fail)" | head -20
```

### 12. Talos System Health

```bash
# Get Talos version (single node)
talosctl version --nodes <node-ip>

# ❌ AVOID: health command with multiple nodes (not supported)
# talosctl health --nodes 192.168.55.11,192.168.55.12,192.168.55.13

# ✅ USE: health command with single node
talosctl health --nodes <single-node-ip>

# Get machine status
talosctl get machinestatus --nodes <node-ip>

# Check services on a node
talosctl services --nodes <node-ip>

# Read dmesg for hardware errors
talosctl dmesg --nodes <node-ip> | grep -iE "(error|fail|warn)" | tail -20
```

### 13. Hardware Health

```bash
# Note: Temperature monitoring via talosctl may not work on all hardware
# This is expected and not a critical issue

# Attempt to read temperature sensors (may not return data)
talosctl read /sys/class/hwmon/hwmon*/temp*_input --nodes <node-ip>

# Check for hardware errors in dmesg
talosctl dmesg --nodes <node-ip> | grep -iE "(hardware|temperature|thermal)" | tail -20
```

### 14. Resource Utilization

```bash
# Node resource usage
kubectl top nodes

# Top CPU consuming pods
kubectl top pods -A --sort-by=cpu | head -15

# Top memory consuming pods
kubectl top pods -A --sort-by=memory | head -15

# Get node details
kubectl get nodes -o wide
```

### 15. Backup System

```bash
# List backup CronJobs
kubectl get cronjobs -n storage

# Check latest backup job
kubectl get jobs -n storage | grep backup

# Get backup job logs
kubectl logs -n storage job/<backup-job-name> --tail=20

# Check backup completion time
kubectl get job -n storage <backup-job-name> -o jsonpath='{.status.completionTime}'
```

### 16. Version Checks

```bash
# Kubernetes version (UPDATED - --short flag removed)
kubectl version -o json | jq -r '.serverVersion | "Server: \(.gitVersion)"'

# ❌ AVOID: Old kubectl version command
# kubectl version --short

# Talos version
talosctl version --nodes <node-ip>

# Get Helm chart versions from HelmReleases
kubectl get helmrelease -n <namespace> <name> -o jsonpath='{.spec.chart.spec.version}'

# Examples:
kubectl get helmrelease -n storage longhorn -o jsonpath='{.spec.chart.spec.version}'
kubectl get helmrelease -n kube-system cilium -o jsonpath='{.spec.chart.spec.version}'
kubectl get helmrelease -n monitoring kube-prometheus-stack -o jsonpath='{.spec.chart.spec.version}'
```

### 17. Security Checks

```bash
# Find pods running as root (basic check)
kubectl get pods -A -o json | jq -r '.items[] | select(.spec.securityContext.runAsUser == 0 or (.spec.containers[].securityContext.runAsUser // 0) == 0) | "\(.metadata.namespace)/\(.metadata.name)"' | head -20

# List ingresses (to check TLS configuration)
kubectl get ingress -A

# Check for LoadBalancer services
kubectl get svc -A --field-selector spec.type=LoadBalancer
```

### 18. Network Connectivity

```bash
# List all ingresses
kubectl get ingress -A

# Check ingress controllers
kubectl get svc -n network | grep ingress

# Check external-dns
kubectl get deployment -n network external-dns

# Verify DNS pods
kubectl get pods -n kube-system -l k8s-app=kube-dns
```

### 19. GitOps Status

```bash
# Check all kustomizations
flux get kustomizations -A

# Check Git source status
flux get sources git -A

# Check if Git repo is accessible
flux reconcile source git flux-system

# Check for drift
flux diff kustomization <name> -n <namespace>
```

### 20. Namespace Review

```bash
# List all namespaces
kubectl get namespaces

# Check for stuck resources in Terminating state
kubectl get namespaces | grep Terminating
kubectl get pods -A | grep Terminating

# Check resource quotas (if configured)
kubectl get resourcequotas -A
```

---

## Common Pitfalls & Solutions

### 1. JQ Complex Queries with Shell Quoting
**Problem**: Complex jq filters with shell escaping can fail
**Solution**: Use simpler jsonpath queries or test jq syntax separately first

```bash
# ❌ Can fail with quoting issues
kubectl get certificates -A -o json | jq -r '.items[] | select(.status.renewalTime != null) | "..."'

# ✅ Use jsonpath instead
kubectl get certificates -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}: expires={.status.renewalTime}{"\n"}{end}'
```

### 2. Kubectl Version Command Changed
**Problem**: `kubectl version --short` no longer works in newer versions
**Solution**: Use `-o json` with jq or `-o yaml`

```bash
# ❌ Old way (deprecated)
kubectl version --short

# ✅ New way
kubectl version -o json | jq -r '.serverVersion.gitVersion'
```

### 3. Talosctl Health with Multiple Nodes
**Problem**: `talosctl health` doesn't support multiple nodes in `--nodes` flag
**Solution**: Run health check one node at a time or omit `--nodes` to check all

```bash
# ❌ Doesn't work
talosctl health --nodes 192.168.55.11,192.168.55.12,192.168.55.13

# ✅ Works - single node
talosctl health --nodes 192.168.55.11

# ✅ Works - check all configured nodes
talosctl health
```

### 4. Temperature Sensor Access
**Problem**: Hardware temperature sensors may not be accessible via talosctl
**Solution**: This is expected on some hardware; rely on other health indicators (CPU metrics, throttling)

### 5. Field Selector Limitations
**Problem**: Not all fields support field selectors
**Solution**: Use `grep` or `jq` for complex filtering

```bash
# ✅ Works - standard field selectors
kubectl get pods -A --field-selector=status.phase=Pending

# ❌ May not work - custom field selectors
kubectl get pods -A --field-selector=status.restartCount>5

# ✅ Alternative - use awk/grep
kubectl get pods -A -o wide | awk 'NR==1 || $4 > 5'
```

---

## Tips for Efficient Health Checks

1. **Use `-A` for cluster-wide checks**: Always use `-A` (all namespaces) for comprehensive views
2. **Combine with `| grep` or `| awk`**: Pipe output to filter for specific conditions
3. **Check logs with `--since` and `--tail`**: Limit log output to recent entries only
4. **Use `|| echo "message"`**: Provide clear output when no issues found
5. **Save frequently used queries**: Create shell aliases for common health check commands
6. **Run checks in parallel**: Use background jobs for long-running commands when gathering data

Example parallel execution:
```bash
kubectl get pods -A > /tmp/pods.txt &
kubectl get deployments -A > /tmp/deployments.txt &
kubectl get statefulsets -A > /tmp/statefulsets.txt &
wait
cat /tmp/pods.txt /tmp/deployments.txt /tmp/statefulsets.txt
```

---

## Maintenance Log

Keep a log of when this check was run and major findings:

| Date | Health Status | Critical Issues | Actions Taken | Notes |
|------|---------------|-----------------|---------------|-------|
| 2025-11-27 | Excellent | 0 | Updated health check documentation with command reference | Added tested commands and common pitfalls section |
| 2025-11-15 | Excellent | 0 | Fixed pgadmin cert, cleaned orphaned volumes | All systems operational |
| | | | | |

---

## Contact & Escalation

If critical issues are found:
1. Address immediately if cluster stability is at risk
2. Document the issue and resolution
3. Update monitoring/alerting to catch similar issues
4. Review root cause and implement preventive measures

---

*Last Updated: 2025-11-27*
