---
plan_id: homepage-2.0.0
component: homepage
pr: null                              # no open Renovate PR at plan time — this bump was never
                                      # surfaced (see §1, "why this was invisible"). If Renovate
                                      # opens one before the window, record the number here and
                                      # re-verify the target tag.
kind: image                           # image tag ONLY. NO chart bump: jameswynn/homepage stays
                                      # 2.1.0 (its appVersion v1.2.0 is a default we override).
current: "v1.13.2"
target: "v2.0.0"
update_type: major
risk: medium                          # major + a 4-day-old release + the middleware now wraps
                                      # EVERY route + the k8s discovery client was swapped.
                                      # NOT high: no persistent data, nothing depends on
                                      # homepage, and revert is a one-line git revert.
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [default]               # everything mutated lives here
  resources:
    - helmrelease/homepage            # image.tag v1.13.2 -> v2.0.0 (chart unchanged)
    - deployment/homepage             # rolls; strategy Recreate -> brief dashboard outage
    - configmap/homepage              # chart-rendered config (services/widgets/settings/bookmarks)
    - serviceaccount/homepage         # unchanged, re-verified against the new discovery path
    - clusterrole/homepage            # CLUSTER-SCOPED, unchanged — but see §1.4, upstream now
    - clusterrolebinding/homepage     # REQUIRES cluster scope for `gateway: true`. Already met.
    - ingress/homepage                # unchanged; Authentik forward-auth stays the only gate
    - servicemonitor/homepage         # unchanged; scrape path now falls under the new matcher
  shared: []                          # NOTHING shared is mutated. Homepage is a cluster-wide
                                      # READER (ingresses / httproutes / gateways / pods / nodes
                                      # / metrics.k8s.io) — read-only, and the v2 change REDUCES
                                      # api-server calls. See §6 for the read-dependency, which
                                      # is a verification-confounder, not a blast radius.
depends_on: []                        # NOT gated by app-template-5.0 — different chart (§1.5)
conflicts_with: []                    # none hard; §6 lists the soft "do not co-schedule" set
security_ref: F-5aebd69d
status: draft
window: "tue-early:2026-08-18"        # 60m slot, cap 6, no-reboot. Shares the slot with
                                      # bitnamilegacy-exit-phase1 (low/1, 25m, ns ai+security,
                                      # shared falco) — zero namespace or shared-infra overlap.
                                      # Budget after both: 3/6 risk, 50/60 min.
auto_execute: false                   # major — operator go/no-go, never unattended
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/homepage-integration.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-08-15"
---

# Homepage: image `v1.13.2` → `v2.0.0`

## 1) Summary & why held

Held because it is a **major** (`v1` → `v2`). Nothing else gates it: `homepage`
is not on the `runbooks/auto-update-policy.yaml` deny-list.

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-5aebd69d** (`security` / severity `accepted`).
> Full detail (CVE IDs, counts, exposure, exploitability) lives on the
> finding record — it is deliberately not reproduced here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-5aebd69d`
> - CLI: `runbooks/policy-cli.py finding show F-5aebd69d`
>
> See `docs/sops/vulnerability-disclosure.md` before adding any
> vulnerability detail to a committed file.

### 1.1) Why this was invisible until now — an audit-logic defect, not a new gap

F-5aebd69d is currently filed under **AR-029 as `accepted`**, on the stated
grounds that we are *"already on the newest upstream tag"*. **That grounds is
false.** `v2.0.0` has existed in `ghcr.io/gethomepage/homepage` since
2026-08-14 and `v2` / `v2.0` / `v2.0.0` are all present in the tag list.

Root cause is ours, in `runbooks/check-all-versions.py::_pick_latest_semver_tag`:

```python
cp = self.parse_version(current_tag) if current_tag else None
if cp:
    same_major = [t for t in version_tags if self._semver_tag_key(t)[0] == cp[0]]
    if same_major:
        return same_major[0]
```

The function **prefers the current tag's major**. For any component a full
major behind, the newest same-major tag *is* the current pin, so the check
reports "latest" and the CVE check files the result into the accepted bucket.
This is a class defect: **every component one major behind is equally invisible
today**, not just homepage. Step 6 fixes it; see §6 for why that step is
separable from the cluster change.

### 1.2) The upstream breaking change — exactly one, and it is opt-in

The `v2.0.0` release notes list a single item under `⚠️ Breaking Changes`:

> - Feature: homepage auth (#6769) @shamoon

The new docs section (`docs/installation/index.md`, added by that PR) is
unambiguous that it must be turned on:

> As of version 2.0, Homepage supports a simple authorization gate with a
> password or OIDC. **When enabled**, Homepage will use password login by
> default unless OIDC variables are provided.
>
> Required environment variables for authentication:
> - `HOMEPAGE_AUTH_ENABLED=true`
> - `HOMEPAGE_AUTH_SECRET` …
> - `HOMEPAGE_EXTERNAL_URL` …

And the gate in the shipped `v2.0.0` `src/utils/env.js` is a strict
string compare, so an unset variable is unambiguously off:

```js
export function isAuthEnabled() {
  return process.env.HOMEPAGE_AUTH_ENABLED === "true";
}
```

**We do not set `HOMEPAGE_AUTH_ENABLED`.** Our only env are
`HOMEPAGE_ALLOWED_HOSTS: "*"` and `TZ`. So the breaking change is inert for us
and the Authentik forward-auth on `ingress/homepage` remains the sole gate.
**Do not enable it in this window** — it would double-gate a dashboard that is
already behind Authentik, and `HOMEPAGE_EXTERNAL_URL` would leak the hostname
into plaintext values.

### 1.3) The change that is NOT in the release notes and does affect us

`src/middleware.js` had its route matcher **widened from `/api/:path*` to
effectively everything**:

```js
// v1.13.2
matcher: "/api/:path*"

// v2.0.0
matcher: [
  "/",
  "/((?!_next/static|_next/image|favicon.ico|robots.txt|manifest.json|sitemap.xml|icons/|api/auth|auth/).*)",
]
```

The middleware also performs the `HOMEPAGE_ALLOWED_HOSTS` host check. In v1
that check only guarded the API; **in v2 it guards the whole dashboard**, and a
host miss returns HTTP 400 for the page, not just for a widget. We are safe
because `HOMEPAGE_ALLOWED_HOSTS: "*"` short-circuits it (`allowAll`). Treat
that value as load-bearing for the rest of this plan's life: tightening it is
now a whole-app change, not an API-only one, and it would also swallow the
ServiceMonitor's `/metrics` scrape path, which the matcher does not exclude.

### 1.4) Kubernetes service discovery — mechanism changed, RBAC requirement already met

Two maintenance entries in the release rewrite the discovery path our dashboard
depends on:

> - Performance: reduce calls to kubernetes api-server (#6963) @emouawad
> - Chore: update kubernetes-node-client (#6959) @shamoon

PR #6963 carries an explicit operator warning:

> ⚠️ Note: RBAC: A ClusterRole / ClusterRoleBinding is required now when
> `gateway: true` — whereas a namespaced RBAC RoleBinding was enough.
>
> This is a performance enhancement that switches from looping on Kubernetes
> namespaces then calling get CRD for each namespace to using 1 API call to
> list HttpRoute CRD on all the cluster.

**We have `kubernetes.gateway: true`, so this warning applies to us — and it is
already satisfied.** The `jameswynn/homepage` chart's `_rbac.yaml` renders a
`ClusterRole` + `ClusterRoleBinding` (never a namespaced `Role`), and the live
objects confirm cluster-scoped `get`/`list`/`watch` on
`gateway.networking.k8s.io/{httproutes,gateways}` — from the chart's built-in
rule plus our `extraClusterRoles` block. **No RBAC change is required.** Verify
it anyway in pre-check (c); this is the single most likely thing to silently
empty the dashboard.

The k8s client library swap (#6959) is the residual risk: discovery is the only
thing homepage does that matters here, and its client was replaced wholesale in
a release that is four days old with no `v2.0.x` patch yet.

### 1.5) Blast radius: the ingress annotation schema does **NOT** change

This was the open question, and the answer bounds the whole plan.
`docs/configs/kubernetes.md` — the document that defines the entire
`gethomepage.dev/*` annotation contract and the discovery mechanism — is
**byte-identical between `v1.13.2` and `v2.0.0`**:

```bash
diff -u <(curl -s https://raw.githubusercontent.com/gethomepage/homepage/v1.13.2/docs/configs/kubernetes.md) \
        <(curl -s https://raw.githubusercontent.com/gethomepage/homepage/v2.0.0/docs/configs/kubernetes.md)
# (no output)
```

`enabled` / `name` / `group` / `icon` / `description` / `pod-selector` /
`widget.*` / `href` / `weight` / `instance` all keep their v1 meaning, and the
annotation-**plus**-label requirement from `docs/sops/homepage-integration.md`
is unchanged.

**Therefore this upgrade does NOT touch every app's ingress.** For scale, had
the schema moved this would have been a cluster-wide rewrite: **66 of 102 live
ingresses** carry `gethomepage.dev/enabled: "true"` (all 66 also carry the
required label), spread over **72 manifest files across 22 namespaces**. None
of them is edited by this plan. Same for the four config files — `settings.md`,
`widgets.md`, `bookmarks.md` and `docker.md` are identical across the two tags,
and `services.md` differs only by two documentation sentences (custom-api
widgets do not support `highlight`; icon sets are fetched from a remote CDN).
Our `config:` block in the HelmRelease needs no edit.

### 1.6) Chart and runtime

- **Chart stays `jameswynn/homepage` 2.1.0.** That is the newest published
  version (2025-05-07) and it is an unofficial chart that has not been updated
  for homepage v2. It pins `bjw-s common` **1.5.1** as an internal subchart
  dependency — this is the *library* chart, **not** the `app-template` chart
  the `app-template-5.0` plan migrates, and `homepage` does not match the
  `*app-template*` deny-list entry. `depends_on` is correctly empty.
- **Runtime is unchanged.** `v1.13.2` and `v2.0.0` build from the same
  `node:22-slim` → `node:22-alpine` stages, same `USER root`, same
  `ENV PORT=3000` / `HOSTNAME=::` / `EXPOSE $PORT`. No probe, port, or
  securityContext change is needed; our probes are `tcpSocket:3000`, which is
  auth- and route-agnostic either way.

## 2) Pre-checks

```bash
# a) target tag actually exists (application-update.md Step 0)
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:gethomepage/homepage:pull&service=ghcr.io" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://ghcr.io/v2/gethomepage/homepage/manifests/v2.0.0" -o /dev/null -w '%{http_code}\n'
#    expect 200.

# b) current state is clean — nothing in flight
flux -n default get helmrelease homepage
kubectl -n default get pods -l app.kubernetes.io/name=homepage
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
#    expect READY=True, 1/1 Running, no non-Ready kustomizations.

# c) THE RBAC GATE (§1.4) — must be cluster-scoped, must cover httproutes.
kubectl get clusterrole homepage -o yaml | grep -A8 'gateway.networking.k8s.io'
kubectl get clusterrolebinding homepage -o jsonpath='{.roleRef.kind}/{.roleRef.name}{"\n"}'
#    expect a ClusterRole (not Role) granting get/list on httproutes + gateways,
#    and ClusterRole/homepage as the roleRef. If either is namespaced: STOP.

# d) baseline the discovery result BEFORE the upgrade, to diff against after.
kubectl get ingress -A -o json | python3 -c "
import sys,json
i=json.load(sys.stdin)['items']
en=[x for x in i if x['metadata'].get('annotations',{}).get('gethomepage.dev/enabled')=='true']
lb=[x for x in en if x['metadata'].get('labels',{}).get('gethomepage.dev/enabled')=='true']
print('ingresses total',len(i),'| homepage-enabled',len(en),'| with label',len(lb))"
#    record the numbers; expect 102 / 66 / 66 at plan time.
kubectl -n default logs -l app.kubernetes.io/name=homepage --tail=100 | grep -ci error || true

# e) FRESHNESS GATE — v2.0.0 was published 2026-08-14, four days before this
#    window, with no patch release behind it. Check for v2 regressions that
#    landed since, especially in kubernetes discovery / auth middleware:
gh api repos/gethomepage/homepage/releases --paginate -q '.[] | "\(.tag_name)\t\(.published_at)"' | head -5
gh issue list --repo gethomepage/homepage --state open --limit 20 --search "kubernetes discovery in:title"
#    If a v2.0.x patch exists: re-verify §1 against it and prefer the patch as
#    the target. If open issues report broken k8s discovery on v2: DEFER to the
#    next window and record why on F-5aebd69d.
```

## 3) Steps

All GitOps. No direct cluster mutation; no manual `flux reconcile` unless the
rollout stalls (§7 of `docs/sops/application-update.md`).

1. **Marker** — so the `alert-triage-agent` treats the roll as expected:
   ```bash
   runbooks/update-marker.sh add homepage default 2 "v1.13.2 -> v2.0.0 major"
   ```

2. **Silence the app's alerts** (attended-update default,
   `docs/sops/application-update.md` Step 1). `strategy: Recreate` means the
   dashboard goes fully down for the roll, so `KubePodNotReady` /
   `KubeDeploymentReplicasMismatch` will fire otherwise:
   ```bash
   kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &
   NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
   END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
   curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
     "matchers":[{"name":"namespace","value":"default","isRegex":false,"isEqual":true},
                 {"name":"alertname","value":"Kube(Pod|Deployment).*","isRegex":true,"isEqual":true}],
     "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window-agent",
     "comment":"homepage v1.13.2->v2.0.0 — suppressing rollout noise. auto-expires 2h"}'
   ```
   Record the returned silence id; delete it in Step 5.

3. **The bump — one line.** In
   `kubernetes/apps/default/homepage/app/helmrelease.yaml`, line 27:
   ```yaml
       image:
         repository: ghcr.io/gethomepage/homepage
   -     tag: v1.13.2
   +     tag: v2.0.0
   ```
   **Change nothing else.** Specifically: do NOT add `HOMEPAGE_AUTH_*` or
   `HOMEPAGE_OIDC_*` env (§1.2), do NOT touch `HOMEPAGE_ALLOWED_HOSTS: "*"`
   (§1.3), do NOT touch `enableRbac` / `extraClusterRoles` (§1.4), do NOT touch
   `chart.spec.version: 2.1.0` (§1.6), and do NOT edit any `gethomepage.dev/*`
   annotation anywhere in the repo (§1.5).

   Leave `upgrade.remediation.retries: 3` **as-is**. Unlike the superset /
   openclaw cases the SOP warns about, homepage runs no startup migration and
   holds no state — if the new image crash-loops, Flux's automatic rollback to
   v1.13.2 is the outcome we want, not a thrash to fight.

4. **Commit + push** (work on `main`, stage only this hunk):
   ```bash
   git add -p kubernetes/apps/default/homepage/app/helmrelease.yaml
   git commit -m "fix(homepage): image v1.13.2 -> v2.0.0 (major; security driver F-5aebd69d)

   Upstream's only breaking change (auth, #6769) is opt-in via
   HOMEPAGE_AUTH_ENABLED and stays off — Authentik forward-auth remains the
   gate. Ingress annotation schema is unchanged between the tags, so no app
   ingress is touched. Chart stays jameswynn/homepage 2.1.0.

   Plan: runbooks/maintenance/plans/homepage-2.0.0.md"
   git push
   ```
   > Commit message stays publish-safe: reference the finding id, never the
   > detail (`docs/sops/vulnerability-disclosure.md`).

5. **Watch the roll** (Recreate: old pod terminates before the new one starts):
   ```bash
   kubectl -n default rollout status deploy/homepage --timeout=5m
   kubectl -n default logs -l app.kubernetes.io/name=homepage -f --tail=50
   ```
   Then run §4. On success: delete the silence, `runbooks/update-marker.sh
   clear homepage`.

6. **Re-triage the finding, then fix the audit defect** (repo-side, no cluster
   change — safe to defer out of the window if the slot is tight):
   ```bash
   source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up
   runbooks/policy-cli.py finding detail F-5aebd69d --plan homepage-2.0.0 --detail-file /tmp/d.md
   ```
   `/tmp/d.md` records the post-upgrade scan result and the AR-029
   misclassification (detail belongs there, not here). Then fix
   `_pick_latest_semver_tag` in `runbooks/check-all-versions.py` so a
   higher-major tag is reported as available instead of the current pin being
   echoed back as "latest" — per the house rule, fix a false positive at the
   audit-logic root cause rather than re-accepting the symptom. Leaving this
   undone means the next component a full major behind is equally invisible.

## 4) Verification

```bash
# 1. HelmRelease reconciled; DEPLOYED image is the new tag (not just READY=True)
flux -n default get helmrelease homepage
kubectl -n default get deploy homepage -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
#    expect ghcr.io/gethomepage/homepage:v2.0.0

# 2. Pod Ready and STABLE (0 restarts after ~2 min settle)
kubectl -n default get pods -l app.kubernetes.io/name=homepage

# 3. THE REAL TEST — service discovery still finds everything. Compare against
#    the pre-check (d) baseline: the dashboard must show the same service count.
kubectl -n default logs -l app.kubernetes.io/name=homepage --tail=200 | grep -iE 'error|forbidden|rbac|cannot list'
#    expect NO 'forbidden' / 'cannot list' — those would mean §1.4 RBAC regressed.

# 4. Dashboard renders and is still gated by Authentik (not by homepage's own
#    new auth): open https://homepage.${SECRET_DOMAIN} — expect the Authentik
#    login, then the dashboard. If a homepage-native /auth/signin page appears,
#    HOMEPAGE_AUTH_ENABLED leaked in — revert (§5).
#    Spot-check by eye, against the pre-check (d) count of 66:
#      - every group in settingsString is populated (AI, Databases, System,
#        Network Services, Home Automation, Monitoring, Infrastructure, Office,
#        Media, Download)
#      - the k8s `resources` + `kubernetes` widgets show node cpu/memory
#        (proves metrics.k8s.io access survived the client swap)
#      - the 3 Monitoring entries with podSelector show pod status
#      - the manually-configured Infrastructure entries still ping

# 5. Gateway discovery specifically (the #6963 rewrite, cluster-wide list now)
kubectl get httproute -A; kubectl get gateway -A
#    the HTTPRoute-backed entries must still appear on the dashboard.

# 6. Host check did not start biting (the widened matcher, §1.3)
kubectl -n default logs -l app.kubernetes.io/name=homepage --tail=200 | grep -i 'host validation'
#    expect nothing.

# 7. Nothing else in the cluster moved
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'

# 8. Post-scan result goes on F-5aebd69d, NOT in this file.
```

## 5) Rollback

Concrete and cheap — this is why the plan is `medium` and not `high`. Homepage
holds **no persistent data** (its only volume is an `emptyDir` for logs) and
**nothing in the cluster depends on it**, so a revert is lossless and total.

```bash
# 1. revert the one-line bump
git revert --no-edit <sha-from-step-4>
git push
# 2. Flux reconciles back to v1.13.2 (or already did it for you — remediation
#    retries:3 auto-rolls back a crash-looping release; confirm which happened)
flux -n default get helmrelease homepage
kubectl -n default get deploy homepage -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
#    expect ghcr.io/gethomepage/homepage:v1.13.2
# 3. confirm the cluster is back
kubectl -n default rollout status deploy/homepage --timeout=5m
kubectl -n default get pods -l app.kubernetes.io/name=homepage
#    then re-open https://homepage.${SECRET_DOMAIN} and re-check the group/service
#    counts against the pre-check (d) baseline.
# 4. clear the marker + silence; set this plan's status to `blocked` with the
#    reason, and record the failure detail on F-5aebd69d.
runbooks/update-marker.sh clear homepage
```

No RBAC, config, annotation, chart or secret change is made by this plan, so
there is nothing else to restore. If Flux has already auto-rolled back and is
sitting in a failed-upgrade loop, the `git revert` is still the correct fix —
it makes the reverted spec the desired state instead of a remediation artifact.

## 6) Interference notes

- **`shared: []` is deliberate and is the headline finding.** The obvious fear —
  that a homepage major rewrites the `gethomepage.dev/*` contract and therefore
  touches all **66 homepage-enabled ingresses across 22 namespaces** — **does
  not materialise**: the annotation/discovery document is byte-identical
  between the two tags (§1.5). This plan edits exactly one line in one file.
  The true blast radius is `default/homepage` and a few minutes of dashboard
  downtime.

- **Homepage is a cluster-wide READER, and that is a verification confounder,
  not a blast radius.** It lists ingresses, HTTPRoutes, Gateways, pods, nodes
  and `metrics.k8s.io` across every namespace. It mutates none of them, and
  #6963 *reduces* api-server load. But it means **any co-scheduled plan that
  churns ingresses, HTTPRoutes, the Gateway, or metrics-server will make §4's
  discovery verification unreadable** — you cannot tell "v2 discovery broke"
  from "that app's ingress is mid-rollout". Soft do-not-co-schedule set:
  `envoy-gateway-phase2` / `-phase3`, `ingress-nginx-1.15.6`, and anything
  moving metrics-server. None of these is currently in `tue-early:2026-08-18`.

- **Chosen slot `tue-early:2026-08-18` is clean.** It holds
  `bitnamilegacy-exit-phase1` (risk low/1, 25 min, namespaces `ai` + `security`,
  `shared: [falco]`). Zero overlap with `default` and zero overlap with falco.
  Combined budget 3/6 risk-weight and 50/60 minutes — fits with headroom.
  Deliberately **not** `thu-early:2026-08-20` (superset-redis-official already
  books 45 of that window's 60 minutes) and **not** `sat-early:2026-08-22`
  (kube-prometheus-stack-88 perturbs `shared: [monitoring]`, and homepage owns a
  ServiceMonitor — harmless in reality but it muddies both verifications).
  `sun-window:2026-08-16` is reserved for `talos-v1.13.8`; homepage is
  `needs_reboot: false` and must not consume the only reboot-capable slot.

- **Freshness is the honest reason this is not `risk: low`.** `v2.0.0` shipped
  2026-08-14 — four days before the window, with no `v2.0.x` patch behind it,
  and it carries both a brand-new auth middleware wrapping every route and a
  wholesale Kubernetes client swap. Pre-check (e) is a real gate, not a
  formality: if a patch release exists by the window, prefer it; if v2 k8s
  discovery regressions are open upstream, defer. The counter-argument for
  going early rather than soaking is that the failure mode is "dashboard down
  for five minutes" and the revert is one line.

- **Two traps for whoever executes it.** (1) `HOMEPAGE_AUTH_ENABLED` must stay
  **absent** — homepage is already behind Authentik forward-auth, and enabling
  the native gate would double-gate it and require `HOMEPAGE_EXTERNAL_URL`,
  which puts the hostname in plaintext values in a public repo. (2)
  `HOMEPAGE_ALLOWED_HOSTS: "*"` is now load-bearing for the entire app, not just
  `/api` (§1.3) — do not "tighten" it opportunistically during this window.

- **Not blocked by, and does not block, `app-template-5.0`.** Homepage is
  delivered by `jameswynn/homepage` 2.1.0, which pins `bjw-s common` 1.5.1 as an
  internal subchart. That is the library chart, not the `app-template` chart
  being migrated, and `homepage` does not match the `*app-template*` deny-list
  entry. The two plans are independent in both directions.
