---
plan_id: envoy-gateway-phase1
component: envoy-gateway
pr: null
kind: migration-pilot               # Phase 1 of the ingress migration: the go/no-go gate
current: "EG installed, 0 routes (post phase0)"
target: "3 pilots proven: plain route, authentik ext-auth, homepage discovery"
update_type: pilot
risk: medium                        # touches ONE authentik provider (headlamp) +
                                    # homepage values; both per-app reversible.
                                    # No other app moves.
est_duration_min: 60
needs_reboot: false
touches:
  namespaces: [network, kube-system, default, monitoring]
  resources:
    - "httproute/echo-server (NEW; its Ingress removed same commit)"
    - "httproute/headlamp + httproute headlamp-outpost (NEW)"
    - "securitypolicy/headlamp (NEW, extAuth -> ak-outpost-headlamp)"
    - "referencegrant in kube-system (NEW, cross-ns backendRef to outpost svc)"
    - "authentik proxy provider 'headlamp': mode nginx->envoy forward-auth"
    - "helmrelease/homepage (gateway discovery verification)"
  shared: [auth]                    # only the HEADLAMP provider is touched, but a
                                    # mistake in the SecurityPolicy pattern informs
                                    # all later conversions — treat auth blips on
                                    # headlamp as expected during the window
depends_on: [envoy-gateway-phase0]
conflicts_with: []                  # never same window as authentik/cloudflared/
                                    # cert-manager plans (migration house rule)
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
                                    # window-agent: run only if phase0 verified clean;
                                    # defer to sun-window:2026-08-16 on time overrun
auto_execute: false
sops_refs:
  - docs/troubleshooting/ingress-migration-plan.md
  - docs/sops/authentik.md
generated: "2026-08-07"
---

# Envoy Gateway — Phase 1 pilots (the go/no-go gate)

## 1. Summary & why

Three pilots prove the load-bearing mechanics before any bulk conversion.
**A failure here = NO-GO → Traefik fallback decision** (decision doc §fallback)
with nothing user-facing changed beyond the two pilot apps (both reverted).

- **Pilot A (plain):** echo-server Ingress → HTTPRoute on `envoy-internal`.
  Gate: k8s-gateway auto-resolves the host to 192.168.55.103 once the Ingress
  is gone; app serves via EG.
- **Pilot B (forward-auth):** headlamp (internal, low blast radius):
  app HTTPRoute + separate HTTPRoute for `/outpost.goauthentik.io` with
  cross-ns backendRef → `ak-outpost-headlamp-forward-auth.kube-system:9000`
  (+ ReferenceGrant) + SecurityPolicy `extAuth.http` →
  `/outpost.goauthentik.io/auth/envoy`, `headersToBackend` = existing
  auth-response-headers list, `failOpen: false`. Authentik side: switch ONLY
  the headlamp proxy provider nginx→envoy mode (blueprint/configmap change,
  reversible). Gate: full redirect → login → callback → header-injection loop.
- **Pilot C (homepage discovery):** move `gethomepage.dev/*` annotations onto
  the pilot HTTPRoutes (same commit as each Ingress removal — no double
  discovery). Gate: tiles appear + widgets work with `kubernetes.gateway: true`
  (flakiness reports exist upstream — this is exactly what we're testing).

## 2. Pre-checks

```bash
# phase0 landed: gateways Programmed on .103/.104, EG healthy, 0 firing alerts
mise exec -- kubectl get gateway -n network
mise exec -- kubectl get pods -n network | grep envoy
# headlamp + echo currently healthy through nginx (baseline)
mise exec -- kubectl get ingress -A | grep -E "echo|headlamp"
# interactive baseline: headlamp SSO round-trip via nginx works RIGHT NOW
# authentik healthy (server 3/3, blueprints errored count unchanged)
mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik | head -4
```

## 3. Steps (GitOps; cberg-agent for manifests; ak provider change via blueprint)

1. Pilot A: echo-server commit (HTTPRoute + delete Ingress + homepage
   annotations move). Verify gate A.
2. Pilot B: headlamp commit (routes + ReferenceGrant + SecurityPolicy +
   authentik provider mode switch). Verify gate B interactively.
3. Pilot C: verify homepage tiles for both pilots; check homepage logs for
   discovery errors.
4. Record results in docs/troubleshooting/ingress-migration-plan.md (gate
   outcomes + any pattern corrections for the P2 bulk).

## 4. Verification

- A: `curl` echo host resolves to .103 (k8s-gateway) and serves 200 via EG.
- B: browser SSO loop on headlamp: redirect to auth.<domain>, login, land
  back authenticated; `X-authentik-*` headers present at the app; a second
  browser (no session) is blocked (failOpen=false honored).
- C: homepage shows both tiles, no duplicates, widgets live.
- Cluster-wide: 0 firing alerts; all other ingresses untouched (spot-check 3).

## 5. Rollback (per pilot, independent)

`git revert` the pilot commit → Ingress returns, k8s-gateway flips DNS back
(TTL 60); for headlamp also revert the authentik provider mode to nginx
(blueprint revert in same commit). EG stack itself stays (phase0 scope).

## 6. Interference notes

- Only headlamp's auth is at risk; all other forward-auth apps stay on nginx
  outposts untouched. Expected: brief headlamp auth blips during the switch.
- Do NOT proceed to Phase 2 in this window regardless of time remaining —
  gate results need operator review (go/no-go is the whole point).
- Same-window sequencing (operator choice 2026-08-07): app-template canary +
  phase0 + phase1 = capacity 6/6, ~duration-tight. Order: app-template canary
  (its own plan) / phase0 / phase1 last; phase1 defers to sun-window:2026-08-16
  if the window overruns. Phase1 MUST NOT start unless phase0 verification
  passed in full.
