---
plan_id: nextcloud-whiteboard-2.1.2
component: nextcloud-whiteboard
pr: null                              # no Renovate PR open (gh pr list --search whiteboard -> []); coverage needs_plan_groups, direct bump
kind: image
current: "v2.0.0"
target: "v2.1.2"                      # GHCR OCI index sha256:fd714528ae29beb9e9ad56589c031f7c6c688979b5e0cfbba7bb546cf75a0e43 (verified 2026-10-23; retargeted from v2.1.0; v2.1.2 published 2026-10-23T08:14Z = under a day old)
update_type: minor
risk: low                             # the hold is a FALSE POSITIVE of the *nextcloud* glob (§1.2); stateless node websocket server, no PVC, no occ
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - deployment/nextcloud-whiteboard   # image tag only (kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml); one pod roll
                                        # Applied by Flux Kustomization office/nextcloud, which also owns helmrelease/nextcloud --
                                        # the HelmRelease spec is NOT changed by this commit, so helm-controller does not upgrade it.
  shared: [monitoring]                  # READ-only: §2/§4 read Prometheus (the window's instrument). No Gateway/HTTPRoute,
                                        # cert-manager, cilium, coredns, Longhorn or CIFS change. httproute/nextcloud-whiteboard
                                        # (envoy-external) is read by §4, not modified.
depends_on: []
conflicts_with:
  - nextcloud-9.4.1                    # exporter bump: same Kustomization office/nextcloud (its commit edits helmrelease.yaml, so
                                        # helm-controller upgrades the nextcloud release) and the same Prometheus reads; one change per
                                        # night keeps "what restarted" unambiguous. Reciprocal entry added there 2026-10-23.
  - redis-fleet-8.10.3                 # (retargeted 2026-10-27 from superseded 8.10.2) restarts nextcloud + nextcloud-redis (sat-attended:2026-10-24): the §2.2b/§4.3 `occ` execs
                                        # into deploy/nextcloud would hit a restarting pod (false STOP / false FAIL)
  - nextcloud-mcp-0.202.1              # same office namespace; separate Deployment, serialize to keep §4 attributable
  # Removed 2026-10-23 (no such plan exists any more): nextcloud-fleet-35.0.1 (executed, file retired),
  # kube-prometheus-stack-92.10.1 and -92.2.0 (retired). §2.4/§4.5 read Prometheus: if a kube-prometheus-stack
  # bump is ever planned for the same night, add it here.
exclusive: false
security_ref: F-ba1774e1              # security driver, tracked on the record (detail stays in sweep_findings); see §1.4.
capability_change: false              # websocket-server-only bump: bug fixes (disconnect ordering, presenter-end logic,
                                        # Redis URL parsing for a strategy we do not use) + node base 26.8.2 -> 26.12.0.
                                        # The user-visible "open whiteboards in the viewer / NC36" feature ships in the
                                        # Nextcloud APP 2.1.0, which is already live; this plan installs no app update (§1.3).
rollback_class: git-revert            # nothing forward-only: STORAGE_STRATEGY=lru (in-memory), no PVC, no DB, no occ
finding_refs: [F-3cb96208, F-ba1774e1, F-1c66e9e5, F-cc2aa0f5]
                                        # F-3cb96208 version finding (the sweep retargets it to 2.1.2); F-ba1774e1 security
                                        # driver; F-1c66e9e5 + F-cc2aa0f5 its acceptance records. Detail stays on the records.
review: ready-for-go@2026-10-23      # delta plan-reviewer 2026-10-23: ready-for-go once the redaction + 4.6 control below landed
status: vetted
window: "nightly:2026-10-29"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/maintenance-windows.md
  - docs/sops/verification-contents-not-shape.md
premises:
  - id: image-is-still-v2.0.0
    why: >-
      current: and the rollback target are v2.0.0 (index digest sha256:05959663...). If the
      manifest has moved, the sed in §3 matches nothing and the rollback digest is wrong.
    run: kubectl get deploy -n office nextcloud-whiteboard -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/nextcloud-releases/whiteboard:v2.0.0
  - id: storage-strategy-still-lru
    why: >-
      rollback_class git-revert and "no data at rest" rest on STORAGE_STRATEGY=lru (in-memory
      room cache; boards persist in Nextcloud files). If someone switched to redis, the 2.1.0
      RedisAdapter change (comma-split REDIS_URL) becomes live and this plan must be re-reviewed.
    run: kubectl get deploy -n office nextcloud-whiteboard -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="STORAGE_STRATEGY")].value}'
    expect_exact: lru
  - id: server-pod-digest-is-v2.0.0
    why: "Rollback target on record: the running pod is the v2.0.0 index digest, so `git revert` restores exactly what ran."
    run: kubectl get pods -n office -l app=nextcloud-whiteboard -o jsonpath='{.items[0].status.containerStatuses[0].imageID}'
    expect_contains: sha256:059596633333d009890c64858f89f133ccd973a2e0823ad960a0cc05cf8657f1
  - id: no-active-whiteboard-rooms
    why: >-
      The pod roll drops every open socket; with lru storage a user mid-edit can lose the last
      unsaved seconds. Zero active rooms = no one is editing = no data at risk. Read from the
      server's own /status counter (measured 0 rooms / 0 clients on 2026-10-21).
    run: kubectl get --raw /api/v1/namespaces/office/services/nextcloud-whiteboard:3002/proxy/status | jq -r .metrics.rooms.activeRooms
    expect_exact: "0"
  - id: nextcloud-release-ready
    why: >-
      Do not roll anything in office while a Nextcloud upgrade is mid-flight or failed
      (the 35.0.2 upgrade executed 2026-10-23; HelmRelease Ready=True); the §4.3 JWT-consistency read needs a working Nextcloud. (occ
      maintenance mode cannot be read by a premise -- exec is refused -- so §2.2b reads it.)
    run: kubectl get helmrelease -n office nextcloud -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
generated: "2026-10-21"
---

# nextcloud-whiteboard v2.0.0 -> v2.1.2 (websocket server image)

## 1. Summary & why held

### 1.1 What changes
One line in `kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml`: the
`whiteboard-server` container image `ghcr.io/nextcloud-releases/whiteboard:v2.0.0`
-> `:v2.1.2`. This is the standalone Node.js collaboration (socket.io) server
behind `httproute/nextcloud-whiteboard` on `envoy-external`. It is a plain
Kustomize Deployment (1 replica, RollingUpdate, no PVC, only an `emptyDir` on
`/tmp`), `STORAGE_STRATEGY=lru`, JWT secret from `secret/nextcloud-config` key
`whiteboard-jwt-secret`.

Upstream evidence (github.com/nextcloud/whiteboard, all `prerelease: false`;
newest stable is **v2.1.2**, published 2026-10-23T08:14Z, so under a day old at
retarget; v2.1.1 2026-10-22, v2.1.0 2026-10-20):
- **v2.1.0** server-side diff `v2.0.0..v2.1.0 -- websocket_server Dockerfile` (6 files,
  +124/-45, read in full):
  - `SocketService.js`: the disconnect handler now awaits the pending
    "disconnecting" handler before clearing socket metadata (#1412 "Hand saving over
    to another user when the saving user leaves (needs the new websocket server)").
  - `RoomLifecycleService.js`: presenter-still-connected `continue` restructured into
    if/else; no longer clears timer/voting state when a room empties (with
    `VotingService.clearRoom` removed).
  - `RedisAdapter.js`: comma-separated multi-node REDIS_URL parsing. Inert here:
    live logs say `Using default in-memory adapter` / `lru storage strategy`.
  - `Dockerfile`: base `node:26.8.2-alpine` -> `node:26.12.0-alpine` (same major).
  - No new or renamed socket events, no change to the auth middleware
    (`socketAuthenticateHandler` / `handleAuthError`), no new env vars, no new port.
- **v2.1.1** release notes: two app/front-end fixes (version-restore handling, keep
  deleted elements when commenting/voting) plus dependency and translation updates.
- **v2.1.2** release notes: *"Use Node 26.12.1 from the October security release in the
  Docker image"* (#1428). `Dockerfile`: `node:26.12.0-alpine` -> `node:26.12.1-alpine`
  (both stages). The whole `v2.1.0...v2.1.2` compare (21 commits) touches no
  `websocket_server/` file; the rest is front end, CHANGELOG, tests, l10n and the
  `package.json` version (2.1.0 -> 2.1.2, which the server's `/status` reports). So
  the §4 probes written against v2.1.0's server code apply unchanged.
- Image: GHCR OCI index `v2.1.2` = `sha256:fd714528ae29beb9e9ad56589c031f7c6c688979b5e0cfbba7bb546cf75a0e43`
  (manifest HEAD 200, 2026-10-23); `v2.0.0` = `sha256:05959663...` (running now);
  `v2.1.0` = `sha256:855227c3...` (superseded).

### 1.2 Why it was held -- and why that reason does NOT apply
Held by the `*nextcloud*` deny rule in `runbooks/auto-update-policy.yaml`:
*"chart+image must bump together and run occ migrations (Mail custom_app /
stuck-maintenance trap) -- operator-supervised only."* **Every clause of that
reason is false for this component**, exactly the shape the file already
documents for `*nextcloud-mcp*` and `*nextcloud-redis*` (both given their own
rule above the glob for this reason):
- *chart+image together*: there is no chart. The Deployment is raw YAML in the
  nextcloud app folder; no HelmRelease renders it.
- *occ migrations*: the websocket server never runs `occ` and has no database.
- *Mail custom_app / stuck maintenance mode*: nothing in this change touches the
  Nextcloud pod, its PVCs, its DB or maintenance mode.

So the hold is a **false positive of the glob**, and this plan is `risk: low`.
The real (small) risks are user-facing only: (a) the roll drops open sockets
(guarded by premise `no-active-whiteboard-rooms`), and (b) a server/app version
skew (§1.3). Repo correction owed (not done here): add a `*nextcloud-whiteboard*`
rule ABOVE `*nextcloud*` with its own reason (majors pair with a Nextcloud APP
major, e.g. 1.5.9 -> 2.0.0 was the Vue-3 rewrite; minors/patches are server-only).

### 1.3 Server/app pairing -- the app is ALREADY ahead of the server
**Changed since the first draft (re-measured 2026-10-23):** the Nextcloud APP
`whiteboard` is now **2.1.0** live (`occ app:list`): the Nextcloud 35 upgrade
(`nextcloud-fleet-35.0.1`, executed 2026-10-23) ran its `occ app:update --all` pass
and pulled it. The server is still v2.0.0. The 2.1.0 app expects the new server for the
save hand-over fix (#1412), and the 2.1.x server keeps the 2.0.0 protocol, so this bump
is no longer "server first, app later": it **closes a live version skew** (app 2.1.0 /
server 2.0.0; the degradation is only the saving-user-leaves hand-over, i.e. 2.0.0
behaviour). That is a reason to take it soon, not a reason for risk. The app diff
`v2.0.0..v2.1.0 -- lib appinfo` has no `lib/Migration` change. This plan installs no app
update.

### 1.4 Security driver
See F-ba1774e1 (detail stays in `sweep_findings`, per `docs/sops/vulnerability-disclosure.md`).
This bump is the remediation available to us (we bump, we never rebuild); closure is
measured by the next scan, not asserted here.

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). All read-only.

```bash
# 2.1 premises (the window agent re-runs these at runtime)
.venv/bin/python3 runbooks/plan-premises.py nextcloud-whiteboard-2.1.2

# 2.2 Flux healthy for the owning Kustomization
flux get ks -n office nextcloud          # READY True, applied revision = origin/main HEAD

# 2.2b Nextcloud not in maintenance mode (expect: false; STOP on true or on an error)
kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ config:system:get maintenance"

# 2.3 baseline: version + rooms from the server itself (expect: 2.0.0 0 0)
kubectl exec -n office deploy/nextcloud-whiteboard -c whiteboard-server -- node -e "fetch('http://127.0.0.1:3002/status').then(r=>r.json()).then(j=>console.log(j.version, j.metrics.rooms.activeRooms, j.metrics.rooms.connectedClients))"

# 2.4 baseline metrics (record values)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://localhost:19090/api/v1/query --data-urlencode 'query=kube_deployment_status_replicas_available{namespace="office",deployment="nextcloud-whiteboard"}' | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('available', r[0]['value'][1] if r else 'EMPTY')"
kill $PF 2>/dev/null

# 2.5 rollback digest on record (expect sha256:059596633333d009890c64858f89f133ccd973a2e0823ad960a0cc05cf8657f1)
kubectl get pods -n office -l app=nextcloud-whiteboard -o jsonpath='{.items[0].status.containerStatuses[0].imageID}'; echo

# 2.6 the JWT probe passes BEFORE the change (proves the §4.2 gate works on the old server)
#     -> run §4.2 now; expect PASS / PASS / CONNECT_ERROR Authentication error.
```

STOP if any premise fails, if 2.3 shows `activeRooms` > 0 (someone is editing --
wait, do not force), or if 2.6 does not pass on the old server.

## 3. Steps

```bash
cd /Users/mu/code/cberg-home-nextgen
# 3.1 bump the tag (re-dry-tested on a scratch copy with BSD sed 2026-10-23; resulting diff:
#   25c25
#   <         image: ghcr.io/nextcloud-releases/whiteboard:v2.0.0
#   ---
#   >         image: ghcr.io/nextcloud-releases/whiteboard:v2.1.2
sed -i '' 's|image: ghcr.io/nextcloud-releases/whiteboard:v2\.0\.0$|image: ghcr.io/nextcloud-releases/whiteboard:v2.1.2|' \
  kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml
git diff --stat kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml   # exactly 1 file, 1 insertion, 1 deletion
grep -c 'whiteboard:v2.1.2' kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml   # must print 1

# 3.2 validate
kubeconform -summary -ignore-missing-schemas kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml

# 3.3 commit ONLY this path (shared worktree), verify subject + contents, push
cat > /tmp/wb-msg.txt <<'EOF'
chore(nextcloud-whiteboard): bump websocket server v2.0.0 -> v2.1.2

Plan nextcloud-whiteboard-2.1.2. Server-only; the Nextcloud app is already 2.1.0
(from the Nextcloud 35 app-update pass); this brings the server up to it.

<the executing agent's Co-Authored-By trailer>
EOF
git commit --only kubernetes/apps/office/nextcloud/app/whiteboard-proxy.yaml -F /tmp/wb-msg.txt
git log -1 --format=%s          # must be the subject above; amend before push if not
git show --stat HEAD            # must list ONLY whiteboard-proxy.yaml
git push
```

Flux applies via the push webhook (no manual reconcile). Expected: within ~2 min
a new ReplicaSet, the old pod terminates after the new one is Ready.

## 4. Verification

```bash
# 4.1 rollout + digest (tag strings lie; read the running imageID)
kubectl rollout status -n office deploy/nextcloud-whiteboard --timeout=180s
kubectl get pods -n office -l app=nextcloud-whiteboard -o 'custom-columns=NAME:.metadata.name,IMG:.status.containerStatuses[0].imageID,RESTARTS:.status.containerStatuses[0].restartCount,READY:.status.containerStatuses[0].ready'
# PASS: exactly one pod, imageID ends sha256:fd714528ae29beb9e9ad56589c031f7c6c688979b5e0cfbba7bb546cf75a0e43,
#       RESTARTS 0, READY true. FAIL prints the old 05959663... digest (rollout did not land)
#       or two pods / restarts > 0.

# 4.1b the server reports the new version (FAIL: prints 2.0.0)
kubectl exec -n office deploy/nextcloud-whiteboard -c whiteboard-server -- node -e "fetch('http://127.0.0.1:3002/status').then(r=>r.json()).then(j=>console.log(j.version, j.status, j.metrics.storageStrategy))"
# PASS: "2.1.2 running lru"  (j.version is the package.json version: v2.0.0 reads 2.0.0 live, v2.1.2 reads 2.1.2)
```

**4.2 CONTENTS ASSERTION: a JWT-authenticated socket.io session is accepted and a
wrongly-signed one is refused, both in-cluster and through the public hostname** --
measured by the probe below, compared to the identical pre-change run (§2.6).
The probe signs a 60 s token with the pod's own `JWT_SECRET_KEY` and waits for the
server's `init-room` event (emitted only after `socketAuthenticateHandler` passed,
`SocketService.handleConnection`). It joins no room and writes nothing. The
negative control signs with a wrong key and must get `Authentication error`
(`handleAuthError`) -- so the gate is proven able to fail. Dry-run on v2.0.0
2026-10-21: `PASS init-room via websocket` x2, `CONNECT_ERROR Authentication error`.

```bash
WB=$(kubectl get httproute -n office nextcloud-whiteboard -o jsonpath='{.spec.hostnames[0]}')
cat > /tmp/wb-probe.js <<'EOF'
const {io}=require("/app/node_modules/socket.io-client");const jwt=require("/app/node_modules/jsonwebtoken");
const url=process.argv[1]; const bad=process.argv[2]==="bad";
const tok=jwt.sign({userid:"wb-probe",user:{id:"wb-probe",name:"wb-probe"},fileId:0,permissions:"read"},bad?"deliberately-wrong":process.env.JWT_SECRET_KEY,{algorithm:"HS256",expiresIn:60});
const s=io(url,{transports:["websocket"],auth:{token:tok},reconnection:false,timeout:8000});
s.on("init-room",()=>{console.log("PASS init-room via "+s.io.engine.transport.name);s.close();process.exit(0)});
s.on("connect_error",e=>{console.log("CONNECT_ERROR "+e.message);process.exit(2)});
setTimeout(()=>{console.log("TIMEOUT");process.exit(3)},12000);
EOF
P=$(cat /tmp/wb-probe.js)
kubectl exec -n office deploy/nextcloud-whiteboard -c whiteboard-server -- node -e "$P" http://127.0.0.1:3002 good; echo "exit=$?"   # PASS ... exit=0
kubectl exec -n office deploy/nextcloud-whiteboard -c whiteboard-server -- node -e "$P" "https://$WB" good;    echo "exit=$?"   # PASS ... exit=0
kubectl exec -n office deploy/nextcloud-whiteboard -c whiteboard-server -- node -e "$P" "https://$WB" bad;     echo "exit=$?"   # CONNECT_ERROR Authentication error, exit=2
```
FAIL modes: `TIMEOUT` (websocket upgrade broken at the edge / server not
listening), `CONNECT_ERROR Authentication error` on a `good` run (JWT handling
regressed), or `PASS` on the `bad` run (auth no longer enforced -- roll back
immediately). Note `$P` is passed as ONE argument (double-quoted); do not
word-split it.

**4.3 CONTENTS ASSERTION: Nextcloud and the server still share the same JWT
secret** -- hash prefix comparison only; the secret is never printed. The
empty-string hash prefix `e3b0c44298fc1c14` is rejected so an empty read cannot
pass. Measured equal on 2026-10-21.
```bash
A=$(kubectl exec -n office deploy/nextcloud -c nextcloud -- su -s /bin/sh www-data -c "php occ config:app:get whiteboard jwt_secret_key | tr -d '\n' | sha256sum" | cut -c1-16)
B=$(kubectl exec -n office deploy/nextcloud-whiteboard -c whiteboard-server -- sh -c 'printf %s "$JWT_SECRET_KEY" | sha256sum' | cut -c1-16)
if [ -n "$A" ] && [ "$A" != "e3b0c44298fc1c14" ] && [ "$A" = "$B" ]; then echo JWT_MATCH; else echo "JWT_MISMATCH nc=$A wb=$B"; fi
```

```bash
# 4.4 public polling handshake from the Mac (edge -> envoy-external -> service)
curl -s -m10 "https://$WB/socket.io/?EIO=4&transport=polling" | head -c 60; echo
# PASS: starts with 0{"sid":  FAIL: HTML / 5xx / empty.

# 4.5 Prometheus (kube-state-metrics), >= 5 min after rollout. Own shell: any port-forward from section 2 is gone, so open it here.
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://localhost:19090/api/v1/query --data-urlencode 'query=kube_deployment_status_replicas_available{namespace="office",deployment="nextcloud-whiteboard"}' | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('available', r[0]['value'][1] if r else 'EMPTY')"
curl -s http://localhost:19090/api/v1/query --data-urlencode 'query=max(increase(kube_pod_container_status_restarts_total{namespace="office",container="whiteboard-server"}[10m]))' | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('restarts10m', r[0]['value'][1] if r else 'EMPTY')"
kill $PF 2>/dev/null
# PASS: available 1, restarts10m 0. EMPTY on either = the instrument is not reading (FAIL, do not
# score as healthy) -- both series were confirmed present live on 2026-10-21.

# 4.6 server log sanity (case-insensitive)
kubectl logs -n office deploy/nextcloud-whiteboard --since=10m | grep -i -E 'error|exception|unhandled' | grep -v -i 'Authentication error' | head
# PASS: no lines. The 4.2 negative control makes the server log
#       "[AUTH] Authentication failed for socket ...: Authentication error" (console.debug goes to
#       stdout in Node) -- expected, and excluded by the grep -v.
kubectl logs -n office deploy/nextcloud-whiteboard --since=10m | grep -c 'Server started successfully on port 3002'   # PASS: 1
# 4.6 CONTROL (proves the exclusion in the absence grep is excluding something real, not hiding a dead log read):
# the 4.2 bad-probe run must have produced at least one Authentication line in the same window.
kubectl logs -n office deploy/nextcloud-whiteboard --since=10m | grep -c -i 'Authentication'   # PASS: >= 1
#   FAIL = 0: the negative probe did not reach the server (or logs are unreadable), so the absence grep above measured
#   nothing; re-run 4.2 and 4.6 together within 10 min. Run 4.6 within 10 min of the 4.2 bad probe.
```

CONTROL: metric kube_deployment_status_replicas_available -- `{namespace="office",deployment="nextcloud-whiteboard"}` must read 1 (EMPTY = instrument dead = FAIL)
CONTROL: metric kube_pod_container_status_restarts_total -- `increase(...{namespace="office",container="whiteboard-server"}[10m])` must read 0

4.7 Optional attended check (Chrome, per house rule): open any whiteboard file in
Nextcloud Files, draw one stroke, reload; the stroke persists and the collaborator
avatar list renders. Not required for the nightly window -- 4.2 covers the
server's auth + websocket path end to end.

## 5. Rollback

Nothing is forward-only (no PVC, no DB, no occ; boards live in Nextcloud files).

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-3.3>          # restores :v2.0.0 in whiteboard-proxy.yaml
git log -1 --format=%s                     # confirm it is YOUR revert subject
git show --stat HEAD                       # only whiteboard-proxy.yaml
git push
kubectl rollout status -n office deploy/nextcloud-whiteboard --timeout=180s
kubectl get pods -n office -l app=nextcloud-whiteboard -o jsonpath='{.items[0].status.containerStatuses[0].imageID}'; echo
# back = ends sha256:059596633333d009890c64858f89f133ccd973a2e0823ad960a0cc05cf8657f1
```
Then re-run §4.1b (expect `2.0.0 running lru`) and §4.2 (PASS/PASS/CONNECT_ERROR).
The Nextcloud APP is already 2.1.0 (§1.3), so after a rollback the server is 2.0.0 again:
protocol-compatible, only the save hand-over fix (#1412) is degraded, which is the
behaviour today.

## 6. Interference notes

- **Owning Kustomization is `office/nextcloud`** (path `kubernetes/apps/office/nextcloud/app`,
  `wait: false`), shared with `helmrelease/nextcloud`, `nextcloud-redis`,
  `notify-push`, both HTTPRoutes. This commit changes only the whiteboard
  Deployment, so the other objects re-apply unchanged (no helm upgrade, no
  Nextcloud restart, no redis restart -> no user logout).
- **`nextcloud-fleet-35.0.1`: executed 2026-10-23, no longer a constraint.** Its
  app-update pass already moved the NC app to 2.1.0 (§1.3); this plan completes the pair.
- **`nextcloud-9.4.1` (exporter), `redis-fleet-8.10.2` (sat-attended:2026-10-24),
  `nextcloud-mcp-0.202.1`:** declared in `conflicts_with`; never the same night.
  The exporter commit edits `helmrelease.yaml` in the same Kustomization, so helm-controller
  runs a nextcloud helm upgrade that would blur this plan's §4 reads; redis-fleet restarts
  the pod the §2.2b/§4.3 `occ` execs target.
- **Prometheus:** §2.4/§4.5 read it. No kube-prometheus-stack plan is open (retired
  2026-10-23); serialize one away if it is ever planned.
- `bitnamilegacy-exit-nextcloud-db` (blocked): no
  conflict -- they do not touch this Deployment and this plan does not touch
  theirs; the whiteboard server never talks to MariaDB or nextcloud-redis.
- `helm-drift-detection`: lists this Deployment as not Helm-owned (outside drift
  detection); no interaction.
- Storage: no PVC is created, modified or deleted. The CIFS storage-safety
  pre-flight does not apply (no CIFS object in scope); `pvc/nextcloud-data`
  (`cifs-nextcloud-data`, severe tier) is untouched.
- Suitable for the unattended `nightly` window under SD-11 (interruption is
  accepted, no data/feature loss): the only user impact is a few seconds of
  socket reconnect, and the `no-active-whiteboard-rooms` premise refuses the run
  while anyone is editing.
