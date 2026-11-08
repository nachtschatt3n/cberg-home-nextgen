---
plan_id: postgres-digest-refresh-2026-11
component: postgres-digest-refresh
pr: 463                                # Renovate #463 (pgvector/pgvector digest). Its sibling #227 (postgres:18.6-alpine
                                       # digest) is the same job and is delivered by this plan too; `pr` holds one int.
kind: image
current: "pgvector/pgvector:0.8.7-pg16@7b822b0 (shared postgresql, affine-pg, sure-pg + 3 init Jobs); postgres:18.6-alpine@d3e1620 (superset-pg18 + 4 CronJobs) and @63bdc97 (paperclip-postgresql, the amd64 child of d3e1620)"
target: "0dd3149"                      # pgvector/pgvector:0.8.7-pg16 digest (PR #463); also postgres:18.6-alpine 123b179 / paperclip child 300ebd0 (PR #227).
                                       # Kept to the #463 digest token because maintenance-plan.py compares target: with the held PR's new: by token.
update_type: n/a                       # digest refresh of an unchanged tag: PG 16.15 -> 16.15, PG 18.6 -> 18.6, pgvector 0.8.7 -> 0.8.7
risk: medium                           # five stateful databases restart (Recreate), one of them multi-tenant; no on-disk change
est_duration_min: 65                   # IN-WINDOW: pre-checks + dumps 15 + 2 small restore proofs 10 | stage 1 10 | stage 2 10 | stage 3a 10 | stage 3b 5 | close-out 5.
                                       # The three 20Gi restore proofs are a PRE-WINDOW prerequisite (section 2.5a), not counted here.
needs_reboot: false
touches:
  namespaces: [databases, office, ai, kube-system, media]   # namespaces whose objects are EDITED. Client-only namespaces (home-automation, monitoring,
                                       # my-software-production) are listed under resources as clients, not here: the validator's interference
                                       # check is shallow (namespace + shared intersection) and would flag every monitoring/home-automation plan.
  resources:
    - deployment/databases/postgresql                  # shared PG16 + pgvector server: image digest; Recreate-equivalent (maxSurge 0)
    - pvc/databases/postgresql-data-5g                 # same volume, same PGDATA; untouched
    - deployment/office/affine-pg                      # via helmrelease/office/affine-pg (app-template 5.3.0), strategy Recreate
    - deployment/office/sure-pg                        # via helmrelease/office/sure-pg, strategy Recreate
    - deployment/databases/superset-pg18               # postgres:18.6-alpine digest, strategy Recreate
    - deployment/ai/paperclip-postgresql               # postgres:18.6-alpine amd64-child digest, strategy Recreate
    - job/databases/oc8-db-init-v1a                    # renamed v1b (immutable Job template), re-runs idempotent bootstrap
    - job/databases/ninth-banner-feedback-db-init-v1a  # renamed v1b
    - job/databases/sweep-history-init-v9a             # renamed v9b
    - cronjob/databases/sweep-heartbeat                # image only (client sidecar-style image; next run picks it up)
    - cronjob/kube-system/authentik-channels-cleanup   # image only
    - cronjob/kube-system/authentik-db-probe           # image only
    - cronjob/media/media-library-audit                # image only
    - pvc/office/affine-pg-data
    - pvc/office/sure-pg-data
    - pvc/databases/superset-pg18-data
    - pvc/ai/paperclip-postgresql-data
    # CLIENTS that lose their connection during a restart and must reconnect (not edited):
    - deployment/databases/nocodb                      # shared server, db nocodb
    - deployment/ai/oc8-backend                        # shared server, db oc8 (also oc8-worker, oc8-scheduler, oc8-ingestion-worker)
    - cronjob/home-automation/pallet-price-monitor     # shared server, db pellets
    - deployment/monitoring/grafana                    # shared server, db pellets (datasource "Pellets")
    - deployment/monitoring/sweep-dashboard            # shared server, db sweep_history (SWEEP_PG_DSN)
    - deployment/my-software-production/the-ninth-banner  # shared server, db ninth_banner_feedback
    - deployment/office/affine                         # affine-pg
    - deployment/office/sure-web                       # sure-pg (also sure-worker)
    - deployment/databases/superset                    # superset-pg18 (also superset-worker, superset-celerybeat)
    - deployment/ai/paperclip                          # paperclip-postgresql
  shared:
    - shared-postgresql                # databases/postgresql is multi-tenant: 5 app databases + the sweep's own history DB
    - sweep-history-db                 # runbooks/sweep-run.py, sweep-dashboard and the sweep-heartbeat CronJob read it; do not overlap a sweep
    - storage/longhorn                 # five PVs detach and re-attach; the restore proofs create scratch Longhorn volumes
    - monitoring                       # section 4 reads Prometheus (the window's instrument)
depends_on: []
conflicts_with:
  # Same data / same pods:
  - paperclip-26.04                    # blocked - restarts deployment/paperclip, the only client of paperclip-postgresql
  - nextcloud-12.0.2                   # draft - Part B converts a datadir in namespace office; never stack two database restarts
  - bitnamilegacy-exit-nextcloud-db    # blocked - quiesces Nextcloud's DB in namespace office
  - redis-fleet-8.10.3                 # restarts sure-redis and superset-redis, which sure-web / superset need for the section 4 client gates
  # Platform serialisation (a roll of these confounds every reconnect gate):
  - longhorn-1.13.0                    # engine upgrade under all five volumes; the restore proofs also need a quiet backup target
  - talos-linux-1.14.5                 # node roll; all five databases run on k8s-nuc14-02
  - coredns-1.50.2                     # clients reconnect by DNS name (postgresql.databases.svc)
  - etcd-timeouts-5000-500             # blocked - control-plane timing change
  - helm-drift-detection               # asserts Helm revisions are identical across releases; this plan upgrades affine-pg and sure-pg
  - flux-oci-chart-sources             # re-points the app-template chart source used by affine-pg and sure-pg
  - flux-reconciler-impersonation      # blocked - changes who applies these Kustomizations
  # The window's instrument (section 4 reads Prometheus): grafana. A same-night kube-prometheus-stack bump (open PRs #428, #501) and the
  # nocodb #426 calver bump (migrations into the shared server) have no plan file, so they are NOT listable - the window agent must keep them out of this slot by hand.
  - grafana-chart-14.4.0                     # vetted - restarts Grafana (a client of db pellets) and the dashboards the operator watches
exclusive: false
security_ref: F-ae6a4cbf               # accepted-risk register entries for these two images (detail stays in the DB)
capability_change: false               # same PostgreSQL minor, same pgvector tag: behaviour identical, only the image base layers are rebuilt
rollback_class: git-revert             # in-place same-major digest swap; the revert is complete. The Longhorn backup + pg_dumpall are the floor for a data fault.
finding_refs: [F-ae6a4cbf, F-2a076950]
review: ready-for-go@2026-11-08   # plan-reviewer 2026-11-08: needs-fix (G5/3b policy-table loss undetectable, contradictory restore-proof rule on 20Gi volumes, absence-only gates), fixed with live negative controls, final blocking-only review ready-for-go; HUMAN-GATED; the three 20Gi restore proofs (2.5a) must be PROVEN before the window
status: vetted
window: "sun-attended:2026-12-20"      # coordinator-assigned 2026-11-08: free Sunday, validator-clean. Fallback: sun-attended:2026-12-27.
                                       # Do NOT stack with 2026-12-06 (n8n-fleet-2.46.6 + vaultwarden). NOT nightly: the 04:00 sweep and the
                                       # 07:30 retro read sweep_history, and this restarts it. Keep nocodb #426 (one-way knex migrations INTO the
                                       # shared server), kube-prometheus-stack #428 / #501 and any other DB-touching bump out of the same night.
premises:
  # Read-verb only, one pipeline each. Measured 2026-11-08 against the live cluster.
  - id: shared-image-current
    why: >-
      `current:` claims the shared server runs pgvector 0.8.7-pg16 @ 7b822b0. A different digest means the nightly lane or a hand edit
      already moved it: the stage-3a sed matches nothing. Drop that leg, do not force it.
    run: kubectl get deploy postgresql -n databases -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "pgvector/pgvector:0.8.7-pg16@sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a"
  - id: office-pg-images-current
    why: Same, for affine-pg and sure-pg (order as listed). Both ride a HelmRelease, so the live image proves the HelmRelease is applied.
    run: kubectl get deploy affine-pg sure-pg -n office -o jsonpath='{.items[*].spec.template.spec.containers[0].image}'
    expect_exact: "pgvector/pgvector:0.8.7-pg16@sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a pgvector/pgvector:0.8.7-pg16@sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a"
  - id: superset-image-current
    why: Same, for superset-pg18 (d3e1620 is the multi-arch index digest).
    run: kubectl get deploy superset-pg18 -n databases -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "postgres:18.6-alpine@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2"
  - id: paperclip-image-current
    why: >-
      Same, for paperclip-postgresql. It pins 63bdc97, the amd64 CHILD manifest of d3e1620, not the index. PR #227 moves it to 300ebd0,
      the amd64 child of the new index 123b179. Both children verified against the registry 2026-11-08.
    run: kubectl get deploy paperclip-postgresql -n ai -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "postgres:18.6-alpine@sha256:63bdc97d67b5133bf0e5ebd500bec6d046fa851dc81340d838f0347e616107e8"
  - id: shared-strategy-no-surge
    why: >-
      The shared Deployment mounts an RWO Longhorn PVC. maxSurge 0 is what keeps it from the Multi-Attach lottery (docs/sops/longhorn-rwo-multi-attach.md).
      If this prints anything else the rollout can wedge on FailedAttachVolume and the plan must stop.
    run: kubectl get deploy postgresql -n databases -o jsonpath='{.spec.strategy.type}-{.spec.strategy.rollingUpdate.maxSurge}'
    expect_exact: "RollingUpdate-0"
  - id: office-pg-recreate
    why: affine-pg and sure-pg must be Recreate (RWO PVC, single replica).
    run: kubectl get deploy affine-pg sure-pg -n office -o jsonpath='{.items[*].spec.strategy.type}'
    expect_exact: "Recreate Recreate"
  - id: databases-pg18-recreate
    why: superset-pg18 must be Recreate.
    run: kubectl get deploy superset-pg18 -n databases -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: paperclip-recreate
    why: paperclip-postgresql must be Recreate.
    run: kubectl get deploy paperclip-postgresql -n ai -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: databases-pair-ready
    why: Baseline - the two databases-namespace servers are Ready (1 1). 0 means a pre-existing outage, so no gate in section 4 would mean anything.
    run: kubectl get deploy postgresql superset-pg18 -n databases -o jsonpath='{.items[*].status.readyReplicas}'
    expect_exact: "1 1"
  - id: volumes-healthy
    why: >-
      The five Longhorn volumes are healthy before anything restarts (order: shared, affine, sure, paperclip, superset). A degraded
      volume turns a routine re-attach into a rebuild.
    run: kubectl get volumes.longhorn.io postgresql-data-5g pvc-27866fc8-77df-4fe6-8397-e69f3fa0fa7d pvc-bd4b4e52-0a71-4690-aade-ad99b1cddfe6 pvc-773cc06e-4984-4bcf-ae38-64fe77f68a5c superset-pg18-data -n storage -o jsonpath='{.items[*].status.robustness}'
    expect_exact: "healthy healthy healthy healthy healthy"
  - id: init-jobs-current-names
    why: >-
      Stage 3b renames three init Jobs (v1a/v1a/v9a -> v1b/v1b/v9b). Fewer than 3 means a Job was already renamed or TTL-pruned
      (ttlSecondsAfterFinished is 7d): re-derive the names before editing.
    run: kubectl get job -n databases -o name | grep -c -e init-v1a -e init-v9a
    expect_exact: "3"
  - id: no-restore-proof-leftovers
    why: backup-restore-proof.py REFUSES to start (exit 2) if a previous run left scratch volumes labelled restore-proof=true.
    run: kubectl get volumes.longhorn.io -n storage -l restore-proof=true -o name | wc -l
    expect_exact: "0"
  - id: main-still-old-digest
    why: >-
      origin/main still carries the OLD shared digest exactly once. 0 means #463 (or a hand edit) already landed. Run `git fetch origin`
      first or this reads a stale ref.
    run: git show origin/main:kubernetes/apps/databases/postgresql/app/deployment.yaml | grep -c 7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a
    expect_exact: "1"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/immutable-job-image-bumps.md
  - docs/sops/postgres-major-upgrade.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-08"
---

# postgres-digest-refresh-2026-11

## 1. Summary & why held

**What changes.** Two Renovate digest PRs on the same family of images, delivered as one plan so the databases restart once each, in a
controlled order, with a restore proof and per-database gates in between:

| PR | image (tag unchanged) | old digest | new digest | what runs it |
|---|---|---|---|---|
| #463 | `pgvector/pgvector:0.8.7-pg16` | `7b822b0aac60...` (built 2026-10-01) | `0dd3149a06e4...` (built 2026-10-31) | **shared `databases/postgresql`**, `office/affine-pg`, `office/sure-pg`, and the init Jobs `oc8-db`, `ninth-banner-feedback-db`, `sweep-history` |
| #227 | `postgres:18.6-alpine` | `d3e1620b530c...` (index) | `123b17998ccaf...` (index, built 2026-11-05) | `databases/superset-pg18`, CronJobs `sweep-heartbeat`, `authentik-channels-cleanup`, `authentik-db-probe`, `media-library-audit` |
| #227 | same tag, **amd64 child manifest** | `63bdc97d67b5...` | `300ebd02c6d4...` | `ai/paperclip-postgresql` (the only consumer that pins the child, not the index) |

Full digests are in section 3. Measured against the registry 2026-11-08: the new pgvector image reports `PG_VERSION=16.15-1.pgdg12+2` and the
new alpine images `PG_VERSION=18.6`, **identical to the images they replace**. So this is a base-layer rebuild of the same PostgreSQL minor and
the same pgvector tag - not a version change. `63bdc97`/`300ebd0` were confirmed to be the `linux/amd64` children of `d3e1620`/`123b179`.

**Why it is held.** The auto-updater's `update_type=unknown` (digest, no semver) is not auto-applicable (`runbooks/auto-update.py` dry-run:
`#463 ... update_type=unknown (only patch/minor auto-apply)`; `#227` title not in the `update <dep> ( x -> y )` shape). It is also a restart
of five stateful, in-use databases, one of them shared by seven clients and the sweep's own history store. The bump itself is expected to be
boring; the plan exists because the failure modes are not (clients that do not reconnect, a volume that does not re-attach, a Job that cannot
be re-applied).

**History worth knowing (F-63bfde8b).** The pgvector 0.8.7 bump was auto-reverted twice in October (10-14, re-merged as #362 on 10-17, a 7-PR batch reverted again;
the finding records that auto-revert does not hold the culprit). That is why this refresh is planned, staged and human-gated instead of landing through Step 0.
The Kustomization `authentik` (kube-system, `wait: false`, `timeout: 5m`) also reconciles in stage 1 because two CronJobs live in it: it is applied as a whole, so a
pre-existing unhealthy object there would show as that Kustomization NotReady (check `flux get ks -A` in 2.4 first); `wait: false` means it does not block the stage.

**The one thing the PRs get WRONG as written.** #463 edits the `image:` line of three standalone init Jobs in place
(`databases/oc8-db`, `ninth-banner-feedback-db`, `sweep-history`). A Job's `.spec.template` is immutable: Flux's apply fails with
`field is immutable`, the Kustomization goes NotReady and - for `oc8-db`, which has `wait: true` - stays that way, silently stopping that app path
(`docs/sops/immutable-job-image-bumps.md` s.1). The house fix is the `vN` rename (their header comments say so). **Do not merge #463 as is.**
Stage 3b applies the same digest WITH the rename. #227 has no Jobs, only CronJobs (mutable template) and Deployments.

**Is anything beyond a pod restart needed? No.**
- *Extensions*: the tag is unchanged (`0.8.7`), so the pgvector control file version is unchanged; no `ALTER EXTENSION`. (Observed and NOT in scope:
  db `oc8` records `vector 0.8.6`, `affine` `0.8.1`, `sure` `0.8.6` - they lag the installed 0.8.7 already; a digest refresh does not change that.)
- *Collation*: the pgvector image is Debian bookworm (glibc 2.36, recorded `datcollversion` 2.36 in every database, measured). A rebuild on the same
  Debian release keeps glibc 2.36; a glibc bump would flag every index on text columns as suspect. Gate G6 asserts it explicitly. The alpine
  images (musl) record no collation version (`-`), also asserted.
- *Config / initdb*: nothing is re-initialised - `PGDATA` already exists on each volume, the entrypoint skips initdb, and `/docker-entrypoint-initdb.d` scripts do not re-run.
- *Data format*: PostgreSQL's versioning policy states that minor releases never change the internal storage format and are compatible with earlier
  and later minor releases of the same major. Here even the minor is identical (16.15/16.15, 18.6/18.6).

**Residual stateful risk (why this is human-gated and `risk: medium`).** (a) A shutdown that cannot finish its checkpoint inside the 30 s grace
period leaves crash recovery for the new pod (G3 catches it; the previous restarts on 2026-09-27 and 2026-10-12 both logged a clean
"database system was shut down"). (b) A volume that does not re-attach cleanly. (c) A client that never reconnects. (d) The shared server has
no `PostgresDown`-style alert in the repo (only sure, superset, paperclip, authentik, mealie, immich have one), so its outage is only visible
through the gates below.

**Out of scope (listed so nobody folds them in):**
- **#411** `postgres:16-alpine` digest - already merged; it is the ephemeral CI-runner sidecar (`ci-runner` namespace), not a database we run.
- **#294** `postgres` to v18 (major) - a datadir major migration, own plan and own decision; `docs/sops/postgres-major-upgrade.md` applies.
- **#282** `ghcr.io/immich-app/postgres` 14 -> 16 - a datadir major migration on a denied component; not a digest refresh.
- The floating-tag servers `authentik-pg` (`18.6-bookworm`), `mealie-pg` (`18.6-bookworm`), `teslamate-postgres`, `traccar-postgres`, `penpot-db` (`18.6`) carry
  no digest pin, have no Renovate PR, and are not touched. There is no further sibling digest PR for these instances (checked: `gh pr list` open set
  2026-11-08; `git grep` of the three old digests over `origin/main` finds exactly the 12 lines in #463 + #227, plus prose in `paperclip-postgresql-18.6.md`).

**Security.** The registry's accepted-risk entries for these two image names are tracked under `security_ref`; this plan states no per-image
vulnerability facts (public repo; see `docs/sops/vulnerability-disclosure.md`). A newer digest exists, which is the only remediation this
household performs for a third-party image.

## 2. Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` on the Mac. Everything here is read-only against the cluster except the scratch objects of the
restore proofs (labelled `restore-proof=true`, removed by the script). Use **bash** for the helper script (the repo's zsh scalar-splitting
trap bites path lists); the commands below are one-per-line on purpose.

**2.1 Working directory and the gate script.** `$W` holds a database dump (role password hashes included): mode 700, outside the repo, deleted in 6.

```bash
export W="$HOME/.cache/pgdr-$(date +%Y%m%d)"; mkdir -p -m 700 "$W"
cat > "$W/pgdr.sh" <<'PGDR_EOF'
#!/usr/bin/env bash
# pgdr.sh snap|verify|tblcheck|selftest <shared|affine|sure|superset|paperclip> [target-digest-hex | database]
# Read-only against the cluster (kubectl get/logs/exec + SELECTs). Needs $W (mode-700 scratch dir).
set -uo pipefail
W=${W:?set W first}
MODE=${1:?}; INST=${2:-}; WANT=${3:-}
CRASH_RE='automatic recovery in progress'
CLEAN_RE='database system was shut down at'
if [ "$MODE" = selftest ]; then   # proves the G3 absence gate CAN fail (known-bad replay)
  echo 'LOG:  database system was not properly shut down; automatic recovery in progress' | grep -qi "$CRASH_RE" || { echo "SELFTEST FAIL: crash line not detected"; exit 1; }
  echo 'LOG:  database system was shut down at 2026-10-12 11:18:59 UTC' | grep -qi "$CRASH_RE" && { echo "SELFTEST FAIL: clean line flagged as crash"; exit 1; }
  echo 'LOG:  database system was shut down at 2026-10-12 11:18:59 UTC' | grep -qi "$CLEAN_RE" || { echo "SELFTEST FAIL: clean anchor missed"; exit 1; }
  echo 'LOG:  database system was not properly shut down; automatic recovery in progress' | grep -qi "$CLEAN_RE" && { echo "SELFTEST FAIL: crash line matched the clean anchor"; exit 1; }
  echo "SELFTEST OK (crash line trips G3; clean line passes; anchors do not cross-match)"; exit 0
fi
[ -n "$INST" ] || { echo "instance required"; exit 2; }
case $INST in
  shared)    NS=databases; D=postgresql;            SEL=app=postgresql;                              ROLE=postgres;  DBS="nocodb oc8 sweep_history ninth_banner_feedback pellets"; DEB=1;;
  affine)    NS=office;    D=affine-pg;             SEL=app.kubernetes.io/instance=affine-pg;        ROLE=affine;    DBS="affine";     DEB=1;;
  sure)      NS=office;    D=sure-pg;               SEL=app.kubernetes.io/instance=sure-pg;          ROLE=sure;      DBS="sure";       DEB=1;;
  superset)  NS=databases; D=superset-pg18;         SEL=app=superset-pg18;                           ROLE=superset;  DBS="superset";   DEB=0;;
  paperclip) NS=ai;        D=paperclip-postgresql;  SEL=app=paperclip-postgresql;                    ROLE=paperclip; DBS="paperclip";  DEB=0;;
  *) echo "unknown instance $INST"; exit 2;;
esac
q() { kubectl exec -i -n "$NS" "deploy/$D" -- psql -U "$ROLE" -d "$1" -At; }
TBL="select schemaname||'.'||tablename||' '||(xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', schemaname, tablename), false, true, '')))[1]::text from pg_tables where schemaname not in ('pg_catalog','information_schema') order by 1;"
COLL="select datname||' '||coalesce(datcollversion,'-')||' '||coalesce(pg_database_collation_actual_version(oid),'-') from pg_database where not datistemplate order by 1;"
START="select extract(epoch from pg_postmaster_start_time())::bigint;"
COMMITS="select datname||'='||xact_commit from pg_stat_database where datname is not null and datname not like 'template%' and datname<>'postgres' order by 1;"
# Per-table rule. STATIC tables must be EXACT. Every other table may not shrink by more than max(2, 2%).
# Growth is silent only where listed in GROW_OK (sweep_history: sweep_findings, sweep_cycles); any other table whose
# count moves UP is printed as CHANGED and fails when the table is STATIC.
static_re() { case $1 in
  sweep_history) echo '^public\.(accepted_risks|slo_definitions|noise_suppressions|security_acceptances|component_autonomy|media_audit_runs|slo_snapshots|window_runs|plan_executions) ';;
  superset)      echo '^public\.ab_';;
  *)             echo '^$^';; esac; }
tblcmp() {   # tblcmp <db> : live per-table counts vs $W/$INST.<db>.tbl ; returns 0 pass, 1 fail ; prints one line per table that differs
  local db=$1
  echo "$TBL" | q "$db" > "$W/$INST.$db.tbl.now" || { echo "TBLCMP FAILED: query $db"; return 1; }
  python3 - "$W/$INST.$db.tbl" "$W/$INST.$db.tbl.now" "$(static_re "$db")" "$db" <<'PY'
import sys, re
def load(p): return {l.rsplit(" ", 1)[0]: int(l.rsplit(" ", 1)[1]) for l in open(p) if l.strip()}
a, b, static, db = load(sys.argv[1]), load(sys.argv[2]), re.compile(sys.argv[3]), sys.argv[4]
grow_ok = {"sweep_history": {"public.sweep_findings", "public.sweep_cycles"}}.get(db, set())
bad = []
if set(a) != set(b): bad.append(f"table set differs: missing={sorted(set(a)-set(b))} new={sorted(set(b)-set(a))}")
for t in sorted(set(a) & set(b)):
    x, y = a[t], b[t]
    st = bool(static.search(t + " "))
    if st and x != y: bad.append(f"STATIC {t}: {x} -> {y}")
    elif not st and y < x - max(2, x // 50): bad.append(f"{t}: {x} -> {y} (shrank more than max(2, 2%))")
    if x != y and t not in grow_ok: print(f"   changed {t}: {x} -> {y}")
print("   tables=%d  total rows %d -> %d" % (len(b), sum(a.values()), sum(b.values())))
for m in bad: print("   BAD " + m)
sys.exit(1 if bad else 0)
PY
}
if [ "$MODE" = snap ]; then
  for db in $DBS; do echo "$TBL" | q "$db" > "$W/$INST.$db.tbl" || { echo "SNAP FAILED $INST/$db"; exit 1; }
    [ -s "$W/$INST.$db.tbl" ] || { echo "SNAP FAILED $INST/$db: empty table list"; exit 1; }; done
  echo "$COLL"  | q postgres > "$W/$INST.coll"  || { echo "SNAP FAILED coll"; exit 1; }
  echo "$START" | q postgres > "$W/$INST.start" || { echo "SNAP FAILED start"; exit 1; }
  echo "SNAP OK $INST: $(for db in $DBS; do printf '%s tables=%s rows=%s; ' "$db" "$(wc -l < "$W/$INST.$db.tbl" | tr -d ' ')" "$(awk '{s+=$NF} END{print s}' "$W/$INST.$db.tbl")"; done)start=$(cat "$W/$INST.start")"; exit 0
fi
if [ "$MODE" = tblcheck ]; then   # tblcheck <inst> <db> : exact per-table diff against the last snap (stage 3b gate)
  db=${WANT:?database name}; tblcmp "$db" && { echo "TBLCHECK PASS [$INST/$db]"; exit 0; } || { echo "TBLCHECK FAIL [$INST/$db]"; exit 1; }
fi
# ---- verify ----
FAIL=0; bad() { echo "GATE FAIL [$INST] $*"; FAIL=1; }
[ -n "$WANT" ] || { echo "verify needs the target digest hex"; exit 2; }
# G1 exactly one pod, running the TARGET digest (rollout status green-lights the old generation)
PODS=$(kubectl get pod -n "$NS" -l "$SEL" -o jsonpath='{.items[*].metadata.name}')
[ "$(echo $PODS | wc -w)" -eq 1 ] || bad "expected 1 pod, got: $PODS"
IMG=$(kubectl get pod -n "$NS" -l "$SEL" -o jsonpath='{.items[0].status.containerStatuses[0].imageID}')
case $IMG in *"$WANT"*) echo "G1 ok imageID=$IMG";; *) bad "G1 imageID=$IMG does not contain $WANT";; esac
kubectl get pod -n "$NS" -l "$SEL" -o jsonpath='{.items[0].status.containerStatuses[0].ready}' | grep -q true || bad "G1 container not ready"
# G2 postmaster really restarted
NEW=$(echo "$START" | q postgres); OLD=$(cat "$W/$INST.start")
[ "${NEW:-0}" -gt "$OLD" ] && echo "G2 ok postmaster start $OLD -> $NEW" || bad "G2 postmaster start did not advance ($OLD -> ${NEW:-none})"
# G3 POSITIVE anchor (clean shutdown line + ready line) AND the crash-recovery absence. Fresh pod only: a pod whose log has rotated
# reads "no clean-shutdown line" and fails, which is correct for a NEW pod and expected for an OLD one. Run `selftest` first.
LOG=$(kubectl logs -n "$NS" -l "$SEL")
echo "$LOG" | grep -qi "$CLEAN_RE" && echo "G3 ok clean-shutdown line present" || bad "G3 no '$CLEAN_RE' line (not a clean start, or not a fresh pod)"
echo "$LOG" | grep -qi "$CRASH_RE" && bad "G3 crash recovery ran" || echo "G3 ok no crash recovery"
echo "$LOG" | grep -qi 'database system is ready to accept connections' || bad "G3 no ready line"
echo "$LOG" | grep -qi 'collation version' && bad "G3 collation-version warning in log"
# G4 PGDATA is on the Longhorn device, not the container layer
DEV=$(kubectl exec -n "$NS" "deploy/$D" -- df -P /var/lib/postgresql/data | tail -1 | awk '{print $1}')
case $DEV in /dev/longhorn/*) echo "G4 ok PGDATA device $DEV";; *) bad "G4 PGDATA device is '$DEV'";; esac
# G5 contents, PER TABLE: same table set; STATIC tables exact; others may not shrink by more than max(2, 2%)
for db in $DBS; do
  echo "G5 $db:"; tblcmp "$db" || bad "G5 $db per-table comparison failed (see BAD lines above)"
done
# G6 collation: glibc images keep the recorded version; musl images record none
BAD=$(echo "$COLL" | q postgres | awk -v deb=$DEB '{ if (deb==1 && ($2!="2.36" || $3!="2.36")) print; if (deb==0 && ($2!="-" || $3!="-")) print }')
[ -z "$BAD" ] && echo "G6 ok collation versions unchanged" || bad "G6 collation drift: $BAD"
# G7 clients reconnected: xact_commit of every app DB must GROW after the pod is Ready (poll up to 10 min)
echo "$COMMITS" | q postgres > "$W/$INST.c0"; END=$(( $(date +%s) + 600 ))
while :; do
  sleep 30; echo "$COMMITS" | q postgres > "$W/$INST.c1"
  STILL=$(python3 - "$W/$INST.c0" "$W/$INST.c1" <<'PY'
import sys
a=dict(l.strip().split("=") for l in open(sys.argv[1]) if "=" in l)
b=dict(l.strip().split("=") for l in open(sys.argv[2]) if "=" in l)
print(" ".join(k for k in a if int(b.get(k,0))<=int(a[k])))
PY
)
  [ -z "$STILL" ] && { echo "G7 ok every app database is being committed to by its clients"; break; }
  [ "$(date +%s)" -ge "$END" ] && { bad "G7 no client commits after 10 min on: $STILL"; break; }
done
[ $FAIL -eq 0 ] && echo "STAGE GATE PASS [$INST]" || { echo "STAGE GATE FAIL [$INST]"; exit 1; }
PGDR_EOF
bash -n "$W/pgdr.sh" && echo SYNTAX-OK        # expect SYNTAX-OK
bash "$W/pgdr.sh" selftest                   # expect SELFTEST OK ... (replays a literal crash-recovery log line and proves gate G3 trips on it)
```

**2.2 Repo state.** ADVISORY (the empty `git status` is an absence check; it cannot prove nobody else is mid-edit, `git commit --only` is the real protection). The local checkout may be behind (it was 12 commits behind on 2026-11-08).

```bash
git fetch origin && git merge --ff-only origin/main
git status --short -- kubernetes/apps/ai/paperclip kubernetes/apps/databases kubernetes/apps/office/affine kubernetes/apps/office/sure kubernetes/apps/kube-system/authentik kubernetes/apps/media/library-tools
# PASS: the git status prints NOTHING (no foreign edits in the 12 files). Anything printed: stop, find the owner (shared worktree).
gh pr view 463 --json state,headRefOid -q .state     # PASS: OPEN. (MERGED/CLOSED: re-run the premises; the work may be partly done.)
gh pr view 227 --json state -q .state                # PASS: OPEN
```

**2.3 The digests the registry serves TODAY for these tags** (Renovate may have moved the PRs again; plan digests are only valid if the tag still resolves to them).

```bash
python3 - <<'PY'
import json, urllib.request
def dig(repo, tag):
    tok = json.load(urllib.request.urlopen(f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"))["token"]
    acc = "application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json"
    r = urllib.request.Request(f"https://registry-1.docker.io/v2/{repo}/manifests/{tag}", method="HEAD", headers={"Authorization": "Bearer " + tok, "Accept": acc})
    return urllib.request.urlopen(r).headers["docker-content-digest"]
print("pgvector 0.8.7-pg16 :", dig("pgvector/pgvector", "0.8.7-pg16"))
print("postgres 18.6-alpine:", dig("library/postgres", "18.6-alpine"))
PY
```
PASS (measured 2026-11-08): `sha256:0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f` and
`sha256:123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395`. **If either differs, the tag has been rebuilt again:** STOP,
take the digest from the CURRENT Renovate PR branch, re-run section 1's `PG_VERSION` comparison (the config blob `Env`) and substitute it for
every occurrence below (the paperclip child digest must be re-derived from the new index: `manifests[]` entry with `platform.architecture=amd64`).
A digest nobody compared is not a refresh.

**2.4 Cluster baseline.**

```bash
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
# PASS: "No resources found". Anything listed: explain it before continuing.
flux get ks -A | awk 'NR==1 || $5 != "True"'
# PASS: only the header line. A NotReady Kustomization will mask a stage failure.
kubectl get volumes.longhorn.io -n storage -l restore-proof=true -o name | wc -l            # PASS: 0
```

**2.5 Backups are fresh AND the newest one restores on the NEW image.** The proofs cannot touch live data: Longhorn restores into a NEW volume, the scratch pod/PVC/PV are
labelled `restore-proof=true`, and the script removes them. `runbooks/backup-restore-proof.py` was FIXED for this plan (uncommitted working-tree edit, tests passing, see section 6):
the scratch PV/PVC is now sized from the SOURCE volume's `spec.size` (it hardcoded 5Gi) and `--image` is REQUIRED (it defaulted to the stale `0.8.6-pg16`).

```bash
python3 runbooks/longhorn-backup-age.py postgresql-data-5g pvc-27866fc8-77df-4fe6-8397-e69f3fa0fa7d pvc-bd4b4e52-0a71-4690-aade-ad99b1cddfe6 pvc-773cc06e-4984-4bcf-ae38-64fe77f68a5c superset-pg18-data --max-hours 26 | tee "$W/backup-age.txt"; echo "rc=${PIPESTATUS[0]}"
grep -c ' FRESH ' "$W/backup-age.txt"        # PASS: 5 and rc=0. A STALE/NONE line exits 1 (measured fresh, 19.4 h, 2026-11-08).
```
Volume names: shared `postgresql-data-5g`, affine `pvc-27866fc8-...`, sure `pvc-bd4b4e52-...`, paperclip `pvc-773cc06e-...`, superset `superset-pg18-data`.

**ONE RULE for every restore proof, wherever it runs:** exit 0 with a `RESTORE PROVEN: ...` line is the only pass. Exit 1 (`RESTORE PROOF FAILED`) or 2 (`INCONCLUSIVE` / precondition)
means STOP: that database is NOT restarted, and the cause is found before the plan continues. There is no "record it and rely on the dump" branch any more - the one cause that used to
justify it (the 5Gi capacity mismatch on the 20Gi volumes) is fixed in the script, so a failure now says something about the backup. (An INCONCLUSIVE is upgraded by re-running with the right
`--superuser`; that re-run is the proof, the first run is not.)

**2.5a PRE-WINDOW prerequisite (any day before the window, non-destructive, label-scoped, ONE AT A TIME): the three 20Gi sources - affine, sure, superset.** These are the slow proofs
(a 20Gi Longhorn restore from the NAS backup target); doing them in-window cost ~25 minutes of an attended slot for no reason. Run them on a quiet day, not during a sweep or a backup run
(`kubectl get volumes.longhorn.io -n storage -l restore-proof=true -o name | wc -l` must read 0 first), strictly serially. They use the TARGET images from 2.3; if the registry digest moves
before the window (2.3 re-check), a proof taken on the old target is void for the new digest and must be re-run.

```bash
python3 runbooks/backup-restore-proof.py --volume pvc-27866fc8-77df-4fe6-8397-e69f3fa0fa7d --superuser affine --namespace databases --smoke-table affine.users --image pgvector/pgvector:0.8.7-pg16@sha256:0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f
python3 runbooks/backup-restore-proof.py --volume pvc-bd4b4e52-0a71-4690-aade-ad99b1cddfe6 --superuser sure --namespace databases --smoke-table sure.users --image pgvector/pgvector:0.8.7-pg16@sha256:0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f
python3 runbooks/backup-restore-proof.py --volume superset-pg18-data --superuser superset --namespace databases --smoke-table superset.ab_user --image postgres:18.6-alpine@sha256:123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395
kubectl get volumes.longhorn.io -n storage -l restore-proof=true -o name | wc -l            # PASS: 0 after each one (scratch removed)
```
PASS per proof: exit 0 and `RESTORE PROVEN: backup <name> (<ts>) boots postgres with N databases as superuser '<role>', <db.table>=<rows> rows`. What it can fail on: a backup that does not boot (never-ready, exit 1),
a missing superuser (exit 2), a smoke table that is absent (`SELECT count(*)` errors, exit 1), or fewer than 3 databases. It proves the restore is non-empty and starts on the new image, not that it is current (2.6 covers recency).

RECORD THE RESULTS HERE (edit this table when each proof is run; the window agent refuses to start with any row not `PROVEN`, or with a proof older than 14 days or taken on a different digest than 2.3 resolved):

| volume | image digest used | backup name / snapshot time | result (exit, RESTORE PROVEN line) | date |
|---|---|---|---|---|
| affine `pvc-27866fc8-...` (20Gi) | pgvector `7b822b0aac60` (CURRENT live digest; window proves `0dd3149a06e4`) | backup-0646733ade284dc2 (2026-11-08T23:06:14Z) | exit 0, PROVEN: 4 databases as superuser 'affine', affine.users=1 rows | 2026-11-09 |
| sure `pvc-bd4b4e52-...` (20Gi) | pgvector `7b822b0aac60` (CURRENT live digest; window proves `0dd3149a06e4`) | backup-c47849c4b21d4989 (2026-11-08T23:08:22Z) | exit 0, PROVEN: 4 databases as superuser 'sure', sure.users=1 rows | 2026-11-09 |
| superset `superset-pg18-data` (20Gi) | postgres alpine `d3e1620b530c` (CURRENT live digest; window proves `123b17998cca`) | backup-8216553292024639 (2026-11-08T23:09:04Z) | exit 0, PROVEN: 4 databases as superuser 'superset', superset.ab_user=2 rows | 2026-11-09 |

**2.5b IN-WINDOW proofs: the two 5Gi sources** (shared, paperclip; ~5 minutes each), same rule.

```bash
python3 runbooks/backup-restore-proof.py --volume postgresql-data-5g --superuser postgres --namespace databases --smoke-table sweep_history.sweep_findings --image pgvector/pgvector:0.8.7-pg16@sha256:0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f
python3 runbooks/backup-restore-proof.py --volume pvc-773cc06e-4984-4bcf-ae38-64fe77f68a5c --superuser paperclip --namespace databases --pgdata /var/lib/postgresql/data/postgres18/pgdata --smoke-table paperclip.agents --image postgres:18.6-alpine@sha256:300ebd02c6d4de9ee27ad7f6855d5d21b4d3a4a5117767c1197d284c635d9736
kubectl get volumes.longhorn.io -n storage -l restore-proof=true -o name | wc -l            # PASS: 0
```
The paperclip `--pgdata` is `postgres18/pgdata` because its Deployment mounts the volume with `subPath: postgres18` (verified: the pod's `/var/lib/postgresql/data` contains only `pgdata`).

**2.6 Fresh logical dump (the floor for anything the nightly backup, up to 25 h old, would miss).** Plain-SQL `pg_dumpall` per instance, streamed to the Mac.

```bash
kubectl exec -n databases deploy/postgresql -- pg_dumpall -U postgres > "$W/shared.sql"
kubectl exec -n office deploy/affine-pg -- pg_dumpall -U affine > "$W/affine.sql"
kubectl exec -n office deploy/sure-pg -- pg_dumpall -U sure > "$W/sure.sql"
kubectl exec -n databases deploy/superset-pg18 -- pg_dumpall -U superset > "$W/superset.sql"
kubectl exec -n ai deploy/paperclip-postgresql -- pg_dumpall -U paperclip > "$W/paperclip.sql"
for f in shared affine sure superset paperclip; do printf '%s bytes=%s trailer=%s\n' "$f" "$(wc -c < "$W/$f.sql" | tr -d ' ')" "$(tail -c 300 "$W/$f.sql" | grep -c 'database cluster dump complete')"; done
```
PASS (floors are ~50% of the sizes measured 2026-11-08: shared 849 MB, affine 19 MB, sure 62 MB, superset 2.7 MB, paperclip 80 MB): every `trailer=1`
(a truncated stream - lost connection, killed exec - lacks the trailer comment) and bytes >= `shared 400000000`, `affine 9000000`, `sure 30000000`,
`superset 1000000`, `paperclip 40000000`. Any `trailer=0` or short file: re-dump that instance; do not proceed on a partial dump.

**2.7 Pre-change per-TABLE snapshots** (exact count of every user table in every database; re-taken immediately before each stage in section 3, this run proves the script reads every instance).

```bash
for i in shared affine sure superset paperclip; do bash "$W/pgdr.sh" snap "$i"; done
```
PASS: five `SNAP OK <inst>: ...` lines. Measured 2026-11-08: shared `nocodb tables=188 rows=90119, oc8 71/170, sweep_history 11/11235, ninth_banner_feedback 6/2443,
pellets 10/10172`; affine `93/~349100`; sure `132/237734`; superset `53/3718`; paperclip `37/11484`. The sweep_history policy tables (the ones nothing else regenerates) read, exactly: `accepted_risks 119, slo_definitions 7, noise_suppressions 39, security_acceptances 118` (plus `component_autonomy 188, media_audit_runs 47, slo_snapshots 699, window_runs 146, plan_executions 148, sweep_cycles 735, sweep_findings 8989`). A `SNAP FAILED` line (role, pod or query problem) aborts: every later gate depends on it.

**2.8 No overlapping consumer.** Confirm the sweep is not running (`runbooks/sweep-run.py` holds a port-forward to the shared server) and no
conflicting plan is in flight.

```bash
ps -axo pid,command | grep -E 'sweep-run\.py|auto-update\.py --apply' | grep -v grep
# ADVISORY (an absence check: it only sees this Mac): empty. A running sweep or Step-0 apply: wait for it, then re-run 2.4.
ps -axo pid,command | grep -E 'port-forward.*(postgresql|5432)' | grep -v grep
# ADVISORY: empty. runbooks/alert-record.py and the sweep helper hold a `kubectl port-forward` to the shared server; a hit means a sweep/alert-record is live and its
# connection WILL drop at stage 3a. Tell the alert-watcher / ops console that the shared server restarts at <time> so the drop is not read as an incident.
python3 runbooks/maintenance-plan.py --open | grep -E 'longhorn-1.13.0|talos-linux-1.14.5|redis-fleet-8.10.3|coredns-1.50.2|grafana-chart-14.4.0|helm-drift-detection'
# PASS: none of these is stamped for TODAY's window.
```

## 3. Steps

GitOps only: edit, commit, push `main`, let Flux reconcile (no manual `flux reconcile`). Three commits (four with 3b) so each blast radius is verified
before the next. Commits use `git commit --only <paths> -F <msgfile>`; after each, `git log -1 --format=%s` must show YOUR subject before `git push`
(shared worktree, CLAUDE.md). BSD `sed` syntax below (`sed -i ''`) is correct on the Mac and was dry-tested on scratch copies of the `origin/main` files
2026-11-08; the resulting diff is quoted. The old digests occur exactly once per file, so each `s///` changes exactly one line.

Before EACH stage: re-take the fingerprints of that stage's instances (`bash "$W/pgdr.sh" snap <inst>`), record the UTC time, and run
`kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded` (must be empty).

### Stage 1 - paperclip-postgresql + superset-pg18 (+ four CronJobs): smallest blast radius first

Digests: superset index `d3e1620b...a65b2 -> 123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395`; paperclip child
`63bdc97d...07e8 -> 300ebd02c6d4de9ee27ad7f6855d5d21b4d3a4a5117767c1197d284c635d9736`.

```bash
bash "$W/pgdr.sh" snap paperclip; bash "$W/pgdr.sh" snap superset; date -u +%FT%TZ
sed -i '' 's/63bdc97d67b5133bf0e5ebd500bec6d046fa851dc81340d838f0347e616107e8/300ebd02c6d4de9ee27ad7f6855d5d21b4d3a4a5117767c1197d284c635d9736/' kubernetes/apps/ai/paperclip/app/postgresql.yaml
sed -i '' 's/d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2/123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395/' kubernetes/apps/databases/superset/app/pg18-deployment.yaml
sed -i '' 's/d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2/123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395/' kubernetes/apps/databases/sweep-history/app/heartbeat-cronjob.yaml
sed -i '' 's/d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2/123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395/' kubernetes/apps/kube-system/authentik/app/cronjob-channels-cleanup.yaml
sed -i '' 's/d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2/123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395/' kubernetes/apps/kube-system/authentik/app/cronjob-db-probe.yaml
sed -i '' 's/d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2/123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395/' kubernetes/apps/media/library-tools/app/audit-cronjob.yaml
git diff --stat | tail -1
git diff -U0 | grep -c '^+ *image: postgres:18.6-alpine@sha256:\(123b1799\|300ebd02\)'
```
Expected: `6 files changed, 6 insertions(+), 6 deletions(-)` and `6`. Dry-test result for the paperclip file:
`-        image: postgres:18.6-alpine@sha256:63bdc97d...` / `+        image: postgres:18.6-alpine@sha256:300ebd02c6d4...` (line 67). A count other than 6 means a pattern
matched nothing or twice: `git checkout -- <file>` and stop.

```bash
printf 'chore(container): refresh postgres:18.6-alpine digest d3e1620->123b179 (paperclip child 63bdc97->300ebd0)\n\nSame PG 18.6; superset-pg18, paperclip-postgresql, 4 CronJobs. Delivers Renovate #227 (maintenance plan postgres-digest-refresh-2026-11, stage 1).\n' > "$W/msg1.txt"
git commit --only kubernetes/apps/ai/paperclip/app/postgresql.yaml kubernetes/apps/databases/superset/app/pg18-deployment.yaml kubernetes/apps/databases/sweep-history/app/heartbeat-cronjob.yaml kubernetes/apps/kube-system/authentik/app/cronjob-channels-cleanup.yaml kubernetes/apps/kube-system/authentik/app/cronjob-db-probe.yaml kubernetes/apps/media/library-tools/app/audit-cronjob.yaml -F "$W/msg1.txt"
git log -1 --format=%s ; git show --stat HEAD | tail -8      # subject must be YOURS and the stat must list exactly the six files
git push origin main
```
Then wait for the Deployments to roll (a wait only, not the verdict): `kubectl rollout status deploy/paperclip-postgresql -n ai --timeout=300s` and
`kubectl rollout status deploy/superset-pg18 -n databases --timeout=300s`. Then run the section 4 stage gate for `paperclip` and `superset`.
**Do not start stage 2 until both print `STAGE GATE PASS`.**

### Stage 2 - affine-pg + sure-pg (HelmReleases)

```bash
bash "$W/pgdr.sh" snap affine; bash "$W/pgdr.sh" snap sure; date -u +%FT%TZ
sed -i '' 's/7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a/0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f/' kubernetes/apps/office/affine/app/postgres-helmrelease.yaml
sed -i '' 's/7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a/0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f/' kubernetes/apps/office/sure/app/postgres-helmrelease.yaml
git diff --stat | tail -1                                            # expect: 2 files changed, 2 insertions(+), 2 deletions(-)
git diff -U0 | grep '^[-+] *tag:'                                    # expect the old/new pair for each file
```
Dry-test diff line (both files, line 40): `-              tag: 0.8.7-pg16@sha256:7b822b0aac60...` / `+              tag: 0.8.7-pg16@sha256:0dd3149a06e4...`.

```bash
printf 'chore(container): refresh pgvector/pgvector 0.8.7-pg16 digest 7b822b0->0dd3149 (affine-pg, sure-pg)\n\nSame PG 16.15 / pgvector 0.8.7. Delivers Renovate #463 part 1 (maintenance plan postgres-digest-refresh-2026-11, stage 2).\n' > "$W/msg2.txt"
git commit --only kubernetes/apps/office/affine/app/postgres-helmrelease.yaml kubernetes/apps/office/sure/app/postgres-helmrelease.yaml -F "$W/msg2.txt"
git log -1 --format=%s ; git show --stat HEAD | tail -4
git push origin main
```
Wait: `kubectl rollout status deploy/affine-pg -n office --timeout=300s` and `deploy/sure-pg`; then the stage gate for `affine` and `sure`.

### Stage 3a - the shared server (largest blast radius, last)

Immediately before: confirm no sweep is running (`ps` check from 2.8) and re-snap.

```bash
bash "$W/pgdr.sh" snap shared; date -u +%FT%TZ
sed -i '' 's/7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a/0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f/' kubernetes/apps/databases/postgresql/app/deployment.yaml
git diff --stat | tail -1                                            # expect: 1 file changed, 1 insertion(+), 1 deletion(-)
printf 'chore(container): refresh pgvector/pgvector 0.8.7-pg16 digest 7b822b0->0dd3149 (shared postgresql)\n\nSame PG 16.15 / pgvector 0.8.7; maxSurge 0 keeps the RWO volume from Multi-Attach. Delivers Renovate #463 part 2 (maintenance plan postgres-digest-refresh-2026-11, stage 3a).\n' > "$W/msg3a.txt"
git commit --only kubernetes/apps/databases/postgresql/app/deployment.yaml -F "$W/msg3a.txt"
git log -1 --format=%s ; git show --stat HEAD | tail -3
git push origin main
```
Expected downtime of the shared server: ~1-3 min (the 2026-09-27 paperclip roll took 2 min 47 s from shutdown to ready, mostly volume detach/attach and image pull; the
postgres process itself is ready ~1 s after start). During it nocodb, oc8 (4 Deployments), Grafana's "Pellets" panels, `sweep-dashboard`, `the-ninth-banner` feedback
and the `pallet-price-monitor` CronJob get connection errors. That is the accepted interruption. Wait: `kubectl rollout status deploy/postgresql -n databases --timeout=300s`; then the stage gate for `shared`.

### Stage 3b - the three init Jobs (rename, NOT an in-place edit) - only after 3a passed

**SOP `docs/sops/immutable-job-image-bumps.md` section 4a read-through - VERDICT (planner, 2026-11-08; the executor re-reads the three scripts at the window and records agreement or STOPS):**
- (a) read end-to-end: `databases/sweep-history/app/schema-configmap.yaml`, `databases/oc8-db/app/bootstrap-configmap.yaml`, `databases/ninth-banner-feedback-db/app/bootstrap-configmap.yaml`. DONE.
- (b) idempotent forms only: guarded `CREATE ROLE`/`CREATE DATABASE` (`SELECT 1 ... | grep -q 1 || CREATE`), `CREATE TABLE/INDEX IF NOT EXISTS`, `CREATE EXTENSION IF NOT EXISTS vector`, `GRANT`/`ALTER DEFAULT PRIVILEGES`,
  `ALTER ROLE ... PASSWORD` (re-asserts the SOPS-held password, unchanged), `ALTER SCHEMA public OWNER`, `ALTER DATABASE ... OWNER`. PASS.
- (c) hard-stop statements: grep of all three for `DROP TABLE|DROP INDEX|DROP DATABASE|DROP ROLE|TRUNCATE|DELETE FROM|INSERT` finds NONE. The only `DROP` is `ALTER TABLE sweep_findings DROP CONSTRAINT IF EXISTS ck_findings_resolved_status`
  immediately followed by `ADD CONSTRAINT ... CHECK ((resolved_at IS NULL) = (status <> 'resolved'))` inside one `BEGIN ... COMMIT` with `SET lock_timeout = '5s'` - a constraint re-creation, no row is touched; it re-validates the existing
  rows (a scan of ~9k) and fails the Job (retried, `backoffLimit: 6`) rather than damaging anything if a sweep holds a lock. The `INSERT`/`DELETE` words in oc8's script are inside `GRANT SELECT, INSERT, UPDATE, DELETE` privilege lists. PASS (no hard stop).
- (d) `ALTER COLUMN ... TYPE`: only `slo_snapshots.budget_remaining_pct TYPE NUMERIC(8,2)`, a widening and a no-op once applied (already 8,2). PASS.
- (e) logical backup first: the 2.6 `pg_dumpall` of the shared server (all of `sweep_history` included, taken in this window) satisfies it. A single policy table can be extracted from `$W/shared.sql` if only it needs restoring.
- (f) exact before/after row counts of EVERY sweep_history table: below.

```bash
bash "$W/pgdr.sh" snap shared                        # re-baseline immediately before the push (3a already passed)
grep -E 'accepted_risks|slo_definitions|noise_suppressions|security_acceptances' "$W/shared.sweep_history.tbl" | tee "$W/policy-before.txt"
# expect (2026-11-08): public.accepted_risks 119 / public.noise_suppressions 39 / public.security_acceptances 118 / public.slo_definitions 7  (any DIFFERENT value is today's truth: it is the baseline, but it must be non-zero)
```

Jobs are one-shot and idempotent bootstrap scripts; their image does not touch the running server. The rename makes Flux prune the old Job and create a new one, which
RE-RUNS the bootstrap once against the (now refreshed) live server - an extra proof that roles, grants and the `vector` extension are intact. Dry-tested on scratch copies.

```bash
for f in kubernetes/apps/databases/oc8-db/app/init-job.yaml kubernetes/apps/databases/ninth-banner-feedback-db/app/init-job.yaml kubernetes/apps/databases/sweep-history/app/init-job.yaml; do sed -i '' 's/7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a/0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f/' "$f"; done
sed -i '' 's/^  name: oc8-db-init-v1a$/  name: oc8-db-init-v1b/' kubernetes/apps/databases/oc8-db/app/init-job.yaml
sed -i '' 's/^  name: ninth-banner-feedback-db-init-v1a$/  name: ninth-banner-feedback-db-init-v1b/' kubernetes/apps/databases/ninth-banner-feedback-db/app/init-job.yaml
sed -i '' 's/^  name: sweep-history-init-v9a  # v9->v9a:/  name: sweep-history-init-v9b  # v9a->v9b:/' kubernetes/apps/databases/sweep-history/app/init-job.yaml
cat > "$W/hist.py" <<'PY'
import sys
path, line = sys.argv[1], sys.argv[2]
src = open(path).read().split("\n")
i = src.index("apiVersion: batch/v1")          # ValueError if the anchor moved: stop, do not guess
src.insert(i, line)
open(path, "w").write("\n".join(src))
PY
python3 "$W/hist.py" kubernetes/apps/databases/oc8-db/app/init-job.yaml '#   v1b -- image digest re-pinned (same 0.8.7-pg16 tag, same PG 16.15); no script change. Rename forces prune+recreate; bootstrap is idempotent.'
python3 "$W/hist.py" kubernetes/apps/databases/ninth-banner-feedback-db/app/init-job.yaml '#   v1b -- image digest re-pinned (same 0.8.7-pg16 tag, same PG 16.15); no script change. Rename forces prune+recreate; bootstrap is idempotent.'
python3 "$W/hist.py" kubernetes/apps/databases/sweep-history/app/init-job.yaml '#   v9b -- image digest re-pinned (same 0.8.7-pg16 tag, same PG 16.15); no schema or bash change. Rename forces prune+recreate; bootstrap is idempotent.'
git diff --stat | tail -1                                            # expect: 3 files changed, 9 insertions(+), 6 deletions(-)
git diff -U0 | grep -E '^[-+](  name:|          image:|#   v)' | cut -c1-110
```
After the push and the Jobs completing, the 3b gate (section 4.3) re-reads every sweep_history table and diffs it EXACTLY against that baseline.

Dry-test diff (oc8-db): `-  name: oc8-db-init-v1a` / `+  name: oc8-db-init-v1b`, the image line `7b822b0a... -> 0dd3149a...`, and one added `#   v1b -- ...` comment; sweep-history:
`-  name: sweep-history-init-v9a  # v9->v9a: ...` / `+  name: sweep-history-init-v9b  # v9a->v9b: ...`. Preserve the files' trailing newline: if `git diff` shows `\ No newline at end of file` for any of the three, append one.

```bash
printf 'chore(container): init Jobs pgvector digest 7b822b0->0dd3149 via vN rename (oc8-db v1b, ninth-banner-feedback-db v1b, sweep-history v9b)\n\nJob spec is immutable (docs/sops/immutable-job-image-bumps.md); Renovate #463 edits them in place and would fail the Kustomization. Bootstrap is idempotent (maintenance plan postgres-digest-refresh-2026-11, stage 3b).\n' > "$W/msg3b.txt"
git commit --only kubernetes/apps/databases/oc8-db/app/init-job.yaml kubernetes/apps/databases/ninth-banner-feedback-db/app/init-job.yaml kubernetes/apps/databases/sweep-history/app/init-job.yaml -F "$W/msg3b.txt"
git log -1 --format=%s ; git show --stat HEAD | tail -5
git push origin main
```

## 4. Verification

Rollout status is NOT the verdict: it green-lights the old generation (`feedback_rollout_status_old_generation`). Each stage's verdict is the gate script, which
measures properties that fail when they are wrong.

**4.1 Per-stage gate** (run after each stage; `<hex>` = the 64-hex digest of the TARGET image as it appears in `status.containerStatuses[].imageID`):

```bash
bash "$W/pgdr.sh" verify paperclip 300ebd02c6d4de9ee27ad7f6855d5d21b4d3a4a5117767c1197d284c635d9736
bash "$W/pgdr.sh" verify superset  123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395
bash "$W/pgdr.sh" verify affine    0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f
bash "$W/pgdr.sh" verify sure      0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f
bash "$W/pgdr.sh" verify shared    0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f
```
PASS = the last line of each is `STAGE GATE PASS [<inst>]` (exit 0). What each gate guards against, and what it prints on failure:

| Gate | Property | Fails (prints `GATE FAIL [inst] ...`) when |
|---|---|---|
| G1 | exactly ONE pod, its `imageID` contains the target digest, container ready | the Deployment still runs the old generation, a second pod lingers (Multi-Attach wedge), or the pull failed |
| G2 | `pg_postmaster_start_time()` advanced past the pre-change snapshot | the server never restarted (e.g. the edit did not reach the pod template) |
| G3 | POSITIVE: log has `database system was shut down at` AND `database system is ready to accept connections`; ABSENT: `automatic recovery in progress`, `collation version` | the previous server was killed mid-checkpoint (crash recovery), the pod is not fresh, or the new image's libc changed |
| G4 | `/var/lib/postgresql/data` is a `/dev/longhorn/...` device (`df -P`) | PGDATA landed in the container layer (the `postgres-major-upgrade.md` trap: invisible to row counts until the next restart) |
| G5 | per database, PER TABLE: same table set; STATIC tables EXACT (`sweep_history`: accepted_risks, slo_definitions, noise_suppressions, security_acceptances, component_autonomy, media_audit_runs, slo_snapshots, window_runs, plan_executions; `superset`: every `ab_*` table); every other table may not shrink by more than max(2, 2%); `sweep_findings` and `sweep_cycles` may grow silently | any table or row vanished - a summed total cannot hide it (the old 98%-of-total rule would have passed with 225 of sweep_history's 11,235 rows gone, i.e. the 283 policy rows wiped) |
| G6 | glibc images: `datcollversion` and the live `pg_database_collation_actual_version` are both `2.36`; musl images: both `-` | a rebuilt base shipped a different glibc/collation |
| G7 | `xact_commit` of every app database GROWS between two samples 30 s apart (polled up to 10 min) | the clients did not reconnect (a stuck pool, a crash-looping app) |

CONTENTS ASSERTION: the databases still hold their data - per database and PER TABLE (`SELECT count(*)` over every user table via `query_to_xml`), the table set is identical and static tables are exact, compared to the `snap` taken minutes earlier. A server that is up but empty (wrong PGDATA, wrong volume), or one that lost a single policy table, passes `pg_isready` and every HTTP probe and fails G5.
CONTENTS ASSERTION: the clients are really talking to the NEW server - G7 reads each application database's own commit counter, which only that application's connections advance (the gate connects to
database `postgres`, never to an app database, so it cannot satisfy itself).

Negative controls (all measured 2026-11-08 against the unchanged cluster, `WANT` = a digest the pod does or does not run):
- G5/tblcheck fails on one lost policy row (replayed 2026-11-08 by editing the baseline file to `accepted_risks 120` against the live 119): `BAD STATIC public.accepted_risks: 120 -> 119` then `TBLCHECK FAIL [shared/sweep_history]`, rc=1. And growth on `sweep_findings` only (baseline 8900 vs live 8989) passes silently, rc=0.
- G3's crash-recovery absence fails on a known-bad line: `bash "$W/pgdr.sh" selftest` replays the literal PostgreSQL line `database system was not properly shut down; automatic recovery in progress` through the same `grep -qi` and prints `SELFTEST OK` only if it matches (and the clean line `database system was shut down at ...` does not). The positive anchor reads absent on pods whose log has rotated (measured today on the 27-42-day-old pods: `GATE FAIL [superset] G3 no 'database system was shut down at' line`), which is the correct answer for a non-fresh pod and the reason the gate is only meaningful on the pod a stage just created.
- G2 fails with no restart: `GATE FAIL [superset] G2 postmaster start did not advance (1790499046 -> 1790499046)` (and the overall `STAGE GATE FAIL`, rc=1).
- G1 fails on a wrong digest: `GATE FAIL [sure] G1 imageID=docker.io/pgvector/pgvector@sha256:7b822b0a... does not contain 0dd3149a...`.
- G4 had a real defect in my first draft (busybox `df` wraps a long device name onto two lines and printed `20466256` for the device); fixed with `df -P` and re-measured: `G4 ok PGDATA device /dev/longhorn/superset-pg18-data`.
- G7's control: the same two-sample read on `template1` (no client) must show NO growth: `kubectl exec -n databases deploy/postgresql -- psql -U postgres -d postgres -Atc "select xact_commit from pg_stat_database where datname='template1'"` twice, 30 s apart, identical.
- Per-app commit growth measured over 90 s before any change (so G7 is not flaky): nocodb 21, oc8 18, sweep_history 29, pellets 4, ninth_banner_feedback 4, affine 277, sure 100, superset 27, paperclip 26. `pellets` and `ninth_banner_feedback` are the quiet two: their 30-s samples can read equal, hence the 10-minute poll; if a quiet one is the ONLY remaining item at the deadline, run the app-side probe in 4.2 for it before calling it a failure.

**4.2 Per-client connectivity** (the point of the plan: nothing downstream is left holding a dead socket). Run after the stage that restarts the client's server.

| Server | Client (ns) | Check |
|---|---|---|
| shared | `oc8-backend`, `oc8-worker`, `oc8-scheduler`, `oc8-ingestion-worker` (ai) | `kubectl get deploy -n ai oc8-backend oc8-worker oc8-scheduler oc8-ingestion-worker -o jsonpath='{.items[*].status.readyReplicas}'` -> `1 1 1 1`, restarts unchanged: `kubectl get pods -n ai -l app.kubernetes.io/name=oc8 -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}'` (record before/after; a rise means the app crash-looped on the outage - note it, it must be stable after) |
| shared | `nocodb` (databases) | `kubectl exec -n databases deploy/nocodb -- wget -qO- http://127.0.0.1:8080/api/v1/health` -> `{"message":"OK",...}` (measured); this is a SHAPE check on its own - G7's `nocodb` commit growth is the contents check |
| shared | `sweep-dashboard` (monitoring), `sweep-heartbeat` CronJob, `runbooks/sweep-run.py` | `kubectl create job --from=cronjob/sweep-heartbeat pgdr-hb-$(date +%H%M) -n databases` then `kubectl wait --for=condition=complete job/pgdr-hb-<same> -n databases --timeout=120s` and `kubectl delete job pgdr-hb-<same> -n databases`; PASS = `condition met`. Then `SELECT max(...)`-free read of the history DB: `kubectl exec -i -n databases deploy/postgresql -- psql -U postgres -d sweep_history -Atc "select count(*) from sweep_findings"` >= `8989` (measured 2026-11-08) |
| shared | `pallet-price-monitor` (home-automation), Grafana "Pellets" | `kubectl exec -n databases deploy/postgresql -- psql -U postgres -d pellets -Atc "select count(*) from pg_stat_activity where datname='pellets'"` is informational; the pass is G7 on `pellets`, plus Grafana datasource health from the UI (Connections -> Data sources -> Pellets -> Save & test: "Database Connection OK"). Operator-visible, attended window |
| shared | `the-ninth-banner` (my-software-production) | `kubectl get deploy -n my-software-production the-ninth-banner -o jsonpath='{.status.readyReplicas}'` -> `1`; G7 on `ninth_banner_feedback` |
| affine-pg | `affine` (office) | `kubectl exec -n office deploy/affine -- node -e 'require("http").get("http://127.0.0.1:3010/info",r=>console.log(r.statusCode))'` -> `200` (measured; SHAPE) + G7 `affine` (277 commits/90 s - the strong signal) |
| sure-pg | `sure-web`, `sure-worker` (office) | `kubectl exec -n office deploy/sure-web -- ruby -e 'require "net/http"; puts Net::HTTP.get_response(URI("http://127.0.0.1:3000/up")).code'` -> `200` (measured; SHAPE) + G7 `sure` (100 commits/90 s) + `kubectl get deploy sure-web sure-worker -n office -o jsonpath='{.items[*].status.readyReplicas}'` -> `1 1` |
| superset-pg18 | `superset`, `superset-worker`, `superset-celerybeat` (databases) | `kubectl get deploy superset superset-worker superset-celerybeat -n databases -o jsonpath='{.items[*].status.readyReplicas}'` -> `1 1 1` + G7 `superset` |
| paperclip-postgresql | `paperclip` (ai) | `kubectl get deploy paperclip -n ai -o jsonpath='{.status.readyReplicas}'` -> `1` + G7 `paperclip` |

If a client has NOT reconnected after its server is Ready and G7 has timed out for it: `kubectl rollout restart deploy/<client> -n <ns>` ONCE (an ephemeral pod restart,
no git change), re-run the stage gate. A second failure is a rollback trigger (section 5), not a retry loop.

**4.3 Stage 3b (init Jobs).** The `grep -c` = 0 line is an ABSENCE check and is valid ONLY together with the positive `succeeded` = `1 1 1` line below it (an empty Job list would also print 0).

```bash
kubectl get job -n databases -o name | grep -e init-v1b -e init-v9b            # PASS: 3 lines (oc8-db-init-v1b, ninth-banner-feedback-db-init-v1b, sweep-history-init-v9b)
kubectl get job -n databases -o name | grep -c -e init-v1a -e init-v9a         # PASS: 0 (old Jobs pruned; a non-zero count means Flux did not prune)
kubectl get job oc8-db-init-v1b ninth-banner-feedback-db-init-v1b sweep-history-init-v9b -n databases -o jsonpath='{.items[*].status.succeeded}'    # PASS: "1 1 1"
kubectl get job oc8-db-init-v1b -n databases -o jsonpath='{.spec.template.spec.containers[0].image}' | grep -c 0dd3149a06e4     # PASS: 1
kubectl logs -n databases job/oc8-db-init-v1b --tail=3                          # PASS: last line "==> Done. vector: 0.8.6"
flux get ks oc8-db ninth-banner-feedback-db sweep-history -n databases          # PASS: all Ready=True (oc8-db has wait:true, so this is the one that goes red on a bad Job)
```
`succeeded` empty (Job still running) or `0` fails the `"1 1 1"` match; the oc8 log line proves the bootstrap reached its last statement against the refreshed server.
**The 3b CONTENTS gate (SOP 4a(f), exact per table):**

```bash
bash "$W/pgdr.sh" tblcheck shared sweep_history        # PASS: "TBLCHECK PASS [shared/sweep_history]"; the 4 policy tables + component_autonomy, media_audit_runs, slo_snapshots, window_runs, plan_executions must be EXACT
grep -E 'accepted_risks|slo_definitions|noise_suppressions|security_acceptances' "$W/shared.sweep_history.tbl.now" | diff - "$W/policy-before.txt" && echo POLICY-ROWS-IDENTICAL
bash "$W/pgdr.sh" tblcheck shared oc8                  # oc8/ninth_banner_feedback/pellets/nocodb are live apps: no table may shrink by more than max(2, 2%)
bash "$W/pgdr.sh" tblcheck shared ninth_banner_feedback
```
`tblcheck` prints any table whose count moved (`changed <table>: a -> b`) so a legitimate change by normal traffic is visible, not hidden; a STATIC table that moves, a vanished table, or a shrink beyond tolerance prints `BAD ...` and `TBLCHECK FAIL` (rc 1) -> roll back per section 5 and restore from the 2.6 dump.
`POLICY-ROWS-IDENTICAL` is the exact before/after the SOP requires (`diff` prints the differing lines instead). Run both BEFORE the window-agent close-out writes `window_runs`/`plan_executions` rows.

CONTENTS ASSERTION: roles and extension survived the re-run - `kubectl exec -n databases deploy/postgresql -- psql -U postgres -d oc8 -Atc "select extname||' '||extversion from pg_extension order by 1"` -> `plpgsql 1.0` and `vector 0.8.6` (the
pre-change values; a bootstrap that dropped/re-created the extension would print `vector 0.8.7`).

**4.4 CronJobs (images only).** They run on their own schedule; the images must be right and one real run must succeed.

```bash
kubectl get cronjob sweep-heartbeat -n databases authentik-channels-cleanup authentik-db-probe -n kube-system media-library-audit -n media 2>&1 | head -1   # (see below: one namespace per call)
kubectl get cronjob sweep-heartbeat -n databases -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
kubectl get cronjob authentik-channels-cleanup authentik-db-probe -n kube-system -o jsonpath='{.items[*].spec.jobTemplate.spec.template.spec.containers[0].image}'
kubectl get cronjob media-library-audit -n media -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[*].image}'
```
PASS: every `postgres:18.6-alpine` image printed ends in `@sha256:123b17998ccaf47e53b502e8c6a1e79afd8f579c6f3eec83c563da026f957395` (media-library-audit also lists its `python:3.14.10-slim` container, unchanged).
Then one real run: `kubectl create job --from=cronjob/authentik-db-probe pgdr-probe-$(date +%H%M) -n kube-system`, `kubectl wait --for=condition=complete job/<that name> -n kube-system --timeout=120s` -> `condition met`, then delete that Job.
(The probe is a read-only connectivity check against `authentik-pg`; a failure prints `error: timed out waiting for the condition` and `kubectl logs job/<name>` names the cause.) A pull error on the new digest shows as `ImagePullBackOff` there.

**4.5 Instruments and alerts** (the window's Prometheus: `kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090`; metric names verified present 2026-11-08).

CONTROL: metric kube_deployment_status_replicas_available - for each of `postgresql`, `superset-pg18` (databases), `affine-pg`, `sure-pg` (office), `paperclip-postgresql` (ai) the value is `1` at the end of its stage; an EMPTY result is a FAIL (series exist today, measured for postgresql, affine-pg, sure-pg).
CONTROL: metric kube_pod_container_status_restarts_total - the NEW pod of each database shows `0` (a crash-looping database restarts; the old pod's series disappears with it).
CONTROL: alertname SurePostgresDown - not firing 10 min after stage 2 (state `inactive` today; the rule exists in the loaded rule set).
CONTROL: alertname SupersetPostgresDown - not firing 10 min after stage 1.
CONTROL: alertname PaperclipPostgresqlPodNotReady - not firing 10 min after stage 1.
CONTROL: alertname PaperclipPostgresqlPodCrashLooping - not firing 10 min after stage 1.
Gap, stated so nobody reads silence as health: there is NO alert for `databases/postgresql` (shared) or `affine-pg` going down; for those the stage gate and the `kube_deployment_status_replicas_available` read are the only instruments.

**4.6 End state.**

```bash
flux get ks -A | awk 'NR==1 || $5 != "True"'                      # PASS: header only
flux get hr -n office affine-pg sure-pg                            # PASS: both Ready=True
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded       # PASS: No resources found
gh pr view 463 --json state -q .state; gh pr view 227 --json state -q .state
```
The two PRs: Renovate closes a PR whose change is already in `main` on its next run (#227 is "Immortal": it is recreated only if its content differs from `main`). PASS is either `CLOSED`/`MERGED`, or - if a NEWER digest has appeared since - a PR
whose diff is a different digest than this plan's. Do NOT close them by hand and do NOT merge #463 (it would revert the Job renames; section 1). Verify with `gh pr diff <n> | grep '^[-+] .*image:\|tag:'`: any line that still shows an OLD digest from this plan means a file was missed.

## 5. Rollback

**Why a revert is complete here (the evidence the plan rests on).** Old and new images are the same PostgreSQL minor (registry config blob `PG_VERSION`: `16.15-1.pgdg12+2` for both pgvector digests; `18.6` for all four alpine
digests, measured 2026-11-08) with the same pgvector tag; no schema, catalog or WAL change is made by the plan; PostgreSQL's versioning policy guarantees storage-format compatibility with earlier AND later minors of a major. So
the new server's files are readable by the old image and vice versa. The new server also runs NO migration step (nothing in these images does). The init Jobs only re-run `CREATE ... IF NOT EXISTS`/grants.

**Per-stage revert (preferred, any stage, any time):**

```bash
git log --oneline -6                                    # find the stage's commit (subject starts "chore(container): refresh ..." / "init Jobs ...")
git revert --no-edit <sha-of-the-failed-stage>          # reverts ONLY that stage; later stages (if any ran) are reverted newest-first
git log -1 --format=%s                                  # confirm the subject is a Revert of YOUR stage before pushing
git push origin main
```
Stage 3b first if both 3a and 3b ran. After the push Flux restores the old pinned digest (Recreate again: another 1-3 minutes of downtime for that server). The old image must be pulled again if its node cache was
pruned: the digests are registry-pinned so they remain pullable. A revert of stage 3b renames the Jobs back to v1a/v1a/v9a and re-runs the idempotent bootstrap with the old image - harmless.

Confirm the cluster is back: `bash "$W/pgdr.sh" verify <inst> <OLD-digest-hex>` (old hexes: paperclip `63bdc97d67b5133bf0e5ebd500bec6d046fa851dc81340d838f0347e616107e8`, superset `d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2`,
pgvector instances `7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a`) -> `STAGE GATE PASS`, using a fresh `snap` taken just before the revert as the baseline so G2 and G5 compare to the pre-revert state.

**Rollback triggers:** any `STAGE GATE FAIL` that is not explained and fixed within 10 minutes; G3 `crash recovery ran`; G4 not a Longhorn device; G5 table-count mismatch or rows < 98%; G6 collation drift (STOP - do not
let apps write to indexes built under a different collation; revert, then `REINDEX` is a separate decision); a client that fails G7 twice; any Longhorn volume leaving `healthy` after the pod comes back.

**If the data itself is damaged (not expected; reachable only through a crash during shutdown or a volume fault) - this is the forward-only branch, and it is a procedure:**
1. Stop the damage: suspend the app's Kustomization (`flux suspend ks <name> -n <ns>`) and scale its clients to 0 (`kubectl scale deploy/<client> -n <ns> --replicas=0`). Do not revert first - a revert restarts the database again over damaged files.
2. Preserve the evidence: `kubectl logs` of the failed pod to `$W`, and the Longhorn volume untouched (do not delete the PVC; storage-safety rules apply - these are RWO Longhorn volumes, not CIFS).
3. Recover from the **Longhorn backup** per `docs/sops/backup.md` "Restore from Backup" (restore the newest Completed Backup of the volume into a NEW volume and bind a restored PV/PVC), or - for a smaller loss window - restore the 2.6 logical dump into a fresh
   server: start a scratch pod from the OLD image on an empty volume, `psql -U <role> -d postgres < "$W/<inst>.sql"` (pg_dumpall output recreates roles and databases). RPO: Longhorn = last nightly (up to ~25 h; measured fresh at 19.4 h on 2026-11-08), logical dump = the moment of 2.6.
4. Repoint with the SAME speaking PV name convention (`docs/sops/longhorn.md`); verify with G5 against the 2.7 fingerprint.
Logical dumps contain role password hashes: keep them in `$W` only, never in the repo or a ticket.

**Restore-proof leftovers** (if a proof was interrupted): `kubectl get pod,pvc -n databases -l restore-proof=true`, `kubectl get pv -l restore-proof=true`, `kubectl get volumes.longhorn.io -n storage -l restore-proof=true` and delete in that order
(pod, pvc, pv, then the Longhorn volume). The scratch PV is `Retain`, which is why the volume must be deleted last by name.

## 6. Interference notes

- **Schedule.** `sun-attended:2026-12-20` (fallback `2026-12-27`), assigned by the coordinator; do not stack with 2026-12-06 (n8n-fleet-2.46.6 + vaultwarden). The 20Gi restore proofs (2.5a) must be recorded BEFORE that date.
- **Keep OUT of the same night:** nocodb #426 (calver bump, one-way knex migrations into the shared server), kube-prometheus-stack #428 / #501 (the window's instrument), and any other plan or Step-0 auto-update batch that restarts a database client.
- **Close-out cleanup.** After the window (and the gates passed): `rm -rf "$W"` (the dumps hold password hashes). Delete this plan file in the commit that records `status: executed`; Renovate then drops #463/#227 on its own.
- **Shared server blast radius.** Stage 3a restarts the only PG16 server that the sweep itself uses. Never overlap `runbooks/sweep-run.py` (the 48 h 04:00 cron) or the weekly retro (Mon 07:30), and never run in `nightly` (03:30-05:00 overlaps the sweep, and nothing human is watching the shared server, which has no alert). Attended window or an operator-present on-demand run only.
- **Why `conflicts_with` is long.** It lists the plans that (a) restart the same pods or databases (`paperclip-26.04`, `nextcloud-12.0.2`, `bitnamilegacy-exit-nextcloud-db`, `redis-fleet-8.10.3` - sure and superset need their Redis for the G7 client gates), (b) move storage, nodes or DNS under the gates
  (`longhorn-1.13.0`, `talos-linux-1.14.5`, `coredns-1.50.2`, `etcd-timeouts-5000-500`), (c) assert or change Helm/Flux state this plan touches (`helm-drift-detection` asserts identical revisions; `flux-oci-chart-sources` re-points app-template; `flux-reconciler-impersonation`), or (d) restart the operator's instrument (`grafana-chart-14.4.0`).
  A same-night `kube-prometheus-stack` bump (#428 / #501) has no plan file to list: the window agent must keep it out of this slot manually.
- **NOT a conflict, deliberately:** `n8n-fleet-2.46.6` (SQLite on its own PVC; its premise `sqlite-not-postgres` was verified) - the suggested slot `sun-attended:2026-12-06` shares only the window. `openclaw-2026.11.1` (blocked) and `open-webui-0.13.0` do not use these servers.
- **Reciprocity.** `--validate` checks refs resolve, not that they are mutual. `postgres-digest-refresh-2026-11` was added to `conflicts_with` of longhorn-1.13.0, talos-linux-1.14.5, redis-fleet-8.10.3, coredns-1.50.2, grafana-chart-14.4.0, helm-drift-detection, flux-oci-chart-sources and paperclip-26.04 (uncommitted frontmatter edits). **NOT done: nextcloud-12.0.2** (untracked file, skipped by instruction) - whoever commits it must add this plan to its `conflicts_with`.
- **Hold-back.** If the operator wants these two PRs not to be re-proposed as the registry rebuilds the tags every few weeks, that is a policy decision (a `runbooks/auto-update-policy.yaml` rule), not part of this plan. Note `*ninth-banner-feedback-db*` already has a `paths` HOLD for the Job file.
- **Repo corrections found while planning (not fixed here):** (1) `backup-restore-proof.py` defaulted `--image` to `pgvector/pgvector:0.8.6-pg16` (stale; live is 0.8.7) and hardcoded a 5Gi PV/PVC capacity (3 of the 5 sources are 20Gi). FIXED in the working tree (uncommitted): the scratch PV/PVC is sized from the source Longhorn volume's `spec.size`, `--image` is required, and `runbooks/tests/test-backup-proof-superuser.py` gained five guards (all passing). Any doc that shows the command without `--image` (`docs/sops/control-liveness.md`) needs the flag added. (2) `auto-update.py` reports `#227 ? -> ?` because its title is the bare `chore(container): update postgres`; the dry-run therefore shows no component for it.
  (3) Renovate's #463 changes standalone Job images in place, which the repo's own SOP says breaks Flux; a Renovate `packageRules` entry that excludes `kubernetes/apps/**/init-job.yaml` (or a post-update rename) would stop this recurring.
- **Gate script provenance.** `pgdr.sh` was exercised read-only against the live cluster on 2026-11-08: `snap` on all five instances, `verify` against the CURRENT (unchanged) digests - the expected failures (G2 on every instance, G3 `no ready line` on pods with rotated logs) fired and the expected passes (G1/G4/G5/G6/G7) held.
  The first run exposed two defects (a wrapped `df` line, a log `--tail` that missed the ready line) - both fixed in the version embedded in 2.1. It has NOT been run against a freshly restarted pod; the first execution is the window itself, which is why the stages are sequential.
