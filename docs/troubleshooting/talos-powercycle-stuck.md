# Talos `--mode powercycle` reboot stuck on node 03

## Symptom

`talosctl reboot --mode powercycle --nodes 192.168.55.13` returns successfully ("post check passed") but node never re-establishes etcd or kubelet. `talosctl get machinestatus` reports `stage: rebooting` with `unmetConditions: []` indefinitely. Other Talos services (apid, containerd, machined, dashboard) keep running, so the API answers, but cri/etcd/kubelet/trustd all show `Finished/Fail`.

Observed twice during 2026-04-30 Talos v1.11→v1.13 rolling upgrade, both times on `k8s-nuc14-03` only. Each time recovery worked the same way: a follow-up `talosctl reboot --mode default` (graceful) cleared the stuck state and services restarted normally.

## Reproduction

1. Cluster is healthy on Talos v1.13.0.
2. Run `talosctl reboot --mode powercycle --nodes 192.168.55.13 --wait`
3. Command returns "post check passed" within ~3 min.
4. After "completion": `talosctl get machinestatus -n 192.168.55.13` shows `stage: rebooting`. kubectl shows the node `NotReady`. Pings to the node IP succeed (so it physically rebooted, hardware is up). But Talos services that were stopped during the reboot sequence (etcd, cri, kubelet, trustd) never get restarted.

Other 2 nodes are unaffected by the same command sequence. Issue appears specific to nuc14-03's hardware/firmware combination.

## Workaround

```bash
mise exec -- talosctl reboot --mode default --nodes 192.168.55.13 --wait
# Default-mode reboot completes normally; services come back; node returns to Ready.
```

Take ~5 min. After this, `machinestatus.spec.stage` returns to `running`.

## Hypotheses

1. **kexec-via-`powercycle` race**: `--mode powercycle` is supposed to bypass kexec and do a full hardware power cycle (vs `default` which can use kexec for fast warm reboot). Maybe NUC14 BIOS/IPMI firmware doesn't fully relinquish hardware on powercycle, leaving Talos's runtime controller in `rebooting` after the actual reboot completes — the controller never sees the "reboot finished" event because it itself was the trigger.
2. **Talos runtime status race**: The machine-status controller updates `stage: rebooting` BEFORE issuing the reboot. If the new boot's runtime can't read/clear that state, it stays.
3. **Hardware-specific (NUC14-03 only)**: only this node, twice. No similar behavior on -01 or -02. Could be SSD/firmware/BIOS revision difference.

## Mitigation in upgrade procedure

For Talos rolling upgrades on this cluster:

- Use `--mode default` (or omit `--mode`) by default.
- Reserve `--mode powercycle` for when GuC/firmware really needs a cold reboot (e.g. the GuC LOADABLE/0x0 → RUNNING/0xf0 retry).
- If `powercycle` is needed and the node sticks: `talosctl reboot --mode default` to recover.

## Open questions / follow-up

- Does `talosctl reboot --mode powercycle` reproducibly stick on nuc14-03 every time, or only sometimes? (Sample n=2/2 so far.)
- Does it correlate with the node being current etcd leader vs follower?
- Is this fixed in a Talos v1.14 / v1.15 release?
- Is the BIOS/firmware of nuc14-03 different from nuc14-01/-02 (different boot revision)?

## References

- `talosctl reboot --help` — `--mode` flag docs
- Observation timestamps:
  - 1st occurrence: 2026-04-30 Stage A, after v1.11→v1.12.7 upgrade
  - 2nd occurrence: 2026-04-30 Stage B, after v1.12.7→v1.13.0 upgrade
- Both times: graceful default reboot recovered.
