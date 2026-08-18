---
plan_id: superset-redis-official
component: superset
pr: null                              # archived registry — no upstream tag can fix it
kind: chart                           # HelmRelease values + a new sibling manifest
current: "bundled bitnamilegacy/redis 7.0.10-debian-11-r4 (superset chart subchart redis 17.9.4)"
target: "redis:8.10.0-alpine (official image) deployed as superset-redis, chart's bundled redis disabled"
update_type: major                    # datastore replacement (Redis 7.0 → 8.10), cache only
risk: medium                          # cache + Celery broker only; no durable data
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - helmrelease/superset             # redis.enabled: false
    - "new: deployment/superset-redis + service/superset-redis (plain manifests)"
    - secret/superset-secrets          # REDIS_HOST is repointed (SOPS edit)
    - deployment/superset              # restarts (Recreate)
    - deployment/superset-worker       # Celery broker moves — restarts
    - deployment/superset-celerybeat   # Celery broker moves — restarts
  shared: []                           # Superset's OWN cache; the shared databases/redis is untouched
depends_on: []
conflicts_with: []
status: executed   # 2026-08-17, pulled forward from thu-early window; celery transport verified on superset-redis-official
window: null                          # cleared 2026-08-18: plan executed 2026-08-17, window slot released
security_ref: F-f6239bec        # bitnamilegacy/redis fixable-CRIT finding (linked 2026-08-17 so the sweep board can collapse it as planned)
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/sops-encryption.md
generated: "2026-08-15"
---

# Superset stage 1/4 — replace the bundled `bitnamilegacy/redis` with the official image

## 1) Summary & why held

Stage 1 of 4, split out of the former `superset-bitnamilegacy-migration` (120 min,
un-schedulable — the longest window is 90 min). **This stage is the cheap half of
that plan: it clears the larger share of F-9d114719/F-937701ef and it touches
no durable data.**

**Why no version bump can fix this.** The Superset chart itself pins the archived
mirror. From chart 0.22.4's own `values.yaml` (verified 2026-08-15):

```yaml
redis:
  image: { registry: docker.io, repository: bitnamilegacy/redis, tag: 7.0.10-debian-11-r4 }
postgresql:
  image: { registry: docker.io, repository: bitnamilegacy/postgresql, tag: 14.17.0-debian-12-r3 }
```

`bitnamilegacy` is Bitnami's **archived** catalog: the Docker Hub tag listing shows
its newest push on **2025-08-28** and nothing since. It receives no security updates,
ever. Meanwhile `docker.io/bitnami/redis` now publishes only `latest` plus `sha256-*`
attestation tags — no semver stream at all, so there is nothing for Renovate to
track and no "pin a fixed version" option. The only remediation is to leave the
registry.

**Why Redis first, and why it is medium and not high.** This Redis holds cache and
the Celery broker only — nothing durable. Cutting over is a restart, not a
migration. Doing it in its own window means the Postgres work (stages 2–4) starts
with the noisy, low-value half already gone.

**Why the image cannot simply be re-pointed in the subchart.** The Bitnami redis
subchart's templates assume Bitnami's entrypoint, config paths, non-root UID and
`REDIS_PASSWORD` env contract. Pointing `redis.image.repository` at the official
`redis` image renders a pod that cannot start. The correct move is
`redis.enabled: false` plus our own manifest — the same conclusion the house
already reached for `office/sure` ("keeps the cluster free of CloudNativePG +
OT-Redis-Operator just for one app").

**Deliberate choice — plain Deployment + Service, not `app-template`.** The house
has both patterns (`databases/redis` uses app-template 3.7.3; `databases/postgresql`
is a plain Deployment). Plain manifests are used here so that Superset's datastores
do **not** enlarge the blast radius of the pending `app-template-5.0` migration
(`sat-early:2026-08-29`). Mirror `kubernetes/apps/databases/postgresql/` for the
file shape.

**Password wiring.** `superset-secrets` already carries `REDIS_HOST`, `REDIS_PORT`,
`REDIS_PASSWORD` and `redis-password` (same value), and the chart mounts it via
`envFromSecrets` **after** its own generated env Secret — later `envFrom` entries
win, so `superset-secrets` is authoritative for the client. Reuse the existing
password for the new server (`--requirepass` from the same Secret key) and the
client side needs no change at all.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) what is actually running right now
mise exec -- kubectl get pods -n databases | grep superset
mise exec -- kubectl get hr -n databases superset \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'
mise exec -- kubectl get deploy,sts -n databases -o json | python3 -c "
import sys, json
for o in json.load(sys.stdin)['items']:
    n = o['metadata']['name']
    if 'superset' in n:
        for c in o['spec']['template']['spec']['containers']:
            print(o['kind'], n, c['name'], c['image'])"
# record the bitnamilegacy/redis tag you see — that is what this stage removes.

# b) CONFIRM nothing durable lives in this Redis before you throw it away
POD=$(mise exec -- kubectl get pods -n databases -l app.kubernetes.io/name=redis \
  -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n databases $POD -- sh -c 'redis-cli -a "$REDIS_PASSWORD" INFO keyspace'
mise exec -- kubectl exec -n databases $POD -- sh -c 'redis-cli -a "$REDIS_PASSWORD" INFO persistence' | grep -E 'aof_enabled|rdb_last_save'
# expect cache/celery keys only. master.persistence.enabled is false in our values, i.e.
# this Redis ALREADY loses its contents on every restart — that is the whole argument
# that a cutover is safe. If you find application state here, STOP and re-plan.

# c) the official tag exists
curl -s "https://hub.docker.com/v2/repositories/library/redis/tags?page_size=100&ordering=last_updated" \
  | python3 -c "import sys,json;print([t['name'] for t in json.load(sys.stdin)['results'] if t['name'].endswith('-alpine')][:10])"
# pick the current 8.x-alpine (databases/redis runs 8.10.0-alpine — match it)

# d) no in-flight reconcile, no Celery work mid-flight
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
mise exec -- kubectl logs -n databases deploy/superset-worker --tail=20
```

## 3) Steps

1. **Marker** (Superset will restart; Celery tasks in flight are dropped):
   ```bash
   runbooks/update-marker.sh add superset databases 1 "superset redis: bitnamilegacy 7.0.10 -> official redis 8.10.0-alpine"
   ```
2. **Add the new Redis manifests** in
   `kubernetes/apps/databases/superset/app/redis-deployment.yaml` — a Deployment +
   Service named `superset-redis-official`, modelled on
   `kubernetes/apps/databases/postgresql/app/deployment.yaml`:
   - image `redis:8.10.0-alpine`
   - `command: ["redis-server", "--save", "", "--appendonly", "no", "--requirepass", "$(REDIS_PASSWORD)"]`
     with `REDIS_PASSWORD` from `secretKeyRef: {name: superset-secrets, key: redis-password}`
   - no PVC (cache only; the bundled one had `persistence.enabled: false` too)
   - `strategy: Recreate`, liveness/readiness `redis-cli -a "$REDIS_PASSWORD" ping`
   - requests 50m/64Mi, limit 512Mi
   - Service `superset-redis-official`, port 6379, ClusterIP
   Add it to `kubernetes/apps/databases/superset/app/kustomization.yaml` `resources:`.
3. **Disable the bundled Redis** in
   `kubernetes/apps/databases/superset/app/helmrelease.yaml`: replace the whole
   `redis:` values block with
   ```yaml
       # Bundled Bitnami redis retired 2026-XX-XX: bitnamilegacy is an ARCHIVED
       # registry (last push 2025-08-28, no future security fixes) and
       # docker.io/bitnami/redis publishes no semver tags. Security driver
       # tracked as F-9d114719. Superset now uses the official redis image
       # deployed by redis-deployment.yaml in this folder.
       redis:
         enabled: false
   ```
4. **Repoint the client** — edit the SOPS secret in place (never decrypt to `/tmp`
   and re-encrypt from there; see `docs/sops/sops-encryption.md` and the SOPS rules
   in `CLAUDE.md`):
   ```bash
   sops kubernetes/apps/databases/superset/app/secret.sops.yaml
   #   REDIS_HOST: superset-redis-official      (was the chart's headless service)
   #   REDIS_PORT: "6379"                        (unchanged)
   #   REDIS_PASSWORD / redis-password: UNCHANGED — the new server reuses them
   ```
5. **Prove the render** before pushing — the bundled Redis must be gone and no
   `bitnamilegacy` image may remain in the Redis path:
   ```bash
   cd /tmp && rm -rf sschart && mkdir sschart && cd sschart
   curl -sSL -o s.tgz https://github.com/apache/superset/releases/download/superset-helm-chart-0.22.4/superset-0.22.4.tgz
   tar xzf s.tgz
   cd /Users/mu/code/cberg-home-nextgen
   mise exec -- yq '.spec.values' kubernetes/apps/databases/superset/app/helmrelease.yaml \
     | sed 's/\${SECRET_DOMAIN}/example.invalid/g' > /tmp/sschart/values.yaml
   mise exec -- helm template superset /tmp/sschart/superset -n databases -f /tmp/sschart/values.yaml \
     > /tmp/sschart/render.yaml
   grep -c 'bitnamilegacy/redis' /tmp/sschart/render.yaml || echo "no bundled redis (expected)"
   grep -n 'bitnamilegacy' /tmp/sschart/render.yaml | head            # postgres only, still expected here
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/databases/superset
   ```
6. **Commit + push** (on `main`, stage only these three files):
   ```bash
   git add kubernetes/apps/databases/superset/app/redis-deployment.yaml \
           kubernetes/apps/databases/superset/app/kustomization.yaml \
           kubernetes/apps/databases/superset/app/helmrelease.yaml \
           kubernetes/apps/databases/superset/app/secret.sops.yaml
   git commit -m "feat(superset): replace bundled bitnamilegacy redis with official redis 8.10.0-alpine"
   git push
   ```
   Flux reconciles: the new Redis starts, the chart's Redis StatefulSet is removed,
   and Superset + worker + beat restart onto the new broker.
7. Clear the marker on success: `runbooks/update-marker.sh clear superset`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) the release reconciled and the old objects are gone
mise exec -- kubectl get hr -n databases superset \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'   # True 0.22.4
mise exec -- kubectl get pods -n databases | grep superset
mise exec -- kubectl get sts -n databases | grep -i redis || echo "bundled redis StatefulSet gone (expected)"

# b) THE image check — read the live object, not the HR status
mise exec -- kubectl get deploy -n databases superset-redis-official \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'          # redis:8.10.0-alpine
mise exec -- kubectl get pods -n databases -o json | python3 -c "
import sys, json
for p in json.load(sys.stdin)['items']:
    if 'superset' in p['metadata']['name']:
        for cs in p['status'].get('containerStatuses', []):
            print(p['metadata']['name'], cs['image'], 'ready', cs['ready'], 'restarts', cs['restartCount'])"
# NOTHING in the superset stack may still reference bitnamilegacy/redis.

# c) the new Redis is actually reachable AND password-protected
RP=$(mise exec -- kubectl get pods -n databases -l app=superset-redis-official -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n databases $RP -- sh -c 'redis-cli -a "$REDIS_PASSWORD" ping'   # PONG
mise exec -- kubectl exec -n databases $RP -- redis-cli ping 2>&1 | grep -i 'noauth\|denied' \
  && echo "auth enforced (expected)"

# d) THE load-bearing check — Superset is USING it. Celery is the part that fails
#    silently: the web UI can look fine while async queries and alerts/reports are dead.
mise exec -- kubectl logs -n databases deploy/superset --since=15m | grep -iE 'redis|celery|connection refused|error' | head -20
mise exec -- kubectl logs -n databases deploy/superset-worker --since=15m | grep -iE 'ready|celery@|connected|error' | head -20
mise exec -- kubectl logs -n databases deploy/superset-celerybeat --since=15m | tail -20
mise exec -- kubectl exec -n databases $RP -- sh -c 'redis-cli -a "$REDIS_PASSWORD" INFO keyspace'
# expect keys to appear once Superset warms the cache — an empty keyspace after a UI
# login means the client is NOT talking to this server.

# e) operator smoke test: log in via Authentik OIDC, open a dashboard (cache path),
#    then run a saved query in SQL Lab with async enabled (Celery broker path).
```

Success = HR Ready, no `bitnamilegacy/redis` anywhere in the namespace, the new
Redis Ready with auth enforced, Superset/worker/beat logging a healthy broker
connection, keys present after a UI login, and the async SQL Lab query returning.

## 5) Rollback

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <redis-commit-sha>     # restores redis.enabled:true + the old REDIS_HOST
git push
mise exec -- kubectl get hr -n databases superset \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
mise exec -- kubectl get pods -n databases | grep -E 'superset|redis'
mise exec -- kubectl logs -n databases deploy/superset-worker --since=10m | tail -20
```

The revert also reverts the SOPS secret hunk (`REDIS_HOST`), so the client and
server move back together — do not revert the HelmRelease without the secret.
Confirmed back = the bundled Redis StatefulSet is Running again and the worker
reconnects. **There is nothing to restore:** this Redis never had persistence
(`master.persistence.enabled: false`), so a cutover in either direction loses only
cache, which Superset rebuilds.

If Helm wedges `pending-upgrade`, clear it per `docs/sops/application-update.md` §11.

## 6) Interference notes

- **Out of order:** this stage is independent of the Postgres stages and may run
  before or after them — but the *later* stages assume it has run, because
  `superset-pg-decommission` (stage 4) verifies that **no** `bitnamilegacy` image
  remains in the namespace. Running the Postgres stages first is fine; running
  stage 4 before this one just means that assertion fails.
- **Do not co-schedule with a Superset chart bump.** The chart is held (AR-050
  class) and per `project_superset_chart_020_redis_auth` its immutable Deployment
  selectors require a delete-recreate on any chart up/down bump. This stage keeps
  the chart at 0.22.4 exactly so no selector churn happens in the same window.
- Superset's web, worker and beat pods all restart. Superset alerts/reports
  (`ALERT_REPORTS: True`) will not fire during the restart.
- Deliberately **not** app-template: keeps Superset's datastores out of the
  `app-template-5.0` migration's blast radius (`sat-early:2026-08-29`).
