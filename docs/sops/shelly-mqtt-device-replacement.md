# SOP: Shelly / MQTT Device Replacement

> Description: Replacing (or decommissioning) a Shelly unit so that no stale identity survives it — the retained MQTT `online` topic, the orphan Home Assistant device, the Uptime Kuma monitor pointing at the dead address, and the household health probes that key on it.
> Version: `2026.09.22`
> Last Updated: `2026-09-22`
> Owner: `home-automation`

---

## 1) Description

A Shelly's identity is its **MAC**, not its friendly name. Every consumer keys
on the MAC one way or another: the MQTT topic prefix embeds it, Home
Assistant's `shelly` integration registers the device under
`identifiers: [shelly, <MAC>]`, and DHCP hands the unit its address by it.
Swapping the hardware therefore creates a *second* identity with the same
friendly name — and nothing retires the first one:

- the broker keeps the old unit's Last-Will `…/online false` as a **retained**
  message, forever, because Mosquitto persistence is on;
- HA keeps the old device entry, pointing at the dead IP;
- the Uptime Kuma monitor keeps pinging the old address until someone edits it;
- the sweep's health probe fires on that address every cycle with a false
  "function lost" premise.

Measured 2026-09-22 for the swap that raised `F-77c8664c`/`F-9601f761`: the
retained `online false` of the decommissioned MAC is still on the broker, HA's
registry holds two `shelly` devices with the same name (one with the dead
`configuration_url`), the Kuma monitor had already been repointed to the new
address (status UP), and the old address still returns no HTTP.

- Scope: Shelly Gen2/Gen3 units (`shellyplus*`, `shellyplug*`,
  `shellypro*`, wall displays) publishing to `home-automation/mosquitto` and
  integrated in Home Assistant; their Uptime Kuma ping monitors.
- Prerequisites: `kubectl` (mosquitto pod exec), `hactl`
  (`/Users/mu/code/hactl`, `mise exec -- hactl`), Uptime Kuma UI access, the
  new unit's friendly name and — if you can read it off the device — its MAC.
- Out of scope: Zigbee devices (`docs/sops/zigbee2mqtt.md`), the broker itself.

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Broker | `deployment/mosquitto` in `home-automation`, `eclipse-mosquitto:2.0.22`; `persistence true` on `/data` (retained messages survive restarts); `allow_anonymous true` (in-pod `mosquitto_pub/_sub` need no credentials) |
| Topic shape | `shellies/<model>-<mac>-<friendly name>/…` — a **custom `topic_prefix`** set on each unit (`/rpc/MQTT.GetConfig`), so the MAC is in the topic |
| Availability topic | `<prefix>/online` — `true` while connected, `false` published **retained** by the broker as the unit's Last Will |
| HA integration | native `shelly` (RPC over HTTP/websocket), device `identifiers: [["shelly","<MAC>"]]`, `configuration_url: http://<ip>` — **not** MQTT discovery (the `mqtt` integration exists but no Shelly device carries an `mqtt` identifier, checked 2026-09-22) |
| Kuma | `ping` monitors named `Shelly <model> <friendly name>`, under a group monitor `Shelly`; UI-managed on PVC `kuma-monitoring-config`; scraped into Prometheus as `monitor_status{monitor_name,monitor_hostname}` |
| Health probes | `runbooks/health-check.sh` §40 classifies `^Shelly` monitors as `info`; the health-check agent additionally `curl`s `http://<monitor host>/rpc/Shelly.GetStatus` and files a finding on `http=000` |
| Other MQTT consumers | Node-RED (`/data/flows.json` carried 0 `shellies/` topic references on 2026-09-22); ioBroker's Shelly MQTT adapter is commented out |

---

## 3) Blueprints

N/A — nothing about a Shelly is declared in git. The device's own config, the
broker's retained store, HA's device registry and Kuma's SQLite are four
separate, imperative stores, which is exactly why this SOP exists.

Useful read-only RPCs (Gen2+, verified 2026-09-22 against a live unit):

```bash
curl -s http://<ip>/rpc/Shelly.GetDeviceInfo   # name, id, mac, model, gen, fw_id, app
curl -s http://<ip>/rpc/MQTT.GetConfig          # enable, server, client_id, topic_prefix, rpc_ntf, status_ntf
curl -s http://<ip>/rpc/Shelly.GetStatus        # what the health probe calls
```

---

## 4) Operational Instructions

### Step 0 — Inventory the OLD unit before it is unplugged (if it still answers)

```bash
OLD_IP=<old-ip>
curl -s http://$OLD_IP/rpc/Shelly.GetDeviceInfo | /usr/bin/python3 -m json.tool   # note: mac, name
curl -s http://$OLD_IP/rpc/MQTT.GetConfig | /usr/bin/python3 -c 'import sys,json;print(json.load(sys.stdin)["topic_prefix"])'
```

If the old unit is already dead, recover the same facts from the other stores:

```bash
# MQTT: every identity carrying the friendly name (the retained one is the old unit)
kubectl -n home-automation exec deploy/mosquitto -c app -- \
  mosquitto_sub -h 127.0.0.1 -p 1883 -t 'shellies/+/online' -W 8 -v | grep -i '<friendly name>'
# HA: devices with that name -> two DIFFERENT shelly identifiers (MACs) = one is the orphan
cd /Users/mu/code/hactl && mise exec -- hactl get devices --format json | /usr/bin/python3 -c "
import sys,json
for x in json.load(sys.stdin):
    if '<friendly name>'.lower() in ((x.get('name_by_user') or x.get('name') or '').lower()):
        print(x['id'], x.get('name'), x.get('identifiers'), x.get('configuration_url'))"
```

> **Read the HA output carefully.** On 2026-09-22 the listing showed most
> Shelly names *twice* with **identical** identifiers (cause not established —
> treat it as a listing artefact). The decommissioned-unit signal is one
> friendly name with two **different** `shelly` MACs, one of whose
> `configuration_url` no longer answers. Do not delete on name alone.

Record: old MAC, old topic prefix, old IP, HA device id(s), Kuma monitor name.

### Step 1 — Commission the NEW unit

1. Power it, join it to the IoT SSID, give it the **same friendly name**.
2. Set MQTT on the unit (server = the broker's LAN address, `topic_prefix`
   in the house shape `shellies/<model>-<mac>-<friendly name>`, RPC + status
   notifications on) — mirror `MQTT.GetConfig` from a sibling unit.
3. HA discovers it (native `shelly` integration) as a **new** device. If the
   old device still exists, the new one's entities may get `_2` suffixes —
   check with `hactl get states | grep <slug>` and fix the ids after Step 3.
4. Optional, if the old unit had a DHCP reservation: move it to the new MAC
   or delete it (`unifictl local client list` → controller UI). Whether a
   reservation existed for the 2026-09 swap was **not verified**; the
   replacement received a dynamic lease, which is consistent with the old MAC
   having held a reservation.

### Step 2 — Clear the OLD identity on the broker (STATE CHANGE, operator-approved)

Only for the MAC you confirmed decommissioned. Several live units legitimately
sit at `online false` (sleeping battery devices, units awaiting power) — the
2026-09-22 census had five such rows, four of them real inventory.

```bash
OLD_PREFIX='shellies/<model>-<old-mac>-<friendly name>'
# 1. what is retained under that prefix? (usually only /online)
kubectl -n home-automation exec deploy/mosquitto -c app -- \
  mosquitto_sub -h 127.0.0.1 -p 1883 -t "$OLD_PREFIX/#" -W 5 -v
# 2. delete each retained topic found: an EMPTY retained publish clears it
kubectl -n home-automation exec deploy/mosquitto -c app -- \
  mosquitto_pub -h 127.0.0.1 -p 1883 -t "$OLD_PREFIX/online" -r -n
```

Non-destructive: a live unit re-announces itself on its next (re)connect, so
clearing the wrong topic costs one reconnect, not data.

### Step 3 — Remove the orphan device from Home Assistant

```bash
cd /Users/mu/code/hactl
mise exec -- hactl delete device <old-device-id>          # dry-run by default: read the plan
mise exec -- hactl delete device <old-device-id> --yes    # commit
```

(Or Settings → Devices → the device with the dead `configuration_url` →
Delete.) Then rename any `_2`-suffixed entities of the new unit back to the
canonical ids so dashboards and automations keep resolving.

### Step 4 — Repoint the Uptime Kuma monitor, then restart Kuma

In the Kuma UI edit `Shelly <model> <friendly name>` → hostname = the new
unit's address (or delete the monitor if the role is gone). **Then restart
the pod** — the Prometheus exporter keeps emitting the OLD hostname's label-set
until it does (`docs/sops/monitoring.md` §"After editing/removing a monitor"):

```bash
kubectl -n monitoring rollout restart deploy/uptime-kuma
```

### Step 5 — Close the sweep findings

The unreachable-address finding (`F-794c688d` shape) and the duplicate-identity
finding (`F-77c8664c`) both clear on the next cycle once Steps 2–4 hold; if the
address finding was filed under a "function lost" premise, re-title or close it
by hand: `runbooks/policy-cli.py finding close <id>`.

---

## 5) Examples

### Example A: swap after failure (the 2026-09 case)

Old unit dead at its address → Step 0 from stores (retained `online false`
identified the old MAC; HA showed two MACs under one name) → new unit already
commissioned by the household → Kuma had already been repointed (measured UP
on 2026-09-22) → remaining work: Step 2 (clear the retained topic), Step 3
(delete the HA orphan), Step 4's restart.

### Example B: planned replacement, old unit still alive

Step 0 against the live old unit (RPCs), Step 1, then **factory-reset or
power off the old unit before Step 2** — otherwise it reconnects and
re-publishes `online true`, and the "one identity per name" check in §6
fails for the opposite reason.

---

## 6) Verification Tests

### Test 1: exactly one MQTT identity per friendly name

```bash
kubectl -n home-automation exec deploy/mosquitto -c app -- \
  mosquitto_sub -h 127.0.0.1 -p 1883 -t 'shellies/+/online' -W 8 -v \
  | grep -ic '<friendly name>/online'
```

Expected:
- `1`, and that line reads `true`

If failed:
- `2` → Step 2 was skipped or hit the wrong prefix; `0` → the new unit is not publishing (check `MQTT.GetConfig` on it)

### Test 2: one HA device per name, and its entities are fresh

```bash
cd /Users/mu/code/hactl && mise exec -- hactl get devices --format json | /usr/bin/python3 -c "
import sys,json
macs={tuple(i) for x in json.load(sys.stdin) if '<friendly name>'.lower() in ((x.get('name_by_user') or x.get('name') or '').lower()) for i in x.get('identifiers',[]) if i[0]=='shelly'}
print(len(macs), macs)"
mise exec -- hactl get states | grep -i '<entity slug>'
```

Expected:
- `1` distinct `shelly` MAC; the power/energy entities carry a `last_updated` within minutes

If failed:
- the orphan device still exists (Step 3), or the new device's entities are suffixed `_2`

### Test 3: Kuma monitor UP on the new host, no ghost series

```bash
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 &
sleep 3
curl -s 'http://localhost:9090/api/v1/query?query=monitor_status' | /usr/bin/python3 -c "
import sys,json
for r in json.load(sys.stdin)['data']['result']:
    m=r['metric']
    if '<friendly name>'.lower() in m.get('monitor_name','').lower(): print(m['monitor_name'], m.get('monitor_hostname'), r['value'][1])"
```

Expected:
- exactly one series for the monitor, `monitor_hostname` = the new address, value `1`

If failed:
- two series (old + new host) → Step 4's restart was skipped; value `0` → the new address is wrong or the unit is off the network

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| Sweep keeps filing "Shelly `<name>` unreachable at `<old ip>`" although the device works | Kuma monitor still points at the old address (the agent probes the monitor's host) | Step 4, including the restart |
| `mosquitto_sub -t '#'` shows two `<name>/online` rows, one `false` | retained Last Will of the old MAC | Step 2 |
| HA shows the sensor but values never update | the entities resolved to the OLD device; the new one got `_2` ids | Step 3, then rename the new entities |
| Kuma still shows the OLD host DOWN after the edit | exporter label-set cached in memory | `rollout restart deploy/uptime-kuma` |
| `online false` rows for units that were NOT replaced | sleeping battery units / unpowered sockets — normal | leave them; only clear a MAC you have confirmed retired |
| The retained topic comes back after clearing | the old unit is still powered and reconnected | power it off / factory-reset, then clear again |

```bash
kubectl -n home-automation exec deploy/mosquitto -c app -- mosquitto_sub -h 127.0.0.1 -p 1883 -t 'shellies/+/online' -W 8 -v | sort
kubectl -n home-automation logs deploy/mosquitto -c app --tail=2000 | grep -i "<friendly name>" | tail
```

---

## 8) Diagnose Examples

### Diagnose Example 1: "is the old address really dead, or is it the monitor?"

```bash
curl -s -o /dev/null -w 'http=%{http_code} t=%{time_total}\n' --max-time 6 http://<old ip>/rpc/Shelly.GetStatus
curl -s -o /dev/null -w 'http=%{http_code} t=%{time_total}\n' --max-time 6 http://<a sibling ip>/rpc/Shelly.GetStatus   # control, same VLAN
```

Expected:
- old `http=000` after the timeout AND the control `http=200` in well under a second → the address is dead, not the path

If unclear:
- control also `000` → VLAN routing / firewall, not this device; stop and check `unifictl local health get`

### Diagnose Example 2: "which MAC is the live one?"

```bash
kubectl -n home-automation exec deploy/mosquitto -c app -- \
  mosquitto_sub -h 127.0.0.1 -p 1883 -t 'shellies/+/events/rpc' -W 30 -v | grep -i '<friendly name>' | head -3
```

Expected:
- events arrive only under the NEW MAC's prefix; the old prefix stays silent (it publishes nothing but its retained `online`)

If unclear:
- widen to `-t "shellies/<old prefix>/#" -W 60` — any traffic there means the old unit is still alive

---

## 9) Health Check

```bash
# broker-wide: identities at online=false (review, do not act blindly)
kubectl -n home-automation exec deploy/mosquitto -c app -- mosquitto_sub -h 127.0.0.1 -p 1883 -t 'shellies/+/online' -W 8 -v | grep -c false
# HA: names carried by more than one DISTINCT shelly MAC
cd /Users/mu/code/hactl && mise exec -- hactl get devices --format json | /usr/bin/python3 -c "
import sys,json,collections
m=collections.defaultdict(set)
for x in json.load(sys.stdin):
    for i in x.get('identifiers',[]):
        if i[0]=='shelly': m[(x.get('name_by_user') or x.get('name') or '')].add(i[1])
print([n for n,s in m.items() if len(s)>1])"
```

Expected:
- the `false` count matches the known sleeping/unpowered set; the HA list is empty

---

## 10) Security Check

```bash
# the device's own auth state (Gen2 units ship with HTTP auth OFF)
curl -s http://<new ip>/rpc/Shelly.GetDeviceInfo | /usr/bin/python3 -c 'import sys,json;print("auth_en=",json.load(sys.stdin).get("auth_en"))'
```

Expected:
- no device IP, MAC or MQTT credential committed anywhere (this repo is public — this SOP deliberately carries placeholders only)
- the broker's `allow_anonymous true` posture is unchanged by this procedure (it is a pre-existing choice, not something this SOP grants)
- the new unit sits on the IoT VLAN, not on Trusted

---

## 11) Rollback Plan

- Cleared retained topic: nothing to restore — a live unit republishes on
  reconnect. If the "old" unit turns out to be needed, power it on; it
  re-announces itself.
- Deleted HA device: the `shelly` integration re-discovers a powered unit;
  entity ids are recreated (dashboards referencing renamed ids need the rename
  undone).
- Kuma monitor: re-add / re-edit in the UI, then `rollout restart deploy/uptime-kuma`.

---

## 12) References

- Findings: `F-77c8664c` (duplicate identity + retained topic), `F-9601f761` (this SOP gap), `F-794c688d` (the unreachable-address probe)
- `docs/sops/monitoring.md` — Uptime Kuma stale-series restart rule
- `runbooks/health-check.sh` §22a (MQTT/Shelly) and §40 (Kuma classification)
- `docs/sops/sli-catalog.md` #6 — `broker_clients_connected` is broker-wide, not Shelly-only
- `kubernetes/apps/home-automation/mosquitto/app/config/mosquitto.conf`
- Home Assistant `shelly` integration; Shelly Gen2+ RPC (`Shelly.GetDeviceInfo`, `MQTT.GetConfig`)

---

## Version History

- `2026.09.22`: Initial SOP (F-9601f761 / F-77c8664c). Grounded in the 2026-09 swap: broker census, HA registry read via hactl, Kuma series via Prometheus, live RPC reads on a control unit — all read-only.
