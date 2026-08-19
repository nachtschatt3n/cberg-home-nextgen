---
plan_id: bitnamilegacy-exit-nextcloud-redis
component: nextcloud
pr: null                               # archived registry — no upstream tag can fix it
kind: chart                            # HelmRelease values + a new sibling manifest
current: "bundled bitnamilegacy/redis:latest (redis 8.0.3) as nextcloud-redis-master"
target: "redis:8.10.0-alpine (official image) as nextcloud-redis, chart's bundled redis disabled"
update_type: minor                     # redis 8.0.3 -> 8.10.0; the registry move is the real work
risk: medium                           # distributed cache + FILE LOCKING; no durable data
est_duration_min: 45                   # 30 -> 45 (AMENDED 2026-08-19): the values change is
                                       # larger than drafted — six coupled edits, not one
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
    - networkpolicy/nextcloud-redis             # SUBCHART-OWNED — vanishes with redis.enabled:false
                                                # (AMENDED 2026-08-19, see §1a item 6)
  shared: []                                    # nextcloud's OWN cache; no shared datastore
depends_on: []
conflicts_with: [bitnamilegacy-exit-nextcloud-db]
security_ref: F-d62ac46a                        # see also F-46597825 (same image, fixable class)
status: executed                                # EXECUTED 2026-08-19 (d6070b82 cutover,
                                                # 1dabbefd notify-push follow-up) in the
                                                # operator-approved ad-hoc window. Was:
                                                # AMENDED + re-vetted 2026-08-19 against a real
                                                # `helm template` render of chart 9.2.5.
# RETAIN, do not delete on the usual executed-plan convention: §5 stays the live
# rollback while the orphaned PV redis-data-nextcloud-redis-master-0 is still the
# only way back, i.e. until the "clean for a week" retirement in §6 is done and
# phase 4 (bitnamilegacy-exit-nextcloud-db) has landed.
window: null                          # cleared 2026-08-19: executed in the ad-hoc window
                                      # (d6070b82 + 1dabbefd), so the fri-early:2026-08-28 slot is
                                      # released. maintenance-plan.py buckets by `window` regardless
                                      # of `status`, so leaving it set would reserve 45m + a medium
                                      # risk-weight of a 60m window for work already done.
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

## 1a) AMENDMENT 2026-08-19 — what `redis.enabled: false` ACTUALLY removes

**The plan as originally drafted would have shipped a broken Nextcloud.** Held
back from execution on 2026-08-19 by operator instruction, amended, re-vetted.

Method — not template-reading, but a real render of the pinned chart with our
real values, diffed:

```bash
helm pull nextcloud/nextcloud --version 9.2.5 --untar
# values extracted verbatim from spec.values of our HelmRelease
helm template nextcloud ./nextcloud -f <ours> --namespace office   # redis ON
helm template nextcloud ./nextcloud -f <ours+redis.enabled:false>  # redis OFF
# diff the `nextcloud` Deployment between the two
```

`redis.enabled` gates **six** things, not one. In chart 9.2.5 the gates are
`templates/deployment.yaml` lines 28, 274, 328, 406 and `_helpers.tpl` 180-226,
plus the subchart's own resources:

1. **Pod label `nextcloud-redis-client: "true"`** (deployment.yaml:28) — removed.
   *Verified harmless:* no NetworkPolicy in the cluster selects it
   (`kubectl get netpol -A -o yaml | grep -c nextcloud-redis-client` → 0).
2. **`REDIS_HOST` + `REDIS_HOST_PORT` on the MAIN container** (`_helpers.tpl`
   `nextcloud.env.redis`) — removed. These are what `redis.config.php` reads.
   Without them Nextcloud silently falls back to no distributed cache **and no
   file locking**.
3. **`REDIS_URL` MUTATES — the trap the original draft walked into.** The helper
   picks the URL form from the *auth* values, not the enabled flag:
   ```
   {{- if or (and .Values.redis.auth.enabled .Values.redis.auth.password) ... }}
   - name: REDIS_URL
     value: "redis://:$(REDIS_HOST_PASSWORD)@$(REDIS_HOST):$(REDIS_HOST_PORT)"
   {{- else }}
   - name: REDIS_URL
     value: "redis://$(REDIS_HOST):$(REDIS_HOST_PORT)"
   {{- end }}
   ```
   Our HR currently sets `redis.auth.enabled: false`, so we get the clean form.
   **The original step 3 said to replace the WHOLE `redis:` block with just
   `enabled: false`** — which drops `auth.enabled: false` and lets the chart
   default (`auth.enabled: true`, `password: changeme`) win. Rendered result:
   `REDIS_URL="redis://:$(REDIS_HOST_PASSWORD)@$(REDIS_HOST):$(REDIS_HOST_PORT)"`
   where **`REDIS_HOST_PASSWORD` is never emitted** — an empty-password AUTH
   against a Redis with no `requirepass`. `redis.auth.enabled: false` MUST be
   retained explicitly.
4. **`init-redis-session-ini` init container** (deployment.yaml:328) — removed.
5. **`php-confd` emptyDir volume** (deployment.yaml:406) — removed.
6. **The subchart's `networkpolicy/nextcloud-redis`** — removed with the
   subchart. It restricts ingress to port 6379 on
   `app.kubernetes.io/{instance: nextcloud, name: redis}`. The replacement
   Deployment inherits no policy, so the new Redis is **unguarded** unless we
   ship one.

**On items 4 and 5 — correcting the record.** The concern raised was that losing
them "lands PHP sessions on an unwritable path". Against *this* configuration
that does **not** hold, and the render proves it: in our rendered Deployment
`php-confd` appears exactly twice — the emptyDir, and a mount **on the init
container only**. The main `nextcloud` container never mounts it (it mounts only
`zz-memory_limit.ini` and `zz-opcache.ini` into `conf.d`). The chart's
`redis-session.ini` volumeMount at deployment.yaml:274-277 lives in the
**cronjob** container block, which our values do not render. So the init
container writes `redis-session.ini` into an emptyDir nothing else ever reads —
**the whole php-confd mechanism is inert here.** Removing it is a no-op.
Do **not** re-add it via `extraVolumes`/`extraInitContainers`: that would
reintroduce dead weight and imply a coupling that does not exist. This is
recorded so the next reader does not "restore" it.

**The real fix is items 2+3, and the chart supports it directly.** Use
`externalRedis` — the chart's first-class external path (`_helpers.tpl:197`,
`{{- else if .Values.externalRedis.enabled }}`) — rather than hand-injecting
`REDIS_HOST` through `nextcloud.extraEnv` as originally drafted. Verified render
with `redis: {enabled: false, auth: {enabled: false}}` +
`externalRedis: {enabled: true, host: nextcloud-redis, port: "6379"}`:

```yaml
- name: REDIS_HOST
  value: "nextcloud-redis"
- name: REDIS_HOST_PORT
  value: "6379"
- name: REDIS_URL
  value: "redis://$(REDIS_HOST):$(REDIS_HOST_PORT)"     # clean form, no empty AUTH
```

**Also corrected: the draft pointed at the wrong `REDIS_HOST`.** Step 3 said
"`nextcloud.extraEnv` → REDIS_HOST … around line 367". Line ~367 of the
HelmRelease is **not** `extraEnv` (which is `[]` at line 201) — it is the
`extraSidecarContainers` **worker** container's own hardcoded env. That worker
keeps `nextcloud-redis-master` regardless of any chart value and must be edited
separately. Confirmed still present in the corrected render. So there are
**two** hardcoded `nextcloud-redis-master` references in the HR to repoint (the
worker sidecar's env, and the `wait-for-redis` initContainer), *plus* the
chart-level `externalRedis.host`.

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

3. **Edit `kubernetes/apps/office/nextcloud/app/helmrelease.yaml`** — FOUR edits.
   (REWRITTEN 2026-08-19; the original single-edit version shipped a broken
   `REDIS_URL` and repointed the wrong `REDIS_HOST`. See §1a.)

   **3a. Replace the `redis:` values block** (around line 596). Note
   `auth.enabled: false` is **retained deliberately** — dropping it flips the
   chart default to `auth.enabled: true` and rewrites `REDIS_URL` into an
   empty-password AUTH form (§1a item 3):
   ```yaml
       # Bundled Bitnami redis retired 2026-08-19: bitnamilegacy is an ARCHIVED
       # registry (last push 2025-08-28, no future security fixes) and
       # docker.io/bitnami/redis publishes no semver tags. Security driver
       # tracked as F-d62ac46a. Nextcloud now uses the official redis image
       # deployed by redis-deployment.yaml in this folder.
       redis:
         enabled: false
         auth:
           # DO NOT REMOVE. With the subchart disabled this value still selects
           # the REDIS_URL form in _helpers.tpl. Chart default is `true` +
           # password `changeme`, which renders
           # redis://:$(REDIS_HOST_PASSWORD)@... with REDIS_HOST_PASSWORD never
           # emitted — an empty-password AUTH against a no-requirepass Redis.
           enabled: false
   ```

   **3b. Add the `externalRedis` block** (chart-supported external path — this is
   what restores `REDIS_HOST`/`REDIS_HOST_PORT`/`REDIS_URL` on the MAIN
   container; do NOT hand-inject them via `nextcloud.extraEnv`):
   ```yaml
       externalRedis:
         enabled: true
         host: nextcloud-redis
         port: "6379"
         # no password — matches the retired instance's auth-disabled posture;
         # redis.config.php carries no password either.
   ```

   **3c. Repoint the `wait-for-redis` initContainer** (around line 229, under
   `nextcloud.extraInitContainers`) to `until nc -z nextcloud-redis 6379; do`
   and fix its echo string. Leave `wait-for-mariadb` and `install-openclaw-mail`
   untouched.

   **3d. Repoint the `extraSidecarContainers` worker's OWN env** (around line
   366): `REDIS_HOST: nextcloud-redis-master` → `nextcloud-redis`. This is a
   hardcoded container env, NOT `extraEnv` and NOT chart-driven — no value
   change reaches it. Leave `REDIS_HOST_PORT: "6379"`.

   **Verify the render before committing** — this is the step that would have
   caught the original defect:
   ```bash
   helm template nextcloud nextcloud/nextcloud --version 9.2.5 \
     -f <(python3 -c "import yaml,sys;print(yaml.safe_dump(yaml.safe_load(open('kubernetes/apps/office/nextcloud/app/helmrelease.yaml'))['spec']['values']))") \
     --namespace office | grep -A2 'name: REDIS_URL'
   # MUST be:  value: "redis://$(REDIS_HOST):$(REDIS_HOST_PORT)"
   # NOT:      value: "redis://:$(REDIS_HOST_PASSWORD)@$(REDIS_HOST):$(REDIS_HOST_PORT)"
   ```

3e. **Ship a replacement NetworkPolicy** in `redis-deployment.yaml` (§1a item 6).
   The subchart's `networkpolicy/nextcloud-redis` disappears with
   `redis.enabled: false`, leaving the new Redis unguarded. Mirror its posture —
   ingress restricted to TCP 6379 — against the new Deployment's own labels.

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

**AMENDED 2026-08-19 — run these FIRST; they are the checks that would have
caught the original defect. A green HelmRelease does not prove any of them.**

```bash
# 0a) the MAIN container's redis env, read off the LIVE pod (not the HR)
mise exec -- kubectl get deploy -n office nextcloud -o json | python3 -c "
import sys,json
c=[c for c in json.load(sys.stdin)['spec']['template']['spec']['containers'] if c['name']=='nextcloud'][0]
e={v['name']:v.get('value') for v in c.get('env',[])}
for k in ('REDIS_HOST','REDIS_HOST_PORT','REDIS_URL','REDIS_HOST_PASSWORD'):
    print(f'{k} = {e.get(k)!r}')
"
#   REDIS_HOST      = 'nextcloud-redis'      (NOT nextcloud-redis-master, NOT None)
#   REDIS_HOST_PORT = '6379'
#   REDIS_URL       = 'redis://$(REDIS_HOST):$(REDIS_HOST_PORT)'
#   REDIS_HOST_PASSWORD = None               <- and REDIS_URL must NOT reference it

# 0b) the worker sidecar was repointed too (§1a — it is hardcoded, not chart-driven)
mise exec -- kubectl get deploy -n office nextcloud -o json | python3 -c "
import sys,json
for c in json.load(sys.stdin)['spec']['template']['spec']['containers']:
    e={v['name']:v.get('value') for v in c.get('env',[])}
    if 'REDIS_HOST' in e: print(c['name'], '->', e['REDIS_HOST'])
"
#   every container must say nextcloud-redis; ANY remaining -master is a miss

# 0c) no dangling reference anywhere in the rendered spec
mise exec -- kubectl get deploy -n office nextcloud -o yaml | grep -c 'nextcloud-redis-master'   # 0

# 0d) file locking + cache actually live (this is what silently degrades)
mise exec -- kubectl exec -n office deploy/nextcloud -c nextcloud -- \
  php occ config:system:get memcache.locking      # \OC\Memcache\Redis
mise exec -- kubectl exec -n office deploy/nextcloud -- \
  redis-cli -h nextcloud-redis ping 2>/dev/null || \
  mise exec -- kubectl exec -n office deploy/nextcloud-redis -- redis-cli ping   # PONG

# 0e) the replacement NetworkPolicy exists (the subchart's vanished — §1a item 6)
mise exec -- kubectl get netpol -n office nextcloud-redis
```

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

## 4b) Execution record — 2026-08-19 (ad-hoc window)

Result: **PASS.** Commits `d6070b82` (cutover) and `1dabbefd` (notify-push
follow-up; `853bf719` was an intermediate attempt reverted by it).

The §3 pre-commit render gate passed:
`REDIS_URL = "redis://$(REDIS_HOST):$(REDIS_HOST_PORT)"`, zero
`nextcloud-redis-master` strings, no redis subchart objects.
Block 0a-0e all green. A real web session was established end to end through
the ingress, and an upload/overwrite/rename/read/delete/restore-from-trash
round trip completed with zero 423s and no `LockedException`.

**One thing the plan did not predict — a THIRD hidden reference.** §1a found
the two hardcoded `nextcloud-redis-master` strings in the HelmRelease. There is
a third, and it is not in git at all: Nextcloud's **persisted `config.php` on
the `nextcloud-config` PVC** carries a literal
`'redis' => ['host' => ...]`, baked in at install time. The main container is
immune — the chart's `redis.config.php` overlay is loaded later and its
`getenv('REDIS_HOST')` wins, so `occ config:system:get redis` reported the new
host and the release went green. But **`notify_push` parses `config.php`
directly and ignores that overlay**, so the push channel sat in a
reconnect loop against a Service that no longer existed
(`failed to lookup address information`). Nothing in the HelmRelease, the
rendered Deployment, or the HR Ready status exposes this.

Fix, for the next rename (phase 4 will hit the same trap with `dbhost`):

```bash
# Nextcloud rewrites config.php from the FULL MERGED config on any write, so a
# throwaway key round-trip refreshes the stale literal. A plain
# `occ config:system:set redis host --value=...` is a NO-OP here: it compares
# against the MERGED value, which the overlay has already made correct.
mise exec -- kubectl exec -n office deploy/nextcloud -c nextcloud -- \
  su -s /bin/sh www-data -c 'php occ config:system:set zz_touch --value=1'
mise exec -- kubectl exec -n office deploy/nextcloud -c nextcloud -- \
  su -s /bin/sh www-data -c 'php occ config:system:delete zz_touch'
# then roll notify-push so notify_push re-parses, and verify:
mise exec -- kubectl exec -n office deploy/nextcloud -c nextcloud -- \
  su -s /bin/sh www-data -c 'php occ notify_push:self-test'   # must be 6x green
```

Adding `REDIS_HOST` to the notify-push container does **not** work — tried in
`853bf719`, disproven on the live pod, reverted in `1dabbefd`, which leaves the
finding as a comment in `notify-push.yaml`.

**Add `occ notify_push:self-test` to the verification of every plan that
renames a Nextcloud backing service.** It is the only check that catches this;
pods Ready, HR Ready and `occ status` are all green while it is broken.

Also worth recording: the subchart-owned `networkpolicy/nextcloud-redis` and
our replacement share a name, so Helm deleted ours while pruning the subchart,
*after* kustomize-controller had applied it. One `flux reconcile kustomization
nextcloud -n office` put it back permanently — the race is one-time, because
the Helm release no longer tracks that object. A distinct name would avoid it
entirely.

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
  cleanup once phase 4 is done and Nextcloud has run clean for a week. It also
  fires a standing `LonghornVolumeDetached` warning for as long as it exists —
  suppress via `runbooks/policy-cli.py noise` if the soak runs long, so it does
  not mask a real detach.
- **Follow-up work this plan deliberately did NOT do**, carried out of the
  post-execution review so it is not lost:
  1. **Auth.** The replacement runs without `--requirepass`, inherited verbatim
     from the retired instance. The review established that the blocker this
     plan assumed ("Nextcloud carries no password path, so both sides must move
     together") does **not** exist — the plumbing is already there upstream.
     Enabling auth is a normal scoped change; the recipe is in the corrected
     comment at the top of `redis-deployment.yaml`.
  2. **NetworkPolicy source scoping.** The shipped policy mirrors the retired
     one 1:1, which means it constrains ports and not sources. The verified
     consumer selectors for a `from:` block are recorded in the same file.
  Both are hardening, not cutover work, and neither belongs in a window that
  was scoped as a registry move — but neither should ride as an untracked
  implicit acceptance either. Decide between a follow-up plan and an explicit
  entry in the risk register.
