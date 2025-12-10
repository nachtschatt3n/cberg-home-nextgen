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

## 18. Network Infrastructure (UniFi)

### Overall Network Health
- Run comprehensive network diagnostics with AI analysis
- Check UniFi gateway health and WAN status
- Verify system subsystem status (routing, WiFi, switching)

### Device Health & Inventory
- List all network devices (switches, APs, gateway) with status
- Check for unadopted or offline devices
- Verify device firmware versions and uptime
- Check for pending upgrades
- Monitor device-specific issues (port anomalies, spectrum scan results)

### WiFi Infrastructure
- Check all WiFi access points status and health
- Monitor AP client distribution and load balancing
- Verify WiFi connectivity metrics and satisfaction scores
- Check channel utilization and Radio AI isolation
- Review WiFi management settings

### Network Configuration & Security
- Verify VLAN connectivity (especially k8s-network VLAN 55)
- Check network/subnet configurations
- Review firewall rules for blocks or denies
- Verify firewall groups and policies
- Check security status and threat detection
- Review mDNS bridging configuration for cross-VLAN discovery

### Client Connectivity & Performance
- Monitor total client count (wired vs wireless)
- Check for blocked or problematic clients
- Identify top bandwidth consumers
- Review client connection history and events
- Check for client roaming issues

### Traffic Analysis
- Monitor overall traffic statistics
- Check DPI (Deep Packet Inspection) data for application usage
- Review traffic routing and flow rules
- Analyze bandwidth usage patterns
- Check for traffic anomalies or unexpected flows

### Network Events & Logs
- Review recent network events (last 50-100)
- Check for critical alerts and warnings
- Filter events by subsystem (WAN, LAN, WLAN)
- Identify recurring issues or patterns
- Check system logs for errors

### Uplinks & Connectivity
- Check switch uplinks and port status
- Verify WAN connectivity and uptime
- Check for interface errors or drops
- Monitor uplink utilization

## 19. Network Connectivity (Kubernetes)
- Verify DNS resolution is working
- Check ingress controller health
- Verify external-dns is updating records
- Check Cloudflare tunnel status (if applicable)
- Test internal service discovery
- Verify cross-VLAN routing from k8s to other VLANs

## 20. GitOps Status
- Check Flux reconciliation status
- Verify Git repository connectivity
- Check for any drift between Git and cluster state
- Review webhook receiver status

## 21. Namespace Review
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
For each of the 21 sections above:
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
[Comprehensive details for each of the 21 sections]

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

### 18. Network Infrastructure (UniFi)

**Prerequisites:**
```bash
# Configure unifictl once (if not already configured)
unifictl local configure \
  --url https://192.168.30.1:8443 \
  --username admin \
  --password '<PASSWORD>' \
  --site default \
  --scope local \
  --verify-tls false

# Validate configuration
unifictl validate --local-only
```

**🤖 AI-Optimized Diagnostics (Recommended):**
```bash
# Comprehensive network diagnostics with AI analysis
unifictl local diagnose network -o llm

# WiFi-specific diagnostics
unifictl local diagnose wifi -o llm

# Client overview diagnostics
unifictl local diagnose client -o llm

# Troubleshoot specific client (requires MAC address)
unifictl local diagnose client <MAC> -o llm
```

**Overall Network Health:**
```bash
# Overall network health
unifictl local health get

# WAN status and uptime
unifictl local wan get

# Security status
unifictl local security get

# Check for subsystem issues (using Python for reliable parsing)
unifictl local health get -o json | python3 -c "
import sys, json
health = json.load(sys.stdin)
if 'subsystems' in health:
    issues = [s for s in health['subsystems'] if s.get('status') != 'ok']
    if issues:
        print('Subsystem issues found:')
        for s in issues:
            print(f\"  - {s.get('subsystem', 'Unknown')}: {s.get('status', 'N/A')}\")
    else:
        print('All subsystems OK')
"
```

**Device Status & Management:**
```bash
# List all network devices with AI-optimized output
unifictl local device list -o llm

# List all devices (table view)
unifictl local device list

# Find offline devices
unifictl local device list -o json | python3 -c "
import sys, json
devices = json.load(sys.stdin).get('data', [])
offline = [d for d in devices if d.get('state') != 1]
if offline:
    print(f'Offline devices ({len(offline)}):')
    for d in offline:
        print(f\"  - {d.get('name', 'Unknown')} ({d.get('model', 'N/A')}): {d.get('state_txt', 'Unknown state')}\")
else:
    print('All devices online')
"

# Check unadopted devices
unifictl local device list --unadopted

# Adopt all unadopted devices (if any found)
unifictl local device adopt-all

# Filter by device type
unifictl local device list --filter "SW"     # Switches
unifictl local device list --filter "AP"     # Access Points
unifictl local device list --filter-regex "^U(AP|SW)" # Regex filter

# Get specific device details with correlation
unifictl local correlate device <MAC> --include-clients -o llm

# Check for port anomalies
unifictl local device port-anomalies
```

**WiFi Infrastructure:**
```bash
# WiFi connectivity metrics
unifictl local wifi connectivity

# WiFi management settings
unifictl local wifi management

# WiFi configuration
unifictl local wifi config

# Radio AI isolation matrix
unifictl local wifi radio-ai

# WiFi stats (last 24 hours) - requires timestamp in milliseconds
START=$(python3 -c "import time; print(int((time.time() - 86400) * 1000))")
END=$(python3 -c "import time; print(int(time.time() * 1000))")
unifictl local wifi stats --start $START --end $END

# WiFi stats for specific AP
unifictl local wifi stats --start $START --end $END --ap-mac <MAC>

# Radio-level statistics
unifictl local wifi stats --radios --start $START --end $END
```

**Client Connectivity & Performance:**
```bash
# List all connected clients with AI optimization
unifictl local client list -o llm

# Wired vs wireless breakdown
unifictl local client list --wired -o json | python3 -c "import sys, json; print(f\"Wired: {len(json.load(sys.stdin).get('data', []))}\")"
unifictl local client list --wireless -o json | python3 -c "import sys, json; print(f\"Wireless: {len(json.load(sys.stdin).get('data', []))}\")"

# Check for blocked clients
unifictl local client list --blocked

# Active clients (v2 API)
unifictl local client active

# Client connection history
unifictl local client history --limit 50

# Top bandwidth consumers
unifictl local top-client list --limit 20 -o llm

# Top devices by traffic
unifictl local top-device list --limit 10

# Troubleshoot specific client with correlation
unifictl local correlate client <MAC> --include-events -o llm
```

**Network Configuration:**
```bash
# List VLANs/networks (verify k8s-network VLAN 55)
unifictl local network list

# Check k8s-network specifically (VLAN 55)
unifictl local network list -o json | python3 -c "
import sys, json
networks = json.load(sys.stdin).get('data', [])
k8s_net = next((n for n in networks if n.get('vlan') == 55), None)
if k8s_net:
    print(f\"k8s-network (VLAN 55): {k8s_net.get('name', 'N/A')}\")
    print(f\"  Subnet: {k8s_net.get('ip_subnet', 'N/A')}\")
    print(f\"  DHCP: {k8s_net.get('dhcp_enabled', False)}\")
else:
    print('k8s-network (VLAN 55) not found!')
"

# List WiFi networks (SSIDs)
unifictl local wlan list

# Check firewall rules
unifictl local firewall-rule list

# Check for deny/drop rules
unifictl local firewall-rule list -o json | python3 -c "
import sys, json
rules = json.load(sys.stdin).get('data', [])
deny_rules = [r for r in rules if r.get('action') in ['drop', 'reject']]
if deny_rules:
    print(f'Deny/Drop rules ({len(deny_rules)}):')
    for r in deny_rules:
        print(f\"  - {r.get('name', 'Unnamed')}: action={r.get('action')}, enabled={r.get('enabled')}\")
else:
    print('No deny/drop rules configured')
"

# List firewall groups
unifictl local firewall-group list

# List port profiles
unifictl local port-profile list
```

**Traffic Analysis:**
```bash
# DPI summary (Deep Packet Inspection)
unifictl local dpi get

# Traffic statistics (last 24 hours)
START=$(python3 -c "import time; print(int((time.time() - 86400) * 1000))")
END=$(python3 -c "import time; print(int(time.time() * 1000))")
unifictl local traffic stats --start $START --end $END --include-unidentified true

# Traffic flow latest (daily top 30)
unifictl local traffic flow-latest --period day --top 30

# Application traffic rate
unifictl local traffic app-rate --start $START --end $END --include-unidentified true

# Traffic routing rules
unifictl local traffic routes

# Traffic filter metadata
unifictl local traffic filter-data
```

**Network Events & Logs:**
```bash
# Network events (last 50)
unifictl local event list --limit 50

# Format events with Python
unifictl local event list --limit 50 -o json | python3 -c "
import sys, json
events = json.load(sys.stdin).get('data', [])
for e in events:
    print(f\"{e.get('datetime', 'N/A')} [{e.get('key', 'N/A')}]: {e.get('msg', 'N/A')}\")
"

# System logs - critical
unifictl local log critical --limit 50

# System logs - all
unifictl local log all --limit 100

# Device alert logs
unifictl local log device-alert --limit 20

# Time-series event export (last 100 events as CSV)
unifictl local time-series events --limit 100 --format csv > /tmp/network-events.csv
```

**Time-Series Data Export (for trending):**
```bash
# Calculate timestamps (last 7 days)
START=$(python3 -c "import time; print(int((time.time() - 604800) * 1000))")
END=$(python3 -c "import time; print(int(time.time() * 1000))")

# Export traffic time-series (CSV for analysis)
unifictl local time-series traffic --start $START --end $END --format csv > /tmp/traffic-7days.csv

# Export WiFi time-series (all APs)
unifictl local time-series wifi --start $START --end $END --format csv > /tmp/wifi-7days.csv

# Export WiFi time-series (specific AP)
unifictl local time-series wifi --start $START --end $END --ap-mac <MAC> --format csv > /tmp/wifi-ap-7days.csv

# Export events for analysis
unifictl local time-series events --limit 200 --format json -o llm > /tmp/network-events-analysis.json
```

**Export for Reporting:**
```bash
# Export device inventory
unifictl local device list -o csv > /tmp/unifi-devices.csv

# Export switches only
unifictl local device list --filter-regex "^SW" -o csv > /tmp/unifi-switches.csv

# Export APs only
unifictl local device list --filter-regex "^U(AP|6|7)" -o csv > /tmp/unifi-aps.csv

# Export client list
unifictl local client list -o csv > /tmp/unifi-clients.csv

# Export wired clients only
unifictl local client list --wired -o csv > /tmp/unifi-wired-clients.csv

# Export wireless clients only
unifictl local client list --wireless -o csv > /tmp/unifi-wireless-clients.csv

# Export network configuration
unifictl local network list -o csv > /tmp/unifi-networks.csv

# Export WLAN configuration
unifictl local wlan list -o csv > /tmp/unifi-wlans.csv

# Export firewall rules
unifictl local firewall-rule list -o csv > /tmp/unifi-firewall-rules.csv

# Export top clients
unifictl local top-client list --limit 50 -o csv > /tmp/unifi-top-clients.csv
```

**Troubleshooting Workflows:**
```bash
# Workflow 1: Diagnose client connectivity issue
CLIENT_MAC="<client-mac>"
unifictl local correlate client $CLIENT_MAC --include-events -o llm

# Workflow 2: Check AP health and connected clients
AP_MAC="<ap-mac>"
unifictl local correlate ap $AP_MAC -o llm

# Workflow 3: Network capacity planning
unifictl local device list -o llm
unifictl local client list -o llm
unifictl local top-client list --limit 20 -o llm
unifictl local top-device list --limit 20 -o llm

# Workflow 4: Security monitoring
unifictl local security get -o llm
unifictl local event list --limit 100 -o llm
unifictl local firewall-rule list -o llm
```

### 19. Network Connectivity (Kubernetes)

```bash
# List all ingresses
kubectl get ingress -A

# Check ingress controllers
kubectl get svc -n network | grep ingress

# Check external-dns
kubectl get deployment -n network external-dns

# Verify DNS pods
kubectl get pods -n kube-system -l k8s-app=kube-dns

# Test cross-VLAN routing from k8s to NAS
kubectl run test-network --rm -it --image=busybox --restart=Never -- ping -c 3 192.168.31.230

# Test DNS resolution from pod
kubectl run test-dns --rm -it --image=busybox --restart=Never -- nslookup google.com
```

### 20. GitOps Status

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

### 21. Namespace Review

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
