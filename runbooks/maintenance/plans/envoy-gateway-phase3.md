---
plan_id: envoy-gateway-phase3
component: envoy-gateway
pr: null
kind: migration-cutover             # Phase 3: external apps + Cloudflare tunnel flip
current: "external apps on ingress-nginx (cloudflared wildcard -> nginx)"
target: "external apps on HTTPRoute/envoy-external; cloudflared wildcard -> envoy-external"
update_type: migration
risk: high                          # the external cutover touches the Cloudflare
                                    # tunnel path serving ~26 public apps; per-
                                    # hostname canaries first, wildcard flip last
                                    # (one revertible commit)
est_duration_min: 90
needs_reboot: false
touches:
  namespaces: [network, all-external]
  resources:
    - "~26 external Ingress -> HTTPRoute on envoy-external"
    - "cloudflared config.yaml: per-hostname canary rules, then wildcard flip"
    - "external-dns target annotations carried to HTTPRoutes"
    - "uptime-kuma forward-auth pair on envoy-external"
  shared: [cloudflared, auth]       # SOLO-ish window: no other plan may touch
                                    # cloudflared/cert-manager/authentik; avoid
                                    # co-scheduling app plans whose verification
                                    # is via public ingress
depends_on: [envoy-gateway-phase2]
conflicts_with: [app-template-5.0]  # don't run an app-template tier in this window
status: scheduled
window: "sun-window:2026-08-30"     # weekend, operator-present; canaries soak from
                                    # commits earlier in the week if desired
auto_execute: false
sops_refs:
  - docs/troubleshooting/ingress-migration-plan.md
generated: "2026-08-07"
---

# Envoy Gateway — Phase 3: external + tunnel cutover

Per decision doc §P3: (1) convert external apps to HTTPRoutes on
`envoy-external` (public DNS unchanged — everything CNAMEs to
external.${SECRET_DOMAIN} → tunnel). (2) cloudflared ordered per-hostname
canaries → `https://envoy-external.network.svc:443` (originServerName +
http2Origin) above the wildcard→nginx rule; canaries MUST include authentik's
own hostname (verify SSO before anything else), one forward-auth app, and
nextcloud (websockets). Soak. (3) Wildcard flip = one commit; **rollback =
revert that commit** (seconds). (4) Move the `dependsOn: cloudflared`
ordering from the external nginx HR to the EG ks.

Verify: every canary hostname serves + authenticates; after flip, spot-check
10 public apps + SAML (wazuh) + Alexa music-stream path; 0 firing alerts;
Kuma all green (69 monitors are the real external verification fleet).
