---
plan_id: superset-bitnamilegacy-migration
component: superset
pr: null                              # no upstream tag can fix this — see Summary
kind: chart
current: "bitnamilegacy/postgresql 14.17.0 + bitnamilegacy/redis 7.0.10 (Superset metadata DB + cache)"
target: "off the bitnamilegacy registry entirely (CloudNativePG or official postgres; official redis/valkey)"
update_type: major                    # datastore replacement, not a version bump
risk: high
est_duration_min: 120
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - helmrelease/superset
    - "superset metadata Postgres (dashboards, charts, users, saved queries)"
    - "superset Redis (cache/celery broker)"
    - pvc/superset-postgresql
  shared: []                          # Superset's OWN bundled datastores, not the shared ones
depends_on: []
conflicts_with: []
status: draft
window: null                          # needs an operator decision on target architecture
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
generated: "2026-08-15"
---

# Superset: get off the archived `bitnamilegacy` registry

## 1) Summary & why held

`bitnamilegacy/postgresql:14.17.0` (**5 fixable CRITICAL**) and
`bitnamilegacy/redis:7.0.10` (**14 fixable CRITICAL**) — 19 criticals, the
largest remaining cluster in the CVE list.

**No bump can fix these.** `bitnamilegacy` is Bitnami's *archived* catalog: it
receives no further security updates, ever. The "newer tag available" the scanner
reports is misleading in two ways — the newest tags are major-version jumps
(PG 14→17, Redis 7→8) that the Superset chart does not support, and even
`bitnamilegacy/redis:latest` carries 7 unpatchable criticals of its own (AR-029).

So the only real remediation is **replacing the datastores**, which is why this is
a plan and not an image bump.

**Also blocked on:** the Superset chart itself is held (AR-050 / app-template
class), and per `project_superset_chart_020_redis_auth` the chart's immutable
Deployment selectors require a delete-recreate on any chart up/down bump. Doing
the datastore migration and the chart move in one window is how you lose the
metadata DB.

**Same registry, other users** (separate hygiene, not this plan):
`nextcloud-mariadb`, `paperless-ngx-mariadb`, and two unpinned
`bitnamilegacy/{redis,mariadb}:latest` floating tags in `office/`. Those should at
minimum be pinned.

## 2) Pre-checks

```bash
# what is actually running, and what holds the real data
kubectl get pods -n databases | grep superset
kubectl get pvc -n databases | grep superset

# METADATA DB IS THE WHOLE RISK: dashboards, charts, saved queries, users.
# Take a logical dump IN ADDITION to the Longhorn backup — a volume snapshot of a
# running Postgres is not a substitute for pg_dump.
kubectl exec -n databases superset-postgresql-0 -- \
  pg_dump -U superset superset > /tmp/superset-metadata-$(date +%F).sql
wc -c /tmp/superset-metadata-*.sql     # sanity: not zero

# Redis holds cache + celery broker state only — confirm nothing durable lives there
kubectl exec -n databases deploy/superset-redis -- redis-cli INFO keyspace
```

## 3) Steps

Decide the target first — this plan deliberately does not pick for you:

- **Option A (recommended): CloudNativePG** for the metadata DB. The cluster
  already runs CNPG patterns elsewhere; gives managed backups/failover and leaves
  the archived registry entirely.
- **Option B: official `postgres:` image** via the chart's `externalDatabase`
  values. Smaller change, still off bitnamilegacy, but you own backups.
- For the cache: official `redis:` (already used cluster-wide at 8.x) or
  `valkey/valkey` (already used by penpot).

Then, in order, **one datastore per window**:
1. Stand the new Postgres up alongside the old one; restore the dump into it.
2. Point Superset at it (`externalDatabase` / connection secret), reconcile,
   verify (§4), and only then decommission the old one.
3. Repeat separately for Redis — it is cache-only, so it can be cut over with a
   restart rather than a migration.

**Do not** combine with the held Superset chart bump. Datastore first, chart
later, verified in between.

## 4) Verification

```bash
kubectl get pods -n databases | grep superset     # all Ready
# Operator smoke test — this is the real verification, not pod status:
#   log in; open a dashboard that uses a saved chart; run a saved query;
#   confirm users/roles survived. A restored-but-wrong metadata DB looks
#   perfectly healthy at the pod level and is empty in the UI.
trivy image <new-postgres-image> --severity CRITICAL --ignore-unfixed
trivy image <new-redis-image>    --severity CRITICAL --ignore-unfixed
```

## 5) Rollback

Keep the old datastore running until §4 passes — that IS the rollback: point
Superset back at the old connection secret and reconcile. Once the old Postgres
is deleted, rollback becomes restore-from-dump, so do not delete it in the same
window. Retain the pg_dump regardless.

## 6) Interference notes

- Superset's Postgres/Redis are its own; the cluster-shared `databases/postgresql`
  and `databases/redis` are untouched.
- Never co-schedule with the Superset chart bump (AR-050) or with
  `longhorn-1.12.1-engine` (storage-layer work under a live DB migration).
- `window: null` on purpose: the architecture choice (A vs B) is an operator
  decision, and the plan should be re-targeted once that is made.
