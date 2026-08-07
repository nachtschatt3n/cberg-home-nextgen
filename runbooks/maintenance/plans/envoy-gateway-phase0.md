---
plan_id: envoy-gateway-phase0
component: envoy-gateway
pr: null                            # greenfield deploy — no Renovate PR
kind: deploy                        # new component (Phase 0 of the ingress migration)
current: "none"
target: "envoy-gateway v1.8.3+ (chart oci://docker.io/envoyproxy/gateway-helm)"
update_type: install
risk: low                           # PARALLEL-RUN: no existing traffic touched;
                                    # ingress-nginx keeps serving everything.
                                    # New Gateways sit on fresh LB IPs (.103/.104)
                                    # that nothing references yet.
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
    - helmrelease/k8s-gateway            # watchedResources += HTTPRoute
    - helmrelease/external-dns           # sources += gateway-httproute
    - helmrelease/homepage               # kubernetes.gateway: true + RBAC
    - "certificate (wildcard duplicate into network ns)"
  shared: []                        # nothing routes through the new gateways yet;
                                    # k8s-gateway/external-dns/homepage changes are
                                    # additive (existing Ingress sources retained)
depends_on: []
conflicts_with: []                  # do not co-schedule with cloudflared/cert-manager
                                    # plans as a general rule for this migration
status: scheduled                   # operator-scheduled 2026-08-07
window: "sat-early:2026-08-15"      # with app-template canary (cap-fit 6/6) + phase1 if time allows; window-agent sequences: P0 before P1, defer P1 to sun-08-16 on overrun
                                    # alongside light plans (risk weight 1)
auto_execute: false                 # new infra component → operator go/no-go
sops_refs:
  - docs/troubleshooting/ingress-migration-plan.md
  - docs/sops/maintenance-windows.md
generated: "2026-08-07"
---

# Envoy Gateway — Phase 0 foundation (parallel-run, zero traffic impact)

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
   - k8s-gateway: `watchedResources: ["Ingress","Service","HTTPRoute"]`
   - external-dns: sources += `gateway-httproute` (keep `ingress`)
   - homepage: `kubernetes.gateway: true` + ClusterRole read on
     `gateway.networking.k8s.io` (httproutes, gateways)
4. Commit, push, reconcile.

## 4. Verification

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
