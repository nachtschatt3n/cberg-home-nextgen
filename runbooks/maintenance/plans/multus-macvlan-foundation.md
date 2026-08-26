---
plan_id: multus-macvlan-foundation
component: multus
pr: null
kind: deploy                        # new CNI meta-plugin + IoT NAD + first migration
current: "5 hostNetwork apps (multicast/mDNS pinned to node IPs)"
target: "Multus installed; VLAN-30 macvlan NAD ready; esphome off hostNetwork"
update_type: install
risk: medium                        # CNI-adjacent (Talos machine-config VLAN
                                    # sub-interface + switch trunk change), but
                                    # additive: Cilium primary CNI untouched
                                    # (cni.exclusive already false); existing pods
                                    # unaffected until they opt in via annotation
est_duration_min: 90
needs_reboot: false                 # talosctl apply-config for the VLAN sub-iface
                                    # is no-reboot; switch trunk is UniFi config
touches:
  namespaces: [kube-system, home-automation]
  resources:
    - "helmrelease/multus (NEW, thick daemonset + Talos patches: host-run-netns mount, install-binary args, 150Mi limit)"
    - "networkattachmentdefinition/iot (NEW: macvlan on enp86s0.30, static IPAM, sbr)"
    - "UniFi: trunk VLAN 30 onto the 3 node ports (Basement-SW-24-PoE)"
    - "Talos machine-config: enp86s0.30 VLAN sub-interface (apply-config per node, serial)"
    - "esphome: hostNetwork=false -> plain pod network + ping status + use_address (easy win, needs NO macvlan)"
  shared: [cni-adjacent]            # do NOT co-schedule with any Cilium/Talos plan
depends_on: []                      # independent of the EG migration
conflicts_with: []                    # RESOLVED 2026-08-16: was [talos-v1.13.8], dropped
                                      # because that work SHIPPED (all 3 nodes on v1.13.8, plan
                                      # retired). An unresolvable conflicts_with is silently
                                      # UNENFORCED — it reads as a guard while being none.
                                      #
                                      # The interference SURFACE survives the id: never
                                      # co-schedule this with a Talos node-reboot roll. A rolling
                                      # drain wipes the ephemeral partition and rebuilds ~50 of 65
                                      # Longhorn replicas per node; stacking CNI-layer changes on
                                      # that is how 2026-08-16 produced a 34-volume / 37-pod attach
                                      # pile-up. Re-point at the next talos-* plan when written.
status: reference                     # was 'scheduled' with window:null — a contradiction:
                                      # a plan that believes it is scheduled but names no slot
                                      # silently never runs. 'reference' is the honest state:
                                      # deliberately outside the window system until its
                                      # track is activated (P0.4, 2026-08-26).
window: null                          # UNSCHEDULED 2026-08-16. 90m of work against a 90m maximum
                                      # window — zero rollback slack, the same TIGHT condition that
                                      # app-template-5.0 was pulled for. Treated consistently rather
                                      # than granted an exception, because the first thing sacrificed
                                      # in an overrun is the rollback, and this one reconfigures the
                                      # CNI layer.
                                      #
                                      # Natural split: (1) install Multus + define the VLAN-30 macvlan
                                      # NetworkAttachmentDefinition — additive, nothing moves onto it;
                                      # (2) migrate esphome off hostNetwork onto the NAD. Stage 1 is
                                      # inert and fits comfortably; stage 2 is the risky half and
                                      # deserves its own window with room to roll back.
                                      # 60m window — it never fit. sun-window:2026-09-06 is a
                                      # free 90m slot. (It does not need reboot, so a sun window
                                      # is not required, but no 90m no-reboot slot was free.)
auto_execute: false
sops_refs:
  - docs/troubleshooting/ingress-migration-plan.md   # hostNetwork research recorded in §scope
generated: "2026-08-07"
---

# Multus + macvlan foundation (+ esphome de-hostNetwork)

Per the 2026-08-07 hostNetwork research (recorded in the ingress decision doc
§scope-exclusions + memory): fixes the multicast/mDNS problem no gateway can
touch. Crib onedr0p home-ops: multus (kube-system) + NAD with
`{macvlan master enp86s0.30, mode bridge, static IPAM} + sbr`, per-pod static
IP AND static MAC (stable L2 identity across reschedules — the actual
failover win). Talos ships macvlan natively (≥1.8); Cilium already
`cni.exclusive: false`.

Order: (1) UniFi trunk VLAN 30 to node ports [operator/unifi-agent];
(2) Talos VLAN sub-interface via talhelper patch + apply-config, one node at
a time, verify link; (3) Multus HR + Talos daemonset patches; (4) NAD `iot`
+ throwaway test pod (static IP from 192.168.32.0/23, ping the IoT VLAN,
receive mDNS); (5) esphome: drop hostNetwork (needs NO macvlan — ping-based
status + use_address per device).

Follow-ups (separate plans once this proves): music-assistant → macvlan
(bind iface + published IP = macvlan IP; Sonos manual IPs as backstop; keep
LB .29 for UI + music-stream ingress for Alexa), then home-assistant
(+ cast known_hosts / homekit advertise_ip belt-and-braces). matter-server
stays hostNetwork for now; otbr permanently.

## Verification

**CONTENTS ASSERTION: multicast/mDNS frames are actually RECEIVED on the
macvlan interface.** This plan exists *because* multicast does not work; an
attached NAD, a pod with a static IP on 192.168.32.0/23 and a successful
unicast `ping` are all the SHAPE of that fix and are exactly what a pod with
working L3 and broken multicast also looks like. Assert the property directly
(`docs/sops/verification-contents-not-shape.md`):

```bash
# step 4 test pod, on the `iot` NAD
kubectl exec -n <ns> <testpod> -- ip -o addr show           # macvlan iface with the static IP
kubectl exec -n <ns> <testpod> -- ping -c3 <an IoT VLAN host>   # L3 — the FLOOR, not the assertion

# THE assertion: multicast frames arrive. Non-empty output within ~30s is the pass;
# a silent capture is the failure this plan exists to prevent.
kubectl exec -n <ns> <testpod> -- timeout 30 tcpdump -ni <macvlan-iface> -c 5 'udp port 5353'
#   must capture >= 1 mDNS packet. Zero packets => macvlan is up and useless.
```

```bash
# step 5, esphome after dropping hostNetwork — assert DEVICES, not pods.
# An esphome pod that is Ready with zero devices reachable is the empty-but-
# healthy shape; the device count is the contents.
kubectl get pods -n home-automation | grep esphome                  # floor
#   Operator/ha-agent: confirm every ESPHome device still reports ONLINE in the
#   dashboard and at least one entity's state updates in Home Assistant — the
#   ping-based status + use_address path is what actually changed.
```

Also: `flux get kustomizations -A` clean, and no node lost its VLAN link after
the per-node Talos apply-config (verify link before moving to the next node —
this is already ordered as step 2).

## Rollback

NAD/Multus are additive — revert commits; esphome revert restores
hostNetwork; Talos VLAN sub-iface removal via apply-config.
