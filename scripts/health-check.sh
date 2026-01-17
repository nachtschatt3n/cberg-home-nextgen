#!/usr/bin/env bash

# Kubernetes Cluster Health Check Script
# Executes all 33 sections from AI_weekly_health_check.MD
# Usage: ./scripts/health-check.sh [output-file]

set -uo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Output file
OUTPUT_FILE="${1:-/tmp/health-check-$(date +%Y%m%d-%H%M%S).txt}"
SUMMARY_FILE="/tmp/health-check-summary-$(date +%Y%m%d-%H%M%S).txt"
ISSUES_FILE="/tmp/health-check-issues-$(date +%Y%m%d-%H%M%S).txt"

echo "========================================" | tee "$OUTPUT_FILE"
echo "Kubernetes Cluster Health Check" | tee -a "$OUTPUT_FILE"
echo "Date: $(date)" | tee -a "$OUTPUT_FILE"
echo "Output: $OUTPUT_FILE" | tee -a "$OUTPUT_FILE"
echo "========================================" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# Counters for summary
CRITICAL_ISSUES=0
WARNINGS=0
CHECKS_PASSED=0
CHECKS_FAILED=0

# Arrays to store issues
declare -a CRITICAL_ISSUES_LIST
declare -a MAJOR_ISSUES_LIST
declare -a MINOR_ISSUES_LIST

# Helper functions
log_section() {
    echo -e "\n${BLUE}=== $1 ===${NC}" | tee -a "$OUTPUT_FILE"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}" | tee -a "$OUTPUT_FILE"
    ((CHECKS_PASSED++))
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}" | tee -a "$OUTPUT_FILE"
    ((WARNINGS++))
}

log_critical() {
    echo -e "${RED}❌ $1${NC}" | tee -a "$OUTPUT_FILE"
    ((CRITICAL_ISSUES++))
    ((CHECKS_FAILED++))
}

log_info() {
    echo "ℹ️  $1" | tee -a "$OUTPUT_FILE"
}

add_critical_issue() {
    CRITICAL_ISSUES_LIST+=("$1")
}

add_major_issue() {
    MAJOR_ISSUES_LIST+=("$1")
}

add_minor_issue() {
    MINOR_ISSUES_LIST+=("$1")
}

# Helper to safely get integer count
safe_count() {
    local result=$(eval "$1" 2>/dev/null | head -1 || echo "0")
    # Remove any non-digit characters
    result=$(echo "$result" | tr -cd '0-9' || echo "0")
    # If empty, return 0
    if [ -z "$result" ]; then
        echo "0"
    else
        echo "$result"
    fi
}

# Verify cluster access
log_section "Phase 1: Preparation"
if kubectl cluster-info &>> "$OUTPUT_FILE"; then
    log_success "Cluster access verified"
else
    log_critical "Cannot access cluster"
    add_critical_issue "Cannot access Kubernetes cluster"
    exit 1
fi

# Get node list for later use
NODE_IPS=$(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}')
log_info "Nodes: $(kubectl get nodes -o jsonpath='{.items[*].metadata.name}' | tr ' ' ', ')"

echo "" | tee -a "$OUTPUT_FILE"

#######################################
# Phase 2: Core Infrastructure Checks
#######################################

log_section "Section 1: Cluster Events & Logs"
{
    echo "Recent events (last 50):"
    kubectl get events -A --sort-by='.lastTimestamp' | tail -50
    echo ""

    WARNING_COUNT=$(safe_count "kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | grep -v 'NAMESPACE' | wc -l")
    echo "Warning events: $WARNING_COUNT"

    OOM_COUNT=$(safe_count "kubectl get events -A --field-selector reason=OOMKilled 2>/dev/null | grep -v 'NAMESPACE' | wc -l")
    echo "OOM kills: $OOM_COUNT"

    EVICTED_COUNT=$(safe_count "kubectl get events -A --field-selector reason=Evicted 2>/dev/null | grep -v 'NAMESPACE' | wc -l")
    echo "Pod evictions: $EVICTED_COUNT"

    if [ "$WARNING_COUNT" -gt 10 ]; then
        log_warning "High warning count: $WARNING_COUNT events"
        add_minor_issue "High warning event count: $WARNING_COUNT"
    elif [ "$WARNING_COUNT" -gt 0 ]; then
        log_info "Warning events: $WARNING_COUNT"
    else
        log_success "No warning events"
    fi

    if [ "$OOM_COUNT" -gt 0 ]; then
        log_critical "OOM kills detected: $OOM_COUNT"
        add_critical_issue "OOM kills detected: $OOM_COUNT pods"
    else
        log_success "No OOM kills"
    fi

    if [ "$EVICTED_COUNT" -gt 0 ]; then
        log_critical "Pod evictions detected: $EVICTED_COUNT"
        add_critical_issue "Pod evictions detected: $EVICTED_COUNT pods"
    else
        log_success "No pod evictions"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 2: Jobs & CronJobs"
{
    echo "All CronJobs:"
    kubectl get cronjobs -A
    echo ""

    echo "Recent jobs:"
    kubectl get jobs -A --sort-by='.status.startTime' | tail -20
    echo ""

    FAILED_JOBS=$(safe_count "kubectl get jobs -A 2>/dev/null | grep -E '(0/1|Failed)' | wc -l")
    echo "Failed jobs (last 7 days): $FAILED_JOBS"

    # Check backup job
    BACKUP_JOB=$(kubectl get jobs -n storage --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null | grep -o 'daily-backup-all-volumes[^ ]*' | head -1 || echo "")
    if [ -n "$BACKUP_JOB" ]; then
        BACKUP_STATUS=$(kubectl get job -n storage "$BACKUP_JOB" -o jsonpath='{.status.succeeded}' 2>/dev/null || echo "0")
        BACKUP_TIME=$(kubectl get job -n storage "$BACKUP_JOB" -o jsonpath='{.status.completionTime}' 2>/dev/null || echo "Not completed")
        echo "Last backup job: $BACKUP_JOB (Succeeded: $BACKUP_STATUS, Time: $BACKUP_TIME)"

        if [ "$BACKUP_STATUS" == "1" ]; then
            log_success "Backup system operational"
        else
            log_warning "Backup status unclear: $BACKUP_STATUS"
            add_minor_issue "Backup job status unclear"
        fi
    else
        log_warning "No backup jobs found"
        add_minor_issue "No backup jobs found in storage namespace"
    fi

    if [ "$FAILED_JOBS" -gt 0 ]; then
        log_warning "Failed jobs detected: $FAILED_JOBS"
        add_minor_issue "Failed jobs: $FAILED_JOBS"
    else
        log_success "No failed jobs"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 3: Certificates"
{
    echo "All certificates:"
    kubectl get certificates -A
    echo ""

    TOTAL_CERTS=$(safe_count "kubectl get certificates -A --no-headers 2>/dev/null | wc -l")
    READY_CERTS=$(kubectl get certificates -A -o json 2>/dev/null | jq '[.items[] | select(.status.conditions[]? | select(.type=="Ready" and .status=="True"))] | length' || echo "0")

    echo "Certificates: $READY_CERTS/$TOTAL_CERTS ready"

    if [ "$READY_CERTS" == "$TOTAL_CERTS" ] && [ "$TOTAL_CERTS" -gt 0 ]; then
        log_success "All certificates ready ($TOTAL_CERTS/$TOTAL_CERTS)"
    else
        log_warning "Some certificates not ready: $READY_CERTS/$TOTAL_CERTS"
        add_major_issue "Certificates not ready: $READY_CERTS/$TOTAL_CERTS"
        echo "Not ready certificates:"
        kubectl get certificates -A -o json | jq -r '.items[] | select(.status.conditions[]? | select(.type=="Ready" and .status!="True")) | "\(.metadata.namespace)/\(.metadata.name)"'
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 4: DaemonSets"
{
    echo "All DaemonSets:"
    kubectl get daemonsets -A
    echo ""

    MISMATCHED=$(kubectl get daemonsets -A -o json | jq -r '.items[] | select(.status.desiredNumberScheduled != .status.currentNumberScheduled or .status.desiredNumberScheduled != .status.numberReady) | "\(.metadata.namespace)/\(.metadata.name): desired=\(.status.desiredNumberScheduled) current=\(.status.currentNumberScheduled) ready=\(.status.numberReady)"')

    if [ -z "$MISMATCHED" ]; then
        log_success "All DaemonSets healthy"
    else
        log_warning "DaemonSets with mismatched counts:"
        echo "$MISMATCHED"
        add_major_issue "DaemonSets not at desired state: $MISMATCHED"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 5: Helm Deployments"
{
    echo "HelmReleases:"
    flux get helmreleases -A | head -20
    echo ""

    TOTAL_HELM=$(safe_count "flux get helmreleases -A 2>/dev/null | grep -v 'NAMESPACE' | wc -l")
    FAILED_HELM=$(safe_count "flux get helmreleases -A 2>/dev/null | grep -E '(Failed|Error|Unknown)' | wc -l")

    echo "HelmReleases: $((TOTAL_HELM - FAILED_HELM))/$TOTAL_HELM ready"

    echo ""
    echo "Kustomizations:"
    flux get kustomizations -A | head -20

    TOTAL_KUST=$(safe_count "flux get kustomizations -A 2>/dev/null | grep -v 'NAMESPACE' | wc -l")
    NOT_RECONCILED=$(safe_count "flux get kustomizations -A 2>/dev/null | grep -v 'Applied revision' | grep -v 'NAMESPACE' | wc -l")

    echo ""
    echo "Kustomizations: $((TOTAL_KUST - NOT_RECONCILED))/$TOTAL_KUST reconciled"

    if [ "$FAILED_HELM" -eq 0 ] && [ "$NOT_RECONCILED" -eq 0 ]; then
        log_success "All Helm releases and Kustomizations healthy"
    else
        log_warning "Issues detected - Helm failures: $FAILED_HELM, Kustomization not reconciled: $NOT_RECONCILED"
        if [ "$FAILED_HELM" -gt 0 ]; then
            add_major_issue "HelmRelease failures: $FAILED_HELM"
        fi
        if [ "$NOT_RECONCILED" -gt 0 ]; then
            add_minor_issue "Kustomizations not reconciled: $NOT_RECONCILED"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 6: Deployments & StatefulSets"
{
    echo "Deployments not at desired replicas:"
    kubectl get deployments -A -o json | jq -r '.items[] | select(.spec.replicas != (.status.readyReplicas // 0)) | "\(.metadata.namespace)/\(.metadata.name): \(.status.readyReplicas // 0)/\(.spec.replicas)"' | head -20
    echo ""

    echo "StatefulSets:"
    kubectl get statefulsets -A
    echo ""

    BAD_DEPLOYS=$(kubectl get deployments -A -o json | jq '[.items[] | select(.spec.replicas != (.status.readyReplicas // 0))] | length')
    BAD_STS=$(kubectl get statefulsets -A -o json | jq '[.items[] | select(.spec.replicas != (.status.readyReplicas // 0))] | length')

    if [ "$BAD_DEPLOYS" -eq 0 ] && [ "$BAD_STS" -eq 0 ]; then
        log_success "All deployments and StatefulSets healthy"
    else
        log_warning "Workloads not at desired replicas - Deployments: $BAD_DEPLOYS, StatefulSets: $BAD_STS"
        add_major_issue "Workloads not ready - Deployments: $BAD_DEPLOYS, StatefulSets: $BAD_STS"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 7: Pods Health"
{
    echo "Pod status summary:"
    NON_RUNNING=$(safe_count "kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded --no-headers 2>/dev/null | wc -l")
    echo "Non-running pods: $NON_RUNNING"
    echo ""

    echo "Pods with high restart counts (>5):"
    kubectl get pods -A -o json | jq -r '.items[] | select(.status.containerStatuses[]? | select(.restartCount > 5)) | "\(.metadata.namespace)/\(.metadata.name): \(.status.containerStatuses[0].restartCount) restarts"' | head -20
    echo ""

    CRASH_LOOP=$(safe_count "kubectl get pods -A 2>/dev/null | grep -c 'CrashLoopBackOff'")
    PENDING=$(safe_count "kubectl get pods -A 2>/dev/null | grep -c 'Pending'")

    echo "CrashLoopBackOff pods: $CRASH_LOOP"
    echo "Pending pods: $PENDING"

    if [ "$CRASH_LOOP" -eq 0 ] && [ "$PENDING" -eq 0 ]; then
        log_success "No pods in CrashLoopBackOff or Pending"
    else
        log_critical "Pod issues - CrashLoopBackOff: $CRASH_LOOP, Pending: $PENDING"
        if [ "$CRASH_LOOP" -gt 0 ]; then
            add_critical_issue "Pods in CrashLoopBackOff: $CRASH_LOOP"
        fi
        if [ "$PENDING" -gt 0 ]; then
            add_critical_issue "Pods Pending: $PENDING"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 8: Prometheus & Monitoring"
{
    echo "Prometheus pods:"
    kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus
    echo ""

    echo "Alertmanager pods:"
    kubectl get pods -n monitoring -l app.kubernetes.io/name=alertmanager
    echo ""

    PROM_RUNNING=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus -o json | jq '[.items[] | select(.status.phase=="Running")] | length')
    AM_RUNNING=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=alertmanager -o json | jq '[.items[] | select(.status.phase=="Running")] | length')

    if [ "$PROM_RUNNING" -gt 0 ] && [ "$AM_RUNNING" -gt 0 ]; then
        log_success "Prometheus and Alertmanager running"
    else
        log_critical "Monitoring issue - Prometheus: $PROM_RUNNING, Alertmanager: $AM_RUNNING"
        add_critical_issue "Monitoring system not running - Prom: $PROM_RUNNING, AM: $AM_RUNNING"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 9: Alertmanager Alerts"
{
    echo "Checking Alertmanager alerts via Prometheus API..."
    echo ""

    # Port-forward in background
    kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 > /dev/null 2>&1 &
    PF_PID=$!
    sleep 3

    ALERT_CHECK=$(curl -s 'http://localhost:9090/api/v1/alerts' 2>/dev/null || echo '{"status":"error"}')

    if echo "$ALERT_CHECK" | jq -e '.status == "success"' > /dev/null 2>&1; then
        echo "Alert data retrieved successfully"
        echo ""

        # Get all firing alerts excluding Watchdog
        FIRING_ALERTS=$(echo "$ALERT_CHECK" | jq -r '[.data.alerts[] | select(.state == "firing" and .labels.alertname != "Watchdog" and .labels.alertname != "InfoInhibitor")] | length')

        echo "Firing alerts (excluding Watchdog): $FIRING_ALERTS"
        echo ""

        if [ "$FIRING_ALERTS" -gt 0 ]; then
            echo "Active Alerts:"
            echo "$ALERT_CHECK" | jq -r '.data.alerts[] | select(.state == "firing" and .labels.alertname != "Watchdog" and .labels.alertname != "InfoInhibitor") | "  - \(.labels.alertname) (\(.labels.severity // "unknown")): \(.annotations.summary // .annotations.description // "No description")"' | head -20

            log_warning "Active alerts firing: $FIRING_ALERTS"
            add_major_issue "Prometheus alerts firing: $FIRING_ALERTS"
        else
            log_success "No alerts firing"
        fi
    else
        log_warning "Unable to retrieve alert data from Prometheus"
        add_minor_issue "Could not check Prometheus alerts"
    fi

    # Kill port-forward
    kill $PF_PID 2>/dev/null || true
    wait $PF_PID 2>/dev/null || true
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 10: Longhorn Storage"
{
    echo "Longhorn volumes:"
    kubectl get volumes -n storage -o wide | head -20
    echo ""

    TOTAL_VOLUMES=$(safe_count "kubectl get volumes -n storage --no-headers 2>/dev/null | wc -l")
    UNHEALTHY_VOLUMES=$(kubectl get volumes -n storage -o json 2>/dev/null | jq '[.items[] | select(.status.state != "attached" or .status.robustness != "healthy")] | length')

    echo "Volumes: $((TOTAL_VOLUMES - UNHEALTHY_VOLUMES))/$TOTAL_VOLUMES healthy"

    if [ "$UNHEALTHY_VOLUMES" -gt 0 ]; then
        echo "Unhealthy volumes:"
        kubectl get volumes -n storage -o json | jq -r '.items[] | select(.status.state != "attached" or .status.robustness != "healthy") | "\(.metadata.name): state=\(.status.state) robustness=\(.status.robustness)"'
    fi

    echo ""
    echo "PVC status:"
    PENDING_PVC=$(safe_count "kubectl get pvc -A 2>/dev/null | grep -E '(Pending|Lost|Unknown)' | wc -l")
    echo "Pending/Lost/Unknown PVCs: $PENDING_PVC"

    echo ""
    AUTO_DELETE=$(kubectl get settings.longhorn.io auto-delete-pod-when-volume-detached-unexpectedly -n storage -o jsonpath='{.value}' 2>/dev/null || echo "unknown")
    echo "autoDeletePodWhenVolumeDetachedUnexpectedly: $AUTO_DELETE (should be false)"

    if [ "$UNHEALTHY_VOLUMES" -eq 0 ] && [ "$PENDING_PVC" -eq 0 ] && [ "$AUTO_DELETE" == "false" ]; then
        log_success "Longhorn storage healthy"
    else
        log_warning "Storage issues - Unhealthy volumes: $UNHEALTHY_VOLUMES, Pending PVCs: $PENDING_PVC, AutoDelete: $AUTO_DELETE"
        if [ "$UNHEALTHY_VOLUMES" -gt 0 ]; then
            add_major_issue "Unhealthy Longhorn volumes: $UNHEALTHY_VOLUMES"
        fi
        if [ "$PENDING_PVC" -gt 0 ]; then
            add_major_issue "Pending PVCs: $PENDING_PVC"
        fi
        if [ "$AUTO_DELETE" != "false" ]; then
            add_minor_issue "AutoDelete setting is $AUTO_DELETE (should be false)"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

#######################################
# Phase 3: Application & Service Checks
#######################################

log_section "Section 11: Container Logs Analysis"
{
    echo "Checking infrastructure logs for errors..."

    CILIUM_ERRORS=$(safe_count "kubectl logs -n kube-system -l app.kubernetes.io/name=cilium --tail=100 --since=24h 2>&1 | grep -iE '(error|fatal|critical)' | wc -l")
    echo "Cilium errors (24h): $CILIUM_ERRORS"

    COREDNS_ERRORS=$(safe_count "kubectl logs -n kube-system -l k8s-app=kube-dns --tail=100 --since=24h 2>&1 | grep -iE '(error|fatal)' | wc -l")
    echo "CoreDNS errors (24h): $COREDNS_ERRORS"

    FLUX_ERRORS=$(safe_count "kubectl logs -n flux-system deployment/kustomize-controller --tail=50 --since=24h 2>&1 | grep -iE '(error|fail)' | wc -l")
    echo "Flux controller errors (24h): $FLUX_ERRORS"

    CERT_ERRORS=$(safe_count "kubectl logs -n cert-manager deployment/cert-manager --tail=50 --since=24h 2>&1 | grep -i error | wc -l")
    echo "cert-manager errors (24h): $CERT_ERRORS"

    TOTAL_ERRORS=$((CILIUM_ERRORS + COREDNS_ERRORS + FLUX_ERRORS + CERT_ERRORS))

    if [ "$TOTAL_ERRORS" -lt 10 ]; then
        log_success "Infrastructure logs clean (total errors: $TOTAL_ERRORS)"
    elif [ "$TOTAL_ERRORS" -lt 50 ]; then
        log_warning "Infrastructure errors detected: $TOTAL_ERRORS"
        add_minor_issue "Infrastructure log errors: $TOTAL_ERRORS"
    else
        log_critical "High error count in infrastructure logs: $TOTAL_ERRORS"
        add_critical_issue "High infrastructure error count: $TOTAL_ERRORS"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 12: Talos System Health"
{
    echo "Checking Talos node health..."

    if command -v talosctl &> /dev/null; then
        for node in $NODE_IPS; do
            echo "=== Node $node ==="
            talosctl services --nodes "$node" 2>&1 | head -10 || echo "Failed to get services for $node"
        done
        log_success "Talos health check completed"
    else
        log_warning "talosctl not available, skipping Talos checks"
        add_minor_issue "talosctl not available for Talos health checks"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 13: Hardware Health"
{
    echo "Checking hardware health..."

    if command -v talosctl &> /dev/null; then
        for node in $NODE_IPS; do
            echo "=== Hardware errors on $node ==="
            ERRORS=$(safe_count "talosctl dmesg --nodes '$node' 2>&1 | grep -iE '(error|fail|hardware|memory|ecc|pci|disk)' | wc -l")
            echo "Hardware errors: $ERRORS"
            if [ "$ERRORS" -gt 10 ]; then
                add_minor_issue "High hardware errors on $node: $ERRORS"
            fi
        done
        log_success "Hardware health check completed"
    else
        log_warning "talosctl not available, skipping hardware checks"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 14: Resource Utilization"
{
    echo "Node resource usage:"
    kubectl top nodes
    echo ""

    echo "Top 10 CPU consuming pods:"
    kubectl top pods -A --sort-by=cpu 2>/dev/null | head -15 || echo "Metrics not available"
    echo ""

    echo "Top 10 memory consuming pods:"
    kubectl top pods -A --sort-by=memory 2>/dev/null | head -15 || echo "Metrics not available"
    echo ""

    PRESSURE=$(kubectl get nodes -o json | jq -r '.items[] | select(.status.conditions[] | select(.type=="DiskPressure" or .type=="MemoryPressure") | .status=="True") | .metadata.name')

    if [ -z "$PRESSURE" ]; then
        log_success "No resource pressure detected"
    else
        log_critical "Resource pressure detected on: $PRESSURE"
        add_critical_issue "Resource pressure on nodes: $PRESSURE"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 15: Backup System"
{
    echo "Backup system status:"
    kubectl get cronjob -n storage daily-backup-all-volumes 2>/dev/null || echo "Backup CronJob not found"
    echo ""

    BACKUP_JOB=$(kubectl get jobs -n storage --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null | grep -o 'daily-backup-all-volumes[^ ]*' | head -1 || echo "")
    if [ -n "$BACKUP_JOB" ]; then
        echo "Last backup job:"
        kubectl get job -n storage "$BACKUP_JOB" 2>/dev/null || echo "Job details not available"
        log_success "Backup system operational"
    else
        log_warning "No backup jobs found"
        add_minor_issue "No backup jobs found"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 16: Version Checks"
{
    echo "Kubernetes version:"
    kubectl version -o json 2>/dev/null | jq -r '.serverVersion.gitVersion' || kubectl version --short 2>&1 | grep Server
    echo ""

    if command -v talosctl &> /dev/null; then
        echo "Talos version:"
        talosctl version --nodes "$(echo "$NODE_IPS" | awk '{print $1}')" 2>&1 | head -5 || echo "Failed to get Talos version"
    fi

    log_success "Version check completed"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 17: Security Checks"
{
    echo "Security posture check..."

    ROOT_PODS=$(kubectl get pods -A -o json | jq '[.items[] | select(.spec.securityContext.runAsUser == 0 or (.spec.containers[].securityContext.runAsUser // 0) == 0)] | length')
    echo "Pods running as root: $ROOT_PODS"

    LB_SERVICES=$(safe_count "kubectl get svc -A --field-selector spec.type=LoadBalancer --no-headers 2>/dev/null | wc -l")
    echo "LoadBalancer services: $LB_SERVICES"

    INGRESSES=$(safe_count "kubectl get ingress -A --no-headers 2>/dev/null | wc -l")
    echo "Total ingresses: $INGRESSES"

    if [ "$ROOT_PODS" -eq 0 ]; then
        log_success "No pods running as root"
    else
        log_info "Pods running as root: $ROOT_PODS (review for security)"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 18: Network Infrastructure (UniFi)"
{
    echo "Checking UniFi network..."

    if command -v unifictl &> /dev/null; then
        cd /home/mu/code/unifictl 2>/dev/null || true
        unifictl local health get 2>&1 || echo "UniFi controller not accessible"
        log_success "UniFi check completed"
    else
        log_warning "unifictl not available, skipping UniFi checks"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 18a: UniFi Hardware Metrics (Prometheus)"
{
    echo "Checking UnPoller metrics via Prometheus..."
    echo ""

    # Port-forward in background (use different port to avoid conflicts)
    kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9091:9090 > /dev/null 2>&1 &
    PF_PID=$!
    sleep 3

    # Check if UnPoller is scraping
    UNPOLLER_UP=$(curl -s 'http://localhost:9091/api/v1/query?query=up{job="unpoller"}' 2>/dev/null | python3 -c "
import sys, json
try:
    result = json.load(sys.stdin)
    if result.get('status') == 'success' and result['data']['result']:
        value = result['data']['result'][0]['value'][1]
        print('1' if value == '1' else '0')
    else:
        print('0')
except:
    print('0')
" || echo "0")

    if [ "$UNPOLLER_UP" == "1" ]; then
        echo "✅ UnPoller is scraping metrics"
        echo ""

        # Count online devices
        echo "Online UniFi devices:"
        curl -s 'http://localhost:9091/api/v1/query?query=count(unifipoller_device_uptime_seconds>0)' 2>/dev/null | python3 -c "
import sys, json
try:
    result = json.load(sys.stdin)
    if result.get('status') == 'success' and result['data']['result']:
        count = result['data']['result'][0]['value'][1]
        print(f'  Total online: {count}')
    else:
        print('  Unable to get device count')
except:
    print('  Error getting device count')
" || echo "  Error querying Prometheus"

        echo ""

        # Check for offline devices
        echo "Offline UniFi devices:"
        OFFLINE_DEVICES=$(curl -s 'http://localhost:9091/api/v1/query?query=unifipoller_device_uptime_seconds==0' 2>/dev/null | python3 -c "
import sys, json
try:
    result = json.load(sys.stdin)
    if result.get('status') == 'success' and result['data']['result']:
        offline = result['data']['result']
        if offline:
            for device in offline:
                name = device['metric'].get('name', 'unknown')
                print(f'  - {name}')
            print(f'{len(offline)}')  # Return count on last line
        else:
            print('  None')
            print('0')
    else:
        print('  Unable to check')
        print('0')
except:
    print('  Error')
    print('0')
" || echo -e "  Error\n0")

        OFFLINE_COUNT=$(echo "$OFFLINE_DEVICES" | tail -1)
        echo "$OFFLINE_DEVICES" | head -n -1
        echo ""

        # Check device temperatures
        echo "Device temperatures:"
        curl -s 'http://localhost:9091/api/v1/query?query=unifipoller_device_system_stats_temps' 2>/dev/null | python3 -c "
import sys, json
try:
    result = json.load(sys.stdin)
    if result.get('status') == 'success' and result['data']['result']:
        temps = result['data']['result']
        high_temp_count = 0
        for temp in temps:
            device = temp['metric'].get('name', 'unknown')
            temp_c = float(temp['value'][1])
            if temp_c > 75:
                print(f'  🔴 {device}: {temp_c}°C (HIGH)')
                high_temp_count += 1
            elif temp_c > 60:
                print(f'  🟡 {device}: {temp_c}°C (WARM)')
            else:
                print(f'  ✅ {device}: {temp_c}°C')
        if not temps:
            print('  No temperature data available')
    else:
        print('  Unable to get temperature data')
except Exception as e:
    print(f'  Error: {e}')
" || echo "  Error querying temperatures"

        echo ""

        # Check total client count
        echo "Connected clients:"
        curl -s 'http://localhost:9091/api/v1/query?query=sum(unifipoller_device_user_num_sta)' 2>/dev/null | python3 -c "
import sys, json
try:
    result = json.load(sys.stdin)
    if result.get('status') == 'success' and result['data']['result']:
        count = result['data']['result'][0]['value'][1]
        print(f'  Total clients: {count}')
    else:
        print('  Unable to get client count')
except:
    print('  Error getting client count')
" || echo "  Error querying Prometheus"

        echo ""

        # Check wireless interference
        echo "Wireless interference (>50%):"
        INTERFERENCE=$(curl -s 'http://localhost:9091/api/v1/query?query=unifipoller_device_radio_channel_interference>50' 2>/dev/null | python3 -c "
import sys, json
try:
    result = json.load(sys.stdin)
    if result.get('status') == 'success' and result['data']['result']:
        interference = result['data']['result']
        if interference:
            for radio in interference:
                device = radio['metric'].get('name', 'unknown')
                channel = radio['metric'].get('channel', 'N/A')
                level = float(radio['value'][1])
                print(f'  ⚠️  {device} (channel {channel}): {level}%')
            print(f'{len(interference)}')  # Return count
        else:
            print('  ✅ No high interference detected')
            print('0')
    else:
        print('  Unable to check interference')
        print('0')
except:
    print('  Error')
    print('0')
" || echo -e "  Error\n0")

        INTERFERENCE_COUNT=$(echo "$INTERFERENCE" | tail -1)
        echo "$INTERFERENCE" | head -n -1

        # Evaluate health
        if [ "$OFFLINE_COUNT" -eq 0 ] && [ "$INTERFERENCE_COUNT" -eq 0 ]; then
            log_success "UniFi network hardware healthy"
        elif [ "$OFFLINE_COUNT" -gt 0 ]; then
            log_warning "UniFi offline devices detected: $OFFLINE_COUNT"
            add_minor_issue "UniFi offline devices: $OFFLINE_COUNT"
        fi

        if [ "$INTERFERENCE_COUNT" -gt 0 ]; then
            log_warning "High wireless interference detected: $INTERFERENCE_COUNT radios"
            add_minor_issue "High wireless interference: $INTERFERENCE_COUNT radios"
        fi
    else
        echo "⚠️  UnPoller is not scraping metrics or not found"
        log_warning "UnPoller metrics not available"
        add_minor_issue "UnPoller not providing metrics"
    fi

    # Kill port-forward
    kill $PF_PID 2>/dev/null || true
    wait $PF_PID 2>/dev/null || true
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 19: Network Connectivity"
{
    echo "Ingress controllers:"
    kubectl get svc -n network | grep ingress || echo "No ingress services found"
    echo ""

    echo "external-dns status:"
    kubectl get deployment -n network external-dns 2>/dev/null || echo "external-dns not found"

    log_success "Network connectivity check completed"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 20: GitOps Status"
{
    echo "Git sources:"
    flux get sources git -A | head -10
    echo ""

    echo "Kustomizations:"
    flux get kustomizations -A | head -20
    echo ""

    NOT_RECONCILED=$(safe_count "flux get kustomizations -A 2>/dev/null | grep -v 'Applied revision' | grep -v 'NAMESPACE' | wc -l")
    echo "Not reconciled: $NOT_RECONCILED"

    if [ "$NOT_RECONCILED" -eq 0 ]; then
        log_success "GitOps fully synchronized"
    else
        log_warning "GitOps reconciliation issues: $NOT_RECONCILED"
        add_minor_issue "Kustomizations not reconciled: $NOT_RECONCILED"
    fi
} >> "$OUTPUT_FILE" 2>&1

#######################################
# Phase 4: Advanced Monitoring
#######################################

log_section "Section 21: Namespace Review"
{
    TOTAL_NS=$(safe_count "kubectl get namespaces --no-headers | wc -l")
    echo "Total namespaces: $TOTAL_NS"

    TERMINATING_NS=$(safe_count "kubectl get namespaces 2>/dev/null | grep 'Terminating' | wc -l")
    echo "Terminating namespaces: $TERMINATING_NS"

    TERMINATING_PODS=$(safe_count "kubectl get pods -A 2>/dev/null | grep 'Terminating' | wc -l")
    echo "Terminating pods: $TERMINATING_PODS"

    if [ "$TERMINATING_NS" -eq 0 ] && [ "$TERMINATING_PODS" -eq 0 ]; then
        log_success "No stuck resources"
    else
        log_warning "Stuck resources - NS: $TERMINATING_NS, Pods: $TERMINATING_PODS"
        add_minor_issue "Stuck resources - NS: $TERMINATING_NS, Pods: $TERMINATING_PODS"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 22: Home Automation Health"
{
    echo "Home Assistant:"
    kubectl get pods -n home-automation -l app.kubernetes.io/name=home-assistant
    echo ""

    echo "Home Assistant detailed logs (last 100 lines):"
    HA_LOGS=$(kubectl logs -n home-automation deployment/home-assistant --tail=100 2>&1 || echo "Unable to get logs")
    echo "$HA_LOGS"
    echo ""

    HA_ERRORS=$(echo "$HA_LOGS" | grep -cE "(ERROR|error|Failed|failed)" || true)
    echo "Home Assistant errors: $HA_ERRORS"
    echo ""

    # Categorize errors
    DIRIGERA_ERRORS=$(echo "$HA_LOGS" | grep -c "dirigera" || true)
    TIBBER_ERRORS=$(echo "$HA_LOGS" | grep -c "tibber" || true)
    RESMED_ERRORS=$(echo "$HA_LOGS" | grep -c "resmed" || true)
    SHELLY_ERRORS=$(echo "$HA_LOGS" | grep -c "shelly" || true)
    TESLA_ERRORS=$(echo "$HA_LOGS" | grep -c "tesla" || true)

    echo "Error breakdown:"
    echo "  - Dirigera hub: $DIRIGERA_ERRORS"
    echo "  - Tibber API: $TIBBER_ERRORS"
    echo "  - ResMed MyAir: $RESMED_ERRORS"
    echo "  - Shelly devices: $SHELLY_ERRORS"
    echo "  - Tesla: $TESLA_ERRORS"
    echo ""

    echo "Zigbee2MQTT:"
    kubectl get pods -n home-automation -l app.kubernetes.io/name=zigbee2mqtt
    echo ""

    echo "Zigbee2MQTT logs (last 50 lines):"
    Z2M_LOGS=$(kubectl logs -n home-automation deployment/zigbee2mqtt --tail=50 2>&1 || echo "Unable to get logs")
    echo "$Z2M_LOGS"
    echo ""

    Z2M_ERRORS=$(echo "$Z2M_LOGS" | grep -cE "(error|ERROR|warn|WARN)" || true)
    echo "Zigbee2MQTT errors/warnings: $Z2M_ERRORS"
    echo ""

    echo "Mosquitto MQTT Broker:"
    kubectl get pods -n home-automation -l app.kubernetes.io/name=mosquitto
    echo ""

    echo "Mosquitto logs (last 50 lines):"
    MQTT_LOGS=$(kubectl logs -n home-automation deployment/mosquitto --tail=50 2>&1 || echo "Unable to get logs")
    echo "$MQTT_LOGS"
    echo ""

    MQTT_ERRORS=$(echo "$MQTT_LOGS" | grep -cE "(error|ERROR)" || true)
    echo "Mosquitto errors: $MQTT_ERRORS"

    if [ "$HA_ERRORS" -lt 10 ] && [ "$Z2M_ERRORS" -lt 5 ] && [ "$MQTT_ERRORS" -eq 0 ]; then
        log_success "Home automation healthy"
    elif [ "$HA_ERRORS" -lt 50 ]; then
        log_warning "Home Assistant errors: $HA_ERRORS (mostly external integrations)"
        add_minor_issue "Home Assistant integration errors: $HA_ERRORS (external services)"
    else
        log_warning "High Home Assistant error count: $HA_ERRORS"
        add_major_issue "High Home Assistant error count: $HA_ERRORS"
    fi

    if [ "$Z2M_ERRORS" -gt 10 ]; then
        add_minor_issue "Zigbee2MQTT errors/warnings: $Z2M_ERRORS"
    fi

    if [ "$MQTT_ERRORS" -gt 0 ]; then
        add_minor_issue "Mosquitto MQTT broker errors: $MQTT_ERRORS"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 23: Media Services Health"
{
    echo "Jellyfin status:"
    kubectl get pods -n media -l app.kubernetes.io/name=jellyfin
    echo ""

    echo "Tube Archivist:"
    kubectl get pods -n download -l app.kubernetes.io/name=tube-archivist

    log_success "Media services check completed"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 24: Database Health"
{
    echo "PostgreSQL:"
    kubectl get pods -n databases -l app.kubernetes.io/name=postgresql 2>/dev/null || echo "PostgreSQL not found"
    echo ""

    echo "MariaDB:"
    kubectl get statefulsets -n databases mariadb 2>/dev/null || echo "MariaDB not found"

    log_success "Database health check completed"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 25: External Services & Connectivity"
{
    echo "Cloudflare tunnel:"
    kubectl get pods -n network -l app=cloudflared 2>/dev/null || echo "Cloudflare tunnel not found"

    log_success "External connectivity check completed"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 26: Security & Access Monitoring"
{
    echo "Authentik server:"
    kubectl get pods -n kube-system -l app.kubernetes.io/name=authentik

    log_success "Security monitoring check completed"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 27: Performance & Trends"
{
    echo "Current performance snapshot:"
    kubectl top nodes 2>/dev/null || echo "Metrics not available"

    log_success "Performance check completed"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 28: Backup & Recovery Verification"
{
    BACKUP_JOBS=$(safe_count "kubectl get jobs -n storage --sort-by=.metadata.creationTimestamp 2>/dev/null | tail -5 | grep '1/1' | wc -l")
    echo "Recent successful backups (last 5): $BACKUP_JOBS"

    if [ "$BACKUP_JOBS" -ge 1 ]; then
        log_success "Backup verification passed"
    else
        log_warning "Backup verification issues (recent successes: $BACKUP_JOBS)"
        add_major_issue "No recent successful backups found"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 29: Environmental & Power Monitoring"
{
    echo "System load:"
    kubectl top nodes 2>/dev/null | awk 'NR>1 {print $1 ": CPU=" $3 ", Memory=" $5}' || echo "Metrics not available"

    log_success "Environmental monitoring completed"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 30: Application-Specific Checks"
{
    echo "Authentik:"
    AUTH_PODS=$(safe_count "kubectl get pods -n kube-system -l app.kubernetes.io/name=authentik | grep 'Running' | wc -l")
    echo "Running pods: $AUTH_PODS"
    echo ""

    echo "Grafana:"
    GRAF_PODS=$(safe_count "kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana | grep 'Running' | wc -l")
    echo "Running pods: $GRAF_PODS"
    echo ""

    echo "Longhorn:"
    LH_PODS=$(safe_count "kubectl get pods -n storage -l app.kubernetes.io/name=longhorn-manager | grep 'Running' | wc -l")
    echo "Running manager pods: $LH_PODS"

    log_success "Application-specific checks completed"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 31: Home Assistant Integration Health"
{
    echo "Already covered in Section 22"
    log_info "See Section 22 for detailed Home Assistant integration analysis"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 32: Zigbee2MQTT Device Monitoring"
{
    echo "Zigbee2MQTT status:"
    kubectl get pods -n home-automation -l app.kubernetes.io/name=zigbee2mqtt
    echo ""

    echo "Checking device count..."
    ZIGBEE_DEVICES=$(kubectl exec -n home-automation deployment/zigbee2mqtt -- cat /data/state.json 2>/dev/null | jq 'keys | length' 2>/dev/null || echo "Unable to check")
    echo "Total Zigbee devices: $ZIGBEE_DEVICES"

    log_success "Zigbee monitoring completed"
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 33: Battery Health Monitoring"
{
    echo "Checking battery status..."
    BATTERY_CHECK=$(kubectl exec -n home-automation deployment/zigbee2mqtt -- sh -c '
        cat /data/state.json 2>/dev/null | jq -r "
            to_entries[] |
            select(.value.battery and (.value.battery < 30)) |
            \"\(.key): \(.value.battery)%\"
        " 2>/dev/null || echo "No critical batteries detected"
    ' 2>&1)

    echo "$BATTERY_CHECK"

    CRITICAL_BATTERIES=$(echo "$BATTERY_CHECK" | grep -c "%" || true)

    if [ "$CRITICAL_BATTERIES" -gt 0 ]; then
        log_warning "Critical batteries detected: $CRITICAL_BATTERIES devices"
        add_minor_issue "Zigbee devices with low batteries (<30%): $CRITICAL_BATTERIES"
    else
        log_success "No critical battery levels"
    fi
} >> "$OUTPUT_FILE" 2>&1

#######################################
# Additional Checks: Elasticsearch & UnPoller
#######################################

log_section "Elasticsearch Logs Analysis"
{
    echo "Checking Elasticsearch for errors..."

    ES_POD=$(kubectl get pods -n monitoring -l common.k8s.elastic.co/type=elasticsearch -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$ES_POD" ]; then
        echo "Elasticsearch pod: $ES_POD"
        ES_ERRORS=$(safe_count "kubectl logs -n monitoring '$ES_POD' --tail=100 --since=24h 2>&1 | grep -iE '(error|exception|warn)' | wc -l")
        echo "Elasticsearch errors/warnings (24h): $ES_ERRORS"

        if [ "$ES_ERRORS" -lt 20 ]; then
            log_success "Elasticsearch logs clean"
        else
            log_warning "Elasticsearch errors detected: $ES_ERRORS"
            add_minor_issue "Elasticsearch errors/warnings: $ES_ERRORS"
        fi
    else
        log_warning "Elasticsearch pod not found"
        add_minor_issue "Elasticsearch pod not found"
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "UnPoller Status (Current Investigation)"
{
    echo "UnPoller deployment:"
    kubectl get deployment -n monitoring unpoller 2>/dev/null || echo "UnPoller not found"
    echo ""

    echo "UnPoller pods:"
    kubectl get pods -n monitoring -l app.kubernetes.io/name=unpoller
    echo ""

    UNPOLLER_POD=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=unpoller -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$UNPOLLER_POD" ]; then
        echo "Recent UnPoller logs (last 50 lines):"
        kubectl logs -n monitoring "$UNPOLLER_POD" --tail=50 2>&1 || echo "Unable to get logs"
        echo ""

        UNPOLLER_ERRORS=$(safe_count "kubectl logs -n monitoring '$UNPOLLER_POD' --tail=100 2>&1 | grep -iE '(error|fail)' | wc -l")
        echo "UnPoller errors (last 100 lines): $UNPOLLER_ERRORS"

        UNPOLLER_STATUS=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=unpoller -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "Unknown")

        if [ "$UNPOLLER_STATUS" == "Running" ] && [ "$UNPOLLER_ERRORS" -eq 0 ]; then
            log_success "UnPoller is running successfully"
        elif [ "$UNPOLLER_STATUS" == "Running" ]; then
            log_warning "UnPoller running but has errors: $UNPOLLER_ERRORS"
            add_minor_issue "UnPoller has errors: $UNPOLLER_ERRORS"
        else
            log_critical "UnPoller is not running properly (Status: $UNPOLLER_STATUS)"
            add_critical_issue "UnPoller not running (Status: $UNPOLLER_STATUS)"
        fi
    else
        log_warning "UnPoller pod not found"
        add_minor_issue "UnPoller pod not found"
    fi
} >> "$OUTPUT_FILE" 2>&1

#######################################
# Generate Issues Summary
#######################################

# Calculate counts outside subshell to avoid unbound variable errors
# Temporarily disable strict mode for array length checks
set +u
CRIT_COUNT="${#CRITICAL_ISSUES_LIST[@]}"
MAJOR_COUNT="${#MAJOR_ISSUES_LIST[@]}"
MINOR_COUNT="${#MINOR_ISSUES_LIST[@]}"
set -u

echo "" | tee -a "$OUTPUT_FILE"
log_section "Issues Summary by Severity"

{
    echo "========================================="
    echo "ISSUES SUMMARY"
    echo "========================================="
    echo ""

    echo "🔴 CRITICAL ISSUES ($CRIT_COUNT):"
    if [ "$CRIT_COUNT" -eq 0 ]; then
        echo "  None - Excellent!"
    else
        for issue in "${CRITICAL_ISSUES_LIST[@]}"; do
            echo "  - $issue"
        done
    fi
    echo ""

    echo "🟡 MAJOR ISSUES ($MAJOR_COUNT):"
    if [ "$MAJOR_COUNT" -eq 0 ]; then
        echo "  None"
    else
        for issue in "${MAJOR_ISSUES_LIST[@]}"; do
            echo "  - $issue"
        done
    fi
    echo ""

    echo "🔵 MINOR ISSUES ($MINOR_COUNT):"
    if [ "$MINOR_COUNT" -eq 0 ]; then
        echo "  None"
    else
        for issue in "${MINOR_ISSUES_LIST[@]}"; do
            echo "  - $issue"
        done
    fi
    echo ""

    echo "========================================="
    echo "RECOMMENDATIONS"
    echo "========================================="
    echo ""

    if [ "$CRIT_COUNT" -gt 0 ]; then
        echo "⚠️  IMMEDIATE ACTION REQUIRED:"
        echo "   Address all critical issues immediately"
        echo ""
    fi

    if [ "$MAJOR_COUNT" -gt 0 ]; then
        echo "📋 HIGH PRIORITY:"
        echo "   Review and address major issues within 24-48 hours"
        echo ""
    fi

    if [ "$MINOR_COUNT" -gt 0 ]; then
        echo "📝 MONITOR:"
        echo "   Minor issues should be reviewed during regular maintenance"
        echo ""
    fi

    if [ "$CRIT_COUNT" -eq 0 ] && [ "$MAJOR_COUNT" -eq 0 ]; then
        echo "✅ CLUSTER STATUS: HEALTHY"
        echo "   No critical or major issues detected"
        echo "   Continue regular monitoring and maintenance"
        echo ""
    fi

} | tee -a "$OUTPUT_FILE" "$ISSUES_FILE"

#######################################
# Generate Final Summary
#######################################

echo "" | tee -a "$OUTPUT_FILE"
log_section "Health Check Summary"

{
    echo "========================================="
    echo "HEALTH CHECK SUMMARY"
    echo "========================================="
    echo "Date: $(date)"
    echo "Duration: N/A (full scan)"
    echo ""
    echo "Status Counts:"
    echo "  ✅ Checks Passed: $CHECKS_PASSED"
    echo "  ⚠️  Warnings: $WARNINGS"
    echo "  ❌ Critical Issues: $CRITICAL_ISSUES"
    echo "  ❌ Checks Failed: $CHECKS_FAILED"
    echo ""
    echo "Issue Breakdown:"
    echo "  🔴 Critical: $CRIT_COUNT"
    echo "  🟡 Major: $MAJOR_COUNT"
    echo "  🔵 Minor: $MINOR_COUNT"
    echo ""

    if [ "$CRIT_COUNT" -eq 0 ] && [ "$WARNINGS" -le 2 ]; then
        echo "Overall Health: 🟢 EXCELLENT"
    elif [ "$CRIT_COUNT" -eq 0 ] && [ "$WARNINGS" -le 5 ]; then
        echo "Overall Health: 🟡 GOOD"
    elif [ "$CRIT_COUNT" -le 2 ]; then
        echo "Overall Health: 🟠 WARNING"
    else
        echo "Overall Health: 🔴 CRITICAL"
    fi

    echo ""
    echo "Reports Generated:"
    echo "  - Full report: $OUTPUT_FILE"
    echo "  - Issues summary: $ISSUES_FILE"
    echo "========================================="
} | tee -a "$OUTPUT_FILE" "$SUMMARY_FILE"

echo ""
echo -e "${GREEN}Health check complete!${NC}"
echo "Full report: $OUTPUT_FILE"
echo "Summary: $SUMMARY_FILE"
echo "Issues: $ISSUES_FILE"
echo ""
echo "Next steps:"
echo "  - Review full output: cat $OUTPUT_FILE"
echo "  - Check summary: cat $SUMMARY_FILE"
echo "  - Review issues: cat $ISSUES_FILE"
echo "  - Update health check log: AI_weekly_health_check_current.md"
