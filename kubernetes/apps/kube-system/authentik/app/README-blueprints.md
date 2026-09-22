# Authentik Blueprints

Authentik blueprints are stored in a **SOPS-encrypted ConfigMap** (`configmap.sops.yaml`) so the real domain values can live in a public repository.

## Architecture

- **Source of truth**: every blueprint is a data key of `configmap.sops.yaml` (SOPS-encrypted) — **this is what Authentik loads at runtime**
- **Deployment**: Flux decrypts and applies the ConfigMap; `helmrelease.yaml` mounts it read-only at **`/blueprints/cberg`** on the server and worker pods
- **Loading**: that path is a *subdirectory* of the image's own `/blueprints`, so the upstream `default/`, `system/` and `migrations/` blueprints stay visible and re-apply on every image bump, while ours are discovered recursively as `cberg/<key>.yaml`. There is no init container and no copy step (the old copy-into-emptyDir layout hid the upstream trees — F-6d6decf1, 2026-09-23)

Full layout, discovery/re-apply semantics and the post-rollout verification list: `docs/sops/authentik.md`, section "Blueprint directory layout and upstream re-apply semantics".

## Adding, updating or removing a blueprint

Edit the encrypted ConfigMap **in place** — never via `/tmp` (see the warning in `kustomization.yaml`):

```bash
sops kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml
```

Add, change or delete the data key (`<app>-blueprint.yaml: |` …), save, commit with `git commit --only`, push. Adding a key is enough: discovery is recursive and Reloader rolls the pods. **No `helmrelease.yaml` edit is needed for a new blueprint.** Removing a key removes the file; `clear_failed_blueprints` then deletes its `BlueprintInstance` row (the objects it created stay — add `state: absent` entries first if they must go, as `wazuh-blueprint.yaml` shows).

Verify with the `BlueprintInstance` listing in the SOP (there is no `show_blueprints` command on this image).

## Why a SOPS-encrypted ConfigMap?

- **Security**: real domains and OIDC client secrets can be committed to a public repository
- **GitOps**: Flux handles decryption; nothing is configured in the Authentik UI
- **Single source**: one encrypted ConfigMap instead of many files
