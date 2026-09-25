---
plan_id: penpot-cache-9.2
component: penpot-cache
pr: null                              # No Renovate PR. The deny rule `*valkey*` in
                                      # runbooks/auto-update-policy.yaml blocks the PR lane;
                                      # coverage.py routed this to PLAN via its arity check.
kind: image
current: "9.1.2"                      # live-verified 2026-09-25: deploy spec image
                                      # valkey/valkey:9.1.2 AND `INFO server` valkey_version:9.1.2
target: "9.2 series, BLOCKED: no GA fixed 9.2.N tag exists; pin the first GA 9.2.N, never the floating 9.2"
                                      # Deliberately NOT a fixed tag yet — there is none to name.
                                      # When a GA ships, REFRESH IN PLACE (keep plan_id): set
                                      # target to `"9.2.N (fixed pin replacing the floating 9.2)"`
                                      # — the leading 9.2.N is what premise
                                      # target-is-a-fixed-ga-tag reads, and the trailing bare 9.2
                                      # keeps target_covers() matching the held `new: 9.2`.
update_type: minor
risk: low                             # stateless cache (save "" / appendonly no), single consumer
                                      # app, no schema. Low ONLY once the target is a GA tag.
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/penpot-cache        # image tag edit
    - deployment/penpot-cache         # Recreate strategy -> ~10-30s cache outage
    - deployment/penpot-backend       # NOT edited; its lettuce client drops + reconnects
    - deployment/penpot-exporter      # NOT edited; holds one client connection, reconnects
  shared: []                          # dedicated cache, no PVC, no route; not a shared redis
depends_on: []
conflicts_with: [kube-prometheus-stack-91.4.1, flux-reconciler-impersonation]
                                      # kube-prometheus-stack-91.4.1: §4 reads kube-state-metrics
                                      #   through Prometheus — the window's instrument.
                                      # flux-reconciler-impersonation: changes how kustomize/helm
                                      #   controllers apply in every namespace incl. office; a
                                      #   same-night change there would make a failed apply here
                                      #   ambiguous (whose fault?) and muddy the rollback.
exclusive: false
security_ref: null                    # no CVE driver; the valkey image-CVE register row is an
                                      # AR-029 acceptance on the finding record, not this plan's driver
capability_change: false
rollback_class: git-revert            # no persistence: 9.2 writes no RDB/AOF a 9.1.2 could not read
finding_refs: [F-fe71a06e]            # "penpot-cache: image valkey/valkey 9.1.2 → 9.2 (minor)"
status: blocked                       # BLOCKED on premise target-is-a-fixed-ga-tag (see §1)
window: null
premises:
  # Run 2026-09-25 while writing: 1, 2, 4 PASS; 3 FAILS BY DESIGN (the block).
  - id: live-image-still-9.1.2
    why: >-
      `current:` claims 9.1.2. If the deployment already moved (the 2026-09-21
      Step 0 direct-bump put the floating 9.2 = 9.2.0-rc1 into production once,
      reverted in 397af0ff), this plan's baseline and rollback target are wrong.
    run: kubectl get deploy -n office penpot-cache -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: valkey/valkey:9.1.2
  - id: manifest-pin-still-9.1.2
    why: "The §3 sed anchors on the exact string `tag: \"9.1.2\"`; a changed pin makes it a silent no-op."
    run: cat /Users/mu/code/cberg-home-nextgen/kubernetes/apps/office/penpot-cache/app/helmrelease.yaml | grep -c 'tag. "9.1.2"'
    expect_exact: "1"
  - id: target-is-a-fixed-ga-tag
    why: >-
      THE BLOCKER. As of 2026-09-25 no GA 9.2.x exists: Docker Hub
      valkey/valkey:9.2.0, 9.2.1, 9.2.2 all return 404, and the floating 9.2 is
      digest-identical to 9.2.0-rc1 (GitHub marks 9.2.0-rc1 Pre-release; Latest
      is 9.1.2). The premise runner cannot query a registry (curl is not an
      allowed verb), so the gate is the plan's own target line: it passes only
      after a human/planner has verified a GA 9.2.N in the registry (§2.1) and
      refreshed `target:` to name it. Until then it fails and the scheduler
      refuses the plan.
    run: cat /Users/mu/code/cberg-home-nextgen/runbooks/maintenance/plans/penpot-cache-9.2.md | grep -E -c '^target. "9[.]2[.][0-9]+ '
    expect_exact: "1"
  - id: penpot-backend-points-at-penpot-cache
    why: >-
      The consumer the §4 client-reconnect gate counts. If penpot's redis host
      moved, the reconnect assertion measures the wrong thing.
    run: kubectl get helmrelease -n office penpot -o jsonpath='{.spec.values.config.redis.host}'
    expect_exact: penpot-cache
sops_refs:
  - docs/sops/application-update.md
generated: "2026-09-25"
---

# penpot-cache: valkey 9.1.2 -> 9.2 (BLOCKED until a GA 9.2.N ships)

## 1. Summary & why held

`penpot-cache` (namespace `office`) is a cache-only Valkey (bjw-s app-template
5.1.0, `strategy: Recreate`, `--save ""`, `--appendonly no`, no PVC, no auth)
serving Penpot's backend and exporter on `penpot-cache:6379`.

Coverage reports `valkey/valkey 9.1.2 -> 9.2` and PLANs it because *"target 9.2
names FEWER version components than the pinned 9.1.2 — a floating series
pointer, not a fixed version"*. That hold is **correct, not a false positive**.
Measured 2026-09-25 against the registry and upstream:

| Probe | Result |
|---|---|
| `valkey/valkey:9.2` | 200, index digest `sha256:247b5e73…` |
| `valkey/valkey:9.2.0-rc1` | 200, **same** digest `sha256:247b5e73…` |
| `valkey/valkey:9.2.0`, `9.2.1`, `9.2.2`, `9.2.0-rc2` | 404 |
| `valkey/valkey:9.1.2` / `9.1` | 200, both `sha256:418652cf…` |
| GitHub `valkey-io/valkey` releases | `9.2.0-rc1` = **Pre-release** (2026-09-16); **Latest = 9.1.2** |

(Earlier measurements on 09-19/09-21 recorded `b0eef48f…` for both tags; Hub
shows both re-pushed 2026-09-21T09:08Z, now `247b5e73…`. Still digest-identical,
still the RC — a re-push of a floating tag is exactly why it must not be pinned.)

So the floating `9.2` is a release candidate, and it has already reached
production once: the Step 0 direct-bump `335ff526` shipped it and `397af0ff`
reverted it (history on F-581837f0 / F-aff597aa, both resolved). **This plan
therefore pins a fixed GA `9.2.N` or does nothing; it never pins `9.2`.** It
stays `status: blocked` and premise `target-is-a-fixed-ga-tag` fails until a
GA exists.

Upstream evidence for the eventual 9.2 (from the 9.2.0-rc1 notes, re-read these
for the GA before unblocking): the only listed *Behavior Change* is *"Active
expiration of keys and hash fields now increments the dirty counter, so save
points (and thus BGSAVE) may trigger more often"* — inert here (`--save ""`).
Everything else is new commands/configs, performance and cluster fixes; nothing
touches the standalone RESP path Penpot's lettuce client uses. `redis_version`
compat string reads 7.2.4 on 9.1.2; the gate in §4 does not depend on it.

### Unblocking procedure (whoever refreshes this plan)
1. Run §2.1. It must print a 200 for a `9.2.N` with N a plain integer, the
   GitHub release for it must NOT be a prerelease, and its digest must differ
   from every `-rc*` tag.
2. Refresh in place (keep `plan_id`): set `target:` to
   `"9.2.N (fixed pin replacing the floating 9.2)"`, replace `9.2.0` with `9.2.N`
   in §3/§4, re-read the GA release notes for new *Behavior Changes*, set
   `status: draft`, re-date `generated:`. Premise 3 then passes.
3. Separately (NOT in this window), the `*valkey*` deny rule in
   `runbooks/auto-update-policy.yaml` names "a GA 9.2.x appears on Docker Hub"
   as its removal condition — raise that with the operator as its own reviewed
   policy change.

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.1 THE GATE — a GA fixed 9.2.N exists and is not an RC twin. Replace N.
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:valkey/valkey:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in 9.2.N 9.2.0-rc1 9.2; do
  printf '%-12s ' "$t"
  curl -s -I -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json" \
    "https://registry-1.docker.io/v2/valkey/valkey/manifests/$t" \
    | grep -i -E '^HTTP|docker-content-digest' | tr -d '\r' | tr '\n' ' '; echo
done
gh release list -R valkey-io/valkey -L 5
# PASS: 9.2.N -> HTTP 200 with a digest DIFFERENT from 9.2.0-rc1's, and
#       gh lists 9.2.N without "Pre-release". FAIL (today): 9.2.N -> 404.

# 2.2 premises (1,2,4 must PASS; 3 passes only after the refresh above)
.venv/bin/python3 runbooks/plan-premises.py penpot-cache-9.2

# 2.3 baseline: exactly one pod, running 9.1.2, clients connected
kubectl -n office get deploy/penpot-cache deploy/penpot-backend deploy/penpot-exporter
kubectl -n office exec deploy/penpot-cache -- valkey-cli INFO server | grep -i valkey_version
kubectl -n office exec deploy/penpot-cache -- valkey-cli INFO clients | grep -i connected_clients
# baseline 2026-09-25: valkey_version:9.1.2, connected_clients:6
#   (4 from the penpot-backend pod IP, 1 exporter, 1 the cli itself)

# 2.4 baseline redis error noise in the backend (expect 0 outside bursts;
#     one 88-line RedisCommandTimeoutException burst was seen 2026-09-24T20:26Z)
kubectl -n office logs deploy/penpot-backend --since=30m | grep -i -c -E 'RedisCommandTimeout|RedisConnectionException|Connection refused'

# 2.5 Flux healthy for both releases
flux get helmreleases -n office | grep -E 'NAME|penpot'
```

No backup step: the cache holds no durable state (keyspace was empty at
authoring; `--save ""`, no PVC).

## 3. Steps

1. Edit the pin (dry-tested on a scratch copy with BSD sed 2026-09-25; the
   resulting diff was exactly `<   tag: "9.1.2"` / `>   tag: "9.2.0"`):

   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' 's/tag: "9\.1\.2"/tag: "9.2.0"/' kubernetes/apps/office/penpot-cache/app/helmrelease.yaml
   git diff kubernetes/apps/office/penpot-cache/app/helmrelease.yaml   # exactly one line changed
   grep -n 'tag: "9.2' kubernetes/apps/office/penpot-cache/app/helmrelease.yaml   # must be 9.2.<N>, never bare 9.2
   ```
   (Substitute the real GA `9.2.N` for `9.2.0` when refreshing.)

2. Commit only that file and push:

   ```bash
   git commit --only kubernetes/apps/office/penpot-cache/app/helmrelease.yaml \
     -m "chore(penpot-cache): valkey 9.1.2 -> 9.2.N (plan penpot-cache-9.2)"
   git log -1 --format=%s        # confirm the subject is yours
   git show --stat HEAD          # exactly one file
   git push
   ```

3. Let the Flux webhook reconcile (no manual reconcile). The Deployment is
   `Recreate`, so expect a 10-30s window where Penpot's backend logs
   connection errors while it reconnects. Penpot sessions are not stored in
   the cache; open editors may see a brief realtime-sync hiccup.

## 4. Verification

Run from T+3 min after the new pod is Ready (allows the lettuce reconnect).

```bash
# 4.1 the running binary is the pinned GA — NOT the rc (contents, not the tag)
kubectl -n office get pod -l app.kubernetes.io/name=penpot-cache \
  -o jsonpath='{range .items[*]}{.status.containerStatuses[0].image}{" "}{.status.containerStatuses[0].imageID}{"\n"}{end}'
kubectl -n office exec deploy/penpot-cache -- valkey-cli INFO server | grep -i valkey_version
# PASS: exactly one line, image valkey/valkey:9.2.N, valkey_version:9.2.N.
# FAIL shapes: valkey_version:9.2.0 on an rc build prints the same number — so
#   ALSO compare imageID's digest against the 9.2.0-rc1 digest from §2.1; equal = FAIL.
#   Two lines = old pod still terminating; wait and re-run.

# 4.2 real round-trip on a scratch DB (penpot uses db 0)
kubectl -n office exec deploy/penpot-cache -- valkey-cli -n 15 SET plan:penpot-cache-9.2 ok EX 60
kubectl -n office exec deploy/penpot-cache -- valkey-cli -n 15 GET plan:penpot-cache-9.2
# PASS: prints `ok`. FAIL: (nil) or an error.

# 4.3 consumers reconnected
kubectl -n office exec deploy/penpot-cache -- valkey-cli CLIENT LIST | awk '{print $2}' | cut -d= -f2 | cut -d: -f1 | sort | uniq -c
kubectl -n office get pod -l app.kubernetes.io/name=penpot-backend -o jsonpath='{.items[0].status.podIP}{"\n"}'
kubectl -n office get pod -l app.kubernetes.io/name=penpot-exporter -o jsonpath='{.items[0].status.podIP}{"\n"}'
# PASS: the backend pod IP appears with >= 1 connection AND the exporter IP with >= 1.
# FAIL: only 127.0.0.1 listed -> the app never reconnected (baseline had 4 + 1).

# 4.4 no redis errors after the reconnect grace
kubectl -n office logs deploy/penpot-backend --since=10m | grep -i -c -E 'RedisCommandTimeout|RedisConnectionException|Connection refused'
# PASS: 0 when --since window starts after T+3 min (re-run with --since=5m if the
#   Recreate itself is inside the 10 min). FAIL: any non-zero count past T+3 min.

# 4.5 Penpot itself answers (floor, not the gate)
kubectl -n office get deploy penpot-backend penpot-frontend penpot-exporter
flux get helmreleases -n office | grep penpot
```

CONTENTS ASSERTION: the cache serves reads and writes on the new GA binary and
Penpot's clients are attached to it — measured by 4.1 (version + digest not the
rc), 4.2 (SET/GET round-trip returns `ok`), 4.3 (backend and exporter pod IPs
present in `CLIENT LIST`), compared to the 2026-09-25 baseline of 4 backend + 1
exporter connections on 9.1.2.

CONTROL: metric kube_pod_container_info — `{namespace="office",container="app",pod=~"penpot-cache.*"}` must return exactly one series whose `image` label is `docker.io/valkey/valkey:9.2.N` (read live 2026-09-25: one series, image `docker.io/valkey/valkey:9.1.2`).
CONTROL: metric kube_deployment_status_replicas_available — `{namespace="office",deployment="penpot-cache"}` must be 1 for 10 min after the rollout (baseline 1).
CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="office",pod=~"penpot-backend.*"}` must not increase across the window (baseline 0); a crash-looping backend on reconnect shows here first.

## 5. Rollback

Stateless and forward-safe: nothing on disk, so the old binary has nothing to
reload.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-step-2>
git log -1 --format=%s ; git show --stat HEAD   # one file, the revert
git push
```

Confirm back:

```bash
kubectl -n office get deploy penpot-cache -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # valkey/valkey:9.1.2
kubectl -n office exec deploy/penpot-cache -- valkey-cli INFO server | grep -i valkey_version            # 9.1.2
```
then re-run §4.2-4.4 against 9.1.2. If the HelmRelease is stuck `pending-upgrade`
or remediation has already rolled back, follow `docs/sops/application-update.md`
§7/§11 (`helm rollback penpot-cache <last-deployed> -n office --wait=false`)
before the revert lands.

## 6. Interference notes

- **Blocked:** do not schedule until premise `target-is-a-fixed-ga-tag` passes.
  Never "resolve" the block by pinning `9.2` or `9.2.0-rc1`.
- Only Penpot depends on this cache (verified: penpot HelmRelease
  `config.redis.host: penpot-cache`; client list shows only backend + exporter).
  Nextcloud/affine/sure redis instances are separate Deployments and untouched.
- `conflicts_with` carries kube-prometheus-stack-91.4.1 (the §4 CONTROL metrics
  come through it) and flux-reconciler-impersonation (it changes the apply path
  in `office`). No other open plan touches `penpot*`.
- The `*valkey*` deny rule stays in place through this window; this is a
  manual, reviewed bump and is not affected by it. Removing the rule is a
  separate policy change (see §1 unblocking step 3).
- Repo correction noted while planning: the header comment in
  `kubernetes/apps/office/penpot-cache/app/helmrelease.yaml` says the service
  is `penpot-cache-primary` and that penpot references it; the live Service is
  `penpot-cache` and penpot's HelmRelease uses `penpot-cache`. No
  `penpot-cache-primary` object exists. Out of scope for this plan.
