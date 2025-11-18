# Authentik Blueprints

Authentik blueprints are now stored in a **SOPS-encrypted ConfigMap** (`configmap.sops.yaml`) for security, allowing sensitive domain information to be stored in a public repository.

## Architecture

- **Source of Truth**: All blueprints are stored in `configmap.sops.yaml` (SOPS-encrypted) - **this is what Authentik loads at runtime**
- **Deployment**: Flux decrypts and applies the ConfigMap, which is mounted as a volume to Authentik pods
- **Loading**: Init containers copy blueprints from the ConfigMap volume to `/blueprints` directory for Authentik to load

## Adding a New App with Authentik

1. Decrypt the ConfigMap: `sops -d kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml > /tmp/configmap.yaml`
2. Add your blueprint to the `data` section in `/tmp/configmap.yaml`:
   ```yaml
   data:
     your-app-blueprint.yaml: |
       version: 1
       entries:
         # ... your blueprint content ...
   ```
3. Re-encrypt: `sops -e /tmp/configmap.yaml > kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`
4. Update `helmrelease.yaml` to copy your blueprint in the init containers (both server and worker sections)
5. Commit and push - Flux will decrypt and apply automatically

## Updating an Existing Blueprint

1. Decrypt the ConfigMap: `sops -d kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml > /tmp/configmap.yaml`
2. Edit the blueprint entry in `/tmp/configmap.yaml`
3. Re-encrypt: `sops -e /tmp/configmap.yaml > kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`
4. Commit and push

## Removing an App

1. Decrypt the ConfigMap: `sops -d kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml > /tmp/configmap.yaml`
2. Remove the blueprint entry from the `data` section
3. Re-encrypt: `sops -e /tmp/configmap.yaml > kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`
4. Update `helmrelease.yaml` to remove the blueprint copy command from init containers
5. Commit and push

## Why SOPS-Encrypted ConfigMap?

- **Security**: Sensitive domain information (actual domains, not placeholders) can be stored safely in a public repository
- **GitOps**: Fully automated deployment - Flux handles decryption automatically
- **Single Source**: All blueprints in one encrypted ConfigMap, easier to manage than multiple files
