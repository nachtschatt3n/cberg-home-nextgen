---
plan_id: paperless-db-12.3.3
component: paperless-db
pr: null                              # version-check finding, no Renovate PR — the
                                      # image lives in a plain Deployment yaml
kind: image
current: "11.8.9"
target: "12.3.3"
update_type: major                    # MariaDB server major: 11.8 LTS -> 12.3 LTS
risk: high                            # one-way datadir upgrade on the document library
est_duration_min: 60
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - deployment/paperless-db                   # image bump + MARIADB_AUTO_UPGRADE env
    - pvc/paperless-db-data                     # datadir upgraded IN PLACE (one-way)
    - deployment/paperless-ngx                  # quiesced (scale 0) for the duration
    - kustomization/paperless-ngx               # suspended during the quiesce
    - helmrelease/paperless-ngx                 # suspended during the quiesce (no edit)
  shared: []                                    # own Longhorn volume; no shared infra
depends_on: []                        # bitnamilegacy-exit-paperless-db EXECUTED 2026-08-19
conflicts_with: []  # RESOLVED 2026-09-05: dead ref 'longhorn-1.12.1-engine' removed — that plan was EXECUTED 2026-08-29 (34abe2bb) and its file deleted. Verified complete: 94/94 volumes on longhorn-engine v1.12.1, single engine image deployed. There is no engine upgrade left to collide with, so this guard protected nothing.  # engine upgrade perturbs every attached
                                          # volume incl. paperless-db-data — never
                                          # share a window (it holds sat-attended:2026-08-29)
security_ref: null                    # version-currency driver, not a CVE driver
capability_change: false              # same DB service, same app behaviour intended
rollback_class: backup-restore        # MariaDB majors have NO downgrade — git revert
                                      # alone is worse than nothing (old binary on a
                                      # 12.3-format datadir)
backup_gate: "logical dump taken in-window, verified non-empty + '-- Dump completed' + per-table counts captured, BEFORE the image bump"
finding_refs: [F-1c080cce]
status: draft
window: null                          # recommend sat-attended:2026-09-05 (see notes)
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/mariadb-major-upgrade.md
  - docs/sops/backup.md
  - docs/sops/paperless.md
  - docs/sops/longhorn.md
generated: "2026-08-28"
---

# paperless-db: mariadb 11.8.9 → 12.3.3 (LTS → LTS major)

## 1. Summary & why held

Bump the paperless document database from MariaDB **11.8.9** (11.8 LTS) to
**12.3.3** — the **next LTS line** (released 2026-05-29, maintained until June
2029). Held by the version gate: *"Major version change typically indicates
breaking changes"* (finding **F-1c080cce**, version section, 2026-08-28 sweep).

This is an **in-place datadir upgrade**, not a replatform: same official
`mariadb` image lineage, same volume `paperless-db-data`, same plain
Deployment installed by plan `bitnamilegacy-exit-paperless-db` (executed
2026-08-19). LTS→LTS (skipping the 12.0–12.2 rolling releases) is the
documented upstream path.

Upstream incompatibilities across 11.8 → 12.3 (release notes,
mariadb.com/docs `mariadb-12.3-changes-and-improvements`):

- **`innodb_snapshot_isolation` defaults to ON** — changes REPEATABLE READ
  semantics; a transaction touching rows modified after its snapshot can now
  fail with "Record has changed since last read". Watch-item for
  paperless/Django (low-concurrency single app; knob can be set OFF without
  rollback if it bites).
- **New reserved words** `CONVERSION`, `TO_DATE`, `ST_COLLECT` — unquoted
  identifiers with these names break. Paperless's Django schema (74 tables,
  `documents_*`/`auth_*`/`django_*` naming) uses none of them.
- Removed long-deprecated system variables `big_tables`, `large_page_size`,
  `storage_engine` — none set in our args.
- Replica `master_use_gtid` reset bug affected 12.3.0–12.3.2, **fixed in
  12.3.3** (we target 12.3.3; no replication here anyway).
- **No downgrade exists.** Rollback is dump-restore only
  (`docs/sops/mariadb-major-upgrade.md`).

Why not auto-safe: one-way major on the household document library. Why it is
still very doable: the mariadb-major SOP already covers both silent failure
modes (skipped `mariadb-upgrade`; TLS-loopback resets) from the
`databases/mariadb` 12.2.2→13.0.1 upgrade, and this instance holds exactly one
user schema (`paperless`, 74 tables, all `utf8mb3_general_ci` by design — the
charset pin in the Deployment args stays).

**Official-image trap (differs from the Bitnami SOP context):** the official
`mariadb` entrypoint does **NOT** run `mariadb-upgrade` unless
`MARIADB_AUTO_UPGRADE=1` is set. Without it we'd serve 11.8-format system
tables under a 12.3 binary with every surface signal green — the exact SOP
failure mode 1. The step below adds the env var permanently.

Baseline quirk (recorded 2026-08-28, pre-upgrade): datadir marker
`/var/lib/mysql/mariadb_upgrade_info` reads `11.8.8` while the server is
11.8.9 — benign patch-level lag within one GA series. After this upgrade the
marker MUST read `12.3.3`; do not "pass" it on any 11.8 value.

## 2. Pre-checks

```bash
# Cluster + component healthy, no in-flight reconcile
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
kubectl -n office get pods -l app=paperless-db   # 1/1 Running, no restarts
kubectl -n office get deploy paperless-db -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
# expect: mariadb:11.8.9

# Longhorn volume healthy + last nightly backup fresh (<26h, 03:00 CronJob)
kubectl get volume -n storage paperless-db-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LAST_BACKUP:.status.lastBackupAt

# Schema inventory + collation gate (SOP step 1/2): expect paperless=74-ish
# tables, all utf8mb3_general_ci (matches the charset pin in the args)
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e \
   "SELECT table_schema, COUNT(*) FROM information_schema.tables GROUP BY 1;
    SELECT table_collation, COUNT(*) FROM information_schema.tables
      WHERE table_schema=\"paperless\" GROUP BY 1;"'

# Datadir headroom for the auto-upgrade system-table backup (needs a few MB)
kubectl -n office exec deploy/paperless-db -- df -h /var/lib/mysql

# No consume backlog about to collide with the downtime (informational)
kubectl -n office logs deploy/paperless-ngx --tail=20 | grep -i consume || true
```

Abort the window for this plan if the volume is not `attached/healthy`, the
last backup is stale, or any paperless table is not `utf8mb3_*` (that would
mean drift since the 2026-08-19 replatform — re-investigate first).

## 3. Steps

All cluster writes in this section are executed by the window agent /
cberg-agent; the manifest change is GitOps.

**3.1 Quiesce the app** (scanner SMB inbox + email ingestion buffer upstream —
documents queue, nothing is lost):

```bash
flux suspend kustomization paperless-ngx -n flux-system
flux suspend helmrelease paperless-ngx -n office
kubectl -n office scale deploy/paperless-ngx --replicas=0
kubectl -n office wait --for=delete pod -l app.kubernetes.io/name=paperless-ngx --timeout=120s
```

**3.2 Logical dump — the rollback floor (SOP step 2, non-negotiable):**

```bash
mkdir -p ~/backups/paperless-db && chmod 0700 ~/backups/paperless-db
DUMP=~/backups/paperless-db/paperless-db-pre-12.3.3-$(date +%Y%m%d%H%M).sql
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb-dump --default-character-set=utf8mb4 --single-transaction --all-databases \
   -uroot -p"$MARIADB_ROOT_PASSWORD"' > "$DUMP"
chmod 0600 "$DUMP"

# Verify the dump before trusting it:
tail -1 "$DUMP" | grep -q -- '-- Dump completed' || echo "ABORT: dump incomplete"
grep -c 'CREATE TABLE' "$DUMP"          # expect ~74 (paperless) + system tables
ls -lh "$DUMP"                          # non-trivial size
```

(The 4-byte-lead-byte grep from the SOP is N/A here: the paperless schema is
utf8mb3 by design and cannot hold 4-byte content. Dumping with the utf8mb4
client charset is still correct — utf8mb3 ⊂ utf8mb4, no transcoding loss.)

**3.3 Baseline per-table row counts** (the contents baseline for §4):

```bash
kubectl -n office exec deploy/paperless-db -- sh -c '
  for t in $(mariadb -N -uroot -p"$MARIADB_ROOT_PASSWORD" -e \
    "SELECT table_name FROM information_schema.tables
     WHERE table_schema=\"paperless\" AND table_type=\"BASE TABLE\""); do
    echo "$t $(mariadb -N -uroot -p"$MARIADB_ROOT_PASSWORD" -e \
      "SELECT COUNT(*) FROM paperless.\`$t\`")"
  done' | sort > /tmp/paperless-db-counts-pre.txt
wc -l /tmp/paperless-db-counts-pre.txt   # expect ~74 lines
```

**3.4 Longhorn snapshot as fast-path insurance** (DB is idle now — app is at 0):

```bash
kubectl apply -f - <<'EOF'
apiVersion: longhorn.io/v1beta2
kind: Snapshot
metadata:
  name: paperless-db-data-pre-12-3-3
  namespace: storage
spec:
  volume: paperless-db-data
  createSnapshot: true
EOF
kubectl -n storage get snapshot.longhorn.io paperless-db-data-pre-12-3-3 -o jsonpath='{.status.readyToUse}{"\n"}'
# expect: true
```

**3.5 GitOps change** — edit
`kubernetes/apps/office/paperless-ngx/app/db-deployment.yaml`:

- `image: mariadb:11.8.9` → `image: mariadb:12.3.3`
- Add to the container `env:` block (before `MARIADB_DATABASE`):

  ```yaml
        # Official image does NOT run mariadb-upgrade on a server-major roll
        # unless told to (docs/sops/mariadb-major-upgrade.md failure mode 1,
        # official-image variant). Keeps the datadir marker in lockstep with
        # the binary on this and future majors. The entrypoint backs up the
        # system tables into the datadir before upgrading.
        - name: MARIADB_AUTO_UPGRADE
          value: "1"
  ```

- Update the header comment's version references while there.

```bash
cd /Users/mu/code/cberg-home-nextgen
git commit --only kubernetes/apps/office/paperless-ngx/app/db-deployment.yaml \
  -m "feat(paperless-db): mariadb 11.8.9 -> 12.3.3 LTS + MARIADB_AUTO_UPGRADE (plan paperless-db-12.3.3, F-1c080cce)"
git show --stat HEAD    # ONLY db-deployment.yaml — shared worktree check
git push
```

**3.6 Roll the DB** (Kustomization owns the Deployment; reconcile is
SOP-sanctioned here — mariadb SOP step 4):

```bash
flux resume kustomization paperless-ngx -n flux-system   # resumes + reconciles
flux reconcile kustomization paperless-ngx -n flux-system --with-source
kubectl -n office rollout status deploy/paperless-db --timeout=300s
# WATCH the upgrade actually run — do not skip:
kubectl -n office logs deploy/paperless-db | grep -iE 'upgrade|phase' | head -40
# expect the mariadb-upgrade phases (1..8), NOT "already upgraded" against 11.8
```

If the entrypoint upgrade did not run or half-ran (SOP failure mode 2 —
transport resets): run it by hand over the socket:

```bash
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb-upgrade --protocol=socket --skip-ssl -uroot -p"$MARIADB_ROOT_PASSWORD"'
```

**3.7 Verify the DB (§4, DB half) — then and only then un-quiesce the app:**

```bash
flux resume helmrelease paperless-ngx -n office
flux reconcile helmrelease paperless-ngx -n office   # restores replicas=1
kubectl -n office rollout status deploy/paperless-ngx --timeout=300s
```

## 4. Verification

Version alone is the known misleading signal — check the marker and contents.

```bash
# 1. Binary AND datadir agree on 12.3.3 (baseline was 11.8.8 — see §1)
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e "SELECT VERSION();";
   cat /var/lib/mysql/mariadb_upgrade_info'
# expect: 12.3.3-MariaDB...  AND  12.3.3

# 2. Integrity: all tables OK
kubectl -n office exec deploy/paperless-db -- sh -c \
  'mariadb-check --protocol=socket --all-databases -uroot -p"$MARIADB_ROOT_PASSWORD"' \
  | grep -v OK || echo "all OK"

# 3. CONTENTS ASSERTION: per-table row counts of the paperless schema —
#    measured by the §3.3 loop re-run post-upgrade, compared to
#    /tmp/paperless-db-counts-pre.txt; the diff MUST be silent.
#    (re-run the §3.3 command into /tmp/paperless-db-counts-post.txt)
diff /tmp/paperless-db-counts-pre.txt /tmp/paperless-db-counts-post.txt && echo COUNTS-MATCH

# 4. The dependent app works — a DB its app cannot use is the failure worth
#    catching. API document count equals the documents_document baseline:
kubectl -n office exec deploy/paperless-ngx -- python3 -c "
import urllib.request, json, os
req = urllib.request.Request('http://localhost:8000/api/documents/?page_size=1')
req.add_header('Authorization', 'Token '+os.environ.get('PAPERLESS_ADMIN_TOKEN','')) if False else None
print(urllib.request.urlopen('http://localhost:8000/api/statistics/').status)" \
  2>/dev/null || curl -sk https://paperless.${SECRET_DOMAIN}/ -o /dev/null -w '%{http_code}\n'
# floor: HTTP 200. Real assertion: open the web UI, confirm the document count
# on the dashboard equals the pre-upgrade documents_document count from
# /tmp/paperless-db-counts-pre.txt, and open one existing document.

# 5. Ingestion round-trip (attended): drop a throwaway PDF into the scanner
#    SMB inbox (or the consume dir) and watch it appear as a new document.
#    This exercises validator -> consume -> DB write end-to-end on 12.3.
kubectl -n office logs deploy/paperless-ngx -f --tail=20   # watch the consume

# 6. Watch-item for 24h: grep app logs for the innodb_snapshot_isolation
#    signature before closing the plan.
kubectl -n office logs deploy/paperless-ngx --since=1h | grep -i 'Record has changed' || echo clean
```

Nightly Longhorn backup of `paperless-db-data` must complete on the next 03:00
cycle (check `lastBackupAt` next sweep).

## 5. Rollback

**There is no in-place downgrade.** Never run the 11.8.9 image against a
datadir the 12.3 upgrade has touched — reverting the manifest alone is worse
than doing nothing (SOP Rollback Plan).

Trigger: server won't start on 12.3.3, `mariadb-upgrade` cannot complete, the
counts diff is non-silent, or paperless cannot serve its library.

1. Suspend + quiesce again (§3.1) and scale `deploy/paperless-db` to 0.
2. Revert the manifest:
   ```bash
   git revert <hash-of-3.5-commit>   # back to mariadb:11.8.9
   git push
   ```
   Keep the Kustomization suspended until the data is back (step 3/4), then
   resume.
3. **Fast path — Longhorn snapshot revert** (preferred; the §3.4 snapshot was
   taken with the server idle): detach `paperless-db-data`, revert the volume
   to snapshot `paperless-db-data-pre-12-3-3` via the Longhorn UI/API
   (maintenance-mode attach), re-attach, resume the Kustomization, scale up.
4. **Fallback — dump restore into a fresh datadir**: with the Deployment back
   on 11.8.9 and scaled to 0, wipe the datadir via a one-off debug pod
   mounting `paperless-db-data` (`rm -rf /var/lib/mysql/*` — this PVC only,
   triple-check the claim name), scale up (entrypoint re-initialises from the
   `MARIADB_*` env), then:
   ```bash
   kubectl -n office exec -i deploy/paperless-db -- sh -c \
     'mariadb --default-character-set=utf8mb4 -uroot -p"$MARIADB_ROOT_PASSWORD"' < "$DUMP"
   ```
5. Confirm back-state: `SELECT VERSION();` → 11.8.9, counts diff vs
   `/tmp/paperless-db-counts-pre.txt` silent, paperless serves, ingestion
   round-trip passes. Set this plan `status: blocked` with the failure noted.

## 6. Interference notes

- **`paperless-mariadb` (detached Longhorn volume) is UNTOUCHABLE.** It is the
  deliberate rollback soak from `bitnamilegacy-exit-paperless-db` (executed
  2026-08-19) — do not delete, attach, back up "while we're here", or clean it
  up during this window. It plays **no role** in this plan's rollback: its
  contents are the pre-replatform 11.8.2 Bitnami datadir, two migrations
  behind after this upgrade. Its retirement is a separate operator decision.
  > **RESOLVED 2026-09-05:** this conflict no longer applies — `longhorn-1.12.1-engine`
  > was EXECUTED 2026-08-29 (34abe2bb) and its file deleted; 94/94 volumes verified on
  > engine v1.12.1, single engine image deployed. Removed from `conflicts_with` in the
  > frontmatter. Text around this note kept for provenance.
- **`conflicts_with: longhorn-1.12.1-engine`** — that plan holds
  **sat-attended:2026-08-29** and live-upgrades the engine of every attached
  volume, including `paperless-db-data`. Never co-window; schedule this no
  earlier than **sat-attended:2026-09-05**. That also keeps a clean week
  before `bitnamilegacy-exit-nextcloud-db` (sat-attended:2026-09-12) — avoid
  stacking two one-way DB operations in one 90-minute attended slot.
- **Attended, not nightly**: `rollback_class: backup-restore` + one-way datadir
  + risk high ⇒ operator-present window; `needs_reboot: false`, so Saturday is
  fine.
- **Ingestion pipeline downtime** (~30–40 min inside the window): paperless
  app is scaled to 0 while the dump/bump runs. Scanner drops to the SMB inbox
  and email ingestion sits in the mailbox — both buffer, nothing is lost,
  consume catches up after §3.7. The ARAG bill push (health-insurance-agent)
  and any paperless API consumers will error during the quiesce; Homepage
  widget + Uptime Kuma will flag paperless — pre-silence or expect the pages.
- The suspend/scale in §3.1 is deliberate and must be symmetric: resuming the
  Kustomization (3.6) before the HelmRelease (3.7) is ordered so the DB is
  verified before the app returns. Do not resume the HR early.
- Dumps contain `mysql.global_priv` hashes — keep `0600`, never commit, delete
  after the soak window closes.
