---
plan_id: helm-drift-detection
component: flux/helm-controller
pr: null                              # No Renovate PR exists or can exist: this is a
                                      # CONFIG change (a field on every HelmRelease),
                                      # not a version bump. Renovate has no opinion.
kind: config
current: "126 HelmReleases in 139 child Kustomizations, spec.driftDetection unset on all 126 (mode defaults to `disabled`: helm-controller v1.6.3 never compares the Helm storage manifest with the cluster). P0 EXECUTED 2026-09-26 (d17af8e0: the two SSA-rejected stored manifests fixed). P1 attempted 2026-09-26 (fbc220f7) and REVERTED (5bdd3164): its strategic-merge child patch dropped bare `key:` nulls from spec.values of 3 HelmReleases -> 3 unintended Helm upgrades. Re-measured 2026-09-28."
target: "spec.driftDetection.mode: enabled on every HelmRelease, with ignore rules derived from a measured >=7-day warn-mode inventory — delivered in FOUR windowed steps (P0 fix the two SSA-rejected charts -> P1 warn -> P2 ignores + retire the two known day-1 diffs -> P3 enabled), each its own window, each one commit, each independently revertible"
update_type: refactor
risk: medium                          # Two sources. (1) Phase 1 is NOT read-only for a
                                      # release whose stored manifest the API server
                                      # rejects on a server-side dry-run: helm-controller's
                                      # diff step errors and that HelmRelease sits at
                                      # Ready=False from P1 onward. The §2.1 gate exists
                                      # so that set is EMPTY before P1 (today it is
                                      # ai/anythingllm + media/jellyfin; P0 fixes both).
                                      # (2) Phase 3: the first reconcile in `enabled`
                                      # mode PATCHES every drifted object that is not
                                      # ignored, cluster-wide, in one 30-minute interval,
                                      # and a patch to a pod template (annotation, env,
                                      # replicas) or to an operator CR is a ROLLOUT —
                                      # measured today: the GpuDevicePlugin correction
                                      # rolls the intel-gpu-plugin DaemonSet on all 3
                                      # nodes. §2.3's empty-inventory gate is what keeps
                                      # that first reconcile a no-op; §3.2.0 retires the
                                      # two known day-1 diffs on OUR terms, in warn mode.
est_duration_min: 60                  # The LONGEST phase (P3): §2.3 gate ~10 + edit/commit/
                                      # propagate ~10 + the mandatory 30-min first-interval
                                      # watch + §4.3 positive control ~10. Per-phase figures
                                      # in §7 (P0 20 / P1 20 / P2 40 / P3 60). The frontmatter
                                      # number is what the OVER-TIME/TIGHT check consumes, so
                                      # it must be the worst case, not the average. The
                                      # >=7-day soak between P1 and P2 is calendar time.
needs_reboot: false
touches:
  namespaces:
    - flux-system                     # the file edited in P1/P2/P3 lives here (cluster-apps Kustomization)
    - kube-system                     # P2: hand re-apply of GpuDevicePlugin/intel-gpu-plugin -> DaemonSet roll (3 nodes)
    - monitoring                      # P2: hand re-apply of Prometheus/kube-prometheus-stack (benign, no rollout)
    - "ALL (every namespace that holds a HelmRelease — SPEC ONLY: a new field on 126 HelmReleases; no workload change in P1/P2/P3 given clean §2.1 / §3.0.0-step-6 / §2.3 gates)"
  resources:
    - kubernetes/flux/cluster/ks.yaml                    # THE edit, phases 1-3
    - kustomization/flux-system/cluster-apps             # gains one spec.patches entry
    - "139 child Kustomizations (each gains one spec.patches entry, rendered by cluster-apps)"
    - "126 HelmReleases (each gains spec.driftDetection; no Helm upgrade — gated pre-commit by §3.0.0 step 6, verified post-apply by step 8)"
    # P0 resources (anythingllm, jellyfin) removed 2026-09-28: P0 EXECUTED 2026-09-26 (d17af8e0).
    - "the 7 HelmReleases whose spec.values carry nulls (databases/influxdb, default/homepage, network/adguard-home, kube-system/authentik, monitoring/uptime-kuma, monitoring/prometheus-blackbox-exporter, media/jellyfin) — spec-only like the rest; §1.5 proves their values are untouched by the JSON6902 patch, and §3.0.0 steps 6/8 gate it. adguard-home is the LAN DNS (192.168.55.5): the one casualty of 2026-09-26 with a household-wide blast radius."
    - gpudeviceplugin/intel-gpu-plugin                  # P2 §3.2.0 hand re-apply (warn mode)
    - daemonset/kube-system/intel-gpu-plugin-intel-gpu-plugin   # rolled by that re-apply
    - prometheus/monitoring/kube-prometheus-stack       # P2 §3.2.0 hand re-apply (benign add)
    - helmrelease/kube-system/reloader                  # P2 ONLY, and only if the
                                                        # inventory shows env-var drift (§3.2 C)
  shared:
    - "intel-gpu-plugin (P2 §3.2.0 only): the DaemonSet roll re-registers gpu.intel.com/i915 on each node; the 7 running GPU claimants (frigate, scrypted, immich-server, immich-machine-learning, jellyfin, makemkv, plex) keep running, NEW GPU pods cannot schedule for ~1 min per node"
    # DELIBERATELY nothing else, and re-check at Phase 3: in P1/P2 the controller only
    # READS (server-side dry-run). P3 is gated on an EMPTY inventory (§2.3), so its
    # first reconcile corrects nothing. What P3 changes is platform BEHAVIOUR from
    # then on (manual edits to Helm-managed objects are reverted within one HR
    # interval) — that is an interference note (§6), not a perturbation in the
    # window. If the P3 pre-check is NOT clean, do not run P3; the leftover drift
    # names which shared surface it would touch.
depends_on: []
conflicts_with:
  # RESOLVED 2026-09-27: talos-1.14.1 EXECUTED (cad2bd3f; 3-node roll in sun-attended:2026-09-27) and retired together with the superseded talos-1.14.0 -- refs removed per the dead-ref convention.
  - grafana-chart-13.2.3              # (status superseded 2026-09-14; kept until that file is
                                      # retired — ref still resolves.) §6.4: pure attribution — a Helm upgrade in the same
                                      # window as P3 gives every grafana rollout two causes
  # - affine-redis-8.10.2 (RESOLVED 2026-09-26: executed + retired in now:2026-09-26; ref removed) # §4.1 revision-identity diff: that plan upgrades
                                      # office/affine-redis (rev 14 -> 15). Reciprocal of
                                      # its own declaration; added 2026-09-26 (plan review).
  - flux-reconciler-impersonation     # Reciprocal of its own declaration (it swaps the identity
                                      # helm-controller applies under; drift correction under
                                      # impersonation is untested). Added 2026-09-26 (review).
                                      # intel-device-plugin-0.37.0 and falco-9.2.0 also name this
                                      # plan but are NOT listed: both run/ran in the 2026-09-26
                                      # main NOW run and are retired on execution, and a ref to a
                                      # deleted plan is a --validate DEAD-REF.
  # Added 2026-09-28 (P1 re-plan). Two reasons, both about the P1 gates' validity:
  - flux-fleet-0.60.0                 # Flux operator/instance bump: a kustomize-controller or
                                      # flux CLI change can change patch/null semantics, which is
                                      # exactly what §3.0.0 steps 3/6 measure. Never the same
                                      # window; after it lands, re-run the gates (premises pin
                                      # kustomize-controller v1.9 / distribution 2.9). Reciprocal.
  - flux-oci-chart-sources            # rewrites chart sources on HelmReleases incl. kube-system/
                                      # authentik (a null-bearing HR) — a same-window HR spec
                                      # change invalidates values-gate snapshot B.
  - jellyfin-12.1                     # edits media/jellyfin HR values (null-bearing); same reason.
  - uptime-kuma-2.5.5-slim-rootless   # edits monitoring/uptime-kuma HR values (null-bearing). Reciprocal.
  - chart-patches-coredns-reloader-blackbox   # edits prometheus-blackbox-exporter HR (null-bearing). Reciprocal.
  # Reciprocals of plans that already name this one (a HelmRelease change in the P1 run
  # breaks rev-gate/values-gate attribution, and P1 must be the day's LAST HR change):
  - app-template-5.2.1
  - librechat-2.0.14
  - mariadb-chart-27.3.0
  - penpot-chart-1.10.0
  - redis-fleet-8.10.2
  # traccar-6.16.0 REMOVED 2026-09-29: executed green in nightly:2026-09-29 (3a943035), plan retired (1a40b257)
  - otel-operator-0.23.0              # reciprocal (it names this plan); HR bump -> attribution
security_ref: null
capability_change: false              # no user-visible behaviour changes; Flux reconciles the
                                      # same manifests, it merely starts to notice edits
rollback_class: git-revert            # every phase is ONE commit; the revert restores the
                                      # previous state on the next reconcile (P2's hand
                                      # re-apply is a no-op to revert — see §5)
autonomy_override: human-gated        # RESTRICTS only. P0 executed. P1 is a dedicated
                                      # operator-GO run since the 2026-09-26 revert (§7); P2
                                      # (DaemonSet roll) and P3 are attended. A multi-phase plan in one
                                      # file cannot be one AUTO-NIGHT unit, so the scheduler
                                      # must not treat it as one.
finding_refs: []
review: ready-for-go@2026-09-28   # plan-reviewer: needs-fix (render-gate false-FAIL on self-growing
                      # ConfigMap cluster-settings + 9 non-blocking) -> fixed -> READY-FOR-GO same day.
status: vetted   # 2026-09-28 P1 RE-PLANNED (§1.5, §3.0.0): child patch is now JSON6902 op:add (proven to keep all
                      # 18 null leaves on the 7 null-bearing HRs), with pre-commit parent/render gates and a
                      # post-apply values gate, each demonstrated to FAIL on the fbc220f7 shape. Vetted for P1
                      # ONLY, as a dedicated operator-GO NOW run; risk medium -> NOT SD-10 preapproved; no GO recorded.
                      # HISTORY — 2026-09-26 NOW run: P0 EXECUTED GREEN (d17af8e0: anythingllm + jellyfin stored manifests pass
                      # SSA, no pod-template change). P1 REVERTED (fbc220f7 -> 5bdd3164): the rev-gate caught 3
                      # unexplained Helm upgrades (databases/influxdb, default/homepage, network/adguard-home)
                      # because the parent-ks spec.patches pass drops explicit `key: null` entries from
                      # spec.values, so chart defaults return. P1 is NOT spec-only for null-bearing values
                      # (7 HRs carry nulls). [Superseded 2026-09-28: the chosen fix is the JSON6902 child
                      # patch (§1.5); the nulls stay as they are.]
window: "sat-attended:2026-11-07"   # SCHEDULED 2026-09-28 by maintenance-window-agent (operator: "schedule everything that needs to be scheduled"); GO needed: P1 only, as the LAST/only plan of an attended window (plan section 7)
                                      # set status back to `vetted`; after P1 and after P2 set
                                      # `awaiting-soak` (run-now.py refuses it, so no NOW run
                                      # can collapse a soak; flip to `vetted` when it ends)
                                      # AND refresh `generated:` to the edit date in that
                                      # same commit — maintenance-plan.py flags a plan as
                                      # `unused > stale_after_days` (14) from `generated`,
                                      # and this plan is legitimately mid-soak for weeks.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/flux-upgrade.md
  - docs/sops/maintenance-windows.md
  - docs/sops/longhorn-rwo-multi-attach.md
premises:
  - id: helm-controller-is-v1.6.x
    why: >-
      Drift detection is a GA field on HelmRelease v2 since helm-controller 1.0 and
      is NOT gated by a controller flag on this version (live args carry only
      ObjectLevelWorkloadIdentity=false). A different major would need the
      feature-gate story re-read before any of §3 applies.
    run: kubectl get deploy -n flux-system helm-controller -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "ghcr.io/fluxcd/helm-controller:v1.6."
  - id: parent-patch-wiring-is-live
    why: >-
      Mechanism A (§1.3) rides on the EXISTING parent->child patch in the
      cluster-apps Kustomization. If that patch is gone or reshaped, the render
      proof in §1.4 no longer describes this cluster.
    run: kubectl get kustomization -n flux-system cluster-apps -o jsonpath='{.spec.patches[*].target.labelSelector}'
    expect_contains: "substitution.flux.home.arpa/disabled notin (true)"
  - id: child-kustomizations-receive-parent-patches
    why: >-
      grafana's ks.yaml declares NO decryption block; the one on the live object
      arrives only through the parent patch. Its presence proves the nested-patch
      path (parent patches child, child patches its own render) is live, which is
      the whole basis for touching one file instead of 124.
    run: kubectl get kustomization -n monitoring grafana -o jsonpath='{.spec.decryption.provider}'
    expect_exact: "sops"
  - id: no-helmrelease-is-enabled-yet
    why: >-
      Phases 1 and 2 assume nothing is correcting drift today. A HelmRelease
      already in `enabled` mode means someone moved ahead of this plan; the
      inventory and the Phase 3 gate would be measuring a mixed cluster.
      (Holds until Phase 3 executes; the plan is then retired.)
    run: kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.driftDetection.mode}{"\n"}{end}' | grep -c enabled
    expect_exact: "0"
  - id: all-helmreleases-ready
    why: >-
      Do not add a new reconcile phase on top of a release that is already
      failing — its drift condition would be noise, and a Phase 3 correction on
      a broken release has two candidate causes. Exactly one line, and it must
      be the True line. THIS PREMISE IS RE-CHECKED AFTER P1 PROPAGATES, not only
      before (§4.1 assertion 0): a release whose stored manifest the API server
      rejects on the server-side dry-run fails its reconcile the moment `warn`
      lands, so "all Ready before" does not imply "all Ready after".
    run: kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' | sort | uniq -c
    expect_matches: '^\s*[0-9]+ True\s*$'
  - id: helmrelease-count-in-expected-range
    why: >-
      The 124 figure in this plan is a snapshot. A count far outside it means
      the inventory in §3.1 must be re-taken and the ignore rules re-derived —
      the plan is not wrong, its evidence is stale.
    run: kubectl get helmrelease -A --no-headers | wc -l
    expect_matches: '^\s*1[0-9]{2}\s*$'
  - id: no-hpa-exists
    why: >-
      §3.2 deliberately does NOT ignore /spec/replicas (a manual scale is drift
      we WANT corrected). That decision is only safe while no
      HorizontalPodAutoscaler manages a Helm-rendered Deployment.
    run: kubectl get hpa -A --no-headers | wc -l
    expect_exact: "0"
  - id: no-flux-alert-objects
    why: >-
      Phase 1 emits a Warning Event (reason DriftDetected) per drifted
      HelmRelease per interval. With zero notification-controller Alert objects
      those events reach no pager, which is what makes Phase 1 nightly-safe.
      One Alert with eventSeverity info or a HelmRelease source changes that.
    run: kubectl get alerts.notification.toolkit.fluxcd.io -A --no-headers | wc -l
    expect_exact: "0"
  - id: flux-distribution-is-2.9
    why: >-
      §3.0.0's pre-commit gates run the LOCAL `flux build` as a stand-in for
      kustomize-controller's kustomize. That stand-in reproduced the live
      2026-09-26 failure exactly (the same 3 HelmReleases, the same 11 paths),
      measured with CLI v2.9.0 against distribution v2.9.3. A different
      distribution minor ships a different kustomize and the proof no longer
      transfers. (The CLI side cannot be a premise — plan-premises.py refuses
      `flux version` — so §3.0.0 step 1 asserts `flux version --client` prints
      `flux: v2.9.` by hand.)
    run: kubectl get fluxinstance -n flux-system flux -o jsonpath='{.spec.distribution.version}'
    expect_contains: "v2.9."
  - id: kustomize-controller-is-v1.9
    why: >-
      The controller side of the same claim: kustomize-controller v1.9.x is the
      applier whose SMP behaviour dropped the bare-key nulls on 2026-09-26. A
      bump (flux-fleet-0.60.0 or a distribution change) needs the §3.0.0 step-3
      demonstration re-read before P1.
    run: kubectl get deploy -n flux-system kustomize-controller -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_contains: "ghcr.io/fluxcd/kustomize-controller:v1.9."
generated: "2026-09-28"
---

# Helm drift detection: fix the SSA-rejected charts -> warn -> ignore rules -> enabled, cluster-wide

## 0) Decision memo — "no drift" today means "nothing is looking"

Every one of the 126 HelmReleases (124 when first measured 2026-09-14) in this cluster runs with
`spec.driftDetection` unset, and the CRD is explicit about what that means:
*"If not explicitly set, it defaults to DiftModeDisabled"* — helm-controller
never compares what Helm last applied with what is in the cluster. The
GitOps guarantee this repo relies on — *the cluster is what git says* — is
therefore only true for objects Flux's kustomize-controller applies directly.
For the 124 Helm-managed releases (79 of them `app-template`, i.e. most of the
apps), the guarantee holds only at the moment of a `helm upgrade`; between
upgrades any `kubectl edit`, `kubectl scale`, a stray `kubectl apply`, an
operator's hot-fix, or another controller rewriting a field is invisible
until the next chart or values change silently overwrites it — or does not,
because SSA keeps the foreign field.

Three things already recorded in this repo or measured for this plan show the
cost:

- `bitnamilegacy-exit-nextcloud-db` §3 and `superset-pg-cutover` §3 both
  carry the boxed warning *"kubectl scale --replicas=0 DOES NOT HOLD. Flux
  drift-corrects it back."* That sentence is only half true today: a Helm
  UPGRADE (the replatform commit) resets replicas; plain drift is NOT
  corrected, because nothing is looking. Two plans reasoned about a control
  that does not exist.
- The `sop-reload-test` annotation sits on all 28 kube-prometheus-stack
  dashboard ConfigMaps in `monitoring` (measured 2026-09-14, absent from the
  Helm manifest). It is a leftover from a test, harmless, and nobody knew it
  was there — the shape of every unknown edit.
- **Two stored release manifests are not valid Kubernetes objects** (§1.2,
  §2.1): `ai/anythingllm` renders `strategy` under the POD spec and
  `media/jellyfin` renders `privileged`/`capabilities`/`allowPrivilegeEscalation`
  under the POD security context. Helm's three-way merge never noticed
  because it only sends the fields that changed between two revisions; a
  server-side apply rejects both with `field not declared in schema`. Nobody
  knew, for the same reason: nothing was looking.

The fix is one Flux field, but the field has a dangerous setting (`enabled`
patches objects) and a safe one (`warn` only reports) — and even the safe one
is only safe for a release whose manifest the API server accepts. The plan is
to first make every stored manifest SSA-clean (P0), then spend seven days in
`warn`, measure what actually drifts, encode the legitimate mutators as ignore
rules and retire the known day-1 diffs on our own terms (P2), and only then
turn correction on — so that the first correcting reconcile has, by
construction, nothing to correct.

## 1) Summary & why held

### 1.1 What changes, and what does not

- **Changed, P0:** two `helmrelease.yaml` files are corrected so that their
  rendered manifests pass a server-side apply (§3.0). Each is a values /
  postRenderer change, therefore a **Helm upgrade and a `Recreate` restart of
  that app** (anythingllm, jellyfin). This is the only phase that touches a
  workload by design.
- **Changed, P1-P3:** `kubernetes/flux/cluster/ks.yaml` gains ONE more entry
  in the `cluster-apps` Kustomization's `spec.patches`. It patches every child
  Kustomization to carry a `spec.patches` entry of its own, which stamps
  `spec.driftDetection` onto every HelmRelease that child renders. Three
  commits over three windows: mode `warn` (P1), add `ignore` rules (P2), mode
  `enabled` (P3).
- **Not changed by P1-P3:** no chart version, no values, no image, no
  workload. A `spec.driftDetection` change is not part of the Helm release
  (chart + values); helm-controller reconciles the HelmRelease's new
  generation without a `helm upgrade`. **That is a claim, and §4.1 asserts
  it** (Helm revision numbers identical across all 126 releases
  before/after).
- **Phase 1 is NOT guaranteed read-only.** `warn` never *writes* (§1.2), but
  the comparison is a server-side dry-run apply of the stored manifest, and a
  manifest the API server rejects makes that reconcile FAIL: the HelmRelease
  goes `Ready=False` (reason `StateError`-class, the diff step errors before
  any release action) and stays there every interval until the manifest is
  fixed. Today that set is exactly `ai/anythingllm` and `media/jellyfin`
  (measured in §2.1). P0 fixes them; the §2.1 gate refuses P1 while the set is
  non-empty; §4.1 re-asserts `126 Ready=True` AFTER propagation.
- **P1 is NOT spec-only if delivered as a strategic-merge patch** (learned
  2026-09-26, root-caused 2026-09-28, §1.5): kustomize's SMP drops bare
  `key:` (implicit-null) entries from the HelmRelease it patches, so a
  chart-default deletion in `spec.values` disappears, the values digest
  changes, and helm-controller runs a `helm upgrade`. P1 therefore delivers the
  field with a JSON6902 `op: add`, which touches nothing else — proven over
  every child and every HelmRelease before commit (§3.0.0 step 6).
- **Why held / why a plan:** there is no version to bump and no auto-updater
  lane for "add a field to 124 HelmReleases", and the end state changes
  platform behaviour cluster-wide (manual edits get reverted). Phase 3 is
  operator-present by design.

### 1.2 How the detection actually works (read from the code, then measured)

helm-controller v1.6.3 (`internal/action/diff.go`) builds a
`jsondiff` diff per rendered object; `fluxcd/pkg/ssa/jsondiff/unstructured.go`
performs the comparison as a **server-side dry-run apply** with
`client.DryRunAll`, `client.ForceOwnership` and
`client.FieldOwner("helm-controller")`, then compares the dry-run result with
the live object after `removeMetadataAndStatus()` (labels and annotations are
compared separately, add/replace only). §2.1 emulates exactly that call for
every object of every release, read-only. Measured 2026-09-14 across all 124
releases (~600 objects):

| Live edit | In the Helm manifest? | Drift? | Measured 2026-09-14 |
|---|---|---|---|
| `kubectl scale` on an app-template Deployment (`replicas: 1` rendered) | yes | **YES** | forced apply sets it back; live differs (positive control §4.1) |
| `kubectl rollout restart` -> `kubectl.kubernetes.io/restartedAt` on the pod template | no | **no** | 0 rows — an annotation owned by another field manager survives the apply |
| Reloader `STAKATER_*` env var (env-vars strategy, 10 Helm-managed Deployments today) | no | **no** | 0 rows — env is a map-list keyed by `name`; a foreign entry is kept |
| cainjector / patch-job `caBundle` on cert-manager, kube-prometheus-stack, eck, intel webhooks | no | **no** | 0 rows — field absent from manifest is retained |
| otel-operator webhook `caBundle` (chart generates the cert) | yes | **no today** | 0 rows (manifest == live); YES after any hand rotation |
| extra annotation on a dashboard ConfigMap (`sop-reload-test`) | no | **no** | 0 rows |
| `kubectl edit` of an image / env value / resource limit that the chart sets | yes | **YES** | this is the drift the plan exists for |
| **`GpuDevicePlugin/intel-gpu-plugin` `spec.monitoringMode: single`** | **yes** (stored manifest line 16) | **YES — guaranteed** | live object lacks the field: it was pruned by the older CRD when chart 0.36.0 first rendered it (rev 4, May), and Helm's 3-way merge never re-sent it (rev 5 old==new). helm-controller's managedFields do not own it. |
| **`Prometheus/kube-prometheus-stack` `spec.paused: false`** | **yes** (manifest, twice) | **YES — guaranteed** | same mechanism: unchanged between revisions, so never re-sent; live lacks it. |
| `ai/anythingllm` Deployment `spec.template.spec.strategy` | yes (chart bug: `.Values.strategy` rendered under the pod spec) | **REJECTED** | `field not declared in schema` — the release cannot be diffed at all |
| `media/jellyfin` Deployment `spec.template.spec.securityContext.capabilities` (+ `privileged`, `allowPrivilegeEscalation`) | yes (values put container-only keys in `podSecurityContext`) | **REJECTED** | same error class |

**Expected day-1 inventory** (what §3.1.3 will show once P1 has propagated,
if the cluster is as measured):

1. `kube-system/intel-device-plugin-gpu` — `Drifted=True`, one object,
   `GpuDevicePlugin/intel-gpu-plugin`, `/spec/monitoringMode` added (`single`).
   **Correction is a DaemonSet roll on all 3 nodes:** the operator's
   `getPodArgs()` (v0.36.0, `pkg/controllers/gpu/controller.go`) appends
   `-monitoring-mode=<value>` only when the field is non-empty, and
   `UpdateDaemonSet()` compares the joined arg strings — the live DaemonSet
   args carry no `-monitoring-mode` today, so the string differs and the
   template is rewritten. Pre-decided in §3.2.0.
2. `monitoring/kube-prometheus-stack` — `Drifted=True`, one object,
   `Prometheus/kube-prometheus-stack`, `/spec/paused` added (`false`). Benign:
   `false` and unset are the same to prometheus-operator; the StatefulSet
   generation does not move. Pre-decided in §3.2.0.
3. Nothing else. Anything beyond these two lines on day 1 is either a change
   since 2026-09-14 (re-run §2.1 and compare) or a case the emulation missed;
   read its message before Phase 2.

Events and conditions (verified in `api/v2/condition_types.go` and
`internal/reconcile/atomic_release.go`, `correct_cluster_drift.go`):

- Warning Event, reason **`DriftDetected`**, in BOTH `warn` and `enabled`.
- Condition **`Drifted`** on the HelmRelease: `True/DriftDetected` when drift
  exists, `False/NoDriftDetected` when the comparison ran and found nothing.
  A HelmRelease with **no** `Drifted` condition is one where detection never
  ran — this is the §4.1 contents assertion.
- Correction (only `enabled`): Normal Event **`DriftCorrected`**, Warning Event
  **`DriftCorrectionFailed`**. The correcting code path is
  `NewCorrectClusterDrift(...)` and it is instantiated **only** when
  `GetMode() == DriftDetectionEnabled`; in `warn` the reconciler returns
  `nil, nil` after recording the event. **`warn` never corrects** — that is
  a code-path fact, not a documentation promise. (A correction does not flip
  `Drifted` back by itself; the next reconcile re-diffs and marks
  `NoDriftDetected`. §4.3 therefore asserts the VALUE, not the condition.)
- The full JSON-patch summary is logged only at `--log-level=debug`;
  helm-controller runs `info`. §3.1.4 shows how to read the exact diff the
  controller reads, without changing the controller.

### 1.3 Mechanism: A, B or C — A, and it is already the house pattern

| Option | Diff size | Provably applied? | Verdict |
|---|---|---|---|
| **A** — one extra `spec.patches` entry on the parent `cluster-apps` Kustomization that patches every child Kustomization to carry a HelmRelease patch | **1 file, ~25 lines**, 3 commits total | yes — §1.4 renders parent AND child | **chosen** |
| B — a `patches:` block in each of the 123 child `ks.yaml` files | 123 files x 3 phases | yes, but 369 hunks to review and one missed file is silent | rejected |
| C — edit all 124 `helmrelease.yaml` | 124 files x 3 phases | yes | rejected; also loses the single revert |

Why A is not exotic here: the parent already does exactly this for
`decryption` and `postBuild.substituteFrom` — every one of the 136 live child
Kustomizations carries a decryption block that appears in no `ks.yaml`. The
new entry is a sibling of that patch, with its own opt-out label so a child
can be excluded without touching the substitution behaviour.

**Three properties of A that the executor must know:**

1. **The nested patch REPLACES, it does not merge.** Kustomize has no merge
   key for the HelmRelease CRD's `ignore` list, so a HelmRelease that declares
   its own `spec.driftDetection` gets it overwritten by the injected patch
   (verified 2026-09-14 with a scratch `kustomize build`: an HR carrying
   `mode: enabled` + a caBundle ignore rule rendered with `mode: warn` and
   ONLY the injected rule). A per-app exception is therefore expressed by
   labelling the app's **Kustomization** (`ks.yaml`) with
   `drift-detection.flux.home.arpa/disabled: "true"` — the parent then skips
   that child, and the app's `helmrelease.yaml` owns the field entirely.
   Object-level exceptions inside a release use the upstream annotation/label
   `helm.toolkit.fluxcd.io/driftDetection: disabled` (via the chart's values
   or a `postRenderers` patch on that HR).
2. **The same replace semantics apply to the child's `spec.patches` list**:
   a child `ks.yaml` that declares its own `spec.patches` would have that list
   REPLACED by the injected one. Zero of the 134 children declare any today
   (verified 2026-09-14); a future `ks.yaml` that needs its own patches must
   also carry the opt-out label above, or lose them silently.
3. **Propagation is three hops and takes up to ~12 minutes unaided:**
   `flux-system` Kustomization (interval 10m) applies the parent edit ->
   `cluster-apps` reconciles on its spec change and rewrites the 134 children
   -> each child reconciles on ITS spec change and rewrites its HelmRelease
   -> helm-controller reconciles each HelmRelease's new generation. No manual
   reconcile is required. To compress the wait inside a window,
   `flux reconcile kustomization flux-system --with-source` is the one
   `docs/sops/flux-upgrade.md`-sanctioned nudge; everything downstream is
   spec-change-triggered.
4. **The CHILD patch must be a JSON6902 `op: add`, never a strategic-merge
   patch** (§1.5). The PARENT patch (Kustomization -> child Kustomization)
   stays strategic-merge, like the existing decryption/substitution patch it
   sits next to: §3.0.0 step 6's parent-gate proves it changes nothing in any
   child spec except `/spec/patches`. P2 and P3 edit only the `value:` of the
   same op — the form never changes back.

### 1.4 Proof of render (2026-09-14, read-only, `flux build`)

Parent, with the proposed patch added to a scratch copy of
`kubernetes/flux/cluster/ks.yaml`:

```
flux build kustomization cluster-apps --path ./kubernetes/apps \
  --kustomization-file <scratch>/ks-cluster-apps.yaml
# -> 206 documents; child Kustomizations rendered: 134, with driftDetection patch: 134
```

Child, feeding the rendered `grafana` Kustomization (namespace `monitoring`)
back in — the scratch object is passed with `--kustomization-file`, the CLI
still resolves `substituteFrom` against the live cluster, and SOPS is not
needed because the encrypted Secret is passed through untouched:

```
flux build kustomization grafana -n monitoring \
  --path ./kubernetes/apps/monitoring/grafana/app \
  --kustomization-file <scratch>/grafana-ks-rendered.yaml
# -> HelmRelease monitoring/grafana driftDetection= {'mode': 'warn'} chart 13.2.1
#    kinds: ['Secret', 'HelmRelease', 'HTTPRoute']   unsubstituted ${...}: 0
```

Both `flux build` calls succeeded without `--dry-run`; the postBuild
substitutions resolved from the live `cluster-settings` / `cluster-secrets`.
(The first attempt failed with `kustomizations "grafana" not found` — the CLI
defaults to `-n flux-system`; pass the child's real namespace.) A second,
differently-shaped child (`kube-system/reloader`, chartRef/OCI) renders the
same field.

The exact patch text is in §3.1.1. Rendered form on a child (what
`kubectl get kustomization -n monitoring grafana -o yaml` will show after P1):

```yaml
spec:
  patches:
  - patch: |-
      - op: add
        path: /spec/driftDetection
        value:
          mode: warn
    target:
      group: helm.toolkit.fluxcd.io
      kind: HelmRelease
```

(Corrected 2026-09-28: the 2026-09-14 proof above used the strategic-merge
child form that failed on 2026-09-26 — §1.5. The render proof for the JSON6902
form is §1.5's gate output.)

### 1.5 The 2026-09-26 P1 failure, root-caused (2026-09-28, read-only)

**Inventory — every HelmRelease in git with a null in `spec`** (PyYAML over all
`kubernetes/**/*.yaml`, 127 HelmRelease documents; `key:`, `key: null` and
`key: ~` all load as None). Seven HelmReleases, 18 null leaves, all under
`spec.values`, all deliberate deletions of a chart default (Helm treats a
user-supplied null as "remove this default key"). `helm get values` shows the
same 18 nulls stored in the live releases, so each is part of the values digest
helm-controller compares — removing any one is a Helm upgrade, whatever it
renders to. Preservation is therefore required for all 18; none is safe to drop.

| HelmRelease | null leaves (paths under `spec.values`) | YAML form in git | SMP child patch (render) | 2026-09-26 live |
|---|---|---|---|---|
| databases/influxdb | `backup/resources/requests`, `backup/persistence/annotations`, `backupRetention/resources/requests`, `backupRetention/startingDeadlineSeconds` | bare `key:` | **all 4 dropped** | **upgraded** rev 11, reverted rev 12 |
| default/homepage | `config/docker`, `config/settings` | bare `key:` | **both dropped** | **upgraded** rev 30, reverted rev 31 |
| network/adguard-home | `services/dns/externalTrafficPolicy`, `.../tcp/nodePort`, `.../udp/nodePort`, `.../ipFamilyPolicy`, `.../ipFamilies` | bare `key:` | **all 5 dropped** | **upgraded** rev 22, reverted rev 23 |
| kube-system/authentik | `worker/livenessProbe`, `worker/readinessProbe`, `worker/startupProbe` | `key: null` | kept | not upgraded (rev 50 unchanged) |
| monitoring/uptime-kuma | `serviceMonitor/scheme`, `serviceMonitor/namespace` | `key: ~` | kept | not upgraded (rev 18) |
| monitoring/prometheus-blackbox-exporter | `config/modules/http_2xx` | `key: null` | kept | not upgraded (rev 3) |
| media/jellyfin | `readinessProbe/httpGet` | `key: null` | kept | not upgraded (rev 37 = P0) |

**The mechanism, measured:** the three casualties are exactly the three files
whose nulls are written as a bare `key:` with no value; the four whose nulls
are an explicit `null`/`~` survived. `flux build` of each child with the
2026-09-26 SMP child patch reproduces the live outcome row for row (11 paths
dropped on 3 HRs, 7 kept on 4), and the same build with a JSON6902
`- op: add / path: /spec/driftDetection / value: {mode: warn}` keeps all 18.
**Why the field alone is not an upgrade — primary evidence is the code:**
helm-controller v1.6.3 `internal/reconcile/state.go` `DetermineReleaseState`
(~lines 138-172) returns out-of-sync only for a chart change, a values
(config) digest change, or a postRenderers/commonMetadata digest change;
`driftDetection` feeds only the diff branch. Live corroboration (not proof —
P1 was live only ~3.5 min, 14:28:57-14:32:11 UTC, and it is not established
that every HR reconciled in that time): in the 14:28-14:45 UTC window the only
revisions besides P0 (14:26) and flux-instance rev 6 (14:26:17, before the P1
commit) are the three casualties, twice each; 106 of 126 HRs show a
kustomize-controller write at 14:33-14:34 (the revert stripping the field), so
they did carry it without being upgraded.

**Why not "just write `null` in the three files"?** It would make the SMP
survive today (explicit null is kept), but it is a rule every future
`helmrelease.yaml` author must remember, with the failure mode "silent Helm
upgrade of an unrelated app". The JSON6902 form removes the class: it cannot
touch a field it does not name. (Normalising the three files is still a
reasonable hygiene follow-up; it is NOT a P1 precondition.)

**Whole-tree proof, 2026-09-28** (tools in §3.0.0 step 2):

```
render-gate.py --patch smp       -> FAIL databases/influxdb, default/homepage, network/adguard-home
                                    children=139 rendered_helmreleases=126 live_helmreleases=126 non_pass=3   rc=1
render-gate.py --patch json6902  -> children=139 rendered_helmreleases=126 live_helmreleases=126 non_pass=0
                                    RENDER-GATE PASS                                                        rc=0
render-gate.py --patch json6902 --value '{"mode":"warn","ignore":[{"paths":[".../kubectl.kubernetes.io~1restartedAt"],"target":{"kind":"Deployment"}}]}'
                                 -> RENDER-GATE PASS (the P2 shape — nested lists in the value are fine)
parent-gate.py <HEAD ks.yaml> <p1-edit.py result>     -> objects=211 child_kustomizations=139 patched=139 fails=0  PASS rc=0
parent-gate.py <HEAD ks.yaml> <fbc220f7 ks.yaml>      -> patched=0 fails=139  PARENT-GATE FAIL rc=1
parent-gate.py <HEAD ks.yaml> <p1 result> '{"mode":"enabled"}'  -> PARENT-GATE FAIL rc=1 (wrong value is caught)
values-gate.py snapshot T; compare T                   -> PASS, 126 HelmReleases, 18 null leaves
values-gate.py compare T (snapshot doctored: influxdb backup/resources/requests deleted) -> FAIL (added) rc=1
```

The P1 edit applied to a scratch copy of `kubernetes/flux/cluster/ks.yaml` by
`p1-edit.py` is byte-identical to the gated candidate; `diff -u` is a pure
31-line append after line 72 (`labelSelector: substitution.flux.home.arpa/disabled notin (true)`),
first added line `+    - # Cluster-wide Helm drift detection (plan helm-drift-detection, phase 1: warn).`,
the JSON6902 lines `+                - op: add` / `+                  path: /spec/driftDetection`.
A second run of `p1-edit.py` on the edited copy refuses (`STOP: ks.yaml already
carries driftDetection`, rc 1).

## 2) Pre-checks

### 2.0 Every phase

```bash
cd /Users/mu/code/cberg-home-nextgen
python3 runbooks/plan-premises.py helm-drift-detection          # all 10 must PASS
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'         # header only
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'         # header only
git status --porcelain kubernetes/flux/cluster/ks.yaml            # empty: nobody else mid-edit
# Baseline for the "no Helm upgrade" assertion (§4.1) is `rev-gate.py snapshot` (§3.0.0),
# taken IMMEDIATELY before the P1 commit — never here: Step 0 and P0 itself bump revisions.
```

### 2.1 PRE-PHASE-1 GATE — every stored manifest must pass a server-side dry-run (MANDATORY)

This is the controller's own comparison, run by hand, read-only, for every
document of every release: `helm get manifest` -> `kubectl apply
--server-side --dry-run=server --field-manager=helm-controller
--force-conflicts` **per document, in the document's own namespace** (a
whole-manifest `-f -` with one `-n` false-fails cert-manager, cilium and
kube-prometheus-stack on their cross-namespace objects — that is a
`kubectl` limitation, not drift). It also prints the non-artefact diffs, which
is the §3.1.4 export and the §1.2 "expected day-1 inventory" in one run.

```bash
mkdir -p /private/tmp/claude-501/helm-drift-detection
cat > /private/tmp/claude-501/helm-drift-detection/hr-ssa-gate.py <<'PY'
#!/usr/bin/env python3
"""helm-controller drift detection, emulated read-only: per-document server-side
DRY-RUN apply of every stored release manifest as field manager helm-controller with
force ownership, then diff vs live (managedFields/status stripped). FAIL rows are
apply errors (that release WILL sit at Ready=False in warn mode). DIFF rows are what
the controller will report as drift. meta.helm.sh/* and app.kubernetes.io/managed-by
rows are filtered: helm-controller stamps them before diffing, they are artefacts."""
import json, subprocess, sys, yaml, concurrent.futures as cf
STRIP={"managedFields","resourceVersion","generation","uid","creationTimestamp","selfLink"}
ARTEFACT=("meta.helm.sh/","app.kubernetes.io/managed-by")
def run(cmd,inp=None):
    p=subprocess.run(cmd,input=inp,capture_output=True,text=True); return p.returncode,p.stdout,p.stderr
def clean(o):
    o=json.loads(json.dumps(o)); o.pop("status",None)
    for k in STRIP: o.get("metadata",{}).pop(k,None)
    return o
def diff(a,b,path=""):
    out=[]
    if isinstance(a,dict) and isinstance(b,dict):
        for k in sorted(set(a)|set(b)):
            p=path+"/"+k
            if k not in a: out.append((p,"ADD",None,b[k]))
            elif k not in b: out.append((p,"REMOVE",a[k],None))
            else: out+=diff(a[k],b[k],p)
    elif isinstance(a,list) and isinstance(b,list):
        if len(a)!=len(b): out.append((path,"LIST-LEN",len(a),len(b)))
        else:
            for i,(x,y) in enumerate(zip(a,b)): out+=diff(x,y,f"{path}/{i}")
    elif a!=b: out.append((path,"CHANGED",a,b))
    return out
def one(ns,rel):
    rc,man,err=run(["helm","get","manifest",rel,"-n",ns])
    if rc: return [f"FAIL\t{ns}/{rel}\thelm get manifest: {err.strip()[:160]}"]
    rows=[]
    for d in yaml.safe_load_all(man):
        if not d: continue
        dns=(d.get("metadata") or {}).get("namespace") or ns
        kind,name=d["kind"],d["metadata"]["name"]
        rc,out,err=run(["kubectl","apply","--server-side","--dry-run=server","--field-manager=helm-controller",
                        "--force-conflicts","-n",dns,"-o","json","-f","-"],inp=yaml.safe_dump(d))
        if rc: rows.append(f"FAIL\t{ns}/{rel}\t{kind}/{dns}/{name}\t{err.strip()[:220]}"); continue
        grp=d["apiVersion"].split("/")[0] if "/" in d["apiVersion"] else ""
        rc,live,err=run(["kubectl","get",f"{kind}.{grp}" if grp else kind,name,"-n",dns,"-o","json"])
        if rc: rows.append(f"MISSING\t{ns}/{rel}\t{kind}/{dns}/{name}\t(would be recreated)"); continue
        for p,how,a,b in diff(clean(json.loads(live)),clean(json.loads(out))):
            if any(k in p for k in ARTEFACT): continue
            if p.startswith("/metadata/") and not (p.startswith("/metadata/labels") or p.startswith("/metadata/annotations")): continue
            if how=="REMOVE" and p.startswith("/metadata/"): continue   # foreign labels/annotations survive SSA
            rows.append(f"DIFF\t{ns}/{rel}\t{kind}/{dns}/{name}\t{how}\t{p}\t{json.dumps(a,default=str)[:100]}\t{json.dumps(b,default=str)[:100]}")
    return rows
rc,out,_=run(["helm","list","-A","-o","json"])
rels=[(r["namespace"],r["name"]) for r in json.loads(out)]
print(f"releases: {len(rels)}",file=sys.stderr)
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    for rows in ex.map(lambda r: one(*r),rels):
        for r in rows: print(r)
PY
python3 /private/tmp/claude-501/helm-drift-detection/hr-ssa-gate.py > /private/tmp/claude-501/helm-drift-detection/hr-ssa-gate.tsv       # ~3 min, ~600 objects, read-only
# THE GATE is the fail-closed wrapper (§3.0.0 step 2), not `grep -c '^FAIL'`: the bare
# grep reads 0 — a false PASS — when the script crashes or helm list hides a pending
# release (both reproduced 2026-09-26). The wrapper re-runs the script and checks exit
# code, release coverage == HelmRelease count, and 0 FAIL rows:
python3 /private/tmp/claude-501/helm-drift-detection/ssa-gate-check.py; echo "rc=$?"                # MUST print SSA-GATE PASS, rc=0 — else STOP
grep '^FAIL\|^MISSING' /private/tmp/claude-501/helm-drift-detection/hr-ssa-gate.tsv
grep '^DIFF' /private/tmp/claude-501/helm-drift-detection/hr-ssa-gate.tsv                          # = the expected day-1 inventory
```

**Measured 2026-09-14 (before P0):**

```
FAIL  ai/anythingllm   Deployment/ai/anythingllm   ... .spec.template.spec.strategy: field not declared in schema
FAIL  media/jellyfin   Deployment/media/jellyfin   ... .spec.template.spec.securityContext.capabilities: field not declared in schema
DIFF  kube-system/intel-device-plugin-gpu  GpuDevicePlugin/kube-system/intel-gpu-plugin  ADD  /spec/monitoringMode  null  "single"
DIFF  monitoring/kube-prometheus-stack     Prometheus/monitoring/kube-prometheus-stack   ADD  /spec/paused          null  false
```

Any `FAIL` row names a release that will sit at `Ready=False` from P1 onward.
**Zero FAIL rows is the gate.** The two DIFF rows are expected (§1.2) and are
retired in §3.2.0; a DIFF row that is not in §1.2 is new information — record
it in the inventory finding before P1, not after.

Also for Phase 1 only:

```bash
# Nothing drifts "officially" yet — 0 events, 0 Drifted conditions is the expected start
kubectl get events -A --field-selector reason=DriftDetected --no-headers | wc -l   # 0
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Drifted")].type}{"\n"}{end}' | grep -c Drifted   # 0
```

### 2.2 Phase 2 only

- The Phase 1 inventory (§3.1.3) covers **>= 7 calendar days** including at
  least one weekend window, one nightly window with Step 0 safe-updates
  applied, one `frigate-restart` (02:30) and one `docs-site-refresh` (05:30)
  run. Shorter, and the rules are guesses.
- Every candidate rule in §3.2 is either **backed by an inventory line** or
  **struck out with a reason**.
- The inventory's day-1 lines are exactly the two in §1.2 (or the difference
  is explained in the inventory finding).
- P2 is **attended** (§3.2.0 rolls the GPU DaemonSet): `sat-attended` or
  `sun-attended`, never nightly.

### 2.3 Phase 3 only — THE GATE

```bash
# 1. The inventory must be EMPTY: every HelmRelease reports NoDriftDetected under the P2 ignore set.
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}{" "}{.status.conditions[?(@.type=="Drifted")].reason}{"\n"}{end}' | grep -v NoDriftDetected
# expect: NO output. Any line names an object that Phase 3 WILL patch on its first reconcile.
#         (An opted-out HR prints an empty reason and therefore FAILS this gate — correct direction.)

# 1b. Same thing measured from the API instead of the condition (§2.1 script, ~3 min):
python3 /private/tmp/claude-501/helm-drift-detection/hr-ssa-gate.py > /private/tmp/claude-501/helm-drift-detection/hr-ssa-gate-p3.tsv; grep -c '^FAIL\|^DIFF' /private/tmp/claude-501/helm-drift-detection/hr-ssa-gate-p3.tsv   # 0

# 2. No standing manual override on a Helm-managed workload (a replicas=0 parked by hand is
#    exactly what Phase 3 un-parks):
kubectl get deploy,sts -A -o json | python3 -c "
import sys,json
for d in json.load(sys.stdin)['items']:
    l=d['metadata'].get('labels') or {}
    if 'helm.toolkit.fluxcd.io/name' in l and d['spec'].get('replicas')==0:
        print(d['kind'], d['metadata']['namespace']+'/'+d['metadata']['name'])"
# expect: NO output (measured 2026-09-14: none)

# 3. No HelmRelease is suspended for another plan's in-flight work:
kubectl get helmrelease -A -o jsonpath='{range .items[?(@.spec.suspend==true)]}{.metadata.namespace}/{.metadata.name}{"\n"}{end}'
# expect: NO output — a suspended HR is skipped by helm-controller and would be corrected on resume

# 4. No other plan in this window touches a Helm-managed workload by hand (§6);
#    conflicts_with (grafana-chart-13.2.3 and the rest of the frontmatter list) is enforced by the sequencer.
```

If step 1, 1b or 2 prints anything: **do not run Phase 3.** Either the drift
is legitimate (add the rule, re-run Phase 2, soak again) or it is an unknown
edit (fix it in git, or revert it by hand *while still in warn mode*, and
watch it clear). The list printed in step 1 IS the explicit "what will be
corrected on the first reconcile" — Phase 3's contract is that it is empty.

## 3) Steps

Phases 1-3 edit the same file. The patch entry below is appended to
`spec.patches` of the `cluster-apps` Kustomization in
`kubernetes/flux/cluster/ks.yaml`, directly after the existing
substitution patch. Commit with `git commit --only <paths>` (shared worktree
rule in `CLAUDE.md`) and verify `git show --stat HEAD` lists exactly the
intended files. **Every phase commit also refreshes this plan's `generated:`
to the edit date** (and bumps `status`) — `maintenance-plan.py` flags a plan
`unused > stale_after_days` (14 days from `generated`), and this plan is
legitimately mid-soak from ~2026-09-29 otherwise.

### 3.0 Phase 0 — EXECUTED 2026-09-26 (`d17af8e0`)

The two SSA-rejected stored manifests were fixed (anythingllm: pod-level
`strategy` dropped + postRenderer `strategy: null`; jellyfin: container-only
keys removed from `podSecurityContext`). Result recorded in `2326ab02`: SSA gate
126/126 with only the two known DIFF rows, no pod roll (the removed keys had
already been pruned from the live pod templates). The step-by-step P0 text
(§3.0.1-§3.0.3 of the 2026-09-26 revision) is in git history at `355ef7ee`;
it is not repeated here because it will not run again. **P0 is a P1
precondition only through the §2.1 gate**, which is re-run in step 4 below: a
new SSA-invalid manifest since 2026-09-26 blocks P1 the same way.

### 3.0.0 P1 re-run — dedicated, FINAL run (re-planned 2026-09-28)

**What went wrong on 2026-09-26 and what changed** (full evidence §1.5): the
child patch was a strategic-merge patch; kustomize's SMP path re-serialises the
target HelmRelease and drops every bare `key:` (implicit null) from
`spec.values`, so 11 deliberate chart-default deletions on three HelmReleases
vanished and helm-controller upgraded them (influxdb rev 11, homepage rev 30,
adguard-home rev 22; the revert re-upgraded them at rev 12/31/23). The child
patch is now a JSON6902 `op: add /spec/driftDetection`, which never touches
another field, and two new PRE-COMMIT render gates prove over the whole tree
that nothing but `spec.driftDetection` changes — both demonstrated to FAIL on
the 2026-09-26 shape. A third, post-apply gate compares every live HelmRelease
spec with a pre-commit snapshot.

**Why still a dedicated FINAL run** (unchanged reasoning): P1 must be the last
HelmRelease change of its day — the §2.1 SSA gate must cover every stored
manifest as it will be after that day's upgrades, and the revision gate must
attribute every Helm upgrade. `run-now.py` cannot express "last", so P1 is its
own on-demand run (or the last plan of an attended window with nothing
HelmRelease-changing after it).

Every block is self-contained (no shell variable, function or port-forward
survives between blocks); state lives in fixed files under
`/private/tmp/claude-501/helm-drift-detection/`.

1. **Preconditions.** Any main NOW run of the day is FINALIZED (`run-now.py`
   exits 10 while a `now` row is open). This plan is `status: vetted`. Then
   `.venv/bin/python3 runbooks/run-now.py preflight helm-drift-detection --operator-go "<who/how>"`
   -> exit 0. Step 0 of the run lands first as always; the settle check in
   `rev-gate.py` absorbs it. §2.0 as written (all premises PASS — including
   `flux-distribution-is-2.9` and `kustomize-controller-is-v1.9`, which pin the
   claim that the local `flux build` reproduces the controller's kustomize), and
   `flux version --client` prints `flux: v2.9.` (the CLI half of that claim;
   2.9.0 on 2026-09-28 — any other minor: STOP and re-run step 3 before trusting
   step 6).
2. **Tooling** — run the §2.1 heredoc block (writes `hr-ssa-gate.py`), then:

```bash
mkdir -p /private/tmp/claude-501/helm-drift-detection
cat > /private/tmp/claude-501/helm-drift-detection/ssa-gate-check.py <<'SSACHECK'
#!/usr/bin/env python3
"""Wraps hr-ssa-gate.py (same dir) so the gate FAILS CLOSED: a crash, a partial
run (helm list hiding a pending release) or a FAIL row is a FAIL; only a complete
run over every HelmRelease with zero FAIL rows prints SSA-GATE PASS."""
import json, os, subprocess, sys
D = os.path.dirname(os.path.abspath(__file__))
p = subprocess.run([sys.executable, f"{D}/hr-ssa-gate.py"], capture_output=True, text=True)
open(f"{D}/hr-ssa-gate.tsv", "w").write(p.stdout)
hr = len(json.loads(subprocess.run(["kubectl", "get", "helmrelease", "-A", "-o", "json"],
                                   capture_output=True, text=True, check=True).stdout)["items"])
rel = [l for l in p.stderr.splitlines() if l.startswith("releases: ")]
rows = p.stdout.splitlines()
fails = [r for r in rows if r.startswith("FAIL")]
for r in rows:
    print(r[:300])
problems = []
if p.returncode: problems.append(f"gate script exited {p.returncode}: {p.stderr.strip()[-300:]}")
if rel != [f"releases: {hr}"]: problems.append(f"covered {rel} but {hr} HelmReleases exist")
if fails: problems.append(f"{len(fails)} FAIL row(s)")
print(f"SSA-GATE {'FAIL' if problems else 'PASS'}: HelmReleases={hr} {rel} FAIL={len(fails)} "
      f"DIFF={sum(r.startswith('DIFF') for r in rows)} MISSING={sum(r.startswith('MISSING') for r in rows)}")
for x in problems: print("  -", x)
sys.exit(1 if problems else 0)
SSACHECK
cat > /private/tmp/claude-501/helm-drift-detection/rev-gate.py <<'REVGATE'
#!/usr/bin/env python3
"""Helm-revision identity gate for helm-drift-detection P1, scoped so other plans'
commits cannot false-FAIL it and a real upgrade cannot false-PASS it.
  rev-gate.py snapshot NAME            -> <dir>/rev-NAME.json   (refuses unless SETTLED)
  rev-gate.py compare NAME [--require-warn] [--no-explain]
Exit 0 PASS, 1 FAIL, 2 NOT-SETTLED (re-run later; never read 2 as a pass)."""
import json, os, subprocess, sys
D = os.path.dirname(os.path.abspath(__file__))
REPO = "/Users/mu/code/cberg-home-nextgen"
def sh(*c): return subprocess.run(c, capture_output=True, text=True, check=True, cwd=REPO).stdout
def cond(o, t):
    return next((c for c in o.get("status", {}).get("conditions", []) if c["type"] == t), None)
def settled(require_warn):
    subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=REPO, check=True)
    head = sh("git", "rev-parse", "origin/main").strip()
    # floor = newest commit that touches anything Flux applies; plan-only commits
    # by other sessions move HEAD but cannot change a HelmRelease, so they are ignored
    floor = sh("git", "log", "-1", "--format=%H", "origin/main", "--", "kubernetes/").strip()
    why = []
    for k in json.loads(sh("kubectl", "get", "kustomization", "-A", "-o", "json"))["items"]:
        n = k["metadata"]["namespace"] + "/" + k["metadata"]["name"]
        if k["spec"].get("suspend"): continue
        applied = (k["status"].get("lastAppliedRevision") or "").rsplit(":", 1)[-1]
        if not applied or subprocess.run(["git", "merge-base", "--is-ancestor", floor, applied], cwd=REPO).returncode != 0:
            why.append(f"ks {n} applied {applied[:8] or '-'} does not contain {floor[:8]}")
        if k["status"].get("observedGeneration") != k["metadata"]["generation"]: why.append(f"ks {n} generation lag")
    hrs = json.loads(sh("kubectl", "get", "helmrelease", "-A", "-o", "json"))["items"]
    for h in hrs:
        n = h["metadata"]["namespace"] + "/" + h["metadata"]["name"]
        r = cond(h, "Ready")
        if h["status"].get("observedGeneration") != h["metadata"]["generation"]: why.append(f"hr {n} generation lag")
        if not r or r["status"] != "True": why.append(f"hr {n} Ready={r and r['status']}")
        if require_warn:
            if (h["spec"].get("driftDetection") or {}).get("mode") != "warn": why.append(f"hr {n} mode!=warn")
            if not cond(h, "Drifted"): why.append(f"hr {n} has no Drifted condition (detection never ran)")
    return head, hrs, why
def revs():
    return {f"{r['namespace']}/{r['name']}": int(r["revision"]) for r in json.loads(sh("helm", "list", "-A", "-a", "-o", "json"))}
def main(argv, settled=settled):
  mode, name = argv[1], argv[2]
  flags = set(argv[3:]); path = f"{D}/rev-{name}.json"
  head, hrs, why = settled("--require-warn" in flags)
  if why:
      print("NOT-SETTLED:", len(why), "reason(s)"); print("\n".join(why[:25])); sys.exit(2)
  cur = revs()
  if len(cur) != len(hrs):
      print(f"FAIL: helm list has {len(cur)} releases, {len(hrs)} HelmReleases"); sys.exit(1)
  if mode == "snapshot":
      json.dump({"head": head, "revs": cur}, open(path, "w"), indent=1)
      print(f"SNAPSHOT {name}: {len(cur)} releases at {head[:8]} -> {path}"); sys.exit(0)
  base = json.load(open(path))
  ks = {(k["metadata"]["namespace"], k["metadata"]["name"]): k["spec"]["path"].lstrip("./")
        for k in json.loads(sh("kubectl", "get", "kustomization", "-A", "-o", "json"))["items"]}
  bad, explained = [], []
  for key in sorted(set(base["revs"]) | set(cur)):
      a, b = base["revs"].get(key), cur.get(key)
      if a == b: continue
      h = next((x for x in hrs if f"{x['metadata']['namespace']}/{x['metadata']['name']}" == key), None)
      lab = (h or {}).get("metadata", {}).get("labels", {})
      kpath = ks.get((lab.get("kustomize.toolkit.fluxcd.io/namespace"), lab.get("kustomize.toolkit.fluxcd.io/name")))
      commits = sh("git", "log", "--format=%h %s", f"{base['head']}..{head}", "--", kpath).strip() if kpath and "--no-explain" not in flags else ""
      (explained if commits else bad).append(f"{key} rev {a}->{b}" + (f"  explained by: {commits.splitlines()[0]}" if commits else ("  (--no-explain)" if "--no-explain" in flags else f"  (path {kpath}: no commit since {base['head'][:8]})")))
  for e in explained: print("EXPLAINED", e)
  for e in bad: print("UNEXPLAINED", e)
  print(f"REV-GATE {'FAIL' if bad else 'PASS'}: {len(cur)} releases, {len(explained)} explained change(s), {len(bad)} unexplained")
  sys.exit(1 if bad else 0)
if __name__ == "__main__":
  main(sys.argv)
REVGATE
cat > /private/tmp/claude-501/helm-drift-detection/render-gate.py <<'RENDERGATE'
#!/usr/bin/env python3
"""helm-drift-detection render gate: prove the CHILD-level patch changes nothing
in any rendered object except adding spec.driftDetection to HelmReleases.

For every live child Kustomization of cluster-apps (not opted out), `flux build`
twice: BASE = the live child spec as applied today; CAND = the same spec plus the
candidate child patch. Require per rendered object:
  - HelmRelease: CAND minus spec.driftDetection == BASE (deep; null != missing,
    PyYAML loads both `key:` and `key: null` as None), and
    CAND.spec.driftDetection == VALUE
  - every other object: CAND == BASE
Coverage: rendered HelmReleases == live HelmReleases (minus opted-out children),
so a crash or a skipped child can never read as PASS. Prints ids and JSON paths
only, never values (values carry cluster-secrets substitutions).
--patch smp reproduces the 2026-09-26 fbc220f7 shape: KNOWN-BAD CONTROL ONLY.
Exit 0 = RENDER-GATE PASS, 1 = FAIL. Read-only."""
import argparse, json, os, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
import yaml

OPT_OUT = "drift-detection.flux.home.arpa/disabled"
ap = argparse.ArgumentParser()
ap.add_argument("--patch", choices=["smp", "json6902"], required=True)
ap.add_argument("--value", default='{"mode": "warn"}',
                help="JSON of spec.driftDetection (P1 warn; P2 adds ignore; P3 enabled)")
ap.add_argument("--repo", default="/Users/mu/code/cberg-home-nextgen")
a = ap.parse_args()
VALUE = json.loads(a.value)
TARGET = {"group": "helm.toolkit.fluxcd.io", "kind": "HelmRelease"}
if a.patch == "smp":
    PATCH = {"patch": yaml.safe_dump({"apiVersion": "helm.toolkit.fluxcd.io/v2", "kind": "HelmRelease",
                                      "metadata": {"name": "not-used"},
                                      "spec": {"driftDetection": VALUE}}), "target": TARGET}
else:
    PATCH = {"patch": yaml.safe_dump([{"op": "add", "path": "/spec/driftDetection", "value": VALUE}]),
             "target": TARGET}


# Excluded from comparison: ConfigMap */cluster-settings. Its SETTING_EXAMPLE value
# substitutes itself (`${SETTING_EXAMPLE}` inside its own value) and grows ~54 bytes on
# every apply by cluster-apps/eck-operator/kibana/elasticsearch, so two renders seconds
# apart can differ for a reason unrelated to the patch (plan review 2026-09-28; repo
# correction owed in kubernetes/flux/components/common/cluster-settings.yaml). The
# drift-detection child patch targets kind HelmRelease only and cannot touch it.
def excluded(k):
    return k[0] == "ConfigMap" and k[2] == "cluster-settings"


def kget(*args):
    return json.loads(subprocess.check_output(["kubectl", "get", *args, "-o", "json"]))


def diffpaths(x, y, p=""):
    if type(x) is not type(y):
        return [p or "/"]
    if isinstance(x, dict):
        out = []
        for k in sorted(set(x) | set(y), key=str):
            if k not in x or k not in y:
                out.append(f"{p}/{k} ({'missing in CAND' if k not in y else 'added in CAND'})")
            else:
                out += diffpaths(x[k], y[k], f"{p}/{k}")
        return out
    if isinstance(x, list):
        if len(x) != len(y):
            return [f"{p} (len {len(x)}->{len(y)})"]
        return sum((diffpaths(i, j, f"{p}/{n}") for n, (i, j) in enumerate(zip(x, y))), [])
    return [] if x == y else [p]


def build(ks, extra):
    obj = {"apiVersion": ks["apiVersion"], "kind": ks["kind"],
           "metadata": {"name": ks["metadata"]["name"], "namespace": ks["metadata"]["namespace"]},
           "spec": json.loads(json.dumps(ks["spec"]))}
    if extra:
        obj["spec"]["patches"] = list(obj["spec"].get("patches") or []) + [PATCH]
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(obj, f)
        fn = f.name
    try:
        r = subprocess.run(["flux", "build", "kustomization", obj["metadata"]["name"],
                            "-n", obj["metadata"]["namespace"], "--path", obj["spec"]["path"],
                            "--kustomization-file", fn], cwd=a.repo, capture_output=True, text=True)
    finally:
        os.unlink(fn)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else f"rc={r.returncode}")
    docs = {}
    for d in yaml.safe_load_all(r.stdout):
        if isinstance(d, dict):
            m = d.get("metadata", {})
            docs[(d.get("kind"), m.get("namespace"), m.get("name"))] = d
    return docs


def check(ks):
    name = f'{ks["metadata"]["namespace"]}/{ks["metadata"]["name"]}'
    try:
        base, cand = build(ks, False), build(ks, True)
    except Exception as e:  # noqa: BLE001
        return name, "ERROR", [str(e)], 0
    fails, nhr = [], 0
    if set(base) != set(cand):
        fails.append(f"object set differs: {sorted(map(str, set(base) ^ set(cand)))}")
    for k in sorted(set(base) & set(cand), key=str):
        if excluded(k):
            continue
        b, c = base[k], json.loads(json.dumps(cand[k]))
        if k[0] == "HelmRelease":
            nhr += 1
            dd = c.get("spec", {}).pop("driftDetection", "ABSENT")
            if dd != VALUE:
                fails.append(f"{k}: spec.driftDetection is not the expected value")
        fails += [f"{k[0]} {k[1]}/{k[2]}: {p}" for p in diffpaths(b, c)]
    return name, ("FAIL" if fails else "PASS"), fails, nhr


items = [k for k in kget("kustomization", "-A")["items"]
         if (k["metadata"].get("labels") or {}).get("kustomize.toolkit.fluxcd.io/name") == "cluster-apps"
         and (k["metadata"].get("labels") or {}).get(OPT_OUT) != "true"]
optout_ns = {k["metadata"]["namespace"] + "/" + k["metadata"]["name"]
             for k in kget("kustomization", "-A")["items"]
             if (k["metadata"].get("labels") or {}).get(OPT_OUT) == "true"}
live_hr = sum(1 for h in kget("helmrelease", "-A")["items"]
              if f'{h["metadata"].get("labels", {}).get("kustomize.toolkit.fluxcd.io/namespace")}/'
                 f'{h["metadata"].get("labels", {}).get("kustomize.toolkit.fluxcd.io/name")}' not in optout_ns)
with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(check, items))
nfail = 0
for name, st, fails, _ in sorted(res):
    if st != "PASS":
        nfail += 1
        print(f"{st} {name}")
        for f in fails:
            print(f"    {f}")
rendered_hr = sum(r[3] for r in res)
print(f"children={len(items)} rendered_helmreleases={rendered_hr} live_helmreleases={live_hr} "
      f"non_pass={nfail} patch={a.patch} value={json.dumps(VALUE, sort_keys=True)[:80]}")
ok = nfail == 0 and rendered_hr == live_hr and rendered_hr > 0
print("RENDER-GATE PASS" if ok else "RENDER-GATE FAIL")
sys.exit(0 if ok else 1)
RENDERGATE
cat > /private/tmp/claude-501/helm-drift-detection/parent-gate.py <<'PARENTGATE'
#!/usr/bin/env python3
"""helm-drift-detection parent gate: render cluster-apps from the CURRENT and the
CANDIDATE kubernetes/flux/cluster/ks.yaml and require
  - an identical rendered object set,
  - every non-Kustomization object deep-identical,
  - every child Kustomization identical outside /spec/patches, and /spec/patches
    == exactly ONE JSON6902 patch [{op: add, path: /spec/driftDetection, value: VALUE}]
    targeting HelmRelease (compared PARSED, so ks.yaml whitespace is free, but the
    fbc220f7 strategic-merge shape -- a mapping, not an op list -- can never match),
  - opted-out children (drift-detection.flux.home.arpa/disabled=true) unchanged.
Together with render-gate.py (which proves THAT child patch preserves every value)
this covers the whole parent -> child -> HelmRelease path.
Usage: parent-gate.py <current ks.yaml> <candidate ks.yaml> ['<VALUE JSON>']
Exit 0 = PARENT-GATE PASS, 1 = FAIL. Prints ids only, never values."""
import json, os, subprocess, sys, tempfile
import yaml

REPO = "/Users/mu/code/cberg-home-nextgen"
VALUE = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {"mode": "warn"}
TARGET = {"group": "helm.toolkit.fluxcd.io", "kind": "HelmRelease"}


# Excluded from comparison: ConfigMap */cluster-settings. Its SETTING_EXAMPLE value
# substitutes itself (`${SETTING_EXAMPLE}` inside its own value) and grows ~54 bytes on
# every apply by cluster-apps/eck-operator/kibana/elasticsearch, so two renders seconds
# apart can differ for a reason unrelated to the patch (plan review 2026-09-28; repo
# correction owed in kubernetes/flux/components/common/cluster-settings.yaml). The
# drift-detection child patch targets kind HelmRelease only and cannot touch it.
def excluded(k):
    return k[0] == "ConfigMap" and k[2] == "cluster-settings"


def is_expected(patches):
    if not isinstance(patches, list) or len(patches) != 1:
        return False
    p = patches[0]
    try:
        ops = yaml.safe_load(p.get("patch", ""))
    except yaml.YAMLError:
        return False
    return p.get("target") == TARGET and ops == [{"op": "add", "path": "/spec/driftDetection", "value": VALUE}]


def render(ksfile):
    doc = next(d for d in yaml.safe_load_all(open(ksfile)) if d and d["metadata"]["name"] == "cluster-apps")
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(doc, f)
        fn = f.name
    try:
        r = subprocess.run(["flux", "build", "kustomization", "cluster-apps", "-n", "flux-system",
                            "--path", "./kubernetes/apps", "--kustomization-file", fn],
                           cwd=REPO, capture_output=True, text=True)
    finally:
        os.unlink(fn)
    if r.returncode:
        print(f"PARENT-GATE FAIL: flux build rc={r.returncode}")
        sys.exit(1)
    out = {}
    for d in yaml.safe_load_all(r.stdout):
        if isinstance(d, dict):
            m = d["metadata"]
            out[(d["kind"], m.get("namespace"), m["name"])] = d
    return out


base, cand = render(sys.argv[1]), render(sys.argv[2])
fails, nks, npatched = [], 0, 0
if set(base) != set(cand):
    fails.append(f"object set differs: {sorted(map(str, set(base) ^ set(cand)))}")
for k in sorted(set(base) & set(cand), key=str):
    if excluded(k):
        continue
    b, c = json.loads(json.dumps(base[k])), json.loads(json.dumps(cand[k]))
    if k[0] == "Kustomization":
        nks += 1
        optout = (c["metadata"].get("labels") or {}).get("drift-detection.flux.home.arpa/disabled") == "true"
        bp, cp = b["spec"].pop("patches", None), c["spec"].pop("patches", None)
        if optout:
            if bp != cp:
                fails.append(f"{k}: opted-out child's patches changed")
        elif bp is not None or not is_expected(cp):
            fails.append(f"{k}: patches base={'set' if bp else 'none'} cand={'EXPECTED' if is_expected(cp) else 'UNEXPECTED'}")
        else:
            npatched += 1
    if b != c:
        fails.append(f"{k}: differs outside /spec/patches")
for f in fails:
    print("FAIL", f)
print(f"objects={len(cand)} child_kustomizations={nks} patched={npatched} fails={len(fails)}")
ok = not fails and npatched > 0
print("PARENT-GATE PASS" if ok else "PARENT-GATE FAIL")
sys.exit(0 if ok else 1)
PARENTGATE
cat > /private/tmp/claude-501/helm-drift-detection/values-gate.py <<'VALUESGATE'
#!/usr/bin/env python3
"""Live HelmRelease spec-identity gate for helm-drift-detection P1.
  values-gate.py snapshot NAME   -> <dir>/values-NAME.json (every live HR's spec minus driftDetection)
  values-gate.py compare NAME [--expect ns/name ...]
                                 -> deep-compare the live specs now with the snapshot;
                                    --expect lists HelmReleases whose spec change is
                                    INTENDED in this step (e.g. P2's reloader switch):
                                    they are printed EXPECTED and do not fail the gate,
                                    but an --expect entry that did NOT change fails it
The ONLY permitted difference is spec.driftDetection. null vs missing is a
difference (the 2026-09-26 failure was exactly `key: null` -> key absent).
Prints ids + JSON paths only, never values. Exit 0 PASS, 1 FAIL."""
import json, os, subprocess, sys
D = os.path.dirname(os.path.abspath(__file__))


def live():
    items = json.loads(subprocess.run(["kubectl", "get", "helmrelease", "-A", "-o", "json"],
                                      capture_output=True, text=True, check=True).stdout)["items"]
    out = {}
    for h in items:
        s = dict(h["spec"])
        s.pop("driftDetection", None)
        out[h["metadata"]["namespace"] + "/" + h["metadata"]["name"]] = s
    return out


def paths(a, b, p=""):
    if type(a) is not type(b):
        return [p or "/"]
    if isinstance(a, dict):
        r = []
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                r.append(f"{p}/{k} ({'removed' if k not in b else 'added'})")
            else:
                r += paths(a[k], b[k], f"{p}/{k}")
        return r
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{p} (len {len(a)}->{len(b)})"]
        return sum((paths(x, y, f"{p}/{i}") for i, (x, y) in enumerate(zip(a, b))), [])
    return [] if a == b else [p]


mode, name = sys.argv[1], sys.argv[2]
expect = set(sys.argv[sys.argv.index("--expect") + 1:]) if "--expect" in sys.argv else set()
f = f"{D}/values-{name}.json"
cur = live()
if mode == "snapshot":
    json.dump(cur, open(f, "w"))
    def nulls(o):
        if isinstance(o, dict): return sum(1 if v is None else nulls(v) for v in o.values())
        if isinstance(o, list): return sum(1 if v is None else nulls(v) for v in o)
        return 0
    nv = sum(nulls(v.get("values") or {}) for v in cur.values())
    print(f"VALUES SNAPSHOT {name}: {len(cur)} HelmReleases, {nv} null leaves in spec.values -> {f}")
    sys.exit(0)
base = json.load(open(f))
bad = 0
changed = set()
for k in sorted(set(base) | set(cur)):
    if k not in base or k not in cur:
        print(f"FAIL {k}: {'new' if k not in base else 'gone'}"); bad += 1; continue
    for p in paths(base[k], cur[k], "/spec"):
        changed.add(k)
        if k in expect:
            print(f"EXPECTED {k}: {p}")
        else:
            print(f"FAIL {k}: {p}"); bad += 1
for k in sorted(expect - changed):
    print(f"FAIL {k}: --expect given but its spec did not change"); bad += 1
print(f"VALUES-GATE {'FAIL' if bad else 'PASS'}: {len(cur)} HelmReleases, {bad} difference(s) outside spec.driftDetection")
sys.exit(1 if bad else 0)
VALUESGATE
cat > /private/tmp/claude-501/helm-drift-detection/p1-edit.py <<'P1EDIT'
#!/usr/bin/env python3
"""Append the P1 drift-detection patch to cluster-apps' spec.patches in
kubernetes/flux/cluster/ks.yaml. Text-level append (the file is NEVER
re-serialised), anchored: refuses unless the file ends with the substitution
patch's target block exactly once and carries no driftDetection yet."""
import sys
F = sys.argv[1] if len(sys.argv) > 1 else "/Users/mu/code/cberg-home-nextgen/kubernetes/flux/cluster/ks.yaml"
ANCHOR = ("      target:\n        group: kustomize.toolkit.fluxcd.io\n        kind: Kustomization\n"
          "        labelSelector: substitution.flux.home.arpa/disabled notin (true)\n")
BLOCK = """    - # Cluster-wide Helm drift detection (plan helm-drift-detection, phase 1: warn).
      # Every child Kustomization gets a patch that stamps spec.driftDetection onto
      # each HelmRelease it renders. `warn` only compares (server-side dry-run) and
      # emits DriftDetected events + a Drifted condition; it never patches anything.
      # The child patch MUST stay a JSON6902 `op: add`: a strategic-merge patch
      # re-serialises the HelmRelease and drops bare `key:` (implicit-null) values
      # from spec.values -> Helm upgrade (influxdb/homepage/adguard-home, 2026-09-26,
      # fbc220f7 reverted in 5bdd3164).
      # OPT-OUT: label the app's ks.yaml with
      #   drift-detection.flux.home.arpa/disabled: "true"
      # and its own helmrelease.yaml owns the field (the child's spec.patches list is
      # REPLACED by this one).
      patch: |-
        apiVersion: kustomize.toolkit.fluxcd.io/v1
        kind: Kustomization
        metadata:
          name: not-used
        spec:
          patches:
            - patch: |-
                - op: add
                  path: /spec/driftDetection
                  value:
                    mode: warn
              target:
                group: helm.toolkit.fluxcd.io
                kind: HelmRelease
      target:
        group: kustomize.toolkit.fluxcd.io
        kind: Kustomization
        labelSelector: drift-detection.flux.home.arpa/disabled notin (true)
"""
t = open(F).read()
if "driftDetection" in t:
    sys.exit("STOP: ks.yaml already carries driftDetection")
if t.count(ANCHOR) != 1 or not t.endswith(ANCHOR):
    sys.exit("STOP: ks.yaml no longer ends with the substitution patch target -- file changed since review")
open(F, "w").write(t + BLOCK)
print("edited", F)
P1EDIT
ls -l /private/tmp/claude-501/helm-drift-detection/
```

3. **Known-bad demonstrations — every new gate must be seen to FAIL** on the
   identical command that must PASS in step 6/8:

```bash
cd /Users/mu/code/cberg-home-nextgen
D=/private/tmp/claude-501/helm-drift-detection
# 3a. Render gate with the 2026-09-26 child patch shape (strategic merge). ~10 s.
.venv/bin/python3 $D/render-gate.py --patch smp; echo "rc=$?"
# MUST print RENDER-GATE FAIL, rc=1, naming exactly databases/influxdb, default/homepage,
# network/adguard-home with "/spec/values/... (missing in CAND)" rows (11 paths; measured
# 2026-09-28). A DIFFERENT set of HelmRelease rows means the bare-key null inventory in git
# changed since 2026-09-28 — re-run the §1.5 enumeration and record it (non-HelmRelease rows
# cannot appear: the one self-growing object, ConfigMap */cluster-settings, is excluded in
# the script — see its comment); a PASS here means no bare-key
# null is left anywhere (then 3b/3c alone carry the fail-ability demonstration).
# 3b. Parent gate against the reverted P1 shape:
git show fbc220f7:kubernetes/flux/cluster/ks.yaml > $D/ks-fbc220f7.yaml
git show HEAD:kubernetes/flux/cluster/ks.yaml > $D/ks-before.yaml
.venv/bin/python3 $D/parent-gate.py $D/ks-before.yaml $D/ks-fbc220f7.yaml > $D/pg-fbc.txt; echo "rc=$?"; tail -2 $D/pg-fbc.txt
# MUST print "patched=0 fails=<child count>" + PARENT-GATE FAIL (every child's patch is the SMP
# mapping, not the JSON6902 op). Measured 2026-09-28: fails=139, rc=1.
# 3c. Values gate against a doctored snapshot (one null leaf deleted):
.venv/bin/python3 $D/values-gate.py snapshot DEMO
.venv/bin/python3 -c "
import json; f='$D/values-DEMO.json'; d=json.load(open(f))
del d['databases/influxdb']['values']['backup']['resources']['requests']; json.dump(d, open(f,'w'))"
.venv/bin/python3 $D/values-gate.py compare DEMO; echo "rc=$?"
# MUST print "FAIL databases/influxdb: /spec/values/backup/resources/requests (added)" +
# VALUES-GATE FAIL, rc=1 (measured 2026-09-28). If influxdb's null moved, pick any path from
# `.venv/bin/python3 $D/values-gate.py snapshot X` output's null leaves instead.
```

4. **SSA gate** — `python3 /private/tmp/claude-501/helm-drift-detection/ssa-gate-check.py; echo "rc=$?"`
   MUST print `SSA-GATE PASS` (rc 0: script exit 0, releases == HelmRelease
   count, 0 FAIL rows). The two DIFF rows (GpuDevicePlugin, Prometheus) are
   expected. Anything else: STOP.
5. **Baselines, immediately before the edit:**

```bash
cd /Users/mu/code/cberg-home-nextgen
python3 /private/tmp/claude-501/helm-drift-detection/rev-gate.py snapshot B; echo "rc=$?"      # rc 0; re-run on 2 (never proceed on 2)
.venv/bin/python3 /private/tmp/claude-501/helm-drift-detection/values-gate.py snapshot B      # "126 HelmReleases, 18 null leaves" on 2026-09-28
```

6. **Edit + prove (pre-commit; nothing is pushed if either gate fails):**

```bash
cd /Users/mu/code/cberg-home-nextgen
D=/private/tmp/claude-501/helm-drift-detection
git status --porcelain kubernetes/flux/cluster/ks.yaml                 # empty
git show HEAD:kubernetes/flux/cluster/ks.yaml > $D/ks-before.yaml
.venv/bin/python3 $D/p1-edit.py                                        # "edited ..."; STOP text = file changed since review
git diff --stat -- kubernetes/flux/cluster/ks.yaml                    # 1 file changed, 31 insertions(+)
git diff -- kubernetes/flux/cluster/ks.yaml | grep -c '^-[^-]'        # 0 (pure append)
.venv/bin/python3 $D/parent-gate.py $D/ks-before.yaml kubernetes/flux/cluster/ks.yaml; echo "rc=$?"
# MUST: "child_kustomizations=N patched=N fails=0" (N=139 on 2026-09-28) + PARENT-GATE PASS, rc 0
.venv/bin/python3 $D/render-gate.py --patch json6902; echo "rc=$?"
# MUST: "rendered_helmreleases=H live_helmreleases=H non_pass=0" (H=126 on 2026-09-28) + RENDER-GATE PASS, rc 0
# Either FAILS: git checkout -- kubernetes/flux/cluster/ks.yaml, STOP, read the paths printed.
# (2026-09-28 review: 2 of 5 unpatched runs false-failed on ConfigMap cluster-settings, which
#  grows on every apply; the scripts now exclude it. Re-verified PASS 3/3 json6902, FAIL 3/3 smp.)
```

   Why the two gates together are the proof: `parent-gate` proves the edited
   `ks.yaml` hands EVERY child exactly `[{op: add, path: /spec/driftDetection,
   value: {mode: warn}}]` and changes nothing else in any child or any other
   object `cluster-apps` renders; `render-gate` proves that exact child patch,
   applied to every live child spec, changes nothing in any rendered object
   except adding `spec.driftDetection` — null-vs-missing distinguished, so the
   2026-09-26 failure is the thing it measures (3a).

7. **Commit `kubernetes/flux/cluster/ks.yaml` ALONE** (the close-out in step 10
   carries this plan, so a P1 revert stays one file). Message file first; the
   commit in a shell that has NOT sourced `sweep-pg-dsn.sh` (a sourced DSN
   breaks the pre-commit hook):

```bash
cd /Users/mu/code/cberg-home-nextgen
M=/private/tmp/claude-501/helm-drift-detection/msg-helm-drift-detection-p1b-$(date +%s).txt
printf '%s\n' "feat(flux): helm drift detection phase 1 (re-run) - mode: warn via JSON6902" "" \
  "One parent patch on cluster-apps; each child Kustomization adds" \
  "spec.driftDetection {mode: warn} to its HelmReleases with a JSON6902 op:add," \
  "never a strategic-merge patch: the SMP form dropped bare key: nulls from" \
  "spec.values and upgraded influxdb/homepage/adguard-home (fbc220f7, reverted" \
  "in 5bdd3164). Pre-commit gates: parent-gate + render-gate PASS over all" \
  "children, 0 changed values; SSA gate PASS. Detection only, no correction." \
  "Plan: runbooks/maintenance/plans/helm-drift-detection.md section 3.0.0" > "$M"
git commit --only kubernetes/flux/cluster/ks.yaml -F "$M"
git show --stat HEAD          # exactly kubernetes/flux/cluster/ks.yaml
git log -1 --format=%s        # the subject above — amend BEFORE push if not
git push
flux reconcile kustomization flux-system --with-source   # the flux-upgrade.md-sanctioned nudge
```

8. **P1 verification** (Monitor tool re-runs; no sleep loops):

```bash
cd /Users/mu/code/cberg-home-nextgen
python3 /private/tmp/claude-501/helm-drift-detection/rev-gate.py compare B --require-warn; echo "rc=$?"
# rc 2 while propagating (re-run). rc 0 = every HelmRelease has mode: warn,
# observedGeneration == generation, Ready=True, a Drifted condition, and NO unexplained
# revision change (the P1 commit touches no app path, so ANY upgrade is UNEXPLAINED —
# exactly how it caught the 2026-09-26 run). rc 1 = STOP -> §5 P1 revert NOW.
.venv/bin/python3 /private/tmp/claude-501/helm-drift-detection/values-gate.py compare B; echo "rc=$?"
# rc 0 "VALUES-GATE PASS: 126 HelmReleases, 0 difference(s) outside spec.driftDetection".
# On 2026-09-26 this would have printed 11 "(removed)" rows on 3 HelmReleases.
# rc 1 = STOP -> §5 P1 revert NOW (a values change IS a Helm upgrade within seconds) —
# UNLESS every FAIL row names a HelmRelease that the rev-gate line above printed as
# EXPLAINED (a concurrent session's commit to that app's path since snapshot B). Then re-run
# as `values-gate.py compare B --expect <ns/name> ...` for exactly those releases; it must
# PASS. Never pass --expect for a release rev-gate did not EXPLAIN.
```

   Then §4.1 assertions 1 and 3.
9. **If step 8 fails**, the revert is §5 "P1 revert"; after it, re-run both
   step-8 commands: values-gate PASS again, and every UNEXPLAINED release in
   rev-gate reverted to the pre-P1 values (a second upgrade, as on 2026-09-26 —
   expected, not a new fault).
10. **Close-out commit (this plan file only):** `status: awaiting-soak` (NOT
    `vetted`: `run-now.py` refuses awaiting-soak, so no NOW run can collapse the
    soak), `window: null`, `generated: "<today>"`, the §3.1.3 day-1 finding id
    in `finding_refs`. P2 not before P1 + 7 days and only after the inventory
    spans a weekend window (§2.2).

### 3.1 Phase 1 — `mode: warn` cluster-wide (landed ONLY via §3.0.0; operator GO)

#### 3.1.1 The edit

Appended verbatim to `spec.patches` of `cluster-apps` by `p1-edit.py`
(§3.0.0 step 2/6) — a text append, the file is never re-serialised:

```yaml
    - # Cluster-wide Helm drift detection (plan helm-drift-detection, phase 1: warn).
      # Every child Kustomization gets a patch that stamps spec.driftDetection onto
      # each HelmRelease it renders. `warn` only compares (server-side dry-run) and
      # emits DriftDetected events + a Drifted condition; it never patches anything.
      # The child patch MUST stay a JSON6902 `op: add`: a strategic-merge patch
      # re-serialises the HelmRelease and drops bare `key:` (implicit-null) values
      # from spec.values -> Helm upgrade (influxdb/homepage/adguard-home, 2026-09-26,
      # fbc220f7 reverted in 5bdd3164).
      # OPT-OUT: label the app's ks.yaml with
      #   drift-detection.flux.home.arpa/disabled: "true"
      # and its own helmrelease.yaml owns the field (the child's spec.patches list is
      # REPLACED by this one).
      patch: |-
        apiVersion: kustomize.toolkit.fluxcd.io/v1
        kind: Kustomization
        metadata:
          name: not-used
        spec:
          patches:
            - patch: |-
                - op: add
                  path: /spec/driftDetection
                  value:
                    mode: warn
              target:
                group: helm.toolkit.fluxcd.io
                kind: HelmRelease
      target:
        group: kustomize.toolkit.fluxcd.io
        kind: Kustomization
        labelSelector: drift-detection.flux.home.arpa/disabled notin (true)
```

#### 3.1.2 Land it

Only through §3.0.0 steps 1-10 (known-bad demonstrations, SSA gate, baselines,
`p1-edit.py`, parent-gate + render-gate PASS, commit `ks.yaml` ALONE, push,
rev-gate + values-gate). The 2026-09-26 text of this subsection (commit plan +
`ks.yaml` together, `grep -c 'mode: warn'` as the render proof) is retired: a
count of `mode: warn` lines is exactly the proof that PASSED on 2026-09-26 while
three HelmReleases lost values.

#### 3.1.3 Inventory collection (runs for the whole soak, not just in the window)

The **`Drifted` condition is the durable inventory** — it persists on the
HelmRelease as long as the drift exists and is refreshed every reconcile
(interval 30m on 118 of 124 HRs). Events expire after the apiserver's 1h TTL
and are only useful for the *timing* of a drift. Snapshot at least once per
nightly window and once per sweep:

```bash
# Current inventory — one line per HR with its condition reason + message
kubectl get helmrelease -A -o json | python3 -c "
import sys,json
for h in json.load(sys.stdin)['items']:
    for c in h['status'].get('conditions',[]):
        if c['type']=='Drifted' and c['status']=='True':
            print(h['metadata']['namespace']+'/'+h['metadata']['name'], '|', c['message'].replace('\n',' ')[:400])"
# day 1 expected: exactly kube-system/intel-device-plugin-gpu and monitoring/kube-prometheus-stack (§1.2)

# Events in the last hour (timing + which objects, reason DriftDetected)
kubectl get events -A --field-selector reason=DriftDetected -o custom-columns=TS:.lastTimestamp,NS:.metadata.namespace,HR:.involvedObject.name,MSG:.message --sort-by=.lastTimestamp
```

Store each snapshot on the ops DB so it outlives this file: on day 1 create
`source runbooks/lib/sweep-pg-dsn.sh && sweep_pg_dsn_up && .venv/bin/python3 runbooks/policy-cli.py finding add --title 'helm drift inventory (warn-mode soak)' --severity monitor --component flux/helm-controller --plan helm-drift-detection --section plan --detail-file /private/tmp/claude-501/helm-drift-detection/drift-day1.md; sweep_pg_dsn_down`
(ONE Bash call: the DSN does not survive into the next call, and a missing DSN fails closed with a well-formed denial),
then append with `finding detail <id> --detail-file` each day; the finding
id goes into `finding_refs:` of this plan on the day-1 edit. The 7-day export
is the input to §3.2.

Also watch the cost of looking: helm-controller now dry-run-applies every
object of every release each interval.

```bash
kubectl top pod -n flux-system -l app=helm-controller     # pre-P1 2026-09-14: 8m CPU / 100Mi against limits 1 CPU / 1Gi
```

#### 3.1.4 Exporting the per-object diff — read exactly what the controller reads

The condition message names the objects and the kind of change but not the
field. The §2.1 script already produces the full-cluster answer
(`grep '^DIFF' /private/tmp/claude-501/helm-drift-detection/hr-ssa-gate.tsv`). For one named object, the same
comparison by hand — server-side dry-run of the stored document, diffed
against the live object with `managedFields` and `status` stripped:

```bash
NS=<ns>; REL=<helmrelease>; KIND=<Deployment>; NAME=<object>
helm get manifest "$REL" -n "$NS" | python3 -c "
import sys,yaml
k=sys.argv[1]; n=sys.argv[2]
for d in yaml.safe_load_all(sys.stdin):
    if d and d.get('kind')==k and d['metadata']['name']==n: print(yaml.safe_dump(d))" "$KIND" "$NAME" \
  | kubectl apply --server-side --dry-run=server --field-manager=helm-controller --force-conflicts -n "$NS" -o json -f - \
  | python3 -c "import sys,json,yaml;d=json.load(sys.stdin);d.pop('status',None);[d['metadata'].pop(k,None) for k in ('managedFields','resourceVersion','generation','uid','creationTimestamp')];print(yaml.safe_dump(d,sort_keys=True))" > /tmp/want.yaml
kubectl get "$KIND" "$NAME" -n "$NS" -o json \
  | python3 -c "import sys,json,yaml;d=json.load(sys.stdin);d.pop('status',None);[d['metadata'].pop(k,None) for k in ('managedFields','resourceVersion','generation','uid','creationTimestamp')];print(yaml.safe_dump(d,sort_keys=True))" > /tmp/live.yaml
diff -u /tmp/live.yaml /tmp/want.yaml
```

Read the output as: `+` lines under `spec` are what correction WOULD write,
`-` lines under `spec` are what it would remove. Two artefact classes are NOT
drift and must be ignored when reading: (a) `meta.helm.sh/release-name`,
`meta.helm.sh/release-namespace` and `app.kubernetes.io/managed-by: Helm`
showing as removed — helm-controller stamps them onto the rendered object
before diffing, the bare `helm get manifest` document lacks them; (b) any
`-` line under `metadata.labels` / `metadata.annotations` — foreign labels
and annotations survive a forced server-side apply, and `jsondiff` compares
those two maps for add/replace only. Everything else is what the `Drifted`
condition is talking about.

### 3.2 Phase 2 — ignore rules from the inventory + retire the known day-1 diffs (attended)

#### 3.2.0 Retire the two guaranteed diffs on our terms, while still in `warn`

Neither can be fixed in git: the stored manifest ALREADY carries the field in
both cases, and Helm's three-way merge only sends fields that changed between
two revisions — no values edit makes it re-send an unchanged one. The live
objects lack the field because the CRD pruned it at the time (GpuDevicePlugin,
rev 4) or it was never re-asserted (Prometheus). The remaining options are (a)
ignore rules — wrong, both are real, benign-to-fix desired state — or (b) do
the correction by hand, in an attended window, in warn mode, with the exact
command helm-controller would run. **(b) is the decision.** It must NOT be
left to P3's first reconcile, because the GpuDevicePlugin correction rolls the
GPU DaemonSet on all three nodes (§1.2) and P3's contract is "corrects
nothing".

```bash
# (1) GpuDevicePlugin — WILL roll daemonset/kube-system/intel-gpu-plugin-intel-gpu-plugin (3 nodes)
DS=intel-gpu-plugin-intel-gpu-plugin
kubectl get ds $DS -n kube-system -o jsonpath='{.metadata.generation}'; echo      # note it (6 on 2026-09-14)
kubectl get pods -A -o json | python3 -c "
import sys,json
print([p['metadata']['namespace']+'/'+p['metadata']['name'] for p in json.load(sys.stdin)['items']
  if any(k.startswith('gpu.intel.com/') for c in p['spec']['containers'] for k in ((c.get('resources') or {}).get('limits') or {}))])" > /tmp/gpu-claimants-before.txt
helm get manifest intel-device-plugin-gpu -n kube-system | python3 -c "
import sys,yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d['kind']=='GpuDevicePlugin': print(yaml.safe_dump(d))" \
  | kubectl apply --server-side --field-manager=helm-controller --force-conflicts -n kube-system -f -
# -> gpudeviceplugin.deviceplugin.intel.com/intel-gpu-plugin serverside-applied
kubectl rollout status ds/$DS -n kube-system --timeout=5m                          # 3/3 updated
kubectl get ds $DS -n kube-system -o jsonpath='{.spec.template.spec.containers[0].args}'; echo   # now contains -monitoring-mode=single
diff /tmp/gpu-claimants-before.txt <(kubectl get pods -A -o json | python3 -c "...same one-liner...")   # identical: no claimant restarted
kubectl get node -o json | python3 -c "
import sys,json;print({n['metadata']['name']:n['status']['allocatable'].get('gpu.intel.com/i915') for n in json.load(sys.stdin)['items']})"   # all 3 nodes re-advertise i915

# (2) Prometheus — benign add, no rollout expected
kubectl get sts prometheus-kube-prometheus-stack -n monitoring -o jsonpath='{.metadata.generation}'; echo   # note it (2 on 2026-09-14)
helm get manifest kube-prometheus-stack -n monitoring | python3 -c "
import sys,yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d['kind']=='Prometheus': print(yaml.safe_dump(d))" \
  | kubectl apply --server-side --field-manager=helm-controller --force-conflicts -n monitoring -f -
kubectl get prometheus kube-prometheus-stack -n monitoring -o jsonpath='{.spec.paused}'; echo    # false
kubectl get sts prometheus-kube-prometheus-stack -n monitoring -o jsonpath='{.metadata.generation}'; echo   # UNCHANGED

# (3) Watch both HRs clear within one interval (or `flux reconcile helmrelease <hr> -n <ns>` to hurry):
# (two commands: with two -n flags kubectl uses the LAST one, and the first name is NotFound)
kubectl get helmrelease intel-device-plugin-gpu -n kube-system -o jsonpath='{.status.conditions[?(@.type=="Drifted")].reason}{"\n"}'   # NoDriftDetected
kubectl get helmrelease kube-prometheus-stack -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Drifted")].reason}{"\n"}'      # NoDriftDetected
```

This is a direct cluster write, sanctioned here because it is byte-for-byte
the write helm-controller will perform in P3, moved to a moment of our
choosing; the desired state in git is unchanged and the next Helm upgrade of
either release would have done the same. Record both in the inventory
finding with the DaemonSet generation before/after.

#### 3.2.1 The ignore rules

Edit the SAME nested patch: keep `mode: warn`, add `ignore:` **inside the
JSON6902 `value:`** (the op, path and target lines do not change — never
convert it back to a strategic-merge document, §1.5). **Only rules
with an inventory line survive.** The catalogue below gives the concrete
syntax for each known mutator (all shapes accepted by a server-side dry-run of
a HelmRelease on v1.6.3, 2026-09-14); JSON Pointer per RFC 6901, `/` inside a
key escaped as `~1`.

```yaml
                - op: add
                  path: /spec/driftDetection
                  value:
                    mode: warn
                    ignore:
                      # B) kubectl rollout restart (nightly frigate-restart 02:30, docs-site-refresh 05:30,
                      #    and 32 helm-managed workloads that carry the stamp today).
                      #    APPLY ONLY IF the inventory shows this path — measured NOT drift (§1.2, 0 rows).
                      - paths: ["/spec/template/metadata/annotations/kubectl.kubernetes.io~1restartedAt"]
                        target: { kind: Deployment }
                      - paths: ["/spec/template/metadata/annotations/kubectl.kubernetes.io~1restartedAt"]
                        target: { kind: StatefulSet }
                      - paths: ["/spec/template/metadata/annotations/kubectl.kubernetes.io~1restartedAt"]
                        target: { kind: DaemonSet }
                      # C) Reloader. PREFERRED FIX is not a rule but a strategy switch (below);
                      #    with the annotations strategy the only mutation is this pod-template annotation:
                      - paths: ["/spec/template/metadata/annotations/reloader.stakater.com~1last-reloaded-from"]
                      # C') FALLBACK if the strategy is left at env-vars: JSON Pointer cannot select a
                      #    list item by name, so the whole env of container 0 is masked — a real env
                      #    drift on that container goes unseen. Scope it to Reloader-annotated objects.
                      # - paths: ["/spec/template/spec/containers/0/env"]
                      #   target:
                      #     kind: Deployment
                      #     annotationSelector: reloader.stakater.com/auto=true
                      # D) dashboard ConfigMaps — foreign annotations (sop-reload-test today).
                      #    APPLY ONLY IF observed; measured NOT drift. Prefer deleting the stray
                      #    annotation over masking all annotations on 30 ConfigMaps.
                      # - paths: ["/metadata/annotations"]
                      #   target:
                      #     kind: ConfigMap
                      #     labelSelector: grafana_dashboard=1
                      # E) webhook caBundle written by cainjector / patch jobs / the operator itself.
                      #    Index per webhook entry (ECK has 16). APPLY ONLY IF observed; the four
                      #    injector-fed charts render NO caBundle (measured not drift), otel-operator
                      #    renders its own and is byte-equal today.
                      # - paths: ["/webhooks/0/clientConfig/caBundle", "/webhooks/1/clientConfig/caBundle"]
                      #   target: { kind: ValidatingWebhookConfiguration }
                      # - paths: ["/webhooks/0/clientConfig/caBundle"]
                      #   target: { kind: MutatingWebhookConfiguration }
                      # A) HPA-managed replicas — DELIBERATELY ABSENT. No HPA exists (premise
                      #    no-hpa-exists), and a manual `kubectl scale` is drift we WANT reverted;
                      #    that is why §3.4 exists. If an HPA is ever added, add exactly:
                      # - paths: ["/spec/replicas"]
                      #   target:
                      #     kind: Deployment
                      #     name: <the autoscaled deployment>
                      # NOT a rule: /spec/monitoringMode (GpuDevicePlugin) and /spec/paused (Prometheus)
                      # are real desired state, retired by hand in §3.2.0.
```

**C) Reloader strategy switch** (only if the inventory shows `STAKATER_*`
env drift on any of the **10 Helm-managed** injected Deployments —
`ai/openclaw`, `databases/superset`, `databases/superset-celerybeat`,
`databases/superset-worker`, `kube-system/authentik-server`,
`kube-system/authentik-worker`, `network/cloudflared`, `office/affine`,
`office/nextcloud`, `office/sure-pg`; the three other injected Deployments —
`monitoring/edot-collector`, `office/nextcloud-whiteboard`,
`office/scan-inbox-validator` — are NOT HelmRelease-owned and are outside
drift detection entirely): in
`kubernetes/apps/kube-system/reloader/app/helmrelease.yaml` (chart 2.2.16) set

```yaml
    reloader:
      reloadStrategy: annotations   # was `default` (= env-vars). Upstream: "preferred in GitOps
                                    # environments to prevent config drift in tools like ArgoCD or Flux"
```

Effects to know: only Reloader's own pod restarts; existing `STAKATER_*` env
vars stay on the 10 Deployments until their next rollout (they are foreign
fields, not drift); future reloads stamp the annotation instead. Same commit
as the P2 rule, since the rule and the strategy are one decision.

Land it through §3.0.0 steps 4-8 with the P2 value: snapshots B2, edit, then
`parent-gate.py <HEAD ks.yaml> kubernetes/flux/cluster/ks.yaml '<P2 value JSON>'`
and `render-gate.py --patch json6902 --value '<P2 value JSON>'` both PASS
(the P2 shape was dry-run 2026-09-28: PASS), `git commit --only` of `ks.yaml`
(+ the reloader HR if switched — then rev-gate EXPLAINS reloader's upgrade by
that commit, and values-gate runs as `compare B2 --expect kube-system/reloader`,
which prints its change as EXPECTED and fails if it did NOT change), push, rev-gate + values-gate. This plan's `generated:` is
refreshed in the close-out commit. Then **soak again until the §2.3 gate is clean** — a
rule set that still leaves `Drifted=True` somewhere is not finished.

### 3.3 Phase 3 — `mode: enabled` cluster-wide (attended)

1. Run §2.0 and **§2.3 in full**; the printed inventory must be empty.
   **What WILL be corrected on the first reconcile is exactly that list** —
   every `Drifted=True` object not covered by a P2 ignore rule; the contract
   is that it is empty, and if it is not, the plan stops here.
2. Edit: `mode: warn` -> `mode: enabled` inside the JSON6902 `value:`. Nothing
   else in `ks.yaml`. In this plan: `generated: "<today>"` (close-out commit).
3. §3.0.0 steps 5-8 with the P3 value: parent-gate + render-gate with
   `--value '<P3 value JSON>'` PASS; `git commit --only kubernetes/flux/cluster/ks.yaml`;
   push; `flux reconcile kustomization flux-system --with-source`; rev-gate +
   values-gate PASS (a values change in P3 would be an upgrade AND a correction
   baseline shift in the same reconcile).
4. For the first full HR interval (30 min) watch, in this order:

```bash
kubectl get events -A --field-selector reason=DriftCorrectionFailed --no-headers | wc -l   # must stay 0
kubectl get events -A --field-selector reason=DriftCorrected -o custom-columns=TS:.lastTimestamp,NS:.metadata.namespace,HR:.involvedObject.name,MSG:.message
# EXPECTED: empty — the gate said there was nothing to correct. ANY line here is a
# correction the inventory missed; read its message before anything else, because
# a corrected pod-template field is a rollout that just happened.
kubectl get pods -A --field-selector status.phase!=Running,status.phase!=Succeeded --no-headers | wc -l
kubectl get ds intel-gpu-plugin-intel-gpu-plugin -n kube-system -o jsonpath='{.metadata.generation}'   # unchanged from §3.2.0
```

5. Positive control (§4.3) — prove correction works on a stateless target.
6. Mark `status: executed`, delete this file in the same commit that
   retires it (README rule), and paste the §6.2 paragraph into the two named
   plans in that commit (with the nocodb-specific insertion described there).

### 3.4 Protocol for in-window scale-to-0 once Phase 3 is live

From Phase 3 on, `kubectl scale deploy/<x> --replicas=0` on a Helm-managed
Deployment is reverted within one HR interval (<= 30 min; 5 min on the two
5-minute HRs) with a `DriftCorrected` event — mid-dump, mid-restore, whenever
the interval lands. Every plan that quiesces an app by hand must therefore:

```bash
# BEFORE the scale — take the release out of reconciliation:
flux suspend helmrelease <hr> -n <ns>            # spec.suspend=true; the SOP-sanctioned live toggle
kubectl scale deploy/<x> -n <ns> --replicas=0
# ...do the work...
kubectl scale deploy/<x> -n <ns> --replicas=1    # or leave it: resume corrects it
flux resume helmrelease <hr> -n <ns>             # triggers a reconcile; drift correction restores replicas
```

The house-preferred alternative stays valid and is stronger: make
`replicas: 0` the desired state in git for the duration (both scale plans
already describe it). Either way, **a plan that says `kubectl scale` without
`flux suspend` is wrong after Phase 3**, and §2.3 step 3 refuses to run Phase
3 while any HR is suspended for someone else's work.

## 4) Verification

Flux Ready / pods healthy are the floor for every phase; the assertions below
are the ones that would fail with the thing configured-but-inert.

### 4.0 Phase 0

```bash
# Shape: both upgraded and Ready (two commands — with two -n flags kubectl uses the LAST one
# and reports anythingllm NotFound). The three deploy lines below are NOT gates: the live
# pod templates already lacked both keys before P0 (measured 2026-09-26), so they print the
# same before and after.
kubectl get helmrelease anythingllm -n ai -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} rev={.status.history[0].version}{"\n"}'
kubectl get helmrelease jellyfin -n media -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} rev={.status.history[0].version}{"\n"}' 
kubectl get deploy anythingllm -n ai -o jsonpath='{.spec.strategy.type} {.spec.template.spec.strategy}'; echo   # "Recreate " (pod-level field ABSENT)
kubectl get deploy jellyfin -n media -o jsonpath='{.spec.template.spec.securityContext}'; echo                   # fsGroup/runAsGroup/runAsUser only
kubectl get deploy jellyfin -n media -o jsonpath='{.spec.template.spec.containers[0].securityContext.privileged}'; echo   # true (container unchanged)

# CONTENTS ASSERTION (THE P0 GATE): the STORED manifests (what drift detection reads) pass a
# server-side dry-run — `python3 /private/tmp/claude-501/helm-drift-detection/ssa-gate-check.py` prints SSA-GATE PASS (§3.0.0 step 6;
# its FAIL on the identical command before P0 is the known-bad demonstration, step 3).
# The scoped loop below is a diagnostic only: an empty `helm get manifest` prints nothing and
# would read as "no FAIL".
for r in ai:anythingllm media:jellyfin; do helm get manifest ${r##*:} -n ${r%%:*} | python3 -c "
import sys,yaml,subprocess
ns=sys.argv[1]
for d in yaml.safe_load_all(sys.stdin):
    if not d: continue
    p=subprocess.run(['kubectl','apply','--server-side','--dry-run=server','--field-manager=helm-controller','--force-conflicts','-n',(d['metadata'].get('namespace') or ns),'-f','-'],input=yaml.safe_dump(d),capture_output=True,text=True)
    print('FAIL' if p.returncode else 'ok', d['kind'], d['metadata']['name'], p.stderr.strip()[:120])" ${r%%:*}; done   # no FAIL
# App probes: anythingllm and jellyfin answer on their HTTPRoutes (HTTP 200/302 via the internal gateway);
# jellyfin: a hardware-transcode still works (container securityContext unchanged) — operator spot check.
# Then the full §2.1 run through the wrapper: SSA-GATE PASS across all 126.
```

### 4.1 Phase 1

```bash
# CONTENTS ASSERTION 0 (premise all-helmreleases-ready, RE-CHECKED AFTER PROPAGATION): every
# HelmRelease reconciled its new generation successfully — the dry-run diff step did not
# reject any stored manifest. Exactly one line, "126 True" (or the premise range).
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' | sort | uniq -c
python3 runbooks/plan-premises.py helm-drift-detection            # all 10 PASS, again, AFTER P1

# Shape: the field landed everywhere
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.driftDetection.mode}{"\n"}{end}' | sort | uniq -c   # "126 warn" (no blank line)
kubectl get kustomization -n monitoring grafana -o jsonpath='{.spec.patches[0].patch}' | grep -c 'op: add'        # 1 (the SMP shape of 2026-09-26 prints 0)

# CONTENTS ASSERTION 1: detection actually RAN on every release — a `Drifted` condition
# (True OR False) exists on all of them. Measured by the count of HRs carrying the
# condition, compared to the HR count. A release with no condition was never compared.
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Drifted")].reason}{"\n"}{end}' | sort | uniq -c
# expect: only DriftDetected / NoDriftDetected lines, summing to 126, no empty line;
#         DriftDetected == 2 on day 1 (§1.2), and §3.1.3 names exactly those two HRs.

# CONTENTS ASSERTION 2: no Helm upgrade was triggered by the spec change — every
# release revision is identical to the §2.0 baseline (a rolled-out cluster with
# "warn" is the wrong outcome even if everything is Ready).
python3 /private/tmp/claude-501/helm-drift-detection/rev-gate.py compare B --require-warn; echo "rc=$?"     # rc=0 REV-GATE PASS
# Scoped, not global: baseline B is taken after P0 and after the cluster settled, and a
# revision change is tolerated ONLY when a commit since B touched that release's own
# Kustomization path (printed as EXPLAINED — e.g. a concurrent session's bump). A change with
# no such commit is UNEXPLAINED and FAILS. Demonstrated 2026-09-26 against a doctored
# baseline: 2 UNEXPLAINED -> rc=1, and the live intel-device-plugin / mqttx-web bumps of the
# main run -> EXPLAINED by their commits. Also asserts assertion 0 (Ready=True on all) with
# observedGeneration == generation, so a stale Ready cannot pass it.

# CONTENTS ASSERTION 2b (added 2026-09-28): no HelmRelease spec changed except driftDetection —
# the direct measurement of the 2026-09-26 failure (null leaves removed from spec.values):
.venv/bin/python3 /private/tmp/claude-501/helm-drift-detection/values-gate.py compare B; echo "rc=$?"   # rc=0 VALUES-GATE PASS
# Shown able to fail in §3.0.0 step 3c; on 2026-09-26 it would have printed 11 "(removed)" rows.

# CONTENTS ASSERTION 3 (positive control, warn does not correct): scale a stateless,
# PVC-less, helm-managed Deployment UP by one and wait one reconcile.
kubectl scale deploy/docs-site -n monitoring --replicas=2         # docs-site: replicas: 1 rendered, RollingUpdate, no PVC
flux reconcile helmrelease docs-site -n monitoring
kubectl get helmrelease docs-site -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Drifted")].message}'; echo
kubectl get deploy docs-site -n monitoring -o jsonpath='{.spec.replicas}'; echo    # MUST still be 2
kubectl scale deploy/docs-site -n monitoring --replicas=1
# expect: message names Deployment docs-site; replicas stayed 2 => detected, not corrected.
```

### 4.2 Phase 2

```bash
# §3.2.0 landed: both known diffs are gone from the API-side inventory
python3 /private/tmp/claude-501/helm-drift-detection/hr-ssa-gate.py > /private/tmp/claude-501/helm-drift-detection/hr-ssa-gate-p2.tsv; grep '^FAIL\|^DIFF' /private/tmp/claude-501/helm-drift-detection/hr-ssa-gate-p2.tsv   # empty
kubectl get ds intel-gpu-plugin-intel-gpu-plugin -n kube-system -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled}'; echo   # 3/3

# Shape: the rules rendered on a real HR
kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.driftDetection.ignore}' | python3 -m json.tool

# CONTENTS ASSERTION: the rule set silences exactly the legitimate mutators and
# NOTHING ELSE. Two halves, both required:
#  (a) every object that was Drifted=True for a catalogued reason now reads NoDriftDetected —
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}{" "}{.status.conditions[?(@.type=="Drifted")].reason}{"\n"}{end}' | grep -vc NoDriftDetected   # 0
#  (b) an UN-ignored drift is still seen (the §4.1 positive control repeated verbatim:
#      docs-site to 2 replicas -> Drifted=True -> back to 1). If (a) is 0 and (b) is
#      blind, the rule set over-masked and must be narrowed.
```

### 4.3 Phase 3

```bash
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.driftDetection.mode}{"\n"}{end}' | sort | uniq -c   # "126 enabled"
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' | sort | uniq -c   # "126 True"

# CONTENTS ASSERTION 1: the first enabled reconcile corrected NOTHING (gate honesty):
kubectl get events -A --field-selector reason=DriftCorrected --no-headers | wc -l            # 0 for the first 30 min
kubectl get events -A --field-selector reason=DriftCorrectionFailed --no-headers | wc -l     # 0

# CONTENTS ASSERTION 2: correction really happens — the VALUE, not the event:
kubectl scale deploy/docs-site -n monitoring --replicas=2
flux reconcile helmrelease docs-site -n monitoring
sleep 30; kubectl get deploy docs-site -n monitoring -o jsonpath='{.spec.replicas}'; echo   # MUST be 1 again
kubectl get events -n monitoring --field-selector reason=DriftCorrected,involvedObject.name=docs-site --no-headers | wc -l   # >= 1
```

## 5) Rollback

Each phase is one commit; each rollback is `git revert` of that commit, and
takes effect through the normal reconcile (P0: a Helm upgrade back; P1-P3: the
three-hop propagation in §1.3).

```bash
git revert --no-edit <phase-commit-sha>
git show --stat HEAD                                  # exactly the phase's files
git push
flux reconcile kustomization flux-system --with-source
# Confirm the cluster is back:
kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.driftDetection.mode}{"\n"}{end}' | sort | uniq -c
#   after P1 revert: one blank line x126 (field gone)   after P2 revert: "126 warn", no ignore
#   after P3 revert: "126 warn"
kubectl get kustomization -n flux-system cluster-apps -o jsonpath='{.spec.patches[*].target.labelSelector}'   # P1 revert: only the substitution selector
```

Per-phase notes:

- **P0 revert:** restores the two old values blocks -> Helm upgrade -> one
  more `Recreate` restart each; the stored manifests are SSA-invalid again,
  so P1 must NOT run until the fix is re-landed (the §2.1 gate says so). If
  only one app misbehaves, revert that file alone. The anythingllm
  Deployment-level `Recreate` is present in both states (proven §3.0.1).
- **P1 revert (re-planned 2026-09-28):** `git revert --no-edit <P1 sha>` —
  one file, `kubernetes/flux/cluster/ks.yaml`. Confirm: `values-gate.py compare B`
  -> PASS (the revert removes only `spec.driftDetection`, which the gate
  ignores) and `kubectl get helmrelease -A -o jsonpath='{range .items[*]}{.spec.driftDetection.mode}{"\n"}{end}' | sort -u`
  -> one empty line. If step 8 had already caught upgrades, the revert
  re-upgrades those releases back to the git values (2026-09-26: rev 12/31/23)
  — expected; `helm get values -n <ns> <rel> -o json` then shows the null leaves
  back (§1.5 table).
  `Drifted` conditions linger on HR status until each HR's
  next reconcile, then disappear (the field is unset). Harmless; do not chase
  them. An HR that went `Ready=False` in P1 recovers on the revert as well —
  but the right fix is its manifest, not the revert.
- **P2 revert:** if the Reloader strategy was switched in the same commit, the
  revert also restores env-vars; Reloader's own pod restarts, nothing else.
  §3.2.0's two hand re-applies are NOT reverted by any git action: they wrote
  the desired state that was already in the manifest, so "rollback" would mean
  removing a field the next Helm upgrade re-asserts anyway. Leave them.
- **P3 revert:** stops future corrections; it does **not** un-correct
  anything already patched. That is why §2.3 gates on an empty inventory —
  the rollback budget for P3 is "stop", not "undo". Anything P3 corrected
  in error is restored by fixing the desired state in git.
- **Emergency stop for a single release** without a revert:
  `flux suspend helmrelease <hr> -n <ns>` (helm-controller skips suspended
  objects entirely), or label its `ks.yaml` with the §3.1.1 opt-out and push.

## 6) Interference notes

### 6.1 Reloader (`kube-system/reloader`, chart 2.2.16, env-vars strategy)

10 **Helm-managed** Deployments carry `STAKATER_*` env vars today
(`ai/openclaw`, `databases/superset`, `databases/superset-celerybeat`,
`databases/superset-worker`, `kube-system/authentik-server`,
`kube-system/authentik-worker`, `network/cloudflared`, `office/affine`,
`office/nextcloud`, `office/sure-pg`); three more (`monitoring/edot-collector`,
`office/nextcloud-whiteboard`, `office/scan-inbox-validator`) carry them but
are not HelmRelease-owned, so drift detection never looks at them. Measured
NOT drift (§1.2, 0 rows), but if Phase 1 shows it, Phase 2 **must** handle it
before Phase 3 — in `enabled` mode a correction that strips the env var is a
rollout of that Deployment, and the next Secret change re-injects it: a
restart loop on `authentik-server`, `nextcloud`, `openclaw` and friends, every
interval. The strategy switch (§3.2 C) is the fix; the env-pointer rule is
the fallback.

### 6.2 The two open plans that scale Helm-managed workloads by hand

`bitnamilegacy-exit-nextcloud-db` (status blocked) and `nocodb-2026.09.0`
(status draft) both run `kubectl scale ... --replicas=0` inside their window.
After Phase 3 that scale is reverted within one HR interval. They do not
conflict with **this** plan's windows (P0-P2 change nothing they touch), but
their own steps are wrong from P3 on.

- **`nocodb-2026.09.0`: the scale-to-0 is in its ROLLBACK block (§5, lines
  339-347)**, fencing the pod between the `git revert` and the dump restore.
  Insert `flux suspend helmrelease nocodb -n databases` immediately BEFORE
  `kubectl scale deploy -n databases nocodb --replicas=0` (line 339), and
  `flux resume helmrelease nocodb -n databases` AFTER the restore is verified
  and `--replicas=1` (line 347) is back — otherwise the correction un-fences
  nocodb mid-restore and the old code boots against a half-restored schema.
  Note the interplay with the revert: `flux resume` triggers the reconcile
  that applies the reverted (2026.08.2) desired state, which is what you want
  at that point and not before.
- **`bitnamilegacy-exit-nextcloud-db`**: its preferred hold is already
  `replicaCount: 0` in git (line ~355), which is drift-proof; the fallback
  `kubectl scale` path (lines 558, 736, 965, 979) needs the generic paste
  below. Its own note that suspending the Kustomization alone is not enough
  stays true — the HelmRelease is the object to suspend.

Paste this into each plan's §6, in the commit that retires this file:

> **Helm drift correction is ON cluster-wide (plan `helm-drift-detection`,
> executed <date>).** `kubectl scale --replicas=0` on a Helm-managed
> Deployment is now reverted by helm-controller within one interval (30 min;
> `DriftCorrected` event) — the old "Flux drift-corrects it back" warning is
> now literally true, not only on the next upgrade. Run
> `flux suspend helmrelease <hr> -n <ns>` BEFORE the scale and
> `flux resume` after, or make `replicas: 0` the desired state in git for
> the duration (already the preferred path in this plan). Never leave an HR
> suspended past the window: a suspended release is invisible to drift
> detection and to Step 0 safe-updates.

`superset-pg-cutover` carries the same warning but is `executed`; the
not-yet-written `superset-pg-decommission` inherits this note.

### 6.3 Nightly rollout-restart CronJobs

`home-automation/frigate-restart` (02:30) and `monitoring/docs-site-refresh`
(05:30 Berlin) run `kubectl rollout restart` on Helm-managed Deployments,
stamping `kubectl.kubernetes.io/restartedAt`. Measured NOT drift (§1.2). If
Phase 1 shows it anyway, rule B in §3.2 is mandatory before Phase 3:
otherwise every correction would strip the annotation — a **second** rollout
of frigate at ~03:00 (inside the Longhorn backup window) and of docs-site at
~06:00, daily. The nightly window (03:30) sits between the two; both restarts
are visible in the inventory by day 2.

### 6.4 `grafana-chart-13.2.3` (pending, draft) and Step 0 safe-updates

A Helm upgrade rewrites every object of its release and resets the drift
baseline; it is compatible with every phase and runs in any window. It is in
`conflicts_with` purely for attribution: in the **same** window as Phase 3 a
grafana rollout has two candidate causes. The sequencer enforces that now;
this paragraph is the reason. Step 0 safe-updates bump Helm revisions — take
the §2.0 revision baseline *before* Step 0 or exclude what Step 0 touched from
the §4.1 diff.

### 6.5 `talos-1.14.0` (awaiting-go, sun-attended 2026-09-27)

Requires the whole sun-attended slot; Phase 3 cannot share it —
`conflicts_with` makes that machine-enforced. A node roll does not edit
Helm-managed specs, so drift state is unaffected by the roll, and `warn` mode
during the roll is fine. Keep Phase 3 off that Sunday and off the week before
it — an unexplained correction on `cilium` or `longhorn-manager` (both
Helm-managed, both carry a `restartedAt` stamp) is not something to debug on
a reboot day. P2's GPU DaemonSet roll (§3.2.0) should also not share the
Talos Sunday: a plugin re-registration during a node drain is one more
variable.

### 6.7 Flux version changes and other `ks.yaml` editors (added 2026-09-28)

The P1 safety argument rests on how kustomize applies a JSON6902 vs a
strategic-merge patch, measured with flux CLI v2.9.0 against
kustomize-controller v1.9.4. `flux-fleet-0.60.0` (operator/instance bump) and
any distribution change can move that; both are now in `conflicts_with`, and
the premises `flux-distribution-is-2.9` / `kustomize-controller-is-v1.9` (+ the step-1 CLI check) refuse a stale
proof. `flux-reconciler-impersonation` edits the same file with
`yq -i` — a full re-serialisation of `ks.yaml`; if it lands between P1 and
P3, re-run parent-gate on its result (the parsed comparison tolerates a
reformatted block scalar, a changed op list does not). If it lands BEFORE P1
(its window is sun-attended:2026-10-11), `p1-edit.py`'s end-of-file anchor
refuses ("file changed since review") — fail-closed, but P1 then needs its
anchor re-derived and re-reviewed. Preferred order: P1 first (a weekday run
before 2026-10-03).

### 6.6 What Phase 3 changes for everyone, permanently

From Phase 3 on, the in-pod-edit exception in `CLAUDE.md` still applies to
PVC-held config (not Kubernetes objects), and every "quick" `kubectl edit`
of a Helm-managed object is undone within 30 minutes. That is the intended
outcome; it must be in the next `docs/sops/application-update.md` revision
(§7 troubleshooting: "my hot-fix disappeared") — owed in the retirement
commit.

## 7) Duration and window class

| Phase | In-window work | est_min | Window class | Why that class |
|---|---|---|---|---|
| 0 — SSA-clean the two charts | 2 file edits, `helm template` + `kustomize build` + dry-run proofs, commit, 2 x Recreate rollout, §4.0 | 20 | **nightly** (unattended-safe with operator GO) or sat-attended | same blast radius as any image bump of these two apps; git revert; no shared infra |
| 1 — warn | §3.0.0: known-bad demos (~1 min), §2.1 SSA gate (~3 min), snapshots, edit, parent+render gates (~1 min), commit, propagate, rev+values gates, §4.1 | 30 | **dedicated on-demand run or the LAST plan of an attended window, operator GO** (was "nightly, unattended-safe" — that claim failed on 2026-09-26) | controller only reads once §2.1 is clean; the pre-commit gates now prove 0 value changes; but it must be the day's last HelmRelease change for the attribution gates, which the nightly scheduler cannot guarantee |
| soak | >= 7 calendar days, snapshots per nightly window + sweep | 0 | — | inventory must span both weekend windows, Step 0 upgrades, both restart CronJobs |
| 2 — retire day-1 diffs + ignore rules | §3.2.0 two hand re-applies (GPU DaemonSet roll ~5 min + checks), rules from inventory, prove render, commit, §4.2 (+ Reloader switch if needed) | 40 | **sat-attended / sun-attended** (not nightly: the DaemonSet roll) | still warn; rule authoring is human work done BEFORE the window from the exported inventory |
| soak | until §2.3 is clean, min 2 nightly windows | 0 | — | proves the rule set, not the calendar |
| 3 — enabled | §2.3 gate (incl. 3-min API-side run), edit, commit, propagate, **30-min watch**, §4.3 | 60 | **sat-attended / sun-attended, operator present** | first correcting reconcile is cluster-wide; rollback is "stop", not "undo" |

Total in-window: 140 min across four windows; `est_duration_min` in the
frontmatter is the worst single phase (P3, 60) because that number is what
the OVER-TIME/TIGHT check consumes per assigned window. Never collapse the
soaks into a daily nightly cadence (`maintenance-windows.yaml` soak rule).

## 8) Open items — could not be determined read-only

1. **Whether any of the measured-no rows in §1.2 drift over 7 days** (they
   did not in a single 2026-09-14 snapshot) is exactly what Phase 1
   measures; the plan is written so that either answer is fine, but the
   Phase 2 rule diff cannot be pre-written beyond §3.2.0.
2. **helm-controller resource headroom** under 124 x per-interval dry-run
   applies — measure `kubectl top` before/after P1 (§3.1.3; baseline 8m /
   100Mi against limits 1 CPU / 1Gi). If CPU throttles against its limit,
   raise the limit in the flux-instance/operator values rather than
   lengthening HR intervals.
3. **Durable event sink.** `DriftDetected` events are 1h-TTL. The
   otel-operator daemon forwards `k8s_objects` Event logs to Elasticsearch
   (edot `transform/strip-k8s-managedfields` exists for exactly those), so a
   7-day query on `reason: DriftDetected` should be possible there; the data
   stream name was not verified from this seat. The `Drifted` condition
   snapshot in §3.1.3 does not depend on it.
4. **`finding_refs`** — populated on day 1 of the soak with the inventory
   finding id (§3.1.3); the frontmatter field is left empty on purpose until
   that record exists.
5. **Why the live Prometheus CR lacks `paused`** was not traced to a
   specific revision (helm-controller's managedFields do not own it; the
   field has been identical across revisions since at least rev 38). The
   mechanism (3-way merge never re-sends an unchanged field) is sufficient
   for the plan; the history is not.
7. **CLI-vs-controller kustomize equivalence is inferred, not proven for
   JSON6902.** The local `flux build` reproduced the controller's SMP null
   drop exactly (§1.5), which is strong evidence the two share the relevant
   kustomize code; that the controller also keeps the nulls under JSON6902 is
   observed only after the push. Supporting evidence (plan review 2026-09-28):
   flux2 CLI v2.9.0 and kustomize-controller v1.9.4 pin the same
   kustomize/api + kyaml v0.21.1, and fluxcd/pkg/kustomize 1.35.1 -> 1.35.4
   changes only image-merge / OpenAPI-reset code, not patch or null handling.
   The post-apply values-gate and rev-gate remain anyway, and §5's revert is
   one file.
6. **The intel-gpu-plugin DaemonSet roll is inferred from operator source
   (v0.36.0 `getPodArgs` / `UpdateDaemonSet`), not observed.** §3.2.0 records
   the generation before/after; if it does not move, the note in §1.2 is
   downgraded, nothing else changes.
