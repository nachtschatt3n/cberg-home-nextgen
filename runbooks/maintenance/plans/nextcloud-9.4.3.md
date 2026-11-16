---
plan_id: nextcloud-9.4.3
component: nextcloud
pr: 526                               # Renovate PR for the CHART leg (now reads 9.4.1 -> 9.4.4, 1 line; re-read 2026-11-16). The IMAGE leg
                                      # has its own Renovate PR #535 (35.0.2 -> 35.0.3, the same three lines and the same digest 8a7a65b8 as
                                      # step 3.3). This plan lands both legs in ONE commit and closes #526 and #535 after 3.3. PR #406 is the
                                      # same-tag 35.0.2 digest refresh and is made moot by this plan (section 6). plan_id/file name keep
                                      # "9.4.3" on purpose: other plans reference it; the chart target is 9.4.4.
kind: chart                           # group of three members moved in ONE commit: chart + server image + notify-push image
current: "chart 9.4.1 + image nextcloud:35.0.2@sha256:e0b1a2af52c82c07b7a0e8e59878bd8769e704447734d5d238a836982f51b9c8 (app, worker, cron, notify-push)"
target: "chart 9.4.4 + image nextcloud:35.0.3@sha256:8a7a65b8bae82a79568fec2ed9cf3e374a1944eda2a22ebe130d79463336fee3 (app, worker, cron, notify-push)"
update_type: patch                    # chart patch (metadata-only, measured 1.2) + server patch 35.0.2 -> 35.0.3 (same major, same PHP 8.5.12)
risk: medium                          # The chart leg is a no-op. The image leg is NOT: OC_Version 35,0,2,2 -> 35,0,3,2 makes the entrypoint
                                      # rsync core onto the PVC and run `occ upgrade` (forward-only DB migrations, appstore app swaps) on the
                                      # household file/mail/calendar server. A patch, with a rehearsed recovery path, hence medium not high;
                                      # rollback is backup-restore, which keeps it human-gated whatever the risk word says.
est_duration_min: 95                  # pre-checks+baseline 15, dump+config tar+snapshots 10, app pre-drain + Mail gate 15, bump roll (rsync ~5 +
                                      # occ upgrade) 15, gates 15, close-out commit + second roll 10, settle 15. Does NOT fit sat-attended
                                      # (70 usable) or nightly: needs sun-attended (180 usable) or an on-demand NOW run.
needs_reboot: false
touches:
  namespaces: [office, storage]       # storage: two Longhorn Snapshot objects created in 2.6 (backup artifacts only)
  resources:
    - helmrelease/nextcloud                    # chart version, values.image.tag, worker sidecar image, TEMPORARY remediation + startupProbe values
    - deployment/nextcloud                     # Recreate; restarted TWICE (bump commit, close-out commit). ~8-15 min outage on the first, ~4 on the second
    - deployment/nextcloud-notify-push         # image line; RollingUpdate
    - cronjob/nextcloud-cron                   # image from values.image.tag; also label-only chart change
    - deployment/nextcloud-metrics             # chart label change on the object metadata only; pod NOT restarted (measured 1.2)
    - pvc/nextcloud-config                     # WRITTEN: core rsync + version.php + config.php + custom_apps (app pre-drain and occ upgrade)
    - statefulset/nextcloud-mariadb            # NOT restarted (pod template label is the subchart's mariadb-20.5.5, unchanged); DB WRITTEN one-way by occ upgrade
    - pvc/nextcloud-mariadb
    - pvc/nextcloud-data                       # CIFS cifs-nextcloud-data (severe tier): remounted, read by gates, NO PVC/PV operation anywhere
    - deployment/nextcloud-redis               # READ-ONLY: not restarted, sessions and locks survive
    - snapshot.longhorn.io/nextcloud-config-pre-35-0-3     # new, ns storage (2.6)
    - snapshot.longhorn.io/nextcloud-mariadb-pre-35-0-3    # new, ns storage (2.6)
  shared: [envoy-external, cifs/nextcloud-data, storage/longhorn, monitoring]   # envoy-external: public hostname 503 during both rolls, edge gates read through it.
                                                                                # storage/longhorn: snapshots + the rollback revert. monitoring: G8 reads Prometheus,
                                                                                # 2.7 posts a namespace-wide Alertmanager silence for office.
depends_on: []
conflicts_with:
  - nextcloud-35.0.2-digest-d88929d    # same three image lines; this plan makes it moot (section 6). Never the same window
  - nextcloud-12.0.2                   # MariaDB sidecar major under this app: never while an occ upgrade writes the same DB
  - bitnamilegacy-exit-nextcloud-db    # blocked; replaces the DB and edits the same HelmRelease
  - nextcloud-mcp-0.203.0              # Nextcloud clients whose own gates read Nextcloud
  - nextcloud-mcp-0.204.0
  - nextcloud-mcp-0.206.0
  - nextcloud-mcp-0.211.1
  - redis-fleet-8.10.3                 # restarts nextcloud-redis (sessions, file locks) - never during an upgrade
  - postgres-digest-refresh-2026-11    # office restarts; 2.7 silence is namespace-wide and would hide their alerts
  - postgres-fleet-18.7-bookworm       # touches namespace office (same reason)
  - kube-prometheus-stack-93.3.0      # draft, exclusive, window null: restarts Prometheus, which this plan's gates read (retargeted 2026-11-16 from retired 92.22.0)
  - longhorn-1.13.0                    # snapshots (2.6) and the 5.3 revert need a stable Longhorn
  - talos-linux-1.14.5                 # node reboot under a pod that is mid occ upgrade = the stuck-maintenance case
  - talos-linux-1.14.6                 # node roll (exclusive, supersedes 1.14.5 draft): same stuck-maintenance risk.
  - envoy-gateway-1.10.0               # edge gates (status.php, /login) read through envoy-external
  - envoy-proxy-config-distroless-v1.40.0
  - envoy-proxy-config-distroless-v1.40.2
  - coredns-1.50.5                     # occ upgrade downloads apps from the appstore and Mail gates talk IMAP: both need DNS
  - flux-oci-chart-sources             # re-sources every HelmRelease chart
  - helm-drift-detection
  - flux-reconciler-impersonation
  - etcd-timeouts-5000-500
exclusive: false
security_ref: F-2a75fae0              # citation only: the open security finding for the nextcloud:35.0.2 image (severity critical, 'newer upstream tag available, bump the image'); the 35.0.3 leg of this plan is its remedy. Detail is DB-only. Close it after the post-window sweep stops seeing the 35.0.2 tag, not from this plan.
capability_change: false              # same-behaviour patch on both legs. The app updates taken in 3.2 are appstore patch/minor releases
                                      # under the operator's standing "always take app updates" rule, not a capability this plan introduces
rollback_class: backup-restore        # entrypoint refuses an older image on newer data (lines 184-186); DB migrations are forward-only.
                                      # No backup_gate named => HUMAN-GATED, which is what the deny rule asks for
finding_refs: [F-45b00114, F-e39c0b2c, F-4a9d6631]   # version findings: chart (re-queried 2026-11-16: now titled 9.4.1 -> 9.4.4, status unchanged), nextcloud image, notify-push image
review: ready-for-go@2026-11-16
status: vetted
window: null                          # requested: sun-attended, or an operator-triggered NOW run. Not nightly, not sat-attended (duration)
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-14"
premises:
  # Run from the REPO ROOT. All PASS-shaped as measured 2026-11-14; each fails when the state drifts.
  - id: chart-is-9.4.1
    why: The plan moves the chart 9.4.1 -> 9.4.4. Any other value means someone merged #526 or the chart moved again.
    run: kubectl get helmrelease nextcloud -n office -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "9.4.1"
  - id: live-image-is-35.0.2
    why: >-
      Baseline is server 35.0.2 at ANY digest (the digest-refresh plan may have run first, which is fine: step 3.3 rewrites by regex).
      35.0.3 already live means the plan is moot; anything else means the baseline in section 1 is not today's.
    run: kubectl get deployment nextcloud -n office -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "nextcloud:35.0.2@sha256:"
  - id: manifests-have-three-35.0.2-pins
    why: Step 3.3 must rewrite exactly 2 lines in helmrelease.yaml and 1 in notify-push.yaml. Another count means a new consumer or a moved pin.
    run: grep -h -c -e '35\.0\.2@sha256:' kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml
    expect_matches: '(?s)^2\s+1$'
  - id: no-temporary-block-left-behind
    why: A previous run's TEMPORARY remediation/startupProbe block still in the file would make the step 3.3 anchor edit fail or double up.
    run: grep -c 'TEMPORARY (plan' kubernetes/apps/office/nextcloud/app/helmrelease.yaml
    expect_exact: "0"
  - id: startup-probe-threshold-is-10
    why: Step 3.3 raises it to 50 for the upgrade and 3.6 restores 10. A different live value means the probe budget argument in 1.4 is wrong.
    run: kubectl get deployment nextcloud -n office -o jsonpath='{.spec.template.spec.containers[0].startupProbe.failureThreshold}'
    expect_exact: "10"
  - id: strategy-is-recreate
    why: Old and new app pods must never write the config volume together (two entrypoints rsyncing /var/www/html).
    run: kubectl get deployment nextcloud -n office -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: app-pod-ready-both-containers
    why: Pre-state is a settled pod. occ-level state (version, maintenance, Mail) needs kubectl exec, which the runner refuses - that is pre-check 2.1.
    run: kubectl get pods -n office -l app.kubernetes.io/component=app -o jsonpath='{.items[*].status.containerStatuses[*].ready}'
    expect_exact: "true true"
  - id: nextcloud-config-volume-healthy
    why: Core, apps and config live here; snapshot 2.6 and rollback 5.3 depend on it.
    run: kubectl get volumes.longhorn.io nextcloud-config -n storage -o jsonpath='{.status.robustness}'
    expect_exact: "healthy"
  - id: nextcloud-mariadb-volume-healthy
    why: The DB is written one-way by occ upgrade; dump 2.5 and snapshot 2.6 depend on it.
    run: kubectl get volumes.longhorn.io nextcloud-mariadb -n storage -o jsonpath='{.status.robustness}'
    expect_exact: "healthy"
  - id: sidecar-still-11.8.3
    why: The MariaDB sidecar is out of scope. If it moved, the dump/restore commands in 2.5 and 5.3 must be re-checked.
    run: kubectl get statefulset nextcloud-mariadb -n office -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "bitnamilegacy/mariadb:11.8.3@sha256:ada2a782"
---

# nextcloud-9.4.3 - Nextcloud chart 9.4.1 -> 9.4.4 and server 35.0.2 -> 35.0.3 (app, worker, cron, notify-push) in lockstep

## 1. Summary & why held

### 1.1 What moves (one commit, three members)

| Member | File / line | From | To |
|---|---|---|---|
| chart `nextcloud` | `kubernetes/apps/office/nextcloud/app/helmrelease.yaml` line 11 | 9.4.1 | 9.4.4 |
| image `nextcloud` (main container + `nextcloud-cron`) | same file, line 34 `values.image.tag` | `35.0.2@sha256:e0b1a2af...` | `35.0.3@sha256:8a7a65b8...` |
| image `nextcloud` (`worker` sidecar) | same file, line 234 | same | same |
| image `nextcloud` (`nextcloud-notify-push`) | `kubernetes/apps/office/nextcloud/app/notify-push.yaml` line 40 | same | same |

**Why held:** the `*nextcloud*` deny rule in `runbooks/auto-update-policy.yaml`: "chart+image must bump together and run occ migrations (Mail custom_app /
stuck-maintenance trap) - operator-supervised only." For this group the reason is TRUE for the image leg (1.3) and not for the chart leg (1.2).
Standing operator policy: always take app updates, Mail working afterwards is the hard gate, chart and image go to the newest together.

### 1.2 Chart 9.4.1 -> 9.4.4: every intermediate exists, the change is metadata-only with our values (measured 2026-11-14 for 9.4.3, 2026-11-16 for 9.4.4)

- `https://nextcloud.github.io/helm/index.yaml`: 9.4.2 (2026-11-12T21:35Z) and 9.4.3 (2026-11-12T21:50Z) exist. **Both still carry `appVersion: 35.0.2`** - no
  chart carries 35.0.3 yet. 9.4.3 was then the newest chart (superseded by 9.4.4, see the retarget bullet below, also appVersion 35.0.2), so "newest chart + newest image" is the lockstep shape; `image.tag` is pinned in our values,
  so appVersion is never used for the image. Subchart pins unchanged (mariadb 20.5.5, redis 21.1.3, postgresql 16.7.4, collabora-online 1.1.60).
- Release notes. 9.4.2: CI action bumps plus "bump xperimental/nextcloud-exporter from 0.9.1 to 0.9.2" (helm#898). 9.4.3: "chore(docs): correct defaults and
  mislabelled externalRedis keys in README" (helm#902). `gh api repos/nextcloud/helm/compare/nextcloud-9.4.1...nextcloud-9.4.3` touches only
  `Chart.yaml` (+1 -1), `README.md`, `values.yaml` (+1 -1: the exporter default tag) and two workflow files. **No template changed.**
- Unpacked-tarball diff 9.4.1 vs 9.4.3: `Chart.yaml` version, README, `values.yaml` line 996 `tag: 0.9.1 -> 0.9.2`. We already pin the exporter to 0.9.2 in our values.
- `helm template` of both charts with OUR values: 1446 lines each, the diff is **14 lines = `helm.sh/chart: nextcloud-9.4.1 -> 9.4.3` on 7 objects**, none inside a
  pod template (Deployment `nextcloud`, Deployment `nextcloud-metrics`, CronJob `nextcloud-cron`: label absent from the pod template; StatefulSet
  `nextcloud-mariadb` pod template carries the SUBCHART label `mariadb-20.5.5`, unchanged, and the live pod shows the same). So the chart leg restarts nothing.
- **Retarget 2026-11-16: chart 9.4.4 is now the newest** (index.yaml: `version: 9.4.4` present, no 9.4.5; `appVersion: 35.0.2`). Upstream 9.4.3 -> 9.4.4
  touches only `Chart.lock`/`Chart.yaml`: "update collabora-online to 1.3.8 (#906)" (subchart pin 1.1.60 -> 1.3.8). The subchart is gated by
  `collabora.enabled`, chart default `false`, and our values do not set it. Measured with `helm template nextcloud nextcloud/nextcloud -n office -f <our
  spec.values>` for 9.4.1, 9.4.3 and 9.4.4: all three render 1446 lines and **zero collabora objects** (`grep -c -i collabora` = 0 on the 9.4.4 render);
  diff 9.4.1 -> 9.4.4 = exactly the same 14 lines as before (`helm.sh/chart: nextcloud-9.4.1 -> 9.4.4` on 7 objects); diff 9.4.3 -> 9.4.4 = the same 7
  label pairs only. **The collabora bump changes no rendered object**; the chart leg still restarts nothing.
- PR #526: OPEN, one file, one line, now titled `update nextcloud ( 9.4.1 → 9.4.4 )` (`gh pr diff 526`: `-version: 9.4.1` / `+version: 9.4.4`, 2026-11-16).
- PR #535 (opened by Renovate after this plan was first drafted): OPEN, `update nextcloud ( 35.0.2 → 35.0.3 )`, the same three image lines as step 3.3 with
  the same digest `8a7a65b8...` (`gh pr diff 535`, 2026-11-16). Merging either PR alone splits the lockstep; 3.3 carries both and closes both.

### 1.3 Image 35.0.2 -> 35.0.3: the tag exists and `occ upgrade` WILL run (measured against the registry 2026-11-14)

| | LIVE `35.0.2@e0b1a2af` | TARGET `35.0.3@8a7a65b8` |
|---|---|---|
| amd64 manifest | `c73d6b4ada51...` | `f5a6d4827685...` |
| image created | 2026-10-28T02:38Z | 2026-11-13T22:16Z |
| `NEXTCLOUD_VERSION` / `PHP_VERSION` | 35.0.2 / 8.5.12 | 35.0.3 / 8.5.12 |
| `/usr/src/nextcloud/version.php` | `array(35,0,2,2)` (also the installed version on the PVC) | `array(35,0,3,2)`, `OC_Build 2026-11-12T14:11:48+00:00 7764ef49...`, `OC_VersionCanBeUpgradedFrom 'nextcloud' => '35.0' => true` |

The version.php of the target was read by streaming the 276 MB source layer (`b9f7209b05d2`) of the amd64 manifest. Upstream release `v35.0.3` exists
(`nextcloud/server`, published 2026-11-12T13:14Z, not a pre-release; changelog on `nextcloud-releases/server`). Tag `35.0` resolves to a different index digest
(`8041f246...`) with the SAME amd64 manifest: the multi-arch index was still settling on 2026-11-14, hence the re-resolve in pre-check 2.2.

The live entrypoint (`/entrypoint.sh` in the running pod): line 189 `if version_greater "$image_version" "$installed_version"` -> line 206 `rsync ... --delete
--exclude-from=/upgrade.exclude /usr/src/nextcloud/ /var/www/html/` (excludes `/config/ /data/ /custom_apps/ /themes/ /version.php`), line 212 copies
`version.php` LAST, line 294 `occ upgrade`. Lines 184-186 refuse to start an image OLDER than the data. So after this bump a `git revert` alone crash-loops.

What 35.0.3 migrates (quotes from the upstream changelog, 198 PRs, all fixes): "Fix(migration): check if deleted_by column exists before trying to add it to
files_trash table (server#65518)", "Fix: Remove auto increment migration on share_external (server#65711)", "Fix: move column drop in to separate migration
(server#65719)", "Fix(sharing): Add names to new indexes (server#66386)", "Fix: add files_metadata_index to the filecache partition (server#65414)",
"Perf(activity): reintroduce activity_object index (activity#3021)". No breaking-change or manual-step note; no PHP or DB requirement change. So expect the
`oc_migrations` count to grow from 570 and index work on `oc_filecache`-family tables; nothing that needs an operator decision.

### 1.4 The three traps this plan defuses (all seen on this instance)

1. **`occ upgrade` swaps appstore apps, including Mail.** Live `lib/private/Updater.php` line 260 calls `upgradeAppStoreApps($this->appManager->getEnabledApps())`
   and line 401 updates every enabled app for which `isUpdateAvailable`. Pending today (`occ update:check`): mail 5.13.2, assistant 4.1.0, calendar 6.6.5,
   contacts 8.10.0, context_chat 5.6.0, drawio 4.3.11, richdocuments 12.0.2, richdocumentscode 26.4.502, spreed 25.0.8. Left alone, Mail would be replaced INSIDE
   the core upgrade - the 2026-06-06 failure (incomplete `mail/vendor/`, every `occ` and cron pod dead, `status.php` still 200). **Defusal: step 3.2 takes the app
   updates first, on 35.0.2, and gates Mail before the image moves**, so a Mail failure is attributable and cheap.
2. **Startup probe vs rsync + `occ upgrade`.** startupProbe = 60 s + 10 x 30 s = 360 s. On 2026-09-26 a patch upgrade's rsync alone took ~289 s and the probe
   killed the container inside `occ upgrade` - that is how maintenance mode sticks. **Defusal: the bump commit temporarily sets `startupProbe.failureThreshold: 50`**
   (60 + 50 x 30 = 1560 s, below the HelmRelease `timeout: 30m`), restored in 3.6. Same shape as the executed 35.0.2 rollout (`6fe988f4` / `d2e9a100`).
3. **Flux remediation vs a half-run upgrade.** With `retries: 3` a timed-out upgrade is rolled back to the 35.0.2 image on 35.0.3 data, which the entrypoint
   refuses. **Defusal: `upgrade.remediation.retries: 0` + `remediateLastFailure: false` for the attempt**, restored in 3.6.

Not a trap here: no enabled app declares a `max-version` below 35 (scanned every `custom_apps/*/appinfo/info.xml` live; Mail declares `min 32 max 35`), so the
"force-enabled app silently re-disabled" hazard has no target on a 35.0.x patch. It is still gated (G3).

### 1.5 Live baseline (read-only, 2026-11-14)

| Fact | Value |
|---|---|
| HelmRelease | chart 9.4.1, Helm revision 61, Ready True |
| `occ status` | version 35.0.2.2, maintenance false, needsDbUpgrade false |
| pod | `nextcloud` 2/2 (containers `nextcloud` + `worker`), 0 restarts; strategy Recreate; initContainers `wait-for-mariadb`, `wait-for-redis`, `install-openclaw-mail`, `mariadb-isalive` |
| apps | 69 enabled / 9 disabled; mail 5.13.1, calendar 6.6.4, contacts 8.9.5, whiteboard 2.1.2, google_synchronization 4.3.2, notify_push 1.4.2, richdocuments 12.0.1, openclaw_mail 0.1.0, spreed 25.0.6, assistant 4.0.0 |
| Mail | 3 accounts; mailboxes 10 / 9 / 12 = 31 (occ and DB agree); `mail:account:diagnose 1` ends `IMAP connection test passed`, rc 0; `mail/vendor/autoload.php` loads |
| DB (11.8.3) | 214 tables; `oc_migrations` 570, `oc_filecache` 35059, `oc_mail_messages` 54084, `oc_calendarobjects` 2906 |
| Longhorn | `nextcloud-config` and `nextcloud-mariadb` healthy, lastBackupAt 2026-11-13T23:00Z (CronJob `storage/daily-backup-all-volumes`, `0 23 * * *`) |
| Prometheus | `nextcloud_up` 1, `up{job="nextcloud-metrics"}` 1, `nextcloud_files_total` 35059, `nextcloud_users_total` 3 |

Mailbox and message counts drift with normal use: the SAME-DAY snapshot (2.4) is the baseline, never this table. Carried from the digest-refresh draft, not
re-measured by me: `google_synchronization` has had no background jobs and an expired token since 2026-11-04 (pre-existing, operator click needed; not gated).

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). `occ` is always called in the direct form `kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ ...`
(never through an `$OCC` variable: zsh does not word-split it). All working files live in a mode-700 directory outside the repo:

```sh
umask 077; X=~/db-dumps/nextcloud-9.4.3-exec; mkdir -p $X; chmod 700 $X
```

**2.1 Nothing in flight, instance healthy.**
```sh
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ status        # EXPECT versionstring 35.0.2, maintenance false, needsDbUpgrade false
flux get helmrelease nextcloud -n office                                       # EXPECT READY True, 9.4.1
kubectl get pods -n office | grep -i nextcloud                                 # app 2/2 Running; cron pods Completed, none Error
git status --short kubernetes/apps/office/nextcloud                            # EXPECT empty (no other session mid-edit on these files)
```
ABORT on maintenance true, needsDbUpgrade true, any cron pod in `Error`, or a dirty file.

**2.2 Upstream targets still what section 1 measured** (network reads; deliberately not premises).
```sh
curl -s --max-time 30 https://nextcloud.github.io/helm/index.yaml | grep -c -e '^    version: 9\.4\.4$'      # EXPECT 1 (0 = chart withdrawn: STOP)
curl -s --max-time 30 https://nextcloud.github.io/helm/index.yaml | grep -c -e '^    version: 9\.4\.5$'      # EXPECT 0 (1 = newer chart: re-review, lockstep goes to NEWEST)
curl -s --max-time 20 "https://hub.docker.com/v2/repositories/library/nextcloud/tags/35.0.3" | python3 -c "import sys,json; print(json.load(sys.stdin)['digest'])"
#   EXPECT sha256:8a7a65b8bae82a79568fec2ed9cf3e374a1944eda2a22ebe130d79463336fee3 (re-read 2026-11-16: unchanged; tag 35.0.4 404)
gh pr view 526 --json state,title,files --jq '.state, .title, ([.files[].path]|join(" "))'
#   EXPECT OPEN / fix(helm): update nextcloud ( 9.4.1 → 9.4.4 ) / kubernetes/apps/office/nextcloud/app/helmrelease.yaml
gh pr view 535 --json state,title,files --jq '.state, .title, ([.files[].path]|join(" "))'
#   EXPECT OPEN / fix(container): update nextcloud ( 35.0.2 → 35.0.3 ) / .../helmrelease.yaml .../notify-push.yaml
gh pr diff 535 | grep -c '^+.*35\.0\.3@sha256:8a7a65b8'                        # EXPECT 3 (same digest as 3.3; another digest => use it per the next paragraph)
```
If the tag now resolves to a DIFFERENT digest (upstream rebuilt it, as happened twice with 35.0.2): use the new digest in 3.3, and before doing so re-read its
bundled `version.php` with the registry script in `nextcloud-35.0.2-digest-d88929d.md` pre-check 2.2 (tag/digest swapped). PASS only if it prints
`OC_Version = array(35,0,3,` - a `35,0,4` or `36,` array is a different upgrade and this plan must be re-reviewed. Renovate's image PR #535 exists; close it
(and #526) after 3.3 lands - this plan does the four lines by hand so that chart and image move in ONE commit.

**2.3 Longhorn backups fresh (floor) + negative control.**
```sh
python3 runbooks/longhorn-backup-age.py nextcloud-config nextcloud-mariadb --max-hours 26     # EXPECT exit 0, both FRESH
python3 runbooks/longhorn-backup-age.py nextcloud-config nextcloud-mariadb --max-hours 0.1    # CONTROL: EXPECT exit 1 (both STALE)
```
Not FRESH: wait for CronJob `storage/daily-backup-all-volumes` (23:00 UTC) per `docs/sops/backup.md`. Do not proceed on STALE.

**2.4 Gate tooling + same-day baseline.** Write the gate (logic fixture-tested 2026-11-14: pre-vs-pre PASS; wrong version, maintenance on, Mail disabled, an
account at 0 mailboxes, a lost mailbox row and an unloadable occ each print `FAIL` and return 1):

```sh
cat > $X/nc_gate.py <<'PY'
import json, os, re, sys
pre, post, ver = sys.argv[1:4]
bad = []
def rd(d, f):
    p = os.path.join(d, f)
    return open(p).read() if os.path.exists(p) else ""
st = rd(post, "status.txt")
for pat in (r"versionstring: %s\s*$" % re.escape(ver), r"needsDbUpgrade: false", r"maintenance: false"):
    if not re.search(pat, st, re.M):
        bad.append("status.txt lacks /%s/ (an EMPTY status.txt means occ itself cannot load)" % pat)
def apps(d):
    try:
        return json.loads(rd(d, "apps.json"))
    except ValueError:
        return None
a, b = apps(pre), apps(post)
if not a or not b or not a.get("enabled") or not b.get("enabled"):
    bad.append("apps.json unreadable or empty (occ app:list failed)")
else:
    for k in ("enabled", "disabled"):
        lost, new = sorted(set(a[k]) - set(b[k])), sorted(set(b[k]) - set(a[k]))
        if lost or new:
            bad.append("%s app SET changed: lost=%s new=%s" % (k, lost, new))
    for app in ("mail", "calendar", "contacts", "google_synchronization", "notify_push", "whiteboard", "openclaw_mail"):
        if app not in b["enabled"]:
            bad.append("app %s is not enabled" % app)
    for app in sorted(set(a["enabled"]) & set(b["enabled"])):
        if a["enabled"][app] != b["enabled"][app]:
            print("INFO app version moved: %s %s -> %s" % (app, a["enabled"][app], b["enabled"][app]))
for f in ("mailboxes.txt", "cals.txt"):
    x, y = rd(pre, f), rd(post, f)
    if not x.strip() or not y.strip():
        bad.append("%s empty" % f)
    elif x != y:
        bad.append("%s differs: %r -> %r" % (f, x.split(), y.split()))
    if f == "mailboxes.txt" and re.search(r"mailboxes=0\b", y):
        bad.append("an account lists 0 mailboxes")
def db(d):
    return {l.split("\t")[0]: int(l.split("\t")[1]) for l in rd(d, "db.txt").splitlines() if "\t" in l}
x, y = db(pre), db(post)
if len(x) != 6 or len(y) != 6:
    bad.append("db.txt incomplete (mariadb unreadable): %d/%d rows" % (len(x), len(y)))
else:
    for k in ("mail_accounts", "mail_mailboxes"):
        if x[k] != y[k]:
            bad.append("db %s: %d -> %d (must be EXACT)" % (k, x[k], y[k]))
    for k in ("filecache", "mail_messages", "calendarobjects", "migrations"):
        if y[k] < x[k]:
            bad.append("db %s shrank: %d -> %d" % (k, x[k], y[k]))
    print("INFO migrations %d -> %d" % (x["migrations"], y["migrations"]))
for m in bad:
    print("FAIL " + m)
print("GATE FAIL" if bad else "GATE PASS")
sys.exit(1 if bad else 0)
PY
nc_snap() {
  d="$1"; mkdir -p "$d"
  kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ status 2>/dev/null > "$d/status.txt"
  kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ app:list --output=json 2>/dev/null > "$d/apps.json"
  for n in 1 2 3; do echo "acct$n mailboxes=$(kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ mail:mailbox:list $n 2>/dev/null | grep -c '^| [0-9]')"; done > "$d/mailboxes.txt"
  kubectl exec deploy/nextcloud -n office -c nextcloud -- sh -c 'for u in $(php occ user:list --output=json | php -r "echo implode(\" \", array_keys(json_decode(stream_get_contents(STDIN),true)));"); do echo "cals=$(php occ dav:list-calendars $u | awk "/^\\| /{n++} END{print n-1}")"; done | sort' 2>/dev/null > "$d/cals.txt"
  kubectl exec nextcloud-mariadb-0 -n office -c mariadb -- sh -c 'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -e "select \"filecache\",count(*) from nextcloud.oc_filecache union all select \"mail_accounts\",count(*) from nextcloud.oc_mail_accounts union all select \"mail_mailboxes\",count(*) from nextcloud.oc_mail_mailboxes union all select \"mail_messages\",count(*) from nextcloud.oc_mail_messages union all select \"calendarobjects\",count(*) from nextcloud.oc_calendarobjects union all select \"migrations\",count(*) from nextcloud.oc_migrations"' 2>/dev/null > "$d/db.txt"
}
nc_snap $X/pre; cat $X/pre/mailboxes.txt $X/pre/cals.txt $X/pre/db.txt
python3 $X/nc_gate.py $X/pre $X/pre 35.0.2; echo "positive control rc=$?"       # EXPECT GATE PASS, rc=0
python3 $X/nc_gate.py $X/pre $X/pre 35.0.3; echo "negative control rc=$?"       # EXPECT one FAIL (versionstring) + GATE FAIL, rc=1
```
EXPECT today: `acct1 mailboxes=10 / acct2 9 / acct3 12`, three `cals=` lines, six db rows (`mail_accounts 3`, `mail_mailboxes 31`, `migrations 570`).
Do not continue if the negative control returns 0 (the gate is blind) or the positive control returns 1 (the snapshot is incomplete: a `nc_snap` reader failed).
The mailbox loop, the DB query, `occ status` and `app:list --output=json` were run live by me on 2026-11-14; the `cals.txt` one-liner is copied from the
digest-refresh draft (its author ran it 2026-11-09) and was NOT re-run by me - if `cals.txt` comes out empty the gate says so (`cals.txt empty`).

Mail-specific baseline (the hard gate's own instruments must exist before anything changes):
```sh
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ list mail | grep -c -E '^ +mail:(mailbox:list|account:sync|account:diagnose) '   # EXPECT 3
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ mail:account:diagnose 1 | grep -c -i 'IMAP connection test passed'               # EXPECT 1
kubectl exec deploy/nextcloud -n office -c nextcloud -- php -r 'require "/var/www/html/custom_apps/mail/vendor/autoload.php"; echo "MAIL_AUTOLOAD_OK\n";'   # EXPECT MAIL_AUTOLOAD_OK
kubectl exec deploy/nextcloud -n office -c nextcloud -- php -r 'require "/var/www/html/custom_apps/mail/vendor/nope/autoload.php"; echo "MAIL_AUTOLOAD_OK\n";' ; echo "CONTROL rc=$?"
#   CONTROL: EXPECT a PHP fatal "Failed opening required" and rc=255 (measured) - this is what the incomplete-vendor failure prints
```

**2.5 DB dump + config tar (the restore points for 5.3).** `--default-character-set=utf8mb4` is load-bearing (tables are `utf8mb4_bin`).
```sh
kubectl exec nextcloud-mariadb-0 -n office -c mariadb -- sh -c 'mariadb-dump -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" --default-character-set=utf8mb4 --single-transaction --routines --events --triggers --databases nextcloud' > $X/nextcloud-pre-35.0.3.sql
tail -c 200 $X/nextcloud-pre-35.0.3.sql | grep -c 'Dump completed'                 # EXPECT 1 (a truncated dump has no trailer)
grep -c '^CREATE TABLE' $X/nextcloud-pre-35.0.3.sql                                # EXPECT 214
ls -l $X/nextcloud-pre-35.0.3.sql | awk '{print ($5 > 100000000) ? "SIZE_OK" : "SIZE_TOO_SMALL"}'   # EXPECT SIZE_OK (~1 GB DB)
kubectl exec deploy/nextcloud -n office -c nextcloud -- tar cf - -C /var/www/html config > $X/config-pre-35.0.3.tar
tar tf $X/config-pre-35.0.3.tar | grep -c -E '^config/(config|custom\.config)\.php$'                 # EXPECT 2
tar xOf $X/config-pre-35.0.3.tar config/config.php | grep -c "'version' => '35\.0\.2"                # EXPECT 1 (the archive is the 35.0.2 config)
```
Any EXPECT missed => no usable restore point: ABORT. Both files hold application data and secrets: never into the repo, deleted at close-out.

**2.6 Longhorn snapshots (same-day fast path for 5.3).** Backup artifacts only; same procedure the executed 35.0.2 rollout used.
```sh
for V in nextcloud-config nextcloud-mariadb; do kubectl apply -f - <<EOF
apiVersion: longhorn.io/v1beta2
kind: Snapshot
metadata:
  name: ${V}-pre-35-0-3
  namespace: storage
spec:
  volume: ${V}
  createSnapshot: true
EOF
done
sleep 10
kubectl get snapshots.longhorn.io nextcloud-config-pre-35-0-3 nextcloud-mariadb-pre-35-0-3 -n storage -o custom-columns=NAME:.metadata.name,READY:.status.readyToUse
```
EXPECT `true` on both. False/empty => 5.3 has no fast path (only the 23:00 backup): operator decides whether to continue. Take these BEFORE 3.2 so they also
predate the app pre-drain and stay consistent with the 2.5 dump.

**2.7 Active-update marker + silence** (`docs/sops/application-update.md` step 1; 4 h TTL).
```sh
runbooks/update-marker.sh add nextcloud office 4 "35.0.2->35.0.3 + chart 9.4.4 (plan nextcloud-9.4.3)"
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 19093:9093 >/dev/null 2>&1 & PF=$!; sleep 3
python3 - <<'PY' > $X/silence.json
import json, urllib.request
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc); f = "%Y-%m-%dT%H:%M:%S.000Z"
body = {"matchers": [{"name": "namespace", "value": "office", "isRegex": False, "isEqual": True}], "startsAt": now.strftime(f),
        "endsAt": (now + timedelta(hours=4)).strftime(f), "createdBy": "maintenance-window-agent",
        "comment": "nextcloud 35.0.2->35.0.3 (plan nextcloud-9.4.3). auto-expires 4h"}
r = urllib.request.Request("http://localhost:19093/api/v2/silences", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
print(urllib.request.urlopen(r).read().decode())
PY
python3 -c "import json,sys; print('silenceID', json.load(open(sys.argv[1]))['silenceID'])" $X/silence.json      # KeyError / traceback => NOT silenced: fix before going on
kill $PF 2>/dev/null
```
(`$X` is unset inside the quoted heredoc on purpose: the Python block writes to stdout and the shell redirects it.) The silence is namespace-wide, which is
why every other `office` plan is in `conflicts_with`. This POST block is adapted from the SOP and the executed 35.0.2 plan and was NOT dry-run by me.

## 3. Steps

**3.1 Go/no-go.** All premises PASS, 2.1-2.7 clean, operator present (attended window or NOW run). Otherwise STOP.

**3.2 App pre-drain on 35.0.2, then the Mail gate (before the image moves).** Appstore app state lives on the `nextcloud-config` volume + DB and has no GitOps
path (no ConfigMap or repo file projects `custom_apps/<appstore app>`), so in-pod `occ` is the only route; it is covered by 2.5/2.6, taken first.
```sh
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ app:update --showonly        # EXPECT today: the 9 apps in 1.4 (drift is fine). EMPTY => already drained, go to the gate
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ app:update --all > $X/predrain.txt 2>&1; echo "app:update rc=$?"; cat $X/predrain.txt
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ app:update --showonly | wc -l  # EXPECT 0 lines left
nc_snap $X/predrain; python3 $X/nc_gate.py $X/pre $X/predrain 35.0.2; echo "predrain gate rc=$?"
```
PASS = rc 0, `GATE PASS`, `INFO app version moved: mail 5.13.1 -> 5.13.2` (or newer) among the INFO lines, enabled/disabled sets unchanged. Then the Mail hard
gate, section 4 **G4** in full, plus the next scheduled cron run:
```sh
date -u +%Y-%m-%dT%H:%M:%SZ > $X/predrain-done.txt       # wait >= 6 min, then:
kubectl get jobs -n office --sort-by=.metadata.creationTimestamp -o custom-columns=NAME:.metadata.name,CREATED:.metadata.creationTimestamp,SUCCEEDED:.status.succeeded,FAILED:.status.failed | grep nextcloud-cron | tail -2
#   PASS: a Job CREATED after predrain-done.txt with SUCCEEDED 1 and FAILED <none>. FAILED >= 1 is the Mail-vendor failure shape: kubectl logs job/<name> -n office
```
HOW IT FAILS: `GATE FAIL`, an autoload error naming `custom_apps/mail`, or a failed cron Job => recover Mail with 5.1 ON 35.0.2 (nothing is migrated yet). If Mail
cannot be made green here, STOP: do not start 3.3 (see 5.4). `$X/predrain` is the baseline for every gate after the bump.

**3.3 The bump commit - chart + three image lines + temporary remediation-off and startup budget.** Work on `main`.
```sh
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main; git merge --ff-only origin/main
NEW='35.0.3@sha256:8a7a65b8bae82a79568fec2ed9cf3e374a1944eda2a22ebe130d79463336fee3'     # or the digest re-resolved in 2.2
sed -i '' -E 's|^      version: 9\.4\.1$|      version: 9.4.4|' kubernetes/apps/office/nextcloud/app/helmrelease.yaml
sed -i '' -E "s|^      tag: 35\.0\.2@sha256:[0-9a-f]{64}$|      tag: $NEW|" kubernetes/apps/office/nextcloud/app/helmrelease.yaml
sed -i '' -E "s|^          image: nextcloud:35\.0\.2@sha256:[0-9a-f]{64}$|          image: nextcloud:$NEW|" kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml
python3 - <<'PY'
p = "kubernetes/apps/office/nextcloud/app/helmrelease.yaml"
s = open(p).read()
a = "  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 3\n"
b = ("  upgrade:\n    cleanupOnFail: true\n    remediation:\n"
     "      retries: 0                 # TEMPORARY (plan nextcloud-9.4.3 step 3.3) - restore 3 in step 3.6\n"
     "      remediateLastFailure: false\n")
c = ("    startupProbe:\n      enabled: true\n      initialDelaySeconds: 60\n      periodSeconds: 30\n"
     "      timeoutSeconds: 5\n      failureThreshold: 10\n")
d = ("    startupProbe:\n      enabled: true\n      initialDelaySeconds: 60\n      periodSeconds: 30\n"
     "      timeoutSeconds: 5\n      failureThreshold: 50               # TEMPORARY (plan nextcloud-9.4.3 step 3.3) - restore 10 in step 3.6\n")
assert s.count(a) == 1 and s.count(c) == 1, ("anchor blocks not found exactly once", s.count(a), s.count(c))
open(p, "w").write(s.replace(a, b, 1).replace(c, d, 1)); print("temporary blocks written")
PY
git diff -- kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml | grep '^[-+][^-+]'
```
EXPECT exactly (dry-run on scratch copies with BSD sed on macOS, 2026-11-14, re-run with the 9.4.4 sed on 2026-11-16 against the current files; the regex
also matches if the digest-refresh plan moved the 35.0.2 digest first):
```
-      version: 9.4.1
+      version: 9.4.4
-      retries: 3
+      retries: 0                 # TEMPORARY (plan nextcloud-9.4.3 step 3.3) - restore 3 in step 3.6
+      remediateLastFailure: false
-      tag: 35.0.2@sha256:e0b1a2af52c82c07b7a0e8e59878bd8769e704447734d5d238a836982f51b9c8
+      tag: 35.0.3@sha256:8a7a65b8bae82a79568fec2ed9cf3e374a1944eda2a22ebe130d79463336fee3
-          image: nextcloud:35.0.2@sha256:e0b1a2af52c82c07b7a0e8e59878bd8769e704447734d5d238a836982f51b9c8
+          image: nextcloud:35.0.3@sha256:8a7a65b8bae82a79568fec2ed9cf3e374a1944eda2a22ebe130d79463336fee3
-      failureThreshold: 10
+      failureThreshold: 50               # TEMPORARY (plan nextcloud-9.4.3 step 3.3) - restore 10 in step 3.6
-          image: nextcloud:35.0.2@sha256:e0b1a2af52c82c07b7a0e8e59878bd8769e704447734d5d238a836982f51b9c8
+          image: nextcloud:35.0.3@sha256:8a7a65b8bae82a79568fec2ed9cf3e374a1944eda2a22ebe130d79463336fee3
```
(`helm template` of chart 9.4.4 with the edited values, 2026-11-16: rc 0; 3 `nextcloud:35.0.3@sha256:8a7a65b8` image lines (app, worker, cron), 0 `35.0.2@`,
`failureThreshold: 50`; against the 9.4.1 render of today's values the only other diff lines are the 14 `helm.sh/chart` labels.) A different diff => `git checkout -- <both files>` and stop. Then:
```sh
grep -c -e '35\.0\.2@sha256' kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml    # EXPECT :0 and :0
printf '%s\n\n%s\n\n%s\n\n%s\n' 'feat(nextcloud): 35.0.2 -> 35.0.3 + chart 9.4.1 -> 9.4.4 lockstep + notify-push (plan nextcloud-9.4.3)' \
  'Chart 9.4.4 renders only helm.sh/chart label changes against 9.4.1 with our values (collabora subchart disabled). Supersedes Renovate PRs #526 and #535. TEMPORARY for this rollout: upgrade.remediation.retries 0 and startupProbe.failureThreshold 50; both restored in the follow-up commit.' \
  'finding_refs: F-45b00114 F-e39c0b2c F-4a9d6631' 'Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>' > $X/msg-bump.txt
git commit --only kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml -F $X/msg-bump.txt
git show --stat HEAD; git log -1 --format=%s        # ONLY the two files; the subject must be THIS one (amend before push if not)
git rev-parse HEAD > $X/bump-sha.txt; git push origin main
```
Then close PR #526 (chart) AND PR #535 (image) with a comment naming the commit - both diffs are contained in it; merging either separately would split
the lockstep, and leaving #535 open lets Renovate rebase it onto a stale base:
```sh
for N in 526 535; do gh pr close $N --comment "Superseded by $(cat $X/bump-sha.txt) (plan nextcloud-9.4.3: chart 9.4.4 + image 35.0.3 in one commit)"; done
gh pr view 526 --json state --jq .state; gh pr view 535 --json state --jq .state      # EXPECT CLOSED / CLOSED
```

**3.4 Watch the rollout (attended).** Recreate: the old pod goes, the new one runs initContainers -> rsync -> `occ upgrade`. Budget 1560 s from container start.
Flux is webhook-driven; do not force a reconcile unless nothing has started after 10 min.
```sh
flux get helmrelease nextcloud -n office
POD=$(kubectl get pod -n office -l app.kubernetes.io/name=nextcloud,app.kubernetes.io/component=app -o jsonpath='{.items[0].metadata.name}')
kubectl logs "$POD" -n office -c nextcloud --timestamps --tail=40
```
Re-issue about every 60 s (bounded reads, no follow). Expected log shape: `Initializing nextcloud 35.0.3.2 ...` / `Upgrading nextcloud from 35.0.2.2 ...` /
`Initializing finished` (rsync done, ~5 min) / `Turned on maintenance mode` / `Updating database schema` / `Updated database` / `Update successful` /
`Turned off maintenance mode`. HOW IT FAILS: a `Disabled incompatible app:` line (none expected on a patch) or a non-empty `The following apps have been
disabled:` => 5.1; still inside `occ upgrade` 22 min after container start => prepare 5.2; do NOT delete the pod, scale, or re-push while it is upgrading.
A HelmRelease that reports Failed on timeout while section 4 is green is NOT a rollback trigger (retries 0: no auto-rollback; 3.6 re-reconciles it).
```sh
kubectl rollout status deploy/nextcloud -n office --timeout=9m                 # re-issue while the log shows progress
kubectl rollout status deploy/nextcloud-notify-push -n office --timeout=5m
```
`rollout status` green is not proof (it can report the old generation): G1 checks the running digest.

**3.5 Verify** - section 4, G1-G8, against `$X/predrain`.

**3.6 Close out (only after section 4 is green).**
```sh
cd /Users/mu/code/cberg-home-nextgen; git fetch origin main; git merge --ff-only origin/main
python3 - <<'PY'
p = "kubernetes/apps/office/nextcloud/app/helmrelease.yaml"
s = open(p).read()
a = ("      retries: 0                 # TEMPORARY (plan nextcloud-9.4.3 step 3.3) - restore 3 in step 3.6\n"
     "      remediateLastFailure: false\n")
c = "      failureThreshold: 50               # TEMPORARY (plan nextcloud-9.4.3 step 3.3) - restore 10 in step 3.6\n"
assert s.count(a) == 1 and s.count(c) == 1, "temporary blocks not found - check by hand"
open(p, "w").write(s.replace(a, "      retries: 3\n", 1).replace(c, "      failureThreshold: 10\n", 1)); print("restored retries 3 + startup failureThreshold 10")
PY
grep -c 'TEMPORARY (plan' kubernetes/apps/office/nextcloud/app/helmrelease.yaml          # EXPECT 0
git diff -- kubernetes/apps/office/nextcloud/app/helmrelease.yaml | grep -c '^[-+] '      # EXPECT 5 (3 removed + 2 added)
printf '%s\n\n%s\n' 'chore(nextcloud): restore remediation retries 3 + startupProbe 10 after the 35.0.3 rollout (plan nextcloud-9.4.3 step 3.6)' 'Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>' > $X/msg-close.txt
git commit --only kubernetes/apps/office/nextcloud/app/helmrelease.yaml -F $X/msg-close.txt
git show --stat HEAD; git log -1 --format=%s; git push origin main
```
(The restore edit was dry-run on a scratch copy on 2026-11-16 after the 3.3 edit: see the record at the end of 5.3.) This commit changes the probe in the pod template, so the pod
rolls once more: a plain 35.0.3 -> 35.0.3 restart (no rsync, no `occ upgrade`, ~4 min). After it is Ready re-run **G1, G2 and G4**, then:
```sh
runbooks/update-marker.sh clear nextcloud
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 19093:9093 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -X DELETE "http://localhost:19093/api/v2/silence/$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['silenceID'])" $X/silence.json)" -o /dev/null -w 'DELETE -> HTTP %{http_code}\n'   # EXPECT 200
kill $PF 2>/dev/null
kubectl delete snapshots.longhorn.io nextcloud-config-pre-35-0-3 nextcloud-mariadb-pre-35-0-3 -n storage     # only after G9 (settle) is green; the gate's own objects
```
Close the three findings with the bump commit (`runbooks/policy-cli.py finding close F-45b00114 --commit "$(cat $X/bump-sha.txt)"`, same for `F-e39c0b2c`,
`F-4a9d6631`; source the DSN in a separate shell call from any `git commit`). Retire this plan file in the commit that records the window. Keep `$X` until the
next 23:00 Longhorn backup covers the 35.0.3 state, then delete the dump and the config tar (secrets).

## 4. Verification

`nc_snap $X/post` first. Baseline is `$X/predrain` (after the app pre-drain, before the image moved). Every gate states what a failure prints.

**G1 - the new digest runs everywhere, the old one nowhere (shape floor).**
```sh
kubectl get pods -n office -o jsonpath='{range .items[*]}{.metadata.name}{" "}{range .status.containerStatuses[*]}{.name}{"="}{.imageID}{" "}{end}{"\n"}{end}' | grep -e '^nextcloud-[0-9a-f]\{6,\}' -e notify-push > $X/imageids.txt
grep -o 'sha256:8a7a65b8' $X/imageids.txt | wc -l        # EXPECT 3 (main + worker in one pod, notify-push). If 2.2 re-resolved the digest, use its first 8 hex chars
grep -c 'sha256:e0b1a2af' $X/imageids.txt                # EXPECT 0. >=1 = the old generation still serves or a pull failed
grep -c 'sha256:3f05f4d5' $X/imageids.txt                # CONTROL: EXPECT 0 (a digest that can never match: proves the grep discriminates)
kubectl get helmrelease nextcloud -n office -o jsonpath='{.status.history[0].chartVersion} {.status.history[0].status}'     # EXPECT 9.4.4 deployed (9.4.1 = the chart leg did not apply)
```

**G2 - CONTENTS ASSERTION: the instance is Nextcloud 35.0.3, fully migrated, out of maintenance, with its data** - measured by
`python3 $X/nc_gate.py $X/predrain $X/post 35.0.3`, compared to the same-day `$X/predrain` snapshot.
```sh
python3 $X/nc_gate.py $X/predrain $X/post 35.0.3; echo "gate rc=$?"                    # EXPECT GATE PASS, rc=0, and "INFO migrations 570 -> N" with N >= 570
python3 $X/nc_gate.py $X/predrain $X/post 35.0.2; echo "CONTROL rc=$?"                 # CONTROL: EXPECT FAIL versionstring + rc=1 (the gate reads the post state, not the baseline)
kubectl logs deploy/nextcloud -n office -c nextcloud | grep -c -i -e 'Update successful'           # EXPECT >=1 on the FIRST pod after 3.3 (0 after the 3.6 restart: expected there)
kubectl exec deploy/nextcloud -n office -c nextcloud -- grep -c "OC_Version = array(35,0,3," /var/www/html/version.php   # EXPECT 1 (the PVC copy, written last by the entrypoint)
```
FAIL shapes: `status.txt lacks /maintenance: false/` (stuck maintenance -> 5.1/5.2); all three `status.txt lacks` lines plus `apps.json unreadable` (occ cannot
load: the Mail vendor failure -> 5.1); `db ... shrank`; `needsDbUpgrade` true (upgrade interrupted -> 5.2). A migrations count that did not grow is reported as
INFO, not failed: upstream lists migration FIXES, and whether a new migration row lands depends on them - the version and needsDbUpgrade lines are the proof.

**G3 - app-set parity (silently re-disabled apps).** Part of `nc_gate` (`enabled app SET changed`, `app <x> is not enabled` for mail, calendar, contacts,
google_synchronization, notify_push, whiteboard, openclaw_mail). Additionally:
```sh
kubectl logs deploy/nextcloud -n office -c worker | grep -c 'openclaw_mail: enabled'                        # EXPECT 1 (the worker re-enables it on boot)
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ app:update --showonly | wc -l               # report only: apps with a 35.0.3-only release may appear; take them with 3.2's commands + G4
```

**G4 - Mail (the operator's HARD GATE; contents, not a smoke test).** CONTENTS ASSERTION: Mail still holds all three accounts and every cached mailbox, its
code loads, and it can talk to its server - measured by `nc_gate` (`mailboxes.txt` per account exact against the same-day baseline; DB `mail_accounts` and
`mail_mailboxes` exact; `mail_messages` may only grow) plus:
```sh
kubectl exec deploy/nextcloud -n office -c nextcloud -- php -r 'require "/var/www/html/custom_apps/mail/vendor/autoload.php"; echo "MAIL_AUTOLOAD_OK\n";'    # EXPECT MAIL_AUTOLOAD_OK. FAILS as "Failed opening required", rc 255 (control run in 2.4)
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ mail:account:diagnose 1 | grep -c -i 'IMAP connection test passed'     # EXPECT 1
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ mail:account:sync 1; echo "sync1 rc=$?"                                # EXPECT rc=0
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ mail:account:sync 999; echo "CONTROL sync999 rc=$?"                    # CONTROL: EXPECT "does not exist", rc=1 - the rc is a real signal
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ mail:account:sync 3; echo "sync3 rc=$?"                                # EXPECT rc=0 (second provider)
# Log-stream absence check WITH controls: read the WHOLE container log of the current pod once into a file (no --since: on the first new pod the
# `Update successful` line is usually older than 15 min by the time G4 runs), then count every pattern on that SAME file.
kubectl logs deploy/nextcloud -n office -c nextcloud > $X/g4-log.txt; echo "logs rc=$? lines=$(wc -l < $X/g4-log.txt)"     # EXPECT rc=0, lines > 0
grep -c -i -e 'custom_apps/mail' -e 'Failed opening required' $X/g4-log.txt                       # EXPECT 0
grep -c -i -e 'resuming normal operations' $X/g4-log.txt                                          # POSITIVE CONTROL (every pod): EXPECT >= 1 (Apache start line; measured 1 on the live pod 2026-11-16)
grep -c -i -e 'Update successful' $X/g4-log.txt                                                   # POSITIVE CONTROL (FIRST pod after 3.3 only): EXPECT >= 1. 0 on the 3.2 pre-drain run and after the 3.6 restart is expected
printf '%s\n' "PHP Fatal error:  Uncaught Error: Failed opening required '/var/www/html/custom_apps/mail/vendor/autoload.php'" > $X/g4-replay.txt
grep -c -i -e 'custom_apps/mail' -e 'Failed opening required' $X/g4-replay.txt                    # REPLAY: EXPECT 1 (the exact grep detects the failure string; dry-run 2026-11-16 printed 1)
```
What this sub-check can and cannot see: the container stream carries the entrypoint/`occ upgrade` output and Apache's error log (PHP fatals of WEB requests);
it does NOT carry `kubectl exec ... occ` stderr (those surface in the autoload and `mail:account:sync` lines above) nor `data/nextcloud.log`. The positive controls
prove the file is this pod's real stream (an empty or wrong-container read prints 0 on them and FAILS); the replay proves the pattern matches the failure text.
Live baseline 2026-11-16 on the 35.0.2 pod: 48115 lines, failure grep 0, `resuming normal operations` 1. The autoload line, not this grep, is the primary Mail
code gate.
Not gates (known, benign): account 2 (iCloud) intermittent STATUS errors; `mail:account:diagnose` exiting 2 on a Gmail account because of the `[Google Mail]`
container; message counts moving with traffic. Never run `mail:clean-up`. The `sync 999` control and `sync 3` are taken from the digest-refresh draft /
operator notes and were not re-run by me on 2026-11-14 (`diagnose 1` and the autoload pair were). **Attended part (executor in Chrome; passwords and 2FA are
operator-only):** open Mail, open the INBOX of account 1 and one message body, and open the compose window. A blank Mail page or a 500 on the message body is
a FAIL even with every command above green.

**G5 - cron runs on the new image.**
```sh
T=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo $T          # wait >= 6 min, then:
kubectl get jobs -n office --sort-by=.metadata.creationTimestamp -o custom-columns=NAME:.metadata.name,CREATED:.metadata.creationTimestamp,SUCCEEDED:.status.succeeded,FAILED:.status.failed | grep nextcloud-cron | tail -2
#   PASS: a Job CREATED after $T with SUCCEEDED 1, FAILED <none>. FAILED >= 1 = every-occ-fails shape (5.1)
NOW=$(date +%s); LC=$(kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ config:app:get core lastcron 2>/dev/null); echo "lastcron age $((NOW-LC))s"
[ $((NOW-LC)) -lt 600 ] && echo CRON_FRESH || echo CRON_STALE          # EXPECT CRON_FRESH
[ $((NOW-LC)) -lt 1 ] && echo CRON_FRESH || echo "CONTROL: CRON_STALE"  # CONTROL: must print CRON_STALE
```

**G6 - files are there (CIFS data mount readable through the new pod).**
```sh
kubectl exec deploy/nextcloud -n office -c nextcloud -- sh -c 'ls /var/www/html/data | wc -l'                       # EXPECT >= 5 (user dirs + appdata + log); 0 = data volume not mounted
kubectl exec deploy/nextcloud -n office -c nextcloud -- sh -c 'ls /var/www/html/data-nope 2>/dev/null | wc -l'      # CONTROL: EXPECT 0
```
`oc_filecache` not shrinking is already in `nc_gate`. For an authenticated WebDAV PROPFIND with a throwaway app password (207 vs 401 control), use G6 + 2.7 of
`nextcloud-35.0.2-digest-d88929d.md` verbatim; it is optional here because the attended Mail/Files look in G4 covers the same path. The `ls` pair above was not
run by me (the `/var/www/html/data` mount path is the chart default `nextcloud.datadir`; confirm with `kubectl exec ... -- php occ config:system:get datadirectory`).

**G7 - public edge, login page, push.** Host from the live route (never typed into the repo):
```sh
H=$(kubectl get httproute nextcloud -n office -o jsonpath='{.spec.hostnames[0]}')
curl -s --max-time 15 https://$H/status.php | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['version'], d['maintenance'], d['needsDbUpgrade'])"   # EXPECT 35.0.3.2 False False
curl -s --max-time 15 https://$H/login | grep -c -i data-requesttoken             # EXPECT 1 (the rendered login shell, not an Envoy error page)
curl -s --max-time 15 https://$H/robots.txt | grep -c -i data-requesttoken        # CONTROL: EXPECT 0
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ notify_push:self-test | grep -c '✗'      # EXPECT 0 (a failing check prints the cross, e.g. "push server is running the same version as the app")
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ notify_push:self-test | grep -c '✓'      # EXPECT 6 (a 0 here means the reader, not the app, is broken)
```
Login is Nextcloud-native; there is no Authentik path to verify.

**G8 - the metrics still arrive.**
```sh
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q() { curl -s --max-time 10 --data-urlencode "query=$1" http://localhost:19090/api/v1/query | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r), [x['value'][1] for x in r][:2])"; }
q 'nextcloud_up == 1'                        # EXPECT 1 ['1']
q 'up{job="nextcloud-metrics"} == 1'         # EXPECT 1 ['1']
q 'nextcloud_files_total > 35000'            # EXPECT 1 [...]  (baseline 35059)
q 'nextcloud_users_total == 3'               # EXPECT 1 ['3']
q 'nextcloud_up == 0'                        # CONTROL: EXPECT 0 []
kill $PF 2>/dev/null
```
CONTROL: metric nextcloud_up - the exporter's own login probe against the upgraded server; exactly one series equal to 1 (0 or absent = the exporter cannot read the app).
CONTROL: metric up - scrape target `nextcloud-metrics` is 1 (the exporter pod is not restarted by this plan).
CONTROL: metric nextcloud_files_total - floor 35000 against the 35059 baseline; an empty library would pass a bare "series present" check.
CONTROL: metric nextcloud_users_total - exact 3.
(All four series were read live on 2026-11-14 and returned one sample each. Do not gate on `nextcloud_scrape_errors_total`: lazily-born counter, F-a6b4b30c.)

**G9 - settle.** 15 minutes after the 3.6 restart: all `nextcloud*` pods Running/Completed, `restartCount` 0 on the app pod, and a fresh
`nc_snap $X/post2; python3 $X/nc_gate.py $X/predrain $X/post2 35.0.3` still `GATE PASS`.

## 5. Rollback

A bare `git revert` of the bump is NOT a rollback once the new pod has started: the 35.0.2 image refuses 35.0.3 data (entrypoint lines 184-186) and crash-loops.
Recover FORWARD first (5.1/5.2); go back in time (5.3) only on an operator decision.

**5.1 Stuck maintenance mode, a broken app (Mail), or a disabled app after `occ upgrade`.** Symptoms: `maintenance: true`; every `occ` dies with an autoload
error naming `custom_apps/<app>`; cron Jobs FAILED; `nc_gate` reports a lost app.
```sh
# 1. only if an autoload error names the app: move it aside so occ can load at all
kubectl exec deploy/nextcloud -n office -c nextcloud -- mv /var/www/html/custom_apps/mail /var/www/html/custom_apps/mail.broken
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ status
# 2. finish the interrupted upgrade, leave maintenance
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ upgrade
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ maintenance:mode --off
# 3. reinstall the app cleanly from the appstore
kubectl exec deploy/nextcloud -n office -c nextcloud -- rm -rf /var/www/html/custom_apps/mail.broken
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ app:install mail
# 4. anything that moved to Disabled: re-enable (google_synchronization needs --force; openclaw_mail is NOT an appstore app - app:enable only, never app:install)
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ app:enable --force google_synchronization
```
Mail accounts and cached mailboxes live in the DB, not in `custom_apps/mail`, so the reinstall keeps them - G4's exact mailbox counts prove it. Then section 4
in full. If only maintenance is stuck: step 2 alone. This recipe is the 2026-06-06 recovery (memory `project_nextcloud_upgrade_mailapp`), written for the
`nextcloud-config` volume (`custom_apps` subPath).

**5.2 The startup probe (26 min budget) or a node event killed the container mid-upgrade.** The kubelet restarts it. If the kill came during the rsync (no
`Initializing finished` in `kubectl logs --previous`), nothing was migrated and the restart simply re-runs the upgrade. If it came during `occ upgrade`,
`version.php` is already 35.0.3 on the PVC, so the entrypoint skips the upgrade branch and starts Apache with maintenance still on: run 5.1 step 2, then
section 4. With `retries: 0` Flux does not roll anything back underneath you.

**5.3 Full rollback to 35.0.2 - operator decision only (data written since 2.5 is lost from the DB).** The CIFS data PVC `nextcloud-data` is not touched in any
step; no PVC or PV is deleted (storage-safety rules). Files uploaded during the window survive on the share and are re-indexed by a later `occ files:scan --all`.
```sh
# (a) freeze GitOps and stop every writer of the two Longhorn volumes
flux suspend kustomization nextcloud -n office; flux suspend helmrelease nextcloud -n office
kubectl scale deploy/nextcloud deploy/nextcloud-notify-push -n office --replicas=0
kubectl patch cronjob nextcloud-cron -n office -p '{"spec":{"suspend":true}}'
kubectl wait --for=delete pod -l app.kubernetes.io/name=nextcloud,app.kubernetes.io/component=app -n office --timeout=5m
kubectl get pods -n office --field-selector=status.phase=Running -o name | grep -c nextcloud-cron     # EXPECT 0 before going on (a running cron pod holds the RWX volume)
# (b) DB back to the 2.5 dump - CHECK THE FILE FIRST, the DROP is irreversible
tail -c 200 $X/nextcloud-pre-35.0.3.sql | grep -c 'Dump completed'                                      # 1 or STOP
kubectl exec nextcloud-mariadb-0 -n office -c mariadb -- sh -c 'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -e "DROP DATABASE nextcloud; CREATE DATABASE nextcloud CHARACTER SET utf8mb4 COLLATE utf8mb4_bin"'
kubectl exec -i nextcloud-mariadb-0 -n office -c mariadb -- sh -c 'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" --default-character-set=utf8mb4' < $X/nextcloud-pre-35.0.3.sql
```
(c) Code, apps and config: revert Longhorn volume `nextcloud-config` (detached after (a)) to snapshot `nextcloud-config-pre-35-0-3` - Longhorn UI -> Volume ->
Attach in Maintenance Mode -> Snapshots -> Revert -> Detach. Snapshot gone: restore the last 23:00 backup into the volume per `docs/sops/backup.md` and
`docs/sops/longhorn.md`; then put the exact pre-window `config/` back from `$X/config-pre-35.0.3.tar` once a 35.0.2 pod runs. The snapshot predates the app
pre-drain, consistent with the dump (Mail returns to 5.13.1). DB and config volume must go back TOGETHER; restoring one gives code and schema at different versions.
```sh
# (d) git: restore both manifests from the commit before the bump (whole-file restore; check nothing else landed on them since)
cd /Users/mu/code/cberg-home-nextgen; git fetch origin main; git merge --ff-only origin/main
git log --format='%h %s' "$(cat $X/bump-sha.txt)^..HEAD" -- kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml
#   EXPECT only the bump (and the 3.6 restore). Any other subject => STOP and hand-merge with the operator.
for P in kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml; do git show "$(cat $X/bump-sha.txt)^:$P" > "$P.rollback-tmp"; mv "$P.rollback-tmp" "$P"; done
grep -c -e '35\.0\.2@sha256' kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml     # EXPECT :2 and :1
grep -c '^      version: 9\.4\.1$' kubernetes/apps/office/nextcloud/app/helmrelease.yaml                                                   # EXPECT 1
printf '%s\n\n%s\n' 'revert(nextcloud): back to 35.0.2 + chart 9.4.1 after DB dump + nextcloud-config snapshot restore (plan nextcloud-9.4.3 5.3)' 'Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>' > $X/msg-rollback.txt
git commit --only kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml -F $X/msg-rollback.txt
git show --stat HEAD; git log -1 --format=%s; git push origin main
kubectl patch cronjob nextcloud-cron -n office -p '{"spec":{"suspend":false}}'
flux resume helmrelease nextcloud -n office; flux resume kustomization nextcloud -n office
```
Confirm back: `occ status` 35.0.2.2 with maintenance false; HelmRelease Ready on 9.4.1; `nc_snap $X/rb; python3 $X/nc_gate.py $X/pre $X/rb 35.0.2` = `GATE PASS`
(against `$X/pre`, the pre-drain baseline); G4, G5, G7 green. The old digest `e0b1a2af` was still pullable from Docker Hub on 2026-11-14 and is cached on the node.
The direct `kubectl scale/patch` and `flux suspend` calls in (a) are the one place this plan leaves GitOps, as in the executed 35.0.2 plan; 5.3 (a)-(c) were NOT
rehearsed for this plan - it is that plan's procedure with names and versions changed, and they were not executed there either (that rollout went green).
**(d) and the 3.6 restore WERE dry-run, 2026-11-16**, in a scratch git repo seeded with today's two manifests: commit "pre", apply the 3.3 edits (9.4.4 sed +
temporary-block Python) and commit "bump", apply the 3.6 Python restore (printed `restored retries 3 + startup failureThreshold 10`, TEMPORARY count 0, diff
count 5) and commit "close", then run (d) verbatim with `$X` pointing at the scratch dir: the `git log` listed exactly `close` and `bump`; the loop restored both
files; the greps printed `helmrelease.yaml:2`, `notify-push.yaml:1` and `1`; `git diff` against "pre" was EMPTY (byte-identical restore).

**5.4 Abandon before 3.3** (after 3.2): nothing in git to revert. The app updates stay (standing policy) unless Mail could not be made green on 35.0.2 - then
5.3 (b)+(c) return the apps to the pre-window state. Clear the marker and the silence, delete the two snapshots.

## 6. Interference notes

- **Blast radius.** Namespace `office` only. `deployment/nextcloud` restarts twice (first ~8-15 min with rsync + `occ upgrade`, second ~4 min); the public
  hostname behind `envoy-external` answers 503 meanwhile. `nextcloud-notify-push` rolls once. NOT restarted: `nextcloud-mariadb`, `nextcloud-redis` (sessions
  survive), `nextcloud-metrics`, `nextcloud-whiteboard`, `nextcloud-mcp`. Clients (`nextcloud-mcp`, the OpenClaw mail/calendar integration, desktop/mobile
  sync) see errors during the outage and reconnect. Do not start within ~10 min before a scheduled OpenClaw briefing that reads Nextcloud mail or calendar.
- **Relation to the other Nextcloud plans (none of them edited by this planner):**
  - `nextcloud-35.0.2-digest-d88929d` (draft, another session, uncommitted): **made moot by this plan** - it moves the same three lines to a newer 35.0.2 digest,
    and 35.0.3 supersedes any 35.0.2 build. Its own target has also drifted: PR #406 now proposes `786c1021...` (same amd64 manifest `3139d734aa87`, new index).
    Recommendation for its owner: mark it `superseded` by `nextcloud-9.4.3` once this plan is vetted, and close #406 after 3.3 lands (Renovate will otherwise
    retarget it). If it runs FIRST it is harmless here: the premise and the 3.3 regex accept any 35.0.2 digest. Listed in `conflicts_with`; it already lists
    the plans it conflicts with but not this one - reciprocity must be added on its side.
  - `nextcloud-12.0.2` (draft, another session, uncommitted; MariaDB sidecar 11.8.3 -> 12.0.2): independent target, same database. **Never in the same window**,
    and this plan should run first (a server patch on the known 11.8.3 DB, then the DB major on a settled 35.0.3). No `depends_on` either way; `conflicts_with`
    on this side, to be added reciprocally on its side.
  - `bitnamilegacy-exit-nextcloud-db` (blocked): edits the same HelmRelease and replaces the DB; conflict only. When it is revived its dump/restore figures
    must be re-taken on 35.0.3.
  - `bitnamilegacy-exit-nextcloud-redis` (executed 2026-08-19): no relation beyond history; its outcome (`externalRedis`, `redis.enabled: false`) is part of the
    values this plan leaves untouched.
  - `nextcloud-9.4.0` (superseded, folded into the executed 35.0.1 rollout): historical; this plan is its successor on the chart line (same metadata-only finding).
- **`conflicts_with` is the only field the scheduler honours** and `--validate` does not check reciprocity. The other side still needs `nextcloud-9.4.3` added in:
  `nextcloud-35.0.2-digest-d88929d`, `nextcloud-12.0.2`, `redis-fleet-8.10.3`, `postgres-digest-refresh-2026-11`, `postgres-fleet-18.7-bookworm`,
  `kube-prometheus-stack-93.3.0`, `longhorn-1.13.0`, `talos-linux-1.14.5`, `coredns-1.50.5`, `nextcloud-mcp-0.211.1`.
- **Step 0 of the window (safe auto-updates) runs first as always**; the `*nextcloud*` deny rule keeps PRs #526, #535 and #406 out of it. Nothing else in `office` may
  be mid-roll when 3.2 starts.
- **Operator option, not decided here:** every Nextcloud version bump needs the temporary `failureThreshold: 50` and costs a second pod roll to restore it.
  Leaving the startup budget permanently high would remove both the edit and the second outage, at the price of a slower restart of a genuinely hung pod.
- **Pre-existing, not caused or fixed here:** `google_synchronization` token/background-job state (see 1.5) - an operator click in Nextcloud settings.
- **Cleanup:** the two Longhorn snapshots, the silence, the update marker, and `$X` (dump + config tar hold application data and secrets; never commit them).
- No reboot, no node drain, no PVC/PV operation, no Authentik or Homepage change.
