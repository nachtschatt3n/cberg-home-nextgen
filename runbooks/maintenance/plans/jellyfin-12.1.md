---
plan_id: jellyfin-12.1
component: jellyfin
pr: null                              # No open Renovate PR targets 12.x. Re-verified 2026-09-15:
                                      # `gh pr list --state all --limit 300 --search "jellyfin"`
                                      # shows nothing newer than the CLOSED
                                      # 10.11.11.20260606-153911 bump (#166, 2026-06-06). This
                                      # held update is surfaced by coverage.py / sweep finding
                                      # F-fc5e2913, not by a Renovate PR.
kind: image
current: "10.11.11.20260606-153911"   # re-verified live 2026-09-15: deployment image, pod
                                      # digest sha256:aefb67e6… on k8s-nuc14-03, 0 restarts, 8d.
target: "12.1.20260915-010956"        # RETARGETED 2026-09-15 from 12.0.20260908-012347 — see
                                      # the REFRESH section. Docker Hub `latest`, `12`, `12.1`
                                      # and this tag all resolve to digest sha256:78d3ea12…
                                      # (published 2026-09-15T01:21Z). GitHub release v12.1:
                                      # prerelease=false, draft=false, 2026-09-15T01:23:53Z.
update_type: major
risk: high                            # Forward-only DB migration (upstream's own words, §1.3)
                                      # on the household's ACTIVELY USED media server — 61M
                                      # jellyfin.db, a real library (509 movies / 43 series /
                                      # 2377 episodes / 615 songs measured 2026-09-15) on
                                      # CIFS, real config on Longhorn, one repository plugin
                                      # upstream says must be removed first and which has NO
                                      # 12.x build, breaking API-route removals on an
                                      # internet-facing app (envoy-external), AND a legacy-
                                      # auth switch-off that this repo's OWN library-tools
                                      # CronJobs trip over (§1.4). Real state is at stake;
                                      # `high` is not precautionary rounding.
est_duration_min: 60                  # RAISED from 45 (2026-09-15): +Step 0 verification and
                                      # the upstream-mandated post-upgrade full library scan,
                                      # which 12.0's notes say "will take significantly longer
                                      # than normal" on first run — ~3000 items over CIFS.
                                      # §4.2 is only evaluable AFTER that scan completes.
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - helmrelease/jellyfin
    - deployment/jellyfin
    - pvc/jellyfin-config               # longhorn-static RWX 25Gi, 5.8G used — jellyfin.db,
                                        # plugins/, users, everything that matters
    - pvc/jellyfin-media                # cifs-jellyfin-media — NOT touched by this plan, see
                                        # §2.1; named so nobody touches it
    - plugin/TubeArchivistMetadata      # installed today (1.4.4.0, targetAbi 10.11.0.0) —
                                        # upstream requires repository plugins be removed
                                        # before migrating (§1.3); see §3 step 1
    - configmap/library-tools-scripts   # NEW 2026-09-15: four Jellyfin API calls use the
                                        # legacy `X-Emby-Token` header, which 12.x's
                                        # DisableLegacyAuthorization migration switches off
                                        # (§1.4). The header switch is being landed NOW by
                                        # cberg-agent as its own backward-compatible commit,
                                        # outside this plan; §3 step 0 references it and
                                        # gate G3 verifies it reconciled (0 call sites).
    - cronjob/media-metadata-coverage   # hourly consumer of the above (feeds media-dashboard)
    - cronjob/media-per-item-refresh    # 6-hourly consumer of the above
    - cronjob/media-rescan              # manual-only consumer of the above
    - deployment/media-dashboard        # reads coverage output; shows "no Jellyfin data" on 401
  shared: [igpu-i915]                   # REUSE the exact token scrypted-0.147.0.md and
                                        # frigate-0.18.0.md carry. Pod requests+limits
                                        # `gpu.intel.com/i915: 1`, scheduled on k8s-nuc14-03
                                        # (live 2026-09-15), which also serves
                                        # immich-machine-learning and makemkv (3/5 slots; plex
                                        # and immich-server have MOVED to nuc14-01 since the
                                        # 09-11 write-up). `shared` is an INTERSECTION key —
                                        # reuse this spelling in every GPU-touching plan.
depends_on: []
conflicts_with:
  # - media-audit-durable-output      # REMOVED 2026-09-23: that plan EXECUTED (960f3d4e) and was retired,
                                      # so the shared edit target no longer collides. Original note kept below:
                                      # sat-attended:2026-09-19) ALSO edits
                                      # configmap/library-tools-scripts. Two plans rewriting
                                      # the same ConfigMap in one window is exactly the
                                      # interference the window agent exists to catch; keep
                                      # them apart. (Review 2026-09-15: the step-0 hunks —
                                      # the X-Emby-Token lines in rescan.py /
                                      # metadata_coverage.py / per_item_refresh.py — do NOT
                                      # overlap 09-19's audit.py edit, so step 0 lands now,
                                      # not after 09-19; §6.) No other open plan touches
                                      # helmrelease/jellyfin or either jellyfin PVC
                                      # (`maintenance-plan.py --open`, 2026-09-15).
  - media-naming-p3                   # ROLLBACK-CLASS STACKING — ADDED 2026-09-21. Those three
  - n8n-2.39.8                        # and this plan are all `rollback_class: backup-restore`.
  # - nextcloud-34.0.4 (RESOLVED 2026-09-26: executed + retired in now:2026-09-26; ref removed) # Two backup-restore rollbacks in one slot leave no
                                      # rollback capacity for either — which is precisely why
                                      # THIS plan was moved off sun-attended:2026-10-04 on
                                      # 2026-09-15 (see the `window:` note below). That move
                                      # was recorded only as prose on the window line, so
                                      # nothing enforced the rule it established and the next
                                      # reader could not find it; declared here, it is
                                      # enforced. Once per pair: window-scheduler.py:253-260
                                      # reads conflicts_with in EITHER direction, so the three
                                      # counterpart files need no reciprocal entry.
security_ref: F-3a72570a              # Security finding on the CURRENT image — detail on
                                      # the record only, never here. A tag bump is the only
                                      # remediation this household performs for a
                                      # third-party image (we bump, we never rebuild). What
                                      # the target's scan looks like is recorded on the
                                      # finding via `policy-cli.py finding detail`, not in
                                      # this file; §4.8 has the verification command.
capability_change: true               # Real, user-visible breaking changes in this span —
                                      # see §1.3/§1.4. Legacy `/emby` and `/mediabrowser`
                                      # routes REMOVED, legacy authorization switched OFF by
                                      # a migration, global subtitle config replaced by
                                      # per-library config, and the installed
                                      # TubeArchivistMetadata plugin removed with no
                                      # 12.x-compatible build available (upstream issue open
                                      # since 2026-09-08) — a standing functionality loss.
rollback_class: backup-restore        # NOT git-revert. Upstream's 12.0 release notes:
                                      # "this release includes database changes that prevent
                                      # rolling back without a full restore." 12.1 carries the
                                      # same migrations. A bare image-tag revert reintroduces
                                      # 10.11.11's binary against a database 12.x has already
                                      # migrated forward — the documented failure mode. §2.3.
backup_gate: "on-demand Longhorn backup of the jellyfin-config volume (holds jellyfin.db,
  plugins/, users/, everything that matters), triggered in-window immediately before the tag
  edit is pushed and verified by a NEW Completed Backup CR for jellyfin-config whose
  creationTimestamp is AFTER the trigger command ran — the nightly 03:00 backup (newest
  Completed at review time: backup-d8aa67bc8b614641, 2026-09-15T03:04:21Z; re-record at
  window time) does not satisfy this gate on its own because it predates the
  plugin-removal step (§3 step 1). Triggered via cronjob/daily-backup-all-volumes (ns
  storage) — NOT `backup-of-all-volumes`, which does not exist. See §3 step 4 and §5."
finding_refs: [F-fc5e2913, F-3a72570a]
status: awaiting-go   # REVIEWED 2026-09-15 (plan-reviewer fan-out, corrections applied in c36388bc)
window: "sat-attended:2026-10-10"   # 2026-09-23: moved off 10-11 (flux-reconciler-impersonation is exclusive there; media-audit-durable-output left 10-10 by executing early). Earlier, 2026-09-15: moved off 10-04: reconciler RISK-CLASS STACKING — two backup-restore plans (frigate, jellyfin) in one slot leaves no rollback capacity; jellyfin has the heavier prerequisite list
premises:
  - id: image-is-still-10.11.11
    why: >-
      `current:` claims 10.11.11.20260606-153911 and every baseline in this plan
      (item counts, GPU probe, digest for rollback, client inventory) is captured
      against it. If the cluster already moved, this plan is stale and must be
      re-derived, not executed.
    run: kubectl get deploy -n media jellyfin -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: docker.io/jellyfin/jellyfin:10.11.11.20260606-153911
  - id: config-pvc-still-longhorn-static
    why: >-
      The entire rollback determination (§2.3) and the backup_gate rest on
      jellyfin-config being the Longhorn-static, backed-up volume it is today. If
      the StorageClass or binding changed, the backup/restore path this plan
      documents no longer applies.
    run: kubectl get pvc -n media jellyfin-config -o jsonpath='{.spec.storageClassName}'
    expect_exact: longhorn-static
  - id: jellyfin-config-volume-healthy
    why: >-
      The backup_gate depends on Longhorn being able to snapshot this volume
      on demand. A degraded/detached volume cannot satisfy the gate, and that
      must be caught before anything else is touched.
    run: kubectl get volumes.longhorn.io -n storage jellyfin-config -o jsonpath='{.status.state}'
    expect_exact: attached
  - id: media-storageclass-reclaim-retain
    why: >-
      docs/sops/storage-safety.md: cifs-jellyfin-media is `subdir: /` on the
      whole NAS media export (Tier-1/catastrophic). This plan performs NO PVC
      action, but the executor must know the class is still Retain before doing
      anything in this namespace — if it ever reads Delete, STOP and surface it;
      a mis-typed delete would then wipe the shared export for every media app.
    run: kubectl get sc cifs-jellyfin-media -o jsonpath='{.reclaimPolicy}'
    expect_exact: Retain
  - id: hr-remediation-at-default
    why: >-
      §3 step 2 disables Flux remediation for the migration attempt and §3
      step 8 restores it. If it is already 0 at window start, a previous attempt
      was left half-done and its state must be understood before a second
      migration is fired at the same database.
    run: kubectl get helmrelease -n media jellyfin -o jsonpath='{.spec.upgrade.remediation.retries}'
    expect_exact: "1"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/storage-safety.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-09-11"
---

# jellyfin: image 10.11.11.20260606-153911 -> 12.1.20260915-010956 (major)

## REFRESH 2026-09-15 — retargeted 12.0.20260908-012347 -> 12.1.20260915-010956 (F-fc5e2913)

Upstream shipped **12.1** on 2026-09-15, seven days after 12.0. `coverage.py`
matches plans on release line, so the 12.0 plan stopped covering this
component and the sweep re-dispatched a planner. The file was **renamed**
(`git mv jellyfin-12.0.md jellyfin-12.1.md`, `plan_id` moved with it) rather
than given a REFRESH-only note like `grafana-chart-13.2.3`, because unlike
that case the release line itself moved and a same-id plan would keep failing
the matcher every cycle. Nothing was keyed on the old id: `window: null`, no
GO, no issue beyond the sweep's own ingest row (which re-keys from the plan
file on the next cycle).

**What changed 12.0 -> 12.1, read from the v12.1 release notes and diffed
against the 12.0 notes already quoted below.** 12.1 is a **bugfix release** —
47 changes, every one a fix, no new breaking or behaviour changes listed, and
the same instruction: *"As always, please ensure you take a full backup before
upgrading!"* The **migration surface is unchanged**: the forward-only 12.0
database migrations are what a 10.11.11 -> 12.1 hop runs, so every premise
that made 12.0 `risk: high` / `backup-restore` / `capability_change: true`
carries over verbatim. Three of the 47 fixes touch the migration path itself,
which is why going **straight to 12.1 is preferable to 12.0**, not merely
equivalent:

1. *"Clean up invalid data before running migrations"* (#17835) and *"Fix
   database optimization memory use and pre-migration backup integrity"*
   (#17836) — the pre-migration backup 12.0 writes into `SQLiteBackups/` is
   fixed to be actually restorable, and dirty rows are cleaned before the
   schema moves. Both harden exactly the step this plan is afraid of.
2. *"Fix versions of a video still listing separately from their group and
   preserve manual merges"* (#17842) and *"Only group episodes as versions on a
   confident path parse"* (#17890) — the alternate-version regrouping that 12.0
   said the mandatory post-upgrade scan would repair. Still run the scan (§3
   step 7); 12.1 just makes its outcome less surprising.
3. *"Preserve library items when directory enumeration fails"* (#18007) — on
   a CIFS-backed library this is the difference between a transient SMB hiccup
   during the (long) first scan silently dropping items and not. Directly
   relevant to §4.2.

Also in 12.1 and relevant here: *"Fix nested unnumbered season folders
collapsing onto the first one"* (#18044), *"Fix trickplay using the wrong
video stream"* (#17883), *"Fix transcode throttling not enabling on supported
systems"* (#17906), *"Fix device access revocation not logging out existing
sessions"* (#18026). Nothing in 12.1 changes the plugin ABI beyond what 12.0
did; the TubeArchivistMetadata situation (§1.3 item 2) is unchanged.

**Every live premise was re-measured 2026-09-15**, not carried forward:
image/digest, PVC classes and PV reclaim policies, volume health, newest
backup CR, plugin inventory (`/Plugins` API and `/config/plugins`), DB size,
VAAPI encoder count and a real encode probe, i915 node allocation, alert
baseline, client-app inventory (`/Devices`), and the library item counts that
§4.2 compares against. Two things the 09-11 plan had **wrong** were found and
fixed in the process:

- Its VAAPI baseline/verification called bare `ffmpeg`, which is **not on
  PATH** in this image (`/usr/lib/jellyfin-ffmpeg/ffmpeg` is) — `grep -c`
  returned `0`, which would have read as "hardware encode lost" after the
  upgrade. Corrected to the full path; the real baseline is **7 vaapi
  encoders, VAAPI_ENCODE_OK**.
- Its API verification used the `X-Emby-Token` / `X-Emby-Authorization`
  headers — which are **precisely the legacy authorization 12.x switches
  off** (§1.4). The plan would have 401'd against its own upgraded server and
  reported a broken migration. Corrected to the modern `Authorization:
  MediaBrowser …` header, verified working on 10.11.11 today.

And one thing it **missed** entirely, now §1.4 and §3 step 0: this repo's own
`library-tools` scripts talk to Jellyfin with the legacy header.

## 1. Summary & why held

Move `deployment/jellyfin` (namespace `media`) from
`docker.io/jellyfin/jellyfin:10.11.11.20260606-153911` to
`docker.io/jellyfin/jellyfin:12.1.20260915-010956` — the chart itself
(`jellyfin` 3.2.0, appVersion 10.11.8, still the newest in
`jellyfin.github.io/jellyfin-helm`) is **not** touched by this plan; only the
image tag inside the existing HelmRelease changes.

### 1.1 This is a genuine major, not a versioning artifact

Upstream jumped from the 10.x line to `12.0` — **there is no 11.x release
line** (GitHub Releases: v12.0 GA 2026-09-08, preceded by rc1..rc7 from
2026-06-21; v12.1 GA 2026-09-15). Jellyfin's 12.0 notes state the supported
path explicitly:

> "Direct upgrades from 10.10.7 and 10.11.x to 12.0 are supported;
> intermediate upgrades are not required."

12.1 is a minor on that line with no extra step called out, so
`10.11.11 -> 12.1` direct is the same supported path — there is no reason to
stage through 12.0, and per the REFRESH section three migration-path fixes
are a reason not to. **Re-run the tag/GA check at execution time** (§2.5 gate
G1); a plan written today and run days later must not assume a registry tag
still resolves.

### 1.2 Why this cannot be an auto-safe update

`update_type: major` alone routes this to the plan lane under
`runbooks/auto-update-policy.yaml` / `coverage.py` regardless of any deny
rule — no false-positive hold to report. The hold is correct and the reasons
are concrete (§1.3, §1.4, §2.3).

### 1.3 Breaking-change review, quoted from the 12.0 release notes (all still apply to 12.1)

1. **Forward-only database migration.** *"A full backup of the data
   directory is strongly recommended, as this release includes database
   changes that prevent rolling back without a full restore."* Basis for
   `rollback_class: backup-restore` and the mandatory `backup_gate` (§2.3).
2. **Installed repository plugins must be removed first.** *"Installed
   repository plugins (anything not built-in) should also be removed before
   migrating. Plugins will likely need time to adapt to the new database
   changes, so re-adding them afterward is the safest approach."* **Not
   hypothetical for us**: `/Plugins` lists `TubeArchivist Metadata 1.4.4.0
   Active` alongside the five built-ins (AudioDB, MusicBrainz, OMDb, Studio
   Images, TMDb — all `10.11.11.0`, they ship with the server and migrate
   with it). The plugin's `build.yaml` says `targetAbi: "10.11.0.0"`, its
   last release is v1.4.4 (2025-12-02), and upstream issue **#96 "Jellyfin
   12.0 support — plugin still targets ABI 10.11.0.0" is open (2026-09-08)**.
   So removal (§3 step 1) is a **standing capability loss** — the Tube
   Archivist -> Jellyfin metadata bridge from
   `docs/sops/media-library-standards.md` — until a 12.x build exists. That is
   an operator judgement (§6), not something this plan resolves.
3. **Legacy API routes removed.** *"Legacy route prefixes removed (`/emby/*`
   and `/mediabrowser/*`). Old third-party clients that rely on them will
   stop working."* Jellyfin is on `envoy-external` (internet-facing,
   `jellyfin.${SECRET_DOMAIN}`, no SecurityPolicy — it authenticates in-app).
   No in-repo consumer uses those prefixes (grepped 2026-09-15). The client
   inventory in §1.4 is what bounds the external exposure.
4. **Legacy authorization disabled** — *"Legacy authorization is now
   disabled by default, and a migration disables it on existing installs as
   well."* See §1.4: this one has a concrete, in-repo casualty.
5. **Subtitle configuration** moves from global to per-library — existing
   global subtitle settings do not carry forward automatically.
6. **File-extension reclassification** (`.ogg` audio-only, `.aifc` audio,
   `.aiff` no longer image). Low blast radius here; noted because it is a
   silent reclassification, not an error.
7. **Mandatory full library scan after upgrade.** *"Alternative versions of
   media that were auto resolved (not manually merged) will be removed due to
   data type issues -> A full library scan will fix this again and is
   therefore REQUIRED AFTER UPGRADE. First scan will take significantly longer
   than normal and some movies might appear as newly added."* A required
   step (§3 step 7) and the reason §4.2 is evaluated only after it completes.

### 1.4 Legacy authorization — what it actually is, and who trips over it (NEW 2026-09-15)

Read from the v12.1 source, not the prose. In
`Jellyfin.Server.Implementations/Security/AuthorizationContext.cs` the
following are each guarded by `Configuration.EnableLegacyAuthorization`:
the `X-Emby-Token` header, the `X-MediaBrowser-Token` header, the
`api_key=` query parameter, and the `X-Emby-Authorization` header. **Not**
guarded (i.e. the forms that keep working): the standard
`Authorization: MediaBrowser Token="…"` header (also carrying
`Client/Device/DeviceId/Version`) and the `ApiKey=` query parameter (capital
A, K). The migration
`Jellyfin.Server/Migrations/Routines/20260531160000_DisableLegacyAuthorization.cs`
runs at `CoreInitialisation` on first boot of 12.x, sets
`EnableLegacyAuthorization = false` and saves `system.xml`. Our live
`system.xml` has **`<EnableLegacyAuthorization>true`** today, so this
migration WILL fire and WILL change behaviour for every legacy-header caller.

Measured 2026-09-15 against the live 10.11.11 (via port-forward, key from
`secret/media-manager-tokens` kept in-shell): modern header -> 200,
`X-Emby-Token` -> 200 (only because legacy is still on), `ApiKey=` -> 200.

**Casualty in this repo:** `configmap/library-tools-scripts` sends
`headers={"X-Emby-Token": …}` in four places — `rescan.py` (`/Library/Refresh`),
`metadata_coverage.py` (`/Items?Recursive=true…`), `per_item_refresh.py`
(`/Items?Recursive=true…` and `/Items/{id}/Refresh`). Consumers:
`cronjob/media-metadata-coverage` (hourly, feeds `deployment/media-dashboard`,
which then renders *"no Jellyfin data (check JELLYFIN_API_KEY in secret)"* —
a misleading diagnosis), `cronjob/media-per-item-refresh` (6-hourly),
`cronjob/media-rescan` (manual). After the upgrade all four calls 401. Fix:
§3 step 0 switches them to the modern header, which **already works on
10.11.11**, so it lands as a separate backward-compatible commit *before* the
bump and needs no rollback coupling.

**Exposure outside the repo** (`/Devices`, 28 registered devices, app
families only): Jellyfin Web (10.10.6..10.11.11 builds — refreshes with the
server), Jellyfin Mobile iOS/iPadOS 1.7.0, Jellyfin iOS 1.7.0, Jellyfin tvOS
1.0.1, Infuse-Direct 8.1.5, **Home Assistant** (3 devices, the
`jellyfin` integration), **Music Assistant** (2.5.8 and 2.10.3, the
Jellyfin provider). Official Jellyfin clients and Infuse use the modern
header. HA and Music Assistant go through Python client libraries; the
2026-09-15 review read both from source (verified, not inferred):

- **Home Assistant 2026.9.2** (live image) pins `jellyfin-apiclient-python==1.16.0`.
  At that tag the client's own requests carry `Authorization: MediaBrowser …`
  (`http.py` l.271), so the integration's **state entities and media_player
  survive** the migration. But its `_build_url` (`http.py` l.91-92) still
  appends the legacy `api_key=` query parameter to the stream/thumbnail URLs
  that HA's media_source hands to players. **Expected casualty: playing or
  browsing Jellyfin items from HA's media browser 401s after the upgrade**
  until HA ships a newer apiclient (upstream master already uses `ApiKey`;
  v1.17.0/v1.18.0 exist, HA has not bumped). Remedy = HA update, **not**
  re-enabling legacy auth. Explicit check in §4.6.
- **Music Assistant 2.10.3** (live pod) uses `aiojellyfin 0.14.1`, whose own
  requests send `Authorization: MediaBrowser` (`session.py` l.75); its
  `_build_url` adds legacy `api_key`, but MA's Jellyfin provider
  `_normalize_jellyfin_media_url` rewrites it to `apiKey`, which matches the
  unguarded `ApiKey` branch case-insensitively. **Expected green** in §4.6.

If either check fails anyway, the remedy is on their side (client update) or
an **operator decision** to re-enable `EnableLegacyAuthorization` in
`system.xml`/Dashboard — the key still exists in 12.x; the migration only
flips it once — which weakens the hardening 12.0 shipped and is therefore not
a step in this plan.

## 2. Pre-checks

### 2.1 State snapshot — what is actually on each volume (re-measured 2026-09-15)

- `jellyfin-config` -> **longhorn-static**, RWX, 25Gi declared / **5.8G used**;
  PV `jellyfin-config`, `volumeHandle: jellyfin-config`, reclaim `Retain`;
  Longhorn volume `attached`/`healthy`. Contains `jellyfin.db` (61M — the live
  library/user/auth DB), `library.db.old` (28M, a prior-migration leftover,
  harmless), `plugins/`, `trickplay/`, `subtitles/`, `SQLiteBackups/`, and
  `config/{system,network,encoding,…}.xml`. **This is the volume that
  matters.** Backed by the nightly `cronjob/daily-backup-all-volumes` (ns
  `storage`, `0 3 * * *`, owned by the Longhorn RecurringJob
  `daily-backup-all-volumes` — `kubectl get recurringjobs.longhorn.io -n
  storage daily-backup-all-volumes`; the name `backup-of-all-volumes` that
  several docs still use does NOT exist in the cluster). Newest Completed
  Backup CR at review time: `backup-d8aa67bc8b614641` 2026-09-15T03:04:21Z
  (re-record at window time). That backup predates the plugin removal this
  plan performs, so it is **not** sufficient — the `backup_gate` requires a
  fresh in-window backup (§3 step 4).
- `jellyfin-media` -> **`cifs-jellyfin-media`**, `//192.168.55.240/media`,
  `subdir: /`, StorageClass **and** PV `reclaimPolicy: Retain` (both
  re-read live). This is the **Tier-1 / catastrophic** class in
  `docs/sops/storage-safety.md` — shared with Plex, MakeMKV, JDownloader,
  Tube Archivist, Immich's cache. **This plan performs NO PVC action of any
  kind** — no delete, no resize, no StorageClass change, on either PVC. It is
  named in `touches` only so the window agent and executor know what must
  not be touched. The storage-safety 3-step pre-flight does not apply because
  nothing destructive is planned here; the `media-storageclass-reclaim-retain`
  premise is a tripwire, not a licence.
- No external database, no shared DB instance — Jellyfin's state is entirely
  file-based (SQLite) on `jellyfin-config`.

### 2.2 Hardware / shared iGPU

Live pod is on **k8s-nuc14-03**, holding `gpu.intel.com/i915: 1` in both
requests and limits, `privileged: true`, `SYS_ADMIN`, `runAsUser/Group: 0`
— accepted under `AR-009`. Node 03's i915 allocation is **3/5** at refresh
time: `jellyfin`, `immich-machine-learning`, `makemkv` (plex and
immich-server now sit on nuc14-01 — the 09-11 write-up is out of date on
this). Rendered Deployment strategy is `Recreate` (verified on the live
object, not the HelmRelease), so the old pod fully releases its i915 slot
before the replacement is scheduled. The shared-hardware exposure is a
privileged container re-probing the Intel graphics stack on a render node
shared with whatever else is transcoding on nuc14-03 at that moment. VAAPI
must be proven post-upgrade (§4.4), not assumed from a Ready pod.

### 2.3 Rollback determination — read this before assuming `git-revert`

Jellyfin's 12.0 notes foreclose a plain tag revert: rolling back "without a
full restore" is unsupported once the migration has run, because the
on-disk `jellyfin.db` schema moves forward and 10.11.11's code is not
guaranteed to read it (and per §1.3 item 2, plugin removal is destructive to
plugin-side state regardless of the core DB). Therefore:

- `rollback_class: backup-restore`, not `git-revert`.
- The **only** valid rollback is: revert the git tag (keeps the Kustomization
  honest) **and** restore `jellyfin-config` from the pre-upgrade Longhorn
  backup captured by the `backup_gate` (§3 step 4, §5).
- Do **not** attempt a bare tag revert and call it done — a Ready pod on the
  reverted tag proves nothing about whether it can read a migrated database.
- The step-0 library-tools commit does **not** need reverting on rollback:
  the modern header works on 10.11.11 (measured).

### 2.4 Alert baseline (re-measured 2026-09-15)

No `media`-namespace alerts firing (Prometheus `/api/v1/alerts`,
Watchdog/InfoInhibitor excluded). The only non-noise alert cluster-wide is
`AuthentikOutpostDisconnected` (kube-system, `pending`) — pre-existing,
unrelated, do not attribute it to this change.

### 2.5 Commands — run all of these before touching anything. G1/G2/G3 are ABORT gates.

```bash
cd /Users/mu/code/cberg-home-nextgen

# --- G1 (ABORT) — re-verify the target still resolves and is still GA.
#     Lives here, not in `premises:`, because plan-premises.py's read-only
#     allowlist deliberately excludes network tools like curl.
curl -s "https://api.github.com/repos/jellyfin/jellyfin/releases/tags/v12.1" | python3 -c \
 "import sys,json;d=json.load(sys.stdin);print(d['tag_name'],'prerelease',d['prerelease'],'draft',d['draft'])"
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:jellyfin/jellyfin:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  "https://registry-1.docker.io/v2/jellyfin/jellyfin/manifests/12.1.20260915-010956"
#   MUST be prerelease=False, draft=False, and manifest HTTP 200. Anything
#   else: STOP, do not execute, re-derive the plan. (If a 12.2 or 12.1.x
#   rebuild has since appeared, this plan needs a REFRESH, not a sed.)

# --- G2 (ABORT) — plugin inventory unchanged since this plan was refreshed.
POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n media $POD -- sh -c 'ls /config/plugins'
#   Expected (measured 2026-09-15): configurations/  .jellyfin-plugin
#   TubeArchivistMetadata_1.4.4.0/
#   A DIFFERENT or ADDITIONAL repository plugin => re-check its 12.x
#   compatibility before proceeding — §3 step 1 only accounts for this one.

# --- G3 (ABORT) — §3 step 0 has LANDED on main and reconciled: the
#     library-tools scripts must no longer send the legacy header.
git log --oneline -3 -- kubernetes/apps/media/library-tools/app/scripts-configmap.yaml
kubectl get configmap -n media library-tools-scripts -o json | python3 -c \
 "import sys,json;print('legacy X-Emby-Token call sites:', sum(v.count('X-Emby-Token') for v in json.load(sys.stdin)['data'].values()))"
#   MUST print 0. If it prints 4, step 0 has not landed — do it first (it is
#   backward-compatible and safe any time before the window), then re-check.

# --- Baselines for §4 (record the numbers) ---
kubectl get pod -n media $POD -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
#   expect sha256:aefb67e6a7ff1debdd154a78a7bbb780fd0c873d8639210a7f6a2016ad2b35db (the rollback digest)
kubectl exec -n media $POD -- sh -c 'du -sh /config/data/jellyfin.db; ls -la /config/data/*.db'
kubectl exec -n media $POD -- sh -c 'grep -o "<EnableLegacyAuthorization>[^<]*" /config/config/system.xml'
#   expect <EnableLegacyAuthorization>true — the migration in §1.4 will flip it
kubectl exec -n media $POD -- sh -c '/usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -encoders 2>/dev/null | grep -c vaapi'
#   expect 7 (measured 2026-09-15). NOTE the full path — bare `ffmpeg` is NOT on PATH here.
kubectl exec -n media $POD -- sh -c \
  '/usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -f lavfi -i testsrc=size=320x240:rate=5:duration=1 -vf format=nv12,hwupload \
     -c:v h264_vaapi -f null - && echo VAAPI_ENCODE_OK'
RESTART_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "RESTART_TS=$RESTART_TS"

# API key for the contents assertions — the library-tools key, never echoed:
JF_KEY=$(sops -d kubernetes/apps/media/library-tools/app/secret.sops.yaml \
  | python3 -c "import sys,yaml;print(yaml.safe_load(sys.stdin)['stringData']['JELLYFIN_API_KEY'])")
kubectl port-forward -n media svc/jellyfin 8097:8096 >/dev/null 2>&1 &
sleep 3
curl -s -H "Authorization: MediaBrowser Token=\"$JF_KEY\"" http://localhost:8097/Items/Counts | python3 -m json.tool
#   BASELINE measured 2026-09-15 (re-record at window time — the library moves):
#   MovieCount 509  SeriesCount 43  EpisodeCount 2377  SongCount 615
#   AlbumCount 39   BoxSetCount 78
curl -s -H "Authorization: MediaBrowser Token=\"$JF_KEY\"" "http://localhost:8097/Devices" | python3 -c "
import sys,json,collections
d=json.load(sys.stdin); items=d.get('Items',[])
for (a,v),n in sorted(collections.Counter((i.get('AppName'),i.get('AppVersion')) for i in items).items(), key=lambda x:-x[1]): print(n,a,v)"
#   Note which Home Assistant / Music Assistant versions are registered — §4.6.

# --- Alert noise suppression (docs/sops/application-update.md Step 1) ---
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"media","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"Jellyfin.*|Kube(Pod|Deployment).*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"operator",
  "comment":"jellyfin 10.11.11 -> 12.1 major upgrade — rollout+migration noise. auto-expires 4h"}'
runbooks/update-marker.sh add jellyfin media 4 "jellyfin 10.11.11->12.1"
```

## 3. Steps

GitOps + one in-window manual admin action (plugin removal). Follow
`docs/sops/application-update.md` §"Attended" tier (silence -> disable
rollback -> bump -> watch -> verify -> restore rollback).

0. **ALREADY IN FLIGHT — the library-tools header switch is being landed
   separately by cberg-agent (2026-09-15), as its own `git commit --only`
   outside this plan. Do NOT redo it here.** It is backward-compatible
   (measured working on 10.11.11: the `Authorization: MediaBrowser` header is
   unguarded in `AuthorizationContext.cs`), and its hunks — the four
   `X-Emby-Token` call sites in `rescan.py` (`/Library/Refresh`),
   `metadata_coverage.py` (`jellyfin_items`), `per_item_refresh.py`
   (`jellyfin_missing`, `jellyfin_refresh`) — do not overlap the `audit.py`
   key that `media-audit-durable-output` (sat-attended:2026-09-19) edits, so
   there is no reason to hold it until after 09-19. What this plan owns is the
   **verification** that it reconciled, which is gate G3 in §2.5 plus the
   contents check below (run once the ConfigMap shows 0 call sites):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git log --oneline -3 -- kubernetes/apps/media/library-tools/app/scripts-configmap.yaml   # the header-switch commit
   grep -c 'X-Emby-Token' kubernetes/apps/media/library-tools/app/scripts-configmap.yaml     # 0
   # CONTENTS check for step 0 (after Flux reconciles the ConfigMap): a coverage run
   # must still return Jellyfin data on 10.11.11 with the modern header —
   J=coverage-step0-$(date +%H%M)
   kubectl create job -n media --from=cronjob/media-metadata-coverage "$J"
   kubectl wait -n media job/"$J" --for=condition=complete --timeout=10m
   kubectl logs -n media job/"$J" | grep -i jellyfin | head
   #   must show non-zero Jellyfin item/coverage figures, not an auth error.
   ```
   If G3 still prints 4 at window start, the separate commit has not landed
   or not reconciled — chase THAT commit (do not write a second one from this
   plan), then re-run G3.

1. **Remove the TubeArchivistMetadata plugin from the running instance**
   (Dashboard -> Plugins -> uninstall), or via the pod filesystem if the UI
   path is unavailable:
   ```bash
   POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
   kubectl exec -n media $POD -- sh -c 'rm -rf "/config/plugins/TubeArchivistMetadata_1.4.4.0"'
   ```
   App-state on the PVC, not a manifest — no GitOps path exists (same class
   of exception CLAUDE.md documents for Home Assistant packages). Do this
   **before** the tag bump, per upstream's explicit instruction (§1.3 item 2).
   Its 12.x incompatibility is upstream issue #96 — nothing to re-install
   afterwards until that closes (§6).

2. Disable Flux rollback for the attempt (so a slow first-boot migration
   isn't mistaken for a crash and rolled back mid-migration). Edit
   `kubernetes/apps/media/jellyfin/app/helmrelease.yaml`:
   ```yaml
   upgrade:
     remediation:
       retries: 0
       remediateLastFailure: false   # restore retries: 1 / true after success (step 8)
   ```

3. Bump the image tag in the same file:
   ```yaml
   image:
     repository: docker.io/jellyfin/jellyfin
     tag: 12.1.20260915-010956     # was: 10.11.11.20260606-153911
   ```
   Change nothing else in this pass — no env/plugin/probe changes belong in
   the same diff as the version bump.

4. **Satisfy the `backup_gate` — before committing anything above.**
   Trigger an on-demand backup and prove it landed AFTER step 1:
   ```bash
   GATE_START=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "GATE_START=$GATE_START"
   # docs/sops/backup.md "Manual Backup (Ad-hoc)" — the CronJob backs up ALL
   # volumes (broader than needed, acceptable); or Longhorn UI -> Volume ->
   # jellyfin-config -> Create Backup for just this one. The CronJob is
   # `daily-backup-all-volumes` (Longhorn RecurringJob-owned) — NOT
   # `backup-of-all-volumes`, which returns NotFound.
   kubectl create job --from=cronjob/daily-backup-all-volumes pre-jellyfin-12-$(date +%Y%m%d-%H%M) -n storage
   kubectl get backups -n storage -l backup-volume=jellyfin-config \
     --sort-by=.metadata.creationTimestamp \
     -o custom-columns=NAME:.metadata.name,STATE:.status.state,CREATED:.metadata.creationTimestamp | tail -3
   #   MUST show a NEW Completed backup with CREATED > GATE_START (and newer
   #   than backup-22db01b0fb404cf2 / 2026-09-14T03:00:31Z on file at refresh
   #   time). Record its NAME — §5 restores from it. Not Completed within a
   #   reasonable wait => STOP; do not proceed to step 5 without it.
   ```

5. Commit + push both HelmRelease edits together with `--only` (shared
   worktree, see CLAUDE.md):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git diff kubernetes/apps/media/jellyfin/app/helmrelease.yaml
   git commit --only kubernetes/apps/media/jellyfin/app/helmrelease.yaml \
     -m "feat(jellyfin): 10.11.11.20260606-153911 -> 12.1.20260915-010956 (upstream GA major); disable remediation for the migration"
   git show --stat HEAD        # every file here must be yours
   git push
   ```

6. Watch Flux reconcile — no manual `flux reconcile`; the GitRepository
   webhook + 30m HelmRelease interval covers it:
   ```bash
   flux get helmrelease -n media jellyfin --watch
   kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -w
   kubectl logs -n media -l app.kubernetes.io/name=jellyfin -f | grep -iE 'migrat|DisableLegacyAuthorization|error|fail'
   ```
   Expect the old pod to fully terminate before the new one appears
   (`Recreate`). Budget for the image pull plus the first-boot migration
   (12.0 notes: *"Migration routines clean up existing data on first boot"*)
   — let it run to completion; do not hand-kill the pod mid-migration
   (`docs/sops/application-update.md` §7 if it wedges).

   **How 12.1 actually behaves during the migration (read from v12.1
   `Program.cs` / `SetupServer.cs`, corrected 2026-09-15):** every migration
   (CoreInitialisation l.211, AppInitialisation l.217, cleanup, DB optimize)
   runs BEFORE `_jellyfinHost.StartAsync()` (l.227), but a `SetupServer`
   already listens on 8096 during that time: it maps `/health` (returns
   Degraded → HTTP **200**) and `/System/Info/Public` (→ **503**). Three
   consequences:
   - liveness (`/health`) stays green throughout, so the pod is **not** killed
     at "60s + 10x30s" by a long migration — do not plan around that;
   - readiness (tcpSocket 8096) and the chart-3.2.0 default `startupProbe`
     (tcpSocket, 30x10s, present on the live Deployment) both pass on the
     SetupServer, so **pod Ready, `helm --wait` and HR Ready=True all arrive
     WHILE the migration is still running** — "Ready" proves nothing here,
     which is the concrete reason §4 is contents-based;
   - do NOT "protect" the migration by raising a probe threshold via the
     HelmRelease: under `Recreate` a pod-template change replaces the pod and
     kills the very migration it was meant to protect.

   What to do instead: watch the pod log for `Running migration X of Y` /
   `Startup complete`, treat `/System/Info/Public` → 503 as "still migrating",
   and end this step only on a 503→200 transition whose body reports
   `Version` 12.1.x (§4.1). Then **re-establish the port-forward** — the one
   from §2.5 died with the old pod:
   ```bash
   kubectl port-forward -n media svc/jellyfin 8097:8096 >/dev/null 2>&1 &
   sleep 3
   curl -s -o /dev/null -w 'public-info http=%{http_code}\n' http://localhost:8097/System/Info/Public   # 503 = migrating, 200 = up
   ```

7. **Mandatory post-upgrade full library scan** (upstream requirement, §1.3
   item 7) — Dashboard -> Scheduled Tasks -> "Scan Media Library", or:
   ```bash
   curl -s -X POST "http://localhost:8097/Library/Refresh" -H "Authorization: MediaBrowser Token=\"$JF_KEY\""
   ```
   This scan is expected to run long (first scan after the type fixes,
   ~3000 items over CIFS). §4.2 and §4.5 are evaluated after it Completes;
   if it outlasts the window, the window may close on §4.1/§4.3/§4.4/§4.6
   green with §4.2/§4.5 handed to the same-day post-window check — it must
   not be skipped, and the plan is not `executed` until it passes.

8. On success: restore `upgrade.remediation.retries: 1` /
   `remediateLastFailure: true` in the HelmRelease, commit, push; drop the
   silence; clear the marker (§5 tail). On failure: rollback (§5); clear the
   marker.

## 4. Verification

### 4.1 Floor (shape checks — necessary, not sufficient)

```bash
POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
kubectl get helmrelease -n media jellyfin -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pods -n media -l app.kubernetes.io/name=jellyfin
kubectl get pod -n media $POD -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
#   expect sha256:78d3ea1207d1322471fcac39a614f004f2ccf7e878f95ab2977d752f07e4dd7e (12.1 digest as of 2026-09-15)
curl -s http://localhost:8097/System/Info/Public | python3 -c "import sys,json;print(json.load(sys.stdin)['Version'])"   # 12.1.x
kubectl exec -n media $POD -- sh -c 'grep -o "<EnableLegacyAuthorization>[^<]*" /config/config/system.xml'
#   expect false — proves the migration routine ran, and explains any legacy-client fallout
```

### 4.2 CONTENTS ASSERTION (primary — library survived the migration)

> **CONTENTS ASSERTION: after the mandatory full scan (§3 step 7) has
> Completed, `/Items/Counts` is >= the pre-upgrade baseline for every
> non-zero counter**, measured by Jellyfin's own API with the modern
> `Authorization` header, compared to the §2.5 baseline (2026-09-15:
> Movie 509 / Series 43 / Episode 2377 / Song 615 / Album 39 / BoxSet 78).

```bash
curl -s "http://localhost:8097/Items/Counts" -H "Authorization: MediaBrowser Token=\"$JF_KEY\"" | python3 -m json.tool
```

Evaluate **only after** §4.5 shows the scan Completed — 12.0's notes say
auto-resolved alternate versions are dropped on migration and restored by
the scan, so a count read mid-scan is expected to be low and proves nothing.
A shortfall that persists after the scan must be explained item-by-item
(`/Items?Recursive=true&Fields=Path…` diffed against the pre-upgrade list
`library-tools`' `jellyfin_items` already produces) before it is accepted; a
schema-only migration with counts at zero is exactly the "ceiling without a
floor" failure in `docs/sops/verification-contents-not-shape.md`.

### 4.3 CONTENTS ASSERTION (secondary — real login still works, on the modern path)

> **CONTENTS ASSERTION: a real user authentication succeeds post-upgrade
> using the non-legacy header** — not `/health` or `/System/Info/Public`
> (unauthenticated, green even if every login broke).

```bash
# Credentials: NO SOPS secret in this repo holds a Jellyfin admin password (only the
# library-tools API key in media/library-tools secret.sops.yaml and media-manager-tokens
# exist — checked 2026-09-15). The operator supplies the Jellyfin admin username/password
# at the prompt (read -s), never writes them into a file, and this check is therefore
# ATTENDED. Do not skip it because the placeholders are blank.
read -r -p 'Jellyfin admin user: ' JF_USER; read -r -s -p 'Jellyfin admin pw (not stored): ' JF_PW; echo
curl -s -o /dev/null -w 'http=%{http_code}\n' -X POST "http://localhost:8097/Users/AuthenticateByName" \
  -H 'Content-Type: application/json' \
  -H 'Authorization: MediaBrowser Client="plan-verify", Device="cli", DeviceId="plan-verify", Version="1.0"' \
  -d "{\"Username\":\"$JF_USER\",\"Pw\":\"$JF_PW\"}"
unset JF_PW
#   MUST be 200 with an AccessToken in the body, not 401.
# And the API key path the CronJobs use:
curl -s -o /dev/null -w 'apikey-modern http=%{http_code}\n' -H "Authorization: MediaBrowser Token=\"$JF_KEY\"" http://localhost:8097/System/Info
curl -s -o /dev/null -w 'legacy-header http=%{http_code}\n' -H "X-Emby-Token: $JF_KEY" http://localhost:8097/System/Info
#   EXPECTED after the migration: modern 200, legacy 401. A legacy 200 means
#   EnableLegacyAuthorization did NOT flip — investigate before declaring
#   the migration complete; do not "fix" it by leaving it on.
```

### 4.4 CONTENTS ASSERTION (hardware transcode)

> **CONTENTS ASSERTION: hardware VA-API encode on the shared iGPU still
> engages** — compared to the §2.5 baseline (7 vaapi encoders,
> VAAPI_ENCODE_OK on 10.11.11). Full ffmpeg path — bare `ffmpeg` is not on PATH.

```bash
kubectl exec -n media $POD -- sh -c '/usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -encoders 2>/dev/null | grep -c vaapi'
#   MUST be >= 7.
kubectl exec -n media $POD -- sh -c \
  '/usr/lib/jellyfin-ffmpeg/ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -f lavfi -i testsrc=size=320x240:rate=5:duration=1 -vf format=nv12,hwupload \
     -c:v h264_vaapi -f null - && echo VAAPI_ENCODE_OK'
```

### 4.5 Full library scan actually ran (not just "task exists")

```bash
curl -s "http://localhost:8097/ScheduledTasks" -H "Authorization: MediaBrowser Token=\"$JF_KEY\"" \
  | python3 -c "import sys,json;[print(t['Name'],t['State'],(t.get('LastExecutionResult') or {}).get('Status'),(t.get('LastExecutionResult') or {}).get('EndTimeUtc')) for t in json.load(sys.stdin) if 'Scan' in t['Name']]"
#   "Scan Media Library" must show Status Completed with EndTimeUtc AFTER
#   RESTART_TS (§2.5) — pre-refresh it read Completed 2026-09-14T19:52Z; a
#   timestamp older than RESTART_TS is the OLD scan, not evidence.
```

### 4.6 Consumers on the other side of the auth change (CONTENTS, not reachability)

```bash
# library-tools (this repo): a coverage run returns real Jellyfin figures on 12.1
kubectl create job -n media --from=cronjob/media-metadata-coverage coverage-post12-$(date +%H%M)
kubectl logs -n media job/coverage-post12-$(date +%H%M) | grep -iE 'jellyfin|401|unauthor' | head
#   non-zero Jellyfin figures, no 401.
# media-dashboard renders a Jellyfin section (not "no Jellyfin data"):
curl -s http://<media-dashboard via port-forward>/ | grep -c 'no Jellyfin data'    # expect 0

# Home Assistant `jellyfin` integration (HA 2026.9.2, jellyfin-apiclient-python 1.16.0 — §1.4):
#   EXPECTED GREEN: entities / media_player not `unavailable` (ha-agent / hactl) — the
#     integration's own requests use the modern Authorization header.
#   EXPECTED CASUALTY: browsing/playing a Jellyfin item from HA's media browser
#     (Media -> Jellyfin) 401s, because the client appends legacy `api_key=` to the
#     stream/thumbnail URLs it hands to players. Record it as EXPECTED, not as a failed
#     migration; remedy = an HA release that bumps the apiclient past 1.16.0 (upstream
#     already uses `ApiKey`). Do NOT re-enable legacy auth for this.
# Music Assistant (2.10.3, aiojellyfin 0.14.1 — §1.4): EXPECTED GREEN — library browse
#   returns items AND a track/movie starts playing (MA rewrites api_key -> apiKey, the
#   unguarded branch). A 401 here is unexpected and needs a real look.
#   Any other failure => §1.4 remedy path (client-side fix or an operator
#   decision), NOT a rollback trigger on its own.
```

### 4.7 External reachability + no new alerts

```bash
curl -s -o /dev/null -w 'http=%{http_code}\n' https://jellyfin.${SECRET_DOMAIN}/System/Ping    # 200 via envoy-external
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys, json
for a in json.load(sys.stdin)['data']['alerts']:
    n = a['labels'].get('alertname')
    if n in ('Watchdog','InfoInhibitor'): continue
    print(n, a['labels'].get('namespace'), a['state'])
"
#   Compare against §2.4 (only pre-existing AuthentikOutpostDisconnected).
```

### 4.8 Security finding follow-through (F-3a72570a)

```bash
# same flags the sweep's CVE check uses; TAG is the tag now running
trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed docker.io/jellyfin/jellyfin:$TAG
```
Compare the result against the **finding record**, not against this file —
the planner's 2026-09-15 scan of the target is attached there
(`runbooks/policy-cli.py finding show F-3a72570a`), and the post-upgrade
result goes there too (`finding detail F-3a72570a --plan jellyfin-12.1`),
per `docs/sops/vulnerability-disclosure.md`. Per the house rule we bump and
never rebuild, so whatever the next sweep's CVE check reports on an
already-newest tag is rated under `AR-029`, not as an action for this plan;
if it still reports the finding as actionable after 12.1 is live, that is a
check-logic question for the sweep, not a reason to hold this upgrade.

## 5. Rollback

Concrete, two-part per §2.3 — a tag revert alone is **not** sufficient and
must not be represented as a completed rollback.

```bash
cd /Users/mu/code/cberg-home-nextgen

# 1) Revert the manifest (cosmetic without the restore, but keeps git honest):
git log --oneline -5 -- kubernetes/apps/media/jellyfin/app/helmrelease.yaml
git revert --no-edit <the-bump-commit>
git show --stat HEAD
git push
#    Do NOT revert the step-0 library-tools commit — the modern header works on 10.11.11.

# 2) Suspend BOTH Flux objects so nothing re-applies the old PV/PVC or restarts the
#    Deployment mid-restore (pv/pvc are applied by the `jellyfin` Kustomization in ns
#    media, prune: true — the HelmRelease alone is not enough), then free the volume:
flux suspend kustomization -n media jellyfin
flux suspend helmrelease -n media jellyfin
kubectl scale deploy -n media jellyfin --replicas=0     # release the RWX volume before restore
kubectl wait -n media --for=delete pod -l app.kubernetes.io/name=jellyfin --timeout=5m

# 3) Restore jellyfin-config from the backup_gate's Backup CR (name recorded in §3
#    step 4). READ FIRST: `spec.csi.volumeHandle` on a PersistentVolume is IMMUTABLE,
#    and pv/jellyfin-config + pvc/jellyfin-config are git-tracked
#    (kubernetes/apps/media/jellyfin/app/config-pv.yaml, config-pvc.yaml) and
#    Flux-reapplied — so "repoint the existing PV" is NOT possible. This is the ONE
#    ordered recipe (docs/sops/backup.md "Bind Restored Volume to Application", as
#    corrected for git-tracked static PVs):
#
#    (a) Longhorn UI (port-forward svc/longhorn-frontend 8080:80) -> Backup ->
#        jellyfin-config -> <the gate's backup> -> Restore -> NEW volume name
#        R=jellyfin-config-r$(date +%Y%m%d). numberOfReplicas: git's config-pv.yaml
#        declares "3" while the live Longhorn volume runs 2 — choose deliberately and
#        write the SAME value into the PV in (b). Wait until the restored volume shows
#        detached + healthy in `kubectl get volumes.longhorn.io -n storage $R`.
#    (b) In git, on main, --only these two files, do NOT push yet:
#          config-pv.yaml : metadata.name -> $R ; csi.volumeHandle -> $R ;
#                           keep accessModes [ReadWriteMany], 25Gi, longhorn-static,
#                           persistentVolumeReclaimPolicy Retain, fsType ext4,
#                           staleReplicaTimeout "30"
#          config-pvc.yaml: spec.volumeName -> $R ; the PVC NAME STAYS `jellyfin-config`
#                           (the HelmRelease's `existingClaim`)
#    (c) Delete the OLD PVC and its PV. Storage-safety pre-flight first — this is
#        driver.longhorn.io with reclaim Retain, NOT a CIFS class, so it is allowed, but
#        it must be shown, and pvc/jellyfin-media is never named in this step:
PV=$(kubectl -n media get pvc jellyfin-config -o jsonpath='{.spec.volumeName}')
kubectl get pv "$PV" -o jsonpath='{.spec.csi.driver} {.spec.persistentVolumeReclaimPolicy} {.spec.csi.volumeHandle}{"\n"}'
#        MUST print: driver.longhorn.io Retain jellyfin-config  — anything else: STOP.
kubectl -n media delete pvc jellyfin-config
kubectl delete pv "$PV"          # Retain: the old Longhorn volume `jellyfin-config` (the
                                 # failed-migration state) stays for forensics; delete it in
                                 # Longhorn only after the restored one has proven itself
#    (d) git push (the two-file commit from (b)); resume the Kustomization so Flux
#        creates pv/$R and the re-pointed pvc/jellyfin-config, then resume the HR:
flux resume kustomization -n media jellyfin
kubectl -n media get pvc jellyfin-config -o jsonpath='{.status.phase} {.spec.volumeName}{"\n"}'   # Bound jellyfin-config-r<date>
flux resume helmrelease -n media jellyfin
flux reconcile helmrelease -n media jellyfin --force
#
#    ALTERNATIVE (same-name restore, no git change): delete the Longhorn Volume CR
#    `jellyfin-config` and restore the backup under the SAME name so the existing static
#    PV re-binds. ONLY if the executor has first confirmed, on a scratch volume, that
#    Longhorn does not cascade-delete the externally-created PV/PVC — not verified at
#    plan time, so the git-tracked path above is the default.
#    Either way: NO action on pvc/jellyfin-media at any point.
```

Confirm the cluster is actually back — by digest and by re-running the
contents assertions, not by "Ready":

```bash
POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
kubectl get pod -n media $POD -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
#   MUST be sha256:aefb67e6a7ff1debdd154a78a7bbb780fd0c873d8639210a7f6a2016ad2b35db (10.11.11, §2.5)
curl -s "http://localhost:8097/Items/Counts" -H "Authorization: MediaBrowser Token=\"$JF_KEY\"" | python3 -m json.tool
#   MUST match the pre-upgrade §2.5 baseline — proves the RESTORED database,
#   not just the reverted binary
kubectl exec -n media $POD -- sh -c 'ls /config/plugins'
#   the restored volume brings TubeArchivistMetadata_1.4.4.0 back with it
```

Then clear the silence and marker:
```bash
curl -s -X DELETE localhost:9093/api/v2/silences/<id>
runbooks/update-marker.sh clear jellyfin
```

## 6. Interference notes

- **`conflicts_with: [media-audit-durable-output]`** — that plan (vetted,
  `sat-attended:2026-09-19`) rewrites `configmap/library-tools-scripts`; so
  does the step-0 header switch. Never in the same window. The step-0 commit
  itself is being landed now by cberg-agent (outside this plan): its hunks
  (the X-Emby-Token lines) do not overlap 09-19's `audit.py` edit on a single
  `main`, so it neither waits for 09-19 nor hands that plan a merge conflict.
  What must be true before THIS window is G3 = 0 call sites and a coverage
  Job returning real Jellyfin figures (§3 step 0).
- **`touches.shared: [igpu-i915]`** — the token from `scrypted-0.147.0.md`
  (originally `scrypted-0.145.0.md`, since retired), reused deliberately
  (set-intersection match). `frigate-0.18.0` (draft, medium, 50min, also
  recommends `sun-attended:2026-09-20`) now declares the same token too and
  is a privileged GPU-touching image bump on **k8s-nuc14-02**; this plan's
  pod is on **k8s-nuc14-03**. Different physical iGPU — not a hard conflict,
  but the scheduler will raise an `igpu-i915` INTERFERENCE warning if they
  share a slot — so avoid stacking two privileged GPU-touching bumps
  back-to-back; if both land on 09-20 anyway, run this one **last** so its
  background scan does not overlap frigate's verification. Same for
  `scrypted-0.147.0` (nuc14-02): separate slots.
- **No PVC action on the happy path — and exactly ONE on rollback.**
  `cifs-jellyfin-media` is Tier-1/catastrophic per
  `docs/sops/storage-safety.md`; it is named in `touches` so nobody touches
  it (§2.1). The rollback in §5 restores `jellyfin-config` to a NEW Longhorn
  volume, commits a new PV name + PVC `volumeName` to git, and deletes the
  OLD `pvc/jellyfin-config` + its PV (Longhorn, reclaim Retain — the old
  volume survives) after the storage-safety pre-flight shown in §5 step 3(c).
  It never touches the CIFS PVC.
- **`backup_gate` must PASS before the commit in §3 step 5.** This plan
  derives HUMAN-GATED regardless (`capability_change: true` forecloses both
  `auto-night` and `auto-backup-gated` in `runbooks/autonomy-policy.yaml`),
  so this is a correctness gate, not an autonomy gate: without it a failed
  migration has no way back.
- **Window recommendation (queue as of 2026-09-15, `maintenance-plan.py --open`):**
  - `sat-attended:2026-09-19` holds `media-audit-durable-output` — excluded
    by `conflicts_with`.
  - **`sun-attended:2026-09-20`** (200 min, risk capacity 6) holds
    `absenty-drop-npm-runtime` (low=1, 60 min, awaiting-go). Adding this plan
    (high=3, 60 min) => **risk-load 4/6, 120/200 min** — comfortable, and it
    is the attended day with a human present for the go/no-go, the plugin
    removal and the HA/Music Assistant checks. If `frigate-0.18.0`
    (medium=2, 50 min) is also placed there: 6/6 and 170/200 — at the risk
    ceiling; the window agent should then choose between frigate and this
    plan for 09-20, not run both plus absenty.
  - `sat-attended:2026-09-26` (wazuh, medium, 45 min) would land at 5/6 and
    105/90 min — over time; `2026-10-03` (external-dns, medium, 40 min) at
    5/6 and 100/90 — over time. Neither fits without dropping something.
  - `sun-attended:2026-09-27` is the Talos node-reboot window
    (`talos-1.14.0`, high, 140/200) — do not add a second high-risk item.
  `window:` is left `null` for the window agent to confirm against the live
  queue.
- **TubeArchivistMetadata has no 12.x build** (upstream issue #96 open since
  2026-09-08, `targetAbi 10.11.0.0`). Removing it is required by upstream and
  is a standing capability loss for the Tube Archivist -> Jellyfin bridge
  until that issue closes. Whether to proceed anyway, wait for the plugin,
  or replace the integration is an **operator decision** to be made at the
  go/no-go — this plan does not silently resolve it.
- **Biggest gotcha for the executor**: the migration flips
  `EnableLegacyAuthorization` off, so anything still sending `X-Emby-Token`
  / `X-Emby-Authorization` / `api_key=` — including this plan's own
  pre-refresh verification commands, and this repo's library-tools CronJobs
  until step 0 lands — starts returning 401 and looks like a broken upgrade.
  Do not read that as a failed migration, and do not "fix" it by re-enabling
  legacy auth; use the modern header (§1.4). And, as before: do not accept
  "pod Ready" or "new digest" as success, and do not accept a bare
  `git revert` as "rolled back" — §4.2/§4.3's real API calls and §5's
  restore-then-verify are what actually prove anything here.
