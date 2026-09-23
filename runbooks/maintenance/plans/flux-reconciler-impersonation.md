---
plan_id: flux-reconciler-impersonation
component: flux-system
pr: null                              # not a Renovate item; PLAN-lane sweep finding
kind: infra
current: "kustomize-controller v1.9.4 and helm-controller v1.6.3 run --watch-all-namespaces=true with NO --default-service-account, both bound to cluster-admin by clusterrolebinding/cluster-reconciler-flux-system. All 140 Kustomizations and 125 HelmReleases across 18 namespaces (zero explicit spec.serviceAccountName, zero spec.kubeConfig) are applied as cluster-admin. The live FluxInstance already carries cluster.tenantDefaultServiceAccount=default with multitenant=false and that renders NOTHING (verified against flux-operator v0.57.0 source, section 1.2)."
target: "Both controllers carry --default-service-account=flux-reconciler, rendered by FluxInstance spec.kustomize.patches (NOT by tenantDefaultServiceAccount, which only takes effect under the rejected multitenant profile). A ServiceAccount flux-reconciler exists in each of the 18 namespaces with TIERED RBAC: 9 platform namespaces (ai cert-manager default flux-system kube-system monitoring network security storage) keep cluster-admin because their content creates ClusterRoles/CRDs/webhooks; 8 storage-owning app namespaces get namespace-admin plus PersistentVolume/StorageClass; my-software-production gets namespace-admin only. cluster-meta and cluster-apps pin serviceAccountName explicitly."
update_type: security
risk: high                            # NOT from the diff size. The change alters the
                                      # identity EVERY reconcile runs under; a wrong
                                      # binding stops a whole namespace reconciling,
                                      # and a wrong flux-system binding stops the
                                      # cluster reconciling INCLUDING the revert.
est_duration_min: 70                  # Stage A 12 + B1 10 + B2 10 + C 20 + D 8 = 60,
                                      # plus 10 rollback budget. This is the WHOLE
                                      # usable sat-attended budget (90 - 20 Step-0
                                      # reserve); a Sunday slot with no reboot plan
                                      # gives margin and is acceptable — this is not
                                      # reboot work, so it must not displace one.
needs_reboot: false
touches:
  namespaces: [ai, backup, cert-manager, databases, default, download, flux-system, home-automation, kube-public, kube-system, media, monitoring, my-software-development, my-software-production, my-software-showcase, network, office, security, storage]
  resources:
    - fluxinstance/flux (flux-system)
    - deployment/kustomize-controller (flux-system)
    - deployment/helm-controller (flux-system)
    - helmrelease/flux-instance (flux-system)
    - configmap/flux-instance-helm-values-* (flux-system, generator-hashed)
    - kustomization/cluster-meta (flux-system)
    - kustomization/cluster-apps (flux-system)
    - kustomization/flux-reconciler-rbac (flux-system, NEW)
    - kustomization/impersonation-probe (kube-public, NEW, window-scoped)
    - "18x serviceaccount/flux-reconciler + rolebinding/flux-reconciler (NEW)"
    - "9x clusterrolebinding/flux-reconciler-cluster-admin-<ns> (NEW)"
    - "8x clusterrolebinding/flux-reconciler-storage-<ns> (NEW)"
    - clusterrole/flux-reconciler-namespaced, clusterrole/flux-reconciler-storage (NEW)
    - kustomization/jdownloader, kustomization/tube-archivist (download, canary)
    - "helmrelease/{jdownloader,tube-archivist,tube-archivist-elasticsearch,tube-archivist-redis} (download, canary)"
  shared: [flux, monitoring]          # flux IS the shared infra every other plan
                                      # depends on; monitoring because section 4
                                      # reads Prometheus and Alertmanager.
depends_on: []
conflicts_with:                       # exclusive: true already keeps the slot empty;
  - flux-oci-chart-sources            # these name WHY. Rewrites Flux sources.
  - helm-drift-detection              # changes HelmRelease behaviour cluster-wide.
  - kube-prometheus-stack-91.4.1      # the window's instrument (section 4 reads it).
  - talos-1.14.1                      # node roll restarts the controllers mid-proof.
exclusive: true                       # No other change may be IN FLIGHT while the
                                      # identity Flux applies under is being swapped:
                                      # a concurrent plan's git-revert rollback needs a
                                      # working reconciler, and this plan is the one
                                      # thing that can take that away.
security_ref: F-7b847e3e
capability_change: true               # Flux's authorization behaviour changes:
                                      # what a Kustomization/HelmRelease in a given
                                      # namespace CAN apply is narrowed. Never
                                      # unattended.
autonomy_override: human-gated        # RESTRICTS only. Needs a FRESH operator GO on
                                      # the day; nothing recorded before this file
                                      # existed covers it.
rollback_class: git-revert            # every stage is a manifest commit; section 5
                                      # additionally carries the break-glass for the
                                      # one state where the revert cannot reconcile.
finding_refs:
  - F-7b847e3e                        # the plan-or-page join key; DB record has the
                                      # exposure detail — do not restate it here.
premises:                             # read 2026-09-22 ~15:00Z; 10/10 PASS at authoring.
  - id: flag-not-rendered-yet
    why: >-
      The whole plan assumes neither controller carries --default-service-account
      today. If one already does, the staged rollout below is not what is being
      changed and every gate baseline is wrong.
    run: >-
      kubectl get deploy -n flux-system kustomize-controller helm-controller -o json
      | jq '[.items[].spec.template.spec.containers[0].args[]]'
      | jq 'map(select(startswith("--default-service-account")))'
      | jq 'length'
    expect_exact: "0"
  - id: fluxinstance-patches-empty
    why: >-
      Stage C sets spec.kustomize.patches from an EMPTY list. A non-empty list means
      someone already customises the controllers and the yq edit in section 3.4 would
      clobber it — merge by hand instead.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.spec.kustomize.patches}'
    expect_exact: "[]"
  - id: multitenant-off
    why: >-
      The design deliberately does NOT enable the multitenant profile (it would add
      --no-cross-namespace-refs and break 130/135 Kustomizations and 123/125
      HelmReleases per docs/sops/flux-image-automation-push-auth.md). If it is on,
      --default-service-account is ALREADY rendered and this plan is moot.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='multitenant={.spec.cluster.multitenant}'
    expect_exact: "multitenant=false"
  - id: operator-v0.57.0
    why: >-
      The patch semantics (profile patches first, spec.kustomize.patches appended
      last; --default-service-account only in the multitenant profile) were read
      from flux-operator v0.57.0 source. A bump between authoring and execution
      means re-reading internal/builder/profiles.go and
      internal/controller/fluxinstance_controller.go at the new tag before running.
    run: kubectl get deploy -n flux-system flux-operator -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "flux-operator:v0.57.0"
  - id: no-explicit-sa-anywhere
    why: >-
      The survey found zero Kustomizations/HelmReleases with spec.serviceAccountName.
      One appearing since means someone started this work another way; reconcile
      the two designs before continuing.
    run: >-
      kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases -A -o json
      | jq '[.items[].spec.serviceAccountName]'
      | jq 'map(select(. != null))'
      | jq 'length'
    expect_exact: "0"
  - id: flux-reconciler-sa-absent
    why: >-
      Stage A creates serviceaccount/flux-reconciler in 18 namespaces. If any exists
      already the plan was partially executed or aborted mid-way; find out which
      stage landed before re-running from section 3.1.
    run: >-
      kubectl get serviceaccounts -A -o json
      | jq '[.items[].metadata.name]'
      | jq 'map(select(. == "flux-reconciler"))'
      | jq 'length'
    expect_exact: "0"
  - id: namespace-set-unchanged
    why: >-
      tenants.yaml (section 3.1) covers exactly these 18 namespaces. A namespace
      hosting a Kustomization or HelmRelease that is NOT in this list gets NO
      ServiceAccount and NO RBAC, and after Stage C every reconcile in it fails with
      forbidden. Regenerate tenants.yaml with the new namespace (and classify its
      tier from the two premises below) before running.
    run: >-
      kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases -A -o json
      | jq -r '[.items[].metadata.namespace]'
      | jq -r 'unique'
      | jq -r 'join(" ")'
    expect_exact: "ai backup cert-manager databases default download flux-system home-automation kube-system media monitoring my-software-development my-software-production my-software-showcase network office security storage"
  - id: tier-a-owner-set-unchanged
    why: >-
      The 9 namespaces whose reconciled content OWNS non-storage cluster-scoped
      objects (ClusterRole, ClusterRoleBinding, CRD, webhook, Namespace, VAP, ...)
      are the ones bound to cluster-admin. RBAC escalation prevention means a
      ServiceAccount cannot create a ClusterRole/Binding whose permissions it does
      not itself hold, so a scoped grant here would fail on the next chart bump.
      A namespace joining this set needs a cluster-admin CRB added in tenants.yaml;
      one leaving it can be demoted (follow-up, not this window). Measured from the
      ownership labels/annotations kustomize-controller and Helm stamp on every
      object they apply.
    run: >-
      kubectl get clusterroles,clusterrolebindings,crds,mutatingwebhookconfigurations,validatingwebhookconfigurations,namespaces,validatingadmissionpolicies,validatingadmissionpolicybindings,clusterissuers,gatewayclasses,csidrivers,priorityclasses,nodefeaturerules,volumesnapshotclasses,apiservices -o json
      | jq '[.items[].metadata]'
      | jq 'map(.labels["kustomize.toolkit.fluxcd.io/namespace"] // .annotations["meta.helm.sh/release-namespace"] // empty)'
      | jq -r 'unique'
      | jq -r 'join(" ")'
    expect_exact: "ai cert-manager default flux-system kube-system monitoring network security storage"
  - id: storage-owner-set-unchanged
    why: >-
      Namespaces whose content owns a PersistentVolume or StorageClass need the
      flux-reconciler-storage ClusterRole (the 8 non-platform ones get a CRB in
      tenants.yaml; the platform ones in this list are cluster-admin anyway).
      my-software-production is deliberately ABSENT from this list and gets no
      cluster-scoped grant at all. A new owner appearing needs a storage CRB first.
    run: >-
      kubectl get pv,sc -o json
      | jq '[.items[].metadata]'
      | jq 'map(.labels["kustomize.toolkit.fluxcd.io/namespace"] // .annotations["meta.helm.sh/release-namespace"] // empty)'
      | jq -r 'unique'
      | jq -r 'join(" ")'
    expect_exact: "ai backup databases download home-automation kube-system media monitoring my-software-development my-software-showcase office"
  - id: nothing-failing-before-we-start
    why: >-
      Section 4 reads "count of not-Ready == 0" after each stage. That gate is only
      meaningful against a baseline of 0; a pre-existing failure would be
      misattributed to this change (or hide a new one). Counts Ready=False ONLY:
      Ready=Unknown is a reconcile in flight, and with 140 Kustomizations on 1m
      intervals one is in flight at almost any instant (measured 2026-09-22 — a
      "!= True" form read 1 and 0 twenty seconds apart).
    run: >-
      kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases -A -o json
      | jq '[.items[].status.conditions[]]'
      | jq 'map(select(.type == "Ready"))'
      | jq 'map(select(.status == "False"))'
      | jq 'length'
    expect_exact: "0"
status: awaiting-go   # reviewed 2026-09-23 (needs-fix -> both blocking gate fixes applied below)
window: "sun-attended:2026-10-11"   # scheduled 2026-09-23 per the review: earliest reboot-free attended slot; needs a fresh GO on the day
                                      # the slot shape (attended, exclusive, no reboot).
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/flux-upgrade.md
  - docs/sops/flux-image-automation-push-auth.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-22"
---

# Stop Flux applying everything as cluster-admin: per-namespace reconciler impersonation

Driver: sweep finding `F-7b847e3e` (section `plan`, lane PLAN). The exposure
detail lives on the finding record — `python3 runbooks/policy-cli.py finding show
F-7b847e3e` — and is deliberately not restated here (public repo). This file is
the staged, verifiable answer to it.

## 1. Summary & why held

### 1.1 What changes

Today every `Kustomization` and `HelmRelease` in the cluster is applied by
`kustomize-controller` / `helm-controller` **as cluster-admin**, because both
controller ServiceAccounts are bound to `cluster-admin`
(`clusterrolebinding/cluster-reconciler-flux-system`, live) and neither
controller carries `--default-service-account` (live args, read 2026-09-22:
`--events-addr`, `--watch-all-namespaces=true`, `--log-level=info`,
`--log-encoding=json`, `--enable-leader-election`,
`--feature-gates=ObjectLevelWorkloadIdentity=false` — nothing else).

After this plan, both controllers carry `--default-service-account=flux-reconciler`.
Flux then applies every Kustomization/HelmRelease that names no
`spec.serviceAccountName` **as `system:serviceaccount:<its own namespace>:flux-reconciler`**
(upstream Kustomization docs: *"all Kustomizations which don't have
`.spec.serviceAccountName` specified will use the service account name provided
by `--default-service-account=<SA Name>` in the namespace of the object"*; the
HelmRelease docs say the same for Helm actions and Helm storage). The controllers
keep their cluster-admin binding — they need it to impersonate — but every
apply is now bounded by the impersonated account's RBAC.

What is and is not impersonated (read from the pinned controller sources,
`kustomize-controller` v1.9.4 `internal/controller/kustomization_controller.go`
and `helm-controller` v1.6.3 `internal/controller/helmrelease_controller.go`):

| Operation | Client | Consequence for RBAC design |
|---|---|---|
| kustomize-controller server-side apply, prune, health checks / status poller | **impersonated** (`ssa.NewResourceManager(kubeClient, statusPoller, …)`) | the tenant SA needs rights on everything in the Kustomization's inventory |
| `spec.decryption.secretRef` (sops-age) | `r.Client` — controller's own | tenant SA needs NO secret read for decryption |
| `spec.postBuild.substituteFrom` (cluster-settings / cluster-secrets) | `r.Client` — controller's own | tenant SA needs NO read of those |
| source artifact download | HTTP fetcher | n/a |
| helm-controller install/upgrade/rollback/uninstall/test, Helm release storage (release Secrets in the HR namespace), `crds: CreateReplace` | **impersonated** (`kube.WithImpersonate(obj.Spec.ServiceAccountName, obj.GetNamespace())`, falling back to the controller default) | tenant SA needs rights on everything the chart renders, plus `secrets` in its namespace |
| `spec.valuesFrom` | `r.Client` — controller's own | no tenant grant needed |

### 1.2 Why the finding's prescribed remedy is wrong as written (repo correction)

The finding says *"set FluxInstance `spec.cluster.tenantDefaultServiceAccount`
to render `--default-service-account`"*. **That field is inert on this cluster
and would stay inert.** Live evidence: the FluxInstance already has
`tenantDefaultServiceAccount: default` (since the chart default) with
`multitenant: false`, and neither controller has the flag. Upstream source at
the deployed tag confirms why — `flux-operator` v0.57.0,
`internal/controller/fluxinstance_controller.go`:

```go
if obj.GetCluster().Multitenant {
    options.Patches += builder.GetProfileMultitenant(
        obj.GetCluster().TenantDefaultServiceAccount)
}
```

and `internal/builder/profiles.go` puts `--default-service-account=%s` **only**
inside the multitenant profile, alongside `--no-cross-namespace-refs=true` on
every controller and `--no-remote-bases=true` on kustomize-controller.
`multitenant: true` is the lockdown `docs/sops/flux-image-automation-push-auth.md`
§"Do not reach for `--no-cross-namespace-refs`" rejected on measured grounds
(130/135 Kustomizations and 123/125 HelmReleases source from `flux-system`; the
survey today: 140/140 and 125/125 — see 1.3). So the finding's remedy is
"flip the one field that does nothing" and the obvious next step would be
"flip the field that breaks the cluster".

The correct instrument, from the same controller file, is the operator's
generic patch hook, applied **after** every profile:

```go
if obj.Spec.Kustomize != nil && len(obj.Spec.Kustomize.Patches) > 0 {
    patchesData, err := yaml.Marshal(obj.Spec.Kustomize.Patches)
    ...
    options.Patches += string(patchesData)
}
```

A `spec.kustomize.patches` entry adding the arg to the two Deployments renders
exactly the flag the multitenant profile would, and nothing else. The
`flux-instance` chart passes `instance.kustomize` through verbatim
(`kustomize: {{ .Values.instance.kustomize | toYaml | nindent 4 }}` in
`templates/instance.yaml`), so the change is one block in
`kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml`.

**The finding's `action` text should be amended to say this** (attach via
`policy-cli.py finding detail F-7b847e3e --plan flux-reconciler-impersonation`);
this plan is read-only against the DB and has not done so.

### 1.3 The survey (read-only, 2026-09-22, the design's ground truth)

| Measure | Value |
|---|---|
| Kustomizations / HelmReleases | **140 / 125**, all Ready |
| Namespaces hosting either | **18**: ai backup cert-manager databases default download flux-system home-automation kube-system media monitoring my-software-development my-software-production my-software-showcase network office security storage |
| Kustomizations living in `flux-system` | 6 (`flux-system` root, `cluster-meta`, `cluster-apps`, `flux-guardrails`, `flux-operator`, `flux-instance`); the other 134 live in their app namespace with `targetNamespace` = own namespace |
| Explicit `spec.serviceAccountName` / `spec.kubeConfig` | **0 / 0** on both kinds |
| HelmReleases with `crds: CreateReplace` | 7, all in kube-system / monitoring / network (platform tier) |
| Cross-namespace namespaced objects | Kustomizations: only `cluster-apps` (18 Namespaces + per-namespace cluster-settings/cluster-secrets/sops-age + 134 child Kustomizations). Helm: `cert-manager`→kube-system Role/RB, `cilium`→cilium-secrets Role/RB, `kube-prometheus-stack`→kube-system Service/Endpoints — all platform tier |
| Cluster-scoped objects owned by Kustomizations (inventory) | 35 PersistentVolume, 22 Namespace, 21 CRD, 19 StorageClass, 5+5 ClusterRole/CRB, 2 ClusterIssuer, 2+2 VAP/VAPB, 2 NodeFeatureRule, 1 GatewayClass, 1 VolumeSnapshotClass, Cilium L2/IPPool — spread over **57 of 140** Kustomizations |
| Cluster-scoped objects owned by Helm releases (decoded release manifests) | 8 release namespaces: cert-manager, default (homepage ClusterRole+CRB), flux-system, kube-system, monitoring, network, security, storage |
| RoleBindings to a ClusterRole rendered by any chart | **0** (no `bind`-escalation trap in Tier B) |
| Existing `admin`/`edit`/`cluster-admin` RoleBindings cluster-wide | **0** — the exposure is latent, as the finding says |
| Flux controller metrics scraped by Prometheus | **none** (`gotk_*` absent); only flux-operator's `flux_resource_info` / `flux_instance_info` exist — section 4 is built on those plus controller logs |

### 1.4 The tiered design that falls out of the survey

One ServiceAccount name everywhere (`flux-reconciler`), `automountServiceAccountToken: false`
(no pod ever uses it — it exists only to be impersonated), and three grant shapes:

| Tier | Namespaces | Grant | Why |
|---|---|---|---|
| **A — platform** | ai, cert-manager, default, flux-system, kube-system, monitoring, network, security, storage (9) | `ClusterRoleBinding` → `cluster-admin` | Their content creates ClusterRoles/CRBs/CRDs/webhooks. RBAC escalation prevention (a principal may only create a (Cluster)Role it already holds every rule of, or hold `escalate`/`bind`) makes any narrower grant equivalent to cluster-admin with extra steps, and one that silently breaks on the next chart bump at 03:30. |
| **B — app + storage** | backup, databases, download, home-automation, media, my-software-development, my-software-showcase, office (8) | `RoleBinding` → ClusterRole `flux-reconciler-namespaced` (`*/*/*`, namespace-bounded) **plus** `ClusterRoleBinding` → ClusterRole `flux-reconciler-storage` (`persistentvolumes`, `storageclasses`) | They own PVs (longhorn-static pattern) and/or CIFS StorageClasses, nothing else cluster-scoped. |
| **B — app only** | my-software-production (1) | `RoleBinding` → `flux-reconciler-namespaced` only | Owns nothing cluster-scoped. Zero cluster-scope rights. |

The RoleBinding-to-ClusterRole shape is chosen on purpose: a RoleBinding can
only ever grant within its own namespace, and `*/*/*` covers every CRD kind
(HTTPRoute, ServiceMonitor, PrometheusRule, Certificate, …) that the built-in
`admin`/`edit` roles do NOT aggregate — the survey shows those kinds in nearly
every app namespace, so `admin` would have broken all of them.

**What this closes and what it leaves.** After Stage C, a principal who can
create a Kustomization/HelmRelease in a Tier-B namespace gets namespace-admin
there plus PV/StorageClass — not the cluster. In Tier-A namespaces the identity
is still cluster-admin; `edit` in kube-system/flux-system/monitoring is
already game-over, but `default` (homepage's ClusterRole/CRB) and `ai`
(ai-sre/mcpo ClusterRole/CRB) are Tier A only because one app each renders
cluster RBAC. Moving that RBAC into a flux-system-owned Kustomization would
demote both — a follow-up, recorded in section 6, not this window. The
cluster-wide `persistentvolumes`/`storageclasses` grant to Tier B is also a
residual (a StorageClass with `subdir: /` + reclaim `Delete` is the
`docs/sops/storage-safety.md` catastrophe class) — same follow-up.

### 1.5 Why this is a window, not an edit

A wrong binding does not break one app: **every Kustomization and HelmRelease
in that namespace stops reconciling**, and a wrong `flux-system` binding stops
`cluster-apps`, `cluster-meta` and the root sync — including the ability to
reconcile the revert. Section 5 carries the break-glass for exactly that state.
Hence: attended, exclusive, human-gated, and staged so that the flux-system
identity is proven under an explicit `serviceAccountName` (Stage B2) before
the default flips for everything (Stage C).

## 2. Pre-checks

Run in the window, after Step 0, before anything is committed. The frontmatter
premises are re-run by the window agent (`plan-premises.py --require-premises`);
these are the human-read checks on top.

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.1 Premises, live (all ten must PASS; a FAIL is a stop, not a warning)
.venv/bin/python3 runbooks/plan-premises.py flux-reconciler-impersonation

# 2.2 Shared worktree is clean of OTHER people's edits to the files this plan touches.
#     On 2026-09-22 an uncommitted PSA edit sat on kubernetes/flux/components/common/namespace.yaml
#     (F-b0ec926b). It must be committed or stashed by its owner first — cluster-apps
#     re-applies every Namespace in Stage B2 and a half-edited namespace file would ride in.
git status --porcelain -- kubernetes/flux kubernetes/apps/flux-system kubernetes/apps/download
# EXPECT: empty.

# 2.3 Flux is quiescent: nothing mid-rollout, source fresh
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
mise exec -- kubectl get gitrepository -n flux-system flux-system -o jsonpath='{.status.artifact.revision}{"\n"}'
# EXPECT: header-only for both awk lines; revision == `git rev-parse main` after your last push.

# 2.4 Record the baselines the gates compare against
mise exec -- kubectl get pods -n flux-system -o custom-columns='NAME:.metadata.name,STARTED:.status.startTime' | grep -E 'kustomize-controller|helm-controller'
date -u +%Y-%m-%dT%H:%M:%SZ   # T0 — every "since" below is relative to this

# 2.5 Instruments alive (section 4 CONTROL lines are meaningless otherwise)
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s 'http://localhost:19090/api/v1/query' --data-urlencode 'query=count by (kind) (flux_resource_info{kind=~"Kustomization|HelmRelease", suspended="False"})' | grep -o '"kind":"[A-Za-z]*"},"value":\[[0-9.]*,"[0-9]*"'
# EXPECT: Kustomization 140, HelmRelease 125 (re-measure; the numbers are the FLOOR for section 4).
curl -s 'http://localhost:19090/api/v1/query' --data-urlencode 'query=ALERTS{alertname=~"Flux.*",alertstate="firing"}' | grep -c alertname
# EXPECT: 0
kill $PF 2>/dev/null

# 2.6 Silence the ONE expected alert and drop the update marker (application-update SOP step 1)
#     The window-scoped probe (section 3.1) is Ready=False for ~20 min BY DESIGN after Stage C;
#     FluxResourceNotReady has for: 15m and would page. Silence the probe ONLY — a broad Flux
#     silence would blind the very gate this window relies on.
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 >/dev/null 2>&1 & AM=$!; sleep 2
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"alertname","value":"FluxResourceNotReady","isRegex":false,"isEqual":true},
              {"name":"name","value":"impersonation-probe","isRegex":false,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"operator",
  "comment":"flux-reconciler-impersonation: probe Kustomization is not-ready by design. auto-expires 3h"}'
kill $AM 2>/dev/null
runbooks/update-marker.sh add flux-system flux-system 3 "flux-reconciler-impersonation (F-7b847e3e)"
```

## 3. Steps

All GitOps. Every commit uses `git commit --only <paths>` (shared worktree),
then `git log -1 --format=%s` must show YOUR subject and `git show --stat HEAD`
must list only your files, before `git push`. Each stage has a gate in section 4;
**do not start the next stage until its gate passes** — the stages are ordered
so that the blast radius of each failure is contained by the stage before it.

### 3.1 Stage A — create the identities and their RBAC (inert until something impersonates)

New Flux Kustomization `flux-reconciler-rbac` in `flux-system`, owned by
`cluster-apps` (so it is applied by the platform identity — before Stage C the
controller SA, after it `flux-system:flux-reconciler`, both cluster-admin, so
creating a cluster-admin CRB never trips escalation prevention). **No
`targetNamespace`** — it creates objects in 18 namespaces by explicit
`metadata.namespace`, like `flux-guardrails` creates cluster-scoped objects.

```bash
cd /Users/mu/code/cberg-home-nextgen
D=kubernetes/apps/flux-system/flux-reconciler-rbac
mkdir -p $D/app $D/probe

cat > $D/ks.yaml <<'EOF'
---
# yaml-language-server: $schema=https://raw.githubusercontent.com/fluxcd-community/flux2-schemas/main/kustomization-kustomize-v1.json
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: &app flux-reconciler-rbac
  namespace: flux-system
spec:
  commonMetadata:
    labels:
      app.kubernetes.io/name: *app
  interval: 30m
  path: ./kubernetes/apps/flux-system/flux-reconciler-rbac/app
  prune: true
  sourceRef:
    kind: GitRepository
    name: flux-system
    namespace: flux-system
  # No targetNamespace ON PURPOSE: this Kustomization creates the
  # flux-reconciler ServiceAccount + RoleBinding in EVERY namespace that hosts
  # a Kustomization/HelmRelease (18 on 2026-09-22) and the cluster-scoped
  # ClusterRoles/ClusterRoleBindings. A targetNamespace would fold all 18
  # ServiceAccounts into flux-system and every impersonated reconcile would
  # fail with "forbidden". See runbooks/maintenance/plans/flux-reconciler-impersonation.md
  # (retired after execution; the design is summarised in tenants.yaml's header).
  timeout: 5m
  # wait: false ON PURPOSE. wait: true health-checks every applied object,
  # INCLUDING the kube-public probe Kustomization, which is not-Ready BY
  # DESIGN after stage C — with wait: true that would propagate and mark this
  # Kustomization Ready=False (kstatus reads the child's Ready condition).
  # ServiceAccounts/RoleBindings/ClusterRoleBindings have no rollout to wait
  # for; "Applied" is their whole health. Gate A2/A3 checks the CONTENTS.
  wait: false
EOF

cat > $D/app/kustomization.yaml <<'EOF'
---
# yaml-language-server: $schema=https://json.schemastore.org/kustomization
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ./clusterroles.yaml
  - ./tenants.yaml
  - ./probe-kustomization.yaml   # window-scoped; removed in Stage D
EOF

cat > $D/app/clusterroles.yaml <<'EOF'
---
# Bound via a RoleBinding in each tenant namespace: a RoleBinding can only
# ever grant inside its own namespace, and "*" covers the CRD kinds
# (HTTPRoute, ServiceMonitor, PrometheusRule, Certificate, ...) that the
# built-in admin/edit ClusterRoles do NOT aggregate.
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: flux-reconciler-namespaced
rules:
  - apiGroups: ["*"]
    resources: ["*"]
    verbs: ["*"]
---
# Bound cluster-wide ONLY in namespaces whose Kustomizations own a
# PersistentVolume (longhorn-static pattern) or a StorageClass (CIFS classes).
# Residual: this is cluster-wide PV/StorageClass control — see the follow-up
# on F-7b847e3e about moving PV/SC manifests under a flux-system-owned path.
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: flux-reconciler-storage
rules:
  - apiGroups: [""]
    resources: ["persistentvolumes"]
    verbs: ["*"]
  - apiGroups: ["storage.k8s.io"]
    resources: ["storageclasses"]
    verbs: ["*"]
EOF

# tenants.yaml is GENERATED so the three namespace lists are the single source
# of truth. Re-run when a namespace joins/leaves a list (premises
# namespace-set-unchanged / tier-a-owner-set-unchanged / storage-owner-set-unchanged
# are the detectors). Dry-tested 2026-09-22: 53 documents = 18 SA + 18 RB + 9 + 8 CRB.
cat > $D/app/gen-tenants.sh <<'GEN'
#!/usr/bin/env bash
# Emits tenants.yaml next to this script. Lists measured 2026-09-22 (plan
# flux-reconciler-impersonation, F-7b847e3e). ALL = every namespace hosting a
# Kustomization or HelmRelease. TIER_A = owns ClusterRole/CRD/webhook-class
# objects -> cluster-admin. STORAGE_B = non-platform namespaces owning a
# PersistentVolume or StorageClass -> flux-reconciler-storage. Everything
# else gets namespace-admin only.
set -euo pipefail
cd "$(dirname "$0")"
ALL="ai backup cert-manager databases default download flux-system home-automation kube-system media monitoring my-software-development my-software-production my-software-showcase network office security storage"
TIER_A="ai cert-manager default flux-system kube-system monitoring network security storage"
STORAGE_B="backup databases download home-automation media my-software-development my-software-showcase office"
OUT=tenants.yaml
{
  echo "# GENERATED by gen-tenants.sh -- edit the lists in the script, not this file."
  for ns in $ALL; do cat <<EOF
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: flux-reconciler
  namespace: ${ns}
automountServiceAccountToken: false
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: flux-reconciler
  namespace: ${ns}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: flux-reconciler-namespaced
subjects:
  - kind: ServiceAccount
    name: flux-reconciler
    namespace: ${ns}
EOF
  done
  for ns in $TIER_A; do cat <<EOF
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: flux-reconciler-cluster-admin-${ns}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: ServiceAccount
    name: flux-reconciler
    namespace: ${ns}
EOF
  done
  for ns in $STORAGE_B; do cat <<EOF
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: flux-reconciler-storage-${ns}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: flux-reconciler-storage
subjects:
  - kind: ServiceAccount
    name: flux-reconciler
    namespace: ${ns}
EOF
  done
} > "$OUT"
echo "wrote $OUT: $(grep -c '^---' "$OUT") documents"
GEN
chmod +x $D/app/gen-tenants.sh && $D/app/gen-tenants.sh
# EXPECT: wrote tenants.yaml: 53 documents

# The window-scoped probe: a Kustomization in kube-public, a namespace with NO
# flux-reconciler SA and NO RBAC. Before Stage C it reconciles (cluster-admin);
# after Stage C it MUST fail with forbidden naming kube-public:flux-reconciler.
# That flip is the only unambiguous proof the flag is live AND the identity is
# the per-namespace one (section 4, gate C4). prune: false so Stage D can delete
# the Kustomization without a prune it has no rights to perform.
cat > $D/app/probe-kustomization.yaml <<'EOF'
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: impersonation-probe
  namespace: kube-public
  labels:
    substitution.flux.home.arpa/disabled: "true"   # not built by cluster-apps, but be explicit
spec:
  interval: 1m
  path: ./kubernetes/apps/flux-system/flux-reconciler-rbac/probe
  prune: false
  sourceRef:
    kind: GitRepository
    name: flux-system
    namespace: flux-system
  timeout: 1m
  wait: false
EOF
cat > $D/probe/kustomization.yaml <<'EOF'
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ./configmap.yaml
EOF
cat > $D/probe/configmap.yaml <<'EOF'
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: impersonation-probe
  namespace: kube-public
data:
  purpose: "window-scoped tripwire for flux-reconciler-impersonation; deleted in Stage D"
EOF

# Register the new Kustomization. This file has NO patches: block, so the
# appended line cannot land under the wrong key — but verify anyway
# (feedback_kustomization_append_wrong_key).
mise exec -- yq -i '.resources += ["./flux-reconciler-rbac/ks.yaml"]' kubernetes/apps/flux-system/kustomization.yaml
mise exec -- yq '.resources' kubernetes/apps/flux-system/kustomization.yaml
# EXPECT the three entries: ./flux-guardrails/ks.yaml, ./flux-operator/ks.yaml, ./flux-reconciler-rbac/ks.yaml

# Local render + lint BEFORE committing
mise exec -- kubectl kustomize $D/app | grep -c '^kind:'
# EXPECT: 56  (2 ClusterRole + 18 ServiceAccount + 18 RoleBinding + 17 ClusterRoleBinding + 1 Kustomization)
mise exec -- kubectl kustomize $D/app | grep -c 'namespace: flux-system$'
# EXPECT: 5  (flux-system's SA, its RoleBinding, and the two subjects that name it) — NOT 53.
mise exec -- task kubeconform

printf 'feat(flux): per-namespace flux-reconciler identities + tiered RBAC (stage A of F-7b847e3e)\n\nInert until --default-service-account renders (stage C). Adds ServiceAccount\nflux-reconciler + RoleBinding in the 18 namespaces that host a Kustomization or\nHelmRelease, cluster-admin CRBs for the 9 platform namespaces whose content\nowns ClusterRoles/CRDs/webhooks, PV/StorageClass CRBs for the 8 storage-owning\napp namespaces, and a window-scoped impersonation probe in kube-public.\n\nPlan: runbooks/maintenance/plans/flux-reconciler-impersonation.md\n' > /tmp/msg-a.txt
git commit --only kubernetes/apps/flux-system/kustomization.yaml $D -F /tmp/msg-a.txt
git log -1 --format=%s        # MUST be the subject above (feedback_commit_editmsg_race)
git show --stat HEAD          # MUST list only kustomization.yaml + the 8 new files
git push
```

Then wait for `cluster-apps` (webhook, ~1 min) and the new Kustomization:

```bash
mise exec -- kubectl get kustomization -n flux-system cluster-apps flux-reconciler-rbac
mise exec -- kubectl get kustomization -n kube-public impersonation-probe
```

Run gates **A1–A4** (section 4.1) before Stage B.

### 3.2 Stage B1 — Tier-B canary under an EXPLICIT `serviceAccountName` (namespace `download`)

`download` is the canary because it exercises every Tier-B grant at once
(2 Kustomizations that own a StorageClass and PersistentVolumes, 4
app-template HelmReleases) and nothing outside the household depends on it.
An explicit `spec.serviceAccountName` bumps `metadata.generation`, so both
controllers reconcile it **now** under the new identity, while every other
object in the cluster is still cluster-admin.

```bash
cd /Users/mu/code/cberg-home-nextgen
# Kustomizations — yq is clean on these short files (dry-tested 2026-09-22):
#   +  serviceAccountName: flux-reconciler   (appended under spec:)
for f in kubernetes/apps/download/jdownloader/ks.yaml kubernetes/apps/download/tube-archivist/ks.yaml; do
  mise exec -- yq -i '.spec.serviceAccountName = "flux-reconciler"' "$f"
done
# HelmReleases — NOT yq (it strips the blank lines in these long app-template
# files and produces a 3-hunk cosmetic diff). BSD-sed insert after the ONE
# top-level `spec:` line each file has (grep -c '^spec:$' == 1 in all four):
#   @@ -5,6 +5,7 @@  spec:
#   +  serviceAccountName: flux-reconciler
for f in kubernetes/apps/download/jdownloader/app/helmrelease.yaml \
         kubernetes/apps/download/tube-archivist/app/helmrelease.yaml \
         kubernetes/apps/download/tube-archivist/app/elasticsearch-helmrelease.yaml \
         kubernetes/apps/download/tube-archivist/app/redis-helmrelease.yaml; do
  sed -i '' '/^spec:$/a\
  serviceAccountName: flux-reconciler
' "$f"
done
git diff --stat -- kubernetes/apps/download      # EXPECT: 6 files, +1 line each
mise exec -- task kubeconform

printf 'chore(download): reconcile as flux-reconciler explicitly (stage B1 canary, F-7b847e3e)\n\nTier-B canary for runbooks/maintenance/plans/flux-reconciler-impersonation.md:\nexplicit spec.serviceAccountName on the 2 Kustomizations and 4 HelmReleases in\ndownload so they reconcile under the namespace-scoped identity BEFORE the\ncluster-wide default flips. Reverted to the default in stage D.\n' > /tmp/msg-b1.txt
git commit --only kubernetes/apps/download -F /tmp/msg-b1.txt
git log -1 --format=%s && git show --stat HEAD
git push
```

Run gates **B1-1 … B1-NEG** (section 4.2).

### 3.3 Stage B2 — the platform identity under an EXPLICIT `serviceAccountName` (`cluster-meta`, `cluster-apps`)

This is the stage that de-risks Stage C: `cluster-apps` re-applies all 18
Namespaces, 54 per-namespace ConfigMaps/Secrets and 134 child Kustomizations
as `flux-system:flux-reconciler`. If the cluster-admin CRB for flux-system is
wrong, it fails HERE — while the root `flux-system` Kustomization and every
app Kustomization are still cluster-admin and the revert reconciles normally.

```bash
cd /Users/mu/code/cberg-home-nextgen
# Multi-document file; yq applies the expression per document (dry-tested: two
# +1-line hunks, comments and `---` preserved):
mise exec -- yq -i 'select(.kind == "Kustomization").spec.serviceAccountName = "flux-reconciler"' kubernetes/flux/cluster/ks.yaml
git diff -- kubernetes/flux/cluster/ks.yaml       # EXPECT exactly two added lines, one per document
mise exec -- task kubeconform

printf 'chore(flux): cluster-meta + cluster-apps reconcile as flux-system/flux-reconciler (stage B2, F-7b847e3e)\n\nPins the platform identity explicitly before the cluster-wide default flips\n(stage C). KEPT after the rollout on purpose: the two Kustomizations that apply\nevery other Kustomization state who they run as, independent of the controller\nflag. Plan: runbooks/maintenance/plans/flux-reconciler-impersonation.md\n' > /tmp/msg-b2.txt
git commit --only kubernetes/flux/cluster/ks.yaml -F /tmp/msg-b2.txt
git log -1 --format=%s && git show --stat HEAD
git push
```

Run gates **B2-1 … B2-3** (section 4.3). **These explicit names are kept**
(section 3.5 does not remove them).

### 3.4 Stage C — flip the default for both controllers

One block appended to `instance:` in
`kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml`
(dry-tested 2026-09-22 with the yq below; the diff is exactly this):

```diff
@@ -25,3 +25,12 @@
     pullSecret: flux-system-git-auth
+  kustomize:
+    patches:
+      - target:
+          kind: Deployment
+          name: (kustomize-controller|helm-controller)
+        patch: |
+          - op: add
+            path: /spec/template/spec/containers/0/args/-
+            value: --default-service-account=flux-reconciler
```

The target-name regex is the same shape the operator's own multitenant profile
uses. Propagation path — know it, so you know what to watch: push → `cluster-apps`
→ Kustomization `flux-instance` (configMapGenerator re-hashes
`flux-instance-helm-values-*`, so the HelmRelease's `valuesFrom` name changes
and its generation bumps) → helm-controller upgrades release `flux-instance`
(chart renders only the FluxInstance CR, so Helm's wait returns immediately;
`upgrade.remediation: rollback` would undo a CR the CRD schema rejects — a
safe failure) → flux-operator sees the FluxInstance spec change → rebuilds
with the patch appended after all profiles → applies the two Deployments →
`wait: true` blocks on rollout (reconcileTimeout default 5m) → both pods
restart with the flag → every Kustomization/HelmRelease re-reconciles under
impersonation within minutes.

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- yq -i '.instance.kustomize.patches = [{"target": {"kind": "Deployment", "name": "(kustomize-controller|helm-controller)"}, "patch": "- op: add\n  path: /spec/template/spec/containers/0/args/-\n  value: --default-service-account=flux-reconciler\n"}]' \
  kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml
git diff -- kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml   # MUST equal the diff above
mise exec -- yq '.instance.kustomize.patches[0].target.name' kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml
# EXPECT: (kustomize-controller|helm-controller)
mise exec -- task kubeconform
T_C=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "T_C=$T_C"

printf 'feat(flux): render --default-service-account=flux-reconciler on kustomize/helm-controller (stage C, F-7b847e3e)\n\nFluxInstance spec.kustomize.patches, NOT cluster.tenantDefaultServiceAccount:\nthat field only renders inside the multitenant profile, which also adds\n--no-cross-namespace-refs and is rejected for this monorepo\n(docs/sops/flux-image-automation-push-auth.md). Every Kustomization/HelmRelease\nwithout spec.serviceAccountName now applies as <its namespace>/flux-reconciler\n(RBAC from stage A). Plan: runbooks/maintenance/plans/flux-reconciler-impersonation.md\n' > /tmp/msg-c.txt
git commit --only kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml -F /tmp/msg-c.txt
git log -1 --format=%s && git show --stat HEAD
git push

# Watch the propagation in order (each line should turn green within ~1 min of the previous)
mise exec -- kubectl get kustomization -n flux-system cluster-apps flux-instance
mise exec -- kubectl get helmrelease   -n flux-system flux-instance
mise exec -- kubectl get fluxinstance  -n flux-system flux
mise exec -- kubectl get pods -n flux-system -o custom-columns='NAME:.metadata.name,STARTED:.status.startTime' | grep -E 'kustomize-controller|helm-controller'
```

Run gates **C1 … C6** (section 4.4). C4 is the contents assertion for the
whole plan; do not proceed to Stage D on C1–C3 alone.

### 3.5 Stage D — return the canary to the default path, remove the probe, close out

The download objects go back to relying on the flag (so the canary namespace
is proven on the DEFAULT path too, and the repo stays uniform: only the two
platform Kustomizations carry an explicit name). The probe is deleted.

```bash
cd /Users/mu/code/cberg-home-nextgen
for f in kubernetes/apps/download/jdownloader/ks.yaml kubernetes/apps/download/tube-archivist/ks.yaml; do
  mise exec -- yq -i 'del(.spec.serviceAccountName)' "$f"
done
for f in kubernetes/apps/download/jdownloader/app/helmrelease.yaml \
         kubernetes/apps/download/tube-archivist/app/helmrelease.yaml \
         kubernetes/apps/download/tube-archivist/app/elasticsearch-helmrelease.yaml \
         kubernetes/apps/download/tube-archivist/app/redis-helmrelease.yaml; do
  sed -i '' '/^  serviceAccountName: flux-reconciler$/d' "$f"
done
git diff --stat -- kubernetes/apps/download       # EXPECT: 6 files, -1 line each (exact inverse of B1)

D=kubernetes/apps/flux-system/flux-reconciler-rbac
git rm -q $D/app/probe-kustomization.yaml $D/probe/kustomization.yaml $D/probe/configmap.yaml
mise exec -- yq -i 'del(.resources[] | select(. == "./probe-kustomization.yaml"))' $D/app/kustomization.yaml
mise exec -- kubectl kustomize $D/app | grep -c '^kind:'     # EXPECT: 55
mise exec -- task kubeconform

printf 'chore(flux): download back on the default reconciler identity; drop the impersonation probe (stage D, F-7b847e3e)\n\nStage B1 canary reverted now that stage C renders the default; the probe in\nkube-public served its purpose (it flipped to forbidden under the per-namespace\nidentity, gate C4). Plan: runbooks/maintenance/plans/flux-reconciler-impersonation.md\n' > /tmp/msg-d.txt
git commit --only kubernetes/apps/download $D -F /tmp/msg-d.txt
git log -1 --format=%s && git show --stat HEAD
git push
```

Run gates **D1 … D3** (section 4.5). Then the one hand cleanup the probe's
`prune: false` leaves behind (the probe Kustomization could not have deleted
it — that inability is the property we proved):

```bash
mise exec -- kubectl delete configmap -n kube-public impersonation-probe
```

Close out: delete the Alertmanager silence early (`curl -s -X DELETE
localhost:9093/api/v2/silences/<id>`), `runbooks/update-marker.sh clear
flux-system`, run `health-check-agent` and `security-agent`, and record the
follow-ups from section 6.3 on the finding
(`policy-cli.py finding detail F-7b847e3e --plan flux-reconciler-impersonation
--detail-file …`) before closing it with `finding close F-7b847e3e --commit <stage-C sha>`.

## 4. Verification

Every gate below states what the failure it guards against PRINTS. The Flux
controllers are not scraped, so the instruments are flux-operator's
`flux_resource_info` (Prometheus), the controllers' JSON logs, the objects'
`.status`, and SubjectAccessReview (`kubectl auth can-i --as`).

```
CONTROL: metric flux_resource_info — count by (kind) of {kind=~"Kustomization|HelmRelease", ready="False", suspended="False", name!="impersonation-probe"} must read 0 for 10 consecutive minutes after each stage, AND count of {kind="Kustomization"} must still read the pre-check floor (140 on 2026-09-22; 141 while the probe exists) and {kind="HelmRelease"} 125 — a disappearing series is a failed scrape, not a healthy cluster.
CONTROL: metric flux_instance_info — {name="flux", ready="True"} == 1 after Stage C; ready="False" with reason ReconciliationFailed is the operator's 5-minute rollout wait expiring.
CONTROL: metric controller_runtime_reconcile_errors_total — {namespace="flux-system", controller="fluxinstance"} increase over the window == 0 (the operator itself must not be erroring on the patched build).
CONTROL: alertname FluxResourceNotReady — not firing at close-out for anything but the (silenced, then deleted) probe.
CONTROL: alertname FluxSourceStalled — not firing at any point (source-controller is untouched; if it fires, something else is wrong — stop).
CONTROL: alertname FluxMetricsAbsent — not firing (proves the instrument the first CONTROL reads is alive).
```

Helper used by several gates — distinct objects reconciled and forbidden
lines, from the CURRENT pod's log (a `kubectl logs deploy/…` with no `--since`
reads from the pod's start, which after Stage C is exactly "since the flag"):

```bash
# usage: fluxlog <kustomize-controller|helm-controller> [since e.g. 20m]
fluxlog() { mise exec -- kubectl logs -n flux-system deploy/$1 ${2:+--since=$2} 2>/dev/null | .venv/bin/python3 -c "
import sys, json
kind = 'Kustomization' if '$1'.startswith('kustomize') else 'HelmRelease'
seen, forb = set(), []
for line in sys.stdin:
    try: j = json.loads(line)
    except Exception: continue
    o = j.get(kind) or {}
    if isinstance(o, dict) and o.get('name'): seen.add(o['namespace'] + '/' + o['name'])
    if 'forbidden' in line.lower() or 'unauthorized' in line.lower():
        forb.append((o.get('namespace'), o.get('name'), j.get('msg', '')[:100], (j.get('error') or '')[:160]))
print(f'distinct {kind}s logged: {len(seen)}')
print(f'forbidden/unauthorized lines: {len(forb)}')
for f in forb: print('  FORBIDDEN', f)
"; }
```

### 4.1 Gates after Stage A

```bash
# A1 — the RBAC Kustomization applied everything (a partial apply reads Ready=False, message names the object)
mise exec -- kubectl get kustomization -n flux-system flux-reconciler-rbac -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.conditions[?(@.type=="Ready")].message}{"\n"}'
# PASS: True Applied revision: main@sha1:<stage-A sha>     FAIL: False <kind> "<name>" ... 
mise exec -- kubectl get serviceaccounts -A --field-selector metadata.name=flux-reconciler --no-headers | wc -l     # PASS: 18
mise exec -- kubectl get clusterrolebindings -o name | grep -c '^clusterrolebinding.rbac.authorization.k8s.io/flux-reconciler-'   # PASS: 17

# A2 — the can-i matrix: every tier does what its row says and NOT what the next row says.
#      A wrong roleRef, a subject in the wrong namespace, or a missing CRB prints the
#      opposite word in that cell. Expected per column: ns-deploy=yes for all 18;
#      clusterroles=yes for the 9 Tier-A only; persistentvolumes=yes for Tier-A + the 8
#      storage namespaces, NO for my-software-production; cross-ns-secret(office)=no for
#      every non-Tier-A namespace.
for ns in ai backup cert-manager databases default download flux-system home-automation kube-system media monitoring my-software-development my-software-production my-software-showcase network office security storage; do
  SA="system:serviceaccount:$ns:flux-reconciler"
  printf '%-26s ns-deploy=%-4s clusterroles=%-4s persistentvolumes=%-4s cross-ns-secret(office)=%s\n' "$ns" \
    "$(mise exec -- kubectl auth can-i create deployments -n $ns --as=$SA)" \
    "$(mise exec -- kubectl auth can-i create clusterroles --as=$SA)" \
    "$(mise exec -- kubectl auth can-i create persistentvolumes --as=$SA)" \
    "$(mise exec -- kubectl auth can-i get secrets -n office --as=$SA)"
done
# NEGATIVE CONTROL in the same run (proves `no` is reachable, not a default):
mise exec -- kubectl auth can-i create deployments -n kube-public --as=system:serviceaccount:kube-public:flux-reconciler     # MUST print: no

# A3 — CONTENTS ASSERTION: the grants cover the LIVE inventory, not the plan's table.
#      For every Kustomization, every cluster-scoped kind in its status.inventory must be
#      patchable by that namespace's flux-reconciler. A kind that appeared after the
#      survey (or a mis-tiered namespace) prints a DENIED line; the check fails on any.
mise exec -- kubectl get kustomizations.kustomize.toolkit.fluxcd.io -A -o json > /tmp/ks.json
mise exec -- kubectl api-resources --namespaced=false --no-headers > /tmp/api.txt
.venv/bin/python3 - <<'EOF'
import json, subprocess, collections
ks = json.load(open('/tmp/ks.json'))['items']
# Kind -> plural.group from api-resources (cluster-scoped only). Columns are
# NAME [SHORTNAMES] APIVERSION NAMESPACED KIND; SHORTNAMES is often EMPTY, so
# never index by position — anchor on the NAMESPACED column, always "false" here.
plural = {}
for line in open('/tmp/api.txt'):
    parts = line.split()
    if 'false' not in parts: continue
    i = parts.index('false')
    name, apiver, kind = parts[0], parts[i - 1], parts[i + 1]
    group = apiver.split('/')[0] if '/' in apiver else ''
    plural[(group, kind)] = f'{name}.{group}' if group else name
need = collections.defaultdict(set)
for k in ks:
    ns = k['metadata']['namespace']
    for e in (k.get('status', {}).get('inventory', {}).get('entries') or []):
        p = e['id'].split('_')
        if p[0] == '':                      # cluster-scoped entry: _<name>_<group>_<kind>
            need[ns].add((p[-2], p[-1]))
denied = 0; checked = 0
for ns in sorted(need):
    for group, kind in sorted(need[ns]):
        res = plural.get((group, kind))
        if not res: print('UNMAPPED', ns, group, kind); denied += 1; continue
        r = subprocess.run(['mise','exec','--','kubectl','auth','can-i','patch',res,f'--as=system:serviceaccount:{ns}:flux-reconciler'], capture_output=True, text=True).stdout.strip()
        checked += 1
        if r != 'yes': print('DENIED', ns, res); denied += 1
print(f'checked {checked} (namespace, cluster-scoped kind) pairs; denied {denied}')
print('PASS' if denied == 0 and checked > 0 else 'FAIL')
EOF
# PASS line required. Dry-run of the mapping on 2026-09-22: 36 (namespace, kind) pairs across 16 namespaces,
# 0 unmapped, 14 distinct cluster-scoped resources. A `checked 0` is a FAIL (the inventory could not be read).

# A4 — probe baseline: it reconciles NOW (as cluster-admin). If it does not, the probe is
#      broken and C4 cannot mean anything.
mise exec -- kubectl get kustomization -n kube-public impersonation-probe -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # PASS: True
mise exec -- kubectl get configmap -n kube-public impersonation-probe -o jsonpath='{.data.purpose}{"\n"}'                                          # PASS: the purpose string
```

### 4.2 Gates after Stage B1 (download, explicit identity)

```bash
# B1-1 — both Kustomizations reconciled THE NEW GENERATION under the new SA (an old-generation
#        Ready=True is the stale success feedback_rollout_status_old_generation warns about)
mise exec -- kubectl get kustomization -n download -o custom-columns='NAME:.metadata.name,SA:.spec.serviceAccountName,GEN:.metadata.generation,OBS:.status.observedGeneration,READY:.status.conditions[?(@.type=="Ready")].status,MSG:.status.conditions[?(@.type=="Ready")].message'
# PASS: SA=flux-reconciler, GEN==OBS, READY=True, MSG "Applied revision: main@sha1:<B1 sha>" on both
# FAIL: READY=False with MSG like: persistentvolumes "jdownloader-config" is forbidden: User "system:serviceaccount:download:flux-reconciler" cannot patch resource "persistentvolumes" ...

# B1-2 — the 4 HelmReleases likewise (helm storage + release inspection ran as the SA)
mise exec -- kubectl get helmrelease -n download -o custom-columns='NAME:.metadata.name,SA:.spec.serviceAccountName,GEN:.metadata.generation,OBS:.status.observedGeneration,READY:.status.conditions[?(@.type=="Ready")].status,MSG:.status.conditions[?(@.type=="Ready")].message'
# PASS: 4 rows, SA=flux-reconciler, GEN==OBS, READY=True
# FAIL shape: READY=False, MSG: ... secrets is forbidden: User "system:serviceaccount:download:flux-reconciler" cannot list resource "secrets" in API group "" in the namespace "download"

# B1-3 — the controllers' own view since T0: the download objects were reconciled and NOTHING was forbidden
fluxlog kustomize-controller 15m | grep -E 'distinct|forbidden|FORBIDDEN'
fluxlog helm-controller 15m      | grep -E 'distinct|forbidden|FORBIDDEN'
# PASS: forbidden/unauthorized lines: 0 on both. Any FORBIDDEN line = stop, revert B1 (section 5.3).
mise exec -- kubectl logs -n flux-system deploy/kustomize-controller --since=15m | grep -c 'server-side apply completed.*"namespace":"download"'
# PASS: >= 2 (one per Kustomization). 0 means the generation bump did not reconcile — do not proceed.

# B1-NEG — scope is REAL (same SA, different namespace / cluster scope):
mise exec -- kubectl auth can-i create clusterroles --as=system:serviceaccount:download:flux-reconciler     # MUST print: no
mise exec -- kubectl auth can-i get secrets -n office --as=system:serviceaccount:download:flux-reconciler     # MUST print: no
mise exec -- kubectl auth can-i create storageclasses --as=system:serviceaccount:download:flux-reconciler     # MUST print: yes (storage tier)
mise exec -- kubectl auth can-i create storageclasses --as=system:serviceaccount:my-software-production:flux-reconciler   # MUST print: no
```

### 4.3 Gates after Stage B2 (flux-system, explicit identity)

```bash
# B2-1 — cluster-meta and cluster-apps reconciled the new generation as flux-system/flux-reconciler
mise exec -- kubectl get kustomization -n flux-system cluster-meta cluster-apps -o custom-columns='NAME:.metadata.name,SA:.spec.serviceAccountName,GEN:.metadata.generation,OBS:.status.observedGeneration,READY:.status.conditions[?(@.type=="Ready")].status,MSG:.status.conditions[?(@.type=="Ready")].message'
# PASS: both SA=flux-reconciler, GEN==OBS, READY=True. FAIL: cluster-apps READY=False "... is forbidden: User "system:serviceaccount:flux-system:flux-reconciler" ..." — the cluster-admin CRB for flux-system is wrong; section 5.3, NOT Stage C.

# B2-2 — it actually re-applied its 200+ objects (Namespaces, per-ns secrets, child Kustomizations)
mise exec -- kubectl logs -n flux-system deploy/kustomize-controller --since=10m | grep -c 'server-side apply completed.*"Kustomization":{"name":"cluster-apps","namespace":"flux-system"}'
# PASS: >= 1
fluxlog kustomize-controller 10m | grep -E 'forbidden|FORBIDDEN'      # PASS: forbidden/unauthorized lines: 0

# B2-3 — nothing downstream regressed (the children were re-applied by a different identity)
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'  # PASS: header only
```

### 4.4 Gates after Stage C (the flip)

```bash
# C1 — the flag is on BOTH controllers and BOTH pods restarted after T_C
mise exec -- kubectl get deploy -n flux-system kustomize-controller helm-controller -o jsonpath='{range .items[*]}{.metadata.name}: {.spec.template.spec.containers[0].args}{"\n"}{end}' | grep -c 'default-service-account=flux-reconciler'
# PASS: 2.   FAIL: 0 (patch not rendered — check `kubectl get fluxinstance -n flux-system flux -o jsonpath='{.status.conditions}'` for BuildFailed) or 1 (regex matched one name).
mise exec -- kubectl get pods -n flux-system -o custom-columns='NAME:.metadata.name,STARTED:.status.startTime' | grep -E 'kustomize-controller|helm-controller'
# PASS: both STARTED > T_C (from section 3.4).

# C2 — the operator is happy with the patched build
mise exec -- kubectl get fluxinstance -n flux-system flux -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.conditions[?(@.type=="Ready")].reason} {.status.conditions[?(@.type=="Ready")].message}{"\n"}'
# PASS: True ReconciliationSucceeded Reconciliation finished in ...   FAIL: False ReconciliationFailed <timeout / not-ready deployments>
mise exec -- kubectl get helmrelease -n flux-system flux-instance -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion} {.status.history[0].status}{"\n"}'
# PASS: True 0.57.0 deployed (a "superseded"/rolled-back history[0] means the CR was rejected and Helm remediated — the flag is NOT on; stop).

# C3 — EVERY object re-reconciled under impersonation and none was forbidden.
#      No --since: the current pods started at the flip, so their whole log IS "since the flag".
#      Wait until both distinct counts reach the floor (typically < 5 min; hard stop 10 min).
fluxlog kustomize-controller       # PASS: distinct Kustomizations logged: >= 141 (140 + probe), forbidden lines: <= the probe's own (namespace kube-public) and NOTHING else
fluxlog helm-controller            # PASS: distinct HelmReleases logged: 125, forbidden/unauthorized lines: 0
# FAIL shape (kustomize): FORBIDDEN ('office', 'nextcloud', 'Reconciliation failed ...', 'storageclasses.storage.k8s.io "cifs-nextcloud-data" is forbidden: User "system:serviceaccount:office:flux-reconciler" ...')
# FAIL shape (helm):      FORBIDDEN ('media', 'plex', 'Failed to determine release state', 'secrets is forbidden: User "system:serviceaccount:media:flux-reconciler" cannot list ...')

# C4 — CONTENTS ASSERTION: the identity is REAL. The probe that reconciled in A4 must now FAIL,
#      and the failure must name the per-namespace account. This is the one gate that
#      distinguishes "flag rendered and honoured" from "flag rendered and ignored".
mise exec -- kubectl get kustomization -n kube-public impersonation-probe -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"|"}{.status.conditions[?(@.type=="Ready")].message}{"\n"}'
# PASS: False|... configmaps "impersonation-probe" is forbidden: User "system:serviceaccount:kube-public:flux-reconciler" cannot patch resource "configmaps" ...
#       (the verb may read "patch" or "create"; the User string is the assertion)
# FAIL: True|Applied revision ...   -> the flag is not in effect for Kustomizations. Stop, section 5.1.
# The same assertion for helm-controller is B1-2/C3: a HelmRelease reconciled with no
# `secrets ... forbidden` under an SA that only has the namespaced grant PROVES the
# grant was consulted (cluster-admin would also pass, which is why the probe exists
# for the kustomize side; helm-controller consumes the identical flag from the same
# patch, gate C1 proves it is rendered there too).

# C5 — the instrument agrees, sustained (CONTROL lines above), floor included
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for i in 1 2 3; do
  curl -s 'http://localhost:19090/api/v1/query' --data-urlencode 'query=count by (kind) (flux_resource_info{kind=~"Kustomization|HelmRelease", ready="False", suspended="False", name!="impersonation-probe"}) or vector(0)' | grep -o '"value":\[[0-9.]*,"[0-9]*"'
  curl -s 'http://localhost:19090/api/v1/query' --data-urlencode 'query=count by (kind) (flux_resource_info{kind=~"Kustomization|HelmRelease", suspended="False"})' | grep -o '"kind":"[A-Za-z]*"},"value":\[[0-9.]*,"[0-9]*"'
  curl -s 'http://localhost:19090/api/v1/query' --data-urlencode 'query=flux_instance_info{name="flux"}' | grep -o '"ready":"[A-Za-z]*"'
  curl -s 'http://localhost:19090/api/v1/query' --data-urlencode 'query=ALERTS{alertname=~"FluxSourceStalled|FluxMetricsAbsent|FluxResourceNotReady",alertstate="firing",name!="impersonation-probe"}' | grep -c alertname
  sleep 300
done
kill $PF 2>/dev/null
# PASS on all three samples (10 min): not-ready count 0 (or the `or vector(0)` zero), totals 141/125, ready:"True", alert count 0.
# FAIL: a non-zero not-ready count, OR a total BELOW the floor (series vanished = scrape broke = shape check would have said "0 failures").

# C6 — negative control on the instrument, same session: a metric that cannot exist must read empty
curl -s 'http://localhost:19090/api/v1/query' --data-urlencode 'query=count(flux_resource_info_nonexistent_9f3a)' | grep -c '"result":\[\]'   # MUST print: 1
```

### 4.5 Gates after Stage D

```bash
# D1 — download reconciled its NEW generation on the DEFAULT path (no explicit SA), still clean
mise exec -- kubectl get kustomization,helmrelease -n download -o custom-columns='KIND:.kind,NAME:.metadata.name,SA:.spec.serviceAccountName,GEN:.metadata.generation,OBS:.status.observedGeneration,READY:.status.conditions[?(@.type=="Ready")].status'
# PASS: 6 rows, SA=<none>, GEN==OBS, READY=True
fluxlog kustomize-controller 10m | grep -E 'forbidden|FORBIDDEN'; fluxlog helm-controller 10m | grep -E 'forbidden|FORBIDDEN'   # PASS: 0 and 0

# D2 — the probe is gone, the RBAC Kustomization pruned it, nothing else pruned
mise exec -- kubectl get kustomization -n kube-public impersonation-probe 2>&1 | grep -c NotFound     # PASS: 1
mise exec -- kubectl get kustomization -n flux-system flux-reconciler-rbac -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # PASS: True
mise exec -- kubectl get serviceaccounts -A --field-selector metadata.name=flux-reconciler --no-headers | wc -l     # PASS: still 18

# D3 — whole-cluster floor at close-out
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'; mise exec -- flux get helmreleases -A | awk 'NR==1 || $5 != "True"'   # PASS: headers only
```

Then `health-check-agent` and `security-agent`.

## 5. Rollback

Stages are independent commits, so rollback is per stage — **but order
matters**: never revert Stage A while Stage C is live (that deletes the
flux-system identity's cluster-admin binding while every reconcile still
impersonates it → total wedge). Revert C, confirm the flag is gone, then B, then A.

### 5.1 Stage C — the flag (preferred path, while Flux still reconciles)

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <stage-C sha>        # restores helm-values.yaml: kustomize.patches gone
git log -1 --format=%s && git show --stat HEAD && git push
# The revert propagates the same path as section 3.4 (cluster-apps -> ks flux-instance -> hr flux-instance -> operator -> rollout).
mise exec -- kubectl get deploy -n flux-system kustomize-controller helm-controller -o jsonpath='{range .items[*]}{.metadata.name}: {.spec.template.spec.containers[0].args}{"\n"}{end}' | grep -c 'default-service-account'
# CONFIRMED BACK when: 0, both pods restarted again, `flux get ks -A`/`hr -A` all True,
# and the probe (if still present) is Ready=True again — the exact inverse of C4.
```

### 5.2 Stage C — when Flux CANNOT reconcile the revert (flux-system identity broken)

Symptom: `cluster-apps` / `flux-system` root Kustomization Ready=False with a
`forbidden ... system:serviceaccount:flux-system:flux-reconciler` message, so
the revert commit never applies. **flux-operator is unaffected** — it runs as
its own ServiceAccount (`flux-operator`, cluster-admin, AR-011) and does not
impersonate — so it can be told directly to drop the patch:

```bash
mise exec -- kubectl -n flux-system patch fluxinstance flux --type=json -p '[{"op":"replace","path":"/spec/kustomize/patches","value":[]}]'
# The operator's watch fires within seconds: it rebuilds without the arg, re-applies both
# Deployments, the pods restart as plain cluster-admin. Confirm exactly as 5.1 (grep -c == 0).
# THEN land the git revert (5.1) so git and cluster agree; helm-controller's next upgrade of
# flux-instance (generation bump from the revert) re-applies the CR with patches: [] — same state.
```

This is a direct cluster mutation and is documented here precisely because it
is the one moment GitOps cannot self-heal; it is the break-glass, not the path.
The `docs/sops/flux-upgrade.md` §Rollback "suspend the HRs, helm rollback"
route also works but is slower and touches more.

### 5.3 Stage B2 / B1 — explicit identities

```bash
git revert --no-edit <stage-B2 sha>      # cluster-meta/cluster-apps back to the controller identity
git revert --no-edit <stage-B1 sha>      # download back to the controller identity
git push
```

A B1 failure is contained to `download` (6 objects Ready=False, apps keep
running on their last-applied state — Flux failing to apply does not undeploy
anything). A B2 failure shows as `cluster-apps` Ready=False; its revert is
applied by the root `flux-system` Kustomization, which at that point still
runs as the controller SA (Stage C not yet done), so it always lands.

### 5.4 Stage A — the identities

```bash
git revert --no-edit <stage-A sha> && git push
# cluster-apps prunes kustomization/flux-reconciler-rbac; its finalizer prunes the 55 objects.
mise exec -- kubectl get serviceaccounts -A --field-selector metadata.name=flux-reconciler --no-headers | wc -l   # CONFIRMED when: 0
mise exec -- kubectl get clusterrolebindings -o name | grep -c flux-reconciler-                                    # 0
```

Only after 5.1/5.2 has confirmed `grep -c == 0` on the controller args.

### 5.5 Rollback-class note

`git-revert` is honest for every stage: nothing forward-only happens — no data,
no schema, no PV is touched, and Flux failing to apply never removes a
workload. The single non-git step is 5.2, and it exists only for the state in
which git cannot reach the cluster.

## 6. Interference notes

### 6.1 For the window agent

- **`exclusive: true`, attended, no reboot.** Sat-attended at full budget
  (70 of 70 usable minutes) or a Sunday with no reboot plan. Do NOT put it in
  `sun-attended:2026-09-27` (talos-1.14.1) and do not let it displace a reboot
  plan from a Sunday — it is not reboot work.
- **Step 0 (safe updates) runs BEFORE this plan, as always, and NOTHING may be
  applied through Flux after Stage C except this plan's own Stage D.** A safe
  update landing between C and D would be the first unattended impersonated
  Helm upgrade in the household with no one reading the gate.
- **The first nightly window after execution is the real soak.** Its Step 0
  batch is the first set of Helm upgrades run under the per-namespace
  identities. The window agent's health gate + auto-revert covers a failing
  HelmRelease, but a `forbidden` surfaces as Ready=False, not as a pod
  regression — the executor should ask the operator to read that nightly's
  report, or the sweep's `FluxResourceNotReady` will be the first signal.
- **`conflicts_with` names the reason each other plan is excluded:**
  `flux-oci-chart-sources` rewrites the sources every reconcile reads;
  `helm-drift-detection` changes what helm-controller does on every
  reconcile (and drift correction under impersonation is untested here);
  `kube-prometheus-stack-91.4.1` is the instrument section 4 reads;
  `talos-1.14.1` restarts the controllers mid-proof and would make the
  "since pod start" log gate lie.
- **Shared worktree.** On 2026-09-22 `kubernetes/flux/components/common/namespace.yaml`
  carried someone else's uncommitted PSA edit (F-b0ec926b / F-481fadb8).
  Pre-check 2.2 refuses to start while any file this plan's `cluster-apps`
  re-apply would pick up is dirty. `git commit --only` is mandatory on every
  stage — a foreign hunk riding into Stage C would be applied by the very
  identity change being tested.

### 6.2 Things that are NOT touched and must stay that way

- `spec.cluster.multitenant` stays `false` — see 1.2; premise `multitenant-off`.
- `clusterrolebinding/cluster-reconciler-flux-system` stays — the controllers
  need cluster-admin to impersonate. The finding's exposure is closed by
  bounding what they impersonate, not by removing their power. AR-011 (the
  flux-operator's own cluster-admin binding) is untouched and still does not
  cover this binding; the finding record should say the binding is now
  bounded rather than accepted.
- `source-controller`, `notification-controller`, image-* controllers: no
  impersonation exists for them; nothing changes.
- The root `flux-system` Kustomization is operator-generated and cannot carry
  an explicit `serviceAccountName` from git; it takes the default, i.e.
  `flux-system:flux-reconciler` (cluster-admin) — same identity as
  `cluster-apps`. Proven by C3/C5 (it reconciles) rather than by an explicit
  stage.

### 6.3 Follow-ups this plan deliberately leaves (record on F-7b847e3e at close-out)

1. **New-namespace trap (SOP correction, must land with the plan):** after
   Stage C, a namespace that hosts a Kustomization/HelmRelease but has no
   `flux-reconciler` SA + RoleBinding fails every reconcile with
   `forbidden`. `docs/sops/new-deployment-blueprint.md` needs a step "add the
   namespace to `gen-tenants.sh` ALL (and TIER_A / STORAGE_B if it owns
   cluster-scoped objects), regenerate, commit BEFORE the app", and
   `runbooks/health-check.sh` should assert `namespaces hosting ks/hr ⊆
   namespaces with serviceaccount/flux-reconciler` every sweep. Neither edit
   is a window action; both are owed the BEFORE the window (reviewer 2026-09-23: any namespace outside the tenant generator stops reconciling at Stage C).
2. **Demote `default` and `ai` from Tier A** by moving homepage's and
   ai-sre/mcpo's ClusterRole/ClusterRoleBinding under a flux-system-owned
   Kustomization (as `flux-reconciler-rbac` already is). Both are
   cluster-admin today only because one app each renders cluster RBAC.
3. **Storage residual:** Tier-B's cluster-wide `persistentvolumes` /
   `storageclasses` grant. Moving the `longhorn-static` PVs and the CIFS
   StorageClasses under a flux-system-owned path would let the storage CRBs
   go — but that is 35 PVs + 19 StorageClasses across 15 Kustomizations and
   changes the PV ownership labels; it is its own plan.
4. **Permanent tripwire:** re-create the kube-public probe permanently with a
   dedicated alert (`flux_resource_info{name="impersonation-probe", ready="True"}`
   → "impersonation is OFF") and exclude it from `FluxResourceNotReady`. Rejected
   for this window because a permanently not-Ready Kustomization is sweep
   noise until that exclusion exists; it is a monitoring change, not a Flux one.
5. **Finding text correction:** F-7b847e3e's `action` prescribes
   `tenantDefaultServiceAccount`, which is inert here (1.2). Amend the record
   so the next reader does not plan the inert change — or, worse, the
   multitenant one.
