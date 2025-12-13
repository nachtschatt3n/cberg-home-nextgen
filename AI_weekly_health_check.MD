# Weekly Kubernetes Cluster Health Check

## Purpose
This document contains a comprehensive health check prompt designed to be run weekly to ensure the cluster is operating optimally and all components are up-to-date.

## Frequency
**Run this check once per week** (recommended: Sunday evenings or Monday mornings)

---

## Health Check Prompt

```
Perform a comprehensive health check of my home lab Kubernetes cluster and network infrastructure. Check ALL of the following areas and provide a detailed report:

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
- Check Talos system health per node
- Review kernel logs (dmesg) for errors and hardware issues
- Check node temperatures and thermal status
- Verify Talos services are running on each node
- Check for hardware errors (ECC, PCI device issues)

## 13. Hardware Health

### Node Health Checks
- Run Talos health checks on each node individually
- Verify all nodes are responsive and healthy
- Check node uptime and system load
- Review node resource utilization trends

### Temperature Monitoring
- Check CPU and system temperatures via Talos sensors
- Report temperatures for each node
- Flag any temperatures above 80°C
- Check for thermal throttling indicators
- Note: Temperature sensors may not be available on all hardware

### Hardware Errors
- Check kernel logs (dmesg) for hardware errors
- Look for disk I/O errors or SMART warnings
- Review memory errors (ECC if applicable)
- Check PCI device errors and detection issues
- Verify all expected hardware is detected properly

### Network Health
- Check network interface errors (receive/transmit)
- Review network drop rates and collisions
- Check for network interface flapping
- Verify all expected interfaces are up and operational

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
- Verify system subsystem status (routing, WiFi, switching, VPN)
- Monitor overall network health and subsystem status

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

## 22. Home Automation Health
- Check Home Assistant system health and integrations
- Verify Zigbee2MQTT coordinator connectivity
- Monitor MQTT broker status and client connections
- Check ESPHome device connectivity and updates
- Review Node-RED flows for errors
- Verify Scrypted camera feeds and motion detection

## 23. Media Services Health
- Check Jellyfin/Plex library scans and transcoding
- Verify media file accessibility and permissions
- Monitor Tube Archivist indexing status
- Check download client (JDownloader) queue and history
- Review media storage utilization and cleanup

## 24. Database Health
- Check PostgreSQL/MariaDB connection pools and active connections
- Monitor database sizes and growth trends
- Verify backup integrity (not just existence)
- Check for long-running queries or locks
- Review database performance metrics

## 25. External Services & Connectivity
- Test Cloudflare tunnel status and connectivity
- Verify external DNS resolution for all services
- Check SSL certificate validity for external domains
- Monitor external service response times
- Test VPN connectivity (if applicable)

## 26. Security & Access Monitoring
- Review authentication logs for failed attempts
- Check for unusual network traffic patterns
- Monitor firewall rules and blocked connections
- Verify backup encryption and access controls
- Check for exposed services without authentication

## 27. Performance & Trends
- Monitor application response times
- Track resource usage patterns over time
- Check for memory leaks in long-running services
- Monitor network latency to external services
- Review error rates and retry patterns

## 28. Backup & Recovery Verification
- Test backup restoration procedures (quarterly)
- Verify backup data integrity and completeness
- Check backup storage utilization and retention
- Monitor backup transfer speeds and reliability
- Review disaster recovery documentation currency

## 29. Environmental & Power Monitoring
- Monitor server room temperature and humidity
- Check UPS status and battery health
- Monitor power consumption trends
- Verify cooling system operation
- Check for environmental alerts

## 30. Application-Specific Checks
- Custom health checks for each major application
- API endpoint testing for web services
- Database connectivity verification
- File system integrity checks
- Service dependency validation

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
For each of the 30 sections above:
- ✅ Status: OK/Warning/Critical
- Metrics/counts
- Specific issues found (if any)
- Recommendations

### Service Availability Matrix
| Service | Internal Access | External Access | Health Status | Last Checked |
|---------|----------------|-----------------|---------------|--------------|
| Authentik | ✅ | ✅ | Healthy | 2025-12-13 |
| Home Assistant | ✅ | ✅ | Healthy | 2025-12-13 |
| etc... | | | | |

### Version Report
Table format showing:
- Component Name
- Current Version
- Latest Available Version
- Status (Up-to-date/Update Available/Critical Update)
- Update Priority (High/Medium/Low)

### Performance Metrics
- Average response times for critical services
- Resource utilization trends (CPU/Memory over time)
- Network performance (latency, throughput)
- Error rates and retry patterns

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
- Service reliability metrics
- Environmental monitoring data

---

End of health check. Provide comprehensive output for all sections.
```

---

## Expected Output Example

The health check should produce a report similar to this structure:

```markdown
# Kubernetes Cluster Health Check Report
**Date**: 2025-12-13
**Cluster**: cberg-home-nextgen
**Nodes**: 3 (k8s-nuc14-01, k8s-nuc14-02, k8s-nuc14-03)

## Executive Summary
- **Overall Health**: ✅ Excellent
- **Critical Issues**: 0
- **Warnings**: 1 (security-related)
- **Outdated Components**: 0 (versions current)
- **Service Availability**: 100% (10/10 services healthy)
- **Uptime**: All systems operational

## Service Availability Matrix
| Service | Internal Access | External Access | Health Status | Response Time |
|---------|----------------|-----------------|---------------|---------------|
| Authentik | ✅ | ✅ | Healthy | 0.2s |
| Home Assistant | ✅ | ✅ | Healthy | 0.8s |
| Nextcloud | ✅ | ✅ | Healthy | 0.3s |
| Jellyfin | ✅ | ✅ | Healthy | 0.1s |
| Grafana | ✅ | ✅ | Healthy | 0.1s |
| Prometheus | ✅ | ✅ | Healthy | 0.1s |
| Longhorn UI | ✅ | ✅ | Healthy | 0.2s |
| phpMyAdmin | ✅ | ✅ | Healthy | 0.3s |
| Uptime Kuma | ✅ | ✅ | Healthy | 0.2s |
| Paperless-NGX | ✅ | ✅ | Healthy | 0.4s |

## Detailed Findings
[Comprehensive details for each of the 30 sections]

## Performance Metrics
- **Average Response Times**: 0.25s across all services
- **Resource Utilization**: CPU 3-6%, Memory 26-36%
- **Network Performance**: 48 clients, 0 packet loss
- **Database Connections**: PostgreSQL: 12 active, MariaDB: 8 active
- **Error Rate**: 0% across monitored services

## Version Report
| Component | Current | Latest | Status | Priority |
|-----------|---------|--------|--------|----------|
| Kubernetes | v1.34.0 | Current | Up-to-date | N/A |
| Talos | v1.11.0 | Current | Up-to-date | N/A |
| Longhorn | 1.10.1 | Current | Up-to-date | N/A |
| Cilium | 1.17.1 | Current | Up-to-date | N/A |
| Prometheus Stack | 68.4.4 | Current | Up-to-date | N/A |
| Home Assistant | 2025.12.1 | Current | Up-to-date | N/A |
| Authentik | 2025.10.2 | Current | Up-to-date | N/A |

## Action Items
### Critical (Do Immediately)
- None

### Important (This Week)
- Review pods running as root (documented for awareness)

### Maintenance (Next Window)
- None required

### Long-term Improvements
- Implement automated backup restoration testing
- Add environmental monitoring sensors
- Enhance security monitoring with intrusion detection

## Trends & Observations
- **Resource Usage**: Stable at optimal levels
- **Performance**: Consistent response times, no degradation
- **Backup Success**: 100% success rate (last: 2025-12-13T03:22:57Z)
- **Network**: 48 clients connected, all devices online
- **Storage**: All volumes healthy, 47 volumes backed up
- **Home Automation**: All 15 devices connected, MQTT stable
- **Media Services**: Libraries up-to-date, transcoding functional
- **Environmental**: Temperatures within normal range
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

# Get machine status for all nodes
talosctl get machinestatus

# Check services on a specific node
talosctl services --nodes <node-ip>

# Read dmesg for hardware errors (run per node)
talosctl dmesg --nodes <node-ip> | grep -iE "(error|fail|warn|hardware|temperature|thermal)" | tail -20

# Check node temperatures (may not be available on all hardware)
talosctl read /sys/class/hwmon/hwmon*/temp*_input --nodes <node-ip>

# Check for thermal throttling or temperature issues
talosctl dmesg --nodes <node-ip> | grep -iE "(thermal|throttl|temperature|hot)" | tail -10

# Get node uptime and basic system info
talosctl get machinestatus --nodes <node-ip> -o json | jq -r '.spec | "Node \(.hostname): Uptime=\(.uptime), Stage=\(.stage)"'
```

### 13. Hardware Health

```bash
# Node health checks - run individually for each node
for node in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo "=== Checking node $node ==="
  talosctl health --nodes $node
  talosctl get machinestatus --nodes $node
done

# Temperature monitoring (may not be available on all hardware)
echo "=== Temperature Sensors ==="
for node in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo "Node $node:"
  talosctl read /sys/class/hwmon/hwmon*/temp*_input --nodes $node 2>/dev/null || echo "  Temperature sensors not available"
done

# Check for thermal issues across all nodes
echo "=== Thermal Status Check ==="
for node in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo "Node $node thermal events:"
  talosctl dmesg --nodes $node | grep -iE "(thermal|throttl|temperature|hot|cpu.*temp)" | tail -5
done

# Hardware error detection
echo "=== Hardware Error Check ==="
for node in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo "Node $node hardware errors:"
  talosctl dmesg --nodes $node | grep -iE "(error|fail|hardware|memory|ecc|pci|disk|io)" | tail -5
done

# Network interface health
echo "=== Network Interface Health ==="
for node in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo "Node $node network interfaces:"
  talosctl dmesg --nodes $node | grep -iE "(eth|enp|network|link|carrier)" | tail -3
done
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
# NOTE: Use system-installed unifictl (not dev repo)
# Verify unifictl is available
which unifictl

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

**Switch Health Checks (PoE, STP, Port Errors):**
```bash
# Get all switches and check PoE status
unifictl local device list --filter "SW" -o json | python3 -c "
import sys, json
devices = json.load(sys.stdin).get('data', [])

print('Switch PoE Status:')
for switch in devices:
    name = switch.get('name', 'Unknown')
    model = switch.get('model', '')

    # Check if switch supports PoE
    port_table = switch.get('port_table', [])
    poe_ports = [p for p in port_table if p.get('poe_enable', False)]

    if poe_ports:
        # Calculate PoE usage (handle both string and numeric values)
        total_poe_power = 0
        for p in poe_ports:
            if p.get('poe_mode') == 'auto':
                poe_val = p.get('poe_power', 0)
                try:
                    total_poe_power += float(poe_val) if poe_val else 0
                except (ValueError, TypeError):
                    pass
        poe_budget = switch.get('stat', {}).get('max_power', 0)

        print(f'\\n  {name} [{model}]:')
        print(f'    PoE Budget: {poe_budget}W')
        print(f'    PoE Used: {total_poe_power:.1f}W ({total_poe_power/poe_budget*100:.0f}% of budget)' if poe_budget > 0 else '    PoE Used: {total_poe_power:.1f}W')

        # Flag high PoE usage
        if poe_budget > 0 and total_poe_power/poe_budget > 0.9:
            print(f'    ⚠️  HIGH PoE USAGE (>90%) - consider load balancing or higher budget switch')
        elif poe_budget > 0 and total_poe_power/poe_budget > 0.8:
            print(f'    ℹ️  Moderate PoE usage (>80%)')

        # Count PoE devices
        poe_active = []
        for p in poe_ports:
            if p.get('poe_mode') == 'auto':
                try:
                    poe_val = float(p.get('poe_power', 0)) if p.get('poe_power') else 0
                    if poe_val > 0:
                        poe_active.append(p)
                except (ValueError, TypeError):
                    pass
        print(f'    Active PoE Ports: {len(poe_active)}/{len(poe_ports)}')

        # Check for PoE errors
        poe_errors = [p for p in poe_ports if p.get('poe_fault', False)]
        if poe_errors:
            print(f'    ⚠️  PoE Faults on {len(poe_errors)} port(s):')
            for p in poe_errors:
                print(f'      - Port {p.get(\"port_idx\")}: {p.get(\"name\", \"unnamed\")}')
"

# Check for port errors (CRC, drops, collisions)
unifictl local device list --filter "SW" -o json | python3 -c "
import sys, json
devices = json.load(sys.stdin).get('data', [])

print('\\nSwitch Port Errors:')
for switch in devices:
    name = switch.get('name', 'Unknown')
    port_table = switch.get('port_table', [])

    # Check each port for errors
    error_ports = []
    for port in port_table:
        port_idx = port.get('port_idx', 'N/A')
        port_name = port.get('name', f'Port {port_idx}')

        # Get error counters
        rx_errors = port.get('rx_errors', 0)
        tx_errors = port.get('tx_errors', 0)
        rx_dropped = port.get('rx_dropped', 0)
        tx_dropped = port.get('tx_dropped', 0)

        total_errors = rx_errors + tx_errors + rx_dropped + tx_dropped

        if total_errors > 0:
            error_ports.append({
                'idx': port_idx,
                'name': port_name,
                'rx_errors': rx_errors,
                'tx_errors': tx_errors,
                'rx_dropped': rx_dropped,
                'tx_dropped': tx_dropped,
                'total': total_errors
            })

    if error_ports:
        print(f'\\n  {name}:')
        print(f'    ⚠️  {len(error_ports)} port(s) with errors:')
        for ep in sorted(error_ports, key=lambda x: x['total'], reverse=True)[:5]:  # Show top 5
            print(f'      Port {ep[\"idx\"]} ({ep[\"name\"]}): RX err={ep[\"rx_errors\"]}, TX err={ep[\"tx_errors\"]}, RX drop={ep[\"rx_dropped\"]}, TX drop={ep[\"tx_dropped\"]}')
    else:
        print(f'  {name}: ✅ No port errors')
"

# Check Spanning Tree Protocol (STP) status
unifictl local device list --filter "SW" -o json | python3 -c "
import sys, json
devices = json.load(sys.stdin).get('data', [])

print('\\nSpanning Tree Protocol (STP) Status:')
for switch in devices:
    name = switch.get('name', 'Unknown')
    port_table = switch.get('port_table', [])

    # Check STP states
    stp_blocking = [p for p in port_table if p.get('stp_state') == 'blocking']
    stp_forwarding = [p for p in port_table if p.get('stp_state') == 'forwarding']
    stp_disabled = [p for p in port_table if p.get('stp_state') == 'disabled']

    print(f'\\n  {name}:')
    if stp_blocking:
        print(f'    ⚠️  {len(stp_blocking)} port(s) in BLOCKING state (preventing loops):')
        for p in stp_blocking[:3]:  # Show first 3
            print(f'      - Port {p.get(\"port_idx\")}: {p.get(\"name\", \"unnamed\")}')

    print(f'    Forwarding: {len(stp_forwarding)} ports')
    print(f'    Disabled: {len(stp_disabled)} ports')
"

# Check uplink status and port speed
unifictl local device list --filter "SW" -o json | python3 -c "
import sys, json
devices = json.load(sys.stdin).get('data', [])

print('\\nSwitch Uplink Status:')
for switch in devices:
    name = switch.get('name', 'Unknown')
    port_table = switch.get('port_table', [])
    uplink = switch.get('uplink', {})

    # Find uplink port
    uplink_port = None
    for port in port_table:
        if port.get('is_uplink', False):
            uplink_port = port
            break

    if uplink_port:
        port_idx = uplink_port.get('port_idx', 'N/A')
        speed = uplink_port.get('speed', 0)
        full_duplex = uplink_port.get('full_duplex', False)

        # Convert speed to human readable
        speed_str = f'{speed}Mbps'
        if speed >= 1000:
            speed_str = f'{speed/1000:.0f}Gbps'

        duplex = 'Full-Duplex' if full_duplex else 'Half-Duplex'

        print(f'  {name}:')
        print(f'    Uplink Port: {port_idx}')
        print(f'    Speed: {speed_str} ({duplex})')

        # Flag non-optimal uplink
        if speed < 1000:
            print(f'    ⚠️  Slow uplink (<1Gbps) - check cable or port')
        elif not full_duplex:
            print(f'    ⚠️  Half-duplex detected - check cable or switch port')
        elif speed >= 10000:
            print(f'    ✅ 10GbE uplink')
    else:
        print(f'  {name}: No uplink detected')
"

# Check port utilization on switches
unifictl local device list --filter "SW" -o json | python3 -c "
import sys, json
devices = json.load(sys.stdin).get('data', [])

print('\\nSwitch Port Utilization:')
for switch in devices:
    name = switch.get('name', 'Unknown')
    port_table = switch.get('port_table', [])

    total_ports = len([p for p in port_table if p.get('port_idx', 0) > 0])  # Exclude SFP/management
    up_ports = len([p for p in port_table if p.get('up', False)])

    utilization = (up_ports / total_ports * 100) if total_ports > 0 else 0

    print(f'  {name}:')
    print(f'    Ports in use: {up_ports}/{total_ports} ({utilization:.0f}%)')

    # Flag if running out of ports
    if utilization > 90:
        print(f'    ⚠️  High port utilization (>90%) - consider expansion')
    elif utilization > 80:
        print(f'    ℹ️  Moderate port utilization (>80%)')
"
```

**WiFi Infrastructure:**
```bash
# WiFi connectivity metrics
unifictl local wifi connectivity

# WiFi management settings
unifictl local wifi management

# WiFi configuration
unifictl local wifi config

# Radio AI isolation matrix (check for interference isolation)
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

**WiFi Radio Interference & Health Checks:**
```bash
# Check WiFi satisfaction scores (indicates client experience quality)
unifictl local wifi connectivity -o json | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'satisfaction' in data:
    sat = data['satisfaction']
    score = sat.get('average', 0)
    print(f'WiFi Satisfaction Score: {score}%')
    if score < 80:
        print(f'  ⚠️  LOW SATISFACTION - investigate interference or coverage')
    elif score < 90:
        print(f'  ℹ️  Moderate satisfaction - room for improvement')
    else:
        print(f'  ✅ Excellent satisfaction')
else:
    print('Satisfaction data not available')
"

# Check channel utilization (high utilization = potential interference)
unifictl local device list --filter "AP" -o json | python3 -c "
import sys, json
devices = json.load(sys.stdin).get('data', [])
print('AP Channel Utilization:')
for ap in devices:
    name = ap.get('name', 'Unknown')
    radios = ap.get('radio_table', [])
    for radio in radios:
        band = radio.get('name', 'unknown')
        channel = radio.get('channel', 'N/A')
        utilization = radio.get('channel_utilization', 0)
        tx_power = radio.get('tx_power', 'N/A')
        # Flag high utilization
        flag = ''
        if utilization > 70:
            flag = ' ⚠️  HIGH INTERFERENCE'
        elif utilization > 50:
            flag = ' ℹ️  Moderate usage'
        print(f'  {name} [{band}]: Ch {channel}, {utilization}% utilized, {tx_power}dBm{flag}')
"

# Check for neighboring APs causing interference
unifictl local device list --filter "AP" -o json | python3 -c "
import sys, json
devices = json.load(sys.stdin).get('data', [])
print('\\nNeighboring AP Interference:')
for ap in devices:
    name = ap.get('name', 'Unknown')
    scan = ap.get('spectrum_scanning', {})
    if scan:
        for band, data in scan.items():
            neighbors = data.get('neighbor_aps', [])
            if neighbors:
                print(f'  {name} [{band}]: {len(neighbors)} neighboring APs detected')
                strong_neighbors = [n for n in neighbors if n.get('signal', -100) > -70]
                if strong_neighbors:
                    print(f'    ⚠️  {len(strong_neighbors)} strong interfering APs (signal > -70 dBm)')
"

# Check Radio AI isolation scores (detects self-interference)
unifictl local wifi radio-ai -o json | python3 -c "
import sys, json
data = json.load(sys.stdin)
if isinstance(data, dict) and 'matrix' in data:
    matrix = data['matrix']
    print('\\nRadio AI Isolation (self-interference detection):')
    issues = []
    for row in matrix:
        for col in matrix[row]:
            score = matrix[row][col].get('isolation_score', 100)
            if score < 30 and row != col:  # Low isolation between different radios
                issues.append(f\"  ⚠️  Low isolation ({score}) between {row} and {col}\")
    if issues:
        print('\\n'.join(issues))
        print('\\n  Action: Consider adjusting AP placement or channel selection')
    else:
        print('  ✅ Good isolation between all radios')
else:
    print('Radio AI data not available')
"

# Check for channel conflicts (overlapping channels)
unifictl local device list --filter "AP" -o json | python3 -c "
import sys, json
from collections import defaultdict
devices = json.load(sys.stdin).get('data', [])

# Group by band and channel
channels = defaultdict(list)
for ap in devices:
    name = ap.get('name', 'Unknown')
    radios = ap.get('radio_table', [])
    for radio in radios:
        band = radio.get('name', 'unknown')
        channel = radio.get('channel')
        if channel:
            channels[f'{band}'].append((name, channel))

print('\\nChannel Assignment Review:')
for band, aps in channels.items():
    print(f'  {band}:')
    # Count channel usage
    ch_count = defaultdict(int)
    for ap, ch in aps:
        ch_count[ch] += 1

    for ap, ch in aps:
        flag = ''
        if ch_count[ch] > 1:
            flag = f' ⚠️  {ch_count[ch]} APs on same channel (potential interference)'
        print(f'    {ap}: Ch {ch}{flag}')
"

# Check WiFi client distribution (only actual APs, exclude switches/gateways)
unifictl local device list -o json | python3 -c "
import sys, json
devices = json.load(sys.stdin).get('data', [])

# Filter to only actual access points (not switches or gateways)
aps = []
for device in devices:
    device_type = device.get('type', '')
    model = device.get('model', '')
    name = device.get('name', '')

    # Include only if type is 'uap' OR name contains 'AP'
    # Exclude switches (USW, USMINI, US###P models) and gateways (UDM)
    is_switch = device_type == 'usw' or any(x in model for x in ['USW', 'USM', 'US24', 'US48', 'US8'])
    is_gateway = device_type == 'udm' or 'UDM' in model
    is_ap = device_type == 'uap' or 'AP' in name

    if is_ap and not is_switch and not is_gateway:
        aps.append(device)

print('\\nClient Distribution per AP (Access Points only):')
total_clients = 0
ap_data = []

for ap in aps:
    name = ap.get('name', 'Unknown')
    model = ap.get('model', '')
    clients = ap.get('num_sta', 0)
    total_clients += clients

    # Identify AP capabilities by model
    # WiFi 7: U7 Pro
    is_wifi7 = 'U7PRO' in model or model == 'U7PRO'

    # WiFi 6/6E: U6 series (U6 Pro, U6+, U6 Lite, U6 LR, U6 Mesh, U6 Enterprise)
    is_wifi6 = any(x in model for x in ['UAP6', 'U6', 'UAPL6'])

    # WiFi 5 (AC): UAP-AC series (AC Pro, AC LR, AC Lite, AC HD, AC Mesh, AC IW)
    # Note: Some have confusing model codes like U7LR which is actually UAP AC LR (WiFi 5)
    is_wifi5 = any(x in model for x in ['U7LR', 'UAPHD', 'UAPPRO', 'UACLR', 'UAC']) or 'AC' in name

    # Legacy: older than WiFi 5
    is_legacy = not (is_wifi7 or is_wifi6 or is_wifi5)

    # Determine WiFi generation for display
    if is_wifi7:
        wifi_gen = 'WiFi 7'
        max_clients = 80  # WiFi 7 can handle many clients
    elif is_wifi6:
        wifi_gen = 'WiFi 6'
        max_clients = 50  # WiFi 6 decent capacity
    elif is_wifi5:
        wifi_gen = 'WiFi 5 (AC)'
        max_clients = 30  # WiFi 5 moderate capacity
    else:
        wifi_gen = 'Legacy'
        max_clients = 20  # Older APs

    flag = ''
    if clients > max_clients:
        flag = f' ⚠️  HIGH LOAD (>{max_clients} for {wifi_gen})'
    elif clients == 0:
        flag = ' ℹ️  No clients'
    elif is_wifi7 and clients > 30:
        flag = f' ✅ Good load for {wifi_gen}'
    elif clients > max_clients * 0.7:
        flag = f' ℹ️  Moderate load for {wifi_gen}'

    ap_data.append((name, model, clients, wifi_gen, max_clients))
    print(f'  {name} [{model}] ({wifi_gen}): {clients} clients{flag}')

if ap_data:
    avg = total_clients / len(ap_data) if len(ap_data) > 0 else 0
    print(f'\\n  Total wireless clients: {total_clients}')
    print(f'  Total APs: {len(ap_data)}')
    print(f'  Average: {avg:.1f} clients per AP')

    # Check for overloaded APs
    overloaded = [(n, c, g, m) for n, mo, c, g, m in ap_data if c > m]
    if overloaded:
        print(f'\\n  ⚠️  Overloaded APs: {len(overloaded)}')
        for name, count, gen, max_c in overloaded:
            print(f'    - {name} ({gen}): {count}/{max_c} clients')
    else:
        print(f'\\n  ✅ All APs within capacity')
"

# Check 2.4 GHz vs 5 GHz vs 6 GHz client distribution
unifictl local client list --wireless -o json | python3 -c "
import sys, json
clients = json.load(sys.stdin).get('data', [])
band_24 = sum(1 for c in clients if '2.4' in str(c.get('radio', '')))
band_5 = sum(1 for c in clients if '5' in str(c.get('radio', '')))
band_6 = sum(1 for c in clients if '6' in str(c.get('radio', '')))
total = len(clients)
if total > 0:
    print(f'\\nWiFi Band Distribution:')
    print(f'  2.4 GHz: {band_24} clients ({band_24/total*100:.1f}%)')
    print(f'  5 GHz:   {band_5} clients ({band_5/total*100:.1f}%)')
    print(f'  6 GHz:   {band_6} clients ({band_6/total*100:.1f}%)')
    print(f'\\n  Note: 2.4 GHz typically used for IoT devices and legacy clients')
    # Only flag if 2.4 GHz usage is extremely high (>80%)
    if band_24/total > 0.8:
        print(f'  ⚠️  Very high 2.4 GHz usage ({band_24/total*100:.0f}%) - verify IoT devices')
        print(f'      Check if modern devices are stuck on 2.4 GHz instead of 5/6 GHz')
    elif band_6 > 0:
        print(f'  ✅ WiFi 6E/7 devices utilizing 6 GHz band')
"
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
# Network events (last 100 for comprehensive analysis)
unifictl local event list --limit 100

# Format events with Python for readability
unifictl local event list --limit 100 -o json | python3 -c "
import sys, json
events = json.load(sys.stdin).get('data', [])
for e in events:
    print(f\"{e.get('datetime', 'N/A')} [{e.get('key', 'N/A')}]: {e.get('msg', 'N/A')}\")
"

# Check for WAN/Internet disconnect events
unifictl local event list --limit 200 -o json | python3 -c "
import sys, json
events = json.load(sys.stdin).get('data', [])
wan_events = [e for e in events if 'wan' in e.get('key', '').lower() or 'EVT_GW_' in e.get('key', '')]
if wan_events:
    print(f'WAN/Internet events found ({len(wan_events)}):')
    for e in wan_events[:10]:  # Show last 10
        print(f\"  {e.get('datetime', 'N/A')} [{e.get('key')}]: {e.get('msg', 'N/A')}\")
else:
    print('No WAN/Internet disconnect events')
"

# Check for client connection errors
unifictl local event list --limit 200 -o json | python3 -c "
import sys, json
events = json.load(sys.stdin).get('data', [])
# Common client error event keys
error_keys = ['EVT_LU_Disconnected', 'EVT_LU_Lost_Connection', 'EVT_WU_Disconnected',
              'EVT_LU_Roam_Err', 'EVT_WU_Roam_Err', 'authentication_failed']
client_errors = [e for e in events if any(k in e.get('key', '') for k in error_keys)]
if client_errors:
    print(f'Client connection errors ({len(client_errors)}):')
    for e in client_errors[:10]:
        print(f\"  {e.get('datetime', 'N/A')} [{e.get('key')}]: {e.get('msg', 'N/A')}\")
else:
    print('No client connection errors')
"

# Check for device/infrastructure errors
unifictl local event list --limit 200 -o json | python3 -c "
import sys, json
events = json.load(sys.stdin).get('data', [])
# Device offline, reboot, adoption issues
device_keys = ['EVT_AP_Lost_Contact', 'EVT_SW_Lost_Contact', 'EVT_AP_Rebooted',
               'EVT_SW_Rebooted', 'EVT_AP_Upgraded', 'EVT_SW_Upgraded']
device_events = [e for e in events if any(k in e.get('key', '') for k in device_keys)]
if device_events:
    print(f'Device infrastructure events ({len(device_events)}):')
    for e in device_events[:10]:
        print(f\"  {e.get('datetime', 'N/A')} [{e.get('key')}]: {e.get('msg', 'N/A')}\")
else:
    print('No device infrastructure issues')
"

# Check for security/firewall events
unifictl local event list --limit 200 -o json | python3 -c "
import sys, json
events = json.load(sys.stdin).get('data', [])
security_keys = ['EVT_IPS_Alert', 'EVT_AD_Block', 'blocked', 'threat', 'intrusion']
security_events = [e for e in events if any(k.lower() in e.get('key', '').lower() for k in security_keys)]
if security_events:
    print(f'Security/Firewall events ({len(security_events)}):')
    for e in security_events[:10]:
        print(f\"  {e.get('datetime', 'N/A')} [{e.get('key')}]: {e.get('msg', 'N/A')}\")
else:
    print('No security alerts')
"

# System logs - critical only
unifictl local log critical --limit 50

# System logs - all (for comprehensive review)
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

### 22. Home Automation Health

```bash
# Check Home Assistant health endpoint
curl -s http://home-assistant.home-automation.svc.cluster.local:8123/api/ | jq -r '.message' 2>/dev/null || echo "Home Assistant API not accessible"

# Check MQTT broker connections
kubectl exec -n home-automation deployment/mosquitto -- netstat -tlnp | grep :1883

# Check Zigbee2MQTT coordinator status
kubectl logs -n home-automation deployment/zigbee2mqtt --tail=20 | grep -i "coordinator\|connected\|error"

# Check ESPHome devices
kubectl get pods -n home-automation -l app.kubernetes.io/name=esphome -o jsonpath='{.items[*].status.phase}'

# Check Node-RED flows
kubectl logs -n home-automation deployment/node-red --tail=10 | grep -i "error\|started\|stopped"
```

### 23. Media Services Health

```bash
# Check Jellyfin health
curl -s http://jellyfin.media.svc.cluster.local:8096/health | jq . 2>/dev/null || echo "Jellyfin health check failed"

# Check Tube Archivist indexing status
kubectl logs -n download deployment/tube-archivist --tail=20 | grep -i "index\|scan\|error"

# Check JDownloader status
kubectl exec -n download deployment/jdownloader -- ls -la /opt/JDownloader/Downloads/ | wc -l

# Check media storage utilization
kubectl exec -n storage longhorn-csi-plugin-xxx -- df -h /mnt/media 2>/dev/null || echo "Media storage check requires pod access"
```

### 24. Database Health

```bash
# Check PostgreSQL connections
kubectl exec -n databases deployment/postgresql -- psql -U postgres -c "SELECT count(*) as active_connections FROM pg_stat_activity;"

# Check MariaDB status
kubectl exec -n databases deployment/mariadb -- mysql -u root -e "SHOW PROCESSLIST;" 2>/dev/null | wc -l

# Monitor database sizes
kubectl exec -n databases deployment/postgresql -- psql -U postgres -c "SELECT pg_size_pretty(pg_database_size(current_database()));"

# Check for long-running queries
kubectl exec -n databases deployment/postgresql -- psql -U postgres -c "SELECT now() - query_start as duration, query FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '1 minute' ORDER BY duration DESC LIMIT 5;"
```

### 25. External Services & Connectivity

```bash
# Test external DNS resolution
for domain in "auth.example.com" "hass.example.com" "drive.example.com"; do
  echo "Testing $domain:"
  dig +short $domain | head -1
  curl -s -I https://$domain | head -1
done

# Check Cloudflare tunnel status
kubectl get pods -n network -l app=cloudflared

# Test external service response times
curl -s -w "Time: %{time_total}s\n" -o /dev/null https://auth.example.com
curl -s -w "Time: %{time_total}s\n" -o /dev/null https://hass.example.com
```

### 26. Security & Access Monitoring

```bash
# Check recent authentication failures (if logs available)
kubectl logs -n kube-system deployment/authentik-server --tail=100 --since=24h | grep -i "failed\|invalid\|unauthorized" | wc -l

# Check for unusual network traffic (basic)
unifictl local top-client list --limit 10 -o json | jq -r '.[] | select(.rx_bytes > 1000000000) | "\(.hostname): \(.rx_bytes) bytes"' 2>/dev/null || echo "Traffic analysis requires unifictl"

# Check firewall blocks
unifictl local event list --limit 50 -o json | jq -r '.data[] | select(.key | contains("blocked")) | "\(.datetime): \(.msg)"' 2>/dev/null || echo "Firewall events require unifictl"
```

### 27. Performance & Trends

```bash
# Monitor application response times (basic)
kubectl top pods -A --sort-by=cpu | head -10

# Check for memory leaks (basic trend)
kubectl top pods -A --sort-by=memory | head -10

# Monitor network latency (if speedtest available)
kubectl run speedtest --rm -it --image=alpine --restart=Never -- apk add curl && curl -s https://speed.cloudflare.com/__down?bytes=1000000 | wc -c
```

### 28. Backup & Recovery Verification

```bash
# Check backup file integrity (basic)
kubectl logs -n storage job/backup-of-all-volumes-xxx --tail=50 | grep -i "completed\|failed\|error"

# Verify backup storage utilization
kubectl get pvc -n storage -l app.kubernetes.io/name=longhorn -o json | jq -r '.items[].status.capacity.storage'

# Check backup retention (count snapshots)
kubectl get volumes -n storage -o json | jq -r '.items[].status.backupStatus | length' 2>/dev/null || echo "Backup status check"
```

### 29. Environmental & Power Monitoring

```bash
# Check server temperatures (if sensors available)
for node in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo "Node $node temperature:"
  talosctl read /sys/class/hwmon/hwmon*/temp*_input --nodes $node 2>/dev/null || echo "  Sensors not available"
done

# Monitor system load trends
kubectl top nodes

# Check for thermal throttling
for node in 192.168.55.11 192.168.55.12 192.168.55.13; do
  talosctl dmesg --nodes $node | grep -i "throttl" | tail -3
done
```

### 30. Application-Specific Checks

```bash
# Custom health checks for critical applications
echo "=== Application Health Checks ==="

# Authentik
kubectl exec -n kube-system deployment/authentik-server -- python manage.py check --deploy

# Prometheus
curl -s http://prometheus.monitoring.svc.cluster.local:9090/-/healthy

# Grafana
curl -s http://grafana.monitoring.svc.cluster.local:3000/api/health

# Longhorn
curl -s http://longhorn-frontend.storage.svc.cluster.local:80/health

# Home Assistant (if API accessible)
curl -s -H "Authorization: Bearer YOUR_TOKEN" http://home-assistant.home-automation.svc.cluster.local:8123/api/states | jq length 2>/dev/null || echo "Home Assistant API check failed"
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

### 6. Temperature Sensor Availability
**Problem**: Hardware temperature sensors may not be accessible via Talos
**Solution**: This is expected on many systems; rely on system logs and CPU metrics instead

```bash
# ✅ Check what temperature sensors are available
talosctl read /sys/class/hwmon/hwmon*/temp*_input --nodes <node-ip> 2>/dev/null || echo "Temperature sensors not available"

# ✅ Check system logs for thermal events
talosctl dmesg --nodes <node-ip> | grep -iE "(thermal|throttl|temperature|hot)"
```

### 7. UniFi Network Health Interpretation
**Problem**: VPN subsystem may show as error even when not in use
**Solution**: Focus on critical subsystems (WAN, LAN, WLAN); VPN errors may be expected if not configured

```bash
# ✅ Check subsystem status with proper interpretation
unifictl local health get -o json | python3 -c "
import sys, json
health = json.load(sys.stdin)
subsystems = health.get('subsystems', [])
for s in subsystems:
    status = s.get('status')
    name = s.get('subsystem')
    if name == 'vpn' and status == 'error':
        print(f'{name}: {status} (may be expected if VPN not configured)')
    else:
        print(f'{name}: {status}')
"
```

---

## Tips for Efficient Health Checks

1. **Use `-A` for cluster-wide checks**: Always use `-A` (all namespaces) for comprehensive views
2. **Combine with `| grep` or `| awk`**: Pipe output to filter for specific conditions
3. **Check logs with `--since` and `--tail`**: Limit log output to recent entries only
4. **Use `|| echo "message"`**: Provide clear output when no issues found
5. **Save frequently used queries**: Create shell aliases for common health check commands
6. **Run checks in parallel**: Use background jobs for long-running commands when gathering data
7. **Test commands individually first**: Verify complex commands work before adding to health checks
8. **Document expected vs actual results**: Note when certain checks may not return data (like temperature sensors)
9. **Automate repetitive checks**: Create scripts for routine monitoring
10. **Baseline normal values**: Track what "normal" looks like for your environment
11. **Prioritize by impact**: Focus on services that affect most users first
12. **Include external monitoring**: Test services from outside your network too

## Automation Suggestions

### Weekly Health Check Script
Create a script that runs all checks and generates a report:

```bash
#!/bin/bash
# weekly-health-check.sh

REPORT_FILE="/tmp/health-check-$(date +%Y%m%d).md"
echo "# Kubernetes Cluster Health Check Report" > $REPORT_FILE
echo "**Date**: $(date)" >> $REPORT_FILE
echo "**Cluster**: cberg-home-nextgen" >> $REPORT_FILE

# Run all checks and append to report
# ... (add all health check commands)

echo "Health check completed. Report saved to $REPORT_FILE"
```

### Automated Alerting
Set up alerts for critical conditions:

```bash
# Example: Alert if any pod is not running
NON_RUNNING=$(kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded | wc -l)
if [ $NON_RUNNING -gt 0 ]; then
    echo "ALERT: $NON_RUNNING pods not in running state" | mail -s "Cluster Health Alert" admin@example.com
fi
```

### Dashboard Integration
Consider integrating with existing monitoring:

- **Grafana**: Create health check dashboard
- **Uptime Kuma**: Add external service monitoring
- **Prometheus**: Add custom health check metrics
- **Alertmanager**: Route health check alerts

### Service-Specific Monitoring
Add custom checks for your critical services:

```bash
# Home Assistant API check
HA_STATUS=$(curl -s -H "Authorization: Bearer $HA_TOKEN" http://home-assistant:8123/api/ | jq -r '.message' 2>/dev/null)
if [ "$HA_STATUS" != "API running." ]; then
    echo "Home Assistant API issue: $HA_STATUS"
fi

# Database connection check
DB_CONNECTIONS=$(kubectl exec -n databases deployment/postgresql -- psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;" -t)
if [ $DB_CONNECTIONS -gt 50 ]; then
    echo "High database connections: $DB_CONNECTIONS"
fi
```

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
| 2025-12-13 | Excellent | 0 | 1 | Major expansion: Added 9 new health check sections for comprehensive home lab monitoring | Added home automation, media services, database health, external services, security monitoring, performance trends, backup verification, environmental monitoring, and application-specific checks |
| 2025-12-13 | Excellent | 0 | 0 | Updated UniFi network section with enhanced event log checking | Added checks for WAN/Internet disconnects, client errors, device issues, and security events; clarified system unifictl usage |
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

*Last Updated: 2025-12-13 (Major expansion: Added comprehensive home lab monitoring with 30 health check sections)*
