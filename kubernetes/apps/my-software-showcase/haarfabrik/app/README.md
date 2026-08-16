# Kubernetes Manifests for Haarfabrik Extranet

This directory contains Kubernetes manifests for deploying the Haarfabrik Extranet Rails application to the `my-software-showcase` cluster.

## Files

- **namespace.yaml**: Creates the `my-software-showcase` namespace
- **deployment.yaml**: Main Deployment resource with health checks, resource limits, and security policies
- **service.yaml**: Service exposing port 3000 for cluster-internal traffic
- **configmap.yaml**: Non-sensitive configuration (database host, port, logging level)
- **secrets.sops.yaml**: Encrypted secrets template (database credentials, SECRET_KEY_BASE)
- **rbac.yaml**: RBAC resources (ServiceAccount, Role, RoleBinding)
- **servicemonitor.yaml**: Prometheus monitoring configuration and alerting rules

## Deployment Steps

### 1. Set up encrypted secrets (SOPS)

First, prepare your secrets file with actual values:

```bash
# Install SOPS if not already installed
# Copy the template
cp k8s/secrets.sops.yaml k8s/secrets.yaml

# Edit with actual values (not in template)
vim k8s/secrets.yaml
# Update:
#   db.username: actual_db_user
#   db.password: actual_db_password
#   secret.key.base: $(rails secret)

# Encrypt with SOPS (requires KMS or age key)
sops -e -i k8s/secrets.yaml
```

### 2. Apply manifests to cluster

```bash
# Apply namespace and base resources
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/rbac.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml

# Apply deployment and service
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# If Prometheus is available, apply monitoring
kubectl apply -f k8s/servicemonitor.yaml
```

### 3. Verify deployment

```bash
# Check pods
kubectl -n my-software-showcase get pods -l app=haarfabrik

# Check pod logs
kubectl -n my-software-showcase logs -f deployment/haarfabrik

# Check service
kubectl -n my-software-showcase get svc haarfabrik

# Test health endpoints
kubectl -n my-software-showcase port-forward svc/haarfabrik 3000:3000
curl http://localhost:3000/health
curl http://localhost:3000/health/ready
curl http://localhost:3000/health/live
```

## Environment Variables

The deployment uses environment variables from ConfigMap and Secrets:

### From ConfigMap (haarfabrik-config)
- `DB_HOST`: Database host (default: mysql)
- `DB_PORT`: Database port (default: 3306)
- `DB_DATABASE`: Database name (default: showcase_haarfabrik_prod)
- `RAILS_LOG_LEVEL`: Rails logging level (default: info)

### From Secrets (haarfabrik-secrets)
- `DB_USERNAME`: Database user
- `DB_PASSWORD`: Database password
- `SECRET_KEY_BASE`: Rails secret key for session encryption

## Health Checks

The deployment includes three health check endpoints:

- **Liveness** (`/health/live`): Returns 200 if the process is alive. Kubernetes restarts the pod if this fails.
- **Readiness** (`/health/ready`): Returns 200 if the app is ready to receive traffic (checks database connectivity).
- **Startup** (`/health/startup`): Returns 200 when the app is fully initialized.

## Resource Limits

```
Requests:
  Memory: 256Mi
  CPU: 100m

Limits:
  Memory: 1Gi
  CPU: 500m
```

Adjust these based on your actual usage patterns.

## Database Migration

To run database migrations on deployment:

```bash
# Before first deployment, ensure database is created
kubectl -n my-software-showcase run haarfabrik-migrate \
  --image=ghcr.io/nachtschatt3n/haarfabrik-extranet:latest \
  --restart=Never \
  -- bundle exec rake db:create db:migrate db:seed
```

Or add an init container to the deployment to run migrations automatically.

## Flux Image Automation

The deployment uses `ghcr.io/nachtschatt3n/haarfabrik-extranet:latest` which can be automated with Flux:

```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImagePolicy
metadata:
  name: haarfabrik
  namespace: my-software-showcase
spec:
  imageRepositoryRef:
    name: haarfabrik
  policy:
    semver:
      range: ">=0.0.0"
```

The CI/CD pipeline automatically builds and pushes new images with `production-YYYYMMDDHHMMSS` tags, which Flux can pick up and deploy.

## Monitoring Alerts

The ServiceMonitor and PrometheusRule define alerts for:

- Pod restarting frequently (>0.1 restarts/15min)
- High memory usage (>90% of limit)
- High CPU usage (>80% of limit)
- Pod not ready for >3 minutes
- Pod in CrashLoopBackOff state
- Deployment has no replicas

## Troubleshooting

### Pod not starting

Check logs:
```bash
kubectl -n my-software-showcase logs deployment/haarfabrik
```

Check events:
```bash
kubectl -n my-software-showcase describe pod -l app=haarfabrik
```

### Database connection errors

Verify ConfigMap and Secrets:
```bash
kubectl -n my-software-showcase get cm haarfabrik-config
kubectl -n my-software-showcase get secret haarfabrik-secrets
```

Check database is accessible:
```bash
kubectl -n my-software-showcase run mysql-test \
  --image=mysql:5.7 \
  --rm -it \
  -- mysql -h mysql -u <username> -p<password> showcase_haarfabrik_prod
```

### Memory/CPU throttling

Check usage:
```bash
kubectl -n my-software-showcase top pods -l app=haarfabrik
```

Increase resource limits in deployment.yaml and apply:
```bash
kubectl apply -f k8s/deployment.yaml
```

## Links

- **GitHub Repo**: https://github.com/ibdigital/haarfabrik-extranet
- **Container Registry**: ghcr.io/nachtschatt3n/haarfabrik-extranet
- **Cluster**: my-software-showcase namespace
- **Flux Repo**: git@github.com:ibdigital/my-software-showcase-k8s.git
