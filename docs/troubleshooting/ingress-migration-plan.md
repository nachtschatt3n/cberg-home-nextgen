# Ingress migration: ingress-nginx (EOL) → Envoy Gateway

**Decision date:** 2026-08-07 · **Status:** approved, Phase 0 queued
**Delete when:** migration complete (Phase 4 done, nginx decommissioned)

## Why

`kubernetes/ingress-nginx` reached EOL 2026-03-24 (repo archived at
controller-v1.15.1 — exactly what we run on both classes). 3 unfixable critical
CVEs on the image; no fixes will ever ship. InGate (successor) failed/retired;
Kubernetes' endorsed direction is Gateway API. The Chainguard-fork stopgap
(`runbooks/maintenance/plans/ingress-nginx-1.15.6.md`) needs a paid
subscription → **superseded**, kept as break-glass only.

Interim risk: **AR-055** (sweep policy DB) accepts the 3 CVEs, time-boxed —
hard review **2026-09-18**; escalates to the Chainguard contingency if the
external cutover hasn't happened by then.

## Decision

**Envoy Gateway ≥ v1.8.3** (pinned + held on the reviewed-update path — the
v1.7.0 ext-auth regression is the cautionary tale), template-style, staged
parallel-run. **Runner-up/fallback: Traefik Proxy OSS v3.7** — its
ingress-nginx annotation compat layer (85+ annotations incl. our auth set) is
a 1–2 session bail-out, pre-positioned at the Phase-1 pilot gate.

Scored 5 candidates against the measured migration surface (102 Ingresses,
24 nginx annotation keys, 13 snippet users, 10 authentik forward-auth apps,
homepage discovery, cloudflared tunnel, Cilium v1.20): EG ≈4.4, Traefik ≈4.3,
kgateway ≈3.4, Istio ≈3.1 (mesh weight unjustified), Cilium-GW ≈2.8 (welds
ingress to CNI upgrades; ExternalAuth too new). Full analysis in the planning
session 2026-08-07; key EG wins: exact home-ops reference alignment (template
runs Cilium+EG+cert-manager+cloudflared today — manifests port nearly
copy-paste), Gateway API destination architecture, verified answers for every
real usage (SecurityPolicy ext-auth w/ authentik `/auth/envoy`, Brotli via
BackendTrafficPolicy, CF-Connecting-IP via ClientTrafficPolicy
clientIPDetection, wazuh/kibana HTTPS backends via Backend+skip-verify,
gethomepage `kubernetes.gateway: true` HTTPRoute discovery).

### Measured facts that shrink the job

- The "13 snippets" decompose: 10× identical `auth-snippet` one-liner
  (vanishes with ext-auth), 2× the same five security headers
  (→ ResponseHeaderModifier), **1 real item**: langfuse
  `proxy_cookie_path` — no equivalent on EG *or* Traefik → app-side fix
  (NextAuth cookie env) or a ~10-line Lua filter (EnvoyExtensionPolicy).
- ~60 apps are bjw-s app-template → `ingress:` → `route:` values swap
  (mechanical; route syntax survives the separate 3.7.3→5.x chart plan).
- k8s-gateway supports watching HTTPRoute (per-app DNS flips automatically);
  external-dns has a `gateway-httproute` source (template uses it);
  cert-manager wildcard secret plugs into Gateway listeners directly.
- cloudflared's ordered per-hostname rules = free per-app canary for the
  external cutover; wildcard flip is one revertible commit.
- Brotli/OCSP/real-IP live in controller values, not per-ingress — converts
  once. **OCSP is moot** (Let's Encrypt shut its OCSP responders) — drop it.
- Dead-weight annotations needing no port: enable-websocket,
  websocket-services, priority; most body-size/buffering (Envoy streams by
  default).

### Scope exclusions

- **L4 stays on Cilium LB-IPAM** (mosquitto, plex, HA-CoAP, adguard DNS,
  wazuh-syslog, traccar, …): gateways add nothing (Traefik lacks UDPRoute;
  EG's TCP/UDPRoute solves no problem LB-IPAM doesn't) and would couple L4
  availability to the gateway. Explicitly out of scope.
- **hostNetwork apps (music-assistant, home-assistant, esphome,
  matter-server, otbr) are a SEPARATE track** — their issue is
  multicast/mDNS discovery, which NO gateway routes. Fix is Multus + macvlan
  (static IP+MAC, `sbr`, VLAN-30 leg preferred — the onedr0p home-ops
  pattern; Talos ships macvlan natively, Cilium already `cni.exclusive:
  false`). Per-app: MA + HA → macvlan; esphome → plain pod network (ping
  status, `use_address`); matter-server → keep hostNetwork for now
  (macvlan possible but upstream-unsupported); otbr → keep (it IS a router;
  replicas: 0 pending SLZB RMA). Independent sequencing; own plan when
  picked up.

## Phases (each = maintenance-window work, operator-gated)

- **P0 — Foundation** (1 session, zero traffic impact): Gateway API CRDs;
  EG HelmRelease pinned ≥1.8.3 + auto-update deny rule; GatewayClass +
  EnvoyProxy params; Gateways `envoy-internal` (lbipam .103) /
  `envoy-external` (.104); ClientTrafficPolicy (internal XFF-trust /
  external CF-Connecting-IP), BackendTrafficPolicy (brotli+gzip),
  https-redirect route; k8s-gateway watchedResources += HTTPRoute;
  external-dns sources += gateway-httproute; homepage
  `kubernetes.gateway: true` + gateway RBAC. Plan:
  `runbooks/maintenance/plans/envoy-gateway-phase0.md`.
- **P1 — Pilots = go/no-go gate** (1 session): echo (plain), headlamp
  (forward-auth: HTTPRoute + outpost HTTPRoute w/ cross-ns backendRef +
  ReferenceGrant + SecurityPolicy extAuth → `/outpost.goauthentik.io/auth/envoy`;
  authentik provider mode nginx→envoy per app, reversible), homepage
  discovery (hard-requirement gate — flakiness reports exist).
  **No-go → Traefik fallback; nothing user-facing changed.**
- **P2 — Internal bulk** (~76 objects, 2–3 sessions), batch-per-namespace,
  one commit each. Hardening milestone when last snippet consumer converts:
  `allow-snippet-annotations: false` on both nginx HRs (neutralizes the
  injection-CVE class before migration ends). langfuse converts here w/
  app-side cookie fix + explicit OAuth test.
- **P3 — External + tunnel** (~26 objects, 1–2 sessions): HTTPRoutes on
  envoy-external; per-hostname cloudflared canaries (incl. authentik itself
  + one auth'd app + nextcloud websockets), soak, then wildcard flip
  (rollback = revert 1 commit).
- **P4 — Decommission** (1 session): delete nginx HRs/classes, ExternalName
  outpost services, `*-authentik-outpost` Ingresses; prune external-dns/
  k8s-gateway Ingress sources; keep .103/.104 (less churn); confirm Trivy
  findings gone + disable AR-055; update docs (network, applications,
  new-deployment-blueprint → HTTPRoute pattern, homepage SOP).

**Effort:** ~6–8 attended sessions ≈ 3–6 weeks at 4 windows/week.
**Highest-risk moments:** P1 auth pilot, langfuse OAuth, wildcard flip —
each individually revertible. Never co-schedule with cloudflared /
cert-manager / authentik plans.

## References

- onedr0p home-ops / cluster-template `network/envoy-gateway` (reference
  manifests: GatewayNamespace deploy type, cloudflared →
  `envoy-external.network.svc:443` w/ originServerName + http2Origin)
- authentik forward-auth docs (envoy) + James Wynn walkthrough (Feb 2026)
- EG v1.7.0 ext-auth regression: envoyproxy/gateway#8202 (why we pin+hold)
- gethomepage k8s gateway discovery + discussion #5969 (pilot gate)
- CNCF's own ingress-nginx→EG migration (Apr 2026)
