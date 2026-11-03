---
plan_id: flux-fleet-0.62.0
component: flux-fleet                 # chart-family group: flux-operator + flux-instance (ns flux-system)
pr: 257                               # Renovate "update flux operator group ( 0.61.0 -> 0.62.0 )": both
                                      # helmrelease.yaml + kubernetes/bootstrap/apps/helmfile.yaml; CI green
                                      # (Flate Render Gate, Flux Local Diff x2), MERGEABLE at authoring.
                                      # Coverage recorded no PR; the PR exists (gh pr view 257).
kind: chart
current: "flux-operator chart 0.61.0 (operator image v0.61.0) + flux-instance chart 0.61.0; FluxInstance distribution v2.9.6 (unchanged by this plan)"
target: "flux-operator chart 0.62.0 (operator image v0.62.0) + flux-instance chart 0.62.0; distribution stays v2.9.6"
update_type: minor                    # 0.x line: 0.61 -> 0.62 is a "minor" at major 0
risk: medium                          # The rendered diff is small (section 1.3) and the six controllers
                                      # are measured NOT to re-render (section 1.4). Medium comes from the
                                      # operator BINARY delta, which is large this time (k8s libs 0.36 ->
                                      # 0.37, fluxcd/pkg/ssa 0.77 -> 0.83, notifier and RSIP controller
                                      # rewrites, SPIFFE plumbing), and from blast radius: this is the
                                      # reconcile engine, and the operator pod is the only exporter of the
                                      # flux_* series every Flux alert reads.
est_duration_min: 35                  # pre-checks 8 + merge/pull 3 + propagate/roll 7 + verification 13
                                      # (includes a 10-min soak) + docs follow-up 4.
needs_reboot: false
touches:
  namespaces: [flux-system]
  resources:
    - helmrelease/flux-operator (flux-system)          # chart 0.61.0 -> 0.62.0; helm rev 4 -> 5
    - helmrelease/flux-instance (flux-system)          # chart 0.61.0 -> 0.62.0; helm rev 8 -> 9
    - deployment/flux-operator (flux-system)           # ROLLS: image v0.61.0 -> v0.62.0 (1 replica)
    - crd/fluxinstances.fluxcd.controlplane.io         # schema: +spec.spiffe, +cluster.objectIdentityRBAC,
                                                       # +cluster.multitenantObjectIdentity (default false),
                                                       # 2 new + 1 rewritten CEL rules (section 1.3)
    - crd/resourcesetinputproviders.fluxcd.controlplane.io  # 13-line schema delta; 0 objects exist
    - "crd/fluxreports + crd/resourcesets (labels only)"
    - fluxinstance/flux (flux-system)                  # labels only; spec byte-identical
    - "clusterrole/{flux-operator-edit,flux-operator-view,flux-web-user,flux-web-admin}, clusterrolebinding/flux-operator, service/flux-operator, serviceaccount/flux-operator, networkpolicy/flux-operator-web, servicemonitor/flux-operator (labels only)"
    - kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml
    - kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml
    - "kubernetes/bootstrap/apps/helmfile.yaml (in PR 257; NOT reconciled by Flux)"
    - "docs/infrastructure.md (follow-up commit)"
  shared: [flux, monitoring]          # flux: the GitOps control plane every other plan's rollback
                                      # depends on. monitoring: the flux-operator pod is the ONLY
                                      # exporter of flux_resource_info / flux_instance_info /
                                      # flux_operator_info (gotk_* is not scraped) - the instrument
                                      # behind FluxResourceNotReady, FluxSourceStalled, FluxMetricsAbsent.
depends_on: []
conflicts_with:
  - flux-reconciler-impersonation     # rewrites FluxInstance patches and the controllers' identity;
                                      # its premise operator-v0.57.0 pins the operator tag (already
                                      # stale at v0.61.0). Two control-plane causes for one failure.
  - flux-oci-chart-sources            # rewrites Flux chart sources (can move these two HRs to an
                                      # OCIRepository) and patches FluxInstance (Stage 10).
  - helm-drift-detection              # changes HelmRelease behaviour cluster-wide incl. these two HRs;
                                      # any flux-system helm revision bump would be unattributable.
  - etcd-timeouts-5000-500            # perturbs the apiserver/etcd the operator's SSA apply and the
                                      # helm upgrade talk to; a same-window Flux not-Ready could be
                                      # either plan's. Not exclusive, so this must be explicit.
exclusive: false                      # the six controllers do NOT roll (section 1.4, gated in 4.4), so
                                      # reconciliation continues and a co-scheduled plan's git-revert
                                      # still works.
security_ref: null                    # no security driver. The image-register row for the operator
                                      # image (F-b81fe869, accepted) is unrelated to this target.
capability_change: false              # 0.62.0 adds SPIFFE mTLS, object-identity field renames, a web-UI
                                      # nodes dashboard and source-watcher impersonation. None is
                                      # configured or reachable here: no spec.spiffe, multitenant off,
                                      # no HTTPRoute to :9080, source-watcher not a component, and the
                                      # impersonation change applies only to Flux >= 2.10. The rendered
                                      # controllers are byte-identical (section 1.4).
rollback_class: git-revert            # no forward-only step: no stored-version change, no data. The one
                                      # persisted side effect (the defaulted multitenantObjectIdentity
                                      # field) is pruned by the 0.61.0 CRD on read; section 5.
finding_refs:
  - F-60f2b033                        # flux-operator: chart 0.61.0 -> 0.62.0 (version, monitor)
  - F-703d6382                        # flux-instance: chart 0.61.0 -> 0.62.0 (version, monitor)
premises:
  # Read-verb only. All run 2026-10-27 ~09:30 CEST at authoring: every one returned the expected value.
  - id: operator-image-current
    why: >-
      current claims operator image v0.61.0. If it moved, the diffs in sections 1.3/1.4 and the
      helm revision numbers in section 5 are wrong - re-derive before running.
    run: kubectl get deploy -n flux-system flux-operator -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/controlplaneio-fluxcd/flux-operator:v0.61.0
  - id: both-charts-current
    why: Both HRs must be on 0.61.0 (kubectl lists them in argument order, flux-operator then flux-instance).
    run: kubectl get hr -n flux-system flux-operator flux-instance -o jsonpath='{.items[*].status.history[0].chartVersion}'
    expect_exact: 0.61.0 0.61.0
  - id: both-hrs-ready
    why: Never start a control-plane change from a not-Ready control plane.
    run: kubectl get hr -n flux-system flux-operator flux-instance -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")].status}'
    expect_exact: True True
  - id: distribution-v2.9.6-digest
    why: >-
      Gate 4.5 asserts the distribution revision is UNCHANGED after the bump (0.62.0 knows Flux
      2.10, which shipped 2026-10-26; the exact pin v2.9.6 must hold it back). The baseline digest
      must be the one measured at authoring.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.status.lastAppliedRevision}'
    expect_contains: "v2.9.6@sha256:57a1bc1dd355767dbce6a429dfe13fecb8c8cd2910543218861d897bac0d6f15"
  - id: distribution-pin-exact
    why: >-
      The no-controller-roll claim holds only while distribution.version is an exact v2.9.6. A
      semver range (2.x, >=2.9) would let the 0.62.0 operator resolve to v2.10.0 - a full
      controller roll this plan does not cover.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.spec.distribution.version}'
    expect_exact: v2.9.6
  - id: identity-fields-compatible
    why: >-
      The 0.62.0 FluxInstance CRD adds CEL rules over these fields (section 1.3). They pass only
      with multitenant off and multitenantWorkloadIdentity false; a different value means the
      flux-instance helm upgrade could be REJECTED by the apiserver - re-assess.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.spec.cluster.multitenant}{" "}{.spec.cluster.multitenantWorkloadIdentity}'
    expect_exact: false false
  - id: no-object-level-wid-field
    why: >-
      New CEL rule forbids objectLevelWorkloadIdentity together with objectIdentityRBAC; the
      ObjectLevelWorkloadIdentity code path also changed. Absent today - if it appears, re-read
      internal/builder/object_identity.go at v0.62.0.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.spec.cluster}' | grep -c ObjectLevel
    expect_exact: "0"
  - id: no-spiffe-spec
    why: SPIFFE is the headline 0.62.0 feature; it is inert only while spec.spiffe is absent.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.spec}' | grep -c -i spiffe
    expect_exact: "0"
  - id: no-resourcesets
    why: >-
      The ResourceSet/RSIP controller changes in 0.62.0 (resourcesetinputprovider_controller.go
      rewrite, RSIP CRD delta) are inert ONLY because zero such objects exist.
    run: kubectl get resourcesets.fluxcd.controlplane.io,resourcesetinputproviders.fluxcd.controlplane.io -A -o name | wc -l | tr -d ' '
    expect_exact: "0"
  - id: target-operator-chart-published
    why: The target operator chart must resolve from the OCI registry the HelmRepository points at.
    run: helm show chart oci://ghcr.io/controlplaneio-fluxcd/charts/flux-operator --version 0.62.0 | grep '^version:'
    expect_exact: "version: 0.62.0"
  - id: target-instance-chart-published
    why: Same, for the instance chart.
    run: helm show chart oci://ghcr.io/controlplaneio-fluxcd/charts/flux-instance --version 0.62.0 | grep '^version:'
    expect_exact: "version: 0.62.0"
  - id: cluster-reconciles-clean
    why: >-
      Gate 4.6 asserts notready=0 after the change; a pre-existing not-Ready object would make it
      fail for a reason this plan did not cause. Suspended objects excluded, as in FluxResourceNotReady.
    run: >-
      kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases.helm.toolkit.fluxcd.io -A
      -o jsonpath='{range .items[*]}{.spec.suspend}{"/"}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
      | grep -v -e '^true/' -e '^false/True$' -e '^/True$' | wc -l | tr -d ' '
    expect_exact: "0"          # 248 ks+hr total, all Ready at authoring
  - id: edit-anchor-unique
    why: The section 3.1 fallback sed must match exactly one line per helmrelease (run from the repo root).
    run: >-
      cat kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml
      kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml | grep -c '^      version: 0.61.0$'
    expect_exact: "2"
status: superseded                    # 2026-11-03: superseded by flux-fleet-0.62.1 (same PR #257, same files, same finding_refs;
                                      # Renovate retargeted 0.62.0 -> 0.62.1). Do NOT run this file; terminal.
superseded_by: flux-fleet-0.62.1
review: null
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/flux-upgrade.md
  - docs/sops/flux-image-automation-push-auth.md
  - docs/sops/maintenance-windows.md
  - docs/sops/disaster-recovery.md
generated: "2026-10-27"
---

# flux-fleet 0.61.0 -> 0.62.0 (flux-operator + flux-instance charts)

## 1. Summary & why held

### 1.1 What changes

Both halves of the Flux control-plane chart family move together in **one commit**: the
squash-merge of Renovate PR #257.

| HelmRelease (ns flux-system) | chart | effect of this bump (measured, section 1.3) |
|---|---|---|
| `flux-operator` | 0.61.0 -> 0.62.0 | **operator pod rolls** to image `v0.62.0`; `fluxinstances` CRD schema grows (SPIFFE + object-identity fields, CEL rules); `resourcesetinputproviders` CRD 13-line delta; everything else labels only |
| `flux-instance` | 0.61.0 -> 0.62.0 | **labels only** (`helm.sh/chart`, `app.kubernetes.io/version`); FluxInstance spec byte-identical |

PR #257 also bumps `kubernetes/bootstrap/apps/helmfile.yaml` (both charts, 0.61.0 -> 0.62.0).
Flux does not reconcile that file, so the DR bootstrap stays in step with no cluster effect.

**The distribution is NOT touched**: `instance.distribution.version: v2.9.6` stays, so the six
controllers keep their images. **Flux v2.10.0 shipped on 2026-10-26** and operator 0.62.0 is the
first release that can install it ("Add Flux 2.10 compatibility", #1082). Moving to 2.10 is a
separate, high-risk plan per `docs/sops/flux-upgrade.md`. This plan is its prerequisite, not
its substitute.

### 1.2 Why it was held

coverage.py: *"0.x release-line move (0.61 -> 0.62): at major 0 the minor IS the breaking axis;
needs an assessed window plan"*. That is a structural rule, not a detected breaking change.

**Upstream release notes**, v0.62.0, published 2026-10-26
(`gh release view v0.62.0 -R controlplaneio-fluxcd/flux-operator`). The full list of
non-dependabot items:
- *"Enable multitenant impersonation for source-watcher"* (#1058)
- *"Log OIDC issuer URL on refresh errors"* (#1043)
- *"web: fix OIDC connections being reused"* (#1063)
- workload-identity docs (#1068, #1070)
- *"web: Add nodes dashboard"* (#1062)
- *"[RFC-0014] operator: retire `ObjectLevelWorkloadIdentity` feature gate"* (#1078)
- *"Update to Kubernetes 1.37"* (#1079)
- *"web: Update to Preact 11 and Tailwind CSS 4"* (#1080)
- *"[RFC-0014] operator: rename obj-lvl wid to object identity"* (#1081)
- *"Add Flux 2.10 compatibility"* (#1082)
- *"[RFC-0014] add support for mTLS with SPIFFE to `FluxInstance` and Flux Web UI"* (#1084)

None is labelled breaking. The two items that could break an existing install are #1078 and
#1081. They are scoped as follows:

- **#1078/#1081 (feature-gate retirement, field renames).** `internal/builder/workload_identity.go`
  was replaced by `object_identity.go`. Read at v0.62.0, the `>= 2.7.0 && < 2.10.0` branch (our
  v2.9.6) is unchanged in effect: it still emits
  `GetProfileObjectLevelWorkloadIdentity(allControllers, false)` and sets
  `RemovePermissionForCreatingServiceAccountTokens = true` when object identity is off. The
  "gate retired" and "RBAC added back" behaviour applies only in the `default:` (>= 2.10.0)
  branch. The old field names stay accepted as "legacy".
- **#1058 (source-watcher impersonation).** `GetProfileMultitenant` adds `source-watcher` only
  when `cluster.multitenant` is true AND the version is >= 2.10.0. Both conditions are false here
  (premises `identity-fields-compatible`, `distribution-pin-exact`).
- **SPIFFE (#1084).** `ValidateAndApplySPIFFEConfig` returns nil at its first line when
  `spec.spiffe == nil` (`internal/builder/spiffe.go:104`). The operator SPIFFE source is only
  consulted when `spec.spiffe.mtls.enabled` (`fluxinstance_controller.go`, `build()`).
  `status.spiffe` stays nil. Premise `no-spiffe-spec`.
- **K8s 1.37 libs.** `k8s.io/client-go` 0.36.3 -> 0.37.1 and `controller-runtime` 0.24.1 -> 0.25.2
  against apiserver `v1.36.0` (measured), which is inside the supported +-1 client skew.
- **Reconcile libraries.** `fluxcd/pkg/ssa` 0.77.0 -> 0.83.0, `fluxcd/pkg/kustomize` 1.39.0 -> 1.44.0,
  `sigs.k8s.io/kustomize/api` 0.21.1 -> 0.21.2. These are real deltas (in 0.57 -> 0.61 they were
  identical), which is why 1.4 is measured rather than argued.
- **Metrics reporter** (`internal/reporter/metrics.go`). Only the `source_name` label changed, and
  only for HelmReleases with `spec.chart.kind: OCIRepository`. That spec does not exist here:
  every HR uses `spec.chart.spec.sourceRef` or `chartRef`, both of which keep their old branch.
  Gate 4.3 reads the series count, not that label.
- **Notifier rewrite.** It adds an `action` annotation to operator events. No notification-controller
  `Alert` objects exist in the cluster (`kubectl get alerts.notification.toolkit.fluxcd.io -A` is
  empty), so nothing consumes it.

### 1.3 Rendered chart diff with OUR values

Measured 2026-10-27. Method: `helm pull` both versions of both charts, `helm template` with
`app/helm-values.yaml` and `instance/helm-values.yaml`, then a per-object diff.

- **flux-instance:** 2 changed lines (the `helm.sh/chart` and `app.kubernetes.io/version`
  labels). The chart gains an optional `instance.spiffe` passthrough, which we leave unset.
- **flux-operator:** no object added or removed. Non-label deltas:
  - `Deployment/flux-operator`: `image: ...flux-operator:v0.61.0 -> v0.62.0`, nothing else. The
    new chart values `spiffe.*` and `web.authorizedClientSPIFFEIDs` default empty and render
    nothing.
  - `CRD/fluxinstances`: 251 changed lines. It adds `spec.spiffe`, `cluster.objectIdentityRBAC`
    and `cluster.multitenantObjectIdentity` (with `default: false`), and has three cluster-level
    CEL rules plus one new spec-level rule. Evaluated against the live spec
    (`multitenant: false`, `multitenantWorkloadIdentity: false`, no `objectLevelWorkloadIdentity`,
    no `objectIdentityRBAC`, no `spiffe`), **all four rules pass**. The premises pin each input.
  - `CRD/resourcesetinputproviders`: 13 lines. 0 objects exist.

### 1.4 Will the six controllers re-render? Measured: NO

`flux-operator build instance` is the operator's own builder exposed as a CLI. I ran the
**v0.61.0 and v0.62.0 darwin_arm64 CLIs** (GitHub release assets) against the **live FluxInstance
spec** (`kubectl get fluxinstance flux -o yaml`, reduced to spec). The output was **byte-identical:
7585 lines each, `diff` empty.** Both builds used the same `flux-operator-manifests:latest`
artifact that the live FluxInstance pulls, so the only variable was the operator's builder. The
expected outcome is a server-side-apply no-op for the controllers: **no controller restart**.
Gate 4.4 turns this into a check that fails if it is wrong. If the newer SSA library's
normalisation still triggered a re-apply that changes a pod template, 4.4 prints the diff.

**Verdict:** the hold is a **false positive for breakage**. What remains is blast radius and a
larger-than-usual operator binary delta. The previous identical-shape run (0.57 -> 0.61,
executed `now:2026-10-21`, `23a89557`) passed every gate this plan re-uses. Hence risk medium,
one commit, with gates that read what the operator reports.

### 1.5 Execution class (why there is no `autonomy_override`)

Derived: `capability_change: false` + `git-revert` + no reboot => AUTO-NIGHT. `shared: [flux]`
is in the SD-11 in-code floor and `risk: medium` is not SD-10, so **an operator GO is still
required**. The GO is NOT tied to an attended slot, though: with a GO this can run in any
window, `nightly` included. I deliberately did not set `autonomy_override: human-gated`. Per
F-1ce18da8, that made the 0.60.0 plan's nightly-scoped GO lapse for five nights. Whether this
control-plane bump should nonetheless be attended is the operator's call when giving the GO.

## 2. Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` in zsh. Any failure -> stop, do not merge.

```bash
cd /Users/mu/code/cberg-home-nextgen
# a) premises (all 13 must PASS)
.venv/bin/python3 runbooks/plan-premises.py flux-fleet-0.62.0 --require-premises

# b) PR 257 is still exactly the three-file 0.61.0 -> 0.62.0 bump and green
gh pr view 257 --json state,mergeable,files,statusCheckRollup \
  -q '"\(.state) \(.mergeable) files=\([.files[].path]|join(",")) checks=\([.statusCheckRollup[]|(.conclusion//.state)]|unique|join(","))"'
# PASS: "OPEN MERGEABLE files=kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml,
#        kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml,kubernetes/bootstrap/apps/helmfile.yaml checks=SUCCESS"
gh pr diff 257 | grep -c '^+.*version: 0.62.0$'      # PASS: 4
gh pr diff 257 | grep -c '^-.*version: 0.61.0$'      # PASS: 4
# If Renovate has retargeted the PR (e.g. 0.62.1) or it is closed: STOP, the plan needs a refresh.

# c) upstream has not yanked or superseded v0.62.0 since authoring
gh release view v0.62.0 -R controlplaneio-fluxcd/flux-operator --json isPrerelease,isDraft -q '"\(.isPrerelease) \(.isDraft)"'   # PASS: false false
gh release list -R controlplaneio-fluxcd/flux-operator --limit 2      # informational: a v0.62.1 means read its notes first

# d) repo is at the revision Flux has applied (no in-flight reconcile of a newer commit)
git fetch -q origin
mise exec -- kubectl -n flux-system get gitrepository flux-system -o jsonpath='{.status.artifact.revision}{"\n"}'
git rev-parse origin/main
# PASS: the sha in the artifact revision equals origin/main.

# e) snapshot known-good state OUTSIDE the repo (used by 4.4, 4.5 and section 5)
mkdir -p /tmp/flux-fleet-062 && cd /tmp/flux-fleet-062
mise exec -- kubectl -n flux-system get deploy source-controller kustomize-controller helm-controller \
  notification-controller image-reflector-controller image-automation-controller \
  -o jsonpath='{range .items[*]}{.metadata.name}{" gen="}{.metadata.generation}{" img="}{.spec.template.spec.containers[0].image}{"\n"}{end}' \
  > ctrl-before.txt
mise exec -- kubectl -n flux-system get pods -l 'app in (source-controller,kustomize-controller,helm-controller,notification-controller,image-reflector-controller,image-automation-controller)' \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.startTime}{"\n"}{end}' > ctrl-pods-before.txt
wc -l ctrl-before.txt ctrl-pods-before.txt        # PASS: 6 and 6 (both measured 6 at authoring)
mise exec -- kubectl -n flux-system get deploy flux-operator -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}' > operator-before.txt
mise exec -- kubectl -n flux-system get fluxinstance flux -o jsonpath='{.status.lastAppliedRevision}{"\n"}' > fi-rev-before.txt
mise exec -- kubectl get crd fluxinstances.fluxcd.controlplane.io fluxreports.fluxcd.controlplane.io \
  resourcesets.fluxcd.controlplane.io resourcesetinputproviders.fluxcd.controlplane.io -o yaml > operator-crds-before.yaml
mise exec -- helm -n flux-system history flux-operator --max 3 > helm-op-before.txt
mise exec -- helm -n flux-system history flux-instance --max 3 > helm-inst-before.txt
tail -1 helm-op-before.txt; tail -1 helm-inst-before.txt
# EXPECT (measured 2026-10-27): flux-operator rev 4 deployed flux-operator-0.61.0;
#                              flux-instance rev 8 deployed flux-instance-0.61.0.
# If the numbers differ, write the real ones down: section 5 step 2 uses them.
cd /Users/mu/code/cberg-home-nextgen

# f) Prometheus baseline for the flux_* instrument (port-forward by PID, never kill %1)
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
pq() { curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "EMPTY")'; }
pq 'count(flux_resource_info)' | tee /tmp/flux-fleet-062/series-before.txt   # measured 425 on 2026-10-27
pq 'count(count by (kind) (flux_resource_info))'                             # PASS: 10 (measured 10)
pq 'count(flux_resource_info{ready="False",suspended="False"})'              # PASS: EMPTY
pq 'count(flux_operator_info{version="v0.61.0"})'                            # PASS: 1
pq 'count(flux_operator_info{version="v0.62.0"})'                            # PASS: EMPTY  <- negative control for gate 4.2
pq 'max_over_time(count(flux_resource_info{ready="False",suspended="False"})[14d:10m])'   # POSITIVE CONTROL for 4.6: must be non-EMPTY (46 on 2026-10-27); EMPTY -> the ready="False" gate cannot fail, STOP
pq 'count(count_over_time(ALERTS{alertname="FluxResourceNotReady"}[14d]))'   # POSITIVE CONTROL for the 4.6 ALERTS gate: non-EMPTY (886 on 2026-10-27); EMPTY -> retry [30d]; still EMPTY -> 4.6 ALERTS line informational only
pq 'count(ALERTS{alertname=~"Flux.*",alertstate="firing"})'                  # PASS: EMPTY
pq 'max(container_memory_working_set_bytes{namespace="flux-system",container="manager",pod=~"flux-operator-.*"})' | tee /tmp/flux-fleet-062/opmem-before.txt   # ~190 MB at authoring (limit 1Gi)
kill $PF 2>/dev/null
# Fleet-size baseline for gate 4.6 (never compare against a hardcoded total; 248 at authoring)
mise exec -- kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases.helm.toolkit.fluxcd.io -A -o json \
  | python3 -c 'import sys,json; it=json.load(sys.stdin)["items"]; bad=[i["metadata"]["namespace"]+"/"+i["metadata"]["name"] for i in it if not i["spec"].get("suspend") and not any(c["type"]=="Ready" and c["status"]=="True" for c in i.get("status",{}).get("conditions",[]))]; print("total=%d notready=%d %s" % (len(it), len(bad), bad))' | tee /tmp/flux-fleet-062/total-before.txt
# PASS: notready=0. The total= value is the 4.6 baseline.

# g) push path works (the rollback is a push)
git push --dry-run origin main && echo PUSH_OK
```

Not taken, and why: SOP `flux-upgrade.md` step 2 sets `retries: 0` / `cleanupOnFail: false` to
stop helm remediation from half-reverting a **six-controller roll**. No controller rolls here
(1.4). The only rolling workload is the operator Deployment, and an automatic helm rollback of
it to 0.61.0 is the failure mode we want, not a hazard. Gate 4.1 detects one if it happens.

## 3. Steps

### 3.1 The coordinated bump: merge PR #257 (one squash commit, three files)

```bash
cd /Users/mu/code/cberg-home-nextgen
gh pr merge 257 --squash --delete-branch
git fetch -q origin
git log -1 --format='%H %s' origin/main | tee /tmp/flux-fleet-062/core.txt
git show --stat origin/main | tail -5
# MUST list exactly: app/helmrelease.yaml, instance/helmrelease.yaml, bootstrap/apps/helmfile.yaml (3 files, 6 +/-)
cut -d' ' -f1 /tmp/flux-fleet-062/core.txt > /tmp/flux-fleet-062/core-sha.txt
git pull --ff-only     # shared worktree: if this refuses because of others' local changes, do NOT stash theirs;
                       # the cluster reconciles from origin, the local checkout only matters for 3.3
```

**Fallback, ONLY if PR #257 is unmergeable (conflict) or was closed:** apply the same edit
directly. Dry-tested on scratch copies on macOS 2026-10-27 (BSD sed). The resulting diff:
`12c12 <       version: 0.61.0 >       version: 0.62.0` in each helmrelease, and
`41c41`/`48c48 <     version: 0.61.0 >     version: 0.62.0` in helmfile.yaml.

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's/^      version: 0\.61\.0$/      version: 0.62.0/' \
  kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml \
  kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml
sed -i '' -e '/charts\/flux-operator$/{n;s/^    version: 0\.61\.0$/    version: 0.62.0/;}' \
          -e '/charts\/flux-instance$/{n;s/^    version: 0\.61\.0$/    version: 0.62.0/;}' \
  kubernetes/bootstrap/apps/helmfile.yaml
git diff --stat -- kubernetes/apps/flux-system/flux-operator/ kubernetes/bootstrap/apps/helmfile.yaml   # EXPECT: 3 files, 4 insertions, 4 deletions
mise exec -- kubeconform -summary -ignore-missing-schemas kubernetes/apps/flux-system/flux-operator/
mkdir -p /tmp/flux-fleet-062
cat > /tmp/flux-fleet-062/msg-core.txt <<'EOF'
feat(flux): flux-operator + flux-instance charts 0.61.0 -> 0.62.0 (plan flux-fleet-0.62.0)

Operator image v0.61.0 -> v0.62.0. Distribution stays v2.9.6; rendered
FluxInstance spec unchanged and controller manifests byte-identical
(flux-operator build instance, both CLIs). Supersedes Renovate #257.
Findings F-60f2b033 F-703d6382.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml \
  kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml \
  kubernetes/bootstrap/apps/helmfile.yaml -F /tmp/flux-fleet-062/msg-core.txt
git log -1 --format=%s          # MUST be the subject above (shared-worktree message swap guard); amend if not
git show --stat HEAD            # MUST list exactly the three files
git rev-parse HEAD > /tmp/flux-fleet-062/core-sha.txt
git push origin main
gh pr close 257 --comment "Applied directly by plan flux-fleet-0.62.0 ($(cat /tmp/flux-fleet-062/core-sha.txt))"
```

### 3.2 Propagation (observe; do not force unless stalled)

Webhook -> `Receiver` -> GitRepository `flux-system` -> Kustomizations `flux-operator` and
`flux-instance` -> helm-controller upgrades `hr/flux-operator` (CRDs updated, operator pod rolls)
then `hr/flux-instance` (`dependsOn: flux-operator`).

```bash
for i in $(seq 1 20); do
  R=$(mise exec -- kubectl -n flux-system get hr flux-operator flux-instance -o jsonpath='{.items[*].status.history[0].chartVersion}')
  echo "$(date +%T) $R"; [ "$R" = "0.62.0 0.62.0" ] && break; sleep 30
done
[ "$R" = "0.62.0 0.62.0" ] && echo PROPAGATED || echo "PROPAGATION_NOT_COMPLETE after 10 min -> run the reconcile block below"
```

If after 10 minutes the source revision has not reached the core sha, the webhook did not fire.
`docs/sops/flux-upgrade.md` section 4 step 4 prescribes driving the reconcile in order. Run
this only in that case:

```bash
mise exec -- flux -n flux-system reconcile source git flux-system
mise exec -- flux -n flux-system reconcile ks flux-operator && mise exec -- flux -n flux-system reconcile hr flux-operator
mise exec -- flux -n flux-system reconcile ks flux-instance && mise exec -- flux -n flux-system reconcile hr flux-instance
```

If `hr/flux-instance` goes `Ready=False` with a message containing `x-kubernetes-validations` or
`Invalid value`, a CEL rule from 1.3 has rejected the FluxInstance. This is not an outage: the
old FluxInstance object stays in place and the controllers keep running. Go to section 5 step 1.

### 3.3 Follow-up commit (ONLY after section 4 is fully green)

`docs/infrastructure.md` still says 0.61.0 in three places. Dry-tested on a scratch copy
(BSD sed). Diff: lines `111,112` `| 0.61.0 | flux-system |` -> `| 0.62.0 | flux-system |`, and
line `134` `(flux-operator/flux-instance chart 0.61.0)` -> `(... chart 0.62.0)`.

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' -e 's#^\(| [45] | Flux [A-Za-z]* | `oci://ghcr.io/controlplaneio-fluxcd/charts/flux-[a-z]*` | \)0\.61\.0 |#\10.62.0 |#' \
          -e 's#(flux-operator/flux-instance chart 0\.61\.0)#(flux-operator/flux-instance chart 0.62.0)#' \
  docs/infrastructure.md
git diff --stat -- docs/infrastructure.md   # EXPECT: 1 file, 3 insertions, 3 deletions
cat > /tmp/flux-fleet-062/msg-docs.txt <<'EOF'
docs(flux): infrastructure.md to flux charts 0.62.0

No cluster effect. Plan flux-fleet-0.62.0.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git commit --only docs/infrastructure.md -F /tmp/flux-fleet-062/msg-docs.txt
git log -1 --format=%s && git show --stat HEAD && git push origin main
```

Then retire this plan file per `runbooks/maintenance/plans/README.md` and close both findings
with the core sha: `runbooks/policy-cli.py finding close F-60f2b033 --commit <core-sha>` (same
for F-703d6382).

## 4. Verification

Run in order; each gate says what its failure prints. Re-establish the Prometheus port-forward
(`PF=$!` form from 2 f) and re-define `pq` first. The operator restart does not affect this
port-forward, because it targets Prometheus, not the operator.

### 4.1 Both releases deployed at 0.62.0, no remediation rollback

```bash
mise exec -- kubectl -n flux-system get hr flux-operator flux-instance \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.history[0].chartVersion}{" "}{.status.history[0].status}{" "}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
mise exec -- helm -n flux-system history flux-operator --max 2
mise exec -- helm -n flux-system history flux-instance --max 2
```
- **PASS:** `flux-instance 0.62.0 deployed True` and `flux-operator 0.62.0 deployed True`. Helm's
  latest revisions are 5 (`flux-operator-0.62.0`, "Upgrade complete") and 9
  (`flux-instance-0.62.0`).
- **FAIL looks like:**
  - chartVersion `0.61.0` with a newer revision described as `Rollback to 4` (remediation fired);
  - Ready `False` with `upgrade retries exhausted`;
  - a CEL `Invalid value` message on flux-instance (see 3.2).

### 4.2 The operator serving metrics IS the new build

```bash
mise exec -- kubectl -n flux-system get deploy flux-operator -o jsonpath='{.spec.template.spec.containers[0].image}{" avail="}{.status.availableReplicas}{"\n"}'
mise exec -- kubectl -n flux-system get pods -l app.kubernetes.io/name=flux-operator \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.phase}{" restarts="}{.status.containerStatuses[0].restartCount}{"\n"}{end}'
sleep 60   # one scrape interval after the new pod is Ready
pq 'count(flux_operator_info{version="v0.62.0"})'
pq 'count(flux_operator_info{version="v0.61.0"})'
mise exec -- kubectl -n flux-system logs deploy/flux-operator --since=10m | grep -c -i -e '"level":"error"' -e 'panic'
```
- **PASS:**
  - the image reads `...flux-operator:v0.62.0 avail=1`;
  - exactly one pod, `Running restarts=0`;
  - `flux_operator_info` with `v0.62.0` -> `1`, with `v0.61.0` -> `EMPTY`;
  - the error/panic count is `0`.
- **FAIL looks like:**
  - `v0.62.0` -> `EMPTY`. This can fail: at authoring the same query returned `EMPTY` and the
    `v0.61.0` query returned `1`.
  - `EMPTY` for BOTH versions. The scrape itself is broken (ServiceMonitor/port), so treat it
    as FAIL and go to 4.3.
  - A non-zero log count. Read the lines. A logged error is not automatically a revert: if 4.3
    to 4.6 pass, record it and decide with the operator.

CONTROL: metric flux_operator_info — `count` with `version="v0.62.0"` must be exactly 1 after the roll, and the v0.61.0 series must be gone.

### 4.3 The operator still reports the whole fleet (contents, not shape)

```bash
pq 'count(flux_resource_info)'; cat /tmp/flux-fleet-062/series-before.txt
pq 'count by (kind) (flux_resource_info)'
```
CONTENTS ASSERTION: the operator's report of every Flux object is complete. It is measured by
`count(flux_resource_info)` against the 2 f baseline (425 at authoring).

- **PASS:** the count is within +/-5 of the baseline AND all 10 kinds are present: HelmRelease,
  HelmChart, HelmRepository, Kustomization, GitRepository, OCIRepository, Receiver, ImagePolicy,
  ImageRepository, ImageUpdateAutomation.
- **FAIL looks like:**
  - `EMPTY`, meaning the reporter or scrape is broken. Here an empty result is a FAIL, never a
    pass.
  - A count far below the baseline. 0.62.0 rewrote reporter code around the cluster/node info,
    and this is the gate that sees a regression there.
  - A missing kind.

CONTROL: metric flux_resource_info — `count()` floor at baseline-5 with all 10 kinds present; also the input to FluxResourceNotReady / FluxSourceStalled / FluxMetricsAbsent.

### 4.4 The six controllers did NOT roll (the plan's central claim)

```bash
mise exec -- kubectl -n flux-system get deploy source-controller kustomize-controller helm-controller \
  notification-controller image-reflector-controller image-automation-controller \
  -o jsonpath='{range .items[*]}{.metadata.name}{" gen="}{.metadata.generation}{" img="}{.spec.template.spec.containers[0].image}{"\n"}{end}' \
  | diff /tmp/flux-fleet-062/ctrl-before.txt - && echo CONTROLLERS_UNCHANGED
mise exec -- kubectl -n flux-system get pods -l 'app in (source-controller,kustomize-controller,helm-controller,notification-controller,image-reflector-controller,image-automation-controller)' \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.startTime}{"\n"}{end}' \
  | diff /tmp/flux-fleet-062/ctrl-pods-before.txt - && echo CONTROLLER_PODS_UNCHANGED
```
- **PASS:** both `..._UNCHANGED` lines print.
- **FAIL looks like:** a `diff` hunk showing `gen=4` or a new pod name/startTime. That means the
  0.62.0 operator re-applied the controllers, which contradicts 1.4. The likely cause is the SSA
  library bump (0.77 -> 0.83).
- **On FAIL:** this is not automatically an outage (check 4.6), but the plan's premise is
  falsified. Stop, record the diff, do not proceed to 3.3, and decide revert-vs-keep with the
  operator.
- This gate can fail: `diff` against the snapshot is an exact-string compare, so any digest or
  generation change prints.

### 4.5 FluxInstance applied the SAME distribution, spec intact

```bash
mise exec -- kubectl -n flux-system get fluxinstance flux \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{" "}{.status.lastAppliedRevision}{"\n"}'
cat /tmp/flux-fleet-062/fi-rev-before.txt
mise exec -- kubectl -n flux-system get fluxinstance flux -o jsonpath='{.spec.sync.pullSecret}{"|"}{.spec.distribution.version}{"|"}{.status.spiffe}{"\n"}'
mise exec -- kubectl -n flux-system get gitrepository flux-system -o jsonpath='{.spec.secretRef.name}{"|"}{.spec.ignore}{"\n"}'
pq 'count(flux_instance_info{ready="True",revision="v2.9.6@sha256:57a1bc1dd355767dbce6a429dfe13fecb8c8cd2910543218861d897bac0d6f15"})'
```
- **PASS:**
  - `True v2.9.6@sha256:57a1bc1d...`, identical to the saved revision;
  - the second line reads `flux-system-git-auth|v2.9.6|` (empty `status.spiffe`);
  - the GitRepository shows `flux-system-git-auth|` followed by the ignore block containing
    `!/kubernetes`;
  - the PromQL returns `1` (measured `1` at authoring).
- **FAIL looks like:**
  - any `v2.10` revision. The operator moved the distribution, which means a full controller
    roll this plan did not cover. Revert immediately.
  - an empty `pullSecret` (the silent-prune failure in
    `docs/sops/flux-image-automation-push-auth.md`);
  - an ignore block without `!/kubernetes`;
  - a non-empty `status.spiffe`.

CONTROL: metric flux_instance_info — `count` with ready="True" and the exact v2.9.6 digest revision label must be 1.

### 4.6 The cluster still reconciles end to end (10-minute soak)

```bash
sleep 600
mise exec -- kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases.helm.toolkit.fluxcd.io -A -o json \
  | python3 -c 'import sys,json; it=json.load(sys.stdin)["items"]; bad=[i["metadata"]["namespace"]+"/"+i["metadata"]["name"] for i in it if not i["spec"].get("suspend") and not any(c["type"]=="Ready" and c["status"]=="True" for c in i.get("status",{}).get("conditions",[]))]; print("total=%d notready=%d %s" % (len(it), len(bad), bad))' | tee /tmp/flux-fleet-062/total-after.txt
cat /tmp/flux-fleet-062/total-before.txt
pq 'count(flux_resource_info{ready="False",suspended="False"})'
pq 'count(ALERTS{alertname=~"FluxResourceNotReady|FluxSourceStalled|FluxMetricsAbsent",alertstate=~"pending|firing"})'
pq 'max(container_memory_working_set_bytes{namespace="flux-system",container="manager",pod=~"flux-operator-.*"})'; cat /tmp/flux-fleet-062/opmem-before.txt
mise exec -- kubectl -n flux-system get ks flux-system cluster-apps flux-operator flux-instance \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.lastAppliedRevision}{"\n"}{end}'
kill $PF 2>/dev/null
```
- **PASS:**
  - `notready=0`, with `total` within +/-3 of the 2 f baseline (NOT a hardcoded number; 248 at
    authoring).
  - Both of the first two PromQL lines are `EMPTY`. That is valid only because 4.3 proved the
    series exist and the 2 f positive controls proved both queries can match (46 and 886 at
    authoring).
  - Operator memory is below 512 MB. The baseline was ~190 MB and the limit is 1Gi; 0.62.0 adds
    a nodes dashboard to the always-on web server on :9080.
  - All four Kustomizations show `refs/heads/main@sha1:<core sha or later>`.
- **FAIL looks like:**
  - `notready=N [ns/name...]`;
  - a non-empty ALERTS count;
  - memory approaching the limit (OOM risk), which needs an operator decision;
  - a Kustomization still on the pre-change sha (reconciliation stalled).
- FluxMetricsAbsent has `for: 30m` and cannot fire inside this window. 4.3's floor is what
  actually guards the metric path.

CONTROL: alertname FluxResourceNotReady — must not be pending or firing after the soak.
CONTROL: alertname FluxSourceStalled — must not be pending or firing (would mean the GitRepository cannot fetch: nothing deploys).
CONTROL: alertname FluxMetricsAbsent — must not be firing; informational within the window (30m `for`), covered by 4.3.

## 5. Rollback

Nothing in this plan is forward-only. There is no stored-version change and no data. The only
persisted side effect is that the apiserver, under the 0.62.0 CRD, will default
`spec.cluster.multitenantObjectIdentity: false` into the stored FluxInstance on its next write.
After a downgrade, the 0.61.0 CRD's structural schema drops that unknown field when the object
is read, and 0.61.0 never reads it. The 3.3 docs commit has no cluster effect and never needs
reverting for recovery.

**Trigger:** any of 4.1-4.3 or 4.5-4.6 FAILs, or 4.4 FAILs together with any 4.6 failure.

1. **GitOps revert (preferred).** The controllers never rolled, so Flux is fully able to apply it.
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git fetch -q origin && git pull --ff-only
   git revert --no-edit $(cat /tmp/flux-fleet-062/core-sha.txt)
   git log -1 --format=%s && git show --stat HEAD     # the three PR-257 files only
   git push origin main
   ```
   helm-controller downgrades both releases to 0.61.0 (new revisions, e.g. 6 and 10), the
   operator pod rolls back to v0.61.0, and the CRDs return to the 0.61.0 schema. Renovate will
   reopen a PR for 0.62.0. Leave it unmerged and set this plan to `blocked` with the failure.
2. **Flux-independent.** Use this only if the operator or helm-controller is wedged and step 1
   has not converged within 10 minutes.
   ```bash
   for hr in flux-operator flux-instance; do mise exec -- kubectl -n flux-system patch hr $hr --type merge -p '{"spec":{"suspend":true}}'; done
   mise exec -- helm -n flux-system rollback flux-operator 4    # rev numbers from /tmp/flux-fleet-062/helm-op-before.txt
   mise exec -- helm -n flux-system rollback flux-instance 8    # and helm-inst-before.txt
   # still crashlooping? pin the known-good image recorded in operator-before.txt:
   mise exec -- kubectl -n flux-system set image deploy/flux-operator manager=$(cat /tmp/flux-fleet-062/operator-before.txt)
   ```
   Then make git match (push the step 1 revert) and un-suspend both HRs
   (`...patch hr $hr --type merge -p '{"spec":{"suspend":false}}'`). If even this fails, follow
   `docs/sops/disaster-recovery.md`. The container name `manager` was verified live 2026-10-27.
3. **Confirm the cluster is back.**
   - Re-run 4.1, expecting `0.61.0 deployed True` for both.
   - Re-run 4.2, expecting `flux_operator_info{version="v0.61.0"}` -> `1` and `v0.62.0` -> `EMPTY`.
   - 4.3, 4.5 and 4.6 keep their PASS criteria unchanged.
   - `/tmp/flux-fleet-062/operator-crds-before.yaml` is for one case only: a schema mismatch
     blocking the 0.61.0 operator, which is not expected because 0.62.0 only ADDS fields and
     rules. In that case alone, apply it with `mise exec -- kubectl apply -f`.

## 6. Interference notes

- **Control plane, but not a controller roll.** Only `deployment/flux-operator` restarts
  (~30-60 s). Source/kustomize/helm/notification/image controllers keep reconciling other plans'
  commits throughout, which is why this plan is not `exclusive`. If 4.4 shows otherwise, treat
  the window as having had a full controller roll (transient `artifact not found` for about one
  interval, per `docs/sops/flux-upgrade.md` Test 2).
- **The instrument restarts.** Every Flux alert reads `flux_*` series from the operator pod, so
  its restart leaves a scrape gap of about one interval. No other open plan's verification reads
  `flux_*` except `flux-reconciler-impersonation` (in conflicts_with). No
  `kube-prometheus-stack` plan is open. Renovate #428 (kube-prometheus-stack 92.11.1 -> 92.14.0)
  is an open PR: if a window's Step 0 lands it the same night, run this plan's gates only after
  Prometheus is back Ready.
- **Flux v2.10.0 is out (2026-10-26), and Renovate #448 bumps the `flux` CLI pin to 2.10.0.**
  This plan keeps the distribution at v2.9.6 (premise `distribution-pin-exact`, gate 4.5). Repo
  note for the operator: merging #448 before a distribution-2.10 plan runs would break the
  CLI/distribution match that `docs/sops/flux-upgrade.md` section 2 asks for. A future
  `flux-distribution-2.10.0` plan should `depends_on: [flux-fleet-0.62.0]`, because 0.62.0 is
  the first operator with 2.10 support (#1082). That plan also inherits Flux 2.10's own
  RBAC/feature-gate changes noted in 1.2.
- **flux-reconciler-impersonation** is blocked and unwindowed. Its premise
  `operator-v0.57.0` is already stale (live is v0.61.0). After this plan it should read
  `v0.62.0`, and its owner must re-read `internal/builder/profiles.go` at v0.62.0 first:
  `GetProfileMultitenant` gained a version argument (source-watcher, >= 2.10 only), and
  `workload_identity.go` became `object_identity.go`. For v2.9.x and our non-multitenant spec
  the effect is identical (1.2), but that plan appends a Deployment patch and must confirm it
  for itself.
- **helm-drift-detection** (`sat-attended:2026-11-07`) adds `spec.driftDetection` to these two
  HRs as well. Its premise `helm-controller-is-v1.6.x` and its note that live controller args
  carry only `ObjectLevelWorkloadIdentity=false` stay true after this plan: the controllers are
  byte-identical (4.4).
- **flux-oci-chart-sources** (`sun-attended:2026-11-22`) may move these two HRs' chart source to
  an `OCIRepository`. If it runs first, the 3.1 edit target changes and this plan must be
  refreshed.
- **etcd-timeouts-5000-500** (`sun-attended:2026-11-08`) perturbs the apiserver/etcd. It is
  listed in conflicts_with for attribution only.
- **Step 0 interplay.** coverage.py lists this group under `needs_plan_groups`, so the safe-update
  lane will neither auto-merge #257 nor direct-bump these files. The window must not merge #257
  outside this plan.
- **Out of scope, deliberately:** the distribution bump, the `.mise.toml` flux CLI pin (#448), and
  adopting any 0.62.0 feature (SPIFFE, objectIdentityRBAC rename, web-UI exposure).
