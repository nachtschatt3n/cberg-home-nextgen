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

### File Naming Convention
- When encrypting files with sops, filenames must end with `.sops` extension
- Example: `config.sops.yaml`, `secret.sops.json`
- Never commit unencrypted secrets to the repository

### SOPS Configuration Overview
The repository uses path-based encryption rules defined in `.sops.yaml`:
- **Kubernetes secrets**: `kubernetes/**/*.sops.yaml` - encrypts only `data` and `stringData` fields
- **Talos configs**: `talos/**/*.sops.yaml` - encrypts entire file
- **Age key**: `age1nw624gkjpl0sattullahnekdswjcvsgarf8gwwyf9jdqc0zm9enqyp2pf6`

### Correct Workflow for Encrypting Secrets

**CRITICAL**: SOPS creation rules are path-based. You MUST encrypt files that are already in the correct repository path.

#### ❌ WRONG: Encrypting from /tmp
```bash
# DON'T: This will fail with "error loading config: no matching creation rules found"
sops -d kubernetes/apps/namespace/app/secret.sops.yaml > /tmp/secret.yaml
# Edit /tmp/secret.yaml
sops -e /tmp/secret.yaml > kubernetes/apps/namespace/app/secret.sops.yaml
# ❌ FAILS: /tmp/secret.yaml doesn't match any path_regex rules
```

#### ✅ CORRECT: Encrypt in Repository Path
```bash
# Method 1: Edit encrypted file directly (preferred for small changes)
sops kubernetes/apps/namespace/app/secret.sops.yaml
# Opens in $EDITOR, auto-encrypts on save

# Method 2: Decrypt, copy to repo path, encrypt in place (for complex edits)
sops -d kubernetes/apps/namespace/app/secret.sops.yaml > /tmp/secret.yaml
# Edit /tmp/secret.yaml with your changes
cp /tmp/secret.yaml kubernetes/apps/namespace/app/secret-new.sops.yaml
sops -e -i kubernetes/apps/namespace/app/secret-new.sops.yaml
mv kubernetes/apps/namespace/app/secret-new.sops.yaml kubernetes/apps/namespace/app/secret.sops.yaml
rm /tmp/secret.yaml  # Clean up
```

#### Example: Updating pgAdmin Secret
```bash
# Step 1: Decrypt to temporary location for editing
sops -d kubernetes/apps/databases/pgadmin/app/secret.sops.yaml > /tmp/pgadmin-secret.yaml

# Step 2: Edit the decrypted file
# (Make your changes to /tmp/pgadmin-secret.yaml)

# Step 3: Copy to repository path with .sops.yaml extension
cp /tmp/pgadmin-secret.yaml kubernetes/apps/databases/pgadmin/app/secret-new.sops.yaml

# Step 4: Encrypt in place (file must be in kubernetes/ path)
sops -e -i kubernetes/apps/databases/pgadmin/app/secret-new.sops.yaml

# Step 5: Replace old encrypted file
mv kubernetes/apps/databases/pgadmin/app/secret-new.sops.yaml kubernetes/apps/databases/pgadmin/app/secret.sops.yaml

# Step 6: Clean up temporary files
rm -f /tmp/pgadmin-secret.yaml
```

### Common SOPS Errors and Solutions

#### Error: "error loading config: no matching creation rules found"
**Cause**: Trying to encrypt a file outside the `kubernetes/` or `talos/` directory paths.

**Solution**: Copy the file to the correct repository path before encrypting:
```bash
# Wrong: sops -e /tmp/file.yaml > kubernetes/apps/...
# Right: cp /tmp/file.yaml kubernetes/apps/... && sops -e -i kubernetes/apps/...
```

#### Error: "sops metadata not found"
**Cause**: Trying to use `sops --set` on a file that isn't encrypted yet.

**Solution**: Use direct editing or the encrypt-in-place workflow above.

#### Error: File encrypted but Flux can't decrypt
**Cause**: Age key not available in Flux namespace or incorrect encryption regex.

**Solution**:
- Verify age key secret exists: `kubectl get secret sops-age -n flux-system`
- Check encryption regex matches: Kubernetes secrets should only encrypt `data` and `stringData` fields

### Quick Reference Commands

```bash
# Edit encrypted file directly (opens in editor)
sops kubernetes/apps/namespace/app/secret.sops.yaml

# View encrypted file contents without editing
sops -d kubernetes/apps/namespace/app/secret.sops.yaml

# Verify file is properly encrypted
head -20 kubernetes/apps/namespace/app/secret.sops.yaml | grep "sops:"

# Re-encrypt file with updated keys (if age key changes)
sops updatekeys kubernetes/apps/namespace/app/secret.sops.yaml
```

## Information Security
- This repository is public, so never commit secret domains, URLs, or other sensitive information
- All secrets and sensitive data must be encrypted using SOPS before committing
- Ensure no credentials, API keys, or configuration details are exposed in the repository

## Best Practices
- Use kubectl and talosctl commands to debug cluster state rather than console output
- Prefer YAML schemas for configuration files over JSON where possible
- Follow kebab-case naming for files and directories, snake_case for variables/functions
- Use task commands for common operations like validating templates or running tests

## AI & App/Infra References

Detailed AI/Ollama operational guidance has been moved to:
- `docs/sops/ai-integration.md`

Application inventory and service-level context:
- `docs/applications.md`

Infrastructure and topology reference:
- `docs/infrastructure.md`

## New Deployment Blueprint

Use `docs/sops/new-deployment-blueprint.md` as the default SOP for any new application rollout.

Minimum mandatory rules:
- Use GitOps only: change manifests in git, push, and rely on Flux webhook flow (no direct cluster edits and no manual reconcile by default)
- Follow code/style standards from this file (naming, formatting, schema-first config, secret handling)
- Follow namespace placement and directory structure rules from `docs/applications.md` and `docs/infrastructure.md`
- Register all user-facing web apps in Homepage via ingress annotations + labels
- Apply Longhorn storage-class rules (`longhorn` vs `longhorn-static`) from `docs/sops/longhorn.md`
- Execute rollout verification using the SOP test structure (deployment checks, health checks, security checks, rollback path)

## Network Architecture

### Physical Topology

**Internet Connection:**
- ISP: Deutsche Glasfaser (fiber)
- WAN1: 84.143.63.97 (Telekom) - Port 9
- WAN2: 100.93.84.20 (Glasfaser) - IPv6: 2a00:6020:1000:6c::5253 - Port 8

**Core Network Infrastructure:**
- **DMP-CBERG**: Main router/gateway (192.168.30.1, GbE uplink)
  - Connected to: Basement-SW-48 PoE via 10 GbE SFP+

**Switching Infrastructure:**
- **Basement-SW-48 PoE** (192.168.30.118) - 10 GbE SFP+ uplink
  - Provides PoE to access points and connects downstream switches
  - Connected devices:
    - Upstairs-AP-UAP AC LR (192.168.30.200)
    - Hallway-AP-U6 Pro (192.168.30.205)
    - Guest Room USW SW-8 (192.168.30.165, GbE)
    - Basement-SW-24-PoE (192.168.30.220, 10 GbE SFP+)
    - Basement-AP-U6+ (192.168.30.212)
    - U7 Pro (192.168.30.148)
    - Living Room-01-SW-5 (192.168.30.115, GbE)
    - Living Room-02-SW-5 (192.168.30.100, GbE)

- **Basement-SW-24-PoE** (192.168.30.220) - 10 GbE SFP+ uplink
  - Connected Kubernetes cluster nodes:
    - K8s-nuc14-01
    - K8s-nuc14-02
    - K8s-nuc14-03

**Storage:**
- **UNAS-CBERG** (192.168.31.230) - 10 GbE SFP+ connection, Servers VLAN

### VLAN and Network Segmentation

| VLAN ID | Network Name | Subnet | IPv6 Subnet | DHCP Range | Purpose |
|---------|--------------|--------|-------------|------------|---------|
| 1 | Trusted | 192.168.30.0/24 | 2a00:6020:ad52:4300::/64 | 14/101 leases | Network infrastructure, trusted admin devices |
| 2 | USA-Peer | 192.168.60.0/24 | - | 1/249 leases | VPN/peering connections |
| 10 | Servers | 192.168.31.0/24 | 2a00:6020:ad52:4301::/64 | 10/249 leases | NAS, server infrastructure |
| 20 | Trusted-Devices | 192.168.50.0/24 | 2a00:6020:ad52:4302::/64 | 7/101 leases | Trusted client devices |
| 30 | IoT | 192.168.32.0/23 | 2a00:6020:ad52:4303::/64 | 102/499 leases | IoT devices, smart home |
| 40 | Clients-Guests-Untrusted | 192.168.34.0/24 | - | 1/191 leases | Guest and untrusted devices |
| 55 | k8s-network | 192.168.55.0/24 | 2a00:6020:ad52:4304::/64 | 0/11 leases | Kubernetes cluster nodes |

### WiFi Networks

| SSID | Network (VLAN) | Bands | Clients | Security |
|------|----------------|-------|---------|----------|
| cberg-trusted-clients | Trusted-Devices (20) | 2.4 GHz, 5 GHz, 6 GHz | 6 | WPA2/WPA3 |
| cberg-guests | Clients-Guests-Untrusted (40) | 2.4 GHz, 5 GHz | 1 | WPA2 |
| cberg-iot | IoT (30) | 2.4 GHz | 74 | WPA2 |
| Cberg-usa | USA-Peer (2) | 2.4 GHz, 5 GHz, 6 GHz | 1 | WPA2/WPA3 |

**Access Points:**
- Upstairs-AP-UAP AC LR (192.168.30.200) - GbE, legacy AC
- Hallway-AP-U6 Pro (192.168.30.205) - GbE, WiFi 6
- Basement-AP-U6+ (192.168.30.212) - GbE, WiFi 6
- U7 Pro (192.168.30.148) - GbE, WiFi 7

### mDNS Configuration

**Gateway mDNS Proxy:** Custom scope enabled for cross-VLAN mDNS resolution

**VLAN Scope (mDNS bridging enabled):**
- Trusted (1)
- Servers (10)
- Trusted-Devices (20)
- IoT (30)
- k8s-network (55)
- USA-Peer (2)

**Excluded from mDNS:**
- Clients-Guests-Untrusted (40) - isolated guest network

### Kubernetes Cluster Network

**Cluster Nodes:**
- All three nodes connected to Basement-SW-24-PoE via GbE
- Node IPs assigned from k8s-network (192.168.55.0/24, VLAN 55)
- Dedicated network segment isolated from other VLANs

**Inter-VLAN Access:**
- Kubernetes services can access:
  - Servers VLAN (10) - for NAS storage at 192.168.31.230
  - IoT VLAN (30) - for home automation integrations
  - Trusted VLAN (1) - for network management
- Gateway routing and firewall rules control cross-VLAN access

### Network Security Posture

**Default Security:** Allow All (permissive internal routing)

**Network Isolation:**
- Guest network (VLAN 40) isolated from internal networks
- IoT devices (VLAN 30) segmented but accessible for integrations
- Kubernetes cluster (VLAN 55) on dedicated segment with controlled access
- Server infrastructure (VLAN 10) on separate segment

**IPv6:**
- Dual-stack enabled on most networks (Trusted, Servers, IoT, Trusted-Devices, k8s-network)
- Guest and USA-Peer networks IPv4-only

### Network Debugging Commands

#### Basic Network Connectivity
```bash
# Check UniFi controller connectivity
ping 192.168.30.1

# Check Kubernetes node connectivity
ping 192.168.55.{node-ip}

# Check NAS connectivity
ping 192.168.31.230

# Verify cross-VLAN routing
traceroute {destination-ip}

# Check DNS resolution
nslookup {hostname}
dig {hostname}

# Check network interfaces on nodes (via kubectl exec or talosctl)
kubectl exec -n {namespace} {pod} -- ip addr
kubectl exec -n {namespace} {pod} -- ip route
```

#### UniFi Network Diagnostics (unifictl)

**Prerequisites:**
```bash
# Configure unifictl for local controller access (run once)
cd /home/mu/code/unifictl
unifictl local configure \
  --url https://192.168.30.1:8443 \
  --username admin \
  --password '<PASSWORD>' \
  --site default \
  --scope local \
  --verify-tls false
```

**Network Health & Status:**
```bash
# Overall network health
unifictl local health

# WAN connectivity status
unifictl local wan

# Network events (alerts, warnings)
unifictl local events

# Recent events filtered
unifictl local events -o json | jq '.[] | select(.key | contains("EVT_"))'
```

**Device Monitoring:**
```bash
# List all network devices (switches, APs, gateway)
unifictl local devices

# Filter by device type
unifictl local devices --filter "SW"      # Switches
unifictl local devices --filter "AP"      # Access Points
unifictl local devices --filter "UDM"     # Gateway

# Show unadopted/pending devices
unifictl local devices --unadopted

# Watch devices in real-time (refresh every 5s)
unifictl local devices --watch 5

# Export device inventory to CSV
unifictl local devices -o csv > /tmp/devices.csv
```

**Client Connectivity:**
```bash
# List all connected clients
unifictl local clients

# Filter by connection type
unifictl local clients --wired
unifictl local clients --wireless

# Show blocked clients
unifictl local clients --blocked

# Watch clients in real-time
unifictl local clients --watch 5

# Top bandwidth consumers
unifictl local top-clients --limit 20
unifictl local top-devices --limit 10
```

**Network Configuration:**
```bash
# List VLANs/networks
unifictl local networks

# List WiFi networks (SSIDs)
unifictl local wlans

# List firewall rules
unifictl local firewall-rules

# List firewall groups
unifictl local firewall-groups

# Port profiles (switch port configurations)
unifictl local port-profiles
```

**Traffic Analysis:**
```bash
# DPI (Deep Packet Inspection) summary
unifictl local dpi

# Traffic statistics
unifictl local traffic

# Top clients by traffic
unifictl local top-clients --limit 10 -o json
```

**Device Management:**
```bash
# Get specific device details
unifictl local device <MAC> --ports

# Restart a device
unifictl local device <MAC> --restart

# Adopt an unadopted device
unifictl local device <MAC> --adopt

# Upgrade device firmware
unifictl local device <MAC> --upgrade

# Bulk adopt all unadopted devices
unifictl local devices --adopt-all
```

**Client Management:**
```bash
# Block a client
unifictl local client <MAC> --block

# Unblock a client
unifictl local client <MAC> --unblock

# Force reconnect a client
unifictl local client <MAC> --reconnect
```

**Troubleshooting Workflows:**
```bash
# Check for network issues
unifictl local health -o json | jq '.subsystems[] | select(.status != "ok")'

# Find offline devices
unifictl local devices -o json | jq -r '.[] | select(.state != 1) | "\(.name): \(.state_txt)"'

# Check for high client count on specific AP
unifictl local devices --filter "Hallway-AP" -o json | jq '.[].num_sta'

# Export all configuration for backup
unifictl local networks -o csv > /tmp/networks-backup.csv
unifictl local wlans -o csv > /tmp/wlans-backup.csv
unifictl local firewall-rules -o csv > /tmp/firewall-backup.csv
```

**Output Formats:**
```bash
# Pretty table (default, human-readable)
unifictl local devices

# JSON (for scripting and jq processing)
unifictl local devices -o json

# CSV (for spreadsheets and reporting)
unifictl local devices -o csv

# Raw API response
unifictl local devices -o raw
```

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
  numberOfReplicas: 2
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
      numberOfReplicas: "2"
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

# Check Longhorn volume accessMode
kubectl get volume {volume-name} -n storage -o jsonpath='{.spec.accessMode}'

# Check PV accessModes
kubectl get pv {pv-name} -o jsonpath='{.spec.accessModes}'

# Check PVC accessModes
kubectl get pvc {pvc-name} -n {namespace} -o jsonpath='{.spec.accessModes}'
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

## Authentik Blueprint Management

Detailed Authentik blueprint workflows, UUIDs, ingress patterns, and troubleshooting are documented in:
- `docs/sops/authentik.md`

Required policy in this AGENTS file:
- Always use blueprints (GitOps), never UI-only configuration.
- Keep Authentik blueprint data in `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`.

## Documentation Conventions

### Folder Structure

```
runbooks/                        # Recurring operational procedures + their scripts
  version-check.md               # How to run the version check tool
  health-check.md                # Cluster health check procedure
  check-all-versions.py          # Version check script (primary tool)
  extract-current-versions.sh    # Basic extraction script (no update checking)
  check-versions.sh              # Legacy bash version check script
  version-check-current.md       # Auto-generated by runbooks/check-all-versions.py (do not hand-edit)
  health-check-current.md        # Latest health check output (do not hand-edit)
docs/
  troubleshooting/               # Active investigations — delete when resolved
    <topic>-plan.md              # Analysis and options for an ongoing issue
    <topic>-setup.md             # Reference/setup guide for a specific integration
```

### When to Create a Doc

| Situation | Where |
|-----------|-------|
| Recurring task that needs a procedure + script | `runbooks/<name>.md` (+ script alongside) |
| Active investigation or open issue (multi-session) | `docs/troubleshooting/<topic>-plan.md` |
| Integration reference guide with ongoing value | `docs/troubleshooting/<topic>-setup.md` |
| One-time migration, completed cleanup, resolved incident | Don't create — use a commit message |
| Auto-generated current state snapshot | `runbooks/*-current.md` (script-owned) |

### Lifecycle Rules

- **Runbooks**: permanent, updated in-place as procedures evolve
- **Troubleshooting docs**: delete when the issue is resolved or the integration is stable
- **`*-current.md` files**: auto-generated, never hand-edited; overwritten on next run
- **Do NOT create** point-in-time status reports, per-session health snapshots, or migration logs — use git commit messages instead

### Current Progress / Session Notes

Do not create session-specific docs. Use:
- Git commit messages for decisions and completed steps
- `runbooks/health-check-current.md` for current cluster state
- `runbooks/version-check-current.md` for current version/Renovate PR status
- `docs/troubleshooting/` only for issues that span multiple sessions and need structured analysis

### Canonical Reference Docs

Use these docs as source-of-truth references instead of duplicating large operational detail in AGENTS:
- `docs/applications.md` for application inventory and app-level context
- `docs/infrastructure.md` for infrastructure, topology, and platform reference
- `docs/sops/` for operational SOPs (including new deployment blueprint, AI integration, and Authentik blueprint workflows)

### SOP Default Structure

All SOP documents under `docs/sops/` must follow the template at:
- `docs/sops/SOP-TEMPLATE.md`

Required sections in every SOP:
- Description
- Overview
- Blueprints (or `N/A` if not applicable)
- Operational Instructions
- Examples
- Verification Tests (to confirm it worked)
- Troubleshooting
- Diagnose Examples
- Health Check
- Security Check
- Rollback Plan

Versioning requirement:
- Use date versioning format `YYYY.MM.DD` (example: `2026.02.04`)
- Include `Version` and `Last Updated` fields in the SOP header

### SOP Discovery And Usage

Before implementing operational changes, discover and apply existing SOPs:
- List SOPs: `ls docs/sops/`
- Search by topic: `rg -n "<keyword>" docs/sops/*.md`
- View SOP titles: `rg -n "^# SOP:" docs/sops/*.md`

When using an SOP:
- Follow `Operational Instructions`
- Run `Verification Tests`
- Run `Health Check` and `Security Check`
- Keep a rollback path from `Rollback Plan`

If a reusable solution is found and no matching SOP exists:
- Create a new SOP in `docs/sops/<topic>.md` using `docs/sops/SOP-TEMPLATE.md`
- Fill all required sections
- Set date-based version (`YYYY.MM.DD`)

## Special Notes
- Cursor rules: Environment configurations from .cursor/rules/env.mdc
- Copilot instructions: Not found - follow general GitHub guidelines
- always generate strong passwords when you setup secrets
