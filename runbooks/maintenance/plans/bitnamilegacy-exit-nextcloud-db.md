---
plan_id: bitnamilegacy-exit-nextcloud-db
component: nextcloud
pr: null                               # archived registry — no upstream tag can fix it
kind: chart                            # HelmRelease values + new sibling manifests + storage
current: "bundled bitnamilegacy/mariadb:latest (server 11.8.2-MariaDB) on PVC nextcloud-mariadb"
target: "mariadb:11.8.8 (Docker Official Image) as deployment/nextcloud-db on a NEW volume nextcloud-db-data"
update_type: major                     # datastore replacement (image lineage + datadir + uid)
risk: high                             # the household's primary file server; occ migrations
est_duration_min: 80
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud                     # mariadb.enabled:false + externalDatabase.host
    - "new: deployment/nextcloud-db + service/nextcloud-db"
    - "new: pvc/nextcloud-db-data + pv/nextcloud-db-data + longhorn volume nextcloud-db-data (manual apply)"
    - statefulset/nextcloud-mariadb             # REMOVED by the chart
    - deployment/nextcloud                      # full restart; loses the mariadb-isalive initContainer
    - deployment/nextcloud-notify-push          # restarts with the stack
    - deployment/nextcloud-metrics              # restarts with the stack
    - pvc/nextcloud-mariadb                     # orphaned, Retain — the rollback data
  shared: [storage]                             # allocates a new 2-replica Longhorn volume
depends_on: [bitnamilegacy-exit-nextcloud-redis, bitnamilegacy-exit-paperless-db]
                                                # RESOLVED 2026-08-19:
                                                # bitnamilegacy-exit-nextcloud-redis EXECUTED
                                                # (d6070b82) — dependency satisfied
conflicts_with: [longhorn-1.12.1-engine, bitnamilegacy-exit-paperless-db, bitnamilegacy-exit-nextcloud-redis]
                                                # nextcloud-redis EXECUTED 2026-08-19; the only
                                                # residual coupling is the shared HelmRelease
security_ref: F-cb42f390                        # see also F-90dd1a52 (same image, fixable class)
status: blocked                                 # ROLLED BACK 2026-08-19 (revert d1dbbdd1).
                                                # Root cause + required fix in 3c. Do not
                                                # re-run until the dump is proven to carry
                                                # 4-byte characters.
window: "sat-early:2026-09-12"                 # RESHUFFLED 2026-08-16 onto the daily-window cadence
                                      # (7 windows/week, was 4). Deliberate soaks are
                                      # preserved, not compressed — see the windows YAML.
                                                # how to pull this forward — 2 months on an
                                                # archived registry is the cost of waiting
auto_execute: false                             # *mariadb* AND *nextcloud* are both deny-listed
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/mariadb-major-upgrade.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
  - docs/sops/longhorn.md
generated: "2026-08-15"
---

# bitnamilegacy exit, phase 4/5 — Nextcloud off the bundled Bitnami MariaDB

## 1) Summary & why held

Phase 4 of 5 (the last of the four office phases), and the last `bitnamilegacy` image in the cluster once
`superset-pg-decommission` has also run. Same operation as phase 3, on a bigger
and far more consequential database: **206 tables, ~1.2 GB, the household's
files, shares, calendars, contacts and mail accounts.** Phase 3 exists so this
one is a repeat, not a first attempt.

**Why this is held and can never be auto-applied — two independent deny rules.**
`runbooks/auto-update-policy.yaml` denies both `*mariadb*` and `*nextcloud*`:

> `*mariadb*` — "A DB-engine bump is never unattended-safe. The bitnami
> entrypoint can SKIP `mariadb-upgrade` on a server-major roll while reporting
> Ready and the right `SELECT VERSION()` — leaving old-format system tables under
> the new binary."
>
> `*nextcloud*` — "chart+image must bump together and run occ migrations (Mail
> custom_app / stuck-maintenance trap) — operator-supervised only."

**Why no version bump can fix this.** The HelmRelease pins
`docker.io/bitnamilegacy/mariadb:latest`. `bitnamilegacy` is Bitnami's
**archived** catalog: the free images were moved there on 2025-08-28 and nothing
has been published since; it exists "solely to help with migration" and receives
no updates or patches, ever. `latest` there is a frozen tag pretending to be a
rolling one — the pod runs **11.8.2-MariaDB** and always will.
`docker.io/bitnami/mariadb` is not a fallback (digest-only, no semver stream for
Renovate). The only remediation is to leave the registry.

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-cb42f390** and **F-90dd1a52** (both `bitnamilegacy/mariadb:latest`).
> Counts, CVE identifiers and exposure live on the finding records — they are
> deliberately not reproduced here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-cb42f390`
> - CLI: `runbooks/policy-cli.py finding show F-cb42f390`
>
> See `docs/sops/vulnerability-disclosure.md` before adding any vulnerability
> detail to a committed file.

### A second bitnamilegacy container hides on the Nextcloud pod itself

`deployment/nextcloud` currently runs an initContainer **`mariadb-isalive`** on
`docker.io/bitnamilegacy/mariadb:latest` — emitted by nextcloud chart 9.2.5's
`templates/deployment.yaml` whenever `mariadb.enabled` is true. It disappears
automatically with `mariadb.enabled: false`; no manual edit is needed, but the
window agent should expect the Nextcloud pod's init list to shrink by one, and
Verification asserts it is gone.

### What actually changes, and what deliberately does not

| | now | after |
|---|---|---|
| image | `bitnamilegacy/mariadb:latest` | `mariadb:11.8.8` (Docker Official Image) |
| **server version** | **11.8.2** | **11.8.8 — same LTS series** |
| datadir | `/bitnami/mariadb/data` | `/var/lib/mysql` |
| runtime uid | 1001 (bitnami) | 999 (mysql) |
| volume | `nextcloud-mariadb` (kept, untouched) | `nextcloud-db-data` (new) |
| server charset | `utf8mb3` / `utf8mb3_general_ci` | **pinned to the same** |
| nextcloud image | `nextcloud:34.0.2` | **unchanged — deliberately** |
| chart version | 9.2.5 | **unchanged — deliberately** |

**The Nextcloud image and chart do not move in this window.** That is the single
most important scoping decision here: the deny-list reason for `*nextcloud*` is
occ migrations, and the recorded failure mode (memory
`project_nextcloud_upgrade_mailapp`) is an image bump running occ migrations that
break the Mail custom_app and stick maintenance mode. By holding image and chart
still, this window contains **zero** schema migrations — it is a byte-for-byte
logical restore of the same schema under a different server binary. Any occ
schema work is a separate, later plan.

**This is also not a MariaDB major upgrade** — 11.8.2 → 11.8.8 is a patch move
inside the 11.8 LTS series. The risk is the replatform (datadir layout, uid,
dump/restore), not a system-table format transition.

### The verification trap that must not be skipped

`docs/sops/mariadb-major-upgrade.md` is explicit that **every signal an operator
normally trusts can lie**: `Ready=True`, a correct `SELECT VERSION()` and a
running pod are all compatible with old-format system tables underneath, because
the entrypoint can log *"This installation is already upgraded"* and move on. So
Verification checks the **datadir marker** (`/var/lib/mysql/mariadb_upgrade_info`)
and runs `mariadb-check --all-databases`, not just `SELECT VERSION()`. If a
manual upgrade is ever needed it must run **over the socket**
(`mariadb-upgrade --protocol=socket --skip-ssl`) — the SOP records that the
default TLS/TCP loopback resets mid-run, half-applies the privilege migration and
emits hundreds of misleading `server has gone away` errors; two runs failing at
*different* script lines is the tell that it is transport, not a bad statement.

### The charset trap

Read on the live cluster 2026-08-15:

```
@@character_set_server = utf8mb3      @@collation_server = utf8mb3_general_ci
schema `nextcloud`     = utf8mb3 / utf8mb3_general_ci     (206 tables)
@@innodb_file_per_table = 1           @@log_bin = 0
```

MariaDB 11.5+ changed the default server collation; the official 11.8 image
initialises a fresh datadir as `utf8mb4` with a `uca1400` collation. Unpinned,
the entrypoint would create `nextcloud` as utf8mb4 while the dump restores
utf8mb3 tables into it — a silently mixed schema, and Nextcloud is *particularly*
unforgiving here (it reports 4-byte support and index-length behaviour off the
schema). The new Deployment therefore pins
`--character-set-server=utf8mb3 --collation-server=utf8mb3_general_ci` so this
window changes the **image and nothing else**. Converting Nextcloud to utf8mb4
(`occ db:convert-mysql-charset`) is a real improvement and a **separate** plan.

### One thing phase 3 needed and this one does not

Nextcloud's credentials already live in our own SOPS secret. `nextcloud-config`
carries `db-username`, `db-password`, `mariadb-root-password`,
`mariadb-password` and `mariadb-replication-password`, and
`externalDatabase.existingSecret` already points the app at `db-username` /
`db-password`. **No SOPS edit is required in this window** — the chart-generated
secret problem that phase 3 had does not exist here.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) phases 2 and 3 have landed
mise exec -- kubectl get deploy -n office nextcloud-redis paperless-db \
  -o custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image
# redis:8.10.0-alpine and mariadb:11.8.8 — phase 3 is the rehearsal for this one.
# If phase 3 was rolled back, DO NOT run this plan.

# b) current state of the source DB
mise exec -- kubectl get sts -n office nextcloud-mariadb \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # bitnamilegacy/mariadb:latest
mise exec -- kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- mariadb --version

# c) RECORD THE BASELINE.
#    Every artefact this plan writes goes to ~/db-dumps, NOT /tmp — see 3b.
#    The row-count baselines are load-bearing (they are diffed before the app is
#    allowed up) and /tmp on a multi-user Mac is world-readable. The path is
#    written out literally rather than held in a shell variable, because this
#    plan is executed in separate blocks and a fresh shell would silently
#    resolve an unset variable to / .
umask 077 && mkdir -p ~/db-dumps && chmod 700 ~/db-dumps
#
#    Note the root password is delivered as a FILE here
#    (MARIADB_ROOT_PASSWORD_FILE), not an env var — that is why every command
#    below uses "$(cat $MARIADB_ROOT_PASSWORD_FILE)".
mise exec -- kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -e "
     select @@version, @@character_set_server, @@collation_server, @@innodb_file_per_table, @@log_bin;
     select table_schema, count(*) from information_schema.tables group by 1;
     select schema_name, default_character_set_name, default_collation_name from information_schema.schemata;
     select count(*) from mysql.user;"' | tee ~/db-dumps/nextcloud-db-baseline.txt
mise exec -- kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -e "
     select table_name, table_rows, table_collation from information_schema.tables
     where table_schema=\"nextcloud\" order by table_name;"' | tee ~/db-dumps/nextcloud-db-tables-before.txt
wc -l ~/db-dumps/nextcloud-db-tables-before.txt        # expect 206 rows

#    *** EXACT row counts for ALL 206 tables — the binding acceptance test ***
#    `table_rows` above is an InnoDB ESTIMATE; it is fine for the table LIST and
#    the collations and useless as evidence that data arrived. Generate one
#    count(*) per table and keep the output:
#    (single-quoted body: everything runs INSIDE the pod, so the password never
#     enters kubectl argv, the API-server audit log or your shell history.
#     MYSQL_PWD rather than -p"$P" so it is not in the in-pod process argv
#     either — `-p<value>` is visible to `ps` inside that PID namespace, and
#     these loops fork ~206 short-lived clients.)
mise exec -- kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c '
  export MYSQL_PWD=$(cat "$MARIADB_ROOT_PASSWORD_FILE")
  for T in $(mariadb -uroot -N -B -e "select table_name from information_schema.tables where table_schema=\"nextcloud\" and table_type=\"BASE TABLE\" order by table_name"); do
    printf "%s=%s\n" "$T" "$(mariadb -uroot -N -B nextcloud -e "select count(*) from \`$T\`")"
  done' > ~/db-dumps/nextcloud-rows-before.txt
wc -l ~/db-dumps/nextcloud-rows-before.txt            # expect 206
awk -F= '{s+=$2} END {print "total rows:", s}' ~/db-dumps/nextcloud-rows-before.txt
#    Record that total. It is the number the restore must reproduce.

# d) SIZE THE WORK — this decides whether 85 min is right
mise exec -- kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -e "
     select round(sum(data_length+index_length)/1024/1024) as mb
     from information_schema.tables where table_schema=\"nextcloud\";"'
mise exec -- kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- df -h /bitnami/mariadb
# If the schema is much over ~2 GB, re-estimate the window BEFORE starting.
# `oc_filecache` and `oc_activity` dominate and grow without bound.

# e) APPLICATION baseline — the numbers Verification must reproduce exactly
mise exec -- kubectl exec -n office deploy/nextcloud -- \
  su -s /bin/sh www-data -c 'php occ status' | tee ~/db-dumps/nextcloud-app-baseline.txt
mise exec -- kubectl exec -n office deploy/nextcloud -- \
  su -s /bin/sh www-data -c 'php occ user:list | wc -l; php occ app:list | head -60' \
  | tee -a ~/db-dumps/nextcloud-app-baseline.txt
# `occ app:list` MUST show openclaw_mail under Enabled — that is the custom app
# whose loss is the documented Nextcloud-upgrade failure mode.
mise exec -- kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -e "
     select (select count(*) from nextcloud.oc_filecache),
            (select count(*) from nextcloud.oc_users),
            (select count(*) from nextcloud.oc_share),
            (select count(*) from nextcloud.oc_mail_accounts);"' | tee -a ~/db-dumps/nextcloud-app-baseline.txt

# f) Longhorn backup of the source volume — the disaster floor. The logical dump
#    in step 2 is the WORKING rollback; this is the layer beneath it.
#    The storage/backup-of-all-volumes CronJob runs nightly at 03:00, so in a
#    09:00 window there is normally already a backup ~6h old:
mise exec -- kubectl get volume -n storage nextcloud-mariadb nextcloud-main nextcloud-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt
# nextcloud-mariadb's lastBackupAt must be within the last 24h. If it is not,
# trigger one and WAIT — but budget for it, a full-cluster backup run can take a
# long time (docs/sops/backup.md §Pre-Upgrade Backup Procedure):
#   mise exec -- kubectl create job --from=cronjob/backup-of-all-volumes \
#     pre-nextcloud-db-$(date +%Y%m%d) -n storage
#   mise exec -- kubectl wait --for=condition=complete job/pre-nextcloud-db-$(date +%Y%m%d) \
#     -n storage --timeout=3600s

# g) the old volume is Retain and there is room for a new one
mise exec -- kubectl get pv nextcloud-mariadb \
  -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy,SC:.spec.storageClassName
# MUST read Retain / longhorn-static. If not, STOP — docs/sops/storage-safety.md.
mise exec -- kubectl get nodes.longhorn.io -n storage \
  -o custom-columns=NAME:.metadata.name,READY:.status.conditions[?\(@.type==\"Ready\"\)].status

# h) the target tag exists
curl -s "https://hub.docker.com/v2/repositories/library/mariadb/tags?page_size=100&ordering=last_updated&name=11.8" \
  | python3 -c "import sys,json;print([t['name'] for t in json.load(sys.stdin)['results']][:12])"   # 11.8.8 present

# i) nobody is mid-upload. 09:00 Saturday is NOT 05:00 — check for active sessions.
mise exec -- kubectl logs -n office deploy/nextcloud --since=10m | grep -iE 'PUT|upload' | tail
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3a) SEQUENCING ENFORCEMENT — added 2026-08-19, read before §3

**The single most important finding of the 2026-08-19 window**, learned the hard
way on the paperless sibling (`bitnamilegacy-exit-paperless-db`, commit
`4604c711`) and confirmed independently during an unrelated containment the same
day:

> **`kubectl scale ... --replicas=0` DOES NOT HOLD. Flux drift-corrects it back.**

This plan already says the right thing in prose — quiesce, dump, replatform,
restore, *then* bring the app up. But the mechanism it uses to hold the app down
(`kubectl scale --replicas=0`) is a manual override of a Flux-managed field, and
Flux reverts it on its next reconcile. Worse, **the reconcile is not incidental:
step 6 pushes a commit and deliberately waits for Flux to apply it.** That same
reconcile restores `replicas: 1`.

The resulting sequence is the failure:

```
scale to 0  ->  push replatform commit  ->  Flux applies it
            ->  Flux ALSO restores replicas: 1
            ->  Nextcloud boots against the EMPTY new datadir
            ->  it runs its own migrations / init
            ->  ONLY THEN does step 7's restore run
```

On paperless this was survivable **only** because `mysqldump --add-drop-table`
drops every table before recreating it, so the restore steam-rollered whatever
the app had just created. **Do not rely on that here.** Nextcloud is materially
worse than paperless in this shape:

- its entrypoint runs schema migrations and can treat an empty database as a
  **fresh install**;
- it persists identity and state (`instanceid`, `secret`, `maintenance`) into
  `config.php` **on the PVC**, which no database restore reverts — the same
  config-on-PVC trap that bit `notify_push` during the redis cutover
  (`d6070b82`);
- a fresh-install path can therefore leave the PVC and the restored database
  disagreeing about which instance this is, which a row-count check will not
  detect.

### Required: make `replicas: 0` the DESIRED state, not an override

Preferred, because it is GitOps-native and cannot race:

1. Set the app's replica count to **0 in the HelmRelease values** in the SAME
   commit as the replatform (step 6). Flux then converges *to* 0; its reconcile
   becomes harmless instead of hostile.

   Verified available 2026-08-19: `kubernetes/apps/office/nextcloud/app/helmrelease.yaml`
   carries `replicaCount: 1` at **line 36** (the app's own value — *not* the
   `replicaCount` further down, which belongs to a subchart), and chart 9.2.5's
   `templates/deployment.yaml` renders `replicas: {{ .Values.replicaCount }}`
   directly from it. So `replicaCount: 0` is a one-line, Flux-native hold.
2. Do the restore (step 7) and run Verification (a)-(d) with the app still down.
3. Only then, a SECOND commit restores the replica count to 1 (step 8).

Acceptable alternative (kept only as a fallback — the value above IS exposed,
so prefer it): `flux
suspend helmrelease -n office nextcloud` **and** `flux suspend kustomization -n
office nextcloud` before scaling to 0, resuming only after (a)-(d) pass. Note
this was verified today: suspending the Kustomization alone is **not** enough —
the HelmRelease-owned Deployment is reconciled back independently, so **both**
must be suspended. It is the weaker option because a suspended HelmRelease also
blocks step 6's own apply, so the suspend must be timed around it.

### Verify the hold actually held

Before running the restore, confirm the app did not come up in the gap:

```bash
mise exec -- kubectl get deploy -n office nextcloud -o jsonpath='{.spec.replicas} {.status.replicas}{"\n"}'   # 0 0
mise exec -- kubectl get pods -n office -l app.kubernetes.io/component=app        # no pods
# and prove it never briefly ran against the empty DB:
mise exec -- kubectl get events -n office --field-selector involvedObject.name=nextcloud --sort-by=.lastTimestamp | tail -20
```

If the app DID start against the empty datadir, do **not** simply carry on
because the restore will drop the tables anyway. Stop, and check `config.php` on
the PVC for a regenerated `instanceid`/`secret` before continuing.

Row counts alone will not catch this class of failure — see
`docs/sops/verification-contents-not-shape.md`, which this plan already applies
to the restore itself. The same principle applies to the *ordering*: a correct
final row count does not prove the app never touched the database first.

## 3b) SENSITIVE ARTEFACTS — what this plan writes to disk, and where it goes

Added 2026-08-19 after a security review of the plan files. The handling below is
now an explicit decision; previously it was simply unexamined.

**What the dump contains.** A `mysqldump` of the `nextcloud` database includes
`oc_users`, whose `password` column holds every user's password hash. It also
carries app credential and token tables. This is not an ordinary data export —
treat the file as a credential store.

**Decision: the dump is RETAINED as the recovery floor.** §5 Rollback step 1
depends on it, and `docs/sops/mariadb-major-upgrade.md` is explicit that the
logical dump is the only rollback that works for this class of change. So it is
deliberately kept, not deleted at the end of the window.

Because it is retained, its handling is stated rather than left implicit:

| | |
|---|---|
| **Location** | `~/db-dumps/nextcloud-<date>.sql` on the operator's Mac — **never** a git-tracked path, never inside a container image, never a shared `/tmp` |
| **Created with** | `umask 077`, in a directory pre-created `chmod 700`, file `chmod 600` (already in step 2 — keep it) |
| **Copied into the pod** | **Never.** Step 7 streams it over stdin; no second copy exists |
| **Removed when** | the migration has soaked and the new volume has its own verified Longhorn backup — i.e. after the first successful nightly `daily-backup-all-volumes` run covering `nextcloud-db-data`, confirmed present. Until then it is the only floor and must not be deleted |
| **Removed how** | `rm -P ~/db-dumps/nextcloud-<date>.sql` (overwrite before unlink), then confirm the directory is empty |

**Do not** move it to cloud storage, attach it to an issue, or paste any part of
it into a report. If it must be inspected, `grep` for schema/structure only.

**Also note the baseline files.** Steps in §2 and §4 `tee` several artefacts to
the operator's `/tmp` — `nextcloud-db-baseline.txt`, `nextcloud-db-tables-*.txt`,
`nextcloud-rows-*.txt`, `nextcloud-app-baseline.txt`. These hold row counts and
schema names, **not** credentials, so they are a much lower grade of exposure —
but `/tmp` on a multi-user Mac is world-readable, and these must be diffed
before the app comes up, so they are load-bearing for the window. **The plan's
commands have been changed to write them under `~/db-dumps/`** alongside the
dump (already `chmod 700`) rather than `/tmp`; remove them with the dump. The
path is written out literally in each command rather than held in a shell
variable, because this plan is run in separate blocks and an unset variable in a
fresh shell would silently resolve to `/`.

> This is a recurring shape in this repo, not a one-off: the same review found
> an SOP instructing operators to decode an Elasticsearch superuser password to
> `/tmp` with no cleanup step. When a procedure writes a secret to disk, the
> location, the mode, and the removal all belong in the procedure.

## 3c) WHY THIS PLAN IS BLOCKED — the dump was lossy (2026-08-19)

Attempt 1 was **rolled back mid-restore, before the app was allowed up**
(replatform `c01b71e2`, revert `d1dbbdd1`). Nextcloud is serving from the
untouched bundled volume. **No data was lost** — the app never came up against
the new server, so nothing was written anywhere but the new, otherwise-unused
volume.

### Root cause

`mariadb-dump` was invoked without `--default-character-set`. The connection
therefore negotiated the **server default**, `utf8mb3`. But the server default
is not what the data is stored in:

- all 206 tables are **`utf8mb4_bin`**
- only the **server and schema DEFAULTS** are `utf8mb3`

So the server transcoded **every 4-byte character to `?` on its way out** into
the dump. Filenames, comments, calendar and contact fields containing emoji or
any other 4-byte codepoint would have been permanently flattened.

### Why it was caught — and how nearly it wasn't

The restore failed with a **duplicate-key error on `oc_reactions`**: two rows
differing only in a 4-byte character had both become `?` and collided on a
UNIQUE index. That error is also the *proof* of corruption — a running server
cannot hold rows that violate its own unique index, so the dump could not have
been a faithful copy.

**Had `oc_reactions` carried no unique index, the restore would have completed
and passed every check this plan defines**: 206/206 tables, 1,816,443/1,816,443
rows, matching per-table collations, `occ status` clean. The corruption is
invisible to row counts *because the rows are all there* — only their contents
are damaged, and the source would then have been decommissioned.

This is the contents-not-shape failure class
(`docs/sops/verification-contents-not-shape.md`) one level deeper than row
counts: **a correct row count, on a correct table count, with correct
collations, over silently transcoded content.**

### The plan's own check pointed the wrong way

Step 2 previously asserted `CREATE DATABASE` in the dump "must carry utf8mb3 /
utf8mb3_general_ci". That is the schema *default*, and it is exactly what a
lossy utf8mb3 dump looks like — the check confirmed the bug instead of catching
it. It has been removed and replaced with a 4-byte round-trip assertion.

### Required before attempt 2

1. `--default-character-set=utf8mb4` on the dump (now in step 2).
2. The 4-byte round-trip assertion (now in step 2): count source rows where
   `char_length <> octet_length`, and confirm the dump still contains real
   `\xf0-\xf4` lead bytes. On 2026-08-19 the source had **6** such rows in
   `oc_reactions` alone; a dump with zero 4-byte sequences is lossy.
3. Re-verify after restore that those same rows still differ in
   `char_length` vs `octet_length` on the TARGET — not just that they exist.
4. The new volume `nextcloud-db-data` and `deploy/nextcloud-db` (scaled to 0)
   are left in place from attempt 1. **Do not delete them** (storage safety);
   attempt 2 should reuse or explicitly re-initialise them, and must not assume
   an empty datadir. A detach alert for that volume is silenced until
   2026-08-24 — the expiry is deliberate, so the decision cannot rot.
5. **Rotate the reused database credential as part of attempt 2** (operator
   decision, 2026-08-19). Four keys in the nextcloud secret share a single
   value, `mariadb-replication-password` among them. It is **not** present in
   public git history, which is what makes it materially less urgent than the
   paperless placeholder rotated the same day — so it was deliberately NOT given
   its own window. Attempt 2 already stands up a fresh server and re-issues the
   application account, so it is the cheap moment to stop the reuse: give each
   key its own generated value. Note the entrypoint will not re-apply a password
   to an existing datadir, so any account that already exists needs an explicit
   `ALTER USER` after the Secret lands — the same ordering the paperless
   rotation used.
   *Not* in scope: the Nextcloud **admin login** credential. That is the
   operator's own sign-in, recorded as a finding for them to action, and it must
   not be rotated by an agent.

### What did work, and should be kept

The two guards added earlier the same day both held: the Flux-native replica
hold (§3a) kept the app at `0 0` through the reconcile, and the
contents-before-shape discipline is what turned a silent corruption into a
loud, attributable failure at the safest possible moment.

## 3) Steps

1. **Marker + silence.** Nextcloud is fully down for most of this window:
   ```bash
   runbooks/update-marker.sh add nextcloud office 3 "mariadb: bitnamilegacy 11.8.2 -> official mariadb:11.8.8"
   ```
   Silence `namespace=office` rollout alerts for 4h per
   `docs/sops/application-update.md` §4 Step 1. Tell the household — this is a
   user-visible outage of files, calendars, contacts and mail.

2. **Maintenance mode ON, then quiesce, then dump.** Maintenance mode first so
   clients stop writing while the app is still able to serve them a clean answer:
   ```bash
   mise exec -- kubectl exec -n office deploy/nextcloud -- \
     su -s /bin/sh www-data -c 'php occ maintenance:mode --on'
   mise exec -- kubectl exec -n office deploy/nextcloud -- \
     su -s /bin/sh www-data -c 'php occ status'          # maintenance: true
   mise exec -- kubectl scale deploy/nextcloud -n office --replicas=0
   mise exec -- kubectl wait --for=delete pod -n office -l app.kubernetes.io/component=app --timeout=300s
   ```
   Take the logical dump — per `docs/sops/mariadb-major-upgrade.md` step 2 this is
   **the only rollback that works**, and it must be protected:
   ```bash
   umask 077 && mkdir -p ~/db-dumps && chmod 700 ~/db-dumps
   D=~/db-dumps/nextcloud-$(date +%F).sql
   mise exec -- kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
     'mariadb-dump -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" \
        --default-character-set=utf8mb4 \
        --single-transaction --routines --triggers --events \
        --databases nextcloud' > "$D"
   chmod 600 "$D"
   ls -l "$D"                       # must NOT be zero bytes
   tail -1 "$D"                     # must read "-- Dump completed"
   grep -c 'CREATE TABLE' "$D"      # expect 206

   # *** THE CHECK THAT MATTERS — see 3c. Row counts cannot see this. ***
   # Every table is utf8mb4_bin; only the server/schema DEFAULTS are utf8mb3.
   # Without --default-character-set=utf8mb4 the connection negotiates utf8mb3
   # and the server transcodes every 4-byte character to '?' ON THE WAY OUT.
   # Prove the dump round-trips 4-byte data before you trust it:
   SRC4=$(mise exec -- kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
     'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" --default-character-set=utf8mb4 -N -B nextcloud -e \
        "select count(*) from oc_reactions where char_length(reaction) <> octet_length(reaction);"')
   echo "source rows with multi-byte data: $SRC4"     # 2026-08-19: 6
   # the dump must still contain real multi-byte bytes, not '?'
   LC_ALL=C grep -c $'[\xf0-\xf4]' "$D" || echo "NO 4-BYTE SEQUENCES IN DUMP — ABORT"
   #    ^ if SRC4 > 0 and this is 0, the dump is LOSSY. Do not restore it.
   ```
   We dump **only the `nextcloud` schema**, not `mysql` — the new server's
   entrypoint creates the user from `MARIADB_USER`/`MARIADB_PASSWORD`, and a
   `mysql`-schema dump would carry `mysql.global_priv` password hashes. Keep the
   file `0600` in a `0700` directory and **do not commit it**.

3. **Add the storage manifests**, per `docs/sops/longhorn.md`: a `longhorn-static`
   volume with a **speaking name** used identically in the Longhorn `Volume` CR,
   the `PV` name, the PV `volumeHandle`, the PVC name and the PVC's `volumeName`
   — `nextcloud-db-data`. Size **10Gi** (the retiring volume is 5Gi at 25% but
   `oc_filecache`/`oc_activity` grow), `numberOfReplicas: 2`,
   `persistentVolumeReclaimPolicy: Retain`, `storageClassName: longhorn-static`.
   New files: `kubernetes/apps/office/nextcloud/app/db-pv.yaml`, `db-pvc.yaml`,
   `db-longhorn-volume.yaml`.

   The Longhorn `Volume` CR must be applied **by hand** and must **not** be in
   `kustomization.yaml` — the app Kustomization's `targetNamespace: office` would
   override its `namespace: storage` and create a broken duplicate Longhorn
   ignores (`CLAUDE.md` §Longhorn):
   ```bash
   mise exec -- kubectl apply -f kubernetes/apps/office/nextcloud/app/db-longhorn-volume.yaml
   mise exec -- kubectl get volume -n storage nextcloud-db-data
   ```

4. **Add the MariaDB manifests** in
   `kubernetes/apps/office/nextcloud/app/db-deployment.yaml` — Deployment +
   Service `nextcloud-db`, modelled on the `paperless-db` manifests phase 3
   already proved:
   - image `mariadb:11.8.8`, `strategy: Recreate`, `replicas: 1`
   - env from `nextcloud-config`:
     `MARIADB_ROOT_PASSWORD` ← `mariadb-root-password`,
     `MARIADB_USER` ← `db-username`,
     `MARIADB_PASSWORD` ← `db-password`;
     plain: `MARIADB_DATABASE: nextcloud`
   - **charset pin — do not omit:**
     ```yaml
     args:
       - --character-set-server=utf8mb3
       - --collation-server=utf8mb3_general_ci
       - --innodb-file-per-table=1
       - --transaction-isolation=READ-COMMITTED
       - --max-connections=200
     ```
     (`READ-COMMITTED` is Nextcloud's documented recommendation for MySQL/MariaDB;
     confirm against the retiring server in pre-check (c) and match whatever it
     actually ran rather than assuming.)
   - PVC `nextcloud-db-data` mounted at `/var/lib/mysql`
   - liveness/readiness `healthcheck.sh --connect --innodb_initialized`,
     `initialDelaySeconds: 45`
   - resources: requests 100m/512Mi, limits 1000m/2Gi (the subchart had
     100m/334M request, 1Gi limit — Nextcloud's DB is the busier of the two)
   - Service `nextcloud-db`, port 3306, ClusterIP
   Register `db-pv.yaml`, `db-pvc.yaml`, `db-deployment.yaml` in
   `kustomization.yaml` `resources:` (**not** the Longhorn Volume CR).

5. **Edit `kubernetes/apps/office/nextcloud/app/helmrelease.yaml`**:
   - `externalDatabase:` — add the host (everything else there is already
     correct: `enabled: true`, `type: mysql`, `database: nextcloud`,
     `existingSecret` → `nextcloud-config` / `db-username` / `db-password`):
     ```yaml
         externalDatabase:
           enabled: true
           type: mysql
           host: nextcloud-db
           database: nextcloud
           ...
     ```
     From chart 9.2.5 `templates/_helpers.tpl`, `MYSQL_HOST` comes from
     `.Values.externalDatabase.host` only once `mariadb.enabled` is false —
     until then the `{{- else if .Values.mariadb.enabled }}` branch wins and the
     host is templated from the subchart. Both edits must be in the same commit.
   - Replace the whole `mariadb:` values block (around line 464) with:
     ```yaml
         # Bundled Bitnami mariadb retired 2026-XX-XX: bitnamilegacy is an
         # ARCHIVED registry (last push 2025-08-28, no future security fixes) and
         # docker.io/bitnami/mariadb publishes no semver tags (digest-only).
         # Security driver tracked as F-cb42f390. Nextcloud now uses the official
         # mariadb image deployed by db-deployment.yaml in this folder, reached
         # via externalDatabase.host above. Disabling this ALSO removes the
         # chart's `mariadb-isalive` initContainer, which was the last
         # bitnamilegacy container on the nextcloud pod itself.
         # Server charset is PINNED to utf8mb3/utf8mb3_general_ci to match the
         # retired server — see the plan; utf8mb4 is a separate migration.
         mariadb:
           enabled: false
     ```
   - Update the `wait-for-mariadb` initContainer (around line 214) to
     `until nc -z nextcloud-db 3306; do` and fix its echo string. Leave
     `wait-for-redis` and `install-openclaw-mail` untouched.

6. **Validate, commit, push** (on `main`, stage only the files you touched):
   ```bash
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas \
     kubernetes/apps/office/nextcloud
   git add kubernetes/apps/office/nextcloud/app/db-deployment.yaml \
           kubernetes/apps/office/nextcloud/app/db-pv.yaml \
           kubernetes/apps/office/nextcloud/app/db-pvc.yaml \
           kubernetes/apps/office/nextcloud/app/db-longhorn-volume.yaml \
           kubernetes/apps/office/nextcloud/app/kustomization.yaml \
           kubernetes/apps/office/nextcloud/app/helmrelease.yaml
   git commit -m "feat(nextcloud): replatform mariadb from archived bitnamilegacy to official mariadb:11.8.8"
   git push
   ```
   Flux reconciles: the new MariaDB initialises an empty datadir and the bundled
   StatefulSet is removed. Nextcloud is still scaled to 0 — keep it there.

   > **"Keep it there" is not self-enforcing. See §3a — the commit you just
   > pushed is exactly what brings the app back up against the empty datadir.**
   > Do not proceed past this point until `replicas: 0` is the state Flux is
   > actively converging TO, not a manual override it is about to undo.

7. **Restore into the new server** before letting Nextcloud near it.

   **Stream the dump over stdin — do NOT `kubectl cp` it into the pod.** See
   §3b: this dump contains `oc_users` password hashes, and streaming means no
   plaintext copy is ever written to a second disk, so there is no file to
   permission and none to forget to delete.
   ```bash
   mise exec -- kubectl rollout status deploy/nextcloud-db -n office --timeout=900s
   NEW=$(mise exec -- kubectl get pods -n office -l app=nextcloud-db -o jsonpath='{.items[0].metadata.name}')

   # -i streams $D into the client's stdin; nothing lands on the pod filesystem.
   mise exec -- kubectl exec -i -n office $NEW -- sh -c \
     'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD"' < "$D" 2>&1 | tail -30
   # Read every warning. Grant/definer warnings are benign; ERROR lines are not.

   # prove nothing was left behind by an earlier/aborted attempt:
   mise exec -- kubectl exec -n office $NEW -- sh -c 'ls -l /tmp/*.sql 2>/dev/null || echo "no dump on pod fs (expected)"'
   ```
   > **Fallback, only if streaming is impractical** (very large dump timing out
   > the exec): copy it, but then the file is your responsibility —
   > ```bash
   > mise exec -- kubectl cp "$D" office/$NEW:/tmp/restore.sql
   > mise exec -- kubectl exec -n office $NEW -- chmod 600 /tmp/restore.sql
   > # ... restore ...
   > mise exec -- kubectl exec -n office $NEW -- rm -f /tmp/restore.sql
   > mise exec -- kubectl exec -n office $NEW -- sh -c 'ls /tmp/restore.sql 2>/dev/null && echo "STILL PRESENT — remove it" || echo removed'
   > ```
   > `kubectl cp` does not guarantee a restrictive mode, so `chmod` explicitly,
   > and **verify** the removal rather than assuming the `rm` ran — if the
   > restore errors or you abort between the two commands, the file survives.
   > Note the pod filesystem is ephemeral (a restart discards it), which limits
   > but does not eliminate the exposure.
   **Run Verification (a)–(d) here, with Nextcloud still at 0 replicas.** Do not
   bring the app up onto an unverified restore.

8. **Bring Nextcloud back and leave maintenance mode**:
   ```bash
   mise exec -- kubectl scale deploy/nextcloud -n office --replicas=1
   mise exec -- kubectl rollout status deploy/nextcloud -n office --timeout=900s
   mise exec -- kubectl exec -n office deploy/nextcloud -- \
     su -s /bin/sh www-data -c 'php occ maintenance:mode --off'
   mise exec -- kubectl exec -n office deploy/nextcloud -- \
     su -s /bin/sh www-data -c 'php occ status'          # maintenance: false
   ```
   **Do NOT run `occ upgrade`, `occ db:add-missing-*` or
   `occ maintenance:repair` in this window.** The schema is a byte-for-byte
   restore of a schema Nextcloud 34.0.2 was already happy with; running migration
   helpers here is the exact move that sticks maintenance mode and breaks the
   Mail custom_app (memory `project_nextcloud_upgrade_mailapp`). If `occ status`
   *asks* for an upgrade, something is wrong with the restore — stop and roll
   back rather than migrating forward.

9. Clear the marker and drop the silence on success:
   `runbooks/update-marker.sh clear nextcloud`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
NEW=$(mise exec -- kubectl get pods -n office -l app=nextcloud-db -o jsonpath='{.items[0].metadata.name}')

# --- run (a)-(d) with nextcloud still at 0 replicas ---

# a) the release reconciled and the old objects are gone
mise exec -- kubectl get hr -n office nextcloud \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'   # True 9.2.5
mise exec -- kubectl get sts -n office | grep -i nextcloud || echo "bundled mariadb StatefulSet gone (expected)"
mise exec -- kubectl get deploy -n office nextcloud-db \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'      # mariadb:11.8.8
mise exec -- kubectl get pvc -n office nextcloud-db-data             # Bound
mise exec -- kubectl get volume -n storage nextcloud-db-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness

# b) *** THE MARIADB TRAP — version alone is NOT sufficient ***
mise exec -- kubectl exec -n office $NEW -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "select version();"'
mise exec -- kubectl exec -n office $NEW -- cat /var/lib/mysql/mariadb_upgrade_info
#    ^ CORRECTED 2026-08-19 from phase 3's execution: MariaDB 11.8 writes the marker
#      as `mariadb_upgrade_info`. The old `mysql_upgrade_info` path does not exist on
#      this image, so `cat` exits 1 — which reads exactly like the trap this check is
#      meant to catch, and will send you chasing a non-existent problem. Cross-check
#      with `mariadb-upgrade ... --check-if-upgrade-is-needed`, which prints
#      "already upgraded to <version>" and exits 1 when nothing is due.
#    ^ MUST show 11.8.8. If it lags, run the upgrade BY HAND OVER THE SOCKET:
#        mise exec -- kubectl exec -n office $NEW -- sh -c \
#          'mariadb-upgrade --protocol=socket --skip-ssl -uroot -p"$MARIADB_ROOT_PASSWORD"'
#      Expect all 8 phases. NEVER over the default TLS/TCP loopback — it resets
#      mid-run and half-applies the privilege migration.
mise exec -- kubectl exec -n office $NEW -- sh -c \
  'mariadb-check --protocol=socket --all-databases -uroot -p"$MARIADB_ROOT_PASSWORD"' | grep -v ' OK$' | head
#    ^ every table must be OK; the grep should print (almost) nothing.

# c) charset did NOT drift
mise exec -- kubectl exec -n office $NEW -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "
  select @@version, @@character_set_server, @@collation_server, @@innodb_file_per_table, @@transaction_isolation;
  select schema_name, default_character_set_name, default_collation_name
    from information_schema.schemata where schema_name=\"nextcloud\";"'
# MUST read utf8mb3 / utf8mb3_general_ci — compare to ~/db-dumps/nextcloud-db-baseline.txt.

# d) THE load-bearing check — the restore is COMPLETE, not merely "successful".
#    *** CONTENTS ASSERTION: exact row counts for ALL 206 tables, diffed against
#    the pre-check baseline, BEFORE nextcloud is allowed back up. ***
#    This is the check the paperless-db incident (2026-08-19) did not have: a
#    brand-new database with all 74 tables and ZERO rows passed pod-Ready,
#    schema-present and HTTP 200 while 714 documents were invisible. Nextcloud
#    behaves identically — it starts happily on a complete, empty schema and
#    simply shows you no files. See docs/sops/verification-contents-not-shape.md.
#    Same form as pre-check (c). NOTE the password source differs between the
#    two pods: the OLD bitnami STS delivers it as a FILE
#    ($MARIADB_ROOT_PASSWORD_FILE); the NEW official image as an ENV VAR.
mise exec -- kubectl exec -n office $NEW -- sh -c '
  export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"
  for T in $(mariadb -uroot -N -B -e "select table_name from information_schema.tables where table_schema=\"nextcloud\" and table_type=\"BASE TABLE\" order by table_name"); do
    printf "%s=%s\n" "$T" "$(mariadb -uroot -N -B nextcloud -e "select count(*) from \`$T\`")"
  done' > ~/db-dumps/nextcloud-rows-after.txt
wc -l ~/db-dumps/nextcloud-rows-after.txt                                  # 206
diff ~/db-dumps/nextcloud-rows-before.txt ~/db-dumps/nextcloud-rows-after.txt \
  && echo "ALL 206 TABLE COUNTS IDENTICAL — restore is complete"
# `diff` MUST be silent. ANY output: STOP, do not bring nextcloud up, roll back
# (§5). An all-zero right-hand side is the paperless signature — a perfect,
# empty schema. A silent diff over 206 tables is what makes every later check
# meaningful; without it they are all shape.
awk -F= '{s+=$2} END {print "total rows:", s}' ~/db-dumps/nextcloud-rows-after.txt
#   must equal the pre-check total, and must not be ~0.

mise exec -- kubectl exec -n office $NEW -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "
  select table_name, table_rows, table_collation from information_schema.tables
  where table_schema=\"nextcloud\" order by table_name;"' > ~/db-dumps/nextcloud-db-tables-after.txt
diff ~/db-dumps/nextcloud-db-tables-before.txt ~/db-dumps/nextcloud-db-tables-after.txt
# `table_rows` is an InnoDB ESTIMATE and will differ — the TABLE LIST and the
# COLLATIONS must match exactly. 206 tables before, 206 after.
mise exec -- kubectl exec -n office $NEW -- sh -c 'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "
  select (select count(*) from nextcloud.oc_filecache),
         (select count(*) from nextcloud.oc_users),
         (select count(*) from nextcloud.oc_share),
         (select count(*) from nextcloud.oc_mail_accounts);"'
# MUST match ~/db-dumps/nextcloud-app-baseline.txt exactly. oc_filecache is the file
# index — a short count here means a partial restore, and Nextcloud would happily
# start and simply not show your files.

# --- only now bring nextcloud up (step 8), then continue ---

# e) the pod lost its bitnamilegacy initContainer and gained nothing else
mise exec -- kubectl get deploy -n office nextcloud -o json | python3 -c "
import sys, json
s = json.load(sys.stdin)['spec']['template']['spec']
for c in s.get('initContainers', []): print('INIT', c['name'], c['image'])
for c in s['containers']:             print('MAIN', c['name'], c['image'])"
# expect wait-for-mariadb / wait-for-redis / install-openclaw-mail /
# init-redis-session-ini as INIT — NO mariadb-isalive, NO bitnamilegacy anywhere.

# f) cluster-wide sweep: is any bitnamilegacy image left running at all?
mise exec -- kubectl get pods -A -o json | python3 -c "
import sys, json
hits = 0
for p in json.load(sys.stdin)['items']:
    for cs in p['status'].get('containerStatuses', []) + p['status'].get('initContainerStatuses', []):
        if 'bitnamilegacy' in cs['image']:
            hits += 1; print(p['metadata']['namespace'], p['metadata']['name'], cs['image'])
print('remaining bitnamilegacy containers:', hits)"
# Expect ONLY the superset postgresql/redis pods, until the superset stages land.
# Zero once superset-pg-decommission has also run.

# g) THE application check — "a database that starts but that its app cannot use
#    is the failure worth catching" (SOP §Verification Tests)
mise exec -- kubectl exec -n office deploy/nextcloud -- \
  su -s /bin/sh www-data -c 'php occ status'                       # maintenance: false, no "upgrade needed"
mise exec -- kubectl exec -n office deploy/nextcloud -- \
  su -s /bin/sh www-data -c 'php occ user:list | wc -l; php occ app:list | head -60'
# Diff against ~/db-dumps/nextcloud-app-baseline.txt. openclaw_mail MUST still be
# Enabled — the install-openclaw-mail initContainer re-materializes it on every
# boot, so a missing app means that initContainer failed, not the DB.
mise exec -- kubectl exec -n office deploy/nextcloud -- \
  su -s /bin/sh www-data -c 'php occ db:add-missing-indices --dry-run' 2>&1 | tail -20
# DRY RUN only, as a read-only assertion that the schema is complete. It must
# report nothing to add. DO NOT run it for real in this window.
curl -s -o /dev/null -w 'nextcloud %{http_code}\n' --max-time 20 "https://drive.$DOM/status.php"
curl -s --max-time 20 "https://drive.$DOM/status.php" | python3 -m json.tool
# installed:true, maintenance:false, needsDbUpgrade:false, version 34.x
mise exec -- kubectl logs -n office deploy/nextcloud --since=20m | grep -iE 'error|exception|sqlstate' | head -20

# h) operator smoke test — the parts that fail SILENTLY:
#    1. Log in via the web UI; confirm the file tree renders with real content
#       (oc_filecache path) and a thumbnail loads.
#    2. Upload a file, rename it, delete it, restore from trash (locking +
#       filecache write path).
#    3. Open the Mail app and confirm accounts still list and a folder loads
#       (oc_mail_accounts) — see memory project_nextcloud_mail_account_quirks
#       for which IMAP errors are benign.
#    4. Open Calendar and Contacts.
#    5. Confirm a desktop/mobile client syncs.
#    6. Confirm the sidecars reconnected:
mise exec -- kubectl logs -n office deploy/nextcloud-notify-push --since=15m | tail -10
mise exec -- kubectl logs -n office deploy/nextcloud-metrics     --since=15m | tail -10
mise exec -- kubectl logs -n office deploy/nextcloud-mcp         --since=15m | tail -10
#    7. Confirm OpenClaw's draft route still works (openclaw_mail custom app).

# i) the old volume is untouched and still the rollback
mise exec -- kubectl get pv nextcloud-mariadb \
  -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,RECLAIM:.spec.persistentVolumeReclaimPolicy
mise exec -- kubectl get volume -n storage nextcloud-mariadb \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,LASTBACKUP:.status.lastBackupAt

# j) no fixable criticals introduced by the new image
mise exec -- trivy image mariadb:11.8.8 --severity CRITICAL --ignore-unfixed | tail -20
```

Success = **the 206-table exact row-count diff silent before nextcloud comes
back up** (the binding contents assertion — everything below is the floor);
HR Ready on chart 9.2.5 with `nextcloud:34.0.2` unchanged; no
`bitnamilegacy` container on any `office` pod including the Nextcloud
initContainer list; `nextcloud-db` Ready on `mariadb:11.8.8` with the datadir
marker reading **11.8.8** and `mariadb-check` all-OK; charset still
`utf8mb3_general_ci`; 206 tables with matching collations; `oc_filecache` /
`oc_users` / `oc_share` / `oc_mail_accounts` counts identical to the baseline;
`occ status` maintenance false with no upgrade pending; `db:add-missing-indices
--dry-run` clean; `status.php` `needsDbUpgrade:false`; `openclaw_mail` Enabled;
upload/rename/delete/restore and Mail/Calendar/Contacts all working.

### Persisted-config check — MANDATORY (learned 2026-08-19, phase 2b)

**A green HelmRelease is not verification of a hostname change on this app.**
Phase 2b renamed the redis Service and everything went green — HR Ready, pods
Ready, `occ config:system:get redis` reporting the NEW host — while
`nextcloud-notify-push` sat in a reconnect loop against the Service that had
just been deleted.

Cause: Nextcloud persists backing-service hosts as literals in `config.php` on
the `nextcloud-config` PVC. The chart's `*.config.php` overlay (a
`getenv()`-guarded file) is loaded LATER and wins for the main container, which
is why `occ` reports the correct value and the main app is unaffected.
`notify_push` parses `config.php` directly and never sees the overlay, so it
alone keeps the stale literal. This applies to `dbhost` exactly as it applied
to the redis host.

```bash
# BEFORE and AFTER the host cut — read the persisted literal, not the merged value
mise exec -- kubectl exec -n office deploy/nextcloud -c nextcloud -- \
  sh -c "grep -A5 \"'dbhost'\" /var/www/html/config/config.php"

# If it still shows the retired host, refresh it. A plain
# `occ config:system:set dbhost --value=...` is a NO-OP: it compares against the
# MERGED value, which the overlay has already made correct. Nextcloud rewrites
# config.php from the full merged config on ANY write, so use a throwaway key:
mise exec -- kubectl exec -n office deploy/nextcloud -c nextcloud -- \
  su -s /bin/sh www-data -c 'php occ config:system:set zz_touch --value=1'
mise exec -- kubectl exec -n office deploy/nextcloud -c nextcloud -- \
  su -s /bin/sh www-data -c 'php occ config:system:delete zz_touch'

# then roll the consumers that parse config.php themselves, and verify:
mise exec -- kubectl rollout restart deploy/nextcloud-notify-push -n office
mise exec -- kubectl exec -n office deploy/nextcloud -c nextcloud -- \
  su -s /bin/sh www-data -c 'php occ notify_push:self-test'   # must be 6/6 green
```

Adding the env var to the notify-push container does NOT work — tried and
disproven on the live pod in phase 2b (`853bf719`, reverted by `1dabbefd`).

## 5) Rollback

**There is no in-place downgrade of a MariaDB datadir** — but this plan never
upgraded one. The old server's volume was never opened by the new binary, so
rollback is a revert plus a re-bind, with the logical dump as the belt.

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- kubectl scale deploy/nextcloud -n office --replicas=0

git revert --no-edit <nextcloud-db-commit-sha>   # restores mariadb.enabled:true + externalDatabase.host
git push

# the bundled StatefulSet comes back and re-binds the UNTOUCHED nextcloud-mariadb PVC
mise exec -- kubectl rollout status sts/nextcloud-mariadb -n office --timeout=900s
mise exec -- kubectl exec -n office nextcloud-mariadb-0 -c mariadb -- sh -c \
  'mariadb -uroot -p"$(cat $MARIADB_ROOT_PASSWORD_FILE)" -N -e "
     select version();
     select count(*) from information_schema.tables where table_schema=\"nextcloud\";
     select count(*) from nextcloud.oc_filecache;"'
# expect 11.8.2, 206, and the baseline filecache count — nothing wrote to it.

mise exec -- kubectl scale deploy/nextcloud -n office --replicas=1
mise exec -- kubectl rollout status deploy/nextcloud -n office --timeout=900s
mise exec -- kubectl exec -n office deploy/nextcloud -- \
  su -s /bin/sh www-data -c 'php occ maintenance:mode --off; php occ status'
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s --max-time 20 "https://drive.$DOM/status.php" | python3 -m json.tool
```

**If maintenance mode is stuck ON after the revert** (the documented Nextcloud
trap), clear it at the config level rather than fighting occ:
```bash
mise exec -- kubectl exec -n office deploy/nextcloud -- \
  su -s /bin/sh www-data -c 'php occ config:system:set maintenance --value=false --type=boolean'
mise exec -- kubectl exec -n office deploy/nextcloud -- su -s /bin/sh www-data -c 'php occ status'
```
See memory `project_nextcloud_upgrade_mailapp` for the full recovery recipe
(including re-enabling the Mail custom_app).

**If `nextcloud-mariadb` is somehow damaged**, restore in this order:
1. the logical dump from step 2 (`~/db-dumps/nextcloud-<date>.sql`) into a fresh
   datadir on the previous image — `docs/sops/mariadb-major-upgrade.md`
   §Rollback Plan;
2. failing that, the Longhorn backup taken in pre-check (f), per
   `docs/sops/backup.md` §"Restore from Backup" → §"Bind Restored Volume to
   Application". Note `nextcloud-main` and `nextcloud-data` are **not** touched by
   this plan — the files themselves are never at risk here, only the index.

**Storage safety:** `nextcloud-mariadb` and `nextcloud-db-data` are
`longhorn-static` with `reclaimPolicy: Retain` — neither is a CIFS/SMB class, so
a PVC delete cannot reach a share (`docs/sops/storage-safety.md`). Run the
pre-flight one-liner anyway before any PVC deletion. The Longhorn `Volume` CR for
`nextcloud-db-data` was applied by hand and survives the revert; delete it
deliberately only if abandoning.

**Do not delete `nextcloud-mariadb` in this window.** It is the rollback. Retire
it in a later cleanup after a full week clean.

Confirmed back = bundled StatefulSet Running on 11.8.2 with 206 tables and the
baseline `oc_filecache` count, `status.php` `maintenance:false` /
`needsDbUpgrade:false`, files visible, Mail app loading.

## 6) Interference notes

- **Window choice is the weakest part of this plan and the operator should
  challenge it.** `sat-early:2026-10-24` is the **second** free 90-minute
  no-reboot slot (phase 3 takes 10-17). `sat-early` is the only 90-min window
  that is not reboot-reserved — `runbooks/maintenance-windows.yaml` explicitly
  says "push every `needs_reboot:false` plan (kube-prom-stack, mariadb,
  nextcloud\*) to Tue/Thu/Sat" — and 08-22 (kube-prometheus-stack), 08-29
  (app-template-5.0), 09-05 (longhorn engine), 09-12 (superset-pg-cutover),
  09-19 (paperless-ngx-3.0.5, solo), 09-26 (grafana-13-app), 10-03 and 10-10
  (the media plans) are all taken with under 80 free minutes each. **That leaves
  the household's file server on an archived registry for another ten weeks —
  the single biggest cost in this whole programme, and it is a scheduling
  constraint, not a technical one.** If that is unacceptable, the cheapest fix is
  to re-slot *draft* plans rather than compress this one: `grafana-13-app`
  (09-26) and `media-naming-p3` (10-10) are both `draft` and both lower-stakes
  than an unpatched datastore. **Do not** move this to `sun-window`: that is the
  only reboot-capable slot and the windows file reserves it deliberately.
- **`conflicts_with: bitnamilegacy-exit-paperless-db`** and
  **`depends_on:` it** — phase 3 is the same operation on a tenth of the data.
  One MariaDB replatform per window, and never this one first. If phase 3 was
  rolled back, this plan is invalid until phase 3 is re-planned. One window of
  separation (10-17 → 10-24) is the minimum: phase 3's rollback volume must have
  been observed clean before the same procedure is repeated here.
- **`depends_on` / `conflicts_with: bitnamilegacy-exit-nextcloud-redis`** —
  phase 2b EXECUTED 2026-08-19 (`d6070b82` + `1dabbefd`), so its
  `redis.enabled: false` / `externalRedis:` wiring is settled and live. The
  only residual coupling is that both plans edit the same HelmRelease: re-read
  the current `redis:` and `externalRedis:` blocks before touching `mariadb:`,
  and do NOT resurrect the subchart values. Note the trap phase 2b hit head-on
  — `redis.auth.enabled: false` had to be RETAINED after disabling the
  subchart, because `_helpers.tpl` still reads it to pick the URL form. Check
  whether any `mariadb.*` value steers the parent chart the same way before
  deleting that block.
- **`conflicts_with: longhorn-1.12.1-engine`** — this plan creates a new Longhorn
  volume and depends on healthy replica scheduling. Never pair storage-engine
  work with new-volume creation.
- **`shared: [storage]`** — allocates a 2-replica `longhorn-static` volume. Do
  not pair with another storage-touching plan.
- **Nextcloud is DOWN, in maintenance mode, for most of this window**, and this
  is a 09:00 Saturday slot, not 05:00. Files, calendars, contacts, mail and every
  sync client are unavailable. Tell the household in advance. Downstream that
  will log errors throughout: `nextcloud-notify-push`, `nextcloud-metrics`,
  `nextcloud-mcp`, `nextcloud-whiteboard`, and OpenClaw's draft path through the
  `openclaw_mail` custom app. None need a manual restart.
- **Explicitly out of scope, and must stay out:** the Nextcloud image (34.0.2)
  and chart (9.2.5) do not move; no `occ upgrade`, no `db:add-missing-*` for
  real, no `maintenance:repair`; no utf8mb3 → utf8mb4 conversion; no MariaDB
  major (11.8 → 12/13). Each is its own plan. Bundling any of them into this
  window re-creates exactly the deny-list scenario the `*nextcloud*` rule exists
  to prevent.
- **After this plan, the only bitnamilegacy images left in the cluster are
  Superset's**, retired by `superset-redis-official` (`thu-early:2026-08-20`) and
  `superset-pg-standup` / `-cutover` / `-decommission`. Verification (f) asserts
  this. Once both tracks finish, the `bitnamilegacy` findings can be closed and
  the AR-029 acceptances covering them retired.
- **Not covered by this phase set at all:** `ai/librechat`
  (`bitnami/mongodb`, digest-pinned) and `databases/mariadb`
  (`bitnami/mariadb`, digest-pinned). Those sit on the **paywalled current**
  catalog, not the archived one — a different failure mode (a frozen digest with
  no semver stream, which Renovate's `helm-values` manager cannot surface drift
  on; `docs/sops/mariadb-major-upgrade.md` §Security Check). They need their own
  plan and their own accepted-risk review date. Do not fold them in here.
