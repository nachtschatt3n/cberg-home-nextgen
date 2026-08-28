---
plan_id: affine-redis-8.10.0      # kept from original generation (refresh 2026-08-28;
                                  # window/tracking references key on this id — do not rename)
component: affine-redis
pr: null                          # coverage.py needs_plan — no open Renovate PR
kind: image
current: "8.10.0-alpine"
target: "8.10.1-alpine"
update_type: security             # upstream classifies 8.10.1 urgency SECURITY (patch step)
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
security_ref: null                 # no sweep finding dispatched this refresh; driver is the
                                   # upstream security-classified patch, detail stays upstream (see §1)
capability_change: false
rollback_class: git-revert
finding_refs: []
status: draft
window: null                       # window agent assigns — any no-reboot weekday slot (mon/tue/wed/thu/fri/sat)
# auto_execute RETIRED 2026-08-26 (P2.1b) — execution class is now DERIVED
# from capability_change/rollback_class per runbooks/autonomy-policy.yaml.
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-28"            # refreshed; original plan (8.8.0→8.10.0) generated 2026-08-16
---

# affine-redis 8.10.0-alpine → 8.10.1-alpine

## 1) Summary & why held

`affine-redis` is a **stock Docker Hub `redis` image** run as AFFiNE's ephemeral
cache/queue. Only its image tag moves here: `redis:8.10.0-alpine →
8.10.1-alpine` (upstream patch step). The AFFiNE application image
(`ghcr.io/toeverything/affine`) is **not** touched by this plan.

**Refresh history (2026-08-28).** The original edition of this plan targeted
`8.8.0 → 8.10.0`; that bump has since landed (deployed image verified
`redis:8.10.0-alpine`, pod Ready 0 restarts, manifest tag matches). Upstream
then released **8.10.1**, so the version sweep flagged the plan stale. Ground
truth re-verified against Docker Hub on 2026-08-28: `8.10.1-alpine` → HTTP 200;
**`8.10.2-alpine` → 404 and `8.11.0-alpine` → 404** — 8.10.1-alpine is the
newest published 8.10.x/alpine tag. Do NOT plan or bump toward "8.10.2"; that
tag does not exist. `plan_id` retained from the original generation so window
tracking stays continuous.

**What 8.10.1 is.** Upstream marks the 8.10.1 release urgency **SECURITY** — a
patch release consisting of security remediations, with no documented bug fixes,
breaking changes, persistence-format changes, or protocol/command changes.
Item-level detail lives in the upstream redis 8.10.1 GitHub release notes and is
**deliberately not restated here** (public-repo vulnerability-disclosure rule —
see `docs/sops/vulnerability-disclosure.md`). Deployment context that bounds the
exposure: this redis is a **dedicated ClusterIP cache** (`affine-redis:6379`,
LAN-only cluster, single trusted client), runs **without TLS** and **without any
persistence** (`--save "" --appendonly "no"`, no PVC), so it never loads RDB
payloads at all — several of the patched classes simply have no code path here.
Treat the bump as prompt hygiene, not an emergency.

**Why it was held — still a policy false positive.** No open Renovate PR;
`coverage.py` attributes the hold to the `*affine*` deny rule in
`runbooks/auto-update-policy.yaml`:

> "affine chart/image bumps carry breaking env→config.json changes even on patch
> tags (0.27.3) — hold for manual review."

That reason is about the **AFFiNE server image's** env → `config.json` migration
surface. It has nothing to do with the plain upstream Redis cache image; the
glob simply also catches the `affine-redis` HelmRelease name.

**Why the residual risk is genuinely low:**
- The redis container runs **with no persistence at all** — verbatim args
  `--save "" --appendonly "no"` (see `redis-helmrelease.yaml`). No PVC, no RDB,
  no AOF: on-disk-format change classes cannot apply across the restart.
- AFFiNE uses it as a standard cache/pub-sub over `affine-redis:6379`; a
  same-minor patch step carries no command/protocol movement.
- Upstream documents 8.10.1 as fixes-only (see above), no behavioural change.

The proper long-term fix is still to tighten the deny rule so it does not
swallow the sidecar (scope it to the affine app image, or allow-list
`affine-redis`); that is an **operator/policy change, out of scope for this
plan** — flagged again for the window agent to raise.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) affine stack currently healthy (all three Ready, 0 restarts)
kubectl get pods -n office | grep -E 'affine(-pg|-redis)?-'
flux get helmreleases -n office | grep -E 'affine(-pg|-redis)?\b'

# b) confirm what is actually running now (expect redis:8.10.0-alpine)
kubectl get deploy -n office affine-redis \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'

# c) confirm redis is truly non-persistent (expect --save "" --appendonly no; NO pvc)
kubectl get deploy -n office affine-redis \
  -o jsonpath='{.spec.template.spec.containers[0].command}{"\n"}'
kubectl get pvc -n office | grep -i redis || echo "no redis PVC (expected)"

# d) target tag exists — and the phantom next tag still does not.
#    8.10.1-alpine MUST return 200. If 8.10.2-alpine has started returning 200
#    since 2026-08-28, upstream moved again: STOP and refresh this plan rather
#    than executing against a superseded target.
curl -s -o /dev/null -w '8.10.1-alpine -> %{http_code}\n' \
  https://hub.docker.com/v2/repositories/library/redis/tags/8.10.1-alpine
curl -s -o /dev/null -w '8.10.2-alpine -> %{http_code} (expect 404)\n' \
  https://hub.docker.com/v2/repositories/library/redis/tags/8.10.2-alpine

# e) baseline for the §4 contents assertion — what this redis holds under
#    normal load (it is non-persistent, so this is a LOAD baseline, not a
#    survival baseline; §4b must climb back to a comparable order of magnitude)
POD=$(kubectl get pods -n office -l app.kubernetes.io/name=affine -o name | grep redis | head -1)
kubectl exec -n office ${POD##*/} -- redis-cli dbsize
kubectl exec -n office ${POD##*/} -- redis-cli info clients | grep connected_clients

# f) no in-flight reconcile / other office plan running this window
flux get kustomizations -n flux-system | grep -E 'office|affine' || true
```

Proceed only if the stack is Ready, redis shows `--save "" --appendonly no`, no
redis PVC exists, and `8.10.1-alpine` returns 200 (with `8.10.2-alpine` still 404).

## 3) Steps (GitOps)

No alert silence or rollback-disable needed (low-risk, non-migration sidecar) —
`docs/sops/application-update.md` §5 Example A path.

1. Edit the redis image tag:

   File: `kubernetes/apps/office/affine/app/redis-helmrelease.yaml`
   ```yaml
   # spec.values.controllers.main.containers.app.image
             image:
               repository: redis
               tag: 8.10.1-alpine   # was 8.10.0-alpine
               pullPolicy: IfNotPresent
   ```

2. Commit + push (work directly on `main`, no feature branch; `--only` so a
   concurrent session's staged hunks cannot ride along):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git commit --only kubernetes/apps/office/affine/app/redis-helmrelease.yaml \
     -m "chore(affine): redis sidecar 8.10.0-alpine -> 8.10.1-alpine (upstream security patch; ephemeral cache, non-persistent)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012bXdxrZGGHNy5e4RnF6seD"
   git show --stat HEAD   # verify: exactly this one file
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
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # expect redis:8.10.1-alpine

# redis pod Ready, 0 restarts after settle
kubectl get pods -n office | grep affine-redis
POD=$(kubectl get pods -n office -l app.kubernetes.io/name=affine -o name | grep redis | head -1)
POD=${POD##*/}
```

### CONTENTS ASSERTION — `PING` → `PONG` is NOT verification

`PONG` is a liveness probe wearing a verification costume: it is answered by a
freshly-initialised, completely empty redis exactly as cheerfully as by the one
holding Affine's sessions. A `Recreate` swap onto a mis-mounted or wrong-named
PVC produces `Ready` + `PONG` + an app that has quietly lost every session.
See `docs/sops/verification-contents-not-shape.md` (cache/broker row).

**CONTENTS ASSERTION: a real write/read round-trip, plus non-empty live state.**

```bash
# a) round-trip — write a throwaway key and read the exact bytes back
kubectl exec -n office $POD -- redis-cli set __verify_$$ ok EX 60
kubectl exec -n office $POD -- redis-cli get __verify_$$      # MUST echo: ok
kubectl exec -n office $POD -- redis-cli del __verify_$$

# b) the app REPOPULATED it. Note the inversion for THIS app: affine-redis runs
#    `--save "" --appendonly no` with no PVC (pre-check c), so an empty dbsize
#    immediately after the Recreate is CORRECT, not a failure. The contents
#    property here is therefore not "state survived" but "state comes BACK" —
#    a redis that stays permanently at 0 keys while affine reports Ready means
#    the app is not actually writing to it (wrong host/port/db, silent client
#    failure), which is exactly the empty-but-healthy shape.
kubectl exec -n office $POD -- redis-cli dbsize          # 0 right after the swap: expected
#    ...then exercise the app (open Affine, load a doc) and re-measure:
kubectl exec -n office $POD -- redis-cli dbsize          # MUST be > 0 within a few minutes
kubectl exec -n office $POD -- redis-cli info keyspace   # at least one dbN with keys=N
#    Still 0 after real app traffic => affine is not using this redis. STOP.
kubectl exec -n office $POD -- redis-cli info clients | grep connected_clients
#    non-zero — the affine pods are actually holding connections

# c) the CONSUMER actually reconnected — assert from the app side, not the
#    broker side. Log in to Affine in a browser and load a document; the
#    workspace list and doc content must render with real data, not an empty
#    shell.
kubectl get pods -n office | grep -E 'affine-[0-9a-f]'
kubectl logs -n office deploy/affine --since=3m | grep -iE 'redis|econnrefused|error' | tail -20 || true
```

Success = affine-redis HR Ready, image `redis:8.10.1-alpine`, redis pod 0
restarts after ~2 min, **the set/get round-trip returns the written value,
`connected_clients` > 0, and `dbsize` climbs back above 0 once Affine is
exercised**, and Affine loads a document in the browser (a brief error burst
during the Recreate swap is expected and self-heals; because this redis is
deliberately non-persistent, session loss across the swap is expected too — see
§2c).

## 5) Rollback

Single-file revert — the change is one image tag; the cache is disposable so
there is no data to restore. (Rollback target is `8.10.0-alpine`, the currently
deployed and known-good tag.)

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <commit-sha>     # or restore tag: 8.10.0-alpine in redis-helmrelease.yaml
git push
```

Confirm recovery:
```bash
kubectl get deploy -n office affine-redis \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # back to redis:8.10.0-alpine
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
  weight 1 (low) — trivially fits `capacity_risk: 6`. Being an upstream
  security-classified patch, prefer the **next available** slot over deferral.
- **Version drift guard.** This plan was already refreshed once because the
  target moved under it (8.10.0 executed, 8.10.1 released). Pre-check (d)
  re-asserts the tag frontier at execution time; if `8.10.2-alpine` exists by
  then, refresh the plan instead of executing.
- **Policy flag for the operator/window agent:** the `*affine*` deny rule is
  over-broad — it holds this stock-redis sidecar under a reason written for the
  AFFiNE server image. Consider narrowing the rule in
  `runbooks/auto-update-policy.yaml` so `affine-redis` (and future non-app
  sidecars) can flow through the safe lane. Policy edit, not part of executing
  this plan.
