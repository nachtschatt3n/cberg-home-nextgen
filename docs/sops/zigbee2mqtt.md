# SOP: Zigbee2MQTT operations

> Description: Lifecycle operations for the Zigbee2MQTT (Z2M) deployment and its mesh — opening/closing `permit_join`, removing devices safely, recovering from interview failures on CC2652-class router firmware, backup/restore, and post-incident smoke testing.
> Version: `2026.07.14`
> Last Updated: `2026-07-14`
> Owner: `cberg-home-ops`

---

## 1) Description

Covers everyday Z2M operations and incident recovery for the home-automation Zigbee mesh.

- Scope: `home-automation/zigbee2mqtt` HelmRelease, the Zigbee mesh (one SLZB-06P10 coordinator + SLZB-06P7 router + ~20 end devices), and the MQTT broker integration.
- Prerequisites: `kubectl` access, MQTT publish access to the mosquitto broker (LAN host can reach `192.168.55.15:1883` anonymously; in-cluster pods can reach `mosquitto-internal.home-automation.svc.cluster.local:1883`).
- Out of scope: changes to the mosquitto broker itself — see the mosquitto HelmRelease + the broker hygiene PR series; Zigbee channel/PAN migration (rare, requires re-pairing every device).

**The bright-line rule of this SOP:** never use `bridge/request/device/remove` with `force:true` without completing the 3-step pre-flight in §4. Force-removing a SMLIGHT router and then reflashing it has cascaded into a multi-hour incident before (2026-06-04).

---

## 2) Overview

| Setting | Value |
|---|---|
| Namespace | `home-automation` |
| Z2M HelmRelease | `kubernetes/apps/home-automation/zigbee2mqtt/app/helmrelease.yaml` |
| Z2M data PVC | `zigbee2mqtt-data` (Longhorn) |
| Z2M frontend | `the `zigbee2mqtt` internal ingress (`zigbee2mqtt.${SECRET_DOMAIN}`)` |
| Coordinator | SLZB-06P10 @ `192.168.32.20`, IEEE `0x00124b00336cc62a`, TCP serial `tcp://192.168.32.20:6638` |
| Router (mesh) | SLZB-06P7 @ `192.168.32.21`, IEEE `0x00124b0031dffd19` (factory; previously `0x00124b002d12beec` before reflash) |
| MQTT broker (in-cluster target) | `mqtt://mosquitto-internal.home-automation.svc.cluster.local:1883` |
| MQTT broker (LAN clients) | `192.168.55.15:1883` (mosquitto-main LB) |
| Backups | Longhorn `daily-backup-all-volumes` @ 03:00, retain 7 (per `kubernetes/apps/storage/longhorn/app/recurring-backup-job.yaml`) |

---

## 3) Blueprints

- Source of truth: `kubernetes/apps/home-automation/zigbee2mqtt/app/helmrelease.yaml`
- Z2M runtime state (not in git, lives in PVC): `/data/database.db`, `/data/state.json`, `/data/coordinator_backup.json`, `/data/configuration.yaml`
- Device definitions (upstream): [zigbee-herdsman-converters `src/devices/smlight.ts`](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/smlight.ts) — covers SLZB-06, SLZB-06P7, SLZB-06P10, SLZB-06M, etc.

`/data/database.db` is a line-delimited JSON file. One device per line; each line is a complete JSON object with at least: `id`, `type` (`Coordinator|Router|EndDevice|Unknown`), `ieeeAddr`, `nwkAddr`, `epList`, `endpoints`, `interviewCompleted`, `interviewState`, plus optional `manufId`, `manufName`, `modelId`, `powerSource`, `lastSeen`.

---

## 4) Operational Instructions

### 4a) Open / close `permit_join` (correct API)

The Z2M API for `bridge/request/permit_join` expects `{"time": N}`. To **close**, send `{"time": 0}`. Sending `{"value": false}` produces `Invalid payload`.

```bash
# Open 254s (max)
mise exec -- kubectl -n home-automation exec deploy/mosquitto -c app -- mosquitto_pub \
  -h 127.0.0.1 -p 1883 \
  -t zigbee2mqtt/bridge/request/permit_join \
  -m '{"value": true, "time": 254}'

# Close
mise exec -- kubectl -n home-automation exec deploy/mosquitto -c app -- mosquitto_pub \
  -h 127.0.0.1 -p 1883 \
  -t zigbee2mqtt/bridge/request/permit_join \
  -m '{"time": 0}'

# Verify
mise exec -- kubectl -n home-automation exec deploy/mosquitto -c app -- mosquitto_sub \
  -h 127.0.0.1 -p 1883 -t zigbee2mqtt/bridge/info -C 1 -W 5 \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('permit_join =', d.get('permit_join'))"
```

### 4b) Remove a device (3-step pre-flight)

Before any `bridge/request/device/remove`, especially with `force:true`:

1. **Inventory snapshot.** Capture the current `bridge/devices` for the IEEE — friendly_name, type, model, last_seen, networkAddress. Save to a file.
2. **Verify the IEEE belongs to a real device.** Check the device exists physically (look at the SLZB UI for a router, check HA for an end device). If you can't find it, it may be a ghost from a prior reflash — see §8 Diagnose Example 2.
3. **Confirm intent with the operator.** `force:true` removes a device even if it isn't responding; the device's NV still claims to be on the network and will keep beaconing. This is rarely the right call.

```bash
# Soft remove (recommended) — sends leave to the device, waits for ack
mosquitto_pub -h 192.168.55.15 -t zigbee2mqtt/bridge/request/device/remove \
  -m '{"id": "<friendly_name_or_IEEE>"}'

# Force remove (rare) — only after the 3-step pre-flight
mosquitto_pub -h 192.168.55.15 -t zigbee2mqtt/bridge/request/device/remove \
  -m '{"id": "<friendly_name_or_IEEE>", "force": true}'
```

After any remove, `bridge/event` publishes `{"type": "device_leave"}` and `homeassistant/.../config` topics are cleared with empty retained payloads. HA dashboards referencing the removed device's friendly_name need updating.

### 4c) Add an external converter (skip when DB injection is cleaner)

External converters live in `/data/external_converters/<file>.js`. They require the device to first send a recognisable frame (i.e. interview must succeed enough to read `modelId`). For devices where interview itself fails — like CC2652-class routers — external converters do **not** help. Use **DB injection** (§4d) instead.

### 4d) DB injection — recover from interview failure on a CC2652-class router

Use this when a device has joined Z2M but `interviewState=FAILED` with `Interview failed because can not get node descriptor`, and the device's `modelId` is a known router (e.g. `SLZB-06P7`, `SLZB-06P10`, `SLZB-06M`, `SLZB-MR3 CC2674P10`).

Background: ZDO Node Descriptor on CC2652P/CC2674P10 router firmware is unreliable across all SMLIGHT-supplied firmware versions (20221102 / 20250325 / 20250403 verified failing). Refs: [Koenkk/zigbee2mqtt#28050](https://github.com/Koenkk/zigbee2mqtt/issues/28050), [Discussion #9479](https://github.com/Koenkk/zigbee2mqtt/discussions/9479). Reflashing does not fix it. **Reflashing or Mode-toggle wipes the chip's IEEE NV; avoid unless you have an out-of-band way to restore it.**

The fix: pre-populate `/data/database.db` with a complete row for the device so Z2M skips the interview entirely and applies the existing `smlight.ts` definition.

```bash
# 1. Snapshot the DB
mise exec -- kubectl -n home-automation exec deploy/zigbee2mqtt -- \
  cp /data/database.db /data/database.db.bak-$(date +%Y-%m-%d-preinj)

# 2. Scale Z2M to 0 (else it overwrites our edits on auto-save)
mise exec -- kubectl -n home-automation scale deploy/zigbee2mqtt --replicas=0
# Wait for pod terminated:
until ! mise exec -- kubectl -n home-automation get pods -l app.kubernetes.io/name=zigbee2mqtt --no-headers 2>/dev/null | grep -q .; do sleep 2; done

# 3. Apply the one-shot edit pod
cat <<'YAML' | mise exec -- kubectl apply -f -
apiVersion: v1
kind: Pod
metadata: { name: z2m-db-fix, namespace: home-automation }
spec:
  restartPolicy: Never
  containers:
    - name: edit
      image: ghcr.io/koenkk/zigbee2mqtt:2.11.0
      command: ["sh","-c","sleep 600"]
      volumeMounts: [{ name: data, mountPath: /data }]
      securityContext: { runAsUser: 0 }
  volumes:
    - name: data
      persistentVolumeClaim: { claimName: zigbee2mqtt-data }
YAML
until mise exec -- kubectl -n home-automation get pod z2m-db-fix -o jsonpath='{.status.phase}' 2>/dev/null | grep -q Running; do sleep 2; done

# 4. Write the patch script and run it
cat <<'JS' > /tmp/z2m-db-fix.js
const fs = require('fs');
const path = '/data/database.db';
const TARGET_IEEE = '0x00124b0031dffd19';   // <-- EDIT: the failing device's IEEE
const TARGET_MODEL = 'SLZB-06P7';            // <-- EDIT: must match a zigbeeModel in smlight.ts

const lines = fs.readFileSync(path, 'utf8').split('\n');
let replaced = false;
const out = lines.map((line) => {
  if (!line.trim()) return line;
  let obj;
  try { obj = JSON.parse(line); } catch (e) { return line; }
  if (obj.ieeeAddr !== TARGET_IEEE) return line;
  const fixed = {
    id: obj.id, type: 'Router', ieeeAddr: TARGET_IEEE, nwkAddr: obj.nwkAddr,
    manufId: 0, manufName: 'SMLIGHT', powerSource: 'Mains (single phase)',
    modelId: TARGET_MODEL, epList: [1],
    endpoints: { '1': {
      profId: 260, epId: 1, devId: 1,
      inClusterList: [0, 3, 6], outClusterList: [0],
      clusters: { genBasic: { attributes: {
        modelId: TARGET_MODEL, manufacturerName: 'SMLIGHT',
        powerSource: 1, zclVersion: 8, hwVersion: 1,
        dateCode: '20221102', swBuildId: '20221102',
      } } },
      binds: [], configuredReportings: [], meta: {},
    } },
    interviewCompleted: true, interviewState: 'SUCCESSFUL',
    meta: {}, lastSeen: obj.lastSeen || Date.now(),
  };
  replaced = true;
  console.error(`replacing id=${obj.id} ieee=${obj.ieeeAddr} (was type=${obj.type}, state=${obj.interviewState})`);
  return JSON.stringify(fixed);
});
if (!replaced) { console.error('ERROR: target ieee not found'); process.exit(2); }
fs.writeFileSync(path, out.join('\n'));
console.error('done');
JS
mise exec -- kubectl -n home-automation cp /tmp/z2m-db-fix.js home-automation/z2m-db-fix:/tmp/fix.js
mise exec -- kubectl -n home-automation exec z2m-db-fix -- node /tmp/fix.js

# 5. Tear down the edit pod and bring Z2M back
mise exec -- kubectl -n home-automation delete pod z2m-db-fix --wait=false
mise exec -- kubectl -n home-automation scale deploy/zigbee2mqtt --replicas=1
until mise exec -- kubectl -n home-automation get pod -l app.kubernetes.io/name=zigbee2mqtt -o jsonpath='{.items[0].status.containerStatuses[0].ready}' 2>/dev/null | grep -q true; do sleep 3; done

# 6. Verify (see §6 Test 2)

# 7. Optional: rename the device
mosquitto_pub -h 192.168.55.15 -t zigbee2mqtt/bridge/request/device/rename \
  -m '{"from":"0x00124b0031dffd19","to":"SLZB-06 Router-tub-room"}'
```

### 4e) GitOps for HelmRelease changes

All Z2M / mosquitto HelmRelease edits go through Flux:

```bash
# Edit kubernetes/apps/home-automation/zigbee2mqtt/app/helmrelease.yaml
git add kubernetes/apps/home-automation/zigbee2mqtt/app/helmrelease.yaml
git commit -m "feat(zigbee2mqtt): <what changed>"
git push
# Flux webhook reconciles within ~30s; verify:
mise exec -- flux get helmreleases -n home-automation zigbee2mqtt
```

### 4f) SLZB router present on LAN but dropped from the mesh — remote radio-reboot + rejoin

Use this when the **SLZB-06 router** (`0x00124b0031dffd19`, "SLZB-06 Router-tub-room") disappears from the mesh but the device itself is still powered and on the LAN. This is a **different failure** from the CC2652 interview bug (§4d) and from a real power/PoE outage at the location — do not confuse them.

**Fingerprint (all four must hold):**

1. The SLZB core answers on the LAN: `ping 192.168.32.21` succeeds, and `http://192.168.32.21/metrics` + `http://192.168.32.21/ha_sensors` respond.
2. `/ha_sensors` shows **`"ethernet":true`** (PoE Ethernet link up) — so power + the Basement-SW-48 port-18 uplink are working. This **rules out a power/PoE outage** (would need a physical trip) and a down switch port.
3. Z2M still has the router in the DB with `interview_completed: true` (via `bridge/devices`) — so this is **not** the §4d interview bug (which shows `interview_completed: false` / `interviewState=FAILED`).
4. A live networkmap scan shows the router node with **`failed: ["lqi","routingTable"]` and 0 links**, and a **stale `lastSeen`** (days/weeks old). This is the definitive "radio is not in the mesh right now" signal.

```bash
# Fingerprint checks
ping -c3 192.168.32.21
curl -s http://192.168.32.21/ha_sensors    # want "ethernet":true
# Router DB state (interview_completed should be true → NOT the §4d bug):
mise exec -- kubectl -n home-automation exec deploy/mosquitto -c app -- mosquitto_sub \
  -h 127.0.0.1 -p 1883 -t zigbee2mqtt/bridge/devices -C 1 -W 8 \
  | python3 -c "import sys,json;[print(x.get('interview_completed'),x.get('type')) for x in json.load(sys.stdin) if x.get('ieee_address')=='0x00124b0031dffd19']"
# Live mesh state (want links>0 and no 'failed' fields):
mise exec -- kubectl -n home-automation exec deploy/mosquitto -c app -- mosquitto_pub \
  -h 127.0.0.1 -p 1883 -t zigbee2mqtt/bridge/request/networkmap -m '{"type":"raw","routes":true}'
# then read zigbee2mqtt/bridge/response/networkmap and inspect the router node's 'failed' + link count
```

Note: the router has `availability:false` in Z2M (CC2652 routers fail Z2M's ZDO availability pings), so **`+/availability` and `bridge/health` will NOT tell you it dropped** — the networkmap `failed`/link check and `lastSeen` are the only reliable live signals. A childless router that rejoins may also stay silent in Z2M logs; re-run the networkmap to confirm, don't wait for a log line.

**Recovery ladder — remote-first, least-invasive first. The device is reachable, so none of steps 1–3 need a physical trip:**

1. **Radio-only restart (least invasive).** SLZB web UI `http://192.168.32.21` → **Settings and Tools → General settings → "Zigbee Restart"** (button, left of the row; **do NOT** click the adjacent "Zigbee Flash Mode" — that drops the CC2652 into the bootloader and risks the NV/IEEE). This resets only the CC2652 (`zb_temp` in `/ha_sensors` jumps; `device uptime` is unchanged because the ESP32 core is not rebooted). Wait ~2 min, re-run the networkmap. If the router now has links and a fresh `lastSeen` → done, go to the re-home step.
2. **If no rejoin: "Router Reconnect" and/or a full device Reboot.** Same General-settings page has a **"Router Reconnect"** button (tells the router to reconnect to its commissioned network) — no `permit_join` needed. A full device **Reboot** (bottom-left of the UI) power-cycles Core + Radio (device drops off the LAN ~10–20 s, then rejoins from NV); heavier but sometimes needed when a radio-only restart doesn't take.
3. **If still no rejoin: re-join with `permit_join`.** Open `permit_join` on the coordinator (§4a, `{"time":254}`), trigger the join from the SLZB UI ("Router Reconnect"), watch for the device announce, then **close `permit_join`** (`{"time":0}`). This is the escalation gate — get operator go-ahead before opening the join window.
4. **Physical trip only as last resort.** If steps 1–3 all fail with the core still healthy (LAN-reachable, `ethernet:true`), the radio's network NV no longer holds valid membership and it will not re-commission over the air — the CC2652 radio hardware/NV is the remaining suspect. This is the point to visit the site: inspect the unit, and if it still won't rejoin, plan a replacement. **Observed at least once (2026-07-14) that the entire remote ladder — radio restart, Router Reconnect, full device reboot, and `permit_join` + Router Reconnect — all failed to rejoin,** so do not expect remote recovery to always succeed; when all rungs fail, escalate to hardware rather than re-looping the ladder.

**After the router is back:** re-home any sleepy end-devices that were parented through it and got orphaned when it dropped (they show a stale `lastSeen` from the same event; Aqara devices don't re-parent on their own). Open `permit_join` briefly and press the device's pair button once — see §5 Example A. Track which children were affected via each device's `lastSeen` in the networkmap.

**Worked example (2026-07-14):** the tub-room router had been out of the mesh since 2026-06-03 (`lastSeen` 40.7 days stale, networkmap `failed:[lqi,routingTable]`, 0 links) while the core stayed LAN-reachable with `ethernet:true` and `interview_completed:true` — matching this fingerprint, not §4d and not a power outage (the same event orphaned the "Entry Door" Aqara child, which shares the 2026-06-03 `lastSeen`). **The entire remote ladder was worked and ALL of it failed:** (1) radio-only "Zigbee Restart" reset the CC2652 (`zb_temp` moved) but did not rejoin; (2) "Router Reconnect" — no change; (3) a full device **Reboot** (confirmed: `/ha_sensors` `uptime` reset to ~150 s, `ethernet:true` back) still did not rejoin from NV; (4) a bounded `permit_join` `{"time":180}` on the coordinator with "Router Reconnect" produced no device announce/interview/join in the Z2M logs — the router stayed `failed:[lqi,routingTable]` / 0 links / stale `lastSeen` throughout, while the rest of the mesh stayed healthy (14 coordinator links). `permit_join` was explicitly closed afterward and confirmed `permit_join:false`. Conclusion: remote recovery exhausted → the radio's NV/hardware is the cause and a **physical site visit / replacement** is required. Verify between every rung and stop the instant `lastSeen` goes fresh + `failed` clears + links appear; do not re-loop the ladder once all four rungs have failed.

---

## 5) Examples

### Example A: Re-pair a new sensor

```bash
# Open the window
mosquitto_pub -h 192.168.55.15 -t zigbee2mqtt/bridge/request/permit_join -m '{"value": true, "time": 254}'
# Press the pair button on the device
# Watch z2m logs:
mise exec -- kubectl -n home-automation logs deploy/zigbee2mqtt -f | grep -iE "joined|interview"
# When successful, rename and close
mosquitto_pub -h 192.168.55.15 -t zigbee2mqtt/bridge/request/device/rename -m '{"from":"<IEEE>","to":"Living Room Sensor"}'
mosquitto_pub -h 192.168.55.15 -t zigbee2mqtt/bridge/request/permit_join -m '{"time": 0}'
```

### Example B: A SLZB router joins but interview fails

Use §4d (DB injection). Do **not** reflash the radio firmware — Node Descriptor fails identically on all 3 SMLIGHT-supplied router firmwares (20221102 / 20250325 / 20250403), and each reflash risks NV wipe.

---

## 6) Verification Tests

### Test 1: bridge state is healthy

```bash
mise exec -- kubectl -n home-automation exec deploy/mosquitto -c app -- mosquitto_sub \
  -h 127.0.0.1 -p 1883 -t zigbee2mqtt/bridge/info -t zigbee2mqtt/bridge/devices \
  -W 5 -C 2 -v
```

Expected:
- `bridge/info` shows `permit_join` matching what you set (`false` when idle)
- `bridge/devices` count = expected number; no entries with `type=Unknown` and `interview_completed=false` (other than known-pending devices)

If failed:
- Check pod status: `mise exec -- kubectl -n home-automation get pods -l app.kubernetes.io/name=zigbee2mqtt`
- Tail logs: `mise exec -- kubectl -n home-automation logs deploy/zigbee2mqtt --tail=200`

### Test 2: a known router is in the right state

```bash
mise exec -- kubectl -n home-automation exec deploy/mosquitto -c app -- mosquitto_sub \
  -h 127.0.0.1 -p 1883 -t zigbee2mqtt/bridge/devices -C 1 -W 5 \
  | python3 -c "
import sys,json
devs = json.load(sys.stdin)
m = [x for x in devs if x.get('ieee_address') == '0x00124b0031dffd19']
if not m: print('MISSING'); exit(1)
d = m[0]; defn = d.get('definition') or {}
assert d['type'] == 'Router', d['type']
assert d['interview_completed'] is True
assert d['supported'] is True
assert defn.get('model') == 'SLZB-06P7'
print('ok')
"
```

Expected:
- `ok`

If failed:
- The DB-injection row may have drifted; rerun §4d with the snapshot as a reference.

### Test 3: mesh has at least one Router

```bash
mise exec -- kubectl -n home-automation exec deploy/mosquitto -c app -- mosquitto_pub \
  -h 127.0.0.1 -p 1883 -t zigbee2mqtt/bridge/request/networkmap \
  -m '{"type":"raw","routes":true}'
# Then read response (give it ~30-60s):
mise exec -- kubectl -n home-automation exec deploy/mosquitto -c app -- mosquitto_sub \
  -h 127.0.0.1 -p 1883 -t zigbee2mqtt/bridge/response/networkmap -C 1 -W 90
```

Expected:
- Response status `ok` with a node list that includes the coordinator and at least one Router-typed node.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---|---|---|
| `Interview failed because can not get node descriptor` on a SLZB router | Class-wide CC2652 ZDO bug | §4d DB injection — **do not reflash** |
| Router `lastSeen` stale (days/weeks) + networkmap `failed:[lqi,routingTable]` + 0 links, but core pingable & `/ha_sensors` `ethernet:true` | Radio dropped from mesh while device stays powered/on-LAN (not the §4d interview bug, not a power outage) | §4f: SLZB UI **General settings → "Zigbee Restart"**; if no rejoin → "Router Reconnect" / device Reboot → `permit_join` + join; physical trip only if all fail |
| `bridge/request/permit_join` returns `Invalid payload` | Used `{"value": false}` to close | Use `{"time": 0}` — see §4a |
| Device suddenly missing from `bridge/devices` | Z2M restart + low-prior-message device may have been pruned (esp. with `leave_count > 0`) | Restore from the daily Longhorn backup of `zigbee2mqtt-data`, or rejoin via permit_join |
| HA entities for a device vanish after rename | Z2M cleared the old HA discovery configs and republished under new friendly_name | Update HA dashboards/automations to the new entity IDs |
| Z2M frontend shows "Cannot GET /devices" | Direct hash-routes don't always work | Go to root (`/`) and click Devices in the nav |
| Coordinator not shown in Devices tab | By design ([Koenkk/zigbee2mqtt#1143](https://github.com/Koenkk/zigbee2mqtt/issues/1143)) | Use Network Map or `bridge/info.coordinator` instead |

---

## 8) Diagnose Examples

### Diagnose Example 1: device claims to be online but mesh shows no traffic

```bash
mise exec -- kubectl -n home-automation exec deploy/mosquitto -c app -- mosquitto_sub \
  -h 127.0.0.1 -p 1883 -t zigbee2mqtt/bridge/health -C 1 -W 12 \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
ieee = '<IEEE>'   # set me
stats = d.get('devices', {}).get(ieee, {})
print(f'messages={stats.get(\"messages\")} per_sec={stats.get(\"messages_per_sec\")} '
      f'leave_count={stats.get(\"leave_count\")} nwk_changes={stats.get(\"network_address_changes\")}')
print(f'(window uptime: {d.get(\"process\",{}).get(\"uptime_sec\")} sec)')
"
```

Expected:
- For an actively-routing device: `messages_per_sec > 0.001` and `leave_count = 0`. If `messages = 1` over 60 min, the chip is silent — see §4d.

If unclear:
- Request a networkmap and check whether the device appears in `links` at all (Test 3).

### Diagnose Example 2: a "ghost" device that doesn't physically exist

If a router (e.g. `0x00124b00xxxxxxxx`) shows up after a SLZB reflash and you only have N physical SLZB devices, the chip's factory-default IEEE may have briefly beaconed during the reflash, leaving a ghost row in Z2M.

```bash
# Confirm: count physical SLZBs on the LAN
for ip in 192.168.32.20 192.168.32.21 ...; do
  resp=$(curl -sS --max-time 2 "http://$ip/api2?action=4&cmd=0")
  [[ "$resp" == "ok" ]] && echo "SLZB at $ip"
done
```

Expected:
- The number of SLZB responders equals the number of physical units you own.

If unclear:
- Inspect the SMLIGHT dashboard for each unit — confirm their IEEE in `Dashboard → Device information`. Compare to Z2M's `bridge/devices` IEEE list. Any extra Z2M entry without a physical match is a ghost — clean it up with `device/remove` (soft, not force) after disabling permit_join.

---

## 9) Health Check

```bash
# Pod ready
mise exec -- kubectl -n home-automation get pods -l app.kubernetes.io/name=zigbee2mqtt
# HelmRelease reconciled
mise exec -- flux get helmreleases -n home-automation zigbee2mqtt
# Bridge state online
mise exec -- kubectl -n home-automation exec deploy/mosquitto -c app -- \
  mosquitto_sub -h 127.0.0.1 -p 1883 -t zigbee2mqtt/bridge/state -C 1 -W 4
# Longhorn backup of zigbee2mqtt-data within last 24h
mise exec -- kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,LAST_BACKUP_AT:.status.lastBackupAt --no-headers \
  | awk '$1 == "zigbee2mqtt-data"'
```

Expected:
- Pod `Ready 1/1`
- HelmRelease `Ready=True`
- `bridge/state` returns `{"state":"online"}`
- `LAST_BACKUP_AT` within the last 24h

---

## 10) Security Check

Z2M operates on the LAN (broker at `192.168.55.15:1883` is plaintext, anonymous is allowed — accepted risk). Verify:

```bash
# No Z2M secrets in plaintext in the repo:
git -C . grep -E 'network_key|ext_pan_id' kubernetes/apps/home-automation/zigbee2mqtt | grep -v "test\|sample"
# Ingress is internal-only (no LAN→WAN exposure of the Z2M frontend):
mise exec -- kubectl -n home-automation get ingress zigbee2mqtt -o jsonpath='{.spec.ingressClassName}'
# permit_join is closed when not in active pairing:
mise exec -- kubectl -n home-automation exec deploy/mosquitto -c app -- mosquitto_sub \
  -h 127.0.0.1 -p 1883 -t zigbee2mqtt/bridge/info -C 1 -W 4 \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('permit_join') is False; print('closed')"
```

Expected:
- `grep` returns nothing
- IngressClassName is `internal`
- `closed`

---

## 11) Rollback Plan

### Rollback the DB injection from §4d

```bash
mise exec -- kubectl -n home-automation scale deploy/zigbee2mqtt --replicas=0
until ! mise exec -- kubectl -n home-automation get pods -l app.kubernetes.io/name=zigbee2mqtt --no-headers 2>/dev/null | grep -q .; do sleep 2; done

# Re-apply the one-shot edit pod from §4d step 3, then:
mise exec -- kubectl -n home-automation exec z2m-db-fix -- \
  cp /data/database.db.bak-2026-06-04-preinj /data/database.db
mise exec -- kubectl -n home-automation delete pod z2m-db-fix --wait=false
mise exec -- kubectl -n home-automation scale deploy/zigbee2mqtt --replicas=1
```

### Rollback a HelmRelease change

Standard Flux rollback:

```bash
mise exec -- flux suspend helmrelease zigbee2mqtt -n home-automation
git revert <commit>
git push
mise exec -- flux resume helmrelease zigbee2mqtt -n home-automation
```

### Rollback to a Longhorn backup (full PVC restore)

If the DB is corrupted beyond surgical repair: restore from the daily backup of `zigbee2mqtt-data`. Procedure in `docs/sops/disaster-recovery.md`. Note the cost — restores the entire PVC state from up to 24h ago.

---

## 12) References

- [Koenkk/zigbee2mqtt#28050 — CC2674P10 chipset as router (fixed-in-dev)](https://github.com/Koenkk/zigbee2mqtt/issues/28050)
- [Koenkk/zigbee2mqtt#9479 — CC2652R does not work as a router](https://github.com/Koenkk/zigbee2mqtt/discussions/9479)
- [Koenkk/zigbee2mqtt#1143 — device list doesn't contain coordinator (by design)](https://github.com/Koenkk/zigbee2mqtt/issues/1143)
- [zigbee-herdsman-converters smlight.ts (device definitions)](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/smlight.ts)
- [Z2M MQTT API — bridge requests](https://www.zigbee2mqtt.io/guide/usage/mqtt_topics_and_messages.html)
- [SMLIGHT Router mode manual](https://smlight.tech/support/manuals/books/slzb-07pxmgx/page/zigbee-router-mode)
- `kubernetes/apps/home-automation/zigbee2mqtt/app/helmrelease.yaml`
- `kubernetes/apps/home-automation/mosquitto/app/helmrelease.yaml`
- `kubernetes/apps/storage/longhorn/app/recurring-backup-job.yaml`

---

## Version History

- `2026.07.14`: add §4f (SLZB router present on LAN but dropped from the mesh — remote radio-reboot + rejoin ladder) and matching troubleshooting row. Distinguishes this failure (stale `lastSeen` + networkmap `failed:[lqi,routingTable]` + core reachable/`ethernet:true`) from the §4d interview bug and from a real power/PoE outage. Captures the 2026-07-14 tub-room recovery: a radio-only "Zigbee Restart" did not rejoin the mesh, requiring escalation.
- `2026.06.04`: initial SOP. Captures lessons from the 2026-06-04 incident: SLZB-06P7 force-remove → reflash cycle → Node Descriptor failure → DB-injection recovery; corrects `permit_join` close API; documents Longhorn backup retention bump 1→7; adds CC2652-router-as-router workaround procedure.
