---
plan_id: envoy-proxy-config-distroless-v1.39.4
component: envoy-proxy-config
also_covers:
  - docker.io/envoyproxy/envoy        # the Envoy DATA-PLANE image pinned in EnvoyProxy/network/envoy-proxy-config
  - envoy-gateway                     # the gateway-helm CHART (HelmRelease network/envoy-gateway) 1.9.2 -> 1.9.3, moved in the SAME
                                      # commit since 2026-10-26 (finding F-c63ead4d). coverage.py reads this list.
supersedes: envoy-proxy-config-distroless-v1.39.3   # chain: -v1.39.2 -> -v1.39.3 -> this plan (both earlier drafts retired/superseded)
refreshed: "2026-10-26"               # MATERIAL CHANGE 2026-10-26: chart gateway-helm 1.9.2 -> 1.9.3 MERGED INTO this plan (see §1
                                      # "Refresh 2026-10-26"). Earlier: RETARGETED 1.39.4 -> 1.39.5 in place on 2026-10-23.
                                      # The plan_id/file name KEEP "-v1.39.4" deliberately: other plans and the 1.40.0 plan
                                      # reference this id in conflicts_with; the TARGET in `target:` is authoritative.
pr: null                              # no Renovate PR: the `distroless-v` prefix is not docker-versionable
                                      # (gatewayclass.yaml comment). Surfaced by version-check-current.md row
                                      # "distroless-v1.39.1 -> distroless-v1.39.4" (now .5); dispatched by sweep cycle ee022565.
kind: image
current: "distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4"
target: "chart gateway-helm 1.9.3 + data plane distroless-v1.39.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0"
update_type: patch
risk: medium                          # low PROBABILITY (same Envoy minor as the compiled default; the 1.39.5
                                      # delta is a CA trust-store fix + dep bumps, no source/ change; the carried
                                      # 1.39.4 delta is seven thread-affinity race fixes) but total IMPACT: this image IS the only HTTP data
                                      # plane; the bump rolls all 6 proxy pods of envoy-internal + envoy-external.
                                      # 2026-10-26: the controller (3 replicas) now rolls in the same change; its restart is
                                      # low risk (data plane keeps serving the last xDS), the proxy roll is unchanged in kind.
est_duration_min: 70                  # was 55. +15: controller roll + helm upgrade ~5, end-state settle (a possible SECOND proxy
                                      # re-render by the new controller) ~6, CRD-identity + policy re-baseline + extra pre-checks ~4.
                                      # With etcd-timeouts-5000-500 (110) this is 180 of the 180 usable min in sun-attended: zero
                                      # slack, hence the conflicts_with entry below and §6.
needs_reboot: false
exclusive: false
touches:
  namespaces: [network]
  resources:
    - envoyproxy/network/envoy-proxy-config                      # spec.provider.kubernetes.envoyDeployment.container.image
    - deployment/network/envoy-internal                          # ROLLS: envoy 1.39.1 -> 1.39.5 AND shutdown-manager gateway:v1.9.2 -> v1.9.3 + new tmp emptyDir (3 pods, surge-first)
    - deployment/network/envoy-external                          # ROLLS: same (3 pods, surge-first)
    - helmrelease/network/envoy-gateway                          # chart gateway-helm 1.9.2 -> 1.9.3 (helm-controller upgrade)
    - deployment/network/envoy-gateway                           # CONTROLLER ROLLS: gateway:v1.9.2 -> v1.9.3 (3 replicas, leader election; lease 5b9825d2.gateway.envoyproxy.io)
    - kustomization/network/envoy-gateway-crds                   # vendored CRD files get a provenance-header-only change; cluster CRD content UNCHANGED (verified 2026-10-26)
    - kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
    - kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml
    - kubernetes/apps/network/envoy-gateway/crds/gateway-api-standard.yaml   # header line 2 only
    - kubernetes/apps/network/envoy-gateway/crds/envoy-gateway.yaml          # header line 2 only
  shared:
    - gateway/envoy                   # envoy-internal (.103) + envoy-external (.104) carry EVERY
                                      # HTTPRoute (95 routes / 80 host-VIP pairs, re-measured 2026-10-13)
    - public-edge                     # envoy-external is the internet-facing data plane
    - authentik                       # 12 SecurityPolicies (extAuth forward-auth) are enforced inside Envoy
    - monitoring                      # §2.7/§4.4 read Prometheus + blackbox probe_success (the instrument)
depends_on: []
  # The controller coupling is a premise (`controller-is-1.9.2`), not a plan dependency:
  # envoy-gateway-1.9.2 executed and was retired in 418faa1e; chart 1.9.2 re-measured live 2026-10-13.
conflicts_with:                       # every id re-checked as an existing, non-terminal plan file 2026-10-23;
  # 2026-10-25: pruned dead refs penpot-chart-1.10.0, external-dns-1.23.0 (executed/retired)
                                      # reasons in §6. DROPPED 2026-10-23 (no such plan file any more):
                                      # jellyfin-12.2.20261005, open-webui-17.0.0, coredns-1.48.2,
                                      # flux-fleet-0.60.0, kube-prometheus-stack-92.2.0.
  - authentik-2026.8.5                # reciprocal: names this plan; Authentik ext-auth path is exercised by §4
  - authentik-web-max-requests        # reciprocal: names this plan; same path
  - n8n-2.39.8                        # reciprocal: names this plan (status executed; kept for the reciprocity check)
  - envoy-proxy-config-distroless-v1.40.0   # SAME pin line (blocked); two plans moving one pin never share a window
  - talos-linux-1.14.2                # node drain competes for the single PDB disruption
  - talos-linux-1.14.4                # same
  - flux-reconciler-impersonation     # exclusive; rewrites how kustomize-controller applies this
  - flux-oci-chart-sources            # moves Flux sources; same §3/§5 apply-and-revert path
  - etcd-timeouts-5000-500            # ADDED 2026-10-26 (both plans hold sun-attended:2026-11-08). It restarts etcd on all 3
                                      # control-plane nodes one at a time (quorum 2/3); the EG controller roll needs the apiserver
                                      # for its leader-election lease and helm-controller's upgrade needs it too. Capacity:
                                      # 110 + 70 = 180 of 180 usable min (200 - 20 Step-0 reserve), zero slack. NEEDS the
                                      # reciprocal entry in etcd-timeouts-5000-500 (not edited here).
capability_change: false              # same-behaviour patch: no new route, permission, API surface or
                                      # exposure; the EnvoyProxy object changes its image string and the chart moves a patch
                                      # (helm template diff 1.9.2 vs 1.9.3 with the live values: version labels, controller image,
                                      # certgen image, an unused ratelimit image string; no RBAC, no CRD content, no new API).
rollback_class: git-revert            # the old image is digest-pinned, still published and cached on all 3 nodes; the old
                                      # controller image gateway:v1.9.2 is still published; no CRD content change (so no
                                      # Gateway-API admission-policy trap), no state, no migration. §5 is ONE git revert.
autonomy_override: human-gated        # shared `gateway` derives HUMAN-GATED via SHARED_INFRA_FLOOR anyway;
                                      # attended window only.
security_ref: F-61035b6e              # the 1.39.5 delta IS security-labelled upstream (release image CA trust-store update, in
                                      # addition to the 1.39.2/1.39.3 chain's items). Detail stays on the DB record.
finding_refs: [F-4a6327dd, F-61035b6e, F-c63ead4d, F-10b4fee2]  # version row for this pin (re-opens with the 1.39.5 title) + the planner-raised plan row
                                      # + F-c63ead4d "envoy-gateway: chart 1.9.2 -> 1.9.3 (patch)" (added 2026-10-26, chart merged in)
                                      # + F-10b4fee2 "envoy-proxy-config 1.39.1 -> 1.40.x" (the MINOR version row; RELATED, not delivered here:
                                      # this plan stays inside the 1.39 minor, the 1.40.0 plan remains blocked. Listed so the row is not read as unplanned).
                                      # F-df39740f (inert compression) is cited in §1/§2.3b but NOT owned here.
review: ready-for-go@2026-10-26   # plan-reviewer 2026-10-26 delta re-review after the chart-1.9.3 merge; 2026-10-23 GO is VOID (home-operation item superseded 2026-10-26) - fresh GO needed once the operator picks the window
                                      # controller roll merged in), so that verdict no longer describes this file. A plan-reviewer
                                      # must re-review; only the sweep writes a new `ready-for-go@` line.
status: vetted                       # re-reviewed 2026-10-26; HUMAN-GATED; window null until the operator picks one of the three section-6 options
                                      # scope is NOT carried over: it must be RE-CONFIRMED after re-review (§1, §6).
window: null                          # OPEN until the operator picks one (§6 lists the options). The 2026-10-23 slot sun-attended:2026-11-08 is
                                      # contradicted by the mutual conflicts_with with etcd-timeouts-5000-500 (vetted, same slot, 180 of 180 min).
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/envoy-gateway-upgrade.md
  - docs/sops/gateway-api-httproute.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-13"
premises:
  - id: controller-is-1.9.2
    why: "This plan moves the chart 1.9.2 -> 1.9.3 AND the data plane in one commit. Any other live chart version means the controller already moved (e.g. 1.9.3 landed on its own, which would have rolled the proxies already) or the plan's pre-state is wrong; re-check §1 before proceeding."
    run: kubectl get helmrelease envoy-gateway -n network -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "1.9.2"
  - id: repo-hr-pin-is-1.9.2
    why: "§3.1's sed on helmrelease.yaml matches only the single `version: 1.9.2` line; if git already holds another chart version the sed matches nothing and §5's restore target is wrong."
    run: grep -c '^      version[:] 1\.9\.2$' kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml
    expect_exact: "1"
  - id: shutdown-manager-on-v1.9.2
    why: "Baseline for the end-state gate: the shutdown-manager sidecar tracks the CONTROLLER tag (gateway:v1.9.2 today) and is the reason a chart-only bump would roll the proxies. If it already shows v1.9.3 the roll has partly happened."
    run: kubectl get deploy envoy-internal -n network -o jsonpath='{.spec.template.spec.containers[?(@.name=="shutdown-manager")].image}'
    expect_exact: "docker.io/envoyproxy/gateway:v1.9.2"
  - id: eg-crd-count-18
    why: "Baseline for the CRD-identity gate (§4.0b): 18 Gateway API + Envoy Gateway CRDs live (2026-10-26). A different count means the CRD set moved before the window."
    run: kubectl get crd -o name | grep -c -e gateway.networking.k8s.io -e gateway.envoyproxy.io
    expect_exact: "18"
  - id: envoy-gateway-hr-ready
    why: "Do not move the data plane under a failing controller; it renders the proxy Deployments."
    run: kubectl get helmrelease envoy-gateway -n network -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: repo-pin-is-1.39.1
    why: "current: claims the 1.39.1 digest pin. If someone already moved it (e.g. an earlier draft of this chain ran), §3.1's sed matches nothing and §5's restore target is wrong."
    run: grep -o 'envoy:distroless-v[^ ]*' kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
    expect_exact: "envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4"
  - id: live-envoyproxy-pin-is-1.39.1
    why: "Git and cluster must agree before the edit, or the roll is not caused by this change."
    run: kubectl get envoyproxy envoy-proxy-config -n network -o jsonpath='{.spec.provider.kubernetes.envoyDeployment.container.image}'
    expect_exact: "docker.io/envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4"
  - id: both-gateways-programmed
    why: "Start from a serving data plane; a pre-existing Programmed=False would be blamed on the bump."
    run: >-
      kubectl get gateway -n network -o jsonpath='{range .items[*]}{.metadata.name}={.status.conditions[?(@.type=="Programmed")].status} {end}'
    expect_matches: '^envoy-external=True envoy-internal=True\s*$'
  - id: six-proxy-pods-ready
    why: "The surge-first roll and PDB minAvailable 2 assume 3/3 per gateway at the start."
    run: >-
      kubectl get deploy envoy-internal envoy-external -n network -o jsonpath='{range .items[*]}{.metadata.name}={.status.readyReplicas} {end}'
    expect_matches: '^envoy-internal=3 envoy-external=3\s*$'
---

# envoy-proxy-config + envoy-gateway: chart 1.9.2 -> 1.9.3 and Envoy data plane distroless-v1.39.1 -> distroless-v1.39.5

## 1. Summary & why held

**MATERIAL CHANGE 2026-10-26: the Envoy Gateway chart `gateway-helm` 1.9.2 -> 1.9.3 is
merged into this plan. The operator GO recorded on 2026-10-23 covered the data-plane pin
ONLY, so it does NOT cover this scope: this plan is `draft` with `review: null` until a
plan-reviewer re-reviews it, and the GO must be RE-CONFIRMED after that review.**
Why merged rather than a second plan (evidence, all measured 2026-10-26):
- EG chart **1.9.3 was published 2026-10-26T09:58Z** (finding `F-c63ead4d`, no Renovate PR)
  and its compiled `DefaultEnvoyProxyImage` is
  `distroless-v1.39.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0`,
  byte-identical to this plan's data-plane target (`api/v1alpha1/shared_types.go` at
  `v1.9.3`). So the pin now moves WITH the chart bump, exactly as the deny rule
  `*envoyproxy/envoy*` requires: **there is no longer any deny-rule departure to decide.**
- Doing them separately costs TWO full proxy rolls: the shutdown-manager sidecar of every
  proxy pod runs `docker.io/envoyproxy/gateway:<controller tag>` (live: `gateway:v1.9.2`
  on all 6 pods), and 1.9.3 also adds a `shutdown-manager-tmp` emptyDir volume + `/tmp`
  mount to the proxy Deployment (upstream `proxy/resource.go`). A chart-only bump
  therefore rolls both gateways anyway (precedent: `dd286b9a`, chart 1.9.1 -> 1.9.2).
- The chart delta is small: `helm template` of `gateway-helm` 1.9.2 vs 1.9.3 with the live
  HelmRelease values differs only in version labels, the controller image, the certgen
  image, and an unused `ratelimit` image string; **RBAC unchanged for our values**. The
  `gateway-crds-helm` 1.9.2 vs 1.9.3 pull differs only in `Chart.yaml`, and
  `revendor.sh 1.9.3` on a scratch copy changed exactly line 2 (provenance header) of each
  vendored file: **CRD content unchanged, Gateway API bundle still v1.6.1**.

**Refresh 2026-10-23: target moved 1.39.4 -> 1.39.5.** Upstream published v1.39.5 at
2026-10-23T00:59Z, 10 days after this plan's 1.39.4 draft. Executing 1.39.4 would put all
6 proxy pods on a patch that is already one release behind, and cost a second full roll.
Same image, same Envoy MINOR, same controller (EG 1.9.2, still the newest 1.9.x), same
procedure; what changed is the digest and the upstream delta (below). [SUPERSEDED
2026-10-26: the 2026-10-23 window choice `sun-attended:2026-11-08` and the deny-rule
departure decision are both withdrawn; see §6 for the open window options.] The chain `-v1.39.2 -> -v1.39.3 -> this plan`
is bookkeeping-complete: the earlier drafts no longer exist or are `superseded`.

**What changes (ONE commit, two functional lines).**
1. `kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml` line 23: chart
   `gateway-helm` `version: 1.9.2` -> `1.9.3` (helm-controller upgrade; the EG controller
   Deployment, 3 replicas, rolls `gateway:v1.9.2` -> `v1.9.3`).
2. `kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml` line 85: the
   `EnvoyProxy/network/envoy-proxy-config` container image, digest-pinned, moves from
   `docker.io/envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c1…` to
   `docker.io/envoyproxy/envoy:distroless-v1.39.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0`
   (now equal to the 1.9.3 compiled default; the existing in-file comment already says the
   pin IS the compiled default and must move with the chart, so no comment edit).
3. `revendor.sh 1.9.3` rewrites the provenance header (line 2) of the two vendored CRD
   files; it is bookkeeping, not a cluster change (content identical).
Both gateways' proxy Deployments (`envoy-internal`, `envoy-external`, 3 pods each) roll:
envoy container 1.39.1 -> 1.39.5, shutdown-manager `gateway:v1.9.2` -> `v1.9.3`, plus the
new `shutdown-manager-tmp` volume. **The proxies may roll TWICE in quick succession**: the
EnvoyProxy CR is applied by the Kustomization immediately, so the still-running 1.9.2
controller re-renders the Deployments with the new envoy image first; the 1.9.3 controller
then re-renders again (new sidecar tag + volume). Deployment rollouts coalesce to the
newest template, so the end state is deterministic, but `rollout status` can go green on an
intermediate generation, which is why §3.4/§4.0 gate on the END STATE instead.

**Why held.** `runbooks/auto-update-policy.yaml` rules `*envoy-gateway*` (the chart,
cluster-critical gateway controller; every EG release compiles in its tested Envoy) and
`*envoyproxy/envoy*` (the data-plane image is coupled to the controller and is the only
HTTP data plane in the cluster). This plan satisfies the coupling: both move in one change.

**EG v1.9.3 upstream evidence (2026-10-26, `release-notes/v1.9.3.yaml` at tag `v1.9.3`,
`compare/v1.9.2...v1.9.3`: 16 commits).** `breaking changes:` is EMPTY. Content:
- security updates: Envoy bumped to v1.39.5 (this plan's data-plane target) and a
  `golang.org/x/net` bump in the controller. Detail stays on `security_ref`
  (`docs/sops/vulnerability-disclosure.md`); no CVE ids in this file.
- bug fixes that do NOT reach our configuration: `api_key_auth` listener churn (we do not
  use that filter); HTTPS/HTTP shared-container-port RouteConfiguration
  (our listeners do not share a port); Cilium ClusterMesh dual-labelled EndpointSlices;
  `HTTPRouteFilter` backendRef index; namespace-watch cache and its Helm RBAC (we set no
  `watch`, rendered RBAC identical); route-status ordering and duplicate `status.parents`.
- bug fix that DOES touch rendering: shutdown-manager `/tmp` emptyDir (above), and the
  shutdown-manager now clears a stale `/tmp/shutdown-ready` on start.
- one status change we must re-baseline: policies with `mergeType` report merge results on
  ONE ancestor per parentRef. Our only user is `BackendTrafficPolicy
  my-software-production/the-ninth-banner-ai-generate` (`StrategicMerge`); its route's
  parentRef carries `sectionName: https`, so upstream's fix (which concerns parentRefs WITHOUT
  a `sectionName`) should not move it. Live baseline today: exactly one ancestor,
  `Gateway/envoy-external/https`, `Accepted=True,Merged=True`. §2.5/§4.2 assert that.

**Compatibility with the live controller: COMPATIBLE (same minor), measured 2026-10-13. [Superseded 2026-10-26 for the pairing question: under chart 1.9.3 the pin IS the controller's own default.]**
- Live: HelmRelease `network/envoy-gateway` chart `1.9.2`, Ready=True; controller image
  `docker.io/envoyproxy/gateway:v1.9.2`; all 6 `envoy` containers run imageID
  `sha256:eb2c01c1…`, admin `server_info` = `b579d07d…/1.39.1/Clean/RELEASE/BoringSSL`, LIVE.
- EG `v1.9.2` and the `release/v1.9` branch head both compile
  `DefaultEnvoyProxyImage = distroless-v1.39.1@sha256:eb2c01c1…`. Newest EG releases are
  still v1.9.2 / v1.8.5 (2026-09-28); there is no v1.9.3, and no EG release (re-checked 2026-10-23) ships 1.39.5.
  So no chart bump exists that would move this pin in lockstep.
  **[FALSE since 2026-10-26: EG v1.9.3 (published 2026-10-26T09:58Z) compiles
  `distroless-v1.39.5@sha256:9d84a586…`; the chart bump DOES move the pin in lockstep and is
  now part of this plan. The two sentences above are kept only as the record of the
  2026-10-23 reasoning.]**
- EG compatibility matrix (`site/content/en/news/releases/matrix.md`, main, last changed
  7ee8b982 2026-09-11): v1.9 <-> **`distroless-v1.39.x`**; "Each Envoy Gateway release
  ships with, and is tested against, a single Envoy Proxy minor version" and "The Envoy
  Proxy column shows the supported minor version. The exact image that a given Envoy
  Gateway patch release ships may be a newer patch within that same minor version."
  Honest reading: 1.39.5 is inside the supported MINOR; upstream has not shipped an EG
  release that pairs v1.9 with 1.39.5 specifically. No xDS/API surface changed in the
  1.39.5 delta (it touches NO `source/` file; see below) nor in 1.39.4 (destructor/thread-affinity fixes).

**Upstream evidence.** Read from the GitHub release body for `v1.39.5` and the
`compare/v1.39.4...v1.39.5` file list (2026-10-23), and `changelogs/1.39.4.yaml` at tag
`v1.39.4`.

*v1.39.5 (2026-10-23; 9 commits, 61 files, ZERO files under `source/`).* Release body
summary: one upstream **security fix** and one behaviour change.
- Security-labelled upstream: CA trust-store update in the release image (and the
  Rust DNS-resolver crates / Envoy Mobile roots, neither in our distroless binary
  path). It is the reason to prefer 1.39.5 over 1.39.4 and gives this plan a security
  driver. Detail stays on `security_ref` (docs/sops/vulnerability-disclosure.md).
- Behaviour change: `contrib/istio` peer-metadata label precedence (6 files under
  `contrib/istio`). Not compiled into the distroless image we run; no Istio.
- Commits: build-image bump, the CA trust-store update, CVE-ignore list for unaffected CVEs,
  the istio fix backport, OpenSSL 3.5.9 bump (build/contrib tooling; the proxy binary is
  BoringSSL), renewed OCSP test certs, changelog summary, release prep.

*v1.39.4 (2026-10-12; carried, unchanged).* Seven `bug_fixes`, no `breaking_changes`:
- `aws`, `composite`, `dynamic_modules`, `filter_chain`: route-level configuration could
  be destroyed on a worker thread when an RDS update replaced the route configuration.
- `local_ratelimit`: the share provider manager owned by a route-level local rate limit
  configuration could be destroyed on a worker thread on an RDS update. It is now handed
  to the main dispatcher.
- `sds`: a generic secret provider shared with worker threads could be destroyed on a
  worker thread.
- `stats`: exported Prometheus native histogram bucket indices one bucket too low
  (protobuf exposition only).
- `compare/v1.39.3...v1.39.4`: 16 commits, 85 files (fixes above, `thrift`/`fips_go`
  build-time bumps, Docker build base digest).
- Cumulative from live 1.39.1: also the 1.39.2 (BoringSSL bump, packaging) and 1.39.3
  (two auth-filter crash fixes, brotli bump) deltas. Which of those apply to the live
  version is recorded on `security_ref` F-61035b6e, not here.

**Which of those code paths we actually run (re-measured 2026-10-23 on the live 1.39.1
pods with the §2.3b parser: 5 of 6 pods read, identical to 2026-10-13 — the sixth
port-forward returned nothing, the `UNREADABLE` guard exists for exactly that):**
- `envoy.filters.http.local_ratelimit`: **ON our path** — 1 HTTP filter + 1 per-route
  config on each of the 3 envoy-external pods (BackendTrafficPolicy
  `my-software-production/the-ninth-banner-ai-generate`, reworked to per-client +
  global buckets on 2026-10-12 in bf045b58). The (carried) 1.39.4 fix is a destruction race on
  exactly that route-level config during RDS updates, i.e. it HARDENS a path we use;
  it is also the one changed path whose rendering §4.1b must prove survives.
- `sds` generic secret: **ON our path** — one `generic_secret` (`jwt-sa-bearer`, the
  proxy's xDS SA-token) on every pod. Fix is destructor-thread only.
- `aws_*`, `composite`, `filter_chain`, `dynamic_modules`, `compressor` and the filters
  behind the 1.39.3 crash fixes: no instances of the affected filters on any pod (detail on
  `security_ref` F-61035b6e; positive control: `ext_authz` 11/11 internal, 1/1 external =
  the 12 SecurityPolicies).
- Native histograms: Prometheus `kube-prometheus-stack` has no `enableFeatures` /
  `scrapeNativeHistograms`; the PodMonitor scrapes text `/stats/prometheus`. The `stats`
  fix does not touch our instrument.

**Registry facts (Docker Hub v2 API, 2026-10-23).**
- `distroless-v1.39.5` = OCI index `sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0`
  (linux/amd64 `sha256:00c38048…`, linux/arm64 `sha256:3a84aef7…`), HTTP 200.
- `distroless-v1.39.4` = `sha256:ccb37e93…` (still published, no longer the target).
- `distroless-v1.39.1` still resolves to `sha256:eb2c01c1…` = the live imageID on all 6
  pods: rollback target published and node-cached. `distroless-v1.40.0` is now 200
  (`sha256:23b72ac1…`, a MINOR move — separate blocked plan, never this one).
- Live state re-measured 2026-10-23: HR `envoy-gateway` 1.9.2 Ready, EnvoyProxy image =
  the 1.39.1 pin, both Gateways Programmed=True, 3/3 + 3/3 proxy pods, all `1.39.1 LIVE`.
- SDS: one `generic_secret` (`jwt-sa-bearer`) on the pod checked (2026-10-23 structural walk).
- Added 2026-10-26: `docker.io/envoyproxy/gateway:v1.9.3` = OCI index
  `sha256:192fc9bdadb6d2462e8cf7bd702ce3dd9648f3310c6038787448a1f509b7cd9f`, HTTP 200
  (controller, shutdown-manager sidecar and certgen image); `gateway:v1.9.2` still
  resolves (`sha256:9d67017c…`), the rollback target. `distroless-v1.39.5` re-resolved to
  `9d84a586…` the same day. Envoy upstream's newest is now v1.40.1 (a MINOR move: the
  separate, still-blocked `envoy-proxy-config-distroless-v1.40.0` plan, whose pinned
  target is therefore itself stale).

**Repo correction: CLOSED 2026-10-26.** The deny rule's reason says this pin moves "only
in the SAME change as the gateway-helm chart bump … never on its own". Under EG 1.9.2 this
plan would have departed from that wording; with chart 1.9.3 merged in it does not, so the
proposed rule reword (and the operator decision about it) is withdrawn. The rule text is
correct as written.

**Latent finding (not planned around, F-df39740f).** `BackendTrafficPolicy
network/envoy-compression` is Accepted=True yet every pod still renders **0**
compressor filters (re-measured 2026-10-13). If that is fixed before this window, the
1.39.3-delta brotli bump (carried in this target) lands on a live path, hence the §2.3b STOP-and-amend.

**Verdict.** Two small same-minor patches in one change. The data plane's only code
touching our request path is a race fix on a filter we use; the controller patch carries
no breaking change, no CRD content change and no RBAC change for our values. It rolls
every HTTP-serving pod (possibly twice) and restarts the controller, so it runs in an
attended window, human-gated. No reboot. Risk stays `medium`: low probability, total impact.

## 2. Pre-checks (read-only, ~20 min)

Run these AFTER Step 0 of the window has settled.

**Shell state does not survive between agent Bash calls.** §2.4 writes every helper
(`envver`, `filtmap`, `routes`, `policies`, `sweep`, `changed`, `q`, `alerts`, `pfprom`,
`pfstop`) to `/tmp/envoy1395-win/fns.sh`. EVERY later block in §2.4–§5 starts with
`. /tmp/envoy1395-win/fns.sh`, which also `cd`s into `/tmp/envoy1395-win`. `q()` and
`alerts()` own their Prometheus port-forward on :19090. Every after-file is checked
with `test -s` before it is read: an unsourced helper writes 0 lines and an unguarded
diff then reports a vacuous PASS (measured 2026-10-05 on the 1.39.2 draft).

2.1 Premises: `.venv/bin/python3 runbooks/plan-premises.py envoy-proxy-config-distroless-v1.39.4`.
Every premise must PASS.

2.2 Flux, workloads and PDBs (all objects verified to exist 2026-10-13):
```bash
flux get kustomizations -n network | grep -E 'envoy-gateway'          # envoy-gateway + envoy-gateway-crds, Ready True
kubectl -n network get deploy envoy-gateway envoy-internal envoy-external   # all 3/3
kubectl -n network get pdb envoy-internal envoy-external                    # ALLOWED DISRUPTIONS 1 each
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o wide    # 3 per gateway, one per node
kubectl -n network get deploy envoy-gateway -o jsonpath='{.spec.replicas} {.status.readyReplicas} {.spec.template.spec.containers[*].image}{"\n"}'   # 3 3 docker.io/envoyproxy/gateway:v1.9.2
kubectl -n network get lease 5b9825d2.gateway.envoyproxy.io -o jsonpath='{.spec.holderIdentity}{"\n"}'   # an envoy-gateway-<hash>-<id>_<uuid> holder (2026-10-26: present)
kubectl -n network get pdb | grep envoy-gateway                               # control-plane PDB minAvailable 2 (chart values) -- a controller roll with <3 ready would stall on it
mkdir -p /tmp/envoy1395-win
kubectl -n network get pods -l app.kubernetes.io/name=k8s-gateway -o jsonpath='{range .items[*]}{.metadata.name} {.status.startTime} {.status.containerStatuses[0].restartCount}{"\n"}{end}' > /tmp/envoy1395-win/kgw.before
test -s /tmp/envoy1395-win/kgw.before && [ "$(wc -l < /tmp/envoy1395-win/kgw.before)" -eq 3 ] && cat /tmp/envoy1395-win/kgw.before
#   k8s-gateway BASELINE (name, startTime, restartCount): must print exactly 3 rows (2026-10-26: all started 2026-10-03, restartCount 0).
#   §4.0b diffs against it. Empty or != 3 rows = STOP (a vacuous baseline would make the "not restarted" check pass).
```

2.3 Upstream target is still what this plan pins (network read, not a premise):
```bash
T=$(curl -fsSL "https://auth.docker.io/token?service=registry.docker.io&scope=repository:envoyproxy/envoy:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in distroless-v1.39.5 distroless-v1.39.1; do echo "$t $(curl -fsSI -H "Authorization: Bearer $T" -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' https://registry-1.docker.io/v2/envoyproxy/envoy/manifests/$t | grep -i docker-content-digest | tr -d '\r')"; done
# must print (measured 2026-10-13):
#   distroless-v1.39.5 docker-content-digest: sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0
#   distroless-v1.39.1 docker-content-digest: sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4
gh release list -R envoyproxy/gateway -L 4          # newest v1.9.x must still be v1.9.3 (v1.8.6 also listed: ignore, other minor)
gh release list -R envoyproxy/envoy -L 4            # newest 1.39.x must still be v1.39.5 (v1.40.x may also be listed: ignore, minor move)
# the controller image (also the shutdown-manager sidecar and the certgen hook image) must be pullable BEFORE the commit:
T=$(curl -fsSL "https://auth.docker.io/token?service=registry.docker.io&scope=repository:envoyproxy/gateway:pull" | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in v1.9.3 v1.9.2; do echo "gateway:$t $(curl -fsSI -H "Authorization: Bearer $T" -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' https://registry-1.docker.io/v2/envoyproxy/gateway/manifests/$t | grep -i -e '^HTTP' -e docker-content-digest | tr -d '\r' | tr '\n' ' ')"; done
# must print (measured 2026-10-26):
#   gateway:v1.9.3 HTTP/2 200  docker-content-digest: sha256:192fc9bdadb6d2462e8cf7bd702ce3dd9648f3310c6038787448a1f509b7cd9f
#   gateway:v1.9.2 HTTP/2 200  docker-content-digest: sha256:9d67017c442a70e6ae9f1a358e6c80eb653c67c2e40823d9a991e0daf37ba926
# and the digest in the first pull-check of this block (distroless-v1.39.5) must STILL equal gateway v1.9.3's compiled default:
gh api 'repos/envoyproxy/gateway/contents/api/v1alpha1/shared_types.go?ref=v1.9.3' -H 'Accept: application/vnd.github.raw' | grep 'DefaultEnvoyProxyImage ='
#   must print ...distroless-v1.39.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0
```
- FAIL shape / STOP: a different digest (tag re-pushed) or an empty line (tag gone or
  registry unreachable); `gateway:v1.9.3` not HTTP 200 (a failed pull would wedge the
  controller roll, the certgen hook and every proxy's sidecar); the `DefaultEnvoyProxyImage`
  line not equal to this plan's pin (the lockstep claim in §1 is then false: re-plan).
  If an EG v1.9.4+ exists, or a v1.39.6, this plan is stale: re-plan rather than ship a
  known-superseded patch.

2.3b **Exposure re-check: which changed code paths are live?** Uses `filtmap` from §2.4
(write §2.4 first, then run this). It parses each pod's `/config_dump` STRUCTURALLY
(listener `http_filters` + route `typed_per_filter_config`), not by substring: a raw
substring count over the full dump hits the compiled-extension list and reported 1–2
"instances" of every filter on 2026-10-13, which is a false exposure reading.
```bash
. /tmp/envoy1395-win/fns.sh
filtmap | sort | tee filt.before
test -s filt.before && [ "$(wc -l < filt.before)" -eq 6 ] && echo FILT_ROWS_OK
grep -c UNREADABLE filt.before                                  # must print 0 (or 1 under the baseline tolerance rule)
# measured 2026-10-13 04:1x (format filter=<http_filters>/<per-route configs>):
#   envoy-external-… ext_authz=1/1  local_ratelimit=1/1 compressor=0/0 router=4   (x3)
#   envoy-internal-… ext_authz=11/11 local_ratelimit=0/0 compressor=0/0 router=4  (x3)
```
- BASELINE TOLERANCE RULE (pre-roll only): the helpers now wait up to 10 s for the
  port-forward. If exactly ONE pod still prints `UNREADABLE`, re-run `filtmap` once; if it
  stays unreadable and the other two pods of its gateway read identically, record it and
  continue (5-of-6 baseline). Two or more `UNREADABLE`, or a whole gateway unreadable,
  is a STOP. After the roll (§4) the requirement is strict: 0 `UNREADABLE`.
- PASS: `FILT_ROWS_OK`, 0 `UNREADABLE` (or the tolerance rule above), `ext_authz` non-zero on all 6 (control: proves the
  parser sees filters), `compressor=0/0` on all 6.
- STOP-and-amend: a non-zero `compressor` means F-df39740f was fixed since 2026-10-13;
  the brotli dependency bump is then on every compressible response and §4 has no
  decode gate. A different `local_ratelimit` count is fine (record it); §4.1b diffs
  against THIS file, not the 2026-10-13 numbers.

2.4 Write the helper file once, then take the baseline Envoy build version on all 6
pods (the input to the §4.1 CONTENTS assertion). Paste exactly as written. `envver`,
`routes`, `policies`, `sweep`, `changed`, `q`, `alerts` are the 1.39.2-draft helpers
dry-run 2026-10-05 under zsh and bash (`changed()` rc 0/1/2/2/2 on identical /
one-row-000 / empty / short / key-mismatch); `filtmap` is new and was dry-run
2026-10-13 under zsh 5.9 and bash against all 6 live pods (output above).
```bash
mkdir -p /tmp/envoy1395-win
cat > /tmp/envoy1395-win/fns.sh <<'FNS'
# envoy1395 window helpers. SOURCE at the top of EVERY later block:  . /tmp/envoy1395-win/fns.sh
W="${W:-/tmp/envoy1395-win}"; cd "$W" || return 1
envver() { i=0; for p in $(kubectl -n network get pods -l app.kubernetes.io/component=proxy -o name); do
  port=$((19100+i)); i=$((i+1))
  kubectl -n network port-forward "$p" "$port":19000 >/dev/null 2>&1 & pf=$!; for _ in 1 2 3 4 5 6 7 8 9 10; do curl -s --max-time 2 -o /dev/null "http://localhost:$port/ready" && break; sleep 1; done
  v=$(curl -s --max-time 5 "http://localhost:$port/server_info" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['version'].split('/')[1], d['state'])" 2>/dev/null)
  kill $pf 2>/dev/null; echo "${p#pod/} ${v:-UNREADABLE}"; done; }
filtmap() { i=0; for p in $(kubectl -n network get pods -l app.kubernetes.io/component=proxy -o name); do
  port=$((19120+i)); i=$((i+1))
  kubectl -n network port-forward "$p" "$port":19000 >/dev/null 2>&1 & pf=$!; for _ in 1 2 3 4 5 6 7 8 9 10; do curl -s --max-time 2 -o /dev/null "http://localhost:$port/ready" && break; sleep 1; done
  curl -s --max-time 20 "http://localhost:$port/config_dump" > "$W/.cd" 2>/dev/null
  kill $pf 2>/dev/null; wait $pf 2>/dev/null
  python3 - "${p#pod/}" "$W/.cd" <<'PY'
import sys,json
from collections import Counter
pod,f=sys.argv[1],sys.argv[2]
try: d=json.load(open(f))
except Exception: print(pod,"UNREADABLE"); sys.exit(0)
hf=Counter(); pr=Counter()
def walk(o):
    if isinstance(o,dict):
        for x in o.get("http_filters",[]) or []: hf[x.get("name","").split("/")[0]]+=1
        for k in (o.get("typed_per_filter_config") or {}): pr[k.split("/")[0]]+=1
        for v in o.values(): walk(v)
    elif isinstance(o,list):
        for v in o: walk(v)
for c in d.get("configs",[]):
    if c.get("@type","").split(".")[-1] in ("ListenersConfigDump","RoutesConfigDump"): walk(c)
n=lambda k:"%d/%d"%(hf["envoy.filters.http."+k],pr["envoy.filters.http."+k])
print(pod,"ext_authz="+n("ext_authz"),"local_ratelimit="+n("local_ratelimit"),"compressor="+n("compressor"),"router="+str(hf["envoy.filters.http.router"]))
PY
done; }
routes() { kubectl get httproute -A -o json | python3 -c '
import sys,json;from collections import Counter;c=Counter()
for r in json.load(sys.stdin)["items"]:
  for p in r.get("status",{}).get("parents",[]):
    s={x["type"]:x["status"] for x in p.get("conditions",[])}
    c[(p["parentRef"]["name"],"Accepted="+s.get("Accepted","?"),"ResolvedRefs="+s.get("ResolvedRefs","?"))]+=1
for k,v in sorted(c.items()): print(k,v)'; }
policies() { kubectl get securitypolicy,clienttrafficpolicy,backendtrafficpolicy,backend -A -o json | python3 -c '
import sys,json;from collections import Counter;c=Counter()
for o in json.load(sys.stdin)["items"]:
  st=o.get("status",{}); a=st.get("ancestors") or []
  v=[x["status"] for y in a for x in y.get("conditions",[]) if x["type"]=="Accepted"] or [x["status"] for x in st.get("conditions",[]) if x["type"]=="Accepted"]
  c[(o["kind"],tuple(sorted(set(v))))]+=1
print(sorted(c.items()))'; }
sweep() { test -s "$W/hosts.txt" || { echo "GUARD: $W/hosts.txt missing or empty" >&2; return 2; }
  while read -r h v; do printf '%s %s %s\n' "$v" "$(curl -sk -o /dev/null -w '%{http_code}' --max-time 8 --resolve "$h:443:$v" "https://$h/" </dev/null)" "$h"; done < "$W/hosts.txt"; }
# changed BEFORE AFTER -- rows "<vip> <code> <host>", joined on key host|vip.
# rc 0 = no change, rc 1 = CHANGED lines printed, rc 2 = GUARD (empty input / row-count / join mismatch)
changed() { b=$1; a=$2
  test -s "$b" && test -s "$a" || { echo "GUARD: empty input ($b / $a)"; return 2; }
  nb=$(wc -l < "$b" | tr -d ' '); na=$(wc -l < "$a" | tr -d ' ')
  [ "$nb" = "$na" ] || { echo "GUARD: row count $nb (before) != $na (after)"; return 2; }
  awk '{print $3"|"$1, $2}' "$b" | sort > "$W/.kb"; awk '{print $3"|"$1, $2}' "$a" | sort > "$W/.ka"
  nj=$(join "$W/.kb" "$W/.ka" | wc -l | tr -d ' ')
  [ "$nj" = "$nb" ] || { echo "GUARD: join matched $nj of $nb rows"; return 2; }
  join "$W/.kb" "$W/.ka" | awk '$2!=$3 {print "CHANGED", $1, $2, "->", $3; n++} END {print "CHECKED " NR " rows, CHANGED " n+0; exit (n>0)}'; }
pfprom() { curl -sf --max-time 3 http://localhost:19090/-/ready >/dev/null 2>&1 && return 0
  kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & echo $! > "$W/pf.pid"
  for _ in 1 2 3 4 5 6 7 8 9 10; do sleep 1; curl -sf --max-time 3 http://localhost:19090/-/ready >/dev/null 2>&1 && return 0; done
  echo "GUARD: prometheus port-forward not ready" >&2; return 2; }
pfstop() { [ -f "$W/pf.pid" ] && kill "$(cat "$W/pf.pid")" 2>/dev/null; rm -f "$W/pf.pid"; }
q() { pfprom || { echo PF_FAILED; return 2; }
  curl -s --get http://localhost:19090/api/v1/query --data-urlencode "query=$1" | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"];print(r[0]["value"][1] if r else "EMPTY")' 2>/dev/null || echo QUERY_FAILED; }
alerts() { pfprom || { echo PF_FAILED; return 2; }
  n=$(curl -s http://localhost:19090/api/v1/rules | python3 -c 'import sys,json;print(sum(1 for g in json.load(sys.stdin)["data"]["groups"] for r in g["rules"] if r.get("type")=="alerting" and r["name"].startswith(("EnvoyGateway","IngressProbe"))))' 2>/dev/null)
  echo "RULES=${n:-QUERY_FAILED}$([ "$n" = 6 ] || echo ' RULES_NOT_6_INSTRUMENT_BLIND')"
  curl -s http://localhost:19090/api/v1/alerts | python3 -c 'import sys,json;print(sorted({a["labels"]["alertname"] for a in json.load(sys.stdin)["data"]["alerts"] if a["state"]=="firing" and a["labels"]["alertname"].startswith(("EnvoyGateway","IngressProbe"))}))'; }
endstate() { ev="$1"; gt="$2"; { kubectl -n network get pods -l app.kubernetes.io/component=proxy -o json; echo '@@@'; kubectl -n network get deploy envoy-internal envoy-external envoy-gateway -o json; echo '@@@'; kubectl -n network get lease 5b9825d2.gateway.envoyproxy.io -o jsonpath='{.spec.holderIdentity}'; echo '@@@'; kubectl -n network get pods -l app.kubernetes.io/name=gateway-helm -o jsonpath='{.items[*].metadata.name}'; } | python3 -c '
import sys,json
ev,gt=sys.argv[1],sys.argv[2]
a,b,c,ctl=sys.stdin.read().split("@@@")
try: pods=json.loads(a)["items"]; deps=json.loads(b)["items"]
except Exception: print("END_STATE_FAIL: kubectl output unreadable"); sys.exit(1)
bad=[]
env=[p for p in pods]
if len(env)!=6: bad.append("proxy pod count %d != 6 (a terminating or surplus pod is still present)"%len(env))
for p in env:
    n=p["metadata"]["name"]; cs={x["name"]:x for x in p["status"].get("containerStatuses",[])}; sp={x["name"]:x for x in p["spec"]["containers"]}
    if "distroless-v"+ev+"@sha256:" not in sp["envoy"]["image"]: bad.append("%s envoy spec image %s"%(n,sp["envoy"]["image"]))
    if not sp["shutdown-manager"]["image"].endswith("/gateway:"+gt): bad.append("%s shutdown-manager image %s"%(n,sp["shutdown-manager"]["image"]))
    if not all(x.get("ready") for x in cs.values()) or len(cs)!=2: bad.append("%s containers not all ready"%n)
for d in deps:
    n=d["metadata"]["name"]; s=d["status"]; sp=d["spec"]
    if s.get("observedGeneration")!=d["metadata"]["generation"]: bad.append("%s observedGeneration != generation (old generation still being reconciled)"%n)
    if not (s.get("replicas")==s.get("updatedReplicas")==s.get("readyReplicas")==sp["replicas"]==3) or s.get("unavailableReplicas"): bad.append("%s replicas not settled 3/3/3: %s"%(n,{k:s.get(k) for k in ("replicas","updatedReplicas","readyReplicas","unavailableReplicas")}))
    if n=="envoy-gateway":
        img=[x["image"] for x in sp["template"]["spec"]["containers"]]
        if not all(i.endswith("/gateway:"+gt) for i in img): bad.append("controller image %s"%img)
holder=c.strip()
cp=ctl.split()
if len(cp)!=3: bad.append("controller pod count %d != 3: %r"%(len(cp),cp))
if holder.split("_")[0] not in cp: bad.append("lease holder %r is not one of the current controller pods %r (stale lease from a terminated pod, or no leader)"%(holder,cp))
print("END_STATE_OK envoy=%s gateway=%s holder=%s"%(ev,gt,holder) if not bad else "END_STATE_FAIL:\n  "+"\n  ".join(bad))
sys.exit(1 if bad else 0)' "$ev" "$gt"; }
crdfp() { kubectl get crd -o json | python3 -c '
import sys,json
for o in json.load(sys.stdin)["items"]:
    n=o["metadata"]["name"]
    if n.endswith(".gateway.networking.k8s.io") or n.endswith(".gateway.envoyproxy.io"):
        print(n, o["metadata"].get("annotations",{}).get("gateway.networking.k8s.io/bundle-version","-"), "gen="+str(o["metadata"]["generation"]))'; }
btpninth() { kubectl get backendtrafficpolicy the-ninth-banner-ai-generate -n my-software-production -o json | python3 -c '
import sys,json
try: o=json.load(sys.stdin)
except Exception: print("BTP_FAIL: unreadable"); sys.exit(1)
a=o.get("status",{}).get("ancestors",[])
rows=sorted("%s/%s/%s %s"%(x["ancestorRef"].get("kind"),x["ancestorRef"].get("name"),x["ancestorRef"].get("sectionName"),",".join(sorted("%s=%s"%(c["type"],c["status"]) for c in x["conditions"]))) for x in a)
for r in rows: print(r)
ok = rows==["Gateway/envoy-external/https Accepted=True,Merged=True"]
print("BTP_NINTH_OK" if ok else "BTP_NINTH_CHANGED: expected exactly one ancestor Gateway/envoy-external/https Accepted=True,Merged=True")
sys.exit(0 if ok else 1)'; }
FNS
echo "FNS_WRITTEN $(grep -c '() {' /tmp/envoy1395-win/fns.sh) functions"     # must print 13
. /tmp/envoy1395-win/fns.sh
envver | tee ver.before
test -s ver.before && grep -c ' 1\.39\.1 LIVE$' ver.before    # must print 6 (2026-10-13 live: 6)
crdfp | tee crd.before; wc -l < crd.before                  # must print 18 (the CRD-identity baseline for §4.0b)
endstate 1.39.1 v1.9.2; echo "rc=$?"                        # PRE-state must print END_STATE_OK ... rc=0 (control: the same call with 1.39.5 v1.9.3 prints END_STATE_FAIL)
btpninth | tee btp.before                                   # must end BTP_NINTH_OK (one ancestor Gateway/envoy-external/https Accepted=True,Merged=True)
```
Then run §2.3b. The `endstate 1.39.5 v1.9.3` NEGATIVE CONTROL (must print `END_STATE_FAIL` and rc=1
on this pre-state) proves the §4.0 gate can fail:
```bash
. /tmp/envoy1395-win/fns.sh
endstate 1.39.5 v1.9.3 > ctl.out; echo "control rc=$?"; head -3 ctl.out   # control rc=1 and END_STATE_FAIL ... (this is the pre-state)
```

2.5 Baseline route and policy acceptance (§4.2 diffs against them):
```bash
. /tmp/envoy1395-win/fns.sh
routes > routes.before; policies > policies.before
test -s routes.before && test -s policies.before && cat routes.before policies.before   # empty = STOP
btpninth                                                                                 # BTP_NINTH_OK (re-baseline for §4.2: the controller patch changes how mergeType policies report ancestors)
```
Any non-True line already in the baseline must be noted and not blamed on this change.

2.6 **Behavioural baseline of BOTH gateways.** Per-hostname HTTP status through each VIP.
Hostnames are pulled live into /tmp only and never committed. Row key is host+VIP.
Re-measured 2026-10-13: 95 HTTPRoutes, 80 pairs (54 on .103, 26 on .104).
```bash
. /tmp/envoy1395-win/fns.sh
kubectl get httproute -A -o json | python3 -c '
import sys,json
vip={"envoy-internal":"192.168.55.103","envoy-external":"192.168.55.104"};seen=set()
for r in json.load(sys.stdin)["items"]:
  for p in r["spec"].get("parentRefs",[]):
    if p.get("sectionName")=="http" or p["name"] not in vip: continue
    for h in r["spec"].get("hostnames") or []:
      if (h,vip[p["name"]]) not in seen: seen.add((h,vip[p["name"]])); print(h,vip[p["name"]])' > hosts.txt
test -s hosts.txt && wc -l < hosts.txt                       # ~80; empty = STOP
sweep > status.before
test -s status.before && [ "$(wc -l < status.before)" -eq "$(wc -l < hosts.txt)" ] && echo BASELINE_ROWS_OK
awk '{print $1,$2}' status.before | sort | uniq -c
awk '{print $2}' hosts.txt | sort | uniq -c        # BOTH 192.168.55.103 and 192.168.55.104 must appear
# negative control -- proves the sweep can SEE a missing route (Envoy answers 404 for an unrouted host):
for v in 192.168.55.103 192.168.55.104; do curl -sk -o /dev/null -w "$v %{http_code}\n" --max-time 8 --resolve "nohost-negative-control.invalid:443:$v" https://nohost-negative-control.invalid/; done   # must print 404 twice
```
Pre-existing `404`/`405`/`503` rows (unrouted `/`, backend down) are expected; §4.3
judges only rows that CHANGE.

2.7 Prometheus and alert baseline:
```bash
. /tmp/envoy1395-win/fns.sh
q 'count(up{namespace="network",job="network/envoy-gateway"}==1)'          # 6   (2026-10-13: 6)
q 'sum(envoy_listener_manager_lds_update_rejected{namespace="network"})'   # 0   (2026-10-13: 0, over 6 series)
q 'sum(envoy_cluster_manager_cds_update_rejected{namespace="network"})'    # 0   (2026-10-13: 0)
q 'sum(rate(envoy_http_downstream_rq_xx{namespace="network",envoy_response_code_class="2"}[5m]))'  # >0 (2026-10-13: ~1.05)
q 'min(probe_success{probe_class=~"http|dns"})'                            # 1   (2026-10-13: 1, over 5 probes)
alerts                                                                     # must print exactly two lines: RULES=6 and [] (2026-10-26: RULES=6, [])
pfstop
```
`alerts` filters to `EnvoyGateway*`/`IngressProbe*` on purpose, and first asserts that 6 such alerting
rules are LOADED (`IngressProbeFailing`, `EnvoyGatewayPodNotReady`, `EnvoyGatewayPodCrashLooping`,
`EnvoyGatewayPodRestarted`, `EnvoyGateway5xxSustained`, `EnvoyGatewayMetricsAbsent`; measured via
`/api/v1/rules` 2026-10-26, all `inactive`), so an unloaded rule group cannot read as "nothing firing". On 2026-10-13 unrelated
`TargetDown`, `AragScrape*` and `MaintenanceWindow*` alerts were firing; record them, do
not STOP on them, and do not blame them on this change. `PF_FAILED`, `QUERY_FAILED` or
`EMPTY` from any `q` line is a STOP, never a pass.

**STOP** if any of these fails:
- a premise fails;
- §2.3 shows a different digest, `gateway:v1.9.3` not HTTP 200, a compiled default other than this plan's pin, an EG v1.9.4+, or an Envoy v1.39.6+;
- `endstate 1.39.1 v1.9.2` is not `END_STATE_OK`, `crd.before` is not 18 rows, `btpninth` is not `BTP_NINTH_OK` on the pre-state, or `kgw.before` (§2.2) is empty or not 3 rows;
- a proxy Deployment is below 3/3, or a PDB allows 0 disruptions;
- `ver.before` or `filt.before` has an `UNREADABLE` line that the baseline tolerance rule (§2.3b) does not cover, or `FILT_ROWS_OK` is missing;
- §2.3b shows a non-zero `compressor`;
- the negative control does not print 404 twice;
- an `EnvoyGateway*` or `IngressProbe*` alert is firing;
- any `test -s` guard prints nothing, or `BASELINE_ROWS_OK` is missing;
- any `q` prints `PF_FAILED`, `QUERY_FAILED` or `EMPTY`.

## 3. Steps (GitOps)

3.1 Edit the chart pin and the data-plane pin, then re-vendor the CRDs. Both seds were
dry-tested 2026-10-26 on scratch copies of the two files on macOS (BSD sed); each changed
exactly one line, verbatim diffs:
```
helmrelease.yaml  23c23
<       version: 1.9.2
>       version: 1.9.3
gatewayclass.yaml  85c85
<           image: docker.io/envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4
>           image: docker.io/envoyproxy/envoy:distroless-v1.39.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0
```
`revendor.sh 1.9.3` was dry-run 2026-10-26 on a scratch copy of the `crds/` directory: both
vendored files differ from the committed ones in line 2 ONLY
(`# Source: oci://docker.io/envoyproxy/gateway-crds-helm:1.9.2` -> `:1.9.3`).
```bash
cd /Users/mu/code/cberg-home-nextgen
H=kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml
F=kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
sed -i '' 's/^\([[:space:]]*version: \)1\.9\.2$/\11.9.3/' "$H"
sed -i '' 's|envoyproxy/envoy:distroless-v1\.39\.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4$|envoyproxy/envoy:distroless-v1.39.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0|' "$F"
mise exec -- bash kubernetes/apps/network/envoy-gateway/crds/revendor.sh 1.9.3
#   MUST print, for BOTH files:  "content UNCHANGED (header-only diff)"  and  "bundle-version(s) now vendored: bundle-version: v1.6.1"
#   "content CHANGED -- review before proceeding" or a bundle-version other than v1.6.1 = STOP, do not commit (the CRD-free rollback in §5 no longer holds).
git diff --stat -- "$H" "$F" kubernetes/apps/network/envoy-gateway/crds/
#   exactly 4 files, each "1 insertion(+), 1 deletion(-)"
grep -c 'version: 1\.9\.3$' "$H"                                                                      # 1
grep -c 'distroless-v1.39.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0' "$F"   # 1
.venv/bin/python3 -c "import yaml;list(yaml.safe_load_all(open('$H')));d=list(yaml.safe_load_all(open('$F')));print('YAML_OK',d[1]['spec']['provider']['kubernetes']['envoyDeployment']['container']['image'])"
#   (bare python3 may lack PyYAML)
```
Do NOT add the old "moved AHEAD of the compiled default" annotation: the pin is now the
compiled default, and the existing in-file comment (pin IS the compiled default; moves with
the chart) is already accurate.

3.2 Commit with `--only` (shared worktree), verify, then push. Land the §6 plan-file
bookkeeping (reciprocal refs, plan retirement) in a SEPARATE commit, never inside this one.
```bash
cat > /tmp/envoy1395-msg.txt <<'EOF2'
feat(envoy-gateway): chart 1.9.2 -> 1.9.3 + data plane distroless-v1.39.1 -> v1.39.5

One change because they are coupled: EG v1.9.3 compiles
DefaultEnvoyProxyImage = distroless-v1.39.5@sha256:9d84a586... (the new pin), and a
chart-only bump would roll the proxies anyway (shutdown-manager sidecar tag + new /tmp
emptyDir). CRD content unchanged (header-only re-vendor, bundle v1.6.1); RBAC unchanged
for our values. Rolls the controller (3) and envoy-internal/-external (3+3, surge-first).
Plan: runbooks/maintenance/plans/envoy-proxy-config-distroless-v1.39.4.md (security_ref F-61035b6e)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF2
git commit --only kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml kubernetes/apps/network/envoy-gateway/crds/gateway-api-standard.yaml kubernetes/apps/network/envoy-gateway/crds/envoy-gateway.yaml -F /tmp/envoy1395-msg.txt
git log -1 --format=%s    # must be "feat(envoy-gateway): chart 1.9.2 -> 1.9.3 + data plane distroless-v1.39.1 -> v1.39.5"; amend if not
git show --stat HEAD      # exactly those 4 files
git push
```

3.3 Reconcile. Unlike the data-plane-only version of this plan, the HelmRelease now moves,
so reconcile the CRD Kustomization first (content-identical, a no-op), then the app
Kustomization (applies the EnvoyProxy CR and the HelmRelease spec), then the HelmRelease:
```bash
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization envoy-gateway-crds -n network
flux reconcile kustomization envoy-gateway -n network
flux reconcile helmrelease envoy-gateway -n network
kubectl -n network get envoyproxy envoy-proxy-config -o jsonpath='{.spec.provider.kubernetes.envoyDeployment.container.image}{"\n"}'   # ...distroless-v1.39.5@sha256:9d84a586...
kubectl get helmrelease envoy-gateway -n network -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'   # True 1.9.3 (history[0] is the latest release)
```
If the HelmRelease reports a failed upgrade, helm-controller's remediation (`retries: 3`,
`cleanupOnFail`) rolls the chart back by itself: do not fight it, go to §5.

3.4 Wait for the END STATE (not for `rollout status`). Poll `endstate` every 30 s for up to
15 minutes (the controller roll ~3 min, then one or two proxy rolls ~4 min each, the
shutdown-manager drains each old pod up to 360 s):
```bash
. /tmp/envoy1395-win/fns.sh
for i in $(seq 1 30); do endstate 1.39.5 v1.9.3 > endstate.out && break; sleep 30; done; cat endstate.out; echo "polls=$i"
#   PASS: END_STATE_OK envoy=1.39.5 gateway=v1.9.3 holder=envoy-gateway-<hash>-<id>_<uuid>
#   NOT SETTLED at 15 min (END_STATE_FAIL): do NOT roll back yet. Read the listed lines, re-run the poll (another 15 min is fine
#   while pods are progressing: a pod Pending/ContainerCreating/terminating on its 360 s drain is progress). Go to §5 only if a pod
#   is STUCK (CrashLoopBackOff, ImagePullBackOff, Pending with no scheduling progress, unready with growing restartCount) or the
#   window budget is exhausted.
```
`rollout status` is deliberately NOT the gate: it can go green on the OLD generation
(`feedback_rollout_status_old_generation`) or on the intermediate generation of a
double render. `endstate` reads, per pod, the SPEC image of both containers and readiness;
per Deployment, `observedGeneration == generation` and `replicas == updated == ready == 3`
with no `unavailableReplicas`; exactly 6 proxy pods (a lingering terminating pod fails it);
the controller image tag on all 3 controller replicas; and a live leader-election lease
holder. (Negative control run in §2.4: the same call on the pre-state prints `END_STATE_FAIL`.)

## 4. Verification

4.0 **CONTENTS ASSERTION: the END STATE, both planes, on every pod** — measured by
`endstate 1.39.5 v1.9.3` (spec images + readiness + generation settle + lease holder),
compared to the pre-state `endstate 1.39.1 v1.9.2` = `END_STATE_OK` from §2.4. Re-run it
once the §3.4 poll has passed, and once more at the end of the soak (§4.5):
```bash
. /tmp/envoy1395-win/fns.sh
endstate 1.39.5 v1.9.3; echo "rc=$?"          # END_STATE_OK envoy=1.39.5 gateway=v1.9.3 holder=...   rc=0
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o jsonpath='{range .items[*]}{.metadata.name}{" "}{range .spec.containers[*]}{.name}={.image}{" "}{end}{"\n"}{end}' | sed -E 's/^[^ ]+ //' | sort | uniq -c
#   exactly ONE line: 6 envoy=docker.io/envoyproxy/envoy:distroless-v1.39.5@sha256:9d84a586... shutdown-manager=docker.io/envoyproxy/gateway:v1.9.3
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o jsonpath='{range .items[*]}{.spec.volumes[*].name}{"\n"}{end}' | sort | uniq -c
#   exactly ONE line: 6 x "sa-token certs sds shutdown-manager-tmp" (the new emptyDir 1.9.3 renders)
kubectl -n network get pods -l app.kubernetes.io/name=gateway-helm -o wide      # 3 controller pods Running, one per node, RESTARTS 0 (the pod that was at 1 restart rolls away)
kubectl -n network get gateway                                                  # both PROGRAMMED True
```
- PASS: `END_STATE_OK` rc=0; one unique container-image line over all 6 proxy pods; one
  unique volume line; 3 controller pods on 3 nodes; both Gateways Programmed.
- FAIL shapes: `END_STATE_FAIL` listing a pod still on `1.39.1` or `gateway:v1.9.2` (the
  roll stopped at the intermediate render); `observedGeneration != generation`; 7+ proxy pods
  (an old ReplicaSet is not scaled down); `no controller lease holder` (leader election did
  not settle: check the controller pods' logs and the apiserver); a mix of two image lines
  (a pod from each render). The gate can fail: on the pre-state it prints `END_STATE_FAIL`
  (§2.4 negative control, measured 2026-10-26).

4.0b **CONTENTS ASSERTION: the CRD set is IDENTICAL and k8s-gateway was not touched** (the
properties that keep §5 a plain `git revert` and the k8s-gateway restart-twice DNS gate
unnecessary). CRDs measured by `crdfp` (name, `bundle-version` annotation,
`metadata.generation` of all 18 Gateway API + Envoy Gateway CRDs) against `crd.before`;
k8s-gateway measured by pod name + startTime + restartCount against `kgw.before` (§2.2):
```bash
. /tmp/envoy1395-win/fns.sh
crdfp > crd.after
test -s crd.before && test -s crd.after && [ "$(wc -l < crd.before)" -eq 18 ] && [ "$(wc -l < crd.after)" -eq 18 ] && diff crd.before crd.after && echo CRD_SET_IDENTICAL
#   PASS: CRD_SET_IDENTICAL. Any diff line (a generation bump or a bundle-version change) = the CRD
#   CONTENT moved after all: STOP, do not proceed to the soak, and apply docs/sops/envoy-gateway-upgrade.md
#   (k8s-gateway restart gate TWICE, Gateway-API admission-policy rollback caveat) before anything else.
# negative control -- the comparator must be able to FAIL: a forced generation change must print a diff line
sed '1s/gen=[0-9]*/gen=99/' crd.after > crd.bad; diff crd.before crd.bad            # must print "1c1" and the two rows (diff rc 1)
kubectl -n network get pods -l app.kubernetes.io/name=k8s-gateway -o jsonpath='{range .items[*]}{.metadata.name} {.status.startTime} {.status.containerStatuses[0].restartCount}{"\n"}{end}' > kgw.after
test -s kgw.before && test -s kgw.after && [ "$(wc -l < kgw.before)" -eq 3 ] && [ "$(wc -l < kgw.after)" -eq 3 ] && diff kgw.before kgw.after && echo K8S_GATEWAY_UNTOUCHED
#   PASS: K8S_GATEWAY_UNTOUCHED (same 3 pod names, same startTimes, restartCount unchanged). A new pod name, a
#   newer startTime or a higher restartCount = k8s-gateway restarted during this change: STOP and run the SOP's
#   restart-twice DNS gate (its CRD-coupled failure only bites on a pod START with the new CRDs present).
sed '1s/ [0-9]*$/ 9/' kgw.after > kgw.bad; diff kgw.before kgw.bad                  # control: must print "1c1" and the two rows
# INFORMATIONAL ONLY, NOT a pass criterion (the pods are weeks old and their last 80 lines are a flood of [INFO] DNS
# queries, so this reads 0 even if a startup sync error happened long ago; it only catches a CURRENT error burst):
for p in $(kubectl -n network get pods -l app.kubernetes.io/name=k8s-gateway -o name); do kubectl -n network logs $p --tail=80; done | grep -icE 'could not sync|failed to list'
```
The real k8s-gateway protection is `CRD_SET_IDENTICAL` + `K8S_GATEWAY_UNTOUCHED` here and the
internal-DNS blackbox probe in §4.4 (`probe_success{probe_class="dns"}`, 2 series, 1 on 2026-10-26).
The gates can fail: a changed CRD bumps `metadata.generation` (the 1.9.1 -> 1.9.2 re-vendor
did change `envoyproxies` content, `dd286b9a`), so `diff` prints that line; both controls
above are run on real files and must print their diff.

4.1 **CONTENTS ASSERTION: every proxy pod runs the 1.39.5 binary and is LIVE** —
measured by imageID + admin `server_info`, compared to `ver.before` (6 × `1.39.1 LIVE`).
```bash
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o jsonpath='{range .items[*]}{range .status.containerStatuses[?(@.name=="envoy")]}{.imageID}{"\n"}{end}{end}' | sort | uniq -c
#   expect: 6 x docker.io/envoyproxy/envoy@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0
. /tmp/envoy1395-win/fns.sh
envver | tee ver.after
test -s ver.after || echo 'FAIL: ver.after empty -- instrument did not run'
[ "$(wc -l < ver.after)" -eq 6 ] || echo 'FAIL: ver.after does not have 6 rows'
grep -c ' 1\.39\.5 LIVE$' ver.after                   # must print 6
grep -vc ' 1\.39\.5 LIVE$' ver.after                  # must print 0
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o wide   # 3 per gateway, one per node
```
- PASS: 6 lines `<pod> 1.39.5 LIVE`, 6 × the `9d84a586…` imageID, each gateway one pod per node.
- FAIL shape: a `1.39.1` line (pod not re-rendered / roll half-done); `UNREADABLE`
  (admin not answering); state `PRE_INITIALIZING`/`DRAINING` (not at config); two pods
  of one gateway on one node (spread collapsed, seen 2026-09-07).
- The gate can fail: `ver.before` reads `1.39.1` on these pods (live 2026-10-13), so the
  `1\.39\.5` grep returns 0 against the pre-state. Note the imageID is the INDEX digest
  `9d84a586…` on these nodes (live pods show the index digest `eb2c01c1…` for 1.39.1,
  not a per-arch digest).

4.1b **CONTENTS ASSERTION: the rendered filter map is unchanged, including the
local rate limit on envoy-external** — the one changed code path we run (§1). Measured
by `filtmap` (structural `/config_dump` parse), compared to `filt.before` with pod names
stripped (pods are new after the roll).
```bash
. /tmp/envoy1395-win/fns.sh
filtmap | sort | tee filt.after
test -s filt.after && [ "$(wc -l < filt.after)" -eq 6 ] && echo FILT_AFTER_ROWS_OK
strip() { sed -E 's/^(envoy-(internal|external))-[^ ]+ /\1 /' "$1" | sort; }
strip filt.before > filt.before.k; strip filt.after > filt.after.k
grep -c UNREADABLE filt.after.k                                    # must print 0
diff filt.before.k filt.after.k && echo FILTMAP_UNCHANGED
grep -c '^envoy-external .*local_ratelimit=1/1' filt.after.k       # must print 3 (if §2.3b baseline was 1/1)
# negative control: the same grep against the internal rows must print 0 -- the counter discriminates
grep -c '^envoy-internal .*local_ratelimit=1/1' filt.after.k       # must print 0
```
- PASS: `FILT_AFTER_ROWS_OK`, `FILTMAP_UNCHANGED`, 0 `UNREADABLE`, external count 3, internal 0.
- FAIL shape: `local_ratelimit=0/0` on an external pod (the BackendTrafficPolicy no longer
  renders, i.e. the AI-generate endpoint lost its abuse guard while every route stays
  200); `ext_authz` lower than baseline (a SecurityPolicy dropped — forward-auth silently
  bypassed or the route 5xx's); any `UNREADABLE`.
- Why config, not a 429 probe: provoking the limit means POSTing to an AI generation
  endpoint (cost + real user buckets); the per-route config is the contents of what this
  change could drop. The `envoy_http_local_rate_limit_*` metrics are not used: they are
  per-pod counters that reset on the roll and only materialise once traffic hits the
  filter, so an empty result would be ambiguous.

4.2 Route and policy acceptance must not regress (diff against §2.5):
```bash
. /tmp/envoy1395-win/fns.sh
routes > routes.after; policies > policies.after
test -s routes.after && test -s policies.after && test -s routes.before && test -s policies.before \
  && diff routes.before routes.after && diff policies.before policies.after && echo ACCEPTANCE_UNCHANGED
btpninth | tee btp.after; diff btp.before btp.after && echo BTP_NINTH_UNCHANGED   # policy re-baseline (see below)
```
- PASS only if `ACCEPTANCE_UNCHANGED` prints (two empty files would diff equal; the
  `test -s` guards make that a FAIL).
- PASS also needs `BTP_NINTH_OK` (last line of `btp.after`) AND `BTP_NINTH_UNCHANGED`:
  `BackendTrafficPolicy my-software-production/the-ninth-banner-ai-generate` (the only
  `mergeType` user and the only `local_ratelimit` route) must still report exactly ONE
  ancestor, `Gateway/envoy-external/https`, `Accepted=True,Merged=True`. EG 1.9.3 changed
  how `mergeType` policies report ancestors (upstream #10314); our route's parentRef has a
  `sectionName`, which that fix does not touch, so a diff here would be a surprise, not an
  expectation. `btpninth` fails (rc 1, `BTP_NINTH_CHANGED`) on 0, 2 or a differently-keyed
  ancestor or a missing `Merged` condition (the python is the same code path that printed
  `BTP_NINTH_OK` live on 2026-10-26; a synthetic second ancestor made its comparison False).
  A change that still shows `Accepted=True` on every ancestor but reshapes the list is a
  real finding for §4.1b (does `local_ratelimit=1/1` still hold on envoy-external?).
- FAIL shape: a line moves to `Accepted=False`/`ResolvedRefs=False`, a count drops, or a
  policy kind gains a `False`. This is now the floor check for the controller as well as
  the data plane: the controller IS replaced, so a translation regression shows here first.

4.3 **CONTENTS ASSERTION, behavioural probe of BOTH gateways** — every host+VIP pair
serves the same status as `status.before`.
```bash
. /tmp/envoy1395-win/fns.sh
sweep > status.after
test -s status.after && echo AFTER_NONEMPTY                                   # absent = FAIL
wc -l < status.before; wc -l < status.after                                   # must be EQUAL (~80)
awk '{print $1}' status.after | sort | uniq -c   # both .103 and .104 present, same counts as status.before
# prove the comparator can FAIL: one row forced to 000 must give rc 1 and exactly one CHANGED line
sed '1s/^\([^ ]*\) [0-9]*/\1 000/' status.after > status.knownbad
changed status.before status.knownbad; echo "control rc=$?"                    # must print CHANGED ... -> 000 and "control rc=1"
changed status.before status.after; echo "rc=$?"                              # rc 0 clean, rc 1 CHANGED rows, rc 2 GUARD = FAIL
```
- If `control rc=1` does not print, the comparator is blind: FAIL the gate.
- Any `GUARD:` line or `rc=2` is an instrument FAIL, never "0 CHANGED".
- Re-probe each `CHANGED` line once after 60 s (an app pod can be mid-restart).
- PASS: `AFTER_NONEMPTY`, equal row counts, `control rc=1`, real run rc 0 (or rc 1 where
  every CHANGED row returns to baseline on re-probe); both VIPs present.
- FAIL: a pair stuck at `000` (TLS/listener failure); stuck at `404` (route dropped; the
  negative control proved Envoy says 404 for an unrouted host); a `2xx/3xx/401` stuck at
  `5xx` (`302 -> 5xx` = broken Authentik forward-auth).

4.4 Prometheus gates. Wait 10 minutes after §3.4 so the 5m windows cover only new pods.
```bash
. /tmp/envoy1395-win/fns.sh
q 'count(up{namespace="network",job="network/envoy-gateway"}==1)'                               # 6
q 'sum(envoy_listener_manager_lds_update_rejected{namespace="network"})'   # 0
q 'count(envoy_listener_manager_lds_update_rejected{namespace="network"})' # 6 (non-vacuous: EMPTY cannot pass)
q 'sum(envoy_cluster_manager_cds_update_rejected{namespace="network"})'    # 0
q 'sum(rate(envoy_http_downstream_rq_xx{namespace="network",envoy_response_code_class="2"}[5m]))' # > 0
q 'sum(rate(envoy_http_downstream_rq_xx{namespace="network",envoy_response_code_class="5"}[5m])) / sum(rate(envoy_http_downstream_rq_xx{namespace="network"}[5m]))'   # < 0.02
q 'min(probe_success{probe_class=~"http|dns"})'                                                   # 1
q 'count(probe_success{probe_class="dns"})'                                                       # 2 (non-vacuous: the k8s-gateway DNS probes exist; EMPTY or 0 = FAIL)
q 'min(probe_success{probe_class="dns"})'                                                         # 1 (internal DNS answers; the k8s-gateway protection gate)
alerts                                                                                            # exactly two lines: RULES=6 and []  (RULES_NOT_6_INSTRUMENT_BLIND or QUERY_FAILED = FAIL: an empty firing list over a missing rule set is vacuous)
pfstop
```
`PF_FAILED`, `QUERY_FAILED` or `EMPTY` on any line is a FAIL, never a pass. All metric
names below returned non-empty results live on 2026-10-13.
- CONTROL: metric envoy_http_downstream_rq_xx — 2xx rate `> 0` (floor against a data plane that is up but serves nothing; baseline ~1.05 rps 2026-10-13); 5xx ratio `< 0.02`.
- CONTROL: metric envoy_listener_manager_lds_update_rejected — raw sum over the 6 new pods `0`, series count `6`. Raw counter, not `increase()`, because `increase()` drops a new series' first sample and would miss a rejection of the initial config.
- CONTROL: metric envoy_cluster_manager_cds_update_rejected — raw sum `0`.
- CONTROL: metric probe_success — min over the 5 http/dns blackbox probes `1`.
- CONTROL: metric up — `count(up{job="network/envoy-gateway"}==1)` = `6` (all new pods scraped).
- CONTROL: alertname EnvoyGatewayMetricsAbsent — must NOT be firing (keeps the metric gates non-vacuous).
- CONTROL: alertname EnvoyGateway5xxSustained — must NOT be firing.
- CONTROL: alertname EnvoyGatewayPodCrashLooping — must NOT be firing.
- CONTROL: alertname EnvoyGatewayPodNotReady — must NOT be firing.
- CONTROL: alertname IngressProbeFailing — must NOT be firing.

Alert rules verified present in git 2026-10-13: `gateway-availability-alerts.yaml`
(MetricsAbsent, 5xxSustained), `envoy-gateway-alerts.yaml` (PodCrashLooping,
PodNotReady), `blackbox-exporter-alerts.yaml` (IngressProbeFailing), all under
`kubernetes/apps/monitoring/kube-prometheus-stack/app/`.

4.5 Soak: re-run 4.1b, 4.3 and 4.4 once more, 7 minutes later (each block sources
`fns.sh`; after-files are overwritten and re-guarded). An RDS update happens on any
route change; the carried 1.39.4 fixes are in that path, so a crash would show as a restart:
```bash
kubectl -n network get pods -l app.kubernetes.io/component=proxy -o jsonpath='{range .items[*]}{.metadata.name} {range .status.containerStatuses[?(@.name=="envoy")]}{.restartCount}{end}{"\n"}{end}'   # all 0
```
Also at the end of the soak, `endstate 1.39.5 v1.9.3` (§4.0) once more, and
```bash
kubectl -n network get pods -l app.kubernetes.io/name=gateway-helm -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].restartCount}{"\n"}{end}'   # 3 pods, all 0
```
Then retire this plan file per `README.md` (separate commit).

## 5. Rollback

One `git revert` restores BOTH pins. Nothing in this change is forward-only: no CRD CONTENT
change (so the Gateway-API admission-policy trap in `docs/sops/envoy-gateway-upgrade.md`
§Rollback does not apply; §4.0b proves it), no state, no migration. The old data-plane
image is digest-pinned, published and cached on every node; `gateway:v1.9.2` is still
published (§2.3, HTTP 200 on 2026-10-26) and the 3 nodes ran it until this change.

5.1 Revert and push (~2 min plus the controller roll and the proxy roll(s)):
```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-3.2>
git log -1 --format=%s    # must be 'Revert "feat(envoy-gateway): chart 1.9.2 -> 1.9.3 + data plane distroless-v1.39.1 -> v1.39.5"'
git show --stat HEAD      # exactly the 4 files of §3.2
grep -o 'envoy:distroless-v[^ ]*' kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
#   must print envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4
grep -c '^      version: 1\.9\.2$' kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml    # 1
git push
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization envoy-gateway-crds -n network
flux reconcile kustomization envoy-gateway -n network
flux reconcile helmrelease envoy-gateway -n network
```
Then wait for the END STATE with the OLD values (same poll as §3.4, NOT `rollout status`):
```bash
. /tmp/envoy1395-win/fns.sh
for i in $(seq 1 30); do endstate 1.39.1 v1.9.2 > endstate.out && break; sleep 30; done; cat endstate.out; echo "polls=$i"
#   PASS: END_STATE_OK envoy=1.39.1 gateway=v1.9.2 holder=...
```
If the revert conflicts (another commit touched the same lines), restore by hand. Both
sed lines were dry-tested 2026-10-26 on scratch copies (returned the originals):
```bash
H=kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml
F=kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
sed -i '' 's/^\([[:space:]]*version: \)1\.9\.3$/\11.9.2/' "$H"
sed -i '' 's|envoyproxy/envoy:distroless-v1\.39\.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0$|envoyproxy/envoy:distroless-v1.39.1@sha256:eb2c01c13125d1629637cb4e4cce7207009fb7cc2c8027f9742758549d15b6f4|' "$F"
mise exec -- bash kubernetes/apps/network/envoy-gateway/crds/revendor.sh 1.9.2     # header lines back to :1.9.2
git diff --stat           # then: the same 4 files, 1 line each, equal to the revert
```
Then commit it with `--only` as in §3.2 and verify the subject. If helm-controller already
remediated a FAILED chart upgrade on its own (`kubectl get helmrelease envoy-gateway -n
network` shows the previous chart again), the data plane may still carry the new image: git
is then the thing to revert so the cluster and git agree again.

5.2 Confirm the cluster is back:
- `endstate 1.39.1 v1.9.2` = `END_STATE_OK` (the primary gate), and `grep -c shutdown-manager-tmp`
  over the proxy pods' volumes back to `0`.
- Re-run 4.1 with `1\.39\.1` in place of `1\.39\.5` (6 × imageID `sha256:eb2c01c1…`,
  `grep -c ' 1\.39\.1 LIVE$' ver.after` = 6), keeping the `test -s` and 6-row guards.
- Re-run 4.0b (`CRD_SET_IDENTICAL`), 4.1b, 4.2 (including `BTP_NINTH_UNCHANGED`), 4.3 (including the `status.knownbad` control) and 4.4 against the
  SAME `/tmp/envoy1395-win/*.before` baselines. They must pass.

5.3 **Break-glass, data plane dark and the revert cannot land.** (The controller being down
or leaderless alone does NOT darken the data plane: the proxies keep serving their last
xDS config; only new pods or a restart of a proxy need the controller.) Flux fetches from GitHub
over cluster DNS/egress, not through Envoy, so a dark Envoy does not block 5.1. If new
pods crash-loop, `kubectl -n network rollout undo deploy/envoy-internal` (and
`envoy-external`) is a stopgap only — the controller re-renders these Deployments from
the EnvoyProxy CR and overwrites the undo at the next reconcile. Follow with 5.1 at once.

## 6. Interference notes

- **Attended window only (sat/sun), never nightly.** `touches.shared` carries
  `gateway/envoy` (in `SHARED_INFRA_FLOOR`); `autonomy_override: human-gated` says so
  explicitly. No reboot, not `exclusive`, but it should be the only routing-perturbing
  plan in its window.
- **MATERIAL CHANGE TO A PLAN THAT ALREADY HAD A GO (2026-10-26).** The operator GO of
  2026-10-23 was given for the data-plane pin only. This revision adds the chart
  `gateway-helm` 1.9.3 and a controller roll, so that GO does not carry over: after the
  plan-reviewer re-reviews this file (`review: null`, `status: draft` until then), the
  GO must be asked for AGAIN on the new scope (chart + controller + data plane in one
  commit, possible double proxy roll, 70 min). Do not run it, and do not let the window
  agent treat the old GO record as covering it.
- **No deny-rule departure any more.** Rule `*envoyproxy/envoy*` says the pin moves only in
  the SAME change as the gateway-helm chart bump; with chart 1.9.3 merged in, that is
  exactly what this plan does (the pin equals 1.9.3's `DefaultEnvoyProxyImage`). The
  earlier "operator decides the departure / rule reword" item is withdrawn.
- **Chain bookkeeping is complete:** the -v1.39.2 file is `superseded`; the -v1.39.3 draft no
  longer exists. Two plans moving the same pin must never both be open: the 1.40.0 plan is
  `blocked` and names this plan; its pinned target (1.40.0) is itself stale (upstream is on
  1.40.1) and stays blocked because no EG release supports Envoy 1.40.
- **Controller prerequisite:** the premise `controller-is-1.9.2` is a PRE-state check now
  (this plan moves the chart itself). If the chart is already 1.9.3 (a Renovate PR merged
  it, or someone ran it), the proxies have already rolled once on the new sidecar: the
  premise fails, and the plan reduces to the data-plane pin line only. Re-plan, do not
  force it. Keep Renovate's chart PR (when one appears) unmerged until this plan runs.
- **Slot: `window: null`, the operator chooses.** `etcd-timeouts-5000-500` (vetted) holds
  `sun-attended:2026-11-08` (110 min) and the two plans are mutual `conflicts_with`. In any
  case `sun-attended` is 200 min minus the 20-min Step-0 reserve = 180 usable, and 110 + 70 =
  180 leaves ZERO slack for a 45-min rollback. It also matters operationally: etcd restarts
  one control-plane node at a time while this change replaces the EG controller (leader
  election and helm-controller both need the apiserver); stacking them would confound both
  gates. Options (the operator's call; this plan does not pick):
  1. `sun-attended:2026-12-06`: the earliest conflict-free slot per the 2026-10-26 re-review
     (empty, first after Step 0). 70 of 180 usable min; the safe default.
  2. `sat-attended:2026-11-28`: fits only with ZERO slack (sat-attended is 90 min, 70 usable,
     plan is 70) — a failed gate has no rollback budget in the slot. Not recommended.
  3. Keep `sun-attended:2026-11-08` (the 2026-10-23 choice) and MOVE `etcd-timeouts-5000-500`
     to another Sunday, then drop the `conflicts_with` pair's date overlap. Needs that plan's
     owner to agree.
  Do not stamp a `window:` here by hand; the window agent / scheduler assigns it after the
  GO. Earlier attended slots are unavailable: 11-01 is the exclusive Talos roll.
- **Any app-restarting plan sharing the slot** (`nocodb-2026.09.1` was named here before; that
  plan file no longer exists): read/read overlap on `monitoring` only, but an app with an
  HTTPRoute restarting would show as a `CHANGED` row in §4.3, so serialize: this plan runs
  first and finishes its §4.5 soak before anything else starts. Not in `conflicts_with`,
  because that would forbid a shared slot that is fine when serialized.
- **Run it FIRST among the remaining plans**, right after Step 0 settles: any app with an
  HTTPRoute that another same-window plan restarts becomes a `CHANGED` line in §4.3.
- **Reciprocity (re-checked 2026-10-26 against every other plan file's `conflicts_with`).**
  `--validate` does not check it. These now name this plan id, so the pairs are mutual:
  `etcd-timeouts-5000-500` (apiserver/leader election, 180 of 180 min), `flux-oci-chart-sources`
  and `flux-reconciler-impersonation` (the apply and revert path; the latter is `blocked`),
  `authentik-2026.8.5`, `authentik-web-max-requests` (same Authentik forward-auth path),
  `talos-linux-1.14.4` (node drain vs the single PDB disruption), `envoy-proxy-config-distroless-v1.40.0`
  (same pin line, blocked). ONE-WAY the other direction (they name this plan; this plan does not
  name them; optional, decide at the vet): `redis-fleet-8.10.2`, `tube-archivist-0.6.0` (touches
  `gateway/envoy-external`; an app restart there would be a `CHANGED` row in §4.3).
  If a coredns or `kube-prometheus-stack` plan is opened for the same window, serialize it
  (§2.7/§4.4 read Prometheus/blackbox; cluster DNS is on the instrument path) and add it to
  `conflicts_with` on both sides.
- **Traffic during the roll.** Surge-first, one pod at a time (25%/25% -> maxSurge 1,
  maxUnavailable 0; PDB minAvailable 2). The shutdown-manager drains each old pod
  (terminationGracePeriod 360 s). Long-lived connections (websockets, SSE, HA frontend,
  media streams) are cut once per pod and reconnect: interruption, not data loss. If the new
  controller re-renders the Deployments after the old one did (§1), a pod can be replaced twice,
  so a long-lived connection may be cut twice.
- **Not touched:** k8s-gateway (CRD content unchanged, so the SOP's restart-twice DNS gate is
  NOT needed; §4.0b proves the premise and checks the pods were not restarted), external-dns and
  public DNS, cert-manager certificates. **Touched (new 2026-10-26):** the EG controller
  Deployment (3 replicas) and the HelmRelease; `helm-drift-detection` (`sat-attended:2026-11-07`,
  the day before, adds a field to all HelmReleases incl. this one) is a different window and
  needs no entry, but its P-gates must be clean before this runs.
