# Flux GitOps Deployment Guide: My Software Showcase

This guide provides step-by-step instructions for deploying all 15 containerized legacy applications to the `my-software-showcase` Kubernetes namespace using Flux GitOps.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [SOPS Encryption Setup](#sops-encryption-setup)
3. [GHCR Image Pull Secret Setup](#ghcr-image-pull-secret-setup)
4. [Database Initialization](#database-initialization)
5. [Flux Reconciliation](#flux-reconciliation)
6. [Verification & Health Checks](#verification--health-checks)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before beginning deployment, ensure you have:

- **Kubernetes cluster** running with `my-software-showcase` namespace created:
  ```bash
  kubectl create namespace my-software-showcase
  ```

- **Flux** installed and configured:
  ```bash
  flux --version
  ```

- **SOPS** installed locally for secret management:
  ```bash
  sops --version
  ```

- **Age** key generator installed:
  ```bash
  age --version
  ```

- **kubectl** configured with cluster access:
  ```bash
  kubectl cluster-info
  ```

- **Git** repository access to the homelab repo:
  ```bash
  git clone https://github.com/yourusername/cberg-home-nextgen.git
  ```

- **MariaDB** running in `databases` namespace at `mariadb.databases.svc.cluster.local:3306`

- **GitHub Container Registry** access with personal access token

---

## SOPS Encryption Setup

### Step 1: Install Age on Your Local Machine

Age is used for SOPS encryption. Install it:

**macOS:**
```bash
brew install age
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt-get install age
```

**Linux (Alpine):**
```bash
apk add age
```

### Step 2: Verify SOPS Configuration

The repository already has `.sops.yaml` configured with the Age public key:

```bash
cat .sops.yaml | grep age1
```

You should see:
```
age1nw624gkjpl0sattullahnekdswjcvsgarf8gwwyf9jdqc0zm9enqyp2pf6
```

### Step 3: Install Age Private Key in Cluster

The Age private key must be installed in the cluster for Flux to decrypt secrets.

**Generate a new Age keypair (if needed):**
```bash
age-keygen -o age-key.txt
```

**Extract the public key and update `.sops.yaml`** (if using new key):
```bash
grep "public key:" age-key.txt
```

**Install the private key in the cluster as a Kubernetes secret:**
```bash
kubectl create secret generic sops-age \
  --from-file=age.agekey=age-key.txt \
  -n flux-system
```

**Verify the secret was created:**
```bash
kubectl get secret sops-age -n flux-system
```

### Step 4: Configure Flux to Use SOPS

Flux needs to know to decrypt SOPS-encrypted files. This is typically done in Kustomization resources.

Check if your Flux `GitRepository` and `Kustomization` resources are configured:

```bash
kubectl get kustomizations -n flux-system
```

Ensure your app Kustomizations reference the SOPS secret (example):

```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: my-software-showcase
spec:
  decryption:
    provider: sops
    secretRef:
      name: sops-age
```

---

## GHCR Image Pull Secret Setup

### Step 1: Create GitHub Personal Access Token (PAT)

1. Go to https://github.com/settings/tokens
2. Click **"Generate new token (classic)"**
3. Give it a name: `GHCR read:packages`
4. Select scopes:
   - `repo` (full control)
   - `read:packages`
   - `workflow`
5. Click **"Generate token"**
6. **Copy and save the token** (you won't be able to see it again)

### Step 2: Create Docker Config

Authenticate with GitHub Container Registry:

```bash
docker login ghcr.io -u YOUR_GITHUB_USERNAME -p YOUR_PERSONAL_ACCESS_TOKEN
# When prompted for password, paste the PAT
```

**Extract the base64-encoded config:**

```bash
cat ~/.docker/config.json | base64 -w 0
# Copy the entire output (it's very long)
```

### Step 3: Update GHCR Secret Template

Edit the GHCR secret file:

```bash
sops kubernetes/apps/my-software-showcase/_shared/ghcr-secret.sops.yaml
```

Replace the placeholder:
```yaml
stringData:
  .dockerconfigjson: PLACEHOLDER_DOCKERCONFIGJSON_ENCRYPT_WITH_SOPS_BEFORE_COMMITTING
```

With your base64-encoded config:
```yaml
stringData:
  .dockerconfigjson: eyJh...[very long base64 string]...==
```

**Save the file** (SOPS will auto-encrypt on close).

### Step 4: Verify Encryption

Confirm the file is encrypted:

```bash
sops kubernetes/apps/my-software-showcase/_shared/ghcr-secret.sops.yaml
```

You should see encrypted data, then the decrypted values. When you save and exit, it re-encrypts.

### Step 5: Commit to Git

```bash
git add kubernetes/apps/my-software-showcase/_shared/ghcr-secret.sops.yaml
git commit -m "chore: encrypt GHCR secret for image pull authentication"
git push
```

### Step 6: Flux Applies the Secret

Flux will automatically decrypt and apply the secret when it reconciles the Kustomization:

```bash
flux reconcile kustomization my-software-showcase -n flux-system
```

Verify the secret was created:

```bash
kubectl get secret ghcr-secret -n my-software-showcase
kubectl describe secret ghcr-secret -n my-software-showcase
```

---

## Database Initialization

### Step 1: Create Required Databases

All 15 apps require dedicated databases. See `/kubernetes/apps/my-software-showcase/_shared/database-init.yaml` for the full list.

**Option A: Manual Database Creation**

Connect to MariaDB and create databases:

```bash
# Port-forward to MariaDB (if in different namespace)
kubectl port-forward -n databases svc/mariadb 3306:3306 &

# Connect to MySQL
mysql -h localhost -P 3306 -u root -p

# Run SQL commands (see database-init.yaml for full list)
CREATE DATABASE showcase_zuhause_betreut_prod CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE showcase_inbewegung_prod CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE showcase_kfa_medienarchiv_prod CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
# ... (continue for all 15 apps)

CREATE USER 'showcase_app'@'%' IDENTIFIED BY 'SECURE_PASSWORD_HERE';
GRANT ALL PRIVILEGES ON showcase_*.* TO 'showcase_app'@'%';
FLUSH PRIVILEGES;
```

**Option B: Automated Database Creation via Kubernetes Job**

Uncomment and apply the Job in `database-init.yaml` (requires MariaDB root credentials stored as secret).

### Step 2: Update App Secrets with Database Credentials

For each app, update the encrypted secrets with actual database password:

```bash
# For each app (inbewegung, metaldyne, u-zeit, stepbystepguide, ordiga, etc.)
sops kubernetes/apps/my-software-showcase/APPNAME/app/secret.sops.yaml
```

Update:
```yaml
stringData:
  DATABASE_PASSWORD: PLACEHOLDER_ENCRYPTED_DB_PASSWORD_REPLACE_WITH_ACTUAL_PASSWORD
  SECRET_KEY_BASE: PLACEHOLDER_ENCRYPTED_RAILS_SECRET_KEY_REPLACE_WITH_ACTUAL_KEY
```

With actual values:
```yaml
stringData:
  DATABASE_PASSWORD: your_actual_db_password
  SECRET_KEY_BASE: rails-secret-key-from-rails-secret-command
```

Generate Rails secret if needed:
```bash
docker run --rm ruby:latest rails secret
# Or if you have Rails locally:
rails secret
```

**Save and commit all secret files:**

```bash
git add kubernetes/apps/my-software-showcase/*/app/secret.sops.yaml
git commit -m "chore: encrypt app-specific database and Rails secrets"
git push
```

---

## Flux Reconciliation

### Step 1: Create Root Kustomization (if not exists)

The repository should already have all Kustomization resources defined. Verify:

```bash
kubectl get kustomizations -n flux-system
flux get kustomizations -n flux-system
```

### Step 2: Reconcile the My Software Showcase Namespace

Trigger an immediate reconciliation:

```bash
flux reconcile kustomization my-software-showcase -n flux-system
```

Monitor the reconciliation:

```bash
flux get kustomizations -n flux-system --watch
```

### Step 3: Monitor Individual App Deployments

Watch pods being created:

```bash
kubectl get pods -n my-software-showcase -w
```

### Step 4: Check HelmReleases

View the status of all HelmReleases:

```bash
kubectl get helmreleases -n my-software-showcase
flux get helmreleases -n my-software-showcase
```

### Step 5: View Flux Logs

If any reconciliation fails:

```bash
flux logs --all-namespaces --follow
```

For a specific app:

```bash
flux logs -n my-software-showcase --follow
```

---

## Verification & Health Checks

### Step 1: Pod Status

Verify all pods are running:

```bash
kubectl get pods -n my-software-showcase
```

Expected output (for all 15 apps):
```
NAME                                        READY   STATUS    RESTARTS   AGE
zuhause-betreut-xxxxxxxxxx-xxxxx            1/1     Running   0          2m
inbewegung-xxxxxxxxxx-xxxxx                 1/1     Running   0          2m
kfa-medienarchiv-xxxxxxxxxx-xxxxx           1/1     Running   0          2m
... (all 15 apps)
```

### Step 2: Check Pod Logs

For any failing pod:

```bash
kubectl logs -n my-software-showcase -l app.kubernetes.io/name=APPNAME
kubectl describe pod -n my-software-showcase <pod-name>
```

### Step 3: Verify Secret Decryption

Confirm secrets were decrypted correctly:

```bash
kubectl get secrets -n my-software-showcase
kubectl get secret ghcr-secret -n my-software-showcase
kubectl get secret inbewegung-secrets -n my-software-showcase
```

### Step 4: Test Ingress Access

If ingress is configured, test app access:

```bash
kubectl get ingress -n my-software-showcase
```

Try accessing via the configured domain:
```bash
curl https://zuhause-betreut.${SECRET_DOMAIN}
curl https://inbewegung.${SECRET_DOMAIN}
```

### Step 5: Check Resource Metrics (if Prometheus installed)

```bash
kubectl top pods -n my-software-showcase
```

### Step 6: Database Connectivity Test

Verify apps can connect to the database by checking pod logs:

```bash
kubectl logs -n my-software-showcase -l app.kubernetes.io/name=zuhause-betreut
```

Look for successful database connection messages.

---

## Troubleshooting

### Flux Reconciliation Failures

**Check Kustomization status:**
```bash
flux get kustomizations -n flux-system --status
```

**View detailed error:**
```bash
flux get kustomization my-software-showcase -n flux-system --verbose
```

**Check Git repository status:**
```bash
flux get sources git -n flux-system
```

### SOPS Decryption Errors

**Error: `could not decrypt`**

- Verify Age key is installed:
  ```bash
  kubectl get secret sops-age -n flux-system
  ```

- Verify Kustomization has decryption configured:
  ```bash
  kubectl get kustomization -n flux-system -o yaml | grep -A5 decryption
  ```

- Re-encrypt files if Age key changed:
  ```bash
  sops -e -i kubernetes/apps/my-software-showcase/_shared/ghcr-secret.sops.yaml
  ```

### Image Pull Errors

**Error: `Failed to pull image`**

- Verify GHCR secret exists:
  ```bash
  kubectl get secret ghcr-secret -n my-software-showcase
  ```

- Check secret content (if decrypted):
  ```bash
  kubectl get secret ghcr-secret -n my-software-showcase -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d | jq
  ```

- Verify image exists in GHCR:
  ```bash
  docker pull ghcr.io/nachtschatt3n/zuhause-betreut-caretakermanager:production-20260816000000
  ```

### Database Connection Errors

**Error: `Access denied for user 'showcase_app'`**

- Verify database credentials in secret:
  ```bash
  sops kubernetes/apps/my-software-showcase/APPNAME/app/secret.sops.yaml
  ```

- Verify user exists in MariaDB:
  ```bash
  mysql -h mariadb.databases.svc.cluster.local -u root -p
  SELECT user, host FROM mysql.user WHERE user='showcase_app';
  ```

- Verify user has correct permissions:
  ```bash
  SHOW GRANTS FOR 'showcase_app'@'%';
  ```

**Error: `Can't connect to database server`**

- Verify MariaDB is running:
  ```bash
  kubectl get pods -n databases
  ```

- Verify network connectivity from pod:
  ```bash
  kubectl exec -it <app-pod> -n my-software-showcase -- \
    mysql -h mariadb.databases.svc.cluster.local -u showcase_app -p showcase_zuhause_betreut_prod -e "SELECT 1"
  ```

### Health Check Failures

**Error: `Liveness probe failed`**

- Check pod logs:
  ```bash
  kubectl logs -n my-software-showcase <pod-name>
  ```

- Verify the health endpoint is correct in HelmRelease:
  ```bash
  kubectl get helmrelease -n my-software-showcase APPNAME -o yaml | grep -A5 probes
  ```

- Test health endpoint manually:
  ```bash
  kubectl exec -it <pod-name> -n my-software-showcase -- curl -v http://localhost:3000/health/liveness
  ```

### Ingress Not Working

**Error: `404 Not Found` or `Connection Refused`**

- Verify ingress resource created:
  ```bash
  kubectl get ingress -n my-software-showcase
  ```

- Check ingress controller:
  ```bash
  kubectl get pods -n ingress-nginx
  ```

- Verify DNS resolution:
  ```bash
  nslookup zuhause-betreut.${SECRET_DOMAIN}
  ```

---

## Rollback & Recovery

### Rollback to Previous Version

If deployment fails, revert the Git commit:

```bash
git log --oneline -5
git revert <commit-hash>
git push
```

Flux will automatically reconcile and roll back pods.

### Manual Pod Restart

To restart an app:

```bash
kubectl rollout restart deployment/zuhause-betreut -n my-software-showcase
```

### Delete and Redeploy

To completely remove and redeploy an app:

```bash
kubectl delete all -l app.kubernetes.io/name=APPNAME -n my-software-showcase
flux reconcile kustomization my-software-showcase -n flux-system
```

---

## Monitoring & Observability

### View Flux Reconciliation History

```bash
flux get kustomizations -n flux-system --all-namespaces
flux logs -n flux-system --follow
```

### Check HelmRelease Status

```bash
kubectl get helmreleases -n my-software-showcase -o wide
kubectl describe helmrelease APPNAME -n my-software-showcase
```

### Monitor Image Automation

```bash
kubectl get imagerepository -n my-software-showcase
kubectl get imagepolicy -n my-software-showcase
kubectl get imageupdateautomation -n my-software-showcase
```

### View Event Logs

```bash
kubectl get events -n my-software-showcase --sort-by='.lastTimestamp'
```

---

## Next Steps

1. **Load Demo Data**: After apps are running, load seed/demo data using scripts from the source repositories
2. **Configure Monitoring**: Set up Prometheus scraping for apps with ServiceMonitor resources
3. **Enable HTTPS**: Ensure ingress certificates are configured via cert-manager
4. **Set Up Backups**: Configure database backup strategies for persistent data
5. **Security Hardening**: Review network policies, RBAC, and security context settings

---

## Support & References

- **Flux Documentation**: https://fluxcd.io/docs/
- **Kustomize Reference**: https://kustomize.io/
- **SOPS with Age**: https://fluxcd.io/docs/guides/mozilla-sops/
- **GitHub Container Registry**: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
- **Kubernetes Ingress**: https://kubernetes.io/docs/concepts/services-networking/ingress/

---

**Created**: 2026-08-16  
**Updated By**: Claude Code  
**Status**: Ready for deployment
