# SOP: auto-update — SAFE Renovate PRs auto-applied at Step 0 of each maintenance window (sweep is read-only)

> Version: `2026.08.18`
> Last Updated: `2026-08-18`

## 1) Description

The daily (cron-triggered) sweep auto-merges the *safe* subset of open Renovate
PRs so the cluster stays current without the operator hand-merging every
patch/minor bump — while a mis-classified "safe" update (e.g. a patch tag that
is actually breaking) is still held for review.

The engine is `runbooks/auto-update.py`. It is **strict deny-by-default**: a PR
merges only when every gate passes. **Where it APPLIES (updated 2026-07-31):**
safe updates land in the **maintenance windows** — the `maintenance-window-agent`
runs `AUTO_UPDATE_APPLY=1 auto-update.py --apply` at Step 0 of every maintenance
window (daily since 2026-08-16 — `runbooks/maintenance-windows.yaml`). The
daily **sweep is read-only** and only DRY-RUNS the engine (rule 4c) to report
what will land next window. This split keeps observability read-only
while safe patch/minor bumps still flow automatically on the window cadence.

The core requirement — *"assess the safe level correctly"* — is met by the parse
gate plus four independent gates, not the semver label alone: the label is
necessary but not sufficient (affine `0.27.3` is a "patch" that ships a
breaking `env→config.json` change; it is caught by both the deny-list and the
release-notes scan).

Related: `runbooks/version-check.md`, `.github/renovate.json5`,
`docs/sops/monitoring.md` (alert authoring), `docs/sops/new-deployment-blueprint.md`.

## 2) Overview

- **What runs:** `runbooks/auto-update.py` (+ `runbooks/auto-update-policy.yaml`).
- **Who runs it:** the `daily-operation` sweep orchestrator, rule 4c, after the
  version specialist finishes and the verdict is reconciled.
- **The parse gate + four gates (ALL must pass):**
  0. **G0 parse** — the PR title must attribute the bump to exactly ONE
     component and ONE full target version. Two shapes are accepted:
     - **spanned** — `update <dep> ( <cur> → <new> )`, from the custom
       `commitMessageExtra` on the docker/helm/github-release `packageRules`
       in `.github/renovate.json5`.
     - **bare** — `update <dep> to <x.y.z>`, Renovate's DEFAULT extra for any
       dep NOT matched by those rules. Accepted only when the dep is a SINGLE
       token (so `update <groupName> group to vX` can never match) and the
       target is a FULL dotted version (so a major rendered as `to v2`, or
       `to latest`, is still refused). `cur` is reported as `?` with
       `cur_known=false` — nothing gates on it; safe/unsafe comes from the
       PR's update-type LABEL.

     Anything else → `gate=parse` hold. A `gate=parse` hold is now a genuine
     attribution failure, not a rendering artifact (memory:
     `feedback_version_attribution`).
  1. **G1 type** — `update_type ∈ {patch, minor}` (from the Renovate label).
     major / digest / unknown / security → hold.
  2. **G2 policy** — depName not blocked by a `deny` rule in
     `auto-update-policy.yaml`. Deny globs match **anywhere** in the dep path
     (so `siderolabs/*` blocks `ghcr.io/siderolabs/installer`). A rule may set
     `max: patch` to allow patches but hold minors of that component.
  3. **G3 breaking** — NO breaking-change signal in the PR's target release
     notes. Reuses `check-all-versions.py`'s `fetch_release_notes` +
     `detect_breaking_changes`. Best-effort: if notes can't be fetched, this
     gate is skipped and the merge relies on G2 + G4 (logged explicitly).
  4. **G4 ci** — PR `mergeable == MERGEABLE` and every CI check green. The
     repo's `flux-local` workflow renders every HelmRelease with Helm on each
     PR, so green = the manifest actually renders. Pending checks → hold this
     cycle (passes next cycle); failing checks → hold.
- **Apply guard:** merges + git ops happen ONLY when `--apply` is passed AND
  `SWEEP_TRIGGER=cron` (or `AUTO_UPDATE_APPLY=1` for an explicit operator run).
  Otherwise dry-run.
- **Post-apply gate:** after the batch merges → `git pull` → `flux reconcile`
  the affected kustomizations → wait `AUTO_UPDATE_RECONCILE_WAIT` (default 150s)
  → assert Flux HR/Ks Ready + no CrashLoop/ImagePull/high-restart pods in the
  affected namespaces. On failure → `git revert` the batch, re-reconcile, emit a
  **critical** finding, and route an `auto_update_revert` issue (keyed on the
  finding_id) to OpenClaw's `home-operation` skill for the operator — with
  `runbooks/lib/notify.py` as the fallback if the openclaw pod is down (see
  `docs/sops/maintenance-windows.md` for the contract). Exit codes: `0` ok,
  `2` applied-then-reverted, `1` error.
- **Fail-safe:** if `auto-update-policy.yaml` is missing/unparseable, the engine
  **denies everything**.

## 3) Blueprints

N/A (plain Python runbook + git-tracked policy YAML; no Authentik/Homepage/
Longhorn objects). The classifier contract lives verbatim in the
`auto-update.py` module docstring and this SOP.

## 4) Operational Instructions

Change behaviour via git (never edit a running process):

- **Add/remove a deny rule:** edit `runbooks/auto-update-policy.yaml`, bump its
  `version`, commit, push. It's git-tracked on purpose — an unattended-merge
  allowlist must be code-reviewed, not a mutable DB row.
- **Change the safe tier:** the tier is patch+minor (G1). To restrict to
  patch-only, add a global rule or tighten G1 in `auto-update.py`.
- **Tune the health-gate wait:** `AUTO_UPDATE_RECONCILE_WAIT` env (seconds).
- **Disable auto-apply entirely:** remove the `--apply` invocation from
  `daily-operation.md` rule 4c (dry-run still reports what *would* merge), or
  set the policy file aside (fail-safe denies all).

Run manually:

```bash
# dry-run classification (safe anywhere, never merges)
.venv/bin/python3 runbooks/auto-update.py
.venv/bin/python3 runbooks/auto-update.py --json      # machine-readable

# force an APPLY outside the cron sweep (operator only — merges live PRs!)
AUTO_UPDATE_APPLY=1 .venv/bin/python3 runbooks/auto-update.py --apply
```

## 5) Examples

### Example A: dry-run, one PR held (Talos)

```
== auto-update: 1 open Renovate PR(s) · policy v2026.07.25 · trigger=manual · mode=dry-run ==
⏸️  #194 ghcr.io/siderolabs/installer v1.13.6→v1.13.7 [patch] — Talos node image — needs a rolling node-reboot maintenance window, not a git merge.
== 0 safe / 1 held · dry-run (no changes) ==
```

### Example B: scheduled run, two merged + healthy

```
== auto-update: 5 open PR(s) · trigger=cron · mode=APPLY ==
✅ #201 docker.io/library/redis 8.8.0→8.8.1 [patch] — patch/minor, not denied, no breaking signal, CI green
✅ #202 ghcr.io/cloudflare/cloudflared 2026.7.2→2026.7.3 [patch] — …
⏸️  #203 ghcr.io/toeverything/affine 0.27.1→0.27.3 [patch] — breaking-change signal in release notes: env→config.json
  ✔ merged #201 redis → 8.8.1 (a1b2c3d4)
  ✔ merged #202 cloudflared → 2026.7.3 (e5f6a7b8)
-- syncing local main + reconciling 2 affected app(s) --
== applied 2 update(s), post-apply health OK ==
```

### Example C: merged, regressed, auto-reverted (the failure path)

```
  ✔ merged #210 someapp → 2.4.0 (deadbeef)
!! POST-APPLY HEALTH GATE FAILED — reverting the batch:
     - default/someapp-xxxx: CrashLoopBackOff
== ALERT: batch auto-reverted; cluster restored to pre-merge state ==
```

→ emits a **critical** `auto-update` finding; exit 2.

## 6) Verification Tests

### Test 1: classifier correctness (no live merges)

```bash
.venv/bin/python3 runbooks/auto-update.py --json | python3 -c "
import sys,json; d=json.load(sys.stdin)
print('safe:', [c['dep'] for c in d['safe']])
print('held:', [(c['dep'],c['gate']) for c in d['held']])"
```

Every `safe` entry MUST be patch/minor, absent from the deny-list, and have
green CI. Every known-risky component (affine, app-template, mariadb-minor,
Talos, nextcloud, openclaw) MUST appear in `held`.

### Test 2: policy + parse gates (offline unit check)

Run the synthetic matrix (affine/app-template/mariadb/Talos/nextcloud/openclaw →
held; cloudflared/redis → allowed; grouped/unparseable PR → held; bare
`update busybox to v1.38.0` → parses; `update Flux Operator group to v1.2.3`
and `update foo to v2` → still refused). Any mismatch means a deny glob or the
title parser is wrong — fix before the next scheduled run.

### Test 3: apply guard holds on manual runs

```bash
.venv/bin/python3 runbooks/auto-update.py --apply   # trigger is 'manual'
# MUST print the "staying read-only … manual-sweep guard" line and merge nothing.
```

## 7) Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| A risky PR classified `safe` | deny glob doesn't match the dep's registry prefix | globs match anywhere now (`_match_anywhere`); add/fix the rule + bump policy version |
| Everything held with "deny-all fail-safe" | policy YAML missing/unparseable | fix `auto-update-policy.yaml`; it's the intended fail-safe |
| Safe PR never merges | CI pending/failing, or not mergeable (conflict) | `gh pr checks <n>`; rebase/fix the PR; it retries next cycle |
| `--apply` merged nothing on cron | no PR passed all four gates | expected; check the held reasons in `--json` |
| Merge happened but no reconcile | `flux`/`kubectl` not on PATH in the sweep env | run under `sweep-run.py`/mise so tooling resolves |
| Batch reverted repeatedly | a bump genuinely breaks the app | add it to the deny-list until fixed upstream |
| A version-only patch bump held with `gate=parse` | Title matches neither the spanned nor the bare shape (grouped PR, hand-authored `bump image to sha-…`, major rendered `to v2`) | Expected — it is genuinely unattributable. Do NOT widen the regex to make one PR pass; route it through a maintenance-window plan. |

## 8) Diagnose Examples

```bash
# Why was PR #N held?
.venv/bin/python3 runbooks/auto-update.py --json \
  | python3 -c "import sys,json;[print(c['gate'],c['reason']) for c in json.load(sys.stdin)['held'] if c['number']==N]"

# What did the last scheduled run do? (findings in the shared cycle)
curl -fsS $SWEEP_DASHBOARD_URL/api/findings?section=version | \
  jq '.[] | select(.title|test("Auto-update"))'
```

## 9) Health Check

```bash
# The engine imports cleanly + policy parses + fail-safe intact
.venv/bin/python3 runbooks/auto-update.py --json >/dev/null && echo "engine OK"
python3 -c "import yaml; yaml.safe_load(open('runbooks/auto-update-policy.yaml')); print('policy OK')"
```

Ongoing: a healthy scheduled run merges 0–N safe bumps and reports post-apply
health OK. A `reverted` count > 0 or a critical `auto-update` finding means a
merged bump regressed — investigate the named app before re-allowing it.

## 10) Security Check

- The engine only ever merges **Renovate-authored** PRs (`--author app/renovate`)
  that pass CI — it cannot introduce arbitrary code.
- It never touches `.sops.*` files (Renovate ignores them; nothing here decrypts
  secrets).
- Deny-list + release-notes scan + CI-green are compensating controls on top of
  the semver label; the apply guard (`--apply` AND cron trigger) prevents an
  operator's read-only sweep from mutating the cluster.
- The git identity used to merge/revert is the operator's local `gh`/`git`
  credentials on the Mac — same trust boundary as a manual merge.

## 11) Rollback Plan

```bash
# Immediate: stop auto-applying (dry-run still reports) —
# remove the `--apply` line from .claude/agents/daily-operation.md rule 4c,
# commit, push.

# Harder stop: delete/rename runbooks/auto-update-policy.yaml — the engine's
# fail-safe then denies EVERY PR (dry-run and apply both merge nothing).

# Undo a specific auto-merge that already landed:
git revert --no-edit <merge-sha> && git push origin main
# (Flux reconciles the revert; same as the engine's own auto-revert path.)
```

## 12) References

- Engine: `runbooks/auto-update.py`
- Policy (git-tracked deny-list): `runbooks/auto-update-policy.yaml`
- Orchestrator hook: `.claude/agents/daily-operation.md` rule 4c
- Version audit engine reused for G3: `runbooks/check-all-versions.py`
- CI gate: `.github/workflows/flux-local.yaml`
- Renovate config: `.github/renovate.json5`

## Version History

| Version | Date | Change |
|---|---|---|
| 2026.08.18 | 2026-08-18 | Documented the G0 parse gate; added Renovate's bare `update <dep> to <x.y.z>` shape (PR #205 held on `gate=parse` despite being a green version-only patch); corrected the window cadence to daily. |
| 2026.07.25 | 2026-07-25 | Initial SOP. Sweep-driven, health-gated auto-merge of patch+minor Renovate PRs; deny-by-default policy + release-notes breaking scan; cron-only apply guard; auto-revert on post-apply regression. |
