---
plan_id: kube-prometheus-stack-89.2.2
component: kube-prometheus-stack
pr: null                          # no open Renovate PR found (gh pr list, 2026-09-05);
                                  # held by the major-version gate before a PR existed
kind: chart
current: "88.6.3"
target: "89.2.2"
update_type: major
risk: low                         # see §1 — evidenced, not assumed: appVersion
                                  # unchanged, CRDs byte-identical, rendered
                                  # manifest diff against OUR values is ONLY
                                  # version/chart labels. Held correctly by the
                                  # "major = PLAN lane" policy; investigation
                                  # found this specific major to be an
                                  # operational no-op. Still requires operator
                                  # go/no-go per CLAUDE.md ("non-safe updates
                                  # are operator go/no-go by default").
est_duration_min: 30
needs_reboot: false
touches:
  namespaces: [monitoring]
  resources:
    - helmrelease/kube-prometheus-stack
    - configmap/kube-prometheus-stack-values
    - deployment/kube-prometheus-stack-operator            # relabeled -> restarts (1 replica, brief)
    - statefulset/prometheus-kube-prometheus-stack-prometheus   # operator-generated, NOT expected to restart (see §1)
    - statefulset/alertmanager-kube-prometheus-stack-alertmanager # operator-generated, NOT expected to restart (see §1)
    - "crds: prometheuses/alertmanagers/servicemonitors/podmonitors/probes/prometheusrules/scrapeconfigs/thanosrulers/alertmanagerconfigs/prometheusagents.monitoring.coreos.com"
    - "50 PrometheusRule objects templated from kubernetes/apps/monitoring/kube-prometheus-stack/app/*-alerts.yaml (relabeled only)"
    - "servicemonitor/longhorn (chart-rendered; relabeled only)"
  shared: [monitoring, alerting]  # this chart OWNS the alerting path itself:
                                  # Prometheus rule evaluation + Alertmanager
                                  # delivery for every other app's alerts runs
                                  # through it. Not "a consumer of shared
                                  # infra" like grafana — this IS the shared
                                  # infra.
depends_on: []
conflicts_with:
  - grafana-13.0.0                # same window (sat-attended:2026-09-19) + same
                                  # namespace (monitoring). Not a true resource
                                  # collision, but an ORDERING requirement:
                                  # grafana-13.0.0's verification gate (§4.4 of
                                  # that plan) queries Prometheus via
                                  # /api/ds/query and Alertmanager via the proxy
                                  # health check. Run THIS plan first and get a
                                  # clean §4 here before grafana's window slot,
                                  # so a grafana datasource failure can't be
                                  # confused with an alerting-stack regression
                                  # from this bump. Do not interleave.
  - unpoller-v5.1.0                # same window + namespace. unpoller's own
                                  # CONTENTS ASSERTION (§4.3 of that plan) reads
                                  # up{job="unpoller"} and a count() query FROM
                                  # Prometheus. Same reasoning: this plan first,
                                  # verified green, before unpoller's slot.
security_ref: null                # no CVE/security driver; appVersion (Prometheus
                                  # v0.93.1, Alertmanager, prometheus-operator)
                                  # is IDENTICAL before and after — nothing to
                                  # disclose
capability_change: false          # packaging/label-only bump for our config;
                                  # no new feature is enabled (grafana subchart
                                  # stays grafana.enabled:false; cert-manager
                                  # admission-webhook feature stays disabled)
rollback_class: git-revert        # one value in one file; appVersion never moves
finding_refs: []
status: draft
window: null                      # window agent assigns
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
generated: "2026-09-05"
---

# kube-prometheus-stack: chart 88.6.3 → 89.2.2 (major — evidenced as a label-only no-op for our config)

## 1) Summary & why held

Held by the auto-updater's major-version gate (`docs/sops/auto-update.md`) —
correctly, since chart majors are never provably safe from the version number
alone. Investigation below shows this specific major is, for our deployment,
an operational no-op: nothing in Prometheus, Alertmanager, prometheus-operator,
or the CRD set changes behaviourally. The hold was the right call to make
generically; the finding is that this instance clears with high confidence.

**appVersion does NOT move.** Chart index
(`https://prometheus-community.github.io/helm-charts/index.yaml`, fetched
2026-09-05):

| chart | appVersion | created |
|---|---|---|
| 88.6.3 (current) | v0.93.1 | 2026-09-02 |
| 89.0.0 | v0.93.1 | 2026-09-03 |
| 89.2.2 (target) | v0.93.1 | 2026-09-04 |

Prometheus, Alertmanager, and `quay.io/prometheus-operator/prometheus-operator`
all stay pinned at the same upstream release. **This is a chart-major that does
NOT move appVersion — the different, lower risk class from a bump that does
both** (contrast `grafana-13.0.0`, also a chart major with unchanged
appVersion, for the same reasoning pattern).

**What actually changed, per upstream release notes** (`gh api
repos/prometheus-community/helm-charts/releases/tags/kube-prometheus-stack-89.{0.0,1.0,2.0,2.1,2.2}`):

- 89.0.0: bump the bundled (grafana subchart) dependency to Grafana chart v13
- 89.1.0: non-major dependency updates
- 89.2.0: bundled grafana subchart → v13.2.0
- 89.2.1: prometheus-operator's **cert-manager admission-webhook** template
  (`templates/prometheus-operator/certmanager.yaml`) gets a default `commonName`
  on its `Certificate` (PR #7234 — fixes strict-CN issuers like Vault)
- 89.2.2: bundled grafana subchart → v13.2.1

Every one of these lands on features we do not use:

1. **The bundled grafana subchart is disabled**: `helmvalues.yaml` sets
   `grafana.enabled: false` (we run Grafana as its own separate HelmRelease,
   `kubernetes/apps/monitoring/grafana/`). All four grafana-subchart bumps
   (89.0.0/89.2.0/89.2.2 and its transitive dashboard-JSON/template changes)
   render nothing.
2. **The cert-manager admission-webhook path is off by default and we don't
   turn it on**: `grep -n -i certmanager helmvalues.yaml` returns nothing; the
   chart default is `prometheusOperator.admissionWebhooks.certManager.enabled:
   false`. PR #7234's `commonName` default only applies when that path is
   enabled.

**Proof, not inference — three independent checks, all done read-only against
the pulled chart tarballs, none against the live cluster:**

- **CRDs are byte-identical.** `helm pull` both 88.6.3 and 89.2.2, `diff -q`
  every file in `charts/crds/crds/*.yaml` (Prometheus, Alertmanager,
  ServiceMonitor, PodMonitor, Probe, PrometheusRule, ScrapeConfig,
  ThanosRuler, AlertmanagerConfig, PrometheusAgent) — **zero diffs**. This
  chart owns the CRD set and Helm does not upgrade CRDs on `helm upgrade`
  (the classic silent-failure mode for this chart) — moot here because there
  is nothing to apply. Flux's HelmRelease already carries
  `install.crds: CreateReplace` / `upgrade.crds: CreateReplace`
  (`kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml`),
  which is Flux's own CRD-apply mechanism (distinct from `helm upgrade`'s
  no-op) — it will re-apply the identical CRD manifests, a harmless no-op.
- **`values.yaml` diff is two new commented-out options**: a grafana
  `folderAnnotation` (grafana disabled, irrelevant) and a commented
  `admissionWebhooks.certManager.privateKey` example (feature disabled,
  irrelevant). No key restructuring, no `values.schema.json` in this chart to
  hard-fail against (unlike the app-template 5.x class of major — SOP §7b).
- **Full `helm template` diff against OUR actual values**, same release name
  both sides (to isolate real diffs from the release-name artifact of a naive
  compare):
  ```
  helm template kube-prometheus-stack kps-old/kube-prometheus-stack -n monitoring -f our-values.yaml > render-old.yaml
  helm template kube-prometheus-stack kps-new/kube-prometheus-stack -n monitoring -f our-values.yaml > render-new.yaml
  diff render-old.yaml render-new.yaml
  ```
  6271 lines rendered each side. **Every line of the diff is
  `app.kubernetes.io/version: "88.6.3"` → `"89.2.2"` or
  `chart: kube-prometheus-stack-88.6.3` → `-89.2.2` label churn** — on the
  operator Deployment, kube-state-metrics, node-exporter, the Prometheus/
  Alertmanager/ThanosRuler CR objects, and the chart-rendered `longhorn`
  ServiceMonitor. **Zero diff in any `spec:` block, container image, arg,
  resource limit, probe, storage spec, or selector.**

**The one real side effect: the prometheus-operator Deployment's own pod
template labels change** (`chart`/`app.kubernetes.io/version`), which forces
a rollout of that Deployment — single replica, brief restart (seconds). The
**Prometheus and Alertmanager StatefulSets are not Helm templates** — the
operator generates them from the `Prometheus`/`Alertmanager` CR specs, and
since the operator binary itself is version-pinned identical
(`quay.io/prometheus-operator/prometheus-operator:v0.93.1`, unchanged), it
will regenerate the identical StatefulSet spec on its next reconcile and the
StatefulSet controller sees no diff — no expected restart of the Prometheus
or Alertmanager pods themselves. §4 verifies this rather than assuming it.

**The alerting-path stakes, and why verification below is not just "pods
Ready":** this chart is the metric-and-alert backbone every other component's
health checks (and this very maintenance-window pipeline) depend on. A
regression here is invisible to `kubectl get pods` — a Prometheus that starts
but drops rule evaluation, or an Alertmanager that starts but stops routing to
Telegram, looks identical to a healthy one at the pod-Ready level. §4 proves
rule-load counts, live rule evaluation (Watchdog), Alertmanager receipt, and
one real notification round-trip through the Telegram receiver.

**The `release: kube-prometheus-stack` selector trap, checked and clean:**
`Prometheus.spec.ruleSelector` / `serviceMonitorSelector` in our values
(`helmvalues.yaml:161-167`) pin `matchLabels: {release: kube-prometheus-stack}`
with `ruleSelectorNilUsesHelmValues: false` /
`serviceMonitorSelectorNilUsesHelmValues: false` — i.e. selection is on OUR
fixed label value, not derived from the Helm release name or chart version, so
this bump cannot change what gets selected. Confirmed **all 50** of our
hand-authored `*-alerts.yaml` PrometheusRule files already carry
`release: kube-prometheus-stack` (`grep -l` count == file count) — none would
silently stop loading even if the selector generation logic had moved (it
hasn't — see the render diff above).

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.1 Re-verify "current" hasn't moved under this plan (README warning: Step 0
# safe-update lane may have already carried 88.6.3 -> 88.6.4/88.6.5 before this
# plan's window). If live != 88.6.3, update this plan's `current:` first.
mise exec -- kubectl -n monitoring get hr kube-prometheus-stack -o jsonpath='{.spec.chart.spec.version}{"\n"}{.status.conditions[?(@.type=="Ready")].status}{"\n"}'

# 2.2 No in-flight reconcile anywhere (this bump touches every namespace's
# PrometheusRule selection surface)
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'

# 2.3 BASELINE — rule count + release-label coverage (compare after)
grep -l "release: kube-prometheus-stack" kubernetes/apps/monitoring/kube-prometheus-stack/app/*alerts*.yaml | wc -l   # expect 50
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 & sleep 3
curl -s http://localhost:9090/api/v1/rules | python3 -c "
import sys,json
d=json.load(sys.stdin)['data']['groups']
print('rule groups:', len(d), '| total rules:', sum(len(g['rules']) for g in d))"

# 2.4 BASELINE — alerting pipeline already alive BEFORE the change (Watchdog
# fires continuously by design; this is the standard kube-prometheus-stack
# end-to-end canary)
curl -s 'http://localhost:9090/api/v1/query?query=ALERTS%7Balertname%3D%22Watchdog%22%7D' | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(r or 'NO WATCHDOG SERIES — ABORT, pipeline already broken pre-change')"
kill %1
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 & sleep 3
curl -s 'http://localhost:9093/api/v2/alerts?filter=alertname%3D%22Watchdog%22' | python3 -c "import sys,json; a=json.load(sys.stdin); print(len(a), 'Watchdog alert(s) in AM' if a else 'NO WATCHDOG IN ALERTMANAGER — ABORT')"
kill %1

# 2.5 CRD identity re-check (repeat the plan's own evidence right before executing)
helm repo update prometheus-community
cd /tmp && rm -rf kps-old kps-new
helm pull prometheus-community/kube-prometheus-stack --version 88.6.3 --untar --untardir kps-old
helm pull prometheus-community/kube-prometheus-stack --version 89.2.2 --untar --untardir kps-new
diff -rq kps-old/kube-prometheus-stack/charts/crds/crds kps-new/kube-prometheus-stack/charts/crds/crds
# expect: no output (identical). Any output here invalidates this plan's risk
# rating — stop and re-assess before proceeding.
```

Abort if: HR not Ready, any Kustomization/HelmRelease cluster-wide not Ready,
rule-group/count query fails, Watchdog is absent from either Prometheus or
Alertmanager (pipeline already broken — not this plan's problem to fix blind),
or the CRD re-check now shows a diff (upstream shipped a new patch since
2026-09-05 — re-open the release-notes review in §1 for the delta before
proceeding).

## 3) Steps (GitOps)

1. Edit `kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml`:
   `spec.chart.spec.version: 88.6.3` → `89.2.2`.
2. Validate locally:
   ```bash
   task kubeconform
   ```
3. Commit **only** this file (shared worktree rule — `--only`, not `add -A`):
   ```bash
   git commit --only kubernetes/apps/monitoring/kube-prometheus-stack/app/helmrelease.yaml \
     -m "feat(kube-prometheus-stack)!: chart 88.6.3 -> 89.2.2 (label-only major, appVersion v0.93.1 unchanged)" \
     -m "CRDs byte-identical, render diff vs our values is version/chart labels only. Plan: kube-prometheus-stack-89.2.2."
   git show --stat HEAD          # exactly one file
   git push
   ```
4. Let the Flux webhook reconcile (no manual `flux reconcile` needed per SOP
   default — only escalate to a forced reconcile if it stalls beyond ~5 min):
   ```bash
   mise exec -- flux -n monitoring get hr kube-prometheus-stack --watch
   ```
5. Expect exactly one visible blip: the `kube-prometheus-stack-operator`
   Deployment pod restarts once (relabeled pod template, §1). Do **not** be
   alarmed if the Prometheus/Alertmanager StatefulSet pods do **not** restart
   — that is the predicted (and verified in §4) outcome, not a stuck rollout.

## 4) Verification (run ALL)

```bash
# 4.1 HelmRelease landed on the intended chart version, Ready, appVersion unchanged
mise exec -- kubectl -n monitoring get hr kube-prometheus-stack -o jsonpath='{.status.history[0].chartVersion}{" ready="}{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
mise exec -- kubectl -n monitoring get deploy kube-prometheus-stack-operator -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
# expect: quay.io/prometheus-operator/prometheus-operator:v0.93.1 (UNCHANGED)

# 4.2 Operator restarted (expected); Prometheus/Alertmanager pods did NOT
# unnecessarily restart (age should be older than the operator pod, or at
# minimum show no CrashLoop/new-image churn)
mise exec -- kubectl -n monitoring get pods -l app.kubernetes.io/name=kube-prometheus-stack-prometheus-operator
mise exec -- kubectl -n monitoring get pods -l app.kubernetes.io/name=prometheus,operator.prometheus.io/name=kube-prometheus-stack-prometheus
mise exec -- kubectl -n monitoring get pods -l app.kubernetes.io/name=alertmanager

# 4.3 CRDs re-applied, unchanged content (Flux crds:CreateReplace, not a manual step)
for crd in prometheuses alertmanagers servicemonitors podmonitors probes prometheusrules scrapeconfigs thanosrulers alertmanagerconfigs prometheusagents; do
  mise exec -- kubectl get crd ${crd}.monitoring.coreos.com -o jsonpath="{.spec.versions[-1].name}{'\n'}"
done
# compare each against the pre-change list (should be identical version names)

# 4.4 CONTENTS ASSERTION (rule load): same 50/50 release-label coverage AND
# Prometheus reports the same (or larger, if concurrent unrelated commits
# landed) rule/group count as the §2.3 baseline — NOT fewer.
grep -l "release: kube-prometheus-stack" kubernetes/apps/monitoring/kube-prometheus-stack/app/*alerts*.yaml | wc -l
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 & sleep 3
curl -s http://localhost:9090/api/v1/rules | python3 -c "
import sys,json
d=json.load(sys.stdin)['data']['groups']
print('rule groups:', len(d), '| total rules:', sum(len(g['rules']) for g in d))"
# MUST be >= the §2.3 baseline. A drop means the selector or CRD generation
# broke — the exact silent-failure mode this plan exists to catch.

# 4.5 CONTENTS ASSERTION (rule EVALUATION, not just load): Watchdog still
# firing continuously, timestamp newer than the upgrade
curl -s 'http://localhost:9090/api/v1/query?query=ALERTS%7Balertname%3D%22Watchdog%22%7D' | python3 -c "
import sys,json,time
r=json.load(sys.stdin)['data']['result']
print(r or 'FAIL: no Watchdog series — rule evaluation stopped')
if r: print('age(s):', time.time()-float(r[0]['value'][0]))"
kill %1

# 4.6 CONTENTS ASSERTION (delivery to Alertmanager): Watchdog present in AM
mise exec -- kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 & sleep 3
curl -s 'http://localhost:9093/api/v2/alerts?filter=alertname%3D%22Watchdog%22' | python3 -c "import sys,json; a=json.load(sys.stdin); print(len(a),'Watchdog alert(s)' if a else 'FAIL: Watchdog missing from Alertmanager')"

# 4.7 CONTENTS ASSERTION (full pipeline incl. Telegram receiver): fire ONE
# synthetic, clearly-labeled, self-resolving test alert through the REAL
# critical route and confirm the notifier counter increments. Attended window
# — operator visually confirms the message lands in the home-operation
# Telegram channel; this is the strongest available proof the receiver config
# (chart-templated Secret/AlertmanagerConfig wiring) survived the bump.
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).isoformat())")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat())")
BEFORE=$(curl -s http://localhost:9093/metrics | grep -c 'alertmanager_notifications_total{integration="telegram"')
curl -s -X POST http://localhost:9093/api/v2/alerts -H 'Content-Type: application/json' -d '[{
  "labels":{"alertname":"MaintenanceWindowTestAlert","severity":"critical"},
  "annotations":{"summary":"kube-prometheus-stack 89.2.2 upgrade verification — expect this in Telegram, then auto-resolve"},
  "startsAt":"'$NOW'","endsAt":"'$END'"}]'
sleep 15
curl -s http://localhost:9093/metrics | grep 'alertmanager_notifications_total{integration="telegram"'
# notifications_total for integration=telegram must have INCREMENTED vs BEFORE,
# and alertmanager_notifications_failed_total{integration="telegram"} must NOT
# have incremented. Operator confirms the Telegram message arrived.
kill %1
```

**CONTENTS ASSERTION (stated per the plans README convention):** the property
that could silently break is *rule evaluation and delivery*, not process
liveness. Measured by §4.4 (rule count ≥ baseline), §4.5 (Watchdog series
fresh), §4.6 (Watchdog reaches Alertmanager), and §4.7 (a real alert reaches
the Telegram receiver) — compared against the §2.3/§2.4 pre-change baselines.
All four would still read "pods Ready" if the alerting path were silently
dead; none of them would read green if it were.

## 5) Rollback

Single-file, single-value change; appVersion never moved, so revert is
complete and safe:

```bash
git revert <sha-of-step-3-commit> && git push
mise exec -- flux -n monitoring reconcile ks kube-prometheus-stack --with-source
mise exec -- flux -n monitoring reconcile hr kube-prometheus-stack
# Confirm: HR chart version back to 88.6.3, operator image still v0.93.1
# (unchanged either way), then RE-RUN §4.4/§4.5/§4.6 — a rollback is a change
# and needs the same gate re-run.
```

No PVC, TSDB, or Alertmanager silence-state impact expected in either
direction (Prometheus/Alertmanager StatefulSets are not predicted to restart
at all — §1, §4.2).

## 6) Interference notes

- **This IS the shared alerting/monitoring infra**, not a consumer of it — the
  `shared: [monitoring, alerting]` tag is deliberate. Every other app's
  PrometheusRule, every ServiceMonitor, and the Telegram receiver ride through
  this one HelmRelease.
- **Run BEFORE `grafana-13.0.0` and `unpoller-v5.1.0`** in the shared
  `sat-attended:2026-09-19` window (see `conflicts_with`). Both of those
  plans' own verification gates query Prometheus/Alertmanager directly
  (grafana's `/api/ds/query` + Alertmanager proxy health check; unpoller's
  `up{job="unpoller"}`/series-count check). Get a fully green §4 here first so
  a failure in either of those plans cannot be confused with a regression from
  this bump — same ordering logic those two plans already apply to each
  other.
- **Expected, do not page:** one restart of the `kube-prometheus-stack-operator`
  Deployment pod (single replica, seconds). During that narrow window, do not
  create or edit any `PrometheusRule`/`ServiceMonitor`/`Probe`/`ScrapeConfig`
  object elsewhere in the cluster — the operator's admission webhook briefly
  has no backend pod to validate against.
- **Not expected — investigate if seen:** any restart of the Prometheus or
  Alertmanager StatefulSet pods themselves. Per §1/§4.2 the operator binary
  version is unchanged, so it should regenerate byte-identical StatefulSet
  specs; a restart there would mean this plan's core evidence (render diff =
  labels only) missed something and needs re-review before trusting the rest
  of the window's verification.
- **Re-verify `current:` before executing** (plans README warning): the
  nightly/attended safe-update lane (Step 0 of every window,
  `docs/sops/auto-update.md`) may have already carried this chart through one
  or more 88.6.x patches before this plan's window arrives. If so, treat
  §2.5's CRD re-diff as authoritative over this file's `current:` field.
- No reboot, no other namespace's workloads restart, no storage change.
