---
plan_id: openclaw-2026.10.5
component: openclaw
status: blocked
review: null
window: null
findings: [F-79c6922e, F-39d3d443]     # openclaw + @openclaw/discord 2026.6.11 -> 2026.10.5
kind: npm
current: "2026.6.11"
target: "2026.10.5"
update_type: major
risk: high
est_duration_min: 90
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/ai/openclaw
    - deployment/ai/openclaw            # Recreate roll; PVC openclaw-data is RWO
    - pvc/ai/openclaw-data
    - kubernetes/apps/ai/openclaw/app/helmrelease.yaml
  shared: [ai]
depends_on: []
conflicts_with:
  - talos-linux-1.14.4                  # exclusive node roll evicts the pod mid-migration
---

# openclaw 2026.6.11 -> 2026.10.5

## 0. Verdict: BLOCKED (not viable on the current node 22 base)

**Blocker (measured 2026-10-23 against the npm registry):** `openclaw@2026.10.5`
declares `engines.node = ">=24.16.0 <25 || >=26.1.0"`. Node 22 is excluded (the
running base is `node:22.23.3-bookworm`; 2026.6.11 needs only `>=22.19.0`).
Node 22 support ended somewhere between 2026.7.1 (`>=22.22.3 <23 || >=24.15.0`)
and 2026.9.33 (`>=24.16.0 <25 || >=26.1.0`). 2026.10.6 (npm `latest`) tightens to
`>=24.22.1 <25 || >=26.12.1`. So the upgrade needs an init-image move to
**node 24.x (>=24.16, prefer 24.22.1+)**; node 26 is allowed by 10.5 but 24 is
the lower-risk line (other apps in this repo already run node 24.22.x).

**Unblock condition:** an in-pod dry run (section 3) on a node 24 base completes
with `openclaw doctor` Errors: 0, the plugin symlink present, and a live turn on
`openai/gpt-5.6-terra`. Until then do not edit the HelmRelease.

Note for the earlier hold (commit for F-6a859080): `runbooks/auto-update-policy.yaml`
`image_major_ceiling` caps the openclaw `node` image at 22 and the Renovate rule
(`allowedVersions "<23"`, scoped to `kubernetes/apps/ai/openclaw/**`) mirrors it.
**Both must be raised to 24 (`max_major: 24`, `"<25"`) in the same commit as the
base-image move**, or the checker will keep reporting the 24 line as unreachable.

## 1. Premises that can fail (re-check at window time)
1. `npm view openclaw@2026.10.5 engines.node` still `>=24.16.0 <25 || >=26.1.0`
   (and note whether `latest` moved past 10.6; pin ONE plain version for host,
   `@openclaw/discord` and the managed `@openclaw/codex` realign - all three exist
   at 2026.10.5, verified).
2. `@openclaw/codex@2026.10.5` peerDependency `openclaw >=2026.10.5`, compat
   `pluginApi >=2026.10.5`, vendors `@openai/codex 0.160.0` and its catalog names
   gpt-5.6-terra, gpt-5.6-luna, gpt-5.6-sol and gpt-6-astra (verified in the
   tarball; there is NO model called `gpt-6-luna`). Re-check that the catalog
   still lists terra: if yes, the `models.providers.openai` overlay and
   `OPENCLAW_CODEX_APP_SERVER_BIN` (needed with 2026.6.11 only because its
   vendored codex 0.139.0 was rejected for 5.6) may be redundant; keep both
   until section 3 proves otherwise, do not remove them in this change.
3. The 2026.7.x "managed plugins resolve the host via a PHYSICAL symlink" blocker
   (upstream #78185) is still unfixed in the realign block: after the raw
   `npm install @openclaw/{codex,discord}@$OC_VER` the link
   `~/.openclaw/npm/node_modules/@openclaw/<pkg>/node_modules/openclaw` ->
   `~/.openclaw/lib/node_modules/openclaw` must be created idempotently
   (every boot, after install, before `chown -R`). Re-verify the file's current
   state first; this fix was never applied.
4. A "Memory Core -> SQLite" startup migration (introduced 2026.7.1) will run when
   jumping from 6.11; the gateway refuses to start until `openclaw doctor --fix`
   has run against the mounted state. Needs a `doctor --fix` step in the init
   container (state PVC mounted, HOME set).
5. Unknown: breaking changes across ~4 months of releases (6.11 -> 10.5). Read the
   release notes for 2026.7.x - 2026.10.5 for: config schema changes (a bad key on
   the PVC config crashloops every replacement pod, init only patches), Telegram
   poller / channel plugin changes, speech/TTS provider config, memory-core
   dreaming (`dreaming-narrative-*.js` timeout sed patch may no longer match: the
   patch is idempotent but check it still finds its target), cron store format,
   and multi-agent (9 agents) routing config. NOT assessed read-only; this is the
   largest residual risk.
6. Codex OAuth is current (`codex login status`); it drifts ~10 days and a re-login
   needs the operator in a browser. Do not start the window with a stale login.

## 2. Pre-checks (all must pass; abort otherwise)
```bash
cd /Users/mu/code/cberg-home-nextgen
python3 runbooks/longhorn-backup-age.py            # openclaw-data backup < 24h, else take one first
OC=$(kubectl -n ai get pod -l app.kubernetes.io/instance=openclaw -o jsonpath='{.items[0].metadata.name}')
kubectl -n ai exec "$OC" -c app -- codex login status
kubectl -n ai exec "$OC" -c app -- openclaw cron list      # NO cron due within 30 min (07:00/08:45 briefing, 03:00 dreaming, 04:00 sweep trigger)
kubectl -n ai exec "$OC" -c app -- bash -lc 'pgrep -af "[s]ay|tts" || echo no-inflight-say'
```
Never roll during a due cron or an in-flight `say` (a 07:01 reconcile once killed
the briefing's detached voice). Also copy `~/.openclaw/openclaw.json` to
`openclaw.json.bak-pre-10.5` on the PVC.

## 3. In-pod validation BEFORE the GitOps roll (gpt-5.6 rollout trap)
Do not mutate the live pod's install. In a scratch pod (same image tag as the
target base, `node:24.22.1-bookworm` digest-pinned, PVC NOT mounted, or a Longhorn
clone of openclaw-data mounted RW) run:
1. `npm i openclaw@2026.10.5`, then the managed plugins `@openclaw/codex` and
   `@openclaw/discord` at the same version, then create the peer symlink (2.3).
2. `openclaw doctor --fix` then `openclaw doctor`: **Errors: 0** (startup-safe;
   catalog misses are request-time FailoverErrors and cannot crashloop, but any
   config validation error does).
3. A live turn on `openai/gpt-5.6-terra` through the codex app-server (with
   and without `OPENCLAW_CODEX_APP_SERVER_BIN`), and one on `openai/gpt-5.5`.
4. Never write provider overlays for non-bundled providers (e.g. `codex-cli`):
   hard-fails startup and persists on the PVC.
Only if 1-3 pass, proceed to section 4. If it fails, fill the blocker back in
section 0 and stop.

## 4. Execution (GitOps only, one commit)
In `kubernetes/apps/ai/openclaw/app/helmrelease.yaml`:
1. init image `node` tag -> `24.22.1-bookworm@sha256:<verified digest>`.
2. `install_npm openclaw@2026.10.5` and the explicit `@openclaw/discord@2026.10.5`
   line (both plain, no `-N` suffix).
3. Add the peer-symlink loop and the `doctor --fix` step (premises 3 and 4).
4. Raise the node ceiling (policy `image_major_ceiling` to 24, Renovate `<25`).
5. Optionally set `upgrade.remediation.retries: 0` / `remediateLastFailure: false`
   for this one roll so Flux does not roll back before the fix runs; revert after.
Commit with `git commit --only <paths>`, push, let Flux reconcile; verify the
rendered Deployment strategy is `Recreate` and the live pod's startTime/digest
changed (rollout status alone can green-light the old generation).

## 5. Behaviour verification (all must pass)
```bash
OC=$(kubectl -n ai get pod -l app.kubernetes.io/instance=openclaw -o jsonpath='{.items[0].metadata.name}')
kubectl -n ai exec "$OC" -c app -- bash -lc 'jq -r .version ~/.openclaw/lib/node_modules/openclaw/package.json; jq -r .version ~/.openclaw/npm/node_modules/@openclaw/codex/package.json; node -v'   # 2026.10.5 x2, v24.x
kubectl -n ai exec "$OC" -c app -- openclaw agent -m "Reply with exactly this token: CANARY7F3" --session-id hc --timeout 90
kubectl -n ai exec "$OC" -c app -- bash -lc 'cd ~/clawd && python3 scripts/morning_briefing.py --dry-run | head -30'
```
- Every one of the 9 agents answers a canary turn (main agent first; it is the
  OAuth anchor), model reported as `openai/gpt-5.6-terra`.
- Telegram RECEIVE test: send a message to the bot and confirm a reply (a wedged
  poller sends but never receives; `kill 1` recovers). Discord too.
- TTS: run the `say` skill once; audio produced (local Qwen3-TTS on :8000, or the
  ElevenLabs fallback).
- Dreaming: `~/clawd/DREAMS.md` updates after the next 03:00 run; confirm the
  narrative timeout patch applied (`grep -c 42e4` on `dist/dreaming-narrative-*.js`).
- Crons: `openclaw cron list` shows all jobs (briefing, dreaming, sweep trigger
  8163c139, retro e9ce4ac3) with sane next-run times.
- `runbooks/health-check.sh` OpenClaw block: plugin skew ALIGNED, canary OK,
  skill-bin presence OK. First real 08:45 briefing sends and voices.

## 6. Rollback
1. `git revert` the roll commit (restores node 22.23.3, openclaw 2026.6.11, plugins),
   push, Flux reconcile (Recreate). Do not hand-delete pods mid-Recreate.
2. If the new version already migrated the state (Memory Core SQLite, config
   schema) so 2026.6.11 will not start: restore `openclaw.json.bak-pre-10.5` and
   restore `openclaw-data` from the pre-window Longhorn backup (static volume,
   same name; follow docs/sops/longhorn.md and backup.md - scale to 0 first).
3. If helm is stuck in `pending-upgrade`: `helm rollback openclaw <last-deployed>
   --wait=false` then reconcile the reverted git spec (`maxHistory: 1` means older
   revisions may be gone).
4. If the codex login is lost: `codex login --device-auth` (operator, browser).

## 7. Risk and duration
Risk **high**: a 4-month, multi-step version jump plus a Node major-line change, a
state migration on the PVC, and a plugin-resolution mechanism that already caused a
crashloop once. Duration ~90 minutes including validation (about 30 for section 3,
15 for the roll, 30 for verification, 15 slack). Needs an attended window, not the
unattended nightly. No reboot; the household assistant is down for the roll (a few
minutes) and for any rollback.
