---
plan_id: redis-fleet-8.10.2
component: redis                      # matches the held dep basename `redis` for every consumer
pr: null                              # coverage.py needs_plan (direct-bump lane) — no Renovate PR
kind: image
current: "redis:8.10.1-alpine on 8 consumers (databases/redis, databases/superset-redis-official, download/tube-archivist-redis, media/immich-redis, office/nextcloud-redis, office/paperless-redis, office/sure-redis, ai/open-webui-redis sidecar of chart open-webui 17.0.0)"
target: "redis:8.10.2-alpine on all 8 consumers (open-webui app is NOT part of this plan any more: already v0.12.3 / chart 17.0.0)"
update_type: patch
risk: medium                          # Every leg alone is low (same-minor patch, RDB_VERSION 15 unchanged, 6 upstream
                                      # commits). Medium because: (a) nextcloud-redis now enforces a password and
                                      # logs every user out; (b) the sure-redis leg SILENTLY EMPTIES Sure's
                                      # sidekiq-cron schedule unless sure-worker is restarted afterwards (§1.4);
                                      # (c) 8 restarts of shared session/broker stores in one slot.
est_duration_min: 70                  # pre-checks 10 · 8 legs x ~5 · sure worker restart +3 · waits the gates absorb
                                      # (nextcloud-cron <=5, immich poll <=3, notify-push <=3) · attended paperless
                                      # PDF + Nextcloud login + open-webui chat. open-webui leg SHRANK (no app roll,
                                      # no sqlite backup). 70 would be the whole sat-attended budget, so this plan
                                      # takes a SUNDAY slot (180).
needs_reboot: false
touches:
  namespaces: [databases, download, media, office, ai]
  resources:
    - helmrelease/redis                         # databases — app-template, AOF on pvc/redis-data
    - deployment/redis
    - pvc/redis-data                            # remounted by the Recreate, AOF re-loaded; not modified
    - deployment/superset-redis-official        # databases — plain manifest (superset Kustomization)
    - helmrelease/tube-archivist-redis          # download — RDB on pvc/tube-archivist-redis-data
    - deployment/tube-archivist-redis
    - pvc/tube-archivist-redis-data             # remounted, dump.rdb re-loaded; not modified
    - helmrelease/immich-redis                  # media
    - deployment/immich-redis
    - deployment/nextcloud-redis                # office — plain manifest (nextcloud Kustomization), requirepass via secret/nextcloud-config
    - secret/nextcloud-config                   # read-only reference (redis-password key); not modified
    - deployment/paperless-redis                # office — plain manifest (paperless-ngx Kustomization), requirepass
    - helmrelease/sure-redis                    # office
    - deployment/sure-redis
    - deployment/sure-worker                    # office — ROLLOUT RESTART after the swap (§3 leg 6)
    - helmrelease/open-webui                    # ai — ONLY the redis sidecar tag changes (chart 17.0.0, app v0.12.3 untouched)
    - deployment/open-webui-redis
    # consumers that reconnect in-process and are NOT restarted (asserted in §4):
    - statefulset/open-webui
    - deployment/superset-worker
    - deployment/superset-celerybeat
    - deployment/tube-archivist
    - deployment/immich-server
    - deployment/nextcloud
    - deployment/nextcloud-notify-push          # may restart itself on redis loss (did twice 2026-09-27)
    - deployment/paperless-ngx
    - deployment/sure-web
  shared: [monitoring]                  # §4 reads Prometheus (the window's instrument). No gateway,
                                        # storage-class, DNS or CNI change; the two PVCs are only
                                        # remounted by their own pod.
depends_on: []
conflicts_with:
  - tube-archivist-0.6.0   # reciprocal, added 2026-10-26 (sweep a1721200 plan review)
  - tube-archivist-elasticsearch-9.5.5   # reciprocal, added 2026-10-26 (sweep a1721200 plan review)
  # Same consumers / same files (reciprocity added 2026-10-24 re-plan; each is listed back by these plans):
  - nextcloud-9.4.1                     # vetted nightly:2026-10-28 — Nextcloud app roll; lists this plan. Must be settled BEFORE leg 8.
  - nextcloud-whiteboard-2.1.2          # vetted nightly:2026-10-29 — Nextcloud whiteboard (uses nextcloud redis path); lists this plan.
  - nextcloud-mcp-0.201.2               # blocked — lists this plan (nextcloud-redis restart)
  - nextcloud-mcp-0.198.0               # blocked — reciprocity from 2026-10-05 review
  # sure-0.7.5 dead ref removed 2026-10-24 (plan file no longer exists); a future sure-* plan that rolls sure-redis/sure-worker must serialize with leg 6.
  - bitnamilegacy-exit-nextcloud-db     # blocked — quiesces Nextcloud; never stack a session-store restart on a DB cutover.
  - bitnamilegacy-exit-nextcloud-redis  # nextcloud-redis rewrite; same file/restart
  - paperless-db-13.0.2                 # vetted — restarts paperless-ngx and its DB; keep the celery-broker swap out of that slot.
  - python-fleet-3.15.0                 # draft sat-attended:2026-11-14 — rolls ai/ + office/ app images that are redis consumers
  - immich-server-3.3.5                 # reciprocity (2026-10-25): rolls immich-server, the BullMQ consumer of immich-redis (leg 5); never the same night
  - openclaw-2026.10.5                  # 2026-10-31 attended full day, namespace ai
  # Platform serialisation (a roll of these confounds every reconnect gate in §4):
  - helm-drift-detection                # its gate asserts Helm revisions are IDENTICAL across all releases; this plan upgrades 5 releases
  - flux-oci-chart-sources              # re-points chart sources incl. open-webui / app-template releases
  - flux-reconciler-impersonation       # changes WHO applies every Kustomization/HelmRelease this plan relies on
  - talos-linux-1.14.4                  # node reboots (sun 2026-11-01)
  - coredns-1.48.1                      # a CoreDNS roll while consumers re-resolve their redis Service names confounds the reconnect gates
  - longhorn-1.13.0                     # sun 2026-11-15 — two Longhorn PVCs are remounted here; never stack on a storage upgrade
  - authentik-2026.8.5                  # SSO login for Nextcloud/Paperless/Immich/Sure/open-webui used by the attended checks
  - authentik-web-max-requests          # same
  - envoy-proxy-config-distroless-v1.40.0  # public edge roll hides app reachability gates
  - envoy-proxy-config-distroless-v1.39.4  # same
  - etcd-timeouts-5000-500              # control-plane timing change under 8 rolling Deployments
  # Dropped 2026-10-25 as executed/retired (no longer open plans): flux-distribution-2.9.6, cilium-1.20.4. If another CNI or Flux-controller
  # plan is filed, re-add it (a CNI roll drops every client-server connection; a controller roll confounds the GitOps legs).
  # Dropped 2026-10-24 as dead refs: flux-fleet-0.60.0, app-template-5.2.1, nextcloud-fleet-35.0.1,
  # chart-patches-coredns-reloader-blackbox (plans no longer exist / executed); no open kube-prometheus-stack plan.
  # If a kube-prometheus-stack-* plan reappears, add it (§4 reads Prometheus).
exclusive: false
security_ref: F-6cfc5079                # related: the open-webui image's accepted security finding (detail on the record).
capability_change: false                # same-behaviour patch bump on all 8; nextcloud-redis auth/config is already live
                                        # and unchanged by this plan; open-webui app not touched any more.
autonomy_override: human-gated          # nextcloud-redis leg logs every user out (policy rule
                                        # *nextcloud-redis*: "ATTENDED low-traffic slot"); the
                                        # sure-worker restart needs a human reading §4 leg-6 gate.
rollback_class: git-revert              # one commit per leg, each reverts cleanly: RDB/AOF format is
                                        # unchanged (RDB_VERSION 15 in both tags); no schema/app migration in this plan.
backup_gate: "Completed Longhorn backup < 26h for tube-archivist-redis-data and the redis-data volume (§2 g); PLUS an in-pod/local copy of tube-archivist dump.rdb taken in §3 leg 4 immediately before that leg (byte count compared)."
finding_refs: [F-d2bb762b, F-8c50c463, F-625d3a3f, F-c637a09a, F-3fcdca7b, F-3a75c9aa, F-2e326f86, F-e8a41b1b, F-db500cce]
                                        # the 8 per-consumer redis image findings. F-31c19a7f (open-webui chart 16.6.0)
                                        # is NO LONGER answered here: the chart is already 17.0.0 (live 2026-10-24).
status: superseded                      # 2026-10-27 (sweep 3f978ad9): redis 8.10.3 published 2026-10-26 (trips §2 c
                                        # "8.10.3 -> 200 = refresh"); scope also shrank 8 -> 3 (other consumers now Step-0 lane).
superseded_by: redis-fleet-8.10.3
review: ready-for-go@2026-10-25   # plan-reviewer 2026-10-25 delta re-review: premises PASS, gates verified
                # No operator GO recorded; HUMAN-GATED.
window: null                            # was sun-attended:2026-11-29; the slot is carried by redis-fleet-8.10.3
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md               # read-only relevance: two Longhorn PVCs remounted, none deleted
  - docs/sops/paperless.md
  - docs/sops/immich.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-09-27"
replanned: "2026-10-24"
premises:
  # Read-verb only. Each was run 2026-10-24 and returned the expected value.
  - id: databases-images-current
    why: >-
      `current:` claims 8.10.1-alpine on both databases redis Deployments. If the
      nightly lane or a hand edit moved either, that leg is a no-op and §3's sed
      for it matches nothing — drop the leg, do not force it. A value of 8.10.2
      means someone already did it.
    run: kubectl get deploy -n databases redis superset-redis-official -o jsonpath='{.items[*].spec.template.spec.containers[0].image}'
    expect_exact: redis:8.10.1-alpine redis:8.10.1-alpine
  - id: office-images-current
    why: Same, for the three office redis Deployments (order nextcloud, paperless, sure).
    run: kubectl get deploy -n office nextcloud-redis paperless-redis sure-redis -o jsonpath='{.items[*].spec.template.spec.containers[0].image}'
    expect_exact: redis:8.10.1-alpine redis:8.10.1-alpine redis:8.10.1-alpine
  - id: media-download-ai-images-current
    why: Same, for immich-redis, tube-archivist-redis and the open-webui sidecar.
    run: kubectl get deploy -A -o jsonpath='{range .items[?(@.metadata.name=="immich-redis")]}{.spec.template.spec.containers[0].image}{" "}{end}{range .items[?(@.metadata.name=="tube-archivist-redis")]}{.spec.template.spec.containers[0].image}{" "}{end}{range .items[?(@.metadata.name=="open-webui-redis")]}{.spec.template.spec.containers[0].image}{end}'
    expect_exact: redis:8.10.1-alpine redis:8.10.1-alpine redis:8.10.1-alpine
  - id: open-webui-app-already-current
    why: >-
      The plan assumes open-webui is ALREADY on v0.12.3 / chart 17.0.0 and that only its
      redis sidecar moves. If the StatefulSet is on anything else, leg 3 would also roll
      the app and the §4 leg-3 "app not restarted" gate is wrong — re-plan.
    run: kubectl get sts -n ai open-webui -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/open-webui/open-webui:v0.12.3
  - id: open-webui-chart-current
    why: Leg 3 must not carry a chart bump; chart 17.0.0 is the live release.
    run: kubectl get hr -n ai open-webui -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: 17.0.0
  - id: databases-redis-is-aof
    why: >-
      databases/redis is the canary BECAUSE it is the one AOF-persistent
      instance (it exercises the new binary loading a persisted file). If
      persistence changed, the leg order and rollback reasoning change.
    run: kubectl get deploy -n databases redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_exact: '["redis-server","--appendonly","yes","--save",""]'
  - id: tube-archivist-redis-default-config-on-pvc
    why: >-
      tube-archivist-redis runs the image's DEFAULT config (RDB snapshots, no
      command override) with /data on a PVC — the only consumer whose contents
      survive a restart. The literal prefix keeps output non-empty; a command
      appearing after `cmd=` means someone changed persistence.
    run: kubectl get deploy -n download tube-archivist-redis -o jsonpath='{"cmd="}{.spec.template.spec.containers[0].command}{" claim="}{.spec.template.spec.volumes[?(@.persistentVolumeClaim)].persistentVolumeClaim.claimName}'
    expect_exact: cmd= claim=tube-archivist-redis-data
  - id: nextcloud-redis-requirepass-wrapper
    why: >-
      Nextcloud was upgraded to 35.0.2 / chart 9.4.1 on 2026-10-23 and nextcloud-redis now
      starts through a wrapper that REFUSES to start without REDIS_PASSWORD and runs
      `--requirepass`. The old plan asserted the plain `redis-server --save "" --appendonly no`
      command; that premise is now false. This premise asserts the wrapper is still the
      live one (the pattern appears only in the new command), so §4 leg 8 may rely on
      REDISCLI_AUTH and on the NOAUTH control.
    run: kubectl get deploy -n office nextcloud-redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_contains: 'exec redis-server --save'
  - id: nextcloud-redis-auth-env-from-secret
    why: >-
      The password comes from secret/nextcloud-config key redis-password (both REDIS_PASSWORD
      and REDISCLI_AUTH). The §4 leg-8 round trip and the NOAUTH control depend on this. Names
      only; the secret value is never printed.
    run: kubectl get deploy -n office nextcloud-redis -o jsonpath='{"secret="}{.spec.template.spec.containers[0].env[*].valueFrom.secretKeyRef.name}{" key="}{.spec.template.spec.containers[0].env[*].valueFrom.secretKeyRef.key}'
    expect_exact: 'secret=nextcloud-config nextcloud-config key=redis-password redis-password'
  - id: sure-redis-non-persistent
    why: >-
      The sure-worker restart in §3 leg 6 is required precisely because this
      redis loses everything (including the sidekiq-cron schedule) on restart.
      If persistence were turned on, the restart becomes unnecessary.
    run: kubectl get deploy -n office sure-redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_exact: '["redis-server","--save","","--appendonly","no"]'
  - id: sure-worker-surge-zero
    why: >-
      §3 leg 6 rollout-restarts sure-worker. maxSurge 0 guarantees no second
      Sidekiq process registers the cron schedule concurrently and that its RWO
      `uploads` volume is not double-attached.
    run: kubectl get deploy -n office sure-worker -o jsonpath='{.spec.strategy.rollingUpdate.maxSurge}'
    expect_exact: "0"
  - id: tube-archivist-redis-backed-up
    why: The one redis whose contents are persistent. Freshness asserted in §2 g.
    run: kubectl get backups.longhorn.io -n storage -o jsonpath='{.items[?(@.status.volumeName=="tube-archivist-redis-data")].status.state}'
    expect_contains: Completed   # existence only; freshness is the §2 g longhorn-backup-age.py gate
  - id: manifest-pins-current
    why: >-
      §3's seds are anchored on these exact literals; each file must hold exactly
      one line ENDING in 8.10.1-alpine (the open-webui comment line ends in
      "is", so it is not counted; its own sed handles it). A count of 0 means
      that leg's commit would be empty; 2 means a second pin the sed would also
      rewrite.
    run: grep -c "8\.10\.1-alpine$" kubernetes/apps/databases/redis/app/helmrelease.yaml kubernetes/apps/databases/superset/app/redis-deployment.yaml kubernetes/apps/download/tube-archivist/app/redis-helmrelease.yaml kubernetes/apps/media/immich/app/redis-helmrelease.yaml kubernetes/apps/office/nextcloud/app/redis-deployment.yaml kubernetes/apps/office/paperless-ngx/app/redis-deployment.yaml kubernetes/apps/office/sure/app/redis-helmrelease.yaml kubernetes/apps/ai/open-webui/app/helmrelease.yaml
    expect_matches: '(?s)^(?:\S+:1\n?){8}$'
---

> **SUPERSEDED 2026-10-27 by [`redis-fleet-8.10.3`](redis-fleet-8.10.3.md)** (target 8.10.3-alpine, 3 held consumers). Do not execute this file.

# redis fleet 8.10.1-alpine → 8.10.2-alpine (8 consumers; re-planned 2026-10-24)

## 1. Summary & why held

### 1.0 Re-plan delta (2026-10-24)

The Saturday attended window of 2026-10-24 deferred this plan because two premises
had moved. Both were re-measured live:

1. **open-webui is already on `v0.12.3` (chart 17.0.0, Helm release v58)**, started
   2026-10-22. The old lockstep (app 0.11.3 -> 0.11.4 + chart 16.5.0 -> 16.6.0) is
   void; the app and chart legs, the sqlite pre-copy and the alembic-head
   rollback branch are REMOVED. Leg 3 now changes only the chart-rendered redis
   sidecar tag (`redis.image.tag`), with the app pod expected NOT to restart.
   The image tag form is now `v0.12.3` (leading `v`).
2. **nextcloud-redis now enforces a password** (Nextcloud 35.0.2 / chart 9.4.1,
   2026-10-23; the manifest was already hardened by `5601933a`). Live: the
   container command is an `sh -c` wrapper that exits if `REDIS_PASSWORD` is empty and
   runs `redis-server --save "" --appendonly no --requirepass "$REDIS_PASSWORD"`; both
   `REDIS_PASSWORD` and `REDISCLI_AUTH` come from `secret/nextcloud-config` key
   `redis-password`; a NetworkPolicy admits only the Nextcloud app/cronjob pods and
   `nextcloud-notify-push`; notify-push now reads `REDIS_URL`. The image swap does not
   touch the secret, wrapper or policy, so the password path survives the roll by
   construction; §4 leg 8 proves it (round trip with auth AND an unauthenticated
   `NOAUTH` control).

Also re-measured: **the target is still right.** `redis:8.10.2-alpine` is the newest
tag (`8.10.3`, `8.11.0`, `8.12.0` -> 404; upstream `gh release list`: 8.10.2 is
Latest, published 2026-09-17, the only newer patch after 8.10.1). The Docker Hub tag was
RE-PUSHED on 2026-10-22T15:05Z (index digest now
`sha256:0bf6577d7774e592b29d093e3ac9390eb91e13d72c21e506afce736de5e0eeb0`; the
2026-09-27 digest was `3811...`): a rebuild of the same upstream release. §2 b re-checks
cooldown and prints the digest so a later re-push is visible.

### 1.1 What moves

Eight Docker Hub `redis` instances move `8.10.1-alpine -> 8.10.2-alpine`, one commit
per consumer, in blast-radius order (§3). The eighth, open-webui's chart-rendered
websocket redis, is a one-line values change in the open-webui HelmRelease. (Because it
is the same HelmRelease, the Helm upgrade re-renders the open-webui StatefulSet from
identical values, so no pod-template change is expected; §4 asserts it.)
`affine-redis` is already on 8.10.2 (live, `office/affine-redis`) and is the fleet's
in-cluster proof of the tag.

### 1.2 Why held — the redis legs

Seven legs were held by **G3: "could not verify the release notes"**. That is a
resolver gap, not a signal (`IMAGE_RELEASE_NOTES_PROJECTS` now maps `redis`; upstream
tag is bare `8.10.2`, ours is `-alpine`). Read by hand from `redis/redis`
(`gh release view 8.10.2 -R redis/redis`, update urgency SECURITY):

- **6 commits** vs 8.10.1. No `rdb.c`, `aof.c` or `rdb.h` change; `RDB_VERSION` is `15`
  in both tags, so the AOF of databases/redis and the dump.rdb of tube-archivist-redis
  load unchanged forward AND backward (the rollback property this plan relies on).
- Bundled RediSearch/TimeSeries modules v8.10.0 -> v8.10.1; no instance here holds
  module data.
- One new config option, `cluster-bus-port-protected-mode` (default `no`) — cluster
  mode only; none of these run cluster mode. No default changes for a single-node server.
- Security-class items are in ACL/transaction handling, the cluster bus and the modules;
  item-level detail stays upstream (`docs/sops/vulnerability-disclosure.md`). None changes
  the RESP protocol or a command's reply for the default user; three consumers use
  `requirepass` (superset, paperless, nextcloud), none define ACL users.

The eighth, **nextcloud-redis**, is also held by its own deny rule (`*nextcloud-redis*`):
*any restart signs out every logged-in Nextcloud user and drops held locks ... schedule
an ATTENDED low-traffic slot*. Honoured here (leg 8, last, attended, announced).

### 1.3 open-webui leg (reduced)

Only the sidecar changes. The sidecar runs the image defaults (no `command`, no volume,
RDB snapshots to the container filesystem) and holds 4 keys of websocket/pubsub state.
Upstream evidence for in-process re-attach (open-webui `v0.12.3`, `backend/open_webui/socket/main.py`, read 2026-10-25): the websocket
manager is `socketio.AsyncRedisManager` (line 116), and `redis_event_listener()` (line ~1227) runs `pubsub.subscribe`/`listen()` inside a `while True` that
catches every exception, logs `Redis event listener failed. Retrying.`, sleeps `REDIS_PUBSUB_RECONNECT_INTERVAL` and doubles it up to
`REDIS_PUBSUB_MAX_RECONNECT_INTERVAL` (both imported at lines 49-50): a redis restart is designed to be survived, with exponential back-off. That is
source reading, not a measurement on this cluster, so §4 leg 3 still measures it (client count returns to the
baseline) and gives the fallback (`kubectl rollout restart sts/open-webui -n ai`: image
and DB unchanged, so safe, but it ends the user's sessions on that pod briefly).

### 1.4 The trap this plan exists to catch — Sure's cron schedule

`sure-redis` is non-persistent. Sure's recurring jobs (bank sync, market data,
cleanups — 11 entries, `SCARD cron_jobs:default` = 11 on 2026-09-27) live ONLY
in that redis, and are written there ONLY at Sidekiq startup:
sidekiq-cron 2.3.0 (`Gemfile.lock` of the Sure fork),
`lib/sidekiq/cron/schedule_loader.rb`:

```ruby
Sidekiq.configure_server do |config|
  config.on(:startup) do
    schedule_loader = Sidekiq::Cron::ScheduleLoader.new
    ...
    schedule_loader.load_schedule
```

and the poller only reads what is in redis (`Sidekiq::Cron::Job.all('*')` in
`poller.rb#enqueue`). Sure's own `AutoSyncScheduler.sync!` is likewise an
`on(:startup)` hook (`config/initializers/sidekiq.rb`). So swapping the redis
under a running `sure-worker` leaves a perfectly healthy worker with an **empty
schedule** — no error, no alert, pods Ready — until the worker next restarts.
Leg 6 therefore restarts `sure-worker` after the new redis is Ready, and §4
asserts the schedule count comes back to 11. (Repo correction in §6: the
unattended lane must never apply a sure-redis bump without that restart.)

### 1.5 Consumer classification (re-measured 2026-10-24, `redis-cli info` in each pod; all on redis_version 8.10.1)

| Leg | Instance | Persistence | Holds | Consumers (CLIENT LIST → pod) | Restart cost |
|---|---|---|---|---|---|
| 1 | databases/redis | **AOF on PVC** (`redis-data`) | nothing (0 keys, 1 client = our own cli, 2026-10-24) | none | none — canary for the persisted-load path |
| 2 | databases/superset-redis-official | none | celery broker + results (1444 keys, `requirepass`) | superset-worker, superset-celerybeat | in-flight celery results lost; worker reconnect in-process **measured** (worker started 08:22, redis restarted 08:49 on 2026-09-27, `inspect ping` → pong now) |
| 3 | ai/open-webui-redis (sidecar only) | RDB defaults, **no volume** (container fs) | websocket/pubsub + locks (4 keys) | open-webui-0 (5 connections) | brief pubsub gap; app NOT rolled (§1.3) |
| 4 | download/tube-archivist-redis | **RDB on PVC** (`tube-archivist-redis-data`) | celery broker + **durable app state** (`ta:cookie`, no TTL; 65 keys) | tube-archivist (worker + beat) | none if dump.rdb reloads; beat uses DatabaseScheduler (schedule in DB, not redis) |
| 5 | media/immich-redis | none | BullMQ queues (60 keys) | immich-server (19 blocking workers) | queued/active jobs dropped (whether Immich re-queues them is NOT verified from source here — the §4 gate is only that its workers re-attach; a half-done thumbnail/metadata job may need a manual "missing" re-run from the Immich admin Jobs page) |
| 6 | office/sure-redis | none | sidekiq queues + **cron schedule** + Rails cache | sure-worker, sure-web | **cron schedule lost → worker restart required (§1.4)** |
| 7 | office/paperless-redis | none (`requirepass`) | celery broker + channels layer | paperless-ngx | an in-flight consume task is lost → drain first (§2) |
| 8 | office/nextcloud-redis | none, **`requirepass` from secret/nextcloud-config** | PHP sessions, file locks, distributed cache (682 keys) | nextcloud, nextcloud-notify-push, nextcloud-cron Jobs (NetworkPolicy-restricted) | **every logged-in user signed out**, held locks dropped |

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) premises (read-only, fail closed)
.venv/bin/python3 runbooks/plan-premises.py redis-fleet-8.10.2

# b) G5 cooldown still satisfied (a re-push resets it). PASS prints AGE_OK;
#    TOO_NEW or FETCH_FAILED is a STOP. The digest is printed so a re-push is visible.
curl -s https://hub.docker.com/v2/repositories/library/redis/tags/8.10.2-alpine | python3 -c '
import sys, json, datetime as d
try: t = json.load(sys.stdin)["last_updated"]
except Exception: print("FETCH_FAILED redis"); sys.exit(1)
a = (d.datetime.now(d.timezone.utc) - d.datetime.fromisoformat(t.replace("Z","+00:00"))).total_seconds()/3600
print(("AGE_OK" if a >= 48 else "TOO_NEW"), "redis", round(a,1), "h", t); sys.exit(0 if a >= 48 else 1)'
curl -s https://hub.docker.com/v2/repositories/library/redis/tags/8.10.2-alpine | python3 -c 'import sys,json;print("DIGEST", json.load(sys.stdin)["digest"])'
#    Expected 2026-10-24: last_updated 2026-10-22T15:05Z, DIGEST sha256:0bf6577d...e0eeb0.
#    A DIFFERENT last_updated/DIGEST means the tag was re-pushed again: re-read the notes
#    and re-check the cooldown before proceeding. AGE_OK needs >= 48 h since last_updated.

# c) targets resolvable, nothing newer superseding them.
#    EXPECT EXACTLY: 8.10.2-alpine -> 200, 8.10.3-alpine -> 404
for t in 8.10.2-alpine 8.10.3-alpine; do
  curl -s -o /dev/null -w "$t -> %{http_code}\n" https://hub.docker.com/v2/repositories/library/redis/tags/$t
done
#    FAILS as: 8.10.2-alpine -> 404 (tag withdrawn) or 8.10.3-alpine -> 200 (a newer patch
#    exists: refresh this plan, do not apply a superseded target).

# d) Flux sane, nothing in flight in these namespaces
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
#    PASS: header line only for both (or unrelated rows you have explained).

# e) no other plan in this window touches these apps / asserts Helm revisions
python3 runbooks/maintenance-plan.py --open | grep -iE 'redis|nextcloud|paperless|immich|superset|sure|tube|open-webui|helm-drift|flux-|cilium|talos|authentik|coredns|longhorn|envoy' || true
#    PASS: no other plan scheduled for this slot. Any hit scheduled for TODAY is a STOP (see conflicts_with).

# f) BASELINE — record every number; §4 compares against them.
#    (values measured 2026-10-24 in brackets; auth'd instances authenticate via the
#    REDISCLI_AUTH env var already present in their containers)
for x in databases/redis databases/superset-redis-official download/tube-archivist-redis \
         media/immich-redis office/nextcloud-redis office/paperless-redis office/sure-redis ai/open-webui-redis; do
  ns=${x%/*}; d=${x#*/}
  echo "## $x $(kubectl exec -n $ns deploy/$d -- sh -c 'redis-cli info server | grep ^redis_version; redis-cli info clients | grep ^connected_clients; redis-cli info keyspace | grep ^db0' | tr '\r\n' '  ')"
done
#    [redis 1 client/no db0 · superset 15/1444 · tube-archivist 6/65 · immich 81/60 ·
#     nextcloud 14/682 · paperless 10/13 · sure 13/639 · open-webui-redis 6/4]
#    Client counts and key counts drift; they are floors-with-slack, not exact values.
kubectl exec -n office deploy/sure-redis -- redis-cli scard cron_jobs:default          # [11]
kubectl exec -n download deploy/tube-archivist-redis -- redis-cli exists ta:cookie     # [1]
kubectl exec -n media deploy/immich-redis -- sh -c 'redis-cli client list | grep -c "cmd=bzpopmin"'   # [19]
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8080/api/version').read())"   # [{"version":"0.12.3",...}]
kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.startTime}{" restarts="}{.status.containerStatuses[0].restartCount}{"\n"}' | tee /tmp/redis-fleet-owui0   # [2026-10-22T21:15:33Z restarts=0] — §4 leg 3 compares
kubectl exec -n ai deploy/open-webui-redis -- redis-cli client list | grep -c 'addr=10\.'   # [5] app-side connections, baseline for leg 3
# nextcloud-redis: AUTH control BEFORE the roll (so the post-roll NOAUTH result is not first-time evidence)
kubectl exec -n office deploy/nextcloud-redis -- sh -c 'env -u REDISCLI_AUTH redis-cli ping; redis-cli ping'   # [NOAUTH Authentication required. / PONG]

# f2) CONSUMER BASELINE — the "not restarted" criterion of every leg compares against this file.
T0=$(date -u +%s); echo "$T0" > /tmp/redis-fleet-T0; echo "T0=$T0"   # window start, used by the §4 restart control
BASE=/tmp/redis-fleet-consumers-$T0.txt
# Shell state does NOT survive separate tool calls: in every later call run
#   T0=$(cat /tmp/redis-fleet-T0); BASE=/tmp/redis-fleet-consumers-$T0.txt
# and re-define the helper functions (cons_snap, wait_img, v_floor, v_rt, v_cons, leg_commit).
# Failure modes if you forget are loud (command not found / CONSUMERS_CHANGED), never a false green.
cons_snap() {   # prints: ns/name restartCount startTime, one line per consumer pod
  for x in databases/superset-worker databases/superset-celerybeat download/tube-archivist media/immich-server \
           office/paperless-ngx office/nextcloud office/sure-web; do
    ns=${x%/*}; d=${x#*/}
    sel=$(kubectl get deploy -n $ns $d -o json | python3 -c 'import sys,json; print(",".join(f"{k}={v}" for k,v in json.load(sys.stdin)["spec"]["selector"]["matchLabels"].items()))')
    kubectl get pod -n $ns -l "$sel" -o json | python3 -c '
import sys, json
for p in json.load(sys.stdin)["items"]:
    if p["metadata"].get("deletionTimestamp") or p["status"].get("phase") != "Running": continue
    r = sum(c.get("restartCount", 0) for c in p["status"].get("containerStatuses", []))
    print(sys.argv[1] + "/" + p["metadata"]["name"], r, p["status"]["startTime"])' "$ns"
  done
}
cons_snap | tee "$BASE"; [ "$(wc -l < "$BASE" | tr -d ' ')" = 7 ] || { echo "BASELINE_INCOMPLETE"; exit 1; }   # 7 lines expected; an empty baseline would make v_cons pass unchecked

# g) backups fresh (< 26 h) — ground truth is the newest Completed Backup CR
# Shared helper (F-a915dd47): counts the nightly Backup CR even when its status
# never synced (status.volumeName empty), cross-checked against the BackupVolume.
python3 runbooks/longhorn-backup-age.py tube-archivist-redis-data \
  $(kubectl get pvc -n databases redis-data -o jsonpath='{.spec.volumeName}') --max-hours 26 \
  || { echo "ABORT: a volume has no confirmed backup < 26h"; exit 1; }
#    PASS: two FRESH lines (open-webui-20g is no longer touched by this plan). (Daily job: CronJob storage/daily-backup-all-volumes, 03:00.)

# h) drain checks — record; each is re-run immediately before its own leg.
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- celery --app paperless inspect active 2>&1 | tail -5
kubectl exec -n download deploy/tube-archivist -- sh -c 'cd /app && celery -A task inspect active 2>&1 | tail -5'
#    PASS: "- empty -" for each node. A running consume/download task means WAIT, not proceed.

# i) Prometheus reachable for §4 (the controls read it)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -G http://127.0.0.1:9090/api/v1/query --data-urlencode 'query=count(kube_pod_container_status_restarts_total{namespace="office"})' | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print("PROM_OK" if r and float(r[0]["value"][1])>0 else "PROM_EMPTY")'
kill $PF 2>/dev/null
```

Proceed only if (a) all premises PASS, (b) AGE_OK, (c) 200/404, (d) clean,
(f) the pre-roll NOAUTH/PONG pair, (g) FRESH ×2, (i) PROM_OK. For (h), proceed per leg when that leg's
drain check is empty. **Announce** the Nextcloud sign-out before starting
(the policy rule's attended-slot condition).

Optional silence (SOP §4 Step 1), one per namespace, 2 h TTL. Silences affect
only Alertmanager notifications; the §4 alert gates read Prometheus' own
`/api/v1/alerts`, which a silence does not change.

## 3. Steps (GitOps, one commit per leg, in this order)

Order = ascending blast radius, and each leg's §4 gates must PASS before the
next leg starts. Every leg is its own commit so a failure reverts one consumer.

Common commit recipe — each leg below sets `LEG`, `FILE`, `SUBJ` as shell
variables, then runs `leg_commit`. The message goes to a UNIQUE file (shared
worktree). Never paste `<...>` placeholders into zsh — they are redirections.

```bash
cd /Users/mu/code/cberg-home-nextgen
leg_commit() {
  local MSG; MSG=$(mktemp /tmp/redis-fleet-leg$LEG.XXXXXX)
  printf '%s\n\n%s\n' "$SUBJ" "Plan redis-fleet-8.10.2, leg $LEG." > "$MSG"
  git diff -- "$FILE"                  # must be exactly the diff shown for the leg
  git commit --only "$FILE" -F "$MSG" || { echo COMMIT_FAILED; return 1; }
  [ "$(git log -1 --format=%s)" = "$SUBJ" ] || { echo "SUBJECT_MISMATCH — amend before push"; return 1; }
  git show --stat HEAD                 # exactly one file
  git push && rm -f "$MSG"
}
```

Do NOT `flux reconcile` by hand — the webhook applies it. Wait-for-image helper
(zsh-safe; do not name a variable `path` — zsh ties it to `$PATH`):

```bash
wait_img() {   # wait_img <ns> <deploy|sts>/<name> <expected image>
  local ns=$1 obj=$2 want=$3 i
  for i in $(seq 1 30); do
    got=$(kubectl get -n $ns $obj -o jsonpath='{.spec.template.spec.containers[0].image}')
    [ "$got" = "$want" ] && kubectl rollout status -n $ns $obj --timeout=180s && echo "ROLLED $obj" && return 0
    sleep 10
  done
  echo "NOT_ROLLED $obj (spec=$got)"; return 1
}
```

Tag edits below were dry-run on scratch copies of every target file on macOS
(BSD sed) on 2026-09-27; the diff lines shown are that output.

### Leg 1 — databases/redis (canary: AOF-persistent, no consumers)

```bash
sed -i '' 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.1-alpine$/\18.10.2-alpine/' kubernetes/apps/databases/redis/app/helmrelease.yaml
#   -              tag: 8.10.1-alpine
#   +              tag: 8.10.2-alpine
LEG=1 FILE=kubernetes/apps/databases/redis/app/helmrelease.yaml
SUBJ="chore(redis): databases/redis 8.10.1-alpine -> 8.10.2-alpine (plan redis-fleet-8.10.2 leg 1)"
leg_commit
wait_img databases deploy/redis redis:8.10.2-alpine
```
Then §4 leg 1.

### Leg 2 — databases/superset-redis-official

```bash
sed -i '' 's/^\([[:space:]]*image:[[:space:]]*redis:\)8\.10\.1-alpine$/\18.10.2-alpine/' kubernetes/apps/databases/superset/app/redis-deployment.yaml
#   -        image: redis:8.10.1-alpine
#   +        image: redis:8.10.2-alpine
LEG=2 FILE=kubernetes/apps/databases/superset/app/redis-deployment.yaml
SUBJ="chore(superset): redis 8.10.1-alpine -> 8.10.2-alpine (plan redis-fleet-8.10.2 leg 2)"
leg_commit
wait_img databases deploy/superset-redis-official redis:8.10.2-alpine
```

### Leg 3 — ai/open-webui: redis sidecar tag ONLY (chart 17.0.0 and app v0.12.3 untouched)

No sqlite pre-copy and no alembic assertion are needed: the app image and DB are not
touched. Edit (two substitutions, one file; the comment line keeps the file honest):
```bash
sed -i '' -e 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.1-alpine$/\18.10.2-alpine/' \
          -e 's/ 8\.10\.1-alpine is$/ 8.10.2-alpine is/' kubernetes/apps/ai/open-webui/app/helmrelease.yaml
#   -      # only — no persistence, no ACL/auth, no modules. 8.10.1-alpine is
#   +      # only — no persistence, no ACL/auth, no modules. 8.10.2-alpine is
#   -          tag: 8.10.1-alpine
#   +          tag: 8.10.2-alpine
#   (dry-run on a scratch copy, BSD sed, 2026-10-24; `tag: v0.12.3` at the app image is NOT matched)
LEG=3 FILE=kubernetes/apps/ai/open-webui/app/helmrelease.yaml
SUBJ="chore(open-webui): redis sidecar 8.10.1-alpine -> 8.10.2-alpine (plan redis-fleet-8.10.2 leg 3)"
leg_commit
wait_img ai deploy/open-webui-redis redis:8.10.2-alpine
```
(open-webui-redis is `RollingUpdate 25%` — a new pod may briefly coexist with the old;
harmless for an ephemeral pubsub store with no volume.) The Helm release moves from
revision 58 to 59.

### Leg 4 — download/tube-archivist-redis (persistent RDB)

Re-run the TA drain check from §2 h (must be empty). Then copy the snapshot
out (read-only against the pod):
```bash
B=/tmp/ta-dump-$(date +%Y%m%d_%H%M%S).rdb
kubectl exec -n download deploy/tube-archivist-redis -- cat /data/dump.rdb > "$B"
LIVE=$(kubectl exec -n download deploy/tube-archivist-redis -- sh -c 'wc -c < /data/dump.rdb' | tr -d ' ')
echo "live=$LIVE copy=$(wc -c < "$B" | tr -d ' ') file=$B"     # PASS: equal and > 0 (9605 on 2026-09-27)
sed -i '' 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.1-alpine$/\18.10.2-alpine/' kubernetes/apps/download/tube-archivist/app/redis-helmrelease.yaml
#   -              tag: 8.10.1-alpine
#   +              tag: 8.10.2-alpine
LEG=4 FILE=kubernetes/apps/download/tube-archivist/app/redis-helmrelease.yaml
SUBJ="chore(tube-archivist): redis 8.10.1-alpine -> 8.10.2-alpine (plan redis-fleet-8.10.2 leg 4)"
leg_commit
wait_img download deploy/tube-archivist-redis redis:8.10.2-alpine
```
The `Recreate` sends SIGTERM; with `save` configured redis writes a final
snapshot on shutdown and the new pod loads it.

### Leg 5 — media/immich-redis

```bash
sed -i '' 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.1-alpine$/\18.10.2-alpine/' kubernetes/apps/media/immich/app/redis-helmrelease.yaml
#   -              tag: 8.10.1-alpine
#   +              tag: 8.10.2-alpine
LEG=5 FILE=kubernetes/apps/media/immich/app/redis-helmrelease.yaml
SUBJ="chore(immich): redis 8.10.1-alpine -> 8.10.2-alpine (plan redis-fleet-8.10.2 leg 5)"
leg_commit
wait_img media deploy/immich-redis redis:8.10.2-alpine
```

### Leg 6 — office/sure-redis, THEN restart sure-worker

```bash
sed -i '' 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.1-alpine$/\18.10.2-alpine/' kubernetes/apps/office/sure/app/redis-helmrelease.yaml
#   -              tag: 8.10.1-alpine
#   +              tag: 8.10.2-alpine
LEG=6 FILE=kubernetes/apps/office/sure/app/redis-helmrelease.yaml
SUBJ="chore(sure): redis 8.10.1-alpine -> 8.10.2-alpine (plan redis-fleet-8.10.2 leg 6)"
leg_commit
wait_img office deploy/sure-redis redis:8.10.2-alpine

# The schedule is now EMPTY (§1.4). Confirm that is what you see — this is the
# positive control for the gate below:
kubectl exec -n office deploy/sure-redis -- redis-cli scard cron_jobs:default     # expect 0
# Re-register it: restart the worker ONCE, only after the new redis is Ready.
# (The one imperative step in this plan: there is no GitOps way to order a
# restart AFTER another Deployment's rollout; same pattern as
# docs/sops/secret-rotation.md consumer roll. maxSurge 0 — premise sure-worker-surge-zero.)
kubectl rollout restart deploy/sure-worker -n office
kubectl rollout status deploy/sure-worker -n office --timeout=300s
```

### Leg 7 — office/paperless-redis

Re-run the paperless drain check from §2 h (must be `- empty -`); also confirm
the broker queue is empty:
```bash
kubectl exec -n office deploy/paperless-redis -- redis-cli llen celery     # PASS: 0
sed -i '' 's/^\([[:space:]]*image:[[:space:]]*redis:\)8\.10\.1-alpine$/\18.10.2-alpine/' kubernetes/apps/office/paperless-ngx/app/redis-deployment.yaml
#   -        image: redis:8.10.1-alpine
#   +        image: redis:8.10.2-alpine
LEG=7 FILE=kubernetes/apps/office/paperless-ngx/app/redis-deployment.yaml
SUBJ="chore(paperless): redis 8.10.1-alpine -> 8.10.2-alpine (plan redis-fleet-8.10.2 leg 7)"
leg_commit
wait_img office deploy/paperless-redis redis:8.10.2-alpine
```

### Leg 8 — office/nextcloud-redis (last; signs every user out)

Announce first. The password, wrapper and NetworkPolicy are NOT edited: only the image
line changes, so `requirepass` is re-applied by the same wrapper from the same
`secret/nextcloud-config` key (never print it). Pick a moment right AFTER a `nextcloud-cron` Job completed
(schedule `*/5`), so the next tick lands on the new redis:
```bash
kubectl get jobs -n office --sort-by=.metadata.creationTimestamp | grep nextcloud-cron | tail -2
sed -i '' 's/^\([[:space:]]*image:[[:space:]]*redis:\)8\.10\.1-alpine$/\18.10.2-alpine/' kubernetes/apps/office/nextcloud/app/redis-deployment.yaml
#   -        image: redis:8.10.1-alpine
#   +        image: redis:8.10.2-alpine
LEG=8 FILE=kubernetes/apps/office/nextcloud/app/redis-deployment.yaml
SUBJ="chore(nextcloud): redis 8.10.1-alpine -> 8.10.2-alpine (plan redis-fleet-8.10.2 leg 8)"
leg_commit
wait_img office deploy/nextcloud-redis redis:8.10.2-alpine
```

## 4. Verification (per leg, before the next leg starts)

**Floor for every leg** (shape only — proves the new binary runs, nothing more):
```bash
v_floor() {   # v_floor <ns> <deploy> — selects pods by the Deployment's OWN selector
  local ns=$1 d=$2 sel             # (a name-prefix match would also catch redisinsight-* for "redis")
  sel=$(kubectl get deploy -n $ns $d -o json | python3 -c 'import sys,json; print(",".join(f"{k}={v}" for k,v in json.load(sys.stdin)["spec"]["selector"]["matchLabels"].items()))')
  kubectl get pod -n $ns -l "$sel" -o json | python3 -c '
import sys, json
ps = [p for p in json.load(sys.stdin)["items"]
      if p["status"].get("phase") == "Running" and not p["metadata"].get("deletionTimestamp")]
imgs = sorted({c["image"] for p in ps for c in p["status"].get("containerStatuses", [])})
print("PODS", len(ps), imgs)
ok = len(ps) == 1 and imgs == ["docker.io/library/redis:8.10.2-alpine"]
print("FLOOR_OK" if ok else "FLOOR_FAIL"); sys.exit(0 if ok else 1)' \
  && kubectl exec -n $ns deploy/$d -- redis-cli info server | grep -i '^redis_version'
}
# PASS: "PODS 1 ['docker.io/library/redis:8.10.2-alpine']", FLOOR_OK, "redis_version:8.10.2".
# FAILS as: PODS 2 (old pod still serving), an 8.10.1 image (the live status
# form is docker.io/library/redis:8.10.1-alpine, measured 2026-09-27), or redis_version:8.10.1.
```

Consumers NOT restarted (every leg; compares against the §2 f2 baseline file).
PASS prints `CONSUMERS_UNCHANGED`. FAILS as `CONSUMERS_CHANGED` with the diff
lines: a recreated pod (new name/startTime) or a raised restartCount.
sure-worker and open-webui-0 are deliberately NOT in the set (both are
restarted on purpose); every pod that IS in it must be unchanged after every
leg:
```bash
v_cons() { cons_snap > /tmp/redis-fleet-consumers-now.txt; if diff "$BASE" /tmp/redis-fleet-consumers-now.txt; then echo CONSUMERS_UNCHANGED; else echo CONSUMERS_CHANGED; fi; }
```
Measured non-zero control: `diff` of two snapshots across the 2026-09-27
node roll would differ on every line (all seven consumers carry an
08:22–08:49Z startTime from that roll), so the check is not structurally blind.
If immich-server is restarted deliberately under leg 5's fallback, record that
and re-baseline (`cons_snap > "$BASE"`) before leg 6.

Round-trip on every instance (scratch db 15, 60 s TTL, deleted after). FAILS as
`(nil)` / `NOAUTH` / connection refused instead of `ok`:
```bash
v_rt() { kubectl exec -n $1 deploy/$2 -- sh -c 'redis-cli -n 15 set __plan_verify ok EX 60 >/dev/null; redis-cli -n 15 get __plan_verify; redis-cli -n 15 del __plan_verify >/dev/null'; }
```
(superset and paperless carry `REDISCLI_AUTH` in the container env, so the same
command authenticates there.)

### CONTENTS ASSERTIONS — per consumer

`PONG` and Ready are what an EMPTY redis nobody talks to also shows. Each leg's
contents gate is the consumer's own state reappearing in the new server; each
names what it prints when it fails.

**Leg 1 — databases/redis.**
`v_floor databases redis; v_rt databases redis`, then
CONTENTS ASSERTION: the AOF was loaded and is still being written — measured by
```bash
kubectl exec -n databases deploy/redis -- sh -c 'redis-cli info persistence | grep -E "^(aof_enabled|loading|aof_last_write_status|aof_last_bgrewrite_status):"; ls /data/appendonlydir'
```
PASS: `aof_enabled:1`, `loading:0`, both statuses `ok`, and
`appendonly.aof.manifest` present. FAILS as `aof_enabled:0` (config lost),
`err` status, or an empty dir (AOF not on the PVC any more). No consumer to
check: CLIENT LIST showed none. The AOF is empty (0 keys), so this leg proves the
AOF LOAD PATH and config survive, not data survival — leg 4 (tube-archivist,
65 keys incl. a durable one) is the persisted-DATA proof.

**Leg 2 — superset.** `v_floor databases superset-redis-official; v_rt databases superset-redis-official`, then
CONTENTS ASSERTION: the celery worker reconnected in-process and re-declared its queue —
```bash
kubectl exec -n databases deploy/superset-worker -c superset -- celery --app=superset.tasks.celery_app:app inspect ping 2>&1 | grep -c pong   # PASS: >= 1
kubectl exec -n databases deploy/superset-redis-official -- redis-cli exists _kombu.binding.celery                        # PASS: 1
kubectl exec -n databases deploy/superset-redis-official -- redis-cli info clients | grep ^connected_clients             # PASS: >= 8 [14]
```
FAILS as: `inspect ping` printing `Error: No nodes replied within time
constraint` (0 pong), `exists` → 0 (worker not bound to this broker), clients
1–2. Then `v_cons` → `CONSUMERS_UNCHANGED` (run it at the end of EVERY leg).

**Leg 3 — open-webui (sidecar only).** `v_floor ai open-webui-redis; v_rt ai open-webui-redis`, then
```bash
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8080/api/version').read())"
#   PASS: {"version":"0.12.3",...}. FAILS as a connection error / any other version (app rolled to something else).
kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.startTime}{" restarts="}{.status.containerStatuses[0].restartCount}{"\n"}' | diff - /tmp/redis-fleet-owui0 && echo OWUI_APP_UNCHANGED
#   PASS: OWUI_APP_UNCHANGED (the HR upgrade re-rendered identical StatefulSet values). FAILS as a
#   diff: the app pod was recreated — acceptable only if /api/version above still says 0.12.3
#   (record it); a crash/restart-count increase is a FAIL.
for i in $(seq 1 12); do
  C=$(kubectl exec -n ai deploy/open-webui-redis -- redis-cli client list | grep -c 'addr=10\.')
  echo "t=$((i*10))s app_connections=$C"; [ "$C" -ge 3 ] && { echo OWUI_REATTACHED; break; }; sleep 10
done; [ "$C" -ge 3 ] || echo OWUI_NOT_REATTACHED
#   PASS: OWUI_REATTACHED within 2 min (baseline 5 app connections; floor 3). FAILS as
#   OWUI_NOT_REATTACHED / app_connections=0: the app did not reconnect in-process ->
#   `kubectl rollout restart sts/open-webui -n ai` once (image/DB unchanged), re-run this loop;
#   still failing -> §5 leg 3.
```
CONTENTS ASSERTION: the app serves real data over the websocket -> redis path — attended:
sign in, open an existing chat (its history renders; an empty chat list for an existing
user is a FAIL), send one message to an Ollama model and receive a streamed reply.

**Leg 4 — tube-archivist.** `v_floor download tube-archivist-redis; v_rt download tube-archivist-redis`, then
CONTENTS ASSERTION: the persisted state came back —
```bash
kubectl exec -n download deploy/tube-archivist-redis -- sh -c 'redis-cli exists ta:cookie; redis-cli dbsize; redis-cli info persistence | grep -E "^(loading|rdb_last_bgsave_status):"'
#   PASS: exists=1, dbsize >= 55 [65 on the 2026-09-27/10-24 baseline, 66 on 2026-10-25], loading:0, rdb_last_bgsave_status:ok
#   FAILS as exists=0 / dbsize a handful (~5-10) of fresh celery keys: dump.rdb was NOT loaded -> §5 leg-4 restore.
kubectl exec -n download deploy/tube-archivist -- sh -c 'cd /app && celery -A task inspect ping 2>&1' | grep -c pong   # PASS: >= 1
```

**Leg 5 — immich.** `v_floor media immich-redis; v_rt media immich-redis`, then
CONTENTS ASSERTION: BullMQ workers re-attached to the new server — poll up to 3 min:
```bash
for i in $(seq 1 18); do
  W=$(kubectl exec -n media deploy/immich-redis -- sh -c 'redis-cli client list | grep -c "cmd=bzpopmin"')
  S=$(kubectl exec -n media deploy/immich-redis -- sh -c 'redis-cli --scan --pattern "immich_bull:*:stalled-check" | wc -l' | tr -d ' ')
  echo "t=$((i*10))s blocking_workers=$W stalled_check_keys=$S"; [ "$W" -ge 15 ] && [ "$S" -ge 10 ] && { echo IMMICH_GATE_PASS; break; }; sleep 10
done
[ "$W" -ge 15 ] && [ "$S" -ge 10 ] || echo IMMICH_GATE_FAIL
#   (stalled-check keys carry a ~30 s TTL; single samples 7 s apart read 6..19 on
#   2026-09-27 — hence a poll with a floor, not one reading.)
#   PASS: workers >= 15 [19] and stalled-check keys >= 10 [18].
#   FAILS as workers 0 (ioredis did not reconnect) -> restart immich-server ONCE
#   (`kubectl rollout restart deploy/immich-server -n media`), re-run; still failing -> §5.
```
Also `curl` `/api/server/ping` via `kubectl port-forward -n media svc/immich-server 12283:2283` → `{"res":"pong"}`.

**Leg 6 — sure.** `v_floor office sure-redis; v_rt office sure-redis`, then
CONTENTS ASSERTION: the cron schedule is re-registered and a worker heartbeats —
```bash
kubectl exec -n office deploy/sure-redis -- redis-cli scard cron_jobs:default    # PASS: 11 (baseline §2 f). FAILS as 0: the worker restart did not happen / did not load the schedule
kubectl exec -n office deploy/sure-redis -- redis-cli scard processes            # PASS: >= 1 (Sidekiq heartbeat). FAILS as 0
kubectl exec -n office deploy/sure-redis -- redis-cli exists cron_job:default:sync_all_accounts   # PASS: 1 (AutoSyncScheduler on(:startup))
kubectl port-forward -n office svc/sure 18085:80 >/dev/null 2>&1 & PF=$!; sleep 5
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18085/up                # PASS: 200
kill $PF 2>/dev/null
```
The positive control for the 11 is the `0` printed in §3 leg 6 before the
restart; if that read 11 instead of 0, stop and find out why before trusting
the gate.

**Leg 7 — paperless.** `v_floor office paperless-redis; v_rt office paperless-redis`, then
CONTENTS ASSERTION: the consumer is bound to the new broker —
```bash
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- celery --app paperless inspect ping 2>&1 | grep -c pong   # PASS: >= 1
kubectl exec -n office deploy/paperless-redis -- redis-cli exists _kombu.binding.celery                                  # PASS: 1
```
Attended: drop one test PDF into the consume path per `docs/sops/paperless.md`
(or re-run a pending one) and confirm it becomes a document — the end-to-end
job round-trip through this broker. `inspect ping` alone does not prove a task
is delivered.

**Leg 8 — nextcloud.** `v_floor office nextcloud-redis; v_rt office nextcloud-redis`
(`v_rt` authenticates through the container's `REDISCLI_AUTH`, so `ok` proves the
password in the secret matches the one the server enforces), then the AUTH CONTROL pair:
```bash
kubectl exec -n office deploy/nextcloud-redis -- sh -c 'env -u REDISCLI_AUTH redis-cli ping'
#   PASS: "NOAUTH Authentication required." (the password requirement survived the swap).
#   FAILS as PONG: the server came up unauthenticated (wrapper/args lost) — STOP, §5 leg 8.
#   Positive control: the same command printed NOAUTH on the 8.10.1 pod in §2 f.
kubectl exec -n office deploy/nextcloud-redis -- redis-cli ping    # PASS: PONG (auth'd). FAILS as NOAUTH: password mismatch with secret/nextcloud-config.
#   (A wrapper that refused to start for an empty REDIS_PASSWORD leaves the pod CrashLooping, which wait_img/v_floor already
#   fail on; the former separate log grep for it is dropped as redundant.)
```
Notify-push: the absence grep is paired with a POSITIVE signal. Its logs are normally silent (0 lines in 24 h, measured 2026-10-25), so a
clean log alone proves nothing; the positive signal is that its pod IP is a connected client of the NEW redis. Run in ONE call (shell
variables do not survive separate calls):
```bash
SINCE=$(kubectl get pod -n office -l app=nextcloud-redis -o jsonpath='{.items[0].status.startTime}')   # new redis pod start = swap time
NPIP=$(kubectl get pod -n office -l app=nextcloud-notify-push -o jsonpath='{.items[0].status.podIP}')
echo "since=$SINCE notify-push-ip=$NPIP"
for i in $(seq 1 18); do
  C=$(kubectl exec -n office deploy/nextcloud-redis -- redis-cli client list | grep -c "addr=$NPIP:")
  echo "t=$((i*10))s notify_push_clients=$C"; [ "$C" -ge 1 ] && { echo NOTIFY_PUSH_CONNECTED; break; }; sleep 10
done; [ "$C" -ge 1 ] || echo NOTIFY_PUSH_NOT_CONNECTED
kubectl logs -n office deploy/nextcloud-notify-push --since-time="$SINCE" | grep -ciE 'NOAUTH|WRONGPASS|AUTH failed|connection refused'
#   PASS: NOTIFY_PUSH_CONNECTED within 3 min AND the grep prints 0. FAILS as NOTIFY_PUSH_NOT_CONNECTED (never re-attached, or wrong
#   password) or a non-zero grep. Control measured 2026-10-25 on the 8.10.1 redis: the notify-push pod IP appears in CLIENT LIST
#   (1 connection), so the positive half can pass; only that half can fail on a silent log. If notify-push restarted itself on redis
#   loss (expected, §3) its IP changed: the labelled lookup takes the NEW pod's IP.
```
Then the Nextcloud HTTP gate and notify-push readiness (own fence, one call):
```bash
kubectl port-forward -n office svc/nextcloud 18082:8080 >/dev/null 2>&1 & PF=$!; sleep 5
curl -s http://127.0.0.1:18082/status.php     # PASS: "installed":true,"maintenance":false
kill $PF 2>/dev/null
kubectl get deploy -n office nextcloud-notify-push -o jsonpath='{.status.readyReplicas}{"\n"}'   # PASS: 1 within 3 min (it may restart itself once on redis loss — did so twice 2026-09-27; that is expected, a CrashLoop is not)
#   FAILS as: status.php empty or "maintenance":true; readyReplicas empty (0 ready).
```
CONTENTS ASSERTION: the first `nextcloud-cron` Job AFTER the swap completes
and repopulates the cache — `kubectl get jobs -n office --sort-by=.metadata.creationTimestamp | grep nextcloud-cron | tail -1`
must show a Job created after the swap with `1/1` COMPLETIONS, and
`kubectl exec -n office deploy/nextcloud-redis -- redis-cli dbsize` then reads
`>= 10` (baseline 682 incl. sessions; cron alone writes cache keys). FAILS as a
failed/erroring cron Job (cron.php takes file locks in this redis) or dbsize
staying at 1. Attended: sign in to Nextcloud and open one file (exercises
sessions + locking).

### CONTROLS — instruments the gates above and the final sweep read

- CONTROL: metric kube_pod_container_status_restarts_total — final gate over
  the WHOLE window (range = minutes since §2 f2's `T0`, not a fixed 30 m that
  would miss legs 1–5 of an 70-minute run). The query is namespace-wide on
  purpose (fails toward caution): a RESTARTED row for a pod NOT in `touches`
  must be looked at and explained, not ignored — it is not this plan's
  failure only if it predates T0's first leg or is unrelated by its logs. PASS prints `NO_RESTARTS` or only
  `nextcloud-notify-push-*` (≤ 2, expected on redis loss). FAILS as any other
  `RESTARTED <ns> <pod> <n>` line. The deliberate sure-worker / open-webui rolls
  create NEW pods with restartCount 0, so they do not show here. Non-zero
  control: the same expression with `[24h] > 0` returned rows on 2026-09-27
  (e.g. `databases/phpmyadmin-*` 1.0, `ai/librechat-librechat-*` 1.0) — the
  query is not structurally empty.
  ```bash
  kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
  M=$(( ( $(date -u +%s) - T0 ) / 60 + 5 ))
  curl -s -G http://127.0.0.1:9090/api/v1/query \
    --data-urlencode "query=increase(kube_pod_container_status_restarts_total{namespace=~\"databases|download|media|office|ai\"}[${M}m]) > 0" \
    | python3 -c '
import sys, json
r = json.load(sys.stdin)["data"]["result"]
for x in r: print("RESTARTED", x["metric"]["namespace"], x["metric"]["pod"], round(float(x["value"][1]), 1))
print("NO_RESTARTS") if not r else None'
  kill $PF 2>/dev/null
  ```
- CONTROL: metric kube_pod_status_ready — each of the 8 redis pods `condition="true"` = 1 at the end.
- CONTROL: alertname SupersetRedisDown — not firing 10 min after leg 2.
- CONTROL: alertname TubeArchivistPodRestarted — not firing for `tube-archivist-*` (non-redis) pods after leg 4.
- CONTROL: alertname ImmichPodRestarted — not firing after leg 5 (fires if immich-server had to be restarted by the kubelet).
- CONTROL: alertname SureRedisDown — not firing 10 min after leg 6.
- CONTROL: alertname SurePodRestarted — expected to stay silent: `rollout restart` creates a NEW pod (restartCount 0), so this firing means a crash, not our restart.

Read alerts from Prometheus (silences do not hide them there):
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://127.0.0.1:9090/api/v1/alerts | python3 -c '
import sys, json
names = {"SupersetRedisDown","TubeArchivistPodRestarted","ImmichPodRestarted","SureRedisDown","SurePodRestarted","ImmichRedisNotReady"}
a = [x for x in json.load(sys.stdin)["data"]["alerts"] if x["labels"].get("alertname") in names and x["state"] == "firing"]
print("FIRING", [(x["labels"]["alertname"], x["labels"].get("pod")) for x in a]) if a else print("NONE_FIRING")'
kill $PF 2>/dev/null
```
`NONE_FIRING` is only evidence if the rules are LOADED (a rule Prometheus never
loaded is silent forever): all six were present in `/api/v1/rules` on
2026-09-27. Re-check with the same port-forward:
`curl -s http://127.0.0.1:9090/api/v1/rules | grep -o '"name":"\(SupersetRedisDown\|TubeArchivistPodRestarted\|ImmichPodRestarted\|SureRedisDown\|SurePodRestarted\|ImmichRedisNotReady\)"' | sort -u | wc -l`
→ PASS `6`.

Success = every leg's floor + round-trip + contents assertion PASS, and the
final controls clean.

## 5. Rollback

Per leg, newest first. Nothing forward-only happens in any leg: the RDB/AOF format is
unchanged (§1.2) and no app or schema is touched (open-webui leg is sidecar-only).

```bash
cd /Users/mu/code/cberg-home-nextgen
FILE=kubernetes/apps/...          # that leg's file (set it; do not paste a placeholder)
SHA=$(git log -1 --format=%H -- "$FILE")
git show --stat $SHA          # confirm it is that leg's 8.10.2 commit (and ONLY that file)
MSG=$(mktemp /tmp/redis-fleet-revert.XXXXXX); printf 'revert: %s\n' "$(git log -1 --format=%s $SHA)" > "$MSG"
git revert --no-commit $SHA && git commit --only "$FILE" -F "$MSG"
git log -1 --format=%s        # confirm it is YOUR revert subject
git show --stat HEAD          # exactly that one file
git push; rm -f "$MSG"
# then, for that leg, e.g.: wait_img office deploy/sure-redis redis:8.10.1-alpine
# (open-webui: wait_img ai deploy/open-webui-redis redis:8.10.1-alpine)
```
Then re-run that leg's §4 CONTENTS ASSERTION against the reverted pod — a
rollback is done only when the consumer is back on it.

Leg-specific additions:
- **Leg 6 (sure):** the revert swaps redis again → schedule empty again →
  `kubectl rollout restart deploy/sure-worker -n office` once more, then assert
  `scard cron_jobs:default` = 11.
- **Leg 4 (tube-archivist):** 8.10.1 loads the 8.10.2-written dump.rdb (same
  RDB_VERSION 15). If after either direction `exists ta:cookie` = 0 (snapshot
  not loaded): the only durable app value is the YouTube cookie — re-import it
  in Tube Archivist's settings UI (operator), the celery keys regenerate. Last
  resort for the whole volume: restore `tube-archivist-redis-data` from the
  §2 g Longhorn backup per `docs/sops/backup.md` "Restore from Backup"; the
  local copy from §3 leg 4 (`/tmp/ta-dump-*.rdb`) is the byte-exact pre-change
  snapshot to compare against.
- **Leg 3 (open-webui):** the revert is complete (sidecar has no volume and the app/DB were
  never touched). After it, re-run the §4 leg-3 re-attach loop; if the app is stuck,
  `kubectl rollout restart sts/open-webui -n ai`. No sqlite restore path exists or is needed.
- **Leg 8 (nextcloud-redis, password path):** the revert swaps only the image line, so the wrapper,
  `secret/nextcloud-config` and the NetworkPolicy are identical on both sides. After it, assert
  the same checks as §4 leg 8 (NOAUTH unauth'd, PONG auth'd, notify-push CONNECTED). If
  the server is up but `PONG` fails with NOAUTH while auth'd, the secret and the running server
  disagree: `kubectl rollout restart deploy/nextcloud-redis -n office` (re-reads the secret), never
  disable `requirepass`. Sessions/locks are lost either way (non-persistent); users sign in again.
  Do not edit or print the secret in a rollback.
- **Helm wedged `pending-upgrade`** on any app-template leg:
  `docs/sops/application-update.md` §11 (`helm rollback <rel> <rev> -n <ns> --wait=false`,
  then `flux reconcile helmrelease -n <ns> <rel> --force`). Revisions before the
  plan (2026-10-24, chart app-template 5.3.0): redis 16, tube-archivist-redis 17,
  immich-redis 13, sure-redis 15, open-webui 58 (chart 17.0.0).

Cleanup after a successful window (not a rollback): delete the local
`/tmp/ta-dump-*.rdb` and `/tmp/redis-fleet-*`.

## 6. Interference notes

- **Blast radius is strictly per leg**: each redis serves one app; no redis is
  shared across apps (CLIENT LIST 2026-09-27). `databases/redis` has no
  clients at all — it is kept (and first) as the AOF canary.
- **Nextcloud users are signed out** at leg 8 — announce; attended slot only.
- **`conflicts_with`** was rebuilt 2026-10-24: Nextcloud-side plans (nextcloud-9.4.1,
  whiteboard, mcp, the bitnamilegacy exits, paperless-db) are listed because they restart
  consumers or the redis files; platform plans (talos, coredns, longhorn, flux-oci/reconciler,
  envoy, authentik, etcd) because a CNI/node/edge/storage change confounds every reconnect
  gate. Dead refs dropped (flux-distribution-2.9.6 and cilium-1.20.4, executed, 2026-10-25; flux-fleet-0.60.0, app-template-5.2.1, nextcloud-fleet-35.0.1,
  chart-patches-coredns-reloader-blackbox, kube-prometheus-stack-*). **Order:**
  nextcloud-9.4.1 (nightly 10-28) and nextcloud-whiteboard-2.1.2 (nightly 10-29) are
  expected to have executed by 11-29; if either slipped into this slot, serialize them
  BEFORE leg 8, never in the same hour. If a new kube-prometheus-stack plan
  appears, add it here (§4 reads Prometheus).
- **Window choice:** `sun-attended:2026-11-29`. Occupied attended slots: openclaw sat 10-31, talos sun 11-01, otel-operator + helm-drift sat 11-07, etcd/envoy sun
  11-08, python sat 11-14, longhorn sun 11-15, flux-oci sun 11-22. 11-29 is the next slot
  with none of them; sat 11-21 is also free of plans but its 70-minute budget equals this
  plan's estimate, leaving no slack for the attended checks. If the operator wants it
  sooner, sat 11-21 works only with the nextcloud-cron/immich waits trimmed.
- **Helm-drift:** helm-drift-detection (sat 11-07) will have executed before this slot; if it
  adds a field to every HelmRelease, the sed edits here are unaffected (they touch only the
  image-tag lines), but the Helm revision numbers in §5 will be higher — read them fresh.
- **Not in scope, same HelmReleases:** app-template chart 5.1.0 → 5.2.1 for
  redis, tube-archivist-redis, immich-redis, sure-redis (F-94bbd7ee, F-b5e13899,
  F-2983fb7e, F-6d39efbe). (The open-webui chart is already 17.0.0; F-31c19a7f is not answered here.)
  Any plan for those touches these HelmReleases and must be serialized with
  this one. (app-template is now 5.3.0 live; the 5.2.1 plan is gone.)
- **No reboot, no storage-class or PVC operation** — two Longhorn PVCs are
  remounted by their own Recreate; storage-safety pre-flight N/A (no delete).
- **Repo corrections found while planning (not made here — planner writes only
  this file):**
  1. DONE (check-all-versions.py:555/567, verified 2026-09-28). `runbooks/check-all-versions.py` `IMAGE_RELEASE_NOTES_PROJECTS` lacked
     `'redis': ('redis', 'redis')`, and the `-alpine` suffix must be stripped
     to find release `8.10.2`. Until fixed, every redis patch bump lands in
     PLAN on G3 "release notes unavailable" (this is the second fleet-wide
     redis patch to do so).
  2. DONE (auto-update-policy.yaml `*sure-redis*` rule, verified 2026-09-28). **sure-redis is not safe for the unattended lane as-is**: any image swap
     silently empties Sure's sidekiq-cron schedule until sure-worker restarts
     (§1.4). Either add a `*sure-redis*` deny rule with that reason or give the
     auto-updater a post-bump consumer restart. Worth checking whether the
     earlier 8.10.0 → 8.10.1 bump left the schedule empty for a period (bank
     sync gaps) — not verified here.
  3. The open-webui HelmRelease comment says the sidecar runs "no persistence
     … no modules"; live it runs the image defaults (RDB `save 3600 1 300 100
     60 10000` to container fs, 5 modules loaded) because the chart sets no
     command. Harmless (no volume) but the comment is false.
