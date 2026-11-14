---
plan_id: nocodb-2026.10.1
component: nocodb
pr: 426                               # Renovate PR #426 "update nocodb/nocodb ( 2026.09.1 -> 2026.10.1 )", branch
                                      # renovate/nocodb-nocodb-2026.x. One-line diff in
                                      # kubernetes/apps/databases/nocodb/app/helmrelease.yaml. Held by the
                                      # `*nocodb*` deny rule (max: patch): a calver month hop parses as `minor`.
kind: image
current: "2026.09.1"                  # measured live 2026-11-09: deploy/nocodb image nocodb/nocodb:2026.09.1,
                                      # digest sha256:27d2fd14670db892ac721849d4f071edce47e386a1e74c921a0162644b9c213d,
                                      # git pin tag: 2026.09.1, /api/v1/version currentVersion 2026.09.1, 0 restarts
target: "2026.10.1"                   # Docker Hub tag_last_pushed 2026-10-29T11:02:50Z (digest sha256:8c2dd068...cd6ae);
                                      # GitHub release 2026.10.1 "Bug Fix Release" published 2026-10-29T11:19:16Z.
                                      # 2026.10.0 (2026-10-23) was the feature release; 2026.10.1 is the first
                                      # patch on it. Both ship migrations: this bump crosses BOTH.
update_type: minor                    # calver month hop; carries 15 knex schema migrations
risk: medium
est_duration_min: 55                  # pre-dump 10 s + gates ~1 min, scratch-restore proof ~6 min (pod start, initdb,
                                      # restore of a 13 MB gzip into a 378 MB database, capture), HR reconcile +
                                      # migration boot ~3 min, 300 s settle before 4.1 passes, 4.4/4.5 ~3 min,
                                      # human acceptance 4.6 ~10 min. Rollback (if needed) adds ~15 min.
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - helmrelease/nocodb
    - deployment/nocodb
    - pvc/nocodb-data                  # near-empty; all real state is in PG
    - database/nocodb@postgresql       # 15 one-way knex migrations run into this database on boot
    - pod/nocodb-restore-proof         # throwaway scratch pod (emptyDir), created and deleted by 2g; never mounts a live PVC
  shared: [postgresql, monitoring]     # postgresql: the shared deployment/postgresql in ns databases (5 tenant DBs;
                                      # NOT restarted by this plan, but the migration writes into it and the
                                      # postgres-digest-refresh plan restarts it). monitoring: 4.5 reads
                                      # kube-prometheus-stack's Prometheus, the window's instrument.
depends_on: []
conflicts_with:
  # [same shared postgresql server]
  - postgres-digest-refresh-2026-11   # restarts deployment/postgresql (sun-attended:2026-12-20) and sweep_history. A restart
                                      # while a migration is mid-flight leaves a held knex lock; never the same night.
                                      # Its own frontmatter says "keep nocodb #426 out of the same night" but it does not
                                      # name this plan_id (this file did not exist): orchestrator follow-up, add the
                                      # reciprocal entry there.
  # [platform events that drop the pod-to-postgres connection or confound the reconnect gates]
  - longhorn-1.13.0
  - talos-linux-1.14.5
  - coredns-1.50.5                    # nocodb reaches postgresql.databases.svc by DNS name
  - etcd-timeouts-5000-500
  # [same HelmRelease / same namespace / same instrument]
  - helm-drift-detection
  - flux-oci-chart-sources
  - flux-reconciler-impersonation
  - redis-fleet-8.10.3                # rolls redis workloads in ns databases; 4.5's alert gate is scoped to ns databases
  - kube-prometheus-stack-93.3.0      # 4.5 reads Prometheus (shared infra of the window)
  - envoy-gateway-1.10.0              # platform roll on the gateway path; confounds the post-migration reachability gates
  # [rollback-class stacking (house rule 81fdd797: every backup-restore pair is declared;
  #  two in one slot leave no rollback capacity for either)]
  - n8n-2.47.7
  - nextcloud-12.0.2
  - media-naming-p3
  - tube-archivist-elasticsearch-9.5.5
  - bitnamilegacy-exit-nextcloud-db
  - talos-power-tuning-ab
exclusive: false
security_ref: F-3568c697              # open security record on the running 2026.09.1 image (newer tag now exists, so this
                                      # bump is its remedy). Detail stays in sweep_findings only.
capability_change: true               # 2026.10.0/2026.10.1 add user-visible surface: classic apps (Interfaces renamed and
                                      # extended), workflow playback, MCP OAuth sign-in, Timeline resource allocation, and a
                                      # behaviour change (API/CSV timestamps now carry milliseconds on PostgreSQL).
rollback_class: backup-restore        # 15 knex migrations run on boot. Upstream documents no downgrade, and two of the
                                      # migration `down()` bodies are explicitly no-ops ("nothing to revert").
                                      # A tag revert is NOT a rollback; section 5 is purge + dump-restore.
backup_gate: "pg_dump of the nocodb database (name resolved from the live NC_DB secret's d= param) taken from deploy/postgresql
  BEFORE the tag edit is pushed, under set -o pipefail, gated on: gzip validity, a 10 MB byte floor (measured 13,338,473 B on
  2026-11-09), COPY-block count equal to the live BASE TABLE count across all non-system schemas (188 = 186 public + 2 user-data),
  the six named metadata tables present exactly once, and the pg_dump completion marker. THEN restored into a throwaway pod and
  the restored copy compared to the live baseline (counts, three knex ledgers name-for-name, user-data rows). A fresh Longhorn
  backup of postgresql-data-5g (runbooks/longhorn-backup-age.py --max-hours 24) is the disaster fallback."
finding_refs: [F-ca5c5597, F-3568c697] # `finding list --grep nocodb` 2026-11-09: F-ca5c5597 (version lane, "nocodb/nocodb 2026.09.1 -> 2026.10.1 (minor)")
                                      # and F-3568c697 (security lane, this image). F-24edea5f / F-655a9c6c matched the
                                      # grep but are generic plan-lane rows, not this component.
review: null
status: draft
window: null                          # recommended, not assigned: sat-attended:2026-12-12 (see section 6)
premises:
  # Read-verb only, one allowed read each. Measured 2026-11-09 against the live cluster.
  - id: live-image-is-still-2026.09.1
    why: >-
      `current:` is 2026.09.1 and the 15-migration expectation was derived against the 2026.09.1 knex ledger (112 v0 rows).
      Any other live tag means the baseline and the expected count are stale; re-derive before executing.
    run: kubectl get deploy nocodb -n databases -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "nocodb/nocodb:2026.09.1"
  - id: db-secret-still-wired-to-nocodb-env
    why: >-
      2f/4.4/5 resolve the DB name from secret `nocodb` (NC_DB). If the envFrom secretRef moved, those commands would target the wrong object.
    run: kubectl get deploy nocodb -n databases -o jsonpath='{.spec.template.spec.containers[0].envFrom[0].secretRef.name}'
    expect_exact: nocodb
  - id: shared-postgresql-instance-still-present
    why: >-
      Dump, baseline, scratch-restore image and rollback all key off deploy/postgresql in ns databases. A renamed or replaced
      instance would silently retarget them.
    run: kubectl get deploy postgresql -n databases -o jsonpath='{.metadata.name}'
    expect_exact: postgresql
  - id: deployment-strategy-recreate
    why: >-
      Single replica on an RWO Longhorn PVC. Recreate guarantees the 2026.09.1 pod is gone before 2026.10.1 boots and runs
      migrations, so two versions never run against the DB at once (and no Multi-Attach).
    run: kubectl get deploy nocodb -n databases -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: helmrelease-ready
    why: "Do not stack a one-way migration on an already-failing release."
    run: kubectl get helmrelease nocodb -n databases -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: httproute-still-wired-to-nocodb-service
    why: >-
      Routing and the forward-auth SecurityPolicy are declared untouched by this plan. If the app route moved or was renamed, the 4.6
      acceptance path and the interference notes describe a different topology.
    run: kubectl get httproute nocodb -n databases -o jsonpath='{.spec.rules[0].backendRefs[0].name}'
    expect_exact: nocodb
  # Not premises (the runner accepts only read verbs of kubectl): the v0 ledger count 112 (read via kubectl exec), the registry tag
  # check (curl) and the Longhorn freshness gate (python3 runbooks/longhorn-backup-age.py) are all executed in section 2 (b), (d), (h).
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/gateway-api-httproute.md
generated: "2026-11-09"
---

# nocodb 2026.09.1 -> 2026.10.1

## 1) Summary & why held

An image-only bump (`nocodb/nocodb`; chart stays on app-template 5.3.0) across **two** calver releases: 2026.10.0 (the
feature release, 2026-10-23) and 2026.10.1 (bug-fix, 2026-10-29). It follows the shape of the retired `nocodb-2026.09.1`
plan (executed green 2026-10-21, retired in `5dc0306c9`; read from git history): mandatory pre-dump, contents gates, purge-then-restore
rollback. **New in this plan, because the previous one lacked it: the dump is restored into a throwaway pod and compared to
the live baseline BEFORE the tag is pushed**, so "we have a dump" means "we have proven the dump restores".

**Why it is held, and the hold is correct.** `runbooks/auto-update-policy.yaml` has the rule `match: "*nocodb*"`, `max: patch`:
"calver - month bumps parse as `minor` but are FEATURE releases that run one-way knex schema migrations into the shared postgresql
instance on boot. Upstream documents no downgrade, so rollback is restore-from-dump only. Never unattended: needs the mandatory
pre-dump + operator acceptance gate from runbooks/maintenance/plans/nocodb-calver.md." `2026.09.1 -> 2026.10.1` is `minor` by
the classifier, above `max: patch`, so Step 0 refuses it. The plan is human-gated (`capability_change: true`, forward-only
migrations, `rollback_class: backup-restore`).

> **Repo correction (not fixed here).** The deny-rule reason names `runbooks/maintenance/plans/nocodb-calver.md`. That file was
> retired (last version `git show a29928dba^:runbooks/maintenance/plans/nocodb-calver.md`) and the reference now dangles. The
> procedure it describes lives in the per-bump plans (this file's section 2f/2g/4.4/5). Point the reason at "the per-bump
> nocodb plan" or restore a stub, so the next planner is not sent to a missing file.

**Migrations: 15 pending, measured against the LIVE ledger.** 2026.10.1's `XcMigrationSourcev0.ts` registers 127 names. The live
`xc_knex_migrationsv0` holds 112 rows (latest `nc_202609260900_interface_detail_default_config`, applied 2026-10-21 21:36Z by the
2026.09.1 bump). `comm` of the two sorted lists (2026-11-09): **15 pending, 0 ledger-only**:

`nc_202609300900_vault_permissions`, `nc_202610011000_automation_executions_run_control`,
`nc_202610040132_normalize_datetime_field_meta_keys`, `nc_202610051531_hq_roadmap`,
`nc_202610071500_invite_links_interface`, `nc_202610081200_users_recanonicalize_proton_emails`,
`nc_202610081300_invite_links_app`, `nc_202610081400_col_button_workflow_meta`,
`nc_202610121136_file_references_url_index`, `nc_202610131500_factory_machines`,
`nc_202610141200_abuse_reports`, `nc_202610141300_abuse_reports_moderation`,
`nc_202610201426_chat_sessions_factory_slug`, `nc_202610221200_mcp_token_hash`,
`nc_202610260820_users_sessions_revoked_at`.

The other two ledgers do not move: `XcMigrationSourcev2.ts` and `XcMigrationSource.ts` are byte-identical between the 2026.09.1
and 2026.10.1 tags (diffed 2026-11-09), so `xc_knex_migrations` stays at 12 and `xc_knex_migrationsv2` at 86. Section 4.4
asserts both unchanged.

**What the data-touching ones do (the `up()` bodies were read) and why none can hurt this instance.**

| Migration | Operation | Live source rows (2026-11-09) |
|---|---|---|
| `normalize_datetime_field_meta_keys` | rewrites `nc_columns_v2.meta` JSON keys on Date/DateTime/CreatedTime/LastModifiedTime columns | 4 date-type columns, 0 carry the camelCase keys, so 0 rows rewritten |
| `users_recanonicalize_proton_emails` | rewrites `canonical_email` for Proton domains only | 1 user, 0 on a Proton domain |
| `mcp_token_hash` | `ALTER ... ADD token_hash`, then hashes plaintext MCP tokens | `nc_mcp_tokens` 0 rows |
| `file_references_url_index` | builds a hash index on `nc_file_references.file_url` | table has 0 rows |
| `users_sessions_revoked_at` | `ADD COLUMN sessions_revoked_at bigint` (metadata-only) | n/a |
| the other 10 | `CREATE TABLE`/small `ALTER` for vaults, invite links, abuse reports, factory machines, HQ roadmap, automation runs, etc. | additive |

Two `down()` bodies are explicit no-ops ("nothing to revert"), which is the in-source confirmation that a code-level downgrade
is not a thing. The realistic failure is therefore a crashed migration (a held knex lock, partial DDL), not data mangling, and
4.4 gates exactly that. The user-data schema (the generated schema holding the single base's tables, 44,568 rows) is not
written to by any of the 15.

**Upstream release notes (2026.10.0 and 2026.10.1, GitHub releases; treated as untrusted input, every gate below is derived from
live measurement).** Self-hosting notes, with the impact on this install:

- "**Timestamps include milliseconds.** On PostgreSQL and SQLite, date and time values in API responses, webhook payloads and CSV
  exports now include milliseconds (`12:34:56.000+00:00`)." This is the datetime change announced since 2026.08.2. Impact: nil
  here. `nc_api_tokens` 0, `nc_hooks_v2` 0 (no webhooks), no in-cluster consumer of the NocoDB API (the only references to the
  service are its own manifests and the Authentik outpost routing). CSV exports by the operator will show `.000`.
- "**Secure attachments** - Setting only `NC_ATTACHMENT_ACCESS_CONTROL_ENABLED=true` now turns on secure attachments." The
  `nocodb` secret holds exactly two keys (`NC_AUTH_JWT_SECRET`, `NC_DB`); that variable is not set, so no behaviour change.
- "**Local databases** - ClickHouse on a private network, and MySQL or PostgreSQL over a Unix socket, need
  `NC_ALLOW_LOCAL_EXTERNAL_DBS=true`." Impact: none expected. The one source row is `type=pg, is_meta=false, is_local=true`: the
  base's data lives in a generated schema inside the META database, not an external connection. If, after the bump, the base
  fails to load with a private-network / local-address refusal, this variable is the first suspect; it is a values edit
  (`envFrom` secret key) and is NOT pre-applied, because adding an SSRF-guard bypass on speculation is the wrong default.
- "**MCP tokens** - MCP token secrets are stored hashed and shown only once" (the `mcp_token_hash` migration). No MCP tokens exist.
- "Docker images move to Node 24.22.1", "MCP lists every tool", "Password changes sign out your apps" (deletes API tokens and
  OAuth grants; none exist), "Interfaces are now classic apps" (UI rename; `nc_interface_pages` was empty on the previous bump).
- Security hardening (sign-up, invitations, OAuth, shared views, exports, database connections, stored secrets): no config needed.

**Blast radius.** One replica, `strategy: Recreate`, downtime about 1-3 minutes. The PVC is near-empty; all state is in the
`nocodb` database (378 MB: 1 base / 2 models / 4 views / 162 columns, 1 user, 44,568 user-data rows; 347 MB of it is the
`nc_audit_v2` audit table at 44,659 rows, which is why the database is large but the gzip dump is 13 MB). The shared
postgresql server is **not restarted**. Routing (HTTPRoutes `nocodb` and `nocodb-authentik-outpost`, SecurityPolicy
`nocodb-forward-auth`, the Homepage tile, Authentik forward-auth outpost) is untouched.

**Risk `medium`**: 15 one-way migrations into a database inside a shared server, no documented downgrade. Not `high`: every
source table the migrations read is empty or unmatched here, the previous month's identical procedure ran clean twice, and the
dump restores in seconds. Not `low` for the same one-way reason.

## 2) Pre-checks

```bash
# RUN 2 (a)-(k) AS ONE Bash CALL, under bash (not zsh: ncq is saved/restored with declare -f), timeout 600000 ms
# (dump + gzip passes + scratch restore ~8 min). Needs SOPS_AGE_KEY_FILE (repo .envrc), kubectl, flux, python3, curl.
cd /Users/mu/code/cberg-home-nextgen
set -o pipefail

# a) nocodb + shared PG healthy, HR Ready, live tag == current, no scratch leftovers:
kubectl get pods -n databases | grep -E 'nocodb|^postgresql'
HR_READY=$(kubectl get hr -n databases nocodb -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
LIVE_IMG=$(kubectl get deploy -n databases nocodb -o jsonpath='{.spec.template.spec.containers[0].image}')
echo "HR Ready=[$HR_READY] image=[$LIVE_IMG]"      # measured 2026-11-09: True / nocodb/nocodb:2026.09.1
[ "$HR_READY" = "True" ] || { echo 'FAIL: HR nocodb not Ready'; exit 1; }
[ "$LIVE_IMG" = "nocodb/nocodb:2026.09.1" ] || { echo 'FAIL: live image != current: plan is stale, re-derive'; exit 1; }
LEFT=$(kubectl get pods -n databases -l restore-proof=nocodb --no-headers 2>/dev/null | wc -l | tr -d ' ')
[ "$LEFT" = "0" ] || { echo "FAIL: $LEFT leftover nocodb-restore-proof pod(s); delete them first"; exit 1; }

# b) target still resolves and nothing NEWER is out (a newer 2026.10.x/2026.11.x => re-plan, do not run):
curl -s "https://hub.docker.com/v2/repositories/nocodb/nocodb/tags/2026.10.1" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['name'], d['tag_last_pushed']); sys.exit(0 if d['name']=='2026.10.1' else 1)" \
  || { echo 'FAIL: target tag missing'; exit 1; }
curl -s "https://hub.docker.com/v2/repositories/nocodb/nocodb/tags/?page_size=25&name=2026.1" \
  | python3 -c "import sys,json; print(sorted(r['name'] for r in json.load(sys.stdin)['results']))"
# measured 2026-11-09: ['2026.10.0', '2026.10.1']. Any other entry (2026.10.2, 2026.11.x) => ADVISORY: retarget (README: refresh in place).

# c) release-age cooldown (>= 48 h; cleared 2026-10-31T11:02Z, measured age ~ 11 days on 2026-11-09)
python3 -c "
from datetime import datetime, timezone; import sys
age=(datetime.now(timezone.utc)-datetime.fromisoformat('2026-10-29T11:02:50+00:00')).total_seconds()/3600
print(f'age_hours={age:.1f}'); sys.exit(0 if age>=48 else 1)" || { echo 'FAIL: cooldown not cleared'; exit 1; }

# d) Longhorn backups fresh: the section 5 disaster fallback. The shared script takes the newest CONFIRMED backup
#    (backup-CR cross-check), unlike raw status.lastBackupAt which can lag a cycle.
python3 runbooks/longhorn-backup-age.py postgresql-data-5g nocodb-data --max-hours 24 \
  || { echo 'FAIL: Longhorn backup freshness gate'; exit 1; }
# measured 2026-11-09 00:3x local: postgresql-data-5g 0.7h FRESH (backup-8656246909b2459e at=2026-11-08T23:05:28Z),
# nocodb-data 0.7h FRESH. FAILS ON: a backup older than 24 h (prints STALE, rc!=0), or no confirmed backup (NONE, rc!=0).
# The script's own tests: python3 runbooks/tests/test-longhorn-backup-age.py (prints "all passed", 2026-11-09).

# e) not the same night as the shared-server restart or another DB-touching plan:
.venv/bin/python3 runbooks/maintenance-plan.py --open | grep -E 'postgres-digest-refresh|redis-fleet|longhorn-1.13|talos-linux|coredns' \
  || echo 'no conflicting plan listed'
# Compare the window printed beside each against TONIGHT'S window. Same slot => STOP, do not run.

# f) DB name from the live secret (never written to the repo), shared helpers:
NCDB_NAME=$(sops -d /Users/mu/code/cberg-home-nextgen/kubernetes/apps/databases/nocodb/app/secret.sops.yaml \
  | python3 -c "import sys,yaml,urllib.parse as u; s=yaml.safe_load(sys.stdin)['stringData']['NC_DB']; print(u.parse_qs(u.urlsplit(s).query)['d'][0])")
[ -n "$NCDB_NAME" ] || { echo 'FAIL: DB name did not resolve'; exit 1; }
echo "DB name: $NCDB_NAME"                          # measured 2026-11-09: nocodb
ncq() { kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -tAc "$0"' "$1"; }

# g) MANDATORY pre-dump (the backup_gate), taken BEFORE the tag edit.
B=~/backups/nocodb/pre-2026.10.1
mkdir -p "$B" && chmod 700 "$B"
OUT="$B/nocodb-pre-2026.10.1.sql.gz"
kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$NCDB" --clean --if-exists' \
  | gzip > "$OUT" || { echo 'FAIL: pg_dump pipeline non-zero'; exit 1; }
chmod 600 "$OUT"
gzip -t "$OUT" || { echo 'FAIL: gzip invalid'; exit 1; }                       # GATE 1 (shape only)
SZ=$(stat -f%z "$OUT")                                                           # BSD stat (macOS)
[ "${SZ:-0}" -ge 10000000 ] || { echo "FAIL: dump too small: ${SZ:-unset} B"; exit 1; }   # GATE 2
# GATE 3: one COPY block per live BASE TABLE in EVERY non-system schema (the base's rows live in a second, generated
# schema; a public-only count would not notice a dump that lost the user data). Measured 2026-11-09: live 188, COPY 188.
LIVE_TABLES=$(ncq "select count(*) from information_schema.tables where table_schema not in ('pg_catalog','information_schema') and table_type='BASE TABLE'")
[ -n "$LIVE_TABLES" ] || { echo 'FAIL: live table count did not read'; exit 1; }
DUMP_COPIES=$(gunzip -c "$OUT" | grep -c '^COPY ')
echo "live BASE TABLEs=$LIVE_TABLES  COPY blocks=$DUMP_COPIES"
[ "$DUMP_COPIES" -eq "$LIVE_TABLES" ] || { echo "FAIL: $DUMP_COPIES COPY blocks for $LIVE_TABLES tables"; exit 1; }
# GATE 4: the named metadata tables AND the ledger the 15 migrations write to. grep >/dev/null, NOT grep -q: -q exits early,
# gunzip takes SIGPIPE and under pipefail a PRESENT table reads as missing (false FAIL seen 2026-09-26). Each matches once.
for t in nc_bases_v2 nc_models_v2 nc_views_v2 nc_columns_v2 xc_knex_migrationsv2 xc_knex_migrationsv0; do
  gunzip -c "$OUT" | grep "^COPY public\.$t " >/dev/null || { echo "FAIL: $t missing from dump"; exit 1; }
done
# GATE 5: completion marker. The newer pg_dump appends \unrestrict AFTER it, so look in the last 8 lines, not the last 1.
gunzip -c "$OUT" | tail -8 | grep 'PostgreSQL database dump complete' >/dev/null \
  || { echo 'FAIL: no completion marker, dump truncated'; exit 1; }
echo "BACKUP GATE PASSED: $OUT ($SZ B, $DUMP_COPIES tables)"
# NEGATIVE CONTROL (measured 2026-11-09 on a scratch copy of today's dump, first 5,000,000 bytes re-gzipped): gzip -t PASSES
# (shape only, which is why GATE 1 alone is worthless), COPY blocks = 2 != 188 (GATE 3 fails), marker count 0 (GATE 5 fails).

# h) BASELINE: files read back by 3.0, 4.4, the scratch proof and 5. Writes the two helper scripts so later blocks are
#    self-contained (no shell variables carried over). Dry-tested 2026-11-09, see the controls listed under 4.4.
cat > "$B/capture.sh" <<'SH'
# sourced with OUTDIR set and ncq() defined in the caller (live OR scratch server)
mkdir -p "$OUTDIR"
ncq "select name from xc_knex_migrations order by name" > "$OUTDIR/ledger-base.txt"
ncq "select name from xc_knex_migrationsv0 order by name" > "$OUTDIR/ledger-v0.txt"
ncq "select name from xc_knex_migrationsv2 order by name" > "$OUTDIR/ledger-v2.txt"
{
  echo "tables=$(ncq "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")"
  echo "knex_base=$(ncq "select count(*) from xc_knex_migrations")"
  echo "knex_v0=$(ncq "select count(*) from xc_knex_migrationsv0")"
  echo "knex_v2=$(ncq "select count(*) from xc_knex_migrationsv2")"
  echo "locks=$(ncq "select (select max(is_locked) from xc_knex_migrations_lock)||'/'||(select max(is_locked) from xc_knex_migrationsv0_lock)||'/'||(select max(is_locked) from xc_knex_migrationsv2_lock)")"
  echo "triple=$(ncq "select (select count(*) from nc_bases_v2)||'/'||(select count(*) from nc_models_v2)||'/'||(select count(*) from nc_views_v2)")"
  echo "cols=$(ncq "select count(*) from nc_columns_v2")"
  echo "users=$(ncq "select count(*) from nc_users_v2")"
  echo "userrows=$(ncq "select string_agg(n||'='||c, ' ' order by n) from (select table_schema||'.'||table_name n, (xpath('/row/c/text()', query_to_xml(format('select count(*) c from %I.%I', table_schema, table_name), false, true, '')))[1]::text c from information_schema.tables where table_schema not in ('public','pg_catalog','information_schema') and table_type='BASE TABLE') s")"
} > "$OUTDIR/counts.txt"
cat "$OUTDIR/counts.txt"
SH
cat > "$B/compare.py" <<'PY'
import sys, re
mode, pre_dir, post_dir = sys.argv[1], sys.argv[2], sys.argv[3]   # mode: upgrade | restore | same
EXPECT_NEW_V0 = 15          # 127 registered in 2026.10.1 minus 112 in the live ledger (2026-11-09)
def kv(d):
    out = {}
    for line in open(f'{d}/counts.txt'):
        k, _, v = line.rstrip('\n').partition('=')
        out[k] = v
    return out
def ledger(d, v):
    return [l.strip() for l in open(f'{d}/ledger-{v}.txt') if l.strip()]
pre, post = kv(pre_dir), kv(post_dir)
bad, soft = [], []
need = ['tables','knex_base','knex_v0','knex_v2','locks','triple','cols','users','userrows']
for k in need:
    for side, d in (('pre', pre), ('post', post)):
        if not d.get(k):
            bad.append(f'{side} {k} is EMPTY - the read failed, gate did not measure')
if bad: print('FAIL:', '; '.join(bad)); sys.exit(1)
if not re.fullmatch(r'\S+=\d+( \S+=\d+)*', pre['userrows']):
    print(f"FAIL: pre userrows malformed: {pre['userrows']!r}"); sys.exit(1)
if sum(int(x.split('=')[-1]) for x in pre['userrows'].split()) == 0:
    print('FAIL: pre userrows sums to 0 - baseline is not measuring user data'); sys.exit(1)
for k in need: print(f'{k:10} {pre[k]} -> {post[k]}')
if post['locks'] != '0/0/0': bad.append(f"knex lock held: {post['locks']} (a migration crashed mid-run)")
if post['triple'] != pre['triple']: bad.append(f"base/model/view counts changed {pre['triple']} -> {post['triple']}")
if post['userrows'] != pre['userrows']: bad.append(f"USER DATA row counts changed: {pre['userrows']} -> {post['userrows']}")
if post['users'] != pre['users']: bad.append(f"nc_users_v2 count changed {pre['users']} -> {post['users']}")
for v in ('base', 'v0', 'v2'):
    a, b = ledger(pre_dir, v), ledger(post_dir, v)
    if not a: bad.append(f'pre ledger-{v} empty'); continue
    lost = sorted(set(a) - set(b))
    if lost: bad.append(f'ledger {v} LOST {len(lost)} entries (rolled back): {lost[:5]}')
if mode == 'upgrade':
    for k in ('tables', 'cols'):
        if int(post[k]) < int(pre[k]): bad.append(f'{k} shrank {pre[k]} -> {post[k]}')
    for k in ('knex_base', 'knex_v2'):      # 2026.10.1 changes neither source (diffed vs 2026.09.1)
        if post[k] != pre[k]: bad.append(f'{k} moved {pre[k]} -> {post[k]}: this plan expects it unchanged')
    added = int(post['knex_v0']) - int(pre['knex_v0'])
    print(f'v0 ledger advanced by {added} (expected {EXPECT_NEW_V0})')
    if added < 1: bad.append('v0 ledger did not advance: the new image did not migrate')
    elif added != EXPECT_NEW_V0: soft.append(f'v0 advanced by {added}, expected {EXPECT_NEW_V0}')
else:  # restore | same: must reproduce the baseline EXACTLY
    for k in ('tables', 'knex_base', 'knex_v0', 'knex_v2', 'cols'):
        if post[k] != pre[k]: bad.append(f'{k} {pre[k]} -> {post[k]} (must be exact)')
    for v in ('base', 'v0', 'v2'):
        if ledger(pre_dir, v) != ledger(post_dir, v): bad.append(f'ledger {v} differs from baseline')
if bad: print('FAIL: ' + ' | '.join(bad)); sys.exit(1)
if soft: print('OPERATOR-DECISION (no auto-rollback; all hard gates green): ' + ' | '.join(soft)); sys.exit(2)
print(f'CONTENTS GATE PASSED ({mode})')
PY
OUTDIR="$B/pre"; . "$B/capture.sh"
# Measured live 2026-11-09 (expect this shape): tables=186 knex_base=12 knex_v0=112 knex_v2=86 locks=0/0/0 triple=1/2/4
#   cols=162 users=1 userrows=<generated-schema>.<table>=0 <generated-schema>.<table>=44568
python3 "$B/compare.py" same "$B/pre" "$B/pre" || { echo 'FAIL: baseline incomplete, do not proceed'; exit 1; }   # self-check, must PASS
# ~/backups/nocodb/pre-2026.09.1/ is the PREVIOUS bump's dump. This plan never reads it.

# i) SCRATCH RESTORE PROOF: restore the dump we just took into a throwaway pod (emptyDir, no live PVC, no live DB touched),
#    then compare the restored copy to the live baseline. NOT a Longhorn restore: it proves the logical dump itself.
IMG=$(kubectl get deploy -n databases postgresql -o jsonpath='{.spec.template.spec.containers[0].image}')
echo "scratch image (same as the live server): $IMG"   # measured: pgvector/pgvector:0.8.7-pg16@sha256:7b822b0a...
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: nocodb-restore-proof
  namespace: databases
  labels: {restore-proof: "nocodb"}
spec:
  restartPolicy: Never
  containers:
    - name: pg
      image: $IMG
      env:
        - {name: POSTGRES_PASSWORD, value: scratch-only-not-a-secret}
        - {name: PGDATA, value: /scratch/pgdata}
      volumeMounts: [{name: scratch, mountPath: /scratch}]
      resources: {requests: {cpu: 100m, memory: 256Mi}, limits: {memory: 1Gi}}
  volumes:
    - name: scratch
      emptyDir: {sizeLimit: 3Gi}
EOF
kubectl wait --for=condition=Ready pod/nocodb-restore-proof -n databases --timeout=180s || { echo 'FAIL: scratch pod not Ready'; exit 1; }
# The image's entrypoint runs a TEMPORARY socket-only server during initdb; pg_isready would already say "ready" on it.
# Wait for the entrypoint's own end-of-init line, THEN for the real server.
for i in $(seq 1 60); do
  kubectl logs -n databases nocodb-restore-proof 2>/dev/null | grep 'init process complete' >/dev/null && break; sleep 2
done
for i in $(seq 1 30); do
  kubectl exec -n databases nocodb-restore-proof -- pg_isready -U postgres >/dev/null 2>&1 && break; sleep 2
done
sq() { kubectl exec -n databases nocodb-restore-proof -- psql -U postgres -d nocodb -tAc "$1"; }
kubectl exec -n databases nocodb-restore-proof -- psql -U postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE nocodb LOGIN" -c "CREATE DATABASE nocodb OWNER nocodb" \
  || { echo 'FAIL: scratch role/db create'; kubectl delete pod -n databases nocodb-restore-proof --wait=false; exit 1; }
EMPTY=$(sq "select count(*) from information_schema.tables where table_schema='public'")
[ "$EMPTY" = "0" ] || { echo "FAIL: scratch db not empty ($EMPTY): the proof would measure nothing"; exit 1; }   # POSITIVE CONTROL: starts at 0
gunzip -c "$OUT" | kubectl exec -i -n databases nocodb-restore-proof -- psql -U postgres -d nocodb -v ON_ERROR_STOP=1 >/dev/null \
  || { echo 'FAIL: dump did not restore into the scratch server'; kubectl delete pod -n databases nocodb-restore-proof --wait=false; exit 1; }
ncq_live=$(declare -f ncq); ncq() { sq "$1"; }          # capture.sh calls ncq(): point it at the scratch server
OUTDIR="$B/scratch"; . "$B/capture.sh"
python3 "$B/compare.py" restore "$B/pre" "$B/scratch" || { echo 'FAIL: restored copy != live baseline, THE DUMP IS NOT RESTORABLE. Do not proceed'; kubectl delete pod -n databases nocodb-restore-proof --wait=false; exit 1; }
kubectl delete pod -n databases nocodb-restore-proof --wait=true --timeout=120s
eval "$ncq_live"                                         # restore the live ncq
[ "$(kubectl get pods -n databases -l restore-proof=nocodb --no-headers | wc -l | tr -d ' ')" = "0" ] || { echo 'FAIL: scratch pod still present'; exit 1; }
echo 'SCRATCH RESTORE PROOF PASSED'
# FAILS ON: pod not Ready; role/db create error; scratch db not empty before the restore; psql ON_ERROR_STOP error mid-replay;
# any count/ledger/user-row mismatch between the restored copy and the live baseline (compare.py restore mode is exact).
# NOT executed at planning time (planning is read-only against the cluster). Dry-run verified instead: the Pod manifest
# passes `kubectl apply --dry-run=server`, the dump contains no `public` schema DDL (a fresh db's public does not collide),
# and every owner in the dump is the single role `nocodb`, which this block creates. REVIEWER/WINDOW: first live run of this
# block is the window's; if the pod misbehaves, STOP before the tag edit, nothing live was touched.

# j) no in-flight Flux trouble in ns databases (advisory outside it)
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -n databases | awk 'NR==1 || $4 != "True"'

# k) PRE-CHANGE run of the 4.5 Prometheus block with EXPECT_IMG=docker.io/nocodb/nocodb:2026.09.1. It must print
#    PROMETHEUS GATE PASSED. A scoped alert that predates the change => STOP.
```

## 3) Steps

0. **Drift gate, run immediately before the tag edit** (one Bash call): proves the live DB still equals the dumped one, so the
   dump you are about to rely on is the current state, not an hour-old one.
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   set -o pipefail
   NCDB_NAME=$(sops -d kubernetes/apps/databases/nocodb/app/secret.sops.yaml \
     | python3 -c "import sys,yaml,urllib.parse as u; s=yaml.safe_load(sys.stdin)['stringData']['NC_DB']; print(u.parse_qs(u.urlsplit(s).query)['d'][0])")
   ncq() { kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
     'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -tAc "$0"' "$1"; }
   B=~/backups/nocodb/pre-2026.10.1
   [ -s "$B/pre/counts.txt" ] && gzip -t "$B/nocodb-pre-2026.10.1.sql.gz" || { echo 'FAIL: no dump/baseline, 2 did not run'; exit 1; }
   rm -rf "$B/predrift"; OUTDIR="$B/predrift"; . "$B/capture.sh"
   python3 "$B/compare.py" same "$B/pre" "$B/predrift" || { echo 'FAIL: DB changed since the dump. Re-run all of section 2 (new dump), do not edit'; exit 1; }
   ```
   If this fails because a person edited the base after the dump, re-run section 2 entirely: a dump older than the live
   state is a rollback to the wrong data.

1. **Marker** (attended-tier update per `application-update.md`):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   runbooks/update-marker.sh add nocodb databases 4 "2026.09.1 -> 2026.10.1 (15 knex migrations)"
   ```

2. **Disable HR upgrade remediation and bump the tag, in one edit.** A Flux remediation rollback while knex is writing schema
   would flip the image back halfway through the migration. Dry-tested on a scratch copy of today's `helmrelease.yaml` with
   BSD sed and python on 2026-11-09. The `retries: 3` under `install:` is left alone; the python anchor matches only the
   `upgrade:` block (asserted `count == 1`).
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   F=kubernetes/apps/databases/nocodb/app/helmrelease.yaml
   sed -i '' 's/^\([[:space:]]*tag:[[:space:]]*\)2026\.09\.1$/\12026.10.1/' "$F"
   python3 - "$F" <<'PY'
   import sys
   p = sys.argv[1]; s = open(p).read()
   old = "  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 3\n"
   new = "  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 0\n      remediateLastFailure: false\n"
   assert s.count(old) == 1, 'upgrade block not found exactly once, file moved, STOP'
   open(p, 'w').write(s.replace(old, new)); print('upgrade remediation disabled')
   PY
   git diff --stat -- "$F"; git diff -- "$F"
   ```
   The expected diff, exactly as produced on the scratch copy (`diff orig new`):
   ```
   24c24,25
   <       retries: 3
   ---
   >       retries: 0
   >       remediateLastFailure: false
   36c37
   <               tag: 2026.09.1
   ---
   >               tag: 2026.10.1
   ```
   This is the same one-line change Renovate PR #426 carries (plus the temporary remediation guard). Do not merge the PR
   separately: land this edit, then close #426 with a pointer to the commit (or merge #426 first and apply only the
   python half; the python anchor does not depend on the tag).

3. **Commit + push.** The worktree is shared, so use `--only` and check the subject:
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   MSG=/tmp/msg-nocodb-2026.10.1-$(date +%s).txt
   printf 'feat(nocodb): 2026.09.1 -> 2026.10.1 (15 knex migrations; plan nocodb-2026.10.1, PR #426)\n' > "$MSG"
   git commit --only kubernetes/apps/databases/nocodb/app/helmrelease.yaml -F "$MSG"
   git log -1 --format=%s     # MUST be the subject above; amend before push if not
   git show --stat HEAD       # ONLY the nocodb helmrelease
   git push
   git rev-parse HEAD         # RECORD this as BUMP_SHA for section 5 step 4
   ```

4. **Watch the migration boot.** Bounded commands only; never `kubectl logs -f` in the executed sequence.
   ```bash
   flux reconcile kustomization nocodb -n databases --with-source   # only if the webhook lags
   kubectl rollout status deploy/nocodb -n databases --timeout=5m
   kubectl logs -n databases deploy/nocodb --since=10m --tail=200
   ```
   `rollout status` can report on the OLD generation if it races the HR upgrade; 4.1 re-reads the live pod's image and that
   read is the binding check. Liveness has `initialDelaySeconds: 60` + 3 x 30 s: a migration that takes longer than about
   150 s would be killed mid-run. The previous two bumps (12 migrations each) booted well inside that; if the pod restarts
   (4.1 `restartCount`), 4.4 will show a held knex lock, which is a rollback trigger.

5. **After section 4 passes:** restore HR remediation, commit, clear the marker. Dry-tested as the inverse of step 2; the file
   returned byte-identical to the original apart from the tag.
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   F=kubernetes/apps/databases/nocodb/app/helmrelease.yaml
   python3 - "$F" <<'PY'
   import sys
   p = sys.argv[1]; s = open(p).read()
   new = "  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 3\n"
   old = "  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 0\n      remediateLastFailure: false\n"
   assert s.count(old) == 1, 'temp remediation block not found, STOP'
   open(p, 'w').write(s.replace(old, new)); print('remediation restored')
   PY
   MSG=/tmp/msg-nocodb-remed-$(date +%s).txt
   printf 'chore(nocodb): restore HR remediation retries after 2026.10.1 bump\n' > "$MSG"
   git commit --only "$F" -F "$MSG"
   git log -1 --format=%s && git show --stat HEAD
   git push
   runbooks/update-marker.sh clear nocodb
   ```

## 4) Verification

Run each sub-block as its own Bash call. Every block re-derives its own inputs from files and the cluster. Do not accept a
gate that printed nothing.

```bash
# --- 4.1 HR Ready, pod on the NEW image, stable (re-run, never sleep) -------
cd /Users/mu/code/cberg-home-nextgen
set -o pipefail
HR_READY=$(kubectl get hr -n databases nocodb -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
echo "HR Ready=[$HR_READY]"
[ "$HR_READY" = "True" ] || { echo 'FAIL: HelmRelease nocodb not Ready'; exit 1; }
kubectl get pods -n databases -l app.kubernetes.io/name=nocodb -o json > /tmp/nocodb-pod.json \
  || { echo 'FAIL: could not read nocodb pod'; exit 1; }
python3 - /tmp/nocodb-pod.json <<'PY' || { echo 'FAIL: 4.1 pod gate'; exit 1; }
import json, sys
from datetime import datetime, timezone
items = json.load(open(sys.argv[1]))['items']
if len(items) != 1: print(f'expected 1 nocodb pod, got {len(items)}'); sys.exit(1)
p = items[0]; img = p['spec']['containers'][0]['image']; cs = p['status']['containerStatuses'][0]
st = (cs.get('state') or {}).get('running', {}).get('startedAt')
if not st: print(f'container not running: {cs.get("state")}'); sys.exit(1)
age = (datetime.now(timezone.utc) - datetime.fromisoformat(st.replace('Z', '+00:00'))).total_seconds()
print(f'image={img} restartCount={cs["restartCount"]} running_for={age:.0f}s')
if img != 'nocodb/nocodb:2026.10.1': print(f'wrong image {img}'); sys.exit(1)
if cs['restartCount'] != 0: print('restartCount != 0 (crash-loop, or liveness killed it mid-migration)'); sys.exit(1)
if age < 300: print(f'NOT YET SETTLED: re-run in {int(300-age)+5}s'); sys.exit(1)
print('4.1 PASSED')
PY
# FAILS ON: HR not Ready; image still 2026.09.1 (TODAY's live state prints "wrong image nocodb/nocodb:2026.09.1", rc=1);
# restartCount>0; not running; <300 s since start. Same gate as the 2026.09.1 plan's 4.1.

# --- 4.2 VERSION CONTENTS GATE: the running code's self-reported version ----
set -o pipefail
kubectl port-forward -n databases svc/nocodb 19392:8080 >/dev/null 2>&1 & PF=$!
trap 'kill $PF 2>/dev/null' EXIT
curl -s -o /dev/null --retry 15 --retry-connrefused --retry-delay 1 --max-time 30 http://localhost:19392/api/v1/health
VER=$(curl -s --max-time 10 http://localhost:19392/api/v1/version \
      | python3 -c "import sys,json; print(json.load(sys.stdin).get('currentVersion',''))" 2>/dev/null)
echo "currentVersion=[$VER]"
[ "$VER" = "2026.10.1" ] || { echo "FAIL: app reports [$VER], expected 2026.10.1"; exit 1; }
curl -s --max-time 10 http://localhost:19392/api/v1/health | grep '"message":"OK"' >/dev/null \
  || { echo 'FAIL: /api/v1/health body not message OK'; exit 1; }
# API layer + auth enforced (no API token exists, so a base listing needs the DB, see 4.4): an UNAUTHENTICATED call must be
# refused. A 200 here would mean auth is off; a 000/5xx means the API did not come up.
CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://localhost:19392/api/v2/meta/bases)
echo "unauthenticated /api/v2/meta/bases -> $CODE"
[ "$CODE" = "401" ] || { echo "FAIL: expected 401, got $CODE"; exit 1; }
kill $PF 2>/dev/null; trap - EXIT
# Measured 2026-11-09 on the live 2026.09.1 pod: {"currentVersion":"2026.09.1","releaseVersion":"2026.09.1"}, health
# {"message":"OK",...}, unauthenticated bases listing 401, root 200. So TODAY this gate FAILS at the version line
# (VER=2026.09.1), as it must. An unreachable app gives VER="" which never equals 2026.10.1.
# No service token exists (nc_api_tokens 0, nc_mcp_tokens 0 on 2026-11-09), so no authenticated base listing is attempted;
# the base/model/view/row contents are gated against the DB in 4.4 instead. Creating a token just to test would add an
# artifact to a database whose counts this plan compares.

# --- 4.3 BOOT LOG GATE --------------------------------------------------------
kubectl logs -n databases deploy/nocodb --since=20m > /tmp/nocodb-boot.log 2>&1
[ -s /tmp/nocodb-boot.log ] || { echo 'FAIL: empty boot log, no restart happened, gate measured nothing'; exit 1; }
echo "boot log lines: $(wc -l < /tmp/nocodb-boot.log)"
grep -inE '"level":(50|60)|unhandled|econnrefused|cannot find module|migration failed|fatal' /tmp/nocodb-boot.log
ERRS=$(grep -cE '"level":(50|60)' /tmp/nocodb-boot.log)
FATALS=$(grep -icE 'unhandled|econnrefused|cannot find module|migration failed|fatal' /tmp/nocodb-boot.log)
echo "pino error/fatal records: $ERRS   plain-text fatal markers: $FATALS"
[ "$ERRS" -eq 0 ]   || { echo "FAIL: $ERRS pino error/fatal records"; exit 1; }
[ "$FATALS" -eq 0 ] || { echo "FAIL: $FATALS fatal markers"; exit 1; }
grep 'App started successfully' /tmp/nocodb-boot.log >/dev/null \
  || { echo 'FAIL: no "App started successfully", boot did not complete'; exit 1; }
# Migration log lines: knex logs per-migration progress at info level. The count is ADVISORY (4.4 is the binding measure),
# but print what the pod said so the operator sees the 15:
echo "migration-related log lines: $(grep -icE 'migrat' /tmp/nocodb-boot.log)"
grep -iE 'migrat' /tmp/nocodb-boot.log | cut -c1-200 | head -30
# Measured 2026-11-09 on the live 2026.09.1 pod (running 18 d): the 5-line tail ends "App started successfully." and
# contains 0 error records. The pre-change boot log of the 2026.09.1 pod was measured at 29 lines, exactly 1 "App started
# successfully", 0 records at pino level 40/50/60 (2026-10-01). The EMPTY-LOG guard exists because `--since=20m` on a pod
# that did not restart reads nothing, and an empty file would pass every grep -c = 0 check.
# If "migrat" matches 0 lines the pod may log migrations only at debug level: do not fail on it, rely on 4.4.

# --- 4.4 MIGRATION + DATA CONTENTS GATE (the knex ledgers and user rows) ------
cd /Users/mu/code/cberg-home-nextgen
set -o pipefail
NCDB_NAME=$(sops -d kubernetes/apps/databases/nocodb/app/secret.sops.yaml \
  | python3 -c "import sys,yaml,urllib.parse as u; s=yaml.safe_load(sys.stdin)['stringData']['NC_DB']; print(u.parse_qs(u.urlsplit(s).query)['d'][0])")
[ -n "$NCDB_NAME" ] || { echo 'FAIL: DB name did not resolve'; exit 1; }
ncq() { kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -tAc "$0"' "$1"; }
B=~/backups/nocodb/pre-2026.10.1
[ -s "$B/pre/counts.txt" ] || { echo "FAIL: no baseline at $B/pre, section 2h did not run"; exit 1; }
rm -rf "$B/post"; OUTDIR="$B/post"; . "$B/capture.sh"
python3 "$B/compare.py" upgrade "$B/pre" "$B/post"; RC=$?
[ $RC -eq 0 ] && echo 'GATE PASSED'
[ $RC -eq 2 ] && echo 'OPERATOR DECISION: all hard gates green but the migration COUNT differs from 15. Read the ledger diff (comm -13 pre/ledger-v0.txt post/ledger-v0.txt), do not auto-roll-back.'
[ $RC -le 2 ] && [ $RC -ne 1 ] || { echo 'FAIL: 4.4 contents gate, see section 5'; exit 1; }
# HARD FAILS ON: any knex lock still held (crashed migration); any base/v0/v2 ledger entry from the baseline missing
# (rolled back); tables/cols shrinking; base or v2 ledger count MOVING; base/model/view triple or nc_users_v2 count changing;
# ANY change to the per-table user-data row counts; v0 ledger not advancing at all; any empty read.
# RC 2 (not a hard fail): v0 advanced by a number other than 15, e.g. the image registers a different list than the git tag.
# DRY-TESTED 2026-11-09 against the LIVE baseline (compare same, pre vs pre -> PASS, rc 0) and eight synthetic post-states,
# each giving the stated verdict: good (+15 v0, tables 186->195) rc 0 "CONTENTS GATE PASSED (upgrade)"; lock 0/1/0 ->
# "knex lock held"; one user-data count 44568->44000 -> "USER DATA row counts changed"; nc_users_v2 1->2 -> "nc_users_v2
# count changed"; v0 advanced by only 7 -> rc 2 OPERATOR-DECISION; v0 not advanced -> "did not migrate"; cols emptied ->
# "post cols is EMPTY"; 62 ledger names deleted (restore mode) -> "ledger v0 LOST 62 entries"; knex_v2 86->87 -> "moved".
# Expected on success: knex_v0 112 -> 127, tables 186 -> more than 186, knex_base 12 and knex_v2 86 unchanged, triple 1/2/4
# unchanged, users 1, userrows unchanged, locks 0/0/0.

# --- 4.5 PROMETHEUS GATE: image series, Flux readiness, scoped alerts ---------
set -o pipefail
EXPECT_IMG="${EXPECT_IMG:-docker.io/nocodb/nocodb:2026.10.1}"
SCOPE_NS="${SCOPE_NS:-databases}"
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19391:9090 >/dev/null 2>&1 & PF=$!
trap 'kill $PF 2>/dev/null' EXIT
curl -s -o /dev/null --retry 15 --retry-connrefused --retry-delay 1 --max-time 30 http://localhost:19391/-/ready
D=$(mktemp -d)
curl -s --max-time 10 http://localhost:19391/api/v1/alerts > "$D/alerts.json"
curl -s --max-time 10 --get --data-urlencode 'query=kube_pod_container_info{namespace="databases",pod=~"nocodb-.*"}' http://localhost:19391/api/v1/query > "$D/info.json"
curl -s --max-time 10 --get --data-urlencode 'query=flux_resource_info{kind="HelmRelease",name="nocodb"}' http://localhost:19391/api/v1/query > "$D/flux.json"
kill $PF 2>/dev/null; trap - EXIT
EXPECT_IMG="$EXPECT_IMG" SCOPE_NS="$SCOPE_NS" python3 - "$D" <<'PY' || { echo 'FAIL: 4.5 Prometheus gate'; exit 1; }
import json, os, sys
d = sys.argv[1]
def load(n):
    j = json.load(open(f'{d}/{n}.json'))
    assert j.get('status') == 'success', f'{n}: Prometheus API not success, instrument down, gate did NOT measure'
    return j['data']
bad = []
info = load('info')['result']
imgs = sorted({r['metric'].get('image') for r in info})
print('kube_pod_container_info images:', imgs)
if not info: bad.append('kube_pod_container_info returned 0 series, scrape broken, not a pass')
elif imgs != [os.environ['EXPECT_IMG']]: bad.append(f"image series {imgs} != [{os.environ['EXPECT_IMG']}]")
fl = load('flux')['result']
print('flux_resource_info nocodb:', [(r['metric'].get('ready'), r['metric'].get('suspended')) for r in fl])
if not fl: bad.append('flux_resource_info returned 0 series for HelmRelease nocodb')
elif any(r['metric'].get('ready') != 'True' for r in fl): bad.append('flux_resource_info: HelmRelease nocodb ready != True')
ns = os.environ['SCOPE_NS']
fire = [a for a in load('alerts')['alerts'] if a['state'] == 'firing'
        and a['labels'].get('alertname') not in ('Watchdog', 'InfoInhibitor')]
mine = lambda a: a['labels'].get('namespace') == ns or a['labels'].get('exported_namespace') == ns or any('nocodb' in str(v) for v in a['labels'].values())
scoped = sorted({a['labels']['alertname'] for a in fire if mine(a)})
print('advisory (other namespaces, non-gating):', sorted({a['labels']['alertname'] for a in fire if not mine(a)}))
print(f'SCOPED ({ns} / nocodb) firing: {scoped}')
if scoped: bad.append(f'scoped alerts firing: {scoped}')
if bad: print('FAIL: ' + ' | '.join(bad)); sys.exit(1)
print('PROMETHEUS GATE PASSED')
PY
# DRY-TESTED 2026-11-09 (identical block, read-only):
#   EXPECT_IMG=docker.io/nocodb/nocodb:2026.09.1 (the section-2k pre-check form) -> "PROMETHEUS GATE PASSED", rc 0
#     (image series ['docker.io/nocodb/nocodb:2026.09.1'], flux ready True/suspended False, scoped alerts [])
#   default EXPECT_IMG (2026.10.1) against today's cluster -> "FAIL: image series [...2026.09.1] != [...2026.10.1]", rc 1
#     (the gate can fail). Other-namespace alerts firing today (AragScrapeDown, TargetDown, MaintenanceWindowMissed, ...)
#     are printed as advisory and do not gate.
# If the old pod's series lingers right after rollout, re-run once 4.1 has passed.

# --- 4.6 OPERATOR ACCEPTANCE (why this stays attended): SSO login is a HUMAN step ----
# Log in through the normal route (Authentik forward-auth, then NocoDB's own login). No agent can do this: the forward-auth
# session and NocoDB's user session are both interactive. Open the single base, both tables and all 4 views; confirm the
# large table renders its rows; make a test edit, reload, confirm it persisted; revert it. Date columns now render with
# milliseconds in API/CSV output (expected, upstream-documented). Open the Apps page once (Interfaces became "classic
# apps"). Measured scope 2026-11-09: 1 base / 2 models / 4 views / 44,568 data rows.
# The hostname is NOT written here (public repo): read it from the live route,
#   kubectl get httproute -n databases nocodb -o jsonpath='{.spec.hostnames[0]}'
# An unauthenticated request to that host must still be redirected to Authentik (the forward-auth SecurityPolicy is untouched).
```

- CONTENTS ASSERTION: nocodb's metadata and user data must survive the 15 migrations unchanged. 4.4 measures this with
  `compare.py` over `counts.txt` and the three `ledger-*.txt`, captured live and compared to the 2h baseline in
  `~/backups/nocodb/pre-2026.10.1/pre`.
- CONTENTS ASSERTION: the running code is 2026.10.1. 4.2 reads `/api/v1/version` `currentVersion`, not an HTTP status.
- CONTROL: metric kube_pod_container_info, exactly one image value for pods `nocodb-*` in ns databases, equal to
  `docker.io/nocodb/nocodb:2026.10.1`. 0 series is a FAIL.
- CONTROL: metric flux_resource_info, the HelmRelease nocodb series present with `ready="True"`. 0 series is a FAIL.
- CONTROL: alertname FluxResourceNotReady must not be firing for name=nocodb (the scoped filter covers it; it has `for: 15m`,
  so the metric read above is the fast signal and the alert the slow one).

## 5) Rollback

**A tag revert alone is NOT a rollback.** After 15 knex migrations, 2026.09.1's code has no guarantee it can read the
migrated schema, upstream documents no downgrade, and two of the migrations declare their `down()` a no-op. **The rollback is
restoring the pre-dump taken in section 2g**: fence, purge, restore, verify, then revert git. The dump was proven restorable in
2i before the tag was pushed. Procedure carried from the retired `nocodb-2026.09.1` plan section 5 with counts and paths updated.

**Trigger:** any 4.1-4.5 FAIL that a re-run does not clear, or a 4.6 failure. A `compare.py` FAIL on `userrows`, `triple` or
`users` rolls back immediately. A FAIL that is only a held lock also rolls back (a crashed migration leaves partial DDL).
`compare.py` exit 2 (count differs from 15, everything else green) is an operator decision, not a trigger.

```bash
# Steps 0-3 as ONE Bash call (timeout 600000): 3b reads $PRE_ACL from 2a.
cd /Users/mu/code/cberg-home-nextgen
set -o pipefail
NCDB_NAME=$(sops -d kubernetes/apps/databases/nocodb/app/secret.sops.yaml \
  | python3 -c "import sys,yaml,urllib.parse as u; s=yaml.safe_load(sys.stdin)['stringData']['NC_DB']; print(u.parse_qs(u.urlsplit(s).query)['d'][0])")
[ -n "$NCDB_NAME" ] || { echo 'ABORT: DB name did not resolve, do NOT run a blind restore'; exit 1; }
B=~/backups/nocodb/pre-2026.10.1
DUMP="$B/nocodb-pre-2026.10.1.sql.gz"
[ -f "$DUMP" ] && gzip -t "$DUMP" && [ -s "$B/pre/counts.txt" ] \
  || { echo "ABORT: dump or baseline missing under $B"; exit 1; }

# 1) FENCE: suspend the HR (no helm upgrade can re-scale mid-restore), then scale to 0.
flux suspend helmrelease nocodb -n databases
[ "$(kubectl get hr -n databases nocodb -o jsonpath='{.spec.suspend}')" = "true" ] \
  || { echo 'ABORT: HelmRelease not suspended, do not purge'; exit 1; }
kubectl scale deploy -n databases nocodb --replicas=0
kubectl wait --for=delete pod -n databases -l app.kubernetes.io/name=nocodb --timeout=120s

ncq() { kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -tAc "$0"' "$1"; }

# 2a) record schema public owner + ACL. Measured live 2026-10-01 (previous bump): owner pg_database_owner,
#     acl {pg_database_owner=UC/pg_database_owner,=U/pg_database_owner,nocodb=UC/pg_database_owner}. Re-read, do not assume.
PRE_OWNER=$(ncq "select pg_get_userbyid(nspowner) from pg_namespace where nspname='public'")
PRE_ACL=$(ncq "select coalesce(nspacl::text,'') from pg_namespace where nspname='public'")
[ -n "$PRE_OWNER" ] && [ -n "$PRE_ACL" ] || { echo 'ABORT: could not read schema public owner/ACL'; exit 1; }
echo "pre-purge public owner=$PRE_OWNER acl=$PRE_ACL"

# 2b) purge DDL built FROM the measured ACL.
PURGE_SQL=$(PRE_ACL="$PRE_ACL" PRE_OWNER="$PRE_OWNER" python3 -c "
import os
names = {'U': 'USAGE', 'C': 'CREATE'}
sql = ['DROP SCHEMA public CASCADE;', 'CREATE SCHEMA public;',
       'ALTER SCHEMA public OWNER TO \"%s\";' % os.environ['PRE_OWNER']]
for e in os.environ['PRE_ACL'].strip('{}').split(','):
    if '=' not in e: continue
    grantee, rest = e.split('=', 1)
    privs = ', '.join(names[c] for c in rest.split('/')[0] if c in names)
    if not privs: continue
    tgt = 'PUBLIC' if grantee == '' else '\"%s\"' % grantee
    sql.append('GRANT %s ON SCHEMA public TO %s;' % (privs, tgt))
print('\n'.join(sql))
")
printf 'purge DDL:\n%s\n' "$PURGE_SQL"
printf '%s' "$PURGE_SQL" | grep '^DROP SCHEMA public CASCADE;' >/dev/null || { echo 'ABORT: purge DDL did not generate'; exit 1; }

# 2c) apply (one psql -c = one transaction). WHY purge at all: `pg_dump --clean` drops only objects IN the dump, so tables the
#     15 migrations CREATED would survive a plain replay and the exact-equality gate in 3 would (correctly) refuse, leaving
#     nocodb down. The user-data schema is NOT purged here: the dump's own --clean DROP/CREATE covers it (no migration
#     creates objects there), and 3 verifies its row counts exactly.
kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -v ON_ERROR_STOP=1 -c "$0"' \
  "$PURGE_SQL" || { echo 'ABORT: purge failed, nothing restored; escalate'; exit 1; }

# 2d) positive control: public must be empty before replay.
PURGED=$(ncq "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")
echo "public tables after purge: [$PURGED] (expect 0)"
[ "$PURGED" = "0" ] || { echo 'ABORT: schema not empty after purge, do NOT restore on top; escalate'; exit 1; }

# 2e) replay the dump. ON_ERROR_STOP=1 + pipefail are load-bearing.
gunzip -c "$DUMP" | kubectl exec -i -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -v ON_ERROR_STOP=1' \
  || { echo 'RESTORE FAILED, do NOT scale nocodb up; escalate to the operator'; exit 1; }

# 3) CONTENTS: the restore must reproduce the baseline EXACTLY (counts, all three ledgers name-for-name, locks 0/0/0, triple,
#    users, per-table user-data rows).
rm -rf "$B/restored"; OUTDIR="$B/restored"; . "$B/capture.sh"
python3 "$B/compare.py" restore "$B/pre" "$B/restored" \
  || { echo 'RESTORE INCOMPLETE, app stays at 0 replicas; escalate'; exit 1; }

# 3b) schema grants came back (grantee SET compare; grantor may differ legitimately).
POST_ACL=$(ncq "select coalesce(nspacl::text,'') from pg_namespace where nspname='public'")
PRE_ACL="$PRE_ACL" POST_ACL="$POST_ACL" python3 -c "
import os, sys
g = lambda a: {e.split('=')[0] for e in a.strip('{}').split(',') if '=' in e}
missing = g(os.environ['PRE_ACL']) - g(os.environ['POST_ACL'])
print('grantees pre', sorted(g(os.environ['PRE_ACL'])), 'post', sorted(g(os.environ['POST_ACL'])))
sys.exit(1 if missing else 0)
" || { echo 'RESTORE INCOMPLETE, re-grant USAGE, CREATE ON SCHEMA public to the missing role, re-run 3b'; exit 1; }
echo 'DB RESTORED TO PRE-2026.10.1 BASELINE'
```

```bash
# 4) SEPARATE Bash call. Only now move git back, confirm the old tag reached the LIVE HR spec, THEN resume (helm upgrade brings
#    the pod back at replicas:1 on 2026.09.1). NEVER `kubectl scale --replicas=1` by hand while the HR spec still says
#    2026.10.1: that boots the new code against the restored DB and re-runs the 15 migrations.
cd /Users/mu/code/cberg-home-nextgen
set -o pipefail
BUMP_SHA=<sha recorded at section 3 step 3>
F=kubernetes/apps/databases/nocodb/app/helmrelease.yaml
git show "$BUMP_SHA^:$F" > "$F" || { echo 'ABORT: could not restore file'; exit 1; }
grep -E '^[[:space:]]*tag:[[:space:]]*2026\.09\.1$' "$F" >/dev/null || { echo 'ABORT: restored file is not 2026.09.1'; exit 1; }
MSG=/tmp/msg-nocodb-rollback-$(date +%s).txt
printf 'revert(nocodb): back to 2026.09.1 after failed 2026.10.1 (plan nocodb-2026.10.1 section 5)\n' > "$MSG"
git commit --only "$F" -F "$MSG"
git log -1 --format=%s && git show --stat HEAD      # ONLY the nocodb helmrelease
git push
flux reconcile kustomization nocodb -n databases --with-source
TAG=$(kubectl get hr -n databases nocodb -o jsonpath='{.spec.values.controllers.nocodb.containers.app.image.tag}')
echo "live HR spec tag=[$TAG]"
[ "$TAG" = "2026.09.1" ] || { echo 'ABORT: HR spec not reverted yet, do NOT resume; re-run the reconcile'; exit 1; }
flux resume helmrelease nocodb -n databases
kubectl rollout status deploy/nocodb -n databases --timeout=5m
# Confirm: 4.1 with 2026.09.1 in place of 2026.10.1, 4.2 expecting 2026.09.1, 4.5 with EXPECT_IMG=docker.io/nocodb/nocodb:2026.09.1.
# Then the operator opens the base and confirms the data is back and an edit saves.
runbooks/update-marker.sh clear nocodb
```

The HR suspend/resume and scale-to-0 are the sanctioned direct-cluster actions that fence the restore; restoring the file in
step 4 brings Flux's desired state back. **Disaster fallback if the dump itself is bad** (it was proven restorable in 2i, so
this should not happen): the `postgresql-data-5g` Longhorn backup checked fresh in 2d. Restoring it rolls back **every**
database in the shared instance (measured 2026-11-09: `nocodb`, `oc8`, `pellets`, `postgres`, `sweep_history`,
`ninth_banner_feedback`), so it is a last resort coordinated per `docs/sops/backup.md`. Verified object names (live,
2026-11-09): `deployment/nocodb`, `deployment/postgresql`, `helmrelease/nocodb`, `pvc/nocodb-data`, `cronjob/daily-backup-all-volumes`
(ns storage), `secret/nocodb` keys `NC_AUTH_JWT_SECRET`, `NC_DB`.

## 6) Interference notes

- **`postgres-digest-refresh-2026-11` (sun-attended:2026-12-20) restarts `deployment/postgresql`, the shared server this
  migration writes into.** They must not share a night: a server restart during the migration boot leaves a held knex lock and
  partial DDL, and the restart's own reconnect gates (which list nocodb as a client) would be confounded by a pod that is
  mid-migration. Its frontmatter asks to keep "nocodb #426" out of its slot but has no plan_id to name; this plan now provides
  one, so the reciprocal `conflicts_with: nocodb-2026.10.1` belongs on that file (orchestrator follow-up; this planner writes
  only its own plan). `window-scheduler.py` honours one-sided declarations symmetrically.
- **Which apps use the shared server** (live 2026-11-09): databases `nocodb`, `oc8`, `pellets`, `sweep_history`,
  `ninth_banner_feedback`, `postgres`. **Nextcloud, paperless, affine, sure, superset, paperclip each have their own
  database server**, so their plans are not declared for server-sharing; the nextcloud/media/n8n/open-webui/etc. entries in
  `conflicts_with` are rollback-class stacking only (house rule 81fdd797).
- **Sweep overlap.** `sweep_history` lives in the same server. This plan does not restart it, but the migration adds load for
  a few seconds; the 04:00 sweep and 07:30 retro read it. An attended Saturday daytime window avoids the issue.
- **`helm-drift-detection`, `flux-reconciler-impersonation`, `flux-oci-chart-sources`** change how this HR (or every HR)
  reconciles; `redis-fleet-8.10.3` rolls redis in ns `databases` (4.5 blocks on any firing alert scoped there);
  `kube-prometheus-stack-93.3.0` touches the instrument 4.5 reads; `envoy-gateway-1.10.0`, `coredns-1.50.5` and `n8n-2.47.7` are platform/backup-restore neighbours. All declared (refs re-derived 2026-11-14 after the plan review).
- **App-template chart bumps.** If any plan bumps `version:` in `kubernetes/apps/databases/nocodb/app/helmrelease.yaml`
  (live chart is 5.3.0), step 2's edits do not touch that line, so either order works; section 5 step 4 restores the bump's
  parent and so keeps whatever chart version was live before.
- **Downtime:** about 1-3 min (Recreate plus the migration boot). The two HTTPRoutes, the SecurityPolicy, the Homepage tile
  and the Authentik outpost are untouched.
- **Window, recommended but not assigned (`window: null`, human-gated, `capability_change: true`):** attended slot required (4.6 is a
  human step; not `nightly`, Step 0's unattended lane cannot do 4.6). Re-derived 2026-11-14 from `maintenance-plan.py --open`: the
  EXECUTABLE set is helm-drift-detection (sat-attended:2026-11-28, declared conflict), longhorn-1.13.0 (sun 11-15), talos-linux-1.14.5
  (sun 11-22), redis-fleet-8.10.3 (sun 11-29), flux-oci-chart-sources (sun 12-13) and postgres-digest-refresh-2026-11 (sun 12-20).
  No Saturday is occupied except 11-28. Candidates: `sat-attended:2026-12-05` (6 days after redis, 8 days before the shared-server
  restart: a bad migration is rolled back and settled first) or `sat-attended:2026-12-12` (eve of flux-oci-chart-sources, a declared
  conflict, so less preferred). Avoid 11-21 (eve of the talos roll), 11-28 (helm-drift) and 12-19 (eve of the restart). The operator
  assigns the slot; this file does not.
- **One-way boundary:** after 4.6 passes and the window closes, the pre-dump is the only way back. Keep
  `~/backups/nocodb/pre-2026.10.1/` (dump, `pre/`, `capture.sh`, `compare.py`) at least until the next nightly Longhorn
  backup after sign-off (the nightly job `daily-backup-all-volumes` runs 23:00 UTC).
