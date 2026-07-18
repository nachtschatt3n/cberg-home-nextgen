# Troubleshooting: openclaw 2026.6.11 → 2026.7.1 upgrade (BLOCKED)

> Status: **blocked / reverted to 2026.6.11** (2026-07-18). Delete this doc once
> 2026.7.1 lands cleanly. Owner for the remaining work: **openclaw-agent**.

openclaw (`kubernetes/apps/ai/openclaw`) is the personal AI agent ("Clawd") in
the `ai` namespace. It is installed at pod startup by an initContainer that
`npm install -g`s the host + plugins onto a PVC (`/home/node/.openclaw`), on base
image `node:22-bookworm`. Deployment strategy is `Recreate`. A 2026-07-18 attempt
to reach 2026.7.1 was reverted after four stacked blockers; the running instance
is back on 2026.6.11 and healthy. Memory: `project_openclaw_2026_7_1_upgrade`.

## Why it matters / current state
- **2026.6.11 == 2026.7.1 in app terms?** No — unlike superset, openclaw 2026.7.1
  is a genuinely newer release (new UI, models, `openclaw attach`, and a
  **gateway crash-loop stability fix** we actually want). So landing it has value.
- Running: `openclaw@2026.6.11`, node 22.22.0, healthy. Git = cluster = 2026.6.11.
- Upgrade alerts silenced in Alertmanager (`OpenClaw.*` / ns `ai`) — see the
  update SOP `docs/sops/application-update.md`.

## The four blockers (in the order they surfaced)

### Layer 1 — node engine (SOLVED, was mis-scoped)
Sweep finding F-58cf59e1 called it "node 22 → 26 major". FALSE. npm registry
engine for `openclaw@2026.7.1`: `">=22.22.3 <23 || >=24.15.0 <25 || >=25.9.0"`.
Node 22 stays valid — just **≥22.22.3**. Running base `node:22-bookworm` was
cached at 22.22.0 (< 22.22.3). Fix: pin `node:22.22.3-bookworm` (both the init and
app container images). Even 2026.7.2-beta keeps this range. **Not node 26.**

### Layer 2 — version-string skew (SOLVED)
host publishes `2026.7.1` / `-1` / `-2`; `@openclaw/codex` `2026.7.1` / `-1`;
`@openclaw/discord` **only** `2026.7.1`. The managed-plugin realign
(helmrelease ~L413) installs `@openclaw/{codex,discord}@$OC_VER` where `$OC_VER`
= the host's exact version. Pinning host to `2026.7.1-2` → realign requests a
non-existent `@openclaw/discord@2026.7.1-2` → realign fails → codex harness
rejects the openai provider. Fix: pin host + the explicit discord line + realign
target all to **plain `2026.7.1`** (the only version all three publish).

### Layer 3 — managed-plugin peer link (SOLVED — upstream #78185)
After the above, app crash-looped:
`Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'openclaw' imported from
~/.openclaw/npm/node_modules/@openclaw/codex/dist/session-binding-*.js`.
From 2026.7.x the managed-store plugins resolve the host `openclaw` package
(bare + `openclaw/plugin-sdk/*`) via a **physical symlink**
`<plugin>/node_modules/openclaw` → the host openclaw root. The host reasserts
that link only from its own install/update/`doctor --fix` flows
(`relinkOpenClawPeerDependenciesInManagedNpmRoot`); our raw `npm install` realign
never triggers it. 2026.6.11 didn't need it (it aliased plugin-sdk in-process via
`plugin-sdk-native-resolver`). Confirmed upstream: openclaw/openclaw#78185
(+ #57390, #49806). Fix (verified against the real 2026.7.1 tarballs — no link =
crash, link = all 45 subpaths resolve): after the realign `npm install`, recreate
the link:
```bash
HOST_OC=/home/node/.openclaw/lib/node_modules/openclaw
for pkg in @openclaw/codex @openclaw/discord; do
  d=/home/node/.openclaw/npm/node_modules/$pkg
  [ -d "$d" ] || continue
  mkdir -p "$d/node_modules"; ln -sfn "$HOST_OC" "$d/node_modules/openclaw"
done
```
Ordering is load-bearing (a fresh `npm install` strips a link a prior
`doctor --fix` created). Verified in the failed run: init logged
`Linked openclaw peer -> …/@openclaw/{codex,discord}/node_modules/openclaw` and
the `ERR_MODULE_NOT_FOUND` was gone.

### Layer 4 — Memory Core → SQLite migration won't complete (UNSOLVED — the wall)
With layers 1-3 fixed, the gateway still refuses to start:
```
[state-migrations] Legacy state migration warnings:
 - Skipped Memory Core session ingestion import for /home/node/clawd because SQLite rows already exist; left legacy source in place
 - Skipped Memory Core short-term recall import  … SQLite rows already exist; left legacy source in place
 - Skipped Memory Core phase signals import      … SQLite rows already exist; left legacy source in place
[openclaw] Reason: OpenClaw startup migrations did not complete cleanly; refusing to report the gateway ready.
  at runStateMigrationPreflight (…/dist/config-guard-*.js:143)
```
2026.7.1 adds a "Memory Core → SQLite" migration. It wants to import the legacy
sources under `/home/node/clawd` into SQLite, but **SQLite rows already exist**,
so it skips the import AND leaves the legacy source — a partial/ambiguous state
that the preflight then rejects ("did not complete cleanly").

**Why the state is partial:** the repeated attempts each ran `openclaw doctor
--fix` (in the init), which created SQLite rows but did not remove/finalise the
legacy sources — so on the next boot the migration sees BOTH and refuses. Plain
`doctor --fix` in the init does NOT reconcile this. This is the open problem.

**Leads for the openclaw-agent (do NOT thrash the live pod):**
- Determine what "clean" completion needs: does 2026.7.1 expect the legacy
  `/home/node/clawd` Memory Core sources to be REMOVED (or archived) once SQLite
  rows exist? Is there a flag/marker file that signals "migration complete"?
- Is there a dedicated migration command (e.g. `openclaw migrate --force` /
  `openclaw doctor --fix --migrate`) distinct from `doctor --fix`?
- The safest approach is to reconcile the migration against a COPY of the PVC
  state offline (not the live pod), find the exact steps to reach a clean state,
  then bake them into the init once — rather than iterating on the live gateway.
- Consider whether a from-clean state (SQLite rows absent) migrates cleanly, i.e.
  the conflict is only because prior partial runs pre-created rows.

## Rollout mechanics that made this painful (lessons)
- **`Recreate` + Flux `upgrade.remediation` rollback = thrash.** Each 2026.7.1
  crash failed helm `--wait` → Flux rolled back to 2026.6.11 before the fixed
  init pod could run. For an attempt, temporarily set
  `upgrade.remediation: { retries: 0, remediateLastFailure: false }`; restore
  `retries: 3` after.
- **Do NOT hand-delete pods mid-Recreate** — the deployment recreates on the same
  (crashing) ReplicaSet, and it wedges helm into `pending-upgrade`.
- **`maxHistory: 1`** prunes old revisions, so `helm rollback` cannot reach a
  2026.6.11 revision. Recovery recipe that worked: `helm rollback openclaw
  <last-deployed-rev> -n ai --wait=false` to clear the stuck `pending-upgrade`,
  then `flux reconcile hr openclaw --force` on the reverted (2026.6.11) git spec —
  the Recreate then boots 2026.6.11 clean (RS `5ff5b76845`).
- Revert recipe: `git checkout <known-good-commit> -- .../openclaw/app/helmrelease.yaml`.

## References
- Memory: `project_openclaw_2026_7_1_upgrade`, `project_openclaw_codex_oauth_drift`
- Upstream: openclaw/openclaw#78185, #57390, #49806
- Commits (2026-07-18): 3e3ba479, befe6763, cfd00335 (attempt 1-2), 70a09536
  (full fix incl. peer-link), c03363a2 / bcb06c25 (reverts)
