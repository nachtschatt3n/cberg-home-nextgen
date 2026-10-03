---
plan_id: reloader-2.2.18
component: reloader                   # HelmRelease kube-system/reloader (chart `reloader`,
                                      # HelmRepository flux-system/stakater -> oci://ghcr.io/stakater/charts)
pr: null                              # no Renovate PR; held in the coverage.py PLAN lane (G3: release notes unavailable)
kind: chart
current: "chart 2.2.16 (image v1.4.21)"   # MEASURED live 2026-10-03: HR spec+lastAttemptedRevision 2.2.16 Ready,
                                          # deploy image ghcr.io/stakater/reloader:v1.4.21, 1/1 ready
target: "chart 2.2.18 (image v1.4.22)"    # chart 2.2.18 appVersion v1.4.22 (helm show chart); tag v1.4.22 on ghcr = HTTP 200
update_type: patch
risk: low                             # MEASURED: `helm template` 2.2.16 vs 2.2.18 with our exact values differs
                                      # ONLY in helm.sh/chart / chart / app.kubernetes.io/version / version labels
                                      # and the container image tag (v1.4.21 -> v1.4.22). Args, RBAC, ServiceAccount,
                                      # strategy, resources, PodMonitor: byte-identical. Stateless, no PVC.
est_duration_min: 45                  # §2 5 + §3 3 + Flux pickup/roll ~5 + §4 immediate gates 5 +
                                      # 30 min wait for the events-floor read (§4) - the window agent may run
                                      # other non-conflicting plans during that wait; slack 2
needs_reboot: false
exclusive: false
touches:
  namespaces: [kube-system]
  resources:                          # every object verified to EXIST live 2026-10-03 (kubectl get)
    - helmrelease/kube-system/reloader          # the only object this plan EDITS (spec.chart.spec.version)
    - deployment/kube-system/reloader           # image v1.4.21 -> v1.4.22; RollingUpdate 25%/25% at
                                                # replicas 1 => surge-first (new pod Ready before old exits)
    - podmonitor/kube-system/reloader           # label only
    - kubernetes/apps/kube-system/reloader/app/helmrelease.yaml
  shared:
    - reloader                        # 19 `auto` + 4 named reload annotations on top-level workloads
                                      # cluster-wide (measured 2026-10-03) depend on it to roll on
                                      # ConfigMap/Secret change; a broken reloader silently MISSES reloads
    - monitoring                      # §4 reads Prometheus (reloader PodMonitor series, kube-state-metrics)
depends_on: []
conflicts_with:
  - chart-patches-coredns-reloader-blackbox   # carried reloader 2.2.16 -> 2.2.17 as its item B; that item is
                                              # CARVED OUT into this plan (2026-10-03). Kept as a conflict until
                                              # the bundle's carve-out edit is re-reviewed, so the two can never
                                              # race on the same HelmRelease.
  - nextcloud-fleet-35.0.1            # its Commit A RELIES on a reloader roll of deployment/nextcloud; a reloader
                                      # restart in the same window can drop or double that roll
  - nextcloud-redis-hardening         # deployment/nextcloud-whiteboard is reloader-rolled on Secret change
  - external-dns-1.23.0               # external-dns pod carries a reloader annotation (it listed the bundle for this)
  - app-template-5.2.1                # edits ConfigMaps/Secrets of ~78 workloads; a reloader roll mid-§4 reads as
                                      # a missed/extra generation change (it listed the bundle for this)
  - helm-drift-detection              # its P2 adds driftDetection to helmrelease/kube-system/reloader
  - flux-oci-chart-sources            # moves HelmRepository sources incl. flux-system/stakater (this chart's source)
  - flux-reconciler-impersonation     # exclusive; rewrites how helm-controller applies this HR
  - flux-fleet-0.60.0                 # upgrades helm-/source-controller = this plan's apply AND revert path
                                      # No kube-prometheus-stack plan is open (91.4.1 executed). If one appears
                                      # it MUST be added here: §4 reads Prometheus.
capability_change: false              # v1.4.22 adds OPTIONAL leader-election timing flags (unset here; enableHA is
                                      # off, args are just --log-level=info), rejects non-positive pause-period
                                      # (0 pause-period annotations live), turns an invalid-regex panic into a
                                      # logged error (all 4 named-annotation values compile). Chart 2.2.18 only
                                      # tpl-renders image.repository/tag/digest - we set none of them. Same
                                      # behaviour for our config.
rollback_class: git-revert            # stateless controller, no PVC, no CRD, no migration
security_ref: F-0cf695f9              # reloader image finding; v1.4.22 is the bump (detail in the DB only)
finding_refs:
  - F-74a00f0b                        # "reloader: chart 2.2.16 → 2.2.18 (patch)" (version finding; moved here from
                                      # chart-patches-coredns-reloader-blackbox with the carve-out)
review: null
premises:
  # All read-only single commands. Values measured 2026-10-03.
  - id: reloader-hr-on-2-2-16
    why: >-
      §3's sed rewrites `version: 2.2.16`; the HR must be Ready and fully applied on 2.2.16 so a
      git revert lands on a known-good revision. Prints a different string and fails otherwise.
    run: kubectl get helmrelease -n kube-system reloader -o jsonpath='{.spec.chart.spec.version} {.status.lastAttemptedRevision} {.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: 2.2.16 2.2.16 True
  - id: reloader-image-v1-4-21
    why: >-
      §4 asserts the image moves v1.4.21 -> v1.4.22 and the replica count stays 1. Baseline must hold.
    run: kubectl get deploy -n kube-system reloader -o jsonpath='{.spec.template.spec.containers[0].image} {.spec.replicas} {.status.readyReplicas}'
    expect_exact: ghcr.io/stakater/reloader:v1.4.21 1 1
  - id: reloader-args-unchanged
    why: >-
      capability_change false rests on no HA / leader-election / pause flags being in use. If someone
      enabled HA or added flags since, the v1.4.22 leader-election and RBAC changes DO apply: stop, re-plan.
    run: kubectl get deploy -n kube-system reloader -o jsonpath='{.spec.template.spec.containers[0].args}'
    expect_exact: '["--log-level=info"]'
  - id: repo-pins-2-2-16-once
    why: "§3's sed assumes exactly one `      version: 2.2.16` line in the HR file (run from the repo root)."
    run: "grep -c '^      version: 2.2.16$' kubernetes/apps/kube-system/reloader/app/helmrelease.yaml"
    expect_exact: "1"
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/monitoring.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-03"
---

# reloader: Helm chart 2.2.16 -> 2.2.18 (image v1.4.21 -> v1.4.22)

## 1. Summary & why held

`kube-system/reloader` pins chart `reloader` 2.2.16 (image `v1.4.21`). Target is chart 2.2.18,
`appVersion: v1.4.22` (`helm show chart oci://ghcr.io/stakater/charts/reloader --version 2.2.18`).
This plan answers `F-74a00f0b`. The security driver is `security_ref: F-0cf695f9`; the detail is
on the DB record only.

**Why held:** coverage gate G3 could not read release notes. The chart tags `chart-v2.2.17` and
`chart-v2.2.18` have no CHANGELOG; their notes are on GitHub releases. **On investigation the hold
is a false positive for risk.** The upstream evidence, read 2026-10-03:

- **Image v1.4.22** (GitHub release `v1.4.22`, 2026-09-09, the only app release between v1.4.21 and
  the chart target). The release notes list:
  - "fix: reject non-positive pause-period durations" (#1208)
  - "feat: expose client-go leader election timings as flags and Helm values" (#1206)
  - "Move leases RBAC to *-metadata-reader role when HA is enabled" (#1106)
  - "chore: cleanup left over lease"
  - ubi9 base bump; "bump Go to 1.26.8 and spdystream to v0.5.1" (#1216)

  The `v1.4.21...v1.4.22` compare also has "fix: prevent panic on invalid regex in reload
  annotation" and "Surface invalid-regex errors to the call site". None of this reaches our config.
  `enableHA` is off: the live args are exactly `["--log-level=info"]`, and the rendered RBAC is
  identical. There are 0 `pause-period` annotations live. All 4 named `…reloader.stakater.com/reload`
  values (authentik-server/worker, configmap + secret) compile as regexes. That was checked with
  Python `re`; the values are plain object names, so RE2 accepts them too.
- **Chart 2.2.17** (2026-09-09) is a pure version bump to appVersion v1.4.22.
- **Chart 2.2.18** (GitHub release `chart-v2.2.18`, 2026-09-30) contains only "chore(chart):
  render image fields with tpl" (#1234), plus CI/PR-title workflow changes. The chart diff is
  `templates/deployment.yaml`: `image.repository`, `image.tag` and `image.digest` now go through
  `tpl`. `values.yaml` gets one comment line, and `Chart.yaml` the version. We set no `image.*`
  values, so `tpl` of the plain default `ghcr.io/stakater/reloader` / `v1.4.22` renders the same
  string.
- **Rendered diff with OUR values** (`helm template` 2.2.16 vs 2.2.18, 2026-10-03; 309 lines each):
  only the `helm.sh/chart`, `chart`, `app.kubernetes.io/version` and `version` labels change on
  all 7 objects, plus `image: "ghcr.io/stakater/reloader:v1.4.21"` → `"…:v1.4.22"`.
  2.2.17 → 2.2.18 alone differs ONLY in the chart labels.

**Net effect:** one surge-first pod roll of a stateless controller onto a patch image.

**Relationship to `chart-patches-coredns-reloader-blackbox`:** that vetted bundle carried this
component as item B, targeting 2.2.16 → **2.2.17**. The held target has since moved to 2.2.18. The
bundle is pinned to `sun-attended:2026-11-01` only because of its CoreDNS item. Its own §6 says that
A+B alone would derive AUTO-NIGHT, and its item C is already superseded by `coredns-1.48.1`. Item B
is therefore **carved out into this plan**, in the same commit. This keeps one live plan per
component, lets reloader land in a nightly window instead of waiting for November, and moves
`F-74a00f0b` here. The bundle keeps `F-0cf695f9` only as a citation, which it no longer needs.
`conflicts_with` names the bundle until that carve-out is re-reviewed.

## 2. Pre-checks (all read-only; abort on any failure)

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py reloader-2.2.18          # all PASS
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'             # header only
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'             # header only
git status --short -- kubernetes/apps/kube-system/reloader           # empty (no foreign edits)
flux get sources git -n flux-system flux-system ; git rev-parse --short origin/main   # same revision = Step 0 settled
```

**2.1 Log baseline.** §4 requires the same count after the change.
```bash
kubectl -n kube-system logs deploy/reloader | grep -ciE 'level=(warning|error|fatal)|panic'
# 1 on 2026-10-03: the startup `KUBERNETES_NAMESPACE is unset…` warning. Record the number.
kubectl -n kube-system logs deploy/reloader | grep -ciE 'starting controller to watch resource type: (configmaps|secrets)'
# 2 on 2026-10-03
```

**2.2 Prometheus baseline.** The port-forward stays up for §4.
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
q(){ curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(len(r)); [print(' ',{k:v for k,v in x['metric'].items() if k in ('pod','event_type','success')},x['value'][1]) for x in r]"; }
q 'up{job="kube-system/reloader"}'                                              # 1 series, value 1
q 'sum by (pod,event_type)(increase(reloader_events_received_total[30m]))'      # update > 0 (82.4 on 2026-10-03)
q 'sum by (success)(increase(reloader_reload_executed_total[7d]))'              # true ~41, false 0 (2026-10-03)
```
If the first query prints `0` series, the scrape is broken before the change, and every later
metric gate would read empty on both sides. STOP.

**2.3 Change log anchor** (for §5's missed-reload sweep): `date -u +%Y-%m-%dT%H:%M:%SZ` and note it.

## 3. Steps

Shared-worktree rule: use `git commit --only <path>`, then check `git log -1 --format=%s` (the
subject is yours) and `git show --stat HEAD` (exactly one file) BEFORE `git push`. The sed was
dry-tested with macOS BSD sed on a scratch copy. Resulting diff: `12c12 <       version: 2.2.16 --- >       version: 2.2.18`.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/kube-system/reloader/app/helmrelease.yaml
test "$(grep -c '^      version: 2\.2\.16$' $F)" = 1 || { echo ABORT; return 1 2>/dev/null || exit 1; }
sed -i '' 's/^      version: 2\.2\.16$/      version: 2.2.18/' $F
git diff -- $F     # exactly: -      version: 2.2.16  /  +      version: 2.2.18
git commit --only $F -m "feat(kube-system): reloader chart 2.2.16 -> 2.2.18 (image v1.4.22) (F-74a00f0b)"
git log -1 --format=%s && git show --stat HEAD && git push
```
Flux picks it up via the push webhook; no manual reconcile. Wait for
`kubectl get hr -n kube-system reloader` Ready, with a message naming `2.2.18`. Allow up to 10 min;
if nothing has happened by then, check the webhook / GitRepository revision first. Then run §4.

## 4. Verification

- Image + readiness. Run
  `kubectl get deploy -n kube-system reloader -o jsonpath='{.spec.template.spec.containers[0].image} {.status.readyReplicas} {.status.updatedReplicas}'`.
  It must print `ghcr.io/stakater/reloader:v1.4.22 1 1`. `rollout status` can green-light the OLD
  generation, so check the live pod as well:
  `kubectl get pods -n kube-system -l app.kubernetes.io/name=reloader -o 'custom-columns=N:.metadata.name,IMG:.spec.containers[0].image,RS:.status.containerStatuses[0].restartCount,START:.status.startTime'`
  must show exactly one pod, on `v1.4.22`, with restarts 0 after 5 min. A `v1.4.21` pod, or two pods
  more than 2 min after Ready, is a FAIL.
- CONTENTS ASSERTION: both informers start and the log is no noisier than before. Measured by
  `kubectl -n kube-system logs deploy/reloader | grep -ciE 'starting controller to watch resource type: (configmaps|secrets)'`
  → `2`, and
  `kubectl -n kube-system logs deploy/reloader | grep -ciE 'level=(warning|error|fatal)|panic'`
  → EQUAL to the §2.1 baseline (1 on 2026-10-03). Both greps are case-insensitive. The baseline line
  proves the grep matches this log format. An invalid-regex error, a pause-period rejection, an RBAC
  "forbidden" or a panic raises the count, which is a FAIL. A count of 0 means the startup warning
  vanished, so the log format or config changed: investigate before passing.
- CONTENTS ASSERTION: the new pod's informers actually receive update events, not just a Ready
  probe. Measured by
  `q 'sum(increase(reloader_events_received_total{event_type="update",pod="<NEW pod>"}[30m]))'`,
  read 30 min after the new pod's startTime. Floor `> 0`. Per the bundle's 24 h measurement
  (2026-09-27), the summed 30m form never read 0 (minimum 7.1); the 10m form read 0 in 38 of 144
  windows, so it is not used. It read 82.4 on 2026-10-03. A watch or RBAC regression leaves this at
  0 while the pod is Ready, which is a FAIL. Filter on the NEW pod name: the old pod's series linger
  until they go stale and would mask a dead new pod.
- CONTROL: metric up — `up{job="kube-system/reloader"}` = 1 with `pod=<NEW pod>`, so the PodMonitor scrapes the new pod. 0 series means the scrape broke, and the two metric gates in this section would read empty: FAIL.
- CONTROL: metric reloader_events_received_total — the `> 0` floor above, new pod only.
- CONTROL: metric kube_deployment_status_replicas_available — `{namespace="kube-system",deployment="reloader"}` = 1.
- CONTROL: metric reloader_reload_executed_total — soak, not a window gate. On the new pod, `{success="true"}` must be `> 0` within 48 h (the live rate is about 41 per 7 d) and `{success="false"}` must stay 0. The window agent records this as a follow-up for the next sweep. A `success="false"` increment on the new pod is a regression to raise as a finding.

Finally, `kill $PF`.

## 5. Rollback

Nothing forward-only happens: the controller is stateless, with no PVC, no CRD and no migration.

```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%h -- kubernetes/apps/kube-system/reloader/app/helmrelease.yaml)
git show --stat $SHA          # confirm it is the 2.2.18 bump commit
git revert --no-edit $SHA && git log -1 --format=%s && git show --stat HEAD && git push
```
To confirm the cluster is back: the HR is Ready on 2.2.16, and the §4 image check prints
`ghcr.io/stakater/reloader:v1.4.21 1 1`. Re-run §4's log gates against the §2.1 baseline.

**Missed reloads.** If the new pod was broken (Ready but not watching), any workload whose
ConfigMap/Secret changed in the meantime was NOT rolled. List the candidates:
`git log --since=<§2.3 anchor> --name-only --format= -- kubernetes/ | grep -iE 'configmap|secret|values' | sort -u`.
Out-of-git changes, such as Secrets written by operators or controllers, will not show there. Then
roll only the affected workloads, through their own GitOps path. Do not mass-restart.

## 6. Interference notes

- **Derives AUTO-NIGHT** by the policy inputs: risk low, `capability_change: false`,
  `rollback_class: git-revert`, and no `SHARED_INFRA_FLOOR` surface (`reloader` and `monitoring` are
  not storage/cni/gateway/etcd/dns). It fits `nightly` (45 of 90 min). Most of that is the 30-min
  events-floor wait, which is idle time and can overlap other non-conflicting plans.
- **Run it with no ConfigMap/Secret-changing plan in flight.** For ~10 s during the surge roll, the
  old and new pods watch at the same time. A change landing then is seen by both. That is harmless
  (both write the same hash, so the second write is a no-op), but it makes another plan's
  "rolled exactly once" gate ambiguous. That is why `nextcloud-fleet-35.0.1`,
  `nextcloud-redis-hardening`, `external-dns-1.23.0` and `app-template-5.2.1` are in
  `conflicts_with`.
- `helm-drift-detection`, `flux-oci-chart-sources`, `flux-reconciler-impersonation` and
  `flux-fleet-0.60.0` rewrite this HR, its source, or the controller that applies and reverts it.
  Never run them in the same window. Those plans should list this one back; reciprocity is not
  validated.
- Retire this file (delete it) in the commit that records execution, and run
  `runbooks/policy-cli.py finding close F-74a00f0b --commit <sha>`. Re-measure F-0cf695f9 on the next
  security sweep rather than closing it by hand.
