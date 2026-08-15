---
plan_id: bitnamilegacy-exit-nextcloud-redis
component: nextcloud
pr: null                               # archived registry — no upstream tag can fix it
kind: chart                            # HelmRelease values + a new sibling manifest
current: "bundled bitnamilegacy/redis:latest (redis 8.0.3) as nextcloud-redis-master"
target: "redis:8.10.0-alpine (official image) as nextcloud-redis, chart's bundled redis disabled"
update_type: minor                     # redis 8.0.3 -> 8.10.0; the registry move is the real work
risk: medium                           # distributed cache + FILE LOCKING; no durable data
est_duration_min: 30
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud                     # redis.enabled: false + REDIS_HOST repointed
    - "new: deployment/nextcloud-redis + service/nextcloud-redis"
    - statefulset/nextcloud-redis-master        # REMOVED by the chart
    - deployment/nextcloud                      # restarts (locking + cache move; users logged out)
    - deployment/nextcloud-notify-push          # restarts with the stack
    - pvc/redis-data-nextcloud-redis-master-0   # orphaned, Retain — kept for rollback
  shared: []                                    # nextcloud's OWN cache; no shared datastore
depends_on: []
conflicts_with: [bitnamilegacy-exit-nextcloud-db]
security_ref: F-d62ac46a                        # see also F-46597825 (same image, fixable class)
status: draft
window: "tue-early:2026-09-08"
auto_execute: false                             # *nextcloud* is on the auto-update deny-list
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-15"
---

# bitnamilegacy exit, phase 2b/5 — Nextcloud Redis

## 1) Summary & why held

Phase 2b of 5, the twin of `bitnamilegacy-exit-paperless-redis`. Together they
clear the cheap half of the `office` namespace's bitnamilegacy exposure —
**Redis instances that hold nothing durable** — so the two MariaDB replatforms
(phases 3 and 4) start with the noisy, low-value half already gone. Same
sequencing the Superset migration used (`superset-redis-official` before the
Postgres stages).

**Why this is split from the paperless Redis.** They were drafted as one
55-minute plan; that consumed 92% of a 60-minute weekday window with no slack for
a rollback. Two 30-minute plans in two windows is the same work with room to
recover, and the two rollbacks were already independent.

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
start. The correct move is `redis.enabled: false` plus our own manifest.

**Deliberate choice — plain Deployment + Service, not `app-template`.** Keeps
this datastore **out of the blast radius** of the pending `app-template-5.0`
migration (`sat-early:2026-08-29`), the same reason `superset-redis-official`
gives. Mirror `kubernetes/apps/databases/postgresql/app/deployment.yaml`.

**Why medium and not low.** Read on the live cluster 2026-08-15:
`nextcloud-redis-master` holds **597 keys, 590 of them with TTLs** — and its role
is not just cache. `config.php` sets:

```php
'filelocking.enabled'  => true,
'memcache.distributed' => '\OC\Memcache\Redis',
'memcache.locking'     => '\OC\Memcache\Redis',
```

So this Redis carries the **distributed transactional file lock**. Losing it
drops transient locks and logs every user out — it does not lose files, but it is
the difference between "a cache blipped" and "a file operation was interrupted".
That is why this gets its own window and an upload/rename/delete/restore smoke
test rather than a `PING`.

**No SOPS work here.** Unlike paperless, this Redis runs with
`auth.enabled: false` and Nextcloud's generated `redis.config.php` carries no
password, so there is no chart-generated secret to rescue and no credential to
carry. `REDIS_HOST` / `REDIS_HOST_PORT` are already set by hand in
`nextcloud.extraEnv` — the client side is a one-line change.

**Auth parity is deliberate.** The replacement also runs without
`--requirepass`, so this window is a pure registry move. Adding auth means
editing `redis.config.php` as well; that is a follow-up, not part of this plan.

**The new Service is `nextcloud-redis`, not `nextcloud-redis-master`.** Reusing
the old name would make the client-side diff zero, but during the reconcile Helm
still owns a Service of that name while kustomize-controller applies ours — a
field-manager/already-exists conflict at exactly the wrong moment. A new name
costs two reference edits and removes the race.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) what is running, and CONFIRM nothing durable lives in this Redis
mise exec -- kubectl get sts -n office | grep -i 'nextcloud.*redis'
mise exec -- kubectl get hr -n office nextcloud \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'
mise exec -- kubectl exec -n office nextcloud-redis-master-0 -c redis -- sh -c \
  'redis-cli INFO keyspace; redis-cli INFO persistence | grep -E "aof_enabled|rdb_last_save"'
# Expect ~600 keys, almost all with TTLs (cache/locks/sessions). If you find
# APPLICATION STATE here, STOP and re-plan.

# b) baseline the app so Verification has something to compare against
mise exec -- kubectl exec -n office deploy/nextcloud -- \
  su -s /bin/sh www-data -c 'php occ status; php occ config:system:get memcache.locking; php occ config:system:get memcache.distributed'
# maintenance: false, and both memcache keys \OC\Memcache\Redis

# c) nobody is mid-upload — a file lock dropped under an active transfer is the
#    one user-visible way this goes wrong
mise exec -- kubectl logs -n office deploy/nextcloud --since=10m | grep -iE 'PUT|upload|lock' | tail

# d) the official tag exists and matches the house standard
curl -s "https://hub.docker.com/v2/repositories/library/redis/tags?page_size=100&ordering=last_updated" \
  | python3 -c "import sys,json;print([t['name'] for t in json.load(sys.stdin)['results'] if t['name'].endswith('-alpine')][:10])"
# office/affine and office/sure run redis:8.8.0-alpine; superset-redis-official
# targets 8.10.0-alpine. Match 8.10.0-alpine.

# e) the volume we are about to orphan is Retain (rollback depends on it)
mise exec -- kubectl get pv redis-data-nextcloud-redis-master-0 \
  -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy,SC:.spec.storageClassName
# MUST read Retain / longhorn-static. If not, STOP — docs/sops/storage-safety.md.

# f) no in-flight reconcile
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps

1. **Marker + silence.** Nextcloud restarts and every user is logged out:
   ```bash
   runbooks/update-marker.sh add nextcloud office 2 "redis: bitnamilegacy -> official redis 8.10.0-alpine"
   ```
   Silence `namespace=office` rollout alerts for 4h per
   `docs/sops/application-update.md` §4 Step 1.

2. **Add the Redis manifests** in
   `kubernetes/apps/office/nextcloud/app/redis-deployment.yaml` — Deployment +
   Service `nextcloud-redis`, modelled on
   `kubernetes/apps/databases/postgresql/app/deployment.yaml`:
   - image `redis:8.10.0-alpine`
   - `command: ["redis-server", "--save", "", "--appendonly", "no"]`
     — **no `--requirepass`**, matching the current `auth.enabled: false` posture
     (see §1; adding auth is a separate change that must also edit
     `redis.config.php`)
   - **no PVC** — cache, locks and sessions only; the bundled instance's 8Gi
     volume exists but holds nothing worth carrying across
   - `strategy: Recreate`, liveness/readiness `redis-cli ping`
   - requests 100m/128Mi, limit 256Mi (matches what the subchart had)
   - Service `nextcloud-redis`, port 6379, ClusterIP
   Register it in `kubernetes/apps/office/nextcloud/app/kustomization.yaml`
   `resources:`.

3. **Edit `kubernetes/apps/office/nextcloud/app/helmrelease.yaml`**:
   - Replace the whole `redis:` values block (currently around line 596) with:
     ```yaml
         # Bundled Bitnami redis retired 2026-XX-XX: bitnamilegacy is an ARCHIVED
         # registry (last push 2025-08-28, no future security fixes) and
         # docker.io/bitnami/redis publishes no semver tags. Security driver
         # tracked as F-d62ac46a. Nextcloud now uses the official redis image
         # deployed by redis-deployment.yaml in this folder. Auth stays DISABLED
         # to match the retired instance — redis.config.php carries no password.
         redis:
           enabled: false
     ```
   - `nextcloud.extraEnv` → `REDIS_HOST: nextcloud-redis` (was
     `nextcloud-redis-master`, around line 367). Leave `REDIS_HOST_PORT: "6379"`.
   - Update the `wait-for-redis` initContainer (around line 229) to
     `until nc -z nextcloud-redis 6379; do` and fix its echo string. Leave
     `wait-for-mariadb` and `install-openclaw-mail` untouched.

4. **Validate, commit, push** (on `main`, stage only these three files):
   ```bash
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas \
     kubernetes/apps/office/nextcloud
   git add kubernetes/apps/office/nextcloud/app/redis-deployment.yaml \
           kubernetes/apps/office/nextcloud/app/kustomization.yaml \
           kubernetes/apps/office/nextcloud/app/helmrelease.yaml
   git commit -m "feat(nextcloud): replace bundled bitnamilegacy redis with official redis 8.10.0-alpine"
   git push
   ```

5. Clear the marker and drop the silence on success:
   `runbooks/update-marker.sh clear nextcloud`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)

# a) the release reconciled and the old objects are gone
mise exec -- kubectl get hr -n office nextcloud \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.lastAppliedRevision}{"\n"}'   # True 9.2.5
mise exec -- kubectl get sts -n office | grep -i 'nextcloud.*redis' \
  || echo "bundled redis StatefulSet gone (expected)"

# b) THE image check — read the live objects, not the HR status
mise exec -- kubectl get deploy -n office nextcloud-redis \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'          # redis:8.10.0-alpine
mise exec -- kubectl get pods -n office -o json | python3 -c "
import sys, json
for p in json.load(sys.stdin)['items']:
    if 'nextcloud' not in p['metadata']['name']: continue
    for cs in p['status'].get('containerStatuses', []) + p['status'].get('initContainerStatuses', []):
        if 'bitnamilegacy' in cs['image']:
            print('STILL LEGACY:', p['metadata']['name'], cs['image'])"
# Only the mariadb StatefulSet and the pod's `mariadb-isalive` initContainer may
# print (both retired by phase 4). NOTHING redis-shaped.

# c) the new Redis is reachable
NR=$(mise exec -- kubectl get pods -n office -l app=nextcloud-redis -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n office $NR -- redis-cli ping                 # PONG (no auth, by design)

# d) THE load-bearing check — nextcloud is USING it
mise exec -- kubectl rollout status deploy/nextcloud -n office --timeout=900s
mise exec -- kubectl exec -n office deploy/nextcloud -- \
  su -s /bin/sh www-data -c 'php occ status'                              # maintenance: false
mise exec -- kubectl exec -n office deploy/nextcloud -- \
  su -s /bin/sh www-data -c 'php occ config:system:get memcache.locking'  # \OC\Memcache\Redis
mise exec -- kubectl exec -n office $NR -- redis-cli INFO keyspace
# db0 must be FILLING after a login. An EMPTY keyspace once users are active
# means nextcloud is NOT talking to this server — and with
# 'memcache.locking' pointed at a Redis it cannot reach, file operations fail.
mise exec -- kubectl logs -n office deploy/nextcloud --since=15m \
  | grep -iE 'redis|lock|connection refused|error' | head -20
curl -s --max-time 20 "https://drive.$DOM/status.php" | python3 -m json.tool
# installed:true, maintenance:false, needsDbUpgrade:false

# e) operator smoke test — the LOCKING path is what a PING does not cover:
#    1. Log in (session store).
#    2. Upload a file, rename it, delete it, restore it from trash.
#       Any "file is locked" / 423 error here is the failure to catch.
#    3. Open the Mail app and confirm accounts list (see memory
#       project_nextcloud_mail_account_quirks for which IMAP errors are benign).
#    4. Confirm a desktop/mobile client syncs.
mise exec -- kubectl logs -n office deploy/nextcloud-notify-push --since=15m | tail -10
mise exec -- kubectl logs -n office deploy/nextcloud-mcp         --since=15m | tail -10

# f) the old volume is still there, untouched, for rollback
mise exec -- kubectl get pv redis-data-nextcloud-redis-master-0 \
  -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,RECLAIM:.spec.persistentVolumeReclaimPolicy
```

Success = HR Ready on chart 9.2.5; no redis-shaped `bitnamilegacy` image left on
any nextcloud pod; `nextcloud-redis` Ready on `redis:8.10.0-alpine`; `occ status`
out of maintenance mode with a filling keyspace; upload/rename/delete/restore all
working with no lock errors; `status.php` clean; the old PV still present and
Retain.

## 5) Rollback

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <nextcloud-redis-commit-sha>   # restores redis.enabled:true + REDIS_HOST
git push
mise exec -- kubectl get hr -n office nextcloud \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
mise exec -- kubectl rollout status sts/nextcloud-redis-master -n office --timeout=300s
mise exec -- kubectl rollout status deploy/nextcloud -n office --timeout=900s
mise exec -- kubectl exec -n office deploy/nextcloud -- su -s /bin/sh www-data -c 'php occ status'
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s --max-time 20 "https://drive.$DOM/status.php" | python3 -m json.tool
```

The revert moves `REDIS_HOST` and the initContainer back together with
`redis.enabled`, so client and server never disagree.

**If maintenance mode is stuck ON** after the restart (the documented Nextcloud
trap), clear it at the config level rather than fighting occ:
```bash
mise exec -- kubectl exec -n office deploy/nextcloud -- \
  su -s /bin/sh www-data -c 'php occ config:system:set maintenance --value=false --type=boolean'
```
See memory `project_nextcloud_upgrade_mailapp` for the full recovery recipe.

The bundled StatefulSet re-binds its **existing**
`redis-data-nextcloud-redis-master-0` PVC — Retain, `longhorn-static`, backed up
nightly. **Storage safety:** a Longhorn volume, not a CIFS/SMB class, so a PVC
delete cannot reach a share (`docs/sops/storage-safety.md`); run the pre-flight
one-liner anyway before any deletion. **Do not delete it in this window** — it is
the rollback. Retire it in a later cleanup after a full week clean.

**There is nothing to restore data-wise:** cache, transient locks and sessions
are rebuilt on demand in either direction.

If Helm wedges `pending-upgrade`, clear it per `docs/sops/application-update.md` §11.

Confirmed back = bundled StatefulSet Running, `occ status` maintenance false,
`status.php` clean, an upload/delete round-trip working.

## 6) Interference notes

- **`conflicts_with: bitnamilegacy-exit-nextcloud-db`** — phase 4 edits the same
  HelmRelease and lists this plan in `depends_on`. Never the same window.
- **Every Nextcloud user is logged out** and every open session is invalidated:
  the session store and distributed cache move. At 05:00 on a Tuesday that is a
  non-event, but it is user-visible and sync clients will re-authenticate.
- **Downstream consumers are not modified but will blip:**
  `nextcloud-notify-push` (its whole job is the Redis-backed push channel — it is
  the loudest one in the logs), `nextcloud-metrics`, `nextcloud-mcp`,
  `nextcloud-whiteboard`, and OpenClaw's draft path through the `openclaw_mail`
  custom app. None need a manual restart.
- **`shared: []` is correct and deliberate**: this is Nextcloud's *own* cache.
  The shared `databases/redis` instance is untouched.
- **Not app-template**, on purpose — keeps this datastore out of the
  `app-template-5.0` blast radius (`sat-early:2026-08-29`).
- **Deliberately out of scope:** the Nextcloud image (34.0.2) and chart (9.2.5)
  do not move, and Redis auth is not introduced. `*nextcloud*` is on the
  auto-update deny-list precisely because chart+image bumps run occ migrations
  that stick maintenance mode and break the Mail custom_app; this plan contains
  no schema work at all, which is what keeps it at medium.
- One orphaned 8Gi Longhorn volume (`redis-data-nextcloud-redis-master-0`)
  remains after this window. It is the rollback path; retire it in a follow-up
  cleanup once phase 4 is done and Nextcloud has run clean for a week.
