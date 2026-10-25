---
plan_id: python-fleet-3.15.0
component: python                     # image fleet keyed on the Docker Official Image `python` (slim);
                                      # plan_id kept at python-fleet-3.15.0 on purpose (README "refresh in place, keep the
                                      # plan_id"): the coverage group is now keyed python-fleet-3.15.1 - same job, newer x.1
also_covers: [openclaw-probe, mcpo, mealie-shopping-sync]
pr: null                              # direct-bump lane (coverage.py needs_plan_groups) - no Renovate PR
kind: image
current: "python:3.14.x-slim (3.14.9 live and in git 2026-10-25, re-landed by #420; 3.14.8 accepted) on 3 PLAN-lane consumers (ai/openclaw-probe CronJob, ai/mcpo initContainer runtime-setup, office/mealie-shopping-sync CronJob)"
target: "python:3.15.1-slim on the same 3 consumers (one commit)"
update_type: minor                    # CPython feature release 3.14 -> 3.15 (NOT a patch); same Debian 13 trixie base
risk: low                             # (refreshed 2026-10-25, baseline 3.14.x, target 3.15.1) all three are stdlib-only scripts or a build-only init (§1.3); the 3.15
                                      # removals touch none of their imports (§1.2, dry-compiled §1.3); nothing
                                      # forward-only; every consumer is a short CronJob or an init that re-runs on
                                      # every pod start. Residual risk = x.0 interpreter regressions (3.15.1 is the first bugfix release; its tag was re-pushed 2026-10-24T08:08Z).
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
  # Refreshed 2026-10-25. Dropped (retired/executed): python-fleet-3.14.8 (executed, file retired - this plan IS its
  # successor), kube-prometheus-stack-92.2.0 (no kps plan is open now; if one is filed re-add it: §4 reads Prometheus and
  # §4.1 asserts Alertmanager POST 200, a same-night kps bump blinds both gates), flux-fleet-0.60.0 (executed 10-06).
  # flux-distribution-2.9.6 dropped 2026-10-25 (executed/retired - no longer an open plan).
  - redis-fleet-8.10.2                  # reciprocity: it restarts redis for ai/ + office/ consumers in the same namespaces
                                        # (sun-attended:2026-11-29, so no same-slot clash, but they must not share a night)
  - openclaw-2026.10.5                  # same Flux Kustomization ai/openclaw as cronjob/openclaw-probe; currently blocked
  - helm-drift-detection                # adds spec.driftDetection to every HR incl. helmrelease/mcpo
  - flux-oci-chart-sources              # rewrites HelmRelease chart sources (bjw-s app-template consumers incl. mcpo)
  - nextcloud-9.4.1                     # ns office; an office-wide silence would hide a failing mealie-shopping-sync
                                        # (KubeJobFailed). Replaces the dead nextcloud-fleet-35.0.1 ref; the
                                        # nextcloud-fleet-34.0.5 file it briefly pointed at was removed 2026-10-23
exclusive: false
autonomy_override: human-gated        # RESTRICTS only (2026-10-23 review): a minor interpreter move is an attended
                                      # window item, not nightly. Slot: sat-attended:2026-11-14 (or an attended
                                      # on-demand run), NOT nightly - see §1.6.
security_ref: F-8bac0223                # the OPEN python:3.14.7-slim "newer upstream tag" row; detail stays in the DB
capability_change: false                # same-behaviour runtime for unchanged scripts; no new feature, route,
                                        # permission, API or exposure
rollback_class: git-revert              # nothing forward-only: no PVC, no schema, no persisted state from the bump
finding_refs: [F-8bac0223, F-691c4827, F-e716fd93, F-1e43e578, F-237bd599]   # re-queried 2026-10-23 (`finding list --grep`):
                                        # image security row F-8bac0223 (still open, title names 3.14.7), the three CURRENT
                                        # per-consumer version rows (openclaw-probe / mcpo / mealie-shopping-sync, all
                                        # "3.14.8-slim -> 3.15.0-slim (minor)", last seen 2026-10-21), and the ops-retro
                                        # deny-glob proposal. The old 3.14.7->3.14.8 rows (F-12279835, F-f78e1e01, F-959b2979)
                                        # are RESOLVED and dropped.
premises:
  # All read-only. Re-measured live 2026-10-25: all three PASS on 3.14.9-slim (3.14.8 also accepted).
  - id: probe-on-3.14.8
    why: >-
      `current:` claims the CronJob runs python:3.14.8-slim or 3.14.9-slim (3.14.9 was applied then auto-reverted by a
      false health-gate revert on 2026-10-23, §1.4, and may legitimately re-land via Step 0). Anything else means the
      fleet moved (3.15 already applied or an unknown tag - this plan is stale) or the
      file changed shape (the §3 sed would not match).
    run: kubectl get cronjob openclaw-probe -n ai -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_matches: '^python:3\.14\.[89]-slim$'
  - id: mcpo-init-on-3.14.8
    why: >-
      The python image is the mcpo initContainer `runtime-setup`, not the app container
      (ghcr.io/open-webui/mcpo). A different first init or strategy means the values shape moved.
    run: kubectl get deploy mcpo -n ai -o jsonpath='{.spec.template.spec.initContainers[0].name}={.spec.template.spec.initContainers[0].image} {.spec.strategy.type}'
    expect_matches: '^runtime-setup=python:3\.14\.[89]-slim Recreate$'
  - id: mealie-sync-on-3.14.8
    why: "Third member of the coverage group."
    run: kubectl get cronjob mealie-shopping-sync -n office -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_matches: '^python:3\.14\.[89]-slim$'
  # The registry facts (target still trixie; past the 48 h minor cooldown) cannot be premises:
  # plan-premises.py allows only kubectl/flux/helm/git/text-filter stages. They are §2 gates
  # 2.1/2.2, each printing a STOP token on failure.
review: ready-for-go@2026-10-25   # plan-reviewer 2026-10-25 delta re-review: premises PASS, gates verified
status: vetted
window: "sat-attended:2026-11-14"   # cooldown (re-pushed tag) ends 2026-10-26T08:08Z, so any start before that prints YOUNG; 11-14 is clear of cilium 10-25, openclaw 10-31, talos 11-01, otel 11-07, envoy 11-08
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-13"
refreshed: "2026-10-25"             # review corrections 2026-10-25: 3.15.1-slim re-pushed (digest 533b0b2f...), 3.14.9 re-landed, gates hardened (§2.1-2.3)
---

# python-fleet-3.15.0 - python:3.14.x-slim -> 3.15.1-slim on openclaw-probe, mcpo (init), mealie-shopping-sync

## 1. Summary & why held

One commit moves three inline `python:*-slim` pins from `3.14.x-slim` (3.14.9 live) to
`3.15.1-slim`:

| Consumer | Object | What python does there | File |
|---|---|---|---|
| ai/openclaw-probe | CronJob `*/30` | runs `probe.py` (stdlib `json`, `os`, `time`, `urllib.request`): TTS health check, POSTs fire/resolve of `OpenClawVoiceProviderDown` to Alertmanager | `kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml` |
| ai/mcpo | Deployment `mcpo`, **initContainer `runtime-setup`** | build environment only: `apt-get` nodesource `node_20`, `pip install uv`, `npm install -g` three node MCP servers into the `/shared` emptyDir, copies `node`, `uv`, `uvx` to `/shared/bin`. The **app container `ghcr.io/open-webui/mcpo:git-44ce6d0` is NOT changed**; no interpreter from this image reaches it. | `kubernetes/apps/ai/mcpo/app/helmrelease.yaml` |
| office/mealie-shopping-sync | CronJob `*/5` | runs `sync.py` (stdlib `json`, `os`, `sys`, `urllib.error`, `urllib.request`, `datetime`): Mealie -> HA shopping list | `kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml` (script in `shopping-sync-configmap.yaml`) |

### 1.1 What actually holds each member (the coverage `reason` is misleading)

The group's reason text, *"held at 2026.6.11 pending the Memory Core->SQLite
migration (2026.7.1 blocked)"*, is the reason of the FIRST member only. It is
**not** a property of the python image. Measured with `runbooks/coverage.py --json`
on 2026-10-13 against `runbooks/auto-update-policy.yaml` version `2026.10.12`:

- **openclaw-probe** - held by `match: "*openclaw*"` (policy line ~409, no `max:`),
  whose reason belongs to the OpenClaw APP image. It matches only because the
  component key `openclaw-probe` contains the substring `openclaw`. The probe is a
  stdlib script with no OpenClaw code and no coupling to the OpenClaw version.
  **Misattribution** (already recorded on `F-237bd599`).
- **mcpo** - held by `match: "*mcpo*"` (line ~273, no `max:`), reason *"python init
  base image major (3.11->3.14) rides these tags."* That move executed in
  `39fa6625` (2026-09-13); the rule's premise is spent but, with no `max:`, it holds
  every mcpo update. **Stale rule.**
- **mealie-shopping-sync** - no deny rule. Held by **G3** (breaking-change signal
  in release notes): the matched text is the What's New boilerplate
  *"Migration/Upgrade Guide ... pyperformance benchmark suite report a 7-8%
  geometric mean"* - a performance paragraph, not a breaking change. A
  **G3 false positive** on the wording, although the conclusion "a Python minor
  deserves a plan" is right for other reasons (§1.2). It would also be held by G5
  (48 h minor cooldown; tag first seen 2026-10-12 23:10 UTC).

Note for the operator: the policy narrowing proposed on `F-237bd599`
(`*mcpo*` and a new `*openclaw-probe*` rule at `max: patch`) would **not** release
this bump - it is a minor. So this plan stays necessary even if that lands.

### 1.2 Upstream: what 3.15 changes that could matter here

Python 3.15.0 was released 2026-10-09 (docs.python.org/3.15 What's New); the
Docker Official `3.15.1-slim` tag was published 2026-10-12. Interpreter-level
changes checked against each consumer:

- **UTF-8 mode is now the default (PEP 686):** *"Python now uses UTF-8 as the
  default encoding, independent of the system's environment ... This only
  applies when no `encoding` argument is given."* None of the scripts open
  files; all bytes are decoded via `.decode()` (UTF-8 already). No effect.
- **Removed in 3.15** (full list read): `ast` constructor strictness,
  `collections.abc.ByteString` from `__all__`, `ctypes.SetPointerType`,
  `datetime.strptime` with `%d` but no year, `glob.glob0/glob1`,
  `http.server.CGIHTTPRequestHandler`, `Loader.load_module`,
  `importlib.resources.files(package=)`, `PurePath.is_reserved`,
  `platform.java_ver`, `sre_*`, `sysconfig.is_python_build(check_home)`,
  `RLock` extra args, `co_lnotab`, `typing.ByteString`/kw-`NamedTuple`/
  `no_type_check_decorator`, `wave` marks, `zipimporter.load_module`.
  **None is used** by either script (they use `urllib.request.urlopen`,
  `json`, `time.strftime/gmtime`, `datetime.now(timezone.utc).isoformat()`).
- **Porting section:** sqlite3 keyword-only args, `resource.RLIM_INFINITY`,
  `mmap.resize`, `iterparse` ResourceWarning, argparse `dest` inference,
  `base64.urlsafe_b64decode` padding, unittest warnings. None applies.
- **urllib / http.client / ssl:** only additions (`max_response_headers`,
  new `ssl` group/sigalg APIs, `urllib.parse` keyword params). No default
  changes to `urlopen`, HTTP or TLS behaviour.
- **mcpo init:** `pip` still ships in the image (pip 26.2.1 under
  `/usr/local/lib/python3.15/site-packages`, measured by `trivy --list-all-pkgs`),
  `uv` publishes only `py3-none` wheels (interpreter-independent, PyPI 0.13.0),
  and the binaries the init copies (`/usr/bin/node`, `/usr/local/bin/uv`,
  `/usr/local/bin/uvx`) live at the same paths. No CPython wheel is built.
- **Base OS:** `3.15.1-slim` digest == `3.15.1-slim-trixie` digest (Docker Hub, re-measured 2026-10-25 after the tag was
  RE-PUSHED on 2026-10-24T08:08Z: both `sha256:533b0b2f9b5d46fd097091cf826f27902f1d6c3bca714b6dc74551356aa97a51`,
  amd64 manifest `sha256:b23bb42e5298...`; the 2026-10-23 digest was `08275f76...`). Trivy reports the image as Debian 13.7, same as
  3.14.9-slim. Same distribution as 3.14.x-slim, so
  the nodesource `nodistro` repo and apt flow are unchanged. (3.15 dropped the
  riscv64 platform from the manifest; we run amd64 only.)

### 1.3 Evidence gathered (dry tests)

- Both scripts were extracted from their ConfigMaps and `compile()`d under
  CPython **3.15.0b2** with `-W error` (the 3.15.0 final build is not yet
  available to uv on macOS), and every stdlib call they make
  (`datetime.now(timezone.utc).isoformat()`, `time.strftime(...gmtime())`,
  `"%g" % x`, the imports) was executed: clean, `sys.flags.utf8_mode == 1`.
  This is a beta, so the in-cluster gates in §4 remain the real proof.
- Security side: Trivy RE-RUN 2026-10-25 on the re-pushed digest `533b0b2f...` (`--severity HIGH,CRITICAL --ignore-unfixed`):
  `python:3.15.1-slim` shows 0 OS-package and 4 bundled-Python-package rows, identical in count to `python:3.14.9-slim` (0 / 4)
  - **no security gain from taking the minor over the patch**. Detail stays on the DB record (`F-8bac0223`), not here.
- The earlier dry-compile (CPython 3.15.0b2, `-W error`) is from 2026-10-13 and STALE for the final build: `uv python list`
  on 2026-10-25 still offers only 3.15.0b2 on macOS, so it could not be re-run against 3.15.1. It still covers the API surface
  (3.15.1 is bugfix-only); the in-cluster gates in §4 are the proof.
- Python 3.15.1 changelog (docs.python.org/3.15/whatsnew/changelog.html, read 2026-10-23): bugfix-only (interpreter/JIT/
  REPL crash fixes, no API removals, no default changes touching `urllib`/`json`/`ssl`/`datetime`/`time`). The beta
  dry-compile above therefore still stands for the API surface; the final-build proof is the in-cluster gates in §4.

### 1.4 Baseline history: 3.14.8 executed, 3.14.9 reverted then re-landed

- **Update 2026-10-25: 3.14.9 HAS RE-LANDED.** Renovate #420 (`b8b55656`) merged `3.14.8 -> 3.14.9` again after the false-positive
  revert below; live and in git today all three members and all 14 siblings read `3.14.9-slim` (3 alpine consumers `3.14.9-alpine`).
  Baseline is therefore 3.14.9 in practice; 3.14.8 stays accepted by the premises and seds in case of another revert.
- `python-fleet-3.14.8` **executed 2026-10-13** (`5c92657d`, Renovate #342) and its plan file was retired
  (`649f99ee`). Live and in git on 2026-10-23: all three members and the 14 siblings read `python:3.14.8-slim`.
  This plan was written against 3.14.7 and is re-based here; its old "mutually exclusive with python-fleet-3.14.8"
  premise is gone because that plan no longer exists.
- **3.14.9 was applied and auto-reverted on 2026-10-23 - by the automation, not by a defect.** At 13:21-13:22 +0200 the
  Step 0 safe-update apply merged six Renovate PRs (python slim #397 `77427c92`, 17 files incl. these three; python alpine
  #393 `e561dd11`; node #394; alpine-linux #390; cloudflared #399; falco #400 - renovate-bot commits about 14 s apart).
  At 13:28:17 the post-apply health gate reverted all six in one second (`9a78145c`, `ee6ac777`, `5df52355`, `d6a0d2a2`,
  `b3e0f213`, `9208e0ce`). The revert was a FALSE positive: concurrent commit traffic made Flux report "dependency
  revision not up to date", which the gate read as regression. **No python-specific defect is recorded anywhere** (no
  failing probe, issue or finding). (An earlier draft of this plan called the merge a manual operator merge; the coordinator
  corrected that.) Consequence: **3.14.9 may legitimately re-land via a later Step 0, so the baseline is 3.14.8 OR 3.14.9**
  (§2.0, premises and the sed all accept either) and the rollback restores whatever tag was live before the change (§5).
- **Target retargeted 3.15.0 -> 3.15.1.** `python:3.15.1-slim` is on Docker Hub (`last_updated` 2026-10-22T08:09Z) and
  Renovate/coverage already track it (PR #354; coverage group id now `python-fleet-3.15.1`). The earlier draft said
  "if a 3.15.1 exists, STOP and retarget - an x.1 is strictly preferable": that condition is now true, so the plan is
  retargeted rather than stopped. **The tag was re-pushed 2026-10-24T08:08Z** (digest now `533b0b2f...`), which restarts the 48 h minor
  cooldown (policy `minimum_release_age_hours`): it lapses **2026-10-26T08:08Z** (§2.2 gates it, §2.1 prints the digest so a further
  re-push is visible). The 2026-11-14 slot is far past it; a later re-push moves the date again, which is why §2.2 is re-run in-window.

### 1.5 Fleet scope - DECIDED: the three members only (canary), the other 14 follow

The same `python:3.14.x-slim` string appears on 14 further consumers (recounted in git 2026-10-25 with
`grep -rIl 'python:3\.14\.[0-9]*-slim' kubernetes`: 17 files total minus these 3 = ai/ollama-toolfix, download/tube-archivist
{image,metadata}-sync = 2, 11 media/library-tools objects = 14; a reviewer's count of 15 did not reproduce) plus 3 `3.14.x-alpine` consumers
(backup/icloud-backup-freshness, kube-system/crash-ghost-reaper, monitoring/elasticsearch obs-recovery; different string, different
base: untouched). **Decision: this plan edits ONLY openclaw-probe, mcpo init and mealie-shopping-sync**, because (a) they are the
coverage group `python-fleet-3.15.1` this plan covers and have per-consumer §4 gates measured live; (b) they span the three
distinct shapes (a probe that POSTs to Alertmanager, a pip/npm build init, an HTTP-to-HA sync), so they are a representative
canary for the interpreter move; (c) the 14 siblings are mostly NFS/CIFS-mounted media tooling with no gate written, two files are owned by
other plans, and changing 17 files in one commit makes a partial rollback (§5) coarse.
**Follow-up:** after this plan passes AND soaks one full day (>= one nightly), the 14 sibling `3.14.x-slim` consumers move to
3.15.1-slim as a second step - by the direct-bump lane if the policy lets minors through, else as a second fleet plan
(file it then; this plan does not pre-write it). The 14 stay on 3.14.x meanwhile; mixed 3.14/3.15 across independent
CronJobs is harmless (no shared state or wheels). F-8bac0223 therefore stays OPEN after this plan.

### 1.6 Slot - attended sat/sun, not nightly

A 3.14 -> 3.15 move is a minor interpreter change on a Recreate-strategy tool server (mcpo, ~90 s outage for openclaw's
MCP calls). The plan declares `autonomy_override: human-gated`: stamped **`sat-attended:2026-11-14`** (90 min vs est 35),
or an attended on-demand run once the 48 h cooldown has lapsed (2026-10-26T08:08Z: an earlier start would print
YOUNG in §2.2). 11-14 is clear of cilium 10-25, openclaw 10-31, talos 11-01, otel 11-07 and envoy 11-08. Not `nightly`: the three gates in §4 need a human to
read the openclaw-probe tick and the mcpo tool counts, and the 03:30 slot overlaps Step 0 safe-update churn that confounds
attribution. Reboot not needed, so Saturday suffices.

**Verdict:** risk `low`, honest residual = interpreter-minor regressions on a one-day-old bugfix release; a false-positive
hold on the image for two members and a correct-in-effect but wrongly-worded hold for the third (§1.1).

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). All read-only.

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py python-fleet-3.15.0      # every premise must PASS

# 2.0 the three files are on the 3.14.x baseline (3.14.8 OR a re-landed 3.14.9, §1.4), nothing is on 3.15 yet.
#     Prints "ok 3 PRE=<tag>"; anything else => STOP and re-plan. PRE is the tag a rollback must restore (§5).
N=$(grep -c 'python:3\.14\.[89]-slim$\|tag: 3\.14\.[89]-slim$' kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml kubernetes/apps/ai/mcpo/app/helmrelease.yaml | awk -F: '{s+=$2} END{print s}')
PRE=$(grep -h -o '3\.14\.[89]-slim$' kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml kubernetes/apps/ai/mcpo/app/helmrelease.yaml | sort -u | tr '\n' ',')
[ "$N" = 3 ] && echo "ok $N PRE=$PRE" || echo "STOP baseline-moved N=$N"
#   PRE with two values (3.14.8,3.14.9,) = a partially re-landed fleet: still proceed, rollback is per-file (§5).

# 2.1 target still Debian trixie AND print the digest so a re-push is visible (§1.2: re-pushed 2026-10-24T08:08Z).
#     Prints "trixie sha256:..." ; DIFFERENT => STOP and re-plan. Expected 2026-10-25: trixie sha256:533b0b2f9b5d46fd...
#     A digest other than 533b0b2f... means the tag was re-pushed again: re-run 2.2 (cooldown restarts) and re-read §1.3.
python3 -c "import json,urllib.request as u;g=lambda t: json.load(u.urlopen('https://hub.docker.com/v2/repositories/library/python/tags/'+t))['digest'];a=g('3.15.1-slim');print('trixie' if a==g('3.15.1-slim-trixie') else 'DIFFERENT',a)"

# 2.2 past the 48 h MINOR cooldown (policy minimum_release_age_hours; patch-only override does not apply).
#     last_updated only ever moves later on a rebuild, so this errs conservative. Prints AGED; YOUNG => STOP.
#     Measured 2026-10-25: 3.15.1-slim last_updated 2026-10-24T08:08:38Z -> YOUNG until 2026-10-26T08:08Z, AGED after
#     (today it prints YOUNG - by design; the 2026-11-14 slot is far past it unless the tag is re-pushed again).
python3 -c "import json,urllib.request as u,datetime as d;t=json.load(u.urlopen('https://hub.docker.com/v2/repositories/library/python/tags/3.15.1-slim'))['last_updated'];a=(d.datetime.now(d.timezone.utc)-d.datetime.fromisoformat(t.replace('Z','+00:00'))).total_seconds()/3600;print('AGED' if a>=48 else 'YOUNG')"

# 2.3 no 3.15.2 yet? (if a 3.15.2-slim exists, STOP and retarget - a newer bugfix is strictly preferable; same
#     retarget-in-place rule as 3.15.0 -> 3.15.1). ABSENCE gate: only an HTTP 404 counts as "absent"; ANY other failure
#     (DNS, timeout, 429, 5xx) prints FETCH_FAILED, which is also a STOP - the old try/except-Exception form printed
#     ok on every failure and could not fail.
#     Measured 2026-10-25: 3.15.2-slim -> ok-no-3.15.2 ; KNOWN-BAD CONTROL (a tag that exists, 3.15.1-slim) ->
#     STOP-3.15.1-slim-exists-retarget ; unreachable network (https_proxy=http://127.0.0.1:9) -> FETCH_FAILED URLError.
#     To run the control, replace both 3.15.2-slim occurrences with 3.15.1-slim and the printed tag accordingly.
python3 -c "import urllib.request as u,urllib.error as e
try: u.urlopen('https://hub.docker.com/v2/repositories/library/python/tags/3.15.2-slim',timeout=15); print('STOP-3.15.2-exists-retarget')
except e.HTTPError as x: print('ok-no-3.15.2' if x.code==404 else 'FETCH_FAILED http %s'%x.code)
except Exception as x: print('FETCH_FAILED',type(x).__name__)"

# Flux owners healthy and on HEAD (all three Kustomizations live in the app namespace)
flux get kustomizations -n ai openclaw
flux get kustomizations -n ai mcpo
flux get kustomizations -n office mealie
flux get helmreleases -n ai mcpo                                         # Ready True

# Baseline: last runs of both CronJobs succeeded (re-record in-window; 2026-10-13 was 02:00:05Z / 02:10:04Z)
kubectl -n ai get cronjob openclaw-probe -o jsonpath='{.status.lastSuccessfulTime} {.status.lastScheduleTime}{"\n"}'
kubectl -n office get cronjob mealie-shopping-sync -o jsonpath='{.status.lastSuccessfulTime} {.status.lastScheduleTime}{"\n"}'

# NOTE: shell variables (N, PRE, PF, J, PUSH_TS) do NOT survive separate tool calls. Run each §2/§3/§4 block in ONE call,
#       or re-derive: PRE/N via 2.0, PUSH_TS via `export PUSH_TS=<the UTC time printed after git push>`.

# Baseline: the running init imageID (record it; it is the PRE-tag digest the §5 rollback returns to)
kubectl -n ai get pod -l app.kubernetes.io/name=mcpo -o jsonpath='{.items[0].status.initContainerStatuses[0].imageID}{"\n"}'

# Baseline: mcpo per-server tool counts (the §4.2 contents baseline) + negative control.
# Measured 2026-10-13 and re-measured 2026-10-23 (identical): context7=2 prometheus=10 alertmanager=9 kubernetes=14 github=26, nonexistent=404
kubectl -n ai port-forward svc/mcpo 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 3
for s in context7 prometheus alertmanager kubernetes github nonexistent; do
  printf '%s ' "$s"; curl -s -o /tmp/mcpo-$s.json -w '%{http_code} ' http://localhost:18000/$s/openapi.json
  python3 -c "import json;print(len(json.load(open('/tmp/mcpo-$s.json')).get('paths',{})))" 2>/dev/null || echo PARSE_FAIL
done
kill $PF 2>/dev/null
```

STOP if any premise fails, 2.0-2.3 print a STOP/YOUNG/DIFFERENT/FETCH_FAILED token, any Flux
object is not Ready, or a baseline server is non-200 (re-record first: §4.2
compares against what you record HERE, not the 2026-10-13 numbers - the init
pulls newest npm packages on every start).

## 3. Steps

```bash
cd /Users/mu/code/cberg-home-nextgen
git pull --rebase

# 3.1 the two CronJobs (BSD sed; dry-tested 2026-10-25 on scratch copies of the live 3.14.9 files)
sed -i '' 's|image: python:3\.14\.[89]-slim$|image: python:3.15.1-slim|' \
  kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml \
  kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml

# 3.2 the mcpo initContainer tag (the app container tag git-44ce6d0 is NOT touched; it has no '-slim')
sed -i '' 's|^\([[:space:]]*tag:[[:space:]]*\)3\.14\.[89]-slim$|\13.15.1-slim|' \
  kubernetes/apps/ai/mcpo/app/helmrelease.yaml

git diff --stat -- kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml \
  kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml \
  kubernetes/apps/ai/mcpo/app/helmrelease.yaml      # expect exactly 3 files, 3 insertions, 3 deletions
```

Dry-test result (scratch copies, 2026-10-25; the three files differ from the live 3.14.9 originals in exactly these lines):

```
openclaw-probe.yaml        95c95  <  image: python:3.14.9-slim   >  image: python:3.15.1-slim
shopping-sync-cronjob.yaml 48c48  <  image: python:3.14.9-slim   >  image: python:3.15.1-slim
helmrelease.yaml (mcpo)    47c47  <  tag: 3.14.9-slim            >  tag: 3.15.1-slim
```

`shopping-sync-cronjob.yaml` still contains `3.14.7-slim` once afterwards, in
the comment on line 45 ("already runs elsewhere") - expected; leave it.

```bash
# 3.3 write the message file FIRST, then commit ONLY these paths (shared worktree) and verify before pushing
MSG=$(mktemp /tmp/msg-python-fleet-315.XXXXXX)   # unique file (shared worktree)
cat > "$MSG" <<'EOF'
chore(deps): python 3.14.x-slim -> 3.15.1-slim on openclaw-probe, mcpo init, mealie-shopping-sync

Plan: runbooks/maintenance/plans/python-fleet-3.15.0.md (security_ref F-8bac0223)
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

Flux applies on the push webhook; no manual reconcile (SOP default). If nothing
has applied after 10 minutes, `flux get kustomizations -n ai openclaw` shows the
revision - escalate rather than force. Avoid pushing within 2 min before a
`:00`/`:30` tick so §4.1's "first job after push" is unambiguous.

## 4. Verification

Every gate compares against objects created AFTER `PUSH_TS` (exported in §3.3;
the python one-liners read it from the environment).

**4.0 Applied (floor).** Each live spec carries the new tag:

```bash
kubectl -n ai get cronjob openclaw-probe -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'          # python:3.15.1-slim
kubectl -n office get cronjob mealie-shopping-sync -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}' # python:3.15.1-slim
kubectl -n ai get deploy mcpo -o jsonpath='{.spec.template.spec.initContainers[0].image}{"\n"}'                                    # python:3.15.1-slim
```

Fails (prints the old `3.14.x-slim`) if Flux has not applied - wait/escalate; do not
judge 4.1-4.3 on old pods.

**4.1 openclaw-probe - CONTENTS: still measures TTS and still reaches
Alertmanager on 3.15** - first Job after `PUSH_TS`, against the baseline log
shape (re-measured 2026-10-23, job `openclaw-probe-29879550`: `local_tts_ok=True` + two `alertmanager POST 200`).

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
kubectl -n ai get pod -l job-name="$J" -o jsonpath='{.items[0].status.containerStatuses[0].image}{"\n"}'   # python:3.15.1-slim
kubectl -n ai logs job/"$J" | grep -ciE '^local_tts_ok=true$'               # 1
kubectl -n ai logs job/"$J" | grep -ciE '^alertmanager POST 200 '           # 2
```

PASS = succeeded 1, image 3.15.1-slim, `local_tts_ok=True` 1, `POST 200` 2.
Failure shapes: an import/syntax break leaves `succeeded` empty and a traceback
in the log; a urllib/TLS regression prints `tts health error:` +
`local_tts_ok=False` (first grep 0) and ALSO fires `OpenClawVoiceProviderDown`
critical (the user-visible symptom); an Alertmanager POST failure raises and
fails the Job. Caveat: `local_tts_ok=False` can also mean the Mac-mini TTS
server is down - curl its `/health` from the Mac before blaming the image.

**4.2 mcpo - CONTENTS: every MCP server still starts and exposes its tools.**

```bash
kubectl -n ai get pod -l app.kubernetes.io/name=mcpo -o jsonpath='{.items[0].status.startTime} {.items[0].status.initContainerStatuses[0].image} {.items[0].status.initContainerStatuses[0].state.terminated.exitCode}{"\n"}'
# startTime AFTER PUSH_TS; image python:3.15.1-slim; exitCode 0
kubectl -n ai wait --for=condition=Ready pod -l app.kubernetes.io/name=mcpo --timeout=600s
kubectl -n ai logs -l app.kubernetes.io/name=mcpo -c runtime-setup --tail=40 | grep -ciE 'Runtime setup complete'   # 1
kubectl -n ai port-forward svc/mcpo 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 3
for s in context7 prometheus alertmanager kubernetes github nonexistent; do
  printf '%s ' "$s"; curl -s -o /tmp/mcpo-$s.json -w '%{http_code} ' http://localhost:18000/$s/openapi.json
  python3 -c "import json;print(len(json.load(open('/tmp/mcpo-$s.json')).get('paths',{})))" 2>/dev/null || echo PARSE_FAIL
done
kill $PF 2>/dev/null
```

PASS = every real server `200` with paths >= the §2 baseline, and
`nonexistent 404` (negative control re-measured 2026-10-23: same counts 2/10/9/14/26, nonexistent 404; so a 404 on a real
name is a real failure, not a URL mistake). Failure shapes: `pip`/`uv` broken
on 3.15 -> init exits non-zero (`Init:Error`/`Init:CrashLoopBackOff`, Ready wait
times out, `Runtime setup complete` count 0); a broken `node`/`uvx` copy -> the
affected server is 404 or 0 paths. A drop on ONE npm server with the others
intact points at npm drift (the init pulls newest packages every start), not
python - see §5.

**4.3 mealie-shopping-sync - CONTENTS: still reads Mealie and Home Assistant** -
first Job after `PUSH_TS` (<=5 min), against baseline
`done: pushed=0 already-synced=143 excluded=0 lists=1` (re-measured 2026-10-23, job `mealie-shopping-sync-*` latest).

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

PASS = succeeded 1, HA read line present, `already-synced` non-zero (an empty
Mealie read prints `already-synced=0` and fails the regex; an HTTP/urllib break
exits 1 with `HTTP <code>:` on stderr and `succeeded` stays empty).

**Instruments (CONTROL lines)** - kube-state-metrics in the `kube-prometheus-stack`
Prometheus; selectors returned series on 2026-10-02 and an empty result for a
nonexistent job name (non-vacuous); the `assert r` below makes an empty answer
a failure.

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

Nothing forward-only happens: no PVC, no schema, no persisted state is written
by a base-image change (mcpo's `/shared` is an emptyDir rebuilt on every start;
the mealie sync's Mealie/HA writes are the job's normal behaviour and identical
on either interpreter). Rollback is a revert:

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-3.3>
git show --stat HEAD            # the same 3 files, tags back to the PRE tag(s) recorded in §2.0 (3.14.8 or 3.14.9)
git log -1 --format=%s          # Revert "chore(deps): python 3.14.x-slim -> 3.15.1-slim ..."
git push
```

Partial rollback is acceptable and preferable if only one member fails: restore
just that file's line (`git checkout <sha-of-3.3>~1 -- <file>`, commit with
`--only <file>`) and leave the others on 3.15.

Confirm back: the §4.0 commands print the pre-change `python:3.14.[89]-slim` (PRE from §2.0) for the reverted
member(s); mcpo pod `startTime` is after the revert push and §4.2 counts match
the §2 baseline; the next openclaw-probe / mealie Jobs pass §4.1/§4.3. If §4.2
failed because an npm package moved (one server down, init log clean), the
revert will NOT fix it - the reverted init re-pulls the same newest npm
packages; pin the offending package in the init script under a separate
plan/commit and say so in the window report. If `OpenClawVoiceProviderDown`
fired during a failed §4.1, it resolves on the next successful probe tick (the
probe POSTs `endsAt=now`); no manual Alertmanager action.

## 6. Interference notes

- **Retired/dead refs (2026-10-25):** `flux-distribution-2.9.6` (executed), `python-fleet-3.14.8` (executed; this plan is its successor, §1.4),
  `flux-fleet-0.60.0` (executed), `kube-prometheus-stack-92.2.0` (no kps plan is open; **if one is filed it must not
  share the night** - §4.1 asserts `POST 200` to Alertmanager and the CONTROL lines read Prometheus).
- **Flux plans** (`flux-oci-chart-sources`, `helm-drift-detection`)
  restart or rewrite the machinery that applies `helmrelease/mcpo`; serialize. `openclaw-2026.10.5` (blocked) shares the
  Flux Kustomization `ai/openclaw` with `cronjob/openclaw-probe`.
- **Renovate 3.14.9** (auto-reverted 2026-10-23, RE-LANDED 2026-10-25 via #420, §1.4): done; further x.y.z patches may still land via Step 0 before the slot. Fine: §2.0, the premises and the sed accept 3.14.8 or 3.14.9.
- **redis-fleet-8.10.2** (sun-attended:2026-11-29) restarts the redis behind ai/open-webui and office consumers; listed in
  `conflicts_with` for reciprocity. Different slots, so no clash as scheduled; never share a night.
- **ns ai neighbours:** other ai plans share the namespace only (no shared object, no shared Flux Kustomization); a
  same-window failure in `ai` is harder to attribute - prefer separate slots if the window is busy.
- **mcpo consumers:** openclaw reaches mcpo through `mcporter-config`; the
  ~90 s Recreate drops in-flight tool calls. Check no OpenClaw cron is due
  (morning briefing ~07:00) per `feedback_no_openclaw_roll_during_crons` -
  this plan does not roll openclaw itself.
- Not rolled: `deployment/openclaw`, `deployment/mealie`,
  `deployment/ollama-toolfix`.
- **Repo corrections owed (report; out of scope for this plan):**
  1. `*openclaw*` (no `max:`) catches `openclaw-probe` by substring and puts
     the OpenClaw app's Memory-Core reason on a stdlib python CronJob - this is
     the reason text coverage printed for this whole group. Tracked on
     `F-237bd599`; note its proposed `max: patch` fix would still hold minors
     like this one.
  2. `*mcpo*` reason is spent since `39fa6625` (2026-09-13).
  3. G3's breaking-change regex fires on CPython's What's New boilerplate
     ("Migration/Upgrade Guide", pyperformance paragraph) - a false-positive
     shape worth fixing at the audit-logic root (it will also hit the other 14
     slim consumers after cooldown).
  4. Unrelated but seen: the mcpo init installs nodesource `node_20.x`, which
     is past upstream EOL (April 2026) - a separate plan, not this one.
