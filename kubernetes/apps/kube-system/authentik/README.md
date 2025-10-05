# Authentik Identity Provider

This directory contains the Flux configuration for deploying Authentik as an identity provider and SSO solution in the kube-system namespace.

## Overview

Authentik is deployed with the following configuration:
- **Version**: 2025.8.4
- **Namespace**: kube-system
- **Database**: External MariaDB (databases namespace)
- **Cache**: Internal Redis with Longhorn storage
- **Replicas**: 2 server pods, 2 worker pods
- **Ingress**: External ingress class at `auth.${SECRET_DOMAIN}` (accessible from internet)
- **Monitoring**: Prometheus ServiceMonitor enabled

## Pre-deployment Setup

### 1. Database Setup

Before deploying, you need to create the Authentik database in MariaDB:

```bash
# Connect to MariaDB
kubectl exec -it -n databases mariadb-0 -- mysql -u root -p

# Run the database setup (or use the provided SQL file)
source setup-database.sql
```

Alternatively, use the provided SQL setup script:
```bash
kubectl exec -i -n databases mariadb-0 -- mysql -u root -p < setup-database.sql
```

### 2. Update Secrets

Update the encrypted secrets with your actual values:

```bash
# Edit the secret file
sops kubernetes/apps/kube-system/authentik/app/secret.sops.yaml
```

Required secrets:
- `SECRET_AUTHENTIK_SECRET_KEY`: Generated automatically (keep the current value)
- `SECRET_AUTHENTIK_DB_PASSWORD`: Set to the password you used for the 'authentik' database user
- `SECRET_AUTHENTIK_GEOIP_ACCOUNT_ID`: Your MaxMind account ID (optional)
- `SECRET_AUTHENTIK_GEOIP_LICENSE_KEY`: Your MaxMind license key (optional)

### 3. Verify Dependencies

Ensure these components are deployed and healthy:
- Longhorn (storage namespace)
- MariaDB (databases namespace)
- Internal ingress controller

## Deployment

After completing the setup, Flux will automatically deploy Authentik. Monitor the deployment:

```bash
# Check Flux Kustomization
flux get kustomizations -n flux-system | grep authentik

# Check HelmRelease
flux get helmreleases -n kube-system authentik

# Check pods
kubectl get pods -n kube-system -l app.kubernetes.io/name=authentik
```

## Access

Once deployed, access Authentik at:
- **URL**: `https://auth.${SECRET_DOMAIN}`
- **Initial Setup**: Follow the Authentik setup wizard on first access

## Configuration

### Initial Admin User

On first access, Authentik will prompt you to create an initial admin user. Use a strong password and enable 2FA.

### Homepage Integration

The deployment includes Homepage annotations for dashboard integration:
- **Group**: Authentication  
- **Icon**: authentik.png
- **Description**: Identity Provider and SSO

### Monitoring

Prometheus metrics are enabled and available at:
- Server metrics: `/metrics` endpoint
- ServiceMonitor: `authentik` in kube-system namespace

## Troubleshooting

### Common Issues

1. **Database Connection Issues**
   - Verify MariaDB is running: `kubectl get pods -n databases`
   - Check database credentials in the secret
   - Ensure the authentik database and user exist

2. **Redis Issues**
   - Check Redis pods: `kubectl get pods -n kube-system -l app=redis`
   - Verify Longhorn storage is available

3. **Ingress Issues**
   - Verify external ingress controller is running
   - Check certificate generation
   - Confirm DNS resolution for auth.${SECRET_DOMAIN}
   - Verify Cloudflare Tunnel configuration for external access

### Logs

Check application logs:
```bash
# Server logs
kubectl logs -n kube-system -l app.kubernetes.io/name=authentik,app.kubernetes.io/component=server

# Worker logs  
kubectl logs -n kube-system -l app.kubernetes.io/name=authentik,app.kubernetes.io/component=worker

# Redis logs
kubectl logs -n kube-system -l app.kubernetes.io/name=redis
```

## Backup and Recovery

### Database Backup
Database backups are handled by your MariaDB backup strategy. The authentik database should be included in regular backups.

### Configuration Backup
Export Authentik configuration through the web interface:
1. Login as admin
2. Go to System → Backup & Restore
3. Export configuration

### Redis Data
Redis data is persisted to Longhorn volumes and included in Longhorn's backup strategy.

## Updating

To update Authentik:
1. Update the chart version in `helmrelease.yaml`
2. Commit and push changes
3. Flux will handle the rolling update

Check the [Authentik release notes](https://github.com/goauthentik/authentik/releases) for any breaking changes or migration steps.