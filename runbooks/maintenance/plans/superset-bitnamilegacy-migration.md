---
plan_id: superset-bitnamilegacy-migration
component: superset
pr: null
kind: chart
current: "bitnamilegacy/postgresql 14.17.0 + bitnamilegacy/redis 7.0.10 (Superset metadata DB + cache)"
target: "official redis 8.10.0-alpine + postgres 17.11-alpine — delivered in 4 stages"
update_type: major
risk: high
est_duration_min: 170                 # sum of the four stages (45+45+50+30), for reference only
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - "see the individual stage plans — this file executes nothing"
  shared: []
depends_on: []
conflicts_with: [longhorn-1.12.1-engine]
status: superseded                    # INDEX ONLY — split into 4 stage plans on 2026-08-15
window: null                          # never schedule this file; schedule the stages
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
generated: "2026-08-15"
superseded_by:
  - superset-redis-official
  - superset-pg-standup
  - superset-pg-cutover
  - superset-pg-decommission
---

# Superset: off the archived `bitnamilegacy` registry — INDEX (split into 4 stages, 2026-08-15)

**This file is an index. It executes nothing.** The original plan was 120 minutes
against a 90-minute maximum window, so it could not be scheduled at all. It is now
four stages, each of which leaves Superset in a consistent, working, independently
revertible state.

| # | plan | what moves | risk | est | window |
|---|---|---|---|---|---|
| 1 | `superset-redis-official` **(executed 2026-08-17, plan retired)** | bundled `bitnamilegacy/redis` → official `redis:8.10.0-alpine` (cache only) | medium | 45 m | `thu-early:2026-08-20` |
| 2 | `superset-pg-standup` **(executed, plan retired)** | stand up `postgres:17.11-alpine` **alongside** + restore a dump; **no cutover** | medium | 45 m | `thu-early:2026-09-03` |
| 3 | [`superset-pg-cutover`](superset-pg-cutover.md) | fresh dump + repoint `DB_HOST`; old DB **left running** as the rollback | high | 50 m | `sat-early:2026-09-12` |
| 4 | [`superset-pg-decommission`](superset-pg-decommission.md) | `postgresql.enabled:false` — the archived image finally leaves the namespace | medium | 30 m | `tue-early:2026-09-22` |

Redis first because it is cache-only and clears **the larger share of the driver**
(F-9d114719) with no data risk. Postgres is then split standup → cutover → decommission so that the DB
replacement never shares a window with the moment its rollback disappears.

## ⚠️ The decision that must be re-confirmed before stage 2

The superseded plan recorded *"DECIDED 2026-08-15 — Option A, CloudNativePG… the
cluster already runs CNPG patterns elsewhere"*. **That justification is false.**
CloudNativePG is not installed here: the only mention in the entire repo is
`kubernetes/apps/office/sure/app/helmrelease.yaml`, which *disables* it
(`cnpg.enabled: false`, `cloudnative-pg.enabled: false`) with the comment *"keeps
the cluster free of CloudNativePG + OT-Redis-Operator just for one app."*

Option A therefore requires **installing a cluster-wide operator first** — its own
plan, its own risk, and a reversal of a documented house decision. The stage plans
implement **Option B**: the house pattern already used twice in `databases/` — a
plain Deployment on an official image with a real semver stream. Same outcome (off
`bitnamilegacy`, back under Renovate coverage), no new operator. If the operator
still prefers CNPG, stage 2 must not run as written.

## Facts carried forward from the original plan

- **No bump can fix this, and the reason is in the chart itself.** Superset chart
  0.22.4's own `values.yaml` pins `bitnamilegacy/postgresql:14.17.0-debian-12-r3`
  and `bitnamilegacy/redis:7.0.10-debian-11-r4` (verified 2026-08-15). Upgrading the
  chart does not move off the archived registry.
- **`bitnamilegacy` is archived**: newest push on Docker Hub is **2025-08-28** and
  there will be no further security updates. Its semver tags do still exist (unlike
  `docker.io/bitnami/*`, which now publishes only `latest` + `sha256-*`), so *pinning*
  is possible — and pointless.
- **This is the largest remaining security cluster in the fleet.** The per-image
  breakdown is deliberately not reproduced here:

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-937701ef** (postgresql) and **F-9d114719** (redis).
> Counts, advisory references and exposure live on the finding records.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-937701ef`
> - CLI: `runbooks/policy-cli.py finding show F-937701ef`
>
> Convention: `docs/sops/vulnerability-disclosure.md`.
- **The cutover is one Secret key.** `superset-secrets` already carries `DB_HOST`,
  `DB_PORT`, `DB_USER`, `DB_PASS`, `DB_NAME`, `REDIS_HOST`, `REDIS_PORT`,
  `REDIS_PASSWORD`, and the chart mounts it through `envFromSecrets` **after** its own
  generated env Secret, so it wins. `SQLALCHEMY_DATABASE_URI` is built at runtime from
  those env vars (`_helpers.tpl`).
- **Do not fold in the chart bump.** The Superset chart is held (AR-050 class) and per
  `project_superset_chart_020_redis_auth` its immutable Deployment selectors require a
  delete-recreate on any chart up/down bump. The chart stays at 0.22.4 for all four
  stages.
- **New datastores are deliberately NOT app-template**, so Superset does not enlarge
  the blast radius of the pending `app-template-5.0` migration.
- **Same registry, other users** (separate hygiene item, not this plan set):
  `nextcloud-mariadb`, `paperless-ngx-mariadb`, and one unpinned
  `bitnamilegacy/mariadb:latest` floating tag under `office/` (both office Redis
  instances left the registry 2026-08-18/19).

## For the window agent

Schedule the **stages**, never this file. `depends_on` is a hard chain for
2 → 3 → 4; stage 1 (Redis) is independent and may run at any point before stage 4,
whose verification asserts that no `bitnamilegacy` image remains. Stage 4 out of
order is the one genuinely destructive mis-sequencing in this set: it deletes the
database Superset is using.
