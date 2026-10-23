---
plan_id: falco-9.2.1
component: falco
pr: null                              # no Renovate PR exists (gh pr list --search falco, all states: [] on 2026-10-22);
                                      # coverage direct-bump lane. Held by G3 (release notes unverified) + earned
                                      # autonomy 0 green / 0 revert in 90d -- NOT by a breaking-change signal.
kind: chart
current: "9.2.0"
target: "9.2.1"
update_type: patch
risk: low
est_duration_min: 30                  # 1 commit + Flux; DaemonSet RollingUpdate maxUnavailable=1 over 3 nodes, each pod
                                      # re-runs falcoctl-artifact-install (pulls container plugin 0.7.5 + falco-rules from
                                      # ghcr/falcosecurity index) ~1-2 min/node; plus metacollector Deployment roll; plus
                                      # ~10 min of section 4 (wait for post-roll events in falco.log and in Wazuh).
needs_reboot: false
touches:
  namespaces: [security]
  resources:                          # every object verified to EXIST live 2026-10-22 (kubectl get)
    - kubernetes/apps/security/falco/app/helmrelease.yaml   # the ONE line edited: chart.spec.version
    - helmrelease/security/falco                  # chart 9.2.0 -> 9.2.1
    - daemonset/security/falco                    # rolls on all 3 nodes: image falco 0.45.0 -> 0.45.1; /host/proc
                                                  # mount gains readOnly: true; checksum/config + checksum/rules change
    - configmap/security/falco-falcoctl           # install ref plugin/container 0.7.4 -> 0.7.5
    - configmap/security/falco                    # label churn (checksum moves; values-derived content unchanged)
    - configmap/security/falco-rules              # label churn only
    - deployment/security/falco-k8s-metacollector # label churn only (subchart 0.3.2 -> 0.3.3). IMAGE STAYS 0.1.4:
                                                  # our values pin k8s-metacollector.image.tag "0.1.4" (see section 6)
    - service/security/falco-k8s-metacollector    # label churn only
    - "daemonset/security/falco-log-rotate: NOT changed (not chart-owned); its hostPath /var/run/falco is shared with falco"
    - "daemonset/security/wazuh-agent, statefulset/security/wazuh-manager-master: NOT changed; read by section 4.4"
  shared: [wazuh-siem]                # READ-only: falco is the runtime-event source for the Wazuh SIEM. Each node is
                                      # unmonitored for the ~1 min its falco pod restarts. No gateway/envoy, no
                                      # authentik, no storage, no CNI, no monitoring change.
depends_on: []
conflicts_with:
  - wazuh-100404-ci-build-tuning      # reloads the Wazuh manager's falco rule family; a falco re-roll the same night
                                      # confounds both plans' SIEM-volume gates (and section 4.4 here)
  - talos-linux-1.14.4                # exclusive node roll; restarts falco on every node mid-verification
  - talos-linux-1.14.2                # same (awaiting-go, superseded-by-1.14.4 pending)
  - cilium-1.20.3                     # exclusive; CNI roll fires cilium init-container execs falco would record + its
                                      # canaries read ds/falco-log-rotate
  - kube-prometheus-stack-92.2.0      # exclusive; section 4.1 reads Prometheus (kube-state-metrics) + ALERTS
  - kube-prometheus-stack-92.10.1     # exclusive; same reason
  - flux-fleet-0.60.0                 # swaps helm-controller, which performs this upgrade and the section 5 revert
  - flux-distribution-2.9.6           # same helm-controller apply/revert path
  - flux-reconciler-impersonation     # blocked; changes how helm-controller applies every HR
  - flux-oci-chart-sources            # rewires chart sources incl. ns security (falco); confounds which chart applied
  - helm-drift-detection              # writes a field on every HelmRelease incl. falco
exclusive: false
security_ref: null                    # not security-driven (dispatch brief + coverage). Falco 0.45.1 is a bugfix release.
capability_change: false              # same-behaviour patch: bugfixes in falco/libs/container plugin, chart fixes that
                                      # are no-ops for our values (ServiceMonitor gating -- ours is create:false) or a
                                      # TIGHTENING (/host/proc read-only). No new feature, route, permission, API,
                                      # exposure or rule. Upstream "Bug Fixes" section is the whole release.
rollback_class: git-revert            # stateless DaemonSet. No PVC, no DB, no migration. falco.log is a tmpfs hostPath
                                      # hand-off buffer (capped by falco-log-rotate), format unchanged. Plugins + rules are
                                      # re-pulled into emptyDirs on every pod start, so a revert re-pulls 0.7.4.
finding_refs: [F-550e5381]            # "falco: chart 9.2.0 -> 9.2.1 (patch)", section version (policy-cli finding list --grep falco)
review: ready-for-go@2026-10-23   # plan-reviewer 2026-10-23: premises 9/9, 0 blocking
status: vetted
window: nightly:2026-10-26   # not same night as talos/wazuh/cilium
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/falco.md
  - docs/sops/verification-contents-not-shape.md
premises:
  - id: live-chart-9.2.0
    why: "Diff/rollback baseline. Anything else = the plan is stale (or a Step 0 direct-bump already applied it)."
    run: kubectl get helmrelease falco -n security -o jsonpath='{.status.history[0].chartVersion}'
    expect_exact: "9.2.0"
  - id: helmrelease-ready
    why: "Do not stack a bump on an already-failing release."
    run: kubectl get helmrelease falco -n security -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: live-falco-image-0.45.0
    why: "Rollback baseline for the only workload image this hop changes."
    run: kubectl get ds falco -n security -o jsonpath='{.spec.template.spec.containers[?(@.name=="falco")].image}'
    expect_exact: "docker.io/falcosecurity/falco:0.45.0"
  - id: live-plugin-ref-0.7.4
    why: "Rollback baseline for the container plugin ref (the metadata-enrichment path section 4.3 asserts on)."
    run: kubectl get cm falco-falcoctl -n security -o jsonpath='{.data.falcoctl\.yaml}' | grep -o 'plugin/container:[0-9.]*' | sort -u
    expect_exact: "plugin/container:0.7.4"
  - id: driver-modern-ebpf
    why: >-
      Section 1's render diff (and the /host/proc readOnly change being safe) assumes driver.kind=modern_ebpf,
      i.e. no driver-loader init container that would need a writable /host/proc. Any other driver voids it.
    run: kubectl get helmrelease falco -n security -o jsonpath='{.spec.values.driver.kind}'
    expect_exact: "modern_ebpf"
  - id: metacollector-pin-0.1.4
    why: >-
      Section 1 states the metacollector image does NOT change because of this pin. If the pin moved or was
      removed, the render diff is void (the chart default is now 0.1.5).
    run: kubectl get helmrelease falco -n security -o jsonpath='{.spec.values.k8s-metacollector.image.tag}'
    expect_exact: "0.1.4"
  - id: falco-ds-fully-ready
    why: "Pre-state 3/3/3 (desired ready updated). A node already missing falco makes section 4 unattributable."
    run: kubectl get ds falco -n security -o jsonpath='{.status.desiredNumberScheduled} {.status.numberReady} {.status.updatedNumberScheduled}'
    expect_exact: "3 3 3"
  - id: wazuh-agent-ready
    why: "Section 4.4 proves events still reach Wazuh through the agent DaemonSet; it must be 3/3 before."
    run: kubectl get ds wazuh-agent -n security -o jsonpath='{.status.numberReady}'
    expect_exact: "3"
  - id: proc-mount-currently-rw
    why: >-
      Baseline for the CONTENTS ASSERTION in 4.2: on 9.2.0 the falco container's proc-fs mount has no readOnly
      field (empty). 9.2.1 must render "true". If it is already "true" someone else changed the template.
    run: kubectl get ds falco -n security -o jsonpath='{.spec.template.spec.containers[?(@.name=="falco")].volumeMounts[?(@.name=="proc-fs")].readOnly}' | wc -c | tr -d ' '
    expect_exact: "0"
generated: "2026-10-22"
---

# falco chart 9.2.0 -> 9.2.1 (Falco 0.45.0 -> 0.45.1)

## 1. Summary & why held

A patch bump of the falcosecurity `falco` chart in `security`. **The hold looks
like a false positive**: G3 could not fetch/verify release notes and earned
autonomy has no history (0 green / 0 revert in 90d) — there is no
breaking-change signal. I verified the notes and the rendered diff myself.

**Upstream evidence**:

- `falco/CHANGELOG.md` in the 9.2.1 chart tarball, quoted:
  > * Upgrade Falco to v0.45.1
  > * Bump the default `collectors.containerEngine.pluginRef` to `container:0.7.5`
  > * Do not render the `ServiceMonitor` when `metrics.enabled` is `false` … (falcosecurity/charts#1053)
  > * Mount `/host/proc` read-only in the Falco container whenever the driver loader does not run, including with `driver.kind=modern_ebpf` …
- Falco 0.45.1 GitHub release (published 2026-10-19). The whole release is
  "Bug Fixes", plus one non-user-facing build chore: libs 0.26.1 / driver
  11.0.1, the container plugin 0.7.5 ("listener shutdown fix for reloads"), a
  fix so `file_output` with `keep_alive: true` resumes after a failed write (we
  run `keep_alive: false`, so this does not apply to us), a metrics-scrape race
  fix (our metrics are off), and "avoid exiting when files in watched
  directories disappear during reload setup". It lists no breaking changes,
  config-key changes or rule-schema changes.
- Subcharts: `k8s-metacollector` 0.3.2 -> 0.3.3 (default app 0.1.4 -> 0.1.5).
  `falcosidekick` 0.14.0 -> 0.14.1 changes the redis image, but we run it
  `enabled: false`, so it renders nothing.

**Rendered diff**, with our live HelmRelease values. I ran
`helm pull` for both versions, then `helm template falco … -n security -f
<spec.values>` and diffed the output on 2026-10-22. The diff contains only
these lines:

| Object | Change |
|---|---|
| `ds/falco` container `falco` | `docker.io/falcosecurity/falco:0.45.0` -> `:0.45.1` |
| `ds/falco` volumeMount `proc-fs` (`/host/proc`) | gains `readOnly: true` (template now uses `driverLoader.enabled` helper; modern_ebpf has no loader) |
| `ds/falco` pod annotations | `checksum/config`, `checksum/rules` change. This forces the roll. |
| `cm/falco-falcoctl` | install ref `ghcr.io/falcosecurity/plugins/plugin/container:0.7.4` -> `0.7.5` |
| all chart objects | `helm.sh/chart` / `app.kubernetes.io/version` labels |
| `deploy/falco-k8s-metacollector` | labels only. **The image stays `k8s-metacollector:0.1.4`** because of our values pin |

`falcoctl` stays at 0.14.2. Nothing changes in the custom rules, the
`file_output` path, the hostPath mounts or the resources. The target artifacts
exist: `docker.io/falcosecurity/falco:0.45.1` returned manifest HTTP 200 and
`ghcr.io/falcosecurity/plugins/plugin/container:0.7.5` returned HTTP 200, both
on 2026-10-22.

**The real risk** is a different one: falco being briefly absent. While each
node's pod rolls (about 1 min per node, `maxUnavailable: 1`), that node has no
runtime monitoring. A new container plugin could also silently degrade
container metadata enrichment. That would not crash anything. It would null
`container.name` / `container.image.repository`, which would make every scoped
exclusion in `customRules` stop matching and flood Wazuh at level 12. Section
4.3 asserts that property directly.

## 2. Pre-checks

Run all premises:
`.venv/bin/python3 runbooks/plan-premises.py falco-9.2.1` → all PASS.

Then:

```bash
# 2.1 Flux healthy, nothing in flight for falco
flux get helmreleases -n security falco
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'     # expect header only (or nothing touching security)

# 2.2 Baseline enrichment + event flow per node (save output). Script used again in 4.3.
cat > /tmp/falco-enrich.py <<'EOF'
import sys, json, re
ev = []
for l in sys.stdin:
    if l.startswith('{'):
        try: ev.append(json.loads(l))
        except ValueError: pass
pod = [e for e in ev if re.fullmatch(r'[0-9a-f]{12}', str(e.get('output_fields', {}).get('container.id', '')))]
ok = [e for e in pod if e['output_fields'].get('container.image.repository') not in (None, '<NA>', '')]
print(f"events={len(ev)} pod_events={len(pod)} enriched={len(ok)} last={ev[-1]['time'] if ev else None}")
sys.exit(0 if ev and pod and len(ok) == len(pod) else 1)
EOF
for p in $(kubectl -n security get pods -l app.kubernetes.io/name=falco -o name); do
  printf '%s ' "$p"; kubectl -n security exec "$p" -c falco -- tail -n 500 /var/run/falco/falco.log | python3 -I /tmp/falco-enrich.py; echo " rc=$?"
done
```

Baseline measured 2026-10-22, with each node at `rc=0`:

- `falco-4vgpp` (nuc14-02): pod_events=500, enriched=500
- `falco-9tdf9` (nuc14-01): pod_events=55, enriched=55
- `falco-msn4n` (nuc14-03): pod_events=488, enriched=488

Not every event comes from a pod. Events with `container.id=runtime` are Talos
system-containerd processes such as `/opt/cni/bin/cilium-cni`. They carry no
image by design, so the script excludes them and counts only 12-hex pod
container ids. **STOP if any node is `rc=1` before the change.** In that case
enrichment is already broken and section 4.3 cannot attribute a failure to
this bump.

```bash
# 2.3 Wazuh is currently ingesting falco alerts (baseline for 4.4)
kubectl -n security exec wazuh-manager-master-0 -c wazuh-manager -- tail -n 3000 /var/ossec/logs/alerts/alerts.json \
  | python3 -c "
import sys,json
n=0;last=None
for l in sys.stdin:
    try: a=json.loads(l)
    except ValueError: continue
    if 'falco' in json.dumps(a.get('rule',{}).get('groups',[])).lower() or a.get('decoder',{}).get('name','').lower().startswith('falco') or 'falco' in a.get('location','').lower():
        n+=1; last=a.get('timestamp')
print('falco_alerts',n,'last',last)"
# 2026-10-22 baseline: falco_alerts 837, last within the same minute. STOP if 0 / last is stale (>15 min):
# the SIEM path is already down and 4.4 would prove nothing.
```

## 3. Steps

1. Edit the chart version. This was dry-tested with BSD sed on a scratch copy.
   The resulting diff is exactly
   `<       version: 9.2.0` / `>       version: 9.2.1` (line 12):

   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' 's/^      version: 9\.2\.0$/      version: 9.2.1/' kubernetes/apps/security/falco/app/helmrelease.yaml
   git diff --stat kubernetes/apps/security/falco/app/helmrelease.yaml   # expect: 1 file, 1 insertion, 1 deletion
   ```

   Do NOT touch the `k8s-metacollector.image.tag: "0.1.4"` pin in this plan.
   See section 6.

2. Commit only that path (shared worktree), then verify that the commit is
   yours and push:

   ```bash
   git commit --only kubernetes/apps/security/falco/app/helmrelease.yaml \
     -m "chore(falco): chart 9.2.0 -> 9.2.1 (Falco 0.45.1) (plan falco-9.2.1)" \
     -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
   git log -1 --format=%s          # must be the subject above
   git show --stat HEAD            # must list exactly the one helmrelease.yaml
   git push
   ```

3. Let the Flux webhook reconcile. The HR has `timeout: 15m` and
   `upgrade.remediation.strategy: rollback`, so a failed roll self-reverts the
   release. Watch it:

   ```bash
   kubectl -n security rollout status ds/falco --timeout=15m
   kubectl -n security rollout status deploy/falco-k8s-metacollector --timeout=5m
   ```

## 4. Verification

**4.1 Release and rollout state.** This is the floor of the check, not the
check itself.

```bash
kubectl get helmrelease falco -n security -o jsonpath='{.status.history[0].chartVersion} {.status.conditions[?(@.type=="Ready")].status}'; echo
#   expect: 9.2.1 True   (fails as "9.2.0 True" if remediation rolled back, or "... False")
kubectl get ds falco -n security -o jsonpath='{.status.desiredNumberScheduled} {.status.numberReady} {.status.updatedNumberScheduled}'; echo
#   expect: 3 3 3
kubectl -n security get pods -l app.kubernetes.io/name=falco -o custom-columns='POD:.metadata.name,NODE:.spec.nodeName,RESTARTS:.status.containerStatuses[*].restartCount,START:.status.startTime'
#   expect: 3 pods, one per node, START = this window, RESTARTS 0,0
```

CONTROL: metric kube_daemonset_status_number_ready — `{namespace="security",daemonset="falco"}` must read 3 (live 2026-10-22: 3); a stuck roll reads 2.
CONTROL: metric kube_daemonset_status_updated_number_scheduled — `{namespace="security",daemonset="falco"}` must read 3 after the roll; reads <3 while a node is still on the old template.
CONTROL: alertname WazuhAgentDaemonSetNotReady — must be NOT firing (the agent that tails falco.log is unaffected by this change; firing means a node-level problem confounds 4.4).
CONTROL: alertname ContainerMemoryNearLimit — must be NOT firing for `container="falco"` in ns security over the 15 min after the roll (falco limit 768Mi; a new plugin/libs memory regression shows here first).

```bash
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=kube_daemonset_status_updated_number_scheduled%7Bnamespace%3D%22security%22%2Cdaemonset%3D%22falco%22%7D' \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(r[0]['value'][1] if r else 'EMPTY')"
#   expect: 3   (EMPTY = instrument missing -> gate FAILS, do not read as pass)
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=ALERTS%7Balertstate%3D%22firing%22%2Calertname%3D~%22WazuhAgentDaemonSetNotReady%7CContainerMemoryNearLimit%22%2Cnamespace%3D%22security%22%7D' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='success'; print(len(d['data']['result']),'firing')"
#   expect: 0 firing
```

**4.2 CONTENTS ASSERTION: the new objects carry the 9.2.1 contents.**
Measured with the three commands below and compared against the section 2
premises (`0.45.0`, `0.7.4`, empty readOnly).

```bash
kubectl get ds falco -n security -o jsonpath='{.spec.template.spec.containers[?(@.name=="falco")].image}'; echo
#   expect: docker.io/falcosecurity/falco:0.45.1
for p in $(kubectl -n security get pods -l app.kubernetes.io/name=falco -o name); do
  kubectl -n security get "$p" -o jsonpath='{.status.containerStatuses[?(@.name=="falco")].image}{"\n"}'
done
#   expect: 3x docker.io/falcosecurity/falco:0.45.1  (the RUNNING pods, not just the template)
kubectl get cm falco-falcoctl -n security -o jsonpath='{.data.falcoctl\.yaml}' | grep -o 'plugin/container:[0-9.]*' | sort -u
#   expect: plugin/container:0.7.5
kubectl get ds falco -n security -o jsonpath='{.spec.template.spec.containers[?(@.name=="falco")].volumeMounts[?(@.name=="proc-fs")].readOnly}'; echo
#   expect: true   (premise proved it was empty on 9.2.0 -- so this line FAILS if the old template is still live)
kubectl get deploy falco-k8s-metacollector -n security -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
#   expect: docker.io/falcosecurity/k8s-metacollector:0.1.4  (pin held; 0.1.5 here means the values pin was lost)
```

**4.3 CONTENTS ASSERTION: falco still produces enriched events on every node
after the roll.** This is the property the bump could silently break. Measured
by re-running the section 2.2 loop, compared against the baseline:
- every node prints `rc=0`;
- `last=` is later than that pod's `START` from 4.1, which proves the NEW
  process wrote the events;
- `enriched == pod_events`.

Wait about 5 min after the last pod is Ready before running it.

The gate can fail, and here is why each failure condition triggers:

- `rc=1` with `enriched < pod_events` means the container plugin 0.7.5 is not
  resolving image/name metadata. The negative control proves the script
  catches it: feeding it one event with `container.id=abcdefabcdef` and
  `container.image.repository=null` printed `enriched=0` and `rc=1` on
  2026-10-22.
- `rc=1` with `events=0` means falco is not writing at all.
- `last=` from before START means the file only holds pre-roll lines.

On a low-volume node (nuc14-01 had only 55 pod events in its last 500 lines),
a `pod_events=0` result fails closed. Wait another 5 min, or widen to
`tail -n 2000` before calling it.

Also check falco's own log for errors since start. Transient
`[k8smeta] error during the RPC call` lines are baseline: there were 2 to 5
per pod in the last 500 lines on 2026-10-22, and the plugin retries and logs
"received at least one event". So exclude that one pattern and require the
recovery line. Both greps are case-insensitive.

```bash
for p in $(kubectl -n security get pods -l app.kubernetes.io/name=falco -o name); do
  L=$(kubectl -n security logs "$p" -c falco)
  printf '%s errors=%s k8smeta_ok=%s\n' "$p" \
    "$(printf '%s\n' "$L" | grep -iE '\[(error|critical)\]' | grep -viE 'k8smeta\] error during the RPC call' | wc -l | tr -d ' ')" \
    "$(printf '%s\n' "$L" | grep -ciE 'received at least one event from the k8s-metacollector')"
done
#   expect per pod: errors=0 k8smeta_ok>=1
#   errors>0  -> read the lines (a rule-load error crash-loops falco; see docs/sops/falco.md section 7)
#   k8smeta_ok=0 -> k8s enrichment never connected; 4.3 k8s.ns.name fields will be null -> FAIL
```

**4.4 CONTENTS ASSERTION: falco events still reach the SIEM.** Measured by
re-running the section 2.3 command. It must print `falco_alerts > 0` with a
`last` timestamp later than the last falco pod's START. This fails if the
`/var/run/falco` hostPath or the JSON format changed underneath the
wazuh-agent tail. Neither is expected from the render diff, but this is the
end-to-end property the household actually relies on.

## 5. Rollback

There is no state and nothing forward-only: no PVC, no DB, no migration.
Plugins and rules are re-pulled into emptyDirs on every pod start, and
falco.log is a capped tmpfs buffer with an unchanged format.

1. If the HR upgrade itself fails, helm-controller's
   `upgrade.remediation.strategy: rollback` already restores release 9.2.0.
   Confirm with
   `kubectl get hr falco -n security -o jsonpath='{.status.history[0].chartVersion}'`.
   Still revert in git (step 2) so the next reconcile does not retry the
   upgrade 3 times.
2. GitOps revert:

   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   git revert --no-edit <sha-of-step-3.2-commit>
   git log -1 --format=%s     # confirm it is the revert of the falco commit
   git push
   kubectl -n security rollout status ds/falco --timeout=15m
   ```

3. Confirm the cluster is back by re-running the section 2 premises
   `live-chart-9.2.0`, `live-falco-image-0.45.0`, `live-plugin-ref-0.7.4` and
   `falco-ds-fully-ready`. All must PASS. Then re-run the 4.3 loop and require
   `rc=0` on every node. Then re-run 4.4.

## 6. Interference notes

- **SIEM gap.** Each node runs without falco for about 1 min during the roll.
  Run this in the nightly window, not during known CI/build activity. No other
  workload restarts. `falco-log-rotate` and `wazuh-agent` are not chart-owned
  and do not roll.
- **`conflicts_with`.**
  - `wazuh-100404-ci-build-tuning` reloads the Wazuh-side falco rule family.
    Running both in one night makes each one's SIEM-volume and ingestion gates
    unattributable.
  - The talos, cilium and kube-prometheus-stack plans are exclusive anyway.
    They are listed because 4.1 reads Prometheus, and because a node/CNI roll
    restarts falco under our verification.
  - The flux/helm plans change the helm-controller path that applies the
    upgrade and the rollback.
- **The metacollector pin now lags.** `k8s-metacollector.image.tag: "0.1.4"`
  was added to move the image AHEAD of a stale subchart default (0.1.1). The
  9.2.1 subchart defaults to 0.1.5, so the pin now holds the image one patch
  BEHIND the default. I deliberately kept it out of this plan: it is a separate
  image change that needs its own evaluation. It should be bumped or dropped
  in a follow-up. Per the HR comment, re-verify by render.
- **The HR comment above `customRules` names "Falco 0.44.0's built-in
  exclusions".** That is cosmetic and stale since 9.x. No action is needed for
  this plan.
- **Rule content unchanged.** `falco-rules:5` is followed at runtime by
  falcoctl regardless of chart version. This bump does not change which
  rules ruleset is pulled.
