---
plan_id: absenty-drop-npm-runtime
component: absenty
pr: null                              # self-owned image; no upstream PR
kind: image
current: "node + npm installed in the Dockerfile `base` stage, inherited by `production`"
target: "node + npm confined to the build stages (`assets`, `dev`); `production` runtime is node-free"
update_type: refactor                 # Dockerfile stage restructure, no dependency version moves
risk: low
est_duration_min: 60
needs_reboot: false
touches:
  namespaces: [my-software-development, my-software-production]
  resources:
    - helmrelease/absenty                       # both namespaces
    - "ghcr.io/nachtschatt3n/absenty"
  shared: []
depends_on: []
conflicts_with: []
status: draft
window: null
# auto_execute RETIRED 2026-08-26 (P2.1b) — execution class is now DERIVED
# from capability_change/rollback_class per runbooks/autonomy-policy.yaml.
# (original rationale: changes the shape of the production runtime image)
security_ref: F-fec7ea4b              # security driver; detail is DB-only
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

`Dockerfile` today has one `base` stage that every other stage inherits:

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
caller. Findings below were verified read-only on 2026-08-18 against
`development`; **re-verify at execution time**, since the app moves.

```bash
cd /Users/mu/code/absenty && git checkout development && git pull --ff-only

# 1. Nothing on the boot path shells out to a JS toolchain.
#    Production CMD is: bash -lc "bin/rails db:prepare && bundle exec puma -C config/puma.rb"
grep -nE 'npm|npx|yarn|bun|pnpm|node|esbuild|tailwindcss' \
  bin/* config/*.rb config/environments/production.rb config.ru Rakefile lib/tasks/*.rake

# 2. No Ruby-side shell-out from application code at all.
grep -rnE 'system\(|IO\.popen|Open3|Kernel\.exec|`|%x' app/ lib/*.rb

# 3. No gem can demand a JS runtime.
grep -niE 'execjs|racer|libv8|nodejs|duktape|terser|uglifier|webpacker|shakapacker|sassc|dartsass|autoprefixer' Gemfile.lock

# 4. assets:precompile is never invoked at runtime.
grep -rnE 'precompile|javascript:build|css:build' --include='*.rb' --include='*.rake' \
  --include='*.yml' --include='Dockerfile' . | grep -v node_modules

# 5. No HEALTHCHECK in the image.
grep -n HEALTHCHECK Dockerfile
```

Expected result, and what it means:

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
- **`assets:precompile` is not in the runtime path.** It appears exactly once
  outside `node_modules`, in `.github/workflows/ci-cd.yml` — CI only. The image
  build instead runs `npm run build && npm run build:css` in the `assets` stage
  and `COPY --from=assets /app/app/assets/builds` into `production`.
- **No `HEALTHCHECK`**, and the cluster probes are all `httpGet`
  (`/health/{liveness,readiness,startup}`) with no `exec:`, no
  `initContainers`, no sidecars, and no `command:`/`args:` override on the
  production HelmRelease. No CronJob runs against this image.

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

```bash
cd /Users/mu/code/absenty
git rev-parse --short HEAD
docker image inspect ghcr.io/nachtschatt3n/absenty:production-latest \
  --format '{{.Size}}' 2>/dev/null || echo "(pull first)"
```

Record the production image size — the expected shrink is one of the
verification signals (§7).

## 5) The change

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

```bash
# a) the production image no longer carries a JS toolchain
docker run --rm --entrypoint sh ghcr.io/nachtschatt3n/absenty:production-<NEW_TS> \
  -c 'for b in node npm npx corepack yarn; do command -v $b || echo "$b: absent (expected)"; done'

# b) build stages still have it (assets must be able to build at all)
#    -- implicitly proven: if they did not, the image build would have failed.

# c) image got smaller
docker image inspect ghcr.io/nachtschatt3n/absenty:production-<NEW_TS> --format '{{.Size}}'
#    compare against the §4 baseline

# d) the emitted bundle is unchanged by the restructure
#    (this change must not alter asset CONTENT at all -- same esbuild, same
#     inputs, only a different stage graph)
docker run --rm --entrypoint sh ghcr.io/nachtschatt3n/absenty:production-<NEW_TS> \
  -c 'cd /app/app/assets/builds && find . -type f | sort | xargs sha256sum'
#    diff against the same command run on production-<PREVIOUS_TS>: expect IDENTICAL
```

Cluster-side, after the tag lands via GitOps:

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- kubectl get pods -n my-software-production | grep absenty   # 1/1, 0 restarts
mise exec -- kubectl -n my-software-production port-forward svc/absenty 18080:80 &

# the page loads AND references a fingerprinted bundle
curl -s http://127.0.0.1:18080/ -o /tmp/absenty-index.html -w 'status=%{http_code}\n'
grep -oE '/assets/[A-Za-z0-9._/-]+-[0-9a-f]{8,}\.(js|css)' /tmp/absenty-index.html | sort -u

# every referenced bundle actually serves real content -- HTTP 200 with an
# empty or HTML-error body is the trap this check exists to catch
for a in $(grep -oE '/assets/[A-Za-z0-9._/-]+-[0-9a-f]{8,}\.(js|css)' /tmp/absenty-index.html | sort -u); do
  printf '%-70s %s %s bytes  %s\n' "$a" \
    "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18080$a)" \
    "$(curl -s http://127.0.0.1:18080$a | wc -c)" \
    "$(curl -s http://127.0.0.1:18080$a | head -c 60 | tr -d '\n')"
done
```

A fingerprinted `application-<digest>.js` must return 200 with a multi-hundred-KB
JS body. A few hundred bytes, or a body starting with `<!DOCTYPE`, means
sprockets failed to resolve and is serving an error page — treat as a STOP and
roll back. Finally load the login page in a browser and confirm the React
bundle mounts: a broken bundle returns 200 and renders nothing.

Compare resulting counts against the finding record, not against this file:
`runbooks/policy-cli.py finding show F-fec7ea4b`.

## 8) Blast radius

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

## 9) Rollback

- **Before promotion:** `git revert` the Dockerfile commit on `development`,
  push, let CI publish a replacement dev tag.
- **After promotion:** `git revert` the promotion merge on `production`; CI
  republishes from the reverted tree.
- **Immediate cluster recovery:** pin
  `kubernetes/apps/my-software-production/absenty/app/helmrelease.yaml` back to
  the last known-good `production-*` tag and let Flux reconcile. That is the
  fastest path back and does not depend on a CI round trip.

> **Window pre-check (2026-08-18):** the `absenty-image-updates`
> ImageUpdateAutomation in BOTH `my-software-development` and
> `my-software-production` is `Ready=False / GitOperationFailed`
> (`GitRepository/flux-system` is an HTTPS URL with no write credential, so the
> automation cannot push). Until that is fixed, **the helmrelease tag must be
> bumped by hand in this repo** — do not wait for the automation to roll a new
> image during this plan's window.

## 10) Risk & duration

- **risk: low.** No version moves at all — this is a stage-graph refactor that
  removes files from one layer. The asset bytes are expected to be *bit-identical*
  (§7d), which is an unusually strong verification signal: most changes cannot
  assert that. The residual uncertainty is the sprockets live-compile path
  (§3, second subtlety), which §7's fingerprinted-bundle check exercises
  end-to-end.
- **est_duration_min: 60.** ~15 min for the Dockerfile restructure and a local
  `docker build` of the `production` target, ~10 min dev-lane CI round trip,
  ~15 min dev soak, ~20 min promotion PR, tag bump and cluster verification.
  Fits a 90-minute slot with rollback headroom.
- Most of the work is **cross-repo and not a cluster change**. Only the
  promotion and the tag move need the window.

## 11) Interference surface

- Touches only `absenty` in `my-software-development` and
  `my-software-production`. No shared datastore, no ingress-controller
  involvement, no reboot. Safe to co-schedule with unrelated small plans.
- **Do not co-schedule with any other absenty change**, including a routine
  dependency-refresh batch. This plan's headline verification is that the
  emitted asset bundle is bit-identical before and after; a dependency bump
  landing in the same image destroys that signal and turns a clean check into
  an ambiguous one.
- If an absenty dependency refresh is queued for the same window, land **this**
  plan first and the refresh after, so each gets an unambiguous verification.
