# SOP: Authentik Identity Provider

> Standard Operating Procedures for Authentik authentication and authorization management.
> Reference: `docs/security.md` for security overview, Authentik blueprint pattern details.
> Description: Managing Authentik forward-auth integrations through GitOps blueprints.
> Version: `2026.03.01`
> Last Updated: `2026-03-01`
> Owner: `Platform`

---

## Description

This SOP defines the required blueprint-driven workflow for Authentik integrations, including
provider/application/outpost wiring, ingress integration, and post-deploy validation.

---

## Overview

Authentik provides unified SSO and forward-auth proxy for all cluster services.

| Setting | Value |
|---------|-------|
| Namespace | `kube-system` |
| Deployment | `kubernetes/apps/kube-system/authentik/` |
| Blueprint source | `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml` (SOPS-encrypted) |
| Config approach | Blueprints only — never use UI |
| Auth flow | Forward auth proxy via per-app outposts |

**CRITICAL:** All Authentik configuration MUST be done via blueprints, never the UI.
Blueprints are version-controlled, GitOps-compatible, and reproducible.
Workflow: decrypt ConfigMap -> edit blueprint entry -> re-encrypt -> commit -> push.

---

## Blueprints

Auth configuration source-of-truth:
- `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`

App-level blueprint source files (optional — some apps keep a local copy):
- `kubernetes/apps/{namespace}/{app}/app/authentik-blueprint.yaml` (if present)

The central ConfigMap is the source of truth. A per-app file is optional documentation.
All Authentik changes must be declarative and committed to Git (no UI-only configuration).

---

## Operational Instructions

Operational flow:
1. Create or update app blueprint manifest.
2. Merge blueprint entry into Authentik SOPS ConfigMap.
3. Update app ingress and outpost ingress paths.
4. Commit/push and verify outpost resources and login flow.

Detailed implementation steps are in `Integrating a New Application` below.

---

## Examples

### Example 1: Provider to Application Reference

```yaml
- id: my-app-application
  model: authentik_core.application
  attrs:
    provider: !KeyOf my-app-provider
```

### Example 2: Outpost with Kubernetes Service Connection

```yaml
- id: my-app-outpost
  model: authentik_outposts.outpost
  attrs:
    service_connection: "162f6c4f-053d-4a1a-9aa6-d8e590c49d70"
    providers:
      - !KeyOf my-app-provider
```

---

## Key UUIDs (Hardcode These in Blueprints)

| Name | UUID |
|------|------|
| default-provider-authorization-implicit-consent | `0cdf1b8c-88f9-4b90-a063-a14e18192f74` |
| default-provider-invalidation-flow | `b8a97e00-f02f-48d9-b854-b26bf837779c` |
| Local Kubernetes Cluster service connection | `162f6c4f-053d-4a1a-9aa6-d8e590c49d70` |

---

## Integrating a New Application

### Step 1: Create Blueprint File

Create `kubernetes/apps/{namespace}/{app}/app/authentik-blueprint.yaml`:
This file is the app-level source blueprint that should also be copied into the Authentik SOPS ConfigMap.

```yaml
version: 1
entries:
  # --- Proxy Provider ---
  - id: my-app-provider
    model: authentik_providers_proxy.proxyprovider
    state: present
    attrs:
      name: my-app-forward-auth
      mode: forward_single
      external_host: "https://myapp.domain.com"
      internal_host: "http://myapp.{namespace}.svc.cluster.local:{PORT}"
      internal_host_ssl_validation: false
      authorization_flow: "0cdf1b8c-88f9-4b90-a063-a14e18192f74"
      invalidation_flow: "b8a97e00-f02f-48d9-b854-b26bf837779c"

  # --- Application ---
  - id: my-app-application
    model: authentik_core.application
    state: present
    attrs:
      name: My App
      slug: my-app
      provider: !KeyOf my-app-provider
      meta_launch_url: "https://myapp.domain.com"
      meta_icon: "https://myapp.domain.com/favicon.ico"

  # --- Outpost ---
  - id: my-app-outpost
    model: authentik_outposts.outpost
    state: present
    attrs:
      name: my-app-forward-auth
      type: proxy
      service_connection: "162f6c4f-053d-4a1a-9aa6-d8e590c49d70"
      providers:
        - !KeyOf my-app-provider
      config:
        authentik_host: "https://auth.domain.com"
        authentik_host_insecure: false
        kubernetes_namespace: kube-system
        kubernetes_replicas: 1
```

**Key rules:**
- Use hardcoded UUIDs for flows (not slugs)
- Use `!KeyOf` to reference other blueprint entries (not strings)
- Use SOPS-encrypted ConfigMap for actual domain values (Flux substitution doesn't work in ConfigMap data)
- `kubernetes_namespace: kube-system` is standard for all outposts

### Step 2: Add Blueprint to Authentik ConfigMap

The ConfigMap is the source Authentik reads. It's SOPS-encrypted.

```bash
# Decrypt ConfigMap
sops -d kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml > /tmp/configmap.yaml

# Edit /tmp/configmap.yaml — add your blueprint as a new data entry:
# data:
#   existing-blueprint.yaml: |
#     ...existing content...
#   my-app-blueprint.yaml: |
#     <paste your blueprint content here>

# Copy to repo path (must be in kubernetes/ for SOPS path rules)
cp /tmp/configmap.yaml kubernetes/apps/kube-system/authentik/app/configmap-new.sops.yaml

# Encrypt in place
sops -e -i kubernetes/apps/kube-system/authentik/app/configmap-new.sops.yaml

# Replace old file
mv kubernetes/apps/kube-system/authentik/app/configmap-new.sops.yaml \
   kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml

# Clean up
rm /tmp/configmap.yaml
```

### Step 3: Configure App Ingress with Auth Annotations

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app
  namespace: my-namespace
  annotations:
    # Authentik forward auth
    nginx.ingress.kubernetes.io/auth-url: "http://ak-outpost-my-app-forward-auth.kube-system.svc.cluster.local:9000/outpost.goauthentik.io/auth/nginx"
    nginx.ingress.kubernetes.io/auth-signin: "https://auth.${SECRET_DOMAIN}/outpost.goauthentik.io/start?rd=$scheme://$http_host$request_uri"
    nginx.ingress.kubernetes.io/auth-response-headers: "Set-Cookie,X-authentik-username,X-authentik-groups,X-authentik-email,X-authentik-name,X-authentik-uid"
    nginx.ingress.kubernetes.io/auth-snippet: |
      proxy_set_header X-Forwarded-Host $http_host;
    # Homepage
    gethomepage.dev/enabled: "true"
    gethomepage.dev/name: "My App"
    gethomepage.dev/group: "Group Name"
    gethomepage.dev/icon: "my-app.png"
    gethomepage.dev/description: "Description"
  labels:
    gethomepage.dev/enabled: "true"
spec:
  ingressClassName: internal
  rules:
    - host: myapp.${SECRET_DOMAIN}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: my-app
                port:
                  number: 8080
```

### Step 4: Create Outpost Ingress

The `/outpost.goauthentik.io/*` paths must be exposed via a separate ingress:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app-authentik-outpost
  namespace: my-namespace
spec:
  ingressClassName: internal
  rules:
    - host: myapp.${SECRET_DOMAIN}
      http:
        paths:
          - path: /outpost.goauthentik.io
            pathType: Prefix
            backend:
              service:
                name: ak-outpost-my-app-forward-auth
                port:
                  number: 9000
```

The outpost service (`ak-outpost-my-app-forward-auth`) is automatically created in `kube-system`
when the blueprint runs and the outpost is created.

### Step 5: Commit and Verify

```bash
# Commit changes
git add kubernetes/apps/{namespace}/{app}/
git add kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml
git commit -m "feat(authentik): add my-app forward auth"
git push

# Wait for Flux reconciliation, then verify
kubectl exec -n kube-system deployment/authentik-server -- \
  python3 manage.py show_blueprints

# Check outpost was created
kubectl get deployment -n kube-system ak-outpost-my-app-forward-auth
kubectl get svc -n kube-system ak-outpost-my-app-forward-auth
```

---

## Removing an Application Integration

```bash
# 1. Decrypt ConfigMap, remove the blueprint entry, re-encrypt
sops -d kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml > /tmp/configmap.yaml
# Remove the app's blueprint data entry from /tmp/configmap.yaml
cp /tmp/configmap.yaml kubernetes/apps/kube-system/authentik/app/configmap-new.sops.yaml
sops -e -i kubernetes/apps/kube-system/authentik/app/configmap-new.sops.yaml
mv kubernetes/apps/kube-system/authentik/app/configmap-new.sops.yaml \
   kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml
rm /tmp/configmap.yaml

# 2. If a per-app blueprint file exists, remove it
# rm kubernetes/apps/{namespace}/{app}/app/authentik-blueprint.yaml  # only if present

# 3. Remove auth annotations from ingress
# 4. Remove outpost ingress
# 5. Commit and push
```

---

## Blueprint Reference: DO's and DON'Ts

### ✅ DO

- Use hardcoded flow UUIDs (not slug names)
- Use `!KeyOf` for cross-entry references
- Use SOPS-encrypted ConfigMap for actual domain values
- Include `service_connection` for Kubernetes outposts
- Create a dedicated outpost per application

### ❌ DON'T

- Use UI for any Authentik configuration
- Use slug names for flow references (will fail)
- Use string names for provider references (use `!KeyOf`)
- Use Flux substitution in ConfigMap data fields (doesn't work)
- Omit `service_connection` from outposts
- Bind to the embedded outpost

---

## Blueprint Entry Checklist

Before deploying a new Authentik integration, verify:

1. Proxy Provider
   - Uses flow UUIDs, not slug names
   - `external_host` is an actual domain value (stored in SOPS ConfigMap)
   - `internal_host` points to the correct in-cluster service and port
2. Application
   - Uses `provider: !KeyOf <provider-id>` (not a string name)
   - Launch URL and icon URL use actual domain values
3. Outpost
   - Uses `providers: [!KeyOf <provider-id>]`
   - Includes `service_connection: "162f6c4f-053d-4a1a-9aa6-d8e590c49d70"`
   - Sets `kubernetes_namespace: kube-system`
4. Ingress
   - Main ingress includes `auth-url`, `auth-signin`, and auth response headers
   - Separate ingress exists for `/outpost.goauthentik.io/*`
5. Verification
   - `show_blueprints` includes the new blueprint
   - `ak-outpost-{app}-forward-auth` deployment and service exist in `kube-system`

---

## Reference Implementations

- Frigate NVR (blueprint in central ConfigMap only):
  - Outpost ingress: `kubernetes/apps/home-automation/frigate-nvr/app/authentik-outpost-ingress.yaml`
- phpMyAdmin (blueprint in central ConfigMap only):
  - Outpost ingress: `kubernetes/apps/databases/phpmyadmin/app/authentik-outpost-ingress.yaml`
- Longhorn (has per-app blueprint file + entry in central ConfigMap):
  - Blueprint file: `kubernetes/apps/storage/longhorn/app/authentik-blueprint.yaml`

For all apps: blueprint entry is in `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`.

---

## Verification Tests

### Test 1: Blueprint Loaded

```bash
kubectl exec -n kube-system deployment/authentik-server -- \
  python3 manage.py show_blueprints
```

Expected:
- New/updated blueprint appears in output without load errors.

If failed:
- Decrypt and validate `configmap.sops.yaml` structure and re-apply via GitOps.

### Test 2: Outpost Resources Created

```bash
kubectl get deployment -n kube-system ak-outpost-{app}-forward-auth
kubectl get svc -n kube-system ak-outpost-{app}-forward-auth
```

Expected:
- Deployment and service exist and are `Ready`.

If failed:
- Check Authentik logs for service connection or blueprint reference errors.

---

## Troubleshooting

```bash
# Check blueprints loaded
kubectl exec -n kube-system deployment/authentik-server -- \
  python3 manage.py show_blueprints

# Authentik server logs
kubectl logs -n kube-system -l app.kubernetes.io/name=authentik --tail=100

# Filter blueprint logs
kubectl logs -n kube-system -l app.kubernetes.io/name=authentik --tail=200 | grep -i blueprint

# Filter outpost logs
kubectl logs -n kube-system -l app.kubernetes.io/name=authentik --tail=200 | grep -i outpost

# Check all outpost deployments
kubectl get deployments -n kube-system -l app.kubernetes.io/managed-by=goauthentik.io

# Check outpost services
kubectl get svc -n kube-system | grep ak-outpost

# Check if outpost service exists for a specific app
kubectl get svc -n kube-system ak-outpost-{app}-forward-auth

# Full outpost resources
kubectl get all -n kube-system -l goauthentik.io/outpost-name={app}-forward-auth
```

### Common Issues

| Issue | Likely Cause | Fix |
|-------|-------------|-----|
| Blueprint not loading | ConfigMap not updated | Verify blueprint in decrypted ConfigMap |
| Outpost deployment not created | Missing `service_connection` | Add `service_connection: "162f6c4f-..."` |
| Auth redirect loop | Outpost ingress missing | Create ingress for `/outpost.goauthentik.io/*` |
| 401 on auth-url | Wrong outpost service name | Check `ak-outpost-{app}-forward-auth.kube-system.svc.cluster.local` |
| Blueprint fails with UUID error | Using slug instead of UUID | Replace slug with UUID in blueprint |

---

## Diagnose Examples

### Diagnose Example 1: Redirect Loop After Login

```bash
kubectl get ingress -n {namespace} -o yaml | rg "outpost.goauthentik.io|auth-url|auth-signin"
kubectl get svc -n kube-system ak-outpost-{app}-forward-auth
```

Expected:
- Main ingress has auth annotations and outpost ingress path exists.

If unclear:
- Check outpost logs with `kubectl logs -n kube-system -l app.kubernetes.io/name=authentik --tail=200 | grep -i outpost`.

### Diagnose Example 2: Blueprint Applies But No Outpost Deployment

```bash
kubectl logs -n kube-system -l app.kubernetes.io/name=authentik --tail=200 | grep -Ei "blueprint|service_connection|error"
```

Expected:
- No errors for missing `service_connection` or invalid references.

If unclear:
- Verify `service_connection` UUID and `!KeyOf` references in blueprint.

---

## Health Check

```bash
kubectl exec -n kube-system deployment/authentik-server -- \
  python3 manage.py show_blueprints
kubectl get deployments -n kube-system -l app.kubernetes.io/managed-by=goauthentik.io
kubectl get svc -n kube-system | grep ak-outpost
```

Expected:
- Blueprints load cleanly and expected outpost resources remain healthy.

---

## Security Check

```bash
# Auth blueprint source remains encrypted
head -20 kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml | rg "sops:"

# Check no plaintext auth secrets accidentally committed
rg -n --glob '*.yaml' 'client_secret|password|token' kubernetes/apps/kube-system/authentik kubernetes/apps/*/*/app | head -40
```

Expected:
- Secrets stay SOPS-encrypted and no plaintext credentials are introduced.

---

## Rollback Plan

```bash
# Roll back the blueprint/config changes by reverting commit(s)
git log -- kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml
git revert <commit-sha>
git push
```

Rollback validation:
- Re-run `Verification Tests`.
