---
plan_id: home-assistant-2026.11.0
component: home-assistant              # Deployment home-automation/home-assistant (app-template HelmRelease, image pinned TWICE: containers.app + initContainers.certifi-patch)
pr: 487                                # Renovate "update ghcr.io/home-assistant/home-assistant ( 2026.10.2 -> 2026.11.0 )", OPEN MERGEABLE, Flate Render Gate SUCCESS (gh pr view 487, 2026-11-06); diff = the two tag lines only
kind: image
current: "2026.10.2"                   # MEASURED live 2026-11-06: deploy image (app + init) and /config/.HA_VERSION all 2026.10.2; pod started 2026-10-22T23:53:38Z (14 d uptime)
target: "2026.11.0"                    # newest STABLE: gh api repos/home-assistant/core/releases 2026-11-06 = 2026.11.0 (prerelease=false, published 2026-11-04T17:32Z); everything newer is 2026.11.0bN (prerelease=true). ghcr manifest 2026.11.0 -> HTTP 200
update_type: minor                     # monthly minor; upstream calls it "the biggest release we've ever shipped, by far" (5,827 PRs)
risk: high                             # whole-house restart + FORWARD-ONLY startup migrations in core: the HACS custom integration is replaced by the built-in Marketplace (config entry re-domained, registry rows re-platformed, custom_components/hacs and .storage/hacs.* DELETED by core), entity naming migration (core.entity_registry minor 23 -> 24), restore-state re-indexed; 33 custom components face developer-API changes (DeviceInfo dataclass, RestoreStateData.last_states removed)
est_duration_min: 100                  # pre-checks 20 + merge/roll 15 (first boot of a big minor: pip reinstall + Marketplace migration) + settle 10 (floor) + verification 35 + buffer 20
needs_reboot: false                    # pod restart only, no node reboot
touches:
  namespaces: [home-automation]
  resources:
    - "helmrelease/home-automation/home-assistant (image tag x2: containers.app + initContainers.certifi-patch), kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml"
    - "deployment/home-automation/home-assistant (strategy Recreate, verified live 2026-11-06) -> ONE pod replacement, hostNetwork on k8s-nuc14-01"
    - "pvc/home-automation/home-assistant-config (longhorn-static, RWO, 40Gi): .storage registries rewritten by startup migrations; /config/custom_components/hacs removed by core; .storage/hacs.* replaced by .storage/marketplace.*; .storage/lovelace_resources URLs rewritten /hacsfiles -> /local/community"
    - "/config/custom_components/* pip requirements are reinstalled on first boot (needs outbound PyPI; boot time rises)"
    - "httproute/home-automation/home-assistant (envoy-external): not changed, but HA's login flow behaviour changes in this release (Auth host-match rule, section 1.2)"
  shared:
    - home-assistant-smarthome          # every HA automation/script is DOWN for the restart (Recreate, no overlap): lights, climate, solar helpers, presence, irrigation
    - mqtt                              # HA is a client of home-automation/mosquitto; discovery entities are re-published on start (zigbee2mqtt, teslamate, solarfocus, zero-export-controller feed)
    - zigbee-matter-hubs                # zigbee2mqtt / matter-server / otbr stay up but their HA entities flap to unavailable during the restart
    - alexa-cloud-and-hmip-cloud        # alexa_media / alexa_devices and homematicip_cloud re-authenticate on start (HmIP wedge, SOP step 3)
    - ollama-host                       # HA voice pipelines call the shared Mac mini Ollama host (192.168.30.111:11434); the conversation test queues there
    - public-edge                       # HA is published on envoy-external; the release changes HA's own login-flow validation (domain-name access unaffected per upstream, asserted in 4.5)
    - monitoring                        # Prometheus is a secondary instrument (restart counter, 4.9)
depends_on: []
conflicts_with:                         # every id below exists in runbooks/maintenance/plans/ on 2026-11-06 (checked by ls); executed/superseded HA plans are not listed
  - talos-linux-1.14.5                  # node reboots (HA is hostNetwork on nuc14-01; a drain mid-migration strands the pod with half-migrated .storage)
  - etcd-timeouts-5000-500              # control-plane service restarts; keep the API server stable while the restore path may be needed
  - longhorn-1.13.0                     # storage engine under the volume HA's config + recorder DB live on, and the 5.2 restore path needs Longhorn
  - flux-reconciler-impersonation       # rewires the helm-controller identity for this HelmRelease (and 5.2 needs flux suspend/resume to work)
  - helm-drift-detection                # adds spec.driftDetection to this HelmRelease
  - flux-oci-chart-sources              # rewrites the HelmRelease chart source block
  - otbr-0.4.0                          # Thread border router in the same namespace feeding Thread entities; keep regressions attributable (that plan lists the HA plan too; its ref still names 2026.10.2 -> repo correction in the report)
  - otbr-thread-rcp-recovery            # same namespace, same Thread/otbr HA integration
  - n8n-fleet-2.44.6                    # home-automation sibling with HA webhooks
  - frigate-reolink-go2rtc-flv          # home-automation sibling; the frigate custom integration's entities are part of this plan's entity gate
exclusive: false                        # conflicts_with covers the known overlaps; HA's restart does not perturb other namespaces
security_ref: F-f6741f24                # fixable-critical security finding on the 2026.10.2 image; detail stays in the DB (CLAUDE.md "Information Security")
capability_change: true                 # NOT a same-behaviour bump: HACS is replaced by the built-in Marketplace (new code path that installs/updates third-party code), the login flow gains a host-match rule, entity display names change on dashboards and in voice context. Each is user-visible behaviour change.
rollback_class: backup-restore          # forward-only migrations run on first boot (HACS -> Marketplace deletes custom_components/hacs + .storage/hacs.*; entity registry minor 24). A git revert alone leaves 2026.10.2 without HACS; the restore in 5.2 is required
finding_refs: [F-f6741f24, F-636d64b5]  # F-f6741f24 security row on :2026.10.2 (closes on re-scan only if upstream ships the fixes in 2026.11.0), F-636d64b5 version-monitor row 2026.10.2 -> 2026.11.0
premises:
  - id: live-is-2026-10-2-and-strategy-recreate
    why: "The plan assumes the 2026.10.2 -> 2026.11.0 delta and a Recreate strategy (single-replica RWO Longhorn volume, docs/sops/longhorn-rwo-multi-attach.md). Read from the RENDERED Deployment, not the HelmRelease."
    run: >-
      kubectl get deploy home-assistant -n home-automation -o jsonpath='{.spec.template.spec.containers[0].image}{" "}{.spec.strategy.type}'
    expect_exact: "ghcr.io/home-assistant/home-assistant:2026.10.2 Recreate"
  - id: init-container-also-2026-10-2
    why: "The certifi-patch initContainer runs the same image; both pins move together or the init builds the CA bundle from a different Python/certifi than the app."
    run: >-
      kubectl get deploy home-assistant -n home-automation -o jsonpath='{.spec.template.spec.initContainers[0].image}'
    expect_exact: "ghcr.io/home-assistant/home-assistant:2026.10.2"
  - id: git-still-pins-2026-10-2-twice
    why: "PR #487 changes exactly the two tag lines. If git no longer holds exactly two 2026.10.2 pins (already bumped, PR #375 merged to 2026.10.4, or a third pin added), the merge/sed step is wrong."
    run: >-
      grep -c 'tag: 2026.10.2' kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml
    expect_exact: "2"
  - id: home-assistant-config-volume-healthy
    why: "Rollback is restore-class: it depends on the Longhorn volume and its 23:00 backup; a degraded volume weakens it."
    run: >-
      kubectl get volume home-assistant-config -n storage -o jsonpath='{.status.robustness}'
    expect_exact: "healthy"
  - id: mqtt-and-z2m-ready
    why: "The MQTT/Zigbee2MQTT verification compares against a healthy broker and bridge; a broker already down makes every post-roll entity read ambiguous."
    run: >-
      kubectl get deploy mosquitto zigbee2mqtt -n home-automation -o jsonpath='{range .items[*]}{.metadata.name}={.status.readyReplicas} {end}'
    expect_exact: "mosquitto=1 zigbee2mqtt=1"
status: vetted   # 2026-11-06 plan-reviewer needs-fix (1 blocking: 4.3 pattern control) -> reviewer's 3 corrections applied same day
window: null
review: ready-for-go@2026-11-06   # plan-reviewer 2026-11-06: premises 5/5, claims verified vs upstream source + live pod; sole blocking item (4.3 absence-gate pattern control) fixed, plus 2 nonblocking edits; reviewer stated ready-for-go after that fix
sops_refs: [docs/sops/home-assistant-updates.md, docs/sops/application-update.md, docs/sops/longhorn-rwo-multi-attach.md, docs/sops/longhorn.md, docs/sops/backup.md, docs/sops/verification-contents-not-shape.md, docs/sops/home-assistant-certifi-ca-trust.md]
backup_gate: "Three restore sources, the first two are gates. (1) A pre-change tarball of /config/.storage + .HA_VERSION + custom_components/hacs taken with kubectl exec and integrity-checked locally (2.3; PASS prints OK with every JSON .storage file parsed, the hacs entry and custom_components/hacs/manifest.json present; a truncated stream raises EOFError, dry-tested 2026-11-06 on a 100 kB truncation). This is the restore source for 5.2 because it is the ONLY copy of the HACS integration code core deletes. (2) The 23:00 Longhorn backup of home-assistant-config, PASS = `.venv/bin/python3 runbooks/longhorn-backup-age.py home-assistant-config --max-hours 26` prints FRESH (measured 2026-11-06 03:2x: 3.4h FRESH; the same call with --max-hours 1 prints STALE). (3) HA's built-in daily backup tar in /config/backups (advisory)."
restore_proof: "The restore in 5.2 is a file-level overwrite of .storage + custom_components/hacs from the 2.3 tarball into the quiesced PVC. Proof before the roll: the tarball is opened, every JSON registry parsed, and the hacs config entry + 108 hacs registry rows + 21 /hacsfiles dashboard resources counted from it (2.3, gate script dry-run 2026-11-06 printed `OK entries 2380 config_entries 218`). The recorder DB needs no restore: SCHEMA_VERSION is 53 at both 2026.10.2 and 2026.11.0 (measured from db_schema.py at each tag 2026-11-06; re-checked in 2.1). DECISION FOR THE OPERATOR: a scratch-volume Longhorn restore drill is NOT part of this plan; if a full volume restore within 30 days is required before a restore-class HA roll, run the recipe in `git show 655b59be^:runbooks/maintenance/plans/home-assistant-2026.10.1.md` section 2.4 the day before."
generated: "2026-11-06"
---

# Home Assistant 2026.10.2 -> 2026.11.0 (PR #487)

## 1) Summary & why held

Home Assistant 2026.11.0 is the November monthly minor (stable, published 2026-11-04; checked
`gh api repos/home-assistant/core/releases` on 2026-11-06: newest `prerelease=false` tag is 2026.11.0, everything newer
is a 2026.11.0bN beta). It was held by operator decision on 2026-10-12: this home runs ~218 config entries over ~85
domains plus 33 custom components, and a release can change or remove one of them while the pod stays Ready, so the
Step-0 health gate cannot see it. The security motivation is `F-f6741f24` (fixable critical findings on the 2026.10.2
image: upstream ships a newer tag, we bump). Whether 2026.11.0 clears them is verified by the next scan (4.10), not
assumed.

This is NOT a routine minor. Upstream's own words: "This is the biggest release we've ever shipped, by far." Three
changes in it run forward-only migrations on first boot against our PVC (1.1), which is why `rollback_class` is
`backup-restore` and `risk: high`. It is not a false-positive hold.

Note: PR #375 (2026.10.2 -> 2026.10.4, patch line) is still open. Merging #487 supersedes it; Renovate closes it on its
next run. Do NOT merge #375 in the same window (it would rewrite the same two lines).

### 1.1 Forward-only startup migrations (read from upstream code at tag 2026.11.0)

1. **HACS becomes the built-in Marketplace.** Release notes: "With this release, HACS becomes part of Home Assistant as
   the new Marketplace ... Home Assistant migrates it when it starts after the update ... The HACS installer stops at
   Home Assistant 2026.11." Upstream code, `homeassistant/loader.py@2026.11.0`: `"hacs": BlockedIntegration(None, "is
   now built into Home Assistant as the Marketplace", replaced_by="marketplace")`, and `MIGRATED_CUSTOM_INTEGRATIONS`
   rewrites the config entry to the built-in domain. `homeassistant/components/marketplace/migration.py@2026.11.0`:
   - re-platforms every `hacs` entity-registry row to `marketplace` and rewrites device identifiers (removes the HACS
     system device and its `update.hacs_update` entity);
   - rewrites dashboard resources from `/hacsfiles` (`LEGACY_DASHBOARD_RESOURCE_BASE`) to `/local/community`
     (`DASHBOARD_RESOURCE_BASE`) in the storage collection;
   - once `.storage/marketplace.repositories` exists: `shutil.rmtree(<config>/custom_components/hacs)` (skipped only for
     a symlink/`.git` dev checkout; ours is a plain directory, 52 MB, HACS 2.0.5), removes `.storage/hacs/` and unlinks
     `.storage/hacs.hacs`, `hacs.critical`, `hacs.repositories`, `hacs.data`.

   Our exposure, measured 2026-11-06: one `hacs` config entry, 108 `hacs` registry rows (54 disabled), 54 installed
   HACS repositories (31 integrations, 21 dashboard plugins, 2 themes), 21 of 29 dashboard resources under
   `/hacsfiles/`. The installed custom integrations themselves stay in `custom_components/` and keep loading; only the
   HACS manager is replaced. `/local/community/<card>` serves the same files as `/hacsfiles/<card>` on 2026.10.2 too
   (measured: both 200 `text/javascript`, a nonexistent card 404), so the resource rewrite survives a revert. The
   HACS code and registries do NOT: a 2026.10.2 pod after a plain revert has no `hacs` directory and a config entry
   whose domain it does not know. That is the restore in 5.2.
   First use of the Marketplace UI shows a risk notice an admin must accept before install/update works (release
   notes); the migration carries an existing acceptance over where one is stored. Not a gate; operator UI item.
2. **Entity naming rework.** "Entity names are now composed from the entity name and its context ... Names you gave an
   entity yourself are migrated ... the old name is kept as an alias for your voice assistants, and in the
   friendly_name attribute until the name is changed. Cards, badges, and rows ... now show the device name followed by
   the entity name." `core.entity_registry` minor version 23 -> 24 (`helpers/entity_registry.py` at each tag). Entity
   IDs, automations and scripts are unaffected per upstream. Our exposure: 39 user-named entities of 5343; 6
   automation message templates read `state_attr(..., 'friendly_name')`, which upstream says keeps the old name.
   Dashboards will look different; that is cosmetic, an operator item, not a rollback trigger (4.7 measures it).
3. **Restore-state re-index** (developer blog 2026-10-06): stored states are indexed by entity-registry id instead of
   entity id. Restoring `.storage` from the tarball (5.2) puts the old file back.

### 1.2 Backward-incompatible changes checked against what this home actually runs

Source: the "Backward-incompatible changes" section of https://www.home-assistant.io/blog/2026/11/04/release-202611/
(read in full, 2026-11-06), each checked against live `core.config_entries`, `core.entity_registry`,
`configuration.yaml`, `packages/` and `automations.yaml`:

| Change | Do we run it? | Verdict |
|---|---|---|
| Entity names (above) | yes, everywhere | cosmetic on dashboards; friendly_name kept for renamed entities; 4.7 measures |
| Auth: at a non-local IP "the address in your browser now has to match the address Home Assistant sees ... If they do not, logging in fails with 'Invalid client id'". "Domain names and local network IP addresses are accepted the same way as before." | HA is reached by domain name (`hass.<domain>` on envoy-external) and by LAN IP; no `http:` block in configuration.yaml | not affected per upstream text; 4.5 opens a real login flow on the public hostname |
| MQTT: "entities without a unique_id no longer use their device configuration" | `mqtt` loaded, 415 MQTT registry rows (all registry rows carry a unique_id by definition); no YAML `mqtt:` block | a YAML-less MQTT entity without unique_id is not in the registry; 4.2 catches any entity loss |
| Calendar and Sun: new-style `sun.*` / `calendar.event_*` triggers "with an offset but without offset_type" flip sign | 4 sun triggers with offsets in irrigation automations, all LEGACY form (`trigger: sun` + `event:`), 0 new-style triggers (grep 2026-11-06) | not affected: the legacy schema at 2026.11.0 (`sun/trigger.py` L559) is unchanged, Optional offset, no offset_type |
| Ring: deprecated ding/motion binary sensors, volume sensors, siren switch removed | `ring` loaded, 55 entities; already on `event.*`, `number.*_volume`, `siren.*` | not affected |
| Device tracker (UniFi Network): renamed trackers now start with the device name; new trackers added disabled | `unifi` x2, 134 trackers (12 enabled, 1 user-named); automations use `device_tracker.<id>` only | entity IDs unchanged; cosmetic |
| Philips Hue: "None" light effect removed | `hue` loaded; 0 `effect: none` in YAML | not affected |
| Telegram: legacy `notify` platform `telegram` removed | `telegram_bot` loaded with a notify ENTITY; no `platform: telegram` in YAML; `notify.pellet_alerts_household` is a `platform: group` of two mobile_app services (packages/pellet_notify_group.yaml) | not affected |
| Matter: concentration units, climate turn_on, tilt-only covers | `matter` entry present, 0 enabled matter entities | not affected |
| Python deps folder no longer used | Container install: "Home Assistant Container [is] not affected"; `/config/deps` is empty (4 kB) | not affected |
| Apple iCloud reminders, AdGuard Home, Uptime Kuma, SMTP, Tuya, Xiaomi, NINA, Bluesound, Nanoleaf, Evohome, others | not configured (domain list 2026-11-06; iCloud is the `icloud3` custom component, not core `icloud`) | not affected |

Operator-named integrations, from the full changelog (https://www.home-assistant.io/changelogs/core-2026.11, 4713
entries): Tibber 5 entries, Shelly 31 (new entities/sensors, "Improve state restore", config-entry-method refactor;
no removal), MQTT 37 (only the unique_id item above is behaviour-breaking), HomematicIP Cloud 18 (switches/covers/lights
rebuilt "from channels": we have 0 HmIP switch/cover/light entities, 52 binary_sensor/sensor/climate), Ollama 3
(diagnostics, unload refactor). ResMed, Dirigera, Tesla (tesla_custom, teslafi), Traeger are custom components, not in
the core changelog: covered by 1.3.

### 1.3 Custom components (33 dirs in /config/custom_components on 2026-11-06)

alexa_devices 0.0.3-pr171136-on-2026.6.0, alexa_media 5.18.0, awtrix 0.7.0, bambu_lab 2.2.26, bermuda 0.8.7, bps 0.2.1,
custom_conversation 1.7.0, dirigera_platform 0.0.1, dwd_precipitation_forecast 0.2.1, dwd_weather 5.3.0,
dynamic_energy_cost 1.2.4, dyson_local 1.5.7, flichub v1.0.28, frigate 5.15.6, gruenbeck_cloud 1.0.5, ha_hatch 1.31.9,
ha_washdata 0.5.9.1, hacs 2.0.5 (REPLACED by core, 1.1), haghs 2.3.0, homeconnect_ws 1.0.6, icloud3 3.7.7,
neonplan3d 2.0.10, nodered 4.3.2, openai_tts 3.8, resmed_myair v0.2.7, samsung_familyhub_fridge 0.1.0, solarfocus 7.0.1,
tesla_custom 3.28.0, teslafi 2.13.0, tibber_prices 0.38.0, traeger 2026.09.08, trmnl 1.0.0, wyzeapi 0.1.40.

Developer-API changes in 2026.11 that can break a custom component (developers.home-assistant.io blog), and a static
scan of all 33 (in-pod grep 2026-11-06):

- `RestoreStateData.last_states` removed: 0 hits. Every restoring component uses `async_get_last_state()` (nodered,
  dynamic_energy_cost, bambu_lab, tibber_prices), which upstream says is "not affected".
- `DeviceInfo` is now a dataclass: `[]`, `.get()`, `.update()` "still works for now" (compat layer); gone are
  `DeviceInfo({...})`, `DeviceInfo(**payload)` with foreign keys, `.copy/.setdefault/.pop/.values`, `|`, `len()`,
  `isinstance(x, dict)`. Scan: 0 hits for the removed forms; `homeconnect_ws` uses `device_info["connections"] = ...`
  item assignment (compat layer, works). Core still accepts a plain dict from `entity.device_info`
  (`helpers/entity_platform.py@2026.11.0` L876 `dict(device_info)` fallback).
- Config-entry functions return None, flows must pass `step_id`: custom integrations "can keep returning a boolean"
  and missing step_id "log a deprecation warning" until 2027.5. Not breaking now.

Honest limit: a grep is not an import. The empirical gate is 4.3/4.4: every custom domain `loaded` before must be
`loaded` after. `alexa_devices` (a PR-based fork pinned to a 2026.6.0 core) is the likeliest canary and is asserted by
name.

### 1.4 DB migration verdict: no recorder schema migration

`SCHEMA_VERSION = 53` at both 2026.10.2 and 2026.11.0 (`homeassistant/components/recorder/db_schema.py` at each tag,
2026-11-06); `REQUIRED_PYTHON_VER` (3, 14, 2) at both. Gate 2.1 re-runs the schema read.

### 1.5 Memory-leak-vs-uptime context

The pod has run 14 days (since 2026-10-22T23:53Z), 1872 MiB of a 4 GiB limit at 03:2x on 2026-11-06. The operator's
update restarts are what cap HA's slow leak; an uptime-based alert (> 4 d) is a known pattern, not a new problem. This
roll resets uptime; do not read the post-roll memory drop as an effect of 2026.11.0, and do not read a climb over the
following days as a regression unless it outruns the pre-roll slope.

## 2) Pre-checks

All read-only. Run from the repo root. `hactl` is at `/Users/mu/code/hactl` (`mise exec -- python3`, helpers
`hactl.core.load_config` / `make_api_request(url, token, method='GET', data=None)`, signature checked 2026-11-06).
Operator PRESENT (capability_change: true routes this plan HUMAN-GATED). Any FAIL in section 2 means STOP, change
nothing, report.

### 2.1 Gates

```bash
gh pr view 487 --json state,mergeable --jq '.state + " " + .mergeable'
# PASS: OPEN MERGEABLE (measured 2026-11-06). FAIL looks like: CLOSED / CONFLICTING -> use the fallback sed in step 2.
T=$(curl -s "https://ghcr.io/token?scope=repository:home-assistant/home-assistant:pull" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $T" -H 'Accept: application/vnd.oci.image.index.v1+json' https://ghcr.io/v2/home-assistant/home-assistant/manifests/2026.11.0
# PASS: 200 (2026-11-06). FAIL looks like: 404 (tag 2026.99.9 returns 404 with the same call, measured) -> ImagePullBackOff after Recreate.
for t in 2026.10.2 2026.11.0; do curl -fsS https://raw.githubusercontent.com/home-assistant/core/$t/homeassistant/components/recorder/db_schema.py | grep -m1 '^SCHEMA_VERSION'; done
# PASS: two identical lines (SCHEMA_VERSION = 53 both). FAIL: different numbers -> STOP, the no-DB-migration verdict is void.
gh api repos/home-assistant/core/releases --jq '[.[]|select(.prerelease==false)][0].tag_name'
# PASS: 2026.11.0. A newer STABLE (e.g. 2026.11.1) -> STOP: refresh this plan in place (target + 1.1/1.2 re-read +
# re-review, README "When the held target MOVES"); never bump to an unread version. A beta cannot print (filter).
.venv/bin/python3 runbooks/plan-premises.py home-assistant-2026.11.0
# PASS: all five premises pass.
```

Slot hygiene: `.venv/bin/python3 runbooks/maintenance-plan.py --open` must not show any `conflicts_with` id above
scheduled into this slot. Step 0 of the window (safe-update apply) may also roll home-automation images: it runs
first; take the 2.3 baselines AFTER it.

No automation mid-run: do not call any state-changing HA service (the only service call in this plan is the read-only
`todo.get_items` with `return_response` in 4.4), do not edit anything in `/config`, do not install/update anything
in HACS or the Marketplace, do not remove a user. The only mutation is the image tag in git.

### 2.2 Backups

```bash
.venv/bin/python3 runbooks/longhorn-backup-age.py home-assistant-config --max-hours 26
# PASS: "home-assistant-config <age>h FRESH via backup-cr backup=..." (2026-11-06: 3.4h FRESH, backup-cfa553179b0d4bae).
# FAIL: "... STALE ..." exit 1 -> STOP and ask cberg-agent for:
#   kubectl create job --from=cronjob/daily-backup-all-volumes manual-backup-$(date +%Y%m%d-%H%M) -n storage   (cronjob exists, schedule 0 23 * * *; heavy, all volumes)
kubectl get backups.longhorn.io -n storage -l backup-volume=home-assistant-config --sort-by=.metadata.creationTimestamp -o jsonpath='{range .items[?(@.status.state=="Completed")]}{.metadata.name}{" "}{.status.size}{"\n"}{end}' | tail -1
# PASS: a name and a size > 1000000000. FAIL: empty output, or size 0 -> STOP.
kubectl exec deploy/home-assistant -c app -n home-automation -- sh -c "find /config/backups -name '*.tar' -mmin -1500 -size +1000000k | wc -l"
# ADVISORY: >= 1 (HA's own daily backup). 0 is a warning, not a stop; the tarball + Longhorn backup are the gates.
```

### 2.3 Pre-change tarball (the 5.2 restore source) with integrity check, plus baselines

```bash
S=/private/tmp/ha-pre-2026.11.0; test -e "$S" && echo "EXISTS: another session's files? list, do not delete"; mkdir -p $S
kubectl exec deploy/home-assistant -c app -n home-automation -- tar czf - -C /config --exclude=__pycache__ .storage .HA_VERSION custom_components/hacs > $S/config-pre.tgz
cat > $S/gate23.py <<'PY'
import tarfile, json, sys
p=sys.argv[1]; want=sys.argv[2]
t=tarfile.open(p); names=t.getnames()          # a truncated gzip stream raises EOFError here
assert len(names)>100, "CONTROL FAILED: tarball has %d entries" % len(names)
assert t.extractfile('.HA_VERSION').read().decode().strip()==want, ".HA_VERSION is not %s" % want
assert 'custom_components/hacs/manifest.json' in names, "FAIL: custom_components/hacs missing from tarball (rollback would lose HACS)"
bad=[]
for m in t.getmembers():
    if m.isfile() and m.name.startswith('.storage/') and '/' not in m.name[9:] and not m.name.endswith(('.pem','.ics','.pickle')):
        try: json.load(t.extractfile(m))
        except Exception: bad.append(m.name)
ce=json.load(t.extractfile('.storage/core.config_entries'))['data']['entries']
assert len(ce)>=200, "CONTROL FAILED: core.config_entries has %d entries" % len(ce)
assert [e for e in ce if e['domain']=='hacs'], "FAIL: no hacs config entry in the pre tarball"
for f in ('hacs.repositories','hacs.hacs','lovelace_resources','core.entity_registry','core.restore_state'):
    assert '.storage/'+f in names, "FAIL: .storage/%s missing" % f
assert not bad, "FAIL: unparsable .storage files: %s" % bad[:5]
print('OK entries',len(names),'config_entries',len(ce))
PY
python3 -I $S/gate23.py $S/config-pre.tgz 2026.10.2
# PASS: "OK entries ~2380 config_entries ~218" (dry-run 2026-11-06, 22.7 MB). FAIL: AssertionError, or EOFError on a
# truncated exec stream (dry-tested: a 100 kB truncation raises EOFError) -> STOP.
# The tarball holds tokens and credentials: local only, never committed, never copied elsewhere.
cd /Users/mu/code/hactl
mise exec -- hactl get states --format json > $S/states-pre.json
mise exec -- hactl get error-log --format json > $S/errorlog-pre.json
mise exec -- hactl get integrations --format json > $S/integrations-pre.json
mise exec -- hactl doctor --format json > $S/doctor-pre.json
mise exec -- python3 -c "import sys,json; sys.path.insert(0,'.'); from hactl.core import load_config, make_api_request; u,t=load_config(); json.dump(make_api_request(u+'/api/states',t), open('$S/apistates-pre.json','w'))"
cd /Users/mu/code/cberg-home-nextgen
kubectl logs deploy/home-assistant -c app -n home-automation > $S/halog-pre.log
kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}' > $S/digest-pre.txt
python3 - <<PY
import json
S='$S'
st=json.load(open(S+'/states-pre.json')); el=json.load(open(S+'/errorlog-pre.json')); ig=json.load(open(S+'/integrations-pre.json'))
assert st['total_entities']>=2000, "CONTROL FAILED: states payload empty/wrong shape"
assert len(el['unavailable_entities'])>0 and ig['summary']['total']==len(ig['integrations'])>=200, "CONTROL FAILED: payload empty"
print('entities',st['total_entities'],'unavailable(states)',st['unavailable_count'],'unavailable(error-log list)',len(el['unavailable_entities']),'integrations',ig['summary']['by_state'])
PY
wc -l < $S/halog-pre.log      # CONTROL: must be >= 1000 (45062 lines on 2026-11-06) or the 4.3 signature diff compares nothing
cat $S/digest-pre.txt         # expect ...@sha256:33afb0659d786213264c2211f8d91c5fe87461c56eba6a3a546eb05fc71e89f4 (2026-11-06)
```

Reference baseline measured 2026-11-06 via the API (re-measure at run time; the NEW numbers are the baseline): 2631
states, 274 unavailable, 71 automations, 7 calendars, 589 loaded components, z2m bridge `on` at version 2.14.3,
`input_boolean.hmip_sustained_outage` off.

## 3) Steps

GitOps only. No `flux reconcile` unless the Flux webhook does not fire (SOP).

1. Confirm 2.1-2.3 are green. Stop here (and say so) on any FAIL.
2. Merge PR #487 (two `tag:` lines in `kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml`, +2/-2).

```bash
gh pr merge 487 --squash && git pull --ff-only
git show --stat HEAD | tail -3
# PASS: exactly one file changed, 2 insertions/2 deletions. FAIL: more files (a foreign hunk) -> stop.
MERGE_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "$MERGE_AT"
```

   Fallback if the PR went stale (macOS BSD sed, dry-tested 2026-11-06 on a scratch copy of the file):

```bash
sed -i '' 's/^\([[:space:]]*tag: \)2026\.10\.2$/\12026.11.0/' kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml
git diff -U0 | grep '^[-+] '
# dry-test diff: 49c49 "tag: 2026.10.2" -> "tag: 2026.11.0" and 74c74 the same (two lines each side, nothing else)
git commit --only kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml -m 'feat(home-assistant): 2026.10.2 -> 2026.11.0 (plan home-assistant-2026.11.0)'
git log -1 --format=%s   # confirm the subject is YOURS before pushing (shared worktree), then git push
```

3. Wait for the roll. Recreate: the old pod is deleted first, so HA is DOWN until the new pod passes readiness (pip
   reinstall of custom-component requirements + the one-time Marketplace migration; allow up to 15 minutes).

```bash
kubectl rollout status deploy/home-assistant -n home-automation --timeout=15m
kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].spec.containers[0].image}{" "}{.items[0].status.startTime}{" "}{.items[0].status.containerStatuses[0].imageID}{"\n"}'
# PASS: image ...:2026.11.0, startTime newer than $MERGE_AT, imageID digest DIFFERENT from $S/digest-pre.txt.
# FAIL: image 2026.10.2 (rollout status green-lights the OLD generation), same digest, or ImagePullBackOff.
# If the image still reads 2026.10.2 right after the merge, Flux has not reconciled yet: wait (flux get hr home-assistant -n home-automation), then re-check. Only a persistent mismatch after 5 min is a FAIL.
```

4. One restart by construction. Do NOT restart again; per-integration `reload` only with the operator's say-so
   (CLAUDE.md rule 4). Do nothing else in the pod until section 4 is done.

## 4) Verification

Settle floor: wait 10 minutes after the pod is Ready (certifi-patch init, pip reinstall, Marketplace migration,
cloud re-auth, BLE re-scan). Every gate below prints PASS or FAIL; one FAIL moves to section 5, it never retries
silently (except where a single re-run is stated).

```bash
S=/private/tmp/ha-pre-2026.11.0
POD_START=$(kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].status.startTime}'); echo "$POD_START"
```

### 4.1 Version, digest, API, core config check, certifi init (SOP steps 1-2)

```bash
kubectl exec deploy/home-assistant -c app -n home-automation -- cat /config/.HA_VERSION ; echo
kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}{"\n"}'
kubectl logs deploy/home-assistant -c certifi-patch -n home-automation | grep -c 'redirected OK'
kubectl exec deploy/home-assistant -c app -n home-automation -- sh -c 'mount | grep -c site-packages'
cd /Users/mu/code/hactl && mise exec -- python3 - <<'PY'
import sys; sys.path.insert(0,'.')
from hactl.core import load_config, make_api_request
u,t=load_config()
c=make_api_request(u+'/api/config',t)
assert c['version']=='2026.11.0', "FAIL: API reports %s (old generation or wrong target)" % c['version']
assert c['state']=='RUNNING', "FAIL: core state %s" % c['state']
r=make_api_request(u+'/api/config/core/check_config',t,method='POST',data={})
assert r.get('result')=='valid', "FAIL: check_config %s" % str(r)[:300]
print('PASS api version',c['version'],'check_config valid, components',len(c['components']))
PY
# PASS: .HA_VERSION 2026.11.0; restartCount 0; certifi grep prints 1; site-packages mount count prints 0; python prints PASS.
# FAIL: "FAIL: API reports 2026.10.2", state NOT_RUNNING/STARTING (re-run once after 2 min), check_config "invalid" with
# errors (a YAML/package schema problem: packages are dropped silently otherwise), certifi 0 (init did not redirect:
# wyzeapi TLS breaks), mount count > 0 (EBUSY trap, docs/sops/home-assistant-certifi-ca-trust.md).
```

### 4.2 Entity gate: newly-unavailable SET difference

```bash
cd /Users/mu/code/hactl
mise exec -- hactl get states --format json > $S/states-post.json
mise exec -- hactl get error-log --format json > $S/errorlog-post.json
python3 - <<PY
import json, collections
S='$S'
pre=json.load(open(S+'/errorlog-pre.json'))['unavailable_entities']; post=json.load(open(S+'/errorlog-post.json'))['unavailable_entities']
st0=json.load(open(S+'/states-pre.json')); st1=json.load(open(S+'/states-post.json'))
assert st1['total_entities']>=2000 and len(post)>0, "CONTROL FAILED: post payload empty/wrong shape"
new=sorted({e['entity_id'] for e in post}-{e['entity_id'] for e in pre})
print('entities',st0['total_entities'],'->',st1['total_entities'],'| unavailable',len(pre),'->',len(post),'| NEW unavailable',len(new))
for e in new[:40]: print('  NEW',e)
N=15
assert st1['total_entities']>=st0['total_entities']-20, "FAIL: lost %d entities" % (st0['total_entities']-st1['total_entities'])
assert len(new)<=N, "FAIL: %d newly unavailable (limit %d)" % (len(new),N)
print('PASS')
PY
```

CONTENTS ASSERTION: the set of entities that HAVE a state did not shrink by more than 15 newly-unavailable / 20 lost
entities, measured by the error-log unavailable list and `get states` total, compared to the 2.3 baseline. PASS prints
`PASS`. FAIL prints `FAIL: ... newly unavailable` with the `NEW` list (a whole integration's prefix = a setup failure)
or `FAIL: lost N entities`. The `update.hacs_update` entity is expected to disappear (Marketplace removes the HACS system
device, 1.1): it counts toward the 20, it is not a FAIL on its own.

### 4.3 Logs: setup failures and new error signatures in the real pod log

```bash
kubectl logs deploy/home-assistant -c app -n home-automation --since-time="$POD_START" | sed $'s/\x1b\\[[0-9;]*m//g' > $S/halog-post.log
wc -l < $S/halog-post.log      # CONTROL: >= 1000
grep -ciE 'unable to install|setup failed|error setting up|migration handler not found' $S/halog-post.log
echo "ERROR (MainThread) [homeassistant.setup] Setup failed for custom integration 'x': boom" | grep -ciE 'unable to install|setup failed|error setting up|migration handler not found'
# CONTROL: the echo line above must print 1 (proves the pattern matches HA's real text); the real-log grep before it must print 0. A control count of 0 voids the gate.
grep -iE 'is now part of Home Assistant|took over the existing installation|removed what the previous installation|moved [0-9]+ dashboard resource' $S/halog-post.log | cut -c1-220
sed $'s/\x1b\\[[0-9;]*m//g' $S/halog-pre.log | grep -E ' (ERROR|CRITICAL) ' | sed -E 's/^[0-9-]+ [0-9:.]+ //' | cut -c1-90 | sort -u > $S/sig-pre.txt
grep -E ' (ERROR|CRITICAL) ' $S/halog-post.log | sed -E 's/^[0-9-]+ [0-9:.]+ //' | cut -c1-90 | sort -u > $S/sig-post.txt
comm -13 $S/sig-pre.txt $S/sig-post.txt | head -40
```

PASS: the first grep count is 0 (the SOP step 1 patterns, case-insensitive against mixed-case upstream output:
"Setup failed for custom integration 'x'", "Error setting up entry ... for x", "Unable to install package"); the second
grep shows the Marketplace takeover lines (upstream log strings from `loader.py` / `marketplace/migration.py`:
"Custom integration 'hacs' is now part of Home Assistant as 'marketplace'", "Took over the existing installation of N
entities and M devices", "Moved 21 dashboard resource(s)", "Removed what the previous installation left behind");
`comm` prints no line naming a setup failure or a loaded integration. Chronic noise (resmed_myair, dirigera_platform,
frigate API, websocket) is in both files and removed by `comm`. FAIL: a non-zero first count, or a `comm` line like
"ERROR (MainThread) [homeassistant.setup] Setup failed for custom integration 'alexa_devices' ...". Deprecation
WARNINGs from custom components (step_id, bool return) are expected and are not ERRORs.

### 4.4 Integrations, custom components, Z2M, HmIP, Alexa lists, voice (SOP steps 1, 3, 4)

```bash
cd /Users/mu/code/hactl
mise exec -- hactl get integrations --format json > $S/integrations-post.json
mise exec -- python3 - <<PY
import sys, json; sys.path.insert(0,'.')
from hactl.core import load_config, make_api_request
S='$S'
pre=json.load(open(S+'/integrations-pre.json')); post=json.load(open(S+'/integrations-post.json'))
assert len(post['integrations'])>=200, "CONTROL FAILED: integrations payload empty"
was={i['entry_id']:i for i in pre['integrations']}; now={i['entry_id']:i for i in post['integrations']}
bad=[(i['domain'],i['title'],was[k]['state'],i['state']) for k,i in now.items() if k in was and was[k]['state']=='loaded' and i['state']!='loaded']
gone=[was[k]['domain'] for k in was if k not in now and was[k]['domain']!='hacs']
print('loaded',pre['summary']['by_state'].get('loaded'),'->',post['summary']['by_state'].get('loaded'),'| moved off loaded',len(bad),'| gone',gone)
for b in bad: print('  OFF-LOADED',b)
must={'mqtt','ollama','shelly','unifi','google','tibber','homematicip_cloud','hue','telegram_bot','ring','marketplace',
      'alexa_devices','custom_conversation','dirigera_platform','dwd_weather','teslafi','resmed_myair','traeger','tibber_prices','frigate','nodered'}
ld={i['domain'] for i in post['integrations'] if i['state']=='loaded'}
assert must<=ld, "FAIL: not loaded: %s" % sorted(must-ld)
assert 'hacs' not in {i['domain'] for i in post['integrations']}, "FAIL: a hacs config entry still exists (Marketplace did not take over)"
assert not bad and not gone, "FAIL: integration(s) moved off loaded or disappeared"
u,t=load_config()
sts={s['entity_id']:s for s in make_api_request(u+'/api/states',t)}
assert sts['binary_sensor.zigbee2mqtt_bridge_connection_state']['state']=='on', "FAIL: Zigbee2MQTT bridge not online"
v=sts['sensor.zigbee2mqtt_bridge_version']['state']; assert v not in ('unavailable','unknown'), "FAIL: z2m bridge version sensor not republished (%s)" % v
assert sts['input_boolean.hmip_sustained_outage']['state']=='off', "FAIL: HmIP sustained-outage flag is on"
print('PASS integrations + z2m bridge', v, '| hmip outage flag off')
PY
```

PASS prints `PASS integrations + z2m bridge <version>`. FAIL names the domain/state: `setup_retry` on a cloud session
(alexa, tibber, homematicip_cloud, ring) is normal for ~2 minutes, re-run once; `migration_error` is forward-only, go
to 5.2. `marketplace` in `must` is the CONTENTS check that the HACS takeover produced a working integration, and the
`hacs` assertion fails if the old entry survived. `gone` excludes `hacs` on purpose (its entry is re-domained, not lost;
`entry_id` match is asserted in 4.6). Z2M version is compared for presence, not pinned (it moves independently: 2.14.2
on 2026-10-22, 2.14.3 on 2026-11-06).

HmIP (SOP step 3): if `homematicip_cloud` entities are unavailable 15 minutes after boot, check
`automation.hmip_cloud_session_self_heal` `last_triggered`; the self-heal reloads entry `01JRZY6QRWHRW34RP7ZPASGKTS`.
Investigate only if it is stale (SOP diagnose example 2).

Alexa lists (SOP step 4, read check; the account's entity ids are derived at run time from the registry so no account
name is written here):

```bash
cd /Users/mu/code/hactl && mise exec -- python3 - <<'PY'
import sys, json, urllib.request; sys.path.insert(0,'.')
from hactl.core import load_config, make_api_request
u,t=load_config()
ents=[s['entity_id'] for s in make_api_request(u+'/api/states',t) if s['entity_id'].startswith('todo.') and s['state'] not in ('unavailable','unknown')]
alexa=[e for e in ents if e not in ('todo.shopping_list','todo.mathias_todo')]
assert len(alexa)>=2, "FAIL: alexa_devices todo entities missing/unavailable: %s" % ents
for e in alexa:
    req=urllib.request.Request(u+'/api/services/todo/get_items?return_response', data=json.dumps({"entity_id":e}).encode(), headers={'Authorization':'Bearer '+t,'Content-Type':'application/json'})
    r=json.load(urllib.request.urlopen(req, timeout=60))
    items=r['service_response'][e]['items']
    print(e.split('.')[0], 'list', alexa.index(e), 'items', len(items))
print('PASS alexa lists readable')
PY
# PASS: both lists print an item count and "PASS". FAIL: KeyError/HTTP 500 or "missing/unavailable".
# The add/remove round-trip (SOP step 4, the definitive Amazon-side proof) is run ONLY with the operator present and
# removes by the STORED summary (Amazon normalises case). Then: kubectl create job ha-sync-check -n office --from=cronjob/mealie-shopping-sync ;
# kubectl logs job/ha-sync-check -n office (must print the HA item count) ; kubectl delete job ha-sync-check -n office
```

Voice pipeline (answers via the shared Ollama host, NUM_PARALLEL=1, expect up to ~90 s queued latency):

```bash
cd /Users/mu/code/hactl && mise exec -- python3 - <<'PY'
import sys, json, urllib.request; sys.path.insert(0,'.')
from hactl.core import load_config
u,t=load_config()
for agent in ('conversation.voice_gemma_e2b','conversation.ollama_conversation'):
    req=urllib.request.Request(u+'/api/conversation/process', data=json.dumps({"text":"Antworte nur mit dem einzelnen Wort Pong.","agent_id":agent,"language":"de"}).encode(), headers={'Authorization':'Bearer '+t,'Content-Type':'application/json'})
    r=json.load(urllib.request.urlopen(req, timeout=240))
    sp=r['response']['speech']['plain']['speech']; rt=r['response']['response_type']
    print(agent, rt, repr(sp[:80]))
    assert rt!='error' and 'pong' in sp.lower(), "FAIL: %s did not answer (%s %r)" % (agent, rt, sp[:120])
print('PASS voice')
PY
```

PASS: both agents return a non-error reply containing "pong". FAIL: `response_type: error` ("Sorry, I had a problem
talking to the Ollama server") or a urllib timeout (loud). Both conversation entities exist on 2026-11-06. No device
command is sent. Cloud agents (OpenAI, Gemini, OpenClaw) are not exercised (cost/external).

Per-feed spot checks (unchanged from the 10.2 plan, read-only, can FAIL):

```bash
kubectl get deploy zigbee2mqtt mosquitto zero-export-controller teslamate -n home-automation -o jsonpath='{range .items[*]}{.metadata.name}={.status.readyReplicas} {end}'; echo
# PASS: all =1 (all four =1 on 2026-11-06). Proves HA's restart did not take a feed down.
cd /Users/mu/code/hactl && mise exec -- python3 - <<'PY'
import sys; sys.path.insert(0,'.')
from hactl.core import load_config, make_api_request
u,t=load_config(); s=make_api_request(u+'/api/states',t)
cal=[x for x in s if x['entity_id'].startswith('calendar.')]
assert len(cal)>=7 and not [x for x in cal if x['state']=='unavailable'], "FAIL: calendar entities missing/unavailable: %s" % [x['entity_id'] for x in cal if x['state']=='unavailable']
sol=[x for x in s if x['entity_id'].startswith('sensor.solar_') and x['state'] not in ('unavailable','unknown')]
assert len(sol)>=4, "FAIL: only %d solar_* sensors have values" % len(sol)
au=[x for x in s if x['entity_id'].startswith('automation.')]
assert len(au)>=69 and not [x for x in au if x['state']=='unavailable'], "FAIL: automations %d, unavailable %s" % (len(au),[x['entity_id'] for x in au if x['state']=='unavailable'][:5])
print('PASS calendars',len(cal),'solar sensors with value',len(sol),'automations',len(au))
PY
```

### 4.5 Login flow on the public hostname (Auth host-match change)

```bash
cd /Users/mu/code/hactl && mise exec -- python3 - <<'PY'
import sys, json, urllib.request, urllib.error; sys.path.insert(0,'.')
from hactl.core import load_config
u,t=load_config(); b=u.rstrip('/')
host=b.split('://')[1].split(':')[0]
assert not host.replace('.','').isdigit(), "CONTROL FAILED: hactl base URL is an IP, this gate must use the hostname"
body=json.dumps({"client_id":b+"/","handler":["homeassistant",None],"redirect_uri":b+"/?auth_callback=1"}).encode()
try:
    r=json.load(urllib.request.urlopen(urllib.request.Request(b+'/auth/login_flow',data=body,headers={'Content-Type':'application/json'}),timeout=20))
except urllib.error.HTTPError as e:
    raise SystemExit("FAIL: login_flow HTTP %s %r" % (e.code, e.read()[:200]))
assert r.get('type')=='form' and r.get('step_id')=='init', "FAIL: login flow did not open: %r" % r
urllib.request.urlopen(urllib.request.Request(b+'/auth/login_flow/'+r['flow_id'],method='DELETE'),timeout=20)
print('PASS login flow opens on the hostname (form/init), flow deleted')
PY
```

PASS: `PASS login flow opens ...` (measured on 2026.10.2: `200 form init`, DELETE 200). FAIL looks like
`FAIL: login_flow HTTP 400 b'...Invalid client id...'`, the upstream error text for the new rule. Honest limit: on
2026.10.2 a mismatched client_id also opens a form, so this gate proves the hostname path still logs in, not that the
new rule is active. No credentials are sent; the flow is deleted. Operator present: also open the HA companion app
once (it uses the same hostname).

### 4.6 Marketplace takeover (the forward-only migration, CONTENTS check)

```bash
kubectl exec deploy/home-assistant -c app -n home-automation -- tar czf - -C /config .storage .HA_VERSION > $S/config-post.tgz
kubectl exec deploy/home-assistant -c app -n home-automation -- sh -c 'test -d /config/custom_components/hacs; echo hacs_dir_present=$?'
cat > $S/gatemkt.py <<'PY'
import tarfile, json, sys
pre, post = sys.argv[1], sys.argv[2]
def ld(p, f): return json.load(tarfile.open(p).extractfile('.storage/' + f))
names = set(tarfile.open(post).getnames())
ce = ld(post, 'core.config_entries')['data']['entries']
assert len(ce) >= 200, "CONTROL FAILED: post config_entries has %d entries" % len(ce)
h = [e for e in ce if e['domain'] == 'hacs']; m = [e for e in ce if e['domain'] == 'marketplace']
assert not h and len(m) == 1, "FAIL: hacs entries %d, marketplace entries %d (expected 0 and 1)" % (len(h), len(m))
er0 = ld(pre, 'core.entity_registry')['data']['entities']; er1 = ld(post, 'core.entity_registry')['data']['entities']
n0 = sum(e['platform'] == 'hacs' for e in er0); n1 = sum(e['platform'] == 'marketplace' for e in er1); left = sum(e['platform'] == 'hacs' for e in er1)
assert n0 >= 50, "CONTROL FAILED: pre registry has only %d hacs entities" % n0
assert left == 0 and n1 >= n0 - 4, "FAIL: registry not adopted: hacs %d -> marketplace %d, %d hacs rows left" % (n0, n1, left)
r0 = [i['url'] for i in ld(pre, 'lovelace_resources')['data']['items']]; r1 = [i['url'] for i in ld(post, 'lovelace_resources')['data']['items']]
want = sum(u.startswith(('/hacsfiles/', '/local/community/')) for u in r0)
got = sum(u.startswith('/local/community/') for u in r1); stale = [u for u in r1 if u.startswith('/hacsfiles/')]
assert want >= 15, "CONTROL FAILED: pre has only %d HACS dashboard resources" % want
assert not stale and got == want and len(r1) == len(r0), "FAIL: resources %d->%d, /local/community %d of %d, stale /hacsfiles %d" % (len(r0), len(r1), got, want, len(stale))
assert '.storage/marketplace.repositories' in names, "FAIL: .storage/marketplace.repositories missing (migration did not finish)"
print('PASS marketplace adopted: entry', m[0]['entry_id'][-6:], '| entities hacs', n0, '-> marketplace', n1, '| resources', got, '/local/community')
PY
python3 -I $S/gatemkt.py $S/config-pre.tgz $S/config-post.tgz
```

CONTENTS ASSERTION: the HACS install was adopted, not dropped: exactly one `marketplace` config entry and no `hacs`
entry, the ~108 `hacs` registry rows re-platformed to `marketplace` (tolerance 4: the system device's rows are removed
by design), all 21 HACS dashboard resources rewritten to `/local/community` with none left on `/hacsfiles`, and
`.storage/marketplace.repositories` present; compared to the 2.3 tarball. `hacs_dir_present=1` is expected (core
deleted `custom_components/hacs`); `=0` means the cleanup did not run (Marketplace not yet adopted: re-run once after
5 minutes, then FAIL). The gate was dry-run 2026-11-06: against the PRE tarball as "post" it prints
`FAIL: hacs entries 1, marketplace entries 0`; against a synthetic post-state it prints
`PASS marketplace adopted: entry ...4T | entities hacs 108 -> marketplace 108 | resources 21 /local/community`.

Dashboard resources actually serve (each rewritten URL fetched, JS body, not an HTML error page):

```bash
cd /Users/mu/code/hactl && mise exec -- python3 - <<PY
import sys, json, tarfile, urllib.request, urllib.error; sys.path.insert(0,'.')
from hactl.core import load_config
u,t=load_config(); b=u.rstrip('/')
r=[i['url'] for i in json.load(tarfile.open('$S/config-post.tgz').extractfile('.storage/lovelace_resources'))['data']['items'] if i['url'].startswith('/local/community/')]
assert len(r)>=15, "CONTROL FAILED: %d community resources" % len(r)
bad=[]
for p in r:
    try:
        x=urllib.request.urlopen(b+p,timeout=20); body=x.read(64)
        if x.status!=200 or body.lstrip().startswith(b'<'): bad.append((p,x.status))
    except urllib.error.HTTPError as e: bad.append((p,e.code))
assert not bad, "FAIL: %d resources do not serve: %s" % (len(bad),bad[:5])
print('PASS', len(r), 'community resources serve JS')
PY
# Negative control measured 2026-11-06: /local/community/nonexistent-card/x.js -> 404 (would land in bad).
```

Forward-only inventory (decides how much 5.2 must restore; informational, not a pass/fail):

```bash
python3 -I - $S/config-pre.tgz $S/config-post.tgz <<'PY'
import json, sys, tarfile, collections
def vers(tgz):
    ent=json.load(tarfile.open(tgz).extractfile('.storage/core.config_entries'))['data']['entries']
    assert len(ent)>150, "CONTROL FAILED: config_entries did not load"
    m=collections.defaultdict(set)
    for e in ent: m[e['domain']].add((e['version'],e.get('minor_version')))
    return m
pm,qm=vers(sys.argv[1]),vers(sys.argv[2])
for k in sorted(set(pm)|set(qm)):
    if pm.get(k)!=qm.get(k): print('  MIGRATED',k,sorted(pm.get(k,[])),'->',sorted(qm.get(k,[])))
PY
# Expected: hacs [...] -> [] and marketplace [] -> [...]. Any OTHER domain listed = an extra forward-only config-entry
# migration; note it for 5.2 (the tarball restore covers it).
```

### 4.7 Entity naming change: measure, do not roll back on it

```bash
cd /Users/mu/code/hactl
mise exec -- python3 -c "import sys,json; sys.path.insert(0,'.'); from hactl.core import load_config, make_api_request; u,t=load_config(); json.dump(make_api_request(u+'/api/states',t), open('$S/apistates-post.json','w'))"
python3 - <<PY
import json
S='$S'
def fn(p):
    return {s['entity_id']:(s.get('attributes') or {}).get('friendly_name') for s in json.load(open(p))}
a,b=fn(S+'/apistates-pre.json'),fn(S+'/apistates-post.json')
assert len(a)>=2000 and len(b)>=2000, "CONTROL FAILED: /api/states snapshot too small (%d/%d)" % (len(a),len(b))
ch=[(k,a[k],b[k]) for k in a if k in b and a[k]!=b[k]]
print('friendly_name changed on',len(ch),'of',len(a))
for c in ch[:20]: print('  ',c)
PY
```

Upstream keeps `friendly_name` for renamed entities, so the count should be small. This is reported to the operator,
NOT a rollback trigger (display text only; entity IDs and automations are unchanged). A count above ~300 means the
notification templates that read `friendly_name` (6 in automations.yaml) may now say something different: operator
reviews the list. CONTROL FAILED here means the hactl JSON shape differs; fix the read, do not skip.

### 4.8 Automations, repairs, doctor; SOP step 5 spot-check

```bash
cd /Users/mu/code/hactl
mise exec -- hactl doctor --format json > $S/doctor-post.json
python3 - <<PY
import json
a=json.load(open('$S/doctor-pre.json')); b=json.load(open('$S/doctor-post.json'))
print('post',json.dumps(b.get('summary',b))[:600]); print('pre ',json.dumps(a.get('summary',a))[:600])
PY
kubectl exec deploy/home-assistant -c app -n home-automation -- sh -c 'ls /config/custom_sentences/de /config/custom_sentences/en | wc -l; ls /config/packages/*.yaml | wc -l'
```

PASS: `post` shows no failed check that `pre` did not also fail; check_config already PASSED in 4.1 (a package dropped by
schema validation fails check_config). Then dispatch the `ha-agent` for the SOP step 5 deep regression (custom
sentences vs intent schema, `vacation_ai`/`central_water_daily` packages, `ai_person_check*.py`, the
`custom_conversation` `instructions_prompt` surviving, `/vacation-mode` dashboard). SOP Example B: mark the bump
verified only after the ha-agent reports clean. The Marketplace risk notice and any dashboard naming tidy-up are
operator UI items, listed in the report, not gates.

### 4.9 Prometheus (secondary; skip if kube-prometheus-stack is rolling)

CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="home-automation",pod=~"home-assistant-.*"}` is 0
for the new pod; the same query with `pod=~"mosquitto-.*"` must return a series (proves the metric is scraped; an empty
result on the HA query alone is meaningless).

### 4.10 Security motivation (advisory, not a gate)

After the next sweep, `runbooks/policy-cli.py finding list --grep home-assistant` should no longer show F-f6741f24 open
for `:2026.10.2`. A finding re-keyed to `:2026.11.0` with the same fixable items means upstream did not ship the fix
(no further action for a third-party image: we bump, never rebuild).

## 5) Rollback

Decide with the operator. Rollback is RESTORE-CLASS because of 1.1: the 2026.11.0 pod deleted
`custom_components/hacs` and `.storage/hacs.*` and re-domained the HACS config entry. HA is hostNetwork on k8s-nuc14-01
with a Recreate Deployment and an RWO Longhorn PVC: the restore needs the pod at 0 replicas.

Rollback triggers: any FAIL in 4.1, 4.2, 4.3, 4.4 (after its one re-run), 4.5 or 4.6. NOT triggers: 4.7 naming counts,
the Marketplace notice, deprecation warnings.

### 5.1 Why a plain `git revert` is not enough

A revert alone brings up 2026.10.2 with: no HACS code on disk, a config entry with domain `marketplace` it cannot load,
108 registry rows on an unknown platform, and an entity registry at minor 24. Custom integrations still load (their
directories are untouched), but HACS is gone. Use 5.2. Partial-acceptance alternative (operator decision only): if the
only failure is ONE custom integration, stay on 2026.11.0 and disable that config entry instead of rolling back.

### 5.2 Restore procedure (delegate to cberg-agent; operator present)

```bash
S=/private/tmp/ha-pre-2026.11.0
python3 -I $S/gate23.py $S/config-pre.tgz 2026.10.2     # re-prove the restore source first: must print OK
flux suspend hr home-assistant -n home-automation
kubectl scale deploy/home-assistant --replicas=0 -n home-automation
kubectl wait --for=delete pod -l app.kubernetes.io/name=home-assistant -n home-automation --timeout=5m
kubectl get volumeattachment -o jsonpath='{range .items[*]}{.spec.source.persistentVolumeName}{" "}{.status.attached}{"\n"}{end}' | grep home-assistant-config   # expect nothing (detached)
kubectl run ha-restore -n home-automation --restart=Never --image=ghcr.io/home-assistant/home-assistant:2026.10.2 \
  --overrides='{"spec":{"containers":[{"name":"ha-restore","image":"ghcr.io/home-assistant/home-assistant:2026.10.2","command":["sleep","3600"],"volumeMounts":[{"name":"config","mountPath":"/config"}]}],"volumes":[{"name":"config","persistentVolumeClaim":{"claimName":"home-assistant-config"}}]}}'
kubectl wait --for=condition=Ready pod/ha-restore -n home-automation --timeout=5m
kubectl cp $S/config-pre.tgz home-automation/ha-restore:/tmp/config-pre.tgz
kubectl exec ha-restore -n home-automation -- sh -c 'cd /config && tar czf /tmp/config-failed-2026.11.0.tgz .storage .HA_VERSION && rm -rf custom_components/hacs .storage/marketplace.* && tar xzf /tmp/config-pre.tgz -C /config && cat /config/.HA_VERSION && ls custom_components/hacs/manifest.json && grep -c "\"domain\": *\"hacs\"" .storage/core.config_entries'
# PASS: prints 2026.10.2, the manifest path, and 1. (The failed 2026.11.0 state is kept in the pod at /tmp only for
# diagnosis: copy it out with kubectl cp before deleting the pod if the operator wants it.)
kubectl delete pod ha-restore -n home-automation
git revert --no-edit <merge-sha-of-PR-487> && git log -1 --format=%s && git push      # both tag lines back to 2026.10.2
flux resume hr home-assistant -n home-automation      # helm upgrade restores replicas=1 at 2026.10.2
kubectl get deploy home-assistant -n home-automation -o jsonpath='{.spec.replicas}{"\n"}'   # must print 1; if 0: kubectl scale deploy/home-assistant --replicas=1 -n home-automation
kubectl rollout status deploy/home-assistant -n home-automation --timeout=15m
```

Confirm the cluster is back: deploy image `...:2026.10.2` (app and init), `/config/.HA_VERSION` 2026.10.2, then re-run
4.1 (expecting 2026.10.2), 4.2, 4.3 and 4.4 with `must` minus `marketplace` plus `hacs`, against the saved 2.3 baseline.
Lovelace resources come back as `/hacsfiles/...` from the tarball (both paths serve on 2026.10.2, measured).

Cost: helper values, automation `last_triggered` and registry edits made between the tarball (2.3) and the restore are
lost; recorder history is NOT lost (schema 53 both sides, DB not touched). If the tarball restore itself fails:
Longhorn restore of `home-assistant-config` from the newest Completed Backup CR (2.2; docs/sops/longhorn.md, restore
under the SAME speaking name, `volumeHandle` is immutable); loses up to the time since the 23:00 backup.

## 6) Interference notes

- Whole-house impact during the Recreate gap (~5-15 min: pip reinstall + one-time migration): every automation and
  script is off, including irrigation and the solar helpers; zigbee/matter/ESPHome hubs stay up and re-sync. Do not
  combine with a node reboot (`talos-linux-1.14.5`) or control-plane work (`etcd-timeouts-5000-500`): a drain in the
  middle of the Marketplace migration strands half-migrated `.storage`.
- `longhorn-1.13.0` and the Flux plans (`flux-reconciler-impersonation`, `helm-drift-detection`,
  `flux-oci-chart-sources`) must not share the slot: the restore in 5.2 depends on Longhorn attach/detach and on
  `flux suspend/resume hr home-assistant` behaving as today.
- Same-namespace siblings (`otbr-0.4.0`, `otbr-thread-rcp-recovery`, `n8n-fleet-2.44.6`, `frigate-reolink-go2rtc-flv`)
  feed entities into gates 4.2-4.4; serialise them to keep a regression attributable.
- No kube-prometheus-stack plan is open on 2026-11-06; if one appears for the same night it must be added to
  `conflicts_with` (4.9 reads Prometheus). `edot-collector-0.164.0` (nightly 2026-11-10) only affects Elasticsearch
  log shipping; this plan's log evidence uses `kubectl logs`, unaffected.
- The Ollama host (192.168.30.111) is shared: the voice test makes two short requests; do not run it while a briefing
  or another heavy Ollama job is queued (requests serialise).
- PR #375 (2026.10.2 -> 2026.10.4) touches the same two lines: do not merge it in this window; Renovate closes it after
  #487 lands.
- Window: capability_change true + restore-class rollback => HUMAN-GATED, operator present. A `sat-attended` slot fits
  (100 min, no reboot); avoid nights where Step 0 rolls other home-automation images (re-take 2.3 after Step 0).
- After the run (operator): accept the Marketplace notice once in Settings > Marketplace, glance over the main
  dashboards for the naming change, and update `docs/sops/home-assistant-updates.md` (it describes HACS reinstalling
  requirements; after this release the manager is the built-in Marketplace).
