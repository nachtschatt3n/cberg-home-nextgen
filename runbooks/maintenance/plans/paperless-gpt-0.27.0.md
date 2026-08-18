---
plan_id: paperless-gpt-0.27.0
component: paperless-gpt
pr: null                          # auto-update applied + auto-reverted 2026-08-18 (3d60ab9f)
kind: image
current: "v0.25.1"
target: "v0.27.0"
update_type: minor
risk: low
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/paperless-gpt
    - deployment/paperless-gpt
  shared: []                       # talks to paperless-ngx + Ollama host over the network only; no shared storage/DB
depends_on: []
conflicts_with: []
security_ref: null
status: executed                  # 2026-08-18, commit 264b6064
window: "2026-08-18"
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/paperless.md
generated: "2026-08-18"
---

# paperless-gpt v0.25.1 → v0.27.0 (with non-root entrypoint fix)

## 1) Summary & why held

This morning's auto-update (Step 0) bumped `icereed/paperless-gpt` v0.25.1 →
v0.27.0 and **auto-reverted** it (commit `3d60ab9f`): the pod went
CrashLoopBackOff. Home-operation issue
`auto-update-revert-paperless-gpt-20260818`.

**Root cause (verified against upstream source):** v0.26.0 ("Rootless
Container") introduced an `entrypoint.sh` + `su-exec` that is *designed to be
started as root*: it runs `adduser`, `mkdir -p /home/paperless-gpt` and
`chown -R $PUID:$PGID /app /home/paperless-gpt`, then drops to `PUID:PGID`
(default 10001). Our pod securityContext already enforces
`runAsUser: 1000 / runAsNonRoot: true`, so the entrypoint starts as UID 1000:
`mkdir /home/paperless-gpt` and the `chown -R` fail, `set -e` exits → crash
loop. v0.25.1 had no entrypoint at all (`CMD ["/app/paperless-gpt"]`).

## 2) Fix (keeps our non-root securityContext)

Bypass the root-only entrypoint and exec the binary directly — exactly the
v0.25.1 execution model, which already ran correctly as UID 1000:

- `command: ["/app/paperless-gpt"]` on the main container
- `HOME=/home/paperless-gpt` env + `home` emptyDir mounted at
  `/home/paperless-gpt` (the image's intended home; the entrypoint would have
  exported it — belt-and-braces, the v0.27.0 Go source itself never reads HOME)

**Compatibility verified in the v0.27.0 source tree:**
- All writable paths are relative to `WORKDIR /app`: `prompts/`, `config/`,
  `db/` — all already emptyDir mounts in our HelmRelease
- Document cache → `os.TempDir()/paperless-gpt` (`/tmp`, world-writable)
- `ocr_prompt.tmpl` still loaded by name → our configMap subPath override keeps
  working
- `MANUAL_TAG` / `AUTO_TAG` envs still honored; the dropped `MANUAL_OCR_TAG`
  queue is not configured by us

No root granted; PUID/PGID not needed (numeric IDs come from the pod
securityContext).

## 3) Execution (GitOps)

1. Single commit: tag `v0.25.1 → v0.27.0` **and** the three values changes
   above in `kubernetes/apps/office/paperless-gpt/app/helmrelease.yaml`.
2. Pre-commit: `task template:configure -- --strict` + kubeconform + helm
   template render check of the bjw-s 5.1.0 values.
3. Push, let Flux reconcile the `office` kustomization.

## 4) Verification

- Pod Running + Ready, **0 restarts** through a ≥5 min settle period
- Logs: no `permission denied` / `read-only` errors; server listening on 8080
- Functional: paperless-ngx API connectivity in logs (document polling), OCR
  queue processing. gemma4 empty-response vision quirks are known/pre-existing
  — out of scope.
- Resolve home-operation issue `auto-update-revert-paperless-gpt-20260818`.

## 5) Rollback

One line: revert the image tag to `v0.25.1` (the added command/HOME/emptyDir
values are harmless under v0.25.1 — it has no entrypoint to bypass), or
`git revert` the commit. Same shape as `3d60ab9f`. State: all persistence is
emptyDir (stateless add-on; suggestions/history are recreatable), so no data
migration risk in either direction.

## 6) Interference

None: single app in `office`, no shared resources, no reboot, no chart bump
(stays app-template 5.1.0). Keep out of the same window as a paperless-ngx
plan only to keep verification signals clean.
