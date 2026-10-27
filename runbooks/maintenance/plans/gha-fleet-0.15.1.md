---
plan_id: gha-fleet-0.15.1
component: actions-runner-controller   # chart family: gha-runner-scale-set-controller (x2 HelmReleases) + gha-runner-scale-set (x3 HelmReleases)
pr: 415                               # Renovate "update ...gha-runner-scale-set-controller ( 0.15.0 → 0.15.1 )" (1 file:
                                      # arc-system/gha-runner-scale-set-controller/app/ocirepository.yaml). The OTHER half is
                                      # PR 414 "update ...gha-runner-scale-set ( 0.15.0 → 0.15.1 )" (2 files: ci-runner + arc-build
                                      # ocirepository.yaml). Both OPEN, CI green (Flate Render Gate pass) on 2026-10-24. This plan
                                      # lands ONE direct commit with all three files (SOP ci-runner §2c: lockstep, one commit) and
                                      # then closes both PRs as superseded (§3.5). Do NOT merge either PR on its own.
kind: chart
current: "0.15.0 (controller chart sha256:20a36921…, scale-set chart sha256:bdfdad17…; controller image ghcr.io/actions/gha-runner-scale-set-controller:0.15.0)"
target: "0.15.1"                      # controller chart sha256:c2497a6dedaaa723322abfe9ea2f5a81b9b8fbb90b38e45d7835b6c7629a3aae,
                                      # scale-set chart sha256:2ae7e43db61047aa3c4182e73c8f58ace35e796fa07d41b64fb3c39e81e1f365
                                      # (both re-derived with `helm pull` 2026-10-24; identical to the Renovate PR digests)
update_type: patch
risk: low                             # templates byte-identical (diff -r: only Chart.yaml + CRD validation on an unused field,
                                      # §1.2); controller tolerates same-minor skew (§1.3); no PVC/state; rollback = git revert.
est_duration_min: 30                  # pre-checks 5 · edit/commit/push 3 · Flux apply (controller ks wait:true, then runner ks)
                                      # ~8 · verification 10 · soak 4
needs_reboot: false
touches:
  namespaces: [arc-system, ci-runner, arc-build]
  resources:                          # every object verified to EXIST live 2026-10-24 (kubectl get)
    - ocirepository/gha-runner-scale-set-controller   # arc-system — EDITED (tag+digest); chart source of BOTH controller HRs
    - ocirepository/gha-runner-scale-set              # ci-runner — EDITED; chart source of the-ninth-banner-runners + -browser-runners
    - ocirepository/gha-runner-scale-set              # arc-build — EDITED; chart source of the-ninth-banner-build-runners
    - helmrelease/gha-runner-scale-set-controller     # arc-system → deployment/arc-controller rolls
    - helmrelease/gha-runner-scale-set-build-controller   # arc-system → deployment/arc-build-controller rolls
    - helmrelease/the-ninth-banner-runners            # ci-runner → autoscalingrunnerset/ninth-banner-k8s (labels only)
    - helmrelease/the-ninth-banner-browser-runners    # ci-runner → autoscalingrunnerset/ninth-banner-browser-k8s (labels only)
    - helmrelease/the-ninth-banner-build-runners      # arc-build → autoscalingrunnerset/ninth-banner-build-k8s (labels only)
    - autoscalinglistener/ninth-banner-k8s-59fd7c9b-listener          # arc-system — deleted + re-created by the controller
    - autoscalinglistener/ninth-banner-browser-k8s-59fd7c9b-listener  # arc-system — deleted + re-created
    - autoscalinglistener/ninth-banner-build-k8s-7b4779b7-listener    # arc-system — deleted + re-created
    - crd/autoscalingrunnersets.actions.github.com    # cluster-scoped, CreateReplace by both controller HRs
    - crd/autoscalinglisteners.actions.github.com
    - crd/ephemeralrunnersets.actions.github.com
    - crd/ephemeralrunners.actions.github.com
  shared: [monitoring, ci-runner, crds/actions.github.com, github-actions/the-ninth-banner]
                                      # monitoring = §4 reads Prometheus (PodMonitor arc-system/arc, ARC* alerts).
                                      # ci-runner = the CI node-capacity surface other ci-runner plans also declare.
                                      # github-actions = the private game repo's self-hosted job queue pauses ~1-2 min per
                                      # listener rebuild (queued jobs wait, nothing is lost).
depends_on: []
conflicts_with:
  # 2026-10-25: dead refs flux-distribution-2.9.6 and cilium-1.20.4 (executed/retired) pruned.
  # 2026-10-27: ci-gate-primary-control-rework (superseded, reviewer reject) pruned.
  - talos-linux-1.14.4                # node roll restarts every ARC pod; attribution of §4 impossible.
  - talos-power-tuning-ab             # measures CI load on ci-runner; a listener gap skews its CI baseline.
  - helm-drift-detection              # changes how helm-controller treats every HelmRelease (incl. these five).
  - flux-reconciler-impersonation     # changes WHO applies the arc-system/ci-runner/arc-build Kustomizations.
exclusive: false
security_ref: F-1fd1d6a0
capability_change: false              # same chart templates, same values, same runner pods; controller binary gains bug fixes only
                                      # (metrics-guard fix, rate-limit requeue, cleanup of never-used succeeded runners). No new
                                      # route, permission, RBAC, API, label or exposure.
rollback_class: git-revert            # nothing forward-only: no PVC, no DB, no stored CR uses the only CRD field whose validation
                                      # changed (measured 0/4 kinds, §1.2); a revert re-applies the 0.15.0 CRDs and images.
finding_refs: [F-5602ee2a, F-87d453b9, F-a2cff4a9, F-1fd1d6a0]            # `finding list --grep gha-runner` 2026-10-24: the AR-029 register row on the 0.15.0
                                      # CONTROLLER image (accepted as "already newest" — no longer true since 0.15.1 shipped
                                      # 2026-10-23). This bump is what moves it; whether the row clears is for the next sweep's
                                      # scan to MEASURE, not for this plan to claim. Detail stays on the record.
review: ready-for-go@2026-10-25   # plan-reviewer 2026-10-25 delta re-review: premises PASS, gates verified
status: vetted
window: nightly:2026-11-09   # AUTO-NIGHT class: no operator GO needed; Renovate PRs 414/415 are closed by the plan, never merged alone
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/ci-runner.md            # §2c "Upgrades": lockstep, one commit, re-derive digests
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-24"
premises:
  # Read-verb only. Each run live 2026-10-24 ~02:00Z and returned exactly the expected value.
  - id: controller-source-on-0150
    why: >-
      current: claims the controller chart source is pinned to 0.15.0 at the known digest. If someone already bumped it, the
      §3 sed matches nothing and the plan is a no-op (retire it instead).
    run: kubectl get ocirepository -n arc-system gha-runner-scale-set-controller -o jsonpath='{.spec.ref.tag} {.spec.ref.digest}'
    expect_exact: "0.15.0 sha256:20a369215b8c2ed981c4c0c75e56e6009564d51fffcbbd314d5da0ef82de253a"
  - id: scaleset-sources-on-0150
    why: >-
      Both scale-set chart sources (ci-runner, arc-build) must be on 0.15.0; a half-bumped state means someone merged PR 414
      alone and the lockstep premise of this plan is already broken (verify the controller, then just do the missing half).
    run: kubectl get ocirepository -A -o jsonpath='{range .items[?(@.metadata.name=="gha-runner-scale-set")]}{.metadata.namespace}={.spec.ref.tag} {end}'
    expect_exact: "arc-build=0.15.0 ci-runner=0.15.0"
  - id: scale-sets-running-on-0150
    why: >-
      The three AutoscalingRunnerSets carry version label 0.15.0 and are Running. The controller DELETES an ARS whose version
      label is a different MINOR than its build (IsVersionAllowed, §1.3); same-minor is the safety argument of this plan, so
      the starting label must be 0.15.x, and a set already Pending/Outdated must be fixed before, not during, the bump.
    run: kubectl get autoscalingrunnerset -A -o jsonpath='{range .items[*]}{.metadata.name}={.metadata.labels.app\.kubernetes\.io/version}/{.status.phase} {end}'
    expect_exact: "ninth-banner-build-k8s=0.15.0/Running ninth-banner-browser-k8s=0.15.0/Running ninth-banner-k8s=0.15.0/Running"
  - id: arc-helmreleases-ready
    why: >-
      All five ARC HelmReleases Ready before the change; an already-failing HR would mask (or be blamed on) this upgrade.
    run: kubectl get hr -A -o jsonpath='{range .items[?(@.spec.chartRef.name=="gha-runner-scale-set")]}{.metadata.name}={.status.conditions[?(@.type=="Ready")].status} {end}{range .items[?(@.spec.chartRef.name=="gha-runner-scale-set-controller")]}{.metadata.name}={.status.conditions[?(@.type=="Ready")].status} {end}'
    expect_exact: "the-ninth-banner-build-runners=True the-ninth-banner-browser-runners=True the-ninth-banner-runners=True gha-runner-scale-set-build-controller=True gha-runner-scale-set-controller=True"
  - id: crds-on-controller-gen-0220
    why: >-
      Baseline for the §4 CRD contents assertion: the live CRDs are the 0.15.0 ones (controller-gen v0.22.0). 0.15.1 ships
      v0.23.0; if this already reads v0.23.0 the §4 gate cannot fail and must be replaced.
    run: kubectl get crd autoscalingrunnersets.actions.github.com -o jsonpath='{.metadata.annotations.controller-gen\.kubebuilder\.io/version}'
    expect_exact: "v0.22.0"
---

# gha-fleet-0.15.1 — actions-runner-controller charts 0.15.0 → 0.15.1 (all halves, one commit)

## 1. Summary & why held

### 1.1 What changes

ARC is two charts wired to **three** OCIRepository sources. All three move together:

| Source (edited) | Chart | HelmReleases it feeds |
|---|---|---|
| `arc-system/gha-runner-scale-set-controller` | gha-runner-scale-set-controller | `arc-system/gha-runner-scale-set-controller` (watches `ci-runner`) **and** `arc-system/gha-runner-scale-set-build-controller` (watches `arc-build`, `chartRef` to the same source) |
| `ci-runner/gha-runner-scale-set` | gha-runner-scale-set | `ci-runner/the-ninth-banner-runners`, `ci-runner/the-ninth-banner-browser-runners` (no source of its own; it shares this one) |
| `arc-build/gha-runner-scale-set` | gha-runner-scale-set | `arc-build/the-ninth-banner-build-runners` |

The dispatch named two members (both controllers). Answer to "do the scale-set charts move in lockstep": **yes, and there are two
scale-set sources, not one** — `ci-runner` and `arc-build`. Renovate split them across PR 415 (controller) and PR 414 (both
scale-set sources). The in-file comments on both OCIRepositories and SOP `ci-runner.md` §2c require one commit.

### 1.2 Upstream evidence (release gha-runner-scale-set-0.15.1, published 2026-10-23)

"What's Changed", verbatim titles: *Fix inconsistent guards for scale set metrics registration and publishing* (#4566);
*Updates: runner to v2.338.0 / v2.338.1* (#4708, #4724 — chart default runner image only; we override the runner template,
so this does not reach our pods); *Bump Go to 1.27.3 and update Go dependencies* (#4725); *Remove succeeded ephemeral runners
that never ran a job from the service* (#4709); *Requeue rate-limited scale-set requests without client retries* (#4726).
No breaking change, no values change, no migration note.

Chart diff, measured (`helm pull` both versions, `diff -r`, 2026-10-24):
- **gha-runner-scale-set**: only `Chart.yaml` (`version`/`appVersion`). `templates/` byte-identical — so the build pool's
  index-based postRenderer (`/spec/template/spec/initContainers/1` = dind) still targets the same container.
- **gha-runner-scale-set-controller**: `Chart.yaml`, a test file, and all four CRDs: `controller-gen` v0.22.0 → v0.23.0 plus
  `minLength: 1` / `minimum: 0, maximum: 100000` / `maxItems: 10` on the pod-spec field `evictionResponders` only. Tightened
  validation could reject stored objects that violate it — measured **0** occurrences of `evictionResponders` across all live
  AutoscalingRunnerSets, AutoscalingListeners, EphemeralRunnerSets and EphemeralRunners.

### 1.3 Why it was held — and why the hold is a policy hold, not a technical one

Held by deny rule `*gha-runner-scale-set*` (`runbooks/auto-update-policy.yaml`): "controller chart and scale-set chart MUST
run the same version and are bumped together in one commit; ... a chart bump can carry CRD changes. Planned window only."
The CRD change is real but inert (1.2). The lockstep risk was checked against upstream code, not the rule text:
`controllers/actions.github.com/autoscalingrunnerset_controller.go` @0.15.1 — when
`!v1alpha1.IsVersionAllowed(ars.Labels["app.kubernetes.io/version"], build.Version)` the controller **deletes the
AutoscalingRunnerSet**. `apis/actions.github.com/v1alpha1/version.go` (identical in 0.15.0 and 0.15.1) allows a mismatch when
`rv.major == bv.major && rv.minor == bv.minor`. 0.15.0 ↔ 0.15.1 is same-minor, so the controller-first window between the two
halves cannot delete a scale set. The rule is still right for a MINOR bump (0.15 → 0.16 would delete every set whose half
lags) — see §6. **Verdict: low-risk patch; the hold was correct policy but near false-positive for this patch.**

### 1.4 Expected runtime effect (from the same controller source)
- `arc-controller` and `arc-build-controller` Deployments roll (new image `gha-runner-scale-set-controller:0.15.1`).
- The listener spec embeds the controller image and the ARS labels, so `listenerSpecChanged` / label inequality fires and
  each of the 3 AutoscalingListeners is deleted and re-created (pods keep their names; new `app.kubernetes.io/version=0.15.1`).
  Self-hosted jobs are not picked up for ~1-2 min per pool; GitHub keeps them queued.
- EphemeralRunnerSets: only labels/annotations differ (runner spec unchanged), which takes the metadata-patch branch, not
  `ephemeralRunnerSetActionableSpecChanged` — **running and idle runner pods are not recycled**; a job in flight finishes.
- ARC #4706 (old runner sets stuck Terminating, 0.14 → 0.15) does not apply: no ARS is deleted on a same-minor bump.

## 2. Pre-checks

Run from the repo root on the Mac (zsh). All read-only.

1. Premises: `.venv/bin/python3 runbooks/plan-premises.py gha-fleet-0.15.1` — all 5 PASS, else stop.
2. Both PRs still open and unchanged (target digests as in the frontmatter):
   ```bash
   gh pr view 415 --json state,files -q '.state' ; gh pr view 414 --json state -q '.state'   # OPEN OPEN
   gh pr diff 415 | grep -E '^\+ +digest:' ; gh pr diff 414 | grep -E '^\+ +digest:'
   ```
   Digests must equal `c2497a6d…3aae` (controller) and `2ae7e43d…f365` (scale set, twice). If upstream re-published the tag
   (GHCR tags are mutable), stop and re-derive: `helm pull oci://ghcr.io/actions/actions-runner-controller-charts/<chart> --version 0.15.1` prints `Digest:`.
3. No job mid-run you would rather not race (soft; in-flight jobs survive, §1.4):
   ```bash
   gh api 'repos/nachtschatt3n/the-ninth-banner/actions/runs?status=in_progress' -q '.total_count'
   ```
4. Baseline (record the output in the window log):
   ```bash
   kubectl get pods -n arc-system -o wide
   kubectl get autoscalinglistener -n arc-system -o custom-columns='NAME:.metadata.name,IMG:.spec.image'
   gh api repos/nachtschatt3n/the-ninth-banner/actions/runners -q '.runners[] | [.name,.status] | @tsv'
   ```
   Expected 2026-10-24: 2 controllers + 3 listeners Running, listeners on `…controller:0.15.0`, 2 runners `online`
   (`ninth-banner-k8s-runner-*`, `ninth-banner-build-k8s-runner-*`, i.e. the two `minRunners: 1` warm runners).
5. No ARC alert already firing (Prometheus port-forward as in §4.6). Nothing to back up: ARC holds no PVC and no DB; all state
   is the five HelmReleases + CRs, re-created from git.

## 3. Steps (GitOps, one commit)

1. Record the start time: `T0=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo $T0`
2. Edit the three sources (dry-tested on scratch copies under macOS BSD sed, 2026-10-24):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' -e 's/^\([[:space:]]*tag:\) 0\.15\.0$/\1 0.15.1/' \
     -e 's/sha256:20a369215b8c2ed981c4c0c75e56e6009564d51fffcbbd314d5da0ef82de253a/sha256:c2497a6dedaaa723322abfe9ea2f5a81b9b8fbb90b38e45d7835b6c7629a3aae/' \
     kubernetes/apps/arc-system/gha-runner-scale-set-controller/app/ocirepository.yaml
   sed -i '' -e 's/^\([[:space:]]*tag:\) 0\.15\.0$/\1 0.15.1/' \
     -e 's/sha256:bdfdad17cf8e45ae064c73ed6764f0c75d4bf71a6e2912e6363a43d6dfc787de/sha256:2ae7e43db61047aa3c4182e73c8f58ace35e796fa07d41b64fb3c39e81e1f365/' \
     kubernetes/apps/ci-runner/the-ninth-banner-runners/app/ocirepository.yaml \
     kubernetes/apps/arc-build/the-ninth-banner-build-runners/app/ocirepository.yaml
   git diff --stat -- kubernetes/apps/arc-system kubernetes/apps/ci-runner kubernetes/apps/arc-build   # 3 files, 6+/6-
   ```
   Dry-run diff (all three files produced exactly these lines; comments untouched):
   ```
   -    tag: 0.15.0
   -    digest: sha256:20a369215b8c2ed981c4c0c75e56e6009564d51fffcbbd314d5da0ef82de253a
   +    tag: 0.15.1
   +    digest: sha256:c2497a6dedaaa723322abfe9ea2f5a81b9b8fbb90b38e45d7835b6c7629a3aae
   -    tag: 0.15.0
   -    digest: sha256:bdfdad17cf8e45ae064c73ed6764f0c75d4bf71a6e2912e6363a43d6dfc787de
   +    tag: 0.15.1
   +    digest: sha256:2ae7e43db61047aa3c4182e73c8f58ace35e796fa07d41b64fb3c39e81e1f365
   ```
   (the scale-set pair appears twice: ci-runner and arc-build). If `git diff --stat` shows anything other than 3 files /
   6 insertions / 6 deletions, stop.
3. Also update the version cells in `docs/sops/ci-runner.md` §2c ("Controller ... 0.15.0", "Scale set ... 0.15.0") to 0.15.1
   in the same commit.
4. Commit only these paths (shared worktree), verify, push:
   ```bash
   git commit --only \
     kubernetes/apps/arc-system/gha-runner-scale-set-controller/app/ocirepository.yaml \
     kubernetes/apps/ci-runner/the-ninth-banner-runners/app/ocirepository.yaml \
     kubernetes/apps/arc-build/the-ninth-banner-build-runners/app/ocirepository.yaml \
     docs/sops/ci-runner.md \
     -m "fix(arc): actions-runner-controller charts 0.15.0 -> 0.15.1 in lockstep (plan gha-fleet-0.15.1; supersedes #414 #415)"
   git log -1 --format=%s        # must be the subject above
   git show --stat HEAD          # exactly the 4 files
   git push
   ```
   Flux ordering is enforced by the existing Kustomization `dependsOn` (no manual sequencing): `the-ninth-banner-runners`
   waits for `gha-runner-scale-set-controller` (`wait: true`), `the-ninth-banner-browser-runners` waits for
   `the-ninth-banner-runners`, `the-ninth-banner-build-runners` waits for `gha-runner-scale-set-build-controller`, which waits
   for `gha-runner-scale-set-controller`. Do NOT `flux reconcile` unless the source has not picked up the commit after 10 min
   (`flux get ks gha-runner-scale-set-controller` revision still old) — then one `flux reconcile source git flux-system`.
5. After §4 passes, close the superseded Renovate PRs:
   `gh pr close 415 -c "Superseded by $(git rev-parse --short HEAD) (lockstep commit, plan gha-fleet-0.15.1)"` and the same
   for 414.

## 4. Verification

Wait for all five HRs to settle (typically < 8 min), then run every gate. Each one was checked to be able to fail: on the
pre-change cluster gates 4.1-4.5 read the OLD values today (live 2026-10-24), i.e. they FAIL until the upgrade lands.

**4.1 HelmReleases on the new chart, Ready** (fails today: reads `0.15.0+…`):
```bash
kubectl get hr -A -o jsonpath='{range .items[?(@.spec.chartRef.kind=="OCIRepository")]}{.metadata.namespace}/{.metadata.name}={.status.history[0].chartVersion}/{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' | grep -E 'gha-runner|ninth-banner-(build-|browser-)?runners'
```
PASS: 5 lines, controllers `0.15.1+c2497a6dedaa/True`, scale sets `0.15.1+2ae7e43db610/True`.

**4.2 CRDs actually replaced** — CONTENTS ASSERTION: the cluster serves the 0.15.1 CRD schema, measured by
```bash
for c in autoscalingrunnersets autoscalinglisteners ephemeralrunnersets ephemeralrunners; do kubectl get crd $c.actions.github.com -o jsonpath='{.metadata.annotations.controller-gen\.kubebuilder\.io/version}{"\n"}'; done
```
compared to baseline `v0.22.0` (premise). PASS: four lines `v0.23.0`. Guards against `crds: CreateReplace` silently not
applying (HR Ready says nothing about CRDs).

**4.3 Controllers rolled to the new binary** (fails if the Deployment did not roll or the pull failed):
```bash
kubectl get pods -n arc-system -l app.kubernetes.io/component=controller-manager -o custom-columns='NAME:.metadata.name,IMG:.spec.containers[0].image,START:.status.startTime,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
```
PASS: exactly 2 pods (`arc-controller-*`, `arc-build-controller-*`), image `…controller:0.15.1`, START > `$T0`, READY true,
RESTARTS 0. (Do not trust `rollout status`: it can green-light the old generation.)

**4.4 Scale sets kept, re-labelled, Running** — CONTENTS ASSERTION: all three scale sets still exist (none deleted by the
version check, §1.3) and carry the new version, measured by
```bash
kubectl get autoscalingrunnerset -A -o jsonpath='{range .items[*]}{.metadata.name}={.metadata.labels.app\.kubernetes\.io/version}/{.status.phase} {end}'
```
PASS exactly: `ninth-banner-build-k8s=0.15.1/Running ninth-banner-browser-k8s=0.15.1/Running ninth-banner-k8s=0.15.1/Running`.
A missing name = the controller deleted it → Rollback (§5).

**4.5 Listeners rebuilt and holding a broker session** — CONTENTS ASSERTION: each listener re-registered with GitHub and is
consuming the job queue, measured from its own log (the pod is new, so its whole log is post-`$T0`):
```bash
for l in ninth-banner-k8s-59fd7c9b-listener ninth-banner-browser-k8s-59fd7c9b-listener ninth-banner-build-k8s-7b4779b7-listener; do
  echo "== $l img=$(kubectl get autoscalinglistener -n arc-system $l -o jsonpath='{.spec.image}') start=$(kubectl get pod -n arc-system $l -o jsonpath='{.status.startTime}')"
  echo "session=$(kubectl logs -n arc-system $l | grep -c -i 'Handling initial session statistics') scaler=$(kubectl logs -n arc-system $l | grep -c -i 'Calculated target runner count') errors=$(kubectl logs -n arc-system $l | grep -c -i 'level=ERROR')"
done
```
PASS per listener: img `…controller:0.15.1`, start > `$T0`, `scaler>=1`, `errors=0`. `scaler` is the gate. The `session` count is
informational only: 'Handling initial session statistics' is verified in upstream source (`actions/scaleset` v0.5.0
`listener/listener.go`, the version 0.15.1's go.mod pins) but is NOT present in today's 0.15.0 listener log (rotated), so do not gate on it;
'Calculated target runner count' is in `cmd/ghalistener/scaler/scaler.go` (0.15.1 source). Failure it guards against: a listener that is Running but
cannot authenticate / reach the broker prints the token/session error at `level=ERROR` and never logs the session line.
If the listener name differs (name is derived from the namespace hash, unchanged here), use
`kubectl get autoscalinglistener -n arc-system`.

**4.6 Metrics still arrive from the NEW pods** — CONTROL lines:
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s --data-urlencode 'query=count(up{namespace="arc-system"} == 1)' http://localhost:19090/api/v1/query | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print('UP', r[0]['value'][1] if r else 'EMPTY')"
curl -s --data-urlencode 'query=max by (name) (gha_controller_running_listeners{namespace="arc-system"})' http://localhost:19090/api/v1/query | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print('LISTENERS', sorted((x['metric']['name'],x['value'][1]) for x in r) or 'EMPTY')"
curl -s --data-urlencode 'query=count by (name) (gha_min_runners)' http://localhost:19090/api/v1/query | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print('SCALESETS', len(r))"
curl -s 'http://localhost:19090/api/v1/alerts' | python3 -c "import sys,json; a=[x['labels']['alertname'] for x in json.load(sys.stdin)['data']['alerts'] if x['labels']['alertname'].startswith('ARC') and x['state']=='firing']; print('ARC_FIRING', a or 'NONE')"
kill $PF 2>/dev/null
```
CONTROL: metric up — `count(up{namespace="arc-system"} == 1)` = 5 (2 controllers + 3 listeners; measured 5 on 2026-10-24). `EMPTY` or <5 = scrape lost.
CONTROL: metric gha_controller_running_listeners — all three listener names present with max value 1.
CONTROL: metric gha_min_runners — exported by the listeners; 3 series (one per scale set), measured 3 on 2026-10-24.
CONTROL: alertname ARCRunnerScaleSetNotRegistered — not firing 15 min after `$T0` (fires if a scale set has its secret but no listener for 15m).
CONTROL: alertname ARCPodCrashLooping — not firing.
CONTROL: alertname ARCPodNotReady — not firing.
Run the alert line once ~15 min after `$T0` (the NotRegistered rule has `for: 15m`); `ARC_FIRING NONE` = PASS.

**4.7 Soak (morning report, not a window blocker):** the next real CI run of the game repo ran on the self-hosted pools:
`gh api 'repos/nachtschatt3n/the-ninth-banner/actions/runs?per_page=1' -q '.workflow_runs[0].id'` then
`gh api repos/nachtschatt3n/the-ninth-banner/actions/runs/<id>/jobs -q '.jobs[] | [.name,.runner_name,.conclusion] | @tsv'` —
`runner_name` must start with `ninth-banner-` and no job may sit `queued` > 30 min (`ARCRunnerJobsWaiting` would fire).
A job failing on its own test merits is not a regression of this plan (recent CI runs already fail on the game's own tests).

## 5. Rollback

Trigger: any of 4.1-4.6 fails and does not self-heal within 10 min, or a scale set disappears (4.4).

1. `git revert --no-edit <sha-of-§3.4-commit>`; `git log -1 --format=%s` (must read `Revert "fix(arc): …"`); `git push`.
   This restores tag 0.15.0 + the 0.15.0 digests on all three sources (and the SOP cells). Flux re-applies in the same
   `dependsOn` order; CreateReplace re-applies the 0.15.0 CRDs (it only drops the extra validation, no stored object uses it).
   Same-minor skew is tolerated in this direction too.
2. If an HR is stuck `pending-upgrade` / `upgrade retries exhausted`: per `docs/sops/application-update.md` §11, clear it with
   `flux suspend hr -n <ns> <name>` + `flux resume hr -n <ns> <name>` (the HR names are the five in `touches`).
3. **If a scale set was deleted (4.4)**: the revert alone re-creates it — the ARS is a chart object of its HelmRelease and the
   controller re-registers it with GitHub on create (`createRunnerScaleSet`). Runs-on labels are registered at create time from
   the unchanged `scaleSetLabels`/`runnerScaleSetName`, so they come back identical. If the HR reads Ready but the ARS is
   absent, force a re-render once: `flux reconcile hr -n <ns> <name> --force`.
4. Confirm back: re-run 4.1/4.3/4.4/4.5 expecting `0.15.0` values (`…controller:0.15.0`, label `0.15.0`, CRD annotation
   `v0.22.0`), 4.6 all CONTROL lines green, and `gh api repos/nachtschatt3n/the-ninth-banner/actions/runners` lists the
   warm runners `online`. Re-open nothing: Renovate re-opens 414/415 by itself on its next run.

## 6. Interference notes

- **Shared surfaces:** cluster-scoped `actions.github.com` CRDs (only ARC uses them); Prometheus is the §4 instrument — no
  kube-prometheus-stack plan is open today; if one is filed for the same night, add it to `conflicts_with` (and vice versa).
- **CI impact:** each listener rebuild pauses job pickup for its pool ~1-2 min; jobs queue at GitHub and are not lost. Runner
  pods (incl. a job in flight) are not recycled (§1.4). The nightly 03:30 slot is quiet: the game's CI runs observed at
  ~06:00 and ~08:35 UTC.
- **No node impact:** no reboot, no PVC, no change to runner resources/affinity, so the CI thermal/power plans
  (`talos-power-tuning-ab`, `ci-gate-primary-control-rework`) are conflicts only for attribution, not for safety.
- **Reciprocity:** `talos-power-tuning-ab` and `ci-gate-primary-control-rework` do
  not list this plan; the window agent should add `gha-fleet-0.15.1` to their `conflicts_with` (validate checks refs, not
  reciprocity).
- **Repo corrections (not done here, report only):**
  1. `runbooks/auto-update-policy.yaml` rule `*gha-runner-scale-set*` and SOP `ci-runner.md` §2c should state the precise
     upstream mechanism: on a MINOR mismatch the controller **deletes** the AutoscalingRunnerSet (`IsVersionAllowed`,
     same-minor only). That is the real reason for lockstep and makes clear a patch bump is low risk while a minor bump must
     land controller + every scale-set source in one commit.
  2. SOP §2c "Controller"/"Scale set" rows mention only the `ci-runner` scale-set source; the `arc-build` source
     (`kubernetes/apps/arc-build/the-ninth-banner-build-runners/app/ocirepository.yaml`) and the second controller
     (`gha-runner-scale-set-build-controller`, same chart source) are part of the lockstep and should be named there, and the
     controller OCIRepository comment ("bump ../../../ci-runner/... in the same commit") should also name arc-build.
  3. The build-runners postRenderer patches `initContainers/1` by index; harmless for 0.15.1 (templates identical) but the
     next minor must re-check the dind init-container order before merging.
