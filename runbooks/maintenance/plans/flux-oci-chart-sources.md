---
plan_id: flux-oci-chart-sources
component: flux-sources
pr: null                              # No Renovate PR exists or can exist: this is a
                                      # source-KIND refactor, not a version bump. Renovate
                                      # diffs versions inside a source it already
                                      # understands; it has no opinion about which KIND of
                                      # source holds the chart.
kind: infra
current: "28 HTTP HelmRepository chart sources (all 28 referenced by a HelmRelease) + 9 type:oci HelmRepository + 4 OCIRepository (ONE is this plan's: network/k8s-gateway; three are the ARC runner charts from the gha-fleet work) + 4 GitRepository (flux-system, csi-driver-smb, oc8, plex) — re-measured live 2026-11-03. Stage 1 is COMPLETE (the last orphan, external-secrets, was deleted by 67216b3b / F-fb2cc8a2 on 2026-10-23); stage 2 executed by another route (GitRepository); plex moved to a GitRepository (102ec800). Cluster and Flux CLI are v2.9.6."
target: "every referenced chart with an immutable OCI source migrated to OCIRepository pinned by tag AND digest; the rest explicitly parked with a named reason — delivered in 11 stages, each independently abandonable. The sun-attended:2026-12-13 slot carries STAGE 3 ONLY (six releases: four restart nothing, falco and node-feature-discovery each restart once), proceeding per release when Step 0b prints G3-NON-REGRESSION and the operator GO in section 1.00 is recorded."
update_type: refactor
risk: high                            # NOT from any single stage. Two drivers, both
                                      # measured, both in §1: (a) the migration ROLLS the
                                      # workload — 9 releases / 17 workloads in stages 3-6 restart
                                      # (re-measured 2026-11-03 with the build-metadata method,
                                      # §1.0), and the set includes the CNI DaemonSet,
                                      # longhorn-manager, the cert-manager webhook and the SSO
                                      # server; (b) every stage edits the Kustomization that
                                      # gates delivery for the whole cluster. Per-stage risk is
                                      # in the stage table — stages 0, 1, 3 and 4 are genuinely
                                      # low. The 12-13 slice (stage 3) is low risk; two of its six releases (falco, node-feature-discovery) restart once.
est_duration_min: 100                 # RE-SCOPED 2026-11-03 from 30 (per stage) to the figure for
                                      # the ONE slice this window carries: Stage 3 = intel x3,
                                      # paperless-ngx ~10 min each, node-feature-discovery and falco
                                      # ~20 each (post-roll gates), + 20 overhead (section 1.00). Later stages are separate slices with their own
                                      # figures in §3.1 and need their own window; the whole
                                      # programme (~6h) must never be scheduled as one unit.
needs_reboot: false                   # No node reboot anywhere in this plan. But see §6:
                                      # a Talos roll RESTARTS source-controller, which is
                                      # the event this plan exists to survive, so it must
                                      # not share a window with one.
touches:
  namespaces: [flux-system, kube-system, cert-manager, storage, network, monitoring, office, ai, security]
  # Namespaces of the stages that are executable (3, 4, 5, 6, 10). Stage 7's ten HTTP-only charts
  # (databases, media, home-automation, default, office) and unpoller (monitoring, stage 8) are
  # PARKED; whichever slice un-parks them adds its own namespaces in its own plan revision.
  resources:
    - "kustomization/cluster-meta (spec.wait:true — EVERY stage removes members from the gate that blocks cluster-apps)"
    - "helmrepository/* in flux-system (28 HTTP objects: 17 replaced by stages 3-6, 1 blocked (unpoller), 10 parked (stage 7))"
    - "ocirepository/* (NEW, one per migrated app, in the app's own namespace)"
    - "helmrelease/* (up to 19 releases switch spec.chart.spec -> spec.chartRef across stages 3-6; stage 3 = 6 of them)"
    - "helmrelease/kube-system/intel-device-plugin-{operator,gpu,npu}, helmrelease/kube-system/node-feature-discovery, helmrelease/office/paperless-ngx, helmrelease/security/falco (STAGE 3 — the 12-13 slice; ONLY falco (daemonset, 3 pods) and node-feature-discovery (worker daemonset + master deployment) restart, once each)"
    - "daemonset/cilium + deployment/cilium-operator (stage 6, ROLL)"
    - "daemonset/longhorn-manager + deployment/longhorn-{ui,driver-deployer} (stage 6, ROLL — 79 volumes)"
    - "deployment/cert-manager{,-webhook,-cainjector} (stage 6, ROLL — webhook gap = Certificate admission failures)"
    - "deployment/authentik-{server,worker} + statefulset/authentik-postgresql (stage 5, ROLL — SSO)"
    - "deployment/grafana, deployment+statefulset/open-webui, deployment/anythingllm, deployment/nextcloud, deployment/otel-operator + daemonset/otel-operator-daemon-collector (stage 5, ROLL)"
    - "runbooks/check-all-versions.py + runbooks/coverage.py (Stage 0 — chartRef blindness; DONE 97c3e913)"
    - "fluxinstance/flux spec.kustomize.patches (Stage 10 — emptyDir sizeLimit)"
  shared: [flux-sources, cni-adjacent, cert-manager, storage/longhorn, monitoring, authentik, public-dns]
depends_on: []
conflicts_with: [flux-reconciler-impersonation, helm-drift-detection, flux-fleet-0.62.0, flux-fleet-0.62.1, etcd-timeouts-5000-500, talos-linux-1.14.5, longhorn-1.13.0, authentik-2026.8.5, grafana-14.1.0, edot-collector-0.164.0, descheduler-0.37.0, anythingllm-1.19, jellyfin-3.7.0, tube-archivist-0.6.0, frigate-reolink-go2rtc-flv, envoy-proxy-config-distroless-v1.39.4, redis-fleet-8.10.3]   # RE-PLANNED 2026-11-03 against every open plan's frontmatter
  # 2026-11-03: dropped dead refs otel-operator-0.23.0 (executed out-of-band 0e976cf5), jellyfin-12.1 (superseded by the 12.2 plan, itself later superseded), paperless-db-13.0.2 (executed a99794cc).
  # 2026-11-03: ADDED flux-fleet-0.62.0/0.62.1 (draft: flux-operator + flux-instance HRs and fluxinstance/flux, which Stage 10 patches; each lists this plan),
  #   etcd-timeouts-5000-500 (touches flux-system and perturbs the apiserver every Flux apply talks to; sun 11-08), authentik-2026.8.5 (sat 11-21; stage 5 switches authentik's chart source),
  #   descheduler-0.37.0 / anythingllm-1.19 / jellyfin-3.7.0 (same HelmReleases as stage 4 / 5 / 7), edot-collector-0.164.0 (monitoring: the instrument our verification reads).
  # Window ordering around sun-attended:2026-12-13 (all measured 2026-11-03): talos-linux-1.14.5 sun 11-22 (restarts source-controller; three weeks earlier, so a cold cache is long gone),
  #   redis-fleet-8.10.3 sun 11-29, helm-drift-detection sat 11-28 (P1 warn: adds spec.driftDetection to every HelmRelease, so stage 3's helmrelease.yaml edits must be rebased on it),
  #   envoy-proxy-config-distroless-v1.39.4 sun 12-06 (a week earlier; its own gateway restart gate must be finished and green before this plan starts), longhorn-1.13.0 sun 11-15.
  #   The same-night kube-prometheus-stack bump rule: none is windowed on 12-13 today; if one is slotted, move it — stage 3 verification reads Prometheus for the node-feature and gpu series.
  # 2026-11-03: REMOVED otel-operator-0.26.1 (plan retired cdf1cf53; the chart bump landed in 5aa609d5, live pin 0.26.1) -- dead ref. The same dead ref was removed from five sibling plans' conflicts_with.
  # About twenty other plans list this plan reciprocally only because it edits HelmReleases; none shares a surface with the stage that runs on 12-13 and they are not repeated here.
security_ref: null                     # F-0e310ef2 (plan-section, not security) RESOLVED 102ec800; no security finding drives this plan
capability_change: true                # Stage 9 gives Flux chart-provenance ENFORCEMENT it
                                       # does not have today (spec.verify fails CLOSED), and
                                       # Stage 10 adds an eviction limit (emptyDir sizeLimit).
                                       # Stage 3 alone (the 12-13 slice) is same-behaviour; the
                                       # programme as a whole is not, so this stays true.
rollback_class: git-revert
finding_refs: [F-0e310ef2, F-764e4fc3]   # both RESOLVED (102ec800 / 2026-09-20); kept as provenance -- no open driver
premises:
  - id: cluster-meta-still-gates
    why: "The whole plan exists because cluster-meta wait:true blocks cluster-apps; if that changed, the risk model changed."
    run: kubectl get kustomization cluster-meta -n flux-system -o jsonpath='{.spec.wait}'
    expect_exact: "true"
  - id: http-helmrepos-28
    why: "Scope is 28 HTTP HelmRepositories, all referenced (external-secrets was deleted by 67216b3b). Fewer means a stage ran outside this plan; more means a new HTTP source appeared."
    run: kubectl get helmrepository -A -o jsonpath='{range .items[*]}{.spec.type}{"\n"}{end}' | grep -c '^$'
    expect_exact: "28"
  - id: oci-helmrepos-9
    why: "The legacy type:oci HelmRepositories are out of scope; a tenth means someone chose the type:oci fallback of §1.4 for a stage."
    run: kubectl get helmrepository -A -o jsonpath='{range .items[*]}{.spec.type}{"\n"}{end}' | grep -c '^oci$'
    expect_exact: "9"
  - id: ocirepository-exact-set
    why: "Exactly four OCIRepositories exist: k8s-gateway (this plan's one migration) plus three ARC runner charts (gha-fleet, NOT this plan). Any other name means a stage ran outside this plan; a missing one means a source was lost."
    run: kubectl get ocirepository -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}{" "}{end}'
    expect_exact: "arc-build/gha-runner-scale-set arc-system/gha-runner-scale-set-controller ci-runner/gha-runner-scale-set network/k8s-gateway"
  - id: gitrepository-exact-set
    why: "The GitRepository chart sources are csi-driver-smb (stage 2, done), plex (done) and oc8, plus flux-system itself; a fifth means a stage-7 chart moved outside this plan."
    run: kubectl get gitrepository -A -o jsonpath='{range .items[*]}{.metadata.name}{" "}{end}'
    expect_exact: "csi-driver-smb flux-system oc8 plex"
  - id: stage3-releases-still-http
    why: "Stage 3 migrates exactly six releases whose sourceRef is intel (3), node-feature-discovery, gabe565 or falcosecurity. Fewer than six means part of the slice already ran."
    run: kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.chart.spec.sourceRef.name}{"\n"}{end}' | grep -c -x -e intel -e node-feature-discovery -e gabe565 -e falcosecurity
    expect_exact: "6"
  - id: chartref-roll-still-observed
    why: "§1.4's roll prediction rests on the build-metadata chart label."
    run: kubectl get deploy k8s-gateway -n network -o jsonpath='{.spec.template.metadata.labels.helm\.sh/chart}'
    expect_contains: "_3783b0b4bc41"
  - id: unpoller-still-2.4.0
    why: "Stage 8 is blocked only while the pin predates the OCI registry's first tag (2.5.0)."
    run: kubectl get helmrelease -n monitoring -o jsonpath='{range .items[*]}{.spec.chart.spec.chart}={.spec.chart.spec.version}{"\n"}{end}' | grep '^unpoller='
    expect_exact: "unpoller=2.4.0"
  - id: flux-distribution-v2.9.6
    why: "§3.7 (spec.verify) and §3.8 (source-controller emptyDir) were measured against Flux v2.9.6; a different distribution means source-controller changed and those claims need re-measuring."
    run: kubectl get fluxinstance flux -n flux-system -o jsonpath='{.spec.distribution.version}'
    expect_exact: "v2.9.6"
  - id: falco-checksum-config-prefix
    why: "Section 1.00's falco figures (the predicted checksum change and the 34/34/3/3/3 baseline) were measured against this pod-template checksum; a different prefix means the falco release changed (a Step 0 chart bump?) and the restart prediction must be re-derived."
    run: kubectl get ds falco -n security -o jsonpath='{.spec.template.metadata.annotations.checksum/config}'
    expect_matches: "^2bd4ff4b"
  - id: nfd-worker-checksum-config-prefix
    why: "Same for node-feature-discovery: the worker DaemonSet's pod-template checksum/config prefix measured 2026-11-03."
    run: kubectl get ds node-feature-discovery-worker -n kube-system -o jsonpath='{.spec.template.metadata.annotations.checksum/config}'
    expect_matches: "^c66cab76"
  - id: source-controller-emptydirs-unbounded
    why: "Stage 10 exists because both emptyDir volumes have no sizeLimit; once a limit is set this stage is done and must not be re-run."
    run: kubectl get deploy source-controller -n flux-system -o jsonpath='{.spec.template.spec.volumes[*].emptyDir}'
    expect_exact: "{} {}"
status: draft     # RE-PLANNED 2026-11-03 after the premise check failed (http-helmrepos 29->28, ocirepository 1->4). Substance changed (§1.0): the earlier review 'ready-for-go@2026-09-28' is CLEARED and a plan-reviewer must re-review before this is vetted. Was vetted.
review: null      # was ready-for-go@2026-09-28; cleared 2026-11-03 (the plan was materially amended)
window: "sun-attended:2026-12-13"   # UNCHANGED. Scheduled 2026-10-05 (operator "plan all and time them"); MOVED 2026-11-02 from sun-attended:2026-11-22 (talos-linux-1.14.5 takes that Sunday). Re-checked 2026-11-03 against every open plan: no hard conflict forces a move.
                                       # HUMAN-GATED (autonomy_override, capability change) -> operator GO (the GO text is in §1.00 and includes the falco and NFD restarts). This slot carries
                                       # STAGE 3 ONLY. Each release proceeds iff its Step 0b prints G3-NON-REGRESSION; D1 is a separate policy question, not a prerequisite.
autonomy_override: human-gated         # Staged programme; est_duration_min is per slice; the
                                       # riskiest stages roll the CNI and storage. The scheduler
                                       # must not treat this as one unit.
sops_refs:
  - docs/sops/flux-chart-source-pinning.md
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/maintenance-windows.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/audit-script-correctness.md
  - docs/sops/storage-safety.md
  - docs/sops/longhorn.md
  - docs/sops/k8s-gateway-dns.md
  - docs/sops/authentik.md
  - docs/sops/flux-upgrade.md
  - docs/sops/flux-dependency-revision-gate.md
generated: "2026-09-11"
replanned: "2026-11-03"
---

# Migrate HTTP chart sources to OCIRepository + HelmRelease.chartRef

## 1. Summary & why held

### 1.00 Stage 3 execution brief — the 2026-12-13 window (read this first, then §3.2 for step detail)

**What it does.** Moves six Flux chart sources from an HTTP `HelmRepository` to a digest-pinned `OCIRepository` + `chartRef` (one commit per release). **Four of the six restart nothing; TWO restart workloads** — this corrects the earlier "no workload roll" claim, which was wrong (plan-reviewer, 2026-11-03):

| order | release (ns) | files in the commit (`git commit --only` list, exact) | restarts? | extra gate |
|---|---|---|---|---|
| 1 | `intel-device-plugin-operator` (kube-system) | `kubernetes/apps/kube-system/intel-device-plugin/app/{ocirepository.yaml (new),kustomization.yaml,helmrelease.yaml}` | no | operator Deployment pod name + `creationTimestamp` unchanged |
| 2 | `intel-device-plugin-gpu` (kube-system) | `kubernetes/apps/kube-system/intel-device-plugin/gpu/{ocirepository.yaml (new),kustomization.yaml,helmrelease.yaml}` | no | DaemonSet `intel-gpu-plugin-intel-gpu-plugin` pods unchanged + node snapshot identical |
| 3 | `intel-device-plugin-npu` (kube-system) | `kubernetes/apps/kube-system/intel-device-plugin/vpu/{ocirepository.yaml (new),helmrelease.yaml}` **and** `kubernetes/flux/meta/repositories/helm/{intel.yaml (deleted),kustomization.yaml}`. **`vpu/` has NO `kustomization.yaml`** (Flux auto-generates one, so it picks up the new file by itself): do not name a kustomization path here, `git commit --only` fails on a path that does not exist | no | DaemonSet `intel-npu-plugin-intel-npu-plugin` pods unchanged + node snapshot identical |
| 4 | `node-feature-discovery` (kube-system) | `kubernetes/apps/kube-system/node-feature-discovery/app/{ocirepository.yaml (new),kustomization.yaml,helmrelease.yaml}` + `kubernetes/flux/meta/repositories/helm/{node-feature-discovery.yaml (deleted),kustomization.yaml}` | **YES: worker DaemonSet (3 pods) + master Deployment** | §4.2 NFD row |
| 5 | `paperless-ngx` (office) | `kubernetes/apps/office/paperless-ngx/app/{ocirepository.yaml (new),kustomization.yaml,helmrelease.yaml}` + `kubernetes/flux/meta/repositories/helm/{gabe565.yaml (deleted),kustomization.yaml}` | no | pod name + `creationTimestamp` identical; HTTPRoute serves real content |
| 6 | `falco` (security) | `kubernetes/apps/security/falco/app/{ocirepository.yaml (new),kustomization.yaml,helmrelease.yaml}` + `kubernetes/flux/meta/repositories/helm/{falcosecurity.yaml (deleted),kustomization.yaml}` | **YES: DaemonSet `falco`, 3 pods, `maxUnavailable: 1`** | §4.2 falco row |

**Literal per-release environment** (paste before each release's §3.2 steps; `CHART` is the chart name Step 3 pulls, `OCINAME` the OCIRepository name, `WL` empty unless stated):

```bash
# 1 operator
export NS=kube-system REL=intel-device-plugin-operator CHART=intel-device-plugins-operator OCINAME=intel-device-plugins-operator REPO=intel OCI_PATH=ghcr.io/intel/helm-charts/intel-device-plugins-operator APPDIR=kubernetes/apps/kube-system/intel-device-plugin/app WL=
# 2 gpu
export NS=kube-system REL=intel-device-plugin-gpu CHART=intel-device-plugins-gpu OCINAME=intel-device-plugins-gpu REPO=intel OCI_PATH=ghcr.io/intel/helm-charts/intel-device-plugins-gpu APPDIR=kubernetes/apps/kube-system/intel-device-plugin/gpu WL="ds/intel-gpu-plugin-intel-gpu-plugin"
# 3 npu
export NS=kube-system REL=intel-device-plugin-npu CHART=intel-device-plugins-npu OCINAME=intel-device-plugins-npu REPO=intel OCI_PATH=ghcr.io/intel/helm-charts/intel-device-plugins-npu APPDIR=kubernetes/apps/kube-system/intel-device-plugin/vpu WL="ds/intel-npu-plugin-intel-npu-plugin"
# 4 node-feature-discovery
export NS=kube-system REL=node-feature-discovery CHART=node-feature-discovery OCINAME=node-feature-discovery REPO=node-feature-discovery OCI_PATH=registry.k8s.io/nfd/charts/node-feature-discovery APPDIR=kubernetes/apps/kube-system/node-feature-discovery/app WL=
# 5 paperless-ngx
export NS=office REL=paperless-ngx CHART=paperless-ngx OCINAME=paperless-ngx REPO=gabe565 OCI_PATH=ghcr.io/gabe565/charts/paperless-ngx APPDIR=kubernetes/apps/office/paperless-ngx/app WL=
# 6 falco
export NS=security REL=falco CHART=falco OCINAME=falco REPO=falcosecurity OCI_PATH=ghcr.io/falcosecurity/charts/falco APPDIR=kubernetes/apps/security/falco/app WL=
```

**Do NOT delete `intel.yaml` in commits 1 and 2.** Three HelmReleases (`intel-device-plugin-{operator,gpu,npu}`) use `HelmRepository/intel`; deleting it after the first would leave the other two without a source, inside the `cluster-meta` gate. Only commit 3 (the last Intel release) deletes it, and only after the Step 5 deletion gate reads 0.

**Why two restart (measured 2026-11-03, reviewer-confirmed).** Under `chartRef`, helm-controller records the chart version as `<VER>+<first 12 hex of the pinned digest>`. falco's and NFD's ConfigMap templates embed the `helm.sh/chart` label, so their rendered ConfigMap changes and the pod-template annotations `checksum/config` (falco also `checksum/rules`) change with it; the old-render checksums equal the live annotations exactly (falco `2bd4ff4b…`, verified against the live DaemonSet). The first-draft predictor only looked for `helm.sh/chart` in pod-template *labels* and was blind to it. The replacement predictor (§3.2 Step 4, script in §8) re-renders with the build-metadata version and diffs every workload's `template:` block: falco prints two `WILL ROLL` lines, NFD two (worker DaemonSet, master Deployment) plus an informational hook-Job line, paperless-ngx and all three Intel releases print `ROLL-PREDICTION: none`.

**Operator GO text (this is the acceptance D3 did not cover; record it with `home-operation decide`):** *"GO flux-oci-chart-sources Stage 3 in sun-attended:2026-12-13: six chart-source moves. I accept one restart of falco (3 pods, one node at a time, a per-node detection gap while its pod restarts) and one restart of node-feature-discovery (worker DaemonSet + master Deployment) on the forward move, and one more of each on a rollback. No other workload restarts."*

**Budget and order.** Order as in the table: operator, gpu, npu, node-feature-discovery, paperless-ngx, falco (NFD's and falco's post-roll checks run last because they are the slow ones). `est_duration_min: 100` = 6 × ~10 min edits/commits (Intel and paperless ~10, NFD and falco ~20 including their post-roll gates) + 20 min fixed overhead. This is on top of the window's own 20-min Step 0 reserve; the slot has 180 schedulable minutes.

**Window-agent rules.**
1. **Step 0 (the safe-update apply) runs first in every window, including this one.** Re-run §2's pre-checks AFTER it: Step 0 can bump a chart this plan is about to migrate.
2. **Re-read the live `VER` of every release** (§3.2 reads it from the HelmRelease; never type one) and re-derive each digest from the registry at execution time. The pins in §7 are 2026-11-03 figures.
3. **Step 0b (G3 non-regression) is the gate that replaced "D1 open means NO-GO".** Stage 3 proceeds for a release iff Step 0b prints `G3-NON-REGRESSION` for it. Measured 2026-11-03: falco, the three Intel releases and paperless-ngx are unresolved before AND after; node-feature-discovery resolves before and after. D1 remains an open *policy* question (should G3 refuse on an unresolved lookup?) but is not a prerequisite of Stage 3. **D2 does not apply**: all four registries are upstream-native (`ghcr.io/intel`, `ghcr.io/gabe565`, `ghcr.io/falcosecurity`, `registry.k8s.io/nfd`). **D3 (§1.0) is for stages 5-6**; Stage 3's acceptance is the GO text above.
4. **`helm-drift-detection` runs `sat-attended:2026-11-28` (P1: adds `spec.driftDetection` to every HelmRelease).** After rebasing onto it, re-run Step 1 (`collect.sh`) and take the baseline AFTER that commit; a baseline from before it makes Assertion 2's `gen` comparison meaningless. If its P2/P3 have run, also confirm `kubectl get helmrelease falco -n security -o jsonpath='{.spec.driftDetection}'` before the falco commit and say so in the commit.
5. **No `kube-prometheus-stack` bump may be windowed on 12-13** (the falco/NFD gates read Prometheus-adjacent state through Wazuh and node objects, but the monitoring namespace must be quiet). `maintenance-plan.py --open` today shows none.
6. Install the tools once per window: run the §8 heredocs into `$T`.

**Dry-run record (2026-11-03, read-only).** Tarballs: `falco`, `paperless-ngx` and `intel-device-plugin-{gpu,npu}` byte-identical to the deployed HTTP artifacts; `intel-device-plugin-operator` and `node-feature-discovery` are repackages (different tar bytes) whose renders are nevertheless identical apart from the predicted build-metadata effects. All six `helm pull` digests equal the registries' `docker-content-digest`.

### 1.0 Re-plan record, 2026-11-03 (it overrides anything BELOW §1.00 that disagrees; §1.00 overrides this)

**Why this section exists.** The premise check failed on two of its (then) five
premises and a plan whose premises do not hold must not execute. Both failures
were benign and neither means a stage of this plan ran:

| premise | was | live 2026-11-03 | cause |
|---|---|---|---|
| HTTP HelmRepository count | 29 | **28** | `external-secrets`, the one orphan the operator had HELD, was deleted by `67216b3b` (sweep finding F-fb2cc8a2: no HelmRelease or chartRef consumed it, no ExternalSecret CRDs). **Stage 1 is therefore 6 of 6 done.** The "HELD, do not delete" text below is historical: there is nothing left to hold or delete. |
| OCIRepository count | 1 | **4** | three ARC runner charts (`arc-build`, `arc-system`, `ci-runner`; commit `a03a8616`, now in the gha-fleet plan) were added in exactly the shape §3.2 prescribes — `ref.tag` AND `ref.digest`, app-local file. They are not this plan's work; the premise now pins the exact set of four names instead of a bare count. |

**What else moved since 2026-09-28 (all measured live 2026-11-03, none of it assumed):**

- Cluster and CLI are Flux **v2.9.6** (source-controller `v1.9.6`, helm-controller `v1.6.5`); the text below said 2.9.0 / 2.9.3. flux-operator and flux-instance charts are `0.61.0`; `flux-fleet-0.62.0` / `0.62.1` are drafts that touch the same two HelmReleases and `fluxinstance/flux` (both now in `conflicts_with`).
- **Every pinned chart version moved**: the §7 appendix now carries the live pins and re-verified presence. Reading a stale version from the old table would have failed Step 3's pull — and the recipe never hard-codes one (`VER` is read from the live HelmRelease).
- Census: `HelmChart` objects **109** (was 122), source-controller `/data` **38.4 MB**, **18** CIFS StorageClasses / **21** Bound CIFS PVCs (was 19 / 21), **79** Longhorn volumes, 75 attached and healthy (was 94). 16 apps were decommissioned on 2026-10-04 (`ac7bf0e0`).
- **Roll scope re-measured with the build-metadata method (the label-only method of §1.4 was blind to checksum annotations).** For every in-scope release with an OCI chart, `helm template` of the deployed chart vs the OCI chart with its version rewritten to `<VER>+<digest12>` (exactly what helm-controller does under `chartRef`), diffing each workload's `template:` block (`rollpred.py`, §8). Results, live pins of 2026-11-03: **restarts**: falco (DaemonSet), node-feature-discovery (worker DaemonSet + master Deployment) [stage 3]; authentik (server + worker, label AND `checksum/secret`), grafana, open-webui (StatefulSet + redis Deployment), anythingllm [stage 5]; cilium (DaemonSet + operator), cert-manager (3 Deployments), longhorn (manager DaemonSet + ui + driver-deployer) [stage 6]. **No restart**: intel-device-plugin-{operator,gpu,npu}, paperless-ngx [stage 3]; external-dns, headlamp, metrics-server, descheduler (CronJob template annotation only: the next scheduled run uses it, no pod is replaced) [stage 4]; nextcloud and otel-operator [stage 5; both changed since 2026-09-11, when the old census listed them as rolling]. 9 rolling releases / 17 workloads in stages 3-6. **Not re-measured:** stage 7 (ten charts) and `unpoller` have no OCI chart to render against; their rows keep the 2026-09-11 label-only figures and are explicitly unverified for checksum annotations.
- Stage 10 inputs unchanged: `FluxInstance.spec.kustomize.patches` still holds exactly one GitRepository `ignore` patch (append, do not replace) and both emptyDirs still have no `sizeLimit` (now a premise).

**Defects found in the old text while re-measuring** (each fixed where it occurs below):

1. §2(3) `ls /data/helmchart | wc -l` printed `1` — the cache is `helmchart/flux-system/<ns>-<release>/`, so it counted the namespace directory, not artifacts. A gate that reads 1 whether the cache holds 1 or 200 artifacts cannot fail. Now `find … -type f`.
2. §3.2 Step 4 ran `mise exec -- helm …`, which fails in agent shells ("couldn't exec process"), and a failed render left **both** render files empty, so `diff` reported *identical* — a gate that passes when both sides are empty. Now plain `helm` (mise-pinned 3.22.1, asserted) plus a non-empty-render assertion. Demonstrated 2026-11-03 on falco: deployed tarball sha256 `b8a1aa98…` is **byte-identical** to the OCI layer; both renders 736 lines; `diff` empty; the OCI manifest digest (`helm pull` "Digest:") equals the registry's `docker-content-digest` `08cd4fd5…`.
3. §4.1 `coverage.py --json | … d.get('items') …` prints `[]` whether Stage 0 worked or not (the JSON has no `items` key; it has `lanes`/`needs_plan`). Replaced by a check of the generated version snapshot, which does change.
4. §3.3 item 3 / §4.1: the `grep -c 'release notes unavailable…'` gate counts a *string*, so rewording the message would "pass" without closing anything. See D1 for what actually matters and a gate that can fail.
5. **Review 2026-11-03 (plan-reviewer, `needs-fix`).** The "no workload roll" claim for falco and node-feature-discovery was false (see §1.00); the Step 4 predictor looked only at pod-template *labels*. Replaced by the build-metadata re-render + `template:` diff, demonstrated on falco (prints the checksum change) and on paperless-ngx (prints `none`).
6. `collect.sh` could not baseline `intel-device-plugin-gpu` / `-npu`: their DaemonSets are created by the operator's `GpuDevicePlugin` / `NpuDevicePlugin` CRs and carry no `helm.toolkit.fluxcd.io/name` label, so it printed `ABORT: 0 workloads` yet exited 0 (the `sys.exit(1)` sat inside a pipeline whose last command was `tee`) and Assertion 2 then compared two empty files. Now: explicit `WL` list, nonzero exit on an empty baseline, and a caller that checks it. The `-gt 50` render-length floor false-aborted on real renders of 23 (gpu) and 17 (npu) lines; it is now "at least one `^kind:` document, same count old and new".
7. Step 5's deletion gate `grep -rn "name: $REPO" … must be empty` can never pass for `intel` (substring of `intel-device-plugin-*`) or `node-feature-discovery` (the HelmRelease's own `metadata.name` and a `dependsOn`). Now an exact-match count with a positive control (`intel` must read 3 before the first Intel commit).
8. Assertion 1 compared `status.artifact.revision` with `<VER>@<digest>`; with `ref.digest` pinned the live OCIRepositories (k8s-gateway, the ARC pair) report `revision = sha256:<manifest digest>` with no tag prefix, so the literal compare false-fails every component. Now compared with `$S/digest.txt`.
9. `$APPDIR` was a placeholder, `intel-device-plugin/vpu` has no `kustomization.yaml`, and `git commit --only` on a new untracked file needs `git add -N` first. All six real file lists are in §1.00.


**Decisions the operator must record in this file before the dependent stage runs** (none is a window action; if they are not recorded the window agent reports NO-GO, it does not improvise):

- **D1 — G3 (breaking-change scan) for chart bumps. A policy question; does NOT block Stage 3.** Measured today with the resolver `auto-update.py` actually uses (`_owner_repo` + `fetch_release_notes`, target version of each live release): release notes resolve for `cilium`, `cert-manager` and `node-feature-discovery` and **do not resolve** for `falco`, `intel-device-plugins-*`, `paperless-ngx`, `authentik`, `grafana`, `nextcloud`, `open-webui`, `opentelemetry-kube-stack` or `anythingllm` — *before* any migration; G3 falls open on an unresolved lookup (documented asymmetry in `docs/sops/auto-update.md`). So the migration does not by itself remove G3 coverage, and the per-release **Step 0b non-regression gate** (can fail: known-bad `cilium` + the k8s-gateway path prints `G3-REGRESSION`) is what Stage 3 needs. The open question is whether G3 should *refuse* on an unresolved lookup (changes what is auto-mergeable; its own plan and tests). It need not gate stages 5-7 either, provided Step 0b passes for each release; if the operator prefers to close the fail-open first, that is option (b).
- **D2 — charts-mirror trust. Blocks stage 4 and the longhorn half of stage 6; irrelevant to Stage 3** (all four Stage 3 registries are upstream-native). `docs/sops/flux-chart-source-pinning.md` §4.1 rung 4: a third-party mirror (`ghcr.io/home-operations/charts-mirror`) changes the trust root and is "never a cleanup step of a plan". All five charts (`descheduler`, `external-dns`, `headlamp`, `metrics-server`, `longhorn`) are present in it at the live pins (§7), but none moves until the operator writes "charts-mirror accepted for <chart>" here.
- **D3 — accept the roll. For STAGES 5 AND 6 ONLY** (authentik, grafana, open-webui, anythingllm; cilium, cert-manager, longhorn: §1.0 census). Stage 3's own restarts (falco, node-feature-discovery) are accepted by the one-line GO text in §1.00, not by D3. The alternative for stages 5/6 (`type: oci` HelmRepository: no roll, no `verify`, stays in the `cluster-meta` gate) loses stage 9. Decide per stage.

**What the 2026-12-13 window runs.** Stage 3 only, exactly as §1.00: six releases, one commit each, two of them (falco, node-feature-discovery) restart once; each proceeds when its Step 0b prints `G3-NON-REGRESSION` and the operator GO text is recorded. Everything else in §3.1 is a later slice with its own window and, where a decision is listed, its own recorded decision. It does not run unattended and does not share the slot with anything on the `conflicts_with` list.

### 1.1 What happened, and what it proved about the shape of our source layer

On 2026-09-11 `HelmRepository/k8s-gateway` pointed at a GitHub Pages chart index
that upstream **deleted** instead of redirecting. The index 404'd, the
HelmRepository could not go Ready, and because `cluster-meta` carries
`spec.wait: true` over `./kubernetes/flux/meta` — **verified live** —
`cluster-apps` (which `dependsOn: cluster-meta`) was blocked. For ~90 minutes
**no commit could deploy**. Nothing was down; *delivery* was.

That is the finding worth generalising: one third-party URL, owned by one person,
with no consumer outside a single app, is wired into a gate that every app in the
cluster passes through. We have **30 more of them**.

The near-miss was worse than the outage. `source-controller` stores artifacts on
an **`emptyDir`** (verified: volumes `data` and `tmp`, both `emptyDir: {}`, **no
`sizeLimit`**), and the chart tarball existed only there. One eviction or node
drain and internal DNS would have been unrecoverable — with a 3-node Talos roll
booked for `sun-attended:2026-09-27`, i.e. precisely that event.

Driver findings: **`F-0e310ef2`** (this plan's subject) and **`F-764e4fc3`** (the
emptyDir / disaster-recovery half — answered by Stage 10 and by §4.3's cold-cache
test). A third, `F-37ace39e`, asked for a digest pin on the one already-migrated
OCIRepository; it was **answered outside this plan by `0c77bbb0`** while this plan
was being written, so it is deliberately not claimed here — but the rule it
established is §1.5(a) and every stage below obeys it. Vulnerability and exposure
detail stays on those records.

### 1.2 The measured inventory (re-verify before executing; 2026-09-11 figures — the 2026-11-03 re-measure is in §1.0 and the table at the end of this subsection)

| | count | note |
|---|---|---|
| `HelmRepository` total, in repo | 40 | was 48 this morning; `k8s-gateway` migrated (`43a3b3e4`), `pajikos` deleted (`4dfc3e32`), five Stage-1 orphans deleted (`7c048735`) |
| of which `type: oci` | 10 | legacy OCI shape, healthy — out of scope except as the comparison in §1.4 |
| of which HTTP | **30** | this plan's scope |
| HTTP, referenced by a HelmRelease | **29** | stages 2-8 — `csi-driver-smb` left this population at `001ab0ad` |
| HTTP, referenced by **nothing** | **1** | stage 1 — five deleted (`7c048735`); `external-secrets` HELD, not a worklist item |
| `OCIRepository` | 1 | `network/k8s-gateway`, tag **and** digest pinned |
| cached `HelmChart` artifacts in the emptyDir | **122** | the blast radius of one source-controller restart |

**Re-measured live 2026-11-03** (supersedes the column above): `HelmRepository` 37 = **28 HTTP** (all referenced by a HelmRelease: 0 orphans) + 9 `type: oci`; `OCIRepository` 4 (k8s-gateway + 3 ARC runner charts); `GitRepository` 4 (`flux-system`, `csi-driver-smb`, `oc8`, `plex`); 109 `HelmChart` objects; `/data` 38.4 MB. The 28 HTTP repositories by stage: 3 → `intel`, `node-feature-discovery`, `gabe565`, `falcosecurity`; 4 → `descheduler`, `external-dns`, `headlamp`, `metrics-server`; 5 → `authentik`, `grafana`, `nextcloud`, `open-webui`, `opentelemetry`, `mintplex-labs`; 6 → `cilium`, `jetstack`, `longhorn`; 7 → `apache-superset`, `blakeblackshear`, `dirsigler`, `elastic`, `influxdata`, `jameswynn`, `jellyfin`, `penpot`, `rm3l`, `sure`; 8 → `unpoller`.

Five of the six — `backube`, `democratic-csi`, `guerzon`, `piraeus`,
`rook-ceph` — were deleted in `7c048735` (2026-09-11). **One remains and is NOT
a worklist item: `external-secrets`, deliberately retained by the operator**
because it is the one that was never wired up at all, and no evidence it was
intended is not evidence it was not. Verified by grepping every `name:` in
`kubernetes/` outside `kubernetes/flux/meta/repositories/` — zero hits each.
When re-running that grep, scope it to `kubernetes/` or exclude
`.claude/worktrees/`: a stale worktree still holds the five deleted files, so a
repo-root grep reports them as present. Four match the
"dormant 8-19 months" profile by last git touch: `external-secrets`
(2025-02-19), `backube` / `piraeus` / `rook-ceph` (2025-02-25); `democratic-csi`
and `guerzon` were last touched 2026-02-22 in a bulk edit and are equally
unreferenced. The fifth dormant one was `pajikos` — already deleted today, for
exactly this reason: Home Assistant does **not** run on that chart any more
(`home-automation/home-assistant` is a `bjw-s` app-template release), so its
plaintext-`http://` problem was never a Home Assistant risk, just an unreferenced
object sitting in the delivery gate.

**All 36 HTTP indexes answered 200 when probed on 2026-09-11** (three benign
redirects: `external-secrets` 302, `unpoller` 301, the since-deleted `pajikos`
301). So no second source is 404 *today* — which is the point: the one that died
was 200 yesterday too.

### 1.3 The capability gain is real, and it is OCIRepository-only

Verified against the live CRDs, not the docs:
`helmrepositories.source.toolkit.fluxcd.io` serves **only `v1`**, and `v1`'s
`spec` has **no `verify` field at all** (`accessFrom certSecretRef insecure
interval passCredentials provider secretRef suspend timeout type url`).
`ocirepositories…/v1` has `verify.{provider,secretRef,matchOIDCIdentity,trustedRootSecretRef}`
with `provider ∈ {cosign, notation}`, and `ref.{tag,digest,semver,semverFilter}`.

So chart provenance verification is not "off" for our HTTP repos — it is
**unexpressible**, and it stays unexpressible under `type: oci` too. Only
`OCIRepository` can ever carry it. Stage 9 is where it is actually turned on, per
registry, never blanket (§3.7).

### 1.4 THE GOTCHA THAT SHAPES THIS PLAN: chartRef is **not** a workload no-op

> **2026-11-03 correction:** the census below used a label-only method and under-counts. `chartRef` also changes every `checksum/*` pod-template annotation computed from a ConfigMap or Secret that embeds the chart label (falco, node-feature-discovery, authentik). The re-measured scope and the correct method are in §1.0; the Step 4 predictor in §3.2 implements it.

Measured on the one component already migrated, and it contradicts the
assumption the migration was designed around.

When a HelmRelease sources its chart via `chartRef: OCIRepository`,
helm-controller reports the chart version with the artifact digest as **semver
build metadata**. Live, on `network/k8s-gateway`:

```
status.lastAttemptedRevision: 3.7.2+3783b0b4bc41      # was: 3.7.2
status.history:  v8 chart 3.7.2+3783b0b4bc41 deployed / v7 chart 3.7.2 superseded
```

Charts stamp `helm.sh/chart: <name>-<version>` into the **pod template** — it is
part of Helm's standard recommended label set. Build metadata is not a legal
label value, so Helm sanitises `+` to `_`, and the pod-template label changed:

```
helm.sh/chart=k8s-gateway-3.7.2   ->   helm.sh/chart=k8s-gateway-3.7.2_3783b0b4bc41
```

A changed pod template is a changed pod-template hash, so a new ReplicaSet was
created and **all three internal-DNS pods were replaced** ~50 seconds after the
commit (`rs/k8s-gateway-64ccd5c579`, pods created 21:01:48-21:02:12Z). The chart
bytes were byte-identical. The workload rolled anyway.

By contrast a `type: oci` HelmRepository does **not** do this — `kube-system/reloader`,
sourced that way, reports a clean `2.2.16` with no build metadata. The roll is
specific to `chartRef`.

**Measured scope** (`kubectl get deploy,sts,ds -A`, checking pod-template labels
*and* annotations for a chart-version-derived key): **22 releases / 38 workloads**
carry such a key. Inside this plan's scope that includes:

- `kube-system/csi-driver-smb` — `DaemonSet/csi-smb-node` (3 nodes) + controller → **the CSI driver behind all 19 CIFS StorageClasses and 21 Bound PVCs**
- `kube-system/cilium` — `DaemonSet/cilium` + `cilium-operator` → **CNI roll**
- `storage/longhorn` — `DaemonSet/longhorn-manager` + ui + driver-deployer → **storage control plane, 94 volumes**
- `cert-manager/cert-manager` — controller + **webhook** + cainjector → admission gap for `Certificate` writes
- `kube-system/authentik` — server + worker + `StatefulSet/authentik-postgresql` → **SSO**
- `office/nextcloud` (`StatefulSet/nextcloud-mariadb`), `ai/open-webui` (+ redis), `ai/anythingllm`, `monitoring/{grafana,unpoller,eck-operator,otel-operator,prometheus-*}`, `media/{plex,jellyfin}`

And — usefully — the components whose pod templates carry **no** such key, which
therefore migrate with **no restart at all** (2026-11-03: `falco` and `node-feature-discovery` were removed from this list — they restart via `checksum/*` annotations, §1.00): `external-dns`, `metrics-server`,
`descheduler`, `intel-device-plugin-*`, `headlamp`,
`frigate`, `superset`, `influxdb`, `penpot`, `paperless-ngx`, `sure`,
`uptime-kuma`, `adguard-home`, `homepage`. That split is what the stage order in
§3.1 is built on.

**Consequences baked into this plan:**

1. The "source change must be a no-op" gate cannot be "nothing restarted". It is:
   **exactly one new Helm revision, rendered manifest identical except for the
   `helm.sh/chart` version string, and nothing else different** — same images,
   same replica counts, `generation` +1 at most, replacement pods Ready with 0
   restarts. Any other diff aborts the component (§3.2 step 4).
2. Order by blast radius of a **restart**, not by the size of the edit.
3. **The roll is the price of admission and this plan pays it**, because
   `spec.verify` and digest pinning are OCIRepository-only. That is an operator
   decision recorded here, not a silent one: if the answer is "do not restart the
   CNI and the CSI driver for a source refactor", then stages 2/5/6 should be
   re-scoped to `type: oci` (no roll, no verify, stays in the `cluster-meta`
   gate) and Stage 9 dropped. **Decide before Stage 2.**

### 1.5 Four more traps, each already paid for once

**(a) A tag-only OCIRepository FOLLOWS a re-pushed tag.** This inverts the
property we rely on today: `reconcileStrategy: ChartVersion` on an HTTP source
means an unchanged version string never re-pulls — which is exactly why today's
host repoint did *not* change the deployed bytes. An OCIRepository re-resolves
tag → digest every `interval`, GHCR does not enforce tag immutability, and the
HelmRelease upgrades on any new artifact revision with no git diff and no
Renovate PR. `F-37ace39e` recorded it; `0c77bbb0` fixed it for `k8s-gateway` and
wrote the rule into the manifest. **Every OCIRepository this plan creates carries
`ref.tag` AND `ref.digest`, re-derived from the registry.** A deny rule does not
substitute: it gates git-visible version changes, not silent tag re-resolution.

**(b) A relocated or re-published tarball is usually not the same artifact.**
Today's kapsi.fi copy of 3.7.2 was a repackage: 9195 → 9616 bytes, different
digest, differing in `Chart.yaml` maintainers plus a stray dev file. It was only
*provably* safe because both tarballs were extracted and `helm template`'d
against the live release values and diffed. That diff is **mandatory per
component** (§3.2 step 4) — not optional, and not replaceable by "same version
number". Note also that `reconcileStrategy: ChartVersion` means an unchanged
version string does **not** re-pull, so a source move can leave the old tarball
deployed and look like a success.

**(c) Our own version tooling WAS blind to `chartRef` — FIXED 2026-09-11 in
`97c3e913`.** Kept here because the hazard it describes is the reason Stage 0
exists, and because one half of it is still open. What was measured:

```
# runbooks/check-all-versions.py parse_helmrelease() on the migrated file:
chart_name='' chart_version='' repo=''   chartRef={'kind': 'OCIRepository', 'name': 'k8s-gateway'}
```

It read `spec.chart.spec` only. A migrated release dropped out of the version
snapshot with **no degradation record** — it did not look broken, it looked
chart-less. `coverage.py` read that snapshot, so it would have stopped proposing
chart bumps for every migrated component: not "held", *absent*.

Both parsers now resolve `chartRef`, and an unreadable chart source is counted
and announced instead of returning empty strings (`unresolved_chart_sources` →
stderr + report table + a `warning` finding + a per-component auto-close veto).
Measured after the fix: 123 of 124 chart sources resolve, k8s-gateway among
them. **Still open:** `csi-driver-smb` resolves to nothing at all — a
GitRepository-path chart has no version in git, and Renovate's flux manager
cannot track that shape either (F-2e76c058), so the driver behind all 19 CIFS
StorageClasses currently has no automated version signal. The bucket makes that
loud; it does not close it.

And G3 (the
breaking-change scan in `auto-update.py`) resolves release notes by mapping the
dep name to a GitHub repo, which OCI chart paths break:

```
ghcr.io/k8s-gateway/charts/k8s-gateway        -> ('k8s-gateway', 'charts')          # does not exist
ghcr.io/home-operations/charts-mirror/frigate -> ('home-operations','charts-mirror') # wrong notes
quay.io/jetstack/charts/cert-manager          -> None
```

An unresolved G3 **fails open** ("relied on CI + policy"). So a naive migration
would quietly remove breaking-change scanning from chart updates while leaving
them auto-mergeable. **Stage 0 fixes the tooling first** — the
`docs/sops/audit-script-correctness.md` standard: a check that cannot measure
must not report a pass.

Status after `97c3e913`: the derivation half is fixed — a generic
`charts` / `charts-mirror` / `helm-charts` / `helm` path segment is no longer
used as a GitHub repo name (it produced the provably nonexistent
`k8s-gateway/charts`), and k8s-gateway's real repo — `k8s_gateway`, with an
underscore, verified against the GitHub API — is pinned in the mapping table.
**The FAIL-OPEN itself is NOT fixed:** `auto-update.py`'s G3 still treats an
unresolved release-note lookup as "no breaking changes", and a derived
owner/repo remains a heuristic that can 404 silently (a mirror namespace does
not own the upstream project). Closing it means making G3 refuse to pass on an
unresolvable lookup, which changes what is auto-mergeable — a policy-bearing
change that needs its own operator decision, not a side effect of a parser fix.

**(d) Signature probing by `.sig` tag alone gives false negatives.** Three cosign
layouts are in play: the legacy `sha256-<digest>.sig` tag (cert-manager, NFD,
unpoller, charts-mirror/external-dns); a bare `sha256-<digest>` tag whose child
layer is `application/vnd.dev.sigstore.bundle.v0.3+json` (falco, and 5 of the 6
charts-mirror charts); and OCI-1.1 **referrers** (cilium, and k8s-gateway — whose
signatures were twice reported absent today for exactly this reason). A first
pass that checked only `.sig` called 5 signed charts unsigned. §3.7 checks all
three.

**(e) Do not weaken a deny rule.** `runbooks/auto-update-policy.yaml` gained
`*k8s-gateway*` today (`6ec81e05`, reason text corrected in `0c77bbb0`). Globs
still match after migration because the chart name appears in the OCI path —
verify that per component (§3.2 step 6) rather than assuming it.

## 2. Pre-checks (run at the start of EVERY stage, not once for the plan)

```bash
cd /Users/mu/code/cberg-home-nextgen

# (1) Delivery is healthy BEFORE you touch the gate that controls it.
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
flux get sources all -A    | awk 'NR==1 || $5 != "True"'
kubectl -n flux-system get kustomization cluster-meta \
  -o jsonpath='{.spec.wait} {.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # expect: true True

# (2) Nothing else is mid-flight — this worktree is shared.
git status --porcelain; git log --oneline -3

# (3) The cache we are one restart away from losing is still intact.
kubectl -n flux-system get pod -l app=source-controller \
  -o custom-columns='NAME:.metadata.name,RESTARTS:.status.containerStatuses[*].restartCount,START:.status.startTime'
kubectl -n flux-system exec deploy/source-controller -- /bin/sh -c 'du -sh /data; find /data/helmchart -type f | wc -l'   # expect ~38 MB and ~218 files (109 HelmCharts x tarball + index); 0 or 1 files = cold cache, ABORT

# (4) Longhorn + CIFS baseline (required for stages 2 and 6; harmless elsewhere).
kubectl get volumes -n storage -o json | python3 -c "import sys,json;v=json.load(sys.stdin)['items'];print('volumes',len(v),'attached',sum(1 for x in v if x['status'].get('state')=='attached'),'healthy',sum(1 for x in v if x['status'].get('robustness')=='healthy'))"
kubectl get pvc -A -o json | python3 -c "import sys,json;p=json.load(sys.stdin)['items'];print('cifs PVCs bound:',sum(1 for x in p if (x['spec'].get('storageClassName') or '').startswith('cifs-') and x['status']['phase']=='Bound'))"

# (5) Silence + marker for the component being migrated (SOP application-update
#     §Step 1). The roll in §1.4 WILL fire pod/not-ready alerts; silence them
#     deliberately rather than explaining them afterwards.
runbooks/update-marker.sh add <component> <ns> 2 "chart source -> OCIRepository"

# (5b) Tooling is the pinned one, and Flux is the version this plan was measured on.
helm version --short            # expect v3.22.1 (mise pin). Use plain `helm`, NOT `mise exec -- helm`
                                #   (fails in agent shells and then yields EMPTY renders, see §1.0 defect 2)
flux version | head -1          # expect: flux: v2.9.6  (flux-fleet / Talos plans may legitimately move it: re-run the premises)

# (6) ABORT the stage if any of these hold:
#   - any Kustomization or HelmRelease not Ready
#   - source-controller restarted within the last hour (cold cache: a migration
#     on a cold cache cannot be distinguished from one that broke the cache)
#   - a Talos roll, Longhorn upgrade or Cilium change is in the same window
#   - the component's deny rule in auto-update-policy.yaml would stop matching
```

## 3. Steps

### 3.1 Stage table — sequence, size, risk, and what each stage buys

Run in order. Every stage is one or more independent commits and the plan is
**safely abandonable after any stage**: stopping leaves a mixture of HTTP and OCI
sources, which is the state the cluster is in today. The full per-component
source inventory this table is derived from is in §7.

| # | Stage | components | min | risk | rolls? | buys |
|---|---|---|---|---|---|---|
| 0 | **Teach the version/update pipeline about `chartRef`** — **3 of 4 items DONE `97c3e913`, and the snapshot has carried `k8s-gateway` with chart `3.7.2` through 7+ sweeps since (re-verified 2026-11-03: `version-check-current.md` row populated, 3 git-sourced charts in the "unresolved" table, k8s-gateway not among them). Item 3's G3 fail-open is a pre-existing property, now framed as operator decision D1 (§1.0).** | tooling only | ~10 left | low | no | stops the migration from blinding `coverage.py` and the version snapshot |
| 1 | ~~Delete the 6 unreferenced HelmRepositories~~ **6 of 6 DONE** — five on 2026-09-11 (`7c048735`), and `external-secrets` (the one the operator had held) on 2026-10-23 (`67216b3b`, F-fb2cc8a2). There are no unreferenced HTTP sources left. | — | 0 | — | no | executed: six third-party URLs out of the `cluster-meta` gate. **Do not execute this row.** |
| 2 | ~~`csi-driver-smb` → charts-mirror OCI~~ **DONE 2026-09-11 via a DIFFERENT route — see §3.4** | csi-driver-smb | 0 | — | **no roll occurred** | executed as a GitRepository pinned to commit `59dce96e` (the v1.20.3 cut), NOT charts-mirror. **Do not execute this row.** |
| 3 | **Upstream-native OCI — THE 2026-12-13 SLICE (§1.00): four releases restart nothing, falco and node-feature-discovery restart once each.** | intel (3 releases), node-feature-discovery, gabe565/paperless-ngx, falcosecurity/falco | 10-20 ea (100 total) | low | **falco + NFD only** (build-metadata method, 2026-11-03) | 6 releases off HTTP; the first three Intel commits are a zero-impact rehearsal |
| 4 | **No-roll, charts-mirror — BLOCKED on operator decision D2** (docs/sops/flux-chart-source-pinning.md §4.1 rung 4: a third-party mirror is never a cleanup step of a plan) | descheduler, external-dns, headlamp, metrics-server | 15 ea | low-med | **no** | only after the operator records the charts-mirror trust decision in this plan |
| 5 | **Rolling, upstream-native OCI, app tier — needs D3 + Step 0b per release (measured 2026-11-03: authentik, grafana, open-webui, anythingllm restart; nextcloud and otel-operator do NOT)** | authentik, grafana, nextcloud, open-webui, opentelemetry, mintplex-labs | 25 ea | medium | yes | the apps where a restart is tolerable but not free |
| 6 | **Rolling, cluster-critical — ONE PER WINDOW — needs D3 + Step 0b per release** | cilium, jetstack/cert-manager, longhorn (charts-mirror — BLOCKED on D2; and `longhorn-1.13.0` is windowed `sun-attended:2026-11-15`, so re-read the live longhorn pin before planning this) | 30 ea | **high** | yes | the sources whose failure blocks recovery |
| 7 | **The 10 remaining charts with no OCI anywhere — mirror track (PARKED; its own plan revision adds its namespaces)** | ~~plex~~ (DONE 102ec800, Shape D GitRepository), then apache-superset, blakeblackshear, dirsigler, elastic, influxdata, jameswynn, jellyfin, penpot, rm3l, sure (three of them — `rm3l`, `jameswynn`, `blakeblackshear` — also carry open LOW sweep postures about being hosted under a personal GitHub account: F-ac4ec44e, F-04817ce7, F-1e7d8813; not claimed by this plan) | decision + 20 ea | medium | some | the long tail; needs §3.6 decided first |
| 8 | **`unpoller` — blocked, coupled to a chart upgrade** | unpoller | — | — | — | own plan; see §3.5 (re-verified 2026-11-03: live pin still 2.4.0, OCI `2.4.0` still 404, `2.5.0` present) |
| 9 | **`spec.verify` — pilot, then per registry** | signed registries only | 30 pilot | medium | no | the capability gain from §1.3 |
| 10 | **`source-controller` emptyDir `sizeLimit`** | flux-system | 15 | low | yes (source-controller) | caps an unbounded emptyDir; answers the other half of `F-764e4fc3`. Re-read `fluxinstance/flux` first: `flux-fleet-0.62.x` and `flux-reconciler-impersonation` also edit it |

**Stage 1 coordination note:** other sessions were editing `k8s-gateway` and
`pajikos` manifests on 2026-09-11 (`43a3b3e4`, `0c77bbb0`, `5a7baeb5`,
`4dfc3e32`). Re-read `kubernetes/flux/meta/repositories/helm/` before Stage 1 and
adjust the list — do not revert someone else's work.

### 3.2 The per-component recipe (stages 2-7) — follow it verbatim, per component

One component per commit. Never batch two components into one commit: the
rollback must be able to name exactly one thing.

```bash
cd /Users/mu/code/cberg-home-nextgen
export NS=<namespace> REL=<helmrelease> CHART=<chart-name>
export VER=$(kubectl get helmrelease $REL -n $NS -o jsonpath='{.spec.chart.spec.version}')   # READ the live pin; never type it. Another plan may have moved it since this was written
test -n "$VER" || { echo "ABORT: $NS/$REL has no spec.chart.spec.version (already on chartRef?)"; exit 1; }
export S=/Users/mu/.claude/jobs/flux-oci/$NS-$REL   # scratch; NOT /tmp. FIXED path: every agent Bash call is a
mkdir -p "$S"                                       # new shell ($$ changes, vars vanish) -- re-run these 3 lines at the top of EVERY step
export T=/Users/mu/.claude/jobs/flux-oci/tools       # §8 scripts, installed once per window
export WL=                                            # set ONLY for operator-created workloads: gpu WL="ds/intel-gpu-plugin-intel-gpu-plugin", npu WL="ds/intel-npu-plugin-intel-npu-plugin"
REPO=<helmrepository-name>; OCI_PATH=<from §7>; OCINAME=<ocirepository name = chart name>
export APPDIR=<literal directory from §1.00 (one block of literal env lines per Stage 3 release); later stages read it from the release's ks.yaml>
```

**Step 0b — G3 non-regression (before any edit).** Moving a chart to an OCI path
changes the dependency string the update pipeline sees. The component must keep
at least the release-note coverage it has today (decision D1, §1.0). Write the
probe once per stage and run it per component:

```bash
cat > "$S/g3nr.py" <<'PY'
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("au", "runbooks/auto-update.py")
au = importlib.util.module_from_spec(spec); sys.modules["au"] = au; spec.loader.exec_module(au)
ck = au._load_version_checker()
def probe(dep, tag):
    orr = au._owner_repo(ck, dep)
    if not orr:
        return "no-owner-repo", None
    for t in (tag, "v" + tag.lstrip("v"), tag.lstrip("v")):
        try:
            n = ck.fetch_release_notes(orr[0], orr[1], t)
        except Exception:
            n = None
        if n and n.get("body"):
            return "resolved", orr
    return "unresolved", orr
a = probe(os.environ["HTTP_DEP"], os.environ["VER"])
b = probe(os.environ["OCI_DEP"], os.environ["VER"])
print("HTTP-era:", a, "| OCI:", b)
if a[0] == "resolved" and b[0] != "resolved":
    print("G3-REGRESSION: release notes resolved before the move and not after"); sys.exit(1)
print("G3-NON-REGRESSION")
PY
HTTP_DEP=$CHART OCI_DEP=$OCI_PATH python3 "$S/g3nr.py" 2>&1 | grep -c '^G3-NON-REGRESSION$'     # THE GATE: must print 1 (a bare pipe into grep would mask the script's exit 1; a regression prints 0)
```

(`OCI_PATH` is the `<registry>/<path>` form from §7 with no `oci://`.) PASS is the
count `1` printed above (the line `G3-NON-REGRESSION` exists exactly once). Measured 2026-11-03 — pass: `falco` (unresolved before and
after), `node-feature-discovery` (resolved before and after); **known-bad that must
print `G3-REGRESSION` and exit 1**: `HTTP_DEP=cilium OCI_DEP=ghcr.io/k8s-gateway/charts/k8s-gateway VER=1.20.4`.
Run it with the script as a **file** (above); the same code fed through
`python3 - <<EOF` printed nothing at all, and a silent probe reads as a pass.
A `G3-REGRESSION` is fixed by adding the real repo to the notes map
(`IMAGE_RELEASE_NOTES_PROJECTS` / `CHART_RELEASE_SOURCES` in
`runbooks/check-all-versions.py`) in the SAME commit as the migration, then re-run.

**Step 1 — baseline the workload (before any edit).** Save it; §4.2 diffs against it.

```bash
cat > "$S/collect.sh" <<'EOS'
set -euo pipefail
W=$(mktemp)
# env: NS REL  and optionally WL="ds/<name> ..." for releases whose workloads are created by an operator CR
kubectl -n "$NS" get helmrelease "$REL" -o json | python3 -c "import sys,json;d=json.load(sys.stdin);print('HR revision',d['status'].get('lastAttemptedRevision'));print('history',[(h['version'],h['chartVersion'],h['status']) for h in d['status'].get('history',[])])"
if [ -n "${WL:-}" ]; then
  kubectl -n "$NS" get $WL -o json > "$W"
else
  kubectl -n "$NS" get deploy,sts,ds -l "helm.toolkit.fluxcd.io/name=$REL" -o json > "$W"
fi
python3 - "$W" <<'PY'
import sys, json, os, subprocess
d = json.load(open(sys.argv[1]))
items = d['items'] if d.get('kind') == 'List' else [d]
if not items:
    print('ABORT: 0 workloads for', os.environ['NS'], os.environ['REL'], os.environ.get('WL', '(label helm.toolkit.fluxcd.io/name)')); sys.exit(1)
for i in items:
    m = i['metadata']; t = i['spec']['template']
    print('SPEC', i['kind'], m['name'], 'replicas', i['spec'].get('replicas'),
          'containers', sorted((c['name'], c['image']) for c in t['spec']['containers']))
    print('VOL', i['kind'], m['name'], 'gen', m['generation'],
          'chartlabel', (t['metadata'].get('labels') or {}).get('helm.sh/chart'),
          'checksums', sorted((k, v[:8]) for k, v in (t['metadata'].get('annotations') or {}).items() if k.startswith('checksum/')))
    sel = ','.join(f'{k}={v}' for k, v in i['spec']['selector']['matchLabels'].items())
    for p in json.loads(subprocess.check_output(['kubectl', '-n', os.environ['NS'], 'get', 'pods', '-l', sel, '-o', 'json']))['items']:
        print('VOL pod', p['metadata']['name'], p['metadata']['creationTimestamp'],
              [c['restartCount'] for c in p['status'].get('containerStatuses', [])])
PY
rm -f "$W"
kubectl -n flux-system get helmchart "$NS-$REL" -o jsonpath='{.status.artifact.revision} {.status.artifact.digest}{"\n"}'
EOS
export NS REL WL
bash "$S/collect.sh" > "$S/baseline.txt" || { echo "ABORT: baseline failed (0 workloads or unreadable)"; exit 1; }
test "$(grep -c '^SPEC' "$S/baseline.txt")" -gt 0 || { echo "ABORT: baseline has no SPEC lines"; exit 1; }
cat "$S/baseline.txt"
bash "$T/nodesnap.sh" > "$S/nodes-before.txt" || { echo "ABORT: node snapshot"; exit 1; }   # Intel + NFD releases only (also falco's neighbours: harmless elsewhere)
```

Dry-run 2026-11-03: falco and the Intel operator baseline via the HelmRelease label (`SPEC`/`VOL` lines, `checksum/*` now captured); the gpu release baselines via `WL`; **known-bad**: gpu *without* `WL` prints `ABORT: 0 workloads …` and exits 1 (it used to exit 0 with an empty baseline).

**Step 2 — copy the tarball that is ACTUALLY DEPLOYED out of the cache.** Do not
re-download from the HTTP index: the index may already serve a different artifact
(that is the failure mode), and the cache is the only record of what is running.

```bash
POD=$(kubectl -n flux-system get pod -l app=source-controller -o name | cut -d/ -f2)
P=/data/$(kubectl -n flux-system get helmchart "$NS-$REL" -o jsonpath='{.status.artifact.path}')
test "$P" != /data/ || { echo "ABORT: HelmChart $NS-$REL has no artifact path"; exit 1; }
kubectl -n flux-system cp "flux-system/$POD:$P" "$S/deployed.tgz"
shasum -a 256 "$S/deployed.tgz"; ls -l "$S/deployed.tgz"
```

**Step 3 — fetch the candidate OCI chart and record the digest you will pin.**

```bash
helm pull "oci://$OCI_PATH" --version "$VER" -d "$S" 2>&1 | tee "$S/pull.txt"
shasum -a 256 "$S/$CHART-$VER.tgz"; ls -l "$S/$CHART-$VER.tgz"

# ref.digest is the MANIFEST digest = helm pull's "Digest:" line (verified equal to
# docker-content-digest on ghcr.io, quay.io and registry.k8s.io, 2026-09-28).
DIGEST=$(sed -n 's/^Digest: //p' "$S/pull.txt")
echo "$DIGEST" | grep -Eq '^sha256:[0-9a-f]{64}$' || { echo "ABORT: no manifest digest"; exit 1; }
echo "$DIGEST" > "$S/digest.txt"
```

If the tarball digests match, note it. **If they differ, do not stop** — a
repackage is common and usually benign. What matters is step 4.

**Step 4 — MANDATORY GATE: render both charts against the LIVE values and diff.**

```bash
helm -n $NS get values $REL --all -o yaml > "$S/live-values.yaml"
test "$(wc -l < "$S/live-values.yaml")" -gt 3 || { echo "ABORT: empty live values"; exit 1; }
mkdir -p "$S/old" "$S/new"
tar xzf "$S/deployed.tgz"    -C "$S/old"
tar xzf "$S/$CHART-$VER.tgz" -C "$S/new"
KV=$(kubectl version -o json | python3 -c 'import sys,json;v=json.load(sys.stdin)["serverVersion"];print(v["major"]+"."+v["minor"])')
for w in old new; do
  helm template $REL "$S/$w/$CHART" -n $NS -f "$S/live-values.yaml" \
    --kube-version "$KV" > "$S/render-$w.yaml" 2> "$S/render-$w.err"
  # GATE-CAN-FAIL: two EMPTY renders diff as identical. Both must contain manifest documents (the real
  # renders are as short as 17 lines for npu and 23 for gpu, so a line-count floor false-aborts: count documents).
  grep -q '^kind:' "$S/render-$w.yaml" || { echo "ABORT: $w render has no manifest documents -> $(head -3 "$S/render-$w.err")"; exit 1; }
done
test "$(grep -c '^kind:' "$S/render-old.yaml")" = "$(grep -c '^kind:' "$S/render-new.yaml")" || { echo "ABORT: object count differs old vs new"; exit 1; }
diff -u "$S/render-old.yaml" "$S/render-new.yaml" | tee "$S/render.diff"
```

(2026-11-03 dry run, falco 9.2.2: deployed and OCI tarballs byte-identical, both renders 736 lines, `render.diff` empty. The known-bad: with `helm` missing from PATH both renders are 0 lines and the `^kind:` assertion aborts. `helm` on PATH works in agent shells; `mise exec -- helm` failed in one sandboxed shell here, which is environment-specific: just require `helm version --short` to print the pinned v3.22.1.)

**Gate:** `render.diff` must be **empty**, or contain only differences you can
name and justify in the commit message (`Chart.yaml` maintainers, a stray dev file
the `.helmignore` misses). **Any rendered-object difference — an image, an RBAC
rule, a probe, a resource limit, a NetworkPolicy — aborts this component.** It is
then a chart *change* wearing a source change's clothes, and needs its own plan.

Then predict the roll the way helm-controller will cause it. Under `chartRef` the
chart version becomes `<VER>+<first 12 hex of the pinned digest>`; re-render with
that version and diff every workload's whole pod template (labels AND `checksum/*`
annotations — a labels-only check missed falco and node-feature-discovery):

```bash
D12=$(sed 's/^sha256://' "$S/digest.txt" | cut -c1-12)
rm -rf "$S/newmeta"; cp -R "$S/new" "$S/newmeta"
sed -E "s/^version:[[:space:]]*.*/version: $VER+$D12/" "$S/new/$CHART/Chart.yaml" > "$S/Chart.meta.yaml" && cp "$S/Chart.meta.yaml" "$S/newmeta/$CHART/Chart.yaml"
grep -q "^version: $VER+$D12$" "$S/newmeta/$CHART/Chart.yaml" || { echo "ABORT: the Chart.yaml version rewrite did not apply (a silent sed no-op would make rollpred print a false 'none')"; exit 1; }   # BSD sed: [[:space:]], not \s
helm template $REL "$S/newmeta/$CHART" -n $NS -f "$S/live-values.yaml" --kube-version "$KV" > "$S/render-newmeta.yaml" 2> "$S/render-newmeta.err"
python3 "$T/rollpred.py" "$S/render-old.yaml" "$S/render-newmeta.yaml"
```

Read the output as the restart list for the commit message and for Assertion 2.
Every release must end with the line `ROLL-PREDICTION:`; no such line means the tool
broke, not that nothing rolls. Dry-run 2026-11-03 (live pins): **falco** prints two
`WILL ROLL: DaemonSet/falco …checksum/config` / `…checksum/rules` lines (the known-bad
demonstration of the old predictor's blindness: it printed nothing for falco);
**node-feature-discovery** prints `WILL ROLL: DaemonSet/node-feature-discovery-worker`
and `Deployment/node-feature-discovery-master` (+ an informational hook-Job line);
**paperless-ngx** and the three **Intel** releases print only `ROLL-PREDICTION: none`.

**Step 5 — write the manifests.** `ocirepository.yaml` goes in the **app's own
folder**, not in `kubernetes/flux/meta`. That is the second half of the fix: a
source inside `cluster-apps` can only break its own app's Kustomization, while
every object under `./kubernetes/flux/meta` sits behind `cluster-meta`'s
`wait: true` and can block the whole tree. Follow `43a3b3e4` + `0c77bbb0`.

```yaml
---
# yaml-language-server: $schema=https://raw.githubusercontent.com/fluxcd-community/flux2-schemas/main/ocirepository-source-v1.json
apiVersion: source.toolkit.fluxcd.io/v1
kind: OCIRepository
metadata:
  name: <chart>
# Replaces HelmRepository/<repo> (HTTP). Why: an HTTP chart index is a mutable
# third-party URL wired into cluster-meta's wait gate, and spec.verify does not
# exist on the HelmRepository v1 API. See
# runbooks/maintenance/plans/flux-oci-chart-sources.md §1.
#
# THE DIGEST IS THE TRUST ANCHOR, not the tag and not the deny rule. An
# OCIRepository re-resolves tag -> digest every interval and the registry does
# not enforce tag immutability, so a tag overwrite upstream would replace this
# workload within the hour with NO git diff and NO PR. To move versions, change
# tag AND digest together, re-derived from the registry.
spec:
  interval: 1h
  layerSelector:
    mediaType: application/vnd.cncf.helm.chart.content.v1.tar+gzip
    operation: copy
  ref:
    tag: "<VER>"
    digest: sha256:<manifest-digest-from-step-3>
  url: oci://<registry>/<path>
```

Then, in the same commit — `migrate.py` (§8) writes exactly the manifest above, switches
the HelmRelease to `chartRef`, adds `ocirepository.yaml` to the app's `kustomization.yaml`
(or notes that there is none: `intel-device-plugin/vpu`), and optionally deletes the HTTP source:

```bash
# (a) positive control BEFORE the first edit, live: HelmReleases whose chart sourceRef is $REPO.
#     Exact match (the old `grep -rn "name: $REPO"` can never pass: `name: intel` matches intel-device-plugin-*,
#     and `name: node-feature-discovery` matches the HelmRelease's own metadata.name and a dependsOn).
kubectl get helmrelease -A -o jsonpath='{..sourceRef.name}' | tr ' ' '\n' | grep -c -x "$REPO"
#     measured 2026-11-03: intel 3, node-feature-discovery 1, gabe565 1, falcosecurity 1. For the three Intel commits the live
#     count is 3 before commit 1, 2 before commit 2 and 1 before commit 3 (read it AFTER the previous commit has reconciled and its
#     HelmRelease is Ready). Any other number, or 0, means a release already moved or the command is broken: ABORT.
python3 "$T/srcrefs.py" "$REPO"                                   # same count from the working tree + the files
# (b) write the manifests. Pass the 6th argument (the HelmRepository file) ONLY on the LAST release that uses $REPO:
#     for Intel that is npu (commit 3), NEVER the operator or gpu commits. migrate.py itself refuses to delete a
#     repository another HelmRelease still uses (that refusal is the deletion gate, demonstrated in §8).
python3 "$T/migrate.py" "$APPDIR" "$OCINAME" "$OCI_PATH" "$VER" "$(cat "$S/digest.txt")" [kubernetes/flux/meta/repositories/helm/$REPO.yaml]
python3 "$T/srcrefs.py" "$REPO"                                   # after the LAST release: 0
```

**Step 6 — validate, then commit (shared-worktree rules).**

```bash
task kubeconform
grep -n "$CHART\|$REL" runbooks/auto-update-policy.yaml    # deny globs must still match the new dep name (none of the stage 3 set has a deny rule today: they stay auto-updatable, which is why Step 0b matters)
git add -N $APPDIR/ocirepository.yaml          # --only cannot name an untracked file without intent-to-add
# The exact --only list per release is the table in §1.00. Shape (Intel operator/gpu, which do NOT delete the repo):
#   git commit --only $APPDIR/ocirepository.yaml $APPDIR/kustomization.yaml $APPDIR/helmrelease.yaml -F "$S/msg.txt"
# last-user releases add the two meta paths:
#   ... kubernetes/flux/meta/repositories/helm/$REPO.yaml kubernetes/flux/meta/repositories/helm/kustomization.yaml
# npu: NO kustomization path (the directory has none):
#   git commit --only $APPDIR/ocirepository.yaml $APPDIR/helmrelease.yaml kubernetes/flux/meta/repositories/helm/intel.yaml kubernetes/flux/meta/repositories/helm/kustomization.yaml -F "$S/msg.txt"
git log -1 --format=%s; git show --stat HEAD        # the subject must be YOURS and every file yours
git push
```

The commit message must state: the deployed tarball digest/size, the OCI layer
digest/size, that `render.diff` was empty (or exactly what it contained), the
pinned `ref.digest`, and **which workloads are expected to roll**.

### 3.3 Stage 0 — teach the pipeline about `chartRef` (do this first)

> **STATUS 2026-11-03: items 1, 2 and 4 are DONE in `97c3e913` and have survived
> weeks of sweeps** (the version snapshot carries `k8s-gateway` with chart 3.7.2;
> `runbooks/tests/test-helmrelease-chartref-shape.py` passes 39/39). **Item 3's
> fail-open is a pre-existing property of G3, not something this plan creates** —
> measured in §1.0 D1: most chart dependencies already resolve no release notes
> today. It is therefore an operator decision (D1), not a Stage 0 task, and the
> old text's claim that the derivation was "fixed" holds only for some OCI paths.

Repo-only; no cluster change. Three edits plus a ground-truth test:

1. **DONE (`97c3e913`).** `runbooks/check-all-versions.py` → `parse_helmrelease()`: when `spec.chartRef`
   is present, resolve the sibling `ocirepository.yaml` in the same directory to
   recover `chart_name` (OCI path's last segment / CR name) and `chart_version`
   (from `ref.tag`), and register the `oci://` URL so
   `get_latest_chart_version()` takes its existing OCI branch.
2. **DONE (`97c3e913`).** Same for `coverage.py` → `_chart_source_for()`, so the chart-publish-age
   cooldown keeps working instead of silently returning `None`.
3. **PARTIAL — derivation fixed, FAIL-OPEN STILL OPEN.** `get_repo_info_from_image()` / `get_chart_repo_info()`: strip a
   `charts` / `charts-mirror` / `helm-charts` / `helm` path segment so G3
   resolves real upstream release notes. Today
   `ghcr.io/k8s-gateway/charts/k8s-gateway` resolves to the nonexistent repo
   `k8s-gateway/charts` and G3 fails **open**.
   The segment strip landed in `97c3e913`, and k8s-gateway's real repo
   (`k8s-gateway/k8s_gateway`, underscore — API-verified) is pinned in the
   mapping table. What remains: a derived `owner/chart` is still a HEURISTIC
   that can 404 (a mirror namespace does not own the upstream project), and
   `auto-update.py`'s G3 still treats an unresolvable lookup as "no breaking
   changes". **Closing this means G3 must refuse to pass when it cannot
   measure**, which changes what is auto-mergeable — own operator decision.
4. **DONE (`97c3e913`).** `runbooks/tests/` — a test that feeds the real migrated
   `kubernetes/apps/network/internal/k8s-gateway/helmrelease.yaml` in and asserts
   `chart_name == 'k8s-gateway'` and `chart_version == '3.7.2'`, with the
   pre-migration file as the negative case. Per
   `docs/sops/audit-script-correctness.md`, a check validated only on synthetic
   input is not validated.

**Stage 0 is satisfied for starting stage 3** (it has survived sweeps — proof in §4.1); stages 3-7 additionally wait for decision D1.

### 3.4 Stage 2 — `csi-driver-smb` ✅ EXECUTED 2026-09-11, by a different route

> **STOP. DO NOT EXECUTE THE BODY OF THIS STAGE.** It was completed on
> 2026-09-11 in `001ab0ad` + `9a8eb6e5`, but **not** via charts-mirror OCI as
> planned below. Running the text as written would REPLACE an upstream commit
> pin with a third-party mirror pin — a regression, not progress.
>
> What shipped instead, and why it is stronger:
> * **`GitRepository` pinned to `ref.commit: 59dce96e11522a46354d6970393b00b1c2a57351`**
>   (the commit tagged v1.20.3), with `ref.branch: release-1.20` — required
>   because the release is not reachable from `master`, which has diverged.
>   A git commit SHA **is** the content address, so this needs no separate
>   digest pin the way an OCI tag does.
> * **Trust root stays on kubernetes-csi.** charts-mirror is a re-publisher;
>   using it would have moved the root off upstream and required proving the
>   mirror's bytes equal upstream's. That remains a legitimate operator choice,
>   just not the one taken.
> * **A trap this stage's original plan would have walked into:** the repo's
>   `index.yaml` hardcodes an **absolute** tarball URL back to the branch
>   (`…/csi-driver-smb/master/charts/v1.20.3/…`). Pinning the *index* to a
>   version path would still have fetched the *chart* from `master` — a fix
>   that looks real and is not. The GitHub Pages mirror is equally mutable and
>   additionally serves a repackaged 1.20.3.
> * **Verified no-op:** Helm release stayed at **v5** (no v6 secret), all three
>   workload generations 5/5, 0 restarts, 19/19 CIFS StorageClasses, 114/114
>   PVCs Bound, and six real CIFS mounts read including both catastrophic-tier
>   shares. `helm template` identical 619/619 lines, 12/12 objects matching live.
> * **`spec.timeout: 5m` was required** (`9a8eb6e5`): this swapped a few-KB index
>   fetch for a ~118 MB clone **inside the `wait: true` gate** that blocks
>   `cluster-apps`, against a 60s default. Any future GitRepository source in
>   this gate needs the same consideration.
> * **REGRESSION TO CLOSE — version tracking is gone.** Renovate's flux manager
>   reads a GitRepository only via `ref.tag`, and the HelmRelease no longer has
>   a `version:` field, so neither Renovate nor `check-all-versions.py` can
>   compare against upstream; the chart's image tags are frozen at the pinned
>   commit too. Needs a Renovate `customManagers` decision. Do not "fix" it with
>   a comment-only bump PR that auto-update could merge as safe.

#### Original Stage 2 plan (superseded, retained for its reasoning)

It is first because its source is the worst (a **mutable git branch** via
`raw.githubusercontent.com/kubernetes-csi/csi-driver-smb/master/charts` — the same
silent-404 shape that caused today's outage) and its blast radius is the largest
(**all 19 CIFS StorageClasses**, 21 Bound PVCs, including the catastrophic-tier
`cifs-jellyfin-media` / `cifs-plex-media`).

Three things that bound the risk, all verified:

- **No data risk.** All 19 CIFS classes are `reclaimPolicy: Retain`. This stage
  creates and deletes **no PVC** — `docs/sops/storage-safety.md` forbids it for
  CIFS classes and a root-`subdir` class is the 4.7 TB incident. The test in §4.2
  writes through an *already-mounted* volume instead.
- **A node-plugin restart does not unmount.** Existing mounts live in the node's
  mount namespace and survive. What fails during the roll is *in-flight*
  attach/provision, which is why this runs in a window with no other storage work.
- **The source exists and is signed.** `oci://ghcr.io/home-operations/charts-mirror/csi-driver-smb`
  carries `1.20.3` — our exact pin — and is cosign-signed (sigstore bundle, not a
  `.sig` tag; see §1.5(d)).

Read `docs/sops/storage-safety.md` before this stage, not after.

### 3.5 Stage 8 — `unpoller` is blocked, and must not be smuggled in

`oci://ghcr.io/unpoller/helm-chart/unpoller` exists and is signed, but carries
only **2.5.0 → 2.8.0**; a manifest `HEAD` on `2.4.0` returns 404. Our pin is
`2.4.0`. So migrating `unpoller` to OCI **forces a chart upgrade in the same
change**, which violates the §3.2 step-4 gate by construction (the render diff
cannot be empty across a minor bump).

Do not "just take 2.5.0 while we're in there". Write a separate
`unpoller-2.5.0`-style plan with its own release-notes review, and leave
`unpoller` on HTTP until then. It is an internal monitoring exporter with no
consumer depending on its availability for recovery, so parking it is cheap.

### 3.6 Stage 7 — the 11 charts with no OCI source, and which option creates work

Eleven referenced charts have **no OCI artifact anywhere** — not upstream, not in
`charts-mirror`: `apache-superset`, `blakeblackshear` (frigate), `dirsigler`
(uptime-kuma), `elastic` (eck-operator), `influxdata`, `jameswynn` (homepage),
`jellyfin`, `penpot`, `plex`, `rm3l` (adguard-home), `sure`. All 11 publish via
`chart-releaser-action` to a gh-pages `index.yaml` and never run `helm push` —
a reliable negative signal, though a private-but-existing package is
indistinguishable from an absent one over anonymous pulls, so treat each as
*unconfirmed-absent* rather than proven-absent.

| option | ongoing work for us | trust | verdict |
|---|---|---|---|
| **Upstream's own OCI registry** | **none** — Renovate tracks the tag, upstream carries publishing | highest: the chart's canonical distribution point | **always first choice** — it is what stages 3, 5 and 6 use |
| **Contribute the chart to `home-operations/charts-mirror`** | **none per version** after the PR lands — the community runs the sync, artifacts are cosign-signed and Renovate-tracked. **But:** its README prunes a chart **6 months after upstream ships OCI** and says it is our responsibility to move to the official source, so this adds a **recurring re-check**, not a permanent home | maintained community project rather than one person's Pages site | **second choice** and the right answer for most of the 11; one upstream PR per chart |
| **`flux mirror` into `ghcr.io/nachtschatt3n`** | **yes, bounded**: one config file + one scheduled runner (GitHub Action cron or a CronJob) + a GHCR push credential. New upstream versions are picked up automatically by a `version:` semver range — **no per-version push** — but a failing mirror job becomes a new way for a pinned version to be missing | we control the registry; nothing signed upstream to carry over, so we would sign our own | **third choice**, and the right one for `plex` if upstream stays HTTP-only. **Explicitly NOT a fork — it is an automated re-publish, there is nothing to hand-merge.** Note it is v0.x (`flux plugin install mirror` works on our v2.9.6; not installed today) |

What none of these is: **vendoring the chart into this repo.** The operator
rejected that on maintenance-burden grounds and it stays rejected — it is the one
option that creates unbounded per-version hand-work.

**Update 2026-09-28:** `plex` is DONE (102ec800, Shape D GitRepository). `rm3l` was repointed
(59c24761, 2026-09-18) after its host died — a second outage of this plan's exact shape — to a
`raw.githubusercontent.com/rm3l/helm-charts/gh-pages` index, i.e. a mutable-branch source.

**Recommended split for the 11:** propose `plex` and `jellyfin` to
`charts-mirror` first (both are widely used, so the contribution is likely
welcome and the mirror is signed); if `plex` is declined or slow, `flux mirror` it
into our own GHCR, because its mutable-branch source is the second-worst in the
estate. Leave the remaining nine on HTTP **with their risk named in this plan**
rather than pretending the migration is complete — an HTTP source that is
honestly listed as HTTP is not the failure mode that caused today's outage; an
unowned one is.

### 3.7 Stage 9 — `spec.verify`: pilot it, then per registry, never blanket

`spec.verify` fails **closed**: on an artifact it cannot verify, the source stops
reconciling — which on `cilium` or `csi-driver-smb` is not cosmetic.

```bash
# All THREE cosign layouts must be checked (see §1.5(d)):
TOK=$(curl -s "https://ghcr.io/token?scope=repository:<path>:pull&service=ghcr.io" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
# (1) legacy .sig tag   (2) bare sha256-<digest> tag holding a sigstore bundle
curl -s -H "Authorization: Bearer $TOK" "https://ghcr.io/v2/<path>/tags/list" \
  | python3 -c 'import sys,json;t=json.load(sys.stdin).get("tags") or [];print("sig-tags",sum(1 for x in t if x.endswith(".sig")),"bare-sha-tags",sum(1 for x in t if x.startswith("sha256-") and not x.endswith(".sig")),"of",len(t))'
# (3) OCI 1.1 referrers
curl -s -H "Authorization: Bearer $TOK" "https://ghcr.io/v2/<path>/referrers/sha256:<manifest-digest>" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print([m.get("artifactType") for m in d.get("manifests",[])])'
```

**Pilot first, on something expendable.** It is **unverified** whether Flux
2.9.6's `verify.provider: cosign` accepts the newer
`application/vnd.dev.sigstore.bundle.v0.3+json` layout, and that layout covers 5
of the 6 charts-mirror charts plus falco. So: enable `verify` on **one** low-stakes
signed component (`falcosecurity` or `descheduler`), confirm the source still
reconciles **after a deliberate `flux reconcile source oci …`**, and only then
extend it. `matchOIDCIdentity` must be pinned to an identity actually observed —
a drifting identity is the same fail-closed outage with extra steps. Never enable
it on `cilium`, `csi-driver-smb` or `longhorn` until it has soaked a week
elsewhere.

### 3.8 Stage 10 — `source-controller` storage: cap the emptyDir, do NOT give it a PVC

Measured, so the recommendation is evidence-led and the answer is **no PVC**:

- `/data` held **41.8 MB / 328 files** (helmchart 19.1 MB, helmrepository
  16.0 MB, gitrepository 6.8 MB, ocirepository 16 KB) after 5 days and 0
  restarts (2026-09-11); **38.4 MB / 218 helmchart files, 0 restarts since the
  pod started 2026-10-25** (2026-11-03). A PVC would be ~24× oversized for it.
- `deploy/source-controller` is already `replicas: 1` + `strategy: Recreate` in
  the vendored upstream manifest, so the `longhorn-rwo-multi-attach` trap does
  not apply — but an RWO Longhorn volume **pins the pod's reschedule** to a node
  that can attach it. Today a drain reschedules instantly and re-downloads 42 MB;
  with a PVC it waits for detach/reattach. For this cache the PVC makes failover
  *slower*, and it adds a 95th Longhorn volume to the nightly backup set holding
  data that is 100% re-derivable.
- `flux-operator` does support it (`FluxInstance.spec.storage.{class,size}`, both
  required; it templates a hardcoded `PersistentVolumeClaim/source-controller`
  with `ReadWriteOnce` and no PV-name knob, which also collides with the
  speaking-PV-name rule in `docs/sops/longhorn.md`). The option exists and is
  still the wrong one here.
- **The real defect is that both emptyDirs have no `sizeLimit`** while `/data`
  sits on the node root filesystem (69% full when measured 2026-09-11 — re-measure with `talosctl df` before quoting a figure). Cap it via
  `FluxInstance.spec.kustomize.patches` (currently holds one GitRepository `ignore` patch — APPEND, do not replace): `sizeLimit: 2Gi` on
  `data`, something small on `tmp`.
- **And the honest correction to a claim made today:** an OCIRepository's stored
  artifact lives in *the same emptyDir* (`/data/ocirepository`, 2 files measured),
  so migrating to OCI does **not** make chart recovery survive a pod restart. What
  it buys is that the artifact can be **re-fetched** afterwards — an immutable
  digest in a live registry is re-fetchable, a deleted Pages index is not.
  Durability comes from the source being alive and immutable, never from the cache.

This stays in this plan rather than being spun out because it is the other half of
`F-764e4fc3` and is meaningless without the re-fetchability the earlier stages
deliver. It rolls `source-controller` itself — schedule it **last**, alone.

## 4. Verification

`Ready=True` is worthless here on its own: it has been green through two total
internal-DNS outages, and worse, a `Ready` can be served **off the stale emptyDir
cache**. Every assertion below is written to exclude that.

### 4.1 Stage 0 (tooling) — CONTENTS ASSERTION

> **CONTENTS ASSERTION:** the migrated, `chartRef`-sourced component still appears
> in the version snapshot **with a non-empty chart name and version** — measured
> by `runbooks/check-all-versions.py` output and the Quick Overview row for
> `k8s-gateway`, compared to the pre-Stage-0 run where that row's chart cell is
> empty.

```bash
python3 runbooks/check-all-versions.py 2>&1 | grep -v 'mise WARN' | tail -3          # regenerates runbooks/version-check-current.md
grep -n '| `k8s-gateway`' runbooks/version-check-current.md                           # chart cell must read 3.7.2, not '-'  (live 2026-11-03: "| `k8s-gateway` | `network` | 3.7.2 ✅ |")
# Unresolved-sources table: the migrated component must NOT be in it, and the 3 git-sourced charts MUST be (positive control: proves the table was read).
sed -n '/Unresolved chart sources/,/^### Upstream freshness/p' runbooks/version-check-current.md | grep -c -e '`k8s-gateway`'                       # must print 0
sed -n '/Unresolved chart sources/,/^### Upstream freshness/p' runbooks/version-check-current.md | grep -c -e '`plex`' -e '`oc8`' -e '`csi-driver-smb`'  # must print 3 (a 0 here means the section moved and the line above proves nothing)
.venv/bin/python3 runbooks/maintenance-plan.py --validate && echo VALIDATE_OK
.venv/bin/python3 runbooks/tests/test-helmrelease-chartref-shape.py | tail -1         # expect "39 passed, 0 failed"
```

The G3 question formerly gated here with a `grep -c 'release notes unavailable…'`
on `auto-update.py` (a gate on a *string*: rewording the message would pass it
without closing anything) is now decision **D1** in §1.0 plus the per-component
Step 0b probe, whose failure mode was demonstrated.

A still-empty chart cell, or the migrated component appearing in the unresolved table, means Stage 0 did not work and **stages 3-7 must not
start** — each would delete a component from the update pipeline.

### 4.2 Stages 2-7, per component — three assertions, all required

> **CONTENTS ASSERTION 1 (fresh artifact, not stale cache):** the new
> OCIRepository's `status.artifact.revision` equals the manifest digest we pinned
> **and** its `status.artifact.lastUpdateTime` is **after** the push commit's
> timestamp. A `Ready` whose artifact predates the commit is the cache answering.
> (With `ref.digest` pinned the live OCIRepositories — k8s-gateway and the ARC pair —
> report `revision = sha256:<manifest digest>` with NO `<tag>@` prefix, so the literal
> `<VER>@<digest>` compare of the first draft false-failed every component.)

**Before any HelmRelease assertion, the OCIRepository must be `Ready=True`** (this is the first in-cluster use of `registry.k8s.io` as an OCIRepository, for node-feature-discovery; a source that cannot fetch leaves the HelmRelease stuck with the OLD pods kept running, which `git revert` fixes):

```bash
kubectl -n $NS wait --for=condition=Ready ocirepository/$OCINAME --timeout=5m          # must print "... condition met"; a timeout = STOP, inspect `describe`, revert if the registry path is wrong
REV=$(kubectl -n $NS get ocirepository $OCINAME -o jsonpath='{.status.artifact.revision}')
test "$REV" = "$(cat "$S/digest.txt")" && echo REVISION-IS-PINNED-DIGEST      # must print it; known-bad: compare to "$VER@$(cat "$S/digest.txt")" -> never equal
kubectl -n $NS get ocirepository $OCINAME -o jsonpath='{.status.artifact.lastUpdateTime}{"\n"}'
git log -1 --format=%cI HEAD                                                   # lastUpdateTime must be later
```

> **CONTENTS ASSERTION 2 (workload change equals the PREDICTED change, nothing else):**
> exactly **one** new Helm revision whose `chartVersion` is `<VER>+<digest12>`; every
> Deployment/StatefulSet/DaemonSet keeps the same images, replica counts and container
> set (`SPEC` lines identical); and the `VOL` lines differ **only** as Step 4's
> `rollpred.py` predicted. **No-roll releases** (paperless-ngx, the three Intel
> releases): the `VOL` lines — generation, pod names, `creationTimestamp`, restart
> counts — are IDENTICAL. **Rolling releases** (falco, node-feature-discovery, and the
> later-stage ones): generation +1, `checksum/*` / `helm.sh/chart` change, new pods Ready with 0
> restarts, each pod's `creationTimestamp` after the commit.

```bash
export NS REL WL
test "$(grep -c '^SPEC' "$S/baseline.txt")" -gt 0 || { echo "ABORT: empty baseline"; exit 1; }
bash "$S/collect.sh" > "$S/after.txt" || { echo "ABORT: after-collect failed"; exit 1; }
diff <(grep '^SPEC' "$S/after.txt") <(grep '^SPEC' "$S/baseline.txt") && echo SPEC-IDENTICAL   # must print SPEC-IDENTICAL
# NO-ROLL release: must print NO-ROLL-CONFIRMED.   ROLLING release: the diff is EXPECTED non-empty; read it against rollpred.py's output.
diff <(grep '^VOL' "$S/after.txt") <(grep '^VOL' "$S/baseline.txt") && echo NO-ROLL-CONFIRMED
# Known-bad demo (run once): sed 's/:[^:)]*)/:bogus)/' "$S/baseline.txt" > "$S/bad.txt";
# diff <(grep '^SPEC' "$S/bad.txt") <(grep '^SPEC' "$S/baseline.txt") must be NON-empty.
kubectl -n $NS get events --field-selector type=Warning --sort-by=.lastTimestamp | tail -20
```

> **CONTENTS ASSERTION 3 (behavioural, per component):** the thing the chart
> delivers still works, asserted directly. Use the row for the component:

| component | the assertion — not `Ready`, not `Running` |
|---|---|
| `csi-driver-smb` | **A real read/write round-trip through an already-mounted CIFS volume** in an existing pod (write a probe file, read it back, remove it), on a **non-catastrophic** class; plus all 21 CIFS PVCs still `Bound` and `csi-smb-node` 3/3 Ready. **Create and delete NO CIFS PVC** (`docs/sops/storage-safety.md`). |
| `longhorn` | RW round-trip through an existing `longhorn` PVC, **and** volume counts by `state`/`robustness` identical to the §2(4) baseline, **and** the next `storage/daily-backup-all-volumes` run completes (cross-check its newest Completed Backup CR — lastBackupAt can lag, docs/sops/backup.md). |
| `cilium` | Cross-node pod-to-pod reachability **and** in-cluster DNS resolution from a pod, after the DaemonSet settles; `cilium-dbg status --brief` on each node returns OK on all 3. |
| `jetstack` (cert-manager) | Create a throwaway `Certificate` in a scratch namespace, assert it reaches `Ready` within 2 min (this exercises the webhook, which is the part that rolls), then delete it. |
| `authentik` | **A real login through each affected path** (`docs/sops/authentik.md`); do not trust `/-/health/ready`. Re-run the outpost `kubernetes_disabled_components` audit **from the live outpost list**, not a repo grep. |
| `grafana`, `opentelemetry`, `unpoller`, `elastic` | **The series still arrive**: scrape target `up == 1` *and* a representative series non-empty over a window starting **after** the roll; for log-emitting components a **non-zero document floor** in Elasticsearch, not just a ceiling. |
| `external-dns` | A record it owns still resolves publicly **and** internal names still resolve through the internal resolver. Counts, not names. (Log-absence is NOT a PASS criterion — it was never shown to match a known-bad case.) |
| `nextcloud` | `occ status` plus a file listing returning a non-zero count — its MariaDB StatefulSet rolls. |
| `gabe565` (paperless-ngx) | **No restart expected, so assert exactly that**: the pod name and `creationTimestamp` captured in the baseline (`VOL pod …` line) are IDENTICAL after (`NO-ROLL-CONFIRMED`), the HelmRelease is Ready on the new revision, **and** the HTTPRoute serves real content: `H=$(kubectl get httproute paperless-ngx -n office -o jsonpath='{.spec.hostnames[0]}')`, `curl -sS -o "$S/pl.html" -w '%{http_code} %{size_download}\n' "https://$H/accounts/login/"` prints `200` and more than 2000 bytes, and `grep -c -i paperless "$S/pl.html"` is at least 1. Dry-run: live login page = `200 6889`, 2 matches; **known-bad** `https://$H/definitely-not-here/` = `302 0`, 0 matches. (The earlier consume-directory round trip created a document, contradicted "count equal", and tested nothing a non-restarting release could have broken.) |
| `plex`, `jellyfin` | Library item **counts** match the pre-roll baseline (counts only — never titles, in any committed artifact). |
| `intel` (operator, gpu, npu) | **No restart**: `bash "$T/nodesnap.sh" | diff - "$S/nodes-before.txt"` is empty (12 rows: per node `intel.feature.node.kubernetes.io/gpu` and `/npu` labels plus `gpu.intel.com/i915` and `npu.intel.com/accel` capacity; 2026-11-03 baseline: all `true`, `i915=5`, `accel=1` on all 3 nodes) **and** the DaemonSet pods are unchanged (`intel-gpu-plugin-intel-gpu-plugin` / `intel-npu-plugin-intel-npu-plugin` `VOL pod` lines identical; the operator's controller-manager pod identical). `nodesnap.sh` exits 1 unless it sees exactly 12 rows (an empty capacity map is the silent failure). |
| `node-feature-discovery` | **Restarts (worker DaemonSet 3/3, master Deployment 1/1).** `kubectl rollout status` can green-light the OLD generation: assert, copy-paste, the worker `kubectl get ds node-feature-discovery-worker -n kube-system -o jsonpath='{.status.observedGeneration} {.metadata.generation} {.status.numberReady} {.status.updatedNumberScheduled} {.status.desiredNumberScheduled}'` (live `5 5 3 3 3`) and the master `kubectl get deploy node-feature-discovery-master -n kube-system -o jsonpath='{.status.observedGeneration} {.metadata.generation} {.status.readyReplicas} {.status.updatedReplicas} {.spec.replicas}'` (live `5 5 1 1 1`) — first two equal, remaining three equal the expected count; **then** `bash "$T/nodesnap.sh" | diff - "$S/nodes-before.txt"` must be EMPTY — the same 12 rows, with before/after values pasted into the commit/GO record. This is the gate that matters: the Intel device plugins are scheduled by the NFD-published `intel.feature…/gpu|npu` labels, so a label lost during the NFD roll would evict the plugin pods and drop `gpu.intel.com/i915` for the seven GPU consumers. If the snapshot differs, re-run it every 30 s for up to 5 minutes (labels are re-published after the master settles) and declare a regression only if the difference persists past that bounded poll; then STOP and revert (§5). |
| `falcosecurity` | **Restarts (DaemonSet `falco`, 3 pods, `maxUnavailable: 1`, so a per-node detection gap while each pod restarts).** (1) readiness, copy-paste: `kubectl get ds falco -n security -o jsonpath='{.status.observedGeneration} {.metadata.generation} {.status.numberReady} {.status.updatedNumberScheduled} {.status.desiredNumberScheduled}'` — live baseline `34 34 3 3 3`; PASS = the first two numbers equal each other and the last three equal 3 (after the move the generation numbers rise by one, so compare, do not hard-code); every `falco` pod `2/2` Ready with a `creationTimestamp` after the commit. (2) **Sink read-back with a positive control from BEFORE the roll.** falco emits continuously (≈2-3 alerts per node per minute), so the real stream is the trigger: `CUT=$(python3 -c "import datetime;print((datetime.datetime.utcnow()-datetime.timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%S'))")` then `kubectl exec -n security wazuh-manager-master-0 -- tail -n 20000 /var/ossec/logs/alerts/alerts.json | python3 "$T/falco_sink.py" "$CUT"` must print `FALCO-SINK-OK` (alerts from all 3 agents) **before the commit** — if it does not, the sink read is broken and the post-roll read proves nothing: ABORT. (3) After the DaemonSet settles, record `ROLLDONE=$(date -u +%Y-%m-%dT%H:%M:%S)` and repeat the same read with cutoff `$ROLLDONE`, polling for up to 10 minutes (Wazuh lags a few minutes): it must print `FALCO-SINK-OK` — all three nodes producing falco alerts AFTER the roll. **Known-bad** (run 2026-11-03): cutoff `2099-01-01T00:00:00` prints `FALCO-SINK-FAIL` and exits 1. **Do not run the sink read within ~15 minutes either side of 00:00 UTC:** `alerts.json` rotates at UTC midnight, so a read straddling it sees only the new file. Informational only, NOT a gate (the sink read is the gate): no `[error]` lines in the falco pod logs (`docs/sops/falco.md` Test 1). |
| everything else | The app's own HTTPRoute returns its real content (non-empty, not an error page) on the path a user would use. |

### 4.3 Whole-plan assertion, at the end of every stage

```bash
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'     # cluster-meta AND cluster-apps
kubectl get helmrepository -A --no-headers | wc -l           # live baseline 37 (28 HTTP + 9 oci): falls by exactly what the stage removed (stage 3: 4 repos -> 33)
kubectl get ocirepository  -A --no-headers | wc -l           # live baseline 4: rises by exactly what the stage added (stage 3: 6 releases -> 10; intel's three releases may share one OCIRepository per chart, so count names, not releases)
```

And the one that actually proves the point of the whole plan — run it **once**,
after the last app stage, in an attended window:

```bash
kubectl -n flux-system rollout restart deploy/source-controller
# then assert EVERY HelmRelease re-reconciles from its source with a COLD cache:
flux get sources all -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A | awk 'NR==1 || $5 != "True"'
```

This is the scenario `F-764e4fc3` is about. It is the only real test of
re-fetchability, and it is exactly why it does not run mid-stage: a component
still on HTTP whose upstream has died will fail here, and that is the finding, not
a regression of this plan.

## 5. Rollback

Per component, and always the same shape because every stage is
`rollback_class: git-revert`:

```bash
git revert --no-edit <sha>    # restores the HelmRepository file + its kustomization
                              # entry + the HelmRelease chart block, atomically
git push
```

Then **confirm the cluster is actually back** — do not assume:

```bash
kubectl -n flux-system get helmrepository $REPO -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'   # True
kubectl -n flux-system get helmchart $NS-$REL -o jsonpath='{.status.artifact.revision}{"\n"}'                         # re-created
kubectl -n $NS get helmrelease $REL -o json | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'].get('lastAttemptedRevision'), [(h['version'],h['chartVersion'],h['status']) for h in d['status']['history']])"
export NS REL WL
bash "$S/collect.sh" > "$S/reverted.txt" || { echo "ABORT: post-revert collect failed"; exit 1; }
# Compare ONLY what a revert must restore. The full collect.sh output can never diff clean: it carries the HR revision,
# the Helm history (which GAINS entries on a revert) and the HelmChart line. Pod names/timestamps and generations also
# legitimately differ for the releases that restarted.
diff <(grep '^SPEC' "$S/reverted.txt") <(grep '^SPEC' "$S/baseline.txt") && echo SPEC-BACK-TO-BASELINE        # all six releases: must print it
# falco and node-feature-discovery additionally: the workload VOL lines minus generation and minus the pod lines.
# The checksum/* annotations must be the BASELINE values again, i.e. the pod template is the pre-move one.
diff <(grep '^VOL' "$S/reverted.txt" | grep -v '^VOL pod' | sed -E 's/ gen [0-9]+//') \
     <(grep '^VOL' "$S/baseline.txt" | grep -v '^VOL pod' | sed -E 's/ gen [0-9]+//') && echo VOL-TEMPLATE-BACK-TO-BASELINE
```

(Dry-run 2026-11-03 against live falco: both lines print. **Known-bad:** a baseline whose `checksum/config` prefix is replaced by the predicted post-move value (`sed 's/2bd4ff4b/135ba72d/'`) makes the second `diff` non-empty and `VOL-TEMPLATE-BACK-TO-BASELINE` is not printed — i.e. a falco still on the moved template is caught. The `VOL pod` lines are excluded on purpose: a rolled DaemonSet has new pod names and `creationTimestamp`s after the revert.)

Three revert-specific facts, so they are not mistaken for failure:

1. **The revert rolls the workload a second time** — `helm.sh/chart` loses its
   `_<digest>` suffix, so the pod template changes back. Budget **two** rolls per
   component, not one. This is the main reason stages 2, 5 and 6 want an attended
   window with slack.
2. **The revert re-creates a dependency on the HTTP index.** If the revert is
   because the OCI path was wrong, fine. If the HTTP source is *also* sick,
   reverting restores a broken source into `cluster-meta`'s wait gate and
   re-blocks all delivery. Check first:
   `curl -sS -o /dev/null -w '%{http_code}\n' <repo-url>/index.yaml`.
3. **Stage 1 (the 6 deletions) reverts cleanly but pointlessly** — the objects
   were referenced by nothing. If something broke after Stage 1 the cause is
   elsewhere; re-adding the sources will not fix it.

4. **Stage 3 specifics (two rolls each for falco and node-feature-discovery).** Forward = one restart, revert = a second restart of each (the pod-template checksum annotations return to the old values). The four other releases revert with no restart. **Intel revert order is newest first: npu (commit 3), then gpu, then the operator.** The npu revert brings `intel.yaml` back; reverting the operator or gpu commit alone, while `intel.yaml` is still deleted, would point that HelmRelease at a HelmRepository that no longer exists. Commits 1 and 2 never deleted it. After a falco revert, repeat the §4.2 falco sink read (`FALCO-SINK-OK` with a cutoff after the revert settled); after an NFD revert, repeat the `nodesnap.sh` diff.

For Stage 0 the rollback is the same `git revert`, confirmed by the version
snapshot regaining its pre-change row count. For Stage 10 it removes the
`kustomize.patches` entry and `source-controller` returns to an unbounded
emptyDir.

## 6. Interference notes

- **Every stage perturbs the delivery path itself.** `cluster-meta` has
  `wait: true` and `cluster-apps` `dependsOn` it, so a mistake in any stage blocks
  *all* deployments, not just the component's. **No other plan should share a
  window with a stage of this plan**, and the window agent should run this plan's
  stage **first** so a failure is diagnosed before other work is misattributed to
  it.
- **A node roll restarts source-controller (cold cache): never share a window with one;
  talos-1.14.1 executed 2026-09-27.** (Historical: this was `conflicts_with: [talos-1.14.0]`.) A node
  roll restarts `source-controller` and empties the 122-artifact cache; it also
  rebuilds ~50 Longhorn replicas per node. Stages 2 and 6 roll the CSI driver,
  `longhorn-manager` and the CNI DaemonSet. Never the same window, preferably not
  the same weekend.
- **`shared: [flux-sources, cni-adjacent, cert-manager, storage/longhorn, dns-internal, monitoring]`**
  — `flux-sources` is the gate above; the rest name what the §1.4 roll touches.
  Stage 5 and Stage 9's pilot touch `monitoring`, which already carries an
  unrelieved interference warning on `sat-attended:2026-09-12` between
  `edot-collector-0.160.0` and `grafana-orphan-dashboard-uid` — do not add a
  monitoring stage to a slot that already holds two monitoring plans.
- **Stage 3 window rules (2026-11-03 review).** Step 0 (the safe-update apply) runs first in every window — re-run §2 after it; re-read the live `VER` of each release; no `kube-prometheus-stack` bump may be windowed on 12-13; after `helm-drift-detection` P1 (sat 11-28) rebase the six edits and take the §3.2 Step 1 baseline AFTER it, because it adds `spec.driftDetection` to every HelmRelease and changes `generation` bookkeeping.
- **Ordering is fixed by dependency, not preference.** Stage 0 before any of 2-7
  (otherwise each migration silently deletes a component from the update
  pipeline). Stage 1 may share Stage 0's window — it is subtraction only. Stage 2
  before 3-7 only because blast radius should be retired while attention is high;
  if that feels wrong on the day, run Stage 3 first as a rehearsal — it is the LOWEST-impact stage,
  not an impact-free one: falco and node-feature-discovery restart once on the forward move
  and once on a rollback (§1.00); only the first three Intel commits are zero-impact. Stage 9 only after a soak. Stage 10 last,
  alone.
- **At most one component per window in Stage 6**, and never `cilium` +
  `longhorn` together: CNI churn plus storage-control-plane churn in one window is
  how a recoverable mistake becomes an unrecoverable one.
- **Slot reality at the time of the re-plan (2026-11-03, from `maintenance-plan.py --open`).**
  `sun-attended:2026-12-13` currently holds only this plan (schedulable budget
  `200 - 20 = 180` min; the 100-min Stage 3 slice fits with room for the 20-min
  Step 0 reserve and a hold-back). The neighbours that matter, in time order:
  `sun-attended:2026-11-15` `longhorn-1.13.0` (storage control plane — finished
  and green three weeks before), `sun-attended:2026-11-22` `talos-linux-1.14.5`
  (restarts source-controller; three weeks earlier, cold cache long gone),
  `sat-attended:2026-11-28` `helm-drift-detection` (P1 adds `spec.driftDetection`
  to every HelmRelease — **rebase** the six Stage 3 `helmrelease.yaml` edits on
  that commit; re-run Step 0 of §3.2 so the baseline is taken after it),
  `sun-attended:2026-11-29` `redis-fleet-8.10.3`, `sun-attended:2026-12-06`
  `envoy-proxy-config-distroless-v1.39.4` (gateway restart gate; must be green).
  `nightly` is unattended and must never take a stage of this plan:
  `autonomy_override: human-gated`, and every rolling stage restarts something.
  No hard conflict forces the window to move.
- **Concurrent sessions.** Four commits touched this area on 2026-09-11
  (`43a3b3e4`, `0c77bbb0`, `5a7baeb5`, `4dfc3e32`); three more since (`67216b3b` external-secrets, `a03a8616` ARC OCIRepositories, `102ec800` plex GitRepository). Re-read
  `kubernetes/flux/meta/repositories/helm/` and the `k8s-gateway` app folder
  before Stage 1, and adjust rather than reverting anyone's work. Commit with
  `git commit --only <explicit paths>`; verify with `git show --stat HEAD`.
- **This plan merges no Renovate PR and changes no chart version.** If a
  component's `render.diff` is non-empty, that is a version change in disguise:
  stop, and let it be planned as one (`unpoller` is the known instance, §3.5).

## 7. Appendix — per-component source inventory (probed 2026-09-11)

Verdicts came from live registry `tags/list` + per-version manifest `HEAD` calls;
nothing is listed as present unless a call returned it. **Re-derive the digest at
execution time** — the digests are deliberately not recorded here, because a
stale digest in a plan is worse than no digest.

### Upstream-native OCI (13 repos) — first choice, no mirror needed

Re-probed 2026-11-03 (anonymous registry `HEAD` on the manifest of the version
each live HelmRelease pins). A "signed" column was **not** re-probed and is
carried from 2026-09-11 for orientation only; re-check at Stage 9. Versions
move before the window: `VER` is read from the live HelmRelease in §3.2.

| HelmRepository | OCI path | live pin — present in OCI? | signed (2026-09-11) | rolls? | stage |
|---|---|---|---|---|---|
| `authentik` | `ghcr.io/goauthentik/helm-charts/authentik` | 2026.8.3 yes (2026.8.5 also present; `authentik-2026.8.5` is windowed 11-21) | no | yes (label AND `checksum/secret`) | 5 |
| `cilium` | `quay.io/cilium/charts/cilium` | 1.20.4 yes | yes (referrers) | yes | 6 |
| `falcosecurity` | `ghcr.io/falcosecurity/charts/falco` | 9.2.2 yes | yes (bundle v0.3) | **yes (DaemonSet, checksum annotations)** | 3 |
| `gabe565` | `ghcr.io/gabe565/charts/paperless-ngx` | 0.24.1 yes | no | no | 3 |
| `grafana` | `ghcr.io/grafana-community/helm-charts/grafana` | 14.0.1 yes (`grafana-14.1.0` pending) | no | yes | 5 |
| `intel` | `ghcr.io/intel/helm-charts/intel-device-plugins-{operator,gpu,npu}` | 0.37.1 yes (all 3) | no | no | 3 |
| `jetstack` | `quay.io/jetstack/charts/cert-manager` | `v1.21.3` and `1.21.3` both yes | yes (legacy `.sig`) | yes | 6 |
| `mintplex-labs` | `ghcr.io/mintplex-labs/helm-charts/anythingllm` | 1.0.0 yes | no | yes | 5 |
| `nextcloud` | `ghcr.io/nextcloud/helm/nextcloud` | 9.4.1 yes | no | **no** (re-measured; was listed as rolling) | 5 |
| `node-feature-discovery` | `registry.k8s.io/nfd/charts/node-feature-discovery` | 0.20.1 yes | yes (legacy `.sig`) | **yes (worker DaemonSet + master Deployment)** | 3 |
| `open-webui` | `ghcr.io/open-webui/helm-charts/open-webui` | 17.0.0 yes | no | yes | 5 |
| `opentelemetry` | `ghcr.io/open-telemetry/opentelemetry-helm-charts/opentelemetry-kube-stack` | 0.26.1 yes (the live pin moved from 0.24.3 on 2026-11-03 via `5aa609d5`; presence of 0.26.1 confirmed by the Step 3 pull in the census run) | no | **no** (re-measured; was listed as rolling) | 5 |
| `unpoller` | `ghcr.io/unpoller/helm-chart/unpoller` | **2.4.0 ABSENT (404)**, 2.5.0 present | yes (legacy `.sig`) | yes | **8 — blocked** |

**Two traps in this table.** `grafana`: the obvious path
`ghcr.io/grafana/helm-charts/grafana` **exists but is stale** — 138 tags ending at
9.4.5/10.5.x, no 12.x or 13.x. Pinning it would silently move us three major
chart versions backwards. Use `grafana-community`, which matches the HTTP repo we
already use. `jetstack`: both `v1.21.1` and `1.21.1` resolve — pin the form the
HelmRelease already uses (`v1.21.3` today) so the render diff stays empty.

### `charts-mirror` only (5 repos remain in scope) — all cosign-signed (2026-09-11), pinned versions present 2026-11-03

`oci://ghcr.io/home-operations/charts-mirror/<chart>`: `descheduler` 0.37.0 ·
`external-dns` 1.23.0 · `headlamp` 0.46.0 · `metrics-server` 3.14.0 (stage 4) ·
`longhorn` 1.12.1 (stage 6) — each present at the live pin. (`csi-driver-smb` is
moot: stage 2 went to a commit-pinned GitRepository.)

**BLOCKED on operator decision D2 (§1.0):** docs/sops/flux-chart-source-pinning.md
§4.1 rung 4 says a third-party mirror is a different trust decision and never a
cleanup step of a plan. None of these five moves to charts-mirror until the
operator records "charts-mirror accepted for <chart>" in this file.

Two things to carry forward: the mirror **prunes a chart 6 months after upstream
ships OCI**, so these six need a recurring upstream re-check (fold it into the
sweep rather than remembering it). And `headlamp`'s apparent upstream OCI
(`ghcr.io/kubernetes-sigs/headlamp/charts`) is a **private** package —
anonymous pull denied, and the maintainers intend `registry.k8s.io` instead — so
charts-mirror is the correct source for it today, not the ghcr path.

### No OCI anywhere (10 repos remain after plex) — stage 7, PARKED, mirror decision required

`apache-superset` · `blakeblackshear` (frigate) · `dirsigler` (uptime-kuma) ·
`elastic` (eck-operator) · `influxdata` · `jameswynn` (homepage) · `jellyfin` ·
`penpot` · `rm3l` (adguard-home) · `sure`. (`plex` is DONE.)

`plex` WAS the priority of the eleven (DONE 102ec800, Shape D GitRepository); like `csi-driver-smb` it tracks a **mutable
git branch** (`raw.githubusercontent.com/plexinc/pms-docker/gh-pages`). `elastic`
is worth a note because it looks migratable and is not:
`docker.elastic.co/eck/eck-operator:3.5.0` is the **operator image**, not a chart
(it resolves as an OCI image index, whereas every real Helm chart probed returned
config mediaType `application/vnd.cncf.helm.config.v1+json`).

### Unreferenced (0 repos)

None remain. `external-secrets` — the one the operator had HELD — was deleted
on 2026-10-23 by `67216b3b` (F-fb2cc8a2: no consumer, no ExternalSecret CRDs).
Flagged for the operator in the re-plan report because this plan had recorded a
"do not delete" and another session did it; nothing broke (all Flux objects
Ready after).

Already deleted in `7c048735`: `backube` (its `volsync` chart *is* in
charts-mirror, if it is ever wanted again) · `democratic-csi` · `guerzon` ·
`piraeus` · `rook-ceph`.

### Stated as unverified

- **No signature was *validated*.** Only the presence of a signature artifact at
  the expected location was checked; no `cosign verify` ran (cosign is not
  installed locally).
- **Whether Flux 2.9.6 accepts the sigstore-bundle-v0.3 layout** — untested, and
  it gates 6 of the signed candidates. Hence the pilot in §3.7.
- **`registry.k8s.io` cannot be tag-enumerated anonymously** (`tags/list` returns
  an empty array for every path). NFD 0.19.0 was instead confirmed positively by
  `helm show chart … --version 0.19.0`.
- **The 11 "no OCI" verdicts rest on anonymous-pull 401s**, which cannot
  distinguish private-but-existing from absent — the `headlamp` case proves the
  failure mode. Each was corroborated by the project's release automation using
  `chart-releaser`, but treat them as unconfirmed-absent and re-probe before
  committing to a mirror.
- **`flux mirror` is v0.x** and not installed here; its behaviour is documented,
  not exercised.

## 8. Appendix B — Stage 3 tool scripts (each dry-run 2026-11-03; known-bad result stated)

Install once per window. `$T` is a fixed path (every agent Bash call is a new shell):

```bash
export T=/Users/mu/.claude/jobs/flux-oci/tools; mkdir -p "$T"
```

`rollpred.py` — the roll predictor (Step 4). Known-bad: falco prints two `WILL ROLL` lines; an empty render prints `ABORT: empty render` and exits 2; paperless-ngx / Intel print `ROLL-PREDICTION: none`. A tool that prints nothing at all is broken, not clean: the last line is mandatory.

**`$T/rollpred.py`**

```bash
cat > "$T/rollpred.py" <<'EOT'
import sys, yaml
WL = ("Deployment", "StatefulSet", "DaemonSet")
def load(p):
    out = {}
    for d in yaml.safe_load_all(open(p)):
        if d and "kind" in d:
            out[(d["kind"], d["metadata"].get("name"))] = d
    return out
def diff(a, b, path=""):
    if type(a) != type(b):
        yield path, a, b; return
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            yield from diff(a.get(k), b.get(k), path + "/" + str(k))
    elif isinstance(a, list):
        if len(a) != len(b):
            yield path, a, b; return
        for i, (x, y) in enumerate(zip(a, b)):
            yield from diff(x, y, path + "[%d]" % i)
    elif a != b:
        yield path, a, b
old, new = load(sys.argv[1]), load(sys.argv[2])
if not old or not new:
    print("ABORT: empty render"); sys.exit(2)
n = 0
for key in sorted(set(old) | set(new)):
    if key not in old or key not in new:
        print("OBJECT-SET-CHANGED", key); n += 1; continue
    if key[0] in WL:
        for p, x, y in diff(old[key]["spec"]["template"], new[key]["spec"]["template"]):
            print("WILL ROLL: %s/%s template%s: %s -> %s" % (key[0], key[1], p, str(x)[:60], str(y)[:60])); n += 1
    elif key[0] in ("Job", "CronJob"):
        t = lambda o: (o["spec"].get("jobTemplate") or {}).get("spec", o["spec"]).get("template")
        for p, x, y in diff(t(old[key]), t(new[key])):
            print("HOOK/JOB-TEMPLATE-CHANGED (no running pod is replaced): %s/%s template%s" % (key[0], key[1], p))
    elif key[0] not in ("ConfigMap", "Secret", "ServiceAccount", "Service", "ClusterRole", "ClusterRoleBinding", "Role", "RoleBinding") and "spec" in old[key]:
        # custom resource consumed by an operator: spec change could roll what the operator owns
        for p, x, y in diff(old[key].get("spec"), new[key].get("spec")):
            print("CR-SPEC-CHANGED: %s/%s spec%s" % (key[0], key[1], p)); n += 1
rolls = n
print("ROLL-PREDICTION: %s" % ("none" if n == 0 else "see lines above"))
sys.exit(0)
EOT
```

`migrate.py` — writes `ocirepository.yaml`, switches the HelmRelease to `chartRef`, adds the kustomization entry if a `kustomization.yaml` exists, and (6th argument) deletes the HelmRepository file and its line, **but refuses (and writes nothing) while any other HelmRelease in `kubernetes/apps/` still uses that repository**. Atomic: every assertion runs before the first write. Known-bad (run 2026-11-03): the gpu migration with `intel.yaml` as 6th argument while the operator and npu releases still use it prints `REFUSING to delete HelmRepository/intel: still used by [...]` and leaves the tree unchanged; an app dir with no `chart.spec` block raises `no spec.chart.spec block found`. The `chart.spec` replacement removes only the 6-space-indented lines under `spec:` and keeps any comment indented less than that (re-tested on all six releases 2026-11-03: falco's 4-line `timeout: 15m` comment survives; the first version's `\s*#.*` alternative ate it).

**`$T/migrate.py`**

```bash
cat > "$T/migrate.py" <<'EOT'
import os, re, sys
# usage: python3 migrate.py <appdir> <ocirepo-name> <oci-url-without-scheme> <tag> <digest> [<helmrepo-file-to-delete>]
appdir, name, url, tag, digest = sys.argv[1:6]
drop = sys.argv[6] if len(sys.argv) > 6 else None
assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest), "digest must be the manifest digest"
ocirepo_text = (f"""---
# yaml-language-server: $schema=https://raw.githubusercontent.com/fluxcd-community/flux2-schemas/main/ocirepository-source-v1.json
apiVersion: source.toolkit.fluxcd.io/v1
kind: OCIRepository
metadata:
  name: {name}
# Replaces the HTTP HelmRepository for this chart (chart index = one mutable third-party URL inside
# cluster-meta's wait gate; spec.verify exists only on OCIRepository). Plan:
# runbooks/maintenance/plans/flux-oci-chart-sources.md. THE DIGEST IS THE TRUST ANCHOR: change tag AND
# digest together, re-derived from the registry, never one alone.
spec:
  interval: 1h
  layerSelector:
    mediaType: application/vnd.cncf.helm.chart.content.v1.tar+gzip
    operation: copy
  ref:
    tag: "{tag}"
    digest: {digest}
  url: oci://{url}
""")
hr = os.path.join(appdir, "helmrelease.yaml")
t = open(hr).read()
new, n = re.subn(r"(?m)^  chart:\n    spec:\n(?:      .*\n)+",
                 f"  chartRef:\n    kind: OCIRepository\n    name: {name}\n", t, count=1)
assert n == 1, "no spec.chart.spec block found in " + hr
ks = os.path.join(appdir, "kustomization.yaml")
ks_new = None
if os.path.exists(ks):
    k = open(ks).read()
    ks_new, n = re.subn(r"(?m)^(  - )((?:\./)?)helmrelease\.yaml$", r"\1\2ocirepository.yaml\n\1\2helmrelease.yaml", k, count=1)
    assert n == 1, "no helmrelease.yaml entry in " + ks
else:
    print("NOTE: no kustomization.yaml in", appdir, "- Flux auto-includes ocirepository.yaml")
mk_new = None
if drop:
    import glob, yaml
    repo = os.path.splitext(os.path.basename(drop))[0]
    others = []
    for f in glob.glob("kubernetes/apps/**/*.yaml", recursive=True):
        if os.path.abspath(f) == os.path.abspath(hr):
            continue
        try:
            docs = list(yaml.safe_load_all(open(f)))
        except Exception:
            continue
        for d in docs:
            if isinstance(d, dict) and d.get("kind") == "HelmRelease":
                sr = (((d.get("spec") or {}).get("chart") or {}).get("spec") or {}).get("sourceRef") or {}
                if sr.get("kind") == "HelmRepository" and sr.get("name") == repo:
                    others.append(f)
    assert not others, "REFUSING to delete HelmRepository/%s: still used by %s" % (repo, others)
    mk = "kubernetes/flux/meta/repositories/helm/kustomization.yaml"
    k = open(mk).read()
    mk_new = re.sub(r"(?m)^  - (?:\./)?" + re.escape(os.path.basename(drop)) + r"\n", "", k)
    assert mk_new != k, "entry not found in " + mk
# nothing has been written yet: every assert above fires before the first write
open(os.path.join(appdir, "ocirepository.yaml"), "w").write(ocirepo_text)
open(hr, "w").write(new)
if ks_new: open(ks, "w").write(ks_new)
if drop:
    os.remove(drop); open(mk, "w").write(mk_new)
EOT
```

`srcrefs.py` — how many HelmReleases in the WORKING TREE still use a HelmRepository (the deletion gate, Step 5). Measured baseline: `intel` 3, `node-feature-discovery` 1, `gabe565` 1, `falcosecurity` 1; after the migrations 0.

**`$T/srcrefs.py`**

```bash
cat > "$T/srcrefs.py" <<'EOT'
import sys, glob, yaml
# usage: python3 srcrefs.py <HelmRepository name>  -> prints how many HelmReleases in the WORKING TREE still use it as chart.spec.sourceRef
repo = sys.argv[1]
n, files = 0, []
for f in glob.glob("kubernetes/apps/**/*.yaml", recursive=True):
    try:
        docs = list(yaml.safe_load_all(open(f)))
    except Exception:
        continue
    for d in docs:
        if isinstance(d, dict) and d.get("kind") == "HelmRelease":
            s = (((d.get("spec") or {}).get("chart") or {}).get("spec") or {}).get("sourceRef") or {}
            if s.get("kind") == "HelmRepository" and s.get("name") == repo:
                n += 1; files.append(f)
print(n, *files)
EOT
```

`nodesnap.sh` — NFD/Intel gate: 12 rows (3 nodes x 2 labels + 2 capacities). Exits 1 unless exactly 12 rows. Known-bad: a tampered baseline (`i915=5` -> `i915=0`) makes `diff` non-empty.

**`$T/nodesnap.sh`**

```bash
cat > "$T/nodesnap.sh" <<'EOT'
kubectl get node -o json | python3 -c "
import sys, json
rows = []
for n in json.load(sys.stdin)['items']:
    nm = n['metadata']['name']
    for k, v in n['metadata']['labels'].items():
        if k in ('intel.feature.node.kubernetes.io/gpu', 'intel.feature.node.kubernetes.io/npu'):
            rows.append(f'{nm} label {k}={v}')
    for k, v in n['status']['capacity'].items():
        if k in ('gpu.intel.com/i915', 'npu.intel.com/accel'):
            rows.append(f'{nm} capacity {k}={v}')
print('\n'.join(sorted(rows)))
if len(rows) != 12:
    print('SNAPSHOT-FAIL: expected 12 rows (3 nodes x 2 labels + 2 capacities), got', len(rows), file=sys.stderr); sys.exit(1)
"
EOT
```

`falco_sink.py` — reads Wazuh's `alerts.json` and requires a falco-decoded alert from ALL THREE agents after a cutoff. Measured 2026-11-03: falco emits continuously (about 2-3 alerts per node per minute, so no deliberate trigger is needed and none is allowed to substitute for the real stream). Known-bad: cutoff `2099-01-01T00:00:00` prints `FALCO-SINK-FAIL` and exits 1; cutoff 10 minutes ago printed `FALCO-SINK-OK` with 20/24/24 alerts per node.

**`$T/falco_sink.py`**

```bash
cat > "$T/falco_sink.py" <<'EOT'
import sys, json, datetime
# usage: kubectl exec ... tail -n N alerts.json | python3 falco_sink.py <cutoff-ISO-UTC e.g. 2026-11-03T01:00:00>
cut = datetime.datetime.fromisoformat(sys.argv[1]).replace(tzinfo=datetime.timezone.utc)
agents = {}
total = 0
for line in sys.stdin:
    try:
        d = json.loads(line)
    except ValueError:
        continue
    if not str(d.get("location", "")).endswith("/falco.log"):
        continue
    ts = datetime.datetime.strptime(d["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
    total += 1
    if ts >= cut:
        a = d.get("agent", {}).get("name", "?")
        agents[a] = agents.get(a, 0) + 1
print("falco alerts since", sys.argv[1], "per agent:", json.dumps(agents, sort_keys=True), "(falco alerts scanned:", total, ")")
if len(agents) < 3:
    print("FALCO-SINK-FAIL: fewer than 3 agents delivered a falco alert after the cutoff"); sys.exit(1)
print("FALCO-SINK-OK")
EOT
```

`collect.sh` is defined inline in §3.2 Step 1 (it must be re-created per component because it reads `$NS`, `$REL`, `$WL`).
