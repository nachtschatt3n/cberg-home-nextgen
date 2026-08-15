# SOP: Envoy Gateway upgrade (chart + Gateway API CRD channel)

> Description: Upgrading Envoy Gateway in this cluster — the `gateway-helm` chart, the Gateway API CRD channel it drags with it, and the k8s-gateway restart gate that must pass twice before the bump is considered done.
> Version: `2026.08.16`
> Last Updated: `2026-08-16`
> Owner: `cberg-agent / operator`

## Description

How to upgrade Envoy Gateway in this cluster. An EG minor bump is **never just a
chart bump** — it drags the Gateway API CRD channel with it, and those CRDs are
what a full internal-DNS outage was traced to on 2026-08-15. Written after
executing that ritual for the first time (1.8.3 → 1.9.0, gateway-api v1.5.1 →
v1.6.1) while EG carried zero traffic.

EG supports a minor for roughly six months, so this runs about twice a year.

## Overview

Three things move together and must be treated as one change:

1. the `gateway-helm` chart,
2. the **vendored** Gateway API + EG CRDs, and
3. whatever `k8s-gateway` does when it next restarts with the new CRDs present.

(3) is the dangerous one and is not obvious from the diff.

## Blueprints

N/A.

## Operational Instructions

1. **Baseline, in writing.** k8s-gateway pod age + zero sync errors; a sample of
   hosts resolving against 192.168.55.101 (internal → .100, external → .102);
   both Gateways `Programmed=True`; ingress-nginx pod names, ages and restart
   counts; the current `gateway.networking.k8s.io/bundle-version`.
2. **Check the support matrix before choosing a version.** EG 1.8 covers
   Kubernetes 1.32-1.35; 1.9 covers 1.33-1.36. Running EG off-matrix is easy to
   do accidentally, because nothing warns you — it is a docs fact, not a
   validation.
3. Bump `kubernetes/apps/network/envoy-gateway/app/helmrelease.yaml`.
4. **Re-vendor the CRDs with the script**, never by hand:
   `mise exec -- bash kubernetes/apps/network/envoy-gateway/crds/revendor.sh <version>`
   The CRDs are vendored because the `gateway-crds-helm` chart (~4.5 MB, both
   channels) exceeds Helm's **1 MiB release-Secret limit**. Do not "tidy" this
   into a HelmRelease; it will fail at install. They are applied by a Flux
   Kustomization, so `crds: CreateReplace` is inert here.
5. Commit, push, reconcile **Kustomization then HelmRelease**.
6. Run the DNS gate below.

## Examples

```bash
# Re-vendor (from repo root)
mise exec -- bash kubernetes/apps/network/envoy-gateway/crds/revendor.sh 1.9.0

# What actually changed
kubectl get crd -o json | python3 -c "
import sys, json
c = [x for x in json.load(sys.stdin)['items']
     if 'gateway.networking.k8s.io' in x['metadata']['name']]
print(len(c), {x['metadata']['annotations'].get(
    'gateway.networking.k8s.io/bundle-version') for x in c})"
```

## Verification Tests

**The DNS gate — run the restart TWICE.**

```bash
kubectl -n network rollout restart deploy/k8s-gateway
kubectl -n network rollout status deploy/k8s-gateway --timeout=180s
kubectl -n network logs deploy/k8s-gateway --tail=80 | grep -icE 'could not sync|failed to list'   # must be 0
# then resolve several known hosts against 192.168.55.101 and check the VIPs
```

Twice, because **the failure is latent**: CRDs coexist happily with a *running*
k8s-gateway pod and only bite when a pod *starts* with them present. One clean
restart can be luck. Then let it soak and re-check — the next real test is the
next node reboot or eviction.

Also assert **non-regression**, not just success: both ingress-nginx controllers
unrestarted and still serving, and a sample of live hosts end-to-end. EG must
stay parallel and traffic-free until the migration phases say otherwise.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Could not sync required resources` in a fresh k8s-gateway pod; every name SERVFAILs | k8s_gateway informs on a route version the new bundle no longer serves | revert (see Rollback), restart, confirm DNS |
| CRD delete hangs forever | `gatewayclasses` finalizer deadlock | `docs/sops/k8s-gateway-dns.md` §8 |
| Old CRDs rejected on apply | the bundle's own admission policy (see Rollback) | remove the VAP first |

## Diagnose Examples

```bash
kubectl -n network logs deploy/k8s-gateway --tail=100 | grep -iE 'sync|failed to list'
kubectl get gateway -A -o custom-columns='NAME:.metadata.name,PROGRAMMED:.status.conditions[?(@.type=="Programmed")].status'
```

## Health Check

Both Gateways `Programmed=True`; EG controller and both gateway Deployments
Running; k8s-gateway 0 sync errors; blackbox `probe_success{probe_class="dns"}`
= 1. Note those probes accept **any** `192.168.x.x` answer, so they would miss a
*wrong-VIP* response — check the actual VIPs by hand during an upgrade.

## Security Check

Each bundle is a net posture change worth reading, not assuming: 1.9.0 added
`runAsNonRoot`, `readOnlyRootFilesystem`, `seccompProfile`,
`automountServiceAccountToken: false` and a narrowed ClusterRole. Re-run
`revendor.sh` and byte-compare to prove the vendored files are reproducible and
nothing was hand-edited.

## Rollback Plan

**Assume `git revert` will NOT work.** From v1.6.1 the Gateway API bundle ships a
`ValidatingAdmissionPolicy` (`failurePolicy: Fail`) whose version floor advances
with every release. At v1.6.1 the floor is `v1.[0-5]`, so **v1.5.1 is denied** —
verified with `kubectl apply --dry-run=server`, which rejected 9 of the old CRDs.
Its message also misreports the cutoff as "before v1.5.0".

The policy objects are **Flux-managed**, so `kubectl delete` alone is re-applied
on the next reconcile. To actually roll back: remove the VAP + its binding from
the vendored manifest and reconcile, *then* apply the older CRDs, *then* revert
the chart — and run the DNS gate again afterwards.

Because the floor advances every release, this gets worse over time, not better.
**Plan CRD-coupled upgrades on the assumption that forward-fix is the realistic
path and rollback is expensive** — which is exactly why the 1.8.3 → 1.9.0 move
was done at zero traffic rather than after the migration.
