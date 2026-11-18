---
plan_id: envoy-gateway-1.10.0
component: envoy-gateway
also_covers:
  - gateway-crds-helm                 # the vendored CRDs under crds/ (revendor.sh 1.10.0), same commit
  - docker.io/envoyproxy/envoy        # the Envoy DATA-PLANE pin in EnvoyProxy/network/envoy-proxy-config, same commit
supersedes:                           # both are BLOCKED waiting for exactly this release (their UNBLOCK = "an EG v1.10.x
  - envoy-proxy-config-distroless-v1.40.2   #   release whose DefaultEnvoyProxyImage is distroless-v1.40.x"). Their files are
  - envoy-proxy-config-distroless-v1.40.0   #   NOT edited here (planner writes one file); bookkeeping owed, see §6.4.
pr: 496                               # Renovate "feat(container): update gateway-helm ( 1.9.3 → 1.10.0 )". DO NOT MERGE AS-IS:
                                      # it bumps only the chart line (§1.2). Executed as one direct commit on main; the PR is
                                      # then closed by Renovate (or by hand) as already-applied.
kind: chart
current: "1.9.3"
target: "1.10.0"
update_type: minor
risk: high                            # Envoy Gateway is the ONLY HTTP data plane (93 HTTPRoutes, LAN .103 + public edge .104),
                                      # and this change rolls the controller AND all 6 proxy pods AND moves the data plane a
                                      # MINOR (Envoy 1.39 -> 1.40) AND re-applies 8 EG CRDs, which re-arms the k8s-gateway
                                      # (cluster DNS) restart gate. Probability of trouble is low (§1.4), impact is total.
est_duration_min: 85                  # §2 15 + §3 edits/commit 10 + reconcile+rolls ~10 + DNS gate x2 ~12 + §4 ~23 + soak 10 + slack 5
needs_reboot: false
exclusive: true                       # "no other change in flight": every other plan's reachability/auth gate goes THROUGH this
                                      # data plane and every name resolves through the k8s-gateway this re-gates, so any co-tenant
                                      # both confounds and is confounded. Also covers plans not written yet.
touches:
  namespaces: [network]
  resources:
    - helmrelease/network/envoy-gateway                     # chart 1.9.3 -> 1.10.0 (controller image v1.9.3 -> v1.10.0, 3 pods)
    - kustomization/network/envoy-gateway-crds              # re-applies crds/ (8 gateway.envoyproxy.io CRDs change; 10 Gateway API CRDs header-only)
    - kustomization/network/envoy-gateway
    - deployment/network/envoy-gateway                      # ROLLS (3 pods, surge-first, PDB minAvailable 2)
    - job/network/envoy-gateway-gateway-helm-certgen        # helm hook, re-runs on upgrade
    - envoyproxy/network/envoy-proxy-config                 # data-plane image distroless-v1.39.5 -> distroless-v1.40.2
    - deployment/network/envoy-internal                     # ROLLS (3 pods: envoy 1.40.2 + shutdown-manager v1.10.0)
    - deployment/network/envoy-external                     # ROLLS (3 pods)
    - deployment/network/k8s-gateway                        # §3.6 DNS gate: rollout restart TWICE (SOP-mandated)
    - "crd/*.gateway.envoyproxy.io (8)"
    - kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml
    - kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
    - kubernetes/apps/network/envoy-gateway/crds/envoy-gateway.yaml
    - kubernetes/apps/network/envoy-gateway/crds/gateway-api-standard.yaml   # header lines only (proved §1.3)
  shared:
    - gateway/envoy                   # envoy-internal (.103) + envoy-external (.104) carry EVERY HTTPRoute
    - envoy-internal
    - envoy-external
    - public-edge                     # envoy-external is the internet-facing data plane (cloudflared wildcard)
    - dns                             # k8s-gateway (192.168.55.101) is restarted twice by the gate; every cluster name
    - authentik                       # 13 SecurityPolicies (extAuth forward-auth) are enforced inside Envoy; §4.4 logs in
    - monitoring                      # §4 reads Prometheus (envoy LDS/CDS-rejection counters, probe_success) — the instrument
depends_on: []
conflicts_with:                       # built 2026-11-07 from every non-terminal plan's frontmatter (maintenance-plan.py --open)
  - envoy-proxy-config-distroless-v1.40.2   # SAME pin line; superseded by this plan (blocked)
  - envoy-proxy-config-distroless-v1.40.0   # SAME pin line; superseded (blocked)
  - talos-linux-1.14.5                # node drains compete for the single PDB disruption per gateway + k8s-gateway; exclusive itself
  - flux-oci-chart-sources            # moves Flux chart sources + touches public-dns/monitoring; same §3/§5 apply-and-revert path
  - helm-drift-detection              # adds spec.driftDetection to every HelmRelease incl. this one
  - flux-reconciler-impersonation     # rewrites how kustomize-controller applies crds/ and app/ (blocked, exclusive)
  - etcd-timeouts-5000-500            # apiserver restarts confound the rolls, the CRD apply and the §4 gates (blocked)
  - redis-fleet-8.10.3                # it already declares a conflict with the 1.40.x pin plans (public-edge reads)
  # - open-webui-0.13.0  (dead ref: plan retired; removed 2026-11-16 by plan review)                 # same: its §4.6 reads the app through envoy-external
  - tube-archivist-0.6.0              # shared gateway/envoy-external; its reachability gate reads through the edge
  - kube-prometheus-stack-93.3.0      # draft, exclusive; rolls Prometheus = the instrument §2.5/§4.2/§4.5 read (lists this plan already)
  - coredns-1.50.5                    # draft; cluster DNS roll confounds the §3.6 DNS gate and the dig checks (does NOT list this plan yet, §6.4)
  - immich-server-3.4.1               # draft; its §4.8/§4.9 gates read through envoy-external (lists this plan already)
  - nextcloud-9.4.3                   # draft; public-edge gates (status.php, /login) read through envoy-external (lists this plan already)
  - postgres-fleet-18.7-bookworm      # draft; lists this plan already (13 forward-auth policies live in this data plane)
capability_change: true               # Not a same-behaviour bump. The data plane crosses an Envoy MINOR (1.40: post-quantum
                                      # X25519MLKEM768 joins the default ECDH curves on every TLS handshake, event-driven drain,
                                      # container-aware worker count, removed runtime guards), and EG 1.10 changes live behaviour
                                      # we use: local rate-limited 429s now carry Retry-After (BTP the-ninth-banner-ai-generate),
                                      # active health checks follow the backend protocol. Plus new API surface (8 CRDs gain fields).
rollback_class: git-revert            # ESTABLISHED, not assumed (§1.5): the Gateway API bundle stays v1.6.1, so the
                                      # safe-upgrades VAP floor does not move and does not block the revert; the EG CRD change is
                                      # purely ADDITIVE (0 removed fields, 0 removed/renamed versions, all v1alpha1 served+storage),
                                      # and no live object uses a new field. §2.7 proves the 1.9.3 CRDs are still admissible by a
                                      # server-side dry-run BEFORE the change. One commit, one revert.
autonomy_override: human-gated        # shared gateway/dns/authentik derives HUMAN-GATED anyway; attended window only.
security_ref: null                    # not security-driven (dispatch: security_evidence none)
finding_refs:
  - F-6b98d1ef                        # section version, "envoy-gateway: chart 1.9.3 -> 1.10.0 (minor)", open (status unchanged) -- THE version row
  - F-dd4736a3                        # section doc, docs/applications.md:225 says gateway-helm 1.9.2, live is 1.9.3; fixed by the optional line in §3.3
                                      # (F-10b4fee2, data-plane 1.40.2 row, is already RESOLVED. F-88de0e3b was the OLDER 1.9.0 -> 1.9.2 doc row,
                                      # resolved 2026-11-14 in 3fbded01; it exists but is not this change's finding, so it is not referenced.)
review: ready-for-go@2026-11-15      # plan-reviewer 2nd pass 2026-11-15: ready-for-go, 0 blocking (1st pass needs-fix, all 3 blockers fixed + verified live)
status: awaiting-go
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/envoy-gateway-upgrade.md
  - docs/sops/k8s-gateway-dns.md
  - docs/sops/gateway-api-httproute.md
  - docs/sops/authentik.md
generated: "2026-11-07"
premises:
  - id: hr-chart-is-1.9.3
    why: "current: and §5's restore target. Any other value means the chart moved by another path; re-plan."
    run: kubectl get helmrelease envoy-gateway -n network -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "1.9.3"
  - id: hr-ready
    why: "Do not upgrade a controller that is already failing; it renders both proxy Deployments."
    run: kubectl get helmrelease envoy-gateway -n network -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: live-controller-v1.9.3
    why: "Git and cluster agree before the edit, so the roll is attributable to this change."
    run: kubectl get deploy envoy-gateway -n network -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "docker.io/envoyproxy/gateway:v1.9.3"
  - id: repo-pin-is-1.39.5
    why: "§3.3's sed is anchored on this exact tag+digest; if the pin moved, the sed matches nothing and §5 restores the wrong image."
    run: grep -o 'envoy:distroless-v[^ ]*' kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
    expect_exact: "envoy:distroless-v1.39.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0"
  - id: vendored-crds-from-1.9.3
    why: "Both vendored files must come from the current chart, or revendor.sh's UNCHANGED/CHANGED verdict in §3.2 compares against the wrong baseline."
    run: grep -h '^# Source. oci' kubernetes/apps/network/envoy-gateway/crds/gateway-api-standard.yaml kubernetes/apps/network/envoy-gateway/crds/envoy-gateway.yaml | sort -u
    expect_exact: "# Source: oci://docker.io/envoyproxy/gateway-crds-helm:1.9.3"
  - id: vendored-bundle-v1.6.1
    why: "THE rollback premise: the plan's git-revert class rests on the Gateway API bundle NOT moving (1.10.0 also ships v1.6.1). If the vendored bundle is already something else, the VAP analysis in §1.5 is void."
    run: grep -ho 'bundle-version. v[0-9.]*' kubernetes/apps/network/envoy-gateway/crds/gateway-api-standard.yaml | sort -u
    expect_exact: "bundle-version: v1.6.1"
  - id: safe-upgrades-vap-present
    why: "§1.5 reasons about this policy; confirm it is the one in force."
    run: kubectl get validatingadmissionpolicy safe-upgrades.gateway.networking.k8s.io -o name
    expect_exact: "validatingadmissionpolicy.admissionregistration.k8s.io/safe-upgrades.gateway.networking.k8s.io"
  - id: both-gateways-programmed
    why: "Start from a serving data plane; a pre-existing Programmed=False would be blamed on the bump."
    run: >-
      kubectl get gateway -n network -o jsonpath='{range .items[*]}{.metadata.name}={.status.conditions[?(@.type=="Programmed")].status} {end}'
    expect_matches: '^envoy-external=True envoy-internal=True\s*$'
  - id: six-proxy-pods-ready
    why: "The surge-first roll and PDB minAvailable 2 assume 3/3 per gateway at the start."
    run: >-
      kubectl get deploy envoy-internal envoy-external envoy-gateway -n network -o jsonpath='{range .items[*]}{.metadata.name}={.status.readyReplicas} {end}'
    expect_matches: '^envoy-internal=3 envoy-external=3 envoy-gateway=3\s*$'
  - id: k8s-gateway-3-ready
    why: "The DNS restart gate rolls k8s-gateway twice under PDB minAvailable 2; it must start at 3/3."
    run: kubectl get deploy k8s-gateway -n network -o jsonpath='{.status.readyReplicas}'
    expect_exact: "3"
---

# envoy-gateway: chart 1.9.3 -> 1.10.0 (+ EG CRDs + Envoy data plane 1.39.5 -> 1.40.2, one commit)

## 1. Summary & why held

### 1.1 What changes (one commit, three edits)

| File | Change |
|---|---|
| `kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml` | `version: 1.9.3` -> `version: 1.10.0` (controller `docker.io/envoyproxy/gateway:v1.9.3` -> `v1.10.0`; same image for the proxies' shutdown-manager sidecar) |
| `kubernetes/apps/network/envoy-gateway/crds/{gateway-api-standard,envoy-gateway}.yaml` | re-vendored by `revendor.sh 1.10.0` |
| `kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml` (line 85) | Envoy pin `distroless-v1.39.5@sha256:9d84a586…` -> `distroless-v1.40.2@sha256:09ca6f2140a61ad8df11779a4a30d52b48433d444466328494f9188c9c35eded` |

Everything else in the rendered chart is unchanged: `helm template` of 1.9.3 vs 1.10.0 with
the live HelmRelease values (measured 2026-11-07) differs ONLY in the three
`docker.io/envoyproxy/gateway:` image lines and the chart/version labels. No RBAC rule,
webhook, Service port, or values-key change. The certgen helm-hook Job re-runs.

### 1.2 Why held, and why PR #496 must not be merged as-is

Policy hold (`runbooks/auto-update-policy.yaml`, rules `*gateway-helm*` / `*envoy-gateway*` /
`*envoyproxy/envoy*`): a chart bump drags the CRD channel with it; any bump runs the
k8s-gateway restart gate twice; and the data-plane pin "moves only in the SAME change as the
gateway-helm chart bump, to that release's DefaultEnvoyProxyImage — never on its own".

PR #496 changes exactly one line (`version: 1.10.0`, checked via `gh pr diff 496`; CI green).
Merging it alone would (a) leave the vendored EG CRDs at 1.9.3 under a 1.10.0 controller, and
(b) keep the explicit 1.39.5 pin, so EG 1.10 would drive an Envoy minor it was never tested
with. Upstream matrix (`site/content/en/news/releases/matrix.md`): "Each Envoy Gateway release
ships with, and is tested against, a single Envoy Proxy minor version", row
`v1.10 | distroless-v1.40.x | … | Gateway API v1.6.1 | Kubernetes v1.34-v1.37`. Hence the
three edits are one commit. The cluster is on Kubernetes v1.36.0 (all 3 nodes): on-matrix for
both 1.9 and 1.10.

Target data-plane image = EG v1.10.0's compiled default
(`api/v1alpha1/shared_types.go@v1.10.0`):
`DefaultEnvoyProxyImage = "docker.io/envoyproxy/envoy:distroless-v1.40.2@sha256:09ca6f21…"`.
Registry re-resolved 2026-11-07: Docker Hub `envoyproxy/envoy:distroless-v1.40.2` index digest
= `sha256:09ca6f2140a61ad8df11779a4a30d52b48433d444466328494f9188c9c35eded` (match).
Controller `envoyproxy/gateway:v1.10.0` index digest `sha256:c2243d43…` (published).

### 1.3 The CRD question, answered with the actual bytes (not inferred)

Rendered `gateway-crds-helm:1.10.0` exactly as `revendor.sh` does, into a scratch dir, and
compared with the committed files minus their 3 header lines:

- `gateway-api-standard.yaml`: **content byte-identical** (`diff` = 0 lines). Bundle stays
  `gateway.networking.k8s.io/bundle-version: v1.6.1` on all 12 annotated objects (10 CRDs + VAP
  + binding). **The Gateway API channel does NOT move.** So the policy's core fear ("the NEXT
  channel bump is unproven against k8s-gateway") does not arise in this release.
- `envoy-gateway.yaml`: **content CHANGED** (~5000 diff lines). Structural diff of all 8
  `gateway.envoyproxy.io` CRDs: same names, same single version `v1alpha1` (served+storage),
  **0 removed schema paths**, additions only (e.g. Backend +3, BackendTrafficPolicy +45,
  ClientTrafficPolicy +29, EnvoyExtensionPolicy +172, EnvoyProxy +64, SecurityPolicy +49),
  plus new CEL/enum rules (they apply on the next write of an object, not retroactively).

Because the EG CRD file changes, the SOP's header-only exception does NOT apply (it requires
both files unchanged): **run the full restart-twice DNS gate** (§3.6). (k8s_gateway informs
only on the `gateway.networking.k8s.io` group, which does not change, so the gate is expected
to pass; it is run because the SOP says so, not because a failure is predicted — see the repo
correction in §6.5.)

### 1.4 Upstream breaking changes, checked against what we run

Source: `release-notes/v1.10.0.yaml` at envoyproxy/gateway (dated November 5, 2026), section
"breaking changes". Each item checked against the live objects (2026-11-07):

| Upstream breaking change (quoted, abridged) | Our exposure |
|---|---|
| "Backend now requires `endpoints` when `type` is `Endpoints` (the default)." | `backend/security/wazuh-dashboard-tls` is `type: Endpoints` WITH `endpoints: [fqdn wazuh-dashboard.security…:5601]` — compliant. |
| "Rate-limited 429s now include `Retry-After` by default." | `backendtrafficpolicy/my-software-production/the-ninth-banner-ai-generate` uses `rateLimit.type: Local` — its 429s gain a `Retry-After` header. Behaviour change, benign; no opt-out set. |
| "Active HTTP health checks now use the HTTP protocol of the requests to the backend…" | No BackendTrafficPolicy sets `healthCheck` (both BTPs checked). Not exposed. |
| "Health check `timeout`/`interval` … rejected at admission when set to `0s`." | Not used. |
| "ClientTrafficPolicy now rejects `tls.clientValidation.subjectAltNames`… with `VerifyIfGiven`" | Both CTPs set only `clientIPDetection` + `targetRefs`. Not exposed. |
| "A `SecurityPolicy` whose `authorization` rules reference a JWT provider…" / "HTTP is no longer supported as an OIDC issuer URL scheme." / JWT requirement renamed | All 13 SecurityPolicies use `extAuth.http` (Authentik forward-auth) only — no JWT, no OIDC, no `authorization`. Not exposed. |
| Strict Lua validation / Lua xDS shape / Wasm / dynamicModules / extension manager `backendResources` | No EnvoyExtensionPolicy, no EnvoyPatchPolicy, no Lua, no Wasm, no extension manager. Not exposed. |
| Cookie session persistence `Path=/`, generated session-name hash | No route uses `sessionPersistence`. Not exposed. |
| `watchable_depth` removed; `watchable_subscribe_duration_seconds` buckets changed | EG controller metrics are NOT scraped (`count(watchable_subscribe_total)` empty in Prometheus). `edot-collector` configmap lists the metric name only (name unchanged). No alert/dashboard reads the removed buckets (`rg` over `kubernetes/`). |
| `EnvoyProxy … loadBalancerSourceRanges` max 64 CIDRs | Not set. |

Deprecations scheduled for REMOVAL in v1.11 (`targetRef`, `backendRef` on ext-auth, BTP
`compression`, CTP `enableProxyProtocol`): live objects already use `targetRefs`,
`extAuth.http.backendRefs` and `compressor` — nothing to migrate before 1.11.

Envoy 1.40 data plane: covered by the predecessor plans' analysis
(`envoy-proxy-config-distroless-v1.40.2` §1): new default ECDH curve list incl. X25519MLKEM768,
event-driven drain, container-aware CPU detection, removed runtime guards. Those plans were
blocked ONLY for lack of an EG release that compiles 1.40 — EG v1.10.0 is that release.

### 1.5 Rollback class — established

The SOP says "Assume `git revert` will NOT work" because the bundle VAP
(`safe-upgrades.gateway.networking.k8s.io`, `failurePolicy: Fail`) denies Gateway API CRDs
whose `bundle-version` matches `v1.[0-5].\d+`. That bites only when the **Gateway API**
bundle-version moves backwards. Here it is v1.6.1 before and after, so a revert re-applies the
same v1.6.1 content (header lines only differ) and the VAP admits it. The VAP does not cover
`gateway.envoyproxy.io`. The EG CRD revert is to a strict schema subset; no live EG object
sets any field added in 1.10 (we write none in this plan), so nothing is pruned. Helm chart
downgrade 1.10.0 -> 1.9.3 is an ordinary `helm upgrade` by helm-controller (no chart-native
CRDs: `crds.enabled: false`). Hence `rollback_class: git-revert` — and §2.7 proves the
1.9.3 CRDs are still admissible with a server-side dry-run before anything moves.

Safety property worth knowing: the proxy Deployments are rendered by the controller. If the
1.10.0 controller fails to come up, it renders nothing new and the 1.39.5 proxies keep serving
their last good config. Proxy rolls are surge-first (`maxSurge 25%`->1, `maxUnavailable 25%`->0
at 3 replicas) under PDB `minAvailable: 2`, so a new proxy that never goes Ready stalls the
roll instead of draining the gateway.

## 2. Pre-checks (executor; may use gh/curl/loops)

Run in ONE zsh session from the repo root (`cd /Users/mu/code/cberg-home-nextgen`).

2.1 **Premises**: `.venv/bin/python3 runbooks/plan-premises.py envoy-gateway-1.10.0 --require-premises` -> PASS, no `REFUSED`.

2.2 **Upstream unchanged since planning** (stop if any differs):
```bash
gh release view v1.10.0 -R envoyproxy/gateway --json tagName,isPrerelease -q '.tagName+" "+(.isPrerelease|tostring)'   # v1.10.0 false
gh api 'repos/envoyproxy/gateway/contents/api/v1alpha1/shared_types.go?ref=v1.10.0' -H 'Accept: application/vnd.github.raw' | grep 'DefaultEnvoyProxyImage ='
# must contain: distroless-v1.40.2@sha256:09ca6f2140a61ad8df11779a4a30d52b48433d444466328494f9188c9c35eded
gh release list -R envoyproxy/gateway --limit 5   # if a v1.10.x patch exists, consider retargeting (README "When the held target MOVES")
```

2.3 **Baseline, in writing** (the §4 comparisons read these files):
```bash
B=/tmp/eg110-baseline; mkdir -p $B
kubectl get pods -n network -l app.kubernetes.io/name=k8s-gateway -o custom-columns='N:.metadata.name,START:.status.startTime,RC:.status.containerStatuses[0].restartCount' --no-headers > $B/k8sgw.txt; cat $B/k8sgw.txt   # 3 rows
kubectl get httproute -A -o json | python3 -c "
import json,sys
it=json.load(sys.stdin)['items']
bad=[r['metadata']['namespace']+'/'+r['metadata']['name'] for r in it if not r.get('status',{}).get('parents') or any(c['type'] in ('Accepted','ResolvedRefs') and c['status']!='True' for p in r['status']['parents'] for c in p['conditions'])]
print(len(it), len(bad), bad)" | tee $B/routes.txt      # measured 2026-11-07: 93 0 []
kubectl get securitypolicy,clienttrafficpolicy,backendtrafficpolicy -A -o json | python3 -c "
import json,sys
for i in json.load(sys.stdin)['items']:
  a=(i.get('status',{}).get('ancestors') or [{}])
  print(i['kind'], i['metadata']['namespace']+'/'+i['metadata']['name'], sorted({c['type']+'='+c['status'] for x in a for c in x.get('conditions',[])}))" | sort | tee $B/policies.txt   # 13 SecurityPolicy, 2 CTP, 2 BTP
kubectl get crd -o json | python3 -c "
import sys,json
for x in sorted(json.load(sys.stdin)['items'], key=lambda x:x['metadata']['name']):
  if x['spec']['group'] in ('gateway.networking.k8s.io','gateway.envoyproxy.io'):
    print(x['metadata']['name'], x['metadata'].get('annotations',{}).get('gateway.networking.k8s.io/bundle-version','-'), x['metadata']['generation'])" > $B/crds.txt; wc -l < $B/crds.txt   # 18
```

2.4 **Sample hosts** (derived at run time — no hostnames in this public file):
```bash
HI=$(kubectl get httproute -n monitoring prometheus -o jsonpath='{.spec.hostnames[0]}')   # internal, forward-auth protected
HE=$(kubectl get httproute -n ai open-webui -o jsonpath='{.spec.hostnames[0]}')           # external
test -n "$HI" && test -n "$HE" && echo HOSTS_OK
dig +short @192.168.55.101 "$HI"   # 192.168.55.103
dig +short @192.168.55.101 "$HE"   # 192.168.55.104
curl -sk -o /dev/null -w '%{http_code} %{redirect_url}\n' --resolve "$HI:443:192.168.55.103" "https://$HI/" | grep -c '^302 .*/application/o/authorize/'   # 1 (measured 2026-11-07)
curl -sk -o /dev/null -w '%{http_code}\n' --resolve "$HE:443:192.168.55.104" "https://$HE/"   # 200 (measured 2026-11-07)
```

2.5 **Prometheus instrument up** (shared infra; nothing in `kube-prometheus-stack` may be mid-change):
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
# EXECUTOR RULE: an EMPTY (or errored / port-forward-down) answer is a FAIL, never a pass. Only the ALERTS query below
# may legitimately be EMPTY. q() therefore prints FAIL_EMPTY and returns 1 on no data, and a failed port-forward fails loudly.
q(){ curl -sf http://localhost:19090/api/v1/query --data-urlencode "query=$1" | python3 -c 'import sys,json;r=json.load(sys.stdin)["data"]["result"]
if not r: print("FAIL_EMPTY"); sys.exit(1)
print([x["value"][1] for x in r])' || echo "FAIL_NO_DATA: $1"; }
q 'count(envoy_server_live == 1)'                                         # ['6']
q 'sum(envoy_listener_manager_lds_update_rejected) + sum(envoy_cluster_manager_cds_update_rejected)'   # ['0']
q 'count(probe_success{probe_class="dns"} == 1)'                          # ['2']
q 'ALERTS{alertstate="firing",alertname=~"EnvoyGateway.*|InternalDns.*|BlackboxProbesAbsent"}'      # EMPTY
kill $PF 2>/dev/null
```

2.6 **Flux clean, no node event in flight**:
```bash
flux get kustomizations -n network | grep -E 'envoy-gateway'      # both Ready True
kubectl get nodes --no-headers | awk '{print $2}' | sort | uniq -c   # 3 Ready, none SchedulingDisabled
```

2.6b **etcd / apiserver stable for >= 6 h** (etcd was flapping on 2026-11-15; an apiserver or etcd blip mid-roll is
indistinguishable from this change failing, and the CRD apply + two HelmRelease reconciles all write through it):
```bash
kubectl get pods -n kube-system -l component=kube-apiserver -o jsonpath='{range .items[*]}{.metadata.name} restarts={.status.containerStatuses[0].restartCount} up={.status.startTime}{"\n"}{end}'
# PASS: 3 rows, every restarts=0, every up= older than 6 h (compare to `date -u`). Any restart or younger row = STOP, re-schedule.
q 'increase(etcd_server_leader_changes_seen_total[6h])'   # run inside §2.5's port-forward; must print 0 on every member
# FAIL_EMPTY here means etcd is not scraped: fall back to `talosctl etcd status` twice, 10 min apart; RAFT TERM must be equal on all
# 3 members and unchanged between the two reads. Never treat an empty answer as stable.
```

2.7 **Rollback admissibility proof — BEFORE the change** (server dry-run, writes nothing). The
committed 1.9.3 files ARE the rollback target; they must be admitted by the live VAP now:
```bash
D=kubernetes/apps/network/envoy-gateway/crds; S=$(mktemp -d)
n=$(( $(grep -c '^kind: ' $D/gateway-api-standard.yaml) + $(grep -c '^kind: ' $D/envoy-gateway.yaml) ))   # measured 2026-11-15: 12 + 8 = 20
kubectl apply --server-side --dry-run=server --force-conflicts --field-manager=eg110-dryrun -f $D/gateway-api-standard.yaml -f $D/envoy-gateway.yaml > $S/good.out 2>&1
echo "applied=$(grep -c 'serverside-applied (server dry run)' $S/good.out)/$n denied=$(grep -ciE 'denied|forbidden|error' $S/good.out)"
# PASS = applied equals n AND denied=0.   (positive marker: every object must report; "0 errors" alone also reads 0 if kubectl printed nothing)
# CONTROL (known-bad, same command, must FAIL): the same standard file with the bundle stamped v1.5.1
sed 's/bundle-version: v1.6.1/bundle-version: v1.5.1/' $D/gateway-api-standard.yaml > $S/gw-bad.yaml
kubectl apply --server-side --dry-run=server --force-conflicts --field-manager=eg110-dryrun -f $S/gw-bad.yaml > $S/bad.out 2>&1
echo "control denied=$(grep -ciE 'denied|forbidden|error' $S/bad.out)"    # must be >= 1; if 0 the gate cannot fail -> STOP, do not trust a 0 above
```
REPLAYED 2026-11-15 on the live cluster (server dry-run, writes nothing; BSD sed diff: 12 lines changed `v1.6.1` -> `v1.5.1`):
good set printed `applied=20 denied=0` (rc 0); the v1.5.1 control printed `rc=1`, `applied=2` (VAP + binding only) and
`denied=10` ("...is forbidden: ValidatingAdmissionPolicy 'safe-upgrades.gateway.networking.k8s.io' ... denied request: Installing CRDs
with version before v1.5.0 is prohibited"). So the gate discriminates: 0 vs 10, 20/20 vs 2/20. A non-zero count or applied != n = STOP: the
rollback class is wrong; re-plan as backup-restore/forward-fix.

2.8 **Backups**: none required — no PVC, no database, no stateful object is touched. The
"state" is git (§5).

## 3. Steps (GitOps)

3.1 **Chart bump** (dry-tested on a scratch copy with BSD sed 2026-11-07; diff = `23c23 <       version: 1.9.3 --- >       version: 1.10.0`):
```bash
sed -i '' 's/^      version: 1\.9\.3$/      version: 1.10.0/' kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml
grep -c '^      version: 1.10.0$' kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml   # 1
```
Optionally append to the PINNED comment above it: `# 1.9.3 -> 1.10.0 (2026-11-xx): with
EG CRDs re-vendored and Envoy distroless-v1.40.2 (EG 1.10 compiled default), one commit.`

3.2 **Re-vendor CRDs with the script** (never by hand):
```bash
mise exec -- bash kubernetes/apps/network/envoy-gateway/crds/revendor.sh 1.10.0
```
REQUIRED output (verified against a scratch render 2026-11-07):
```
  gateway-api-standard.yaml: content UNCHANGED (header-only diff)
  envoy-gateway.yaml: content CHANGED -- review before proceeding
  bundle-version(s) now vendored: bundle-version: v1.6.1
```
STOP and abort (do not commit; `git checkout -- kubernetes/apps/network/envoy-gateway/`) if
`gateway-api-standard.yaml` reports CHANGED or the bundle-version is anything but `v1.6.1` —
that is a channel move this plan's rollback class does not cover.
Then confirm the EG CRD change is still additive-only (same check as §1.3):
```bash
git diff --stat kubernetes/apps/network/envoy-gateway/crds/   # gateway-api-standard.yaml: 2 lines (+1 -1 header) ; envoy-gateway.yaml: large
git diff kubernetes/apps/network/envoy-gateway/crds/gateway-api-standard.yaml | grep -c '^[-+][^-+]'   # 2 (the Source line, - and +)
```

3.3 **Data-plane pin** (dry-tested 2026-11-07; diff = line 85 `distroless-v1.39.5@sha256:9d84a586…` -> `distroless-v1.40.2@sha256:09ca6f21…`):
```bash
sed -i '' 's#envoy:distroless-v1\.39\.5@sha256:9d84a586119a27b50437dbb01eccd4722832741539b1ed53c8e9d6da6067a6e0#envoy:distroless-v1.40.2@sha256:09ca6f2140a61ad8df11779a4a30d52b48433d444466328494f9188c9c35eded#' kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml
grep -c 'envoy:distroless-v1.40.2@sha256:09ca6f2140a61ad8df11779a4a30d52b48433d444466328494f9188c9c35eded' kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml   # 1
```
Also update the comment's `DefaultEnvoyProxyImage at v1.9.1` reference to `v1.10.0` (cosmetic).
Optional same commit: `docs/applications.md` line 225 "chart `gateway-helm` 1.9.2" -> "1.10.0"
(sweep finding F-dd4736a3 tracks that stale doc line; if included, the commit also closes it, see §3.4).

3.4 **Validate + commit** (shared worktree rules):
```bash
kubeconform -summary -ignore-missing-schemas kubernetes/apps/network/envoy-gateway/
PRE=$(git rev-parse HEAD); echo $PRE > /tmp/eg110-baseline/pre-sha.txt     # baseline = HEAD before the change
cat > /tmp/eg110-msg.txt <<EOF
feat(envoy-gateway): chart 1.9.3 -> 1.10.0 + re-vendor EG CRDs + data plane distroless-v1.39.5 -> v1.40.2

One change per auto-update-policy (*gateway-helm*, *envoyproxy/envoy*): EG 1.10 compiles
Envoy distroless-v1.40.2. Gateway API bundle unchanged (v1.6.1, header-only re-vendor);
EG CRDs additive only. Supersedes Renovate PR #496 (chart line only).
Plan: runbooks/maintenance/plans/envoy-gateway-1.10.0.md
Pre-change-HEAD: $PRE

<TRAILERS: paste the Co-Authored-By / Claude-Session lines EXACTLY as the attribution reminder given to the executing session
states them at execution time. Do not copy a model name from this plan; the planner's was a placeholder and may be stale.>
EOF
git commit --only kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml \
  kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml \
  kubernetes/apps/network/envoy-gateway/crds/gateway-api-standard.yaml \
  kubernetes/apps/network/envoy-gateway/crds/envoy-gateway.yaml -F /tmp/eg110-msg.txt
git log -1 --format=%s     # must be the subject above (EDITMSG race)
git show --stat HEAD       # exactly these 4 files (+ docs/applications.md if included)
SHA=$(git rev-parse HEAD); echo $SHA > /tmp/eg110-baseline/sha.txt      # the CHANGE commit (a commit cannot name its own SHA; the footer carries PRE)
git push
```

3.5 **Reconcile in SOP order** (the SOP calls for it: Kustomization then HelmRelease):
```bash
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization envoy-gateway-crds -n network      # wait: true; must be Ready
flux reconcile kustomization envoy-gateway -n network
flux reconcile helmrelease envoy-gateway -n network
kubectl rollout status deploy/envoy-gateway -n network --timeout=300s
kubectl rollout status deploy/envoy-internal -n network --timeout=600s
kubectl rollout status deploy/envoy-external -n network --timeout=600s
```
`rollout status` can green-light an OLD generation — §4.1 checks the live image digests, not this.
If `envoy-internal`/`envoy-external` do not roll within ~3 min of the controller being Ready,
check `kubectl get envoyproxy envoy-proxy-config -n network -o jsonpath='{.spec.provider.kubernetes.envoyDeployment.container.image}'`.

3.6 **DNS gate — k8s-gateway restart, TWICE** (docs/sops/envoy-gateway-upgrade.md; EG CRD
generations changed, so the header-only exception does not apply):
```bash
# $HI / $HE from §2.4. Why not `logs --tail=200 | grep`: k8s-gateway runs the CoreDNS `log` plugin, so a busy resolver writes one line per
# query and the startup/sync lines scroll out of a 200-line tail within seconds (measured 2026-11-15 on the live pod: the first lines of
# a 24h window were already query lines). A replayed failure line followed by 300 query lines read 0 through `--tail=200 | grep` (FALSE PASS).
# So: read the whole life of the fresh pods (--since after the restart), AND require a positive marker on the same stream.
for i in 1 2; do
  kubectl rollout restart deploy/k8s-gateway -n network
  kubectl rollout status deploy/k8s-gateway -n network --timeout=180s
  sleep 20
  N=$(kubectl get pods -n network -l app.kubernetes.io/name=k8s-gateway -o name | wc -l | tr -d ' '); echo "pods=$N"   # 3
  for k in 1 2 3 4 5 6; do dig +short @192.168.55.101 "$HI" >/dev/null; done      # generate marker traffic; the Service spreads it over the 3 pods
  L=$(for p in $(kubectl get pods -n network -l app.kubernetes.io/name=k8s-gateway -o name); do kubectl logs -n network $p --since=10m; done)
  echo "errs=$(echo "$L" | grep -ciE 'could not sync|failed to list|servfail')"        # 0
  echo "marker=$(echo "$L" | grep -F "$HI" | grep -c ' NOERROR ')"                    # >= 1 (measured pattern: `"A IN <host>. udp ..." NOERROR qr,aa`)
  dig +short @192.168.55.101 "$HI"; dig +short @192.168.55.101 "$HE"     # .103 then .104 — non-empty, exact VIPs
done
```
PASS per round = `pods=3` AND `errs=0` AND `marker>=1` AND exact VIPs. `marker=0` means the log stream was unread or the digs never reached
a pod: the `errs=0` beside it proves nothing, treat as FAIL and re-read. The 10-minute `--since` window is longer than any fresh pod's
life, so it covers startup sync through the dig; the previous round's pods are gone, so there is no carry-over.
REPLAYED 2026-11-15 on scratch logs (the SOP's recorded failure shape, docs/sops/k8s-gateway-dns.md:238): good sample `errs=0 marker=1`;
failure sample (`... plugin/k8s_gateway: Could not sync required resources` + a SERVFAIL query line) `errs=2 marker=0`; a stream with
no queries for `$HI` `errs=0 marker=0` (the case the marker exists to reject). The OLD gate on failure-line-plus-300-query-lines through
`--tail=200` printed `0`. The failure text is the one recorded in the 2026-08-15 outage (docs/sops/k8s-gateway-dns.md); any non-zero
`errs` or SERVFAIL/empty dig = §5 immediately.

## 4. Verification

4.1 **Live versions — contents, not rollout status.**
```bash
kubectl get pods -n network -l app.kubernetes.io/name=gateway-helm -o jsonpath='{range .items[*]}{.status.containerStatuses[0].image}{"\n"}{end}' | sort | uniq -c
#   3 docker.io/envoyproxy/gateway:v1.10.0
for d in envoy-internal envoy-external; do
  kubectl get pods -n network -l "gateway.envoyproxy.io/owning-gateway-name=$d" -o json | python3 -c "
import sys,json
for p in json.load(sys.stdin)['items']:
  print(p['metadata']['name'], p['status'].get('phase'), sorted((c['name'], c['imageID'].split('@')[-1][:19], c['ready']) for c in p['status'].get('containerStatuses',[])))"
done
```
PASS: 3+3 pods, each `envoy` imageID `sha256:09ca6f2140a6…` and `shutdown-manager` image
`v1.10.0`, all ready. FAIL shape: any `sha256:9d84a586…` (old ReplicaSet still serving) or
fewer than 3 rows per gateway.
CONTENTS ASSERTION: the data plane actually runs Envoy 1.40.2 — measured by the `envoy`
container imageID on all 6 proxy pods, compared to the target digest `09ca6f21…` (baseline `9d84a586…`).

4.2 **xDS accepted by the new data plane** (the documented cross-minor failure is SILENT
rejection with pods Ready):
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
# wait >= 2 scrape intervals after the last proxy pod went Ready
q 'count(envoy_server_live == 1)'                                                                    # ['6']
q 'sum(envoy_listener_manager_lds_update_rejected) + sum(envoy_cluster_manager_cds_update_rejected)'  # ['0']
q 'count(envoy_listener_manager_lds_update_success > 0)'                                             # ['6']
kill $PF 2>/dev/null
```
EXECUTOR: `q` is the §2.5 helper (EMPTY / no-data = `FAIL_EMPTY`/`FAIL_NO_DATA` = FAIL, never pass); re-define it in the new shell first.
`count(envoy_server_live == 1)` = 6 guards the rejection sum against reading 0 because the
series vanished (both read empty if the PodMonitor broke; `EMPTY` = FAIL, not pass). Measured
pre-change 2026-11-07: 6 series each, rejection sum 0.
CONTROL: metric envoy_server_live — count of live proxies must be exactly 6.
CONTROL: metric envoy_listener_manager_lds_update_rejected — sum must be 0 across all 6 new pods.
CONTROL: metric envoy_cluster_manager_cds_update_rejected — sum must be 0.
CONTROL: metric envoy_listener_manager_lds_update_success — >0 on all 6 (a proxy that never got a listener reads 0).

4.3 **Gateway API objects non-regressed** (compare with §2.3 files):
```bash
kubectl get gateway -n network -o jsonpath='{range .items[*]}{.metadata.name}={.status.conditions[?(@.type=="Programmed")].status} {end}'; echo   # both True
# re-run the §2.3 routes and policies one-liners into $B/routes.after.txt / $B/policies.after.txt
diff $B/routes.txt $B/routes.after.txt && echo ROUTES_SAME        # 93 0 []
diff $B/policies.txt $B/policies.after.txt && echo POLICIES_SAME  # all Accepted=True as before
```
A new condition type appearing in policies.after (e.g. a `Warning`) prints a diff: read it,
it is not automatically a failure, but `Accepted=False` on any row IS.
CONTENTS ASSERTION: every one of the 93 HTTPRoutes is still Accepted+ResolvedRefs and all 17
EG policies still Accepted — measured by the §2.3 one-liners, diffed against the pre-change baseline.

4.4 **Forward-auth still enforced (Authentik)** — the EG 1.7.0 ext-auth regression is why this
chart is held at all:
```bash
curl -sk -o /dev/null -w '%{http_code} %{redirect_url}\n' --resolve "$HI:443:192.168.55.103" "https://$HI/" | grep -c '^302 .*/application/o/authorize/'   # 1
```
FAIL shapes: `200` (auth bypassed — the policy is `failOpen: false`, so a 200 means the
filter is gone), `403`/`500` (ext-auth backend broken), or a 302 elsewhere. Then complete one
real login in Chrome on that host (operator present) and confirm the app page loads.
CONTENTS ASSERTION: an unauthenticated request to a protected host is redirected to the
Authentik authorize endpoint — measured by the curl above, baseline `302 …/application/o/authorize/` (2026-11-07).

4.5 **Public edge + DNS end-to-end**:
```bash
curl -sk -o /dev/null -w '%{http_code}\n' --resolve "$HE:443:192.168.55.104" "https://$HE/"   # 200 (baseline 200)
dig +short @192.168.55.101 "$HI"; dig +short @192.168.55.101 "$HE"                         # exact .103 / .104
```
Then, from outside the LAN (phone on mobile data), open one envoy-external host.
The blackbox DNS probes accept any 192.168.x.x answer, so the exact-VIP dig is the check, the
probe is the floor:
CONTROL: metric probe_success — `count(probe_success{probe_class="dns"} == 1)` must be 2 (both k8s-gateway probes).
CONTROL: alertname InternalDnsResolutionFailing — not firing.
CONTROL: alertname EnvoyGatewayPodNotReady — not firing.
CONTROL: alertname EnvoyGateway5xxSustained — not firing during a 10-minute soak.
CONTROL: alertname EnvoyGatewayMetricsAbsent — not firing (guards 4.2's metrics against vanishing).

4.6 **Rollback still admissible AFTER the change** (now the live CRDs are 1.10.0; the 1.9.3 files are the PRE-change commit's):
```bash
PRE=$(cat /tmp/eg110-baseline/pre-sha.txt)      # fallback if /tmp was lost: the `Pre-change-HEAD:` footer of the change commit
S=$(mktemp -d); for f in gateway-api-standard envoy-gateway; do git show "$PRE:kubernetes/apps/network/envoy-gateway/crds/$f.yaml" > $S/$f.yaml; done
n=$(( $(grep -c '^kind: ' $S/gateway-api-standard.yaml) + $(grep -c '^kind: ' $S/envoy-gateway.yaml) ))     # 20
kubectl apply --server-side --dry-run=server --force-conflicts --field-manager=eg110-dryrun -f $S/gateway-api-standard.yaml -f $S/envoy-gateway.yaml > $S/good.out 2>&1
echo "applied=$(grep -c 'serverside-applied (server dry run)' $S/good.out)/$n denied=$(grep -ciE 'denied|forbidden|error' $S/good.out)"   # 20/20 denied=0
sed 's/bundle-version: v1.6.1/bundle-version: v1.5.1/' $S/gateway-api-standard.yaml > $S/gw-bad.yaml
kubectl apply --server-side --dry-run=server --force-conflicts --field-manager=eg110-dryrun -f $S/gw-bad.yaml > $S/bad.out 2>&1
echo "control denied=$(grep -ciE 'denied|forbidden|error' $S/bad.out)"       # must be >= 1 (measured 10 on 2026-11-15); 0 = gate blind, STOP
```
PASS = `applied=20/20 denied=0` AND control `denied>=1`. Same gate and replay evidence as §2.7.

4.7 **Soak 10 min**, re-run 4.2 and 4.5. Close-out: set `status: executed`, delete this file
in the retire commit (README), and do the §6.4 bookkeeping.

## 5. Rollback

Trigger: any FAIL in §3.6 or §4.1-4.5, or user-visible routing/auth loss.

```bash
git log -3 --oneline                   # READ IT: a concurrent session may have committed after ours
SHA=$(git log -n1 --format=%H --grep='^feat(envoy-gateway): chart 1.9.3 -> 1.10.0')
test "$SHA" = "$(cat /tmp/eg110-baseline/sha.txt)" || echo "MISMATCH: /tmp file vs git log -- trust git log, check the Pre-change-HEAD footer"
git log --oneline "$SHA"..HEAD -- kubernetes/apps/network/envoy-gateway/     # must be EMPTY; if not, later edits touch the same files: revert by hand, not blind
git status --short kubernetes/apps/network/envoy-gateway/                    # must be clean before revert
git revert --no-edit "$SHA"            # one commit reverts chart + CRDs + data-plane pin together
git log -1 --format=%s                 # 'Revert "feat(envoy-gateway): chart 1.9.3 -> 1.10.0 …"'
git push
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization envoy-gateway-crds -n network
flux reconcile kustomization envoy-gateway -n network
flux reconcile helmrelease envoy-gateway -n network
kubectl rollout status deploy/envoy-gateway -n network --timeout=300s
kubectl rollout status deploy/envoy-internal -n network --timeout=600s
kubectl rollout status deploy/envoy-external -n network --timeout=600s
```
Why this works: §1.5 + §2.7/§4.6 dry-runs (the Gateway API bundle stays v1.6.1, so the VAP
admits the revert). If the revert's CRD apply is nevertheless denied by the VAP (it should
not be), follow the SOP's documented path: remove the VAP + binding from
`crds/gateway-api-standard.yaml` in a follow-up commit, reconcile, then re-apply the older CRDs.

If the HelmRelease is stuck (remediation retries exhausted): `flux suspend hr envoy-gateway -n network && flux resume hr envoy-gateway -n network` after the revert is in git.

Confirm back:
- `kubectl get deploy envoy-gateway -n network -o jsonpath='{.spec.template.spec.containers[0].image}'` = `docker.io/envoyproxy/gateway:v1.9.3`;
- §4.1 loop shows `envoy` imageID `sha256:9d84a586…` on 3+3 pods;
- `grep -h '^# Source: oci' kubernetes/apps/network/envoy-gateway/crds/*.yaml | sort -u` = `# Source: oci://docker.io/envoyproxy/gateway-crds-helm:1.9.3`;
- re-run §3.6 (DNS gate, twice — the EG CRD generations changed again) and §4.2-4.5.

The 1.39.5 image is digest-pinned, still published and cached on all 3 nodes. No data is at
risk; the cost of a rollback is a second proxy roll.

## 6. Interference notes

6.1 **Exclusive.** Every HTTP(S) request and every in-cluster name lookup crosses the surfaces
this plan rolls (both Gateways, the controller, and k8s-gateway twice). Do not co-schedule
anything; `exclusive: true`. With `talos-linux-1.14.5` (11-22) and `longhorn-1.13.0` (11-15)
already exclusive Sundays, and `redis-fleet-8.10.3` (11-29) / `flux-oci-chart-sources` (12-13)
in `conflicts_with`, the next free reboot-not-needed attended slot is the window agent's call
(85 min fits a sat-attended or sun-attended slot; NOT nightly — human-gated).

6.2 **PDB arithmetic.** envoy-gateway, envoy-internal, envoy-external, k8s-gateway each have
`minAvailable: 2` of 3 — one voluntary disruption each. A node drain during this plan would
compete for it; hence `talos-linux-1.14.5` in `conflicts_with`.

6.3 **Prometheus is the instrument** (§2.5, §4.2, §4.5). An open kube-prometheus-stack bump plan
EXISTS: `kube-prometheus-stack-93.3.0` (draft, exclusive; it already lists this plan). It is in
`conflicts_with`: never the same night, and never a window where either has run unverified, because
rolling Prometheus blanks every gate here (EMPTY reads as FAIL by §2.5's rule, which is the intended
outcome, not a flake). `kube-prometheus-stack-92.22.0` (coredns plan names it, sat-attended 12-12) is
the same class: re-read `maintenance-plan.py --open` at vet time for any other monitoring bump.

6.4 **Bookkeeping owed (not done by this planner — one-file rule):**
- `envoy-proxy-config-distroless-v1.40.2` and `-v1.40.0`: set `status: superseded`,
  `superseded_by: envoy-gateway-1.10.0`. Their UNBLOCK condition (EG v1.10.x with
  DefaultEnvoyProxyImage distroless-v1.40.x) is met by v1.10.0 = distroless-v1.40.2.
- Reciprocal `conflicts_with: envoy-gateway-1.10.0` on: talos-linux-1.14.5,
  flux-oci-chart-sources, helm-drift-detection, flux-reconciler-impersonation,
  etcd-timeouts-5000-500, redis-fleet-8.10.3, open-webui-0.13.0, tube-archivist-0.6.0
  (the three last ones already list the 1.40.x pin plans for the same reason), and **coredns-1.50.5**
  (checked 2026-11-15: it does NOT list this plan; the others of the new five -- kube-prometheus-stack-93.3.0,
  immich-server-3.4.1, nextcloud-9.4.3, postgres-fleet-18.7-bookworm -- already do).
- After execution, PR #496 closes as already-applied; if Renovate leaves it open, close it by hand referencing the commit.

6.5 **Repo corrections (for the operator / SOP owner, not acted on here):**
- `runbooks/auto-update-policy.yaml` `*gateway-helm*` reason says "a chart bump drags the
  Gateway API CRD channel with it". For 1.9.x -> 1.10.0 it does not (bundle v1.6.1 on both;
  matrix rows v1.9 and v1.10 both list Gateway API v1.6.1). The hold is still right (data
  plane minor + EG CRDs + only data plane), but the reason should say "MAY drag".
- `docs/sops/envoy-gateway-upgrade.md` header-only exception keys on BOTH vendored files.
  k8s_gateway informs only on `gateway.networking.k8s.io`; an `envoy-gateway.yaml`-only change
  cannot trigger the k8s-gateway failure mode. The exception could key on
  `gateway-api-standard.yaml` alone — this plan nonetheless runs the full gate as written.
- The SOP's Rollback section ("Assume git revert will NOT work") is true only when the
  Gateway API bundle-version moves; worth stating the condition so planners can establish
  the class instead of inheriting the worst case.
