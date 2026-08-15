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
status: blocked                     # 2026-08-15: foundation blocked. phase0 was attempted,
                                    # took ALL internal DNS down (k8s-gateway v1alpha2
                                    # informers vs Gateway API v1.5.1 CRDs), and was rolled
                                    # back. No phase can run until the DNS story is fixed.
                                    # LIKELY UNBLOCK (found 2026-08-15, after the rollback):
                                    # k8s_gateway upstream MOVED ORGS (ori-edge -> k8s-gateway);
                                    # new chart 3.7.2 / app 1.8.0 (2026-07-06) is built against
                                    # gateway-api v1.5.1 — the exact CRD set EG installs. The
                                    # "no upgrade exists" premise was an artifact of watching
                                    # the frozen old repo. Path: upgrade k8s-gateway first,
                                    # prove DNS healthy, THEN re-run phase0. Operator go/no-go.
window: null                          # 2026-08-15: the envoy chain is NO LONGER window work.
                                      # phase2 alone is est 120m and the largest window is 90m,
                                      # so it never fit; the 5 phases are strictly sequential,
                                      # which shuffling cannot fix. Operator decision: run the
                                      # migration as an ATTENDED PROJECT outside the window
                                      # system — which is what a 5-phase ingress migration
                                      # actually is. Do NOT schedule these into windows.
                                      # (previous value kept in git history)
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
