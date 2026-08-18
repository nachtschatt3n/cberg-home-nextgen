---
plan_id: superset-6.1.0
component: superset
pr: null                              # no Renovate PR exists — the repo pins `image.tag`
                                      # by hand and the chart already ships appVersion
                                      # 6.1.0, so Renovate sees no gap. See §1.
kind: image                           # image tag ONLY — chart stays 0.22.4 (see §1)
current: "apache/superset:5.0.0 on chart 0.22.4 (metadata DB at alembic 74ad1125881c)"
target: "apache/superset:6.1.0 on chart 0.22.4 (metadata DB migrated to alembic 4b2a8c9d3e1f)"
update_type: major                    # two application majors: 5.0.0 -> 6.0.0 -> 6.1.0
risk: high                            # one-way schema migrations + a Flask-AppBuilder major
                                      # under our only SSO path. Rollback is restore-from-dump,
                                      # NOT a tag revert. See §5.
est_duration_min: 75                  # needs a 90-min window; a 60-min weekday slot leaves
                                      # zero slack for the restore-from-dump rollback
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - helmrelease/superset             # image.tag + bootstrapScript (same commit)
    - deployment/superset              # Recreate roll onto 6.1.0
    - deployment/superset-worker       # Celery worker roll
    - deployment/superset-celerybeat   # Celery beat roll
    - job/superset-init-db             # helm post-upgrade hook — runs `superset db upgrade`
    - secret/superset-config           # chart-generated; re-rendered
    - deployment/superset-pg           # SCHEMA MUTATED (13 alembic migrations, one-way)
    - pvc/superset-pg-data             # the migrated metadata DB lives here
    - deployment/superset-redis-official   # cache invalidated (MD5 -> SHA-256 key change)
    - "READ-ONLY DEP: deployment/postgresql (databases) — Superset's only data-source
       connection is `Pellets` -> postgresql.databases.svc:5432/pellets. Not mutated,
       but §4 verification FAILS if it is down. Do not co-schedule with a plan
       declaring shared: [postgresql] (e.g. nocodb-calver)."
  shared: []                           # nothing outside Superset's own stack is perturbed;
                                       # ingress/cert-manager/CNI untouched
depends_on: [superset-pg-cutover]      # HARD. See §6 — this must not run against the DB
                                       # we are about to retire.
conflicts_with: [superset-pg-cutover, superset-pg-decommission, longhorn-1.12.1-engine]
security_ref: F-9d259837
status: draft
window: "sun-window:2026-09-20"         # SCHEDULED 2026-08-19 — OPERATOR DECISION: Option B
                                       # (after superset-pg-decommission), NOT Option A.
                                       # Why B: A (sat 08-29) would close the security driver
                                       # ~2 weeks sooner but leaves only 3 days of soak on a
                                       # freshly-cut-over database before running 13 one-way
                                       # migrations on top of it. If the cutover has a latent
                                       # issue that surfaces in week two, we would be unwinding
                                       # an app major AND a database migration together. The
                                       # driver is app-level (security_ref: F-9d259837);
                                       # that does not justify compressing a database soak.
                                       # Why 09-20 and not §6's suggested 09-13/09-19: both were
                                       # taken after this plan was written. Needs a SOLO 90-min
                                       # slot (75 min of work), so only sat-early/sun-window
                                       # qualify, and every one through 09-19 already holds a
                                       # 60-80 min HIGH-risk plan: sun 09-06 bitnamilegacy-exit-
                                       # paperless-db (70m), sat 09-12 bitnamilegacy-exit-
                                       # nextcloud-db (80m), sun 09-13 grafana-13-app (60m),
                                       # sat 09-19 authentik-postgres-18 (60m). sun-window
                                       # 2026-09-20 is the first free 90-min slot; capacity 6
                                       # (this plan = 3), no reboot plan competing for it.
                                       # Interference surface clear: cutover wed 08-26,
                                       # decommission sat 09-05, longhorn-1.12.1-engine sat
                                       # 08-22, nocodb-calver (shared: postgresql) tue 08-25.
                                       # WATCH: authentik-postgres-18 (sat 09-19) migrates the
                                       # SSO database the DAY BEFORE, and §4's acceptance test
                                       # is an Authentik OIDC login. Confirm an OIDC login works
                                       # BEFORE starting §3, so a login failure is not
                                       # mis-attributed to the Flask-AppBuilder major. If
                                       # authentik-postgres-18 slips into 09-20 or was rolled
                                       # back, move this to sat-early:2026-09-26.
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/authentik.md
  - docs/sops/longhorn.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-08-18"
---

# Superset 5.0.0 → 6.1.0 (two application majors, one-way metadata migration)

## 1) Summary & why held

`apache/superset:6.1.0` went stable on **2026-08-17** (image index digest
`sha256:08e3be59a16ef196aa6d65c8ac561ba53e5b463b972cd697d841adccc6d389bc`,
created `2026-08-17T06:12:20Z`; PyPI `apache-superset` 6.1.0 the same day). We run
`5.0.0` (image created `2025-09-11`). Two stable majors have shipped since.

**Security driver.** `security_ref: F-9d259837` — detail on the finding record in
sweep_history, per `docs/sops/vulnerability-disclosure.md`. Do not restate it here.

**AR-052 is now factually stale — flag it, do not edit it.** AR-052 (scoped to
`apache/superset`, operator-approved 2026-08-06) records the justification
*"5.0.0 is the latest STABLE … Revisit when a superset >5.0.0 stable ships."*
That condition has now been met twice. Once this plan executes, AR-052 should be
**retired or re-scoped by the operator** (`runbooks/policy-cli.py risk`). It is an
operator-approved acceptance; the window agent must not mutate it as a side effect
of this upgrade.

### What is actually changing — and the three things that made this non-safe

**This is a one-line image bump, not a chart bump.** Verified against the live
release: chart **0.22.4 already declares `appVersion: 6.1.0`** (as has every chart
since 0.16.0), and our HelmRelease overrides it back down with `image.tag: 5.0.0`.
So 6.1.0 is the version this chart is built and tested against — we are *removing*
a downgrade, not pushing the chart past its supported app.

**Consequence: the immutable-Deployment-selector trap does not apply.** The
`project_superset_chart_020_redis_auth` hazard (a chart up/down bump relabels
`spec.selector`, requiring a hand-delete of the three Deployments) is triggered by
a **chart** version change. The chart version does not move in this plan. Confirmed
by reading chart 0.22.4's `templates/`: `spec.selector` is rendered from
`superset.componentSelectorLabels`, which has no dependency on `.Values.image.tag`.
**If the executor finds themselves changing `spec.chart.spec.version`, this plan is
being executed wrong — stop.**

The three real blockers:

**(a) Our `bootstrapScript` actively downgrades redis-py below 6.1.0's hard floor.**
This is the single highest-probability failure and it is silent — it would only
surface as broken Celery/caching after the roll.

- 6.1.0 `pyproject.toml` line 95: `"redis>=5.0.0, <6.0"`
- 6.1.0 `requirements/base.txt`: `redis==5.3.1` (so the image already ships a
  correct client — it is installed by the Dockerfile's `uv pip install -e .`)
- our HelmRelease `bootstrapScript` runs, on **every** webserver / worker / beat /
  init-db pod start: `uv pip install … redis==4.5.4 …`

On 5.0.0 that pin was merely stale (base was `redis==4.6.0`, floor `redis>=4.6.0,<5.0`).
On 6.1.0 it is **two majors below a hard requirement**. The `redis` line must be
deleted from `bootstrapScript` in the same commit as the tag bump. `psycopg2-binary`
and `authlib` must stay — neither is in `requirements/base.txt`, and the published
`lean` image does not install the `postgres` extra.

**(b) Flask-AppBuilder 4.5.5 → 5.0.2 — a major, directly under our only SSO path.**
UPDATING.md, 6.0.0, [PR 33055]:

> Upgrades Flask-AppBuilder to 5.0.0. The `AUTH_OID` authentication type has been
> deprecated and is no longer available as an option in Flask-AppBuilder.

We use `AUTH_TYPE = AUTH_OAUTH` with an Authentik OIDC provider — **not** `AUTH_OID`
— so the removed auth type is not ours, and `flask-appbuilder[oauth] 5.0.2` still
declares `Authlib<2.0.0,>=0.14` (our `authlib==1.3.0` satisfies it). But FAB 5 also
moves `Flask-Babel <3 → <5` (image: 2.0.0 → 3.1.0) and
`marshmallow-sqlalchemy <0.29 → <3` (image: 0.28.2 → 1.4.0), and one of the new
migrations is `32bf93dfe2a4_add_on_cascade_in_fab_tables` — FK changes on the
`ab_*` tables that hold our users and role mappings. Our
`AUTH_ROLES_SYNC_AT_LOGIN` + `AUTH_ROLES_MAPPING` (`superset-admins` → Admin)
re-evaluates on every login through that changed stack. **Proving an Authentik
login still lands the Admin role is a first-class acceptance test (§4h), not a
nice-to-have.**

Reassuringly, the frameworks that usually break a Superset major **do not move**:
`flask` stays 2.3.3, `sqlalchemy` stays **1.4.54** (no SQLAlchemy 2.x migration),
`flask-sqlalchemy` stays 2.5.1, `marshmallow` stays `<4` (upstream deliberately
blocks 4.x: `# marshmallow>=4 has issues: apache/superset#33162`). The real movers
are FAB 4→5, redis 4→5, `sqlglot` 26→28, `urllib3` 1.26→2.6, `cryptography` 43→46,
`pandas` 2.0.3→2.1.4, `celery` 5.4→5.5, `alembic` 1.14→1.15, and a base-OS move
(`python:3.11.13-slim-bookworm` → `python:3.11.14-slim-trixie`, Debian 12 → 13).

**(c) The metadata migration is ONE-WAY. Rollback is restore-from-dump.**
13 new alembic migrations sit between the two releases (332 → 345 files; none
removed). Our live DB is at 5.0.0's head `74ad1125881c`; `94e7a3499973` (the first
6.x migration) has exactly that as its `down_revision`, and the chain terminates at
**`4b2a8c9d3e1f`** (`create_tasks_table`) — the value §4c must see afterwards.

The schema changes themselves are **purely additive** — no `drop_table` or
`drop_column` appears in any `upgrade()`; every drop lives in a `downgrade()`. New
columns (`tables.folders`, `table_columns.datetime_format`, `dashboards.theme_id`),
new tables (`theme`, `tasks`, `task_subscribers`), a widened
`ab_user.username` VARCHAR(64)→(128), and FAB FKs recreated with `ON DELETE CASCADE`.

**What makes it one-way is the data reshaping, not the DDL.** Two of the revisions
document their own irreversibility:

```python
# 363a9b1e8992_convert_metric_currencies_from_str_to_json
def downgrade():
    """
    No op downgrade.
    ...
    """
    pass

# f5b5f88d8526_fix_form_data_string_in_query_context
#   "This migration fixes data corruption, downgrade is not meaningful"
```

Plus `f1edd4a4d4f2` casts `sql_metrics.currency` TEXT → JSON and `378cecfdba9f`
rewrites `slices.params` row by row. **`superset db downgrade` is not the rollback
path and must not be attempted.**

Upstream publishes no downgrade guarantee either way — the only official word is on
[admin-docs/installation/upgrading-superset](https://superset.apache.org/admin-docs/installation/upgrading-superset/):

> While upgrading superset should not delete your charts and dashboards, we
> recommend following best practices and to **backup your metadata database before
> upgrading**.

So a pre-upgrade `pg_dump` is a hard gate (§3 step 3): without it there is no way
back. (No minimum PostgreSQL version is published for 6.x — the docs say only that
Superset "is tested to work with PostgreSQL and MySQL" as the metadata DB. PG 17.11
is well inside what SQLAlchemy 1.4.54 + psycopg2 2.9.9 support.)

> **Read UPDATING.md at the `6.1.0` tag, not at `master`.** master's `## 6.1.0`
> section has been retro-edited with post-6.1.0 items — most alarmingly a
> "composite primary keys on many-to-many association tables" block. Its migration
> (`2bee73611e32_composite_pk_association_tables`) is **absent from the 6.1.0 tag**
> and exists only on master. It is not in scope and must not be planned around.

### Two 6.x breaking changes that turned out NOT to apply to us — verified, not assumed

Both were checked against the live database rather than reasoned about, because
both would otherwise have raised the risk materially.

- **UPDATING.md 6.0.0, [PR 33116]:** `x_axis_sort_series` → `x_axis_sort` —
  *"There's a migration added that can potentially affect a significant number of
  existing charts."* Live count: `select count(*) from slices where params like
  '%x_axis_sort_series%'` → **0** of our 10 charts. No exposure.
- **UPDATING.md 6.0.0, [PR 34258]:** the Dockerfile default flipped
  `INCLUDE_CHROMIUM="true"` → `"false"` (confirmed at line 170 of both tags'
  Dockerfiles) — *"This is a breaking change for anyone using the `lean` layer, as
  it will no longer include Chromium by default."* We set `ALERT_REPORTS: True`, so
  this looks alarming. Live count: `select count(*) from report_schedule` → **0**.
  No alert or report is configured, so nothing screenshots today. (Also note 6.1.0's
  `config.py` still defaults `WEBDRIVER_TYPE = "firefox"` and
  `PLAYWRIGHT_REPORTS_AND_THUMBNAILS: False`, and `INCLUDE_FIREFOX` was already
  `"false"` on 5.0.0 — so screenshot reports were never functional here.) **If the
  operator ever wants alerts/reports, that is separate follow-up work requiring a
  browser-bearing image; do not treat it as in scope, and do not "fix" it here.**

Three more 6.x changes are real but low-impact for us, listed so the executor
recognises them rather than triages them mid-window:

- **6.1.0, [PR 35621]:** default hash algorithm MD5 → SHA-256 —
  *"Existing cached data will be invalidated upon upgrade."* Our cache is
  `superset-redis-official`, deliberately non-persistent (`--save "" --appendonly no`),
  so a cold cache is the normal post-restart state anyway. 6.1.0 also ships
  `HASH_ALGORITHM_FALLBACKS = ["md5"]`, so the transition is graceful. **Expect the
  first dashboard load to be slower. That is not a regression.**
- **6.0.0, [PR 32432]:** the List Roles view moved to the frontend and *"requires
  `FAB_ADD_SECURITY_API` to be enabled in the configuration and `superset init` to
  be executed."* Both are already satisfied: 6.1.0's `config.py` line 1631 defaults
  `FAB_ADD_SECURITY_API = True`, and the chart's `init.initscript` runs
  `superset init` on every upgrade. No config change needed.
- **6.0.0, [PR 33084]:** `DISALLOWED_SQL_FUNCTIONS` expanded across engines
  including PostgreSQL — *"Existing queries using these functions may now be
  blocked."* Our sole data source is `postgresql+psycopg2` → `pellets`, so this is
  in scope; §4i executes a real query to prove it.

The 6.1.0 MCP service, WebSocket/GAQ config, `APP_NAME`/`CUSTOM_FONT_URLS`
theming changes, `ENVIRONMENT_TAG_CONFIG` colours and ClickHouse driver floor are
all **not applicable**: chart 0.22.4 defaults `supersetMcp.enabled`,
`supersetWebsockets.enabled` and `supersetCeleryFlower.enabled` to `false`, and we
set none of those config keys. Across 5.0.0 → 6.1.0 exactly **one** feature flag is
removed (`HORIZONTAL_FILTER_BAR`, unused here) and exactly **one** top-level config
key (`THEME_OVERRIDES`, unset here); no default flag flips, and no API endpoint or
CLI command is removed.

> ⚠️ **Do NOT set `THEME_DEFAULT` while fixing anything in this window.** UPDATING.md
> pushes you toward it (for `brandAppName`, `fontUrls`), but a *partial*
> `THEME_DEFAULT` white-screens the frontend on 6.1.0 —
> [apache/superset#40375](https://github.com/apache/superset/issues/40375):
> `Cannot read properties of undefined (reading 'startsWith')`, including on the
> login page. We set no theme keys today; **leave it that way.** If theming is ever
> wanted, it needs a complete token set and its own plan.

**One verified chart/app divergence — non-blocking for us, but record it.** Superset
6.x added `superset/tasks/slack.py` and lists it in `config.py:1368`'s
`CeleryConfig.imports`. Chart 0.22.4's `_helpers.tpl` (line 325, the `cache.enabled`
branch — our path) hardcodes its own `CeleryConfig` and sets
`CELERY_CONFIG = CeleryConfig`, replacing Superset's default wholesale with only
four imports: `superset.sql_lab`, `superset.tasks.scheduler`,
`superset.tasks.thumbnails`, `superset.tasks.cache`. So `superset.tasks.slack`
never registers with our workers. **Impact today: none** — 0 report schedules, no
Slack notification config, and a missing `imports` entry does not fail startup (it
only raises `NotRegistered` if such a task is dispatched). Upstream fixed it in
chart **0.22.5** (#42945), which is **not yet in the published Helm index** — the
index tops out at 0.22.4, so Flux cannot pull it regardless. If Slack report
notifications are ever enabled, add `superset.tasks.slack` via `configOverrides`
rather than chasing a chart bump.

**Insights / local-LLM path: NOT WIRED.** Checked — Superset has no Ollama or
OpenAI configuration in this repo. Our whole feature-flag surface is
`FEATURE_FLAGS = {"EMBEDDED_SUPERSET": False, "ALERT_REPORTS": True}`. There is no
LLM path to verify. (The local-LLM Insights integration in this homelab belongs to
the **Sure** finance app, not Superset — do not conflate them.)

### Blast radius

Small and self-contained. Superset is an internal analytics UI on the `internal`
ingress class; nothing else consumes it. It holds **1 dashboard, 10 charts, 10
datasets, 2 users, 0 saved queries, 15 MB** of metadata — so the dump, the restore
and the 13 migrations are all seconds-scale, and the duration below is dominated by
image pull and human verification, not by data. Nothing shares its Postgres, its
Redis, or its PVCs. It **reads** the shared `databases/postgresql` (pgvector) for
its one dataset connection but never writes to it.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) THE ORDERING GATE — superset-pg-cutover must already have executed.
#    Superset must be on the NEW postgres before any 6.x migration runs.
mise exec -- kubectl exec -n databases deploy/superset -- printenv DB_HOST
#    MUST print: superset-pg     <-- if it still prints superset-postgresql, STOP.
#    Running this plan against the old bundled DB migrates the database we are
#    retiring and destroys the cutover's restore-and-compare baseline. See §6.

# b) we are where we think we are
mise exec -- kubectl get deploy -n databases superset \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'          # apache/superset:5.0.0
mise exec -- kubectl get hr -n databases superset \
  -o jsonpath='chart={.status.history[0].chartVersion} app={.status.history[0].appVersion}{"\n"}'
#    chart=0.22.4 app=6.1.0   <-- chart MUST already be 0.22.4; do not bump it here

# c) record the acceptance baseline (compare against this in §4)
PW=$(sops -d kubernetes/apps/databases/superset/app/secret.sops.yaml \
     | python3 -c "import sys,yaml;print(yaml.safe_load(sys.stdin)['stringData']['postgresql-password'])")
NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n databases $NEW -- env PGPASSWORD="$PW" psql -U superset -d superset -At -c "
  select 'alembic='||version_num from alembic_version
  union all select 'dashboards='||count(*) from dashboards
  union all select 'slices='||count(*)     from slices
  union all select 'tables='||count(*)     from tables
  union all select 'dbs='||count(*)        from dbs
  union all select 'ab_user='||count(*)    from ab_user
  union all select 'ab_user_role='||count(*) from ab_user_role
  union all select 'saved_query='||count(*)  from saved_query
  union all select 'report_schedule='||count(*) from report_schedule;" | tee /tmp/superset-pre.txt
#    alembic MUST read 74ad1125881c (5.0.0 head). Anything else = unexpected state, STOP.

# d) the target image really exists, and pin the multi-arch INDEX digest
curl -s "https://hub.docker.com/v2/repositories/apache/superset/tags/6.1.0" |
  python3 -c "import sys,json;d=json.load(sys.stdin);print(d['last_updated'],d['digest'])"
#    expect digest sha256:08e3be59a16ef196aa6d65c8ac561ba53e5b463b972cd697d841adccc6d389bc
#    If it differs, upstream rebuilt the tag — use the CURRENT digest and say so.
#    EXPECT THIS TO HAPPEN. The 6.1.0 git tag is dated 2026-05-01 but the image was
#    last re-pushed 2026-08-17: upstream rebuilds this tag in place. That mutability
#    is exactly why the tag is digest-pinned in step 4 — see
#    docs/sops/application-update.md §Step 0b.

# e) Superset's only data source is up (else §4i/§4j fail for the wrong reason)
mise exec -- kubectl get deploy -n databases postgresql

# f) fresh Longhorn backup of the metadata volume (belt to §3's braces)
mise exec -- kubectl get volume -n storage superset-pg-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt
#    require lastBackupAt within the last 24h; if stale, take one before proceeding.

# g) no in-flight reconcile anywhere
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
mise exec -- flux get helmreleases  -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps

1. **Marker + silence.** A `Recreate` roll plus a schema migration will fire
   `SupersetPodNotReady` / `SupersetPodRestarted` (`superset-alerts.yaml`):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   runbooks/update-marker.sh add superset databases 3 "superset 5.0.0 -> 6.1.0 major upgrade (one-way metadata migration)"
   ```
   Then the Alertmanager silence per `docs/sops/application-update.md` §4 Step 1,
   `namespace=databases`, `alertname=Superset.*|Kube(Pod|Deployment).*`, TTL 4h.

2. **Disable Flux rollback for the attempt — non-negotiable here.** The chart runs
   `superset db upgrade` from a `helm.sh/hook: post-upgrade` Job, i.e. **after** the
   webserver/worker/beat Deployments have already rolled onto 6.1.0. There is a
   real window in which 6.1 code is live against a 5.0 schema. If anything wobbles
   in that window, `remediation.strategy: rollback` will yank the release back and
   the migration never runs — the attempt/rollback thrash this app already produced
   on the 2026-08-17 redis cutover.
   ```bash
   # kubernetes/apps/databases/superset/app/helmrelease.yaml
   #   upgrade:
   #     cleanupOnFail: true
   #     remediation:
   #       retries: 0                  # was 3
   #       remediateLastFailure: false # ADD
   git add kubernetes/apps/databases/superset/app/helmrelease.yaml
   git commit -m "chore(superset): disable HR rollback for the 6.1.0 upgrade attempt"
   git push
   ```
   Wait for the HR to pick up the new spec before step 4:
   ```bash
   mise exec -- kubectl get hr -n databases superset -o jsonpath='{.spec.upgrade.remediation.retries}{"\n"}'   # 0
   ```

3. **THE GATE — pre-upgrade dump. Do not proceed without it.** The migrations are
   one-way (§1c); this dump *is* the rollback.
   ```bash
   STAMP=$(date +%F-%H%M)
   NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')
   mise exec -- kubectl exec -n databases $NEW -- \
     sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' \
     > /tmp/superset-pre-6.1.0-$STAMP.dump
   ls -l /tmp/superset-pre-6.1.0-$STAMP.dump          # NOT zero bytes (~a few MB)
   mise exec -- pg_restore -l /tmp/superset-pre-6.1.0-$STAMP.dump | head -5   # readable TOC
   echo "$STAMP" > /tmp/superset-upgrade-stamp        # §5 needs this
   ```
   Taking the dump with Superset **running** is acceptable here: content is
   effectively static (0 saved queries, 0 reports) and the only writer during the
   window is the operator. Do **not** quiesce — that is the cutover's problem, not
   this one.

4. **The change — one commit, two edits.** Both must land together; the tag bump
   alone ships a broken redis client (§1a).
   ```bash
   # kubernetes/apps/databases/superset/app/helmrelease.yaml
   ```
   **Edit 1 — image tag, digest-pinned to the verified index digest:**
   ```yaml
       image:
         repository: apache/superset
         # 6.1.0 stable, published 2026-08-17. Chart 0.22.4 already declares
         # appVersion 6.1.0 — this removes a pin-down, it does not outrun the chart.
         # Index (multi-arch) digest, verified 2026-08-18. Do NOT pin a per-platform digest.
         tag: 6.1.0@sha256:08e3be59a16ef196aa6d65c8ac561ba53e5b463b972cd697d841adccc6d389bc
         pullPolicy: IfNotPresent
   ```
   **Edit 2 — `bootstrapScript`: drop the `redis` line, bump `psycopg2-binary`:**
   ```yaml
       bootstrapScript: |
         #!/bin/bash
         # Superset 6.1.0 hard-requires redis>=5.0.0,<6.0 (pyproject.toml) and the
         # image already ships redis==5.3.1 (requirements/base.txt). The old
         # `redis==4.5.4` line here silently DOWNGRADED the client two majors below
         # that floor on every pod start — removed deliberately, do not restore it.
         # psycopg2-binary and authlib ARE still needed: neither is in base.txt, and
         # the published `lean` image does not install the `postgres` extra.
         # 6.1.0 pins psycopg2-binary==2.9.9 in that extra; authlib 1.3.0 satisfies
         # flask-appbuilder[oauth] 5.0.2's Authlib<2.0.0,>=0.14.
         uv pip install --python /app/.venv/bin/python \
           psycopg2-binary==2.9.9 \
           authlib==1.3.0
         if [ ! -f ~/bootstrap ]; then echo "Running Superset with UID $(id -u)" > ~/bootstrap; fi
   ```
   Leave **everything else untouched** — `spec.chart.spec.version: 0.22.4`,
   `timeout: 15m`, `configOverrides.oidc.py`, `cache.host`, `redis.enabled: false`,
   `postgresql.enabled: true`, `supersetNode.strategy: Recreate`, the worker
   `--concurrency=4` command, resources.
   ```bash
   git add kubernetes/apps/databases/superset/app/helmrelease.yaml
   git commit -m "feat(superset): 5.0.0 -> 6.1.0 (chart stays 0.22.4; drop the redis-py downgrade from bootstrapScript)

Chart 0.22.4 already declares appVersion 6.1.0; this removes the image.tag pin-down.
bootstrapScript no longer reinstalls redis: 6.1.0 requires redis>=5.0.0,<6.0 and the
image ships 5.3.1, so the old redis==4.5.4 line was a two-major downgrade on every
pod start. psycopg2-binary moved to 2.9.9 to match 6.1.0's postgres extra.
Metadata migration is one-way (13 alembic revisions, 74ad1125881c -> 4b2a8c9d3e1f);
pre-upgrade dump taken as the rollback. Plan: superset-6.1.0. security_ref: F-9d259837"
   git push
   ```

5. **Watch the roll, then the migration.** Do **not** hand-delete pods mid-`Recreate`.
   ```bash
   # Deployments roll first (post-upgrade hook, remember)
   mise exec -- kubectl rollout status deploy/superset -n databases --timeout=900s
   # then the hook Job. helm.sh/hook-delete-policy: before-hook-creation means the
   # old Job is deleted and recreated — there is NO immutable-Job problem here.
   mise exec -- kubectl get job -n databases superset-init-db -w      # ctrl-C on Completions 1/1
   mise exec -- kubectl logs -n databases job/superset-init-db --tail=200
   #   expect: "Upgrading DB schema..." then alembic INFO lines for the 13 revisions,
   #   then "Initializing roles..." (superset init), then create-admin (|| true).
   #   Any Traceback here = the migration failed → §5.
   ```
   **If the webserver crash-loops before the hook fires** (6.1 code on the 5.0
   schema), do not revert immediately — drive the migration by hand from a 6.1.0
   pod, then let the Deployments settle:
   ```bash
   # if ANY superset pod is alive, drive it from there:
   mise exec -- kubectl -n databases exec deploy/superset -- superset db upgrade

   # if all three are crash-looping, run it from the worker (it has the same image,
   # env and config mounts but no HTTP readiness probe to fail):
   mise exec -- kubectl -n databases exec deploy/superset-worker -- \
     sh -c '. /app/pythonpath/superset_bootstrap.sh; superset db upgrade'
   ```
   (Delegate this to cberg-agent — it is a live cluster action.) Once
   `alembic_version` reads `4b2a8c9d3e1f`, restart the webserver and continue at §4.

6. **On success only**, restore the guard rails and clear the noise suppression:
   ```bash
   #   upgrade.remediation.retries: 3   (restore)
   #   remove remediateLastFailure: false
   git add kubernetes/apps/databases/superset/app/helmrelease.yaml
   git commit -m "chore(superset): restore HR rollback remediation after the 6.1.0 upgrade"
   git push
   runbooks/update-marker.sh clear superset
   # DELETE the Alertmanager silence (do not wait for the 4h TTL)
   ```

7. **Retire this plan file** in the same commit that lands the upgrade, per
   `runbooks/maintenance/plans/README.md`, and set the finding's disposition:
   ```bash
   source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up
   runbooks/policy-cli.py finding detail F-9d259837 --plan superset-6.1.0 --detail-file /tmp/d.md
   ```
   Then surface AR-052 to the operator for retirement/re-scoping (§1). **Do not edit
   AR-052 from this plan.**

## 4) Verification

Success = **every** item below. (a)–(g) are mechanical; (h)–(k) are the ones that
actually catch a bad upgrade, and (h) and (i) require the operator.

```bash
cd /Users/mu/code/cberg-home-nextgen
PW=$(sops -d kubernetes/apps/databases/superset/app/secret.sops.yaml \
     | python3 -c "import sys,yaml;print(yaml.safe_load(sys.stdin)['stringData']['postgresql-password'])")
NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')

# a) the new BYTES are running — verify by imageID, not by tag string
mise exec -- kubectl get pods -n databases -l app.kubernetes.io/instance=superset \
  -o custom-columns=POD:.metadata.name,IMAGEID:.status.containerStatuses[0].imageID
#    every imageID must resolve to sha256:08e3be59a16ef196aa6d65c8ac561ba53e5b463b972cd697d841adccc6d389bc

# b) the app agrees
mise exec -- kubectl exec -n databases deploy/superset -- superset version 2>&1 | tail -3     # 6.1.0

# c) the migration reached head
mise exec -- kubectl exec -n databases $NEW -- env PGPASSWORD="$PW" psql -U superset -d superset -At \
  -c "select version_num from alembic_version;"
#    MUST be 4b2a8c9d3e1f  (was 74ad1125881c). Unchanged = the hook never ran → §5.
mise exec -- kubectl exec -n databases $NEW -- env PGPASSWORD="$PW" psql -U superset -d superset -At \
  -c "select to_regclass('public.tasks') is not null, to_regclass('public.theme') is not null;"
#    both t — the two new 6.x tables landed

# d) THE REDIS-PIN REGRESSION TEST — this is the check that proves Edit 2 took
for D in superset superset-worker superset-celerybeat; do
  echo -n "$D redis-py="
  mise exec -- kubectl exec -n databases deploy/$D -- \
    /app/.venv/bin/python -c "import redis;print(redis.__version__)"
done
#    all three must be 5.x (expect 5.3.1). A 4.x here = the bootstrapScript edit is
#    missing or was reverted — Celery/caching is broken even if the pods look Ready.

# e) Celery is genuinely alive (not just the pod)
mise exec -- kubectl exec -n databases deploy/superset-worker -- \
  celery -A superset.tasks.celery_app:app inspect ping
mise exec -- kubectl logs -n databases deploy/superset-celerybeat --since=15m | tail -20
#    beat must be emitting schedule ticks, no "Cannot connect to redis" / AuthenticationError
mise exec -- kubectl logs -n databases deploy/superset --since=20m \
  | grep -iE 'traceback|error|alembic|could not connect' | head -30

# f) pods stable (0 restarts after settle) and the alerts are quiet
mise exec -- kubectl get pods -n databases | grep superset

# g) data survived — diff against the pre-check baseline
mise exec -- kubectl exec -n databases $NEW -- env PGPASSWORD="$PW" psql -U superset -d superset -At -c "
  select 'dashboards='||count(*) from dashboards
  union all select 'slices='||count(*) from slices
  union all select 'tables='||count(*) from tables
  union all select 'dbs='||count(*)    from dbs
  union all select 'ab_user='||count(*) from ab_user
  union all select 'ab_user_role='||count(*) from ab_user_role;" > /tmp/superset-post.txt
diff <(grep -v alembic /tmp/superset-pre.txt) /tmp/superset-post.txt && echo "COUNTS MATCH"

DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "https://superset.$DOM/health"     # 200
```

**Operator smoke test — the load-bearing part. A migrated-but-wrong Superset is
perfectly healthy at pod level and useless in the browser.**

- **(h) Authentik OIDC login, and the ROLE.** Log in at `https://superset.$DOM` via
  the Authentik button. It must (1) complete the redirect without an
  `invalid_request` / `redirect_uri` error — proving `ENABLE_PROXY_FIX` +
  `PROXY_FIX_CONFIG` still take effect through FAB 5 — and (2) land you as
  **Admin**, not a freshly-registered Gamma. Confirm under Settings → List Users
  that your role is Admin and that `ab_user_role` did not grow. *This is the check
  for the FAB 4→5 major (§1b); if it fails, nothing else matters.*
  See `docs/sops/authentik.md` if the provider side needs inspecting.
  *(6.x hardcodes the Security / List Users / List Roles menu to the Admin role and
  adds `SUPERSET_SECURITY_VIEW_MENU = True` — see
  [#37097](https://github.com/apache/superset/issues/37097). Our
  `superset-admins` → Admin mapping covers it; if that menu is missing, the role
  mapping is what failed, which is exactly what this test exists to catch.)*
- **(i) A dashboard renders WITH DATA.** Open the one dashboard; every panel must
  paint real numbers, not "No results" and not an error card. This exercises the
  6.x chart-params migrations end to end.
- **(j) A chart query executes.** Open a chart in Explore and hit Run. Then SQL Lab
  → the `Pellets` connection → run a real `select … from … limit 10`. A
  *"disallowed function"* error here is the expanded `DISALLOWED_SQL_FUNCTIONS`
  (§1, PR 33084), not a broken upgrade — note the function and decide, do not
  auto-revert for it.
- **(k) The Databases list still shows the `Pellets` connection** and Test
  Connection passes (proves `psycopg2-binary==2.9.9` installed into the venv).

**Not applicable, do not go looking for them:** alerts/reports (0 configured, and
6.1.0's lean image has no browser — §1), the Insights/local-LLM path (not wired to
Superset at all), Flower/WebSocket/MCP (chart-disabled).

**Expected and NOT a regression:**
- The first dashboard load is slow (SHA-256 cache key change invalidated the cache, §1).
- A **repeating** `WARNING … Could not load default spinner SVG: … loading.svg` in
  the webserver log. Known 6.1.0 cosmetic bug
  ([#40478](https://github.com/apache/superset/issues/40478)) — harmless, but it is
  high-volume and will look like a new error signal to log-based alerting. The §4e
  grep is deliberately `-iE 'traceback|error|…'` so this WARNING does not match; if
  it starts showing up on the sweep's log-noise board afterwards, suppress it via
  `runbooks/policy-cli.py noise` rather than treating it as an upgrade failure.

## 5) Rollback

**`superset db downgrade` is NOT the rollback. Do not run it.** The migration chain
contains an explicit no-op `downgrade()` (§1c) — a downgrade would leave the schema
claiming 5.0.0 while the data stays in 6.x shape, which is worse than either state.

**The rollback is: restore the §3-step-3 dump, then revert the image.** Both halves,
in this order, or the app comes up 5.0.0 against a 6.1.0 schema.

```bash
cd /Users/mu/code/cberg-home-nextgen
STAMP=$(cat /tmp/superset-upgrade-stamp)
NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')

# 1. stop the writers (delegate live cluster actions to cberg-agent)
mise exec -- kubectl scale deploy/superset deploy/superset-worker deploy/superset-celerybeat \
  -n databases --replicas=0
mise exec -- kubectl get pods -n databases | grep superset      # only superset-pg / redis remain

# 2. restore the pre-upgrade metadata DB over a clean schema
mise exec -- kubectl cp /tmp/superset-pre-6.1.0-$STAMP.dump databases/$NEW:/tmp/rollback.dump
mise exec -- kubectl exec -n databases $NEW -- sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -c "drop schema public cascade; create schema public;"'
mise exec -- kubectl exec -n databases $NEW -- sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     --no-owner --no-privileges /tmp/rollback.dump' 2>&1 | tail -30
#    ownership/extension warnings are benign; any `error:` line is not.

# 3. revert the image + bootstrapScript commit (§3 step 4)
git revert --no-edit <upgrade-commit-sha>
git push

# 4. bring it back and CONFIRM both halves reverted together
mise exec -- kubectl scale deploy/superset deploy/superset-worker deploy/superset-celerybeat \
  -n databases --replicas=1
mise exec -- kubectl rollout status deploy/superset -n databases --timeout=900s
mise exec -- kubectl exec -n databases deploy/superset -- superset version 2>&1 | tail -3   # 5.0.0
mise exec -- kubectl exec -n databases $NEW -- env PGPASSWORD="$PW" psql -U superset -d superset -At \
  -c "select version_num from alembic_version;"                                            # 74ad1125881c
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "https://superset.$DOM/health"       # 200
```
Then re-run the §2c baseline query and confirm it matches `/tmp/superset-pre.txt`
exactly, and log in once via Authentik to confirm the role mapping is back.

Finally restore `retries: 3` / drop `remediateLastFailure: false` (§3 step 6),
clear the marker and delete the silence — the rollback path must not leave the HR
with rollback disabled.

**Recovery floors, in order of preference:**
1. `/tmp/superset-pre-6.1.0-$STAMP.dump` — the primary, above.
2. The Longhorn backup of `superset-pg-data` from §2f — restore per
   `docs/sops/backup.md` + `docs/sops/longhorn.md`.
3. **Only while `superset-pg-decommission` has not yet run:** `superset-postgresql-0`
   still holds the pre-*cutover* data at schema `74ad1125881c`. It is stale by
   however long the cutover soak has been running, and reaching it means also
   reverting `DB_HOST` in `secret.sops.yaml`. Last resort, and note that using it
   discards anything created since the cutover.

## 6) Interference notes

**Ordering — `depends_on: [superset-pg-cutover]` is the whole point of this section.**

Today (2026-08-18) Superset still runs on the **old** bundled
`bitnamilegacy/postgresql 14.17.0` StatefulSet. The replacement `postgres:17.11-alpine`
(`superset-pg`) was stood up alongside it this morning (commit `95322f1f`,
restore verified 47/47 tables identical) but Superset is **not** repointed —
`superset-pg-cutover` (currently `wed-early:2026-08-26`) does that.

Running this plan first would be wrong in two independent ways:

1. **It would migrate the database we are about to retire.** The 13 one-way 6.x
   migrations would land on `superset-postgresql`, and the cutover's fresh
   dump/restore would then carry a 6.x schema onto `superset-pg` — while the
   *rollback* database (the old one, by design left running) would also already be
   at 6.x. The cutover's rollback story is "the old DB is untouched and still
   correct". A 6.x migration destroys exactly that property.
2. **It would invalidate the cutover's acceptance test.** `superset-pg-cutover`
   proves itself by comparing `pg_stat_user_tables` row counts and `alembic_version`
   between the two databases, restore-and-compare style. Mutating the schema across
   that comparison makes the baseline meaningless — the comparison would either be
   run against a moved target or, worse, pass while comparing two equally-wrong
   states.

§2a is the hard gate: `printenv DB_HOST` must read `superset-pg`. **If it reads
`superset-postgresql`, abort the plan — do not "just also do the cutover".**

**Scheduling — DECIDED 2026-08-19: Option B, `sun-window:2026-09-20`.** The trade
below is recorded for history; it is **closed** — the window agent must not re-open
it. Needs a **90-minute** slot (`sat-early` or `sun-window`); 75 min of work in a
60-min weekday slot leaves nothing for a restore-from-dump rollback, and 75 min
against a 90-min window means the slot must be **solo**.

- **Option A — `sat-early:2026-08-29`** (earliest 90-min slot after the cutover).
  Closes the security driver ~2 weeks sooner. **Cost:** it lands *inside* the
  cutover's deliberate 10-day soak, which ends at `superset-pg-decommission`
  (`sat-early:2026-09-05`). Once 6.1's migrations run, the old bundled DB stops
  being a one-line rollback for the cutover — reverting would become a two-part
  revert (image tag *and* `DB_HOST`), and `superset-pg-decommission`'s frontmatter
  `current:` ("bundled … still running (idle) alongside the live postgres:17.11-alpine")
  must be re-read before it executes, because the live DB will no longer be at the
  schema it assumes.
- **Option B — the first 90-min slot after `superset-pg-decommission`
  (≥ 2026-09-05; `sun-window:2026-09-13` or `sat-early:2026-09-19` are free).**
  Cleanest: the cutover's soak completes untouched, and the major upgrade starts
  from a single, settled metadata DB. **Cost:** ~3 more weeks on the security driver.

Per the windows YAML: *"Daily windows compress the INDEPENDENT work; they must not
be used to collapse a soak."* This plan is not independent of that soak.

**Operator ruling (2026-08-19): Option B.** Option A's 3-day soak on a freshly
cut-over metadata DB, followed immediately by 13 one-way migrations, risks having to
unwind an app major *and* a database migration together if a latent cutover issue
surfaces in week two. An app-level driver (`security_ref: F-9d259837`) does not
justify compressing a database soak.

The two slots §6 originally offered as free were both taken between this plan being
written and being scheduled (`sun-window:2026-09-13` → `grafana-13-app`;
`sat-early:2026-09-19` → `authentik-postgres-18`, itself scheduled 2026-08-18). The
first genuinely free 90-min slot on/after the decommission is **`sun-window:2026-09-20`**
— see the frontmatter comment for the full slot-by-slot elimination and the
Authentik-adjacency pre-flight note.

**Same-window exclusions.**
- `conflicts_with: superset-pg-cutover` — the cutover is the prerequisite, and the
  two together are ~125 min of serial work on the same database in one window.
- `conflicts_with: superset-pg-decommission` — the decommission removes the
  deepest recovery floor listed in §5.
- `conflicts_with: longhorn-1.12.1-engine` — matches the sibling superset plans;
  the metadata PVC lives on Longhorn and a schema migration must not run under
  storage-engine work.
- **Not in `conflicts_with`, but do not co-schedule:** any plan declaring
  `shared: [postgresql]` (today: `nocodb-calver`, `tue-early:2026-08-25`).
  Superset's sole data-source connection is
  `postgresql.databases.svc.cluster.local:5432/pellets`; if that Deployment is
  bouncing, §4i/§4j fail for a reason that has nothing to do with this upgrade,
  and the window agent will read it as a regression.

**Things the window agent should expect and NOT treat as failure.**
- Superset is genuinely **down for the roll** (`supersetNode.strategy: Recreate`,
  plus a large first-time image pull — 6.1.0 is a different base layer set to
  5.0.0, Debian 12 → 13, so nothing is cached on the nodes). Budget 10–15 min.
- The webserver rolls onto 6.1.0 **before** `superset db upgrade` runs (the chart's
  migration Job is a `post-upgrade` hook). Brief 6.1-code-on-5.0-schema errors in
  the webserver log during that window are expected. This is exactly why §3 step 2
  disables Flux rollback — without it the HR remediates mid-migration and thrashes.
- The HR `timeout: 15m` is already set for this app's `Recreate` transition. **Do
  not lower it**, and do not "help" by deleting pods.
- First dashboard load after the upgrade is slow (cache key algorithm changed).
- `superset-init-db` Job pods churn: the hook deletes and recreates the Job
  (`hook-delete-policy: before-hook-creation`). There is **no** immutable-Job
  problem here, unlike `docs/sops/immutable-job-image-bumps.md`.

**Chart version must not move.** `spec.chart.spec.version` stays `0.22.4`. Chart
0.22.4 already targets appVersion 6.1.0, so there is nothing to gain, and a chart
bump would drag in the immutable-selector delete-recreate dance
(`project_superset_chart_020_redis_auth`) on top of a one-way schema migration —
two independent failure modes in one window. As of writing, 0.22.4 is also the
**newest installable** chart: 0.22.5 and 0.22.6 have GitHub release tags but are
**absent from `https://apache.github.io/superset/index.yaml`**, so Flux cannot
resolve them. If they land in the index before this executes, the window agent's
Step-0 safe-update pass may bump the chart on its own — in that case **re-verify the
rendered `spec.selector` and this plan's assumptions before executing**; do not
proceed on the assumption that the chart is where this plan left it. (For the
record, the diff from 0.20.0 → 0.22.4 is additive-only — the sole removals are five
`maxUnavailable: 1` PDB defaults — and the bundled bitnami subcharts are pinned
identically at `postgresql 16.7.27` / `redis 17.9.4`. The immutable-selector break
was chart **0.19.0**, which is behind us; selectors carry no version component.)

**Post-execution follow-ups (not part of this window):**
- Retire or re-scope **AR-052** — operator action, `runbooks/policy-cli.py risk`.
- Optionally adopt 6.1.0's `DISTRIBUTED_COORDINATION_CONFIG` (a new Redis-backed
  coordination backend, *"recommended for Redis enabled production deployments"*)
  pointed at `superset-redis-official`. Purely additive, zero urgency at our scale.
- Alerts/reports remain non-functional (no browser in the lean image). If the
  operator ever wants them, that is a separate plan needing a Chromium-bearing
  image build.
