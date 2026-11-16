---
plan_id: otbr-thread-rcp-recovery
component: otbr
pr: null                              # no Renovate PR: a sweep FINDING (F-16d94a1b), not a version bump
kind: infra
current: "SLZB-06P7 192.168.33.238 (MAC 0C:DC:7E:36:F8:04): core v3.3.8.dev3 (fw_channel dev, sel_fw_channel any), radio CC2652P7 zb_type 2 (thread) zb_version 20260304; otbr Deployment replicas 0 since 371bac303 (2026-10-30)"
target: "same unit on core SLZB-OS v3.4.3.dev1 (radio firmware UNCHANGED at 20260304), RCP answers a Spinel PROP_VALUE_GET, otbr back at replicas 1 and attached to the same Thread network"
update_type: n/a
risk: medium                          # the device action is a ONE-WAY core flash (v3.3.8.dev3 is no longer on the OTA list),
                                      #   but its only consumer (otbr) is already at 0 and nothing depends on it today:
                                      #   matter-server has 0 commissioned devices and the Thread mesh runs on the Apple
                                      #   border routers. The cluster side is a single-file git revert of a replicas line
est_duration_min: 100                 # 15 pre-checks + 5 backup + 10 flash + 5 Spinel probe + 10 commit/reconcile
                                      #   + 30 soak + 10 verification = 85; +15 for the one allowed forward fallback (3.4)
needs_reboot: false                   # no NODE reboot. The SLZB unit reboots itself as part of the core flash
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/otbr                # git: controllers.otbr.replicas 0 -> 1 (reverse of 371bac303's HR hunk ONLY)
    - deployment/otbr                 # 0 -> 1, strategy Recreate (verified live), pinned to k8s-nuc14-03
    - pvc/otbr-data                   # Longhorn volume pvc-da17b5c6-... is DETACHED today and ATTACHES on scale-up;
                                      #   holds /data/thread (the dataset otbr-agent rejoins with). Not edited
    - service/otbr                    # not edited
    - httproute/otbr                  # not edited (envoy-internal); comes back to life with the pod
  shared:
    - device/slzb-06p7-thread-192.168.33.238   # the ONLY device this plan acts on. UniFi: Guest Room USW SW-8 PORT 7
                                               #   (Ethernet MAC 0c:dc:7e:36:f8:07, UniFi alias "SLZB-06 Router-basement")
    - unifi/guest-room-usw-sw-8       # power-cycle fallback is PORT 7 of the switch that ALSO powers the Zigbee
                                      #   coordinator on PORT 4. Never port 4, never a switch restart
    - thread-mesh                     # our Border Router rejoins the Apple-provisioned Thread network
    - host-netfilter/k8s-nuc14-03     # otbr-agent (hostNetwork) rewrites the node's ip(6)tables on start
    - home-assistant/otbr-integration # HA config entry otbr -> http://192.168.55.13:8081 recovers
    - matter-server                   # same node, consumes Thread routes; 0 commissioned devices today
    - storage/longhorn                # one volume attach (otbr-data)
    - monitoring                      # gate 4.4 cross-checks kube-state-metrics through Prometheus
depends_on: []
conflicts_with:
  - otbr-0.4.0                        # rolls the SAME Deployment; its premises (otbr-available, live imageID) need a
                                      #   running pod. Run THIS first, never in the same slot
  - music-assistant-skill-b1ef33a     # reciprocal (it names this plan): same namespace, HA-adjacent restarts
  - iobroker-v12.0.0-digest-005ba9c   # home-automation roll on the same night muddies attribution of gate 4.6/4.8
  - talos-linux-1.14.6                # node roll reboots k8s-nuc14-03 (otbr's pinned node) and flushes host netfilter
  - talos-linux-1.14.5                # same (sun-attended:2026-11-22)
  - talos-power-tuning-ab             # node-level apply-config on the same node set; keep attribution clean
  - longhorn-1.13.0                   # reciprocal: scale-up ATTACHES otbr-data; never during a Longhorn engine move
  - kube-prometheus-stack-93.3.0      # reciprocal: gate 4.4 reads Prometheus (the window's instrument is shared infra)
exclusive: false
security_ref: null
capability_change: false              # restores the behaviour that ran 2026-09-03 .. 2026-10-28; the core flash adds no
                                      #   feature we use (socket-server mode, same radio firmware, same RCP role)
rollback_class: one-way               # the core flash cannot return to v3.3.8.dev3 (not offered by the OTA API). The
                                      #   git half (replicas) is a clean revert, see section 5
autonomy_override: human-gated        # operator-attended: the flash is OPERATOR-ONLY in the SLZB web UI
finding_refs: [F-16d94a1b, F-6b96ab0c]   # RCP root cause (open); applications.md says otbr re-enabled while live is 0
                                         #   (closes once replicas is back at 1). F-3264f551/F-647d65c6 resolved 10-30
review: null
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/zigbee2mqtt.md          # 4d-bis (read-only SLZB endpoints; never guess /api2 actions) and 4f rung 5
  - docs/sops/longhorn.md             # the otbr-data attach on scale-up
generated: "2026-11-16"
premises:
  - id: otbr-scaled-to-zero-live
    why: >-
      The plan starts from the 371bac303 state. If replicas is not 0, someone already scaled otbr
      back (or a pod is crash-looping again): re-diagnose before touching the device.
    run: kubectl get deploy otbr -n home-automation -o jsonpath='{.spec.replicas}'
    expect_exact: "0"
  - id: otbr-no-pod
    why: >-
      The Spinel probe in 3.3 needs the SLZB socket free. The socket server serves one client, so a
      running otbr pod would hold it and make the probe meaningless.
    run: kubectl get pod -n home-automation -l app.kubernetes.io/name=otbr -o name | wc -l
    expect_exact: "0"
  - id: hr-last-changed-by-scale-down
    why: >-
      Step 3.5 reverse-applies ONLY the helmrelease hunk of 371bac303. That is clean only while
      371bac303 is still the last commit touching the file (dry-checked 2026-11-16 with
      git apply -R --check). If otbr-0.4.0 or anything else edited it since, re-derive the edit.
    run: git log -1 --format=%H -- kubernetes/apps/home-automation/otbr/app/helmrelease.yaml
    expect_exact: "371bac303583369ca1826bbdbb233ab189675b70"
  - id: repo-replicas-zero
    why: >-
      Git must still say replicas 0, exactly once, so the scale-up commit is the one reviewed change.
    run: "git show HEAD:kubernetes/apps/home-automation/otbr/app/helmrelease.yaml | grep -c 'replicas: 0'"
    expect_exact: "1"
  - id: rcp-target-is-wired-p7
    why: >-
      Every device step is aimed at 192.168.33.238. If NETWORK_DEVICE moved (back to the WiFi P7 at
      .32.70, or anything else) the target device is wrong and the plan must be redone.
    run: kubectl get deploy otbr -n home-automation -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="NETWORK_DEVICE")].value}'
    expect_exact: "192.168.33.238:6638"
  - id: image-unchanged
    why: >-
      F-16d94a1b rules out the image (v0.4.0 ran clean 10-16 .. 10-28). If the tag moved, the scale-up
      tests two changes at once.
    run: kubectl get deploy otbr -n home-automation -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/ownbee/hass-otbr-docker:v0.4.0"
  - id: hr-ready
    why: >-
      The scale-up is a Helm upgrade of this release. A release that is not Ready now would fail the
      upgrade for an unrelated reason.
    run: kubectl get helmrelease otbr -n home-automation -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: otbr-data-bound
    why: >-
      The Thread dataset otbr-agent rejoins with lives on this PVC. It must still be Bound to the same
      volume, or the BR would form/join a different network on scale-up.
    run: kubectl get pvc otbr-data -n home-automation -o jsonpath='{.status.phase} {.spec.volumeName}'
    expect_exact: "Bound pvc-da17b5c6-0d8c-42cf-9a25-bc444ac9a71d"
---

# otbr-thread-rcp-recovery: core-firmware flash of the Thread SLZB, then scale otbr back to 1

## 1. Summary and why held

**Operator decision 2026-11-16: "go to the firmware flash".** This plan is re-planned around it.

**State today (measured read-only 2026-11-16 ~00:00Z):**

- `home-automation/otbr` is at **replicas 0** since commit `371bac303` (2026-10-30): the CC2652P7
  RCP stopped answering Spinel around 2026-10-28 14:4xZ (otbr-agent died at
  `Init() at spinel_driver.cpp:87: Failure` on every attempt, 619 restarts) and a full radio reboot
  did not recover it. No pod exists; HelmRelease `otbr` is Ready; `pvc/otbr-data` is Bound, its
  Longhorn volume `pvc-da17b5c6-…` is `detached` (last backup 2026-10-29T23:03Z).
- The device `/ha_info`: `model SLZB-06P7`, `MAC 0C:DC:7E:36:F8:04`, `device_ip 192.168.33.238`,
  `sw_version v3.3.8.dev3`, `fw_channel dev`, `sel_fw_channel any`, `zb_hw CC2652P7`,
  `zb_type 2` (pysmlight `ZB_TYPES[2] = "thread"`), `zb_version 20260304`, `zb_channel 0`.
  `/ha_sensors`: `ethernet:true`, `auto_zigbee:false`, `socket_uptime 0`, `uptime 296617` s.
  `/metrics`: `smlight_socket_clients{} 0`.
- **All three SLZB units rebooted at about 2026-11-12 13:31Z** (Thread unit uptime 296617 s,
  coordinator 296669 s, tub-room router 296673 s; UniFi uptimes agree). That is a power/PoE event,
  not anything this plan did. **Nobody has tested Spinel since**, because otbr is at 0. Pre-check
  2.6 tests it before the flash (section 3.0).

**Ladder already worked (do not repeat):** radio-only restart (`cmd=1`), full device reboot
(`cmd=3`), plus the 2026-10-30 PANIC reboot from a guessed `action=6` (`zigbee2mqtt.md` 4d-bis) and
the 11-12 power event. The only untried rung is `zigbee2mqtt.md` §4f **rung 5: a core-firmware
change, then retry**. The precedent in §4f: the tub-room router failed the whole remote ladder on
v3.3.3.dev7 and came back with a plain reconnect after the core moved to v3.3.5.dev1.

**Target firmware, from the upstream OTA manifest** (fetched 2026-11-16,
`https://updates.smlight.tech/services/api/slzb-06x-ota.php?type=ESP`; pysmlight
`catalog.determine_firmware_type()` maps a non-U, non-Ultima model such as SLZB-06P7 to `ESP`, so
this is the list this unit is offered; no core build newer than 2026-10-28 exists):

| build | rev | channel | relevant notes (quoted) |
|---|---|---|---|
| v3.3.8.dev3 | — | dev | **installed; no longer on the list** |
| v3.3.8.dev7 | 20260911 | dev | "Minor socket server improvements." |
| v3.4.1.dev1 | 20260925 | dev | "Increased the keepalive setting for the socket server to 60 seconds." "Added more socket server debug info to device log." (watchdog/auto-restart items are under "Zigbee Hub mode" only) |
| **v3.4.3.dev1** | **20261006** | dev | "The OS will now apply adaptive timing and UART FIFO configurations based on the selected baud rate." "Socket Server refactoring — Fixed TCP_NODELAY not being applied … The logic for detecting connection losses has been modified to minimize false positives … A radio frame is now sent as a single TCP packet" |
| v3.4.5.dev0 | 20261028 | dev | newest; Zigbee Hub mode rework, EFR32 transport fixes, script fixes. Nothing for CC26xx or socket mode |
| v3.3.1 | 20260425 | release | **older than installed = a downgrade. NOT proposed** (its OTBR fixes are for "Thread+OTBR running on device" mode, not our RCP-over-TCP mode) |

**Chosen target: v3.4.3.dev1** (`slzb-os-v3.4.3.dev1-ota.bin`, HTTP 200, 2 880 144 bytes on
2026-11-16). Reason: it is the build that rewrote exactly the path that died (socket server and
the UART timing for the selected baud), it has 41 days of dev exposure, and it carries less
unrelated change than v3.4.5.dev0. **One allowed forward fallback: v3.4.5.dev0** (cumulative, 19
days, `slzb-os-v3.4.5.dev0-ota.bin`, HTTP 200, 2 887 728 bytes). Nothing older than installed.

**CC2652P7 compatibility.** A core flash replaces the ESP32 OS only; it does not touch the radio
firmware, its type or its NV (`zigbee-agent`: "An SLZB-OS (core) update reboots the device … it
does not touch the radio, network key, or pairings"). The radio stays on **20260304**, which is
already the newest Thread RCP SMLIGHT publishes for this chip (radio manifest
`?type=ZB&format=slzb&device=3&idx=0`, pysmlight `Devices["SLZB-06p7"] = 3`: `type 2`,
`prod: true`, `baud 460800`, rev 20260304; the only other type-2 builds are older). Its one stated
core requirement is "SLZB-OS v2.8.5.dev12 or higher", which both candidates meet. **No radio
reflash or mode change is in this plan** (`zigbee2mqtt.md` §4d: radio reflash and mode toggles
have wiped NV on SMLIGHT units).

**Why this is not unattended.** The flash is one-way and runs in the SLZB web UI: operator-only
per `zigbee-agent` ("You do not flash firmware yourself"). Impact if it all fails: none beyond
today (otbr stays at 0; matter-server has 0 commissioned devices; HA's preferred Thread dataset
has `source: iOS-app` and the Apple BRs carry the mesh).

**DEVICE IDENTITY — the hard boundary of this plan.** Act ONLY on IP `192.168.33.238` + device MAC
`0C:DC:7E:36:F8:04` + `zb_type 2` + `zb_hw CC2652P7`. Do **NOT** touch:

- the **SLZB-06P10 Zigbee coordinator** `192.168.32.20` (MAC `14:2B:2F:DB:AA:C0`, core v3.3.3.dev7,
  UniFi: **Guest Room USW SW-8 port 4** — the SAME switch as this unit). Restarting it drops the
  whole Zigbee mesh and restarts Z2M.
- the **SLZB-06 router** `192.168.32.21` ("Router Tub Room", Basement-SW-48 PoE port 18). It also
  fingerprints as SLZB-06P7, so model strings alone are ambiguous.
- the old WiFi SLZB-06P7 at `192.168.32.70`.

**UniFi naming trap:** UniFi lists this unit as **"SLZB-06 Router-basement"** with Ethernet MAC
**`0c:dc:7e:36:f8:07`** (the ESP32's Ethernet MAC is base+3; `/ha_info` reports the `…:F8:04`
base MAC). A MAC search for `…:f8:04` in UniFi finds nothing. Match UniFi on IP `192.168.33.238`
plus prefix `0c:dc:7e:36:f8`, never on the alias.

## 2. Pre-checks (all read-only)

2.1 Premises: `.venv/bin/python3 runbooks/plan-premises.py otbr-thread-rcp-recovery --require-premises`.
All eight must PASS.

2.2 Device identity. Every field must match before anything else:
```bash
curl -s -m 5 http://192.168.33.238/ha_info | python3 -c "
import sys,json; i=json.load(sys.stdin)['Info']
ok = (i['MAC']=='0C:DC:7E:36:F8:04' and i['model']=='SLZB-06P7' and i['zb_type']==2 and i['zb_hw']=='CC2652P7' and i['device_ip']=='192.168.33.238')
print('IDENTITY', 'OK' if ok else 'MISMATCH', i['MAC'], i['model'], i['zb_type'], i['sw_version'], i['zb_version'])"
```
PASS (measured 2026-11-16): `IDENTITY OK 0C:DC:7E:36:F8:04 SLZB-06P7 2 v3.3.8.dev3 20260304`.
`MISMATCH`, a connection error or a Python traceback means STOP. If `sw_version` already reads
something other than `v3.3.8.dev3`, the unit self-updated: record it and go to 3.3 (probe) first.

2.3 Upstream still offers the target (the manifest can change):
```bash
curl -s -m 15 'https://updates.smlight.tech/services/api/slzb-06x-ota.php?type=ESP' | python3 -c "
import sys,json; v=[f['ver'] for f in json.load(sys.stdin)['fw']]
print('TARGET', 'OK' if 'v3.4.3.dev1' in v else 'GONE', 'FALLBACK', 'OK' if 'v3.4.5.dev0' in v else 'GONE', 'NEWEST', v[0])"
```
PASS: `TARGET OK FALLBACK OK NEWEST v3.4.5.dev0`. A different `NEWEST` means a new build shipped:
read its notes before flashing; do not silently pick it.

2.4 **PoE port, looked up BEFORE the window (read-only)** — the physical fallback if the unit does
not come back after the flash:
```bash
mise exec -- unifictl local client list --limit 500 -o json | python3 -c "
import sys,json; d=json.load(sys.stdin); d=d.get('data',d) if isinstance(d,dict) else d
for c in d:
    if c.get('ip')=='192.168.33.238' or str(c.get('mac','')).lower().startswith('0c:dc:7e:36:f8'):
        print('PORT', c.get('mac'), c.get('ip'), c.get('last_uplink_name'), 'port', c.get('sw_port'), repr(c.get('name')))"
```
PASS (measured 2026-11-16): `PORT 0c:dc:7e:36:f8:07 192.168.33.238 Guest Room USW SW-8 port 7 'SLZB-06 Router-basement'`.
Port 7 is configured `PoE Out + Data`, `poe_mode auto`. Write the switch and port into the run log.
If the port is 4, or the switch is not SW-8, STOP and re-identify: port 4 is the coordinator.

2.5 Baselines for the collateral gate 4.6. Record:
```bash
curl -s -m 5 http://192.168.32.20/metrics | grep -e smlight_device_uptime -e smlight_socket_uptime
kubectl get pod -n home-automation -l app.kubernetes.io/name=zigbee2mqtt -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}'
```
Measured 2026-11-16: coordinator `smlight_device_uptime` about 2.97e8 ms, z2m restartCount `4`.

2.6 **Spinel probe on the CURRENT firmware** (pod is at 0, so the socket is free). Script in 3.3.
- `SPINEL SILENT bytes=0` = the 10-28 failure persists: proceed with the flash.
- `SPINEL ANSWERS <version>` = the 11-12 power event revived the radio. The operator's decision
  was taken on the 10-30 evidence. Ask the operator ONE question before flashing: "radio answers
  on v3.3.8.dev3 — flash anyway, or skip to 3.5 scale-up?" Do not decide it yourself.

2.7 Thread network baseline for CONTENTS gate 4.5. Do not write the value into any committed file:
```bash
HA=$(kubectl get pod -n home-automation -l app.kubernetes.io/name=home-assistant -o name | head -1)
kubectl exec -n home-automation $HA -c app -- python3 -c "
import json; d=json.load(open('/config/.storage/thread.datasets'))['data']
t=bytes.fromhex([x for x in d['datasets'] if x['id']==d['preferred_dataset']][0]['tlv']); i=0
while i<len(t):
    ty,l=t[i],t[i+1]
    if ty==2: print('HA_EXT_PANID', t[i+2:i+2+l].hex().upper())
    i+=2+l"
```
Expect exactly one `HA_EXT_PANID <16 hex>` line.

2.8 Nothing else in flight on the same pod, node, volume or namespace: none of the plans in
`conflicts_with` in this slot, and `kubectl get ds longhorn-manager -n storage -o jsonpath='{.spec.template.spec.containers[0].image}'`
still prints the pre-window Longhorn version (`longhornio/longhorn-manager:v1.12.1` today).

## 3. Steps

Roles: **[OPERATOR-ONLY]** = the operator at the SLZB web UI. **[zigbee-agent]** = read-only device
checks. **[cberg-agent]** = the git change. No agent issues any `/api2?action=` call in this plan:
`zigbee2mqtt.md` 4d-bis, a guessed `action=6` panic-rebooted this radio on 2026-10-30.

**3.1 [OPERATOR-ONLY] Device config backup, stored OUTSIDE the repo.**
Open `http://192.168.33.238`, confirm the header shows hostname `SLZB-06 Matter-over-Thread`, then
Settings → Backup/Restore → download the config backup. Save it to
`~/Documents/slzb-backups/slzb-06p7-thread-192.168.33.238-2026MMDD.<ext as saved>` (any path outside
`/Users/mu/code/cberg-home-nextgen`; it holds network config). Note in the run log the file name and
size. While in the UI, read and write into the run log the **radio mode** (Thread) and the
**radio baud rate** (the published RCP 20260304 is built for 460800). Do not change either.
PASS: a non-empty file exists at that path. No file = do not flash.

**3.2 [OPERATOR-ONLY] Flash the CORE to v3.4.3.dev1.**
SLZB web UI → Settings → Firmware update → **Core / SLZB-OS** (NOT the Zigbee/radio section) →
select **v3.4.3.dev1** and install. If the UI only offers the newest build, use its local-file
upload with `https://updates.smlight.tech/firmware/slzb06x/core/slzb-os-v3.4.3.dev1-ota.bin`
(download it first; the size must be 2 880 144 bytes). Do not touch "Zigbee Flash Mode", radio
firmware, or the channel selector. Do not power the unit off during the flash; it reboots itself.
Wait until `http://192.168.33.238` answers again (usually 1–2 min), then re-run 2.2.
PASS: `IDENTITY OK 0C:DC:7E:36:F8:04 SLZB-06P7 2 v3.4.3.dev1 20260304`. Gate 4.1 states the fails.

If the unit does not answer within 10 min: **[OPERATOR-ONLY]** PoE power-cycle **Guest Room USW SW-8
port 7** in the UniFi UI (Devices → SW-8 → Port 7 → Power Cycle). Re-read the port label against
2.4 first. NEVER port 4 (coordinator) and NEVER `unifictl local device restart` on the switch (that
drops the coordinator too). `unifictl` 5.7.0 has no per-port power-cycle command, so this is UI-only.

**3.3 [zigbee-agent] Spinel probe, pod still at 0.** A raw `PROP_VALUE_GET(PROP_NCP_VERSION)` over
TCP 6638. `zigbee2mqtt.md` 4d-bis classes a Spinel property get as read-only. The frame is
`7e 81 02 02 5e 80 7e` (HDLC-lite, FCS CRC-16/X.25; encoder and decoder dry-tested offline on
2026-11-16: FCS of `123456789` = `0x906e`, the standard check value, and a synthetic
`PROP_VALUE_IS` reply round-trips). Never send `RESET` or any write from this script.
```bash
python3 -I - 192.168.33.238 6638 <<'EOF'
import socket, sys, time
def fcs(b):
    c = 0xFFFF
    for x in b:
        c ^= x
        for _ in range(8):
            c = (c >> 1) ^ 0x8408 if c & 1 else c >> 1
    return c ^ 0xFFFF
def frame(p):
    c = fcs(p); raw = p + bytes([c & 0xFF, c >> 8]); out = bytearray([0x7E])
    for x in raw:
        out += bytes([0x7D, x ^ 0x20]) if x in (0x7E, 0x7D) else bytes([x])
    return bytes(out + b'\x7e')
def unframe(buf):
    res = []
    for chunk in buf.split(b'\x7e'):
        if not chunk: continue
        d = bytearray(); esc = False
        for x in chunk:
            if esc: d.append(x ^ 0x20); esc = False
            elif x == 0x7D: esc = True
            else: d.append(x)
        if len(d) > 2 and fcs(bytes(d[:-2])) == (d[-2] | d[-1] << 8): res.append(bytes(d[:-2]))
    return res
host, port = sys.argv[1], int(sys.argv[2])
s = socket.create_connection((host, port), timeout=5); s.sendall(frame(bytes([0x81, 0x02, 0x02])))
buf = b''; end = time.time() + 5
while time.time() < end:
    try:
        r = s.recv(512)
        if not r: break
        buf += r
        if any(f[1:3] == b'\x06\x02' for f in unframe(buf)): break
    except socket.timeout: break
s.close()
hits = [f for f in unframe(buf) if f[1:3] == b'\x06\x02']
print('SPINEL ANSWERS', hits[0][3:].split(b'\0')[0].decode(errors='replace')) if hits else print('SPINEL SILENT bytes=%d' % len(buf))
EOF
```
Run it twice, 30 s apart. PASS: both print `SPINEL ANSWERS <RCP version string>`. FAIL:
`SPINEL SILENT bytes=0` (the 10-28 signature: TCP accepts, radio silent), or `ConnectionRefusedError`
(socket server down). **Do not scale up on a FAIL.**

**3.4 Forward fallback, once: v3.4.5.dev0 [OPERATOR-ONLY flash].** Only if 3.3 FAILS on v3.4.3.dev1.
Same procedure as 3.2 with `slzb-os-v3.4.5.dev0-ota.bin` (2 887 728 bytes), then 2.2 must print
`v3.4.5.dev0 20260304`, then 3.3 again. If 3.3 still FAILS: **STOP.** Leave otbr at 0, write the
result into F-16d94a1b, and re-route to DECIDE (repair/RMA vs replace the unit vs retire OTBR).
Radio reflash is NOT the next rung here; that is an operator decision of its own (§4d NV risk).

**3.5 [cberg-agent] Scale otbr back to 1 — reviewed GitOps commit.** Only after 3.3 PASSES.
Do NOT `git revert 371bac303`: that commit also added `docs/sops/zigbee2mqtt.md` §4d-bis, which
must stay. Reverse-apply only its helmrelease hunk (dry-run with `--check` first; it passed on
2026-11-16 against HEAD `c64528c10`):
```bash
cd /Users/mu/code/cberg-home-nextgen
git show 371bac303 -- kubernetes/apps/home-automation/otbr/app/helmrelease.yaml | git apply -R --check
git show 371bac303 -- kubernetes/apps/home-automation/otbr/app/helmrelease.yaml | git apply -R
git diff -- kubernetes/apps/home-automation/otbr/app/helmrelease.yaml
```
The resulting diff (dry-tested on a scratch copy, 2026-11-16) removes the six `# 2026-10-30:
scaled to 0 …` comment lines and changes one line:
```
-        replicas: 0
+        replicas: 1
```
Commit and push it as its own change (shared worktree rules from CLAUDE.md). Write the message
file first, then commit in a separate shell call from any DSN sourcing:
```bash
cd /Users/mu/code/cberg-home-nextgen
git commit --only kubernetes/apps/home-automation/otbr/app/helmrelease.yaml -F /path/to/msg.txt
git log -1 --format=%s          # must be YOUR subject, else amend before push
git show --stat HEAD            # exactly one file: kubernetes/apps/home-automation/otbr/app/helmrelease.yaml
git push
```
Suggested subject: `fix(otbr): scale back to 1 after SLZB core v3.4.3.dev1 revived the Thread RCP`.
Flux picks it up by webhook; no manual reconcile. Record the commit SHA (`SCALEUP_SHA`) and the
time the pod starts (`T0`).

**3.6 [zigbee-agent / cberg-agent, read-only]** Run section 4 at T0 + 5 min and again at T0 + 30 min.

## 4. Verification (positive gates; every gate below has a measured or code-derived FAIL)

**4.1 CONTENTS ASSERTION — the device runs the target core and the SAME radio.** Re-run 2.2 after
3.2 (or 3.4). PASS: `IDENTITY OK 0C:DC:7E:36:F8:04 SLZB-06P7 2 v3.4.3.dev1 20260304`
(or `v3.4.5.dev0`). FAIL shapes: `v3.3.8.dev3` (the flash did not take), a `zb_type` other than
`2` or a `zb_version` other than `20260304` (the radio was touched: STOP, do not scale up, and
restore the 3.1 backup via Backup/Restore), `MISMATCH` (wrong device answered at that IP).

**4.2 Radio answers Spinel at replicas 0.** Section 3.3. PASS/FAIL as stated there. This is the
only gate before the git change and it decides 3.5.

**4.3 Pod up and STAYS up (positive, measured on the live object).**
CONTROL: metric kube_pod_container_status_restarts_total (raw counter read via kubectl here; cross-checked in 4.4).
```bash
kubectl get pod -n home-automation -l app.kubernetes.io/name=otbr -o jsonpath='{range .items[*]}{.metadata.name} ready={.status.containerStatuses[0].ready} restarts={.status.containerStatuses[0].restartCount} started={.status.containerStatuses[0].state.running.startedAt} node={.spec.nodeName}{"\n"}{end}'
```
At T0 + 5 min: exactly one line, `ready=true`, `restarts=0`, `node=k8s-nuc14-03`; record
`started=`. At T0 + 30 min: same pod name, `ready=true`, `restarts=` equal to the T0 + 5 value
(expected `0`), and `started=` unchanged (so the container has run at least 30 min).
Note: the container has NO readiness or liveness probe (verified live), so `ready=true` alone
only means "process running". The gate is the unchanged `restarts` and `started` pair. FAIL shape,
measured 10-28..10-30: otbr-agent exits about 13 s after each start, so `restarts` climbs within the
first minute (131 in 24 h, 619 total) and `started=` moves or is empty (`state.waiting`).

**4.4 Soak cross-check in Prometheus.**
CONTROL: metric kube_pod_container_status_restarts_total
`increase(kube_pod_container_status_restarts_total{namespace="home-automation",container="app",pod=~"otbr-.*"}[30m]) == 0`
read at T0 + 30 min. PASS: the query returns the otbr series with value 0. FAIL: a value above 0,
or NO series at all (the new pod is not scraped yet, which proves nothing: fall back to 4.3 and
re-read 10 min later).

**4.5 CONTENTS ASSERTION — the BR rejoined the SAME Thread network as an active node.**
otbr REST API (hostNetwork on k8s-nuc14-03, the endpoint HA uses):
```bash
curl -s -m 5 http://192.168.55.13:8081/node/state
curl -s -m 5 http://192.168.55.13:8081/node/ext-panid
```
PASS: state is `"router"`, `"leader"` or `"child"`, and ext-panid equals `HA_EXT_PANID` from 2.7
(case-insensitive). FAIL: connection refused (agent dead), `"disabled"` or `"detached"` for more
than 5 min, or a different ext-panid. A different ext-panid means the BR formed or joined another
network: scale back to 0 (5.2) and treat it as a dataset incident.

**4.6 Device side: the socket client stays connected.**
```bash
curl -s -m 5 http://192.168.33.238/metrics | grep -e smlight_socket_clients -e smlight_socket_uptime
```
PASS: `smlight_socket_clients{} 1`, and `smlight_socket_uptime` larger on a second read 60 s later.
FAIL: `smlight_socket_clients{} 0` / `smlight_socket_uptime{} 0` (measured today with no client,
and during the crashloop the device log showed `Client disconnected (connection lost)` about 13 s
after each `New client`).

**4.7 Collateral: the Zigbee side was untouched.** Re-run 2.5. PASS: the coordinator's
`smlight_device_uptime` and `smlight_socket_uptime` are LARGER than the 2.5 baseline (neither
reset) and the zigbee2mqtt restartCount still equals the 2.5 value (`4` today). A reset means the
wrong device or switch port was hit: escalate.

**4.8 Storage and HA.** `kubectl get volume -n storage pvc-da17b5c6-0d8c-42cf-9a25-bc444ac9a71d -o jsonpath='{.status.state} {.status.robustness}'`
PASS: `attached healthy`. FAIL: `attached degraded` or `faulted` (today `detached unknown`, the
expected pre-state). Then ha-agent, read-only: HA config entry `otbr` state `loaded`.

## 5. Rollback

5.1 **The core flash is one-way.** v3.3.8.dev3 is not on the OTA list, and v3.3.1 (the release
build) is a downgrade this plan does not authorise. The only firmware move left is forward
(3.4). If the flash resets device settings, restore the 3.1 backup via Settings → Backup/Restore
(operator-only), then re-run 2.2. The Thread dataset is NOT on the device: it lives in
`pvc/otbr-data` (`/data/thread`) and in HA's `thread.datasets`, and no step here writes either.

5.2 **Scale-up (3.5) — the git half, a clean revert.** If 4.3, 4.5 or 4.8 fails, revert within
10 min (each crash rewrites host netfilter on k8s-nuc14-03):
```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit $SCALEUP_SHA       # a single-file commit, so the revert is single-file too
git show --stat HEAD                    # exactly kubernetes/apps/home-automation/otbr/app/helmrelease.yaml
git log -1 --format=%s                  # must be the Revert subject, then push
git push
```
Confirm back at the pre-state: premises `otbr-scaled-to-zero-live` (`0`) and `otbr-no-pod` (`0`)
pass again, and HelmRelease `otbr` is Ready. The Longhorn volume detaches again; that is expected.

5.3 If 4.7 shows the coordinator or z2m was disturbed, this plan stops there: hand the Zigbee side
to zigbee-agent's coordinator playbook. Do not continue to 3.5.

## 6. Interference notes

- **Run this BEFORE `otbr-0.4.0`, never in the same slot.** That plan's premises
  (`otbr-available`, the live imageID) need a running pod, so it cannot pass until 3.5 has.
  **Repo correction:** `otbr-0.4.0` should gain `depends_on: [otbr-thread-rcp-recovery]` and a
  reciprocal `conflicts_with` entry. Also missing a reciprocal entry for this plan:
  `iobroker-v12.0.0-digest-005ba9c` and `talos-power-tuning-ab`. `--validate` does not check
  reciprocity.
- `talos-linux-1.14.5` (sun-attended:2026-11-22) and `talos-linux-1.14.6` reboot k8s-nuc14-03, the
  otbr node, and flush host netfilter. Not the same day: a node reboot would read as an RCP failure.
- `longhorn-1.13.0` already lists this plan: the scale-up attaches `otbr-data`, so never during a
  Longhorn engine move. `kube-prometheus-stack-93.3.0` already lists it too (gate 4.4).
- `iobroker-v12.0.0-digest-005ba9c` is stamped `now:2026-11-16`. Do not run this plan that evening.
- **Physical shared surface:** the fallback PoE cycle is on Guest Room USW SW-8, which also powers
  the Zigbee coordinator (port 4). Only port 7 is in scope.
- **Window fit:** human-gated and operator-attended (the flash is operator-only in a web UI). Not
  `nightly`. Fits the next attended slot that holds none of the conflicts, for example
  sat-attended:2026-11-21, or an operator-GO'd attended NOW evening. About 85 min, 100 with the
  3.4 fallback.
- The 2026-11-12 ~13:31Z power event rebooted all three SLZB units. Pre-check 2.6 exists because of
  it: the radio may already answer, and the flash decision was taken before anyone could know.
- Related, NOT answered here: F-59a2a2ce (no OTBR/Thread SOP). After this run, sections 3.3/4.x
  are the raw material for it. **Repo correction for the SOP:** `zigbee2mqtt.md` §4f describes the
  tub-room router only; it should say that rung 5 also applies to the Thread unit, and record the
  UniFi alias/MAC trap for `192.168.33.238` (alias "SLZB-06 Router-basement", Ethernet MAC `…:f8:07`).
