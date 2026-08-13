---
plan_id: metrics-server-v0.9.0
component: metrics-server
pr: null                            # no Renovate PR — Trivy-driven CVE remediation.
                                    # Renovate tracks the CHART (3.13.x) and there is no
                                    # newer chart; the HR pins no explicit image.tag today,
                                    # so Renovate has nothing to bump. Applied by hand as a
                                    # values image-tag override (see Summary).
kind: image                         # image-tag override on the existing chart 3.13.1
                                    # (chart version is NOT changed by this plan)
current: "v0.8.1"                   # image (chart 3.13.1, appVersion default v0.8.1)
target: "v0.9.0"                    # image (chart stays 3.13.1)
update_type: minor                  # image 0.8 → 0.9 by semver
risk: low
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/metrics-server
    - deployment/metrics-server                 # single replica, stateless, no PVC
    - apiservice/v1beta1.metrics.k8s.io         # aggregated Metrics API backed by this pod
  shared: [metrics-api]                         # NOT ingress/cert-manager/cni/coredns/DB/longhorn.
                                                # The aggregated metrics.k8s.io API is cluster-wide
                                                # infra: during the ~15-30s single-replica roll,
                                                # `kubectl top`, HPAs, VPAs and dashboards get
                                                # transient errors from metrics.k8s.io. Blast radius
                                                # is real but brief + self-healing. NOTE: 0 HPAs
                                                # exist cluster-wide (verified), so nothing autoscaled
                                                # is perturbed — only `kubectl top` / dashboards.
depends_on: []
conflicts_with: []                  # don't co-schedule with anything that itself relies on
                                    # metrics.k8s.io being continuously up (none pending)
status: awaiting-go                 # thu-early:2026-08-13 unattended run: auto_execute:false ⇒ not fast-tracked; deferred, go/no-go routed via home-operation (issue metrics-server-v0.9.0)
window: "thu-early:2026-08-13"       # CVE remediation batch (no-reboot); window-agent sequences w/ the others
                                    # (risk-weight low=1, fits any no-reboot window trivially;
                                    # CVE-urgency argues for the nearest slot). Window agent assigns.
auto_execute: false                 # low-risk + trivial ⇒ eligible for the unattended fast-track,
                                    # but left false: this pins the image OUT of the chart's
                                    # appVersion (drift), and v0.9.0 changes storage-readiness
                                    # semantics — one operator eyeball on `kubectl top` post-roll
                                    # is cheap. See "auto-updatability" in the Summary.
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-06"
---

# metrics-server image v0.8.1 → v0.9.0 (chart 3.13.1, unchanged)

## 1) Summary & why held

CVE remediation for the cluster's metrics-server (`registry.k8s.io/metrics-server/metrics-server`,
namespace `kube-system`). A fresh Trivy scan (2026-08-06) flags **2 fixable CRITICAL**
CVEs on the running image `v0.8.1`. The fixed image is **v0.9.0** (released 2026-07-13):

> upstream release notes v0.9.0: *"CVE-2025-47907 and CVE-2025-47906"* fixed *"via Go v1.26.4"*;
> also *"golang.org/x/crypto"* bumped 0.39.0 → 0.45.0, and *"Bump Kubernetes dependencies to v1.36.2"*.

These are Go-toolchain/stdlib CVEs baked into the v0.8.1 build; the v0.9.0 image is
rebuilt on Go 1.26.4 and clears them. This matches the Trivy finding (2 fixable CRITICALs).

**Why this was held / can't auto-merge — the crux.** There is **no helm chart release that
ships v0.9.0 yet.** The newest published chart is **3.13.1** (2026-06-11), and it still pins
`appVersion: v0.8.1` (verified against the upstream helm index and the GitHub releases page).
So:
- **Renovate has no PR to open** — it tracks the chart version (3.13.x, already current) and
  our HelmRelease currently pins **no explicit `image.tag`** (it inherits the chart default
  `v{{ .Chart.AppVersion }}` = v0.8.1). There is nothing for the version-bump path to bump.
- The only way to get v0.9.0 today is a **values image-tag override**: pin
  `values.image.tag: v0.9.0` on the still-3.13.1 chart. Chart 3.13.1's `values.yaml` supports
  this (`image.tag` defaults to `""` → `v{{ .Chart.AppVersion }}`; the deployment renders
  `image: {{ include "metrics-server.image" . }}` which honors the override). Verified by
  unpacking `metrics-server-3.13.1.tgz`.
- Pinning an image **ahead of / outside** the chart's own appVersion is exactly the
  "image ↔ chart drift" the auto-updater refuses to do unattended, so it's correctly held to
  a window.

**Risk is genuinely low.** Blast radius is one stateless pod in `kube-system` behind the
aggregated `v1beta1.metrics.k8s.io` APIService. The only consumers are `kubectl top`,
HPAs/VPAs, and dashboards (Headlamp/Grafana). **Verified: zero HPAs exist cluster-wide**
(`kubectl get hpa -A` → none), so nothing autoscaled depends on it. The single-replica roll
causes ~15-30s of `metrics.k8s.io` unavailability, then self-heals. No PVC, no DB, no
shared ingress/cert-manager/cni/coredns touched.

**One real behavioral watch-item** (not a blocker): v0.9.0 *"Require both node and pod
metrics for storage readiness."* → the new pod may report NotReady a little longer at
startup until it has scraped BOTH node and pod metrics for the first time. Verification waits
for `/readyz` + APIService Available before declaring success (don't panic on a slightly
longer first-ready).

**Compatibility:** v0.9.0 bumps k8s client deps to v1.36.2; our cluster is v1.36.0 (Talos
v1.13.7) — well within range, no min-version concern. No changed/removed flags: the existing
`args` (`--kubelet-insecure-tls`, `--kubelet-preferred-address-types`,
`--kubelet-use-node-status-port`, `--metric-resolution=10s`, `--kubelet-request-timeout=2s`)
are all still valid in v0.9.0.

**Auto-updatability verdict:** it CANNOT flow through the normal auto-updater today (no chart
release carries v0.9.0 → no Renovate PR; and the fix is a manual image-out-of-chart pin, not a
chart/image PR merge). It is low-risk enough to be a fast-track candidate, but the chart-drift
+ readiness-semantics change justify keeping it operator go/no-go (`auto_execute: false`). It
does not need a *long* window — a short no-reboot slot (or a fast-tracked low-risk run) is
plenty.

## 2) Pre-checks

```bash
export KUBECONFIG=/Users/mu/code/cberg-home-nextgen/kubeconfig

# a) current state: HR Ready on chart 3.13.1, one pod Ready on v0.8.1, 0 restarts
kubectl get hr -n kube-system metrics-server \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} chart={.status.history[0].chartVersion}{"\n"}'   # True chart=3.13.1
kubectl get deploy -n kube-system metrics-server \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'                                                   # ...metrics-server:v0.8.1
kubectl get pods -n kube-system -l app.kubernetes.io/name=metrics-server -o wide                                 # 1/1 Running, 0 restarts

# b) the aggregated Metrics API is currently healthy (this is what briefly drops on the roll)
kubectl get apiservice v1beta1.metrics.k8s.io \
  -o jsonpath='{.status.conditions[?(@.type=="Available")].status}{"\n"}'                                        # True
kubectl top nodes | head -5                                                                                       # returns real numbers NOW (baseline)

# c) confirm nothing autoscaled depends on it (documents the low blast radius)
kubectl get hpa -A                                                                                               # expect: No resources found

# d) verify the target image tag EXISTS in registry.k8s.io (version-attribution rule) — expect 307 (redirect to blob store; same as v0.8.1)
curl -s -o /dev/null -w 'v0.9.0 -> %{http_code}\n' \
  -H "Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json" \
  https://registry.k8s.io/v2/metrics-server/metrics-server/manifests/v0.9.0

# e) no in-flight reconcile
flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps (GitOps, copy-pasteable)

> Single change: ADD an `image.tag` override to the HelmRelease `values`. The chart
> version stays `3.13.1`. Do NOT touch `spec.chart.spec.version`. The existing
> `args`/`resources`/`serviceMonitor` values are unchanged.

1. **(Optional) active-update marker** so the alert-triage-agent treats the ~15-30s
   metrics-API blip (and any `KubeDeployment`/pod not-ready alert) as EXPECTED:
   ```bash
   runbooks/update-marker.sh add metrics-server kube-system 1 "v0.8.1->v0.9.0 CVE image pin"
   ```

2. **Add the image-tag override** in
   `kubernetes/apps/kube-system/metrics-server/app/helmrelease.yaml`. Under
   `spec.values:`, add an `image:` block (sibling of the existing `args:` / `metrics:` /
   `serviceMonitor:` / `resources:` keys):
   ```yaml
     values:
       image:
         # Pin ahead of chart 3.13.1's appVersion (v0.8.1) to clear CVE-2025-47907 /
         # CVE-2025-47906 (fixed in v0.9.0, Go 1.26.4). REMOVE this override once a
         # metrics-server chart ships appVersion >= v0.9.0 (then bump the chart normally).
         tag: v0.9.0
       args:
         - --kubelet-insecure-tls
         # ...(leave the rest of values unchanged)...
   ```
   Confirm exactly one image tag override is present and the chart version is untouched:
   ```bash
   grep -n 'tag: v0.9.0' kubernetes/apps/kube-system/metrics-server/app/helmrelease.yaml   # exactly one hit
   grep -n 'version: 3.13.1' kubernetes/apps/kube-system/metrics-server/app/helmrelease.yaml # still 3.13.1
   ```

3. **Validate render + schema** before pushing:
   ```bash
   task template:configure -- --strict
   kubeconform -summary -fail-on error kubernetes/apps/kube-system/metrics-server
   ```

4. **Commit + push** (work on `main`, stage only this hunk):
   ```bash
   git add -p kubernetes/apps/kube-system/metrics-server/app/helmrelease.yaml
   git commit -m "fix(metrics-server): pin image v0.9.0 to clear CVE-2025-47907/47906 (chart 3.13.1)"
   git push
   ```
   Flux webhook reconciles the HelmRelease; the Deployment rolls the single replica.

5. **On success**, clear the marker:
   ```bash
   runbooks/update-marker.sh clear metrics-server
   ```

## 4) Verification

```bash
export KUBECONFIG=/Users/mu/code/cberg-home-nextgen/kubeconfig

# a) HR reconciled + healthy, pod rolled to v0.9.0, 0 restarts after settle
kubectl get hr -n kube-system metrics-server \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} chart={.status.history[0].chartVersion}{"\n"}'   # True chart=3.13.1
kubectl get deploy -n kube-system metrics-server \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'                                                   # ...metrics-server:v0.9.0
kubectl rollout status deploy/metrics-server -n kube-system --timeout=120s
kubectl get pods -n kube-system -l app.kubernetes.io/name=metrics-server -o wide                                 # 1/1 Running, 0 restarts

# b) THE load-bearing check — the aggregated Metrics API is back and `kubectl top` works
#    (allow up to ~60-90s: v0.9.0 requires BOTH node+pod metrics before storage-ready)
kubectl get apiservice v1beta1.metrics.k8s.io \
  -o jsonpath='{.status.conditions[?(@.type=="Available")].status}{"\n"}'                                        # True
kubectl top nodes                                                                                                # real numbers, no error
kubectl top pods -n kube-system | head -5                                                                        # real numbers, no error

# c) startup log sanity — no flag-parse errors, no scrape auth failures
POD=$(kubectl get pod -n kube-system -l app.kubernetes.io/name=metrics-server -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n kube-system $POD | tail -30   # expect "Serving securely"/scrape lines; no "unknown flag", no persistent scrape errors

# d) no HPAs to break, but confirm none flipped to unknown-metrics (there are none today)
kubectl get hpa -A
```

Success = HR Ready=True on chart 3.13.1, one pod Ready on `:v0.9.0` with 0 restarts after
~2-3 min, `v1beta1.metrics.k8s.io` Available=True, and `kubectl top nodes`/`pods` return real
numbers.

## 5) Rollback

Stateless, no data — instant and safe. Revert the override (restores the chart default v0.8.1):
```bash
export KUBECONFIG=/Users/mu/code/cberg-home-nextgen/kubeconfig
git revert --no-edit <bump-commit-sha>       # removes the image.tag override
git push
flux reconcile helmrelease -n kube-system metrics-server --force
```
Confirm back-to-good:
```bash
kubectl get deploy -n kube-system metrics-server \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'                                # ...:v0.8.1
kubectl get apiservice v1beta1.metrics.k8s.io \
  -o jsonpath='{.status.conditions[?(@.type=="Available")].status}{"\n"}'                      # True
kubectl top nodes | head -3                                                                   # real numbers
```
Then clear the marker (`runbooks/update-marker.sh clear metrics-server`). No DB/PVC restore is
ever needed. (Accepting the CVE for one more cycle is safe if v0.9.0 misbehaves — the criticals
are Go-stdlib in an internal, LAN-only metrics component with no untrusted input path.)

## 6) Interference notes

- **Blast radius: one stateless pod in `kube-system`.** Only the `metrics-server` Deployment
  rolls; ~15-30s of `metrics.k8s.io` unavailability during the single-replica replace, then
  self-heals. No PVC, no DB, no shared ingress/cert-manager/cni/coredns/longhorn perturbed.
- **`shared: [metrics-api]` — the one cross-cutting surface.** The aggregated
  `v1beta1.metrics.k8s.io` API briefly returns errors to ALL callers (`kubectl top`, HPAs,
  VPAs, Headlamp/Grafana panels) while the pod rolls. **Mitigant: 0 HPAs exist cluster-wide**
  (verified), so nothing autoscaled is affected — impact is limited to a transient `kubectl top`
  / dashboard blip. Still, do NOT co-schedule this in the same window as any plan that itself
  churns metrics.k8s.io consumers or that would introduce an HPA mid-window.
- **Chart-vs-image DRIFT is intentional and time-boxed.** After this, the HelmRelease pins
  `image.tag: v0.9.0` while `chart.spec.version` is 3.13.1 (appVersion v0.8.1). When a
  metrics-server chart ships appVersion >= v0.9.0, a Renovate chart PR will appear — at that
  point **remove the `image.tag` override in the same PR** so the pin doesn't freeze an older
  image under a newer chart (see feedback: chart-version bumps don't move the image, and here
  the reverse — a stale image pin can outlive its need). Flag this as a follow-up for the
  version-check/auto-updater path.
- **Not a reboot job** (`needs_reboot: false`), low blast, stateless → fits any short no-reboot
  window (tue/thu/sat-early); suggested `sat-early:2026-08-08` as the soonest slot given the
  CRITICAL-CVE urgency. Operator-present preferred only to eyeball `kubectl top` after the roll,
  not because of scope.
