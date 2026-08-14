---
plan_id: harness-frontend-vite7
component: ha-ai-harness
pr: null                              # self-owned image; no upstream PR
kind: image
current: "harness-home-frontend 0.5.3-alpha — 1 fixable CRITICAL (esbuild Go stdlib)"
target: "vite 7 toolchain, esbuild >= 0.27 — 0 fixable CRITICAL"
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
status: draft
window: null
auto_execute: false                   # toolchain major bump on the serving process
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-15"
---

# harness-home-frontend: vite 6 -> 7 to clear the esbuild Go-stdlib CRITICAL

## 1) Summary & why held

The `harness-home-rebuild` plan (executed 2026-08-15, commit fb821821) took the
frontend from **5 fixable CRITICAL to 1**. The survivor is:

```
CVE-2025-68121  stdlib v1.23.12 -> 1.24.13, 1.25.7, 1.26.0-rc.3
                app/node_modules/@esbuild/linux-x64/bin/esbuild
```

This is the **Go standard library compiled into the esbuild binary**, so the fix
is an esbuild version, not a patch we can apply:

| esbuild | Go stdlib | verdict |
|---|---|---|
| 0.25.12 | go1.23.12 | vulnerable — and the newest of the 0.25 line |
| 0.27.3  | go1.25.7  | fixed |
| 0.28.2  | go1.26.5  | fixed |

`vite@6` declares `esbuild: ^0.25.0`, so npm cannot resolve anything ≥0.27 while
we stay on vite 6 — 0.25.12 is a dead end. `vite@7` declares
`esbuild: ^0.27.0 || ^0.28.0`.

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

Severity context for scheduling: this is a build-tool binary reached only via
vite's dep pre-bundling, not a network-facing surface — real-world exploitability
is low. It is worth doing properly rather than rushing.

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
