---
plan_id: openclaw-2026.11.1
supersedes: openclaw-2026.10.5   # same upgrade, retargeted 2026-11-07 (10.5/10.6 -> newest stable 11.1)
component: openclaw
status: blocked
review: null
window: "attended full day, only on the coordinator go-live message (operator 2026-11-07: all of them, the full openclaw day); not while etcd-timeouts-5000-500 runs"
findings: [F-79c6922e, F-39d3d443]     # openclaw + @openclaw/discord 2026.6.11 -> 2026.11.1
kind: npm
current: "2026.6.11"
target: "2026.11.1"   # npm latest 2026-11-07; re-check dist-tags at run time
update_type: major
risk: high
capability_change: true       # major: new model ids, plugin set and state migrations change user-visible behaviour
rollback_class: backup-restore   # forward SQLite state migration on openclaw-data: rollback = PVC snapshot restore, not a git revert
est_duration_min: 150      # attended roll incl. backup, ~30 min boot, verification and rollback budget; happy path ~100 (rehearsal already done on clones 2026-11-07)
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
  - redis-fleet-8.10.3   # reciprocal, 2026-11-02 sweep 2ad957af
  - talos-linux-1.14.5                  # exclusive node roll evicts the pod mid-migration (reciprocal, vetted)
  - etcd-timeouts-5000-500              # sun-attended 2026-11-08: restarts etcd on all control-plane nodes; must not overlap the openclaw roll (add the reciprocal line there)
unblock_stages:                      # ONE attended day; rehearsal DONE 2026-11-07 on three cloned volumes (section R.6/R.7); next: reviewer verdict, then coordinator go-live
  - id: R-rehearsal        # DONE: gateway boot, doctor migration, per-agent auth, turns on gpt-6.1-terra fallbackUsed=False, crons, whisper, skills
  - id: P-review           # plan-reviewer-agent verdict (section G is the governing text)
  - id: A-attended-roll    # G.1 preconditions -> G.2 backup -> G.3 roll -> G.4 gates -> G.5 rollback if any gate fails
backup_gate: "G.2: Longhorn Snapshot pre-openclaw-1111 readyToUse=true AND the manual backup job completes with longhorn-backup-age.py clawd-bot-data --max-hours 1 exit 0 AND the config+workspace tarball lists files AND openclaw.json.bak-pre-11.1 exists in the pod. All four must PASS before the push."
restore_proof: "R.1/R.7: the same backup family (backup-92bafe79c04542f2, 2026-11-06) was restored into three scratch volumes in ~9 min each and booted on 2026.11.1; the snapshot-revert path is G.5 step 3 (Longhorn snapshot CR creation verified on a scratch volume, readyToUse=true in seconds)."
premises:
  - id: live-image-still-node-22
    why: "current: and the rollback target assume the live pod still runs the node 22 / 2026.6.11 image; if the Deployment already moved, the baseline is wrong."
    run: kubectl get deploy -n ai openclaw -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: node:22.
  - id: manifest-pin-still-6.11.1
    why: "The change set is a diff against this exact helmrelease; a changed pin means the diff no longer applies."
    run: grep -c 'install_npm openclaw@2026.6.11' /Users/mu/code/cberg-home-nextgen/kubernetes/apps/ai/openclaw/app/helmrelease.yaml
    expect_exact: "1"
  - id: helmrelease-last-commit-unchanged
    why: "Another agent edits OpenClaw files; a newer helmrelease commit than the one the diff was made against must be re-read before the roll (git apply --3way may still pass)."
    run: git log -1 --format=%h -- kubernetes/apps/ai/openclaw/app/helmrelease.yaml
    expect_exact: 1cbf86998
  - id: strategy-is-recreate
    why: "RWO Longhorn PVC + replicas 1: RollingUpdate would Multi-Attach-deadlock; the roll relies on Recreate."
    run: kubectl get deploy -n ai openclaw -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: data-volume-healthy
    why: "The rollback is a snapshot revert on this volume; a degraded volume turns it into a data risk."
    run: kubectl get volume -n storage clawd-bot-data -o jsonpath='{.status.robustness}'
    expect_exact: healthy
  - id: anthropic-secret-key-present
    why: "The change set references Secret anthropic-api-key (not optional); a missing Secret fails the pod at start."
    run: kubectl get secret -n ai anthropic-api-key -o jsonpath='{.data}'
    expect_contains: ANTHROPIC_API_KEY
  - id: openclaw-kustomization-ready
    why: "A Kustomization already failing would make a post-roll failure unattributable."
    run: flux get kustomization openclaw -n ai
    expect_contains: "True"
---

# openclaw 2026.6.11 -> 2026.11.1

> Sections 0a-7 below were written for 10.5/10.6 and are kept as reference; where they differ, section R (this
> retarget, 2026-11-07) governs. `review` is set only by the plan-reviewer outcome; R.2 blockers are resolved in R.6/R.7.

## G. Governing execution plan (2026-11-08; supersedes the timeline in 0b)

**Status:** rehearsed end-to-end on a cloned PVC (R.6/R.7 results). Vetting stamps are set only by the plan-reviewer outcome (see frontmatter `review`).
**Operator authorisation:** chat 2026-11-07, "All of them we do the full openclaw day"; coordinator sends the go-live message; execute via the maintenance-window path. The operator is NOT needed for a browser step IF the production codex login is still valid (`codex login status` in the live pod before the roll).
**Change set:** `runbooks/maintenance/plans/openclaw-2026.11.1.changeset.diff` (3 files: helmrelease, `runbooks/auto-update-policy.yaml` `max_major` 22 -> 24, `.github/renovate.json5` `allowedVersions` `<23` -> `<25`; one commit). It is a unified diff against the helmrelease as of commit `6cd501125`; apply with `git apply --3way runbooks/maintenance/plans/openclaw-2026.11.1.changeset.diff` and re-read the helmrelease diff if `git log -3 -- kubernetes/apps/ai/openclaw/app/helmrelease.yaml` shows newer commits than `1cbf86998`.
Contents: node 24.22.2-bookworm digest-pinned (app + init); openclaw / `@openclaw/discord` 2026.11.1; raw install + peer links for codex, discord, duckduckgo-plugin in the init; root `chmod 755 /home/node; chmod 1777 /tmp` (+ `tmp` mounted in init); config guard bridges `agents.list` <-> `agents.entries`, writes whisper into `tools.media.models` (env form, 4 threads) without duplicates, deletes `channels.discord.ui`, raises `bootstrapMaxChars` 40000 / total 80000; skill frontmatter repair; `doctor --fix` loop (4 passes, parks refused Codex sidecars in `~/.openclaw/doctor-held`, fails loud); `plugins install` (trusted-official) for codex / discord / duckduckgo; per-agent openai auth import; container env `OMP_NUM_THREADS`/`MKL_NUM_THREADS`=4, `resources.limits.cpu` 4, `ANTHROPIC_API_KEY` from Secret `anthropic-api-key` (not optional; provider detection only, primary stays `openai/gpt-6.1-terra`, no anthropic model in fallbacks); Reloader annotation lists `anthropic-api-key`; `upgrade.timeout` 40m, `remediation.retries: 0`, `remediateLastFailure: false`, startup probe `failureThreshold` 180 (30 min).

### G.1 Preconditions (all must hold; abort otherwise)
```bash
cd /Users/mu/code/cberg-home-nextgen
OC=$(kubectl -n ai get pod -l app.kubernetes.io/instance=openclaw -o jsonpath='{.items[0].metadata.name}')
kubectl -n ai exec "$OC" -c app -- codex login status                 # must say Logged in using ChatGPT (the auth import reuses this file)
kubectl -n ai exec "$OC" -c app -- openclaw cron list                 # NO job due in the next 45 min; avoid 06:55-07:15 and 08:40-09:00 Berlin; 8163c139 sweep trigger not due
N_CRON=$(kubectl -n ai exec "$OC" -c app -- bash -lc 'openclaw cron list | grep -a -c "^[0-9a-f]\{8\}-"'); echo "N_CRON=$N_CRON"   # record it: G.4 compares to it (32 on 2026-11-08; the Maintenance Window job cd659ac2 already shows status err before the roll, a baseline, not a regression)
kubectl -n ai exec "$OC" -c app -- bash -lc 'ls -t ~/clawd/.tmp/say/ 2>/dev/null | head -1; pgrep -af "[s]ay|tts" || echo no-inflight-say'
npm view openclaw dist-tags --json                                    # latest must still be 2026.11.1; if it moved, stop and re-plan
git status --short kubernetes/apps/ai/openclaw runbooks/auto-update-policy.yaml .github/renovate.json5   # clean
git -c rebase.autoStash=true pull --rebase origin main
git apply --check runbooks/maintenance/plans/openclaw-2026.11.1.changeset.diff
```
The operator is using the live assistant (Telegram group sessions): confirm with the coordinator that this is the agreed quiet window. Never roll during a due cron or an in-flight `say` (07:01 incident). `etcd-timeouts-5000-500` (sun-attended 2026-11-08) must be finished first; `open-webui-0.13.0` and `anythingllm-1.19` also touch namespace `ai`: do not run them in the same window.

### G.2 Backup (rollback depends on these; do not skip)
The snapshot is taken with the pod live, so it is crash-consistent (SQLite WAL replays), not quiesced. **Loss window:** anything written after the snapshot (sessions, Telegram state, cron runs) is lost on a snapshot-revert rollback, so take the snapshot as late as possible: right before the push, after G.1 passes.
```bash
# 1. Longhorn snapshot of the live volume (CR form verified on the rehearsal clone: readyToUse=true in seconds)
kubectl apply -f - <<'EOF'
apiVersion: longhorn.io/v1beta2
kind: Snapshot
metadata: {name: pre-openclaw-1111, namespace: storage}
spec: {volume: clawd-bot-data, createSnapshot: true}
EOF
kubectl -n storage get snapshots.longhorn.io pre-openclaw-1111 -o jsonpath='{.status.readyToUse}{"\n"}'   # must print true
# 2. Off-volume copy (Longhorn backup): wait for the manual job, then require a backup < 1 h old (exit code gates it)
kubectl create job --from=cronjob/daily-backup-all-volumes manual-backup-openclaw-1111 -n storage
kubectl -n storage wait --for=condition=complete job/manual-backup-openclaw-1111 --timeout=45m && python3 runbooks/longhorn-backup-age.py clawd-bot-data --max-hours 1 || { echo "BACKUP GATE FAILED: stop"; exit 1; }
# 3. Tarball of config + workspace to the Mac (outside the repo)
mkdir -p ~/Backups/openclaw-pre-11.1 && kubectl -n ai exec "$OC" -c app -- tar czf - -C /home/node .openclaw/openclaw.json clawd clawd-juno-andrea clawd-vita-mathias clawd-vita-andrea clawd-vita-margaret clawd-vita-cora clawd-jerry-mathias clawd-jerry-andrea clawd-voice --exclude=node_modules > ~/Backups/openclaw-pre-11.1/openclaw-config-workspaces.tgz && tar tzf ~/Backups/openclaw-pre-11.1/openclaw-config-workspaces.tgz | head -3
kubectl -n ai exec "$OC" -c app -- cp /home/node/.openclaw/openclaw.json /home/node/.openclaw/openclaw.json.bak-pre-11.1   # absolute paths: no remote shell here, a ~ would expand on the Mac
kubectl -n ai exec "$OC" -c app -- ls -l /home/node/.openclaw/openclaw.json.bak-pre-11.1
```

### G.3 Roll (GitOps, one commit)
```bash
git apply --3way runbooks/maintenance/plans/openclaw-2026.11.1.changeset.diff
git diff --stat                                                           # exactly: renovate.json5, helmrelease.yaml, auto-update-policy.yaml
git add .github/renovate.json5 kubernetes/apps/ai/openclaw/app/helmrelease.yaml runbooks/auto-update-policy.yaml   # explicit paths, never -A
printf 'feat(openclaw): 2026.6.11 -> 2026.11.1 on node 24 (plan openclaw-2026.11.1)\n\n...\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_012bXdxrZGGHNy5e4RnF6seD\n' > "$MSG"   # write BEFORE the hook gate
git commit --only .github/renovate.json5 kubernetes/apps/ai/openclaw/app/helmrelease.yaml runbooks/auto-update-policy.yaml -F "$MSG"
git show --stat HEAD && git log -1 --format=%s && git push
```
Then watch (no manual reconcile needed; the webhook applies it): `kubectl -n ai get pod -l app.kubernetes.io/instance=openclaw -w`; init ~5 min; app container boot before the port opens ~20-25 min on first boot (doctor passes ~2.5 min each, plugin installs ~1.5 min, per-agent auth import ~1.5 min x 8); `kubectl -n ai logs deploy/openclaw -c app -f` shows `doctor --fix pass`, `openai auth imported for agent ...`. The Deployment is `Recreate`: the old pod stops first. Verify the live pod `startTime` and image digest changed (`kubectl -n ai get pod -l app.kubernetes.io/instance=openclaw -o jsonpath='{.items[0].status.startTime} {.items[0].spec.containers[0].image}'`), not just rollout status.
**Expected downtime of the assistant: 25-35 minutes** (old pod stopped -> gateway listening); budget 60. Hard rollback cutoff: gateway not listening and `doctor`/boot not progressing 45 min after the push.

### G.4 Verification gates (one `set -e` block; every line is an assertion and aborts on failure; all must pass; save it as a script file and run it with `bash`, so a failure does not close the operator's interactive shell)
```bash
set -euo pipefail
OC=$(kubectl -n ai get pod -l app.kubernetes.io/instance=openclaw -o jsonpath='{.items[0].metadata.name}')
X() { kubectl -n ai exec "$OC" -c app -- bash -lc "$1"; }
JQ_TURN="import sys,json;t=sys.stdin.read();d=json.loads(t[t.find('{'):]);m=d['result']['meta'];assert m['agentMeta']['model']=='gpt-6.1-terra' and m['executionTrace']['fallbackUsed'] is False, (m['agentMeta'].get('model'),m['executionTrace'].get('fallbackUsed'));print(d['result']['payloads'][0]['text'][:60])"
[ "$(X 'node -v')" = "v24.22.2" ]
[ "$(X "jq -r .version ~/.openclaw/lib/node_modules/openclaw/package.json")" = "2026.11.1" ]
[ "$(kubectl -n ai get deploy openclaw -o jsonpath='{.spec.strategy.type}')" = "Recreate" ]
# plugins: positive assertion paired with the absence gate (an empty/rotated log alone proves nothing)
[ "$(X 'openclaw plugins inspect codex --runtime --json' | jq -r '[.plugin.status,.plugin.trust.reason,.plugin.version]|@tsv')" = $'loaded\ttrusted-official\t2026.11.1' ]
[ "$(X 'openclaw plugins inspect duckduckgo --runtime --json' | jq -r '.plugin.status')" = "loaded" ]
[ "$(X 'openclaw plugins inspect discord --runtime --json' | jq -r '.plugin.status')" = "loaded" ]   # trust record-missing is expected (global install)
[ "$(kubectl -n ai logs "$OC" -c app | grep -a -c 'ERR_MODULE_NOT_FOUND\|Cannot find package' || true)" = "0" ]
X 'openclaw config validate' | grep -q 'Config valid'
[ "$(X 'openclaw doctor --lint' | python3 -c "import sys,json;print(sum(1 for l in sys.stdin if l.startswith('{') for f in json.loads(l)['findings'] if f['severity']=='error'))")" = "0" ]   # Errors: 0 (the splitfairy MCP check needs the live URL: it must pass in prod)
X 'openclaw models status' | grep -a 'Default' | grep -q 'openai/gpt-6.1-terra'
X 'openclaw models status' | grep -a 'Fallbacks' | grep -q 'ollama/gemma4:26b-mlx'
if X 'openclaw models status' | grep -a 'Fallbacks' | grep -qi anthropic; then echo "GATE FAIL: anthropic model in fallback chain"; false; fi   # (a '!'-negated pipeline is exempt from set -e: do not use it)
# live turn on the primary, fallback must not be used (assert inside JQ_TURN)
X 'openclaw agent -m "Reply with exactly this token: CANARY7F3" --session-id hc-1111 --timeout 150 --json' | python3 -c "$JQ_TURN" | grep -q CANARY7F3
# tool turn
X 'openclaw agent -m "Use your shell tool to run: echo TOOLOK-\$((6*7)) and reply with only the tool output." --session-id hc-tool --timeout 200 --json' | grep -a -q 'TOOLOK-42'
# answer test on EVERY openai agent (voice is ollama-native by design): primary model, fallbackUsed False
for a in main juno-andrea vita-mathias vita-andrea vita-margaret vita-cora jerry-mathias jerry-andrea; do
  X "openclaw agent --agent $a -m 'Reply with exactly: OK-$a' --session-id ans-$a --timeout 120 --json" | python3 -c "$JQ_TURN" | grep -q "OK-$a"
done
# cron store intact: same job count as recorded in G.1, the four named ids present
[ "$(X 'openclaw cron list | grep -a -c "^[0-9a-f]\{8\}-"')" = "$N_CRON" ]
for id in 0788b8a7 d55acccd 8163c139 e9ce4ac3; do X "openclaw cron list | grep -a -q '^$id'"; done
X 'home-operation list' | grep -q .
X 'cd ~/clawd && python3 scripts/morning_briefing.py --dry-run' | grep -a -q 'Good morning'
# whisper: exactly one audio model entry, env form, 4 threads
[ "$(X "python3 -c \"import json;m=json.load(open('/home/node/.openclaw/openclaw.json'))['tools']['media']['models'];print(len(m),m[0]['command'],m[0]['args'][0])\"")" = "1 env OMP_NUM_THREADS=4" ]
# skills: none skipped, and a repaired one now carries its description (positive check)
[ "$(X "head -4 ~/clawd/skills/gcal/SKILL.md | grep -c '^description:'")" = "1" ]
[ "$(X 'openclaw skills list 2>&1 | grep -a -c "description is required" || true')" = "0" ]
# ANTHROPIC key in the pod equals the Secret (hash compare, value never printed)
LIVE=$(kubectl -n ai get secret anthropic-api-key -o jsonpath='{.data.ANTHROPIC_API_KEY}' | base64 -d | shasum -a 256 | cut -c1-12)
POD=$(X 'printf %s "$ANTHROPIC_API_KEY" | sha256sum | cut -c1-12'); [ -n "$POD" ] && [ "$LIVE" = "$POD" ]
X 'openclaw models status' | grep -a -q 'anthropic .*source=env: ANTHROPIC_API_KEY'
# no agent silently fell back since the roll
[ "$(kubectl -n ai logs "$OC" -c app | grep -a -c 'No route-compatible authentication source' || true)" = "0" ]
echo ALL-AUTOMATED-GATES-PASS
```
Plus the human/channel gates (substitute for what cannot be rehearsed with blanked tokens): **Telegram RECEIVE probe** (operator or a family member sends a message to each bot account `vita`, `jerry` and one group binding; the agent replies, `grep -a "telegram" ` log shows inbound; a wedged poller sends but never receives, `kill 1` recovers), Discord DM, one `say` voice note (local Qwen3-TTS or the ElevenLabs fallback), `runbooks/health-check.sh` OpenClaw block (plugin skew ALIGNED, canary, skill-bin presence), health of the next 08:45 briefing (first real voice send after the roll; Sunday-morning checkpoint) and the 03:00 dreaming run (`DREAMS.md` gets real diary text).
Not rehearsable and therefore watched after the roll: real Telegram/Discord traffic, the 08:45 briefing with voice, dreaming narrative timeout (the old `NARRATIVE_TIMEOUT_MS` sed no longer matches; the narrative now uses the agent timeout), whisper on a real voice note, the "reply session initialization conflicted" loop (our `session-accessor-*.js` patch targets `.js`; 11.x ships `.mjs`, so the block is a logged WARN no-op: verify upstream fix by watching for the loop).

### G.5 Rollback (decide by the cutoff in G.3 or any failed gate). ORDER MATTERS: freeze Flux and stop the pod BEFORE anything else, otherwise Flux boots 2026.6.11 on the already-migrated state.
1. `flux suspend kustomization openclaw -n ai` then `kubectl -n ai scale deploy/openclaw --replicas=0`; wait until no openclaw pod exists.
2. Restore the data: revert volume `clawd-bot-data` to snapshot `pre-openclaw-1111` (Longhorn UI: `kubectl -n storage port-forward svc/longhorn-frontend 8080:80`; Volume -> attach in maintenance mode -> Snapshots -> Revert -> detach). **Everything written since that snapshot (sessions, Telegram state, cron runs) is lost** (this is the loss window G.2 names). If the snapshot is unusable, restore the Longhorn backup taken in G.2 into a new volume and rebind per `docs/sops/backup.md` (Case B: the PV `volumeHandle` is immutable, via GitOps).
3. `git revert <roll commit>` and push (restores node 22, 2026.6.11, `max_major` 22, `<23`, the 15m helm timeout and remediation).
4. `flux resume kustomization openclaw -n ai`; Flux scales to 1 and boots 2026.6.11 on the restored data. If helm is stuck in `pending-upgrade`: `helm rollback openclaw <last-deployed> --wait=false`, then reconcile.
5. Restore `openclaw.json` from `openclaw.json.bak-pre-11.1` (or the tarball) only if the volume revert was not used.
6. Verify 2026.6.11: canary turn (`gpt-6.1-terra` needs the 6.11 overlay + `OPENCLAW_CODEX_APP_SERVER_BIN`, both preserved by the revert), `openclaw cron list` count == `N_CRON`, Telegram receive.
Expected rollback duration 20-30 min (snapshot revert + 6.11 boot, which re-runs the old init).

### G.6 Follow-ups after a verified roll (separate commits)
Revert `upgrade.timeout`/`remediation` to 15m / retries 3 and the startup probe to 30; remove the dead dreaming `sed` and `session-accessor` patch blocks once the 11.x behaviour is confirmed; move `OPENCLAW_CODEX_APP_SERVER_BIN` and the openai model overlay out only after a separate rehearsal (they are kept, unchanged, in this roll); schedule a node 26 rehearsal before raising the Renovate cap past 24; close F-79c6922e / F-39d3d443 and refresh AR-075 / AR-076.

## R. Retarget and cloned-PVC rehearsal result, 2026-11-07 (openclaw-agent)

**Verdict (R.1-R.7, historical): the doctor blocker was root-caused and fixed, and every rehearsable gate passed on a cloned PVC. The governing text is Section G; the live roll happens only on the coordinator go-live message after the reviewer verdict.**

Operator direction applied: newest stable of everything, old node-22 and 9.x exclusions ignored. Targets: openclaw
2026.11.1 (`latest`), `@openclaw/codex` + `@openclaw/discord` 2026.11.1 (peer `>=2026.11.1`), `@openai/codex` unpinned
(init installs newest), node 24.22.2-bookworm digest-pinned (`sha256:8fa96264...`; 24.22.1 tag was rebuilt in place to a
different digest). Node 26 was NOT compared: the rehearsal never got past doctor, so no node A/B can be measured yet.
engines for 11.1: `>=24.16.0 <25 || >=26.1.0`.

**Rehearsal setup (scratch objects, all labelled `purpose=openclaw-rehearsal-2026-11-07`, production untouched):**
Longhorn Volume `openclaw-trial-data` and `openclaw-trial2-data` (storage ns) restored from backup `backup-92bafe79c04542f2`
(2026-11-06 23:08Z, ~9 min restore), PV/PVC of the same names in `ai`, Secret `openclaw-trial-secret` (every credential blanked),
Deployments `openclaw-trial` / `openclaw-trial2` (scaled to 0). Pod spec rendered with `helm template` from the modified
HelmRelease so the init script ran verbatim; app container held on `sleep infinity` and the boot steps run by hand.

**R.1 Measured, passing**
- Init (node 24.22.2) installs cleanly: `openclaw --version` 2026.11.1; managed plugins `@openclaw/codex` and `@openclaw/discord`
  both 2026.11.1; the peer symlink loop creates `.../@openclaw/codex/node_modules/openclaw`. Old `ERR_MODULE_NOT_FOUND`: NOT
  reproduced at install/doctor time (the plugin path never crashed). It is untested at gateway boot and on a model turn
  because those are behind R.2.
- Agent DB schema migration v1 -> v27 for all 9 agents ran in the first doctor pass (pre-migration `.bak` copies written per db).
- Doctor wall-clock 1m20s to 2m40s per pass on the ~28 GB store (well under the 15m Helm timeout), but it needs several passes.

**R.2 Blocking defects (each measured; fixes in R.3 are required but NOT sufficient)**
1. `/tmp` (emptyDir, fsGroup) is mode 2777 and `/home/node` (PVC root) is 2775: doctor refuses ("temp workspace ancestor /tmp has
   group/world-writable mode 2777 without sticky protection", "SQLite staging ancestor must not allow another user to replace
   its child: /home/node"). `TMPDIR` is ignored (preferred dir is hard-coded `/tmp/openclaw`). Fixed in the modified init:
   `chmod 755 /home/node; chmod 1777 /tmp` as root, plus the `tmp` emptyDir also mounted into the init container. Verified: `/tmp` drwxrwsrwt afterwards.
2. `channels.discord.ui: {}` (on the PVC config) is rejected by the 11.x discord schema and makes doctor treat the config as
   "unavailable"; delete the key before doctor. (Same residual error as the 10.x offline trial.)
3. **Unresolved blocker.** With 1 and 2 fixed, `doctor --fix --non-interactive` still exits 1 with "Plugin migration source
   config changed or could not be read; rerun Doctor" and never performs the `agents.list -> agents.entries` migration
   (`doctor --lint` keeps reporting `agents.list moved to keyed agents.entries`). Reruns (x5), `--force --yes`, and
   `openclaw update repair --yes --no-restart` (6 min; reports "Plugin duckduckgo data/settings upgrade is unfinished") all fail identically.
   Also tried: moving the one refused Codex binding sidecar aside (a doctor step "plugin-doctor-state" refused it as
   "current plugin state changed"; other 21 sidecars migrated fine), hand-converting `agents.list` to `agents.entries`
   (doctor then asks for "explicit surface owners" and still fails the same way), and removing the duckduckgo web_search entry.
   Doctor's own config read reports "Config unavailable" at start-up, i.e. the plugin migration cannot read the legacy-shaped config.
   The 2026-10-23 Mac trial on 10.5/10.6 completed this migration, so 11.1 (or the real, larger PVC state) behaves differently.
4. The app-container config guard (init node script in the HelmRelease) is written against `cfg.agents.list` (managed agent
   set, bindings, splitfairy deny-list). After a successful doctor migration it must read/write `agents.entries` plus the
   explicit `agents.ownership` surface owners. This rewrite cannot be validated until R.2.3 is solved.

**R.3 Change set prepared (NOT pushed; diff at the scratchpad, 89 lines):** both node tags to the 24.22.2 digest, `install_npm openclaw@2026.11.1` + `@openclaw/discord@2026.11.1`, peer-link loop after the managed realign, root `chmod` of `/home/node` and `/tmp` at init start, `tmp` mounted into init. Still to add once R.2.3 is solved: delete `channels.discord.ui`, `openclaw doctor --fix --non-interactive` (loop until clean, fail loud) between the config guard and `exec openclaw gateway`, entries-aware config guard, `runbooks/auto-update-policy.yaml` `max_major` 22 -> 24 and `.github/renovate.json5` `allowedVersions` `<23` -> `<25` (or removed) in the SAME commit.

**R.4 Gates the final plan must carry (unchanged ask):** live turn on `openai/gpt-6.1-terra` with fallbackUsed=false; `cron list` identical (4 ids); Telegram send AND received-message probe; home-operation CLI; `doctor` Errors 0; managed `@openclaw/codex` loads with no ERR_MODULE_NOT_FOUND at gateway boot; wizard check. None of these ran (blocked before gateway boot). A codex device-login for the trial (never copy production auth.json) is also still outstanding.

**R.5 Next steps / retest trigger:** (a) file an upstream issue with the support bundle the repair wrote (`~/.openclaw/logs/support/openclaw-diagnostics-*.zip` on the trial2 volume); (b) retest on each new `latest` (2026.11.5-beta.1 exists; do not take it unless it becomes `latest`) with the same clone procedure; (c) if still failing, bisect state: restore a clone, strip `plugins.entries` stale ids and unset non-essential channels/plugins until doctor reads the config; (d) rollback class unchanged: this stays an attended-day, snapshot-restore plan. Scratch objects remain for the retest: volumes `openclaw-trial-data`, `openclaw-trial2-data`, Secret `openclaw-trial-secret`, Deployments scaled to 0; remove with `kubectl -n ai delete deploy openclaw-trial openclaw-trial2 openclaw-trial3; kubectl -n ai delete pvc openclaw-trial-data openclaw-trial2-data openclaw-trial3-data; kubectl delete pv openclaw-trial-data openclaw-trial2-data openclaw-trial3-data; kubectl -n storage delete volume openclaw-trial-data openclaw-trial2-data openclaw-trial3-data; kubectl -n ai delete secret openclaw-trial-secret anthropic-trial-dummy`.

### R.7 Full gate results on the third clone (2026-11-07/08; trial3, node 24.22.2, cpu limit 4, gateway with `OPENCLAW_SKIP_CRON/CHANNELS/GMAIL_WATCHER=1`, `cron.enabled=false`, blanked tokens, own codex login, nothing sent to real users)

| Gate | Result |
|---|---|
| `doctor --fix` with the login present | exit 0; auth-profile store imported to SQLite, legacy file archived |
| `@openclaw/codex` load / ERR_MODULE_NOT_FOUND | `loaded`, `trusted-official` after `plugins install`; 0 hits in 4 gateway logs. **Old blocker not reproduced.** |
| Live turn, primary | **`openai/gpt-6.1-terra`, `fallbackUsed=False`** (after the per-agent auth import below); tool turn: 1 `exec` call, 0 failures, output `TOOLOK-42` |
| Answer test, 8 openai agents | all 8 `openai/gpt-6.1-terra` fallbackUsed False; `voice` stays `ollama-native/gemma4:26b-mlx` by design |
| `openclaw cron list` | 41 jobs, `0788b8a7`, `d55acccd`, `8163c139`, `e9ce4ac3` present |
| `home-operation list` / `--help` | works; briefing `--dry-run` builds English text (blanked upstreams print their expected fetch notes) |
| whisper `env` form after doctor | survives, but the legacy guard appended one duplicate `tools.media.models` entry per boot (4 after 3 boots); fixed (guard writes `tools.media.models`, replaces its audio entry): 1 entry after 3 boots |
| whisper timing, 175 s real .ogg, cpu limit 4 | 4 threads 56 s / 48 s, 2 threads 57 s, uncapped 43 s: **no measurable speed difference at limit 4** (whisper `tiny` is ~3.5x realtime either way). The cpu limit/threads change protects the gateway from starvation; it is not a speed-up. The 2-CPU run was ~60 s per transcription as well. |
| skills `description:` | 8 skills (`fax`, `gcal`, `mealie`, `mealplan`, `shoplist` main; `gcal`, `mealie`, `mealplan` juno-andrea) are PVC-only (not in the SOPS configmap), so the fix is an idempotent init step adding frontmatter from the first heading; 0 "Skipping invalid skill" afterwards |
| TOOLS.md -> AGENTS.md | doctor merges once (AGENTS.md 24551 bytes, unchanged over 3 later boots); the init re-seeds TOOLS.md every boot, so the warning "still stores local tool notes in TOOLS.md" persists (warning only); `bootstrapMaxChars` raised to 40000 / total 80000 so the merged file is not truncated at 20000 |
| `ANTHROPIC_API_KEY` (dummy value in the trial only) | `openclaw models status`: providers `anthropic`, `anthropic-openai`, `claude-cli` detected via env; `Default` still `openai/gpt-6.1-terra`, `Fallbacks` still `ollama/gemma4:26b-mlx`; doctor unaffected; in-pod env hash equals the expected hash. Note `claude-cli` also picks the key up. |
| `doctor --lint` | 0 errors except the splitfairy MCP schema check (blanked URL in the trial; expect pass in prod); warnings: heartbeat in HEARTBEAT.md, plaintext secret fields, LAN bind, TOOLS.md |
| Boot time | init ~5 min; app container to "boot sequence done" ~9 min on a migrated state (doctor loop + plugin check + 8 x `auth list`); first boot on an unmigrated clone: 2 doctor passes ~2.5 min each, plus ~12 min of per-agent auth import |

**Defects found by this rehearsal and fixed in the change set:** /tmp and /home/node permissions; `channels.discord.ui`; doctor sidecar refusal; duckduckgo external plugin; raw-npm plugins "provenance-invalid" (use `plugins install`); `plugins install --force` is NOT idempotent for discord on a 2nd boot (skip when trusted-official, warn otherwise; discord then runs from the init's global install with trust `record-missing`, loaded); skills frontmatter; duplicate whisper models; `bootstrapMaxChars`; helm 15m timeout / 3 retries / startup probe 5 min would roll the release back mid-migration; and **per-agent openai auth**: 2026.11.1 has no read-through from `main`. Without the import only `main` reaches openai; the other 7 agents silently answer from the local gemma fallback (`fallbackUsed=True`, reason "No route-compatible authentication source is configured for openai"). `agents.defaults.authInheritance.agentId: main` did NOT fix it. `models auth login` imports `~/.codex/auth.json` without a browser, `models auth activate` verifies it but pins the agent to `openai/gpt-6-astra@profile` (so the pin is unset), ~86 s per agent, the gateway must be stopped. The change set automates this in the app container before `exec openclaw gateway`.

**Scratch objects (cleanup in R.5):** now also `openclaw-trial3-data` volume/PV/PVC, Deployment `openclaw-trial3`, Secrets `openclaw-trial-secret` and `anthropic-trial-dummy`.


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

### R.6 Bisect result (2026-11-07, later): root cause of R.2.3 found and fixed in rehearsal

**Root cause:** the PVC config has `tools.web.search.provider: "duckduckgo"` (added 2026-11-07, 8f51d787e). In 2026.11.1 the DuckDuckGo
provider is NOT in the host package any more; it is the external package **`@openclaw/duckduckgo-plugin`** (2026.11.1, peer `>=2026.11.1`).
With it absent doctor's plugin-migration step cannot read the legacy-shaped config and aborts the whole run with the generic
"Plugin migration source config changed or could not be read". Bisect (scrubbed config, fresh empty state, 8 variants): removing
`plugins.entries`, channels, `mcp`, `skills` or `tools.media/deny` did NOT help; removing `tools` fixed it; within it only `tools.web`
(or just `tools.web.search.provider`) fixed it. Installing the package into the managed store (raw npm + peer link) also fixed it.
Second, independent doctor refusal: one live session's Codex binding sidecar ("current plugin state changed at session-key:main:...");
parking the refused `*.codex-app-server.json` (not `.migrated`) in `~/.openclaw/doctor-held` lets the remaining steps run.

**End-to-end on a third clone (node 24.22.2, openclaw 2026.11.1), with the prepared change set:**
- init + app boot sequence: doctor pass 1 refused (sidecar), pass 2 completed; `openclaw config validate` = valid; `agents.entries` (9 agents) + `agents.ownership: explicit`; `tts`, `memory`, `talk` top-level keys created; `channels.discord.ui` gone.
- **ERR_MODULE_NOT_FOUND re-test: not reproduced.** Gateway started, loaded `codex` from `~/.openclaw/npm/projects/openclaw-codex-*/node_modules/@openclaw/codex` (0 `ERR_MODULE_NOT_FOUND`/`Cannot find package` hits in the gateway log), `/codex` command registered, 19 plugins incl. discord, duckduckgo, telegram, memory-core.
- NEW: raw `npm install` into the managed store leaves `@openclaw/codex` at trust `provenance-invalid` (doctor: "Plugin codex is unavailable: not a bundled or verified official installation") and capability consent pending. `openclaw plugins install @openclaw/<pkg>@<ver> --force --accept-capabilities` (needs a valid config, so AFTER doctor) sets `trusted-official`, relocates the plugin under `npm/projects/` and links the peer itself. Added to the change set for codex, discord, duckduckgo-plugin.
- `openclaw cron list`: 41 jobs retained, incl. `0788b8a7`, `d55acccd`, `8163c139`, `e9ce4ac3`. Caution: a gateway started on a clone RUNS the cloned crons; it was stopped within minutes, credentials were blanked and the cloned `~/.codex/auth.json` was removed first (never use it: refresh-token rotation could invalidate production).
- NEW, must fix before the roll: 8 workspace skills are skipped as "description is required": `fax`, `gcal`, `mealie`, `mealplan`, `shoplist` (main workspace) and `gcal`, `mealie`, `mealplan` (juno-andrea). Add a YAML frontmatter `description:` to those `skill-*.md` seeds in the SOPS skills configmap.
- NEW warnings: `AuthProfileMigrationRequiredError` for agent main (auth store legacy credential migration; needs the codex login present and a doctor pass with it), TOOLS.md -> AGENTS.md migration would exceed `bootstrapMaxChars` 20000 (24377 chars) for main (raise `agents.entries.main.bootstrapMaxChars`), heartbeat instructions still in HEARTBEAT.md, MCP server splitfairy schema check (needs the real URL/token).

**NOT tested (needs the operator's codex device login on a trial pod, so stopped here):** live turn on `openai/gpt-6.1-terra` with fallbackUsed=false, Telegram send and receive probe, `home-operation` CLI, briefing dry-run, `say`, whisper (doctor migrates `tools.media.audio` to capability-tagged `tools.media.models`; the guard still writes the legacy `audio` shape every boot and must be made to preserve the `env OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 whisper` form (live PVC config currently says 2; the change set uses 4 with cpu limit 4): the change set sets that form in the guard and adds `OMP_NUM_THREADS/MKL_NUM_THREADS=4` container env, but the post-migration shape is unverified), node 26 vs 24 A/B.

**Prepared change set (unpushed, 199-line diff, applies cleanly to HEAD):** node 24.22.2 digest-pinned (both containers); `openclaw@2026.11.1`, `@openclaw/discord@2026.11.1`; realign installs + peer links for codex, discord, duckduckgo-plugin; root `chmod 755 /home/node; chmod 1777 /tmp`; `tmp` emptyDir mounted into init; list<->entries bridge in the config guard; `channels.discord.ui` removal; `doctor --fix` loop (4 passes, parks refused sidecars, fails loud) + `config validate`; `plugins install --force --accept-capabilities` for the 3 plugins; whisper `env` thread cap + OMP/MKL container env (4 threads; app container `resources.limits.cpu` raised 2 -> 4 because the 2-CPU limit starved whisper while torch sees all 18 host cores). Still to add in the same commit: policy `max_major` 24 and Renovate `<25`; skills frontmatter fix; `bootstrapMaxChars`.

**Retest/next:** rerun the clone rehearsal with the operator present for the codex login (turn, Telegram receive, home-operation), then plan-review, then the attended roll. Upstream issue text is drafted in the scratchpad (not posted).

## 0a. Re-measurement 2026-11-07 (openclaw-agent): 2026.11.1 is NOT viable on node 22

- npm dist-tags: `latest` 2026.11.1, `extended-stable` 2026.9.36, `beta` 2026.11.5-beta.1.
- Node engines (registry): 2026.11.1 and 11.5-beta.1 `>=24.16.0 <25 || >=26.1.0`; extended-stable 9.36 `>=24.22.1 <25 || >=26.12.1`.
  Node 22 is excluded from EVERY version from 2026.9.3 on. The last node-22-capable release is **2026.9.2** (`>=22.22.3 <23`);
  2026.9.10 to 9.32 were never published, and 2026.9.3 to 9.9 already require 24.16. So there is no node-22 path to anything newer than 9.2.
- `@openclaw/codex` and `@openclaw/discord` 2026.11.1 exist and pin `peerDependencies.openclaw >=2026.11.1` (lockstep with the host, as with 10.6).
- Consequence: the node major (22 -> 24.22.1+) is a hard prerequisite of ANY openclaw move. It does not ride Renovate PR #279 (that PR is now
  headlamp-only, `node 24.19.0 -> 24.22.2` alpine; the openclaw node rule is file-scoped `allowedVersions "<23"`, e058e79c6, so the finding
  F-0f5cc025 split was already done). The openclaw node move ships inside the one-day roll below, with `image_major_ceiling max_major: 24` and
  Renovate `"<25"` in the same change set. Retarget recommendation: **2026.11.1** (npm `latest`) instead of 10.6, node 24.22.1, same one-day structure.
- Offline Mac trial of 11.1 on node 24.22.1 (scrubbed live config): `openclaw --version` OK; `doctor --lint` reports the same single known
  error (`agents.list moved to keyed agents.entries`). `doctor --fix` in the scratch HOME did NOT complete (state DB admission/plugin-receipt
  errors in a bare scratch home): INCONCLUSIVE, not evidence for or against. The rehearsal on a cloned PVC remains the gate.

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

### One-day attended plan (operator decisions 2026-10-23; replaces the old S1-S4 multi-session staging)

**Slot (D1):** Saturday **2026-10-31**, full day, assistant and briefing may be down all day, operator at computer and browser all day.
Confirmed by the operator 2026-10-23; alternatives considered: Sat 2026-11-07 (one more week of 10.x release soak, 7 days of margin before any Talos work) or Sun 2026-11-01
(rejected: the talos reboot window runs that day, so a failed roll would collide with it). Saturday gives a full
rollback day before the Sunday talos reboot (`conflicts_with: talos-linux-1.14.4`). Re-check `npm view openclaw dist-tags` on Thursday; if `latest` moved, keep 10.6 unless it is a fix for our path.

**Before the day (agents, no operator, Thu-Fri 10-29/30; this is the old S1):** prepare the git change as ONE reviewable change set, reviewed by plan-reviewer-agent, NOT pushed
and NOT reaching prod until the roll step. Contents: both `node` tags -> `24.22.1-bookworm@sha256:6449e19d8184d84062525b6a7524def03146c2cb04a7f08b076680d0e8e4240a`
(app AND `install-openclaw` init container: the gateway runs under the app container's node); `install_npm openclaw@2026.10.6` + `@openclaw/discord@2026.10.6`;
peer-link `ln -sfn` loop then `openclaw doctor --fix --non-interactive` (HOME set, state mounted, fails init loudly on non-zero); idempotent config fixes:
`del channels.discord.ui`, Discord `commands.ownerAllowFrom` -> `discord:user:<id>`, Telegram `defaultAccount` -> `vita`, voice-agent model object with fallbacks (D3);
remove the dead dreaming `sed` block; `npm rebuild -g`; `upgrade.remediation.retries: 0` / `remediateLastFailure: false` for THIS roll only (7.1 lesson: Flux otherwise
rolls back before init finishes; revert in a follow-up commit after verification); `runbooks/auto-update-policy.yaml` `image_major_ceiling` `max_major: 24` (reason text updated) and Renovate
`allowedVersions "<25"` in the SAME change set (these ship with the roll, not before; do not commit them early). Also prepare the rollback revert and a rollback script
(scale 0, restore volume from the pre-roll snapshot, reconcile). Pre-day checks (agents): codex login valid, `longhorn-backup-age.py` fresh, free Longhorn capacity for a 17 G clone + snapshot,
trial NetworkPolicy and Secret drafted.

**Timeline (Europe/Berlin, 2026-10-31)**

| Time | Step | Who | Operator active |
|---|---|---|---|
| 08:45-09:10 | Normal 08:45 briefing runs on production (untouched). Nothing starts until it has sent. | cron | - |
| 09:15 | Preflight: codex status, cron list, backup age, `git status` clean for the change set. Take Longhorn snapshot of `openclaw-data`, create clone volume `openclaw-data-trial` (17 G) | agents | 5 min (confirm) |
| 09:35 | Operator runs `codex login --device-auth` for the rehearsal pod in a browser (D6); separate login, NEVER a copy of production `auth.json` | operator | 5 min |
| 09:40-10:40 | **Single rehearsal (old S2+S3 merged)** on the clone: pod `openclaw-trial`, node 24.22.1 image, clone PVC mounted, channels disabled and tokens blanked BEFORE start, egress limited to DNS, npm, OpenAI, Ollama, no HTTPRoute/Service, no cron, no reloader annotation, not the production PVC or `openclaw-secret`. Runs: the prepared init script verbatim; **`doctor --fix` wall-clock on the ~3 GB agent store (must be well under the Helm timeout, record it)**; real SQLite migration (diff row counts of `state/openclaw.sqlite` and `agents/*` before/after); `doctor --lint` Errors 0; **gateway boot** to ready; model turn on `openai/gpt-6-luna` and `openai/gpt-5.6-terra` (with/without `OPENCLAW_CODEX_APP_SERVER_BIN`); one answer turn per agent id (9); `openclaw skills list` (~27 seeded skills load, init re-seed not fighting Workshop migration); `openclaw cron list` byte-compare (4 ids); `npm rebuild -g` CLI smoke (codex, gemini, claude, opencode, playwright); `say` skill dry path | agents | 0 (stand-by) |
| 10:40 | **GO/NO-GO #1**: agents present the rehearsal evidence. Any miss -> fix in git and re-run the failing slice, or abort the day (nothing in prod changed). Delete clone and trial pod. Plan status flips `blocked` -> `ready` ONLY here | operator | 10 min |
| 10:50 | Quiet start: pause the 4 crons (briefing `0788b8a7`, dreaming `d55acccd`, sweep trigger `8163c139`, retro `e9ce4ac3` - Saturday, no retro due) via the cron CLI, wait for any in-flight `say`/turn to finish | agents | - |
| 11:00 | Fresh pre-roll Longhorn snapshot AND backup of `openclaw-data`, copy `openclaw.json` -> `openclaw.json.bak-pre-10.6`, `codex login status`. **T0.** Rollback target = this snapshot (assistant quiet, so ~nothing lost) | agents | - |
| 11:10-11:40 | **Roll (old S4)**: single GitOps push (change set above), Flux reconcile (`Recreate`). Verify live pod startTime/digest, not rollout status; `kubectl -n ai logs` init to completion | agents | - |
| 11:40-12:40 | Verification (section 5, below): versions + node v24.22.1 on app AND init, `doctor --lint` Errors 0, canary, **answer test on all 9 agents (D5)**, cron list unchanged (re-enable the 4 crons only after the answer test passes), briefing `--dry-run`, one `say`, Discord DM, health-check.sh OpenClaw block, heartbeat edit works | agents | - |
| 11:50 | **Telegram RECEIVE test (D5)**: operator sends a message to both bot accounts (`vita`, `jerry`) and one group binding; agents confirm replies; wedged-poller check | operator | 15 min |
| 12:45 | **GO/NO-GO #2** (keep vs roll back). Everything green -> keep; revert `remediation` retries in a follow-up commit; resume crons if not yet | operator | 5 min |
| **13:30** | **HARD ROLLBACK CUTOFF.** If verification is not fully green by 13:30 the roll is rolled back, no extensions and no "one more fix". | rule | - |
| 13:30-14:30 | (only if triggered) Rollback: `git revert` roll commit + push, scale to 0, restore pre-roll volume, reconcile, verify 6.11 canary + crons, re-enable crons. Done by **14:30**. | agents | 10 min |
| 14:30-end | Soak, stay at the computer through the afternoon; watch the poller and heartbeat | optional | - |

Totals: wall-clock 09:15 -> ~12:45 on the happy path (about 3.5-4.5 h incl. slack), worst case rollback complete 14:30 (about 5.25 h). Operator active about 1.5 h
(5 + 5 + 10 + 15 + 5 + decisions and D8) .

**Making Sunday 2026-11-01 (talos reboot) safe**
- Failed or doubtful day: rolled back by 14:30 Saturday, so Sunday sees plain 6.11 and the talos window proceeds as planned.
- Successful day: the new version runs the Saturday night 03:00 dreaming and Sunday morning crons (first real runs of dreaming/diary and the 08:45 briefing with voice). Sunday morning checkpoint BEFORE the talos reboot starts:
  `DREAMS.md` updated with real diary text, briefing sent and voiced, Telegram poller receiving, `cron list` sane. Any miss -> restore the Saturday 11:00 snapshot (loses only the night) and talos proceeds on 6.11; do not let the node roll evict the pod while the question is open.
- Normal pod eviction by the node drain after a verified roll is just a restart on the migrated state (the init is idempotent); `conflicts_with` talos stays for the roll+rollback day only.
- The nightly 03:30 unattended window must not touch openclaw: the safe-update policy keeps the `node`/openclaw pins on the deny/ceiling logic; confirm the policy file reason covers it before Saturday.

### Operator choices: ALL DECIDED (confirmed 2026-10-23)
- **Day:** Saturday 2026-10-31 (the 11-07 alternative is dropped).
- **Hard rollback cutoff 13:30 stays**, no extensions.
- **D8 = option B:** pin the known-good `openai/gpt-5.6-terra` as primary for the first 24 h after the roll; switch back to `gpt-6-luna` in its own separate commit afterwards. The prepared change set therefore defaults to terra (overlay and `OPENCLAW_CODEX_APP_SERVER_BIN` stay). The rehearsal still tests both models.

### Accepted decisions (2026-10-23)
D2 compressed to one day (git prep by agents beforehand; one rehearsal merging scratch pod and clone; roll the same afternoon block); D3 fix Telegram `defaultAccount`, Discord `ownerAllowFrom`,
voice-agent fallbacks in the roll; D4 `@openclaw/discord` moves in the same roll; D5 answer test on all 9 agents and the operator sends the Telegram receive test; D6 operator does the codex device-login for the rehearsal;
D8 pin terra for the first 24 h; D7 fresh snapshot/backup immediately before the roll and crons paused so rollback loses ~nothing (rollback = git revert + restore pre-roll volume).
Could still fail (the rehearsal exists to catch these): SQLite state migration on real data, Workshop skills migration, native addon ABI, Telegram poller regression, luna id rejected by the 10.6 plugin, init-time `doctor --fix` exceeding the Helm timeout on a 3 GB store.

Note: sections 1-7 are the generic reference written for 10.5. Where they differ from 0b (target 2026.10.6, `openclaw.json.bak-pre-10.6`, one-day timeline, hard cutoff 13:30, rehearsal-first), 0b governs.

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
15 for the roll, 30 for verification, 15 slack). Needs an attended full day (see 0b), not the
unattended nightly. No reboot; the household assistant is down for the roll (a few
minutes) and for any rollback.
