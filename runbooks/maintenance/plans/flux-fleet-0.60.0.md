---
plan_id: flux-fleet-0.60.0
component: flux-fleet                 # chart-family group: flux-operator + flux-instance (ns flux-system)
pr: null                              # No Renovate PR. Dispatched by the nightly window 2026-09-28
                                      # Step 0.5 from coverage.py needs_plan_groups.
kind: chart
current: "flux-operator chart 0.57.0 (operator image v0.57.0) + flux-instance chart 0.57.0; FluxInstance distribution v2.9.3 (unchanged by this plan)"
target: "flux-operator chart 0.60.0 (operator image v0.60.0) + flux-instance chart 0.60.0; distribution stays v2.9.3"
update_type: minor                    # 0.x line: 0.57 -> 0.60 is three "minors" at major 0
risk: medium                          # NOT from the diff, which is measured trivial (section 1.2).
                                      # From the blast radius: this is the reconcile engine, and the
                                      # flux-operator pod is ALSO the only exporter of flux_* metrics
                                      # that every Flux alert reads. Low would route it to SD-10
                                      # unattended pre-approval; the control plane does not go there
                                      # on a first run.
est_duration_min: 35                  # pre-checks 8 + edit/commit/push 3 + propagate/roll 8 +
                                      # verification 12 (includes a 10-min not-ready soak) + docs
                                      # follow-up commit 4.
needs_reboot: false
touches:
  namespaces: [flux-system]
  resources:
    - helmrelease/flux-operator (flux-system)          # chart 0.57.0 -> 0.60.0; helm rev 3 -> 4
    - helmrelease/flux-instance (flux-system)          # chart 0.57.0 -> 0.60.0; helm rev 6 -> 7
    - deployment/flux-operator (flux-system)           # ROLLS: image v0.57.0 -> v0.60.0 (1 replica)
    - crd/resourcesets.fluxcd.controlplane.io          # gains one CEL rule; 0 objects exist
    - crd/fluxinstances.fluxcd.controlplane.io         # labels only
    - crd/fluxreports.fluxcd.controlplane.io           # labels only
    - crd/resourcesetinputproviders.fluxcd.controlplane.io  # labels only
    - fluxinstance/flux (flux-system)                  # labels only (helm.sh/chart, app version)
    - "clusterrole/{flux-operator-edit,flux-operator-view,flux-web-user,flux-web-admin}, clusterrolebinding/flux-operator, service/flux-operator, serviceaccount/flux-operator, networkpolicy/flux-operator-web, servicemonitor/flux-operator (labels only)"
    - kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml
    - kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml
    - "kubernetes/bootstrap/apps/helmfile.yaml (follow-up commit; NOT reconciled by Flux)"
    - "docs/infrastructure.md (follow-up commit)"
  shared: [flux, monitoring]          # flux: the GitOps control plane every other plan's
                                      # rollback depends on. monitoring: the flux-operator pod is
                                      # the ONLY exporter of flux_resource_info / flux_instance_info /
                                      # flux_operator_info (gotk_* is not scraped), i.e. the
                                      # instrument behind FluxResourceNotReady, FluxSourceStalled and
                                      # FluxMetricsAbsent; its restart is a scrape gap.
depends_on: []
conflicts_with:
  - flux-reconciler-impersonation     # exclusive; swaps the identity kustomize/helm-controller
                                      # apply under via FluxInstance patches, AND its premise
                                      # `operator-v0.57.0` pins the operator tag this plan moves.
                                      # Same-window = two control-plane causes for one failure.
  - flux-oci-chart-sources            # rewrites Flux chart sources (can move these two HRs'
                                      # chart source to OCIRepository) and edits cluster-meta.
  - helm-drift-detection              # changes HelmRelease behaviour cluster-wide incl. these two
                                      # HRs; attribution of any flux-system diff would be ambiguous.
  # - librechat-2.0.14 (RESOLVED 2026-09-30: executed + retired in nightly:2026-09-30, c75c5c39/4465c3c1; ref removed per the dead-ref convention)
  - redis-fleet-8.10.2                # Flux controller upgrade under its GitOps legs (review 2026-09-28).
  - nextcloud-fleet-35.0.1            # helm-controller restart mid-§3.4 strands its release
                                      # pending-upgrade (retries: 0) (review 2026-09-28).
exclusive: false                      # the six controllers do NOT roll (section 1.2, gated in 4.4),
                                      # so reconciliation continues throughout and a co-scheduled
                                      # plan's git-revert still works. conflicts_with covers the
                                      # three plans that touch Flux itself.
security_ref: null                    # no security driver claimed by the dispatch. The accepted
                                      # image-register row for the operator image (F-b81fe869) may
                                      # clear as a side effect; detail stays in the DB.
capability_change: false              # operator deltas are the web UI / MCP server / CLI (none
                                      # exposed or used here: no HTTPRoute to :9080, no MCP
                                      # deployment) and ResourceSet behaviour (0 ResourceSets).
                                      # Rendered controllers are byte-identical (section 1.2).
autonomy_override: human-gated        # RESTRICTS only. Control-plane change on its first run;
                                      # wants an operator GO, not SD-10 pre-approval.
rollback_class: git-revert            # no forward-only step: no CRD stored-version change, no
                                      # storage migration, no data. Flux-independent helm rollback
                                      # to measured revisions is in section 5.
finding_refs:
  - F-60f2b033                        # flux-operator: chart 0.57.0 -> 0.60.0 (version, monitor)
  - F-703d6382                        # flux-instance: chart 0.57.0 -> 0.60.0 (version, monitor)
premises:
  # Read-verb only. All nine run 2026-09-28 ~04:05 CEST and returned the expected value.
  - id: operator-image-current
    why: >-
      current claims operator image v0.57.0. If it moved, the chart diff in section 1.2
      and the helm revision numbers in section 5 are wrong - re-derive before running.
    run: kubectl get deploy -n flux-system flux-operator -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/controlplaneio-fluxcd/flux-operator:v0.57.0
  - id: both-charts-current
    why: Both HRs must be on 0.57.0 (kubectl lists them in argument order, i.e. flux-operator then flux-instance).
    run: kubectl get hr -n flux-system flux-operator flux-instance -o jsonpath='{.items[*].status.history[0].chartVersion}'
    expect_exact: 0.57.0 0.57.0
  - id: both-hrs-ready
    why: Never start a control-plane change from a not-Ready control plane.
    run: kubectl get hr -n flux-system flux-operator flux-instance -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")].status}'
    expect_exact: True True
  - id: distribution-v2.9.3-digest
    why: >-
      Gate 4.5 asserts the distribution revision is UNCHANGED after the bump. The baseline
      digest must be the one measured at authoring, or that gate compares against the wrong thing.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.status.lastAppliedRevision}'
    expect_contains: "v2.9.3@sha256:448f13677f141ed1d67ace07e2459495f4b0ae4a11ae88c77e369174709631ec"
  - id: no-resourcesets
    why: >-
      The two functional operator deltas in 0.57->0.60 (new CEL rule on ResourceSet
      dependsOn; PR 1011 honoring reconcile-disabled on ResourceSet-applied objects) are inert
      ONLY because zero ResourceSets/InputProviders exist. If one appeared, re-assess both.
    run: kubectl get resourcesets.fluxcd.controlplane.io,resourcesetinputproviders.fluxcd.controlplane.io -A -o name | wc -l | tr -d ' '
    expect_exact: "0"
  - id: target-operator-chart-published
    why: The target operator chart must still resolve from the OCI registry the HelmRepository points at.
    run: helm show chart oci://ghcr.io/controlplaneio-fluxcd/charts/flux-operator --version 0.60.0 | grep '^version:'
    expect_exact: "version: 0.60.0"
  - id: target-instance-chart-published
    why: Same, for the instance chart.
    run: helm show chart oci://ghcr.io/controlplaneio-fluxcd/charts/flux-instance --version 0.60.0 | grep '^version:'
    expect_exact: "version: 0.60.0"
  - id: cluster-reconciles-clean
    why: >-
      Gate 4.6 asserts notready=0 after the change; a pre-existing not-Ready object would make
      that gate fail for a reason this plan did not cause (or be waved through as "it was
      already like that"). Suspended objects are excluded, same as FluxResourceNotReady.
    run: >-
      kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases.helm.toolkit.fluxcd.io -A
      -o jsonpath='{range .items[*]}{.spec.suspend}{"/"}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
      | grep -v -e '^true/' -e '^false/True$' -e '^/True$' | wc -l | tr -d ' '
    expect_exact: "0"          # count of unsuspended ks+hr not Ready=True (268 total, all "/True" at authoring)
  - id: edit-anchor-unique
    why: The section 3 sed must match exactly one line per file (run from the repo root).
    run: >-
      cat kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml
      kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml | grep -c '^      version: 0.57.0$'
    expect_exact: "2"
status: vetted    # plan-reviewer 2026-09-28 (F-2c849d1e): needs-fix (absence gates without positive control) -> fixed -> delta re-review ready-for-go. HUMAN-GATED (autonomy_override); run before flux-reconciler-impersonation (10-11).
review: ready-for-go@2026-09-28
window: "nightly:2026-10-06"   # SCHEDULED 2026-09-28 by maintenance-window-agent (operator: "schedule everything that needs to be scheduled"); GO needed (autonomy_override, Flux floor); before flux-reconciler-impersonation 10-11
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/flux-upgrade.md
  - docs/sops/flux-image-automation-push-auth.md
  - docs/sops/maintenance-windows.md
  - docs/sops/disaster-recovery.md
generated: "2026-09-28"
---

# flux-fleet 0.57.0 -> 0.60.0 (flux-operator + flux-instance charts)

## 1. Summary & why held

### 1.1 What changes

Both halves of the Flux control-plane chart family move together, in **one commit**:

| HelmRelease (ns flux-system) | chart | what it deploys | effect of this bump |
|---|---|---|---|
| `flux-operator` | 0.57.0 -> 0.60.0 | the operator Deployment (1 replica), its 4 CRDs, RBAC, Service, NetworkPolicy, ServiceMonitor | **operator pod rolls** to image `v0.60.0`; one CEL rule added to the ResourceSet CRD; everything else labels only |
| `flux-instance` | 0.57.0 -> 0.60.0 | the `FluxInstance/flux` CR | **labels only** (`helm.sh/chart`, `app.kubernetes.io/version`); spec byte-identical |

The **distribution is NOT touched**: `instance.distribution.version: v2.9.3` in
`kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml` stays as is,
so source/kustomize/helm/notification/image-reflector/image-automation controllers
stay on their current images. This is a deliberate scope decision: moving the
distribution (v2.9.4/v2.9.5 now exist) is the high-risk half described in
`docs/sops/flux-upgrade.md` and is a separate plan if wanted.

### 1.2 Why it was held, and what the evidence says

Held by coverage.py: *"0.x release-line move (0.57 -> 0.60) - at major 0 the minor IS
the breaking axis; needs an assessed window plan"*. That is a structural rule, not a
detected breaking change. Assessed against primary sources:

**Upstream release notes** (github.com/controlplaneio-fluxcd/flux-operator releases
v0.58.0, v0.58.1, v0.59.0, v0.60.0) declare **no breaking change**. The content is
dominated by the web UI, the MCP server (stateless spec migration, new tools) and the
CLI (`distro mirror --distribution-artifact`), plus dependency bumps (golang.org/x,
grpc, k8s libs v0.36.2 -> v0.36.3). Two items touch operator reconcile behaviour, and
both are scoped to ResourceSets:

- v0.59.0, PR #1011 *"operator: honor reconcile disabled annotation on in-cluster
  objects"*: "Sets `ExclusionSelector` on the apply options so in-cluster objects
  annotated with `fluxcd.controlplane.io/reconcile: disabled` are skipped". Files
  changed: `internal/controller/resourceset_controller*.go` and the ResourceSet docs only.
- ResourceSet CRD gains `x-kubernetes-validations: rule '!has(self.readyExpr) || has(self.ready)'`
  on `spec.dependsOn[]`.

**This cluster has zero ResourceSets and zero ResourceSetInputProviders** (measured;
premise `no-resourcesets`), so both are inert here.

**Rendered diff with OUR values** (measured 2026-09-28: `helm pull` both versions of both
charts, `helm template` with `app/helm-values.yaml` / `instance/helm-values.yaml`, `diff`):

- flux-instance: 2 changed lines, `helm.sh/chart` and `app.kubernetes.io/version` labels.
  The FluxInstance spec (distribution, components, sync incl. `pullSecret`, the
  GitRepository `ignore` patch) is identical.
- flux-operator: labels on every object, `image: ...flux-operator:v0.57.0 -> v0.60.0`,
  and the 3-line CEL rule above. No values-schema change affecting `serviceMonitor.create`.

**Will the six controllers re-render?** The operator builds controller manifests from
`internal/builder` + the distribution manifests. `git diff v0.57.0 v0.60.0` (upstream repo):
`internal/builder/` **unchanged**; `config/data/flux/v2.9.3/` **unchanged** (moot here: the live FluxInstance sets `distribution.artifact: oci://ghcr.io/controlplaneio-fluxcd/flux-operator-manifests:latest`, so the manifests come from that OCI artifact, which the running v0.57.0 operator already pulls and which this bump does not change);
`internal/controller/fluxinstance_controller.go` changes one `//nolint` comment;
`github.com/fluxcd/pkg/ssa` v0.77.0, `fluxcd/pkg/kustomize` v1.39.0 and
`sigs.k8s.io/kustomize/api` v0.21.1 are the **same versions** in both go.mod files (kustomize
was only promoted from indirect to direct). The live controller pod templates carry no
operator-version label or annotation (inspected `deploy/kustomize-controller`). So the
expected outcome is a server-side-apply no-op for the controllers: **no controller
restart**. Gate 4.4 turns this claim into a check that fails if it is wrong.

**Verdict:** the hold is effectively a **false positive for breakage**. What remains is
blast radius: this is the reconcile engine, and the operator pod is the only exporter of
the `flux_*` metrics the Flux alerts read. Hence risk medium, attended, one commit, with
gates that read the contents of what the operator reports.

### 1.3 Security note

No security driver was given with the dispatch. The operator image has an accepted
register row in the findings DB (`F-b81fe869`); that row may be
re-evaluated after this lands. Detail stays in the DB.

## 2. Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` in zsh. Any failure -> stop, do not edit.

```bash
cd /Users/mu/code/cberg-home-nextgen
# a) premises (all 9 must PASS)
.venv/bin/python3 runbooks/plan-premises.py flux-fleet-0.60.0

# b) repo is at the revision Flux has applied (no in-flight reconcile of a newer commit)
git fetch -q origin && git status -sb | head -1
mise exec -- kubectl -n flux-system get gitrepository flux-system -o jsonpath='{.status.artifact.revision}{"\n"}'
git rev-parse origin/main
# PASS: the sha in the artifact revision equals origin/main.

# c) snapshot known-good state OUTSIDE the repo (used by 4.4, 4.5 and section 5)
mkdir -p /tmp/flux-fleet && cd /tmp/flux-fleet
mise exec -- kubectl -n flux-system get deploy source-controller kustomize-controller helm-controller \
  notification-controller image-reflector-controller image-automation-controller \
  -o jsonpath='{range .items[*]}{.metadata.name}{" gen="}{.metadata.generation}{" img="}{.spec.template.spec.containers[0].image}{"\n"}{end}' \
  > ctrl-before.txt
mise exec -- kubectl -n flux-system get pods -l 'app in (source-controller,kustomize-controller,helm-controller,notification-controller,image-reflector-controller,image-automation-controller)' \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.startTime}{"\n"}{end}' > ctrl-pods-before.txt
wc -l ctrl-before.txt ctrl-pods-before.txt        # PASS: 6 and 6
mise exec -- kubectl -n flux-system get deploy flux-operator -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}' > operator-before.txt
mise exec -- kubectl -n flux-system get fluxinstance flux -o jsonpath='{.status.lastAppliedRevision}{"\n"}' > fi-rev-before.txt
mise exec -- kubectl get crd fluxinstances.fluxcd.controlplane.io fluxreports.fluxcd.controlplane.io \
  resourcesets.fluxcd.controlplane.io resourcesetinputproviders.fluxcd.controlplane.io -o yaml > operator-crds-before.yaml
mise exec -- helm -n flux-system history flux-operator --max 3 > helm-op-before.txt
mise exec -- helm -n flux-system history flux-instance --max 3 > helm-inst-before.txt
tail -1 helm-op-before.txt; tail -1 helm-inst-before.txt
# EXPECT (measured 2026-09-28): flux-operator rev 3 deployed flux-operator-0.57.0;
#                              flux-instance rev 6 deployed flux-instance-0.57.0.
# If the numbers differ, write the real ones down: section 5 step 2 uses them.
cd /Users/mu/code/cberg-home-nextgen

# d) Prometheus baseline for the flux_* instrument (port-forward by PID, never kill %1)
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
pq() { curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "EMPTY")'; }
pq 'count(flux_resource_info)' | tee /tmp/flux-fleet/series-before.txt   # measured 478 on 2026-09-28
pq 'count(flux_resource_info{ready="False",suspended="False"})'           # PASS: EMPTY
pq 'count(flux_operator_info{version="v0.57.0"})'                         # PASS: 1
pq 'count(flux_operator_info{version="v0.60.0"})'                         # PASS: EMPTY  <- negative control for gate 4.2
pq 'max_over_time(count(flux_resource_info{ready="False",suspended="False"})[14d:10m])'   # POSITIVE CONTROL for 4.6: must be non-EMPTY (47 on 2026-09-28); EMPTY -> the ready="False" gate cannot fail, STOP
pq 'count(count_over_time(ALERTS{alertname="FluxResourceNotReady"}[14d]))'   # POSITIVE CONTROL for the 4.6 ALERTS gate: must be non-EMPTY (1205 series on 2026-09-28); if EMPTY retry with [30d], still EMPTY -> treat the 4.6 ALERTS line as informational only
pq 'count(ALERTS{alertname=~"Flux.*",alertstate="firing"})'               # PASS: EMPTY
kill $PF 2>/dev/null

# e) SOPS/push path works (the rollback is a push)
mise exec -- sops -d kubernetes/apps/flux-system/flux-operator/instance/git-auth-secret.sops.yaml >/dev/null && echo SOPS_OK
git push --dry-run origin main && echo PUSH_OK
```

Not taken, and why: the SOP's step 2 (set `retries: 0` / `cleanupOnFail: false` on both HRs
for the attempt) exists to stop helm remediation half-reverting a **six-controller roll**.
Here no controller rolls; the only rolling workload is the operator Deployment, and an
automatic helm rollback of it to 0.57.0 is the desired failure mode, not a hazard. Leaving
remediation as-is also keeps this a one-file-pair commit with a one-commit revert. Gate 4.1
detects a remediation rollback if one happens.

## 3. Steps

### 3.1 The coordinated bump (one commit, both HRs)

Dry-tested on scratch copies on macOS 2026-09-28 (BSD sed). Resulting diff, identical in
both files:

```
-      version: 0.57.0
+      version: 0.60.0
```

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's/^      version: 0\.57\.0$/      version: 0.60.0/' \
  kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml \
  kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml
git diff --stat -- kubernetes/apps/flux-system/flux-operator/     # EXPECT: 2 files, 2 insertions, 2 deletions
mise exec -- yq '.spec.chart.spec.version' \
  kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml \
  kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml   # EXPECT: 0.60.0 / --- / 0.60.0
mise exec -- kubeconform -summary -ignore-missing-schemas kubernetes/apps/flux-system/flux-operator/

cat > /tmp/flux-fleet/msg-core.txt <<'EOF'
feat(flux): flux-operator + flux-instance charts 0.57.0 -> 0.60.0 (plan flux-fleet-0.60.0)

Operator image v0.57.0 -> v0.60.0. Distribution stays v2.9.3; rendered
FluxInstance spec and controller manifests unchanged (builder/ssa/kustomize
identical between tags). Findings F-60f2b033 F-703d6382.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/flux-system/flux-operator/app/helmrelease.yaml \
  kubernetes/apps/flux-system/flux-operator/instance/helmrelease.yaml -F /tmp/flux-fleet/msg-core.txt
git log -1 --format=%s          # MUST be the subject above (shared-worktree message swap guard); amend if not
git show --stat HEAD            # MUST list exactly the two helmrelease.yaml files
git rev-parse HEAD | tee /tmp/flux-fleet/core-sha.txt
git push origin main
```

### 3.2 Propagation (observe; do not force unless stalled)

The GitHub webhook -> `Receiver/github-receiver` -> GitRepository `flux-system` ->
Kustomizations `flux-operator` and `flux-instance` (both watch the source revision) ->
helm-controller upgrades `hr/flux-operator` (operator pod rolls) and `hr/flux-instance`
(`dependsOn: flux-operator`). Order between the two does not matter for correctness here:
the flux-instance render is label-only, which the 0.57.0 operator handles identically.

```bash
SHA=$(cat /tmp/flux-fleet/core-sha.txt)
for i in $(seq 1 20); do
  R=$(mise exec -- kubectl -n flux-system get hr flux-operator flux-instance -o jsonpath='{.items[*].status.history[0].chartVersion}')
  echo "$(date +%T) $R"; [ "$R" = "0.60.0 0.60.0" ] && break; sleep 30
done
[ "$R" = "0.60.0 0.60.0" ] && echo PROPAGATED || echo "PROPAGATION_NOT_COMPLETE after 10 min -> run the reconcile block below"
```

If after 10 minutes the source revision has not reached `$SHA`, the webhook did not fire.
`docs/sops/flux-upgrade.md` section 4 step 4 prescribes driving the reconcile in order; only then:

```bash
mise exec -- flux -n flux-system reconcile source git flux-system
mise exec -- flux -n flux-system reconcile ks flux-operator && mise exec -- flux -n flux-system reconcile hr flux-operator
mise exec -- flux -n flux-system reconcile ks flux-instance && mise exec -- flux -n flux-system reconcile hr flux-instance
```

### 3.3 Follow-up commit (ONLY after section 4 is fully green)

Bring the two non-reconciled references into line. `kubernetes/bootstrap/apps/helmfile.yaml`
still pins **0.14.0** for both charts (stale since the 2026-08-11 upgrade): a disaster-recovery
bootstrap from it would install an operator that predates the image-API v1 GA the running
cluster depends on. It is not applied by Flux, so this commit changes no cluster state and
is kept separate so the section 5 revert of the core commit stays a single clean revert.

Dry-tested diffs (scratch copies, BSD sed):

```
helmfile.yaml   41c41  <     version: 0.14.0   >     version: 0.60.0      (flux-operator)
                48c48  <     version: 0.14.0   >     version: 0.60.0      (flux-instance)
infrastructure.md 111,112: `| 0.57.0 | flux-system |` -> `| 0.60.0 | flux-system |`
                  134: "(flux-operator/flux-instance chart 0.57.0)" -> "(... chart 0.60.0)"
```

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' -e '/charts\/flux-operator$/{n;s/^    version: 0\.14\.0$/    version: 0.60.0/;}' \
          -e '/charts\/flux-instance$/{n;s/^    version: 0\.14\.0$/    version: 0.60.0/;}' \
  kubernetes/bootstrap/apps/helmfile.yaml
sed -i '' -e 's#^\(| [45] | Flux [A-Za-z]* | `oci://ghcr.io/controlplaneio-fluxcd/charts/flux-[a-z]*` | \)0\.57\.0 |#\10.60.0 |#' \
          -e 's#(flux-operator/flux-instance chart 0\.57\.0)#(flux-operator/flux-instance chart 0.60.0)#' \
  docs/infrastructure.md
git diff --stat -- kubernetes/bootstrap/apps/helmfile.yaml docs/infrastructure.md   # EXPECT: 2 files, 5 insertions, 5 deletions
cat > /tmp/flux-fleet/msg-docs.txt <<'EOF'
docs(flux): bootstrap helmfile + infrastructure.md to flux charts 0.60.0

Bootstrap helmfile pinned flux-operator/flux-instance 0.14.0 since before the
2026-08-11 upgrade (DR path drift). No cluster effect. Plan flux-fleet-0.60.0.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
git commit --only kubernetes/bootstrap/apps/helmfile.yaml docs/infrastructure.md -F /tmp/flux-fleet/msg-docs.txt
git log -1 --format=%s && git show --stat HEAD && git push origin main
```

Then retire this plan file per `runbooks/maintenance/plans/README.md` (delete in the landing
commit or the next one) and close the two findings with the core sha:
`runbooks/policy-cli.py finding close F-60f2b033 --commit <core-sha>` (same for F-703d6382).

## 4. Verification

Run in order; each gate names what its failure prints. Re-establish the Prometheus
port-forward (`PF=$!` form from section 2 d) and re-define `pq` first; the operator pod
restart does not affect it (it targets Prometheus, not the operator).

### 4.1 Both releases deployed at 0.60.0, no remediation rollback

```bash
mise exec -- kubectl -n flux-system get hr flux-operator flux-instance \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.history[0].chartVersion}{" "}{.status.history[0].status}{" "}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
mise exec -- helm -n flux-system history flux-operator --max 2
mise exec -- helm -n flux-system history flux-instance --max 2
```
PASS: `flux-instance 0.60.0 deployed True` and `flux-operator 0.60.0 deployed True`; helm
latest revisions are 4 (`flux-operator-0.60.0`, "Upgrade complete") and 7
(`flux-instance-0.60.0`). FAIL looks like: chartVersion `0.57.0` with a newer revision whose
description is `Rollback to 3` (remediation fired), or Ready `False` with
`upgrade retries exhausted`.

### 4.2 The operator serving metrics IS the new build

```bash
mise exec -- kubectl -n flux-system get deploy flux-operator -o jsonpath='{.spec.template.spec.containers[0].image}{" avail="}{.status.availableReplicas}{"\n"}'
mise exec -- kubectl -n flux-system get pods -l app.kubernetes.io/name=flux-operator \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.phase}{" restarts="}{.status.containerStatuses[0].restartCount}{"\n"}{end}'
sleep 60   # one scrape interval after the new pod is Ready
pq 'count(flux_operator_info{version="v0.60.0"})'
pq 'count(flux_operator_info{version="v0.57.0"})'
```
PASS: image `...flux-operator:v0.60.0 avail=1`; one pod `Running restarts=0`;
`v0.60.0` -> `1`, `v0.57.0` -> `EMPTY`.
FAIL looks like: `v0.60.0` -> `EMPTY`. Proven able to fail: at authoring (2026-09-28) the
same query returned `EMPTY` and `v0.57.0` returned `1`. `EMPTY` for BOTH means the scrape
itself is broken (ServiceMonitor/port/NetworkPolicy) -> go to 4.3 and treat as FAIL.

CONTROL: metric flux_operator_info — the gate reads `count` with `version="v0.60.0"`; must be exactly 1 after the roll, and the v0.57.0 series must be gone.

### 4.3 The operator still reports the whole fleet (contents, not shape)

```bash
pq 'count(flux_resource_info)'; cat /tmp/flux-fleet/series-before.txt
pq 'count by (kind) (flux_resource_info)'
```
CONTENTS ASSERTION: the operator's report of every Flux object is complete — measured by
`count(flux_resource_info)`, compared to the section 2 d baseline (478 at authoring): PASS if
within +/-5 of the baseline AND all 10 kinds are present (HelmRelease, HelmChart,
HelmRepository, Kustomization, GitRepository, OCIRepository, Receiver, ImagePolicy,
ImageRepository, ImageUpdateAutomation). FAIL looks like `EMPTY` (scrape or reporter broken
— an empty result is a FAIL here, never a pass), a count far below baseline, or a kind
missing (e.g. no `Receiver` row: the webhook path would then be unmonitored).

CONTROL: metric flux_resource_info — `count()` floor at baseline-5 with all 10 kinds present; also the input to FluxResourceNotReady / FluxSourceStalled / FluxMetricsAbsent.

### 4.4 The six controllers did NOT roll (the plan's central claim)

```bash
mise exec -- kubectl -n flux-system get deploy source-controller kustomize-controller helm-controller \
  notification-controller image-reflector-controller image-automation-controller \
  -o jsonpath='{range .items[*]}{.metadata.name}{" gen="}{.metadata.generation}{" img="}{.spec.template.spec.containers[0].image}{"\n"}{end}' \
  | diff /tmp/flux-fleet/ctrl-before.txt - && echo CONTROLLERS_UNCHANGED
mise exec -- kubectl -n flux-system get pods -l 'app in (source-controller,kustomize-controller,helm-controller,notification-controller,image-reflector-controller,image-automation-controller)' \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.startTime}{"\n"}{end}' \
  | diff /tmp/flux-fleet/ctrl-pods-before.txt - && echo CONTROLLER_PODS_UNCHANGED
```
PASS: both `..._UNCHANGED` lines print. FAIL looks like a `diff` hunk showing `gen=3` or a new
pod name/startTime: the 0.60.0 operator re-rendered the controllers, contradicting section 1.2.
That is not automatically an outage (check 4.6), but the plan's premise is falsified: stop,
record the diff, and do not proceed to 3.3; decide revert-vs-keep with the operator. Proven
able to fail: `diff` against the snapshot is exact-string; a digest or generation change prints.

### 4.5 FluxInstance applied the SAME distribution, spec intact

```bash
mise exec -- kubectl -n flux-system get fluxinstance flux \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{" "}{.status.lastAppliedRevision}{"\n"}'
cat /tmp/flux-fleet/fi-rev-before.txt
mise exec -- kubectl -n flux-system get fluxinstance flux -o jsonpath='{.spec.sync.pullSecret}{"\n"}'
mise exec -- kubectl -n flux-system get gitrepository flux-system -o jsonpath='{.spec.secretRef.name}{"|"}{.spec.ignore}{"\n"}'
pq 'count(flux_instance_info{ready="True",revision="v2.9.3@sha256:448f13677f141ed1d67ace07e2459495f4b0ae4a11ae88c77e369174709631ec"})'
```
PASS: `True v2.9.3@sha256:448f1367...` identical to the saved revision; pullSecret
`flux-system-git-auth`; GitRepository shows `flux-system-git-auth|` followed by the ignore
block containing `!/kubernetes`; the PromQL returns `1`. FAIL looks like a different
revision/digest (distribution moved), an empty `pullSecret` (the silent-prune failure in
`docs/sops/flux-image-automation-push-auth.md`), or an ignore block without `!/kubernetes`.

CONTROL: metric flux_instance_info — `count` with ready="True" and the exact v2.9.3 digest revision label must be 1.

### 4.6 The cluster still reconciles end to end (10-minute soak)

```bash
sleep 600
mise exec -- kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases.helm.toolkit.fluxcd.io -A -o json \
  | python3 -c 'import sys,json; it=json.load(sys.stdin)["items"]; bad=[i["metadata"]["namespace"]+"/"+i["metadata"]["name"] for i in it if not i["spec"].get("suspend") and not any(c["type"]=="Ready" and c["status"]=="True" for c in i.get("status",{}).get("conditions",[]))]; print("total=%d notready=%d %s" % (len(it), len(bad), bad))'
pq 'count(flux_resource_info{ready="False",suspended="False"})'
pq 'count(ALERTS{alertname=~"FluxResourceNotReady|FluxSourceStalled|FluxMetricsAbsent",alertstate=~"pending|firing"})'
mise exec -- kubectl -n flux-system get ks flux-system cluster-apps flux-operator flux-instance \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.lastAppliedRevision}{"\n"}{end}'
```
PASS: `notready=0` with `total` within a few of the pre-check (268 at authoring);
both PromQL lines `EMPTY` — valid only because 4.3 proved the series exist AND the section 2 d positive controls proved both queries can match (reviewer measurement 2026-09-28: ready="False" max 47 over 14d; FluxResourceNotReady pending 1205 samples over 14d); all four
Kustomizations show `refs/heads/main@sha1:<core-sha or later>`. FAIL looks like
`notready=N [ns/name...]`, a non-empty ALERTS count, or a Kustomization still on the
pre-change sha (reconciliation stalled). Note FluxMetricsAbsent has `for: 30m` and cannot
fire inside this window — 4.3's floor is what actually guards the metric path.

CONTROL: alertname FluxResourceNotReady — must not be pending or firing after the soak.
CONTROL: alertname FluxSourceStalled — must not be pending or firing (would mean the GitRepository cannot fetch: nothing deploys).
CONTROL: alertname FluxMetricsAbsent — must not be firing; informational within the window (30m `for`), covered by 4.3.

```bash
kill $PF 2>/dev/null
```

## 5. Rollback

Nothing in this plan is forward-only: no CRD stored-version change (the only CRD schema
delta is an added CEL rule on a kind with 0 objects), no data, no migration. The follow-up
commit 3.3 is not applied to the cluster and never needs reverting for recovery.

**Trigger:** any of 4.1-4.3 or 4.5-4.6 FAIL; or 4.4 FAIL combined with any 4.6 failure.

1. **GitOps revert (preferred — the controllers never rolled, so Flux is fully able to apply it):**
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git revert --no-edit $(cat /tmp/flux-fleet/core-sha.txt)
   git log -1 --format=%s && git show --stat HEAD     # the two helmrelease.yaml files only
   git push origin main
   ```
   helm-controller downgrades both releases to 0.57.0 (new revisions, e.g. 5 and 8);
   the operator pod rolls back to v0.57.0; the ResourceSet CRD loses the CEL rule.
2. **Flux-independent (only if the operator or helm-controller is wedged and step 1 does not converge in 10 min):**
   ```bash
   for hr in flux-operator flux-instance; do mise exec -- kubectl -n flux-system patch hr $hr --type merge -p '{"spec":{"suspend":true}}'; done
   mise exec -- helm -n flux-system rollback flux-operator 3    # rev numbers from /tmp/flux-fleet/helm-op-before.txt
   mise exec -- helm -n flux-system rollback flux-instance 6    # and helm-inst-before.txt
   # still crashlooping? pin the known-good image recorded in operator-before.txt:
   mise exec -- kubectl -n flux-system set image deploy/flux-operator manager=$(cat /tmp/flux-fleet/operator-before.txt)
   ```
   Then make git match (step 1 revert pushed), and un-suspend both HRs
   (`...patch hr $hr --type merge -p '{"spec":{"suspend":false}}'`). If even this fails,
   `docs/sops/disaster-recovery.md`.
3. **Confirm the cluster is back:** re-run 4.1 expecting `0.57.0 deployed True` for both;
   4.2 expecting `flux_operator_info{version="v0.57.0"}` -> `1` and `v0.60.0` -> `EMPTY`;
   4.3, 4.5 and 4.6 unchanged in their PASS criteria. The CRD snapshot in
   `/tmp/flux-fleet/operator-crds-before.yaml` exists only for the case where a schema
   mismatch blocks the 0.57.0 operator (not expected: 0.60.0 only ADDS a rule); apply it
   with `mise exec -- kubectl apply -f` only in that case.

## 6. Interference notes

- **Control plane, but not a controller roll.** Only `deployment/flux-operator` restarts
  (~30-60 s). Source/kustomize/helm/notification/image controllers keep running and keep
  reconciling other plans' commits during this plan; that is why it is not `exclusive`.
  If 4.4 shows otherwise, treat the window as having had a full controller roll (transient
  `artifact not found` for about one interval per `docs/sops/flux-upgrade.md` Test 2).
- **The instrument restarts.** Every Flux alert reads `flux_*` series exported by the
  operator pod. During its restart there is a scrape gap of about one interval. Any other plan
  in the same window whose verification reads `flux_resource_info` must not run its
  gates during this plan's section 3.2-4.3.
- **flux-reconciler-impersonation (sun-attended:2026-10-11, exclusive).** Its premise
  `operator-v0.57.0` (`expect_contains: "flux-operator:v0.57.0"`) will FAIL once this plan
  lands, and correctly so: it asks for a re-read of `internal/builder/profiles.go` and
  `fluxinstance_controller.go` at the new tag. That re-read is done here (section 1.2): builder
  unchanged, controller change is one `//nolint` comment. Its owner must amend that premise
  to `v0.60.0`, citing this plan, before 10-11 — or this plan must run after it. Running
  THIS plan first is preferred (smaller change, clean baseline for the identity swap).
- **flux-oci-chart-sources** may later move these two HRs' chart source from
  `HelmRepository/controlplaneio` (already `type: oci`) to an `OCIRepository`; if that stage
  runs first, the section 3.1 edit target changes (`spec.chartRef` / OCIRepository tag) and
  this plan must be refreshed.
- **helm-drift-detection** adds `spec.driftDetection` to every HelmRelease including these two;
  a same-window run makes any helm revision bump on flux-system unattributable.
- **Reciprocity:** `flux-reconciler-impersonation` and `helm-drift-detection` already list `flux-fleet-0.60.0`; `flux-oci-chart-sources` gains the entry in the commit that tracks this plan. If impersonation runs first, premise `distribution-v2.9.3-digest` and gate 4.5's digest will fail by design (its FluxInstance patch changes the digest): re-baseline them, do not wave it through.
- **Out of scope, deliberately:** the distribution bump v2.9.3 -> v2.9.x (new controller
  images, the SOP's high-risk half) and the `.mise.toml` `flux` CLI pin. Neither moves here.
- **Step 0 interplay:** coverage.py lists these under `needs_plan_groups`, so the nightly
  safe-update lane will not direct-bump them; no other lane edits these two files.
