---
plan_id: harness-frontend-vite7
component: ha-ai-harness
pr: null                              # self-owned image; no upstream PR
kind: image
current: "harness-home-frontend 0.5.3-alpha (vite 6 toolchain)"
target: "vite 7 toolchain (esbuild >= 0.27)"
update_type: major
risk: medium
est_duration_min: 60
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/ha-ai-harness
    - "ghcr.io/nachtschatt3n/harness-home-frontend"
  shared: []
depends_on: []
conflicts_with: []
status: scheduled
window: "sun-window:2026-08-30"
# Scheduled 2026-08-15. 60m in a 90m slot. Not a tue/thu 60m slot: 60-of-60
# leaves zero rollback time.
auto_execute: false                   # toolchain major bump on the serving process
security_ref: F-9f752afd              # security driver; detail is DB-only
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-15"
---

# harness-home-frontend: vite 6 -> 7 to clear a residual build-toolchain CVE

## 1) Summary & why held

The `harness-home-rebuild` plan (executed 2026-08-15, commit fb821821) cleared
most of the frontend's fixable criticals. One survivor needs a framework major.

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-9f752afd**. The advisory ID, the affected binary, the
> before/after counts and the exploitability assessment live on the finding
> record, not here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-9f752afd`
> - CLI: `runbooks/policy-cli.py finding show F-9f752afd`
>
> Convention: `docs/sops/vulnerability-disclosure.md`.

**Why a vite major is the only path** (this part is a plain dependency-resolution
fact and is safe to state): the vulnerable component is a Go binary vendored into
esbuild, so the fix is an esbuild version, not a patch. `vite@6` declares
`esbuild: ^0.25.0`, so npm cannot resolve anything ≥0.27 while we stay on vite 6
— the newest 0.25 release is a dead end. `vite@7` declares
`esbuild: ^0.27.0 || ^0.28.0`. The exact fixed esbuild version to target is on
the finding record.

**Why this is a major, not a bump:** the container's `CMD` is
`npm run dev` — the **vite dev server is the serving process**, not a build-time
tool. So a vite major lands directly on the runtime. It also drags:

- `@vitejs/plugin-vue` ^5 -> ^6 (v5 peer-deps cap at vite ^6)
- `vitest` 3.2.x -> 4.x likely (vite 7 peer range)
- vite 7 needs node ^20.19.0 || >=22.12.0 — satisfied by `node:22-alpine`

Note also `vite.config.ts` carries a Vite-6-specific fix (commit 68a74d9,
"use boolean true for allowedHosts in Vite 6") — re-verify `allowedHosts: true`
under vite 7, it is the setting that lets the ingress hostname reach the dev
server at all.

Severity context for scheduling is recorded on **F-9f752afd** — read it there
before picking a window. Short version for sequencing only: this is not an
emergency, so do it properly rather than rushing.

## 2) Pre-checks

```bash
cd /Users/mu/code/ha-ai-harrnes
git status --short                      # clean tree
grep -n '"vite"\|"vitest"\|plugin-vue' frontend/package.json

# current published state
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
mise exec -- trivy image ghcr.io/nachtschatt3n/harness-home-frontend:0.5.3-alpha \
  --severity CRITICAL --ignore-unfixed
```

## 3) Steps

1. In `/Users/mu/code/ha-ai-harrnes/frontend`, bump the toolchain together:
   `vite@^7`, `@vitejs/plugin-vue@^6`, and `vitest` to whatever vite 7's peer
   range requires; refresh `package-lock.json`.
2. Confirm the lockfile actually moved esbuild:
   `python3 -c "import json;d=json.load(open('package-lock.json'));print(d['packages']['node_modules/esbuild']['version'])"`
   — must be >= 0.27.
3. Smoke test locally **before** tagging (this is the serving process):
   ```bash
   npm ci
   VITE_ALLOWED_HOSTS=all ./node_modules/.bin/vite --host 0.0.0.0 --port 5199 &
   curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5199/     # expect 200
   ```
4. Commit, tag `v0.5.4-alpha`, push. CI (`.github/workflows/build.yml`) builds
   and pushes both images on `v*` tags. **Push over HTTPS with the gh token —
   SSH to github.com:22 times out from this host.**
5. Update BOTH tags in
   `kubernetes/apps/home-automation/ha-ai-harness/app/helmrelease.yaml`, commit,
   push, let Flux reconcile.

## 4) Verification

```bash
export TRIVY_USERNAME=nachtschatt3n TRIVY_PASSWORD="$(gh auth token)"
mise exec -- trivy image ghcr.io/nachtschatt3n/harness-home-frontend:0.5.4-alpha \
  --severity CRITICAL --ignore-unfixed          # expect 0

# build date really moved (a tag change is not a rebuild)
mise exec -- trivy image ghcr.io/nachtschatt3n/harness-home-frontend:0.5.4-alpha \
  --severity CRITICAL --ignore-unfixed -f json | \
  python3 -c "import sys,json;print(json.load(sys.stdin)['Metadata']['ImageConfig']['created'])"

mise exec -- kubectl get pods -n home-automation | grep harness   # Ready, 0 restarts
mise exec -- kubectl logs -n home-automation deploy/ha-ai-harness-frontend --tail=10
# ^ must show "VITE v7.x ready" and no allowedHosts/host-check error

# UI actually reachable through the ingress hostname, not just the pod
mise exec -- kubectl -n home-automation port-forward svc/ha-ai-harness-frontend 15173:5173 &
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:15173/    # expect 200
curl -s http://127.0.0.1:15173/health                               # proxied to server
```

## 5) Rollback

`git revert` the helmrelease commit and reconcile — `0.5.3-alpha` stays in ghcr
and is a known-good image. The source-repo tag needs no rollback; an unused tag
is harmless.

## 6) Interference notes

- Single app in `home-automation`, no shared datastore, no ingress-controller
  involvement. Safe to co-schedule with unrelated small plans.
- The vite/plugin-vue/vitest bump is cross-repo work and is NOT a cluster change
  — do it any time before the window. Only the tag move needs the window.
- Highest-risk failure mode is the dev server refusing the ingress Host header
  (`allowedHosts`), which presents as an HTTP 403 from a **Running, Ready** pod.
  Do not trust pod readiness alone — curl it.
