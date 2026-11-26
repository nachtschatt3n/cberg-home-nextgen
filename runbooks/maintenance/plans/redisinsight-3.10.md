---
plan_id: redisinsight-3.10
component: redisinsight
pr: 556                               # Renovate "update redis/redisinsight ( 3.8.0 -> 3.10.2 )", OPEN, mergeable CLEAN, all checks
                                      # green incl. Flate Render Gate (gh pr checks 556, 2026-11-26). Diff = exactly the one image line.
kind: image
current: "3.8.0"                      # MEASURED 2026-11-26: deploy/redisinsight image redis/redisinsight:3.8.0, pod
                                      # redisinsight-5c8979657d-q6h9q 1/1, imageID
                                      # sha256:b5e19ee240abef6edb435871b90ff8a210995422e8e018ab61c0339d318a1f84 (= Docker Hub 3.8.0 index digest)
target: "3.10.2"                      # RE-PLANNED 2026-11-26 from 3.10.0 (needs_replan channel-unresolved: 3.10.2 is the stable head).
                                      # GitHub release 3.10.2: Latest, isPrerelease=false, published 2026-11-24T09:47:34Z.
                                      # Docker Hub 2026-11-26: 3.10.2 = 3.10 = latest = index
                                      # sha256:2c4684628233e6f3aee1d8279b54cd19f420afb64b8ce6d9cc477919c234373d
                                      # (amd64 sha256:1d4ee8722307e6d052d7ff04c9cadd59ca5efedfdca817f39e29cea1b8b95607). Pin the FIXED tag.
update_type: minor
risk: low                             # admin UI (300K sqlite of saved connection definitions on a 2Gi Longhorn RWO PVC), internal-only
                                      # route, no dependents. 3.10.0 breaking changes are TLS-only / import-only and measured not to apply
                                      # (1.2); 3.10.2 adds a CORS tightening that does not affect same-origin use (1.2b). Two forward-only
                                      # sqlite migrations (3.10.0), backward-tolerant (1.3); 3.10.0 -> 3.10.2 adds none.
est_duration_min: 20                  # backup copy 2, merge+pull 2, reconcile+roll 3 (image pull ~1 min), verify 8, slack 5
needs_reboot: false
touches:
  namespaces: [databases]
  resources:                          # every object verified to EXIST live 2026-11-26
    - deployment/redisinsight         # git edit: containers[0].image 3.8.0 -> 3.10.2. ROLLS ONCE (maxSurge 0 / maxUnavailable 1:
                                      # old pod terminates first, so no RWO Multi-Attach). initContainer busybox:1.38.0 UNCHANGED.
    - pvc/redisinsight-data           # longhorn (dynamic) volume pvc-a545f6e7-2134-4b43-98b5-f0e8a3c1fe69; sqlite schema migrated on boot
    - service/redisinsight            # unchanged
    - httproute/redisinsight          # unchanged (envoy-internal, LAN-only)
    - kustomization/redisinsight      # Flux Kustomization (lives in ns databases)
    - "docker.io/redis/redisinsight"
  shared: []                          # DELIBERATE: restarts nothing shared. The server only opens client connections to the in-cluster
                                      # redis instances it already knows (read path, same as today). Verification reads Prometheus
                                      # (kube-state-metrics) -> expressed in conflicts_with, not shared.
depends_on: []
conflicts_with:                       # re-checked 2026-11-26 against every non-terminal plan naming databases/redis/monitoring/longhorn/nodes
  - kube-prometheus-stack-93.3.0      # restarts Prometheus/kube-state-metrics, the instrument the CONTROL gate in section 4 reads
  - redis-fleet-8.10.3                # rolls redis.databases / tube-archivist-redis / open-webui-redis: the three backends the
                                      # CONTENTS ASSERTION connects to; a rolling backend reads as a 3.10 regression
  - longhorn-1.13.0                   # exclusive storage-engine move; the PVC must stay attached during the roll
  - talos-linux-1.14.6                # node roll (reboot) evicts the pod mid-gate
  # redis-fleet-8.10.3 is stamped sun-attended:2026-11-29: do NOT run this plan in that window.
  # redis-fleet-8.12.0 (draft) was checked and is NOT a conflict: it touches immich-redis / sure-redis / nextcloud-redis only, none of
  #   which is a saved RedisInsight connection (the stale nextcloud-redis-master.office entry points at a Service that does not exist).
exclusive: false
security_ref: F-3a0917b0              # the OPEN security row on the CURRENT image (critical lane, last seen 2026-11-26; detail in DB only:
                                      # policy-cli finding show F-3a0917b0). Its title says a newer upstream tag exists, so this bump is its
                                      # remedy (bump, never rebuild). Whether 3.10.2 clears it is measured by the next security sweep.
capability_change: false              # FACT: no new route, listener, permission, Secret or exposure; rendered delta is one image tag.
                                      # Upstream changes REDUCE reach if anything (3.10.2 turns cross-origin API access off for the Docker
                                      # build, 1.2b). UI-only additions (Redis tools panel showing an `npx` command; Copilot retired, never
                                      # configured here) do not change what the server can reach or who can reach it.
rollback_class: git-revert            # 3.8.0 boots against the migrated sqlite (1.3); the pre-change db copy (3.1) is the belt.
finding_refs: [F-3a0917b0, F-9533cf69]   # re-queried 2026-11-26 (finding list --grep redisinsight --all): F-3a0917b0 security (open,
                                      # critical lane), F-9533cf69 version lane "3.8.0 -> 3.10.2" (open). F-75f8ab9a / F-b2efaec7 are resolved.
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-18"
replanned: "2026-11-26"               # retargeted 3.10.0 -> 3.10.2 in place (plan_id kept)
premises:
  - id: live-image-is-3.8.0
    why: "`current:` claims 3.8.0. Any other tag means the bump already landed (or the plan is mis-based): verify per section 4 and retire, do not execute."
    run: kubectl get deploy redisinsight -n databases -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "redis/redisinsight:3.8.0"
  - id: git-pin-is-3.8.0-once
    why: "Step 3.2 (PR merge or the sed fallback) changes exactly ONE image line. Zero or two matches = the file moved; re-derive the edit."
    run: "git show HEAD:kubernetes/apps/databases/redisinsight/app/deployment.yaml | grep -c '^        image: redis/redisinsight:3[.]8[.]0$'"
    expect_exact: "1"
  - id: no-surge-on-rwo
    why: "The roll is Multi-Attach-safe only because maxSurge is 0 (single replica on an RWO Longhorn PVC)."
    run: kubectl get deploy redisinsight -n databases -o jsonpath='{.spec.strategy.rollingUpdate.maxSurge}'
    expect_exact: "0"
  - id: deployment-available
    why: "Never stack a bump on an already-unavailable app; a pre-existing failure would be misread as a 3.10 regression."
    run: kubectl get deploy redisinsight -n databases -o jsonpath='{.status.availableReplicas}'
    expect_exact: "1"
  - id: flux-ks-ready
    why: "The change lands via the redisinsight Kustomization; it must be Ready before the push."
    run: kubectl get kustomization redisinsight -n databases -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: no-cors-origin-override
    why: "Section 1.2b: the 3.10.2 CORS change is harmless only because RI_CORS_ORIGIN is unset (same-origin UI). If someone sets it, re-read 1.2b."
    run: "git show HEAD:kubernetes/apps/databases/redisinsight/app/deployment.yaml | grep -c RI_CORS"
    expect_exact: "0"
---

# redisinsight 3.8.0 -> 3.10.2

## 1. Summary & why held

**What changes:** one line in `kubernetes/apps/databases/redisinsight/app/deployment.yaml`,
`image: redis/redisinsight:3.8.0` -> `image: redis/redisinsight:3.10.2`. That is exactly the
diff of Renovate PR #556 (`gh pr diff 556`, 2026-11-26). The busybox `fix-permissions`
initContainer stays `busybox:1.38.0`.

### 1.0 Re-plan 2026-11-26

This plan was first written for 3.10.0. Tonight's plan-refine flagged
`channel-unresolved` because 3.10.0 is no longer the stable head: upstream shipped
3.10.1 (Docker Hub only, 2026-11-18, no GitHub release) and 3.10.2 (GitHub release,
Latest, 2026-11-24). All five original premises still PASS (nothing landed); the work
is not applied. Target moved to 3.10.2, and the 3.10.0 -> 3.10.2 delta was read in
upstream code (1.2b, 1.3).

### 1.1 Why it was held

The coverage lane first saw the floating series tag `3.10` (fewer components than the
`3.8.0` pin, so not provably GA and would silently move). Renovate later opened #556 for
the fixed tag `3.10.2`. The fixed tag exists and is GA:

- Docker Hub (2026-11-26): `3.10.2`, `3.10` and `latest` all resolve to index digest
  `sha256:2c4684628233e6f3aee1d8279b54cd19f420afb64b8ce6d9cc477919c234373d`, pushed
  2026-11-24T09:26Z (amd64 `sha256:1d4ee872...b8b95607`).
- GitHub release `3.10.2` (redis/RedisInsight): `isPrerelease=false`, Latest:
  *"This is a patch release of Redis Insight 3.10.2, which includes bug fixes."*
- Redis Insight ships even minors only (3.0 ... 3.8, 3.10), so there is no 3.9.x.

It is also a minor bump (3.8 -> 3.10) of an image with breaking changes in its notes, so
the hold is legitimate rather than a false positive; risk stays low after measurement.

### 1.2 Upstream breaking changes (3.10.0) — quoted, and measured against our config

From the 3.10.0 release notes:

> **Breaking Change:** when "Verify TLS Certificate" is on, Redis Insight now also
> verifies that the server certificate matches the host name or IP address you connect
> to. ... Connections with "Verify TLS Certificate" turned off are not affected.

> **Breaking Change:** in Docker, Redis Stack, and the VS Code extension, importing
> databases no longer reads certificate and SSH key files from a path on the host.

Re-measured live 2026-11-26 via the in-pod API (§2.4 command): `DBS=6 TLS_OR_SSH=0`.
Neither TLS change can affect a non-TLS connection, and we do not use file-path
imports. Not applicable.

> Security hardening across the app: WebSocket connections are now authorized ...

Checked in upstream code (`redisinsight/api/src/main.ts`): the new `WindowsAuthAdapter`
(x-window-id gate) is installed only when `RI_BUILD_TYPE === 'ELECTRON'`; the image sets
`ENV RI_BUILD_TYPE='DOCKER_ON_PREMISE'` (Dockerfile at 3.10.2, line 60) and the live pod
reports `buildType=DOCKER_ON_PREMISE`. WebSockets (Pub/Sub, profiler, bulk actions) keep
`SessionMetadataAdapter`, unchanged.

### 1.2b 3.10.0 -> 3.10.2 delta (read in `compare/3.10.0...3.10.2`, 32 files)

Release notes 3.10.2: TLS cluster connections with host-name-only certificates fixed
(#6620); Pub/Sub multi-unsubscribe no longer closes the connection (#6612). Neither
touches a plain-TCP standalone connection.

Not in the notes, found in code: **CORS tightened for the Docker build.**
`api/config/default.ts` changed `origin: process.env.RI_CORS_ORIGIN ? ... : '*'` to
`origin: process.env.RI_CORS_ORIGIN`, and the new `src/common/utils/cors.util.ts`:

```ts
// The Docker API has no login, so cross-origin browser access stays off unless an origin is configured.
return { origin: buildType === BuildType.DockerOnPremise ? false : '*', credentials };
```

`main.ts` now calls `app.enableCors(getCorsOptions(...))`. Effect here: our UI is served
by the same server/port (same origin through `httproute/redisinsight`), so browser
requests are same-origin and CORS headers are irrelevant; `origin: false` in the Nest/
express `cors` middleware omits the headers, it does not reject the request. The
deployment does not set `RI_CORS_ORIGIN` (premise `no-cors-origin-override`; the only env
is `RITRUSTEDORIGINS`). Net: reduced exposure (a foreign web page can no longer read the
unauthenticated API from a LAN browser), no capability added. §4.4 includes a gate that
the API still answers a request carrying our own `Origin` header.

Dockerfile: unchanged base (`node:24.22.2-alpine` build + runtime), `EXPOSE 5540`,
`USER node`.

### 1.3 Forward-only state: sqlite migrations

`compare 3.8.0...3.10.0` adds exactly two TypeORM migrations in
`redisinsight/api/migration/`:

- `1784100000000-pipeline-draft.ts` — `CREATE TABLE "pipeline_draft"` + index
  (has a `down()`); 3.8.0 never reads it.
- `1785100000000-azure-verify-server-cert.ts` — `UPDATE database_instance SET
  verifyServerCert=1 WHERE tls=1 AND provider IN ('AZURE_CACHE',...)`; matches **0 rows**
  here (no TLS, no Azure). `down()` is a no-op.

3.10.0 -> 3.10.2 adds **none** (migration dir has 65 entries at both tags, newest
`1785100000000-azure-verify-server-cert.ts`; no migration path in the compare file list).

TypeORM on 3.8.0 only runs *pending* migrations from its own list and does not reject
extra executed rows, so a revert boots against the migrated db. Belt: §3.1 copies the
db off-cluster first; Longhorn's daily backup of the volume completed 2026-11-25T23:05Z
(`healthy`).

### 1.4 Runtime/image delta vs 3.8.0

Runtime stage `FROM node:24.16.0-alpine` -> `node:24.22.2-alpine` (same Node major).
Port 5540, `USER node`, `/data`, entrypoint unchanged. Build switched yarn->npm, so the
image is somewhat larger (disk only). Memory limit 512Mi.

### 1.5 Security driver

Cited, not described: `security_ref: F-3a0917b0` (detail in sweep_history only). Its
title states a newer upstream tag exists; bumping is the in-scope remediation.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh).

2.1 Premises: `.venv/bin/python3 runbooks/plan-premises.py redisinsight-3.10 --require-premises`
must PASS (6 premises) with no `REFUSED` line.

2.2 Target still exists and still points at the vetted digest (network check, not a premise):
```bash
curl -s https://hub.docker.com/v2/repositories/redis/redisinsight/tags/3.10.2 \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("digest"))'
```
PASS: prints `sha256:2c4684628233e6f3aee1d8279b54cd19f420afb64b8ce6d9cc477919c234373d`.
A different digest = upstream re-pushed the tag: stop and re-review. `None` = tag gone: stop.

2.3 Upstream did not ship a newer 3.10.x meanwhile (if it did, this plan needs another in-place re-plan):
```bash
gh release list -R redis/RedisInsight -L 3
curl -s 'https://hub.docker.com/v2/repositories/redis/redisinsight/tags/latest' | python3 -c 'import sys,json; print(json.load(sys.stdin).get("digest"))'
```
PASS: newest release line is `3.10.2 Latest`, and `latest` prints the same digest as 2.2.
(Docker Hub moved ahead of GitHub once before: 3.10.1 appeared on Hub with no release.)

2.3b PR #556 still carries exactly the one-line diff and is mergeable:
```bash
gh pr view 556 --json state,mergeable,mergeStateStatus -q '.state+" "+.mergeable+" "+.mergeStateStatus'
gh pr diff 556 | grep -c '^[-+] '
gh pr checks 556
```
PASS: `OPEN MERGEABLE CLEAN`, `2` (one `-`, one `+` line), all checks `pass`. If the PR is
closed, rebased onto a different tag, or not CLEAN, use the §3.2 fallback instead.

2.4 Still no TLS/SSH connection saved (the 1.2 "not applicable" depends on it):
```bash
kubectl exec -n databases deploy/redisinsight -c redisinsight -- node -e 'const B="http://localhost:5540/api";fetch(B+"/databases").then(r=>r.json()).then(async d=>{let t=0;for(const x of d){const j=await (await fetch(B+"/databases/"+x.id)).json();if(j.tls||j.ssh)t++}console.log("DBS="+d.length+" TLS_OR_SSH="+t)})'
```
PASS: `DBS=6 TLS_OR_SSH=0` (re-measured 2026-11-26). Any `TLS_OR_SSH` > 0: re-read 1.2 for that
connection before proceeding.

2.5 Baseline the CONTENTS ASSERTION (record the output; §4.3 compares against it):
```bash
kubectl exec -n databases deploy/redisinsight -c redisinsight -- node -e 'const B="http://localhost:5540/api";fetch(B+"/databases").then(r=>r.json()).then(async d=>{let ok=[];for(const x of d){const r=await fetch(B+"/databases/"+x.id+"/connect");if(r.status==200)ok.push(x.host)}console.log("CONNECT_OK="+ok.length+"/"+d.length);console.log(ok.sort().join("\n"))})'
```
Re-measured 2026-11-26: `CONNECT_OK=3/6` — `open-webui-redis.ai.svc.cluster.local`,
`redis.databases.svc.cluster.local`, `tube-archivist-redis.download.svc.cluster.local`.
The other three (`nextcloud-redis-master.office`, `paperless-ngx-redis-master.office`,
`langfuse-redis.ai`) are stale saved connections to Services that no longer exist and fail
on 3.8.0 too — pre-existing, not in scope.

2.5b Baseline the boot-line count (§4.2 compares against it):
```bash
kubectl exec -n databases deploy/redisinsight -c redisinsight -- sh -c 'cat /data/logs/redisinsight-2*.log* | grep -c "boostrap | Server is running on"'
```
Record the number as BOOTS_BEFORE. Measured 2026-11-26: `0` (grep prints 0 and exits 1;
that is the value, not an error). The app keeps only the current day's log file
(`/data/logs/redisinsight-2026-11-26.log.0` was the only one), so older boot lines rotate
away; measure BOOTS_BEFORE in the same session, immediately before §3. The string
(`boostrap` misspelled upstream) is emitted by `main.ts` L114-115 at tag 3.10.2.

2.6 Longhorn backup fresh (< 26h):
```bash
kubectl get volume pvc-a545f6e7-2134-4b43-98b5-f0e8a3c1fe69 -n storage -o jsonpath='{.status.lastBackupAt}{" "}{.status.robustness}{"\n"}'
```
PASS: timestamp within the last 26h and `healthy` (2026-11-26: `2026-11-25T23:05:41Z healthy`).
Daily backups come from `cronjob/storage/daily-backup-all-volumes` (verified to exist). If
stale, §3.1's local copy is still the restore path.

2.7 Confirm none of `conflicts_with` is scheduled into the same window
(`.venv/bin/python3 runbooks/maintenance-plan.py --open`). `redis-fleet-8.10.3` holds
`sun-attended:2026-11-29`: not that window.

## 3. Steps

3.0 Per `docs/sops/application-update.md` Step 1: drop an update marker:
```bash
runbooks/update-marker.sh add redisinsight databases 1 "3.8.0->3.10.2 upgrade"
```

3.1 Off-cluster copy of the sqlite db (read-only against the cluster; the image has `tar`):
```bash
TS=$(date +%Y%m%d_%H%M%S); POD=$(kubectl get pod -n databases -l app=redisinsight -o jsonpath='{.items[0].metadata.name}')
mkdir -p "$HOME/backups/redisinsight" && kubectl cp -c redisinsight "databases/$POD:/data/redisinsight.db" "$HOME/backups/redisinsight/redisinsight.db.$TS"
ls -l "$HOME/backups/redisinsight/redisinsight.db.$TS"
```
PASS: file exists, ~300K. Record `$TS` for §5.

3.2 Land the pin. **Primary: merge Renovate PR #556** (its diff is exactly the target edit, §2.3b):
```bash
gh pr merge 556 --squash
git pull --rebase --autostash
git log -1 --format='%h %s'
grep -n 'image: redis/redisinsight' kubernetes/apps/databases/redisinsight/app/deployment.yaml
```
PASS: the newest commit is the #556 squash, and the grep prints `        image: redis/redisinsight:3.10.2`.
Record the merge sha for §5.

**Fallback (only if §2.3b failed):** edit + commit by hand (BSD sed, dry-tested on a scratch
copy 2026-11-26):
```bash
sed -i '' 's|^        image: redis/redisinsight:3\.8\.0$|        image: redis/redisinsight:3.10.2|' \
  kubernetes/apps/databases/redisinsight/app/deployment.yaml
git diff kubernetes/apps/databases/redisinsight/app/deployment.yaml
git commit --only kubernetes/apps/databases/redisinsight/app/deployment.yaml \
  -m "feat(redisinsight): 3.8.0 -> 3.10.2 (plan redisinsight-3.10)"
git log -1 --format=%s     # must be the subject above; amend before push if not
git show --stat HEAD       # exactly one file
git push
```
Expected diff (exactly this):
```
-        image: redis/redisinsight:3.8.0
+        image: redis/redisinsight:3.10.2
```
Then close #556 with a comment pointing at the commit.

The Flux webhook reconciles; no manual `flux reconcile` (only if nothing has moved after
5 min: `flux reconcile kustomization redisinsight -n databases --with-source`).

3.3 Watch the roll (old pod terminates first, then the new one pulls and starts):
```bash
kubectl rollout status deploy/redisinsight -n databases --timeout=5m
```

## 4. Verification

`rollout status` can green-light the old generation, so each gate reads the live pod.

4.1 Live pod runs the vetted digest:
```bash
kubectl get pod -n databases -l app=redisinsight -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.containerStatuses[0].imageID}{" "}{.status.containerStatuses[0].ready}{"\n"}{end}'
```
PASS: exactly ONE line, ending `@sha256:2c4684628233e6f3aee1d8279b54cd19f420afb64b8ce6d9cc477919c234373d true`
(the 3.8.0 pod reports the INDEX digest the same way, measured 2026-11-26).
FAIL looks like: the 3.8.0 digest `sha256:b5e19ee2...` (old generation still serving), two lines
(roll in progress), or `false`. If it shows the amd64 digest `sha256:1d4ee872...b8b95607`
instead, that is the same image: PASS.

4.2 App reports the new version and boots cleanly (POSITIVE gates first, absence counts second):
```bash
kubectl exec -n databases deploy/redisinsight -c redisinsight -- node -e 'fetch("http://localhost:5540/api/info").then(r=>r.json()).then(j=>console.log("appVersion="+j.appVersion+" buildType="+j.buildType))'
kubectl exec -n databases deploy/redisinsight -c redisinsight -- sh -c 'cat /data/logs/redisinsight-2*.log* | grep -c "boostrap | Server is running on"'
kubectl exec -n databases deploy/redisinsight -c redisinsight -- sh -c 'cat /data/logs/redisinsight-2*.log* | grep -i -c -e QueryFailedError -e SQLITE_ -e migration'
kubectl exec -n databases deploy/redisinsight -c redisinsight -- sh -c 'cat /data/logs/redisinsight-errors-*.log* | grep -i -c -e QueryFailedError -e SQLITE_ -e migration'
```
PASS (all): line 1 prints `appVersion=3.10.2 buildType=DOCKER_ON_PREMISE` (`appVersion` default
is `'3.10.2'` in `config/default.ts` at the tag); line 2 equals BOOTS_BEFORE + 1 (TypeORM runs
pending migrations before the Nest app listens, so this line only appears if the migrations
completed); lines 3 and 4 print `0`.
FAIL: `appVersion=3.8.0` or an empty/errored line 1; line 2 equal to BOOTS_BEFORE (old pod, or the
new one died before listening); a non-zero line 3/4. Lines 3/4 alone are never sufficient (a
missing log file also prints 0); line 2 is the gate that can fail while they read 0.
Why these files: container stdout carries only `Running docker-entry.sh`; RedisInsight writes its
own log to `/data/logs/redisinsight-<date>.log.0` and ERROR-level lines to
`/data/logs/redisinsight-errors-<date>.log.0`. The errors file already holds
`DatabaseClientFactory`/`IoredisRedisConnectionStrategy` lines from the three stale connections
(§2.5); those are expected to grow after §4.3 and are not counted.

4.3 **CONTENTS ASSERTION: the saved connection set survived the schema migration and the new
runtime can still talk to every reachable backend** — re-run the §2.5 command. PASS:
`CONNECT_OK=3/6` with the identical three hostnames. This fails if the sqlite were empty/reset
(`CONNECT_OK=0/0` — `/api/databases` returns `[]` on a fresh db, which every shape check above
still passes), if the migration corrupted `database_instance` (fewer rows / 500s), or if the
changed connection-strategy code (#6620 touched `ioredis.redis.connection.strategy.ts`) regressed
plain connections (`3/6` -> lower).

4.4 Through the real edge (LAN, envoy-internal) — the UI and API serve, including with our own Origin header (1.2b):
```bash
H=$(kubectl get httproute redisinsight -n databases -o jsonpath='{.spec.hostnames[0]}')
curl -s -o /dev/null -w '%{http_code}\n' "https://$H/api/health"
curl -s "https://$H/" | grep -i -c '<div id="root"'
curl -s -o /dev/null -w '%{http_code}\n' -H "Origin: https://$H" "https://$H/api/databases"
```
PASS: `200`, a count >= 1, `200`. FAIL: 503/000 (route lost its backend), 0 (an error page, not
the SPA shell), or a 403/4xx on line 3 (the CORS change rejecting same-origin requests, which the
code reading in 1.2b says it does not). Then a browser check in Chrome: open the UI, open the
`redis.databases` connection, Browser tab lists keys (this exercises the real same-origin fetch +
WebSocket path the curl cannot).

4.5 No restarts after the roll, replica available:

CONTROL: metric kube_deployment_status_replicas_available — `{namespace="databases",deployment="redisinsight"}` must read `1` at T+5 min (reads 0 during a crash loop).
CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="databases",container="redisinsight"}` for the NEW pod name must read `0` at T+5 min (old pod reads 2, so the series is scraped and non-empty).

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://localhost:19090/api/v1/query --data-urlencode 'query=kube_deployment_status_replicas_available{namespace="databases",deployment="redisinsight"}' | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print("AVAIL="+(r[0]["value"][1] if r else "EMPTY"))'
curl -s http://localhost:19090/api/v1/query --data-urlencode 'query=kube_pod_container_status_restarts_total{namespace="databases",container="redisinsight"}' | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print([(x["metric"]["pod"],x["value"][1]) for x in r] or "EMPTY")'
kill $PF 2>/dev/null
```
PASS: `AVAIL=1` and the new pod's restarts `0`. `EMPTY` is a FAIL of the instrument, not a pass
— fall back to `kubectl get pod -n databases -l app=redisinsight` RESTARTS column and note it.

4.6 Close-out: `runbooks/update-marker.sh clear redisinsight`. Plan retirement per the plans
README. F-9533cf69 / F-3a0917b0 are sweep-owned and re-evaluated by the next sweep.

## 5. Rollback

Trigger: any §4 gate fails and is not explained within 10 minutes.

5.1 Revert the pin:
```bash
git revert --no-edit <sha-from-3.2>
git log -1 --format=%s; git show --stat HEAD    # one file, subject "Revert ..."
git push
kubectl rollout status deploy/redisinsight -n databases --timeout=5m
```
Confirm: §4.1 shows digest `sha256:b5e19ee240abef6edb435871b90ff8a210995422e8e018ab61c0339d318a1f84`,
§4.2 shows `appVersion=3.8.0`, §2.5 shows the baseline `CONNECT_OK=3/6`. Renovate will reopen a PR
for the tag; leave it, this plan stays the gate.

5.2 Only if 3.8.0 then fails to read the db (not expected, see 1.3) — restore the §3.1 copy.
This is app data on a PVC with no GitOps path (CLAUDE.md in-pod exception applies):
```bash
POD=$(kubectl get pod -n databases -l app=redisinsight -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n databases "$POD" -c redisinsight -- cp /data/redisinsight.db "/data/redisinsight.db.backup.$(date +%Y%m%d_%H%M%S)"
kubectl cp -c redisinsight "$HOME/backups/redisinsight/redisinsight.db.<TS>" "databases/$POD:/data/redisinsight.db"
kubectl delete pod -n databases "$POD"    # Deployment recreates it on the same PVC; the app re-reads the restored db
kubectl rollout status deploy/redisinsight -n databases --timeout=5m
```
Then re-run §2.5 and expect `CONNECT_OK=3/6`. Last resort: restore the Longhorn backup of volume
`pvc-a545f6e7-2134-4b43-98b5-f0e8a3c1fe69` per `docs/sops/backup.md` (data loss window: since the
last 23:00 UTC backup — at most saved-connection edits, which do not happen unattended).

Report the in-pod restore and the backup path if 5.2 was used.

## 6. Interference notes

- Single Deployment in `databases`; no other workload mounts `redisinsight-data`; nothing
  depends on redisinsight (admin UI only). Homepage tile is read from the unchanged HTTPRoute.
- The roll is safe on RWO because `maxSurge: 0` (premise `no-surge-on-rwo`); expect ~1 min of
  UI downtime while the old pod terminates and 3.10.2 pulls.
- `conflicts_with` carries: `kube-prometheus-stack-93.3.0` (the 4.5 instrument),
  `redis-fleet-8.10.3` (rolls the three backends 4.3 connects to; stamped
  sun-attended:2026-11-29), `longhorn-1.13.0` (exclusive storage move),
  `talos-linux-1.14.6` (node reboots). `redis-fleet-8.12.0` checked and excluded (different redises).
- PR #556 is still open 8 days after Renovate opened it (2026-11-18), i.e. Step 0 has not
  auto-merged it. Merging it is step 3.2. If Step 0 of the same window lands it first, premise
  `live-image-is-3.8.0` fails: verify per §4 and retire the plan instead of re-applying.
- Repo correction (version-detection lane, not this window): the coverage lane proposed the
  floating `3.10` tag although a fixed sibling with the identical digest existed; it should prefer
  the full-semver sibling of a floating tag. Also: `plan-refine` raised `channel-unresolved` here
  while the actual condition was "a newer patch on the same minor shipped"; the message
  ("could not confirm 3.10.2 is the stable-channel head") reads as an upstream ambiguity rather than
  "your target is stale".
