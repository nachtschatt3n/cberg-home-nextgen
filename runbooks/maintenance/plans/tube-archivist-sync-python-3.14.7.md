---
plan_id: tube-archivist-sync-python-3.14.7
component: tube-archivist-nfo-sync
also_covers:                          # lockstep sibling: same image, same namespace, same
  - tube-archivist-image-sync         # PVC, bumped in the SAME commit (coverage.py reads this)
pr: null                              # no Renovate PR — coverage.py direct-bump lane, held by G3
kind: image
current: "3.11-slim"                  # floating variant tag on BOTH CronJobs. Live pods run
                                      # imageID python@sha256:1dd3dca8… (a stale node-cached
                                      # pull; Docker Hub's 3.11-slim index is now da047cb9…)
target: "3.14.7-slim"                 # Docker Hub tag exists (last_updated 2026-09-19); already
                                      # running on 13 other sites in this cluster since ea1e860d
update_type: minor
risk: low                             # stdlib-only scripts; byte-identical output measured under
                                      # 3.11 vs 3.14 (§1.3). The residual risk is that both
                                      # scripts swallow errors and exit 0, so a regression would
                                      # be SILENT — which is what §4 is built around.
est_duration_min: 65                  # commit+reconcile ~5; then the gates must wait for the
                                      # NEXT scheduled run of each CronJob (nfo :00, image :30),
                                      # worst case ~60 min; ~15 min with the optional §3.3 on-demand Jobs.
needs_reboot: false
touches:
  namespaces: [download]
  resources:
    - cronjob/tube-archivist-nfo-sync
    - cronjob/tube-archivist-image-sync
    - pvc/tube-archivist-youtube      # both jobs WRITE here (.nfo files, folder/backdrop/banner.jpg)
    - "docker.io/library/python:3.14.7-slim"
  shared: [cifs-share]                # writes land on the cifs-tube-archivist-media share that
                                      # Jellyfin reads; no PVC is created/deleted/changed
depends_on: []
conflicts_with:
  - kube-prometheus-stack-91.4.1      # §4 CONTROL gates read Prometheus (kube-state-metrics
                                      # job series); a same-night KPS restart reads as "no data"
  - flux-reconciler-impersonation     # changes the identity Flux reconciles `download` with;
                                      # if it misbehaves the same night, this commit's reconcile
                                      # failure is unattributable
exclusive: false
security_ref: null
capability_change: false             # same scripts, same inputs, same outputs (measured §1.3)
rollback_class: git-revert            # nothing forward-only: the jobs rewrite derived sidecar
                                      # files every hour from ES/TA, so a revert self-heals them
finding_refs: [F-043dfda0, F-897440a7]
status: vetted   # 2026-09-26 plan-reviewer needs-fix -> fixed (A: 4.4 ERR/HTTP=0 informational; B: 4.5 succeeded-series counterpart); C-F applied; text-only fixes, no re-review needed
window: "now:2026-09-26"   # ON-DEMAND NOW run 2026-09-26 (run-now.py stamp; was None)
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/media-library-standards.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-25"
premises:
  - id: nfo-sync-still-on-3.11-slim
    why: "`current:` claims 3.11-slim. If the CronJob already moved, this plan is stale."
    run: kubectl get cronjob -n download tube-archivist-nfo-sync -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_exact: python:3.11-slim
  - id: image-sync-still-on-3.11-slim
    why: "Lockstep sibling must be on the same starting tag, or the one-commit edit in §3 diverges."
    run: kubectl get cronjob -n download tube-archivist-image-sync -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_exact: python:3.11-slim
  - id: nfo-sync-not-suspended
    why: "§4 waits for the next SCHEDULED run; a suspended CronJob never produces one and every gate would time out."
    run: kubectl get cronjob -n download tube-archivist-nfo-sync -o jsonpath='{.spec.suspend}'
    expect_exact: "false"
  - id: image-sync-not-suspended
    why: "Same as above for the image-sync half."
    run: kubectl get cronjob -n download tube-archivist-image-sync -o jsonpath='{.spec.suspend}'
    expect_exact: "false"
  - id: youtube-pvc-bound
    why: "Both jobs and every §4 contents gate read/write pvc/tube-archivist-youtube; if it is not Bound the baseline in §2 cannot be taken."
    run: kubectl get pvc -n download tube-archivist-youtube -o jsonpath='{.status.phase}'
    expect_exact: Bound
---

# tube-archivist sync jobs: python 3.11-slim -> 3.14.7-slim

## 1. Summary & why held

Two stdlib-only helper CronJobs in `download` run a ConfigMap-mounted script on
a stock `python:*-slim` image:

| CronJob | Schedule | Script (ConfigMap) | Does |
|---|---|---|---|
| `tube-archivist-nfo-sync` | `0 * * * *` | `tube-archivist-nfo-sync` / `sync_nfo.py` | reads `ta_video` from ES, rewrites every `.nfo` + `tvshow.nfo`/`artist.nfo` on the youtube PVC |
| `tube-archivist-image-sync` | `30 * * * *` | `tube-archivist-image-sync` / `sync_images.py` | copies channel poster/fanart/banner from TA's cache into each `UC*` channel folder |

The change is one line per CronJob: `image: python:3.11-slim` ->
`image: python:3.14.7-slim`.

**Why held:** coverage.py G3 — "could not verify the release notes". CPython has
no per-image changelog Renovate/coverage can parse, so the gate could not prove
safety for a three-minor jump. That is a tooling limitation, not a signal of a
breaking change; this plan does the assessment by hand. **Verdict: effectively a
false-positive hold → `risk: low`**, but the scripts' error handling makes a
silent regression possible, so it still gets a contents-based window.

### 1.1 What 3.12–3.14 removed, against what the scripts import

Imports used: `os`, `sys`, `json`, `base64`, `urllib.request` (`urlopen`,
`Request`), `urllib.error.HTTPError`, `xml.etree.ElementTree` (`Element`,
`SubElement`, `ElementTree.write`, `indent`), `datetime.datetime.fromtimestamp`.

Removals across the jump, measured locally (3.11.15 vs 3.14.6):
- 3.12: `distutils`, `imp`, `asynchat`/`asyncore` gone — none imported.
- 3.13 (PEP 594 dead batteries): `cgi`, `telnetlib`, … gone — none imported.
- 3.14: `urllib.request.URLopener` / `FancyURLopener` gone
  (`'URLopener' in dir(urllib.request)` True on 3.11, False on 3.14) — the
  scripts use only `urlopen`/`Request`, which are unchanged.
- `datetime.utcfromtimestamp` is deprecated (3.12) — the script uses
  `fromtimestamp`, not deprecated. `ET.indent` present on both (and guarded by
  `hasattr` anyway). No `Element.__bool__` truthiness test in either script.

### 1.2 Precedent

`python:3.14.7-slim` has run since 2026-08-27 (`ea1e860d`) on 11 library-tools
manifests (same pattern: ConfigMap script on a slim image, CIFS media PVC,
`runAsUser: 1000`) and the openclaw probe/toolfix. Measured 2026-09-25:
`media-metadata-coverage`, `media-per-item-refresh`, `media-library-audit`,
`media-plex-fs-classifier` all have `lastSuccessfulTime` within the last 24 h on
3.14.7-slim. The non-root UID 1000 with no `/etc/passwd` entry is therefore
already proven on this image.

### 1.3 Differential run (the evidence this plan rests on)

Both scripts were extracted from the live ConfigMaps and run under 3.11.15 and
3.14.6 against a local fake ES + fake TA cache server (12 videos across 3
channels, mixed epoch/ISO `published`, a `channel: null` fallback, XML-special
and non-ASCII characters in titles; a 404 channel, a 500 channel, a pre-existing
`folder.jpg`), with `-W error::DeprecationWarning -W error::PendingDeprecationWarning -W error::SyntaxWarning`:
- both exit 0 on both versions, no warning raised;
- stdout identical on both versions for both scripts;
- **all 34 output files (18 `.nfo`, 12 video stubs, 3 images, 1 pre-existing)
  byte-identical** (sha diff of the whole tree: empty).
- Only difference seen: under `-X dev` (dev mode, not used in the pod) 3.14
  emits `ResourceWarning: Implicitly cleaning up <HTTPError 404>` for unclosed
  HTTPError bodies. `ResourceWarning` is ignored by default, so this does not
  appear in production logs and does not change behaviour.

Local 3.14 was 3.14.6 (Homebrew); 3.14.7 is a bugfix release on the same line.
The in-window §4 run on the real image is the final check.

### 1.4 The trap this plan is built around

**Both scripts exit 0 on failure.** Negative control, run locally on 3.14 with
the fake server down:
- `sync_nfo.py`: `get_all_videos()` catches every exception, prints
  `Error fetching from ES: ...`, returns `[]`; `main()` then prints
  `Retrieved 0 videos from Elasticsearch.` and **returns → rc=0, Job Complete**.
- `sync_images.py`: `fetch()` catches every exception, prints `  ERR <url>: ...`,
  counts it as `source-missing`, prints `Done. ...` → **rc=0, Job Complete**.

So Job success and `kube_job_status_failed == 0` prove only that the interpreter
started. Every real gate in §4 reads the log CONTENTS and the files on the PVC.

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py tube-archivist-sync-python-3.14.7   # all premises PASS

# 2.1 Flux healthy for the app
flux get kustomizations -A | grep -E 'NAME|tube-archivist'     # READY True
flux get helmreleases -n download                               # all READY True

# 2.2 Last runs on 3.11 succeeded (baseline must be a GOOD run, or §4 compares to garbage)
kubectl get jobs -n download --sort-by=.metadata.creationTimestamp | grep -E 'nfo-sync|image-sync' | tail -4
NFO_POD=$(kubectl get pods -n download --sort-by=.metadata.creationTimestamp -o name | grep tube-archivist-nfo-sync | tail -1)
IMG_POD=$(kubectl get pods -n download --sort-by=.metadata.creationTimestamp -o name | grep tube-archivist-image-sync | tail -1)
kubectl logs -n download "$NFO_POD" | tail -3
kubectl logs -n download "$IMG_POD" | tail -1
```

Record the baseline numbers (measured 2026-09-25 01:00Z, for orientation):
- nfo-sync: `Retrieved 1642 videos` / `Found 1642 video files candidates` /
  `Processed 1642 videos across 23 channels`
- image-sync: `copied=0  skipped(existing)=72  source-missing/404=0`
  (24 `UC*` channel dirs × 3 artwork files = 72)
- `.nfo` files rewritten per run: 1688 (= 1642 episode + 23 `tvshow.nfo` + 23 `artist.nfo`)

Old digest (for the §4 "actually pulled the new image" check): the running
3.11 pods report `docker.io/library/python@sha256:1dd3dca85e22886e44fcad1bb7ccab6691dfa83db52214cf9e20696e095f3e36`.

```bash
# 2.3 NFO content baseline — taken AFTER the last 3.11 nfo-sync run finished and
#     BEFORE the push. KEEP IT IN SCRATCH, NEVER COMMIT: the paths carry media titles.
B=/private/tmp/ta-nfo-baseline; mkdir -p $B
kubectl exec -n download deploy/tube-archivist -- sh -c 'find /youtube -name "*.nfo" -exec sha256sum {} + | sort -k2' > $B/pre.sha
wc -l < $B/pre.sha                                             # ~1689
```

## 3. Steps

```bash
cd /Users/mu/code/cberg-home-nextgen
A=kubernetes/apps/download/tube-archivist/app

# 3.1 Edit both CronJobs in ONE commit (BSD sed, dry-tested on scratch copies 2026-09-25)
sed -i '' 's#image: python:3\.11-slim$#image: python:3.14.7-slim#' \
  $A/metadata-sync-cronjob.yaml $A/image-sync-cronjob.yaml
git diff $A
```

Expected diff (exactly these two lines, from the dry-test):

```
metadata-sync-cronjob.yaml:  -              image: python:3.11-slim
                             +              image: python:3.14.7-slim
image-sync-cronjob.yaml:     -              image: python:3.11-slim
                             +              image: python:3.14.7-slim
```

```bash
grep -c 'python:3.14.7-slim' $A/metadata-sync-cronjob.yaml $A/image-sync-cronjob.yaml   # 1 and 1
kubeconform -summary -ignore-missing-schemas $A/metadata-sync-cronjob.yaml $A/image-sync-cronjob.yaml

# 3.2 Commit only these two files, verify, push
git commit --only $A/metadata-sync-cronjob.yaml $A/image-sync-cronjob.yaml \
  -m "chore(tube-archivist): sync jobs python 3.11-slim -> 3.14.7-slim (plan tube-archivist-sync-python-3.14.7)"
git log -1 --format=%s        # must be the subject above
git show --stat HEAD          # exactly the two cronjob files
git push      # if rejected (shared main moved): git pull --rebase && git push

# 3.3 Wait for Flux (webhook) — no manual reconcile
kubectl get cronjob -n download tube-archivist-nfo-sync tube-archivist-image-sync \
  -o custom-columns='NAME:.metadata.name,IMG:.spec.jobTemplate.spec.template.spec.containers[0].image'
# both show python:3.14.7-slim before continuing
T=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "bump live at $T"   # used by §4; taken AFTER both CronJobs show 3.14.7, so no 3.11 run can land after $T
```

Then either **wait for the next scheduled run of each** (nfo at :00, image at
:30), or — attended runs only, to cut the wait — trigger one run of each from
the RECONCILED CronJob (precedent: docs/sops/media-library-standards.md,
docs/sops/secret-rotation.md). Only after the check above shows
`python:3.14.7-slim` on both (a Job created earlier copies the OLD template),
and not within 2 min of :00/:30:

    kubectl create job -n download --from=cronjob/tube-archivist-nfo-sync tube-archivist-nfo-sync-manual-$(date +%s)
    # after it Completes (~10 s):
    kubectl create job -n download --from=cronjob/tube-archivist-image-sync tube-archivist-image-sync-manual-$(date +%s)

The Job copies the CronJob's live jobTemplate verbatim (image, env, secret,
PVC, securityContext) and is ownerRef'd to the CronJob (history limits GC it;
Flux does not prune it; not drift). The `-manual-` names keep the 4.1 pod grep
and the 4.5 `tube-archivist-(nfo|image)-sync.*` regex matching. It proves the
same thing as a scheduled run; only the controller's schedule, which this
change does not touch, is not exercised. If 4.5 lastSuccessfulTime does not
advance for a manual Job, rely on the 4.5 succeeded-series check.

## 4. Verification

Run each block after the first Job created **after `$T`** has Completed.

```bash
NFO_POD=$(kubectl get pods -n download --sort-by=.metadata.creationTimestamp -o name | grep tube-archivist-nfo-sync | tail -1)
IMG_POD=$(kubectl get pods -n download --sort-by=.metadata.creationTimestamp -o name | grep tube-archivist-image-sync | tail -1)
for P in $NFO_POD $IMG_POD; do
  kubectl get -n download $P -o jsonpath='{.metadata.creationTimestamp} {.spec.containers[0].image} {.status.containerStatuses[0].imageID} {.status.phase}{"\n"}'
done
```

**4.1 Right image actually ran.** PASS: creationTimestamp > `$T`, image
`python:3.14.7-slim`, imageID ≠ `…1dd3dca8…` (the old 3.11 digest), phase
`Succeeded`. FAIL prints the old digest or `python:3.11-slim` (Flux did not
apply / wrong pod picked). Note the node-cached 3.14.7-slim digest seen on
library-tools pods is `83ff1d24…`, while Docker Hub's index now reads
`caaf356f…` (tag was re-pushed 2026-09-19) — either is fine; the check is
"not the old one", not a specific new digest.

**4.2 nfo-sync did real work (CONTENTS).**

```bash
kubectl logs -n download "$NFO_POD" | grep -iE 'retrieved|found|processed|error|failed|traceback'
```

CONTENTS ASSERTION: nfo-sync read ES and wrote episode metadata — measured by
the job log, compared to the §2.2 baseline. PASS: `Retrieved N` with N ≥ the
baseline (1642 at authoring) and N > 0, `Processed N videos across M channels`
with M ≥ 23, and **no** `Error fetching from ES` / `Failed to write` / `Traceback` line
(case-insensitive grep). FAIL prints `Error fetching from ES: …` +
`Retrieved 0 videos` while the Job is still Complete (§1.4 negative control,
code path `get_all_videos` except-branch → `main` early return).

**4.3 The files on the PVC were rewritten, and their contents did not change.**

```bash
kubectl exec -n download deploy/tube-archivist -- sh -c "find /youtube -name '*.nfo' -newermt '$T' | wc -l"
kubectl exec -n download deploy/tube-archivist -- sh -c 'find /youtube -name "*.nfo" -exec sha256sum {} + | sort -k2' > $B/post.sha
wc -l < $B/post.sha          # must be >= wc -l < $B/pre.sha; empty/short = FAIL (exec/mount problem), not a clean diff
diff $B/pre.sha $B/post.sha | grep -c '^[<>]'
```

CONTENTS ASSERTION: every NFO was rewritten by the 3.14 interpreter with
byte-identical output — measured by `find -newermt $T` and a sha256 diff of all
`.nfo` files, compared to the §2.3 pre-bump baseline. PASS: newer-than-`$T`
count ≥ 1688 (baseline; = episodes + 2×channels), and the sha diff is **0**
lines when `Retrieved` is unchanged from baseline. If TA ingested new videos
between the two runs, only lines for the NEW `.nfo` files may appear (`>` with
no matching `<`); any changed pre-existing file is a FAIL — §1.3 showed 3.14
produces byte-identical XML, so a change means different serialization/date
handling. FAIL modes this catches: 0 rewritten (script bailed out early),
permission/encoding failure on write (`Failed to write NFO` in the log, file
count short), altered XML. Clean up `$B` afterwards (titles in paths).

**4.4 image-sync did real work (CONTENTS).**

```bash
kubectl logs -n download "$IMG_POD" | grep -icE '^  (ERR|HTTP) '
kubectl logs -n download "$IMG_POD" | grep -i 'done\.'
```

CONTENTS ASSERTION: every channel folder still has its three artwork files —
measured by the `Done.` line, compared to the baseline 72. PASS: the `Done.`
line is present, `copied + skipped(existing)` ≥ 72 (3 × number of `UC*`
dirs; 24 at authoring) and `source-missing/404=0`. FAIL: no `Done.` line
(`YOUTUBE_ROOT /youtube not mounted` + rc=1, or a Traceback), or a sum < 72.
NOT verified in-window: the TA-cache fetch path (`urlopen`). `fetch()` runs
only for a MISSING artwork file (`os.path.exists(dst)` short-circuits first)
and all 72 exist, so the ERR/HTTP count is 0 by construction on every run —
it is informational, not a gate. The `urlopen` path under 3.14 rests on the
§1.3 local differential (404/500 channels exercised there).

**4.5 Prometheus controls (floor, not the gate).**

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s --data-urlencode 'query=kube_cronjob_status_last_successful_time{namespace="download",cronjob=~"tube-archivist-(nfo|image)-sync"}' http://localhost:19090/api/v1/query
curl -s --data-urlencode 'query=kube_job_status_failed{namespace="download",job_name=~"tube-archivist-(nfo|image)-sync.*"} > 0' http://localhost:19090/api/v1/query
curl -s --data-urlencode 'query=kube_job_status_succeeded{namespace="download",job_name=~"tube-archivist-(nfo|image)-sync.*"} == 1' http://localhost:19090/api/v1/query
kill $PF 2>/dev/null
```

CONTROL: metric kube_cronjob_status_last_successful_time — both series present (2 results; measured live 2026-09-25) and each value > epoch of `$T`. An absent series is a FAIL, not a pass.
CONTROL: metric kube_job_status_failed — the `> 0` query returns an empty result for jobs created after `$T`, AND the `kube_job_status_succeeded == 1` query returns a series for EACH post-`$T` job (job name = the 4.1 pod's `job-name` label). The succeeded query is the half that can fail: if it lacks the post-`$T` job names, the empty failed-result is a missing series, not a pass — FAIL.

These catch the loud failure (interpreter/image won't start, `ImagePullBackOff`,
crash). The silent failure is caught only by 4.2–4.4.

## 5. Rollback

Nothing forward-only: both jobs regenerate derived sidecar files every hour
from ES / the TA cache, and neither touches ES, TA or the PVC definition.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <bump-sha>
git log -1 --format=%s; git show --stat HEAD     # only the two cronjob files
git push
kubectl get cronjob -n download tube-archivist-nfo-sync tube-archivist-image-sync \
  -o custom-columns='NAME:.metadata.name,IMG:.spec.jobTemplate.spec.template.spec.containers[0].image'
# both python:3.11-slim
```

Confirm back: the next nfo-sync run (on the node-cached 3.11 digest `1dd3dca8…`,
or whatever the float resolves to) logs `Processed ≥1642 videos across ≥23
channels`, and re-run the §4.3 sha diff against `pre.sha` → 0 changed
pre-existing files. If 4.3 found altered NFOs, the next 3.11 run rewrites them
all from ES, which is the repair; Jellyfin picks them up on its normal library
scan (`lockdata=true` means nothing else overwrites them).

## 6. Interference notes

- **Scope is only these two CronJobs.** The main `tube-archivist` app, its ES and
  redis are untouched (the redis `8.10.1 -> 8.10.2` patch, F-625d3a3f, is a
  separate safe-lane item; bumping it the same window is fine but would muddy
  4.2 if ES/TA restarted — prefer it lands after §4).
- **Shared surface:** the `cifs-tube-archivist-media` share (PVC
  `tube-archivist-youtube`, RWX, Retain). Writes only; no PVC/PV operation. Jellyfin
  reads these NFOs — a same-night Jellyfin plan (`jellyfin-12.1`) is not a hard
  conflict because the NFO bytes are expected unchanged, but do not attribute a
  Jellyfin metadata regression to this plan without checking 4.3 first.
- **`conflicts_with`:** `kube-prometheus-stack-91.4.1` (4.5 reads Prometheus),
  `flux-reconciler-impersonation` (changes how Flux applies `download`; an
  unexplained reconcile failure would be unattributable).
- **`float-tag-pinning` (programme, Batch A)** lists these two sites among its
  `python:3.11-slim` pins. After this plan, they are on a version-shaped tag and
  drop out of Batch A's python:3.11 edit; that plan's inventory should be
  refreshed, not treated as a conflict.
- **Timing:** gates need the :00 and :30 runs after the push. In the nightly
  window (03:30) push before 03:55 so the 04:00 nfo run and 04:30 image run fall
  inside it; 65 min fits the 70-min nightly budget only if Step 0 is short —
  otherwise schedule in a sat-attended slot.
- Same held shape, NOT covered here: `crash-ghost-reaper` and
  `elasticsearch-obs-recovery` (`python:3.12-alpine -> 3.14.7-alpine`); they need
  their own plans.
