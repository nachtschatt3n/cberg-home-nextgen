---
plan_id: flux-fleet-0.62.1
component: flux-fleet                 # chart-family group: flux-operator + flux-instance (ns flux-system)
supersedes: flux-fleet-0.62.0         # uncommitted 2026-10-27 draft for target 0.62.0; Renovate #257 has
                                      # since retargeted to 0.62.1. That file must be set status: superseded
                                      # (or deleted) so the two never both reach a window - they claim the
                                      # same PR and the same finding_refs.
pr: 257                               # Renovate "update flux operator group ( 0.61.0 -> 0.62.1 )": same three
                                      # files as before (both helmrelease.yaml + kubernetes/bootstrap/apps/
                                      # helmfile.yaml), 4 version lines; CI SUCCESS, MERGEABLE at authoring
                                      # (2026-10-29).
kind: chart
current: "flux-operator chart 0.61.0 (operator image v0.61.0) + flux-instance chart 0.61.0; FluxInstance distribution v2.9.6 (unchanged by this plan)"
target: "flux-operator chart 0.62.1 (operator image v0.62.1) + flux-instance chart 0.62.1; distribution stays v2.9.6"
update_type: minor                    # 0.x line: 0.61 -> 0.62 is a "minor" at major 0; 0.62.0 -> 0.62.1 is a
                                      # one-fix patch on top (section 1.3)
risk: medium                          # Rendered diff small (1.4) and the six controllers measured NOT to
                                      # re-render with the v0.62.1 builder (1.5). Medium = the operator
                                      # BINARY delta of the 0.62 line (k8s libs 0.36 -> 0.37, fluxcd/pkg/ssa
                                      # 0.77 -> 0.83, notifier + RSIP controller rewrites, SPIFFE plumbing)
                                      # and blast radius: this is the reconcile engine, and the operator pod
                                      # is the only exporter of the flux_* series every Flux alert reads.
est_duration_min: 35                  # pre-checks 8 + merge/pull 3 + propagate/roll 7 + verification 13
                                      # (includes a 10-min soak) + docs follow-up 4.
needs_reboot: false
touches:
  namespaces: [flux-system]
  resources:
    - helmrelease/flux-operator (flux-system)          # chart 0.61.0 -> 0.62.1; helm rev 4 -> 5
    - helmrelease/flux-instance (flux-system)          # chart 0.61.0 -> 0.62.1; helm rev 8 -> 9
    - deployment/flux-operator (flux-system)           # ROLLS: image v0.61.0 -> v0.62.1 (1 replica)
    - crd/fluxinstances.fluxcd.controlplane.io         # schema: +spec.spiffe, +cluster.objectIdentityRBAC,
                                                       # +cluster.multitenantObjectIdentity (default false),
                                                       # CEL rules (1.4); 0.62.1 adds a description-only edit
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
  - talos-linux-1.14.5                # ADDED 2026-11-03 (reciprocal: it already names this plan): restarts the six Flux controllers
                                      # and suspends/resumes ImageUpdateAutomation; a main-pushing Flux bump cannot share a slot.
                                      # Replaces the stale talos-linux-1.14.2, which is superseded.
  - coredns-1.50.0                    # ADDED 2026-11-03 (reciprocal: it already names this plan): this plan's revert path is
                                      # git push -> source-controller resolving github.com THROUGH CoreDNS; both plans are 35 min,
                                      # 70 of 70 usable nightly min, and a DNS fault would be attributed to the wrong change.
  # flux-fleet-0.62.0 REMOVED 2026-11-03: it is now `status: superseded` (terminal, pointing at this plan), so it can
  # never reach a window and a conflicts_with edge to it is dead weight.
exclusive: false                      # the six controllers do NOT roll (1.5, gated in 4.4), so
                                      # reconciliation continues and a co-scheduled plan's git-revert
                                      # still works.
security_ref: F-73c160d1              # LINKED 2026-11-03 (was `null`, "no security driver", which was wrong): the open security row for
                                      # the CURRENT operator image ghcr.io/controlplaneio-fluxcd/flux-operator:v0.61.0 is "fixable
                                      # HIGH findings, newer upstream tag available" (contextual tier medium). This plan moves
                                      # that image to v0.62.1, the newer tag the row points at. Detail stays on the DB record, not
                                      # here. Whether v0.62.1 actually clears the set is NOT assumed: confirm on the next
                                      # security-check after the window (§3.3 closes F-73c160d1 only if the row is gone).
                                      # The accepted image-register row F-b81fe869 names v0.57.0 and is unrelated.
capability_change: false              # 0.62.x adds SPIFFE mTLS, object-identity field renames, a web-UI
                                      # nodes dashboard and source-watcher impersonation. None is
                                      # configured or reachable here: no spec.spiffe, multitenant off,
                                      # no HTTPRoute to :9080, source-watcher not a component, and the
                                      # impersonation change applies only to Flux >= 2.10. 0.62.1 only
                                      # narrows when the operator SPIFFE ID is authorized (mTLS-only path).
                                      # Rendered controllers byte-identical (1.5).
rollback_class: git-revert            # no forward-only step: no stored-version change, no data. The one
                                      # persisted side effect (the defaulted multitenantObjectIdentity
                                      # field) is pruned by the 0.61.0 CRD on read; section 5.
finding_refs:
  - F-73c160d1                        # security_ref above (image CVE row for the operator image v0.61.0)
  - F-60f2b033                        # flux-operator: chart 0.61.0 -> 0.62.1 (version, monitor)
  - F-703d6382                        # flux-instance: chart 0.61.0 -> 0.62.1 (version, monitor)
premises:
  # Read-verb only. All run 2026-10-29 at authoring.
  - id: operator-image-current
    why: >-
      current claims operator image v0.61.0. If it moved, the diffs in 1.4/1.5 and the helm
      revision numbers in section 5 are wrong - re-derive before running.
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
      Gate 4.5 asserts the distribution revision is UNCHANGED after the bump (0.62.x knows Flux
      2.10, which shipped 2026-10-26; the exact pin v2.9.6 must hold it back). The baseline digest
      must be the one measured at authoring.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.status.lastAppliedRevision}'
    expect_contains: "v2.9.6@sha256:57a1bc1dd355767dbce6a429dfe13fecb8c8cd2910543218861d897bac0d6f15"
  - id: distribution-pin-exact
    why: >-
      The no-controller-roll claim holds only while distribution.version is an exact v2.9.6. A
      semver range (2.x, >=2.9) would let the 0.62.1 operator resolve to v2.10.0 - a full
      controller roll this plan does not cover.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.spec.distribution.version}'
    expect_exact: v2.9.6
  - id: distribution-registry-upstream
    why: >-
      0.62.1 (#1087) changed embedded image digests ONLY for the controlplane ENTERPRISE v2.9.6
      variants. They are irrelevant only while the registry is upstream ghcr.io/fluxcd.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.spec.distribution.registry}'
    expect_exact: ghcr.io/fluxcd
  - id: identity-fields-compatible
    why: >-
      The 0.62.x FluxInstance CRD adds CEL rules over these fields (1.4). They pass only with
      multitenant off and multitenantWorkloadIdentity false; a different value means the
      flux-instance helm upgrade could be REJECTED by the apiserver - re-assess.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.spec.cluster.multitenant}{" "}{.spec.cluster.multitenantWorkloadIdentity}'
    expect_exact: false false
  - id: no-object-level-wid-field
    why: >-
      New CEL rule forbids objectLevelWorkloadIdentity together with objectIdentityRBAC; the
      ObjectLevelWorkloadIdentity code path also changed. Absent today - if it appears, re-read
      internal/builder/object_identity.go at v0.62.1.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.spec.cluster}' | grep -c ObjectLevel
    expect_exact: "0"
  - id: no-spiffe-spec
    why: >-
      SPIFFE is the headline 0.62.0 feature and the ONLY code path 0.62.1 changes
      (spiffeMTLSData); both are inert only while spec.spiffe is absent.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.spec}' | grep -c -i spiffe
    expect_exact: "0"
  - id: no-resourcesets
    why: >-
      The ResourceSet/RSIP controller changes in 0.62.0 (resourcesetinputprovider_controller.go
      rewrite, RSIP CRD delta) are inert ONLY because zero such objects exist.
    run: kubectl get resourcesets.fluxcd.controlplane.io,resourcesetinputproviders.fluxcd.controlplane.io -A -o name | wc -l | tr -d ' '
    expect_exact: "0"
  - id: operator-web-port-valid
    why: >-
      0.62.1 moved the WEB_SERVER_PORT parse BEFORE controller setup and exits(1) on a non-integer;
      the value also sets the new WebUIEnabled builder input. Must stay the integer 9080 measured
      at authoring (build output measured identical with and without web UI, 1.5).
    run: kubectl get deploy -n flux-system flux-operator -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="WEB_SERVER_PORT")].value}'
    expect_exact: "9080"
  - id: target-operator-chart-published
    why: The target operator chart must resolve from the OCI registry the HelmRepository points at.
    run: helm show chart oci://ghcr.io/controlplaneio-fluxcd/charts/flux-operator --version 0.62.1 | grep '^version:'
    expect_exact: "version: 0.62.1"
  - id: target-instance-chart-published
    why: Same, for the instance chart.
    run: helm show chart oci://ghcr.io/controlplaneio-fluxcd/charts/flux-instance --version 0.62.1 | grep '^version:'
    expect_exact: "version: 0.62.1"
  - id: cluster-reconciles-clean
    why: >-
      Gate 4.6 asserts notready=0 after the change; a pre-existing not-Ready object would make it
      fail for a reason this plan did not cause. Suspended objects excluded, as in FluxResourceNotReady.
    run: >-
      kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases.helm.toolkit.fluxcd.io -A
      -o jsonpath='{range .items[*]}{.spec.suspend}{"/"}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
      | grep -v -e '^true/' -e '^false/True$' -e '^/True$' | wc -l | tr -d ' '
    expect_exact: "0"          # 248 ks+hr total at authoring; databases/phpmyadmin was briefly not-Ready
                               # mid-upgrade and Ready a minute later - re-run once before treating as STOP
  - id: edit-anchor-unique
    why: The section 3.1 fallback sed must match exactly one line per helmrelease (run from the repo root).
    run: >-
      cat kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml
      kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml | grep -c '^      version: 0.61.0$'
    expect_exact: "2"
status: vetted                        # plan-reviewer 2026-11-03: ready-for-go; operator GO still required (SD-11 floor)
review: ready-for-go@2026-11-03
window: null                          # RECOMMENDED nightly:2026-11-07 (Saturday 03:30 Berlin). NOT the 2026-11-08 night (etcd-timeouts-5000-500
                                      # restarts etcd that same Sunday morning: attribution) and NOT 2026-11-10 (edot-collector-0.164.0 nightly).
                                      # helm-drift-detection has MOVED to sat-attended:2026-11-28, so 11-07 is no longer shared with it.
                                      # COLLISION to resolve: coredns-1.50.0 is recommended for the same night and the two are a
                                      # declared mutual conflict (70 of 70 min). One must move; the operator / scheduler decides.
                                      # Needs an operator GO either way (§1.6).
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/flux-upgrade.md
  - docs/sops/flux-image-automation-push-auth.md
  - docs/sops/maintenance-windows.md
  - docs/sops/disaster-recovery.md
generated: "2026-10-29"
---

# flux-fleet 0.61.0 -> 0.62.1 (flux-operator + flux-instance charts)

**Supersedes `flux-fleet-0.62.0`** (uncommitted draft, 2026-10-27, target 0.62.0). Renovate #257
retargeted to 0.62.1 the same day upstream published it. All research in that draft was
re-checked against 0.62.1. It still holds, and the 0.62.0 -> 0.62.1 delta is in 1.3. The 0.62.0
file must be set `status: superseded`. Until then both files claim PR #257 and both finding ids.

## 1. Summary & why held

### 1.1 What changes

Both halves of the Flux control-plane chart family move together in **one commit**, the
squash-merge of Renovate PR #257.

| HelmRelease (ns flux-system) | chart | effect of this bump (measured, 1.4) |
|---|---|---|
| `flux-operator` | 0.61.0 -> 0.62.1 | **operator pod rolls** to image `v0.62.1`. `fluxinstances` CRD schema grows (SPIFFE and object-identity fields, CEL rules). `resourcesetinputproviders` CRD has a 13-line delta. Everything else is labels only |
| `flux-instance` | 0.61.0 -> 0.62.1 | **labels only** (`helm.sh/chart`, `app.kubernetes.io/version`). FluxInstance spec byte-identical |

PR #257 also bumps `kubernetes/bootstrap/apps/helmfile.yaml` (both charts, 0.61.0 -> 0.62.1).
Flux does not reconcile that file, so the DR bootstrap stays in step and the cluster sees nothing.

**The distribution is NOT touched.** `instance.distribution.version: v2.9.6` stays, so the six
controllers keep their images. **Flux v2.10.0 shipped on 2026-10-26**, and operator 0.62.x is
the first line that can install it ("Add Flux 2.10 compatibility", #1082). Moving to 2.10 is a
separate, high-risk plan per `docs/sops/flux-upgrade.md`. This plan is its prerequisite, not its
substitute.

### 1.2 Why it was held, and the 0.62.0 release notes

The hold came from coverage.py: *"0.x release-line move (0.61 -> 0.62), the minor is the
breaking axis at major 0"*. That is a structural rule, not a detected breaking change.

**Upstream v0.62.0** (2026-10-26, `gh release view v0.62.0 -R controlplaneio-fluxcd/flux-operator`).
The non-dependabot items:
- source-watcher multitenant impersonation (#1058)
- OIDC log/fix (#1043, #1063)
- workload-identity docs (#1068, #1070)
- web nodes dashboard (#1062)
- *"[RFC-0014] operator: retire `ObjectLevelWorkloadIdentity` feature gate"* (#1078)
- Kubernetes 1.37 libs (#1079)
- Preact 11 / Tailwind 4 (#1080)
- *"rename obj-lvl wid to object identity"* (#1081)
- Flux 2.10 compatibility (#1082)
- SPIFFE mTLS for `FluxInstance` and Web UI (#1084)

None is labelled breaking. Scoped against this cluster (carried over from the 0.62.0 draft and
re-checked; nothing below is touched by 0.62.1):

- **#1078/#1081 (gate retirement, renames).** `internal/builder/workload_identity.go` became
  `object_identity.go`. The `>= 2.7.0 && < 2.10.0` branch (our v2.9.6) still emits
  `GetProfileObjectLevelWorkloadIdentity(allControllers, false)` and sets
  `RemovePermissionForCreatingServiceAccountTokens = true` when object identity is off. The
  "gate retired / RBAC added back" behaviour lives only in the `>= 2.10.0` branch. The old field
  names are still accepted as legacy.
- **#1058.** `GetProfileMultitenant` adds `source-watcher` only when `cluster.multitenant` is true
  AND the version is >= 2.10.0. Both are false here (premises `identity-fields-compatible`,
  `distribution-pin-exact`).
- **SPIFFE (#1084).** `ValidateAndApplySPIFFEConfig` returns nil immediately when
  `spec.spiffe == nil`. Premise `no-spiffe-spec`.
- **K8s 1.37 libs.** client-go 0.36.3 -> 0.37.1 and controller-runtime 0.24.1 -> 0.25.2, against
  apiserver `v1.36.0` (re-measured 2026-10-29). That is inside the supported +-1 skew.
- **Reconcile libraries.** fluxcd/pkg/ssa 0.77 -> 0.83, fluxcd/pkg/kustomize 1.39 -> 1.44. These
  are real deltas, which is why 1.5 is measured rather than argued.
- **Metrics reporter.** Only the `source_name` label changed, and only for HelmReleases with
  `spec.chart.kind: OCIRepository`, which none of ours use. Gate 4.3 reads the series count.
- **Notifier rewrite.** It adds an `action` annotation to operator events. There are zero
  notification-controller `Alert` objects (re-measured: `kubectl get alerts.notification.toolkit.fluxcd.io -A -o name | wc -l` -> `0`).

### 1.3 What 0.62.1 changes on top of 0.62.0 (new for this plan)

**Upstream v0.62.1** (published 2026-10-27 15:35 UTC, latest at authoring). It has exactly two PRs:

- **#1086 "[RFC-0014] operator: fix operator SPIFFE ID".** In 0.62.0 the operator was authorized
  in the controllers' mTLS flags under its SVID ID. In 0.62.1 it is authorized under the stable
  template-derived ID, and only when it has a SPIFFE Workload API source. It is added as an
  artifact client of source-controller/source-watcher only when the embedded Web UI is on. Read
  from the `v0.62.0...v0.62.1` compare:
  - `internal/builder/spiffe.go`: the only behavioural change is inside `spiffeMTLSData`. That
    function is called only under `if spiffe.MTLS != nil && spiffe.MTLS.Enabled`, which in turn
    sits after the `spec.spiffe == nil` early return. **It is inert here** (premise `no-spiffe-spec`).
  - `internal/controller/fluxinstance_controller.go`: the 0.62.0 call
    `r.SPIFFESource.GetX509SVID()` is removed. `build()` now sets
    `options.OperatorMTLSEnabled = r.SPIFFESource != nil` and `options.WebUIEnabled = r.WebUIEnabled`.
    Both are read only by `spiffeMTLSData`.
  - `cmd/operator/main.go`: the `WEB_SERVER_PORT` parse moved ahead of controller setup, so
    `WebUIEnabled = webServerPort > 0` can be passed in. A non-integer still exits(1), as before.
    Our value is `9080` (premise `operator-web-port-valid`), so `WebUIEnabled` is true, and that
    is inert without mTLS (measured in 1.5).
  - `config/crd/.../fluxinstances.yaml`: a **description-only** edit of
    `spiffe.mtls.componentIDTemplate`. No schema, default or CEL change. Confirmed by the
    rendered diff in 1.4.
- **#1087 "Release v0.62.1".** Version strings, plus new image digests for the
  **controlplane ENTERPRISE** v2.8.8/v2.9.6 variants (`ghcr.io/controlplaneio-fluxcd/{alpine,distroless,distroless-fips}/...`).
  Our FluxInstance uses `registry: ghcr.io/fluxcd` (premise `distribution-registry-upstream`), so
  those digests are never selected.

**Net:** 0.62.1 is a SPIFFE-only fix on a path this cluster does not take. It neither adds nor
removes risk relative to 0.62.0. Every risk statement of the 0.62.0 draft carries over unchanged.

### 1.4 Rendered chart diff with OUR values (re-measured for 0.62.1)

Measured 2026-10-29. I ran `helm pull` for 0.61.0, 0.62.0 and 0.62.1 of both charts, then
`helm template` with `app/helm-values.yaml` / `instance/helm-values.yaml` (`--include-crds` for
the operator), then `diff`.

- **flux-instance 0.61.0 -> 0.62.1:** 2 changed lines (`helm.sh/chart`, `app.kubernetes.io/version`).
  51 lines rendered at each version.
- **flux-operator 0.61.0 -> 0.62.1:** 330 changed lines (0.61.0 -> 0.62.0 was 326). No object is
  added or removed. The non-label deltas:
  - `Deployment/flux-operator`: the image `...flux-operator:v0.61.0 -> v0.62.1`, and nothing else.
    The `spiffe.*` and `web.authorizedClientSPIFFEIDs` values default to empty and render nothing.
  - `CRD/fluxinstances`: adds `spec.spiffe`, `cluster.objectIdentityRBAC` and
    `cluster.multitenantObjectIdentity` (`default: false`), plus the cluster-level and spec-level
    CEL rules. Evaluated against the live spec (`multitenant: false`,
    `multitenantWorkloadIdentity: false`, no `objectLevelWorkloadIdentity`, no
    `objectIdentityRBAC`, no `spiffe`), **all rules pass**. The premises pin each input.
  - `CRD/resourcesetinputproviders`: 13 lines. There are 0 objects of this kind.
- **0.62.0 -> 0.62.1 (operator):** only the `componentIDTemplate` description block (6 -> 10
  lines) and the image tag. **0.62.0 -> 0.62.1 (instance):** the two label lines only.

### 1.5 Will the six controllers re-render? Measured with the v0.62.1 builder: NO

`flux-operator build instance` exposes the operator's own builder as a CLI. On 2026-10-29 I ran
the **v0.61.0 and v0.62.1 darwin_arm64 CLIs** (GitHub release assets) against the **live
FluxInstance spec**, reduced to apiVersion/kind/name/namespace/spec:

| build | lines | `diff` vs v0.61.0 |
|---|---|---|
| v0.61.0 | 7585 | - |
| v0.62.1 | 7585 | empty (byte-identical) |
| v0.62.1 `--operator-web-ui-enabled` (the new 0.62.1 flag mirroring our `WEB_SERVER_PORT=9080`) | 7585 | empty (byte-identical) |

All three builds used the same `flux-operator-manifests:latest` artifact that the live
FluxInstance pulls. The expected outcome is a server-side-apply no-op for the controllers:
**no controller restart**. Gate 4.4 turns this into a check that fails if it is wrong (for
example, if the newer SSA library's normalisation re-applied a pod template).

**Verdict:** the hold is a **false positive for breakage**. What remains is blast radius and a
larger-than-usual operator binary delta. The last identical-shape run (0.57 -> 0.61, executed
`now:2026-10-21`, `23a89557`) passed every gate this plan re-uses. Hence risk medium, one commit,
and gates that read what the operator reports.

### 1.6 Execution class (why there is no `autonomy_override`)

The derived class is AUTO-NIGHT (`capability_change: false` + `git-revert` + no reboot). But
`shared: [flux]` is in the SD-11 in-code floor, and `risk: medium` does not qualify for SD-10, so
**an operator GO is still required**. The GO does not need an attended slot: with a GO this can
run in any window, `nightly` included. I deliberately left out `autonomy_override: human-gated`,
because per F-1ce18da8 that made the 0.60.0 plan's nightly-scoped GO lapse for five nights.

**Recommended slot (refreshed 2026-11-03):** `nightly:2026-11-07`, after an operator GO. It is
before `etcd-timeouts-5000-500` (`sun-attended:2026-11-08`), so that plan's etcd restarts cannot
blur this plan's gates (do not take the 11-08 night, which ends hours before it). It is also
clear of `helm-drift-detection` (now `sat-attended:2026-11-28`), `talos-linux-1.14.5`
(`sun-attended:2026-11-22`, the exclusive node roll that replaced the superseded
`talos-linux-1.14.2`), `flux-oci-chart-sources` (`sun-attended:2026-12-13`) and
`edot-collector-0.164.0` (`nightly:2026-11-10`; avoid the 11-10 night). Avoid any night on which
kube-prometheus-stack (#428, now 92.11.1 -> 92.17.1) lands in Step 0 (see 6). Conflict to
resolve before stamping the window: `coredns-1.50.0` is recommended for the same night and is a
declared `conflicts_with` in BOTH directions (70 of 70 usable nightly min, and this plan's revert
path depends on CoreDNS).

**Security driver.** `security_ref: F-73c160d1` (see the frontmatter): the operator image this plan
retires carries an open, fixable-HIGH image row with a newer upstream tag available. That raises
this plan's urgency but not its risk class: it stays `risk: medium`, GO required. After the window,
the next security-check must be read to see whether the row cleared; do not claim it from the bump alone.

## 2. Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` in zsh. If any check fails, stop and do not merge.

```bash
cd /Users/mu/code/cberg-home-nextgen
# a) premises (all 15 must PASS)
.venv/bin/python3 runbooks/plan-premises.py flux-fleet-0.62.1 --require-premises

# a2) the superseded draft is not also in the window
grep -m1 '^status:' runbooks/maintenance/plans/flux-fleet-0.62.0.md 2>/dev/null || echo "0.62.0 file absent"
# PASS: "status: superseded" or "0.62.0 file absent". "status: draft|vetted|scheduled" -> STOP: mark it first.

# b) PR 257 is still exactly the three-file 0.61.0 -> 0.62.1 bump, and green
gh pr view 257 --json state,mergeable,files,statusCheckRollup \
  -q '"\(.state) \(.mergeable) files=\([.files[].path]|join(",")) checks=\([.statusCheckRollup[]|(.conclusion//.state)]|unique|join(","))"'
# PASS: "OPEN MERGEABLE files=kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml,
#        kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml,kubernetes/bootstrap/apps/helmfile.yaml checks=SUCCESS"
gh pr diff 257 | grep -c '^+.*version: 0.62.1$'      # PASS: 4 (measured 4 at authoring)
gh pr diff 257 | grep -c '^-.*version: 0.61.0$'      # PASS: 4
# If Renovate has retargeted the PR again (e.g. 0.62.2 / 0.63.0) or it is closed: STOP, the plan needs a refresh.

# c) upstream has not yanked or superseded v0.62.1 since authoring
gh release view v0.62.1 -R controlplaneio-fluxcd/flux-operator --json isPrerelease,isDraft -q '"\(.isPrerelease) \(.isDraft)"'   # PASS: false false
gh release list -R controlplaneio-fluxcd/flux-operator --limit 2      # informational: anything newer than v0.62.1 -> read its notes first

# d) repo is at the revision Flux has applied (no in-flight reconcile of a newer commit)
git fetch -q origin
kubectl get gitrepository flux-system -n flux-system -o jsonpath='{.status.artifact.revision}{"\n"}'
git rev-parse origin/main
# PASS: the sha in the artifact revision equals origin/main.

# e) snapshot known-good state OUTSIDE the repo (used by 4.4, 4.5 and section 5)
mkdir -p /tmp/flux-fleet-0621 && cd /tmp/flux-fleet-0621
kubectl get deploy -n flux-system source-controller kustomize-controller helm-controller \
  notification-controller image-reflector-controller image-automation-controller \
  -o jsonpath='{range .items[*]}{.metadata.name}{" gen="}{.metadata.generation}{" img="}{.spec.template.spec.containers[0].image}{"\n"}{end}' \
  > ctrl-before.txt
kubectl get pods -n flux-system -l 'app in (source-controller,kustomize-controller,helm-controller,notification-controller,image-reflector-controller,image-automation-controller)' \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.startTime}{"\n"}{end}' > ctrl-pods-before.txt
wc -l ctrl-before.txt ctrl-pods-before.txt        # PASS: 6 and 6 (all six gen=3 at authoring)
kubectl get deploy -n flux-system flux-operator -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}' > operator-before.txt
kubectl get fluxinstance -n flux-system flux -o jsonpath='{.status.lastAppliedRevision}{"\n"}' > fi-rev-before.txt
kubectl get crd fluxinstances.fluxcd.controlplane.io fluxreports.fluxcd.controlplane.io \
  resourcesets.fluxcd.controlplane.io resourcesetinputproviders.fluxcd.controlplane.io -o yaml > operator-crds-before.yaml
helm history flux-operator -n flux-system --max 3 > helm-op-before.txt
helm history flux-instance -n flux-system --max 3 > helm-inst-before.txt
tail -1 helm-op-before.txt; tail -1 helm-inst-before.txt
# EXPECT (re-measured 2026-10-29): flux-operator rev 4 deployed flux-operator-0.61.0;
#                                  flux-instance rev 8 deployed flux-instance-0.61.0.
# If the numbers differ, write the real ones down: section 5 step 2 uses them.
cd /Users/mu/code/cberg-home-nextgen

# f) Prometheus baseline for the flux_* instrument (port-forward by PID, never kill %1)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
pq() { curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "EMPTY")'; }
pq 'count(flux_resource_info)' | tee /tmp/flux-fleet-0621/series-before.txt   # 425 on 2026-10-29
pq 'count(count by (kind) (flux_resource_info))'                              # PASS: 10 (measured 10)
pq 'count(flux_resource_info{ready="False",suspended="False"})'               # PASS: EMPTY
pq 'count(flux_operator_info{version="v0.61.0"})'                             # PASS: 1
pq 'count(flux_operator_info{version="v0.62.1"})'                             # PASS: EMPTY  <- negative control for gate 4.2
pq 'max_over_time(count(flux_resource_info{ready="False",suspended="False"})[14d:10m])'   # POSITIVE CONTROL for 4.6: must be non-EMPTY (46 on 2026-10-29); EMPTY -> the ready="False" gate cannot fail, STOP
pq 'count(count_over_time(ALERTS{alertname="FluxResourceNotReady"}[14d]))'    # POSITIVE CONTROL for the 4.6 ALERTS gate: non-EMPTY (693 on 2026-10-29); EMPTY -> retry [30d]; still EMPTY -> 4.6 ALERTS line informational only
pq 'count(ALERTS{alertname=~"Flux.*",alertstate="firing"})'                   # PASS: EMPTY
pq 'max(container_memory_working_set_bytes{namespace="flux-system",container="manager",pod=~"flux-operator-.*"})' | tee /tmp/flux-fleet-0621/opmem-before.txt   # 192438272 (~184 MiB) at authoring; limit 1Gi
kill $PF 2>/dev/null
# Fleet-size baseline for gate 4.6 (never compare against a hardcoded total; 248 at authoring)
kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases.helm.toolkit.fluxcd.io -A -o json \
  | python3 -c 'import sys,json; it=json.load(sys.stdin)["items"]; bad=[i["metadata"]["namespace"]+"/"+i["metadata"]["name"] for i in it if not i["spec"].get("suspend") and not any(c["type"]=="Ready" and c["status"]=="True" for c in i.get("status",{}).get("conditions",[]))]; print("total=%d notready=%d %s" % (len(it), len(bad), bad))' | tee /tmp/flux-fleet-0621/total-before.txt
# PASS: notready=0. The total= value is the 4.6 baseline. A single object mid-upgrade (seen once at
# authoring: databases/phpmyadmin, Ready one minute later) -> wait 2 min and re-run before STOP.

# g) push path works (the rollback is a push)
git push --dry-run origin main && echo PUSH_OK
```

**Not done, and why.** SOP `flux-upgrade.md` step 2 sets `retries: 0` / `cleanupOnFail: false`
so that helm remediation cannot half-revert a **six-controller roll**. No controller rolls here
(1.5). The only workload that rolls is the operator Deployment, and an automatic helm rollback
of it to 0.61.0 is the failure mode we want, not a hazard. Gate 4.1 detects one if it happens.

**mise note (2026-10-29).** `mise exec` currently prints `failed to write cache file ...
Permission denied` because `~/Library/Caches/mise/aqua-*` contains root-owned dirs. The commands
above call the mise-installed `kubectl`/`helm`/`flux` directly from PATH, so they work. If a
wrapper insists on `mise exec`, the warnings are noise, not a failure.

## 3. Steps

### 3.1 The coordinated bump: merge PR #257 (one squash commit, three files)

```bash
cd /Users/mu/code/cberg-home-nextgen
gh pr merge 257 --squash --delete-branch
git fetch -q origin
git log -1 --format='%H %s' origin/main | tee /tmp/flux-fleet-0621/core.txt
git show --stat origin/main | tail -5
# MUST list exactly: app/helmrelease.yaml, instance/helmrelease.yaml, bootstrap/apps/helmfile.yaml (3 files, 4 +/4 -)
# and the subject MUST contain "0.62.1".
cut -d' ' -f1 /tmp/flux-fleet-0621/core.txt > /tmp/flux-fleet-0621/core-sha.txt
git pull --ff-only     # shared worktree: if this refuses because of others' local changes, do NOT stash theirs;
                       # the cluster reconciles from origin, the local checkout only matters for 3.3
```

**Fallback, ONLY if PR #257 is unmergeable (conflict) or was closed:** apply the same edit
directly. I dry-tested it on scratch copies on macOS (BSD sed) on 2026-10-29. Resulting diff:
`12c12 <       version: 0.61.0 >       version: 0.62.1` in each helmrelease, and
`41c41` / `48c48 <     version: 0.61.0 >     version: 0.62.1` in helmfile.yaml.

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's/^      version: 0\.61\.0$/      version: 0.62.1/' \
  kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml \
  kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml
sed -i '' -e '/charts\/flux-operator$/{n;s/^    version: 0\.61\.0$/    version: 0.62.1/;}' \
          -e '/charts\/flux-instance$/{n;s/^    version: 0\.61\.0$/    version: 0.62.1/;}' \
  kubernetes/bootstrap/apps/helmfile.yaml
git diff --stat -- kubernetes/apps/flux-system/flux-operator/ kubernetes/bootstrap/apps/helmfile.yaml   # EXPECT: 3 files, 4 insertions, 4 deletions
kubeconform -summary -ignore-missing-schemas kubernetes/apps/flux-system/flux-operator/
mkdir -p /tmp/flux-fleet-0621
cat > /tmp/flux-fleet-0621/msg-core.txt <<'EOF'
feat(flux): flux-operator + flux-instance charts 0.61.0 -> 0.62.1 (plan flux-fleet-0.62.1)

Operator image v0.61.0 -> v0.62.1. Distribution stays v2.9.6; rendered
FluxInstance spec unchanged and controller manifests byte-identical
(flux-operator build instance, v0.61.0 vs v0.62.1 CLIs). Supersedes
Renovate #257. Findings F-60f2b033 F-703d6382.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml \
  kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml \
  kubernetes/bootstrap/apps/helmfile.yaml -F /tmp/flux-fleet-0621/msg-core.txt
git log -1 --format=%s          # MUST be the subject above (shared-worktree message swap guard); amend if not
git show --stat HEAD            # MUST list exactly the three files
git rev-parse HEAD > /tmp/flux-fleet-0621/core-sha.txt
git push origin main
gh pr close 257 --comment "Applied directly by plan flux-fleet-0.62.1 ($(cat /tmp/flux-fleet-0621/core-sha.txt))"
```

### 3.2 Propagation (observe; do not force unless stalled)

The chain is: webhook -> `Receiver` -> GitRepository `flux-system` -> Kustomizations
`flux-operator` and `flux-instance` -> helm-controller. helm-controller upgrades
`hr/flux-operator` first (CRDs updated, operator pod rolls), then `hr/flux-instance`
(`dependsOn: flux-operator`).

```bash
for i in $(seq 1 20); do
  R=$(kubectl get hr -n flux-system flux-operator flux-instance -o jsonpath='{.items[*].status.history[0].chartVersion}')
  echo "$(date +%T) $R"; [ "$R" = "0.62.1 0.62.1" ] && break; sleep 30
done
[ "$R" = "0.62.1 0.62.1" ] && echo PROPAGATED || echo "PROPAGATION_NOT_COMPLETE after 10 min -> run the reconcile block below"
```

If the source revision has not reached the core sha after 10 minutes, the webhook did not fire.
For that case, `docs/sops/flux-upgrade.md` section 4 step 4 prescribes an ordered reconcile. Run
it only then:

```bash
flux reconcile source git flux-system -n flux-system
flux reconcile ks flux-operator -n flux-system && flux reconcile hr flux-operator -n flux-system
flux reconcile ks flux-instance -n flux-system && flux reconcile hr flux-instance -n flux-system
```

`hr/flux-instance` may go `Ready=False` with a message containing `x-kubernetes-validations` or
`Invalid value`. That means a CEL rule from 1.4 rejected the FluxInstance. It is not an outage:
the old FluxInstance object stays in place and the controllers keep running. Go to section 5
step 1.

### 3.3 Follow-up commit (ONLY after section 4 is fully green)

`docs/infrastructure.md` still says 0.61.0 in three places. I dry-tested the edit on a scratch
copy (BSD sed) on 2026-10-29. Diff: lines `111,112` change `| 0.61.0 | flux-system |` to
`| 0.62.1 | flux-system |`, and line `134` changes `(flux-operator/flux-instance chart 0.61.0)`
to `(... chart 0.62.1)`.

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' -e 's#^\(| [45] | Flux [A-Za-z]* | `oci://ghcr.io/controlplaneio-fluxcd/charts/flux-[a-z]*` | \)0\.61\.0 |#\10.62.1 |#' \
          -e 's#(flux-operator/flux-instance chart 0\.61\.0)#(flux-operator/flux-instance chart 0.62.1)#' \
  docs/infrastructure.md
git diff --stat -- docs/infrastructure.md   # EXPECT: 1 file, 3 insertions, 3 deletions
cat > /tmp/flux-fleet-0621/msg-docs.txt <<'EOF'
docs(flux): infrastructure.md to flux charts 0.62.1

No cluster effect. Plan flux-fleet-0.62.1.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git commit --only docs/infrastructure.md -F /tmp/flux-fleet-0621/msg-docs.txt
git log -1 --format=%s && git show --stat HEAD && git push origin main
```

Then retire this plan file per `runbooks/maintenance/plans/README.md`, along with the superseded
`flux-fleet-0.62.0.md` if it still exists. Close both findings with the core sha:
`runbooks/policy-cli.py finding close F-60f2b033 --commit <core-sha>`, and the same for
F-703d6382.

## 4. Verification

Run the gates in order. Each one says what its failure prints. First re-establish the Prometheus
port-forward (the `PF=$!` form from 2 f) and re-define `pq`. The operator restart does not break
this port-forward, because it targets Prometheus, not the operator.

### 4.1 Both releases deployed at 0.62.1, no remediation rollback

```bash
kubectl get hr -n flux-system flux-operator flux-instance \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.history[0].chartVersion}{" "}{.status.history[0].status}{" "}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
helm history flux-operator -n flux-system --max 2
helm history flux-instance -n flux-system --max 2
```
- **PASS:**
  - `flux-instance 0.62.1 deployed True` and `flux-operator 0.62.1 deployed True`;
  - helm's latest revisions are 5 (`flux-operator-0.62.1`, "Upgrade complete") and 9
    (`flux-instance-0.62.1`).
- **FAIL looks like:**
  - chartVersion `0.61.0` with a newer revision described as `Rollback to 4` (remediation fired);
  - Ready `False` with `upgrade retries exhausted`;
  - a CEL `Invalid value` message on flux-instance (see 3.2).

### 4.2 The operator serving metrics IS the new build

```bash
kubectl get deploy -n flux-system flux-operator -o jsonpath='{.spec.template.spec.containers[0].image}{" avail="}{.status.availableReplicas}{"\n"}'
kubectl get pods -n flux-system -l app.kubernetes.io/name=flux-operator \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.phase}{" restarts="}{.status.containerStatuses[0].restartCount}{"\n"}{end}'
sleep 60   # one scrape interval after the new pod is Ready
pq 'count(flux_operator_info{version="v0.62.1"})'
pq 'count(flux_operator_info{version="v0.61.0"})'
kubectl logs deploy/flux-operator -n flux-system --since=10m | grep -c -i -e '"level":"error"' -e 'panic' -e 'unable to parse web server port'
```
- **PASS:**
  - the image reads `...flux-operator:v0.62.1 avail=1`;
  - there is exactly one pod, `Running restarts=0`;
  - `flux_operator_info` returns `1` for `v0.62.1` and `EMPTY` for `v0.61.0`;
  - the error/panic count is `0`.
- **FAIL looks like:**
  - `v0.62.1` -> `EMPTY`. This gate can fail: at authoring this exact query returned `EMPTY`
    and the `v0.61.0` query returned `1`.
  - `EMPTY` for BOTH versions: the scrape itself is broken (ServiceMonitor/port). Treat it as
    FAIL and go to 4.3.
  - a CrashLoop with `unable to parse web server port`: the moved 0.62.1 parse (1.3).
  - any other non-zero log count: read the lines. A logged error is not automatically a revert.
    If 4.3-4.6 pass, record it and decide with the operator.

CONTROL: metric flux_operator_info: the `count` with `version="v0.62.1"` must be exactly 1 after the roll, and the v0.61.0 series must be gone.

### 4.3 The operator still reports the whole fleet (contents, not shape)

```bash
pq 'count(flux_resource_info)'; cat /tmp/flux-fleet-0621/series-before.txt
pq 'count by (kind) (flux_resource_info)'
```
CONTENTS ASSERTION: the operator's report of every Flux object is complete. It is measured by
`count(flux_resource_info)` against the 2 f baseline (425 at authoring).

- **PASS:** the count is within +/-5 of the baseline AND all 10 kinds are present: HelmRelease,
  HelmChart, HelmRepository, Kustomization, GitRepository, OCIRepository, Receiver, ImagePolicy,
  ImageRepository, ImageUpdateAutomation.
- **FAIL looks like:**
  - `EMPTY`: the reporter or the scrape is broken. Here an empty result is a FAIL, never a pass.
  - a count far below the baseline: the 0.62 reporter rewrite regressed, and this is the gate
    that sees it.
  - a missing kind.

CONTROL: metric flux_resource_info: the `count()` floor is baseline-5, with all 10 kinds present. This series is also the input to FluxResourceNotReady / FluxSourceStalled / FluxMetricsAbsent.

### 4.4 The six controllers did NOT roll (the plan's central claim)

```bash
kubectl get deploy -n flux-system source-controller kustomize-controller helm-controller \
  notification-controller image-reflector-controller image-automation-controller \
  -o jsonpath='{range .items[*]}{.metadata.name}{" gen="}{.metadata.generation}{" img="}{.spec.template.spec.containers[0].image}{"\n"}{end}' \
  | diff /tmp/flux-fleet-0621/ctrl-before.txt - && echo CONTROLLERS_UNCHANGED
kubectl get pods -n flux-system -l 'app in (source-controller,kustomize-controller,helm-controller,notification-controller,image-reflector-controller,image-automation-controller)' \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.startTime}{"\n"}{end}' \
  | diff /tmp/flux-fleet-0621/ctrl-pods-before.txt - && echo CONTROLLER_PODS_UNCHANGED
```
- **PASS:** both `..._UNCHANGED` lines print.
- **FAIL looks like:** a `diff` hunk showing `gen=4` or a new pod name/startTime. That means the
  0.62.1 operator re-applied the controllers, which contradicts 1.5. The likely cause is the SSA
  library bump (0.77 -> 0.83), or the WebUIEnabled input if `spec.spiffe` was somehow set.
- **On FAIL:** this alone is not an outage (check 4.6), but the plan's premise is falsified.
  Stop, record the diff, do not proceed to 3.3, and decide revert-vs-keep with the operator.
- This gate can fail: `diff` against the snapshot is an exact-string compare, so any digest or
  generation change prints.

### 4.5 FluxInstance applied the SAME distribution, spec intact

```bash
kubectl get fluxinstance -n flux-system flux \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{" "}{.status.lastAppliedRevision}{"\n"}'
cat /tmp/flux-fleet-0621/fi-rev-before.txt
kubectl get fluxinstance -n flux-system flux -o jsonpath='{.spec.sync.pullSecret}{"|"}{.spec.distribution.version}{"|"}{.status.spiffe}{"\n"}'
kubectl get gitrepository flux-system -n flux-system -o jsonpath='{.spec.secretRef.name}{"|"}{.spec.ignore}{"\n"}'
pq 'count(flux_instance_info{ready="True",revision="v2.9.6@sha256:57a1bc1dd355767dbce6a429dfe13fecb8c8cd2910543218861d897bac0d6f15"})'
```
- **PASS:**
  - the first line reads `True v2.9.6@sha256:57a1bc1d...`, identical to the saved revision;
  - the second reads `flux-system-git-auth|v2.9.6|` (empty `status.spiffe`);
  - the GitRepository shows `flux-system-git-auth|` followed by an ignore block containing
    `!/kubernetes`;
  - the PromQL returns `1` (re-measured `1` on 2026-10-29).
- **FAIL looks like:**
  - any `v2.10` revision. The operator moved the distribution, which is a full controller roll
    this plan does not cover. Revert immediately.
  - an empty `pullSecret` (the silent-prune failure in `docs/sops/flux-image-automation-push-auth.md`);
  - an ignore block without `!/kubernetes`;
  - a non-empty `status.spiffe`.

CONTROL: metric flux_instance_info: the `count` with ready="True" and the exact v2.9.6 digest revision label must be 1.

### 4.6 The cluster still reconciles end to end (10-minute soak)

```bash
sleep 600
kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases.helm.toolkit.fluxcd.io -A -o json \
  | python3 -c 'import sys,json; it=json.load(sys.stdin)["items"]; bad=[i["metadata"]["namespace"]+"/"+i["metadata"]["name"] for i in it if not i["spec"].get("suspend") and not any(c["type"]=="Ready" and c["status"]=="True" for c in i.get("status",{}).get("conditions",[]))]; print("total=%d notready=%d %s" % (len(it), len(bad), bad))' | tee /tmp/flux-fleet-0621/total-after.txt
cat /tmp/flux-fleet-0621/total-before.txt
pq 'count(flux_resource_info{ready="False",suspended="False"})'
pq 'count(ALERTS{alertname=~"FluxResourceNotReady|FluxSourceStalled|FluxMetricsAbsent",alertstate=~"pending|firing"})'
pq 'max(container_memory_working_set_bytes{namespace="flux-system",container="manager",pod=~"flux-operator-.*"})'; cat /tmp/flux-fleet-0621/opmem-before.txt
kubectl get ks -n flux-system flux-system cluster-apps flux-operator flux-instance \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.lastAppliedRevision}{"\n"}{end}'
kill $PF 2>/dev/null
```
- **PASS:**
  - `notready=0`, and `total` is within +/-3 of the 2 f baseline (NOT a hardcoded number; 248 at
    authoring);
  - both of the first two PromQL lines return `EMPTY`. That counts as a pass only because 4.3
    proved the series exist and the 2 f positive controls proved both queries can match;
  - operator memory is below 512 MB (baseline ~184 MiB, limit 1Gi; the 0.62 nodes dashboard runs
    on the always-on :9080 web server);
  - all four Kustomizations show `refs/heads/main@sha1:<core sha or later>`.
- **FAIL looks like:**
  - `notready=N [ns/name...]`;
  - a non-empty ALERTS count;
  - memory approaching the limit (OOM risk), which needs an operator decision;
  - a Kustomization still on the pre-change sha (reconciliation stalled).
- FluxMetricsAbsent has `for: 30m` and cannot fire inside this window. The 4.3 floor is what
  actually guards the metric path.

CONTROL: alertname FluxResourceNotReady: must not be pending or firing after the soak.
CONTROL: alertname FluxSourceStalled: must not be pending or firing (it would mean the GitRepository cannot fetch, so nothing deploys).
CONTROL: alertname FluxMetricsAbsent: must not be firing. Informational within the window (30m `for`); 4.3 covers it.

## 5. Rollback

Nothing in this plan is forward-only. There is no stored-version change and no data. The only
persisted side effect: under the 0.62.1 CRD, the apiserver defaults
`spec.cluster.multitenantObjectIdentity: false` into the stored FluxInstance on its next write.
After a downgrade, the 0.61.0 CRD's structural schema drops that unknown field on read, and
0.61.0 never reads it. The 3.3 docs commit has no cluster effect and never needs reverting for
recovery.

**Trigger:** any of 4.1-4.3 or 4.5-4.6 FAILs, or 4.4 FAILs together with any 4.6 failure.

1. **GitOps revert (preferred).** The controllers never rolled, so Flux is fully able to apply it.
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git fetch -q origin && git pull --ff-only
   git revert --no-edit $(cat /tmp/flux-fleet-0621/core-sha.txt)
   git log -1 --format=%s && git show --stat HEAD     # the three PR-257 files only
   git push origin main
   ```
   helm-controller downgrades both releases to 0.61.0 (new revisions, e.g. 6 and 10). The
   operator pod rolls back to v0.61.0 and the CRDs return to the 0.61.0 schema. Renovate will
   reopen a PR for 0.62.x. Leave it unmerged and set this plan to `blocked` with the failure.
2. **Flux-independent.** Use this only if the operator or helm-controller is wedged and step 1
   has not converged within 10 minutes.
   ```bash
   for hr in flux-operator flux-instance; do kubectl patch hr $hr -n flux-system --type merge -p '{"spec":{"suspend":true}}'; done
   helm rollback flux-operator 4 -n flux-system    # rev numbers from /tmp/flux-fleet-0621/helm-op-before.txt
   helm rollback flux-instance 8 -n flux-system    # and helm-inst-before.txt
   # still crashlooping? pin the known-good image recorded in operator-before.txt:
   kubectl set image deploy/flux-operator -n flux-system manager=$(cat /tmp/flux-fleet-0621/operator-before.txt)
   ```
   Then make git match (push the step 1 revert) and un-suspend both HRs
   (`kubectl patch hr $hr -n flux-system --type merge -p '{"spec":{"suspend":false}}'`). If even
   this fails, follow `docs/sops/disaster-recovery.md`. The container name `manager` was
   verified live on 2026-10-27, and the helm revisions 4 and 8 were re-verified on 2026-10-29.
3. **Confirm the cluster is back.**
   - Re-run 4.1, expecting `0.61.0 deployed True` for both.
   - Re-run 4.2, expecting `flux_operator_info{version="v0.61.0"}` -> `1` and `v0.62.1` -> `EMPTY`.
   - 4.3, 4.5 and 4.6 keep their PASS criteria unchanged.
   - `/tmp/flux-fleet-0621/operator-crds-before.yaml` is for one case only: a schema mismatch
     blocking the 0.61.0 operator. That is not expected, because 0.62.x only ADDS fields and
     rules. In that case alone, apply it with `kubectl apply -f`.

## 6. Interference notes

- **Supersedes `flux-fleet-0.62.0`.** It touched the same files and PR and claimed the same
  `finding_refs`. It is now `status: superseded` (2026-11-03, pointing at this plan) and is no longer
  in `conflicts_with`. Other plans still name it as a neighbour (`talos-linux-1.14.5`,
  `flux-oci-chart-sources`, `edot-collector-0.164.0`; they name `-0.62.1` as well): those are
  their text, not this plan's, and `maintenance-plan.py --validate` is the arbiter for dead refs.
- **talos-linux-1.14.5** (`sun-attended:2026-11-22`, exclusive) and **coredns-1.50.0** are now in
  `conflicts_with` (see the frontmatter); the stale reference to the superseded `talos-linux-1.14.2`
  elsewhere in this file means 1.14.5.
- **Control plane, but not a controller roll.** Only `deployment/flux-operator` restarts
  (~30-60 s). The source/kustomize/helm/notification/image controllers keep reconciling other
  plans' commits throughout, which is why this plan is not `exclusive`. If 4.4 shows otherwise,
  treat the window as having had a full controller roll: expect a transient `artifact not found`
  for about one interval, per `docs/sops/flux-upgrade.md` Test 2.
- **The instrument restarts.** Every Flux alert reads `flux_*` series from the operator pod, so
  its restart leaves a scrape gap of about one interval. Of the open plans, only
  `flux-reconciler-impersonation` reads `flux_*` in its verification, and it is in
  conflicts_with. No `kube-prometheus-stack` plan is open, but **Renovate #428
  (kube-prometheus-stack 92.11.1 -> 92.17.1, retargeted since authoring) is open**. If a window's Step 0 lands it the same
  night, run this plan's gates only after Prometheus is back Ready, and re-take the 2 f baseline.
- **Flux v2.10.0 is out (2026-10-26), and Renovate #448 (open) bumps the `flux` CLI pin to
  2.10.0.** This plan keeps the distribution at v2.9.6 (premise `distribution-pin-exact`, gate
  4.5). Repo note for the operator: merging #448 before a distribution-2.10 plan runs would break
  the CLI/distribution match that `docs/sops/flux-upgrade.md` section 2 asks for. A future
  `flux-distribution-2.10.0` plan should `depends_on: [flux-fleet-0.62.1]`.
- **flux-reconciler-impersonation** is blocked and unwindowed. Its premise `operator-v0.57.0` is
  already stale (live is v0.61.0); after this plan it should read `v0.62.1`. Its owner must
  re-read `internal/builder/profiles.go` and `object_identity.go` at v0.62.1 first, because
  `GetProfileMultitenant` gained a version argument. For v2.9.x and our non-multitenant spec the
  effect is identical (1.2).
- **helm-drift-detection** (`sat-attended:2026-11-28`, moved from 11-07 on 2026-11-02) adds `spec.driftDetection` to these two
  HRs as well. Its premise `helm-controller-is-v1.6.x` stays true after this plan, because the
  controllers are byte-identical (4.4). Run this plan first, or in a different night.
- **flux-oci-chart-sources** (`sun-attended:2026-12-13`, re-scheduled) may move these two HRs' chart source to
  an `OCIRepository`. If it runs first, the 3.1 edit target changes and this plan must be
  refreshed.
- **etcd-timeouts-5000-500** (`sun-attended:2026-11-08`) perturbs the apiserver/etcd. It is in
  conflicts_with for attribution only.
- **Step 0 interplay.** coverage.py lists this group under `needs_plan_groups`, so the safe-update
  lane will neither auto-merge #257 nor direct-bump these files. The window must not merge #257
  outside this plan.
- **Out of scope, deliberately:** the distribution bump, the `.mise.toml` flux CLI pin (#448), and
  adopting any 0.62 feature (SPIFFE, the objectIdentityRBAC rename, web-UI exposure).
