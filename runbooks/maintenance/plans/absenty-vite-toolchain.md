---
plan_id: absenty-vite-toolchain
component: absenty
pr: null                              # self-owned image; no upstream PR
kind: image
current: "esbuild ^0.25.10 direct devDependency (lockfile 0.25.12)"
target: "esbuild ^0.28 (a line built on a current Go toolchain)"
update_type: major                    # esbuild is pre-1.0: every minor may break
risk: low
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [my-software-development, my-software-production]
  resources:
    - helmrelease/absenty                       # both namespaces
    - "ghcr.io/nachtschatt3n/absenty"
  shared: []
depends_on: []
conflicts_with: [harness-frontend-vite7]   # SAME root cause, DIFFERENT remedy, no shared
                                           # work — do not co-schedule. See §10 for the
                                           # operator override if capacity forces a pairing.
status: draft
window: null
auto_execute: false                   # bundler major on the asset build path
security_ref: F-b8fbb7de              # security driver; detail is DB-only
sops_refs:
  - docs/sops/vulnerability-disclosure.md
  - docs/sops/self-built-image-rebuild.md
generated: "2026-08-18"
---

# absenty: move the direct esbuild devDependency off the ^0.25 line

## 1) Summary & why held

The 2026-08-18 dependency promotion (absenty `b470a9fe`, promoted to
`production` as PR #59 / merge `ad33a415`) cleared the lockfile-pinned gem
findings. One item survives it by construction, because it is not an npm
package version problem at all.

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-b8fbb7de**. The advisory IDs, the affected binary paths, the
> before/after counts and the exploitability assessment live on the finding
> record, not here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-b8fbb7de`
> - CLI: `runbooks/policy-cli.py finding show F-b8fbb7de`
>
> Convention: `docs/sops/vulnerability-disclosure.md`.

**Why a dependency bump cannot fix it** (plain dependency-resolution fact, safe
to state): `esbuild` ships a precompiled **Go** binary per platform
(`@esbuild/linux-x64/bin/esbuild`). The findings are in the Go standard library
that binary was compiled against, so they move only when esbuild itself is
rebuilt on a newer Go toolchain — i.e. when the **esbuild release line** moves.
No npm-level patch, lockfile refresh or `npm audit fix` can reach inside a
compiled binary. `npm audit` does not even see it: it reports 0 high on this
tree today.

## 2) What actually needs to move — and what does NOT

This is the part where absenty differs from the harness case, and where the
original finding text is now stale. Verify it before planning any work:

```bash
cd /Users/mu/code/absenty && git checkout development && npm ci --ignore-scripts
python3 -c "
import json; p=json.load(open('package-lock.json'))['packages']
for k in ('node_modules/esbuild','node_modules/vite','node_modules/vite/node_modules/esbuild','node_modules/vitest'):
    print(k, '->', p.get(k,{}).get('version'))"
```

As of `b470a9fe` this prints:

| path | version | state |
|---|---|---|
| `node_modules/esbuild` | **0.25.12** | **must move** — direct devDependency, `^0.25.10` in `package.json` |
| `node_modules/vite` | 7.3.6 | already current |
| `node_modules/vite/node_modules/esbuild` | **0.28.2** | **already ≥0.28** after the same bump |
| `node_modules/vitest` | 3.2.7 | fine (vite peer range `^5 \|\| ^6 \|\| ^7`) |

So:

- **NOT needed: a vite major.** absenty is already on vite 7, and vite 7.3.6
  declares `esbuild: ^0.27.0 || ^0.28.0` — its nested copy resolved to 0.28.2
  on its own. The finding's original action line ("possibly vite 8") was written
  against the pre-bump image and is **obsolete**; do not plan vite 8 work.
- **NEEDED: one line in `package.json`** — `devDependencies.esbuild`
  `^0.25.10` → `^0.28.0`, plus the refreshed `package-lock.json`.

Note where vite sits in this repo: absenty does **not** build with vite. The
bundler is a direct esbuild CLI call, and vite is present only because `vitest`
depends on it. That is why the direct devDependency, not vite, is the carrier.

## 3) Is it a breaking change for absenty's build?

esbuild is pre-1.0, so 0.25 → 0.28 crosses three lines that may each carry
breaking changes. Absenty's surface is unusually small, because it drives
esbuild through one CLI invocation with a long-stable flag set
(`package.json` → `scripts.build`):

```
npx esbuild app/javascript/application.tsx app/javascript/entrypoints/login.tsx \
  --bundle --sourcemap --outdir=app/assets/builds --public-path=/assets \
  --loader:.tsx=tsx --loader:.ts=tsx --jsx=automatic
```

There is no `esbuild.config.js`, no plugin API use, and no programmatic
`build()` call — the plugin API is where esbuild's breaking changes usually
land, and absenty does not touch it. Read the release notes for 0.26/0.27/0.28
anyway and check specifically for: default `target` changes, `--public-path`
semantics, `--jsx=automatic` / JSX runtime resolution, and TS decorator or
`tsconfig` handling changes. Treat any of those as a real risk to the emitted
bundle, not just to the exit code.

**The failure mode to fear is a silently different bundle, not a failed build.**
Verify the output, not the return code (§5).

## 4) Pre-checks

```bash
cd /Users/mu/code/absenty
git checkout development && git pull --ff-only
git status --short                                   # clean tree
grep -n '"esbuild"' package.json                     # expect ^0.25.10

# record the current bundle as the comparison baseline
npm ci && npm run build && npm run build:css
mkdir -p /tmp/absenty-assets-before && cp app/assets/builds/* /tmp/absenty-assets-before/
ls -l /tmp/absenty-assets-before/
```

## 5) Steps

1. On `development`, bump the single devDependency and refresh the lockfile:
   ```bash
   npm install --save-dev esbuild@^0.28.0
   ```
2. Confirm the lockfile actually moved the binary-bearing package:
   ```bash
   python3 -c "
   import json; p=json.load(open('package-lock.json'))['packages']
   print('esbuild        ', p['node_modules/esbuild']['version'])
   print('@esbuild/linux-x64', p.get('node_modules/@esbuild/linux-x64',{}).get('version'))"
   # both must be >= 0.28
   ```
3. Rebuild and diff the emitted assets against the baseline — this is the real
   gate:
   ```bash
   npm run build && npm run build:css
   for f in app/assets/builds/*; do
     b=/tmp/absenty-assets-before/$(basename "$f")
     printf '%-40s before=%-9s after=%-9s\n' "$(basename "$f")" \
       "$(wc -c < "$b" 2>/dev/null || echo -)" "$(wc -c < "$f")"
   done
   ```
   A size swing of a few percent is normal across esbuild lines. A file that
   vanished, went near-zero, or changed by an order of magnitude is a STOP.
4. Run the test suite and the Rails asset path:
   ```bash
   npm test -- --run          # vitest, non-watch
   npm run lint
   bundle exec rails assets:precompile   # RAILS_ENV=test
   ```
5. Commit on `development` and push. `ci.yml` publishes
   `development-<YYYYMMDDHHMMSS>`. Let the dev-lane image build and confirm the
   binary moved in the image itself (a lockfile change is not proof the image
   rebuilt — `docs/sops/self-built-image-rebuild.md`).
6. Smoke the dev environment, then promote to `production` with the repo's
   normal PR flow (`gh pr create -B production -H development`, merge on green),
   exactly as PR #59 did.

## 6) Verification

```bash
# the binary in the published dev image, not just the lockfile
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
mise exec -- trivy image ghcr.io/nachtschatt3n/absenty:development-<NEW_TS> \
  --severity CRITICAL,HIGH --ignore-unfixed

# build date really moved (a tag change is not a rebuild)
mise exec -- trivy image ghcr.io/nachtschatt3n/absenty:development-<NEW_TS> \
  --ignore-unfixed -f json -q | \
  python3 -c "import sys,json;print(json.load(sys.stdin)['Metadata']['ImageConfig']['created'])"

# app still serves its own JS after the bundler change
mise exec -- kubectl get pods -n my-software-development | grep absenty   # Ready, 0 restarts
mise exec -- kubectl -n my-software-development port-forward svc/absenty 18080:80 &
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18080/          # expect 200/302
# then load the login page in a browser and confirm the React bundle mounts —
# a broken bundle returns HTTP 200 and renders nothing.
```

Compare the resulting counts against the finding record, not against this file:
`runbooks/policy-cli.py finding show F-b8fbb7de`.

## 7) Blast radius

**This is a build-time toolchain, so the risk is a broken image, not a runtime
outage.**

- esbuild runs at **image build time**. The published **production** image does
  not ship `node_modules` at all — the compiled esbuild binary is present in the
  dev-lane image and in CI, not in the production runtime. What that implies for
  the driver's exposure, and therefore for how long this can sit in `draft`, is
  recorded on **F-b8fbb7de** — read it there before picking a window.
- A bad bump therefore surfaces as **a build that fails in CI** (loud, safe,
  caught before any tag is published) or — the case that matters — **a build
  that succeeds and emits a subtly different bundle**. Only the second one can
  reach users, and only after a deliberate promotion to `production`.
- Because CI publishes only from a branch push, a broken bundle is contained to
  the `development` lane until someone opens the promotion PR. Do not skip the
  dev-lane soak.
- No database, no migration, no PVC, no shared infrastructure. No other app
  consumes this image.

## 8) Rollback

- **Before promotion:** `git revert` the single commit that changed
  `package.json` + `package-lock.json` on `development`, push, let CI publish a
  replacement dev tag.
- **After promotion:** `git revert` the promotion merge on `production`; CI
  republishes from the reverted tree. The previously-good image
  `production-20260818155406` remains in ghcr and is a known-good rollback
  target — pin the helmrelease tag to it directly for an immediate recovery,
  then sort the source branch out afterwards.
- **Cluster-side:** the tag in
  `kubernetes/apps/my-software-{development,production}/absenty/app/helmrelease.yaml`
  is the only cluster surface. Reverting that commit and letting Flux reconcile
  is the fastest path back.

> **Window pre-check (2026-08-18):** the `absenty-image-updates`
> ImageUpdateAutomation in BOTH `my-software-development` and
> `my-software-production` is currently `Ready=False / GitOperationFailed`
> (`GitRepository/flux-system` is an HTTPS URL with no write credential, so the
> automation cannot push). Until that is fixed, **the helmrelease tag must be
> bumped by hand in this repo** — do not wait for the automation to roll a new
> image during this plan's window.

## 9) Risk & duration

- **risk: low.** Small, reversible, single-dependency change on a build-time
  tool with no plugin-API surface; the production runtime does not carry the
  component. The residual uncertainty is bundle-output drift across three
  pre-1.0 esbuild lines, which §5 step 3 and §6 are designed to catch.
- **est_duration_min: 45.** ~15 min for the bump + local build/test loop,
  ~10 min for the dev-lane CI round trip, ~20 min for the dev soak, promotion
  PR and verification. Fits a 60- or 90-minute slot with rollback headroom.
- Most of the work is **cross-repo and NOT a cluster change** — the bump, the
  build comparison and the test run can be done any time before the window.
  Only the promotion and the tag move need the window.

## 10) Interference surface

- Touches only `absenty` in `my-software-development` and
  `my-software-production`. No shared datastore, no ingress-controller
  involvement, no reboot. Safe to co-schedule with unrelated small plans.
- **Relationship to `harness-frontend-vite7` (scheduled `sat-early:2026-08-29`,
  security_ref F-9f752afd): same root cause, different remedy — they do NOT
  share work.**

  | | harness-frontend-vite7 | absenty-vite-toolchain |
  |---|---|---|
  | root cause | esbuild's vendored Go binary | esbuild's vendored Go binary |
  | blocked by | `vite@6` pins `esbuild ^0.25` | direct devDep pins `esbuild ^0.25` |
  | remedy | **vite 6 → 7** (+ plugin-vue 5→6, vitest 3→4) | **esbuild ^0.25 → ^0.28**, one line |
  | vite state | on 6, must move | already on 7, stays |
  | esbuild role | build tool *and* dev server is the runtime | build-time bundler only |
  | risk | medium — vite dev server IS the serving process | low — production image ships no `node_modules` |
  | repo | `ha-ai-harness` | `absenty` |

  **Recommendation: do NOT co-schedule for efficiency, and do not make either
  depend on the other.** This is encoded as
  `conflicts_with: [harness-frontend-vite7]` in the frontmatter, because the
  window agent reads the field and not this prose. There is no shared artifact, namespace, image or
  lockfile — the only thing in common is the lesson, which is already learned.
  Co-scheduling would put two bundler-toolchain changes with different failure
  signatures in one window and make a regression harder to attribute.

  If window capacity forces a pairing, **sequence harness first**: it is the
  higher-risk of the two (its change lands on a live serving process, this one
  cannot take production down), so it should get the window's rollback headroom
  while it is still uncommitted. This plan is a good filler for a later,
  smaller slot.
- One genuine ordering note: if a routine dependency-refresh batch for absenty
  is queued for the same window, land **this** plan first. A lockfile refresh
  run afterwards will simply keep `esbuild ^0.28`; run in the other order and
  the refresh regenerates a lockfile this plan then has to re-resolve.
