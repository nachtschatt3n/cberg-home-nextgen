---
plan_id: kube-prometheus-stack-88
component: kube-prometheus-stack
pr: null                            # not found in the current open PR set (194/196/197/198);
                                    # window agent: reconcile the real Renovate PR # before executing
kind: chart
current: "87.17.0"
target: "88.1.2"                     # target moved 88.0.1 → 88.1.2 (sweep 2026-08-02);
                                    # analysis below was done at 88.0.1 — the executor
                                    # MUST re-check the 88.1.0→88.1.2 point-release delta
                                    # (operator/CRD changes) before running the window.
update_type: major
risk: high                          # severity is medium; set HIGH deliberately — this is the
                                    # cluster-wide observability substrate + a CRD-changing major.
                                    # HIGH routes it to the operator-present Sun window, which is right.
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [monitoring, storage] # CRDs are CLUSTER-SCOPED — the replace touches
                                    # monitoring.coreos.com objects in EVERY namespace
  resources:
    - helmrelease/kube-prometheus-stack
    - crd/prometheuses.monitoring.coreos.com
    - crd/alertmanagers.monitoring.coreos.com
    - crd/alertmanagerconfigs.monitoring.coreos.com
    - crd/prometheusrules.monitoring.coreos.com
    - crd/servicemonitors.monitoring.coreos.com
    - crd/podmonitors.monitoring.coreos.com
    - crd/probes.monitoring.coreos.com
    - crd/scrapeconfigs.monitoring.coreos.com
    - crd/prometheusagents.monitoring.coreos.com
    - crd/thanosrulers.monitoring.coreos.com
    - deployment/kube-prometheus-stack-operator
    - statefulset/prometheus-kube-prometheus-stack-prometheus
    - statefulset/alertmanager-kube-prometheus-stack-alertmanager
    - daemonset/kube-prometheus-stack-prometheus-node-exporter
    - deployment/kube-prometheus-stack-kube-state-metrics
    - pvc/prometheus-kube-prometheus-stack-prometheus-db-*   # longhorn, DO NOT delete
    - pvc/alertmanager-kube-prometheus-stack-alertmanager-db-* # longhorn, DO NOT delete
  shared: [monitoring, prometheus-operator-crds]   # observability substrate — every app's
                                    # metrics + alerting flow through this stack
depends_on: []
conflicts_with: []                  # no hard resource conflict, but see Interference notes:
                                    # run FIRST/solo — its rollout briefly blinds cluster-wide alerting
status: draft                       # still DRAFT — must be finalized (vetted→scheduled)
                                    # before it will execute; reslotted only (2026-08-10).
window: "sat-early:2026-08-22"      # RESLOTTED from missed 2026-08-08. no-reboot ⇒ Sat,

cve_impact: |                         # added 2026-08-14 during CVE triage
  This chart bump is the single highest-value CVE action open. It clears THREE
  of the 25 open fixable-CRITICAL findings at once, all of them inside the
  kube-prometheus-stack render:
    - docker.io/grafana/grafana:12.3.1        9 fixable CRITICAL (-> 12.4.8 / 12.3.10)
    - quay.io/kiwigrid/k8s-sidecar:2.5.0      2 fixable CRITICAL (-> 2.10.1)
    - docker.io/curlimages/curl:8.9.1         2 fixable CRITICAL (-> 8.21.0)
  = 13 criticals. The curl one is NOT the otel-ilm Job (that is already pinned
  at 8.21.0 in git) — it is grafana's dashboard-download sidecar, which is why
  it has no git pin of its own and only moves with this chart.
  Target drift: plan says 88.1.2, upstream is now 88.3.0 — re-target before the
  window. Verify the rendered grafana/sidecar/curl tags with `helm template`
  before commit, and check the Deployment images afterwards (not just HR Ready).
                                    # not Sun. SOLO (alerting blind 2-5m) — 2026-08-15 sat
                                    # is taken by app-template-5.0 ⋂ envoy phase0/1, so this
                                    # gets the next clean solo Sat window.
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/maintenance-windows.md
  - docs/sops/monitoring.md
generated: "2026-08-02"
---

# kube-prometheus-stack 87.17.0 → 88.0.1 (chart major)

## 1) Summary & why held

**What changes.** A single Helm chart major: `kube-prometheus-stack` 87.17.0 →
88.0.1. The only substantive upstream change across 88.0.0/88.0.1 is
**prometheus-operator v0.92.x → v0.93.0**, which bumps the operator image, the
config-reloader image, node-exporter + kube-state-metrics images, and — the
reason it's a *major* — the **10 `monitoring.coreos.com` CRDs**
(alertmanagerconfigs, alertmanagers, podmonitors, probes, prometheusagents,
prometheuses, prometheusrules, scrapeconfigs, servicemonitors, thanosrulers).

**Why the auto-updater held it.** Gate **G1 (type)**: `update_type == major` is
never auto-safe (SOP `auto-update.md`). Correctly held — a chart major on the
stack that runs Prometheus + Alertmanager + the operator CRDs is exactly a
"non-safe, execute-deliberately" update.

**Is it actually breaking for us?** The prometheus-operator v0.93.0 API changes
are **additive / backward-compatible for this cluster** — none require a config
migration:

| v0.93.0 change | Impact here |
|---|---|
| uint→int Go types + **reject negative values** (new API validation) | Additive validation. Every field we set (retention, resources, `for:`, thresholds) is positive → **safe**. |
| Default `.spec.shards` now = 1 for Prometheus/PrometheusAgent | We don't set `shards`; effective value was already 1 → **no-op**. |
| New `TSDBSpec.chunkEncoding` field | Additive, unset → **no-op**. |
| AlertmanagerConfig Slack `updateMessage` field | We route to **Telegram**, not Slack → **irrelevant**. |
| Operator stops auto-disabling compaction w/ Thanos sidecar | **No Thanos** in this cluster → **irrelevant**. |
| Remote-write metadata disabled on message v2.0 | **No remote-write** configured → **irrelevant**. |

So there is **no schema migration** to perform and no expected loss of our custom
config. The real risk of this upgrade is **operational, not migratory**:

1. **The CRD apply itself (biggest gotcha).** `helmvalues.yaml` sets
   `crds.enabled: true`, so the CRDs render as templated release resources and
   are applied by the Helm upgrade path (client-side). The `prometheuses`,
   `alertmanagers` and `prometheusagents` CRDs are **very large** and a
   client-side apply of the *changed* schemas can fail with
   `metadata.annotations: Too long: must have at most 262144 bytes`. The
   documented-safe path (chart `UPGRADE.md`) is to **`kubectl apply
   --server-side` the 10 v0.93.0 CRDs BEFORE** the chart bump — Step 3 below.
2. **Cluster-wide monitoring blindness during rollout.** The new operator
   reconciles the Prometheus + Alertmanager StatefulSets → rolling restart;
   node-exporter (DaemonSet) + kube-state-metrics also get new images → rolling
   restart. Expect **~2–5 min of gappy metrics / no alert evaluation** while
   pods cycle. A broken stack means we go blind — hence risk `high` +
   operator-present window + the heavy Verification section.
3. **Our tuned rule surface must survive.** ~30 custom `PrometheusRule` files
   (selected by `ruleSelector matchLabels release=kube-prometheus-stack`), the
   `telegram` `AlertmanagerConfig` (v1alpha1), and the **disabled/replaced**
   stock rules (`defaultRules.disabled` + `defaultRules.rules`) must all still
   load with the new operator. Verification proves this.

**Decoupled (NOT touched):** Grafana runs as a **separate HelmRelease**
(`kubernetes/apps/monitoring/grafana`, `grafana.enabled: false` in this chart) —
this bump does **not** restart Grafana. `sweep-dashboard` is its own Deployment,
unrelated to Grafana/this chart. Both stay up.

> `pr:` is `null` because no open PR for this bump was found in the current set
> (open: #194 Talos, #196 n8n, #197/#198 coredns). The window agent must fill in
> the real Renovate PR number (or confirm it was superseded) before executing.

## 2) Pre-checks

```bash
# --- Flux + cluster baseline ---
flux get helmreleases -A | awk 'NR==1 || $NF!="True"'          # everything Ready
flux get kustomizations -A | awk 'NR==1 || $NF!="True"'
kubectl get pods -n monitoring | grep -vE 'Running|Completed'  # expect empty
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -20

# --- confirm target chart 88.0.1 is published in the HelmRepository index ---
kubectl get helmrepository -n flux-system prometheus-community -o jsonpath='{.status.artifact.revision}{"\n"}'
# (or) flux -n flux-system get source helm prometheus-community

# --- capture the pre-upgrade rule/alert baseline (compare after) ---
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
PF=$!; sleep 3
# total rule/group count
curl -s localhost:9090/api/v1/rules | python3 -c "import sys,json;d=json.load(sys.stdin)['data']['groups'];print('groups',len(d),'rules',sum(len(g['rules']) for g in d))"
# prove our DISABLED stock rules are ABSENT and our TUNED replacements are present
curl -s localhost:9090/api/v1/rules | python3 -c "
import sys,json
names={r['name'] for g in json.load(sys.stdin)['data']['groups'] for r in g['rules']}
dis=['KubeAPIDown','KubeControllerManagerDown','KubeSchedulerDown','KubeletDown']
print('stock-disabled still absent:', all(n not in names for n in dis))   # expect True
print('tuned present:', {'CPUThrottlingHigh','etcdDatabaseHighFragmentationRatio','NodeMemoryMajorPagesFaults','NodeUnexpectedReboot'} <= names)"  # expect True
# firing alerts baseline (minus synthetic)
curl -s localhost:9090/api/v1/alerts | python3 -c "import sys,json;print(sorted({a['labels']['alertname'] for a in json.load(sys.stdin)['data']['alerts'] if a['labels']['alertname'] not in ('Watchdog','InfoInhibitor')}))"
# scrape-target up-count baseline
curl -s localhost:9090/api/v1/targets | python3 -c "import sys,json;t=json.load(sys.stdin)['data']['activeTargets'];print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))"
kill $PF

# --- current operator + CRD versions (to confirm the bump landed) ---
kubectl -n monitoring get deploy kube-prometheus-stack-operator -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl get crd prometheuses.monitoring.coreos.com -o jsonpath='{.metadata.annotations.operator\.prometheus\.io/version}{"\n"}'

# --- PVCs healthy + bound (data must survive; DO NOT delete these) ---
kubectl get pvc -n monitoring | grep -E 'prometheus|alertmanager'
kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,ROBUST:.status.robustness,LASTBK:.status.lastBackupAt --no-headers | grep -iE 'promet|alertman' || true

# --- confirm Telegram routing is live before we touch it (recent delivery / config load) ---
kubectl -n monitoring logs statefulset/alertmanager-kube-prometheus-stack-alertmanager -c alertmanager --tail=20 | grep -i 'telegram\|config' || true
```

Go criteria: all HR/Ks Ready; monitoring pods Running; 88.0.1 present in the
index; baseline captured (rule count, disabled-absent=True, tuned-present=True,
target up-count); PVCs Bound + Longhorn `robustness=healthy`.

## 3) Steps

> GitOps for the chart bump. The one non-GitOps action is the **server-side CRD
> pre-apply** (Step 3) — this is the chart's own documented `UPGRADE.md`
> procedure for a CRD-changing major and is the mitigation for the annotation
> size-limit failure. Run via `cberg-agent`. Attended window only.

**Step 1 — silence expected monitoring-ns rollout noise + drop an update marker**
(SOP `application-update.md` §Step 1). Keep the silence **scoped to
`namespace=monitoring`** so real alerts from every other namespace still fire the
moment Alertmanager is back:
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S.000Z'))")
curl -s -X POST localhost:9093/api/v2/silences -H 'Content-Type: application/json' -d '{
  "matchers":[{"name":"namespace","value":"monitoring","isRegex":false,"isEqual":true},
              {"name":"alertname","value":"Kube(Pod|Deployment|StatefulSet|DaemonSet).*|TargetDown|Prometheus.*|Watchdog","isRegex":true,"isEqual":true}],
  "startsAt":"'$NOW'","endsAt":"'$END'","createdBy":"maintenance-window",
  "comment":"kube-prometheus-stack 87.17.0->88.0.1 chart major — suppressing rollout noise. auto-expires 2h"}'
runbooks/update-marker.sh add kube-prometheus-stack monitoring 2 "chart 87.17.0->88.0.1 major"
```

**Step 2 — disable Flux rollback for the attempt** (SOP §Step 2) so a slow
operator/Prometheus/Alertmanager rollout can't be remediated mid-flight. Edit
`kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml`:
```yaml
  upgrade:
    cleanupOnFail: true
    crds: CreateReplace
    remediation:
      retries: 0                 # was 3 — restore after success
      remediateLastFailure: false
```
Also bump `timeout: 15m` → `timeout: 25m` for the run (CRD + StatefulSet rollout
headroom). Commit this together with Step 4, or as its own commit first.

**Step 3 — server-side pre-apply the v0.93.0 CRDs (via cberg-agent).** This makes
the subsequent Helm CRD apply a consistent no-op and avoids the
`metadata.annotations: Too long` client-side failure:
```bash
for c in alertmanagerconfigs alertmanagers podmonitors probes prometheusagents \
         prometheuses prometheusrules scrapeconfigs servicemonitors thanosrulers; do
  kubectl apply --server-side --force-conflicts \
    -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/v0.93.0/example/prometheus-operator-crd/monitoring.coreos.com_${c}.yaml
done
# confirm they took the new version annotation
kubectl get crd prometheuses.monitoring.coreos.com -o jsonpath='{.metadata.annotations.operator\.prometheus\.io/version}{"\n"}'  # expect 0.93.0
```
Existing CRs (all our PrometheusRules, ServiceMonitors, the telegram
AlertmanagerConfig) are untouched — the schema change is additive.

**Step 4 — bump the chart version.** Edit `helmrelease.yaml`:
```yaml
  chart:
    spec:
      chart: kube-prometheus-stack
      version: 88.0.1        # was 87.17.0
```
```bash
git add kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml
git commit -m "feat(kube-prometheus-stack): update chart ( 87.17.0 → 88.0.1 )"
git push        # work on main (repo convention: no feature branches)
```

**Step 5 — watch the rollout** (Flux reconciles on webhook; a manual nudge is OK
here since this is an attended major):
```bash
flux -n monitoring reconcile helmrelease kube-prometheus-stack --with-source
kubectl -n monitoring get pods -w   # operator → prometheus → alertmanager → node-exporter → KSM
```
Expected order: operator Deployment rolls first, then it reconciles the
Prometheus + Alertmanager StatefulSets (rolling), node-exporter DaemonSet and
kube-state-metrics roll independently.

**Step 6 — on success, restore guards + clear noise.** Revert Step 2
(`retries: 3`, `remediateLastFailure` removed, `timeout: 15m`), commit, push.
Then:
```bash
curl -s localhost:9093/api/v2/silences | python3 -c "import sys,json;[print(s['id']) for s in json.load(sys.stdin) if s['status']['state']=='active' and 'kube-prometheus-stack' in s.get('comment','')]" | xargs -I{} curl -s -X DELETE localhost:9093/api/v2/silences/{}
runbooks/update-marker.sh clear kube-prometheus-stack
```

## 4) Verification

```bash
# 1) HelmRelease reconciled to 88.0.1 and Ready
kubectl -n monitoring get helmrelease kube-prometheus-stack -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'  # True 88.0.1

# 2) Operator on v0.93.0, running, 0 restarts after settle
kubectl -n monitoring get deploy kube-prometheus-stack-operator -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # ...:v0.93.0
kubectl -n monitoring get pods -l app.kubernetes.io/name=kube-prometheus-stack-prometheus-operator

# 3) CRDs served at 0.93.0
for c in prometheuses alertmanagers alertmanagerconfigs prometheusrules servicemonitors; do
  echo "$c: $(kubectl get crd $c.monitoring.coreos.com -o jsonpath='{.metadata.annotations.operator\.prometheus\.io/version}')"
done   # all 0.93.0

# 4) Prometheus + Alertmanager Ready, PVCs still Bound (NO data loss)
kubectl -n monitoring get pods -l app.kubernetes.io/name=prometheus
kubectl -n monitoring get pods -l app.kubernetes.io/name=alertmanager
kubectl get pvc -n monitoring | grep -E 'prometheus|alertmanager'   # Bound, same volumes as pre-check

# 5) RULE SURVIVAL — the crux. Re-run the pre-check queries and diff:
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 & PF=$!; sleep 3
curl -s localhost:9090/api/v1/rules | python3 -c "import sys,json;d=json.load(sys.stdin)['data']['groups'];print('groups',len(d),'rules',sum(len(g['rules']) for g in d))"  # ~= baseline
curl -s localhost:9090/api/v1/rules | python3 -c "
import sys,json
names={r['name'] for g in json.load(sys.stdin)['data']['groups'] for r in g['rules']}
dis=['KubeAPIDown','KubeControllerManagerDown','KubeSchedulerDown','KubeletDown']
print('stock-disabled STILL absent:', all(n not in names for n in dis))                       # True
print('tuned replacements present:', {'CPUThrottlingHigh','etcdDatabaseHighFragmentationRatio','NodeMemoryMajorPagesFaults','NodeUnexpectedReboot','NodeMemoryECCUncorrectableErrors'} <= names)"  # True
# confirm our tuned etcd rule (512MiB/1h) is the one loaded, not stock (100MiB/10m):
curl -s localhost:9090/api/v1/rules | python3 -c "import sys,json;print([r for g in json.load(sys.stdin)['data']['groups'] if g['name']=='etcd-tuned' for r in g['rules']][0]['duration'])"  # 3600
# targets back up (~= baseline count)
curl -s localhost:9090/api/v1/targets | python3 -c "import sys,json;t=json.load(sys.stdin)['data']['activeTargets'];print('up',sum(1 for x in t if x['health']=='up'),'/',len(t))"
kill $PF

# 6) Alertmanager config loaded + telegram route intact (no config error after CRD change)
kubectl -n monitoring logs statefulset/alertmanager-kube-prometheus-stack-alertmanager -c alertmanager --tail=30 | grep -iE 'completed loading|error' 
kubectl -n monitoring exec statefulset/alertmanager-kube-prometheus-stack-alertmanager -c alertmanager -- amtool config routes --alertmanager.url=http://localhost:9093 2>/dev/null || true
# ROUTING SMOKE TEST — fire a synthetic alert, confirm Telegram delivery, then expire it:
kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 & PF=$!; sleep 3
curl -s -X POST localhost:9093/api/v2/alerts -H 'Content-Type: application/json' -d '[{"labels":{"alertname":"UpgradeSmokeTest","severity":"warning","namespace":"monitoring"},"annotations":{"summary":"kube-prometheus-stack 88 upgrade routing test — ignore"}}]'
# → confirm it lands in the Telegram home-operation channel, then it self-resolves.
kill $PF

# 7) Longhorn AlertmanagerConfig (storage ns) + telegram AlertmanagerConfig still Accepted
kubectl get alertmanagerconfig -A
kubectl -n monitoring get alertmanagerconfig telegram -o jsonpath='{.metadata.name}{"\n"}'

# 8) decoupled stack unaffected
flux -n monitoring get helmrelease grafana | awk 'NR==1||/grafana/'   # still Ready, untouched
kubectl -n monitoring get pods -l app.kubernetes.io/name=grafana      # not restarted by this bump
kubectl -n monitoring get deploy sweep-dashboard                       # untouched
```

Success = HR True@88.0.1; operator v0.93.0 healthy; CRDs 0.93.0; Prometheus +
Alertmanager Ready on the **same PVCs**; rule count ≈ baseline with
stock-disabled still absent + tuned replacements present; targets up ≈ baseline;
Telegram smoke-test delivered; Grafana + sweep-dashboard untouched.

## 5) Rollback

Trigger if: HR stuck `pending-upgrade`, operator/Prometheus/Alertmanager
crash-loops, rules fail to load, or the Telegram smoke-test doesn't arrive.

```bash
# 1) Revert the chart bump (and the Step-2 guard edit if committed together)
git revert --no-edit <bump-commit-sha>
git push origin main
flux -n monitoring reconcile helmrelease kube-prometheus-stack --with-source --force

# 2) If Helm is wedged pending-upgrade, clear it first (maxHistory:2 keeps the prior rev):
helm history kube-prometheus-stack -n monitoring
helm rollback kube-prometheus-stack <last-deployed-rev> -n monitoring --wait=false
flux -n monitoring reconcile helmrelease kube-prometheus-stack --force
```

**CRDs are intentionally NOT rolled back.** The v0.93.0 CRDs are additive
supersets; the reverted 87.17.0 operator runs correctly against them (Helm does
not downgrade CRDs, and downgrading them is unsafe). Leave them at 0.93.0.

Confirm restored:
```bash
kubectl -n monitoring get helmrelease kube-prometheus-stack -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'  # True 87.17.0
kubectl -n monitoring get pods -l app.kubernetes.io/name=prometheus     # Ready
# rules load + telegram routes (re-run Verification #5 + #6 smoke test)
```
Then drop the silence + clear the marker (Step 6) so alerting is live again.

## 6) Interference notes

- **This is cluster-wide shared infra (`shared: [monitoring, prometheus-operator-crds]`).**
  Every app's metrics + alert evaluation flow through this stack. Its rollout
  (operator → Prometheus + Alertmanager restart, node-exporter + KSM restart)
  causes **~2–5 min of gappy metrics and no alert evaluation**.
- **Run this plan FIRST in its window and fully verify (Section 4) that
  monitoring is healthy BEFORE executing or verifying any other plan** — any
  co-scheduled plan whose verification relies on live alerts/metrics (target-up
  counts, "no CrashLoop alert fired") will read false-clean during the blind
  window. Prefer running it **solo**; if co-scheduled, serialize it ahead of
  everything and re-check the target up-count after.
- **CRDs are cluster-scoped.** The server-side pre-apply (Step 3) momentarily
  updates the `monitoring.coreos.com` CRD definitions used by *every* namespace,
  but existing CRs are untouched (additive schema) — no re-render of app
  ServiceMonitors/PrometheusRules is needed.
- **Silence is scoped to `namespace=monitoring` only** — keep it that way so real
  alerts elsewhere still fire once Alertmanager returns. Short TTL (2h) so it
  self-clears if the window overruns.
- **Do NOT delete the Prometheus/Alertmanager Longhorn PVCs** at any point — not
  required for a chart upgrade; deleting them discards metric history + active
  silences. (Not a CIFS/SMB class, so not a storage-safety catastrophe, but still
  gratuitous data loss.)
- **Grafana + sweep-dashboard are separate deployments** and are not restarted by
  this bump — don't gate this plan on them, and don't expect them to move.
- `needs_reboot: false` — no node reboot; does not need an `allow_reboot` window,
  but the `risk: high` rating still routes it to the operator-present Sun slot,
  which is appropriate for a verify-heavy observability major.
