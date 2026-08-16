# My Software Showcase - Deployment Status

This document tracks the deployment status of all 15 legacy applications being containerized and deployed to the `my-software-showcase` Kubernetes namespace using Flux GitOps.

## Deployment Overview

| # | Application | App ID | Repo | K8s Status | Flux Status | Notes |
|---|-------------|--------|------|-----------|------------|-------|
| 1 | Zuhause Betreut Caretakermanager | `zuhause-betreut` | https://github.com/ibdigital/zuhause-betreut-caretakermanager | Manifests Staged | Ready | K8s resources in place |
| 2 | Inbewegung Family Manager | `inbewegung` | https://github.com/ibdigital/inbewegung-familymanager | Awaiting Manifests | Pending | Source repo K8s generation needed |
| 3 | KFA Medienarchiv | `kfa-medienarchiv` | https://github.com/ibdigital/kfa_medienarchiv | Manifests Staged | Ready | K8s resources in place |
| 4 | Mangold Smart Home Advisor | `mangold-smarthomeadvisor` | https://github.com/ibdigital/mangold-smarthomeadvisor | Manifests Staged | Ready | K8s resources in place |
| 5 | Metaldyne Mini ERP | `metaldyne` | https://github.com/ibdigital/metaldyne-mini-erp | Awaiting Manifests | Pending | Source repo K8s generation needed |
| 6 | U-Zeit | `u-zeit` | https://github.com/ibdigital/u-zeit | Awaiting Manifests | Pending | Source repo K8s generation needed |
| 7 | Step By Step Guide | `stepbystepguide` | https://github.com/ibdigital/stepbystepguide | Awaiting Manifests | Pending | Source repo K8s generation needed |
| 8 | Holm Backend | `holm-backend` | https://github.com/ibdigital/holm-backend | Manifests Staged | Ready | K8s resources in place |
| 9 | See EDV IBSPM | `see-edv-ibspm` | https://github.com/ibdigital/see-edv-ibspm | Manifests Staged | Ready | K8s resources in place |
| 10 | Ordiga | `ordiga` | https://github.com/ibdigital/ordiga | Awaiting Manifests | Pending | Source repo K8s generation needed |
| 11 | Haarfabrik Extranet | `haarfabrik` | https://github.com/ibdigital/haarfabrik-extranet | Manifests Staged | Ready | K8s resources in place |
| 12 | Max Jung Fahrzeugcontrolling | `max-jung` | https://github.com/ibdigital/max-jung-transporte-fahrzeugcontrolling | Manifests Staged | Ready | K8s resources in place |
| 13 | IB Gastro | `ibgastro` | https://github.com/ibdigital/ibgastro | Manifests Staged | Ready | K8s resources in place |
| 14 | Globalmobility Group | `globalmobility` | https://github.com/ibdigital/globalmobility-group-gmbh-globaldispo.de | Manifests Staged | Ready | K8s resources in place |
| 15 | Uzeit.de | `uzeit-de` | https://github.com/ibdigital/uzeit.de | Manifests Staged | Ready | K8s resources in place |

## Summary

- **Total Apps**: 15
- **Kubernetes Namespace**: `my-software-showcase`
- **Flux GitOps Repository**: https://github.com/ibdigital/my-software-showcase-k8s.git
- **Container Registry**: ghcr.io/nachtschatt3n/*
- **Status**: 10 apps with manifests staged, 5 apps awaiting K8s generation

## Manifest Staging Status

### Successfully Staged (10 apps)

K8s manifests have been copied from source repositories into the homelab Flux repository:

1. **zuhause-betreut** (`/kubernetes/apps/my-software-showcase/zuhause-betreut/app/`)
   - Source: `/home/mu/code/ib/apps/zuhause-betreut-caretakermanager/k8s/*`
   - Includes: helmrelease, image-automation, secrets, service, deployment

2. **kfa-medienarchiv** (`/kubernetes/apps/my-software-showcase/kfa-medienarchiv/app/`)
   - Source: `/home/mu/code/ib/apps/kfa_medienarchiv/k8s/*`
   - Includes: helmrelease, image-automation, secrets, service

3. **mangold-smarthomeadvisor** (`/kubernetes/apps/my-software-showcase/mangold-smarthomeadvisor/app/`)
   - Source: `/home/mu/code/ib/apps/mangold-mangold-smarthomeadvisor/k8s/*`
   - Includes: helmrelease, image-automation, secrets, service

4. **holm-backend** (`/kubernetes/apps/my-software-showcase/holm-backend/app/`)
   - Source: `/home/mu/code/ib/apps/holm-backend/k8s/*`
   - Includes: deployment, helmrelease, image-automation, prometheus-rule, secrets, service

5. **see-edv-ibspm** (`/kubernetes/apps/my-software-showcase/see-edv-ibspm/app/`)
   - Source: `/home/mu/code/ib/apps/see-edv-ibspm/k8s/*`
   - Includes: configmap, deployment, image-automation, prometheus-rule, secrets, service

6. **haarfabrik** (`/kubernetes/apps/my-software-showcase/haarfabrik/app/`)
   - Source: `/home/mu/code/ib/apps/haarfabrik-extranet/k8s/*`
   - Includes: configmap, deployment, namespace, rbac, secrets (SOPS), servicemonitor

7. **max-jung** (`/kubernetes/apps/my-software-showcase/max-jung/app/`)
   - Source: `/home/mu/code/ib/apps/max-jung-transporte-fahrzeugcontrolling/k8s/*`
   - Includes: deployment, helmrelease, image-automation, prometheus-rule, rbac, secrets, service

8. **ibgastro** (`/kubernetes/apps/my-software-showcase/ibgastro/app/`)
   - Source: `/home/mu/code/ib/apps/ibgastro/k8s/*`
   - Includes: configmap, deployment, pvc, secrets, service

9. **globalmobility** (`/kubernetes/apps/my-software-showcase/globalmobility/app/`)
   - Source: `/home/mu/code/ib/apps/globalmobility-group-gmbh-globaldispo.de/k8s/*`
   - Includes: configmap, deployment, prometheus-rule, pvc, secrets, serviceaccount, service

10. **uzeit-de** (`/kubernetes/apps/my-software-showcase/uzeit-de/app/`)
    - Source: `/home/mu/code/ib/apps/uzeit.de/k8s/*`
    - Includes: configmap, deployment, image-automation, ingress, namespace, prometheus-rule, pvc, rbac, secrets, service

### Pending Manifest Generation (5 apps)

These apps require K8s manifests to be generated and added to source repositories:

1. **inbewegung** - Inbewegung Family Manager
   - Source: `/home/mu/code/ib/apps/inbewegung-familymanager/`
   - TODO: Generate K8s manifests (Rails 4.2.5, Ruby 2.1.7, MySQL)

2. **metaldyne** - Metaldyne Mini ERP
   - Source: `/home/mu/code/ib/apps/metaldyne-mini-erp/`
   - TODO: Generate K8s manifests (Rails 4.2.9, Ruby 2.4.5, MySQL)

3. **u-zeit** - U-Zeit
   - Source: `/home/mu/code/ib/apps/u-zeit/`
   - TODO: Generate K8s manifests (Rails 4.1.4, Ruby 2.3.0, MySQL)

4. **stepbystepguide** - Step By Step Guide
   - Source: `/home/mu/code/ib/apps/stepbystepguide/`
   - TODO: Generate K8s manifests (Rails 4.1.1, Ruby 2.3.1, MySQL)

5. **ordiga** - Ordiga
   - Source: `/home/mu/code/ib/apps/ordiga/`
   - TODO: Generate K8s manifests (Rails 3.2.16, Ruby 2.2.5, MySQL)

## Flux Reconciliation Configuration

Each app is configured as a Flux `Kustomization` resource with:

- **Namespace**: `my-software-showcase`
- **Source**: GitRepository `flux-system` (points to this homelab repo)
- **Path**: `./kubernetes/apps/my-software-showcase/<app-id>/app`
- **Reconciliation Interval**: 30 minutes
- **Retry Interval**: 1 minute
- **Timeout**: 5 minutes
- **Prune**: Enabled (deletes resources removed from Git)

Example: `/kubernetes/apps/my-software-showcase/holm-backend/ks.yaml`

## Next Steps

### Phase 1: SOPS Encryption Setup (All Apps)

Before applying manifests to cluster:

1. **Generate Age keypair** (if not exists):
   ```bash
   age-keygen -o age-key.txt
   ```

2. **Create SOPS encryption configuration** (`.sops.yaml` in repo root):
   ```yaml
   creation_rules:
     - path_regex: ".*secrets.*\\.sops\\.ya?ml$"
       encrypted_regex: "^(data|stringData)$"
       key_groups:
       - age: <age-key>
   ```

3. **Encrypt existing secret files**:
   For each app with `secrets.yaml` or `secret.yaml`:
   ```bash
   sops -e -i <app>/app/secrets.yaml
   # Rename to secrets.sops.yaml
   mv <app>/app/secrets.yaml <app>/app/secrets.sops.yaml
   ```

4. **Update kustomization.yaml** to reference `.sops.yaml` files

5. **Commit encrypted secrets** to Git

### Phase 2: Image Pull Secrets (All Apps)

1. **Create GitHub Container Registry secret** in `my-software-showcase` namespace:
   ```bash
   kubectl create secret docker-registry ghcr-secret \
     --docker-server=ghcr.io \
     --docker-username=<github-token-user> \
     --docker-password=<github-token> \
     --docker-email=mathiasuhl@googlemail.com \
     -n my-software-showcase
   ```

2. **Reference in each app's kustomization.yaml**:
   ```yaml
   imagePullSecrets:
   - name: ghcr-secret
   ```

### Phase 3: Database Provisioning (Pending Apps)

For the 5 apps awaiting K8s manifests:

1. Generate K8s Deployment manifests in source repos
2. Include database initialization scripts
3. Create MySQL secrets with credentials
4. Add image-automation.yaml for container image updates
5. Push to source repos and trigger manifest sync

### Phase 4: Flux Reconciliation

1. **Apply root kustomization**:
   ```bash
   flux create kustomization my-software-showcase \
     --source=flux-system \
     --path=./kubernetes/apps/my-software-showcase \
     -n flux-system
   ```

2. **Monitor reconciliation**:
   ```bash
   flux get kustomizations -n flux-system --watch
   flux get helmreleases -A --watch
   ```

3. **Check app status**:
   ```bash
   kubectl get pods -n my-software-showcase -w
   kubectl describe pod -n my-software-showcase <pod-name>
   ```

### Phase 5: SOPS Secret Key Installation (Cluster)

1. **Install SOPS controller** (Sealed Secrets or External Secrets Operator)
2. **Add Age private key to cluster**:
   ```bash
   kubectl create secret generic sops-age \
     --from-file=age.agekey=age-key.txt \
     -n flux-system
   ```

3. **Configure Kustomization resources** to decrypt with SOPS

## Resource Files in Homelab Repo

```
/kubernetes/apps/my-software-showcase/
├── kustomization.yaml                    # Root Kustomization (all 15 apps)
├── DEPLOYMENT_STATUS.md                  # This file
├── zuhause-betreut/
│   ├── ks.yaml                          # Flux Kustomization
│   └── app/
│       ├── helmrelease.yaml
│       ├── image-automation.yaml
│       ├── ghcr-secret.sops.yaml
│       ├── secret.sops.yaml
│       └── kustomization.yaml
├── holm-backend/
│   ├── ks.yaml
│   └── app/
│       ├── deployment.yaml
│       ├── helmrelease.yaml
│       ├── image-automation.yaml
│       ├── prometheus-rule.yaml
│       ├── secrets.yaml
│       ├── service.yaml
│       └── kustomization.yaml
├── see-edv-ibspm/
│   └── ...
├── haarfabrik/
│   └── ...
├── max-jung/
│   └── ...
├── ibgastro/
│   └── ...
├── globalmobility/
│   └── ...
├── uzeit-de/
│   └── ...
├── kfa-medienarchiv/
│   └── ...
├── mangold-smarthomeadvisor/
│   └── ...
├── inbewegung/            # Awaiting K8s manifests
│   ├── ks.yaml
│   └── app/
│       └── kustomization.yaml
├── metaldyne/             # Awaiting K8s manifests
│   ├── ks.yaml
│   └── app/
│       └── kustomization.yaml
├── u-zeit/                # Awaiting K8s manifests
│   ├── ks.yaml
│   └── app/
│       └── kustomization.yaml
├── stepbystepguide/       # Awaiting K8s manifests
│   ├── ks.yaml
│   └── app/
│       └── kustomization.yaml
└── ordiga/                # Awaiting K8s manifests
    ├── ks.yaml
    └── app/
        └── kustomization.yaml
```

## Environment Variables & Secrets Template

Each app directory should contain environment template files for manual provisioning:

```bash
# In each app/k8s directory, create:
.env.example                  # Publicly shared environment template
secrets.yaml.example          # Decrypted secrets template (SOPS encrypted in production)
```

Example format:
```yaml
# app/secrets.yaml.example
apiVersion: v1
kind: Secret
metadata:
  name: <app-id>-secrets
  namespace: my-software-showcase
type: Opaque
stringData:
  DATABASE_HOST: mysql.databases.svc.cluster.local
  DATABASE_NAME: showcase_<app_id>_prod
  DATABASE_USER: showcase_app
  DATABASE_PASSWORD: PLACEHOLDER_ENCRYPTED_IN_SOPS
  RAILS_SECRET_KEY_BASE: PLACEHOLDER_ENCRYPTED_IN_SOPS
```

## Container Images

All apps push to: `ghcr.io/nachtschatt3n/<app-id>:latest`

Flux `ImagePolicy` and `ImageUpdateAutomation` resources automatically update Deployment manifests when new images are pushed.

## Monitoring & Observability

### Prometheus Rules

Apps with `prometheus-rule.yaml`:
- holm-backend
- see-edv-ibspm
- max-jung
- globalmobility
- uzeit-de
- haarfabrik (servicemonitor instead)

### Service Monitors

- haarfabrik: `servicemonitor.yaml`

Other apps need ServiceMonitor configuration for Prometheus scraping.

## Rollback & Recovery

1. **Revert Git commit**:
   ```bash
   git revert <commit-hash>
   ```

2. **Flux detects change** and reconciles (within 30min interval or manually trigger)

3. **Check rollback status**:
   ```bash
   flux get kustomizations --all-namespaces
   flux get helmreleases --all-namespaces
   ```

## Troubleshooting

### Flux Reconciliation Failures

```bash
flux get kustomizations -n my-software-showcase --status
flux logs --all-namespaces --follow
```

### App Deployment Issues

```bash
kubectl describe deployment <app-id> -n my-software-showcase
kubectl logs -n my-software-showcase -l app.kubernetes.io/name=<app-id>
```

### SOPS Decryption Errors

Ensure Age private key is installed in cluster and referenced in Flux Kustomization resources.

### Image Pull Errors

Verify `ghcr-secret` exists and is referenced in each app's `kustomization.yaml`.

## Links

- **Flux Documentation**: https://fluxcd.io/docs/
- **Kustomize Reference**: https://kustomize.io/
- **SOPS with Age**: https://fluxcd.io/docs/guides/mozilla-sops/
- **GitHub Container Registry**: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry

## Maintenance & Updates

- Monitor Flux release updates: https://github.com/fluxcd/flux2/releases
- Update container base images for security patches
- Review and rotate secrets quarterly
- Test disaster recovery procedures monthly

---

**Last Updated**: 2026-08-16  
**Staged By**: Claude Code  
**Status**: 10/15 apps staged, Flux GitOps ready for deployment
