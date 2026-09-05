---
plan_id: mcpo-python-3.14
component: mcpo
pr: null                              # no open Renovate PR found; drift held by the
                                       # blanket `*mcpo*` deny rule in
                                       # runbooks/auto-update-policy.yaml (line 86-87)
kind: image
current: "3.11-slim"
target: "3.14.7-slim"
update_type: major
risk: medium
est_duration_min: 20
needs_reboot: false
touches:
  namespaces: [ai]
  resources: [helmrelease/mcpo, initcontainer/runtime-setup]
  shared: []                          # ClusterIP-only, ingress disabled, no PVC,
                                       # no shared DB/cache. Co-resident `ai`
                                       # namespace app (openclaw) does NOT
                                       # reference mcpo anywhere in its manifests
                                       # (verified — see Interference notes).
depends_on: []
conflicts_with: []
security_ref: null
capability_change: false              # base-image bump only; mcpo's own image
                                       # (ghcr.io/open-webui/mcpo:git-44ce6d0) and
                                       # its config.json are untouched
rollback_class: git-revert
finding_refs: []
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
generated: "2026-09-05"
---

## 1. Summary & why held

`kubernetes/apps/ai/mcpo/app/helmrelease.yaml` pins the `runtime-setup`
**initContainer** to `python:3.11-slim`. Renovate/version-check flagged
`3.14.7-slim` as the current tag, and the update is HELD by a blanket policy
rule, not a scan of the actual diff:

```yaml
# runbooks/auto-update-policy.yaml:86-87
  - match: "*mcpo*"
    reason: "python init base image major (3.11→3.14) rides these tags."
```

That rule fires on every `mcpo` dependency regardless of which one moved —
it exists because a 3-minor-version Python jump (3.11→3.12→3.13→3.14) is not
provably safe to auto-merge, full stop.

**What this bump actually touches, established by reading the manifest (not
assumed):** `python:3.11-slim` is used **only** as the image for the
`runtime-setup` initContainer (`spec.values.controllers.mcpo.initContainers.runtime-setup`).
That initContainer does not run any of mcpo's own code. Its entire job is to
populate a shared `emptyDir` (`/shared`) that the app container later reads
from `$PATH`:

1. `apt-get install curl ca-certificates gnupg`, add the NodeSource repo, `apt-get install nodejs` (Node 20.x, pinned separately from Python).
2. `pip install --upgrade pip && pip install uv` — installs `uv`/`uvx` as **Rust binaries**, then copies `/usr/local/bin/{uv,uvx}` and `/usr/bin/node` into `/shared/bin`.
3. `npm install -g` three MCP server packages (`@upstash/context7-mcp`, `prometheus-mcp`, `@modelcontextprotocol/server-github`) into `/shared/lib/node_modules`.

The **app container** is a completely separate image,
`ghcr.io/open-webui/mcpo:git-44ce6d0`, unaffected by this bump — its own
Python runtime, if any, is baked into that image and is not in scope here.

**Does mcpo/its deps support 3.14?** Two separate questions, both checked:

- **mcpo itself** (`open-webui/mcpo`, `pyproject.toml`): `requires-python = ">=3.11"` — no upper bound, so 3.14 is not excluded. Moot anyway per above: mcpo's own image is untouched by this plan.
- **What actually runs under the initContainer's Python interpreter** is just `pip` and `uv`. Verified on PyPI:
  - `pip` 26.2.1, `requires_python: >=3.10` — supports 3.14.
  - `uv` 0.12.10 ships wheels tagged `py3-none-*` (e.g. `uv-0.12.10-py3-none-manylinux_2_17_x86_64...whl`) — it's a Rust binary with **no CPython ABI dependency**, so it installs and runs identically under any CPython 3.x. Once copied to `/shared/bin/uv`, `uvx`-launched MCP servers (`alertmanager-mcp-server`, `mcp-kubernetes-server` in `config.json`) are executed by **uv's own managed Python runtime** (python-build-standalone), not the initContainer's system interpreter — so the removed-stdlib-module risk that usually makes a 3.11→3.14 jump scary does not apply here. No Python application code in this repo's control actually executes "as" 3.14.

**The real, previously-undocumented risk this investigation surfaced:**
`python:3.14.7-slim` is **not** what it looks like next to `3.11-slim` — Docker
Hub confirms the digest of plain `3.14.7-slim` is byte-identical to
`3.14.7-slim-trixie` (Debian 13), whereas `3.11-slim` on this manifest predates
Debian's switch and effectively tracks Bookworm-era defaults
(`3.14.7-slim-bookworm` is a **different**, available digest). So this bump is
actually two changes riding one tag: a Python major **and** a silent Debian
Bookworm→Trixie base-OS swap. The apt-based steps (steps 1 above: package
names, NodeSource's GPG/repo flow) are the part that could break on Trixie —
not the Python version itself. That is the thing to actually watch during
rollout, not stdlib deprecations.

**Verdict:** the "major Python bump" framing overstates the risk for *this*
specific tag reference — it's a bootstrap-only initContainer, and both tools
that run under it (pip, uv) are confirmed 3.14-compatible. The genuine
open question is the Bookworm→Trixie base-OS change bundled into the tag,
which is untested here. `risk: medium` reflects that residual unknown, not
a Python-compatibility concern.

**Target tag verified to exist** (Docker Hub API, 2026-09-05):
```
name: 3.14.7-slim
last_updated: 2026-09-01T23:08:54Z
digest: sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6
arch present: amd64, arm64, ppc64le, s390x, 386, arm, riscv64  (amd64 covers the nuc14 nodes)
```

## 2. Pre-checks

```bash
# 1) HelmRelease currently healthy before touching anything
kubectl get helmrelease -n ai mcpo -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'

# 2) Capture baseline pod/initContainer imageIDs (for the rollback-verification diff later)
kubectl get pod -n ai -l app.kubernetes.io/name=mcpo -o jsonpath='{range .items[0].status.initContainerStatuses[*]}{.name}{"="}{.imageID}{"\n"}{end}'
kubectl get pod -n ai -l app.kubernetes.io/name=mcpo -o jsonpath='{range .items[0].status.containerStatuses[*]}{.name}{"="}{.imageID}{"\n"}{end}'

# 3) Baseline: confirm what the initContainer currently installs into /shared (contents, not just "it ran")
POD=$(kubectl get pod -n ai -l app.kubernetes.io/name=mcpo -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n ai "$POD" -c app -- /shared/bin/node --version
kubectl exec -n ai "$POD" -c app -- /shared/bin/uv --version
kubectl exec -n ai "$POD" -c app -- /shared/bin/npm ls -g --depth 0 --prefix /shared

# 4) Confirm the working tree is clean on this one file before editing (shared-worktree hygiene)
git -C /Users/mu/code/cberg-home-nextgen status --short kubernetes/apps/ai/mcpo/app/helmrelease.yaml
```

No alert silence / update-marker needed for Step 1 of `application-update.md`
— this is not an attended-migration-class change (no startup migration, no
immutable selectors, no DB), but DO watch the rollout live per Step 4 since a
failed initContainer means mcpo never becomes Ready at all (see §6).

## 3. Steps

1. Edit the initContainer tag:
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' 's/tag: 3\.11-slim/tag: 3.14.7-slim/' kubernetes/apps/ai/mcpo/app/helmrelease.yaml
   git diff kubernetes/apps/ai/mcpo/app/helmrelease.yaml   # confirm exactly one line changed, in initContainers.runtime-setup only
   ```

2. Commit and push (path-scoped, per shared-worktree convention):
   ```bash
   git commit --only kubernetes/apps/ai/mcpo/app/helmrelease.yaml -m "$(cat <<'EOF'
   feat(mcpo): bump runtime-setup initContainer python 3.11-slim -> 3.14.7-slim

   Bootstrap-only initContainer (installs node/npm/uv into a shared emptyDir);
   does not affect mcpo's own runtime image. Verified pip/uv both support
   3.14; residual risk is the bundled Bookworm->Trixie base-OS switch in the
   plain `slim` tag, not the Python version itself. See
   runbooks/maintenance/plans/mcpo-python-3.14.md.

   Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
   EOF
   )"
   git push
   ```

3. Let Flux reconcile (`ks.yaml` interval 30m). To not wait a full cycle:
   ```bash
   flux reconcile kustomization mcpo -n ai --with-source
   flux reconcile helmrelease mcpo -n ai
   ```

4. Watch the rollout — the initContainer is the part that can fail:
   ```bash
   kubectl get pods -n ai -l app.kubernetes.io/name=mcpo -w
   # once a new pod appears:
   NEWPOD=$(kubectl get pod -n ai -l app.kubernetes.io/name=mcpo -o jsonpath='{.items[0].metadata.name}')
   kubectl logs -n ai "$NEWPOD" -c runtime-setup -f
   ```
   Watch specifically for the `apt-get update` / NodeSource GPG+repo steps —
   that is where a Bookworm→Trixie package-name or repo mismatch would surface,
   not in the `pip install uv` step.

## 4. Verification

```bash
NEWPOD=$(kubectl get pod -n ai -l app.kubernetes.io/name=mcpo -o jsonpath='{.items[0].metadata.name}')

# Shape: pod Ready, HelmRelease Ready (floor, not the whole check)
kubectl get pod -n ai "$NEWPOD"
kubectl get helmrelease -n ai mcpo -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'

# CONTENTS ASSERTION 1 — the initContainer's actual output exists and is non-empty,
# not just "exited 0" (proves apt/npm/pip genuinely completed under 3.14.7-slim):
kubectl exec -n ai "$NEWPOD" -c app -- /shared/bin/node --version
kubectl exec -n ai "$NEWPOD" -c app -- /shared/bin/uv --version
kubectl exec -n ai "$NEWPOD" -c app -- /shared/bin/npm ls -g --depth 0 --prefix /shared
# compare package list against the pre-check baseline (§2.3) — must match
# (context7-mcp, prometheus-mcp, @modelcontextprotocol/server-github all present)

# CONTENTS ASSERTION 2 — blast-radius proof: only the initContainer image
# changed, the app container's image did not:
kubectl get pod -n ai "$NEWPOD" -o jsonpath='{range .status.initContainerStatuses[*]}{.name}={.imageID}{"\n"}{end}'
kubectl get pod -n ai "$NEWPOD" -o jsonpath='{range .status.containerStatuses[*]}{.name}={.imageID}{"\n"}{end}'
# initContainer imageID must now reference python:3.14.7-slim's digest
# (sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6);
# app container imageID must be UNCHANGED from the §2.2 baseline.

# CONTENTS ASSERTION 3 — mcpo actually SERVES a real request post-startup,
# not just "container Running" (a python import error inside mcpo's own
# process, or an uvx-launched MCP server that fails on first invocation,
# happens AFTER the startup probe passes):
kubectl port-forward -n ai svc/mcpo 8000:8000 &
PF_PID=$!
API_KEY=$(kubectl -n ai get secret mcpo-api-key -o jsonpath='{.data.api-key}' | base64 -d)

# 3a) openapi.json lists all 5 configured MCP tool proxies by name — proves
# every server in config.json actually mounted, not just that / responds:
curl -s -H "Authorization: Bearer $API_KEY" http://localhost:8000/openapi.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
paths = list(d.get('paths', {}).keys())
expected = ['context7', 'prometheus', 'alertmanager', 'kubernetes', 'github']
missing = [e for e in expected if not any(e in p for p in paths)]
assert not missing, f'missing MCP tool namespaces in openapi.json: {missing}'
print(f'OK: all 5 tool namespaces present, {len(paths)} total paths')
"

# 3b) one REAL tool call end-to-end through the proxy (prometheus needs no
# external credential, so it's the cleanest smoke test): a trivial PromQL
# query that must return actual data, not an empty/error body:
curl -s -X POST -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  http://localhost:8000/prometheus/prometheus_query \
  -d '{"query":"up"}' | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d)
# adjust the key path to whatever prometheus-mcp actually returns, but the
# assertion must be: non-empty result list, not just HTTP 200
"
kill $PF_PID
```

If 3a or 3b fails while the pod shows `Running`/`Ready`, that is exactly the
"python import error after startup" failure mode this update was held for —
treat it as a verification FAILURE and roll back (§5), do not treat green
probes as sufficient.

## 5. Rollback

`maxHistory: 1` on this HelmRelease means `helm rollback` cannot reach the
pre-upgrade revision — revert in git, per `docs/sops/application-update.md` §7:

```bash
cd /Users/mu/code/cberg-home-nextgen
git log --oneline -- kubernetes/apps/ai/mcpo/app/helmrelease.yaml | head -5
git revert --no-edit <the-bump-commit-sha>
git push
flux reconcile kustomization mcpo -n ai --with-source
flux reconcile helmrelease mcpo -n ai
```

Confirm the rollback landed (new pod, fresh initContainer run under the old
image — the emptyDir is wiped on pod recreation so this re-runs the full
apt/pip/npm sequence under `python:3.11-slim`):

```bash
NEWPOD=$(kubectl get pod -n ai -l app.kubernetes.io/name=mcpo -o jsonpath='{.items[0].metadata.name}')
kubectl get pod -n ai "$NEWPOD" -o jsonpath='{.status.initContainerStatuses[0].imageID}{"\n"}'
# must reference python:3.11-slim's digest again
# then re-run Verification §4 assertions 1 and 3 against the rolled-back pod
```

## 6. Interference notes

- **Namespace `ai` is shared with `openclaw`**, but `openclaw`'s own MCP
  server registrations (`kubernetes/apps/ai/openclaw/app/mcporter-config.yaml`
  — nextcloud, browser, homeassistant) do **not** reference `mcpo` or its
  ClusterIP service anywhere. No manifest in this repo wires anything to
  `mcpo`'s service (`ingress.main.enabled: false`, ClusterIP only) — the
  consumer of its 5 MCP-to-OpenAPI proxies (context7/prometheus/alertmanager/
  kubernetes/github) is external to this repo (a manual client or an
  out-of-band agent config). **The window agent should confirm nothing is
  mid-use of mcpo before starting** — there's no in-repo way to check this,
  so treat "consumer unknown" as the actual interference risk, not a
  namespace collision.
- **Full-outage window, not partial**: because the app container's readiness
  depends on the `runtime-setup` initContainer completing, mcpo is
  **completely unavailable** (all 5 tool proxies) from pod termination until
  the new initContainer finishes (apt-get + node install + 3× npm install —
  historically a couple of minutes, network-dependent). This is not a
  rolling/zero-downtime bump.
- **No shared infra perturbed**: no ingress, no cert-manager, no shared DB,
  no Longhorn PVC (`runtime-tools` is `emptyDir`, `config` is a ConfigMap
  mount) — safe to run in any window, unattended-eligible from an infra
  standpoint, but `risk: medium` (untested Bookworm→Trixie apt behavior)
  argues for watching the rollout live rather than trusting Step 0's
  auto-apply gate, hence this went through the plan lane rather than direct-bump.
- **If Trixie's NodeSource/apt flow breaks**, the fix is likely to pin the
  `-bookworm` suffix explicitly (`3.14.7-slim-bookworm`) instead of reverting
  the Python version at all — worth trying as a forward-fix before a full
  git-revert, since it isolates the actual variable that broke.
