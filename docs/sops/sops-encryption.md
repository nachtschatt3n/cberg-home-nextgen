# SOP: SOPS Encryption

> Standard Operating Procedures for secret management with SOPS and age encryption.
> Reference: `docs/security.md` for security overview and key details.
> Description: Encrypting, editing, validating, and rotating secrets with SOPS + age.
> Version: `2026.03.01`
> Last Updated: `2026-03-01`
> Owner: `Platform`

---

## Description

This SOP defines the required workflows for handling encrypted secrets in a public GitOps repository
using SOPS and age, including error handling and validation checks.

---

## Overview

SOPS (Secrets OPerationS) with age encryption secures all secrets stored in this public Git repository.
Flux decrypts secrets at apply time using the age private key stored in the cluster.
This repository is public: never commit unencrypted credentials, domains, URLs, or other sensitive values.
Apply secret changes through GitOps: update encrypted files in this repository, commit, push, and let Flux reconcile.

| Setting | Value |
|---------|-------|
| Encryption tool | SOPS v3.9.4 |
| Backend | age v1.2.1 |
| Age public key | `age1nw624gkjpl0sattullahnekdswjcvsgarf8gwwyf9jdqc0zm9enqyp2pf6` |
| Key file | `$PWD/age.key` (gitignored) |
| Env var | `SOPS_AGE_KEY_FILE=$PWD/age.key` |

---

## Blueprints

N/A for dedicated Authentik-style blueprints.

Secret encryption policy source-of-truth:
- `.sops.yaml` creation rules
- SOPS-encrypted manifest files under `kubernetes/**/*.sops.yaml` and `talos/**/*.sops.yaml`

---

## Operational Instructions

1. Create/edit secret files in repository paths matching `.sops.yaml` creation rules.
2. Encrypt with `sops -e -i` (or edit in-place with `sops <file>`).
3. Verify encrypted metadata exists.
4. Commit/push and let Flux decrypt at apply time.

---

## Examples

### Example 1: Edit Existing Secret In Place

```bash
sops kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml
```

### Example 2: Create and Encrypt New Secret

```bash
cat > kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml << 'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: my-app-secret
  namespace: {namespace}
stringData:
  password: "replace-me"
EOF
sops -e -i kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml
```

---

## Verification Tests

### Test 1: File Contains SOPS Metadata

```bash
head -20 kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml | grep "sops:"
```

Expected:
- Output contains `sops:` metadata block.

If failed:
- File is not encrypted; run `sops -e -i`.

### Test 2: Flux Decryption Prerequisite Exists

```bash
kubectl get secret sops-age -n flux-system
```

Expected:
- `sops-age` secret exists.

If failed:
- Recreate/update SOPS age secret via GitOps path.

---

## File Naming Convention

All encrypted files MUST include the `.sops` suffix. In this repository, prefer `.sops.yaml`:

- ✅ `secret.sops.yaml`
- ✅ `configmap.sops.yaml`
- ✅ `secret.sops.json`
- ❌ `secret.yaml` (never commit unencrypted)

---

## SOPS Path Rules (`.sops.yaml`)

```yaml
creation_rules:
  - path_regex: talos/.*\.sops\.ya?ml
    mac_only_encrypted: true      # Entire file encrypted
    key_groups:
      - age:
          - "age1nw624gkjpl0sattullahnekdswjcvsgarf8gwwyf9jdqc0zm9enqyp2pf6"

  - path_regex: kubernetes/.*\.sops\.ya?ml
    encrypted_regex: "^(data|stringData)$"  # Only data/stringData fields
    mac_only_encrypted: true
    key_groups:
      - age:
          - "age1nw624gkjpl0sattullahnekdswjcvsgarf8gwwyf9jdqc0zm9enqyp2pf6"
```

**CRITICAL:** SOPS creation rules are path-based. You MUST encrypt files that are already
in the correct repository path. Encrypting from `/tmp/` will fail with
`error loading config: no matching creation rules found`.

---

## Common Operations

### Edit an Encrypted File

Opens the file in `$EDITOR`, decrypts in memory, re-encrypts on save:

```bash
sops kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml
```

This is the preferred method for small changes.

### View an Encrypted File

```bash
sops -d kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml
```

### Create a New Encrypted Secret

```bash
# 1. Create the plaintext file in the correct kubernetes/ path
cat > kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml << 'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: my-app-secret
  namespace: {namespace}
stringData:
  password: "my-strong-password"
  api-key: "my-api-key"
EOF

# 2. Encrypt in place (file must already be in kubernetes/ path)
sops -e -i kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml

# 3. Verify encryption
head -20 kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml | grep "sops:"
```

### Update an Existing Secret

**Method 1 — Direct edit (preferred for small changes):**
```bash
sops kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml
```

**Method 2 — Decrypt → edit → re-encrypt (for complex changes):**
```bash
# Decrypt to temp file
sops -d kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml > /tmp/secret.yaml

# Edit
nano /tmp/secret.yaml

# Copy to repo path (must be in kubernetes/)
cp /tmp/secret.yaml kubernetes/apps/{namespace}/{app}/app/secret-new.sops.yaml

# Encrypt in place
sops -e -i kubernetes/apps/{namespace}/{app}/app/secret-new.sops.yaml

# Replace original
mv kubernetes/apps/{namespace}/{app}/app/secret-new.sops.yaml \
   kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml

# Clean up temp file
rm /tmp/secret.yaml
```

### Verify a File is Encrypted

```bash
# Should show SOPS metadata block
head -20 kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml | grep "sops:"

# Should show placeholder values (not actual secrets)
grep "ENC\[" kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml | head -5
```

---

## Creating Kubernetes Secrets (Template)

All Kubernetes Secrets must be SOPS-encrypted before committing.

```yaml
# secret.sops.yaml (before encryption)
apiVersion: v1
kind: Secret
metadata:
  name: {app}-secret
  namespace: {namespace}
stringData:
  # Add your key-value pairs here
  # Generate strong passwords: openssl rand -base64 32
  DB_PASSWORD: "$(openssl rand -base64 32)"
  API_KEY: "your-api-key-here"
```

Then encrypt:
```bash
sops -e -i kubernetes/apps/{namespace}/{app}/app/secret.sops.yaml
```

**Always generate strong passwords:**
```bash
openssl rand -base64 32   # Strong random password
openssl rand -hex 32      # Hex format
python3 -c "import secrets; print(secrets.token_urlsafe(32))"  # URL-safe
```

---

## Flux SOPS Integration

Flux decrypts secrets using the age key stored as a cluster secret.

**Verify the age key is in the cluster:**
```bash
kubectl get secret sops-age -n flux-system
kubectl get secret sops-age -n flux-system -o jsonpath='{.data.age\.agekey}' | base64 -d | head -1
```

If the secret is missing, Flux cannot decrypt SOPS files and all secrets will fail.
Preferred approach (GitOps): update `kubernetes/flux/components/common/sops-age.sops.yaml` and let Flux reconcile.
Emergency break-glass only:
```bash
# Recreate the sops-age secret (only if missing)
kubectl create secret generic sops-age \
  --namespace flux-system \
  --from-file=age.agekey=${SOPS_AGE_KEY_FILE}
```

---

## Key Rotation (Rare — Use With Care)

If the age key needs to be rotated:

1. Generate new age key pair:
   ```bash
   age-keygen -o new.key
   cat new.key  # Copy public key from header comment
   ```

2. Update `.sops.yaml` with new public key

3. Re-encrypt all SOPS files with both old and new keys (allows transitional period):
   ```bash
   # Find all SOPS files
   find kubernetes/ talos/ -name "*.sops.yaml" | xargs -I{} sops updatekeys {}
   ```

4. Update `SOPS_AGE_KEY_FILE` in cluster and update the `sops-age` secret in `flux-system`

5. After all re-encryption confirmed working, remove old key from `.sops.yaml` and re-encrypt again

6. Update `docs/security.md` with new age key

---

## Verification and Auditing

```bash
# Find unencrypted Kubernetes Secret files (should return nothing)
grep -rl 'kind: Secret' kubernetes/ --include="*.yaml" | grep -v '\.sops\.yaml$'

# Find SOPS temp files left on disk
find kubernetes/ talos/ -name '.decrypted~*' -type f

# Verify all .sops.yaml files have SOPS metadata
find kubernetes/ talos/ -name "*.sops.yaml" | while read f; do
  if ! grep -q "sops:" "$f"; then
    echo "NOT ENCRYPTED: $f"
  fi
done

# Run full security audit
python3 runbooks/security-check.py
```

---

## Troubleshooting

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `no matching creation rules found` | File not in `kubernetes/` or `talos/` path | Move file to correct path before encrypting |
| `sops metadata not found` | File not yet encrypted | Use `sops -e -i` to encrypt first |
| `sops metadata not found` (after `sops --set`) | `--set` was used on plaintext file | Encrypt first or edit directly with `sops <file>` |
| `failed to get the data key required to decrypt the SOPS file` | Age key file missing or wrong path | Check `SOPS_AGE_KEY_FILE` env var |
| `failed to decrypt` | Wrong age key | Verify `SOPS_AGE_KEY_FILE` points to correct key |
| Flux `decryption failed` | `sops-age` secret missing in `flux-system` | `kubectl get secret sops-age -n flux-system` |

---

## Environment Setup

mise automatically sets `SOPS_AGE_KEY_FILE` when in the project directory:

```bash
echo $SOPS_AGE_KEY_FILE
# Should output: /home/mu/code/cberg-home-nextgen/age.key

# Verify key file exists and is readable
ls -la $SOPS_AGE_KEY_FILE

# Verify it can decrypt (test with known file)
sops -d kubernetes/flux/components/common/cluster-secrets.sops.yaml | grep "SECRET_DOMAIN"
```

---

## Diagnose Examples

### Diagnose Example 1: `no matching creation rules found`

```bash
pwd
ls -la /tmp
```

Expected:
- You identify file being encrypted outside `kubernetes/` or `talos/`.

If unclear:
- Move file into correct repo path and retry `sops -e -i`.

### Diagnose Example 2: Flux Decryption Fails

```bash
kubectl get secret sops-age -n flux-system
kubectl get kustomizations -A
kubectl get events -n flux-system --sort-by='.lastTimestamp' | tail -30
```

Expected:
- Missing/invalid age secret or reconciliation error is visible.

If unclear:
- Validate local key and re-encrypt target file.

---

## Health Check

```bash
# Validate all SOPS files still have metadata
find kubernetes/ talos/ -name "*.sops.yaml" | while read f; do
  grep -q "sops:" "$f" || echo "NOT ENCRYPTED: $f"
done
```

Expected:
- No `NOT ENCRYPTED` output.

---

## Security Check

```bash
# Find unencrypted Secret manifests
grep -rl 'kind: Secret' kubernetes/ --include="*.yaml" | grep -v '\.sops\.yaml$'
```

Expected:
- No plaintext Kubernetes Secret manifests are returned.

---

## Rollback Plan

```bash
# Revert problematic secret/key changes
git log -- .sops.yaml kubernetes/ talos/
git revert <commit-sha>
git push
```

Rollback validation:
- Re-run `Verification Tests` and `Health Check`.
