# SOP: k8s-gateway Split-Horizon DNS (and the Gateway API CRD Incompatibility)

> Description: Operating and troubleshooting the internal split-horizon DNS at 192.168.55.101 (CoreDNS k8s_gateway plugin), including the (RESOLVED on app 1.8.0) incompatibility with Gateway API CRDs that caused a full internal-DNS outage on 2026-08-15.
> Version: `2026.08.19`
> Last Updated: `2026-08-19`
> Owner: `cberg-agent / operator`

---

## 1) Description

k8s-gateway is the answer to "why do `*.${SECRET_DOMAIN}` hosts resolve to
LAN VIPs at home but to Cloudflare on the internet". It watches cluster
resources and serves A records for their hostnames; AdGuard (192.168.55.5)
forwards the domain to it — **and so does the cluster's own CoreDNS**, whose
`${SECRET_DOMAIN}` server block forwards the whole zone to this same IP. So this
service is on the critical path for LAN clients *and* for every in-cluster pod
resolving an internal host.

- Scope: namespace `network`, deployment `k8s-gateway`, LB 192.168.55.101:53
- Prerequisites: kubectl via mise, repo checkout
- Out of scope: AdGuard itself, external DNS (external-dns/Cloudflare)

**This SOP originally existed for one hazard: on app 0.4.0, installing ANY
Gateway API CRD — from any vendor, before any Gateway/HTTPRoute exists —
armed a latent, total internal-DNS outage.** RESOLVED 2026-08-15 by upgrading
to chart 3.7.2 / app 1.8.0 (new upstream org, built against gateway-api
v1.5.1) and re-verified with the §8 restart gate after the Envoy Gateway
CRDs landed. Re-verified AGAIN 2026-08-16 at gateway-api **v1.6.1**
(EG 1.9.0 / "phase 0.5"). §8 stays as the incident record and as the
mandatory restart-and-verify gate for future CRD/chart changes.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `network` |
| Source of truth | `kubernetes/apps/network/internal/k8s-gateway/helmrelease.yaml` |
| Chart / app | `k8s-gateway` 3.7.2 / k8s_gateway plugin 1.8.0 (upstream moved orgs: ori-edge → k8s-gateway; image `ghcr.io/k8s-gateway/k8s_gateway`, tag pinned in HR because the chart default lags) |
| LB IP | 192.168.55.101 (lbipam, UDP 53) |
| Watched resources | `["Ingress", "Service"]` — adding `HTTPRoute` is deliberate phase-1 work of the EG migration, behind the §8 restart-and-verify gate |
| TTL | 60 (matches SOA negative TTL; do not lower — see comment in HR) |
| Expected answers | internal-class hosts → 192.168.55.100, external-class → 192.168.55.102 |
| Critical dependency | **BOTH** AdGuard (for LAN clients) **and cluster CoreDNS** — CoreDNS's `${SECRET_DOMAIN}` server block forwards to this IP (`kubernetes/apps/kube-system/coredns/app/helm-values.yaml`), so in-cluster resolution of internal hosts fails with it too. (Corrected 2026-08-19: this row previously read "none in-cluster", which understated the blast radius of a k8s-gateway outage in the exact SOP written to handle one.) |
| Upstream retry policy | CoreDNS forwards to this IP with `max_connect_attempts 0` (unbounded), set explicitly. CoreDNS >= 1.14.7 defaults to 2 connect attempts per upstream; our forward block has a SINGLE upstream, which is the shape that cap bites, and the resulting SERVFAIL would then be cached. The directive parses identically on 1.14.6 and 1.14.7. Revisit as its own change — unbounded also preserves the retry-storm behaviour upstream capped on purpose. |
| Alerting | **NONE** — the 2026-08-15 full outage fired zero alerts (known gap) |

---

## 3) Blueprints

N/A — plain HelmRelease, no blueprint system.

- Source of truth: `kubernetes/apps/network/internal/k8s-gateway/helmrelease.yaml`
- The guard comment above `watchedResources` in that file is normative.

---

## 4) Operational Instructions

Normal changes (TTL, resources, values):

1. Edit the HelmRelease in place.
2. `mise exec -- task kubeconform` (2 known pre-existing pallet-price-monitor errors are unrelated).
3. Commit, push; Flux reconciles.
4. **Any change that restarts the pod: run the §7 health check immediately
   after rollout.** The pod restart is what arms/triggers the §8 failure —
   never assume DNS is fine because the rollout reported success.

---

## 5) Examples

```bash
# Resolve an internal host through k8s-gateway directly
mise exec -- dig +short @192.168.55.101 <internal-host>.${SECRET_DOMAIN} A   # expect 192.168.55.100

# Through the household resolver
mise exec -- dig +short @192.168.55.5 <internal-host>.${SECRET_DOMAIN} A
```

---

## 6) Verification Tests

```bash
# 1. one internal-class and one external-class host answer with the right VIP
mise exec -- dig +short @192.168.55.101 <internal-host>.${SECRET_DOMAIN} A   # 192.168.55.100
mise exec -- dig +short @192.168.55.101 <external-host>.${SECRET_DOMAIN} A   # 192.168.55.102
# 2. zero informer-sync errors in the CURRENT pod
mise exec -- kubectl logs -n network deploy/k8s-gateway --tail=100 | grep -c "Could not sync required resources"   # must be 0
```

---

## 7) Health Check

```bash
mise exec -- kubectl get pods -n network -l app.kubernetes.io/name=k8s-gateway
mise exec -- kubectl logs -n network deploy/k8s-gateway --tail=50 | grep -E "ERROR|failed to list" || echo OK
mise exec -- dig +short @192.168.55.101 <any-ingress-host> A   # must answer
```

An empty `dig` answer for a host that has an Ingress = outage, even if the
pod is Running/Ready (the plugin fails closed while CoreDNS itself stays up —
readiness does NOT cover informer sync).

That sentence is now **machine-enforced** — it is the whole rationale for
`validate_answer_rrs` in the blackbox DNS modules:

```bash
# Automated equivalent since 2026-08-15 (N-15): answer-validating blackbox DNS probes
mise exec -- kubectl get probe -n monitoring dns-k8s-gateway-primary dns-k8s-gateway-secondary
# probe_success{probe_class="dns"} must be 1 for both. Alerts:
#   InternalDnsResolutionFailing (2m, critical)  — one name not resolving
#   InternalDnsResolverDown      (2m, critical)  — ALL DNS probes down = whole-zone shape
#   BlackboxProbesAbsent        (10m, critical)  — the SLI went SILENT (reads 100% otherwise)
```

The 2026-08-15 outage produced **zero** SLO signal: `probe_success` did not
exist, so every pod/controller-derived SLI read 100%. Closed by
`kubernetes/apps/monitoring/prometheus-blackbox-exporter/` (N-15) and SLO
`internal-dns-resolution` (99.9% / 7d).

---

## 8) Troubleshooting — THE Gateway API CRD trap (2026-08-15 incident)

**Symptom:** every internal lookup returns empty/SERVFAIL; pod log spams

```
[ERROR] plugin/errors: 2 <host>. A: plugin/k8s_gateway: Could not sync required resources
failed to list *v1alpha2.GRPCRoute: the server could not find the requested resource
failed to list *v1alpha2.TLSRoute:  the server could not find the requested resource
```

**Cause:** k8s_gateway v0.4.0 starts informers for the Gateway API route
family at `v1alpha2` **as soon as any `gateway.networking.k8s.io` CRD exists
in the cluster** — no Gateway or HTTPRoute needed. Gateway API v1.5.1 serves
GRPCRoute only at `v1` and TLSRoute's `v1alpha2` is `served: false`, so the
informers never sync and the plugin fails closed for EVERY name it serves,
including all Ingress-backed hosts. The v1.6.1 bundle (current) keeps that
exact shape and **adds two more instances of it**: TCPRoute and UDPRoute
also ship `v1alpha2` with `served: false`. The trap surface got wider, not
narrower.

**Ruled out during the incident — do not re-litigate:**
- NOT `watchedResources`: a fresh pod with `["Ingress","Service"]` failed identically.
- NOT RBAC: the chart grants `gateway.networking.k8s.io/*` list/watch.
- ~~NOT fixable by upgrade~~ — WRONG, and it was the actual fix: the "newest
  published" premise came from watching the frozen ori-edge repo. The upstream
  moved to the k8s-gateway org; chart 3.7.2 / app 1.8.0 is built against
  gateway-api v1.5.1, checks CRD presence at startup, and only informs on the
  resource kinds actually configured. Upgraded + gated 2026-08-15 (3003c050,
  69daf59c): fresh 1.8.0 pods sync cleanly with all 8 Gateway API CRDs
  (gateway-api v1.5.1) present — and again 2026-08-16 with all 10
  (gateway-api v1.6.1), see the validated-bundle note below.

**The failure is LATENT.** A pod already running when the CRDs land keeps
resolving (its informers predate them). Only a pod that STARTS with the CRDs
present fails. So "DNS still works" after installing CRDs proves nothing —
the outage fires at the next restart (node reboot, eviction, chart bump),
possibly days later. **Verification gate for anything that installs Gateway
API CRDs: `kubectl rollout restart deploy/k8s-gateway -n network`, wait for
rollout, then re-run §6.** Run it TWICE — one clean restart can be luck.

**v1.6.1 validated (2026-08-16, EG 1.9.0 / phase 0.5).** The gate was run
twice against the new bundle: k8s-gateway chart 3.7.2 / app 1.8.0 starts
cleanly with all 10 v1.6.1 standard-channel CRDs present (fresh pods, 0
sync errors, all sampled Ingress hosts resolving). App 1.8.0 logs
`updating resources with: [Ingress Service]` and starts NO route informers
at all — that is *why* the added `served: false` v1alpha2 TCPRoute/UDPRoute
shapes are inert here. **This does not retire the gate.** The tolerance is
a property of app 1.8.0's configured-kinds behaviour, so it must be
re-proven on any k8s-gateway version change, on any future CRD channel
bump, and the moment `watchedResources` gains `HTTPRoute` in phase 1 —
phase 1 is exactly where the plugin *does* start route informers.

**Sources that can introduce the CRDs:** Envoy Gateway, Traefik (Gateway API
mode), Istio, Cilium `gatewayAPI.enabled`, or any chart bundling them
transitively — including via a Renovate bump. The auto-update policy denies
`*gateway-helm*`/`*gateway-crds-helm*`/`*envoy-gateway*` for this reason.

**Recovery:** remove all `gateway.networking.k8s.io` CRDs (GitOps revert →
Flux prunes).

> **Rollback trap (verified 2026-08-16): the v1.6.1 bundle blocks its own
> rollback.** The bundle ships a `ValidatingAdmissionPolicy`
> `safe-upgrades.gateway.networking.k8s.io` (binding
> `validationActions: [Deny]`, `failurePolicy: Fail`) whose CEL rejects any
> CRD annotated with a `bundle-version` below a floor. **The floor advances
> with every bundle** — v1.5.1 denied `v1.[0-4].\d+`, v1.6.1 denies
> `v1.[0-5].\d+` — so each bundle blocks the one you would roll back to.
> This generalises: expect it on every future channel bump, not just this
> one. The live v1.6.1 policy is still in force while the revert is applied. Its deny message is also stale
> — it claims "before v1.5.0" while the regex blocks through v1.5.x — so an
> operator mid-rollback gets a message that looks inapplicable.
> **The VAP and its binding are Flux-managed** (they live inside
> `crds/gateway-api-standard.yaml`, labelled
> `kustomize.toolkit.fluxcd.io/name=envoy-gateway-crds`), so a bare
> `kubectl delete` is re-applied on the next reconcile — it only buys a
> window. A working rollback therefore has to bring the older, permissive
> policy pair back **in the same commit** as the CRD downgrade, which a plain
> `git revert` of the re-vendor commit does. If the apply is still denied
> (kustomize applies CRDs before the cluster-scoped VAP, and the API server's
> policy cache lags), delete the binding and re-reconcile:
>
> ```bash
> kubectl delete validatingadmissionpolicybinding safe-upgrades.gateway.networking.k8s.io
> flux reconcile kustomization envoy-gateway-crds -n network
> ```
>
> **Standing pre-flight before any bundle downgrade** — proves the deny in
> seconds without changing anything:
>
> ```bash
> kubectl apply --dry-run=server -f <old httproutes CRD>   # expect Denied if trapped
> ``` Expect the `gatewayclasses` CRD to deadlock if an orphaned
GatewayClass still carries `gateway-exists-finalizer.gateway.networking.k8s.io`
after its controller is gone — clear the CR's finalizer
(`kubectl patch gatewayclass <name> --type=merge -p '{"metadata":{"finalizers":[]}}'`),
then the CRD deletes. DNS recovers as soon as the CRDs are gone (informers
retry and succeed); restart the pod anyway to get a clean baseline.

**Before any future gateway migration:** the internal split-horizon story
must be settled FIRST. Options analysed in
`runbooks/maintenance/plans/envoy-gateway-phase0.md` §0 (plan retired after phase-0 execution 2026-08-15; recoverable via `git show 15fac5c8^:runbooks/maintenance/plans/envoy-gateway-phase0.md`) — replace k8s-gateway;
AdGuard wildcard rewrites; fork the plugin to v1 routes; gateway in
Ingress-only mode).

---

## 9) Diagnose Examples

```bash
# Gateway API CRDs present (10 standard-channel CRDs expected since phase 0.5
# landed 2026-08-16 at gateway-api v1.6.1; app 1.8.0 tolerates them)
mise exec -- kubectl get crd | grep -c gateway.networking.k8s.io

# Informer errors, current pod
mise exec -- kubectl logs -n network deploy/k8s-gateway --tail=200 | grep -E "failed to list|Could not sync" | tail

# What the plugin is configured to watch (live)
mise exec -- kubectl get cm -n network k8s-gateway -o jsonpath='{.data.Corefile}' | grep resources
```

---

## 10) Security Check

- The chart's ClusterRole grants `gateway.networking.k8s.io: ['*']` list/watch
  — chart default, read-only, acceptable; it is what makes the §8 trigger
  permanently armed, not a privilege problem.
- No secrets involved; service is LAN-only (VLAN reachability per network docs).

### The other half of split-horizon: keep INTERNAL hostnames out of PUBLIC DNS

k8s-gateway answers the internal side. external-dns
(`kubernetes/apps/network/external/external-dns/helmrelease.yaml`) answers the
public Cloudflare side, and it must never publish an internal-only hostname.

Two scoping flags do that, one per source — **both are load-bearing**:

| external-dns source | scoping flag | keeps out |
|---|---|---|
| `ingress` | `--ingress-class=external` | every `className: internal` Ingress |
| `gateway-httproute` | `--gateway-name=envoy-external` + `--gateway-namespace=network` | every HTTPRoute parented to `envoy-internal` |

**`--ingress-class` filters Ingress objects ONLY — it has no effect whatsoever
on HTTPRoutes.** Before the gateway flags were added (2026-08-15, `bca46f0e`),
the `gateway-httproute` source was completely unscoped: any HTTPRoute with a
hostname would have been published to the public zone regardless of which
Gateway it attached to. Latent while no route carried a hostname; it arms the
moment the Envoy migration starts moving hosts onto the gateways.

Why name+namespace and not `--gateway-label-filter`: it is a default-deny
allowlist of exactly one Gateway that needs no label on the Gateway objects,
and a typo, a rename, or a newly added gateway all fail CLOSED (not published).
`--label-filter` is NOT an option — it applies to the `ingress` and `crd`
sources too, so under `policy: sync` it would prune the existing external
records. `--gateway-name` takes a single name; if a second externally-facing
Gateway is ever added, switch to `--gateway-label-filter` and label it.

Verify after ANY change to external-dns sources/flags, or when routes move
between gateways (do not trust `Ready=True` — assert the negative outcome):

```bash
# 1. the filter is actually live in the process, not just in git
kubectl -n network logs deploy/external-dns | grep -o 'GatewayName:[^ ]* GatewayNamespace:[^ ]*'

# 2. NEGATIVE TEST: a hostname on the INTERNAL gateway must NOT reach public DNS.
#    Create a throwaway HTTPRoute on envoy-internal with a test hostname, then:
kubectl -n network logs deploy/external-dns | grep -i '<testhost>'   # expect: nothing
dig +short <testhost>.${SECRET_DOMAIN} @1.1.1.1                      # expect: empty
#    Also check the TXT registry record (an A record whose k8s.a- TXT is missing
#    is treated as unowned and is left behind FOREVER by policy: sync):
dig +short TXT k8s.a-<testhost>.${SECRET_DOMAIN} @1.1.1.1            # expect: empty
#    Then delete the throwaway route.

# 3. policy: sync can DELETE — confirm the existing external record set is intact
#    (external_dns_registry_endpoints_total must be unchanged, and every loop
#    should log "All records are already up to date")
kubectl -n network logs deploy/external-dns --tail=20 | grep -E 'All records|Changing record'
```

A/B control that proves the filter (not something else) is what suppressed the
route: run a throwaway `--dry-run --once` external-dns pod on the same image
with and without the two flags. With them you get
`Gateway network/envoy-internal does not match envoy-external ...` followed by
`No endpoints could be generated from HTTPRoute ...`. `--dry-run` writes
nothing; give the pod ONLY the sources you are testing and remember that a
partial `sources:` list under `policy: sync` will log DELETEs for everything
else (harmless under dry-run, alarming to read).

---

## 11) Rollback Plan

The HelmRelease is the only artifact: `git revert` the offending commit and
push. If the incident is CRD-induced, rollback of k8s-gateway itself does
NOT help — remove the CRDs (§8 Recovery).

## Related

- **`docs/sops/envoy-gateway-upgrade.md`** — the coupled chart + Gateway API
  CRD-channel ritual, including the DNS gate below and the fact that from
  v1.6.1 the bundle's own admission policy blocks rolling back to the
  previous channel.
