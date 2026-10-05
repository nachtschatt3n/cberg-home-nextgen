---
plan_id: descheduler-0.37.0
component: descheduler                # HelmRelease kube-system/descheduler (chart `descheduler`,
                                      # HelmRepository flux-system/descheduler -> https://kubernetes-sigs.github.io/descheduler)
pr: null                              # no Renovate PR; dispatched from coverage.py needs_plan_groups (nightly 2026-10-05 Step 0.5)
kind: chart
current: "chart 0.36.0 (image v0.36.0)"   # MEASURED live 2026-10-05: HR spec+lastAttemptedRevision 0.36.0 Ready;
                                          # cronjob image registry.k8s.io/descheduler/descheduler:v0.36.0
target: "chart 0.37.0 (image v0.37.0)"    # `helm search repo descheduler/descheduler --versions` lists 0.37.0
                                          # (appVersion 0.37.0); registry.k8s.io tags/list contains v0.37.0, manifest HTTP 200
update_type: minor
risk: low                             # MEASURED: `helm template` 0.36.0 vs 0.37.0 with our exact values (182 lines each)
                                      # differs ONLY in chart/version labels, checksum/config (label-driven), the image tag,
                                      # and ClusterRole `pods` verbs losing `delete` (unused; upstream PR #1888). The
                                      # rendered policy.yaml is identical. Source diff v0.36.0..v0.37.0: defaultevictor
                                      # and LowNodeUtilization logic UNCHANGED (only an error-message string in
                                      # usageclients.go). Workload is a CronJob: no long-running pod, no PVC.
est_duration_min: 35                  # §2 5 + §3 3 + Flux pickup 5 + §4.1 immediate gates 5 + §4.2 first-run gate,
                                      # which needs the 04:00 CronJob run (in-window only if Ready before 03:58, see §6) + slack
needs_reboot: false
exclusive: false
touches:
  namespaces: [kube-system]
  resources:                          # every object verified to EXIST live 2026-10-05 (kubectl get)
    - helmrelease/kube-system/descheduler          # the only object this plan EDITS (spec.chart.spec.version)
    - cronjob/kube-system/descheduler              # image v0.36.0 -> v0.37.0; schedule "0 4 * * *" unchanged
    - configmap/kube-system/descheduler            # policy.yaml: labels only, data byte-identical
    - clusterrole/descheduler                      # pods verbs: drop `delete` (pods/eviction create unchanged)
    - clusterrolebinding/descheduler               # labels only
    - serviceaccount/kube-system/descheduler       # labels only
    - kubernetes/apps/kube-system/descheduler/app/helmrelease.yaml
  shared:
    - pod-placement                   # the descheduler EVICTS pods cluster-wide (all namespaces) via the eviction API
                                      # when LowNodeUtilization finds an under-utilized node. Measured 2026-10-05: 123
                                      # running pods are eligible; 81 PVC-mounting pods are protected (ignorePvcPods),
                                      # 45 DaemonSet + 15 system-critical pods are protected by default. Last 3 runs: 0
                                      # evictions (no node under the 45/40/48 % thresholds).
    - monitoring                      # §4 reads Prometheus (kube-state-metrics job/cronjob series)
depends_on: []
conflicts_with:
  - flux-fleet-0.60.0                 # upgrades helm-/source-controller = this plan's apply AND revert path
  - flux-oci-chart-sources            # its stage 4 moves this chart's source (flux-system/descheduler) to OCI
  - helm-drift-detection              # rewrites how helm-controller treats every HelmRelease incl. this one
  - flux-reconciler-impersonation     # exclusive; rewrites how helm-controller applies this HR
                                      # No kube-prometheus-stack plan is open (91.4.1 executed 2026-09-26). If one
                                      # appears it MUST be added here: §4 reads Prometheus.
capability_change: false              # v0.37.0 adds only OPT-IN chart values (podDisruptionBudget, schedulerName,
                                      # runtimeClassName, hostUsers, revisionHistoryLimit) - we set none, and the
                                      # Deployment-only ones do not render for kind: CronJob. RBAC NARROWS (pods delete
                                      # removed). Policy API v1alpha2 unchanged; eviction filter + LowNodeUtilization
                                      # code unchanged. Same behaviour for our config.
rollback_class: git-revert            # stateless CronJob, no PVC, no CRD, no migration
security_ref: F-160fc0dd              # descheduler v0.36.0 image finding (AR-029, was already-newest); v0.37.0 is the
                                      # first newer tag. Detail in the DB only.
finding_refs:
  - F-160fc0dd                        # the bump is this finding's remediation; re-measure on the next security sweep
review: null
premises:
  # All read-only single pipelines. Values measured 2026-10-05.
  - id: descheduler-hr-on-0-36-0
    why: >-
      §3's sed rewrites `version: 0.36.0`; the HR must be Ready and fully applied on 0.36.0 so a git revert
      lands on a known-good revision. Prints a different string and fails otherwise.
    run: kubectl get helmrelease -n kube-system descheduler -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: 0.36.0 0.36.0 True
  - id: descheduler-cronjob-image-v0-36-0
    why: "§4.1 asserts the CronJob image moves v0.36.0 -> v0.37.0; the baseline must hold."
    run: kubectl get cronjob -n kube-system descheduler -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image} {.spec.schedule} {.spec.suspend}'
    expect_exact: registry.k8s.io/descheduler/descheduler:v0.36.0 0 4 * * * false
  - id: descheduler-policy-uses-legacy-protection-flags
    why: >-
      The Longhorn-RWO safety argument rests on `ignorePvcPods: true` (-> PodsWithPVC protection via
      legacyGetPodProtections, unchanged in v0.37.0). If someone migrated to `podProtections:` since, the
      validation path differs (mixing is rejected) - stop and re-plan. Expect exactly the two legacy lines.
    run: kubectl get configmap -n kube-system descheduler -o jsonpath='{.data.policy\.yaml}' | grep -c -e 'ignorePvcPods. true' -e 'evictLocalStoragePods. true' -e 'podProtections'
    expect_exact: "2"
  - id: descheduler-sa-can-evict
    why: >-
      v0.37.0 drops `pods delete`; eviction relies solely on pods/eviction create, which must already be granted.
      NOTE the subresource form: `can-i create pods/eviction` prints "no" even when granted - use --subresource.
    run: kubectl auth can-i create pods --subresource=eviction --as=system:serviceaccount:kube-system:descheduler -n default
    expect_exact: "yes"
  - id: k8s-within-tested-range
    why: >-
      Upstream compatibility matrix: v0.37 is compiled against k8s 1.37 client libs and tested on the three latest
      minors (1.35-1.37). The cluster is 1.36.0 on 2026-10-05.
    run: kubectl version | grep 'Server Version'
    expect_matches: 'Server Version. v1\.3[567]\.'
  - id: repo-pins-0-36-0-once
    why: "§3's sed assumes exactly one `      version: 0.36.0` line in the HR file (run from the repo root)."
    run: "grep -c '^      version: 0.36.0$' kubernetes/apps/kube-system/descheduler/app/helmrelease.yaml"
    expect_exact: "1"
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-05"
---

# descheduler: Helm chart 0.36.0 -> 0.37.0 (image v0.36.0 -> v0.37.0)

## 1. Summary & why held

`kube-system/descheduler` pins chart `descheduler` 0.36.0. It runs as a **CronJob** (`0 4 * * *`) with one
profile: `DefaultEvictor` (`ignorePvcPods: true`, `evictLocalStoragePods: true`) and the
`LowNodeUtilization` balance plugin (thresholds cpu 45 / mem 40 / pods 48 %, targets 55 / 55 / 52 %).
The target is chart 0.37.0, appVersion 0.37.0, released 2026-10-04. The image tag `v0.37.0` is present on
registry.k8s.io (tags/list, manifest HTTP 200). This plan also carries `security_ref: F-160fc0dd`;
the detail is on the DB record only.

**Why held:** coverage gate, quoted: "0.x release-line move (0.36 -> 0.37) — at major 0 the minor IS
the breaking axis; needs an assessed window plan". **On investigation the hold is a false positive for
risk.** The evidence was read 2026-10-05.

- **Upstream release notes, `v0.37.0`** (GitHub release). Everything that reaches a running binary or
  the chart:
  - "Remove unnecessary pods delete permission from ClusterRole" (#1888). The PR says: "The descheduler
    evicts exclusively through the **eviction subresource** — `PolicyV1().Evictions(...).Evict(ctx,
    eviction)` … There are **no direct `Pods().Delete()` calls**". Verified in the v0.37.0 source: the
    only non-test pod `.Delete(` calls are on the fake client in `kubeclientsandbox.go`, and the real
    path is `evictions.go:637`.
  - "fix: emit eviction metrics for background evictions" (#1880). This only matters for KubeVirt-style
    background eviction, which we do not use, and metrics are not scraped here.
  - Opt-in chart values (#1885, #1890, #1892, #1884): `podDisruptionBudget` (Deployment-only),
    `schedulerName`, `runtimeClassName`, `hostUsers`, `revisionHistoryLimit` (Deployment-only). All
    default off or empty, and we set none of them.
  - "Fix LoggingAlphaOptions wiring" (#1906). Feature gates now go through
    `features.DefaultMutableFeatureGate`. We pass no `--feature-gates`.
  - Node-condition log restructure (#1907). "Ignoring node" for a NotReady node moves from V(1) to V(4),
    so it disappears at our `--v=3`. That only matters when reading logs (see §4).
  - "(Code-cleanup) removed EvictionRequests" (#1915). This removes an unused method only. The summary
    log lines `Number of evictions/requests` and `Total number of evictions/requests` are byte-identical
    in v0.37.0 (`descheduler.go:252`, `profile.go:417`).
  - Dependency security bumps (x/net, x/crypto, grpc, cel-go) and the k8s client bump to 1.37. Upstream
    tests on 1.35–1.37 (README compatibility matrix), and the cluster runs **v1.36.0**.
- **Policy API:** `descheduler/v1alpha2` is unchanged. `pkg/api` differs only in regenerated
  conversion code (field-by-field copies become `unsafe.Pointer` casts of identical structs). §4.2 still
  checks that the policy PARSES to our thresholds, because generated code is exactly where a silent
  misparse would hide.
- **Eviction behaviour and Longhorn RWO.** `git diff v0.36.0 v0.37.0 -- pkg/framework/plugins/defaultevictor
  pkg/framework/plugins/nodeutilization` is empty apart from one error-message string. The deprecated
  `ignorePvcPods` flag still maps to the `PodsWithPVC` protection (`legacyGetPodProtections`,
  `defaultevictor.go:422`), and `applyPVCPodsProtection` refuses any pod that mounts a PVC ("pod with PVC
  is protected against eviction"). So **no Longhorn-RWO or CIFS-backed pod can be evicted, before or
  after**, and the RWO Multi-Attach trap (`docs/sops/longhorn-rwo-multi-attach.md`) cannot be triggered
  by this component. `validation.go` still rejects MIXING the legacy flags with `podProtections`; the
  premise `descheduler-policy-uses-legacy-protection-flags` asserts that we do not mix them.
- **Rendered diff with OUR values** (`helm template` 0.36.0 vs 0.37.0, 2026-10-05; 182 lines each):
  - the `helm.sh/chart` and `app.kubernetes.io/version` labels change on all objects;
  - `checksum/config` changes, driven by the ConfigMap's labels, while `data.policy.yaml` is identical;
  - `image: …:v0.36.0` → `…:v0.37.0`;
  - in ClusterRole `descheduler`, the `pods` verbs go from `["get","watch","list","delete"]` to
    `["get","watch","list"]`.

  Nothing else changes, including the CronJob schedule, args (`--policy-config-file=/policy-dir/policy.yaml --v=3`),
  `concurrencyPolicy: Forbid`, and the repo's extra `descheduler-pvc` ClusterRole/Binding (not chart-owned, untouched).

**Blast radius (descheduler evicts cluster-wide).** When it acts, it evicts pods in every namespace
through the eviction API. That API honours PDBs; there are 13 PDBs live. Measured 2026-10-05: of 314
pods, 123 running pods are eligible. Protected are 81 PVC-mounting pods, 45 DaemonSet pods and 15
system-critical pods. No per-node or total eviction cap is configured, so if a node turns
under-utilized (most plausibly a freshly rebooted node after a Talos roll), one run could move many
eligible pods. **This plan does not change that behaviour.** It is stated so the window agent knows
what a misbehaving v0.37.0 run *could* do: evict stateless pods. Stateful pods are protected by the
unchanged PVC filter. The last 3 runs (2026-10-02..04) evicted 0 pods, because all three nodes sit above
the under-utilization thresholds.

**Net effect:** one HelmRelease upgrade that rewrites a CronJob spec, a ConfigMap (labels only) and a
narrower ClusterRole. Nothing restarts. The new image first runs at the next 04:00.

## 2. Pre-checks (all read-only; abort on any failure)

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py descheduler-0.37.0        # all PASS
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'              # header only
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'              # header only
git status --short -- kubernetes/apps/kube-system/descheduler         # empty (no foreign edits)
flux get sources git -n flux-system flux-system ; git rev-parse --short origin/main   # same revision = Step 0 settled
date +%H:%M                                                           # see §6: before 03:58 => §4.2 runs in-window
```

**2.1 Baseline of the last run.** §4.2 compares against it.
```bash
J=$(kubectl get jobs -n kube-system -o json | python3 -c "import sys,json; j=[x for x in json.load(sys.stdin)['items'] if x['metadata']['name'].startswith('descheduler-')]; j.sort(key=lambda x:x['metadata']['creationTimestamp']); print(j[-1]['metadata']['name'])")
echo $J
kubectl logs -n kube-system job/$J | grep -ciE 'Criteria for a node under utilization.*cpu="45\.00%" memory="40\.00%" pods="48\.00%"'   # 1 on 2026-10-04
kubectl logs -n kube-system job/$J | grep -ciE '"Number of evictions/requests"'                                                      # 1
kubectl logs -n kube-system job/$J | grep -cE '^E[0-9]{4} |forbidden'                                                                 # 0
```
Old job pods are garbage-collected: on 2026-10-05 only the newest job still had logs, and the older two
timed out. If the newest job also has no logs, record "no baseline" and rely on §4.2's absolute
criteria, which do not need a baseline.

**2.2 Policy and RBAC snapshot**, for §4.1's byte-compare:
```bash
kubectl get cm -n kube-system descheduler -o jsonpath='{.data.policy\.yaml}' > /tmp/descheduler-policy.before
shasum -a 256 /tmp/descheduler-policy.before   # 7824e53b6e3b2ca1cac97ef4a40b907798946170f38c844a8b5ae37fdeecce12 on 2026-10-05
```

## 3. Steps

Shared-worktree rule: use `git commit --only <path>`, then check `git log -1 --format=%s` (the subject is
yours) and `git show --stat HEAD` (exactly one file) BEFORE `git push`. The sed was dry-tested with
macOS BSD sed on a scratch copy. Resulting diff:
`12c12 <       version: 0.36.0 --- >       version: 0.37.0`.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/kube-system/descheduler/app/helmrelease.yaml
test "$(grep -c '^      version: 0\.36\.0$' $F)" = 1 || { echo ABORT; return 1 2>/dev/null || exit 1; }
sed -i '' 's/^      version: 0\.36\.0$/      version: 0.37.0/' $F
git diff -- $F     # exactly: -      version: 0.36.0  /  +      version: 0.37.0
git commit --only $F -m "feat(kube-system): descheduler chart 0.36.0 -> 0.37.0 (image v0.37.0)"
git log -1 --format=%s && git show --stat HEAD && git push
```
Flux picks this up via the push webhook; no manual reconcile is needed. Wait for
`kubectl get hr -n kube-system descheduler` to be Ready with a message naming `0.37.0`. Allow up to
10 min. If nothing has happened by then, check the webhook and the GitRepository revision first.

## 4. Verification

### 4.1 Immediate gates (right after the HR is Ready)

- **CronJob spec.**
  `kubectl get cronjob -n kube-system descheduler -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image} {.spec.schedule} {.spec.suspend}'`
  must print `registry.k8s.io/descheduler/descheduler:v0.37.0 0 4 * * * false`. A `v0.36.0` image means
  the upgrade did not apply. `true` means something suspended the job, which is also a FAIL.
- CONTENTS ASSERTION: the eviction policy is byte-identical. Measure it with
  `kubectl get cm -n kube-system descheduler -o jsonpath='{.data.policy\.yaml}' | shasum -a 256` and
  compare against the §2.2 hash (`7824e53b…ce12` on 2026-10-05). Any change to thresholds, plugins or
  the `ignorePvcPods` / `evictLocalStoragePods` flags changes the hash: FAIL, roll back (§5) BEFORE
  04:00. `diff /tmp/descheduler-policy.before <(…)` shows what moved.
- CONTENTS ASSERTION: eviction rights are intact and `delete` is gone.
  - `kubectl auth can-i create pods --subresource=eviction --as=system:serviceaccount:kube-system:descheduler -n default`
    must print `yes`.
  - `kubectl auth can-i delete pods --as=system:serviceaccount:kube-system:descheduler -n default`
    must print `no`. It read `yes` on 0.36.0, so this proves the new ClusterRole is live.
  - `kubectl auth can-i list persistentvolumeclaims --as=system:serviceaccount:kube-system:descheduler -A`
    must print `yes`. The PVC filter needs this.

  Negative control, measured 2026-10-05: the same eviction check `--as=system:serviceaccount:kube-system:nobody`
  prints `no`, so the probe can fail. Do NOT use `can-i create pods/eviction`: it prints `no` even when
  the right is granted.

### 4.2 First-run gate (the next 04:00 CronJob run after Ready)

Wait for a `descheduler-<n>` Job created after the HR became Ready. List the candidates with
`kubectl get jobs -n kube-system --sort-by=.metadata.creationTimestamp`. Then check:

- **The Job succeeded on the new image.**
  `kubectl get pods -n kube-system -l job-name=<J> -o 'custom-columns=IMG:.spec.containers[0].image,PHASE:.status.phase'`
  must print `…:v0.37.0  Succeeded`. A `Failed` phase or `kube_job_status_failed=1` is a FAIL. A failed
  run evicts nothing, so the failure mode is safe, but it is still a regression and calls for a rollback.
- CONTENTS ASSERTION: the policy parsed to OUR thresholds and the balance loop ran to completion.
  - `kubectl logs -n kube-system job/<J> | grep -ciE 'Criteria for a node under utilization.*cpu="45\.00%" memory="40\.00%" pods="48\.00%"'`
    must print `1`.
  - `kubectl logs -n kube-system job/<J> | grep -ciE '"Number of evictions/requests"'` must print `1`.

  A conversion or misparse regression that zeroes or drops the thresholds prints `0` on the first grep.
  A crash before completion prints `0` on the second. Both line formats were confirmed unchanged in the
  v0.37.0 source (`lownodeutilization.go`, `descheduler.go:252`), and both matched the 2026-10-04
  v0.36.0 log.
- CONTENTS ASSERTION: no RBAC or eviction errors, and no PVC-backed pod was evicted.
  - `kubectl logs -n kube-system job/<J> | grep -cE '^E[0-9]{4} |forbidden'` must print `0`. A
    `forbidden` here means the narrowed ClusterRole broke something.
  - For every `"Evicted pod"` line, check that the named pod's owner workload mounts no PVC:
    `kubectl logs -n kube-system job/<J> | grep -E '"Evicted pod"'` lists them, and it printed nothing
    on the last 3 runs.

    Any evicted pod from a workload with a `persistentVolumeClaim` volume means the PVC protection
    regressed. Treat that as an immediate FAIL: roll back (§5), and check that workload for Multi-Attach
    per `docs/sops/longhorn-rwo-multi-attach.md`.
  - Also record `totalEvicted=<n>` from the summary line. A sudden non-zero count with no
    under-utilized node in the classification lines would be a behaviour change: investigate it.
- CONTROL: metric kube_cronjob_status_last_successful_time — `{namespace="kube-system",cronjob="descheduler"}` must ADVANCE past the HR-Ready time (it read 2026-10-04T04:00:05Z on 2026-10-05). If it does not advance, the run never succeeded: FAIL.
- CONTROL: metric kube_job_status_succeeded — `{namespace="kube-system",job_name="<J>"}` = 1.
- CONTROL: metric kube_job_status_failed — `{namespace="kube-system",job_name="<J>"}` = 0. All three series exist live (kube-state-metrics), measured 2026-10-05.

**If the HR became Ready after 03:58**, §4.2 cannot run inside the window. The window agent must record
it as a next-morning follow-up for the sweep, with the job name pattern and these criteria. Until §4.2
passes, the plan is `awaiting-soak`, not `executed`.

## 5. Rollback

Nothing forward-only happens here: the workload is a stateless CronJob, with no PVC, no CRD and no
migration.

```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%h -- kubernetes/apps/kube-system/descheduler/app/helmrelease.yaml)
git show --stat $SHA          # confirm it is the 0.37.0 bump commit
git revert --no-edit $SHA && git log -1 --format=%s && git show --stat HEAD && git push
```
Confirm the cluster is back:
- the HR is Ready on 0.36.0;
- the §4.1 CronJob check prints `…:v0.36.0 0 4 * * * false`;
- `can-i delete pods` for the SA prints `yes` again;
- the policy hash equals §2.2.

**Emergency stop (the run itself misbehaves, e.g. it evicts PVC-backed pods).** A revert alone does
not stop a run that is already in progress, and the next 04:00 run would use whatever is reconciled by
then. To stop runs entirely while you investigate, set the chart value `suspend: true` in the same file,
via GitOps. The chart renders `.spec.suspend` from it (`templates/cronjob.yaml:18`). The edit sits
directly under `values:`:
```yaml
  values:
    kind: CronJob
    suspend: true
```
Commit it with `--only` and push. Confirm with
`kubectl get cronjob -n kube-system descheduler -o jsonpath='{.spec.suspend}'` → `true`. Any pod already
evicted has been rescheduled by its controller. Check PVC-backed ones for `Multi-Attach` events
(`kubectl get events -A --field-selector reason=FailedAttachVolume`).

## 6. Interference notes

- **Derives AUTO-NIGHT** by the policy inputs: risk low, `capability_change: false`,
  `rollback_class: git-revert`, and no `SHARED_INFRA_FLOOR` surface. `pod-placement` and `monitoring`
  are not storage, cni, gateway, etcd or dns, because the PVC filter keeps Longhorn out of reach. It
  fits `nightly`: 35 of the 70 schedulable minutes.
- **Run it FIRST among the nightly plans, right after Step 0**, so the HR is Ready before 03:58 and the
  04:00 run lands inside the 03:30–05:00 window. That makes §4.2 an in-window gate rather than a
  follow-up. If it cannot be first, it still runs correctly; only the evidence is deferred (§4.2 last
  paragraph).
- **Pre-existing, unchanged by this plan, and worth knowing:** the descheduler's own 04:00 run falls
  INSIDE every nightly window. A plan whose verification asserts "pod X was not restarted / rolled
  exactly once" can be confused by a descheduler eviction at 04:00. It evicted 0 pods on each of the
  last 3 nights, but that changes the morning after a node reboot. Not this plan's change, but the
  window agent should read `totalEvicted` from the 04:00 job log before blaming another plan.
- `flux-fleet-0.60.0`, `flux-oci-chart-sources`, `helm-drift-detection` and
  `flux-reconciler-impersonation` rewrite this HR, its source, or the controller that applies and
  reverts it. Never run any of them in the same window. Those plans should list this one back;
  reciprocity is not validated.
- After a Talos node roll (`talos-linux-1.14.2`), the next 04:00 run is the one most likely to evict at
  scale (an empty node classifies as under-utilized). Do not run THIS plan the night after a node roll:
  the §4.2 eviction review would then have to tell "new binary" apart from "expected rebalance".
- Retire this file (delete it) in the commit that records execution, once §4.2 has passed. Re-measure
  `F-160fc0dd` on the next security sweep rather than closing it by hand.
