# Zuhause-Betreut-Caretakermanager Deployment Checklist

## Overview
This checklist outlines the steps required to fully deploy the zuhause-betreut-caretakermanager application to the Kubernetes cluster. The manifests are staged and ready, but secrets must be encrypted with SOPS before deployment can proceed.

---

## Phase 1: Secrets Encryption

### 1.1 Encrypt Application Secrets (`secret.sops.yaml`)

**File Location:** `kubernetes/apps/my-software-showcase/zuhause-betreut/app/secret.sops.yaml`

**Current State:** Contains placeholder values

**Required Values:**
- `DATABASE_URL`: Database connection string following the format:
  - For MySQL/MariaDB: `mysql://[username]:[password]@[host]:[port]/[database]`
  - For PostgreSQL: `postgresql://[username]:[password]@[host]:[port]/[database]`
  - See deployment guide for specific K8s service endpoints

- `SECRET_KEY_BASE`: Rails secret key base for session encryption
  - **Current placeholder:** `placeholder_secret_key_base_replace_with_real_key_from_rails_secret`
  - **Generate with:** `rails secret` (if Rails is available) or `openssl rand -hex 32`

**Encryption Steps:**
1. Navigate to the repository root: `cd /home/mu/code/cberg-home-nextgen`
2. Update the secret values in `secret.sops.yaml`:
   ```bash
   sops kubernetes/apps/my-software-showcase/zuhause-betreut/app/secret.sops.yaml
   ```
3. SOPS will decrypt the file, allowing you to edit
4. Update the `DATABASE_URL` and `SECRET_KEY_BASE` with real values
5. Save and exit the editor
6. SOPS will automatically re-encrypt and save the file
7. Verify encryption with: `sops -d kubernetes/apps/my-software-showcase/zuhause-betreut/app/secret.sops.yaml` (should show the real values when decrypted)

### 1.2 Encrypt GHCR Registry Secret (`ghcr-secret.sops.yaml`)

**File Location:** `kubernetes/apps/my-software-showcase/zuhause-betreut/app/ghcr-secret.sops.yaml`

**Current State:** Contains placeholder `.dockerconfigjson`

**Purpose:** Allows Kubernetes to pull Docker images from GitHub Container Registry (GHCR)

**Prerequisites:**
- GitHub Personal Access Token (PAT) with `read:packages` scope
- Docker CLI access (for `docker login`)

**Steps to Generate and Encrypt:**
1. Create/retrieve your GitHub PAT with `read:packages` scope from: https://github.com/settings/tokens/new

2. Login to GHCR locally:
   ```bash
   echo $GITHUB_TOKEN | docker login ghcr.io -u <your-github-username> --password-stdin
   ```
   Replace `<your-github-username>` with your actual GitHub username

3. Extract the Docker config:
   ```bash
   cat ~/.docker/config.json | base64 -w0
   ```
   Or directly use the config JSON

4. Edit the secret file:
   ```bash
   sops kubernetes/apps/my-software-showcase/zuhause-betreut/app/ghcr-secret.sops.yaml
   ```

5. Replace the `.dockerconfigjson` value with the actual Docker config JSON

6. Save and exit; SOPS will re-encrypt automatically

**Important Note:** This secret is shared across all apps in the `my-software-showcase` namespace. Only create once; all apps reference the same secret.

---

## Phase 2: Image Registry Setup

### 2.1 Verify GitHub Container Registry Access

- **Repository:** `ghcr.io/ibdigital/zuhause-betreut-caretakermanager`
- **Image Tag Format:** `production-YYYYMMDDHHMMSS` (e.g., `production-20260816000000`)
- **Current Tag in Manifest:** `production-20260816000000`

**Verification Steps:**
1. Confirm the GitHub PAT has `read:packages` scope
2. Test GHCR access locally:
   ```bash
   docker pull ghcr.io/ibdigital/zuhause-betreut-caretakermanager:production-20260816000000
   ```
3. Verify the image exists and is accessible

### 2.2 Update Image Tag if Needed

If a newer image is available:
1. Update the `tag` field in `helmrelease.yaml` under:
   ```yaml
   spec.values.controllers.zuhause-betreut.containers.app.image.tag
   ```
2. Flux ImageUpdateAutomation will handle automatic updates for new `production-*` tags

---

## Phase 3: Database Configuration

### 3.1 Database Name and Credentials

**Database Name:** 
- Development: `showcase_zuhause_betreut_dev`
- Production: `showcase_zuhause_betreut_prod` (adjust as needed)

**Database User Credentials:**
- **Username:** `showcase_user`
- **Password:** [Set in encrypted `secret.sops.yaml` → `DATABASE_URL`]
- **Host:** `mariadb.databases.svc.cluster.local` (if using MariaDB) or PostgreSQL service endpoint
- **Port:** `3306` (MySQL/MariaDB) or `5432` (PostgreSQL)

**Ensure the database and user are created before deployment:**
```bash
# Example MariaDB setup (run this on your database server/pod)
CREATE DATABASE showcase_zuhause_betreut_dev;
CREATE USER 'showcase_user'@'%' IDENTIFIED BY 'PASSWORD';
GRANT ALL PRIVILEGES ON showcase_zuhause_betreut_dev.* TO 'showcase_user'@'%';
FLUSH PRIVILEGES;
```

---

## Phase 4: Verification and Validation

### 4.1 Validate Kustomize Build

Before deploying, ensure the manifests build correctly:
```bash
cd /home/mu/code/cberg-home-nextgen
kustomize build kubernetes/apps/my-software-showcase | head -50
```

Expected output should include:
- `kind: Namespace` with name `my-software-showcase`
- `kind: Secret` for `ghcr-secret` (encrypted)
- `kind: Secret` for `zuhause-betreut-secrets` (encrypted)
- `kind: HelmRelease` for `zuhause-betreut`
- `kind: ImageRepository`, `ImagePolicy`, `ImageUpdateAutomation` resources

### 4.2 Check Ingress Domain

The ingress is configured to use the cluster secret domain:
```yaml
hosts:
  - host: "zuhause-betreut.${SECRET_DOMAIN}"
```

**Verify:**
1. The `${SECRET_DOMAIN}` variable is defined in cluster-secrets (check kustomize build output)
2. DNS is configured to resolve `zuhause-betreut.${SECRET_DOMAIN}` to the cluster ingress

### 4.3 Verify Security Settings

Manifests include:
- **Pod Security Context:** Non-root user (UID/GID 1000), read-only filesystem where applicable
- **Image Pull Secret:** `ghcr-secret` for GHCR authentication
- **Health Probes:** Liveness, readiness, and startup probes configured for Rails app
- **Resource Limits:** Memory limit 1Gi, CPU requests 100m

---

## Phase 5: Deployment

### 5.1 Commit Encrypted Secrets

Once secrets are encrypted:
```bash
cd /home/mu/code/cberg-home-nextgen
git add kubernetes/apps/my-software-showcase/zuhause-betreut/app/secret.sops.yaml
git add kubernetes/apps/my-software-showcase/zuhause-betreut/app/ghcr-secret.sops.yaml
git add kubernetes/apps/my-software-showcase/
git commit -m "chore(zuhause-betreut): add encrypted secrets and kustomization"
git push origin main
```

### 5.2 Flux Automatic Reconciliation

Once committed and pushed:
1. Flux will automatically detect changes in the Git repository
2. The Kustomization resource will be reconciled
3. Secrets will be decrypted using the cluster's AGE key
4. The HelmRelease will deploy the application

Monitor deployment:
```bash
kubectl get all -n my-software-showcase
kubectl logs -n my-software-showcase deployment/zuhause-betreut -f
```

### 5.3 Verify Deployment

**Check pod status:**
```bash
kubectl get pods -n my-software-showcase -l app.kubernetes.io/name=zuhause-betreut
```

**Check logs:**
```bash
kubectl logs -n my-software-showcase -l app.kubernetes.io/name=zuhause-betreut -f
```

**Verify application is healthy:**
```bash
# Port-forward to test locally
kubectl port-forward -n my-software-showcase svc/zuhause-betreut 3000:3000
curl http://localhost:3000/health/readiness
```

**Check ingress:**
```bash
kubectl get ingress -n my-software-showcase
```

---

## Phase 6: Credential Rotation and Maintenance

### 6.1 Scheduled Secret Rotation

**Credentials that should be rotated regularly:**
1. `SECRET_KEY_BASE` - Rotate every 6-12 months
2. `DATABASE_URL` password - Rotate every 3-6 months
3. GHCR token - Rotate as per your organization's security policy

**Rotation Procedure:**
1. Generate new credentials
2. Update the encrypted secret file: `sops kubernetes/apps/my-software-showcase/zuhause-betreut/app/secret.sops.yaml`
3. Update database password in your database server
4. Commit and push changes
5. Flux will automatically reconcile within 30 minutes (or trigger manually)
6. Application may need to restart for new secrets to take effect

### 6.2 Secret Backup

- Keep backup copies of:
  - The actual (unencrypted) `SECRET_KEY_BASE` value
  - Database user credentials
  - GHCR token
- Store backups in a secure location (password manager, vault, etc.)
- **Do NOT commit unencrypted secrets to Git**

---

## Phase 7: Post-Deployment Troubleshooting

### 7.1 Common Issues

**Issue: ImagePullBackOff error**
- **Cause:** GHCR credentials not properly encrypted or pod can't access `ghcr-secret`
- **Solution:** 
  1. Verify `ghcr-secret` exists: `kubectl get secret ghcr-secret -n my-software-showcase`
  2. Check secret content: `kubectl get secret ghcr-secret -n my-software-showcase -o jsonpath='{.data}'`
  3. Re-encrypt and redeploy if needed

**Issue: CrashLoopBackOff or failed startup probes**
- **Cause:** Application can't connect to database or missing `SECRET_KEY_BASE`
- **Solution:**
  1. Check logs: `kubectl logs -n my-software-showcase <pod-name>`
  2. Verify DATABASE_URL is correct: `kubectl get secret zuhause-betreut-secrets -n my-software-showcase -o jsonpath='{.data.DATABASE_URL}' | base64 -d`
  3. Test database connectivity from pod or jump host
  4. Verify database exists and user has correct permissions

**Issue: 502 Bad Gateway on ingress**
- **Cause:** Service or pods not available
- **Solution:**
  1. Check pod status: `kubectl get pods -n my-software-showcase`
  2. Check service: `kubectl get svc -n my-software-showcase`
  3. Check ingress: `kubectl describe ingress -n my-software-showcase`

### 7.2 Useful Debug Commands

```bash
# Get full manifest
kubectl get kustomization zuhause-betreut -n my-software-showcase -o yaml

# Check helm release status
kubectl get helmrelease -n my-software-showcase

# Describe helm release for events
kubectl describe helmrelease zuhause-betreut -n my-software-showcase

# Get pod events
kubectl describe pod -n my-software-showcase <pod-name>

# Check resource limits
kubectl top pods -n my-software-showcase
```

---

## Summary Checklist

- [ ] **Phase 1:** Encrypt `secret.sops.yaml` with real DATABASE_URL and SECRET_KEY_BASE
- [ ] **Phase 1:** Encrypt `ghcr-secret.sops.yaml` with real GHCR credentials
- [ ] **Phase 2:** Verify GHCR access and image availability
- [ ] **Phase 3:** Database created and user credentials set
- [ ] **Phase 4:** Run `kustomize build` validation
- [ ] **Phase 4:** Verify `${SECRET_DOMAIN}` is configured in cluster secrets
- [ ] **Phase 4:** Review security context and resource limits
- [ ] **Phase 5:** Commit encrypted secrets to Git
- [ ] **Phase 5:** Push to main branch
- [ ] **Phase 5:** Monitor Flux reconciliation
- [ ] **Phase 6:** Application pods are running and healthy
- [ ] **Phase 6:** Ingress is responding with application
- [ ] **Phase 7:** Document any credential rotation schedule

---

## Support and Questions

For issues with:
- **SOPS Encryption:** Check `.sops.yaml` configuration and AGE key in cluster
- **Flux Deployment:** Review Flux Kustomization and HelmRelease status
- **Application Health:** Check Rails logs and health endpoints
- **Database Connectivity:** Verify DNS resolution and network policies

---

**Last Updated:** 2026-08-16
**Deployment Status:** Ready for Secrets Encryption Phase
