---
plan_id: python-fleet-3.15.2
component: python                     # image fleet keyed on the Docker Official Image `python` (slim)
supersedes: python-fleet-3.15.0       # carried forward 2026-10-27 (sweep 3f978ad9 rule 4d0): same job, newer bugfix
                                      # (3.15.1 -> 3.15.2). README prefers refresh-in-place; the coordinator asked for a
                                      # new file, so finding_refs + cross-refs are carried by hand (§6).
also_covers: [openclaw-probe, mcpo, mealie-shopping-sync]
pr: null                              # direct-bump lane (coverage.py needs_plan_groups group python-fleet-3.15.2) - no Renovate PR
kind: image
current: "python:3.14.x-slim (3.14.10 live and in git 2026-11-02, Renovate #442 / 72308883 of 2026-10-28; any 3.14.N accepted) on 3 PLAN-lane consumers (ai/openclaw-probe CronJob, ai/mcpo initContainer runtime-setup, office/mealie-shopping-sync CronJob)"
target: "python:3.15.2-slim (recorded index digest sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0, §2.1) on the same 3 consumers (one commit)"
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
                                        # the MCP tool server consumed by openclaw (ConfigMap openclaw-mcp-servers,
                                        # file mcporter-config.yaml) and falco
    - cronjob/mealie-shopping-sync      # office - Flux Kustomization office/mealie; deployment/mealie untouched
  shared: [monitoring]                  # §4 reads Prometheus (kube-state-metrics) AND openclaw-probe POSTs to
                                        # Alertmanager - both are the window's instruments. No gateway/envoy,
                                        # DNS, CNI, storage or Authentik surface: none of the three has an
                                        # HTTPRoute, a PVC or an SSO path.
depends_on: []
conflicts_with:
  # 2026-11-03: dropped `mealie-3.30.0` (plan retired/never existed; DEAD-REF in maintenance-plan.py --validate)
  # Carried from python-fleet-3.15.0; re-checked 2026-11-02 against runbooks/maintenance/plans/ (the four entries
  # below all exist and are non-terminal: redis-fleet-8.10.3 draft, openclaw-2026.10.5 blocked, helm-drift-detection
  # vetted, flux-oci-chart-sources vetted).
  # 2026-11-02 (review needs-fix): REMOVED `nextcloud-9.4.1` - a dead ref (maintenance-plan.py DEAD-REF); only
  # nextcloud-9.4.0 exists and it is superseded (folded into nextcloud-fleet-35.0.1). Its stated purpose (an
  # office-wide silence hiding a failing mealie-shopping-sync) is covered by the §6 Alertmanager note; no live plan
  # replaces it. The open nextcloud-mcp-* plans are blocked/window null and touch no shared silence.
  # No kube-prometheus-stack plan is open (no kps-bump file in the plan dir, 2026-11-02); if one is filed, add it:
  # §4 reads Prometheus and §4.1 asserts Alertmanager POST 200, a same-night kps bump blinds both gates.
  - redis-fleet-8.10.3                  # reciprocity: restarts redis for office/ consumers (sun-attended:2026-11-29). Successor of
                                        # redis-fleet-8.10.2 (superseded concurrently 2026-10-27, same sweep); lists this plan back.
  - openclaw-2026.10.5                  # same Flux Kustomization ai/openclaw as cronjob/openclaw-probe; currently blocked
  - helm-drift-detection                # adds spec.driftDetection to every HR incl. helmrelease/mcpo (sat-attended:2026-11-07)
  - flux-oci-chart-sources              # rewrites HelmRelease chart sources (bjw-s app-template consumers incl. mcpo)
exclusive: false
autonomy_override: human-gated        # RESTRICTS only (carried from the 2026-10-23 review): a minor interpreter move is
                                      # an attended window item, not nightly - see §1.6.
security_ref: F-2abb920e                # CURRENT image row for python:3.14.10-slim (AR-029 accepted, last seen 2026-11-02); detail stays in the DB.
                                        # 2026-11-02: was F-8bac0223, a python:3.14.7-slim row (last seen 2026-10-17) for a tag
                                        # nothing runs any more - dropped (it is also not in finding_refs below).
capability_change: false                # same-behaviour runtime for unchanged scripts; no new feature, route,
                                        # permission, API or exposure
rollback_class: git-revert              # nothing forward-only: no PVC, no schema, no persisted state from the bump
finding_refs: [F-a9351f4e, F-691c4827, F-e716fd93, F-1e43e578, F-237bd599]   # re-queried 2026-11-02 (`finding list --grep python`):
                                        # the three CURRENT per-consumer version rows - openclaw-probe F-691c4827 / mcpo
                                        # F-e716fd93 / mealie-shopping-sync F-1e43e578, all titled "3.14.10-slim -> 3.15.2-slim
                                        # (minor)", last seen 2026-11-02 - the ops-retro deny-glob proposal F-237bd599, and
                                        # F-a9351f4e (plan section, new 2026-11-02): coverage.py's fleet group id drops the tag
                                        # variant, so the alpine trio and 15 slim siblings READ as covered by this plan though
                                        # it excludes them (§1.5). F-8bac0223 (python:3.14.7-slim row) dropped: stale.
premises:
  # All read-only. Measured live 2026-11-02: all three PASS on 3.14.10-slim (they FAILED on the 2026-10-27 [89] regex
  # once Renovate #442 moved the baseline; that is the intended STOP, fixed here by accepting any 3.14.N).
  - id: probe-on-3.14.x
    why: >-
      `current:` claims the CronJob runs python:3.14.N-slim (3.14.10 on 2026-11-02). Anything else means the fleet moved
      (3.15 already applied or an unknown tag - this plan is stale) or the file changed shape (the §3 sed would not match).
    run: kubectl get cronjob openclaw-probe -n ai -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_matches: '^python:3\.14\.[0-9]+-slim$'
  - id: mcpo-init-on-3.14.x
    why: >-
      The python image is the mcpo initContainer `runtime-setup`, not the app container
      (ghcr.io/open-webui/mcpo). A different first init or strategy means the values shape moved.
    run: kubectl get deploy mcpo -n ai -o jsonpath='{.spec.template.spec.initContainers[0].name}={.spec.template.spec.initContainers[0].image} {.spec.strategy.type}'
    expect_matches: '^runtime-setup=python:3\.14\.[0-9]+-slim Recreate$'
  - id: mealie-sync-on-3.14.x
    why: "Third member of the coverage group."
    run: kubectl get cronjob mealie-shopping-sync -n office -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_matches: '^python:3\.14\.[0-9]+-slim$'
  # The registry facts (target still trixie; past the 48 h minor cooldown; no newer bugfix) are §2 gates
  # 2.1-2.3, each printing a STOP token on failure - they need curl/python network reads, kept out of premises.
review: ready-for-go@2026-11-02          # plan-reviewer 2026-11-02: ready-for-go, 0 blocking; nits applied (PY_SHA capture, pushed=0 + imageID digest gate, severity wording); HUMAN-GATED, fresh operator GO on this plan_id
status: vetted                          # was draft. 2026-11-02: revised after an
                                        # independent review (needs-fix) - baseline 3.14.10, re-pushed 3.15.2 digest, dead
                                        # conflicts_with ref, finding_refs; the earlier GO does NOT carry over (§1.7).
window: "sat-attended:2026-11-14"       # suggestion only (the window agent assigns it). 35 of the 70 schedulable min (90 - 20 Step 0
                                        # reserve), alone in the slot (re-grepped `^window:` 2026-11-02; every other plan naming
                                        # 2026-11-14 does so in prose with window null or superseded). Cooldown on 3.15.2-slim:
                                        # last_updated 2026-11-02T05:08:22Z -> lapses 2026-11-04T05:08Z, far before the slot.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-27"                 # revised 2026-11-02 (review needs-fix); frontmatter keys unchanged
---

# python-fleet-3.15.2 - python:3.14.x-slim -> 3.15.2-slim on openclaw-probe, mcpo (init), mealie-shopping-sync

## 1. Summary & why held

This plan replaces `python-fleet-3.15.0` (vetted for 3.15.1, now `superseded`). The job is the same. Only the
bugfix target moved: Docker Official `python:3.15.2-slim` was first published 2026-10-27T02:15Z. The old plan's §2.3
says that when a newer bugfix exists you STOP and retarget, and that condition was true then.

**Revised 2026-11-02 after an independent review (needs-fix).** Two things moved under the 2026-10-27 draft:
the 3.14 baseline (Renovate #442, commit `72308883`, 2026-10-28: `3.14.9 -> 3.14.10`, so all three members now read
`3.14.10-slim` and the original `[89]` premises/sed no longer matched) and the `3.15.2-slim` tag itself, which was
re-pushed (§1.2). Both are fixed below; §1.7 states what that does to the earlier approval.

One commit moves three inline `python:*-slim` pins from `3.14.x-slim` (3.14.10 live) to `3.15.2-slim`:

| Consumer | Object | What python does there | File |
|---|---|---|---|
| ai/openclaw-probe | CronJob `*/30` | runs `probe.py` (stdlib `json`, `os`, `time`, `urllib.request`): TTS health check, POSTs fire/resolve of `OpenClawVoiceProviderDown` to Alertmanager (`http://kube-prometheus-stack-alertmanager.monitoring.svc:9093`) | `kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml` |
| ai/mcpo | Deployment `mcpo`, **initContainer `runtime-setup`** | build environment only: `apt-get` nodesource `node_20`, `pip install uv`, `npm install -g` three node MCP servers into the `/shared` emptyDir, copies `node`, `uv`, `uvx` to `/shared/bin`. The **app container `ghcr.io/open-webui/mcpo:git-44ce6d0` is NOT changed**. | `kubernetes/apps/ai/mcpo/app/helmrelease.yaml` |
| office/mealie-shopping-sync | CronJob `*/5` | runs `sync.py` (stdlib `json`, `os`, `sys`, `urllib.error`, `urllib.request`, `datetime`): Mealie (`http://mealie.office:9000`) -> HA (`http://home-assistant.home-automation:8123`) shopping list | `kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml` (script in `shopping-sync-configmap.yaml`) |

### 1.1 What actually holds each member (the coverage `reason` is mis-attributed)

The group's dispatch reason, *"held at 2026.6.11 pending the Memory Core->SQLite migration (2026.7.1 blocked)"*,
is the reason of the FIRST member only. It is **not** a property of the python image. I re-measured this on
2026-10-27 with `runbooks/coverage.py --json` (`needs_plan[]`) against `runbooks/auto-update-policy.yaml`
version `2026.10.26` (not re-run on 2026-11-02; the policy file's `*openclaw*` / `*mcpo*` rules and line numbers
are as of that run):

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
  G5 (48 h minor cooldown; measured from the tag's `last_updated`, which is now 2026-11-02T05:08:22Z, so the
  cooldown lapses 2026-11-04T05:08Z - see §1.2).

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

**Image facts (RE-MEASURED 2026-11-02 against the Docker Hub API and Trivy; the 2026-10-27 values are superseded):**

- **The tag was re-pushed after this plan was first written.** On 2026-10-27 `3.15.2-slim` pointed at index digest
  `sha256:197f6622a70b...` (amd64 `7ce16513bf93...`). Docker hub now shows the amd64 platform manifest re-pushed
  2026-10-28T05:06Z and the index re-pushed 2026-11-02T05:08Z (a `riscv64` entry was added). The Trivy / Debian /
  pip facts the first draft quoted were measured on the OLD digest and are re-done below.
- `3.15.2-slim` digest == `3.15.2-slim-trixie` digest ==
  `sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0` (**the recorded digest, `REC` in §2.1**)
- amd64 manifest: `sha256:3053ea19f29305df68292b41291d621e0cbc9c1c826822c631713891ea0b64e9`
- `last_updated`: `2026-11-02T05:08:22Z` -> the 48 h minor cooldown (§2.2) lapses **2026-11-04T05:08Z**. (The amd64
  content itself has been stable since 2026-10-28T05:06Z, but the gate and the auto-updater read `last_updated`,
  so this plan follows the tag.) Any further re-push restarts the clock again.
- `3.15.3-slim`: HTTP 404 (re-measured 2026-11-02), so 3.15.2 is newest.
- Trivy 0.76.1 (mise pin) on the new digest reports Debian **13.7**, the same base as `3.14.10-slim`
  (digest `sha256:3cabfd7d7aaf...`, scanned side by side: identical OS-package and lang-package result). So the
  nodesource `nodistro` apt flow is unchanged.
- pip **26.2.2** is still bundled at `/usr/local/lib/python3.15/site-packages` (Trivy package list on the new digest).

### 1.3 Evidence gathered (dry tests)

- **Security side:** a Trivy 0.76.1 scan of the CURRENT `python:3.15.2-slim` digest `8c13a3f3...` (2026-11-02) shows
  the same result as `python:3.14.10-slim` scanned in the same run, so taking the minor brings **no security gain**
  for the image scan. Counts and detail stay on the DB record (`F-2abb920e`, the AR-029 row for 3.14.10-slim),
  not here (docs/sops/vulnerability-disclosure.md).
- **Script compatibility:** the 3.15.0 plan's dry-compile of both scripts was under CPython 3.15.0b2 with
  `-W error`, plus execution of every stdlib call they make. It still covers the API surface, because 3.15.1
  and 3.15.2 are bugfix-only. It was not re-run against a final build, because uv on macOS still lacks one.
  The in-cluster gates in §4 are the proof.
- **sed dry test (2026-11-02, BSD sed on macOS):** run on scratch copies of the live 3.14.10 files with the widened
  `3\.14\.[0-9]*` patterns, the edits change exactly these lines and nothing else (§3).

### 1.4 History and baseline

- `python-fleet-3.14.8` executed on 2026-10-13.
- 3.14.9 was applied on 2026-10-23, then auto-reverted by a false-positive health gate. It re-landed via
  Renovate #420 (`b8b55656`) on 2026-10-25.
- **3.14.10 landed via Renovate #442 (`72308883`, 2026-10-28).** Live and in git on 2026-11-02 (HEAD `4fee010d`,
  Flux Kustomizations `ai/openclaw`, `ai/mcpo`, `office/mealie` Ready at that revision), all three members read
  `3.14.10-slim`. The 2026-10-27 draft predicted this exact case in its §6 ("a 3.14.10 landing would make the
  premises FAIL ... widen the regexes"); it came true and all three premises and the §2.0 count did FAIL. The
  premises, §2.0 and the §3 sed now accept ANY `3.14.N` (`[0-9]+` in Python `re` / `[0-9]*` in BSD sed), so a
  further 3.14 patch before the slot does not stale the plan again; `PRE` (§2.0) records whichever tag a rollback
  must restore.
- `python-fleet-3.15.0` was reviewed `ready-for-go@2026-10-25` and slotted for `sat-attended:2026-11-14` with
  target 3.15.1. It is now superseded by this file. What changed is §1.2 / §1.3 (new image facts and
  changelog), §2.1-2.3 (digest, cooldown and next-bugfix gates retargeted), and every `3.15.1` in §3 and §4.
  Steps, gates, rollback and conflicts are otherwise carried over unchanged.

### 1.5 Fleet scope: the three members only (canary); 18 siblings are NOT covered

This plan edits **ONLY openclaw-probe, the mcpo init and mealie-shopping-sync** (`also_covers` lists exactly
these three). They are the coverage group, they have measured per-consumer gates, and they span three distinct
shapes (Alertmanager probe, pip/npm build init, HTTP-to-HA sync).

**The following 18 consumers are NOT covered by this plan** (re-grepped in `kubernetes/` 2026-11-02, all on
`3.14.10`):

- **15 `python:3.14.10-slim` siblings:** ai/ollama-toolfix (1), download/tube-archivist image-sync and
  metadata-sync (2), media/library-tools (12 objects: 11 CronJobs plus the `dashboard` Deployment).
- **3 `python:3.14.10-alpine` consumers** (a different tag variant and base; two of them are digest-pinned
  `@sha256:...`, so their bump must also move the digest): backup/icloud-backup-freshness `icloud-sync-probe`,
  kube-system/crash-ghost-reaper, monitoring/elasticsearch `elasticsearch-obs-recovery`. Their version rows are
  `3.14.10-alpine -> 3.15.2-alpine`: **F-6bf5a0aa** (icloud-sync-probe), **F-302480e4** (crash-ghost-reaper),
  **F-eb7756e8** (elasticsearch-obs-recovery).

**Why this needs saying: `coverage.py` reports them as covered when they are not (F-a9351f4e, new 2026-11-02).**
The image-fleet group id drops the tag variant, so `python 3.15.2-alpine` and `python 3.15.2-slim` collide into
one group. Any tool or reader that joins by component + target version will therefore show the alpine trio and
the 15 slim siblings as "planned by python-fleet-3.15.2", although this plan neither edits nor gates them. They
have no plan. F-a9351f4e is in `finding_refs` for that reason; the fix (variant in the group id; require
`also_covers`/`touches` membership for component+version matches) is a repo change outside this plan.

**Follow-up owner:** the next sweep's rule 4d0 dispatch (the coordinator), once the F-a9351f4e fix lands so the
siblings stop reading as covered. Their rows to close or plan against are the three alpine rows above plus the
slim siblings' own version rows (for example F-0be2a0b6 media-sidecar, F-21fb4456 ollama-toolfix, F-51ad9f3c
tube-archivist-image-sync). The intended path: once this plan passes and soaks for at least one nightly, the 15
slim siblings move to `3.15.2-slim` as a second step, and the alpine trio to `3.15.2-alpine` as a third. That
goes through the direct-bump lane if the policy lets minors through, otherwise through a second fleet plan,
filed at that point. Mixed 3.14/3.15 across independent CronJobs is harmless.

**Findings that stay OPEN after this plan:** the siblings' version rows above. The old image-security rows
`F-8bac0223` (`python:3.14.7-slim`, last seen 2026-10-17) and `F-f266fdf3` (`python:3.14.8-slim`, last seen
2026-10-27) describe tags nothing in `kubernetes/` runs any more and should be reconciled by the sweep, not
linked to this plan; the current image row is F-2abb920e (AR-029 accepted).

### 1.6 Slot: attended Saturday, not nightly

The suggested slot is **`sat-attended:2026-11-14`**: 35 min of the **70 schedulable minutes** (90 min window minus
the 20 min Step 0 reserve; `runbooks/maintenance-windows.yaml`), alone in the slot - re-grepped
`^window:` across `runbooks/maintenance/plans/` on 2026-11-02, no other plan holds it (the tube-archivist plans
mention 11-14 only in prose to say why they avoid it - 35 + 65 and 35 + 60 both exceed 70 - and
`redis-fleet-8.10.3` names it as the reciprocal `conflicts_with` entry). The cooldown
(§1.2, §2.2) lapses 2026-11-04T05:08Z, ten days before the slot, unless the tag is re-pushed again; §2.1/§2.2
catch that on the day.

Not `nightly`: the §4 gates need a human to read the openclaw-probe tick and the mcpo tool counts, and the
03:30 slot overlaps Step 0 safe-update churn. No reboot is needed.

**Verdict:** risk `low`. The honest residual is an interpreter minor on a bugfix release whose tag has already
been re-pushed once (§1.2) - which is why §2.1 pins the digest.

### 1.7 Approval status: the earlier GO does not carry over

The operator GO recorded for `python-fleet-3.15.0` (target `python:3.15.1-slim`, review
`ready-for-go@2026-10-25`) does **not** apply to this plan. That plan is `superseded`; its target tag no longer
exists as the thing being deployed; the `3.15.2-slim` tag has been re-pushed since this plan was first written; and
the baseline it was reviewed against (3.14.9) has changed to 3.14.10. After this revision passes review, a **fresh
`home-operation decide` on `python-fleet-3.15.2`** is needed before the window agent may run it. The plan stays
`draft` with review null until then.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). All read-only.

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py python-fleet-3.15.2      # every premise must PASS

# 2.0 the three files are on the 3.14.x baseline (ANY 3.14.N; 3.14.10 on 2026-11-02), nothing is on 3.15 yet.
#     Prints "ok 3 PRE=<tag>"; anything else => STOP and re-plan. PRE is the tag a rollback must restore (§5).
#     Uses `grep -E` on purpose: with the BRE alternation form (`...-slim$\|tag: ...-slim$`) macOS /usr/bin/grep treats
#     the first `$` as a literal (not an anchor before `\|`) and counts 0,0,1 on these very files => false STOP. Dry-run
#     2026-11-02 with /usr/bin/grep: BRE form 0 on openclaw-probe.yaml; ERE form below 1,1,1 (N=3). A member already
#     on 3.15 or a changed shape counts 0 for that file => STOP, as intended.
N=$(grep -cE 'python:3\.14\.[0-9]+-slim$|tag: 3\.14\.[0-9]+-slim$' kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml kubernetes/apps/ai/mcpo/app/helmrelease.yaml | awk -F: '{s+=$2} END{print s}')
PRE=$(grep -h -o -E '3\.14\.[0-9]+-slim$' kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml kubernetes/apps/ai/mcpo/app/helmrelease.yaml | sort -u | tr '\n' ',')
[ "$N" = 3 ] && echo "ok $N PRE=$PRE" || echo "STOP baseline-moved N=$N"
#   Measured 2026-11-02 on the live files, run under bash (real /usr/bin/grep) AND zsh (grep shell function): ok 3 PRE=3.14.10-slim,
#   (The 2026-10-27 draft's `[89]` form read "STOP baseline-moved N=0" on these same files.)

# 2.1 target still Debian trixie AND still the digest this plan was measured on (REC, recorded 2026-11-02).
#     Prints "ok-trixie-digest-matches sha256:..." => proceed.
#     Prints "STOP-DIGEST-CHANGED sha256:<new>"    => the tag was RE-PUSHED since the plan was measured (it already was
#       once, 2026-10-27 -> 2026-11-02): STOP; re-run 2.2 (cooldown restarts), re-run the §1.2 Trivy / Debian / pip
#       facts on the new digest, put the new digest into REC here and in §1.2, and have the plan re-reviewed.
#     Prints "STOP-NOT-TRIXIE ..." if slim and slim-trixie diverge (slim moved to a newer Debian).
#     Equality of slim vs slim-trixie alone cannot catch a re-push (both tags move together) - hence the REC compare.
#     Measured 2026-11-02: ok-trixie-digest-matches sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0
#     Known-bad control (REC set to the superseded 2026-10-27 digest sha256:197f6622a70b...): prints STOP-DIGEST-CHANGED.
REC=sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0
REC=$REC python3 -c "import json,os,urllib.request as u;g=lambda t: json.load(u.urlopen('https://hub.docker.com/v2/repositories/library/python/tags/'+t,timeout=20))['digest'];a=g('3.15.2-slim');b=g('3.15.2-slim-trixie');r=os.environ['REC'];print('STOP-NOT-TRIXIE' if a!=b else ('ok-trixie-digest-matches' if a==r else 'STOP-DIGEST-CHANGED'),a)"

# 2.2 past the 48 h MINOR cooldown (policy minimum_release_age_hours). Prints AGED; YOUNG => STOP.
#     Measured 2026-11-02: last_updated 2026-11-02T05:08:22Z -> YOUNG until 2026-11-04T05:08Z (by design today;
#     the 2026-11-14 slot is far past it unless the tag is re-pushed again - `last_updated` moved from
#     2026-10-27T02:15Z when the index was re-pushed, which is why this gate reads it live, not from the plan).
python3 -c "import json,urllib.request as u,datetime as d;t=json.load(u.urlopen('https://hub.docker.com/v2/repositories/library/python/tags/3.15.2-slim'))['last_updated'];a=(d.datetime.now(d.timezone.utc)-d.datetime.fromisoformat(t.replace('Z','+00:00'))).total_seconds()/3600;print('AGED' if a>=48 else 'YOUNG')"

# 2.3 no 3.15.3 yet? (if 3.15.3-slim exists, STOP and retarget - same carry-forward as 3.15.1 -> 3.15.2).
#     ABSENCE gate: only HTTP 404 counts as absent; any other failure prints FETCH_FAILED (also a STOP).
#     Measured 2026-11-02: 3.15.3-slim -> HTTP 404 (ok-no-3.15.3). KNOWN-BAD CONTROL: substitute 3.15.2-slim
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
#   Re-checked 2026-11-02: kustomizations ai/openclaw, ai/mcpo, office/mealie all READY True at
#   refs/heads/main@sha1:4fee010d; helmrelease ai/mcpo READY True (app-template 5.3.0). A False/Unknown here is a STOP.

# Baseline: last runs of both CronJobs succeeded (re-record in-window)
kubectl -n ai get cronjob openclaw-probe -o jsonpath='{.status.lastSuccessfulTime} {.status.lastScheduleTime}{"\n"}'
kubectl -n office get cronjob mealie-shopping-sync -o jsonpath='{.status.lastSuccessfulTime} {.status.lastScheduleTime}{"\n"}'

# NOTE: shell variables (N, PRE, PF, J, PUSH_TS) do NOT survive separate tool calls. Run each §2/§3/§4 block in ONE call,
#       or re-derive: PRE/N via 2.0, PUSH_TS via `export PUSH_TS=<the UTC time printed after git push>`.

# Baseline: the running init imageID (record it; it is the PRE-tag digest the §5 rollback returns to)
kubectl -n ai get pod -l app.kubernetes.io/name=mcpo -o jsonpath='{.items[0].status.initContainerStatuses[0].imageID}{"\n"}'

# Baseline: mcpo per-server tool counts (the §4.2 contents baseline) + negative control.
# Measured 2026-10-13 and 2026-10-23 (identical; NOT re-measured 2026-11-02 - the mcpo pod is up on 3.14.10 since
# 2026-10-28T02:33Z, its init log reads 'Runtime setup complete' once; the port-forward counts are re-recorded in-window): context7=2 prometheus=10 alertmanager=9 kubernetes=14 github=26, nonexistent=404
kubectl -n ai port-forward svc/mcpo 18000:8000 >/dev/null 2>&1 & PF=$!; sleep 3
for s in context7 prometheus alertmanager kubernetes github nonexistent; do
  printf '%s ' "$s"; curl -s -o /tmp/mcpo-$s.json -w '%{http_code} ' http://localhost:18000/$s/openapi.json
  python3 -c "import json;print(len(json.load(open('/tmp/mcpo-$s.json')).get('paths',{})))" 2>/dev/null || echo PARSE_FAIL
done
kill $PF 2>/dev/null
```

STOP in any of these cases:

- any premise fails;
- 2.0-2.3 print any `STOP...` token (`STOP baseline-moved`, `STOP-DIGEST-CHANGED`, `STOP-NOT-TRIXIE`, `STOP-3.15.3-exists-retarget`), `YOUNG` or `FETCH_FAILED`;
- any Flux object is not Ready;
- a baseline server is non-200.

§4.2 compares against what you record HERE, not the historical numbers, because the init pulls the newest npm
packages on every start.

## 3. Steps

```bash
cd /Users/mu/code/cberg-home-nextgen
git pull --rebase

# 3.1 the two CronJobs (BSD sed; dry-tested 2026-11-02 on scratch copies of the live 3.14.10 files; any 3.14.N matches)
sed -i '' 's|image: python:3\.14\.[0-9]*-slim$|image: python:3.15.2-slim|' \
  kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml \
  kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml

# 3.2 the mcpo initContainer tag (the app container tag git-44ce6d0 is NOT touched; it has no '-slim')
sed -i '' 's|^\([[:space:]]*tag:[[:space:]]*\)3\.14\.[0-9]*-slim$|\13.15.2-slim|' \
  kubernetes/apps/ai/mcpo/app/helmrelease.yaml

git diff --stat -- kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml \
  kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml \
  kubernetes/apps/ai/mcpo/app/helmrelease.yaml      # expect exactly 3 files, 3 insertions, 3 deletions
```

Dry-test result (scratch copies, 2026-11-02, BSD sed; `diff -r` of the three scratch files against the originals
shows exactly 6 changed lines, 3 each side). Each of the three files differs from the live 3.14.10 original
in exactly this one line:

```
openclaw-probe.yaml        95c95  <  image: python:3.14.10-slim  >  image: python:3.15.2-slim
shopping-sync-cronjob.yaml 48c48  <  image: python:3.14.10-slim  >  image: python:3.15.2-slim
helmrelease.yaml (mcpo)    47c47  <  tag: 3.14.10-slim           >  tag: 3.15.2-slim
```

Afterwards, `shopping-sync-cronjob.yaml` still contains `3.14.7-slim` once, in a comment ("already runs
elsewhere"). That is expected: leave it.

```bash
# 3.3 write the message file FIRST, then commit ONLY these paths (shared worktree) and verify before pushing
MSG=$(mktemp /tmp/msg-python-fleet-3152.XXXXXX)   # unique file (shared worktree)
cat > "$MSG" <<'EOF'
chore(deps): python 3.14.x-slim -> 3.15.2-slim on openclaw-probe, mcpo init, mealie-shopping-sync

Plan: runbooks/maintenance/plans/python-fleet-3.15.2.md (security_ref F-2abb920e)
EOF
git commit --only \
  kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml \
  kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml \
  kubernetes/apps/ai/mcpo/app/helmrelease.yaml \
  -F "$MSG"
git show --stat HEAD            # exactly the 3 files above
git log -1 --format=%s          # must be the subject above; amend before push if not
export PY_SHA=$(git rev-parse HEAD)   # the commit section 5 reverts
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
`alertmanager POST 200` lines (re-measured 2026-11-02 on 3.14.10, job `openclaw-probe-29893350`: `succeeded` 1,
`local_tts_ok=True`, two `alertmanager POST 200 firing=False severity=...` lines - the greps below read 1 and 2 on it).

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
(the `143` was measured 2026-10-23; re-measured 2026-11-02 on 3.14.10, job `mealie-shopping-sync-29893375`:
`home assistant list holds 50 item(s)`, `done: pushed=0 already-synced=209 excluded=0 lists=1`. The count drifts with the
shopping list; the gate is `already-synced` non-zero, not the number).

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
kubectl -n office logs job/"$J" | grep -iE '^done: pushed=0 already-synced=[1-9][0-9]* '   # one line
kubectl -n office get pod -l job-name="$J" -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'   # must end @sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0 (the pre-change pod shows a different digest)
```

PASS = succeeded `1`, the HA read line is present, `pushed=0` (a duplicate push would fail the regex) and `already-synced` is non-zero, and the pod imageID is the pinned index digest.

Failure shapes:

- **Empty Mealie read:** prints `already-synced=0`, which fails the regex.
- **HTTP/urllib break:** the script exits 1 with `HTTP <code>:` on stderr and `succeeded` stays empty.

**Instruments (CONTROL lines).** These read kube-state-metrics in the `kube-prometheus-stack` Prometheus. The
`assert r` in the script below makes an empty answer a failure. Run the block in the SAME shell call where
`PUSH_TS` is exported (or re-export it first), because the first query is built from it.

CONTROL: metric kube_job_status_failed - `job_name=~"openclaw-probe.*|mealie-shopping-sync.*"` in ns ai/office,
restricted to Jobs created AFTER `PUSH_TS` (joined to `kube_job_created > PUSH_EPOCH`; the bare metric reads every
retained Job, including pre-push ones, so it could neither show the new Jobs nor fail on them): every printed value
`=0`. A `=1` is a failed post-push Job. An EMPTY RESULT means no post-push Job has been scraped yet (wait one
scrape interval and one cron tick, then rerun), and is itself a failed gate, never a pass.
CONTROL: metric kube_deployment_status_replicas_available - `{namespace="ai",deployment="mcpo"}` back to 1 within 10 min of the push (baseline 1). The printed name is the kube-state-metrics pod, not mcpo; read the value (`=1`). `=0` or EMPTY is a fail.
CONTROL: metric kube_pod_init_container_status_restarts_total - `{namespace="ai",container="runtime-setup"}` stays 0 on the new pod (an init crash loop shows here first). The printed name is the mcpo pod; `=0` passes, any higher value fails.

Dry-tested 2026-11-02 against the live Prometheus (PUSH_TS set two hours back): the three queries printed
`openclaw-probe-29893350=0, mealie-shopping-sync-29893370=0`, then `...=1`, then `mcpo-...=0`. Known-bad control with
`PUSH_TS=2099-01-01T00:00:00Z` (no Job can be newer): the first query raised `AssertionError: EMPTY RESULT`, so the
join cannot silently pass on an empty set.

```bash
PUSH_EPOCH=$(python3 -c "import os,datetime as d;print(int(d.datetime.strptime(os.environ['PUSH_TS'],'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=d.timezone.utc).timestamp()))")
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for q in "kube_job_status_failed{namespace=~\"ai|office\",job_name=~\"openclaw-probe.*|mealie-shopping-sync.*\"} and on(namespace,job_name) (kube_job_created > $PUSH_EPOCH)" \
         'kube_deployment_status_replicas_available{namespace="ai",deployment="mcpo"}' \
         'kube_pod_init_container_status_restarts_total{namespace="ai",container="runtime-setup"}'; do
  printf '%s => ' "${q:0:60}"; curl -s -G http://localhost:19090/api/v1/query --data-urlencode "query=$q" \
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
git revert --no-edit "$PY_SHA"
git show --stat HEAD            # the same 3 files, tags back to the PRE tag(s) recorded in §2.0 (whichever 3.14.N §2.0 printed as PRE, 3.14.10 on 2026-11-02)
git log -1 --format=%s          # Revert "chore(deps): python 3.14.x-slim -> 3.15.2-slim ..."
git push
```

If only one member fails, a partial rollback is acceptable and preferable. Restore just that file's line with
`git checkout "$PY_SHA"~1 -- <file>`, commit it with `--only <file>`, and leave the others on 3.15.

**Confirm the cluster is back:**

- The §4.0 commands print the pre-change `python:3.14.N-slim` (PRE from §2.0; `python:3.14.10-slim` on 2026-11-02) for each reverted member.
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
    review that produced it no longer applies (§1.7: a fresh `home-operation decide` on `python-fleet-3.15.2` is
    required after this revision is reviewed).
- **Flux plans** (`flux-oci-chart-sources` sun 11-22, `helm-drift-detection` sat 11-07) restart or rewrite the
  machinery that applies `helmrelease/mcpo`. Serialize with them. `openclaw-2026.10.5` (blocked) shares the
  Flux Kustomization `ai/openclaw` with `cronjob/openclaw-probe`.
- **No kube-prometheus-stack plan is open** (no kps-bump file in the plan dir, 2026-11-02). If one is filed, it
  must not share the night: §4.1 asserts `POST 200` to Alertmanager and the CONTROL lines read Prometheus.
  `shared: [monitoring]` in the frontmatter carries this; add the kps plan to `conflicts_with` when it exists.
- **Alertmanager silences in `office`.** The 2026-10-27 draft listed `nextcloud-9.4.1` as a conflict because an
  office-wide silence would hide a failing `mealie-shopping-sync` (`KubeJobFailed`). That plan id never existed
  (dead ref, removed), and no live plan replaces it. §4.3 and the CONTROL line read the Job and its metric directly,
  not an alert, so a silence cannot blind them; before the window, glance at active silences for the `office`
  namespace anyway.
- **Renovate x.y.z patches on 3.14** may still land via Step 0 before the slot. That is fine: §2.0, the
  premises and the sed accept ANY `3.14.N` (this is exactly what #442 / 3.14.10 did to the 2026-10-27 draft, whose
  `[89]` regexes failed on it). What would make the premises FAIL now is a member already on 3.15, a non-`-slim`
  tag or a changed file shape - the intended STOPs. Step 0 may also bump the three members to 3.15.x itself only
  if the policy ever lets a minor through; then this plan is moot and should be closed, not run.
- **redis-fleet-8.10.3** (sun-attended:2026-11-29) restarts the redis behind office/ consumers. It is
  in a different slot, so there is no clash as scheduled. Never put the two on the same night.
- **mcpo consumers:** openclaw reaches mcpo through ConfigMap `openclaw-mcp-servers` (file `mcporter-config.yaml`; there is no object named `mcporter-config`, checked live 2026-11-02), and the ~90 s Recreate drops in-flight
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
  5. `coverage.py` fleet group id drops the tag variant (`F-a9351f4e`): the alpine trio and 15 slim siblings read
     as covered by this plan (§1.5).
  6. Stale image-security rows `F-8bac0223` (3.14.7-slim) and `F-f266fdf3` (3.14.8-slim) describe
     tags nothing runs; they should be reconciled by the sweep, not worked from this plan.
