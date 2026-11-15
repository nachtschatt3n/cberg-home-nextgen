---
plan_id: python-fleet-3.15.2
component: python                     # image fleet keyed on the Docker Official Image `python` (slim)
supersedes: python-fleet-3.15.0       # see §1.1: that file is the 3-member CANARY plan (different members), already
                                      # status superseded; its `superseded_by: python-fleet-3.15.2` named an earlier
                                      # file of THIS id that executed 2026-11-06 and was retired in 316a07b1b.
                                      # This file REUSES the id for the 15 remaining slim consumers (step two).
also_covers: [ollama-toolfix, tube-archivist-image-sync, tube-archivist-nfo-sync, media-cleanup, media-cleanup-nfos, media-dashboard, media-episode-sidecar, media-intake-watcher, media-library-audit, media-metadata-coverage, media-organize, media-per-item-refresh, media-plex-fs-classifier, media-rescan, media-sidecar]
pr: null                              # direct-bump lane (coverage group python-fleet-3.15.2); no Renovate PR was named in the dispatch (not re-checked with gh, §7)
kind: image
current: "python:3.14.10-slim (tag only, no digest) on 15 consumers - ai/ollama-toolfix (Deployment), download/tube-archivist-image-sync + tube-archivist-nfo-sync (CronJobs), media/library-tools (11 CronJobs + Deployment media-dashboard); live and in git 2026-11-14 at HEAD 3fbded01b; any 3.14.N accepted"
target: "python:3.15.2-slim pinned tag@digest to the SAME index digest the canary trio already runs from git (2026-11-14: sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928, Docker Hub tag pushed 2026-11-07T23:08Z); §2.1 re-reads it from git, §3 pins what §2.1 read"
update_type: minor                    # CPython feature release 3.14 -> 3.15; same Debian 13 trixie base
risk: medium                          # Probability low: every script is stdlib-only (one runtime pip dep, pg8000, with a
                                      # built-in fallback), none uses an API removed in 3.15 (§1.3), and the same
                                      # digest has run 3 sibling consumers here since 2026-11-06. Rated medium for
                                      # BLAST RADIUS and for what was NOT proven: two active jobs (media-intake-watcher,
                                      # media-cleanup-nfos) and four suspended ones move/rename/delete files on a
                                      # read-write mount of the whole media export, and no member script was executed
                                      # on a 3.15 interpreter before this plan (§7). A file move is not undone by git.
est_duration_min: 60                  # pre-checks 8 · edit/commit/push 4 · Flux apply ~3 · two pod rolls ~3 ·
                                      # immediate gates 7 · wait for the :30 and :00 CronJob ticks (<=35) · tick gates 5.
                                      # Fits sat-attended (70 schedulable) only ALONE in the slot.
needs_reboot: false
touches:
  namespaces: [ai, download, media]
  resources:
    - deployment/ollama-toolfix         # ai - Flux Kustomization ai/openclaw (plain manifest ollama-toolfix.yaml); RollingUpdate, no PVC;
                                        # the Ollama proxy used by openclaw and oc8 (in-flight local-model requests are cut at the roll)
    - cronjob/tube-archivist-image-sync # download - Flux Kustomization download/tube-archivist
    - cronjob/tube-archivist-nfo-sync   # download - same Kustomization
    - deployment/media-dashboard        # media - Flux Kustomization media/library-tools; Recreate; ~1 min outage of the dashboard
    - cronjob/media-cleanup             # media - suspended (on-demand only)
    - cronjob/media-cleanup-nfos        # media - weekly Sun 04:30 UTC, WRITES to the media export
    - cronjob/media-episode-sidecar     # media - suspended
    - cronjob/media-intake-watcher      # media - every 30 min, WRITES to the media export
    - cronjob/media-library-audit       # media - daily; python container `audit` only, the `persist` postgres container is NOT edited
    - cronjob/media-metadata-coverage   # media - hourly, no PVC
    - cronjob/media-organize            # media - suspended
    - cronjob/media-per-item-refresh    # media - every 6 h, no PVC
    - cronjob/media-plex-fs-classifier  # media - daily, read-only mount
    - cronjob/media-rescan              # media - suspended, no PVC
    - cronjob/media-sidecar             # media - suspended
  shared: [monitoring, media, cifs-plex-media, cifs-tube-archivist-media]
                                        # monitoring: §4 CONTROL lines read kube-state-metrics in Prometheus.
                                        # media / cifs-plex-media: the jobs act on the shared media export (PVC plex-media-smb,
                                        # class cifs-plex-media, subdir `/`); the PVC, PV and StorageClass are NOT changed (§1.5).
                                        # No gateway/envoy, DNS, CNI, Longhorn or Authentik surface: the one HTTPRoute
                                        # (media-dashboard on envoy-internal) is not edited.
depends_on: []
conflicts_with:
  # Read every plan's frontmatter 2026-11-14; all six exist and are non-terminal. Reciprocity is NOT yet declared
  # on their side (this planner writes only this file) - see §6.
  - postgres-digest-refresh-2026-11     # edits the SAME file and CronJob (audit-cronjob.yaml / media-library-audit, `persist` image)
  - tube-archivist-0.6.0                # same Flux Kustomization download/tube-archivist; rewrites configmap/tube-archivist-image-sync
  - tube-archivist-elasticsearch-9.5.5  # same Kustomization; its §4.3 gate runs a job from cronjob/tube-archivist-nfo-sync
  - redis-fleet-8.10.3                  # restarts redis in download/media/ai; the sync jobs call the tube-archivist API mid-restart
  - media-naming-p3                     # renames library files through the same library-tools scripts; never under a same-night interpreter move
  - kube-prometheus-stack-93.3.0       # draft, exclusive, window null: restarts Prometheus, which this plan's gates read (retargeted 2026-11-16 from retired 92.22.0)
exclusive: false
autonomy_override: human-gated        # RESTRICTS only (carried from the canary plan's 2026-10-23 review): an interpreter
                                      # minor is an attended item, not nightly. §4 needs a human to read job logs.
security_ref: null                    # no security driver for this group. (The accepted image rows for the old and new tag exist
                                      # in the DB; detail stays there - docs/sops/vulnerability-disclosure.md.)
capability_change: false              # same scripts, same behaviour, newer runtime; no new feature, route, permission, API or exposure
rollback_class: git-revert            # the bump itself persists nothing. Caveat stated in §5: file operations a job performed
                                      # on the share while on 3.15 are not reverted by git.
finding_refs: [F-21fb4456, F-51ad9f3c, F-72f94c92, F-2dd44d16, F-615deabd, F-07a07562, F-003c2dfe, F-ef491aba, F-7b21d461, F-2c9e212c, F-45e20f90, F-2779235c, F-be43fadf, F-f63a9bdc, F-0be2a0b6]
                                      # queried 2026-11-14 (`policy-cli.py finding list --grep python`): the 15 per-consumer version rows,
                                      # all titled "<member>: image python 3.14.10-slim -> 3.15.2-slim (minor)", last seen 2026-11-14.
premises:
  - id: toolfix-on-3.14-rolling
    why: >-
      current claims the proxy runs python 3.14.N-slim as a RollingUpdate Deployment. Anything else means the fleet
      moved (plan stale) or the manifest changed shape (the §3 sed would not match).
    run: kubectl get deploy ollama-toolfix -n ai -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.strategy.type}'
    expect_matches: '^python:3\.14\.[0-9]+-slim RollingUpdate$'
  - id: intake-on-3.14
    why: "The every-30-min writer is the member whose first run on 3.15 is the main gate (§4.3); it must still be on 3.14."
    run: kubectl get cronjob media-intake-watcher -n media -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_matches: '^python:3\.14\.[0-9]+-slim$'
  - id: dashboard-on-3.14-recreate
    why: "The dashboard is the only member with a pip install at start; Recreate means one short outage, no surge pod."
    run: kubectl get deploy media-dashboard -n media -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.strategy.type}'
    expect_matches: '^python:3\.14\.[0-9]+-slim Recreate$'
  - id: nfo-sync-on-3.14
    why: "Representative of the two download-namespace members."
    run: kubectl get cronjob tube-archivist-nfo-sync -n download -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_matches: '^python:3\.14\.[0-9]+-slim$'
  - id: canary-still-on-3.15.2-pinned
    why: >-
      The plan pins the digest the canary (openclaw-probe) carries. If the canary moved off 3.15.2 (a 3.15.3 landed,
      or it was reverted) the target is stale - STOP and refresh this plan.
    run: kubectl get cronjob openclaw-probe -n ai -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_matches: '^python:3\.15\.2-slim@sha256:[0-9a-f]{64}$'
  - id: media-export-class-is-retain
    why: >-
      Six members mount PVC plex-media-smb (class cifs-plex-media, subdir /). This plan never touches the PVC; the
      premise records that the class is still Retain so nobody reads a PVC step into it (§1.5).
    run: kubectl get storageclass cifs-plex-media -o jsonpath='{.reclaimPolicy}'
    expect_exact: Retain
review: ready-for-go@2026-11-16      # plan-reviewer 2nd pass 2026-11-16: ready-for-go, 0 blocking (1st pass needs-fix: dead kps ref + placeholder FILES line; both fixed, path lists diffed identical, BSD sed dry-run on all 15). Advisory: 3.1 count guard only prints; make it an if-gate.
status: vetted
window: null                          # suggestion only (window agent assigns): sat-attended:2026-11-21 or sat-attended:2026-12-05 (prefer 12-05 if etcd still flaps), alone in the slot, see §1.6
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/storage-safety.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-14"
---

# python-fleet-3.15.2 - python:3.14.10-slim -> 3.15.2-slim on the 15 remaining slim consumers

## 1. Summary & why held

One commit changes one `image:` line in each of 15 manifests, from `python:3.14.10-slim` to
`python:3.15.2-slim@sha256:<digest>`. Nothing else changes: no script, no ConfigMap, no schedule, no volume.

| Namespace | Object | Schedule / shape | Storage it mounts | File under `kubernetes/apps/` |
|---|---|---|---|---|
| ai | Deployment `ollama-toolfix` | 1 replica, RollingUpdate | none (script ConfigMap) | `ai/openclaw/app/ollama-toolfix.yaml` |
| download | CronJob `tube-archivist-image-sync` | hourly :30 | `tube-archivist-youtube` RW | `download/tube-archivist/app/image-sync-cronjob.yaml` |
| download | CronJob `tube-archivist-nfo-sync` | hourly :00 | `tube-archivist-youtube` RW | `download/tube-archivist/app/metadata-sync-cronjob.yaml` |
| media | Deployment `media-dashboard` | 1 replica, Recreate | `jdownloader-intake` RO | `media/library-tools/app/dashboard-deployment.yaml` |
| media | CronJob `media-intake-watcher` | every 30 min (Berlin) | `plex-media-smb` **RW** | `.../intake-cronjob.yaml` |
| media | CronJob `media-cleanup-nfos` | Sun 04:30 UTC | `plex-media-smb` **RW** | `.../cleanup-nfos-cronjob.yaml` |
| media | CronJob `media-library-audit` | daily 01:45 Berlin | `plex-media-smb` RO | `.../audit-cronjob.yaml` |
| media | CronJob `media-plex-fs-classifier` | daily 01:35 Berlin | `plex-media-smb` RO | `.../plex-fs-classifier-cronjob.yaml` |
| media | CronJob `media-metadata-coverage` | hourly :00 | none | `.../coverage-cronjob.yaml` |
| media | CronJob `media-per-item-refresh` | every 6 h | none | `.../per-item-refresh-cronjob.yaml` |
| media | CronJob `media-rescan` | suspended (on demand) | none | `.../rescan-cronjob.yaml` |
| media | CronJobs `media-cleanup`, `media-organize`, `media-sidecar`, `media-episode-sidecar` | suspended (on demand) | `plex-media-smb` **RW** | `.../cleanup-`, `organize-`, `sidecar-`, `episode-sidecar-cronjob.yaml` |

The member list was confirmed against the repo on 2026-11-14: a grep for `python:3.14` under `kubernetes/` returns
exactly these 15 lines, and the live objects show the same 15 on `python:3.14.10-slim`. `media-library-audit` also
lists `postgres` because its second container (`persist`) runs a postgres image; this plan does not touch that line.

### 1.1 Relation to the earlier plans (read this before trusting the id)

- `python-fleet-3.15.0.md` is **not** an older plan for these 15. It covers three other consumers (openclaw-probe,
  the mcpo init container, mealie-shopping-sync) and is already `status: superseded`. It is left untouched.
- Those three were moved by an earlier file that also had the id `python-fleet-3.15.2`. It executed in the on-demand
  run of 2026-11-06 (commit `39b41f3a9`) and the file was retired in `316a07b1b`. Its §1.5 named these 15 as
  "not covered, second step after a soak".
- This file is that second step and **reuses the id** because the coverage group is keyed that way. A reader of
  `python-fleet-3.15.0`'s `superseded_by:` lands here; the members differ. The three alpine consumers were already
  moved to `3.15.2-alpine` and are out of scope.

Carried forward from the retired plan because it is still valid: the upstream reading (§1.2), the digest-pin
approach, the BSD-sed form, and the two kube-state-metrics controls. Not carried: its per-consumer gates (different
consumers) and its registry cooldown gates (the tag is now seven days old and the digest is taken from git, §2.1).

### 1.2 Why held, and what upstream changed

Held by the breaking-change gate: the 3.15 What's New page contains a migration/porting section. That is a property
of every CPython minor, so the hold is correct in kind even though nothing in it applies here (§1.3).

From `docs.python.org/3.15/whatsnew/3.15.html` (read 2026-11-14; "Python 3.15 was released on 9 October 2026"):

- **UTF-8 default (PEP 686):** "Python now uses UTF-8 as the default encoding, independent of the system's
  environment. ... This only applies when no `encoding` argument is given."
- **Removed:** `ast` constructor leniency; `collections.abc.ByteString` / `typing.ByteString` from `__all__`;
  `ctypes.SetPointerType()`; `datetime.strptime()` "now raises `ValueError` when the format string contains `%d`
  (day of month) without a year directive"; `glob.glob0()` / `glob1()`; "the `CGIHTTPRequestHandler` class and
  the `--cgi` flag"; `Loader.load_module()`; `importlib.resources.files(package=)`;
  `pathlib.PurePath.is_reserved()`; `platform.java_ver()`; the `sre_compile`, `sre_constants`, `sre_parse`
  modules; `sysconfig.is_python_build(check_home=)`; extra arguments to `threading.RLock`; `co_lnotab`;
  keyword-argument `NamedTuple`, zero-field `TypedDict("TD")`, `typing.no_type_check_decorator`; `wave` marks;
  `zipimporter.load_module()`.
- **Porting to Python 3.15:** keyword-only `sqlite3.connect()` parameters; `resource.RLIM_INFINITY` sign;
  `mmap.resize()`; a `ResourceWarning` for an unclosed `xml.etree.ElementTree.iterparse()`; `argparse` dest
  inference for `-f, -foo`; "Padding of input no longer required in `base64.urlsafe_b64decode()`";
  `unittest.assertWarns`.
- **http.server:** "The logging of `BaseHTTPRequestHandler`, as used by the command-line interface, is colored by
  default."
- **3.15.2** (changelog, "Python 3.15.2 final", release date 2026-10-25): bugfix and security release. Its Security
  entries concern `http.cookiejar` cookie-policy checks, `tarfile.tar_filter()` and an `ssl` key denylist. The
  Library section of that changelog was not readable in full (page truncated, §7).

### 1.3 What that means for these scripts (the real question)

All member scripts live in four ConfigMaps (`library-tools-scripts`, `media-dashboard`,
`tube-archivist-image-sync`, `tube-archivist-nfo-sync`) plus `ollama-toolfix-script`. Their imports, grepped from
the manifests on 2026-11-14:

- **Stdlib only:** `json`, `os`, `sys`, `time`, `re`, `datetime`, `hashlib`, `shutil`, `subprocess`, `socket`,
  `ssl`, `base64`, `collections`, `pathlib`, `html`, `urllib.request/error/parse`, `http.cookiejar`,
  `http.server`, `xml.etree.ElementTree`, and the local module `common`.
- **One third-party package:** `media-dashboard` runs `pip install --target /pylib pg8000==1.31.5` at container
  start. PyPI metadata: `requires_python >=3.9`, dependencies `python-dateutil` and `scramp` (pure Python). The
  install is deliberately non-fatal: on failure the dashboard logs `WARN: pip install pg8000 failed` and falls back
  to pod logs. That fallback is exactly why §4.2 asserts page contents, not readiness.

Checked against the removals and porting notes above:

| Change | Used by a member? |
|---|---|
| Removed modules / functions (list in §1.2) | No. No `strptime`, `glob`, `sre_*`, `is_reserved`, `load_module`, `ByteString`, `NamedTuple`, `wave`, `sqlite3`, `argparse`, `mmap`, `resource` in any script. |
| `CGIHTTPRequestHandler` | No. `ollama-toolfix` and `media-dashboard` use `BaseHTTPRequestHandler` (+ `ThreadingHTTPServer` / `HTTPServer`), which stay. |
| Colored `http.server` logging | No effect: both handlers override `log_message` (one prints its own line, one is silent). |
| `iterparse` ResourceWarning | No. Scripts use `ET.parse`, `ET.fromstring`, `ET.indent`, `ElementTree.write`. |
| `base64.urlsafe_b64decode` padding | No. Only `base64.b64encode` (nfo-sync basic auth). |
| UTF-8 default | Several text reads/writes pass no `encoding` (`read_text()`, `write_text()`, `open("a")` in `intake.py`, the service-account token in `dashboard.py`). The official image sets a UTF-8 locale, so the default encoding was already UTF-8 on 3.14 and the bytes written do not change. This rests on the image's `LANG`, which was not re-read from the image config (§7). |
| Deprecated, still present | `datetime.utcnow()` and `utcfromtimestamp()` in `dashboard.py` (deprecated since 3.12, not removed in 3.15); they warn only if warnings are enabled. Worth fixing in the script later; not part of this plan. |
| 3.15.2 `http.cookiejar` fix | `tube-archivist-image-sync` uses a `CookieJar` for a session login against the in-cluster tube-archivist API. The fix ignores cookies with a negative `Version`; an ordinary session cookie is unaffected. §4.4 is the gate. |

`ffprobe` / `ffmpeg` are called by name through `subprocess`; they are not in the `python:*-slim` image on either
version, so that code path is unchanged by this bump (it fails or is skipped today exactly as it will after).

**Evidence from this cluster:** the same image digest has run `openclaw-probe` (every 30 min),
`mealie-shopping-sync` (every 5 min) and the mcpo init container (which runs `pip`) since 2026-11-06, with last
successful runs at 02:00Z / 02:05Z on 2026-11-14. That covers `urllib.request`, `json`, `datetime` and `pip` on
3.15.2. It does **not** cover `http.server`, `xml.etree`, `shutil`/`pathlib` file moves, or `subprocess`.

### 1.4 Verdict

No breaking change applies to these scripts on the evidence read. The hold is a false positive in substance but
the plan is still warranted: a minor interpreter move under jobs that move and delete library files should be
watched by a human once. `risk: medium` for the reasons in the frontmatter.

### 1.5 Storage safety: image tags only

- This plan changes **image tags only**. It does not create, delete, recreate, resize or re-bind any PVC, PV or
  StorageClass, and no step may be extended to do so. `docs/sops/storage-safety.md` applies to anything beyond
  that and is out of scope here.
- Measured 2026-11-14: `media/plex-media-smb` -> class `cifs-plex-media`, `subdir=/`, reclaim `Retain`
  (catastrophic tier: the root of the media export); `download/tube-archivist-youtube` ->
  `cifs-tube-archivist-media`, `subdir=/tube-archivist`, `Retain`; `media/jdownloader-intake` ->
  `cifs-jdownloader-media`, `subdir=/jdownloader`, `Retain`.
- A CronJob spec change does not touch a mounted volume; `smb.csi.k8s.io` has no attach step, so the two
  Deployment rolls cannot block on a volume either.
- If a job fails after the bump, the remedy is §5 (revert the tag). Never "tear down the Job and its PVC".

### 1.6 Slot

Suggested (re-dated 2026-11-16): an attended Saturday (`sat-attended`, 09:00 Berlin, 70 schedulable minutes), alone
in the slot, with the push placed between **:05 and :20** past the hour (§3.3 explains why). Candidates:
`sat-attended:2026-11-21` (free) or `sat-attended:2026-12-05` (free). `sat-attended:2026-11-28` is already taken.
etcd is flapping as of 2026-11-16 and `talos-linux-1.14.5` holds `sun-attended:2026-11-22`; if etcd is not
settled by 11-21, prefer 12-05 - this plan needs a quiet control plane for Flux to apply and for the §4 reads, and
should not sit the day before a node roll it could be confused with. Not nightly: 03:30 overlaps Step 0 churn and
nobody reads the first writer run.
`ollama-toolfix` carries local-model traffic for openclaw and oc8; check no openclaw cron is mid-run before the
push (§2.4).

## 2. Pre-checks

Run from the repo root on the Mac mini. All read-only. Shell variables do not survive separate tool calls; run
each block in one call.

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py python-fleet-3.15.2 --require-premises   # every premise PASS

# 2.0 all 15 files are on a 3.14.N-slim tag. Prints "ok 15 PRE=3.14.10-slim,"; anything else => STOP.
#     Measured 2026-11-14: N=15.
FILES=(kubernetes/apps/ai/openclaw/app/ollama-toolfix.yaml
  kubernetes/apps/download/tube-archivist/app/image-sync-cronjob.yaml
  kubernetes/apps/download/tube-archivist/app/metadata-sync-cronjob.yaml
  kubernetes/apps/media/library-tools/app/audit-cronjob.yaml
  kubernetes/apps/media/library-tools/app/cleanup-cronjob.yaml
  kubernetes/apps/media/library-tools/app/cleanup-nfos-cronjob.yaml
  kubernetes/apps/media/library-tools/app/coverage-cronjob.yaml
  kubernetes/apps/media/library-tools/app/dashboard-deployment.yaml
  kubernetes/apps/media/library-tools/app/episode-sidecar-cronjob.yaml
  kubernetes/apps/media/library-tools/app/intake-cronjob.yaml
  kubernetes/apps/media/library-tools/app/organize-cronjob.yaml
  kubernetes/apps/media/library-tools/app/per-item-refresh-cronjob.yaml
  kubernetes/apps/media/library-tools/app/plex-fs-classifier-cronjob.yaml
  kubernetes/apps/media/library-tools/app/rescan-cronjob.yaml
  kubernetes/apps/media/library-tools/app/sidecar-cronjob.yaml)
N=$(grep -cE 'image: python:3\.14\.[0-9]+-slim$' "${FILES[@]}" | awk -F: '{s+=$2} END{print s}')
PRE=$(grep -h -o -E '3\.14\.[0-9]+-slim$' "${FILES[@]}" | sort -u | tr '\n' ',')
[ "$N" = 15 ] && echo "ok $N PRE=$PRE" || echo "STOP baseline-moved N=$N"

# 2.1 the digest to pin = the one the canary trio carries in git. Prints "DIG=sha256:<64 hex>" when all three
#     canary lines agree; "STOP-CANARY-DIGEST ..." otherwise (a Renovate digest PR half-landed, or the canary moved).
#     Measured 2026-11-14: DIG=sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928
D=$(grep -h -o -E '3\.15\.2-slim@sha256:[0-9a-f]{64}' kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml kubernetes/apps/ai/mcpo/app/helmrelease.yaml | sort -u)
[ "$(echo "$D" | grep -c sha256)" = 1 ] && echo "DIG=${D#*@}" || echo "STOP-CANARY-DIGEST [$D]"

# 2.2 that digest is what a canary pod really runs (proves it is pullable here). Must print the DIG from 2.1.
kubectl get pods -n office -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].imageID}{"\n"}{end}' | grep mealie-shopping-sync | tail -1

# 2.3 Flux owners Ready on HEAD (measured 2026-11-14: all three True at 3fbded01)
flux get kustomizations -n ai openclaw
flux get kustomizations -n download tube-archivist
flux get kustomizations -n media library-tools

# 2.4 nothing mid-flight that the toolfix roll would cut, and no media job running
kubectl get jobs -n ai -o wide | grep -v Complete
kubectl get jobs -n media -o wide | grep -v Complete
kubectl get jobs -n download -o wide | grep -v Complete

# 2.5 BASELINES to compare §4 against (record the printed values in the window log)
kubectl logs -n media deploy/media-dashboard --tail=500 | grep -ci 'WARN: pip install'          # 0 on 2026-11-14
J=$(kubectl get jobs -n download --sort-by=.metadata.creationTimestamp -o name | grep nfo-sync | tail -1); kubectl logs -n download "$J" --tail=1
#   2026-11-14: "Sync completed. Processed <N> videos across <M> channels."  -> record N and M
J=$(kubectl get jobs -n download --sort-by=.metadata.creationTimestamp -o name | grep image-sync | tail -1); kubectl logs -n download "$J" --tail=1
#   2026-11-14: "Done. copied=0  skipped(existing)=<K>  source-missing/404=0"  -> record K
J=$(kubectl get jobs -n media --sort-by=.metadata.creationTimestamp -o name | grep media-intake-watcher | tail -1); kubectl logs -n media "$J" --tail=1
#   2026-11-16 (job media-intake-watcher-29913060): a JSON line with "event": "intake-done", "actions": {} (EMPTY:
#   no file moved), "items" whose "failed" value equals 0, "rescanned": 0 -> record whether actions is empty
kubectl port-forward -n ai deploy/ollama-toolfix 18080:8080 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -m 5 http://localhost:18080/healthz; echo
curl -s -m 20 http://localhost:18080/api/tags | python3 -c "import sys,json; print('models', len(json.load(sys.stdin)['models']))" || echo PARSE_FAIL
kill $PF 2>/dev/null
#   expect "ok" then "models <n>" with n >= 1 -> record n. (The /api/tags baseline was NOT measured by the planner, §7.)
```

STOP if: any premise fails; 2.0 or 2.1 prints a `STOP` token; 2.2 prints a different digest or nothing; a Flux
object is not Ready; a job is Running in 2.4 (wait for it); the dashboard baseline is not 0 (the fallback is
already active - fix that first, otherwise §4.2 cannot distinguish old damage from new); `/api/tags` prints
`PARSE_FAIL` (the Ollama host is down - §4.1 would then be blind).

## 3. Steps

```bash
cd /Users/mu/code/cberg-home-nextgen
git pull --rebase

# 3.1 re-derive FILES (the array from 2.0) and DIG (2.1) in THIS call, then edit. BSD sed; dry-tested 2026-11-14.
#     The 15 paths below are byte-identical to §2.0 (checked 2026-11-16 by diffing the two lists; all 15 exist,
#     each with exactly one `image: python:3.14` line). If you change one list, change both.
FILES=(kubernetes/apps/ai/openclaw/app/ollama-toolfix.yaml
  kubernetes/apps/download/tube-archivist/app/image-sync-cronjob.yaml
  kubernetes/apps/download/tube-archivist/app/metadata-sync-cronjob.yaml
  kubernetes/apps/media/library-tools/app/audit-cronjob.yaml
  kubernetes/apps/media/library-tools/app/cleanup-cronjob.yaml
  kubernetes/apps/media/library-tools/app/cleanup-nfos-cronjob.yaml
  kubernetes/apps/media/library-tools/app/coverage-cronjob.yaml
  kubernetes/apps/media/library-tools/app/dashboard-deployment.yaml
  kubernetes/apps/media/library-tools/app/episode-sidecar-cronjob.yaml
  kubernetes/apps/media/library-tools/app/intake-cronjob.yaml
  kubernetes/apps/media/library-tools/app/organize-cronjob.yaml
  kubernetes/apps/media/library-tools/app/per-item-refresh-cronjob.yaml
  kubernetes/apps/media/library-tools/app/plex-fs-classifier-cronjob.yaml
  kubernetes/apps/media/library-tools/app/rescan-cronjob.yaml
  kubernetes/apps/media/library-tools/app/sidecar-cronjob.yaml)
[ "${#FILES[@]}" = 15 ] || echo "STOP files-array-count=${#FILES[@]}"
D=$(grep -h -o -E '3\.15\.2-slim@sha256:[0-9a-f]{64}' kubernetes/apps/ai/openclaw/app/openclaw-probe.yaml kubernetes/apps/office/mealie/app/shopping-sync-cronjob.yaml kubernetes/apps/ai/mcpo/app/helmrelease.yaml | sort -u)
if [ "$(echo "$D" | grep -c sha256)" = 1 ]; then
  DIG=${D#*@}
  sed -i '' "s|image: python:3\.14\.[0-9]*-slim\$|image: python:3.15.2-slim@${DIG}|" "${FILES[@]}"
  grep -c "image: python:3.15.2-slim@${DIG}\$" "${FILES[@]}"       # every line must end :1
  git diff --stat -- "${FILES[@]}" | tail -1                       # 15 files changed, 15 insertions(+), 15 deletions(-)
else
  echo "STOP-CANARY-DIGEST [$D]   (nothing edited)"
fi
```

Dry-test result (scratch copies of the 15 live files, BSD sed on macOS, 2026-11-14, DIG as measured in §2.1):
each scratch file differs from its original in exactly one line, for example

```
intake-cronjob.yaml   55c55  <  image: python:3.14.10-slim  >  image: python:3.15.2-slim@sha256:65a65fc7...bc36928
audit-cronjob.yaml    58c58  <  image: python:3.14.10-slim  >  image: python:3.15.2-slim@sha256:65a65fc7...bc36928
```

and the `postgres:18.6-alpine@sha256:...` line in `audit-cronjob.yaml` is unchanged (still 1 occurrence).
A `:0` from the `grep -c` means a sed did not match: STOP and `git checkout -- "${FILES[@]}"`.

```bash
# 3.2 message file first, then commit ONLY these 15 paths (shared worktree), verify, and hold the push for 3.3
MSG=$(mktemp /tmp/msg-python-fleet-3152.XXXXXX)
cat > "$MSG" <<'EOF'
chore(deps): python 3.14.10-slim -> 3.15.2-slim (digest-pinned) on 15 slim consumers (ai, download, media)

Plan: runbooks/maintenance/plans/python-fleet-3.15.2.md
EOF
git commit --only "${FILES[@]}" -F "$MSG"
git show --stat HEAD | tail -3      # exactly the 15 files
git log -1 --format=%s              # must be the subject above; amend before pushing if it is not
```

```bash
# 3.3 PUSH BETWEEN :05 AND :20 PAST THE HOUR, then record the time.
date -u +%M                          # 05..20 => push now; otherwise wait
git push
export PUSH_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "PUSH_TS=$PUSH_TS"
```

Why the timing: Flux applies within about 2 minutes of the push. The two Deployments roll at once and are
gated first (§4.1, §4.2). Those gates exercise `http.server`, `urllib` and `pip` on the new image **before** the
:30 tick starts the first writer (`media-intake-watcher`). If §4.1 or §4.2 fails, revert (§5) before :28 so the
writer never runs on 3.15. No manual `flux reconcile` (SOP default); if nothing has applied after 10 minutes, read
`flux get kustomizations -n media library-tools` and escalate rather than force.

## 4. Verification

Compare only against pods and jobs created after `PUSH_TS`. `DIG` is the digest from §2.1.

**4.0 Applied (floor).** All 15 live specs carry the new image.

```bash
kubectl get cronjob -n media -o jsonpath='{range .items[*]}{.metadata.name} {.spec.jobTemplate.spec.template.spec.containers[*].image}{"\n"}{end}' | grep -c 'python:3.15.2-slim@sha256'   # 11
kubectl get cronjob -n download -o jsonpath='{range .items[*]}{.metadata.name} {.spec.jobTemplate.spec.template.spec.containers[*].image}{"\n"}{end}' | grep -c 'python:3.15.2-slim@sha256' # 2
kubectl get deploy ollama-toolfix -n ai -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl get deploy media-dashboard -n media -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Fails by printing a lower count (measured before the change: 0 and 0) or the old `python:3.14.10-slim`. Then Flux
has not applied: wait, do not judge the gates below on old pods.

**4.1 ollama-toolfix - CONTENTS ASSERTION: the proxy still forwards to Ollama.**

```bash
kubectl get pods -n ai -l app.kubernetes.io/name=ollama-toolfix -o jsonpath='{range .items[*]}{.metadata.name} {.status.startTime} {.status.containerStatuses[0].imageID} restarts={.status.containerStatuses[0].restartCount}{"\n"}{end}'
kubectl port-forward -n ai deploy/ollama-toolfix 18080:8080 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -m 5 http://localhost:18080/healthz; echo
curl -s -m 20 http://localhost:18080/api/tags | python3 -c "import sys,json; print('models', len(json.load(sys.stdin)['models']))" || echo PARSE_FAIL
kill $PF 2>/dev/null
```

PASS: exactly one pod, `startTime` later than `PUSH_TS`, `imageID` ending in `DIG`, `restarts=0`; `ok`; and
`models <n>` equal to the §2.5 baseline. The pod line guards against `rollout status` green-lighting the old
generation (an old pod shows the old digest `...fa99b651...` and an earlier start time). `/healthz` alone is shape
(it never calls upstream); `/api/tags` goes through `_proxy` and `urllib.request`, and a broken proxy prints
`PARSE_FAIL` (the handler answers 502 with an error body that has no `models` key) or a crash-looping pod shows
`restarts>0`.

**4.2 media-dashboard - CONTENTS ASSERTION: pg8000 installed on 3.15 and the page reads the database.**

```bash
kubectl get pods -n media -o jsonpath='{range .items[*]}{.metadata.name} {.status.startTime} {.status.containerStatuses[0].imageID}{"\n"}{end}' | grep media-dashboard
kubectl logs -n media deploy/media-dashboard --tail=500 | grep -ci 'WARN: pip install'
kubectl port-forward -n media deploy/media-dashboard 18081:8080 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -m 20 -o /tmp/media-dash.html -w '%{http_code}\n' http://localhost:18081/
grep -c 'source: sweep_history.media_audit_runs' /tmp/media-dash.html
kill $PF 2>/dev/null
```

PASS: new pod on `DIG`; warning count `0`; HTTP `200`; the source marker count is `>= 1`. A failed `pip install`
on 3.15 does **not** stop the pod or fail readiness (by design), so readiness proves nothing here: the failure
prints warning count `1` and marker count `0` (the page falls back to pod logs and omits the
`(source: sweep_history.media_audit_runs, run ...)` line that `dashboard.py` writes only on the database path).
The marker was read from the script, not measured against the live page by the planner (§7): if the baseline page
before the change also shows `0`, record that and judge this gate on the warning count and the HTTP code only.

**If 4.1 or 4.2 fails: go to §5 now, before the :30 tick.**

**4.3 media-intake-watcher - CONTENTS ASSERTION: the first writer run on 3.15 finishes clean (tick at :30).**

```bash
J=$(kubectl get jobs -n media --sort-by=.metadata.creationTimestamp -o name | grep media-intake-watcher | tail -1)
kubectl get "$J" -n media -o jsonpath='{.metadata.creationTimestamp} succeeded={.status.succeeded} failed={.status.failed}{"\n"}'
kubectl get pods -n media -l job-name="${J#job.batch/}" -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'
kubectl logs -n media "$J" | grep -ciE 'traceback|error'
kubectl logs -n media "$J" --tail=1
```

PASS: creation time later than `PUSH_TS`, `succeeded=1`, imageID ends in `DIG`, traceback/error count `0`, and
the last line is a JSON record whose `event` is `intake-done` and whose `items.failed` equals 0 (judge the parsed
fields, not a literal string: the line is sorted-key JSON and other keys sit between them). A 3.15 import or
runtime failure prints `failed=1` and a `Traceback`; a script that starts but dies mid-run lacks the `intake-done`
line. `intake.py` imports `common`, `organize`, `cleanup` and `rescan` as modules, so a clean run also proves those
four suspended members' scripts import on 3.15 (their own code paths stay unexercised, §4.6).

Also record the line's `actions` value. Measured 2026-11-16: `"actions": {}` - the usual tick finds nothing in
intake and moves nothing. **An empty-`actions` tick proves only that the interpreter starts, imports and scans; it
does NOT prove that file moves/renames work on 3.15** (`shutil`/`pathlib` move paths are not exercised). If the
in-window tick shows `actions` empty, record "file-move path unproven" in the window log and keep it on the §4.6
deferred watch: the first tick with a non-empty `actions` after `PUSH_TS` is the real writer gate, read by the next
sweep or the operator.

**4.4 The two tube-archivist syncs - CONTENTS ASSERTION: same work as before (ticks at :30 and :00).**

```bash
J=$(kubectl get jobs -n download --sort-by=.metadata.creationTimestamp -o name | grep image-sync | tail -1)
kubectl get "$J" -n download -o jsonpath='{.metadata.creationTimestamp} succeeded={.status.succeeded}{"\n"}'; kubectl logs -n download "$J" --tail=1
J=$(kubectl get jobs -n download --sort-by=.metadata.creationTimestamp -o name | grep nfo-sync | tail -1)
kubectl get "$J" -n download -o jsonpath='{.metadata.creationTimestamp} succeeded={.status.succeeded}{"\n"}'; kubectl logs -n download "$J" --tail=1
```

PASS: both jobs newer than `PUSH_TS` and `succeeded=1`; image-sync ends `Done. copied=<c>  skipped(existing)=<k>
source-missing/404=0` with `c + k` equal to the baseline `K` (or higher if channels were added); nfo-sync ends
`Sync completed. Processed <N> videos across <M> channels.` with `N` and `M` within a few of the §2.5 baseline.
A broken session login (the `http.cookiejar` path) shows as a non-zero `source-missing/404` or a traceback; a
broken XML write shows as `Processed 0` or a traceback.

**4.5 media-metadata-coverage (tick at :00).**

```bash
J=$(kubectl get jobs -n media --sort-by=.metadata.creationTimestamp -o name | grep media-metadata-coverage | tail -1)
kubectl get "$J" -n media -o jsonpath='{.metadata.creationTimestamp} succeeded={.status.succeeded}{"\n"}'
kubectl logs -n media "$J" | grep -c '^COVERAGE_RESULT_JSON {'
```

PASS: newer than `PUSH_TS`, `succeeded=1`, count `1`. A failure prints `succeeded=` empty and count `0`.

**4.6 Deferred gates (outside the window - the next sweep or the next morning reads them).**

| Member | First run on 3.15 | Read |
|---|---|---|
| `media-intake-watcher` (file moves) | first tick after `PUSH_TS` with non-empty `actions` | job `succeeded=1`, no traceback, `items.failed` equals 0, and each listed action's target exists on the share (media-manager spot check) |
| `media-per-item-refresh` | next 6-hourly tick | job `succeeded=1`, no traceback |
| `media-plex-fs-classifier` | 01:35 Berlin | job `succeeded=1`, no traceback |
| `media-library-audit` | 01:45 Berlin | job `succeeded=1` (both containers) and the dashboard source line shows a `run` timestamp of that night |
| `media-cleanup-nfos` | Sunday 04:30 UTC | job `succeeded=1`, no traceback. **This job deletes files and its first 3.15 run is unattended.** If the window is a Saturday, that is the following morning. |
| `media-cleanup`, `media-organize`, `media-rescan`, `media-sidecar`, `media-episode-sidecar` | only when someone triggers them | spec-level only (§4.0); the first on-demand run after this change should be watched |

**Instruments.** These read kube-state-metrics in the `kube-prometheus-stack` Prometheus.

CONTROL: metric kube_job_status_failed - `{namespace=~"media|download"}` shows no new series with value 1 for a job created after `PUSH_TS`; any `=1` on a `media-*` or `tube-archivist-*-sync-*` job is a fail.
CONTROL: metric kube_job_status_failed - positive companion `count(kube_job_status_failed{namespace=~"media|download"})` returns 18 (reviewer measurement 2026-11-16; the selector matches existing job series). Run it first: an empty result means the instrument is blind (KSM not scraped or label drift), and the "no new =1" check above would then pass vacuously - judge §4 on job status and logs only and record the instrument as blind.
CONTROL: metric kube_deployment_status_replicas_available - `{namespace="ai",deployment="ollama-toolfix"}` and `{namespace="media",deployment="media-dashboard"}` both back to 1 within 10 minutes of the push; `0` or empty is a fail.
CONTROL: alertname KubeJobFailed - not firing for namespaces `media` / `download` at window close.

## 5. Rollback

Trigger: any failed gate in §4.1-§4.5, or a deferred gate in §4.6.

```bash
cd /Users/mu/code/cberg-home-nextgen
git pull --rebase
git log -3 --format='%h %s' -- kubernetes/apps/media/library-tools/app/intake-cronjob.yaml   # find the bump commit
git revert --no-edit <that sha>
git show --stat HEAD | tail -3        # the same 15 files
git log -1 --format=%s                # Revert "chore(deps): python 3.14.10-slim -> 3.15.2-slim ..."
git push
```

Confirm the cluster is back (after Flux applies, about 2 minutes):

```bash
kubectl get cronjob -n media -o jsonpath='{range .items[*]}{.metadata.name} {.spec.jobTemplate.spec.template.spec.containers[*].image}{"\n"}{end}' | grep -c 'python:3.14.10-slim'      # 11
kubectl get cronjob -n download -o jsonpath='{range .items[*]}{.metadata.name} {.spec.jobTemplate.spec.template.spec.containers[*].image}{"\n"}{end}' | grep -c 'python:3.14.10-slim'   # 2
kubectl get deploy ollama-toolfix -n ai -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'        # python:3.14.10-slim
kubectl get deploy media-dashboard -n media -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'    # python:3.14.10-slim
```

then re-run §4.1 and §4.2 with the old image expected, and read the next intake tick as in §4.3.

Notes:

- The revert restores the tag `3.14.10-slim` without a digest, as it is today. Nodes that still hold the image
  run the build they have (`...fa99b651...`); a node that must pull gets the current build of that tag.
- A partial rollback (one member) is fine: revert only that file's line in a normal commit. Mixed 3.14 / 3.15
  across independent jobs is harmless.
- **What git does not undo:** anything a job did on the share while on 3.15. The interpreter persists nothing, but
  a writer that misbehaved would have moved or deleted real files. That is why §3.3 gates the Deployments before
  the first writer tick. If §4.3 shows a failed or half-finished intake run, stop the bleeding first (the revert),
  then hand the job's log to the media-manager to reconcile; the log lists each action with an anonymised item id.
- Rollback never involves a PVC, PV or StorageClass (§1.5).

## 6. Interference notes

- **Reciprocity is missing.** Re-checked 2026-11-16: none of the six named plans lists `python-fleet-3.15.2` in its
  `conflicts_with` (grep of each file; the only hit is a comment in `redis-fleet-8.10.3`). The scheduler honours
  the field on either side, but `postgres-digest-refresh-2026-11` (vetted; same file and CronJob),
  `tube-archivist-0.6.0` (vetted), `tube-archivist-elasticsearch-9.5.5` (vetted), `redis-fleet-8.10.3` (vetted),
  `media-naming-p3` (draft) and `kube-prometheus-stack-93.3.0` (draft; retargeted 2026-11-16 from the retired
  `92.22.0`) should list `python-fleet-3.15.2` back. `redis-fleet-8.10.3` carries a comment that it removed this id
  on 2026-11-06 as a dead ref (the retired canary plan); it applies again now. This planner edits only this file.
- **Same-file edit with `postgres-digest-refresh-2026-11`:** both touch `audit-cronjob.yaml`. Different lines, so
  the commits do not collide textually, but both change `cronjob/media-library-audit` and each plan's gate reads
  that job's next run. Whichever runs second must re-run its own sed dry test.
- **`tube-archivist-0.6.0`** rewrites the image-sync script; if it lands first, §4.4's log format and baseline for
  image-sync must be re-recorded.
- **Step 0 runs first** in every window. If Step 0 (or Renovate) moves the canary digest the same morning, §2.1
  still prints one digest (all three canary lines move together) and this plan pins the new one; if it prints
  `STOP-CANARY-DIGEST`, a digest update is half-applied - wait for it.
- **After this lands,** Renovate's digest updates for `python` cover 18 slim lines instead of 3. That is intended.
- **ollama-toolfix** is the Ollama path for openclaw and oc8. The roll is a surge-then-terminate of a stateless
  proxy; a request in flight on the old pod is cut. Do not push while an openclaw cron that uses a local model is
  running (§2.4).
- **Monitoring:** §4 CONTROL lines and the `KubeJobFailed` alert are the window's instruments; do not share a
  night with a kube-prometheus-stack change.
- **Longhorn / Talos / gateway:** no surface. None of the 15 uses a Longhorn volume; the only route
  (`media-dashboard` on `envoy-internal`) is not edited.

## 7. Open questions and what was not verified

1. **No member script was executed on CPython 3.15.** The compatibility verdict in §1.3 is a read of imports and
   API names (grep over the ConfigMaps) against the upstream notes, plus the canary soak. A local dry-compile on a
   3.15 interpreter was not available to the planner. §4 is the proof, and §3.3's ordering is the control.
2. **3.15.2 changelog, Library section:** not read in full (page truncated). Security entries were read.
3. **Image `LANG`:** the UTF-8 argument in §1.3 assumes the official image still sets a UTF-8 locale; not re-read
   from the image config for this digest.
4. **pg8000 1.31.5 on 3.15:** PyPI metadata allows it (`>=3.9`, pure Python); an actual install/import on 3.15 was
   not run. The dashboard's fallback keeps a failure non-fatal; §4.2 detects it.
5. **Baselines not measured by the planner:** the `/api/tags` model count through the proxy (§2.5) and the
   dashboard source marker on the live page (§4.2). Both are recorded in-window before the change.
6. **Renovate PR:** none was named in the dispatch and none was looked up; `pr: null`.
7. **Suspended members** (5) have no schedulable run; they are verified at spec level only until someone triggers
   them.
