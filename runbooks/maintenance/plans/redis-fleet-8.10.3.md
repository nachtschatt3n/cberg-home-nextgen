---
plan_id: redis-fleet-8.10.3
component: redis                      # coverage group redis-fleet-8.10.3 (image-fleet, 3 members)
supersedes: redis-fleet-8.10.2        # vetted 8-consumer plan, retargeted + narrowed 2026-10-27 (sweep 3f978ad9)
pr: null                              # coverage.py needs_plan (direct-bump lane) — no Renovate PR
kind: image
current: "redis:8.10.1-alpine on media/immich-redis, office/nextcloud-redis, office/sure-redis"
target: "redis:8.10.3-alpine on those 3 (the other 5 redis consumers + affine-redis are NOT in this plan: coverage holds them only on G5 cooldown, so they land via Step 0 direct-bump; §1.1)"
update_type: patch
risk: medium                          # Each leg alone is low (same-minor patch; 8.10.2->8.10.3 is 6 commits, the only
                                      # server-behaviour change is gated on cluster_enabled; RDB_VERSION 15 unchanged).
                                      # Medium because (a) nextcloud-redis signs every user out; (b) the sure-redis leg
                                      # SILENTLY EMPTIES Sure's sidekiq-cron schedule unless sure-worker is restarted (§1.4).
est_duration_min: 45                  # pre-checks 10 · 3 legs x ~5 · immich poll <=3 · sure-worker restart +3 ·
                                      # nextcloud-cron wait <=5 · notify-push poll <=3 · attended Nextcloud/Sure/Immich checks ~6
needs_reboot: false
touches:
  namespaces: [media, office]
  resources:
    - helmrelease/immich-redis                  # media — app-template 5.3.0, non-persistent BullMQ store
    - deployment/immich-redis
    - helmrelease/sure-redis                    # office — app-template 5.3.0, non-persistent
    - deployment/sure-redis
    - deployment/sure-worker                    # office — ROLLOUT RESTART after the swap (§3 leg 2)
    - deployment/nextcloud-redis                # office — plain manifest (nextcloud Kustomization), requirepass wrapper
    - secret/nextcloud-config                   # read-only reference (redis-password key); not modified, never printed
    # consumers that reconnect in-process and are NOT restarted (asserted in §4 v_cons):
    - deployment/immich-server
    - deployment/sure-web
    - deployment/nextcloud
    - deployment/nextcloud-notify-push          # may restart itself on redis loss (did twice 2026-09-27)
    - cronjob/nextcloud-cron                    # next tick after the swap is the leg-3 contents gate
  shared: [monitoring]                  # §4 reads Prometheus (the window's instrument). No gateway, storage,
                                        # DNS or CNI change; none of the three redis pods has a volume.
depends_on: []
conflicts_with:
  # Same consumers / same files (carried from redis-fleet-8.10.2, re-checked 2026-10-27):
  - nextcloud-9.4.1                     # vetted nightly:2026-10-28 — Nextcloud app roll. Must be settled BEFORE leg 3.
  - nextcloud-whiteboard-2.1.2          # vetted nightly:2026-10-29 — uses the nextcloud redis path.
  - nextcloud-mcp-0.202.1               # blocked — every gate calls into Nextcloud; lists nextcloud-redis (successor of 0.201.2, superseded 2026-10-27)
  - bitnamilegacy-exit-nextcloud-db     # blocked — quiesces Nextcloud; never stack a session-store restart on a DB cutover
  - python-fleet-3.15.2                 # sat-attended:2026-11-14 — office/ namespace overlap; reciprocal (successor of superseded 3.15.0)
  # Platform serialisation (a roll of these confounds every reconnect gate in §4):
  - helm-drift-detection                # asserts Helm revisions IDENTICAL across releases; this plan upgrades 2 releases
  - flux-oci-chart-sources              # sun-attended:2026-11-22 — re-points app-template chart sources (immich-redis, sure-redis)
  - flux-reconciler-impersonation       # changes WHO applies the Kustomizations/HelmReleases this plan relies on
  - talos-linux-1.14.4                  # node reboots
  - longhorn-1.13.0                     # immich-server / nextcloud / sure-worker volumes; never stack on a storage upgrade
  - authentik-2026.8.5                  # SSO for the attended Nextcloud/Sure/Immich checks (sat-attended:2026-11-21)
  - authentik-web-max-requests          # same
  - envoy-proxy-config-distroless-v1.40.0  # public edge roll hides app reachability gates
  - envoy-proxy-config-distroless-v1.39.4  # same
  - etcd-timeouts-5000-500              # control-plane timing change under rolling Deployments
  # Dropped vs 8.10.2 (no shared surface any more — those legs left the plan): tube-archivist-0.6.0,
  # tube-archivist-elasticsearch-9.5.5, paperless-db-13.0.2 (executed), openclaw-2026.10.5 (ns ai not touched),
  # immich-server-3.3.5 (executed), nextcloud-mcp-0.198.0 / 0.201.2 and python-fleet-3.15.0 (superseded), bitnamilegacy-exit-nextcloud-redis (executed),
  # coredns-1.48.1 (superseded; its superseded_by coredns-1.48.2 has no file). No kube-prometheus-stack-* plan is
  # open; if one appears, add it (§4 reads Prometheus).
exclusive: false
capability_change: false                # same-behaviour patch bump; nextcloud-redis auth/config untouched
autonomy_override: human-gated          # nextcloud-redis logs every user out and the sure-worker restart needs a human
                                        # reading the §4 leg-2 schedule gate (policy rule *sure-redis*).
rollback_class: git-revert              # one commit per leg; all three are non-persistent (no file to load either way)
backup_gate: "N/A — none of the three redis instances has a volume or persists anything (premises *-non-persistent / nextcloud wrapper --save \"\" --appendonly no); nothing to back up or restore."
finding_refs: [F-c637a09a, F-3fcdca7b, F-2e326f86]
                                        # immich-redis, nextcloud-redis, sure-redis 8.10.1 -> 8.10.3 version findings
                                        # (policy-cli finding list --grep, 2026-10-27). The other 5 consumers' findings
                                        # (F-d2bb762b, F-8c50c463, F-625d3a3f, F-3a75c9aa, F-e8a41b1b) and affine-redis
                                        # F-d40c9c12 are lane HELD (G5 cooldown), not PLAN — Step 0 answers them.
status: draft
review: null
window: "sun-attended:2026-11-29"       # carried from redis-fleet-8.10.2 (dispatcher: keep unless conflicts forbid).
                                        # 11-29 has no other plan; nothing in conflicts_with is stamped for it.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/immich.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-27"
premises:
  # Read-verb only. Each was measured 2026-10-27 and returned the expected value.
  - id: office-images-current
    why: >-
      `current:` claims 8.10.1-alpine on nextcloud-redis and sure-redis (order
      nextcloud, sure). A different value means the nightly lane or a hand edit
      moved one — drop that leg, do not force it.
    run: kubectl get deploy -n office nextcloud-redis sure-redis -o jsonpath='{.items[*].spec.template.spec.containers[0].image}'
    expect_exact: redis:8.10.1-alpine redis:8.10.1-alpine
  - id: immich-redis-image-current
    why: Same, for immich-redis.
    run: kubectl get deploy -n media immich-redis -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: redis:8.10.1-alpine
  - id: immich-redis-non-persistent
    why: >-
      §1.2 rules out the inherited "forward-only DB migrations" hold reason because
      immich-redis is a non-persistent BullMQ store with no volume. If persistence
      were turned on, rollback reasoning (nothing to load) changes.
    run: kubectl get deploy -n media immich-redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_exact: '["redis-server","--save","","--appendonly","no"]'
  - id: nextcloud-redis-requirepass-wrapper
    why: >-
      nextcloud-redis starts through an sh wrapper that refuses an empty REDIS_PASSWORD
      and runs --requirepass. §4 leg 3 relies on REDISCLI_AUTH and on the NOAUTH control.
      The pattern appears only in the wrapper command.
    run: kubectl get deploy -n office nextcloud-redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_contains: 'exec redis-server --save'
  - id: nextcloud-redis-auth-env-from-secret
    why: >-
      REDIS_PASSWORD and REDISCLI_AUTH both come from secret/nextcloud-config key
      redis-password. Names only; the secret value is never printed.
    run: kubectl get deploy -n office nextcloud-redis -o jsonpath='{"secret="}{.spec.template.spec.containers[0].env[*].valueFrom.secretKeyRef.name}{" key="}{.spec.template.spec.containers[0].env[*].valueFrom.secretKeyRef.key}'
    expect_exact: 'secret=nextcloud-config nextcloud-config key=redis-password redis-password'
  - id: sure-redis-non-persistent
    why: >-
      The sure-worker restart in §3 leg 2 is required precisely because this redis
      loses everything (including the sidekiq-cron schedule) on restart.
    run: kubectl get deploy -n office sure-redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_exact: '["redis-server","--save","","--appendonly","no"]'
  - id: sure-worker-surge-zero
    why: >-
      §3 leg 2 rollout-restarts sure-worker. maxSurge 0 guarantees no second Sidekiq
      process registers the cron schedule concurrently and its RWO volume is not
      double-attached.
    run: kubectl get deploy -n office sure-worker -o jsonpath='{.spec.strategy.rollingUpdate.maxSurge}'
    expect_exact: "0"
  - id: manifest-pins-current
    why: >-
      §3's seds are anchored on these literals; each file must hold exactly one line
      ENDING in 8.10.1-alpine. 0 = that leg's commit would be empty; 2 = a second pin
      the sed would also rewrite.
    run: grep -c "8\.10\.1-alpine$" kubernetes/apps/media/immich/app/redis-helmrelease.yaml kubernetes/apps/office/sure/app/redis-helmrelease.yaml kubernetes/apps/office/nextcloud/app/redis-deployment.yaml
    expect_matches: '(?s)^(?:\S+:1\n?){3}$'
---

# redis fleet 8.10.1-alpine → 8.10.3-alpine (3 held consumers; supersedes redis-fleet-8.10.2)

## 1. Summary & why held

### 1.0 What changed vs redis-fleet-8.10.2 (2026-10-27)

1. **Target 8.10.2 → 8.10.3.** Upstream `redis/redis` published 8.10.3 on
   2026-10-26T11:56Z (Latest; same-day patch releases 8.8.4/8.6.8/8.4.8/8.2.11/7.4.12
   for older lines). Docker Hub `redis:8.10.3-alpine` exists: `last_updated`
   2026-10-26T16:59:28Z, index digest
   `sha256:896f241f438ab6a210cfb24f573b84bea721a4cbe67f1b4fd07eb638b3b02a7b`.
   `8.10.4-alpine` and `8.11.0-alpine` → 404. (Note: `8.10.2-alpine` was RE-PUSHED
   again on 2026-10-26T15:05Z, digest now `9f8d2d78...`; the old plan's pinned digest
   check would have failed anyway.)
2. **Scope 8 → 3.** `coverage.py --json` (2026-10-27) puts only immich-redis,
   nextcloud-redis and sure-redis in `needs_plan` (group `redis-fleet-8.10.3`).
   databases/redis, superset-redis-official, tube-archivist-redis, paperless-redis and
   affine-redis are lane **HELD on G5 cooldown only** ("eligible in 15h") → they are
   auto-applied by the Step 0 direct-bump lane once the cooldown clears. The open-webui
   redis sidecar is in **lockstep** with the open-webui app image 0.12.4 (itself held
   only on cooldown) and moves with that, not here. Legs 1–4 and 7 of the old plan
   (canary AOF, superset, open-webui sidecar, tube-archivist RDB, paperless) are
   therefore REMOVED, together with their backup gate, dump.rdb copy and drain checks.
3. **The immich hold reason is inherited and false for this member** (§1.2).

### 1.1 What moves

Three Docker Hub `redis` instances move `8.10.1-alpine -> 8.10.3-alpine`, one commit
per consumer: immich-redis (leg 1), sure-redis + sure-worker restart (leg 2),
nextcloud-redis (leg 3, last). All three are non-persistent (`--save "" --appendonly no`,
no volume), `strategy: Recreate`. `affine-redis` already runs 8.10.2 in-cluster.

### 1.2 Why held, per member — and which reasons are real

Upstream delta, read from `gh api repos/redis/redis/compare/8.10.2...8.10.3` (6 commits,
on top of the 6 of 8.10.2 already reviewed in redis-fleet-8.10.2 §1.2):

- `src/pubsub.c`: PUBLISH/SPUBLISH now reject a message too large for cluster-bus
  propagation — **the new check is inside `if (server.cluster_enabled)`**, and the
  error reply is only reachable through it. None of these instances runs cluster mode,
  so PUBLISH behaviour is unchanged for BullMQ, Sidekiq and Nextcloud.
- `src/cluster.h`, `src/cluster_legacy.c`: cluster mode only.
- `src/tls.c`: cert-field parsing API swap; no instance here uses TLS.
- Build/CI/module Makefiles, version bump. **No `rdb.c`/`aof.c` change; `RDB_VERSION`
  is 15 in both 8.10.2 and 8.10.3** (`src/rdb.h`), as it was in 8.10.1.
- Update urgency SECURITY; the item is cluster-bus-only. Item-level detail stays
  upstream (`docs/sops/vulnerability-disclosure.md`).

Per-member hold reasons (coverage.py, 2026-10-27):

| Member | Hold reason | Real for this member? |
|---|---|---|
| immich-redis | `*immich*`: "Immich server applies forward-only DB migrations ... dump + scratch-restore proof first" | **No — inherited from immich-server by the glob.** immich-redis holds no database and no schema: it is a non-persistent BullMQ queue (premise `immich-redis-non-persistent`; 64 keys, 19 blocking workers, 2026-10-27). A redis swap runs no Immich code and no migration. The real cost is that queued/active BullMQ jobs are dropped (re-runnable from the admin Jobs page) — interruption, not data loss (SD-11). No dump is taken because there is nothing to dump. Repo correction §6.1. |
| sure-redis | `*sure-redis*`: swap silently empties the sidekiq-cron schedule | **Yes** (§1.4). This is why the plan exists. |
| nextcloud-redis | `*nextcloud-redis*`: every user signed out, locks dropped | **Yes**, user impact; accepted interruption under SD-11. |

### 1.3 Nextcloud redis auth path (unchanged by this plan)

The container command is an `sh -c` wrapper that exits if `REDIS_PASSWORD` is empty and
runs `redis-server --save "" --appendonly no --requirepass "$REDIS_PASSWORD"`; both
`REDIS_PASSWORD` and `REDISCLI_AUTH` come from `secret/nextcloud-config` key
`redis-password`; a NetworkPolicy admits only Nextcloud app/cronjob pods and
`nextcloud-notify-push`. The image swap touches none of these, so the password path
survives by construction; §4 leg 3 proves it (auth round trip AND an unauthenticated
`NOAUTH` control; the pre-roll pair read `NOAUTH ... / PONG` on 2026-10-27).

### 1.4 The trap — Sure's cron schedule

`sure-redis` is non-persistent. Sure's recurring jobs (bank sync, market data,
cleanups — `SCARD cron_jobs:default` = **11** on 2026-10-27) live ONLY in that redis
and are written there ONLY at Sidekiq startup (sidekiq-cron 2.3.0,
`lib/sidekiq/cron/schedule_loader.rb`, `config.on(:startup) { ... load_schedule }`;
Sure's `AutoSyncScheduler.sync!` is likewise an `on(:startup)` hook). Swapping the
redis under a running `sure-worker` leaves a healthy worker with an **empty schedule**
— no error, no alert, pods Ready. Leg 2 restarts `sure-worker` after the new redis is
Ready, and §4 asserts the count returns to 11.

### 1.5 Members (re-measured 2026-10-27, all redis_version 8.10.1)

| Leg | Instance | Holds | Consumers | Restart cost |
|---|---|---|---|---|
| 1 | media/immich-redis | BullMQ queues (64 keys) | immich-server (19 `bzpopmin` workers, 17 stalled-check keys) | queued/active jobs dropped; workers reconnect in-process (ioredis) |
| 2 | office/sure-redis | sidekiq queues + **cron schedule** + Rails cache (667 keys) | sure-worker, sure-web (11 clients) | **schedule lost → worker restart required** |
| 3 | office/nextcloud-redis | PHP sessions, file locks, cache (681 keys), `requirepass` | nextcloud, nextcloud-notify-push, nextcloud-cron Jobs | **every logged-in user signed out**, held locks dropped |

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) premises (read-only, fail closed)
.venv/bin/python3 runbooks/plan-premises.py redis-fleet-8.10.3

# b) target still current, cooldown satisfied, digest unchanged since planning.
#    PASS prints AGE_OK and the DIGEST below. TOO_NEW / FETCH_FAILED is a STOP.
curl -s https://hub.docker.com/v2/repositories/library/redis/tags/8.10.3-alpine | python3 -c '
import sys, json, datetime as d
try: j = json.load(sys.stdin); t = j["last_updated"]
except Exception: print("FETCH_FAILED redis"); sys.exit(1)
a = (d.datetime.now(d.timezone.utc) - d.datetime.fromisoformat(t.replace("Z","+00:00"))).total_seconds()/3600
print(("AGE_OK" if a >= 48 else "TOO_NEW"), round(a,1), "h", t, "DIGEST", j.get("digest")); sys.exit(0 if a >= 48 else 1)'
#    Expected (2026-10-27): last_updated 2026-10-26T16:59:28Z, DIGEST sha256:896f241f...b02a7b.
#    A DIFFERENT digest = re-push: re-read the compare (§1.2) before proceeding.

# c) nothing newer superseding the target. EXPECT EXACTLY: 8.10.3 -> 200, 8.10.4 -> 404, 8.11.0 -> 404
for t in 8.10.3-alpine 8.10.4-alpine 8.11.0-alpine; do
  curl -s -o /dev/null -w "$t -> %{http_code}\n" https://hub.docker.com/v2/repositories/library/redis/tags/$t
done
#    FAILS as 8.10.3 -> 404 (withdrawn) or a newer tag -> 200 (refresh this plan; do not apply a superseded target).

# d) Flux sane
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
#    PASS: header line only (or unrelated rows you have explained).

# e) no conflicting plan in this slot
python3 runbooks/maintenance-plan.py --open | grep -iE 'redis|nextcloud|immich|sure|python-fleet|helm-drift|flux-|talos|authentik|longhorn|envoy|etcd' || true
#    PASS: no other plan scheduled for this slot. A hit for TODAY is a STOP (see conflicts_with).

# f) BASELINE — record every number; §4 compares against them. [2026-10-27 values]
for x in media/immich-redis office/nextcloud-redis office/sure-redis; do
  ns=${x%/*}; d=${x#*/}
  echo "## $x $(kubectl exec -n $ns deploy/$d -- sh -c 'redis-cli info server | grep ^redis_version; redis-cli info clients | grep ^connected_clients; redis-cli dbsize' | tr '\r\n' '  ')"
done
#    [immich ~81 clients/64 keys · nextcloud 14/681 · sure 11/667] — floors-with-slack, not exact.
kubectl exec -n office deploy/sure-redis -- redis-cli scard cron_jobs:default                               # [11]
kubectl exec -n media deploy/immich-redis -- sh -c 'redis-cli client list | grep -c "cmd=bzpopmin"'          # [19]
kubectl exec -n office deploy/nextcloud-redis -- sh -c 'env -u REDISCLI_AUTH redis-cli ping; redis-cli ping' # [NOAUTH Authentication required. / PONG]

# f2) CONSUMER BASELINE — the "not restarted" criterion compares against this file.
T0=$(date -u +%s); echo "$T0" > /tmp/redis-fleet3-T0; echo "T0=$T0"
BASE=/tmp/redis-fleet3-consumers-$T0.txt
# Shell state does NOT survive separate tool calls: in every later call run
#   T0=$(cat /tmp/redis-fleet3-T0); BASE=/tmp/redis-fleet3-consumers-$T0.txt
# and re-define the helpers (cons_snap, wait_img, v_floor, v_rt, v_cons, leg_commit).
cons_snap() {   # prints: ns/pod restartCount startTime, one line per consumer pod
  for x in media/immich-server office/nextcloud office/sure-web; do
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
cons_snap | tee "$BASE"; [ "$(wc -l < "$BASE" | tr -d ' ')" -ge 3 ] || { echo "BASELINE_INCOMPLETE"; exit 1; }
#    >= 3 lines (one per consumer Deployment; more if any runs >1 replica). An empty baseline would make v_cons pass unchecked.
#    sure-worker is deliberately NOT in the set (restarted on purpose in leg 2).

# g) Prometheus reachable for §4
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -G http://127.0.0.1:9090/api/v1/query --data-urlencode 'query=count(kube_pod_container_status_restarts_total{namespace="office"})' | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print("PROM_OK" if r and float(r[0]["value"][1])>0 else "PROM_EMPTY")'
kill $PF 2>/dev/null
```

Proceed only if (a) all premises PASS, (b) AGE_OK with the expected digest, (c)
200/404/404, (d) clean, (f) the pre-roll NOAUTH/PONG pair and schedule 11, (g) PROM_OK.
**Announce** the Nextcloud sign-out before starting leg 3.

Optional silence (SOP §4 Step 1) for `media` and `office`, 1 h TTL. Silences affect
only Alertmanager notifications; the §4 alert gates read Prometheus `/api/v1/alerts`.

## 3. Steps (GitOps, one commit per leg, in this order)

Each leg's §4 gates must PASS before the next leg starts. One commit per leg, so a
failure reverts one consumer. Do NOT `flux reconcile` by hand — the webhook applies it.

```bash
cd /Users/mu/code/cberg-home-nextgen
leg_commit() {   # needs LEG, FILE, SUBJ set; message file unique (shared worktree)
  local MSG; MSG=$(mktemp /tmp/redis-fleet3-leg$LEG.XXXXXX)
  printf '%s\n\n%s\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n' "$SUBJ" "Plan redis-fleet-8.10.3, leg $LEG." > "$MSG"
  git diff -- "$FILE"                  # must be exactly the one-line diff shown for the leg
  git commit --only "$FILE" -F "$MSG" || { echo COMMIT_FAILED; return 1; }
  [ "$(git log -1 --format=%s)" = "$SUBJ" ] || { echo "SUBJECT_MISMATCH — amend before push"; return 1; }
  git show --stat HEAD                 # exactly one file
  git push && rm -f "$MSG"
}
wait_img() {   # wait_img <ns> <deploy>/<name> <expected spec image>  (zsh-safe: no variable named `path`)
  local ns=$1 obj=$2 want=$3 i got
  for i in $(seq 1 30); do
    got=$(kubectl get -n $ns $obj -o jsonpath='{.spec.template.spec.containers[0].image}')
    [ "$got" = "$want" ] && kubectl rollout status -n $ns $obj --timeout=180s && echo "ROLLED $obj" && return 0
    sleep 10
  done
  echo "NOT_ROLLED $obj (spec=$got)"; return 1
}
```

Tag edits were dry-run on scratch copies of each target file on macOS (BSD sed),
2026-10-27; the diff lines shown are that output.

### Leg 1 — media/immich-redis

```bash
sed -i '' 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.1-alpine$/\18.10.3-alpine/' kubernetes/apps/media/immich/app/redis-helmrelease.yaml
#   40c40
#   <               tag: 8.10.1-alpine
#   >               tag: 8.10.3-alpine
LEG=1 FILE=kubernetes/apps/media/immich/app/redis-helmrelease.yaml
SUBJ="chore(immich): redis 8.10.1-alpine -> 8.10.3-alpine (plan redis-fleet-8.10.3 leg 1)"
leg_commit
wait_img media deploy/immich-redis redis:8.10.3-alpine
```
Then §4 leg 1.

### Leg 2 — office/sure-redis, THEN restart sure-worker

```bash
sed -i '' 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.1-alpine$/\18.10.3-alpine/' kubernetes/apps/office/sure/app/redis-helmrelease.yaml
#   36c36
#   <               tag: 8.10.1-alpine
#   >               tag: 8.10.3-alpine
LEG=2 FILE=kubernetes/apps/office/sure/app/redis-helmrelease.yaml
SUBJ="chore(sure): redis 8.10.1-alpine -> 8.10.3-alpine (plan redis-fleet-8.10.3 leg 2)"
leg_commit
wait_img office deploy/sure-redis redis:8.10.3-alpine

# The schedule is now EMPTY (§1.4). Positive control for the §4 gate:
kubectl exec -n office deploy/sure-redis -- redis-cli scard cron_jobs:default     # expect 0
# Re-register it: restart the worker ONCE, only after the new redis is Ready.
# (The one imperative step: there is no GitOps way to order a restart AFTER another
# Deployment's rollout; same pattern as docs/sops/secret-rotation.md consumer roll.
# maxSurge 0 — premise sure-worker-surge-zero.)
kubectl rollout restart deploy/sure-worker -n office
kubectl rollout status deploy/sure-worker -n office --timeout=300s
```

### Leg 3 — office/nextcloud-redis (last; signs every user out)

Announce first. Only the image line changes; wrapper, secret and NetworkPolicy are
not edited (never print the secret). Pick a moment right AFTER a `nextcloud-cron` Job
completed (schedule `*/5`), so the next tick lands on the new redis:
```bash
kubectl get jobs -n office --sort-by=.metadata.creationTimestamp | grep nextcloud-cron | tail -2
sed -i '' 's/^\([[:space:]]*image:[[:space:]]*redis:\)8\.10\.1-alpine$/\18.10.3-alpine/' kubernetes/apps/office/nextcloud/app/redis-deployment.yaml
#   52c52
#   <         image: redis:8.10.1-alpine
#   >         image: redis:8.10.3-alpine
LEG=3 FILE=kubernetes/apps/office/nextcloud/app/redis-deployment.yaml
SUBJ="chore(nextcloud): redis 8.10.1-alpine -> 8.10.3-alpine (plan redis-fleet-8.10.3 leg 3)"
leg_commit
wait_img office deploy/nextcloud-redis redis:8.10.3-alpine
```

## 4. Verification (per leg, before the next leg starts)

**Floor for every leg** (shape only — proves the new binary runs):
```bash
v_floor() {   # v_floor <ns> <deploy> — selects pods by the Deployment's OWN selector
  local ns=$1 d=$2 sel
  sel=$(kubectl get deploy -n $ns $d -o json | python3 -c 'import sys,json; print(",".join(f"{k}={v}" for k,v in json.load(sys.stdin)["spec"]["selector"]["matchLabels"].items()))')
  kubectl get pod -n $ns -l "$sel" -o json | python3 -c '
import sys, json
ps = [p for p in json.load(sys.stdin)["items"]
      if p["status"].get("phase") == "Running" and not p["metadata"].get("deletionTimestamp")]
imgs = sorted({c["image"] for p in ps for c in p["status"].get("containerStatuses", [])})
print("PODS", len(ps), imgs)
ok = len(ps) == 1 and imgs == ["docker.io/library/redis:8.10.3-alpine"]
print("FLOOR_OK" if ok else "FLOOR_FAIL"); sys.exit(0 if ok else 1)' \
  && kubectl exec -n $ns deploy/$d -- redis-cli info server | grep -i '^redis_version'
}
# PASS: "PODS 1 ['docker.io/library/redis:8.10.3-alpine']", FLOOR_OK, "redis_version:8.10.3".
# FAILS as PODS 2 (old pod still serving), the 8.10.1 status image (live form measured 2026-10-27 on
# affine-redis: docker.io/library/redis:8.10.2-alpine — same docker.io/library/ prefix), or redis_version:8.10.1.
```

Round trip (scratch db 15, 60 s TTL). FAILS as `(nil)` / `NOAUTH` / connection refused instead of `ok`:
```bash
v_rt() { kubectl exec -n $1 deploy/$2 -- sh -c 'redis-cli -n 15 set __plan_verify ok EX 60 >/dev/null; redis-cli -n 15 get __plan_verify; redis-cli -n 15 del __plan_verify >/dev/null'; }
```

Consumers NOT restarted (end of EVERY leg). PASS `CONSUMERS_UNCHANGED`; FAILS as
`CONSUMERS_CHANGED` with diff lines (a recreated pod or a raised restartCount):
```bash
v_cons() { cons_snap > /tmp/redis-fleet3-consumers-now.txt; if diff "$BASE" /tmp/redis-fleet3-consumers-now.txt; then echo CONSUMERS_UNCHANGED; else echo CONSUMERS_CHANGED; fi; }
```
Non-zero control: snapshots across the 2026-09-27 node roll differed on every line
(all consumers carried new startTimes), so the diff is not structurally blind. If
immich-server is restarted deliberately under leg 1's fallback, record it and
re-baseline (`cons_snap > "$BASE"`) before leg 2.

**Leg 1 — immich.** `v_floor media immich-redis; v_rt media immich-redis`, then
CONTENTS ASSERTION: BullMQ workers re-attached to the new server — poll up to 3 min:
```bash
for i in $(seq 1 18); do
  W=$(kubectl exec -n media deploy/immich-redis -- sh -c 'redis-cli client list | grep -c "cmd=bzpopmin"')
  S=$(kubectl exec -n media deploy/immich-redis -- sh -c 'redis-cli --scan --pattern "immich_bull:*:stalled-check" | wc -l' | tr -d ' ')
  echo "t=$((i*10))s blocking_workers=$W stalled_check_keys=$S"; [ "$W" -ge 15 ] && [ "$S" -ge 10 ] && { echo IMMICH_GATE_PASS; break; }; sleep 10
done
[ "$W" -ge 15 ] && [ "$S" -ge 10 ] || echo IMMICH_GATE_FAIL
#   PASS: workers >= 15 [19] and stalled-check keys >= 10 [17]. Stalled-check keys carry a ~30 s TTL
#   (single samples read 6..19 on 2026-09-27), hence a poll with a floor.
#   FAILS as workers 0 (ioredis did not reconnect) -> `kubectl rollout restart deploy/immich-server -n media`
#   ONCE, re-run; still failing -> §5.
kubectl port-forward -n media svc/immich-server 12283:2283 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s http://127.0.0.1:12283/api/server/ping; echo    # PASS: {"res":"pong"}. FAILS as empty / connection refused
kill $PF 2>/dev/null
```
Attended (optional): Immich admin → Jobs shows queues with workers; if a thumbnail or
metadata job was mid-flight at the swap, run "Missing" for it.
Then `v_cons`.

**Leg 2 — sure.** `v_floor office sure-redis; v_rt office sure-redis`, then
CONTENTS ASSERTION: schedule re-registered and a worker heartbeats —
```bash
kubectl exec -n office deploy/sure-redis -- redis-cli scard cron_jobs:default    # PASS: 11 (§2 f). FAILS as 0: worker restart missing / did not load the schedule
kubectl exec -n office deploy/sure-redis -- redis-cli scard processes            # PASS: >= 1 (Sidekiq heartbeat) [1]. FAILS as 0
kubectl exec -n office deploy/sure-redis -- redis-cli exists cron_job:default:sync_all_accounts   # PASS: 1 [1] (AutoSyncScheduler on(:startup))
kubectl port-forward -n office svc/sure 18085:80 >/dev/null 2>&1 & PF=$!; sleep 5
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18085/up                # PASS: 200
kill $PF 2>/dev/null
```
The positive control for the 11 is the `0` printed in §3 leg 2 before the restart; if
that read 11 instead of 0, stop and find out why before trusting the gate.
Then `v_cons`.

**Leg 3 — nextcloud.** `v_floor office nextcloud-redis; v_rt office nextcloud-redis`
(`v_rt` authenticates via the container's `REDISCLI_AUTH`, so `ok` proves the secret's
password matches the enforced one), then the AUTH CONTROL pair:
```bash
kubectl exec -n office deploy/nextcloud-redis -- sh -c 'env -u REDISCLI_AUTH redis-cli ping'
#   PASS: "NOAUTH Authentication required." FAILS as PONG: server came up unauthenticated — STOP, §5 leg 3.
#   Positive control: printed NOAUTH on the 8.10.1 pod in §2 f.
kubectl exec -n office deploy/nextcloud-redis -- redis-cli ping    # PASS: PONG. FAILS as NOAUTH: password mismatch with the secret.
```
Notify-push reconnect (positive signal — its logs are normally silent, so a clean log
alone proves nothing). ONE call:
```bash
SINCE=$(kubectl get pod -n office -l app=nextcloud-redis -o jsonpath='{.items[0].status.startTime}')
NPIP=$(kubectl get pod -n office -l app=nextcloud-notify-push -o jsonpath='{.items[0].status.podIP}')
echo "since=$SINCE notify-push-ip=$NPIP"
for i in $(seq 1 18); do
  C=$(kubectl exec -n office deploy/nextcloud-redis -- redis-cli client list | grep -c "addr=$NPIP:")
  echo "t=$((i*10))s notify_push_clients=$C"; [ "$C" -ge 1 ] && { echo NOTIFY_PUSH_CONNECTED; break; }; sleep 10
done; [ "$C" -ge 1 ] || echo NOTIFY_PUSH_NOT_CONNECTED
kubectl logs -n office deploy/nextcloud-notify-push --since-time="$SINCE" | grep -ciE 'NOAUTH|WRONGPASS|AUTH failed|connection refused'
#   PASS: NOTIFY_PUSH_CONNECTED within 3 min AND the grep prints 0. FAILS as NOTIFY_PUSH_NOT_CONNECTED or a
#   non-zero grep. If notify-push restarted itself on redis loss, the labelled lookup takes the NEW pod's IP.
```
HTTP + readiness:
```bash
kubectl port-forward -n office svc/nextcloud 18082:8080 >/dev/null 2>&1 & PF=$!; sleep 5
curl -s http://127.0.0.1:18082/status.php     # PASS: "installed":true,"maintenance":false
kill $PF 2>/dev/null
kubectl get deploy -n office nextcloud-notify-push -o jsonpath='{.status.readyReplicas}{"\n"}'   # PASS: 1 within 3 min
#   FAILS as status.php empty or "maintenance":true; readyReplicas empty. (One self-restart of notify-push is expected; CrashLoop is not.)
```
CONTENTS ASSERTION: the first `nextcloud-cron` Job AFTER the swap completes and
repopulates the cache — `kubectl get jobs -n office --sort-by=.metadata.creationTimestamp | grep nextcloud-cron | tail -1`
shows a Job created after `$SINCE` with `1/1` COMPLETIONS, then
`kubectl exec -n office deploy/nextcloud-redis -- redis-cli dbsize` reads `>= 10`
(baseline 681). FAILS as a failed cron Job (cron.php takes file locks here) or dbsize
staying at 0–1. Attended: sign in to Nextcloud and open one file (sessions + locking).
Then `v_cons` (nextcloud and sure-web pods unchanged; notify-push is not in the set).

### CONTROLS — window-wide

- CONTROL: metric `kube_pod_container_status_restarts_total` over the whole run (range
  = minutes since `T0`). PASS `NO_RESTARTS` or only `nextcloud-notify-push-*` (≤ 2).
  FAILS as any other `RESTARTED <ns> <pod> <n>` line — explain it (predates T0 or
  unrelated by its logs) or treat as this plan's failure. The deliberate sure-worker
  roll creates a NEW pod (restartCount 0) and does not show. Non-zero control: the same
  expression with `[24h] > 0` returned rows on 2026-09-27.
  ```bash
  kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
  T0=$(cat /tmp/redis-fleet3-T0); M=$(( ( $(date -u +%s) - T0 ) / 60 + 5 ))
  curl -s -G http://127.0.0.1:9090/api/v1/query \
    --data-urlencode "query=increase(kube_pod_container_status_restarts_total{namespace=~\"media|office\"}[${M}m]) > 0" \
    | python3 -c '
import sys, json
r = json.load(sys.stdin)["data"]["result"]
for x in r: print("RESTARTED", x["metric"]["namespace"], x["metric"]["pod"], round(float(x["value"][1]), 1))
print("NO_RESTARTS") if not r else None'
  kill $PF 2>/dev/null
  ```
- CONTROL: alerts `ImmichPodRestarted`, `ImmichRedisNotReady`, `SureRedisDown`,
  `SurePodRestarted` not firing 10 min after their leg. All four exist in
  PrometheusRules `monitoring/immich-alerts` and `monitoring/sure-alerts` with
  `release: kube-prometheus-stack` (measured 2026-10-27); confirm LOADED below.
  ```bash
  kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
  curl -s http://127.0.0.1:9090/api/v1/rules | python3 -c '
import sys, json
names = {"ImmichPodRestarted","ImmichRedisNotReady","SureRedisDown","SurePodRestarted"}
got = {r["name"] for g in json.load(sys.stdin)["data"]["groups"] for r in g["rules"] if r.get("name") in names}
print("RULES_LOADED", len(got))'                       # PASS: RULES_LOADED 4 (fewer = NONE_FIRING below is not evidence)
  curl -s http://127.0.0.1:9090/api/v1/alerts | python3 -c '
import sys, json
names = {"ImmichPodRestarted","ImmichRedisNotReady","SureRedisDown","SurePodRestarted"}
a = [x for x in json.load(sys.stdin)["data"]["alerts"] if x["labels"].get("alertname") in names and x["state"] == "firing"]
print("FIRING", [(x["labels"]["alertname"], x["labels"].get("pod")) for x in a]) if a else print("NONE_FIRING")'
  kill $PF 2>/dev/null
  ```
  No dedicated Nextcloud-redis alert exists; leg 3 is covered by its own gates.

Success = every leg's floor + round trip + contents assertion PASS, `CONSUMERS_UNCHANGED`
after each leg, and the controls clean.

## 5. Rollback

Per leg, newest first. Nothing forward-only happens: all three instances are
non-persistent (no file is written or loaded on either side), RDB_VERSION is unchanged
anyway, and no app or schema is touched. A rollback is therefore a revert plus the same
consumer re-attach work as the forward leg.

```bash
cd /Users/mu/code/cberg-home-nextgen
FILE=kubernetes/apps/office/sure/app/redis-helmrelease.yaml   # set to THAT leg's file (leg 1 immich / 2 sure / 3 nextcloud)
SHA=$(git log -1 --format=%H -- "$FILE")
git show --stat $SHA          # confirm it is that leg's 8.10.3 commit (and ONLY that file)
MSG=$(mktemp /tmp/redis-fleet3-revert.XXXXXX); printf 'revert: %s\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n' "$(git log -1 --format=%s $SHA)" > "$MSG"
git revert --no-commit $SHA && git commit --only "$FILE" -F "$MSG"
git log -1 --format=%s        # confirm it is YOUR revert subject
git show --stat HEAD          # exactly that one file
git push; rm -f "$MSG"
# then: wait_img <ns> deploy/<that redis> redis:8.10.1-alpine
```
Then re-run that leg's §4 CONTENTS ASSERTION against the reverted pod (v_floor will
correctly print FLOOR_FAIL — it expects 8.10.3; check `redis_version:8.10.1` instead).
A rollback is done only when the consumer is back on it.

Leg-specific additions:
- **Leg 2 (sure):** the revert swaps redis again → schedule empty again →
  `kubectl rollout restart deploy/sure-worker -n office` once more, then assert
  `scard cron_jobs:default` = 11. Forgetting this is the one way a rollback here
  causes silent harm (no bank sync until the next worker restart).
- **Leg 1 (immich):** if workers do not re-attach after the revert either,
  `kubectl rollout restart deploy/immich-server -n media` once; then run "Missing" for
  thumbnail/metadata jobs in the admin Jobs page.
- **Leg 3 (nextcloud-redis):** wrapper, secret and NetworkPolicy are identical on both
  sides. Re-assert NOAUTH unauth'd / PONG auth'd / notify-push CONNECTED. If auth'd PONG
  fails with NOAUTH, `kubectl rollout restart deploy/nextcloud-redis -n office` (re-reads
  the secret); never disable `requirepass`, never print the secret. Users sign in again.
- **Helm wedged `pending-upgrade`** on leg 1 or 2: `docs/sops/application-update.md` §11
  (`helm rollback <rel> <rev> -n <ns> --wait=false`, then
  `flux reconcile helmrelease -n <ns> <rel> --force`). Revisions on 2026-10-27 (chart
  app-template 5.3.0): immich-redis 13, sure-redis 15 — read them fresh at the window
  (helm-drift-detection / flux-oci-chart-sources may have moved them).

Cleanup after a successful window: `rm -f /tmp/redis-fleet3-*`.

## 6. Interference notes

- **Blast radius is strictly per leg**: each redis serves one app (CLIENT LIST).
  No shared storage, no gateway/DNS/CNI change.
- **Nextcloud users are signed out** at leg 3 — announce. SD-11 would allow the nightly
  slot for that leg alone, but the sure leg's schedule gate keeps the plan HUMAN-GATED.
- **Window `sun-attended:2026-11-29`** carried from redis-fleet-8.10.2; no other plan is
  stamped for it (2026-10-27). Neighbours: authentik-2026.8.5 sat 11-21, flux-oci-chart-sources
  sun 11-22 — both different days. At 45 min this would also fit a Saturday budget, but no
  free Saturday before 11-29 is clear of conflicts_with (11-21 holds authentik).
- **nextcloud-9.4.1 (nightly 10-28) and nextcloud-whiteboard-2.1.2 (nightly 10-29)** should
  have executed by 11-29; if either slipped into this slot, serialize it BEFORE leg 3.
- **Step 0 interplay:** the other redis consumers (databases/redis, superset,
  tube-archivist, paperless, affine) direct-bump to 8.10.3 in a nightly Step 0 once G5
  cooldown clears (~2026-10-28). That is NOT this plan; it does mean tube-archivist-redis
  (the one persistent RDB, durable `ta:cookie`) goes unattended without the old plan's
  dump.rdb copy — flagged as an observation below.
- **helm-drift-detection**: if it adds a field to every HelmRelease before this slot, the
  seds here are unaffected (they touch only the tag lines); §5 revision numbers move.
- **Not in scope, same HelmReleases:** app-template chart bumps for immich-redis /
  sure-redis — any such plan must be serialized with this one.
- **No reboot, no PVC/storage operation** — storage-safety pre-flight N/A.
- **Repo corrections found while planning (not made here — planner writes only plan files):**
  1. **`*immich*` deny rule gives immich-redis a false hold reason.** The glob in
     `runbooks/auto-update-policy.yaml` (added 2026-10-22 for immich-server's forward-only
     migrations) also matches `immich-redis`, so every redis patch sends it to PLAN citing
     "dump + scratch-restore proof" for a store that has no database and no persistence.
     Same failure shape as the `*nextcloud*` / `*nextcloud-mcp*` / `*affine*` cases the
     file already documents. Fix: add, ABOVE `*immich*` (first match wins), a
     `- match: "*immich-redis*"` rule with its own true reason (non-persistent BullMQ;
     swap drops queued jobs, re-runnable) and `max: patch`, so redis patches for it can
     ride Step 0 like the other non-persistent consumers. Also check `*immich*` against
     `immich-machine-learning` for the same problem.
  2. **README vs dispatch on retargets.** `runbooks/maintenance/plans/README.md` says to
     KEEP the plan_id on a refresh and supersede only when it becomes a different job.
     This retarget was dispatched as a new id because coverage's group_id is
     `redis-fleet-<target>` and the scope shrank 8 → 3; if coverage keeps naming groups
     by target version, the README rule and coverage's grouping disagree for every fleet
     retarget — one of them should change.
  3. Observation: tube-archivist-redis (persistent RDB, durable `ta:cookie`) is now in the
     unattended lane; the old plan's pre-swap dump.rdb copy and post-swap `exists ta:cookie`
     gate have no equivalent in Step 0's health gate. Low risk (RDB_VERSION 15 unchanged),
     but the cookie gate is the only contents check that would notice a non-load.
