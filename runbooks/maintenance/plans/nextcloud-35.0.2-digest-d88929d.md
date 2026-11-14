---
plan_id: nextcloud-35.0.2-digest-d88929d
component: nextcloud
pr: 406
kind: image
current: "35.0.2@sha256:e0b1a2af52c82c07b7a0e8e59878bd8769e704447734d5d238a836982f51b9c8"
target: "35.0.2@sha256:d88929dc8386420b8963f86cabb667fdaf733eef9dcf8fc98e226801a32c023c"
update_type: patch                    # SAME tag 35.0.2, SAME Nextcloud version.php (35,0,2,2) - an upstream REBUILD (digest refresh), not a version change. Proven in 1.2.
risk: medium                          # household file server + Mail hard gate + ~3-5 min Recreate outage. The change itself is a rebuild of the
                                      # same release; "low" is defensible but not claimed: the no-migration proof comes from the registry, not a rehearsal.
est_duration_min: 45                  # backups check 5 + dump 5 + snapshot 5 + merge/roll 10 + gates 15 + slack 5
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud                    # values.image.tag and the worker sidecar image (2 of the 3 digest lines)
    - deployment/nextcloud                     # strategy Recreate: whole pod (nextcloud + worker containers) restarts; 3-5 min outage
    - deployment/nextcloud-notify-push         # notify-push.yaml image line (3rd digest line); RollingUpdate
    - cronjob/nextcloud-cron                   # chart renders its image from values.image.tag; next */5 run uses the new digest
    - pvc/nextcloud-config                     # RWX longhorn-static: whole /var/www/html incl. custom_apps (Mail etc.). Remounted, NOT modified
    - pvc/nextcloud-data                       # CIFS (cifs-nextcloud-data): remounted by the new pod, NOT modified
    - statefulset/nextcloud-mariadb            # READ-ONLY here: dump + row counts. Not restarted. (sidecar pinned 11.8.3, out of scope)
    - deployment/nextcloud-redis               # READ-ONLY here (sessions stay valid because redis is NOT restarted by this plan)
  shared: [envoy-external, cifs/nextcloud-data, monitoring]   # envoy-external: public hostname 502/503 during Recreate and the edge gates read it.
                                                              # monitoring: READ-ONLY (section 4 G8 reads Prometheus - the window's instrument).
depends_on: []
conflicts_with:
  - nextcloud-mcp-0.203.0              # office-namespace Nextcloud clients whose verification reads Nextcloud; a Nextcloud outage mid-gate false-fails them
  - nextcloud-mcp-0.204.0
  - nextcloud-mcp-0.206.0
  - redis-fleet-8.10.3                 # restarts nextcloud-redis (sessions + file locks): two Nextcloud-facing restarts in one window blur which one broke a gate
  - postgres-digest-refresh-2026-11    # shares namespace office restarts and the Longhorn backup surface; never stack two office restarts
  - nextcloud-12.0.2                   # draft by another session (MariaDB sidecar 11.8.3 -> 12.0.2); Part B converts the datadir under this app
  - bitnamilegacy-exit-nextcloud-db    # blocked; edits the SAME helmrelease and replaces the DB under this app
  - kube-prometheus-stack-92.22.0      # section 4 G8 reads Prometheus: a same-night Prometheus restart makes the instrument unreliable
  - longhorn-1.13.0                    # storage engine bump under nextcloud-config / nextcloud-mariadb: backups + attach semantics move
  - talos-linux-1.14.5                 # node reboots under the pod; also the Sunday reboot-capable window
  - envoy-gateway-1.10.0               # the edge gates (status.php, /login) read through envoy-external
  - envoy-proxy-config-distroless-v1.40.0
  - envoy-proxy-config-distroless-v1.40.2
  - flux-oci-chart-sources             # re-sources every HelmRelease chart: nextcloud HR reconcile timing/ownership moves
  - helm-drift-detection
  - flux-reconciler-impersonation
  - etcd-timeouts-5000-500
exclusive: false
security_ref: null                    # no open finding names THIS digest. Precedent F-59a444f8 (previous rebuild, EXECUTED b529cd63) is a citation only.
capability_change: false              # same release, same behaviour: no new feature, route, permission, API or exposure
rollback_class: git-revert            # same-version image swap, no migration (proven 1.2, enforced by gate G2). Any migration firing flips this to
                                      # backup-restore and STOPS the plan for a human (section 5 path B).
finding_refs: []                      # `policy-cli.py finding list --grep nextcloud` (2026-11-09) has NO finding for this digest; adding one would be
                                      # inventing an ownership claim. Re-check before vetting; if the version sweep files one, add its id here.
review: null
status: superseded   # 2026-11-14 plan-reviewer REJECT: PR #406 was force-updated to a different digest than this plan's target, and nextcloud-9.4.3 (chart 9.4.3 + image 35.0.3) supersedes the whole bump. Never reviewed-ready or executed.
superseded_by: nextcloud-9.4.3
window: null                          # requested: nightly (SD-11: interruption is accepted at night) - or sat-attended if the operator wants Mail checked by eye.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-09"
premises:
  # Run from the REPO ROOT. All measured 2026-11-09 (UTC 00:0x); each can FAIL when the state drifts.
  - id: live-deployment-on-old-digest
    why: >-
      The plan moves e0b1a2af -> d88929dc. If the live Deployment already runs d88929dc (someone merged #406 or the
      nightly auto-update took it) the plan is moot; if it runs a third digest the baseline is not what section 1 measured.
    run: kubectl get deployment nextcloud -n office -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "nextcloud:35.0.2@sha256:e0b1a2af52c8"
  - id: manifest-has-exactly-three-old-digest-lines
    why: >-
      The PR / the step-3 sed rewrites exactly three lines: helmrelease.yaml image.tag + worker sidecar (2) and
      notify-push.yaml (1). A different count means a fourth consumer appeared or the pin was already moved.
    run: grep -h -c e0b1a2af52c82c07b7a0e8e59878bd8769e704447734d5d238a836982f51b9c8 kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml
    expect_matches: '(?s)^2\s+1$'
  - id: no-other-nextcloud-image-pin-in-repo
    why: >-
      Guards against a consumer outside kubernetes/apps/office/nextcloud (a second cron, a job) that also pins the old digest and would be
      left behind. Exactly the 3 lines above must exist repo-wide.
    run: grep -r -l e0b1a2af52c82c07b7a0e8e59878bd8769e704447734d5d238a836982f51b9c8 kubernetes
    expect_matches: '(?s)^kubernetes/apps/office/nextcloud/app/(helmrelease|notify-push)\.yaml\s+kubernetes/apps/office/nextcloud/app/(helmrelease|notify-push)\.yaml$'
  - id: chart-is-9.4.1
    why: >-
      Policy: chart and image move to the NEWEST in lockstep. Chart 9.4.1 carries appVersion 35.0.2 and is the newest (measured 2026-11-09); a chart
      change in the same window would make this a different plan.
    run: kubectl get helmrelease nextcloud -n office -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "9.4.1"
  - id: strategy-is-recreate
    why: >-
      RWO-style single-writer discipline: the Deployment must be Recreate so old and new app pods never write the PVC together (an
      overlapping pair would double-run the entrypoint on shared /var/www/html). Reads the LIVE object.
    run: kubectl get deployment nextcloud -n office -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: app-pod-ready-both-containers
    why: >-
      The pre-state is a settled pod: `nextcloud` and `worker` both ready (premise reads the LIVE pod status; a mid-restart or crash-looping pod
      reads "false"). The occ-level baseline (version 35.0.2.2, maintenance false, needsDbUpgrade false, mail 5.13.1) needs `kubectl exec`, which this runner refuses:
      it is pre-check 2.1/2.5, run by the executor.
    run: kubectl get pods -n office -l app.kubernetes.io/component=app -o jsonpath='{.items[*].status.containerStatuses[*].ready}'
    expect_exact: "true true"
  - id: nextcloud-config-volume-healthy
    why: >-
      Apps and config live on Longhorn volume nextcloud-config. A degraded volume means the backup floor and the remount under the new pod are suspect. Backup AGE
      is not readable here (python3 is refused by the runner); the freshness gate is `runbooks/longhorn-backup-age.py` in pre-check 2.3 with its negative control.
    run: kubectl get volumes.longhorn.io nextcloud-config -n storage -o jsonpath='{.status.robustness}'
    expect_exact: "healthy"
  - id: nextcloud-mariadb-volume-healthy
    why: Same for the DB volume; the dump in 2.4 and the Path-B restore both depend on it.
    run: kubectl get volumes.longhorn.io nextcloud-mariadb -n storage -o jsonpath='{.status.robustness}'
    expect_exact: "healthy"
  - id: sidecar-still-11.8.3
    why: >-
      The MariaDB sidecar is deliberately pinned and OUT OF SCOPE (PR #479 declined). If it moved, the dump/restore path in section 5 changes.
    run: kubectl get statefulset nextcloud-mariadb -n office -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "bitnamilegacy/mariadb:11.8.3@sha256:ada2a782"
---

# nextcloud-35.0.2-digest-d88929d - Nextcloud image digest refresh (PR #406), same tag 35.0.2

## 1. Summary & why held

### 1.1 What moves

Renovate PR #406 (`chore(container): update nextcloud ( e0b1a2a -> d88929d )`, label `renovate/container`) changes THREE lines in two files, all
the same digest swap on the SAME tag `35.0.2`:

| File | Line | Consumer |
|---|---|---|
| `kubernetes/apps/office/nextcloud/app/helmrelease.yaml` | 34 | `values.image.tag` -> main `nextcloud` container AND the chart's `nextcloud-cron` CronJob |
| `kubernetes/apps/office/nextcloud/app/helmrelease.yaml` | 234 | `extraSidecarContainers[worker]` (task-processing worker + whiteboard JWT sync + `openclaw_mail` enable) |
| `kubernetes/apps/office/nextcloud/app/notify-push.yaml` | 40 | `deployment/nextcloud-notify-push` (runs the `notify_push` binary from `custom_apps` on the PVC) |

No chart change (9.4.1 is the newest and already carries appVersion 35.0.2), no value change. CI on the PR: Flate Render Gate, Flux Local Diff
(helmrelease + kustomization) and Labeler all SUCCESS.

**Why held:** the `*nextcloud*` deny rule in `runbooks/auto-update-policy.yaml` holds every Nextcloud image change, because a *version* bump runs `occ upgrade`
on boot (migrations, Mail `custom_apps` vendor breakage, stuck maintenance mode, force-enabled apps silently re-disabled - memory
`project_nextcloud_upgrade_mailapp`). The rule cannot tell a version bump from a same-version rebuild, so this one is held on the rule, not on a
demonstrated hazard. Precedent: `b529cd63` rolled the PREVIOUS rebuild of 35.0.2 (`3f05f4d5` -> `e0b1a2af`, finding F-59a444f8) with no migration.

### 1.2 What the new digest actually is (measured 2026-11-09 against the Docker Hub registry, amd64 child manifests)

| | old `e0b1a2af` (LIVE) | new `d88929dc` (TARGET) |
|---|---|---|
| amd64 manifest | `c73d6b4ada51...` | `3139d734aa87...` |
| image `created` | 2026-10-28T02:38Z | 2026-11-05T08:46Z |
| `NEXTCLOUD_VERSION` env | 35.0.2 | 35.0.2 |
| `PHP_VERSION` env | 8.5.12 | 8.5.12 |
| layers | 22 | 22 (Debian trixie base re-snapshotted, so layer digests differ; the `WORKDIR` layer is byte-identical) |

**The decisive proof that no `occ upgrade` can fire.** I streamed the 276 MB Nextcloud layer of the NEW image (`e3ffd4460d2f`) and read
`/usr/src/nextcloud/version.php`:

```
$OC_Version = array(35,0,2,2);
$OC_Build = '2026-10-15T08:07:55+00:00 ba900af933e61ffa005315b09d6454bfbbcbcc81';
```

The LIVE instance has `/usr/src/nextcloud/version.php` and `/var/www/html/version.php` both at exactly `array(35,0,2,2)` with the identical `OC_Build`.
The entrypoint (`/entrypoint.sh` in the running pod, lines 184-294) calls `occ upgrade` ONLY inside `if version_greater "$image_version" "$installed_version"`
(line 189). Equal versions -> the branch is skipped: no `rsync` of `/usr/src/nextcloud` over the PVC, no `occ upgrade`, no `app:update`, no maintenance toggle.
Everything that changed is the Debian base and the rebuilt PHP/Apache layers - OS-level updates, same Nextcloud source.

So the answer to "can `occ upgrade` fire?" is **no, by construction**, and gate G2 (section 4) proves it after the fact with the migrations-table count
and `occ status`. If G2 nevertheless fails, the plan becomes HUMAN-GATED and the Mail recovery recipe (section 5, path B) applies. That is why
`rollback_class` is `git-revert` but section 5 carries a full forward-only procedure.

### 1.3 Live baseline (read-only, 2026-11-09 ~00:00 UTC)

| Fact | Value |
|---|---|
| chart / HR revision | `nextcloud` 9.4.1, Helm history v61 (2026-11-03 21:37Z) |
| image (main + worker + notify-push + cron) | `nextcloud:35.0.2@sha256:e0b1a2af...` |
| strategy | `deployment/nextcloud` **Recreate** (single replica, pod `2/2`: `nextcloud` + `worker`, 0 restarts); notify-push RollingUpdate |
| initContainers on every roll | `wait-for-mariadb`, `wait-for-redis`, `install-openclaw-mail`, `mariadb-isalive` |
| probes | startup 60s+10x30s, liveness 120s+10x30s (a CIFS blip is ridden out ~5 min), readiness 60s+10x60s |
| `occ status` | version 35.0.2.2, maintenance false, needsDbUpgrade false |
| apps | **69 enabled / 9 disabled**. mail **5.13.1**, calendar 6.6.4, contacts 8.9.5, whiteboard 2.1.2, google_synchronization 4.3.2, notify_push 1.4.2, richdocuments 12.0.1, openclaw_mail 0.1.0 (the 2026-09-20 note's 68/9 is stale - take the same-day snapshot, not the note). Disabled: admin_audit, agenda_bot, encryption, files_3dmodelviewer, files_external, photos, suspicious_login, twofactor_nextcloud_notification, user_ldap |
| pending app updates (NOT part of this plan) | spreed, files_3dmodelviewer, calendar 6.6.5, richdocumentscode, assistant 4.1.0 - policy says app updates are always take-able, but they are a SEPARATE in-pod `occ app:update` step after this window, never mixed with an image roll |
| Mail | 3 accounts (ids 1,2,3); mailboxes 10 / 9 / 12 = **31** (occ and DB agree); `oc_mail_messages` 54008; acct-1 INBOX 21205 msgs / 26 unseen, acct-2 INBOX 1500 / 10, acct-3 INBOX 2141 / 3; `mail:account:diagnose 1` -> "IMAP connection test passed"; `Cron mail sync failed` in the pod log: 0 |
| DB (mariadb 11.8.3) | `oc_filecache` 35049, `oc_migrations` **570**, `oc_calendarobjects` 2906, `oc_jobs` 115 |
| users / calendars | 3 users; calendars per user 1 / 2 / 4 (the 4 includes the two "Google Calendar import" calendars) |
| cron | `cronjob/nextcloud-cron` `*/5`, last runs Completed; `core.lastcron` fresh; backgroundjobs_mode `cron` |
| Longhorn backups | `nextcloud-config` and `nextcloud-mariadb` both FRESH, 0.8 h old at measurement (RecurringJob `daily-backup-all-volumes`, 23:00 UTC) |
| Prometheus | `nextcloud_up`=1, `up{job="nextcloud-metrics"}`=1, `nextcloud_files_total` 35049, `nextcloud_users_total` 3, DB size ~1.03 GB |
| edge | `/status.php` 200 `{version 35.0.2.2, maintenance false}`; `/login` 200 with `data-requesttoken` |
| notify_push | `occ notify_push:self-test` all six checks pass |

**Pre-existing defect, NOT caused by or fixed by this plan (report to the operator):** `google_synchronization` is ENABLED (4.3.2) but has **zero
background jobs** (`occ background-job:list` shows none) and the one connected user's `token_expires_at` is 1793775008 = **2026-11-04T06:50Z**, i.e. ~4.7 days expired and
not refreshing. That is exactly the "app was disabled by an upgrade, jobs were deleted, re-enable does not recreate them" shape in `project_nextcloud_upgrade_mailapp` - it dates from the
2026-11-03 app updates / image roll window, not from anything this plan will do. The calendar import data itself is intact (the import calendars exist; `oc_calendarobjects` 2906).
Fix is an operator click (Nextcloud -> Settings -> Google synchronization, re-register) - see section 6. This plan only asserts it does not get WORSE (G9).

Mail account 2 (the iCloud one) throws intermittent, self-healing STATUS IMAP errors (`project_nextcloud_mail_account_quirks`, benign): they are NOT a rollback trigger and
are not gated. `mail:account:diagnose` exits non-zero on any Gmail account (cosmetic `[Google Mail]` NonExistent container): also not gated; the gate uses account 1 only.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). `occ` is always called in the direct `kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ ...` form (never an `$OCC` variable: zsh does not word-split it).

1. **Window is clear and nothing is mid-flight.**
   ```sh
   kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ status      # expect: versionstring 35.0.2, maintenance false, needsDbUpgrade false
   kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ app:list | grep -c 'mail: 5.13.1'     # expect 1 (Mail baseline on the PVC)
   flux get hr nextcloud -n office                      # READY True, revision 9.4.1
   kubectl get pods -n office | grep -i nextcloud       # nextcloud 2/2 Running; cron pods Completed (none Error)
   kubectl get job -n office | grep -i nextcloud-cron | grep -v -e Complete || echo "no running/failed cron jobs"
   ```
   Abort if `occ status` shows maintenance true or needsDbUpgrade true (premise `instance-healthy-and-unmigrated`).

2. **PR #406 is exactly what section 1.1 says** (network lookup; kept out of the premises on purpose):
   ```sh
   gh pr view 406 --json state,files --jq '.state, ([.files[].path] | sort | join(" "))'
   # expect: OPEN, then: kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml
   gh pr diff 406 | grep -c '^[+-][^+-]'
   # expect: 6   (3 removed + 3 added lines). Anything else: STOP, the PR was rebased onto something else.
   gh pr diff 406 | grep '^+' | grep -c d88929dc8386420b8963f86cabb667fdaf733eef9dcf8fc98e226801a32c023c
   # expect: 3
   ```
   Re-prove the "same Nextcloud version" claim if the PR was rebased to a different digest:
   ```sh
   # prints OC_Version of the image's bundled source; must equal the live 35,0,2,2
   python3 - <<'PY'
   import json,urllib.request,tarfile
   def get(u,t=None,a=None,raw=False):
       r=urllib.request.Request(u)
       if t: r.add_header("Authorization","Bearer "+t)
       if a: r.add_header("Accept",a)
       x=urllib.request.urlopen(r); return x if raw else json.load(x)
   t=get("https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/nextcloud:pull")["token"]
   A="application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json"
   B="https://registry-1.docker.io/v2/library/nextcloud/"
   idx=get(B+"manifests/sha256:d88929dc8386420b8963f86cabb667fdaf733eef9dcf8fc98e226801a32c023c",t,A)
   m=get(B+"manifests/"+[x for x in idx["manifests"] if x["platform"]["architecture"]=="amd64"][0]["digest"],t,A)
   big=max(m["layers"],key=lambda l:l["size"])
   tf=tarfile.open(fileobj=get(B+"blobs/"+big["digest"],t,A,raw=True),mode="r|gz")
   for mem in tf:
       if mem.name.endswith("usr/src/nextcloud/version.php"):
           print([l for l in tf.extractfile(mem).read().decode().splitlines() if "OC_Version =" in l or "OC_Build" in l]); break
   PY
   ```
   **PASS** = `OC_Version = array(35,0,2,2)` and the same `OC_Build`. **FAIL (the check can fail)** = any other array: the digest is a newer Nextcloud, `occ upgrade`
   WILL fire, and this plan must be re-planned as a version upgrade (HUMAN-GATED, Mail recipe). Takes ~1-2 min (276 MB stream, stops at version.php).

3. **Backups (floor) and negative control.**
   ```sh
   python3 runbooks/longhorn-backup-age.py nextcloud-config nextcloud-mariadb --max-hours 26    # expect exit 0, both FRESH
   python3 runbooks/longhorn-backup-age.py nextcloud-config nextcloud-mariadb --max-hours 0.1   # CONTROL: expect exit 1 (both STALE at 0.1 h)
   ```
   If the first is not FRESH, wait for / trigger the RecurringJob `daily-backup-all-volumes` (CronJob `storage/daily-backup-all-volumes`) per `docs/sops/backup.md` and re-run. Do not proceed on STALE.

4. **Logical DB dump (belt and braces; the Longhorn backup is the floor).** The DB is ~1 GB; `utf8mb4` is mandatory (214 tables are `utf8mb4_bin`; a default-charset dump flattens
   4-byte data - this destroyed the 2026-08-19 exit attempt). Nextcloud keeps serving; `--single-transaction` gives a consistent snapshot.
   ```sh
   umask 077; mkdir -p ~/db-dumps; chmod 700 ~/db-dumps
   kubectl exec nextcloud-mariadb-0 -n office -c mariadb -- sh -c 'mariadb-dump -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" --default-character-set=utf8mb4 --single-transaction --routines --events --triggers --databases nextcloud' > ~/db-dumps/nextcloud-pre-35.0.2-d88929d.sql
   tail -c 200 ~/db-dumps/nextcloud-pre-35.0.2-d88929d.sql | grep -c 'Dump completed'          # expect 1 (a truncated dump has no trailer)
   grep -c '^CREATE TABLE' ~/db-dumps/nextcloud-pre-35.0.2-d88929d.sql                          # expect 214
   ls -l ~/db-dumps/nextcloud-pre-35.0.2-d88929d.sql | awk '{print ($5 > 100000000) ? "SIZE_OK" : "SIZE_TOO_SMALL"}'   # expect SIZE_OK
   ```
   (Dry-tested 2026-11-09 on one table: `mariadb-dump ... nextcloud oc_appconfig` ends with `-- Dump completed on ...`.) The dump contains application data: keep it OFF the repo and delete it after the soak.

5. **Baseline snapshot + the gate function (this is the single source for G2/G3/G4/G9).** Paste the function block below into the shell, then:
   ```sh
   PRE=~/nc-gate/pre; nc_snap "$PRE"; cat "$PRE"/status.txt "$PRE"/mailboxes.txt "$PRE"/cals.txt "$PRE"/db.txt
   wc -l < "$PRE"/apps.txt      # expect 78 (69 enabled + 9 disabled); also: grep -c '^enabled' / '^disabled' = 69 / 9
   ```
   Expected today: `mailboxes acct1=10 acct2=9 acct3=12`, `cals=1,2,4`, `db: mail_accounts 3, mail_mailboxes 31, migrations 570`. **Re-take it on the day**; mailbox counts drift with Gmail label changes, so the same-day snapshot is the baseline, not these numbers.

   ```sh
   nc_snap() {
     d="$1"; mkdir -p "$d"
     kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ status 2>/dev/null > "$d/status.txt"
     kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ app:list --output=json 2>/dev/null > "$d/apps.json"
     python3 -c 'import sys,json; d=json.load(open(sys.argv[1])); print("\n".join(sorted([f"enabled {k} {v}" for k,v in d["enabled"].items()]+[f"disabled {k} {v}" for k,v in d["disabled"].items()])))' "$d/apps.json" > "$d/apps.txt"
     for n in 1 2 3; do echo "acct$n mailboxes=$(kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ mail:mailbox:list $n 2>/dev/null | grep -c '^| [0-9]')"; done > "$d/mailboxes.txt"
     kubectl exec deploy/nextcloud -n office -c nextcloud -- sh -c 'for u in $(php occ user:list --output=json | php -r "echo implode(\" \", array_keys(json_decode(stream_get_contents(STDIN),true)));"); do echo "cals=$(php occ dav:list-calendars $u | awk "/^\\| /{n++} END{print n-1}")"; done | sort' 2>/dev/null > "$d/cals.txt"
     kubectl exec nextcloud-mariadb-0 -n office -c mariadb -- sh -c 'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -e "select \"filecache\",count(*) from nextcloud.oc_filecache union all select \"mail_accounts\",count(*) from nextcloud.oc_mail_accounts union all select \"mail_mailboxes\",count(*) from nextcloud.oc_mail_mailboxes union all select \"mail_messages\",count(*) from nextcloud.oc_mail_messages union all select \"calendarobjects\",count(*) from nextcloud.oc_calendarobjects union all select \"migrations\",count(*) from nextcloud.oc_migrations"' 2>/dev/null > "$d/db.txt"
   }

   nc_gate() {   # $1 = PRE dir, $2 = POST dir. Prints one FAIL line per broken property; returns 1 if any.
     pre="$1"; post="$2"; rc=0
     for pat in 'versionstring: 35\.0\.2$' 'needsDbUpgrade: false' 'maintenance: false'; do
       grep -q -e "$pat" "$post/status.txt" || { echo "FAIL status.txt lacks /$pat/ (empty file = occ itself failed)"; rc=1; }
     done
     for f in status.txt apps.txt mailboxes.txt cals.txt; do
       diff -q "$pre/$f" "$post/$f" >/dev/null 2>&1 || { echo "FAIL $f differs from baseline"; diff "$pre/$f" "$post/$f" | head -6; rc=1; }
     done
     python3 - "$pre/db.txt" "$post/db.txt" <<'PY' || rc=1
   import sys
   def rd(p):
       return {l.split("\t")[0]: int(l.split("\t")[1]) for l in open(p) if "\t" in l}
   a, b = rd(sys.argv[1]), rd(sys.argv[2])
   bad = 0
   if not a or not b:
       print("FAIL db.txt empty (mariadb unreadable)"); sys.exit(1)
   for k in ("mail_accounts", "mail_mailboxes", "migrations"):          # EXACT: a migration or a lost mailbox changes these
       if a.get(k) != b.get(k): print(f"FAIL db {k}: {a.get(k)} -> {b.get(k)}"); bad = 1
   for k in ("filecache", "mail_messages", "calendarobjects"):         # FLOOR: may grow with use, must never shrink
       if b.get(k, -1) < a.get(k, 0): print(f"FAIL db {k} shrank: {a.get(k)} -> {b.get(k)}"); bad = 1
   sys.exit(bad)
   PY
     [ "$rc" = 0 ] && echo "GATE PASS" || echo "GATE FAIL"
     return $rc
   }
   ```
   (When pasting, strip the 3-space markdown indent of the heredoc body; the `PY` terminator must start in column 0. Both functions were exercised live on 2026-11-09.)

6. **Gate self-test BEFORE the roll (the gates must be able to FAIL).**
   ```sh
   nc_gate "$PRE" "$PRE"; echo "positive control rc=$?"            # expect GATE PASS, rc=0 (pre vs itself)
   rm -rf ~/nc-gate/ctrl; cp -R "$PRE" ~/nc-gate/ctrl
   sed -i '' 's/^enabled mail .*/enabled mail 0.0.0/' ~/nc-gate/ctrl/apps.txt
   sed -i '' 's/^acct3 mailboxes=.*/acct3 mailboxes=0/' ~/nc-gate/ctrl/mailboxes.txt
   sed -i '' 's/needsDbUpgrade: false/needsDbUpgrade: true/' ~/nc-gate/ctrl/status.txt
   awk 'BEGIN{FS=OFS="\t"} $1=="migrations"{$2=$2+1} {print}' "$PRE"/db.txt > ~/nc-gate/ctrl/db.txt
   nc_gate "$PRE" ~/nc-gate/ctrl; echo "negative control rc=$?"     # expect FOUR+ FAIL lines (status, apps, mailboxes, db migrations) and rc=1
   ```
   Do not start the roll if the negative control returns rc=0: the gate is blind.
   (BSD sed `-i ''` and the awk line were dry-run on macOS against a copy of the live snapshot; the mutated copy produced FAIL on status/apps/mailboxes/migrations.)

7. **WebDAV gate credentials + positive control BEFORE the roll.** Nextcloud's local `admin` env credentials do not authenticate (HTTP 401 measured), so use a throwaway app password for the first listed user (that user has ~15 top-level entries on the CIFS data mount):
   ```sh
   GU=$(kubectl exec deploy/nextcloud -n office -c nextcloud -- sh -c 'php occ user:list --output=json | php -r "\$a=array_keys(json_decode(stream_get_contents(STDIN),true)); echo \$a[0];"' 2>/dev/null)
   GT=$(kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ user:auth-tokens:add "$GU" --name maint-gate-nc-35.0.2-d88929d 2>/dev/null | tail -1)
   [ -n "$GT" ] && echo "token captured (len ${#GT})"      # last line of the command output is the token (source: core/Command/User/AuthTokens/Add.php writeln(<label>); writeln($token))
   dav() { kubectl exec deploy/nextcloud -n office -c nextcloud -- curl -s -o /tmp/pf.xml -w '%{http_code}' -u "$GU:$1" -X PROPFIND -H 'Depth: 1' -H 'Host: nextcloud.office.svc.cluster.local' "http://localhost/remote.php/dav/files/$GU/"; }
   echo "good=$(dav "$GT") bad=$(dav wrong-token)"                       # expect good=207 bad=401  (the bad token is the NEGATIVE CONTROL)
   kubectl exec deploy/nextcloud -n office -c nextcloud -- sh -c 'grep -o "<d:href>" /tmp/pf.xml | wc -l'   # baseline entry count; note it as DAV_PRE (expect ~16 = collection + ~15 children)
   ```
   Do not start if `good` != 207 or `bad` != 401. (`GU` is a username: never paste it into a commit, plan or finding.)

## 3. Steps

All GitOps; no direct cluster mutation. Work on `main`. Use `git commit --only` with explicit paths if you take the fallback.

1. **Merge PR #406** (preferred; it is exactly the 3-line change, CI green):
   ```sh
   gh pr merge 406 --squash --subject 'fix(nextcloud): roll onto the rebuilt upstream 35.0.2 digest d88929dc (app, worker, notify-push)'
   git pull --ff-only origin main
   grep -h -c d88929dc8386420b8963f86cabb667fdaf733eef9dcf8fc98e226801a32c023c kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml   # expect 2 then 1
   grep -r -c e0b1a2af52c82c07b7a0e8e59878bd8769e704447734d5d238a836982f51b9c8 kubernetes/apps/office/nextcloud | grep -v ':0$' || echo "old digest gone"
   ```
   **Fallback if #406 was closed/rebased** - same edit by hand (BSD sed; dry-run on a scratch copy 2026-11-09 produced exactly lines 34 and 234 of helmrelease.yaml and line 40 of notify-push.yaml, 3 replacements, 0 old digests left):
   ```sh
   OLD=e0b1a2af52c82c07b7a0e8e59878bd8769e704447734d5d238a836982f51b9c8
   NEW=d88929dc8386420b8963f86cabb667fdaf733eef9dcf8fc98e226801a32c023c
   sed -i '' "s/$OLD/$NEW/g" kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml
   git diff --stat      # expect 2 files, 3 insertions(+), 3 deletions(-)
   printf '%s\n' 'fix(nextcloud): roll onto the rebuilt upstream 35.0.2 digest d88929dc (app, worker, notify-push)' '' 'Same-version rebuild (OC_Version 35,0,2,2 unchanged): no occ migration expected.' > /tmp/nc-msg.txt
   git commit --only kubernetes/apps/office/nextcloud/app/helmrelease.yaml kubernetes/apps/office/nextcloud/app/notify-push.yaml -F /tmp/nc-msg.txt
   git log -1 --format=%s     # confirm the subject is YOURS before pushing
   git push origin main
   ```
   Record the commit SHA - it is the rollback target. Commit message carries no domains, usernames or vulnerability detail.

2. **Wait for Flux (webhook-driven; do not force-reconcile unless it has not started in 10 min).** Record `T0=$(date +%s)` at the push.
   ```sh
   flux get hr nextcloud -n office            # wait for READY True, "Helm upgrade succeeded" (HR timeout 30m, 3 retries, cleanupOnFail)
   kubectl rollout status deploy/nextcloud -n office --timeout=15m
   kubectl rollout status deploy/nextcloud-notify-push -n office --timeout=5m
   ```
   Expect a 3-5 minute outage of the public hostname (Recreate: old pod terminates, new pod runs four initContainers, then 60 s startup delay). Sessions and file locks survive: `nextcloud-redis` is not touched.
   **`rollout status` can green-light the OLD generation** (feedback_rollout_status_old_generation) - G1 below proves the live digest; do not skip it.

3. **Do NOT run `occ upgrade`, `occ maintenance:mode`, `occ app:update` or `occ app:enable` as part of the happy path.** Nothing should be needed; G2 proves it. If the new pod's log shows
   `Initializing nextcloud` / `Upgrading nextcloud from`, STOP and go to section 5 path B.

## 4. Verification

All gates are run by the executor after step 3.2. `POST=~/nc-gate/post; nc_snap "$POST"` first. Every gate lists what a failure prints.

**G1 - the new digest is live everywhere, and the old one is gone (shape floor).**
```sh
kubectl get pods -n office -o jsonpath='{range .items[*]}{.metadata.name}{" "}{range .status.containerStatuses[*]}{.name}{"="}{.imageID}{" "}{end}{"\n"}{end}' | grep -e '^nextcloud-[0-9a-f]\{6,\}' -e notify-push > /tmp/nc-imageids.txt
grep -o 'sha256:d88929dc' /tmp/nc-imageids.txt | wc -l      # expect 3: main + worker (one pod) + notify-push
grep -c 'sha256:e0b1a2af' /tmp/nc-imageids.txt              # expect 0.  FAILS (prints >=1 / first count 0) if the old generation still serves or a pull failed
grep -o 'sha256:3f05f4d5' /tmp/nc-imageids.txt | wc -l      # CONTROL: expect 0 - proves the grep distinguishes digests (the previous-previous digest can never match)
```
The `nextcloud-cron-*` pods are checked in G5 (they only exist for ~5 minutes after each tick).

**G2 - CONTENTS ASSERTION: the instance is the same Nextcloud, no migration ran, nothing is in maintenance.** Measured by `nc_gate "$PRE" "$POST"` (status.txt equal to baseline = version 35.0.2.2, maintenance false, needsDbUpgrade false; `oc_migrations` count equal to the baseline 570), compared to the baseline taken in step 2.5.
```sh
nc_gate "$PRE" "$POST"          # expect: GATE PASS
kubectl logs deploy/nextcloud -n office -c nextcloud | grep -c -i -e 'Initializing nextcloud' -e 'Upgrading nextcloud from'    # expect 0
kubectl logs deploy/nextcloud -n office -c nextcloud | grep -c -i -e 'resuming normal operations'                                # CONTROL: expect >=1 (fresh pod log is readable; a 0 here means the log reader, not the app, is broken - re-read before trusting the 0 above)
```
FAIL shapes: an empty `status.txt` (occ itself cannot load - the Mail vendor/ failure of 2026-06-06 prints "Failed opening required .../mail/vendor/..." and `status.txt` is empty, so all three `lacks` lines fire); `FAIL db migrations: 570 -> 5xx` if any migration ran; `needsDbUpgrade: true`. The negative control was run in step 2.6.

**G3 - app-set parity (the force-enabled-apps-silently-disabled hazard).** `apps.txt` is part of `nc_gate`; any enabled app that moved to disabled, or any version change (mail 5.13.1, google_synchronization 4.3.2, whiteboard 2.1.2, calendar 6.6.4, contacts 8.9.5, notify_push 1.4.2, openclaw_mail 0.1.0), prints `FAIL apps.txt differs` with the diff. Plus explicit names:
```sh
grep -E '^enabled (mail|calendar|contacts|whiteboard|google_synchronization|notify_push|openclaw_mail) ' "$POST"/apps.txt | wc -l      # expect 7
grep -c '^enabled ' "$POST"/apps.txt; grep -c '^disabled ' "$POST"/apps.txt                                                       # expect 69 and 9 (the same-day baseline values)
kubectl logs deploy/nextcloud -n office -c worker | grep -c 'openclaw_mail: enabled'                                                # expect 1 (worker re-enabled it on boot)
```

**G4 - Mail (HARD GATE, contents not shape).** CONTENTS ASSERTION: Mail still has all three accounts and all 31 mailboxes cached and can talk to its server - measured by `nc_gate` (`mailboxes.txt` per account 10/9/12 exact; DB `mail_accounts` 3 and `mail_mailboxes` 31 exact; `mail_messages` may only grow from 54008) plus a live sync:
```sh
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ mail:account:diagnose 1 | grep -c 'IMAP connection test passed'     # expect 1
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ mail:account:sync 1; echo "sync1 rc=$?"                              # expect rc=0
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ mail:account:sync 999; echo "CONTROL sync999 rc=$?"                  # CONTROL: expect "Account 999 does not exist", rc=1 (measured 2026-11-09) - proves the rc is a real signal
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ mail:mailbox:list 1 | grep INBOX        # INBOX row: messages >= 21205-ish, unseen plausible (26 at baseline); message counts DRIFT with mail traffic - never roll back on those alone
```
Account 2 (iCloud) STATUS errors and `diagnose` exit 2 on the Gmail account are benign and NOT gates. FAIL shapes: `mail:account:sync 1` non-zero or an autoload `Failed opening required` error -> section 5 path B recipe; `acct3 mailboxes=0`/`db mail_mailboxes` drop -> cache loss (do NOT run `mail:clean-up`).
**Attended window only (optional, executor does it in Chrome):** log in, open Mail, open account 1 INBOX and one message body. Passwords and 2FA are operator-only.

**G5 - cron runs on the NEW image.**
```sh
J=nc-gate-cron-$(date +%s)
kubectl create job --from=cronjob/nextcloud-cron $J -n office
kubectl wait --for=condition=complete job/$J -n office --timeout=300s              # FAILS (timeout / exit 1) if the cron pod errors - the Mail-vendor failure mode
kubectl get pod -n office -l job-name=$J -o jsonpath='{.items[0].status.containerStatuses[0].imageID}' | grep -c 'sha256:d88929dc'   # expect 1
kubectl get pod -n office -l job-name=$J -o jsonpath='{.items[0].status.containerStatuses[0].imageID}' | grep -c 'sha256:e0b1a2af'   # CONTROL: expect 0
NOW=$(date +%s); LC=$(kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ config:app:get core lastcron 2>/dev/null)
echo "lastcron age = $((NOW-LC))s"; [ $((NOW-LC)) -lt 600 ] && echo CRON_FRESH || echo CRON_STALE      # expect CRON_FRESH
[ $((NOW-LC)) -lt 1 ] && echo CRON_FRESH || echo "CONTROL (threshold 1s): CRON_STALE"                    # CONTROL: must print CRON_STALE
kubectl delete job $J -n office
```
(`ttlSecondsAfterFinished` is not set on this job; deleting it is cleanup of the gate's own object only.) Also `kubectl get pods -n office | grep nextcloud-cron` must show no `Error`/`ImagePullBackOff`.

**G6 - WebDAV PROPFIND on a real path (CIFS data mount is mounted and readable).**
```sh
echo "good=$(dav "$GT") bad=$(dav wrong-token)"                                   # expect good=207 bad=401 (same as the pre-roll positive/negative control in 2.7)
kubectl exec deploy/nextcloud -n office -c nextcloud -- sh -c 'grep -o "<d:href>" /tmp/pf.xml | wc -l'   # expect >= DAV_PRE (the user's file listing is non-empty: a mounted-but-empty or unmounted CIFS share returns 207 with 1 href or 5xx)
```
FAIL shape: `good=503/500` (data mount missing - the CIFS blip pattern), `good=401` (token/auth path broken), href count 1 (empty share). Then delete the throwaway token:
```sh
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ user:auth-tokens:list "$GU" --output=json | php -r '$d=json_decode(stream_get_contents(STDIN),true); foreach($d as $t) if($t["name"]==="maint-gate-nc-35.0.2-d88929d") echo $t["id"],"\n";'
# then: kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ user:auth-tokens:delete "$GU" <id-from-above>
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ user:auth-tokens:list "$GU" --output=json | grep -c maint-gate-nc    # expect 0
```

**G7 - public edge + login + push.** Host comes from the live route (never typed into the repo):
```sh
H=$(kubectl get httproute nextcloud -n office -o jsonpath='{.spec.hostnames[0]}')
curl -s --max-time 15 https://$H/status.php | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['version'], d['maintenance'], d['needsDbUpgrade'])"   # expect: 35.0.2.2 False False
curl -s --max-time 15 -o /dev/null -w '%{http_code}\n' https://$H/login                                                        # expect 200
curl -s --max-time 15 https://$H/login | grep -c -i data-requesttoken                                                          # expect 1 (the rendered login shell, not an Envoy error page)
curl -s --max-time 15 https://$H/robots.txt | grep -c -i data-requesttoken                                                     # CONTROL: expect 0 - proves the marker is specific to the login page
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ notify_push:self-test | grep -c '✓'                              # expect 6 (redis, redis messages, mount info, connect, trusted proxy, same version)
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ notify_push:self-test | grep -c '✗'                              # expect 0 (a failing check prints ✗ - the app/binary version-mismatch case "push server is running the same version as the app")
```
Login is Nextcloud-native (local password + TOTP): there is NO SSO/OIDC app enabled (`user_oidc`/`oidc_login` absent), so there is no Authentik path to verify here.

**G8 - the metrics instrument still reads.** (Do not gate on `nextcloud_scrape_errors_total`: it is a lazily-born CounterVec and an absent child reads empty on a healthy fresh exporter - F-a6b4b30c.)
```sh
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q() { curl -s --max-time 10 --data-urlencode "query=$1" http://localhost:19090/api/v1/query | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r), [x['value'][1] for x in r][:2])"; }
q 'nextcloud_up == 1'                         # expect: 1 ['1']
q 'up{job="nextcloud-metrics"} == 1'          # expect: 1 ['1']
q 'nextcloud_files_total > 35000'             # expect: 1 [...]  (floor; baseline 35049)
q 'nextcloud_users_total == 3'                # expect: 1 ['3']
q 'nextcloud_up == 0'                         # CONTROL: expect: 0 []  - an inverted predicate returns empty, so the 4 reads above are not tautologies
kill $PF 2>/dev/null
```
CONTROL: metric nextcloud_up - the exporter's own login probe against Nextcloud; the gate requires exactly one series equal to 1 (an exporter that cannot reach the app reads 0 or is absent).
CONTROL: metric up - scrape target `nextcloud-metrics` is `up == 1` (the exporter pod is NOT restarted by this plan, so a 0 here means the app answered the exporter badly).
CONTROL: metric nextcloud_files_total - floor 35000 against the 35049 baseline: a ceiling-less "value present" check would pass on an empty library; this reads the file count the exporter pulled from the DB through the new pod.
CONTROL: metric nextcloud_users_total - exact 3, same-day baseline.

**G9 - Google calendar import + google_synchronization did not get worse.** CONTENTS ASSERTION: the imported calendars and their events are intact and the app is still enabled - measured by `nc_gate` (`cals.txt` 1/2/4 exact; `calendarobjects` floor 2906) and G3 (`enabled google_synchronization 4.3.2`). The expired token / missing background jobs are the PRE-EXISTING defect from 1.3 and are not a pass/fail input; the executor records `token_expires_at` before and after (it must not move to a LATER failure state, e.g. the app becoming disabled) and reports it:
```sh
kubectl exec deploy/nextcloud -n office -c nextcloud -- php occ background-job:list --limit 2000 | grep -i -c -e 'OCA.Google' -e 'Synchroniz'     # baseline 0; record, do not gate (0 before and after = unchanged)
```

**G10 - settle.** 15 minutes after the roll: `kubectl get pods -n office | grep -i nextcloud` all Running/Completed, `restartCount` 0 on the new pod, and `nc_gate` re-run once more (a second `nc_snap` to `~/nc-gate/post2`) still PASS. A pod that passes at +2 min and OOM-restarts at +10 (memory limit 3Gi; peak ~1.4 GiB measured historically) is caught here.

## 5. Rollback

**Path A - same-version image swap, nothing forward-only (the expected path; cost ~5 min).** Use for any failed G1/G5/G6/G7/G8 or a pod that will not become Ready.
```sh
git revert --no-edit <merge-or-fallback-commit-sha>        # restores e0b1a2af on all 3 lines
git push origin main
kubectl rollout status deploy/nextcloud -n office --timeout=15m
kubectl get deployment nextcloud -n office -o jsonpath='{.spec.template.spec.containers[*].image}'   # expect both containers on e0b1a2af
nc_snap ~/nc-gate/rb; nc_gate "$PRE" ~/nc-gate/rb                                                   # expect GATE PASS
```
The old digest is still pullable (manifest fetched from Docker Hub 2026-11-09) and is cached on the node (`IfNotPresent`). **A Flux helm-upgrade failure self-rolls back** (HR `upgrade.remediation.retries: 3`, `cleanupOnFail`); if that happens, the git change is still on `main` - revert it too, or Flux will retry.

**Path B - something forward-only happened (a migration ran: `FAIL db migrations`, `Initializing nextcloud` in the log, `needsDbUpgrade`, or the Mail vendor failure).** This is NOT fixed by `git revert`:
the apps and the Nextcloud code live on the `nextcloud-config` PVC (`custom_apps`, `version.php`, `config/`), which an image revert does not touch. A downgrade is unsupported by the entrypoint
("data version higher than the docker image version" refuses to start). STOP and hand to the operator (HUMAN-GATED). Procedure, in order:
1. Do not delete the PVC or any volume. Keep `~/db-dumps/nextcloud-pre-35.0.2-d88929d.sql` and the Longhorn backups of `nextcloud-config` and `nextcloud-mariadb` taken in 2.3 (the latest completed ones before the window).
2. Recover forward first (Mail recipe, from `project_nextcloud_upgrade_mailapp`; exec into the running pod, container `nextcloud`):
   ```sh
   kubectl exec -it deploy/nextcloud -n office -c nextcloud -- sh
   mv /var/www/html/custom_apps/mail /var/www/html/custom_apps/mail.broken     # so occ can load at all
   php occ status
   php occ upgrade                                                              # finishes the interrupted upgrade, exits maintenance
   php occ maintenance:mode --off
   rm -rf /var/www/html/custom_apps/mail.broken
   php occ app:install mail                                                     # re-downloads from the appstore, re-enables
   php occ app:list | sed -n '/^Disabled:/,$p'                                  # re-force-enable anything newly disabled: php occ app:enable --force google_synchronization
   ```
   then re-run `nc_snap`/`nc_gate` and G5 (a `nextcloud-cron` job must be Completed, not Error). If `maintenance:mode` stuck ON: `php occ maintenance:mode --off`.
3. Restore is the LAST resort (data loss = everything since the backup): scale `deploy/nextcloud` to 0 via git (`replicas: 0` in the HelmRelease, push), restore `nextcloud-mariadb` from the dump
   (`mariadb --default-character-set=utf8mb4 < dump`, via port-forward to `svc/nextcloud-mariadb`, after dropping/recreating the `nextcloud` schema) or revert the Longhorn volume `nextcloud-mariadb`
   AND `nextcloud-config` TOGETHER from the same night's backup (restoring only one gives a DB at version N and code at N+1), per `docs/sops/backup.md` and `docs/sops/longhorn.md`. Never delete the CIFS PVC `nextcloud-data` (class `cifs-nextcloud-data`, storage-safety rules).
Forward-only inventory for this change: none expected (the entrypoint branch is skipped). The 276 MB `nextcloud/` source in the image is NOT copied to the PVC when versions match.

## 6. Interference notes

- **Blast radius.** Own namespace only: `deployment/nextcloud` (Recreate, 3-5 min outage of the public hostname through `envoy-external`), `deployment/nextcloud-notify-push` (rolling), the `nextcloud-cron` pods after the next tick. Not restarted: `nextcloud-mariadb`, `nextcloud-redis`, `nextcloud-metrics`, `nextcloud-whiteboard`, `nextcloud-mcp`. Clients that talk to Nextcloud (`nextcloud-mcp`, the OpenClaw Mail/Calendar integration) will log connection errors for the outage; they reconnect on their own. Interruption is acceptable overnight (SD-11); data or feature loss is not.
- **`conflicts_with` (the only field the scheduler honours).** `nextcloud-mcp-0.203.0/0.204.0/0.206.0` (clients whose own gates read Nextcloud), `redis-fleet-8.10.3` (restarts `nextcloud-redis`: sessions/locks), `postgres-digest-refresh-2026-11`, `nextcloud-12.0.2` and `bitnamilegacy-exit-nextcloud-db` (touch the same app's DB; those two must never share a night with this app roll), `kube-prometheus-stack-92.22.0` (G8 reads Prometheus), `longhorn-1.13.0` and `talos-linux-1.14.5` (storage engine / node reboots under the pod), `envoy-gateway-1.10.0` + the two `envoy-proxy-config-distroless-*` (the edge gates), `flux-oci-chart-sources`, `helm-drift-detection`, `flux-reconciler-impersonation`, `etcd-timeouts-5000-500` (HelmRelease/control-plane timing). Reciprocity is NOT checked by `--validate`: whoever vets these should add `nextcloud-35.0.2-digest-d88929d` to `redis-fleet-8.10.3`, `postgres-digest-refresh-2026-11`, `kube-prometheus-stack-92.22.0`, `longhorn-1.13.0` and `talos-linux-1.14.5` (I was not permitted to edit those files). n8n-fleet-2.46.6 does not touch `office` and was not listed.
- **The Nextcloud DB sidecar is out of scope.** `nextcloud-12.0.2` (declined #479, 11.8.3 -> 12.0.2, EOL upstream and not on Nextcloud 35's supported list) is another session's untracked draft; this plan neither reads nor edits it.
- **Do not bundle app updates.** `occ app:update` for spreed / calendar 6.6.5 / assistant 4.1.0 / richdocumentscode / files_3dmodelviewer is policy-approved ("always take app updates, Mail is the hard gate") but is a separate in-pod step on the PVC with its own `nc_gate`. Mixing it into this window removes the ability to attribute a Mail failure to the image.
- **Operator follow-up (not part of this plan):** the `google_synchronization` re-registration in 1.3 (Settings -> Google synchronization once; stored OAuth token survives, no re-auth unless Google revoked it). Until then the Google calendar import is stale since 2026-11-04.
- **Cleanup in the window:** delete `~/nc-gate`, the throwaway app password (G6) and, after the soak, `~/db-dumps/nextcloud-pre-35.0.2-d88929d.sql` (application data; never commit it).
- **Nothing here needs a reboot, a Flux force-reconcile, or a node drain.** `needs_reboot: false`.
