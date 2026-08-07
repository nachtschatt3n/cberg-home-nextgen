---
plan_id: envoy-gateway-phase4
component: envoy-gateway
pr: null
kind: migration-decommission        # Phase 4: remove ingress-nginx + tidy
current: "nginx idle (0 routes), EG serving everything"
target: "ingress-nginx removed; docs/AR closed out"
update_type: decommission
risk: low                           # nginx serves nothing by now; deletion is
                                    # the low-drama end state
est_duration_min: 60
needs_reboot: false
touches:
  namespaces: [network, kube-system]
  resources:
    - "delete both ingress-nginx HelmReleases + IngressClasses + HelmRepository"
    - "delete ExternalName outpost services + *-authentik-outpost Ingress remnants"
    - "external-dns: drop ingress source; k8s-gateway: drop Ingress watch"
    - "docs: network.md, applications.md, new-deployment-blueprint.md -> HTTPRoute"
    - "AR-055: disable (CVEs gone with the images)"
  shared: []
depends_on: [envoy-gateway-phase3]
conflicts_with: []
status: scheduled
window: "tue-early:2026-09-01"
auto_execute: false
sops_refs:
  - docs/troubleshooting/ingress-migration-plan.md
generated: "2026-08-07"
---

# Envoy Gateway — Phase 4: decommission + close-out

Per decision doc §P4. Pre-check: zero Ingress objects reference the nginx
classes; nginx controller request rate ~0 over 48h (Prometheus). Then delete
the nginx stack, prune the ecosystem sources, keep gateways on .103/.104
(update docs), confirm the fleet Trivy scan no longer reports the v1.15.1
CVEs, `policy-cli.py risk disable AR-055`, update the new-deployment
blueprint to the HTTPRoute pattern (else new apps regress), and DELETE
`docs/troubleshooting/ingress-migration-plan.md` (migration complete — per
docs lifecycle rules). Rollback: git revert restores nginx HRs (harmless
while routes remain on EG).
