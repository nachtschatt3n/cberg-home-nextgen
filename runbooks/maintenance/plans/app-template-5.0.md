---
plan_id: app-template-5.0
component: app-template
pr: null                            # no open Renovate PR captured; deny-listed migration (auto-update-policy.yaml `*app-template*`). Bump the chart `version:` field across every wrapper by hand.
kind: chart
current: "3.7.3"
target: "5.0.0"
update_type: major
risk: high
est_duration_min: 90                # PER BATCH / per sun-window. Full migration = 1 canary + ~4 tiers ≈ 4–5 sun-windows. See §Steps.
needs_reboot: false
touches:
  namespaces:
    - ai
    - backup
    - databases
    - default
    - download
    - home-automation
    - media
    - my-software-development
    - my-software-production
    - network
    - office
  resources:
    # 59 HelmReleases at chart app-template 3.7.3 (iobroker @ 2.4.0 is OUT OF SCOPE — separate older major).
    # Every Deployment/StatefulSet these wrap is delete+recreated (immutable-selector rename, see §1).
    - helmrelease/*                 # all 59 app-template wrappers (full list in §Steps batch table)
    - deployment/*                  # every wrapped Deployment — selector changes → must be deleted so Helm recreates
    - statefulset/penpot-db         # only in-scope STS (no volumeClaimTemplates → no PVC rename)
    - service/*                     # regenerated (naming-scheme change may rename)
    - ingress/*                     # regenerated across ~11 namespaces (Homepage + external-dns re-evaluate)
    - servicemonitor/*              # regenerated; jobLabel default flips (metrics only)
  shared:
    - ingress                       # per-app Ingress objects across 11 namespaces churn (recreate); ingress-controller itself NOT upgraded
    - cloudflared                   # the external tunnel is ITSELF an app-template wrapper — its delete+recreate blips ALL externally-exposed apps; do it LAST, own tier
    # NOT touched: cert-manager, cilium/cni, coredns, longhorn (no PVC deletes; no volumeClaimTemplates in scope)
depends_on: []
conflicts_with:
  - talos-v1.13.8                   # reboot window; do not stack a mass workload churn on top of node drains.
                                    # 2026-08-15 vetting: was `talos-v1.13.7`, a plan_id that no longer
                                    # exists (that upgrade executed; its file was retired). A conflicts_with
                                    # pointing at a non-existent plan is silently UNENFORCED, so this guard
                                    # was dead. Repointed at the live successor plan.
  #
  # RESOLVED, NOT LOST (2026-08-15 vetting). Three guards were dropped here because the
  # work they protected against has already SHIPPED — you cannot contend for a window
  # with an upgrade that is done. Each verified executed before removal:
  #   flux-stack-v0.57   — executed 2026-08-11 (7ec7ad0c, 75ec407b); HelmReleases live on
  #                        chart 0.57.0, FluxInstance on v2.9.3. The concern was that a
  #                        helm-controller bump changes the Helm SDK that RENDERS these
  #                        charts. It has landed, so this plan now renders against the NEW
  #                        SDK regardless — a reason to RE-TEST the rendering assumptions
  #                        in the rewrite, not to serialize windows.
  #   authentik-2026.5.6 — retired in 9a497c19 as executed.
  #   reloader-v2        — retired in 46c8f770 as executed (chart 2.2.14).
  # Keeping them would not have been the conservative choice: maintenance-plan.py now
  # reports DEAD-REF for unresolvable ids, so they would have produced a standing warning
  # that trains the reader to ignore the check.
status: draft                       # STAYS DRAFT — 2026-08-15 vetting: inventory has DRIFTED out
                                    # from under the batch table. NEEDS A SUBSTANTIVE REWRITE, not
                                    # a note. See the "2026-08-15 vetting" block below §Scope.
window: "sat-early:2026-08-29"       # MOVED 2026-08-14 off sat-early:2026-08-15 to resolve a
                                      # three-way interference: it shares `network` with
                                      # envoy-gateway-phase0 and `default`+`network` with
                                      # phase1, which also overlap each other. The EG phases
                                      # have their own documented ordering (P0 then P1); this
                                      # plan touches ~47 HelmReleases and deserves a clean
                                      # solo window rather than competing for one.
                                    # week across Sat+Sun (both operator-present, no
                                    # reboot competes): canary Sat 08-15 → tier1 Sun
                                    # 08-16 → tier2 Sat 08-22 → tier3 Sun 08-23 →
                                    # tier4 Sat 08-29. Window-agent advances the
                                    # window as each tier passes verification. Still
                                    # SOLO per window (no other high-risk plan).
auto_execute: false                 # never unattended — risk:high
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/maintenance-windows.md
generated: "2026-08-02"
---

# app-template 3.7.3 → 5.0.0 (bjw-s common library) — cluster-wide chart migration

## 1) Summary & why held

`app-template` (bjw-s / `oci://ghcr.io/bjw-s/helm` → `common` library chart) is
the wrapper chart for **59 HelmReleases** across **11 namespaces** — from
`echo-server` to `home-assistant`, the external `cloudflared` tunnel, and a
dozen per-app Postgres/Redis/Elasticsearch sidecars. Renovate wants to jump the
chart **two majors, 3.7.3 → 5.0.0**. It is explicitly deny-listed in
`runbooks/auto-update-policy.yaml` (`*app-template*`) precisely because one bump
touches ~all of user-space at once — this is a coordinated **migration**, not a
version bump.

**In scope:** the 59 wrappers pinned at `version: 3.7.3` (full batch table in
§3). **Out of scope:** `home-automation/iobroker` is on `2.4.0` (an even older
major) and is NOT tracked to 5.0.0 here — leave it, plan it separately.

> ### ⚠️ STALENESS — 2026-08-15 vetting pass: DO NOT EXECUTE THIS PLAN AS WRITTEN
>
> This plan was authored 2026-08-02 against a **59-wrapper** inventory. Live
> inventory on 2026-08-15 is **62 HelmReleases at `app-template` 3.7.3** across
> the same 11 namespaces (60 distinct names; `absenty` and `andreamosteller`
> each appear in two namespaces). The batch table in §3 is therefore incomplete,
> and a tier-by-tier execution would silently leave wrappers behind at 3.7.3.
>
> Reproduce:
> ```bash
> kubectl get helmrelease -A -o json | python3 -c "import sys,json; d=json.load(sys.stdin); \
>   print(sum(1 for i in d['items'] if i['spec'].get('chart',{}).get('spec',{}).get('chart')=='app-template' \
>   and i['spec']['chart']['spec']['version']=='3.7.3'))"
> ```
>
> **Named nowhere in this plan (must be added to a tier before it runs):**
>
> | wrapper | ns | why it is missing |
> |---|---|---|
> | `immich-server` | media | deployed 2026-08-08, after this plan was written |
> | `immich-machine-learning` | media | same |
> | `immich-postgres` | media | same — **stateful, belongs in tier 3**, not tier 1 |
> | `immich-redis` | media | same |
> | `icloud-docker-andrea` | backup | tier 1 names only `icloud-docker-mu`; both exist |
>
> **Also wrong in the table:** tier 2 names **`scrypted-nvr`**; the live
> HelmRelease is **`scrypted`** (`home-automation`). A copy-paste execution
> targets a non-existent release.
>
> **Also gone:** the `langfuse` stack was removed in `8714dbd1`, so the 59→62
> delta is +4 immich, +1 (already-present but unnamed) icloud-docker-andrea,
> −1 langfuse, against a base that was itself approximate.
>
> **New interference not known at authoring time — `absenty` image automation.**
> `absenty` (tier 1, ×2 namespaces) had its Flux `ImageUpdateAutomation`
> **unsuspended** on 2026-08-15 and its ImagePolicy pattern changed to
> `<branch>-<ts14>` + `numerical`. Both automations are live and currently
> writing a new tag roughly every 20–30 minutes:
> ```
> my-software-development/absenty-image-updates  suspend=false
> my-software-production/absenty-image-updates   suspend=false
> ```
> They commit into the **same `helmrelease.yaml` files** this plan edits, so a
> tier-1 batch races the automation for the working tree and can land a
> half-applied chart bump or a push conflict mid-window. **Suspend both
> automations for the duration of the tier that touches `absenty`, and unsuspend
> them in the same window** — that step does not exist in §3 today.
>
> Rewrite required: regenerate the §3 batch table from live inventory, fix
> `scrypted`, tier the immich group (with `immich-postgres` treated as stateful),
> and add the absenty automation suspend/unsuspend step. A note cannot carry this.

### The breaking changes (upstream `common-4.0.0` + `common-5.0.0` changelogs)

**4.0.0 (the one that bites):**
1. **Immutable-selector rename — THE blocker.** 4.0.0 *"Renamed the hardcoded
   `app.kubernetes.io/component` label to `app.kubernetes.io/controller`."* In
   3.7.3 that label is part of the **`.spec.selector.matchLabels`** of every
   Deployment/StatefulSet. Verified live:
   ```
   echo-server  selector = {component: echo-server, instance: echo-server, name: echo-server}
   openclaw     selector = {component: openclaw,     instance: openclaw,     name: openclaw}
   penpot-db    selector = {component: penpot-db,    instance: penpot-db,    name: penpot-db}
   ```
   `.spec.selector` is **immutable**. So `helm upgrade` fails with
   `spec.selector: field is immutable` on **every one of the 59 workloads** — the
   exact superset failure (`docs/sops/application-update.md` §7), ×59. Each
   workload must be **deleted so Helm recreates it** with the new selector.
2. **Resource naming standardized** — generated resource names may change; old
   names are pruned and new ones created (Services, Ingresses, ConfigMaps,
   ServiceMonitors). Helm does this in one apply, but ingress host / Homepage /
   external-dns re-converge, so verify each app's URL after.
3. **ServiceAccounts no longer mint a static token by default** (`staticToken`).
   No in-scope app sets `staticToken` → no action, but see 5.0.0 #2.
4. Minimum Kubernetes ≥ 1.28. **Cluster is v1.36.0 — satisfied.**

**5.0.0:**
1. **`rawResources` restructured** (content moved out of `spec:` into a manifest
   wrapper). **No in-scope wrapper uses `rawResources`** (grepped) → **non-issue.**
2. **`automountServiceAccountToken` now defaults to `false`.** Any app that reaches
   the Kubernetes API via the auto-mounted SA token loses access unless it opts
   back in. In scope: **`ai/ai-sre`** (`serviceAccount.create: true`) and
   **`ai/mcpo`** (`serviceAccount.create: false, name: mcpo`) declare a
   ServiceAccount — audit + set `automountServiceAccountToken: true` where the pod
   needs the token (see §3 Step C). Also sanity-check `openclaw`, `hermes-agent`,
   `paperclip` for in-cluster API use post-5.0.
3. **Unprivileged ServiceAccount created by default** (`global.createDefaultServiceAccount`)
   — harmless, but confirm no name clash for apps that already define their own SA.
4. **ServiceMonitor/PodMonitor `jobLabel` now defaults to `app.kubernetes.io/name`**
   — the Prometheus `job` label value changes for the 4 wrappers that declare a
   `serviceMonitor` in values (`echo-server`, `cloudflared`, `zero-export-controller`,
   `solarfocus-scraper`). **Metrics-only**; check no Grafana panel / alert keys on
   the old `job=` value.
5. Minimum Kubernetes ≥ 1.31, Helm ≥ 3.18. **Cluster v1.36.0; Flux
   helm-controller v1.2.0** — verify Helm SDK ≥ 3.18 via the PR's `flux-local`
   render (Pre-check 5). If a render fails on the `kubeVersion`/helm constraint,
   STOP — that is a hard gate.

**Why this is the biggest held gap:** 59 independent HelmReleases, all wrapping
the same chart, all hitting the same immutable-selector wall, spanning the
external tunnel + several databases + all of home-automation. It cannot be a
git-only bump; it is a delete+recreate of ~59 workloads, batched and verified.

### The one thing that makes it tractable

**The 59 wrappers are independent HelmReleases.** A failure in one does **not**
block the others (Flux reconciles per-HR). So we migrate in **blast-tiered
batches**, one tier per sun-window, canary first — a bad app is contained to its
own HR, and we never "big-bang" all 59.

---

## 2) Pre-checks

Run at the start of **every** batch window (the cluster state moves between windows).

```bash
# 0. This must be a sun-window (operator present). Confirm no other high-risk plan
#    is co-scheduled — esp. flux-stack (renderer change), talos, authentik, reloader.
.venv/bin/python3 runbooks/maintenance-plan.py --json | python3 -c "import sys,json;d=json.load(sys.stdin);print('this window queue:',[p for w in d['scheduled'].values() for p in w])"

# 1. Cluster + Flux healthy, nothing already failing (don't migrate onto a red cluster)
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
kubectl get pods -A | grep -vE 'Running|Completed' | grep -v NAMESPACE || echo "all pods healthy"

# 2. Confirm k8s + helm-controller satisfy 5.0.0 floors (k8s>=1.31, helm>=3.18)
kubectl version -o json | python3 -c "import sys,json;print('k8s',json.load(sys.stdin)['serverVersion']['gitVersion'])"   # expect v1.36.x
kubectl get deploy -n flux-system helm-controller -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'

# 3. Longhorn backups fresh for the stateful wrappers in THIS batch (postgres/redis/es
#    sidecars, home-assistant, penpot-db, teslamate/traccar pg). Data lives on PVCs and
#    is NOT deleted by a workload delete — but verify a recent backup before touching DBs.
kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt --no-headers | grep -Ei '<apps-in-this-batch>'

# 4. Record the pre-state of this batch's workloads (selectors + current chart rev)
for hr in <batch HR list>; do
  echo "== $hr =="; kubectl get hr -n <ns> $hr -o jsonpath='{.status.history[0].chartVersion}{"\n"}'
done

# 5. RENDER GATE (the real safety net): render every wrapper in this batch with the
#    5.0.0 chart BEFORE touching the cluster. flux-local is what CI uses; if a wrapper
#    fails to render on 5.0.0, fix its values in the same commit or drop it from the batch.
task template:configure -- --strict            # repo-wide render/validate
kubeconform -summary -fail-on error kubernetes/apps/<batch paths>
```

**Silence + marker (attended-update SOP §Step 1):** before the batch, silence the
batch namespaces' pod/deploy alerts (they WILL churn) and drop update markers:
```bash
runbooks/update-marker.sh add app-template <ns> 3 "app-template 3.7.3->5.0.0 batch"   # per ns in the batch
# Alertmanager silence matching namespace in {ns...} + alertname ~ Kube(Pod|Deployment).* for the window TTL
```

---

## 3) Steps

**GitOps only** (edit `version:` in git, push, Flux reconciles) **+ one manual
`kubectl delete` per workload** (unavoidable — immutable selector; SOP §Step 4,
Example B). No manual `helm` mutation.

### Batching (one tier per sun-window; canary first)

| Tier | Window | Wrappers (namespace) | Why here |
|---|---|---|---|
| **0 — canary** | sun #1 (start) | `echo-server` (default) | Stateless, no data, externally ingressed → proves the exact bump→delete→reconcile→verify loop AND the cloudflared/ingress path end-to-end before touching anything that matters. |
| **1 — stateless leaves** | sun #1 (rest) | `omni-tools`, `mqttx-web`, `next-ai-draw-io`, `gas-price-monitor`, `pallet-price-monitor`, `rainbow-rescue`, `andreamosteller`×2, `absenty`×2, `opencode-andreamosteller`, `_template` (dev), `mcpo`, `hermes-agent`, `ai-sre`, `paperclip`, `nextcloud-mcp`, `paperless-ai`, `paperless-gpt`, `actual-budget`, `arag-web`, `makemkv`, `icloud-docker-mu` | No persistence or self-contained config only; low blast radius. **`ai-sre`/`mcpo` need the automount audit (Step C).** |
| **2 — home-automation** | sun #2 | `mosquitto` FIRST (many depend on the broker), then `home-assistant`, `zigbee2mqtt`, `node-red`, `esphome`, `matter-server`, `otbr`, `music-assistant-server`, `scrypted-nvr`, `trmnl-ha`, `ha-ai-harness`, `solarfocus-scraper`, `zero-export-controller`, `teslamate`(+postgres), `traccar`(+postgres) | Smart-home blast radius; do the broker first, verify HA reconnects (CLAUDE.md: HA errors are never background noise). |
| **3 — databases + office DBs + downloads** | sun #3 | `redis`, `memgraph`, `nocodb`, `phpmyadmin` (databases); `affine`(+postgres+redis), `sure`(+postgres+redis), `penpot-db` (STS), `penpot-cache`, `vaultwarden` (office); `tube-archivist`(+redis+elasticsearch), `jdownloader` (download); `openclaw` (ai) | Stateful — brief DB restart, data safe on PVC. Verify each dependent app reconnects. |
| **4 — shared/external LAST** | sun #4 | `cloudflared` (network) | Restarting the tunnel blips **every externally-exposed app**. Do it alone, deliberately, verify the tunnel is up + an external URL resolves. |

> The window agent may merge tiers if a window has capacity, but **never** run
> tier 4 (cloudflared) in the same window as anything else, and **never** exceed
> one tier's worth of verification bandwidth. `est_duration_min: 90` is per tier.

### Per-wrapper procedure (identical for all 59 — the shared transform)

For each wrapper in the batch:

**Step A — bump the chart version (git):**
```bash
# In each wrapper's helmrelease.yaml, under spec.chart.spec:
#     version: 3.7.3   →   version: 5.0.0
# (leave everything under `values:` unchanged EXCEPT the Step C automount audit)
```
Do a whole-batch sed only after eyeballing the diff (stage per-file hunks —
CLAUDE.md `feedback_stage_specific_hunks`):
```bash
# preview which files this batch touches
grep -rl "chart: app-template" kubernetes/apps/<batch paths> --include="*.yaml"
```

**Step B — commit + push the batch** (Flux reconciles; it will FAIL each HR on the
immutable selector — expected):
```bash
git add -p   # stage only this batch's helmrelease.yaml hunks
git commit -m "feat(app-template): migrate <tier N apps> chart 3.7.3 -> 5.0.0"
git push
```

**Step C — (tier 1 only, once) automount audit for `ai-sre` / `mcpo`:** if either
pod needs the SA token to reach the k8s API, add in the same commit:
```yaml
    serviceAccount:
      # ...existing...
    defaultPodOptions:
      automountServiceAccountToken: true   # 5.0.0 default is false — opt back in
```
Verify post-rollout the app can still reach the API (its own health/log).

**Step D — clear the immutable-selector failure (per workload):** once Flux reports
the HR `Released=false … field is immutable`, delete the workload so Helm recreates
it with the new `controller` selector, then force-reconcile:
```bash
# Deployments (stateless — brief downtime, pod returns immediately):
kubectl delete deployment -n <ns> <workload>
# The one in-scope StatefulSet (penpot-db has NO volumeClaimTemplates → PVCs are
# external and untouched; plain delete is safe):
kubectl delete statefulset -n office penpot-db
# then:
flux reconcile helmrelease -n <ns> <hr> --force
```
> Do NOT hand-delete pods mid-reconcile. Delete the **Deployment/StatefulSet**
> object; Helm recreates it. PVCs are never deleted by a workload delete.

**Step E — verify this wrapper (see §4) before moving to the next.**

---

## 4) Verification

Per wrapper, after Step D:
```bash
# HR reconciled to 5.0.0 and Ready
kubectl get hr -n <ns> <hr> -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'   # expect: True 5.0.0
# new selector carries app.kubernetes.io/controller (proves the rename applied)
kubectl get deploy,sts -n <ns> -l app.kubernetes.io/name=<app> -o jsonpath='{range .items[*]}{.metadata.name}{" sel="}{.spec.selector.matchLabels}{"\n"}{end}'
# pod rolled, Ready, 0 restarts after settle
kubectl get pods -n <ns> -l app.kubernetes.io/name=<app>
```

Per batch, before closing the window:
```bash
flux get helmreleases -A | awk 'NR==1 || $5 != "True"'          # every batch HR Ready=True
kubectl get pods -A | grep -vE 'Running|Completed' | grep -v NAMESPACE || echo "all healthy"
```

Targeted app checks (do these, they catch the naming-scheme regressions):
- **Ingressed apps** (echo-server, vaultwarden, traccar, node-red, omni-tools,
  arag-web, paperless-*, affine, …): the URL still resolves + Homepage tile is
  present (naming change re-derives Ingress/Service names — external-dns +
  Homepage must re-converge).
- **mosquitto:** its external ServiceMonitor selects `app.kubernetes.io/service:
  mosquitto-metrics` — confirm that service name did NOT change (metrics still
  scraped); confirm HA + zigbee2mqtt reconnected to the broker.
- **ai-sre / mcpo:** app can still reach the k8s API (Step C worked).
- **cloudflared (tier 4):** `kubectl logs` shows the tunnel registered; an
  external app URL loads from outside the LAN.
- **Metrics (soft):** for echo-server/cloudflared/zero-export/solarfocus, the
  `job` label flipped to the app name — spot-check the Grafana panel / any alert
  didn't go stale on the old `job=`.

---

## 5) Rollback

Per-batch, contained (each HR is independent — revert only the failing app or the
whole batch commit):

```bash
# A single wrapper regressed → revert its version in git, delete the workload so
# Helm recreates it back on 3.7.3's selector, reconcile:
git checkout <pre-batch-commit> -- kubernetes/apps/<ns>/<app>/app/helmrelease.yaml
git commit -m "revert(app-template): <app> back to 3.7.3" && git push
kubectl delete deployment -n <ns> <workload>       # selector reverts component→ again immutable
flux reconcile helmrelease -n <ns> <hr> --force

# The whole batch regressed → revert the batch commit:
git revert --no-edit <batch-commit-sha> && git push
# then delete each workload in the batch so Helm recreates on 3.7.3, reconcile each HR --force.
```

Confirm restored:
```bash
kubectl get hr -n <ns> <hr> -o jsonpath='{.status.history[0].chartVersion}{"\n"}'   # back to 3.7.3
kubectl get pods -n <ns> -l app.kubernetes.io/name=<app>                             # Ready
```

Notes:
- **Data is safe throughout** — no PVC is ever deleted; no wrapper uses
  `volumeClaimTemplates`; workload deletes leave PVCs intact.
- If a HR wedges `pending-upgrade`, clear it per SOP §7 (`helm rollback <app>
  <last-deployed-rev> -n <ns> --wait=false` → reconcile).
- After a rollback, restore `retries: 3` if you lowered it, drop silences, clear
  markers (`runbooks/update-marker.sh clear app-template`).

---

## 6) Interference notes

- **`conflicts_with` is strict.** This plan perturbs ~11 namespaces at once.
  - **`flux-stack-v0.57`** — that plan bumps `helm-controller`, i.e. the **Helm
    SDK that renders these very charts**. Rendering 59 wrappers on a new library
    chart while the renderer itself changes is two variables at once. **Never the
    same window.** (Ideally: land flux-stack first, its own window, verify, THEN
    start these tiers — but they stay in separate windows regardless.)
  - **`talos-v1.13.7`** (reboot / node drains), **`authentik-2026.5.6`** (SSO on
    the ingress path many of these apps use), **`reloader-v2`** (cluster-wide
    controller) — keep all high-risk plans serialized; no two share a window.
- **`shared: [ingress]`** — the naming-scheme change regenerates per-app Ingress
  objects across the batch's namespaces. The ingress-**controller** is untouched,
  but external-dns + Homepage re-evaluate; expect brief Homepage tile flux and
  verify URLs (§4). This is why an ingress-controller plan must not co-run.
- **`shared: [cloudflared]`** — the external tunnel is itself an app-template
  wrapper (tier 4). Its delete+recreate briefly drops **all external ingress**.
  Tier 4 runs **alone**, last, verified from outside the LAN. `echo-server`
  `dependsOn cloudflared`, so the canary also exercises this edge early.
- **Home-automation blast radius (tier 2):** do `mosquitto` first; HA/zigbee2mqtt
  reconnect to the broker after. CLAUDE.md: any HA error here is investigated for
  smart-home impact, never dismissed.
- **Per-app databases (tier 3):** the postgres/redis/elasticsearch *sidecars* are
  app-template wrappers too — migrating them restarts the DB pod (data safe on
  PVC) and briefly blips the owning app (affine, sure, penpot, teslamate, traccar,
  tube-archivist). Verify each owner reconnects.
- **Multi-window plan:** this is one plan file describing a **batched rollout over
  ~4–5 sun-windows**. The window agent should schedule tier 0/1 first, gate each
  subsequent tier on the prior tier being fully Ready=True, and treat any
  unresolved app as a blocker for its tier only — not for the whole migration.
- **Out of scope:** `home-automation/iobroker` (chart 2.4.0) — do not sweep it
  into a batch; it needs its own 2.x→5.x plan.
