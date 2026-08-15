---
plan_id: envoy-gateway-phase0
component: envoy-gateway
pr: null                            # greenfield deploy — no Renovate PR
kind: deploy                        # new component (Phase 0 of the ingress migration)
current: "none"
target: "envoy-gateway v1.8.3+ (chart oci://docker.io/envoyproxy/gateway-helm)"
update_type: install
risk: high                          # was "low" (parallel-run rationale) — DISPROVEN
                                    # 2026-08-15: measured blast radius was ALL
                                    # internal DNS, latent until the next
                                    # k8s-gateway pod restart. See §0.
est_duration_min: 60
needs_reboot: false
touches:
  namespaces: [network, kube-system, monitoring]
  resources:
    - "crds/gateway.networking.k8s.io (NEW, standard channel)"
    - helmrelease/envoy-gateway (NEW)
    - "gatewayclass/envoy + envoyproxy params (NEW)"
    - "gateway/envoy-internal (.103) + gateway/envoy-external (.104) (NEW)"
    - "clienttrafficpolicy + backendtrafficpolicy + https-redirect route (NEW)"
    - helmrelease/k8s-gateway            # (WITHDRAWN — see §0 blocker)
    - helmrelease/external-dns           # sources += gateway-httproute
    - helmrelease/homepage               # kubernetes.gateway: true + RBAC
    - "certificate (wildcard duplicate into network ns)"
  shared: []                        # nothing routes through the new gateways yet;
                                    # k8s-gateway/external-dns/homepage changes are
                                    # additive (existing Ingress sources retained)
depends_on: []
conflicts_with: []                  # do not co-schedule with cloudflared/cert-manager
                                    # plans as a general rule for this migration
status: blocked                     # 2026-08-15: ATTEMPTED AND ROLLED BACK.
                                    # Gateway API CRDs are incompatible with k8s-gateway
                                    # 0.4.0 (our internal split-horizon DNS) — see
                                    # "Blocker" below. Needs an operator decision on
                                    # internal DNS before phase 0 can land.
window: null                          # 2026-08-15: the envoy chain is NO LONGER window work.
                                      # phase2 alone is est 120m and the largest window is 90m,
                                      # so it never fit; the 5 phases are strictly sequential,
                                      # which shuffling cannot fix. Operator decision: run the
                                      # migration as an ATTENDED PROJECT outside the window
                                      # system — which is what a 5-phase ingress migration
                                      # actually is. Do NOT schedule these into windows.
                                      # (previous value kept in git history)
auto_execute: false                 # new infra component → operator go/no-go
sops_refs:
  - docs/troubleshooting/ingress-migration-plan.md
  - docs/sops/maintenance-windows.md
generated: "2026-08-07"
---

# Envoy Gateway — Phase 0 foundation (parallel-run, zero traffic impact)

## 0. BLOCKER — attempted 2026-08-15, rolled back

Everything in this plan installed and worked. It was rolled back anyway,
because installing the Gateway API CRDs **takes internal DNS down completely**.

`k8s-gateway` (CoreDNS `k8s_gateway` plugin **v0.4.0**, chart 2.4.0 — the
newest published; there is no upgrade) starts informers for the Gateway API
route family **as soon as any Gateway API CRD exists in the cluster**, and it
asks for them at **v1alpha2**:

```
failed to list *v1alpha2.GRPCRoute: the server could not find the requested resource
failed to list *v1alpha2.TLSRoute:  the server could not find the requested resource
```

In Gateway API v1.5.1 (what EG 1.8.3 requires) `GRPCRoute` serves only `v1`,
and `TLSRoute`'s `v1alpha2` is present but `served: false`. The informers never
sync, and the plugin then **fails closed for every name it serves** — including
the 102 Ingress-backed hosts that have nothing to do with Gateway API:

```
[ERROR] plugin/errors: 2 <host>. A: plugin/k8s_gateway: Could not sync required resources
```

Measured impact: every `*.${SECRET_DOMAIN}` lookup against 192.168.55.101
returned empty. Confirmed this is **not** the `watchedResources` setting and
**not** RBAC — reverting `watchedResources` to `["Ingress","Service"]` did not
help (the fresh pod failed identically), and the chart already grants
`gateway.networking.k8s.io/*`. The trigger is the presence of the CRDs alone.

**This blocks the whole migration, not just phase 0.** The plan in
`docs/troubleshooting/ingress-migration-plan.md` assumes "k8s-gateway supports
watching HTTPRoute (per-app DNS flips automatically)". That assumption is false
at the versions we run, and it fails in the worst possible direction: not
"HTTPRoutes are invisible to DNS" but "all internal DNS stops".

### The failure is LATENT — this is the dangerous part

The CRDs went in at 14:33Z and internal DNS kept working perfectly until
14:46Z. It only broke when the k8s-gateway **pod restarted** (my ecosystem-prep
change happened to restart it). The running pod had established its informers
*before* the CRDs existed, so it never tried the v1alpha2 types; a pod that
*starts* with the CRDs present fails immediately and permanently.

Measured: at 14:45Z, with all 16 Gateway API/EG CRDs installed and both
gateways programmed, every internal host still resolved correctly.

**Consequence: phase 0 exactly as written would have passed every verification
test in this plan and left a cluster-wide internal-DNS time bomb** armed to go
off at the next k8s-gateway pod restart — a node reboot, an eviction, a
descheduler move, a chart bump, anything, quite possibly days later and with no
apparent connection to the gateway work. The only reason it surfaced during
execution is that step 3 (`watchedResources`) restarted the pod while I was
still watching.

Any re-attempt must therefore **explicitly restart k8s-gateway and re-verify
DNS** as a gate, rather than trusting that DNS still works after the CRDs land.

### Operator decision needed before re-attempting

Pick the internal split-horizon DNS story first, then redo phase 0:

1. **Replace k8s-gateway.** Its upstream looks stalled (app 0.4.0 across chart
   2.1.0-2.4.0, client-go 0.28.3, CoreDNS 1.11.1). Candidates: external-dns
   with an internal provider writing into AdGuard, or per-app `DNSEndpoint`
   CRs, or CoreDNS with explicit rewrites.
2. **AdGuard wildcard rewrites** — `*.${SECRET_DOMAIN}` -> 192.168.55.100 with
   per-host exceptions for the 26 external hosts. Simple, but hand-maintained
   and it loses the automatic per-app flip the migration relies on.
3. **Fork/patch k8s_gateway** to use `v1` routes. Small Go change, but it makes
   us the maintainer of a DNS-critical component.
4. **Abandon EG for Traefik** (the pre-positioned fallback) — but verify first,
   because the trigger is the Gateway API CRDs themselves, and Traefik's
   Gateway API mode would install the same CRDs. Traefik in *Ingress* mode
   would sidestep it entirely.

Nothing else in this plan needs to change: EG 1.8.3 installed cleanly, both
gateways programmed on .103/.104 with the wildcard cert, https-redirect worked,
and no existing Ingress was affected. See the phase-0 execution notes in
`docs/troubleshooting/ingress-migration-plan.md` for the other findings
(vendored CRDs, externalTrafficPolicy, topology injector) — those stay valid.


## 1. Summary & why

First phase of the approved ingress-nginx→Envoy Gateway migration
(`docs/troubleshooting/ingress-migration-plan.md`). Installs the Gateway API
CRDs + Envoy Gateway ≥1.8.3 + two Gateways on **fresh LB IPs**
(`envoy-internal` 192.168.55.103, `envoy-external` .104) plus the global
policy parity objects. **No existing Ingress/traffic is touched** —
ingress-nginx continues serving 100% of traffic until Phase 2+. Blast radius
of a total failure here = the new, unused gateways don't come up.

Crib the manifests from onedr0p cluster-template
`kubernetes/apps/network/envoy-gateway/` (GatewayNamespace deploy type,
lbipam annotations, ClientTrafficPolicy/BackendTrafficPolicy patterns).

## 2. Pre-checks

```bash
# LB IPs .103/.104 free in the Cilium pool and unclaimed
mise exec -- kubectl get svc -A -o wide | grep -E "55\.10[34]" || echo "free"
# Cilium healthy; L2 announcements working (existing LBs answer)
mise exec -- kubectl get pods -n kube-system -l k8s-app=cilium
# Gateway API CRDs NOT already present (clean install)
mise exec -- kubectl get crd | grep gateway.networking.k8s.io || echo "clean"
# wildcard cert secret exists (cert-manager)
mise exec -- kubectl get secret -n network 2>/dev/null | grep production-tls || \
  mise exec -- kubectl get certificate -A | grep production
# no in-flight reconciles, 0 firing alerts (standard gate)
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3. Steps (GitOps; cberg-agent does the manifest work)

1. New ks `kubernetes/apps/network/envoy-gateway/` (CRDs sub-ks first,
   `dependsOn` for the app):
   a. Gateway API CRDs (standard channel; EG's gateway-crds chart or vendored).
   b. HelmRelease `envoy-gateway` **v1.8.3+ pinned**, values:
      `config.envoyGateway.provider.kubernetes.deploy.type: GatewayNamespace`.
   c. GatewayClass `envoy` + EnvoyProxy params (replicas 1, 100m/1Gi,
      PodMonitor).
   d. Gateways `envoy-internal` / `envoy-external` with
      `lbipam.cilium.io/ips: 192.168.55.103|104`, HTTP+HTTPS listeners,
      `allowedRoutes.namespaces.from: All`, certificateRefs → wildcard secret;
      duplicate wildcard Certificate into `network` ns.
   e. ClientTrafficPolicy per gateway (internal: trust pod/VLAN CIDRs XFF;
      external: `clientIPDetection.customHeader: CF-Connecting-IP`),
      BackendTrafficPolicy (brotli+gzip compression), https-redirect
      HTTPRoute on both http listeners.
2. Add `*envoy-gateway*` deny rule to `runbooks/auto-update-policy.yaml`
   (reason: ext-auth regressions — v1.7.0 broke redirect auth; reviewed
   bumps only).
3. Ecosystem prep (additive, keep Ingress sources):
   - ~~k8s-gateway: `watchedResources: ["Ingress","Service","HTTPRoute"]`~~
     **DO NOT** — this is the step that killed internal DNS (see §0); the
     HelmRelease now carries a guard comment. Internal DNS for HTTPRoutes
     needs the §0 operator decision first.
   - external-dns: sources += `gateway-httproute` (keep `ingress`)
   - homepage: `kubernetes.gateway: true` + ClusterRole read on
     `gateway.networking.k8s.io` (httproutes, gateways)
4. Commit, push, reconcile.

## 4. Verification

**MANDATORY extra gate (lesson of §0): after the CRDs land, restart
k8s-gateway and re-verify internal DNS.** A pod that was running before the
CRDs existed keeps resolving; only a freshly started pod hits the informer
failure. DNS working after CRD install proves nothing.

```bash
# the restart-and-verify gate
mise exec -- kubectl rollout restart deploy/k8s-gateway -n network
mise exec -- kubectl rollout status deploy/k8s-gateway -n network --timeout=120s
mise exec -- dig +short @192.168.55.101 <any-ingress-host> A   # MUST answer
```

```bash
# EG control plane up; both Gateways Programmed=True with their IPs
mise exec -- kubectl get gateway -n network
mise exec -- kubectl get pods -n network | grep envoy
# LB IPs answer via L2 and serve the wildcard cert
curl -sk --resolve test.${SECRET_DOMAIN}:443:192.168.55.103 \
  https://test.${SECRET_DOMAIN}/ -o /dev/null -w '%{http_code} ' \
  && echo "(404/503 from EG = OK, no routes yet)"
openssl s_client -connect 192.168.55.103:443 -servername test.${SECRET_DOMAIN} \
  </dev/null 2>/dev/null | openssl x509 -noout -subject
# nothing regressed: existing ingress traffic + homepage + internal DNS fine
mise exec -- flux get hr -A | awk 'NR==1 || $5!="True"'
# k8s-gateway/external-dns/homepage still healthy after their value changes
mise exec -- kubectl get pods -n network | grep -E "k8s-gateway|external-dns"
```

Success = Gateways Programmed on .103/.104 serving the wildcard cert, EG pods
healthy, zero change to existing ingress behavior, 0 firing alerts.

## 5. Rollback

Nothing depends on the new stack: `git revert` the commit(s) → Flux prunes the
ks (EG, Gateways, CRDs). Revert the k8s-gateway/external-dns/homepage value
additions in the same revert. Existing traffic never moved, so rollback is
invisible to users. (If CRD deletion sticks on finalizers, delete Gateway/
HTTPRoute objects first, then CRDs.)

## 6. Interference notes

- **Parallel-run by design** — no shared surface with running traffic; risk
  weight 1. Safe to co-schedule with unrelated app plans; still avoid
  cloudflared/cert-manager/authentik plans in the same window (migration
  house rule).
- The k8s-gateway/external-dns/homepage edits are additive but DO restart
  those pods — brief (<30s) blips in internal DNS resolution / dashboard.
  Not user-visible in practice; note in the window log.
- Phase 1 (pilots incl. authentik ext-auth + homepage discovery gates) is a
  SEPARATE plan (envoy-gateway-phase1.md). Operator decision 2026-08-07: both
  run in sat-early:2026-08-15 — phase1 starts ONLY after phase0 verification
  passes in full, and defers to sun-window:2026-08-16 on time overrun.
