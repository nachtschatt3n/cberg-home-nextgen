---
plan_id: jellyfin-12.2.20261005       # KEPT per plans/README "When the held target MOVES": the id is an identifier, not an
                                      # assertion. `target:` below (12.3) is authoritative. Refreshed in place 2026-10-23.
component: jellyfin
pr: null                              # No Renovate PR for the 12.x image (coverage.py / F-fc5e2913 surfaces it). Renovate
                                      # PR 410 (chart 3.4.0 -> 3.6.0) is chart-only and is INERT for the image: the
                                      # HelmRelease pins image.tag, and 3.6.0 differs from 3.4.0 ONLY in Chart.yaml
                                      # appVersion 12.2 -> 12.3 (diffed 2026-10-23). It may land before or after this plan.
kind: image
current: "10.11.11.20260606-153911"   # live 2026-10-23: deployment image, pod jellyfin-7cf49bc86b-lrg7s on
                                      # k8s-nuc14-03, 0 restarts. Plugins: 5 built-ins 10.11.11.0 + TubeArchivist Metadata 1.4.4.0.
target: "12.3.20261023-013714"        # Docker Hub: this tag, `12.3`, `12` and `latest` all resolve to index digest
                                      # sha256:2038fe038ab3876a80f6e7b7e0aef6607b032c7dc0c9b3ad3296d0b2eba3bbb5
                                      # (measured 2026-10-23; registry HEAD 200). GitHub release v12.3: prerelease=false,
                                      # draft=false, 2026-10-23T00:30:06Z. Matching chart: 3.6.0 (appVersion 12.3), see pr.
update_type: major
risk: high                            # Unchanged basis: forward-only DB migration chain (10.11 -> 12.x schema, incl. the three
                                      # 12.2 migrations) on the household's actively used, internet-facing media server;
                                      # one repository plugin removed first; legacy-auth switch-off and legacy-route removal
                                      # change client behaviour. 12.3 itself adds NO migration (compare v12.2...v12.3, below).
est_duration_min: 100                 # Happy path, EXCLUDING rollback and excluding any WAITING-for-password time:
                                      # pre-checks+baselines+silence+etcd gate 18 · backup_gate ~12 (the CronJob trigger backs
                                      # up EVERY volume) · plugin uninstall 3 · commit+reconcile+first-boot migration 20 ·
                                      # mandatory full scan ~15 · plugin 1.5.0 install + restart (+ pod-delete fallback) 8 ·
                                      # verification 17 · remediation restore + cleanup 5 · slack 2 = 100.
                                      # ROLLBACK BUDGET IS SEPARATE: ~30-45 min (Longhorn restore from backup + PV/PVC
                                      # re-point + re-verify, §5). Worst case 100 + 45 = 145. Attended ad-hoc run; Step 0
                                      # (safe-update apply, ~20 min) runs FIRST by contract and is additional.
needs_reboot: false
touches:
  namespaces: [media, storage]        # storage: the backup_gate creates a Job from cronjob/storage/daily-backup-all-volumes
  resources:
    - helmrelease/jellyfin
    - deployment/jellyfin
    - pvc/jellyfin-config-rwo           # POST-MIGRATION config volume: longhorn-static RWO 25Gi, ext4 block device (no NFS).
                                        # jellyfin.db, plugins/, users: everything that matters. Created by
                                        # jellyfin-config-rwo-migration; this plan runs AFTER it.
    - pv/jellyfin-config-rwo            # only on ROLLBACK (§5 restore re-points the PV)
    - volume.longhorn.io/jellyfin-config-rwo
    - pvc/jellyfin-config               # OLD RWX claim kept by the migration plan for 14 days, UNMOUNTED. NOT touched here;
                                        # named so nobody deletes it as part of this plan (its retirement is a separate,
                                        # operator-approved plan, and it holds only the PRE-12 DB so it is no rollback for this plan)
    - pvc/jellyfin-media                # cifs-jellyfin-media, Tier-1 catastrophic: NOT touched; named so nobody touches it
    - plugin/TubeArchivistMetadata      # 1.4.4.0 (targetAbi 10.11) uninstalled before the bump, 1.5.0.0 (targetAbi 12.0) after
    - configmap/library-tools-scripts   # READ ONLY: gate G3 asserts 0 legacy-header call sites
    - cronjob/media-metadata-coverage   # consumer of the Jellyfin API (verification 4.6)
    - cronjob/media-per-item-refresh    # consumer of the Jellyfin API
    - cronjob/media-intake-watcher      # consumer (folder-scoped /Library/Media/Updated rescans)
    - deployment/media-dashboard        # renders coverage output
    - cronjob/daily-backup-all-volumes  # ns storage: triggered once for the backup_gate
  shared: [igpu-i915, gateway/envoy-external, storage/longhorn]
                                        # igpu-i915: pod requests+limits gpu.intel.com/i915: 1 (currently k8s-nuc14-03, the only
                                        # i915 claimant there; the migration's stop/start may reschedule it: re-read the node in
                                        # section 2.1). envoy-external: public HTTPRoute, client behaviour changes.
                                        # storage/longhorn: all-volume backup trigger + (rollback) a restore.
depends_on: [jellyfin-config-rwo-migration]
conflicts_with:                         # pruned 2026-10-23 to plans that are still open (status not executed/superseded);
                                        # dropped: jellyfin-12.1, n8n-2.39.8, paperless-db-13.0.2 (executed/superseded), the
                                        # kube-prometheus-stack-92.* trio (no open kps plan; re-add if one is re-opened, the
                                        # window's Prometheus is shared infra), nextcloud-fleet-35.0.1 and coredns-1.48.2 (no file).
  - media-naming-p3                   # backup-restore stacking (draft, unscheduled)
  - nocodb-2026.09.1                  # backup-restore stacking (awaiting-go); never in the same slot
  - helm-drift-detection              # touches helmrelease/media/jellyfin + rolls intel-gpu-plugin
  - flux-oci-chart-sources            # mirrors the jellyfin chart source
  - flux-distribution-2.9.6           # Flux controllers under this plan's GitOps step (carried over)
  - talos-power-tuning-ab             # igpu-i915; carried over
  - talos-linux-1.14.2                # cluster-wide node roll incl. igpu-i915 + longhorn
  - talos-linux-1.14.4                # same class (draft)
  - longhorn-1.13.0                   # backup_gate + restore path run on the engine it replaces
  - etcd-timeouts-5000-500            # control-plane change; do not stack with a backup-restore plan
  - cilium-1.20.3                     # CNI roll: a datapath bounce reads as a Jellyfin or consumer failure (4.6, 4.7)
  - node-feature-discovery-0.20.0     # restarts i915 claimants / GPU labels; the pod must schedule against stable labels
exclusive: false
security_ref: F-3a72570a              # security finding on the CURRENT image: detail on the record only. We bump, we never rebuild.
capability_change: true               # Upstream-documented behaviour changes in 10.11 -> 12.x: legacy /emby and /mediabrowser
                                      # routes REMOVED, legacy authorization switched OFF by migration (HA media-browser
                                      # playback 401s until HA ships apiclient >= 1.17), subtitle config moves global -> per-library.
rollback_class: backup-restore        # 12.0 notes: "database changes that prevent rolling back without a full restore"; 12.2 adds
                                      # three more forward migrations. A bare tag revert is NOT a rollback.
backup_gate: "on-demand Longhorn backup of volume jellyfin-config-rwo, triggered IN-WINDOW as the FIRST mutating step (section 3
  step 1), before the plugin uninstall and the tag bump, while the 10.11.11 pod is running (volume attached;
  allow-recurring-job-while-volume-detached=false). PASS = a NEW Completed Backup CR labelled backup-volume=jellyfin-config-rwo
  whose creationTimestamp > GATE_START, AND `runbooks/longhorn-backup-age.py jellyfin-config-rwo --max-hours 1` prints FRESH.
  Triggered via cronjob/daily-backup-all-volumes (ns storage). The label selector must name the NEW volume: the OLD volume
  jellyfin-config is detached after the migration and its backups go STALE by design, so a gate on the old name is a false
  signal in both directions."
restore_proof: "No separate scratch-restore rehearsal in this plan. The restore METHOD (Longhorn fromBackup into a new
  volume, mounted read-only, sqlite integrity_check + non-zero BaseItems) is exercised by jellyfin-config-rwo-migration
  section 3.4 on the same backup chain immediately before this plan; this plan's own proof is section 5(f): after a
  restore the DB opens, EnableLegacyAuthorization reads true, the 10.11.11 digest is back and /Items/Counts equals the
  pre-change baseline."
finding_refs: [F-fc5e2913, F-3a72570a]
review: ready-for-go@2026-10-23   # plan-reviewer 2026-10-23 on the 12.3 rewrite: needs-fix (PW-1 zsh prompt, gate 4.7 alert baseline) -> both fixed and dry-tested under zsh; target/digest, no 12.2->12.3 migration, sed edits, objects, volume names verified; 7 pre-migration premises pass, 5 post-migration premises fail by design until jellyfin-config-rwo-migration has run. Still needs: migration executed, ha-agent check of the HA Jellyfin client pin, operator at the keyboard for PW-1, fresh GO
status: vetted
window: null                          # `runbooks/run-now.py stamp` / the window agent write this. Not hand-written.
premises:
  # Two groups. GROUP A must PASS before and after the migration. GROUP B (ids prefixed `post-migration-`) describes the
  # layout AFTER jellyfin-config-rwo-migration and is EXPECTED TO FAIL BY DESIGN until that plan has executed (same
  # dependent-plan pattern as the chart/image halves of open-webui). A failing GROUP B premise while
  # jellyfin-config-rwo-migration is not yet `executed` is NOT a defect; it is the ordering guard. At run time ALL must pass.
  - id: image-is-still-10.11.11
    why: >-
      Every baseline (counts, digest for rollback, plugin inventory) is captured against 10.11.11. If anything already moved
      the image, this plan is stale: a 12.x -> 12.3 hop is a different (smaller) job and must be re-derived.
    run: kubectl get deploy -n media jellyfin -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: docker.io/jellyfin/jellyfin:10.11.11.20260606-153911
  - id: chart-is-3.4-to-3.6
    why: >-
      Renovate PR 410 (chart 3.6.0) may land at any time and is inert for the image (appVersion-only diff, tag is pinned).
      Anything outside 3.4.0-3.6.0 means the chart moved in a way this plan did not review: stop and re-diff.
    run: kubectl get helmrelease -n media jellyfin -o jsonpath='{.spec.chart.spec.version}'
    expect_matches: '^3\.[456]\.0$'
  - id: media-storageclass-reclaim-retain
    why: >-
      cifs-jellyfin-media is subdir / on the whole NAS media export (Tier-1). This plan performs NO action on it; if it
      ever reads Delete, STOP and surface it.
    run: kubectl get sc cifs-jellyfin-media -o jsonpath='{.reclaimPolicy}'
    expect_exact: Retain
  - id: hr-remediation-at-default
    why: >-
      Step 3 sets retries 0 for the migration and step 9 restores 1. A 0 at window start means an earlier attempt was left
      half-done.
    run: kubectl get helmrelease -n media jellyfin -o jsonpath='{.spec.upgrade.remediation.retries}'
    expect_exact: "1"
  - id: deployment-strategy-recreate
    why: >-
      The old pod must fully release the RWO volume and its i915 slot before the 12.3 pod starts its migration; a surge pod
      would be Multi-Attach-blocked on RWO and, worse on any other volume, run two Jellyfin processes on one SQLite DB.
    run: kubectl get deploy -n media jellyfin -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: replicas-is-one
    why: >-
      The migration plan stops Jellyfin (replicaCount 0) and restores 1 in its cutover commit. A 0 here means the migration is
      half-done (between its commit A and B): do not start.
    run: kubectl get deploy -n media jellyfin -o jsonpath='{.spec.replicas}'
    expect_exact: "1"
  - id: intake-watcher-apply-enabled
    why: >-
      The migration plan flips INTAKE_APPLY to 0 during its stop and back to 1 at cutover. A 0 here means it never finished,
      and this plan's consumer checks (4.6) would be reading a deliberately idled watcher.
    run: kubectl get cronjob -n media media-intake-watcher -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].env[?(@.name=="INTAKE_APPLY")].value}'
    expect_exact: "1"
  - id: post-migration-config-pvc-is-rwo-static
    why: >-
      EXPECTED TO FAIL BY DESIGN until jellyfin-config-rwo-migration has executed. The backup_gate and section 5 restore are
      written for the static speaking-name RWO claim jellyfin-config-rwo bound to PV jellyfin-config-rwo. Failing at run time
      means the migration did not land (or was rolled back): this plan names the wrong volume, do not run it.
    run: kubectl get pvc -n media jellyfin-config-rwo -o jsonpath='{.spec.storageClassName} {.spec.accessModes[0]} {.spec.volumeName}'
    expect_exact: longhorn-static ReadWriteOnce jellyfin-config-rwo
  - id: post-migration-helmrelease-mounts-rwo
    why: >-
      EXPECTED TO FAIL BY DESIGN until the migration has executed (it repoints existingClaim from jellyfin-config).
    run: kubectl get helmrelease -n media jellyfin -o jsonpath='{.spec.values.persistence.config.existingClaim}'
    expect_exact: jellyfin-config-rwo
  - id: post-migration-volume-attached
    why: >-
      EXPECTED TO FAIL BY DESIGN until the migration has executed. The on-demand backup only runs on an attached volume.
    run: kubectl get volumes.longhorn.io -n storage jellyfin-config-rwo -o jsonpath='{.status.state}'
    expect_exact: attached
  - id: post-migration-volume-is-rwo
    why: >-
      EXPECTED TO FAIL BY DESIGN until the migration has executed. Proves the Longhorn volume itself is rwo (not just the PVC),
      i.e. SQLite is on a block device, which is what the 10.11 -> 12 DB rewrite should run on.
    run: kubectl get volumes.longhorn.io -n storage jellyfin-config-rwo -o jsonpath='{.spec.accessMode}'
    expect_exact: rwo
  - id: post-migration-pv-retain-speaking-name
    why: >-
      EXPECTED TO FAIL BY DESIGN until the migration has executed. section 5 (c) deletes this PV after a pre-flight
      that demands `Retain` and volumeHandle jellyfin-config-rwo; assert the same facts before the window, not at the
      worst moment. (The /config-is-not-NFS proof needs `kubectl exec`, which premises may not use: it is a G0 command.)
    run: kubectl get pv jellyfin-config-rwo -o jsonpath='{.spec.persistentVolumeReclaimPolicy} {.spec.csi.volumeHandle}'
    expect_exact: Retain jellyfin-config-rwo
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/storage-safety.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-23"
---


# jellyfin: image 10.11.11.20260606-153911 -> 12.3.20261023-013714 (major)

## 0. Relationship to `jellyfin-config-rwo-migration` and `jellyfin-12.1`, and what changed in this refresh

**Refreshed in place 2026-10-23** (README "When the held target MOVES": the plan id is kept, `target:` is
authoritative). Three things moved underneath the 2026-10-13 vetted version, so its review and GO do NOT
transfer; it needs a new review:

1. **Upstream retargeted 12.2 -> 12.3.** Jellyfin v12.3 is GA (prerelease=false, 2026-10-23T00:30:06Z). The old
   gate G1 ("anything newer than v12.2 exists: STOP and refresh") fired, as designed. Target is now
   `12.3.20261023-013714`. 12.3 is a 7-change bugfix release with **no new migration** (section 1.3), so the
   forward-only surface is exactly the 12.2 plan's (10.11 -> 12.x set), not larger.
2. **The chart moved.** HelmRelease is on chart 3.4.0 (auto-merged 2026-10-22, PR 388); held PR 410 proposes 3.6.0.
   Diffed 2026-10-23: 3.4.0 -> 3.6.0 changes only `Chart.yaml` (`appVersion` 12.2 -> 12.3, `version`) and README.
   Templates and default values are identical, and our values pin `image.tag`, so the chart version is irrelevant to
   the image rollout. This plan does NOT edit `chart.spec.version`; premise `chart-is-3.4-to-3.6` tolerates PR 410
   landing before or after.
3. **Order (operator decision 2026-10-23): `jellyfin-config-rwo-migration` FIRST, then this plan.** The config volume
   becomes the static speaking-name RWO volume `jellyfin-config-rwo` (Longhorn Volume = PV = PVC = volumeHandle, ext4
   block device, no NFS hop under SQLite WAL). Every backup, restore and rollback step below names the NEW volume.
   The old RWX volume `jellyfin-config` stays, unmounted, for 14 days as the migration plan's rollback source; it
   holds only the PRE-12 database, so it is **not** a rollback source for this plan.
   `depends_on: [jellyfin-config-rwo-migration]`; the reverse `conflicts_with` is gone.

**Why the order is good for this plan:** the 10.11 -> 12 DB rewrite plus the first full scan are exactly the SQLite
load that produced `database is locked` over NFS (migration plan section 1). Running them on the RWO block device
removes that risk from the forward-only step. The migration plan's `baseitems > 0` restore-proof (its section 3.4)
is valid for the 10.11 schema it runs on; this plan's section 5 restore proof for the post-12 schema is in 5(f).

**Same-day sequencing.** Both are attended and both trigger the all-volumes backup. Run them in ONE run record but
SEQUENTIALLY, and do not start this plan until the migration's section 4 gates are green AND its cutover commit B is
pushed (premises `replicas-is-one`, `intake-watcher-apply-enabled`, all `post-migration-*`). Do NOT reuse the
migration's backup as this plan's backup_gate: this plan takes its own, FIRST, on the migrated volume.
If the migration ROLLS BACK (R2), the `post-migration-*` premises fail and this plan stays parked.

**`jellyfin-12.1`** is `status: superseded` (by this plan id) and cannot share a window; it is no longer listed in
`conflicts_with` because it is not open.

### 0.1 Prerequisites (all must be true before the go)

1. `jellyfin-config-rwo-migration` has **executed** with all 12 of its premises green afterwards (re-run its
   `plan-premises.py`), and its section 4 gates are green; it is a separate run record that must be closed first.
2. **Operator-side pre-go item:** ask ha-agent whether Home Assistant's Jellyfin client is still pinned to
   `jellyfin-apiclient-python==1.16.0` (1.4: if yes, HA media-browser playback will 401 after the upgrade; accepted
   casualty, not a blocker, but the operator should know before saying go).
3. The operator is at the keyboard for **PW-1** (the admin password); everything else is runnable without them.
4. A new plan review (the 2026-10-13 `ready-for-go` does not transfer) and a fresh GO.

## 1. Summary & why held

Move `deployment/jellyfin` (ns `media`) from `docker.io/jellyfin/jellyfin:10.11.11.20260606-153911` to
`:12.3.20261023-013714`. Only the image tag (and, temporarily, Helm remediation) changes in
`kubernetes/apps/media/jellyfin/app/helmrelease.yaml`; the chart version is not touched by this plan.
Tag layout: upstream publishes `X.Y.Z.<yyyymmdd-hhmmss>` (10.x: 4-part version) and, from 12.0, `X.Y.<date-time>` plus
floating `12.3`, `12`, `latest`; the repo has always pinned the full dated tag, and so does this plan. Per-arch tags
(`12.3-amd64.<ts>`) exist and must NOT be used: the multi-arch index tag is the one whose digest is gated.
Security driver: `F-3a72570a` (detail on the record only); version row `F-fc5e2913`.

### 1.1 Held because

`update_type: major` routes to the plan lane in `coverage.py` regardless of any deny rule. Not a false positive.

### 1.2 Breaking changes 10.11 -> 12.x (v12.0 release notes, re-read 2026-10-23; all still apply at 12.3)

1. **Forward-only DB migration** - *"this release includes database changes that prevent rolling back without a full
   restore."* -> `backup-restore`, mandatory `backup_gate`. Direct 10.11.x -> 12.0 is supported (*"intermediate upgrades
   are not required"*). 12.0 also: relational `LinkedChildren` table (playlists/collections), `OwnerId` and
   `PrimaryVersionId` become GUID FKs, `ExtraIds` dropped, duplicate artists/people merged and orphaned extras removed
   on first boot. 12.1 hardened the server's own pre-migration backup (#17836) - section 3 step 5 checks it exists, as
   a second line of defence, not as the backup_gate.
2. **Remove repository plugins first** - *"Installed repository plugins (anything not built-in) should also be removed
   before migrating ... re-adding them afterward is the safest approach."* Live 2026-10-23 (read-only `/Plugins`):
   AudioDB, MusicBrainz, OMDb, Studio Images, TMDb (all built-in, 10.11.11.0, migrate with the server) and
   **TubeArchivist Metadata 1.4.4.0 (the only repository plugin)**. Repositories configured: "Jellyfin Stable"
   (`repo.jellyfin.org/files/plugin/manifest.json`, the URL the notes require) and "TubeArchivistMetadata", whose manifest
   lists `1.5.0.0 targetAbi 12.0.0.0` (re-read 2026-10-23).
3. **Legacy route prefixes removed** (`/emby/*`, `/mediabrowser/*`), plus removed API routes (`EasyPassword`,
   `CriticReviews`, `Environment/NetworkShares`, `System/MediaEncoder/Path`, a LiveTv recordings-group route). No
   in-repo consumer uses them (grepped 2026-10-07; re-asserted by gate G3).
4. **Legacy authorization disabled by migration** (`20260531160000_DisableLegacyAuthorization`; unchanged through
   v12.3). `X-Emby-Token`, `X-MediaBrowser-Token`, `api_key=`, `X-Emby-Authorization` stop working;
   `Authorization: MediaBrowser Token="..."` and `ApiKey=` keep working. Live `system.xml` has
   `<EnableLegacyAuthorization>true` (2026-10-23), so the migration WILL fire.
5. **Usernames are normalised with a unique index** - *"installs with usernames that differ only by case need to be
   corrected before upgrading"*. Checked live 2026-10-23: 1 user, 1 case-folded name, no collision; gate G2
   re-asserts it.
6. Subtitle config moves global -> per-library; `.ogg`/`.aifc`/`.aiff` reclassified.
7. **Mandatory full library scan after upgrade** - *"Perform a full library scan to restore alternative versions"*.
8. Config-file surface: of the files we persist under `/config/config` (`system.xml`, `encoding.xml`, `network.xml`,
   `branding.xml`, `database.xml`, `metadata.xml`, `xbmcmetadata.xml`), the notes name only the legacy-auth flag
   (`system.xml`), subtitle settings and the encoder-preset migration (`encoding.xml`). `network.xml` is NOT named in
   any 12.0-12.3 note and the v12.3 diff touches no config schema; section 4.1 still diffs it before/after rather than
   trusting that.

### 1.3 What 12.2 added (v12.2 notes: 51 changes; read from `compare/v12.1...v12.2`)

**12.2 adds migrations**, so the forward-only surface grows beyond 12.0/12.1 (unchanged from the previous revision):

- `Routines/20260912120000_HarmonizeConflictingUserData.cs` (`[JellyfinMigrationBackup(JellyfinDb = true)]`) - collapses
  conflicting per-user watch-state rows. Touches user watch history: section 4.2b checks it.
- `Routines/20260915104305_FixNullEncoderPreset.cs` - *"Fix transcoding settings migration failure caused by null
  EncoderPreset"* (#18059). Directly relevant: encoding.xml is rewritten; section 4.4 proves hardware encode afterwards.
- EF migration `20261002210711_MakeOwnerIdIndexesPartial` and a perf fix to `ChangeOwnerIdToGuid` (#18073).
- `JellyfinMigrationService.EnsureExistingDatabaseAsync` (#18264): a server whose `IsStartupWizardCompleted` is true but
  whose DB is missing/empty now **refuses to start** (LogCritical, throws). A botched restore or wrong mount
  crash-loops loudly instead of coming up as a blank server.
- #18102 *"Never treat unresolvable libraries as grounds for deletion"* - relevant to a CIFS-backed library.

### 1.3b What 12.3 adds (v12.3 notes: 7 changes; `compare/v12.2...v12.3` = 14 commits, read 2026-10-23)

Changed files: version/csproj bumps, `Directory.Packages.props` ("Update Microsoft", .NET package refresh),
`logging.json` (suppresses useless warnings), `BaseItem.cs`, `MediaEncoder.cs`, `ProbeResultNormalizer.cs`,
`SubtitleEncoder.cs`, `TmdbUtils.cs`, and tests. **No file under `Jellyfin.Server.Implementations/Migrations` or
`Routines`: 12.3 adds NO database migration and no config/auth change.** Notes: not-finite ratings/gains no longer
stored (#18267); TMDb year-off-by-one ranking tie (#18343); crash fixes for a subtitle charset without a .NET encoding
(#18309) and for probing streams without frame size (#18243). Effect on us: none of these touch the VAAPI/QSV argument
builders (`EncodingHelper`, not in the diff), but `MediaEncoder.cs` is, so section 4.4 still proves the encoders.
Net: 12.3 does not make the job riskier or smaller than the 12.2 plan; it fixes two probe/subtitle crashes.

### 1.4 Clients on the other side of the auth change (re-measured 2026-10-07; re-read at run time)

`/Devices` app families: Jellyfin Web (10.10.6..10.11.11), Jellyfin iOS/iPadOS 1.7.0, Jellyfin tvOS 1.0.1, Infuse-Direct
8.1.5, Home Assistant (3), Music Assistant (2.10.5, 2.5.8).

- **In-repo**: `configmap/library-tools-scripts` has **0** `X-Emby-Token` call sites (re-measured 2026-10-23, gate G3).
  Last coverage run on 10.11.11: `coverage-jellyfin total 548, http errors []`.
- **Home Assistant** (live 2026.9.x at last look) pins `jellyfin-apiclient-python==1.16.0`. Expected casualty:
  entities and media_player keep working; **playing/browsing Jellyfin items from HA's media browser 401s** until HA
  ships the newer client. Remedy is an HA update, NOT re-enabling legacy auth. Re-check the pin at run time with
  ha-agent before the go (a newer HA may have fixed it).
- **Music Assistant 2.10.5**: expected green (rewrites `api_key` -> `apiKey`); re-checked live in 4.6, not assumed.

## 2. Pre-checks

### 2.1 State (measured 2026-10-23, PRE-migration; re-measure at run time - the migration changes the rows marked *)

- *`pvc/jellyfin-config` (RWX, NFS) is what is mounted today (`/config` = `10.96.70.218:/jellyfin-config`). After the
  migration it is `pvc/jellyfin-config-rwo` -> PV -> Longhorn Volume `jellyfin-config-rwo` (all one identifier),
  longhorn-static RWO 25Gi, 2 replicas, ext4 block device, `/config` source `/dev/longhorn/jellyfin-config-rwo`.
  ~5.8G used; `jellyfin.db` 64.8 MB.
- `pvc/jellyfin-media` -> `cifs-jellyfin-media`, `subdir: /`, Retain - Tier-1 catastrophic.
  **No PVC action of any kind on this claim, happy path or rollback.**
- *Pod `jellyfin-7cf49bc86b-lrg7s` on `k8s-nuc14-03` (the only i915 claimant there); the migration's Recreate may land
  it elsewhere - record the node at run time. Strategy Recreate, privileged (AR-009).
- Plugins dir: `configurations/`, `TubeArchivistMetadata_1.4.4.0/` (contains a `.nfs*` silly-rename file ONLY while on
  NFS; on the RWO volume the directory removes cleanly, but the API uninstall in step 2 is used either way).
- Plugin settings: `plugins/configurations/Jellyfin.Plugin.TubeArchivistMetadata.xml` - copied aside in step 2.
- Alerts (excluding Watchdog/InfoInhibitor): re-record at window time; attribute only NEW alerts to this change.
- Library baseline (`/Items/Counts`, last measured 2026-10-07: Movie 501, Series 47, Episode 2481, Song 631, Album 40,
  BoxSet 78) - **re-recorded at run time after the migration**, because the migration plan's own baseline is the
  authority for "nothing was lost in the copy"; this plan's baseline is "what the 10.11.11 server serves right now".

### 2.2 Commands - G0..G3 are ABORT gates, PW-1 is the only password gate (section 4.3)

```bash
cd /Users/mu/code/cberg-home-nextgen
S=$(mktemp -d "${TMPDIR:-$HOME}/jf-12-3.XXXXXX"); echo "S=$S"     # scratch: never /tmp, never the repo

# --- G0 (ABORT): the config-volume migration has landed. Premises, ALL of them, must PASS (group A and group B).
.venv/bin/python3 runbooks/plan-premises.py jellyfin-12.2.20261005
#   Any FAIL in a `post-migration-*` premise = jellyfin-config-rwo-migration has not executed: STOP, run it first.
#   Any FAIL in group A = the plan is stale or the migration is half-done (replicas 0 / INTAKE_APPLY 0): STOP.
.venv/bin/python3 runbooks/maintenance-plan.py --open | grep -E 'jellyfin-config-rwo-migration' || true
#   The migration plan must read executed (or be absent from --open). It must NOT be mid-run.
kubectl exec -n media deploy/jellyfin -- grep ' /config ' /proc/mounts
#   MUST start with /dev/longhorn/jellyfin-config-rwo and say ext4. FAILS (prints `<ip>:/jellyfin-config /config nfs4`)
#   if the pod is still on the old NFS volume (measured that way 2026-10-23, pre-migration).

# --- G1 (ABORT): drift gate - the target is still the NEWEST stable, and still the same bytes.
#     Use `gh api` - unauthenticated curl to api.github.com is rate-limited from this IP.
gh api repos/jellyfin/jellyfin/releases --jq '[.[]|select(.prerelease==false and .draft==false)][0].tag_name'
#   MUST print: v12.3.   Anything else (v12.4, v13...) = STOP and refresh the plan (README "target MOVES").
#   Filtering out prereleases matters: `.[0]` alone would trip on a 12.4-rc and cry wolf.
gh api repos/jellyfin/jellyfin/releases/tags/v12.3 --jq '[.tag_name,.prerelease,.draft]|@tsv'     # v12.3  false  false
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:jellyfin/jellyfin:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -D - -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  "https://registry-1.docker.io/v2/jellyfin/jellyfin/manifests/12.3.20261023-013714" | grep -iE '^HTTP|docker-content-digest'
#   MUST be HTTP/2 200 and digest sha256:2038fe038ab3876a80f6e7b7e0aef6607b032c7dc0c9b3ad3296d0b2eba3bbb5.
#   A different digest = upstream re-pushed the tag: STOP and re-derive. (Measured 2026-10-23.)
curl -s "https://hub.docker.com/v2/repositories/jellyfin/jellyfin/tags?page_size=10&ordering=last_updated" \
  | python3 -c "
import sys,json,re
n=[r['name'] for r in json.load(sys.stdin)['results']]
newer=[x for x in n if re.fullmatch(r'12\.([4-9]|[1-9]\d)\.\d{8}-\d{6}|1[3-9]\.\d+\.\d{8}-\d{6}',x) or (re.fullmatch(r'12\.3\.\d{8}-\d{6}',x) and x>'12.3.20261023-013714')]
print('NEWER_TAGS', newer if newer else 'none')"
#   MUST print `NEWER_TAGS none`. A later 12.3 respin or a 12.4+ tag = STOP, refresh. FAILS (prints a list) on a respin.

# --- G1b (ABORT): etcd quiet. The backup_gate drives every Longhorn volume's IO and the first boot rewrites a SQLite DB;
#     do not start on an unstable control plane. Prometheus via port-forward (the window's shared instrument).
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9091:9090 >/dev/null 2>&1 & PPF=$!; sleep 3
q(){ curl -s -G localhost:9091/api/v1/query --data-urlencode "query=$1" | python3 -c "
import sys,json;r=json.load(sys.stdin)['data']['result'];print(r[0]['value'][1] if r else 'EMPTY')"; }
q 'count(etcd_server_has_leader==1)'                                                  # MUST be 3
q 'max(increase(etcd_server_leader_changes_seen_total[24h]))'                         # MUST be < 6 (docs/sops/talos-upgrade.md etcd gates)
q 'max(histogram_quantile(0.99,rate(etcd_disk_backend_commit_duration_seconds_bucket[1h])))'   # RECORD; STOP if > 0.25
kill $PPF 2>/dev/null
#   FAIL prints `EMPTY` (target not scraped: an empty result is a FAIL, never a pass), a count other than 3, >= 6 leader
#   changes, or commit p99 > 250 ms. Measured 2026-10-23: 3 / 2 / 0.083 s (above the 50 ms bar that gates node rolls in
#   the talos SOP - an app upgrade is judged at 250 ms; if you are also doing a node/etcd job today, use 50 ms).
#   RECORD the three numbers in the run record and obtain the operator's EXPLICIT acceptance of the p99 value before
#   step 1 (a number above 50 ms is accepted knowingly, not by default).

# --- G2 (ABORT): plugin inventory unchanged; username collision absent; the 12.x plugin build is still published.
POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n media "$POD" -- sh -c 'ls /config/plugins'
#   Expected: configurations  TubeArchivistMetadata_1.4.4.0 . Any OTHER repository plugin => STOP; check its 12.x build.
JF_KEY=$(kubectl -n media get secret media-manager-tokens -o jsonpath='{.data.JELLYFIN_API_KEY}' | base64 -d)
kubectl port-forward -n media svc/jellyfin 8097:8096 >/dev/null 2>&1 & PF=$!; sleep 3
AUTH="Authorization: MediaBrowser Token=\"$JF_KEY\""
curl -s -H "$AUTH" http://localhost:8097/Users | python3 -c "
import sys,json;n=[u['Name'] for u in json.load(sys.stdin)];print('USERS',len(n),'DISTINCT_CASEFOLDED',len({x.lower() for x in n}))"
#   MUST print equal numbers. FAILS (numbers differ) if two names differ only by case (12.0 breaking change).
curl -sL https://github.com/tubearchivist/tubearchivist-jf-plugin/raw/master/manifest.json \
  | python3 -c "import sys,json;v=json.load(sys.stdin)[0]['versions'][0];print(v['version'],v['targetAbi'])"
#   MUST print 1.5.0.0 12.0.0.0 (or newer with targetAbi 12.x).

# --- G3 (ABORT): no in-repo legacy-auth caller.
kubectl get configmap -n media library-tools-scripts -o json | python3 -c \
 "import sys,json;print('legacy X-Emby-Token call sites:', sum(v.count('X-Emby-Token') for v in json.load(sys.stdin)['data'].values()))"
#   MUST print 0 (measured 0 on 2026-10-23). Non-zero => STOP.

# --- Baselines (record every number; all measured against the RUNNING 10.11.11 on the migrated volume) ---
kubectl get pod -n media "$POD" -o jsonpath='{.spec.nodeName}{"\n"}'      # record the node (i915 slot owner)
kubectl get pod -n media "$POD" -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
#   expect ...@sha256:aefb67e6a7ff1debdd154a78a7bbb780fd0c873d8639210a7f6a2016ad2b35db (rollback digest, measured 2026-10-23)
kubectl exec -n media "$POD" -- sh -c 'ls -la /config/data/jellyfin.db; df /config | tail -1; grep -o "<EnableLegacyAuthorization>[^<]*" /config/config/system.xml'
#   expect source /dev/longhorn/jellyfin-config-rwo (NOT an nfs host) and <EnableLegacyAuthorization>true
kubectl exec -n media "$POD" -- sh -c 'cd /config/config && for f in system encoding network branding; do echo "== $f"; cat $f.xml; done' > "$S/config-xml-pre.txt"
#   (config XML holds no secrets; kept in $S, never committed - section 4.1 diffs it)
kubectl exec -n media "$POD" -- sh -c '/usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -encoders 2>/dev/null | grep -c vaapi'
#   expect 7 (measured 2026-10-23). FULL PATH - bare `ffmpeg` is not on PATH and returns 0.
kubectl exec -n media "$POD" -- sh -c \
  '/usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -f lavfi -i testsrc=size=320x240:rate=5:duration=1 -vf format=nv12,hwupload \
     -c:v h264_vaapi -f null - && echo VAAPI_ENCODE_OK'
kubectl exec -n media "$POD" -- sh -c 'grep -io "<HardwareAccelerationType>[^<]*\|<EncoderPreset>[^<]*" /config/config/encoding.xml'
#   expect <HardwareAccelerationType>qsv and <EncoderPreset>medium (measured 2026-10-23)
RESTART_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "RESTART_TS=$RESTART_TS"
# Alert baseline for 4.7 (alertname namespace state, sorted, Watchdog/InfoInhibitor excluded):
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9091:9090 >/dev/null 2>&1 & PPF=$!; sleep 3
curl -s http://localhost:9091/api/v1/alerts | python3 -c "
import sys, json
rows=sorted({(a['labels'].get('alertname'),a['labels'].get('namespace'),a['state']) for a in json.load(sys.stdin)['data']['alerts'] if a['labels'].get('alertname') not in ('Watchdog','InfoInhibitor')})
[print(*r) for r in rows]" | tee "$S/alerts-pre.txt"; wc -l < "$S/alerts-pre.txt"; kill $PPF 2>/dev/null
#   An EMPTY file is legitimate only if Prometheus really has none: confirm the query itself worked (the Watchdog alert
#   is always firing): `curl -s localhost:9091/api/v1/alerts | grep -c Watchdog` must be >= 1 or the baseline is unreadable.
curl -s -H "$AUTH" http://localhost:8097/Items/Counts | python3 -m json.tool | tee "$S/jf-counts-pre.json"
# Watch-state baseline for HarmonizeConflictingUserData (section 4.2b) - per user, played + favorite counts:
curl -s -H "$AUTH" http://localhost:8097/Users | python3 -c "
import sys,json;[print(u['Id'],u['Name']) for u in json.load(sys.stdin)]" | tee "$S/jf-users.txt"
# NB: never name the loop variable UID - it is a read-only special in zsh AND bash.
while read -r U_ID UNAME; do
  P=$(curl -s -H "$AUTH" "http://localhost:8097/Items?userId=$U_ID&Recursive=true&IsPlayed=true&Limit=0" | python3 -c "import sys,json;print(json.load(sys.stdin)['TotalRecordCount'])")
  F=$(curl -s -H "$AUTH" "http://localhost:8097/Items?userId=$U_ID&Recursive=true&IsFavorite=true&Limit=0" | python3 -c "import sys,json;print(json.load(sys.stdin)['TotalRecordCount'])")
  echo "$UNAME played=$P favorite=$F"
done < "$S/jf-users.txt" | tee "$S/jf-userdata-pre.txt"
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
  "comment":"jellyfin 10.11.11 -> 12.3 major upgrade; auto-expires 4h"}'
#   record the returned silenceID
runbooks/update-marker.sh add jellyfin media 4 "jellyfin 10.11.11->12.3"
```

## 3. Steps

All steps run against the post-migration layout. `$S`, `$POD`, `$AUTH`, `$PF` come from section 2.2 (re-create the
port-forward after any pod restart).

1. **backup_gate - FIRST mutating action, on the untouched 10.11.11 state, on the NEW volume.**
   ```bash
   GATE_START=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "GATE_START=$GATE_START"
   kubectl create job --from=cronjob/daily-backup-all-volumes "pre-jellyfin-12-3-$(date +%Y%m%d-%H%M)" -n storage
   # wait (~12 min - it backs up every volume), then:
   kubectl get backups.longhorn.io -n storage -l backup-volume=jellyfin-config-rwo \
     --sort-by=.metadata.creationTimestamp \
     -o custom-columns=NAME:.metadata.name,STATE:.status.state,CREATED:.metadata.creationTimestamp | tail -2
   .venv/bin/python3 runbooks/longhorn-backup-age.py jellyfin-config-rwo --max-hours 1
   ```
   PASS = newest row is `Completed` with CREATED > GATE_START AND the helper prints `FRESH`. Record the Backup NAME -
   section 5 restores from it. FAIL = no new Completed CR, or STALE, or **no CR at all for the label** (which is what a
   mis-typed old volume name or a volume outside the recurring-job group would give) => STOP, nothing has changed yet.
   Do NOT satisfy this gate with a backup of `jellyfin-config` (the detached old RWX volume): it holds the PRE-12-plan
   state of last week and restoring it would silently discard everything since the migration.
   Because the backup is taken BEFORE the plugin removal, a restore brings back a working 10.11.11 including
   TubeArchivistMetadata 1.4.4.

2. **Uninstall TubeArchivistMetadata 1.4.4.0** (upstream 1.2 item 2). App state on the PVC; no GitOps path exists. Copy
   its settings aside (same `.bak` convention already used in that directory), then uninstall via the API:
   ```bash
   kubectl exec -n media "$POD" -- sh -c 'cp -p /config/plugins/configurations/Jellyfin.Plugin.TubeArchivistMetadata.xml /config/plugins/configurations/Jellyfin.Plugin.TubeArchivistMetadata.xml.pre12.bak'
   curl -s -o /dev/null -w 'uninstall http=%{http_code}\n' -X DELETE -H "$AUTH" \
     "http://localhost:8097/Plugins/dc97d0c628b04242afb45833ae1b3715/1.4.4.0"
   #   expect 204
   curl -s -H "$AUTH" http://localhost:8097/Plugins | python3 -c \
    "import sys,json;[print(p['Name'],p['Version'],p['Status']) for p in json.load(sys.stdin) if 'Tube' in p['Name']]"
   kubectl exec -n media "$POD" -- sh -c 'ls /config/plugins; cat /config/plugins/TubeArchivistMetadata_1.4.4.0/meta.json 2>/dev/null | grep -io "\"status\":\"[a-z]*\""'
   ```
   PASS = either the plugin is absent from `/Plugins` and the directory is gone, OR it shows `Deleted` (matched
   case-insensitively; Jellyfin purges it at next startup, before it would be loaded). Still `Active` => STOP (do not
   bump with the 10.11-ABI plugin live). Do NOT `rm -rf` the directory in-pod.

3. **Edit `kubernetes/apps/media/jellyfin/app/helmrelease.yaml`** - tag bump + disable remediation for the attempt (a
   slow first-boot migration must not be "remediated" mid-migration). Dry-tested with BSD sed on a scratch copy of the
   CURRENT file 2026-10-23 (post-migration `existingClaim` line is not matched by either expression):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' \
     -e 's/^\([[:space:]]*tag:[[:space:]]*\)10\.11\.11\.20260606-153911$/\112.3.20261023-013714/' \
     -e '/^  upgrade:/,/^  uninstall:/{s/^\([[:space:]]*retries:[[:space:]]*\)1$/\10/;s/^\([[:space:]]*remediateLastFailure:[[:space:]]*\)true$/\1false/;}' \
     kubernetes/apps/media/jellyfin/app/helmrelease.yaml
   git diff kubernetes/apps/media/jellyfin/app/helmrelease.yaml
   ```
   The diff MUST be exactly these three changed lines (scratch-copy result, 2026-10-23):
   ```
   <       retries: 1
   <       remediateLastFailure: true
   >       retries: 0
   >       remediateLastFailure: false
   <       tag: 10.11.11.20260606-153911
   >       tag: 12.3.20261023-013714
   ```
   (`install.remediation.retries: 1` sits above the `upgrade:` block and is untouched.) Nothing else in this diff. If
   `git diff` shows other hunks (e.g. a chart-version bump from PR 410 that landed meanwhile), they are not yours:
   `git commit --only` below takes the whole file, so STOP and ask - never commit someone else's hunk under this subject.

4. **Commit + push** (shared worktree; message file in `$S`, not `/tmp`):
   ```bash
   printf '%s\n' "feat(jellyfin): 10.11.11.20260606-153911 -> 12.3.20261023-013714 (upstream GA major)" "" \
     "Plan jellyfin-12.2.20261005 (refreshed to 12.3). Remediation disabled for the forward-only first-boot" \
     "migration; restored after verification." > "$S/msg-bump.txt"
   git commit --only kubernetes/apps/media/jellyfin/app/helmrelease.yaml -F "$S/msg-bump.txt"
   git log -1 --format=%s     # MUST be the subject above (message-swap race)
   git show --stat HEAD       # exactly one file
   git push
   ```

5. **Watch the rollout and the migration** - no manual `flux reconcile` (webhook).
   ```bash
   flux get helmrelease -n media jellyfin
   kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -w
   kubectl logs -n media -l app.kubernetes.io/name=jellyfin -f | grep -iE 'migrat|Harmoniz|EncoderPreset|LegacyAuthorization|Startup complete|critical|error|fail'
   ```
   Migrations run before the main host starts while a SetupServer answers `/health` (200) and `/System/Info/Public`
   (503). **Pod Ready / HR Ready arrive while the migration is still running** - they prove nothing. End this step only
   on `Startup complete` in the log AND `/System/Info/Public` -> 200 with `Version` 12.3.x. Do NOT edit probes or kill the
   pod mid-migration. A `LogCritical` "will not start an existing server with an empty database" means the mount/DB is
   wrong - go to section 5, do not "start over". On RWO (Recreate) there is no Multi-Attach risk; if the new pod is
   `ContainerCreating` for > 5 min, read the events before touching anything (the old pod must have released the volume).
   ```bash
   kill $PF 2>/dev/null; kubectl port-forward -n media svc/jellyfin 8097:8096 >/dev/null 2>&1 & PF=$!; sleep 3
   curl -s -o /dev/null -w 'public-info http=%{http_code}\n' http://localhost:8097/System/Info/Public   # 503 = migrating
   POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
   kubectl exec -n media "$POD" -- sh -c 'ls -la /config/data/SQLiteBackups /config/data 2>/dev/null | grep -iE "jellyfin|backup"'
   #   evidence only: the server's own pre-migration copy (JellyfinMigrationBackup). Not the backup_gate; its absence is not a stop.
   ```

6. **Mandatory full library scan** (upstream requirement):
   ```bash
   curl -s -o /dev/null -w 'refresh http=%{http_code}\n' -X POST -H "$AUTH" http://localhost:8097/Library/Refresh
   ```
   Wait for 4.5 Completed before evaluating 4.2. (`$AUTH` still works: the API key is a DB row that migrated; if it
   401s with the modern header the migration lost the key - that is a 4.3 failure, go to section 5.)

7. **Install TubeArchivistMetadata 1.5.0.0** from the already-configured repository, then restart Jellyfin in-process:
   ```bash
   curl -s -o /dev/null -w 'install http=%{http_code}\n' -X POST -H "$AUTH" \
     "http://localhost:8097/Packages/Installed/TubeArchivistMetadata?assemblyGuid=dc97d0c6-28b0-4242-afb4-5833ae1b3715&version=1.5.0.0"
   #   expect 204. Wait until 4.5 shows the scan Completed, THEN:
   curl -s -o /dev/null -w 'restart http=%{http_code}\n' -X POST -H "$AUTH" http://localhost:8097/System/Restart
   sleep 60; kill $PF 2>/dev/null; kubectl port-forward -n media svc/jellyfin 8097:8096 >/dev/null 2>&1 & PF=$!; sleep 3
   curl -s -H "$AUTH" http://localhost:8097/Plugins | python3 -c \
    "import sys,json;[print(p['Name'],p['Version'],p['Status']) for p in json.load(sys.stdin) if 'Tube' in p['Name']]"
   #   PASS: "TubeArchivist Metadata 1.5.0.0 Active". FAIL modes print 1.4.4.0, NotSupported, Malfunctioned, or nothing.
   #   FALLBACK (in-process restart may return 204 yet not reload plugin assemblies): delete the pod - the PVC survives
   #   and the 12.3 image is already on the node, so this is a plain restart, not a re-migration:
   #     kubectl delete pod -n media -l app.kubernetes.io/name=jellyfin
   #     kubectl wait -n media --for=condition=Ready pod -l app.kubernetes.io/name=jellyfin --timeout=5m
   #   then re-open the port-forward and re-run the /Plugins check. Do NOT edit the HelmRelease for this. A failure here
   #   is NOT a rollback trigger on its own - record it and tell the operator.
   kubectl exec -n media "$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')" \
     -- sh -c 'ls -la /config/plugins/configurations/ | grep -i tubearchivist'
   #   the settings XML must still be present; if missing, restore it from the .pre12.bak copy and restart once more.
   ```

8. Run section 4. **Gate PW-1 (4.3) needs the Jellyfin admin password.** If the operator is not at the keyboard when
   the run reaches it, do not improvise: print exactly `WAITING for admin password at gate PW-1`, leave every other
   result recorded, leave remediation at `retries: 0` (step 9 has NOT run) and the silence + marker in place, and stop.
   The run record stays open. Resume = re-open the port-forward and run 4.3 only. The 4 h silence expires on its own: if the wait outlasts it,
   RE-CREATE it on resume (same POST as section 2.2, new `endsAt`) and record the new silenceID for step 9.

9. **Only after PW-1 PASSED and 4.1-4.7 are green - on success**: restore remediation, commit, push; drop silence;
   clear marker.
   ```bash
   sed -i '' -e '/^  upgrade:/,/^  uninstall:/{s/^\([[:space:]]*retries:[[:space:]]*\)0$/\11/;s/^\([[:space:]]*remediateLastFailure:[[:space:]]*\)false$/\1true/;}' \
     kubernetes/apps/media/jellyfin/app/helmrelease.yaml
   git diff kubernetes/apps/media/jellyfin/app/helmrelease.yaml   # exactly retries 0->1, remediateLastFailure false->true
   printf '%s\n' "chore(jellyfin): restore Helm upgrade remediation after 12.3 migration" > "$S/msg-restore.txt"
   git commit --only kubernetes/apps/media/jellyfin/app/helmrelease.yaml -F "$S/msg-restore.txt"
   git log -1 --format=%s; git show --stat HEAD; git push
   curl -s -X DELETE localhost:9093/api/v2/silence/<silenceID>
   runbooks/update-marker.sh clear jellyfin
   kill $PF $AMPF 2>/dev/null
   ```
   Then: this plan -> executed and the file retired per the plans README; record the post-upgrade scan on `F-3a72570a`
   (4.8) and close `F-fc5e2913` with the commit sha. The old RWX volume `jellyfin-config` is still on its 14-day retention
   clock from the migration plan; its retirement is a SEPARATE operator-approved plan.

## 4. Verification

### 4.1 Floor (shape - necessary, not sufficient)

```bash
POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
kubectl get helmrelease -n media jellyfin -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pod -n media "$POD" -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
#   expect ...@sha256:2038fe038ab3876a80f6e7b7e0aef6607b032c7dc0c9b3ad3296d0b2eba3bbb5 (FAILS on the old @sha256:aefb67e6... digest)
curl -s http://localhost:8097/System/Info/Public | python3 -c "import sys,json;print(json.load(sys.stdin)['Version'])"
#   expect 12.3.x ; 10.11.x = rollout did not happen; HTTP 503 = still migrating
kubectl exec -n media "$POD" -- sh -c 'grep -io "<EnableLegacyAuthorization>[^<]*" /config/config/system.xml'
#   expect false - proves the legacy-auth migration ran
kubectl exec -n media "$POD" -- sh -c 'cd /config/config && for f in system encoding network branding; do echo "== $f"; cat $f.xml; done' > "$S/config-xml-post.txt"
diff "$S/config-xml-pre.txt" "$S/config-xml-post.txt"
#   EXPECTED differences only: EnableLegacyAuthorization true->false, version/migration stamps and encoder-option
#   rewrites in encoding.xml. network.xml and branding.xml MUST be identical (a diff there is unexplained: read it,
#   and treat a changed BaseUrl / port / allowed-hosts / PublishedServerUrl value as a rollback-class finding).
kubectl exec -n media "$POD" -- sh -c 'df /config | tail -1'      # still /dev/longhorn/jellyfin-config-rwo, not NFS
```

CONTROL: metric kube_deployment_status_replicas_available - PromQL `kube_deployment_status_replicas_available{namespace="media",deployment="jellyfin"}` must return one series reading 1 after the rollout (measured 1 on 2026-10-23, kube-state-metrics); a value of 0 = no serving pod, and an EMPTY result = kube-state-metrics not scraping / wrong label (verified 2026-10-23: the same query with a nonexistent deployment returns `[]`), so empty is a FAIL of the gate, never a pass.
CONTROL: metric kube_pod_container_status_restarts_total - PromQL `kube_pod_container_status_restarts_total{namespace="media",container="jellyfin"}` must not increase between `Startup complete` and the end of section 4 (compare per pod name; the plugin-fallback pod delete in step 7 starts a NEW pod whose counter restarts at 0). An increase = crash/liveness kill during scan; an empty result = unreadable, treat as FAIL. Query via `kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9091:9090` then `curl -s -G localhost:9091/api/v1/query --data-urlencode 'query=<PromQL>'`.

### 4.2 CONTENTS ASSERTION - the library survived

CONTENTS ASSERTION: after the mandatory scan has Completed (4.5), every non-zero counter of `/Items/Counts` is >= its
section 2.2 baseline (`$S/jf-counts-pre.json`, recorded on 10.11.11 at run time) - measured by Jellyfin's own API with
the modern header.

```bash
curl -s -H "$AUTH" http://localhost:8097/Items/Counts > "$S/jf-counts-post.json"
S="$S" python3 - <<'EOF'
import json,os
s=os.environ['S']
pre=json.load(open(s+'/jf-counts-pre.json')); post=json.load(open(s+'/jf-counts-post.json'))
bad={k:(v,post.get(k)) for k,v in pre.items() if v>0 and (post.get(k) or 0)<v}
print('COUNTS_OK' if not bad else f'COUNTS_SHORT {bad}')
EOF
```
FAIL prints `COUNTS_SHORT {...}` (e.g. a dropped Movie count from un-restored alternate versions, or all zeros from a
schema-only migration). Evaluated mid-scan it is expected to be low - only read it after 4.5. A persistent shortfall
must be explained item-by-item before acceptance.

### 4.2b CONTENTS ASSERTION - per-user watch state survived HarmonizeConflictingUserData

CONTENTS ASSERTION: for every user, `played` and `favorite` totals are >= the baseline (`$S/jf-userdata-pre.txt`).
```bash
# NB: never name the loop variable UID - it is a read-only special in zsh AND bash.
while read -r U_ID UNAME; do
  P=$(curl -s -H "$AUTH" "http://localhost:8097/Items?userId=$U_ID&Recursive=true&IsPlayed=true&Limit=0" | python3 -c "import sys,json;print(json.load(sys.stdin)['TotalRecordCount'])")
  F=$(curl -s -H "$AUTH" "http://localhost:8097/Items?userId=$U_ID&Recursive=true&IsFavorite=true&Limit=0" | python3 -c "import sys,json;print(json.load(sys.stdin)['TotalRecordCount'])")
  echo "$UNAME played=$P favorite=$F"
done < "$S/jf-users.txt" | tee "$S/jf-userdata-post.txt"
diff "$S/jf-userdata-pre.txt" "$S/jf-userdata-post.txt" && echo USERDATA_IDENTICAL
```
A small upward drift is plausible; a DROP for any user is a FAIL - the watch history is the data the household notices.
A Python traceback (KeyError TotalRecordCount) = the call 401'd; fix the header, do not pass.

### 4.3 CONTENTS ASSERTION - real login + auth paths (GATE PW-1: needs the admin password)

The non-password half runs unattended first:
```bash
curl -s -o /dev/null -w 'apikey-modern http=%{http_code}\n' -H "$AUTH" http://localhost:8097/System/Info
curl -s -o /dev/null -w 'legacy-header http=%{http_code}\n' -H "X-Emby-Token: $JF_KEY" http://localhost:8097/System/Info
```
PASS: modern 200 and legacy **401**. Legacy 200 = the migration did not flip the flag: investigate; do not leave legacy
auth on.

The password half (**PW-1**). No SOPS secret holds a Jellyfin admin password; the operator provides it through the
coordinator. The agent prints `WAITING for admin password at gate PW-1` and stops until it is supplied (section 3 step 8).
Handling rules: the password never appears in a command line (argv is visible in `ps`), a commit, a log, the plan
file, a chat transcript or `$S`. Supply it through a hidden prompt in a shell the operator controls, or have the
coordinator export it into a single child process environment for the one call below and unset it immediately:
```bash
# zsh-safe prompts (the window runs zsh on macOS: bash's `read -p` dies there with "-p: no coprocess", the password is
# never read and the call below would send an EMPTY password = false LOGIN_FAIL). Dry-tested 2026-10-23 with
# `printf 'alice\ndummy-pw\n' | zsh -c <this block>`: python saw len_user=5 len_pw=8. Under bash use `bash -c` with -p form instead.
read -r "JF_USER?Jellyfin admin user: "
read -rs "JF_PW?Jellyfin admin pw (not stored): "; echo
[ -n "$JF_USER" ] && [ -n "$JF_PW" ] || { echo "EMPTY_INPUT: not attempting login"; unset JF_PW JF_USER; }
JF_USER="$JF_USER" JF_PW="$JF_PW" python3 - <<'EOF'
import os, json, urllib.request
req = urllib.request.Request("http://localhost:8097/Users/AuthenticateByName",
    data=json.dumps({"Username": os.environ["JF_USER"], "Pw": os.environ["JF_PW"]}).encode(),
    headers={"Content-Type": "application/json",
             "Authorization": 'MediaBrowser Client="plan-verify", Device="cli", DeviceId="plan-verify", Version="1.0"'})
try:
    d = json.load(urllib.request.urlopen(req, timeout=20))
    print("LOGIN_OK" if d.get("AccessToken") else "LOGIN_FAIL")
except Exception as e:
    print("LOGIN_FAIL", type(e).__name__)      # never print the response body or the password
EOF
unset JF_PW JF_USER
```
PASS: `LOGIN_OK`. An empty prompt result prints `EMPTY_INPUT` and counts as NOT RUN (never as pass or fail). FAIL prints `LOGIN_FAIL ...` (401 raises HTTPError, so a wrong password or a broken auth migration can
not read as a pass). Three consecutive `LOGIN_FAIL` with the operator confirming the password = section 5; a single one is
a typo. Until PW-1 has printed `LOGIN_OK` the plan is NOT executed and step 9 does not run.

### 4.4 CONTENTS ASSERTION - hardware transcode on the shared iGPU

```bash
kubectl exec -n media "$POD" -- sh -c '/usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -encoders 2>/dev/null | grep -c vaapi'   # >= 7
kubectl exec -n media "$POD" -- sh -c \
  '/usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -f lavfi -i testsrc=size=320x240:rate=5:duration=1 -vf format=nv12,hwupload \
     -c:v h264_vaapi -f null - && echo VAAPI_ENCODE_OK'
# QSV init test - the CONFIGURED path is qsv, so VAAPI proof alone is insufficient. qsv derives from the vaapi device:
kubectl exec -n media "$POD" -- sh -c \
  '/usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -init_hw_device qsv=qs@va -f lavfi -i testsrc=size=320x240:rate=5:duration=1 \
     -vf format=nv12,hwupload=extra_hw_frames=64 -c:v h264_qsv -f null - && echo QSV_ENCODE_OK'
kubectl exec -n media "$POD" -- sh -c 'grep -io "<HardwareAccelerationType>[^<]*\|<EncoderPreset>[^<]*" /config/config/encoding.xml'
kubectl get pod -n media "$POD" -o jsonpath='{.spec.containers[0].resources.limits}{"\n"}'     # still carries gpu.intel.com/i915:1
```
PASS: >= 7, `VAAPI_ENCODE_OK` AND `QSV_ENCODE_OK` both printed (libva "info" lines are noise; gate on the OK token - a
broken qsv path prints an ffmpeg error such as "Encoder not found" / "Error initializing" / "Device creation failed"
and no OK line), and encoding.xml still reads `<HardwareAccelerationType>qsv` + `<EncoderPreset>medium` (compare against
the section 2.2 capture - the server is configured for **qsv**, not vaapi, despite the VAAPI env vars). FAIL: count 0,
either OK line missing, or acceleration type changed (e.g. `none`) by the `FixNullEncoderPreset` migration. The i915
plugin claim: if the pod is `Pending` with `Insufficient gpu.intel.com/i915`, another claimant took the node's slots -
that is the igpu interference in section 6, not a Jellyfin fault.

### 4.5 The full scan actually ran

```bash
curl -s -H "$AUTH" http://localhost:8097/ScheduledTasks | python3 -c "
import sys,json
for t in json.load(sys.stdin):
    if t['Name']=='Scan Media Library':
        r=t.get('LastExecutionResult') or {}; print(t['State'], r.get('Status'), r.get('EndTimeUtc'))"
```
PASS: `Idle Completed <EndTimeUtc after RESTART_TS>`. The pre-change value is the OLD scan, not evidence. If the scan
outlasts the window, the window may close on 4.1/4.3(non-password)/4.4/4.6 green with 4.2/4.2b/4.5 handed to the
same-day post-window check; the plan is not `executed` until they and PW-1 pass. Also record
`kubectl logs -n media deploy/jellyfin | grep -c 'database is locked'` (the RWO migration's motivating symptom) - evidence,
not a gate.

### 4.6 Consumers across the auth change

```bash
J=coverage-post123-$(date +%H%M)
kubectl create job -n media --from=cronjob/media-metadata-coverage "$J"
kubectl wait -n media job/"$J" --for=condition=complete --timeout=10m
kubectl logs -n media job/"$J" | python3 -c "
import sys,json
ev=[json.loads(l) for l in sys.stdin if l.startswith('{')]
jf=[e for e in ev if e.get('event')=='coverage-jellyfin']
err=[e.get('code') for e in ev if e.get('event')=='coverage-http-error']
print('coverage-jellyfin total:', jf[0]['total'] if jf else 'MISSING', '| http errors:', err)"
```
PASS: total > 0 (baseline 548 on 2026-10-07; re-read the last pre-change run) and no 401. FAIL prints `MISSING` or `[401]`.
Home Assistant (via ha-agent/hactl): Jellyfin entities not `unavailable` = expected green; media-browser playback 401 =
**expected casualty** (1.4), recorded, not a rollback trigger. Music Assistant: browse returns items AND a track plays =
expected green; a 401 needs a real look but is a client-side remedy, not a rollback trigger on its own.

### 4.7 External reachability + no new alerts

```bash
SECRET_DOMAIN=$(kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w 'edge http=%{http_code}\n' "https://jellyfin.${SECRET_DOMAIN}/System/Ping"   # 200 via envoy-external
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9091:9090 >/dev/null 2>&1 & PPF=$!; sleep 3
alerts(){ curl -s http://localhost:9091/api/v1/alerts | python3 -c "
import sys, json
rows=sorted({(a['labels'].get('alertname'),a['labels'].get('namespace'),a['state']) for a in json.load(sys.stdin)['data']['alerts'] if a['labels'].get('alertname') not in ('Watchdog','InfoInhibitor')})
[print(*r) for r in rows]"; }
alerts > "$S/alerts-post.txt"
echo "NEW alerts (in post, not in pre):"; comm -13 "$S/alerts-pre.txt" "$S/alerts-post.txt"
# NEGATIVE CONTROL: the comparison must be able to fail. Against a baseline with one row removed it must print that row:
sed '1d' "$S/alerts-post.txt" > "$S/alerts-ctl.txt"; comm -23 "$S/alerts-post.txt" "$S/alerts-ctl.txt"
#   (skip the control only if alerts-post.txt is empty)
kill $PPF 2>/dev/null
```
PASS: edge 200 AND the "NEW alerts" list is empty (the control prints exactly the row that was removed, proving `comm`
sees differences; an empty control with a non-empty post file = broken comparison, not a pass). A `Pending`->`Firing`
change of an alert already in the baseline shows as new (state is part of the row) - read it before counting it against
the change. Our own silence suppresses notifications, not `/api/v1/alerts`, so a new media alert still prints here.

### 4.8 Security finding follow-through (F-3a72570a)

```bash
trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed docker.io/jellyfin/jellyfin:12.3.20261023-013714
```
Record the outcome on the finding (`runbooks/policy-cli.py finding detail F-3a72570a ...`), never in this file.
Already-newest residue is AR-029 territory, not a reason to hold.

## 5. Rollback (backup-restore - a tag revert alone is NOT a rollback)

Triggers: 4.1/4.2/4.2b/4.3 (incl. PW-1) FAIL that cannot be explained, migration crash-loop, or `LogCritical` on
startup. NOT triggers: TubeArchivist 1.5.0 install failure (step 7), HA media-browser 401 (1.4).

The restore source is the **backup_gate Backup CR of volume `jellyfin-config-rwo`** (name recorded in step 1). It was
taken from the running 10.11.11 server on the migrated volume, so it restores config + DB + plugin 1.4.4 exactly as they
were before step 2. The detached old RWX volume `jellyfin-config` is NOT used: it predates the migration plan's cutover.

```bash
cd /Users/mu/code/cberg-home-nextgen
# 0) Freeze Flux FIRST so neither the revert push nor Helm remediation starts 10.11.11 against the migrated DB, and
#    nothing re-applies PV/PVC mid-restore:
flux suspend kustomization -n media jellyfin
flux suspend helmrelease -n media jellyfin
# 1) Revert in git (keeps git honest; inert while suspended). Newest first: if step 9 already ran there are TWO commits.
git log --oneline -5 -- kubernetes/apps/media/jellyfin/app/helmrelease.yaml
git revert --no-edit <restore-remediation-commit, if it exists>     # then:
git revert --no-edit <bump-commit>
git log -1 --format=%s; git show --stat HEAD
git push
# 2) Free the volume:
kubectl scale deploy -n media jellyfin --replicas=0
kubectl wait -n media --for=delete pod -l app.kubernetes.io/name=jellyfin --timeout=5m
```
(`kubectl scale` holds only because the HelmRelease is suspended; Flux is not fighting it.)

3) Restore `jellyfin-config-rwo` from the backup_gate Backup CR. `spec.csi.volumeHandle` is immutable and
`pv/jellyfin-config-rwo` + `pvc/jellyfin-config-rwo` are git-tracked
(`kubernetes/apps/media/jellyfin/app/config-pv-rwo.yaml`, `config-pvc-rwo.yaml`, created by the migration plan), so the
restore goes to a NEW volume name and git is re-pointed:

- (a) Longhorn UI (`kubectl port-forward -n storage svc/longhorn-frontend 8080:80`) -> Backup -> `jellyfin-config-rwo` ->
  <gate backup> -> Restore -> name `R=jellyfin-config-rwo-r$(date +%Y%m%d)`, accessMode **rwo**, replicas 2 (match the
  live volume). Wait until
  `kubectl get volumes.longhorn.io -n storage $R -o jsonpath='{.status.state} {.status.restoreRequired}'` prints
  `detached false`. Then keep it in the nightly chain:
  `kubectl label volumes.longhorn.io -n storage $R recurring-job-group.longhorn.io/default=enabled`.
- (b) In git (`--only` these two files, do not push yet): `config-pv-rwo.yaml` metadata.name and csi.volumeHandle -> `$R`
  (keep RWO, 25Gi, longhorn-static, Retain, ext4, numberOfReplicas "2", staleReplicaTimeout "30");
  `config-pvc-rwo.yaml` spec.volumeName -> `$R` (**PVC NAME STAYS `jellyfin-config-rwo`**, so the HelmRelease's
  `existingClaim` needs no edit).
- (c) Storage-safety pre-flight, then delete the OLD PVC + PV (Longhorn, Retain - the old Longhorn volume survives for
  forensics). `pvc/jellyfin-media` and `pvc/jellyfin-config` (the retained RWX claim) are never named:
  ```bash
  PV=$(kubectl -n media get pvc jellyfin-config-rwo -o jsonpath='{.spec.volumeName}')
  kubectl get pv "$PV" -o jsonpath='{.spec.csi.driver} {.spec.persistentVolumeReclaimPolicy} {.spec.csi.volumeHandle}{"\n"}'
  #   MUST print: driver.longhorn.io Retain jellyfin-config-rwo - anything else: STOP.
  kubectl -n media delete pvc jellyfin-config-rwo
  kubectl delete pv "$PV"
  ```
- (d) Push (b), then resume:
  ```bash
  git push
  flux resume kustomization -n media jellyfin
  kubectl -n media get pvc jellyfin-config-rwo -o jsonpath='{.status.phase} {.spec.volumeName}{"\n"}'   # Bound jellyfin-config-rwo-r<date>
  flux resume helmrelease -n media jellyfin
  flux reconcile helmrelease -n media jellyfin --force    # HR was suspended; force a fresh upgrade to the reverted values (replicas back to 1)
  ```
- (e) The hand-applied Longhorn Volume manifest `longhorn-volume-rwo.yaml` still describes the original
  `jellyfin-config-rwo`; add a one-line comment pointing at `$R` in the same commit as (b) so the repo does not lie.
- (f) Restore proof is the confirmation block below (the restored DB opens, `EnableLegacyAuthorization` reads true, counts
  match). If it does not: the Longhorn restore of the gate backup is itself broken - STOP and use the migration plan's
  retained old volume + its own R3 path (`docs/sops/backup.md`), which loses everything since the migration cutover.

Confirm we are actually back - by digest and contents, not Ready:
```bash
POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
kubectl get pod -n media "$POD" -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
#   MUST be ...@sha256:aefb67e6a7ff1debdd154a78a7bbb780fd0c873d8639210a7f6a2016ad2b35db
kubectl exec -n media "$POD" -- sh -c 'grep -o "<EnableLegacyAuthorization>[^<]*" /config/config/system.xml; ls /config/plugins; df /config | tail -1'
#   MUST be true (pre-migration DB/config), TubeArchivistMetadata_1.4.4.0 present (the backup predates step 2), and
#   source /dev/longhorn/<R>. `false` = you are looking at the migrated volume, not the restore.
kill $PF 2>/dev/null; kubectl port-forward -n media svc/jellyfin 8097:8096 >/dev/null 2>&1 & PF=$!; sleep 3   # the old one died with the old pod
curl -s -H "$AUTH" http://localhost:8097/Items/Counts      # must match $S/jf-counts-pre.json
```
Ensure remediation in git is back to `retries: 1` / `remediateLastFailure: true` (the revert restores it). Clear silence +
marker. Tell the window agent the Longhorn volume behind `pvc/jellyfin-config-rwo` is now `$R` (backup-age checks,
`backup-volume=` labels and any later plan must use `$R`).

## 6. Interference notes

- **Ordering (operator decision 2026-10-23)**: `jellyfin-config-rwo-migration` FIRST (`depends_on`). Do not interleave: this
  plan starts only after the migration's section 4 gates are green and its cutover is pushed (group B premises). Both
  trigger the all-volumes backup (~12 min each, extra NAS/backup-target load); that is why they are sequential, with the
  second backup being this plan's own backup_gate on the new volume.
- **Window**: attended AD-HOC run, human-gated (capability_change + backup-restore => never unattended). Step 0 (safe-update
  apply, ~20 min) runs first. Budget: 100 min happy path (excluding any WAITING-for-password stop) + up to 45 min rollback
  held in reserve. The operator must be reachable for PW-1 only; everything before it is unattended-capable within the run.
- **Renovate PR 410 (chart 3.6.0)**: inert for the image; it may auto-merge after its cooldown at any time, including
  mid-run. If Flux applies it during the migration, the HelmRelease re-renders from the same pinned tag (no-op rollout of
  labels only). Never `git commit --only` a helmrelease.yaml containing that hunk under this plan's subject (step 3).
- **igpu-i915**: the pod needs 1 slot on whichever node holds it (k8s-nuc14-03 at 2026-10-23, sole claimant there;
  k8s-nuc14-01 hosts immich-server, immich-machine-learning, makemkv). `talos-power-tuning-ab`, `node-feature-discovery-0.20.0`
  and the Talos roll plans are in `conflicts_with`.
- **backup-restore stacking**: `nocodb-2026.09.1`, `media-naming-p3` - never in the same slot. `longhorn-1.13.0`: the
  backup_gate + restore path run on the engine it replaces.
- **Prometheus**: 4.1 CONTROLs, G1b and 4.7 read Prometheus (the window's instrument). No open kube-prometheus-stack plan
  today (the 92.x plans are executed/superseded); if one is re-opened, add it to `conflicts_with` and do not run on its night.
- **cilium-1.20.3** (sun-attended:2026-10-25, solo): a CNI roll during verification reads as a Jellyfin/consumer failure.
- **No CIFS PVC action** anywhere in this plan; `cifs-jellyfin-media` is Tier-1. The retained RWX `jellyfin-config` is also
  not touched.
- **Biggest gotcha**: Pod Ready / HR Ready / `/health` 200 all arrive while the forward-only migration is still running
  (SetupServer). Judge only on `Startup complete` + `/System/Info/Public` 200 + the contents assertions - and never "roll back"
  with a bare `git revert`: 10.11.11 on a migrated DB is the documented failure mode; section 5's restore of the
  `jellyfin-config-rwo` gate backup is the rollback.
