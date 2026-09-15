---
plan_id: nextcloud-34.0.4
component: nextcloud
pr: null                              # no Renovate PR — coverage.py direct-bump items
                                      # F-f3e9ddb0 (server) + F-4a9d6631 (notify-push),
                                      # both routed to the PLAN lane by the `*nextcloud*`
                                      # deny rule in runbooks/auto-update-policy.yaml
kind: image
current: "34.0.3"
target: "34.0.4"
update_type: patch
risk: medium                          # household's primary file/mail/calendar server;
                                      # startup-time `occ upgrade` with a documented
                                      # stuck-maintenance / broken-Mail-app history
                                      # (33.0.0->33.0.4, 2026-06-06). See §1.3 for the
                                      # mechanism and §3.2 for how this plan defuses it.
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud                     # image.tag + worker sidecar tag (+ temporary
                                                # upgrade.remediation.retries 3 -> 0 -> 3)
    - deployment/nextcloud                      # Recreate rollout; entrypoint rsync + occ upgrade
    - deployment/nextcloud-notify-push          # tag moves in the SAME commit (lockstep rule)
    - cronjob/nextcloud-cron                    # template image re-rendered by the chart
    - pvc/nextcloud-config                      # html/ rsynced, custom_apps/ rewritten by app updates
    - statefulset/nextcloud-mariadb             # NOT restarted — receives one-way app migrations
    - deployment/nextcloud-redis                # NOT restarted — clients reconnect; notify_push_* keys rewritten
    - "new: snapshot.longhorn.io/nextcloud-config-pre-34-0-4 + nextcloud-mariadb-pre-34-0-4 (ns storage)"
  shared: []                                    # own Longhorn volumes only; gateway/envoy,
                                                # cert-manager, cilium, coredns untouched.
                                                # Cross-namespace CONSUMERS (ai/openclaw mail +
                                                # calendar skills, office/nextcloud-mcp,
                                                # Homepage widget) see a 2-5 min 503 — §6.
depends_on: []
conflicts_with: [bitnamilegacy-exit-nextcloud-db]   # same helmrelease.yaml, both restart
                                                # deployment/nextcloud. That plan is `blocked`
                                                # with window: null, so no live collision
                                                # today — the guard is for when it revives.
security_ref: F-ab9e243a              # security driver for the image bump. What it is and
                                      # why this tag answers it live on the record only —
                                      # never counts, IDs or vocabulary here (public repo).
capability_change: true               # the SERVER patch changes no capability, but `occ
                                      # upgrade` drags every pending appstore update along
                                      # (Updater.php:244) — Mail 5.10 -> 5.11 is a minor
                                      # line with user-visible features, plus Talk, Calendar,
                                      # Contacts, CODE. Honest answer: users will see changes.
rollback_class: backup-restore        # a git revert is NOT a rollback once `occ upgrade`
                                      # ran: the entrypoint refuses to start an older image
                                      # on newer data (§5.3). Rollback = DB dump restore +
                                      # Longhorn snapshot revert of nextcloud-config. No
                                      # backup_gate named => human-gated, which the deny rule
                                      # demands anyway ("operator-supervised only").
finding_refs: [F-f3e9ddb0, F-4a9d6631, F-ab9e243a]
status: draft
window: null                          # ATTENDED weekend slot only (sat-attended /
                                      # sun-attended). Never `nightly`: the executor must
                                      # watch the entrypoint log during §3.4 and be able to
                                      # run the §5.1 recovery inside the same slot.
premises:
  # Runner grammar (plan-premises.py): kubectl/flux/git/helm READ verbs + text filters
  # only — no exec, no curl, no python, no `$( )`/`;`. Everything occ-derived (status,
  # app set, notify_push self-test) and the Hub-tag check are therefore EXECUTOR gates
  # in §2.0/§2.2, run by hand and abort-on-mismatch, not premises.
  - id: live-server-image-is-still-34.0.3-on-both-containers
    why: >-
      `current:` claims 34.0.3 on the main container AND the worker sidecar. If either
      already moved (a hand bump, a later coverage run), the §3.3 sed is partial or a
      no-op and the §4 baseline (34.0.3.2) is wrong.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].image} {.spec.template.spec.containers[?(@.name=="worker")].image}'
    expect_exact: "docker.io/nextcloud:34.0.3 nextcloud:34.0.3"
  - id: notify-push-image-is-still-34.0.3
    why: >-
      notify-push runs the same image tag by rule (its manifest comment: "moves in the
      SAME commit as the server tag"; a lag was the sole driver of a security finding
      closed 2026-07-31). If it already differs, the lockstep edit in §3.3 must be
      re-derived rather than applied blind.
    run: kubectl get deploy -n office nextcloud-notify-push -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: nextcloud:34.0.3
  - id: git-pins-are-still-34.0.3
    why: >-
      §3.3 edits exactly three lines: `tag: 34.0.3`, the worker `image: nextcloud:34.0.3`
      (helmrelease.yaml) and `image: nextcloud:34.0.3` (notify-push.yaml). If the pins
      already differ the seds are no-ops and the commit is empty.
    run: >-
      git show HEAD:kubernetes/apps/office/nextcloud/app/helmrelease.yaml HEAD:kubernetes/apps/office/nextcloud/app/notify-push.yaml
      | grep -c '34\.0\.3$'
    expect_exact: "3"
  - id: chart-is-still-9.2.6
    why: >-
      §1.2's verdict "image-only under the current chart is valid, no chart move
      exists" was derived against chart 9.2.6 (appVersion 34.0.3, newest published).
      A newer chart would change both the values path and whether a lockstep chart bump
      belongs in this plan.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "9.2.6"
  - id: helmrelease-is-ready-and-not-mid-upgrade
    why: >-
      Starting a helm upgrade on top of an in-flight or failed one is how Flux
      remediation thrash begins (application-update SOP §7). Ready=True is the only
      state this plan starts from.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: server-deployment-has-one-ready-replica
    why: >-
      A pod that is not Ready right now is either mid-restart or already stuck in
      maintenance mode — either way the §2.2 occ gates cannot be trusted and the
      2026-06-06 failure would be started from, not avoided.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.status.readyReplicas}'
    expect_exact: "1"
  - id: redis-is-the-standalone-deployment-outside-the-helmrelease
    why: >-
      §1.5's claim "this bump does NOT restart nextcloud-redis" rests on redis being a
      plain Kustomize Deployment with no spec change in this plan. If it were folded
      back into the chart, a helm upgrade could roll it and sign every user out — the
      `*nextcloud-redis*` deny rule's whole concern.
    run: kubectl get deploy -n office nextcloud-redis -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "redis:8."
  - id: mariadb-is-still-the-bundled-statefulset-with-a-password-file
    why: >-
      §2.3 dump and §5.3 restore exec into `nextcloud-mariadb-0` and read
      `$MARIADB_ROOT_PASSWORD_FILE` (bitnami layout). If bitnamilegacy-exit-nextcloud-db
      has since replatformed the DB, those commands target the wrong server or fail closed.
    run: kubectl get sts -n office nextcloud-mariadb -o jsonpath='{.spec.template.spec.containers[0].env[*].name}'
    expect_contains: MARIADB_ROOT_PASSWORD_FILE
  - id: newest-longhorn-backup-of-nextcloud-mariadb-is-completed
    why: >-
      The durable rollback floor under §5.3 is the nightly 03:00 Longhorn backup. A
      newest backup in any state but Completed means the floor is missing; its AGE is
      read by the executor in §2.1 (the runner cannot do date math).
    run: kubectl get backups.longhorn.io -n storage -l backup-volume=nextcloud-mariadb --sort-by=.status.snapshotCreatedAt -o jsonpath='{.items[-1].status.state}'
    expect_exact: Completed
  - id: newest-longhorn-backup-of-nextcloud-config-is-completed
    why: >-
      Same floor for the code/custom_apps/config volume that §3.2 and the entrypoint
      rewrite; the §2.4 snapshot is same-day only.
    run: kubectl get backups.longhorn.io -n storage -l backup-volume=nextcloud-config --sort-by=.status.snapshotCreatedAt -o jsonpath='{.items[-1].status.state}'
    expect_exact: Completed
  - id: startup-probe-budget-is-unchanged
    why: >-
      §1.3's timing math (kubelet kills the container 60 s + 10 x 30 s = 360 s after start
      if status.php never answers) and the decision to drain the appstore pass FIRST (§3.2)
      both rest on these two numbers. A changed probe changes the risk shape.
    run: kubectl get deploy -n office nextcloud -o jsonpath='{.spec.template.spec.containers[?(@.name=="nextcloud")].startupProbe.failureThreshold} {.spec.template.spec.containers[?(@.name=="nextcloud")].startupProbe.periodSeconds}'
    expect_exact: "10 30"
  - id: flux-remediation-retries-is-3
    why: >-
      §3.3 flips `upgrade.remediation.retries` 3 -> 0 for the attempt and §3.6 restores
      3. If it is already something else, both edits need re-deriving.
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.spec.upgrade.remediation.retries}'
    expect_exact: "3"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/disaster-recovery.md
  - docs/sops/longhorn.md
  - docs/sops/maintenance-windows.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-09-15"
---

# nextcloud 34.0.3 -> 34.0.4 (server image + notify-push, one commit)

## 1) Summary & why held

### 1.1 What moves

Three image-tag lines, one commit, chart **unchanged** at 9.2.6:

| File | Line | From | To |
|---|---|---|---|
| `kubernetes/apps/office/nextcloud/app/helmrelease.yaml` | `image.tag` | `34.0.3` | `34.0.4` |
| same | `extraSidecarContainers[worker].image` | `nextcloud:34.0.3` | `nextcloud:34.0.4` |
| `kubernetes/apps/office/nextcloud/app/notify-push.yaml` | `image` | `nextcloud:34.0.3` | `nextcloud:34.0.4` |

The chart re-renders `cronjob/nextcloud-cron` with the new tag on its own.
`metrics`, `whiteboard`, `mariadb` and `redis` specs do not change and do not
restart.

Both coverage items (`nextcloud` F-f3e9ddb0 and `nextcloud-notify-push`
F-4a9d6631) are the same tag on the same image and are answered by this one
plan; notify-push runs the `notify_push` binary from the shared
`custom_apps/` PVC and only borrows the image for its runtime, so its tag
must equal the server's (the manifest says so, and a lag was a closed
security finding on 2026-07-31).

### 1.2 Does the chart have to move in lockstep? No — and it cannot

The `*nextcloud*` deny rule reads *"chart+image must bump together and run occ
migrations"*. Measured against the published chart index (2026-09-15):

- newest chart is **9.2.6, appVersion 34.0.3** (2026-08-17) — there is no chart
  carrying 34.0.4 to move to;
- this HelmRelease pins `image.tag` explicitly on both the app container and the
  worker sidecar, so the chart's `appVersion` is only the *default* it never
  uses. An image-only bump under 9.2.6 is the first-class path, not a hack — it
  is the mirror image of `f1dccd13` (chart-only under a pinned image).

So the *literal* lockstep half of the hold does not apply. **The hold is still
correct**, for the second half of its sentence: the image bump runs `occ
upgrade` on pod start, and that is where the Mail / stuck-maintenance trap
lives (§1.3). `risk: medium`, attended — not a false positive.

### 1.3 Why an image PATCH is migration-bearing here (the mechanism, with evidence)

The official image's `/entrypoint.sh` (read from the running 34.0.3 pod):

- line 189: `if version_greater "$image_version" "$installed_version"` → rsyncs
  `/usr/src/nextcloud/` over `/var/www/html/` (PVC `nextcloud-config`, RWX,
  ~730 MB in `core/`+`apps/`), then
- line 294: `run_as 'php /var/www/html/occ upgrade'`.

`occ upgrade` is `OC\Updater::doUpgrade()`. At **`lib/private/Updater.php:244`**
(same pod):

```php
// upgrade appstore apps
$this->upgradeAppStoreApps($this->appManager->getEnabledApps());
```

which for every enabled app calls `isUpdateAvailable()` → `updateAppstoreApp()`
— i.e. **a server patch bump downloads and installs every pending appstore
update, inside the container's startup path.** `appstoreenabled` is unset here
(default `true`), so this pass is live. Today's pending set
(`occ app:update --showonly`, 2026-09-15):

```
mail                 5.10.12 -> 5.11.5    (minor line; own DB migrations; PHP 8.1-8.5, NC 32-35 — pod runs PHP 8.5.9)
notify_push          1.4.0   -> 1.4.1    (adds pgsql_ssl config support only)
richdocumentscode    26.4.104 -> 26.4.303 (the built-in CODE AppImage — the largest download by far)
spreed 24.0.4->24.0.5, calendar 6.5.3->6.5.4, contacts 8.7.6->8.8.1, richdocuments 11.1.0->11.1.1,
drawio 4.3.5->4.3.8, guests 4.9.0->4.10.0, integration_paperless 1.0.13->1.0.14
(agenda_bot, files_3dmodelviewer are DISABLED and outside the enabled-apps pass)
```

Now the timer. The chart's startupProbe is `initialDelaySeconds: 60`,
`periodSeconds: 30`, `failureThreshold: 10`: **the kubelet kills the container
360 s after start if `status.php` has not answered.** Measured on the last
plain restart (2026-09-07, no upgrade): container start → Ready = **86 s**, so
the rsync alone is fine. What is *not* budgeted is ten appstore downloads +
extractions onto an NFS-backed RWX volume inside `occ upgrade`. That is the
2026-06-06 incident in one sentence: *the probe restarted the pod mid-`occ
upgrade`; Mail's `vendor/` came out half-extracted, every `occ` and every cron
pod then failed on autoload, and maintenance mode stayed on*
(`project_nextcloud_upgrade_mailapp`).

**Defusal (§3.2):** run the appstore pass *first*, in the foreground of the
healthy pod, where there is no probe timer and each app prints its own result.
Then the image bump's `occ upgrade` has nothing left to download and finishes
in seconds. The remaining risk is the ordinary one (core migration on a
patch), and 34.0.4's notes carry no schema change.

### 1.4 Upstream 34.0.4 — what the release actually contains

Released 2026-09-10 (`nextcloud-releases/server` v34.0.4); Hub tag published
2026-09-12, multi-arch. ~70 server PRs, all fixes; relevant lines verbatim:

- `[Master] fix(security): Update code signing revocation list` — **five**
  times (#63358, #63364, #63370, #63521, #64097). This is the security
  content; the image-level driver is cited as `security_ref`.
- `Fix one core migration: Only add taskprocessing columns if they don't exist
  (#63404)` — makes an *existing* migration idempotent; already-applied rows in
  `oc_migrations` are not re-run.
- `Feat(updater): clear app_install_overwrite on major upgrades (#63633)` —
  **major** upgrades only; inert on 34.0.3→34.0.4.
- `Fix: don't rely on constraint for filecache_extended "upsert" when in
  transaction (#63985)`, `Fix(jobs): don't overwrite the --stop_after baseline
  in background-job:worker (#63328)` — the latter touches the exact command our
  worker sidecar loops on; behaviour fix, no config change.
- `Fix(iMIP): Prevent mails from carrying an unrelated user's name (#63310)`,
  `Fix: Check rememberme cookie previous session id matches uid (#63719)`,
  `Fix(2fa): Add missing BruteForceProtection attribute (#63732)`.
- Bundled apps: `app_api` "make db migrations idempotent", `activity`,
  `circles`, `files_pdfviewer`, `notifications`, `photos`, `text`, `viewer` —
  fixes only.
- **No PHP requirement change, no config key rename, no breaking change, no new
  schema migration.**

### 1.5 The two datastores — explicit verdicts

- **`nextcloud-redis` is NOT restarted.** It is a plain Kustomize Deployment
  (`redis-deployment.yaml`) outside the HelmRelease with no spec change in this
  plan. The main pod's Recreate drops its client connections and they
  reconnect. Logins survive: PHP sessions live under `PHPREDIS_SESSION:*`
  (13 live keys of 972 measured), outside the Nextcloud instance prefix that
  any cache clear would touch. Users see a 503 for the 2-5 min of maintenance,
  not a sign-out. The `*nextcloud-redis*` deny rule is therefore not engaged.
- **`nextcloud-mariadb` is NOT restarted**, but it *is* written: the appstore
  app migrations (Mail 5.11 above all) are one-way. That, plus the entrypoint's
  refusal to start an older image on newer data (§5.3), is why
  `rollback_class: backup-restore` and why §2.3-2.4 take a dump and a snapshot
  before anything moves.

## 2) Pre-checks

Run from the repo root on the Mac mini. Everything here is read-only except the
dump/snapshot artefacts. Baselines go under `~/db-dumps/nextcloud-34.0.4/`
(mode 700, same convention as the bitnamilegacy plan — never `/tmp`).

```bash
cd /Users/mu/code/cberg-home-nextgen
umask 077 && mkdir -p ~/db-dumps/nextcloud-34.0.4 && chmod 700 ~/db-dumps/nextcloud-34.0.4
B=~/db-dumps/nextcloud-34.0.4

# 2.0 premises — every one must PASS before continuing
python3 runbooks/plan-premises.py nextcloud-34.0.4 --require-premises

# 2.0b the checks the premise runner cannot express (needs curl / occ) — ABORT on any mismatch
curl -s https://hub.docker.com/v2/repositories/library/nextcloud/tags/34.0.4 \
  | grep -oE '"name":"34\.0\.4"|"architecture":"amd64"' | sort -u | tr '\n' ' '; echo
#   expect: "architecture":"amd64" "name":"34.0.4"   (application-update SOP Step 0 — never bump to an unpublished tag)
OCC="kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c"
$OCC 'php occ status --output=json'
#   expect: "installed":true, "version":"34.0.3.x", "maintenance":false, "needsDbUpgrade":false — anything else: STOP,
#   the instance is already mid-upgrade or stuck and §5.1 comes BEFORE this plan, not after it
$OCC 'php occ app:list --output=json' | python3 -c "import sys,json;e=json.load(sys.stdin)['enabled'];print(e.get('mail'),e.get('openclaw_mail'),e.get('notify_push'),e.get('google_synchronization'))"
#   expect four versions on the 5.x / 0.1.0 / 1.4.x / 4.x lines (2026-09-15: 5.10.12 0.1.0 1.4.0 4.2.0); a "None" = STOP
$OCC 'php occ notify_push:self-test'
#   expect all six lines green incl. "push server is running the same version as the app"; a red line here
#   is a pre-existing fault (notify-push.yaml's config.php redis-host trap) that this bump would be blamed for
```

**2.1 Cluster / Flux / storage green, nothing in flight**

```bash
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'        # expect header only
flux get helmreleases -n office | grep nextcloud                # READY True, chart 9.2.6
kubectl -n office get pods -l app.kubernetes.io/name=nextcloud  # all Running, 0 recent restarts
kubectl -n office get pods | grep -E 'nextcloud-(notify-push|redis|mariadb)'
kubectl get volumes -n storage nextcloud-mariadb nextcloud-config \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LAST_BACKUP:.status.lastBackupAt
# expect: attached / healthy / lastBackupAt within the last night (premise checks < 36 h)
kubectl -n office get jobs --sort-by=.metadata.creationTimestamp | grep nextcloud-cron | tail -3   # Complete 1/1
```

**2.2 Application baseline (the numbers §4 diffs against)**

```bash
OCC="kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c"
$OCC 'php occ status'                            | tee $B/occ-status-pre.txt
$OCC 'php occ app:list --output=json'            > $B/app-list-pre.json
$OCC 'php occ app:update --showonly'             | tee $B/app-updates-pending-pre.txt
$OCC 'php occ notify_push:self-test'             | tee $B/notify-push-selftest-pre.txt   # 6 green lines
$OCC 'php occ config:system:get version'         | tee $B/config-version-pre.txt         # 34.0.3.2
python3 -c "import json;d=json.load(open('$B/app-list-pre.json'));print(sorted(d['enabled']))" > $B/enabled-set-pre.txt
python3 -c "import json;d=json.load(open('$B/app-list-pre.json'));print(sorted(d['disabled']))" > $B/disabled-set-pre.txt

# DB contents baseline — table count + row counts of the tables the change can hurt
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c '
  mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "show tables" | wc -l
  for T in oc_filecache oc_mail_accounts oc_mail_mailboxes oc_mail_messages oc_users oc_calendarobjects oc_cards oc_migrations oc_appconfig; do
    printf "%s=%s\n" "$T" "$(mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "select count(*) from $T")"
  done' 2>/dev/null | tee $B/rows-pre.txt
# expect: first line 206 (2026-09-15 count); oc_mail_accounts=3; every count > 0

# Mail IMAP round trip, per account (ids from the DB; output stays local)
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "select id from oc_mail_accounts"' 2>/dev/null > $B/mail-account-ids.txt
for ID in $(cat $B/mail-account-ids.txt); do $OCC "php occ mail:account:diagnose $ID" | tee -a $B/mail-diagnose-pre.txt; done
# expect: each account logs in and lists mailboxes (the iCloud account's INTERMITTENT
# STATUS errors are known-benign — project_nextcloud_mail_account_quirks — retry once)
```

**2.3 Pre-change DB dump — the restore point for §5.3.** `--default-character-set=utf8mb4`
is load-bearing: every table is `utf8mb4_bin` while the server default is
`utf8mb3`, and without it the server flattens every 4-byte character to `?`
on the way out (bitnamilegacy-exit-nextcloud-db §3c — that dump was lossy and
passed every row-count check).

```bash
D=$B/nextcloud-pre-34.0.4-$(date +%F).sql
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb-dump -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" \
     --default-character-set=utf8mb4 \
     --single-transaction --routines --triggers --events \
     --databases nextcloud' 2>/dev/null > "$D"
chmod 600 "$D"
ls -l "$D"                                  # must NOT be zero bytes
tail -1 "$D"                                # must read "-- Dump completed"
grep -c 'CREATE TABLE' "$D"                 # must equal the table count from 2.2
grep -c 'SET NAMES utf8mb4' "$D"            # must be >= 1 — the charset proof
```

**2.4 Longhorn snapshots — fast-path insurance for the PVC-resident code + custom_apps and for the DB.**
Same-day only (the 02:30 `global-snapshot-cleanup` deletes user snapshots); the
dump + nightly backup are the durable floor.

```bash
for V in nextcloud-config nextcloud-mariadb; do kubectl apply -f - <<EOF
apiVersion: longhorn.io/v1beta2
kind: Snapshot
metadata:
  name: ${V}-pre-34-0-4
  namespace: storage
spec:
  volume: ${V}
  createSnapshot: true
EOF
done
sleep 10
kubectl -n storage get snapshot.longhorn.io nextcloud-config-pre-34-0-4 nextcloud-mariadb-pre-34-0-4 \
  -o custom-columns=NAME:.metadata.name,READY:.status.readyToUse,SIZE:.status.size
# expect: readyToUse true on both
```

**2.5 Silence + active-update marker** (application-update SOP Step 1; 4 h TTL):

```bash
runbooks/update-marker.sh add nextcloud office 4 "34.0.3->34.0.4 image bump (plan nextcloud-34.0.4)"
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 &
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"office","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"Nextcloud.*|Kube(Pod|Deployment|Job).*|TargetDown","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window-agent",
  "comment":"nextcloud 34.0.3->34.0.4 — rollout + transient cron-job failures during maintenance mode. auto-expires 4h"}' | tee $B/silence.json
```

## 3) Steps

**3.1 Go/no-go.** All premises PASS, 2.1-2.5 clean, dump + snapshots present.
The operator is present and can open Files + Mail afterwards. Abort otherwise.

**3.2 Drain the appstore pass in the foreground (in-pod, deliberate, non-GitOps).**

This is the step that turns the trap into a routine bump. It is the same work
`occ upgrade` would do at line 244 during the next start (§1.3) — just done
where a probe cannot kill it and where each app reports on its own. It is not
a manifest change: appstore apps live on the `nextcloud-config` PVC
(`custom_apps/`) and in the DB, exist in no git repository, and are precisely
the "app state on a PVC with no GitOps path" class the CLAUDE.md exception
covers. The §2.4 snapshot is the backup taken before writing.

```bash
$OCC 'php occ app:update --all' 2>&1 | tee $B/app-update-all.log
# Expect one "<app> updated" per pending app (10 enabled + 2 disabled). richdocumentscode
# (CODE AppImage) is the slow one — minutes, not seconds. Watch for any line
# containing "Error" / "failed" / "Could not".
$OCC 'php occ app:update --showonly'     | tee $B/app-updates-pending-post-3.2.txt   # expect EMPTY
$OCC 'php occ status'                    # maintenance: false, needsDbUpgrade: false, still 34.0.3.2
$OCC 'php occ app:list --output=json'    > $B/app-list-post-3.2.json
python3 - <<EOF
import json
pre=json.load(open('$B/app-list-pre.json')); post=json.load(open('$B/app-list-post-3.2.json'))
assert set(pre['enabled'])==set(post['enabled']), ('ENABLED SET CHANGED', set(pre['enabled'])^set(post['enabled']))
for a in ('mail','openclaw_mail','notify_push','google_synchronization'): assert a in post['enabled'], a
print('enabled set unchanged; mail', pre['enabled']['mail'], '->', post['enabled']['mail'])
EOF
```

Expected wrinkle: `occ notify_push:self-test` now fails ONLY on *"push server
is running the same version as the app"* — the binary on disk is 1.4.1 while
the running container still executes 1.4.0. Step 3.4 rolls that Deployment.
**If any app update fails:** stop here; the instance is still 34.0.3 and
serving; fix that app with §5.1 (move aside → `app:install`) before touching
the image. Do not proceed to 3.3 with a broken app dir — that is the exact
state the entrypoint's `occ upgrade` turns into stuck maintenance.

**3.3 GitOps edit — one commit, two files, three tag lines + the temporary
remediation flip** (application-update SOP Step 2: a Flux rollback of a
half-run `occ upgrade` would start the OLD image on NEW data and crash-loop —
§5.3 — so remediation is off for the attempt).

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
HR=kubernetes/apps/office/nextcloud/app/helmrelease.yaml
NP=kubernetes/apps/office/nextcloud/app/notify-push.yaml

sed -i '' -E 's/^(      tag: )34\.0\.3$/\134.0.4/' "$HR"                      # image.tag
sed -i '' -E 's/^(          image: nextcloud:)34\.0\.3$/\134.0.4/' "$HR"       # worker sidecar
sed -i '' -E 's/^(          image: nextcloud:)34\.0\.3$/\134.0.4/' "$NP"       # notify-push
# remediation: retries 3 -> 0 for this attempt (block is `upgrade:` -> `remediation:` -> `retries: 3`)
python3 - <<'EOF'
import re,io
p='kubernetes/apps/office/nextcloud/app/helmrelease.yaml'; s=open(p).read()
new=s.replace("  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 3\n",
              "  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 0                 # TEMPORARY (plan nextcloud-34.0.4 §3.3) — restore 3 in §3.6\n      remediateLastFailure: false\n",1)
assert new!=s, 'remediation block not found — edit by hand'
open(p,'w').write(new)
EOF

grep -nE 'tag: 34\.0\.4|image: nextcloud:34\.0\.4' "$HR" "$NP"   # expect exactly 3 hits
grep -nE '34\.0\.3' "$HR" "$NP"                                  # expect NONE
grep -nA2 'remediation:' "$HR" | grep -E 'retries: 0|remediateLastFailure: false'   # 2 lines
git diff --stat                                                  # exactly these 2 files
```

Commit (shared worktree: `--only`, never `git add -A`):

```bash
cat > /tmp/nc-msg.txt <<'EOF'
feat(nextcloud): 34.0.3 -> 34.0.4 (server + worker + notify-push, one commit)

Executes runbooks/maintenance/plans/nextcloud-34.0.4.md. Chart stays 9.2.6
(newest published, appVersion 34.0.3; image.tag is pinned explicitly so an
image-only move is the first-class path). notify-push moves in lockstep by
rule. The pending appstore updates were drained in the foreground BEFORE
this bump (plan §3.2) so the entrypoint's occ upgrade has nothing to
download inside the 360 s startup-probe budget — the 2026-06-06 trap.

upgrade.remediation.retries 3 -> 0 for the attempt only (a Flux rollback
onto data occ upgrade already moved would crash-loop on the entrypoint's
downgrade refusal); restored in the follow-up commit.

security_ref: F-ab9e243a  finding_refs: F-f3e9ddb0 F-4a9d6631
EOF
git commit --only kubernetes/apps/office/nextcloud/app/helmrelease.yaml \
                  kubernetes/apps/office/nextcloud/app/notify-push.yaml -F /tmp/nc-msg.txt
git show --stat HEAD            # ONLY the two nextcloud files — anything else, stop
git push origin main
```

**3.4 Watch the rollout — this is the attended part.** Flux reconciles the
Kustomization (webhook), the HelmRelease upgrades (`--wait`, 30 m timeout),
the Deployment does `Recreate`. From the moment the new container starts you
have **360 s** before the startup probe kills it.

```bash
flux get kustomization -n office nextcloud                     # revision = your commit
flux get helmrelease -n office nextcloud                       # Upgrading -> Ready
kubectl -n office get pods -l app.kubernetes.io/name=nextcloud -w   # old pod Terminating, new pod Init -> Running
# In a second terminal, the moment the new pod exists:
NEW=$(kubectl -n office get pod -l app.kubernetes.io/name=nextcloud,app.kubernetes.io/component=app -o jsonpath='{.items[0].metadata.name}')
kubectl -n office logs -f "$NEW" -c nextcloud --timestamps
```

Expected log shape and timing (measured rsync ≈ 86 s; `occ upgrade` with the
appstore pass already drained: seconds):

```
Initializing nextcloud 34.0.4.x ...
Upgrading nextcloud from 34.0.3.2 ...
Initializing finished                     <- ~90 s after start (rsync done)
Nextcloud or one of the apps require upgrade - only a limited number of commands are available
Setting log level to debug / Turned on maintenance mode
Updating database schema / Updated database
Updating <app> ...                        <- shipped apps only; NO downloads expected
Update successful
Turned off maintenance mode
Resetting log level
```

then Apache's `AH00558`/`Command line: 'apache2 -D FOREGROUND'`. If at **~300 s
after container start** the log is still inside `occ upgrade`, get ready for
§5.2 — do not delete the pod, do not scale anything; let the kubelet act and
then repair. Then:

```bash
kubectl -n office rollout status deploy/nextcloud --timeout=15m
kubectl -n office rollout status deploy/nextcloud-notify-push --timeout=5m    # rolls on the tag change
kubectl -n office get pods | grep -E '^nextcloud-(notify-push|cron)'          # notify-push Running; next cron job Complete
```

**3.5 Verify** — §4 in full. Every assertion, including the contents ones.

**3.6 Close out** (after §4 is green):

```bash
# restore remediation
python3 - <<'EOF'
p='kubernetes/apps/office/nextcloud/app/helmrelease.yaml'; s=open(p).read()
new=s.replace("      retries: 0                 # TEMPORARY (plan nextcloud-34.0.4 §3.3) — restore 3 in §3.6\n      remediateLastFailure: false\n","      retries: 3\n",1)
assert new!=s; open(p,'w').write(new)
EOF
grep -nA2 'remediation:' kubernetes/apps/office/nextcloud/app/helmrelease.yaml   # retries: 3 under upgrade
git commit --only kubernetes/apps/office/nextcloud/app/helmrelease.yaml \
  -m "chore(nextcloud): restore upgrade.remediation.retries 3 after the 34.0.4 rollout (plan nextcloud-34.0.4 §3.6)"
git show --stat HEAD && git push origin main

runbooks/update-marker.sh clear nextcloud
SID=$(python3 -c "import json;print(json.load(open('$B/silence.json'))['silenceID'])"); curl -s -X DELETE localhost:9093/api/v2/silences/$SID
```

Then retire this plan file in the commit that records the window (README:
plans are transient) and close the three findings:
`runbooks/policy-cli.py finding close F-f3e9ddb0 --commit <sha>` (and
F-4a9d6631, F-ab9e243a — the security one closes on the re-scan, but say so).
Keep `~/db-dumps/nextcloud-34.0.4/` until the next nightly Longhorn backup
covers the post-upgrade state, then `rm -P` the dump.

## 4) Verification

Floor (shape):

```bash
kubectl get helmrelease -n office nextcloud -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'   # True 9.2.6
kubectl -n office get deploy nextcloud nextcloud-notify-push -o jsonpath='{range .items[*]}{.metadata.name}{" "}{range .spec.template.spec.containers[*]}{.image}{" "}{end}{"\n"}{end}'
# nextcloud docker.io/nextcloud:34.0.4 nextcloud:34.0.4 / nextcloud-notify-push nextcloud:34.0.4
kubectl -n office get pod -l app.kubernetes.io/name=nextcloud,app.kubernetes.io/component=app -o jsonpath='{.items[0].status.containerStatuses[?(@.name=="nextcloud")].imageID}{"\n"}'   # a 34.0.4 digest, restarts 0
kubectl -n office get cronjob nextcloud-cron -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}{"\n"}'   # docker.io/nextcloud:34.0.4
kubectl -n office get jobs --sort-by=.metadata.creationTimestamp | grep nextcloud-cron | tail -2        # newest Complete 1/1 — wait for one that STARTED after the rollout
```

Application (the post-upgrade checklist from `project_nextcloud_upgrade_mailapp`, made executable):

```bash
$OCC 'php occ status' | tee $B/occ-status-post.txt
# versionstring 34.0.4 / version 34.0.4.x / maintenance: false / needsDbUpgrade: false
$OCC 'php occ config:system:get version'                                   # 34.0.4.x
$OCC 'php occ app:list --output=json' > $B/app-list-post.json
python3 - <<EOF
import json
pre=json.load(open('$B/app-list-pre.json')); post=json.load(open('$B/app-list-post.json'))
assert set(pre['enabled'])==set(post['enabled']), ('ENABLED SET CHANGED — re-force-enable per memory', set(pre['enabled'])^set(post['enabled']))
assert not (set(post['disabled'])-set(pre['disabled'])), ('NEWLY DISABLED', set(post['disabled'])-set(pre['disabled']))
for a in ('mail','openclaw_mail','notify_push','google_synchronization','whiteboard','richdocuments'): assert a in post['enabled'], a
print('OK enabled set identical; mail', post['enabled']['mail'], 'notify_push', post['enabled']['notify_push'])
EOF
$OCC 'php occ app:update --showonly'                                       # EMPTY
$OCC 'php occ notify_push:self-test' | tee $B/notify-push-selftest-post.txt  # all 6 lines green, incl. "same version"
$OCC 'php occ integrity:check-core'                                        # no output = clean
$OCC 'tail -200 /var/www/html/data/nextcloud.log' | grep -iE '"level":[34]' | grep -viE 'STATUS|Horde_Imap|account 2' | head   # no upgrade-related errors
                                                                           # (the iCloud account-2 STATUS noise is known-benign)
$OCC 'php -r "echo file_get_contents(\"http://nextcloud:8080/status.php\"),PHP_EOL;"'   # installed true, maintenance false, versionstring 34.0.4
curl -s https://drive.${SECRET_DOMAIN}/status.php                          # same, through the Gateway (external path)
```

**CONTENTS ASSERTIONS** (README rule: assert the property the change could
silently break, not a proxy for it):

1. **CONTENTS ASSERTION: the database still holds the data** — measured by the
   same row-count loop as §2.2 written to `$B/rows-post.txt`, compared to
   `$B/rows-pre.txt`: table count ≥ pre (Mail 5.11 may ADD tables, never drop),
   every listed count ≥ pre and > 0, `oc_migrations` count > pre (the
   migrations that ran are in the ledger). A structurally healthy but emptied
   `oc_mail_messages` / `oc_filecache` fails this; `occ status` would not.
   ```bash
   kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c '
     mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "show tables" | wc -l
     for T in oc_filecache oc_mail_accounts oc_mail_mailboxes oc_mail_messages oc_users oc_calendarobjects oc_cards oc_migrations oc_appconfig; do
       printf "%s=%s\n" "$T" "$(mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -B nextcloud -e "select count(*) from $T")"
     done' 2>/dev/null | tee $B/rows-post.txt
   diff $B/rows-pre.txt $B/rows-post.txt     # only INCREASES allowed (migrations, new mail, new tables)
   ```
2. **CONTENTS ASSERTION: Mail still talks IMAP through the updated app** —
   measured by `php occ mail:account:diagnose <id>` for every id in
   `$B/mail-account-ids.txt`, compared to `$B/mail-diagnose-pre.txt`: each
   account authenticates and lists the same mailbox count. This exercises Mail
   5.11.5's code and `vendor/` end to end — the exact thing that broke in 2026-06.
   Then the operator opens Mail in a browser and reads one message body.
3. **CONTENTS ASSERTION: live push works end to end** — measured by the
   self-test's *"push server is receiving redis messages"* + *"can connect to
   the Nextcloud server"* + *"same version"* lines all green: a real write
   through redis to the rebuilt notify-push container, not a `PONG`.
4. **CONTENTS ASSERTION: the exporter still scrapes the upgraded instance** —
   measured over a window that starts after the rollout, compared to the
   version label before the change:
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 &
   Q='http://localhost:9090/api/v1/query'
   curl -s $Q --data-urlencode 'query=count by (__name__)({__name__=~"nextcloud_.*"})' | python3 -c "import sys,json;print(len(json.load(sys.stdin)['data']['result']),'nextcloud_* series')"   # > 0
   curl -s $Q --data-urlencode 'query=min_over_time(nextcloud_up[10m])' | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['result'])"   # value "1"
   curl -s $Q --data-urlencode 'query=nextcloud_system_info' | python3 -c "import sys,json;[print(r['metric'].get('version')) for r in json.load(sys.stdin)['data']['result']]"   # 34.0.4.x
   curl -s $Q --data-urlencode 'query=nextcloud_users_total' | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['result'][0]['value'][1])"   # > 0, equals the oc_users count above
   ```
   (Series names are the upstream exporter's documented ones; the first query
   lists what actually exists — adapt the label if the exporter renames it,
   do not skip the assertion.)
5. **Attended:** operator opens Files, Mail, Calendar on a phone and the
   whiteboard once (the CODE app was rebuilt in 3.2 — open one office document).

## 5) Rollback

Three tiers, in order of likelihood. Decide by evidence, not by reflex.

**5.1 Stuck maintenance mode and/or a broken app after `occ upgrade` (the
documented failure).** Symptoms: `occ status` shows `maintenance: true`, or
every `occ` fails with a PHP autoload error naming `custom_apps/<app>/vendor`,
cron pods `Error`, `status.php` still 200. Recipe (in the running pod,
container `nextcloud`):

```bash
# 1. get occ loading at all — move the half-extracted app aside
$OCC 'mv /var/www/html/custom_apps/<app> /var/www/html/custom_apps/<app>.broken'
$OCC 'php occ status'
# 2. finish what the entrypoint could not
$OCC 'php occ upgrade'
$OCC 'php occ maintenance:mode --off'
# 3. reinstall the app cleanly from the appstore
$OCC 'rm -rf /var/www/html/custom_apps/<app>.broken'
$OCC 'php occ app:install <app>'          # re-downloads, re-enables
# 4. re-run §4 in full; re-force-enable anything that moved to Disabled
$OCC 'php occ app:enable --force <app>'
```

If it was `notify_push`: after `app:install`, `kubectl -n office rollout
restart deploy/nextcloud-notify-push` so the container picks up the rebuilt
binary, then self-test.

**5.2 The startup probe killed the container mid-`occ upgrade`.** The kubelet
restarts it; the entrypoint now sees `version.php` == image version (it is
copied *last*, before `occ upgrade`) so it skips rsync+upgrade and starts
Apache with Nextcloud still in maintenance. Do NOT let Flux or a rollback
"help": with `retries: 0` it will not. Run `$OCC 'php occ upgrade'` then
`maintenance:mode --off`; if an app dir is half-extracted → §5.1. If the kill
happened *during the rsync* instead (log has no `Initializing finished`;
`version.php` still `34,0,3,2`), nothing was migrated — a plain revert (5.3a)
is enough.

**5.3 Full rollback to 34.0.3 — only if the instance must go back in time.**
A bare `git revert` is **not** a rollback once `occ upgrade` ran: the
entrypoint (line 184) exits 1 with *"the version of the data (34.0.4.x) is
higher than the docker image version (34.0.3.x) and downgrading is not
supported"* and the pod crash-loops. Rollback therefore restores the data
first:

```bash
# (a) freeze GitOps and stop every writer of the two volumes
flux suspend kustomization -n office nextcloud && flux suspend helmrelease -n office nextcloud
kubectl -n office scale deploy/nextcloud deploy/nextcloud-notify-push --replicas=0
kubectl -n office patch cronjob nextcloud-cron -p '{"spec":{"suspend":true}}'
kubectl -n office wait --for=delete pod -l app.kubernetes.io/name=nextcloud,app.kubernetes.io/component=app --timeout=5m

# (b) database: back to the §2.3 dump (mariadb keeps running; it was never restarted)
kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -e "DROP DATABASE nextcloud; CREATE DATABASE nextcloud CHARACTER SET utf8mb4 COLLATE utf8mb4_bin"'
kubectl exec -i -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" --default-character-set=utf8mb4' < "$D" 2>&1 | tail -5
# re-run the §2.2 row-count loop and diff against rows-pre.txt: must be IDENTICAL

# (c) code + custom_apps + config: revert PVC nextcloud-config to the §2.4 snapshot.
#     Longhorn UI -> Volume nextcloud-config -> (volume is detached now) -> Attach in
#     Maintenance Mode -> Snapshots -> nextcloud-config-pre-34-0-4 -> Revert -> Detach.
#     If the snapshot is gone (02:30 cleanup ran), restore last night's backup into a
#     NEW volume and rebind the PV per docs/sops/disaster-recovery.md + longhorn.md.
#     (Either way the volume must have NO consumers — that is what (a) guarantees.)

# (d) git: revert the bump commit(s), so the 34.0.3 spec meets 34.0.3 data
git revert --no-edit <bump-sha> [<retries-restore-sha>]
git show --stat HEAD && git push origin main
kubectl -n office patch cronjob nextcloud-cron -p '{"spec":{"suspend":false}}'
flux resume helmrelease -n office nextcloud && flux resume kustomization -n office nextcloud
# Flux re-applies replicas: 1; then §4 floor + occ status (34.0.3.2, maintenance false)
# + notify_push self-test + the row-count diff == rows-pre.txt
```

Note the appstore updates from §3.2 also live on that volume; the snapshot
revert takes them back too (Mail 5.10.12 etc.), consistent with the DB dump.
If the image bump is abandoned *before* §3.3 but after §3.2, nothing needs
reverting: every updated app declares NC 32-35 compatibility and runs fine on
34.0.3 — just roll notify-push so its binary matches its app.

## 6) Interference notes

- **Attended weekend slot only; never `nightly`.** Not because of duration
  (45 min fits) but because §3.4 needs eyes on a log with a 360 s deadline and
  §5.1 is a hands-on repair. The deny rule says the same in fewer words.
- **Shared RWX volume.** `pvc/nextcloud-config` is mounted by
  `deployment/nextcloud`, `deployment/nextcloud-notify-push` and every
  `nextcloud-cron` Job (RWX, Longhorn share-manager/NFS — so notify-push's
  default RollingUpdate is safe here, no multi-attach). §3.2 rewrites
  `custom_apps/` under all three at once; that is why cron may print one
  transient error during the seconds an app is being replaced. Expected.
- **Cron every 5 min.** Jobs that start while `occ upgrade` holds maintenance
  mode exit non-zero → `KubeJobFailed`-class alerts; the §2.5 silence covers
  `namespace=office`. Do not suspend the CronJob for the normal path (it is
  the first post-upgrade contents signal); §5.3 suspends it only for the
  restore.
- **Consumers that will see a 2-5 min 503:** `office/nextcloud-mcp` (bridge
  for OpenClaw), `ai/openclaw` mail + calendar skills (Juno's morning briefing
  reads Mail — do not run this during the 07:00 briefing), the Homepage
  widget, phones' DAV sync, the whiteboard front-end. None need action; all
  reconnect. `notify_push` reconnects on its own once the server answers.
- **CODE restart.** `richdocumentscode` is replaced in §3.2 — any office
  document open in a browser at that moment reloads. Say so before starting.
- **Not restarted, deliberately:** `nextcloud-redis` (own deny rule; sessions
  survive, §1.5) and `nextcloud-mariadb` (written, not bounced). A window agent
  that sees redis client churn in metrics during §3.4 is seeing reconnects,
  not a restart — `kubectl -n office get pod -l app=nextcloud-redis` shows
  the same pod, restarts 0.
- **`conflicts_with: bitnamilegacy-exit-nextcloud-db`** — same
  `helmrelease.yaml`, same Deployment restart, and that plan replatforms the
  very DB this plan dumps from. It is `blocked`/unwindowed today; if it is
  revived, run this plan first (a smaller, reversible change on the known
  server) and let that one start from 34.0.4.
- **Same-namespace neighbours** (mealie-v3.26.0, a future nextcloud-mcp plan,
  paperless-*): no shared resource, but do not run them *in parallel* in the
  same slot — the §2.5 silence is namespace-wide and would mask their rollout
  noise too. Sequential is fine.
- **Step 0 of the same window** may auto-bump `nextcloud-mcp` (patch lane).
  Independent; no ordering constraint either way.
- **Longhorn housekeeping.** The two §2.4 snapshots are removed by the 02:30
  `global-snapshot-cleanup` the next night; that is intended (the dump and the
  nightly backup are the durable floor). Do not "fix" it by adding retain rules.
- **Timing math is a premise.** `startup-probe-budget-is-unchanged` exists
  because the entire §3.2 rationale is a number; if someone raises the
  threshold before this runs, the plan still works — it just has more slack.
