# SOP: k8s-gateway Split-Horizon DNS (and the Gateway API CRD Incompatibility)

> Description: Operating and troubleshooting the internal split-horizon DNS at 192.168.55.101 (CoreDNS k8s_gateway plugin), including the cluster-critical incompatibility with Gateway API CRDs that caused a full internal-DNS outage on 2026-08-15.
> Version: `2026.08.15`
> Last Updated: `2026-08-15`
> Owner: `cberg-agent / operator`

---

## 1) Description

k8s-gateway is the answer to "why do `*.${SECRET_DOMAIN}` hosts resolve to
LAN VIPs at home but to Cloudflare on the internet". It watches cluster
resources and serves A records for their hostnames; AdGuard (192.168.55.5)
forwards the domain to it.

- Scope: namespace `network`, deployment `k8s-gateway`, LB 192.168.55.101:53
- Prerequisites: kubectl via mise, repo checkout
- Out of scope: AdGuard itself, external DNS (external-dns/Cloudflare)

**This SOP exists mainly for one hazard: installing ANY Gateway API CRD —
from any vendor, before any Gateway/HTTPRoute exists — arms a latent, total
internal-DNS outage.** See §8.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Namespace | `network` |
| Source of truth | `kubernetes/apps/network/internal/k8s-gateway/helmrelease.yaml` |
| Chart / app | `k8s-gateway` 2.4.0 / k8s_gateway plugin 0.4.0 (**newest published — no upgrade exists**) |
| LB IP | 192.168.55.101 (lbipam, UDP 53) |
| Watched resources | `["Ingress", "Service"]` — **HTTPRoute must NOT be added, see §8** |
| TTL | 60 (matches SOA negative TTL; do not lower — see comment in HR) |
| Expected answers | internal-class hosts → 192.168.55.100, external-class → 192.168.55.102 |
| Critical dependency | none in-cluster; AdGuard forwards to it |
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
including all Ingress-backed hosts.

**Ruled out during the incident — do not re-litigate:**
- NOT `watchedResources`: a fresh pod with `["Ingress","Service"]` failed identically.
- NOT RBAC: the chart grants `gateway.networking.k8s.io/*` list/watch.
- NOT fixable by upgrade: chart 2.4.0 / app 0.4.0 is the newest published.

**The failure is LATENT.** A pod already running when the CRDs land keeps
resolving (its informers predate them). Only a pod that STARTS with the CRDs
present fails. So "DNS still works" after installing CRDs proves nothing —
the outage fires at the next restart (node reboot, eviction, chart bump),
possibly days later. **Verification gate for anything that installs Gateway
API CRDs: `kubectl rollout restart deploy/k8s-gateway -n network`, wait for
rollout, then re-run §6.**

**Sources that can introduce the CRDs:** Envoy Gateway, Traefik (Gateway API
mode), Istio, Cilium `gatewayAPI.enabled`, or any chart bundling them
transitively — including via a Renovate bump. The auto-update policy denies
`*gateway-helm*`/`*gateway-crds-helm*`/`*envoy-gateway*` for this reason.

**Recovery:** remove all `gateway.networking.k8s.io` CRDs (GitOps revert →
Flux prunes). Expect the `gatewayclasses` CRD to deadlock if an orphaned
GatewayClass still carries `gateway-exists-finalizer.gateway.networking.k8s.io`
after its controller is gone — clear the CR's finalizer
(`kubectl patch gatewayclass <name> --type=merge -p '{"metadata":{"finalizers":[]}}'`),
then the CRD deletes. DNS recovers as soon as the CRDs are gone (informers
retry and succeed); restart the pod anyway to get a clean baseline.

**Before any future gateway migration:** the internal split-horizon story
must be settled FIRST. Options analysed in
`runbooks/maintenance/plans/envoy-gateway-phase0.md` §0 (replace k8s-gateway;
AdGuard wildcard rewrites; fork the plugin to v1 routes; gateway in
Ingress-only mode).

---

## 9) Diagnose Examples

```bash
# Are any Gateway API CRDs present? (should be 0 while this SOP's constraint holds)
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

---

## 11) Rollback Plan

The HelmRelease is the only artifact: `git revert` the offending commit and
push. If the incident is CRD-induced, rollback of k8s-gateway itself does
NOT help — remove the CRDs (§8 Recovery).
