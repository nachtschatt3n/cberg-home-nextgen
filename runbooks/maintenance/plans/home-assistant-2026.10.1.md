---
plan_id: home-assistant-2026.10.1
component: home-assistant              # Deployment home-automation/home-assistant (app-template HelmRelease, image pinned TWICE: app + certifi-patch initContainer)
pr: 310                                # Renovate "update ghcr.io/home-assistant/home-assistant 2026.9.4 -> 2026.10.1", CI green, MERGEABLE (gh pr view 310, 2026-10-12)
kind: image
current: "2026.9.4"                    # MEASURED live 2026-10-12: deploy image + /config/.HA_VERSION both 2026.9.4
target: "2026.10.1"                    # skips 2026.10.0 (monthly release, backward-incompatible list read in full) and takes its first patch
update_type: minor                     # monthly HA release train; the minor IS the breaking axis
risk: high                             # not from a known break against OUR config (the release-note scan found none that bites, see 1.3) but from
                                       # surface: 215 integrations, 31 custom_components pip-reinstalled on boot, one forward-only .storage migration
                                       # layer, the whole smart home down for the restart, and a 2.6k-entity baseline that has to be re-proven
est_duration_min: 85                   # in-window: pre-checks 15 + merge/roll 10 + settle 10 (floor, HACS pip installs) + verification 30 + buffer 20. The restore_proof (about 20 min) runs the day BEFORE, outside the window.
needs_reboot: false                    # pod restart only, no node reboot
touches:
  namespaces: [home-automation, storage]   # storage: only the scratch restore-proof Volume (section 2.4), deleted again the same day
  resources:
    - "helmrelease/home-automation/home-assistant (image tag x2: containers.app + initContainers.certifi-patch), kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml"
    - "deployment/home-automation/home-assistant (strategy Recreate, verified live 2026-10-12) -> ONE pod replacement, hostNetwork on k8s-nuc14-01"
    - "pvc/home-automation/home-assistant-config (longhorn-static, RWO, 40Gi): /config/.storage, /config/.HA_VERSION and the recorder DB are rewritten by the new version"
    - "volume.longhorn.io/storage/home-assistant-config-restoretest (+ pv/pvc of the same name in home-automation, Job ha-restoretest): SCRATCH objects of the restore_proof, section 2.4"
    - "/config/custom_components/* pip requirements are reinstalled on first boot (needs outbound PyPI; boot time rises)"
  shared:
    - home-assistant-smarthome          # every HA automation/script is DOWN for the restart (Recreate, no overlap): lights, climate, solar helpers, presence
    - mqtt                              # HA is a client of home-automation/mosquitto; discovery entities are re-published on start
    - zigbee-matter-hubs                # zigbee2mqtt / matter-server / otbr stay up but their HA entities flap to unavailable during the restart
    - alexa-cloud-and-hmip-cloud        # alexa_media / alexa_devices and homematicip_cloud re-authenticate on start (cloud sessions)
    - monitoring                        # verification section 4 reads Prometheus (kube_pod_*) as a secondary instrument
depends_on: []                          # DELIBERATELY empty. The otel-operator prerequisite (F-07517014: clear the F-97c88a5c deadlock, HelmRelease
                                        # monitoring/otel-operator Ready=False, FIRST) is NOT a plan: its fix is an operator-GO state change owned by
                                        # cberg-agent, and otel-operator-0.23.0 is an unscheduled draft that is not that fix, so naming it here would
                                        # gate on the wrong object. The SOLE gate is premise otel-operator-helmrelease-ready (Ready=True); it prints
                                        # False today and this plan must not run until it prints True.
conflicts_with:
  - talos-linux-1.14.2                  # node reboots (HA is hostNetwork on nuc14-01; a drain mid-start strands the pod). Window 2026-11-01 today, but exclusive
  - longhorn-1.13.0                     # storage-engine minor on the volume HA's config + recorder DB live on; exclusive
  - k8s-1.36.5                          # control-plane roll (status superseded; listed so a revival cannot share the slot)
  - kube-prometheus-stack-92.2.0        # section 4 reads Prometheus; the shared instrument must not be rolling
  - app-template-5.3.0                  # re-renders home-automation/home-assistant (label-only consumer) -> a second Helm upgrade of the SAME release; Recreate means no pod roll but it muddies GEN_CHANGED attribution
  - app-template-5.2.1                  # superseded by 5.3.0, same files
  - flux-reconciler-impersonation       # rewires the helm-controller identity for this HelmRelease
  - helm-drift-detection                # adds spec.driftDetection to this HelmRelease
  - flux-oci-chart-sources              # rewrites the HelmRelease chart source block
  - flux-distribution-2.9.6             # a Flux controller roll mid-reconcile makes an HR result unattributable
  - flux-fleet-0.60.0
  - otel-operator-0.23.0                # never in the SAME slot (its failure mode would pollute the log/metric reads); NOT a depends_on, see above
  - edot-collector-0.162.0              # log shipper; section 4's error-log scan uses the HA API, but the collector roll drops pod logs in Elasticsearch
  - iobroker-12.0.0                     # home-automation sibling, scheduled nightly 2026-10-15; kept apart so a hub regression is attributable (it runs nightly 10-15, before this slot)
  - teslamate-4.3                       # home-automation sibling feeding HA entities (tesla integrations in section 1.4)
  - n8n-2.39.8                          # home-automation sibling with HA webhooks
  - n8n-chart-2.1.1
  - pgvector-fleet-0.8.7                # touches home-automation postgres consumers read through HA?  kept conservative: shared namespace restarts
  - nextcloud-fleet-35.0.1              # no resource overlap, but both are backup-restore class and human-verified; the scheduler flags RISK-CLASS STACKING + OVER-TIME when they share a slot (150 + 85 min > 180), hence the separate slot
exclusive: false
security_ref: F-b4372efb               # fixable-CVE finding on the 2026.9.4 image; detail stays in the DB (CLAUDE.md "Information Security"). 2026.10.1 is the newer upstream tag that finding waits for.
capability_change: true                # monthly release adds integrations/frontend features and removes the legacy auth mode; behaviour changes by design
rollback_class: backup-restore       # image revert alone is NOT sufficient once .storage / config-entry migrations ran (see section 5)
finding_refs: [F-07517014, F-636d64b5, F-b4372efb]   # F-07517014 plan finding (this plan answers it), F-636d64b5 version-monitor row, F-b4372efb the security row the bump closes
premises:
  # plan-premises.py allows only kubectl/flux/helm/git reads and simple pipelines (no gh, curl, && or ;), and parses
  # `kubectl -n X get` as subcommand X, so the namespace flag goes AFTER the verb. The upstream checks that need
  # curl/gh (PR state, image published, recorder schema) are therefore manual gates in section 2.1.
  - id: live-is-2026-9-4-and-strategy-recreate
    why: "The plan assumes the 2026.9.4 -> 2026.10.1 delta, and the single-replica RWO Longhorn Deployment must use Recreate (docs/sops/longhorn-rwo-multi-attach.md). Both read from the RENDERED Deployment, not the HelmRelease."
    run: >-
      kubectl get deploy home-assistant -n home-automation -o jsonpath='{.spec.template.spec.containers[0].image}{" "}{.spec.strategy.type}'
    expect_exact: "ghcr.io/home-assistant/home-assistant:2026.9.4 Recreate"
  - id: otel-operator-helmrelease-ready
    why: "depends_on gate. Reads Ready=True on monitoring/otel-operator. TODAY it prints False (deadlock F-97c88a5c), so this plan correctly stays deferred until the otel fix has run."
    run: >-
      kubectl get helmrelease otel-operator -n monitoring -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: git-still-pins-2026-9-4-twice
    why: "The change is PR #310 (+2/-2 on the two tag lines). If git no longer holds exactly two 2026.9.4 pins (already bumped by someone, or a third pin was added), the merge/sed step is wrong."
    run: >-
      grep -c 'tag: 2026.9.4' kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml
    expect_exact: "2"
  - id: home-assistant-config-volume-healthy
    why: "The rollback depends on the Longhorn volume and its 03:00 backup; a degraded volume weakens it."
    run: >-
      kubectl get volume home-assistant-config -n storage -o jsonpath='{.status.robustness}'
    expect_exact: "healthy"
status: draft
window: "sun-attended:2026-11-29"      # SCHEDULING DECISION FOR THE OPERATOR (section 1.1): the asked-for sun-attended:2026-10-18 shares the slot with nextcloud-fleet-35.0.1
                                      # (150 min, backup-restore) -> 235 min > 180 schedulable + RISK-CLASS STACKING. Every nearer weekend slot also fails: sat-attended
                                      # has 70 schedulable min (< this plan) and sun 10-25 (160 booked), 11-01 (talos, exclusive), 11-08 (nocodb, backup-restore),
                                      # 11-15 (longhorn, exclusive), 11-22 (flux-oci-chart-sources, conflicts_with) are taken. 11-29 is the first slot with nothing booked.
                                      # To land earlier, MOVE nextcloud-fleet-35.0.1 (or accept the warnings) and set this to sun-attended:2026-10-18.
sops_refs: [docs/sops/home-assistant-updates.md, docs/sops/application-update.md, docs/sops/longhorn-rwo-multi-attach.md, docs/sops/backup.md, docs/sops/verification-contents-not-shape.md]
backup_gate: "Two independent backups, both required before the merge. (1) A FRESH HA built-in backup tar (encrypted, protected: true) created by the
  operator through the HA UI or the backup.create action, with the encryption key at hand. PASS = in-pod `find /config/backups -name '*.tar' -mmin -60 -size +1000000k | wc -l`
  is >= 1 (section 2.2.1; the same find with -mmin -1 prints 0, so the gate can fail). (2) The 03:00 Longhorn backup of volume home-assistant-config, PASS =
  `runbooks/longhorn-backup-age.py home-assistant-config --max-hours 26` prints FRESH (the same call with --max-hours 1 prints STALE, measured 2026-10-12). Longhorn
  is crash-consistent for the live sqlite WAL only, which is why (1) is the primary restore."
restore_proof: "Section 2.4, run the day BEFORE the window (it only reads the backup): restore the newest Completed Backup CR of home-assistant-config into a SCRATCH
  Longhorn volume home-assistant-config-restoretest (spec.fromBackup = that CR .status.url), mount it read-only in a one-off Job in home-automation, copy
  home-assistant_v2.db + -wal + -shm into an emptyDir, open THAT copy normally (WAL replayed) and require PRAGMA integrity_check == ok AND states_meta rowcount > 1000
  (live: 2606) AND core.config_entries parses. A backup that exists is not a backup that restores. Modelled on jellyfin-config-rwo-migration section 3.4;
  runbooks/backup-restore-proof.py is Postgres-only (scratch postgres pod) and cannot prove an HA sqlite restore."
---

# Home Assistant 2026.9.4 -> 2026.10.1 (PR #310)

## 1) Summary & why held

### 1.1 Why held

Home Assistant is a monthly release train (2026.10.0 is the new month; 2026.10.1 is its first patch). Sweep finding
F-07517014 caught that PR #310 would auto-merge in the 2026-10-13 03:30 nightly once the 48h cooldown cleared, with
two worries: (a) the otel-operator HelmRelease is deadlocked (F-97c88a5c), so a Flux batch auto-revert would not have
a healthy reference point, and (b) nobody had read the 2026.10.0 backward-incompatible list against the real
install. Operator decision 2026-10-12: hold HA out of the unattended lanes (deny rule is committed separately, do not
edit `runbooks/auto-update-policy.yaml` from this plan), run the bump in an attended Sunday window, human-gated, after
the otel fix.

Slot (scheduling decision, flagged for the operator): the requested 2026-10-18 cannot hold this plan cleanly.
`nextcloud-fleet-35.0.1` (150 min, `backup-restore`) is already booked there, so the scheduler warns OVER-TIME (150 + 85
> 180 schedulable minutes) and RISK-CLASS STACKING (two irreversible plans in one slot), and the two are human-verified
at the same time. The Saturday slots cannot take it either (70 schedulable minutes; 90 minus the 20-minute Step 0
reserve). The next free Sunday slots all fail on something else (10-25 has 160 of 180 booked, 11-01 is the exclusive
Talos roll, 11-08 carries `nocodb-2026.09.1` which is also `backup-restore`, 11-15 is the exclusive Longhorn roll,
11-22 carries `flux-oci-chart-sources`, which this plan lists in `conflicts_with`), so the plan is parked on the first
slot with nothing booked, `sun-attended:2026-11-29`. If the operator wants it sooner, move `nextcloud-fleet-35.0.1`
rather than stacking. The otel gate is the premise `otel-operator-helmrelease-ready`, not a `depends_on` (the
`otel-operator-0.23.0` draft is not the F-97c88a5c fix; that fix is an operator-GO state change owned by cberg-agent).

### 1.2 DB migration verdict: NO recorder schema migration

Recorder `SCHEMA_VERSION` is 53 at `2026.9.4`, `2026.10.0` and `2026.10.1` (measured from
`homeassistant/components/recorder/db_schema.py` at each tag, 2026-10-12; gate 2.1 re-runs it).
The ~3 GB `home-assistant_v2.db` is therefore NOT rewritten and a revert does not leave it on a newer schema.

That does NOT make the upgrade freely reversible. What IS forward-only:

- `/config/.storage/*` and config-entry data: each integration may run `async_migrate_entry` on first start and bump
  the entry `version`; an older HA then refuses or mis-reads that entry (HA logs "Migration handler not found" /
  "config entry version too new" and sets the entry to `migration_error`).
- `/config/.HA_VERSION` is rewritten to 2026.10.1; an older image start logs a downgrade warning and some storage
  collections are not downgraded.
- HACS / custom_components pip requirements are reinstalled on every boot (SOP checklist); a revert reinstalls the
  old pins, which is fine, but an integration that cached a newer API token/format may need a re-auth.
- Entity/device registry cleanups the new version applies (orphan removal) are not undone by a revert.

So: image revert is sufficient ONLY while the new pod has produced no migration log lines and no registry loss
(checked in 4.6). Otherwise rollback is a restore (section 5).

### 1.3 Release-note scan against OUR install (2026.10.0 backward-incompatible list + 2026.10.1 patch notes)

Read in full from the release blog. Breaking changes that do NOT apply (absent integration or unused shape,
confirmed against `hactl get integrations`, `configuration.yaml` and the automation/script YAML):

- Legacy mode of the Home Assistant auth provider removed (usernames always normalized): no `legacy_*` provider in
  `configuration.yaml`; verify no repair is open (4.5).
- easyEnergy, EnergyZero, EnergyFlip, Google Sheets, Mealie (server >= 3.2), Libre Hardware Monitor, IoTaWatt,
  Linode, Tank Utility, OpenEVSE, Synology DSM, Teslemetry, Proxmox, Rejseplanen, Sofar, UpCloud, Xbox: none is
  configured (Xbox is not_loaded/ignored). The 8 removed/disabled integrations are not in use.
- MQTT `mqtt.publish` / `mqtt.dump` now admin-only: 3 uses in our automations, all run as system context, not a user.
- Telegram bot `download_file` allowlist: no use found.
- Automation condition `state` + `for` shape change: our 3 uses are the safe single-entity form.

Changes that DO touch us are the table in 1.4 (the rows are groups, not a count of integrations; the 31 custom
components are one aggregate row plus the named ones).

### 1.4 Per-integration risk table (built from the live `hactl get integrations` (215) and `get hacs` (31 custom))

Risk: H = could lose function and needs the fix path, M = behaviour change to look at, L = patch-level / cosmetic.
The "verify" column is what section 4.4 runs; the "fix" column is a fallback, not a plan step.

| Integration | What changes at 2026.10 | Risk | Verify after upgrade | Fix if broken |
|---|---|---|---|---|
| custom_components fleet (31: alexa_devices, alexa_media, awtrix, bambu_lab, bermuda, bps, custom_conversation, dirigera_platform, dwd_precipitation_forecast, dwd_weather, dynamic_energy_cost, dyson_local, flichub, frigate, gruenbeck_cloud, ha_hatch, ha_washdata, hacs, haghs, homeconnect_ws, icloud3, nodered, openai_tts, resmed_myair, samsung_familyhub_fridge, solarfocus, tesla_custom, teslafi, tibber_prices, traeger, trmnl, wyzeapi) | New core breaking APIs surface as `DeviceEntry.config_entries` / deprecated-helper warnings; a custom component importing a removed helper fails to set up | H (aggregate) | 4.4: every config entry state is `loaded`; 4.3: the pod log (not `hactl get error-log`) has no `Error setting up` / `Setup failed for` for these domains | Per component: wait for the HACS release, or temporarily disable the entry; do not edit the component in the pod |
| alexa_devices (custom override `0.0.3-pr171136-on-2026.6.0`) | The override shadows the core integration. PR 171136 (To-do list platform) MERGED upstream into 2026.7.0 (mergedAt 2026-06-22), so core already carries it and the override is stale. Core 2026.10.1 pins the same aioamazondevices family | M | The two Alexa todo entities exist, the `_2` list round-trips (add item, read back by summary, remove by stored uid; SOP item) | DECISION POINT D1 (section 1.5) |
| alexa_media | Cloud session re-login on start; unrelated to the core change but shares the Alexa account with alexa_devices | M | Media players for Echo devices not `unavailable`; one `notify`/TTS announce reaches a device | Re-auth via the integration's repair flow (needs the operator's Amazon 2FA) |
| homematicip_cloud | Cloud session (entry `01JRZY6QRWHRW34RP7ZPASGKTS`) re-established on boot | M | `automation.hmip_cloud_session_self_heal` last_triggered unchanged or benign; `input_boolean.hmip_sustained_outage` is off; HmIP entities not unavailable | Self-heal automation first; then reload the entry |
| dirigera_platform | Custom; depends on pinned `dirigera` pip requirement reinstalled on boot | H | Entry loaded; IKEA lights/blinds respond (one toggle) | Wait for HACS release; revert path section 5 |
| dwd_weather / dwd_precipitation_forecast / core dwd_weather_warnings | Core warnings integration moves to `dwdwfsapi` 1.1.0 | M | Warning sensor state not unknown/unavailable; weather entity has a forecast | Reload the entry; if the library import fails, remove then re-add the core entry |
| custom_conversation / openai_tts / core ollama, openai_conversation, google_generative_ai_conversation | Conversation/agent APIs changed in the Assist stack (AI task entities: 3 `ai_task`, 6 `conversation`) | M | `conversation` entities exist (6) and `ai_task` (3); one Assist test sentence returns a non-error response | Reload entry; fall back to the default agent |
| wyzeapi | Cloud API client reinstalled on boot, historically fragile to HA helper removals | M | Wyze entities loaded; camera/plug state not unavailable | HACS update or re-auth |
| icloud3 / core icloud | Core icloud moves to pyicloud 2.7.0 and gains calendar/Reminders; icloud3 coexists | M | `device_tracker` home/not_home count back to baseline (19 home / 3 not_home at snapshot); no `icloud` auth repair | Core icloud 2FA re-auth if prompted (operator action) |
| tesla_custom / teslafi (+ teslamate feed) | Custom; HA entity platform deprecations | M | Tesla sensors report a fresh `last_changed` (<15 min for a polled sensor) | HACS update; reload entry |
| frigate (custom) | Stream TLS handling changed in 2026.10 camera/stream layer | M | Frigate camera entities (15 `camera` in baseline) load; one snapshot via `camera.snapshot` or the frontend renders | Re-add RTSP config option; check frigate logs; revert path |
| bermuda / dyson_local / tibber_prices / gruenbeck_cloud / homeconnect_ws | Custom BLE/cloud; same aggregate import risk as row 1 | M | Entry loaded + one entity of each not unavailable | HACS update |
| hue | 2026.10.1 patch: crash fix for a bridge event path | L | Hue lights (inside the 65 `light` entities) respond | none needed (it is the fix) |
| matter (python-matter-server 8.1.0 external) | 2026.10.1: TemperatureOffset range and `get_lock_users` fixes | L | Matter nodes (2 `lock` in baseline) available | Reload entry; matter-server pod is NOT touched |
| shelly (56 entries) | Uncalibrated covers behave differently (position vs open/close) | M | The `cover` entities (14) show `open`/`closed`, not `unknown`; cover automations still fire | Calibrate the cover on the device, or the Shelly integration option |
| unifi | Reconfigure flow behaviour changed | L | UniFi device trackers present; no repair | Reconfigure only if a repair appears |
| mcp_server | New setups admin-only | L | Existing entry loaded | none |
| template (15), utility_meter (4), music_assistant, esphome, ipp, mqtt, telegram_bot | Patch-level fixes, or the changed shape is not used by us (1.3) | L | Config check clean; entities present | none |

There is deliberately no "N integrations at risk" figure (an earlier draft said 14 without defining it). The table has
18 rows: one aggregate row for the 31 custom components, then the custom/cloud integrations that carry the risk
(dirigera_platform, the alexa pair, homematicip_cloud, wyzeapi, icloud3, tesla_custom/teslafi, frigate, dwd_*,
custom_conversation, the BLE/cloud group) and a tail of core watch items. Core integrations with a hard break against
our config: none found.

### 1.5 Operator DECISION POINTS (not steps; the window agent must not decide these)

- D1 (stale `alexa_devices` override, needs operator approval): `custom_components/alexa_devices` is the patch
  `0.0.3-pr171136-on-2026.6.0`. Its PR merged into core in 2026.7.0, so the override only shadows a core integration
  that already does the same job. Options: (a) leave it for this window (lowest risk to the upgrade, remove later),
  (b) remove it so core takes over (cleaner, but entity/unique-id continuity of the two todo entities has to be
  confirmed after the restart, and `custom_components` is on the PVC with no GitOps path, so removal is an in-pod
  action under the CLAUDE.md exception with a `.backup.YYYYMMDD_HHMMSS` copy). Default for this plan: (a).
- D2 (rollback bar): if post-upgrade verification fails on a SINGLE custom integration only, accept the loss until the
  next HACS release (disable the entry) rather than rolling the whole house back. Default: yes, with operator GO at
  the moment, because a full restore (section 5) loses up to the data since the pre-change backup.
- D3 (uptime caveat): HA restarts cap its known memory leak; the "uptime > 4 d" alert is not a new problem after this
  roll and will start counting from zero.

## 2) Pre-checks

All read-only. Run from the repo root. `hactl` is at `/Users/mu/code/hactl` (`mise exec -- hactl ...`).

### 2.1 Gates

```bash
# Upstream gates that plan-premises.py cannot run (curl/gh). Each prints a value that can FAIL.
gh pr view 310 --json state,mergeable --jq '.state + " " + .mergeable'
# PASS: OPEN MERGEABLE. FAIL looks like: CLOSED / CONFLICTING -> use the fallback sed in step 2.
T=$(curl -s "https://ghcr.io/token?scope=repository:home-assistant/home-assistant:pull" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $T" -H 'Accept: application/vnd.oci.image.index.v1+json' https://ghcr.io/v2/home-assistant/home-assistant/manifests/2026.10.1
# PASS: 200 (measured 2026-10-12). FAIL looks like: 404 (a nonexistent tag, 2099.1.1, returns 404 with the same call) -> ImagePullBackOff after Recreate.
for t in 2026.9.4 2026.10.1; do curl -fsS https://raw.githubusercontent.com/home-assistant/core/$t/homeassistant/components/recorder/db_schema.py | grep -m1 '^SCHEMA_VERSION'; done
# PASS: two identical lines (SCHEMA_VERSION = 53 at both tags on 2026-10-12) = no recorder migration (section 1.2).
# FAIL looks like: different numbers -> the 'no DB migration' verdict is void; re-plan section 5 around a database restore.
```

```bash
# plan premises (four; otel-operator-helmrelease-ready is expected to FAIL until the otel fix has run, and it is the SOLE otel gate)
.venv/bin/python3 runbooks/plan-premises.py home-assistant-2026.10.1

# No sibling plan from conflicts_with is in flight this slot (exact slot id from the frontmatter)
.venv/bin/python3 runbooks/maintenance-plan.py --open | grep -E 'sun-attended:2026-11-29'
# PASS: only this plan. FAIL looks like: a talos/longhorn/kube-prometheus-stack/app-template/flux/nextcloud row.
```

### 2.2 Backup (two independent mechanisms; both required = the `backup_gate`)

Facts the operator must have in hand: HA is `hostNetwork` on k8s-nuc14-01, strategy Recreate, with a single-replica RWO
Longhorn PVC, so a data restore needs the HA backup or the Longhorn backup; git alone restores only the image.

1. HA built-in backup. HA creates automatic backups daily ~05:00 into `/config/backups` (3 retained, ~1.2-1.5 GB each,
   `protected: true` = ENCRYPTED, so the encryption key must be at hand to restore one; confirm the operator has it
   BEFORE the window). Take a FRESH one immediately before the merge so it is version-matched. Because the operator is
   remote, prefer the `backup.create` action (HA UI -> Developer tools -> Actions -> `backup.create`; the `backup`
   domain is present in the live service list, hactl 2026-10-12) over the Settings -> System -> Backups click-path.
   `hactl` has no verb that calls an action (checked: `hactl --help` lists battery/delete/doctor/generate/get/k8s/
   label/memory/pull/update only), so this one step is operator-driven. Wait until the action finishes (the tar is
   written last), then:

```bash
N=$(kubectl exec deploy/home-assistant -c app -n home-automation -- sh -c "find /config/backups -name '*.tar' -mmin -60 -size +1000000k | wc -l" | tr -d ' ')
echo "fresh_backups=$N"; test "$N" -ge 1 && echo PASS || echo "FAIL: no tar newer than 60 min and larger than ~1 GB"
# PASS: fresh_backups >= 1. FAIL looks like: fresh_backups=0 (the newest tar is the 05:00 automatic one, older than 60 min, or the
# database was not included, so it is under 1,000,000 KB). Control measured 2026-10-12: the same find with -mmin -1500 printed 1
# (the 04:59 automatic tar, ~1.23 GB) and with -mmin -1 printed 0, so both outcomes are reachable.
# (BusyBox: `ls --time-style` is rejected in this container, and `| tail` would hide the exit status; `find -mmin -size` works.)
```

2. Longhorn backup of `storage/home-assistant-config` (RecurringJob `daily-backup-all-volumes`, 03:00, retain 7;
   crash-consistent only for the live sqlite WAL, which is why the HA backup above is the primary restore).

```bash
.venv/bin/python3 runbooks/longhorn-backup-age.py home-assistant-config --max-hours 26
# PASS: prints "home-assistant-config <age>h FRESH ..." (measured 2026-10-12: "6.7h FRESH via backup-cr backup=backup-6c567f9380154db0").
# FAIL looks like: "... STALE ..." and exit 1 (the same call with --max-hours 1 printed STALE on 2026-10-12) -> ask
# cberg-agent to run: kubectl create job --from=cronjob/daily-backup-all-volumes manual-backup-$(date +%Y%m%d-%H%M) -n storage
# (all volumes; heavy, only if stale) and re-check the newest Completed Backup CR (docs/sops/backup.md "lastBackupAt Can Lag").
```

3. Copy `.storage` out of the pod BEFORE the roll so a registry/config-entry rewrite can be diffed (kept local,
   NEVER committed; it holds tokens):

```bash
S=/private/tmp/ha-pre-2026.10.1; mkdir -p $S
kubectl exec deploy/home-assistant -c app -n home-automation -- tar czf - -C /config .storage .HA_VERSION > $S/storage-pre.tgz
tar tzf $S/storage-pre.tgz | wc -l ; tar xzOf $S/storage-pre.tgz .HA_VERSION
# PASS: file count > 50 (91 entries seen on 2026-10-12) and the version prints 2026.9.4.
# FAIL looks like: 0 entries / empty tgz (exec stdout truncated) or a version other than 2026.9.4.
```

### 2.3 Baseline (record the numbers; section 4 compares against them)

```bash
cd /Users/mu/code/hactl
mise exec -- hactl get states --format json > $S/states-pre.json
mise exec -- hactl get error-log --format json > $S/errorlog-pre.json     # NOT the HA log: {unavailable_entities (FULL list), recent_errors}
mise exec -- hactl get integrations --format json > $S/integrations-pre.json
mise exec -- hactl doctor --format json > $S/doctor-pre.json
kubectl logs deploy/home-assistant -c app -n home-automation --since-time="$(kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].status.startTime}')" > $S/halog-pre.log
python3 - <<PY
import json
S='$S'
st=json.load(open(S+'/states-pre.json')); el=json.load(open(S+'/errorlog-pre.json')); ig=json.load(open(S+'/integrations-pre.json'))
assert isinstance(st,dict) and st['total_entities']>=2000, "CONTROL FAILED: states payload empty/wrong shape"
assert len(el['unavailable_entities'])==st['unavailable_count']>0, "CONTROL FAILED: the FULL unavailable list must match unavailable_count (states.unavailable_entities is capped at 50)"
assert ig['summary']['total']==len(ig['integrations'])>=200, "CONTROL FAILED: integrations payload empty"
print('total',st['total_entities'],'unavailable',st['unavailable_count'],'integrations',ig['summary']['total'],ig['summary']['by_state'])
PY
wc -l < $S/halog-pre.log      # CONTROL: must be >= 1000 or 4.3's pre/post signature diff compares nothing
```

Reference baseline measured 2026-10-12 (re-measure at the window, then use the NEW numbers): total_entities 2596,
unavailable_count 249, unknown 290, automations 69, scripts 1, integrations 215 (by_state loaded 203 / not_loaded 12), 31
custom, pod log 17,430 lines with 0 setup-failure hits and 466 chronic ERROR lines (resmed_myair, dirigera_platform,
frigate API, websocket). The unavailable set is mostly Z2M/BLE sleepers and intentionally-offline devices, so the gate
is a SET difference (4.2), not zero. Shapes (verified against `/Users/mu/code/hactl/hactl/handlers/`): `get states` is a
DICT whose `unavailable_entities` is CAPPED at 50, which reads a false zero or false pass if used as the set, hence the
FULL list comes from `get error-log --format json`; `get integrations` is `{integrations:[...], summary:{total,
by_state, domains}}`. Parsing either as a bare list is the failure these CONTROLS catch.

### 2.4 restore_proof — prove the Longhorn backup restores (run the day BEFORE the window; reads the backup only)

`runbooks/backup-restore-proof.py` is Postgres-only (it starts a scratch postgres pod) and is NOT usable for this
sqlite/`.storage` volume (repo correction, noted so nobody wires it in). The pattern is the one in
`runbooks/maintenance/plans/jellyfin-config-rwo-migration.md` section 3.4, adapted to HA. Scratch objects only; never
touch anything named `home-assistant-config`.

```bash
GATE_BACKUP=$(kubectl get backups.longhorn.io -n storage -l backup-volume=home-assistant-config --sort-by=.metadata.creationTimestamp -o jsonpath='{range .items[?(@.status.state=="Completed")]}{.metadata.name}{"\n"}{end}' | tail -1)
URL=$(kubectl get backups.longhorn.io -n storage "$GATE_BACKUP" -o jsonpath='{.status.url}')
test -n "$GATE_BACKUP" -a -n "$URL" || echo "STOP: no Completed backup or no .status.url"
URL="$URL" python3 -c 'import os,sys;sys.stdout.write(sys.stdin.read().replace("__BACKUP_URL__",os.environ["URL"]))' < $S/restoretest.yaml.tmpl > $S/restoretest.yaml     # the URL carries the backup target host and "&volume=": substituted at run time, never committed; sed would expand "&" and the Longhorn webhook rejects the result
kubectl apply --dry-run=server -f $S/restoretest.yaml >/dev/null && echo DRYRUN_OK     # must print DRYRUN_OK before the real apply
kubectl apply -f $S/restoretest.yaml
kubectl get volumes.longhorn.io -n storage home-assistant-config-restoretest -o jsonpath='{.status.restoreRequired} {.status.state} {.status.robustness}{"\n"}'
#   poll every 60 s until "false detached ..." (restore finished, volume released); the live volume is ~7.2 GB used
kubectl apply -f $S/ha-restoretest-job.yaml
kubectl wait -n home-automation job/ha-restoretest --for=condition=complete --timeout=30m
kubectl logs -n home-automation job/ha-restoretest
```

`$S/restoretest.yaml.tmpl` (write it first; one Longhorn `Volume` CR must be applied by hand per `docs/sops/longhorn.md`):

```yaml
---
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: home-assistant-config-restoretest
  namespace: storage
spec:
  size: "42949672960"       # 40Gi, same as the live volume (measured)
  numberOfReplicas: 1
  staleReplicaTimeout: 30
  dataEngine: v1
  accessMode: rwo
  frontend: blockdev
  migratable: false
  encrypted: false
  fromBackup: "__BACKUP_URL__"
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: home-assistant-config-restoretest
spec:
  capacity:
    storage: 40Gi
  volumeMode: Filesystem
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: longhorn-static
  csi:
    driver: driver.longhorn.io
    fsType: ext4
    volumeAttributes:
      numberOfReplicas: "1"
      staleReplicaTimeout: "30"
    volumeHandle: home-assistant-config-restoretest
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: home-assistant-config-restoretest
  namespace: home-automation
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 40Gi
  storageClassName: longhorn-static
  volumeName: home-assistant-config-restoretest
```

`$S/ha-restoretest-job.yaml` (the db is ~3 GB; the emptyDir copy is what gets opened, so the restored volume stays read-only):

```yaml
---
apiVersion: batch/v1
kind: Job
metadata:
  name: ha-restoretest
  namespace: home-automation
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 1800
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      restartPolicy: Never
      securityContext: {runAsUser: 0, runAsGroup: 0}
      containers:
        - name: check
          image: python:3.14.7-slim
          command:
            - python3
            - -c
            - |
              import shutil, sqlite3, os, sys, json
              for suf in ("", "-wal", "-shm"):
                  src = "/r/home-assistant_v2.db" + suf
                  if os.path.exists(src):
                      shutil.copy2(src, "/work/home-assistant_v2.db" + suf)
              c = sqlite3.connect("/work/home-assistant_v2.db")      # normal open: WAL is replayed
              ic = c.execute("PRAGMA integrity_check").fetchone()[0]
              n = c.execute("select count(*) from states_meta").fetchone()[0]
              ce = json.load(open("/r/.storage/core.config_entries"))["data"]["entries"]
              print("integrity", ic); print("states_meta", n); print("config_entries", len(ce))
              sys.exit(0 if ic == "ok" and n > 1000 and len(ce) > 150 else 1)
          volumeMounts:
            - {name: restored, mountPath: /r, readOnly: true}
            - {name: work, mountPath: /work}
          resources:
            requests: {cpu: 100m, memory: 256Mi}
            limits: {memory: 1Gi}
      volumes:
        - name: restored
          persistentVolumeClaim: {claimName: home-assistant-config-restoretest, readOnly: true}
        - name: work
          emptyDir: {sizeLimit: 8Gi}
```

PASS = Job Complete, log shows `integrity ok`, `states_meta` > 1000 (live 2606 on 2026-10-12) and `config_entries` > 150
(live 215). FAIL = `integrity` anything but `ok`, `states_meta 0` (an empty restore), or the Job fails: the exit code
is 1 in each case, so `kubectl wait --for=condition=complete` times out instead of passing. On FAIL do not proceed to
the window; open a finding. Cleanup, one delete per exact scratch name: `kubectl delete job/ha-restoretest -n home-automation`,
`kubectl delete pvc/home-assistant-config-restoretest -n home-automation`, `kubectl delete pv/home-assistant-config-restoretest`,
`kubectl delete volumes.longhorn.io/home-assistant-config-restoretest -n storage`.

## 3) Steps

GitOps only. No `flux reconcile` unless the Flux webhook does not fire (SOP).

1. Confirm 2.1-2.3 are green, the 2.4 restore proof PASSED the day before, and the operator has taken the fresh HA
   backup (2.2.1) and has its encryption key. Operator GO recorded.
2. Merge PR #310 (it changes only the two `tag:` lines in
   `kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml`, +2/-2).

```bash
gh pr merge 310 --squash   # then: git pull --ff-only
git show --stat HEAD | tail -3
# PASS: exactly one file changed, 2 insertions/2 deletions. FAIL looks like: more files (a foreign hunk) -> stop.
```

   Fallback if the PR went stale (macOS BSD sed, dry-tested on a scratch copy of the file 2026-10-12; it changes lines 49 and 74 only):

```bash
sed -i '' 's/^\([[:space:]]*tag: \)2026\.9\.4$/\12026.10.1/' kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml
git diff -U0 | grep '^[-+] '
# dry-test result: 49c49 "tag: 2026.9.4" -> "tag: 2026.10.1" and 74c74 "tag: 2026.9.4" -> "tag: 2026.10.1" (two lines each side)
# commit with: git commit --only kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml -m '...'; then
# git log -1 --format=%s  (confirm the subject is YOURS before pushing)
```

3. Wait for the roll. Recreate: the old pod is deleted first, so HA is DOWN until the new pod passes readiness
   (HACS requirement installs make the first boot slow, expect several minutes).

```bash
kubectl rollout status deploy/home-assistant -n home-automation --timeout=15m
kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].spec.containers[0].image}{" "}{.items[0].status.startTime}{"\n"}'
# PASS: image ...:2026.10.1 AND startTime newer than the merge time. FAIL looks like: image 2026.9.4 (rollout status
# green-lights the OLD generation, feedback_rollout_status_old_generation) or ImagePullBackOff.
```

4. Reload vs restart: this change is a full restart by construction (new image). Do NOT additionally restart HA
   afterwards; use `reload` for any single integration that needs a nudge (CLAUDE.md in-pod exception rule 4).
5. Do NOT take any other action inside the pod (no custom_components edit, no D1 removal) until section 4 is
   complete. D1 is a separate, operator-approved follow-up.

## 4) Verification

Settle floor: wait at least 5 minutes after the pod is Ready (the `certifi-patch` initContainer and the HACS pip
reinstall run on boot, cloud integrations re-auth, BLE re-scan), and keep to 10 minutes before reading baselines. A
snapshot taken earlier reads half-started integrations as `unavailable` and the 4.2 gate fails for the wrong reason.

```bash
S=/private/tmp/ha-pre-2026.10.1
POD_START=$(kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].status.startTime}'); echo "$POD_START"
```

### 4.1 Process and version

```bash
kubectl exec deploy/home-assistant -c app -n home-automation -- cat /config/.HA_VERSION ; echo
kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}{"\n"}'
# PASS: 2026.10.1 and restartCount 0. FAIL looks like: 2026.9.4 (old generation) or restartCount > 0 (crash loop).
```

CONTENTS ASSERTION: `.HA_VERSION` equals the target AND `hactl doctor` reports API connectivity OK (a pod that is Ready
but whose API 503s fails here).

### 4.2 Entity gate: newly-unavailable SET difference, grouped by integration

Snapshot (the same three payloads as the baseline in 2.3, plus `.storage` for the entity registry):

```bash
cd /Users/mu/code/hactl
mise exec -- hactl get states --format json > $S/states-post.json
mise exec -- hactl get error-log --format json > $S/errorlog-post.json
mise exec -- hactl get integrations --format json > $S/integrations-post.json
kubectl exec deploy/home-assistant -c app -n home-automation -- tar czf - -C /config .storage > $S/storage-post.tgz
cat > $S/gate42.py <<'PY'
import json, sys, tarfile, collections
D=sys.argv[1]
pre=json.load(open(D+'/states-pre.json')); post=json.load(open(D+'/states-post.json'))
pe=json.load(open(D+'/errorlog-pre.json'))['unavailable_entities']; qe=json.load(open(D+'/errorlog-post.json'))['unavailable_entities']
# CONTROLS: each fails loudly on an empty / wrong-shape payload instead of reading as "no regression"
assert isinstance(post,dict) and post['total_entities']>=2000, "CONTROL FAILED: post states payload empty/wrong shape (baseline ~2596)"
pre_u={e['entity_id'] for e in pe}; post_u={e['entity_id'] for e in qe}
assert len(pre_u)==pre['unavailable_count']>0, "CONTROL FAILED: saved pre set does not match its own count"
assert len(post_u)==post['unavailable_count'], "CONTROL FAILED: the two post readers disagree on the unavailable count"
reg=json.load(tarfile.open(D+'/storage-post.tgz').extractfile('.storage/core.entity_registry'))['data']['entities']
plat={e['entity_id']:e['platform'] for e in reg}
assert len(plat)>3000, "CONTROL FAILED: entity registry did not load (baseline 5367)"
new=sorted(post_u-pre_u)
print('total',pre['total_entities'],'->',post['total_entities'],'| unavailable',len(pre_u),'->',len(post_u),'| newly unavailable',len(new))
for k,v in collections.Counter(plat.get(e,'?unregistered') for e in new).most_common(): print('  NEW unavailable by integration:',k,v)
for e in new[:40]: print('   ',e)
lost=pre['total_entities']-post['total_entities']
assert lost<=25, f"FAIL: {lost} entities disappeared (a custom integration that failed to import drops 20+)"
assert not new, f"FAIL: {len(new)} entities are unavailable now that were not before"
print('PASS')
PY
python3 $S/gate42.py $S
```

PASS prints `PASS` after `newly unavailable 0`. FAIL = an AssertionError: `FAIL: N entities are unavailable now that were
not before` (the post set minus the saved 249-entry pre set is not empty, listed per integration so a custom-fleet
member is visible), or `FAIL: N entities disappeared`. `CONTROL FAILED` means the payload was wrong, NOT that the
system is healthy or broken: fix the read first. Dry-tested 2026-10-12 against the live payloads: pre = post prints
`newly unavailable 0 / PASS`; one injected extra unavailable entity prints `FAIL: 1 entities are unavailable now that
were not before`; a truncated pre set trips the pre-count CONTROL. Z2M/BLE sleepers can flap: if the new set is only
`mqtt`/BLE platforms, re-run the snapshot once after 5 more minutes before judging; a custom integration platform in
the list is a FAIL without a second look.

### 4.3 Logs: the REAL pod log, scanned with controls

`hactl get error-log` is NOT the Home Assistant log: it is a small dict from our own helper (the full unavailable list
plus 3 logbook-filtered errors). The log is the pod log, read from the pod `startTime` (not `--since=15m`, which can roll
past the restart). The log carries ANSI colour codes and is subject to kubelet rotation, so strip colour and assert size.

```bash
kubectl logs deploy/home-assistant -c app -n home-automation --since-time="$POD_START" > $S/halog-post.log
cat > $S/gate43.sh <<'SH'
L=$1
CAN='Unable to install package|Resource busy|os error 16|Setup failed for|Error setting up|Migration handler not found|migration_error'
N=$(wc -l < "$L"); [ "$N" -ge 1000 ] || { echo "CONTROL FAILED: only $N log lines (rotated past the restart, or pod log empty)"; exit 2; }
grep -qE 'homeassistant\.(setup|components)' "$L" || { echo "CONTROL FAILED: no HA logger lines at all"; exit 2; }
H=$(sed $'s/\x1b\\[[0-9;]*m//g' "$L" | grep -ciE "$CAN"); echo "lines=$N canary_hits=$H"
[ "$H" -eq 0 ]
SH
bash $S/gate43.sh $S/halog-post.log; echo "rc=$?"
```

The pattern is the SOP canary (`Unable to install package|Resource busy|os error 16|Setup failed for custom integration`)
widened to the upstream shapes `Setup failed for` and `Error setting up entry ... for <domain>`, plus `Migration handler not
found`; case-insensitive because upstream mixes case. PASS = `canary_hits=0` and `rc=0`. FAIL looks like `canary_hits=N`
with `rc=1`. `rc=2` is a CONTROL failure (too short a log = rotated or the pod logged nothing): re-read, do not pass.
Dry-test against the live 2026-10-12 log (17,430 lines): `canary_hits=0 rc=0`; the same file with two upstream-format
sample lines appended (`... ERROR (MainThread) [homeassistant.config_entries] Error setting up entry ... for dirigera_platform` and
`... [homeassistant.setup] Setup failed for custom integration 'alexa_devices': Unable to import component`) gives
`canary_hits=2 rc=1`; a 50-line file gives `rc=2`.

The four canaries (alexa_devices, dirigera_platform, dwd_weather, custom_conversation) have chronic ERROR noise (about
106 `dirigera_platform` lines in the baseline log), so a count would hide a new failure. Compare NEW error signatures
instead (logger plus the first 80 characters, timestamps removed) against the pre-roll log from 2.3:

```bash
cat > $S/sig.sh <<'SH'
sig(){ sed $'s/\x1b\\[[0-9;]*m//g' "$1" | grep -E ' (ERROR|CRITICAL) ' | sed -E 's/^[0-9-]+ [0-9:.]+ //' | cut -c1-80 | sort -u; }
comm -13 <(sig "$1") <(sig "$2") | grep -E 'custom_components\.(alexa_devices|dirigera_platform|dwd_weather|custom_conversation)|homeassistant\.(setup|config_entries)'
SH
bash $S/sig.sh $S/halog-pre.log $S/halog-post.log
# PASS: prints nothing. FAIL looks like a line per NEW signature, e.g. "ERROR (MainThread) [homeassistant.setup] Setup failed for custom integration 'alexa_devices'..."
# Dry-test: pre = post -> 0 lines; the two sample lines appended to post -> both printed.
```

Positive control that the canary integrations actually started (a silent integration logs no errors either): the
platform lines `Setting up alexa_devices.*` and `Setting up dwd_weather.*` must each appear at least once in
`halog-post.log` (verify: `sed $'s/\x1b\\[[0-9;]*m//g' $S/halog-post.log | grep -c 'Setting up alexa_devices\.'`; the 2026-10-12 baseline log has 8 for
alexa_devices and 2 for dwd_weather). `dirigera_platform` and `custom_conversation` log no `Setting up <domain>.` platform
lines in the baseline (measured: 0 each), so their start check is the `loaded` state in 4.4 plus one IKEA toggle. Informational
only: `grep -iE 'DeviceEntry.config_entries|deprecated'` counts are the work queue for the custom_components, not a failure.

### 4.4 Per-integration checks (table 1.4 "Verify" column)

```bash
python3 - <<PY
import json
S='$S'
pre=json.load(open(S+'/integrations-pre.json')); post=json.load(open(S+'/integrations-post.json'))
# CONTROLS: payload is {integrations:[...], summary:{total,by_state,domains}}; baseline 215 entries, loaded 203 / not_loaded 12
assert len(post['integrations'])>=200 and post['summary']['total']==len(post['integrations']), "CONTROL FAILED: integrations payload empty/wrong shape"
key=lambda i:i['entry_id']
was={key(i):i for i in pre['integrations']}; now={key(i):i for i in post['integrations']}
bad=[(i['domain'],i['title'],was[k]['state'],i['state']) for k,i in now.items() if k in was and was[k]['state']=='loaded' and i['state']!='loaded']
gone=[(was[k]['domain'],was[k]['title']) for k in was if k not in now]
print('loaded',pre['summary']['by_state'].get('loaded'),'->',post['summary']['by_state'].get('loaded'),'| moved off loaded:',len(bad),'| entries gone:',len(gone))
for b in bad: print('  OFF-LOADED',b)
for g in gone: print('  GONE',g)
canary={i['domain']:i['state'] for i in post['integrations'] if i['domain'] in ('alexa_devices','dirigera_platform','dwd_weather','custom_conversation')}
print('canaries',canary); assert len(canary)==4 and all(v=='loaded' for v in canary.values()), "FAIL: a canary integration is not loaded (or missing)"
assert not bad and not gone, "FAIL: integration(s) moved off loaded or disappeared"
print('PASS')
PY
```

PASS prints `PASS` with `moved off loaded: 0`. FAIL = `FAIL: integration(s) moved off loaded or disappeared` (the
`OFF-LOADED` line names domain/title and the new state: `setup_error`, `setup_retry` (cloud sessions are normal for about 2
minutes and must clear: re-run once), `migration_error` (forward-only, see section 5), `not_loaded`) or `FAIL: a canary
integration ...`. CONTROL FAILED = wrong payload shape, fix the read. The 12 baseline `not_loaded` entries are not
counted (the diff only looks at entries that were `loaded` before).

Functional spot checks (operator, 10 min): one Alexa announce, one HmIP value fresh, the two Alexa todo entities
round-trip, one Shelly cover command, one Hue/IKEA light toggle, one Frigate snapshot, Assist test sentence,
one Z2M device command. Mealie shopping sync (`office/mealie-shopping-sync`, exists) is not touched by HA, but run
the SOP check once: `kubectl create job ha-sync-check -n office --from=cronjob/mealie-shopping-sync` then read its
logs (PASS: completes with exit 0 and no HA 5xx).

### 4.5 Automations, scripts, config, repairs

```bash
cd /Users/mu/code/hactl
mise exec -- hactl doctor --format json > $S/doctor-post.json
mise exec -- hactl get automations > $S/auto-post.txt ; mise exec -- hactl get scripts > $S/scripts-post.txt
wc -l $S/auto-post.txt $S/scripts-post.txt                      # CONTROL: both non-empty
python3 - <<PY
import json
d=json.load(open('$S/doctor-post.json')); print(json.dumps(d.get('summary',d))[:600])
PY
```

PASS: `doctor` summary shows no failed check that was not failed in `doctor-pre.json` (configuration check, automations,
integration status, unavailable entities). 69 automations and 1 script present (counts from the baseline); automations
in state `unavailable` or whose `last_triggered` stops updating: none. FAIL looks like: configuration check failed
(invalid YAML at load turns an automation `unavailable`, the worst silent failure), automation count < 69.
Also open Settings -> Repairs: no new "username not normalized" or "integration removed" repair.

### 4.6 Forward-only damage check (decides revert vs restore)

Absence of log lines is not enough (a migration that logs nothing still ran). Diff the per-domain config-entry
`version`/`minor_version` and the file version of `core.config_entries` before and after, from the two `.storage`
copies (parsed locally; nothing is printed except versions, tokens stay in the tarballs):

```bash
cat > $S/gate46.py <<'PY'
import json, sys, tarfile, collections
D=sys.argv[1]
def vers(tgz):
    c=json.load(tarfile.open(tgz).extractfile('.storage/core.config_entries'))
    ent=c['data']['entries']
    assert len(ent)>150, "CONTROL FAILED: config_entries did not load (baseline ~215 entries)"
    m=collections.defaultdict(set)
    for e in ent: m[e['domain']].add((e['version'],e.get('minor_version')))
    return (c['version'],c.get('minor_version')), {k:sorted(v) for k,v in m.items()}
(pf,pm),(qf,qm)=vers(D+'/storage-pre.tgz'),vers(D+'/storage-post.tgz')
moved={k:(pm.get(k),qm.get(k)) for k in set(pm)|set(qm) if pm.get(k)!=qm.get(k)}
print('file version',pf,'->',qf,'| domains',len(pm),'->',len(qm),'| domains whose entry version/minor_version moved:',len(moved))
for k,(a,b) in sorted(moved.items()): print('  MIGRATED',k,a,'->',b)
assert pf==qf, "FAIL: core.config_entries file version moved"
assert not moved, "FAIL: a config-entry version moved = forward-only migration ran -> image revert is NO LONGER safe, restore-class (section 5.2)"
print('PASS')
PY
python3 $S/gate46.py $S
kubectl logs deploy/home-assistant -c app -n home-automation --since-time="$POD_START" | sed $'s/\x1b\\[[0-9;]*m//g' | grep -iE 'migrat' | cut -c1-160 | head
```

PASS = `PASS` and no `migrat` log line: an image revert (5.1) is still safe. FAIL (`MIGRATED <domain> (1, 3) -> (1, 4)`
or any `migrat` log line) does not mean the upgrade failed; it means the revert path changed to restore-class (5.2),
which is the D2 decision. Dry-test 2026-10-12: pre = post prints `moved: 0 / PASS`; a copy with the shelly entries set to
minor_version 4 prints `MIGRATED shelly [(1, 3)] -> [(1, 4)]` and the FAIL assertion; a missing/short file trips the CONTROL.
Also confirm `.HA_VERSION` reads `2026.10.1` (4.1) so the post tarball is from the new generation.

### 4.7 Prometheus (secondary; skipped if kube-prometheus-stack is rolling)

`kube_pod_container_status_restarts_total{namespace="home-automation",pod=~"home-assistant-.*"}` equals 0 for the new pod.
CONTROL: the same query for `pod=~"mosquitto-.*"` returns a series (proves the metric is scraped); an empty result on
the HA query alone is meaningless. kube-prometheus-stack is the shared instrument for this read (it is in
`conflicts_with` and `touches.shared: monitoring`), so a same-night `kube-prometheus-stack-92.2.0` roll voids 4.7.

## 5) Rollback

Decide with 4.6. HA is `hostNetwork` on k8s-nuc14-01 with a Recreate Deployment and an RWO Longhorn PVC: a revert is
another full restart (downtime again), and a data restore needs the HA backup (2.2.1) or the Longhorn backup, not git alone.

### 5.1 Image revert (safe ONLY if 4.6 shows no migration and no entity loss)

```bash
git revert --no-edit <merge-sha-of-PR-310>   # restores both tag lines to 2026.9.4
git push
kubectl rollout status deploy/home-assistant -n home-automation --timeout=15m
kubectl exec deploy/home-assistant -c app -n home-automation -- cat /config/.HA_VERSION
# PASS: image 2026.9.4 live AND the 4.2 and 4.3 gates re-run (post = new snapshot, pre = the saved baseline) pass.
# NOTE: HA logs a "downgrade" warning when it sees .HA_VERSION 2026.10.1; expected, not a failure by itself.
```

### 5.2 Restore (forward-only state was touched, or any custom integration is `migration_error`)

Two restore sources, in order of preference: (A) the fresh HA backup tar from 2.2.1 (encrypted: needs the key; restoring it
through the HA UI or by placing a `.HA_RESTORE` marker restarts the pod), (B) `$S/storage-pre.tgz` for `.storage` only
(recorder DB untouched, schema 53 on both versions), (C) the Longhorn backup (last resort, loses up to the time since 03:00).

1. Revert the image as in 5.1 and let the pod come up (it may report degraded integrations).
2. Scale to zero so the files are quiescent: ask cberg-agent to `kubectl scale deploy/home-assistant --replicas=0 -n home-automation`
   (temporary; Flux/Helm will reset it on the next reconcile, so complete steps 3-4 quickly or suspend the HR:
   `flux suspend hr home-assistant -n home-automation`, resume after).
3. Restore `.storage` from `$S/storage-pre.tgz` (taken in 2.2.3) into the PVC via a one-off job mounting
   `home-assistant-config` (static PV, RWO; the HA pod must be at 0 replicas or the volume mount will not attach),
   OR restore the full HA backup tar taken in 2.2.1 through the HA UI after the 2026.9.4 pod starts.
4. Last resort: Longhorn restore of `home-assistant-config` from the newest Completed Backup CR (docs/sops/longhorn.md; keep the
   speaking PV/volume name, `volumeHandle` is immutable so restore under the SAME name). 2.4 proved on the day before that
   this backup opens and passes `PRAGMA integrity_check`.
5. Resume: `flux resume hr home-assistant -n home-automation`; verify with 4.1-4.5 against the pre-change baseline.

Cost of restore: automations triggered, helper values and recorder history written since the backup are lost (the
recorder DB is NOT migrated, so a DB-only restore is not needed). This is the D2 trade-off the operator decides.

## 6) Interference notes

- Whole-house impact during the Recreate gap (~5-10 min): every automation and script is off; zigbee/matter/ESPHome
  hubs stay up and re-sync on start. Do it when nobody is relying on lights/heating (attended Sunday).
- Do not share the slot with node reboots (talos-linux-1.14.2, exclusive on sun 2026-11-01) or the Longhorn minor
  (longhorn-1.13.0, exclusive on sun 2026-11-15): the pod is hostNetwork on nuc14-01 and its PVC is single-attach.
- Shared instrumentation: `kube-prometheus-stack-92.2.0` must not roll the same night (4.7 reads Prometheus), and
  `edot-collector-0.162.0` drops pod logs in Elasticsearch while it rolls (4.3 reads `kubectl logs`, which is unaffected,
  but the operator's secondary log view is).
- Order: the otel-operator HelmRelease must read Ready=True (premise `otel-operator-helmrelease-ready`, the SOLE gate; no
  `depends_on`) before this plan runs. A Flux batch revert from another plan must not touch this release.
- app-template-5.3.0 re-renders this HelmRelease (label-only, no pod roll). Run it in a different slot, otherwise
  `rollout status` and generation checks here cannot be attributed.
- nextcloud-fleet-35.0.1 and nocodb-2026.09.1 are `backup-restore` plans; do not stack them with this one (scheduler
  RISK-CLASS STACKING) and do not ask the operator to verify two apps at once.
- The ~2.6k entities mean 4.2 and 4.4 are long reads; budget the 85 minutes accordingly. The restore proof (2.4)
  is the day before and holds only scratch objects (`home-assistant-config-restoretest`, `ha-restoretest`).
