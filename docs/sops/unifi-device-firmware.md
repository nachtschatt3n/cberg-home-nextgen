# SOP: UniFi Device Firmware Updates

> Description: How UniFi switch/AP firmware is updated in this homelab — manually, one device at a time, in the Sunday attended window, with an etcd health gate before and after each core switch.
> Version: `2026.09.26`
> Last Updated: `2026-09-26`
> Owner: `homelab-operator` (executed via `unifi-agent`)

---

## 1) Description

On 2026-09-24 (~20:26Z trigger, completions 20:29:21Z / 20:29:40Z) firmware 7.4.1 -> 7.5.15
was applied to **both** `Basement-SW-24-PoE` and `Basement-SW-48 PoE` within 20 seconds.
Every Kubernetes node hangs off SW-24, which itself uplinks through SW-48, so the cluster
was fully partitioned: etcd lost its leader, Elasticsearch timed out ~46k documents and
Longhorn rebuilt replicas (finding `F-784aa78f`).

This SOP makes device firmware a **manual, serial, attended** operation.

- Scope: UniFi switches and APs adopted by the local UniFi Network controller (site `default`).
  Core switches get the full procedure; APs may be batched (see §5 Example B).
- Prerequisites: `unifictl` >= 5.5 via `mise exec` from this repo with a valid cached
  session (never run interactive `unifictl login` from an agent); `kubectl` and `talosctl`
  access to the cluster; Prometheus reachable via port-forward.
- Out of scope: UniFi OS / Network application (console) updates, gateway firmware.

### Hard rules

1. **Updates are manual.** Device auto-update stays OFF (`mgmt.auto_upgrade: false`).
   Do not use "Update All" / bulk upgrade in the Network UI, Site Manager (unifi.ui.com)
   or the mobile app for switches — that is exactly how both switches rebooted together.
2. **Switches are upgraded ONE AT A TIME.** Order: **SW-48 first**, then **SW-24 only after
   SW-48 is back, adopted (`state=1`) and etcd is healthy.** Never both together.
3. **Only in the Sunday attended window** (`sun-attended`, 09:00 Europe/Berlin, the only
   reboot-capable slot in `runbooks/maintenance-windows.yaml`). Never unattended.
   **Never in the same `sun-attended` slot as a Talos node roll** (e.g. plan
   `talos-1.14.1`): a switch reboot and a node reboot each cost etcd a member or its
   leader, and together they can drop quorum — and a failure in either would be
   undiagnosable against the other. One or the other per Sunday, never both.
4. **Pre-check etcd** has a leader and 3 healthy members before each switch.
5. **Verify links and etcd after each switch** before touching the next device.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Controller setting (device auto-update) | `get/setting/mgmt` -> `auto_upgrade: false`, `auto_upgrade_hour: 3` |
| UI location of that setting | UniFi OS Settings > Control Plane > Updates > UniFi Devices (auto-update toggle) |
| UniFi OS auto-update | `/api/system` -> `firmware.autoUpdate.schedule: null` (off) |
| Scheduled upgrade tasks | `rest/scheduletask` — must contain no `action: upgrade` entry |
| Core switch 1 | `Basement-SW-48 PoE` (USW-Pro-48-PoE) — core, uplinks SW-24, APs, NAS path |
| Core switch 2 | `Basement-SW-24-PoE` (USW-Enterprise-24-PoE) — carries all 3 k8s nodes |
| Measured upgrade duration | `upgrade_duration: 200` s per switch (controller-reported) |
| Critical dependency | etcd quorum across `k8s-nuc14-01/02/03` (192.168.55.11-13) |

**Blast radius, honestly stated:**

- **SW-48 reboot**: nodes lose the gateway, NAS path via SW-48 and cross-VLAN traffic for
  ~3-4 min, but stay L2-connected to each other on SW-24 -> etcd should keep its leader.
- **SW-24 reboot**: all three nodes lose each other -> etcd has **no quorum for ~3-4 min
  even when done alone.** This is unavoidable with a single top-of-rack switch; the
  procedure limits it to one bounded partition instead of a compounded one.

---

## 3) Blueprints

N/A — UniFi device firmware and controller settings are not GitOps-managed. The state of
record is the controller itself; this SOP defines the read-back commands (§6, §9).

---

## 4) Operational Instructions

### 4.1 Preparation (day before / start of window)

1. Confirm auto-update is still off and nothing is scheduled (§6 Test 1).
2. Check which devices have an update pending:
   ```bash
   mise exec -- unifictl local device list -o json | python3 -c "
   import sys, json
   d = json.load(sys.stdin); d = d.get('data', d) if isinstance(d, dict) else d
   for x in d:
       print(x.get('name'), x.get('version'), 'upgradable=%s' % x.get('upgradable'), 'to=%s' % x.get('upgrade_to_firmware'))"
   ```
3. Read the release notes for the target version (community.ui.com releases). Hold if they
   mention STP/LACP/SFP+ regressions for the model.
4. Record the before-state (current version, `previous_firmware_version`) for rollback:
   ```bash
   mise exec -- unifictl local device get <MAC> -o json > /tmp/<device>-pre-fw.json
   ```

### 4.2 Pre-check (before EACH switch)

```bash
# etcd: 3 members, one leader, no errors
mise exec -- talosctl etcd status --nodes 192.168.55.11,192.168.55.12,192.168.55.13
mise exec -- talosctl etcd members --nodes 192.168.55.11

# nodes Ready
kubectl get nodes

# Prometheus: every etcd member sees a leader (expect 3)
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s http://localhost:9090/api/v1/query --data-urlencode 'query=sum(etcd_server_has_leader)'
```

Go only if: 3 members listed, all report the same leader ID, `sum(etcd_server_has_leader) == 3`,
all nodes `Ready`, and no Longhorn volume is `degraded`
(`kubectl get volumes -n storage | grep -v healthy`). Otherwise STOP.

### 4.3 Upgrade SW-48 (first)

Approval gate: `device upgrade` is mutating — state the command and blast radius, get the
operator's GO in the same turn.

```bash
mise exec -- unifictl local device upgrade <SW-48-MAC>
```

Wait for the device to come back (~200 s + re-adoption). Then run §4.5 verification.

### 4.4 Upgrade SW-24 (second, only after SW-48 verified)

Re-run the full §4.2 pre-check. Then:

```bash
mise exec -- unifictl local device upgrade <SW-24-MAC>
```

Expect a ~3-4 min cluster partition (see §2). Do not intervene in the cluster while it
reboots. Then run §4.5 verification.

### 4.5 Verify after each switch

```bash
# device back, adopted, on target version, uptime reset
mise exec -- unifictl local device get <MAC> -o json | python3 -c "
import sys, json
d = json.load(sys.stdin); d = d.get('data', d) if isinstance(d, dict) else d
x = d[0] if isinstance(d, list) else d
print(x['name'], x['version'], 'state=%s' % x['state'], 'uptime=%s' % x['uptime'])"

# uplinks / node ports up at expected speed (10G SFP+ uplinks, node ports)
mise exec -- unifictl local device get <MAC> -o json | python3 -c "
import sys, json
d = json.load(sys.stdin); d = d.get('data', d) if isinstance(d, dict) else d
x = d[0] if isinstance(d, list) else d
for p in x.get('port_table', []):
    if p.get('up'): print(p['port_idx'], p.get('name'), p.get('speed'), 'uplink' if p.get('is_uplink') else '')"

# etcd + nodes (same as pre-check)
mise exec -- talosctl etcd status --nodes 192.168.55.11,192.168.55.12,192.168.55.13
kubectl get nodes
```

Proceed to the next device only when: `state=1`, version = target, all previously-up
ports are up at the same speed, etcd has 3 members with one leader, all nodes `Ready`.
Allow Longhorn to finish any rebuilds (`kubectl get volumes -n storage`) before SW-24.

---

## 5) Examples

### Example A: routine switch release (both core switches pending)

1. Sunday 09:00: §4.1 prep, §4.2 pre-check -> GO.
2. Upgrade SW-48, wait, §4.5 verify (etcd must have kept its leader).
3. Wait for Longhorn to be fully `healthy`.
4. §4.2 pre-check again -> upgrade SW-24 -> §4.5 verify.
5. Record versions in the maintenance-window report.

### Example B: AP-only release

APs do not carry cluster traffic. They may be upgraded in the same Sunday window one per
area (so Wi-Fi coverage never drops everywhere at once). Still manual; no etcd gate needed,
but verify each AP returns to `state=1` and re-acquires clients.

### Example C: only SW-24 is pending

Run the full pre-check; accept the ~3-4 min partition; verify. Never "just do it quickly"
outside the window — SW-24 alone is enough to drop etcd quorum.

---

## 6) Verification Tests

### Test 1: device auto-update is off and nothing is scheduled

```bash
# cached session only; this never calls /api/auth/login
mise exec -- unifictl local health get >/dev/null && echo session-ok
# Controller setting (read via the Network UI or the REST endpoint get/setting/mgmt):
#   auto_upgrade must be false
# Scheduled tasks (rest/scheduletask): no entry with action "upgrade"
```

Expected:
- `auto_upgrade: false`; no `upgrade` scheduled task; UniFi OS `firmware.autoUpdate.schedule: null`.

If failed:
- Turn it off in UniFi OS Settings > Control Plane > Updates (UniFi Devices auto-update),
  or `set/setting/mgmt` with `{"auto_upgrade": false}`; read back.

### Test 2: a switch upgrade did not cost etcd its leader (SW-48)

```bash
curl -s http://localhost:9090/api/v1/query --data-urlencode \
  'query=increase(etcd_server_leader_changes_seen_total[30m])'
```

Expected:
- ~0 after an SW-48 upgrade. After SW-24, a single leader change is expected (partition).

If failed:
- Check whether the SW-48 reboot overlapped with anything else (other device, node reboot).

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Both core switches rebooted together | Bulk "Update All" / Site Manager / mobile-app update, or auto-update re-enabled | Check §6 Test 1; check `log all` for `FIRMWARE_UPDATED_V2` + ADMIN; brief admins on rule 1 |
| Switch stuck `state` != 1 after upgrade | Re-adoption pending / inform URL | Wait 5 min; `unifictl local device get <MAC>`; power-cycle via upstream PoE only as last resort |
| Port renegotiated at lower speed | SFP+/DAC compatibility change in new firmware | Compare port_table to pre-state; reseat; roll back (§11) if persistent |
| etcd no leader > 5 min after SW-24 back | Nodes not re-learned / port down | `kubectl get nodes`, `talosctl etcd status`; check node port `up` on SW-24 |

```bash
mise exec -- unifictl local log all --limit 500 -o json   # look for FIRMWARE_UPDATED_V2
mise exec -- unifictl local log admin-activity --limit 50
```

---

## 8) Diagnose Examples

### Diagnose Example 1: "who/what upgraded the switches?"

```bash
mise exec -- unifictl local log all --limit 1000 -o json | python3 -c "
import sys, json, datetime
d = json.load(sys.stdin); d = d.get('data', d) if isinstance(d, dict) else d
for e in d:
    if isinstance(e, dict) and e.get('key') == 'FIRMWARE_UPDATED_V2':
        p = e['parameters']
        print(datetime.datetime.fromtimestamp(e['timestamp']/1000, datetime.UTC),
              p['DEVICE']['name'], p['PREVIOUS_VERSION']['name'], '->', p['VERSION']['name'],
              'admin=%s' % p.get('ADMIN', {}).get('name'))"
```

Expected:
- The completion time and the attributed admin. `FIRMWARE_UPDATED` is a *completion*
  event; the trigger is ~`upgrade_duration` (200 s) earlier.

If unclear:
- An attributed admin with no matching `ADMIN_ACCESS` before the trigger means the
  action came through an already-open session, the mobile app or Site Manager — not auto-update.

### Diagnose Example 2: partition impact

```bash
curl -s http://localhost:9090/api/v1/query --data-urlencode \
  'query=increase(node_network_carrier_changes_total[1h])'
curl -s http://localhost:9090/api/v1/query --data-urlencode \
  'query=increase(etcd_server_leader_changes_seen_total[1h])'
```

Expected:
- Carrier changes on node NICs line up with the switch reboot time.

---

## 9) Health Check

Run in every sweep / before each Sunday window:

```bash
mise exec -- unifictl local device list -o json   # all core switches state=1
# plus §6 Test 1 (auto_upgrade false, no upgrade scheduletask)
```

Expected:
- Core switches online on the same firmware line; auto-update off.

---

## 10) Security Check

```bash
mise exec -- unifictl local log admin-activity --limit 50
```

Expected:
- Firmware changes correlate with a planned window and a known admin.
- No credentials, controller URLs with secrets, or device MACs are committed to this repo.
- Security-relevant firmware (vendor advisory) is still applied promptly — in the next
  Sunday window, or an extra attended window if the advisory is critical.

---

## 11) Rollback Plan

**Firmware rollback (per device):** the controller keeps `previous_firmware_version` and
`previous_firmware_url` on the device object (read them from the §4.1 pre-state file).
In the Network UI: Devices > select device > Settings > Manage > Custom Upgrade -> paste the
previous firmware URL. Same one-at-a-time rule and §4.2/§4.5 gates apply.

**Setting rollback:** the before-state on 2026-09-25 was `auto_upgrade: false`,
`auto_upgrade_hour: 3`. Re-enabling device auto-update is **not recommended** — if ever
done, it applies to both core switches at the same hour, which recreates this incident.

---

## 12) References

- `docs/sops/unifi-controller-rate-limit.md` (auth triage, §4.4 — never retry into a 429)
- `docs/sops/maintenance-windows.md`, `runbooks/maintenance-windows.yaml` (`sun-attended`)
- `docs/sops/talos-upgrade.md` (serial-with-etcd-gate precedent)
- Finding `F-784aa78f`

---

## Version History

- `2026.09.25`: Initial version after the 2026-09-24 dual-switch firmware partition.
