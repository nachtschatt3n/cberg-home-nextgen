---
plan_id: prometheus-crd-ownership
component: otel-operator              # the HelmRelease whose values change. The CRDs
                                      # themselves are cluster-scoped and end up owned by
                                      # kube-prometheus-stack — that HR is NOT edited here.
pr: null                              # no Renovate PR can exist: this is a one-key values
                                      # change on an existing HelmRelease, not a version bump.
kind: config
current: "monitoring.coreos.com CRDs are split-owned — 6 written by kube-prometheus-stack (operator-version 0.93.1), 4 (servicemonitors, podmonitors, probes, scrapeconfigs) re-stamped to operator-version 0.92.0 by otel-operator (opentelemetry-kube-stack 0.21.0, helm revision 24 deployed 2026-09-17T01:53:52Z, crds.installPrometheus UNSET so the chart default true applies, Flux crds: CreateReplace) on EVERY chart bump; the four sit at generation 30 and helm-controller's last WRITE to them is still 2026-09-14T05:45:08Z = revision 23, because revision 24's CreateReplace re-applied byte-identical content and therefore left no trace (measured 2026-09-20 — this is exactly why §4.2 cannot assert an absence)"
target: "otel-operator HelmRelease values crds.installPrometheus: false — helm-controller stops collecting the prometheus-crds subchart's crds/ on install and upgrade; the four CRDs are NOT deleted (they were never release resources) and kube-prometheus-stack becomes the single writer of all ten from its next upgrade (plan kube-prometheus-stack-91.4.1, which declares depends_on: prometheus-crd-ownership)"
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
    - helmrelease/otel-operator                            # values change -> revision 24 -> 25, SAME chart 0.21.0
    - secret/otel-operator-opentelemetry-operator-controller-manager-service-cert   # regenerated on EVERY helm
                                                           # upgrade (autoGenerateCert.recreate: true) — not new.
                                                           # PROMOTED to §4.2's MUST-MOVE CONTROL: it is the only
                                                           # object in this change that is guaranteed to differ
                                                           # afterwards, so it is what separates "the upgrade ran
                                                           # and correctly skipped the CRDs" from "nothing ran".
    - mutatingwebhookconfiguration/otel-operator-opentelemetry-operator-mutation      # caBundle follows the cert
    - validatingwebhookconfiguration/otel-operator-opentelemetry-operator-validation  # caBundle follows the cert
    - "crd/{servicemonitors,podmonitors,probes,scrapeconfigs}.monitoring.coreos.com — NOT modified, NOT deleted: this plan removes otel-operator as a WRITER. generation, resourceVersion and contents stay UNCHANGED after the upgrade — but that is a NECESSARY, NOT SUFFICIENT check (§4.2 c): it reads identically when nothing happened at all, which is why the efficacy proof is the helm DEPENDENCIES line (§4.2 a) and the liveness control is the cert Secret (§4.2 b). The stale helm.toolkit.fluxcd.io/name=otel-operator label stays until kube-prometheus-stack next writes them"
    - "crd/{instrumentations,opampbridges,opentelemetrycollectors,targetallocators}.opentelemetry.io — re-applied byte-identical by CreateReplace, exactly as on every otel-operator upgrade. They leave NO trace when re-applied: measured 2026-09-20 their helm-controller write time is still 2026-08-23T07:06:52Z, stale across revisions 21-24. They are therefore NOT usable as a positive control (§4.2)"
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
                                      # kps-91.4.1 in a LATER window (§6).
                                      # 2026-09-17: otel-operator-0.21.0 ref REMOVED — that
                                      # plan executed (9a35168f) and was retired (37f7c7a6)
                                      # in the nightly window. It edited the SAME HelmRelease
                                      # spec, so two otel-operator upgrades in one window
                                      # would have confounded §4's "generation unchanged
                                      # across an upgrade" assertion. SEE F-7235625a: that
                                      # assertion was VACUOUS in the ordinary case —
                                      # generation, resourceVersion AND the helm-controller
                                      # write timestamp all stayed unchanged through that
                                      # upgrade WHILE this HelmRelease was still the
                                      # configured writer. RESOLVED 2026-09-20: §4.2 was
                                      # rewritten around a positive proof (the pruned
                                      # `helm get metadata` DEPENDENCIES set) plus a
                                      # must-move control (the webhook cert Secret), so it
                                      # no longer rests on an absence.
                                      # The LIVE successor is otel-operator-0.23.0 (draft,
                                      # window: null, human-gated). It already declares BOTH
                                      # `depends_on: prometheus-crd-ownership` AND
                                      # `conflicts_with: prometheus-crd-ownership` (verified
                                      # 2026-09-20), so the exclusion is enforced from that
                                      # side and is not re-added here. Any FUTURE
                                      # otel-operator plan must do the same.
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
status: vetted   # RE-VETTED 2026-09-20 after the gate rewrite. An independent reviewer re-ran every gate against the live cluster and confirmed all nine defects are fixed: gates_still_vacuous NONE, commands_that_error NONE, every_gate_can_fail TRUE. Its 'needs-fix' verdict was explicitly scoped to SCHEDULING/AUTHORISATION ONLY (commit, re-vet, slot, GO) and explicitly instructed NOT to re-edit sections 4 or 5. Validator green, premises 10/10 PASS.
window: null   # UNSCHEDULED 2026-09-20 by the sun-attended window agent. It held sun-attended:2026-09-20 and that window RAN, but the plan was NOT executed: section 4.2 is both vacuous (F-7235625a, re-measured live) and UNSATISFIABLE as written, and section 5.1 rollback confirmation expects GEN=baseline+1 which cannot happen for a byte-identical CreateReplace. The core safety proof in section 1.2/2.5 was independently re-verified and HOLDS. Deliberately NOT re-slotted: sun-attended:2026-09-27 is owned exclusively by talos-1.14.0 (140 of 200 min, needs the whole slot). The scheduler assigns once sections 4.1/4.2/4.4/5.1 are rewritten around the validated positive proof (helm get metadata DEPENDENCIES). Prior rationale below is HISTORICAL.
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
      90.0.0 wrote it. If it reads 0.94.0, plan kube-prometheus-stack-91.4.1 ran
      before this one (allowed, see §6) — then §4.2 expects the four to stay at
      whatever they read in premise four-crds-still-stamped-0.92.0, and this
      expectation must be updated alongside it.
    run: kubectl get crd prometheuses.monitoring.coreos.com -o jsonpath='{.metadata.annotations.operator\.prometheus\.io/version}'
    expect_exact: "0.93.1"
  - id: kps-hr-on-90.0.0-or-a-91.x
    why: "90.0.0 is the written state (measured 2026-09-20: helm revision 39, appVersion v0.93.1); a 91.x means kube-prometheus-stack-91.4.1 already ran, which is an allowed ordering (§6). Anything else (a 92.x major, a downgrade) is a world this plan did not assess."
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
safe patch). Every otel-operator chart bump — 24 revisions so far, near-weekly
in the AUTO lane — re-stamps those four CRDs with the copy bundled in the
umbrella chart, which is generated from prometheus-operator **0.92.0** (the
subchart README says so and both 0.20.9 and 0.21.0 ship that same copy).

**The re-stamp is usually INVISIBLE, and that is what §4.2 had to be rewritten
around.** Revision 24 (0.20.9 → 0.21.0, `2026-09-17T01:53:52Z`) collected and
re-applied the subchart's `crds/` exactly as every other bump does — yet the
four CRDs still read `gen=30`, `rv=370023940..46` and
`hc_write=2026-09-14T05:45:08Z` today (measured 2026-09-20). Because 0.21.0
ships the byte-identical 0.92.0 copy, a CreateReplace of unchanged content is a
no-op Replace: it bumps no `generation`, no `resourceVersion`, and updates no
`managedFields` timestamp. So "the four CRDs did not move" is what **both** a
successful change and a completely failed one look like. The contention is real
and continuous; it is simply not observable as object churn (F-7235625a).
kube-prometheus-stack only writes CRDs during its own install/upgrade action,
so between kps bumps the four sit at 0.92.0 nearly all the time. `managedFields`
also shows a `kubectl Apply` at 2026-08-18T13:32:11Z on the four — a hand
re-apply that the next otel bump overwrote. That is the "accept and re-apply
after each otel bump" option, already tried by accident: a treadmill.

**Function is unaffected today** — no ServiceMonitor/PodMonitor/Probe/
ScrapeConfig in the cluster uses a field added after 0.92.0 — what is lost is
schema validation of newer fields, and after `kube-prometheus-stack-91.4.1`
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
or `prometheuses-crd-is-kps-0.93.1` with `kube-prometheus-stack-91.4.1` already
executed is the allowed ordering of §6 — update those two expectations from the
live values (same commit as the re-validation) and continue; any other fail: stop.

**2.2 — Flux fully green, nothing mid-upgrade in `monitoring`.**

```bash
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
mise exec -- flux get helmreleases   -A | awk 'NR==1 || $5 != "True"'
helm history otel-operator -n monitoring | tail -2
```
**PASS:** both `flux get` commands print only the header; the last helm revision
is `deployed` — **24**, chart `opentelemetry-kube-stack-0.21.0`, deployed
`2026-09-17T01:53:52Z` (measured 2026-09-20). Note the revision number: §4.1
expects **25**. If it is already >24, an otel upgrade landed between this
pre-check and the plan being written — re-read §2.5 for the new chart version
before continuing.

**2.3 — Baselines. Write ALL THREE down; §4.2 is a diff against them.**

Three captures, not one, because §4.2 needs a *positive* proof (a), a *must-move*
liveness control (b) and a *non-regression* set (c). Capture (c) alone is what
made the old §4.2 vacuous — it reads identically whether or not anything ran.

```bash
# (a) EFFICACY WITNESS — the stored release's PRUNED subchart set.
helm get metadata otel-operator -n monitoring | grep -E '^(VERSION|REVISION|DEPENDENCIES):'

# (b) MUST-MOVE CONTROL — this Secret is deleted+recreated on EVERY helm upgrade
#     (our values set admissionWebhooks.autoGenerateCert.recreate: true).
kubectl get secret -n monitoring otel-operator-opentelemetry-operator-controller-manager-service-cert \
  -o jsonpath='rv={.metadata.resourceVersion} created={.metadata.creationTimestamp}{"\n"}'

# (c) NON-REGRESSION SET — all 14 CRDs. str() on the label: a CRD with no
#     helm.toolkit label yields None, and formatting None with a width
#     specifier raises TypeError (it does in §5.3's break-glass, where the raw
#     kps CRD files carry no helm.toolkit labels at all).
kubectl get crd -o json --show-managed-fields | python3 -c "
import sys,json
for c in json.load(sys.stdin)['items']:
    m=c['metadata']; n=m['name']
    if not n.endswith('monitoring.coreos.com') and not n.endswith('opentelemetry.io'): continue
    hc=[f['time'] for f in m.get('managedFields',[]) if f.get('manager')=='helm-controller']
    print(f\"{n:48s} gen={m['generation']:<3} rv={m['resourceVersion']:<12} opver={str(m.get('annotations',{}).get('operator.prometheus.io/version','-')):<8} origin={str(m.get('labels',{}).get('helm.toolkit.fluxcd.io/name')):<22} hc_write={hc[-1] if hc else '-'}\")"
```

**Baseline re-measured live 2026-09-20 (supersedes the 2026-09-15 figures):**

- **(a)** `VERSION: 0.21.0` · `REVISION: 24` ·
  `DEPENDENCIES: opentelemetry-operator,otel-crds,prometheus-crds`
  — **`prometheus-crds` IS PRESENT.** That is the string §4.2 (a) expects to
  change.
- **(b)** `rv=374720502`, `created=2026-09-17T01:53:53Z` — one second after
  revision 24's `DEPLOYED_AT`, confirming the Secret really is recreated per
  upgrade rather than merely updated.
- **(c)** the four contested CRDs `gen=30`, `rv=370023940..46`, `opver=0.92.0`,
  `origin=otel-operator`, `hc_write=2026-09-14T05:45:08Z`; the six kps CRDs
  `opver=0.93.1`, `origin=kube-prometheus-stack`,
  `hc_write=2026-08-19T05:40:05..07Z`; the four `opentelemetry.io` CRDs `gen=2`,
  `origin=otel-operator`, **`hc_write=2026-08-23T07:06:52Z`** — note that this is
  stale across revisions 21, 22, 23 **and** 24, which is why §4.2 does **not**
  use them as a control.

**PASS:** the picture matches the premises (14 rows in (c)); `prometheus-crds`
appears in (a). **If `prometheus-crds` is already ABSENT from (a), this plan has
already been applied** — stop and re-derive §1, do not push a second time.

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
**Baseline re-measured 2026-09-20:** `servicemonitors 49 · podmonitors 3 ·
probes 4 · scrapeconfigs 3` (59), `targets 98 up 98` — unchanged from
2026-09-15. **PASS:** all targets up (a down target makes the §4.3 comparison
ambiguous).

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

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
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
**revision 25** with the SAME chart version (0.21.0); no pod is replaced.

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
**PASS:** `True 0.21.0 25` — chart version **unchanged** from §2.2's measured
0.21.0, helm revision exactly **25** (baseline 24 + 1);
`{"installPrometheus":false}`; `helm get values` shows `crds:` /
`installPrometheus: false`; the operator pod's `STARTED` is **older than the
push** (not rolled) with 0 new restarts; DaemonSet `3/3` with the same
generation as before.
**HOW IT FAILS:** `Ready=False` → §5.2. A chart version other than 0.21.0 means
a chart bump rode along with the values change — the §2.5 layout proof was run
against a different chart than the one that just installed; revert (§5.1) and
re-run §2.5 before retrying. Revision still 24 → the upgrade never ran (see
§4.2 b, which is the authoritative check for this); revision 26+ → something
reconciled twice, so read `helm history` before trusting §4.2.

**4.2 — Did the change TAKE? Positive proof + must-move control + non-regression.**

*Rewritten 2026-09-20 (F-7235625a). The previous version of this section asserted
that `gen`, `rv`, `opver`, `origin` and `hc_write` were unchanged from the §2.3
baseline — **all of which are already true with nothing applied.** They survived
revision 24, an upgrade performed while otel-operator was still the configured
writer (§1.1). It also required the four `opentelemetry.io` CRDs to carry
`hc_write == $UPG`, which is **false before and after** (they read
`2026-08-23T07:06:52Z`), making a "PASS — ALL of" section unsatisfiable. Both
limbs are replaced below.*

```bash
UPG=$(helm history otel-operator -n monitoring -o json | python3 -c "import sys,json;print(json.load(sys.stdin)[-1]['updated'])")
echo "otel upgrade at: $UPG"

# (a) EFFICACY — the stored release's PRUNED subchart set.
helm get metadata otel-operator -n monitoring | grep -E '^(VERSION|REVISION|DEPENDENCIES):'

# (b) MUST-MOVE CONTROL — proves a helm upgrade actually ran at all.
kubectl get secret -n monitoring otel-operator-opentelemetry-operator-controller-manager-service-cert \
  -o jsonpath='rv={.metadata.resourceVersion} created={.metadata.creationTimestamp}{"\n"}'

# (c) NON-REGRESSION — all 14 CRDs (str() guards a label-less CRD; see §2.3 c).
kubectl get crd -o json --show-managed-fields | python3 -c "
import sys,json
for c in json.load(sys.stdin)['items']:
    m=c['metadata']; n=m['name']
    if not n.endswith('monitoring.coreos.com') and not n.endswith('opentelemetry.io'): continue
    hc=[f['time'] for f in m.get('managedFields',[]) if f.get('manager')=='helm-controller']
    print(f\"{n:48s} gen={m['generation']:<3} rv={m['resourceVersion']:<12} opver={str(m.get('annotations',{}).get('operator.prometheus.io/version','-')):<8} origin={str(m.get('labels',{}).get('helm.toolkit.fluxcd.io/name')):<22} hc_write={hc[-1] if hc else '-'} created={m['creationTimestamp']}\")"
```

**(a) EFFICACY LIMB — PASS: `DEPENDENCIES: opentelemetry-operator,otel-crds`,
with `prometheus-crds` ABSENT.** Also `VERSION: 0.21.0`, `REVISION: 25`.
The §2.3 (a) baseline read `opentelemetry-operator,otel-crds,prometheus-crds`,
so this is a **genuinely different string** before and after — which is exactly
what the old section lacked.

*Why this is a proof and not another tautology.* `helm get metadata` prints the
release's **pruned** dependency set — the output of the same
`chartutil.ProcessDependencies(chrt, vals)` that helm-controller runs
**immediately before** `chrt.CRDObjects()` in `applyCRDs` (§1.2 b). If
`prometheus-crds` is gone from that list, the subchart was not in the chart when
the `crds/` collection happened; that *is* the mechanism this plan switches off.
It is demonstrably prune-aware on this cluster, measured 2026-09-20:
`kube-prometheus-stack` declares **5** subcharts in `Chart.yaml`
(`crds`, `kube-state-metrics`, `prometheus-node-exporter`, `grafana`,
`prometheus-windows-exporter`) and its stored release lists only **3** —
`grafana` pruned by our `grafana.enabled: false`, `prometheus-windows-exporter`
by its own condition. `opentelemetry-kube-stack` likewise declares 5 and lists
3, with `kube-state-metrics` and `prometheus-node-exporter` already pruned here.

**HOW IT FAILS:** if the values key did not take — mis-nested under the wrong
parent, dropped by a Flux postBuild substitution, or overridden because someone
also set `crds.install` (the first path in the condition list) — the condition
still resolves true, the subchart is still collected, and `DEPENDENCIES` **still
contains `prometheus-crds`**. → the change is inert: revert per §5.1 and
re-derive §1.2 against the deployed helm-controller before retrying.

**(b) MUST-MOVE CONTROL — PASS: `rv` DIFFERS from the §2.3 (b) baseline
(`374720502`), and `created` equals `$UPG` (within ~2s).**
`admissionWebhooks.autoGenerateCert.recreate: true` deletes and recreates this
Secret on every helm upgrade — measured at revision 24:
`created=2026-09-17T01:53:53Z`, one second after that revision's `DEPLOYED_AT`.

**HOW IT FAILS:** an **unchanged** `rv` means no helm upgrade ran at all — the
commit never reconciled, the webhook was missed, or the HR did not re-render.
This is the limb that makes limb (c) meaningful: without it, "the four CRDs did
not move" is indistinguishable from "nothing happened", which is precisely the
hole F-7235625a found. **If (b) fails, do not read (a) or (c) as a result at
all:** drive the reconcile (§3.5) and re-measure.

**(c) NON-REGRESSION LIMB — PASS: 14 rows, none missing**; for the four
contested CRDs `created=2026-01-05T00:23:30Z` (the original objects, not
re-created), `gen=30`, `opver=0.92.0`, `origin=otel-operator`, `rv` = the §2.3
(c) baseline, and `hc_write` still `2026-09-14T05:45:08Z` — **older than
`$UPG`**. The six kps CRDs untouched.

**This limb is NECESSARY BUT NOT SUFFICIENT and is only informative once (b)
has passed** — on its own it is equally true when nothing ran.
**HOW IT FAILS:** any of the four **missing** → §5.3 immediately (the §1.2 proof
was wrong for the deployed versions — record that before recovering).
`hc_write` on any of the four **equal to `$UPG`**, or `gen` moved off 30 → the
subchart WAS still collected despite (a) → revert per §5.1.

**NOT a control — do NOT use the `opentelemetry.io` CRDs.** Measured 2026-09-20
they read `hc_write=2026-08-23T07:06:52Z`, **stale across revisions 21, 22, 23
and 24**, and they will still read that after revision 25: their content is
byte-identical between these chart versions, and a no-op Replace updates no
`managedFields` timestamp. Expect `gen=2` and that same stale timestamp; it
proves nothing either way.

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

**4.4 — DELETED: the helm-controller log gate cannot emit.**

This step used to grep helm-controller for
`successfully applied N CustomResourceDefinition(s)` (expecting 4, previously 8).
**Measured 2026-09-20: that line cannot appear at this cluster's log level, so
the gate returned the same empty result whether or not the change worked.** The
helm-controller pod has run since `2026-09-06T07:31:53Z`, so its buffer already
spans the 2026-09-17 upgrade (revision 24), and

```
kubectl logs -n flux-system deploy/helm-controller --since=168h | grep -ic customresourcedefinition
```

returns **0** across 5932 lines. A gate with one possible outcome is worse than
no gate — it reads as corroboration while measuring nothing — so it is removed
rather than demoted to "optional".

**Do NOT raise the controller's log level to recover it.** That is a mutation of
a `flux-system` workload, outside this plan's `touches` and its rollback path.
§4.2 (a) is the authoritative — and genuinely discriminating — form of the same
fact.

## 5) Rollback

**5.1 — Git revert (the real rollback). Never deletes a CRD.**

```bash
cd /Users/mu/code/cberg-home-nextgen
git fetch origin main && git merge --ff-only origin/main
git revert --no-edit <sha-of-3.4-commit>
git show --stat HEAD          # exactly helmrelease.yaml
git push origin main
```

Flux upgrades otel-operator to **revision 26** with the key gone → chart default
`true` → helm-controller collects the subchart's `crds/` again and CreateReplace
re-applies the four CRDs. That is exactly the pre-plan state — a rewrite, not a
delete, and the CRs are untouched in both directions. **Confirm:**

```bash
helm get metadata otel-operator -n monitoring | grep -E '^(REVISION|DEPENDENCIES):'
kubectl get crd servicemonitors.monitoring.coreos.com podmonitors.monitoring.coreos.com probes.monitoring.coreos.com scrapeconfigs.monitoring.coreos.com \
  -o custom-columns='NAME:.metadata.name,GEN:.metadata.generation,OPVER:.metadata.annotations.operator\.prometheus\.io/version,ORIGIN:.metadata.labels.helm\.toolkit\.fluxcd\.io/name'
for k in servicemonitors podmonitors probes scrapeconfigs; do printf '%-16s %s\n' $k "$(kubectl get $k.monitoring.coreos.com -A --no-headers | wc -l | tr -d ' ')"; done
```

**Back — ALL of:** `DEPENDENCIES` lists `prometheus-crds` **again** (the positive
proof that the revert took, mirroring §4.2 a — this, not the CRD rows, is what
confirms a rollback); `REVISION: 26`; four rows with **`GEN=30`, UNCHANGED**,
`ORIGIN=otel-operator`, `OPVER=0.92.0`; counts `49/3/4/3`.

**Do NOT expect `GEN` = baseline+1.** *(Corrected 2026-09-20 — the previous text
expected exactly that, and it is wrong.)* The four CRDs are already at 0.92.0,
which is the very copy the subchart ships, so the re-apply is **byte-identical**:
`generation`, `resourceVersion` and `hc_write` all stay put. This is not theory —
it is precisely what revision 24 did (§1.1). Expecting movement would make a
**successful** rollback read as a failed one, at the worst possible moment, and
the next step after "the rollback failed" is the break-glass in §5.3 that applies
CRDs by hand. Read `DEPENDENCIES`, not `GEN`.

*(The one case where `GEN` does move: if `kube-prometheus-stack-91.4.1` has
already stamped the four to 0.94.0, this re-apply is no longer byte-identical and
downgrades them to 0.92.0 with `gen`+1 and `hc_write` = revert time. That is the
BAD ordering §6 warns about, not the expected path.)*

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
SP=$(mktemp -d /private/tmp/claude-501/crd-bg.XXXX)
# Fetch the chart EXPLICITLY — the emergency path must not depend on ambient local
# `helm repo` state (§2.5 does the same for open-telemetry). This cluster's
# prometheus-community HelmRepository is OCI, not an https index
# (kubernetes/flux/meta/repositories/helm/prometheus-community.yaml:
#  url: oci://ghcr.io/prometheus-community/charts), so an OCI pull is the form that
# matches the real source AND needs no `helm repo add`/`helm repo update` at all —
# there is no local index that can be missing or stale. Verified 2026-09-20.
helm pull oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack --version "$V" --untar --untardir "$SP"
ls "$SP/kube-prometheus-stack/charts/crds/crds/"   # expect 10 crd-*.yaml (verified at 90.0.0)
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
  2. `kube-prometheus-stack-91.4.1` (later window): CreateReplace writes all
     **ten** CRDs at 0.94.0 and flips the four's origin label to
     `kube-prometheus-stack`. Its §4.3 "`total 10 at 0.94.0: 10`" then holds
     permanently instead of until the next otel bump. **Already wired — no
     action:** that plan declares `depends_on: [prometheus-crd-ownership]`
     (verified 2026-09-20), so `window-scheduler.py` will not place it until
     this plan is `executed`. The old note here recommended adding that
     dependency; it exists.
  3. `otel-operator-0.23.0` (any later window): the live otel chart-bump
     successor (0.21.0 → 0.23.0, status draft, `window: null`, human-gated).
     **Also already wired — no action:** it declares
     `depends_on: [prometheus-crd-ownership]` *and* `conflicts_with` it, and its
     premise `crd-ownership-fix-is-in-place` asserts
     `.spec.values.crds` contains `"installPrometheus":false`. That premise
     **fails today by design** and flips to PASS the moment this plan executes —
     this plan is its unblocker. Its former premise
     `this-hr-owns-the-prometheus-crds` was removed, so nothing there goes stale
     after step 2. *(The retired `otel-operator-0.21.0` plan named in earlier
     drafts executed as `9a35168f` and no longer exists.)*
  The only BAD order is kps-91.4.1 → any otel bump → this plan: the four would
  sit at 0.92.0 until the next kps chart bump with no writer to fix them (and it
  is the one case where §5.1's rollback confirmation changes shape). Both
  siblings declare `conflicts_with: prometheus-crd-ownership`, so none of the
  three can share a window; the order above is the recommendation for
  consecutive windows.
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
- **Same-HR edits — do NOT combine them.** This plan and `otel-operator-0.23.0`
  edit the same HelmRelease file, and an earlier draft of this bullet offered to
  let the §3.2 values block ride along with the chart bump. **That option is
  withdrawn.** `otel-operator-0.23.0` declares `conflicts_with:
  prometheus-crd-ownership` (so the two must not share a window at all) and
  `depends_on: prometheus-crd-ownership` (so it cannot run first). Combining
  them would also destroy §4.2's control structure: the cert Secret would move
  because of the chart bump rather than because of this values change, and a
  0.21.0 → 0.23.0 bump is `risk: high` — a failure would be attributed to the
  wrong cause. One key, one revision, on its own.
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
