---
plan_id: cilium-1.20.1
component: cilium
pr: null                          # no open Renovate PR — held by the *cilium* deny rule in auto-update-policy.yaml
kind: chart
current: "1.20.0"
target: "1.20.1"
update_type: patch
risk: medium                      # patch content, but CNI datapath = cluster-wide blast radius
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/cilium
    - daemonset/cilium             # rolls on ALL 3 nodes (rollOutCiliumPods: true)
    - deployment/cilium-operator
  shared: [cni/cilium]             # the CNI itself — every pod's dataplane, kube-proxy
                                   # replacement, L2 announcements, LB-IPAM (all 16 LB IPs),
                                   # every NetworkPolicy
depends_on: []
conflicts_with:                    # SOLO window slot — never alongside anything cluster-wide
  - longhorn-1.12.1-engine         # live engine upgrade rides the network the agents blip
  - multus-macvlan-foundation      # CNI-adjacent Talos machine-config change
  # plus: any talos-* node roll (none open today) and the attended envoy-gateway
  # phases — nothing else network/cluster-wide may share this window.
security_ref: null
status: draft
window: "thu-early:2026-09-03"                 # SCHEDULED 2026-08-18: SOLO slot — CNI, cluster-wide; deliberately clear of longhorn-1.12.1-engine (sat 08-22), superset-pg-cutover (wed 08-26) and multus work
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
generated: "2026-08-18"
---

# cilium chart 1.20.0 → 1.20.1 (CNI — plan lane despite patch)

## 1) Summary & why held

Cilium v1.20.1 (released 2026-08-18) is the first patch on our 1.20 line. It is
held not for its content but by the standing `*cilium*` deny rule in
`runbooks/auto-update-policy.yaml`:

> "CNI datapath — … Plan + verify MA/HA streaming before upgrading; never an
> unattended bump."

Every cilium bump rolls the agent DaemonSet on all three nodes and perturbs the
dataplane every pod in the cluster rides on — hence PLAN lane, medium risk,
solo window, regardless of semver distance.

**Upstream content (v1.20.1 release notes):** pure bugfix patch, **no breaking
changes, no documented CVEs, no upgrade notes**. Relevant fixes for our config
(kube-proxy replacement + DSR + native routing + L2 announcements):

- **"Silent CIDR policy bypass and traffic drops after agent restart"** — an
  endpoint-policy-enforcement bug on restart; we run 30+ k8s NetworkPolicies,
  so this fix is a positive reason to take the patch.
- NetworkPolicy updates ignored for up to ~2 min during identity resolution.
- Several DSR fixes (TCP connection recovery, fragmented packets, RevDNAT for
  client→pod through DSR services) — we run `loadBalancer.mode: dsr`.
- Operator shutdown deadlock (CiliumEndpointSlices), misc IPAM fixes.

**Our deploy mechanism (two pins, only one live):**
- **Live pin (this plan edits it):** Flux HR
  `kubernetes/apps/kube-system/cilium/app/helmrelease.yaml` → `version: 1.20.0`,
  values from ConfigMap `cilium-helm-values`
  (`kubernetes/apps/kube-system/cilium/app/helm-values.yaml`). The cilium
  Kustomization is `prune: false`, `wait: true`.
- **Bootstrap-only pin:** `kubernetes/bootstrap/apps/helmfile.yaml` still says
  `1.19.4` (used only at cluster re-bootstrap / DR). Bring it along in the same
  commit for DR parity — it has zero runtime effect.

**Rollout behavior:** `rollOutCiliumPods: true` + `operator.rollOutPods: true`
mean the chart bump rolls agents node-by-node (DaemonSet RollingUpdate,
maxUnavailable 1). Per node there is a brief dataplane blip: established
connections keep flowing (BPF programs stay loaded in-kernel across the agent
restart), but new-flow setup / policy updates / L2 lease renewals on that node
pause for seconds. The 16 `l2announce` leases fail over between nodes during the
roll — LB IPs do NOT change (every LB service is pinned via
`lbipam.cilium.io/ips`, and the VLAN-55 pool blocks are static config in
`config/pool.yaml`, untouched by this plan), but a moving lease causes one
gratuitous-ARP shuffle per VIP. That is the "MA/HA streaming" caveat: an active
Music Assistant stream (192.168.55.29) or HA websocket (192.168.55.24) can hiccup
when its VIP's announcing node changes.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) cilium fully healthy BEFORE touching it
kubectl -n kube-system get ds cilium -o jsonpath='{.status.desiredNumberScheduled} {.status.numberReady}{"\n"}'   # 3 3
kubectl -n kube-system exec ds/cilium -c cilium-agent -- cilium status --brief   # OK
kubectl get hr -n kube-system cilium -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'   # True 1.20.0

# b) chart 1.20.1 present in the helm repo (verified 2026-08-18, re-verify)
curl -s https://helm.cilium.io/index.yaml | grep -c "version: 1.20.1"   # >=1

# c) snapshot the LB table + L2 leases (diffed in §4)
kubectl get svc -A -o wide | grep LoadBalancer | awk '{print $1"/"$2" "$5}' | sort > /tmp/lb-before.txt
kubectl get leases -n kube-system | grep -c cilium-l2announce            # note count (16 today)
kubectl get ciliumloadbalancerippool pool -o jsonpath='{.status.conditions[?(@.type=="cilium.io/PoolConflict")].status}{"\n"}'   # False

# d) nothing else in flight: no failing kustomizations/HRs, no other plan in this
#    window, NO Talos operation of any kind running
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'

# e) no active MA/HA streaming session if avoidable (operator judgement — the
#    per-node blip is seconds, but don't roll the CNI mid-movie)
```

## 3) Steps

1. **Marker + silence** (per `application-update.md` — CNI roll trips
   pod-network alerts cluster-wide for seconds):
   ```bash
   runbooks/update-marker.sh add cilium kube-system 2 "chart 1.20.0 -> 1.20.1 CNI patch"
   ```

2. **Bump the live pin** in
   `kubernetes/apps/kube-system/cilium/app/helmrelease.yaml`:
   ```yaml
       chart:
         spec:
           chart: cilium
           version: 1.20.1
   ```

3. **Bump the bootstrap pin** (DR parity, inert at runtime) in
   `kubernetes/bootstrap/apps/helmfile.yaml`:
   ```yaml
     - name: cilium
       namespace: kube-system
       chart: cilium/cilium
       version: 1.20.1
   ```

4. **Commit + push** (hunk-scoped — shared worktree):
   ```bash
   git add -p kubernetes/apps/kube-system/cilium/app/helmrelease.yaml kubernetes/bootstrap/apps/helmfile.yaml
   git commit -m "feat(cilium): chart 1.20.0 -> 1.20.1 (CNI patch; plan cilium-1.20.1)"
   git push
   ```

5. **Watch the roll — do not walk away.** Agents restart node-by-node
   (~2-3 min/node), then the operator:
   ```bash
   kubectl -n kube-system rollout status ds/cilium --timeout=10m
   kubectl -n kube-system rollout status deploy/cilium-operator --timeout=5m
   kubectl get pods -n kube-system -l k8s-app=cilium -o wide -w
   ```

6. **On success:** clear the marker: `runbooks/update-marker.sh clear cilium`.

## 4) Verification

```bash
# chart + images actually at 1.20.1
kubectl get hr -n kube-system cilium -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'   # True 1.20.1
kubectl -n kube-system get ds cilium -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # v1.20.1

# cilium health on EVERY node (not just one)
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  kubectl -n kube-system exec $p -c cilium-agent -- cilium status --brief; done   # 3x OK

# LB IPs unchanged, leases re-established
kubectl get svc -A -o wide | grep LoadBalancer | awk '{print $1"/"$2" "$5}' | sort > /tmp/lb-after.txt
diff /tmp/lb-before.txt /tmp/lb-after.txt && echo "LB TABLE UNCHANGED"
kubectl get leases -n kube-system | grep -c cilium-l2announce   # same count as §2c

# connectivity smoke across the VIP surface (VLAN 55 L2 announcements)
dig +short +time=2 @192.168.55.5 kubernetes.io >/dev/null && echo "DNS VIP OK"          # adguard
curl -sk -o /dev/null -w 'HA %{http_code}\n' https://192.168.55.24:8123 || \
  curl -s -o /dev/null -w 'HA %{http_code}\n' http://192.168.55.24:8123                 # home-assistant VIP
curl -sk -o /dev/null -w 'ingress %{http_code}\n' https://192.168.55.100                # internal ingress-nginx VIP
# in-cluster east-west + policy still enforced:
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -15   # no CNI/sandbox errors

# NetworkPolicy regression check — the guarded DBs must still work THROUGH their policies
kubectl get netpol -A --no-headers | wc -l    # same count as before (~30)
kubectl exec -n databases deploy/nocodb -- true 2>/dev/null && \
  kubectl logs -n databases deploy/nocodb --tail=5   # app still talking to shared PG

# OPERATOR (the deny-rule gate): play a stream via Music Assistant (192.168.55.29)
# and open the HA dashboard — both must work post-roll. This check is WHY the
# bump is in the plan lane; do not skip it.
```

Let the cluster settle 15 min; confirm no new firing alerts
(`kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090` +
alerts query per CLAUDE.md).

## 5) Rollback

Patch-level downgrade within the same minor is supported by cilium — rollback is
a clean git revert:

```bash
git revert <bump-commit-sha> && git push
flux reconcile source git flux-system
flux reconcile hr -n kube-system cilium
kubectl -n kube-system rollout status ds/cilium --timeout=10m
# confirm back on 1.20.0 and healthy:
kubectl get hr -n kube-system cilium -o jsonpath='{.status.history[0].chartVersion}{"\n"}'   # 1.20.0
for p in $(kubectl get pods -n kube-system -l k8s-app=cilium -o name); do
  kubectl -n kube-system exec $p -c cilium-agent -- cilium status --brief; done
diff <(kubectl get svc -A -o wide | grep LoadBalancer | awk '{print $1"/"$2" "$5}' | sort) /tmp/lb-before.txt
```

Note the rollback itself is ANOTHER full agent roll (same per-node blips) — only
pull it for a real regression (agent crash-loop, policy drops, VIP loss), not
for a transient blip during the roll.

## 6) Interference notes

- **SOLO SLOT — hard rule.** This plan restarts the dataplane under every pod in
  the cluster. It must never share a window with a Talos roll (agents restarting
  while a node drains = compounding blips, and both fight over per-node
  disruption budget), the Longhorn engine upgrade (replica rebuild traffic rides
  the network mid-blip), multus-macvlan work, or ANY other plan — even app-level
  ones — because every other plan's verification depends on the network this one
  is perturbing. `touches.shared: [cni/cilium]` should make the window agent
  flag everything; treat that as intended, not noise.
- Per-node blip profile: established flows survive (in-kernel BPF), new flows /
  policy updates / L2 lease renewals pause seconds per node. The 16 VLAN-55 VIPs
  keep their addresses (lbipam pins + static pool blocks) but may each shuffle
  announcing node once.
- The 1.20.1 fix list itself warns what to watch: the CIDR-policy-after-restart
  fix means the RESTART path is exactly where 1.20.0 misbehaved — verify policy
  enforcement post-roll (§4), don't assume.
- `kubernetes/apps/kube-system/cilium/config/` (LB pool + L2 policy) is NOT
  touched by this plan; any pool edit is a separate change, never bundled here.
- Step 0 safe-update batch runs first in every window: fine — but this plan's
  §2c LB snapshot must be taken AFTER Step 0 settles, immediately before Step 3
  of this plan.
