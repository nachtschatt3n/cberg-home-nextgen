---
plan_id: absenty-drop-npm-runtime
component: absenty
pr: null                              # self-owned image; no upstream PR
kind: image
current: "node + npm installed in the Dockerfile `base` stage, inherited by `production`"
target: "node + npm confined to the build stages (`assets`, `dev`); `production` runtime is node-free"
update_type: refactor                 # Dockerfile stage restructure, no dependency version moves
risk: low
est_duration_min: 90   # RAISED from 60 on 2026-09-20: the old figure costed a
                       # local `docker build` that cannot happen on the executor
                       # host (no container runtime) and omitted the freeze and
                       # suspend sequencing of §9.1 / §11.1 entirely. See §10.
needs_reboot: false
touches:
  namespaces: [my-software-development, my-software-production]
  resources:
    - helmrelease/absenty                       # both namespaces
    - "ghcr.io/nachtschatt3n/absenty"
  shared: []
depends_on: []
conflicts_with: []
capability_change: false
rollback_class: git-revert    # DECLARED 2026-09-06. The production runtime is
                          # Rails + puma and never invokes npm — npm is present
                          # only as an accident of Dockerfile stage inheritance.
                          # Removing it changes the image's SHAPE, not what the
                          # software can do, so capability_change is false.
                          # Undo is: revert the Dockerfile commit and rebuild.
status: blocked   # BLOCKED 2026-09-20 BY DESIGN, not by a defect. The operator chose to drain the dependabot queue (section 12 Q3) rather than freeze it, so six dependency PRs were merged into `production` and CI published production-20260920181830. The premise no-newer-production-tag-has-been-published now FAILS (got production-20260920181830, want production-20260818185444) and plan-premises.py correctly refuses execution. That is the premise doing its job: section 7.5's before/after asset comparison is only meaningful when the ONLY source delta is the Dockerfile stage split, and it no longer is. UNBLOCK = re-baseline (see 11.1), NOT relaxing the premise.
                 # window fired from the per-window cron with no operator
                 # present, so the run was UNATTENDED. Class is AUTO-NIGHT and
                 # the premise PASSED (plan-premises.py exit 0, deployed image
                 # still production-20260818185444), but the category
                 # `image/AUTO-NIGHT` has 1 of the 2 clean supervised runs
                 # `first_runs_supervised` requires (autonomy-record.py
                 # eligible --plan-id absenty-drop-npm-runtime, verified:true).
                 # `supervised` is RECORDED, never inferred from a slot named
                 # "attended", so this run could not have counted as #2.
                 # The ask is a human present for its second supervised run —
                 # not a re-assessment of the plan, which is unchanged.
                 # VETTED 2026-09-06. Premise checked against the LIVE
                 # cluster, not against the plan's own prose:
                 # npm 12.0.2 and node confirmed present at /usr/local/bin in
                 # the RUNNING my-software-production container, not merely
                 # in the Dockerfile. Dockerfile line 39 installs npm in
                 # `base` and line 84 is `FROM base AS production`, so the
                 # inheritance the plan describes is real.
window: null   # UNSCHEDULED 2026-09-20 by the sun-attended window agent. It held sun-attended:2026-09-20 and that window RAN, but the plan was NOT executed: no container runtime exists on the executor host (kills section 4 and the headline section 7d bit-identical assertion) and the only runnable check cannot fail (svc/absenty has no port 80 - only 3000 - and / returns a zero-byte 302, so the asset greps and their loop pass on an empty body). Section 9's claim that the ImageUpdateAutomation is Ready=False is stale and INVERTED: both are Ready=True and unsuspended, so production auto-rolls in ~30 min. Engineering and autonomy gate are fine (eligible, 2/2 clean supervised). Deliberately NOT re-slotted into sun-attended:2026-09-27, which talos-1.14.0 owns exclusively. Prior rationale below is HISTORICAL.
                 # 2026-09-06 by window-scheduler). NOT sat-attended:2026-09-19: that slot is
                 # duration_min 90 and already holds media-audit-durable-output (45 min), so
                 # adding this plan's 60 min would be 105/90 — an OVER-TIME window, and a
                 # reconciler check that fires on a window we intend to run is a check people
                 # learn to ignore. sun-attended:2026-09-20 is attended, 200 min and empty
                 # (talos-1.14.0 sits in sun-attended:2026-09-27, not 09-20), so the supervised
                 # run this plan needs actually has room for its dev-lane soak.
premises:
  - id: artifact-under-test-is-unchanged
    why: >-
      npm 12.0.2 and node were confirmed present in the RUNNING production
      container on 2026-09-06. `kubectl exec` is not permitted in a premise
      (it can run anything), so what is asserted here is that the deployed
      artifact is still the one that was inspected. A rebuild may already have
      removed npm, which would make this plan a no-op rather than a refactor.
    run: kubectl get deploy -n my-software-production absenty -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/nachtschatt3n/absenty:production-20260818185444
  - id: no-newer-production-tag-has-been-published
    why: >-
      ADDED 2026-09-20. §7's headline check is a BEFORE/AFTER comparison of the
      served asset bundle within the production lane, and it is only meaningful
      if the ONLY source delta between the two images is the Dockerfile stage
      split. 18 open dependabot PRs all target the `production` branch (§11.1);
      merging any one of them publishes a new `production-<ts>` tag, which this
      policy immediately selects, which both (a) rolls production on its own and
      (b) destroys the comparison. This premise is that machine check: it FAILS
      the moment anything else has been promoted, and the plan must then be
      re-baselined rather than executed.
    run: kubectl get imagepolicy -n my-software-production absenty -o jsonpath='{.status.latestRef.tag}'
    expect_exact: production-20260818185444
  - id: production-image-automation-is-live-not-broken
    why: >-
      ADDED 2026-09-20, replacing a STALE AND INVERTED prose claim. §9 used to
      assert this automation was `Ready=False / GitOperationFailed` and that the
      HelmRelease tag therefore had to be bumped by hand. Measured 2026-09-20:
      Ready=True, "repository up-to-date", pushing to `main`. That inversion is
      load-bearing twice — it sets the blast radius (a merged promotion rolls
      PRODUCTION unattended) and it breaks the rollback lever (a hand-pin of the
      tag is rewritten back by the Setters strategy). If this ever regresses to
      not-Ready, §9's whole sequencing changes again and must be re-derived.
      `suspend` is deliberately allowed to be ANY of unset, `true` or `false`:
      §9.1 may set it true IN GIT as the manual gate, and this premise must not
      fail when that gate is correctly in place. `false` is accepted too
      (widened 2026-09-20) because lifting the gate by writing `suspend: false`
      is as valid as deleting the line, and the earlier `(true)?` form failed
      CLOSED on a correctly-ungated automation. What this premise actually
      asserts is `ready=True`; the suspend value is informational.
    run: kubectl get imageupdateautomation -n my-software-production absenty-image-updates -o jsonpath='ready={.status.conditions[?(@.type=="Ready")].status} suspend=[{.spec.suspend}]'
    expect_matches: '^ready=True suspend=\[(true|false)?\]$'
# auto_execute RETIRED 2026-08-26 (P2.1b) — execution class is now DERIVED
# from capability_change/rollback_class per runbooks/autonomy-policy.yaml.
# (original rationale: changes the shape of the production runtime image)
security_ref: F-fec7ea4b              # security driver; detail is DB-only.
                                      # STALE as of 2026-09-20: this record is
                                      # status=resolved (resolved_at 2026-08-19)
                                      # and names a SUPERSEDED tag. Kept as the
                                      # historical driver; see §1a. Re-filing a
                                      # live driver is an operator decision, not
                                      # this plan's to make.
sops_refs:
  - docs/sops/vulnerability-disclosure.md
  - docs/sops/self-built-image-rebuild.md
generated: "2026-08-18"
---

# absenty: take npm out of the production runtime layer

## 1) Summary & why held

The 2026-08-18 promotion to `production-20260818155406` cleared the
lockfile-pinned gem items. npm-attributed items survived it (F-fec7ea4b), and
the premise recorded in the Dockerfile for why they would clear was wrong.

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-fec7ea4b**. Advisory IDs, affected package paths, counts and
> the exploitability assessment live on the finding record, not here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-fec7ea4b`
> - CLI: `runbooks/policy-cli.py finding show F-fec7ea4b`
>
> Convention: `docs/sops/vulnerability-disclosure.md`.

### 1a) The stated driver is stale — read this before quoting it

Measured 2026-09-20: **F-fec7ea4b is `status=resolved`** (`resolved_at`
2026-08-19, `resolved_commit` addfd9aa) and its title names
`production-20260817185546`, two tags behind the deployed
`production-20260818185444`. No OPEN finding names absenty or npm. So:

- **Do not cite F-fec7ea4b as a live driver in a report.** It is the historical
  record of why this plan exists, not evidence of a current gap.
- **The change's scope is narrower than "fix the image".** It removes one
  ATTRIBUTION CLASS permanently — everything carried by npm's own bundled tree.
  The image's remaining items are debian/ruby-layer items that this plan does
  not touch at all; they move with base-image bumps (there is an open dependabot
  PR for exactly that, §11.1). Read the current split off the finding record,
  never off this file: `runbooks/policy-cli.py finding list --section security
  --grep absenty`.
- **The structural argument is unaffected by the staleness.** "npm is in the
  runtime layer for no reason" is a fact about the Dockerfile, not about a scan,
  and §7.1/§7.2 assert it directly.

Whether a fresh driver finding should be filed before this executes is in
§12 (open questions) — filing one is an operator/DB action, deliberately not
taken by the agent that corrected this plan.

**Why the version-bump remedy is a dead end** (plain dependency-resolution
fact, safe to state): the driver attributes to npm's OWN bundled dependency
tree — the `node_modules` that ships *inside* the globally-installed npm, not
the application's `node_modules`. `npm ci` never touches the global install, so
no application dependency change or lockfile refresh can reach that tree.

The Dockerfile asserted that upgrading the global npm to 12.0.2 would move
them. **Verified 2026-08-18: it does not.** npm 12.0.2 and npm 11.19.0 bundle
*identical* versions of the relevant transitive dependencies. A global npm bump
moves the npm CLI, not npm's bundled tree. There is no npm version on either
line that changes this, so "bump the pin again" is not a remedy and must not be
re-attempted. *(The incorrect comment was already corrected in absenty
`516cbe04` so the next reader does not re-derive it.)*

**The actual remedy is structural.** The production runtime is Rails + puma and
never invokes npm. npm is a *build* tool that is present in the runtime layer
only as an accident of stage inheritance. Remove it from the runtime and the
entire class of finding leaves with it — permanently, rather than being chased
version by version.

## 2) Where npm comes from, and who actually needs it

`Dockerfile` **at committed `HEAD` (`f5e9b0f5`)** has one `base` stage that
every other stage inherits. *Line numbers in this section describe HEAD, not the
working copy: the worktree already carries the uncommitted restructure (§5a),
where the same content sits at different lines.*

```
FROM ruby:3.3.12-slim-bookworm AS base
  ...apt layer...
  COPY --from=node:22-bookworm-slim /usr/local/ /usr/local/    # line 17-18
  RUN npm install -g npm@12.0.2 && npm --version               # line ~26 (post-516cbe04)
  ...ENV / WORKDIR...

FROM base AS assets       # npm ci + npm run build && npm run build:css
FROM base AS gems         # bundle install only
FROM base AS production   # Rails + puma          <-- inherits node+npm for no reason
FROM base AS dev          # npm ci
```

Note the `COPY --from=node:...` merges node's **entire** `/usr/local` into the
ruby image, so the runtime layer carries not just `npm` but `node`, `npx`,
`corepack` and `yarn`, plus node's include/share/man trees.

| stage | needs node/npm? | why |
|---|---|---|
| `assets` | **yes** | `npm ci`, then `npm run build` / `build:css` → `npx esbuild`, `npx tailwindcss` |
| `dev` | **yes** | `npm ci`; the dev workflow also uses `npm run watch` |
| `gems` | no | `bundle install` only; no native gem in the lock needs node |
| `production` | **no** | see §3 |

## 3) Pre-check: prove the runtime never invokes npm

This is the gate for the whole plan. Do not proceed if any of these turns up a
caller. The CONCLUSIONS were verified read-only on 2026-08-18 and re-verified
2026-09-20; the COMMANDS below are the corrected forms — **the 2026-08-18 forms
misfired on this host and two of them failed in the direction that reads as
clean.** Re-run at execution time; the app moves.

**Why every gate now carries a CONTROL.** Measured 2026-09-20 on this Mac (zsh,
BSD/ugrep userland):

- `grep ... app/ lib/*.rb` — `lib/` holds only `assets/` and `tasks/`, so
  `lib/*.rb` matches nothing and **zsh aborts the entire command** with
  `no matches found`. `app/` was never searched and the gate printed nothing.
  A silent false clean, indistinguishable from a real pass.
- the `bun` token matched `bundle`/`bundler`, so gate 1 returned ~195 lines
  around the ~10 that meant anything — noise that trains a reader to skim.
- **`rg … .` silently skipped `.github/`** — found 2026-09-20 while re-running
  these gates verbatim, i.e. this section's own correction produced a fresh
  instance of the class. ripgrep does not descend into dot-directories without
  `--hidden`, so gate 3.4 reported `assets:precompile` as appearing nowhere
  while the single real invocation sat at `.github/workflows/ci-cd.yml:122`.
  Same shape as the zsh glob: a search that quietly narrowed, reading as a
  cleaner result.
- `timeout` and `gtimeout` **do not exist on this host**. Do not wrap any gate
  in them; the wrapper itself is the failure.

The control is the fix for the whole class: **if the control returns nothing,
the gate did not run, and that is a FAIL, not a pass.**

```bash
cd /Users/mu/code/absenty
# NOTE (§5a): this worktree already carries an UNCOMMITTED Dockerfile change.
# Confirm it is that change before any checkout/pull, and do NOT `git pull` over it.
git status --porcelain Dockerfile        # expect exactly: " M Dockerfile"
git rev-parse --abbrev-ref HEAD          # expect: development

# 3.1 Nothing on the boot path shells out to a JS toolchain.
#     Production CMD: bash -lc "bin/rails db:prepare && bundle exec puma -C config/puma.rb"
rg -n -e '\b(npm|npx|yarn|pnpm|esbuild|tailwindcss)\b' \
   bin/rails bin/rake config/puma.rb config/environments/production.rb config.ru Rakefile
#     CONTROL — the same six paths must be readable and non-empty:
rg -c -e 'rails|rake|Rails' \
   bin/rails bin/rake config/puma.rb config/environments/production.rb config.ru Rakefile
#     `bun` word-anchored and separate: un-anchored it matches bundle/bundler.
rg -n -e '\bbun\b' bin/rails bin/rake config/puma.rb config.ru Rakefile

# 3.2 No Ruby-side shell-out from application code at all.
#     `find`, never a glob: `lib/*.rb` matches nothing here and zsh then kills
#     the whole command — that is the false clean described above.
find app lib \( -name '*.rb' -o -name '*.rake' \) -print0 \
  | xargs -0 grep -nE 'system\(|IO\.popen|Open3|Kernel\.exec|%x'
#     CONTROL — how many files were actually scanned:
find app lib \( -name '*.rb' -o -name '*.rake' \) | wc -l

# 3.3 No gem can demand a JS runtime.
grep -ciE 'execjs|racer|libv8|nodejs|duktape|terser|uglifier|webpacker|shakapacker|sassc|dartsass|autoprefixer' Gemfile.lock
#     CONTROL — we are reading the right lockfile: these gems ARE present:
grep -cE 'cssbundling-rails|jsbundling-rails' Gemfile.lock

# 3.4 assets:precompile is never invoked at runtime.
#     --hidden is LOAD-BEARING. ripgrep does not DESCEND into dot-directories,
#     so a plain `rg ... .` never looks inside .github/ and reports the one real
#     CI invocation as absent. (Naming the file explicitly reads it either way;
#     it is recursion that skips it, which is exactly why it misses silently.)
#     The extra globs keep IDE/deploy caches out: .idea/.rakeTasks carries the
#     entire Rake task table on one line and buries every real hit.
rg -n --hidden -g '!.git' -g '!node_modules' -g '!.idea' -g '!.cap_task_cache' \
   -e 'assets:precompile|javascript:build|css:build|test:prepare' .
#     CONTROL — the traversal actually reaches the hidden .github tree:
rg -n --hidden -g '!.git' -c 'runs-on' . | head -5

# 3.5 No HEALTHCHECK in the image.
grep -c HEALTHCHECK Dockerfile
#     CONTROL — the Dockerfile is being read at all (stage count):
grep -c '^FROM' Dockerfile

# 3.6 Nothing in the CLUSTER execs into the container (probes, hooks, sidecars).
cd /Users/mu/code/cberg-home-nextgen
kubectl -n my-software-production get deploy absenty -o json | python3 -c "
import sys, json
d = json.load(sys.stdin)['spec']['template']['spec']
c = d['containers'][0]
probes = {k: (v or {}).get('exec') for k, v in
          ((p, c.get(p)) for p in ('livenessProbe','readinessProbe','startupProbe'))}
print('containers   :', [x['name'] for x in d['containers']])          # CONTROL: must be non-empty
print('initContainers:', [x['name'] for x in d.get('initContainers',[])])
print('command/args :', c.get('command'), c.get('args'))
print('probe exec   :', probes)                                        # all three must be None
print('lifecycle    :', c.get('lifecycle'))
"
```

Expected result, and what it means (all MEASURED 2026-09-20 unless noted):

- **Controls first.** 3.1's control listed **5 of the 6** boot files with
  non-zero match counts (`config.ru` legitimately contains neither token, which
  is why the control reports per-file counts rather than a single number);
  3.2 scanned **57** `.rb`/`.rake` files; 3.3's control found the bundling gems
  (`cssbundling-rails`/`jsbundling-rails`) in `Gemfile.lock`; 3.4's control
  returned rows from `.github/workflows/`, proving the traversal reached the
  hidden tree; 3.5's control counted the Dockerfile's **6** `FROM` stages; 3.6's
  control returned a non-empty container list. Controls returning those rows is
  what makes the empty results below mean anything at all.
- **Boot path is Ruby-only.** `bin/rails`, `bin/rake`, `bin/bundle`,
  `config/boot.rb`, `config/application.rb`, `config/environments/production.rb`
  and `config/puma.rb` contain no shell-out. `bin/rails` references
  `SKIP_YARN_INSTALL`/`SKIP_BUN_INSTALL` but only on a `test*` ARGV branch,
  which `db:prepare` never takes. Hits in `bin/setup` and `bin/ci` are
  developer/CI scripts, not on the container CMD path.
  `docker/entrypoint.sh` exists but is dead code — the Dockerfile never
  `COPY`s it and sets no `ENTRYPOINT`.
- **Application code has zero shell-out.** The only `system()` calls in the
  repo are in `lib/tasks/linting.rake`, a dev-only rubocop/brakeman task.
- **No JS-runtime gem.** The grep over `Gemfile.lock` returns nothing.
- **`assets:precompile` is not in the runtime path.** 3.4 returns five hits and
  **exactly one is an invocation**: `.github/workflows/ci-cd.yml:122`
  (`run: bundle exec rails assets:precompile`) — CI only, never in the image.
  The other four are text, not calls: `lib/tasks/test.rake:5` (clears the
  `test:prepare` prerequisites), `Dockerfile:102` (§6's self-explaining
  comment), `docs/deployment.md:36` and `doc/TESTING.md:49` (prose). **Count
  invocations, not lines** — and note the older wording here ("appears exactly
  once") was only ever "true" because the search was skipping `.github/`
  entirely. The image build instead runs `npm run build && npm run build:css`
  in the `assets` stage and `COPY --from=assets /app/app/assets/builds` into
  `production`.
- **No `HEALTHCHECK`**, and the cluster probes are all `httpGet`
  (`/health/{liveness,readiness,startup}`) with no `exec:`, no
  `initContainers`, no sidecars, and no `command:`/`args:` override on the
  production HelmRelease. No CronJob runs against this image. **Re-measured
  2026-09-20 via 3.6** — every probe's `exec` is `None`, all three are `httpGet`
  on port 3000 (`/health/{liveness,readiness,startup}`), and the control (the
  container list) is non-empty. The **development** Deployment does carry a
  `bundle-install` initContainer and a `command:` override; that is the dev lane
  and it keeps node deliberately (§7.3).

**The one subtlety that must be understood before touching this — read it.**
`cssbundling-rails` and `jsbundling-rails` *are* in the Gemfile. They enhance
`assets:precompile` **and** `test:prepare` with `css:build` / `javascript:build`,
which shell out to `npm run ...`. They are the one mechanism that could
plausibly invoke npm at runtime. They do not, because:

- the production CMD runs `db:prepare`, which is **not** `db:test:prepare` and
  does not depend on it; and
- `assets:precompile` is never invoked in the image.

`lib/tasks/test.rake` already clears the `test:prepare` prerequisites with an
in-repo comment about avoiding esbuild/tailwind during test prep — direct
evidence the enhancement exists and is understood as a test-path concern.
**If a future change adds `assets:precompile` to the runtime CMD, this plan's
assumption breaks.** That is why §6 adds a comment making the failure
self-explaining.

**Second subtlety — sprockets live-compiles at runtime, and that is fine.**
Nothing sets `config.assets.compile`, there is no `config/initializers/assets.rb`,
`public/assets` is excluded in `.dockerignore`, and the image never runs
`assets:precompile`. So the container has no sprockets manifest and serves
assets through sprockets-rails' default live-compilation. That path is **pure
Ruby** over the already-built files in `app/assets/builds`: no JS compressor is
configured, `app/assets/config/manifest.js` links only `../images` and
`../builds`, and `vendor/assets/*` holds only `.gitkeep`. There is no `.erb` /
`.scss` / `.coffee` asset that could pull in a JS runtime. Removing node does
not affect it — but it *does* mean the fingerprinting in §7 is generated at
request time, which is exactly what the verification checks.

## 4) Baseline to capture before changing anything

> **There is NO container runtime on the executor host.** Measured 2026-09-20:
> `docker`, `podman`, `nerdctl`, `colima`, `lima`, `finch`, `crane`, `skopeo`,
> `regctl`, `oras`, `buildah` are **all absent**; there is no docker socket and
> no Docker.app / OrbStack / Rancher. The previous version of this section
> (`docker image inspect`) could not run at all, and neither could three of the
> four image checks in §7. Every baseline below is taken from the **registry**,
> the **running pod**, or the **served bytes**. `trivy` 0.70.0 IS installed and
> authenticates to GHCR with a `gh` token.

**4.1 — source position of both lanes**

```bash
cd /Users/mu/code/absenty
git rev-parse --short HEAD                  # 2026-09-20: f5e9b0f5 (== origin/development)
git log --oneline -1 origin/production      # 2026-09-20: 54e9fc8d
```

Both deployed images were built from the **current** branch heads: the
production image's config `created` is `2026-08-18T18:56:29Z`, three minutes
after `54e9fc8d` landed at 18:53:40Z. That is what makes §7.5's before/after
comparison meaningful — the only source delta between the deployed image and
the next production build will be the Dockerfile stage split, **provided the
§11.1 dependabot freeze holds**. If it does not, this plan is re-baselined, not
executed (the `no-newer-production-tag-has-been-published` premise enforces it).

**4.2 — image size, from the registry manifest (compressed layer bytes)**

```bash
TOKEN=$(curl -s -u "x:$(gh auth token)" \
  "https://ghcr.io/token?service=ghcr.io&scope=repository:nachtschatt3n/absenty:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for TAG in production-20260818185444 development-20260818184524; do
  curl -s -H "Authorization: Bearer $TOKEN" \
       -H "Accept: application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json" \
       "https://ghcr.io/v2/nachtschatt3n/absenty/manifests/$TAG" \
  | python3 -c "
import sys, json
m = json.load(sys.stdin)
print('$TAG', len(m['layers']), 'layers', round(sum(l['size'] for l in m['layers'])/1048576, 1), 'MB compressed')"
done
```

MEASURED 2026-09-20 — **production: 15 layers, 352.1 MB compressed;
development: 15 layers, 399.9 MB.** Two different numbers from one command is
this probe's own control: it demonstrably reads the tag it is handed rather
than returning a constant. Note these are **compressed** bytes, not the
uncompressed size `docker image inspect` used to report — the §7.6 expectation
is stated in the same unit.

**4.3 — runtime inventory inside the RUNNING production pod**

```bash
kubectl -n my-software-production exec deploy/absenty -- sh -c \
  'for b in node npm npx corepack yarn nodezzz; do
     if command -v $b >/dev/null 2>&1; then echo "PRESENT $b"; else echo "absent  $b"; fi
   done'
```

MEASURED 2026-09-20: `PRESENT node`, `PRESENT npm`, `PRESENT npx`,
`PRESENT corepack`, `absent yarn`, `absent nodezzz`. `node v22.23.2`,
`npm 12.0.2`, and `/usr/local/lib/node_modules` exists. The deliberate
`nodezzz` probe is the **negative control**: it proves the `absent` branch
prints for something that genuinely is not there, so an `absent` line is
evidence rather than an artefact of a broken loop.

**4.4 — package inventory of the production image, from the registry**

```bash
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
mise exec -- trivy image --quiet --scanners vuln --list-all-pkgs --format json \
  --severity CRITICAL ghcr.io/nachtschatt3n/absenty:production-20260818185444 \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
n = sum(len(r.get('Packages') or []) for r in d.get('Results', []) if r.get('Type') == 'node-pkg')
print('node-pkg packages:', n)
print('image created    :', d['Metadata']['ImageConfig']['created'])"
```

MEASURED 2026-09-20: **node-pkg packages: 151**, created
`2026-08-18T18:56:29Z`. 149 of the 151 sit under `usr/local/lib/node_modules/`
— i.e. npm's own bundled tree, exactly the class §1 says cannot be moved by any
npm version bump. (`--severity CRITICAL` only narrows the vulnerability table;
`--list-all-pkgs` enumerates the full inventory regardless, which is the part
this gate reads.)

**4.5 — served-asset and on-disk bundle baseline**

Capture both, from the pod that is serving right now (§7.5 compares against
these):

```bash
kubectl -n my-software-production port-forward svc/absenty 18080:3000 &
curl -s http://127.0.0.1:18080/users/sign_in \
  | rg -o '/assets/[A-Za-z0-9._/-]+-[0-9a-f]{64}\.(js|css)' | sort -u
kubectl -n my-software-production exec deploy/absenty -- sh -c \
  'cd /app/app/assets/builds && find . -type f | sort | xargs sha256sum'
```

MEASURED 2026-09-20 on `production-20260818185444` — served fingerprints:

| asset | bytes |
|---|---|
| `/assets/application-43074dc7d7528f7dba38dd2cfee35b037e7c1c6aa88516cf05c3a2d57024ac54.css` | 29,182 |
| `/assets/application-a33158a9e255e39b51f7fe0c8fbc3f8e07fb706ca446ff8cb6e8c16c5bf1dd55.js` | 2,273,728 |
| `/assets/entrypoints/login-0c6d073f6d1eb0658138eb7bb765fffe7be4d4f07024b30450b2c92de536abe5.js` | 1,108,677 |

and on-disk `/app/app/assets/builds`:

```
53a417c0b1933115f513cb362dff965f3f4ae3f8aa2e373c6a2f2b50e38b79b0  ./application.css
f200563bb0a1fea916acd1fea0859b2157669f6fb48f9316f7827a61a25ea573  ./application.js
2a820ad87300f11a1da9ac84fb6affd77efbf60342107fa95beeef6a00c0a503  ./application.js.map
755158e00a3a28a57dfb2c67bcf6bafc1ab5f4ecbddc164a6a33524a87f4eb75  ./entrypoints/login.js
828bb3af9bb4cc8dfe0ca9a4b9ef618fb004043e185c121e69b54dd9308a9238  ./entrypoints/login.js.map
```

Two measured properties make these usable as verification rather than
decoration:

1. **The 64-hex in each served URL IS the sha256 of the served body** —
   confirmed on 3 of 3 assets (`sha256(body) == the digest in its own URL`). So
   an unchanged fingerprint set is a byte-level identity proof of what the
   browser receives, with no container runtime involved.
2. **The on-disk list is sensitive enough to detect a real bundle difference**
   — the dev pod's `application.js` hashes `99373bee…` against production's
   `f200563b…` (different esbuild settings per lane). A check that can already
   tell two real builds apart is not a check that would sleep through a third.
   *Corollary: compare WITHIN a lane only. Dev-vs-prod differences are
   expected and are not a finding.*

## 5) The change

### 5a) The change is ALREADY WRITTEN, uncommitted, in the absenty worktree

**Confirmed read-only 2026-09-20.** `/Users/mu/code/absenty` has a modified,
uncommitted `Dockerfile` (` M Dockerfile`, +34/−13, mtime `2026-09-13 16:40` —
the deferred window). It is on branch `development` at `f5e9b0f5`, which equals
`origin/development`; it is **not committed, not pushed, and on no branch**, and
both `origin/development` and `origin/production` still carry the old stage
graph. It was diffed line by line against §5 below and **matches exactly**:

| §5 requires | in the worktree |
|---|---|
| `ENV BUNDLE_*` / `WORKDIR /app` stay in `base` | yes — lines 17–27, moved ABOVE the new stage |
| new `FROM base AS nodebase` | line 44 |
| node `COPY --from=node:22-bookworm-slim` + global npm pin inside `nodebase` | yes, both moved out of `base` |
| `assets` repointed | line 71 `FROM nodebase AS assets` |
| `gems` untouched | line 81 `FROM base AS gems` |
| `production` untouched → node-free | line 105 `FROM base AS production` |
| `dev` repointed | line 141 `FROM nodebase AS dev` |
| §6's self-explaining comment | lines 101–104, above the production stage |

It also carries the §5 hazard notes as comments (why `nodebase` must be
`FROM base`, why `rm -rf` in `production` was rejected).

**Consequences for execution — do not skip these:**

1. **Do not `git pull` over it, and do not `git stash` it away.** Confirm
   `git status --porcelain Dockerfile` is exactly ` M Dockerfile` and `git diff`
   still matches the table above before doing anything else.
2. **It is unreviewed as a commit.** Whether to commit this working copy or
   discard it and re-derive from §5 is an operator call (§12 Q1) — this plan's
   correction pass deliberately did not commit, push, or build anything in that
   repo.
3. **It changes nothing until it is committed and CI builds it.** The deployed
   production image predates it; the §4 baselines are all "before".

Smallest safe restructure: insert a `nodebase` stage between `base` and the two
stages that need node, and repoint them.

```
FROM ruby:3.3.12-slim-bookworm AS base
  ...apt layer...                      # unchanged
  ENV BUNDLE_* / RAILS_ENV / ...       # unchanged, STAYS in base
  WORKDIR /app                         # unchanged
  # the COPY --from=node:... and the `npm install -g` RUN are REMOVED from here

FROM base AS nodebase                  # new, ~4 lines
  COPY --from=node:22-bookworm-slim /usr/local/ /usr/local/
  RUN npm install -g npm@<pin> && npm --version

FROM nodebase AS assets                # was: FROM base
FROM base     AS gems                  # unchanged
FROM base     AS production            # unchanged -> now node-free
FROM nodebase AS dev                   # was: FROM base
```

Net diff: delete the node COPY + global-npm RUN from `base`, add a four-line
`nodebase` stage, change two `FROM base` lines to `FROM nodebase`. The
`COPY --from=assets /app/app/assets/builds` line in `production` is untouched.

### Why not just `rm -rf` the node files in the production stage

The alternative — keep `base` as-is and delete `/usr/local/bin/{node,npm,...}`
in `production` — is **rejected**, for three reasons:

1. **It hides rather than removes.** A `rm -rf` in a later layer deletes from
   the squashed filesystem, but the bytes remain in the inherited base layer:
   pull size stays inflated and the payload is recoverable from image history.
   A scanner reading the squashed filesystem goes quiet, which makes it *look*
   like a fix while the image still ships the content. That is precisely the
   failure mode this plan exists to avoid repeating.
2. **It is a hardcoded path list against another project's layout.** If the
   node image reorganises `/usr/local`, the deletion silently stops matching
   and there is no build failure to notice. The stage split fails loudly
   instead — if some stage secretly needed node, its build breaks immediately.
3. **It is dangerous adjacent.** `/usr/local` is shared with ruby itself and
   with `/usr/local/bundle`. An over-broad glob takes out the runtime.

### Hazards when splitting `base`

- Make `nodebase` **`FROM base`**, never a second `FROM ruby:3.3.12-slim-bookworm`.
  A parallel root duplicates the apt layer, the `ENV` block and `WORKDIR`, all
  of which then drift independently.
- Leave the `ENV BUNDLE_*` block in `base`. Moving it into `nodebase` silently
  strips it from `gems` and `production`.
- `dev` overrides `BUNDLE_WITHOUT=` / `BUNDLE_PATH=/bundle`. Keep that block
  after its `FROM nodebase`; `nodebase` adds nothing that conflicts.
- Build-cache shape changes: `assets` and `dev` now share a node layer that
  `production` does not. Cold build time is unchanged; a global-npm pin bump
  stops invalidating the `gems` layer, which is a small win.

## 6) Also update in the same change

- Add a short comment in the `production` stage recording that the runtime is
  deliberately node-free, and that adding `assets:precompile` (or any
  `test:prepare`-style rake path) to the runtime CMD will fail with
  `npx: not found` — by design.
- Re-evaluate the CI image-scan step. `.github/workflows/ci.yml` currently
  runs Trivy non-gating (`exit-code: 0`), and part of its stated justification
  no longer holds once npm leaves the runtime layer (see F-fec7ea4b), so the
  step may be able to gate again. **That comment is itself a disclosure-boundary
  problem** — it states current scan results inline rather than by reference —
  so rewrite it to a `security_ref` pointer in the same pass, and move its
  present wording onto the finding record.
  **Do not flip it to gating in the same change** — land the Dockerfile
  restructure first, observe one clean scan, then flip it in a follow-up so a
  newly-red CI is unambiguously attributable.

## 7) Verification

The failure mode to fear is **assets that stop serving**, not a failed build.
Check the served bytes, not the exit code and not HTTP 200 alone.

### 7.0 — What was wrong with this section, and what replaced it

Every gate below was **run on the executor host on 2026-09-20** in the form
written here. The previous version could not be: three of its four image checks
needed a container runtime that does not exist here, and the one check that
could run **could not fail**.

| old check | verdict | replacement |
|---|---|---|
| (a) `docker run … command -v node` | **cannot run** — no container runtime | **7.1** (registry, trivy) + **7.2** (running pod) |
| (b) build stages "implicitly proven" | not a check | **7.3** — an explicit floor: the dev lane must still HAVE node |
| (c) `docker image inspect --format {{.Size}}` | **cannot run** | **7.6** — registry manifest probe, compressed bytes |
| (d) bit-identical `sha256sum` of two image filesystems | **cannot run**, and this was the plan's self-declared headline signal | **7.5** — within-lane before/after, served fingerprints + in-pod bundle |
| cluster block: `port-forward svc/absenty 18080:80`, `GET /` | **cannot fail** (see below) | **7.4** — port **3000**, path **`/users/sign_in`** |

**Why the old cluster block could not fail — measured, because this is the
defect worth remembering.** `svc/absenty` exposes exactly one port,
`{name: http, port: 3000, targetPort: 3000}`; there is no port 80, so the
port-forward died with *"Service absenty does not have a service port 80"*.
Correct the port and it gets worse rather than better: `GET /` returns **HTTP
302 with a ZERO-BYTE body** (redirect to `/users/sign_in`). Both asset greps
then return **empty against a perfectly healthy pod**, and the `for` loop
written specifically to catch *"HTTP 200 with an empty body"* iterates zero
times and exits 0. **The check self-passed on no body at all.**

**The structural fix, applied to every gate below: each one carries a CONTROL
that MUST return rows in the healthy case.** An empty result is then
distinguishable from a pass — which is the entire class of defect, not just
this instance. (`docs/sops/verification-contents-not-shape.md`: *a health
signal that cannot distinguish "working" from "empty" is not a health signal*.)

**Honesty note on §7d.** The bit-identical comparison of two image filesystems
is **not restored** — it is not achievable on this host, and no substitute
(trivy included) can hash `/app/app/assets/builds` inside an arbitrary tag.
§7.5 is a genuinely different, weaker-in-scope assertion: it compares the
**running pod before** against the **running pod after**, so it is valid only
while nothing else perturbs the source tree (§11.1 freeze + premise). Report it
as that. Do not call it the old §7d.

### 7.1 — PRIMARY: the new production image carries no JS toolchain (registry)

```bash
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
count_node_pkgs() {
  mise exec -- trivy image --quiet --scanners vuln --list-all-pkgs --format json \
    --severity CRITICAL "$1" | python3 -c "
import sys, json
d = json.load(sys.stdin)
n = sum(len(r.get('Packages') or []) for r in d.get('Results', []) if r.get('Type') == 'node-pkg')
print('$1', 'node-pkg:', n, 'created:', d['Metadata']['ImageConfig']['created'])"
}

count_node_pkgs ghcr.io/nachtschatt3n/absenty:production-<NEW_TS>       # EXPECT: 0
count_node_pkgs ghcr.io/nachtschatt3n/absenty:production-20260818185444 # CONTROL: 151
count_node_pkgs ruby:3.3.12-slim-bookworm                               # NEG CONTROL: 0
```

- **EXPECT 0** on the new tag, and a `created` timestamp that is the new build's
  (a stale timestamp means CI re-tagged a cached image — trap 5 in
  `docs/sops/self-built-image-rebuild.md`).
- **CONTROL (sensitivity):** the same command on the currently-deployed tag
  returns **151** (measured 2026-09-20). This is what proves the probe can SEE
  node when node is there, so a `0` is a finding rather than a broken query.
- **NEGATIVE CONTROL (specificity), run 2026-09-20:** the same command against
  `ruby:3.3.12-slim-bookworm` — a genuinely node-free image — returns **0**.
  The pass state is reachable and is not an error artefact.

### 7.2 — PRIMARY: the RUNNING production container is node-free

Stronger than inspecting the image: it asserts the thing actually serving
traffic. (`kubectl exec` is read-only here and fine in a reviewed verification
step; it remains forbidden in a *premise*, which is free text that must not be
able to select an action.)

```bash
kubectl -n my-software-production exec deploy/absenty -- sh -c \
  'for b in node npm npx corepack yarn nodezzz; do
     if command -v $b >/dev/null 2>&1; then echo "PRESENT $b"; else echo "absent  $b"; fi
   done'
```

- **EXPECT:** `absent` for `node`, `npm`, `npx`, `corepack`, `yarn`, and
  `/usr/local/lib/node_modules` gone.
- **CONTROL (sensitivity), measured 2026-09-20 on the deployed pod:**
  `PRESENT node` / `PRESENT npm` / `PRESENT npx` / `PRESENT corepack`.
- **NEGATIVE CONTROL:** `absent nodezzz` — a binary that never existed. It
  proves the `absent` branch actually prints, so a column of `absent` lines is
  evidence and not a silently broken loop. **If `nodezzz` ever prints anything
  other than `absent`, discard the whole gate.**

### 7.3 — FLOOR: the DEV lane must still HAVE node

*A ceiling without a floor is a shape check* — "npm is gone" would also go
green if the stage split had broken the build stages outright. This is the limb
that separates *confined* from *destroyed*.

```bash
# SELF-CONTAINED ON PURPOSE. Every Bash call is a FRESH SHELL, so the export and
# the count_node_pkgs function defined in §7.1's block are NOT in scope here.
# Repeat them; do not assume §7.1 ran in this same shell (it did not).
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
count_node_pkgs() {
  mise exec -- trivy image --quiet --scanners vuln --list-all-pkgs --format json \
    --severity CRITICAL "$1" | python3 -c "
import sys, json
d = json.load(sys.stdin)
n = sum(len(r.get('Packages') or []) for r in d.get('Results', []) if r.get('Type') == 'node-pkg')
print('$1', 'node-pkg:', n, 'created:', d['Metadata']['ImageConfig']['created'])"
}

count_node_pkgs ghcr.io/nachtschatt3n/absenty:development-<NEW_TS>   # EXPECT: large (control: 931 today)
kubectl -n my-software-development exec deploy/absenty -c app -- sh -c \
  'command -v node && command -v npm'                                # EXPECT: both paths print
kubectl -n my-software-development get pods -l app.kubernetes.io/name=absenty
```

Measured 2026-09-20 on `development-20260818184524`: **931** node-pkg packages
(vs 151 in production — the dev image also carries the application's own
`node_modules`). A dev image that drops toward the production number means the
`dev` target lost its node layer: **STOP**, the split is wrong.

The dev Deployment's `bundle-install` initContainer and its `rails server`
command are the loud-failure path described in §8 — a broken dev image
crash-loops the init rather than failing quietly.

### 7.4 — The served page: 200, with markup, with fingerprinted assets

```bash
cd /Users/mu/code/cberg-home-nextgen
kubectl -n my-software-production get pods -l app.kubernetes.io/name=absenty   # 1/1, 0 restarts
kubectl -n my-software-production port-forward svc/absenty 18080:3000 &        # port 3000, NOT 80

# `/` is a ZERO-BYTE 302 -> /users/sign_in. The page that carries assets is the sign-in page.
curl -s -o /dev/null -w 'root:    status=%{http_code} size=%{size_download}\n' http://127.0.0.1:18080/
curl -s -o /tmp/absenty-signin.html -w 'sign_in: status=%{http_code} size=%{size_download}\n' \
  http://127.0.0.1:18080/users/sign_in

python3 - <<'PY'
import re, subprocess, hashlib, sys
html = open('/tmp/absenty-signin.html').read()
refs = sorted(set(re.findall(r'/assets/[A-Za-z0-9._/-]+-[0-9a-f]{64}\.(?:js|css)', html)))
print('fingerprinted refs:', len(refs))          # CONTROL: must be >= 3, else the gate did not run
ok = len(refs) >= 3 and len(html) > 1000
for a in refs:
    body = subprocess.run(['curl', '-s', 'http://127.0.0.1:18080' + a],
                          capture_output=True).stdout
    digest_in_url = re.search(r'-([0-9a-f]{64})\.', a).group(1)
    same = hashlib.sha256(body).hexdigest() == digest_in_url
    big  = len(body) > 1000
    html_error = body.lstrip().startswith(b'<!DOCTYPE')
    ok &= same and big and not html_error
    print(f'{a[:64]:64s} bytes={len(body):>9} sha==url:{same} html_error:{html_error}')
print('GATE', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
PY
```

- **CONTROL:** `len(refs) >= 3`. Zero refs is a **FAIL**, never a pass — that
  single assertion is what the old block was missing.
- **Measured 2026-09-20 on the deployed pod:** `sign_in: status=200
  size=7785`, 3 fingerprinted refs, all three `sha==url:True`, `GATE PASS`.
- A few hundred bytes, or a body starting with `<!DOCTYPE`, means sprockets
  failed to resolve and is serving an error page — **STOP and roll back**
  (§9.2). Finally load the sign-in page in a browser and confirm the React
  bundle mounts: a broken bundle returns 200 and renders nothing.

### 7.5 — HEADLINE: the bundle is byte-identical across the change

Two limbs, both against the §4.5 baseline, both within the production lane:

```bash
# (a) served fingerprints -- the 64-hex IS sha256(body), verified 3/3 in §4.5
curl -s http://127.0.0.1:18080/users/sign_in \
  | rg -o '/assets/[A-Za-z0-9._/-]+-[0-9a-f]{64}\.(js|css)' | sort -u

# (b) the on-disk bundle inside the new pod
kubectl -n my-software-production exec deploy/absenty -- sh -c \
  'cd /app/app/assets/builds && find . -type f | sort | xargs sha256sum'
```

- **EXPECT (a):** the identical three URLs listed in §4.5. Because the
  fingerprint is the sha256 of the served body, an unchanged set is a
  byte-level identity proof of what the browser receives.
- **EXPECT (b):** the identical five digests listed in §4.5.
- **CONTROL / sensitivity evidence:** limb (b) already discriminates between
  two real builds — the dev pod's `application.js` is `99373bee…` against
  production's `f200563b…`. It is not a check that returns "same" for
  everything.
- **A DIFFERENCE HERE IS A STOP.** This change alters the stage graph only;
  same esbuild, same inputs, same `COPY --from=assets`. A changed digest means
  something else moved — most likely a dependabot merge slipping past §11.1 —
  and the correct response is to find out what, not to accept it.

### 7.6 — CORROBORATING (not a gate on its own): the image got smaller

Re-run §4.2's registry probe against the new production tag. Expect a drop from
**352.1 MB compressed**, roughly the size of node's `/usr/local` tree minus
compression. Treat a *smaller* image as corroboration and a *same-or-larger*
image as a reason to re-check 7.1 — but do not pass or fail the change on this
number alone: compression flattens the delta, and layer counts move for
unrelated reasons.

### 7.7 — FLOOR: the rollout actually happened (NECESSARY, NOT SUFFICIENT)

```bash
kubectl -n my-software-production get pods -l app.kubernetes.io/name=absenty     # 1/1, 0 restarts
flux -n my-software-production get helmrelease absenty
# verify the LIVE POD's image, not the HelmRelease's Ready status:
kubectl -n my-software-production get pod -l app.kubernetes.io/name=absenty \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].image}{"\n"}{end}'
flux -n my-software-production get image policy absenty     # selected tag == <NEW_TS>
```

`rollout status` and a Ready HelmRelease both go green against the OLD
generation mid-upgrade — read the pod's image, which is why it is the last
command here rather than the first.

### 7.8 — Reporting

Quote the **finding record**, never counts from this file:
`runbooks/policy-cli.py finding list --section security --grep absenty`. Note
§1a before citing F-fec7ea4b: it is `resolved` and names a superseded tag.

## 8) Blast radius

> **This section is about the ARTIFACT. It is not the whole blast radius — read
> §9.1 before scheduling.** What follows is true and was never wrong: the change
> is confined to the build graph. What it omits is the DELIVERY path, which is
> automatic: merging the promotion PR rolls production unattended in roughly
> 10–40 minutes with nobody watching. A reader who stops here gets the
> pre-2026-09-20 picture.

- **The change is confined to the image's build graph.** No dependency version
  moves, no application code change, no database, no migration, no PVC, no
  shared infrastructure. No other app consumes this image.
- **The dev lane keeps node deliberately** — the `dev` target still builds from
  `nodebase`. Verify the dev image after the change too: the development
  HelmRelease overrides the command (`bundle install` initContainer, then
  `bin/rails db:prepare && rails server`), so a broken dev image shows up as a
  crashlooping init, not as a silent asset problem.
- **The realistic failure is a build break** (loud, caught in CI before any tag
  is published) or **assets that resolve differently at runtime** (quiet — §7 is
  built to catch it).
- Because CI publishes only from a branch push, a bad restructure is contained
  to the `development` lane until the promotion PR is opened. Do not skip the
  dev-lane soak.

## 9) Sequencing, blast radius, and rollback

> ### 9.0 — CORRECTION: the old pre-check was stale AND inverted
>
> Until 2026-09-20 this section asserted that `absenty-image-updates` was
> `Ready=False / GitOperationFailed` in both namespaces and that **"the
> helmrelease tag must be bumped by hand"**. **That is the opposite of the
> truth**, and the inversion is load-bearing in two places — it sets the blast
> radius and it silently breaks the rollback lever. It was corrected against a
> live measurement, not re-derived from prose.
>
> **MEASURED 2026-09-20, both `my-software-development` and
> `my-software-production`:**
>
> | fact | value |
> |---|---|
> | `Ready` | **True** — `Succeeded`, "repository up-to-date" |
> | `.spec.suspend` | **unset** |
> | `.spec.interval` | `30m` |
> | push target | branch `main` of this repo |
> | `lastAutomationRunTime` | `2026-09-20T11:06:13Z` (it runs, now) |
> | setter markers | **live** — `helmrelease.yaml:32` (prod), `:34` and `:43` (dev), each `# {"$imagepolicy": "<ns>:absenty:tag"}` |
> | `ImagePolicy` | `^production-(?P<ts>\d{14})$`, `numerical` **ascending** |
> | `ImageRepository` scan | `10m` |
>
> The automation object's own manifest already warns that *a suspended
> automation still reports `Ready=True`* — so `Ready` is not the field to read.
> Read `.spec.suspend`. Measured today it prints empty in both namespaces.

### 9.1 — Blast radius: merging the promotion PR auto-rolls PRODUCTION

There is **no manual gate**. The chain is fully automatic and needs nobody:

```
merge PR into `production`  →  ci.yml publishes production-<YYYYMMDDHHMMSS>
  →  ImageRepository scan            (≤ 10m)
  →  ImagePolicy selects it          (newest 14-digit ts wins)
  →  ImageUpdateAutomation           (≤ 30m) commits the new tag to main
  →  github-receiver webhook         (Ready, seconds)
  →  cluster-apps Kustomization applies
  →  HelmRelease upgrade, strategy: Recreate  →  PRODUCTION POD REPLACED
```

**Expect production to roll unattended within roughly 10–40 minutes of the
merge, with no further human action.** Anyone who merges the promotion PR and
walks away has shipped to production. Plan the window around that, not around
a hand bump that no longer exists.

**If a human gate is actually wanted, make it explicit — do not lean on a
broken automation.** The durable, GitOps-correct form is to commit the
suspension, because `flux suspend` writes only to the cluster and the next
`cluster-apps` reconcile re-applies the manifest from git:

```bash
# GATE ON (in THIS repo, committed — survives reconciliation):
#   kubernetes/apps/my-software-production/absenty/app/image-automation.yaml
#   under the ImageUpdateAutomation `spec:`  →  add   suspend: true
# then verify it actually landed in the cluster:
kubectl -n my-software-production get imageupdateautomation absenty-image-updates \
  -o jsonpath='suspend=[{.spec.suspend}]{"\n"}'     # expect: suspend=[true]

# GATE OFF, after §7 passes: revert that one line and re-verify:
#   expect: suspend=[]
```

`flux -n my-software-production suspend image update absenty-image-updates`
exists and takes effect instantly — keep it as the **emergency stop** if a roll
is already in flight — but treat it as temporary: it is cluster-only drift that
the next reconcile of the committed manifest can undo without warning.

### 9.2 — Rollback

**Read 9.1 first: while the automation is live, a hand-pin of the tag does not
stick.** The `Setters` strategy rewrites `helmrelease.yaml`'s tag back to
whatever the ImagePolicy currently selects — and after a bad promotion that is
the *bad* tag. A pin applied without suspending is silently reverted inside 30
minutes, and the reverting commit is authored by `fluxcdbot`, so it does not
look like anyone undid anything.

Ordered, from fastest to most complete:

1. **Stop the automation first** (always step 1 of any cluster-side rollback):
   `flux -n my-software-production suspend image update absenty-image-updates`,
   then commit `suspend: true` as in §9.1 so the reconcile cannot undo it.
2. **Then pin** `kubernetes/apps/my-software-production/absenty/app/helmrelease.yaml`
   back to `production-20260818185444` and let Flux reconcile. Verify against
   the **live pod**, not the HelmRelease's Ready status:
   `kubectl -n my-software-production get pod -l app.kubernetes.io/name=absenty -o jsonpath='{.items[*].spec.containers[*].image}'`
3. **Before promotion:** `git revert` the Dockerfile commit on `development`,
   push, let CI publish a replacement dev tag.
4. **After promotion:** `git revert` the promotion merge on `production`; CI
   republishes from the reverted tree. Because the policy is
   **numerical-ascending on the build timestamp**, the reverted rebuild gets a
   *newer* timestamp and is selected normally — you do not need to delete or
   re-tag anything. Resume the automation (§9.1 GATE OFF) once that tag is live.

## 10) Risk & duration

- **risk: low.** No version moves at all — this is a stage-graph refactor that
  removes files from one layer. The residual uncertainty is the sprockets
  live-compile path (§3, second subtlety), which §7.4 and §7.5 exercise
  end-to-end against the running pod.
- **The headline signal is NOT what this plan used to claim.** The old §10 said
  the asset bytes are *bit-identical* per §7d and called it "an unusually strong
  verification signal: most changes cannot assert that". **§7d could not run at
  all on the executor host** — it needed `docker run`, and there is no container
  runtime here. Its replacement (§7.5) is a within-lane before/after comparison
  of the served fingerprints and the in-pod bundle. That is still a byte-level
  identity claim, and for the risk that matters (what a browser receives) it is
  arguably better evidence — but it is **conditional on the source tree being
  otherwise unchanged**, which is why §11.1's freeze and the
  `no-newer-production-tag-has-been-published` premise are now part of the plan
  rather than advice. State it that way in the report; do not re-inherit the
  old superlative.
- **est_duration_min: 90** (was 60). The old figure costed a local
  `docker build` that cannot happen here. Revised: ~10 min §3/§5a pre-checks and
  §4 baseline capture, ~5 min commit on `development`, ~10 min dev-lane CI round
  trip, ~15 min dev soak (§7.3), ~10 min freeze/suspend sequencing (§9.1,
  §11.1), ~10 min promotion PR + CI, ~10–40 min unattended auto-roll (§9.1),
  ~15 min §7 verification on production. The auto-roll wait is the reason this
  wants an attended slot with real headroom, not a 90-minute one packed to the
  brim.
- Most of the work is **cross-repo and not a cluster change**. The window is
  needed for the promotion, the auto-roll, and the verification — not for a
  hand-applied tag bump, which no longer exists (§9.0).

## 11) Interference surface

### 11.1 — PRE-CHECK: freeze the dependabot queue (18 open PRs)

**MEASURED 2026-09-20: 18 open PRs, ALL authored by dependabot, ALL targeting
the `production` branch** (`#36`–`#56`; 0 open PRs target `development`). They
include npm-tree bumps and a **ruby base-image bump `3.3.6` → `3.4.7` (#37)`**.

```bash
cd /Users/mu/code/absenty
gh pr list --base production --state open --json number --jq 'length'        # 2026-09-20: 18
gh pr list --base production --state open --json number,author \
  --jq '[.[] | select(.author.login=="app/dependabot")] | length'            # 2026-09-20: 18
#  CONTROL — the query reaches GitHub and discriminates by base branch:
gh pr list --base development --state open --json number --jq 'length'       # 2026-09-20: 0
```

**SUPERSEDED 2026-09-20 BY OPERATOR DECISION (§12 Q3).** The freeze below was
NOT adopted. The operator chose to drain the queue instead: "the dependabot PRs
should also be executed if they're not breaking anything". Six non-breaking PRs
were merged into `production` on 2026-09-20 (#42, #54, #63, #64, #65, #66, #68 —
patch/minor only, each re-classified AT MERGE TIME), CI published
`production-20260920181830`, and the ImagePolicy selected it.

**Consequences, all of which are working as designed:**
- The `no-newer-production-tag-has-been-published` premise FAILS and blocks
  execution. Correct — do not relax it.
- §4.5's recorded digests and §7.5's bit-identical assertion are INVALIDATED.
  They describe `production-20260818185444`; the comparison baseline must be
  re-taken against the post-drain image before this plan can run.
- §9.1's auto-roll hazard was pre-empted: both `image-automation.yaml` files
  carry `suspend: true` (commit 6194c9f1), so the six merges did NOT roll
  production. The live Deployment is still on `production-20260818185444`.
  That suspend is §12 Q2 answered in the affirmative and must be reverted only
  after this plan passes §7.

**TO UNBLOCK:** (1) finish or deliberately stop the drain; (2) re-take §4.5's
digests and §2.x baselines against the then-current production image; (3) update
this premise's `expect_exact` to that tag IN THE SAME CHANGE as (2) — never
alone, or the premise passes while the comparison is still stale; (4) revert the
automation suspend after §7 passes.

The original freeze rationale is retained below because it explains WHY the
comparison is fragile, which is still true:

**Merge none of them** from the moment the dev-lane soak starts until §7 has
passed on production. Any merge into `production` publishes a new
`production-<ts>` tag, which (a) is selected immediately by the ascending
numerical policy and rolls production on its own (§9.1), and (b) puts a
dependency delta inside the same image, which destroys §7.5 — the comparison
stops being "the stage split changed nothing" and becomes "something changed,
unclear what".

This is no longer advice: the **`no-newer-production-tag-has-been-published`
premise fails closed** if the selected tag has moved off
`production-20260818185444`, and `plan-premises.py` blocks execution.

The ruby `3.4.7` bump specifically **must not share this window** — it changes
the `base` stage this plan is restructuring. Sequence it after, as its own
change, with its own re-baselined §4.5 digests (§12 Q3).

### 11.2 — Other plans

- Touches only `absenty` in `my-software-development` and
  `my-software-production`. No shared datastore, no ingress-controller
  involvement, no reboot. Safe to co-schedule with unrelated small plans.
- **Do not co-schedule with any other absenty change**, including a routine
  dependency-refresh batch — same reason as §11.1.
- If an absenty dependency refresh is queued for the same window, land **this**
  plan first and the refresh after, so each gets an unambiguous verification.

## 12) Open questions for the operator

These need a decision before execution. They were deliberately NOT decided by
the 2026-09-20 correction pass, which was read-only outside this file.

1. **The uncommitted Dockerfile (§5a).** It matches §5 exactly and is dated to
   the deferred 2026-09-13 window. Commit that working copy as-is at execution
   time, or discard it and re-derive from §5 so the change has a clean,
   reviewed provenance?
2. **The manual gate (§9.1).** Accept the unattended ~10–40 min auto-roll to
   production after the promotion merge, or commit `suspend: true` to both
   `image-automation.yaml` files for the duration of the window and revert it
   after §7 passes? The second costs two extra commits and is the only durable
   form of the gate the old §9 wrongly believed it already had.
3. **Dependabot (§11.1).** Freeze all 18 for the window — or merge the ruby
   `3.4.7` base bump FIRST, let production roll on it, and re-baseline §4.5
   before this plan runs? Both are defensible; they cannot be combined.
4. **The security driver (§1a).** F-fec7ea4b is `resolved` and names a
   superseded tag. File a fresh driver finding for the npm-in-runtime class
   (a DB write, `policy-cli.py finding add`), repoint `security_ref` at it —
   or let this plan execute with the historical reference and no live finding?
