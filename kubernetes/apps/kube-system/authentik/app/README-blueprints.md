# Authentik Blueprints

This directory contains copies of Authentik blueprint files from each app directory.

## Adding a New App with Authentik

1. Create `authentik-blueprint.yaml` in your app's `app/` directory
2. Copy it to this directory with the naming pattern: `{app-name}-blueprint.yaml`
3. Add it to `kustomization.yaml` in the `configMapGenerator.files` list

## Removing an App

1. Remove the app's blueprint file from this directory
2. Remove the reference from `kustomization.yaml`

## Why Copies Instead of Symlinks?

Flux/Kustomize checks out the repo to a temporary directory where symlinks don't work.
We use copies instead, which ensures the files are available during the Kustomize build.

Note: When updating a blueprint, remember to update both:
- The original file in the app directory (source of truth)
- The copy in this directory (used by Kustomize)
