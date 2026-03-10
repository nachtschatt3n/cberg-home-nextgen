# Compliance Check Runbook

## Purpose
Run a repeatable compliance audit against repository standards for GitOps, security (SOPS), storage (Longhorn), documentation alignment, and Kubernetes manifest validity.

## Scope
This runbook validates:
- GitOps-only workflow expectations
- SOPS encryption and secret hygiene
- Longhorn storage class and naming policy
- Documentation coverage and SOP conformance
- Manifest/template validation checks
- Full-restore readiness (config completeness + data backup coverage)

This runbook is read-only for cluster state and repository files unless you explicitly apply fixes.

## Canonical References
- `docs/applications.md`
- `docs/infrastructure.md`
- `docs/security.md`
- `docs/sops/new-deployment-blueprint.md`
- `docs/sops/sops-encryption.md`
- `docs/sops/longhorn.md`
- `docs/sops/backup.md`
- `docs/sops/SOP-TEMPLATE.md`

## Prerequisites
```bash
# Required tools
command -v kubectl flux task kubeconform talhelper sops rg >/dev/null

# Cluster connectivity (read only)
kubectl cluster-info

# Verify repo root
pwd
```

## 1. Baseline Validation (Required)
Run the repository-standard checks first.

```bash
# Render templates and strict validation
task template:configure -- --strict

# Kubernetes schema validation
kubeconform -summary -fail-on error kubernetes/apps/

# Talos configuration validation
talhelper validate kubernetes/bootstrap/talos/clusterconfig/

# Full test suite
task test
```

Pass criteria:
- All commands exit `0`
- No schema or render errors

## 2. GitOps Compliance
Ensure no direct cluster mutation workflow is embedded in docs/scripts for normal operations.

```bash
# Manual reconcile commands should not be part of default operational flow
rg -n "flux reconcile|kubectl apply|kubectl patch|kubectl edit" docs runbooks \
  | rg -v "troubleshooting|debug|emergency|example"

# Flux status must be healthy
flux get sources git -A
flux get kustomizations -A
flux get helmreleases -A
```

Pass criteria:
- No policy-violating workflow instructions in normal runbooks/SOPs
- Flux resources show ready/healthy status

## 3. SOPS & Secret Hygiene
Check for plaintext secret drift and naming compliance.

```bash
# Secret manifests that are not .sops.yaml (should be empty)
find kubernetes -type f \( -name '*.yaml' -o -name '*.yml' \) \
  | rg '/secret(\\.|-)?.*\\.ya?ml$' \
  | rg -v '\\.sops\\.ya?ml$'

# SOPS files missing metadata (should be empty)
find kubernetes -type f -name '*.sops.yaml' -print0 \
  | xargs -0 rg -L "^sops:" 

# Common accidental plaintext patterns (review all hits)
rg -n "password:|api[_-]?key:|token:|secret:" kubernetes docs \
  -g '!**/*.sops.yaml'
```

Pass criteria:
- No plaintext Kubernetes secrets committed
- All `*.sops.yaml` files contain SOPS metadata
- No sensitive plaintext values in non-SOPS manifests/docs

## 4. Longhorn Policy Compliance
Validate dynamic vs static usage and naming consistency.

```bash
# Dynamic Longhorn PVCs are allowed (UUID PV names expected)
kubectl get pv -o custom-columns=PV:.metadata.name,SC:.spec.storageClassName,CLAIMNS:.spec.claimRef.namespace,CLAIM:.spec.claimRef.name --no-headers \
  | awk '$2=="longhorn"'

# Static Longhorn PVs must not be UUID-named
kubectl get pv -o custom-columns=PV:.metadata.name,SC:.spec.storageClassName --no-headers \
  | awk '$2=="longhorn-static" && $1 ~ /^pvc-/'

# Pending migration queue (policy-specific)
kubectl get pv -o custom-columns=PV:.metadata.name,SC:.spec.storageClassName,CLAIMNS:.spec.claimRef.namespace,CLAIM:.spec.claimRef.name --no-headers \
  | awk '$2=="longhorn" && $1 ~ /^pvc-/'
```

Additional manifest checks:
```bash
# Static PVs should declare longhorn-static and volumeHandle
rg -n "kind:\s*PersistentVolume|storageClassName:\s*longhorn-static|volumeHandle:" kubernetes/apps

# StatefulSet templates should usually stay dynamic longhorn
rg -n "volumeClaimTemplates|storageClassName:\s*longhorn-static" kubernetes/apps
```

Pass criteria:
- No `longhorn-static` PV with UUID name
- StatefulSet volume templates are not forced into static unless explicitly designed
- Pending UUID dynamic PVs are tracked in `runbooks/longhorn-name-migration-pending.md`

## 5. Documentation Compliance
Verify required docs exist and SOPs follow template requirements.

```bash
# Required top-level docs
ls docs/applications.md docs/infrastructure.md docs/security.md docs/integration.md

# SOP files must include required sections
for f in docs/sops/*.md; do
  rg -q "^## .*Description" "$f" || echo "Missing Description: $f"
  rg -q "^## .*Overview" "$f" || echo "Missing Overview: $f"
  rg -q "^## .*Blueprints" "$f" || echo "Missing Blueprints: $f"
  rg -q "^## .*Operational Instructions" "$f" || echo "Missing Operational Instructions: $f"
  rg -q "^## .*Examples" "$f" || echo "Missing Examples: $f"
  rg -q "^## .*Verification Tests" "$f" || echo "Missing Verification Tests: $f"
  rg -q "^## .*Troubleshooting" "$f" || echo "Missing Troubleshooting: $f"
  rg -q "^## .*Diagnose Examples" "$f" || echo "Missing Diagnose Examples: $f"
  rg -q "^## .*Health Check" "$f" || echo "Missing Health Check: $f"
  rg -q "^## .*Security Check" "$f" || echo "Missing Security Check: $f"
  rg -q "^## .*Rollback Plan" "$f" || echo "Missing Rollback Plan: $f"
done

# SOP version metadata
rg -n "^> Version:|^> Last Updated:" docs/sops/*.md
```

Pass criteria:
- No missing required SOP sections
- Version metadata present in SOPs

## 6. Longhorn Migration Compliance Linkage
If non-compliant dynamic UUID PVs exist, they must be tracked.

```bash
# Ensure migration runbooks exist
ls runbooks/longhorn-name-migration.md runbooks/longhorn-name-migration-pending.md

# Quick check that pending file lists current candidates (manual compare)
kubectl get pv -o custom-columns=PV:.metadata.name,SC:.spec.storageClassName,CLAIMNS:.spec.claimRef.namespace,CLAIM:.spec.claimRef.name --no-headers \
  | awk '$2=="longhorn" && $1 ~ /^pvc-/'
```

Pass criteria:
- Both migration runbooks exist
- Pending list is current with live cluster output

## 7. Full Restore Readiness
Determine whether a bare-metal or new-cluster restore can be completed from documented sources.

### 7.1 Git Configuration Completeness
```bash
# Flux bootstrap and common encrypted bootstrap secrets must exist in git
ls kubernetes/flux/components/common/sops-age.sops.yaml
ls kubernetes/flux/components/common/kustomization.yaml
ls kubernetes/flux/meta/kustomization.yaml

# Core platform inventory docs must exist
ls docs/infrastructure.md docs/applications.md docs/network.md docs/security.md
```

Pass criteria:
- Flux bootstrap manifests are present in git
- Core infra/application/security/network references are present

### 7.2 Restore-Critical Local Artifact Audit
These are intentionally not in git and must be available from secure escrow/local backups.

```bash
# Talos bootstrap artifacts (accepted risk: local-only)
ls -la kubernetes/bootstrap/talos/clusterconfig/

# Verify talos artifacts are ignored by git
git check-ignore kubernetes/bootstrap/talos/clusterconfig/talosconfig

# Cloudflared local credential (accepted risk: local-only)
ls -la cloudflared.json
git check-ignore cloudflared.json
```

Pass criteria:
- Local-only restore-critical files exist where expected
- Files are gitignored and not committed
- Their secure backup location is documented outside this repo (operator action)

### 7.3 SOPS Decryption Recoverability
```bash
# Flux decryption secret exists in-cluster
kubectl get secret sops-age -n flux-system

# Repository bootstrap sops secret manifest exists
ls kubernetes/flux/components/common/sops-age.sops.yaml

# Sample decrypt test (pick one known file)
sops -d kubernetes/flux/components/common/sops-age.sops.yaml >/dev/null
```

Pass criteria:
- `sops-age` exists in `flux-system`
- SOPS files decrypt successfully with available key material

### 7.4 Longhorn Backup Coverage (Data Plane)
```bash
# Backup cronjob should exist and not be suspended
kubectl get cronjobs -n storage -o custom-columns=NAME:.metadata.name,SCHEDULE:.spec.schedule,SUSPEND:.spec.suspend --no-headers \
  | rg 'backup.*all.*volume'

# Recent backup jobs for the backup-all cronjob
kubectl get jobs -n storage --sort-by=.metadata.creationTimestamp \
  -o custom-columns=NAME:.metadata.name,SUCCEEDED:.status.succeeded,COMPLETION:.status.completionTime --no-headers \
  | rg 'backup.*all.*volume' | tail -10

# Per-volume backup recency snapshot
kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt,STATE:.status.state,ROBUSTNESS:.status.robustness --no-headers
```

Optional staleness check (48h):
```bash
kubectl get volumes -n storage -o json | python3 - <<'PY'
import json,sys,datetime
from datetime import timezone
j=json.load(sys.stdin)
now=datetime.datetime.now(timezone.utc)
stale=[]
for v in j["items"]:
    name=v["metadata"]["name"]
    ts=v.get("status",{}).get("lastBackupAt")
    if not ts:
        stale.append((name,"missing"))
        continue
    dt=datetime.datetime.fromisoformat(ts.replace("Z","+00:00"))
    hours=(now-dt).total_seconds()/3600
    if hours>48:
        stale.append((name,f"{hours:.1f}h"))
for name,age in stale:
    print(f"{name}\t{age}")
PY
```

Pass criteria:
- Backup-all CronJob exists, is scheduled, and not suspended
- Latest backup jobs succeed
- No critical Longhorn volume missing `lastBackupAt`
- No critical volume older than 48h backup age

### 7.5 Non-Longhorn PVC Restore Coverage
Data on `cifs-*` or other non-Longhorn storage classes is not covered by Longhorn backups.

```bash
# List PVCs not on longhorn/longhorn-static
kubectl get pvc -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,SC:.spec.storageClassName,STATUS:.status.phase --no-headers \
  | awk '$3!=\"longhorn\" && $3!=\"longhorn-static\"'
```

Pass criteria:
- Every non-Longhorn PVC has a documented backup+restore owner and procedure
- Coverage is documented in runbook/SOP/ops notes (operator action)

### 7.6 External Dependency Restore Gaps
Validate restore dependencies that are outside Kubernetes manifests.

Checklist:
- DNS/provider credentials and zone ownership recovery path documented
- NAS/SMB share restore process documented
- Public certificates and identity provider dependencies documented
- VPN/router access path documented for first-cluster bootstrap

Pass criteria:
- No unknown external dependency needed for full restore
- Missing dependencies are tracked as explicit risks with owner

## 8. New Deployment Compliance
**Objective**: Ensure new applications follow the "New Deployment Blueprint" and are properly integrated into the cluster's lifecycle management.

### 8.1 Blueprint Alignment
- [ ] **Naming & Structure**: Verify new deployments follow `docs/sops/new-deployment-blueprint.md` (kebab-case, directory structure).
- [ ] **Storage Classes**: Verify dynamic data uses `longhorn` and config/static data uses `longhorn-static` (see `docs/sops/longhorn.md`).
- [ ] **Secrets**: Verify all secrets are in `*.sops.yaml` and encrypted in the repository path.

### 8.2 Inventory & Documentation
- [ ] **Application Inventory**: Run `python3 runbooks/doc-check.py` and verify Section 3 (Application Documentation) is clean. New apps MUST be in `docs/applications.md`.
- [ ] **Ingress Integration**: Verify the app has the required annotations/labels for Homepage (checked by `doc-check.py` Section 5).

### 8.3 Health & Version Integration
- [ ] **Version Tracking**: Verify `python3 runbooks/check-all-versions.py` picks up the new app's `HelmRelease` (automatic for `kubernetes/apps/**/helmrelease.yaml`).
- [ ] **Operational Health**:
    - [ ] Verify the app appears in the generic checks of `./runbooks/health-check.sh` (Sections 5-7).
    - [ ] For **critical** apps, verify they have a dedicated section in `runbooks/health-check.sh` and `runbooks/health-check.md` for deep-dive health (API checks, database connection counts, etc.).

Pass criteria:
- `doc-check.py` Section 3 is "OK" (no undocumented apps)
- New app's `HelmRelease` is in `kubernetes/apps/`
- App is listed in `docs/applications.md`
- Critical apps have dedicated health check sections

## 9. Report Format
Record results in this structure:

```text
Compliance Check - YYYY-MM-DD

[PASS|FAIL] Baseline Validation
[PASS|FAIL] GitOps Compliance
[PASS|FAIL] SOPS & Secret Hygiene
[PASS|FAIL] Longhorn Policy Compliance
[PASS|FAIL] Documentation Compliance
[PASS|FAIL] Longhorn Migration Tracking
[PASS|FAIL] Full Restore Readiness
[PASS|FAIL] New Deployment Compliance

Findings:
1. <severity> <finding>
2. ...

Required Actions:
1. ...
2. ...
```

## Common Failures and Fix Path
- `kubeconform` errors:
  - Fix invalid manifests, then rerun Section 1.
- Plaintext secret detected:
  - Move to `*.sops.yaml` and encrypt in-repo path per `docs/sops/sops-encryption.md`.
- `longhorn-static` PV with UUID name:
  - Recreate as static named volume/PV/PVC using `runbooks/longhorn-name-migration.md`.
- Missing SOP sections:
  - Update SOP to match `docs/sops/SOP-TEMPLATE.md`.
- Backup not recent / missing:
  - Fix Longhorn backup CronJob and rerun backup SOP (`docs/sops/backup.md`).
- Non-Longhorn PVC without restore plan:
  - Add/validate external backup procedure and ownership documentation.

## Rollback
This runbook performs checks only. If you made remediation changes, rollback via Git:

```bash
git log --oneline
# Revert the remediation commit(s)
git revert <commit-sha>
# Push and allow Flux to reconcile
```

## Recommended Cadence
- Weekly: full run (Sections 1-8)
- Before large deployment changes: Sections 1, 3, 4
- Before release/tag: full run + archive report in PR description
- Quarterly: deep restore-readiness review (Section 7, including external dependencies)
