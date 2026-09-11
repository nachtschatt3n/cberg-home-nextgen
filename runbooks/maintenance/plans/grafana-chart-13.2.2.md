---
plan_id: grafana-chart-13.2.2
component: grafana
pr: null                          # no Renovate PR supplied with this held update;
                                  # verify no open PR exists before hand-editing
                                  # (grep open PRs titled "grafana" first)
kind: chart
current: "13.2.1"
target: "13.2.2"
update_type: patch
risk: low
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/grafana
    - deployment/grafana
    - pvc/grafana-config              # sqlite lives here; unaffected this hop
    - configmap/grafana-dashboards-default
    - configmap/grafana-dashboards-flux
    - configmap/grafana-dashboards-kubernetes
    - configmap/grafana-dashboards-nginx
    - configmap/grafana-dashboards-teslamate
    - servicemonitor/grafana
  shared: []                        # grafana does not restart shared infra;
                                    # it is itself a monitoring-namespace
                                    # tenant, not an infra component. It DOES
                                    # share ns `monitoring` with edot-collector
                                    # and kube-prometheus-stack — see
                                    # Interference notes.
depends_on: []
conflicts_with: []                  # see Interference notes — recommend
                                    # separate windows from
                                    # grafana-orphan-dashboard-uid rather than
                                    # a hard conflicts_with, since they CAN
                                    # share a window if sequenced correctly
security_ref: F-de4d92cd            # datasource-gate evidence this plan's
                                    # verification reuses; no new CVE driver
capability_change: false            # appVersion unchanged -> no user-visible
                                    # behaviour change (see Summary)
rollback_class: git-revert          # appVersion identical both sides -> no
                                    # sqlite migration crossed -> a plain git
                                    # revert is a real, complete rollback
finding_refs: [F-cce839da]
status: draft
window: null                        # recommend sat-attended:2026-09-19 (NOT
                                    # 2026-09-12 — that slot is already at
                                    # risk-load 7>6 / 100m in a 90m window;
                                    # see Interference notes) or
                                    # sun-attended:2026-09-13, either of which
                                    # has spare capacity today
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/grafana-image-changes.md
premises:
  - id: live-chart-still-13.2.1
    why: >-
      `current:` claims chart 13.2.1. If the cluster already moved (e.g. a
      manual bump, or another plan landed first), this plan's diff/rollback
      baseline is stale.
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "13.2.1"
  - id: live-image-still-13.2.1-distroless
    why: >-
      The whole "appVersion unchanged" safety argument rests on the RUNNING
      image being grafana:13.2.1-distroless with no tag override. If an
      `image.tag` pin was added since this plan was written, the appVersion
      analysis below no longer applies and must be redone.
    run: kubectl get deploy grafana -n monitoring -o jsonpath='{range .spec.template.spec.containers[?(@.name=="grafana")]}{.image}{end}'
    expect_exact: "docker.io/grafana/grafana:13.2.1-distroless"
  - id: helmrelease-ready
    why: "Do not stack this bump on top of an already-failing release."
    run: kubectl get helmrelease grafana -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: target-chart-appversion-unchanged
    why: >-
      This IS the plan's central claim: chart 13.2.2 must still ship
      appVersion 13.2.1 (identical to what runs today), or the low-risk /
      git-revert verdict below is void and this plan must be re-triaged as
      appVersion-unsafe per docs/sops/grafana-image-changes.md.
    run: helm show chart grafana-community/grafana --version 13.2.2 | grep '^appVersion:'
    expect_exact: "appVersion: 13.2.1"
  - id: current-chart-appversion-matches
    why: >-
      Confirms the CURRENT chart (13.2.1) also ships appVersion 13.2.1, so
      the comparison above is apples-to-apples and not an artifact of a stale
      local helm repo cache.
    run: helm show chart grafana-community/grafana --version 13.2.1 | grep '^appVersion:'
    expect_exact: "appVersion: 13.2.1"
generated: "2026-09-11"
---

# grafana: chart 13.2.1 -> 13.2.2 (patch)

## 1) Summary & why held

**This is the appVersion-neutral case the operator's grafana deny rule exists
to let a plan state explicitly, not the hazard case it exists to catch.**

`runbooks/auto-update-policy.yaml` routes **every** grafana chart bump to the
PLAN lane, unconditionally, because a grafana chart version move can silently
carry the Grafana **app** forward across a forward-only sqlite schema
migration (`grafana-config` PVC), which would downgrade the rollback from a
plain `git revert` to a restore-from-backup. That is a real, previously-hit
failure mode here: the 2026-09-06 bump to chart 13.0.1 was approved on the
explicit, checked condition that it shipped appVersion 13.2.0 (identical to
what was running), and the same HelmRelease comment block states that chart
13.1.0+ moves appVersion to 13.2.1 and was deliberately **not** taken at that
time for exactly this reason. The live cluster has since moved to chart
13.2.1 (appVersion 13.2.1) some time after that comment was written — the
gate correctly still routes this new hop here rather than assuming the prior
clearance still applies.

**Measured for this specific hop** (index:
`https://grafana-community.github.io/helm-charts` — the repository this
HelmRelease's `sourceRef` actually points at; `grafana.github.io` is a
different, frozen index at chart 10.5.15 and answers the wrong question if
queried instead), two independent ways:

1. Direct fetch + parse of the repo's `index.yaml` (2026-09-11):
   ```
   13.2.2   appVersion 13.2.1   created 2026-09-06T20:56:35Z
   13.2.1   appVersion 13.2.1   created 2026-09-04T15:14:29Z   <- live today
   13.2.0   appVersion 13.2.1   created 2026-09-04T02:02:08Z
   13.1.0   appVersion 13.2.1   created 2026-09-03T07:15:11Z
   13.0.1   appVersion 13.2.0   created 2026-08-28T21:18:19Z
   ```
2. `helm show chart grafana-community/grafana --version {13.2.1,13.2.2}` —
   both report `appVersion: 13.2.1` (also cross-checked via
   `helm search repo grafana-community/grafana --versions`, which further
   confirms **13.2.2 is the newest chart published as of this check** — no
   later version has shipped that this plan would be silently stale against).

**Conclusion: appVersion is UNCHANGED (13.2.1 -> 13.2.1).** No Grafana app
version move, so no additional forward-only sqlite migration is crossed by
this hop specifically. The deny rule's hazard does not apply to *this* bump
(it did, correctly, the last time this component was planned). Per the SOP
("roll the variant, never the version") and the policy comment's own
precedent, that makes `git revert` a real rollback and downgrades this from
what the deny rule generically implies to a genuinely low-risk change — stated
here rather than assumed, and re-checked at execution time via the
`premises:` above rather than trusted from today.

**appVersion-unchanged also means the container image is byte-identical.**
The chart's own `values.yaml` sets `image.tag: "{{ .Chart.AppVersion
}}-distroless"` with no digest pin either side — since `AppVersion` is
`13.2.1` for both chart 13.2.1 and 13.2.2, the rendered image reference is
`grafana/grafana:13.2.1-distroless` **on both sides of this bump**. This is
not a version bump for the running binary at all; it is a chart-packaging
patch only. Live-confirmed running image today:
`docker.io/grafana/grafana:13.2.1-distroless` (`kubectl get deploy grafana -n
monitoring -o jsonpath=...`).

**Render-diff against OUR real values** (`helm template` of chart 13.2.1 vs
13.2.2, both fed the actual `spec.values` block from
`kubernetes/apps/monitoring/grafana/app/helmrelease.yaml` — not chart
defaults): the two renders differ in exactly two ways, both routine and
neither structural:

- `helm.sh/chart: grafana-13.2.1` -> `grafana-13.2.2` on every labeled object
  (expected on any chart bump; carries no behavioural meaning).
- `checksum/dashboards-json-config` on the Deployment pod template changes —
  this is a direct, mechanical consequence of the label above: the checksum
  hashes the rendered `dashboards-json-configmap.yaml`, and that ConfigMap's
  own `helm.sh/chart` label is part of what gets hashed. It is not evidence of
  a dashboard-content change (dashboard JSON, `dashboardproviders.yaml`
  wiring, and the `sc-dashboard-provider` config are byte-identical across
  the diff). It WILL force a Deployment rollout (see below), same as the
  label change alone would.
- `app.kubernetes.io/version: "13.2.1"` is present and **unchanged** on both
  sides — a second, independent confirmation of the appVersion finding above,
  now from the rendered manifest rather than the chart's own metadata.

The one template-level change in the chart source between 13.2.1 and 13.2.2 is
in `templates/servicemonitor.yaml`: it adds an optional
`.Values.serviceMonitor.labels.release` override (falls back to
`.Release.Name` if unset). We do not set `serviceMonitor.labels`, so the
rendered `ServiceMonitor` is identical either way (`release: "grafana"` on
both renders) — confirmed, not assumed.

**`Deployment.spec.selector.matchLabels` is unchanged** between the two
renders (`app.kubernetes.io/name: grafana`, `app.kubernetes.io/instance:
grafana` on both) — **no immutable-selector conflict, no delete-recreate
required.** The existing `deploymentStrategy: Recreate` + single replica +
RWO `grafana-config` PVC already handles the ordinary rollout this bump
triggers (old pod terminates and releases the volume before the new one
starts); this is the chart's steady-state behaviour, not something new to
this hop.

**Net assessment:** this is the "the hold was appropriate to check, and the
check comes back negative" case, not a false-positive hold — the deny rule
did its job by forcing this measurement rather than letting a possible
appVersion move slip through unattended. Given the confirmed appVersion match
and the trivial render-diff, `risk: low` / `rollback_class: git-revert` is the
honest verdict for *this specific hop*, not a blanket judgment about grafana
chart bumps in general (the next hop must be re-measured the same way).

## 2) Pre-checks

Run all `premises:` above first (`plan-premises.py grafana-chart-13.2.2`).
Then:

```bash
# Cluster health baseline before touching anything
kubectl get helmrelease grafana -n monitoring
kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana
kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana \
  -o jsonpath='{.items[0].status.containerStatuses[*].restartCount}{"\n"}'

# Baseline datasource/plugin counts (compare against these post-bump — this
# is the datasource gate from docs/sops/grafana-image-changes.md, mandatory
# for ANY grafana change even one this trivial)
U=$(kubectl get secret grafana-admin-secret -n monitoring -o jsonpath='{.data.admin-user}' | base64 -d)
P=$(kubectl get secret grafana-admin-secret -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d)
kubectl port-forward -n monitoring svc/grafana 33001:80 &
sleep 4
curl -s -u "$U:$P" 'http://127.0.0.1:33001/api/plugins?embedded=0&type=datasource' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("bundled="+str(len(d))); print(sorted(p["id"] for p in d))'
kill %1

# Confirm no other in-flight reconcile against this HelmRelease
flux get helmrelease grafana -n monitoring
```

Record the baseline plugin count and list — it is the pass/fail bar in §4.

## 3) Steps (GitOps)

No alert-silence step required (risk is low, no image change, pod restart is
brief and Grafana already has no cross-app dependents whose alerts would fire
off Grafana's own unavailability alone) — but if the window agent prefers
consistency with `docs/sops/application-update.md` for any grafana touch, a
short (1h) silence on `alertname=~"Grafana.*|KubePodNotReady.*"` scoped to
`namespace=monitoring` is harmless belt-and-suspenders.

1. Edit the chart version pin:
   ```
   # kubernetes/apps/monitoring/grafana/app/helmrelease.yaml
   spec:
     chart:
       spec:
         chart: grafana
         version: 13.2.1     # ->
         version: 13.2.2
   ```
2. Add a dated comment line to the existing history block (do not delete the
   prior history — it is load-bearing evidence for the next planner):
   ```
   # 2026-09-1x: chart 13.2.2 — routine patch. appVersion UNCHANGED at 13.2.1
   # (measured against both chart 13.2.1 and 13.2.2 via
   # grafana-community.github.io/helm-charts index + `helm show chart`), so
   # this hop crosses no sqlite migration; git-revert remains a real
   # rollback. Plan: grafana-chart-13.2.2. Finding: F-cce839da.
   ```
3. Commit and push:
   ```bash
   git commit --only kubernetes/apps/monitoring/grafana/app/helmrelease.yaml \
     -m "chore(monitoring): grafana chart 13.2.1 -> 13.2.2 (plan grafana-chart-13.2.2, appVersion unchanged at 13.2.1)"
   git push
   ```
4. Let Flux reconcile (interval 30m on this HelmRelease's Kustomization) or,
   since this is an attended window action, force it:
   ```bash
   flux reconcile kustomization grafana -n flux-system --with-source
   flux get helmrelease grafana -n monitoring --watch=false
   ```
5. Watch the `Recreate` rollout (single replica, RWO PVC — expect the pod to
   fully terminate before the replacement starts, same as any grafana bump):
   ```bash
   kubectl rollout status deployment/grafana -n monitoring --timeout=180s
   kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana
   ```

## 4) Verification

Floor checks (shape — necessary but not sufficient on their own):
```bash
kubectl get helmrelease grafana -n monitoring \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# expect: True 13.2.2
flux get kustomization grafana -n flux-system
kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana
kubectl get deploy grafana -n monitoring \
  -o jsonpath='{range .spec.template.spec.containers[?(@.name=="grafana")]}{.image}{"\n"}{end}'
# expect: docker.io/grafana/grafana:13.2.1-distroless (UNCHANGED — this is
# the whole point; a different tag here means the appVersion premise above
# was wrong and this needs to stop)
kubectl logs -n monitoring -l app.kubernetes.io/name=grafana -c grafana --tail=50 | grep -i "migrations completed"
# expect: "performed=0" on every migrator — schema untouched, confirms the
# appVersion-unchanged claim from the RUNNING pod, not just the chart metadata
```

**CONTENTS ASSERTION — the datasource gate from
`docs/sops/grafana-image-changes.md`, mandatory for any grafana change** (a
healthy pod serving an empty plugin catalog is exactly the failure this repo
has hit before, at `-slim`; a chart-only patch should not regress this, but
"should not" is not "verified doesn't"):

```bash
U=$(kubectl get secret grafana-admin-secret -n monitoring -o jsonpath='{.data.admin-user}' | base64 -d)
P=$(kubectl get secret grafana-admin-secret -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d)
kubectl port-forward -n monitoring svc/grafana 33001:80 &
sleep 4

# bundled/plugin count — compare to the §2 baseline, must not be lower
curl -s -u "$U:$P" 'http://127.0.0.1:33001/api/plugins?embedded=0&type=datasource' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d)); print(sorted(p["id"] for p in d))'

# every provisioned datasource resolves AND returns data
for uid in prometheus elasticsearch influxdb unpoller-influxdb pellets TeslaMate; do
  printf '%s -> ' "$uid"
  curl -s -u "$U:$P" -X POST "http://127.0.0.1:33001/api/datasources/uid/$uid/health" \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("status"), "|", str(d.get("message"))[:60])'
done
curl -s -u "$U:$P" 'http://127.0.0.1:33001/api/datasources/proxy/uid/alertmanager/api/v2/status' | head -c 120
curl -s -u "$U:$P" -H 'Content-Type: application/json' -X POST \
  'http://127.0.0.1:33001/api/ds/query' \
  -d '{"queries":[{"refId":"A","datasource":{"uid":"prometheus","type":"prometheus"},"expr":"count(kube_pod_info)","instant":true}]}'
# expect: a non-empty numeric result, not an error frame

# sidecar-provisioned dashboards still load — pick one from each folder that
# depends on the sidecar (not the `dashboards:` block, which is a different
# provisioning path and would not catch a sidecar regression)
curl -s -u "$U:$P" 'http://127.0.0.1:33001/api/search?query=' | python3 -m json.tool | head -40
kill %1
```

```bash
# Prometheus target count unchanged (grafana's own ServiceMonitor still scraped)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
sleep 2
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import sys, json
t = json.load(sys.stdin)['data']['activeTargets']
g = [x for x in t if x['labels'].get('job')=='grafana' or 'grafana' in x['labels'].get('instance','')]
print('grafana targets:', len(g), [x['health'] for x in g])
print('total up:', sum(1 for x in t if x['health']=='up'), '/', len(t))"
kill %1

# no NEW firing alerts (ignore Watchdog/InfoInhibitor, per repo convention)
curl -s http://localhost:9090/api/v1/alerts | grep -o '"alertname":"[^"]*"' | grep -vE 'Watchdog|InfoInhibitor' | sort -u
```

**PASS criteria:** HelmRelease Ready at chart 13.2.2; running image tag still
`13.2.1-distroless`; migration log shows `performed=0`; bundled/datasource
plugin count and list not lower than the §2 baseline; all six datasource
health checks OK; Alertmanager proxy returns config; `/api/ds/query` returns
a number; `/api/search` still lists the sidecar-provisioned dashboards;
grafana's Prometheus target still `up` and total target count unchanged;
Grafana UI login succeeds with the admin secret; no new (non-Watchdog/
InfoInhibitor) firing alerts.

## 5) Rollback

Chart-version-only change, appVersion unchanged both directions, so this is a
plain git revert with no data-migration concern:

```bash
git revert --no-edit <bump-commit-sha>
git push
flux reconcile kustomization grafana -n flux-system --with-source
kubectl rollout status deployment/grafana -n monitoring --timeout=180s
kubectl get deploy grafana -n monitoring \
  -o jsonpath='{.spec.template.spec.containers[?(@.name=="grafana")].image}{"\n"}'
# confirm back to docker.io/grafana/grafana:13.2.1-distroless (it never
# actually changed, so this should already be true even mid-rollback)
kubectl get helmrelease grafana -n monitoring \
  -o jsonpath='{.status.history[0].chartVersion}{"\n"}'
# confirm back to 13.2.1
```

Re-run the §4 CONTENTS ASSERTION block after rollback to confirm datasources
are healthy on the reverted chart.

No `grafana-config` PVC / sqlite restore path is needed at any point in this
plan — there is no schema migration to be behind on either direction.

## 6) Interference notes

- **Two plans already share namespace `monitoring` in window
  `sat-attended:2026-09-12`**: `edot-collector-0.160.0` (vetted, medium,
  25min) and `grafana-orphan-dashboard-uid` (awaiting-go, low, 30min). That
  slot is already over-committed per `maintenance-plan.py --open`
  (risk-load 7>6, ~100min of work against a 90min window). **Do not add this
  plan to that window.** Recommended instead: `sat-attended:2026-09-19`
  (currently only `media-audit-durable-output`, 45min low) or
  `sun-attended:2026-09-13` (currently `absenty-drop-npm-runtime` 60min low +
  `authentik-pg18-lockstep` 35min medium) — both have spare capacity for a
  15min low-risk addition today; re-check `--open` at scheduling time since
  the queue moves.

- **`grafana-orphan-dashboard-uid` touches the SAME component and the SAME
  two resources this plan touches** (`deployment/grafana`,
  `pvc/grafana-config`). Its method is a live `kubectl debug ... --target
  grafana` session attached to the *currently running* grafana pod, deleting
  one sqlite row directly on the PVC. This plan's chart bump forces a
  `Recreate` rollout (new pod, new name) purely from the label/checksum
  change described in §1, even though the image is unchanged.

  **Ordering, if the two ever land in the same window:** run this chart bump
  **first**. Reasoning: the orphan-uid fix's `kubectl debug --target grafana`
  step needs a stable, already-running grafana pod to attach to; running the
  chart bump afterward would recreate that exact pod mid-fix-verification (or
  immediately after), forcing the orphan-uid plan's operator to re-verify
  against a different pod name than the one they just debugged into. Bumping
  the chart first yields one clean Recreate cycle, a stable pod, and *then*
  the orphan-uid plan's debug session and its own verification both run
  against a pod that will not be replaced out from under them.

  Preferred outcome remains: **different windows** (per the capacity note
  above), which sidesteps the ordering question entirely. `conflicts_with` is
  left empty rather than set, because the two plans are compatible if
  sequenced as described — this is a should-avoid, not a must-not-combine.

- **No shared infra is perturbed.** Grafana bumps do not restart
  ingress/gateway, cert-manager, CNI, CoreDNS, or a shared database — grafana
  is a tenant of `monitoring`, not infrastructure other namespaces depend on.
  `kube-prometheus-stack` has `grafana.enabled: false`, so this HelmRelease is
  the sole owner and nothing else reconciles Grafana concurrently.

- **No node reboot.** Single-replica Deployment, `Recreate` strategy already
  set, RWO Longhorn PVC (`grafana-config`) already correctly handled by that
  strategy — this bump does not change any of that config.

- **Re-run the appVersion premises at execution time, not just at planning
  time.** This plan's low-risk verdict is conditioned entirely on the
  measurement in §1 still holding — if chart 13.2.2 gets repackaged (rare but
  not impossible for a `helm-charts` repo) or a later plan changed the
  HelmRelease's `image.tag`, the whole argument for `git-revert` collapses and
  this plan should be blocked pending re-triage, not executed on stale
  confidence.
