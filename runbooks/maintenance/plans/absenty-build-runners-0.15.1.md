---
plan_id: absenty-build-runners-0.15.1
component: absenty-build-runners   # HelmRelease arc-build/absenty-build-runners (chart gha-runner-scale-set); NO source of its own
pr: null                           # no Renovate PR of its own: the chart pin is the SHARED arc-build/gha-runner-scale-set OCIRepository (PR 414 edits it)
kind: chart
current: "0.15.0 (scale-set chart sha256:bdfdad17cf8e45ae064c73ed6764f0c75d4bf71a6e2912e6363a43d6dfc787de)"
target: "0.15.1"                   # scale-set chart sha256:2ae7e43db61047aa3c4182e73c8f58ace35e796fa07d41b64fb3c39e81e1f365 (digest per gha-fleet-0.15.1)
update_type: patch
risk: low
est_duration_min: 10               # NO edit of its own: rides gha-fleet-0.15.1's commit; this is verification of the Absenty pool only
needs_reboot: false
touches:
  namespaces: [arc-build, arc-system]
  resources:                       # every object verified to EXIST live 2026-11-03
    - helmrelease/absenty-build-runners             # arc-build; re-rendered by the shared source bump (NOT edited here)
    - autoscalingrunnerset/absenty-build-k8s        # arc-build; labels only (minRunners 0 / maxRunners 1)
    - autoscalinglistener/absenty-build-k8s-f5698648-listener   # arc-system; deleted + re-created by the controller
  shared: [ci-runner, crds/actions.github.com, github-actions/absenty, monitoring]
depends_on: [gha-fleet-0.15.1]     # the commit that moves the shared source IS this plan's change; this plan only adds the Absenty gates
conflicts_with:
  - gha-fleet-0.15.1               # same lockstep commit; execute as ONE unit (see 1.2)
  - talos-linux-1.14.4             # node roll restarts ARC pods; attribution impossible
  - talos-linux-1.14.5
exclusive: false
capability_change: false           # same templates, same values; no new route, permission, RBAC, API or exposure
rollback_class: git-revert         # nothing forward-only: no PVC/DB; revert of the gha-fleet commit restores 0.15.0
finding_refs: []                   # no sweep finding for this member (`finding list --grep absenty-build` is a coverage hold, not a finding)
review: null
status: superseded   # 2026-11-04 (operator-approved): folded into gha-fleet-0.15.1, whose gates 4.1-4.6 cover the Absenty pool; never executed.
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/ci-runner.md         # 2c lockstep, 2e Absenty / rainbow-rescue pools
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-03"
premises:
  - id: absenty-pool-on-0150
    why: >-
      current: the Absenty HR runs chart 0.15.0 and is Ready. If it already reads 0.15.1 the shared source was bumped
      (gha-fleet-0.15.1 executed) and this plan is a retire-only no-op.
    run: kubectl get hr absenty-build-runners -n arc-build -o jsonpath='{.status.history[0].chartVersion} {.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "0.15.0+bdfdad17cf8e True"
  - id: absenty-dind-initcontainer-index
    why: >-
      The pool's postRenderer patches /spec/template/spec/initContainers/1 BY INDEX (replace image, add resources). The
      gate is that index 1 is still `dind` on the rendered ARS; if the chart reordered init containers the patch would
      hit the wrong one. Fails (prints another name first) on any reorder.
    run: kubectl get autoscalingrunnerset absenty-build-k8s -n arc-build -o jsonpath='{.spec.template.spec.initContainers[1].name}'
    expect_exact: "dind"
  - id: shared-arc-build-source-on-0150
    why: >-
      The shared arc-build source feeds all three build pools; if it is already 0.15.1 the lockstep commit landed.
    run: kubectl get ocirepository gha-runner-scale-set -n arc-build -o jsonpath='{.spec.ref.tag}'
    expect_exact: "0.15.0"
---

# absenty-build-runners-0.15.1 — Absenty image-build pool, chart 0.15.0 -> 0.15.1

## 1. Summary & why held

### 1.1 Why held
Coverage lane PLAN: "G3 could not verify the release notes (release notes unavailable) ... an unverified bump needs an assessed
window". Not security-driven. The release notes ARE available and were assessed in `gha-fleet-0.15.1` section 1.2 (patch: metrics
guard fix, rate-limit requeue, Go bump, cleanup of never-used succeeded runners; runner default image bump does not reach us;
`templates/` of the scale-set chart byte-identical to 0.15.0, only `Chart.yaml` differs; no values change, no migration).
The standing deny rule `*gha-runner-scale-set*` also applies (controller and scale-set versions move in one commit).

### 1.2 This plan is ALREADY COVERED by `gha-fleet-0.15.1` — do not duplicate its edit
`absenty-build-runners` has no OCIRepository: its HelmRelease uses `chartRef: OCIRepository/gha-runner-scale-set` in `arc-build`,
the same source as `the-ninth-banner-build-runners` and `rainbow-rescue-build-runners` (HR comment; ks `dependsOn` it). The one
`tag`/`digest` edit in `kubernetes/apps/arc-build/the-ninth-banner-build-runners/app/ocirepository.yaml` made by `gha-fleet-0.15.1`
section 3 step 2 therefore moves the Absenty pool too. **This plan has NO edit, commit or push step of its own.** Run it as one
unit with `gha-fleet-0.15.1`: execute that plan, then run section 3 below.

### 1.3 Gap in `gha-fleet-0.15.1` the window agent MUST handle (it predates the 2026-11-02 pools)
`gha-fleet-0.15.1` (written 2026-10-24) counts 3 scale sets, 5 HelmReleases, 3 listeners and 5 scraped targets. Live today
(2026-11-03) there are **5 AutoscalingRunnerSets, 7 HelmReleases (5 scale-set HRs and 2
controller HRs) and 5 listeners** because `absenty-build-k8s` and `rainbow-rescue-build-k8s` were added 2026-11-02. Consequences:
- its premises `scale-sets-running-on-0150` and `arc-helmreleases-ready` (`expect_exact`, 3 / 5 names) will now FAIL; the
  plan reviewer or window agent must refresh those expectations to include `absenty-build-k8s=0.15.0/Running`,
  `rainbow-rescue-build-k8s=0.15.0/Running`, `absenty-build-runners=True`, `rainbow-rescue-build-runners=True`;
- its section 4.4 PASS string and section 4.5 listener loop and 4.6 `count(up) = 5` (now 5 listeners + 2 controllers = 7, to be
  measured in pre-checks) must be widened the same way; it never mentions the two new listeners (`absenty-build-k8s-f5698648-listener`,
  `rainbow-rescue-build-k8s-6dd676d8-listener`), which are deleted and re-created too.
  Report this to the owner of `gha-fleet-0.15.1`; the sibling rainbow-rescue / the-ninth-banner-build plans share it.

### 1.4 Risk
Low. Pool is `minRunners: 0`, `maxRunners: 1`, currently no runner pod (idle), so no job can be interrupted unless Absenty CI is
running (weekly rebuild or a push). The listener is re-created (~1-2 min where a queued job is not picked up; GitHub keeps it queued).
Same-minor (0.15.0 -> 0.15.1) skew is tolerated by the controller (`IsVersionAllowed`, per gha-fleet 1.3). The only pool-specific
risk is the index-based postRenderer on `initContainers/1` (dind): chart templates are identical, so unchanged (premise
`absenty-dind-initcontainer-index` guards it).

## 2. Pre-checks
1. `.venv/bin/python3 runbooks/plan-premises.py absenty-build-runners-0.15.1 --require-premises` — all 3 PASS, else stop
   (if `0.15.1`, `gha-fleet-0.15.1` already ran: retire this plan).
2. No Absenty job mid-run (soft): `gh api 'repos/nachtschatt3n/Absenty/actions/runs?status=in_progress' -q '.total_count'`
   (expect 0; a job in flight finishes, only pickup of new jobs pauses).
3. Baseline: `kubectl get autoscalinglistener -n arc-system | grep absenty` shows `absenty-build-k8s-f5698648-listener`.

## 3. Steps
No file edits of its own. After `gha-fleet-0.15.1` section 3 has pushed its commit (which moves the shared `arc-build` source) and
Flux has settled, run section 4. Flux ordering already exists: `absenty-build-runners` ks `dependsOn`
`gha-runner-scale-set-build-controller` and `the-ninth-banner-build-runners`; it has `wait: false`, so its HR may become Ready
after the dependents, allow up to ~10 min.

## 4. Verification
Each gate fails today (reads the OLD value) so it can pass only after the upgrade.

**4.1 Absenty HR on the new chart (fails today: reads `0.15.0+bdfdad17cf8e`):**
```bash
kubectl get hr absenty-build-runners -n arc-build -o jsonpath='{.status.history[0].chartVersion} {.status.conditions[?(@.type=="Ready")].status}'
```
PASS exactly: `0.15.1+2ae7e43db610 True`.

**4.2 ARS kept, re-labelled, dind patch intact (fails if the controller deleted the ARS: empty output / NotFound; or the patch missed):**
```bash
kubectl get autoscalingrunnerset absenty-build-k8s -n arc-build -o jsonpath='{.metadata.labels.app\.kubernetes\.io/version} {.spec.template.spec.initContainers[1].name} {.spec.template.spec.initContainers[1].resources.limits.cpu} {.spec.minRunners}/{.spec.maxRunners}'
```
PASS exactly: `0.15.1 dind 6 0/1`. (`6` proves the postRenderer resources still applied to the dind container, not another.)

**4.3 Listener rebuilt on the new image and consuming (fails if the listener was not re-created or cannot reach GitHub):**
```bash
kubectl get autoscalinglistener absenty-build-k8s-f5698648-listener -n arc-system -o jsonpath='{.spec.image}{"\n"}'
kubectl logs absenty-build-k8s-f5698648-listener -n arc-system | grep -c -i 'Calculated target runner count'
kubectl logs absenty-build-k8s-f5698648-listener -n arc-system | grep -c -i 'level=ERROR'
```
PASS: image ends `controller:0.15.1`; the second count `>=1`; the third `0`. Pod start time must be after the gha-fleet `$T0`
(`kubectl get pod absenty-build-k8s-f5698648-listener -n arc-system -o jsonpath='{.status.startTime}'`). A listener that is Running
but cannot authenticate logs at `level=ERROR` and never prints the scaler line (same logic as gha-fleet 4.5).

**4.4 Egress / quota untouched:** `kubectl get ciliumnetworkpolicy absenty-build-egress -n arc-build -o name` returns the policy
(unchanged object, not part of the chart; confirms the prune did not eat it).

**4.5 Soak (morning report, not a blocker):** the next real Absenty build ran on the pool:
`gh api 'repos/nachtschatt3n/Absenty/actions/runs?per_page=1' -q '.workflow_runs[0].id'`, then
`gh api repos/nachtschatt3n/Absenty/actions/runs/<id>/jobs -q '.jobs[] | [.name,.runner_name,.conclusion] | @tsv'`;
`runner_name` starts `absenty-build-k8s-` for build jobs. A job failing on its own merits is not a regression of this plan.

## 5. Rollback
Identical to `gha-fleet-0.15.1` section 5: `git revert --no-edit <sha of the gha-fleet lockstep commit>`, `git log -1 --format=%s`,
`git push`. This restores tag/digest 0.15.0 on the shared source, so the Absenty HR re-renders at 0.15.0. If the HR is stuck
`pending-upgrade`: `flux suspend hr -n arc-build absenty-build-runners` then `flux resume hr -n arc-build absenty-build-runners`.
If the ARS is missing but the HR is Ready: `flux reconcile hr -n arc-build absenty-build-runners --force`. Confirm back: 4.1 reads
`0.15.0+bdfdad17cf8e True`, 4.2 reads `0.15.0 dind 6 0/1`, 4.3 image `controller:0.15.0`. Nothing forward-only (no PVC, no DB, no stored
CR uses the one CRD field whose validation changed). Fallback for CI: set Absenty `runs-on` back to `ubuntu-latest` per
`docs/sops/ci-runner.md` section 2e rollback.

## 6. Interference notes
- **Same unit as `gha-fleet-0.15.1`** and the sibling plans for `rainbow-rescue-build-runners` and
  `the-ninth-banner-build-runners`/`gha-runner-scale-set-build-controller`: one commit moves all of them; they must run in the
  same window, none before `gha-fleet-0.15.1`. Do not merge Renovate PR 414 alone.
- Absenty CI shares the 2-3 build-pool pods with `arc-build-quota`; the idle pool means no capacity impact at change time.
- Any same-night `kube-prometheus-stack` bump would perturb the Prometheus instrument if gha-fleet 4.6 is reused: serialize.
- Repo corrections (report only): `gha-fleet-0.15.1` and `docs/sops/ci-runner.md` section 2c name only the-ninth-banner pools;
  section 2e says the Absenty chart pin is shared, which is why no separate PR exists for this member.
