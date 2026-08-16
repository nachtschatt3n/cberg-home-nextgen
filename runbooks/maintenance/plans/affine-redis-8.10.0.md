---
plan_id: affine-redis-8.10.0
component: affine-redis
pr: null                          # coverage.py needs_plan — no open Renovate PR
kind: image
current: "8.8.0-alpine"
target: "8.10.0-alpine"
update_type: minor
risk: low
est_duration_min: 10
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/affine-redis
    - deployment/affine-redis
    - deployment/affine            # transient reconnect only (drops redis link ~seconds)
  shared: []                       # dedicated redis (ClusterIP affine-redis:6379); no shared cache/DB/storage/ingress
depends_on: []
conflicts_with: []                 # keep out of the same window as any future affine-app plan (see Interference)
security_ref: null
status: draft
window: null                       # window agent assigns — any no-reboot weekday slot (mon/tue/wed/thu/fri/sat)
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-16"
---

# affine-redis 8.8.0-alpine → 8.10.0-alpine

## 1) Summary & why held

`affine-redis` is a **stock Docker Hub `redis` image** run as AFFiNE's ephemeral
cache/queue. Only its image tag moves here: `redis:8.8.0-alpine → 8.10.0-alpine`
(a minor upstream Redis bump). The AFFiNE application image
(`ghcr.io/toeverything/affine:0.27.3`) is **not** touched by this plan.

**Why it was held — almost certainly a false positive.** `coverage.py` surfaced
this from the full version universe (no open Renovate PR) and attributed the hold
to the `*affine*` deny rule in `runbooks/auto-update-policy.yaml`, whose stated
reason is:

> "affine chart/image bumps carry breaking env→config.json changes even on patch
> tags (0.27.3) — hold for manual review."

That reason is about the **AFFiNE server image's** env → `config.json` migration
surface. It has **nothing to do with the plain upstream Redis cache image**,
which carries no AFFiNE config semantics. The glob simply also catches the
`affine-redis` HelmRelease name.

**Why the residual risk is genuinely low:**
- The redis container runs **with no persistence at all** — verbatim args
  `--save "" --appendonly "no"` (see `redis-helmrelease.yaml`). There is **no
  PVC**, no RDB, and no AOF. So the Redis release-note breaking-change classes
  that matter (RDB/AOF on-disk format, persistence config directives) **do not
  apply** — nothing is read from or written to disk across the restart.
- AFFiNE uses it as a standard cache/pub-sub over `affine-redis:6379`; the
  commands involved are long-stable across Redis majors, let alone an 8.8→8.10
  minor.
- Redis 8.10 release notes (as of 2026-08) describe additive features (e.g.
  compact-hash encoding) and performance work, not a command/protocol break for
  a basic cache client.

Both tag endpoints are published: `redis:8.8.0-alpine` and `redis:8.10.0-alpine`
return HTTP 200 on Docker Hub (note `8.9.0-alpine` is 404 — the published minor
step is 8.8 → 8.10, so the bump is correct, not a skipped patch).

The proper long-term fix is to tighten the deny rule so it does not swallow the
sidecar (e.g. scope it to the affine app image, or add a `max:` / allow-list for
`affine-redis`); that is an **operator/policy change, out of scope for this plan**
— flagged for the window agent to raise.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) affine stack currently healthy (all three Ready, 0 restarts)
kubectl get pods -n office | grep -E 'affine(-pg|-redis)?-'
flux get helmreleases -n office | grep -E 'affine(-pg|-redis)?\b'

# b) confirm what is actually running now (expect redis:8.8.0-alpine)
kubectl get deploy -n office affine-redis \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'

# c) confirm redis is truly non-persistent (expect --save "" --appendonly no; NO pvc)
kubectl get deploy -n office affine-redis \
  -o jsonpath='{.spec.template.spec.containers[0].command}{"\n"}'
kubectl get pvc -n office | grep -i redis || echo "no redis PVC (expected)"

# d) target tag exists
curl -s -o /dev/null -w '8.10.0-alpine -> %{http_code}\n' \
  https://hub.docker.com/v2/repositories/library/redis/tags/8.10.0-alpine

# e) no in-flight reconcile / other office plan running this window
flux get kustomizations -n flux-system | grep -E 'office|affine' || true
```

Proceed only if the stack is Ready, redis shows `--save "" --appendonly no`, no
redis PVC exists, and the target tag returns 200.

## 3) Steps (GitOps)

No alert silence or rollback-disable needed (low-risk, non-migration sidecar) —
`docs/sops/application-update.md` §5 Example A path.

1. Edit the redis image tag:

   File: `kubernetes/apps/office/affine/app/redis-helmrelease.yaml`
   ```yaml
   # spec.values.controllers.main.containers.app.image
             image:
               repository: redis
               tag: 8.10.0-alpine   # was 8.8.0-alpine
               pullPolicy: IfNotPresent
   ```

2. Commit + push (work directly on `main`, no feature branch):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git add kubernetes/apps/office/affine/app/redis-helmrelease.yaml
   git commit -m "chore(affine): redis sidecar 8.8.0-alpine -> 8.10.0-alpine (ephemeral cache, non-persistent)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012bXdxrZGGHNy5e4RnF6seD"
   git push
   ```

3. Let Flux reconcile (webhook). The redis controller uses `strategy: Recreate`,
   so the old pod terminates and the new one starts — a few seconds of cache
   unavailability. Do **not** hand-delete pods.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# HR reconciled + Ready
kubectl get helmrelease -n office affine-redis \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'

# new image is live
kubectl get deploy -n office affine-redis \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # expect redis:8.10.0-alpine

# redis pod Ready, 0 restarts after settle, and PING works
kubectl get pods -n office | grep affine-redis
POD=$(kubectl get pods -n office -l app.kubernetes.io/name=affine -o name | grep redis | head -1)
kubectl exec -n office ${POD##*/} -- redis-cli ping   # expect PONG

# affine app still Ready and reconnected (no sustained redis errors)
kubectl get pods -n office | grep -E 'affine-[0-9a-f]'
kubectl logs -n office deploy/affine --since=3m | grep -iE 'redis|econnrefused|error' | tail -20 || true
```

Success = affine-redis HR Ready, image `redis:8.10.0-alpine`, `PONG`, redis pod
0 restarts after ~2 min, and the affine app pod stays Ready with no sustained
redis connection errors (a brief burst during the Recreate swap is expected and
self-heals).

## 5) Rollback

Single-file revert — the change is one image tag; the cache is disposable so
there is no data to restore.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <commit-sha>     # or restore tag: 8.8.0-alpine in redis-helmrelease.yaml
git push
```

Confirm recovery:
```bash
kubectl get deploy -n office affine-redis \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # back to redis:8.8.0-alpine
kubectl get pods -n office | grep affine-redis                    # Ready, 0 restarts
kubectl get helmrelease -n office affine-redis \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
```

## 6) Interference notes

- **Blast radius is one app.** `affine-redis` is a **dedicated** cache
  (ClusterIP `affine-redis:6379`) consumed only by the AFFiNE app. It is **not**
  a shared Redis. Other `office`-namespace workloads (nextcloud, nextcloud-mcp,
  arag-web, paperless-ai, actual-budget, omni-tools, affine-pg) do not use it and
  are unaffected — hence `shared: []`.
- **No storage risk.** No PVC is mounted on redis; persistence is disabled
  (`--save "" --appendonly "no"`). Storage-safety pre-flight is N/A. The only
  Longhorn volumes in this app (affine-config, affine-storage, affine-pg-data)
  are **not touched**.
- **Transient affine impact only.** During the Recreate swap the running AFFiNE
  pod briefly loses its redis connection and reconnects within seconds; expect a
  short burst of redis-connection log lines, not a restart. The `wait-for-redis`
  initContainer only gates a *fresh* affine pod start, so no affine restart is
  triggered by this change.
- **Ordering / conflicts.** Keep this out of the same window as any future
  AFFiNE **app**-image plan (`conflicts_with` would list it) so the two changes
  are verified independently — today no such plan exists, so `conflicts_with: []`.
- **No reboot, no operator presence required.** Fits any no-reboot weekday slot
  (mon/tue/wed/thu/fri/sat); Sunday's reboot-capable window is not needed. Risk
  weight 1 (low) — trivially fits `capacity_risk: 6`.
- **Policy flag for the operator/window agent:** the `*affine*` deny rule is
  over-broad — it holds this stock-redis sidecar under a reason written for the
  AFFiNE server image. Consider narrowing the rule in
  `runbooks/auto-update-policy.yaml` so `affine-redis` (and future non-app
  sidecars) can flow through the safe lane. Policy edit, not part of executing
  this plan.
