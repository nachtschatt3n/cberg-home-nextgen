---
plan_id: paperless-db-13.0.2
component: paperless-db
pr: null                              # No Renovate PR. The image is pinned in a plain
                                      # Deployment yaml (db-deployment.yaml), not a chart,
                                      # so it rides coverage.py's direct-bump lane. Verified
                                      # 2026-09-16: `gh pr list` shows exactly one open PR
                                      # (#212, talos), nothing for mariadb.
kind: image
current: "12.3.3"                     # live-verified 2026-09-16: deployment image AND
                                      # SELECT VERSION() = 12.3.3-MariaDB-ubu2404, datadir
                                      # marker 12.3.3-MariaDB (binary and marker in lockstep)
target: "13.0.2"
update_type: major                    # MariaDB server major: 12.3 -> 13.0
risk: high                            # one-way datadir conversion on the household document
                                      # library, which has NO second copy (see §1.4)
est_duration_min: 60                  # same proven shape as paperless-db-12.3.3, which ran
                                      # this exact procedure end-to-end in that budget
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - deployment/paperless-db                   # image bump
    - pvc/paperless-db-data                     # datadir converted IN PLACE (one-way)
    - deployment/paperless-ngx                  # quiesced (scale 0) for the duration
    - kustomization/paperless-ngx               # suspended during the quiesce
    - helmrelease/paperless-ngx                 # suspended during the quiesce (no edit)
  shared: []                                    # own longhorn-static volume; no shared infra.
                                                # NOT `storage`: this perturbs one volume, not
                                                # the Longhorn control plane.
depends_on: []
conflicts_with: [bitnamilegacy-exit-nextcloud-db]   # CARRIED FORWARD from paperless-db-12.3.3
                                      # and re-checked 2026-09-16 against every other plan's
                                      # frontmatter. The guard is still REAL: both plans are
                                      # namespace `office`, both risk:high, both
                                      # rollback_class:backup-restore, both are one-way MariaDB
                                      # datadir operations, and 60 + 80 = 140 min does not fit
                                      # a 90-min window. nextcloud-db is `blocked` with
                                      # window:null, so the collision is LATENT, not live —
                                      # but nothing else would stop them sharing a slot if it
                                      # unblocks. NOTE: reciprocity is one-sided — that plan
                                      # lists `paperless-db-12.3.3` (now executed), not this
                                      # plan_id. --validate checks refs resolve, not
                                      # reciprocity, so the other side needs updating by
                                      # whoever next touches it (reported, not edited here).
security_ref: null                    # version-currency driver, not a security driver —
                                      # same as paperless-db-12.3.3. See §1.5 for the one
                                      # security-adjacent interaction (cited by id only).
capability_change: false              # same DB service, same app behaviour intended
rollback_class: backup-restore        # NOT git-revert. See §5 — reverting the manifest alone
                                      # points a 12.3.3 binary at a 13.0-converted datadir,
                                      # which is worse than doing nothing.
backup_gate: "logical dump taken in-window with --default-character-set=utf8mb4, proven non-empty + '-- Dump completed' + the 4-byte lead-byte scan PASSING AGAINST A POSITIVE CONTROL + per-table row counts captured, all BEFORE the image bump"
finding_refs: []                      # DELIBERATELY EMPTY, and checked rather than assumed.
                                      # Queried 2026-09-16 with SWEEP_PG_DSN up:
                                      #   policy-cli.py finding list --grep 'paperless-db' --all
                                      # returns only F-1c080cce (the 11.8.9 -> 12.3.3 bump,
                                      # status RESOLVED 2026-09-06) and three doc/plan-lane
                                      # rows about stale documentation. There is NO open
                                      # finding for 12.3.3 -> 13.0.2: version-check-current.md
                                      # (generated 2026-09-16 03:42) carries the row, but the
                                      # sweep has not filed it yet. An empty list is therefore
                                      # correct — no PLAN-lane finding is left reading as
                                      # unplanned. Add the id here if/when the sweep files one.
status: blocked                       # DELIBERATE, and a deviation from the "status: draft"
                                      # default — see the RECOMMENDATION block below. The
                                      # investigation's conclusion is DO NOT EXECUTE, and
                                      # F-61d8147e — a plan-state hygiene record, nothing to
                                      # do with security — documents that a plan stopped by a
                                      # prose header while its machine-readable status stays
                                      # `draft` is exactly the defect to avoid ("matching
                                      # paperless-db-12.3.3 which was blocked the same day for
                                      # the same class of reason"). Writing `draft` here would
                                      # reproduce that defect in the same component.
window: null                          # the scheduler assigns; nothing should claim a slot
                                      # while the recommendation stands
premises:
  # SCOPE NOTE (inherited from paperless-db-12.3.3, re-confirmed against
  # plan-premises.py on 2026-09-16): a premise may not `kubectl exec` — the
  # runner refuses anything outside its read-verb allowlist. So the live
  # COLLATION and 4-byte-content assertions cannot live here; they live in §2,
  # which runs in-window and does query the database. Every command below was
  # executed on 2026-09-16 and returned the expected value.
  - id: still-on-12.3.3
    why: >-
      The migration is 12.3.3 -> 13.0.2. If the cluster already moved, the dump
      baseline, the rollback target and this plan's entire premise are wrong.
      Measured 2026-09-16: mariadb:12.3.3.
    run: kubectl get deploy -n office paperless-db -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "mariadb:12.3.3"
  - id: auto-upgrade-is-armed
    why: >-
      THE most load-bearing fact in this plan, and the difference from the
      12.3.3 migration. MARIADB_AUTO_UPGRADE=1 is ALREADY in the manifest and
      live on the pod (it was added BY the 12.3.3 plan). So the 13.0.2 container
      runs mariadb-upgrade on its FIRST start, automatically — the one-way
      datadir conversion happens the instant the new image is pulled, with no
      look-first option and no abort point. If this ever reads anything but "1",
      the failure mode inverts to a 13.0 binary silently serving 12.3-format
      system tables, and §3 must be re-planned. Measured 2026-09-16: "1".
    run: kubectl get deploy -n office paperless-db -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="MARIADB_AUTO_UPGRADE")].value}'
    expect_exact: "1"
  - id: restore-path-exists
    why: >-
      rollback_class is backup-restore and there is no second copy of this
      database (the pre-replatform volume paperless-mariadb was DELETED
      2026-08-30, aa825d8f). A restore path must be proven to EXIST before
      anything is touched — this premise fails closed if no Completed backup
      CR for paperless-db-data is present. Measured 2026-09-16: 8 Completed
      backups, newest 2026-09-15T03:03:17Z, 620756992 bytes. FRESHNESS is
      asserted separately in §2 because it is time-relative.
    run: kubectl get backups.longhorn.io -n storage -o jsonpath='{.items[?(@.status.volumeName=="paperless-db-data")].status.state}'
    expect_contains: "Completed"
  - id: backups-still-scheduled
    why: >-
      A restore path that has stopped being refreshed is a stale one. The volume
      must still be in the default recurring-job group that CronJob
      storage/daily-backup-all-volumes (owned by the RecurringJob of the same
      name) drives at 03:00. Measured 2026-09-16: label present, enabled.
    run: kubectl get volume -n storage paperless-db-data -o jsonpath='{.metadata.labels}'
    expect_contains: "recurring-job-group.longhorn.io/default"
  - id: charset-invariant-intact
    why: >-
      The utf8mb4 server pin is what stops a repeat of the OperationalError 1366
      that broke every mail-processing cycle before 9cb10b76 (2026-08-30). It is
      also why the dump's 4-byte proof in §3.2 is mandatory. If these args ever
      go missing, the charset invariant is already broken and a major upgrade is
      the wrong thing to be doing. Measured 2026-09-16: all three args present.
    run: kubectl get deploy -n office paperless-db -o jsonpath='{.spec.template.spec.containers[0].args}'
    expect_contains: "utf8mb4_general_ci"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/mariadb-major-upgrade.md        # see §1.6 — applicability is WRONG for this
                                              # component (F-6d08960a); follow the executed
                                              # 12.3.3 plan where they disagree
  - docs/sops/postgres-major-upgrade.md       # sibling precedent for the SHAPE of a major
                                              # DB upgrade in this household
  - docs/sops/backup.md
  - docs/sops/paperless.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-16"
---

> ## ⛔ RECOMMENDATION: DO NOT EXECUTE — this is an operator DECISION, not a routine bump
>
> **This plan is written, complete and executable, and it recommends against
> running itself.** The window agent must not schedule it; the decision belongs
> to the operator.
>
> The bump is not "12.3.3 → a newer 12.3.x". It moves the household's document
> database **off the LTS line and onto a rolling release**:
>
> | | MariaDB 12.3 (now) | MariaDB 13.0 (target) |
> |---|---|---|
> | Release type | **LTS** | **rolling / innovation** |
> | Released | 2026-05-28 | 2026-09-15 (**1 day** before this plan) |
> | Community support ends | **2029-06-12** | **2026-12-31** |
> | Further patch releases? | yes, for ~3 more years | **no** — upstream's model is "no patch version releases of an innovation release after GA … users are supposed to upgrade to the next minor innovation release" |
>
> So executing this trades ~33 months of supported life for ~3.5 months, and
> commits us to a **quarterly one-way datadir migration** (13.0 → 13.1 → 13.2 …)
> just to stay patched — on a database that has **no second copy**.
>
> The migration is **irreversible** and, because `MARIADB_AUTO_UPGRADE=1` is
> already live, it is **irreversible from the first second the new image starts**.
>
> **There is no upside to buy this with.** 12.3.3 is the newest tag on the LTS
> line (verified on Docker Hub 2026-09-16 — no 12.3.4 exists), it is current and
> fully supported, and none of 13.0's features (`TYPE .. IS REF CURSOR`,
> `innodb_log_archive`, optimizer-trace additions) is used by paperless-ngx.
>
> **Recommended instead:** stay on 12.3.3 LTS and revisit at the **next LTS**
> (upstream's stated model is that the `.3` of each major is LTS, so 13.3 —
> expected mid-2027, date not yet announced by upstream). That is one LTS→LTS hop,
> exactly the shape of the 11.8→12.3 migration that already succeeded here.
>
> **If the operator decides to go anyway**, §2–§6 are the real, executable
> procedure, and every command in them names an object verified to exist.

# paperless-db: mariadb 12.3.3 → 13.0.2 (LTS → ROLLING major)

## 1. Summary & why held

Held by the version gate as a major (`runbooks/version-check-current.md`,
generated 2026-09-16 03:42, row: `paperless-db | office | 12.3.3 → 13.0.2 |
🔴 MAJOR`), and additionally by the standing deny rule `*mariadb*`
(`max: patch`) in `runbooks/auto-update-policy.yaml`: *"A DB-engine bump is
never unattended-safe."* Both holds are correct.

This plan follows `runbooks/maintenance/plans/paperless-db-12.3.3.md` — the
**executed, verified** 11.8.9 → 12.3.3 plan for this exact component — as its
template. Where the two differ, it is called out explicitly below.

### 1.1 What the major boundary actually requires

Established from MariaDB's own documentation and release data, not by analogy:

- **`mariadb-upgrade` must run**, and here it runs *automatically*. The official
  image only runs it when `MARIADB_AUTO_UPGRADE=1` — which the 12.3.3 plan added
  and which is **already live** (premise `auto-upgrade-is-armed`). Evidence it
  works on this deployment: the 12.3.3 roll logged *"Major version upgrade
  detected from 11.8.8-MariaDB to 12.3.3-MariaDB"* and completed all 8 phases;
  a later restart logged *"MariaDB upgrade not required"* (measured again
  2026-09-16 — still the current tail).
- **This INVERTS the 12.3.3 plan's main risk.** There, the danger was that
  `mariadb-upgrade` would be *skipped* (SOP failure mode 1). Here the env var is
  already armed, so the danger is the opposite: the conversion runs the moment
  the pod starts. **There is no "start it and look" step, and no abort point
  after the image lands.** That single fact is the biggest gotcha in this file.
- **Incompatible changes 12.3 → 13.0** are modest, and upstream has published
  **no `Upgrading from MariaDB 12.3 to MariaDB 13.0` guide** (checked
  2026-09-16 — the docs site's upgrade-path index has 11.8→12.3 but no 12.3→13.0
  page; the generic "Upgrading Between Major MariaDB Versions" page applies).
  From the 13.0 changes page and the 13.0.2 release notes:
  - `binlog_row_event_max_size` default raised to 64 KB (no binlog consumer here
    — single server, no replication).
  - `PERFORMANCE_SCHEMA` digests switch to `XXH3_128`.
  - New `innodb_log_archive` (opt-in, off by default).
  - New SQL surface: `TYPE .. IS REF CURSOR`, `RECORD` routine params,
    `UPDATE ... RETURNING`. None used by paperless's Django schema.
  - No removed/renamed system variables that this Deployment sets. Our three
    args (`--character-set-server`, `--collation-server`,
    `--innodb-file-per-table`) are all still valid in 13.0.
  **The breaking change is not a SQL incompatibility — it is the support
  lifecycle.** See the RECOMMENDATION block.
- **Base image changes too.** `12.3.3` publishes a `-noble` variant (Ubuntu
  24.04; the live server string is `12.3.3-MariaDB-ubu2404`). `13.0.2` publishes
  no `-noble` — its variants are bare, `-resolute`, `-ubi`, `-ubi10`. So this
  bump also carries an OS base jump underneath the DB major. Verified against
  the Docker Hub tag list 2026-09-16.

### 1.2 Is the data directory one-way? YES — and the rollback cannot be a git revert

Upstream: *"an in-place downgrade to a previous major version is only allowed if
you have not yet executed `mariadb-upgrade` on the new version"*, because the
`mysql` schema's privilege and system tables change between majors. With
`MARIADB_AUTO_UPGRADE=1` live, `mariadb-upgrade` **always** runs on first start.
Therefore the datadir is one-way **from the first start of 13.0.2**, and:

> **Reverting `db-deployment.yaml` to `mariadb:12.3.3` is NOT a rollback.** It
> points the old binary at a 13.0-converted datadir. That is worse than doing
> nothing. `rollback_class: backup-restore` is set for this reason, and §5 is a
> restore *procedure*, not a revert line.

### 1.3 Does paperless itself constrain the DB version?

Checked upstream (paperless-ngx docs, `setup`): it states *"For new
installations, it is recommended to use PostgreSQL as the database backend"* and
that `PAPERLESS_DBENGINE` must be one of `postgresql`, `mariadb`, `sqlite`.
It declares **no minimum and no maximum MariaDB version**, and no MariaDB
caveat beyond the PostgreSQL preference. Our wiring (`helmrelease.yaml`:
`PAPERLESS_DBENGINE: mariadb`, `PAPERLESS_DBHOST: paperless-db`,
`PAPERLESS_DBPORT: 3306`) is unaffected by the server major.

**So paperless does not block 13.0.2 — but it does not ask for it either.**
Nothing in the application needs this bump; there is no paperless feature, fix
or requirement on the other side of it.

### 1.4 Blast radius, and why `risk: high`

`paperless-db` is the document library's only database, and — per
`docs/sops/paperless.md` §2 — **there is no rollback floor: the live DB is the
only copy.** The pre-replatform volume `paperless-mariadb` was deleted
2026-08-30 (`aa825d8f`). Live baseline measured 2026-09-16:

- **970 documents** (`documents_document`), 74 tables in `paperless`, all
  `utf8mb4_general_ci`, 225 MB used of a 4.9 GB volume (ample headroom for the
  entrypoint's system-table backup).
- The **4-byte content canary is live**: 1 row in
  `paperless_mail_processedmail` has `HEX(subject) LIKE '%F09F%'` — the emoji
  subject class that caused `OperationalError 1366` before the utf8mb4
  conversion. This is why §3.2's 4-byte dump proof is mandatory, not optional.
- Volume `paperless-db-data`: `attached`/`healthy`, `longhorn-static`, PV
  reclaim **`Retain`**, driver `driver.longhorn.io`, 8 Completed backups, newest
  **2026-09-15T03:03:17Z**.

Downstream of an outage: the paperless web UI + API, the scanner→SMB→validator→
consume pipeline, email ingestion, the native-AI suggestions path, and the ARAG
bill push (`health-insurance-agent`). All ingestion **buffers** upstream, so a
quiesce loses nothing — it delays.

### 1.5 One security-adjacent interaction (cited by id only, no detail here)

`security-check.py` rates a fixable-CVE finding actionable only when
`_newer_upstream_tag_exists()`. A newer tag (13.0.2) now exists, which can flip
the standing accepted finding **F-fbbeecab** on the `mariadb:12.3.3` image from
`[AR-029] already on the newest upstream tag` to actionable, and that will read
as pressure to take this bump. It should not:

- The household rule is *bump, never rebuild* — but it does not say *bump onto
  an unsupported line*. 13.0 stops receiving patches at 2026-12-31, so bumping
  there **worsens** the long-run patch posture rather than improving it.
- Per CLAUDE.md, quote the **contextual** tier, not the raw scanner count:
  `paperless-db` is a **ClusterIP** Service with no HTTPRoute and no external
  exposure, so it is not external-unauth and these do not reach this household's
  `critical` tier.
- Detail stays on the finding record. Nothing about it is restated in this file.

### 1.6 Which document I followed, and a repo correction owed

I followed **`runbooks/maintenance/plans/paperless-db-12.3.3.md`** (executed,
verified) as authoritative, **not** `docs/sops/mariadb-major-upgrade.md`.

That SOP is titled *"MariaDB Major Upgrade (Bitnami chart)"* and its Description
still claims it applies to `office/paperless-ngx` "via the Bitnami entrypoint".
**That is wrong for this component** and is already filed as **F-6d08960a**:
`paperless-db` runs the Docker Official image, and its working path is
`MARIADB_AUTO_UPGRADE` + the utf8mb4/4-byte content proof. Concretely, the SOP's
paths do not exist here — it names `/bitnami/mariadb/data/mysql_upgrade_info`,
whereas this deployment's marker is **`/var/lib/mysql/mariadb_upgrade_info`**
(read live 2026-09-16: `12.3.3-MariaDB`). Following the SOP literally would
`cat` a nonexistent file and read the empty result as… whatever the reader
wanted.

Two parts of that SOP **do** still apply and are kept below: the socket/`--skip-ssl`
invocation for a manual `mariadb-upgrade`, and the
`--default-character-set=utf8mb4` dump rule (whose omission silently corrupted a
Nextcloud migration's rollback floor on 2026-08-19).

> **Material for F-6d08960a** (noted here so it is not lost when the 12.3.3 plan
> file is retired per `plans/README.md`): the Docker-Official path that SOP is
> missing is exactly §1.1 + §3.2 + §3.6 of this file — `MARIADB_AUTO_UPGRADE=1`
> semantics, the `/var/lib/mysql/mariadb_upgrade_info` marker path, and the
> positive-control 4-byte dump proof. **This plan does not edit docs**; that is
> the finding's own work item.

## 2. Pre-checks

Run `plan-premises.py paperless-db-13.0.2` first — it fails closed. Then:

```bash
# Cluster + component healthy, no in-flight reconcile
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
kubectl -n office get pods -l app=paperless-db          # expect 1/1 Running, 0 restarts
kubectl -n office get deploy paperless-db -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
# expect: mariadb:12.3.3

# Volume healthy AND the nightly backup is FRESH (<26h; 03:00 CronJob
# storage/daily-backup-all-volumes). The premise proved a backup EXISTS;
# this proves it is RECENT.
kubectl get volume -n storage paperless-db-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LAST_BACKUP:.status.lastBackupAt
# NOTE: lastBackupAt can lag a cycle (docs/sops/backup.md). If it looks stale,
# cross-check the newest Completed Backup CR before aborting:
kubectl -n storage get backups.longhorn.io \
  -o custom-columns=NAME:.metadata.name,VOL:.status.volumeName,STATE:.status.state,CREATED:.status.backupCreatedAt \
  | grep paperless-db-data | sort -k4 | tail -3

# Schema inventory + COLLATION gate (the assertion premises cannot make).
# Expect: paperless=74 tables, and 74 rows of utf8mb4_general_ci.
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e \
   "SELECT table_schema, COUNT(*) FROM information_schema.tables GROUP BY 1;
    SELECT table_collation, COUNT(*) FROM information_schema.tables
      WHERE table_schema=\"paperless\" GROUP BY 1;"'

# Datadir headroom for the entrypoint's system-table backup
kubectl -n office exec deploy/paperless-db -- df -h /var/lib/mysql   # measured: 225M/4.9G
```

**ABORT this plan if:** the volume is not `attached`/`healthy`; no Completed
backup for `paperless-db-data` is newer than 26h (and the Backup-CR cross-check
also fails); any `paperless` table is not `utf8mb4_*` (that would be a
regression of `9cb10b76` — investigate that first, do not upgrade over it); or
the operator has not explicitly overridden the RECOMMENDATION block.

## 3. Steps

All cluster writes are executed by the window agent / cberg-agent. The manifest
change is GitOps.

**3.1 Quiesce the app** (scanner SMB inbox and the GMX mailbox buffer upstream —
documents queue, nothing is lost):

```bash
flux suspend kustomization paperless-ngx -n office   # ns office, NOT flux-system
flux suspend helmrelease   paperless-ngx -n office
kubectl -n office scale deploy/paperless-ngx --replicas=0
kubectl -n office wait --for=delete pod -l app.kubernetes.io/name=paperless-ngx --timeout=120s
```

(Label verified live 2026-09-16: the pod template carries
`app.kubernetes.io/name=paperless-ngx`; `paperless-db` carries `app=paperless-db`.)

**3.2 Logical dump — the rollback floor (non-negotiable):**

```bash
mkdir -p ~/backups/paperless-db && chmod 0700 ~/backups/paperless-db
DUMP=~/backups/paperless-db/paperless-db-pre-13.0.2-$(date +%Y%m%d%H%M).sql
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb-dump --default-character-set=utf8mb4 --single-transaction --all-databases \
   -uroot -p"$MARIADB_ROOT_PASSWORD"' > "$DUMP"
chmod 0600 "$DUMP"

tail -1 "$DUMP" | grep -q -- '-- Dump completed' || echo "ABORT: dump incomplete"
grep -c 'CREATE TABLE' "$DUMP"   # expect ~74 (paperless) + system tables
ls -lh "$DUMP"                   # 12.3.3 dump was ~25.8 MB; expect the same order
```

`--default-character-set=utf8mb4` is **not optional**: without it the server
transcodes 4-byte characters to `?` on the way out and the rollback floor is
corrupt when written (this destroyed a Nextcloud migration's dump on
2026-08-19).

**4-byte proof — MANDATORY, and run the POSITIVE CONTROL first.** A checker that
cannot see 4-byte content makes its own zero meaningless. The SOP's
`LC_ALL=C grep -c $'[\xf0-\xf4]'` form **returns 0 on macOS/BSD regardless of
content** (measured 2026-09-07) — since a zero here means "STOP", running the
broken form aborts a good migration. Use the byte scan:

```bash
# POSITIVE CONTROL — prove the checker can see 4-byte content at all
printf 'ascii\nemoji \xf0\x9f\x93\x84 here\n' > /tmp/ctl.txt
python3 -c "import sys;print(sum(1 for l in open(sys.argv[1],'rb') if any(0xf0<=b<=0xf4 for b in l)))" /tmp/ctl.txt
# EXPECT 1. A 0 here means the CHECKER is broken — stop and fix it, the dump is not implicated.

# the real gate
python3 -c "import sys;print(sum(1 for l in open(sys.argv[1],'rb') if any(0xf0<=b<=0xf4 for b in l)))" "$DUMP"
# EXPECT > 0. Live baseline 2026-09-16: 1 row in paperless_mail_processedmail has
# HEX(subject) LIKE '%F09F%'. A ZERO with a PASSING control means the dump lost
# 4-byte content and is NOT a valid rollback. STOP.
```

**3.3 Baseline per-table row counts** (the contents baseline for §4):

```bash
kubectl -n office exec deploy/paperless-db -- sh -c '
  for t in $(mariadb -N -uroot -p"$MARIADB_ROOT_PASSWORD" -e \
    "SELECT table_name FROM information_schema.tables
     WHERE table_schema=\"paperless\" AND table_type=\"BASE TABLE\""); do
    echo "$t $(mariadb -N -uroot -p"$MARIADB_ROOT_PASSWORD" -e \
      "SELECT COUNT(*) FROM paperless.\`$t\`")"
  done' | sort > /tmp/paperless-db-counts-pre.txt
wc -l /tmp/paperless-db-counts-pre.txt   # expect 74 lines
grep '^documents_document ' /tmp/paperless-db-counts-pre.txt   # expect 970 (2026-09-16)
```

**3.4 Longhorn snapshot — fast-path insurance** (DB is idle; app is at 0):

```bash
kubectl apply -f - <<'EOF'
apiVersion: longhorn.io/v1beta2
kind: Snapshot
metadata:
  name: paperless-db-data-pre-13-0-2
  namespace: storage
spec:
  volume: paperless-db-data
  createSnapshot: true
EOF
kubectl -n storage get snapshot.longhorn.io paperless-db-data-pre-13-0-2 \
  -o jsonpath='{.status.readyToUse}{"\n"}'
# expect: true   (name verified free 2026-09-16 — the only snapshot on this
#                 volume is the daily daily-ba-23690c14-…; the 12.3.3 plan's
#                 paperless-db-data-pre-12-3-3 has already aged out)
```

**3.5 GitOps change** — one line in
`kubernetes/apps/office/paperless-ngx/app/db-deployment.yaml`:

Dry-tested on a scratch copy on macOS (BSD sed) 2026-09-16; the resulting diff is
exactly:

```diff
41c41
<         image: mariadb:12.3.3
---
>         image: mariadb:13.0.2
```

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's|^        image: mariadb:12\.3\.3$|        image: mariadb:13.0.2|' \
  kubernetes/apps/office/paperless-ngx/app/db-deployment.yaml
git diff --stat kubernetes/apps/office/paperless-ngx/app/db-deployment.yaml
```

`MARIADB_AUTO_UPGRADE=1` is **already present** (lines 68–69) — do not re-add it,
and do not remove it. Update the header comment's version references while there.

```bash
git fetch origin main && git merge --ff-only origin/main
git commit --only kubernetes/apps/office/paperless-ngx/app/db-deployment.yaml -F <msgfile>
git log -1 --format=%s     # shared worktree: confirm the subject is YOURS before pushing
git show --stat HEAD       # ONLY db-deployment.yaml
git push origin main
```

**3.6 Roll the DB** (the Kustomization owns this Deployment; the reconcile is
SOP-sanctioned here):

```bash
flux resume kustomization paperless-ngx -n office
flux reconcile kustomization paperless-ngx -n office --with-source
kubectl -n office rollout status deploy/paperless-db --timeout=300s

# WATCH the conversion actually happen — this is the point of no return:
kubectl -n office logs deploy/paperless-db | grep -iE 'upgrade|phase|version' | head -40
# EXPECT a line of the form "Major version upgrade detected from 12.3.3-MariaDB
# to 13.0.2-MariaDB" followed by phases 1..8.
# If it instead says "MariaDB upgrade not required" on a FIRST 13.0.2 start,
# the datadir was NOT converted — go to the manual invocation below.
```

If the entrypoint upgrade did not run or half-ran (the SOP's failure mode 2 —
TLS/TCP loopback resets mid-run, whose tell is that two runs fail at *different*
lines), run it by hand over the socket:

```bash
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb-upgrade --protocol=socket --skip-ssl -uroot -p"$MARIADB_ROOT_PASSWORD"'
```

**3.7 Verify the DB half of §4 — then and only then un-quiesce the app:**

```bash
flux resume helmrelease paperless-ngx -n office
flux reconcile helmrelease paperless-ngx -n office
# The reconcile does NOT restore replicas=1 (measured 2026-09-07): §3.1 scaled with
# kubectl, which is drift the HelmRelease does not correct unless driftDetection is
# enabled — and it is not (spec.driftDetection is unset on all 124 HRs; see the
# helm-drift-detection plan). Scale back explicitly, or the plan finishes with the
# app silently at 0/0 and every check still green.
kubectl -n office scale deploy/paperless-ngx --replicas=1
kubectl -n office rollout status deploy/paperless-ngx --timeout=300s
```

## 4. Verification

Version alone is the known misleading signal. Each gate below states the failure
it can actually catch.

```bash
# 1. Binary AND datadir marker agree on 13.0.2.
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "SELECT VERSION();";
   cat /var/lib/mysql/mariadb_upgrade_info'
# expect: 13.0.2-MariaDB...  AND  13.0.2-MariaDB
# CATCHES: the SOP's failure mode 1 — a 13.0.2 binary serving 12.3-format system
# tables. That state returns the NEW version from VERSION() while the marker still
# reads 12.3.3-MariaDB, and nothing else goes red. Marker path verified live
# (/var/lib/mysql/..., NOT the SOP's /bitnami/... path — see §1.6).
```

```bash
# 2. Integrity across every schema.
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb-check --protocol=socket --all-databases -uroot -p"$MARIADB_ROOT_PASSWORD"' \
  | grep -iv ' ok$' || echo "all OK"
# CATCHES: tables the upgrade left needing repair. Grep is case-INSENSITIVE and
# anchored: mariadb-check prints "<db>.<table><tabs>OK", and a naive `grep -v OK`
# also swallows any line containing "ok" inside a table name.
```

```bash
# 3. CONTENTS ASSERTION: per-table row counts of the paperless schema —
#    measured by re-running the §3.3 loop into /tmp/paperless-db-counts-post.txt
#    and diffing against the pre-upgrade baseline. The diff MUST be silent.
diff /tmp/paperless-db-counts-pre.txt /tmp/paperless-db-counts-post.txt && echo COUNTS-MATCH
# CATCHES: silent row loss. Would fail loudly if any of the 74 tables changed
# count. Baseline is a real measurement (74 tables, documents_document=970),
# not a shape check — an empty DB would fail this, while pod-Ready and
# SELECT VERSION() would both still pass.
```

```bash
# 4. CONTENTS ASSERTION: the 4-byte content class survived, and the server can
#    still WRITE it — the original OperationalError 1366 failure mode.
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e \
   "SELECT COUNT(*) FROM paperless.paperless_mail_processedmail
      WHERE HEX(subject) LIKE \"%F09F%\";
    SELECT table_collation, COUNT(*) FROM information_schema.tables
      WHERE table_schema=\"paperless\" GROUP BY 1;"'
# expect: 1  (matches the 2026-09-16 baseline) AND utf8mb4_general_ci 74
# CATCHES: a charset regression that flattened 4-byte content to '?'. Row counts
# CANNOT catch this — a transcoded row still counts as one row.
```

```bash
# 5. The dependent app works. A DB its app cannot use is the failure worth catching.
kubectl -n office get pods -l app.kubernetes.io/name=paperless-ngx   # 1/1 Running
kubectl -n office logs deploy/paperless-ngx --since=15m | grep -iE '1366|OperationalError|mailbox.login' || echo clean
# Then the paperless.md §6a canary (API token, from the openclaw pod) and the UI:
# the dashboard document count MUST equal 970 (the §3.3 documents_document
# baseline), and one existing document must open.
# CATCHES: a healthy-but-unusable DB. A 401 here is a TOKEN failure, NOT missing
# documents — never read it as data loss (this exact mislabel happened 2026-08-30).
```

```bash
# 6. Ingestion round-trip (attended): drop a throwaway PDF into the scanner SMB
#    inbox and watch it become a document — exercises validator -> consume -> DB
#    WRITE on 13.0, which every read-only check above would miss.
kubectl -n office logs deploy/paperless-ngx -f --tail=20
```

Nightly Longhorn backup of `paperless-db-data` must complete on the next 03:00
cycle (check `lastBackupAt` next sweep). **Do not delete the §3.2 dump or the
§3.4 snapshot until that backup is Completed** — until then they are the only
recovery path for a 13.0-format datadir.

## 5. Rollback

**There is no in-place downgrade, and no manifest revert that helps.** Never run
`mariadb:12.3.3` against a datadir 13.0.2 has started on.

Trigger: the server will not start on 13.0.2; `mariadb-upgrade` cannot complete;
the §4.3 counts diff is non-silent; the §4.4 collation/4-byte assertion fails; or
paperless cannot serve its library.

1. **Quiesce again** — re-suspend per §3.1 and scale the DB down:
   ```bash
   flux suspend kustomization paperless-ngx -n office
   flux suspend helmrelease   paperless-ngx -n office
   kubectl -n office scale deploy/paperless-ngx --replicas=0
   kubectl -n office scale deploy/paperless-db  --replicas=0
   ```
2. **Revert the manifest** (necessary, not sufficient — do this while the data is
   still being restored, and keep the Kustomization suspended until step 3 or 4
   completes):
   ```bash
   git revert <hash-of-the-3.5-commit>    # back to mariadb:12.3.3
   git push origin main
   ```
3. **Fast path — Longhorn snapshot revert** (preferred; `paperless-db-data-pre-13-0-2`
   was taken with the server idle). Detach the volume, revert it to that snapshot
   via the Longhorn UI/API (maintenance-mode attach), re-attach, resume the
   Kustomization, scale up. This returns a **12.3-format** datadir, which the
   reverted 12.3.3 image can open.
   > **STORAGE SAFETY:** this is a snapshot *revert*, not a PVC delete. **Do not
   > delete or recreate `paperless-db-data`.** Its PV is `Retain`,
   > `longhorn-static`, driver `driver.longhorn.io` (verified 2026-09-16). If any
   > step ever seems to call for deleting a PVC, run the 3-step pre-flight from
   > CLAUDE.md (`subdir`, `reclaimPolicy`, StorageClass) and STOP.
4. **Fallback — dump restore into a fresh datadir.** Only if the snapshot revert
   fails. With the Deployment back on 12.3.3 and scaled to 0, clear the datadir
   *contents* via a one-off debug pod mounting `paperless-db-data`
   (`rm -rf /var/lib/mysql/*` — this PVC only, triple-check the claim name; the
   PVC and PV themselves are NOT deleted), scale up so the entrypoint
   re-initialises from the `MARIADB_*` env, then:
   ```bash
   kubectl -n office exec -i deploy/paperless-db -- sh -c \
     'mariadb --default-character-set=utf8mb4 -uroot -p"$MARIADB_ROOT_PASSWORD"' < "$DUMP"
   ```
   `--default-character-set=utf8mb4` on the way IN as well, or the restore
   re-introduces the 1366 bug.
5. **Last resort — restore from the Longhorn backup** (newest Completed backup of
   `paperless-db-data`, e.g. `backup-3416ef68e9e74554` @ 2026-09-15T03:03:17Z):
   restore it into a new volume and rebind, per `docs/sops/backup.md`. Costs up to
   24h of documents — the dump and snapshot exist precisely so this is not needed.
6. **Confirm the back-state, don't assume it:** `SELECT VERSION();` → 12.3.3,
   marker → `12.3.3-MariaDB`, §4.3 counts diff silent against
   `/tmp/paperless-db-counts-pre.txt`, §4.4 collation + 4-byte assertions pass,
   paperless serves, ingestion round-trip passes. Then set this plan
   `status: blocked` with the failure recorded.

## 6. Interference notes

- **`conflicts_with: [bitnamilegacy-exit-nextcloud-db]` is a real guard, carried
  forward.** Same namespace (`office`), both `risk: high`, both
  `rollback_class: backup-restore`, both one-way MariaDB datadir operations, and
  60 + 80 = 140 min cannot fit a 90-min window. That plan is currently `blocked`
  with `window: null`, so the collision is latent — but nothing else would stop
  them sharing a slot if it unblocks. **Reciprocity gap:** that plan's
  `conflicts_with` still names `paperless-db-12.3.3` (executed), not this
  plan_id. `--validate` checks that refs resolve, not that they are mutual, so
  the other side needs the same edit — flagged, not edited here.
- **Do not co-schedule with any Longhorn engine/storage work.** The upgrade holds
  `paperless-db-data` attached and the §3.4 snapshot is the fast rollback path.
- **Attended, never nightly.** `risk: high` + `rollback_class: backup-restore`
  derives **HUMAN-GATED** under `runbooks/autonomy-policy.yaml` (`auto-backup-gated`
  carries `forbid_risk: [high]`), and that is correct here. `needs_reboot: false`,
  so a Saturday slot would suffice *if* it ran at all.
- **Ingestion downtime ~30–40 min inside the window.** The paperless app is at 0
  while the dump and bump run. Scanner drops land in the SMB inbox and email sits
  in the GMX mailbox — both buffer, nothing is lost, consume catches up after
  §3.7. The ARAG bill push and any paperless API consumers will error during the
  quiesce; Homepage and Uptime Kuma will flag paperless — pre-silence per
  `docs/sops/application-update.md` §Step 1, and drop an active-update marker
  (`runbooks/update-marker.sh add paperless-ngx office 4 "..."`) so the
  alert-triage agent treats the noise as EXPECTED.
- **The suspend/scale in §3.1 must be symmetric**, and the order in §3.6/§3.7 is
  deliberate: the Kustomization resumes (DB rolls, DB verified) *before* the
  HelmRelease resumes (app returns). Do not resume the HR early.
- **Dumps contain `mysql.global_priv` password hashes** — keep them `0600` in a
  `0700` directory, never commit them, and delete them once the post-upgrade
  nightly backup has completed.
- **`scan-inbox-validator` rides the paperless-ngx image, not the DB image** — it
  is untouched by this plan, but it does talk to the same consume share, so leave
  it running.
