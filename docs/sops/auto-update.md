# SOP: auto-update — SAFE Renovate PRs auto-applied at Step 0 of each maintenance window (sweep is read-only)

> Version: `2026.09.26`
> Last Updated: `2026-09-26`

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
     render check is the **`Flate Render Gate`** job of
     `.github/workflows/flux-local.yaml` (flate renders every HelmRelease and
     Kustomization on each PR), so green = the manifest actually renders. The
     EOL `flux-local test` job was retired 2026-09-23 (F-6b1dd22b); the file
     keeps its name because the flux-local *diff* jobs still live there, and
     they are not a gate. Pending checks → hold this cycle (passes next
     cycle); failing checks → hold. The gate is **all-or-nothing across the
     whole rollup** and **names no check** — nothing is required by name and
     nothing is ignored by name — so a red workflow that has nothing to do
     with the bump still holds the PR (see §7 for the lane-wide failure that
     hides behind a legitimate-looking per-PR hold), and a check run that a
     since-removed job left on the PR's head SHA still holds it until a fresh
     run (reopen or rebase); the hold reason names that case explicitly.
- **G5 age**: a supply-chain cooldown — nothing may land in the unattended
  nightly lane until it has been public for `minimum_release_age_hours` (48h,
  policy-set 2026-08-26). **Unknown age HOLDS, in both lanes.**

  G5 has TWO implementations, because there are two lanes and they measure
  different objects:

  - **PR lane** (`auto-update.py`): the PR's newest Renovate commit must be ≥
    the cooldown. Measured from the NEWEST commit, so a retargeted PR cannot
    inherit its old target's age. CVE/security bumps waive it (age 0).
  - **Direct-bump lane** (`coverage.py::direct_bump_age_gate`): a direct bump
    has no PR and therefore no commit to measure, so it ages the **artifact's
    publish date** instead:
    - **images** — `image_publish_age_hours()`. `docker.io` reads the Hub tag's
      `last_updated`; every other registry reads the image config blob's
      `created` via `_oci_created()`, which walks a multi-arch index and skips
      the attestation/SBOM children (their platform is `unknown` and they carry
      no config blob, so picking `manifests[0]` blindly 404s). An app can index
      several repos, so the gate takes the **youngest** age across every repo
      that actually carries the target tag, and names that repo in the hold
      reason.
    - **charts** — `chart_publish_age_hours()`. An HTTP chart repo publishes a
      per-version `created` in `index.yaml`. An `oci://` chart has no
      `index.yaml`, but `helm push` stamps the standard OCI annotation
      `org.opencontainers.image.created` on the chart manifest, and
      `_oci_chart_created()` reads it (`5c53e313`, F-88bf8743). `docker.io`'s
      split registry/token hosts are handled; everything else is same-host.

  **Why the chart half is worth knowing:** before `5c53e313` every `oci://`
  source short-circuited to `None`, and since unknown age is hold-fail-safe
  that made the hold **permanent rather than timed** — the component could never
  elapse the cooldown however old the release got, while the hold reason read
  like a countdown that was never counting. Resolving the date turns it back
  into a bounded wait. Verified live 2026-09-22 against
  `oci://ghcr.io/prometheus-community/charts` / `kube-prometheus-stack`:
  `90.0.0 → 367.2h`, `90.2.0 → 222.0h`, and a non-existent version → `None`.

  Fail-safe runs one way only: `_oci_chart_created()` returns `None` on ANY
  failure (unsupported registry, auth, missing annotation), so anything
  unverifiable still holds. This widens what can be VERIFIED, never what is let
  through — a future refactor returning `0.0` or `now()` on failure would invert
  every unreachable registry into an instant cooldown PASS, which is exactly
  what `runbooks/tests/test-oci-chart-age.py` asserts against in both
  directions.

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

#### A `max:` rule's ALLOWED half needs its own candidate source

A `max:` rule permits the lower update_type, but until 2026-09-12 nothing could
ever act on that permission. Renovate proposes only the NEWEST version, which
for a `max:`-held component is by definition the blocked one — so G2 held the
PR (correctly, and that is the end of that road), while the direct-bump half
skipped the component because the Renovate-PR shortcut in `assign_lane()`
counted a PR's mere existence as coverage. Measured: n8n's PR #213 proposed
`2.38.4 → 2.39.4` (the beta line, held by `max: patch`) while `2.38.4 → 2.38.7`
— a plain patch on the stable line that the same rule explicitly permits — was
invisible to both halves.

`coverage.py::max_rule_fallbacks()` closes that. For every item a `max:` rule
blocks it asks upstream's own **stable channel pointer** what the stable head
is, and emits it as an ordinary direct-bump candidate. Reported under
`max_rule_fallback` in `--json` with one of four statuses (`candidate`, `hold`,
`up-to-date`, `already-enumerated`) and, for a candidate, the lane it actually
landed in.

Two properties to hold on to:

- **It is a candidate SOURCE, not a bypass.** Every emitted candidate is
  re-run through `assign_lane()` and must clear G1, G2 (the rule's own `max:`,
  re-evaluated for the lower type), G3 and G5 like any other direct bump. G4 is
  not applicable — a direct bump has no PR.
- **An unconfirmable channel HOLDS.** "Newest semver the rule allows" is exactly
  the inference these rules exist to prevent, so the candidate must be
  positively confirmed by an `org.opencontainers.image.version` label on the
  `stable`/`latest` tag (digest-cross-checked), or by a Docker Hub digest match.
  Charts have no such pointer and always hold. The blocked PR is left strictly
  alone — never closed, retargeted or commented on from code.

**The durable fix for a channel problem is Renovate-side, not policy-side.**
Where upstream publishes a real dist-tag, pin Renovate to the channel pointer
instead of the highest semver — `followTag: "stable"` in `.github/renovate.json5`
(added for `n8nio/n8n` 2026-09-12, `12de99ef`). Renovate then proposes only what
upstream has actually promoted, so the beta stops being re-proposed every time
the pre-release line advances. It does NOT replace the `max:` deny rule:
`followTag` trusts upstream to keep the pointer honest, the policy rule does not,
so the two stay layered as defence in depth. Components without a usable
dist-tag stay on `CHANNEL_RULES` membership (see
`docs/sops/maintenance-windows.md` §Coverage guarantee).

### Test 2: policy + parse gates (offline unit check)

Run the synthetic matrix. **It must assert every deny rule that exists, not a
memorable subset** — a rule absent from the matrix is a rule the test cannot
catch the removal of — and a rule whose `max:` is mis-stated is a hold the test
cannot catch the WIDENING of. As of `2026.09.22` that is all 27 globs:

| Deny glob | Assert |
|---|---|
| `*authentik*` | held at every update_type (added 2026-09-22, `0193f2e4`, operator call) — the chart version and the two `patch-session-settings` initContainers are pinned SEPARATELY: the main server image is NOT pinned in values, so a chart-only bump DOES move the running image, while the initContainers (which pin `ghcr.io/goauthentik/server` inline at two sites) stay put and overlay an old `settings.py` onto new code, with nothing asserting the two agree (mechanism corrected 2026-09-26 — the earlier text had it backwards); and G3 reported its breaking-change signal "unverified (release notes unavailable)" while the item routed to AUTO anyway — a fail-open on the household SSO front door, which every forward-auth service and the Flux controllers that would revert a bad roll sit behind |
| `*app-template*` | `max: patch` (narrowed 2026-09-12) — patch ALLOWED, minor held; major never reaches the rule (G1) |
| `*toeverything/affine*` | held at every update_type (narrowed 2026-09-26 from `*affine*`, which also held sibling components such as `affine-redis` under the AFFiNE app's reason; matched by image repo in the direct-bump lane) |
| `*cilium*` | held at every update_type |
| `*gateway-helm*` | held at every update_type |
| `*gateway-crds-helm*` | held at every update_type |
| `*k8s-gateway*` | held at every update_type |
| `*envoy-gateway*` | held at every update_type |
| `*external-dns*` | held at every update_type — **including `minor`**, which is the case that matters: chart 1.22.x will ship appVersion 0.22.0 and would otherwise score a safe MINOR into the unattended nightly lane |
| `*frigate*` | `max: patch` (added 2026-09-15, F-71dc3610) — patch ALLOWED, minor held: a 0.x MINOR is a release-line move with config + sqlite migrations, and the read-only ConfigMap config cannot be auto-migrated (safe-mode-with-zero-cameras failure is invisible to probes) |
| `*mariadb*` | `max: patch` — patch ALLOWED, minor and major held |
| `*mcpo*` | held at every update_type |
| `*n8nio/n8n*` | `max: patch` (added 2026-09-10 as `*n8n*`; narrowed 2026-09-26 to the image, because the 8gears n8n CHART has no beta channel and was being held under the image's reason) — patch ALLOWED (stable line), minor held: n8n ships its beta/next channel on the next MINOR line with no prerelease marker in the tag |
| `*nocodb*` | `max: patch` — patch ALLOWED, minor held, which is the case that matters: a calver month hop parses as `minor` and runs one-way knex migrations |
| `*nextcloud-mcp*` | `max: patch` (narrowed 2026-09-12) — patch ALLOWED, minor held **with its own reason**, matched BEFORE `*nextcloud*` |
| `*nextcloud-redis*` | held **with its own reason**, matched BEFORE `*nextcloud*` |
| `*nextcloud*` | held at every update_type |
| `*scrypted*` | held at every update_type |
| `*grafana*` | `max: patch` (narrowed 2026-09-12) — patch ALLOWED, minor held (a chart MINOR can move appVersion across forward-only sqlite migrations; a chart PATCH does not) |
| `*unpoller*` | held at every update_type |
| `*openclaw*` | held at every update_type |
| `*@openclaw/*` | held at every update_type |
| `*coredns*` | held at every update_type |
| `aqua:siderolabs/talos` | held at every update_type — the talosctl CLI pin in `.mise.toml` FOLLOWS a node upgrade and must never move ahead of the cluster; listed ABOVE `siderolabs/*` because first match wins and `_match_anywhere` would otherwise attach the node-image reason to a local binary (split 2026-09-13, F-1128fcdf; matrix row added 2026-09-15 — Test 2b had been failing on it) |
| `siderolabs/*` | held at every update_type |
| `*talos*` | held at every update_type |
| `*valkey*` | held at every update_type (INTERIM, added 2026-09-21) — the only upstream tag above the pin is a PRE-RELEASE: a floating 2-component tag digest-identical to an `-rc1`, with no GA above the pin. Withdraw the rule when a real GA publishes, or it freezes valkey on a genuine future release. It also has to reach the DIRECT-BUMP lane, which resolves a deny rule by the component key first and then by each image repository the item names (`denied_for_item`) — the component key alone did not match this glob |

Rule ORDER is load-bearing for the three `nextcloud` globs: the first match
wins, so `*nextcloud-mcp*` and `*nextcloud-redis*` must precede `*nextcloud*`.
If they do not, both are held under the SERVER's chart-lockstep/occ reason,
which is false for them — and a false reason is what gets a real hold
overridden. Assert the reason string, not just the held verdict.

Then the non-deny half: cloudflared/redis → allowed; grouped/unparseable PR →
held; bare `update busybox to v1.38.0` → parses; `update Flux Operator group to
v1.2.3` and `update foo to v2` → still refused. Any mismatch means a deny glob
or the title parser is wrong — fix before the next scheduled run.

### Test 2b: the matrix is COMPLETE *and* CORRECT (guards this section against drift)

Test 2 is a hand-written enumeration, so it decays silently every time a deny
rule is added or narrowed: the SOP keeps passing while asserting a policy that
no longer exists. Both halves have failed in the field.

**Membership** drifted when `*external-dns*` was added in `e97476d3` and eleven
other globs (`cilium`, the four gateway/envoy globs, `mcpo`, `nocodb`, the two
`nextcloud-*` variants, `grafana`, `coredns`, `@openclaw/`) had never been
listed at all.

**The `max:` half is the worse one, because it decays without changing the
verdict.** Until 2026-09-22 this check compared glob MEMBERSHIP only and never
read the `max:` key, so a row asserting "held at every update_type" for a rule
that actually carries `max: patch` passed cleanly — the SOP claimed a component
was fully blocked while the policy was letting its patches through unattended
(F-28c62378). Check all three properties mechanically:

```bash
.venv/bin/python3 - <<'EOF'
import re, yaml
policy = {r['match']: r.get('max')
          for r in yaml.safe_load(open('runbooks/auto-update-policy.yaml'))['deny']}
bt = chr(96)                                   # backtick, kept out of the shell
rows = dict(re.findall(r'^\| ' + bt + r'([^' + bt + r']+)' + bt + r' \| (.*?) \|\s*$',
                       open('docs/sops/auto-update.md').read(), re.M))
missing = set(policy) - set(rows)
stale   = {g for g in set(rows) - set(policy) if '*' in g or '/' in g}
# The Assert cell must SPELL OUT the rule's own `max:`, not merely exist.
wrong = []
for g, cell in rows.items():
    if g not in policy:
        continue                               # a non-policy backticked row
    m = re.search(bt + r'max: (\w+)' + bt, cell)
    claimed = m.group(1) if m else None
    if claimed != policy[g]:
        wrong.append((g, claimed or 'blanket hold', policy[g] or 'blanket hold'))
print('MISSING from the SOP matrix:', sorted(missing) or 'none')
print('STALE in the SOP matrix   :', sorted(stale) or 'none')
print('WRONG max: assertion      :', sorted(wrong) or 'none')
raise SystemExit(1 if (missing or stale or wrong) else 0)
EOF
```

Expected:
- all three lines print `none`, exit 0.

If failed:
- `MISSING` — a deny rule exists that Test 2 does not assert. Add the row.
- `STALE` — Test 2 asserts a rule that was deleted from the policy. Either the
  removal was intentional (drop the row, and say why in the Version History) or
  a hold was lost.
- `WRONG max:` — the row's Assert cell disagrees with the rule's own `max:` key.
  Each triple is `(glob, what the SOP claims, what the policy says)`. Resync the
  row, then ask which side was wrong: a row claiming a blanket hold over a
  `max: patch` rule **over-claims** (that component's patches ARE landing
  unattended tonight), while a row claiming `max: patch` over a blanket rule
  under-claims a hold that really exists. The cell must spell the value in
  backticks exactly as the YAML does — a prose "patches allowed" does not parse
  and is read as a blanket-hold claim.

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
| `--apply` merges nothing for DAYS and EVERY PR is held `gate=ci` | Not the PRs — a **workflow-wide** render-gate failure (`Flate Render Gate`; historically `flux-local`). G4 needs the entire check rollup green, so one red workflow holds every Renovate PR at once and the whole PR lane is frozen; the direct-bump half (`coverage.py`) keeps shipping, so safe updates still appear to flow. Each individual hold reads as a legitimate "CI failing", which is why it ran 8 days unnoticed (F-00235e5c). | Diagnose the WORKFLOW, not the PR: `gh run list --workflow flux-local.yaml -L 10`. If the newest green run predates the holds, the fault is in `.github/workflows/flux-local.yaml` (or its pinned image) — rebasing, reopening or re-running the PRs changes nothing. |
| A PR is held `gate=ci` on a check that is not a job in its workflow any more (the reason ends "stale check run on this head SHA") | The job was removed from `.github/workflows/*.yaml` (e.g. `Flux Local Test`, retired 2026-09-23) but GitHub keeps the check run it had already attached to the PR's head SHA, and nothing re-runs PR workflows when `main` changes. PR #219 carried `Flux Local Test=FAILURE` beside a green `Flate Render Gate` on the same SHA. | `gh pr close <n> && gh pr reopen <n>` (or tick Renovate's rebase box): the fresh `pull_request` run uses the current workflow and the stale check leaves the rollup; G4 clears next cycle. Do NOT teach G4 to ignore the name — that is a silent-green. |
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
- CI render gate: `.github/workflows/flux-local.yaml` — job `flate`, check name `Flate Render Gate` (flux-local test retired 2026-09-23, F-6b1dd22b); shape pinned by `runbooks/tests/test-flate-gate-mitigations.py`, G4's stale-check diagnosis by `runbooks/tests/test-g4-stale-check-diagnosis.py`
- Renovate config: `.github/renovate.json5`

## Version History

| Version | Date | Change |
|---|---|---|
| 2026.09.26 | 2026-09-26 | **Four false holds removed (planner findings, operator-approved).** (a) **G3 reads non-GitHub notes**: `library/alpine` (news posts, parsed from the multi-version slug `Alpine-3.21.8-…-3.24.2-released.html`) and `library/python` (the "What's New In Python X.Y" page of every minor a hop enters; for a patch hop the target minor's "Notable changes in X.Y.N" sections) — `check-all-versions.py` `DISTRO_RELEASE_NOTES` / `fetch_distro_release_notes()`. Both were "release notes unavailable" by construction and routed to a window as unverified. An unreadable source is still unresolved, never clean. (b) **G3s is scoped to the image's build context** (`IMAGE_BUILD_CONTEXTS`, seeded only from the upstream build workflow): `emqx/mqttx-web` → `web/`, so a migration in the Electron desktop tree no longer holds the web image; unlisted images keep the whole-repo scan. (c) **Policy `2026.09.26.1`**: `*affine*` → `*toeverything/affine*`, `*n8n*` → `*n8nio/n8n*`, and the `*authentik*` reason's mechanism corrected. (d) **app-template source link** points at `bjw-s-labs/helm-charts` `app-template-X.Y.Z` (`CHART_RELEASE_SOURCES`). Tests: `test-g3-distro-release-notes.py`, `test-g3s-build-context.py`, `test-auto-update-policy-narrowed-globs.py`, `test-chart-release-source-link.py`. |
| 2026.09.23 | 2026-09-23 | **flux-local test retired; the Flate Render Gate is the single render gate (F-6b1dd22b, operator decision).** The `Flux Local Test` and `Flux Local successful` jobs are gone from `.github/workflows/flux-local.yaml`; the flux-local *diff* jobs stay (they post PR diffs flate does not replace), so the file keeps its name. G4 needed no re-pointing — it never named a check; it holds on any non-green rollup entry — but a check run left on a PR's head SHA by a removed job outlives the job (PR #219: `Flux Local Test=FAILURE` beside a green `Flate Render Gate` on the same SHA), so `ci_state()` now appends "stale check run on this head SHA; reopen or rebase" to that hold reason. Verdict unchanged (hold). New Troubleshooting row. |
| 2026.09.22 | 2026-09-22 | **Two gaps, both found by the SOP asserting something the code stopped doing.** (a) **G5 was documented as a commit-age rule only (F-b5445561)** — the SOP had zero mentions of `oci://` or artifact publish dates, although the engine has had a SECOND G5 implementation since 2026-09-07 and `_oci_chart_created()` since `5c53e313`. The no-PR direct-bump lane has no Renovate commit to measure, so it ages the ARTIFACT: Docker Hub `last_updated`, the OCI image config blob's `created` (youngest across every repo carrying the tag), chart `index.yaml` `created`, and for `oci://` charts the `org.opencontainers.image.created` annotation on the chart manifest. Documented under G5 with the fail-safe direction and why an unresolvable `oci://` age used to make the hold *permanent* rather than timed. Live-verified against `kube-prometheus-stack` 90.0.0 / 90.2.0 / a bogus version. (b) **Test 2b compared glob MEMBERSHIP only, so a wrong `max:` assertion passed (F-28c62378)** — the exact decay the 2026.09.13 entry below flagged as "Test 2b only checks glob MEMBERSHIP, so it cannot see a wrong Assert". It now parses each row's Assert cell and diffs the backticked `max:` against the rule's own key in both directions. Matrix resynced to policy `2026.09.22.1` — 27 globs, with `*authentik*` (`0193f2e4`) and `*valkey*` added. |
| 2026.09.20 | 2026-09-20 | **The G4 item was split across the G5 bullet, so both gates read wrong (F-1025b8c2).** G4 ended mid-sentence on the word "The", and its continuation — the `flux-local` dependency and the pending-vs-failing outcomes — sat orphaned *after* G5's entire 20-line blockquote, where it read as a paragraph about the age cooldown. Re-split so each gate describes itself. Added the Troubleshooting row for the failure that mis-split helped hide: G4 is all-or-nothing across the check rollup, so a **workflow-wide** `flux-local` failure holds EVERY Renovate PR on `gate=ci` and freezes the whole PR lane while the direct-bump half keeps shipping. The SOP documented "failing checks → hold" only as a per-PR outcome and never as a lane-wide outage, so 8 days of legitimate-looking holds went unread (operational cause: F-00235e5c). |
| 2026.09.13 | 2026-09-13 | **Test 2's matrix had drifted again — the failure mode the 2026.09.08 entry below claims to have closed.** Its own Test 2b check reported `MISSING: *k8s-gateway*, *n8n*`, and four Assert cells were stale: `*app-template*`, `*grafana*`, `*nextcloud-mcp*` were narrowed to `max: patch` on 2026-09-12 (`d147b1ce`) and `*nocodb*` earlier, yet all four still read "held at every update_type". Test 2b only checks glob MEMBERSHIP, so it cannot see a wrong Assert — the `max:` semantics still decay silently. Matrix resynced to policy `2026.09.12.1` (23 globs). Also documented the Renovate-side `followTag` channel lever. |
| 2026.09.15 | 2026-09-15 | **`*frigate*` deny rule added (`max: patch`, policy `2026.09.15`, F-71dc3610, operator call).** Frigate is 0.x, so a "minor" is a release-line move with a config migrator and sqlite migrations; the read-only ConfigMap config cannot be auto-migrated, so an unattended bump starts the NVR in safe mode with zero cameras while every probe stays green. coverage.py's 0.x rule already held the direct-bump half; this closes the Renovate-PR half. Test 2 matrix row added. |
| 2026.09.15 | 2026-09-15 | **Two gate bypasses in the direct-bump lane, found in the nightly window by ground-truthing AUTO items.** (1) G3 was NOT applied on the regular patch/minor path: `breaking_change_signal()` had one call site, inside `max_rule_fallbacks()`, so the sentence in §4 ("must clear G1, G2, G3 and G5 like any other direct bump") described the fallback path only — mealie `v3.25.1 → v3.26.0`, `age_waive`d so G5 did not hold it either, was rated AUTO with a BREAKING CHANGE in its release notes (F-ec4c1644). `assign_lane()` now runs `_direct_bump_breaking_gate()` before its AUTO exit: a positive signal routes to PLAN; unfetchable notes still do not hold (the documented asymmetry) but the AUTO reason now says `G3 unverified`. (2) G5 measured the wrong image for a multi-image component: `direct_bump_age_gate()` stopped at the first repo that resolved the target tag, alphabetically `memgraph/lab` (3.5 d old), and rated `memgraph-mage 3.13.1` (13 h old) AUTO inside the cooldown (F-9b77a91a). It now takes the YOUNGEST age across every repo carrying the tag and names that repo in the hold reason. Regression suites: `test-coverage-lane-safety.py` (DirectBumpBreakingGateTest), `test-direct-bump-age-gate.py` (multi-repo youngest carrier). |
| 2026.09.12 | 2026-09-12 | **A `max:` rule's ALLOWED half had no candidate source.** Renovate only ever proposes the newest version — the blocked one — so G2 held the PR while the direct-bump lane skipped the component for *having* a PR. n8n `2.38.4 → 2.38.7` (a patch on the stable line, explicitly permitted by its own `max: patch`) was invisible to both halves. Added `coverage.py::max_rule_fallbacks()`: reads upstream's stable-channel pointer, emits the allowed head as an ordinary direct-bump candidate, holds fail-safe when the channel cannot be confirmed. Regression suite: `runbooks/tests/test-max-rule-fallback.py`. |
| 2026.09.08 | 2026-09-08 | **Completed the Test 2 synthetic matrix and added Test 2b to keep it complete.** The matrix enumerated 8 of the then-20 deny globs; `*external-dns*` was added the same day (`e97476d3`, policy `2026.09.08.1`) and 11 others (`cilium`, `gateway-helm`, `gateway-crds-helm`, `envoy-gateway`, `mcpo`, `nocodb`, `nextcloud-mcp`, `nextcloud-redis`, `grafana`, `coredns`, `@openclaw/`) had never been listed — so the SOP's own test asserted a policy the repo no longer had. Test 1 now derives the list from the policy YAML instead of restating it, and Test 2b fails on any missing-or-stale glob in both directions. |
| 2026.09.05 | 2026-09-05 | Documented the G5 **direct-bump blind spot**: the security waiver reads a marker from the Renovate PR title, so the no-PR direct-bump lane can never trigger it and `age_waive` (retroactive, permanent, per-component) is the only lever. Three occurrences in two days — `3118a96f`, `e813bba0`. |
| 2026.08.18 | 2026-08-18 | Cross-referenced `docs/sops/immutable-job-image-bumps.md` — an auto-applied image bump landing on a Job wedges the whole Kustomization. |
| 2026.08.18 | 2026-08-18 | Documented the G0 parse gate; added Renovate's bare `update <dep> to <x.y.z>` shape (PR #205 held on `gate=parse` despite being a green version-only patch); corrected the window cadence to daily. |
| 2026.07.25 | 2026-07-25 | Initial SOP. Sweep-driven, health-gated auto-merge of patch+minor Renovate PRs; deny-by-default policy + release-notes breaking scan; cron-only apply guard; auto-revert on post-apply regression. |
