# Agent-Specific Guidelines

## Build/Lint/Test Commands
- Validate cluster manifests: `task template:configure -- --strict`
- Lint Kubernetes manifests: `kubeconform -summary -fail-on error kubernetes/apps/`
- Validate Talos configs: `talhelper validate kubernetes/bootstrap/talos/clusterconfig/`
- Run all tests: `task test` (checks template rendering, config validation)
- Test single component: `kubeconform -summary kubernetes/apps/[category]/[app]`
- Run specific task: `task [task-name]`

## Code Style
- Imports: Prefer relative imports for local files, absolute for standard libraries
- Formatting: 2-space indentation (except Python/Shell at 4), LF line endings
- Types: Use YAML schemas for configuration, JSON schema where needed
- Naming: Use kebab-case for files/directories, snake_case for variables/functions
- Error handling: Use Kubernetes pod logs for debugging, not console output
- Secrets: Never commit unencrypted; always use `.sops.yaml` with age encryption

## GitOps Workflow
- All changes must be made through the GitOps Flux workflow
- Modify configuration in the git repository
- Push changes to GitHub which triggers a webhook to reconcile the cluster
- Monitor reconciliation events in the Flux system
- Do not make direct modifications to the Kubernetes cluster

## SOPS Encryption Rules
- When encrypting files with sops, filenames must end with `.sops` extension
- Example: `config.sops.yaml`, `secret.sops.json`
- Never commit unencrypted secrets to the repository

## Information Security
- This repository is public, so never commit secret domains, URLs, or other sensitive information
- All secrets and sensitive data must be encrypted using SOPS before committing
- Ensure no credentials, API keys, or configuration details are exposed in the repository

## Best Practices
- Use kubectl and talosctl commands to debug cluster state rather than console output
- Prefer YAML schemas for configuration files over JSON where possible
- Follow kebab-case naming for files and directories, snake_case for variables/functions
- Use task commands for common operations like validating templates or running tests

## Longhorn Storage Management

### Storage Class Guidelines

#### Use `longhorn` (Dynamic Provisioning) For:
- Application databases (PostgreSQL, MariaDB, MySQL, etc.)
- Application data that grows over time
- Cache volumes
- StatefulSet volumes (they require dynamic provisioning)
- Any volume where automatic provisioning is preferred

**Expected Behavior:**
- PVC Name: Clean, descriptive (e.g., `langfuse-postgresql-data`)
- PV Name: Auto-generated UUID (e.g., `pvc-df1999c2-c73c-4e54-a0a7-9f30571e8636`)
- **IMPORTANT**: do not use UUID PV names use the longhorn-static class

#### Use `longhorn-static` For:
- Configuration directories with fixed size
- Volumes you want to manually manage and preserve
- Volumes that should survive namespace deletions
- Volumes requiring specific Longhorn settings

**Requirements:**
- Must pre-create Longhorn volume (via UI or CRD)
- PV's volumeHandle must match Longhorn volume name exactly
- More complex but provides manual control

### PV/PVC Naming Standards

#### For New Deployments:
```yaml
# Good PVC naming
metadata:
  name: {app}-{purpose}  # e.g., postgres-data, redis-cache, app-config

# Storage class selection
spec:
  storageClassName: longhorn        # For app data (UUID PVs expected)
  storageClassName: longhorn-static # For config (clean PVs)
```

#### Examples of Correct Naming:
- `langfuse-postgresql-data` (using longhorn) → PV: `pvc-df1999c2...` ✅
- `home-assistant-config` (using longhorn-static) → PV: `home-assistant-config` ✅
- `bytebot-cache` (using longhorn) → PV: `pvc-4b56f40c...` ✅

### Longhorn Volume Creation for longhorn-static

If you absolutely must create a longhorn-static volume:

```yaml
# Step 1: Create Longhorn Volume
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: my-app-data
  namespace: storage
spec:
  size: "10737418240"  # Size in bytes (10Gi = 10 * 1024^3)
  numberOfReplicas: 3
  dataEngine: v1
  accessMode: rwo       # or rw for ReadWriteMany
  frontend: blockdev    # Required!
  migratable: false
  encrypted: false

---
# Step 2: Create PV
apiVersion: v1
kind: PersistentVolume
metadata:
  name: my-app-data
spec:
  capacity:
    storage: 10Gi
  volumeMode: Filesystem
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: longhorn-static
  csi:
    driver: driver.longhorn.io
    fsType: ext4
    volumeAttributes:
      numberOfReplicas: "3"
      staleReplicaTimeout: "30"
    volumeHandle: my-app-data  # Must match Longhorn volume name!

---
# Step 3: Create PVC
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: my-app-data
  namespace: my-namespace
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: longhorn-static
  volumeName: my-app-data
```

### Common Mistakes to Avoid

1. **Creating PV before Longhorn Volume**
   - Error: "volume not found"
   - Fix: Create Longhorn Volume first, wait for it to be ready

2. **Mismatched volumeHandle**
   - Error: Volume fails to attach
   - Fix: PV's volumeHandle must exactly match Longhorn volume name

3. **Missing frontend in Longhorn Volume**
   - Error: "invalid volume frontend specified"
   - Fix: Add `frontend: blockdev` to Longhorn Volume spec

4. **Attempting to migrate StatefulSet volumes**
   - Error: StatefulSets require dynamic provisioning
   - Fix: Don't migrate StatefulSet volumes, use longhorn storage class

### Storage Debugging Commands

```bash
# Check Longhorn volumes
kubectl get volume -n storage

# Check PV/PVC bindings
kubectl get pv,pvc -A | grep {app-name}

# Check Longhorn volume details
kubectl describe volume -n storage {volume-name}

# Check for storage-related events
kubectl get events -n {namespace} --field-selector type=Warning

# Verify volume attachment
kubectl describe pod {pod-name} -n {namespace} | grep -A 10 "Volumes:"
```

## Monitoring & Debugging

### Prometheus Access Patterns

#### Port-Forward to Prometheus
```bash
# Start port-forward (use background if needed for long sessions)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &

# Alternative port to avoid conflicts
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9091:9090 &

# Kill all port-forwards when done
killall kubectl
```

#### Query Prometheus API
```bash
# Get all firing alerts (avoid jq shell escaping issues)
curl -s 'http://localhost:9090/api/v1/alerts' | grep -o '"alertname":"[^"]*"' | sort -u

# Get specific metrics
curl -s 'http://localhost:9090/api/v1/query?query=up' | python3 -c "import sys, json; print(json.load(sys.stdin))"

# Parse JSON with Python (more reliable than jq for complex queries)
curl -s 'http://localhost:9090/api/v1/targets' | python3 -c "
import sys, json
data = json.load(sys.stdin)
for target in data['data']['activeTargets']:
    print(f\"{target['labels']['job']}: {target['health']}\")
"
```

#### Common Prometheus Queries
```bash
# Check scrape target health
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s 'http://localhost:9090/api/v1/targets' | python3 -c "
import sys, json;
targets = json.load(sys.stdin)['data']['activeTargets']
print(f'Total: {len(targets)}, Up: {sum(1 for t in targets if t[\"health\"] == \"up\")}')
"

# Get firing alerts (excluding Watchdog/InfoInhibitor)
curl -s 'http://localhost:9090/api/v1/alerts' | grep -o '"alertname":"[^"]*"' | grep -v Watchdog | grep -v InfoInhibitor | sort -u
```

### Event Log Patterns

```bash
# Get recent cluster events (all namespaces)
kubectl get events -A --sort-by='.lastTimestamp' | tail -50

# Get warning events only
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -30

# Get events for specific object
kubectl get events -n {namespace} --field-selector involvedObject.name={name},involvedObject.kind={kind} --sort-by='.lastTimestamp'

# Example: Check HelmRepository events
kubectl get events -n flux-system --field-selector involvedObject.name=external-dns,involvedObject.kind=HelmRepository --sort-by='.lastTimestamp'
```

### Pod and DaemonSet Debugging

```bash
# Check DaemonSet status with Python parsing
kubectl get daemonset {name} -n {namespace} -o json | python3 -c "
import sys, json
s = json.load(sys.stdin)['status']
print(f\"Desired: {s['desiredNumberScheduled']}, Ready: {s['numberReady']}, Available: {s['numberAvailable']}\")
"

# Check pod logs for errors
kubectl logs -n {namespace} {pod-name} --tail=100 | grep -i "warn\|error\|fail"

# Check pod events
kubectl describe pod -n {namespace} {pod-name} | grep -A 10 "Events:"

# Check pods on specific node
kubectl get pods -A --field-selector spec.nodeName={node-name}

# Count pods per node
kubectl get pods -A --field-selector spec.nodeName={node-name} --no-headers | wc -l
```

### Flux Debugging

```bash
# Check kustomization status
kubectl get kustomization {name} -n {namespace} -o jsonpath='{.status.conditions[?(@.type=="Ready")]}'

# Check HelmRepository status
kubectl get helmrepository {name} -n flux-system -o jsonpath='{.spec.url}'
kubectl get helmrepository {name} -n flux-system -o jsonpath='{.status.conditions[?(@.type=="Ready")].message}'

# List all kustomizations and their status
flux get kustomizations -A

# Check source-controller logs for repository issues
kubectl logs -n flux-system deployment/source-controller --tail=50 | grep -i {repo-name}
```

### JSON Parsing Patterns

When dealing with kubectl JSON output, prefer Python over jq to avoid shell escaping issues:

```bash
# AVOID: jq with complex queries (shell escaping issues)
kubectl get pod {name} -o json | jq '.status.conditions[] | select(.type == "Ready")'

# PREFER: Python for complex parsing
kubectl get pod {name} -o json | python3 -c "
import sys, json
pod = json.load(sys.stdin)
ready = next((c for c in pod['status']['conditions'] if c['type'] == 'Ready'), None)
print(f\"Ready: {ready['status']}\")
"

# Simple grep patterns for quick checks
kubectl get helmrepository -n flux-system -o yaml | grep -A 5 "status:"
```

### Job and CronJob Monitoring

**Active CronJobs in Cluster:**
- `storage/backup-of-all-volumes`: Daily Longhorn volume backups at 3:00 AM
- `kube-system/descheduler`: Pod rescheduling optimization

```bash
# List all CronJobs
kubectl get cronjobs -A

# List recent jobs
kubectl get jobs -A --sort-by='.status.startTime' | tail -20

# Check job logs
kubectl logs -n {namespace} job/{job-name} --tail=50

# Delete failed jobs
kubectl delete job {job-name} -n {namespace}
```

### Longhorn Backup Verification

```bash
# Check Longhorn backup CronJob
kubectl get cronjob backup-of-all-volumes -n storage

# Check last backup job
kubectl get jobs -n storage | grep backup-of-all-volumes

# View backup job logs
kubectl logs -n storage job/{job-name} --tail=100

# Check volume backup status
kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,SIZE:.spec.size,LAST_BACKUP:.status.lastBackupAt,BACKUP:.status.lastBackup --no-headers
```

### Resource Usage Checks

```bash
# Node resource usage
kubectl top node {node-name}
kubectl top nodes

# Pod resource usage
kubectl top pod -n {namespace} -l app={label}

# Check actual vs requested resources
kubectl get deployment {name} -n {namespace} -o jsonpath='{.spec.template.spec.containers[0].resources}' | python3 -c "
import sys, json
r = json.load(sys.stdin)
print(f\"CPU: {r['requests']['cpu']} / {r['limits']['cpu']}, Memory: {r['requests']['memory']} / {r['limits']['memory']}\")
"
```

### Container Debugging Limitations

fluent-bit and other minimal containers don't have common utilities:
```bash
# These will FAIL in fluent-bit pods:
kubectl exec -n monitoring fluent-bit-xxx -- cat /file  # No cat
kubectl exec -n monitoring fluent-bit-xxx -- curl url   # No curl
kubectl exec -n monitoring fluent-bit-xxx -- wget url   # No wget

# Use port-forward instead for HTTP endpoints:
kubectl port-forward -n monitoring {pod-name} 2020:2020 &
curl http://localhost:2020/api/v1/health
```

## Special Notes
- Cursor rules: Environment configurations from .cursor/rules/env.mdc
- Copilot instructions: Not found - follow general GitHub guidelines
