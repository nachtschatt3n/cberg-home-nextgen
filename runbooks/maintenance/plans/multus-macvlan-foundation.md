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
conflicts_with: [talos-v1.13.8]     # never in the same window as a Talos change
status: scheduled
window: "thu-early:2026-08-27"
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

Rollback: NAD/Multus are additive — revert commits; esphome revert restores
hostNetwork; Talos VLAN sub-iface removal via apply-config.
