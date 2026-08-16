# Max Jung Transporte - Kubernetes Manifests

This directory contains Kubernetes manifests for deploying the Max Jung Transporte Fahrzeugcontrolling application to the `my-software-showcase` namespace.

## Files

- **deployment.yaml** - Main Deployment resource for the Rails application
  - Configures container image, resource requests/limits
  - Sets up liveness, readiness, and startup probes
  - Mounts volumes for tmp and log directories

- **service.yaml** - Kubernetes Service for internal routing
  - Exposes the application on port 80 (proxies to 3000)
  - Type: ClusterIP (internal only; use Ingress for external access)

- **secrets.yaml** - Kubernetes Secret for sensitive configuration
  - Database credentials (host, port, name, user, password)
  - Rails secret key base
  - **WARNING**: This file contains plaintext secrets and MUST be encrypted with SOPS before committing
  - See encryption instructions below

- **rbac.yaml** - Role, RoleBinding, and ServiceAccount
  - Defines minimal RBAC policy for the application
  - ServiceAccount allows pod to read secrets

- **helmrelease.yaml** - Helm Release for Flux CD
  - Defines desired Helm chart version and values
  - Used for GitOps-based deployments with Flux

- **image-automation.yaml** - Flux Image Automation resources
  - ImageRepository: monitors GHCR for new images
  - ImagePolicy: selects latest production-* tagged image
  - ImageUpdateAutomation: auto-updates deployment on new images

- **prometheus-rule.yaml** - Prometheus alerting rules
  - Monitors pod restarts, memory/CPU usage, pod status
  - Defines critical/warning severity alerts
  - Requires Prometheus Operator to be installed

## Pre-Deployment Setup

### 1. Encrypt Secrets with SOPS

The `secrets.yaml` file contains sensitive data and must be encrypted before committing to version control.

**Install SOPS:**
```bash
# macOS
brew install sops

# Linux
curl -Lo sops https://github.com/mozilla/sops/releases/download/v3.7.3/sops-v3.7.3.linux.amd64
chmod +x sops
sudo mv sops /usr/local/bin/
```

**Generate GPG Key (if not already done):**
```bash
gpg --gen-key  # Follow the prompts
gpg --export-secret-keys > ~/.gnupg/pubring.gpg
```

**Create .sops.yaml in the repo root:**
```yaml
creation_rules:
  - path_regex: k8s/secrets\.yaml
    pgp: 'YOUR_GPG_KEY_FINGERPRINT'
```

**Encrypt secrets.yaml:**
```bash
sops -e -i k8s/secrets.yaml
```

After encryption, the file will be YAML with encrypted values. Commit this file to version control.

### 2. Generate Rails Secret Key Base

```bash
cd /path/to/max-jung-transporte-fahrzeugcontrolling
bundle exec rails secret
```

Copy the output and replace `CHANGE_ME_IN_PRODUCTION` in `k8s/secrets.yaml` with the generated value.

### 3. Set Database Credentials

Update `k8s/secrets.yaml` with production database credentials:
- `db-host`: MySQL server hostname or IP
- `db-port`: MySQL port (default 3306)
- `db-name`: Production database name
- `db-user`: Database user
- `db-password`: Database password (strong password recommended)

### 4. Create GHCR Pull Secret (if using private registry)

If using a private GHCR registry, create a pull secret:

```bash
kubectl create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<github-token> \
  --docker-email=<email> \
  -n my-software-showcase
```

## Deployment Methods

### Option 1: Direct kubectl Apply

```bash
# Apply all manifests
kubectl apply -f k8s/

# Or apply individually
kubectl apply -f k8s/rbac.yaml
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/prometheus-rule.yaml
```

### Option 2: Kustomize

Create `kustomization.yaml` in the k8s/ directory:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: my-software-showcase

resources:
  - rbac.yaml
  - secrets.yaml
  - service.yaml
  - deployment.yaml
  - prometheus-rule.yaml
```

Then apply:
```bash
kubectl apply -k k8s/
```

### Option 3: Flux CD (GitOps)

Commit all manifests to your Flux repository, and Flux will automatically reconcile them.

## Post-Deployment Verification

### Check Deployment Status

```bash
kubectl get deployments -n my-software-showcase
kubectl get pods -n my-software-showcase
kubectl get svc -n my-software-showcase
```

### View Logs

```bash
kubectl logs -f deployment/max-jung -n my-software-showcase
```

### Test Health Endpoints

```bash
# Port-forward to access the service
kubectl port-forward svc/max-jung 3000:80 -n my-software-showcase

# In another terminal, test health endpoints
curl http://localhost:3000/health/liveness
curl http://localhost:3000/health/readiness
curl http://localhost:3000/health/startup
```

### Run Database Migrations

```bash
# Get pod name
POD_NAME=$(kubectl get pod -l app=max-jung -o jsonpath='{.items[0].metadata.name}' -n my-software-showcase)

# Run migration
kubectl exec -it $POD_NAME -n my-software-showcase -- bundle exec rake db:migrate

# Load seed data (optional)
kubectl exec -it $POD_NAME -n my-software-showcase -- bundle exec rake db:seed
```

## Monitoring

Prometheus alerts are defined in `prometheus-rule.yaml`. These require Prometheus Operator to be installed in the cluster.

To view alert status:
```bash
kubectl get prometheusrule max-jung -n my-software-showcase
kubectl describe prometheusrule max-jung -n my-software-showcase
```

## Troubleshooting

### Pod not starting

```bash
# Check pod events
kubectl describe pod -l app=max-jung -n my-software-showcase

# Check logs
kubectl logs -f deployment/max-jung -n my-software-showcase

# Check readiness probe
kubectl get pod -l app=max-jung -o wide -n my-software-showcase
```

### Database connection issues

```bash
# Verify secrets are correctly set
kubectl get secret max-jung-secrets -n my-software-showcase -o yaml

# Check database connectivity from pod
kubectl exec -it <pod-name> -n my-software-showcase -- \
  mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD -D $DB_NAME -e "SELECT 1;"
```

### Image pull failures

```bash
# Check image pull secret
kubectl get secret ghcr-pull-secret -n my-software-showcase

# Check pod events for ImagePullBackOff
kubectl describe pod -l app=max-jung -n my-software-showcase
```

## Resource Requests/Limits

Current defaults (from deployment.yaml):
- **Requests**: 256Mi memory, 100m CPU
- **Limits**: 1Gi memory, 500m CPU

These are conservative estimates suitable for staging/testing. Adjust based on actual usage monitoring.

## Related Documentation

- **Deployment Guide**: See `/home/mu/code/ib/apps/CLAUDE.md` for orchestration context
- **Application README**: See `../README.md` for application-specific details
- **Dockerfile**: See `../Dockerfile` for container image details
