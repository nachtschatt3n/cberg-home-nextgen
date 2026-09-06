---
plan_id: scrypted-0.145.0
component: scrypted
pr: null                          # no Renovate PR exists for this target (verified
                                  # 2026-09-06: `gh pr list --state all --limit 200`
                                  # returns no scrypted PR). Renovate tracks this
                                  # image toward the NEWEST tag, which is the
                                  # even-minor dev channel — see §1. The bump is
                                  # therefore made by hand in the window.
kind: image
current: "v0.143.0-noble-full"
target: "v0.145.0-noble-full"
update_type: minor
risk: medium
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [home-automation]
  resources: [helmrelease/scrypted, deployment/scrypted, pvc/scrypted-data, pvc/scrypted-media]
  shared: [igpu-i915]             # NEW TOKEN, introduced here deliberately. The pod
                                  # holds `gpu.intel.com/i915: 1` on k8s-nuc14-02,
                                  # the same physical iGPU Frigate and Immich-ML use
                                  # on that node (Jellyfin/Plex/MakeMKV on -03).
                                  # Nothing here RECONFIGURES the device plugin, but
                                  # a privileged container churning the i915 driver
                                  # is a real shared-hardware perturbation, so it is
                                  # declared rather than left as an empty list.
                                  # Future GPU-touching plans: reuse this exact token
                                  # — `shared` is an INTERSECTION key, so a synonym
                                  # ("gpu", "intel-gpu") silently detects nothing.
depends_on: []                    # the Flux `dependsOn: intel-device-plugin-gpu` is a
                                  # Kustomization dependency, not a plan — see §7.
conflicts_with: [scrypted-0.146.0]  # same Deployment + same image key — never one window
security_ref: F-b885ec1b
capability_change: false          # see §2.4 — this is the one fact a reviewer should
                                  # challenge, and §3 gate G3 falsifies it at runtime.
rollback_class: git-revert        # see §2.3 — established from the live filesystem,
                                  # not assumed.
finding_refs: [F-b885ec1b]
status: vetted   # VETTED 2026-09-06. Premise checked against the LIVE
                 # cluster, not against the plan's own prose:
                 # live koush/scrypted:v0.143.0-noble-full, matching
                 # `current`. NOTE the workload is deployment/scrypted in
                 # home-automation -- the directory is named scrypted-nvr but
                 # the HelmRelease and the release are both named `scrypted`.
window: "sat-attended:2026-09-12"   # AUTO-ASSIGNED 2026-09-06 by window-scheduler (AUTO-NIGHT; earning supervised runs — category not yet graduated)
premises:
  - id: image-is-still-0.143.0
    why: >-
      `current:` claims v0.143.0-noble-full and the rollback target is that tag.
    run: kubectl get deploy -n home-automation scrypted -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: koush/scrypted:v0.143.0-noble-full
  - id: scrypted-volume-still-set
    why: >-
      SCRYPTED_VOLUME=/data was added on 2026-09-06 to fix a persistence
      defect. If it is missing at execution time, something reverted it and
      upgrading on top would put the new version's state somewhere ephemeral.
    run: kubectl get deploy -n home-automation scrypted -o jsonpath='{.spec.template.spec.containers[0].env}'
    expect_contains: SCRYPTED_VOLUME
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/storage-safety.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/auto-update.md
generated: "2026-09-06"
---

## 1. Summary & why held

Move the Scrypted NVR from `koush/scrypted:v0.143.0-noble-full` to
`koush/scrypted:v0.145.0-noble-full` — **one full stable cut, spanning ten
months and 242 upstream commits** (`v0.143.0` 2025-10-28 → `v0.145.0`
2026-09-02, `compare` API `total_commits: 242`).

### 1.1 Why this is not the same update the auto-updater held

The held update points at `v0.146.0`, which is upstream's **even-minor
development channel** — parked in `scrypted-0.146.0.md` with
`autonomy_override: human-gated`, and correctly so. `v0.145.0` is a different
thing: it is the current **stable** release. Both facts re-verified from
primary sources on 2026-09-06, not taken from the 0.146 plan:

```bash
# FACT 1 — v0.145.0 is a real, non-prerelease GitHub Release.
curl -s "https://api.github.com/repos/koush/scrypted/releases?per_page=15" | python3 -c \
 "import sys,json;[print(r['tag_name'],r['prerelease'],r['draft'],r['published_at']) for r in json.load(sys.stdin)]"
#   v0.145.0  prerelease=False  draft=False  2026-09-02T15:50:28Z   <-- newest release
#   v0.143.0  prerelease=False  draft=False  2025-10-28T17:13:55Z   <-- what we run
#   (no v0.144.x and no v0.146.0 release entry exists at all)

# FACT 2 — the target tag resolves in the registry, manifest HTTP 200 (not just Hub metadata).
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:koush/scrypted:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  "https://registry-1.docker.io/v2/koush/scrypted/manifests/v0.145.0-noble-full"
#   200 · pushed 2026-09-02T18:58:52Z · amd64 sha256:d8944765068c… (1.07 GB) + arm64
```

Both pass. **Re-run both at execution time** — they are cheap, and a plan that
assumes a tag still resolves is how a window gets spent on `ImagePullBackOff`.

**Correction to `scrypted-0.146.0.md` §1, worth carrying forward:** that plan
says the odd-minor pattern was "verified across the last 10 release cycles,
v0.127 through v0.145". That is true *as stated*, but it is not a structural
upstream rule — `v0.118.0`, `v0.120.0`, `v0.122.0`, `v0.124.0` and `v0.126.0`
all carry formal `prerelease: false` releases with **even** minors. The pattern
only holds from v0.127 (2025-01) onward. So the correct gate is, and stays,
*"does a `prerelease: false` GitHub Release exist for this exact tag?"* — never
*"is the minor odd?"*. For `v0.145.0` the answer is yes, checked directly above.

### 1.2 Why it isn't auto-safe

`runbooks/auto-update-policy.yaml` carries an explicit deny rule
`match: "*scrypted*"` whose reason ends *"A stable odd-minor bump is planned in
a window, never unattended."* That rule is what keeps the even-minor dev builds
out of the nightly Step-0 auto-apply, and **it must stay after this bump**
(§7). The consequence is that even a legitimate stable bump can only arrive
through a plan — this one.

### 1.3 Breaking-change review, v0.143.0 → v0.145.0

Read from the `v0.145.0` release body (which spans the whole gap — it contains
the `install v0.143.0` post-release commits) plus a direct diff of the image
recipe at both tags. Four things in this span can actually change behaviour:

1. **GStreamer is REMOVED from the `-full` image.** Primary evidence, a diff of
   `install/docker/Dockerfile.full` between the two tags — the following block
   is deleted at v0.145.0:
   ```
   -RUN apt-get -y install libcairo2-dev libgirepository1.0-dev
   -RUN apt-get -y install \
   -    gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
   -    gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-vaapi
   -RUN apt-get -y install python3-gst-1.0
   ```
   matching upstream commits `be4b772` *"remove gstreamer"* and `34f0529`
   *"prefer libav for stability"*. Scrypted's `python-codecs` plugin offers
   GStreamer as one decoder backend; on any install where a camera is pinned to
   it, that backend disappears and decoding falls back to libav.
   **Impact here: none — verified zero plugins installed (§2.2).** This is the
   single most consequential item in the span and the reason §3 gate G3 exists.
2. **AMD OpenCL removed from the full image** (`- RUN curl … install-amd-graphics.sh`,
   moved into `Dockerfile.amd`). We are Intel-only; no impact.
3. **Intel graphics stack rebased.** `install-intel-graphics.sh` moves the
   legacy compute-runtime from `24.35.30872.22` → `24.35.30872.36` and IGC
   `1.0.17537.20` → `1.0.17537.24` (OpenCL/Level-Zero, i.e. the OpenVINO path).
   Note the Dockerfile fetches that script from **`main`**, not from the tag —
   so the image's GPU layer is not fully determined by the version string.
   That is precisely why §5's GPU check is a live hardware probe rather than a
   release-note reading.
4. **Node.js 22.21.0** (`b4b17d4`), and a repo-wide TypeScript `strict` /
   `strictNullChecks` migration that itself needed a follow-up fix
   (*"restore null-tolerance lost in strictNullChecks migration"*, #2060). Plus
   feature/plugin work that all lives in plugin code paths: new privacy mode,
   RTMP support, detection models migrated to Hugging Face with a changed
   default model, HomeKit/Reolink/Unifi-Protect/Tuya plugin bumps.

**No database or state migration is documented, and none is reachable here** —
see §2.3. The `LevelDocument._id`/`_documentType` commits are TypeScript type
tightening, not an on-disk schema change.

### 1.4 Security driver

AR-081 accepts the residual on the *current* image and states its own review
trigger verbatim: *"Accepted; re-measure when upstream promotes a new stable."*
`v0.145.0`, published 2026-09-02, **is** that promotion — so this plan is the
action AR-081 asked for, not an unrelated bump.

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-b885ec1b** (`security` / severity `accepted`).
> Full detail (CVE IDs, counts, exposure, exploitability) lives on the
> finding record — it is deliberately not reproduced here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-b885ec1b`
> - CLI: `runbooks/policy-cli.py finding show F-b885ec1b`
>
> See `docs/sops/vulnerability-disclosure.md` before adding any
> vulnerability detail to a committed file.

After execution, AR-081 and the related image findings must be **re-measured,
not assumed cleared** (§5.5).

## 2. Blast radius, state, and the two derived facts

### 2.1 Privilege and hardware coupling (carried from `scrypted-0.146.0.md`, re-verified)

Confirmed against the live `deployment/scrypted` and the rendered pod spec on
2026-09-06:

- **Privileged**: `securityContext.privileged: true`, `capabilities.add: [SYS_ADMIN]`,
  `allowPrivilegeEscalation: true`, `runAsUser/Group: 0`. Full container
  capability on the node — this is the reason AR-081 refuses the dev channel and
  the reason `risk: medium` survives despite the app holding no data (§2.5).
- **iGPU**: `gpu.intel.com/i915: 1` in **both** requests and limits, satisfied by
  the cluster-wide `intel-device-plugin-gpu`. Live consumers, measured:

  | Node | i915 alloc | Consumers |
  |---|---|---|
  | k8s-nuc14-01 | 0 / 5 | — |
  | k8s-nuc14-02 | 3 / 5 | **scrypted**, **frigate**, immich-machine-learning |
  | k8s-nuc14-03 | 4 / 5 | jellyfin, plex, makemkv, immich-server |

  **What a failed start costs them: nothing, by scheduling.** The Deployment's
  strategy is `Recreate` (verified on the live object — app-template's default,
  not set in values), so the old pod fully terminates and returns its i915 slot
  *before* the replacement is scheduled. A `CrashLoopBackOff` or
  `ImagePullBackOff` on the new pod leaves the slot free and does not evict,
  starve, or restart Frigate, Jellyfin, Plex, Immich-ML or MakeMKV. Slot
  headroom is ample on every node.

  **The real shared-hardware exposure is one level down and is not
  Kubernetes-visible**: the device plugin hands out *scheduling slots*, not
  concurrent transcode sessions. A privileged, `SYS_ADMIN` container re-probing
  a rebased Intel compute-runtime (§1.3 item 3) shares the physical render node
  `/dev/dri/renderD128` on k8s-nuc14-02 with **Frigate, which is a live NVR with
  real cameras**. A driver-level wedge there is the one way this plan can hurt
  something that matters. Nothing observed suggests it is likely; it is the
  reason `touches.shared` is not `[]`.

- **`/dev/dri` — correction to `scrypted-0.146.0.md` §2.** That plan lists
  "hostPath `/dev/dri`" as the passthrough mechanism. The HelmRelease *declares*
  `extraVolumes`/`extraVolumeMounts` for it, but those keys are **inert on
  app-template 5.1.0** — the rendered Deployment has exactly two volumes
  (`data`, `media`) and no `dev-dri` mount. GPU access today comes entirely from
  the device plugin (which bind-mounts the `by-path` entries) plus `privileged`.
  It works — `card0` and `renderD128` are present in the container and VA-API
  encodes (§5.2 baseline). **Do not "fix" the dead keys in this plan**: they are
  harmless today and touching them changes the device-access path in the same
  window as an image bump, which would make a failure un-bisectable.

### 2.2 Storage — and what is actually on it

- `scrypted-media` → `cifs-scrypted-media` (`//NAS/scrypted`, `subdir: /media`,
  `reclaimPolicy: Retain`) — "Severe" tier in `docs/sops/storage-safety.md`.
  Mounted at `/media`. **Measured: `find /media -type f | wc -l` → `0`, and the
  directory's own mtime is 2025-06-07.** No recordings exist and none ever have.
- `scrypted-data` → `longhorn` dynamic RWX (NFS via share-manager), mounted at
  **`/data`**. **Measured: contains only `lost+found`.**
- **This plan performs no PVC action whatsoever** — no delete, no resize, no
  StorageClass change. The storage-safety 3-step pre-flight is not triggered
  because nothing destructive is planned; the CIFS mount is named here only so
  the window agent knows what must not be touched.
- No external DB, no schema migration; `docs/sops/backup.md` does not apply.

### 2.3 State and the rollback determination — DO NOT SKIP

The rollback class was **established from the live container**, not inferred:

```
SCRYPTED_VOLUME=/server/volume          # from the pod's own env
/server/volume                          # 16 KB total; contains ONLY scrypted.db/
/server/volume/scrypted.db/*            # every file mtime = 2026-09-06 07:23 = pod start
/proc/mounts                            # /data (nfs4), /media (cifs) — and NOTHING on /server
```

**Scrypted's state directory is not on a volume.** `SCRYPTED_VOLUME` is
`/server/volume`, which sits on the container's ephemeral overlay layer, while
the `scrypted-data` PVC is mounted at `/data` and is empty. The LevelDB store
was created 8 hours ago, at this pod's start — it is recreated from scratch on
every restart, and today's pod has 0 restarts because it is 8 hours old.

Three consequences, in order of importance:

1. **`rollback_class: git-revert` is correct, with evidence.** A downgrade
   cannot "find migrated state", because no state survives the restart the
   upgrade itself performs. Reverting the tag returns the cluster to a
   byte-identical starting condition. This is the strong form of git-revert, not
   the assumed form.
2. **The upgrade cannot destroy anything a restart would not already destroy.**
   That, not optimism, is why §2.5 rates this below the 0.146 plan.
3. **This is a latent defect in the deployment, and it is OUT OF SCOPE here.**
   `SCRYPTED_VOLUME` is not pointed at the PVC, so the NVR silently cannot keep
   cameras, plugins, users or settings across a restart. Fixing it is a
   behaviour change with its own risk profile and must be its own plan/decision
   — **do not fold it into this window.** Note that fixing it would also flip
   this plan's `rollback_class` away from `git-revert`, because a downgrade
   would then meet persisted state written by the newer version.

### 2.4 `capability_change: false` — the fact, and how it is falsifiable

Declared **false**, and this is the fact a reviewer should attack hardest.
Reasoning, stated so it can be checked rather than trusted:

- Every capability delta in this span (GStreamer removal, changed default
  detection model, Hugging Face model sourcing, privacy mode, RTMP, plugin
  bumps) lands in **plugin code paths**.
- This instance has **no plugins installed** (`/server/volume` contains no
  `plugins/` directory and totals 16 KB) and **no configured devices** (empty
  LevelDB, zero media files). The core server with no plugins serves a login
  page and nothing else.
- Therefore no user-visible behaviour of *this deployment* changes.

If that premise is false at execution time, the declaration is false. §3 gate
**G3 tests the premise and aborts** rather than letting a stale fact carry an
unattended run.

### 2.5 Why `risk: medium` — and why not the 0.146 plan's reasoning

`scrypted-0.146.0.md` rates the same operation `medium` on the grounds of
"cameras actively recording" and a "real coverage gap" during the restart.
**That premise does not hold** (§2.2, §2.3): there are no cameras, no
recordings, and no persisted configuration, so there is no coverage to lose and
no data to lose. On its own that argues for `low`.

It stays **`medium`** for a different, verified reason: a privileged
`SYS_ADMIN` container re-initialising a rebased Intel compute-runtime shares the
physical iGPU on k8s-nuc14-02 with Frigate, which *is* a live NVR (§2.1).
The blast radius that matters is the neighbour, not the app.

## 3. Pre-checks

Run all of these. **G1–G3 are ABORT gates**, not informational.

```bash
cd /Users/mu/code/cberg-home-nextgen
POD=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted \
        -o jsonpath='{.items[0].metadata.name}')

# --- G1 (ABORT) — re-verify both §1 facts. Do not proceed on anything but a
#     prerelease:false release AND a 200 manifest.
curl -s "https://api.github.com/repos/koush/scrypted/releases/tags/v0.145.0" | python3 -c \
 "import sys,json;d=json.load(sys.stdin);print(d['tag_name'],'prerelease',d['prerelease'],'draft',d['draft'])"
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:koush/scrypted:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  "https://registry-1.docker.io/v2/koush/scrypted/manifests/v0.145.0-noble-full"

# --- G2 (ABORT) — the hard Flux dependency must be healthy, or the HelmRelease
#     will not reconcile at all (ks.yaml: dependsOn intel-device-plugin-gpu).
flux get kustomization -n flux-system intel-device-plugin-gpu
kubectl get pods -n kube-system -l app.kubernetes.io/name=intel-device-plugin-gpu

# --- G3 (ABORT) — FALSIFY the capability_change:false premise (§2.4).
#     Expected: no plugins dir, ~16K volume, 0 media files.
kubectl exec -n home-automation $POD -- sh -c \
  'ls /server/volume; echo "--- du ---"; du -sk /server/volume; echo "--- media ---"; find /media -type f | wc -l'
#   If a `plugins/` directory exists, /server/volume is materially larger than
#   ~16K, or the media count is > 0, then this instance HAS BEEN CONFIGURED
#   since 2026-09-06. STOP. Do not execute. Re-derive the plan: capability_change
#   becomes true (GStreamer removal + default-model change now reach live code),
#   rollback_class must be re-established against real state, and §5 must gain
#   the camera-enumeration and recording assertions this plan cannot currently
#   make honestly.

# --- Clean pre-state (informational)
flux get helmrelease -n home-automation scrypted
kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted -o wide
kubectl get pod -n home-automation $POD -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
git -C /Users/mu/code/cberg-home-nextgen status --porcelain \
  kubernetes/apps/home-automation/scrypted-nvr/

# --- BASELINES for §5. Capture these BEFORE touching anything.
kubectl exec -n home-automation $POD -- ffmpeg -hide_banner -encoders 2>/dev/null \
  | grep -c vaapi                                   # baseline measured 2026-09-06: 7
kubectl exec -n home-automation $POD -- sh -c \
  'ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -f lavfi -i testsrc=size=320x240:rate=5:duration=1 -vf format=nv12,hwupload \
     -c:v h264_vaapi -f null - && echo VAAPI_ENCODE_OK'
#   baseline measured 2026-09-06 on v0.143.0: VAAPI_ENCODE_OK
kubectl logs -n home-automation $POD | grep -E '^Version:' | tail -1   # -> 0.143.0
RESTART_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "RESTART_TS=$RESTART_TS"

# --- Alert noise suppression (docs/sops/application-update.md §Step 1)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"home-automation","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"Scrypted.*|Kube(Pod|Deployment).*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"operator",
  "comment":"scrypted v0.143.0 -> v0.145.0 image bump — rollout noise. auto-expires 2h"}'
runbooks/update-marker.sh add scrypted home-automation 2 "scrypted v0.143.0->v0.145.0"
```

## 4. Steps

GitOps only. One file changes; one line in it changes.

1. Edit `kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml`,
   `spec.values.controllers.scrypted.containers.app.image.tag`:
   ```yaml
   image:
     repository: koush/scrypted
     tag: v0.145.0-noble-full     # was: v0.143.0-noble-full
   ```
   Change nothing else. In particular do **not** touch the inert
   `extraVolumes`/`extraVolumeMounts` block (§2.1) and do **not** add
   `SCRYPTED_VOLUME` (§2.3) — both are separate decisions.

2. Confirm the diff is exactly one line before committing:
   ```bash
   git -C /Users/mu/code/cberg-home-nextgen diff --stat \
     kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml
   git -C /Users/mu/code/cberg-home-nextgen diff \
     kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml
   ```

3. Commit with `--only` (shared worktree — see CLAUDE.md) and push:
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git commit --only kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml \
     -m "feat(scrypted): v0.143.0-noble-full -> v0.145.0-noble-full (current upstream stable)"
   git show --stat HEAD        # every file here must be yours
   git push
   ```
   Keep CVE detail out of the commit message (`docs/sops/vulnerability-disclosure.md`).

4. Watch Flux reconcile. No manual `flux reconcile` — the GitRepository webhook
   plus the 30m HelmRelease interval covers it:
   ```bash
   flux get helmrelease -n home-automation scrypted --watch
   kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted -w
   ```
   The strategy is `Recreate`: expect the old pod to terminate fully before the
   new one appears. That is correct, not a stall. Budget for a cold ~1.07 GB
   pull on k8s-nuc14-02.

5. Do not hand-delete pods mid-rollout. If it wedges, work
   `docs/sops/application-update.md` §7 before improvising. Note the HelmRelease
   has `upgrade.remediation.strategy: rollback, retries: 3` — Helm may roll the
   values back on its own while git still says v0.145.0, so always confirm the
   running `imageID` rather than the manifest (§5.1).

## 5. Verification

### 5.1 Floor (shape checks — necessary, and not sufficient)

```bash
POD=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted \
        -o jsonpath='{.items[0].metadata.name}')
kubectl get helmrelease -n home-automation scrypted \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted
kubectl get pod -n home-automation $POD \
  -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'   # NEW digest, not the tag string
```

### 5.2 CONTENTS ASSERTION (primary — this is the one that carries the plan)

> **CONTENTS ASSERTION: hardware VA-API encode on the shared iGPU still
> actually engages** — measured by initialising a VA-API device on
> `/dev/dri/renderD128` and running a real `h264_vaapi` encode inside the new
> container, compared to the baseline captured in §3 (`VAAPI_ENCODE_OK`, and 7
> VA-API encoders, measured on v0.143.0 on 2026-09-06).

```bash
kubectl exec -n home-automation $POD -- ffmpeg -hide_banner -encoders 2>/dev/null | grep -c vaapi
#   MUST be 7 (av1, h264, hevc, mjpeg, mpeg2, vp8, vp9). Fewer = codec support lost.
kubectl exec -n home-automation $POD -- sh -c \
  'ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -f lavfi -i testsrc=size=320x240:rate=5:duration=1 -vf format=nv12,hwupload \
     -c:v h264_vaapi -f null - && echo VAAPI_ENCODE_OK'
#   MUST print VAAPI_ENCODE_OK.
```

This is the assertion the change could genuinely break and a Ready pod would
never reveal: v0.145.0 rebases the Intel compute-runtime and pulls that layer
from `main` rather than the tag (§1.3 item 3). A container whose GPU stack
regressed starts perfectly, passes every probe, reports Ready — and every
transcode silently falls back to software. `-init_hw_device` fails outright when
the driver is broken, and the encode fails if the render node is unusable, so
neither can go green on a broken GPU.

### 5.3 CONTENTS ASSERTION (secondary — proves new bytes, not a new tag)

> **CONTENTS ASSERTION: the running server is the new build** — measured by the
> server's own version banner and by the disappearance of GStreamer, compared to
> the §3 baseline (`0.143.0`; `gst-launch-1.0` present).

```bash
kubectl logs -n home-automation $POD | grep -E '^Version:' | tail -1
#   MUST read 0.145.0 (v0.143.0 printed "Version:       : 0.143.0")
kubectl exec -n home-automation $POD -- sh -c 'command -v gst-launch-1.0 || echo GSTREAMER_ABSENT_AS_EXPECTED'
#   MUST print GSTREAMER_ABSENT_AS_EXPECTED — it is present on v0.143.0, and the
#   Dockerfile diff (§1.3 item 1) says it must be gone. Present => the pod is
#   still the old image (or Helm rolled back, §4 step 5): treat as NOT UPGRADED.
```

### 5.4 Service reachability

```bash
kubectl -n home-automation port-forward svc/scrypted 11080:11080 &
curl -s -o /dev/null -w 'http=%{http_code} bytes=%{size_download}\n' http://localhost:11080/
#   Expect a 2xx/3xx with a non-trivial body — not a 0-byte response.
```

### 5.5 Honest note on cameras and recordings — read this before writing "verified"

The instinctive NVR assertions ("cameras enumerate", "recordings are being
written", "new files appeared under `/media` after the restart") **cannot be
made honestly on this deployment, and must not be faked green.** There are zero
configured devices, zero installed plugins and zero media files (§2.2, §2.3),
so every one of those checks is vacuous here: a `find /media -newermt …`
returning nothing is indistinguishable from a total failure to record. That is
exactly the failure mode `docs/sops/verification-contents-not-shape.md` names —
*a ceiling without a floor*, and a health signal that cannot tell "working" from
"empty". `scrypted-0.146.0.md` §5 makes precisely that check its required
contents assertion; on today's cluster it would pass while proving nothing.

So: the GPU probe (§5.2) is the load-bearing assertion. Record the media/device
counts as an unchanged **inventory diff** (still 0, still 16 KB) and label them
as such:

```bash
kubectl exec -n home-automation $POD -- sh -c \
  'ls /server/volume; du -sk /server/volume; find /media -type f | wc -l'
#   Expected identical to the §3 G3 baseline. If G3 passed and this differs,
#   something wrote state during the window — investigate before closing.
```

If G3 ever fails (i.e. the instance has been configured), §5.2–§5.4 stop being
sufficient and the camera-enumeration and recording-continuity assertions become
mandatory — but so does re-deriving the plan (§2.4), so that is an abort, not an
extra step.

### 5.6 Close-out

```bash
curl -s -X DELETE localhost:9093/api/v2/silences/<id>
runbooks/update-marker.sh clear scrypted
```
Then re-measure the security posture rather than assuming the bump cleared it:
```bash
source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up
runbooks/policy-cli.py finding list --grep scrypted
runbooks/policy-cli.py risk show AR-081
```
AR-081's own justification names "re-measure when upstream promotes a new
stable" as its review trigger, and its description needle (`koush/scrypted`) is
version-agnostic, so **suppression continues automatically across this bump** —
which is why the re-measure has to be deliberate. Refresh AR-081's
`last_reviewed_at` (and its justification, if the residual changed) via
`runbooks/policy-cli.py risk`. Keep the numbers in the DB, not in this file.

## 6. Rollback

Concrete, and genuinely sufficient — see §2.3 for why nothing else is needed.

```bash
cd /Users/mu/code/cberg-home-nextgen
git log --oneline -5 -- kubernetes/apps/home-automation/scrypted-nvr/app/helmrelease.yaml
git revert --no-edit <the-bump-commit>       # or: git checkout <pre-bump-sha> -- <file>
git show --stat HEAD                          # confirm only the one file
git push
flux reconcile helmrelease -n home-automation scrypted --force   # only if the interval has not fired
```

Confirm the cluster is actually back — by digest and by the two contents
assertions, not by "Ready":

```bash
POD=$(kubectl get pods -n home-automation -l app.kubernetes.io/name=scrypted -o jsonpath='{.items[0].metadata.name}')
kubectl get pod -n home-automation $POD -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
#   MUST be the v0.143.0 digest recorded in §3 (docker.io/koush/scrypted@sha256:f23251da…)
kubectl logs -n home-automation $POD | grep -E '^Version:' | tail -1     # -> 0.143.0
kubectl exec -n home-automation $POD -- sh -c 'command -v gst-launch-1.0'  # -> /usr/bin/gst-launch-1.0
kubectl exec -n home-automation $POD -- sh -c \
  'ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -f lavfi -i testsrc=size=320x240:rate=5:duration=1 -vf format=nv12,hwupload \
     -c:v h264_vaapi -f null - && echo VAAPI_ENCODE_OK'
```

There is **no state-restore leg**: the downgraded container recreates
`/server/volume/scrypted.db` from scratch exactly as the upgraded one did, and
no PVC was written by either. Then clear the silence and marker as in §5.6.

## 7. Interference notes

- **`touches.shared: [igpu-i915]` is a new token, introduced deliberately.**
  `shared` is matched as a set INTERSECTION between plans, so this only detects
  interference if other GPU-holding plans (jellyfin, plex, frigate, immich,
  makemkv, `intel-device-plugin-gpu` itself) adopt the **same spelling**. Please
  reuse `igpu-i915` rather than a synonym. Practical rule for this window: do
  not co-schedule with anything that restarts `intel-device-plugin-gpu` or with
  a GPU-heavy plan on **k8s-nuc14-02** (Frigate, Immich-ML).
- It is **not** in `autonomy-policy.yaml`'s `forbid_shared` (`[storage,
  longhorn]`), so declaring it honestly costs no autonomy. That is the point:
  there was no incentive to leave the list empty.
- **`intel-device-plugin-gpu` is a hard Flux dependency, not a plan
  dependency.** `ks.yaml` sets `dependsOn: {name: intel-device-plugin-gpu,
  namespace: kube-system}`. It is deliberately absent from `depends_on:` because
  a dead plan-id ref is a validation error; gate G2 covers it instead. If that
  Kustomization is unhealthy or mid-reconcile, this HelmRelease will not apply
  at all — the symptom is "nothing happens", not a failure.
- **`conflicts_with: scrypted-0.146.0`** — same Deployment, same image key.
  `scrypted-0.146.0.md` is parked with a DO-NOT-EXECUTE verdict and
  `autonomy_override: human-gated`; the two must never share a window, and this
  plan does **not** supersede it. Per its §7, its `target:` stays truthful to
  what was held; when a `prerelease:false` release for v0.146.x-or-later
  appears, that plan is retired and re-planned against the new tag.
- **Do NOT remove the `*scrypted*` deny rule from
  `runbooks/auto-update-policy.yaml` as part of this work.** It is what keeps
  the even-minor dev channel out of the nightly Step-0 auto-apply, and it stays
  correct after this bump. Its `reason` text will read slightly stale (it names
  v0.144.x); refreshing that wording is a separate docs commit, and leaving it
  is safe.
- **Renovate will keep proposing the newest tag**, which is the dev channel.
  A newer even-minor on Docker Hub is not evidence of a newer stable — apply
  gate G1 (a `prerelease: false` Release for that exact tag), never the
  odd/even heuristic (§1.1).
- **Out of scope, flagged for the operator, not to be fixed in this window:**
  (a) `SCRYPTED_VOLUME=/server/volume` is not backed by a PVC, so this NVR
  cannot persist configuration across a restart (§2.3); (b) the HelmRelease's
  `extraVolumes`/`extraVolumeMounts` for `/dev/dri` are inert under
  app-template 5.1.0 (§2.1). Both are real defects; both change behaviour;
  both deserve their own plan.
- **Biggest gotcha for the executor:** do not accept "pod Ready" or even
  "new digest" as success. The failure this bump can actually produce is a
  perfectly healthy container whose Intel GPU stack regressed and whose
  transcodes silently fall back to software. §5.2 is the check that catches it,
  and it has a measured green baseline from before the change.
