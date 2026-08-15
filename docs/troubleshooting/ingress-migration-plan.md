# Ingress migration: ingress-nginx (EOL) → Envoy Gateway

**Decision date:** 2026-08-07 · **Status:** BLOCKED at Phase 0 (2026-08-15) — internal-DNS prerequisite unresolved, see §Phase 0 execution notes
**Delete when:** migration complete (Phase 4 done, nginx decommissioned)

## Why

`kubernetes/ingress-nginx` reached EOL 2026-03-24 (repo archived at
controller-v1.15.1 — exactly what we run on both classes). The image carries
criticals for which no fix will ever ship (driver: **F-35f34061**; detail is
DB-only per `docs/sops/vulnerability-disclosure.md`). InGate (successor)
failed/retired;
Kubernetes' endorsed direction is Gateway API. The Chainguard-fork stopgap
(`runbooks/maintenance/plans/ingress-nginx-1.15.6.md`) needs a paid
subscription → **superseded**, kept as break-glass only.

Interim risk: **AR-055** (sweep policy DB) accepts F-35f34061, time-boxed —
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
  (→ ResponseHeaderModifier). The one genuinely hard item was langfuse's
  `proxy_cookie_path` (no equivalent on EG *or* Traefik), but **langfuse was
  removed from the cluster on 2026-08-13** — that item is gone, and with it
  the need for an app-side NextAuth cookie fix or a Lua EnvoyExtensionPolicy.
- ~60 apps are bjw-s app-template → `ingress:` → `route:` values swap
  (mechanical; route syntax survives the separate 3.7.3→5.x chart plan).
- ~~k8s-gateway supports watching HTTPRoute (per-app DNS flips automatically)~~
  **FALSE — measured 2026-08-15:** k8s_gateway v0.4.0 fails closed for ALL names
  once any Gateway API CRD exists (see §Phase 0 execution notes). The per-app
  DNS flip is unsolved and is the blocking prerequisite for the migration;
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
  injection-vulnerability class before migration ends). No snippet consumer needs an
  app-side workaround any more (langfuse, the only one, is gone).
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
**Highest-risk moments:** P1 auth pilot, wildcard flip — each individually
revertible. (langfuse OAuth was the third; removed with the app 2026-08-13.) Never co-schedule with cloudflared /
cert-manager / authentik plans.

## Phase 0 execution notes (2026-08-15)

**Phase 0 was attempted, verified working, and then ROLLED BACK.** The migration
is blocked on internal DNS — see the blocker below and
`runbooks/maintenance/plans/envoy-gateway-phase0.md` (status: blocked).

### BLOCKER: Gateway API CRDs kill k8s-gateway (internal DNS)

Installing the Gateway API CRDs — by itself, before any Gateway or HTTPRoute
exists — takes **all** internal DNS down. `k8s-gateway` (CoreDNS `k8s_gateway`
plugin v0.4.0, chart 2.4.0, the newest published) starts route informers at
`v1alpha2` as soon as any Gateway API CRD is present. In Gateway API v1.5.1
`GRPCRoute` serves only `v1` and `TLSRoute`'s `v1alpha2` is `served: false`, so
the informers never sync and the plugin fails closed for **every** name it
serves, including all 102 Ingress-backed hosts:

    [ERROR] plugin/errors: 2 <host>. A: plugin/k8s_gateway: Could not sync required resources

Not the `watchedResources` value (reverting it did not help) and not RBAC (the
chart grants `gateway.networking.k8s.io/*`). This invalidates the assumption
above that "k8s-gateway supports watching HTTPRoute (per-app DNS flips
automatically)" — and it fails toward total DNS loss, not toward invisibility.
**Any** gateway that ships Gateway API CRDs hits this, so it is not an
EG-specific problem: a Traefik *Gateway API* fallback would hit it too, while
Traefik in *Ingress* mode would not. Resolve internal DNS first; options are
listed in the plan file.

**The failure is latent.** The CRDs were installed at 14:33Z and DNS kept
working until 14:46Z, because the running k8s-gateway pod had established its
informers before the CRDs existed. It broke only when that pod restarted. So
phase 0 as written would have **passed all its verification tests** and left a
cluster-wide DNS time bomb armed for the next k8s-gateway restart — node
reboot, eviction, chart bump — likely days later with no obvious link to the
gateway work. Any re-attempt must restart k8s-gateway and re-verify DNS as an
explicit gate.

### Everything else verified fine, and still applies on re-attempt

- **CRDs are VENDORED, not Helm-installed.** `gateway-crds-helm` carries both
  channels (~4.5 MB) and Helm stores the whole chart in its release Secret, so
  the install dies on the 1 MiB Secret limit. `kubernetes/apps/network/envoy-gateway/crds/`
  holds the rendered standard-channel Gateway API + EG CRDs, regenerated by
  `crds/revendor.sh <chart-version>`. **A chart bump is two steps now:** bump
  the HelmRelease *and* re-run revendor.sh in the same commit. On re-attempt, also re-add the `network/envoy-gateway/crds/` kubeconform ignore pattern in `Taskfile.yaml` (removed together with the rollback).
- **`externalTrafficPolicy: Cluster` is mandatory, not a preference.** EG
  defaults the Envoy Service to `Local`, which Cilium documents as incompatible
  with L2 announcements — the VIP can be announced from a node with no Envoy
  pod and traffic silently blackholes (cilium/cilium#39556). At `replicas: 1`
  on 3 nodes that is a 2-in-3 chance of breakage. Set on the EnvoyProxy CR.
  Real client IP therefore comes from the ClientTrafficPolicies (XFF for
  internal, `CF-Connecting-IP` for external), exactly as ingress-nginx does it
  today. If true source IP is ever needed at L3, the fix is an Envoy
  **DaemonSet** (`EnvoyProxy.spec.provider.kubernetes.envoyDaemonSet`), not
  flipping back to `Local`.
- **The topology-injector webhook is disabled.** The chart ships a
  `MutatingWebhookConfiguration` on `pods/binding` with *no* namespace or object
  selector — it intercepts every pod binding in the cluster. It only injects
  zone labels into data-plane pods, which is worthless at `replicas: 1`. Leave
  it off unless the data plane is scaled out across zones.
- **Do not put an OIDC SecurityPolicy on a Gateway** on EG 1.8.x: envoyproxy/gateway#9656
  (open) emits an empty `oauth2` filter, Envoy rejects the whole listener, and
  *every* route on that gateway goes dark while the SecurityPolicy still reports
  `Accepted: True`. Phase 1 uses extAuth, which is unaffected — but Phase 3
  should keep authentik OIDC at route level or on 1.9.x.
- **The #8202 ext-auth regression that justified the pin is long fixed** (it was
  an Envoy 1.37.0 bug, fixed in EG v1.7.1; 1.8.3 ships Envoy 1.38.3). It no
  longer argues 1.8.3 over 1.9.0. What *does*: 1.9.0 was one day old at Phase 0.
- **The pin is time-boxed.** EG 1.8 is EOL **2026-11-08** and its support matrix
  covers k8s 1.32-1.35 while we run **1.36** (untested, not known-broken).
  Re-evaluate 1.9.x before Phase 2; it needs Gateway API v1.6.1 CRDs, so chart
  and vendored CRDs move together.
- Gateway API **v1.5.1 standard** does include `ListenerSet`, which EG 1.8
  informs on unconditionally — the widely-repeated claim that EG 1.8 forces the
  experimental channel is wrong at this bundle version.

## References

- onedr0p home-ops / cluster-template `network/envoy-gateway` (reference
  manifests: GatewayNamespace deploy type, cloudflared →
  `envoy-external.network.svc:443` w/ originServerName + http2Origin)
- authentik forward-auth docs (envoy) + James Wynn walkthrough (Feb 2026)
- EG v1.7.0 ext-auth regression: envoyproxy/gateway#8202 (why we pin+hold)
- gethomepage k8s gateway discovery + discussion #5969 (pilot gate)
- CNCF's own ingress-nginx→EG migration (Apr 2026)
