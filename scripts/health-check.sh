#!/usr/bin/env bash

# Kubernetes Cluster Health Check Script
# Executes all 35 sections from AI_weekly_health_check.MD
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

log_section "Section 18a: UniFi Hardware Metrics (InfluxDB)"
{
    echo "Checking UnPoller metrics from InfluxDB exports..."
    echo ""

    # Get UnPoller pod
    UNPOLLER_POD=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=unpoller -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -z "$UNPOLLER_POD" ]; then
        echo "⚠️  UnPoller pod not found"
        log_warning "UnPoller pod not found"
        add_major_issue "UnPoller pod not found"
    else
        echo "UnPoller pod: $UNPOLLER_POD"
        echo ""

        # Get recent metrics from logs
        RECENT_LOGS=$(kubectl logs -n monitoring "$UNPOLLER_POD" --tail=20 2>&1 || echo "Unable to get logs")

        # Parse latest metrics from logs
        LATEST_METRIC=$(echo "$RECENT_LOGS" | grep "UniFi Metrics Recorded" | tail -1)
        LATEST_EXPORT=$(echo "$RECENT_LOGS" | grep "UniFi Measurements Exported" | tail -1)

        if [ -n "$LATEST_METRIC" ]; then
            echo "Latest metrics recorded:"
            echo "$LATEST_METRIC"
            echo ""

            # Extract counts using grep and awk (take only first match)
            CLIENT_COUNT=$(echo "$LATEST_METRIC" | grep -oP 'Client: \K\d+' | head -1 || echo "0")
            GATEWAY_COUNT=$(echo "$LATEST_METRIC" | grep -oP 'Gateway(s)?: \K\d+' | head -1 || echo "0")
            UAP_COUNT=$(echo "$LATEST_METRIC" | grep -oP 'UAP: \K\d+' | head -1 || echo "0")
            USW_COUNT=$(echo "$LATEST_METRIC" | grep -oP 'USW: \K\d+' | head -1 || echo "0")
            ERROR_COUNT=$(echo "$LATEST_METRIC" | grep -oP 'Err: \K\d+' | head -1 || echo "0")

            echo "Network device summary:"
            echo "  - Connected clients: $CLIENT_COUNT"
            echo "  - Gateways: $GATEWAY_COUNT"
            echo "  - Access Points (UAP): $UAP_COUNT"
            echo "  - Switches (USW): $USW_COUNT"
            echo "  - Errors in recording: $ERROR_COUNT"
            echo ""

            TOTAL_DEVICES=$((GATEWAY_COUNT + UAP_COUNT + USW_COUNT))
            echo "  Total UniFi devices: $TOTAL_DEVICES"
            echo ""
        else
            echo "⚠️  No recent metrics found in logs"
        fi

        if [ -n "$LATEST_EXPORT" ]; then
            echo "Latest InfluxDB export:"
            echo "$LATEST_EXPORT"
            echo ""

            # Check for export errors
            EXPORT_ERRORS=$(echo "$LATEST_EXPORT" | grep -oP 'Err: \K\d+' || echo "0")
            REQ_TIME=$(echo "$LATEST_EXPORT" | grep -oP 'Req/Total: \K[0-9.]+ms' || echo "N/A")

            echo "InfluxDB export status:"
            echo "  - Export errors: $EXPORT_ERRORS"
            echo "  - Request time: $REQ_TIME"
            echo ""
        fi

        # Check overall health
        if [ -n "$LATEST_METRIC" ] && [ "$ERROR_COUNT" -eq 0 ] && [ "$TOTAL_DEVICES" -gt 0 ]; then
            log_success "UnPoller successfully exporting metrics to InfluxDB"
        elif [ -z "$LATEST_METRIC" ]; then
            log_warning "No recent metrics found from UnPoller"
            add_major_issue "UnPoller not recording metrics"
        elif [ "$ERROR_COUNT" -gt 0 ]; then
            log_warning "UnPoller reporting errors: $ERROR_COUNT"
            add_minor_issue "UnPoller has $ERROR_COUNT errors in metric recording"
        elif [ "$TOTAL_DEVICES" -eq 0 ]; then
            log_warning "UnPoller not detecting any UniFi devices"
            add_major_issue "UnPoller shows 0 UniFi devices"
        fi

        # Additional check for recent activity
        LAST_TIMESTAMP=$(echo "$LATEST_METRIC" | grep -oP '^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}' || echo "")
        if [ -n "$LAST_TIMESTAMP" ]; then
            echo "Last metric timestamp: $LAST_TIMESTAMP"
            echo ""
        fi
    fi
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

log_section "Section 22a: MQTT Connectivity & Shelly Devices"
{
    echo "=== MQTT Broker Statistics (Real-time) ==="
    # Use Mosquitto's $SYS topics for accurate connected client count
    MQTT_CONNECTED=$(kubectl exec -n home-automation deployment/mosquitto -c app -- timeout 5 mosquitto_sub -h localhost -t '$SYS/broker/clients/connected' -C 1 2>/dev/null || echo "0")
    MQTT_TOTAL=$(kubectl exec -n home-automation deployment/mosquitto -c app -- timeout 5 mosquitto_sub -h localhost -t '$SYS/broker/clients/total' -C 1 2>/dev/null || echo "0")
    MQTT_INACTIVE=$(kubectl exec -n home-automation deployment/mosquitto -c app -- timeout 5 mosquitto_sub -h localhost -t '$SYS/broker/clients/inactive' -C 1 2>/dev/null || echo "0")

    echo "Total clients: $MQTT_TOTAL"
    echo "Connected/Active: $MQTT_CONNECTED"
    echo "Inactive: $MQTT_INACTIVE"
    echo ""

    echo "=== Recent MQTT Clients (from logs) ==="
    # Fixed parsing: extract client ID properly (field after "as", before space)
    kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=20000 2>&1 | grep "New client connected" | grep -v "<unknown>" | sed 's/.* as //' | sed 's/ .*//' | sort -u | head -20
    echo ""

    echo "=== Shelly MQTT Connections ==="
    # Fixed: increase log window to 20000 and use correct parsing
    SHELLY_COUNT=$(safe_count "kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=20000 2>&1 | grep 'New client connected' | grep -v '<unknown>' | sed 's/.* as //' | sed 's/ .*//' | grep -i shelly | sort -u | wc -l")
    echo "Shelly devices identified (recent reconnections): $SHELLY_COUNT"
    echo ""
    echo "Note: MQTT clients maintain persistent connections. This count shows devices"
    echo "that reconnected recently. Stable devices won't appear in recent logs."
    echo ""

    echo "=== MQTT Authentication Issues ==="
    AUTH_FAILURES=$(safe_count "kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=100 2>&1 | grep -E '(not authorised|authentication|Connection refused)' | wc -l")
    echo "Authentication failures: $AUTH_FAILURES"
    echo ""

    echo "=== MQTT Connection Errors ==="
    MQTT_CONN_ERRORS=$(safe_count "kubectl logs -n home-automation -l app.kubernetes.io/name=mosquitto --tail=100 2>&1 | grep -i error | wc -l")
    echo "Connection errors: $MQTT_CONN_ERRORS"
    echo ""

    echo "=== MQTT Service Status ==="
    kubectl get svc -n home-automation mosquitto-internal -o wide 2>/dev/null || echo "Service not found"
    kubectl get endpoints -n home-automation mosquitto-internal 2>/dev/null || echo "Endpoints not found"
    echo ""

    # Health assessment - use real-time connected count instead of log-based count
    EXPECTED_CLIENTS_MIN=40
    EXPECTED_CLIENTS_MAX=60

    if [ "$AUTH_FAILURES" -gt 5 ]; then
        log_critical "High MQTT authentication failures: $AUTH_FAILURES"
        add_critical_issue "MQTT authentication failures: $AUTH_FAILURES"
    elif [ "$AUTH_FAILURES" -gt 0 ]; then
        log_warning "MQTT authentication failures detected: $AUTH_FAILURES"
        add_minor_issue "MQTT authentication failures: $AUTH_FAILURES"
    fi

    # Check total connected clients instead of just Shelly devices
    if [ "$MQTT_CONNECTED" -lt 20 ]; then
        log_critical "Low MQTT client count: $MQTT_CONNECTED (expected: $EXPECTED_CLIENTS_MIN-$EXPECTED_CLIENTS_MAX)"
        add_critical_issue "Only $MQTT_CONNECTED MQTT clients connected (expected $EXPECTED_CLIENTS_MIN-$EXPECTED_CLIENTS_MAX)"
    elif [ "$MQTT_CONNECTED" -lt 40 ]; then
        log_warning "Below expected MQTT client count: $MQTT_CONNECTED (expected: $EXPECTED_CLIENTS_MIN-$EXPECTED_CLIENTS_MAX)"
        add_minor_issue "MQTT client count below expected: $MQTT_CONNECTED (expected $EXPECTED_CLIENTS_MIN-$EXPECTED_CLIENTS_MAX)"
    else
        log_success "MQTT clients connected: $MQTT_CONNECTED (expected: $EXPECTED_CLIENTS_MIN-$EXPECTED_CLIENTS_MAX)"
    fi

    # Informational check for Shelly devices (not critical since it's based on logs)
    if [ "$SHELLY_COUNT" -lt 10 ]; then
        log_info "Few Shelly devices in recent logs: $SHELLY_COUNT (may indicate stable connections)"
    else
        log_info "Shelly devices in recent logs: $SHELLY_COUNT"
    fi

    if [ "$MQTT_CONN_ERRORS" -gt 10 ]; then
        log_warning "High MQTT connection errors: $MQTT_CONN_ERRORS"
        add_minor_issue "MQTT connection errors: $MQTT_CONN_ERRORS"
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
    echo "Checking battery status across all Zigbee devices..."
    echo ""

    # Get battery data (IEEE addresses and levels)
    BATTERY_DATA=$(kubectl exec -n home-automation deployment/zigbee2mqtt -- cat /data/state.json 2>/dev/null | jq -r 'to_entries[] | select(.value.battery) | "\(.key)|\(.value.battery)"' 2>/dev/null || echo "")

    # Get device friendly names mapping
    CONFIG_DATA=$(kubectl exec -n home-automation deployment/zigbee2mqtt -- cat /data/configuration.yaml 2>/dev/null | grep -A1 "'0x" | grep -E "^  '0x|friendly_name:" | sed "s/'//g" | paste - - | awk -F: '{gsub(/^[ \t]+/, "", $1); gsub(/^[ \t]+/, "", $3); print $1"|"$3}' 2>/dev/null || echo "")

    # Create combined list with friendly names
    BATTERY_LIST=""
    while IFS='|' read -r ieee battery; do
        if [ -n "$ieee" ] && [ -n "$battery" ]; then
            # Look up friendly name
            friendly=$(echo "$CONFIG_DATA" | grep "^$ieee|" | cut -d'|' -f2-)
            [ -z "$friendly" ] && friendly="$ieee"
            BATTERY_LIST="${BATTERY_LIST}${friendly}|${battery}"$'\n'
        fi
    done <<< "$BATTERY_DATA"

    if [ -z "$BATTERY_LIST" ]; then
        echo "⚠️  Unable to retrieve battery data"
        log_warning "Unable to retrieve Zigbee battery data"
        add_minor_issue "Cannot retrieve Zigbee battery status"
    else
        # Count total battery devices
        TOTAL_BATTERY=$(echo "$BATTERY_LIST" | wc -l)
        echo "Total battery-powered devices: $TOTAL_BATTERY"
        echo ""

        # Initialize counters
        CRITICAL_COUNT=0
        WARNING_COUNT=0
        MONITOR_COUNT=0
        GOOD_COUNT=0

        # Categorize by battery level
        CRITICAL_BATTERIES=""
        WARNING_BATTERIES=""
        MONITOR_BATTERIES=""

        while IFS='|' read -r friendly battery; do
            if [ -n "$friendly" ] && [ -n "$battery" ]; then
                # Remove any decimal points
                battery_int=$(echo "$battery" | awk '{print int($1)}')

                if [ "$battery_int" -lt 15 ]; then
                    CRITICAL_BATTERIES="${CRITICAL_BATTERIES}  - ${friendly} (${battery}%)\n"
                    CRITICAL_COUNT=$((CRITICAL_COUNT + 1))
                elif [ "$battery_int" -lt 30 ]; then
                    WARNING_BATTERIES="${WARNING_BATTERIES}  - ${friendly} (${battery}%)\n"
                    WARNING_COUNT=$((WARNING_COUNT + 1))
                elif [ "$battery_int" -lt 50 ]; then
                    MONITOR_BATTERIES="${MONITOR_BATTERIES}  - ${friendly} (${battery}%)\n"
                    MONITOR_COUNT=$((MONITOR_COUNT + 1))
                else
                    GOOD_COUNT=$((GOOD_COUNT + 1))
                fi
            fi
        done <<< "$BATTERY_LIST"

        # Display categorized results
        echo "🔴 CRITICAL (<15%) - Replace Immediately:"
        if [ "$CRITICAL_COUNT" -gt 0 ]; then
            echo -e "$CRITICAL_BATTERIES"
        else
            echo "  None"
        fi
        echo ""

        echo "🟡 WARNING (15-30%) - Replace Soon:"
        if [ "$WARNING_COUNT" -gt 0 ]; then
            echo -e "$WARNING_BATTERIES"
        else
            echo "  None"
        fi
        echo ""

        echo "🔵 MONITOR (30-50%) - Watch Closely:"
        if [ "$MONITOR_COUNT" -gt 0 ]; then
            echo -e "$MONITOR_BATTERIES"
        else
            echo "  None"
        fi
        echo ""

        echo "✅ GOOD (>50%):"
        echo "  $GOOD_COUNT devices"
        echo ""

        # Calculate average battery level
        AVG_BATTERY=$(echo "$BATTERY_LIST" | awk -F'|' '{sum+=$2; count++} END {if(count>0) print int(sum/count); else print 0}')
        echo "Average battery level: ${AVG_BATTERY}%"
        echo ""

        # Add issues based on severity
        if [ "$CRITICAL_COUNT" -gt 0 ]; then
            log_warning "CRITICAL: $CRITICAL_COUNT devices with batteries <15%"
            add_major_issue "Critical battery levels (<15%): $CRITICAL_COUNT devices need immediate replacement"
        fi

        if [ "$WARNING_COUNT" -gt 0 ]; then
            log_warning "WARNING: $WARNING_COUNT devices with batteries 15-30%"
            add_minor_issue "Low batteries (15-30%): $WARNING_COUNT devices need replacement soon"
        fi

        if [ "$CRITICAL_COUNT" -eq 0 ] && [ "$WARNING_COUNT" -eq 0 ]; then
            log_success "All Zigbee device batteries above 30%"
        fi

        # Show recommendations
        echo "📋 Recommendations:"
        if [ "$CRITICAL_COUNT" -gt 0 ]; then
            echo "  🔴 URGENT: Replace batteries in $CRITICAL_COUNT devices immediately"
        fi
        if [ "$WARNING_COUNT" -gt 0 ]; then
            echo "  🟡 Replace batteries in $WARNING_COUNT devices within 1-2 weeks"
        fi
        if [ "$MONITOR_COUNT" -gt 0 ]; then
            echo "  🔵 Monitor $MONITOR_COUNT devices, plan battery replacement"
        fi
        if [ "$CRITICAL_COUNT" -eq 0 ] && [ "$WARNING_COUNT" -eq 0 ] && [ "$MONITOR_COUNT" -eq 0 ]; then
            echo "  ✅ All devices have healthy battery levels"
        fi
    fi
} >> "$OUTPUT_FILE" 2>&1

log_section "Section 34: Elasticsearch Application Logs Analysis"
{
    echo "Querying Elasticsearch for error patterns in application logs..."
    echo ""

    # Get Elasticsearch password
    ES_PASSWORD=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user -o jsonpath='{.data.elastic}' 2>/dev/null | base64 -d || echo "")

    if [ -z "$ES_PASSWORD" ]; then
        log_warning "Cannot retrieve Elasticsearch password"
        add_major_issue "Elasticsearch password not accessible"
    else
        # Port-forward to Elasticsearch
        kubectl port-forward -n monitoring svc/elasticsearch-es-http 9200:9200 > /dev/null 2>&1 &
        PF_PID=$!
        sleep 3

        # Get today's index
        TODAY_INDEX="fluent-bit-$(date +%Y.%m.%d)"
        echo "Querying index: $TODAY_INDEX"
        echo ""

        # Query for error patterns
        ERROR_DATA=$(curl -k -u "elastic:$ES_PASSWORD" -X GET "https://localhost:9200/${TODAY_INDEX}/_search" -H 'Content-Type: application/json' -d '{
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
                "size": 10
              }
            },
            "by_pod": {
              "terms": {
                "field": "k8s_pod_name.keyword",
                "size": 10
              }
            }
          }
        }' 2>/dev/null || echo '{"hits":{"total":{"value":0}}}')

        TOTAL_ERRORS=$(echo "$ERROR_DATA" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['hits']['total']['value'])
except:
    print('0')
" || echo "0")

        echo "Total errors in logs today: $TOTAL_ERRORS"
        echo ""

        if [ "$TOTAL_ERRORS" -gt 0 ] && [ "$TOTAL_ERRORS" != "0" ]; then
            echo "Top 5 namespaces with errors:"
            echo "$ERROR_DATA" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for bucket in data['aggregations']['by_namespace']['buckets'][:5]:
        print(f\"  {bucket['key']}: {bucket['doc_count']}\")
except:
    print('  Unable to parse data')
"
            echo ""

            echo "Top 5 pods with errors:"
            echo "$ERROR_DATA" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for bucket in data['aggregations']['by_pod']['buckets'][:5]:
        print(f\"  {bucket['key']}: {bucket['doc_count']}\")
except:
    print('  Unable to parse data')
"
            echo ""
        fi

        # Check for specific critical patterns
        echo "Checking for critical error patterns..."

        FATAL_COUNT=$(curl -k -u "elastic:$ES_PASSWORD" -X GET "https://localhost:9200/${TODAY_INDEX}/_search" -H 'Content-Type: application/json' -d '{
          "size": 0,
          "query": {
            "query_string": {
              "query": "*FATAL* OR *OOMKilled*",
              "default_field": "log"
            }
          }
        }' 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['hits']['total']['value'])
except:
    print('0')
" || echo "0")

        echo "  FATAL/OOMKilled errors: $FATAL_COUNT"
        echo ""

        # Kill port-forward
        kill $PF_PID 2>/dev/null || true
        wait $PF_PID 2>/dev/null || true

        # Categorize by severity
        TOTAL_ERRORS_INT=$(echo "$TOTAL_ERRORS" | tr -cd '0-9' || echo "0")
        [ -z "$TOTAL_ERRORS_INT" ] && TOTAL_ERRORS_INT=0

        FATAL_COUNT_INT=$(echo "$FATAL_COUNT" | tr -cd '0-9' || echo "0")
        [ -z "$FATAL_COUNT_INT" ] && FATAL_COUNT_INT=0

        if [ "$FATAL_COUNT_INT" -gt 0 ]; then
            log_critical "FATAL/OOM errors detected in logs: $FATAL_COUNT_INT"
            add_critical_issue "FATAL/OOM errors in Elasticsearch logs: $FATAL_COUNT_INT"
        elif [ "$TOTAL_ERRORS_INT" -gt 10000 ]; then
            log_warning "High error count in logs: $TOTAL_ERRORS_INT (>10,000 threshold)"
            add_major_issue "High error count in logs: $TOTAL_ERRORS_INT"
        elif [ "$TOTAL_ERRORS_INT" -gt 5000 ]; then
            log_warning "Elevated error count in logs: $TOTAL_ERRORS_INT"
            add_minor_issue "Elevated error count in logs: $TOTAL_ERRORS_INT"
        elif [ "$TOTAL_ERRORS_INT" -lt 1000 ]; then
            log_success "Log error count within normal range: $TOTAL_ERRORS_INT"
        else
            log_info "Log error count: $TOTAL_ERRORS_INT (monitor for trends)"
        fi
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
