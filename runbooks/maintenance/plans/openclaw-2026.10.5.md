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
recommended_target: "2026.10.6"   # see unblock_stages S0; switch `target` when S1 passes
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
unblock_stages:                      # status stays blocked until S1-S3 pass; S4 = the go/no-go roll
  - id: S0-assessment      # DONE 2026-10-23 (read-only + Mac offline trial), results in section 0b
  - id: S1-git-prep        # init-script + node 24 base + policy ceiling, NOT yet rolled (no HelmRelease change reaches prod until S3 passes)
  - id: S2-scratch-pod     # isolated pod, throwaway state, doctor --fix + one codex turn
  - id: S3-state-rehearsal # Longhorn clone of openclaw-data, doctor --fix on the clone, network-isolated
  - id: S4-attended-roll   # backup gate, quiet-cron window, GitOps roll, verification, rollback = git revert + PVC restore
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

## 0b. Unblock plan (2026-10-23, openclaw-agent; assessment DONE, stages S1-S4 pending)

### Target decision: **2026.10.6** (not 10.5, not the extended-stable 9.33)
- 10.6 = npm `latest` (published 2026-10-22; the 48h release-age cooldown clears 10-24).
  engines `>=24.22.1 <25 || >=26.1x`; node 24.22.1-bookworm is the current 24 tag, so it is satisfiable
  exactly at the floor. `@openclaw/codex` and `@openclaw/discord` 2026.10.6 exist (peer `openclaw >=2026.10.6`,
  vendored `@openai/codex 0.160.0`, catalog terra/luna/sol/astra).
- 10.6 notes carry a fix directly in our path: Doctor can repair an older built-in agent DB that stopped the
  Gateway after the 10.4 -> 10.5 step, and Doctor no longer resets deliberate per-session runtime choices.
  10.5 has the same migrations without those repairs. `extended-stable` (2026.9.33) has the same node 24.16 floor
  and no advantage for a 6.11 jump. Re-check `npm view openclaw dist-tags` at S1; do not chase 10.10-beta.
- Both targets behaved identically in the offline trial below (same migrations, same single residual error).

### Findings from four months of notes (2026.6.12 -> 2026.10.6), items that touch us
1. **Node**: hard floor (see above). Both the `app` container AND the `install-openclaw` init container
   run `node:22.23.3-bookworm@sha256:0e5f9065...` (helmrelease lines ~50 and ~627) and BOTH must move
   (the gateway executes under the app container's node). No sidecars. python 3.11 is the same on bookworm, so
   `PYTHONPATH .../python3.11/site-packages` (whisper, hactl, pg8000) stays valid. TTS is on the Mac mini, unaffected.
   Native addons already built under node 22 on the PVC (`~/.openclaw/lib/node_modules`, 11G) have the wrong ABI:
   run a one-time `npm rebuild -g --prefix /home/node/.openclaw` (or wipe `lib/node_modules` once; it is reinstalled
   every boot anyway) in S2/S3 and confirm every `install_npm` CLI still starts (`codex`, `gemini`, `claude`, `opencode`, `playwright`).
2. **Peer symlink (old blocker)**: SOLVED by upstream. `openclaw doctor --fix` printed "Repaired OpenClaw host
   peer link(s) for 2 managed npm plugin package(s)". Keep the explicit idempotent `ln -sfn` loop from the 7.1
   memory anyway (after the raw `npm install`, before `chown`), then run `doctor --fix`; the loop is belt and braces.
3. **Config schema migration (NEW, the real blocker)**: with the live config the unmigrated 10.x config is
   INVALID (`agents.list moved to keyed agents.entries`), so the gateway would crashloop like the 7.1 attempt.
   `doctor --fix` migrates: `agents.list -> agents.entries` + explicit per-surface `agents.ownership`,
   `agents.defaults.models -> modelPolicy.allow`, `messages.tts -> top-level tts` (same `tts-local-cli` command),
   `tools.media` -> capability-tagged `models[]` (whisper cli kept), retired knobs removed
   (`agents.defaults.heartbeat.skipWhenBusy`, `compaction.reserveTokensFloor`, discord tuning),
   `channels.discord.heartbeat -> heartbeatVisibility`, `channels.telegram.groupAllowFrom` auto-filled from `allowFrom`
   (2 entries; review that this is intended), model credentials copied into agent SQLite (plaintext kept for now),
   legacy memory-core/auth-store rows -> shared SQLite state. The config's 9 agents and 12 Telegram bindings survive intact.
4. **Residual config error AFTER doctor --fix (must be fixed by hand/in init): `channels.discord.ui: {}`** is
   rejected by the 10.x discord plugin schema ("must not have additional properties: ui"). Delete the key
   (python one-liner in init, idempotent) before the gateway starts. This is exactly the 'bad key on the PVC = permanent
   crashloop' class from the gpt-5.6 attempt. Also unfixed warnings to schedule: `commands.ownerAllowFrom[0]` should
   become `discord:user:<id>` (heartbeat route "no-route" otherwise), `channels.telegram.defaultAccount: "default"`
   matches no account (accounts are `vita`, `jerry`), and the `voice` agent's bare model string drops fallbacks.
5. **Model naming (blocker 4 resolved)**: the live primary IS `openai/gpt-6-luna` (default model + `OPENCLAW_DEFAULT_MODEL`),
   made resolvable by the `models.providers.openai.models[]` OVERLAY in the PVC config (terra + gpt-6-luna entries),
   allowlisted with `agentRuntime codex`. The 10.x codex catalog does not list `gpt-6-luna` (only 5.6 terra/luna/sol, 6-astra), but
   in the trial `openclaw models list` on 10.5/10.6 showed `openai/gpt-6-luna ... default,configured` and doctor copied the
   allow-list, so the overlay keeps working. Whether the server accepts the id is the same as today (it works with the
   `OPENCLAW_CODEX_APP_SERVER_BIN=~/.openclaw/bin/codex` v0.164.0 override). Keep overlay + env var for the first roll; remove later
   and separately. NOT verified: a live turn (needs the Codex login).
6. **Cron**: the cron store was already migrated to SQLite before 6.11 (`jobs.json.migrated` on the PVC); 10.x adds quarantining
   of malformed legacy rows instead of failing boot. Jobs live in `state/openclaw.sqlite`; compare `openclaw cron list`
   byte-for-byte before/after (ids 0788b8a7 briefing, d55acccd dreaming, 8163c139 sweep trigger, e9ce4ac3 retro).
7. **Telegram**: no breaking change for our bot topology; many poller-resilience fixes (rate limits, stalled drain,
   isolated polling resume, a polling-worker start failure). Account ownership gating now shows explicit failure
   notices. Still run the receive test; the silent-inbound-death history is not provably gone.
8. **Dreaming/memory**: `NARRATIVE_TIMEOUT_MS` is gone; the narrative timeout is now `resolveAgentTimeoutMs` and the
   dist files are `.mjs`, so the init `sed` over `dreaming-narrative-*.js` silently matches nothing (harmless; REMOVE the block
   in S1 and instead verify the diary text on the first 03:00 run and tune the agent timeout if it falls back).
   The `session-accessor-*.js` stable-revision patch also targets `.js` (now `.mjs`); it WARNs only. The upstream
   fix status for the "reply session initialization conflicted" loop is UNVERIFIED; watch for it after the roll.
9. **Skills (risk)**: "agent-owned Workshop skills": one writable Workshop collection per agent; startup/`doctor --fix`
   migrate "proven legacy skills", ambiguous ones stay for review. Our seeded `~/clawd/skills/<name>/SKILL.md` (~27 dirs) are
   workspace skills; could not be exercised offline (no workspace). S3 must check they still load (`openclaw skills list`) and the
   init re-seed is not fighting the migration.
10. Other breaking items checked and NOT applicable: Code Mode TS-only cells, OpenProse removal, `/prose`,
    video-frames skill removal, SDK/approval API renames (third-party plugins only; we run only codex+discord first-party),
    OpenAI route migration (`codex/*`, `openai-codex/*` refs -> `openai/*`; we already use `openai/*`; grep shows a stale
    `codex-cli/gpt-5.6-terra` map entry that doctor dropped).
11. npm now warns install-scripts are skipped unless allowed (`--allow-scripts`). `openclaw` itself ran fine without its postinstall in
    the trial, but S2 must confirm `npm install -g` on the node 24 image leaves `koffi`/`esbuild`-dependent CLIs working.
12. Disabled-provider `plugins.entries.*` (arcee, groq, ...) only warn "plugin not installed" (also today on 6.11).

### Offline trial actually run (Mac mini, scratchpad, node 24.21.0 for 10.5 and 24.22.1 for 10.6, `HOME` redirected, no cluster contact)
- `npm install -g openclaw@2026.10.5 @openclaw/discord@2026.10.5` OK; `openclaw --version` = 2026.10.5; bundled extensions include
  telegram, ollama, openai, memory-core, tts-local-cli, elevenlabs; `codex` and `discord` are external packages (peer `>=` host).
- Used a CREDENTIAL-SCRUBBED copy of the live `openclaw.json` (read-only `kubectl exec cat`, tokens replaced, paths rewritten).
  `doctor --lint`: 1 error (agents.list). `doctor --fix --non-interactive`: migrated as in item 3, installed codex+discord managed
  plugins at 10.5.0 and created the peer links. First `--fix` attempts failed only because the trial had unset `${SPLITFAIRY_*}` env
  (ours are set in the pod). Final `--lint` after fix + deleting `channels.discord.ui`: zero config errors; remaining errors were
  trial artefacts (MCP host unreachable, gateway auth token not in trial env).
- Repeated end-to-end on 10.6 / node 24.22.1: identical result (same single `ui` error).
- NOT run: a gateway start, a model turn, Telegram, the real SQLite state migration (sessions, auth store, memory), cron, TTS, skills.

### Stage list
- **S1 git prep (no roll; ~1.5 h)**: in one reviewable commit prepared but held until S3 passes: both `node` tags ->
  `24.22.1-bookworm@sha256:6449e19d8184d84062525b6a7524def03146c2cb04a7f08b076680d0e8e4240a`; `install_npm openclaw@2026.10.6`
  and `@openclaw/discord@2026.10.6`; realign block gets the peer-link loop then `openclaw doctor --fix --non-interactive` (HOME set,
  state mounted, fails the init loudly on non-zero); idempotent config fix `del channels.discord.ui` + `ownerAllowFrom` prefix + telegram
  `defaultAccount` -> `vita` (operator decision D3); remove the dead dreaming `sed` block; `npm rebuild -g`; `upgrade.remediation`
  retries 0 for this roll only (Flux otherwise rolls back before the init finishes: 7.1 lesson). Policy: `image_major_ceiling max_major: 24`
  and renovate `allowedVersions "<25"` in the same commit (policy file reason text updated).
- **S2 scratch pod (~2 h, section D below)**; **S3 state rehearsal on a clone (~1.5 h)**; **S4 attended roll (~2 h incl. verification)**.
  Total about 7 h of work over 2 sessions plus one attended window; Telegram/Discord/cron cannot be fully proven before S4.

### S2 scratch pod spec (do not run before the operator approves)
- Own namespace-local name `openclaw-trial`, no HTTPRoute/Service, `replicas 1`, NetworkPolicy egress limited to DNS, npm registry,
  OpenAI (for the turn) and the Ollama host; image `node:24.22.1-bookworm@sha256:6449e19d...`; `emptyDir` home with the SCRUBBED config
  (secret in a throwaway Secret) and an empty workspace.
- MUST NOT have: the production PVC (even read-only), `openclaw-secret` (bot tokens, ElevenLabs, gateway token), the Stakater/reloader
  annotations, any cron, `channels.*.enabled: true`, `mcp` servers pointing at production data, the real `~/.codex/auth.json`
  (a refresh-token copy can rotate and invalidate the production login; use a separate `codex login --device-auth` for the trial, operator in a browser).
- Runs: `npm i -g` on node 24 (S1 recipe), `doctor --fix`, `doctor --lint` (Errors 0), `models list`, `openclaw agent --local` one turn each on
  `openai/gpt-6-luna` and `openai/gpt-5.6-terra` for a throwaway agent, with and without `OPENCLAW_CODEX_APP_SERVER_BIN`; `npm rebuild -g` CLI smoke.
- S3: Longhorn snapshot -> clone volume `openclaw-data-trial` (17 G, 11 G of it re-installable `lib`), mount only in the trial pod,
  channels disabled and tokens blanked by init BEFORE start, egress to the model endpoints only; run `doctor --fix`, record exactly what
  changed in `state/openclaw.sqlite` and `agents/*`, run `openclaw skills list`, `openclaw cron list`, one turn per agent id; then delete the clone.

### S4 attended roll
Preconditions: S1-S3 pass; `runbooks/longhorn-backup-age.py` shows openclaw-data backup under 24 h AND a fresh manual Longhorn snapshot taken
immediately before; `codex login status` valid; no cron due for 30 min and no in-flight `say` (avoid 06:55-07:15 and 02:55-03:15, 03:55-04:15 Berlin;
suggested slot: Saturday attended window midday); copy `openclaw.json` to `openclaw.json.bak-pre-10.6`. Roll by the single GitOps commit
(`Recreate`, verify live pod digest/startTime, not rollout status). Verify: versions 10.6.x/10.6.x/node v24.22.1; `doctor --lint` Errors 0;
canary token turn; each of the 9 agents answers (main first); Telegram RECEIVE test on both bot accounts + one group binding; Discord DM;
`openclaw cron list` unchanged (4 ids); briefing `--dry-run` then the 08:45 real send with voice; one `say`; next 03:00 DREAMS.md update and diary
text; heartbeat-state size and an hourly heartbeat that really edits; health-check.sh OpenClaw block.
**Why a revert is unsafe by itself**: `doctor --fix` rewrites `openclaw.json` (backup `.bak` kept, but 6.11 cannot read `agents.entries`/`ownership`/top-level `tts`),
copies credentials into agent SQLite, moves legacy auth-store/memory-core rows into `state/openclaw.sqlite`, and repairs session schema; 6.11 does not
understand the new schema. Rollback therefore = `git revert` the roll commit AND restore the pre-roll Longhorn snapshot/backup of `openclaw-data`
(scale to 0 / Recreate, restore volume, then reconcile). Anything written between roll and rollback (chat sessions, memory) is lost; keep the window short.

### Decisions for the operator
D1 attended slot (Saturday/Sunday, not near a briefing or the sweep trigger); D2 accept ~7 h prep plus a 2 h window; D3 whether to fix the
Telegram `defaultAccount`, Discord `ownerAllowFrom` and voice-agent fallbacks now or just warn; D4 move `@openclaw/discord` in the same roll (recommended: it must match the host, only a
config key breaks) or disable discord for the first boot; D5 which agents get the answer test (recommend all 9, main + one per family member minimum) and who sends the
Telegram receive test; D6 ok to do the device-login for the scratch pod; D7 accept loss of sessions since the snapshot on rollback; D8 keep `gpt-6-luna` as primary for the roll or pin
to the known-good model for the first 24 h. Could still fail: the SQLite state migration on real data (untested), Workshop skills migration of the seeded skills, ABI of native npm addons,
Telegram poller regression, `gpt-6-luna` rejected by the 10.6 plugin, init-time `doctor --fix` exceeding the Helm timeout on a 3 GB agent store.

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
