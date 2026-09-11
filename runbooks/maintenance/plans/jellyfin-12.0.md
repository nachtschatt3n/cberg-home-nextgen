---
plan_id: jellyfin-12.0
component: jellyfin
pr: null                              # No open Renovate PR targets 12.0. Verified 2026-09-11:
                                      # `gh pr list --state all --limit 300 --search "jellyfin"`
                                      # shows nothing newer than the CLOSED
                                      # 10.11.11.20260606-153911 bump (2026-06-06). This held
                                      # update was surfaced as a direct sweep finding
                                      # (F-fc5e2913), not a Renovate PR.
kind: image
current: "10.11.11.20260606-153911"   # verified live 2026-09-11: `kubectl get deploy -n media
                                      # jellyfin -o jsonpath='{...image}'` matches exactly.
target: "12.0.20260908-012347"
update_type: major
risk: high                            # Forward-only DB migration (upstream's own words, see
                                      # §2.3) on the household's ACTIVELY USED media server —
                                      # 3.5G jellyfin.db, real library under /media, real
                                      # config under /config, one installed repository plugin
                                      # (TubeArchivistMetadata) upstream says must be removed
                                      # before migrating, and breaking API-route removals that
                                      # can strand external clients (this app is exposed on
                                      # envoy-external, internet-facing). This is NOT the
                                      # scrypted-0.145.0 case (empty instance, nothing
                                      # configured, no rollback exposure) — real state is
                                      # actually at stake here, so `risk: high` is not
                                      # precautionary rounding.
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - helmrelease/jellyfin
    - deployment/jellyfin
    - pvc/jellyfin-config               # longhorn-static RWX 25Gi, 5.8G used — jellyfin.db,
                                        # library.db, plugins/, users, everything that matters
    - pvc/jellyfin-media                # cifs-jellyfin-media — NOT touched by this plan, see
                                        # §2.2 and the Rules block below
    - plugin/TubeArchivistMetadata      # installed today (/config/plugins,
                                        # TubeArchivistMetadata_1.4.4.0) — upstream requires
                                        # repository plugins be removed before migrating
                                        # (§1.3); see §3/§4 step 1
  shared: [igpu-i915]                   # REUSE the exact token introduced in
                                        # scrypted-0.145.0.md. Pod requests+limits
                                        # `gpu.intel.com/i915: 1`, currently scheduled on
                                        # k8s-nuc14-03 (live, measured), which also serves
                                        # plex, makemkv, immich-server. `shared` is an
                                        # INTERSECTION key — a synonym detects nothing, reuse
                                        # this spelling in every future GPU-touching plan.
depends_on: []
conflicts_with: []                    # Checked via `maintenance-plan.py --open` 2026-09-11:
                                      # no other open plan touches pvc/jellyfin-config,
                                      # pvc/jellyfin-media, or helmrelease/jellyfin.
                                      # scrypted-0.145.0 shares the `igpu-i915` token but runs
                                      # on a DIFFERENT physical node (nuc14-02, not
                                      # nuc14-03) — not a hard conflict, see §7.
security_ref: null                    # Not a security-driven plan. F-fc5e2913 is a
                                      # version-drift finding (severity `critical` in the
                                      # sweep's generic major-bump classifier), not a
                                      # vulnerability disclosure — nothing to withhold here.
capability_change: true               # Real, user-visible breaking changes in this span —
                                      # see §1.3. Not rounded down: legacy `/emby` and
                                      # `/mediabrowser` API routes are REMOVED (old
                                      # third-party clients break), legacy authorization is
                                      # disabled by default, global subtitle config is
                                      # replaced by per-library config, and the installed
                                      # TubeArchivistMetadata plugin must be removed before
                                      # migrating (§1.3, §3) — a real, if small, functionality
                                      # loss until/unless a 12.0-compatible build exists.
rollback_class: backup-restore        # NOT git-revert. Upstream's own 12.0 release notes:
                                      # "this release includes database changes that prevent
                                      # rolling back without a full restore." A bare image-tag
                                      # revert reintroduces 10.11.11's binary against a
                                      # database 12.0 has already migrated forward — the
                                      # documented failure mode, not a hypothetical. See §2.3.
backup_gate: "on-demand Longhorn backup of the jellyfin-config volume (holds jellyfin.db,
  library.db, plugins/, users/, everything that matters), triggered in-window immediately
  before the tag edit is pushed and verified by a NEW Completed Backup CR for
  jellyfin-config whose creationTimestamp is AFTER the trigger command ran — the stale
  03:00 daily backup (last Completed 2026-09-10T03:01:28Z at plan-write time) does not
  satisfy this gate on its own because it predates the plugin-removal step (§3/§4).
  See §3 step 4 and §6."
finding_refs: [F-fc5e2913]
status: draft
window: null                          # See §7 for the recommended slot and why none of the
                                      # currently queued dates is proposed here.
premises:
  - id: image-is-still-10.11.11
    why: >-
      `current:` claims 10.11.11.20260606-153911 and every baseline in this plan
      (item counts, GPU probe, digest for rollback) is captured against it. If the
      cluster already moved, this plan is stale and must be re-derived, not executed.
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
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/storage-safety.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-09-11"
---

## 1. Summary & why held

Move `deployment/jellyfin` (namespace `media`) from
`docker.io/jellyfin/jellyfin:10.11.11.20260606-153911` to
`docker.io/jellyfin/jellyfin:12.0.20260908-012347` — the chart itself
(`jellyfin` 3.2.0) is already latest and is **not** touched by this plan; only
the image tag inside the existing HelmRelease changes.

### 1.1 This is a genuine major, not a versioning artifact

Upstream jumped straight from the 10.x line to `12.0` — **there is no 11.x
release line**, confirmed against the GitHub Releases API
(`prerelease:false`, published 2026-09-08T01:38:39Z, preceded by rc3..rc7).
This is not a skipped hop the operator needs to backfill: Jellyfin's own
release notes state the supported path explicitly —

> "Direct upgrades from 10.10.7 and 10.11.x to 12.0 are supported;
> intermediate upgrades are not required."

Our running `10.11.11.20260606-153911` is on that supported path. Docker Hub
tags `latest`, `12`, `12.0` and `12.0.20260908-012347` all resolve to the same
2026-09-08 build (verified by whoever dispatched this investigation; **re-run
this check at execution time**, §3 gate G1 — a plan written today and run
days later must not assume a registry tag still resolves).

### 1.2 Why this cannot be an auto-safe update

`update_type: major` alone routes this to the plan lane under
`runbooks/auto-update-policy.yaml` / `coverage.py` regardless of any deny
rule — no false-positive hold to report here, unlike some held updates. The
hold is correct and the reasons are concrete (§1.3, §2.3).

### 1.3 Breaking-change review, quoted from the 12.0 release notes

1. **Forward-only database migration.** *"A full backup of the data
   directory is strongly recommended, as this release includes database
   changes that prevent rolling back without a full restore."* This is the
   basis for `rollback_class: backup-restore` and the mandatory `backup_gate`
   (§2.3).
2. **Installed repository plugins must be removed first.** *"Installed
   repository plugins (anything not built-in) should also be removed before
   migrating"* due to database incompatibilities. **This is not
   hypothetical for us**: `/config/plugins` on the live pod contains
   `TubeArchivistMetadata_1.4.4.0` today (measured 2026-09-11). It must be
   removed before the tag bump (§4 step 1) and its post-upgrade
   compatibility is an open question for the operator (§7) — it bridges
   Tube Archivist content into Jellyfin per `docs/sops/media-library-standards.md`,
   so its removal is a real, if scoped, functionality loss until/unless a
   12.0-compatible build is installed.
3. **Legacy API routes removed.** *"Legacy route prefixes removed (`/emby/*`
   and `/mediabrowser/*`). Old third-party clients that rely on them will
   stop working."* Jellyfin is exposed on `envoy-external` (internet-facing,
   `jellyfin.${SECRET_DOMAIN}`, no SecurityPolicy — it authenticates in-app),
   so this can affect real external clients, not just admin tooling.
4. **Legacy authorization disabled by default** on both fresh and existing
   installs — an auth-path behaviour change, not cosmetic.
5. **Subtitle configuration** moves from global to per-library — existing
   global subtitle settings do not carry forward automatically.
6. **File-extension handling changes**: `.ogg` becomes audio-only (was also
   video), `.aifc` is now recognized as audio, `.aiff` is no longer treated
   as an image. Low blast radius here (no such extensions expected in this
   library) but noted because it is a silent reclassification, not an error.
7. **Mandatory full library scan after upgrade.** *"A full library scan will
   fix this again and is therefore REQUIRED AFTER UPGRADE"* to restore
   alternate versions of media (multi-version items). This is a required
   step (§4), not an optional verification nicety.

Items 3–5 are why `capability_change: true` — this is a real behaviour
change for users and any third-party client, not just an internal version
bump.

## 2. Pre-checks

### 2.1 State snapshot — what is actually on each volume

- `jellyfin-config` → **longhorn-static**, RWX, 25Gi declared / **5.8G used**
  (measured). Contains `jellyfin.db` (61M SQLite, the live library/user/auth
  DB), `library.db.old` (28M, a prior-migration leftover, harmless), the
  `plugins/` directory (see §1.3 item 2), `trickplay/`, `subtitles/`,
  `SQLiteBackups/`. **This is the volume that matters.** Backed by the daily
  `backup-of-all-volumes` CronJob (`docs/sops/backup.md`); latest Completed
  Backup CR at plan-write time: `2026-09-10T03:01:28Z`. That backup predates
  the plugin removal this plan performs, so it is **not** sufficient on its
  own — the `backup_gate` requires a fresh in-window backup (§4 step 4).
- `jellyfin-media` → **`cifs-jellyfin-media`**, `//192.168.55.240/media`,
  `subdir: /`, `reclaimPolicy: Retain`. This is the **Tier-1 / catastrophic**
  class in `docs/sops/storage-safety.md` — a `Delete` reclaim here would wipe
  the entire shared media export (also used by Plex, MakeMKV, JDownloader,
  Tube Archivist, Immich's cache). **This plan performs NO PVC action of any
  kind** — no delete, no resize, no StorageClass change, on either PVC. It is
  named in `touches` only so the window agent and executor know what must
  not be touched. The storage-safety 3-step pre-flight does not apply because
  nothing destructive is planned here.
- No external database, no shared DB instance — Jellyfin's state is entirely
  file-based (SQLite) on `jellyfin-config`.

### 2.2 Hardware / shared iGPU

Live pod is on **k8s-nuc14-03**, holding `gpu.intel.com/i915: 1` in both
requests and limits, `securityContext.privileged: true`,
`capabilities.add: [SYS_ADMIN]`, `runAsUser/Group: 0` — accepted under
`AR-009` (`docs/sops/...` risk register, "Privileged Containers... for
Hardware Access"). Node `k8s-nuc14-03`'s i915 allocation measured 3/5 at
investigation time, shared with `plex`, `makemkv`, `immich-server` per
`gpu.intel.com/i915` device-plugin accounting on that node. Deployment
strategy is `Recreate` (declared in values), so the old pod fully releases
its i915 slot before the replacement is scheduled — a failed start does not
starve the node-03 neighbours. The real shared-hardware exposure, as with
`scrypted-0.145.0`, is one level down: a privileged container re-probing the
Intel graphics stack shares the physical render node with whatever else is
transcoding on nuc14-03 at that moment. Nothing in the 12.0 span specifically
rebases the Intel compute-runtime (that was the scrypted v0.145.0 finding, a
different image), but VAAPI must still be proven working post-upgrade
(§5.2), not assumed from a Ready pod.

### 2.3 Rollback determination — read this before assuming `git-revert`

Jellyfin's own 12.0 release explicitly forecloses a plain tag revert:
rolling back "without a full restore" is unsupported once the migration has
run, because the on-disk `jellyfin.db`/`library.db` schema moves forward and
10.11.11's code is not guaranteed to read a 12.0-migrated database correctly
(and per §1.3 item 2, plugin removal is destructive to plugin-side state
regardless of the core DB). Therefore:

- `rollback_class: backup-restore`, not `git-revert`.
- The **only** valid rollback is: revert the git tag (cosmetic, keeps the
  Kustomization honest) **and** restore `jellyfin-config` from the
  pre-upgrade Longhorn backup captured by the `backup_gate` (§4 step 4, §6).
- Do **not** attempt a bare tag revert and call it done — that reproduces
  exactly the failure mode upstream warns about, silently, because a Ready
  pod on the reverted tag proves nothing about whether it can actually read
  the (now-migrated) database.

### 2.4 Alert baseline

No `media`-namespace alerts firing at investigation time (Prometheus
`/api/v1/alerts`, Watchdog/InfoInhibitor excluded). The only active alert
cluster-wide is `AuthentikOutpostDisconnected` (kube-system, `pending`) —
unrelated, pre-existing, do not attribute any of it to this change.

### 2.5 Commands — run all of these before touching anything. G1/G2 are ABORT gates.

```bash
cd /Users/mu/code/cberg-home-nextgen

# --- G1 (ABORT) — re-verify the target still resolves and is still GA.
#     NOTE: this lives here, not in `premises:`, because plan-premises.py's
#     read-only allowlist (kubectl/flux/talosctl/helm/git + a few bare utils)
#     deliberately excludes network tools like curl — the same reason
#     scrypted-0.145.0.md's equivalent check lives in its §3, not its
#     frontmatter. Re-run both queries live; do not trust this plan's prose.
curl -s "https://api.github.com/repos/jellyfin/jellyfin/releases/tags/v12.0" | python3 -c \
 "import sys,json;d=json.load(sys.stdin);print(d['tag_name'],'prerelease',d['prerelease'],'draft',d['draft'])"
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:jellyfin/jellyfin:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  "https://registry-1.docker.io/v2/jellyfin/jellyfin/manifests/12.0.20260908-012347"
#   MUST be prerelease=False, draft=False, and manifest HTTP 200. Anything
#   else: STOP, do not execute, re-derive the plan.

# --- G2 (ABORT) — confirm the plugin inventory has not changed since this
#     plan was written (kubectl exec is outside plan-premises.py's allowlist,
#     so this is a manual gate here, mirroring scrypted-0.145.0.md's G3).
POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n media $POD -- sh -c 'ls /config/plugins'
#   Expected (measured 2026-09-11): configurations/  .jellyfin-plugin
#   TubeArchivistMetadata_1.4.4.0/
#   If a DIFFERENT or ADDITIONAL plugin now appears, re-check its 12.0
#   compatibility before proceeding — §4 step 1 only accounts for the
#   plugin(s) named here.

# --- Baselines for §5, and pre-migration inventory for the backup_gate ---
kubectl get pod -n media $POD -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
kubectl exec -n media $POD -- sh -c 'du -sh /config/data/jellyfin.db; ls -la /config/data/*.db'
kubectl exec -n media $POD -- ffmpeg -hide_banner -encoders 2>/dev/null | grep -c vaapi
kubectl exec -n media $POD -- sh -c \
  'ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -f lavfi -i testsrc=size=320x240:rate=5:duration=1 -vf format=nv12,hwupload \
     -c:v h264_vaapi -f null - && echo VAAPI_ENCODE_OK'
RESTART_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "RESTART_TS=$RESTART_TS"

# --- Alert noise suppression (docs/sops/application-update.md Step 1) ---
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"media","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"Jellyfin.*|Kube(Pod|Deployment).*","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"operator",
  "comment":"jellyfin 10.11.11 -> 12.0 major upgrade — rollout+migration noise. auto-expires 4h"}'
runbooks/update-marker.sh add jellyfin media 4 "jellyfin 10.11.11->12.0"
```

## 3. Steps

GitOps + one in-window manual admin action (plugin removal). Follow
`docs/sops/application-update.md` §"Attended" tier (silence → disable
rollback → bump → watch → verify → restore rollback).

1. **Remove the TubeArchivistMetadata plugin from the running instance**
   (Jellyfin Dashboard → Plugins → uninstall), or via the pod filesystem if
   the UI path is unavailable:
   ```bash
   POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
   kubectl exec -n media $POD -- sh -c 'rm -rf "/config/plugins/TubeArchivistMetadata_1.4.4.0"'
   ```
   This is app-state on the PVC, not a manifest — there is no GitOps path for
   it (same class of exception CLAUDE.md documents for Home Assistant
   packages). Do this **before** the tag bump, per upstream's explicit
   instruction (§1.3 item 2).

2. Disable Flux rollback for the attempt (so a slow first-boot migration
   isn't mistaken for a crash and rolled back mid-migration). Edit
   `kubernetes/apps/media/jellyfin/app/helmrelease.yaml`:
   ```yaml
   upgrade:
     remediation:
       retries: 0
       remediateLastFailure: false   # restore retries: 1 after success (§5)
   ```

3. Bump the image tag in the same file:
   ```yaml
   image:
     repository: docker.io/jellyfin/jellyfin
     tag: 12.0.20260908-012347     # was: 10.11.11.20260606-153911
   ```
   Change nothing else in this pass — no plugin/env changes belong in the
   same diff as the version bump.

4. **Satisfy the `backup_gate` — do this before committing anything above.**
   Trigger an on-demand Longhorn backup of `jellyfin-config` and prove it
   landed AFTER the plugin removal in step 1:
   ```bash
   kubectl port-forward -n storage svc/longhorn-frontend 8080:80 &
   # Longhorn UI -> Volume -> jellyfin-config -> Create Backup
   # (no CLI trigger exists for a single named volume outside the CronJob;
   # the daily CronJob backs up ALL volumes, which is broader than needed
   # here but acceptable if timing allows — do not wait for 03:00, trigger now)
   GATE_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
   kubectl get backups -n storage -l backup-volume=jellyfin-config \
     --sort-by=.metadata.creationTimestamp \
     -o custom-columns=NAME:.metadata.name,STATE:.status.state,CREATED:.metadata.creationTimestamp | tail -3
   #   MUST show a NEW Completed backup with CREATED > GATE_START and >
   #   the 2026-09-10T03:01:28Z backup on file at plan-write time. If it does
   #   not appear Completed within a reasonable wait, STOP — do not proceed
   #   to step 5 without this.
   ```

5. Commit + push both edits together with `--only` (shared worktree, see
   CLAUDE.md):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git diff kubernetes/apps/media/jellyfin/app/helmrelease.yaml
   git commit --only kubernetes/apps/media/jellyfin/app/helmrelease.yaml \
     -m "feat(jellyfin): 10.11.11.20260606-153911 -> 12.0.20260908-012347 (upstream GA major); disable remediation for the migration"
   git show --stat HEAD        # every file here must be yours
   git push
   ```

6. Watch Flux reconcile — no manual `flux reconcile`, the GitRepository
   webhook + 30m HelmRelease interval covers it:
   ```bash
   flux get helmrelease -n media jellyfin --watch
   kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -w
   ```
   Expect the old pod to fully terminate before the new one appears
   (`Recreate` strategy). Budget for the image pull plus the first-boot DB
   migration — allow it to run to completion; do not hand-kill the pod
   mid-migration (`docs/sops/application-update.md` §7 if it wedges).

7. **Mandatory post-upgrade full library scan** (upstream requirement, §1.3
   item 7) — trigger via Dashboard → Scheduled Tasks → "Scan Media Library",
   or:
   ```bash
   # requires an admin API key; see §5.2 for how to obtain one if not already held
   curl -s -X POST "http://localhost:8096/Library/Refresh" -H "X-Emby-Token: $JELLYFIN_API_KEY"
   ```

8. On success: restore `upgrade.remediation.retries: 1` in the HelmRelease,
   commit, push; drop the silence; clear the marker (§5.6). On failure:
   rollback (§6); clear the marker.

## 4. Verification

### 4.1 Floor (shape checks — necessary, not sufficient)

```bash
POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
kubectl get helmrelease -n media jellyfin -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pods -n media -l app.kubernetes.io/name=jellyfin
kubectl get pod -n media $POD -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'   # NEW digest
```

### 4.2 CONTENTS ASSERTION (primary — library survived the migration)

> **CONTENTS ASSERTION: the library item count after migration is >= the
> pre-upgrade count, not merely "some items exist"** — measured via
> Jellyfin's own `/Items/Counts` API (real query, not a DB file-size proxy;
> no `sqlite3` binary is present in this image to query `jellyfin.db`
> directly), compared to a baseline captured BEFORE the tag edit is pushed.

```bash
# BEFORE (part of §3 pre-checks, capture and record this number):
curl -s "http://localhost:8096/Items/Counts" -H "X-Emby-Token: $JELLYFIN_API_KEY" | python3 -m json.tool
# AFTER (post-migration, same call):
curl -s "http://localhost:8096/Items/Counts" -H "X-Emby-Token: $JELLYFIN_API_KEY" | python3 -m json.tool
#   MovieCount / SeriesCount / SongCount / etc. must be >= the BEFORE values,
#   never silently zero. A schema-only migration (tables present, DB file
#   grew) with item counts at zero is exactly the "ceiling without a floor"
#   failure this repo has hit before (`docs/sops/verification-contents-not-shape.md`).
```

If no API key is already held, create one first (Dashboard → API Keys →
"+"), or authenticate directly:
```bash
curl -s -X POST "http://localhost:8096/Users/AuthenticateByName" \
  -H 'Content-Type: application/json' \
  -H 'X-Emby-Authorization: MediaBrowser Client="plan-verify", Device="cli", DeviceId="plan-verify", Version="1.0"' \
  -d '{"Username":"<admin-user>","Pw":"<password>"}'
#   A successful login here is ALSO the auth-path contents assertion (§4.3) —
#   run it for real, don't stop at /System/Info/Public (unauthenticated,
#   proves nothing about the legacy-auth-disabled-by-default change, §1.3
#   item 4).
```

### 4.3 CONTENTS ASSERTION (secondary — real login still works)

> **CONTENTS ASSERTION: a real authenticated login succeeds post-upgrade** —
> not `/health` or `/System/Info/Public` (both unauthenticated and would stay
> green even if every login broke). This is the check that catches the
> "legacy authorization disabled by default" change (§1.3 item 4) actually
> locking out a real account.

The `AuthenticateByName` call above IS this assertion — it must return a
`200` with an `AccessToken` in the body, not a `401`.

### 4.4 CONTENTS ASSERTION (hardware transcode)

> **CONTENTS ASSERTION: hardware VA-API encode on the shared iGPU still
> engages** — compared to the §2.5 baseline (VAAPI_ENCODE_OK, N vaapi
> encoders on 10.11.11).

```bash
kubectl exec -n media $POD -- ffmpeg -hide_banner -encoders 2>/dev/null | grep -c vaapi
#   MUST match (or exceed) the pre-upgrade count.
kubectl exec -n media $POD -- sh -c \
  'ffmpeg -hide_banner -loglevel error -init_hw_device vaapi=va:/dev/dri/renderD128 \
     -f lavfi -i testsrc=size=320x240:rate=5:duration=1 -vf format=nv12,hwupload \
     -c:v h264_vaapi -f null - && echo VAAPI_ENCODE_OK'
```

### 4.5 Full library scan actually ran (not just "task exists")

```bash
curl -s "http://localhost:8096/ScheduledTasks?IsEnabled=true" -H "X-Emby-Token: $JELLYFIN_API_KEY" \
  | python3 -c "import sys,json;[print(t['Name'],t['State'],t.get('LastExecutionResult',{}).get('Status')) for t in json.load(sys.stdin) if 'Scan' in t['Name']]"
#   The library-scan task's LastExecutionResult.Status must be "Completed"
#   with a timestamp AFTER RESTART_TS (§2.5), not merely "task is Idle".
```

### 4.6 External reachability (real client path, not just cluster-internal)

```bash
curl -s -o /dev/null -w 'http=%{http_code}\n' https://jellyfin.${SECRET_DOMAIN}/System/Ping
#   Expect 200. This is the envoy-external HTTPRoute path a real remote
#   client uses — verify it, not just the in-cluster port-forward.
```

### 4.7 No new firing alerts

```bash
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys, json
for a in json.load(sys.stdin)['data']['alerts']:
    n = a['labels'].get('alertname')
    if n in ('Watchdog','InfoInhibitor'): continue
    print(n, a['labels'].get('namespace'), a['state'])
"
#   Compare against the §2.4 baseline (only pre-existing AuthentikOutpostDisconnected).
```

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

# 2) Suspend the HelmRelease so Flux doesn't fight the restore mid-flight:
flux suspend helmrelease -n media jellyfin

# 3) Restore jellyfin-config from the backup_gate's Backup CR (Longhorn UI:
#    port-forward svc/longhorn-frontend, Backup -> jellyfin-config backup ->
#    Restore -> new volume, e.g. `jellyfin-config-restored`), then repoint
#    the PV per docs/sops/backup.md "Bind Restored Volume to Application" —
#    or, if the restore target is named identically and the original PV/PVC
#    are deleted+recreated pointing at the restored volumeHandle, confirm the
#    claimRef matches before resuming.

flux resume helmrelease -n media jellyfin
flux reconcile helmrelease -n media jellyfin --force
```

Confirm the cluster is actually back — by digest and by re-running the
contents assertions, not by "Ready":

```bash
POD=$(kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o jsonpath='{.items[0].metadata.name}')
kubectl get pod -n media $POD -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
#   MUST be the 10.11.11.20260606-153911 digest recorded in §2.5
curl -s "http://localhost:8096/Items/Counts" -H "X-Emby-Token: $JELLYFIN_API_KEY" | python3 -m json.tool
#   MUST match the pre-upgrade §4.2 baseline — proves the RESTORED database,
#   not just the reverted binary
```

Then clear the silence and marker (§3 step 8 style):
```bash
curl -s -X DELETE localhost:9093/api/v2/silences/<id>
runbooks/update-marker.sh clear jellyfin
```

## 6. Interference notes

- **`touches.shared: [igpu-i915]`** is the token introduced in
  `scrypted-0.145.0.md` — reused deliberately, not a synonym. It is matched
  as a set intersection, so it only flags interference against plans that
  adopt the *same spelling*. `scrypted-0.145.0` shares this token but runs on
  **k8s-nuc14-02**, a different physical iGPU from this plan's
  **k8s-nuc14-03** — not a hard conflict, but the window agent should still
  avoid stacking multiple privileged, GPU-touching image bumps in one window
  as a matter of general caution (same rationale scrypted's plan gives).
- **No PVC action of any kind is taken or should be taken.**
  `cifs-jellyfin-media` (Tier-1/catastrophic per `docs/sops/storage-safety.md`)
  is named in `touches` purely so the window agent knows what must not be
  perturbed — see §2.1.
- **`backup_gate` must PASS before the commit in §3 step 5.** This plan
  derives HUMAN-GATED regardless (capability_change:true forecloses both
  `auto-night` and `auto-backup-gated` classes in
  `runbooks/autonomy-policy.yaml`), so this is not an autonomy gate in the
  unattended sense — it is a correctness gate: without it, a failed
  migration has no way back.
- **Window: none of the currently queued dates fits without stress.**
  Checked via `maintenance-plan.py --open` (2026-09-11):
  - `sat-attended:2026-09-12` is already over its own capacity (risk-load
    7>6, 100min/90min) — do not add a fifth item.
  - `sat-attended:2026-09-19/26` and `2026-10-03` each already carry
    40–45min of other work against a 90min budget; adding this plan's 45min
    would push duration to 85–105min, and none has more than 1–2 points of
    risk-load headroom left for a `high`-risk (3-point) item.
  - **`sun-attended:2026-09-13`** currently holds
    `absenty-drop-npm-runtime` (low, 60min) + `authentik-pg18-lockstep`
    (medium, 35min) = risk-load 3/6, duration 95/150min. Adding this plan
    (high=3, 45min) lands at **risk-load 6/6 exactly** and duration
    140/150min — it fits, but exactly at the risk ceiling, with only 10min
    of time margin. Recommend this slot, but flag to the window agent that
    it is tight and no further item should be added to that date.
  - `sun-attended:2026-09-27` is the Talos node-reboot window
    (`talos-1.14.0`, high, 140/150min) — already full, do not add anything.
  This plan intentionally leaves `window: null` rather than force a fit; the
  maintenance-window-agent should confirm the recommendation above still
  holds against the live queue before scheduling.
- **TubeArchivistMetadata plugin compatibility with 12.0 is unverified and
  out of scope for this plan** — flagged for the operator. If no
  12.0-compatible build exists, removing it (§3 step 1, required by upstream)
  is a standing capability loss, not just a migration step, until a
  compatible version is installed or the integration is replaced. This is a
  judgement call for the operator, not something this plan should silently
  resolve.
- **Biggest gotcha for the executor**: do not accept "pod Ready" or "new
  digest" as success, and do not accept a bare `git revert` as "rolled back".
  The failure this bump can actually produce is a perfectly healthy pod
  serving a migrated-forward, now-incompatible database to a reverted
  binary — §4.2/§4.3's real API calls are what catch a migration that
  silently dropped or hid library items, and §6's restore-then-verify is the
  only rollback that is actually a rollback.
