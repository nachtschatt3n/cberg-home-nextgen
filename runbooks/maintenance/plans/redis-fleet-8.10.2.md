---
plan_id: redis-fleet-8.10.2
component: redis                      # matches the held dep basename `redis` for every
                                      # consumer; open-webui's app leg joins via the
                                      # version pair (0.11.3 in current, 0.11.4 in target)
pr: null                              # coverage.py needs_plan (direct-bump lane) — no Renovate PR
kind: image
current: "redis:8.10.1-alpine on 8 consumers (databases/redis, databases/superset-redis-official, download/tube-archivist-redis, media/immich-redis, office/nextcloud-redis, office/paperless-redis, office/sure-redis, ai/open-webui-redis) + ghcr.io/open-webui/open-webui 0.11.3"
target: "redis:8.10.2-alpine on all 8 consumers + ghcr.io/open-webui/open-webui 0.11.4 (lockstep with its redis sidecar, one commit)"
update_type: patch
risk: medium                          # Every redis leg alone is low (same-minor patch, RDB_VERSION 15
                                      # unchanged, 6 upstream commits). Medium because of: (a) the
                                      # open-webui app leg is a large feature release despite the patch
                                      # number (§1.3); (b) nextcloud-redis logs every user out; (c) the
                                      # sure-redis leg SILENTLY EMPTIES Sure's sidekiq-cron schedule unless
                                      # sure-worker is restarted afterwards (§1.4) — a trap no health
                                      # signal shows.
est_duration_min: 85                  # pre-checks 10 · 8 legs × ~6 (edit/commit/push, reconcile, gates)
                                      # · open-webui leg +5 (STS roll, UI check) · waits the gates can
                                      # absorb (nextcloud-cron ≤5, immich poll ≤3, notify-push ≤3) · the
                                      # attended paperless PDF + Nextcloud login · slack. RAISED from 70
                                      # on review 2026-09-27: 70 was the entire sat-attended budget.
                                      # Now fits sun-attended only (180); review suggested 2026-10-18.
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
    - deployment/nextcloud-redis                # office — plain manifest (nextcloud Kustomization)
    - deployment/paperless-redis                # office — plain manifest (paperless-ngx Kustomization)
    - helmrelease/sure-redis                    # office
    - deployment/sure-redis
    - deployment/sure-worker                    # office — ROLLOUT RESTART after the swap (§3 leg 6)
    - helmrelease/open-webui                    # ai — sidecar tag + app tag, ONE commit
    - deployment/open-webui-redis
    - statefulset/open-webui                    # rolls to 0.11.4
    - pvc/open-webui-20g                        # webui.db copied in-pod before the roll (§3 leg 3)
    # consumers that reconnect in-process and are NOT restarted (asserted in §4):
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
  - nextcloud-redis-hardening           # draft, window:null. Edits the SAME file
                                        # (office/nextcloud/app/redis-deployment.yaml: command,
                                        # NetworkPolicy) and restarts the same redis. Two
                                        # log-everyone-out changes in one slot also blur which one
                                        # broke sessions/locks. Reciprocal entry NOT present in that
                                        # file (planner writes only its own file) — one side suffices
                                        # for the scheduler.
  - helm-drift-detection                # its §4.1 asserts Helm revisions are IDENTICAL across all
                                        # releases before/after; this plan upgrades 5 releases
                                        # (redis, tube-archivist-redis, immich-redis, sure-redis,
                                        # open-webui) and would fail that gate.
  - flux-oci-chart-sources              # rolls statefulset/open-webui (+ its redis) by re-pointing
                                        # the chart source; never two open-webui rolls in one slot.
  - flux-reconciler-impersonation       # touches every namespace here and changes WHO applies
                                        # the Kustomizations/HelmReleases this plan relies on.
  - bitnamilegacy-exit-nextcloud-db     # blocked, window:null — quiesces Nextcloud; never stack a
                                        # session-store restart on a DB cutover.
  - paperless-db-13.0.2                 # vetted, sat-attended:2026-10-24 — restarts paperless-ngx
                                        # and its DB; keep the celery-broker swap out of that slot.
  - app-template-5.2.1                  # draft (concurrent, 2026-09-27). Rewrites the SAME 4 HR files
                                        # (redis, tube-archivist-redis, immich-redis, sure-redis) and its
                                        # §4 SAME_GEN gate reads GEN_CHANGED on this plan's rolls. It
                                        # already lists this plan back. (review 2026-09-27, blocking #1)
  - chart-patches-coredns-reloader-blackbox  # draft. A CoreDNS roll while consumers re-resolve
                                        # their redis Service names would confound every reconnect
                                        # gate in §4. Not reciprocal yet in that file.
exclusive: false
security_ref: F-6cfc5079                # related: the open-webui image's accepted security finding
                                        # (detail on the record). Whether 0.11.4 changes it is for the
                                        # next sweep to MEASURE, not for this plan to claim.
capability_change: true                 # open-webui 0.11.4 changes user-visible behaviour (link
                                        # rendering, skill discovery, Integrations tab opt-in,
                                        # removed bundled Python packages) — never unattended.
autonomy_override: human-gated          # nextcloud-redis leg logs every user out (policy rule
                                        # *nextcloud-redis*: "ATTENDED low-traffic slot"); the
                                        # sure-worker restart needs a human reading §4 leg-6 gate.
rollback_class: git-revert              # one commit per leg, each reverts cleanly: RDB/AOF format is
                                        # unchanged (RDB_VERSION 15 in both tags) and open-webui adds no
                                        # alembic migration (§1.3). Backups are taken anyway (backup_gate).
backup_gate: "Completed Longhorn backup < 26h for open-webui-20g, tube-archivist-redis-data and the redis-data volume (§2 g); PLUS in-pod copies taken in §3 immediately before their leg: webui.db -> webui.db.pre-0.11.4 (sqlite online-backup API, size compared) and tube-archivist dump.rdb -> local scratch file (byte count compared)."
finding_refs: [F-d2bb762b, F-8c50c463, F-625d3a3f, F-c637a09a, F-3fcdca7b, F-3a75c9aa, F-2e326f86, F-e8a41b1b, F-db500cce]
                                        # the 8 per-consumer redis image findings + open-webui
                                        # 0.11.3 -> 0.11.4 (policy-cli finding list --grep redis /
                                        # --grep open-webui, 2026-09-27). The app-template chart
                                        # 5.1.0 -> 5.2.1 findings (F-94bbd7ee, F-b5e13899, F-2983fb7e,
                                        # F-6d39efbe) and open-webui chart 16.6.0 (F-31c19a7f) are
                                        # NOT answered here — separate held items.
status: draft   # plan-reviewer 2026-09-27: needs-fix (3 blocking) -> fixed -> re-review READY-FOR-GO.
                # No operator GO recorded; awaiting vetting/scheduling + go/no-go.
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md               # read-only relevance: two Longhorn PVCs remounted, none deleted
  - docs/sops/paperless.md
  - docs/sops/immich.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-09-27"
premises:
  # Read-verb only. Each was run 2026-09-27 and returned the expected value.
  - id: databases-images-current
    why: >-
      `current:` claims 8.10.1-alpine on both databases redis Deployments. If the
      nightly lane or a hand edit moved either, that leg is a no-op and §3's sed
      for it matches nothing — drop the leg, do not force it.
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
  - id: open-webui-app-current
    why: >-
      The lockstep leg moves open-webui 0.11.3 -> 0.11.4. If the StatefulSet is
      already elsewhere the §1.3 migration evidence (no alembic change between
      exactly these tags) no longer applies — re-derive it.
    run: kubectl get sts -n ai open-webui -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/open-webui/open-webui:0.11.3
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
      command override) with /data on a PVC — it is the only consumer whose
      contents survive a restart and must be asserted after it (§4 leg 4). The
      literal prefix keeps output non-empty; a command appearing after `cmd=`
      means someone changed persistence.
    run: kubectl get deploy -n download tube-archivist-redis -o jsonpath='{"cmd="}{.spec.template.spec.containers[0].command}{" claim="}{.spec.template.spec.volumes[?(@.persistentVolumeClaim)].persistentVolumeClaim.claimName}'
    expect_exact: cmd= claim=tube-archivist-redis-data
  - id: nextcloud-redis-non-persistent
    why: >-
      The logout impact in §1 rests on this redis holding sessions with NO
      persistence, and §4's nextcloud gate uses a password-less redis-cli. If
      nextcloud-redis-hardening landed first, the command carries a wrapper and
      the §4 commands need REDISCLI_AUTH — re-derive leg 8.
    run: kubectl get deploy -n office nextcloud-redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_exact: '["redis-server","--save","","--appendonly","no"]'
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
  - id: open-webui-db-backed-up
    why: >-
      The open-webui leg rolls the app on its sqlite PVC. A Completed Longhorn
      backup must exist (9 Completed on 2026-09-27); freshness is asserted in §2.
    run: kubectl get backups.longhorn.io -n storage -o jsonpath='{.items[?(@.status.volumeName=="open-webui-20g")].status.state}'
    expect_contains: Completed
  - id: tube-archivist-redis-backed-up
    why: The one redis whose contents are persistent. Freshness asserted in §2.
    run: kubectl get backups.longhorn.io -n storage -o jsonpath='{.items[?(@.status.volumeName=="tube-archivist-redis-data")].status.state}'
    expect_contains: Completed
  - id: manifest-pins-current
    why: >-
      §3's seds are anchored on these exact literals; each file must hold exactly
      one line ENDING in 8.10.1-alpine (the open-webui comment line ends in
      "is", so it is not counted; its own sed handles it). A count of 0 means
      that leg's commit would be empty; 2 means a second pin the sed would also
      rewrite. Order of grep's output lines is not asserted.
    run: grep -c "8\.10\.1-alpine$" kubernetes/apps/databases/redis/app/helmrelease.yaml kubernetes/apps/databases/superset/app/redis-deployment.yaml kubernetes/apps/download/tube-archivist/app/redis-helmrelease.yaml kubernetes/apps/media/immich/app/redis-helmrelease.yaml kubernetes/apps/office/nextcloud/app/redis-deployment.yaml kubernetes/apps/office/paperless-ngx/app/redis-deployment.yaml kubernetes/apps/office/sure/app/redis-helmrelease.yaml kubernetes/apps/ai/open-webui/app/helmrelease.yaml
    expect_matches: '(?s)^(?:\S+:1\n?){8}$'
---

# redis fleet 8.10.1-alpine → 8.10.2-alpine (+ open-webui 0.11.3 → 0.11.4)

## 1. Summary & why held

### 1.1 What moves

Eight Docker Hub `redis` instances move `8.10.1-alpine → 8.10.2-alpine`, one
commit per consumer, in blast-radius order (§3). The eighth, open-webui's
chart-rendered websocket redis, moves in ONE commit with the open-webui app
`0.11.3 → 0.11.4` because coverage.py lockstep-binds them (the app image is
PLAN, so the sidecar may not move unattended ahead of it — and vice versa).
`affine-redis` is already on 8.10.2 (`e16ddbeb`, plan `affine-redis-8.10.2`,
executed green 2026-09-26) and is the fleet's first in-cluster proof of the tag.

Tags verified 2026-09-27:
- `redis:8.10.2-alpine` exists on Docker Hub, index digest
  `sha256:3811787313eba226a2ef38658c6ccb91cd5e110edc89c37767de373120a0e5a0`,
  `last_updated 2026-09-24T21:05Z` (a re-push; upstream released 8.10.2 on
  2026-09-17). `8.10.3-alpine` → 404.
- `ghcr.io/open-webui/open-webui:0.11.4` → 200, index digest
  `sha256:9591b13f13843c7721c2b8eaf7382846c81b3ffe126526d1888d1fed50c6a33f`,
  GitHub release published 2026-09-21. `0.11.5` → 404.

Both are past the G5 48 h cooldown today; §2 re-checks because a re-push
resets it.

### 1.2 Why held — the redis legs

Seven legs were held by **G3: "could not verify the release notes (unverified
(release notes unavailable))"**. That is a resolver gap, not a signal:
`IMAGE_RELEASE_NOTES_PROJECTS` in `runbooks/check-all-versions.py` has no entry
for the Docker Hub official image `redis`, and the tag carries an `-alpine`
flavour suffix, while upstream's GitHub release tag is bare `8.10.2` (same
class as the `-openvino` gap already noted in that map). Read by hand from
`redis/redis` releases (`gh release view 8.10.2 -R redis/redis`) and the tag
compare `8.10.1...8.10.2`:

- **6 commits.** Files touched: `acl.c`, `config.c`, `module.c`, `multi.c`,
  `networking.c`, `script.c`, `server.c`, the vector-sets module, `redis.conf`
  and tests. **No `rdb.c`, `aof.c` or `rdb.h` change; `RDB_VERSION` is `15` in
  both tags** — so the AOF of databases/redis and the dump.rdb of
  tube-archivist-redis load unchanged forward AND backward (the rollback
  property this plan relies on).
- `modules/modules.yaml` bumps the bundled RediSearch and TimeSeries modules
  v8.10.0 → v8.10.1; RediSearch's index encoding version is 27 at both tags
  (review 2026-09-27) and no instance here holds module data (tube-archivist
  `FT._LIST` empty; the others run with the modules unused).
- One new config option, `cluster-bus-port-protected-mode`, **"(default
  `no`)"** per the notes — cluster mode only; no instance here runs cluster
  mode. No default changes for a single-node server.
- Other items are fixes in ACL/transaction handling, the cluster bus,
  TimeSeries, RedisSearch and Vector Sets. Item-level detail stays upstream
  (`docs/sops/vulnerability-disclosure.md`). None changes the RESP protocol or
  a command's reply shape for the default user, which is all any consumer here
  uses (two use `requirepass`, none define ACL users).

The eighth, **nextcloud-redis**, is held by its own deny rule
(`*nextcloud-redis*`): *"any restart signs out every logged-in Nextcloud user
and drops held locks … schedule an ATTENDED low-traffic slot"*. That reason is
true and is honoured here (leg 8, last, attended, announced).

### 1.3 Why held — the open-webui app leg (and why it is not trivial)

`0.11.4` is a patch number on a large release (327 commits, 92 KB of notes).
What matters for this deployment, checked against the live instance:

- **Database:** `backend/open_webui/migrations/versions` holds the same 58
  files at `v0.11.3` and `v0.11.4` (GitHub contents API, 2026-09-27); live
  `alembic_version` is `d4c1a8e37b62`. No schema migration → the image revert
  is a complete rollback. §4 asserts the alembic head is unchanged after start.
- **"LangChain community removal … a tool or function importing it has to name
  it in its own requirements"** and **"Undeclared package imports … nltk,
  pymongo, the Google Drive client and the Gemini SDK, are no longer
  installed"**. Live: 0 tools, 1 function (`n8n_pipe`) importing only `os`,
  `pydantic`, `requests`, `time`, `typing` — unaffected.
- **"Integrations tab is opt-in … hidden until an administrator turns on Direct
  Integrations"**. Live: `direct.enable = false`, 0 of 3 users hold personal
  tool/terminal servers; the admin tool server (mcpo) is unaffected — no visible
  loss.
- Slim-image changes do not apply (we run the standard image, sqlite, local
  storage).
- Redis-relevant: a revocation-list fallback ("where Redis cannot be reached, a
  token is now accepted"), non-blocking sign-in rate limiting and a
  `REDIS_TASK_TTL` for shared tasks — all make the app MORE tolerant of the
  brief redis gap this leg causes.
- User-visible changes (link-scheme rendering, skill discovery, per-field
  settings saves) are why `capability_change: true`.

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

### 1.5 Consumer classification (measured 2026-09-27, `redis-cli info` in each pod)

| Leg | Instance | Persistence | Holds | Consumers (CLIENT LIST → pod) | Restart cost |
|---|---|---|---|---|---|
| 1 | databases/redis | **AOF on PVC** (`redis-data`) | nothing (empty AOF, 0 keys) | none (1 client = our own cli) | none — canary for the persisted-load path |
| 2 | databases/superset-redis-official | none | celery broker + results (77 keys) | superset-worker, superset-celerybeat | in-flight celery results lost; worker reconnect in-process **measured** (worker started 08:22, redis restarted 08:49 on 2026-09-27, `inspect ping` → pong now) |
| 3 | ai/open-webui-redis (+ app) | RDB defaults, **no volume** (container fs) | websocket/pubsub + locks (4 keys) | open-webui-0 | app rolls anyway (lockstep) |
| 4 | download/tube-archivist-redis | **RDB on PVC** (`tube-archivist-redis-data`) | celery broker + **durable app state** (`ta:cookie`, no TTL) | tube-archivist (worker + beat) | none if dump.rdb reloads; beat uses DatabaseScheduler (schedule in DB, not redis) |
| 5 | media/immich-redis | none | BullMQ queues (28 keys) | immich-server (19 blocking workers) | queued/active jobs dropped (whether Immich re-queues them is NOT verified from source here — the §4 gate is only that its workers re-attach; a half-done thumbnail/metadata job may need a manual "missing" re-run from the Immich admin Jobs page) |
| 6 | office/sure-redis | none | sidekiq queues + **cron schedule** + Rails cache | sure-worker, sure-web | **cron schedule lost → worker restart required (§1.4)** |
| 7 | office/paperless-redis | none | celery broker + channels layer | paperless-ngx | an in-flight consume task is lost → drain first (§2) |
| 8 | office/nextcloud-redis | none | PHP sessions, file locks, distributed cache | nextcloud, nextcloud-notify-push, nextcloud-cron Jobs | **every logged-in user signed out**, held locks dropped |

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) premises (read-only, fail closed)
.venv/bin/python3 runbooks/plan-premises.py redis-fleet-8.10.2

# b) G5 cooldown still satisfied for BOTH images (a re-push resets it). PASS
#    prints AGE_OK twice; TOO_NEW or FETCH_FAILED on either line is a STOP.
curl -s https://hub.docker.com/v2/repositories/library/redis/tags/8.10.2-alpine | python3 -c '
import sys, json, datetime as d
try: t = json.load(sys.stdin)["last_updated"]
except Exception: print("FETCH_FAILED redis"); sys.exit(1)
a = (d.datetime.now(d.timezone.utc) - d.datetime.fromisoformat(t.replace("Z","+00:00"))).total_seconds()/3600
print(("AGE_OK" if a >= 48 else "TOO_NEW"), "redis", round(a,1), "h", t); sys.exit(0 if a >= 48 else 1)'
gh release view v0.11.4 -R open-webui/open-webui --json publishedAt -q .publishedAt | python3 -c '
import sys, datetime as d
t = sys.stdin.read().strip()
if not t: print("FETCH_FAILED open-webui"); sys.exit(1)
a = (d.datetime.now(d.timezone.utc) - d.datetime.fromisoformat(t.replace("Z","+00:00"))).total_seconds()/3600
print(("AGE_OK" if a >= 48 else "TOO_NEW"), "open-webui", round(a,1), "h", t); sys.exit(0 if a >= 48 else 1)'
#    Expected: redis last_updated 2026-09-24T21:05:07Z, open-webui 2026-09-21T19:25:21Z.
#    A DIFFERENT redis last_updated means the tag was re-pushed: re-read the notes.

# c) targets resolvable, nothing newer superseding them.
#    EXPECT EXACTLY: 8.10.2-alpine -> 200, 8.10.3-alpine -> 404
for t in 8.10.2-alpine 8.10.3-alpine; do
  curl -s -o /dev/null -w "$t -> %{http_code}\n" https://hub.docker.com/v2/repositories/library/redis/tags/$t
done
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:open-webui/open-webui:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in 0.11.4 0.11.5; do   # EXPECT: 0.11.4 -> 200, 0.11.5 -> 404 (200 = refresh the plan)
  curl -s -o /dev/null -w "$t -> %{http_code}\n" -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.index.v1+json" https://ghcr.io/v2/open-webui/open-webui/manifests/$t
done

# d) Flux sane, nothing in flight in these namespaces
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
#    PASS: header line only for both (or unrelated rows you have explained).

# e) no other plan in this window touches these apps / asserts Helm revisions
python3 runbooks/maintenance-plan.py --open | grep -iE 'redis|nextcloud|paperless|immich|superset|sure|tube|open-webui|helm-drift|flux-' || true

# f) BASELINE — record every number; §4 compares against them.
#    (values measured 2026-09-27 in brackets)
for x in databases/redis databases/superset-redis-official download/tube-archivist-redis \
         media/immich-redis office/nextcloud-redis office/paperless-redis office/sure-redis ai/open-webui-redis; do
  ns=${x%/*}; d=${x#*/}
  echo "## $x $(kubectl exec -n $ns deploy/$d -- sh -c 'redis-cli info server | grep ^redis_version; redis-cli info clients | grep ^connected_clients; redis-cli info keyspace | grep ^db0' | tr '\r\n' '  ')"
done
#    [redis 1 client/0 keys · superset 14/77 · tube-archivist 12/50 · immich 81/28 ·
#     nextcloud 13/95 · paperless 10/13 · sure 12/65 · open-webui-redis 4/4]
kubectl exec -n office deploy/sure-redis -- redis-cli scard cron_jobs:default          # [11]
kubectl exec -n download deploy/tube-archivist-redis -- redis-cli exists ta:cookie     # [1]
kubectl exec -n media deploy/immich-redis -- sh -c 'redis-cli client list | grep -c "cmd=bzpopmin"'   # [19]
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "import sqlite3;print(sqlite3.connect('file:/app/backend/data/webui.db?mode=ro',uri=True).execute('select version_num from alembic_version').fetchone()[0])"   # [d4c1a8e37b62]

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
cons_snap | tee "$BASE"                      # 7 lines expected

# g) backups fresh (< 26 h) — ground truth is the newest Completed Backup CR
for v in open-webui-20g tube-archivist-redis-data \
         $(kubectl get pvc -n databases redis-data -o jsonpath='{.spec.volumeName}'); do
  kubectl get backups.longhorn.io -n storage -o json | python3 -c '
import sys, json, datetime as d
v = sys.argv[1]
ts = [b["status"].get("backupCreatedAt") or b["metadata"]["creationTimestamp"]
      for b in json.load(sys.stdin)["items"]
      if b["status"].get("volumeName") == v and b["status"].get("state") == "Completed"]
if not ts: print("NO_BACKUP", v); sys.exit(1)
t = max(ts); a = (d.datetime.now(d.timezone.utc) - d.datetime.fromisoformat(t.replace("Z","+00:00"))).total_seconds()/3600
print(("FRESH" if a < 26 else "STALE"), v, round(a,1), "h"); sys.exit(0 if a < 26 else 1)' "$v"
done
#    PASS: three FRESH lines. (Daily job: CronJob storage/daily-backup-all-volumes, 03:00.)

# h) drain checks — record; each is re-run immediately before its own leg.
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- celery --app paperless inspect active 2>&1 | tail -5
kubectl exec -n download deploy/tube-archivist -- sh -c 'cd /app && celery -A task inspect active 2>&1 | tail -5'
#    PASS: "- empty -" for each node. A running consume/download task means WAIT, not proceed.

# i) Prometheus reachable for §4 (the controls read it)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -G http://127.0.0.1:9090/api/v1/query --data-urlencode 'query=count(kube_pod_container_status_restarts_total{namespace="office"})' | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print("PROM_OK" if r and float(r[0]["value"][1])>0 else "PROM_EMPTY")'
kill $PF 2>/dev/null
```

Proceed only if (a) all premises PASS, (b) AGE_OK ×2, (c) 200/404 ×2,
(d) clean, (g) FRESH ×3, (i) PROM_OK. For (h), proceed per leg when that leg's
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

### Leg 3 — ai/open-webui: redis sidecar + app 0.11.3 → 0.11.4 (ONE commit)

Backup first (sqlite online-backup API, WAL-safe; 88 MB, PVC 16 GB free on
2026-09-27):
```bash
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "
import sqlite3, os
s = sqlite3.connect('/app/backend/data/webui.db'); d = sqlite3.connect('/app/backend/data/webui.db.pre-0.11.4')
s.backup(d); d.close()
print('SRC', os.path.getsize('/app/backend/data/webui.db'), 'COPY', os.path.getsize('/app/backend/data/webui.db.pre-0.11.4'))
print('COPY_ALEMBIC', sqlite3.connect('/app/backend/data/webui.db.pre-0.11.4').execute('select version_num from alembic_version').fetchone()[0])"
#   PASS: COPY > 0 and COPY_ALEMBIC d4c1a8e37b62. (COPY may be smaller than SRC — backup compacts.)
```
Edit (three substitutions, one file — the comment line keeps the file honest):
```bash
sed -i '' -e 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.1-alpine$/\18.10.2-alpine/' \
          -e 's/^\([[:space:]]*tag:[[:space:]]*\)0\.11\.3$/\10.11.4/' \
          -e 's/ 8\.10\.1-alpine is$/ 8.10.2-alpine is/' kubernetes/apps/ai/open-webui/app/helmrelease.yaml
#   -      # only — no persistence, no ACL/auth, no modules. 8.10.1-alpine is
#   +      # only — no persistence, no ACL/auth, no modules. 8.10.2-alpine is
#   -          tag: 8.10.1-alpine
#   +          tag: 8.10.2-alpine
#   -      tag: 0.11.3
#   +      tag: 0.11.4
LEG=3 FILE=kubernetes/apps/ai/open-webui/app/helmrelease.yaml
SUBJ="chore(open-webui): 0.11.3 -> 0.11.4 + redis sidecar 8.10.2-alpine (plan redis-fleet-8.10.2 leg 3)"
leg_commit
wait_img ai deploy/open-webui-redis redis:8.10.2-alpine
wait_img ai sts/open-webui ghcr.io/open-webui/open-webui:0.11.4
```
(open-webui-redis is `RollingUpdate 25%` — a new pod may briefly coexist with
the old; harmless for an ephemeral pubsub store with no volume.)

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

Announce first. Pick a moment right AFTER a `nextcloud-cron` Job completed
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
50 keys incl. a durable one) is the persisted-DATA proof.

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

**Leg 3 — open-webui.** `v_floor ai open-webui-redis; v_rt ai open-webui-redis`, then
```bash
kubectl port-forward -n ai svc/open-webui 18080:80 >/dev/null 2>&1 & PF=$!; sleep 5
curl -s http://127.0.0.1:18080/api/version     # PASS: {"version":"0.11.4",...}  FAILS as 0.11.3 or no body
curl -s http://127.0.0.1:18080/health          # PASS: {"status":true}
kill $PF 2>/dev/null
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "import sqlite3;print(sqlite3.connect('file:/app/backend/data/webui.db?mode=ro',uri=True).execute('select version_num from alembic_version').fetchone()[0])"
#   PASS: d4c1a8e37b62 (unchanged => no migration ran => the image revert is a full rollback).
#   A different head means a migration DID run: rollback then REQUIRES the webui.db.pre-0.11.4 restore (§5).
kubectl exec -n ai deploy/open-webui-redis -- sh -c 'redis-cli info clients | grep ^connected_clients; redis-cli --scan --pattern "open-webui:*" | wc -l'
#   PASS: clients >= 3 [4] and >= 2 open-webui:* keys [4]. FAILS as clients 1 / 0 keys (app not on this redis).
```
CONTENTS ASSERTION: the app serves real data — attended: sign in, open an
existing chat (its history renders), send one message to an Ollama model and
receive a streamed reply (this rides the websocket → redis path). An empty chat
list for an existing user is a FAIL.

**Leg 4 — tube-archivist.** `v_floor download tube-archivist-redis; v_rt download tube-archivist-redis`, then
CONTENTS ASSERTION: the persisted state came back —
```bash
kubectl exec -n download deploy/tube-archivist-redis -- sh -c 'redis-cli exists ta:cookie; redis-cli dbsize; redis-cli info persistence | grep -E "^(loading|rdb_last_bgsave_status):"'
#   PASS: exists=1, dbsize >= 40 [50], loading:0, rdb_last_bgsave_status:ok
#   FAILS as exists=0 / dbsize a handful of fresh celery keys: dump.rdb was NOT loaded -> §5 leg-4 restore.
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

**Leg 8 — nextcloud.** `v_floor office nextcloud-redis; v_rt office nextcloud-redis`, then
```bash
kubectl port-forward -n office svc/nextcloud 18082:8080 >/dev/null 2>&1 & PF=$!; sleep 5
curl -s http://127.0.0.1:18082/status.php     # PASS: "installed":true,"maintenance":false
kill $PF 2>/dev/null
kubectl get deploy -n office nextcloud-notify-push -o jsonpath='{.status.readyReplicas}{"\n"}'   # PASS: 1 within 3 min (it may restart itself once on redis loss — did so twice 2026-09-27; that is expected, a CrashLoop is not)
```
CONTENTS ASSERTION: the first `nextcloud-cron` Job AFTER the swap completes
and repopulates the cache — `kubectl get jobs -n office --sort-by=.metadata.creationTimestamp | grep nextcloud-cron | tail -1`
must show a Job created after the swap with `1/1` COMPLETIONS, and
`kubectl exec -n office deploy/nextcloud-redis -- redis-cli dbsize` then reads
`>= 10` (baseline 95 incl. sessions; cron alone writes cache keys). FAILS as a
failed/erroring cron Job (cron.php takes file locks in this redis) or dbsize
staying at 1. Attended: sign in to Nextcloud and open one file (exercises
sessions + locking).

### CONTROLS — instruments the gates above and the final sweep read

- CONTROL: metric kube_pod_container_status_restarts_total — final gate over
  the WHOLE window (range = minutes since §2 f2's `T0`, not a fixed 30 m that
  would miss legs 1–5 of an 85-minute run). The query is namespace-wide on
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

Per leg, newest first. Nothing forward-only happens in any redis leg (format
unchanged, §1.2); the open-webui leg is forward-only ONLY if §4 leg 3 showed a
changed alembic head.

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
# (open-webui: wait_img ai deploy/open-webui-redis redis:8.10.1-alpine; wait_img ai sts/open-webui ghcr.io/open-webui/open-webui:0.11.3)
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
- **Leg 3 (open-webui):** if the alembic head is unchanged (expected), the
  revert is complete. If it CHANGED, 0.11.3 may not start on the migrated DB,
  so: suspend the open-webui HelmRelease (`flux suspend hr -n ai open-webui`),
  `kubectl scale sts -n ai open-webui --replicas=0` (RWO volume must be
  released — a second pod would hit Multi-Attach), restore through a
  throw-away pod mounting `open-webui-20g` (same image, `sleep` command),
  delete it, then push the revert and `flux resume hr -n ai open-webui` (the
  revert's reconcile restores replicas 1 on 0.11.3). Restore command, run in
  that throw-away pod —
  `kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "import sqlite3; s=sqlite3.connect('/app/backend/data/webui.db.pre-0.11.4'); d=sqlite3.connect('/app/backend/data/webui.db'); s.backup(d); d.close()"`
  then, once `sts/open-webui` is back on 0.11.3 with 1 replica, assert
  alembic head `d4c1a8e37b62` and `/api/version` 0.11.3. Chats written between
  upgrade and restore are lost — say so to the users.
- **Helm wedged `pending-upgrade`** on any app-template leg:
  `docs/sops/application-update.md` §11 (`helm rollback <rel> <rev> -n <ns> --wait=false`,
  then `flux reconcile helmrelease -n <ns> <rel> --force`). Revisions before the
  plan (2026-09-27): redis 15, tube-archivist-redis 16, immich-redis 12,
  sure-redis 14, open-webui 54.

Cleanup after a successful window (not a rollback): leave
`webui.db.pre-0.11.4` for 7 days, then remove it in-pod; delete the local
`/tmp/ta-dump-*.rdb`.

## 6. Interference notes

- **Blast radius is strictly per leg**: each redis serves one app; no redis is
  shared across apps (CLIENT LIST 2026-09-27). `databases/redis` has no
  clients at all — it is kept (and first) as the AOF canary.
- **Nextcloud users are signed out** at leg 8 — announce; attended slot only.
- **`conflicts_with`** is the full serialization set: the hardening plan (same
  file, same restart), helm-drift-detection (Helm-revision gate), the two Flux
  plans (roll open-webui / change the applier), and the two plans that quiesce
  Nextcloud / Paperless. `kube-prometheus-stack-91.4.1` is `executed`, so no
  Prometheus-bump conflict is needed today; if a new kube-prometheus-stack plan
  appears, add it here (§4 reads Prometheus).
- **Not in scope, same HelmReleases:** app-template chart 5.1.0 → 5.2.1 for
  redis, tube-archivist-redis, immich-redis, sure-redis (F-94bbd7ee, F-b5e13899,
  F-2983fb7e, F-6d39efbe) and open-webui chart 16.5.0 → 16.6.0 (F-31c19a7f).
  Any plan for those touches these HelmReleases and must be serialized with
  this one.
- **No reboot, no storage-class or PVC operation** — two Longhorn PVCs are
  remounted by their own Recreate; storage-safety pre-flight N/A (no delete).
- **Repo corrections found while planning (not made here — planner writes only
  this file):**
  1. `runbooks/check-all-versions.py` `IMAGE_RELEASE_NOTES_PROJECTS` lacks
     `'redis': ('redis', 'redis')`, and the `-alpine` suffix must be stripped
     to find release `8.10.2`. Until fixed, every redis patch bump lands in
     PLAN on G3 "release notes unavailable" (this is the second fleet-wide
     redis patch to do so).
  2. **sure-redis is not safe for the unattended lane as-is**: any image swap
     silently empties Sure's sidekiq-cron schedule until sure-worker restarts
     (§1.4). Either add a `*sure-redis*` deny rule with that reason or give the
     auto-updater a post-bump consumer restart. Worth checking whether the
     earlier 8.10.0 → 8.10.1 bump left the schedule empty for a period (bank
     sync gaps) — not verified here.
  3. The open-webui HelmRelease comment says the sidecar runs "no persistence
     … no modules"; live it runs the image defaults (RDB `save 3600 1 300 100
     60 10000` to container fs, 5 modules loaded) because the chart sets no
     command. Harmless (no volume) but the comment is false.
