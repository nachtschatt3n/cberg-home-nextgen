---
plan_id: paperclip-postgresql-18.6
component: paperclip-postgresql        # exact version-check component key — do not rename
pr: null                               # no open Renovate PR — the image lives in a plain
                                      # Deployment yaml (kubernetes/apps/ai/paperclip/app/postgresql.yaml),
                                      # same shape as paperless-db-12.3.3. Renovate DID open
                                      # and merge #206 for the 17.9->17.11 PATCH bump on this
                                      # same image; it has not opened one for the 18.x major
                                      # (separateMajorMinor / major-bumps-need-a-plan config).
kind: image
current: "17.11-alpine"
target: "18.6-alpine"
update_type: major                    # postgres server major: 17 -> 18
risk: high                            # one-way datadir format change on a stateful app DB —
                                      # see "Why high, but the smallest of the three" in §1
est_duration_min: 30
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - deployment/paperclip-postgresql           # image bump; subPath repointed to a fresh dir
    - pvc/paperclip-postgresql-data             # same PVC, NEW subdir for the pg18 datadir —
                                                # old pg17 subdir untouched (rollback floor)
    - helmrelease/paperclip                     # suspended + scaled 0 for the duration (the
                                                # only consumer of this DB)
    - service/paperclip-postgresql              # unchanged, listed because verification hits it
  shared: []                                    # dedicated single-tenant DB, no shared infra:
                                                # not on ingress, cert-manager, cilium, coredns,
                                                # or a shared Longhorn engine version. `ai`
                                                # namespace hosts many other apps (anythingllm,
                                                # librechat, open-webui, openclaw, hermes-agent,
                                                # ai-sre, mcpo, next-ai-draw-io) but NONE of them
                                                # talk to paperclip-postgresql — verified via
                                                # `kubectl get all -n ai` + grep for the service
                                                # name across every other app's manifests.
depends_on: []
conflicts_with: [superset-pg-18.6]    # FORWARD REFERENCE, unconfirmed plan_id — see §6. Verify
                                      # at vetting time: `ls runbooks/maintenance/plans/ | grep
                                      # -i 'superset-pg\|postgres-major'`. If the sibling
                                      # planner landed a different plan_id, fix this field to
                                      # match rather than deleting the guard.
security_ref: null                    # version-currency driver, not a CVE driver. (AR-112
                                      # already covers what remains on postgres:18.6-alpine
                                      # posture generically — F-2a076950 et al — this plan does
                                      # not change that.)
capability_change: false              # same DB engine role, same app behaviour intended
rollback_class: backup-restore        # postgres has NO downgrade path (upstream: "the only
                                      # supported way back to an older major is dump/restore
                                      # from a backup taken before the upgrade" — see §1).
                                      # A same-window abort is cheap (old datadir subPath is
                                      # left on disk untouched, see Steps), but once real
                                      # traffic has hit the new pg18 cluster, going back means
                                      # replaying the dump, not `git revert`.
backup_gate: "pg_dump of the paperclip database taken from the LIVE pg17 pod, verified non-empty + '-- PostgreSQL database dump complete' + per-table row counts captured, BEFORE the image/subPath edit is pushed"
finding_refs: []
status: draft
window: null                          # operator schedules; do not self-assign
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
generated: "2026-09-05"
---

# paperclip-postgresql: postgres 17.11-alpine → 18.6-alpine (major)

## 1. Summary & why held

Bump the dedicated Postgres instance backing `ai/paperclip` (AI agent
orchestration app) from **17.11-alpine** to **18.6-alpine**. Held by the
version gate: "major version change typically indicates breaking changes."
Target confirmed to exist in the registry (2026-09-05): Docker Hub manifest
list for `postgres:18.6-alpine`, linux/amd64 manifest digest
`sha256:63bdc97d67b5133bf0e5ebd500bec6d046fa851dc81340d838f0347e616107e8`
(built from `docker-library/postgres` `18/alpine3.24`, base `alpine:3.24`,
pushed 2026-08-13).

**Why high risk, but the smallest of the three pg-major items in flight
right now.** Postgres majors are a one-way on-disk format change — there is
no `MARIADB_AUTO_UPGRADE`-style in-place path; upstream's own release notes
say the supported route is `pg_upgrade` (needs both major's binaries present
in one image, which this alpine image does not ship) or dump/restore. That
puts this in the same risk **class** as `superset-pg` (still on
`postgres:17.11-alpine`, own plan in flight — see §6) and the already-executed
authentik pg17→18 cutover. Unlike those two, this instance:
- serves **exactly one consumer** (`deployment/paperclip`, verified via
  `kubectl get all -n ai` — no other of the ~9 other apps in the `ai`
  namespace references `paperclip-postgresql`),
- holds a **tiny dataset**: `kubectl get volume` reports `actualSize:
  285716480` (≈272 MiB) on a 5Gi PVC, and the app's own daily dump
  (`/paperclip/instances/default/data/backups/paperclip-YYYYMMDD-*.sql`,
  cron-cleaned by `paperclip-backup-cleanup`) is ~76 MiB,
- is **not** a shared metadata store (unlike Superset/Authentik, nothing else
  in the cluster reads it).

So the mechanism and the one-way-ness earn `risk: high`, but the blast
radius if it goes wrong is "one internal AI tool is down," not "SSO is down"
or "every dashboard is empty."

**Upstream breaking changes assessed (PostgreSQL 18 release notes,
postgresql.org/docs/18/release-18.html) against our dump/restore path:**

- **`COPY ... \.` no longer treated as CSV EOF** — does not apply to us:
  `psql` (the client we restore with) explicitly keeps treating `\.` as the
  `\copy`/STDIN terminator; this change only bites raw `COPY FROM` readers.
- **NOT NULL constraints now live in `pg_constraint`, not just
  `pg_attribute`** — a schema-introspection tool that queries
  `pg_attribute.attnotnull` directly instead of using `\d`/information_schema
  could misbehave. Paperclip's own migration framework is unknown to us
  (closed-source `reeoss/paperclipai-paperclip` image); flagged as a
  **post-restore watch-item**, not a blocker — verified in §4 by confirming
  the app's own schema-management step (its startup migrations, if any) runs
  clean in the logs after cutover.
- **`initdb` enables data checksums by default** — cosmetic for us: our new
  cluster is freshly `initdb`'d by the entrypoint (see mechanism below), so
  it simply gets checksums on with no cross-cluster mismatch to reconcile
  (that failure mode is a `pg_upgrade`-specific gate; we are not using
  `pg_upgrade`).
- **MD5 password auth deprecated** — not in use; the official image has
  defaulted new roles to SCRAM since PG14, and our env-var-created role goes
  through the same `initdb` path on 18 as it did on 17.
- **`effective_io_concurrency`/`maintenance_io_concurrency` defaults 1→16,
  new async-I/O subsystem** — behavioural, not breaking, and irrelevant at
  this DB's scale (272 MiB, low QPS internal tool).
- Upstream's own upgrade guidance for a plain dump/restore (not
  `pg_upgrade`) is explicitly: take a `pg_dump`/`pg_dumpall` backup on the
  old server, load it into a freshly initialized new-version cluster. That
  is the mechanism below.

**Mechanism — dump/restore into a fresh datadir on the SAME PVC, not a
parallel Deployment.** `postgresql.yaml` mounts the PVC at
`/var/lib/postgresql/data` via `subPath: postgres`. Bumping only the image
tag would start the 18 binary directly against 17-format files already
present in that subPath and crash-loop immediately ("database files are
incompatible with server") — that IS the auto-updater's hold condition, not
a theoretical risk. The plan instead repoints `subPath` to a **new, empty**
directory (`postgres18`) in the same edit as the image bump: the official
entrypoint sees an empty PGDATA, runs `initdb` fresh (recreating the
`paperclip` role/database from the same `POSTGRES_USER`/`POSTGRES_DB`/
`POSTGRES_PASSWORD` env vars already in the Deployment — no secret changes
needed), and we then restore a `pg_dump` of the `paperclip` database taken
from the live 17.11 pod beforehand. The old `postgres` subdirectory is left
untouched on the same 5Gi volume (272 MiB used of 5Gi — plenty of headroom
for both copies) — that is the fast, in-window rollback floor described in
§5.

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# Cluster + component healthy, no in-flight reconcile
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
kubectl -n ai get pods -l app=paperclip-postgresql        # 1/1 Running, no restarts
kubectl -n ai get pods -l app.kubernetes.io/name=paperclip
kubectl -n ai get deploy paperclip-postgresql -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
# expect: postgres:17.11-alpine@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73

# Longhorn volume healthy + headroom (confirmed 2026-09-05: 272MiB used / 5Gi, healthy, attached)
kubectl get volume -n storage pvc-773cc06e-4984-4bcf-ae38-64fe77f68a5c \
  -o custom-columns=NAME:.metadata.name,SIZE:.status.actualSize,STATE:.status.state,ROBUST:.status.robustness,LAST_BACKUP:.status.lastBackupAt
# Abort if lastBackupAt is stale (>26h) or state != attached/healthy.

# Schema inventory (informational baseline — expect one non-system DB: paperclip)
kubectl -n ai exec deploy/paperclip-postgresql -- psql -U paperclip -d paperclip -c '\dt' 

# App's own daily dump exists and is recent (extra fallback, NOT the primary backup —
# its format/completeness is unverified by us; confirmed present 2026-09-05, ~76MiB,
# fires ~06:07 daily). Do not rely on it alone.
kubectl -n ai exec deploy/paperclip -c app -- sh -c \
  'ls -la /paperclip/instances/default/data/backups | tail -3'
```

Abort the window for this plan if the volume is not `attached/healthy`, the
last Longhorn backup is stale, or `\dt` shows something other than the
expected paperclip application schema (would mean drift since this plan was
written — re-investigate first).

## 3. Steps

All cluster writes in this section are executed by the window agent /
cberg-agent; the manifest change is GitOps.

**3.1 Quiesce the app** (single consumer of this DB — suspend the
HelmRelease, not the Kustomization, so Flux keeps reconciling our manifest
edit to `postgresql.yaml` in the same Kustomization `paperclip`/`ai`):

```bash
flux suspend helmrelease paperclip -n ai
kubectl -n ai scale deploy/paperclip --replicas=0
kubectl -n ai wait --for=delete pod -l app.kubernetes.io/name=paperclip --timeout=120s
```

**3.2 Baseline per-table row counts** (works unchanged on PG17 and PG18 —
`query_to_xml` counts real rows, not `pg_stat`/planner estimates; same
technique as `superset-pg-cutover` §3.4):

```bash
kubectl -n ai exec -i deploy/paperclip-postgresql -- \
  psql -U paperclip -d paperclip -At -f - <<'SQL' > /tmp/paperclip-pg-counts-pre.txt
select c.relname||'='||(xpath('/row/c/text()',
    query_to_xml(format('select count(*) as c from %I.%I', n.nspname, c.relname),
                 false, true, '')))[1]::text::bigint
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where c.relkind = 'r' and n.nspname = 'public' order by c.relname;
SQL
wc -l /tmp/paperclip-pg-counts-pre.txt
```

**3.3 Logical dump — the rollback floor (non-negotiable):**

```bash
mkdir -p ~/backups/paperclip-postgresql && chmod 0700 ~/backups/paperclip-postgresql
DUMP=~/backups/paperclip-postgresql/paperclip-pre-18.6-$(date +%Y%m%d%H%M).sql
kubectl -n ai exec deploy/paperclip-postgresql -- \
  pg_dump -U paperclip -d paperclip --no-owner --no-privileges > "$DUMP"
chmod 0600 "$DUMP"

# Verify before trusting it:
tail -5 "$DUMP" | grep -q -- '-- PostgreSQL database dump complete' || echo "ABORT: dump incomplete"
grep -c '^CREATE TABLE' "$DUMP"
ls -lh "$DUMP"        # expect roughly in line with the app's own ~76MiB dump
```

(Only `pg_dump` of the single `paperclip` database is needed — not
`pg_dumpall` — because the entrypoint recreates the identical `paperclip`
role/database from the unchanged `POSTGRES_USER`/`POSTGRES_DB`/
`POSTGRES_PASSWORD` env vars during the fresh `initdb` in step 3.5; there
are no other roles/databases in this instance per the §2 `\dt`/pre-check.)

**3.4 Longhorn snapshot as fast-path insurance** (DB is idle now — app is at 0):

```bash
kubectl apply -f - <<'EOF'
apiVersion: longhorn.io/v1beta2
kind: Snapshot
metadata:
  name: paperclip-postgresql-data-pre-18-6
  namespace: storage
spec:
  volume: pvc-773cc06e-4984-4bcf-ae38-64fe77f68a5c
  createSnapshot: true
EOF
kubectl -n storage get snapshot.longhorn.io paperclip-postgresql-data-pre-18-6 -o jsonpath='{.status.readyToUse}{"\n"}'
# expect: true
```

**3.5 GitOps change** — edit
`kubernetes/apps/ai/paperclip/app/postgresql.yaml`:

- `image: postgres:17.11-alpine@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73`
  → `image: postgres:18.6-alpine@sha256:63bdc97d67b5133bf0e5ebd500bec6d046fa851dc81340d838f0347e616107e8`
- `volumeMounts[0].subPath: postgres` → `subPath: postgres18` (fresh, empty
  dir on the same PVC — the old `postgres` subdir is deliberately left in
  place as the rollback floor; do NOT delete it as part of this edit)
- Add a comment above the `subPath` line explaining why it changed (major
  bump, in-place binary swap is not supported, old data preserved under
  `postgres/` for rollback).

```bash
git commit --only kubernetes/apps/ai/paperclip/app/postgresql.yaml \
  -m "feat(paperclip-postgresql): postgres 17.11-alpine -> 18.6-alpine, fresh datadir subPath (plan paperclip-postgresql-18.6)"
git show --stat HEAD    # ONLY postgresql.yaml — shared worktree check (CLAUDE.md)
git push
```

**3.6 Roll the DB:**

```bash
flux reconcile kustomization paperclip -n ai --with-source
kubectl -n ai rollout status deploy/paperclip-postgresql --timeout=180s
# Confirm a genuinely FRESH cluster came up (not an accidental reuse of the old dir):
kubectl -n ai logs deploy/paperclip-postgresql | grep -iE 'initdb|PostgreSQL init process complete|database system is ready'
```

**3.7 Restore the dump into the fresh 18 cluster:**

```bash
kubectl -n ai exec -i deploy/paperclip-postgresql -- \
  psql -U paperclip -d paperclip -v ON_ERROR_STOP=1 -f - < "$DUMP"
```

**3.8 Verify the DB (§4, DB half) — then and only then un-quiesce the app:**

```bash
flux resume helmrelease paperclip -n ai
flux reconcile helmrelease paperclip -n ai   # restores replicas=1
kubectl -n ai rollout status deploy/paperclip --timeout=180s
```

## 4. Verification

Version alone (`SELECT version();` reporting 18.x) is a shape check — a
freshly `initdb`'d, **empty** 18 cluster reports the same version string as
a correctly restored one. Row counts are the real signal.

```bash
# 1. Binary reports 18.6
kubectl -n ai exec deploy/paperclip-postgresql -- psql -U paperclip -d paperclip -c 'SELECT version();'

# 2. CONTENTS ASSERTION: per-table row counts of the paperclip schema —
#    measured by re-running the §3.2 query post-restore, compared to
#    /tmp/paperclip-pg-counts-pre.txt. The diff MUST be silent.
kubectl -n ai exec -i deploy/paperclip-postgresql -- \
  psql -U paperclip -d paperclip -At -f - <<'SQL' > /tmp/paperclip-pg-counts-post.txt
select c.relname||'='||(xpath('/row/c/text()',
    query_to_xml(format('select count(*) as c from %I.%I', n.nspname, c.relname),
                 false, true, '')))[1]::text::bigint
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where c.relkind = 'r' and n.nspname = 'public' order by c.relname;
SQL
diff /tmp/paperclip-pg-counts-pre.txt /tmp/paperclip-pg-counts-post.txt && echo COUNTS-MATCH

# 3. Table count sanity (independent of the row-count diff — catches a
#    restore that silently dropped whole tables rather than rows):
wc -l /tmp/paperclip-pg-counts-pre.txt /tmp/paperclip-pg-counts-post.txt

# 4. The dependent app actually works — a DB its app cannot use is the
#    failure worth catching. Init container must clear ("postgres
#    reachable"), app container must not crash-loop, and the app-level
#    schema-migration step (if any runs at startup) must complete clean —
#    watch for the NOT NULL / pg_constraint watch-item from §1 here:
kubectl -n ai logs deploy/paperclip -c app --tail=100 | grep -iE 'error|migrat|constraint' || echo "no errors in startup log"
kubectl -n ai get pods -n ai -l app.kubernetes.io/name=paperclip   # 2/2 Running, 0 restarts

# 5. Real user-facing check (attended): open https://paperclip.${SECRET_DOMAIN}/,
#    log in, and confirm the same agents/workflows/records that existed before
#    the window are still visible — a "database its app cannot read correctly"
#    can pass every count/log check above and still render an empty UI if the
#    app caches or requires a specific migration marker row.
```

Nightly Longhorn backup of `pvc-773cc06e-...` must complete on the next
03:00 cycle (check `lastBackupAt` next sweep).

## 5. Rollback

**There is no in-place downgrade.** Never point the Deployment's `subPath`
back at `postgres18` under an 17.11 image, or vice versa point a fresh
18-format dir at the 17 binary — mismatched binary/datadir crash-loops
immediately, which is the intended fail-fast behaviour, not a rollback path.

Trigger: the new pod won't start clean, the restore (`psql -f -`) reports
errors under `ON_ERROR_STOP=1`, the counts diff in §4.2 is non-silent, or
the app cannot use the restored DB.

**Fast path — same window, before real traffic hits the new cluster (the
old `postgres` subdir is still untouched on disk):**

1. Re-suspend `helmrelease paperclip` / scale `deploy/paperclip` to 0 if not
   already down.
2. `git revert <hash-of-3.5-commit>` and push — restores `image:
   postgres:17.11-alpine@...` and `subPath: postgres` in one step.
3. `flux reconcile kustomization paperclip -n ai --with-source`
4. `kubectl -n ai rollout status deploy/paperclip-postgresql --timeout=180s`
   — the pod comes back up against the **original, never-touched** `postgres`
   subdir. No data movement needed; this is a genuine git-revert-speed
   rollback because nothing overwrote the old subdir.
5. Confirm: `SELECT version()` → 17.11, counts vs `/tmp/paperclip-pg-counts-pre.txt`
   (re-run the same query on the restored 17 pod) silent, resume
   `helmrelease paperclip`, confirm app healthy.

**Slow path — after the 18 cluster has taken real writes post-cutover (the
17 subdir is now stale, this is the `backup-restore` class the frontmatter
declares):**

1. Quiesce again (§3.1).
2. Take a fresh `pg_dump` off the 18 pod if any post-cutover writes are worth
   keeping (operator judgement call — may not be, for a low-traffic internal
   tool; if not, skip straight to restoring the pre-cutover dump).
3. Either wipe the `postgres18` subdir via a one-off debug pod mounting
   `paperclip-postgresql-data` and re-run 3.5→3.7 with the *original* `$DUMP`
   (`postgres17-format data is unaffected` — the 17 subdir was never
   touched), reverting to 17.11 + the pre-cutover dump; or accept the 18
   cluster as-is and restore into it if the failure was restore-specific.
4. Confirm as in §4, set this plan `status: blocked` with the failure noted.

Dumps under `~/backups/paperclip-postgresql/` contain the app's OpenAI key
and auth secrets embedded in application rows — keep `0600`, never commit,
delete after the soak window closes.

## 6. Interference notes

- **Shares the "postgres-major" risk class with a sibling plan in flight
  right now: `superset-pg` is still on `postgres:17.11-alpine`**
  (`kubernetes/apps/databases/superset/app/pg-deployment.yaml`, confirmed
  2026-09-05) and is presumably being planned in parallel by another
  `upgrade-planner-agent` dispatch — its plan file did not exist in this repo
  at the time this plan was written, so `conflicts_with` above carries a
  **best-guess forward reference** (`superset-pg-18.6`) following this repo's
  `<component>-<target>` naming convention. **The window agent MUST grep
  `runbooks/maintenance/plans/` for the real sibling plan_id before
  scheduling** and correct this field rather than trusting it blindly — same
  discipline as the dead-ref resolutions already recorded in
  `paperless-db-12.3.3.md` and `superset-pg-cutover.md`. Regardless of the
  exact id: **do not schedule more than one postgres-major cutover/restore
  in the same window** — two one-way DB operations competing for operator
  attention in one 90-minute attended slot is the exact stacking mistake
  `paperless-db-12.3.3` already called out for MariaDB.
- **`authentik-pg17-decommission`** (status `awaiting-soak`) is a *different*
  shape of postgres-major-risk-class work — Authentik's own 17→18 cutover
  already executed; that plan only retires the leftover 17.11 StatefulSet.
  It is lower-stakes than a live cutover but is still a one-way storage
  operation (`Retain` PVC deletion) in the same risk family. Prefer not to
  co-window it with this plan either, on the general "one one-way DB action
  per attended slot" principle above, though it is not a hard blocker if the
  window has slack.
- **Attended, not nightly**: `rollback_class: backup-restore` + one-way
  datadir + `risk: high` ⇒ operator-present window. `needs_reboot: false`,
  so any attended slot (not just Sunday) is fine.
- **Downtime is scoped to `ai/paperclip` only.** No other app in the `ai`
  namespace (anythingllm, librechat, open-webui, openclaw, hermes-agent,
  ai-sre, mcpo, next-ai-draw-io, ollama-toolfix) depends on
  `paperclip-postgresql` — verified by checking every other app's manifests
  for the service name. Expect ~10–15 minutes of paperclip UI/API downtime
  inside the window; nothing else in the cluster is affected.
- **`paperclip-backup-cleanup` CronJob (04:00 daily)** only deletes
  `*.sql` files older than 7 days under the `paperclip-data` PVC (the app's
  own dump location, *not* the Postgres PVC this plan touches) and does not
  scale anything — confirmed safe to leave running through the window, no
  interaction with this plan's Deployment/PVC edits.
- The suspend/scale in §3.1 and resume in §3.8 must stay ordered exactly as
  written: verify the DB (§4 items 1–3) **before** resuming the HelmRelease,
  so a bad restore is caught while the app is still safely at 0 replicas
  rather than serving from a broken DB.
