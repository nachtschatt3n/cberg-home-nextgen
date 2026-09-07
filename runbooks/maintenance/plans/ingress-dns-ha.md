---
plan_id: ingress-dns-ha
component: envoy-gateway + k8s-gateway
pr: null                          # not a version bump — a topology change.
                                  # No Renovate PR exists or should exist.
kind: config
current: "envoyDeployment.replicas=1 (both gateways, via GatewayClass parametersRef) · envoy-gateway control plane replicas=1 · k8s-gateway replicas=1 · 0 PDBs in namespace network"
target: "Envoy data planes + EG control plane + k8s-gateway at replicas=3, spread one-per-node, PDB minAvailable=2"
update_type: config
risk: medium                      # NOT low: the blast radius is every internal
                                  # hostname in the household. But every step is
                                  # a values-only change, revertible by one
                                  # git revert, with no data and no schema.
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [network]
  resources:
    - envoyproxy/envoy-proxy-config       # GatewayClass parametersRef — covers BOTH gateways
    - helmrelease/envoy-gateway           # EG control plane replicas
    - helmrelease/k8s-gateway
    - poddisruptionbudget/k8s-gateway     # NEW standalone manifest (chart has no PDB template)
  shared:
    - "Envoy data plane — will carry ALL ingress traffic once phases 1-3 land"
    - "internal DNS (192.168.55.101) — every *.${SECRET_DOMAIN} name in the house"
depends_on: []
conflicts_with: []                # NONE. This is now a PREREQUISITE for
                                  # envoy-gateway-phase1, not a rival to it —
                                  # see §1 "Why this must come first".
capability_change: false          # no new behaviour; same services, more copies
rollback_class: git-revert
security_ref: null                # availability finding, not a vulnerability
finding_refs: [F-f2b89d20]
status: draft
window: null                      # PROPOSED sat-attended:2026-09-12, AHEAD of
                                  # envoy-gateway-phase1. Operator directive
                                  # 2026-09-07: replace nginx ASAP. Left null
                                  # pending go + window rebalancing (see §7).
premises:
  # Re-checked at EXECUTION time, never trusted from when this was written.
  - id: envoy-still-single-replica
    why: >-
      The whole plan exists because these are 1-replica. If someone already
      scaled them, the baseline and the rollback target are both wrong.
    run: kubectl get envoyproxy -n network envoy-proxy-config -o jsonpath='{.spec.provider.kubernetes.envoyDeployment.replicas}'
    expect_exact: "1"
  - id: kgw-still-single-replica
    why: Same, for the DNS half.
    run: kubectl get deploy -n network k8s-gateway -o jsonpath='{.spec.replicas}'
    expect_exact: "1"
  - id: no-pdb-yet
    why: >-
      A pre-existing PDB would mean someone else is mid-change here.
    run: kubectl get pdb -n network --no-headers 2>/dev/null | wc -l | tr -d ' '
    expect_exact: "0"
  - id: three-nodes-schedulable
    why: >-
      whenUnsatisfiable=DoNotSchedule means a 3-replica spread needs 3
      schedulable nodes. On 2 nodes the third replica sits Pending forever,
      which looks like a failed rollout.
    run: kubectl get nodes --no-headers | grep -c ' Ready'
    expect_exact: "3"
sops_refs:
  - docs/sops/k8s-gateway-dns.md
  - docs/sops/monitoring.md
generated: "2026-09-07"
---

## 1) Summary & why

At 04:00:36Z on 2026-09-07 every internal hostname in the house stopped
resolving for ~6 minutes. The chain, traced live (F-f2b89d20):

    ~74 pods recreated on k8s-nuc14-01
      -> the single internal-ingress-nginx replica went down with them
        -> it stopped publishing .status.loadBalancer on its Ingresses
          -> 90 of 117 Ingresses (every "internal" class one) had empty status
            -> k8s-gateway derives its zone from that field -> NXDOMAIN for all

The resolver never failed. It stayed up, reachable on udp/53, answering — with
no records. That is why `Ready=True` was true throughout and told us nothing.

**Migrating to Envoy does not fix this.** Measured 2026-09-07:

| component | replicas | node |
|---|---|---|
| `envoy-internal` (data plane) | 1 | k8s-nuc14-01 |
| `envoy-external` (data plane) | 1 | k8s-nuc14-03 |
| `envoy-gateway` (control plane) | 1 | k8s-nuc14-03 |
| PDBs in namespace `network` | **0** | — |

Two of the three are co-located. Envoy inherits the identical topology, so the
cutover would move the single point of failure rather than remove it.

### Why this must come FIRST, before envoy-gateway-phase1

Phase 1 adds `"HTTPRoute"` to k8s-gateway's `watchedResources`. That is the
same class of edit that caused the **2026-08-15 full internal-DNS outage**
(chart 2.4.0: the mere presence of a Gateway API CRD made the plugin fail
closed for every name, "latent until the next pod restart" —
`docs/sops/k8s-gateway-dns.md` §8). Making that edit while k8s-gateway is a
single replica repeats the exact conditions of an outage this household has
already had twice.

Do the topology first, then the cutover lands on a resilient base. This plan
therefore has **no conflicts** with the phase plans — it is their prerequisite.

### Scope: Class 1 only, and NOT nginx

Operator directive 2026-09-07: replace nginx as soon as possible. So this plan
deliberately does **not** invest in nginx replicas — that work would be thrown
away at phase 4. If the migration slips past the Talos v1.14.0 node roll, see
§8 for the fallback, which is the one case where nginx HA becomes necessary.

It also does not touch the home-automation apps. They cannot be replicated and
it is over-determined: all five are `hostNetwork: true`, music-assistant holds
`hostPort` 80/8095/5000 (one pod per node ceiling), and all mount RWO Longhorn
PVCs (one writer). They are correctly on `strategy: Recreate` and demonstrably
recover — all five returned clean from the whole-cluster reboot of
2026-09-06 07:14-07:37Z with 0 restarts and healthy 2-replica volumes. Their
track is `multus-macvlan-foundation`.

## 2) Pre-checks

    # 1. Premises above, all three, exact match.
    # 2. Baseline to compare against AFTER:
    kubectl get ingress -A -o json | python3 -c "import sys,json;d=json.load(sys.stdin);print('empty-status:',sum(1 for i in d['items'] if not i.get('status',{}).get('loadBalancer',{}).get('ingress')))"
    #    EXPECT 0. Non-zero => you are mid-incident, STOP.
    # 3. All four blackbox probes must read 1 before starting.
    # 4. Headroom. Added requests: Envoy 2x100m/128Mi per gateway (4 extra pods),
    #    k8s-gateway 2x50m/128Mi. ~500m CPU / ~768Mi total.
    kubectl top nodes

## 3) Steps (GitOps)

Four commits, verified independently. **Do not batch them.**

### Step 1 — Envoy data planes (both gateways, one change)

`EnvoyProxy/envoy-proxy-config` is referenced from the `envoy` GatewayClass
`parametersRef`, so it governs **both** `envoy-internal` and `envoy-external`.
Edit `kubernetes/apps/network/envoy-gateway/app/gatewayclass.yaml`, under
`spec.provider.kubernetes`:

    envoyDeployment:
      replicas: 3                      # was 1
      pod:
        topologySpreadConstraints:
          - maxSkew: 1
            topologyKey: kubernetes.io/hostname
            whenUnsatisfiable: DoNotSchedule
            labelSelector:
              matchLabels:
                app.kubernetes.io/managed-by: envoy-gateway
    envoyPDB:
      minAvailable: 2

`envoyPDB` is native in EG 1.9.0 — verified present in the CRD schema
(`provider.kubernetes` exposes `envoyDaemonSet`, `envoyDeployment`, `envoyHpa`,
`envoyPDB`, `envoyService`, `envoyServiceAccount`). No standalone PDB needed
here, unlike k8s-gateway.

**Do NOT edit the generated `envoy-internal`/`envoy-external` Deployments
directly** — Envoy Gateway owns them and reconciles any hand edit away. The
EnvoyProxy CR is the only supported surface.

**Confirm the spread selector against real labels before committing** — a
constraint whose selector matches nothing is silently inert:

    kubectl get pods -n network -l gateway.envoyproxy.io/owning-gateway-name --show-labels

### Step 2 — Envoy Gateway control plane

Raise the `envoy-gateway` Deployment (chart `gateway-helm`) to 3 replicas with
spread + PDB via its HelmRelease values. EG's control plane uses leader
election, so extra replicas are standby, not active-active — that is the
intended HA shape. Verify the chart's exact values key at execution
(`helm show values gateway-helm --version <pinned>`), since it differs across
EG minor versions.

### Step 3 — k8s-gateway + standalone PDB

Chart 3.7.2 supports `replicaCount`, `topologySpreadConstraints` and
`affinity`, but ships **no PDB template** (templates are only _helper/configmap/
deployment/rbac/service/serviceaccount), so the PDB is a new manifest added to
the app `kustomization.yaml`.

In `kubernetes/apps/network/internal/k8s-gateway/helmrelease.yaml` values:

    replicaCount: 3
    topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: kubernetes.io/hostname
        whenUnsatisfiable: DoNotSchedule
        labelSelector:
          matchLabels:
            app.kubernetes.io/name: k8s-gateway
            app.kubernetes.io/instance: k8s-gateway

New `pdb.yaml` alongside it:

    apiVersion: policy/v1
    kind: PodDisruptionBudget
    metadata:
      name: k8s-gateway
      namespace: network
    spec:
      minAvailable: 2
      selector:
        matchLabels:
          app.kubernetes.io/name: k8s-gateway
          app.kubernetes.io/instance: k8s-gateway

Verify the selector matches real pod labels before committing.

`DoNotSchedule` everywhere, not `ScheduleAnyway`: during a node outage the
replacement should stay Pending rather than double up on a surviving node and
give us fake redundancy.

### Step 4 — leave nginx alone

No change. It keeps serving all 117 Ingresses at `replicas: 1` until phase 4
deletes it. This is a deliberate, recorded decision, not an oversight — see §8.

## 4) Verification

After EACH step:

    # a) Replicas actually spread one-per-node
    kubectl get pods -n network -o wide | grep -E 'envoy|k8s-gateway'
    #    EXPECT 3 pods per component on 3 DISTINCT nodes, all Running.
    #    Any Pending pod => the spread cannot be satisfied. Do not proceed.

    # b) PDBs exist AND match pods (a 0-selector PDB is inert)
    kubectl get pdb -n network
    #    EXPECT ALLOWED DISRUPTIONS >= 1, CURRENT HEALTHY = 3, for each.

    # c) Gateways still programmed
    kubectl get gateway -n network
    #    EXPECT PROGRAMMED=True for envoy-internal and envoy-external.

    # d) DNS behaviour, not Flux status. BOTH probes:
    #    probe_success{probe_class="dns"} == 1 for both instances.
    #    NOTE the asymmetry that made the incident hard to read:
    #    dns_k8s_gateway_primary queries an INTERNAL host, secondary an
    #    EXTERNAL-class host. During a total internal-DNS outage this reads
    #    1-of-2. Never call it green on one probe.

    # e) empty-status Ingresses still 0 (nginx is untouched but still serving)

    # f) THE REAL TEST — delete one replica of each and confirm no impact:
    kubectl delete pod -n network <one-envoy-internal-pod>
    kubectl delete pod -n network <one-k8s-gateway-pod>
    #    Re-run (c), (d), (e) immediately. All must hold. If anything dips,
    #    the change did not buy what it was supposed to. Roll back.

## 5) Rollback

`rollback_class: git-revert`. No data, no schema, no one-way migration.

    git revert <commit> && git push

Per step, so a failure in step 3 does not undo steps 1-2.

**Caveat carried from phase 1 that applies to anything CRD-coupled here:** the
Gateway API v1.6.1 bundle installed in phase 0.5 ships a
`ValidatingAdmissionPolicy` (`failurePolicy: Fail`) whose version floor rejects
v1.5.1 CRDs, so `git revert` is NOT available for a CRD change — 9 of the old
CRDs are refused at admission and the policy objects are Flux-managed.
**This plan touches no CRDs**, so a plain revert is valid for all four steps.
Do not generalise the revert path to phase work that does touch them.

## 6) Interference notes

- **PREREQUISITE for `envoy-gateway-phase1`.** Schedule ahead of it, not
  against it.
- **Ordering vs the Talos roll: still must come first.** At `replicas: 1` with
  no PDB, each of the three node drains evicts the only k8s-gateway. That is
  true whether nginx or Envoy is serving.
- **cert-manager / Cloudflare untouched.** No certificate, DNS record or tunnel
  config changes.
- **AR-055 unaffected.** No ingress-nginx version change; the 3 unfixable CVEs
  on v1.15.1 and the 2026-09-18 hard review stand exactly as they are. This is
  availability work, not security progress.

## 7) Window

Proposed **sat-attended:2026-09-12**, ahead of phase 1. Attended, no reboot.
That slot currently carries `edot-collector-0.160.0`, `mcpo-python-3.14` and
`scrypted-0.145.0`, so something must move — see the schedule note in §8.

NOT `nightly`: unattended, and this touches every internal hostname in the
house. If a spread constraint misbehaves the failure mode is the outage we are
fixing, and someone should be awake.

## 8) The nginx decision, recorded

Operator directive 2026-09-07: **replace nginx as soon as possible.** So nginx
gets no HA investment here.

That leaves one uncovered risk, stated plainly rather than buried: **if the
Envoy migration has not completed by the Talos v1.14.0 node roll, the roll will
drain through three single-replica nginx outages** — one per node — because
nginx will still be serving all 117 Ingresses.

The two ways out, both operator calls:

1. **Complete phases 1-3 before the roll.** Then nginx carries no traffic and
   its replica count is irrelevant.
2. **If the migration slips, add the nginx replica bump back** as a throwaway
   4-line change per controller, reverted at phase 4. Cheap insurance.

Do not let this sit undecided until the roll is being scheduled.
