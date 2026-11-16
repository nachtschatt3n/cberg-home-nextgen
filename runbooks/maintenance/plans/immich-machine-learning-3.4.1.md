---
plan_id: immich-machine-learning-3.4.1
component: immich-machine-learning
pr: 531                               # Renovate "update immich monorepo ( v3.3.6 -> v3.4.1 )", OPEN + MERGEABLE 2026-11-13,
                                      # CI green (Flate Render Gate, Flux Local Diff x2). The PR moves BOTH tags; this plan
                                      # lands ONLY the ML tag as its own direct commit and never merges the grouped PR (§6).
kind: image
current: "v3.3.6-openvino"            # live 2026-11-13: deploy/immich-machine-learning, pod on k8s-nuc14-01, imageID
                                      # ghcr.io/immich-app/immich-machine-learning@sha256:035c30de002da9d4d4ae3872107bb9d8e195ead1c1f9fd470a2b0149ed37aec1
target: "v3.4.1-openvino"             # ghcr index digest sha256:97f60b06c5938c326d3ba416bcf24bc94d233f34554c05f3b76336f98ffd5ea9
                                      # (HEAD manifest 2026-11-13). Upstream tag v3.4.1 = commit 22b95194c80a2f2e6201093916b6c8c3d6d271dd,
                                      # release published 2026-11-11T18:27Z (v3.4.0: 2026-11-10T18:31Z).
update_type: minor
risk: low                             # MEASURED from `git diff v3.3.6 v3.4.1 -- machine-learning` (§1): the OpenVINO stack is
                                      # byte-for-byte the same recipe (ORT v1.30.0 source build, openvino pin, Intel GPU runtime
                                      # package versions, sessions/ort.py, ml-models runtime content). What moves is Python-level:
                                      # pillow 12 -> 13 + a JPEG XL decoder, logging config, dependency bumps. Stateless workload,
                                      # git-revert rollback, model cache regenerable.
est_duration_min: 25                  # pre-checks 5 + commit/reconcile 3 + image pull (NOT measured, see §6: 650 MB compressed,
                                      # 7 of 12 layers new) + startup 2 + verification 10.
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - helmrelease/immich-machine-learning     # the one edit: machine-learning-helmrelease.yaml tag (+ fallback comment)
    - deployment/immich-machine-learning      # strategy Recreate (live): ML unavailable for pull + start; the server keeps
                                              # serving the library, smart search / face / OCR jobs fail or queue meanwhile
    - service/immich-machine-learning         # unchanged; endpoints move to the new pod
    - pvc/immich-ml-cache                     # longhorn RWO 30Gi (17G used / 14G free 2026-11-13); detaches and re-attaches
                                              # with the Recreate; models reused, nothing deleted
  shared: [igpu-i915, monitoring]             # the pod requests gpu.intel.com/i915: 1 (Recreate frees, then re-claims a slot);
                                              # §4 reads Prometheus (the window's instrument).
depends_on: []                        # ML goes FIRST. The sibling immich-server-3.4.1 deliberately has depends_on: [] (order by preference, not a hard dependency); formerly: should carry
                                      # depends_on: [immich-machine-learning-3.4.1] (§1 "Coupling", §6). Not listed here.
conflicts_with:
  - talos-linux-1.14.6                 # node roll (exclusive, supersedes 1.14.5 draft).
  - helm-drift-detection              # rolls the intel-gpu-plugin DaemonSet (i915 re-register under the new pod) and changes
                                      # how helm-controller applies this HR.
  - flux-oci-chart-sources            # may move the app-template chart source under this HR mid-window.
  - talos-linux-1.14.5                # node roll (exclusive): reboots the node the ML pod and its Longhorn volume sit on.
  - talos-power-tuning-ab             # changes the nuc14 power/thermal envelope and declares igpu-i915; ML's cpu:3 cap is a thermal bound.
  - longhorn-1.13.0                   # storage engine bump (exclusive) under immich-ml-cache while the Recreate re-attaches it.
  - frigate-reolink-go2rtc-flv        # shared igpu-i915 (both declare it); its Recreate can contend for a slot while §4.3 runs.
  - kube-prometheus-stack-93.3.0     # draft, exclusive, window null: restarts Prometheus, which this plan's gates read (retargeted 2026-11-16 from retired 92.22.0)
exclusive: false
security_ref: F-ad843a10              # open security findings on the running v3.3.6-openvino image (detail in the DB
                                      # record only, never here); see §1 "Security" and §4.7.
capability_change: false              # /predict request and response contract unchanged (schemas.py, main.py routes and the
                                      # server-side machine-learning.repository.ts are identical between the tags). No new route,
                                      # port, permission, env or exposure. The one new ability, decoding JPEG XL input, is
                                      # unreachable here: a server only sends JXL when image.preview.format = jxl, which v3.3.6
                                      # cannot be set to and which is unset (default jpeg) in the live system-config. Reviewer:
                                      # this is the judgement call in this file; see §1.
rollback_class: git-revert            # stateless Deployment; /cache layout code is unchanged, so v3.3.6 reads what v3.4.1 left.
finding_refs: [F-f7fa90d3, F-ad843a10, F-1d38b927]
                                      # F-f7fa90d3: version, "immich-machine-learning: image ... v3.3.6-openvino -> v3.4.0-openvino
                                      # (minor)" (title predates v3.4.1). Queried 2026-11-13 (`policy-cli.py finding list --grep immich`).
                                      # F-ad843a10, F-1d38b927: open security findings on the v3.3.6-openvino image (added
                                      # 2026-11-16 per review; detail stays on the DB record). All three close via §4.7.
review: ready-for-go@2026-11-16
status: vetted
window: null
premises:
  - id: ml-image-is-v3.3.6-openvino
    why: >-
      current, the digests and every baseline in this plan were captured against this pin.
      If the Deployment already moved, this plan is stale (or something else applied it).
    run: |-
      kubectl get deploy immich-machine-learning -n media -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/immich-app/immich-machine-learning:v3.3.6-openvino"
  - id: ml-manifest-pin-is-v3.3.6-openvino
    why: "The §3 sed edits exactly this line; 0 means git already moved and the edit would be a silent no-op."
    run: |-
      grep -c 'tag: v3.3.6-openvino' kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml
    expect_exact: "1"
  - id: ml-hr-ready
    why: "A HelmRelease already failing would mask whether the bump itself reconciled."
    run: |-
      kubectl get helmrelease immich-machine-learning -n media -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: ml-strategy-recreate
    why: "ML mounts the RWO longhorn immich-ml-cache; RollingUpdate risks Multi-Attach (longhorn-rwo-multi-attach SOP)."
    run: |-
      kubectl get deploy immich-machine-learning -n media -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: ml-cache-pvc-bound
    why: "The new pod cannot start without the model cache volume."
    run: |-
      kubectl get pvc immich-ml-cache -n media -o jsonpath='{.status.phase}'
    expect_exact: "Bound"
  - id: i915-allocatable-on-all-nodes
    why: >-
      The Deployment has no nodeSelector or affinity, so the Recreate may land on any node;
      each must advertise the iGPU resource or the pod can sit Pending.
    run: |-
      kubectl get nodes -o jsonpath='{.items[*].status.allocatable.gpu\.intel\.com/i915}'
    expect_exact: "5 5 5"
  - id: immich-ml-alerts-quiet
    why: "ImmichMLNotReady / ImmichPodCrashLooping / ImmichPodRestarted must be quiet before the change, or §4.5 cannot attribute a firing."
    run: |-
      kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=ALERTS%7Balertname%3D~%22ImmichMLNotReady%7CImmichPodCrashLooping%7CImmichPodRestarted%22%2Calertstate%3D%22firing%22%7D'
    expect_contains: '"result":[]'
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/immich.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-13"
---

# immich-machine-learning v3.3.6-openvino -> v3.4.1-openvino

**Folding verdict for the reviewer: this is NOT one deployable unit with `immich-server-3.4.1`.**
The two are separate HelmReleases with no version handshake, they roll back differently (this
half is a plain git revert; the server half carries schema migrations), and the two tags can be
ordered. The required order is **ML first, server second**; a skew of ML v3.4.1 under server
v3.3.6 is safe for as long as needed. Folding the two files is still a legitimate convenience
(precedent: the retired `immich-server-3.3.6` covered both with `also_covers`); if folded, §3
here becomes the server plan's ML leg and must stay its own commit, verified before the server
commit.

## 1. Summary & why held

One file, two lines, in `kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml`:
`tag: v3.3.6-openvino` -> `v3.4.1-openvino`, plus the fallback comment
`plain v3.3.6 (CPU) tag` -> `v3.4.1` kept in step.

**Why held.** Deny rule `*immich*` in `runbooks/auto-update-policy.yaml`: "Immich server applies
forward-only DB migrations; revert after migration crash-loops. Plan lane only: dump +
scratch-restore proof first (immich-server plan)." That reason is about the server. The ML
container has no database connection and no migrations, so for this half the stated hazard does
not exist and the hold is a false positive in substance. It is held because it rides the same
monorepo PR #531, and it still deserves a plan because the server half of that PR is NOT
trivial this time: `git diff v3.3.6 v3.4.1 -- server/src/schema/migrations` adds three
migrations (`1792511451454-AddPasskeyTable`, `1792517020180-AddUpdateIdIndexes`,
`1792568637987-AddAssetOwnerIdUpdateIdIndex`). Merging the grouped PR would therefore carry a
forward-only server change in with this one. This plan does not take a DB dump; that gate
belongs to `immich-server-3.4.1`.

**Security.** This half is not purely a version chore: the running `v3.3.6-openvino` image
carries open security findings, `F-ad843a10` (also `security_ref`) and `F-1d38b927`. Their
detail lives on the `sweep_findings` record (`runbooks/policy-cli.py finding show <id>`), never
in this file. The bump to `v3.4.1-openvino` is the remedy available to us (we bump, we do not
rebuild third-party images). Both findings close only when the post-window sweep re-scans the
new image and no longer reports them (§4.7); landing the commit is not the close.

**Upstream evidence** (blobless clone of `immich-app/immich`, `git diff v3.3.6 v3.4.1 --
machine-learning`, 17 files excluding `uv.lock`; a two-dot diff, because the GitHub compare
API truncates at 300 files and reports changes relative to the merge base):

What is unchanged, and why that sets the risk:
- `machine-learning/Dockerfile` `builder-openvino` stage: still `ONNXRUNTIME_VERSION="v1.30.0"`,
  built from source with `--use_openvino CPU ... --no_telemetry`; `pyproject.toml` still pins
  `openvino==2026.5.0.dev20261005` for that build.
- The Intel GPU runtime packages: the inline `wget` list moved into the new
  `machine-learning/scripts/install-intel-runtime.sh`, with the same seven package URLs and
  versions (IGC 2.41.5 and 1.0.17537.24, compute-runtime 26.35.39758.10 and legacy
  24.35.30872.36, libigdgmm12 22.10.0).
- `immich_ml/sessions/ort.py` (device selection, OpenVINO provider options, cache directory
  keying) and `immich_ml/schemas.py`: no diff.
- The `immich-model` runtime dependency moves `8bf3fd1b` -> `a1eeff2c` in
  `immich-app/ml-models`; the tree diff between those revisions is three files under
  `.github/workflows/` only.

What changes:
- `pillow>=12.2,<13` -> `pillow>=13,<14`, new dependency `pillow-jxl-plugin>=1.3.8`, imported in
  `immich_ml/models/transforms.py` (`from pillow_jxl import JpegXLImagePlugin`,
  `DECODE_THREADS = 0`). From upstream PR #32732 "feat(server): add jxl as target format".
- Logging: `immich_ml/log_conf.json` is deleted; the same config becomes `LOG_CONFIG` in
  `config.py`, applied with `logging.config.dictConfig` and passed to gunicorn as
  `logconfig_dict` (PR #32220). `__main__.py` drops `--log-config-json`.
- `models/ocr/detection.py`: OCR `max_resolution` is rounded up to a multiple of 32
  (PR #32263). Server default is 736 (= 23 x 32) and the live system-config sets no override, so
  this is a no-op here.
- `models/cache.py`: the in-memory model cache key uses `clean_name(entry.name)` (PR #32610,
  a preloaded model was loaded twice).
- `main.py`: the load-failure warning now reads
  `Failed to load ... model '<name>', clearing cache: <error>` (was `. Clearing cache.`).
- RKNN-only changes (`sessions/rknn/*`, `rknn_threads`) do not apply to the OpenVINO image.
- Lockfile bumps that reach the runtime: fastapi 0.136.3 -> 0.162.0, gunicorn 25.3.0 -> 26.2.0,
  uvicorn 0.49.0 -> 0.54.0, pydantic 2.13.5 -> 2.14.1, numpy 2.5.3 -> 2.5.4, onnx 1.22.0 ->
  1.23.2, rapidocr 3.9.2 -> 3.10.0, huggingface-hub 1.32.0 -> 1.33.0.

**Coupling with the server (the question asked of this plan).**
- No version handshake. `server/src/repositories/machine-learning.repository.ts` has no diff
  between the tags; the server uses `/ping` and `/predict` only, and the ML request/response
  schema is unchanged. A one-patch skew has run here before.
- One real ordering constraint, in one direction. v3.4.1 adds `ImageFormat.Jxl`
  (`server/src/enum.ts`) as a selectable preview/thumbnail format, and the server sends the
  preview file to ML (`smart-info.service.ts`, `encodeImage(previewFile.path, ...)`). A v3.4.1
  server set to JXL previews needs an ML that can decode JXL, which v3.3.6 cannot
  (`import pillow_jxl` -> `ModuleNotFoundError`, measured live 2026-11-13). The reverse skew has
  no such edge: a v3.3.6 server has no JXL option, and v3.4.1 ML accepts everything v3.3.6 did.
- Live state: `system_metadata` key `system-config` carries no `image.preview` or
  `image.thumbnail.format` override (defaults `jpeg` / `webp` in `server/src/dtos/config.dto.ts`
  at v3.4.1), so even server-first would work today. ML-first removes the dependence on that
  setting staying untouched.
- Therefore: **may be ordered, ML first; lockstep in one commit is not required.** If this plan
  is rolled back while the server is already on v3.4.1, the only rule is: do not switch the
  image format to JPEG XL until ML is back on v3.4.x.

**capability_change: false, and why.** The container gains a JPEG XL decoder and nothing else
that a caller could reach: no route, port, env, permission or exposure changes, and the Service
is ClusterIP with the server as its only client. The decoder is dormant under the live config.
If the reviewer reads "a new input format the software can parse" as a capability regardless of
reachability, flip the field; the steps do not change.

Context: Immich here is a read-only iCloud-library viewer (`docs/sops/immich.md`). ML is
stateless apart from `/cache` (downloaded models and OpenVINO compiled blobs, regenerable).
**No PVC is deleted, created or resized by this plan.**

## 2. Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` (zsh on the Mac mini). Any FAIL = do not run.

2.1 Premises:
```bash
.venv/bin/python3 runbooks/plan-premises.py immich-machine-learning-3.4.1 --require-premises
```

2.2 Flux and workload healthy:
```bash
flux get helmreleases -n media | grep -E 'NAME|immich'
kubectl get pods -n media -o wide | grep immich
```
PASS: all four `immich-*` HelmReleases `Ready=True`, four pods `Running`.

2.3 Target tag still resolves to the digest in frontmatter (upstream did not re-push):
```bash
TOK=$(curl -s "https://ghcr.io/token?scope=repository:immich-app/immich-machine-learning:pull" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -sI -H "Authorization: Bearer $TOK" \
  -H 'Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.oci.image.manifest.v1+json' \
  https://ghcr.io/v2/immich-app/immich-machine-learning/manifests/v3.4.1-openvino | grep -i docker-content-digest
```
PASS: `sha256:97f60b06c5938c326d3ba416bcf24bc94d233f34554c05f3b76336f98ffd5ea9` (measured 2026-11-13).
FAIL: no line (404 or auth) or another digest. Stop and re-read the release before continuing.

2.4 Baselines, kept in `/tmp/immich-ml-341` and compared in §4:
```bash
mkdir -p /tmp/immich-ml-341
# (a) image markers of the OLD pod. These prove §4.2 can fail:
kubectl exec -n media deploy/immich-machine-learning -- sh -c 'printenv IMMICH_SOURCE_REF IMMICH_SOURCE_COMMIT; python3 -c "import PIL,gunicorn,importlib.util as u;print(\"PIL=\"+PIL.__version__, \"GUNICORN=\"+gunicorn.__version__, \"JXL_PLUGIN=\"+str(u.find_spec(\"pillow_jxl\") is not None))"; ls /usr/src/immich_ml/log_conf.json | wc -l' \
  | tee /tmp/immich-ml-341/markers-before.txt
#   measured 2026-11-13: v3.3.6 / 587f549f46f1cd1822a06e16dcccecef04ea4565 / PIL=12.3.0 GUNICORN=25.3.0 JXL_PLUGIN=False / 1
# (b) the iGPU is visible to OpenVINO now (else the pod is already degraded: STOP):
kubectl exec -n media deploy/immich-machine-learning -- python3 -c "import onnxruntime as ort;print(ort.__version__, ort.capi._pybind_state.get_available_openvino_device_ids())" \
  | tee /tmp/immich-ml-341/ov-devices-before.txt
#   measured 2026-11-13: 1.30.0 ['CPU', 'GPU']
# (c) model cache: disk use and the GPU-kind compiled-blob directories:
kubectl exec -n media deploy/immich-machine-learning -- sh -c 'df -h /cache | tail -1; ls -d /cache/*/*/*/openvino/*/' \
  | tee /tmp/immich-ml-341/cache-before.txt
#   measured 2026-11-13: 30G size, 17G used, 14G free (56%); six dirs, all keyed 12.71.4-112eu:
#   clip/ViT-B-32__openai/{textual,visual}, facial-recognition/buffalo_l/{detection,recognition},
#   ocr/LATIN__PP-OCRv5_mobile/{detection,recognition}
# (d) which models fail to prepare today (pre-existing, must not be blamed on this bump):
kubectl -n media logs deploy/immich-machine-learning 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' > /tmp/immich-ml-341/ml-before.log
grep -A3 -E 'RuntimeError: *Preparing' /tmp/immich-ml-341/ml-before.log | grep -oE '/cache/[A-Za-z_-]+/[A-Za-z0-9_.-]+/[a-z]+' | sort | uniq -c
#   measured 2026-11-13 (13 h of log): 17 x /cache/ocr/LATIN__PP-OCRv5_mobile/recognition, nothing else
```
STOP if (b) lacks `'GPU'`, if free space on `/cache` is under 5G, or if (d) names any model
other than `ocr/LATIN__PP-OCRv5_mobile/recognition` (that would be a new, unexplained fault).

2.5 Functional baseline. Run the two `/predict` probes of §4.3 against the OLD pod and require
`TEXT_PASS` and `VISUAL_PASS` (measured 2026-11-13 on v3.3.6-openvino: `TEXT 512 512`,
`VISUAL 512 faces 0`). A probe that fails before the change cannot gate the change.

2.6 Nothing else in flight on this surface:
```bash
.venv/bin/python3 runbooks/maintenance-plan.py --open
git status --short kubernetes/apps/media/immich/
```
PASS: none of the `conflicts_with` plans is stamped for this window; the immich folder has no
uncommitted change from another session.

## 3. Steps

3.1 Edit (dry-tested on a scratch copy with BSD sed, 2026-11-13). Resulting diff, exactly two lines:
```
47c47
<             # Fallback on OpenVINO regressions: swap to the plain `v3.3.6` (CPU) tag.
>             # Fallback on OpenVINO regressions: swap to the plain `v3.4.1` (CPU) tag.
51c51
<               tag: v3.3.6-openvino
>               tag: v3.4.1-openvino
```
```bash
sed -i '' \
  -e 's|^\([[:space:]]*tag: \)v3\.3\.6-openvino$|\1v3.4.1-openvino|' \
  -e 's|swap to the plain `v3\.3\.6` (CPU) tag|swap to the plain `v3.4.1` (CPU) tag|' \
  kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml
git diff --stat -- kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml   # 1 file, 2 insertions, 2 deletions
```
Anything other than `2 insertions(+), 2 deletions(-)` = `git checkout -- <that file>` and stop.

3.2 Commit only that file and push:
```bash
cat > /tmp/immich-ml-341/msg.txt <<'EOF'
fix(immich-ml): v3.3.6-openvino -> v3.4.1-openvino (plan immich-machine-learning-3.4.1)

ML leg of Renovate PR #531, landed on its own ahead of the server leg. OpenVINO
stack unchanged upstream (ORT v1.30.0 build, openvino pin, Intel runtime); adds
pillow 13 + JPEG XL decoding, logging config moved into code.
EOF
git commit --only kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml -F /tmp/immich-ml-341/msg.txt
git log -1 --format=%s      # must be the subject above; amend before push if not (shared worktree)
git show --stat HEAD        # exactly 1 file
git push
```
Record the SHA as `$ML_BUMP`. The Flux webhook reconciles; no manual `flux reconcile`.
Do not merge or close PR #531: Renovate rebases it down to the server leg, which
`immich-server-3.4.1` owns.

3.3 Wait for the roll, then run all of §4 before the server plan starts:
```bash
kubectl rollout status deploy/immich-machine-learning -n media --timeout=15m
kubectl get events -n media --sort-by=.lastTimestamp | grep -i -E 'immich-machine-learning.*(pull|fail|attach)' | tail -8
```
Note the `Successfully pulled image ... in <duration>` line in the window report; the pull time
for this image has never been recorded (§6).

## 4. Verification

4.1 CONTENTS ASSERTION: the running container is the target image, measured by pod `imageID`
against the ghcr index digest (rollout status alone can green-light the old generation):
```bash
kubectl get pod -n media -l app.kubernetes.io/name=immich-machine-learning \
  -o jsonpath='{range .items[*]}{.metadata.name} {.spec.nodeName} {.status.phase} {.status.containerStatuses[0].imageID} restarts={.status.containerStatuses[0].restartCount}{"\n"}{end}'
```
PASS: exactly one pod, `Running`, imageID ending
`sha256:97f60b06c5938c326d3ba416bcf24bc94d233f34554c05f3b76336f98ffd5ea9`, `restarts=0`.
FAIL: the old digest `sha256:035c30de...` (live value 2026-11-13), two pods, `Pending`
(no i915 slot, or Multi-Attach on `immich-ml-cache`), or `restarts` above 0.

4.2 CONTENTS ASSERTION: the image contents are v3.4.1, measured inside the new pod against
`/tmp/immich-ml-341/markers-before.txt`:
```bash
kubectl exec -n media deploy/immich-machine-learning -- sh -c 'printenv IMMICH_SOURCE_REF IMMICH_SOURCE_COMMIT; python3 -c "import PIL,gunicorn,importlib.util as u;print(\"PIL=\"+PIL.__version__, \"GUNICORN=\"+gunicorn.__version__, \"JXL_PLUGIN=\"+str(u.find_spec(\"pillow_jxl\") is not None))"; ls /usr/src/immich_ml/log_conf.json | wc -l' \
  | tee /tmp/immich-ml-341/markers-after.txt
```
PASS: `v3.4.1`, `22b95194c80a2f2e6201093916b6c8c3d6d271dd`, `PIL=13.0.0`, `GUNICORN=26.2.0`,
`JXL_PLUGIN=True`, and `0` (plus an `ls: cannot access` line on stderr, expected). The `ls` exits
non-zero on the new image because `log_conf.json` is gone; that is the expected result, not a
failure of the command (only `wc -l`'s output is read, and `sh -c` returns `wc`'s status).
FAIL: what the old pod prints today: `v3.3.6`, `587f549f...`, `PIL=12.3.0 GUNICORN=25.3.0
JXL_PLUGIN=False`, `1`. `PIL` and `GUNICORN` are from the v3.4.1 lockfile; if only those two
differ from the expected values while the commit and `JXL_PLUGIN=True` match, record it and
continue.

4.3 CONTENTS ASSERTION: inference returns real embeddings and runs the face pipeline, measured
by direct `/predict` calls (baseline §2.5: textual 512 dims all non-zero, visual 512 dims,
facial-recognition key present):
```bash
python3 - <<'EOF'
import zlib,struct
w=h=256
raw=b''.join(b'\x00'+b''.join(bytes([(x*7+y*3)%256,(x*y)%256,(y*5)%256]) for x in range(w)) for y in range(h))
def c(t,d): return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
open('/tmp/immich-ml-341/probe.png','wb').write(b'\x89PNG\r\n\x1a\n'+c(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+c(b'IDAT',zlib.compress(raw))+c(b'IEND',b''))
EOF
kubectl -n media port-forward svc/immich-machine-learning 13003:3003 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -m 10 http://127.0.0.1:13003/ping; echo
curl -s -m 120 -X POST http://127.0.0.1:13003/predict \
  -F 'entries={"clip":{"textual":{"modelName":"ViT-B-32__openai"}}}' -F 'text=a photo of a dog' \
  | python3 -c "import sys,json;r=json.load(sys.stdin);e=r['clip'];e=json.loads(e) if isinstance(e,str) else e;n=sum(1 for x in e if x!=0);print('TEXT',len(e),n);sys.exit(0 if len(e)==512 and n>500 else 1)" && echo TEXT_PASS || echo TEXT_FAIL
curl -s -m 180 -X POST http://127.0.0.1:13003/predict \
  -F 'entries={"clip":{"visual":{"modelName":"ViT-B-32__openai"}},"facial-recognition":{"detection":{"modelName":"buffalo_l","options":{"minScore":0.7}},"recognition":{"modelName":"buffalo_l"}}}' \
  -F 'image=@/tmp/immich-ml-341/probe.png' \
  | python3 -c "import sys,json;r=json.load(sys.stdin);e=r['clip'];e=json.loads(e) if isinstance(e,str) else e;ok=len(e)==512 and isinstance(r.get('facial-recognition'),list) and r.get('imageWidth')==256;print('VISUAL',len(e),'faces',len(r.get('facial-recognition',[])));sys.exit(0 if ok else 1)" && echo VISUAL_PASS || echo VISUAL_FAIL
kill $PF 2>/dev/null
```
PASS: `pong`, `TEXT_PASS`, `VISUAL_PASS` (`faces 0` is expected; the probe image has no faces).
Can fail: an HTTP 500, a refused connection or a non-JSON body makes the python raise and prints
`*_FAIL`; a zero vector fails the `n>500` floor. Measured negative control 2026-11-13: an unknown
`modelName` returns `{"detail":"Invalid request format."}`, which has no `clip` key -> `TEXT_FAIL`.
The visual probe decodes a PNG through the new pillow 13, so it also exercises the image-decode
path this release changed.

Then the iGPU path and the log, read AFTER the probes so the models have actually loaded:
```bash
kubectl exec -n media deploy/immich-machine-learning -- python3 -c "import onnxruntime as ort;print(ort.__version__, ort.capi._pybind_state.get_available_openvino_device_ids())" \
  | tee /tmp/immich-ml-341/ov-devices-after.txt
grep -c "'GPU" /tmp/immich-ml-341/ov-devices-after.txt                                  # GATE == 1
echo "['CPU']" | grep -c "'GPU"                                                         # REPLAY == 0 (CPU-only list fails the gate)
kubectl -n media logs deploy/immich-machine-learning 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' > /tmp/immich-ml-341/ml-after.log
grep -c 'Starting gunicorn 26.2.0' /tmp/immich-ml-341/ml-after.log                      # CONTROL == 1 (boot banner is in the capture)
grep -c -E 'Loading (visual|textual|detection|recognition) model' /tmp/immich-ml-341/ml-after.log   # CONTROL >= 4 (the probes loaded four models)
grep -A3 -E 'RuntimeError: *Preparing' /tmp/immich-ml-341/ml-after.log | grep -oE '/cache/[A-Za-z_-]+/[A-Za-z0-9_.-]+/[a-z]+' \
  | grep -vc 'ocr/LATIN__PP-OCRv5_mobile/recognition'                                   # GATE == 0
# KNOWN-BAD REPLAY of the identical Preparing pipeline: swap the exclusion for a string that
# matches nothing, against the saved BEFORE log. Must print non-zero, proving the extraction
# still finds Preparing failures in this log format (an all-zero here = the gate is blind).
grep -A3 -E 'RuntimeError: *Preparing' /tmp/immich-ml-341/ml-before.log | grep -oE '/cache/[A-Za-z_-]+/[A-Za-z0-9_.-]+/[a-z]+' \
  | grep -vc 'NO_SUCH_MODEL_REPLAY'                                                     # REPLAY > 0
grep -c -E "Failed to load (visual|textual|detection|recognition) model '(ViT-B-32__openai|buffalo_l)'" /tmp/immich-ml-341/ml-after.log   # GATE == 0
# KNOWN-BAD CONTROL of the identical grep, on a line in the v3.4.1 shape (anchored on the short
# "Failed to load ... model '<name>'" prefix, which Rich cannot wrap; ", clearing cache:" is not matched):
echo "Failed to load visual model 'ViT-B-32__openai', clearing cache: e" \
  | grep -c -E "Failed to load (visual|textual|detection|recognition) model '(ViT-B-32__openai|buffalo_l)'"   # REPLAY == 1
echo "Failed to load recognition model 'LATIN__PP-OCRv5_mobile', clearing cache: e" \
  | grep -c -E "Failed to load (visual|textual|detection|recognition) model '(ViT-B-32__openai|buffalo_l)'"   # NEGATIVE == 0 (OCR is not a gated model)
kubectl exec -n media deploy/immich-machine-learning -- sh -c 'df -h /cache | tail -1; ls -d /cache/*/*/*/openvino/*/' \
  | tee /tmp/immich-ml-341/cache-after.txt
diff /tmp/immich-ml-341/cache-before.txt /tmp/immich-ml-341/cache-after.txt && echo CACHE_SAME
```
PASS: device list contains `'GPU'` with ORT `1.30.0`; both CONTROL lines hold; both GATE lines
read `0`; all three REPLAY lines and the NEGATIVE line print their stated value; free space on `/cache` at least 8G.
A REPLAY that prints the wrong value means the matching gate cannot fail: treat the gates as
unproven (never a pass) and stop before the server plan.
Replays measured locally 2026-11-16 (zsh, macOS BSD grep):
- `echo "['CPU']" | grep -c "'GPU"` -> `0`; control `echo "['CPU', 'GPU']" | grep -c "'GPU"` -> `1`.
- clearing-cache gate: known-bad CLIP line -> `1`; OCR-model line -> `0` (run locally, see below).
- Preparing replay against a live v3.3.6 log captured 2026-11-16 (4456 lines): real exclusion
  -> `0`, `NO_SUCH_MODEL_REPLAY` exclusion -> `21` (all `/cache/ocr/LATIN__PP-OCRv5_mobile/recognition`).
  The count in the window will differ with log length; only "non-zero" is the criterion.
Why each can fail:
- Device check: upstream `immich_ml/sessions/ort.py` (`openvino_device`, unchanged in v3.4.1)
  returns `GPU.<id>` only when `get_available_openvino_device_ids()` lists a GPU and otherwise
  falls back to `CPU` without an info-level log. A pod without the i915 device, or an image that
  lost the GPU plugin, prints `['CPU']` -> grep `0` (replayed above).
- The two CONTROL lines guard the logging rewrite. If `LOG_CONFIG` did not take, the banner and
  the `Loading ... model` lines are missing and the two GATE zeros would be zeros over an empty
  capture. A CONTROL miss means the gates are unproven, never a pass. On the old pod the banner
  grep for `26.2.0` reads `0` (it prints `Starting gunicorn 25.3.0`) and the model-load count
  reads `9`.
- The load-failure gate matches the stable prefix `Failed to load <type> model '<name>'` (not the
  Rich-wrapped tail `clearing cache`), so a wrapped line still counts; the message changed from
  `. Clearing cache.` to `, clearing cache: <error>`. On a load failure upstream `main.py`
  unloads the model, deletes its cache directory and downloads it again; a hit on a CLIP or face
  model means v3.4.1 could not load a model that v3.3.6 loaded. Upstream v3.4.1 `main.py` format:
  `Failed to load {model type, '_' replaced by ' '} model '{name}', clearing cache: {e}`, so a
  CLIP visual failure reads `Failed to load visual model 'ViT-B-32__openai', clearing cache: ...`;
  the replay feeds exactly that shape through the gate pipeline.
- The Preparing gate only proves something if its extraction still matches; the replay against
  `ml-before.log` (which holds the known OCR-recognition failures) shows it does.
- `CACHE_SAME` is informational. A changed `df` line alone is normal; a NEW directory key next
  to `12.71.4-112eu` means OpenVINO recompiled for a different driver or runtime, which
  contradicts the upstream diff: record it and treat the first search or job as slow, not broken.

4.4 Server-side view (secondary, not a gate on its own). The server logs
`Machine learning request '...' failed` when ML answers badly:
```bash
SINCE=$(kubectl -n media get pod -l app.kubernetes.io/name=immich-machine-learning -o jsonpath='{.items[0].status.startTime}')
kubectl -n media logs deploy/immich-server -c main --since-time="$SINCE" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -E "Machine learning request '" | grep -vc "request '{\"ocr\""
```
Baseline over the 13 h before 2026-11-13 10:00: `2` (one AssetDetectFaces event at 00:01, two
lines) next to 34 OCR lines from the known-broken OCR model. Expect `0` shortly after the roll;
any non-OCR line that appears after the new pod started needs reading before the window closes,
because §4.3 only covers the models it probed.

4.5 Metrics and alerts:
CONTROL: metric kube_pod_container_info — exactly one series for the ML pod with
`image_spec` ending `:v3.4.1-openvino` (measured 2026-11-13: that query is EMPTY and the
`:v3.3.6-openvino` form returns `1`, so the gate fails today).
```bash
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=count(kube_pod_container_info%7Bnamespace%3D%22media%22%2Cpod%3D~%22immich-machine-learning-.*%22%2Cimage_spec%3D~%22.*%3Av3.4.1-openvino%22%7D)'
```
PASS: `"value":[<ts>,"1"]`. FAIL: `"result":[]` (scrape lost or old image) or `"2"`.
CONTROL: metric kube_pod_status_ready — `sum(kube_pod_status_ready{namespace="media",pod=~"immich-machine-learning-.*",condition="true"})` reads `1` (EMPTY or `0` = FAIL; reads `1` today).
```bash
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=sum(kube_pod_status_ready%7Bnamespace%3D%22media%22%2Cpod%3D~%22immich-machine-learning-.*%22%2Ccondition%3D%22true%22%7D)'
```
CONTROL: alertname ImmichMLNotReady — not firing 10 min after Ready (`for: 5m` on ready == 0).
CONTROL: alertname ImmichPodCrashLooping — not firing.
CONTROL: alertname ImmichPodRestarted — not firing 15 min after Ready (a clean Recreate starts
at restartCount 0 and does not trip it; a firing is a real container restart).
```bash
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=ALERTS%7Balertname%3D~%22ImmichMLNotReady%7CImmichPodCrashLooping%7CImmichPodRestarted%22%2Calertstate%3D%22firing%22%7D'
```
PASS: `"result":[]` (live 2026-11-13).
An empty `ALERTS` result is only meaningful if the three rules are loaded (a rule that never
loaded is silently empty too). CONTROL, run once alongside the query above:
```bash
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/rules?type=alert' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);n={r['name'] for g in d['data']['groups'] for r in g['rules']};w=['ImmichMLNotReady','ImmichPodCrashLooping','ImmichPodRestarted'];[print(x,x in n) for x in w];sys.exit(0 if all(x in n for x in w) else 1)" && echo RULES_LOADED || echo RULES_MISSING
```
PASS: three `True` lines and `RULES_LOADED` (measured 2026-11-16: all three `True`). FAIL:
any `False` / `RULES_MISSING` (the ALERTS gate is then blind for that alert), or a JSON error
(Prometheus unreachable: the gate is unproven, not passed).

4.6 HelmRelease settled on the new revision:
```bash
kubectl get helmrelease immich-machine-learning -n media -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.conditions[?(@.type=="Ready")].message}'
```
PASS: `True Helm upgrade succeeded ...`. FAIL: `False`, or a message naming a rollback (Helm's
`upgrade.remediation.retries: 3` rolled the release back to v3.3.6 while git says v3.4.1: go
to §5).

4.7 Post-window: the next sweep re-rates F-f7fa90d3 and re-scans the image against
v3.4.1-openvino, which is what decides the security findings F-ad843a10 and F-1d38b927. Close
each with `runbooks/policy-cli.py finding close <id> --commit $ML_BUMP` only once the sweep
agrees for that id (`finding show <id>` no longer reported against the new image). If the
re-scan still reports either one on v3.4.1-openvino, leave it open and note it in the window
report: the bump did not remedy it and it goes back to triage, not to an AR by default.

## 5. Rollback

Nothing here is forward-only: the Deployment is stateless and the `/cache` layout code did not
change, so v3.3.6 reads the cache v3.4.1 used.

5.1 Revert the ML commit:
```bash
git revert --no-edit $ML_BUMP
git log -1 --format=%s && git show --stat HEAD   # Revert of YOUR commit; only machine-learning-helmrelease.yaml
git push
```
If `git revert` refuses (shared index dirty), make the inverse edit (dry-tested 2026-11-13:
restores the file byte-for-byte) and commit it with `--only`:
```bash
sed -i '' \
  -e 's|^\([[:space:]]*tag: \)v3\.4\.1-openvino$|\1v3.3.6-openvino|' \
  -e 's|swap to the plain `v3\.4\.1` (CPU) tag|swap to the plain `v3.3.6` (CPU) tag|' \
  kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml
git commit --only kubernetes/apps/media/immich/app/machine-learning-helmrelease.yaml \
  -m "revert(immich-ml): back to v3.3.6-openvino (plan immich-machine-learning-3.4.1 rollback)"
git log -1 --format=%s && git show --stat HEAD && git push
```

5.2 Confirm the cluster is back:
```bash
kubectl rollout status deploy/immich-machine-learning -n media --timeout=15m
kubectl get pod -n media -l app.kubernetes.io/name=immich-machine-learning \
  -o jsonpath='{.items[0].status.containerStatuses[0].imageID}'
```
PASS: imageID ends `sha256:035c30de002da9d4d4ae3872107bb9d8e195ead1c1f9fd470a2b0149ed37aec1`,
then §4.3 probes print `TEXT_PASS` / `VISUAL_PASS` and §4.5 alerts read `"result":[]`. The
v3.3.6-openvino image is still in the containerd store of k8s-nuc14-01 and k8s-nuc14-03
(2026-11-13), so the rollback only pulls if the pod lands on k8s-nuc14-02.

5.3 If a model's cache directory was cleared during the failed attempt (§4.3 `clearing cache`
gate), the reverted pod downloads it again on first use. That needs outbound access to the
model host and a few minutes; it is not data loss.

5.4 Alternative only if the OpenVINO path alone is broken and the operator prefers to stay on
v3.4.1: the SOP's CPU fallback, plain tag `v3.4.1` (index digest
`sha256:8adebf414256f6e4f837bfbb66fa94f14f4da7260e3a1d65cbba49e4e35d8764`, 2026-11-13).
Operator's choice, not the default; inference then runs on CPU under the `cpu: "3"` cap.

5.5 If the server is already on v3.4.1 when this is rolled back: leave the server alone. ML
v3.3.6 under server v3.4.1 works with the current image settings; do not switch the preview or
thumbnail format to JPEG XL until ML is on v3.4.x again (§1).

## 6. Interference notes

- **Order against `immich-server-3.4.1`: this plan first.** They may share a window (no
  `conflicts_with` between them, deliberately), but the server tag must not move until §4 here
  has passed. The sibling should carry `depends_on: [immich-machine-learning-3.4.1]`; this file
  does not name the sibling in frontmatter because it did not exist when this was written
  (a dead ref fails `--validate`).
- **Do not merge grouped PR #531.** It would land the server's three new migrations in the same
  commit as this tag, without the server plan's dump and restore proof, and the pair could then
  only be reverted together (the 2026-10-12 shape).
- **Step 0 must not batch this.** The `*immich*` deny rule keeps `auto-update.py` off it; if the
  ML tag has moved by the time this runs, premise `ml-image-is-v3.3.6-openvino` fails and the
  plan is stale.
- **Pull time is unmeasured.** The target is 650 MB compressed for linux/amd64, 12 layers of
  which 5 are shared with v3.3.6-openvino, so about the whole image is fetched; it is cached on
  no node. Event history for earlier pulls has expired. ML is down for the pull plus about a
  minute of start (strategy Recreate; `upgrade.timeout: 20m`; the startup probe allows 10 min
  after the container starts). Record the measured duration (§3.3).
- **Node placement is not pinned.** No nodeSelector or affinity; the pod is on k8s-nuc14-01
  today and can land on any node after the Recreate (the Longhorn volume follows, 2 replicas,
  attached and healthy). The manifest comments that reason about k8s-nuc14-03 describe an older
  placement.
- **i915 slots.** Each node advertises 5. k8s-nuc14-01 has all 5 in use today (immich-ml,
  immich-server, jellyfin, makemkv, plex); the Recreate frees one before it asks for one, so the
  pod fits back. `ci-runner` GPU e2e jobs take slots on -02 and -03 for minutes at a time. Hence
  `helm-drift-detection` (intel-gpu-plugin roll), `frigate-reolink-go2rtc-flv`,
  `talos-power-tuning-ab` and `talos-linux-1.14.5` in `conflicts_with`.
- **`longhorn-1.13.0`** must not run while `immich-ml-cache` detaches and re-attaches.
- **Prometheus is this plan's instrument.** `kube-prometheus-stack-93.3.0` is in
  `conflicts_with` (retargeted 2026-11-16 from the retired 92.22.0); it is `exclusive: true` on
  its own side.
- **Not in `conflicts_with`, on purpose:** `redis-fleet-8.10.3` (rolls `immich-redis`; ML does
  not use redis, the server plan owns that conflict) and `icloud-drive-fleet-2.3.0` (a library
  rescan only adds ML load; no gate here counts jobs).
- **Reciprocity:** none of the seven listed plans names this plan yet; the vetting pass should
  mirror the refs. Corrected 2026-11-16: `talos-power-tuning-ab` does NOT still carry
  `immich-machine-learning-3.2.4` in `conflicts_with` (pruned 2026-10-25, see its frontmatter
  comment); it simply names no immich-ml plan. Only its §6 prose (the
  "kube-prometheus-stack-91.9.0 / immich-ml / jellyfin" note) still mentions 3.2.4. That file is
  listed here for the vetting pass to add the reciprocal ref; this plan does not edit it.
- **Pre-existing, out of scope:** the `LATIN__PP-OCRv5_mobile` recognition model fails to
  prepare on v3.3.6 (17 times in 13 h) and the upstream diff gives no reason to expect v3.4.1 to
  change that. §4 excludes it by name so it neither blocks nor hides behind this bump.
- **No route, Authentik or storage-class change.** The ML Service is ClusterIP; users notice
  only that smart search and new face/OCR jobs pause during the roll.
