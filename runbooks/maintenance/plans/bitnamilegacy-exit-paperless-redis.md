---
plan_id: bitnamilegacy-exit-paperless-redis
component: paperless-ngx
pr: null                               # archived registry — no upstream tag can fix it
kind: chart                            # HelmRelease values + a new sibling manifest
current: "bundled bitnamilegacy/redis:latest (redis 8.0.3) as paperless-ngx-redis-master"
target: "redis:8.10.0-alpine (official image) as paperless-redis, chart's bundled redis disabled"
update_type: minor                     # redis 8.0.3 -> 8.10.0; the registry move is the real work
risk: medium                           # Celery broker only; no durable data
est_duration_min: 30
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/paperless-ngx                 # redis.enabled: false + explicit redis env
    - "new: deployment/paperless-redis + service/paperless-redis"
    - secret/paperless-ngx-secret               # SOPS edit — gains redis-password
    - statefulset/paperless-ngx-redis-master    # REMOVED by the chart
    - statefulset/paperless-ngx-redis-replicas  # REMOVED (already scaled 0/0)
    - secret/paperless-ngx-redis                # chart-generated — DELETED with the subchart
    - deployment/paperless-ngx                  # restarts (Celery broker moves)
    - pvc/paperless-redis                       # orphaned, Retain — kept for rollback
  shared: []                                    # paperless' OWN broker; no shared datastore
depends_on: []
conflicts_with: [paperless-ngx-3.0.5, bitnamilegacy-exit-paperless-db]
security_ref: F-d62ac46a                        # see also F-46597825 (same image, fixable class)
status: draft
window: "wed-early:2026-08-19"                 # RESHUFFLED 2026-08-16 onto the daily-window cadence
                                      # (7 windows/week, was 4). Deliberate soaks are
                                      # preserved, not compressed — see the windows YAML.
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/sops-encryption.md
  - docs/sops/paperless.md
generated: "2026-08-15"
---

# bitnamilegacy exit, phase 2a/5 — paperless-ngx Redis

## 1) Summary & why held

Phase 2a of 5. Together with 2b (`bitnamilegacy-exit-nextcloud-redis`) this is the
cheap half of the `office` namespace's bitnamilegacy exposure: **Redis instances
that hold nothing durable.** Clearing them first means the two MariaDB
replatforms (phases 3 and 4) start with the noisy, low-value half already gone —
the same sequencing the Superset migration used (`superset-redis-official` before
the Postgres stages).

**Why this is split from the Nextcloud Redis.** They were drafted as one 55-minute
plan; that consumed 92% of a 60-minute weekday window with no slack for a
rollback. Two 30-minute plans in two windows is the same work with room to
recover, and the two rollbacks were already independent (separate commits,
separate HelmReleases).

**Why no version bump can fix this.** The HelmRelease pins
`docker.io/bitnamilegacy/redis:latest`. `bitnamilegacy` is Bitnami's **archived**
catalog — the free container images were moved there on 2025-08-28 and nothing
has been published since; it exists "solely to help with migration" and receives
no updates or patches, ever. `latest` on an archived registry is a frozen tag
pretending to be a rolling one: the pod runs **redis 8.0.3** and will run 8.0.3
forever. `docker.io/bitnami/redis` is not a fallback — it publishes no semver
stream Renovate can track. The only remediation is to leave the registry.

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-d62ac46a** and **F-46597825** (both `bitnamilegacy/redis:latest`).
> Counts, CVE identifiers and exposure live on the finding records — they are
> deliberately not reproduced here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-d62ac46a`
> - CLI: `runbooks/policy-cli.py finding show F-d62ac46a`
>
> See `docs/sops/vulnerability-disclosure.md` before adding any vulnerability
> detail to a committed file.

**Why the image cannot simply be re-pointed in the subchart.** The Bitnami redis
subchart's templates assume Bitnami's entrypoint, `/opt/bitnami` config paths,
its non-root UID and its `REDIS_PASSWORD` env contract. Pointing
`redis.image.repository` at the official `redis` image renders a pod that cannot
start. The correct move is `redis.enabled: false` plus our own manifest — the
conclusion the house has already reached in `office/sure`, `office/affine`,
`office/penpot-cache` and the pending `superset-redis-official`.

**Deliberate choice — plain Deployment + Service, not `app-template`.** Both
patterns exist in-house. Plain manifests keep this datastore **out of the blast
radius** of the pending `app-template-5.0` migration (`sat-early:2026-08-29`),
the same reason `superset-redis-official` gives. Mirror
`kubernetes/apps/databases/postgresql/app/deployment.yaml` for the file shape.

**Why medium and not high — verified, not assumed.** Read on the live cluster
2026-08-15: `paperless-ngx-redis-master` holds **3 keys, no TTLs** — the Celery
broker/result backend and channels layer. Losing it drops *queued* tasks, which
is why pre-check (b) drains the consume pipeline first. Nothing here is
irreplaceable; a re-scan is cheap.

### Two traps specific to this change

**1. `paperless-ngx-redis` is a chart-GENERATED Secret.** `redis.enabled: false`
deletes it — and with it the `redis-password` key the app reads via
`A_REDIS_PASSWORD`. The password must be moved into our own SOPS secret *in the
same commit*, or paperless comes back with an unresolvable `secretKeyRef` and
sits in `CreateContainerConfigError`.

**2. Disabling the subchart also removes the chart-templated env.** From chart
0.24.1 `templates/common.yaml`, `A_REDIS_PASSWORD` and `PAPERLESS_REDIS` are
emitted **only** inside `{{- if .Values.redis.enabled }}`. Both must be declared
explicitly in our `env:` block.

**The new Service is `paperless-redis`, not `paperless-ngx-redis-master`.**
Reusing the old name would make the client-side diff zero, but during the
reconcile Helm still owns a Service of that name while kustomize-controller
applies ours — a field-manager/already-exists conflict at exactly the wrong
moment. A new name costs two reference edits and removes the race.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) what is running, and CONFIRM nothing durable lives in this Redis
mise exec -- kubectl get sts -n office | grep -i redis
mise exec -- kubectl get hr -n office paperless-ngx \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'
mise exec -- kubectl exec -n office paperless-ngx-redis-master-0 -c redis -- sh -c \
  'redis-cli -a "$REDIS_PASSWORD" INFO keyspace;
   redis-cli -a "$REDIS_PASSWORD" INFO persistence | grep -E "aof_enabled|rdb_last_save"'
# Expect a handful of celery/channels keys. If you find APPLICATION STATE here,
# STOP and re-plan.

# b) DRAIN the pipeline — queued Celery tasks die with the broker
mise exec -- kubectl exec -n office deploy/paperless-ngx -- ls -la /usr/src/paperless/consume/ | tail
mise exec -- kubectl exec -n office paperless-ngx-redis-master-0 -c redis -- \
  sh -c 'redis-cli -a "$REDIS_PASSWORD" LLEN celery'        # 0 = nothing queued
mise exec -- kubectl logs -n office deploy/paperless-ngx --since=15m | grep -iE 'celery|task|consum' | tail
# If a document is mid-OCR, WAIT. A re-scan is cheap; a half-consumed doc is not.
# Pause the scanner path if scans are arriving (docs/sops/paperless.md):
#   mise exec -- kubectl scale deploy/scan-inbox-validator -n office --replicas=0

# c) capture the CURRENT redis password to carry into SOPS unchanged.
#    Do NOT write it to a file in the repo.
mise exec -- kubectl get secret -n office paperless-ngx-redis \
  -o jsonpath='{.data.redis-password}' | base64 -d | pbcopy
echo "redis-password copied to clipboard (length: $(pbpaste | wc -c))"

# d) the official tag exists and matches the house standard
curl -s "https://hub.docker.com/v2/repositories/library/redis/tags?page_size=100&ordering=last_updated" \
  | python3 -c "import sys,json;print([t['name'] for t in json.load(sys.stdin)['results'] if t['name'].endswith('-alpine')][:10])"
# office/affine and office/sure run redis:8.8.0-alpine; superset-redis-official
# targets 8.10.0-alpine. Match 8.10.0-alpine.

# e) the volume we are about to orphan is Retain (rollback depends on it)
mise exec -- kubectl get pv paperless-redis \
  -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy,SC:.spec.storageClassName
# MUST read Retain / longhorn-static. If not, STOP — docs/sops/storage-safety.md.

# f) no in-flight reconcile
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps

1. **Marker + silence:**
   ```bash
   runbooks/update-marker.sh add paperless-ngx office 2 "redis: bitnamilegacy -> official redis 8.10.0-alpine"
   ```
   Silence `namespace=office` rollout alerts for 4h per
   `docs/sops/application-update.md` §4 Step 1.

2. **Carry the redis password into our own SOPS secret.** Edit in place — never
   decrypt to `/tmp` and re-encrypt from there (`docs/sops/sops-encryption.md`
   and the SOPS rules in `CLAUDE.md`):
   ```bash
   sops kubernetes/apps/office/paperless-ngx/app/secret.sops.yaml
   #   add:  redis-password: <the value from pre-check (c)>
   #   keep: PAPERLESS_KEY, PAPERLESS_EMAIL_USERNAME, PAPERLESS_EMAIL_PASSWORD, PAPERLESS_TOKEN
   ```
   Reusing the existing password (rather than rotating) means the client side
   needs no coordinated change and rollback is symmetric.

3. **Add the Redis manifests** in
   `kubernetes/apps/office/paperless-ngx/app/redis-deployment.yaml` — Deployment
   + Service `paperless-redis`, modelled on
   `kubernetes/apps/databases/postgresql/app/deployment.yaml`:
   - image `redis:8.10.0-alpine`
   - `command: ["redis-server", "--save", "", "--appendonly", "no", "--requirepass", "$(REDIS_PASSWORD)"]`
     with `REDIS_PASSWORD` from `secretKeyRef: {name: paperless-ngx-secret, key: redis-password}`
   - **no PVC** — the broker is drained in pre-check (b); persisting a queue we
     deliberately emptied only creates a stale-state hazard
   - `strategy: Recreate`, liveness/readiness `redis-cli -a "$REDIS_PASSWORD" ping`
   - requests 50m/64Mi, limit 256Mi (matches what the subchart had)
   - Service `paperless-redis`, port 6379, ClusterIP
   Register it in `kubernetes/apps/office/paperless-ngx/app/kustomization.yaml`
   `resources:` (after `secret.sops.yaml`, before `helmrelease.yaml`).

4. **Edit `kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml`**:
   - Replace the whole `redis:` values block (currently around line 185) with:
     ```yaml
         # Bundled Bitnami redis retired 2026-XX-XX: bitnamilegacy is an ARCHIVED
         # registry (last push 2025-08-28, no future security fixes) and
         # docker.io/bitnami/redis publishes no semver tags. Security driver
         # tracked as F-d62ac46a. Paperless now uses the official redis image
         # deployed by redis-deployment.yaml in this folder.
         redis:
           enabled: false
     ```
   - Add to the `env:` block (the chart only templates these when
     `redis.enabled` is true — chart 0.24.1 `templates/common.yaml`):
     ```yaml
           A_REDIS_PASSWORD:
             valueFrom:
               secretKeyRef:
                 name: paperless-ngx-secret
                 key: redis-password
           PAPERLESS_REDIS: "redis://:$(A_REDIS_PASSWORD)@paperless-redis:6379"
     ```
     Keep the `$(A_REDIS_PASSWORD)` interpolation form — that is how the chart
     did it and how the container runtime expands it.
   - Update the `wait-for-redis` initContainer (around line 261) to
     `until nc -z paperless-redis 6379; do` and fix its echo string.

5. **Validate, commit, push** (on `main`, stage only these four files):
   ```bash
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas \
     kubernetes/apps/office/paperless-ngx
   git add kubernetes/apps/office/paperless-ngx/app/redis-deployment.yaml \
           kubernetes/apps/office/paperless-ngx/app/kustomization.yaml \
           kubernetes/apps/office/paperless-ngx/app/secret.sops.yaml \
           kubernetes/apps/office/paperless-ngx/app/helmrelease.yaml
   git commit -m "feat(paperless-ngx): replace bundled bitnamilegacy redis with official redis 8.10.0-alpine"
   git push
   ```

6. Scale the validator back if you paused it, then clear the marker and drop the
   silence: `runbooks/update-marker.sh clear paperless-ngx`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)

# a) the release reconciled and the old objects are gone
mise exec -- kubectl get hr -n office paperless-ngx \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'
mise exec -- kubectl get sts -n office | grep -i 'paperless.*redis' \
  || echo "bundled redis StatefulSets gone (expected)"
mise exec -- kubectl get secret -n office paperless-ngx-redis 2>&1 | grep -q NotFound \
  && echo "chart-generated redis secret gone (expected)"

# b) THE image check — read the live objects, not the HR status
mise exec -- kubectl get deploy -n office paperless-redis \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'          # redis:8.10.0-alpine
mise exec -- kubectl get pods -n office -o json | python3 -c "
import sys, json
for p in json.load(sys.stdin)['items']:
    if 'paperless' not in p['metadata']['name']: continue
    for cs in p['status'].get('containerStatuses', []) + p['status'].get('initContainerStatuses', []):
        if 'bitnamilegacy' in cs['image']:
            print('STILL LEGACY:', p['metadata']['name'], cs['image'])"
# Only the mariadb StatefulSet may print (phase 3). NOTHING redis-shaped.

# c) the new Redis is reachable AND password-protected
PR=$(mise exec -- kubectl get pods -n office -l app=paperless-redis -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n office $PR -- sh -c 'redis-cli -a "$REDIS_PASSWORD" ping'    # PONG
mise exec -- kubectl exec -n office $PR -- redis-cli ping 2>&1 | grep -i 'noauth\|denied' \
  && echo "auth enforced (expected)"

# d) THE load-bearing check — paperless is USING it. Celery is the part that
#    fails silently: the web UI renders fine while ingestion is dead.
mise exec -- kubectl rollout status deploy/paperless-ngx -n office --timeout=600s
mise exec -- kubectl logs -n office deploy/paperless-ngx --since=15m \
  | grep -iE 'celery|redis|connection refused|error' | head -20
mise exec -- kubectl exec -n office $PR -- sh -c 'redis-cli -a "$REDIS_PASSWORD" INFO keyspace'
# keys must APPEAR once paperless registers its workers. An empty keyspace after
# the app is Ready means the client is NOT talking to this server.
curl -s -o /dev/null -w 'paperless %{http_code}\n' --max-time 20 "https://paperless.$DOM/"

# e) operator smoke test — the part that fails silently:
#    Drop a test PDF into the consume share and watch it get consumed
#    end-to-end (broker path). Confirm it lands in the library, then delete it.
mise exec -- kubectl logs -n office deploy/paperless-ai  --since=15m | tail -10
mise exec -- kubectl logs -n office deploy/paperless-gpt --since=15m | tail -10
mise exec -- kubectl get deploy -n office scan-inbox-validator -o jsonpath='{.spec.replicas}{"\n"}'   # 1

# f) the old volume is still there, untouched, for rollback
mise exec -- kubectl get pv paperless-redis \
  -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,RECLAIM:.spec.persistentVolumeReclaimPolicy
```

Success = HR Ready; no redis-shaped `bitnamilegacy` image left on any paperless
pod; `paperless-redis` Ready on `redis:8.10.0-alpine` with auth enforced; a
filling keyspace; a test document consumed end-to-end; `scan-inbox-validator`
back at 1 replica; the old PV still present and Retain.

## 5) Rollback

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <paperless-redis-commit-sha>   # restores redis.enabled:true + the chart env
git push
mise exec -- kubectl get hr -n office paperless-ngx \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
mise exec -- kubectl rollout status sts/paperless-ngx-redis-master -n office --timeout=300s
mise exec -- kubectl rollout status deploy/paperless-ngx -n office --timeout=600s
mise exec -- kubectl logs -n office deploy/paperless-ngx --since=10m | tail -20
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w 'paperless %{http_code}\n' --max-time 20 "https://paperless.$DOM/"
```

The revert also reverts the SOPS secret hunk (`redis-password`), the `env:` block
and the initContainer, so client and server move back together — **do not revert
the HelmRelease without the secret**. The chart re-creates its own
`paperless-ngx-redis` Secret on the way back; the chart-templated env reads
whatever it generates, so the pair stays self-consistent either way.

The bundled StatefulSet re-binds its **existing** `paperless-redis` PVC — Retain,
`longhorn-static`, backed up nightly. **Storage safety:** this is a Longhorn
volume, not a CIFS/SMB class, so a PVC delete cannot reach a share
(`docs/sops/storage-safety.md`); run the pre-flight one-liner anyway before any
deletion. **Do not delete it in this window** — it is the rollback. Retire it in
a later cleanup after a full week clean.

**There is nothing to restore data-wise:** the broker was drained before the
cutover, so a move in either direction loses only work that was already
re-runnable.

If Helm wedges `pending-upgrade`, clear it per `docs/sops/application-update.md` §11.

Confirmed back = bundled StatefulSet Running, paperless 200, a test document
consumed.

## 6) Interference notes

- **`conflicts_with: paperless-ngx-3.0.5`** (`sat-early:2026-09-19`) — that plan
  edits the **same HelmRelease `env:` block**. Two plans rewriting one values
  block in one window makes a failed verification un-attributable and a revert
  ambiguous. They must not share a window.
  **They are not in conflict on substance — the opposite.** Verified against the
  upstream v3 migration guide: v3 makes `PAPERLESS_DBENGINE` mandatory
  ("Previously, the engine was inferred from the presence of `PAPERLESS_DBHOST`")
  and this phase-set is what moves paperless from chart-templated DB/Redis env to
  explicit env. Running this plan **first** (2026-08-25, three weeks ahead)
  shrinks the 3.x diff rather than colliding with it.
- **`conflicts_with: bitnamilegacy-exit-paperless-db`** — phase 3 edits the same
  HelmRelease and lists this plan in `depends_on`. Never the same window.
- **Downstream consumers are not modified but will blip:** `paperless-ai` and
  `paperless-gpt` poll the paperless API and will log errors during the restart;
  `scan-inbox-validator` writes into the consume share; OpenClaw's `paperless`
  skill and mcpo's paperless MCP are API consumers. Nothing needs a manual
  restart — but if you scaled the validator to 0 in pre-check (b), **scale it
  back** (step 6).
- **`shared: []` is correct and deliberate**: this is paperless' *own* broker.
  The shared `databases/redis` instance is untouched.
- **Not app-template**, on purpose — keeps this datastore out of the
  `app-template-5.0` blast radius (`sat-early:2026-08-29`).
- One orphaned 5Gi Longhorn volume (`paperless-redis`) remains after this window.
  It is the rollback path; retire it in a follow-up cleanup once phase 3 is done
  and paperless has run clean for a week.
