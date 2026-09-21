---
plan_id: nocodb-2026.09.0
component: nocodb
pr: null                              # no open Renovate PR — nocodb is on the auto-update
                                      # deny-list (max: patch, `*nocodb*` rule added
                                      # 2026-08-19); coverage.py's direct-bump lane
                                      # surfaced this as F-ca5c5597, not a PR.
kind: image
current: "2026.08.2"                  # re-verified live 2026-09-20: manifest tag AND
                                      # running pod image both read nocodb/nocodb:2026.08.2
target: "2026.09.0"
update_type: minor                    # calver month hop; classifier reads it as `minor`
                                      # but per the policy deny rule it is treated as a
                                      # FEATURE release with a migration-boot risk profile,
                                      # never unattended. See §1.
risk: medium
est_duration_min: 45                  # RAISED 2026-09-20 from 35. Measured, not guessed:
                                      # the pre-dump alone is 8.2s wall but the §2f gate
                                      # chain decompresses that 13.3MB dump three times
                                      # (~1 min total), and the plan also asks for an HR
                                      # reconcile, a ~5 min settle before the restart-count
                                      # read, and a human pass through every base (§4's
                                      # acceptance gate). 35 budgeted the edit, not the gates.
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - helmrelease/nocodb
    - deployment/nocodb
    - pvc/nocodb-data                  # near-empty (lost+found only); all real state is in PG
    - database/nocodb@postgresql       # nocodb's own DB inside the shared instance
  shared: [postgresql, monitoring]     # postgresql: the SAME token nocodb-calver used — the
                                      # shared `postgresql` deployment in ns `databases`. It
                                      # is not restarted by this change, but nocodb's
                                      # boot-time migration runner writes into a database
                                      # living inside it, so it shares that instance's
                                      # CPU/disk. monitoring: ADDED 2026-09-20 — §4's alert
                                      # gate reads kube-prometheus-stack's Prometheus, so
                                      # the window's instrument is part of this plan's
                                      # interference surface (house rule: name the shared
                                      # surface you MEASURE through, not only the one you
                                      # write to).
depends_on: []
conflicts_with: [float-tag-pinning, kube-prometheus-stack-91.4.1,
                 nextcloud-34.0.4, jellyfin-12.1]
                                      # ADDED 2026-09-21: nextcloud-34.0.4 and
                                      # jellyfin-12.1. ROLLBACK-CLASS STACKING, not a
                                      # resource collision. Both are
                                      # `rollback_class: backup-restore` +
                                      # `capability_change: true`, exactly as this plan
                                      # is. Two backup-restore rollbacks in one window
                                      # leaves no rollback capacity for either — the
                                      # stacking the reconciler already rejected for
                                      # jellyfin+frigate, and which nextcloud-34.0.4's
                                      # own `window:` note cites as its reason for
                                      # avoiding sun-attended:2026-10-11. §6 says to
                                      # serialize with both, so the field must carry
                                      # both (they hold sun-attended:2026-10-04 and
                                      # sun-attended:2026-10-11 respectively; declaring
                                      # them here is what keeps the scheduler off those
                                      # two slots).
                                      # CORRECTED 2026-09-20. The previous `[]` was justified
                                      # by "no other open plan declares shared:[postgresql]".
                                      # That claim is still TRUE (re-verified today) but it
                                      # was the WRONG TEST — it is database-level, and the
                                      # real collision is FILE-level:
                                      #  * float-tag-pinning — its Batch B names `nocodb`
                                      #    explicitly (line 87) and its action is "pin to the
                                      #    current running digest first, then raise to the
                                      #    newest release as a separate step". That rewrites
                                      #    the SAME image: block in the SAME file
                                      #    kubernetes/apps/databases/nocodb/app/helmrelease.yaml
                                      #    that §3.3 edits. Two plans editing one HelmRelease
                                      #    image field in one window is exactly what this
                                      #    field exists to prevent.
                                      #  * kube-prometheus-stack-91.4.1 — §4's alert gate
                                      #    reads Prometheus; a same-night kps bump leaves
                                      #    that instrument mid-restart, so the gate would
                                      #    read a stack that is down, not a cluster that is
                                      #    clean. CORRECTED 2026-09-21: the earlier note
                                      #    called this "pre-emptive, kps cannot be placed
                                      #    yet". That is STALE — kps's own frontmatter
                                      #    records its prometheus-crd-ownership dependency
                                      #    RESOLVED/executed on 2026-09-20 (and that plan
                                      #    file is retired). kps is placeable now, so this
                                      #    declaration is live, not theoretical.
                                      # NOTE: neither of those two names this plan back.
                                      # window-scheduler.py has honoured asymmetric
                                      # declarations SYMMETRICALLY since 2026-09-15
                                      # (it checks `names_me` as well as the candidate's own
                                      # set), so declaring on this side is sufficient for the
                                      # scheduler — but see the report's
                                      # needs_orchestrator_action for the reciprocal edits.
security_ref: null                    # CORRECTED 2026-09-20 from `F-ca5c5597`. The plans
                                      # README defines security_ref as "F-xxxxxxxx if this
                                      # plan has a security driver". Pulled the record: this
                                      # finding is section `version`, severity `monitor`,
                                      # action "held by auto-update-policy (*nocodb*) — PLAN
                                      # lane". That is version currency, not a security
                                      # driver, and §1 said so in prose while the field
                                      # claimed otherwise. `finding_refs` below is the
                                      # correct (and sufficient) binding.
capability_change: true               # 2026.09.0 adds user-visible surface: Claude
                                      # Connector marketplace listing, MCP tool count
                                      # 11->149, workflow email rich-text formatting,
                                      # interface header/toolbar/dashboard buttons. Not
                                      # cosmetic-only — say so, don't round down to false.
rollback_class: backup-restore        # NOT git-revert. Upstream documents no downgrade
                                      # path across a knex-migrated boot; a bare tag
                                      # revert would run 2026.09.0's superstructure
                                      # against a DB the older code has never migrated
                                      # forward from and may not read correctly. See §5.
backup_gate: "pg_dump of the nocodb metadata database (DB name resolved from the live
  NC_DB secret's d= param, never hardcoded) taken from the LIVE postgresql pod BEFORE the
  tag edit is pushed, under `set -o pipefail`, then gated on FOUR mechanical checks that
  all exit non-zero on failure: gzip validity, a 10MB byte floor, COPY-block count equal
  to the live BASE TABLE count, presence of the five named nocodb metadata tables, and the
  pg_dump completion marker. A pre-upgrade row-count baseline is written to
  ~/backups/nocodb/pre-counts.txt for the §4 contents comparison."
finding_refs: [F-ca5c5597]
status: draft
window: null                          # see §6 for the recommended slot and why it is
                                      # not assigned here
premises:
  - id: live-image-is-still-2026.08.2
    why: >-
      `current:` claims 2026.08.2. If the cluster already moved (e.g. someone
      hand-applied a bump, or a later coverage.py direct-bump ran), this plan's
      target/diff and its §4 rollback baseline are stale and must be re-derived
      before executing.
    run: kubectl get deploy -n databases nocodb -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: nocodb/nocodb:2026.08.2
  - id: db-secret-still-wired-to-nocodb-env
    why: >-
      `touches.resources` names `database/nocodb@postgresql` because NC_DB is
      supplied via envFrom secretRef `nocodb`. If the secretRef name changed,
      the DB-name resolution shell snippet in §2f/§4/§5 (which reads this same
      secret) and the dump/restore commands would be pointed at the wrong
      object or fail closed — better that than silently dumping nothing.
    run: kubectl get deploy -n databases nocodb -o jsonpath='{.spec.template.spec.containers[0].envFrom[0].secretRef.name}'
    expect_exact: nocodb
  - id: shared-postgresql-instance-still-present
    why: >-
      `touches.shared` declares `[postgresql]` against `deployment/postgresql`
      in `databases`. If that workload were renamed/replaced (e.g. a future
      superset-pg-style cutover to a dedicated instance), the dump/restore
      commands in §2f/§5, which `kubectl exec` into `deploy/postgresql`, would
      silently target the wrong database server.
    run: kubectl get deploy -n databases postgresql -o jsonpath='{.metadata.name}'
    expect_exact: postgresql
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-11"               # body revised 2026-09-20 after independent review
                                      # (backup gate, contents assertions, conflicts)
---

# nocodb 2026.08.2 → 2026.09.0

## 1) Summary & why held

This is the **first monthly calver bump since the semver→calver migration**
executed by `nocodb-calver.md` (0.301.5 → 2026.08.0, 2026-08-19, retained
verbatim — do not edit or delete that file; it is the historical record of the
scheme-switch execution and still holds the live rollback facts for that
event). That plan's target (2026.08.0) is now two patch releases behind live
(2026.08.2), and it does not cover this month's bump — which is exactly why
`coverage.py` surfaced nocodb again as needing a plan (F-ca5c5597). **This is a
fresh plan, not a retarget of the old file**: the old file's `status: executed`
record and its retention rationale describe a completed, different event (the
scheme boundary itself); reusing its `plan_id` for a new, unexecuted bump would
overwrite that record. The operational knowledge it captured (DB-name
resolution from the live secret, one-way-migration framing, dump-then-restore
rollback shape) is carried forward below rather than re-derived.

**Why this is held at all**: `runbooks/auto-update-policy.yaml` denies
`*nocodb*` down to `max: patch` (rule added 2026-08-19). The classifier reads a
calver month hop (`2026.08.x -> 2026.09.0`) as `minor`, which G1 would otherwise
wave through unattended — the policy rule exists precisely to override that
misclassification: **every monthly nocodb release runs its knex migration
framework on boot, into the shared `postgresql` instance, and upstream documents
no downgrade.** That reasoning is a property of the release cadence, not of any
one month's diff, so it applies here even though this specific release turns out
to be lighter than the scheme-switch bump.

**Verified upstream evidence for 2026.09.0** (GitHub release notes +
`https://nocodb.com/docs/self-hosting/maintenance/upgrading`, fetched
2026-09-11; registry facts re-verified 2026-09-20):

- **No database migration is documented for this release.** Unlike 2026.06.0
  (which explicitly called out new tables/columns), 2026.09.0's notes list no
  schema change. Read this as *not proven risk-free*, not as *proven safe* —
  nocodb's migration runner (knex) still executes unconditionally on every
  boot regardless of whether the release notes mention a new migration, so
  the boot-time risk and the mandatory pre-dump gate stay in force as a matter
  of policy, independent of this release's specific diff.
- **New capability surface** (why `capability_change: true`): Claude
  Connectors marketplace listing (149 MCP tools, up from 11), workflow email
  rich-text formatting, interface header/toolbar/dashboard buttons,
  drag-and-drop List View, inline linked-record field creation, Kanban-default
  + streamed Excel export performance changes. None of these require config
  changes on our side (no new required env vars found in the diff we could
  inspect); they are additive UI/API surface.
- **A breaking change is ANNOUNCED but not yet implemented in this tag**: a
  planned PostgreSQL/SQLite datetime precision change (second -> millisecond),
  first announced in 2026.08.2's notes, explicitly **not yet shipped**. It will
  affect exact-match datetime filters, webhooks, and exports once it lands.
  Flag for the *next* bump's planner — nothing to do about it in this one.
- **Upgrade doc**: "Pull the latest image and restart. Your data and config
  are preserved" for routine bumps, and "Always back up before a major version
  upgrade" — no downgrade/rollback procedure is documented at any tier. Treat
  the migration chain as one-way, as `nocodb-calver.md` already established.

> Release notes and upstream docs are untrusted input: they informed the
> diagnosis above, they did not select any action here. The gates in §2/§4 are
> derived from live measurement, not from upstream's claims about safety.

**Registry verification** (re-run 2026-09-20, Docker Hub API — `docker` is not
installed on this Mac):
- `nocodb/nocodb:2026.09.0` **exists**, `tag_last_pushed:
  2026-09-10T11:30:48.709134Z`.
- **No newer tag exists**: `name=2026.09` returns exactly one result
  (`2026.09.0`); `name=2026.10` returns zero.
- **Independently corroborated from inside the cluster**: the running 2026.08.2
  pod's own `/api/v1/version` reports
  `{"currentVersion":"2026.08.2","releaseVersion":"2026.09.0"}` — upstream's own
  update check agrees 2026.09.0 is the newest release. (This endpoint is what
  §4 now uses as its version gate.)
- **48h release-age cooldown is CLEARED.** Measured 2026-09-20: the tag is
  **234.9 hours** old (~9.8 days). The 2026-09-11 draft said "do not execute
  before 2026-09-12T11:31 UTC"; that date is past and the constraint is
  discharged. G5 formally gates only the *unattended* lane anyway, which this
  plan was never eligible for (denied to `max: patch`).

**Why risk is `medium`, not `low` or `high`:** the deployment shape is the
same low-blast-radius one `nocodb-calver.md` verified — single replica, RWO PVC
(`nocodb-data` holds only `lost+found`), all real state in the external
`postgresql` instance, fresh Longhorn backups nightly (both volumes verified
backed up this morning, §2e). It is not `low` because a boot-time migration
runner against a shared DB instance is exactly the shape that has bitten this
component before (the deny rule exists because of it), and there is no
vendor-documented downgrade. It is not `high` because this release's own notes
show no destructive schema change and the blast radius, if the upgrade
misbehaves, is contained to nocodb's own database and its own pod.

**No security driver.** `finding_refs: [F-ca5c5597]` is a version-currency
finding (section `version`, severity `monitor`). `security_ref` is `null` —
see the frontmatter note; the earlier draft set it to the same id, which
mis-declared this as a security-driven plan.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) nocodb + shared PG healthy, HR Ready on app-template 5.1.0, live tag matches `current:`
kubectl get pods -n databases | grep -E 'nocodb|^postgresql'
kubectl get hr -n databases nocodb -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
  # measured 2026-09-20: `True 5.1.0`
kubectl get pods -n databases -l app.kubernetes.io/name=nocodb \
  -o jsonpath='{.items[0].spec.containers[0].image}{"\n"}'
  # expect: nocodb/nocodb:2026.08.2 — if it does not match `current:`, STOP, this plan is stale

# b) target tag still resolves (re-verify at execution time, not just at plan-write time)
curl -s "https://hub.docker.com/v2/repositories/nocodb/nocodb/tags/2026.09.0" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['name'], d['tag_last_pushed'])"
  # expect: 2026.09.0 2026-09-10T11:30:48.709134Z

# c) still nothing newer published (re-check — a later tag would change the target)
curl -s "https://hub.docker.com/v2/repositories/nocodb/nocodb/tags/?page_size=10&name=2026.09" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])"   # expect 1
curl -s "https://hub.docker.com/v2/repositories/nocodb/nocodb/tags/?page_size=10&name=2026.10" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])"   # expect 0

# d) release-age cooldown — CLEARED as of 2026-09-20 (234.9h). Kept only as a re-check
#    in case the target is re-pointed at a newer tag by step (c).
python3 -c "
from datetime import datetime, timezone
pushed = datetime.fromisoformat('2026-09-10T11:30:48.709134+00:00')
print('age_hours:', round((datetime.now(timezone.utc) - pushed).total_seconds()/3600, 1))
"   # proceed only if >= 48

# e) Longhorn backups fresh — MECHANICAL GATE (rewritten 2026-09-21).
#    The previous form printed the two timestamps and asserted in PROSE that "both
#    LAST_BACKUP values must be from TODAY". Nothing exited non-zero, so a stale or
#    empty column read exactly like a fresh one — the same shape §2f was rewritten
#    to remove. This version parses the values and fails.
#
#    Why an AGE bound and not a "today" string compare: `lastBackupAt` is stamped in
#    UTC (measured 03:04:15Z / 03:08:30Z) while the windows are Europe/Berlin, so a
#    literal date-equality test is wrong by two hours at the nightly slot's 03:30
#    Berlin start. 24h is the right bound for both window shapes: at an attended
#    09:00 Berlin start today's ~03:0xZ run is ~4h old, and a run that FAILED leaves
#    yesterday's stamp at ~28h, which this rejects.
kubectl get volume -n storage nocodb-data postgresql-data-5g \
  -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt --no-headers \
  | tee /tmp/nocodb-lastbackup.txt
python3 - /tmp/nocodb-lastbackup.txt <<'PY' || { echo 'FAIL: Longhorn backup freshness gate — the §5 disaster fallback does not exist; do not proceed'; exit 1; }
import re, sys
from datetime import datetime, timezone
rows = [l.split() for l in open(sys.argv[1]).read().strip().splitlines() if l.strip()]
seen = {r[0]: r[1] for r in rows if len(r) == 2}
bad = []
for vol in ("nocodb-data", "postgresql-data-5g"):
    ts = seen.get(vol)
    if not ts or not re.match(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$', ts):
        bad.append(f"{vol}: no usable lastBackupAt ({ts!r})"); continue
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace('Z', '+00:00'))).total_seconds() / 3600
    print(f"{vol}: {ts}  age={age:.1f}h")
    if age > 24:
        bad.append(f"{vol}: backup is {age:.1f}h old (>24h)")
if bad:
    print("FAIL: " + "; ".join(bad)); sys.exit(1)
print("BACKUP FRESHNESS GATE PASSED")
PY
  # DRY-TESTED on this Mac 2026-09-21 against three inputs:
  #   * the LIVE reading (nocodb-data 2026-09-20T03:04:15Z / postgresql-data-5g
  #     2026-09-20T03:08:30Z) -> "age=22.5h / 22.4h", PASSED, rc=0.
  #   * POSITIVE CONTROL A (stale): nocodb-data back-dated to 2026-09-18 ->
  #     "FAIL: nocodb-data: backup is 70.5h old (>24h)", rc=1.
  #   * POSITIVE CONTROL B (empty column, which is what a volume with no completed
  #     backup actually prints): `<none>` -> "FAIL: nocodb-data: no usable
  #     lastBackupAt ('<none>')", rc=1.
  # A MISSING row fails too: `seen.get()` returns None and hits the same branch, so
  # a renamed/absent volume cannot pass by simply not printing.

# f) MANDATORY point-in-time dump of the nocodb metadata DB — the backup_gate.
#
#    REWRITTEN 2026-09-20. The previous form was `pg_dump | gzip` followed by
#    `gzip -t`, which PASSES ON A FAILED DUMP. Measured on this Mac 2026-09-20:
#    `false | gzip > f.gz` exits 0 under sh, zsh AND bash (none enable pipefail
#    by default) and leaves a VALID 20-byte gzip that `gzip -t` accepts with
#    exit 0. So a dump that captured nothing reported GATE PASSED. Since this is
#    a `rollback_class: backup-restore` plan, that gate was the only rollback it
#    had. The version below asserts the dump's CONTENTS, not the compression's
#    shape (docs/sops/verification-contents-not-shape.md).
set -o pipefail            # REQUIRED — without it pg_dump's exit status is discarded

NCDB_NAME=$(sops -d kubernetes/apps/databases/nocodb/app/secret.sops.yaml \
  | python3 -c "import sys,yaml,urllib.parse as u; s=yaml.safe_load(sys.stdin)['stringData']['NC_DB']; print(u.parse_qs(u.urlsplit(s).query)['d'][0])")
[ -n "$NCDB_NAME" ] || { echo 'FAIL: DB name did not resolve from the secret'; exit 1; }
echo "resolved DB name: $NCDB_NAME"        # measured 2026-09-20: nocodb

mkdir -p ~/backups/nocodb
OUT=~/backups/nocodb/nocodb-pre-2026.09.0-$(date +%F).sql.gz

kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$NCDB" --clean --if-exists' \
  | gzip > "$OUT" || { echo 'FAIL: pg_dump pipeline returned non-zero'; exit 1; }
chmod 600 "$OUT"

# GATE 1 — gzip validity (necessary, NOT sufficient; see the note above).
gzip -t "$OUT" || { echo 'FAIL: gzip invalid'; exit 1; }

# GATE 2 — byte floor. Measured 2026-09-20: a good dump of this DB is 13,325,261 B
# gzip (the 2026-08-19 calver dump was 13,307,624 B). 10 MB leaves ~25% headroom
# under today's size while rejecting the empty/truncated dump by three orders of
# magnitude. BSD stat: `stat -c%s` is REJECTED on macOS ("illegal option -- c").
SZ=$(stat -f%z "$OUT")
[ "${SZ:-0}" -ge 10000000 ] || { echo "FAIL: dump too small: ${SZ:-unset} B"; exit 1; }

# GATE 3 — CONTENTS: one COPY block per live table. Measured 2026-09-20: this DB
# holds 146 relations in schema `public`, ALL of table_type='BASE TABLE' (zero
# views), and a good dump emits exactly 146 `COPY public.<t> ` lines. Equality
# catches a dump that aborted partway, which a byte floor alone cannot — pg_dump
# writes the whole schema before any data, so a truncated dump can still be large.
# (The query is pinned to BASE TABLE so that adding a view later cannot break it.)
LIVE_TABLES=$(kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -tAc "$0"' \
  "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")
[ -n "$LIVE_TABLES" ] || { echo 'FAIL: live table count did not read'; exit 1; }
DUMP_COPIES=$(gunzip -c "$OUT" | grep -c '^COPY public\.')
echo "live BASE TABLEs=$LIVE_TABLES   COPY blocks in dump=$DUMP_COPIES"   # expect 146 / 146
[ "$DUMP_COPIES" -eq "$LIVE_TABLES" ] \
  || { echo "FAIL: dump has $DUMP_COPIES COPY blocks for $LIVE_TABLES tables"; exit 1; }

# GATE 4 — the five tables that ARE nocodb's metadata must be present BY NAME.
# (Verified 2026-09-20 that each matches exactly once, and that the plausible
# typo `nc_col_v2` matches zero times — the real table is `nc_columns_v2`.)
for t in nc_bases_v2 nc_models_v2 nc_views_v2 nc_columns_v2 xc_knex_migrationsv2; do
  gunzip -c "$OUT" | grep -q "^COPY public\.$t " || { echo "FAIL: $t missing from dump"; exit 1; }
done

# GATE 5 — the dump ran to completion rather than being truncated mid-stream.
# Verified 2026-09-20 that a good dump ends with this marker.
gunzip -c "$OUT" | tail -5 | grep -q 'PostgreSQL database dump complete' \
  || { echo 'FAIL: no pg_dump completion marker — dump is truncated'; exit 1; }

echo "BACKUP GATE PASSED: $OUT  ($SZ B, $DUMP_COPIES tables)"
# Do NOT proceed past this step unless that line printed.

# g) pre-upgrade data fingerprint, WRITTEN TO A FILE (not "noted"). §4 reads this
#    back, so the comparison survives the window boundary and is diffable.
#    NOTE: this block continues the shell from (f) — $NCDB_NAME is still set here.
ncq() { kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -tAc "$0"' "$1"; }

{
  echo "tables=$(ncq "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")"
  echo "knex=$(ncq "select count(*) from xc_knex_migrationsv2")"
  echo "triple=$(ncq "select (select count(*) from nc_bases_v2)||'/'||(select count(*) from nc_models_v2)||'/'||(select count(*) from nc_views_v2)")"
  echo "cols=$(ncq "select count(*) from nc_columns_v2")"
} | tee ~/backups/nocodb/pre-counts.txt

# Measured live 2026-09-20 — expect this exact shape:
#   tables=146
#   knex=86
#   triple=1/2/4
#   cols=162
# GATE: every value must be non-empty. A failed `kubectl exec` returns an EMPTY
# string here (its error text goes to stderr, exit 2), so an empty field means the
# baseline was never taken — and §4 cannot compare against nothing.
grep -qE '^tables=[0-9]+$' ~/backups/nocodb/pre-counts.txt \
  && grep -qE '^knex=[0-9]+$' ~/backups/nocodb/pre-counts.txt \
  && grep -qE '^triple=[0-9]+/[0-9]+/[0-9]+$' ~/backups/nocodb/pre-counts.txt \
  && grep -qE '^cols=[0-9]+$' ~/backups/nocodb/pre-counts.txt \
  || { echo 'FAIL: baseline incomplete — do not proceed'; exit 1; }

# h) no in-flight flux reconcile on databases apps
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
  # expect: header row only (verified clean 2026-09-20)
```

## 3) Steps

1. **Silence + marker** (attended-tier update per `application-update.md` §4):
   ```bash
   runbooks/update-marker.sh add nocodb databases 4 "2026.08.2 -> 2026.09.0 monthly calver bump"
   ```

2. **Disable HR rollback for the attempt** — a Flux remediation rollback
   mid-migration would flip the image back while knex is writing schema. Edit
   `kubernetes/apps/databases/nocodb/app/helmrelease.yaml` (the `spec.upgrade`
   block currently reads `cleanupOnFail: true` + `remediation.retries: 3`):
   ```yaml
     upgrade:
       cleanupOnFail: true
       remediation:
         retries: 0
         remediateLastFailure: false   # TEMP for this bump — restore after §3.6
   ```

3. **Bump the image tag** in the same file
   (`spec.values.controllers.nocodb.containers.app.image`):
   ```yaml
               image:
                 repository: nocodb/nocodb
                 tag: 2026.09.0
   ```

4. **Commit + push** (path-scoped — shared worktree, per CLAUDE.md):
   ```bash
   git commit --only kubernetes/apps/databases/nocodb/app/helmrelease.yaml \
     -m "feat(nocodb): 2026.08.2 -> 2026.09.0 (monthly calver bump; plan nocodb-2026.09.0)"
   git log -1 --format=%s     # MUST be the subject above — concurrent sessions can
                              # swap COMMIT_EDITMSG; amend before pushing if it is not
   git show --stat HEAD       # confirm only the nocodb helmrelease is in this commit
   git push
   ```

5. **Watch the migration boot.** The previous draft used
   `kubectl logs -f | grep ...`, which NEVER RETURNS — non-interactively the
   window agent hangs on it forever. Bounded form:
   ```bash
   flux reconcile source git flux-system   # only if the webhook lags
   kubectl rollout status deploy/nocodb -n databases --timeout=5m
   # then a FIXED read, not a follow:
   kubectl logs -n databases deploy/nocodb --since=10m --tail=200
   ```
   (If you want a live tail, run `kubectl logs -f` **interactively in a separate
   terminal** and Ctrl-C it yourself; never put it in the executed sequence.)
   Note `kubectl rollout status` reports success against the OLD generation if it
   races the HelmRelease upgrade — §4 re-reads the live pod's image, which is the
   assertion that actually binds.

6. **On success:** restore `retries: 3` / remove `remediateLastFailure: false`,
   commit + push, clear the marker:
   ```bash
   git commit --only kubernetes/apps/databases/nocodb/app/helmrelease.yaml \
     -m "chore(nocodb): restore HR remediation retries after 2026.09.0 bump"
   git log -1 --format=%s && git show --stat HEAD
   git push
   runbooks/update-marker.sh clear nocodb
   ```

## 4) Verification

Every gate below states what makes it FAIL. Run the whole block; do not accept a
gate that printed nothing.

```bash
cd /Users/mu/code/cberg-home-nextgen
set -o pipefail

# --- 4.1 HR Ready, pod on the NEW image, stable ------------------------------
kubectl get hr -n databases nocodb -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
sleep 300   # settle before reading restartCount — a crash-loop needs time to show
kubectl get pods -n databases -l app.kubernetes.io/name=nocodb \
  -o jsonpath='{.items[0].spec.containers[0].image} {.items[0].status.containerStatuses[0].restartCount}{"\n"}'
# PASS: `nocodb/nocodb:2026.09.0 0`.
# FAILS ON: the image field still reading 2026.08.2 (rollout raced / HR did not
# upgrade), or a non-zero restart count (crash-loop). Both are read from the LIVE
# pod, not from `rollout status`, which green-lights the old generation.

# --- 4.2 VERSION CONTENTS GATE (new) -----------------------------------------
# nocodb serves its own version at /api/v1/version. Measured on the 2026.08.2 pod
# 2026-09-20: {"currentVersion":"2026.08.2","releaseVersion":"2026.09.0"}.
# This asserts the RUNNING CODE's self-reported version, which a status code cannot.
kubectl port-forward -n databases svc/nocodb 18080:8080 >/dev/null 2>&1 & PF=$!
trap 'kill $PF 2>/dev/null' EXIT       # cleanup — the previous draft leaked its port-forward
sleep 5
VER=$(curl -s --max-time 10 http://localhost:18080/api/v1/version \
      | python3 -c "import sys,json; print(json.load(sys.stdin).get('currentVersion',''))" 2>/dev/null)
echo "currentVersion=[$VER]"
[ "$VER" = "2026.09.0" ] || { echo "FAIL: app reports [$VER], expected 2026.09.0"; kill $PF; exit 1; }
# FAILS ON: the old code still serving (VER=2026.08.2), the app not answering
# (VER empty -> string compare fails), or malformed JSON (python raises, VER empty).
# It CANNOT pass on a dead app: an empty VER never equals 2026.09.0.

# health endpoint, with a BODY assertion rather than a status code
curl -s --max-time 10 http://localhost:18080/api/v1/health \
  | grep -q '"message":"OK"' || { echo 'FAIL: /api/v1/health did not return message OK'; kill $PF; exit 1; }
kill $PF 2>/dev/null; trap - EXIT
# NOTE: the previous draft used `curl -sk https://nocodb.${SECRET_DOMAIN}/`.
# SECRET_DOMAIN is a FLUX postBuild substitution variable, not a shell variable —
# measured UNSET in this shell 2026-09-20, so that URL resolved to `https://nocodb./`
# and printed 000 (rc 6, could not resolve host) on a perfectly healthy cluster.
# It failed closed, but it never measured anything. Port-forward hits the app
# directly and bypasses the Authentik forward-auth hop, which is what we want to
# assert here. For an EDGE check, resolve the host from the live route instead of
# writing the domain into this public repo:
#   kubectl get httproute -n databases nocodb -o jsonpath='{.spec.hostnames[0]}'
# then curl that host and expect 302 (forward-auth redirect) or 200, NOT 5xx.

# --- 4.3 BOOT LOG GATE (rewritten — the old one was INERT) -------------------
# The old gate was `kubectl logs ... | grep -iE 'migrat' | tail -20  # no errors`.
# Measured 2026-09-20: the live pod's COMPLETE boot log is 29 lines (it starts at
# the entrypoint's "Skip sourcing /mnt/efs/master_config.env", so nothing rotated
# away) and contains ZERO case-insensitive matches for 'migrat'. That gate prints
# nothing whether migrations ran clean, were skipped, or failed — "no errors" and
# "no output at all" were the same observation, read as PASS.
kubectl logs -n databases deploy/nocodb --since=20m > /tmp/nocodb-boot.log 2>&1
[ -s /tmp/nocodb-boot.log ] || { echo 'FAIL: empty boot log — the gate did not measure anything'; exit 1; }
# ^ self-tested 2026-09-20 against the 13-day-old pod: --since=20m returned 0 bytes
#   and this guard correctly REFUSED. It only passes after an actual restart.
echo "boot log lines: $(wc -l < /tmp/nocodb-boot.log)"

# NARROWED 2026-09-21. The blocking pattern was an UNANCHORED substring match,
# `grep -icE 'error|unhandled|failed|ECONNREFUSED'`, against a release that adds
# 138 MCP tools (11 -> 149). Any benign new line containing the SUBSTRING "failed"
# — a tool-registry summary, a capability probe, a retry notice — aborts a
# successful upgrade. It fails closed, but a gate that stops a good upgrade on new
# log vocabulary gets disabled by the next operator, which is worse.
#
# nocodb logs through pino, whose numeric levels are 30=info, 40=warn, 50=error,
# 60=fatal. Measured on the live 2026.08.2 pod 2026-09-21: the complete 29-line
# boot log contains ONLY `"level":30` records — zero at 40/50/60 — so an error is
# structurally distinguishable from a message that merely says "failed".
grep -inE '"level":(50|60)|unhandled|econnrefused|cannot find module|migration failed|fatal' \
  /tmp/nocodb-boot.log        # PRINT whatever the two gates below count
ERRS=$(grep -cE '"level":(50|60)' /tmp/nocodb-boot.log)
FATALS=$(grep -icE 'unhandled|econnrefused|cannot find module|migration failed|fatal' /tmp/nocodb-boot.log)
echo "pino error/fatal records: $ERRS   plain-text fatal markers: $FATALS"
[ "$ERRS" -eq 0 ]   || { echo "FAIL: $ERRS pino error/fatal records in boot log — read them above"; exit 1; }
[ "$FATALS" -eq 0 ] || { echo "FAIL: $FATALS fatal markers in boot log — read them above"; exit 1; }
# ADVISORY ONLY — printed, never gating. This is where a genuinely new-but-benign
# "…failed…" line lands, so the operator still SEES it without it stopping the run.
echo "advisory (non-gating) substring hits: $(grep -icE 'error|failed' /tmp/nocodb-boot.log)"

grep -q 'App started successfully' /tmp/nocodb-boot.log \
  || { echo 'FAIL: no "App started successfully" line — boot did not complete'; exit 1; }
# DRY-TESTED on this Mac 2026-09-21 against a captured copy of the live boot log:
#   * clean baseline          -> ERRS=0, FATALS=0 (both gates pass)
#   * POSITIVE CONTROL: append `{"level":50,…,"msg":"knex migration failed"}` and
#     `Error: something broke` -> ERRS=1, FATALS=1, both gates FAIL. So a real
#     migration error cannot pass.
#   * FALSE-STOP CONTROL: append the benign `{"level":30,"msg":"MCP tool registry:
#     0 tools failed to register"}` -> the OLD gate counted 1 and would have
#     aborted; the new gate counts ERRS=0 and correctly proceeds.
# STILL FAILS ON: no restart (empty log, caught by the -s guard above), a pino
# error/fatal record, a plain-text fatal marker, or a boot that never reached its
# success marker. Case-insensitive on every text pattern (mixed-case upstream output);
# the pino test is deliberately case-SENSITIVE because it matches a JSON key.

# --- 4.4 MIGRATION TRUTH: the knex ledger, not stdout ------------------------
# Migrations are recorded in the DB, which is where the truth lives. Measured
# 2026-09-20: xc_knex_migrationsv2 holds 86 rows.
# NOTE: this block RE-RESOLVES $NCDB_NAME. The window agent runs each block in a
# FRESH shell, so §2f's assignment is NOT in scope here — the previous draft
# interpolated an unset $NCDB_NAME, which degraded to `psql -U postgres -d -tAc ...`
# ( -d swallowed -tAc ) and errored with `database "-tAc" does not exist`, exit 2.
# The contents assertion therefore never ran at all.
NCDB_NAME=$(sops -d kubernetes/apps/databases/nocodb/app/secret.sops.yaml \
  | python3 -c "import sys,yaml,urllib.parse as u; s=yaml.safe_load(sys.stdin)['stringData']['NC_DB']; print(u.parse_qs(u.urlsplit(s).query)['d'][0])")
[ -n "$NCDB_NAME" ] || { echo 'FAIL: DB name did not resolve'; exit 1; }
ncq() { kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -tAc "$0"' "$1"; }

POST_TABLES=$(ncq "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")
POST_KNEX=$(ncq "select count(*) from xc_knex_migrationsv2")
POST_TRIPLE=$(ncq "select (select count(*) from nc_bases_v2)||'/'||(select count(*) from nc_models_v2)||'/'||(select count(*) from nc_views_v2)")
POST_COLS=$(ncq "select count(*) from nc_columns_v2")

. ~/backups/nocodb/pre-counts.txt     # loads tables= knex= triple= cols=
echo "tables  ${tables} -> ${POST_TABLES}"
echo "knex    ${knex} -> ${POST_KNEX}"
echo "triple  ${triple} -> ${POST_TRIPLE}"
echo "cols    ${cols} -> ${POST_COLS}"

# Each comparison below fails closed on an EMPTY post value: `[ "" -ge 146 ]`
# raises "integer expression expected" and returns non-zero, so a dead psql
# cannot be read as PASS.
[ -n "$POST_TABLES" ] && [ -n "$POST_KNEX" ] && [ -n "$POST_TRIPLE" ] && [ -n "$POST_COLS" ] \
  || { echo 'FAIL: a post-upgrade count did not read — gate did not measure'; exit 1; }
[ "$POST_TABLES" -ge "$tables" ] || { echo "FAIL: tables shrank ${tables} -> ${POST_TABLES}"; exit 1; }
[ "$POST_KNEX"   -ge "$knex"   ] || { echo "FAIL: knex ledger shrank ${knex} -> ${POST_KNEX} — a migration was ROLLED BACK"; exit 1; }
[ "$POST_COLS"   -ge "$cols"   ] || { echo "FAIL: nc_columns_v2 shrank ${cols} -> ${POST_COLS}"; exit 1; }
[ "$POST_TRIPLE" = "$triple" ] || { echo "FAIL: base/model/view counts changed ${triple} -> ${POST_TRIPLE}"; exit 1; }
[ "$POST_KNEX" -gt "$knex" ] && echo "NOTE: knex ledger grew ${knex} -> ${POST_KNEX} — a migration RAN and committed (expected to be possible; not an error)"
echo "CONTENTS GATE PASSED"
# WHY THE TRIPLE AND cols ARE HERE: `count(*) from information_schema.tables` alone
# (the old gate) passes cleanly if a migration EMPTIES nocodb's metadata while
# leaving all 146 tables standing — table presence is shape, row counts are contents.
# The live values are tiny and exact (1/2/4, 162 columns), so an equality test on
# the triple is safe and catches exactly that failure.

# --- 4.5 no new firing alerts ------------------------------------------------
# Reads kube-prometheus-stack's Prometheus — which is why this plan declares
# shared:[monitoring] and conflicts_with kube-prometheus-stack-91.4.1.
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!
trap 'kill $PF 2>/dev/null' EXIT
sleep 5
RAW=$(curl -s --max-time 10 http://localhost:9090/api/v1/alerts)
printf '%s' "$RAW" | python3 -c "import sys,json; assert json.load(sys.stdin)['status']=='success'" \
  || { echo 'FAIL: Prometheus API did not return status=success — the instrument is down, this gate did NOT measure'; kill $PF; exit 1; }
FIRING=$(printf '%s' "$RAW" | python3 -c "import sys,json; a=json.load(sys.stdin)['data']['alerts']; xs=[x['labels']['alertname'] for x in a if x['state']=='firing' and x['labels']['alertname'] not in ('Watchdog','InfoInhibitor')]; print(len(xs)); [print(' firing:',n) for n in sorted(set(xs))]")
echo "$FIRING"
kill $PF 2>/dev/null; trap - EXIT
# Measured 2026-09-20 pre-change: status=success, 0 non-Watchdog alerts FIRING.
# PASS: first line is 0. FAILS ON: a firing alert, OR Prometheus itself being
# unreachable/mid-restart — the old form (`curl | grep -o '"alertname"'`) printed
# nothing in BOTH cases, so a down Prometheus read exactly like a clean cluster.

# --- 4.6 OPERATOR ACCEPTANCE (the real gate; why this stays attended) --------
# Log in via browser, open EACH existing base, confirm tables/views/records render
# and a test edit saves and survives a page reload. Measured scope 2026-09-20:
# 1 base / 2 models / 4 views — small enough to check exhaustively, so check all of them.
```

## 5) Rollback

**A bare tag revert is NOT a rollback.** Even though this release's own notes
document no new migration, nocodb's knex runner executes unconditionally on
boot; if it wrote anything at all, `2026.08.2`'s code has no guarantee it can
read the result, and upstream documents no downgrade path at any tier.
Rollback is **revert + restore**, exactly the shape `nocodb-calver.md`
established.

```bash
cd /Users/mu/code/cberg-home-nextgen
set -o pipefail

# 0) RE-RESOLVE the DB name. Fresh shell — §2f's $NCDB_NAME is NOT in scope.
#    (The previous draft interpolated it unset here too, so the restore degraded
#    to `psql -U postgres -d` with no argument and errored instead of restoring.
#    Fail-closed, but a non-functional rollback is still not a rollback.)
NCDB_NAME=$(sops -d kubernetes/apps/databases/nocodb/app/secret.sops.yaml \
  | python3 -c "import sys,yaml,urllib.parse as u; s=yaml.safe_load(sys.stdin)['stringData']['NC_DB']; print(u.parse_qs(u.urlsplit(s).query)['d'][0])")
[ -n "$NCDB_NAME" ] || { echo 'ABORT: DB name did not resolve — do NOT run a blind restore'; exit 1; }
DUMP=~/backups/nocodb/nocodb-pre-2026.09.0-$(date +%F).sql.gz    # adjust date if the window crossed midnight
[ -f "$DUMP" ] && gzip -t "$DUMP" || { echo "ABORT: dump $DUMP missing or invalid"; exit 1; }

# 1) revert the bump commit(s), then FENCE the pod before it can serve old code
#    against a new schema.
git revert <bump-commit-sha> && git push
kubectl scale deploy -n databases nocodb --replicas=0
kubectl wait --for=delete pod -n databases -l app.kubernetes.io/name=nocodb --timeout=120s

# --- shared query helper, defined ONCE for steps 2 and 3 -----------------------
ncq() { kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -tAc "$0"' "$1"; }

# 2) PURGE THE SCHEMA, THEN RESTORE.
#
#    *** CORRECTED 2026-09-21 — the previous step 2 made this rollback a
#    GUARANTEED SELF-ABORT. ***
#    The dump is taken (§2f) with `pg_dump --clean --if-exists`, and PostgreSQL's
#    documentation is explicit that --clean emits DROP statements for THE OBJECTS
#    CONTAINED IN THE DUMP ONLY. A table that 2026.09.0's knex migration created is
#    by definition NOT in the pre-upgrade dump, so no DROP is emitted for it and it
#    SURVIVES the restore. Step 3's exact-equality check then compares
#    R_TABLES (= 146 + the new tables) against the 146 baseline, prints
#    "RESTORE INCOMPLETE — counts do not match the pre-upgrade baseline; escalate"
#    and exits 1 — WITH THE APP STILL SCALED TO 0 FROM STEP 1.
#    So the only rollback this plan has aborted, leaving nocodb down, in precisely
#    the scenario it exists for: a migration that ADDED tables. (If the migration
#    added nothing, the old step 2 worked — which is why this never surfaced.)
#    The fix is to return the schema to the same ground the dump was taken against
#    before replaying it.

# 2a) record the CURRENT owner + grants of schema `public` BEFORE dropping it, so
#     2b can put them back exactly and 3b can prove they came back. Measured live
#     2026-09-21: owner `pg_database_owner`; acl
#     {pg_database_owner=UC/pg_database_owner,=U/pg_database_owner,nocodb=UC/pg_database_owner}
#     — PUBLIC holds USAGE, and the app's own role holds USAGE+CREATE.
#     `CREATE SCHEMA public` restores NEITHER: a new schema is owned by whoever
#     created it and carries no grants at all. Losing the app role's grant is the
#     one way a byte-perfect DATA restore still leaves nocodb authenticated but
#     unable to touch its own schema — and it is not safe to assume the dump repairs
#     it, since it was taken without `--create` and may carry no schema-level GRANT.
PRE_OWNER=$(ncq "select pg_get_userbyid(nspowner) from pg_namespace where nspname='public'")
PRE_ACL=$(ncq "select coalesce(nspacl::text,'') from pg_namespace where nspname='public'")
[ -n "$PRE_OWNER" ] || { echo 'ABORT: could not read schema public owner — do not purge blind'; exit 1; }
[ -n "$PRE_ACL" ]   || { echo 'ABORT: could not read schema public ACL — do not purge blind'; exit 1; }
echo "pre-purge public owner=$PRE_OWNER  acl=$PRE_ACL"

# 2b) build the purge DDL FROM THE MEASURED STATE, not from hardcoded role names.
#     The app's role happens to be spelled like the database today; hardcoding that
#     coincidence is exactly how a rollback acquires an object name that does not
#     exist on the night it is needed.
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
printf '%s' "$PURGE_SQL" | grep -q '^DROP SCHEMA public CASCADE;' \
  || { echo 'ABORT: purge DDL did not generate — do not continue'; exit 1; }
# DRY-TESTED on this Mac 2026-09-21 against the LIVE acl above; generated exactly:
#     DROP SCHEMA public CASCADE;
#     CREATE SCHEMA public;
#     ALTER SCHEMA public OWNER TO "pg_database_owner";
#     GRANT USAGE, CREATE ON SCHEMA public TO "pg_database_owner";
#     GRANT USAGE ON SCHEMA public TO PUBLIC;
#     GRANT USAGE, CREATE ON SCHEMA public TO "nocodb";
# i.e. it reproduces the measured ACL exactly, including PUBLIC's USAGE-only grant
# (a blanket `GRANT USAGE, CREATE ... TO PUBLIC` would have WIDENED privileges
# during a rollback). Control: an empty $PRE_ACL emits the DROP/CREATE/ALTER and no
# GRANT lines — but 2a has already aborted on an empty ACL, so that path is unreachable.

# 2c) apply it. One `psql -c` => one transaction, so this is all-or-nothing.
#     Verified live 2026-09-21 that this database holds NO extension outside
#     pg_catalog (only plpgsql, which lives in pg_catalog), so CASCADE drops
#     nocodb's own objects and nothing else. Server is PostgreSQL 16.15.
kubectl exec -n databases deploy/postgresql -- env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -v ON_ERROR_STOP=1 -c "$0"' \
  "$PURGE_SQL" \
  || { echo 'ABORT: schema purge failed — nothing was restored; escalate'; exit 1; }

# 2d) POSITIVE CONTROL for the purge. Measured live 2026-09-21: this database holds
#     146 BASE TABLEs. If the DROP silently did not take effect, this still reads
#     146 and the gate stops here — BEFORE the restore, while the dump is still the
#     untouched source of truth.
PURGED=$(ncq "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")
echo "tables after purge: [$PURGED]  (expect 0; pre-purge was $tables per the baseline)"
[ "$PURGED" = "0" ] || { echo "ABORT: schema not empty after purge (got [$PURGED]) — do NOT restore on top; escalate"; exit 1; }
# An empty $PURGED (dead psql) fails this string compare too — it never equals "0".

# 2e) replay the dump onto the empty schema. Its own `DROP … IF EXISTS` statements
#     are now harmless no-ops, and every CREATE lands on clean ground.
gunzip -c "$DUMP" | kubectl exec -i -n databases deploy/postgresql -- \
  env NCDB="$NCDB_NAME" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$NCDB" -v ON_ERROR_STOP=1' \
  || { echo 'RESTORE FAILED — do NOT scale nocodb back up; escalate to the operator'; exit 1; }
# ON_ERROR_STOP=1 is load-bearing: without it psql reports success after individual
# statements fail, which would leave a partially restored DB looking restored.
# `set -o pipefail` (top of this block) is equally load-bearing on this pipe.

# 3) CONFIRM THE RESTORE BY CONTENTS before bringing the app back
. ~/backups/nocodb/pre-counts.txt
R_TABLES=$(ncq "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")
R_KNEX=$(ncq "select count(*) from xc_knex_migrationsv2")
R_TRIPLE=$(ncq "select (select count(*) from nc_bases_v2)||'/'||(select count(*) from nc_models_v2)||'/'||(select count(*) from nc_views_v2)")
echo "restored tables=$R_TABLES (pre $tables)  knex=$R_KNEX (pre $knex)  triple=$R_TRIPLE (pre $triple)"
[ -n "$R_TABLES" ] && [ "$R_TABLES" = "$tables" ] && [ "$R_KNEX" = "$knex" ] && [ "$R_TRIPLE" = "$triple" ] \
  || { echo 'RESTORE INCOMPLETE — counts do not match the pre-upgrade baseline; escalate'; exit 1; }
# Exact equality here, not >=: a restore is supposed to reproduce the baseline
# exactly. An empty value fails the -n guard rather than matching. THIS TEST IS NOW
# MEANINGFUL: after the 2b-2c purge (proved empty by 2d), the only way to reach 146
# is to have replayed the dump onto an empty schema. Under the old step 2 it could
# only be reached when the migration had added nothing — so it failed exactly when
# it mattered, and passed only when the rollback was not really needed.

# 3b) GRANTS came back. Compares the GRANTEE SET, not the ACL string: the grantor
#     recorded in an ACL entry depends on which role issued the GRANT, so a literal
#     string compare would fail on a correct restore. A MISSING grantee is the real
#     failure — it leaves the app authenticated but unable to touch its own schema.
POST_ACL=$(ncq "select coalesce(nspacl::text,'') from pg_namespace where nspname='public'")
echo "post-restore public ACL: $POST_ACL"
PRE_ACL="$PRE_ACL" POST_ACL="$POST_ACL" python3 -c "
import os, sys
def grantees(acl):
    return {e.split('=')[0] for e in acl.strip('{}').split(',') if '=' in e}
pre, post = grantees(os.environ['PRE_ACL']), grantees(os.environ['POST_ACL'])
missing = pre - post
print('grantees pre:', sorted(pre) or ['(none)'], '-> post:', sorted(post) or ['(none)'])
if missing:
    print('FAIL: schema public lost grantee(s):', sorted(missing)); sys.exit(1)
print('SCHEMA GRANTS RESTORED')
" || { echo "RESTORE INCOMPLETE — re-grant manually before scaling up: GRANT USAGE, CREATE ON SCHEMA public TO <the missing role>; then re-run this gate"; exit 1; }
# FAILS ON: any role present before the purge and absent after. An empty PRE_ACL
# cannot reach here (2a aborts on it), so this gate can never pass vacuously.

# 4) bring nocodb back and confirm it runs the OLD code
kubectl scale deploy -n databases nocodb --replicas=1
kubectl rollout status deploy/nocodb -n databases --timeout=5m
kubectl get pods -n databases -l app.kubernetes.io/name=nocodb \
  -o jsonpath='{.items[0].spec.containers[0].image}{"\n"}'     # expect nocodb/nocodb:2026.08.2
kubectl port-forward -n databases svc/nocodb 18080:8080 >/dev/null 2>&1 & PF=$!
trap 'kill $PF 2>/dev/null' EXIT
sleep 5
curl -s --max-time 10 http://localhost:18080/api/v1/version \
  | python3 -c "import sys,json; v=json.load(sys.stdin)['currentVersion']; print('currentVersion:',v); sys.exit(0 if v=='2026.08.2' else 1)" \
  || { echo 'FAIL: app is not reporting 2026.08.2 after rollback'; kill $PF; exit 1; }
kill $PF 2>/dev/null; trap - EXIT
# OPERATOR: open a base, confirm pre-upgrade data is back and an edit saves.
```

(The scale commands are the one sanctioned direct-cluster action, fencing the
restore; Flux's desired state is restored by the git revert itself. The
`postgresql-data-5g` Longhorn backup from that morning's 03:0x run — verified
present at §2e, stamped 03:08:30Z on 2026-09-20 — is the disaster fallback if
the dump itself is bad. But restoring THAT rolls back every database in the
shared instance, not just nocodb's, and is a last resort coordinated per
`docs/sops/backup.md`.)

## 6) Interference notes

- **File-level collision with `float-tag-pinning` — now declared.** Its Batch B
  names `nocodb` explicitly and its action ("pin to the current running digest
  first, then raise to the newest release as a separate step") rewrites the SAME
  `image:` block in the SAME file, `kubernetes/apps/databases/nocodb/app/helmrelease.yaml`,
  that §3.3 edits. These two must never share a window; `conflicts_with` now says
  so. Note that `float-tag-pinning` carries **no `conflicts_with` and no
  `depends_on` key at all** (verified 2026-09-20) — its own side of this is
  unfixed, and it names four other components that have or will have version
  plans. That is reported to the orchestrator, not edited from here.
  Mitigating fact: it is `status: draft` with `autonomy_override: human-gated`,
  and `window-scheduler.py` only auto-places plans that are
  `vetted`/`scheduled` AND class `AUTO-NIGHT`, so it cannot be auto-scheduled
  today. The exposure is a human co-scheduling them.
- **`kube-prometheus-stack-91.4.1` — declared.** §4.5 reads Prometheus; a
  same-night kps bump takes that instrument down for minutes and the gate would
  measure a restarting stack rather than a clean cluster. **CORRECTED 2026-09-21:**
  the 2026-09-20 draft called this declaration "pre-emptive" because kps was
  "gated behind `depends_on: prometheus-crd-ownership`, so it cannot be placed
  yet". That is no longer true — kps's own frontmatter records that dependency as
  RESOLVED/executed on 2026-09-20, and the `prometheus-crd-ownership` plan file has
  been retired. kps is `status: draft`, `window: null`, and **placeable**, so this
  is a live exclusion, not a theoretical one.
- **Shared `postgresql` instance** (same token `nocodb-calver.md` used). The
  `postgresql` pod itself is not restarted, but the migration runner writes into
  nocodb's database inside it, sharing that instance's CPU/disk with every other
  tenant DB. Measured live 2026-09-21, that instance holds five databases:
  `nocodb`, `oc8`, `pellets`, `postgres`, `sweep_history`.
  **CORRECTED 2026-09-21 — the previous claim "no other OPEN plan writes to this
  instance" was overstated.** `media-audit-durable-output` (`awaiting-go`,
  `sat-attended:2026-10-10`) declares `namespaces: [media, databases]` and
  `touches.resources: "postgres: sweep_history"` — and `sweep_history` is a
  database **inside this same instance**, not a separate server. So a second open
  plan *does* write to this instance. The operational conclusion is unchanged, but
  it rests on two narrower facts, both of which must be re-checked rather than
  assumed: it writes a **different database** (`sweep_history`, not `nocodb`), and
  it is scheduled for a **different night** (10-10 vs. this plan's recommendation
  below). Neither this plan's dump/restore nor its §4 contents gates touch
  `sweep_history`, and vice versa. What remains genuinely exclusive is narrower:
  **no other open plan writes to the `nocodb` database.** `nocodb-calver`,
  `authentik-pg18-lockstep`, `superset-pg-cutover` and `superset-pg-decommission`
  are all `status: executed`; the paperless and paperclip DB plans declare
  `shared: []` against their own dedicated instances. Re-check `--open`
  immediately before scheduling.
- `nocodb-data` PVC is Longhorn RWO but effectively empty (`lost+found` only);
  no storage-class hazard (`longhorn-static`, `Retain`).
- Expected user-visible downtime ~1-3 min (pod replace + migration boot).
  Homepage tile + Authentik forward-auth are unaffected — routing is untouched
  by this plan. (Two HTTPRoutes carry this hostname: `nocodb` and
  `nocodb-authentik-outpost`; neither is edited here.)
- **Release-age cooldown: CLEARED.** The 2026-09-11 draft said "do not run
  before 2026-09-12T11:31 UTC". Measured 2026-09-20, the tag is 234.9h old.
  This constraint is discharged and no longer constrains the window choice.
- **Recommended window (not assigned — `window: null`): `sat-attended:2026-10-17`,
  fallback `sun-attended:2026-10-18`.**
  **RE-DERIVED 2026-09-21 from live `maintenance-plan.py --json`.** The 2026-09-20
  table was wrong in two ways and is replaced wholesale: it recommended
  `sun-attended:2026-10-04` on the evidence "*(empty)* | risk 0/6, 0min/180", but
  that slot holds **`nextcloud-34.0.4`** (`status: vetted`, medium, 75 min, and it
  now carries a recorded operator GO); and its `sun-attended:2026-09-20` row was
  stale. Root cause worth naming so the next author avoids it: in the JSON,
  `scheduled` is a **dict keyed by window id**, not a list — iterating it yields
  slot-id STRINGS, so a membership test written against it finds no plans and every
  slot reads empty.
  Method: `window-scheduler.py` RISK_WEIGHT low=1/medium=2/high=4, capacity_risk 6
  per window, and budget = `duration_min - STEP0_RESERVE_MIN(20)`
  (window-scheduler.py:92 and :270) — so **sat = 70 min, sun = 180 min**, never the
  raw 90/200. This plan adds risk 2 and 45 min. Nightly slots are excluded
  outright: §4.6's acceptance gate is a human browser pass, so this needs an
  **attended** slot.
  | slot | committed (live) | load | verdict for this plan (medium=2, 45 min) |
  |---|---|---|---|
  | `sat-attended:2026-09-26` | wazuh-2xx-edge-coverage (med, 45) | risk 2/6, 45/70 | **45+45=90 > 70 min** |
  | `sun-attended:2026-09-27` | talos-1.14.1 (high, 145) | risk 4/6, 145/180 | **145+45=190 > 180 min** — and a node roll runs every verification against a cluster in motion |
  | `sat-attended:2026-10-03` | external-dns-unowned-cnames (med, 40) + nextcloud-mcp-0.187.1 (med, 30) | risk 4/6, 70/70 | **budget exactly full** |
  | `sun-attended:2026-10-04` | **nextcloud-34.0.4 (med, 75, vetted, operator GO recorded)** | risk 2/6, 75/180 | capacity would fit (120/180, risk 4/6) but **EXCLUDED — rollback-class stacking**, see below |
  | `sat-attended:2026-10-10` | media-audit-durable-output (low, 45) | risk 1/6, 45/70 | **45+45=90 > 70 min** |
  | `sun-attended:2026-10-11` | jellyfin-12.1 (high, 60) | risk 4/6, 60/180 | capacity would fit (105/180, risk 6/6 — at the cap) but **EXCLUDED — rollback-class stacking** |
  | `sat-attended:2026-10-17` | *(empty — verified against the live `scheduled` dict)* | risk 0/6, 0/70 | **FITS: risk 2/6, 45/70 min — RECOMMENDED** |
  | `sun-attended:2026-10-18` | *(empty)* | risk 0/6, 0/180 | fits (risk 2/6, 45/180) — fallback if 10-17 fills |
- **Why not `sun-attended:2026-10-04`, even though 105 min are free there.** That
  slot holds `nextcloud-34.0.4`, which is `rollback_class: backup-restore` +
  `capability_change: true` — as is this plan. Two backup-restore rollbacks in one
  window leaves no rollback capacity for either; `nextcloud-34.0.4`'s own `window:`
  note records this as "the same no-rollback-capacity stacking the reconciler
  already rejected for jellyfin+frigate", which is why it avoided
  `sun-attended:2026-10-11`. **Nextcloud has the recorded GO and keeps 10-04**;
  this plan moves. The same reasoning excludes `sun-attended:2026-10-11`
  (jellyfin-12.1: high, backup-restore, capability_change). Both are now declared
  in `conflicts_with`, so the scheduler enforces it rather than relying on this
  prose.
- Re-run the derivation immediately before scheduling: three of the occupants above
  are `awaiting-go`/`draft` and can still move, and `sat-attended:2026-10-17` is
  only empty until something else claims it.
- One-way boundary: once §4.6's operator acceptance gate passes and the window
  closes, **the pre-upgrade dump is the only way back** — keep
  `~/backups/nocodb/nocodb-pre-2026.09.0-<date>.sql.gz` **and**
  `~/backups/nocodb/pre-counts.txt` (§5 step 3 compares against it) until at
  least the next nightly Longhorn backup after sign-off.
- Attended preferred: the acceptance gate (bases/tables render, edit saves) is
  a human check, same as `nocodb-calver.md`.
