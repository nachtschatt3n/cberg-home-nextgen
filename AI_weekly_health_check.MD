# Weekly Kubernetes Cluster Health Check

## Purpose
This document provides a systematic, AI-executable health check plan for a home lab Kubernetes cluster. The AI should execute checks in numerical order, collecting results and providing a comprehensive report.

## Automated Health Check Script

**⚡ Quick Start**: An automated health check script is available that executes all 39 sections:

```bash
# Run the automated health check
./scripts/health-check.sh

# Script generates three output files:
# - Full report: /tmp/health-check-YYYYMMDD-HHMMSS.txt
# - Summary: /tmp/health-check-summary-YYYYMMDD-HHMMSS.txt
# - Issues only: /tmp/health-check-issues-YYYYMMDD-HHMMSS.txt
```

**Features:**
- ✅ Executes all 39 health check sections automatically
- ✅ Categorizes issues by severity (Critical, Major, Minor)
- ✅ Generates comprehensive reports with recommendations
- ✅ Includes Alertmanager alerts, Elasticsearch application log analysis, and Home Assistant integration analysis
- ✅ Monitors MQTT broker connectivity and Shelly device health
- ✅ Queries Elasticsearch indices for error patterns and trends
- ✅ Queries UnPoller metrics for network hardware health
- ✅ Safe execution with error handling and progress tracking

**When to use the script:**
- Weekly health checks
- Post-deployment verification
- Troubleshooting cluster issues
- Generating health status reports

**When to use manual execution:**
- Deep-dive investigations
- Specific component analysis
- Custom checks not in the script

---

## AI Execution Plan

### Phase 1: Preparation (Run First)
1. **Domain Configuration**: Replace `secret-domain` with actual domain from SOPS files
2. **Tool Verification**: Ensure all required tools are available (kubectl, talosctl, unifictl, jq, etc.)
3. **Time Estimation**: This check takes approximately 15-30 minutes to complete

### Phase 2: Core Infrastructure Checks (Sections 1-10)
Execute in order, collecting metrics and identifying issues.

### Phase 3: Application & Service Checks (Sections 11-20)
Execute systematically, testing each service's health.

### Phase 3b: Camera & NVR Checks (Section 22b)
Verify Frigate NVR camera streaming, MQTT availability, and Home Assistant camera integration.

### Phase 4: Advanced Monitoring (Sections 21-35)
Execute remaining checks, focusing on automation, security, home automation health, and MQTT connectivity.

### Phase 5: Report Generation
Compile all findings into the standardized report format.

---

## Health Check Execution Guide

### Prerequisites
```bash
# Verify tools are available
which kubectl talosctl unifictl jq python3 curl

# Set domain variable (replace with actual domain)
DOMAIN="your-actual-domain.com"

# Verify cluster access
kubectl cluster-info
kubectl get nodes
```

### Execution Workflow
1. **Start with Section 1**, execute all commands in order
2. **Record results** for each check (✅ OK, ⚠️ Warning, ❌ Critical)
3. **Continue sequentially** through all 35 sections
4. **Collect metrics** and identify issues as you go
5. **Generate final report** using the standardized format

---

## 1. Cluster Events & Logs

**Objective**: Identify recent errors, warnings, and system issues
**Success Criteria**: No critical events in last 7 days

**Commands to Execute:**
```bash
# Check recent events (last 7 days)
kubectl get events -A --sort-by='.lastTimestamp' | tail -50

# Count warning events (filtered for actionable warnings only)
# Excludes: BackOff, Pulling, FailedScheduling, Unhealthy (benign warnings)
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | grep -v 'NAMESPACE' | grep -vE '(BackOff|Pulling|FailedScheduling|Unhealthy)' | wc -l

# Check for OOM kills
kubectl get events -A --field-selector reason=OOMKilled

# Check for pod evictions
kubectl get events -A --field-selector reason=Evicted
```

**AI Analysis**: Count events by type, identify patterns, flag any critical issues.
**Pattern Improvements**: Filters out benign warnings (BackOff, Pulling, FailedScheduling, Unhealthy) that are normal Kubernetes behavior and not actionable issues.

---

## 2. Jobs & CronJobs

**Objective**: Verify backup and maintenance job health
**Success Criteria**: All jobs completed successfully, backups recent

**Commands to Execute:**
```bash
# List all jobs with status
kubectl get jobs -A

# List all CronJobs
kubectl get cronjobs -A

# Check backup job status
kubectl get cronjobs -n storage backup-of-all-volumes

# Get last backup completion time
kubectl get jobs -n storage -l job-name=backup-of-all-volumes -o jsonpath='{.items[0].status.completionTime}' 2>/dev/null || echo "No recent backup job found"

# Check for failed jobs in last 7 days
kubectl get jobs -A --sort-by='.status.completionTime' | grep -E "(Failed|Error)" | wc -l
```

**AI Analysis**: Verify backup schedule, check completion times, identify any failures.

---

## 3. Certificates

**Objective**: Ensure SSL certificates are valid and not expiring
**Success Criteria**: All certificates valid, none expiring within 30 days

**Commands to Execute:**
```bash
# List all certificates
kubectl get certificates -A

# Check expiration dates
kubectl get certificates -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}: ready={.status.conditions[?(@.type=="Ready")].status}, expires={.status.renewalTime}{"\n"}{end}'

# Count certificates expiring soon (<30 days)
kubectl get certificates -A -o json | jq -r '.items[] | select(.status.renewalTime != null) | select((.status.renewalTime | fromdate) - now < 2592000) | .metadata.name' | wc -l
```

**AI Analysis**: Parse dates, identify expiring certificates, check readiness status.

---

## 4. DaemonSets

**Objective**: Verify system-level services are running on all nodes
**Success Criteria**: All DaemonSets have desired = current = ready counts

**Commands to Execute:**
```bash
# List all DaemonSets
kubectl get daemonsets -A

# Check for mismatched counts
kubectl get daemonsets -A -o json | jq -r '.items[] | select(.status.desiredNumberScheduled != .status.currentNumberScheduled or .status.desiredNumberScheduled != .status.numberReady) | "\(.metadata.namespace)/\(.metadata.name): desired=\(.status.desiredNumberScheduled) current=\(.status.currentNumberScheduled) ready=\(.status.numberReady)"'
```

**AI Analysis**: Compare desired vs actual counts, identify any DaemonSets with issues.

---

## 5. Helm Deployments

**Objective**: Ensure all applications are properly deployed via GitOps
**Success Criteria**: All HelmReleases reconciled, no HelmRepository failures, no stuck kustomizations

**Commands to Execute:**
```bash
# List all HelmReleases
flux get helmreleases -A

# Check for failed releases
flux get helmreleases -A | grep -E "(Failed|Error|Unknown)" | wc -l

# CRITICAL: Check HelmRepositories for failures (can block kustomizations)
flux get sources helmrepository -A

# Count failed HelmRepositories
flux get sources helmrepository -A | grep 'False' | wc -l

# Get details of failed HelmRepositories
flux get sources helmrepository -A | grep 'False' | while read line; do
  REPO_NS=$(echo "$line" | awk '{print $1}')
  REPO_NAME=$(echo "$line" | awk '{print $2}')
  echo "Failed: $REPO_NS/$REPO_NAME"
  kubectl get helmrepository "$REPO_NAME" -n "$REPO_NS" -o jsonpath='{.status.conditions[?(@.type=="Ready")].message}'
  echo ""
done

# List all Kustomizations
flux get kustomizations -A

# Check for kustomizations not reconciled
flux get kustomizations -A | grep -v "Applied revision" | grep -v "NAMESPACE" | wc -l

# Check for dependency-blocked kustomizations
flux get kustomizations -A | grep "dependency.*not ready"

# Check for kustomizations stuck in health checks
kubectl get kustomizations -A -o json | jq -r '.items[] | select(.status.conditions[]? | select(.type=="Ready" and .reason=="Progressing" and (.message | contains("health check")))) | "\(.metadata.namespace)/\(.metadata.name): \(.status.conditions[] | select(.type=="Ready") | .message)"'
```

**AI Analysis**:
- Count healthy vs failed HelmReleases
- **CRITICAL**: Identify failed HelmRepositories (404 errors, auth issues, network problems)
- Check for kustomizations blocked by dependencies
- Identify kustomizations stuck in health check timeouts (>30 minutes indicates a problem)
- Correlate failed HelmRepositories with stuck kustomizations (common root cause)

---

## 6. Deployments & StatefulSets

**Objective**: Verify application workloads are running correctly
**Success Criteria**: All deployments at desired replicas, StatefulSets healthy

**Commands to Execute:**
```bash
# Check deployments with issues
kubectl get deployments -A -o json | jq -r '.items[] | select(.status.replicas != .status.readyReplicas) | "\(.metadata.namespace)/\(.metadata.name): \(.status.readyReplicas)/\(.status.replicas)"'

# List StatefulSets
kubectl get statefulsets -A

# Check StatefulSet status
kubectl get statefulsets -A -o json | jq -r '.items[] | select(.status.replicas != .status.readyReplicas) | "\(.metadata.namespace)/\(.metadata.name): \(.status.readyReplicas)/\(.status.replicas)"'
```

**AI Analysis**: Identify deployments/StatefulSets not at desired replicas.

---

## 7. Pods Health

**Objective**: Find unhealthy pods requiring attention
**Success Criteria**: No pods in CrashLoopBackOff, minimal restarts

**Commands to Execute:**
```bash
# Find non-running pods
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded --no-headers | wc -l

# Find pods with high restart counts (>5)
kubectl get pods -A -o json | jq -r '.items[] | select(.status.containerStatuses[0].restartCount > 5) | "\(.metadata.namespace)/\(.metadata.name): \(.status.containerStatuses[0].restartCount) restarts"'

# Check for CrashLoopBackOff pods
kubectl get pods -A | grep CrashLoopBackOff | wc -l

# Check for Pending pods
kubectl get pods -A | grep Pending | wc -l
```

**AI Analysis**: Count unhealthy pods, identify patterns in failures.

---

## 8. Prometheus & Monitoring

**Objective**: Verify monitoring stack is functional
**Success Criteria**: Prometheus and Alertmanager running, no critical alerts

**Commands to Execute:**
```bash
# Check Prometheus pods
kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus

# Check Alertmanager pods
kubectl get pods -n monitoring -l app.kubernetes.io/name=alertmanager

# Check for firing alerts
kubectl get prometheusrules -A -o json | jq -r '.items[].spec.groups[].rules[] | select(.alert != null) | .alert' | sort | uniq -c | sort -nr | head -10

# Check Prometheus error logs (last 24h)
kubectl logs -n monitoring deployment/prometheus-kube-prometheus-stack-prometheus --tail=50 --since=24h 2>&1 | grep -i error | wc -l
```

**AI Analysis**: Verify monitoring components are running, check for active alerts.

---

## 9. Alertmanager

**Objective**: Ensure alert routing is working
**Success Criteria**: Alertmanager operational, no silenced critical alerts

**Commands to Execute:**
```bash
# Check Alertmanager status
kubectl get pods -n monitoring -l app.kubernetes.io/name=alertmanager

# Check for silenced alerts
kubectl get prometheusalerts -A 2>/dev/null | grep -i silenced | wc -l

# Check Alertmanager logs for errors
kubectl logs -n monitoring deployment/prometheus-kube-prometheus-stack-alertmanager --tail=50 --since=24h 2>&1 | grep -i error | wc -l
```

**AI Analysis**: Verify alert processing is working correctly.

---

## 10. Longhorn Storage

**Objective**: Verify storage system health
**Success Criteria**: All volumes healthy, no degraded storage, no recent detachment events

**Commands to Execute:**
```bash
# List all volumes with status
kubectl get volumes -n storage -o wide

# Count unhealthy volumes
kubectl get volumes -n storage -o json | jq -r '.items[] | select(.status.state != "attached" or .status.robustness != "healthy") | .metadata.name' | wc -l

# Check PVC status
kubectl get pvc -A | grep -E "(Pending|Lost|Unknown)" | wc -l

# Check Longhorn node status
kubectl get nodes -n storage

# CRITICAL: Check autoDeletePodWhenVolumeDetachedUnexpectedly setting
# This should be "false" to prevent conflicts with Flux reconciliation
kubectl get settings.longhorn.io auto-delete-pod-when-volume-detached-unexpectedly -n storage -o jsonpath='{.value}' && echo
echo "Expected: false (prevents GitOps conflicts)"

# Check for recent volume detachment events (last 24 hours)
kubectl get events -n storage --field-selector type=Warning --sort-by='.lastTimestamp' | grep -i "DetachedUnexpectedly" | tail -20

# Count recent engine failures
kubectl get events -n storage --field-selector type=Warning --sort-by='.lastTimestamp' | grep -i "engine.*dead unexpectedly" | wc -l

# Check for Flux reconciliation conflicts with Longhorn admission webhook
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | grep -i "admission webhook.*longhorn.*denied" | tail -10

# Check Longhorn manager logs for detachment warnings
kubectl logs -n storage daemonset/longhorn-manager --tail=100 --since=24h | grep -i "detach\|degrad" | wc -l

# Verify replica counts match expected (should not be 0/2)
kubectl get volumes -n storage -o json | python3 -c "
import sys, json
volumes = json.load(sys.stdin)['items']
mismatched = 0
for vol in volumes:
    name = vol['metadata']['name']
    status = vol.get('status', {})
    current = status.get('currentNumberOfReplicas', 0)
    desired = vol['spec'].get('numberOfReplicas', 0)
    if current != desired:
        print(f'{name}: {current}/{desired} replicas')
        mismatched += 1
print(f'\nTotal volumes with replica mismatch: {mismatched}')
"
```

**AI Analysis**:
- Identify any storage issues, check volume health
- **CRITICAL**: Verify `autoDeletePodWhenVolumeDetachedUnexpectedly` is `false` (issue from 2025-12-14)
- Check for mass detachment events indicating cluster-wide issues
- Monitor for Flux/Longhorn admission webhook conflicts
- Flag any replica count mismatches that could indicate underlying problems

---

## 11. Container Logs Analysis

**Objective**: Check for application errors in logs
**Success Criteria**: No critical errors in infrastructure logs

**Commands to Execute:**
```bash
# Check Cilium logs for errors (structured patterns only)
kubectl logs -n kube-system -l app.kubernetes.io/name=cilium --tail=100 --since=24h 2>&1 | grep -E 'level=(error|fatal|critical)|\[(ERROR|FATAL|CRITICAL)\]' | grep -v 'Err: 0' | wc -l

# Check CoreDNS logs (structured patterns only)
kubectl logs -n kube-system -l k8s-app=kube-dns --tail=100 --since=24h 2>&1 | grep -E 'level=(error|fatal)|\[(ERROR|FATAL)\]' | grep -v 'Err: 0' | wc -l

# Check Flux controller logs (structured patterns only)
kubectl logs -n flux-system deployment/kustomize-controller --tail=50 --since=24h 2>&1 | grep -E 'level=(error|fatal)|\[(ERROR|FATAL)\]|error:' | grep -v 'Err: 0' | wc -l

# Check cert-manager logs (structured patterns only)
kubectl logs -n cert-manager deployment/cert-manager --tail=50 --since=24h 2>&1 | grep -E 'level=error|\[ERROR\]|error:' | grep -v 'Err: 0' | wc -l
```

**AI Analysis**: Count error occurrences, identify problematic components.
**Pattern Improvements**: Uses structured log patterns (level=error, [ERROR]) to avoid false positives from status fields like "Err: 0" or "error_count: 0".

---

## 12. Talos System Health

**Objective**: Verify node OS health
**Success Criteria**: All nodes healthy, no hardware errors

**Commands to Execute:**
```bash
# Check node status
talosctl get machinestatus

# Check services on each node (run for each node)
for node in $(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}'); do
  echo "=== Node $node ==="
  talosctl services --nodes $node | grep -v "Running" | wc -l
done

# Check for hardware errors (run for each node)
for node in $(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}'); do
  echo "=== Hardware errors on $node ==="
  talosctl dmesg --nodes $node | grep -iE "(error|fail|hardware|memory|ecc|pci|disk)" | wc -l
done
```

**AI Analysis**: Check node health, identify hardware issues.

---

## 13. Hardware Health

**Objective**: Monitor system temperatures and hardware status
**Success Criteria**: Temperatures within safe ranges, no hardware errors

**Commands to Execute:**
```bash
# Check temperatures (may not be available)
for node in $(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}'); do
  echo "=== Temperature check for $node ==="
  talosctl read /sys/class/hwmon/hwmon*/temp*_input --nodes $node 2>/dev/null || echo "Temperature sensors not available"
done

# Check for thermal throttling
for node in $(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}'); do
  talosctl dmesg --nodes $node | grep -iE "(thermal|throttl|temperature|hot)" | wc -l
done

# Check network interface errors
for node in $(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}'); do
  talosctl dmesg --nodes $node | grep -iE "(eth|network|link|carrier)" | grep -i error | wc -l
done

# IMPORTANT: Distinguish between real hardware errors and benign iSCSI messages
# The following are NORMAL and should NOT be counted as hardware errors:
# - "Direct-Access IET VIRTUAL-DISK" - iSCSI virtual disk attachments (Longhorn)
# - "Attached SCSI disk" - Normal disk attachment messages
# - "bio_check_eod" - End of device checks on virtual disks
# Real hardware errors would include: "ECC", "PCI", "memory", "disk failure", etc.
```

**AI Analysis**: Monitor temperatures, check for thermal or network issues. **IMPORTANT**: Distinguish between benign iSCSI virtual disk messages (normal for Longhorn storage) and actual hardware failures. The health check may count benign messages as "errors" - investigate the actual dmesg output before taking action.

---

## 14. Resource Utilization

**Objective**: Check system resource usage
**Success Criteria**: Resources within acceptable limits (<90% utilization)

**Commands to Execute:**
```bash
# Node resource usage
kubectl top nodes

# Top 10 CPU consuming pods
kubectl top pods -A --sort-by=cpu | head -15

# Top 10 memory consuming pods
kubectl top pods -A --sort-by=memory | head -15

# Check disk usage
kubectl get nodes -o json | jq -r '.items[] | "\(.metadata.name): \(.status.capacity)"'

# Check for resource pressure
kubectl get nodes -o json | jq -r '.items[] | select(.status.conditions[] | select(.type=="DiskPressure" or .type=="MemoryPressure") | .status=="True") | .metadata.name'
```

**AI Analysis**: Identify resource bottlenecks, check for pressure conditions.

---

## 15. Backup System

**Objective**: Verify backup integrity and schedule
**Success Criteria**: Recent successful backups, proper retention

**Commands to Execute:**
```bash
# Check backup CronJob
kubectl get cronjob -n storage backup-of-all-volumes

# Get last backup job
kubectl get jobs -n storage -l job-name=backup-of-all-volumes --sort-by=.metadata.creationTimestamp | tail -1

# Check backup job logs
BACKUP_JOB=$(kubectl get jobs -n storage -l job-name=backup-of-all-volumes --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
if [ ! -z "$BACKUP_JOB" ]; then
  kubectl logs -n storage job/$BACKUP_JOB --tail=20 | grep -E "(completed|failed|error)" | tail -5
fi

# Check backup volume count
kubectl get volumes -n storage -o json | jq -r '.items[] | select(.status.backupStatus != null) | .metadata.name' | wc -l
```

**AI Analysis**: Verify backup completion, check for failures.

---

## 16. Version Checks & Updates

**Objective**: Ensure components are up-to-date
**Success Criteria**: No critical version mismatches

**Commands to Execute:**
```bash
# Kubernetes version
kubectl version -o json | jq -r '.serverVersion.gitVersion'

# Talos version
talosctl version --nodes $(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')

# Check Helm chart versions (sample)
kubectl get helmrelease -n storage longhorn -o jsonpath='{.spec.chart.spec.version}'
kubectl get helmrelease -n monitoring kube-prometheus-stack -o jsonpath='{.spec.chart.spec.version}'
kubectl get helmrelease -n kube-system cilium -o jsonpath='{.spec.chart.spec.version}'
```

**AI Analysis**: Compare versions, identify outdated components.

---

## 17. Security Checks

**Objective**: Verify security posture
**Success Criteria**: No root pods, proper RBAC

**Commands to Execute:**
```bash
# Find pods running as root
kubectl get pods -A -o json | jq -r '.items[] | select(.spec.securityContext.runAsUser == 0 or (.spec.containers[].securityContext.runAsUser // 0) == 0) | "\(.metadata.namespace)/\(.metadata.name)"' | wc -l

# Check for LoadBalancer services (potential external exposure)
kubectl get svc -A --field-selector spec.type=LoadBalancer | wc -l

# List ingresses (check TLS)
kubectl get ingress -A | wc -l
```

**AI Analysis**: Identify security issues, check for unauthorized exposures.

---

## 18. Network Infrastructure (UniFi)

**Objective**: Verify network health and configuration
**Success Criteria**: All devices online, proper VLAN configuration

**Commands to Execute:**
```bash
# Check UniFi controller connectivity
unifictl local health get

# Count online devices
unifictl local device list -o json | jq -r '.data[] | select(.state == 1) | .name' | wc -l

# Check k8s-network VLAN
unifictl local network list -o json | jq -r '.data[] | select(.vlan == 55) | .name'

# Check client count
unifictl local client list --wireless -o json | jq -r '.data | length'
unifictl local client list --wired -o json | jq -r '.data | length'
```

**AI Analysis**: Verify network health, check device connectivity.

---

## 18a. UniFi Hardware Metrics (Prometheus)

**Objective**: Verify network hardware health via UnPoller metrics
**Success Criteria**: All devices online, no high-temperature alerts

**Commands to Execute:**
```bash
# Port-forward to Prometheus
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &

# Check UnPoller scraping status
curl -s 'http://localhost:9090/api/v1/query?query=up{job="unpoller"}' | python3 -c "
import sys, json
result = json.load(sys.stdin)['data']['result']
if result and result[0]['value'][1] == '1':
    print('✅ UnPoller is scraping metrics')
else:
    print('❌ UnPoller scraping failed')
"

# Count online devices
curl -s 'http://localhost:9090/api/v1/query?query=count(unifipoller_device_uptime_seconds>0)' | python3 -c "
import sys, json
count = json.load(sys.stdin)['data']['result'][0]['value'][1]
print(f'Online devices: {count}')
"

# Check for offline devices
curl -s 'http://localhost:9090/api/v1/query?query=unifipoller_device_uptime_seconds==0' | python3 -c "
import sys, json
offline = json.load(sys.stdin)['data']['result']
if offline:
    print('⚠️ Offline devices:')
    for device in offline:
        print(f\"  - {device['metric'].get('name', 'unknown')}\")
else:
    print('✅ All devices online')
"

# Check device temperatures
curl -s 'http://localhost:9090/api/v1/query?query=unifipoller_device_system_stats_temps' | python3 -c "
import sys, json
temps = json.load(sys.stdin)['data']['result']
for temp in temps:
    device = temp['metric'].get('name', 'unknown')
    temp_c = float(temp['value'][1])
    if temp_c > 75:
        print(f'🔴 {device}: {temp_c}°C (HIGH)')
    elif temp_c > 60:
        print(f'🟡 {device}: {temp_c}°C (WARM)')
    else:
        print(f'✅ {device}: {temp_c}°C')
"

# Check total client count
curl -s 'http://localhost:9090/api/v1/query?query=sum(unifipoller_device_user_num_sta)' | python3 -c "
import sys, json
count = json.load(sys.stdin)['data']['result'][0]['value'][1]
print(f'Total connected clients: {count}')
"

# Check wireless interference
curl -s 'http://localhost:9090/api/v1/query?query=unifipoller_device_radio_channel_interference>50' | python3 -c "
import sys, json
interference = json.load(sys.stdin)['data']['result']
if interference:
    print('⚠️ High wireless interference detected:')
    for radio in interference:
        device = radio['metric'].get('name', 'unknown')
        channel = radio['metric'].get('channel', 'N/A')
        level = float(radio['value'][1])
        print(f\"  - {device} (channel {channel}): {level}%\")
else:
    print('✅ No high interference detected')
"

# Kill port-forward when done
killall kubectl
```

**AI Analysis**: Aggregate metrics, identify hardware issues, check for temperature anomalies, flag high client counts or interference.

---

## 19. Network Connectivity (Kubernetes)

**Objective**: Test internal networking
**Success Criteria**: DNS working, cross-VLAN routing functional

**Commands to Execute:**
```bash
# Check ingress controllers
kubectl get svc -n network | grep ingress

# Test DNS resolution
kubectl run test-dns --rm -it --image=busybox --restart=Never -- nslookup kubernetes.default.svc.cluster.local

# Test cross-VLAN routing
kubectl run test-network --rm -it --image=busybox --restart=Never -- ping -c 3 192.168.31.230

# Check external-dns
kubectl get deployment -n network external-dns
```

**AI Analysis**: Verify DNS and routing functionality.

---

## 20. GitOps Status

**Objective**: Ensure GitOps reconciliation is working
**Success Criteria**: All sources and kustomizations reconciled, Flux controllers healthy

**Commands to Execute:**
```bash
# Check Git sources
flux get sources git -A

# Check for failed Git sources
flux get sources git -A | grep 'False'

# Check Flux controller pods
kubectl get pods -n flux-system

# Verify all Flux controllers are running
kubectl get pods -n flux-system --field-selector=status.phase=Running

# Check kustomizations
flux get kustomizations -A

# Check for reconciliation errors
flux get kustomizations -A | grep -v "Applied revision" | grep -v "NAMESPACE"

# Identify kustomizations with dependency issues
flux get kustomizations -A | grep "dependency.*not ready"

# Check for kustomizations stuck in reconciliation
kubectl get kustomizations -A -o json | jq -r '.items[] | select(.status.conditions[]? | select(.type=="Ready" and .status!="True")) | "\(.metadata.namespace)/\(.metadata.name): \(.status.conditions[] | select(.type=="Ready") | .message)"'

# Check Flux controller logs for errors
kubectl logs -n flux-system deployment/kustomize-controller --tail=50 --since=1h | grep -i error | wc -l
kubectl logs -n flux-system deployment/source-controller --tail=50 --since=1h | grep -i error | wc -l

# Check for HelmRepository failures that may block kustomizations
flux get sources helmrepository -A | grep 'False'
```

**AI Analysis**:
- Verify all Flux controllers are running (7 expected: flux-operator, helm-controller, image-automation-controller, image-reflector-controller, kustomize-controller, notification-controller, source-controller)
- Verify GitOps health and check for sync issues
- **CRITICAL**: Identify kustomizations blocked by failed dependencies (often caused by broken HelmRepositories)
- Check for kustomizations stuck in "Reconciliation in progress" for >30 minutes
- Correlate HelmRepository failures with stuck kustomizations
- Review controller logs for systematic issues

---

## 21. Namespace Review

**Objective**: Check namespace health and resource usage
**Success Criteria**: No stuck namespaces, proper resource quotas

**Commands to Execute:**
```bash
# List all namespaces
kubectl get namespaces | wc -l

# Check for terminating namespaces
kubectl get namespaces | grep Terminating | wc -l

# Check for terminating pods
kubectl get pods -A | grep Terminating | wc -l

# Check resource quotas
kubectl get resourcequotas -A 2>/dev/null | wc -l
```

**AI Analysis**: Identify namespace issues, check for stuck resources.

---

## 22. Home Automation Health

**Objective**: Verify smart home system functionality
**Success Criteria**: All services running, Zigbee network healthy, MQTT broker operational

**Commands to Execute:**
```bash
# Check Home Assistant
kubectl get pods -n home-automation -l app.kubernetes.io/name=home-assistant

# Check Zigbee2MQTT
kubectl get pods -n home-automation -l app.kubernetes.io/name=zigbee2mqtt

# Check MQTT broker status
kubectl get pods -n home-automation -l app.kubernetes.io/name=mosquitto

# Check MQTT broker listening
kubectl exec -n home-automation deployment/mosquitto -- netstat -tlnp | grep :1883 | wc -l

# Get Zigbee device count
kubectl exec -n home-automation deployment/zigbee2mqtt -- cat /data/state.json | jq 'length' 2>/dev/null || echo "Unable to check device count"

# Check for offline Zigbee devices
kubectl exec -n home-automation deployment/zigbee2mqtt -- cat /data/state.json | jq -r 'to_entries[] | select(.value.last_seen) | select((now - (.value.last_seen | strptime("%Y-%m-%dT%H:%M:%S.%fZ") | mktime)) > 86400*5) | .key' | wc -l 2>/dev/null || echo "Unable to check offline devices"
```

**AI Analysis**: Verify home automation services, check Zigbee health, ensure MQTT broker is operational.
**Error Categorization**: Errors are now categorized by severity (CRITICAL/MAJOR/MINOR). Filters out benign errors from expected offline devices (e.g., Flic Hub) to reduce false positives. Focus on actionable errors vs. external integration issues.

---

## 22a. MQTT Connectivity & Shelly Devices

**Objective**: Monitor MQTT client connections and Shelly device health
**Success Criteria**: Mosquitto accepting connections, Shelly devices connected via MQTT

**Commands to Execute:**
```bash
# Count active MQTT clients
echo "=== MQTT Client Count ==="
kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=1000 | grep "New client connected" | awk '{print $NF}' | sort -u | wc -l

# List unique MQTT clients (last 1000 connections)
echo ""
echo "=== Recent MQTT Clients ==="
kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=1000 | grep "New client connected" | awk '{print $NF}' | sort -u | head -20

# Count Shelly devices connected to MQTT
echo ""
echo "=== Shelly MQTT Connections ==="
SHELLY_COUNT=$(kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=1000 | grep "New client connected" | grep -i shelly | awk '{print $NF}' | sort -u | wc -l)
echo "Shelly devices connected: $SHELLY_COUNT"

# Check for MQTT authentication failures (last 100 lines)
echo ""
echo "=== MQTT Authentication Issues ==="
AUTH_FAILURES=$(kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=100 | grep -E "(not authorised|authentication|Connection refused)" | wc -l)
echo "Authentication failures: $AUTH_FAILURES"

# Check MQTT connection errors
echo ""
echo "=== MQTT Connection Errors ==="
kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=100 | grep -i error | wc -l

# List Home Assistant MQTT discovery devices
echo ""
echo "=== Home Assistant MQTT Integration Status ==="
kubectl logs -n home-automation deployment/home-assistant --tail=200 | grep -i "mqtt" | grep -iE "(connected|disconnected|error)" | tail -5 || echo "No recent MQTT activity in HA logs"

# Check Mosquitto service endpoint
echo ""
echo "=== MQTT Service Status ==="
kubectl get svc -n home-automation mosquitto-internal -o wide
kubectl get endpoints -n home-automation mosquitto-internal

# Optional: Scan for Shelly devices on network (requires network tools)
echo ""
echo "=== Shelly Device Network Scan (Optional) ==="
echo "Run this manually if detailed Shelly scan is needed:"
echo "  python3 /tmp/scan-shelly-mqtt.py"
echo ""
echo "Quick network check - ping MQTT broker from IoT network:"
echo "  Test from: 192.168.33.20 (example Shelly device)"
echo "  Target: 192.168.55.15:1883 (Mosquitto LoadBalancer)"
```

**AI Analysis**:
- Verify MQTT broker is accepting connections from all expected clients
- Count Shelly device connections and compare with expected device count
- Identify any authentication failures that need credentials configured
- Check Home Assistant MQTT integration status
- Monitor for connection drops or errors
- **Expected Shelly Count**: ~34-38 devices (based on network scan)
- **Critical Issues**: >5 authentication failures, <20 Shelly devices connected
- **Warning Issues**: 20-30 Shelly devices connected, 1-5 auth failures

---

## 22b. Frigate NVR & Camera Health

**Objective**: Verify Frigate NVR is operational, all cameras are streaming, and MQTT availability is correct for Home Assistant integration
**Success Criteria**: Frigate pod running, all cameras have active FPS, MQTT availability reports "online", detection enabled where expected

**Commands to Execute:**
```bash
# Check Frigate pod status
echo "=== Frigate Pod Status ==="
kubectl get pods -n home-automation -l app.kubernetes.io/name=frigate

# Check Frigate camera FPS via API
echo ""
echo "=== Camera Streaming Status (Frigate API) ==="
kubectl port-forward -n home-automation svc/frigate 5000:5000 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

curl -s http://localhost:5000/api/stats 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    cameras = data.get('cameras', {})
    total = len(cameras)
    streaming = 0
    detecting = 0
    for cam, info in cameras.items():
        fps = info.get('camera_fps', 0)
        det_fps = info.get('detection_fps', 0)
        detect_enabled = info.get('detection_enabled', False)
        status = 'OK' if fps > 0 else 'DOWN'
        if fps > 0:
            streaming += 1
        if detect_enabled:
            detecting += 1
        print(f'  {cam}: fps={fps}, detection_fps={det_fps}, detect={\"ON\" if detect_enabled else \"OFF\"} [{status}]')
    print(f'\nSummary: {streaming}/{total} cameras streaming, {detecting}/{total} detection enabled')
except Exception as e:
    print(f'Error querying Frigate API: {e}')
"

kill $PF_PID 2>/dev/null || true
wait $PF_PID 2>/dev/null || true

# Check Frigate MQTT availability (critical for HA integration)
echo ""
echo "=== Frigate MQTT Availability ==="
FRIGATE_AVAILABLE=$(kubectl exec -n home-automation deployment/mosquitto -c app -- timeout 5 mosquitto_sub -t 'frigate/available' -C 1 2>/dev/null || echo "unknown")
echo "frigate/available: $FRIGATE_AVAILABLE"

if [ "$FRIGATE_AVAILABLE" != "online" ]; then
    echo "WARNING: Frigate reports '$FRIGATE_AVAILABLE' via MQTT"
    echo "This causes ALL cameras to show as unavailable in Home Assistant"
    echo "Fix: kubectl exec -n home-automation deployment/mosquitto -c app -- mosquitto_pub -t 'frigate/available' -m 'online' -r"
    echo "Permanent fix: kubectl rollout restart deployment/frigate -n home-automation"
fi

# Check Frigate logs for camera connection errors
echo ""
echo "=== Camera Connection Errors (last 500 log lines) ==="
kubectl logs -n home-automation -l app.kubernetes.io/name=frigate --tail=500 2>&1 | grep "crashed unexpectedly" | sed 's/.*for //' | sed 's/\..*//' | sort | uniq -c | sort -rn

# Check for RTSP connection timeouts
echo ""
echo "=== RTSP Connection Timeouts ==="
kubectl logs -n home-automation -l app.kubernetes.io/name=frigate --tail=500 2>&1 | grep "Connection to tcp://" | sed 's/.*Connection to tcp:\/\///' | sed 's/?.*//' | sort | uniq -c | sort -rn

# Check detection state per camera via MQTT
echo ""
echo "=== Camera Detection States (MQTT) ==="
for state_topic in $(kubectl exec -n home-automation deployment/mosquitto -c app -- timeout 3 mosquitto_sub -t 'frigate/+/detect/state' -C 10 -v 2>/dev/null || echo ""); do
    echo "  $state_topic"
done
```

**AI Analysis**:
- Verify Frigate pod is running and cameras are streaming (FPS > 0)
- **CRITICAL**: Check `frigate/available` MQTT topic - if "offline", ALL cameras show unavailable in HA regardless of actual streaming status
- Identify cameras with 0 FPS (RTSP connection issues, camera offline, network problems)
- Check for cameras stuck in crash loops (repeated ffmpeg crashes)
- Monitor detection state (ON/OFF) per camera
- Cross-reference camera IPs with IoT VLAN (192.168.32.0/23) for network issues

**Camera Infrastructure:**
- Cameras are on IoT VLAN (192.168.32.0/23, VLAN 30)
- Frigate connects via RTSP on port 554
- Frigate reports availability to Home Assistant via MQTT topic `frigate/available`
- Home Assistant Frigate integration marks ALL cameras unavailable when MQTT availability is "offline"

**Common Issues and Solutions:**

1. **All cameras unavailable in HA but Frigate is running**:
   - **Cause**: Stale `frigate/available` MQTT retained message set to "offline"
   - **Quick fix**: `kubectl exec -n home-automation deployment/mosquitto -c app -- mosquitto_pub -t 'frigate/available' -m 'online' -r`
   - **Permanent fix**: `kubectl rollout restart deployment/frigate -n home-automation`

2. **Individual camera down (0 FPS)**:
   - **Cause**: Camera offline, RTSP connection timeout, network issue
   - **Check**: Verify camera IP is reachable from k8s-network VLAN
   - **Check**: Camera power and network connectivity on IoT VLAN

3. **Detection disabled on all cameras**:
   - **Check**: `frigate/+/detect/state` MQTT topics
   - **Enable**: Publish `ON` to `frigate/{camera}/detect/set` or enable in Frigate UI

**Thresholds:**
- **Critical**: `frigate/available` = "offline", or Frigate pod not running
- **Major**: >1 camera with 0 FPS, or MQTT availability unknown
- **Minor**: Detection disabled on cameras, individual camera connection timeouts
- **Info**: All cameras streaming, detection states as expected

---

## 23. Media Services Health

**Objective**: Check media server functionality
**Success Criteria**: Services accessible, no critical errors

**Commands to Execute:**
```bash
# Check Jellyfin health
curl -s http://jellyfin.media.svc.cluster.local:8096/health | grep -q "Healthy" && echo "Healthy" || echo "Jellyfin health check failed"

# Check Tube Archivist
kubectl logs -n download deployment/tube-archivist --tail=10 | grep -i error | wc -l

# Check JDownloader
kubectl get pods -n download -l app.kubernetes.io/name=jdownloader

# Check Plex
kubectl get pods -n media -l app.kubernetes.io/name=plex
```

**AI Analysis**: Verify media services are operational.

---

## 24. Database Health

**Objective**: Monitor database performance and connections
**Success Criteria**: Databases accessible, reasonable connection counts

**Commands to Execute:**
```bash
# Check PostgreSQL connections
kubectl exec -n databases deployment/postgresql -- psql -U postgres -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';" 2>/dev/null || echo "PostgreSQL check failed"

# Check MariaDB
kubectl exec -n databases deployment/mariadb -- mysql -u root -e "SELECT COUNT(*) FROM information_schema.processlist;" 2>/dev/null | wc -l 2>/dev/null || echo "MariaDB check failed"

# Check database sizes
kubectl exec -n databases deployment/postgresql -- psql -U postgres -c "SELECT pg_size_pretty(pg_database_size(current_database()));" 2>/dev/null || echo "Size check failed"
```

**AI Analysis**: Monitor database health and performance.

---

## 25. External Services & Connectivity

**Objective**: Verify external access and DNS
**Success Criteria**: External services accessible, DNS resolving

**Commands to Execute:**
```bash
# Test external DNS resolution
for domain in "auth.$DOMAIN" "hass.$DOMAIN"; do
  echo "Testing $domain:"
  dig +short $domain | wc -l
done

# Check Cloudflare tunnel
kubectl get pods -n network -l app=cloudflared | wc -l

# Test external response times
curl -s -w "%{time_total}s" -o /dev/null https://auth.$DOMAIN 2>/dev/null || echo "Auth check failed"
```

**AI Analysis**: Verify external connectivity and DNS.

---

## 26. Security & Access Monitoring

**Objective**: Monitor for security events
**Success Criteria**: No suspicious activity, authentication working

**Commands to Execute:**
```bash
# Check recent auth failures
kubectl logs -n kube-system deployment/authentik-server --tail=100 --since=24h | grep -i "failed\|invalid" | wc -l 2>/dev/null || echo "Auth logs check failed"

# Check firewall blocks (if unifictl available)
unifictl local event list --limit 50 -o json | jq -r '.data[] | select(.key | contains("blocked")) | .msg' | wc -l 2>/dev/null || echo "Firewall check requires unifictl"
```

**AI Analysis**: Monitor security events and access patterns.

---

## 27. Performance & Trends

**Objective**: Track system performance over time
**Success Criteria**: Performance stable, no degradation trends

**Commands to Execute:**
```bash
# Current performance snapshot
kubectl top nodes
kubectl top pods -A | head -10

# Check for memory leaks (compare with previous runs)
kubectl top pods -A --sort-by=memory | head -5

# Network performance check
kubectl get nodes -o json | jq -r '.items[] | .status.addresses[0].address' | head -1 | xargs -I {} ping -c 3 {} | tail -1
```

**AI Analysis**: Compare with baseline performance metrics.

---

## 28. Backup & Recovery Verification

**Objective**: Ensure backup integrity
**Success Criteria**: Backups verifiable, retention policies working

**Commands to Execute:**
```bash
# Check backup job success rate
kubectl get jobs -n storage -l job-name=backup-of-all-volumes --sort-by=.metadata.creationTimestamp | tail -5 | grep "1/1" | wc -l

# Verify backup storage
kubectl get pvc -n storage -l app.kubernetes.io/name=longhorn | grep Bound | wc -l

# Check backup retention
kubectl get volumes -n storage -o json | jq -r '.items[] | select(.status.backupStatus != null) | .status.backupStatus | length' 2>/dev/null | awk '{sum+=$1} END {print sum}' 2>/dev/null || echo "Retention check failed"
```

**AI Analysis**: Verify backup completeness and retention.

---

## 29. Environmental & Power Monitoring

**Objective**: Monitor environmental conditions
**Success Criteria**: Systems within operational parameters

**Commands to Execute:**
```bash
# Check node temperatures
for node in $(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}'); do
  talosctl read /sys/class/hwmon/hwmon*/temp*_input --nodes $node 2>/dev/null | head -3 || echo "Temperature check not available for $node"
done

# Check system load
kubectl top nodes | awk 'NR>1 {print $1 ": load=" $4}'

# Check for thermal events
for node in $(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}'); do
  talosctl dmesg --nodes $node | grep -i thermal | wc -l 2>/dev/null || echo "0"
done
```

**AI Analysis**: Monitor environmental conditions.

---

## 30. Application-Specific Checks

**Objective**: Custom health checks for critical applications
**Success Criteria**: All critical applications responding

**Commands to Execute:**
```bash
# Authentik health
kubectl exec -n kube-system deployment/authentik-server -- python manage.py check --deploy 2>/dev/null | grep -i "system check identified no issues" | wc -l

# Prometheus health
curl -s http://prometheus.monitoring.svc.cluster.local:9090/-/healthy | wc -l

# Grafana health
curl -s http://grafana.monitoring.svc.cluster.local:3000/api/health | jq -r '.database' 2>/dev/null | grep -c "ok" || echo "Grafana check failed"

# Longhorn health
curl -s http://longhorn-frontend.storage.svc.cluster.local/health | wc -l

# Home Assistant API (if accessible)
curl -s -H "Authorization: Bearer YOUR_TOKEN" http://home-assistant.home-automation.svc.cluster.local:8123/api/ | jq -r '.message' 2>/dev/null | grep -c "API running" || echo "Home Assistant API check failed"
```

**AI Analysis**: Verify critical application health.

---

## 31. Home Assistant Integration Health

**Objective**: Check Home Assistant integrations and error patterns
**Success Criteria**: No critical integration failures, services operational

**Commands to Execute:**
```bash
# Check Home Assistant logs for integration errors (last 50 lines)
kubectl logs -n home-automation deployment/home-assistant --tail=50 | grep -E "(ERROR|error|failed|Failed)" | wc -l

# Check for Tesla Wall Connector timeouts
kubectl logs -n home-automation deployment/home-assistant --tail=50 | grep -i "tesla_wall_connector" | grep -i "timeout" | wc -l

# Check Amazon Alexa integration issues
kubectl logs -n home-automation deployment/home-assistant --tail=50 | grep -i "aioamazondevices" | grep -i "failed" | wc -l

# Check ResMed MyAir integration errors
kubectl logs -n home-automation deployment/home-assistant --tail=50 | grep -i "resmed" | grep -i "missing" | wc -l

# Check IKEA Dirigera hub connection issues
kubectl logs -n home-automation deployment/home-assistant --tail=50 | grep -i "dirigera" | grep -i "disconnected" | wc -l

# Check Chromecast connection errors
kubectl logs -n home-automation deployment/home-assistant --tail=50 | grep -i "chromecast" | grep -i "reset by peer" | wc -l

# List active Home Assistant integrations count
kubectl exec -n home-automation deployment/home-assistant -- curl -s http://localhost:8123/api/config | jq -r '.components | length' 2>/dev/null || echo "Cannot check integrations"
```

**AI Analysis**: Identify problematic integrations and categorize by severity. Flag integrations with persistent connectivity issues.

**Common Error Patterns and Solutions:**

1. **Uptime Kuma Connection Failures**:
   - **Error**: `Error fetching uptime_kuma data: Connection to Uptime Kuma failed`
   - **Cause**: Missing API authentication token in Home Assistant integration
   - **Solution**: Configure API token in HA Uptime Kuma integration settings

2. **Duplicate Sensor IDs**:
   - **Error**: `Platform uptime_kuma does not generate unique IDs. ID ... already exists`
   - **Cause**: Multiple monitors with same name in Uptime Kuma creating duplicate HA entities
   - **Solution**: Rename monitors in Uptime Kuma to ensure unique identifiers, or clean up duplicate entities in HA

3. **Tesla Integration Errors**:
   - **Error**: `KeyError: 'None'` in shifter state handling
   - **Cause**: Known bug in Tesla integration v2.13.0 with unknown shifter states
   - **Solution**: Wait for upstream fix or disable problematic features

4. **Amazon Alexa Failures**:
   - **Error**: Connection/authentication failures
   - **Cause**: Token expiration or Alexa service issues
   - **Solution**: Re-authenticate Alexa integration in HA

5. **Dynamic Energy Cost / Tibber Sensor Unavailable (FALSE POSITIVE)**:
   - **Error**: `State of sensor.schulstrasse_105_electricity_price is 'unavailable', skipping update` from `custom_components.dynamic_energy_cost.sensor`
   - **Cause**: During HA startup or restart, the Tibber integration takes a few minutes to initialize and authenticate via JWT. Until initialization completes, `sensor.schulstrasse_105_electricity_price` briefly shows as `unavailable`, causing the `dynamic_energy_cost` integration to log warnings.
   - **Resolution**: This is transient startup noise that auto-resolves within minutes. No action needed. Verify by checking the live sensor state after startup completes: `curl -s -H "Authorization: Bearer $TOKEN" https://hass.uhl.cool/api/states/sensor.schulstrasse_105_electricity_price | jq .state`
   - **Confirmed**: 2026-02-15 — all Tibber sensors operational (electricity price, real-time power via Tibber Pulse). Do not flag as critical.

---

## 32. Zigbee2MQTT Device Monitoring

**Objective**: Monitor Zigbee device connectivity and battery health
**Success Criteria**: All critical devices online, battery levels acceptable

**Commands to Execute:**
```bash
# Get total device count
kubectl exec -n home-automation deployment/zigbee2mqtt -- cat /data/state.json | jq 'keys | length' 2>/dev/null || echo "Cannot check device count"

# Check for devices offline >5 days
kubectl exec -n home-automation deployment/zigbee2mqtt -- cat /data/state.json | jq -r 'to_entries[] | select(.value.last_seen) | select((now - (.value.last_seen | strptime("%Y-%m-%dT%H:%M:%S.%fZ") | mktime)) > 86400*5) | "\(.key): \(.value.last_seen)"' 2>/dev/null || echo "Cannot check offline devices"

# Check battery levels <30%
kubectl exec -n home-automation deployment/zigbee2mqtt -- cat /data/state.json | jq -r 'to_entries[] | select(.value.battery and (.value.battery < 30)) | "\(.key): \(.value.battery)%"' 2>/dev/null || echo "Cannot check battery levels"

# Get device friendly names and status summary
kubectl exec -n home-automation deployment/zigbee2mqtt -- bash -c "
cat /data/configuration.yaml | grep -A 100 'devices:' | grep -E 'friendly_name|0x[0-9a-f]+' | paste - - | head -20
echo '--- Device Status Summary ---'
cat /data/state.json | jq -r 'to_entries[] | select(.value.last_seen) | select((now - (.value.last_seen | strptime(\"%Y-%m-%dT%H:%M:%S.%fZ\") | mktime)) < 86400) | \"\(.key): OK\"' | wc -l | xargs echo 'Devices seen today:'
cat /data/state.json | jq -r 'to_entries[] | select(.value.last_seen) | select((now - (.value.last_seen | strptime(\"%Y-%m-%dT%H:%M:%S.%fZ\") | mktime)) > 86400*7) | \"\(.key): OLD\"' | wc -l | xargs echo 'Devices offline >7 days:'
cat /data/state.json | jq -r 'to_entries[] | select(.value.battery and (.value.battery < 50)) | \"\(.key): \(.value.battery)%\"' | wc -l | xargs echo 'Devices with low battery (<50%):'
"

# Check Zigbee2MQTT coordinator logs for errors
kubectl logs -n home-automation deployment/zigbee2mqtt --tail=20 | grep -i error | wc -l
```

**AI Analysis**: Analyze device connectivity patterns, identify offline devices requiring attention, and flag low battery levels. Categorize issues by priority (critical sensors vs decorative devices).

---

## 33. Battery Health Monitoring

**Objective**: Unified battery status across all smart home devices and systems
**Success Criteria**: No devices with critically low batteries, battery levels monitored

**Commands to Execute:**
```bash
# Zigbee2MQTT Battery Check
echo "=== Zigbee2MQTT Battery Status ==="
kubectl exec -n home-automation deployment/zigbee2mqtt -- bash -c "
echo 'Devices with battery < 30% (CRITICAL):'
cat /data/state.json | jq -r 'to_entries[] | select(.value.battery and (.value.battery < 30)) | \"\(.key): \(.value.battery)%\"' 2>/dev/null || echo 'None'

echo ''
echo 'Devices with battery 30-50% (WARNING):'
cat /data/state.json | jq -r 'to_entries[] | select(.value.battery and (.value.battery >= 30 and .value.battery < 50)) | \"\(.key): \(.value.battery)%\"' 2>/dev/null || echo 'None'

echo ''
echo 'Devices with battery 50-70% (MONITOR):'
cat /data/state.json | jq -r 'to_entries[] | select(.value.battery and (.value.battery >= 50 and .value.battery < 70)) | \"\(.key): \(.value.battery)%\"' 2>/dev/null || echo 'None'

echo ''
echo 'Battery Summary:'
cat /data/state.json | jq -r 'to_entries[] | select(.value.battery) | .value.battery' 2>/dev/null | wc -l | xargs echo 'Total battery-powered devices:'
cat /data/state.json | jq -r 'to_entries[] | select(.value.battery) | .value.battery' 2>/dev/null | awk '{sum+=$1; count++} END {if(count>0) print \"Average battery level: \" int(sum/count) \"%\"; else print \"No battery data\"}' 2>/dev/null || echo 'No battery data'
"

# Ring Camera Battery Check
echo ""
echo "=== Ring Camera Batteries ==="
kubectl exec -n home-automation deployment/home-assistant -- bash -c "
echo 'Ring camera battery levels (if available):'
curl -s -H 'Authorization: Bearer YOUR_TOKEN' http://localhost:8123/api/states | jq -r '.[] | select(.entity_id | contains(\"ring\")) | select(.attributes.battery_level != null) | \"\(.entity_id): \(.attributes.battery_level)%\"' 2>/dev/null || echo 'No Ring battery data available - check Ring app or HA entities'
echo 'Ring doorbell/camera entities:'
curl -s -H 'Authorization: Bearer YOUR_TOKEN' http://localhost:8123/api/states | jq -r '.[] | select(.entity_id | contains(\"ring\")) | \"\(.entity_id): \(.state)\"' 2>/dev/null | head -5 || echo 'Cannot access Ring entities'
" 2>/dev/null || echo "Ring battery check unavailable"

# Home Assistant Battery Sensors Check
echo ""
echo "=== Home Assistant Battery Sensors ==="
kubectl exec -n home-automation deployment/home-assistant -- bash -c "
# Get battery sensor states (this is approximate - actual HA API would be better)
echo 'Home Assistant battery sensors (if available):'
curl -s -H 'Authorization: Bearer YOUR_TOKEN' http://localhost:8123/api/states | jq -r '.[] | select(.entity_id | contains(\"battery\")) | \"\(.entity_id): \(.state)%\"' 2>/dev/null || echo 'Cannot access Home Assistant API'
" 2>/dev/null || echo "Home Assistant battery check unavailable"

# ESPHome Devices Battery Check (if any)
echo ""
echo "=== ESPHome Device Batteries ==="
kubectl get pods -n home-automation -l app.kubernetes.io/name=esphome -o name | head -3 | while read pod; do
  echo "Checking $pod..."
  kubectl logs -n home-automation $pod --tail=10 | grep -i battery || echo "No battery info in logs"
done

# Summary Report
echo ""
echo "=== BATTERY REPLACEMENT PRIORITIES ==="
echo "🔴 CRITICAL (Replace Immediately - <30%):"
kubectl exec -n home-automation deployment/zigbee2mqtt -- cat /data/state.json | jq -r 'to_entries[] | select(.value.battery and (.value.battery < 30)) | "- \(.key): \(.value.battery)%"' 2>/dev/null || echo "None"

echo ""
echo "🟡 HIGH PRIORITY (Replace Soon - 30-50%):"
kubectl exec -n home-automation deployment/zigbee2mqtt -- cat /data/state.json | jq -r 'to_entries[] | select(.value.battery and (.value.battery >= 30 and .value.battery < 50)) | "- \(.key): \(.value.battery)%"' 2>/dev/null || echo "None"

echo ""
echo "🔵 MONITOR (Watch Closely - 50-70%):"
kubectl exec -n home-automation deployment/zigbee2mqtt -- cat /data/state.json | jq -r 'to_entries[] | select(.value.battery and (.value.battery >= 50 and .value.battery < 70)) | "- \(.key): \(.value.battery)%"' 2>/dev/null || echo "None"

echo ""
echo "📋 MAINTENANCE SCHEDULE:"
echo "- Check batteries monthly for devices 50-70%"
echo "- Replace batteries for devices 30-50% within 2 weeks"
echo "- Replace batteries immediately for devices <30%"
echo "- Keep battery stock: CR123A, CR2032, AA, AAA batteries"
```

**AI Analysis**: Aggregate battery data across all systems, prioritize replacements by battery level and device criticality, and provide maintenance recommendations.

---

## 34. Elasticsearch Application Logs Analysis

**Objective**: Query Elasticsearch for error patterns in application logs
**Success Criteria**: No recurring critical errors, error rate within acceptable thresholds

**Commands to Execute:**
```bash
# Port-forward to Elasticsearch
kubectl port-forward -n monitoring svc/elasticsearch-es-http 9200:9200 &
PF_PID=$!
sleep 3

# Get Elasticsearch password from secret
ES_PASSWORD=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' | base64 -d)

# Get today's index name
TODAY_INDEX="fluent-bit-$(date +%Y.%m.%d)"

# Query for error patterns in today's logs
curl -k -u "elastic:$ES_PASSWORD" -X GET "https://localhost:9200/${TODAY_INDEX}/_search" -H 'Content-Type: application/json' -d '{
  "size": 0,
  "query": {
    "bool": {
      "should": [
        {"match": {"log": "error"}},
        {"match": {"log": "ERROR"}},
        {"match": {"log": "fatal"}},
        {"match": {"log": "FATAL"}},
        {"match": {"log": "critical"}},
        {"match": {"log": "CRITICAL"}}
      ],
      "minimum_should_match": 1
    }
  },
  "aggs": {
    "by_namespace": {
      "terms": {
        "field": "k8s_namespace_name.keyword",
        "size": 20
      }
    },
    "by_pod": {
      "terms": {
        "field": "k8s_pod_name.keyword",
        "size": 20
      }
    },
    "by_container": {
      "terms": {
        "field": "k8s_container_name.keyword",
        "size": 20
      }
    }
  }
}' 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
total = data['hits']['total']['value']
print(f'Total errors today: {total}')
print(f'\nTop 10 namespaces with errors:')
for bucket in data['aggregations']['by_namespace']['buckets'][:10]:
    print(f'  {bucket[\"key\"]}: {bucket[\"doc_count\"]}')
print(f'\nTop 10 pods with errors:')
for bucket in data['aggregations']['by_pod']['buckets'][:10]:
    print(f'  {bucket[\"key\"]}: {bucket[\"doc_count\"]}')
print(f'\nTop 10 containers with errors:')
for bucket in data['aggregations']['by_container']['buckets'][:10]:
    print(f'  {bucket[\"key\"]}: {bucket[\"doc_count\"]}')
"

# Query for specific known error patterns
echo ""
echo "Checking for specific error patterns:"

# kube-apiserver 'empty key' errors
EMPTY_KEY_ERRORS=$(curl -k -u "elastic:$ES_PASSWORD" -X GET "https://localhost:9200/${TODAY_INDEX}/_search" -H 'Content-Type: application/json' -d '{
  "size": 0,
  "query": {
    "query_string": {
      "query": "*empty key*",
      "default_field": "log"
    }
  }
}' 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data['hits']['total']['value'])
" || echo "0")

echo "  kube-apiserver 'empty key' errors: $EMPTY_KEY_ERRORS"

# OOM errors
OOM_ERRORS=$(curl -k -u "elastic:$ES_PASSWORD" -X GET "https://localhost:9200/${TODAY_INDEX}/_search" -H 'Content-Type: application/json' -d '{
  "size": 0,
  "query": {
    "query_string": {
      "query": "*OOMKilled* OR *out of memory*",
      "default_field": "log"
    }
  }
}' 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data['hits']['total']['value'])
" || echo "0")

echo "  OOM/out of memory errors: $OOM_ERRORS"

# Network errors
NETWORK_ERRORS=$(curl -k -u "elastic:$ES_PASSWORD" -X GET "https://localhost:9200/${TODAY_INDEX}/_search" -H 'Content-Type: application/json' -d '{
  "size": 0,
  "query": {
    "query_string": {
      "query": "*connection refused* OR *timeout* OR *connection reset*",
      "default_field": "log"
    }
  }
}' 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data['hits']['total']['value'])
" || echo "0")

echo "  Network-related errors: $NETWORK_ERRORS"

# Get recent critical errors (last 10)
echo ""
echo "Recent critical errors (last 10):"
curl -k -u "elastic:$ES_PASSWORD" -X GET "https://localhost:9200/${TODAY_INDEX}/_search" -H 'Content-Type: application/json' -d '{
  "size": 10,
  "query": {
    "bool": {
      "should": [
        {"match": {"log": "CRITICAL"}},
        {"match": {"log": "FATAL"}},
        {"match": {"log": "OOMKilled"}}
      ],
      "minimum_should_match": 1
    }
  },
  "sort": [
    {
      "@timestamp": {
        "order": "desc"
      }
    }
  ],
  "_source": ["@timestamp", "log", "k8s_pod_name", "k8s_namespace_name"]
}' 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for hit in data['hits']['hits']:
    src = hit['_source']
    ts = src.get('@timestamp', 'N/A')
    pod = src.get('k8s_pod_name', 'N/A')
    ns = src.get('k8s_namespace_name', 'N/A')
    log = src.get('log', 'N/A')
    if len(log) > 100:
        log = log[:100] + '...'
    print(f'{ts} [{ns}/{pod}]: {log}')
"

# Kill port-forward
kill $PF_PID 2>/dev/null || true
wait $PF_PID 2>/dev/null || true
```

**AI Analysis**:
- Aggregate error counts by namespace, pod, and container
- Identify recurring error patterns that need attention
- Distinguish between benign errors (e.g., kube-apiserver 'empty key') and critical issues
- Flag any OOM, fatal, or critical errors for immediate investigation
- Compare error rates with baseline to identify anomalies
- **Note**: Some errors like kube-apiserver "empty key" may be normal background noise and can be tracked for trends rather than treated as critical

**Error Rate Thresholds:**
- **Normal**: <1000 errors/day (mostly benign)
- **Monitor**: 1000-5000 errors/day (review error patterns)
- **Warning**: 5000-10000 errors/day (investigate top error sources)
- **Critical**: >10000 errors/day or any FATAL/OOMKilled errors

---

## 35. Ingress Backend Health

**Objective**: Verify all ingress backends have healthy endpoints and monitor ingress controller errors
**Success Criteria**: All ingress services have available backends, ingress controller error rate is acceptable

**Commands to Execute:**
```bash
# Check for ingresses with missing backend endpoints
kubectl get ingress -A -o json | python3 -c "
import sys, json
data = json.load(sys.stdin)
for ing in data.get('items', []):
    ns = ing['metadata']['namespace']
    name = ing['metadata']['name']
    rules = ing.get('spec', {}).get('rules', [])
    for rule in rules:
        host = rule.get('host', 'unknown')
        paths = rule.get('http', {}).get('paths', [])
        for path in paths:
            backend = path.get('backend', {})
            svc_name = backend.get('service', {}).get('name')
            if svc_name:
                print(f'{ns}|{host}|{svc_name}')
" | while IFS='|' read ns host svc; do
    ENDPOINTS=$(kubectl get endpoints "$svc" -n "$ns" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null || echo "")
    if [ -z "$ENDPOINTS" ]; then
        echo "⚠️  No backends for $host (service: $ns/$svc)"
    fi
done

# Check ingress controller errors
kubectl logs -n network -l app.kubernetes.io/name=ingress-nginx --tail=200 --since=1h | grep -E '\[error\]|\[emerg\]'
```

**AI Analysis**:
- Identify any ingresses with no backend endpoints (leads to 503 errors)
- Check for high error rates in ingress controller logs
- Verify SSL/TLS certificate issues
- Flag any ingress configuration problems
- **KNOWN FALSE POSITIVE**: Authentik outpost services (e.g., `nocodb-authentik-outpost`, `frigate-authentik-outpost`, `longhorn-authentik-outpost`, etc.) are `ExternalName` type services that resolve via DNS to `ak-outpost-*` ClusterIP services in `kube-system`. ExternalName services do **not** have `Endpoints` objects, so `kubectl get endpoints` returns empty. This is expected behavior - verify the actual outpost services in `kube-system` have healthy endpoints instead. Typically ~11 Authentik outpost ExternalName services will show "no backends" and should be excluded from the missing backends count.

**Thresholds:**
- **Critical**: Any ingress with 0 backend endpoints (excluding Authentik ExternalName outpost services)
- **Warning**: >10 ingress controller errors in last hour

---

## 36. PVC Capacity Monitoring

**Objective**: Monitor PVC status and capacity allocations
**Success Criteria**: All PVCs are Bound, no Lost or Pending volumes

**Commands to Execute:**
```bash
# Check PVC status summary
echo "PVC Status:"
kubectl get pvc -A --no-headers | awk '{print $4}' | sort | uniq -c

# List PVC allocations (top 20 by size)
kubectl get pvc -A -o custom-columns='NAMESPACE:.metadata.namespace,NAME:.metadata.name,SIZE:.spec.resources.requests.storage,STATUS:.status.phase' --no-headers | sort -k3 -h -r | head -20

# Check for non-Bound PVCs
kubectl get pvc -A | grep -v Bound | grep -v NAMESPACE
```

**AI Analysis**:
- Verify all PVCs are in Bound state
- Identify any PVCs in Pending or Lost state
- Monitor storage allocation distribution
- Note: Actual disk usage requires metrics-server or Prometheus

**Thresholds:**
- **Critical**: Any PVCs in Lost state
- **Major**: Any PVCs in Pending state
- **Info**: Monitor large PVCs approaching storage limits

---

## 37. Service Endpoint Health

**Objective**: Validate all services have available endpoints
**Success Criteria**: All expected services have backend pods ready

**Commands to Execute:**
```bash
# Find services without endpoints
kubectl get endpoints -A -o json | python3 -c "
import sys, json
data = json.load(sys.stdin)
for ep in data.get('items', []):
    if not ep.get('subsets'):
        ns = ep['metadata']['namespace']
        name = ep['metadata']['name']
        print(f'{ns}/{name}')
" | grep -vE "(headless|metrics-service|controller-manager|webhook)"

# Count services by endpoint status
echo "Services without endpoints: $(kubectl get endpoints -A -o json | python3 -c "
import sys, json
data = json.load(sys.stdin)
count = 0
for ep in data.get('items', []):
    if not ep.get('subsets'):
        count += 1
print(count)
")"
```

**AI Analysis**:
- Identify services with no backend endpoints
- Filter out known services that shouldn't have endpoints (metrics services, webhooks)
- Cross-reference with pod status to determine root cause
- Flag services that should have endpoints but don't

**Thresholds:**
- **Major**: >5 unexpected services without endpoints
- **Minor**: 1-5 services without endpoints (may be expected)

---

## 38. Admission Webhook Health

**Objective**: Monitor admission webhook configuration and failure rate
**Success Criteria**: All webhooks functioning without blocking deployments

**Commands to Execute:**
```bash
# List configured webhooks
echo "Validating webhooks:"
kubectl get validatingwebhookconfigurations --no-headers | wc -l

echo "Mutating webhooks:"
kubectl get mutatingwebhookconfigurations --no-headers | wc -l

# Check for webhook failures in events
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | grep -i 'webhook' | grep -iE 'failed|error|timeout'

# Count webhook failures
WEBHOOK_FAILURES=$(kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | grep -i 'webhook' | grep -iE 'failed|error|timeout' | wc -l)
echo "Webhook failures: $WEBHOOK_FAILURES"
```

**AI Analysis**:
- Verify webhook count matches expected configuration
- Check for recent webhook failures blocking operations
- Identify webhook timeout or connection issues
- Monitor webhook certificate expiration

**Thresholds:**
- **Major**: >10 webhook failures in recent events
- **Minor**: 1-10 webhook failures
- **Info**: Monitor webhook configuration changes

---

## Report Generation Instructions

After executing all 39 sections, compile the results into the standardized format:

1. **Executive Summary**: Calculate overall health based on critical issues found
2. **Service Availability Matrix**: Fill in actual service status
3. **Detailed Findings**: Document results from each section including integration health and device status
4. **Performance Metrics**: Aggregate resource usage data
5. **Version Report**: Compile version information
6. **Action Items**: Prioritize issues found including integration fixes and device maintenance
7. **Trends & Observations**: Note patterns including integration reliability and device connectivity trends

**Final Health Score Calculation (39 sections):**
- **✅ Excellent**: 0 critical issues, ≤2 warnings, ≥98% services healthy, <10% devices offline, 0 critical batteries, <1000 log errors/day
- **🟡 Good**: 0 critical issues, 3-4 warnings, ≥95% services healthy, 10-20% devices offline, ≤1 critical battery, <5000 log errors/day
- **🟠 Warning**: 1-2 critical issues, 5-8 warnings, ≥90% services healthy, 20-30% devices offline, 2-5 critical batteries, <10000 log errors/day
- **🔴 Critical**: ≥3 critical issues, ≥9 warnings, <90% services healthy, >30% devices offline, >5 critical batteries, >10000 log errors/day or FATAL errors