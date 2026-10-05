---
plan_id: pgvector-fleet-0.8.7
component: pgvector                   # same-image fleet: one image, five pins (3 servers + 2 client-only Jobs)
pr: null                              # coverage.py direct-bump lane — no Renovate PR exists for any member
kind: image
current: "pgvector/pgvector:0.8.6-pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b on 5 pins: deployment/postgresql (databases, shared), helmrelease/affine-pg + helmrelease/sure-pg (office), job/oc8-db-init-v1 + job/sweep-history-init-v9 (databases)"
target: "pgvector/pgvector:0.8.7-pg16@sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a on all 5 pins (Jobs renamed oc8-db-init-v1a / sweep-history-init-v9a)"
update_type: patch
risk: low                             # MEASURED, not assumed (§1.2): the target image carries the
                                      # IDENTICAL PostgreSQL build (PG_VERSION=16.15-1.pgdg12+2, same as
                                      # live `select version()`), so the server binary and the on-disk
                                      # format do not change; only vector.so + its SQL scripts move.
                                      # 0.8.6->0.8.7 upgrade SQL is COMMENT-only. This plan deliberately
                                      # does NOT run ALTER EXTENSION (house precedent: 0.8.1->0.8.6
                                      # left catalogs alone). The residual risk is the ~30-60s restart
                                      # of the SHARED instance (sweep_history, oc8, nocodb, pellets) —
                                      # blast radius, not change risk; §6.
est_duration_min: 45                  # pre-checks+baseline 9 · affine-pg leg 7 · sure-pg leg 7 ·
                                      # dumps 4 · shared postgresql leg 10 · init-Job leg 5 · slack 3 (conn.sh polls up to 10 min per leg; typical < 1)
needs_reboot: false
touches:
  namespaces: [databases, office, ai]
  resources:
    - deployment/postgresql                 # databases — image bump; maxSurge0/maxUnavailable1 = Recreate-equivalent
    - pvc/postgresql-data-5g                # remounted by the new pod; NOT modified, NOT deleted
    - helmrelease/affine-pg                 # office — app-template 5.1.0, strategy Recreate
    - deployment/affine-pg
    - pvc/affine-pg-data                    # remounted; NOT modified, NOT deleted
    - helmrelease/sure-pg                   # office — app-template 5.1.0, strategy Recreate
    - deployment/sure-pg
    - pvc/sure-pg-data                      # remounted; NOT modified, NOT deleted (PV reclaim is Delete — see §6)
    - job/oc8-db-init-v1                    # pruned by Flux, replaced by job/oc8-db-init-v1a (re-runs idempotent bootstrap)
    - job/sweep-history-init-v9             # pruned by Flux, replaced by job/sweep-history-init-v9a (re-runs idempotent bootstrap)
    - kustomization/oc8-db                  # wait:true — gates kustomization/oc8 (ai) via dependsOn
    - database/sweep_history@postgresql     # bootstrap re-run: DROP+ADD CHECK constraint in one txn, IF NOT EXISTS DDL, GRANTs
    - database/oc8@postgresql               # bootstrap re-run: guarded CREATE ROLE/DATABASE, ALTER ROLE PASSWORD, GRANTs
    # consumers that lose their DB connection for the restart and must reconnect in-process (asserted in §4):
    - deployment/affine                     # office
    - deployment/sure-web                   # office
    - deployment/sure-worker                # office
    - deployment/nocodb                     # databases (shared instance)
    - deployment/oc8-backend                # ai (shared instance)
    - deployment/oc8-worker
    - deployment/oc8-ingestion-worker
    - deployment/oc8-scheduler
    - deployment/sweep-dashboard            # monitoring (reads sweep_history)
    - deployment/media-dashboard            # media (reads sweep_history)
    - cronjob/sweep-heartbeat               # databases, 17 */6 * * * timeZone Europe/Berlin (00:17/06:17/12:17/18:17) — must not run during the shared restart (§6)
  shared: [postgresql, monitoring]          # postgresql = the shared databases/postgresql instance (same token
                                            # nocodb-2026.09.1 uses, so the scheduler sees the intersection).
                                            # monitoring = §4 reads Prometheus. No gateway/DNS/CNI/storage-class
                                            # change; three Longhorn volumes are only remounted by their own pod.
depends_on: []
conflicts_with:
  - app-template-5.2.1                # vetted, nightly:2026-10-09. Bumps the chart on 80 app-template HRs
                                      # INCLUDING affine-pg and sure-pg (same files
                                      # office/{affine,sure}/app/postgres-helmrelease.yaml) and rolls them.
                                      # Two edits to one file in one slot, and its SAME_GEN gate would read
                                      # this plan's rolls as GEN_CHANGED.
  - helm-drift-detection              # its §4 asserts Helm revisions unchanged across all releases; this
                                      # plan upgrades affine-pg and sure-pg.
  - nocodb-2026.09.1                  # nocodb lives on the shared databases/postgresql (shared: [postgresql]);
                                      # its verification needs that instance up and its §4.5 gate is scoped
                                      # to ns databases — a shared-DB restart in the same slot confounds both.
  - redis-fleet-8.10.2                # restarts sure-redis + sure-worker; never stack two Sure backend
                                      # restarts in one slot (which one broke sidekiq becomes unanswerable).
  - flux-fleet-0.60.0                 # Flux controller upgrade underneath this plan's GitOps legs.
  - flux-reconciler-impersonation     # changes WHO applies the Kustomizations/HelmReleases this plan relies on.
  - flux-oci-chart-sources            # rewrites HR chart sources (incl. app-template for affine-pg/sure-pg).
  - sure-0.7.5                        # helm upgrade re-runs sure-migrate (db:prepare) against sure-pg;
                                      # never restart sure-pg under it. Listed back in that plan.
  - kube-prometheus-stack-91.9.0      # vetted, nightly:2026-10-08, exclusive:true. §4 reads Prometheus
                                      # (CONTROL gates); the window's instrument must not move in the same slot.
  - flux-distribution-2.9.6           # Flux controller upgrade underneath this plan's four GitOps legs.
  - nextcloud-fleet-35.0.1            # rolls office workloads; never stack with the affine-pg/sure-pg legs
                                      # (two office restarts in one slot confound §4.A/B attribution).
  - longhorn-1.13.0                   # storage engine upgrade; three RWO Longhorn volumes are re-attached here.
                                      # (talos-linux-1.14.2 / talconfig-multidoc-migration are exclusive:true
                                      # on their own side, which already keeps them out of this slot.)
exclusive: false
security_ref: F-d6d47945              # OPEN accepted security finding on the 0.8.6-pg16 tag whose remedy is
                                      # "newer upstream tag available, bump the image" — this plan IS that
                                      # bump. Detail lives on the record only. (F-bb62d310, the earlier
                                      # "already newest" row, is resolved.) Related, NOT addressed here:
                                      # F-fa3325bc (accepted register row on the same tag; out of this
                                      # plan's scope -- the next sweep re-measures it on 0.8.7). Whether 0.8.7 clears either is for the next sweep to
                                      # MEASURE, not for this plan to claim.
capability_change: false              # same server binary, same extension catalog version (no ALTER
                                      # EXTENSION), same SQL surface; bug-fix-only shared library.
rollback_class: git-revert            # nothing forward-only happens: datadir untouched (same PG build), no
                                      # catalog change (ALTER EXTENSION explicitly excluded — §1.3), the two
                                      # bootstrap re-runs are idempotent. Dumps are taken anyway (backup_gate).
backup_gate: "Completed Longhorn Backup CR < 26h for postgresql-data-5g, pvc-27866fc8-77df-4fe6-8397-e69f3fa0fa7d (affine-pg-data) and pvc-bd4b4e52-0a71-4690-aade-ad99b1cddfe6 (sure-pg-data) (§2.4), PLUS in-window logical dumps taken in §3.4 BEFORE the shared-instance leg: pg_dump -Fc of sweep_history, oc8, nocodb, pellets and pg_dumpall --globals-only, each validated by local pg_restore -l TABLE DATA count against the live table count (sweep_history=11, oc8=71, nocodb=157, pellets=10 measured 2026-10-03)."
finding_refs: [F-c10b4143, F-ed3c402c, F-e48a1da6, F-96a49661, F-9e3a8bdd]
                                      # the five open version findings for this bump, one per pin
                                      # (verified 2026-10-05 with `finding show`): postgresql, affine-pg,
                                      # sure-pg, oc8-db-init-v1, sweep-history-init-v9 — all
                                      # "0.8.6-pg16 -> 0.8.7-pg16 (patch)". The plan-or-page pass joins on these.
review: ready-for-go@2026-10-05   # plan-reviewer 2026-10-05: needs-fix x2 (bookkeeping, absence gates, sweep guard, epochs) -> fixed -> second delta ready-for-go; leg-A cd nit applied
status: vetted
window: "nightly:2026-10-16"   # scheduled 2026-10-05: AUTO-NIGHT (image graduated); alone (45 min); EVEN date = not a 48h sweep night (sweeps land 02:00Z on odd dates), so jit.sh will not stop leg C
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/immutable-job-image-bumps.md     # §4a live-DB checklist governs the two Job renames
  - docs/sops/backup.md
  - docs/sops/longhorn-rwo-multi-attach.md     # why postgresql uses maxSurge 0 — do NOT "fix" it to Recreate
  - docs/sops/storage-safety.md                # read-only relevance: no PVC/PV/Volume is deleted
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-03"
premises:
  # Read-verb only (kubectl get). Each was run 2026-10-03 and returned exactly the expected value.
  - id: shared-postgresql-current
    why: >-
      `current:` claims the shared instance runs the 0.8.6 digest with the maxSurge 0 /
      maxUnavailable 1 strategy and 1 ready replica. If the nightly lane already moved it, leg C is
      a no-op and its sed matches nothing; if the strategy drifted to surge, the roll can deadlock on
      Multi-Attach. Prints something else and fails.
    run: kubectl get deploy -n databases postgresql -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.strategy.rollingUpdate.maxSurge} {.spec.strategy.rollingUpdate.maxUnavailable} {.status.readyReplicas}'
    expect_exact: pgvector/pgvector:0.8.6-pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b 0 1 1
  - id: office-pg-current
    why: Same claim for affine-pg then sure-pg (order of the -o list). A moved pin drops that leg.
    run: kubectl get deploy -n office affine-pg sure-pg -o jsonpath='{.items[*].spec.template.spec.containers[0].image}'
    expect_exact: pgvector/pgvector:0.8.6-pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b pgvector/pgvector:0.8.6-pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b
  - id: office-pg-recreate
    why: >-
      Both app-template DBs mount an RWO Longhorn PVC with replicas 1; a RollingUpdate would surge a
      second pod onto the held volume. The rendered Deployment, not the HR, is what counts.
    run: kubectl get deploy -n office affine-pg sure-pg -o jsonpath='{.items[*].spec.strategy.type}'
    expect_exact: Recreate Recreate
  - id: office-pg-hr-ready
    why: A failing HR would make leg A/B land on a broken release and mis-attribute the failure.
    run: kubectl get hr -n office affine-pg sure-pg -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")].status}'
    expect_exact: True True
  - id: pv-reclaim
    why: >-
      Records the reclaim policy of the three data PVs (postgresql-data-5g, affine-pg-data,
      sure-pg-data, in that order). sure-pg-data is a dynamic `longhorn` PV with reclaim Delete — this
      plan never deletes a PVC, but the executor must know a PVC delete there would destroy Sure's
      ledger. A change in either direction means someone touched storage since authoring: stop and look.
    run: kubectl get pv postgresql-data-5g pvc-27866fc8-77df-4fe6-8397-e69f3fa0fa7d pvc-bd4b4e52-0a71-4690-aade-ad99b1cddfe6 -o jsonpath='{.items[*].spec.persistentVolumeReclaimPolicy}'
    expect_exact: Retain Retain Delete
  - id: longhorn-volumes-healthy
    why: A degraded replica set under a database restart turns a 30s blip into a rebuild under load.
    run: kubectl get volumes.longhorn.io -n storage postgresql-data-5g pvc-27866fc8-77df-4fe6-8397-e69f3fa0fa7d pvc-bd4b4e52-0a71-4690-aade-ad99b1cddfe6 -o jsonpath='{.items[*].status.robustness}'
    expect_exact: healthy healthy healthy
---

# pgvector fleet 0.8.6-pg16 -> 0.8.7-pg16

## 1. Summary & why held

**What changes:** one image digest in five places. Three are database **servers**: the shared
`databases/postgresql` (holds `sweep_history`, `oc8`, `nocodb`, `pellets`), `office/affine-pg` and
`office/sure-pg`. Two are one-shot bootstrap **Jobs** (`oc8-db-init-v1`, `sweep-history-init-v9`)
that use the image **only as a `psql` client**. A Job's `.spec.template` is immutable, so those two
are renamed (`v1a`, `v9a`), and the rename **re-runs** their bootstrap against live data. That makes
them a `docs/sops/immutable-job-image-bumps.md` §4a case.

**Why it was held:** coverage gate G3 could not fetch the release notes ("unavailable"). Earned
autonomy has no track record (0 green / 0 revert in 90d). There is no Renovate PR. There **is** a
security reason to land it: the open, accepted finding `F-d6d47945` (`security_ref`) records that the
current 0.8.6-pg16 tag has fixable image findings and that a newer upstream tag exists. This bump is
the remedy that finding names. The detail stays on the DB record. Whether the 0.8.7 rebuild actually
clears it is for the next sweep to measure; this plan does not claim it. The hold itself was mostly a
**false positive** on evidence availability: once the evidence is read, the change is a bug-fix
library swap. Risk stays `low`. The care below is for the shared-instance restart, not for the version.

### 1.1 Upstream evidence (primary sources, read 2026-10-03)

- `CHANGELOG.md` @ v0.8.7 (2026-10-01): *"Fixed buffer overflow with IVFFlat index build"* and
  *"Fixed error with `avg` aggregate when no matching rows"*. No upgrade, reindex or ALTER
  instructions.
- `git compare v0.8.6...v0.8.7` has 62 commits. They are hardening, compiler-warning fixes, an HNSW
  INSERT-vs-VACUUM duplicate-neighbour race fix (#1010), HNSW level-selection zero handling
  (#1023), new dimension checks on index insert, and `COMMENT ON` for every object (#1013).
  `src/hnsw.h` and `src/ivfflat.h` change only in-memory structs and function signatures
  (`HnswTypeInfo` / `IvfflatTypeInfo` gain a `dimensions` callback). **No on-disk page struct or
  metapage layout changed**, so existing HNSW/IVFFlat indexes stay readable without a REINDEX.
- The Makefile adds `-ffp-contract=fast` (FMA). Distance results may differ in the last float bit.
  This is irrelevant to approximate-NN indexes and to every check below: the §4 expression checks
  use values that are exact in float32.
- `sql/vector--0.8.6--0.8.7.sql` consists **only** of `COMMENT ON FUNCTION/TYPE/OPERATOR/AGGREGATE`
  statements (296 lines, no DDL). `vector.control` has `default_version = '0.8.7'`. **No downgrade
  script `vector--0.8.7--0.8.6.sql` exists.**

### 1.2 Same PG build, so no on-disk change (measured)

The amd64 image config of `0.8.7-pg16` (index digest `sha256:7b822b0a…`, Docker Hub,
`last_updated 2026-10-01`, amd64 + arm64) carries `PG_MAJOR=16`, `PG_VERSION=16.15-1.pgdg12+2`. The
live shared instance reports `PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2)`. **The server binary is
byte-for-byte the same Debian package**, so the data directory format cannot change, and the
rollback image reads the same datadir. Only `vector.so` and `/usr/share/postgresql/16/extension/vector*`
differ.

### 1.3 Does 0.8.7 need `ALTER EXTENSION vector UPDATE` per database? No, and this plan forbids it

- The shared library is loaded by `module_pathname = '$libdir/vector'`. The catalog functions bind
  by C symbol, so a database whose catalog says 0.8.1 or 0.8.6 runs on the 0.8.7 `.so`. This is the
  **live state today**: the shared `postgres` DB and `affine` are at catalog **0.8.1** on the 0.8.6
  library, and `oc8` / `sure` are at **0.8.6**. The 0.8.1 -> 0.8.6 bump (`0c13e773`, `5980365f`)
  deliberately left catalogs alone, and they have run that way since 2026-08-18.
- `ALTER EXTENSION … UPDATE TO '0.8.7'` would only add comments (§1.1). It brings no functional gain.
- **It is the one step that would break rollback.** With no downgrade script, a catalog at 0.8.7 on a
  rolled-back 0.8.6 image has no `vector--0.8.7.sql` on disk. `pg_dump`/restore and any later
  `ALTER EXTENSION` path then fail. Leaving the catalog alone is what keeps
  `rollback_class: git-revert` honest, and §4 asserts the catalog column is **unchanged**.
- Note: `pg_extension_update_paths` will now show an available update. That is expected, not drift.
  Catalog alignment, if anyone ever wants it, is a separate decision. It is not window work.

### 1.4 Live inventory the gates are built on (2026-10-03)

| Instance | DB | catalog extversion | vector cols | hnsw/ivfflat idx | rows in vector cols |
|---|---|---|---|---|---|
| databases/postgresql | postgres | 0.8.1 | 0 | 0 | — |
| | oc8 | 0.8.6 | 2 (`kb_chunk`, `memory_record`, 768d) | 0 | 0 / 0 |
| | nocodb, pellets, sweep_history | (none) | 0 | 0 | — |
| office/affine-pg | affine | 0.8.1 | 5 (1024d) | 5 hnsw (all 16 kB) | 2 (`ai_workspace_embeddings`), rest 0 |
| office/sure-pg | sure | 0.8.6 | 1 (`vector_store_chunks`, 768d) | 0 | 0 |

Vector data is almost empty. The two affine rows are zero vectors: `embedding <=> embedding` returns
NaN, and the HNSW cosine scan returns 0 rows for them on 0.8.6 today. So a "KNN returns results"
check on real data **cannot be made to fail meaningfully**, and §4 does not use one. The contents
assertions are instead: exact per-table row counts for every DB, a per-column vector digest, and an
expression probe that exercises the new library in every DB that has the extension.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). Every command is read-only.

```bash
cd /Users/mu/code/cberg-home-nextgen
mkdir -p /tmp/pgv-87 && cd /tmp/pgv-87

# 2.1 Premises (frontmatter) — all must PASS
/Users/mu/code/cberg-home-nextgen/.venv/bin/python3 /Users/mu/code/cberg-home-nextgen/runbooks/plan-premises.py pgvector-fleet-0.8.7

# 2.2 Target digest still what this plan pins (upstream re-pushes pg16 tags in place)
curl -s "https://hub.docker.com/v2/repositories/pgvector/pgvector/tags/0.8.7-pg16" | python3 -c "import sys,json; print(json.load(sys.stdin)['digest'])"
# PASS: sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a
# FAIL (different digest): upstream rebuilt the tag -> re-verify PG_VERSION (§1.2) before using the new digest; do not silently swap it.

# 2.3 Flux sane for the five Kustomizations involved
flux get ks -A | grep -E '^(databases|office|ai)[[:space:]]+(postgresql|sweep-history|oc8-db|affine|sure|oc8)[[:space:]]'
# PASS: six rows, all READY True. Any False -> stop (a broken ks would swallow this plan's commit).

# 2.4 Backup gate: a Completed Longhorn Backup CR < 26h for each of the three volumes
kubectl get backups.longhorn.io -n storage -o json | python3 -c "
import sys,json,datetime as dt
want={'postgresql-data-5g','pvc-27866fc8-77df-4fe6-8397-e69f3fa0fa7d','pvc-bd4b4e52-0a71-4690-aade-ad99b1cddfe6'}
now=dt.datetime.now(dt.timezone.utc); best={}
for b in json.load(sys.stdin)['items']:
    v=b.get('status',{}).get('volumeName'); s=b.get('status',{}).get('state'); t=b.get('status',{}).get('backupCreatedAt')
    if v in want and s=='Completed' and t:
        t=dt.datetime.fromisoformat(t.replace('Z','+00:00')); best[v]=max(best.get(v,t),t)
bad=[v for v in want if v not in best or (now-best[v]).total_seconds()>26*3600]
for v in sorted(want): print(v, best.get(v))
print('BACKUP_GATE_PASS' if not bad else 'BACKUP_GATE_FAIL '+' '.join(sorted(bad)))"
# PASS: BACKUP_GATE_PASS. FAIL names the stale/missing volume -> stop (do not substitute lastBackupAt; it lags, docs/sops/backup.md).

# 2.5 Not inside the heartbeat minute: sweep-heartbeat is "17 */6 * * *" with timeZone Europe/Berlin
#     (verified live 2026-10-05), i.e. 00:17, 06:17, 12:17, 18:17 Berlin.
TZ=Europe/Berlin date '+%H:%M'
# The shared-instance leg (§3.5) must not START between hh:15 and hh:20 of 00/06/12/18 Berlin.
# Nightly 03:30 is clear of every heartbeat; jit.sh enforces this mechanically.

# 2.6 Shared-instance quiet gate (jit.sh). Written here, run here AND again immediately before the
#     leg-C push (§3.5). Read-only. STOPs on: an unfinished sweep_cycles row started < 6 h ago; ANY
#     sweep_cycles start or sweep_findings.last_seen within 30 min (finished_at alone is NOT proof a
#     sweep ended — every specialist's FindingsWriter.close() stamps it, findings_writer.py
#     _finalise_cycle_row, so the row reads finished after the first of six specialists); a non-idle
#     sweep_writer backend; a sweep script running on this Mac (sweep-run/health-check/
#     check-all-versions/slo-check/render-board); any open `port-forward … postgresql`; a
#     transaction older than 300 s; a 48h-sweep night at >= 03:55 Berlin (the 04:00 cron sweep is
#     due: last cron cycle started >= 40 h ago — cron cycles land 02:00Z every other day, measured
#     10-01/10-03/10-05); the heartbeat minute (hh:15-20 of 00/06/12/18 Berlin); or SWEEP_PG_DSN
#     still set in this shell. Fails CLOSED on a psql error or unparsable output.
cat > jit.sh <<'JIT'
# Leg-C just-in-time gate. Read-only. Prints JIT_GO or JIT_STOP <reasons>; exit 0 only on GO.
# sweep_cycles.finished_at is NOT a "sweep is over" signal: every specialist's FindingsWriter.close()
# stamps it (runbooks/lib/findings_writer.py _finalise_cycle_row), so it reads finished after the
# first of six specialists. Hence the process, recent-write and writer-session checks below.
r=$(kubectl exec -i -n databases deploy/postgresql -- sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d sweep_history -tA -F"|"' <<'SQL'
select
  (select count(*) from sweep_cycles where finished_at is null and started_at > now() - interval '6 hours'),
  (select coalesce(floor(extract(epoch from now() - max(started_at))/3600)::int, 999) from sweep_cycles where trigger = 'cron'),
  (select count(*) from pg_stat_activity where datname is not null and pid <> pg_backend_pid() and now() - xact_start > interval '300 seconds'),
  (select (select count(*) from sweep_cycles where started_at > now() - interval '30 minutes')
        + (select count(*) from sweep_findings where last_seen > now() - interval '30 minutes')),
  (select count(*) from pg_stat_activity where usename = 'sweep_writer' and state <> 'idle' and pid <> pg_backend_pid());
SQL
) || { echo "JIT_STOP psql-failed (cannot prove the gate -> stop)"; exit 2; }
echo "raw=$r"
IFS='|' read -r unf hrs longtx recent wr <<RAW
$r
RAW
case "$unf$hrs$longtx$recent$wr" in ''|*[!0-9]*) echo "JIT_STOP unparsable '$unf|$hrs|$longtx|$recent|$wr'"; exit 2;; esac
[ -n "$wr" ] || { echo "JIT_STOP unparsable '$unf|$hrs|$longtx|$recent|$wr'"; exit 2; }
hm=$(TZ=Europe/Berlin date '+%H%M'); why=''
[ "$unf" -gt 0 ] && why="$why unfinished-sweep-cycle=$unf"
[ "$longtx" -gt 0 ] && why="$why long-txn=$longtx"
[ "$recent" -gt 0 ] && why="$why sweep-write-within-30min=$recent"
[ "$wr" -gt 0 ] && why="$why active-sweep_writer-session=$wr"
procs=$(pgrep -fl '[s]weep-run\.py|[h]ealth-check\.py|[c]heck-all-versions\.py|[s]lo-check\.py|[r]ender-board\.py')
[ -n "$procs" ] && why="$why sweep-process-on-mac"
pf=$(pgrep -fl '[p]ort-forward.*postgresql')
[ -n "$pf" ] && why="$why postgresql-port-forward-open"
# Sweep night = the 48h cron sweep (04:00 Berlin) is due tonight: last cron cycle started >= 40h ago.
if [ "$hrs" -ge 40 ] && [ "$hm" -ge 0355 ] && [ "$hm" -lt 0600 ]; then why="$why sweep-night-clock=$hm(last-cron-sweep-${hrs}h-ago)"; fi
# Heartbeat: sweep-heartbeat is "17 */6 * * *" timeZone Europe/Berlin = 00:17/06:17/12:17/18:17 Berlin.
case "$(TZ=Europe/Berlin date '+%H')" in 00|06|12|18) m=$(TZ=Europe/Berlin date '+%M'); [ "${m#0}" -ge 15 ] && [ "${m#0}" -le 20 ] && why="$why heartbeat-minute";; esac
[ -n "$(env | grep '^SWEEP_PG_DSN=')" ] && why="$why SWEEP_PG_DSN-set-in-this-shell"
if [ -n "$why" ]; then echo "JIT_STOP$why"; [ -n "$procs" ] && echo "$procs"; [ -n "$pf" ] && echo "$pf"; exit 1; fi
echo "JIT_GO clock=$hm last-cron-sweep=${hrs}h-ago unfinished=0 long-txn=0 recent-writes=0 writer-sessions=0 procs=none"
JIT
bash jit.sh
# PASS: "JIT_GO clock=... unfinished=0 long-txn=0 recent-writes=0 writer-sessions=0 procs=none", exit 0.
# FAIL shapes (all dry-run 2026-10-05 on scratch copies with injected values):
#   "JIT_STOP unfinished-sweep-cycle=1 sweep-write-within-30min=3 active-sweep_writer-session=1
#    sweep-night-clock=0402(last-cron-sweep-44h-ago)" exit 1;
#   "JIT_STOP sweep-process-on-mac" + the matching process line (a dummy `sh -c '...; : sweep-run.py'`) exit 1;
#   "JIT_STOP unparsable '0|x|0|0|0'" and "JIT_STOP unparsable '0|6|0||'" (short row) exit 2;
#   "JIT_STOP psql-failed" exit 2. Live run 2026-10-05 10:57 printed: raw=0|6|0|0|0 / JIT_GO.
# Note: one STALE unfinished cycle exists in the table (older than 6 h); the 6 h bound is why it does not block.
```

**2.7 The window agent's OWN `SWEEP_PG_DSN` port-forward targets this instance.** Finish any
Step-0 writes first (`window_runs`, `component_autonomy`, `plan_executions`). Then run
`sweep_pg_dsn_down` in every shell that sourced it **before** §3.5 starts. No shell may hold the DSN
(or its port-forward) open across the §3.5 push and the restart: `jit.sh` refuses to print `JIT_GO`
while `SWEEP_PG_DSN` is set in the running shell. **Between the §3.5 push and the end of §4.C, write
nothing to `sweep_history`** — no `plan_executions`, no `window_runs`, no `component_autonomy`, no
`finding` edits. Record this plan's outcome only after §4.C passes, from a freshly sourced DSN
(`sweep_pg_dsn_up`), and run `sweep_pg_dsn_down` again before any commit. The forward dies with the
pod, and a write in flight during the restart errors out (it is not lost silently).

## 3. Steps

All edits are on `main` in the shared worktree. Commit with `git commit --only <paths>`. Never
commit from a shell that has `SWEEP_PG_DSN` sourced (it breaks the pre-commit gate). After every
commit, run `git log -1 --format=%s` and `git show --stat HEAD` and confirm both are yours before
pushing. Every `sed` below was dry-run on scratch copies on macOS (BSD sed) on 2026-10-03. The
resulting diff is quoted under each step.

### 3.0 Silence + update marker (application-update SOP Step 1)

```bash
cd /Users/mu/code/cberg-home-nextgen
runbooks/update-marker.sh add pgvector databases 2 "pgvector 0.8.6->0.8.7 fleet (shared postgresql restart)"
runbooks/update-marker.sh add affine-pg office 2 "pgvector 0.8.6->0.8.7"
runbooks/update-marker.sh add sure-pg office 2 "pgvector 0.8.6->0.8.7"
```

Every DB alert in scope has `for: >= 5m` (e.g. `SurePostgresDown` `for: 5m`). A Recreate takes
~30-60 s, so **no Alertmanager silence is needed**. A silence would also blind the §4 CONTROL gates.

### 3.1 Baseline (BEFORE) — the contents the gates compare against

```bash
cd /tmp/pgv-87
cat > counts.sh <<'EOF'
for d in $(psql -U "$POSTGRES_USER" -d postgres -tAc "select datname from pg_database where datallowconn and not datistemplate order by 1"); do
  psql -U "$POSTGRES_USER" -d "$d" -tA -F'|' -c "select current_database(), table_schema||'.'||table_name, (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text::bigint from information_schema.tables where table_schema not in ('pg_catalog','information_schema') and table_type='BASE TABLE' order by 2"
done
EOF
cat > vec.sh <<'EOF'
d="$1"
psql -U "$POSTGRES_USER" -d "$d" -tA -F'|' -c "select 'EXPR', current_database(), extversion, (select default_version from pg_available_extensions where name='vector'), (select avg(v)::text from (values ('[1,2]'::vector),('[3,4]'::vector)) t(v)), ('[1,0]'::vector <=> '[0,1]'::vector), ('[0,0]'::vector <-> '[3,4]'::vector) from pg_extension where extname='vector'"
psql -U "$POSTGRES_USER" -d "$d" -tA -F'|' -c "select 'VEC', a.attrelid::regclass::text, (xpath('/row/h/text()', query_to_xml(format('select count(*)::text || chr(58) || md5(coalesce(string_agg(%I::text, chr(10) order by %I::text), chr(69))) as h from %s', a.attname, a.attname, a.attrelid::regclass), false, true, '')))[1]::text from pg_attribute a join pg_type t on t.oid=a.atttypid join pg_class c on c.oid=a.attrelid where c.relkind='r' and t.typname in ('vector','halfvec','sparsevec') and a.attnum>0 and not a.attisdropped order by 2"
EOF
snap() {  # $1 = before|after
  kubectl exec -i -n databases deploy/postgresql -- sh < counts.sh > "counts-shared-$1.txt"
  kubectl exec -i -n office deploy/affine-pg -- sh < counts.sh > "counts-affine-$1.txt"
  kubectl exec -i -n office deploy/sure-pg -- sh < counts.sh > "counts-sure-$1.txt"
  kubectl exec -i -n databases deploy/postgresql -- sh -s postgres < vec.sh >  "vec-shared-$1.txt"
  kubectl exec -i -n databases deploy/postgresql -- sh -s oc8      < vec.sh >> "vec-shared-$1.txt"
  kubectl exec -i -n office deploy/affine-pg -- sh -s affine < vec.sh > "vec-affine-$1.txt"
  kubectl exec -i -n office deploy/sure-pg   -- sh -s sure   < vec.sh > "vec-sure-$1.txt"
}
snap before
wc -l counts-*-before.txt; cat vec-*-before.txt

# Consumer-presence baseline: (datname|usename|backends-newer-than-postmaster|postmaster-epoch)
cat > pairs.sql <<'SQL'
select datname||'|'||usename||'|'||count(*) filter (where backend_start > pg_postmaster_start_time())||'|'||extract(epoch from pg_postmaster_start_time())::bigint
from pg_stat_activity where datname is not null and usename is not null and pid <> pg_backend_pid()
group by datname, usename order by 1;
SQL
kubectl exec -i -n databases deploy/postgresql -- sh -c 'psql -X -U "$POSTGRES_USER" -d postgres -tA' < pairs.sql > pairs-shared-before.txt
kubectl exec -i -n office deploy/affine-pg  -- sh -c 'psql -X -U "$POSTGRES_USER" -d postgres -tA' < pairs.sql > pairs-affine-pg-before.txt
kubectl exec -i -n office deploy/sure-pg    -- sh -c 'psql -X -U "$POSTGRES_USER" -d postgres -tA' < pairs.sql > pairs-sure-pg-before.txt
cat pairs-*-before.txt
# Sure positive in-app DB query baseline (§4.B compares against this line)
kubectl exec -n office deploy/sure-web -c web -- sh -c 'timeout 90 bin/rails runner "puts \"SURE_DB_OK families=#{Family.count} accounts=#{Account.count}\"" 2>&1 | tail -1' | tee sure-app-before.txt
# Presence gate used by §4.A/B/C. Push epochs come from FILES (/tmp/pgv-87/push-{a,b,c}.epoch, written
# by the push line), never from shell variables. Dry-run 2026-10-05: PASS with a baseline whose
# postmaster epoch was set older; FAIL "postmaster=X ... before=X" (same postmaster = no restart),
# FAIL "push=<now>" (postmaster older than the push), "CONN_FAIL bad-push-epoch-file" for an empty and
# for a missing file, and earlier "missing: ghost|ghost" / "empty-baseline" — all exit non-zero.
cat > conn.sh <<'CONN'
# Consumer presence gate. Usage: sh conn.sh <push-epoch-file> <pairs-before-file> <ns> <deploy>
# PASS needs ALL of: (1) the push epoch file holds a number; (2) the postmaster started AFTER that push
# AND differs from (is newer than) the postmaster epoch recorded in field 4 of the BEFORE file — proof
# of a restart independent of the push clock; (3) every REQUIRED (datname|usename) pair of the BEFORE
# baseline has >=1 backend newer than the new postmaster. Polls ${TRIES:-20} x 30 s (10 min max).
# pellets|pellets (Grafana datasource pool) is informational, see §4.C.
push=$(cat "$1" 2>/dev/null); base=$2; ns=$3; dp=$4
case "$push" in ''|*[!0-9]*) echo "CONN_FAIL bad-push-epoch-file '$1' content='$push'"; exit 2;; esac
oldpm=$(head -1 "$base" 2>/dev/null | cut -d'|' -f4)
case "$oldpm" in ''|*[!0-9]*) echo "CONN_FAIL bad-baseline-postmaster '$oldpm' in $base"; exit 2;; esac
req=$(cut -d'|' -f1,2 "$base" | grep -vxE 'pellets\|pellets' | sort -u)
[ -n "$req" ] || { echo "CONN_FAIL empty-baseline (cannot anchor)"; exit 2; }
for i in $(seq 1 ${TRIES:-20}); do
  if [ "$dp" = postgresql ]; then  # pool-on-demand consumers: each request below opens a DB session (measured 2026-10-05)
    kubectl port-forward -n databases svc/nocodb 18080:8080 >/dev/null 2>&1 & p1=$!
    kubectl port-forward -n monitoring svc/sweep-dashboard 18081:80 >/dev/null 2>&1 & p2=$!
    sleep 3; curl -s -o /dev/null localhost:18080/api/v1/auth/user/me; curl -s -o /dev/null localhost:18081/
    kill $p1 $p2 2>/dev/null; wait $p1 $p2 2>/dev/null
  fi
  now=$(kubectl exec -i -n "$ns" deploy/"$dp" -- sh -c 'psql -X -U "$POSTGRES_USER" -d postgres -tA' < pairs.sql)
  pm=$(echo "$now" | head -1 | cut -d'|' -f4)
  miss=''; for k in $req; do n=$(echo "$now" | grep "^$k|" | cut -d'|' -f3); [ "${n:-0}" -ge 1 ] || miss="$miss $k"; done
  if [ -n "$pm" ] && [ "$pm" -gt "$push" ] && [ "$pm" -gt "$oldpm" ] && [ "$pm" != "$oldpm" ] && [ -z "$miss" ]; then
    echo "CONN_PASS $ns/$dp postmaster=$pm>push=$push,>before=$oldpm"; echo "$now"; exit 0; fi
  echo "try $i: postmaster=${pm:-none} push=$push before=$oldpm missing:${miss:- none}"; sleep 27
done
echo "CONN_FAIL $ns/$dp postmaster=${pm:-none} push=$push before=$oldpm missing:$miss"; exit 1
CONN
```

Expected BEFORE (measured 2026-10-03): `counts-shared` has 249 rows (nocodb 157 tables, oc8 71,
pellets 10, sweep_history 11), `counts-affine` 93 tables, `counts-sure` 132. EXPR lines:

```
EXPR|postgres|0.8.1|0.8.6|[2,3]|1|5
EXPR|oc8|0.8.6|0.8.6|[2,3]|1|5
EXPR|affine|0.8.1|0.8.6|[2,3]|1|5
EXPR|sure|0.8.6|0.8.6|[2,3]|1|5
```

There is one VEC line per vector column (8 total). `affine ai_workspace_embeddings` reads
`2:3faf1cf17d52b147d9cf997b0b57df41`. Empty columns read `0:3a3ea00cfc35332cedf6e5e9a32e94da`.

Expected `pairs-*-before.txt` (measured 2026-10-05; the third field varies): shared
`nocodb|nocodb`, `oc8|oc8_app`, `pellets|pellets`, `sweep_history|sweep_reader`; affine-pg
`affine|affine`; sure-pg `sure|sure` (sidekiq). nocodb holds no idle session (0 at 08:30Z, 1 after one
HTTP request), which is why `conn.sh` fires a request before each poll. Whatever pairs the baseline
holds on the night are the ones the gate requires.
**If any file is empty or an EXPR line is missing, stop.** A baseline that did not measure cannot
anchor a gate.

### 3.2 Leg A — affine-pg (canary; same order as the 0.8.6 rollout)

```bash
cd /Users/mu/code/cberg-home-nextgen
OLD='0.8.6-pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b'
NEW='0.8.7-pg16@sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a'
sed -i '' -e "s#${OLD}#${NEW}#" -e 's#(PG 16.x + pgvector 0.8.6)#(PG 16.x + pgvector 0.8.7)#' kubernetes/apps/office/affine/app/postgres-helmrelease.yaml
git diff --stat kubernetes/apps/office/affine/app/postgres-helmrelease.yaml   # 1 file, 2 +/2 -
```

Dry-run diff:

```
<               # Digest-pinned: upstream rebuilds pg16 tags in place (PG 16.x + pgvector 0.8.6)
<               tag: 0.8.6-pg16@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b
>               # Digest-pinned: upstream rebuilds pg16 tags in place (PG 16.x + pgvector 0.8.7)
>               tag: 0.8.7-pg16@sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a
```

```bash
printf 'fix(affine): pgvector 0.8.6-pg16 -> 0.8.7-pg16 (digest re-pinned)\n\nCanary leg of plan pgvector-fleet-0.8.7. Same PG 16.15 build; library-only\nchange; extension catalog deliberately NOT altered (keeps git-revert rollback).\n\nCo-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>\n' > /tmp/pgv-87/msg-a.txt
git commit --only kubernetes/apps/office/affine/app/postgres-helmrelease.yaml -F /tmp/pgv-87/msg-a.txt
git log -1 --format=%s && git show --stat HEAD | tail -3      # must be YOUR subject and ONE file
git push && date +%s > /tmp/pgv-87/push-a.epoch && cat /tmp/pgv-87/push-a.epoch
```

Flux applies via the webhook. If `kubectl get hr -n office affine-pg` has not moved to the new revision
within 5 min: `flux reconcile ks affine -n office --with-source`. Then run **§4.A**. If §4.A fails,
go to §5 and do not continue.

### 3.3 Leg B — sure-pg

Same as 3.2 with `kubernetes/apps/office/sure/app/postgres-helmrelease.yaml`. The identical two-line
diff was dry-run. Commit subject: `fix(sure): pgvector 0.8.6-pg16 -> 0.8.7-pg16 (digest re-pinned)`.
Push with the same line shape as leg A: `git push && date +%s > /tmp/pgv-87/push-b.epoch && cat /tmp/pgv-87/push-b.epoch`. Fallback reconcile: `flux reconcile ks sure -n office --with-source`.
Then run **§4.B**.

### 3.4 Logical dumps — BEFORE touching the shared instance (backup_gate)

```bash
cd /tmp/pgv-87
for db in sweep_history oc8 nocodb pellets; do
  kubectl exec -n databases deploy/postgresql -- sh -c "pg_dump -U \"\$POSTGRES_USER\" -d $db -Fc" > "dump-$db.pgc"
  echo "$db bytes=$(wc -c < dump-$db.pgc) tabledata=$(pg_restore -l dump-$db.pgc | grep -c 'TABLE DATA ')"
done
kubectl exec -n databases deploy/postgresql -- sh -c 'pg_dumpall -U "$POSTGRES_USER" --globals-only' > globals.sql
grep -c '^CREATE ROLE' globals.sql
```

PASS: every DB has non-zero bytes and its `tabledata` equals its table count in
`counts-shared-before.txt`: sweep_history 11, oc8 71, nocodb 157, pellets 10. This was measured with
the local `pg_restore 16.14` against a sweep_history dump on 2026-10-03, which printed 11. The
globals file must hold ≥ 1 `CREATE ROLE` (it includes `sweep_writer`, `sweep_reader`, `oc8_migrate`,
`oc8_app`). FAIL: a 0-byte dump or a short TOC means **stop**. Do not restart the instance
without a proven dump. Keep the dumps in `/tmp/pgv-87`, never under the repo. They contain operator
policy data.

### 3.5 Leg C — the shared databases/postgresql

Prerequisites: §2.7 (no shell holds `SWEEP_PG_DSN`; Step-0 writes finished). The **hard gate is
`jit.sh` run immediately before the push**, after the commit is built, so no minutes pass between
the check and the restart.

```bash
# Re-take the shared consumer baseline NOW (the §3.1 copy is ~30 min old; nocodb's session count
# moves with traffic). conn.sh in §4.C requires exactly these pairs and this postmaster epoch.
( cd /tmp/pgv-87 && kubectl exec -i -n databases deploy/postgresql -- sh -c 'psql -X -U "$POSTGRES_USER" -d postgres -tA' < pairs.sql > pairs-shared-before.txt && cat pairs-shared-before.txt )
# STOP if the file is empty.
cd /Users/mu/code/cberg-home-nextgen
sed -i '' -e "s#${OLD}#${NEW}#" kubernetes/apps/databases/postgresql/app/deployment.yaml
git diff kubernetes/apps/databases/postgresql/app/deployment.yaml | grep '^[-+] '
# -        image: pgvector/pgvector:0.8.6-pg16@sha256:ccc6e83d...
# +        image: pgvector/pgvector:0.8.7-pg16@sha256:7b822b0a...
printf 'fix(postgresql): pgvector 0.8.6-pg16 -> 0.8.7-pg16 (digest re-pinned)\n\nShared-instance leg of plan pgvector-fleet-0.8.7. Same PG 16.15 build; catalog\nextversions left as-is (postgres 0.8.1, oc8 0.8.6). Dumps taken first.\n\nCo-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>\n' > /tmp/pgv-87/msg-c.txt
git commit --only kubernetes/apps/databases/postgresql/app/deployment.yaml -F /tmp/pgv-87/msg-c.txt
git log -1 --format=%s && git show --stat HEAD | tail -3
# JUST-IN-TIME HARD GATE — re-run §2.6 now; push ONLY on JIT_GO.
( cd /tmp/pgv-87 && bash jit.sh ) && git push && date +%s > /tmp/pgv-87/push-c.epoch && cat /tmp/pgv-87/push-c.epoch
```

On `JIT_STOP` the commit is **not pushed**. Wait out the reason (a sweep finishing, the heartbeat
minute) and re-run the gated line. If it is a sweep night past 03:55, do not wait into the sweep:
`git reset --soft HEAD~1 && git restore --staged kubernetes/apps/databases/postgresql/app/deployment.yaml && git checkout -- kubernetes/apps/databases/postgresql/app/deployment.yaml`
(only while the commit is unpushed and `git log -1 --format=%s` is YOUR leg-C subject), skip legs C
and D, and report legs A/B as done with C/D deferred. **From the push until §4.C passes, no write to
`sweep_history`** (§2.7).

(`${OLD}`/`${NEW}` are from §3.2. Re-set them if this is a fresh shell.) The Deployment's
`maxSurge: 0 / maxUnavailable: 1` tears the old pod down before the new one starts. Do **not**
"simplify" it to `type: Recreate`, because SSA rejects that on this object (comment in the
manifest). Fallback reconcile: `flux reconcile ks postgresql -n databases --with-source`. Then run
**§4.C**, then re-establish the window agent's DSN forward.

### 3.6 Leg D — the two client-only bootstrap Jobs (rename = re-run; SOP §4a)

**§4a safety verdict (read end-to-end 2026-10-03):**

- `oc8-db/app/bootstrap-configmap.yaml` has guarded `CREATE ROLE`, `ALTER ROLE … PASSWORD`
  (re-asserts the SOPS value), guarded `CREATE DATABASE`, `CREATE EXTENSION IF NOT EXISTS vector`
  (a no-op: it does **not** update the catalog version), `ALTER SCHEMA OWNER`, `GRANT`s and default
  privileges. Nothing destructive. Its last line prints the catalog version.
- `sweep-history/app/schema-configmap.yaml` has `CREATE … IF NOT EXISTS` throughout, the
  already-applied widening `ALTER COLUMN … TYPE NUMERIC(8,2)`, and **one** `DROP CONSTRAINT IF
  EXISTS` + `ADD CONSTRAINT ck_findings_resolved_status` wrapped in `BEGIN … COMMIT` with
  `lock_timeout 5s`. Inside the transaction, a bad row fails the Job loudly and keeps the old
  constraint. It ran exactly so as v9 five days ago. No TRUNCATE, DELETE or unguarded INSERT.
- Both delivering Kustomizations have `prune: true`, so Flux deletes the old Job and creates the new
  one. Nothing else in `kubernetes/`, `runbooks/` or `.claude/` references the old Job names.
  `docs/applications.md` mentions `oc8-db-init-v1` in prose (step 3.7).

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' -e "s#${OLD}#${NEW}#" -e 's#^  name: oc8-db-init-v1$#  name: oc8-db-init-v1a#' -e 's#^\(\#        schema ownership and default privileges on the shared postgresql\.\)$#\1\
\#   v1a — image pgvector 0.8.6-pg16 -> 0.8.7-pg16 (digest re-pinned); no script change.\
\#         Rename forces prune+recreate (Job spec immutable); bootstrap is idempotent.#' kubernetes/apps/databases/oc8-db/app/init-job.yaml
sed -i '' -e "s#${OLD}#${NEW}#" -e 's#^  name: sweep-history-init-v9  \# v8->v9: component_autonomy table\. Rename forces recreate (Job spec immutable)\.$#  name: sweep-history-init-v9a  \# v9->v9a: pgvector 0.8.7 image only. Rename forces recreate (Job spec immutable).#' -e 's#^\(\#         stays OFF (fail-safe) — nothing depends on the table existing\.\)$#\1\
\#   v9a — image pgvector 0.8.6-pg16 -> 0.8.7-pg16 (digest re-pinned); no schema or\
\#         bash change. Rename forces prune+recreate; bootstrap is idempotent.#' kubernetes/apps/databases/sweep-history/app/init-job.yaml
git diff --stat kubernetes/apps/databases/oc8-db/app/init-job.yaml kubernetes/apps/databases/sweep-history/app/init-job.yaml
# PASS: 2 files, each "+4 -2" (2 History lines added, name + image changed)
```

Dry-run diff (scratch copies, 2026-10-03):

```
oc8-db:        > #   v1a — image pgvector 0.8.6-pg16 -> 0.8.7-pg16 (digest re-pinned); no script change.
               > #         Rename forces prune+recreate (Job spec immutable); bootstrap is idempotent.
               <   name: oc8-db-init-v1            >   name: oc8-db-init-v1a
               <           image: …0.8.6-pg16@sha256:ccc6…   >           image: …0.8.7-pg16@sha256:7b82…
sweep-history: > #   v9a — image pgvector 0.8.6-pg16 -> 0.8.7-pg16 (digest re-pinned); no schema or
               > #         bash change. Rename forces prune+recreate; bootstrap is idempotent.
               <   name: sweep-history-init-v9  # v8->v9: …   >   name: sweep-history-init-v9a  # v9->v9a: pgvector 0.8.7 image only. …
               <           image: …0.8.6-pg16@sha256:ccc6…   >           image: …0.8.7-pg16@sha256:7b82…
```

If either `--stat` line is not `+4 -2`, an anchor did not match (the file drifted). Then `git checkout`
the file and make the edit by hand. Do not commit a half-edited Job: a renamed Job on the old image,
or the new image under the old name, would fail the apply with `field is immutable` and wedge the
Kustomization.

```bash
printf 'fix(oc8-db,sweep-history): init Jobs to pgvector 0.8.7-pg16 (v1->v1a, v9->v9a)\n\nClient-only image bump; Job spec is immutable so the rename forces\nprune+recreate. Both bootstraps re-read end-to-end and are idempotent\n(immutable-job-image-bumps SOP 4a). Plan pgvector-fleet-0.8.7 leg D.\n\nCo-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>\n' > /tmp/pgv-87/msg-d.txt
git commit --only kubernetes/apps/databases/oc8-db/app/init-job.yaml kubernetes/apps/databases/sweep-history/app/init-job.yaml -F /tmp/pgv-87/msg-d.txt
git log -1 --format=%s && git show --stat HEAD | tail -4
git push
```

Fallback reconcile: `flux reconcile ks oc8-db -n databases --with-source` and
`flux reconcile ks sweep-history -n databases --with-source`. Then run **§4.D**.

### 3.7 Docs (same session, separate commit; optional but owed)

In `docs/applications.md` (oc8 row), change `` `oc8-db-init-v1` `` to `` `oc8-db-init-v1a` `` and
`pgvector/pgvector:0.8.6-pg16` to `pgvector/pgvector:0.8.7-pg16`. Do this by hand and stage only
that hunk. `docs/sops/auto-update.md:193` names `sweep-history-init-v9` as the Job that **created**
`component_autonomy`. That is historically true, so leave it.

### 3.8 Close-out

```bash
cd /Users/mu/code/cberg-home-nextgen
runbooks/update-marker.sh clear pgvector; runbooks/update-marker.sh clear affine-pg; runbooks/update-marker.sh clear sure-pg
```

Retire this plan file in the same commit series once §4 is fully green (README: executed plans are
deleted).

## 4. Verification

The `snap after` function and the scripts come from §3.1. Re-define them if the shell is fresh. The
`NEWD` check reads the pod's **resolved** imageID, not the spec. `rollout status` can report the
old generation green (`feedback_rollout_status_old_generation`).

```bash
NEWD=7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a
```

### 4.A after leg A (affine-pg)

```bash
cd /tmp/pgv-87
kubectl get pod -n office -l app.kubernetes.io/instance=affine-pg -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID} {.status.containerStatuses[0].ready} {.status.containerStatuses[0].restartCount}{"\n"}{end}'
# PASS: exactly ONE line: docker.io/pgvector/pgvector@sha256:7b822b0a… true 0
# FAIL shapes: still sha256:ccc6… (not rolled — check hr/affine-pg events), two lines (Recreate stuck), ready false / restarts>0 (crash: kubectl logs).
kubectl exec -i -n office deploy/affine-pg -- sh -s affine < vec.sh > vec-affine-after.txt
kubectl exec -i -n office deploy/affine-pg -- sh < counts.sh > counts-affine-after.txt
cat vec-affine-after.txt
```

- CONTENTS ASSERTION: new library loaded, catalog untouched. The EXPR line must read exactly
  `EXPR|affine|0.8.1|0.8.7|[2,3]|1|5`. Field 4 (`default_version`, read from the extension
  control file on disk) moves 0.8.6 -> 0.8.7. That proves the 0.8.7 files are what the server sees,
  and it reads `0.8.6` if the pod is still on the old image. Field 3 must still be `0.8.1`. It
  **fails** if someone ran ALTER EXTENSION, which would void `rollback_class: git-revert` (§1.3). The
  last three fields exercise `avg`, cosine and L2 in the new `.so`. A broken library prints `ERROR:`
  and no EXPR line at all, and the grep below fails.
- CONTENTS ASSERTION: vector data unchanged. `diff <(grep ^VEC vec-affine-before.txt) <(grep ^VEC vec-affine-after.txt)`
  must print nothing. The per-column `count:md5(text)` goes through `vector_out` of the **new**
  library, so a changed text encoding or lost rows shows as a diff.
- CONTENTS ASSERTION: same data directory, same rows. Run:
  ```bash
  python3 - counts-affine-before.txt counts-affine-after.txt <<'EOF'
  import sys
  def load(p): return {l.split('|')[1]: int(l.split('|')[2]) for l in open(p) if l.count('|')==2}
  b,a=load(sys.argv[1]),load(sys.argv[2])
  if not b or not a or sum(a.values())==0: print('COUNTS_FAIL empty'); sys.exit(1)
  if set(b)!=set(a): print('COUNTS_FAIL tableset', sorted(set(b)^set(a))); sys.exit(1)
  down={t:(b[t],a[t]) for t in b if a[t]<b[t]}; up={t:(b[t],a[t]) for t in b if a[t]>b[t]}
  print('UP (explain each as live traffic):', up)
  print('COUNTS_FAIL decreased', down) if down else print('COUNTS_PASS tables=%d rows=%d'%(len(a),sum(a.values())))
  sys.exit(1 if down else 0)
  EOF
  ```
  PASS: `COUNTS_PASS tables=93 …`. This fails on the classic restart disaster (wrong PGDATA, so
  initdb creates an empty cluster). That cluster shows a different table set and a zero total. It
  also fails on any table whose count went down.
- CONSUMER PRESENCE GATE (the app is back ON the new database, not merely silent):
  ```bash
  kubectl port-forward -n office svc/affine 13010:3010 >/dev/null 2>&1 & PF=$!; sleep 2
  curl -s -o /dev/null -w '%{http_code}\n' localhost:13010/; curl -s localhost:13010/info; kill $PF 2>/dev/null
  cd /tmp/pgv-87 && sh conn.sh push-a.epoch pairs-affine-pg-before.txt office affine-pg   # cd: agent cwd resets between calls (review 2026-10-05)
  ```
  PASS: `200`, a JSON body containing `"AFFiNE` (measured 200 / `AFFiNE 0.27.4 Server` before),
  **and** `CONN_PASS office/affine-pg postmaster=<new>>push=<push-a>,>before=<old>` listing `affine|affine|N|…`
  with N ≥ 1. The pair is keyed on (database, user), so a backend of the `affine` role in the
  `affine` database whose `backend_start` is later than the new postmaster's start is a session the
  app opened **after** the restart. Today the app holds 10 such sessions, so this is the
  DB-touching half that HTTP 200 alone cannot prove (`/info` answers from the Node process).
  It FAILS with `CONN_FAIL … missing: affine|affine` if the app never reconnected within 10 min,
  and with `postmaster=<old>` if the pod never restarted.
  Informational only (not a gate): `kubectl logs -n office deploy/affine --since=2m | grep -ciE "prisma|ECONNREFUSED|database.*(error|unreachable)"`.
  A non-zero count is a lead for investigation, not a verdict; zero proves nothing by itself.
- CONTROL: metric kube_pod_container_status_restarts_total — `kube_pod_container_status_restarts_total{namespace="office",pod=~"affine-pg-.*"}`
  must be 0 for the new pod (the series exists today and reads 0 for the current pod).

### 4.B after leg B (sure-pg)

Same as 4.A with `-l app.kubernetes.io/instance=sure-pg`, `vec.sh` arg `sure` and `counts-sure-*`.
EXPR must read exactly `EXPR|sure|0.8.6|0.8.7|[2,3]|1|5`. VEC diff must be empty.
`COUNTS_PASS tables=132`. Then the consumer gates:

```bash
cd /tmp/pgv-87
kubectl get deploy -n office sure-web sure-worker -o jsonpath='{.items[*].status.readyReplicas}{"\n"}'
# PASS: "1 1"
kubectl exec -n office deploy/sure-web -c web -- sh -c 'timeout 90 bin/rails runner "puts \"SURE_DB_OK families=#{Family.count} accounts=#{Account.count}\"" 2>&1 | tail -1'
# PASS: the line equals sure-app-before.txt (§3.1) — "SURE_DB_OK families=1 accounts=11" on 2026-10-05. FAIL: a PG::ConnectionBad /
# ActiveRecord::ConnectionNotEstablished trace, a timeout (no line), or different counts.
sh conn.sh push-b.epoch pairs-sure-pg-before.txt office sure-pg
# PASS: CONN_PASS office/sure-pg ... with "sure|sure|N|…", N >= 1 — sidekiq (sure-worker) holds a
# session on the NEW postmaster. FAIL: CONN_FAIL ... missing: sure|sure (sidekiq never reconnected).
```

The `rails runner` boots a fresh Rails process in the sure-web pod, so it proves the image's DB
config reaches the new sure-pg; the sidekiq session in `conn.sh` proves the long-running worker
pool reconnected. Informational only: `kubectl logs -n office deploy/sure-worker --since=2m | grep -ciE "PG::|ConnectionBad|could not connect"`
and the same against `deploy/sure-web`.

- CONTROL: alertname SurePostgresDown — must be **not firing** 6 min after the roll (`for: 5m`
  on `kube_pod_status_ready{pod=~"sure-pg-.*"}`). If it is firing, the pod never became Ready.

### 4.C after leg C (shared postgresql)

```bash
cd /tmp/pgv-87
kubectl get pod -n databases -l app=postgresql -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID} {.status.containerStatuses[0].ready} {.status.containerStatuses[0].restartCount}{"\n"}{end}'
# PASS: ONE line, sha256:7b822b0a…, true, 0
kubectl exec -i -n databases deploy/postgresql -- sh -s postgres < vec.sh >  vec-shared-after.txt
kubectl exec -i -n databases deploy/postgresql -- sh -s oc8      < vec.sh >> vec-shared-after.txt
kubectl exec -i -n databases deploy/postgresql -- sh < counts.sh > counts-shared-after.txt
grep ^EXPR vec-shared-after.txt
diff <(grep ^VEC vec-shared-before.txt) <(grep ^VEC vec-shared-after.txt) && echo VEC_SAME
```

- CONTENTS ASSERTION: EXPR must read exactly `EXPR|postgres|0.8.1|0.8.7|[2,3]|1|5` and
  `EXPR|oc8|0.8.6|0.8.7|[2,3]|1|5`, and you must see `VEC_SAME`. The meaning of each field and how it
  fails is as in 4.A.
- CONTENTS ASSERTION: run the 4.A Python block on `counts-shared-before.txt counts-shared-after.txt`.
  PASS: `COUNTS_PASS tables=249`. Increases are allowed only in tables that live traffic writes, and
  each must be explained: `sweep_history.public.{sweep_cycles,sweep_findings,window_runs,plan_executions,component_autonomy,slo_snapshots}`,
  nocodb audit tables, and `pellets` price rows. Any decrease is a FAIL, and so is a changed table set.
- CONSUMER PRESENCE GATE — every (database, user) pair connected before the restart has ≥ 1
  backend newer than the NEW postmaster, within a bounded 10-min wait:
  ```bash
  cd /tmp/pgv-87
  sh conn.sh push-c.epoch pairs-shared-before.txt databases postgresql
  ```
  PASS: `CONN_PASS databases/postgresql postmaster=<new>>push=<push-c>,>before=<old>` and every pair of
  `pairs-shared-before.txt` except `pellets|pellets` present with N ≥ 1 (2026-10-05 baseline:
  `nocodb|nocodb`, `oc8|oc8_app`, `sweep_history|sweep_reader`). Before each poll the script sends
  one HTTP request each to nocodb and sweep-dashboard, which open a session on demand (measured: a
  single nocodb request took `nocodb|nocodb` from 0 to 1). FAIL shapes: `CONN_FAIL … missing: oc8|oc8_app`
  (oc8's pool never came back — check `kubectl logs -n ai deploy/oc8-scheduler`), `postmaster=<old>`
  (the pod never restarted, so the "reconnect" proves nothing), `empty-baseline`.
  `pellets|pellets` is excluded from the requirement on purpose: that session is Grafana's datasource
  pool (client IP = the grafana pod), which reconnects only when someone opens a pellets panel, and
  the pellets data itself is covered by the counts gate. Its write-side consumer is the
  `home-automation/pallet-price-monitor` CronJob (`0 8,20 * * *` Berlin), checked in the morning: its
  `kube_cronjob_status_last_successful_time` must be newer than the window end after the 08:00 run.
- Readiness (supporting, not the gate):
  `for x in "databases nocodb" "ai oc8-backend" "ai oc8-worker" "ai oc8-scheduler" "monitoring sweep-dashboard" "media media-dashboard"; do kubectl get deploy -n ${x%% *} ${x##* } -o jsonpath='{.metadata.name}={.status.readyReplicas}{"\n"}'; done`
  — every line `=1`; an empty value is a FAIL.
- Informational only (not a gate): `kubectl logs -n <ns> deploy/<dp> --since=2m | grep -ciE 'could not connect|connection refused|terminating connection|server closed the connection'`
  for the six deployments above. A non-zero count is a lead to read, not a verdict.
- `sweep_history` readable by its reader role (this is also the first moment a DSN may be held
  again; §2.7): re-establish the DSN (`source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up`).
  In that shell, `.venv/bin/python3 runbooks/policy-cli.py finding list --grep pgvector | grep -c '^F-'`
  must be ≥ 1 (6 rows on 2026-10-03). It reads 0 or an error if the DB or grants are gone. Do
  `sweep_pg_dsn_down` before any commit.
- CONTROL: metric kube_deployment_status_replicas_available — `kube_deployment_status_replicas_available{namespace="databases",deployment="postgresql"}`
  is `1` (reads 1 today).
- CONTROL: alertname SweepPipelineDead — must remain **not firing**. It fires if the next
  `sweep-heartbeat` run (`17 */6`, Europe/Berlin: 00:17/06:17/12:17/18:17) cannot reach `sweep_history`. For a 03:30 nightly window that is the 06:17 Berlin run; check it after that run
  following the window. In the morning report, check that `kube_cronjob_status_last_successful_time{cronjob="sweep-heartbeat"}`
  is newer than the window end.

### 4.D after leg D (init Jobs)

```bash
kubectl get job -n databases oc8-db-init-v1a sweep-history-init-v9a -o jsonpath='{range .items[*]}{.metadata.name} {.status.succeeded} {.spec.template.spec.containers[0].image}{"\n"}{end}'
# PASS: both "1" and both on …0.8.7-pg16@sha256:7b822b0a…
kubectl get job -n databases oc8-db-init-v1 sweep-history-init-v9 2>&1 | grep -c NotFound
# PASS: 2 (Flux pruned both old Jobs)
# Read both Job logs RIGHT AFTER each Job shows succeeded=1. Do not defer this to the morning
# report: on 2026-10-05 `kubectl logs job/oc8-db-init-v1` (completed earlier) already returned
# "error: timed out waiting for the condition" — the pod is no longer readable, and a gate that
# reads nothing must count as FAIL, not as "no errors".
kubectl wait -n databases --for=condition=complete job/oc8-db-init-v1a job/sweep-history-init-v9a --timeout=300s
kubectl logs -n databases job/oc8-db-init-v1a | tail -1 | tee jobs-oc8.log
# PASS: "==> Done. vector: 0.8.6"  — the bootstrap completed AND CREATE EXTENSION IF NOT EXISTS left the catalog alone
kubectl logs -n databases job/sweep-history-init-v9a | tail -1 | tee jobs-sweep.log
# PASS: "==> Done". An empty file or "error: timed out" is a FAIL (re-read immediately; if the pod is gone, assert via §4.D CONTENTS below and record the gap).
flux get ks -A | grep -E '^(databases|ai)[[:space:]]+(oc8-db|oc8|sweep-history)[[:space:]]'
# PASS: three rows READY True (oc8-db is wait:true and gates ai/oc8)
```

- CONTROL: metric kube_job_status_succeeded — `kube_job_status_succeeded{namespace="databases",job_name=~"(oc8-db-init-v1a|sweep-history-init-v9a)"}`
  must have two series, both `1`. An absent series means the Job was never created, typically
  because the apply failed with `field is immutable`. Then the ks shows `False`.
- CONTENTS ASSERTION: policy data survived the bootstrap re-run (SOP §4a f). Re-run `counts.sh`
  against the shared instance into `counts-shared-afterD.txt` and run the 4.A Python block on
  `counts-shared-after.txt counts-shared-afterD.txt`. PASS: `COUNTS_PASS`. Then the explicit
  equality check for the four operator-policy tables (nothing writes those at night, so any
  difference, up OR down, is a FAIL):
  ```bash
  cd /tmp/pgv-87
  for t in accepted_risks slo_definitions noise_suppressions security_acceptances; do
    b=$(grep "^sweep_history|public.$t|" counts-shared-before.txt | cut -d'|' -f3)
    a=$(grep "^sweep_history|public.$t|" counts-shared-afterD.txt | cut -d'|' -f3)
    [ -n "$b" ] && [ "$b" = "$a" ] && echo "EQ_PASS $t=$a" || echo "EQ_FAIL $t before=${b:-missing} after=${a:-missing}"
  done
  ```
  PASS: four `EQ_PASS` lines. `EQ_FAIL … before=missing` means the baseline did not measure the
  table (stop and look, the gate did not run). A decrease in any of them: restore it from
  `dump-sweep_history.pgc` (§5.3) immediately.

## 5. Rollback

Each leg is one commit, and each commit reverts on its own. Nothing forward-only happens: same PG
binary, catalog untouched, idempotent bootstraps. Roll back **only the failing leg and every leg
after it**, newest first.

### 5.1 Server legs (A, B, C)

```bash
cd /Users/mu/code/cberg-home-nextgen
git log --oneline -6 -- kubernetes/apps/office/affine/app/postgres-helmrelease.yaml kubernetes/apps/office/sure/app/postgres-helmrelease.yaml kubernetes/apps/databases/postgresql/app/deployment.yaml
git revert --no-edit <sha-of-the-failing-leg>
git log -1 --format=%s && git show --stat HEAD | tail -3
git push
```

Confirm you are back: the pod's imageID reads `sha256:ccc6e83d…` (4.A/4.C jsonpath). The EXPR line
reads `0.8.6` in field 4 with field 3 unchanged. The VEC diff against `*-before.txt` is empty, and
the counts block prints `COUNTS_PASS`. Because the catalog was never altered, the 0.8.6 library
serves the same catalog it served this morning. That is the reason §1.3 forbids ALTER EXTENSION.
**If the EXPR line shows field 3 changed** (someone ran ALTER EXTENSION), a plain revert no longer
fully restores. Stop and escalate. For a DB that holds no vector data, the clean path is: restore the
dump of that DB from §3.4 into a scratch DB, compare, then decide. Do not improvise `DROP EXTENSION`.

### 5.2 Leg D (Jobs)

`git revert` of the leg-D commit renames the Jobs back to `v1`/`v9` on 0.8.6. Flux prunes `v1a`/`v9a`
and **re-runs** the old bootstraps, which is the same idempotent script, so this is harmless. Confirm
that both old-named Jobs show `succeeded=1` and `flux get ks` is Ready for oc8-db / sweep-history / oc8.

### 5.3 Data restore (only if a §4 counts gate shows loss)

The datadir is not touched by any step here, so data loss would mean something unforeseen. Restore
surgically from the §3.4 dumps (or, for affine/sure, from the Longhorn backup proven in §2.4 via
`docs/sops/backup.md`):

```bash
cd /tmp/pgv-87
# one table, e.g. accepted_risks in sweep_history (data only, into the existing table):
pg_restore -l dump-sweep_history.pgc | grep -E 'TABLE DATA public accepted_risks ' > one.list
kubectl exec -n databases deploy/postgresql -- sh -c 'psql -U "$POSTGRES_USER" -d sweep_history -c "TRUNCATE accepted_risks"'
pg_restore -L one.list -f - dump-sweep_history.pgc | kubectl exec -i -n databases deploy/postgresql -- sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d sweep_history'
# then re-run counts.sh and compare that table against counts-shared-before.txt
```

The TRUNCATE here is a deliberate restore action on a table proven damaged. It needs the operator's
GO in an attended session and must never run as part of an unattended window. **No PVC, PV or
Longhorn Volume is deleted in any rollback path.** Storage-safety house rule: no CIFS/SMB/NFS PVC
delete without the 3-step pre-flight. None is in scope here (all three volumes are Longhorn block).

## 6. Interference notes

- **Shared instance = shared blast radius.** Leg C restarts the instance behind `sweep_history`,
  which is the window's own state store (`window_runs`, `plan_executions`, `component_autonomy`).
  It also backs `oc8`, `nocodb` and `pellets`, and `sweep-dashboard` / `media-dashboard` read from
  it. The outage lasts ~30-60 s. Run leg C **after** Step 0 has recorded its results and with the
  window agent's DSN forward closed (§2.7), and never inside a `sweep-heartbeat` minute (`17 */6`,
  §2.5; Europe/Berlin 00:17/06:17/12:17/18:17). The nightly 03:30 slot sits between the 00:17 and
  06:17 heartbeats, but on a 48h sweep night the 04:00 sweep follows at once — `jit.sh` stops leg C
  from 03:55 on such nights.
- **Longhorn backup at 03:00.** By 03:30 the snapshots are normally taken. If `kubectl get backups.longhorn.io -n storage`
  shows one `InProgress` for `postgresql-data-5g` or either office volume, wait for it to finish
  before restarting that pod.
- **`oc8-db` is `wait: true` and gates `ai/oc8`.** If `oc8-db-init-v1a` fails, `oc8-db` goes
  NotReady and the `oc8` Kustomization stops reconciling. It is not torn down, but later oc8 commits
  stop landing. Watch §4.D's ks line.
- **sure-pg-data is a dynamic PV with `reclaim: Delete`** (premise `pv-reclaim`). Nothing here
  deletes it. Never let a rollback "recreate the PVC".
- **`maxSurge: 0` on postgresql is load-bearing** (`docs/sops/longhorn-rwo-multi-attach.md`). Do not
  change the strategy in the same commit.
- `conflicts_with` covers every same-file, same-instance or same-controller plan found on
  2026-10-03, re-checked 2026-10-05 (frontmatter comments give each reason).
  `kube-prometheus-stack-91.9.0` is vetted for `nightly:2026-10-08` and `exclusive: true`. §4's
  CONTROL gates read Prometheus, so it is listed in `conflicts_with`: never schedule this plan on
  that night. `app-template-5.2.1` is now `nightly:2026-10-09` (same files for affine-pg/sure-pg),
  so 10-09 is excluded too. talos/talconfig/longhorn-class work is exclusive or listed.
- Not covered here on purpose: catalog alignment (`ALTER EXTENSION vector UPDATE`). It is cosmetic
  for 0.8.7 and it converts the rollback class to one-way. Do not fold it into this plan.
