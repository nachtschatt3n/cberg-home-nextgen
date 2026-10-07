---
plan_id: jellyfin-12.2.20261005
component: jellyfin
pr: null                              # No Renovate PR for the 12.x line (same as jellyfin-12.1:
                                      # the held update is surfaced by coverage.py / F-fc5e2913).
kind: image
current: "10.11.11.20260606-153911"   # live 2026-10-07: deployment image, pod digest
                                      # sha256:aefb67e6..., k8s-nuc14-01, 0 restarts, 8d.
target: "12.2.20261005-225228"        # Docker Hub: this tag, `12.2` and `latest` all resolve to
                                      # index digest sha256:357724bf0ae27a672c7cbaa899db2d9abeb13dbd8657ccce750258a4c059d037
                                      # (measured 2026-10-07). GitHub release v12.2:
                                      # prerelease=false, draft=false, 2026-10-05T23:07:59Z.
update_type: major
risk: high                            # Forward-only DB migration (10.11 -> 12.x schema, plus three
                                      # NEW 12.2 migrations) on the household's actively used,
                                      # internet-facing media server; one repository plugin must be
                                      # removed first; legacy-auth switch-off and legacy-route
                                      # removal change client behaviour. Same basis as jellyfin-12.1.
est_duration_min: 70                  # pre-checks+baselines 10 · backup_gate ~12 (the CronJob
                                      # trigger backs up EVERY volume) · plugin uninstall 3 ·
                                      # commit+reconcile+first-boot migration 15 · mandatory full
                                      # scan ~5-15 (normal scan measured 2026-10-06: 1m45s; first
                                      # 12.x scan is "significantly longer") · plugin 1.5.0 install
                                      # + restart 5 · verification 15. Fits sat-attended (90).
needs_reboot: false
touches:
  namespaces: [media, storage]        # storage: the backup_gate creates a Job from
                                      # cronjob/storage/daily-backup-all-volumes
  resources:
    - helmrelease/jellyfin
    - deployment/jellyfin
    - pvc/jellyfin-config               # longhorn-static RWX 25Gi, 5.8G used — jellyfin.db (62M),
                                        # plugins/, users: everything that matters
    - pv/jellyfin-config                # only on ROLLBACK (§5 restore re-points the PV)
    - volume.longhorn.io/jellyfin-config
    - pvc/jellyfin-media                # cifs-jellyfin-media, Tier-1 catastrophic — NOT touched;
                                        # named so nobody touches it
    - plugin/TubeArchivistMetadata      # 1.4.4.0 (targetAbi 10.11) uninstalled before the bump,
                                        # 1.5.0.0 (targetAbi 12.0, released 2026-10-05) installed after
    - configmap/library-tools-scripts   # READ ONLY — gate G3 asserts 0 legacy-header call sites
    - cronjob/media-metadata-coverage   # consumer of the Jellyfin API (verification §4.6)
    - cronjob/media-per-item-refresh    # consumer of the Jellyfin API
    - cronjob/media-intake-watcher      # consumer (folder-scoped /Library/Media/Updated rescans)
    - deployment/media-dashboard        # renders coverage output
    - cronjob/daily-backup-all-volumes  # ns storage — triggered once for the backup_gate
  shared: [igpu-i915, gateway/envoy-external, storage/longhorn]
                                        # igpu-i915: pod requests+limits gpu.intel.com/i915: 1, now
                                        # on k8s-nuc14-01 (3/5 slots with immich-server, makemkv —
                                        # live 2026-10-07). envoy-external: public HTTPRoute, client
                                        # behaviour changes. storage/longhorn: all-volume backup
                                        # trigger + (rollback) a restore.
depends_on: []
conflicts_with:
  - jellyfin-12.1                     # SUPERSEDED BY THIS PLAN (see §0). Must never share a window
                                      # or both run: two forward migrations on the same DB.
  - jellyfin-config-rwo-migration     # same helmrelease + pvc/jellyfin-config. This plan's
                                      # backup_gate, premises and §5 name the OLD RWX volume
                                      # `jellyfin-config`: run THIS plan FIRST (before 10-25).
  - media-naming-p3                   # backup-restore stacking (inherited from jellyfin-12.1)
  - n8n-2.39.8                        # backup-restore stacking (inherited)
  - paperless-db-13.0.2               # backup-restore stacking (inherited; that plan names jellyfin-12.1)
  - nextcloud-fleet-35.0.1            # names jellyfin-12.1 — carried over so the pair stays enforced
  - nocodb-2026.09.1                  # names jellyfin-12.1 — carried over
  - helm-drift-detection              # touches helmrelease/media/jellyfin + rolls intel-gpu-plugin
  - flux-oci-chart-sources            # mirrors the jellyfin chart source
  - flux-distribution-2.9.6           # names jellyfin-12.1 — carried over
  - immich-machine-learning-3.2.4     # names jellyfin-12.1; igpu-i915 + media ns — carried over
  - talos-power-tuning-ab             # names jellyfin-12.1; igpu-i915 — carried over
  - talos-linux-1.14.2                # cluster-wide node roll incl. igpu-i915 + longhorn
  - longhorn-1.13.0                   # backup_gate + restore path run on the engine it replaces
  - kube-prometheus-stack-91.9.0      # §4.7 reads Prometheus (window instrument = shared infra)
exclusive: false
security_ref: F-3a72570a              # security finding on the CURRENT image — detail on the record
                                      # only. We bump, we never rebuild.
capability_change: true               # Upstream-documented behaviour changes in 10.11 -> 12.x:
                                      # legacy /emby and /mediabrowser routes REMOVED, legacy
                                      # authorization switched OFF by migration (HA media-browser
                                      # playback 401s until HA ships apiclient >= 1.17), subtitle
                                      # config moves global -> per-library.
rollback_class: backup-restore        # 12.0 notes: "database changes that prevent rolling back
                                      # without a full restore"; 12.2 adds three more forward
                                      # migrations (§1.3). A bare tag revert is NOT a rollback.
backup_gate: "on-demand Longhorn backup of volume jellyfin-config, triggered IN-WINDOW as the
  FIRST mutating step (§3 step 1), before the plugin uninstall and the tag bump, while the
  10.11.11 pod is running (volume attached; allow-recurring-job-while-volume-detached=false).
  PASS = a NEW Completed Backup CR labelled backup-volume=jellyfin-config whose
  creationTimestamp > GATE_START, AND `runbooks/longhorn-backup-age.py jellyfin-config
  --max-hours 1` prints FRESH. Triggered via cronjob/daily-backup-all-volumes (ns storage) —
  NOT `backup-of-all-volumes`, which does not exist. Newest Completed at planning time:
  backup-db17f322e23e40e2 2026-10-06T03:01:59Z (does not satisfy the gate)."
finding_refs: [F-fc5e2913, F-3a72570a]
review: null
status: draft
window: null                          # Recommendation (§6): take over jellyfin-12.1's slot
                                      # sat-attended:2026-10-10 once 12.1 is marked superseded and
                                      # this plan is reviewed + GO'd; otherwise the next attended
                                      # slot with capacity BEFORE sun-attended:2026-10-25.
premises:
  - id: image-is-still-10.11.11
    why: >-
      Every baseline (counts, digest for rollback, plugin inventory) is captured against
      10.11.11. If jellyfin-12.1 (or anything else) already moved the image, this plan is
      stale — a 12.1 -> 12.2 hop is a different (smaller) job and must be re-derived.
    run: kubectl get deploy -n media jellyfin -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: docker.io/jellyfin/jellyfin:10.11.11.20260606-153911
  - id: config-pvc-still-rwx-longhorn-static
    why: >-
      The backup_gate and §5 restore are written for the RWX longhorn-static PVC bound to PV
      jellyfin-config. If jellyfin-config-rwo-migration ran first, they name the wrong volume.
    run: kubectl get pvc -n media jellyfin-config -o jsonpath='{.spec.storageClassName} {.spec.accessModes[0]} {.spec.volumeName}'
    expect_exact: longhorn-static ReadWriteMany jellyfin-config
  - id: helmrelease-mounts-jellyfin-config
    why: >-
      Guards the ordering against jellyfin-config-rwo-migration, which repoints existingClaim.
    run: kubectl get helmrelease -n media jellyfin -o jsonpath='{.spec.values.persistence.config.existingClaim}'
    expect_exact: jellyfin-config
  - id: jellyfin-config-volume-attached
    why: >-
      The on-demand backup only runs on an attached volume.
    run: kubectl get volumes.longhorn.io -n storage jellyfin-config -o jsonpath='{.status.state}'
    expect_exact: attached
  - id: media-storageclass-reclaim-retain
    why: >-
      cifs-jellyfin-media is subdir / on the whole NAS media export (Tier-1). This plan
      performs NO action on it; if it ever reads Delete, STOP and surface it.
    run: kubectl get sc cifs-jellyfin-media -o jsonpath='{.reclaimPolicy}'
    expect_exact: Retain
  - id: hr-remediation-at-default
    why: >-
      §3 step 4 sets retries 0 for the migration and §3 step 9 restores 1. A 0 at window
      start means an earlier attempt was left half-done.
    run: kubectl get helmrelease -n media jellyfin -o jsonpath='{.spec.upgrade.remediation.retries}'
    expect_exact: "1"
  - id: deployment-strategy-recreate
    why: >-
      The old pod must fully release the RWX volume and its i915 slot before the 12.2 pod
      starts its migration; a surge pod would run two Jellyfin processes on one SQLite DB.
    run: kubectl get deploy -n media jellyfin -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/storage-safety.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-07"
---

# jellyfin: image 10.11.11.20260606-153911 -> 12.2.20261005-225228 (major)

## 0. Relationship to `jellyfin-12.1` and `jellyfin-config-rwo-migration` — read first

**This plan SUPERSEDES `jellyfin-12.1`** (status awaiting-go, `sat-attended:2026-10-10`,
review ready-for-go@2026-09-28). Reasons:

- Executing 12.1 on 10-10 while 12.2 is GA would run the 10.11 -> 12.x forward migration,
  and then a second forward migration (12.2's three new routines, §1.3) a few days later —
  two backup-restore events on the same DB, for no benefit. Upstream supports 10.11.x -> 12.x
  direct ("intermediate upgrades are not required").
- The one thing that made 12.1 a standing capability loss is GONE: TubeArchivistMetadata
  **v1.5.0.0 (targetAbi 12.0.0.0) shipped 2026-10-05** and upstream issue #96 is closed. The
  plugin is now uninstall-before / reinstall-after, not a judgement call.

**Required follow-up the planner did NOT do (it writes one file only):** set `jellyfin-12.1`
to `status: superseded` (note: "superseded by jellyfin-12.2.20261005") and clear its
`window:`. Every plan that named `jellyfin-12.1` in `conflicts_with` is carried into THIS
plan's `conflicts_with` (the scheduler reads the field in either direction), so no
counterpart file needs editing for enforcement. Its GO does not transfer — the target,
the plugin step and the migration set all changed, so this plan needs its own review + GO.

> Repo note: `runbooks/maintenance/plans/README.md` §"When the held target MOVES" says to
> REFRESH a drifted plan in place (keep the plan_id) unless the job changed. 12.1 -> 12.2 is
> the same release line (`_release_line` = (12,)), so by that rule `jellyfin-12.1` should
> have been refreshed, not replaced. The sweep dispatched a new group slug instead; the
> dispatch and the README disagree. Either path is safe so long as exactly ONE of the two
> files is live.

**Ordering vs `jellyfin-config-rwo-migration` (sun-attended:2026-10-25): THIS plan first.**
Its backup_gate, premises and §5 name the RWX volume `jellyfin-config`, and the rwo plan's
reviewed copy-then-switch is image-agnostic. Checked for the rwo plan's §3.4 restore-proof:
the main item table is still `BaseItems` in 12.2 (`JellyfinDbModelSnapshot.cs` l.422,
`ToTable("BaseItems")`), so its `baseitems > 0` gate stays valid after this upgrade. If this
plan ROLLS BACK via §5, the Longhorn volume behind `pvc/jellyfin-config` becomes
`jellyfin-config-r<date>` and the rwo plan's `old-volume-healthy` / `old-volume-backups-exist`
premises will (correctly) fail — re-derive the rwo plan for the new volume name before 10-25.

## 1. Summary & why held

Move `deployment/jellyfin` (ns `media`) from `docker.io/jellyfin/jellyfin:10.11.11.20260606-153911`
to `:12.2.20261005-225228`. Only the image tag (and, temporarily, Helm remediation) changes in
`kubernetes/apps/media/jellyfin/app/helmrelease.yaml`; chart `jellyfin` 3.2.0 is untouched.
Security driver: `F-3a72570a` (detail on the record only).

### 1.1 Held because

`update_type: major` routes to the plan lane in `coverage.py` regardless of any deny rule.
Not a false positive.

### 1.2 Breaking changes 10.11 -> 12.x (12.0 release notes; still apply to 12.2)

1. **Forward-only DB migration** — *"this release includes database changes that prevent
   rolling back without a full restore."* -> `backup-restore`, mandatory `backup_gate`.
2. **Remove repository plugins first** — *"Installed repository plugins (anything not
   built-in) should also be removed before migrating ... re-adding them afterward is the
   safest approach."* Live: `TubeArchivist Metadata 1.4.4.0 Active` (+ 5 built-ins at
   10.11.11.0 that migrate with the server). Its repository
   (`TubeArchivistMetadata`, `.../tubearchivist-jf-plugin/raw/master/manifest.json`) is
   already configured and now lists `1.5.0.0 targetAbi 12.0.0.0`.
3. **Legacy route prefixes removed** (`/emby/*`, `/mediabrowser/*`). No in-repo consumer
   uses them (grepped 2026-10-07).
4. **Legacy authorization disabled by migration** — `20260531160000_DisableLegacyAuthorization`
   is still present in v12.2 and `AuthorizationContext.cs` is unchanged v12.1 -> v12.2, so the
   jellyfin-12.1 §1.4 analysis holds: `X-Emby-Token`, `X-MediaBrowser-Token`, `api_key=`,
   `X-Emby-Authorization` stop working; `Authorization: MediaBrowser Token="..."` and
   `ApiKey=` keep working. Live `system.xml` has `<EnableLegacyAuthorization>true` -> the
   migration WILL fire.
5. Subtitle config moves global -> per-library; `.ogg`/`.aifc`/`.aiff` reclassified.
6. **Mandatory full library scan after upgrade** — auto-resolved alternate versions are
   dropped and restored only by the scan.

### 1.3 What 12.2 adds (v12.2 notes, 51 changes, "minor release brings several bugfixes";
"please ensure you take a full backup before upgrading!")

Read from `compare/v12.1...v12.2`, not only the prose. **12.2 adds migrations**, so the
forward-only surface grows:

- `Routines/20260912120000_HarmonizeConflictingUserData.cs` (`[JellyfinMigrationBackup(JellyfinDb = true)]`)
  — collapses conflicting per-user watch-state rows (position/playcount/played/favorite).
  Touches user watch history: §4.2b checks it.
- `Routines/20260915104305_FixNullEncoderPreset.cs` — *"Fix transcoding settings migration
  failure caused by null EncoderPreset"* (#18059). Directly relevant: we set VAAPI options
  via env; §4.4 proves hardware encode afterwards.
- EF migration `20261002210711_MakeOwnerIdIndexesPartial` and a perf fix to
  `ChangeOwnerIdToGuid` (#18073).
- `JellyfinMigrationService.EnsureExistingDatabaseAsync` (#18264): a server whose
  `IsStartupWizardCompleted` is true but whose DB is missing/empty now **refuses to start**
  (LogCritical, throws) instead of seeding an empty DB. Safety improvement: a botched restore
  or wrong mount crash-loops loudly rather than coming up as a blank server.
- #18102 *"Never treat unresolvable libraries as grounds for deletion"* — relevant to a
  CIFS-backed library during the long first scan.

### 1.4 Clients on the other side of the auth change (re-measured 2026-10-07)

`/Devices` app families: Jellyfin Web (10.10.6..10.11.11), Jellyfin iOS/iPadOS 1.7.0,
Jellyfin tvOS 1.0.1, Infuse-Direct 8.1.5, Home Assistant (3), Music Assistant (2.10.5, 2.5.8).

- **In-repo**: `configmap/library-tools-scripts` now has **0** `X-Emby-Token` call sites
  (commit 5b8193c9); `rescan.py` and `metadata_coverage.py` use `Authorization: MediaBrowser`.
  Last coverage run on 10.11.11: `coverage-jellyfin total 548, http errors []`.
- **Home Assistant 2026.9.4** (live) still pins `jellyfin-apiclient-python==1.16.0`
  (HA `dev` is at 1.19.0). Expected casualty, unchanged from jellyfin-12.1: HA entities and
  media_player keep working; **playing/browsing Jellyfin items from HA's media browser 401s**
  (legacy `api_key=` on stream URLs) until HA ships the newer client. Remedy is an HA update,
  NOT re-enabling legacy auth.
- **Music Assistant 2.10.5**: expected green (provider rewrites `api_key` -> `apiKey`,
  verified from source at 2.10.3 by the 12.1 review; re-checked live in §4.6, not assumed).

## 2. Pre-checks

### 2.1 State (measured 2026-10-07)

- `pvc/jellyfin-config` -> PV `jellyfin-config` (driver.longhorn.io, Retain, volumeHandle
  `jellyfin-config`), longhorn-static RWX 25Gi, 5.8G used, Longhorn volume attached/healthy,
  2 replicas, served over NFS by the share-manager. `jellyfin.db` 64,749,568 bytes.
  `SQLiteBackups/` empty (4K).
- `pvc/jellyfin-media` -> `cifs-jellyfin-media`, `subdir: /`, Retain — Tier-1 catastrophic.
  **No PVC action of any kind on this claim, happy path or rollback.**
- Pod `k8s-nuc14-01`, i915 3/5 (immich-server, jellyfin, makemkv), privileged (AR-009),
  strategy Recreate.
- Plugins dir: `configurations/`, `TubeArchivistMetadata_1.4.4.0/` (contains a `.nfs*`
  silly-rename file — an in-pod `rm -rf` of that dir FAILS while the process holds the DLL;
  hence the API uninstall in §3 step 2, not `rm`).
- Plugin settings live in `plugins/configurations/Jellyfin.Plugin.TubeArchivistMetadata.xml`
  (1022 bytes) — outside the plugin dir; preserved by uninstall, copied aside anyway.
- Alerts (excluding Watchdog/InfoInhibitor): `AuthentikOutpostDisconnected` (kube-system,
  pending), `ICloudDrivePersistentDownloadFailures`, `AragScrapeDown`,
  `AragPushMetricMissing`, `TargetDown` firing — all pre-existing and unrelated to `media`.
  Re-record at window time; attribute only NEW alerts to this change.
- Library baseline (`/Items/Counts`, 2026-10-07): Movie 501, Series 47, Episode 2481,
  Song 631, Album 40, BoxSet 78. Last "Scan Media Library" Completed 2026-10-06T19:59:20Z
  (1m45s). Re-record at window time.

### 2.2 Commands — G1..G3 are ABORT gates

```bash
cd /Users/mu/code/cberg-home-nextgen

# --- G1 (ABORT): target still GA and resolvable. Use `gh api` — UNAUTHENTICATED
#     curl to api.github.com is rate-limited from this IP (403 "API rate limit exceeded"
#     observed 2026-10-07), which would read as a failed gate.
gh api repos/jellyfin/jellyfin/releases/tags/v12.2 --jq '[.tag_name,.prerelease,.draft]|@tsv'
#   MUST print: v12.2  false  false
gh api repos/jellyfin/jellyfin/releases --jq '.[0].tag_name'
#   If this prints anything newer than v12.2 (v12.3, v13...), STOP: refresh the plan.
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:jellyfin/jellyfin:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -D - -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  "https://registry-1.docker.io/v2/jellyfin/jellyfin/manifests/12.2.20261005-225228" | grep -iE '^HTTP|docker-content-digest'
#   MUST be HTTP/2 200 and digest sha256:357724bf0ae27a672c7cbaa899db2d9abeb13dbd8657ccce750258a4c059d037.
#   A different digest = upstream re-pushed the tag: STOP and re-derive.

# --- G2 (ABORT): plugin inventory unchanged; the 12.x build is still published.
POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n media "$POD" -- sh -c 'ls /config/plugins'
#   Expected: configurations  TubeArchivistMetadata_1.4.4.0 . Any OTHER repository plugin
#   => STOP; check its 12.x build before proceeding (§3 handles only this one).
curl -sL https://github.com/tubearchivist/tubearchivist-jf-plugin/raw/master/manifest.json \
  | python3 -c "import sys,json;v=json.load(sys.stdin)[0]['versions'][0];print(v['version'],v['targetAbi'])"
#   MUST print 1.5.0.0 12.0.0.0 (or a newer version with targetAbi 12.x).

# --- G3 (ABORT): no in-repo legacy-auth caller.
kubectl get configmap -n media library-tools-scripts -o json | python3 -c \
 "import sys,json;print('legacy X-Emby-Token call sites:', sum(v.count('X-Emby-Token') for v in json.load(sys.stdin)['data'].values()))"
#   MUST print 0 (measured 0 on 2026-10-07). Non-zero => STOP.

# --- Baselines (record every number) ---
kubectl get pod -n media "$POD" -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
#   expect ...@sha256:aefb67e6a7ff1debdd154a78a7bbb780fd0c873d8639210a7f6a2016ad2b35db (rollback digest)
kubectl exec -n media "$POD" -- sh -c 'ls -la /config/data/jellyfin.db; grep -o "<EnableLegacyAuthorization>[^<]*" /config/config/system.xml'
#   expect <EnableLegacyAuthorization>true
kubectl exec -n media "$POD" -- sh -c '/usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -encoders 2>/dev/null | grep -c vaapi'
#   expect 7 (measured 2026-10-07). FULL PATH — bare `ffmpeg` is not on PATH and returns 0.
kubectl exec -n media "$POD" -- sh -c \
  '/usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -f lavfi -i testsrc=size=320x240:rate=5:duration=1 -vf format=nv12,hwupload \
     -c:v h264_vaapi -f null - && echo VAAPI_ENCODE_OK'
kubectl exec -n media "$POD" -- sh -c 'grep -io "<HardwareAccelerationType>[^<]*\|<EncoderPreset>[^<]*" /config/config/encoding.xml'
#   expect <HardwareAccelerationType>qsv and <EncoderPreset>medium (measured 2026-10-07)
RESTART_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "RESTART_TS=$RESTART_TS"

JF_KEY=$(sops -d kubernetes/apps/media/library-tools/app/secret.sops.yaml \
  | python3 -c "import sys,yaml;print(yaml.safe_load(sys.stdin)['stringData']['JELLYFIN_API_KEY'])")
kubectl port-forward -n media svc/jellyfin 8097:8096 >/dev/null 2>&1 & PF=$!; sleep 3
AUTH="Authorization: MediaBrowser Token=\"$JF_KEY\""
curl -s -H "$AUTH" http://localhost:8097/Items/Counts | python3 -m json.tool | tee /tmp/jf-counts-pre.json
# Watch-state baseline for the HarmonizeConflictingUserData migration (§4.2b) — per user,
# played + favorite counts:
curl -s -H "$AUTH" http://localhost:8097/Users | python3 -c "
import sys,json;[print(u['Id'],u['Name']) for u in json.load(sys.stdin)]" | tee /tmp/jf-users.txt
# NB: never name the loop variable UID — it is a read-only special in zsh AND bash.
while read -r U_ID UNAME; do
  P=$(curl -s -H "$AUTH" "http://localhost:8097/Items?userId=$U_ID&Recursive=true&IsPlayed=true&Limit=0" | python3 -c "import sys,json;print(json.load(sys.stdin)['TotalRecordCount'])")
  F=$(curl -s -H "$AUTH" "http://localhost:8097/Items?userId=$U_ID&Recursive=true&IsFavorite=true&Limit=0" | python3 -c "import sys,json;print(json.load(sys.stdin)['TotalRecordCount'])")
  echo "$UNAME played=$P favorite=$F"
done < /tmp/jf-users.txt | tee /tmp/jf-userdata-pre.txt
curl -s -H "$AUTH" http://localhost:8097/Plugins | python3 -c \
 "import sys,json;[print(p['Name'],p['Id'],p['Version'],p['Status']) for p in json.load(sys.stdin)]"
#   expect TubeArchivist Metadata dc97d0c628b04242afb45833ae1b3715 1.4.4.0 Active

# --- Alert silence + update marker (docs/sops/application-update.md) ---
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & AMPF=$!; sleep 2
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"media","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"Kube(Pod|Deployment).*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window",
  "comment":"jellyfin 10.11.11 -> 12.2 major upgrade; auto-expires 4h"}'
#   record the returned silenceID
runbooks/update-marker.sh add jellyfin media 4 "jellyfin 10.11.11->12.2"
```

## 3. Steps

1. **backup_gate — FIRST mutating action, on the untouched 10.11.11 state.**
   ```bash
   GATE_START=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "GATE_START=$GATE_START"
   kubectl create job --from=cronjob/daily-backup-all-volumes "pre-jellyfin-12-2-$(date +%Y%m%d-%H%M)" -n storage
   # wait (~12 min — it backs up every volume), then:
   kubectl get backups.longhorn.io -n storage -l backup-volume=jellyfin-config \
     --sort-by=.metadata.creationTimestamp \
     -o custom-columns=NAME:.metadata.name,STATE:.status.state,CREATED:.metadata.creationTimestamp | tail -2
   .venv/bin/python3 runbooks/longhorn-backup-age.py jellyfin-config --max-hours 1
   ```
   PASS = newest row is `Completed` with CREATED > GATE_START (newer than
   `backup-db17f322e23e40e2`) AND the helper prints `FRESH`. Record the Backup NAME —
   §5 restores from it. FAIL (no new Completed CR, or helper prints STALE) => STOP, nothing
   has changed yet, abort the plan. Because the backup is taken BEFORE the plugin removal,
   a restore brings back a fully working 10.11.11 including TubeArchivistMetadata 1.4.4.

2. **Uninstall TubeArchivistMetadata 1.4.4.0** (upstream §1.2 item 2). App state on the
   PVC; no GitOps path exists. Copy its settings aside (same `.bak` convention already in
   that directory), then uninstall via the API:
   ```bash
   kubectl exec -n media "$POD" -- sh -c 'cp -p /config/plugins/configurations/Jellyfin.Plugin.TubeArchivistMetadata.xml /config/plugins/configurations/Jellyfin.Plugin.TubeArchivistMetadata.xml.pre12.bak'
   curl -s -o /dev/null -w 'uninstall http=%{http_code}\n' -X DELETE -H "$AUTH" \
     "http://localhost:8097/Plugins/dc97d0c628b04242afb45833ae1b3715/1.4.4.0"
   #   expect 204
   curl -s -H "$AUTH" http://localhost:8097/Plugins | python3 -c \
    "import sys,json;[print(p['Name'],p['Version'],p['Status']) for p in json.load(sys.stdin) if 'Tube' in p['Name']]"
   kubectl exec -n media "$POD" -- sh -c 'ls /config/plugins; cat /config/plugins/TubeArchivistMetadata_1.4.4.0/meta.json 2>/dev/null | grep -io "\"status\":\"[a-z]*\""'
   ```
   PASS = either the plugin is absent from `/Plugins` and the directory is gone, OR the
   plugin shows `Deleted` (status in `/Plugins` / `meta.json`, matched case-insensitively) —
   Jellyfin marks it Deleted when the DLL is held open (the `.nfs*` file) and purges it at
   next startup, before it would be loaded. Still `Active` => STOP (do not bump with the
   10.11-ABI plugin live). Do NOT `rm -rf` the directory in-pod: it fails on the open
   `.nfs*` handle and leaves a half-deleted plugin.

3. **Edit `kubernetes/apps/media/jellyfin/app/helmrelease.yaml`** — tag bump + disable
   remediation for the attempt (a slow first-boot migration must not be "remediated"
   mid-migration). Dry-tested with BSD sed on a scratch copy 2026-10-07:
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' \
     -e 's/^\([[:space:]]*tag:[[:space:]]*\)10\.11\.11\.20260606-153911$/\112.2.20261005-225228/' \
     -e '/^  upgrade:/,/^  uninstall:/{s/^\([[:space:]]*retries:[[:space:]]*\)1$/\10/;s/^\([[:space:]]*remediateLastFailure:[[:space:]]*\)true$/\1false/;}' \
     kubernetes/apps/media/jellyfin/app/helmrelease.yaml
   git diff kubernetes/apps/media/jellyfin/app/helmrelease.yaml
   ```
   The diff MUST be exactly (scratch-copy result):
   ```
   <       retries: 1
   <       remediateLastFailure: true
   >       retries: 0
   >       remediateLastFailure: false
   <       tag: 10.11.11.20260606-153911
   >       tag: 12.2.20261005-225228
   ```
   (`install.remediation.retries: 1` sits above the `upgrade:` block and is untouched.)
   Nothing else in this diff.

4. **Commit + push** (shared worktree):
   ```bash
   printf '%s\n' "feat(jellyfin): 10.11.11.20260606-153911 -> 12.2.20261005-225228 (upstream GA major)" "" \
     "Plan jellyfin-12.2.20261005. Remediation disabled for the forward-only first-boot migration;" \
     "restored after verification. Supersedes jellyfin-12.1." > /tmp/jf122-msg.txt
   git commit --only kubernetes/apps/media/jellyfin/app/helmrelease.yaml -F /tmp/jf122-msg.txt
   git log -1 --format=%s     # MUST be the subject above (message-swap race)
   git show --stat HEAD       # exactly one file
   git push
   ```

5. **Watch the rollout and the migration** — no manual `flux reconcile` (webhook).
   ```bash
   flux get helmrelease -n media jellyfin
   kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -w
   kubectl logs -n media -l app.kubernetes.io/name=jellyfin -f | grep -iE 'migrat|Harmoniz|EncoderPreset|LegacyAuthorization|Startup complete|critical|error|fail'
   ```
   As established from source for 12.1 (Program.cs/SetupServer, unchanged in substance in
   12.2): migrations run before the main host starts while a SetupServer answers `/health`
   (200) and `/System/Info/Public` (503). **Pod Ready / HR Ready arrive while the migration
   is still running** — they prove nothing. End this step only on `Startup complete` in the
   log AND `/System/Info/Public` -> 200 with `Version` 12.2.x. Do NOT edit probes or
   kill the pod mid-migration (under Recreate a pod-template change kills the migration).
   A `LogCritical` "will not start an existing server with an empty database" (§1.3) means
   the mount/DB is wrong — go to §5, do not "start over".
   ```bash
   kill $PF 2>/dev/null; kubectl port-forward -n media svc/jellyfin 8097:8096 >/dev/null 2>&1 & PF=$!; sleep 3
   curl -s -o /dev/null -w 'public-info http=%{http_code}\n' http://localhost:8097/System/Info/Public   # 503 = migrating
   ```

6. **Mandatory full library scan** (upstream requirement):
   ```bash
   curl -s -o /dev/null -w 'refresh http=%{http_code}\n' -X POST -H "$AUTH" http://localhost:8097/Library/Refresh
   ```
   Wait for §4.5 Completed before evaluating §4.2.

7. **Install TubeArchivistMetadata 1.5.0.0** from the already-configured repository, then
   restart Jellyfin in-process to load it:
   ```bash
   curl -s -o /dev/null -w 'install http=%{http_code}\n' -X POST -H "$AUTH" \
     "http://localhost:8097/Packages/Installed/TubeArchivistMetadata?assemblyGuid=dc97d0c6-28b0-4242-afb4-5833ae1b3715&version=1.5.0.0"
   #   expect 204. Wait until §4.5 shows the scan Completed, THEN:
   curl -s -o /dev/null -w 'restart http=%{http_code}\n' -X POST -H "$AUTH" http://localhost:8097/System/Restart
   sleep 60; kill $PF 2>/dev/null; kubectl port-forward -n media svc/jellyfin 8097:8096 >/dev/null 2>&1 & PF=$!; sleep 3
   curl -s -H "$AUTH" http://localhost:8097/Plugins | python3 -c \
    "import sys,json;[print(p['Name'],p['Version'],p['Status']) for p in json.load(sys.stdin) if 'Tube' in p['Name']]"
   #   PASS: "TubeArchivist Metadata 1.5.0.0 Active". FAIL modes print 1.4.4.0, NotSupported,
   #   Malfunctioned, or nothing. A failure here is NOT a rollback trigger on its own (core
   #   upgrade is fine; the plugin can be retried) — record it and tell the operator.
   kubectl exec -n media "$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')" \
     -- sh -c 'ls -la /config/plugins/configurations/ | grep -i tubearchivist'
   #   the settings XML (1022 bytes pre-change) must still be present; if missing, restore it
   #   from the .pre12.bak copy made in step 2 and restart once more.
   ```

8. Run §4.

9. **On success**: restore remediation, commit, push; drop silence; clear marker.
   ```bash
   sed -i '' -e '/^  upgrade:/,/^  uninstall:/{s/^\([[:space:]]*retries:[[:space:]]*\)0$/\11/;s/^\([[:space:]]*remediateLastFailure:[[:space:]]*\)false$/\1true/;}' \
     kubernetes/apps/media/jellyfin/app/helmrelease.yaml
   git diff kubernetes/apps/media/jellyfin/app/helmrelease.yaml   # exactly retries 0->1, remediateLastFailure false->true
   printf '%s\n' "chore(jellyfin): restore Helm upgrade remediation after 12.2 migration" > /tmp/jf122-msg2.txt
   git commit --only kubernetes/apps/media/jellyfin/app/helmrelease.yaml -F /tmp/jf122-msg2.txt
   git log -1 --format=%s; git show --stat HEAD; git push
   curl -s -X DELETE localhost:9093/api/v2/silence/<silenceID>
   runbooks/update-marker.sh clear jellyfin
   kill $PF $AMPF 2>/dev/null
   ```
   Then: `jellyfin-12.1` -> superseded (if not already), this plan -> executed and the file
   retired per the plans README; record the post-upgrade scan on `F-3a72570a` (§4.8).

## 4. Verification

### 4.1 Floor (shape — necessary, not sufficient)

```bash
POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
kubectl get helmrelease -n media jellyfin -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pod -n media "$POD" -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
#   expect ...@sha256:357724bf0ae27a672c7cbaa899db2d9abeb13dbd8657ccce750258a4c059d037
curl -s http://localhost:8097/System/Info/Public | python3 -c "import sys,json;print(json.load(sys.stdin)['Version'])"
#   expect 12.2.x ; 10.11.x = rollout did not happen; HTTP 503 = still migrating
kubectl exec -n media "$POD" -- sh -c 'grep -io "<EnableLegacyAuthorization>[^<]*" /config/config/system.xml'
#   expect false — proves the legacy-auth migration ran
```

CONTROL: metric kube_deployment_status_replicas_available — `{namespace="media",deployment="jellyfin"}` must read 1 after the rollout (measured 1 on 2026-10-07); 0 = no serving pod.
CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="media",container="jellyfin"}` must not increase between `Startup complete` and the end of §4 (baseline 0); an increase = crash/liveness kill during scan.

### 4.2 CONTENTS ASSERTION — the library survived

CONTENTS ASSERTION: after the mandatory scan has Completed (§4.5), every non-zero counter
of `/Items/Counts` is >= its §2.2 baseline (2026-10-07: Movie 501 / Series 47 / Episode 2481 /
Song 631 / Album 40 / BoxSet 78; re-recorded at window time) — measured by Jellyfin's own API
with the modern header.

```bash
curl -s -H "$AUTH" http://localhost:8097/Items/Counts > /tmp/jf-counts-post.json
python3 - <<'EOF'
import json
pre=json.load(open('/tmp/jf-counts-pre.json')); post=json.load(open('/tmp/jf-counts-post.json'))
bad={k:(v,post.get(k)) for k,v in pre.items() if v>0 and (post.get(k) or 0)<v}
print('COUNTS_OK' if not bad else f'COUNTS_SHORT {bad}')
EOF
```
FAIL prints `COUNTS_SHORT {...}` (e.g. a dropped Movie count from un-restored alternate
versions, or all zeros from a schema-only migration). Evaluated mid-scan it is expected to
be low — only read it after §4.5. A persistent shortfall must be explained item-by-item
before acceptance.

### 4.2b CONTENTS ASSERTION — per-user watch state survived HarmonizeConflictingUserData

CONTENTS ASSERTION: for every user, `played` and `favorite` totals are >= the §2.2 baseline
(`/tmp/jf-userdata-pre.txt`).
```bash
# NB: never name the loop variable UID — it is a read-only special in zsh AND bash.
while read -r U_ID UNAME; do
  P=$(curl -s -H "$AUTH" "http://localhost:8097/Items?userId=$U_ID&Recursive=true&IsPlayed=true&Limit=0" | python3 -c "import sys,json;print(json.load(sys.stdin)['TotalRecordCount'])")
  F=$(curl -s -H "$AUTH" "http://localhost:8097/Items?userId=$U_ID&Recursive=true&IsFavorite=true&Limit=0" | python3 -c "import sys,json;print(json.load(sys.stdin)['TotalRecordCount'])")
  echo "$UNAME played=$P favorite=$F"
done < /tmp/jf-users.txt | tee /tmp/jf-userdata-post.txt
diff /tmp/jf-userdata-pre.txt /tmp/jf-userdata-post.txt && echo USERDATA_IDENTICAL
```
A small upward drift is plausible (harmonize keeps the "most" state; the rescan can add
items); a DROP for any user is a FAIL — the watch history is the data the household notices.
A Python traceback (KeyError TotalRecordCount) = the call 401'd; fix the header, do not pass.

### 4.3 CONTENTS ASSERTION — real login + auth paths

```bash
read -r -p 'Jellyfin admin user: ' JF_USER; read -r -s -p 'Jellyfin admin pw (not stored): ' JF_PW; echo
curl -s -X POST "http://localhost:8097/Users/AuthenticateByName" -H 'Content-Type: application/json' \
  -H 'Authorization: MediaBrowser Client="plan-verify", Device="cli", DeviceId="plan-verify", Version="1.0"' \
  -d "{\"Username\":\"$JF_USER\",\"Pw\":\"$JF_PW\"}" | python3 -c "import sys,json;d=json.load(sys.stdin);print('LOGIN_OK' if d.get('AccessToken') else 'LOGIN_FAIL')"
unset JF_PW
curl -s -o /dev/null -w 'apikey-modern http=%{http_code}\n' -H "$AUTH" http://localhost:8097/System/Info
curl -s -o /dev/null -w 'legacy-header http=%{http_code}\n' -H "X-Emby-Token: $JF_KEY" http://localhost:8097/System/Info
```
PASS: `LOGIN_OK`, modern 200, legacy **401**. (No SOPS secret holds a Jellyfin admin
password — operator types it; this check is attended.) Legacy 200 = the migration did not
flip the flag: investigate; do not leave legacy auth on. A JSON decode error on login = 401
body, i.e. FAIL.

### 4.4 CONTENTS ASSERTION — hardware transcode on the shared iGPU

```bash
kubectl exec -n media "$POD" -- sh -c '/usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -encoders 2>/dev/null | grep -c vaapi'   # >= 7
kubectl exec -n media "$POD" -- sh -c \
  '/usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -f lavfi -i testsrc=size=320x240:rate=5:duration=1 -vf format=nv12,hwupload \
     -c:v h264_vaapi -f null - && echo VAAPI_ENCODE_OK'
kubectl exec -n media "$POD" -- sh -c 'grep -io "<HardwareAccelerationType>[^<]*\|<EncoderPreset>[^<]*" /config/config/encoding.xml'
```
PASS: >= 7, `VAAPI_ENCODE_OK` printed, and encoding.xml still reads
`<HardwareAccelerationType>qsv` + `<EncoderPreset>medium` — the live values measured
2026-10-07 (NOTE: the server is configured for **qsv**, not vaapi, despite the VAAPI env vars;
compare against the §2.2 capture, not against an assumption). The 12.2
`FixNullEncoderPreset` / encoder-options migrations rewrite encoding.xml. FAIL: count 0,
no OK line (ffmpeg error text), or acceleration type changed (e.g. `none`).

### 4.5 The full scan actually ran

```bash
curl -s -H "$AUTH" http://localhost:8097/ScheduledTasks | python3 -c "
import sys,json
for t in json.load(sys.stdin):
    if t['Name']=='Scan Media Library':
        r=t.get('LastExecutionResult') or {}; print(t['State'], r.get('Status'), r.get('EndTimeUtc'))"
```
PASS: `Idle Completed <EndTimeUtc after RESTART_TS>`. The pre-change value
(2026-10-06T19:59:20Z) is the OLD scan, not evidence. If the scan outlasts the window, the
window may close on §4.1/4.3/4.4/4.6 green with §4.2/4.2b/4.5 handed to the same-day
post-window check; the plan is not `executed` until they pass.

### 4.6 Consumers across the auth change

```bash
J=coverage-post122-$(date +%H%M)
kubectl create job -n media --from=cronjob/media-metadata-coverage "$J"
kubectl wait -n media job/"$J" --for=condition=complete --timeout=10m
kubectl logs -n media job/"$J" | python3 -c "
import sys,json
ev=[json.loads(l) for l in sys.stdin if l.startswith('{')]
jf=[e for e in ev if e.get('event')=='coverage-jellyfin']
err=[e.get('code') for e in ev if e.get('event')=='coverage-http-error']
print('coverage-jellyfin total:', jf[0]['total'] if jf else 'MISSING', '| http errors:', err)"
```
PASS: total > 0 (baseline 548 on 2026-10-07) and no 401. FAIL prints `MISSING` or `[401]`.
Home Assistant (via ha-agent/hactl): Jellyfin entities not `unavailable` = expected green;
media-browser playback 401 = **expected casualty** (§1.4), recorded, not a rollback trigger.
Music Assistant 2.10.5: browse returns items AND a track plays = expected green; a 401 needs
a real look but is a client-side remedy, not a rollback trigger on its own.

### 4.7 External reachability + no new alerts

```bash
SECRET_DOMAIN=$(kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w 'edge http=%{http_code}\n' "https://jellyfin.${SECRET_DOMAIN}/System/Ping"   # 200 via envoy-external
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9091:9090 >/dev/null 2>&1 & PPF=$!; sleep 3
curl -s http://localhost:9091/api/v1/alerts | python3 -c "
import sys, json
for a in json.load(sys.stdin)['data']['alerts']:
    n=a['labels'].get('alertname')
    if n in ('Watchdog','InfoInhibitor'): continue
    print(n, a['labels'].get('namespace'), a['state'])"
kill $PPF 2>/dev/null
```
PASS: edge 200; no alert absent from the §2.1 baseline list. (Read with our own silence in
place: the silence suppresses notifications, not `/api/v1/alerts`, so a new media alert
still prints here.)

### 4.8 Security finding follow-through (F-3a72570a)

```bash
trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed docker.io/jellyfin/jellyfin:12.2.20261005-225228
```
Record the outcome on the finding (`runbooks/policy-cli.py finding detail F-3a72570a ...`),
never in this file. Already-newest residue is AR-029 territory, not a reason to hold.

## 5. Rollback (backup-restore — a tag revert alone is NOT a rollback)

Triggers: §4.1/§4.2/§4.2b/§4.3 FAIL that cannot be explained, migration crash-loop, or
`LogCritical` on startup. NOT triggers: TubeArchivist 1.5.0 install failure (§3 step 7),
HA media-browser 401 (§1.4).

```bash
cd /Users/mu/code/cberg-home-nextgen
# 0) Freeze Flux FIRST so neither the revert push nor Helm remediation starts 10.11.11
#    against the migrated DB, and nothing re-applies PV/PVC mid-restore:
flux suspend kustomization -n media jellyfin
flux suspend helmrelease -n media jellyfin
# 1) Revert the bump in git (keeps git honest; inert while suspended):
git log --oneline -5 -- kubernetes/apps/media/jellyfin/app/helmrelease.yaml
git revert --no-edit <bump-commit>
git log -1 --format=%s; git show --stat HEAD
git push
# 2) Free the volume:
kubectl scale deploy -n media jellyfin --replicas=0
kubectl wait -n media --for=delete pod -l app.kubernetes.io/name=jellyfin --timeout=5m
```

3) Restore `jellyfin-config` from the backup_gate Backup CR (name recorded in §3 step 1).
`spec.csi.volumeHandle` is immutable and `pv/jellyfin-config` + `pvc/jellyfin-config` are
git-tracked (`kubernetes/apps/media/jellyfin/app/config-pv.yaml`, `config-pvc.yaml`), so the
restore goes to a NEW volume name and git is re-pointed (procedure reviewed for jellyfin-12.1):

- (a) Longhorn UI (`kubectl port-forward -n storage svc/longhorn-frontend 8080:80`) -> Backup
  -> jellyfin-config -> <gate backup> -> Restore -> name `R=jellyfin-config-r$(date +%Y%m%d)`,
  accessMode rwx, replicas 2 (match the live volume; git's config-pv.yaml says "3" — write the
  value you chose into the PV). Wait until
  `kubectl get volumes.longhorn.io -n storage $R -o jsonpath='{.status.state} {.status.restoreRequired}'`
  prints `detached false` (restore finished, volume idle).
- (b) In git (`--only` these two files, do not push yet): `config-pv.yaml` metadata.name and
  csi.volumeHandle -> `$R` (keep RWX, 25Gi, longhorn-static, Retain, ext4,
  staleReplicaTimeout "30"); `config-pvc.yaml` spec.volumeName -> `$R` (PVC NAME STAYS
  `jellyfin-config`).
- (c) Storage-safety pre-flight, then delete the OLD PVC + PV (Longhorn, Retain — the old
  Longhorn volume survives for forensics). `pvc/jellyfin-media` is never named:
  ```bash
  PV=$(kubectl -n media get pvc jellyfin-config -o jsonpath='{.spec.volumeName}')
  kubectl get pv "$PV" -o jsonpath='{.spec.csi.driver} {.spec.persistentVolumeReclaimPolicy} {.spec.csi.volumeHandle}{"\n"}'
  #   MUST print: driver.longhorn.io Retain jellyfin-config — anything else: STOP.
  kubectl -n media delete pvc jellyfin-config
  kubectl delete pv "$PV"
  ```
- (d) Push (b), then resume:
  ```bash
  git push
  flux resume kustomization -n media jellyfin
  kubectl -n media get pvc jellyfin-config -o jsonpath='{.status.phase} {.spec.volumeName}{"\n"}'   # Bound jellyfin-config-r<date>
  flux resume helmrelease -n media jellyfin
  flux reconcile helmrelease -n media jellyfin --force    # HR was suspended; force a fresh upgrade to the reverted values
  ```

Confirm we are actually back — by digest and contents, not Ready:
```bash
POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
kubectl get pod -n media "$POD" -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
#   MUST be ...@sha256:aefb67e6a7ff1debdd154a78a7bbb780fd0c873d8639210a7f6a2016ad2b35db
kubectl exec -n media "$POD" -- sh -c 'grep -o "<EnableLegacyAuthorization>[^<]*" /config/config/system.xml; ls /config/plugins'
#   MUST be true (pre-migration DB/config) and TubeArchivistMetadata_1.4.4.0 present (backup
#   predates the uninstall). `false` = you are looking at the migrated volume, not the restore.
curl -s -H "$AUTH" http://localhost:8097/Items/Counts      # must match /tmp/jf-counts-pre.json
```
Ensure remediation in git is back to `retries: 1` / `remediateLastFailure: true` (the
revert restores it). Clear silence + marker. Then tell the window agent that
`jellyfin-config-rwo-migration` must be re-derived for volume `$R` (§0).

## 6. Interference notes

- **Supersession (§0)**: `jellyfin-12.1` must be marked superseded and lose its window before
  this plan is scheduled; `conflicts_with` lists it so the two can never share a slot.
- **Window recommendation**: attended Saturday, human-gated (capability_change + backup-restore
  => never unattended). Preferred: take over `sat-attended:2026-10-10` (sole occupant was
  jellyfin-12.1; 70/90 min, risk 3/6) if review + GO land in time; else the next attended
  slot with capacity **before** `sun-attended:2026-10-25` (rwo migration). If neither is
  possible, the rwo migration must move after this plan, not before (or both plans get
  re-derived).
- **igpu-i915**: pod on k8s-nuc14-01 with immich-server + makemkv. `immich-machine-learning-3.2.4`
  (nightly:2026-10-11) and `talos-power-tuning-ab` are in `conflicts_with`.
- **backup-restore stacking**: n8n-2.39.8 (sun 10-11), paperless-db-13.0.2 (sat 10-24),
  nextcloud-fleet-35.0.1 (sun 10-18), nocodb, media-naming-p3 — never in the same slot.
- **Prometheus**: §4.7 reads `/api/v1/alerts`; `kube-prometheus-stack-91.9.0`
  (nightly:2026-10-08) is listed.
- **The backup_gate Job backs up EVERY Longhorn volume** (~12 min, extra NAS/backup-target
  load); avoid a slot that also runs a Longhorn-heavy plan (longhorn-1.13.0 listed).
- **No CIFS PVC action** anywhere in this plan; `cifs-jellyfin-media` is Tier-1.
- **Biggest gotcha**: Pod Ready / HR Ready / `/health` 200 all arrive while the forward-only
  migration is still running (SetupServer). Judge only on `Startup complete` + `/System/Info/Public`
  200 + the contents assertions — and never "roll back" with a bare `git revert`: 10.11.11 on a
  migrated DB is the documented failure mode; §5's restore is the rollback.
