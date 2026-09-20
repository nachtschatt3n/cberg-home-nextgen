---
plan_id: prometheus-crd-ownership
component: otel-operator              # the HelmRelease whose values change. The CRDs
                                      # themselves are cluster-scoped and end up owned by
                                      # kube-prometheus-stack — that HR is NOT edited here.
pr: null                              # no Renovate PR can exist: this is a one-key values
                                      # change on an existing HelmRelease, not a version bump.
kind: config
current: "monitoring.coreos.com CRDs are split-owned — 6 written by kube-prometheus-stack (operator-version 0.93.1), 4 (servicemonitors, podmonitors, probes, scrapeconfigs) re-stamped to operator-version 0.92.0 by otel-operator (opentelemetry-kube-stack 0.20.9, crds.installPrometheus at chart default true, Flux crds: CreateReplace) on EVERY chart bump; last write helm-controller 2026-09-14T05:45:08Z = helm revision 23, generation 30"
target: "otel-operator HelmRelease values crds.installPrometheus: false — helm-controller stops collecting the prometheus-crds subchart's crds/ on install and upgrade; the four CRDs are NOT deleted (they were never release resources) and kube-prometheus-stack becomes the single writer of all ten from its next upgrade (plan kube-prometheus-stack-91.4.0)"
update_type: refactor
risk: medium                          # The CHANGE is one values key and the rendered
                                      # release manifest is byte-identical apart from the
                                      # webhook cert that regenerates on every upgrade
                                      # anyway (§1.2 a). Rated medium, not low, because the
                                      # failure mode IF the proof in §1.2 were wrong is
                                      # the cascade-delete of every ServiceMonitor (49),
                                      # PodMonitor (3), Probe (4) and ScrapeConfig (3) in
                                      # the cluster — total scrape loss — and because this
                                      # is the first time this code path runs here. The
                                      # proof is three-sourced (chart layout, helm-controller
                                      # source, live object metadata) and re-run at §2.5.
est_duration_min: 30                  # 10 pre-checks (incl. local chart pull + render A/B)
                                      # + 3 edit/commit/push + 5 reconcile + 7 verification
                                      # + 5 buffer. Nothing restarts, nothing is blind.
needs_reboot: false
touches:
  namespaces:
    - monitoring
  resources:
    - helmrelease/otel-operator                            # values change -> helm revision +1, SAME chart 0.20.9
    - secret/otel-operator-opentelemetry-operator-controller-manager-service-cert   # regenerated on EVERY helm
                                                           # upgrade (autoGenerateCert.recreate: true) — not new
    - mutatingwebhookconfiguration/otel-operator-opentelemetry-operator-mutation      # caBundle follows the cert
    - validatingwebhookconfiguration/otel-operator-opentelemetry-operator-validation  # caBundle follows the cert
    - "crd/{servicemonitors,podmonitors,probes,scrapeconfigs}.monitoring.coreos.com — NOT modified, NOT deleted: this plan removes otel-operator as a WRITER. generation, resourceVersion and contents must be UNCHANGED after the upgrade (§4.2); the stale helm.toolkit.fluxcd.io/name=otel-operator label stays until kube-prometheus-stack next writes them"
    - "crd/{instrumentations,opampbridges,opentelemetrycollectors,targetallocators}.opentelemetry.io — re-applied byte-identical by CreateReplace, exactly as on every otel-operator upgrade"
    - deployment/otel-operator-opentelemetry-operator      # NOT rolled — release manifest identical; the operator hot-reloads the cert
    - daemonset/otel-operator-daemon-collector             # NOT rolled — the OpenTelemetryCollector CR is unchanged
  shared:
    - monitoring                      # DECLARED for the object class, not for a restart:
                                      # the four CRDs are the cluster-wide scrape-config
                                      # surface (59 CRs across 8 namespaces). Prometheus,
                                      # Alertmanager, edot-collector and the daemon
                                      # collectors are NOT perturbed; no scrape gap.
depends_on: []
conflicts_with:
  - kube-prometheus-stack-91.4.1      # both touch the same ten cluster-scoped CRDs; two
                                      # CreateReplace writers in one window is the race
                                      # this plan exists to end. Ordering: THIS plan first,
                                      # kps-91.4.0 in a LATER window (§6).
                                      # 2026-09-17: otel-operator-0.21.0 ref REMOVED — that
                                      # plan executed (9a35168f) and was retired (37f7c7a6)
                                      # in the nightly window. It edited the SAME HelmRelease
                                      # spec, so two otel-operator upgrades in one window
                                      # would have confounded §4's "generation unchanged
                                      # across an upgrade" assertion. SEE F-7235625a: that
                                      # assertion is now known to be VACUOUS in the ordinary
                                      # case — generation, resourceVersion AND the
                                      # helm-controller write timestamp all stayed unchanged
                                      # through tonight's upgrade WHILE this HelmRelease was
                                      # still the configured writer. §4 needs a positive
                                      # proof, not an absence. Any future otel-operator plan
                                      # must re-add this exclusion.
security_ref: null
capability_change: false              # no user-visible behaviour changes: same chart,
                                      # same images, same collectors, same CRD contents;
                                      # only WHICH HelmRelease writes four CRDs changes.
rollback_class: git-revert            # revert re-enables the subchart -> the next otel
                                      # upgrade re-stamps 0.92.0. A rewrite, never a
                                      # delete, in both directions (§5).
autonomy_override: human-gated        # 2026-09-15: first execution of a CRD-ownership
                                      # change on the scrape surface. The mechanism is
                                      # proven (§1.2) but the worst case is not
                                      # revert-recoverable (§5.3), so a human watches the
                                      # ONE helm upgrade. Operator may lift this after a
                                      # clean run. Fits sat-attended; no reboot.
finding_refs:
  - F-a85e8943                        # "Prometheus CRD ownership contention: otel-operator …
                                      # re-writes 4 of the 10 monitoring.coreos.com CRDs"
status: awaiting-go   # DEFERRED 2026-09-19 sat-attended: HUMAN-GATED via autonomy_override, and this run was cron-fired/unattended. go/no-go ingested, scoped sat-attended:2026-09-26.
window: "sun-attended:2026-09-20"   # RE-SCOPED 2026-09-20 from sat-attended:2026-09-26 on an EXPLICIT operator GO given in the Claude Code session for TODAY's attended window (operator present). Capacity re-checked: 135/200 min, risk 5/6. Interference re-checked: namespaces monitoring vs office vs my-software-* are disjoint and no co-scheduled plan is in its conflicts_with (kube-prometheus-stack-91.4.1 stays window:null). Runs FIRST in the window because it declares shared:[monitoring].
premises:
  - id: otel-hr-ready
    why: "Do not stack a values change on an already-failing release; a failed upgrade with remediation strategy rollback would mask the §4 result."
    run: kubectl get helmrelease -n monitoring otel-operator -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: otel-chart-version-whose-layout-was-verified
    why: >-
      The whole safety argument rests on the chart LAYOUT: the four Prometheus
      CRDs live under charts/prometheus-crds/crds/ (a crds/ directory, no
      templates/) behind Chart.yaml condition `crds.install,crds.installPrometheus`.
      That was verified by pulling and inspecting EXACTLY 0.20.9 and 0.21.0
      (both: crds/-only, operator-version 0.92.0). Any other version — including
      a 0.20.x patch that nightly Step 0 may auto-land — must be re-pulled and
      re-checked with the §2.5 recipe before this premise is widened. Do NOT
      widen it without doing that.
    run: kubectl get helmrelease -n monitoring otel-operator -o jsonpath='{.spec.chart.spec.version}'
    expect_matches: "^0\\.(20\\.9|21\\.0)$"
  - id: installPrometheus-not-set-in-our-values
    why: "`current:` says the key is unset (chart default true applies). If someone already set it, this plan is either done or was done differently — re-derive §1 before touching anything."
    run: kubectl get helmrelease -n monitoring otel-operator -o jsonpath='crds=[{.spec.values.crds}]'
    expect_exact: "crds=[]"
  - id: four-crds-still-stamped-0.92.0
    why: >-
      The contention state this plan was written against. If these read 0.94.0
      (or 0.93.1), kube-prometheus-stack wrote them more recently than
      otel-operator did — the plan is STILL needed (the next otel bump would
      re-stamp them) but §2.3's baseline and §4.2's expected version must be
      re-taken from the live objects, and this expectation updated in the same
      commit. A mixed set means something else is writing them: stop.
    run: kubectl get crd servicemonitors.monitoring.coreos.com podmonitors.monitoring.coreos.com probes.monitoring.coreos.com scrapeconfigs.monitoring.coreos.com -o jsonpath='{range .items[*]}{.metadata.annotations.operator\.prometheus\.io/version} {end}'
    expect_exact: "0.92.0 0.92.0 0.92.0 0.92.0"
  - id: four-crds-carry-otel-origin-label
    why: >-
      helm-controller stamps helm.toolkit.fluxcd.io/name=<HR> on every CRD it
      applies from crds/ (crds.go setOriginVisitor). otel-operator on all four =
      the last writer was the otel HR's CreateReplace, which is the mechanism
      this plan switches off. Anything else = a different writer; re-derive.
    run: kubectl get crd servicemonitors.monitoring.coreos.com podmonitors.monitoring.coreos.com probes.monitoring.coreos.com scrapeconfigs.monitoring.coreos.com -o jsonpath='{range .items[*]}{.metadata.labels.helm\.toolkit\.fluxcd\.io/name} {end}'
    expect_exact: "otel-operator otel-operator otel-operator otel-operator"
  - id: prometheuses-crd-is-kps-0.93.1
    why: >-
      The kube-prometheus-stack side of the split, as written. 0.93.1 = kps chart
      90.0.0 wrote it. If it reads 0.94.0, plan kube-prometheus-stack-91.4.0 ran
      before this one (allowed, see §6) — then §4.2 expects the four to stay at
      whatever they read in premise four-crds-still-stamped-0.92.0, and this
      expectation must be updated alongside it.
    run: kubectl get crd prometheuses.monitoring.coreos.com -o jsonpath='{.metadata.annotations.operator\.prometheus\.io/version}'
    expect_exact: "0.93.1"
  - id: kps-hr-on-90.0.0-or-a-91.x
    why: "90.0.0 is the written state; a 91.x means kube-prometheus-stack-91.4.0 already ran, which is an allowed ordering (§6). Anything else (a 92.x major, a downgrade) is a world this plan did not assess."
    run: kubectl get helmrelease -n monitoring kube-prometheus-stack -o jsonpath='{.spec.chart.spec.version}'
    expect_matches: "^(90\\.0\\.0|91\\.[0-9]+\\.[0-9]+)$"
  - id: four-crds-are-NOT-helm-release-resources
    why: >-
      THE premise that makes deletion impossible. Helm only deletes objects that
      are in the release manifest and disappear from the next render. Objects
      applied from a crds/ directory are never in the manifest. Zero
      CustomResourceDefinition documents in `helm get manifest otel-operator`
      proves the four CRDs (and the four otel ones) are outside Helm's
      three-way merge entirely, so no values change can make Helm delete them.
      (grep -c prints 0 and exits 1 — the runner evaluates the printed 0.)
    run: "helm get manifest otel-operator -n monitoring | grep -c '^kind: CustomResourceDefinition'"
    expect_exact: "0"
  - id: four-crds-carry-no-helm-release-annotation
    why: "Second, independent proof of the same fact from the live object: a templated release resource carries meta.helm.sh/release-name and app.kubernetes.io/managed-by=Helm. Both absent = applied via the crds/ path."
    run: kubectl get crd servicemonitors.monitoring.coreos.com -o jsonpath='rn=[{.metadata.annotations.meta\.helm\.sh/release-name}] mb=[{.metadata.labels.app\.kubernetes\.io/managed-by}]'
    expect_exact: "rn=[] mb=[]"
  - id: helm-controller-is-v1.6.x
    why: >-
      The claim "a condition:false subchart's crds/ are not collected" is read
      from helm-controller v1.6.3 internal/action/crds.go, where
      helmchartutil.ProcessDependencies(chrt, vals) runs BEFORE chrt.CRDObjects().
      Flux-side behaviour is version-specific; on any other minor, re-read
      crds.go at the deployed tag before executing.
    run: kubectl get deploy -n flux-system helm-controller -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_matches: "helm-controller:v1\\.6\\."
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/monitoring.md
generated: "2026-09-15"
---

# Prometheus CRD ownership: make kube-prometheus-stack the single writer (otel-operator `crds.installPrometheus: false`)

## 1) Summary & why held

### 1.1 What is wrong

The ten `monitoring.coreos.com` CRDs are written by **two** HelmReleases in
`monitoring`, both with Flux `install.crds: CreateReplace` / `upgrade.crds:
CreateReplace`, and the last one to upgrade wins:

| CRD | last writer (`helm.toolkit.fluxcd.io/name`) | `operator.prometheus.io/version` | gen | helm-controller last write |
|---|---|---|---|---|
| alertmanagerconfigs, alertmanagers, prometheusagents, prometheuses, prometheusrules, thanosrulers | kube-prometheus-stack | 0.93.1 | 2–5 | 2026-08-19T05:40:06Z |
| **servicemonitors, podmonitors, probes, scrapeconfigs** | **otel-operator** | **0.92.0** | **30** | **2026-09-14T05:45:08Z** |

`2026-09-14T05:45:08Z` is exactly helm revision 23 of `otel-operator`
(`opentelemetry-kube-stack` 0.20.6 → 0.20.9, landed by nightly Step 0 as a
safe patch). Every otel-operator chart bump — 23 revisions so far, near-weekly
in the AUTO lane — re-stamps those four CRDs with the copy bundled in the
umbrella chart, which is generated from prometheus-operator **0.92.0** (the
subchart README says so and both 0.20.9 and 0.21.0 ship that same copy).
kube-prometheus-stack only writes CRDs during its own install/upgrade action,
so between kps bumps the four sit at 0.92.0 nearly all the time. `managedFields`
also shows a `kubectl Apply` at 2026-08-18T13:32:11Z on the four — a hand
re-apply that the next otel bump overwrote. That is the "accept and re-apply
after each otel bump" option, already tried by accident: a treadmill.

**Function is unaffected today** — no ServiceMonitor/PodMonitor/Probe/
ScrapeConfig in the cluster uses a field added after 0.92.0 — what is lost is
schema validation of newer fields, and after `kube-prometheus-stack-91.4.0`
(operator 0.94.0) the gap widens to two operator minors. The finding's own
action text says the same. This is not urgent; it is a defect that must be
fixed once, correctly, because the wrong fix is catastrophic.

Sweep record: `F-a85e8943` (section `plan`). Its title carries an `[AR-072]`
prefix only because AR-072's needle is the bare substring `opentelemetry`; that
AR accepts otel *image* findings, not this ownership defect — an incidental,
over-broad match (CLAUDE.md "risk needle" rule). Not changed here; reported.

### 1.2 The question this plan exists to answer — with proof

> Does `opentelemetry-kube-stack` render those four CRDs from a `crds/`
> directory (Helm never deletes those on a values change) or as templated
> release resources gated on `crds.installPrometheus` (in which case `false`
> makes Helm DELETE them and Kubernetes cascade-deletes every CR of those kinds)?

**Answer: `crds/` directory, condition-gated subchart. `false` stops the writes
and deletes nothing.** Three independent lines of evidence, all re-runnable:

**(a) Chart layout — `helm pull open-telemetry/opentelemetry-kube-stack --version 0.20.9`, 2026-09-15.**
The umbrella has **no** top-level `crds/`. `Chart.yaml` declares:

```yaml
- condition: crds.install,crds.installOtel
  name: otel-crds
- condition: crds.install,crds.installPrometheus
  name: prometheus-crds
```

`charts/prometheus-crds/` contains exactly `Chart.yaml`, `README.md` and
`crds/monitoring.coreos.com_{podmonitors,probes,scrapeconfigs,servicemonitors}.yaml`
— **no `templates/` directory at all**. `crds.installPrometheus` appears in
`Chart.yaml` (the condition) and `values.yaml` (default `true`) and **nowhere
else** in the chart. Chart 0.21.0 is identical in layout and content for this
subchart. `helm template … --include-crds` with our HR values lists all 8 CRDs;
with `--set crds.installPrometheus=false` it lists only the 4 `opentelemetry.io`
ones; **without** `--include-crds` (i.e. the release manifest) it lists **0**
CRDs either way, and the two release manifests differ only in the regenerated
webhook cert/`caBundle` (7 `caBundle` lines + `ca.crt`/`tls.crt`/`tls.key`).

**(b) helm-controller source — `fluxcd/helm-controller` tag v1.6.3 (the deployed
image), `internal/action/crds.go`.** `applyCRDs` is the only CRD code path for
`install.crds`/`upgrade.crds`:

```go
if err := helmchartutil.ProcessDependencies(chrt, vals); err != nil { … }   // prunes condition:false subcharts
…
for _, obj := range chrt.CRDObjects() { … }                                   // collects crds/ AFTER the prune
…
// Note, we build the originals from the current set of Custom Resource
// Definitions, and therefore this upgrade will never delete CRDs that
// existed in the former release but no longer exist in the current
// release.
```

`ProcessDependencies` → `processDependencyEnabled` evaluates the comma-separated
condition list (first path that resolves to a bool wins; `crds.install` is unset
in the chart so `crds.installPrometheus` decides) and calls `c.SetDependencies`
with the disabled charts removed. `CreateReplace` then does Create-or-Update on
what remains; there is no Delete branch. So with the key `false`, helm-controller
neither writes nor deletes the four CRDs on the otel HR's install/upgrade.

**(c) Live object metadata (premises).** The four CRDs carry
`helm.toolkit.fluxcd.io/name=otel-operator` (helm-controller's crds/-applier
origin label) and **no** `meta.helm.sh/release-name` annotation, **no**
`app.kubernetes.io/managed-by=Helm` label; `helm get manifest otel-operator`
contains **zero** `CustomResourceDefinition` documents. They are outside Helm's
release three-way merge entirely — Helm cannot delete what is not in the
manifest.

### 1.3 Options considered

| Option | Verdict |
|---|---|
| `crds.installPrometheus: false` on the otel HR | **Chosen.** Proven `crds/`-only + condition-gated (§1.2). One key, no restart, revert = re-enable. |
| `helm.sh/resource-policy: keep` on the four CRDs | Irrelevant: that annotation only affects objects in the release manifest. These are not (§1.2 c). |
| otel HR `install.crds`/`upgrade.crds: Skip` | Would also skip the **otel** CRDs (`opentelemetrycollectors` etc.), which must follow the operator subchart on real bumps. Rejected. |
| Accept, and re-apply kps CRDs after each otel bump | Already happened once by hand (2026-08-18) and was overwritten 4 weeks later; kps only writes on its own upgrade. A treadmill, and a manual `kubectl apply` of CRDs is a direct cluster mutation. Rejected. |

**Not a false-positive hold.** The finding is right that the values flip must not
be done blind; the proof above is what makes it safe. Risk `medium` is for the
stakes, not the probability (frontmatter comment).

## 2) Pre-checks

Run inside the window. Every check has a pass condition; a fail is a no-go.

```bash
cd /Users/mu/code/cberg-home-nextgen
export KUBECONFIG="$PWD/kubeconfig"
```

**2.1 — Premises hold (the scheduler ran them at placement; re-run now).**

```bash
python3 runbooks/plan-premises.py prometheus-crd-ownership --require-premises
```
**PASS:** exit 0, 10/10 premises pass. A fail on `four-crds-still-stamped-0.92.0`
or `prometheuses-crd-is-kps-0.93.1` with `kube-prometheus-stack-91.4.0` already
executed is the allowed ordering of §6 — update those two expectations from the
live values (same commit as the re-validation) and continue; any other fail: stop.

**2.2 — Flux fully green, nothing mid-upgrade in `monitoring`.**

```bash
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'
helm history otel-operator -n monitoring | tail -2
```
**PASS:** both `flux get` commands print only the header; the last helm revision
is `deployed` (23 at plan time). Note the revision number — §4.1 expects +1.

**2.3 — CRD baseline. Write these down; §4.2 is a diff against them.**

```bash
kubectl get crd -o json --show-managed-fields | python3 -c "
import sys,json
for c in json.load(sys.stdin)['items']:
    m=c['metadata']; n=m['name']
    if not n.endswith('monitoring.coreos.com') and not n.endswith('opentelemetry.io'): continue
    hc=[f['time'] for f in m.get('managedFields',[]) if f.get('manager')=='helm-controller']
    print(f\"{n:48s} gen={m['generation']:<3} rv={m['resourceVersion']:<10} opver={m.get('annotations',{}).get('operator.prometheus.io/version','-'):<7} origin={m.get('labels',{}).get('helm.toolkit.fluxcd.io/name'):<22} hc_write={hc[-1] if hc else '-'}\")"
```
**Baseline measured 2026-09-15 06:30Z:** the four contested CRDs `gen=30`,
`rv=370023940..46`, `opver=0.92.0`, `origin=otel-operator`,
`hc_write=2026-09-14T05:45:08Z`; the six kps CRDs `opver=0.93.1`,
`origin=kube-prometheus-stack`; the four `opentelemetry.io` CRDs `gen=2`,
`origin=otel-operator`. **PASS:** the picture matches the premises (14 rows).

**2.4 — Scrape-surface baseline (the contents this change must not touch).**

```bash
for k in servicemonitors podmonitors probes scrapeconfigs; do
  printf '%-16s %s\n' $k "$(kubectl get $k.monitoring.coreos.com -A --no-headers | wc -l | tr -d ' ')"
done
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9099:9090 >/dev/null 2>&1 & sleep 3
curl -s localhost:9099/api/v1/targets | python3 -c "
import sys,json; t=json.load(sys.stdin)['data']['activeTargets']
print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))"
kill %1 2>/dev/null
```
**Baseline 2026-09-15:** `servicemonitors 49 · podmonitors 3 · probes 4 ·
scrapeconfigs 3` (59), `targets 98 up 98`. **PASS:** all targets up (a down
target makes the §4.3 comparison ambiguous).

**2.5 — Re-prove the chart layout for the EXACT pinned version (read-only, local).**
This is what makes the plan safe against a chart patch that landed since it was
written. Runs in the scratchpad; nothing touches the cluster.

```bash
SP=$(mktemp -d /private/tmp/claude-501/crd-own.XXXX)
VER=$(kubectl get helmrelease -n monitoring otel-operator -o jsonpath='{.spec.chart.spec.version}')
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts >/dev/null 2>&1; helm repo update open-telemetry >/dev/null
helm pull open-telemetry/opentelemetry-kube-stack --version "$VER" --untar --untardir "$SP"
C="$SP/opentelemetry-kube-stack"
echo "top-level crds/: $(ls -d $C/crds 2>/dev/null || echo NONE)"
echo "prometheus-crds subchart files:"; find "$C/charts/prometheus-crds" -type f | sort
echo "templates/ under prometheus-crds: $(ls -d $C/charts/prometheus-crds/templates 2>/dev/null || echo NONE)"
grep -n 'condition: crds.install,crds.installPrometheus' "$C/Chart.yaml"
grep -rn 'operator.prometheus.io/version' "$C/charts/prometheus-crds/crds/" | sed 's/.*version: //' | sort -u
kubectl get helmrelease -n monitoring otel-operator -o jsonpath='{.spec.values}' | python3 -c "import sys,json,yaml;yaml.safe_dump(json.load(sys.stdin),open('$SP/values.yaml','w'))"
echo "--- CRDs rendered WITH --include-crds, default:"; helm template otel-operator "$C" -n monitoring --include-crds -f "$SP/values.yaml" --kube-version 1.36.0 | grep -E '^  name: .*\.(monitoring\.coreos\.com|opentelemetry\.io)$' | sort
echo "--- CRDs rendered WITH --include-crds, installPrometheus=false:"; helm template otel-operator "$C" -n monitoring --include-crds -f "$SP/values.yaml" --set crds.installPrometheus=false --kube-version 1.36.0 | grep -E '^  name: .*\.(monitoring\.coreos\.com|opentelemetry\.io)$' | sort
echo "--- CRDs in the RELEASE manifest (no --include-crds), either way:"; helm template otel-operator "$C" -n monitoring -f "$SP/values.yaml" --kube-version 1.36.0 | grep -c '^kind: CustomResourceDefinition'
echo "--- release-manifest diff default vs false (expect only caBundle/ca.crt/tls.* lines):"
diff <(helm template otel-operator "$C" -n monitoring -f "$SP/values.yaml" --kube-version 1.36.0) <(helm template otel-operator "$C" -n monitoring -f "$SP/values.yaml" --set crds.installPrometheus=false --kube-version 1.36.0) | grep -E '^[<>]' | sed -E 's/^([<>] +[a-zA-Z.-]+:).*/\1/' | sort | uniq -c
```
**PASS — ALL of:** `top-level crds/: NONE`; the subchart lists exactly
`Chart.yaml`, `README.md` and four `crds/monitoring.coreos.com_*.yaml`;
`templates/ under prometheus-crds: NONE`; the condition line is found; the
bundled version prints one value (0.92.0 at plan time); default render lists 8
CRD names, the `false` render lists only the 4 `opentelemetry.io` names; release
manifest CRD count `0`; the diff shows only `caBundle`, `ca.crt`, `tls.crt`,
`tls.key` lines. **Any `templates/` under `prometheus-crds`, any
`CustomResourceDefinition` in the release manifest, or any non-cert diff line
= STOP; the proof no longer holds for this chart version.**

## 3) Steps

GitOps only. One file, one key, one commit. No manual reconcile (the git
webhook drives it; the HR spec change triggers the helm upgrade immediately).

**3.1 — No alert silence needed.** Nothing restarts and no scrape gap occurs.
Drop the active-update marker anyway so a stray transient is classified:

```bash
runbooks/update-marker.sh add otel-operator monitoring 1 "crds.installPrometheus=false (plan prometheus-crd-ownership)"
```

**3.2 — The edit.** Insert the block directly under `clusterName: cberg-home`
in the HelmRelease values. Do **not** set `crds.install` (it is the first path
in the condition list and would override `installPrometheus`), and leave
`installOtel` at its default `true`.

```bash
python3 - <<'PYEOF'
from pathlib import Path
p = Path("kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml")
s = p.read_text()
anchor = "  values:\n    clusterName: cberg-home\n"
block = anchor + """
    # Prometheus-operator CRD ownership (plan prometheus-crd-ownership, F-a85e8943).
    # The umbrella chart bundles an OLDER copy of servicemonitors/podmonitors/probes/
    # scrapeconfigs under charts/prometheus-crds/crds/ (a crds/ directory behind the
    # Chart.yaml condition `crds.install,crds.installPrometheus`), and Flux
    # CreateReplace re-stamped them on every chart bump, undoing kube-prometheus-stack's
    # newer set. crds/-directory objects are never Helm release resources, so `false`
    # only stops the WRITES — it deletes nothing (helm-controller crds.go:
    # ProcessDependencies runs before CRDObjects; CreateReplace never deletes).
    # kube-prometheus-stack is the single owner of all ten monitoring.coreos.com CRDs.
    # Do NOT set `crds.install` here: it precedes installPrometheus in the condition.
    crds:
      installPrometheus: false
"""
assert s.count(anchor) == 1, "anchor not found exactly once — edit by hand"
p.write_text(s.replace(anchor, block, 1))
PYEOF
git --no-pager diff kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml
```
**Expected diff:** exactly the comment block plus `crds:` /
`installPrometheus: false` added; nothing removed.

**3.3 — Render check on the edited file (local, seconds).** Re-run the two
`--include-crds` renders from §2.5 with the values from the edited file; the
`monitoring.coreos.com` names must be absent and the release manifest CRD
count `0`:

```bash
python3 -c "import yaml;hr=yaml.safe_load(open('kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml'));yaml.safe_dump(hr['spec']['values'],open('$SP/values-new.yaml','w'))"
helm template otel-operator "$C" -n monitoring --include-crds -f "$SP/values-new.yaml" --kube-version 1.36.0 | grep -E '^  name: .*\.(monitoring\.coreos\.com|opentelemetry\.io)$' | sort
helm template otel-operator "$C" -n monitoring -f "$SP/values-new.yaml" --kube-version 1.36.0 | grep -c '^kind: CustomResourceDefinition'
```
**PASS:** 4 `opentelemetry.io` names only; `0`.

**3.4 — Commit and push (`--only`, shared worktree).**

```bash
cat > /tmp/crd-own-msg.txt <<'MSGEOF'
fix(monitoring): otel-operator stops writing the Prometheus CRDs (crds.installPrometheus=false)

opentelemetry-kube-stack bundles prometheus-operator 0.92.0 copies of the
servicemonitors/podmonitors/probes/scrapeconfigs CRDs under a crds/ directory
in its prometheus-crds subchart, and Flux CreateReplace re-stamped them on
every otel-operator chart bump, undoing kube-prometheus-stack's newer set
(0.93.1 today). Disable that subchart via its Chart.yaml condition.

Proven before flipping: the subchart is crds/-only (no templates/), the four
CRDs are not in the otel-operator release manifest and carry no Helm release
annotation, and helm-controller v1.6.3 prunes condition:false subcharts before
collecting crds/ and never deletes CRDs on CreateReplace. So this removes a
WRITER; the CRDs and all 59 CRs of those kinds are untouched. kube-prometheus-
stack becomes their single owner from its next upgrade.

Plan: runbooks/maintenance/plans/prometheus-crd-ownership.md
Finding: F-a85e8943

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012bXdxrZGGHNy5e4RnF6seD
MSGEOF
git fetch origin main && git merge --ff-only origin/main
git add -N kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml
git commit --only kubernetes/apps/monitoring/otel-operator/app/helmrelease.yaml -F /tmp/crd-own-msg.txt
git log -1 --format=%s        # must be THIS subject (a concurrent commit can swap message files)
git show --stat HEAD          # exactly ONE file
git push origin main
```

**3.5 — Watch the reconcile.** Expected: Kustomization `otel-operator` applies
the new HR spec within a minute of the push; helm-controller upgrades to
revision +1 with the SAME chart version; no pod is replaced.

```bash
kubectl get helmrelease -n monitoring otel-operator -w     # until Ready=True, then Ctrl-C
helm history otel-operator -n monitoring | tail -2
```
If the HR has not started reconciling 5 minutes after the push (webhook missed):
`mise exec -- flux reconcile source git flux-system` — the one manual reconcile
the SOP allows; it only re-fetches git.

**3.6 — On success:** clear the marker and retire this plan file in the same
commit series (plans are transient). Then follow §6 for the two sibling plans.

```bash
runbooks/update-marker.sh clear otel-operator
```

## 4) Verification

Floor: HR Ready, revision +1, no restarts. The section is the CRDs and the
scrape surface.

**4.1 — HelmRelease: values-only upgrade, same chart, nothing rolled.**

```bash
kubectl get helmrelease -n monitoring otel-operator \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion} {.status.history[0].version}{"\n"}'
kubectl get helmrelease -n monitoring otel-operator -o jsonpath='{.spec.values.crds}{"\n"}'
helm get values otel-operator -n monitoring | grep -A1 '^crds:'
kubectl get pods -n monitoring -l 'app.kubernetes.io/name in (opentelemetry-operator)' -o custom-columns='NAME:.metadata.name,STARTED:.status.startTime,RESTARTS:.status.containerStatuses[0].restartCount'
kubectl get daemonset -n monitoring otel-operator-daemon-collector -o jsonpath='{.status.numberReady}/{.status.desiredNumberScheduled} gen={.metadata.generation}{"\n"}'
```
**PASS:** `True 0.20.9 <baseline revision + 1>` (chart version unchanged from
§2.1's premise); `{"installPrometheus":false}`; `helm get values` shows
`crds:` / `installPrometheus: false`; the operator pod's `STARTED` is **older
than the push** (not rolled) with 0 new restarts; DaemonSet `3/3` with the same
generation as before.

**4.2 — The four CRDs: present, unchanged, and NOT written by this upgrade.**

```bash
UPG=$(helm history otel-operator -n monitoring -o json | python3 -c "import sys,json;print(json.load(sys.stdin)[-1]['updated'])")
echo "otel upgrade at: $UPG"
kubectl get crd -o json --show-managed-fields | python3 -c "
import sys,json
for c in json.load(sys.stdin)['items']:
    m=c['metadata']; n=m['name']
    if not n.endswith('monitoring.coreos.com') and not n.endswith('opentelemetry.io'): continue
    hc=[f['time'] for f in m.get('managedFields',[]) if f.get('manager')=='helm-controller']
    print(f\"{n:48s} gen={m['generation']:<3} rv={m['resourceVersion']:<10} opver={m.get('annotations',{}).get('operator.prometheus.io/version','-'):<7} origin={m.get('labels',{}).get('helm.toolkit.fluxcd.io/name'):<22} hc_write={hc[-1] if hc else '-'} created={m['creationTimestamp']}\")"
```
**PASS — ALL of, for `servicemonitors`, `podmonitors`, `probes`, `scrapeconfigs`:**
the row EXISTS (14 rows total, none missing); `created=2026-01-05T00:23:30Z`
(the original objects, not re-created); `gen`, `rv`, `opver` and `origin` are
**byte-identical to the §2.3 baseline** (`gen=30`, `opver=0.92.0`,
`origin=otel-operator` at plan time); `hc_write` is **still the baseline
timestamp** (`2026-09-14T05:45:08Z`), i.e. **older than `$UPG`**. For the four
`opentelemetry.io` CRDs `hc_write` **equals** `$UPG` (helm-controller did run
its CRD pass this upgrade — and applied only those four) with `gen=2` unchanged
(byte-identical re-apply). The six kps CRDs are untouched.
**FAIL conditions:** any of the four missing (→ §5.3 immediately); `hc_write`
on any of the four equal to `$UPG` (the subchart was still collected — the
condition did not take; revert per §5.1 and re-derive §1.2 against the deployed
helm-controller); `gen` moved.

**4.3 — CONTENTS ASSERTIONS (the scrape surface these CRDs define).**

```
CONTENTS ASSERTION 1: every CR of the four kinds still EXISTS — measured by the
  per-kind `kubectl get … -A | wc -l` counts, compared to the §2.4 baseline
  (49/3/4/3). A CRD delete would cascade these to 0; a count that is merely
  "non-zero" is not enough — it must EQUAL the baseline (±0 unless a pod/app
  legitimately came or went during the window, which must be named).
CONTENTS ASSERTION 2: Prometheus still SCRAPES the targets those CRs generate —
  measured by count(up == 1) and the active-target count, evaluated AFTER the
  helm upgrade completed, compared to the §2.4 baseline (98/98). The operator
  regenerates scrape config from the CRs; if the CRs vanished, targets vanish.
CONTENTS ASSERTION 3: the otel operator's validating webhook still answers with
  the regenerated cert — measured by a read of an OpenTelemetryCollector CR and
  a dry-run apply of the live daemon CR, compared to "no webhook/x509 error".
```

```bash
for k in servicemonitors podmonitors probes scrapeconfigs; do
  printf '%-16s %s\n' $k "$(kubectl get $k.monitoring.coreos.com -A --no-headers | wc -l | tr -d ' ')"
done
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9099:9090 >/dev/null 2>&1 & sleep 3
curl -s localhost:9099/api/v1/targets | python3 -c "
import sys,json; t=json.load(sys.stdin)['data']['activeTargets']
print('targets',len(t),'up',sum(1 for x in t if x['health']=='up'))
print('down:',[(x['labels'].get('job'),x['labels'].get('instance')) for x in t if x['health']!='up'])"
curl -s -G localhost:9099/api/v1/query --data-urlencode 'query=count(up == 1)' | python3 -c "import sys,json;print('count(up==1):',json.load(sys.stdin)['data']['result'][0]['value'][1])"
kill %1 2>/dev/null
kubectl get opentelemetrycollector -n monitoring otel-operator-daemon -o jsonpath='{.metadata.name} {.status.version}{"\n"}'
kubectl get opentelemetrycollector -n monitoring otel-operator-daemon -o yaml | kubectl apply --dry-run=server -f - 2>&1 | tail -1
kubectl logs -n monitoring deploy/otel-operator-opentelemetry-operator --since=15m | grep -ciE 'x509|certificate|webhook.*(error|fail)'
```
**PASS:** counts `49 / 3 / 4 / 3` (= §2.4); `targets 98 up 98`, `down: []`,
`count(up==1): 98` (= §2.4); the CR reads back with its version; the dry-run
prints `… configured (server dry run)` or `unchanged (server dry run)` — not an
`x509`/`webhook` error; the log grep prints `0` (grep -c exits 1 on zero
matches — that is the pass).

**4.4 — Optional, if the helm-controller log level captures it:**
`kubectl logs -n flux-system deploy/helm-controller --since=20m | grep otel-operator | grep -i CustomResourceDefinition`
should show `successfully applied 4 CustomResourceDefinition(s)` (was 8). Not
retained at the default level on this cluster (checked 2026-09-15); §4.2's
`hc_write` comparison is the authoritative form of the same fact.

## 5) Rollback

**5.1 — Git revert (the real rollback). Never deletes a CRD.**

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
git revert --no-edit <sha-of-3.4-commit>
git show --stat HEAD          # exactly helmrelease.yaml
git push origin main
```

Flux upgrades otel-operator to revision +2 with the key gone → chart default
`true` → helm-controller collects the subchart's `crds/` again and CreateReplace
**re-stamps** the four CRDs (operator-version 0.92.0, `hc_write` = revert time,
`gen` +1). That is exactly the pre-plan state — a rewrite, not a delete, and the
CRs are untouched in both directions. **Confirm:**

```bash
kubectl get crd servicemonitors.monitoring.coreos.com podmonitors.monitoring.coreos.com probes.monitoring.coreos.com scrapeconfigs.monitoring.coreos.com \
  -o custom-columns='NAME:.metadata.name,GEN:.metadata.generation,OPVER:.metadata.annotations.operator\.prometheus\.io/version,ORIGIN:.metadata.labels.helm\.toolkit\.fluxcd\.io/name'
for k in servicemonitors podmonitors probes scrapeconfigs; do printf '%-16s %s\n' $k "$(kubectl get $k.monitoring.coreos.com -A --no-headers | wc -l | tr -d ' ')"; done
```
**Back:** four rows, `ORIGIN=otel-operator`, `GEN` = baseline+1, `OPVER=0.92.0`;
counts `49/3/4/3`.

**5.2 — If the helm upgrade itself failed** (`Ready=False`, remediation
`strategy: rollback` fires): helm-controller rolls the release back to the
previous revision on its own; CRDs are not part of a helm rollback, so nothing
happens to them either way. Still push the §5.1 revert so git matches the
cluster, then read the HR events for the actual cause.

**5.3 — Break-glass, ONLY if §4.2 shows a CRD missing** (contrary to §1.2; this
means the proof was wrong for the deployed versions — record that first).
Recreate the four CRDs from the kube-prometheus-stack chart that owns them, at
the version the six sibling CRDs read (0.93.1 at plan time), exactly as upstream
`UPGRADE.md` documents; then let the owners recreate the CRs:

```bash
V=$(kubectl get helmrelease -n monitoring kube-prometheus-stack -o jsonpath='{.spec.chart.spec.version}')
SP=$(mktemp -d /private/tmp/claude-501/crd-bg.XXXX); helm pull prometheus-community/kube-prometheus-stack --version "$V" --untar --untardir "$SP"
for c in servicemonitors podmonitors probes scrapeconfigs; do kubectl apply --server-side -f "$SP/kube-prometheus-stack/charts/crds/crds/crd-$c.yaml"; done
# CRs: kustomize-managed ones return on each Kustomization's next reconcile;
# Helm-rendered ServiceMonitors only on that release's next upgrade (drift
# detection is disabled cluster-wide), so force every HelmRelease once:
mise exec -- flux get helmreleases -A --no-header | awk '{print $1, $2}' | while read ns name; do mise exec -- flux reconcile helmrelease -n "$ns" "$name" --force >/dev/null 2>&1 || echo "retry: $ns/$name"; done
```
This is a direct cluster mutation and is listed here only as the recovery for
a state this plan asserts cannot occur; it is not a step.

## 6) Interference notes

- **Ordering across the three plans — THIS plan first.**
  1. `prometheus-crd-ownership` (this): the otel HR stops writing the four CRDs.
     Nothing else changes. From here on, **nightly Step 0's otel-operator patch
     bumps (the AUTO lane that caused every re-stamp) become inert for these
     CRDs.**
  2. `kube-prometheus-stack-91.4.0` (later window): CreateReplace writes all
     **ten** CRDs at 0.94.0 and flips the four's origin label to
     `kube-prometheus-stack`. Its §4.3 "`total 10 at 0.94.0: 10`" then holds
     permanently instead of until the next otel bump. Recommend the orchestrator
     add `depends_on: [prometheus-crd-ownership]` to that plan (this plan's
     single-file rule forbids editing it here).
  3. `otel-operator-0.21.0` (any later window): a chart bump that no longer
     touches `monitoring.coreos.com`. **Its premise
     `this-hr-owns-the-prometheus-crds` (expects label `otel-operator`) becomes
     STALE after step 2** and its `touches` still lists the four CRDs — that
     plan must be revised (drop the premise or flip it to
     `kube-prometheus-stack`, remove the four CRDs from `touches`) before it is
     scheduled after kps-91.4.0. If it runs between steps 1 and 2 instead, it
     is harmless (byte-identical otel CRDs only) and the premise still passes.
  The only BAD order is kps-91.4.0 → any otel bump → this plan: the four would
  sit at 0.92.0 until the next kps chart bump with no writer to fix them.
  `conflicts_with` on both siblings prevents sharing a window; the order above
  is the recommendation for consecutive windows.
- **Interim state between step 1 and step 2 is harmless.** The four CRDs keep
  a stale `helm.toolkit.fluxcd.io/name=otel-operator` label with no writer.
  helm-controller never garbage-collects CRDs by origin label, and `helm
  uninstall` never touches `crds/`-installed objects either; the label is
  purely informational until kps overwrites it.
- **Not a restart, not a scrape gap.** No pod is replaced (§4.1); Prometheus,
  Alertmanager, edot-collector and the daemon collectors are untouched. The
  window's health gate and any other plan's verification are unaffected. The
  only object that changes content is the otel operator's webhook cert Secret
  and the two webhook `caBundle`s — the same churn every otel upgrade causes.
- **Same-HR edits.** This plan and `otel-operator-0.21.0` edit the same file;
  if the orchestrator prefers a single otel commit, the values block from §3.2
  can ride with the 0.21.0 bump — but then §4.2's "generation unchanged across
  an upgrade" is measured across a chart bump, which is equally valid (0.21.0
  ships byte-identical CRDs). Keep them separate unless window capacity forces
  it; the proof reads cleaner as its own revision.
- **helm-controller version pin.** The Flux-side claim is read from v1.6.3
  source (premise `helm-controller-is-v1.6.x`). A Flux upgrade before this
  window means: re-read `internal/action/crds.go` at the new tag and confirm
  `ProcessDependencies` still precedes `CRDObjects()` before widening the
  premise.
- **Policy note for the operator (no action in this plan):** AR-072's needle
  `opentelemetry` also matches this finding's title, so the record shows
  `severity accepted` although the AR is about otel image findings. An
  over-broad needle; scope it (CLAUDE.md "risk needle" rules) so the next
  otel-titled defect is not silently absorbed.
