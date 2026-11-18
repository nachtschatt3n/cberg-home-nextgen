---
plan_id: redisinsight-3.10
component: redisinsight
pr: null                              # no open Renovate PR (gh pr list --search redisinsight: empty, 2026-11-18). Held by the
                                      # coverage/direct-bump lane: the detected target was the FLOATING series tag `3.10`.
kind: image
current: "3.8.0"                      # MEASURED 2026-11-18: deploy/redisinsight image redis/redisinsight:3.8.0, pod
                                      # redisinsight-5c8979657d-q6h9q 1/1 on k8s-nuc14-03, imageID
                                      # sha256:b5e19ee240abef6edb435871b90ff8a210995422e8e018ab61c0339d318a1f84 (= Docker Hub 3.8.0 index digest)
target: "3.10.0"                      # FIXED tag, not the floating `3.10`. Docker Hub 2026-11-18: 3.10.0, 3.10 and latest all =
                                      # index sha256:f00fdc1de63baad22ad2c3eeceede2bcf8859db0b45657033ea70e354f6b9173
                                      # (amd64 sha256:20f1c285583516d7cd169c731a6ed60444e813d41918238d096154215752b5a6).
                                      # GitHub release 3.10.0: published 2026-11-17T13:51:39Z, isPrerelease=false, "General Availability".
update_type: minor
risk: low                             # stateless-ish admin UI (300K sqlite of saved connection definitions on a 2Gi Longhorn RWO PVC),
                                      # internal-only route, no dependents. Both upstream breaking changes are TLS-only / import-only and
                                      # measured not to apply (1.2). Two forward-only sqlite migrations, both backward-tolerant (1.3).
est_duration_min: 20                  # backup copy 2, commit+push 2, reconcile+Recreate-style roll 3 (image pull ~1 min), verify 8, slack 5
needs_reboot: false
touches:
  namespaces: [databases]
  resources:                          # every object verified to EXIST live 2026-11-18
    - deployment/redisinsight         # git edit: containers[0].image 3.8.0 -> 3.10.0. ROLLS ONCE (maxSurge 0 / maxUnavailable 1:
                                      # old pod terminates first, so no RWO Multi-Attach). initContainer busybox:1.38.0 UNCHANGED.
    - pvc/redisinsight-data           # longhorn (dynamic) volume pvc-a545f6e7-2134-4b43-98b5-f0e8a3c1fe69; sqlite schema migrated on boot
    - service/redisinsight            # unchanged
    - httproute/redisinsight          # unchanged (envoy-internal, LAN-only)
    - kustomization/redisinsight      # Flux Kustomization (lives in ns databases)
    - "docker.io/redis/redisinsight"
  shared: []                          # DELIBERATE: restarts nothing shared. The 3.10 server only opens client connections to the
                                      # in-cluster redis instances it already knows (read path, same as today). Verification reads
                                      # Prometheus (kube-state-metrics) -> expressed in conflicts_with, not shared.
depends_on: []
conflicts_with:                       # checked 2026-11-18 against every non-terminal plan naming databases/redis/monitoring/longhorn/nodes
  - kube-prometheus-stack-93.3.0      # restarts Prometheus/kube-state-metrics, the instrument the CONTROL gate in section 4 reads
  - redis-fleet-8.10.3                # rolls redis.databases / tube-archivist-redis / open-webui-redis: the three backends the
                                      # CONTENTS ASSERTION connects to; a rolling backend reads as a 3.10 regression
  - longhorn-1.13.0                   # exclusive storage-engine move; the PVC must stay attached during the roll
  - talos-linux-1.14.6                # node roll (reboot) evicts the pod mid-gate
exclusive: false
security_ref: F-75f8ab9a              # security row on the CURRENT image (detail in DB only: policy-cli finding show F-75f8ab9a).
                                      # It is ACCEPTED under AR-029 "already on the newest upstream tag" -- that premise became false
                                      # on 2026-11-17 when 3.10.0 shipped. This bump is the remediation we perform (bump, never rebuild).
                                      # Whether 3.10.0 clears the count is measured by the next security sweep, not asserted here.
capability_change: false              # FACT: no new route, listener, permission, Secret or exposure; rendered delta is one image tag.
                                      # Upstream UI changes (a "Redis tools" panel that only DISPLAYS an `npx` setup command to run on
                                      # the user's own machine; the cloud-login-only Copilot chat retired -- never configured here) do
                                      # not change what the server can reach or who can reach it. Stricter TLS verification is a
                                      # behaviour change only for TLS connections, of which there are zero (1.2). Reviewer may contest.
rollback_class: git-revert            # 3.8.0 boots against the migrated sqlite (1.3); the pre-change db copy (3.1) is the belt.
finding_refs: [F-75f8ab9a]            # the only sweep finding for this component (finding list --grep redisinsight, 2026-11-18).
                                      # Script-owned: re-evaluated by security-check on the next sweep after the pin moves.
review: null
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-18"
premises:
  - id: live-image-is-3.8.0
    why: "`current:` claims 3.8.0. Any other tag means the bump already landed (or the plan is mis-based): verify per section 4 and retire, do not execute."
    run: kubectl get deploy redisinsight -n databases -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "redis/redisinsight:3.8.0"
  - id: git-pin-is-3.8.0-once
    why: "The step 3.2 sed targets exactly ONE image line. Zero or two matches = the file moved; re-derive the edit."
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
---

# redisinsight 3.8.0 -> 3.10.0

## 1. Summary & why held

**What changes:** one line in `kubernetes/apps/databases/redisinsight/app/deployment.yaml`,
`image: redis/redisinsight:3.8.0` -> `image: redis/redisinsight:3.10.0`. Nothing else
(the busybox `fix-permissions` initContainer stays `busybox:1.38.0`; it is not part of
this group).

### 1.1 Why it was held — and why the hold is resolved by pinning the fixed tag

The detector saw target `3.10`, which has fewer version components than the pin
`3.8.0` — a floating series pointer that cannot be shown GA and would silently move.
Resolved: the fixed tag **`3.10.0` exists** and is GA.

- Docker Hub (2026-11-18): `3.10.0`, `3.10` and `latest` all resolve to index digest
  `sha256:f00fdc1de63baad22ad2c3eeceede2bcf8859db0b45657033ea70e354f6b9173`, pushed
  2026-11-17T13:44Z (per-arch `3.10.0-amd64` = `sha256:20f1c285…52b5a6`).
- GitHub release `3.10.0` (redis/RedisInsight): `isPrerelease=false`, marked Latest,
  body: *"This is the General Availability (GA) release of Redis Insight 3.10.0"*.
- There is no 3.9.x (Redis Insight ships even minors only: 3.0, 3.2, 3.4, 3.6, 3.8, 3.10).

So the hold was a false positive about the *tag form*, not about the release. The plan
pins `3.10.0`, never `3.10`.

### 1.2 Upstream breaking changes — quoted, and measured against our config

From the 3.10.0 release notes:

> **Breaking Change:** when "Verify TLS Certificate" is on, Redis Insight now also
> verifies that the server certificate matches the host name or IP address you connect
> to. Connections to a server by IP address with a certificate issued only for a host
> name will fail. … Connections with "Verify TLS Certificate" turned off are not affected.

> "Verify TLS Certificate" turned off is now honored: previously the certificate was
> still verified in this case.

> **Breaking Change:** in Docker, Redis Stack, and the VS Code extension, importing
> databases no longer reads certificate and SSH key files from a path on the host.

Measured live 2026-11-18 via the in-pod API (`GET /api/databases/<id>` for each of the
6 saved connections): **every connection is `tls=false`, `verifyServerCert=null`,
`ssh=false`**. Neither TLS change can affect a non-TLS connection, and we do not use
file-path imports. Not applicable.

> Security hardening across the app: WebSocket connections are now authorized …

Checked in upstream code (tag 3.10.0, `redisinsight/api/src/main.ts` L76-103): the new
`WindowsAuthAdapter` (x-window-id gate, PR #6225) is installed only when
`RI_BUILD_TYPE === 'ELECTRON'`; for any other build type it uses
`SessionMetadataAdapter`, as before. The image sets
`ENV RI_BUILD_TYPE='DOCKER_ON_PREMISE'` (Dockerfile, unchanged) and the live pod reports
`buildType=DOCKER_ON_PREMISE` from `/api/info`. WebSockets (Pub/Sub, profiler, bulk
actions) are unaffected. Had this branch gone the other way, the web UI would lose every
socket feature — the reason it was checked in code rather than assumed.

"Redis Copilot is retired" — needs a Redis Cloud login; not configured here.

### 1.3 Forward-only state: sqlite migrations

`git compare 3.8.0...3.10.0` adds exactly two TypeORM migrations in
`redisinsight/api/migration/`:

- `1784100000000-pipeline-draft.ts` — `CREATE TABLE "pipeline_draft"` + index
  (has a `down()`); 3.8.0 never reads it.
- `1785100000000-azure-verify-server-cert.ts` — `UPDATE database_instance SET
  verifyServerCert=1 WHERE tls=1 AND provider IN ('AZURE_CACHE',…)`; matches **0 rows**
  here (no TLS, no Azure). `down()` is a no-op.

TypeORM on 3.8.0 only runs *pending* migrations from its own list and does not reject
extra executed rows, so a revert boots against the migrated db. Belt: §3.1 copies the
db off-cluster first; Longhorn's daily backup of the volume completed 2026-11-17T23:02Z.

### 1.4 Runtime/image delta

Dockerfile runtime stage diff 3.8.0 -> 3.10.0 is one line: `FROM node:24.16.0-alpine`
-> `FROM node:24.22.2-alpine` (same Node major). Port 5540, `USER node`, `/data`,
entrypoint unchanged. Build switched yarn->npm and dropped `autoclean`, so the image is
somewhat larger (disk only). Current usage 181Mi of a 512Mi limit.

### 1.5 Security driver

Cited, not described: `security_ref: F-75f8ab9a` (detail in sweep_history only). That
row is accepted under AR-029 on the premise "already on the newest upstream tag", which
stopped being true when 3.10.0 was published — bumping is the remediation in scope.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh).

2.1 Premises: `.venv/bin/python3 runbooks/plan-premises.py redisinsight-3.10 --require-premises`
must PASS with no `REFUSED` line.

2.2 Target still exists and still points at the vetted digest (network check, not a premise):
```bash
curl -s https://hub.docker.com/v2/repositories/redis/redisinsight/tags/3.10.0 \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("digest"))'
```
PASS: prints `sha256:f00fdc1de63baad22ad2c3eeceede2bcf8859db0b45657033ea70e354f6b9173`.
A different digest = upstream re-pushed the tag: stop and re-review. `None` = tag gone: stop.

2.3 Upstream did not ship a 3.10.x patch meanwhile (if it did, retarget this plan in place):
```bash
gh release list -R redis/RedisInsight -L 3
```
PASS: newest line is `3.10.0`.

2.4 Still no TLS/SSH connection saved (the 1.2 "not applicable" depends on it):
```bash
kubectl exec -n databases deploy/redisinsight -c redisinsight -- node -e 'const B="http://localhost:5540/api";fetch(B+"/databases").then(r=>r.json()).then(async d=>{let t=0;for(const x of d){const j=await (await fetch(B+"/databases/"+x.id)).json();if(j.tls||j.ssh)t++}console.log("DBS="+d.length+" TLS_OR_SSH="+t)})'
```
PASS: `DBS=6 TLS_OR_SSH=0` (measured 2026-11-18). Any `TLS_OR_SSH` > 0: re-read 1.2 for that
connection (set its TLS server name) before proceeding.

2.5 Baseline the CONTENTS ASSERTION (record the output; §4.3 compares against it):
```bash
kubectl exec -n databases deploy/redisinsight -c redisinsight -- node -e 'const B="http://localhost:5540/api";fetch(B+"/databases").then(r=>r.json()).then(async d=>{let ok=[];for(const x of d){const r=await fetch(B+"/databases/"+x.id+"/connect");if(r.status==200)ok.push(x.host)}console.log("CONNECT_OK="+ok.length+"/"+d.length);console.log(ok.sort().join("\n"))})'
```
Measured 2026-11-18: `CONNECT_OK=3/6` — `open-webui-redis.ai…`, `redis.databases…`,
`tube-archivist-redis.download…` succeed. The other three (`nextcloud-redis-master.office`,
`paperless-ngx-redis-master.office`, `langfuse-redis.ai`) are **stale saved connections to
services that no longer exist** (`kubectl get svc` NotFound) and return 424 on 3.8.0 too —
pre-existing, not a regression, not in scope (operator may delete them in the UI later).

2.6 Longhorn backup fresh (< 26h):
```bash
kubectl get volume pvc-a545f6e7-2134-4b43-98b5-f0e8a3c1fe69 -n storage -o jsonpath='{.status.lastBackupAt}{" "}{.status.robustness}{"\n"}'
```
PASS: timestamp within the last 26h and `healthy`. (Daily backups come from
`cronjob/storage/daily-backup-all-volumes`.) If stale, §3.1's local copy is still the restore path.

2.7 Confirm none of `conflicts_with` is scheduled into the same window
(`.venv/bin/python3 runbooks/maintenance-plan.py --open`).

## 3. Steps

3.0 Per `docs/sops/application-update.md` Step 1: drop an update marker (and optionally a
4h silence scoped to `namespace=databases`):
```bash
runbooks/update-marker.sh add redisinsight databases 1 "3.8.0->3.10.0 upgrade"
```

3.1 Off-cluster copy of the sqlite db (read-only against the cluster; the image has `tar`):
```bash
TS=$(date +%Y%m%d_%H%M%S); POD=$(kubectl get pod -n databases -l app=redisinsight -o jsonpath='{.items[0].metadata.name}')
mkdir -p "$HOME/backups/redisinsight" && kubectl cp -c redisinsight "databases/$POD:/data/redisinsight.db" "$HOME/backups/redisinsight/redisinsight.db.$TS"
ls -l "$HOME/backups/redisinsight/redisinsight.db.$TS"
```
PASS: file exists, ~300K (live: 308K). Record `$TS` for §5.

3.2 Edit the pin (dry-tested on a scratch copy with BSD sed 2026-11-18):
```bash
sed -i '' 's|^        image: redis/redisinsight:3\.8\.0$|        image: redis/redisinsight:3.10.0|' \
  kubernetes/apps/databases/redisinsight/app/deployment.yaml
git diff kubernetes/apps/databases/redisinsight/app/deployment.yaml
```
Expected diff (exactly this, nothing else):
```
-        image: redis/redisinsight:3.8.0
+        image: redis/redisinsight:3.10.0
```

3.3 Commit only this path and push (shared worktree rules):
```bash
git commit --only kubernetes/apps/databases/redisinsight/app/deployment.yaml \
  -m "feat(redisinsight): 3.8.0 -> 3.10.0 (fixed tag; plan redisinsight-3.10)"
git log -1 --format=%s     # must be the subject above; amend before push if not
git show --stat HEAD       # exactly one file
git push
```
The Flux webhook reconciles; no manual `flux reconcile` (the Kustomization interval is 30m —
only if nothing has moved after 5 min, `flux reconcile kustomization redisinsight -n databases --with-source`).

3.4 Watch the roll (old pod terminates first, then the new one pulls and starts):
```bash
kubectl rollout status deploy/redisinsight -n databases --timeout=5m
```

## 4. Verification

`rollout status` can green-light the old generation, so each gate reads the live pod.

4.1 Live pod runs the vetted digest:
```bash
kubectl get pod -n databases -l app=redisinsight -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.containerStatuses[0].imageID}{" "}{.status.containerStatuses[0].ready}{"\n"}{end}'
```
PASS: exactly ONE line, ending `@sha256:f00fdc1de63baad22ad2c3eeceede2bcf8859db0b45657033ea70e354f6b9173 true`.
FAIL looks like: the 3.8.0 digest `sha256:b5e19ee2…` (old generation still serving), two lines
(roll in progress), or `false`.

4.2 App reports the new version and boots cleanly:
```bash
kubectl exec -n databases deploy/redisinsight -c redisinsight -- node -e 'fetch("http://localhost:5540/api/info").then(r=>r.json()).then(j=>console.log("appVersion="+j.appVersion+" buildType="+j.buildType))'
kubectl exec -n databases deploy/redisinsight -c redisinsight -- sh -c 'cat /data/logs/redisinsight-errors-*.log* | grep -i -c -e QueryFailedError -e SQLITE_ -e migration'
kubectl logs -n databases deploy/redisinsight -c redisinsight | grep -i -c -e QueryFailedError -e SQLITE_ -e migration -e error
```
PASS: `appVersion=3.10.0 buildType=DOCKER_ON_PREMISE`, and both counts `0`.
Why these files: the app's container stdout carries only `Running docker-entry.sh`
(measured — a stdout grep alone reads 0 whatever happens); RedisInsight writes its own log to
`/data/logs/redisinsight-<date>.log.0` and ERROR-level lines to
`/data/logs/redisinsight-errors-<date>.log.0` (format `| ERROR | <Context> | ...`). Baseline
2026-11-18: migration/sqlite count `0`; the errors file does hold 24 lines from
`DatabaseClientFactory`/`IoredisRedisConnectionStrategy` — those are the three stale
connections (§2.5) being probed and are expected to grow after §4.3; do not count them.
FAIL looks like `appVersion=3.8.0` (old pod) or a non-zero count — a failed TypeORM migration
logs `QueryFailedError`/`SQLITE_*`; a bootstrap crash prints to stdout and also surfaces as
restarts in 4.5.

4.3 **CONTENTS ASSERTION: the saved connection set survived the schema migration and the
new runtime can still talk to every reachable backend** — measured by re-running the §2.5
command, compared to the §2.5 baseline. PASS: `CONNECT_OK=3/6` with the identical three
hostnames. This would fail if the sqlite were empty/reset (`CONNECT_OK=0/0` — `/api/databases`
returns `[]` on a fresh db, which every shape check above still passes), if the migration
corrupted `database_instance` (fewer rows / 500s), or if the stricter TLS/connection code
regressed plain connections (`3/6` -> lower). `DBS` must still be 6.

4.4 Through the real edge (LAN, envoy-internal) — the UI and API serve:
```bash
H=$(kubectl get httproute redisinsight -n databases -o jsonpath='{.spec.hostnames[0]}')
curl -s -o /dev/null -w '%{http_code}\n' "https://$H/api/health"
curl -s "https://$H/" | grep -i -c '<div id="root"'
```
PASS: `200` and a count >= 1 (both measured on 3.8.0 2026-11-18). FAIL: 503/000 (route lost its backend) or 0 (an error page, not
the SPA shell). Optional Chrome check: open the UI, open the `redis.databases` connection,
Browser tab lists keys.

4.5 No restarts after the roll, replica available:

CONTROL: metric kube_deployment_status_replicas_available — `{namespace="databases",deployment="redisinsight"}` must read `1` at T+5 min (live 2026-11-18: 1; reads 0 during a crash loop).
CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="databases",container="redisinsight"}` for the NEW pod name must read `0` at T+5 min (old pod read 2, so the series is scraped and non-empty).

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://localhost:19090/api/v1/query --data-urlencode 'query=kube_deployment_status_replicas_available{namespace="databases",deployment="redisinsight"}' | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print("AVAIL="+(r[0]["value"][1] if r else "EMPTY"))'
curl -s http://localhost:19090/api/v1/query --data-urlencode 'query=kube_pod_container_status_restarts_total{namespace="databases",container="redisinsight"}' | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print([(x["metric"]["pod"],x["value"][1]) for x in r] or "EMPTY")'
kill $PF 2>/dev/null
```
PASS: `AVAIL=1` and the new pod's restarts `0`. `EMPTY` is a FAIL of the instrument, not a pass
— fall back to `kubectl get pod -n databases -l app=redisinsight` RESTARTS column and note it.

4.6 Close-out: `runbooks/update-marker.sh clear redisinsight`; delete any silence. Plan
retirement (delete this file in the landing commit or a follow-up) per the plans README.

## 5. Rollback

Trigger: any §4 gate fails and is not explained within 10 minutes.

5.1 Revert the pin:
```bash
git revert --no-edit <sha-of-3.3-commit>
git log -1 --format=%s; git show --stat HEAD    # one file, subject "Revert ..."
git push
kubectl rollout status deploy/redisinsight -n databases --timeout=5m
```
Confirm: §4.1 shows digest `sha256:b5e19ee240abef6edb435871b90ff8a210995422e8e018ab61c0339d318a1f84`,
§4.2 shows `appVersion=3.8.0`, §2.5 shows the baseline `CONNECT_OK=3/6`.

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
`pvc-a545f6e7-2134-4b43-98b5-f0e8a3c1fe69` per `docs/sops/backup.md` (data loss window: since
2026-11-17T23:02Z — at most saved-connection edits, which do not happen unattended).

Report the in-pod restore and the backup path if 5.2 was used.

## 6. Interference notes

- Single Deployment in `databases`; no other workload mounts `redisinsight-data`; nothing
  depends on redisinsight (admin UI only). Homepage tile is read from the unchanged HTTPRoute.
- The roll is safe on RWO because `maxSurge: 0` (premise `no-surge-on-rwo`); expect ~1 min of
  UI downtime while the old pod terminates and 3.10.0 pulls.
- `conflicts_with` carries: `kube-prometheus-stack-93.3.0` (the 4.5 instrument),
  `redis-fleet-8.10.3` (rolls the three backends 4.3 connects to — run either order, not the same
  night), `longhorn-1.13.0` (exclusive storage move), `talos-linux-1.14.6` (node reboots).
  None of those plans needs to list this one back for correctness, but the window agent should
  add the reciprocal refs when it next edits them.
- After landing, the next security sweep re-evaluates F-75f8ab9a on the new image; the AR-029
  "already newest" acceptance no longer applies to 3.8.0 either way.
- Repo correction (for the version-detection lane, not this window): the detector proposed the
  floating `3.10` tag although a fixed `3.10.0` with the identical digest was published
  alongside it; it should prefer the full-semver sibling of a floating tag.
