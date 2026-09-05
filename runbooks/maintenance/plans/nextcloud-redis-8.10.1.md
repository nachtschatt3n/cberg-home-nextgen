---
plan_id: nextcloud-redis-8.10.1
component: nextcloud-redis
pr: null                          # coverage.py needs_plan — no open Renovate PR (plain
                                  # Deployment manifest, not a HelmRelease/chart)
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
    - deployment/nextcloud-redis
    - service/nextcloud-redis        # unchanged, listed for completeness
    - deployment/nextcloud           # transient reconnect; PHP SESSIONS stored here are lost
    - deployment/nextcloud-notify-push  # holds a redis connection too, reconnects
  shared: []                        # dedicated cache for nextcloud only; no shared datastore,
                                    # no ingress/cilium/coredns/longhorn perturbation
depends_on: []
conflicts_with: [bitnamilegacy-exit-nextcloud-db]   # both touch office/nextcloud's data-plane
                                                     # wiring; keep the redis patch out of the
                                                     # same window as the DB cutover so any
                                                     # regression is attributable to one change
security_ref: null                 # no sweep finding dispatched this refresh; driver is the
                                   # upstream security-classified patch, detail stays upstream
capability_change: false
rollback_class: git-revert
finding_refs: []
status: draft
window: null
# auto_execute RETIRED 2026-08-26 (P2.1b) — execution class is now DERIVED
# from capability_change/rollback_class per runbooks/autonomy-policy.yaml.
sops_refs:
  - docs/sops/application-update.md
generated: "2026-09-05"
---

# nextcloud-redis 8.10.0-alpine → 8.10.1-alpine

## 1) Summary & why held

`nextcloud-redis` is a **stock Docker Hub `redis` image** run as a **plain
Kustomize `Deployment`** (`kubernetes/apps/office/nextcloud/app/redis-deployment.yaml`,
listed directly in that folder's `kustomization.yaml`) — it is **not** a
HelmRelease and **not** part of the `nextcloud` chart's bundled/subchart redis.
That bundled Bitnami redis was retired 2026-08-19 (security driver `F-d62ac46a`,
archived `bitnamilegacy` registry) and replaced with this official image,
wired to the `nextcloud` chart's `externalRedis` block (`host: nextcloud-redis`,
`redis.enabled: false`). Only the image tag moves in this plan:
`redis:8.10.0-alpine → 8.10.1-alpine`. The Nextcloud **app** image
(`nextcloud:34.0.3`, chart `9.2.5`) is **not** touched.

**Why it was held — and why the reason does not actually apply here.** The
held-update dispatch cites: *"chart+image must bump together and run occ
migrations (nextcloud coupling)."* That is the `*nextcloud*` catch-all rule in
`runbooks/auto-update-policy.yaml`:

> "chart+image must bump together and run occ migrations (Mail custom_app /
> stuck-maintenance trap) — operator-supervised only."

That rule is written for the **Nextcloud server** — chart version, app image,
and `occ upgrade` migrations move together and can strand the instance in
maintenance mode (see `project_nextcloud_upgrade_mailapp` memory). It has
**nothing to do with this Deployment**: `nextcloud-redis` runs no `occ`
command, is reconciled by a Flux `Kustomization` not a `HelmRelease`, has its
own independent version stream from `library/redis` on Docker Hub, and its
only relationship to the nextcloud chart is one config value
(`externalRedis.host`) that does not change here. The glob simply also
matches the string "nextcloud" in the component name — the exact same failure
mode already documented for `nextcloud-mcp` immediately above this rule in the
policy file (a real, unrelated component swallowed by a broad `*nextcloud*`
match). **Verdict: this is a policy false positive, not a genuine coupling.**
The image can move independently of the chart/app version and does not need
to wait for or accompany a nextcloud chart bump. Flagging for the operator to
narrow the deny rule (add a `*nextcloud-redis*` carve-out above the
`*nextcloud*` line, same pattern already used for `nextcloud-mcp`) is out of
scope for this plan itself.

**What 8.10.1 is.** Upstream marks the 8.10.1 release urgency **SECURITY** — a
patch release consisting of security remediations, with no documented bug
fixes, breaking changes, persistence-format changes, or protocol/command
changes (same release already executed for `affine-redis` today, commit
`ea99ab5d`, and green). Item-level vulnerability detail is deliberately not
restated here — public-repo rule, `docs/sops/vulnerability-disclosure.md`.
Deployment context that bounds exposure: `nextcloud-redis` is a **dedicated
ClusterIP cache** (`nextcloud-redis:6379`, LAN-only cluster), runs **without
TLS** and **without any persistence** (`--save "" --appendonly "no"`, no
PVC — see the deployment manifest's header comment), so it never loads RDB
payloads at all.

**What this redis actually holds — read before treating a restart as free.**
Unlike `affine-redis` (pure cache/pub-sub, no session data), `nextcloud-redis`
backs three distinct Nextcloud subsystems via `redis.config.php` +
`memcache.distributed` / `memcache.locking` in `custom.config.php`:
distributed cache, **file locking** (`filelocking.enabled: true`), and **PHP
session storage**. Steady-state size ~140–800 keys depending on load (current
live `dbsize` at investigation time: 714, `connected_clients: 19`). None of it
is durable by design (no PVC, no AOF/RDB) — but that also means **a restart
does not "restore" the sessions, it discards them**, unlike a redis with
persistence where a crash/restart at least re-reads its last snapshot.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) nextcloud stack currently healthy
kubectl get pods -n office | grep -E 'nextcloud(-redis|-notify-push)?-'
flux get kustomizations -n flux-system | grep -i office

# b) confirm what is actually running now (expect redis:8.10.0-alpine)
kubectl get deploy -n office nextcloud-redis \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'

# c) confirm redis is truly non-persistent (expect --save "" --appendonly no; NO pvc)
kubectl get deploy -n office nextcloud-redis \
  -o jsonpath='{.spec.template.spec.containers[0].command}{"\n"}'
kubectl get pvc -n office | grep -i nextcloud-redis || echo "no redis PVC (expected)"

# d) target tag exists — and the phantom next tag still does not (re-verified
#    2026-09-05: 8.10.1-alpine -> 200, 8.10.2-alpine -> 404, 8.11.0-alpine -> 404)
curl -s -o /dev/null -w '8.10.1-alpine -> %{http_code}\n' \
  https://hub.docker.com/v2/repositories/library/redis/tags/8.10.1-alpine
curl -s -o /dev/null -w '8.10.2-alpine -> %{http_code} (expect 404)\n' \
  https://hub.docker.com/v2/repositories/library/redis/tags/8.10.2-alpine
curl -s -o /dev/null -w '8.11.0-alpine -> %{http_code} (expect 404)\n' \
  https://hub.docker.com/v2/repositories/library/redis/tags/8.11.0-alpine

# e) baseline for the §4 contents assertion
POD=$(kubectl get pods -n office -l app=nextcloud-redis -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n office "$POD" -- redis-cli dbsize
kubectl exec -n office "$POD" -- redis-cli info clients | grep connected_clients

# f) how many users are logged in right now (sessions this bump will drop) —
#    approximate via active PHP session keys; exact count is not critical,
#    the point is knowing it is non-zero before proceeding at a busy moment
kubectl exec -n office "$POD" -- redis-cli --scan --pattern '*session*' | wc -l

# g) no in-flight reconcile / conflicting plan running this window
flux get kustomizations -n flux-system | grep -E 'office' || true
```

Proceed only if the stack is Ready, redis shows `--save "" --appendonly no`, no
redis PVC exists, and `8.10.1-alpine` returns 200 (with `8.10.2-alpine` and
`8.11.0-alpine` still 404).

## 3) Steps (GitOps)

No alert silence or rollback-disable needed (low-risk, non-migration sidecar,
plain Deployment not a HelmRelease) — `docs/sops/application-update.md` §5
Example A path.

1. Edit the redis image tag:

   File: `kubernetes/apps/office/nextcloud/app/redis-deployment.yaml`
   ```yaml
   # spec.template.spec.containers[0].image
       - name: redis
         image: redis:8.10.1-alpine   # was 8.10.0-alpine
   ```

2. Commit + push (work directly on `main`, no feature branch; `--only` so a
   concurrent session's staged hunks cannot ride along):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git commit --only kubernetes/apps/office/nextcloud/app/redis-deployment.yaml \
     -m "chore(nextcloud): redis 8.10.0-alpine -> 8.10.1-alpine (upstream security patch; non-persistent cache/lock/session store)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012bXdxrZGGHNy5e4RnF6seD"
   git show --stat HEAD   # verify: exactly this one file
   git push
   ```

3. Let Flux reconcile (webhook). The Deployment uses `strategy: Recreate`
   (deliberate — see the manifest's header comment: avoids two lock
   namespaces answering `nextcloud-redis` simultaneously during the swap), so
   the old pod fully terminates before the new one starts. Do **not**
   hand-delete pods.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# new image is live
kubectl get deploy -n office nextcloud-redis \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # expect redis:8.10.1-alpine

# redis pod Ready, 0 restarts after settle
kubectl get pods -n office | grep nextcloud-redis
POD=$(kubectl get pods -n office -l app=nextcloud-redis -o jsonpath='{.items[0].metadata.name}')
```

### CONTENTS ASSERTION — `PING` → `PONG` is NOT verification

`PONG` is answered identically by a freshly-initialised, empty redis and by
one correctly serving Nextcloud's cache/lock/session traffic. A `Recreate`
swap onto a wrong Service selector or a silently-failed image pull would still
often show `Ready` on the pod while nothing behind it is real.

**CONTENTS ASSERTION: a real write/read round-trip, plus live client/keyspace
state climbing back to baseline.**

```bash
# a) round-trip — write a throwaway key and read the exact bytes back
kubectl exec -n office $POD -- redis-cli set __verify_$$ ok EX 60
kubectl exec -n office $POD -- redis-cli get __verify_$$      # MUST echo: ok
kubectl exec -n office $POD -- redis-cli del __verify_$$

# b) the app REPOPULATED it. Non-persistent by design (no PVC, no
#    save/appendonly), so dbsize=0 immediately after the Recreate is CORRECT.
#    The property to assert is "state comes BACK", not "state survived":
kubectl exec -n office $POD -- redis-cli dbsize          # 0 right after swap: expected
#    ...then exercise the app (open Nextcloud in a browser, browse a folder,
#    trigger a file operation) and re-measure within a few minutes:
kubectl exec -n office $POD -- redis-cli dbsize          # MUST climb back toward the
                                                          # pre-check (e) baseline order
                                                          # of magnitude (baseline: 714)
kubectl exec -n office $POD -- redis-cli info clients | grep connected_clients
                                                          # MUST return to ~pre-check (e)
                                                          # baseline (baseline: 19), not 0
#    Still near-0 after real app traffic => nextcloud is not using this redis
#    (wrong host/port, silent client failure). STOP and investigate.

# c) the CONSUMER actually reconnected — assert from the app side too
kubectl logs -n office deploy/nextcloud --since=3m | grep -iE 'redis|econnrefused|error' | tail -20 || true
kubectl logs -n office deploy/nextcloud-notify-push --since=3m | grep -iE 'redis|econnrefused|error' | tail -20 || true

# d) file locking actually works post-swap (the property most likely to
#    silently break if memcache.locking pointed at the wrong host): open a
#    file for editing in the Nextcloud web UI in two sessions/tabs and
#    confirm the SECOND gets a lock-conflict warning, not silent overwrite.
```

Success = new pod Ready 0 restarts after ~2 min, **set/get round-trip returns
the written value, `connected_clients` and `dbsize` climb back to baseline
order of magnitude once Nextcloud is exercised**, no redis error bursts in the
nextcloud / notify-push logs beyond the expected few-second reconnect blip,
and file locking (memcache.locking) demonstrably still works.

## 5) Rollback

Single-file revert — the change is one image tag; the cache/session store is
disposable by design so there is no data to restore (session loss already
happened at the forward swap and is not reversible either way).

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <commit-sha>     # or restore tag: 8.10.0-alpine in redis-deployment.yaml
git push
```

Confirm recovery:
```bash
kubectl get deploy -n office nextcloud-redis \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # back to redis:8.10.0-alpine
kubectl get pods -n office | grep nextcloud-redis                 # Ready, 0 restarts
kubectl exec -n office $(kubectl get pods -n office -l app=nextcloud-redis -o jsonpath='{.items[0].metadata.name}') -- redis-cli ping
```

## 6) Interference notes

- **Blast radius is one app's cache/lock/session tier**, not a shared
  datastore. `nextcloud-redis` is consumed only by `deployment/nextcloud` and
  `deployment/nextcloud-notify-push` in the `office` namespace. `nextcloud-mcp`,
  `whiteboard-proxy`, and every other `office` workload (arag-web, paperless,
  affine, actual-budget, omni-tools) do not touch it — hence `shared: []`.
- **User-visible impact: every currently logged-in Nextcloud user is logged
  out.** PHP sessions live in this redis with no persistence; the `Recreate`
  swap discards them outright (not "may survive a fast swap" — sessions are
  gone the moment the old pod terminates). This is a real, if minor,
  disruption: users must log back in (desktop/mobile sync clients typically
  hold a separate long-lived app token and are less affected than the web UI).
  Prefer a lower-traffic window slot; no maintenance-mode banner is needed
  since this is not an `occ` migration.
- **File locking drops for the swap duration.** `filelocking.enabled: true`
  backed by `memcache.locking = Redis` means any file open for editing during
  the few seconds of `Recreate` transition loses its lock; a concurrent editor
  could in principle race. Low likelihood at a scheduled low-traffic window,
  but worth knowing — this is different from `affine-redis`, which has no
  locking semantics.
- **No storage risk.** No PVC is mounted on `nextcloud-redis`; persistence is
  disabled (`--save "" --appendonly "no"`). Storage-safety pre-flight is N/A.
  The nextcloud data PVC and mariadb PVC are untouched.
- **Ordering / conflicts.** `conflicts_with: [bitnamilegacy-exit-nextcloud-db]`
  — that plan also perturbs `office/nextcloud`'s data-plane wiring (the
  replacement mariadb standup). Running both in the same window would make a
  regression hard to attribute to one change. No other office plan is known
  to touch `nextcloud-redis`.
- **No reboot, no operator presence strictly required** given the low risk and
  precedent (identical bump for `affine-redis` executed today, commit
  `ea99ab5d`, green) — but because this redis holds live user sessions (unlike
  `affine-redis`), prefer an attended low-traffic slot over the unattended
  nightly lane so a session-logout complaint has an operator immediately
  available, rather than defer solely on risk grounds.
- **Version drift guard.** Target re-verified 2026-09-05: `8.10.1-alpine` is
  the newest published 8.10.x/alpine tag (`8.10.2-alpine` and `8.11.0-alpine`
  both 404). If either starts returning 200 by execution time, refresh this
  plan rather than executing against a superseded target.
- **Policy flag for the operator/window agent:** the `*nextcloud*` deny rule
  in `runbooks/auto-update-policy.yaml` is over-broad for this component —
  it holds `nextcloud-redis`'s independent image stream under a reason
  written for the Nextcloud **server**'s chart+occ coupling, which does not
  apply (plain Deployment, no chart, no occ). Recommend adding a
  `*nextcloud-redis*` carve-out above the `*nextcloud*` line, the same
  pattern already used for `nextcloud-mcp` immediately above it. Policy edit,
  out of scope for this plan.
