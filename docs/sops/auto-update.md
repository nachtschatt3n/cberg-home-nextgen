# SOP: auto-update — SAFE Renovate PRs auto-applied at Step 0 of each maintenance window (sweep is read-only)

> Version: `2026.09.08`
> Last Updated: `2026-09-08`

## 1) Description

Step 0 of EVERY maintenance window auto-applies the *safe* subset of open
Renovate PRs so the cluster stays current without the operator hand-merging
every patch/minor bump — while a mis-classified "safe" update (e.g. a patch tag
that is actually breaking) is still held for review.

**The sweep does NOT apply anything.** That changed on 2026-07-31 and the older
"sweep-applies" wording here outlived it. The `daily-operation` sweep is
READ-ONLY: it DRY-RUNS this script (rule 4c) purely to report what will land in
the next window. The `maintenance-window-agent` is what applies, at Step 0 of
every window including the unattended nightly one — so safe updates land DAILY,
not once per 48h sweep. A reader who trusts the old wording will scope a window
run to "just the assigned plans" and silently skip Step 0.

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
`docs/sops/monitoring.md` (alert authoring), `docs/sops/new-deployment-blueprint.md`,
`docs/sops/immutable-job-image-bumps.md` — an auto-applied image bump that
lands on a **Job** wedges the whole Flux Kustomization (`spec.template ...
field is immutable`) and every later change to it stops reconciling silently;
that SOP has the `vN`-rename fix and the detection command.

## 2) Overview

- **What runs:** `runbooks/auto-update.py` (+ `runbooks/auto-update-policy.yaml`).
- **Who APPLIES it:** the `maintenance-window-agent`, at Step 0 of every
  window (`AUTO_UPDATE_APPLY=1 auto-update.py --apply`), before any assigned
  plan runs. This is the only actor that merges.
- **Who DRY-RUNS it:** the `daily-operation` sweep orchestrator, rule 4c, after
  the version specialist finishes and the verdict is reconciled. Report only —
  the sweep never applies.
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
- **G5 age**: the PR's newest Renovate commit must be ≥ `minimum_release_age_hours` old (48h, policy-set 2026-08-26) — supply-chain cooldown for the nightly unattended lane. CVE/security bumps waive it (age 0); unknown age HOLDS; measured from the newest commit so a retargeted PR cannot inherit its old target's age.

  > **The security waiver cannot fire in the direct-bump lane.** It reads a
  > security marker out of the **Renovate PR title**, and the no-PR direct-bump
  > half (`coverage.py`) has no title to read — so a bump that *is* the
  > remediation for an open finding is held by G5 for the full 48h precisely
  > when speed matters. The only lever is `age_waive` in
  > `runbooks/auto-update-policy.yaml`: a **retroactive, permanent,
  > per-component** glob allowlist, so it never helps the first time a
  > component needs it. Hit three times in two days —
  > `3118a96f` (mealie, paperless-ngx) and `e813bba0` (music-assistant).
  >
  > Before waiving, confirm the held bump really is the fix (the flagged tag is
  > the *current* one and the held tag is the remediation), then add the glob
  > with a comment naming the finding ref. Note what you are buying: the waiver
  > is permanent and applies to **all** future bumps of that component, not just
  > security ones — revisit if the component starts shipping regressions.
  >
  > ```bash
  > .venv/bin/python3 runbooks/auto-update.py --json | python3 -c \
  >   "import sys,json; d=json.load(sys.stdin); print([(c['dep'],c['gate']) for c in d['held'] if c['gate']=='G5'])"
  > ```
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
green CI. Every component carrying a `deny` rule MUST appear in `held` — the
authoritative list is `runbooks/auto-update-policy.yaml`, not this paragraph.
Derive it rather than trusting a prose enumeration:

```bash
.venv/bin/python3 -c "
import yaml
p = yaml.safe_load(open('runbooks/auto-update-policy.yaml'))
for r in p['deny']:
    print(f\"{r['match']:<24} max={r.get('max','<none: blocked at every update_type>')}\")"
```

A `max:` value means the rule allows up to and including that update_type and
holds everything above it (`*mariadb*` is `max: patch`, i.e. patch may land
unattended, minor+ is held). Every other rule blocks the component outright.

Note there are now TWO safe definitions, deliberately: G1 above governs the
PR-MERGE half, while the no-PR **direct-bump** half reads `coverage.py`'s AUTO
lane, which is stricter — it also excludes pre-release channels, 0.x
release-line moves and lockstep-coupled items. See
`docs/sops/maintenance-windows.md` §Coverage guarantee → AUTO disqualifiers.

### Test 2: policy + parse gates (offline unit check)

Run the synthetic matrix. **It must assert every deny rule that exists, not a
memorable subset** — a rule absent from the matrix is a rule the test cannot
catch the removal of. As of `2026.09.08.1` that is all 21 globs:

| Deny glob | Assert |
|---|---|
| `*app-template*` | held at every update_type |
| `*affine*` | held at every update_type |
| `*cilium*` | held at every update_type |
| `*gateway-helm*` | held at every update_type |
| `*gateway-crds-helm*` | held at every update_type |
| `*envoy-gateway*` | held at every update_type |
| `*external-dns*` | held at every update_type — **including `minor`**, which is the case that matters: chart 1.22.x will ship appVersion 0.22.0 and would otherwise score a safe MINOR into the unattended nightly lane |
| `*mariadb*` | `max: patch` — patch ALLOWED, minor and major held |
| `*mcpo*` | held at every update_type |
| `*nocodb*` | held at every update_type (calver month hops parse as `minor`) |
| `*nextcloud-mcp*` | held **with its own reason**, matched BEFORE `*nextcloud*` |
| `*nextcloud-redis*` | held **with its own reason**, matched BEFORE `*nextcloud*` |
| `*nextcloud*` | held at every update_type |
| `*scrypted*` | held at every update_type |
| `*grafana*` | held at every update_type (chart minor can move appVersion) |
| `*unpoller*` | held at every update_type |
| `*openclaw*` | held at every update_type |
| `*@openclaw/*` | held at every update_type |
| `*coredns*` | held at every update_type |
| `siderolabs/*` | held at every update_type |
| `*talos*` | held at every update_type |

Rule ORDER is load-bearing for the three `nextcloud` globs: the first match
wins, so `*nextcloud-mcp*` and `*nextcloud-redis*` must precede `*nextcloud*`.
If they do not, both are held under the SERVER's chart-lockstep/occ reason,
which is false for them — and a false reason is what gets a real hold
overridden. Assert the reason string, not just the held verdict.

Then the non-deny half: cloudflared/redis → allowed; grouped/unparseable PR →
held; bare `update busybox to v1.38.0` → parses; `update Flux Operator group to
v1.2.3` and `update foo to v2` → still refused. Any mismatch means a deny glob
or the title parser is wrong — fix before the next scheduled run.

### Test 2b: the matrix is COMPLETE (guards this section against drift)

Test 2 is a hand-written enumeration, so it decays silently every time a deny
rule is added: the SOP keeps passing while asserting a policy that no longer
exists. It did — `*external-dns*` was added in `e97476d3` and eleven other
globs (`cilium`, the four gateway/envoy globs, `mcpo`, `nocodb`, the two
`nextcloud-*` variants, `grafana`, `coredns`, `@openclaw/`) had never been
listed at all. Check completeness mechanically, in BOTH directions:

```bash
.venv/bin/python3 - <<'EOF'
import re, yaml
policy = {r['match'] for r in yaml.safe_load(open('runbooks/auto-update-policy.yaml'))['deny']}
bt = chr(96)                                   # backtick, kept out of the shell
sop = set(re.findall(r'^\| ' + bt + r'([^' + bt + r']+)' + bt + r' \|',
                     open('docs/sops/auto-update.md').read(), re.M))
missing = policy - sop
stale   = {g for g in sop - policy if '*' in g or '/' in g}
print('MISSING from the SOP matrix:', sorted(missing) or 'none')
print('STALE in the SOP matrix   :', sorted(stale) or 'none')
raise SystemExit(1 if (missing or stale) else 0)
EOF
```

Expected:
- both lines print `none`, exit 0.

If failed:
- `MISSING` — a deny rule exists that Test 2 does not assert. Add the row.
- `STALE` — Test 2 asserts a rule that was deleted from the policy. Either the
  removal was intentional (drop the row, and say why in the Version History) or
  a hold was lost.

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
| 2026.09.08 | 2026-09-08 | **Completed the Test 2 synthetic matrix and added Test 2b to keep it complete.** The matrix enumerated 8 of the then-20 deny globs; `*external-dns*` was added the same day (`e97476d3`, policy `2026.09.08.1`) and 11 others (`cilium`, `gateway-helm`, `gateway-crds-helm`, `envoy-gateway`, `mcpo`, `nocodb`, `nextcloud-mcp`, `nextcloud-redis`, `grafana`, `coredns`, `@openclaw/`) had never been listed — so the SOP's own test asserted a policy the repo no longer had. Test 1 now derives the list from the policy YAML instead of restating it, and Test 2b fails on any missing-or-stale glob in both directions. |
| 2026.09.05 | 2026-09-05 | Documented the G5 **direct-bump blind spot**: the security waiver reads a marker from the Renovate PR title, so the no-PR direct-bump lane can never trigger it and `age_waive` (retroactive, permanent, per-component) is the only lever. Three occurrences in two days — `3118a96f`, `e813bba0`. |
| 2026.08.18 | 2026-08-18 | Cross-referenced `docs/sops/immutable-job-image-bumps.md` — an auto-applied image bump landing on a Job wedges the whole Kustomization. |
| 2026.08.18 | 2026-08-18 | Documented the G0 parse gate; added Renovate's bare `update <dep> to <x.y.z>` shape (PR #205 held on `gate=parse` despite being a green version-only patch); corrected the window cadence to daily. |
| 2026.07.25 | 2026-07-25 | Initial SOP. Sweep-driven, health-gated auto-merge of patch+minor Renovate PRs; deny-by-default policy + release-notes breaking scan; cron-only apply guard; auto-revert on post-apply regression. |
