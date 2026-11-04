---
plan_id: the-fleet-0.15.1
component: the-ninth-banner-runners   # group "the-fleet-0.15.1": the-ninth-banner-build-runners (arc-build), the-ninth-banner-browser-runners + the-ninth-banner-runners (ci-runner)
pr: 414                               # Renovate "update ...gha-runner-scale-set ( 0.15.0 -> 0.15.1 )" (ci-runner + arc-build sources). Controller half is PR 415.
kind: chart
current: "0.15.0 (gha-runner-scale-set chart sha256:bdfdad17cf8e45ae064c73ed6764f0c75d4bf71a6e2912e6363a43d6dfc787de; controller chart sha256:20a369215b8c2ed981c4c0c75e56e6009564d51fffcbbd314d5da0ef82de253a)"
target: "0.15.1"                      # scale-set chart sha256:2ae7e43db61047aa3c4182e73c8f58ace35e796fa07d41b64fb3c39e81e1f365, controller chart
                                      # sha256:c2497a6dedaaa723322abfe9ea2f5a81b9b8fbb90b38e45d7835b6c7629a3aae (both re-derived with `helm pull`
                                      # 2026-11-03; identical to gha-fleet-0.15.1 and the Renovate PR digests)
update_type: patch
risk: low                             # same-minor patch; templates byte-identical (evidence: gha-fleet-0.15.1 section 1.2/1.3); no PVC/state; git revert.
est_duration_min: 35
needs_reboot: false
touches:
  namespaces: [arc-system, ci-runner, arc-build]
  resources:                          # every object verified to exist live 2026-11-03 (kubectl get)
    - ocirepository/gha-runner-scale-set-controller   # arc-system, EDITED (lockstep: same commit, see section 1)
    - ocirepository/gha-runner-scale-set              # ci-runner, EDITED; source of the-ninth-banner-runners + the-ninth-banner-browser-runners
    - ocirepository/gha-runner-scale-set              # arc-build, EDITED; source of the-ninth-banner-build-runners AND absenty-build-runners AND rainbow-rescue-build-runners
    - helmrelease/gha-runner-scale-set-controller     # arc-system
    - helmrelease/gha-runner-scale-set-build-controller   # arc-system
    - helmrelease/the-ninth-banner-runners            # ci-runner
    - helmrelease/the-ninth-banner-browser-runners    # ci-runner
    - helmrelease/the-ninth-banner-build-runners      # arc-build
    - helmrelease/absenty-build-runners               # arc-build, NOT a group member but rides the shared arc-build source
    - helmrelease/rainbow-rescue-build-runners        # arc-build, same
    - autoscalingrunnerset/ninth-banner-k8s           # ci-runner
    - autoscalingrunnerset/ninth-banner-browser-k8s   # ci-runner
    - autoscalingrunnerset/ninth-banner-build-k8s     # arc-build
    - autoscalingrunnerset/absenty-build-k8s          # arc-build
    - autoscalingrunnerset/rainbow-rescue-build-k8s   # arc-build
    - crd/autoscalingrunnersets.actions.github.com
    - crd/autoscalinglisteners.actions.github.com
    - crd/ephemeralrunnersets.actions.github.com
    - crd/ephemeralrunners.actions.github.com
  shared: [monitoring, ci-runner, arc-build, crds/actions.github.com, github-actions/the-ninth-banner, github-actions/absenty, github-actions/rainbow-rescue]
depends_on: []
conflicts_with:
  - absenty-build-runners-0.15.1      # rides the same arc-build source with no edit of its own; superseded by this plan (reviewer 2026-11-03)
  - helm-drift-detection              # changes how helm-controller treats these HelmReleases (as in gha-fleet-0.15.1)
  - gha-fleet-0.15.1                  # SAME three-file edit; only one of the two may execute (see section 1). Retire gha-fleet-0.15.1 when this one is vetted.
  - talos-linux-1.14.5                # node roll restarts every ARC pod; attribution of section 4 impossible
  - talos-power-tuning-ab             # measures CI load on ci-runner; a listener gap skews its baseline
  - flux-reconciler-impersonation     # changes WHO applies the arc-system/ci-runner/arc-build Kustomizations
  - flux-oci-chart-sources            # edits how chart OCIRepositories are declared; same files
exclusive: false
capability_change: false              # same chart templates, same values, same runner pods; controller binary gains bug fixes only
rollback_class: git-revert            # no PVC, no DB; 0/4 CRD kinds store the only field whose validation tightened (gha-fleet-0.15.1 1.2)
security_ref: F-1fd1d6a0                # controller image finding; detail lives on the finding, not here
finding_refs: [F-5602ee2a, F-87d453b9, F-a2cff4a9, F-1fd1d6a0]   # copied from gha-fleet-0.15.1 (same component, same target); not re-queried, SWEEP_PG_DSN not up in this session
review: ready-for-go@2026-11-03   # plan-reviewer 2026-11-03: needs-fix (bookkeeping only), fixed, delta re-review ready-for-go. status stays draft: gha-fleet-0.15.1 is being re-edited by another session to cover 5 scale sets; ONE of the two must own the edit before either is vetted
status: superseded   # 2026-11-04 (operator-approved): superseded by gha-fleet-0.15.1, which now covers all five ARC scale sets (reviewed ready-for-go 2026-11-03, 44643085). Same three-file edit; never executed.
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/ci-runner.md            # section 2c lockstep + section 2e arc-build pools
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-03"
premises:
  - id: scale-set-sources-on-0150
    why: >-
      current: both scale-set chart sources must still be 0.15.0. If someone merged PR 414 alone, the section 3 sed matches nothing for
      them; do only the missing half.
    run: kubectl get ocirepository -A -o jsonpath='{range .items[?(@.metadata.name=="gha-runner-scale-set")]}{.metadata.namespace}={.spec.ref.tag} {end}'
    expect_exact: "arc-build=0.15.0 ci-runner=0.15.0"
  - id: controller-source-on-0150
    why: >-
      the controller source must still be 0.15.0 at the known digest (lockstep half of this one commit).
    run: kubectl get ocirepository -n arc-system gha-runner-scale-set-controller -o jsonpath='{.spec.ref.tag} {.spec.ref.digest}'
    expect_exact: "0.15.0 sha256:20a369215b8c2ed981c4c0c75e56e6009564d51fffcbbd314d5da0ef82de253a"
  - id: five-scale-sets-running-on-0150
    why: >-
      FIVE AutoscalingRunnerSets exist since the absenty + rainbow-rescue pools landed (116ac5df); gha-fleet-0.15.1 still expects THREE and
      now fails its premises. The controller deletes an ARS whose version label differs by MINOR, so every set must start Running on
      0.15.x; a Pending/Outdated set must be fixed before, not during, the bump.
    run: kubectl get autoscalingrunnerset -A -o jsonpath='{range .items[*]}{.metadata.name}={.metadata.labels.app\.kubernetes\.io/version}/{.status.phase} {end}'
    expect_exact: "absenty-build-k8s=0.15.0/Running ninth-banner-build-k8s=0.15.0/Running rainbow-rescue-build-k8s=0.15.0/Running ninth-banner-browser-k8s=0.15.0/Running ninth-banner-k8s=0.15.0/Running"
  - id: seven-arc-helmreleases-ready
    why: >-
      All seven ARC HelmReleases Ready before the change (3 group members + 2 controllers + the 2 arc-build pools that share the source);
      a failing HR would mask, or be blamed on, this upgrade.
    run: kubectl get hr -A -o jsonpath='{range .items[?(@.spec.chartRef.name=="gha-runner-scale-set")]}{.metadata.name}={.status.conditions[?(@.type=="Ready")].status} {end}{range .items[?(@.spec.chartRef.name=="gha-runner-scale-set-controller")]}{.metadata.name}={.status.conditions[?(@.type=="Ready")].status} {end}'
    expect_exact: "absenty-build-runners=True rainbow-rescue-build-runners=True the-ninth-banner-build-runners=True the-ninth-banner-browser-runners=True the-ninth-banner-runners=True gha-runner-scale-set-build-controller=True gha-runner-scale-set-controller=True"
  - id: crds-on-controller-gen-0220
    why: >-
      Baseline for the section 4.2 CRD contents gate: live CRDs are the 0.15.0 ones (controller-gen v0.22.0; 0.15.1 ships v0.23.0). If this
      already reads v0.23.0 the gate cannot fail.
    run: kubectl get crd autoscalingrunnersets.actions.github.com -o jsonpath='{.metadata.annotations.controller-gen\.kubebuilder\.io/version}'
    expect_exact: "v0.22.0"
---

# the-fleet-0.15.1 - gha-runner-scale-set charts 0.15.0 -> 0.15.1 (group: the-ninth-banner build/browser/runners)

## 1. Summary & why held (and how this plan relates to gha-fleet-0.15.1)

**Why held:** G3 could not verify the release notes (`release notes unavailable`), and the deny rule `*gha-runner-scale-set*`
(`runbooks/auto-update-policy.yaml`) requires controller and scale-set charts to move together in a planned window. Not security-driven.
I verified the notes myself: `gha-runner-scale-set-0.15.1` (2026-10-23) is a bug-fix patch with no breaking change, no values change, no
migration; chart templates of the scale-set chart are byte-identical (`Chart.yaml` only); the controller chart's CRDs change only
controller-gen v0.22.0 -> v0.23.0 plus extra validation on the unused pod-spec field `evictionResponders` (0 live objects use it). Full
upstream evidence and the same-minor `IsVersionAllowed` safety argument: `runbooks/maintenance/plans/gha-fleet-0.15.1.md` sections 1.2-1.3
(not repeated here). Verdict: risk low, 35 min, no reboot.

**Overlap, stated precisely:** `gha-fleet-0.15.1` (vetted, window `nightly:2026-11-09`) edits exactly the same three OCIRepository files
(controller in `arc-system`, scale-set in `ci-runner` and `arc-build`) in one commit, so it already covers all three members of this
group and both controllers. **It cannot run as written any more**: since it was vetted, commit `116ac5df` added two more arc-build pools
(`absenty-build-runners`, `rainbow-rescue-build-runners`) that consume the SAME `arc-build/gha-runner-scale-set` source. Measured live
2026-11-03 with `plan-premises.py gha-fleet-0.15.1`: premises `scale-sets-running-on-0150` (3 ARS expected, 5 exist) and
`arc-helmreleases-ready` (5 HRs expected, 7 match) FAIL, and its section 4 gates (listener loop of 3, `count(up)=5`, 3 `gha_min_runners`
series) would also read wrong with 5 listeners. This plan is therefore the same change with the scope and gates corrected to 5 scale sets /
5 listeners / 7 HelmReleases. As of 2026-11-03 only `absenty-build-runners-0.15.1` exists as a sibling plan file; coverage.py also splits
`gha-runner-scale-set-build-controller-0.15.1` and `rainbow-rescue-build-runners-0.15.1` into their own groups, but no plan files exist for
them. All of them edit or ride the same three source files: **this plan owns the edit. Land ONE commit (section 3), then mark
`absenty-build-runners-0.15.1` and `gha-fleet-0.15.1` superseded; never run two of them.** If coverage dispatches the other two groups, they
are covered by this plan's commit and need no plan of their own.

Lockstep note: the edit moves the controller source too. The controller-first window between controller and scale-set reconciles is safe
for a patch because the controller tolerates same-minor skew (`version.go`, gha-fleet 1.3); a MINOR bump would delete scale sets.

## 2. Pre-checks

1. `.venv/bin/python3 runbooks/plan-premises.py the-fleet-0.15.1 --require-premises` - all 5 PASS, else stop. (Fails if gha-fleet-0.15.1 already ran: then retire this plan.)
2. Renovate PRs still open and digests unchanged (GHCR tags are mutable):
   ```bash
   gh pr view 414 --json state -q .state ; gh pr view 415 --json state -q .state        # OPEN OPEN
   gh pr diff 414 | grep -E '^\+ +digest:' ; gh pr diff 415 | grep -E '^\+ +digest:'
   ```
   Must show `2ae7e43d...f365` (twice, 414) and `c2497a6d...3aae` (415). If different: stop, re-derive with
   `helm pull oci://ghcr.io/actions/actions-runner-controller-charts/<chart> --version 0.15.1` (prints `Digest:`).
3. No build you would rather not race (soft; in-flight jobs survive, runner pods are not recycled):
   `gh api 'repos/nachtschatt3n/the-ninth-banner/actions/runs?status=in_progress' -q '.total_count'`.
4. Baseline, record in the window log:
   ```bash
   kubectl get pods -n arc-system -o wide
   kubectl get autoscalinglistener -n arc-system -o custom-columns='NAME:.metadata.name,IMG:.spec.image'
   ```
   Expected 2026-11-03: 2 controllers + 5 listeners Running, all listeners on `...controller:0.15.0`.
5. No ARC alert firing (Prometheus port-forward as in 4.6). Nothing to back up: ARC holds no PVC/DB; state is HelmReleases + CRs from git.

## 3. Steps (GitOps, one commit)

1. `T0=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo $T0`
2. Edit the three sources (sed taken from gha-fleet-0.15.1, which dry-tested it on macOS BSD sed; the `tag:` pattern is anchored so it
   cannot touch other lines; re-dry-tested 2026-11-03 on scratch copies, output below):
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
   Expected diff lines (each file: one tag line and one digest line changed): `-    tag: 0.15.0` / `+    tag: 0.15.1`, and the digest lines
   `bdfdad17...` -> `2ae7e43d...` (ci-runner, arc-build) and `20a36921...` -> `c2497a6d...` (arc-system). Anything other than 3 files / 6 insertions /
   6 deletions: stop.
3. In `docs/sops/ci-runner.md` change the version cells to 0.15.1: line 185 (Controller `gha-runner-scale-set-controller 0.15.0`), line 186
   (Scale set `0.15.0`) and line 249 (`ARC gha-runner-scale-set 0.15.0 in arc-build`); leave the dated changelog line 474 (history).
4. Commit only these paths (shared worktree), verify subject, push:
   ```bash
   git commit --only \
     kubernetes/apps/arc-system/gha-runner-scale-set-controller/app/ocirepository.yaml \
     kubernetes/apps/ci-runner/the-ninth-banner-runners/app/ocirepository.yaml \
     kubernetes/apps/arc-build/the-ninth-banner-build-runners/app/ocirepository.yaml \
     docs/sops/ci-runner.md \
     -m "fix(arc): gha-runner-scale-set + controller charts 0.15.0 -> 0.15.1 in lockstep (plan the-fleet-0.15.1; supersedes #414 #415)"
   git log -1 --format=%s ; git show --stat HEAD     # subject is yours; exactly the 4 files
   git push
   ```
   Flux ordering is the existing Kustomization `dependsOn` (controller KS `wait: true` first; `the-ninth-banner-build-runners` and the two
   other arc-build pools wait on `gha-runner-scale-set-build-controller`; absenty/rainbow-rescue also wait on `the-ninth-banner-build-runners`).
   No manual `flux reconcile` unless the source has not picked the commit up after 10 min.
5. After section 4 passes: `gh pr close 415 -c "Superseded by $(git rev-parse --short HEAD) (plan the-fleet-0.15.1)"` and the same for 414.

## 4. Verification

Wait up to ~10 min for the seven HRs to settle. Gates 4.1 to 4.5 FAIL on the pre-change cluster (they read 0.15.0 values), which is how they were chosen. Gate 4.6 (`up`=7, 5 `gha_min_runners` series) reads the same before and after: it is a scrape-loss control only, not proof of the upgrade.

**4.1 HelmReleases on the new chart, Ready:**
```bash
kubectl get hr -A -o jsonpath='{range .items[?(@.spec.chartRef.kind=="OCIRepository")]}{.metadata.namespace}/{.metadata.name}={.status.history[0].chartVersion}/{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' | grep -E 'gha-runner|-runners'
```
PASS: 7 lines; the two controllers `0.15.1+c2497a6dedaa/True`, the five scale sets `0.15.1+2ae7e43db610/True`. A `0.15.0+` or `False` line fails.

**4.2 CRDs really replaced (contents, not HR status):**
```bash
for c in autoscalingrunnersets autoscalinglisteners ephemeralrunnersets ephemeralrunners; do kubectl get crd $c.actions.github.com -o jsonpath='{.metadata.annotations.controller-gen\.kubebuilder\.io/version}{"\n"}'; done
```
PASS: four lines `v0.23.0` (baseline `v0.22.0`). Guards against `crds: CreateReplace` silently not applying.

**4.3 Controllers rolled:**
```bash
kubectl get pods -n arc-system -l app.kubernetes.io/component=controller-manager -o custom-columns='NAME:.metadata.name,IMG:.spec.containers[0].image,START:.status.startTime,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
```
PASS: exactly 2 pods, image `...controller:0.15.1`, START later than `$T0`, READY true, RESTARTS 0 (rollout status can green-light the old generation).

**4.4 No scale set deleted, all re-labelled:**
```bash
kubectl get autoscalingrunnerset -A -o jsonpath='{range .items[*]}{.metadata.name}={.metadata.labels.app\.kubernetes\.io/version}/{.status.phase} {end}'
```
PASS exactly: `absenty-build-k8s=0.15.1/Running ninth-banner-build-k8s=0.15.1/Running rainbow-rescue-build-k8s=0.15.1/Running ninth-banner-browser-k8s=0.15.1/Running ninth-banner-k8s=0.15.1/Running`. A missing name means the controller deleted it: Rollback.

**4.5 Five listeners rebuilt and consuming the queue:**
```bash
for l in $(kubectl get autoscalinglistener -n arc-system -o jsonpath='{.items[*].metadata.name}'); do
  echo "== $l img=$(kubectl get autoscalinglistener -n arc-system $l -o jsonpath='{.spec.image}') start=$(kubectl get pod -n arc-system $l -o jsonpath='{.status.startTime}')"
  echo "scaler=$(kubectl logs -n arc-system $l | grep -c -i 'Calculated target runner count') errors=$(kubectl logs -n arc-system $l | grep -c -i 'level=ERROR')"
done
```
PASS: 5 blocks (a different count means a listener is missing), each img `...controller:0.15.1`, start later than `$T0`, `scaler>=1`, `errors=0`.
`scaler` is the gate (present in the 0.15.1 `ghalistener/scaler` source); a listener that cannot authenticate to the broker logs `level=ERROR` and never
reaches the scaler line. Listener names are hash-derived and currently `ninth-banner-k8s-59fd7c9b`, `ninth-banner-browser-k8s-59fd7c9b`,
`ninth-banner-build-k8s-7b4779b7`, `absenty-build-k8s-f5698648`, `rainbow-rescue-build-k8s-6dd676d8` (suffix `-listener`); the loop enumerates live, so a rename does not break it.

**4.6 Metrics from the new pods (CONTROL lines):**
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s --data-urlencode 'query=count(up{namespace="arc-system"} == 1)' http://localhost:19090/api/v1/query | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print('UP', r[0]['value'][1] if r else 'EMPTY')"
curl -s --data-urlencode 'query=count by (name) (gha_min_runners)' http://localhost:19090/api/v1/query | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print('SCALESETS', len(r))"
curl -s 'http://localhost:19090/api/v1/alerts' | python3 -c "import sys,json; a=[x['labels']['alertname'] for x in json.load(sys.stdin)['data']['alerts'] if x['labels']['alertname'].startswith('ARC') and x['state']=='firing']; print('ARC_FIRING', a or 'NONE')"
kill $PF 2>/dev/null
```
CONTROL: metric up - `count(up{namespace="arc-system"} == 1)` must be 7 (2 controllers + 5 listeners; gha-fleet's 5 was written for 3 listeners and is wrong now). `EMPTY` or fewer means scrape lost.
CONTROL: metric gha_min_runners - 5 series (one per scale set). `EMPTY` or fewer: a listener is not exporting.
CONTROL: alertname ARCRunnerScaleSetNotRegistered - not firing 15 min after `$T0` (rule has `for: 15m`).
CONTROL: alertname ARCPodCrashLooping and ARCPodNotReady - not firing. Prometheus is the shared instrument (`monitoring` in touches); if a kube-prometheus-stack bump lands the same night, re-run 4.6 after it settles.

**4.7 Soak (morning report, not a blocker):** the next game CI run lands on `ninth-banner-*` runners and no job sits `queued` > 30 min:
`gh api 'repos/nachtschatt3n/the-ninth-banner/actions/runs?per_page=1' -q '.workflow_runs[0].id'` then `.../jobs -q '.jobs[] | [.name,.runner_name,.conclusion] | @tsv'`.
Absenty / rainbow-rescue pools are `minRunners: 0` and only prove themselves on their next image build; their gate here is 4.4/4.5 (set kept, listener live).

## 5. Rollback

Trigger: any of 4.1-4.6 fails and does not self-heal within 10 min, or a scale set disappears (4.4).

1. `git revert --no-edit <sha-of-3.4-commit>`; `git log -1 --format=%s` must read `Revert "fix(arc): ..."`; `git push`. Restores tag 0.15.0 + the 0.15.0
   digests on all three sources and the SOP cells. Flux re-applies in the same `dependsOn` order; CreateReplace re-applies the 0.15.0 CRDs
   (drops only the extra validation; no stored object uses it). Same-minor skew is tolerated in this direction too.
2. HR stuck `pending-upgrade` / `upgrade retries exhausted`: `flux suspend hr -n <ns> <name>` then `flux resume hr -n <ns> <name>` (per
   `docs/sops/application-update.md`), names from the 7 in `touches`.
3. A deleted scale set is re-created by the revert (the ARS is a chart object; the controller re-registers it with GitHub with unchanged labels).
   If the HR reads Ready but the ARS is absent: `flux reconcile hr -n <ns> <name> --force` once.
4. Confirm back: 4.1/4.3/4.4/4.5 read `0.15.0` values (images `...controller:0.15.0`, label `0.15.0`, CRD annotation `v0.22.0`), 4.6 CONTROL lines green
   (7 up, 5 series). Renovate re-opens 414/415 by itself.

## 6. Interference notes

- **Same-scope plans:** `gha-fleet-0.15.1` (stale, see section 1) and the sibling per-component plans are mutually exclusive with this one;
  the second to run would hit a no-op or failing premise. Exactly one commit changes these three files.
- **CI impact:** each listener rebuild pauses job pickup ~1-2 min per pool (5 pools); GitHub keeps jobs queued, nothing lost; runner pods are not recycled.
- **Node/power plans:** `talos-linux-1.14.5`, `talos-power-tuning-ab`: attribution conflicts only (no reboot, no PVC, no resource change here).
  `flux-reconciler-impersonation` and `flux-oci-chart-sources` touch how these Kustomizations/sources are applied: do not run on the same night.
- **Repo corrections (report only):** (1) `gha-fleet-0.15.1` premises/gates need the 2 new arc-build pools or must be retired; (2) SOP
  `ci-runner.md` section 2c should name the arc-build source and `gha-runner-scale-set-build-controller` in the lockstep set, and the arc-build
  `ocirepository.yaml` carries no "bump with the controller" comment (unlike the ci-runner one), which is how the lockstep is forgotten;
  (3) the build pools patch `initContainers/1` (dind) by index in `postRenderers`: harmless for 0.15.1 (templates identical), re-check on the next minor.
