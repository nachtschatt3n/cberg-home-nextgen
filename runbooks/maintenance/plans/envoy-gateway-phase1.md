---
plan_id: envoy-gateway-phase1
component: envoy-gateway
pr: null
kind: migration-pilot               # Phase 1 of the ingress migration: the go/no-go gate
current: "EG 1.8.3 installed, 1 hostname-less route (post phase0); k8s-gateway watches Ingress+Service only"
target: "3 pilots proven: plain route, authentik ext-auth, homepage discovery"
update_type: pilot
risk: high                          # RAISED 2026-08-16 (was medium). The pilot apps
                                    # themselves are still low blast radius, but phase 1
                                    # is the phase that adds "HTTPRoute" to k8s-gateway's
                                    # watchedResources — a values change that RESTARTS the
                                    # single resolver answering all 102 internal hostnames.
                                    # That exact restart is what detonated the 2026-08-15
                                    # full internal-DNS outage. The trap is fixed (app
                                    # 1.8.0) and now alerted, but the blast radius of a
                                    # regression is every internal name in the house, so
                                    # this is operator-present work, not medium.
est_duration_min: 75                # was 60; +15 for the watchedResources change and the
                                    # mandatory restart-and-verify DNS gate (step 0)
needs_reboot: false
touches:
  namespaces: [network, kube-system, default, monitoring]
  resources:
    - "helmrelease/k8s-gateway: watchedResources += HTTPRoute (STEP 0 — restarts the pod)"
    - "httproute/echo-server (NEW; its Ingress removed same commit)"
    - "httproute/headlamp + httproute headlamp-outpost (NEW)"
    - "securitypolicy/headlamp (NEW, extAuth -> ak-outpost-headlamp)"
    - "referencegrant in kube-system (NEW, cross-ns backendRef to outpost svc)"
    - "authentik proxy provider 'headlamp': mode nginx->envoy forward-auth"
    - "helmrelease/homepage (gateway discovery verification)"
  shared: [auth, dns]               # auth: only the HEADLAMP provider is touched, but a
                                    # mistake in the SecurityPolicy pattern informs all
                                    # later conversions — treat auth blips on headlamp as
                                    # expected during the window.
                                    # dns: ADDED 2026-08-16 — step 0 restarts k8s-gateway
                                    # (192.168.55.101), the split-horizon resolver for
                                    # EVERY internal hostname. Nothing else may touch
                                    # k8s-gateway, CoreDNS or AdGuard in the same session.
depends_on: []                     # phase0 executed 2026-08-15 (69daf59c), plan retired
conflicts_with: []                  # never same session as authentik/cloudflared/
                                    # cert-manager plans, nor anything touching DNS
                                    # (k8s-gateway/adguard/coredns) — see shared: dns
security_ref: null                  # the migration's security driver (the pinned
                                    # ingress-nginx exposure) is tracked on
                                    # envoy-gateway-phase4 / AR-055 — nothing is
                                    # remediated until the nginx stack is gone
status: scheduled                   # unblocked 2026-08-15: k8s-gateway 3.7.2/1.8.0
                                    # (gateway-api v1.5.1, new org). phase0 re-run and
                                    # executed the same day: DNS gates passed twice,
                                    # including the restart-with-CRDs-present gate that
                                    # armed the original outage. Attended project — see
                                    # window note below.
window: null                          # 2026-08-15: the envoy chain is NOT window work.
                                      # phase2 alone is est 120m and the largest window is 90m,
                                      # so it never fit; the 5 phases are strictly sequential,
                                      # which shuffling cannot fix. Operator decision: run the
                                      # migration as an ATTENDED PROJECT outside the window
                                      # system — which is what a 5-phase ingress migration
                                      # actually is. Do NOT schedule these into windows.
                                      # `window: null` here is DELIBERATE, not neglect:
                                      # maintenance-plan.py --open classifies these as
                                      # REFERENCE / UNWINDOWED by design.
                                      # (previous value kept in git history)
auto_execute: false
sops_refs:
  - docs/troubleshooting/ingress-migration-plan.md
  - docs/sops/authentik.md
  - docs/sops/k8s-gateway-dns.md     # ADDED 2026-08-16 — §8 restart-and-verify DNS gate
                                     # is mandatory for step 0; §10 covers the
                                     # external-dns scoping that phases 2-3 depend on
generated: "2026-08-07"
amended: "2026-08-16"                # phase-0 execution learnings folded in
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

### 1.1 Verified starting state (2026-08-16, re-derived from the cluster)

Phase 0 is executed and live; this plan starts from **exactly** this:

| Fact | Value |
|---|---|
| Envoy Gateway | chart `gateway-helm` **1.9.0** (`envoy-gateway:v1.9.0`, data plane distroless-v1.39.0), pod Running, 0 restarts |
| Gateways | `envoy-internal` 192.168.55.103 · `envoy-external` 192.168.55.104 — both `PROGRAMMED=True`, 6h+, 0 restarts |
| Real traffic on EG | **none** — exactly 1 HTTPRoute cluster-wide (`network/https-redirect`), and it carries **no hostname** |
| ingress-nginx | still serves **all 102** Ingresses (76 `internal`, 26 `external`) |
| k8s-gateway | chart 3.7.2 / app **1.8.0**, `watchedResources: ["Ingress","Service"]` |
| Gateway API CRDs | **10** standard-channel CRDs present (gateway-api **v1.6.1**) — was 8/v1.5.1 before phase 0.5; `tcproutes` + `udproutes` are the two new ones |
| external-dns | `sources: [crd, ingress, gateway-httproute]`, scoped `--gateway-name=envoy-external --gateway-namespace=network` (live in the pod args) |

**Phase 0.5 (executed 2026-08-16) changed two things this plan must account for.**
EG is on 1.9.0 and the Gateway API bundle is v1.6.1 — done deliberately at zero
traffic because EG 1.8 supports only Kubernetes 1.32-1.35 while this cluster runs
1.36.0, and because a coupled chart+CRD bump is far cheaper before 102 routes are
attached than after.

> **The v1.6.1 bundle BLOCKS ITS OWN ROLLBACK.** It ships a
> `ValidatingAdmissionPolicy` (`failurePolicy: Fail`) whose version floor advanced
> to `v1.[0-5]`, so v1.5.1 now matches the deny pattern — verified by
> `kubectl apply --dry-run=server`, which rejects **9** of the old CRDs. A plain
> `git revert` of the CRD commit will be refused at admission, and the policy
> objects are Flux-managed so a bare `kubectl delete` is re-applied on reconcile.
> Removal procedure: `docs/sops/k8s-gateway-dns.md` §8. The floor advances with
> EVERY bundle, so this recurs on the next channel bump — do not assume "revert"
> is available as a rollback for anything CRD-coupled.

Two consequences that were NOT true when this plan was first written:

1. **`watchedResources` does NOT yet include `HTTPRoute`.** The decision doc
   listed that as phase-0 scope; it was deliberately deferred to phase 1 and
   the HelmRelease carries a normative guard comment saying so. So **Pilot A's
   gate cannot pass as written** until step 0 below runs: with the Ingress
   deleted and HTTPRoute unwatched, the echo host would simply stop resolving
   internally — not flip to .103.
2. **Step 0 restarts k8s-gateway**, which is the precise trigger of the
   2026-08-15 outage. It is now safe (see §1.2) but it is not casual: it is a
   gated step with its own verification and its own rollback.

### 1.2 What phase 0 taught — the k8s_gateway Gateway-API-CRD trap

Phase 0's **first** attempt (2026-08-15, rolled back in `769bf6dc`) took *all*
internal DNS down. Mechanism, recorded here because it governs step 0 and
phase 4, and because it will outlive this plan:

> `k8s_gateway` **v0.4.0** starts `v1alpha2` informers for the Gateway API
> route family the moment **any** `gateway.networking.k8s.io` CRD exists — no
> Gateway and no HTTPRoute required. In Gateway API **v1.5.1**, `GRPCRoute` is
> served only at `v1` and `TLSRoute`'s `v1alpha2` has `served: false`. The
> informers therefore never sync, and the plugin **fails closed for every name
> it serves** — including all 102 Ingress-backed hosts that have nothing
> whatsoever to do with Gateway API.

Two properties make it dangerous, and both are operational rules now:

- **It is LATENT.** CRDs and working DNS coexist happily until a k8s-gateway
  pod *restarts*. A pod already running when the CRDs land keeps resolving
  (its informers predate them); only a pod that *starts* with the CRDs present
  fails. On 2026-08-15 the CRDs landed at 14:33Z and DNS kept working until
  14:46Z. **So "DNS still works" after installing CRDs proves nothing** — a
  green verification can leave a time bomb that fires days later on a node
  reboot, an eviction or an unrelated chart bump, with nothing visibly
  connecting it to the gateway work.
- **It is NOT Envoy-specific.** *Any* vendor's Gateway API CRDs arm it:
  Traefik in Gateway-API mode, Istio, Cilium `gatewayAPI.enabled`, or any
  chart that bundles them transitively — including via a Renovate bump. **A
  decision to abandon Envoy Gateway for another Gateway-API implementation
  does not retire this hazard**; only staying off Gateway API entirely does.

**Resolved** by moving k8s-gateway to the new upstream org (ori-edge →
k8s-gateway): chart 2.4.0 → **3.7.2**, app 0.4.0 → **1.8.0**, built against
gateway-api v1.5.1, checking CRD presence at startup and informing only on the
kinds actually configured (`3003c050`, `69daf59c`).

**Proof it is genuinely fixed, not merely dormant:** the k8s-gateway pod
started **67 seconds after** the Gateway API CRDs were created. It booted
directly into the failing scenario — all 8 CRDs already present — and synced
with zero errors. That is the restart gate the first attempt never got.

Full incident record, recovery procedure and the finaliser deadlock:
`docs/sops/k8s-gateway-dns.md` §8.

### 1.3 The other phase-0 near-miss: external-dns would have leaked 76 internal hostnames

Fixed before it could fire, in `bca46f0e`. **`--ingress-class=external`
filters Ingress objects ONLY — it has no effect whatsoever on HTTPRoutes.**
With `gateway-httproute` added to `sources` and no gateway filter, *any*
HTTPRoute carrying a hostname would have been published to the **public**
Cloudflare zone regardless of which Gateway it attached to. It was latent only
because no route carried a hostname (still true today: the single route is
hostname-less) — it arms the instant phase 2 starts moving hosts.

Now scoped with `--gateway-name=envoy-external --gateway-namespace=network`
(verified live in the running pod's args). That form was chosen because it is
a **default-deny allowlist of exactly one Gateway**: a typo, a rename, or a
newly added gateway all fail **CLOSED** (nothing published) rather than open.
`--gateway-label-filter` was rejected — it needs a label on Gateway objects
owned by this workstream; `--label-filter` was rejected outright because it
also applies to the `ingress` and `crd` sources, where under `policy: sync` it
would prune existing external records. Phase 2 carries the negative-test gate.

**Still entirely unfiltered: `--source=crd` (DNSEndpoint).** Any DNSEndpoint
in any namespace is published to the public zone. One exists today
(`network/cloudflared`, the tunnel CNAME). This is now the **widest remaining
path to public DNS** in the cluster; it is not a phase-1 action item, but do
not add a DNSEndpoint during this migration without treating it as a public
publication.

### 1.4 Two more phase-0 artefacts that are inert today and stop being inert here

**(a) The `https-redirect` catch-all.** Phase 0 installed HTTPRoute
`network/https-redirect` with **no `hostnames:`**, attached to the `http`
(:80) listener of **both** gateways, filter `requestRedirect{scheme: https,
statusCode: 301}`. Hostname-less means it matches **every** host arriving on
:80. It is inert only because nothing routes through the gateways yet — it
arms the moment a route carries a hostname, i.e. Pilot A. Both pilots
(echo-server, headlamp) are HTTPS-capable, so the redirect is desired
behaviour for them; the hazard lands in phases 2-3, where apps exist that must
NOT be redirected (see phase 3 §2.2). Note it here so nobody later reads the
catch-all as "phase 0 leftover, probably unused".

**(b) AdGuard needs no per-app change.** AdGuard (192.168.55.5) forwards the
whole zone to k8s-gateway and holds only 3 manual rewrites, all for
**non-cluster** hosts. (The HelmRelease declares `rewrites: []`; the live
rewrites are runtime/UI state on the PVC — so they are invisible to a git
grep, which is exactly why they are worth naming.) No AdGuard edit is part of
any phase; if someone proposes one, that is a sign the k8s-gateway path is
being worked around rather than fixed.

## 2. Pre-checks

```bash
# phase0 landed: gateways Programmed on .103/.104, EG healthy, 0 firing alerts
mise exec -- kubectl get gateway -n network
mise exec -- kubectl get pods -n network | grep envoy
# BASELINE FOR STEP 0 — record these BEFORE touching k8s-gateway:
mise exec -- kubectl get cm -n network k8s-gateway -o jsonpath='{.data.Corefile}' | grep resources
#   expect: resources Ingress Service   (HTTPRoute not yet watched — this is the gap step 0 closes)
mise exec -- dig +short @192.168.55.101 <internal-host>.${SECRET_DOMAIN} A   # expect 192.168.55.100
mise exec -- dig +short @192.168.55.101 <external-host>.${SECRET_DOMAIN} A   # expect 192.168.55.102
mise exec -- kubectl logs -n network deploy/k8s-gateway --tail=100 | grep -c "Could not sync required resources"  # must be 0
# the DNS SLI must be ALIVE before we perturb DNS (a silent probe reads 100%)
mise exec -- kubectl get probe -n monitoring dns-k8s-gateway-primary dns-k8s-gateway-secondary
# headlamp + echo currently healthy through nginx (baseline)
mise exec -- kubectl get ingress -A | grep -E "echo|headlamp"
# interactive baseline: headlamp SSO round-trip via nginx works RIGHT NOW
# authentik healthy (server 3/3, blueprints errored count unchanged)
mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik | head -4
```

## 3. Steps (GitOps; cberg-agent for manifests; ak provider change via blueprint)

0. **k8s-gateway starts watching HTTPRoute — do this FIRST and gate it.**
   Edit `kubernetes/apps/network/internal/k8s-gateway/helmrelease.yaml`:
   `watchedResources: ["Ingress", "Service"]` → `["Ingress", "Service", "HTTPRoute"]`
   (the guard comment above that key is normative — update it, don't delete it).
   Commit + push; Flux rolls the Deployment. **Then run the mandatory §8
   restart-and-verify gate — a successful rollout is NOT evidence:**
   ```bash
   mise exec -- kubectl rollout status -n network deploy/k8s-gateway
   mise exec -- kubectl get cm -n network k8s-gateway -o jsonpath='{.data.Corefile}' | grep resources
   mise exec -- kubectl logs -n network deploy/k8s-gateway --tail=200 | grep -cE "Could not sync|failed to list"   # MUST be 0
   mise exec -- dig +short @192.168.55.101 <internal-host>.${SECRET_DOMAIN} A   # still 192.168.55.100
   mise exec -- dig +short @192.168.55.101 <external-host>.${SECRET_DOMAIN} A   # still 192.168.55.102
   # and a second, explicit restart-with-CRDs-present gate:
   mise exec -- kubectl rollout restart -n network deploy/k8s-gateway && \
     mise exec -- kubectl rollout status -n network deploy/k8s-gateway
   # re-run the two digs + the log grep. Any non-zero grep = STOP, revert step 0.
   ```
   **Do not start Pilot A until this gate is green.** If it fails, revert the
   commit; DNS recovers as the pod rolls back. Nothing else in phase 1 has run.
1. Pilot A: echo-server commit (HTTPRoute + delete Ingress + homepage
   annotations move). Verify gate A.
2. Pilot B: headlamp commit (routes + ReferenceGrant + SecurityPolicy +
   authentik provider mode switch). Verify gate B interactively.
3. Pilot C: verify homepage tiles for both pilots; check homepage logs for
   discovery errors.
4. Record results in docs/troubleshooting/ingress-migration-plan.md (gate
   outcomes + any pattern corrections for the P2 bulk).

## 4. Verification

- **0:** the step-0 gate above, run twice (post-rollout and post-explicit-restart);
  zero `Could not sync` / `failed to list` lines in the CURRENT pod; both digs
  answer. `probe_success{probe_class="dns"} == 1` for both DNS probes.
- A: `curl` echo host resolves to .103 (k8s-gateway) and serves 200 via EG.
- **A (negative, DNS-leak):** the echo pilot is on `envoy-internal`, so it must
  NOT appear in public DNS. This is the first live exercise of the `bca46f0e`
  gateway filter — assert the negative, do not trust `Ready=True`:
  ```bash
  mise exec -- kubectl -n network logs deploy/external-dns | grep -i '<echo-host>'   # expect: nothing
  dig +short <echo-host>.${SECRET_DOMAIN} @1.1.1.1                                   # expect: empty
  dig +short TXT k8s.a-<echo-host>.${SECRET_DOMAIN} @1.1.1.1                         # expect: empty
  ```
- B: browser SSO loop on headlamp: redirect to auth.<domain>, login, land
  back authenticated; `X-authentik-*` headers present at the app; a second
  browser (no session) is blocked (failOpen=false honored).
- C: homepage shows both tiles, no duplicates, widgets live.
- Cluster-wide: 0 firing alerts; all other ingresses untouched (spot-check 3);
  `kubectl get ingress -A --no-headers | wc -l` == 100 after both pilots
  (was 102).

## 5. Rollback (per pilot, independent)

`git revert` the pilot commit → Ingress returns, k8s-gateway flips DNS back
(TTL 60); for headlamp also revert the authentik provider mode to nginx
(blueprint revert in same commit). EG stack itself stays (phase0 scope).

**Step 0 rollback:** `git revert` the watchedResources commit → the pod rolls
back to `["Ingress","Service"]`. Confirm with the §6 SOP checks (two digs +
zero-error log grep). Note this must be reverted only when no HTTPRoute is
carrying a hostname yet — reverting it *after* Pilot A would leave the echo
host unresolvable, so revert Pilot A first, step 0 second.

**Deeper rollback (abandoning EG entirely) is NOT a plain revert.** Removing
the Gateway API CRDs is the recovery path for the DNS trap, and the
`gatewayclasses` CRD will deadlock if an orphaned GatewayClass still carries
`gateway-exists-finalizer.gateway.networking.k8s.io` after its controller is
gone. Clear the CR's finaliser first
(`kubectl patch gatewayclass <name> --type=merge -p '{"metadata":{"finalizers":[]}}'`),
then the CRD deletes. Restart k8s-gateway afterwards for a clean baseline.
Full procedure: `docs/sops/k8s-gateway-dns.md` §8 Recovery.

## 6. Interference notes

- **`shared: dns` is the new hard constraint.** Step 0 restarts the single
  resolver for every internal hostname. Nothing touching k8s-gateway, CoreDNS,
  AdGuard, or the Gateway API CRD set may run in the same session — and
  crucially, **no unrelated plan may restart k8s-gateway** while phase 1 is
  mid-flight.
- Only headlamp's auth is at risk; all other forward-auth apps stay on nginx
  outposts untouched. Expected: brief headlamp auth blips during the switch.
- Do NOT proceed to Phase 2 in this session regardless of time remaining —
  gate results need operator review (go/no-go is the whole point).
- **These phases are not window work** (see `window: null` above). The
  same-window sequencing note from 2026-08-07 (co-scheduled with the
  app-template canary + phase0) is obsolete — phase 0 is done and the chain
  now runs attended. Do not revive it.
- **Alerting gap is closed, but only just.** The 2026-08-15 outage fired
  **zero** alerts — every pod/controller-derived SLI read 100% because
  `probe_success` did not exist. The blackbox DNS probes + SLO
  `internal-dns-resolution` (N-15) were added the same day. They are young:
  confirm `BlackboxProbesAbsent` is not firing before relying on them.
