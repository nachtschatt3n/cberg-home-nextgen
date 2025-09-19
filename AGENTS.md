# Repository Guidelines

## Project Structure & Module Organization
This template deploys a Talos + Flux stack; keep rendered manifests aligned with config changes.
- `kubernetes/` holds bootstrap manifests, app releases, and Flux sync targets.
- `templates/` and `makejinja.toml` define the Jinja sources rendered into `kubernetes/` via Task/Mise.
- `.taskfiles/` holds Taskfile extensions for templating, Talos bootstrap, and helper utilities.
- `.github/` carries automation; `tools/` and `requirements.txt` pin CLI dependencies.

## Build, Test, and Development Commands
Trust and install the Mise toolchain:
```sh
mise trust && mise install && mise run deps
```
Render templates (edit `config.yaml` between steps):
```sh
task template:init
task template:configure
```
Bootstrap and reconcile:
```sh
task bootstrap:talos
task bootstrap:apps
task reconcile
```

## Coding Style & Naming Conventions
- `.editorconfig` enforces LF endings, final newlines, and 2-space indentation (Python/Shell stay at 4).
- Name manifests with scope prefixes (e.g. `cluster/`, `network/`) and keep secrets in `*.sops.*` files.
- Prefer Taskfile targets; mirror `templates/scripts` when introducing scripts.

## Testing Guidelines
- `task template:configure` must pass; it runs `makejinja`, encrypts secrets, then validates YAML with `kubeconform` and Talos config with `talhelper validate`.
- When touching rendered resources, run `task template:configure -- --strict` if you add extra options, and spot-check `kubernetes/` diffs before committing.
- For live clusters, run `task template:debug` to capture kubectl snapshots when verifying fixes.

## Commit & Pull Request Guidelines
- Use concise, imperative subjects; prefix with the touched area when helpful (`langfuse:`, `talos:`), matching existing history.
- Squash noisy rendered output and commit only meaningful diffs; never commit unencrypted secrets or new kubeconfig files.
- PRs should outline the change, list the Task targets run, reference related issues, and attach screenshots or logs for cluster-impacting updates.

## Storage & Persistence Policies
- Route high-capacity volumes through the existing CIFS mounts; don't attach raw disks, reuse CIFS-backed PVs in `kubernetes/apps`.
- Databases and config state must live on Longhorn; create static PV/PVC pairs in the Longhorn UI and reference them from manifests to ensure replica scheduling.

## Secrets & Configuration Tips
- Guard `age.key`, `.sops.yaml`, `deploy.key`; rotate via `task template:init` when sharing access.
- Keep `config.yaml` authoritative—document overrides in its comments rather than ad-hoc READMEs.
- Store external credentials in SOPS-encrypted `kubernetes/**/secret.sops.yaml`; verify with `sops --decrypt` before applying.
