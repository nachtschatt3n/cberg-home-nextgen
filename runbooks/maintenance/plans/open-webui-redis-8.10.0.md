---
plan_id: open-webui-redis-8.10.0
component: open-webui-redis
pr: null                          # Trivy-driven hold, not a Renovate PR — tag is a chart
                                  # default (websocket.redis.image.tag), nothing in git for
                                  # Renovate to bump, so no open PR exists. See Summary.
kind: image
current: "7.4.2-alpine3.21"
target: "8.10.0-alpine"
update_type: major                # redis 7 -> 8 major jump
risk: medium                      # major-version gate held it; actual blast radius is small
                                  # (ephemeral pub/sub redis, no persistence, no ACL/modules)
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/open-webui
    - deployment/open-webui-redis
  shared: []                      # no shared infra: this is open-webui's OWN bundled
                                  # websocket redis. It is NOT the databases/redis shared
                                  # instance, NOT langfuse-redis, NOT any bitnami redis.
depends_on: []
conflicts_with: []
status: executed                    # thu-early:2026-08-13 operator-approved, SUCCESSFUL (commit 03541f0f).
                                    # Serialized AFTER langfuse-3.225.1 as required (shared ai ns).
                                    # Pinned websocket.redis.image.tag; verified with `helm template` against chart
                                    # 16.0.0 BEFORE commit that it renders open-webui-redis -> redis:8.10.0-alpine
                                    # (the values path is a chart default, so a wrong path would silently no-op).
                                    # GOTCHA: the first `flux reconcile helmrelease` ran before the Kustomization had
                                    # synced the new HR spec, so Helm upgraded with the OLD values and the deployment
                                    # still showed 7.4.2 while the HR reported Ready. A second reconcile (after the HR
                                    # spec carried the pin) applied it. Check the DEPLOYMENT image, not just HR Ready.
                                    # RESULT: redis 8.10.0 standalone, PING=PONG, SET/GET probe OK, open-webui
                                    # reconnected. CVEs: 7.4.2-alpine3.21 had 6 fixable CRITICAL
                                    # (CVE-2023-24538/24540, CVE-2024-24790, CVE-2025-68121, CVE-2026-31789)
                                    # -> 8.10.0-alpine has 0. Ingress /health = 200 {"status":true}.
                                    # SIDE EFFECT (handled): the redis pod swap killed open-webui's asyncio task
                                    # periodic_session_pool_cleanup ("Connection closed by server", Task finished ->
                                    # does NOT self-restart; it had been ticking every 2 min until 06:46:51). The
                                    # app pod itself did NOT roll on the Helm upgrade, as the plan predicted, so the
                                    # dead task would have persisted silently. Fixed with a rollout restart of
                                    # statefulset/open-webui (safe: durable data on open-webui-20g PVC); task
                                    # confirmed ticking again at 06:53:58. FUTURE RUNS: expect this and plan the
                                    # app restart as a step, not an afterthought.
                                    # PRE-EXISTING (not caused by this upgrade, left alone): that cleanup task logs
                                    # "Unable to renew session cleanup lock. Retrying cleanup ownership." every 2 min
                                    # on BOTH redis 7.4.2 and 8.10.0. Worth a separate look, out of scope here.
window: "thu-early:2026-08-13"       # CVE remediation batch (no-reboot); window-agent sequences w/ the others
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-06"
---

# open-webui-redis 7.4.2-alpine3.21 → 8.10.0-alpine

## 1) Summary & why held

**What runs 7.4.2-alpine3.21.** Exactly one workload in the cluster runs the
official `redis:7.4.2-alpine3.21` image: **`deployment/open-webui-redis`** in
namespace **`ai`**. It is the **bundled websocket/pub-sub Redis** deployed by the
`open-webui` Helm chart (`spec.chart.version: 16.0.0`,
`kubernetes/apps/ai/open-webui/app/helmrelease.yaml`). Its **only consumer** is
Open WebUI itself, which uses it as the Socket.IO websocket manager
(`values.websocket.manager: redis`, `values.websocket.url:
redis://open-webui-redis:6379/0`).

**This is not any of the other redis instances.** All other redis in the cluster
are already on 8.x or are a different image, and are out of scope:
- `databases/redis` → `redis:8.10.0-alpine` (already 8.x — proves the target tag)
- `office/sure`, `office/affine`, `download/tube-archivist` → `redis:8.8.0-alpine`
- `ai/langfuse-redis` → `redis:8.8.0-alpine`
- `databases/superset`, `office/nextcloud`, `office/paperless-ngx` →
  `bitnamilegacy/redis:*` (different image, different versioning)
- `office/penpot` → `valkey/valkey:9.1.1`

**Why the tag isn't in git.** The tag is the **open-webui chart default** at
`websocket.redis.image.tag` (chart `values.yaml` lines ~85–108). The HelmRelease
does not currently pin it, so the running image tracks whatever the chart ships.
Because nothing in git references `7.4.2-alpine3.21`, Renovate has no artifact to
bump — this hold originates from the **fresh Trivy scan (2026-08-06): 6 fixable
CRITICAL CVEs** on the image, not from a Renovate PR (hence `pr: null`). Pinning
the tag in the HelmRelease is therefore a net improvement on its own: it stops
the image silently tracking the chart default.

**Why it was held (the gate): redis 7 → 8 is a MAJOR jump.** The auto-updater's
major-version gate holds any 7.x→8.x bump regardless of consumer, because
redis 8 has real breaking changes for *some* deployments.

**7 → 8 breaking-change analysis (the load-bearing risk).** The redis 8 breaking
changes are:
1. **Modules bundled into core** (RediSearch/RedisJSON/RedisTimeSeries/RedisBloom).
   Only matters if you *use* those modules. Open WebUI does not — it issues
   plain SET/GET/PUB/SUB via the Socket.IO redis manager.
2. **ACL category changes** (`@read`/`@write`/`@dangerous`/etc. now cover the new
   data-structure commands). Only matters if you define ACLs. This instance has
   **no ACL and no auth** (default config, empty password, cluster-internal
   service only).
3. **RDB/AOF on-disk format.** Not applicable: this redis is **ephemeral** —
   `deployment/open-webui-redis` has **no volumes and no PVC** (verified). Nothing
   is persisted; a restart flushes all keys, which is expected and harmless for a
   websocket/pub-sub manager.
4. **Licensing** (AGPLv3 tri-license from 8.0). Not a runtime concern.
5. **Wire protocol.** RESP2/RESP3 are backward-compatible for the SET/GET/PUB/SUB
   surface Socket.IO uses.

**Verdict: LOW real risk despite the MAJOR label.** For *this* consumer none of
the redis 8 breaking changes apply (no modules, no ACL/auth, no persistence). The
target tag `8.10.0-alpine` is already **proven in this same cluster** by
`databases/redis`. No consumer is a blocker. It is filed `risk: medium` and
routed to an operator-present window purely because it is a major-version bump
per the update SOP's "Attended (major)" tier — not because data or the consumer
is fragile.

**Blast radius.** Single namespace `ai`. Worst realistic case: the redis pod
fails to start on 8.x → Open WebUI loses real-time websocket sync (multi-tab live
updates / streaming push) until reverted. Core chat + the app's durable data are
unaffected: Open WebUI's persistent data lives in the `open-webui-20g` PVC
(app DB/config), **not** in redis. No data-loss path exists here.

## 2) Pre-checks

```bash
# a) Confirm the ONLY consumer of 7.4.2-alpine3.21 is open-webui-redis (no surprises)
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{range .spec.containers[*]}{.image}{"\n"}{end}{end}' \
  | grep '7.4.2-alpine3.21'
# expect exactly: ai   redis:7.4.2-alpine3.21

# b) Confirm the redis workload is ephemeral (no PVC / no volumes) — no data to lose
kubectl get deploy -n ai open-webui-redis -o jsonpath='{.spec.template.spec.volumes}{"\n"}'
# expect: empty
kubectl get pvc -n ai | grep -i redis    # expect: no rows

# c) Target tag exists / is pullable
curl -s "https://hub.docker.com/v2/repositories/library/redis/tags/8.10.0-alpine" -o /dev/null -w '%{http_code}\n'
# expect: 200   (and it is already running as databases/redis)

# d) Cluster + Flux healthy, no in-flight reconcile on this HR
flux get helmrelease -n ai open-webui
kubectl get hr -n ai open-webui -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # True
flux get kustomizations -A | awk 'NR==1 || $5!="True"'   # only header => all Ready

# e) Open WebUI itself healthy pre-change
kubectl get pods -n ai -l app.kubernetes.io/name=open-webui
kubectl get deploy -n ai open-webui-redis
```

## 3) Steps (GitOps — follow docs/sops/application-update.md)

This is a `values` override, not an in-place tag edit (the current tag is a chart
default that isn't in git). Add a `websocket.redis.image` pin.

1. **Optional (SOP §1): silence + active-update marker.** The redis pod restart
   causes a brief websocket blip and a possible `KubePodNotReady`/`Kube*` flap.
   ```bash
   runbooks/update-marker.sh add open-webui ai 2 "redis 7->8 (websocket manager)"
   ```
   A full Alertmanager silence (SOP §1) is optional here given the ~1-pod, ~15s blip.

2. **Edit** `kubernetes/apps/ai/open-webui/app/helmrelease.yaml`. In the existing
   `values.websocket` block (currently only `enabled` + `url`), add a `redis`
   subsection pinning the image. Final block:
   ```yaml
       websocket:
         # -- Enables websocket support in Open WebUI with env `ENABLE_WEBSOCKET_SUPPORT`
         enabled: true
         # -- Explicit Redis URL to preserve service name after chart 12.x naming convention change
         url: "redis://open-webui-redis:6379/0"
         # Pin the bundled websocket Redis image. The chart default is
         # redis:7.4.2-alpine3.21, which carries 6 fixable CRITICAL CVEs
         # (Trivy 2026-08-06). Redis 8 is safe for this use: ephemeral pub/sub
         # only — no persistence, no ACL/auth, no modules. 8.10.0-alpine is
         # already proven by databases/redis in this cluster.
         redis:
           enabled: true
           image:
             repository: redis
             tag: 8.10.0-alpine
             pullPolicy: IfNotPresent
   ```
   Path reference: chart `values.yaml` nests the bundled redis at
   `websocket.redis.image.{repository,tag,pullPolicy}` (chart 16.0.0).

3. **Validate render locally** before commit:
   ```bash
   task template:configure -- --strict
   kubeconform -summary kubernetes/apps/ai/open-webui
   ```

4. **Commit + push** (work on `main`, per repo policy). Flux reconciles.
   ```bash
   git add kubernetes/apps/ai/open-webui/app/helmrelease.yaml
   git commit -m "fix(open-webui): pin websocket redis 7.4.2-alpine3.21 -> 8.10.0-alpine (6 CRITICAL CVEs)"
   git push
   ```
   Do not manually `flux reconcile` unless the reconcile stalls (SOP default:
   let the webhook drive it).

## 4) Verification

```bash
# a) HelmRelease reconciled + Ready
kubectl get hr -n ai open-webui -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # True

# b) redis pod now on 8.10.0-alpine, Ready, 0 restarts after settle
kubectl get deploy -n ai open-webui-redis -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'  # redis:8.10.0-alpine
kubectl get pods -n ai -l app=open-webui-redis -o wide   # 1/1 Running
kubectl exec -n ai deploy/open-webui-redis -- redis-cli PING     # PONG
kubectl exec -n ai deploy/open-webui-redis -- redis-cli INFO server | grep redis_version  # 8.10.x

# c) Open WebUI reconnected to redis (websocket manager healthy) — no error spam
kubectl logs -n ai statefulset/open-webui --tail=50 | grep -iE "redis|websocket|socket" | tail
#   expect a clean reconnect, no "connection refused" / "WRONGTYPE" / protocol errors

# d) Open WebUI still serving + durable data intact (data lives on open-webui-20g, not redis)
kubectl get pods -n ai -l app.kubernetes.io/name=open-webui   # Running, Ready
#   Operator smoke test: load open-webui.<DOMAIN>, open a chat in two tabs,
#   confirm live streaming/real-time updates work (exercises the redis websocket manager).
```

Success = redis on 8.10.0-alpine + PONG + reported version 8.x, Open WebUI Ready
with a clean redis reconnect, and multi-tab live updates working.

## 5) Rollback

The change is a single values addition; reverting restores the chart-default
(7.4.2) redis. **No data considerations** — the redis is ephemeral, so the
restart-flush on either direction is expected and harmless; Open WebUI's durable
data is untouched on `open-webui-20g`.

```bash
# Revert the commit (preferred — exact restore)
git revert --no-edit <this-commit-sha>
git push
# or restore just the file from the pre-change commit:
# git checkout <known-good-sha> -- kubernetes/apps/ai/open-webui/app/helmrelease.yaml
#   git commit -m "revert(open-webui): websocket redis back to chart default" && git push

# If Flux is wedged on the HR:
flux reconcile helmrelease -n ai open-webui --force

# Confirm back to known-good
kubectl get deploy -n ai open-webui-redis -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl get pods -n ai -l app.kubernetes.io/name=open-webui   # Ready

# Clear the marker either way
runbooks/update-marker.sh clear open-webui
```

## 6) Interference notes

- **Isolated blast radius.** Touches only `ai/open-webui` (HelmRelease) and its
  own `ai/open-webui-redis` Deployment. `shared: []` — this is Open WebUI's
  private websocket redis; it does **not** touch the shared `databases/redis`,
  `ai/langfuse-redis`, any `bitnamilegacy/redis`, or `penpot` valkey. No
  ingress-controller, cert-manager, cilium, coredns, or shared-DB perturbation.
- **Brief websocket blip.** The redis Deployment does a normal rolling replace
  (~10–20s). During that window Open WebUI's real-time websocket push
  (multi-tab live updates, streaming UI) drops and auto-reconnects; in-flight
  LLM generations continue server-side. Prefer a low-traffic window.
- **Open WebUI pod should NOT restart.** Only the `websocket.redis.image` value
  changes; the open-webui StatefulSet spec is unchanged, so the Helm upgrade
  should not roll the app pod. If it does roll, that is still safe (durable data
  on PVC).
- **No ordering constraints.** `depends_on: []`, `conflicts_with: []`. Can share
  a window with unrelated plans; nothing else consumes this redis.
- **needs_reboot: false** — no node/Talos involvement.
- **Note for the window agent:** `pr: null` is intentional — this is a
  Trivy-CVE-driven hold on a chart-default image tag, not a Renovate PR. Do not
  wait on / look for a PR to merge; the action IS the values pin in step 3.
