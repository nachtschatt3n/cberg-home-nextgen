---
plan_id: nextcloud-mcp-0.178.1
component: nextcloud-mcp
pr: null                              # PLAN lane — coverage.py needs_plan, no open Renovate PR
                                      # (image lives in app-template `image.tag`; Renovate's
                                      # helm-values manager does emit for this one, but none is
                                      # open). Direct bump in the window.
kind: image                           # app-template image-tag bump. NOT a chart bump.
current: "0.175.0"
target: "0.178.1 (supersedes 0.177.1)" # RETARGETED from the sweep's 0.177.1: 0.177.2, 0.178.0 and
                                      # 0.178.1 all published 2026-08-18 after the version-check
                                      # snapshot was taken. 0.178.1 verified to exist in GHCR on
                                      # 2026-08-18 (digest 508c62e4... is 0.177.1, edffc044... is
                                      # 0.178.0; 0.178.1 resolved live). Re-verify in Pre-checks (a).
update_type: minor                    # 0.175 -> 0.178, but see §1: TWO releases in the span are
                                      # tagged BREAKING CHANGE upstream, which is why this is a
                                      # plan and not an AUTO direct bump.
risk: low                             # Low for THIS deployment specifically — see §2, which walks
                                      # each breaking change against what this instance actually
                                      # runs. Stateless: no PVC, no DB, no occ, no maintenance mode.
                                      # Reverted by one git-revert of a single tag line.
est_duration_min: 10
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud-mcp        # app-template 5.1.0 (UNCHANGED) — only image.tag moves
    - kustomization/nextcloud-mcp      # ns `office` (targetNamespace), NOT flux-system
    - deployment/nextcloud-mcp         # single-replica; rolls one pod (~10s), stateless
    - service/nextcloud-mcp            # UNCHANGED (port 8000) — verify, do not edit
    - ingress/nextcloud-mcp            # UNCHANGED (className: internal)
  shared: []                           # nothing shared is mutated. No storage op (no PVC exists).
depends_on: []                         # (Flux KS has a standing dependsOn: nextcloud — not a
                                       # plan-ordering dependency; nextcloud is stable.)
conflicts_with:                        # VERIFICATION-CONFOUND conflicts, not danger conflicts.
  - bitnamilegacy-exit-nextcloud-db    # both restart the Nextcloud BACKEND this MCP proxies;
  - bitnamilegacy-exit-nextcloud-redis # co-scheduling makes the §4 tool-surface probe flap.
security_ref: F-82c48de4
status: draft
window: null                           # window agent assigns. Recommended: any no-reboot weekday
                                       # slot (mon/tue/wed/thu/fri-early) or sat-early.
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-18"
---

# nextcloud-mcp 0.175.0 → 0.178.1 (image minor, two upstream BREAKING tags in span)

## 1. Summary & why this is a plan and not an AUTO bump

`nextcloud-mcp` is **not** the Nextcloud server. It is the standalone
third-party MCP bridge (`ghcr.io/cbcoutinho/nextcloud-mcp-server`) that exposes
Nextcloud as tools to OpenClaw.

The previous hop (`nextcloud-mcp-0.175.0`, executed 2026-08-17 `ad6bdfcd`) was
held by a **misattribution** and correctly re-scored to low risk. **This hop is
different and the hold is real:** the 0.175 → 0.178 span contains two releases
that upstream itself tagged `BREAKING CHANGE`.

| Release | Breaking change |
|---|---|
| **0.176.0** | Webhook **registration API removed** — `GET/POST /api/v1/webhooks`, `DELETE /api/v1/webhooks/{id}` and the `/app/webhooks` pane now 404, and the `registered_webhooks` **table is dropped**. Delivery config relocates to Astrolabe admin settings. |
| **0.177.0** | `create_share` / `nc_share_create` now **reject** `shareType=3` (public link) carrying `shareWith`, and reject a recipient-typed call omitting it. Both previously reached the server; the first silently produced an anonymous public link while reporting success. Callers relying on either now get `ValueError` / `ToolError`. |

A dropped table plus a tool-contract tightening is exactly the "breaking-change
signal in release notes" that the auto-updater's safe-subset gate is there to
catch, so it goes to a window rather than to Step 0.

## 2. Blast-radius assessment against THIS deployment

Both breaking changes were checked against what this instance actually runs
(`kubernetes/apps/office/nextcloud-mcp/app/`), and both look inert here:

**a) 0.176.0 webhook removal — assessed inert.**
- No webhook configuration exists anywhere in the app directory. `rg -i
  'webhook|astrolabe'` over `kubernetes/apps/office/nextcloud-mcp/` returns
  nothing.
- The decrypted secret carries exactly four keys — `NEXTCLOUD_HOST`,
  `NEXTCLOUD_USERNAME`, `NEXTCLOUD_PASSWORD`, `MCP_DEPLOYMENT_MODE`. No
  `WEBHOOK_SECRET`, no `mcp_webhook_secret`.
- No PVC and no database URL, so the dropped `registered_webhooks` table has no
  persistent store here to be dropped *from*. The Alembic migration runs against
  whatever ephemeral store the container brings up and is discarded on roll.
- There is no Astrolabe deployment in this cluster, so the relocated config
  target is not in play.

**b) 0.177.0 `create_share` tightening — assessed low, but unverifiable
statically.** The only consumer is OpenClaw (`ai` ns) via mcporter. Whether any
skill calls `nc_share_create` with a `shareType=3` + `shareWith` pairing cannot
be proven from the manifests — it is agent-authored tool use at runtime. The
new behaviour is a *rejection where the old behaviour silently produced the
wrong object*, so the failure mode after the bump is a loud `ToolError` rather
than a silent bad share. That is a strict improvement, but it is a behaviour
change an operator should be told about, not one to discover from a confused
agent.

**Net:** low risk for this deployment, but operator-visible, so `auto_execute:
false`. The value in the span is real — 0.177.2 fixes Ollama embed retry/batching
and adds vector dead-lettering; 0.177.1 escapes caller values in WebDAV SEARCH
predicates.

## 3. Pre-checks

a. Re-verify the target tag still resolves (it was published the same day this
   plan was written):
   ```
   crane digest ghcr.io/cbcoutinho/nextcloud-mcp-server:0.178.1
   ```
   If a newer patch exists by window time, retarget and re-read the notes for a
   new BREAKING tag before proceeding.
b. Confirm the current pod is Ready on 0.175.0 and the Nextcloud backend it
   proxies is healthy (this app's KS `dependsOn: nextcloud`).
c. Confirm neither `bitnamilegacy-exit-nextcloud-{db,redis}` is running in the
   same window (§conflicts_with).

## 4. Execution (GitOps)

1. Edit `kubernetes/apps/office/nextcloud-mcp/app/helmrelease.yaml`,
   `image.tag: 0.175.0` → `0.178.1`. Nothing else changes — chart stays
   app-template `5.1.0`.
2. Validate: `task kubeconform`.
3. Commit (hunk-scoped) + push to `main`; let the Flux webhook reconcile.
   Commit message carries `security_ref: F-82c48de4` and no vulnerability
   detail (public repo — `.githooks/commit-msg` enforces this).

## 5. Verification

- `kubectl -n office get pods -l app.kubernetes.io/name=nextcloud-mcp` — one
  pod Ready, **0 restarts**, image `…:0.178.1`.
- Pod logs: Alembic migration completes without error and the server binds
  `:8000`. The `registered_webhooks` drop should appear once and succeed.
- Ingress smoke: the MCP endpoint answers on `nextcloud-mcp.${SECRET_DOMAIN}`.
- Tool-surface probe: from OpenClaw, list the MCP tool surface and confirm the
  Nextcloud tools still enumerate (this is the check the §conflicts_with entries
  would otherwise make flap).
- Explicitly exercise a **recipient-typed** share via `nc_share_create` and
  confirm it succeeds; do **not** treat a rejected `shareType=3 + shareWith`
  call as a regression — that rejection is the intended 0.177.0 behaviour.

## 6. Rollback

`git revert <sha> && git push`. Single tag line; pod rolls back in ~10s. No
schema to restore (no PVC, no persistent DB), no data migration to unwind.
