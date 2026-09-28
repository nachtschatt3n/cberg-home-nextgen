---
plan_id: makemkv-v26.09.2
component: makemkv
pr: null                              # No Renovate PR. Surfaced by coverage.py as lane=PLAN
                                      # (sweep finding F-0b69c5d9, cycle 58d45ed0).
kind: image
current: "v26.01.1@sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518"
                                      # re-verified live 2026-09-27: deployment image, pod imageID
                                      # docker.io/jlesage/makemkv@sha256:12ce7fc0..., MakeMKV 1.18.2
                                      # (makemkvcon MSG:1005 + init banner), node k8s-nuc14-03.
target: "v26.09.2@sha256:bfdddd29c5a9958da3003df1e673de7ad6915c846723449c76196d4ef6ca1ca2"
                                      # OCI image INDEX digest, read 2026-09-27 from
                                      # registry-1.docker.io (docker-content-digest on HEAD
                                      # manifests/v26.09.2) AND Docker Hub tag API — identical.
                                      # linux/amd64 child: sha256:90ac356ee40f21b7d0672860791820a78594f52df092f063904c3acdb3f56226
                                      # config label org.label-schema.version=26.09.2, created
                                      # 2026-09-23T14:36:15Z. Pin the INDEX digest (house form,
                                      # same as the current pin, which is also an index digest).
update_type: minor
risk: low                             # The hold was a FALSE POSITIVE of the release-notes gate
                                      # (G3 "release notes unavailable": check-all-versions.py has
                                      # no image->repo mapping for jlesage/makemkv and looked up
                                      # the non-existent github.com/jlesage/makemkv). The real notes
                                      # (jlesage/docker-makemkv, 11 releases) contain no breaking
                                      # change and nothing that alters our config (§1). MakeMKV
                                      # 1.18.2 -> 2.0.0 is a major NUMBER only: upstream's own
                                      # changelog says "Almost no changes, just a version bump".
                                      # Single-replica Recreate Deployment, idle most of the time,
                                      # config backed up nightly, git-revert rollback.
est_duration_min: 25                  # pre-checks 5 + edit/commit/push/propagate ~5 + Recreate
                                      # (image pull ~1 GB, init ~1 min) ~5 + gates §4 ~8 + slack 2
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - helmrelease/makemkv             # the edit (kubernetes/apps/media/makemkv/app/helmrelease.yaml)
    - deployment/makemkv              # Recreate: one pod replaced
    - service/makemkv                 # unchanged; endpoints move to the new pod
    - httproute/makemkv               # unchanged; GUI unavailable ~2 min during Recreate
    - pvc/makemkv-config              # longhorn-static RWO 2Gi, volume makemkv-config; remounted,
                                      # settings.conf rewritten by the new MakeMKV on start
    - pvc/makemkv-media               # cifs-makemkv-media, subdir /Transcode, Retain; remounted
                                      # only — NO PVC/PV action of any kind in this plan
  shared: [igpu-i915, media]          # igpu-i915: the pod requests+limits gpu.intel.com/i915: 1
                                      # (token reused from jellyfin-12.1). Node k8s-nuc14-03 has
                                      # 4/5 i915 slots claimed (scrypted, immich-ml, jellyfin,
                                      # makemkv; measured 2026-09-27). Recreate frees our slot
                                      # before the new pod schedules, so no capacity squeeze —
                                      # UNLESS another GPU pod on nuc14-03 recreates at the same
                                      # moment. media: remount of //NAS/media/Transcode (a subdir
                                      # of the shared media export). Read/write only, no delete.
depends_on: []
conflicts_with:
  - jellyfin-12.1                     # same GPU node (nuc14-03) and same namespace; its §4 GPU
                                      # probes and our Recreate must not interleave, and a
                                      # simultaneous Recreate of two i915 pods on nuc14-03 is the
                                      # only way our slot can be taken. Serialize.
  - helm-drift-detection              # its P2 §3.2.0 re-apply rolls the intel-gpu-plugin
                                      # DaemonSet; "NEW GPU pods cannot schedule for ~1 min per
                                      # node" — our Recreate IS a new GPU pod.
  - flux-reconciler-impersonation     # exclusive:true already keeps its slot empty; named so the
                                      # dependency is explicit: this plan's delivery path IS the
                                      # Flux apply that plan re-identities.
  # PARKED 2026-09-27: app-template-5.2.1 is an uncommitted draft from another session (DEAD-REF on main); re-add to conflicts_with once it lands.
  # - app-template-5.2.1                # concurrent draft (2026-09-27) bumping the chart on every
                                      # app-template HelmRelease, including THIS file. Both edit
                                      # kubernetes/apps/media/makemkv/app/helmrelease.yaml; either
                                      # order works, but not in one window: G1-G8 attribute
                                      # a failure to the image and a mixed change breaks that.
  - float-tag-pinning                 # its frontmatter still describes the EXECUTED Batch M
                                      # (component makemkv, resources helmrelease/makemkv). Same
                                      # file; harmless once that programme rotates to Batch O.
exclusive: false
security_ref: null                    # no security driver; F-0b69c5d9 is a version finding.
capability_change: false              # Baseimage 4.11-4.14 ADD a web terminal, web file manager
                                      # and clipboard toggle, but WEB_TERMINAL / WEB_FILE_MANAGER
                                      # default to 0 and we set neither (asserted in §4 G6). No
                                      # user-visible behaviour of ripping changes.
rollback_class: git-revert            # nothing forward-only: settings.conf is a flat key=value
                                      # file, MakeMKV rewrites its header on every start; the
                                      # nightly Longhorn backup of makemkv-config is the backstop.
finding_refs: [F-0b69c5d9]
status: blocked
blocked_reason: "nightly 2026-09-28: image v26.09.2 LANDED and is healthy (656a896a; G1-G4,G7,G8 PASS, G6 works but its noVNC_app_name probe no longer matches the new UI) -- G5 FAIL fail-closed: Recreate rescheduled the pod onto k8s-nuc14-01 (no /dev/sr0; autodiscripper disabled). Not an image fault, not rolled back. Needs operator: nodeSelector k8s-nuc14-03 via git (plan section 6) or an approved pod reschedule; then re-run G5 and retire this plan. G6 probe needs updating (title MakeMKV / noVNC_container)."
window: null
premises:
  - id: image-is-still-v26.01.1
    why: >-
      `current:` and every baseline below (MakeMKV 1.18.2, node, config
      fingerprints) were captured against this exact pin. If the Deployment
      already moved, this plan is stale.
    run: kubectl get deploy -n media makemkv -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: jlesage/makemkv:v26.01.1@sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518
  - id: hr-ready
    why: "A HelmRelease already failing would mask whether the bump itself reconciled."
    run: kubectl get helmrelease -n media makemkv -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: pod-on-the-drive-node
    why: >-
      The optical drive (/dev/sr0) exists ONLY on k8s-nuc14-03 (talosctl ls /dev
      on all three nodes, 2026-09-27) and the Deployment has NO nodeSelector or
      affinity. Gate G5 asserts the new pod lands there too; if the pod is
      already elsewhere today, ripping is already broken and that is a
      different problem to solve first.
    run: kubectl get pod -n media -l app.kubernetes.io/instance=makemkv -o jsonpath='{.items[0].spec.nodeName}'
    expect_exact: k8s-nuc14-03
  - id: no-auto-rip-in-flight
    why: >-
      A Recreate mid-rip kills makemkvcon and loses the partial output (it
      lands in the ephemeral /output volume, see §6). The autodiscripper logs
      "Starting disc rip..." then exactly one "Disc rip terminated ..." line
      (autodiscripper source, lines ~138-143), so starts minus terminations
      is the number of auto-rips in flight. Positive control: the same awk on
      a synthetic "Starting disc rip..." line prints autorips_inflight=1.
      (kubectl exec is not a premise verb, so the process-level and
      GUI-initiated-rip checks live in §2.2 and must also pass.)
    run: kubectl logs -n media deploy/makemkv | awk '/Starting disc rip\./{s++} /Disc rip terminated/{t++} END{print "autorips_inflight=" s-t}'
    expect_exact: autorips_inflight=0
  - id: media-class-still-retain
    why: >-
      storage-safety.md: cifs-makemkv-media is a Severe-tier class. This plan
      performs NO PVC action, but if the class ever reads Delete the executor
      must STOP before touching anything in this namespace.
    run: kubectl get sc cifs-makemkv-media -o jsonpath='{.reclaimPolicy}'
    expect_exact: Retain
  - id: media-subdir-still-transcode
    why: "Structural storage-safety pre-flight: subdir must not be / or empty."
    run: kubectl get sc cifs-makemkv-media -o jsonpath='{.parameters.subdir}'
    expect_exact: /Transcode
  - id: config-volume-healthy
    why: "The rollback backstop is the nightly Longhorn backup of this volume; it must be attached and healthy."
    run: kubectl get volumes.longhorn.io -n storage makemkv-config -o jsonpath='{.status.state}/{.status.robustness}'
    expect_exact: attached/healthy
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/storage-safety.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-27"
review: ready-for-go@2026-09-27   # plan-reviewer ready-for-go 2026-09-27 (7fff8d81 batch)
---

# makemkv v26.01.1 -> v26.09.2 (MakeMKV 1.18.2 -> 2.0.0)

## 1. Summary & why held

Bump `jlesage/makemkv` from `v26.01.1` to `v26.09.2`, digest-pinned to the
multi-arch index `sha256:bfdddd29…ca1ca2`. app-template stays at 5.1.0 (the
5.2.1 chart bump is a separate finding, F-1111d5a4, and is not part of this plan).

### 1.1 Why it was held — a false positive

`coverage.py` routed it to PLAN with: *"G3 could not verify the release notes
(unverified (release notes unavailable))"*. `runbooks/version-check-current.md`
points the notes at `https://github.com/jlesage/makemkv/releases/...`. That repo
does not exist. The image is built from **`jlesage/docker-makemkv`**, and the
image-to-repo map in `runbooks/check-all-versions.py` (around line 543) has an
entry for `jlesage/jdownloader-2` but none for `jlesage/makemkv`. This is a repo
correction, listed in the report. The hold therefore says nothing about how risky
the update is.

### 1.2 Upstream evidence — every release in the span (`gh release view -R jlesage/docker-makemkv`)

| Release | Change (verbatim, abridged) |
|---|---|
| v26.01.2 | "Updated MakeMKV to version 1.18.3." |
| v26.02.1 | baseimage 4.11.0: "Added a web terminal providing shell access to the container." / web file manager in modal / "Improved web services server stability" / TigerVNC 1.16.0, X server 21.1.21 |
| v26.02.2 | baseimage 4.11.1: "Fixed issue where taking ownership of directory would fail." |
| v26.02.3 | baseimage 4.11.2: "Fixed X server failing to find the appropriate Mesa driver on some setups." |
| v26.03.1 | baseimage 4.11.3: xcompmgr output only in debug; self-signed cert SAN |
| v26.07.1 | "Updated MakeMKV to version 1.18.4." + baseimage 4.12.5: optional read-only FS, fastcompmgr, TigerVNC 1.16.2, noVNC 1.7.0, "relative redirects" for reverse proxies |
| v26.07.2 | baseimage 4.12.6: fix for startup failure when the engine mounts files under `/run`; "Read-only filesystem support now requires exposing `/run` as a tmpfs." |
| v26.08.1 | baseimage 4.13.1: host clipboard sync via env var/UI toggle; web UI and services reliability and security |
| v26.08.2 | baseimage 4.13.2 |
| v26.09.1 | baseimage 4.14.0: installable web app (PWA); clipboard sync fix |
| v26.09.2 | "Updated MakeMKV to version 2.0.0." |

Upstream Dockerfile diff `v26.08.2...v26.09.2`: `MAKEMKV_VERSION=1.18.4 → 2.0.0`
and `FROM jlesage/baseimage-gui:alpine-3.19-v4.13.2 → v4.14.0`. Nothing else
changes at runtime apart from a GUI patch that affects only how the help and
purchase links open.

MakeMKV changelog (`makemkv.com/download/history.html`):
- **v2.0.0 (20.9.2026):** "Almost no changes, just a version bump"; "Small improvements and bugfixes".
- v1.18.4 (15.6.2026): small fixes, an armhf crash fix.
- v1.18.3 (25.1.2026): "Updated LibreDrive and AACS runtime".

**What we checked that does NOT affect us:**
- **Web terminal.** It is a root shell inside a *privileged* container, which is
  effectively root on nuc14-03. Upstream baseimage README: `WEB_TERMINAL` "When
  set to `1`, enables access to a terminal", default `0`. We do not set it. Gate
  G6 asserts it stays unset, because an unauthenticated web terminal behind a
  LAN route on this pod would be a serious exposure.
- **Read-only FS / `/run` tmpfs.** This is opt-in and we do not use it.
- **`/output` volume and `take-ownership`.** These are unchanged (the image config
  still declares `Volumes: /config, /output, /storage`).

### 1.3 `MAKEMKV_KEY=BETA` — does a newer MakeMKV need a newer beta key?

On every container start, `/etc/cont-init.d/55-makemkv.sh` runs
`makemkv-update-beta-key`, which scrapes the current key from
`forum.makemkv.com/…t=1053` and writes it to `app_Key` in `/config/settings.conf`.
It does this **regardless of MakeMKV version**. The failure path does not stop
the container: it prints `ERROR: failed to update beta key.` and keeps the key
already in settings.conf.

- The MakeMKV 2.0.0 notes and the forum post do not mention a key format change
  or a new key for 2.0.
- The forum post says the current beta key is "valid until end of September 2026".
  The key in our settings.conf today is that key (compared by prefix only, never
  printed).
- **Scheduling preference: run BEFORE 2026-10-01 if a slot allows.** Then G4 can
  only see the still-valid September key and a forum-fetch failure is harmless.
- **Consequence for scheduling.** If this runs **on or after 2026-10-01**, the
  restart fetches the October key, provided the forum has posted it. If the fetch
  fails, the pod keeps an expired key. **DVD ripping keeps working** (MakeMKV's
  DVD functions are free). **Blu-ray decryption stops** until a later restart
  picks up a key. The bump does not cause this: any restart after month-end has
  the same exposure, and so does *not* restarting, because the running pod holds
  September's key. Gate G4 reads the init line so the executor knows which case
  they are in.
- **Old-version expiry.** An expired MakeMKV beta build reports "application
  version is too old" (a MakeMKV MSG). Moving to the newest version lowers that
  risk. Gate G3 greps makemkvcon output for `too old|expired|evaluation` (case-
  insensitive) and must find none; a pattern control proves that grep can match
  (see G3).

### 1.4 Wiring gotcha — the image is pinned TWICE; only one renders

`helmrelease.yaml` carries a legacy top-level `values.image` block. It also has
legacy top-level `env`, `securityContext` (with `runAsGroup`/`fsGroup`),
`resources`, `extraVolumes` and `extraVolumeMounts`. Separately, it has
`controllers.main.containers.main.image` plus that container's own
env/securityContext/resources. Measured with
`helm template makemkv oci://ghcr.io/bjw-s-labs/helm/app-template --version 5.1.0 -n media -f <values>`:

- Changing **only** the top-level `image.tag` to `BOGUS-legacy-only` produces
  **byte-identical** rendered output (`diff` empty).
- Changing **only** `controllers.main.containers.main.image.tag` changes line 85
  (`image: jlesage/makemkv:BOGUS-controller`).
- The render has mounts `/config` and `/media` only. The `extraVolumes`
  `dev-dri` hostPath and the `/output` mount are **not rendered**. The live pod
  agrees: `/proc/mounts` shows `/config` (Longhorn), `/media` (CIFS `/Transcode`),
  and `/output` on the node's nvme (the image's anonymous VOLUME). `/dev/dri`
  exists only because the container is privileged.

**So the controller block is the only live pin.** §3 edits **both** lines
anyway, with one `sed`, for two reasons. The version tooling reads both paths
(`version-check-current.md` lists `Path: image` and
`Path: controllers.main.containers.main.image` as two rows). If only the live
one moved, the dead one would keep reporting `v26.01.1 → v26.09.2` forever, a
phantom bump that re-dispatches a planner every sweep. And the two stay
textually identical, so a single substitution cannot drift. Deleting the dead
legacy blocks is the right cleanup, but it is out of scope here (§6).

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen && git pull --ff-only

# 2.1 premises (fail-closed; must be 7/7 PASS) — then 2.2, which premises cannot express (kubectl exec)
.venv/bin/python3 runbooks/plan-premises.py makemkv-v26.09.2

# 2.2 no rip in progress — process + recent-file check (NOT the same as premise
#     no-auto-rip-in-flight, which only counts autodiscripper start/terminate log lines;
#     premises cannot run kubectl exec). Re-run immediately before push.
#     rips= catches CLI rips (autodiscripper `makemkvcon ... backup|mkv ...`).
#     recent= is what covers GUI-initiated rips: those run inside `makemkvcon guiserver`
#     (always present, excluded from rips=) and are only visible as files being written
#     under /output (the GUI destination, app_DestinationDir) or /media.
kubectl exec -n media deploy/makemkv -- sh -c 'echo rips=$(ps -o args | grep -E "[m]akemkvcon .*(mkv|backup) " | wc -l | tr -d " ") recent=$(find /output /media -maxdepth 3 -type f -mmin -15 2>/dev/null | wc -l | tr -d " ")'
#   PASS: rips=0 recent=0.  Anything else = STOP. Attended window: ask the operator whether a
#   disc is being ripped before anything else. Unattended/AUTO-NIGHT window: fail closed —
#   do not push, mark the plan not-run, report; never "wait and retry" into a rip.
#   Detector self-test (must print 1, 1, 0 — proves the regex matches both rip forms and not the drive scan):
for s in "/opt/makemkv/bin/makemkvcon -r --decrypt backup dev:/dev/sr0 /output/X" \
         "/opt/makemkv/bin/makemkvcon -r --cache=1 mkv dev:/dev/sr0 all /output" \
         "/opt/makemkv/bin/makemkvcon -r --cache=1 info disc:9999"; do echo "$s" | grep -cE "[m]akemkvcon .*(mkv|backup) "; done

# 2.3 storage-safety pre-flight (informational — NO PVC action is taken)
PV=$(kubectl -n media get pvc makemkv-media -o jsonpath='{.spec.volumeName}') && \
  kubectl get pv $PV -o jsonpath='{.spec.csi.volumeAttributes.subdir}{" reclaim="}{.spec.persistentVolumeReclaimPolicy}{"\n"}'
#   expect: /Transcode reclaim=Retain

# 2.4 backstop backup is fresh (nightly 03:00, cronjob storage/daily-backup-all-volumes)
kubectl get backups.longhorn.io -n storage -l backup-volume=makemkv-config \
  --sort-by=.metadata.creationTimestamp -o custom-columns='N:.metadata.name,S:.status.state,C:.metadata.creationTimestamp' | tail -2
#   PASS: newest row Completed and created within the last 26h.

# 2.5 BASELINE — record these values; §4 compares against them
kubectl exec -n media deploy/makemkv -- sh -c 'sha256sum /config/machine-id | cut -c1-16; grep -E "^app_(DataDir|DestinationDir|DestinationType) " /config/settings.conf; echo keylen=$(sed -n "s/^app_Key = \"\(.*\)\"/\1/p" /config/settings.conf | wc -c | tr -d " ")'
#   2026-09-27 values: machine-id sha 1st16 = a458b6b3fd1c5321, app_DataDir="/config/data",
#   app_DestinationDir="/output", app_DestinationType="2", keylen=69 (never print the key)

# 2.6 NEGATIVE CONTROL for G3 (must FAIL today — proves the version gate can fail):
kubectl exec -n media deploy/makemkv -- sh -c 'T=$(mktemp -d); cp /config/settings.conf $T/; ln -s $T $T/.MakeMKV; echo "app_UpdateEnable = \"0\"" >> $T/settings.conf; env HOME=$T LD_PRELOAD=/opt/makemkv/lib/libwrapper.so /opt/makemkv/bin/makemkvcon -r --cache=1 --noscan info disc:9999 2>&1 | grep "^MSG:1005"; rm -rf $T' | grep -c 'MakeMKV v2\.0\.0'
#   expect 0 (today prints "MakeMKV v1.18.2 linux(x64-release) started")
```

## 3. Steps

The change is one GitOps edit to one file. It uses a single BSD-sed substitution
that rewrites both identical pins (§1.4).

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/media/makemkv/app/helmrelease.yaml

sed -i '' 's|v26\.01\.1@sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518|v26.09.2@sha256:bfdddd29c5a9958da3003df1e673de7ad6915c846723449c76196d4ef6ca1ca2|' "$F"

# must print 2 and 0
grep -c 'v26.09.2@sha256:bfdddd29c5a9958da3003df1e673de7ad6915c846723449c76196d4ef6ca1ca2' "$F"
grep -c 'v26.01.1' "$F"
git diff --stat -- "$F"     # 1 file, 2 insertions(+), 2 deletions(-)
```

Dry-tested on a macOS scratch copy (2026-09-27). The resulting `diff`:

```
35c35
<       tag: v26.01.1@sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518
---
>       tag: v26.09.2@sha256:bfdddd29c5a9958da3003df1e673de7ad6915c846723449c76196d4ef6ca1ca2
158c158
<               tag: v26.01.1@sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518
---
>               tag: v26.09.2@sha256:bfdddd29c5a9958da3003df1e673de7ad6915c846723449c76196d4ef6ca1ca2
```

The rendered-manifest diff (`helm template` app-template 5.1.0, before vs after)
is exactly one line, and `strategy: Recreate` is unchanged:

```
85c85
<           image: jlesage/makemkv:v26.01.1@sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518
---
>           image: jlesage/makemkv:v26.09.2@sha256:bfdddd29c5a9958da3003df1e673de7ad6915c846723449c76196d4ef6ca1ca2
```

Re-run §2.2 immediately before the commit, then commit only this file:

```bash
cat > /tmp/makemkv-msg.txt <<'EOF'
feat(makemkv): image v26.01.1 -> v26.09.2 (MakeMKV 1.18.2 -> 2.0.0)

Digest-pinned to the multi-arch index sha256:bfdddd29...ca1ca2. Both
the live controllers.main.containers.main.image pin and the dead
legacy values.image pin move together (only the controller one
renders under app-template 5.1.0). Plan: makemkv-v26.09.2.
Finding: F-0b69c5d9
EOF
git commit --only kubernetes/apps/media/makemkv/app/helmrelease.yaml -F /tmp/makemkv-msg.txt
git log -1 --format=%s            # MUST read "feat(makemkv): image v26.01.1 -> v26.09.2 ..." — amend before push if not
git show --stat HEAD              # exactly one file
git push
```

Wait for propagation (webhook → source → Kustomization `media/makemkv` → HR).
No manual `flux reconcile` unless nothing moves within 10 minutes:

```bash
for i in $(seq 1 40); do
  IMG=$(kubectl get deploy -n media makemkv -o jsonpath='{.spec.template.spec.containers[0].image}')
  case "$IMG" in *v26.09.2@sha256:bfdddd29*) echo "deployment spec updated"; break;; esac; sleep 15
done
kubectl rollout status deploy/makemkv -n media --timeout=10m
```

## 4. Verification

`rollout status` can report success for the OLD generation
(`feedback_rollout_status_old_generation`). Every gate below reads the NEW pod
directly. Set up:

```bash
P=$(kubectl get pod -n media -l app.kubernetes.io/instance=makemkv -o jsonpath='{.items[0].metadata.name}'); echo $P
```

**G1 — running digest is the target (not the old one).**
```bash
kubectl get pod -n media $P -o jsonpath='{.status.containerStatuses[0].imageID}{" "}{.status.containerStatuses[0].restartCount}{"\n"}'
```
PASS: imageID ends with `sha256:bfdddd29c5a9958da3003df1e673de7ad6915c846723449c76196d4ef6ca1ca2` and restartCount is `0`.
FAIL looks like: the imageID still ends `12ce7fc0…` (the old pod is still serving, or the spec never moved).

**G2 — HelmRelease reconciled.**
```bash
kubectl get helmrelease -n media makemkv -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.conditions[?(@.type=="Ready")].message}{"\n"}'
```
PASS: `True Helm upgrade succeeded…`.

**G3 — CONTENTS ASSERTION: the new MakeMKV binary is what runs, and it is not self-expired.**

> CONTENTS ASSERTION: the MakeMKV engine version is 2.0.0 and it reports no expiry. Measured by `makemkvcon` MSG:1005 plus the init banner in the container log. Compared to the baseline 1.18.2 from §2.6, where the same command must FAIL.

```bash
kubectl exec -n media $P -- sh -c 'T=$(mktemp -d); cp /config/settings.conf $T/; ln -s $T $T/.MakeMKV; echo "app_UpdateEnable = \"0\"" >> $T/settings.conf; env HOME=$T LD_PRELOAD=/opt/makemkv/lib/libwrapper.so /opt/makemkv/bin/makemkvcon -r --cache=1 --noscan info disc:9999 2>&1 | grep "^MSG"; rm -rf $T' > /tmp/mkv-msg.txt
grep -c 'MakeMKV v2\.0\.0' /tmp/mkv-msg.txt                        # PASS: >= 1
grep -ciE 'too old|expired|evaluation' /tmp/mkv-msg.txt            # PASS: 0
# PATTERN CONTROL for the line above (must be >= 1; measured 17 on 1.18.2, 2026-09-27;
# a nonsense pattern 'zzqq-never-present' measured 0 against the same binary):
kubectl exec -n media $P -- sh -c "strings /opt/makemkv/bin/makemkvcon | grep -ciE 'too old|expired|evaluation'"
kubectl logs -n media $P | grep -E 'Application Version:|Docker Image Version:'
#   PASS: "Application Version:   2.0.0" and "Docker Image Version:  26.09.2"
```

This command runs makemkvcon the same way the autodiscripper drive scan does:
against a throw-away HOME, with updates disabled. Without a disc it prints
`MSG:5010 Failed to open disc`, which is expected. The §2.6 negative control
proves the version grep can fail: it returns 0 against 1.18.2. The
`too old|expired|evaluation` grep is backed by the PATTERN CONTROL: the
binary's own message table contains strings the pattern matches (>= 1), so a
0 on the MSG output is a real "not emitted", not a pattern that can never
match. Scope of that control: it proves the PATTERN can match MakeMKV's
wording. It does NOT prove that `info disc:9999` would emit an expiry MSG
when the build is expired — no expired build is available to test that path.
If the pattern control returns 0 (e.g. `strings` missing from the image),
the expiry half of G3 is UNVERIFIED: report it, do not count it as PASS.

**G4 — registration and config preserved.**
```bash
kubectl logs -n media $P | grep -E '55-makemkv.sh: (registration key already up-to-date|updating registration key|ERROR)'
kubectl exec -n media $P -- sh -c 'sha256sum /config/machine-id | cut -c1-16; grep -E "^app_(DataDir|DestinationDir|DestinationType) " /config/settings.conf; echo keylen=$(sed -n "s/^app_Key = \"\(.*\)\"/\1/p" /config/settings.conf | wc -c | tr -d " "); head -3 /config/settings.conf | grep -o "MakeMKV v[0-9.]*"'
```
PASS:
- The machine-id hash and the three `app_*` lines are identical to the §2.5 baseline.
- keylen is 60 or more.
- The init line is `registration key already up-to-date.`, or `updating registration key...` if the window runs after a month rollover.
- The settings.conf header, once the GUI has written it, is allowed to read `MakeMKV v2.0.0`. It is informational only.

FAIL:
- `ERROR: failed to update beta key.` means the pod could not reach the forum.
  DVD ripping still works, but Blu-ray needs a key that is still valid. Before
  2026-10-01 this is a warning: the September key is still valid. From
  2026-10-01 on, tell the operator (unattended: report it as a G4 WARN in the
  window report; do not roll back). This is **not** a rollback trigger, because
  the old image has the same dependency.
- A different machine-id hash means `/config` did not remount. Roll back.

**G5 — the ripper can still see the drive (the whole point of the pod).**
```bash
kubectl get pod -n media $P -o jsonpath='{.spec.nodeName}{"\n"}'          # PASS: k8s-nuc14-03
kubectl exec -n media $P -- ls -l /dev/sr0                                 # PASS: exists
kubectl logs -n media $P | grep -E '^\[autodiscripper-0\] Ready\.|56-autodiscripper'
#   PASS: "[autodiscripper-0] Ready." present
```
The drive exists only on nuc14-03, and the Deployment has no nodeSelector.
- If the new pod landed on nuc14-01 or nuc14-02, `/dev/sr0` is missing and no
  `autodiscripper-0` service starts. That is a **FAIL**, but the image is not the
  cause. **STOP.** Attended: tell the operator. Unattended/AUTO-NIGHT: fail
  closed — do not roll back (the image is not at fault), do not delete the pod,
  leave the plan not-verified and report G5 FAIL. An attended `kubectl delete pod` to
  reschedule needs the operator's OK, and the durable fix is a nodeSelector
  commit (see §6).
- If the pod on nuc14-03 lacks `[autodiscripper-0] Ready.` while `/dev/sr0`
  exists, the image is the cause. Roll back.

**G6 — the GUI serves real content through the route, and the new web terminal is NOT exposed.**
```bash
H=$(kubectl get httproute -n media makemkv -o jsonpath='{.spec.hostnames[0]}')
curl -sk --resolve "$H:443:192.168.55.103" -o /tmp/mkv.html -w '%{http_code} %{size_download}\n' "https://$H/"
grep -c 'noVNC_app_name' /tmp/mkv.html                                 # PASS: >= 1
grep -ciE '404 Not Found|no healthy upstream|502 Bad Gateway' /tmp/mkv.html   # PASS: 0
kubectl exec -n media $P -- sh -c 'echo WEB_TERMINAL=${WEB_TERMINAL:-unset} WEB_FILE_MANAGER=${WEB_FILE_MANAGER:-unset}'
#   PASS: WEB_TERMINAL=unset (or 0) and WEB_FILE_MANAGER=unset (or 0)
```
PASS: status `200` and a size of more than 5000 bytes. Today's baseline is
`200 13851`, with 2 occurrences of `noVNC_app_name`.

FAIL looks like:
- Envoy's `no healthy upstream` (19 bytes).
- nginx's `404 Not Found` page (146 bytes, measured for `/nonexistent-xyz`).

Both fail the `noVNC_app_name` grep. `192.168.55.103` is the envoy-internal
Gateway named in the HTTPRoute's parentRef (status `Accepted=True
ResolvedRefs=True`, measured today).

**G7 — output mounts writable (round-trip, then clean up).**
```bash
kubectl exec -n media $P -- sh -c 'for d in /media /output; do f=$d/.mkv-plan-probe-$$; echo ok > $f && cat $f && rm -f $f && echo "$d RW-OK"; done'
```
PASS: `/media RW-OK` and `/output RW-OK`, each preceded by `ok`.
FAIL looks like: `Permission denied` or `Read-only file system` on either path.
The v26.02.2 release changed `take-ownership`, which is why this gate exists.

**G8 — steady state for 10 minutes (Prometheus).**
```bash
# EXPLICIT WAIT: G8 is read no earlier than 10 minutes after G1 passed.
# (Executor: note G1's pass time; if G3-G7 took less than 10 min, wait out the remainder,
#  e.g. `sleep 600` measured from G1. A crash-loop's first restart typically lands within
#  that window; reading at +1 min would see restarts=0 on a pod about to die.)
sleep 600
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for q in 'kube_deployment_status_replicas_available{namespace="media",deployment="makemkv"}' \
         'sum(kube_pod_container_status_restarts_total{namespace="media",pod=~"makemkv-.*"})'; do
  curl -s --data-urlencode "query=$q" http://localhost:19090/api/v1/query | \
    python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r), [x['value'][1] for x in r])"
done; kill $PF 2>/dev/null
```

CONTROL: metric kube_deployment_status_replicas_available — the makemkv series must exist (1 result) with the value `1`, measured 10 minutes after G1. An empty result counts as a FAIL, not a pass (baseline 2026-09-27: `1 ['1']`).
CONTROL: metric kube_pod_container_status_restarts_total — the sum over `makemkv-.*` pods must exist and equal `0` for the new pod (baseline `1 ['0']`). A value of 1 or more means a crash-loop, so roll back.

## 5. Rollback

Trigger any rollback on:
- G1, G2 or G3 failing;
- G4 with a changed machine-id;
- G5 failing on nuc14-03 (pod on the drive node, but no autodiscripper);
- G6 still failing after 5 minutes;
- G7 or G8 failing.

Nothing forward-only happens in this plan. MakeMKV 2.0.0 rewrites the header of
`settings.conf`, a flat key=value file that 1.18.2 reads the same way. A
`git revert` is therefore the whole procedure:

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha of the §3 commit>      # restores both pins to v26.01.1@sha256:12ce7fc0...
git log -1 --format=%s                            # confirm it is YOUR revert subject
git push
# wait as in §3, then confirm the cluster is back:
kubectl get deploy -n media makemkv -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
#   expect jlesage/makemkv:v26.01.1@sha256:12ce7fc0e398c240bc06b27459241ddae524e066c476525b9b36a16c3e478518
P=$(kubectl get pod -n media -l app.kubernetes.io/instance=makemkv -o jsonpath='{.items[0].metadata.name}')
kubectl get pod -n media $P -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'   # ...@sha256:12ce7fc0...
kubectl logs -n media $P | grep -E 'Application Version:'                               # 1.18.2
```
Then re-run G4 to G7 against the rolled-back pod.

- **If Helm is wedged** (`pending-upgrade`), follow
  `docs/sops/application-update.md` §11: `helm rollback makemkv <last-deployed-rev> -n media --wait=false`,
  then `flux reconcile helmrelease -n media makemkv --force`.
- **If `/config` contents are damaged**, which nothing in the upstream notes
  predicts, restore volume `makemkv-config` from the newest Completed Longhorn
  backup recorded in §2.4. Follow `docs/sops/backup.md`: scale the Deployment
  down via git, then restore through Longhorn. **Never delete PVC
  `makemkv-media`.** It is on `cifs-makemkv-media` (Severe tier), and nothing in
  this rollback needs it.

## 6. Interference notes

- **The shared iGPU (`igpu-i915`).** Our Recreate releases one
  `gpu.intel.com/i915` slot on nuc14-03 and re-claims one. Four of the five slots
  are in use today, so capacity is fine unless another nuc14-03 GPU pod
  (jellyfin, scrypted, immich-ml) recreates at the same moment. Hence
  `conflicts_with: jellyfin-12.1`. `helm-drift-detection` P2 rolls the
  intel-gpu-plugin DaemonSet, which blocks new GPU pods for about a minute per
  node, hence that conflict too.
- **The CIFS share.** We only remount `//NAS/media/Transcode`. No PV/PVC is
  created, deleted or patched.
- **`media-naming-p3` shares the `media` token but is NOT in `conflicts_with` —
  deliberately.** It renames TV-library files on `cifs-plex-media` /
  `cifs-jellyfin-media` (`subdir: /`, the whole //NAS/media export) and re-identifies
  them in Plex/Jellyfin. We touch only the `/Transcode` subdir, by remount, with
  no file writes except G7's probe file (created and deleted in-place under
  `/Transcode`, never in a library folder). No file or library is shared between
  the two; the `shared: [media]` intersection is a scheduler WARNING, which is the
  right strength. (It is also unwindowed at 240 min.) If a future revision of
  that plan touches `/Transcode`, add the conflict on both sides.
- **The GUI (`makemkv.<domain>` via envoy-internal)** is down for about 2 minutes
  during Recreate. No other app depends on it.
- **Reciprocity.** `jellyfin-12.1`, `helm-drift-detection`,
  `flux-reconciler-impersonation`, `float-tag-pinning` and `app-template-5.2.1` do not list this plan
  in their `conflicts_with`. `--validate` checks only that refs resolve, not
  reciprocity. Adding the reverse refs is a repo correction, not done here.
- **No Prometheus-bumping plan is open.** `kube-prometheus-stack-91.4.1` was
  executed on 2026-09-26. G8 reads Prometheus, so any future kps bump must not
  share this window.
- **>>> CONFIRMED SIDE FINDING — needs its OWN follow-up change; this plan does
  NOT fix it and must not be widened to. <<<** Measured live 2026-09-27
  (`/proc/mounts`, `talosctl ls /dev` on all 3 nodes). Items 1 and 2 below are
  the substance: **rips land on node-local `/output` and are lost on every pod
  restart**, and **`/dev/sr0` exists only on k8s-nuc14-03 while nothing pins the
  pod there.** The follow-up (mount `makemkv-media` at `/output` via
  `persistence.*.globalMounts`/`advancedMounts`, add a nodeSelector for
  k8s-nuc14-03, drop the dead legacy keys) changes where data is written and
  must carry its own plan, review and storage-safety pre-flight.
- **Out of scope, found while planning. These are for the operator; this plan
  deliberately does not fix them.**
  1. **Auto-ripped discs land on ephemeral storage.** `app_DestinationDir =
     "/output"`, but `/output` is the image's anonymous VOLUME on the node's nvme
     (`/proc/mounts`: `/dev/nvme0n1p6 /output xfs`). The CIFS PVC is mounted at
     `/media`, not `/output`. The `extraVolumeMounts` entry that would mount
     `makemkv-media` at `/output` is a legacy key that app-template 5.x ignores.
     Any rip is lost on the next pod restart, and that includes this bump's
     Recreate, which is why §2.2 stops on `recent>0`. `/output` is empty today.
  2. **The drive is not pinned.** `/dev/sr0` exists only on nuc14-03, and the
     Deployment has no nodeSelector or affinity. A Recreate can silently move
     the ripper off the drive (G5 catches that here, and nothing else does).
  3. **Dead values.** The legacy top-level `image`, `env`, `securityContext`,
     `resources`, `extraVolumes` and `extraVolumeMounts`, and the disabled
     `ingress` block, do not render. Removing them (and moving any intent, such
     as the `/output` mount, into `persistence.*.advancedMounts` and
     `defaultPodOptions.nodeSelector`) is its own reviewed change.
