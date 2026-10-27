---
plan_id: authentik-web-max-requests
component: authentik
pr: null                              # config change, no Renovate PR
kind: config
current: "authentik server gunicorn web.max_requests=1000 / jitter=50 (upstream defaults; no AUTHENTIK_WEB__MAX_REQUESTS* env set), 2 workers x 3 server replicas"
target: "server.env AUTHENTIK_WEB__MAX_REQUESTS=10000, AUTHENTIK_WEB__MAX_REQUESTS_JITTER=1000 on the authentik-server Deployment (server block only)"
update_type: config
risk: low                             # stateless, env-only, one rolling restart of 3 replicas with maxUnavailable 0.
                                      # Not "none": it is the SSO front door, and a 10x longer worker lifetime
                                      # trades the 5-min outpost gaps for leak exposure (watched in section 4).
est_duration_min: 20
needs_reboot: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/authentik                     # server.env gains 2 entries
    - deployment/authentik-server               # 3 replicas, rolling restart (new ReplicaSet)
    - "ak-outpost-* websockets (13 managed forward-auth outposts + embedded): every old server pod termination drops its websockets; outposts wait a fixed 300 s before reconnecting, so the config-push channel is down up to 5 min (forward-auth keeps serving, measured)"
  shared:
    - identity-provider   # authentik = SSO (OIDC) + forward-auth for the estate
    - authentik
    - monitoring          # section 4 reads outpost metrics / alert state
depends_on: []                        # runs BEFORE authentik-2026.8.5, which declares depends_on on this plan
conflicts_with:
  - authentik-2026.8.5                  # same HelmRelease + same Deployment roll. SERIALIZED, this plan FIRST (nightly),
                                        # the bump on a later attended slot after the soak (section 1); never two
                                        # commits racing on helmrelease.yaml.
  - envoy-proxy-config-distroless-v1.39.4 # envoy restart carries auth.<domain>; confounds login/forward-auth gates
  - talos-linux-1.14.4                  # node roll evicts authentik pods mid-verification
  - k8s-1.36.5                          # control-plane/kubelet roll
  - etcd-timeouts-5000-500              # etcd must be quiet (pre-check); do not stack
  - flux-reconciler-impersonation       # changes how helm-controller applies this HR
  - helm-drift-detection                # touches HelmRelease handling cluster-wide
  # No kube-prometheus-stack plan is open (92.x plans retired 2026-10-23). Section 4 reads Prometheus, so
  # if a kube-prometheus-stack bump is ever planned for the same night, add it here and serialize.
exclusive: false
security_ref: null
capability_change: false              # same behaviour, only worker recycle interval changes
rollback_class: git-revert            # stateless env; no migrations, no data
finding_refs: []                      # none exists: finding list --grep outpost (2026-10-22) shows only F-89376ab7
                                      # (single-node outposts) and F-37acab13 (doc); neither covers worker recycling
review: ready-for-go@2026-10-23      # delta plan-reviewer 2026-10-23: ready-for-go
status: vetted
window: "nightly:2026-10-28"          # must land >= 2 nights before authentik-2026.8.5
                                      # re-stamped from nightly:2026-10-27: pre-check STOP (abort 1/2) on 2 etcd leader
                                      # changes in the last 1h (02:42/02:47Z, during that night's Step 0 roll); nothing changed.
premises:
  - id: recycle-evidence-in-logs
    why: "Read-only proxy for the 1000-request default (exec is refused by the premise runner): the server logs show gunicorn worker recycling in the last 6 h."
    run: kubectl logs -n kube-system deploy/authentik-server -c server --since=6h | grep -c 'Booting worker'
    expect_matches: '^[1-9][0-9]*$'
  - id: no-override-yet
    why: "No AUTHENTIK_WEB__MAX_REQUESTS env is set today (only AUTHENTIK_WEB__PATH from the chart)."
    run: kubectl get deploy -n kube-system authentik-server -o jsonpath='{.spec.template.spec.containers[0].env[*].name}' | tr ' ' '\n' | grep -c 'WEB__MAX_REQUESTS'
    expect_exact: "0"
  - id: three-server-replicas-ready
    why: "Roll safety assumes 3/3 Ready."
    run: kubectl get deploy -n kube-system authentik-server -o jsonpath='{.status.readyReplicas}/{.spec.replicas}'
    expect_exact: "3/3"
  - id: roll-strategy
    why: "Zero-downtime claim depends on maxUnavailable resolving to 0 (25% of 3 rounds down)."
    run: kubectl get deploy -n kube-system authentik-server -o jsonpath='{.spec.strategy.rollingUpdate.maxUnavailable}/{.spec.strategy.rollingUpdate.maxSurge}'
    expect_exact: "25%/25%"
  - id: worker-recycle-is-happening
    why: "The problem still exists: at least one 'Worker exiting' per 6 h on the busiest pod."
    run: kubectl logs -n kube-system deploy/authentik-server -c server --since=6h | grep -c 'Worker exiting'
    expect_matches: '^[1-9][0-9]*$'
  - id: server-block-env-in-hr
    why: "Env lives under values.server.env in helmrelease.yaml (chart renders it into the Deployment); no value is set there yet."
    run: grep -c 'WEB__MAX_REQUESTS' kubernetes/apps/kube-system/authentik/app/helmrelease.yaml
    expect_exact: "0"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/authentik.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-22"
---

# authentik server: raise gunicorn max_requests 1000 -> 10000 (jitter 50 -> 1000)

## 1. Summary & why held

**Not an update; a config change**, routed to a plan because it restarts the SSO
front door. Evidence (re-verified 2026-10-22): `/lifecycle/gunicorn.conf.py` in
the server image reads `CONFIG.get_int("web.max_requests", 1000)` and
`web.max_requests_jitter` default 50; 2 workers x 3 replicas. Live `Worker
exiting` counts over the last 26 h: pods 2qf46 (3), b6rwb (1), bhl8s (6 in 3.6 h).
Matches in the logs line up with the outpost drops (e.g. 05:44:47 on 2qf46,
05:13:09 on b6rwb, 05:40:19 on bhl8s). Each exit closes that worker's websockets;
outposts then wait a fixed 300 s before reconnecting, so several of the 14
outposts show `authentik_outpost_connection==0` for 5 min several times per
hour. Impact is only the config-push channel (forward-auth keeps serving; the
`AuthentikOutpostDisconnected` rule has `for: 10m` so it only reads pending).

**Numbers.** Busy pod bhl8s recycles ~1 worker / 36 min, i.e. each worker lasts
~1 h for 1000 (+0-50) requests, ~0.28 req/s/worker (the quiet pods ~3x slower).
10000 + jitter 0-1000 gives ~10 h per worker on the busy pod (>= 4 h goal with
2.5x margin; 5000 would give only ~5 h, too close). Jitter 1000 keeps the 6
workers' exits spread rather than synchronised.
**Memory.** Server working sets today: 589-703 Mi against a 2 Gi limit (request
512 Mi); a 10x longer worker lifetime is the leak risk. Ceiling check in section 4;
an OOM kill is a container restart with the other 2 replicas serving.

**Server only.** The worker Deployment is celery, not gunicorn; do NOT add the
env there.

**Bundle or separate? Recommend SEPARATE, and first.** The 2026.8.5 bump
(PR 364, held by the `*authentik*` deny rule) needs the chart + both init pins in
one commit, then a manual push of 13 outposts (memory
`project_authentik_outpost_upgrade.md`: a server upgrade does not bump the managed
outposts). Folding a config tweak into that blast radius makes any regression
unattributable, and the max_requests effect needs a multi-hour soak to judge. Land
this one-liner first (20 min, trivially revertable), soak, then do 2026.8.5. If the
operator prefers one disruption, the two env lines can ride in the 2026.8.5
commit, but the soak check then confounds with the upgrade. The
`authentik-2026.8.4` draft is superseded by 2026.8.5 and should be retargeted/retired by
whoever lands that bump (done: that plan is now `authentik-2026.8.5`, which
`depends_on` this one and is scheduled attended, after the section-4 soak gate passes).

**Schedule.** `nightly` window (03:30, unattended): rolling, maxUnavailable 0,
readiness-gated, no reboot. Pick a night with none of the `conflicts_with` plans
(e.g. not the night of `redis-fleet-8.10.2`, `talos-linux-*`, `cilium-*`).
It must land at least 2 nights before the `authentik-2026.8.5` slot so the 24 h
soak (section 4, S1-S3) is complete and read before that GO.

## 2. Pre-checks

```bash
kubectl get deploy -n kube-system authentik-server            # 3/3
kubectl get pods -n kube-system -l app.kubernetes.io/component=server   # 3 Running, 0 recent restarts
# outposts connected (all 14 == 1) - dips of up to 5 min are the known symptom; wait one
# recycle-free minute rather than starting inside a dip:
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
sleep 3
# Outpost gate script (also used by section 4). Written once, reused. See section 4 for why each term exists.
mkdir -p "$TMPDIR" && cat > "$TMPDIR/ak-outpost-gate.py" <<'PY'
import sys, json, urllib.parse, urllib.request
M = sys.argv[1] if len(sys.argv) > 1 else "authentik_outpost_connection"
def q(e):
    u = "http://localhost:9090/api/v1/query?query=" + urllib.parse.quote(e)
    r = json.load(urllib.request.urlopen(u, timeout=20))["data"]["result"]
    return float(r[0]["value"][1]) if r else None   # empty result = None = FAIL, never read as 0
series = q(f"count({M})")
names  = q(f"count(count by (outpost_name)({M}))")
zeros  = q(f"count({M} == 0) or vector(0)")
ok = (series == 16 and names == 14 and zeros == 0)
print(f"series={series} (want 16) names={names} (want 14) zero={zeros} (want 0) -> {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
PY
python3 -I "$TMPDIR/ak-outpost-gate.py"        # want PASS (retry once a minute if inside a dip)
# etcd quiet: no etcd-timeouts-5000-500 / talos plan active this night; no etcd leader changes
# (3 etcd members -> 3 series; max() collapses them; want 0)
curl -s -G localhost:9090/api/v1/query --data-urlencode 'query=max(increase(etcd_server_leader_changes_seen_total[1h]))'
# record the flip baseline for the soak (measured 2026-10-23: 694; embedded outpost 83, forward-auth outposts 31-50 each)
curl -s -G localhost:9090/api/v1/query --data-urlencode 'query=sum(changes(authentik_outpost_connection[24h]))'
curl -s -G localhost:9090/api/v1/query --data-urlencode 'query=max_over_time(max(container_memory_working_set_bytes{namespace="kube-system",pod=~"authentik-server-.*",container="server"})[24h:5m])/1024/1024'   # MiB, 2026-10-23: 697
# authentik DB backup fresh (<= 26 h; measured 6.7 h FRESH on 2026-10-22)
.venv/bin/python3 runbooks/longhorn-backup-age.py authentik-pg-data --max-hours 26
# memory baseline (record it)
kubectl top pod -n kube-system | grep authentik-server
```
Abort if: any server pod not Ready, backup STALE, an etcd leader change in the last
hour, or a conflicting plan is scheduled the same night.

## 3. Steps (GitOps)

1. In `kubernetes/apps/kube-system/authentik/app/helmrelease.yaml`, under
   `values.server.env` (first block, ~line 56-170; NOT the `worker.env` block
   starting ~line 217), add after the existing `AUTHENTIK_LISTEN__*` entries:
   ```yaml
        # Worker recycle: upstream default 1000 (+0-50) recycled each gunicorn
        # worker every ~1 h on the busy replica; every recycle closes the outpost
        # websockets and each outpost waits a fixed 300 s to reconnect. 10000
        # (+0-1000) ~ 10 h. Server only (the worker Deployment is celery).
        - name: AUTHENTIK_WEB__MAX_REQUESTS
          value: "10000"
        - name: AUTHENTIK_WEB__MAX_REQUESTS_JITTER
          value: "1000"
   ```
   Env values must be strings (quoted) or the chart renders an invalid env.
2. Validate: `helm template` is not needed (plain values), run
   `task kubeconform` and `git diff --stat` (expect +9 lines, 1 file).
3. `git commit --only kubernetes/apps/kube-system/authentik/app/helmrelease.yaml -F <msgfile>`;
   `git log -1 --format=%s` must be your subject; push. Flux/helm-controller rolls
   the Deployment (interval 30m; webhook-triggered on push).

**Roll behaviour.** RollingUpdate maxSurge 25% -> 1, maxUnavailable 25% -> 0 of 3:
one new pod is added, must pass `/-/health/ready/` (period 10 s, 3 failures), then
one old pod terminates, x3. Total capacity never drops below 3 Ready pods, so
logins and forward-auth (served by outposts, which only call the server for
config/session checks over the service) are unaffected. No PDB exists (none
needed). Side effect, expected: each terminating old pod drops its outpost
websockets, so some outposts show connection==0 for up to 5 min after the last pod
swaps (same symptom as today, not a regression).

## 4. Verification

Every gate states how it fails.

1. **Rendered env on all 3 pods** (fails with count < 3 if the key landed in the wrong
   block or the roll has not happened):
   `for p in $(kubectl get pods -n kube-system -l app.kubernetes.io/component=server -o name); do kubectl exec -n kube-system $p -c server -- env | grep -c -E '^AUTHENTIK_WEB__MAX_REQUESTS(_JITTER)?='; done`
   -> `2` three times. Also `kubectl get deploy -n kube-system authentik-server -o jsonpath='{.spec.template.spec.containers[0].env}' | grep -c MAX_REQUESTS` -> 2, and the same grep on `authentik-worker` -> `0`.
2. **Live config value read by authentik's own CONFIG** (fails printing 1000/50 if the
   env var name or prefix is wrong - the typo case the env grep cannot catch):
   `kubectl exec -n kube-system deploy/authentik-server -c server -- python -c "from authentik.lib.config import CONFIG; print(CONFIG.get_int('web.max_requests',1000), CONFIG.get_int('web.max_requests_jitter',50))" 2>&1 | tail -1`
   -> `10000 1000`. (If the interpreter path/import fails, use
   `ak dump_config`-equivalent per `docs/sops/authentik.md`; do not accept a
   mere zero exit.)
3. **Rollout complete on the NEW generation**: `kubectl rollout status deploy/authentik-server -n kube-system`
   plus all 3 pod names differ from pre-roll and `.status.readyReplicas==3` (rollout status
   alone green-lights the old generation).
4. **Login through Authentik works** (the failure is a 5xx/redirect loop): a fresh
   private browser session to an OIDC app and one forward-auth app (e.g. Prometheus)
   completes login and lands on the app; `curl -sk -o /dev/null -w '%{http_code}' https://auth.<domain>/-/health/live/` -> 204.
5. **Outposts reconnect** (fails if any outpost stays 0 past 6 min, or the metric vanishes):
   after the last pod swap wait 6 min. The section 2 port-forward is a separate shell and is gone by now:
   re-open it (`kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &`, `sleep 3`)
   and recreate `$TMPDIR/ak-outpost-gate.py` if the shell was reset, then `python3 -I "$TMPDIR/ak-outpost-gate.py"` (script in
   section 2) -> `PASS`, exit 0. Why three terms: (a) `sum(x==0)` and `count(x==0)` return an
   EMPTY result, not 0, when nothing is zero, so "want 0" read empty on both a healthy cluster AND
   a scrape outage (the defect in the first draft); the script applies `or vector(0)` to the zero
   count and instead fails on the series/name counts. (b) 16 series = 13 forward-auth outposts + the
   embedded outpost reporting once per server pod (3); 14 distinct `outpost_name`s. After the roll the
   old pods' series go stale and the 3 new ones replace them, so 16/14 again; a short count means a
   scrape or relabel loss, not health. (c) the zero count catches an outpost that did not reconnect.
   Controls, measured live 2026-10-23: healthy -> `series=16 names=14 zero=0 PASS`; metric absent
   (`python3 -I ... authentik_nonexistent`) -> `series=None names=None zero=0 FAIL`, rc 1;
   positive control that the zero detector fires: `count(up == 0) or vector(0)` returned `1` (one
   down target exists), so the `count(x == 0) or vector(0)` shape does read non-zero when a zero exists.
6. **Memory sanity**: `kubectl top pod -n kube-system | grep authentik-server` < 1 Gi each
   (fails if >= 1 Gi; baseline 589-703 Mi).

**Soak (blocks the `authentik-2026.8.5` GO; read at roll + 25 h so the roll's own flips are
outside the 24 h window; run in the morning of the second day):**

- S1. Flip count, fails if recycling is not reduced. Baseline measured pre-change 2026-10-23: **694**.
  `sum(changes(authentik_outpost_connection[24h]))` evaluated >= 25 h after the roll ->
  expect ~70 (10x fewer recycles); PASS < 230 (3x reduction). Fails (stays ~700) if the env is
  ineffective; it already reads 694 today, so the gate cannot pass vacuously. Empty result = FAIL
  (metric lost), never PASS. Read per name too: `sum by (outpost_name)(changes(authentik_outpost_connection[24h]))`
  (baseline 31-50 per forward-auth outpost, 83 embedded).
- S2. Worker exits by log, independent of Prometheus:
  `for p in $(kubectl get pods -n kube-system -l app.kubernetes.io/component=server -o name); do kubectl logs -n kube-system $p -c server --since=24h | grep -c 'Worker exiting'; done`
  -> per pod <= 3 (baseline 2026-10-22: 3, 1 and 6 in 3.6 h). Each exit line is matched
  case-sensitively against the exact upstream string verified in the premises.
- S3. Memory ceiling, fails on a leak:
  `max_over_time(max(container_memory_working_set_bytes{namespace="kube-system",pod=~"authentik-server-.*",container="server"})[24h:5m])/1024/1024`
  -> PASS < 1200 (MiB; pre-change 697). Climbing toward 2048 means a leak: drop to 3000/300
  instead of leaving it to OOM. `kube_pod_container_status_restarts_total` for the server pods must
  also be unchanged from the post-roll value (an OOM kill is a restart).
- If S1-S3 pass, record it; `authentik-2026.8.5` may then be taken to GO. If any fails, `authentik-2026.8.5`
  stays unscheduled until this plan is rolled back or retuned.

## 5. Rollback

`git revert <commit>` of the helmrelease commit and push; Flux rolls the 3 replicas
back to defaults (same rolling behaviour, same 5-min outpost gap). Confirm: section 4
gate 1 returns `0` env hits on all pods and gate 2 prints `1000 50`. Nothing is
forward-only: no schema, no data, no blueprint change; the DB backup in section 2 is
a precaution only. Trigger rollback if: any server pod CrashLoops or is OOMKilled,
a login fails after the roll, or soak memory trends past 1.5 Gi.

## 6. Interference notes

- Edits the same `helmrelease.yaml` as the `authentik-2026.8.5` bump:
  never two pending commits to this file in one window; the later one rebases onto the other.
- Any envoy, cilium, coredns, talos, k8s, etcd-timeouts or prometheus-stack change the
  same night confounds gates 4-5 (listed in `conflicts_with`).
- Outpost deployments are untouched (no image or config change); only their websocket
  sessions to the server flap once.
- Do not run during the authentik worker/DB maintenance; the worker Deployment does not restart.
