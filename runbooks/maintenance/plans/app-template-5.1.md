---
plan_id: app-template-5.1
component: app-template
pr: null                            # no open Renovate PR — Renovate diffs against the FROZEN
                                    # oci://ghcr.io/bjw-s/helm repo and sees nothing; component is
                                    # also deny-listed (`*app-template*` in auto-update-policy.yaml).
                                    # Version bumps are hand-edited per wrapper.
kind: chart
current: "3.7.3"
target: "5.1.0"
update_type: major
risk: high
est_duration_min: 90                # PER TIER / per window. Full migration = 8 windows
                                    # (canary+T1 share one). See §3 tier table.
needs_reboot: false
touches:
  namespaces:
    - ai
    - backup
    - databases
    - default
    - download
    - flux-system                   # Step 0 repoints HelmRepository/bjw-s (chart source)
    - home-automation
    - media
    - my-software-development
    - my-software-production
    - my-software-showcase          # NEW since the 5.0 plan — 15 showcase-site wrappers
    - network
    - office
  resources:
    - helmrepository/bjw-s          # flux-system — repointed bjw-s → bjw-s-labs (Step 0)
    # 78 live HelmReleases at chart app-template 3.7.3 across 12 namespaces
    # (+2 repo-only files: home-automation/otbr [ks disabled, RMA] and the
    # my-software-development/_template scaffold — file-bump only, no cluster work).
    - helmrelease/*                 # all 78 wrappers — full per-instance table in §1
    - deployment/*                  # every wrapped Deployment: immutable-selector change
                                    # (component→controller) forces delete+recreate
    - statefulset/penpot-db         # office — no volumeClaimTemplates, PVC external
    - statefulset/iobroker          # home-automation — no volumeClaimTemplates; NOTE: was
                                    # "2.4.0 / out of scope" in the old plan; live+repo are
                                    # 3.7.3 today → IN SCOPE now (tier 5)
    - cronjob/pallet-price-monitor  # cronjob-type controller — NO immutable selector, plain bump
    - service/*                     # regenerated — render-diff PROVED names, LB types and
                                    # lbipam.cilium.io/ips annotations are all UNCHANGED
    - serviceaccount/*              # 5.x now creates one default SA per release (benign; no
                                    # name collisions — verified against live SA list)
    - ingress/*                     # regenerated across 12 namespaces (names stable per render)
    - servicemonitor/*              # echo-server, cloudflared, zero-export-controller,
                                    # solarfocus-scraper — jobLabel default flips (metrics only)
    - imageupdateautomation/absenty-image-updates   # ×2 ns — suspended for tier 2, restored same window
  shared:
    - ingress                       # per-app Ingress objects churn across 12 namespaces;
                                    # ingress-controller itself NOT touched
    - cloudflared                   # the tunnel is ITSELF a wrapper — its delete+recreate blips
                                    # ALL externally-exposed apps; own tier, LAST
    # NOT touched: cert-manager, cilium/cni, coredns, longhorn (no PVC deletes anywhere;
    # neither StatefulSet has volumeClaimTemplates)
depends_on: []
conflicts_with:                     # never share a window with:
  - envoy-gateway-phase1            # shares network + default (+ its own ingress churn)
  - envoy-gateway-phase2            # attended project, touches all-internal namespaces
  - bitnamilegacy-exit-nextcloud-db     # office
  - bitnamilegacy-exit-nextcloud-redis  # office
  - bitnamilegacy-exit-paperless-db     # office
  - bitnamilegacy-exit-paperless-redis  # office
  - paperless-ngx-3.0.5             # office (paperless-ai/-gpt live in the office tier)
  - affine-redis-8.10.0             # image bump on a wrapper this plan migrates — sequence,
                                    # don't co-run; whichever lands second is a trivial rebase
  - redisinsight-3.8.0              # databases
  - longhorn-1.12.1-engine          # mass workload churn on top of an engine upgrade is the
                                    # 2026-08-16 34-volume pile-up shape — never together
  # + the standing rule the retired talos guard encoded: do NOT co-schedule any tier with a
  # Talos node-reboot roll (drain + ~50 Longhorn replica rebuilds per node). Re-point at the
  # next talos-* plan_id when one exists.
security_ref: null
status: vetted                      # EXECUTION IN PROGRESS (ad-hoc:2026-08-18, operator-approved
                                    # standing GO). Progress: Step 0 DONE (cb242c1a); tier 0
                                    # canary DONE (f01aadeb, echo-server 5.1.0 verified); tier 1
                                    # IN PROGRESS (c5365e63 + PVC-naming defect fix — see §1a).
                                    # Supersedes app-template-5.0.md (deleted in same commit).
window: "ad-hoc:2026-08-18"         # started ad-hoc under operator standing GO; remaining tiers
                                    # continue same run or fall back to the 8-window schedule:
                                    # (tiers 0+1, 3, 4, 6) + 3× weekday 60m (tiers 2, 5, 7).
                                    # Step 0 (repo repoint) can ride ANY earlier window — it is
                                    # provably inert (3.7.3 exists in the new registry too).
auto_execute: false                 # never unattended — risk:high, operator-present only
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/maintenance-windows.md
  - docs/sops/longhorn-rwo-multi-attach.md
generated: "2026-08-18"
---

# app-template 3.7.3 → 5.1.0 (bjw-s common library) — cluster-wide chart migration

## 1) Summary & why held

`app-template` (bjw-s `common` wrapper chart) backs **78 live HelmReleases in 12
namespaces** — everything from `echo-server` to `home-assistant`, the external
`cloudflared` tunnel, both StatefulSets (`penpot-db`, `iobroker`), the immich
group, and 15 showcase sites in `my-software-showcase` that did not exist when
the 5.0 plan was written. The jump is **two majors (3.7.3 → 4.x → 5.x)** and is
deny-listed in `runbooks/auto-update-policy.yaml` because one version field
touches ~all of user-space. This is a coordinated migration, not a bump.

This plan **supersedes and replaces `app-template-5.0.md`** (authored 2026-08-02
against 59 wrappers, target 5.0.0; flagged DO-NOT-EXECUTE at the 2026-08-15
vetting). Everything below was regenerated from repo + live cluster truth on
**2026-08-18** and empirically validated by rendering **every wrapper** against
the pulled 5.1.0 chart.

### Inventory reconciliation (2026-08-18)

- **Repo:** 80 files match `chart: app-template`, all at `version: 3.7.3`.
- **Live:** 78 HelmReleases at app-template 3.7.3 (`kubectl get hr -A`).
- **Delta (2):** `home-automation/otbr` — ks.yaml disabled 2026-05-29 pending
  SMLIGHT RMA, not deployed → **file-bump only** (so a future re-enable lands
  straight on 5.1.0 with a fresh selector, no migration debt);
  `my-software-development/_template/opencode-PROJECT_NAME` — undeployed
  scaffold → file-bump only.
- **Fixed vs old plan:** `scrypted` (was misnamed `scrypted-nvr`),
  `icloud-docker-andrea` (was missing), immich ×4 (new), showcase ×15 (new),
  `nextcloud-mcp` (new), langfuse (removed from cluster, gone from table).
- **⚠️ `home-automation/iobroker` is IN scope now.** The old plan (and the
  rewrite brief) said "2.4.0, out of scope". Repo
  (`iobroker/app/helm-release.yaml` — note the hyphenated filename) and live
  cluster both show **3.7.3** today — it was bumped since. It is a
  statefulset-type controller (no volumeClaimTemplates, external PVC) and is
  slotted in tier 5. **Vetter: confirm the operator wants it included.**

### The breaking changes

**4.0.0 (the blocker, unchanged from the old plan, re-verified):**
1. **Immutable-selector rename.** The hardcoded `app.kubernetes.io/component`
   selector label became `app.kubernetes.io/controller`. Render-diff against
   3.7.3 confirms it on every workload (e.g. mosquitto Deployment selector
   `component: mosquitto` → `controller: mosquitto`; same flip on both
   StatefulSets). `.spec.selector` is immutable → `helm upgrade` fails
   `field is immutable` on **all 76 Deployments/StatefulSets** — each must be
   **deleted so Helm recreates it** (SOP `application-update.md` §7). The one
   cronjob-type controller (`pallet-price-monitor`) is exempt (Jobs are created
   fresh).
2. Resource naming standardized — ⚠️ **NOT a non-event: see §1a (found live,
   tier 1, 2026-08-18).** The audit's render-diff checked Services/workloads
   but missed chart-GENERATED PVCs: 5.x appends the `-<identifier>` suffix to
   a generated resource name only when the release has **more than one** item
   of that kind (`itemCount > 1` in `_determineResourceNameFromValues.tpl`),
   so single-PVC releases get their PVC RENAMED `{app}-{key}` → `{app}`.
   For Services the old plan text stands — rendered
   3.7.3-vs-5.1.0 diffs for mosquitto (3 services incl. `mosquitto-metrics`),
   echo-server, traccar (`traccar-main`/`traccar-osmand`), home-assistant,
   scrypted, music-assistant-server, iobroker, penpot-db show **identical
   resource names**, identical Service types, identical `lbipam.cilium.io/ips`
   annotations (LB IPs keep), and the `app.kubernetes.io/service` label
   mosquitto's external ServiceMonitor selects on is preserved.
3. Min Kubernetes ≥1.28 — cluster is v1.36, satisfied.

**5.0.0:**
1. **`rawResources` restructured** — no wrapper uses it (re-grepped 2026-08-18,
   showcase apps included) → non-issue.
2. **`automountServiceAccountToken` defaults to `false`.** Fleet audit: only
   **`ai/ai-sre`** and **`ai/mcpo`** have RBAC-bound ServiceAccounts and need
   the token (both have ClusterRoleBindings in their `rbac.yaml`). No other
   wrapper's pod can use the API today (zero RoleBindings against any `default`
   SA — verified), so the silent flip is harmless fleet-wide. openclaw,
   hermes-agent, paperclip re-checked: no SA declared, no RBAC → no in-cluster
   API use to lose.
3. **A default ServiceAccount is now created per release**
   (`global.createDefaultServiceAccount`, verified in renders: every release
   gains an SA named after itself, pods are repointed to it). Collision audit
   against the live SA list: the only matches are `ai/ai-sre` (already
   chart-owned — fine) and **`ai/mcpo` (kustomize-owned in `rbac.yaml` —
   Helm would fight over it; fixed by the mcpo values migration below)**.
   `paperclip-backup-cleanup` and `media-dashboard` don't collide.
4. **ServiceMonitor/PodMonitor `jobLabel` defaults to `app.kubernetes.io/name`**
   — Prometheus `job` value may change for the 4 wrappers with a
   `serviceMonitor` in values: `echo-server`, `cloudflared`,
   `zero-export-controller`, `solarfocus-scraper` (re-grepped — still exactly
   these 4). Metrics-only; spot-check panels/alerts keyed on `job=`.
5. Min Kubernetes ≥1.31, Helm ≥3.18 — cluster v1.36.0, helm-controller
   **v1.6.3** (Helm SDK ≥3.18) — satisfied.

**5.1.0 (deltas beyond the old plan's 5.0.0 analysis — from `common-5.0.1` +
`common-5.1.0` release notes):**
1. **Values are now hard-validated by a shipped `values.schema.json`**
   ("moved controller strategy validation to values schema"). A wrapper with
   stale value shapes **fails at render time** instead of deploying something
   subtly wrong. This is what breaks ai-sre/mcpo (below) — and it is also our
   safety net: an unfixed wrapper fails loudly in `flux-local`/CI, not on the
   cluster.
2. **`serviceAccount` values were restructured into a map of named objects**
   (`{create: bool, name: str}` is rejected by the schema). This is the actual
   migration the old plan missed — it only planned an "automount audit".
3. 5.0.1/5.1.0 additions (SA name resolution fix, DaemonSet updateStrategy,
   automount on generated SAs, ReferenceGrant generation) — no in-scope impact.
4. Registry verified 2026-08-18: `oci://ghcr.io/bjw-s-labs/helm/app-template`
   serves `3.7.3, 4.0.0 … 5.0.1, 5.1.0` (cosign-signed). **3.7.3 exists in the
   new repo too → the Step 0 repoint is inert on its own** and independently
   safe. The old `oci://ghcr.io/bjw-s/helm` tops out at 3.7.3 (frozen).

### Per-instance special-config audit (all 80 wrappers, 2026-08-18)

Method: parsed every wrapper's values; rendered **all 80** against the pulled
5.1.0 chart (`helm template`, per feedback memory — kubeconform skips HR CRDs).
**Result: 77/80 render clean; 2 real failures (ai-sre, mcpo — schema, fixed
below, migrated values re-rendered OK); 1 false failure (`opencode-PROJECT_NAME`
scaffold — placeholder uppercase release name only; its twin
`opencode-andreamosteller` with identical shape renders clean).**

Impact legend — **MIGRATE**: values must change in the same commit as the bump;
**CARE**: mechanical bump but ordered/verified specially; **ok**: mechanical
bump + standard Step D delete.

| Wrapper (ns) | Special config | 5.x impact |
|---|---|---|
| ai-sre (ai) | `serviceAccount {create,name}` + ClusterRoleBinding; caps drop ALL; 6 PVCs | **MIGRATE** — new SA map syntax + automount opt-in (§3 Step C1) |
| mcpo (ai) | `serviceAccount {create:false,name:mcpo}` (SA is kustomize-owned); initContainer | **MIGRATE** — disable default SA (name collision!) + bind by name + automount (§3 Step C2) |
| openclaw (ai) | initContainer, 6 PVCs, caps drop | ok — no SA/RBAC (verified); verify persona PVCs mount |
| hermes-agent (ai) | multi-container (gateway+dashboard), initContainer, 2 ingresses | ok — no SA/RBAC |
| paperclip (ai) | 2 initContainers, multi-container; separate kustomize SA `paperclip-backup-cleanup`; **generated PVC `paperclip-data` (dynamic, reclaim=Delete)** | **MIGRATE** — `persistence.data.suffix: data` same commit (§1a); no SA collision |
| next-ai-draw-io (ai) | plain | ok |
| icloud-docker-mu / -andrea (backup) | Recreate; CIFS persistence | ok — no PVC touched; storage-safety N/A (no deletes) |
| memgraph (databases) | **multi-controller** (memgraph+lab), 2 services, initContainers, Recreate | CARE — two Deployments to delete in Step D |
| redis (databases) | Recreate, PVC | ok (stateful tier) |
| nocodb, phpmyadmin (databases) | plain / ingress | ok |
| echo-server (default) | **serviceMonitor** (jobLabel flip); `dependsOn: cloudflared` | CARE — canary; check `job=` after |
| jdownloader (download) | Recreate, dependsOn cloudflared | ok (stateful tier) |
| tube-archivist(+redis,+es) (download) | Recreate; ES has IPC_LOCK cap, initContainer; HR dependsOn chain | CARE — order: redis+es → tube-archivist |
| esphome (home-automation) | **hostNetwork** | ok — delete-then-recreate avoids host-port clash |
| home-assistant (h-a) | **hostNetwork**, **LoadBalancer+lbipam IP**, initContainer certifi-patch | CARE — LB name/annotation render-verified stable; verify LB IP + integrations after |
| iobroker (h-a) | **statefulset**, RollingUpdate, LB+lbipam, replicated PVC | CARE — STS delete+recreate; no VCTs (verified); **newly in scope** |
| matter-server (h-a) | hostNetwork | ok |
| mosquitto (h-a) | 3 services (`-main` LB+lbipam / `-internal` / `-metrics`), exporter sidecar, initContainer | CARE — FIRST in its tier; render-verified all 3 svc names + `app.kubernetes.io/service` label stable → external ServiceMonitor keeps scraping |
| music-assistant-server (h-a) | multi-container (app+alexa-skill), hostNetwork, LB+lbipam | CARE — verify Alexa stream URL after (AR-049 context) |
| node-red, zigbee2mqtt, mqttx-web (h-a) | ingress/PVC only | ok — z2m after mosquitto |
| trmnl-ha (h-a) | **generated PVC `trmnl-ha-data` (dynamic, reclaim=Delete)** | **MIGRATE** — `persistence.data.suffix: data` same commit (§1a) |
| ha-ai-harness (h-a) | **multi-controller** (server+frontend), 2 services | CARE — two Deployments in Step D |
| pallet-price-monitor (h-a) | **cronjob-type controller** | ok — **no selector issue, no Step D**; plain bump |
| scrypted (h-a) | **privileged** + SYS_ADMIN, LB+lbipam | ok — PSA override already namespace-level |
| solarfocus-scraper (h-a) | **serviceMonitor**, Recreate | CARE — `job=` flip |
| zero-export-controller (h-a) | **serviceMonitor**, Recreate | CARE — `job=` flip |
| teslamate / traccar (+`-postgres` each) (h-a) | HR dependsOn; traccar 2 svcs (osmand LB+lbipam) | CARE — postgres first, then app |
| immich-server (media) | initContainers wait-for-pg/redis, dependsOn ×2 | CARE — order: pg+redis → ML → server |
| immich-postgres (media) | Recreate, PVC (Deployment, NOT app-template-STS) | ok (stateful tier) |
| immich-redis, immich-machine-learning (media) | ML: **privileged** + SYS_ADMIN (iGPU) | ok |
| makemkv (media) | **privileged** + SYS_ADMIN | ok |
| absenty (msd + msp) | Recreate; **live ImageUpdateAutomation writes its helmrelease.yaml every ~20-30 min**; multi generated PVCs | CARE — suspend both automations for tier 2, restore same window (§3 Step B'); add explicit `suffix` per PVC (§1a) |
| andreamosteller (msd+msp), opencode-andreamosteller (msd) | multi-container/multi-svc (opencode) | ok |
| gas-price-monitor, rainbow-rescue (msp) | caps add (NET_BIND_SERVICE etc.) | ok |
| showcase ×15 (my-software-showcase) | uniform: Recreate + ingress(homepage); 10 wrappers carry chart-generated longhorn-static PVCs; uzeit-de/globalmobility are TYPO3+external MariaDB | **hit §1a live** — `suffix` fix landed with tier 1; uzeit-de has 15m HR timeout (152cb651) |
| cloudflared (network) | **serviceMonitor**; RollingUpdate; the external tunnel itself | CARE — LAST, alone (tier 7); `job=` flip |
| affine(+pg,+redis) (office) | initContainers, dependsOn ×2, Recreate | CARE — pg+redis → affine |
| sure-pg, sure-redis (office) | Recreate (the `sure` app itself is NOT app-template) | ok — verify Sure reconnects |
| penpot-db (office) | **statefulset**, no VCTs; **generated PVC `penpot-db-data` (dynamic, reclaim=Delete — NOT external as previously stated)** | **MIGRATE** — `persistence.data.suffix: data` same commit (§1a); STS delete safe |
| penpot-cache (office) | completely plain | ok |
| actual-budget, arag-web, omni-tools, paperless-ai, paperless-gpt, vaultwarden, nextcloud-mcp (office) | ingress/PVC/caps only | ok |
| otbr (h-a, **repo-only**) | privileged, hostNetwork; ks.yaml disabled (RMA) | file-bump only, no cluster step |
| opencode-PROJECT_NAME (msd `_template`, **repo-only**) | scaffold | file-bump only |

Fleet-wide re-greps (2026-08-18): `rawResources`, `networkpolicies`,
`podMonitor`, `autoscaling`, `route`, `staticToken` — **zero hits** → none of
the other 4.x/5.x surface applies. All single-replica-RWO wrappers already run
`strategy: Recreate` (longhorn-rwo-multi-attach rule holds through the
migration; the chart bump does not touch `strategy` values).

### §1a — PVC-rename defect (found live in tier 1, 2026-08-18) + adopted fix

**Defect:** 5.x renames chart-generated PVCs on single-PVC releases
(`{app}-{key}` → `{app}`, itemCount naming rule — see breaking-changes 4.0.0
#2). On upgrade Helm prunes the old-named PVC; the new-named PVC can't bind
the old PV (stale `claimRef` uid). In tier 1 this broke haarfabrik, ibgastro,
max-jung, stepbystepguide (all `Retain` → data safe, pods Pending ~outage
until fixed). **On dynamic `longhorn` PVCs with `reclaim: Delete` the same
prune DESTROYS the volume** — this would have hit paperclip (tier 3),
trmnl-ha (tier 4), penpot-db (tier 6).

**Adopted mechanism (Option A, render-verified):** every chart-generated PVC
gets an explicit `suffix: <identifier>` in its persistence values, **in the
same commit as that wrapper's version bump** (5.x-only key — do NOT add it
while a wrapper is still on 3.7.3). The suffix has a `hasSuffix` guard, so
it is idempotent for multi-PVC releases (names already carry the identifier)
and pins `{app}-{key}` permanently regardless of future itemCount changes.

**Fleet checklist (chart-generated PVCs only; `existingClaim` wrappers are
immune):**
- tier 1 showcase ×10 files (12 PVCs): landed with the tier-1 fix commit.
- tier 2: `absenty` msd (data/storage/bundle) + msp (data/storage) — names
  currently safe via itemCount>1, add explicit suffix anyway.
- tier 3: `paperclip` (data — **reclaim=Delete, mandatory**).
- tier 4: `trmnl-ha` (data — **reclaim=Delete, mandatory**).
- tier 6: `penpot-db` (data — **reclaim=Delete, mandatory**; plan previously
  said "PVC external" — wrong, it is chart-generated dynamic longhorn).
- file-bumps: `otbr` (data), `_template` (home) — add suffix in the bump.

**RACE lesson (tier 1, 2026-08-18):** a values-fix push does NOT immediately
change the in-cluster HR spec — an HR mid-retry-loop can still render the
PRE-fix spec and SSA-swap PVC names back and forth (ordiga/u-zeit/
zuhause-betreut had PVCs deleted+recreated by exactly this; Retain PVs
caught them, rebound verified, no data loss). **Rule for every later tier:
before ANY 5.1.0 retry/force-reconcile of a wrapper with generated PVCs,
confirm the in-cluster HelmRelease spec already carries the suffix values**
(`kubectl get hr -n <ns> <hr> -o jsonpath='{.spec.values.persistence}'`
shows the suffix keys, or compare `flux get ks` revision to the fix commit).
If a retry loop is live during the push, `flux suspend hr <hr>` across the
push and resume after the Kustomization is on the fix revision. This is
doubly mandatory for the reclaim=Delete wrappers (paperclip, trmnl-ha,
penpot-db) — there a race prune has no Retain net.

**Recovery for an already-orphaned Retain PV** (old PVC pruned, PV
Released): re-point/clear the stale claimRef —
`kubectl patch pv <pv> --type json -p '[{"op":"remove","path":"/spec/claimRef/uid"},{"op":"remove","path":"/spec/claimRef/resourceVersion"}]'`
— the old-named PVC (recreated by remediation or by the fixed render) then
binds. **Never delete a PV or PVC** (storage-safety SOP).

## 2) Pre-checks

Run at the start of **every** tier window (cluster state moves between windows).

```bash
# 0. Operator present; confirm no conflicting plan shares this window
.venv/bin/python3 runbooks/maintenance-plan.py --json | python3 -c "import sys,json;d=json.load(sys.stdin);print('this window queue:',[p for w in d['scheduled'].values() for p in w])"

# 1. Green cluster gate — never migrate onto a red cluster
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
kubectl get pods -A | grep -vE 'Running|Completed' | grep -v NAMESPACE || echo "all pods healthy"

# 2. Floors (once, first window): k8s >=1.31, helm-controller SDK >=3.18
kubectl version -o json | python3 -c "import sys,json;print(json.load(sys.stdin)['serverVersion']['gitVersion'])"   # v1.36.x
kubectl get deploy -n flux-system helm-controller -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'    # v1.6.3+

# 3. Longhorn backups fresh for THIS tier's stateful wrappers (tiers 5/6 esp.)
kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt --no-headers | grep -Ei '<apps-in-this-tier>'

# 4. RENDER GATE — re-render THIS tier's wrappers against 5.1.0 before touching git
#    (the full-fleet render already passed 2026-08-18; re-run per tier for drift):
task template:configure -- --strict
#    plus per-wrapper: helm template <name> oci://ghcr.io/bjw-s-labs/helm/app-template \
#      --version 5.1.0 -n <ns> -f <extracted values>   # must exit 0

# 5. Tier 2 only: absenty automations currently UNSUSPENDED (they write every ~20-30min)
kubectl get imageupdateautomation -A -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,SUSPEND:.spec.suspend
```

**Silence + marker (attended-update SOP):** silence
`Kube(Pod|Deployment|StatefulSet).*` for this tier's namespaces for the window
TTL, and `runbooks/update-marker.sh add app-template <ns> 3 "app-template
3.7.3->5.1.0 tier N"` per namespace in the tier.

## 3) Steps

**GitOps only** (edit files, push, Flux reconciles) **+ one manual
`kubectl delete` per Deployment/StatefulSet** (unavoidable — immutable
selector; SOP §7 pattern). No other direct cluster mutation.

### Step 0 — repoint the chart source (FIRST, its own commit, any window)

The project moved registries; the old repo is frozen at 3.7.3, so without this
there is no source for 5.x. Verified: the new repo also serves **3.7.3**, so
this commit changes nothing on the cluster by itself.

```bash
# kubernetes/flux/meta/repositories/oci/bjw-s.yaml
#   url: oci://ghcr.io/bjw-s/helm   →   url: oci://ghcr.io/bjw-s-labs/helm
git add kubernetes/flux/meta/repositories/oci/bjw-s.yaml
git commit -m "feat(flux): repoint bjw-s HelmRepository to bjw-s-labs (old registry frozen at app-template 3.7.3)"
git push
# verify: flux get sources helm-oci -A | grep bjw-s   → Ready, new URL revision;
# all 78 HRs stay Ready on 3.7.3 (tag exists in the new repo — pre-verified).
```

### Tier plan (78 live wrappers; one tier per window)

| Tier | Slot | Wrappers | Notes |
|---|---|---|---|
| **0 canary** | weekend 90m #1 (start) | `echo-server` (default) | Proves bump→delete→reconcile→verify + ingress/tunnel edge (`dependsOn cloudflared`) + the jobLabel flip. |
| **1 showcase** | same window (rest) | all 15 `my-software-showcase` | Uniform Recreate+ingress pattern; batch-friendly. `uzeit-de` reconciles slow (15m HR timeout) — start it early in the loop. |
| **2 dev/prod + leaves** | weekday 60m | `absenty`×2 (**suspend automations first, Step B′**), `andreamosteller`×2, `opencode-andreamosteller`, `gas-price-monitor`, `rainbow-rescue`, `icloud-docker-mu`, `icloud-docker-andrea`, `nocodb`, `phpmyadmin`, `makemkv` | 12 stateless-ish leaves. Also file-bump `_template/opencode-PROJECT_NAME` here. |
| **3 ai + office stateless** | weekend 90m | `ai-sre`†, `mcpo`† (†values migrations, Steps C1/C2), `hermes-agent`, `next-ai-draw-io`, `paperclip`, `openclaw`, `omni-tools`, `nextcloud-mcp`, `paperless-ai`, `paperless-gpt`, `actual-budget`, `arag-web`, `vaultwarden` | The two MIGRATE wrappers get individual attention; rest mechanical. |
| **4 home-automation core** | weekend 90m | `mosquitto` **FIRST**, then `zigbee2mqtt`, `home-assistant`, `esphome`, `matter-server`, `music-assistant-server`, `node-red`, `scrypted`, `trmnl-ha`, `mqttx-web`, `ha-ai-harness` | Broker first; verify HA + z2m reconnect before proceeding (HA errors are never background noise). |
| **5 home-automation rest** | weekday 60m | `iobroker` (STS), `teslamate-postgres`→`teslamate`, `traccar-postgres`→`traccar`, `solarfocus-scraper`, `zero-export-controller`, `pallet-price-monitor` (no delete needed) | Also file-bump `otbr` here (not live). |
| **6 stateful data** | weekend 90m | `redis`, `memgraph` (databases); `immich-postgres`+`immich-redis`→`immich-machine-learning`→`immich-server` (media); `affine-pg`+`affine-redis`→`affine`, `sure-pg`, `sure-redis`, `penpot-db` (STS), `penpot-cache` (office); `tube-archivist-redis`+`tube-archivist-elasticsearch`→`tube-archivist`, `jdownloader` (download) | 17 wrappers, dependency-ordered (DB/sidecar before owner). If the window runs long, split at the office/download boundary into 6a/6b — every HR is independent. |
| **7 cloudflared** | weekday 60m, ALONE | `cloudflared` (network) | Tunnel delete+recreate blips all external ingress. Nothing else in the window; verify from outside the LAN. |

Window count: **8** (tier 0 shares tier 1's window; +1 if tier 6 splits) —
roughly 2 weekends + 3 weekdays ≈ **2.5–3 weeks** at the daily cadence.
Each tier gates on the previous tier fully `Ready=True`; a failed wrapper
blocks its own tier only (independent HRs), never the whole migration.

### Per-wrapper procedure (Steps A–E)

**Step A — bump (git):** in the wrapper's `helmrelease.yaml`
(`helm-release.yaml` for iobroker), `spec.chart.spec.version: 3.7.3` →
`5.1.0`. Leave `values:` untouched **except** ai-sre/mcpo (C1/C2). Preview the
tier's file list: `grep -rl "chart: app-template" kubernetes/apps/<tier paths>`.

**Step B — commit + push the tier** (stage per-file hunks, `git add -p` — the
worktree is shared):

```bash
git commit -m "feat(app-template): migrate <tier N> chart 3.7.3 -> 5.1.0"
git push
# Flux reconciles; each Deployment/STS HR now FAILS `spec.selector: field is
# immutable` — EXPECTED, cleared in Step D. pallet-price-monitor (cronjob)
# and any freshly-created workloads reconcile clean with no Step D.
```

**Step B′ — tier 2 only, BEFORE Step A:** suspend both absenty automations so
they stop committing into the same files mid-tier; restore in the same window:

```bash
flux suspend image update absenty-image-updates -n my-software-development
flux suspend image update absenty-image-updates -n my-software-production
# ... run tier 2 ...
flux resume image update absenty-image-updates -n my-software-development
flux resume image update absenty-image-updates -n my-software-production
# then confirm both resume writing (or no new tag pending): flux get image update -A
```

**Step C1 — ai-sre values migration (same commit as its Step A).** 5.x schema
rejects `{create, name}`; migrated form (render-validated 2026-08-18 — produces
SA `ai-sre`, pod binds it, token mounted):

```yaml
# REPLACE the old block:
#   serviceAccount:
#     create: true
#     name: ai-sre
# WITH:
serviceAccount:
  ai-sre: {}                      # single entry → SA named exactly "ai-sre" (CRB subject unchanged)
defaultPodOptions:                # merge into existing defaultPodOptions if present
  automountServiceAccountToken: true   # 5.x default false; ai-sre needs the API token
```

**Step C2 — mcpo values migration (same commit as its Step A).** The SA `mcpo`
is kustomize-owned (`rbac.yaml`) — the 5.x auto-created default SA would
collide with it. Migrated form (render-validated: chart creates NO SA, pod
binds existing `mcpo`, token mounted):

```yaml
global:
  createDefaultServiceAccount: false   # SA `mcpo` stays kustomize-owned — avoid ownership fight
controllers:
  mcpo:
    serviceAccount:
      name: mcpo                       # bind the existing SA by name
    # ...existing controller config...
defaultPodOptions:
  automountServiceAccountToken: true
# DELETE the old top-level `serviceAccount: {create: false, name: mcpo}` block.
```

**Step D — clear the immutable-selector failure (per workload):** once the HR
reports `Released=false … field is immutable`:

```bash
kubectl delete deployment -n <ns> <workload>        # or, for the two STSs:
kubectl delete statefulset -n office penpot-db      # no volumeClaimTemplates —
kubectl delete statefulset -n home-automation iobroker   # PVCs external, untouched
flux reconcile helmrelease -n <ns> <hr> --force
```

Multi-controller wrappers need every Deployment deleted: `memgraph` +
`memgraph-lab` (databases/memgraph), `ha-ai-harness-server` +
`ha-ai-harness-frontend` — check actual names via
`kubectl get deploy -n <ns> -l app.kubernetes.io/instance=<hr>`.
Never hand-delete pods; PVCs are never deleted by a workload delete.

**Step E — verify this wrapper (§4) before the next one.** Dependency order
within a tier: mosquitto → its clients; `*-postgres`/`*-redis`/`*-elasticsearch`
→ their owner app.

## 4) Verification

Per wrapper after Step D:

```bash
kubectl get hr -n <ns> <hr> -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'   # True 5.1.0
kubectl get deploy,sts -n <ns> -l app.kubernetes.io/instance=<hr> -o jsonpath='{range .items[*]}{.metadata.name}{" sel="}{.spec.selector.matchLabels}{"\n"}{end}'   # has app.kubernetes.io/controller
kubectl get pods -n <ns> -l app.kubernetes.io/instance=<hr>        # Ready, restarts settle at 0
```

Per tier before closing the window: `flux get hr -A | awk 'NR==1||$5!="True"'`
and the all-pods-healthy one-liner; every ingressed app's URL + Homepage tile.

Targeted (the ones the audit says can regress):
- **mosquitto:** all 3 services exist with old names; external ServiceMonitor
  still scraping (`mosquitto-metrics` label intact); HA + zigbee2mqtt
  reconnected; LB IP unchanged.
- **LoadBalancer apps** (home-assistant, iobroker, mosquitto,
  music-assistant-server, scrypted, traccar-osmand): `kubectl get svc -n
  home-automation -o wide | grep LoadBalancer` — same external IPs as pre-tier.
- **ai-sre / mcpo:** pod can reach the API post-migration
  (`kubectl logs` clean; e.g. `kubectl exec` a `kubectl auth can-i list pods
  --as=system:serviceaccount:ai:<sa>` style check from outside).
- **music-assistant-server:** Alexa skill stream still plays (AR-049 path).
- **jobLabel flip** (echo-server, cloudflared, zero-export-controller,
  solarfocus-scraper): Grafana panels / alerts keyed on `job=` still populate.
- **immich/affine/sure/tube-archivist/teslamate/traccar/penpot:** owner app
  reconnects to its migrated DB sidecar; no crash-loop.
- **cloudflared (tier 7):** tunnel registered in logs; an external URL loads
  from outside the LAN; echo-server (dependsOn) still Ready.

## 5) Rollback

Contained per wrapper / per tier (HRs are independent):

```bash
# single wrapper: revert its file, then repeat the delete dance backwards
git checkout <pre-tier-commit> -- kubernetes/apps/<ns>/<app>/app/helmrelease.yaml
git commit -m "revert(app-template): <app> back to 3.7.3" && git push
kubectl delete deployment -n <ns> <workload>   # selector flips back — immutable again
flux reconcile helmrelease -n <ns> <hr> --force

# whole tier: git revert --no-edit <tier-commit-sha> && git push, then Step-D-delete
# each workload in the tier so Helm recreates on 3.7.3.
```

Confirm restored: HR `history[0].chartVersion` back to 3.7.3, pods Ready.
Notes:
- **3.7.3 remains pullable from the NEW repo** (verified) → Step 0 is never
  rolled back as part of an app rollback. Only revert Step 0 itself if the new
  registry is unreachable (then old repo still serves 3.7.3).
- ai-sre/mcpo rollback = revert the whole file (version + values together —
  the old values shape is invalid on 5.x and vice versa; never mix).
- Wedged `pending-upgrade`: `helm rollback <app> <last-deployed-rev> -n <ns>
  --wait=false` then reconcile (SOP §7).
- Tier 2 abort: `flux resume image update ...` both absenty automations before
  closing the window, whatever else happened.
- Data is safe throughout: no PVC deletes anywhere; neither STS has
  volumeClaimTemplates; CIFS wrappers (icloud-docker ×2, makemkv, jdownloader,
  tube-archivist) have workload-only churn — storage-safety pre-flight not
  triggered (no PVC operations).
- After rollback: drop silences, `runbooks/update-marker.sh clear app-template`.

## 6) Interference notes

- **12 namespaces churn — `conflicts_with` is long and deliberate.** Never
  share a window with: the envoy-gateway phases (shared `network`/`default`,
  plus their own ingress churn — EG phases also run attended OUTSIDE the
  window system, so coordinate calendar-wise, not just slot-wise), any
  `bitnamilegacy-exit-*` / `paperless-ngx-3.0.5` / `affine-redis-8.10.0`
  (office), `redisinsight-3.8.0` (databases), `longhorn-1.12.1-engine`
  (engine upgrade + mass replica churn = the 2026-08-16 pile-up shape).
- **No Talos co-scheduling.** No talos-* plan is open today (v1.13.8
  shipped); when the next one is written, re-add its plan_id here. A node
  drain rebuilds ~50 Longhorn replicas — never stack tier churn on that.
- **Current schedule context (2026-08-18):** kube-prometheus-stack-88 executed
  today (monitoring — no overlap); grafana-chart-11 slotted fri-early
  2026-08-21 (monitoring — no overlap); redisinsight-3.8.0 wed-early
  2026-08-19 (databases — tiers 2/6 must not land that day);
  longhorn-1.12.1-engine sat-early 2026-08-22 — **tier windows must schedule
  around it**, don't take that Saturday; paperless-ngx-3.0.5 sun-window
  2026-08-23 — don't put tier 3 (office) there.
- **`shared: [ingress]`** — per-app Ingress objects are regenerated
  (render-diff says same names, so this is churn, not rename); external-dns +
  Homepage re-converge; brief tile flux expected. The ingress controller
  itself is untouched — but an ingress-controller/EG plan must still never
  co-run.
- **`shared: [cloudflared]`** — tier 7 briefly drops ALL external ingress;
  alone, last, verified from outside.
- **absenty ImageUpdateAutomation ×2** — live writers into tier-2 files;
  suspend/resume inside the tier-2 window (Step B′). Re-check
  `kubectl get imageupdateautomation -A` at every tier start for NEW
  automations (none besides absenty as of 2026-08-18).
- **Multi-window plan:** tiers gate on the previous tier fully Ready; a failed
  wrapper blocks its tier only. The window agent may merge small tiers if
  capacity allows, but never tier 7 with anything, and never two MIGRATE
  wrappers unverified in parallel.
- **Out of scope:** nothing — the old iobroker exclusion is obsolete (it is on
  3.7.3 now, tier 5). Repo-only files (`otbr`, `_template`) get file bumps
  with zero cluster work.
