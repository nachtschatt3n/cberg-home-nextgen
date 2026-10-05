---
plan_id: nocodb-2026.09.1
component: nocodb
pr: null                              # no Renovate PR. Surfaced by coverage.py's direct-bump lane
                                      # and HELD by G3 (structural signal: new knex migration files
                                      # in the 2026.09.0...2026.09.1 diff). NOT held by the
                                      # `*nocodb*` deny rule: that rule is `max: patch`, and a calver
                                      # 2026.09.0 -> 2026.09.1 hop reads as a patch, so the deny rule
                                      # alone would have let this through unattended. G3 is the only
                                      # reason it did not — see §1.
kind: image
current: "2026.09.0"                  # measured live 2026-10-01: deploy/nocodb image
                                      # nocodb/nocodb:2026.09.0, git pin tag: 2026.09.0, and the app's
                                      # own /api/v1/version reports currentVersion 2026.09.0
target: "2026.09.1"                   # Docker Hub tag_last_pushed 2026-09-29T14:32:05Z; GitHub
                                      # release published 2026-09-29T14:39:07Z. No 2026.10.x exists.
update_type: patch                    # calver patch by number; carries 12 knex schema migrations
                                      # (incl. data-moving ones), which is why it is not auto-safe
risk: medium
est_duration_min: 45                  # same gate chain as nocodb-2026.09.0 (executed green 2026-09-26
                                      # inside 45): pre-dump measured 8.2s wall today, gzip gates
                                      # ~1 min, HR reconcile + migration boot ~3 min, a 300 s
                                      # settle before §4.1 passes, Prometheus/contents gates ~2 min,
                                      # and the human acceptance pass (§4.6).
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - helmrelease/nocodb
    - deployment/nocodb
    - pvc/nocodb-data                  # near-empty; all real state is in PG
    - database/nocodb@postgresql       # nocodb's metadata + user-data schemas in the shared instance
  shared: [postgresql, monitoring]     # postgresql: the shared deployment/postgresql in ns databases
                                      # (not restarted; the migration runner writes into the nocodb
                                      # DB inside it). monitoring: §4.5 reads kube-prometheus-stack's
                                      # Prometheus — the window's instrument.
depends_on: []
conflicts_with:
  # [same HelmRelease / same helm-controller upgrade]
  - app-template-5.2.1                # bumps the chart on 78 HRs INCLUDING databases/nocodb
                                      # (same file kubernetes/apps/databases/nocodb/app/helmrelease.yaml,
                                      # same helm upgrade). Holds nightly:2026-10-02.
  - helm-drift-detection              # adds spec.driftDetection to every HR incl. nocodb's
  - flux-reconciler-impersonation     # exclusive; rewires the identity every HR reconcile runs under
  - flux-oci-chart-sources            # rewrites HR chart sources across ns databases; same-night
                                      # reconcile churn in ns databases confounds §4.5's scoped gate
  # [same namespace: §4.5's alert gate is scoped to ns databases]
  # - mariadb-chart-27.3.0 (RESOLVED 2026-10-04: executed + retired 418faa1e (now:2026-10-03); dead ref removed per the dead-ref convention)
  - mariadb-28.1.1  # ADDED 2026-10-04: successor plan (same databases/mariadb HR + mariadb-0 roll); reciprocal -- it already lists this plan
    # rolls databases/mariadb-0 (nightly:2026-10-05)
  - redis-fleet-8.10.2                # rolls redis workloads incl. ns databases
  # [rollback-class stacking (house rule 81fdd797: every backup-restore pair
  #     is declared; two in one slot leave no rollback capacity for either)]
  - jellyfin-12.1
  - n8n-2.39.8
  - paperless-db-13.0.2
  - nextcloud-fleet-35.0.1
  - penpot-chart-1.10.0
  - media-naming-p3
  - bitnamilegacy-exit-nextcloud-db
  # - talconfig-multidoc-migration (RESOLVED 2026-10-05: executed green now:2026-10-04 in a7965251 + retired 10bee773; dead ref removed per the dead-ref convention, sweep 481b9c1f / F-c688c50f)
exclusive: false
security_ref: F-15d4b6c4              # open security record on the running 2026.09.0 image, currently
                                      # accepted under AR-029 because 2026.09.0 WAS the newest tag.
                                      # 2026.09.1 now exists, so that acceptance premise is gone and
                                      # this bump is its remedy. Detail stays in sweep_findings only.
capability_change: true               # 2026.09.1 adds user-visible surface: account-wide MCP
                                      # connections (MCP server 149 -> 199 tools), Table Tools panel,
                                      # invite links, YouTrack sync, base settings modal, and v3 API
                                      # field changes. Not cosmetic.
rollback_class: backup-restore        # 12 knex migrations run on boot (one drops a column after
                                      # moving its data; one ALTERs a column type). Upstream
                                      # documents no downgrade. A tag revert is not a rollback; §5 is
                                      # dump-restore.
backup_gate: "pg_dump of the nocodb database (name resolved from the live NC_DB secret's d= param)
  taken from deploy/postgresql BEFORE the tag edit is pushed, under set -o pipefail, gated on:
  gzip validity, a 10MB byte floor (measured 13,327,948 B on 2026-10-01), COPY-block count equal to
  the live BASE TABLE count across all non-system schemas (157 = 155 public + 2 user-data), the six
  named metadata tables present, and the pg_dump completion marker. A baseline (counts, three knex
  ledgers, lock state, per-table user-data row counts) is written to
  ~/backups/nocodb/pre-2026.09.1/ for the §4.4 and §5 contents comparisons."
finding_refs: [F-15d4b6c4]            # `finding list --grep nocodb` 2026-10-01 returned two rows:
                                      # F-15d4b6c4 (this image's security record) and F-8d9677a0
                                      # (chart 5.1.0 -> 5.2.1, owned by app-template-5.2.1, NOT this
                                      # plan). No version-lane row for 2026.09.1 exists yet (the last
                                      # sweep, 2026-09-29 02:18Z, predates the tag); add it here when
                                      # the next sweep emits one.
review: ready-for-go@2026-10-01   # plan-reviewer-agent, sweep b23be87b
status: awaiting-go   # 2026-10-02 nightly: go_no_go ingested (HUMAN-GATED: capability_change) — was: vetted
window: "sun-attended:2026-11-08"   # proposed 2026-10-02 by maintenance-window-agent: first attended slot with no declared conflict (sat 10-03 = 90/90m TIGHT + monitoring overlap with uptime-kuma; 10-04..11-07 each hold a conflicts_with partner or DNS/monitoring churn). Operator may pull it earlier.
premises:
  - id: live-image-is-still-2026.09.0
    why: >-
      `current:` is 2026.09.0 and the §4.4 expected-migration list was derived
      against the 2026.09.0 knex ledger (100 v0 rows). Any other live tag means
      the baseline and the expected set are stale; re-derive before executing.
    run: kubectl get deploy -n databases nocodb -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: nocodb/nocodb:2026.09.0
  - id: db-secret-still-wired-to-nocodb-env
    why: >-
      §2f/§4.4/§5 resolve the DB name from secret `nocodb` (NC_DB). If the
      envFrom secretRef moved, those commands would target the wrong object.
    run: kubectl get deploy -n databases nocodb -o jsonpath='{.spec.template.spec.containers[0].envFrom[0].secretRef.name}'
    expect_exact: nocodb
  - id: shared-postgresql-instance-still-present
    why: >-
      Dump, baseline and restore all `kubectl exec` into deploy/postgresql in
      ns databases. A renamed/replaced instance would silently retarget them.
    run: kubectl get deploy -n databases postgresql -o jsonpath='{.metadata.name}'
    expect_exact: postgresql
  - id: deployment-strategy-recreate
    why: >-
      Single replica on an RWO Longhorn PVC. Recreate guarantees the 2026.09.0
      pod is gone before 2026.09.1 boots and runs migrations, so two versions
      never run against the DB at once (and no Multi-Attach).
    run: kubectl get deploy -n databases nocodb -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: helmrelease-ready
    why: "Do not stack a one-way migration on an already-failing release."
    run: kubectl get helmrelease -n databases nocodb -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-01"
---

# nocodb 2026.09.0 → 2026.09.1

## 1) Summary & why held

A month-internal calver patch, image only (`nocodb/nocodb`, chart stays on
app-template 5.1.0). It ships after `nocodb-2026.09.0`, which ran green on
2026-09-26 and was retired in `0308b7e7`. This plan uses that plan's shape:
mandatory pre-dump, contents gates, and a purge-then-restore rollback. Four
things were re-measured for this target.

**Why it was held (G3, and the hold is correct, not a false positive).** The
`*nocodb*` deny rule in `runbooks/auto-update-policy.yaml` is `max: patch`. A
`2026.09.0 → 2026.09.1` hop reads as a patch, so **the deny rule alone would
have let it through unattended with no pre-dump**. That would be exactly the
failure the rule's own comment describes ("An unattended Step-0 apply would
perform exactly that with no dump taken"). G3's structural check stopped it,
and the diff justifies the hold:

- **New migration files, 2026.09.0 → 2026.09.1** (GitHub tag trees, compared
  2026-10-01): 11 new files in `packages/nocodb/src/meta/migrations/v0/` and 3
  in `.../chat-messages/` (`nc_005_agents`, `nc_006_agent_app`,
  `nc_007_agent_messages`).
- **The diff that matters is against the LIVE ledger, not the git tree.**
  2026.09.1's `XcMigrationSourcev0.ts` registers 112 migrations. The live
  `xc_knex_migrationsv0` holds 100 rows. **12 are pending:**
  `nc_202609021200_apps`, `nc_202609021201_environments`,
  `nc_202609021202_marketplace`, `nc_202609091200_mcp_token_permissions`,
  `nc_202609161200_chat_sessions_agents`, `nc_202609171500_invite_links`,
  `nc_202609181111_oauth_grant_permissions`, `nc_202609191200_app_factory`,
  `nc_202609211109_code_projects`, `nc_202609250735_oauth_scope_text`,
  `nc_202609251200_vaults`, and
  `nc_202609260900_interface_detail_default_config`.
- **The GitHub tag tree is not the image.** The 2026.09.0 tag tree contains
  zero `nc_202609*` files, yet the 2026.09.0 image applied
  `nc_202609021200_admin_suspend` and `nc_202609031200_agents` on 2026-09-26
  05:58Z. Also, three of the 12 names above are imported by 2026.09.1's
  migration source but are absent from the public tag tree (HTTP 404). So the
  expected-set check in §4.4 is **advisory**. The hard gates are no-shrink,
  no-lost-ledger-entry, no held knex lock, and user data unchanged.
- **The chat-messages source has no ledger table here.** The live DB has only
  `xc_knex_migrations`, `xc_knex_migrationsv0` and `xc_knex_migrationsv2`
  (plus their `_lock` tables), so the three chat-messages files were never run
  against this DB. If 2026.09.1 creates a new ledger table, §4.4 still passes,
  because its gates cover the three existing ledgers.
- **What the 12 do (the `up()` bodies were read)** is mostly additive:
  `createTable` for apps, environments, marketplace, vaults, invite links,
  factory repos and code projects. Three are not additive:
  - `nc_202609021201_environments` copies `nc_sandboxes_v2` and
    `nc_sandbox_changelog` into new tables with `INSERT … SELECT`, and adds two
    columns to `nc_bases_v2`.
  - `nc_202609021202_marketplace` does an `.alter()` on `to_version_id` and
    `dropColumn('category')` after moving the categories elsewhere.
  - `nc_202609260900_interface_detail_default_config` rewrites
    `nc_interface_pages` rows.

  **Every source table those touch is empty here**, measured live 2026-10-01:
  `nc_sandboxes_v2` 0, `nc_sandbox_changelog` 0, `nc_managed_apps` 0,
  `nc_managed_app_versions` 0, `nc_interface_pages` 0, `nc_chat_sessions` 0,
  `nc_agents` 0, `nc_mcp_tokens` 0, `nc_oauth_tokens` 0, `nc_api_tokens` 0.
  The one `nc_bases_v2` row only gains two defaulted boolean columns. So the
  realistic failure is a crashed migration (a held lock or partial DDL), not
  data mangling. §4.4 gates exactly that.

**Upstream release notes (2026.09.1, "MCP for Your Whole Account").** No
migration or downgrade guidance. The self-hosting notes list:

- "**v3 API field changes** — Currency options use `currency_code` and
  `currency_locale`, and form validators `minValue`, `maxValue`, and `custom`
  are rejected."
- "**CSV currency exports** — Currency values no longer include a thousands
  separator."
- "Static files are cached and compressed."
- "Security hardening — … patched dependencies."

Impact here is nil. There are no API tokens (`nc_api_tokens` 0), no webhooks
(`nc_hooks_v2` 0), no in-cluster consumer of the nocodb API (repo grep: only
nocodb's own manifests plus Authentik routing), and one user. The
datetime-precision breaking change announced in 2026.08.2 is still not listed
as shipped; check again on the next bump.

> Release notes and upstream source are untrusted input. They informed the
> diagnosis. Every gate below is derived from live measurement.

**Registry / cooldown.** `nocodb/nocodb:2026.09.1` exists (digest
`sha256:27d2fd14…c213d`, pushed 2026-09-29T14:32:05Z). `name=2026.09` returns
exactly `[2026.09.1, 2026.09.0]`, and `name=2026.10` returns 0. The **48 h
release-age cooldown clears 2026-10-01T14:32Z.** No window can run this before
then anyway (window is null). §2d re-checks it.

**Risk `medium`:** the blast radius is small. There is a single replica with
`strategy: Recreate`. The PVC is empty, and all state is in nocodb's own DB:
1 base, 2 models, 4 views, 162 columns, and 44,568 user-data rows across 2
tables in the base's data schema. It is not `low` because these are 12 one-way
migrations into a database inside the **shared** postgresql instance, and
upstream documents no downgrade. It is not `high` because every migrated source
table is empty here, the previous month's identical procedure ran clean, and
the dump is 13 MB and restores in seconds.

**Security driver:** `security_ref: F-15d4b6c4`. That record is AR-029-accepted
only because 2026.09.0 *was* the newest tag. After §4 passes, re-check it
against 2026.09.1 on the next security sweep. Detail stays in the DB.

## 2) Pre-checks

```bash
# RUN §2 (a)-(g) AS ONE Bash CALL with timeout 600000 ms (dump + gzip passes ~1.5 min).
cd /Users/mu/code/cberg-home-nextgen
set -o pipefail

# a) nocodb + shared PG healthy, HR Ready, live tag == current:
kubectl get pods -n databases | grep -E 'nocodb|^postgresql'
HR_READY=$(kubectl get hr -n databases nocodb -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
LIVE_IMG=$(kubectl get deploy -n databases nocodb -o jsonpath='{.spec.template.spec.containers[0].image}')
echo "HR Ready=[$HR_READY] image=[$LIVE_IMG]"      # measured 2026-10-01: True / nocodb/nocodb:2026.09.0
[ "$HR_READY" = "True" ] || { echo 'FAIL: HR nocodb not Ready'; exit 1; }
[ "$LIVE_IMG" = "nocodb/nocodb:2026.09.0" ] || { echo 'FAIL: live image != current: — plan is stale, re-derive'; exit 1; }

# b) target still resolves; c) nothing newer published (a newer tag => re-plan, do not run)
curl -s "https://hub.docker.com/v2/repositories/nocodb/nocodb/tags/2026.09.1" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['name'], d['tag_last_pushed']); sys.exit(0 if d['name']=='2026.09.1' else 1)" \
  || { echo 'FAIL: target tag missing'; exit 1; }
N10=$(curl -s "https://hub.docker.com/v2/repositories/nocodb/nocodb/tags/?page_size=10&name=2026.10" | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])")
echo "2026.10.x tags: [$N10]"                       # measured 0
[ "$N10" = "0" ] || echo 'ADVISORY: a 2026.10.x tag exists — consider retargeting this plan (README: refresh in place)'

# d) release-age cooldown (>= 48 h; clears 2026-10-01T14:32Z)
python3 -c "
from datetime import datetime, timezone; import sys
age=(datetime.now(timezone.utc)-datetime.fromisoformat('2026-09-29T14:32:05+00:00')).total_seconds()/3600
print(f'age_hours={age:.1f}'); sys.exit(0 if age>=48 else 1)" || { echo 'FAIL: cooldown not cleared'; exit 1; }

# e) Longhorn backups fresh (<24h) — the §5 disaster fallback. Same gate as nocodb-2026.09.0 §2e.
#    Measured 2026-10-01: nocodb-data 2026-09-30T03:08:46Z, postgresql-data-5g 2026-09-30T03:04:26Z.
kubectl get volume -n storage nocodb-data postgresql-data-5g \
  -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt --no-headers > /tmp/nocodb-lastbackup.txt
python3 - /tmp/nocodb-lastbackup.txt <<'PY' || { echo 'FAIL: Longhorn backup freshness gate'; exit 1; }
import re, sys
from datetime import datetime, timezone
seen = {r[0]: r[1] for r in (l.split() for l in open(sys.argv[1]) if l.strip()) if len(r) == 2}
bad = []
for vol in ("nocodb-data", "postgresql-data-5g"):
    ts = seen.get(vol)
    if not ts or not re.match(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$', ts):
        bad.append(f"{vol}: no usable lastBackupAt ({ts!r})"); continue
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace('Z', '+00:00'))).total_seconds() / 3600
    print(f"{vol}: {ts} age={age:.1f}h")
    if age > 24: bad.append(f"{vol}: {age:.1f}h old (>24h)")
if bad: print("FAIL: " + "; ".join(bad)); sys.exit(1)
print("BACKUP FRESHNESS GATE PASSED")
PY
# FAILS ON: a stale stamp (>24h), `<none>` (no completed backup), or a missing row (seen.get -> None).
# Carried verbatim from nocodb-2026.09.0 §2e, which dry-tested all three controls on 2026-09-21.

# f) MANDATORY pre-dump — the backup_gate.
NCDB_NAME=$(sops -d /Users/mu/code/cberg-home-nextgen/kubernetes/apps/databases/nocodb/app/secret.sops.yaml \
  | python3 -c "import sys,yaml,urllib.parse as u; s=yaml.safe_load(sys.stdin)['stringData']['NC_DB']; print(u.parse_qs(u.urlsplit(s).query)['d'][0])")
[ -n "$NCDB_NAME" ] || { echo 'FAIL: DB name did not resolve'; exit 1; }
echo "DB name: $NCDB_NAME"                          # measured 2026-10-01: nocodb
ncq() { kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -tAc "$0"' "$1"; }

B=~/backups/nocodb/pre-2026.09.1
mkdir -p "$B" && chmod 700 "$B"
OUT="$B/nocodb-pre-2026.09.1.sql.gz"
kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$NCDB" --clean --if-exists' \
  | gzip > "$OUT" || { echo 'FAIL: pg_dump pipeline non-zero'; exit 1; }
chmod 600 "$OUT"
gzip -t "$OUT" || { echo 'FAIL: gzip invalid'; exit 1; }                       # GATE 1 (shape only)
SZ=$(stat -f%z "$OUT")                                                           # BSD stat (macOS)
[ "${SZ:-0}" -ge 10000000 ] || { echo "FAIL: dump too small: ${SZ:-unset} B"; exit 1; }   # GATE 2
# GATE 3 — one COPY block per live BASE TABLE in EVERY non-system schema. The base's user
# data lives in a second, generated schema (not `public`), so a public-only count would
# not notice a dump that lost the user data. Measured 2026-10-01: live 157 (155 public + 2),
# COPY blocks 157.
LIVE_TABLES=$(ncq "select count(*) from information_schema.tables where table_schema not in ('pg_catalog','information_schema') and table_type='BASE TABLE'")
[ -n "$LIVE_TABLES" ] || { echo 'FAIL: live table count did not read'; exit 1; }
DUMP_COPIES=$(gunzip -c "$OUT" | grep -c '^COPY ')
echo "live BASE TABLEs=$LIVE_TABLES  COPY blocks=$DUMP_COPIES"
[ "$DUMP_COPIES" -eq "$LIVE_TABLES" ] || { echo "FAIL: $DUMP_COPIES COPY blocks for $LIVE_TABLES tables"; exit 1; }
# GATE 4 — named metadata tables + the ledger the 12 migrations write to. grep >/dev/null,
# NOT grep -q: -q exits early, gunzip takes SIGPIPE and under pipefail a PRESENT table reads
# as missing (false FAIL seen 2026-09-26). Verified 2026-10-01: each matches exactly once.
for t in nc_bases_v2 nc_models_v2 nc_views_v2 nc_columns_v2 xc_knex_migrationsv2 xc_knex_migrationsv0; do
  gunzip -c "$OUT" | grep "^COPY public\.$t " >/dev/null || { echo "FAIL: $t missing from dump"; exit 1; }
done
# GATE 5 — completion marker (truncated dumps lack it). Verified present 2026-10-01.
gunzip -c "$OUT" | tail -5 | grep 'PostgreSQL database dump complete' >/dev/null \
  || { echo 'FAIL: no completion marker — dump truncated'; exit 1; }
echo "BACKUP GATE PASSED: $OUT ($SZ B, $DUMP_COPIES tables)"

# g) BASELINE — written to files, read back by §4.4 and §5. Also writes the two helper
#    scripts so every later block is self-contained (no shell variables carried over).
cat > "$B/capture.sh" <<'SH'
# sourced with OUTDIR set and NCDB_NAME + ncq() defined in the caller
mkdir -p "$OUTDIR"
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
  echo "userrows=$(ncq "select string_agg(n||'='||c, ' ' order by n) from (select table_schema||'.'||table_name n, (xpath('/row/c/text()', query_to_xml(format('select count(*) c from %I.%I', table_schema, table_name), false, true, '')))[1]::text c from information_schema.tables where table_schema not in ('public','pg_catalog','information_schema') and table_type='BASE TABLE') s")"
} > "$OUTDIR/counts.txt"
cat "$OUTDIR/counts.txt"
SH
cat > "$B/compare.py" <<'PY'
import sys, re
mode, pre_dir, post_dir = sys.argv[1], sys.argv[2], sys.argv[3]   # mode: upgrade | restore
def kv(d):
    out = {}
    for line in open(f'{d}/counts.txt'):
        k, _, v = line.rstrip('\n').partition('=')
        out[k] = v
    return out
def ledger(d, v):
    return [l.strip() for l in open(f'{d}/ledger-{v}.txt') if l.strip()]
pre, post = kv(pre_dir), kv(post_dir)
bad = []
need = ['tables','knex_base','knex_v0','knex_v2','locks','triple','cols','userrows']
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
if post['locks'] != '0/0/0': bad.append(f"knex lock held after boot: {post['locks']} (a migration crashed mid-run)")
if post['triple'] != pre['triple']: bad.append(f"base/model/view counts changed {pre['triple']} -> {post['triple']}")
if post['userrows'] != pre['userrows']: bad.append(f"USER DATA row counts changed: {pre['userrows']} -> {post['userrows']}")
for v in ('v0', 'v2'):
    a, b = ledger(pre_dir, v), ledger(post_dir, v)
    if not a: bad.append(f'pre ledger-{v} empty'); continue
    lost = sorted(set(a) - set(b))
    if lost: bad.append(f'ledger {v} LOST {len(lost)} entries (rolled back): {lost[:5]}')
if mode == 'upgrade':
    for k in ('tables', 'knex_base', 'knex_v0', 'knex_v2', 'cols'):
        if int(post[k]) < int(pre[k]): bad.append(f'{k} shrank {pre[k]} -> {post[k]}')
    expect = ['nc_202609021200_apps','nc_202609021201_environments','nc_202609021202_marketplace',
              'nc_202609091200_mcp_token_permissions','nc_202609161200_chat_sessions_agents',
              'nc_202609171500_invite_links','nc_202609181111_oauth_grant_permissions',
              'nc_202609191200_app_factory','nc_202609211109_code_projects',
              'nc_202609250735_oauth_scope_text','nc_202609251200_vaults',
              'nc_202609260900_interface_detail_default_config']
    got = set(ledger(post_dir, 'v0'))
    missing = [m for m in expect if m not in got]
    print(f'expected-new v0 migrations applied: {len(expect)-len(missing)}/{len(expect)}'
          + (f'  ADVISORY (image may differ from the GitHub tag tree): not applied {missing}' if missing else ''))
else:  # restore: must reproduce the baseline EXACTLY
    for k in ('tables', 'knex_base', 'knex_v0', 'knex_v2', 'cols'):
        if post[k] != pre[k]: bad.append(f'{k} {pre[k]} -> {post[k]} (restore must be exact)')
    for v in ('v0', 'v2'):
        if ledger(pre_dir, v) != ledger(post_dir, v): bad.append(f'ledger {v} differs from baseline')
if bad: print('FAIL: ' + ' | '.join(bad)); sys.exit(1)
print(f'CONTENTS GATE PASSED ({mode})')
PY
OUTDIR="$B/pre"; . "$B/capture.sh"
# Measured live 2026-10-01 (expect this shape; userrows names elided here, 2 tables, 44568 rows):
#   tables=155 knex_base=12 knex_v0=100 knex_v2=86 locks=0/0/0 triple=1/2/4 cols=162
# Self-check: compare the baseline against ITSELF — must PASS; also rejects any empty field.
python3 "$B/compare.py" upgrade "$B/pre" "$B/pre" || { echo 'FAIL: baseline incomplete — do not proceed'; exit 1; }
# NOTE: ~/backups/nocodb/pre-counts.txt is the STALE 2026.09.0 baseline (tables=146). This plan
# never reads it; everything lives under $B.

# h) no in-flight Flux trouble in ns databases (advisory outside it)
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -n databases | awk 'NR==1 || $4 != "True"'

# i) PRE-CHANGE run of the §4.5 Prometheus block with EXPECT_IMG=docker.io/nocodb/nocodb:2026.09.0.
#    It must print PROMETHEUS GATE PASSED. A scoped alert that predates the change => STOP.
```

## 3) Steps

1. **Marker** (attended-tier update per `application-update.md`):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   runbooks/update-marker.sh add nocodb databases 4 "2026.09.0 -> 2026.09.1 (12 knex migrations)"
   ```

2. **Disable HR upgrade remediation and bump the tag, in one edit.** A Flux
   remediation rollback while knex is writing schema would flip the image back
   halfway through the migration. Dry-tested on a scratch copy with BSD sed
   and python on 2026-10-01. The `retries: 3` under `install:` is deliberately
   left alone; the python anchor matches only the `upgrade:` block (asserted
   `count == 1`).
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   F=kubernetes/apps/databases/nocodb/app/helmrelease.yaml
   sed -i '' 's/^\([[:space:]]*tag:[[:space:]]*\)2026\.09\.0$/\12026.09.1/' "$F"
   python3 - "$F" <<'PY'
   import sys
   p = sys.argv[1]; s = open(p).read()
   old = "  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 3\n"
   new = "  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 0\n      remediateLastFailure: false\n"
   assert s.count(old) == 1, 'upgrade block not found exactly once — file moved, STOP'
   open(p, 'w').write(s.replace(old, new)); print('upgrade remediation disabled')
   PY
   git diff --stat -- "$F"; git diff -- "$F"
   ```
   The expected diff, exactly as produced on the scratch copy:
   ```
   24c24,25
   <       retries: 3
   ---
   >       retries: 0
   >       remediateLastFailure: false
   36c37
   <               tag: 2026.09.0
   ---
   >               tag: 2026.09.1
   ```
   If `app-template-5.2.1` has landed first (it holds `nightly:2026-10-02`), a
   `version: 5.2.1` line will also show as unchanged context. That is fine,
   because the edits above do not touch it.

3. **Commit + push.** The worktree is shared, so use `--only` and check the
   subject:
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   MSG=/tmp/msg-nocodb-2026.09.1-$(date +%s).txt
   printf 'feat(nocodb): 2026.09.0 -> 2026.09.1 (12 knex migrations; plan nocodb-2026.09.1)\n' > "$MSG"
   git commit --only kubernetes/apps/databases/nocodb/app/helmrelease.yaml -F "$MSG"
   git log -1 --format=%s     # MUST be the subject above; amend before push if not
   git show --stat HEAD       # ONLY the nocodb helmrelease
   git push
   git rev-parse HEAD         # RECORD this as BUMP_SHA for §5 step 4
   ```

4. **Watch the migration boot.** Use bounded commands only. Never put
   `kubectl logs -f` in the executed sequence.
   ```bash
   flux reconcile kustomization nocodb -n databases --with-source   # only if the webhook lags
   kubectl rollout status deploy/nocodb -n databases --timeout=5m
   kubectl logs -n databases deploy/nocodb --since=10m --tail=200
   ```
   `rollout status` can report on the OLD generation if it races the HR
   upgrade. §4.1 re-reads the live pod's image, and that read is the binding
   check.

5. **After §4 passes:** restore HR remediation, commit, and clear the marker.
   This was dry-tested as the inverse of step 2 and restores the original
   bytes.
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   F=kubernetes/apps/databases/nocodb/app/helmrelease.yaml
   python3 - "$F" <<'PY'
   import sys
   p = sys.argv[1]; s = open(p).read()
   new = "  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 3\n"
   old = "  upgrade:\n    cleanupOnFail: true\n    remediation:\n      retries: 0\n      remediateLastFailure: false\n"
   assert s.count(old) == 1, 'temp remediation block not found — STOP'
   open(p, 'w').write(s.replace(old, new)); print('remediation restored')
   PY
   MSG=/tmp/msg-nocodb-remed-$(date +%s).txt
   printf 'chore(nocodb): restore HR remediation retries after 2026.09.1 bump\n' > "$MSG"
   git commit --only "$F" -F "$MSG"
   git log -1 --format=%s && git show --stat HEAD
   git push
   runbooks/update-marker.sh clear nocodb
   ```

## 4) Verification

Run each sub-block as its own Bash call. Every block re-derives its own inputs
from files and the cluster. Do not accept a gate that printed nothing.

```bash
# --- 4.1 HR Ready, pod on the NEW image, stable (re-run, never sleep) -------
cd /Users/mu/code/cberg-home-nextgen
set -o pipefail
HR_READY=$(kubectl get hr -n databases nocodb -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
echo "HR Ready=[$HR_READY]"
[ "$HR_READY" = "True" ] || { echo 'FAIL: HelmRelease nocodb not Ready'; exit 1; }
kubectl get pods -n databases -l app.kubernetes.io/name=nocodb -o json > /tmp/nocodb-pod.json \
  || { echo 'FAIL: could not read nocodb pod'; exit 1; }
python3 - /tmp/nocodb-pod.json <<'PY' || { echo 'FAIL: §4.1 pod gate'; exit 1; }
import json, sys
from datetime import datetime, timezone
items = json.load(open(sys.argv[1]))['items']
if len(items) != 1: print(f'expected 1 nocodb pod, got {len(items)}'); sys.exit(1)
p = items[0]; img = p['spec']['containers'][0]['image']; cs = p['status']['containerStatuses'][0]
st = (cs.get('state') or {}).get('running', {}).get('startedAt')
if not st: print(f'container not running: {cs.get("state")}'); sys.exit(1)
age = (datetime.now(timezone.utc) - datetime.fromisoformat(st.replace('Z', '+00:00'))).total_seconds()
print(f'image={img} restartCount={cs["restartCount"]} running_for={age:.0f}s')
if img != 'nocodb/nocodb:2026.09.1': print(f'wrong image {img}'); sys.exit(1)
if cs['restartCount'] != 0: print('restartCount != 0 (crash-loop)'); sys.exit(1)
if age < 300: print(f'NOT YET SETTLED: re-run in {int(300-age)+5}s'); sys.exit(1)
print('4.1 PASSED')
PY
# FAILS ON: HR not Ready; image still 2026.09.0 (today's live state prints exactly that);
# restartCount>0; not running; <300 s since start. Carried from nocodb-2026.09.0 §4.1,
# dry-tested there against the then-live pod (printed `wrong image`, rc=1).

# --- 4.2 VERSION CONTENTS GATE: the running code's self-reported version ----
set -o pipefail
kubectl port-forward -n databases svc/nocodb 19392:8080 >/dev/null 2>&1 & PF=$!
trap 'kill $PF 2>/dev/null' EXIT
curl -s -o /dev/null --retry 15 --retry-connrefused --retry-delay 1 --max-time 30 http://localhost:19392/api/v1/health
VER=$(curl -s --max-time 10 http://localhost:19392/api/v1/version \
      | python3 -c "import sys,json; print(json.load(sys.stdin).get('currentVersion',''))" 2>/dev/null)
echo "currentVersion=[$VER]"
[ "$VER" = "2026.09.1" ] || { echo "FAIL: app reports [$VER], expected 2026.09.1"; exit 1; }
curl -s --max-time 10 http://localhost:19392/api/v1/health | grep '"message":"OK"' >/dev/null \
  || { echo 'FAIL: /api/v1/health body not message OK'; exit 1; }
kill $PF 2>/dev/null; trap - EXIT
# Measured 2026-10-01 on the live pod: {"currentVersion":"2026.09.0","releaseVersion":"2026.09.1"}
# and health {"message":"OK",...} — so today this gate FAILS (VER=2026.09.0), as it must.
# An unreachable app gives VER="" which never equals 2026.09.1.

# --- 4.3 BOOT LOG GATE --------------------------------------------------------
kubectl logs -n databases deploy/nocodb --since=20m > /tmp/nocodb-boot.log 2>&1
[ -s /tmp/nocodb-boot.log ] || { echo 'FAIL: empty boot log — no restart happened, gate measured nothing'; exit 1; }
echo "boot log lines: $(wc -l < /tmp/nocodb-boot.log)"
grep -inE '"level":(50|60)|unhandled|econnrefused|cannot find module|migration failed|fatal' /tmp/nocodb-boot.log
ERRS=$(grep -cE '"level":(50|60)' /tmp/nocodb-boot.log)
FATALS=$(grep -icE 'unhandled|econnrefused|cannot find module|migration failed|fatal' /tmp/nocodb-boot.log)
echo "pino error/fatal records: $ERRS   plain-text fatal markers: $FATALS"
[ "$ERRS" -eq 0 ]   || { echo "FAIL: $ERRS pino error/fatal records"; exit 1; }
[ "$FATALS" -eq 0 ] || { echo "FAIL: $FATALS fatal markers"; exit 1; }
echo "advisory (non-gating) substring hits: $(grep -icE 'error|failed' /tmp/nocodb-boot.log)"
grep 'App started successfully' /tmp/nocodb-boot.log >/dev/null \
  || { echo 'FAIL: no "App started successfully" — boot did not complete'; exit 1; }
# Re-measured 2026-10-01 on the live 2026.09.0 pod: full log 29 lines, exactly 1
# "App started successfully", 0 records at pino level 40/50/60, 0 fatal markers — so the
# markers this gate keys on are still emitted by the current image. Positive/false-stop
# controls for the pattern were dry-tested in nocodb-2026.09.0 §4.3 (2026-09-21).

# --- 4.4 MIGRATION + DATA CONTENTS GATE (the knex ledgers and user rows) ------
cd /Users/mu/code/cberg-home-nextgen
set -o pipefail
NCDB_NAME=$(sops -d /Users/mu/code/cberg-home-nextgen/kubernetes/apps/databases/nocodb/app/secret.sops.yaml \
  | python3 -c "import sys,yaml,urllib.parse as u; s=yaml.safe_load(sys.stdin)['stringData']['NC_DB']; print(u.parse_qs(u.urlsplit(s).query)['d'][0])")
[ -n "$NCDB_NAME" ] || { echo 'FAIL: DB name did not resolve'; exit 1; }
ncq() { kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -tAc "$0"' "$1"; }
B=~/backups/nocodb/pre-2026.09.1
[ -s "$B/pre/counts.txt" ] || { echo 'FAIL: no baseline at $B/pre — §2g did not run'; exit 1; }
rm -rf "$B/post"; OUTDIR="$B/post"; . "$B/capture.sh"
python3 "$B/compare.py" upgrade "$B/pre" "$B/post" || { echo 'FAIL: §4.4 contents gate — see §5'; exit 1; }
# HARD FAILS ON: any knex lock still held (crashed migration); any v0/v2 ledger entry from
# the baseline missing (rolled back); tables/cols/ledger counts shrinking; base/model/view
# triple changing; ANY change to the per-table user-data row counts; any empty read.
# ADVISORY ONLY: which of the 12 expected migrations appear (the image is not the git tree).
# DRY-TESTED 2026-10-01 against the live DB (baseline vs itself -> PASS, rc 0) plus five
# negative controls on a tampered copy, each rc=1: lock 0/1/0 -> "knex lock held";
# a user row count 44568->44000 -> "USER DATA row counts changed"; one v0 ledger name
# deleted -> "ledger v0 LOST 1 entries"; cols emptied -> "post cols is EMPTY"; and in
# restore mode a grown ledger -> "restore must be exact".
# Expected on success: knex_v0 100 -> 112, tables 155 -> >155, triple 1/2/4 unchanged,
# userrows unchanged, locks 0/0/0.

# --- 4.5 PROMETHEUS GATE: image series, Flux readiness, scoped alerts ---------
set -o pipefail
EXPECT_IMG="${EXPECT_IMG:-docker.io/nocodb/nocodb:2026.09.1}"
SCOPE_NS="${SCOPE_NS:-databases}"
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19391:9090 >/dev/null 2>&1 & PF=$!
trap 'kill $PF 2>/dev/null' EXIT
curl -s -o /dev/null --retry 15 --retry-connrefused --retry-delay 1 --max-time 30 http://localhost:19391/-/ready
D=$(mktemp -d)
curl -s --max-time 10 http://localhost:19391/api/v1/alerts > "$D/alerts.json"
curl -s --max-time 10 --get --data-urlencode 'query=kube_pod_container_info{namespace="databases",pod=~"nocodb-.*"}' http://localhost:19391/api/v1/query > "$D/info.json"
curl -s --max-time 10 --get --data-urlencode 'query=flux_resource_info{kind="HelmRelease",name="nocodb"}' http://localhost:19391/api/v1/query > "$D/flux.json"
kill $PF 2>/dev/null; trap - EXIT
EXPECT_IMG="$EXPECT_IMG" SCOPE_NS="$SCOPE_NS" python3 - "$D" <<'PY' || { echo 'FAIL: §4.5 Prometheus gate'; exit 1; }
import json, os, sys
d = sys.argv[1]
def load(n):
    j = json.load(open(f'{d}/{n}.json'))
    assert j.get('status') == 'success', f'{n}: Prometheus API not success — instrument down, gate did NOT measure'
    return j['data']
bad = []
info = load('info')['result']
imgs = sorted({r['metric'].get('image') for r in info})
print('kube_pod_container_info images:', imgs)
if not info: bad.append('kube_pod_container_info returned 0 series — scrape broken, not a pass')
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
# DRY-TESTED 2026-10-01 (identical block):
#   default EXPECT_IMG (2026.09.1) against today's cluster -> "FAIL: image series
#     ['docker.io/nocodb/nocodb:2026.09.0'] != [...2026.09.1]", rc=1  (gate can fail)
#   EXPECT_IMG=...:2026.09.0 -> PROMETHEUS GATE PASSED, rc=0 (this is the §2i pre-check form)
#   SCOPE_NS=monitoring -> "scoped alerts firing: ['MaintenanceWindowMissed']", rc=1
# If the old pod's series lingers right after rollout, re-run once §4.1 has passed.

# --- 4.6 OPERATOR ACCEPTANCE (why this stays attended) ------------------------
# Log in through the normal route (Authentik forward-auth). Open the single base, both
# tables and all 4 views; confirm the large table renders its rows; make a test edit,
# reload, confirm it persisted; revert it. Open the new Table Tools panel once (new code
# path over migrated metadata). Measured scope 2026-10-01: 1 base / 2 models / 4 views.
# The hostname is NOT written here (public repo): read it from the live route,
#   kubectl get httproute -n databases nocodb -o jsonpath='{.spec.hostnames[0]}'
```

- CONTENTS ASSERTION: nocodb's metadata and user data must survive the 12
  migrations unchanged. §4.4 measures this with `compare.py` over `counts.txt`
  and `ledger-v0.txt`/`ledger-v2.txt`, captured live and compared to the §2g
  baseline in `~/backups/nocodb/pre-2026.09.1/pre`. It covers: per-table
  user-data row counts equal, base/model/view triple equal, no ledger entry
  lost, no knex lock held.
- CONTENTS ASSERTION: the running code is 2026.09.1. §4.2 reads
  `/api/v1/version` `currentVersion`, not an HTTP status.
- CONTROL: metric kube_pod_container_info — there must be exactly one image
  value for pods `nocodb-*` in ns databases, equal to
  `docker.io/nocodb/nocodb:2026.09.1`. 0 series is a FAIL.
- CONTROL: metric flux_resource_info — the HelmRelease nocodb series must be
  present with `ready="True"`. 0 series is a FAIL.
- CONTROL: alertname FluxResourceNotReady — must not be firing for
  name=nocodb. The scoped filter covers it. Because the alert has
  `for: 15m`, the metric read above is the fast signal and the alert is the
  slow one.

## 5) Rollback

**A tag revert alone is NOT a rollback.** After 12 knex migrations, 2026.09.0's
code has no guarantee it can read the migrated schema, and upstream documents
no downgrade. The rollback is fence, purge, restore, verify, then revert. This
is the procedure from `nocodb-2026.09.0` §5 with the counts and paths updated.

**Trigger:** any §4.1–§4.5 FAIL that a re-run does not clear, or a §4.6
failure. A `compare.py` FAIL on `userrows` or `triple` rolls back
immediately. A FAIL that is only a held lock also rolls back, because a
crashed migration leaves partial DDL.

```bash
# Steps 0-3 as ONE Bash call (timeout 600000): 3b reads $PRE_ACL from 2a.
cd /Users/mu/code/cberg-home-nextgen
set -o pipefail
NCDB_NAME=$(sops -d /Users/mu/code/cberg-home-nextgen/kubernetes/apps/databases/nocodb/app/secret.sops.yaml \
  | python3 -c "import sys,yaml,urllib.parse as u; s=yaml.safe_load(sys.stdin)['stringData']['NC_DB']; print(u.parse_qs(u.urlsplit(s).query)['d'][0])")
[ -n "$NCDB_NAME" ] || { echo 'ABORT: DB name did not resolve — do NOT run a blind restore'; exit 1; }
B=~/backups/nocodb/pre-2026.09.1
DUMP="$B/nocodb-pre-2026.09.1.sql.gz"
[ -f "$DUMP" ] && gzip -t "$DUMP" && [ -s "$B/pre/counts.txt" ] \
  || { echo "ABORT: dump or baseline missing under $B"; exit 1; }

# 1) FENCE: suspend the HR (no helm upgrade can re-scale mid-restore), then scale to 0.
flux suspend helmrelease nocodb -n databases
[ "$(kubectl get hr -n databases nocodb -o jsonpath='{.spec.suspend}')" = "true" ] \
  || { echo 'ABORT: HelmRelease not suspended — do not purge'; exit 1; }
kubectl scale deploy -n databases nocodb --replicas=0
kubectl wait --for=delete pod -n databases -l app.kubernetes.io/name=nocodb --timeout=120s

ncq() { kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -tAc "$0"' "$1"; }

# 2a) record schema public owner + ACL. Measured live 2026-10-01: owner pg_database_owner,
#     acl {pg_database_owner=UC/pg_database_owner,=U/pg_database_owner,nocodb=UC/pg_database_owner}
PRE_OWNER=$(ncq "select pg_get_userbyid(nspowner) from pg_namespace where nspname='public'")
PRE_ACL=$(ncq "select coalesce(nspacl::text,'') from pg_namespace where nspname='public'")
[ -n "$PRE_OWNER" ] && [ -n "$PRE_ACL" ] || { echo 'ABORT: could not read schema public owner/ACL'; exit 1; }
echo "pre-purge public owner=$PRE_OWNER acl=$PRE_ACL"

# 2b) purge DDL built FROM the measured ACL (nocodb-2026.09.0 §5 2b, dry-tested 2026-09-21
#     to reproduce this exact ACL incl. PUBLIC's USAGE-only grant).
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

# 2c) apply (one psql -c = one transaction). WHY purge at all: `pg_dump --clean` drops only
#     objects IN the dump, so tables the 12 migrations CREATED would survive a plain replay
#     and the exact-equality gate in 3 would (correctly) refuse — leaving nocodb down.
#     The user-data schema is NOT purged here: the dump's own --clean DROP/CREATE covers it
#     (the migrations do not create objects there), and 3 verifies its row counts exactly.
kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -v ON_ERROR_STOP=1 -c "$0"' \
  "$PURGE_SQL" || { echo 'ABORT: purge failed — nothing restored; escalate'; exit 1; }

# 2d) positive control: public must be empty before replay.
PURGED=$(ncq "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")
echo "public tables after purge: [$PURGED] (expect 0)"
[ "$PURGED" = "0" ] || { echo 'ABORT: schema not empty after purge — do NOT restore on top; escalate'; exit 1; }

# 2e) replay the dump. ON_ERROR_STOP=1 + pipefail are load-bearing.
gunzip -c "$DUMP" | kubectl exec -i -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -v ON_ERROR_STOP=1' \
  || { echo 'RESTORE FAILED — do NOT scale nocodb up; escalate to the operator'; exit 1; }

# 3) CONTENTS: the restore must reproduce the baseline EXACTLY (counts, both ledgers
#    name-for-name, locks 0/0/0, triple, per-table user-data rows).
rm -rf "$B/restored"; OUTDIR="$B/restored"; . "$B/capture.sh"
python3 "$B/compare.py" restore "$B/pre" "$B/restored" \
  || { echo 'RESTORE INCOMPLETE — app stays at 0 replicas; escalate'; exit 1; }

# 3b) schema grants came back (grantee SET compare; grantor may differ legitimately).
POST_ACL=$(ncq "select coalesce(nspacl::text,'') from pg_namespace where nspname='public'")
PRE_ACL="$PRE_ACL" POST_ACL="$POST_ACL" python3 -c "
import os, sys
g = lambda a: {e.split('=')[0] for e in a.strip('{}').split(',') if '=' in e}
missing = g(os.environ['PRE_ACL']) - g(os.environ['POST_ACL'])
print('grantees pre', sorted(g(os.environ['PRE_ACL'])), 'post', sorted(g(os.environ['POST_ACL'])))
sys.exit(1 if missing else 0)
" || { echo 'RESTORE INCOMPLETE — re-grant USAGE, CREATE ON SCHEMA public to the missing role, re-run 3b'; exit 1; }
echo 'DB RESTORED TO PRE-2026.09.1 BASELINE'
```

```bash
# 4) SEPARATE Bash call. Only now move git back, confirm the old tag reached the LIVE HR
#    spec, THEN resume (helm upgrade brings the pod back at replicas:1 on 2026.09.0).
#    NEVER `kubectl scale --replicas=1` by hand while the HR spec still says 2026.09.1:
#    that boots the new code against the restored DB and re-runs the migrations.
cd /Users/mu/code/cberg-home-nextgen
set -o pipefail
BUMP_SHA=<sha recorded at §3 step 3>
F=kubernetes/apps/databases/nocodb/app/helmrelease.yaml
git show "$BUMP_SHA^:$F" > "$F" || { echo 'ABORT: could not restore file'; exit 1; }
grep -E '^[[:space:]]*tag:[[:space:]]*2026\.09\.0$' "$F" >/dev/null || { echo 'ABORT: restored file is not 2026.09.0'; exit 1; }
MSG=/tmp/msg-nocodb-rollback-$(date +%s).txt
printf 'revert(nocodb): back to 2026.09.0 after failed 2026.09.1 (plan nocodb-2026.09.1 §5)\n' > "$MSG"
git commit --only "$F" -F "$MSG"
git log -1 --format=%s && git show --stat HEAD      # ONLY the nocodb helmrelease
git push
flux reconcile kustomization nocodb -n databases --with-source
TAG=$(kubectl get hr -n databases nocodb -o jsonpath='{.spec.values.controllers.nocodb.containers.app.image.tag}')
echo "live HR spec tag=[$TAG]"
[ "$TAG" = "2026.09.0" ] || { echo 'ABORT: HR spec not reverted yet — do NOT resume; re-run the reconcile'; exit 1; }
flux resume helmrelease nocodb -n databases
kubectl rollout status deploy/nocodb -n databases --timeout=5m
# Confirm: run §4.1 with 2026.09.0 in place of 2026.09.1, §4.2 expecting 2026.09.0, and
# §4.5 with EXPECT_IMG=docker.io/nocodb/nocodb:2026.09.0. Then the operator opens the base
# and confirms the data is back and an edit saves.
runbooks/update-marker.sh clear nocodb
```

The HR suspend/resume and scale-to-0 are the sanctioned direct-cluster
actions that fence the restore. Restoring the file in step 4 brings Flux's
desired state back. Disaster fallback if the dump itself is bad: the
`postgresql-data-5g` Longhorn backup checked fresh in §2e. Restoring it
rolls back **every** database in the shared instance (measured 2026-09-21:
`nocodb`, `oc8`, `pellets`, `postgres`, `sweep_history`). It is a last
resort, coordinated per `docs/sops/backup.md`.

## 6) Interference notes

- **`app-template-5.2.1` uses the same file and the same HelmRelease.** Its
  Batch A bumps `version: 5.1.0 → 5.2.1` in
  `kubernetes/apps/databases/nocodb/app/helmrelease.yaml`, and F-8d9677a0 is
  its row. It holds `nightly:2026-10-02`. The two plans are declared in
  `conflicts_with` so their helm upgrades never stack. Either order works:
  §3's sed and python anchor on the tag and on the `upgrade:` block, not on
  the chart version. §5 step 4 restores the bump's parent, so it keeps
  whatever chart version was live before.
- **`helm-drift-detection`, `flux-reconciler-impersonation`,
  `flux-oci-chart-sources`** change how this HR (or every HR) reconciles, so
  they are declared.
- **`mariadb-chart-27.3.0` and `redis-fleet-8.10.2`** roll workloads in
  ns `databases`. §4.5 blocks on any firing alert scoped to that namespace,
  so a same-night roll would either fail this gate or have its own failure
  hidden by it. They are declared.
- **Rollback-class stacking.** This plan is `backup-restore` +
  `capability_change: true`. Every open backup-restore plan is declared,
  following the house rule from `81fdd797`: jellyfin-12.1, n8n-2.39.8,
  paperless-db-13.0.2, nextcloud-fleet-35.0.1, penpot-chart-1.10.0,
  media-naming-p3, bitnamilegacy-exit-nextcloud-db, and
  talconfig-multidoc-migration. **None of those name this plan back.**
  `window-scheduler.py` honours one-sided declarations symmetrically (since
  2026-09-15). Adding the reciprocal entries is an orchestrator follow-up.
- **`float-tag-pinning` is deliberately NOT declared.** Its own file records
  the nocodb file-level collision as resolved: nocodb runs a pinned calver
  tag. Re-check that file's Batch B before scheduling if it is revived.
- **kube-prometheus-stack:** no open kps plan exists (91.4.1 executed
  2026-09-26). If one is drafted, it must be added here, because §4.5 reads
  Prometheus.
- **Shared `postgresql` instance:** it is not restarted. The migrations write
  only into the `nocodb` database. No other open plan writes to that
  database.
- **Downtime:** about 1–3 min (Recreate plus the migration boot). The
  routing (two HTTPRoutes: `nocodb` and `nocodb-authentik-outpost`), the
  Homepage tile and Authentik are untouched.
- **Window, recommended but not assigned (`window: null`):** this needs an
  attended slot for the §4.6 acceptance pass and because of
  `capability_change: true`. Checked against `maintenance-plan.py --open`
  on 2026-10-01:
  - Saturday budget is 70 min after the 20-min Step-0 reserve.
    `sat-attended:2026-10-03` holds uptime-kuma (45 min), and 45 + 45 = 90
    is over 70. Sat 10-10, 10-17, 10-24 and 10-31 each hold a declared
    backup-restore conflict. 11-07 holds helm-drift-detection.
  - Sun 10-04 and 10-11 are held by exclusive plans. 10-18 and 10-25 hold
    declared conflicts.
  - **`sun-attended:2026-11-01`** holds
    chart-patches-coredns-reloader-blackbox (medium, 60 min). With this plan
    that is risk 4/6 and 105/180 min, so it fits. **Recommended.**
  - **Faster alternative:** an operator-triggered on-demand NOW run. That is
    how `nocodb-2026.09.0` ran on 2026-09-26, inside 45 min. It can be
    scheduled any day after the cooldown clears at 2026-10-01T14:32Z.
- **One-way boundary:** after §4.6 passes and the window closes, the
  pre-dump is the only way back. Keep `~/backups/nocodb/pre-2026.09.1/`
  (dump, `pre/`, `capture.sh` and `compare.py`) at least until the next
  nightly Longhorn backup after sign-off. The older
  `~/backups/nocodb/pre-counts.txt` belongs to 2026.09.0; this plan never
  reads it.
