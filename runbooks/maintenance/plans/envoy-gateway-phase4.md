---
plan_id: envoy-gateway-phase4
component: envoy-gateway
pr: null
kind: migration-decommission        # Phase 4: remove ingress-nginx + tidy
current: "nginx idle (0 routes), EG serving everything"
target: "ingress-nginx removed; docs/AR closed out"
update_type: decommission
risk: medium                        # RAISED 2026-08-16 (was low). Deleting the nginx
                                    # HelmReleases really is the low-drama end state,
                                    # but two clean-up items in this phase are NOT:
                                    #   * dropping `ingress` from external-dns `sources`
                                    #     under `policy: sync` — a DELETE-capable change
                                    #     against the PUBLIC zone;
                                    #   * dropping `Ingress` from k8s-gateway
                                    #     watchedResources — restarts the resolver that
                                    #     answers every internal name (the 2026-08-15
                                    #     outage trigger; still needs the §8 gate).
                                    # Both are gated below rather than assumed benign.
est_duration_min: 75                # was 60; +15 for the two gated changes above
needs_reboot: false
touches:
  namespaces: [network, kube-system]
  resources:
    - "delete both ingress-nginx HelmReleases + IngressClasses + HelmRepository"
    - "delete ExternalName outpost services + *-authentik-outpost Ingress remnants"
    - "external-dns: drop `ingress` from sources (GATED — policy: sync deletes)"
    - "k8s-gateway: drop Ingress from watchedResources (GATED — restarts the resolver)"
    - "docs: network.md, applications.md, new-deployment-blueprint.md -> HTTPRoute\n      (incl. the https-redirect catch-all + how to write an exemption route)"
    - "runbooks/auto-update-policy.yaml: correct the stale gateway deny-rule reasons"
    - "AR-055: disable (via policy-cli, operator action)"
  shared: [dns]                     # ADDED 2026-08-16 — both gated items above are DNS
                                    # control-plane changes (internal resolver + public
                                    # zone writer). Nothing else may touch k8s-gateway,
                                    # external-dns, CoreDNS or AdGuard in this session.
depends_on: [envoy-gateway-phase3]
conflicts_with: []
security_ref: F-35f34061            # detail stays on the finding record — see body §7
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
auto_execute: false
sops_refs:
  - docs/troubleshooting/ingress-migration-plan.md
  - docs/sops/k8s-gateway-dns.md     # ADDED 2026-08-16 — §8 restart gate applies to the
                                     # watchedResources change; §10 to the sources change
generated: "2026-08-07"
amended: "2026-08-16"                # phase-0 execution learnings folded in
---

# Envoy Gateway — Phase 4: decommission + close-out

## 1. Summary & why

Per decision doc §P4. Pre-check: zero Ingress objects reference the nginx
classes; nginx controller request rate ~0 over **7 days** (Prometheus) —
**raised from 48h on 2026-08-16**: two known consumers are plausibly *weekly*,
not daily (the wazuh SAML login path and the Alexa audio stream), so 48h of
quiet does not distinguish "unused" from "not used this weekend". Then delete
the nginx stack, prune the ecosystem sources, keep gateways on .103/.104
(update docs), confirm the fleet Trivy scan no longer reports the pinned
v1.15.1 findings, `policy-cli.py risk disable AR-055`, update the
new-deployment blueprint to the HTTPRoute pattern (else new apps regress), and
DELETE `docs/troubleshooting/ingress-migration-plan.md` (migration complete —
per docs lifecycle rules).

## 2. Pre-checks

```bash
mise exec -- kubectl get ingress -A --no-headers | wc -l          # expect 0
mise exec -- kubectl get ingressclass                             # internal/external still present
mise exec -- kubectl get httproute -A --no-headers | wc -l        # expect ~102 + https-redirect
# every nginx annotation behaviour has a live EG equivalent — after this phase
# there is no nginx left to fall back to. Confirm the phase-2/3 inventory is
# fully discharged, in particular:
#   * ai/librechat: X-Tenant-Id is still stripped on the HTTPRoute
#     (RequestHeaderModifier) — it is load-bearing security, not cosmetics
#   * the 3 configuration-snippet users are all converted (this is the same
#     precondition as the phase-2 allow-snippet-annotations=false milestone)
#   * session affinity (13 Ingresses) behaves acceptably under EG's LB policy
#   * the plain-HTTP exemption route(s) still win over the hostname-less
#     https-redirect catch-all (phase 3 §2.2 gate + its control, re-run)
# nginx request rate ~0 over 7 DAYS (not 48h), both controllers:
#   sum(rate(nginx_ingress_controller_requests[7d])) by (controller_pod)
#   ...and check the 7d MAX, not just the current rate — a single weekly SAML
#   or Alexa request is invisible in an instantaneous rate:
#   max_over_time(sum(rate(nginx_ingress_controller_requests[1h]))[7d:1h])
```

## 3. Steps — with the two clean-up items that are NOT bookkeeping

1. Delete the nginx stack (both HelmReleases, IngressClasses, HelmRepository),
   the ExternalName outpost services and `*-authentik-outpost` Ingress remnants.
   **In the same commit, delete the three now-dead nginx-bound alert rules** —
   `IngressNginx5xxSustained` (`ingress-nginx-availability-alerts.yaml`),
   `AuthentikIngressAuthFailures` and `AuthentikIngressAuthBackendError`
   (`authentik-alerts.yaml`). Precondition: their Envoy counterparts exist and
   have been **proven firing** (phase 2 §1.5). Deleting them without that is
   how a permanently-silent auth-failure signal gets normalised. The other 14
   Authentik alerts are controller-independent and stay.

2. **GATED — external-dns `sources`: drop `ingress`.**
   `sources: ["crd", "ingress", "gateway-httproute"]` → `["crd", "gateway-httproute"]`.
   Under `policy: sync`, external-dns **deletes** records it no longer sees a
   source for. This is safe **only** once every external hostname is served by
   an HTTPRoute on `envoy-external`. Do it as its own commit, after step 1, and
   verify against the public zone:
   ```bash
   # before: capture the record set size
   # (external_dns_registry_endpoints_total via the ServiceMonitor, or the log line)
   mise exec -- kubectl -n network logs deploy/external-dns --tail=20 | grep -E 'All records|Changing record'
   # after the roll: the loop must settle on "All records are already up to date"
   # and must NOT log a burst of Deleting/Changing for live public hostnames
   mise exec -- kubectl -n network logs deploy/external-dns --tail=60 | grep -E 'Deleting|Changing record'
   # spot-check 5 public hostnames still resolve to the tunnel CNAME
   dig +short CNAME <host>.${SECRET_DOMAIN} @1.1.1.1
   ```
   **`--source=crd` (DNSEndpoint) stays, and stays entirely unfiltered.** After
   this commit it is the *only* unscoped path to public DNS left in the cluster
   (one endpoint today: `network/cloudflared`). Worth recording as a residual in
   the close-out, not fixing here.

3. **GATED — k8s-gateway `watchedResources`: drop `Ingress`.**
   `["Ingress", "Service", "HTTPRoute"]` → `["Service", "HTTPRoute"]`. This
   **restarts the resolver that answers every internal hostname**, which is the
   exact trigger of the 2026-08-15 full internal-DNS outage. The app-1.8.0 fix
   makes it safe, but the gate is still mandatory — a successful rollout is not
   evidence (`docs/sops/k8s-gateway-dns.md` §8):
   ```bash
   mise exec -- kubectl rollout status -n network deploy/k8s-gateway
   mise exec -- kubectl get cm -n network k8s-gateway -o jsonpath='{.data.Corefile}' | grep resources
   mise exec -- kubectl logs -n network deploy/k8s-gateway --tail=200 | grep -cE "Could not sync|failed to list"   # MUST be 0
   mise exec -- dig +short @192.168.55.101 <internal-host>.${SECRET_DOMAIN} A   # 192.168.55.103
   mise exec -- dig +short @192.168.55.101 <external-host>.${SECRET_DOMAIN} A   # 192.168.55.104
   ```
   Note the expected answers **change in this phase**: with the Ingresses gone,
   the VIPs are the Gateway addresses (.103/.104), not the nginx VIPs
   (.100/.102). Update `docs/sops/k8s-gateway-dns.md` §2 "Expected answers" in
   the same commit, or the SOP's own verification test becomes a false alarm.

4. Docs: `network.md`, `applications.md`, `new-deployment-blueprint.md` →
   HTTPRoute pattern. The blueprint must additionally document **two things a
   new app author cannot discover from the manifests**: (a) the hostname-less
   `network/https-redirect` catch-all 301s every host on :80, so a plain-HTTP
   endpoint needs an explicit more-specific exemption route (phase 3 §2.2);
   and (b) forward-auth is a per-route `SecurityPolicy`, which **fails open**
   if it is missing or misattached — so a new protected app's acceptance test
   is the *negative* one (unauthenticated request must be refused), not "the
   page loads".

5. `policy-cli.py risk disable AR-055` (operator action — see §6).

6. **Correct the stale gateway deny-rule reasons in
   `runbooks/auto-update-policy.yaml`.** They currently read *"NOT DEPLOYED —
   Envoy Gateway phase 0 rolled back 2026-08-15"* for `*gateway-helm*` and
   `*gateway-crds-helm*`. That is factually wrong as of 2026-08-15: phase 0 was
   re-applied (`69daf59c`) and EG 1.8.3 is live. **Keep the deny rules** — a
   Gateway API CRD bump remains the single change most able to break internal
   DNS, and holding them attended is still correct — but rewrite the reasons to
   say so instead of "not deployed". (Git-tracked, code-reviewed; not editable
   from a plan file.)

7. DELETE `docs/troubleshooting/ingress-migration-plan.md`. **Do NOT delete
   `docs/sops/k8s-gateway-dns.md`** — §8 (the Gateway-API-CRD trap, its latency
   property, and the recovery/finaliser procedure) is a permanent operating
   hazard of running Gateway API at all, not migration scaffolding, and it is
   the only place that knowledge survives once the troubleshooting doc goes.

## 4. Verification

- 0 Ingress objects, 0 nginx pods, both IngressClasses gone; every app reachable
  (Kuma's 69 monitors green).
- The two gates in steps 2 and 3, each verified before the next step starts.
- Fleet Trivy scan no longer reports the pinned-v1.15.1 findings (a **zero** is
  publishable; do not paste scanner output into the close-out commit —
  `docs/sops/vulnerability-disclosure.md`).
- `python3 runbooks/maintenance-plan.py` still at 0 warnings after the four
  phase plans are deleted (plans are transient: delete on `executed`).

## 5. Rollback

`git revert` restores the nginx HelmReleases (harmless while routes remain on
EG — nginx simply serves nothing). Reverting step 2 restores the `ingress`
source; note that any public record external-dns already deleted comes back
only if a matching source object exists again. Reverting step 3 restores the
Ingress watch and restarts k8s-gateway — re-run the §8 gate on the way back
too, in both directions.

## 5b. Security driver reference

> **Security driver — detail withheld from this public repo.**
> Tracked as **F-35f34061** (`security` / severity `accepted`).
> Full detail (CVE IDs, counts, exposure, exploitability) lives on the
> finding record — it is deliberately not reproduced here.
>
> - Dashboard: `https://sweep.<DOMAIN>/findings/F-35f34061`
> - CLI: `runbooks/policy-cli.py finding show F-35f34061`
> - Plans: envoy-gateway-phase4, ingress-nginx-1.15.6
>
> See `docs/sops/vulnerability-disclosure.md` before adding any
> vulnerability detail to a committed file.

## 6. Interference notes

- `shared: [dns]` — steps 2 and 3 are DNS control-plane changes. Nothing else
  may touch k8s-gateway, external-dns, CoreDNS or AdGuard in this session.
- **AR-055 close-out, and a flag on its current text (do not edit the policy DB
  from this plan).** AR-055 accepts the ingress-nginx exposure, time-boxed to a
  hard review on **2026-09-18**, escalating to the Chainguard contingency
  (`ingress-nginx-1.15.6.md`, retained as break-glass) if the external cutover
  (phase 3) has not happened. Its justification was written 2026-08-07 and
  still describes the pre-incident plan — it predates the DNS outage, the
  k8s-gateway 3.7.2/1.8.0 upgrade, the phase-0 rollback-and-reapply, and the
  decision to run phases 1-4 as an attended, **unwindowed** project. Because
  the phases now carry no scheduled dates, nothing will surface slippage
  against 2026-09-18 until the date passes. Operator action: re-review the
  AR-055 justification and date. Flagged here, deliberately not changed.
- One compensating control AR-055 names — the phase-2 hardening milestone
  (`allow-snippet-annotations: false`) — disappears with the nginx stack in
  this phase. That is fine (the controller is gone), but it means AR-055 must
  be disabled in the *same* pass, not left accepted against a deleted component.
- **Nothing here touches L4 or hostNetwork.** Cilium LB-IPAM Services
  (mosquitto, plex, home-assistant, adguard DNS, music-assistant-server on
  192.168.55.29, etc.) and the 4 hostNetwork apps (esphome, home-assistant,
  matter-server, music-assistant-server) are outside the ingress path by
  design and survive the nginx deletion untouched. Removing the nginx
  IngressClasses must not be read as "the last ingress-shaped thing is gone".
- **Not window work** (see `window: null`): last in a strictly sequential chain.
  Attended project.
