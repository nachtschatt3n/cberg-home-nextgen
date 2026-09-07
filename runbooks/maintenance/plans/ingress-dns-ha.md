---
plan_id: ingress-dns-ha
component: ingress-nginx + k8s-gateway
pr: null                          # not a version bump — a topology change.
                                  # No Renovate PR exists or should exist.
kind: config
current: "internal-ingress-nginx replicas=1 · external-ingress-nginx replicas=1 · k8s-gateway replicas=1 · 0 PDBs in namespace network"
target: "each of the three at replicas=3, spread one-per-node, PDB minAvailable=2"
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
    - helmrelease/internal-ingress-nginx
    - helmrelease/external-ingress-nginx
    - helmrelease/k8s-gateway
    - poddisruptionbudget/k8s-gateway     # NEW standalone manifest (chart has no PDB template)
  shared:
    - "ingress (BOTH classes) — 117 Ingress objects, 90 internal + 27 external"
    - "internal DNS (192.168.55.101) — every *.${SECRET_DOMAIN} name in the house"
depends_on: []
conflicts_with:
  - envoy-gateway-phase1          # not a hard conflict; both touch the ingress
                                  # path. Do not run in the same window.
capability_change: false          # no new behaviour; same services, more copies
rollback_class: git-revert
security_ref: null                # availability finding, not a vulnerability
finding_refs: [F-f2b89d20]
status: draft
window: null                      # PROPOSED sat-attended:2026-09-19 — see §7.
                                  # MUST land before the Talos v1.14.0 node roll
                                  # (earliest 2026-09-27). Left null pending
                                  # operator go.
premises:
  # Re-checked at EXECUTION time, never trusted from when this was written.
  - id: still-single-replica
    why: >-
      The whole plan exists because these are 1-replica. If someone already
      scaled them, the baseline and the rollback target are both wrong.
    run: kubectl get deploy -n network internal-ingress-nginx-controller external-ingress-nginx-controller k8s-gateway -o jsonpath='{range .items[*]}{.metadata.name}={.spec.replicas} {end}'
    expect_exact: "internal-ingress-nginx-controller=1 external-ingress-nginx-controller=1 k8s-gateway=1 "
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
      -> internal-ingress-nginx-controller (the ONLY replica) went down
        -> it stopped publishing .status.loadBalancer on its Ingresses
          -> 90 of 117 Ingresses (every "internal" class one) had empty status
            -> k8s-gateway derives its zone from that status -> NXDOMAIN for all

The resolver never failed. It stayed up, reachable on udp/53, answering — with
no records. That is why `Ready=True` was true throughout and told us nothing.

**This is the second full internal-DNS outage from this component.** The first
(2026-08-15, chart 2.4.0) is already documented in
`docs/sops/k8s-gateway-dns.md` §8: the mere presence of a Gateway API CRD made
the plugin fail closed for every name, "latent until the next pod restart".
Different mechanism, identical blast radius. One replica is the common factor.

**The real driver is the Talos v1.14.0 node roll.** A rolling node upgrade
drains each node in turn. At `replicas: 1` with no PDB, each of the three
drains evicts the only internal ingress controller and the only k8s-gateway.
The node roll as currently configured would reproduce this outage **three
times**. This plan is a prerequisite for that roll, not an optional hardening.

### Why replicas, and not hostNetwork

Upstream's own README says `controller.hostNetwork` is "Required for use with
CNI based kubernetes installations ... since CNI and hostport don't mix yet" —
it is a workaround for clusters that cannot provide a LoadBalancer, not a
resilience feature. We have Cilium LB-IPAM handing out real VIPs
(.100 internal, .102 external, .101 DNS) with `externalTrafficPolicy: Cluster`,
so any node accepts traffic and forwards to any endpoint. Turning hostNetwork
on would REDUCE our options (one controller per node, port 80/443 contention).
Verified against chart 4.15.1 defaults: `kind: Deployment`, `replicaCount: 1`,
`hostNetwork: false`, `hostPort.enabled: false`, `affinity: {}`,
`topologySpreadConstraints: []`. Our HelmRelease overrides none of them.

### Scope: Class 1 only

This plan covers the stateless, LB-fronted ingress/DNS path ONLY. It
deliberately does NOT touch the home-automation apps (home-assistant,
music-assistant, esphome, matter-server, otbr). Those cannot be replicated and
it is over-determined: all five are `hostNetwork: true`, music-assistant holds
`hostPort` 80/8095/5000 (one pod per node ceiling), and all mount RWO Longhorn
PVCs (one writer). They are correctly on `strategy: Recreate` and they
demonstrably recover — all five came back clean from the whole-cluster reboot
of 2026-09-06 07:14-07:37Z with 0 restarts and healthy 2-replica volumes.
Their resilience track is `multus-macvlan-foundation`, not this plan.

## 2) Pre-checks

    # 1. Premises above, all three, exact match.
    # 2. Capture the baseline you will compare against AFTER:
    kubectl get ingress -A -o json | python3 -c "import sys,json;d=json.load(sys.stdin);print('ingresses:',len(d['items']),'empty-status:',sum(1 for i in d['items'] if not i.get('status',{}).get('loadBalancer',{}).get('ingress')))"
    #    EXPECT: empty-status: 0   <- if non-zero, STOP: you are mid-incident.
    # 3. Probe baseline (all four must be 1 before you start):
    #    probe_success{probe_class="dns"}  and  {probe_class="http"}
    # 4. Confirm headroom. Each extra nginx requests 100m/90Mi, each extra
    #    k8s-gateway 50m/128Mi. Total added requests: ~300m CPU / ~436Mi.
    kubectl top nodes

## 3) Steps (GitOps)

Three separate commits, verified independently. **Do not batch them.** The
internal controller is the one that caused the outage; do it first and let it
prove itself before touching the external path or DNS.

### Step 1 — internal-ingress-nginx

In `kubernetes/apps/network/internal/ingress-nginx/helmrelease.yaml`, under
`values.controller`:

    replicaCount: 3
    minAvailable: 2                 # chart renders the PDB only when replicas > 1;
                                    # default minAvailable is 1, which would allow
                                    # a drain to take us to a single replica.
    topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: kubernetes.io/hostname
        whenUnsatisfiable: DoNotSchedule
        labelSelector:
          matchLabels:
            app.kubernetes.io/name: ingress-nginx
            app.kubernetes.io/instance: internal-ingress-nginx
            app.kubernetes.io/component: controller

`DoNotSchedule`, not `ScheduleAnyway`: during a node outage the replacement
should stay Pending rather than double up on a surviving node and give us fake
redundancy.

### Step 2 — external-ingress-nginx

Identical block in
`kubernetes/apps/network/external/ingress-nginx/helmrelease.yaml`, with
`app.kubernetes.io/instance: external-ingress-nginx` in the selector.

### Step 3 — k8s-gateway + standalone PDB

Chart 3.7.2 supports `replicaCount`, `topologySpreadConstraints` and
`affinity`, but ships **no PDB template** (templates are only _helper/configmap/
deployment/rbac/service/serviceaccount). So the PDB is a new manifest added to
the app's `kustomization.yaml`.

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

New `pdb.yaml` alongside it (and referenced from `kustomization.yaml`):

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

**Verify the rendered selector matches real pod labels before committing** —
a PDB whose selector matches nothing is silently inert and protects nothing,
the same class as the inert-alert-rule trap:

    kubectl get pods -n network -l app.kubernetes.io/name=k8s-gateway --show-labels

## 4) Verification

After EACH step, not just at the end:

    # a) Replicas actually spread one-per-node (this is the point of the change)
    kubectl get pods -n network -o wide | grep -E 'ingress-nginx|k8s-gateway'
    #    EXPECT: 3 pods, 3 DISTINCT nodes, all Running 1/1. Any Pending pod
    #    means the spread constraint cannot be satisfied — do not proceed.

    # b) PDB exists AND matches pods (a 0-selector PDB is inert)
    kubectl get pdb -n network
    #    EXPECT ALLOWED DISRUPTIONS >= 1 and CURRENT HEALTHY = 3.

    # c) Ingress status still published by the (now multi-replica) controller
    kubectl get ingress -A -o json | python3 -c "import sys,json;d=json.load(sys.stdin);print('empty-status:',sum(1 for i in d['items'] if not i.get('status',{}).get('loadBalancer',{}).get('ingress')))"
    #    EXPECT: 0. This is the exact signal that failed during the incident.

    # d) DNS behaviour, not Flux status. Both probes, not one:
    #    probe_success{probe_class="dns"} == 1 for BOTH instances.
    #    NOTE the asymmetry that made the incident easy to misread:
    #    dns_k8s_gateway_primary queries an INTERNAL host, secondary queries an
    #    EXTERNAL-class host. During a total internal-DNS outage probe_success
    #    reads 1-of-2. Never call this green on one probe.

    # e) The real test — deliberately delete ONE replica and confirm no outage:
    kubectl delete pod -n network <one-internal-nginx-pod>
    #    Then re-run (c) and (d) immediately. empty-status must STAY 0 and both
    #    DNS probes must STAY 1. If either dips, the change has not bought what
    #    it was supposed to buy and you should roll back and investigate.

## 5) Rollback

`rollback_class: git-revert`. No data, no schema, no one-way migration.

    git revert <commit> && git push     # Flux reconciles back to replicas=1

Per step, so a failure in step 3 does not undo steps 1-2. The PDB is deleted by
the same revert (it is git-managed via kustomization). If a revert leaves a
stuck PDB blocking eviction, `kubectl delete pdb -n network k8s-gateway` is
safe and immediate — a PDB only gates voluntary disruption.

## 6) Interference notes

- **Do not schedule alongside `envoy-gateway-phase1`.** Both touch the ingress
  path; phase 1 also adds "HTTPRoute" to k8s-gateway's `watchedResources`,
  which is the exact edit that caused the 2026-08-15 fail-closed outage. One
  ingress-path change per window.
- **Ordering vs the Talos roll: this MUST come first.** That is the entire
  point — otherwise the roll drains through three single-replica outages.
- **cert-manager / Cloudflare untouched.** No certificate, no DNS record and no
  tunnel config changes; `default-ssl-certificate` and the cloudflared wildcard
  are unmodified.
- **AR-055 is unaffected.** This does not change the ingress-nginx version, so
  the 3 unfixable CVEs on v1.15.1 and the 2026-09-18 hard review stand exactly
  as they are. More replicas of an EOL controller is more copies of the same
  CVEs — worth saying out loud so nobody reads this plan as security progress.
  It is availability work, nothing else.

## 7) Window

Proposed **sat-attended:2026-09-19** (attended, no reboot needed, currently
holds only `media-audit-durable-output`). `sat-attended:2026-09-12` already
carries three plans. Either satisfies the hard constraint of landing before the
Talos roll (earliest feasible 2026-09-27).

NOT `nightly`: unattended, and this touches every internal hostname in the
house. If the spread constraint misbehaves the failure mode is exactly the
outage we are fixing, and someone should be awake.
