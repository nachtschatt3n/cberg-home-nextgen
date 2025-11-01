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
- **IMPORTANT**: UUID PV names are NORMAL and CORRECT - do not attempt to "fix" them

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

### PV/PVC Migration - DO NOT DO IT

**Critical Warning**: Do NOT attempt to migrate existing dynamically provisioned volumes to have "clean" PV names.

**Why?**
1. UUID PV names are standard Kubernetes practice for dynamic provisioning
2. Migration requires 30-45 minutes downtime per volume
3. Requires complex Longhorn volume pre-creation
4. Risk of data loss during migration
5. Benefit is purely cosmetic (PV names are mostly hidden)
6. Effort: 20+ volumes × 45 min = 15+ hours of work

**When Migration Might Be Justified:**
- Volume is < 5Gi and low-risk (cache, logs)
- You're already planning maintenance for other reasons
- Volume is truly static configuration data
- You need longhorn-static's manual control features

**Detailed Documentation:**
- Migration guide: `/docs/migration/pv-pvc-naming-migration.md`
- Lessons learned: `/docs/migration/pv-pvc-migration-lessons-learned.md`
- Example migration: `/kubernetes/migrations/ai-namespace/`

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

## Special Notes
- Cursor rules: Environment configurations from .cursor/rules/env.mdc
- Copilot instructions: Not found - follow general GitHub guidelines