---
plan_id: flux-distribution-2.9.6
component: flux-distribution          # FluxInstance/flux .spec.distribution.version (ns flux-system):
                                      # the six controllers the flux-operator renders. NOT the
                                      # flux-operator/flux-instance charts (that is flux-fleet-0.60.0).
pr: null                              # No Renovate PR: the distribution line in helm-values.yaml carries
                                      # no Renovate annotation (docs/sops/flux-upgrade.md section 2). Held
                                      # update surfaced by the coordinator 2026-10-05.
kind: infra
current: "FluxInstance distribution v2.9.3 (source-controller v1.9.3, kustomize-controller v1.9.4, helm-controller v1.6.3, notification-controller v1.9.2, image-reflector-controller v1.2.3, image-automation-controller v1.2.3)"
target: "v2.9.6"                      # source-controller v1.9.6, kustomize-controller v1.9.6, helm-controller v1.6.5,
                                      # notification-controller v1.9.4, image-reflector-controller v1.2.5,
                                      # image-automation-controller v1.2.5 (digests in section 1.3)
update_type: patch
risk: medium                          # The diff is small and measured (section 1.4), but ALL SIX controllers
                                      # roll, including the two that would apply this plan's own revert
                                      # (section 5). helm-controller also swaps its Helm library from the
                                      # Flux fork back to upstream Helm v4.2.4. Not high: no CRD storage
                                      # change, no data, patch line, a Flux-independent recovery path exists
                                      # and is rehearsable read-only (pre-check 2.f).
est_duration_min: 50                  # pre-checks 10 + edit/commit/push 3 + propagate/roll 7 +
                                      # verification 22 (incl. a 10-min soak and the end-to-end commit in 4.7) +
                                      # retire/close 3 + slack 5
needs_reboot: false
touches:
  namespaces: [flux-system]
  resources:
    - kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml   # the one-line edit
    - "configmap/flux-instance-helm-values-<hash> (flux-system)"            # configMapGenerator: new hash name
    - helmrelease/flux-instance (flux-system)                               # helm upgrade, new revision (values only)
    - fluxinstance/flux (flux-system)                                       # spec.distribution.version v2.9.3 -> v2.9.6
    - deployment/source-controller (flux-system)                            # ROLLS
    - deployment/kustomize-controller (flux-system)                         # ROLLS
    - deployment/helm-controller (flux-system)                              # ROLLS
    - deployment/notification-controller (flux-system)                      # ROLLS (Receiver/github-receiver briefly down)
    - deployment/image-reflector-controller (flux-system)                   # ROLLS
    - deployment/image-automation-controller (flux-system)                  # ROLLS
    - crd/imageupdateautomations.image.toolkit.fluxcd.io                    # adds a refspec validation pattern (section 1.4)
    - "docs/infrastructure.md (follow-up commit, also the end-to-end test in 4.7)"
  shared: [flux]                      # the reconcile engine and the git-revert path of EVERY other plan.
                                      # Not `monitoring`: the flux-operator pod (the flux_* exporter) does
                                      # NOT restart here (gate 4.4); gotk_* controller metrics are not scraped.
                                      # The window's Prometheus instrument is covered by conflicts_with
                                      # kube-prometheus-stack-91.9.0.
depends_on: [flux-fleet-0.60.0]       # operator chart/image 0.57.0 -> 0.61.0 must be executed first (coordinator
                                      # sequencing; flux-fleet gate 4.5 asserts the distribution is UNCHANGED, so
                                      # the two can never share a commit or a slot).
conflicts_with:
  - cli-tool-pins                     # 2026-10-05: exclusive; touches the flux CLI pin this plan's retire step moves
  - flux-fleet-0.60.0                 # same control plane; it also gates "distribution unchanged" (4.5) and a
                                      # same-slot run would make both plans' gates unattributable.
  - flux-oci-chart-sources            # rewrites Flux chart sources: needs a stable source-controller under it.
  - helm-drift-detection              # changes HelmRelease behaviour fleet-wide; its premise
                                      # `flux-distribution-is-2.9` and its section 3.0.0 proof were measured on
                                      # kustomize/helm-controller of v2.9.3 and must be re-run after this lands.
  - flux-reconciler-impersonation     # swaps the identity kustomize/helm-controller apply under via FluxInstance
                                      # patches; its gates baseline the FluxInstance digest this plan changes.
  - kube-prometheus-stack-91.9.0      # sections 2.d/4.3/4.5/4.6 read Prometheus (the window's instrument).
  - ci-runner-exclude-node02          # proposed for nightly:2026-10-06; GitOps legs need a stable Flux.
  # Plans whose own apply/revert rides helm-controller/kustomize-controller and which an in-flight controller
  # roll would strand (helm-controller restart mid-upgrade leaves a release pending-upgrade; with retries: 0
  # nothing recovers it). Same set flux-fleet-0.60.0 serializes against; this plan rolls MORE than that one.
  - redis-fleet-8.10.2
  - nextcloud-fleet-35.0.1
  - nextcloud-9.4.0
  - n8n-2.39.8
  - n8n-chart-2.1.1
  - pgvector-fleet-0.8.7
  - python-fleet-3.14.8
  - unpoller-5.4.0
  - coredns-1.48.2                    # 2026-10-05: coredns-1.48.1 superseded
  - talos-linux-1.14.2                # 2026-10-05 review: node roll + folded upgrade-k8s (exclusive covers it; named anyway)
  - talos-power-tuning-ab             # 2026-10-05 review: named for completeness
  - anythingllm-1.17
  - grafana-13.2.7
  - external-dns-1.23.0
  - longhorn-1.13.0
  - jellyfin-12.1
  - paperless-db-13.0.2
  - penpot-chart-1.10.0
exclusive: true                       # Every co-scheduled plan relies on these six controllers to apply AND to
                                      # revert itself. conflicts_with cannot name plans not written yet; this
                                      # flag can. (Step 0 safe-update apply is not a plan: see section 6.)
security_ref: null                    # The six controller-image register rows below are the security side of
                                      # this bump (accepted under an AR because a newer upstream exists). Detail
                                      # stays in the findings DB; nothing about them is described here.
capability_change: false              # No new route, permission, API or exposure. The only new feature
                                      # (kustomize-controller DisableCommitStatusEvent) is an opt-in feature gate
                                      # we do not set. The two tightenings (kubeconfig Secrets must be inline;
                                      # ImageUpdateAutomation refspec pattern) match ZERO objects here (premises
                                      # no-kubeconfig-refs, no-iua-refspec).
autonomy_override: human-gated        # RESTRICTS only. The whole reconcile engine rolls; SD-11's in-code floor
                                      # already forbids `flux`, this makes the intent explicit.
rollback_class: git-revert            # No forward-only step: CRD served/stored versions identical between
                                      # v2.9.3 and v2.9.6 (section 1.4). BUT the revert is applied by the very
                                      # controllers this plan replaces - section 5 names the Flux-independent path.
finding_refs:                         # ownership claim: these register rows resolve when the controllers move
  - F-411a07b6                        # source-controller v1.9.3 image row
  - F-e47b7277                        # kustomize-controller v1.9.4 image row
  - F-beed22e5                        # helm-controller v1.6.3 image row
  - F-e97428d6                        # notification-controller v1.9.2 image row
  - F-9fb77dce                        # image-reflector-controller v1.2.3 image row
  - F-edd36ca7                        # image-automation-controller v1.2.3 image row
premises:
  # Read-verb only. All run 2026-10-05 ~10:00 CEST. Expected values below are the values that must hold
  # AT EXECUTION (after flux-fleet-0.60.0 executed); operator-is-0.61.0 therefore FAILS today, by design.
  - id: distribution-current
    why: The edit replaces v2.9.3; if the distribution already moved, this plan is stale (README "outlive its own work").
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.spec.distribution.version}'
    expect_exact: v2.9.3
  - id: operator-is-0.61.0
    why: >-
      depends_on flux-fleet-0.60.0. If the operator is still v0.57.0 that plan has not executed and this one
      must not run (attribution of a regression to operator vs controllers would be impossible).
    run: kubectl get deploy -n flux-system flux-operator -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/controlplaneio-fluxcd/flux-operator:v0.61.0
  - id: fluxinstance-ready
    why: Never roll the controllers from a not-Ready FluxInstance.
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  # Target existence (release + six image digests) is NOT a premise: plan-premises.py allows no
  # network read verb (gh/curl are refused). It is pre-check 2.g, which must pass before the edit.
  - id: no-kubeconfig-refs
    why: >-
      kustomize-controller v1.9.5 / helm-controller v1.6.4 reject kubeconfig Secrets that reference local
      files. Inert only while no Kustomization/HelmRelease uses spec.kubeConfig.
    run: >-
      kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases.helm.toolkit.fluxcd.io -A
      -o jsonpath='{range .items[*]}{.spec.kubeConfig.secretRef.name}{"\n"}{end}' | grep -c .
    expect_exact: "0"
  - id: no-iua-refspec
    why: >-
      The v2.9.6 ImageUpdateAutomation CRD adds pattern '^$|^[^+:]' on spec.git.push.refspec. Inert only while
      no automation sets a refspec (6 automations exist, none sets one).
    run: >-
      kubectl get imageupdateautomations.image.toolkit.fluxcd.io -A
      -o jsonpath='{range .items[*]}{.spec.git.push.refspec}{"\n"}{end}' | grep -c .
    expect_exact: "0"
  - id: cluster-reconciles-clean
    why: >-
      Gate 4.6 asserts notready=0 after the roll; a pre-existing not-Ready object would make it fail for a
      reason this plan did not cause. Suspended objects excluded, same as FluxResourceNotReady.
    run: >-
      kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases.helm.toolkit.fluxcd.io -A
      -o jsonpath='{range .items[*]}{.spec.suspend}{"/"}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
      | grep -v -e '^true/' -e '^false/True$' -e '^/True$' | wc -l | tr -d ' '
    expect_exact: "0"
  - id: edit-anchor-unique
    why: The section 3.1 sed must match exactly one line (run from the repo root).
    run: >-
      grep -c '^    version: v2\.9\.3$' kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml
    expect_exact: "1"
status: draft
review: null
window: null   # 2026-10-05 schedule: proposed operator NOW evening 2026-10-09 18:30 (GO) after (a) flux-fleet-0.60.0 executed 10-06 + >=1 nightly Step 0 on operator v0.61.0, (b) premise operator-is-0.61.0 PASSES and a delta re-review records ready-for-go; fallback nightly:2026-10-14 with GO
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/flux-upgrade.md
  - docs/sops/flux-image-automation-push-auth.md
  - docs/sops/maintenance-windows.md
  - docs/sops/disaster-recovery.md
generated: "2026-10-05"
---

# Flux distribution v2.9.3 -> v2.9.6 (the six controllers)

## 1. Summary & why held

### 1.1 What changes

One line in `kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml`:
`instance.distribution.version: v2.9.3 -> v2.9.6`. The repo pins the distribution by
**version only** — there is no digest pin anywhere in the repo for it (grep of
`kubernetes/`, `kubernetes/bootstrap/`, `docs/`); the operator resolves the image digests
from its manifests artifact (1.3). So there is no digest line to edit.

The chain that applies it: push -> `Receiver/github-receiver` -> `GitRepository/flux-system`
-> `Kustomization/flux-instance` (kustomize-controller) renders a new
`flux-instance-helm-values-<hash>` ConfigMap -> `HelmRelease/flux-instance` (helm-controller)
upgrades the release -> `FluxInstance/flux` spec changes -> **flux-operator** (not one of
the six) server-side-applies the v2.9.6 manifests and rolls all six controller Deployments,
waiting for them (`spec.wait: true`).

| controller | v2.9.3 (live) | v2.9.6 |
|---|---|---|
| source-controller | v1.9.3 | v1.9.6 |
| kustomize-controller | v1.9.4 | v1.9.6 |
| helm-controller | v1.6.3 | v1.6.5 |
| notification-controller | v1.9.2 | v1.9.4 |
| image-reflector-controller | v1.2.3 | v1.2.5 |
| image-automation-controller | v1.2.3 | v1.2.5 |

Out of scope: the operator/instance charts (flux-fleet-0.60.0, must run first) and the local
`flux` CLI pin in `.mise.toml` (`"aqua:fluxcd/flux2" = "2.9.0"`): cli-tool-pins moves it to
2.9.3 (today's cluster), and the 2.9.3 -> 2.9.6 CLI catch-up is owned by THIS plan's §3.4 retire
step (ownership settled 2026-10-05 after both plans disclaimed it). The CLI stays usable against v2.9.6 controllers (same API versions; 2.9.x
patch line), so it does not block this plan.

### 1.2 Why it was held

The distribution line is not Renovate-tracked and `docs/sops/flux-upgrade.md` classifies the
distribution move as "the high-risk half" of a Flux upgrade: the controllers reconcile the very
change that replaces them. flux-fleet-0.60.0 section 1.1 deliberately excluded it. Nothing in the
upstream notes is marked breaking; the hold is structural (control plane), not a detected break.

### 1.3 Target exists — measured 2026-10-05

- `gh release view v2.9.6 -R fluxcd/flux2`: published 2026-10-01, not a pre-release. No v2.9.7 yet.
- The live FluxInstance sets `distribution.artifact: oci://ghcr.io/controlplaneio-fluxcd/flux-operator-manifests:latest`.
  Pulled it (`flux pull artifact`, digest `sha256:8133331bb3ab…` = the live
  `status.lastArtifactRevision`, i.e. the operator already holds this artifact). It contains
  `flux/v2.9.4`, `v2.9.5`, `v2.9.6` and `flux-images/v2.9.6/upstream-alpine.yaml` pinning:

  | image | digest (index) |
  |---|---|
  | ghcr.io/fluxcd/source-controller:v1.9.6 | `sha256:6a6693172589f8ff26123a231d5fa6ceb194a6efb4dc647cdf057c959f76a2e3` |
  | ghcr.io/fluxcd/kustomize-controller:v1.9.6 | `sha256:2ebeaa341da77d52b6abbbba5efcee0450d47f8b42f0e6f33b08f9020262d606` |
  | ghcr.io/fluxcd/helm-controller:v1.6.5 | `sha256:0d52fff5c4d476277b8fcb6beb9041e269adb5db943fe69f5a806ea0c92b1511` |
  | ghcr.io/fluxcd/notification-controller:v1.9.4 | `sha256:840f318265ee26f0d2c48a158bf7896b22aa4e998e320a18646309f0e40b15da` |
  | ghcr.io/fluxcd/image-reflector-controller:v1.2.5 | `sha256:c83ce5c06fed9ebb308cd5165bd144ee934c720f6b47e0da2180869092063c82` |
  | ghcr.io/fluxcd/image-automation-controller:v1.2.5 | `sha256:e1a2720d3951694609c39635886d5dcb15b7dffe0b8248461c6693539c522a28` |

  Each was independently resolved from ghcr (`HEAD /v2/<repo>/manifests/<tag>`, HTTP 200) and
  matches the artifact. Control: the same method returns the live
  `source-controller:v1.9.3@sha256:ff8f3c92…` digest exactly.
  `flux-manifests:v2.9.6` (upstream) also resolves (`sha256:e007ec3c…`).
- The FluxInstance `lastAppliedRevision` after the change is `v2.9.6@sha256:<digest>`; that
  digest is computed by the operator over the rendered set and **cannot be predicted**; gates
  match `v2.9.6@sha256:` and record the value.

### 1.4 Upstream evidence, per release (fluxcd/flux2 release notes + each controller's CHANGELOG at the target tag)

**v2.9.4 (2026-08-07)** — "Note that this release contains CRD schema changes for
`ArtifactGenerator` and `ImageUpdateAutomation`; both CRDs must be updated along with the controllers."
- source-controller v1.9.4: Helm index loading aligned with upstream Helm v4 (skips empty entries);
  Bucket error handling; *"Pin OCI chart verification by digest"*; GCS static auth limited to SA keys.
- notification-controller v1.9.3: event and receiver servers share a 3 MiB body limit (HTTP 413
  above), 30 s read timeout, 10 s header timeout, 256 KiB max header. GitHub push payloads are far
  below this.
- image-automation-controller v1.2.4: `spec.git.push.refspec` gains a pattern rejecting deletion
  (`:ref`) and force (`+`) refspecs. **Zero automations here set a refspec** (premise `no-iua-refspec`).
- image-reflector-controller v1.2.4: ECR host detection only.
- `ArtifactGenerator` belongs to source-watcher, which is **not** in our `components` list; the
  CRD is not installed here (FluxInstance inventory).

**v2.9.5 (2026-08-31)** — *"moves helm-controller and source-controller back to upstream Helm,
now at v4.2.4, dropping the temporary Flux fork"* (helm-controller PR #1565: "Helm 4.2.4 includes
helm/helm#32327, so we can move back"). Also: *"kubeconfigs read from `.spec.kubeConfig` Secrets
are now required to be self-contained … entries referencing files on the local filesystem are
rejected"* (helm-controller v1.6.4, kustomize-controller v1.9.5) — **zero objects here use
`spec.kubeConfig`** (premise `no-kubeconfig-refs`); kustomize-controller purges stale tmp dirs at
startup; negative-length substring `${VAR:2:-1}` no longer panics (repo grep: no such expression).
Everything else is a Kubernetes 1.36.4 library bump.

**v2.9.6 (2026-10-01)**
- helm-controller v1.6.5, PR #1589 *"Fix updating CRDs on upgrades with the Create policy when using
  SSA"*: with the default `upgrade.crds: Create`, SSA had been silently **updating** chart `crds/`
  CRDs on every upgrade; now they are left alone, as with client-side apply. **This is the one real
  behaviour change.** Measured impact here: every HelmRelease whose chart ships a `crds/` directory
  already sets `install/upgrade.crds: CreateReplace` (envoy-gateway, external-dns,
  intel-device-plugin-operator, node-feature-discovery, eck-operator, kube-prometheus-stack,
  otel-operator). CRDs created by helm-controller from a `crds/` dir carry the label
  `helm.toolkit.fluxcd.io/name`; the only such owner NOT in that list is `monitoring/kubernetes-dashboard`
  (12 Kong CRDs) — and that HelmRelease **no longer exists** (orphaned CRDs). cert-manager, longhorn,
  eck-operator and flux-operator ship CRDs as templates (Helm-owned), which #1589 does not touch.
  Net: no live HelmRelease changes behaviour. **Future rule**: a new chart with a `crds/` dir must set
  `crds: CreateReplace` or its CRDs will never update after install.
- helm-controller: recovers HelmReleases stuck with a drifted `Ready=Unknown`; ignores NotFound on
  HelmChart delete.
- source-controller v1.9.6: Azure Blob ETag normalisation (no Bucket sources here); evicts stale Helm
  index cache entries ("Cache is full").
- kustomize-controller v1.9.6: SOPS redaction extended to `postBuild.substituteFrom` values in
  status/events (a strict improvement for us: cluster-secrets is a substituteFrom source); opt-in
  `DisableCommitStatusEvent` gate (not enabled).

**Rendered manifest diff v2.9.3 -> v2.9.6** (measured: both directories from the pulled artifact,
CRD specs compared as JSON, other objects with labels/annotations stripped):
- CRDs: `imageupdateautomations` gains `pattern: "^$|^[^+:]"` + a description line on
  `refspec`; `artifactgenerators` (not installed) gains two validations. **No change to
  served/storage versions of any CRD** — so there is no storage migration (the v2.5->v2.9
  wedge in the SOP's Example B cannot recur) and reverting removes a pattern, nothing more.
- Deployments: the image tag of each of the six controllers. Nothing else (no args, no env,
  no resources, no probes).
- `NetworkPolicy/allow-webhooks` gains `ports: 9292` — not rendered here (`cluster.networkPolicy: false`;
  inventory holds no NetworkPolicy).

**Verdict:** a patch with one real behaviour change (#1589) that is measured inert here, two
tightenings measured inert, and a Helm library swap in helm-controller (fork -> upstream with the
fix the fork existed for). Risk comes from the blast radius, not the diff.

### 1.5 Security note

Six controller-image register rows (finding_refs) are accepted only because a newer upstream tag
exists; this plan is that bump. Detail stays in the findings DB.

## 2. Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` in zsh. Any failure -> stop, do not edit.

```bash
cd /Users/mu/code/cberg-home-nextgen
# a) premises (all 7 must PASS; operator-is-0.61.0 proves depends_on is met)
.venv/bin/python3 runbooks/plan-premises.py flux-distribution-2.9.6
grep -m1 '^status:' runbooks/maintenance/plans/flux-fleet-0.60.0.md 2>/dev/null || echo "flux-fleet plan retired (expected after it executed)"

# b) Step 0 of THIS window has settled, nothing is mid-reconcile, no stranded release
git fetch -q origin
mise exec -- kubectl -n flux-system get gitrepository flux-system -o jsonpath='{.status.artifact.revision}{"\n"}'
git rev-parse origin/main
# PASS: the sha in the artifact revision equals origin/main (Step 0 commits, if any, are applied).
mise exec -- helm list -A --pending
# PASS: header line only. A row = a release pending-install/upgrade/rollback; rolling helm-controller
# under it would strand it. Wait for it to finish or stop.

# c) snapshot known-good state OUTSIDE the repo (used by section 4 and section 5)
mkdir -p /tmp/flux-dist && cd /tmp/flux-dist
mise exec -- kubectl -n flux-system get deploy helm-controller image-automation-controller image-reflector-controller \
  kustomize-controller notification-controller source-controller \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.template.spec.containers[0].image}{"\n"}{end}' \
  | tee ctrl-before.txt
# EXPECT (measured 2026-10-05) six lines, ghcr.io/fluxcd/<name>:<v2.9.3 tag>@sha256:... e.g.
#   source-controller ghcr.io/fluxcd/source-controller:v1.9.3@sha256:ff8f3c92f1bc...
cat > ctrl-expected.txt <<'EOF'
helm-controller ghcr.io/fluxcd/helm-controller:v1.6.5@sha256:0d52fff5c4d476277b8fcb6beb9041e269adb5db943fe69f5a806ea0c92b1511
image-automation-controller ghcr.io/fluxcd/image-automation-controller:v1.2.5@sha256:e1a2720d3951694609c39635886d5dcb15b7dffe0b8248461c6693539c522a28
image-reflector-controller ghcr.io/fluxcd/image-reflector-controller:v1.2.5@sha256:c83ce5c06fed9ebb308cd5165bd144ee934c720f6b47e0da2180869092063c82
kustomize-controller ghcr.io/fluxcd/kustomize-controller:v1.9.6@sha256:2ebeaa341da77d52b6abbbba5efcee0450d47f8b42f0e6f33b08f9020262d606
notification-controller ghcr.io/fluxcd/notification-controller:v1.9.4@sha256:840f318265ee26f0d2c48a158bf7896b22aa4e998e320a18646309f0e40b15da
source-controller ghcr.io/fluxcd/source-controller:v1.9.6@sha256:6a6693172589f8ff26123a231d5fa6ceb194a6efb4dc647cdf057c959f76a2e3
EOF
diff ctrl-expected.txt ctrl-before.txt >/dev/null && echo "ALREADY_ON_TARGET -> stop, plan is stale" || echo "NEGATIVE_CONTROL_OK (gate 4.2 can fail)"
mise exec -- kubectl -n flux-system get deploy flux-operator -o jsonpath='{.spec.template.spec.containers[0].image}{" "}{.metadata.generation}{"\n"}' > operator-before.txt
mise exec -- kubectl -n flux-system get pods -l app.kubernetes.io/name=flux-operator -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.startTime}{"\n"}{end}' > operator-pod-before.txt
mise exec -- kubectl -n flux-system get fluxinstance flux -o yaml > fluxinstance-before.yaml
mise exec -- kubectl -n flux-system get fluxinstance flux -o jsonpath='{.status.lastAppliedRevision}{"\n"}' | tee fi-rev-before.txt
mise exec -- kubectl get crd -o name | grep -E 'toolkit\.fluxcd\.io' | xargs mise exec -- kubectl get -o yaml > flux-crds-before.yaml
mise exec -- kubectl get crd imageupdateautomations.image.toolkit.fluxcd.io -o json \
  | python3 -c 'import sys,json; s=json.load(sys.stdin)["spec"]["versions"]; v=[x for x in s if x["storage"]][0]; print(repr(v["schema"]["openAPIV3Schema"]["properties"]["spec"]["properties"]["git"]["properties"]["push"]["properties"]["refspec"].get("pattern")))'
# EXPECT: None   (negative control for gate 4.5: the pattern is absent on v2.9.3)
mise exec -- helm -n flux-system history flux-instance --max 2 | tee helm-inst-before.txt
# EXPECT (after flux-fleet-0.60.0): latest "deployed flux-instance-0.61.0". Write the revision number down.
cd /Users/mu/code/cberg-home-nextgen

# d) Prometheus baseline (port-forward by PID, never kill %1)
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
pq() { curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "EMPTY")'; }
pq 'count(flux_resource_info)' | tee /tmp/flux-dist/series-before.txt      # 420 on 2026-10-05
pq 'count(flux_instance_info{ready="True",revision=~"v2[.]9[.]3@sha256:.*"})'  # PASS: 1
pq 'count(flux_instance_info{revision=~"v2[.]9[.]6@sha256:.*"})'            # PASS: EMPTY  <- negative control for 4.3 (measured EMPTY 2026-10-05)
pq 'max_over_time(count(flux_resource_info{ready="False",suspended="False"})[14d:10m])'  # POSITIVE CONTROL for 4.6: must be non-EMPTY
pq 'count(ALERTS{alertname=~"Flux.*",alertstate="firing"})'                 # PASS: EMPTY
kill $PF 2>/dev/null
mise exec -- kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases.helm.toolkit.fluxcd.io -A -o json \
  | python3 -c 'import sys,json; it=json.load(sys.stdin)["items"]; bad=[i["metadata"]["namespace"]+"/"+i["metadata"]["name"] for i in it if not i["spec"].get("suspend") and not any(c["type"]=="Ready" and c["status"]=="True" for c in i.get("status",{}).get("conditions",[]))]; print("total=%d notready=%d %s" % (len(it), len(bad), bad))' | tee /tmp/flux-dist/total-before.txt
# PASS: notready=0. total= is the 4.6 baseline.

# e) the push path works (both the change and the revert are pushes)
git push --dry-run origin main && echo PUSH_OK

# f) the Flux-INDEPENDENT recovery path works, read-only (section 5 step 2 depends on it)
mise exec -- kubectl auth can-i patch fluxinstances.fluxcd.controlplane.io -n flux-system
mise exec -- kubectl auth can-i patch helmreleases.helm.toolkit.fluxcd.io -n flux-system
mise exec -- kubectl -n flux-system patch fluxinstance flux --type merge --dry-run=server \
  -p '{"spec":{"distribution":{"version":"v2.9.3"}}}' -o jsonpath='{.spec.distribution.version}{"\n"}'
# PASS: yes / yes / v2.9.3  (server-side dry run: admission + CRD validation accept the rollback patch;
# nothing is persisted). If any fails, the break-glass path does not exist -> STOP, do not run this plan.

# g) the target exists upstream with the digests section 1.3 / ctrl-expected.txt assume
gh release view v2.9.6 -R fluxcd/flux2 --json tagName,isPrerelease
# PASS: {"isPrerelease":false,"tagName":"v2.9.6"}
cat > /tmp/flux-dist/dig.sh <<'EOF'
#!/bin/bash
repo=$1; tag=$2
tok=$(curl -s "https://ghcr.io/token?scope=repository:${repo}:pull" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -sI -H "Authorization: Bearer $tok" \
  -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
  "https://ghcr.io/v2/${repo}/manifests/${tag}" | awk -v r="$repo:$tag" 'tolower($1)=="docker-content-digest:"{d=$2} END{gsub("\r","",d); print r, d}'
EOF
for x in "helm-controller v1.6.5" "image-automation-controller v1.2.5" "image-reflector-controller v1.2.5" \
         "kustomize-controller v1.9.6" "notification-controller v1.9.4" "source-controller v1.9.6"; do
  bash -c "bash /tmp/flux-dist/dig.sh fluxcd/$x"; done
# PASS: each digest equals the one in /tmp/flux-dist/ctrl-expected.txt (measured identical 2026-10-05).
# CONTROL for the method: `bash /tmp/flux-dist/dig.sh fluxcd/source-controller v1.9.3` must print the
# live v1.9.3 digest from ctrl-before.txt (sha256:ff8f3c92...). A blank digest = registry/auth failure, not a pass.
```

Not taken, and why: the SOP step 2 guard (`retries: 0`, `cleanupOnFail: false` on both HRs)
protects against helm remediation half-reverting a slow controller roll. Measured: helm does
not wait for the controller roll — `helm history flux-instance` rev 6 reports "Upgrade complete"
at 14:26:17 on 2026-09-26 while the FluxInstance's first reconcile of that digest started at
14:26:24 (FluxInstance `status.history`) — rev 6 was run by helm-controller v1.6.3 on Helm v4,
the setup this plan runs under (the earlier rev-4 citation was a pre-2.9 Helm v3 run; corrected
2026-10-05 per review). The helm upgrade here only changes a CR, completes in
seconds, and finishes **before** helm-controller is rolled, so remediation has nothing to trip on.
Leaving it as-is keeps this a one-file commit with a one-commit revert. If remediation ever did
fire, gate 4.3 catches it (FluxInstance back on v2.9.3 while git says v2.9.6).

## 3. Steps

### 3.1 The bump (one commit, one file)

Dry-tested on a scratch copy on macOS 2026-10-05 (BSD sed). Resulting diff:

```
6c6
<     version: v2.9.3
---
>     version: v2.9.6
```

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's/^    version: v2\.9\.3$/    version: v2.9.6/' \
  kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml
git diff --stat -- kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml   # EXPECT: 1 file, 1 insertion, 1 deletion
mise exec -- yq '.instance.distribution.version' kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml   # EXPECT: v2.9.6

cat > /tmp/flux-dist/msg-core.txt <<'EOF'
feat(flux): distribution v2.9.3 -> v2.9.6 (plan flux-distribution-2.9.6)

source/kustomize-controller v1.9.6, helm-controller v1.6.5 (upstream Helm
v4.2.4), notification-controller v1.9.4, image-reflector/automation v1.2.5.
CRD served/storage versions unchanged; IUA refspec pattern added (unused here).

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/flux-system/flux-operator/instance/helm-values.yaml -F /tmp/flux-dist/msg-core.txt
git log -1 --format=%s          # MUST be the subject above (shared-worktree message swap guard); amend before push if not
git show --stat HEAD            # MUST list exactly helm-values.yaml
git rev-parse HEAD | tee /tmp/flux-dist/core-sha.txt
git push origin main
```

### 3.2 Propagation and the roll (observe; force only if stalled)

```bash
for i in $(seq 1 24); do
  R=$(mise exec -- kubectl -n flux-system get fluxinstance flux -o jsonpath='{.spec.distribution.version}{" "}{.status.conditions[?(@.type=="Ready")].status}{" "}{.status.lastAppliedRevision}')
  echo "$(date +%T) $R"; case "$R" in "v2.9.6 True v2.9.6@sha256:"*) break;; esac; sleep 20
done
mise exec -- kubectl -n flux-system get pods -o wide
```

EXPECT within ~5 min: spec `v2.9.6`, then Ready `True` with `lastAppliedRevision v2.9.6@sha256:…`
once the operator has rolled and waited for all six Deployments. If after 8 min the
FluxInstance spec is still `v2.9.3`, the webhook/source/kustomize leg did not fire;
`docs/sops/flux-upgrade.md` section 4 step 4 prescribes driving it in order, and only then:

```bash
mise exec -- flux -n flux-system reconcile source git flux-system
mise exec -- flux -n flux-system reconcile ks flux-instance
mise exec -- flux -n flux-system reconcile hr flux-instance
```

If the spec is `v2.9.6` but Ready stays `False` > 5 min: read
`mise exec -- kubectl -n flux-system logs deploy/flux-operator --tail=60`. A CRD `dry-run failed`
is NOT expected (1.4: no version change) — treat as a rollback trigger, not as Example B.

### 3.3 Follow-up commit = the end-to-end test (run as gate 4.7)

Docs only. `docs/infrastructure.md` lines 18, 134, 206. Dry-tested on a scratch copy
(BSD sed), `git diff --stat`: 1 file, 3 insertions, 3 deletions:

```
18c18   < | Flux | v2.9.3 |            > | Flux | v2.9.6 |
134c134 < Flux distribution is v2.9.3 (...) Controllers: source-controller v1.9.3, kustomize-controller v1.9.4, helm-controller v1.6.3, notification-controller v1.9.2, image-reflector-controller v1.2.3, image-automation-controller v1.2.3
        > Flux distribution is v2.9.6 (...) Controllers: source-controller v1.9.6, kustomize-controller v1.9.6, helm-controller v1.6.5, notification-controller v1.9.4, image-reflector-controller v1.2.5, image-automation-controller v1.2.5
206c206 < | Flux | v2.9.3 | GitOps operator |   > | Flux | v2.9.6 | GitOps operator |
```

The chart-version text on line 134 is owned by flux-fleet-0.60.0's follow-up and is not
touched. The "CLI ... v2.9.0, matched to the running distribution" phrase becomes loose; it
is the cli-tool-pins plan's to fix, not this one's.

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' -e 's/^| Flux | v2\.9\.3 |/| Flux | v2.9.6 |/' \
  -e 's/Flux distribution is v2\.9\.3 /Flux distribution is v2.9.6 /' \
  -e 's/source-controller v1\.9\.3, kustomize-controller v1\.9\.4, helm-controller v1\.6\.3, notification-controller v1\.9\.2, image-reflector-controller v1\.2\.3, image-automation-controller v1\.2\.3/source-controller v1.9.6, kustomize-controller v1.9.6, helm-controller v1.6.5, notification-controller v1.9.4, image-reflector-controller v1.2.5, image-automation-controller v1.2.5/' \
  docs/infrastructure.md
git diff --stat -- docs/infrastructure.md      # EXPECT: 1 file, 3 insertions, 3 deletions
cat > /tmp/flux-dist/msg-docs.txt <<'EOF'
docs(flux): infrastructure.md to distribution v2.9.6 controller versions

No cluster effect; doubles as the post-roll end-to-end reconcile test
(webhook -> source -> kustomize) for plan flux-distribution-2.9.6.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
git commit --only docs/infrastructure.md -F /tmp/flux-dist/msg-docs.txt
git log -1 --format=%s && git show --stat HEAD
git rev-parse HEAD | tee /tmp/flux-dist/docs-sha.txt
date -u +%Y-%m-%dT%H:%M:%SZ | tee /tmp/flux-dist/docs-push-time.txt
git push origin main
```

### 3.4 Retire

After section 4 is fully green, first catch the local CLI up (attended, never as root, outside
03:15-06:00): `mise install aqua:fluxcd/flux2@2.9.6` BEFORE editing `.mise.toml`, then change the
one line `"aqua:fluxcd/flux2" = "2.9.3"` -> `"2.9.6"` and verify `mise exec -- flux version --client`
prints 2.9.6 (commit with `git commit --only .mise.toml`). If cli-tool-pins has not run yet (pin
still 2.9.0), leave the CLI to cli-tool-pins and note it. Then: delete this plan file in the next commit (README: plans are
transient). Do NOT hand-close the six finding_refs: they are sweep-owned security rows —
let the next sweep resolve them and VERIFY that it did (`policy-cli.py finding show <F-id>`
for each; any still open after the sweep is a finding, not something to close by hand).
(Review 2026-10-05: the earlier `finding close` example also lacked the required `--reason`.) Then tell the
helm-drift-detection and flux-reconciler-impersonation owners their distribution-bound
premises/baselines need a re-run (section 6).

## 4. Verification

Re-establish the port-forward and `pq` from 2.d first.

### 4.1 Release and controller-roll health

```bash
mise exec -- kubectl -n flux-system get hr flux-instance -o jsonpath='{.status.history[0].status}{" "}{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
mise exec -- helm -n flux-system history flux-instance --max 2
mise exec -- kubectl -n flux-system get pods -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.phase}{" ready="}{.status.containerStatuses[0].ready}{" restarts="}{.status.containerStatuses[0].restartCount}{"\n"}{end}'
mise exec -- helm list -A --pending
```
PASS: `deployed True`; newest helm revision = before+1, "Upgrade complete"; 7 pods (6 controllers +
flux-operator) `Running ready=true restarts=0`; `helm list --pending` prints the header only.
FAIL looks like: a newest revision "Rollback to N" (remediation fired), a controller in
`CrashLoopBackOff`/`restarts=N`, or a release row in `--pending` (helm-controller was rolled
under an in-flight upgrade — that release needs `flux reconcile hr <name> --reset` per its own plan).

### 4.2 Every controller runs EXACTLY the target digest

```bash
mise exec -- kubectl -n flux-system get deploy helm-controller image-automation-controller image-reflector-controller \
  kustomize-controller notification-controller source-controller \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.template.spec.containers[0].image}{"\n"}{end}' \
  | diff /tmp/flux-dist/ctrl-expected.txt - && echo CONTROLLERS_ON_TARGET
mise exec -- kubectl -n flux-system get pods -o jsonpath='{range .items[*]}{.status.containerStatuses[0].imageID}{"\n"}{end}' | grep -c -E '6a669317|2ebeaa34|0d52fff5|840f3182|c83ce5c0|e1a2720d'
```
PASS: `CONTROLLERS_ON_TARGET`, and the running-pod imageID count is `6` (the spec could be right
while a pod still runs the old image — `feedback_rollout_status_old_generation`). FAIL looks like a
`diff` hunk naming a controller still on its v2.9.3 tag, or a count < 6. Proven able to fail:
pre-check 2.c ran the same diff against the live state and printed `NEGATIVE_CONTROL_OK`.

### 4.3 FluxInstance applied v2.9.6, spec intact, operator untouched

```bash
mise exec -- kubectl -n flux-system get fluxinstance flux -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{" "}{.status.lastAppliedRevision}{"\n"}' | tee /tmp/flux-dist/fi-rev-after.txt
mise exec -- kubectl -n flux-system get fluxinstance flux -o jsonpath='{.spec.sync.pullSecret}{"\n"}'
mise exec -- kubectl -n flux-system get gitrepository flux-system -o jsonpath='{.spec.secretRef.name}{"|"}{.spec.ignore}{"\n"}'
pq 'count(flux_instance_info{ready="True",revision=~"v2[.]9[.]6@sha256:.*"})'
pq 'count(flux_instance_info{revision=~"v2[.]9[.]3@sha256:.*"})'
```
PASS: `True v2.9.6@sha256:<new>` (record it — it is the rollback-confirmation baseline for any
later plan); pullSecret `flux-system-git-auth`; GitRepository `flux-system-git-auth|` + ignore
block containing `!/kubernetes`; PromQL `1` then `EMPTY`. FAIL looks like `v2.9.3@…` (helm
remediation or the operator reverted), an empty pullSecret (silent prune,
`docs/sops/flux-image-automation-push-auth.md`), or an ignore block without `!/kubernetes`
(every Kustomization re-downloads the whole repo). Proven able to fail: at 2.d the v2.9.6 query
returned `EMPTY` (measured 2026-10-05).

CONTROL: metric flux_instance_info — `count` with ready="True" and a `v2.9.6@sha256:` revision must be exactly 1, and the v2.9.3 series must be gone.

### 4.4 The flux-operator did NOT restart (the recovery path is intact)

```bash
mise exec -- kubectl -n flux-system get pods -l app.kubernetes.io/name=flux-operator -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.startTime}{"\n"}{end}' | diff /tmp/flux-dist/operator-pod-before.txt - && echo OPERATOR_UNCHANGED
pq 'count(flux_resource_info)'; cat /tmp/flux-dist/series-before.txt
pq 'count by (kind) (flux_resource_info)'
```
PASS: `OPERATOR_UNCHANGED`; `count(flux_resource_info)` within ±5 of baseline and all 10 kinds
present (HelmRelease, HelmChart, HelmRepository, Kustomization, GitRepository, OCIRepository,
Receiver, ImagePolicy, ImageRepository, ImageUpdateAutomation).
FAIL looks like a diff hunk (operator restarted — not part of this change; investigate before
trusting section 5 step 2), `EMPTY` (scrape broken — FAIL, never pass), or a missing kind.

CONTENTS ASSERTION: the operator's report of the whole Flux fleet is complete after the controller swap — measured by `count(flux_resource_info)` and its per-kind breakdown, compared to the 2.d baseline.
CONTROL: metric flux_resource_info — `count()` within ±5 of baseline with all 10 kinds present.

### 4.5 The CRD change landed (contents of what changed)

```bash
mise exec -- kubectl get crd imageupdateautomations.image.toolkit.fluxcd.io -o json \
  | python3 -c 'import sys,json; s=json.load(sys.stdin)["spec"]["versions"]; v=[x for x in s if x["storage"]][0]; print(v["name"], repr(v["schema"]["openAPIV3Schema"]["properties"]["spec"]["properties"]["git"]["properties"]["push"]["properties"]["refspec"].get("pattern")))'
mise exec -- kubectl get crd imageupdateautomations.image.toolkit.fluxcd.io -o jsonpath='{.status.storedVersions}{"\n"}'
mise exec -- kubectl get imageupdateautomations.image.toolkit.fluxcd.io -A \
  -o jsonpath='{range .items[*]}{.metadata.namespace}{"/"}{.metadata.name}{" suspend="}{.spec.suspend}{" ready="}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
```
PASS: `v1 '^$|^[^+:]'`; storedVersions `["v1"]`; all 6 automations listed, every unsuspended one
`ready=True` (2 are suspended by design — open finding, not this plan's). FAIL looks like `None`
(CRD not updated: the operator did not apply the v2.9.6 set) or an unsuspended automation
`ready=False` (it now fails the new validation). Proven able to fail: 2.c printed `None`.

### 4.6 The cluster still reconciles end to end (10-minute soak)

```bash
sleep 600
mise exec -- kubectl get kustomizations.kustomize.toolkit.fluxcd.io,helmreleases.helm.toolkit.fluxcd.io -A -o json \
  | python3 -c 'import sys,json; it=json.load(sys.stdin)["items"]; bad=[i["metadata"]["namespace"]+"/"+i["metadata"]["name"] for i in it if not i["spec"].get("suspend") and not any(c["type"]=="Ready" and c["status"]=="True" for c in i.get("status",{}).get("conditions",[]))]; print("total=%d notready=%d %s" % (len(it), len(bad), bad))'
cat /tmp/flux-dist/total-before.txt
pq 'count(flux_resource_info{ready="False",suspended="False"})'
pq 'count(ALERTS{alertname=~"FluxResourceNotReady|FluxSourceStalled|FluxMetricsAbsent",alertstate=~"pending|firing"})'
mise exec -- kubectl get events -n flux-system --field-selector type=Warning --sort-by=.lastTimestamp | tail -15
```
PASS: `notready=0` with `total` within ±3 of the 2.d baseline; both PromQL lines `EMPTY` (valid only
because 4.4 proved the series exist and 2.d's positive control proved the ready="False" query can
match); no Warning events newer than the roll other than transient `artifact not found` /
`dependency not ready` (SOP Test 2: source-controller rebuilds artifacts on restart; must be gone
by the end of the soak). FAIL looks like `notready=N [ns/name...]` — the message then tells you
which controller regressed (helm: upgrade/rollback errors; kustomize: build/postBuild errors).

CONTROL: alertname FluxResourceNotReady — must not be pending or firing after the soak.
CONTROL: alertname FluxSourceStalled — must not be pending or firing (source-controller on v1.9.6 cannot fetch).
CONTROL: alertname FluxMetricsAbsent — must not be firing; informational inside the window (30m `for`), covered by 4.4.

### 4.7 A real reconcile through every new controller

(a) **Webhook -> source -> kustomize**: run section 3.3 (the docs commit), then:

```bash
DSHA=$(cat /tmp/flux-dist/docs-sha.txt)
for i in $(seq 1 12); do
  R=$(mise exec -- kubectl -n flux-system get ks flux-system cluster-apps flux-instance -o jsonpath='{range .items[*]}{.status.lastAppliedRevision}{" "}{end}')
  echo "$(date +%T) $R"; [ "$(echo $R | grep -o "$DSHA" | wc -l | tr -d ' ')" = "3" ] && break; sleep 15
done
mise exec -- kubectl -n flux-system logs deploy/notification-controller --since-time="$(cat /tmp/flux-dist/docs-push-time.txt)" | grep -ci 'handling github event: push'
```
PASS: all three Kustomizations report `refs/heads/main@sha1:<docs-sha>` within 3 min, and the NEW
notification-controller pod logged at least `1` GitHub push event after the push time (proves the
Receiver works, not just the 1-minute poll). Measured: a non-`kubernetes/` commit does advance
`lastAppliedRevision` (2026-10-05: all ks on the plan-only commit 3c8833b8), and the log line exists
in the current pod (`handling GitHub event: push`, 07:52:58Z). FAIL looks like a Kustomization
stuck on the core sha (kustomize/source regression) or a `0` count with revisions advancing only
after ~1 min (the receiver is dead; the poll is hiding it).

(b) **helm-controller on upstream Helm performs a real upgrade** (SOP Test 2 calls for a forced
end-to-end reconcile; this is its helm half, on a stateless, unused-by-anyone release):

```bash
mise exec -- helm -n default history echo-server --max 1
mise exec -- flux -n default reconcile hr echo-server --force
mise exec -- helm -n default history echo-server --max 2
mise exec -- kubectl -n default get hr echo-server -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{" "}{.status.history[0].status}{"\n"}'
```
PASS: a new helm revision (13 -> 14 as of 2026-10-05) "Upgrade complete", HR `True deployed`.
FAIL looks like "Upgrade failed"/"Rollback to N" or Ready `False` — a Helm-library regression that
every other HelmRelease will hit on its next real upgrade (i.e. the next window's Step 0): roll back.
Do NOT use `flux-instance` for this test: a failed forced upgrade there remediates by rolling back
to the v2.9.3 values revision.

(c) **image-reflector + image-automation**: 

```bash
mise exec -- kubectl get imagerepositories.image.toolkit.fluxcd.io -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"/"}{.metadata.name}{" interval="}{.spec.interval}{" "}{.status.lastScanResult.scanTime}{" "}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
```
PASS: every ImageRepository `True`; every one with `interval=10m` (the absenty pair, measured
2026-10-05) shows a `scanTime` later than the roll by the end of 4.6's soak. The `1h`-interval
ones need only `True` (they will not rescan inside the window). FAIL: any `False`, or a 10m
repository with no scan after the roll — the new image-reflector-controller is not scanning.

```bash
kill $PF 2>/dev/null
```

## 5. Rollback

**Trigger:** any FAIL in 4.1-4.7.

**The self-revert hazard, stated plainly.** The normal revert is a git commit that the *new*
source-controller must fetch, the *new* kustomize-controller must turn into a ConfigMap, and the
*new* helm-controller must upgrade into the FluxInstance. If any of those three is what broke,
**a pushed `git revert` will sit in git and never reach the cluster.** The out-of-band path below
does not use any of the six controllers: it talks to the apiserver directly and lets the
**flux-operator** (which this plan does not touch — gate 4.4) re-render the v2.9.3 controllers.
Pre-check 2.f proved that path is admissible (server-side dry run).

1. **GitOps revert (when source/kustomize/helm-controller are healthy, e.g. the failure is in
   notification/image-* or a 4.7 functional regression):**
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git revert --no-edit $(cat /tmp/flux-dist/core-sha.txt)
   git log -1 --format=%s && git show --stat HEAD     # helm-values.yaml only
   git push origin main
   ```
   Then watch 3.2's loop for `v2.9.3 True v2.9.3@sha256:`. If the FluxInstance spec is not back to
   `v2.9.3` within 8 minutes, go to step 2 — do not wait longer, the revert is not being applied.

2. **Flux-independent (a controller in the apply chain is broken, or step 1 did not converge):**
   ```bash
   # a) stop helm-controller from re-asserting v2.9.6 if it comes back mid-recovery
   mise exec -- kubectl -n flux-system patch hr flux-instance --type merge -p '{"spec":{"suspend":true}}'
   # b) put the distribution back directly on the CR; the flux-operator reconciles it on its own
   mise exec -- kubectl -n flux-system patch fluxinstance flux --type merge -p '{"spec":{"distribution":{"version":"v2.9.3"}}}'
   mise exec -- kubectl -n flux-system annotate fluxinstance flux "reconcile.fluxcd.io/requestedAt=$(date +%s)" --overwrite
   # (annotation names per upstream docs/api/v1/fluxinstance.md: reconcile.fluxcd.io/requestedAt
   #  triggers; fluxcd.controlplane.io/reconcile=disabled pauses)
   # c) watch the six controllers return to the 2.c snapshot
   mise exec -- kubectl -n flux-system get deploy helm-controller image-automation-controller image-reflector-controller \
     kustomize-controller notification-controller source-controller \
     -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.template.spec.containers[0].image}{"\n"}{end}' \
     | diff /tmp/flux-dist/ctrl-before.txt - && echo CONTROLLERS_BACK_ON_V2.9.3
   ```
   The FluxInstance is a Helm-owned object, but helm-controller does not correct drift here
   (no `driftDetection` on any HR until helm-drift-detection lands — re-check that before
   relying on this), so the patch holds while `hr/flux-instance` is suspended.
   **If the flux-operator itself is wedged too** (it should not be — it did not change): disable
   its reconcile of the instance and pin the images by hand from the snapshot:
   ```bash
   mise exec -- kubectl -n flux-system annotate fluxinstance flux fluxcd.controlplane.io/reconcile=disabled --overwrite
   while read -r name image; do mise exec -- kubectl -n flux-system set image deploy/$name manager=$image; done < /tmp/flux-dist/ctrl-before.txt
   ```
   (container name `manager` in all six; check with
   `kubectl -n flux-system get deploy source-controller -o jsonpath='{.spec.template.spec.containers[*].name}'`
   before relying on it.) Restore CRDs from `/tmp/flux-dist/flux-crds-before.yaml` with
   `kubectl apply -f` ONLY if a v2.9.3 controller refuses to start on a schema error (not expected:
   v2.9.6 only adds a pattern). If even this fails: `docs/sops/disaster-recovery.md`.

   **Then make git match, in this order:** once the v2.9.3 controllers reconcile (a Kustomization
   advances to a new sha), push the step-1 revert, wait until `kubectl -n flux-system get ks flux-instance`
   shows the revert sha, then un-suspend:
   `kubectl -n flux-system patch hr flux-instance --type merge -p '{"spec":{"suspend":false}}'`,
   and remove `fluxcd.controlplane.io/reconcile` if it was set
   (`kubectl -n flux-system annotate fluxinstance flux fluxcd.controlplane.io/reconcile-`).
   Un-suspending BEFORE git is reverted re-applies v2.9.6.

3. **Confirm the cluster is back:** `CONTROLLERS_BACK_ON_V2.9.3` (diff vs `ctrl-before.txt` silent);
   FluxInstance `True v2.9.3@sha256:…` (the digest may differ from `fi-rev-before.txt` only if the
   manifests artifact moved; the version prefix must be v2.9.3);
   `count(flux_instance_info{ready="True",revision=~"v2[.]9[.]3@sha256:.*"})` -> `1`;
   4.6 PASS criteria (notready=0 vs baseline); `helm list -A --pending` empty; `hr/flux-instance`
   Ready and not suspended. The IUA CRD reverts to no `pattern` (2.c value `None`).

## 6. Interference notes

- **Run order inside the window:** Step 0 (safe-update apply) runs first in every window and
  relies on Flux to apply AND auto-revert its batch. Start this plan only after Step 0's
  health gate is green and its commits are applied (pre-check 2.b). After this plan, the next
  window's Step 0 is the first fleet-wide exercise of helm-controller on upstream Helm v4.2.4 —
  the window agent should read that Step 0's result with that in mind (gate 4.7b is a sample of one).
- **exclusive: true**: all six controllers restart within ~1-2 minutes. A co-scheduled plan whose
  helm upgrade is in flight when helm-controller rolls is left `pending-upgrade`; with
  `retries: 0` (several plans set that) nothing recovers it. The `conflicts_with` list names the
  known ones; `exclusive` covers the rest.
- **Receiver gap:** notification-controller restarts; a GitHub push during the ~30 s gap is still
  picked up by the GitRepository 1-minute poll. No alerting impact (Alertmanager does not route via
  notification-controller here).
- **Earliest slot / soak:** depends_on flux-fleet-0.60.0 (nightly:2026-10-06, needs GO). Leave at
  least one full nightly Step 0 between the two (operator change soaks a day; a regression is then
  attributable). Earliest sensible: an attended on-demand NOW run on 2026-10-07 evening, or
  `nightly:2026-10-08` with an explicit GO and the operator reachable in the morning. sat 10-10
  holds jellyfin-12.1 and sun 10-11 holds the exclusive flux-reconciler-impersonation placeholder,
  so neither can take an exclusive plan as things stand.
- **flux-reconciler-impersonation:** its FluxInstance patch changes the same digest this plan
  changes; whichever runs second must re-baseline its digest premises (do not wave a digest
  mismatch through). Prefer this plan first (smaller, version-only).
- **helm-drift-detection:** its premise `flux-distribution-is-2.9` (expect_contains `v2.9.`) still
  passes on v2.9.6, but its section 3.0.0 proof was measured on the v2.9.3 controllers; its own
  text says a distribution change needs that step re-run.
- **flux-oci-chart-sources:** source-controller v1.9.4 resolves OCI charts by digest for
  verification; that plan's stages should be measured on v1.9.6, i.e. after this lands.
- **New-chart rule (helm-controller v1.6.5, #1589):** from now on a chart with a `crds/` directory
  needs `install.crds`/`upgrade.crds: CreateReplace`, or its CRDs are created once and never
  updated. Every current such chart already sets it (section 1.4). Repo correction suggested for
  `docs/sops/new-deployment-blueprint.md` (not made by this plan).
- **Orphans noticed, not touched:** 12 Kong CRDs labelled for a `monitoring/kubernetes-dashboard`
  HelmRelease that no longer exists.
- **`.mise.toml` flux CLI 2.9.0** stays; owned by the cli-tool-pins plan. `docs/sops/flux-upgrade.md`
  section 2 asks to keep it aligned; a 2.9.x patch skew is harmless for `flux get/reconcile`.
