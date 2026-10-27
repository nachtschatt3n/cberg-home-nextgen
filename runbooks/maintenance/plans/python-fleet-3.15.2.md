---
plan_id: python-fleet-3.15.2
component: python                     # image fleet keyed on the Docker Official Image `python` (slim)
supersedes: python-fleet-3.15.0       # carried forward 2026-10-27 (sweep 3f978ad9 rule 4d0): same job, newer bugfix
                                      # (3.15.1 -> 3.15.2). README prefers refresh-in-place; the coordinator asked for a
                                      # new file, so finding_refs + cross-refs are carried by hand (§6).
also_covers: [openclaw-probe, mcpo, mealie-shopping-sync]
pr: null                              # direct-bump lane (coverage.py needs_plan_groups group python-fleet-3.15.2) - no Renovate PR
kind: image
current: "python:3.14.x-slim (3.14.9 live and in git 2026-10-27; 3.14.8 accepted) on 3 PLAN-lane consumers (ai/openclaw-probe CronJob, ai/mcpo initContainer runtime-setup, office/mealie-shopping-sync CronJob)"
target: "python:3.15.2-slim on the same 3 consumers (one commit)"
update_type: minor                    # CPython feature release 3.14 -> 3.15 (NOT a patch); same Debian 13 trixie base
risk: low                             # all three are stdlib-only scripts or a build-only init (§1.3); the 3.15 removals
                                      # touch none of their imports (§1.2); nothing forward-only; every consumer is a short
                                      # CronJob or an init that re-runs on every pod start. 3.15.2 is the SECOND bugfix
                                      # release (fixes a 3.15.0 threaded-import regression, §1.2) - strictly better than 3.15.1.
est_duration_min: 35                  # pre-checks 5 · edit/commit/push 3 · Flux apply ~2 · mcpo Recreate + init
                                      # ~2 (measured ~90 s to Ready) · wait for the next openclaw-probe tick (<=30
                                      # min; schedule so a :00/:30 tick falls inside) · gates 5
needs_reboot: false
touches:
  namespaces: [ai, office]
  resources:
    - cronjob/openclaw-probe            # ai - Flux Kustomization ai/openclaw; only the CronJob changes,
                                        # deployment/openclaw is NOT rolled (no openclaw values/chart edit)
    - helmrelease/mcpo                  # ai - Flux Kustomization ai/mcpo; app-template values: init tag only
    - deployment/mcpo                   # ai - rolls (strategy Recreate, emptyDir only, no PVC); ~90 s outage of
                                        # the MCP tool server consumed by openclaw (mcporter-config) and falco
    - cronjob/mealie-shopping-sync      # office - Flux Kustomization office/mealie; deployment/mealie untouched
  shared: [monitoring]                  # §4 reads Prometheus (kube-state-metrics) AND openclaw-probe POSTs to
                                        # Alertmanager - both are the window's instruments. No gateway/envoy,
                                        # DNS, CNI, storage or Authentik surface: none of the three has an
                                        # HTTPRoute, a PVC or an SSO path.
depends_on: []
conflicts_with:
  # Carried from python-fleet-3.15.0 and re-checked 2026-10-27 (all five files exist and are non-terminal).
  # No kube-prometheus-stack plan is open; if one is filed, add it: §4 reads Prometheus and §4.1 asserts
  # Alertmanager POST 200, a same-night kps bump blinds both gates.
  - redis-fleet-8.10.3                  # reciprocity: restarts redis for office/ consumers (sun-attended:2026-11-29). Successor of
                                        # redis-fleet-8.10.2 (superseded concurrently 2026-10-27, same sweep); lists this plan back.
  - openclaw-2026.10.5                  # same Flux Kustomization ai/openclaw as cronjob/openclaw-probe; currently blocked
  - helm-drift-detection                # adds spec.driftDetection to every HR incl. helmrelease/mcpo (sat-attended:2026-11-07)
  - flux-oci-chart-sources              # rewrites HelmRelease chart sources (bjw-s app-template consumers incl. mcpo)
  - nextcloud-9.4.1                     # ns office; an office-wide silence would hide a failing mealie-shopping-sync (KubeJobFailed)
exclusive: false
autonomy_override: human-gated        # RESTRICTS only (carried from the 2026-10-23 review): a minor interpreter move is
                                      # an attended window item, not nightly - see §1.6.
security_ref: F-8bac0223                # the OPEN python:3.14.7-slim "newer upstream tag" row; detail stays in the DB
capability_change: false                # same-behaviour runtime for unchanged scripts; no new feature, route,
                                        # permission, API or exposure
rollback_class: git-revert              # nothing forward-only: no PVC, no schema, no persisted state from the bump
finding_refs: [F-8bac0223, F-691c4827, F-e716fd93, F-1e43e578, F-237bd599]   # re-queried 2026-10-27 (`finding list --grep`):
                                        # image security row F-8bac0223 (still open, last seen 2026-10-17), the three CURRENT
                                        # per-consumer version rows - openclaw-probe F-691c4827 / mcpo F-e716fd93 /
                                        # mealie-shopping-sync F-1e43e578, all titled "3.14.9-slim -> 3.15.2-slim (minor)",
                                        # last seen 2026-10-27 - and the ops-retro deny-glob proposal F-237bd599.
premises:
  # All read-only. Measured live 2026-10-27: all three PASS on 3.14.9-slim.
  - id: probe-on-3.14.x
    why: >-
      `current:` claims the CronJob runs python:3.14.8-slim or 3.14.9-slim. Anything else means the fleet moved
      (3.15 already applied or an unknown tag - this plan is stale) or the file changed shape (the §3 sed would not match).
    run: kubectl get cronjob openclaw-probe -n ai -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_matches: '^python:3\.14\.[89]-slim$'
  - id: mcpo-init-on-3.14.x
    why: >-
      The python image is the mcpo initContainer `runtime-setup`, not the app container
      (ghcr.io/open-webui/mcpo). A different first init or strategy means the values shape moved.
    run: kubectl get deploy mcpo -n ai -o jsonpath='{.spec.template.spec.initContainers[0].name}={.spec.template.spec.initContainers[0].image} {.spec.strategy.type}'
    expect_matches: '^runtime-setup=python:3\.14\.[89]-slim Recreate$'
  - id: mealie-sync-on-3.14.x
    why: "Third member of the coverage group."
    run: kubectl get cronjob mealie-shopping-sync -n office -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_matches: '^python:3\.14\.[89]-slim$'
  # The registry facts (target still trixie; past the 48 h minor cooldown; no newer bugfix) are §2 gates
  # 2.1-2.3, each printing a STOP token on failure - they need curl/python network reads, kept out of premises.
status: draft                           # retarget 3.15.1 -> 3.15.2 needs a fresh plan-review before vetting
window: "sat-attended:2026-11-14"       # carried from python-fleet-3.15.0. Cooldown on 3.15.2-slim (pushed 2026-10-27T02:15Z)
                                        # lapses 2026-10-29T02:15Z, far before the slot. Slot still holds only this plan.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-27"
---

# python-fleet-3.15.2 - python:3.14.x-slim -> 3.15.2-slim on openclaw-probe, mcpo (init), mealie-shopping-sync

## 1. Summary & why held

This plan replaces `python-fleet-3.15.0` (vetted for 3.15.1, now `superseded`). The job is the same. Only the
bugfix target moved: Docker Official `python:3.15.2-slim` was published 2026-10-27T02:15Z. The old plan's §2.3
says that when a newer bugfix exists you STOP and retarget, and that condition is now true.

One commit moves three inline `python:*-slim` pins from `3.14.x-slim` (3.14.9 live) to `3.15.2-slim`:

| Consumer | Object | What python does there | File |
|---|---|---|---|
| ai/openclaw-probe | CronJob `*/30` | runs `probe.py` (stdlib `json`, `os`, `time`, `urllib.request`): TTS health check, POSTs fire/resolve of `OpenClawVoiceProviderDown` to Alertmanager (`http://kube-prometheus-stack-alertmanager.monitoring.svc:9093`) | `kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml` |
| ai/mcpo | Deployment `mcpo`, **initContainer `runtime-setup`** | build environment only: `apt-get` nodesource `node_20`, `pip install uv`, `npm install -g` three node MCP servers into the `/shared` emptyDir, copies `node`, `uv`, `uvx` to `/shared/bin`. The **app container `ghcr.io/open-webui/mcpo:git-44ce6d0` is NOT changed**. | `kubernetes/apps/ai/mcpo/app/helmrelease.yaml` |
| office/mealie-shopping-sync | CronJob `*/5` | runs `sync.py` (stdlib `json`, `os`, `sys`, `urllib.error`, `urllib.request`, `datetime`): Mealie (`http://mealie.office:9000`) -> HA (`http://home-assistant.home-automation:8123`) shopping list | `kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml` (script in `shopping-sync-configmap.yaml`) |

### 1.1 What actually holds each member (the coverage `reason` is mis-attributed)

The group's dispatch reason, *"held at 2026.6.11 pending the Memory Core->SQLite migration (2026.7.1 blocked)"*,
is the reason of the FIRST member only. It is **not** a property of the python image. I re-measured this on
2026-10-27 with `runbooks/coverage.py --json` (`needs_plan[]`) against `runbooks/auto-update-policy.yaml`
version `2026.10.26`:

- **openclaw-probe**: held by `match: "*openclaw*"` (policy line 455, no `max:`). That reason belongs to the
  OpenClaw APP image. The rule matches only because the component key `openclaw-probe` contains the substring
  `openclaw`. The probe is a stdlib script with no OpenClaw code and no coupling to the OpenClaw version.
  **This is a misattribution, as the coordinator suspected.** It is already recorded on `F-237bd599`.
- **mcpo**: held by `match: "*mcpo*"` (line 311, no `max:`), reason *"python init base image major
  (3.11->3.14) rides these tags."* That move executed in `39fa6625` (2026-09-13). The rule's premise is used
  up, but because it has no `max:`, it still holds every mcpo update. **The rule is stale.**
- **mealie-shopping-sync**: no deny rule. Held by **G3** (breaking-change signal). The matched text is the
  What's New boilerplate *"Migration/Upgrade Guide ... pyperformance benchmark suite report a 7-8% geometric
  mean"*, which is a performance paragraph. This is a **G3 false positive** on the wording. It is also held by
  G5 (48 h minor cooldown, which lapses 2026-10-29T02:15Z).

The conclusion "a Python minor deserves an attended plan" still holds on its own merits (§1.2, §1.6). The
policy narrowing proposed on `F-237bd599` (`max: patch`) would **not** release this bump, because it is a minor.

### 1.2 Upstream: what 3.15 changes, and what 3.15.2 adds

**3.15 feature-release surface.** This is unchanged from the vetted 3.15.0 plan and was re-read here:

- **UTF-8 mode is the default (PEP 686).** It only applies when no `encoding` argument is given. None of the
  scripts open files, and all bytes are decoded via `.decode()` (already UTF-8). No effect.
- **Removed in 3.15:**
  - `ast` constructor strictness
  - `collections.abc.ByteString`
  - `ctypes.SetPointerType`
  - `datetime.strptime` with `%d` but no year
  - `glob.glob0/glob1`
  - `http.server.CGIHTTPRequestHandler`
  - `Loader.load_module`
  - `importlib.resources.files(package=)`
  - `PurePath.is_reserved`
  - `platform.java_ver`
  - `sre_*`
  - `RLock` extra args
  - `co_lnotab`
  - `typing.ByteString` / kw-`NamedTuple`
  - `wave` marks
  - `zipimporter.load_module`

  **None of these is used** by either script. They use `urllib.request.urlopen`, `json`,
  `time.strftime/gmtime` and `datetime.now(timezone.utc).isoformat()`.
- **urllib / http.client / ssl:** additions only, with no default changes to `urlopen`, HTTP or TLS behaviour.

**3.15.2 changelog** (docs.python.org/3.15/whatsnew/changelog.html, section "Python 3.15.2 final", release date
2026-10-25, read 2026-10-27). This is a bugfix and security release with no API removals and no changed
defaults. The entries that touch these consumers' code paths:

- **gh-159963**: *"Fix a regression in Python 3.15.0 where threads importing submodules of packages for the
  first time could raise `_DeadlockError` or a spurious 'partially initialized module' ImportError"*. This is
  exactly the kind of x.0 regression the old plan named as residual risk. Our scripts are single-threaded,
  but pip in the mcpo init is not guaranteed to be. This fix is a reason to prefer 3.15.2.
- **ssl** (security section): *"ssl now rejects TLS certificate chains that contain any of a set of compromised
  eMudhra intermediate CA keys"*. Two of our consumers do not use TLS at all: probe -> Alertmanager and
  sync -> Mealie/HA are both plain `http://` cluster-internal URLs (shown in the table). The mcpo init's TLS
  peers (deb.nodesource.com, pypi.org, registry.npmjs.org) are fetched by apt, pip and npm. Of those, only pip
  runs on this interpreter's `ssl`, and it uses certifi/truststore against PyPI's public CA, not eMudhra. **§4.2
  is the gate**: if pip's TLS broke, the init would exit non-zero.
- The other security fixes (`http.cookiejar`, `tarfile.tar_filter`) are in modules none of the scripts import.
  pip uses tarfile only for sdists, and `uv` ships as a `py3-none` wheel.
- gh-106045 (venv path discovery) does not apply, because the init uses no venv. The asyncio, zstd,
  free-threaded and REPL fixes also do not apply.

**Image facts (measured 2026-10-27 against the Docker Hub API):**

- `3.15.2-slim` digest == `3.15.2-slim-trixie` digest ==
  `sha256:197f6622a70b727a4e61bdac13a73b4e2b914b896aa5a729ceb1f45a09bde5fa`
- amd64 manifest: `sha256:7ce16513bf93...`
- `last_updated`: `2026-10-27T02:15:05Z`
- `3.15.3-slim`: HTTP 404, so 3.15.2 is newest.
- Trivy 0.70.0 reports Debian **13.7**, which is the same base as 3.14.9-slim and 3.15.1-slim. So the
  nodesource `nodistro` apt flow is unchanged.
- pip **26.2.2** is still bundled at `/usr/local/lib/python3.15/site-packages`.

### 1.3 Evidence gathered (dry tests)

- **Security side:** a Trivy scan of `python:3.15.2-slim` (2026-10-27) shows the same result as
  3.14.9-slim and 3.15.1-slim, so taking the minor brings **no security gain** for the image scan.
  Counts and detail stay on the DB record (`F-8bac0223`), not here (docs/sops/vulnerability-disclosure.md).
- **Script compatibility:** the 3.15.0 plan's dry-compile of both scripts was under CPython 3.15.0b2 with
  `-W error`, plus execution of every stdlib call they make. It still covers the API surface, because 3.15.1
  and 3.15.2 are bugfix-only. It was not re-run against a final build, because uv on macOS still lacks one.
  The in-cluster gates in §4 are the proof.
- **sed dry test (2026-10-27):** run on scratch copies of the live 3.14.9 files, the edits change exactly
  these lines (§3).

### 1.4 History and baseline

- `python-fleet-3.14.8` executed on 2026-10-13.
- 3.14.9 was applied on 2026-10-23, then auto-reverted by a false-positive health gate. It re-landed via
  Renovate #420 (`b8b55656`) on 2026-10-25.
- Live and in git on 2026-10-27, all three members read `3.14.9-slim`. The premises and the sed still also
  accept 3.14.8, in case of another revert.
- `python-fleet-3.15.0` was reviewed `ready-for-go@2026-10-25` and slotted for `sat-attended:2026-11-14` with
  target 3.15.1. It is now superseded by this file. What changed is §1.2 / §1.3 (new image facts and
  changelog), §2.1-2.3 (digest, cooldown and next-bugfix gates retargeted), and every `3.15.1` in §3 and §4.
  Steps, gates, rollback and conflicts are otherwise carried over unchanged.

### 1.5 Fleet scope: the three members only (canary), the other 14 follow

The same `python:3.14.9-slim` string appears on 14 further consumers:

- ai/ollama-toolfix
- download/tube-archivist image-sync and metadata-sync (2)
- 11 media/library-tools objects

There are also 3 `3.14.9-alpine` consumers, which use a different string and base and are untouched. The live
sweep has version rows for these (for example F-0be2a0b6 media-sidecar and F-302480e4 crash-ghost-reaper),
all targeting 3.15.2.

This plan edits **ONLY openclaw-probe, the mcpo init and mealie-shopping-sync**. These three are the coverage
group, they have measured per-consumer gates, and they span three distinct shapes (Alertmanager probe,
pip/npm build init, HTTP-to-HA sync).

**Follow-up:** once this plan passes and soaks for at least one nightly, the 14 slim siblings move to
3.15.2-slim as a second step. That goes through the direct-bump lane if the policy lets minors through,
otherwise through a second fleet plan, filed at that point. Mixed 3.14/3.15 across independent CronJobs is
harmless. F-8bac0223 stays OPEN after this plan.

### 1.6 Slot: attended Saturday, not nightly

The slot is carried over unchanged: **`sat-attended:2026-11-14`** (90 min budget vs est 35). It is still free,
because the slot holds no other plan per `grep '^window:'` on 2026-10-27. The cooldown lapses
2026-10-29T02:15Z. The tube-archivist plans already budget around python-fleet's 35 min on 11-14, and the
duration is unchanged, so their arithmetic still holds.

Not `nightly`: the §4 gates need a human to read the openclaw-probe tick and the mcpo tool counts, and the
03:30 slot overlaps Step 0 safe-update churn. No reboot is needed.

**Verdict:** risk `low`. The honest residual is an interpreter minor on a two-day-old bugfix release.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). All read-only.

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py python-fleet-3.15.2      # every premise must PASS

# 2.0 the three files are on the 3.14.x baseline (3.14.8 OR 3.14.9), nothing is on 3.15 yet.
#     Prints "ok 3 PRE=<tag>"; anything else => STOP and re-plan. PRE is the tag a rollback must restore (§5).
N=$(grep -c 'python:3\.14\.[89]-slim$\|tag: 3\.14\.[89]-slim$' kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml kubernetes/apps/ai/mcpo/app/helmrelease.yaml | awk -F: '{s+=$2} END{print s}')
PRE=$(grep -h -o '3\.14\.[89]-slim$' kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml kubernetes/apps/ai/mcpo/app/helmrelease.yaml | sort -u | tr '\n' ',')
[ "$N" = 3 ] && echo "ok $N PRE=$PRE" || echo "STOP baseline-moved N=$N"
#   Measured 2026-10-27: ok 3 PRE=3.14.9-slim,

# 2.1 target still Debian trixie AND print the digest so a re-push is visible.
#     Prints "trixie sha256:..." ; DIFFERENT => STOP and re-plan.
#     Expected (2026-10-27): trixie sha256:197f6622a70b727a4e61bdac13a73b4e2b914b896aa5a729ceb1f45a09bde5fa
#     Another digest = the tag was re-pushed: re-run 2.2 (cooldown restarts) and re-run the §1.3 Trivy count.
python3 -c "import json,urllib.request as u;g=lambda t: json.load(u.urlopen('https://hub.docker.com/v2/repositories/library/python/tags/'+t))['digest'];a=g('3.15.2-slim');print('trixie' if a==g('3.15.2-slim-trixie') else 'DIFFERENT',a)"

# 2.2 past the 48 h MINOR cooldown (policy minimum_release_age_hours). Prints AGED; YOUNG => STOP.
#     Measured 2026-10-27: last_updated 2026-10-27T02:15:05Z -> YOUNG until 2026-10-29T02:15Z (by design today;
#     the 2026-11-14 slot is far past it unless the tag is re-pushed again).
python3 -c "import json,urllib.request as u,datetime as d;t=json.load(u.urlopen('https://hub.docker.com/v2/repositories/library/python/tags/3.15.2-slim'))['last_updated'];a=(d.datetime.now(d.timezone.utc)-d.datetime.fromisoformat(t.replace('Z','+00:00'))).total_seconds()/3600;print('AGED' if a>=48 else 'YOUNG')"

# 2.3 no 3.15.3 yet? (if 3.15.3-slim exists, STOP and retarget - same carry-forward as 3.15.1 -> 3.15.2).
#     ABSENCE gate: only HTTP 404 counts as absent; any other failure prints FETCH_FAILED (also a STOP).
#     Measured 2026-10-27: 3.15.3-slim -> HTTP 404 (ok-no-3.15.3). KNOWN-BAD CONTROL: substitute 3.15.2-slim
#     (exists) -> STOP-...-exists-retarget; the same form was shown on 2026-10-25 to print FETCH_FAILED URLError
#     with https_proxy=http://127.0.0.1:9.
python3 -c "import urllib.request as u,urllib.error as e
try: u.urlopen('https://hub.docker.com/v2/repositories/library/python/tags/3.15.3-slim',timeout=15); print('STOP-3.15.3-exists-retarget')
except e.HTTPError as x: print('ok-no-3.15.3' if x.code==404 else 'FETCH_FAILED http %s'%x.code)
except Exception as x: print('FETCH_FAILED',type(x).__name__)"

# Flux owners healthy and on HEAD (all three Kustomizations live in the app namespace)
flux get kustomizations -n ai openclaw
flux get kustomizations -n ai mcpo
flux get kustomizations -n office mealie
flux get helmreleases -n ai mcpo                                         # Ready True

# Baseline: last runs of both CronJobs succeeded (re-record in-window)
kubectl -n ai get cronjob openclaw-probe -o jsonpath='{.status.lastSuccessfulTime} {.status.lastScheduleTime}{"\n"}'
kubectl -n office get cronjob mealie-shopping-sync -o jsonpath='{.status.lastSuccessfulTime} {.status.lastScheduleTime}{"\n"}'

# NOTE: shell variables (N, PRE, PF, J, PUSH_TS) do NOT survive separate tool calls. Run each §2/§3/§4 block in ONE call,
#       or re-derive: PRE/N via 2.0, PUSH_TS via `export PUSH_TS=<the UTC time printed after git push>`.

# Baseline: the running init imageID (record it; it is the PRE-tag digest the §5 rollback returns to)
kubectl -n ai get pod -l app.kubernetes.io/name=mcpo -o jsonpath='{.items[0].status.initContainerStatuses[0].imageID}{"\n"}'

# Baseline: mcpo per-server tool counts (the §4.2 contents baseline) + negative control.
# Measured 2026-10-13 and 2026-10-23 (identical): context7=2 prometheus=10 alertmanager=9 kubernetes=14 github=26, nonexistent=404
kubectl -n ai port-forward svc/mcpo 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 3
for s in context7 prometheus alertmanager kubernetes github nonexistent; do
  printf '%s ' "$s"; curl -s -o /tmp/mcpo-$s.json -w '%{http_code} ' http://localhost:18000/$s/openapi.json
  python3 -c "import json;print(len(json.load(open('/tmp/mcpo-$s.json')).get('paths',{})))" 2>/dev/null || echo PARSE_FAIL
done
kill $PF 2>/dev/null
```

STOP in any of these cases:

- any premise fails;
- 2.0-2.3 print a STOP, YOUNG, DIFFERENT or FETCH_FAILED token;
- any Flux object is not Ready;
- a baseline server is non-200.

§4.2 compares against what you record HERE, not the historical numbers, because the init pulls the newest npm
packages on every start.

## 3. Steps

```bash
cd /Users/mu/code/cberg-home-nextgen
git pull --rebase

# 3.1 the two CronJobs (BSD sed; dry-tested 2026-10-27 on scratch copies of the live 3.14.9 files)
sed -i '' 's|image: python:3\.14\.[89]-slim$|image: python:3.15.2-slim|' \
  kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml \
  kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml

# 3.2 the mcpo initContainer tag (the app container tag git-44ce6d0 is NOT touched; it has no '-slim')
sed -i '' 's|^\([[:space:]]*tag:[[:space:]]*\)3\.14\.[89]-slim$|\13.15.2-slim|' \
  kubernetes/apps/ai/mcpo/app/helmrelease.yaml

git diff --stat -- kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml \
  kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml \
  kubernetes/apps/ai/mcpo/app/helmrelease.yaml      # expect exactly 3 files, 3 insertions, 3 deletions
```

Dry-test result (scratch copies, 2026-10-27). Each of the three files differs from the live 3.14.9 original
in exactly this one line:

```
openclaw-probe.yaml        95c95  <  image: python:3.14.9-slim   >  image: python:3.15.2-slim
shopping-sync-cronjob.yaml 48c48  <  image: python:3.14.9-slim   >  image: python:3.15.2-slim
helmrelease.yaml (mcpo)    47c47  <  tag: 3.14.9-slim            >  tag: 3.15.2-slim
```

Afterwards, `shopping-sync-cronjob.yaml` still contains `3.14.7-slim` once, in a comment ("already runs
elsewhere"). That is expected: leave it.

```bash
# 3.3 write the message file FIRST, then commit ONLY these paths (shared worktree) and verify before pushing
MSG=$(mktemp /tmp/msg-python-fleet-3152.XXXXXX)   # unique file (shared worktree)
cat > "$MSG" <<'EOF'
chore(deps): python 3.14.x-slim -> 3.15.2-slim on openclaw-probe, mcpo init, mealie-shopping-sync

Plan: runbooks/maintenance/plans/python-fleet-3.15.2.md (security_ref F-8bac0223)
EOF
git commit --only \
  kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml \
  kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml \
  kubernetes/apps/ai/mcpo/app/helmrelease.yaml \
  -F "$MSG"
git show --stat HEAD            # exactly the 3 files above
git log -1 --format=%s          # must be the subject above; amend before push if not
git push
export PUSH_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

Flux applies on the push webhook. Do not reconcile manually (SOP default). If nothing has applied after 10
minutes, check the revision with `flux get kustomizations -n ai openclaw` and escalate rather than force it.

Do not push within 2 min before a `:00`/`:30` tick. That keeps §4.1's "first job after push" unambiguous.

## 4. Verification

Every gate compares against objects created AFTER `PUSH_TS`, which §3.3 exports. The python one-liners read
it from the environment.

**4.0 Applied (floor).** Each live spec carries the new tag:

```bash
kubectl -n ai get cronjob openclaw-probe -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'          # python:3.15.2-slim
kubectl -n office get cronjob mealie-shopping-sync -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}' # python:3.15.2-slim
kubectl -n ai get deploy mcpo -o jsonpath='{.spec.template.spec.initContainers[0].image}{"\n"}'                                    # python:3.15.2-slim
```

This gate fails, printing the old `3.14.x-slim`, if Flux has not applied yet. Wait or escalate. Do not judge
4.1-4.3 on old pods.

**4.1 openclaw-probe: CONTENTS. It still measures TTS and still reaches Alertmanager on 3.15.** Check the
first Job after `PUSH_TS` against the baseline log shape: `local_tts_ok=True` plus two
`alertmanager POST 200` lines (re-measured 2026-10-23, job `openclaw-probe-29879550`).

```bash
J=$(kubectl -n ai get jobs -o json | python3 -c "
import sys,json,os
ts=os.environ['PUSH_TS']
js=[j for j in json.load(sys.stdin)['items']
    if (j['metadata'].get('ownerReferences') or [{}])[0].get('name')=='openclaw-probe'
    and j['metadata']['creationTimestamp']>ts]
js.sort(key=lambda j:j['metadata']['creationTimestamp']); print(js[-1]['metadata']['name'] if js else 'NONE')")
echo "$J"                                                                   # NONE => tick not reached yet; wait
kubectl -n ai get job "$J" -o jsonpath='{.status.succeeded}{"\n"}'           # 1
kubectl -n ai get pod -l job-name="$J" -o jsonpath='{.items[0].status.containerStatuses[0].image}{"\n"}'   # python:3.15.2-slim
kubectl -n ai logs job/"$J" | grep -ciE '^local_tts_ok=true$'               # 1
kubectl -n ai logs job/"$J" | grep -ciE '^alertmanager POST 200 '           # 2
```

PASS = succeeded `1`, image `3.15.2-slim`, `local_tts_ok=True` count 1, `POST 200` count 2.

Failure shapes:

- **Import or syntax break:** `succeeded` stays empty and the log holds a traceback.
- **urllib/TLS regression:** the log prints `tts health error:` and `local_tts_ok=False` (so the first grep
  reads 0). It ALSO fires `OpenClawVoiceProviderDown` critical, which is the user-visible symptom.
- **Alertmanager POST failure:** the script raises and the Job fails.

Caveat: `local_tts_ok=False` can also mean the Mac-mini TTS server is down. Curl its `/health` from the Mac
before blaming the image.

**4.2 mcpo: CONTENTS. Every MCP server still starts and exposes its tools.**

```bash
kubectl -n ai get pod -l app.kubernetes.io/name=mcpo -o jsonpath='{.items[0].status.startTime} {.items[0].status.initContainerStatuses[0].image} {.items[0].status.initContainerStatuses[0].state.terminated.exitCode}{"\n"}'
# startTime AFTER PUSH_TS; image python:3.15.2-slim; exitCode 0
kubectl -n ai wait --for=condition=Ready pod -l app.kubernetes.io/name=mcpo --timeout=600s
kubectl -n ai logs -l app.kubernetes.io/name=mcpo -c runtime-setup --tail=40 | grep -ciE 'Runtime setup complete'   # 1
kubectl -n ai port-forward svc/mcpo 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 3
for s in context7 prometheus alertmanager kubernetes github nonexistent; do
  printf '%s ' "$s"; curl -s -o /tmp/mcpo-$s.json -w '%{http_code} ' http://localhost:18000/$s/openapi.json
  python3 -c "import json;print(len(json.load(open('/tmp/mcpo-$s.json')).get('paths',{})))" 2>/dev/null || echo PARSE_FAIL
done
kill $PF 2>/dev/null
```

PASS = every real server returns `200` with paths >= the §2 baseline, and `nonexistent` returns `404`. That
negative control shows a 404 on a real name is a real failure, not a URL mistake.

Failure shapes:

- **`pip`/`uv` broken on 3.15**, including pip TLS under the new ssl denylist (§1.2): the init exits non-zero
  (`Init:Error` or `Init:CrashLoopBackOff`), the Ready wait times out, and the `Runtime setup complete` count
  reads 0.
- **Broken `node`/`uvx` copy:** the affected server returns 404 or 0 paths.
- **One npm server drops while the others are intact:** that points at npm drift, not python (see §5).

**4.3 mealie-shopping-sync: CONTENTS. It still reads Mealie and Home Assistant.** Check the first Job after
`PUSH_TS` (within 5 min) against the baseline `done: pushed=0 already-synced=143 excluded=0 lists=1`
(re-measured 2026-10-23).

```bash
J=$(kubectl -n office get jobs -o json | python3 -c "
import sys,json,os
ts=os.environ['PUSH_TS']
js=[j for j in json.load(sys.stdin)['items']
    if (j['metadata'].get('ownerReferences') or [{}])[0].get('name')=='mealie-shopping-sync'
    and j['metadata']['creationTimestamp']>ts]
js.sort(key=lambda j:j['metadata']['creationTimestamp']); print(js[-1]['metadata']['name'] if js else 'NONE')")
kubectl -n office get job "$J" -o jsonpath='{.status.succeeded}{"\n"}'                          # 1
kubectl -n office logs job/"$J" | grep -ciE '^home assistant list holds [0-9]+ item'             # 1
kubectl -n office logs job/"$J" | grep -iE '^done: pushed=[0-9]+ already-synced=[1-9][0-9]* '   # one line
```

PASS = succeeded `1`, the HA read line is present, and `already-synced` is non-zero.

Failure shapes:

- **Empty Mealie read:** prints `already-synced=0`, which fails the regex.
- **HTTP/urllib break:** the script exits 1 with `HTTP <code>:` on stderr and `succeeded` stays empty.

**Instruments (CONTROL lines).** These read kube-state-metrics in the `kube-prometheus-stack` Prometheus. The
`assert r` in the script below makes an empty answer a failure.

CONTROL: metric kube_job_status_failed - `job_name=~"openclaw-probe.*|mealie-shopping-sync.*"` in ns ai/office: Jobs created after PUSH_TS read 0 (baseline 0).
CONTROL: metric kube_deployment_status_replicas_available - `{namespace="ai",deployment="mcpo"}` back to 1 within 10 min of the push (baseline 1).
CONTROL: metric kube_pod_init_container_status_restarts_total - `{namespace="ai",container="runtime-setup"}` stays 0 on the new pod (an init crash loop shows here first).

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for q in 'kube_job_status_failed{namespace=~"ai|office",job_name=~"openclaw-probe.*|mealie-shopping-sync.*"}' \
         'kube_deployment_status_replicas_available{namespace="ai",deployment="mcpo"}' \
         'kube_pod_init_container_status_restarts_total{namespace="ai",container="runtime-setup"}'; do
  printf '%s => ' "$q"; curl -s -G http://localhost:19090/api/v1/query --data-urlencode "query=$q" \
    | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];assert r,'EMPTY RESULT';print([x['metric'].get('job_name',x['metric'].get('pod',''))+'='+x['value'][1] for x in r])"
done
kill $PF 2>/dev/null
```

## 5. Rollback

Nothing forward-only happens. A base-image change writes no PVC, no schema and no persisted state:

- mcpo's `/shared` is an emptyDir, rebuilt on every start.
- The mealie sync's writes to Mealie and HA are the job's normal behaviour and are identical on either
  interpreter.

Rollback is a revert:

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-3.3>
git show --stat HEAD            # the same 3 files, tags back to the PRE tag(s) recorded in §2.0 (3.14.8 or 3.14.9)
git log -1 --format=%s          # Revert "chore(deps): python 3.14.x-slim -> 3.15.2-slim ..."
git push
```

If only one member fails, a partial rollback is acceptable and preferable. Restore just that file's line with
`git checkout <sha-of-3.3>~1 -- <file>`, commit it with `--only <file>`, and leave the others on 3.15.

**Confirm the cluster is back:**

- The §4.0 commands print the pre-change `python:3.14.[89]-slim` (PRE from §2.0) for each reverted member.
- The mcpo pod `startTime` is after the revert push, and the §4.2 counts match the §2 baseline.
- The next openclaw-probe and mealie Jobs pass §4.1 and §4.3.

**If §4.2 failed because an npm package moved** (one server down, init log clean), the revert will NOT fix it,
because the reverted init re-pulls the same newest npm packages. Pin the offending package in the init script
under a separate plan or commit, and say so in the window report.

If `OpenClawVoiceProviderDown` fired during a failed §4.1, it resolves on the next successful probe tick (the
probe POSTs `endsAt=now`). No manual Alertmanager action is needed.

## 6. Interference notes

- **Supersession bookkeeping (done in the same change as this file):**
  - `python-fleet-3.15.0` is set to `status: superseded` with `window: null` and a pointer here.
  - The redis reciprocity runs through `redis-fleet-8.10.3`, which another planner superseded from 8.10.2 in
    the same sweep. It already lists `python-fleet-3.15.2`, so no redis plan needed an edit from this change.
  - The tube-archivist plans mention "python-fleet" on 11-14 in prose only. Their budget arithmetic (35 min)
    is unchanged.
  - Any home-operation go/no-go issue keyed on `python-fleet-3.15.0` must be re-keyed or re-asked, because the
    review that produced it no longer applies.
- **Flux plans** (`flux-oci-chart-sources` sun 11-22, `helm-drift-detection` sat 11-07) restart or rewrite the
  machinery that applies `helmrelease/mcpo`. Serialize with them. `openclaw-2026.10.5` (blocked) shares the
  Flux Kustomization `ai/openclaw` with `cronjob/openclaw-probe`.
- **No kube-prometheus-stack plan is open.** If one is filed, it must not share the night: §4.1 asserts
  `POST 200` to Alertmanager and the CONTROL lines read Prometheus.
- **Renovate x.y.z patches on 3.14** may still land via Step 0 before the slot. That is fine: §2.0, the
  premises and the sed accept 3.14.8 or 3.14.9. A 3.14.10 landing would make the premises FAIL, which is the
  intended STOP. If that happens, widen the regexes and re-review.
- **redis-fleet-8.10.3** (sun-attended:2026-11-29) restarts the redis behind office/ consumers. It is
  in a different slot, so there is no clash as scheduled. Never put the two on the same night.
- **mcpo consumers:** openclaw reaches mcpo through `mcporter-config`, and the ~90 s Recreate drops in-flight
  tool calls. Check that no OpenClaw cron is due (morning briefing ~07:00), per
  `feedback_no_openclaw_roll_during_crons`. This plan does not roll openclaw itself.
- **Not rolled:** `deployment/openclaw`, `deployment/mealie`, `deployment/ollama-toolfix`.
- **Repo corrections owed** (report only; out of scope for this plan):
  1. `*openclaw*` (no `max:`) catches `openclaw-probe` by substring. It puts the OpenClaw app's Memory-Core
     reason on a stdlib python CronJob, and coverage prints that reason for this whole group (tracked on
     `F-237bd599`).
  2. The `*mcpo*` reason has been used up since `39fa6625`.
  3. G3's regex fires on CPython What's New boilerplate.
  4. The mcpo init installs nodesource `node_20.x`, which is past upstream EOL. That needs a separate plan.
