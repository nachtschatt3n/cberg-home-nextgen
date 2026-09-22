# SOP: Runtime Dependency Pinning

> Description: Containers that resolve their dependencies at POD START from an unpinned upstream — `uvx`, `npx`, `pip install`, `npm install -g`, `cargo install`, `curl | sh`. An upstream major release breaks them with no image change, no Renovate PR, and no CrashLoopBackOff: the process starts, serves HTTP 200, and exposes zero functionality.
> Version: `2026.09.22`
> Last Updated: `2026-09-22`
> Owner: `doc-agent`

---

## ⚠️ This is NOT [`container-dependencies.md`](container-dependencies.md)

The two SOPs share the word "dependency" and nothing else. **Do not merge them.**

| | [`container-dependencies.md`](container-dependencies.md) | **This SOP** |
|---|---|---|
| Topic | *Wait-for* initContainers | *Package resolution* at pod start |
| Dependency means | A running **service** (Postgres, Redis) | A third-party **software package** |
| Mechanism | `initContainers.wait-for-<dep>` running `nc -z <host> <port>` in a loop | `uvx` / `npx` / `pip install` fetching from PyPI/npm/crates.io |
| Failure it prevents | `CrashLoopBackOff` on cold start, because the DB was not up yet | Silent loss of functionality, because upstream shipped a breaking major |
| Failure shape | **Loud** — pod stuck in `Init:0/1`, `KubePodNotReady` fires | **Silent** — pod `1/1 Running`, HTTP 200, zero features |
| Fix | Add a TCP gate before the app starts | Pin a version bound at the invocation, or pre-install into the image |

A wait-for initContainer does not protect against an unpinned package, and
pinning a package does nothing for a cold-start race. They are orthogonal.

---

## 1) Description

Most of this cluster's version surface is tracked: a container image has a tag,
Renovate watches it, `runbooks/check-all-versions.py` audits it, and an upgrade
gets a PR and a maintenance-window plan. **A dependency resolved at pod start
has none of that.** It appears in no image tag and in no lockfile, so it is
invisible to every version-tracking mechanism this repo owns — and it changes
underneath you whenever upstream publishes, which is to say on someone else's
schedule, with no signal on our side.

The failure is not a crash. The wrapper process starts, binds its port, answers
health checks, and serves an **empty** feature surface. Every ordinary readiness
signal passes. That is the whole problem, and it is why this SOP is a detection
rule rather than a checklist item.

- Scope: any container in `kubernetes/apps/**` whose command or initContainer
  fetches and installs software at pod start.
- Prerequisites: repo-pinned tooling via `mise exec --`, cluster read access.
- Out of scope: wait-for initContainers (above); base-image tag pinning
  (ordinary Renovate territory); our own `ghcr.io/nachtschatt3n/**` images,
  which are built by us and rebuilt on our schedule
  ([`self-built-image-rebuild.md`](self-built-image-rebuild.md)).

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Worked example | `mcpo` — namespace `ai` |
| Source of truth | `kubernetes/apps/ai/mcpo/app/configmap.yaml` (+ `helmrelease.yaml`) |
| Failure mode | HTTP `200` with an empty feature surface |
| Detection rule | Assert **contents**, never shape — count tools/endpoints, never trust the status code |
| Remedy | Pin a bound at the invocation, or pre-install into the image |
| Version-tracking coverage | **None** — invisible to Renovate and `check-all-versions.py` (§7) |
| Related findings | `security_ref: F-cfa520f4` (this SOP gap), `F-8fb293e4` (the live mcpo instance) |

### The worked example, measured `[verified 2026-09-22]`

`mcpo` proxies MCP servers to OpenAPI for open-webui. Its ConfigMap registers
**five** servers. Three are `node` commands pointing at **absolute paths** that
an initContainer pre-installed into a shared volume. Two invoke **`uvx` with no
version bound**:

```json
"alertmanager": { "command": "uvx", "args": ["alertmanager-mcp-server"] },
"kubernetes":   { "command": "uvx", "args": ["mcp-kubernetes-server",
                                             "--disable-write", "--disable-delete"] }
```

Tool counts from each server's `openapi.json`, measured through a port-forward:

| MCP server | Invocation | HTTP | Tools exposed |
|---|---|---|---|
| `context7` | `node` + absolute path | `200` | **2** |
| `prometheus` | `node` + absolute path | `200` | **10** |
| `github` | `node` + absolute path | `200` | **26** |
| `alertmanager` | **`uvx`, unpinned** | `200` | **0** |
| `kubernetes` | **`uvx`, unpinned** | `200` | **0** |

The pod is `1/1 Running` with **0 restarts** and an uptime of days. Nothing
alerted. Two of five integrations have been dead the entire time.

### Root cause `[verified 2026-09-22, from the pod's own logs]`

Upstream published `mcp` 2.x, in which `FastMCP` was renamed to `MCPServer`.
Both packages pin no upper bound, so `uvx` resolved the new major at pod start:

```
alertmanager-mcp-server:
  ModuleNotFoundError: No module named 'mcp.server.fastmcp'.
  This is mcp 2.x, where FastMCP was renamed to MCPServer … or pin 'mcp<2'
  to keep running v1 code.

mcp-kubernetes-server:
  AttributeError: 'FastMCP' object has no attribute 'settings'
```

mcpo logs the failures at startup and then **serves anyway**:

```
ERROR - Failed to connect to MCP server 'alertmanager': …
ERROR - Failed to connect to MCP server 'kubernetes': …
WARNING - Failed to connect to:
WARNING -   - alertmanager
WARNING -   - kubernetes
INFO:  … "GET /alertmanager/openapi.json HTTP/1.1" 200 OK
INFO:  … "GET /kubernetes/openapi.json HTTP/1.1" 200 OK
```

Note the shape: **three startup-time ERROR lines, then a permanent 200.** Once
the startup window scrolls out of the log buffer, the only remaining evidence is
an empty `paths` object that nothing was checking.

---

## 3) Blueprints

### The unsafe pattern

```json
{ "command": "uvx", "args": ["some-mcp-server"] }
```

```yaml
command: [sh, -c, "npx -y @vendor/tool@latest --serve"]   # @latest is worst-case
command: [sh, -c, "pip install some-tool && some-tool"]
```

### Remedy A — pin a bound at the invocation (minimal change)

`uvx --with` injects a constraint into the ephemeral environment:

```json
"alertmanager": {
  "command": "uvx",
  "args": ["--with", "mcp<2", "alertmanager-mcp-server"]
},
"kubernetes": {
  "command": "uvx",
  "args": ["--with", "mcp<2", "mcp-kubernetes-server",
           "--disable-write", "--disable-delete"]
}
```

Equivalents: `uvx package==1.2.3`, `npx @vendor/tool@1.2.3` (**never**
`@latest`), `pip install 'tool==1.2.3'`, `cargo install tool@1.2.3`.

Prefer an **exact pin** where the package is the thing you care about, and a
**major bound** (`mcp<2`) where you are constraining a transitive runtime that
must merely stay on a compatible line.

> A bound is a **backstop, not a fix**. It stops the silent break, but the
> package still resolves from upstream at every pod start — an upstream yank or
> a registry outage still breaks the pod, and the pin still needs review at the
> major boundary. Remedy B is strictly stronger.

### Remedy B — pre-install into the image or a shared volume (preferred)

This is what the three **healthy** mcpo servers already do: an initContainer
installs the packages once, and the ConfigMap invokes an **absolute path**, so
pod start resolves nothing from the internet:

```json
"prometheus": {
  "command": "node",
  "args": ["/shared/lib/node_modules/prometheus-mcp/dist/index.mjs", "stdio"]
}
```

The healthy/unhealthy split in that one ConfigMap is the argument for this SOP:
**every server invoked by absolute path works; every server resolved at start
time is dead.**

### In-repo counterexample worth copying

`kubernetes/apps/ai/paperclip/app/helmrelease.yaml` pins its build:

```bash
cargo install unifictl@5.3.1 --root /paperclip/.local     # ✅ exact pin
```

…while, in the same block, bootstrapping the toolchain unpinned:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y …   # ⚠️ unpinned
```

Both shapes live side by side. The pinned one is the pattern to follow.

---

## 4) Operational Instructions

### Adding a component that resolves dependencies at runtime

1. **Prefer not to.** Pre-install into the image or a shared volume (Remedy B).
2. If runtime resolution is unavoidable, **pin at the invocation** (Remedy A) in
   the same commit that introduces it. An unpinned invocation must never be the
   thing that ships.
3. **Add a contents assertion** to that app's verification — a count of tools,
   endpoints, or registered plugins. A status-code check is not verification.
4. Record the pin's rationale in a comment at the invocation: what it bounds and
   what would justify raising it.

### Changing an existing pin

Treat it as an ordinary dependency upgrade: it is a behaviour change with no
image tag to review. Verify with §6 **before and after**, comparing the counts.

```bash
git commit --only kubernetes/apps/ai/mcpo/app/configmap.yaml -F msg.txt
git show --stat HEAD     # shared worktree: confirm no foreign hunk rode along
git push
```

Flux reconciles and the pod rolls. Because the ConfigMap is mounted (and mcpo
runs with `--hot-reload`), confirm the change actually took effect at the
**process** level via §6, not just that the ConfigMap changed.

---

## 5) Examples

### Example A: pin the two mcpo `uvx` servers

Apply the Remedy A snippet from §3 to
`kubernetes/apps/ai/mcpo/app/configmap.yaml`. Expected result: `alertmanager`
and `kubernetes` move from **0** tools to non-zero, while the three controls
(`context7`=2, `prometheus`=10, `github`=26) are unchanged.

Rollback is a single-file `git revert`; both namespaces are already at 0 tools,
so a failed pin cannot regress anything. (Operator approval required — this is a
state change. See `F-8fb293e4`.)

### Example B: audit the class across the repo

```bash
grep -rnE "uvx |npx |pip install|pip3 install|npm install -g|cargo install|curl .*\| *(ba)?sh" \
  kubernetes/ --include="*.yaml" | grep -v "ENC\["
```

Known members of the class in this repo `[verified 2026-09-22]`:

| Location | Pattern | Pinned? |
|---|---|---|
| `apps/ai/mcpo/app/configmap.yaml` | `uvx` ×2 | ❌ **no** — the live failure |
| `apps/ai/mcpo/app/helmrelease.yaml` | initContainer: `apt-get`, NodeSource `node_20.x`, `npm install -g` ×3 | ⚠️ partial — base image pinned, packages not |
| `apps/ai/openclaw/app/mcporter-config.yaml` | `npx -y @playwright/mcp@latest` | ❌ **no** — explicit `@latest` |
| `apps/ai/openclaw/app/helmrelease.yaml` | `npm install -g`, `pip install` (~52 CLIs every pod start) | ❌ **no** |
| `apps/ai/paperclip/app/helmrelease.yaml` | `cargo install unifictl@5.3.1` | ✅ **yes** |
| `apps/ai/paperclip/app/helmrelease.yaml` | `curl https://sh.rustup.rs \| sh` | ❌ no |
| `apps/databases/superset/app/helmrelease.yaml` | `uv pip install` into the runtime venv | review |
| `apps/storage/longhorn/bench/loopback-daemonset.yaml` | `apk add --no-cache util-linux` | ❌ no (bench only) |

Note that `mcpo`'s initContainer pins its **base image** (`python:3.14.7-slim`)
while installing unpinned packages on top. A pinned base image is not a pinned
environment, and it makes the manifest read as more reproducible than it is.

---

## 6) Verification Tests

### Test 1: count the exposed surface — never the status code

```bash
K=$(mise exec -- kubectl -n ai get secret mcpo-api-key -o jsonpath='{.data.api-key}' | base64 -d)
mise exec -- kubectl -n ai port-forward svc/mcpo 33002:8000 >/dev/null 2>&1 &
PF=$!; python3 -c "import time; time.sleep(4)"
for s in context7 prometheus alertmanager kubernetes github; do
  code=$(curl -s -o /tmp/oa.json -w '%{http_code}' -H "Authorization: Bearer $K" \
           "http://127.0.0.1:33002/$s/openapi.json")
  n=$(python3 -c '
import json
try:    print(len(json.load(open("/tmp/oa.json")).get("paths", {})))
except Exception: print("n/a")')
  echo "$s  http=$code  tools=$n"
done
kill $PF; rm -f /tmp/oa.json
```

Expected:
- **Every** server reports `tools` > 0.
- Baseline `[verified 2026-09-22]`: `context7=2`, `prometheus=10`, `github=26`
  (healthy controls) and `alertmanager=0`, `kubernetes=0` (**currently
  failing**).

If failed:
- `http=200 tools=0` is the signature of this SOP. Go to §8 Example 1.
- The three healthy servers are the **negative control**: if they also read 0,
  your measurement is broken, not the servers.

### Test 2: no startup resolution failures in the logs

```bash
mise exec -- kubectl -n ai logs deploy/mcpo -c app --tail=400 \
  | grep -E "Failed to (connect|establish)|ModuleNotFoundError|AttributeError|ImportError"
```

Expected:
- No output.

If failed:
- The traceback names the breaking package and usually the required bound —
  upstream's own message told us to pin `mcp<2`. Read it before guessing.

### Test 3: the pin actually reached the process

A ConfigMap change is not proof the running process picked it up.

```bash
mise exec -- kubectl -n ai get cm mcpo-config -o jsonpath='{.data.config\.json}' | grep -A2 '"uvx"'
mise exec -- kubectl -n ai get pods -l app.kubernetes.io/name=mcpo \
  -o custom-columns=NAME:.metadata.name,AGE:.metadata.creationTimestamp,RESTARTS:.status.containerStatuses[0].restartCount
```

Expected:
- The pin is present in the ConfigMap **and** the pod was created after the
  change (or `--hot-reload` picked it up, proven by Test 1 counts moving).

If failed:
- Restart the deployment and re-run Test 1.

### Test 4: known-bad negative control

An existence check is evidence only if a known-bad input fails. Before trusting
Test 1, confirm a nonsense server name does **not** return a healthy-looking
answer:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $K" \
  "http://127.0.0.1:33002/definitely-not-a-server/openapi.json"
```

Expected:
- A `4xx`. If this also returns `200`, your measurement path is intercepting and
  **all of Test 1 is invalid**. See
  [`verification-contents-not-shape.md`](verification-contents-not-shape.md) §2b.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---|---|---|
| Endpoint returns `200`, feature surface empty | Unpinned runtime dep resolved a breaking upstream major | §6 Test 1, then pin (§3 Remedy A) |
| Worked for months, broke with no deploy | Upstream published; nothing on our side changed | Check the upstream release date against pod start time |
| No Renovate PR for the broken package | The package is in no image tag and no lockfile — structurally invisible | §7 below; this is expected, not a Renovate bug |
| Pod `1/1 Running`, 0 restarts, still broken | The wrapper survives a failed child; no crash to detect | Never treat Running/200 as verification |
| Pin applied, still 0 tools | Process did not restart, or the bound is still too loose | §6 Test 3; widen/narrow the bound per the traceback |
| Breaks only on some pod starts | Resolution is non-deterministic over time — a new upstream release changes the answer | Pin; this is the class's defining property |

### Why version tracking cannot see this `[verified 2026-09-22]`

Both mechanisms are structurally blind, for different reasons:

- **Renovate** (`.github/renovate.json5`) has two `customManagers`. One requires
  an explicit `# renovate: datasource=<ds> depName=<name>` comment immediately
  above the value; the other requires `# renovate: image=<repo>` above a
  `repository:`/`tag:` pair. A bare `"args": ["some-mcp-server"]` matches
  neither, so no PR will ever be raised.
- **`runbooks/check-all-versions.py`** parses `*helmrelease.yaml` for charts and
  images, and for raw manifests applies a text pre-filter requiring
  `kind: Deployment|StatefulSet|DaemonSet|Job|CronJob`. A ConfigMap is skipped
  before it is even parsed — and even if parsed, the script extracts container
  `image` refs, and a package name in `args` is not one.

**Therefore an unpinned runtime dependency has zero automated coverage.** The
only control is the contents assertion in §6, run as part of the sweep. Adding
a `# renovate:` annotation above a pinned version is the cheapest way to buy
coverage back — but it only works once the value *is* pinned.

---

## 8) Diagnose Examples

### Diagnose Example 1: an integration silently does nothing

```bash
# 1. Is the surface actually empty? (contents, not shape)
#    -- §6 Test 1

# 2. Why? The startup window holds the real error.
mise exec -- kubectl -n ai logs deploy/mcpo -c app --tail=500 \
  | grep -B5 -A15 "Failed to connect"

# 3. Which invocation is at fault?
mise exec -- kubectl -n ai get cm mcpo-config -o jsonpath='{.data.config\.json}' \
  | python3 -c '
import sys, json
for name, cfg in json.load(sys.stdin)["mcpServers"].items():
    args = cfg.get("args", [])
    pinned = any(("==" in a) or ("<" in a) or ("@" in a and not a.startswith("@"))
                 for a in args)
    print(f"{name:14s} command={cfg[\"command\"]:6s} pinned={pinned}  {args}")
'
```

Expected:
- The empty servers are exactly the ones whose `command` is a resolver
  (`uvx`/`npx`) rather than an absolute path, and whose args carry no bound.

If unclear:
- Compare against the healthy servers in the same config. A working sibling in
  the same pod rules out networking, auth, and the wrapper itself.

### Diagnose Example 2: did upstream change, or did we?

```bash
# Nothing on our side changed if the manifest is untouched:
git log --oneline -3 -- kubernetes/apps/ai/mcpo/app/configmap.yaml
# ...but the pod resolved packages at ITS start time:
mise exec -- kubectl -n ai get pods -l app.kubernetes.io/name=mcpo \
  -o jsonpath='{.items[0].metadata.creationTimestamp}{"\n"}'
```

Expected:
- A manifest last touched long before a pod that started recently, with a
  traceback naming a renamed/removed API, means **upstream moved**. That is the
  class. The fix is a pin, not a rollback of our own change.

If unclear:
- The traceback text usually names the breaking change explicitly — upstream's
  `mcp` 2.x message states the rename and recommends the exact bound.

---

## 9) Health Check

```bash
# 1. Contents assertion for every runtime-resolved integration (§6 Test 1)

# 2. Startup resolution failures anywhere in the ai namespace
for d in mcpo openclaw; do
  echo "== $d"
  mise exec -- kubectl -n ai logs deploy/$d --all-containers --tail=300 2>/dev/null \
    | grep -cE "ModuleNotFoundError|AttributeError|ImportError|Failed to connect to MCP server" || true
done

# 3. Inventory drift — has an unpinned invocation been added?
grep -rnE "uvx |npx |pip install|npm install -g|cargo install" \
  kubernetes/ --include="*.yaml" | grep -v "ENC\[" | wc -l
```

Expected:
- Every integration reports a non-zero tool/endpoint count.
- Zero startup resolution failures.
- The inventory count matches §5's table; a rise means a new member of the class
  that needs a pin and a contents assertion.

---

## 10) Security Check

```bash
# What does each pod fetch from the internet at start, and from where?
grep -rnE "uvx |npx |pip install|npm install -g|cargo install|curl .*\| *(ba)?sh|deb\.nodesource" \
  kubernetes/ --include="*.yaml" | grep -v "ENC\["
```

Expected:
- **No plaintext secrets in the repo** — API keys stay in SOPS-encrypted Secrets
  and reach the process via `secretKeyRef` / `${VAR}` substitution, never as a
  literal in a ConfigMap.
- **Every runtime fetch is pinned.** An unpinned install is a supply-chain
  change executed on every pod start, by a third party, with no review: whoever
  controls that package name chooses what runs in the cluster, whenever they
  publish. A pin is the only thing turning that into a reviewed decision.
- **`curl … | sh` is unreviewed remote code execution.** Where it cannot be
  removed, pin the installer version and prefer checksum verification.
- **No unintended exposure**: `mcpo` is reachable only in-cluster
  (`ClusterIP`, its ingress is `enabled: false`) and is API-key protected.
  Public hostnames are templated (`${SECRET_DOMAIN}`) and must never be written
  literally into a manifest or a doc — this repo is public.
- Runtime-resolved packages are **not** covered by image scanning: the scanner
  reads the image, and these packages are not in it. Do not read a clean image
  scan as coverage of this class.

---

## 11) Rollback Plan

Pins in this class are single-file, single-line changes.

```bash
# Revert a pin that made things worse
git revert <sha> && git push
mise exec -- flux -n ai reconcile ks mcpo --with-source
mise exec -- kubectl -n ai rollout restart deploy/mcpo
mise exec -- kubectl -n ai rollout status deploy/mcpo --timeout=300s
# then re-run §6 Test 1 — a rollback is a change and needs the same gate
```

Note the asymmetry that makes this class safe to fix: an integration already at
**0 tools cannot regress**. A failed pin leaves it exactly where it was, so the
downside of attempting a pin is bounded at zero while the upside is the
integration working again.

If a pin must be widened rather than reverted, change the bound and re-run §6 —
do not remove the bound entirely and call it a rollback.

---

## 12) References

- `kubernetes/apps/ai/mcpo/app/configmap.yaml` — the worked example (2 unpinned `uvx`, 3 pre-installed)
- `kubernetes/apps/ai/mcpo/app/helmrelease.yaml` — the initContainer that pre-installs the healthy three
- `kubernetes/apps/ai/openclaw/app/mcporter-config.yaml` — `npx … @latest`, same class
- `kubernetes/apps/ai/paperclip/app/helmrelease.yaml` — `cargo install unifictl@5.3.1`, the pinned counterexample
- [`container-dependencies.md`](container-dependencies.md) — **different topic**; wait-for initContainers. See the banner at the top of this SOP
- [`verification-contents-not-shape.md`](verification-contents-not-shape.md) — the detection principle, incl. the negative-control rule
- [`falco.md`](falco.md) — records the runtime-install class from the runtime-detection side (the exclusions exist *because* these containers install at start)
- [`self-built-image-rebuild.md`](self-built-image-rebuild.md) — for images we build ourselves, pre-installing is always available
- `.github/renovate.json5` — the two `customManagers` and why they cannot see this
- `runbooks/check-all-versions.py` — the `kind:` pre-filter that skips ConfigMaps
- Findings: `security_ref: F-cfa520f4` (this SOP gap), `F-8fb293e4` (the live mcpo instance)

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| `2026.09.22` | 2026-09-22 | Initial SOP (`F-cfa520f4`). Defines the class — dependencies resolved at pod start from an unpinned upstream — and separates it explicitly from `container-dependencies.md`, which covers wait-for initContainers and is a different topic. Worked example measured live 2026-09-22: mcpo's two `uvx` servers serve HTTP 200 with 0 tools against healthy controls of 2/10/26, root-caused from the pod's own tracebacks to upstream `mcp` 2.x renaming `FastMCP`. Documents why Renovate's `customManagers` and `check-all-versions.py`'s `kind:` pre-filter are both structurally blind to it, the two remedies (pin at the invocation; pre-install into the image), the repo-wide inventory of the class, and a contents-not-shape verification with a negative control. |
