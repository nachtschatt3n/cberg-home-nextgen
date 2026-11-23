---
plan_id: home-assistant-2026.11.2
component: home-assistant              # Deployment home-automation/home-assistant (app-template HelmRelease, image pinned TWICE: containers.app + initContainers.certifi-patch)
pr: 508                                # Renovate "update ghcr.io/home-assistant/home-assistant ( 2026.11.0 -> 2026.11.2 )", OPEN MERGEABLE, Flate Render Gate + both Flux Local Diff SUCCESS (gh pr view 508, 2026-11-23); diff = the two tag lines only
kind: image
current: "2026.11.0"                   # MEASURED live 2026-11-23: deploy image (app + init) 2026.11.0, /config/.HA_VERSION 2026.11.0, API version 2026.11.0 RUNNING, pod home-assistant-58cd68db8c-twf7g started 2026-11-12T07:49:54Z, imageID @sha256:c6c1ca9931036bf3a2c4cc088d8db25dfea3b33935a5ecc83c40349462e2f69e (== ghcr index digest of 2026.11.0)
target: "2026.11.2"                    # ghcr index digest sha256:493a07e8f6530fc640223f4a0a5248f20a61ca2f718bb1d31efbf08a2c5ea28f (HEAD /v2/home-assistant/home-assistant/manifests/2026.11.2 = 200, 2026-11-23; 2026.11.1 = sha256:6785d1eca68747a524c156faae1b139ed415c07357386ae6fe17291986e59e82; 2026.11.3 = 404). 2026.11.2 published 2026-11-16T20:03Z, prerelease=false, draft=false, newest stable.
update_type: patch
risk: medium                           # patch with no DB/storage migration, but a whole-house Recreate restart on a hand-held (operator, 2026-10-12) component whose integrations can break while the pod stays Ready
est_duration_min: 45                   # pre-checks 10 + backup tarball 3 + merge/roll 10 + settle 5 + verification 15 + buffer 2
needs_reboot: false                    # pod restart only, no node reboot
touches:
  namespaces: [home-automation]
  resources:
    - helmrelease/home-assistant        # the edit: two tag lines in kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml
    - deployment/home-assistant         # strategy Recreate (live): the single hostNetwork pod on the RWO volume is replaced, HA is DOWN for the pull + start (~3-8 min)
    - pvc/home-assistant-config         # NOT edited by git; READ by the 3.3 tarball; written by HA itself on start (restore state, .storage); no schema migration expected (4.5 asserts it)
    - service/home-assistant            # unchanged (LoadBalancer 192.168.55.24); endpoints move to the new pod
    - httproute/home-assistant          # NOT edited; 4.2 reads the app through it
  shared:
    - home-assistant-smarthome          # every HA automation/script is OFF for the restart: lights, climate, solar helpers, irrigation, presence
    - mqtt                              # HA is a client of home-automation/mosquitto; discovery entities are re-published on start (zigbee2mqtt, teslamate, solarfocus, zero-export-controller)
    - zigbee-matter-hubs                # zigbee2mqtt / matter-server / otbr stay up but their HA entities flap to unavailable during the restart; ZHA entries are not_loaded before AND after (baseline)
    - alexa-cloud-and-hmip-cloud        # alexa_devices / homematicip_cloud re-authenticate on start (SOP step 3)
    - ollama-host                       # voice pipelines call the shared Mac mini Ollama host; no voice call is made by this plan
    - public-edge                       # HA is published on envoy-external (hass.<domain>); not edited, read by 4.2
    - monitoring                        # Prometheus is a secondary instrument only (4.7)
depends_on: []
conflicts_with:                         # every id exists in runbooks/maintenance/plans/ on 2026-11-23 (ls); read from the other plans' frontmatter, not guessed
  - talos-linux-1.14.6                  # node roll (draft): HA is hostNetwork on nuc14-03 with an RWO Longhorn volume; a drain mid-start strands the pod
  - longhorn-1.13.0                     # storage engine under the volume HA's config + DB live on (vetted, exclusive-class; its sun-attended:2026-11-22 slot has passed unexecuted)
  - flux-reconciler-impersonation       # rewires the helm-controller identity for this HelmRelease
  - helm-drift-detection                # adds spec.driftDetection to this HelmRelease
  - flux-oci-chart-sources              # rewrites the HelmRelease chart source block
  - kube-prometheus-stack-93.3.0        # restarts Prometheus (4.7 reads it)
  - postgres-digest-refresh-2026-11     # rolls home-automation postgres (teslamate-postgres, traccar-postgres) whose entities feed HA gates
  - otbr-0.4.0                          # same-namespace Thread border router feeding Thread entities: keep regressions attributable
  - otbr-thread-rcp-recovery            # same
  - n8n-2.47.7                          # home-automation sibling with HA webhooks
  - teslamate-4.5                       # home-automation sibling feeding HA through MQTT
  - frigate-reolink-go2rtc-flv          # home-automation sibling; the frigate integration is in the must-load list (4.1)
  - trmnl-ha-0.15.1                     # home-automation sibling; trmnl integration entry (not_loaded in the baseline) lives in HA
  - dashcast-1.6.48                     # home-automation sibling restart in the same namespace
exclusive: false
security_ref: F-f6c312c2                # fixable critical security finding on the 2026.11.0 image; detail stays in the DB (policy-cli.py finding show F-f6c312c2), deliberately not reproduced here
capability_change: false                # same-behaviour patch bump: bug fixes and dependency bumps only (section 1); no new route, permission, API or exposure
rollback_class: git-revert              # no recorder schema migration (SCHEMA_VERSION 53 at 2026.11.0, .1 and .2, read from upstream db_schema.py at each tag 2026-11-23) and gate 4.5 asserts no .storage/config-entry version moved; the 3.3 tarball restore is for the contingency in section 5 only
finding_refs: [F-5654e431, F-f6c312c2]  # F-5654e431 version-monitor row 2026.11.0 -> 2026.11.2 (patch); F-f6c312c2 security critical on :2026.11.0 (newer upstream tag exists). Queried 2026-11-23 (policy-cli.py finding list --grep home-assistant). F-149aad75 is the AR-029 accepted row, not ours.
review: ready-for-go@2026-11-23
status: vetted
window: null
premises:
  - id: live-is-2026-11-0-and-strategy-recreate
    why: "The plan assumes the 2026.11.0 -> 2026.11.2 delta and a Recreate strategy (single-replica RWO Longhorn volume, docs/sops/longhorn-rwo-multi-attach.md). Read from the RENDERED Deployment, not the HelmRelease."
    run: >-
      kubectl get deploy home-assistant -n home-automation -o jsonpath='{.spec.template.spec.containers[0].image}{" "}{.spec.strategy.type}'
    expect_exact: "ghcr.io/home-assistant/home-assistant:2026.11.0 Recreate"
  - id: init-container-also-2026-11-0
    why: "The certifi-patch initContainer runs the same image; both pins move together or the init builds the CA bundle from a different Python/certifi than the app."
    run: >-
      kubectl get deploy home-assistant -n home-automation -o jsonpath='{.spec.template.spec.initContainers[0].image}'
    expect_exact: "ghcr.io/home-assistant/home-assistant:2026.11.0"
  - id: git-still-pins-2026-11-0-twice
    why: "PR #508 and the fallback sed change exactly the two tag lines. If git no longer holds exactly two 2026.11.0 pins (already bumped, a third pin added), the merge/sed step is wrong."
    run: >-
      grep -c 'tag: 2026.11.0' kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml
    expect_exact: "2"
  - id: hr-ready
    why: "A HelmRelease already failing would mask whether the bump itself reconciled."
    run: >-
      kubectl get helmrelease home-assistant -n home-automation -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: home-assistant-config-volume-healthy
    why: "Rollback contingency depends on the Longhorn volume and its 23:00Z backup; a degraded volume weakens it."
    run: >-
      kubectl get volume home-assistant-config -n storage -o jsonpath='{.status.robustness}'
    expect_exact: "healthy"
  - id: mqtt-and-z2m-ready
    why: "The MQTT/Zigbee2MQTT verification compares against a healthy broker and bridge; a broker already down makes every post-roll entity read ambiguous."
    run: >-
      kubectl get deploy mosquitto zigbee2mqtt -n home-automation -o jsonpath='{range .items[*]}{.metadata.name}={.status.readyReplicas} {end}'
    expect_exact: "mosquitto=1 zigbee2mqtt=1"
sops_refs:
  - docs/sops/home-assistant-updates.md
  - docs/sops/application-update.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/longhorn.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/home-assistant-certifi-ca-trust.md
  - docs/sops/vulnerability-disclosure.md
backup_gate: "Two sources. (1) 3.3: a pre-change tarball of /config/.storage + .HA_VERSION + configuration.yaml + automations.yaml + scripts.yaml + scenes.yaml + secrets.yaml + packages/ + custom_sentences/ taken with kubectl exec and integrity-checked locally by gate_tar.py (PASS prints 'OK entries 179 config_entries 250' on 2026-11-23; a truncated stream raises EOFError, dry-tested on a 100 kB truncation; a missing required file raises AssertionError, which is how secrets.yaml missing from the first draft of the tar command was caught). (2) 3.2: runbooks/longhorn-backup-age.py home-assistant-config --max-hours 26 must print FRESH (2026-11-23: 1.5h, backup-ae7b6f000e804923 at 2026-11-22T23:07:12Z)."
restore_proof: "Not required to run: rollback_class is git-revert because no migration happens. The tarball is opened and every JSON .storage file parsed before the push (gate_tar.py); the file-level restore in 5.2 is therefore proven readable, not just present. The recorder DB (3.2 GB, /config/home-assistant_v2.db) is deliberately NOT in the tarball: schema 53 on both sides means a revert reads it unchanged; if it ever did migrate, 5.3 (Longhorn restore) is the path."
generated: "2026-11-23"
---

# Home Assistant 2026.11.0 -> 2026.11.2 (PR #508)

## 1) Summary & why held

Two stable patch releases on the November monthly minor: 2026.11.1 (published 2026-11-09, 61 PRs) and 2026.11.2
(published 2026-11-16, 48 PRs). Verified `gh api repos/home-assistant/core/releases/tags/<tag>`: both `prerelease=false`,
`draft=false`; 2026.11.2 is the newest stable (2026.11.3 returns 404 on ghcr). The operator gave an explicit GO on
2026-11-23 for an on-demand NOW run.

**Why held (a TRUE policy hold, not a false positive).** Deny rule `*home-assistant/home-assistant*` in
`runbooks/auto-update-policy.yaml` (HELD 2026-10-12 by operator decision, `security_ref: F-07517014`): this home runs
~250 config entries (234 loaded on 2026-11-23) and 33 custom components, and a release can change or remove an
integration while the pod stays Ready, so the Step 0 health gate cannot see it. The rule names three requirements and
this plan satisfies each of them:

1. **Take a backup first** -> 2.2 (Longhorn freshness gate) and 3.3 (integrity-checked tarball of the config that is
   NOT in git, with the restore command in 5.2).
2. **Check the release notes for a recorder schema migration (which makes a revert after start unsafe)** -> 1.2: none.
   `SCHEMA_VERSION = 53` at 2026.11.0, 2026.11.1 and 2026.11.2 (`homeassistant/components/recorder/db_schema.py` read
   at each tag, 2026-11-23); gate 2.1 re-reads it at run time and gate 4.5 proves no `.storage`/config-entry version moved.
3. **Verify each integration against a baseline afterwards** -> 3.3 takes the baseline, 4.1/4.3/4.4 compare every
   config entry's state and every entity against it.

What changes: ONLY the image tag, in git (two lines: `containers.app` and `initContainers.certifi-patch`). HA's
`/config` (packages, automations, scripts, `custom_components`) has no GitOps path and is NOT touched by this plan:
`/config/packages/*.yaml` and `/config/custom_components` exist in no repository and are neither edited, restored nor
reinstalled by it. The only path to the cluster is `git push` of the tag line.

### 1.1 Release notes, read in full (2026-11-23)

Source: GitHub release bodies for 2026.11.1 and 2026.11.2 (`gh api repos/home-assistant/core/releases/tags/<tag> --jq .body`).
Neither release has a "Breaking changes" section or a migration note; every entry is a bug fix, a dependency bump or a
small feature, and the two releases carry no blog post of their own.

Checked against what this install actually loads (live `/api/config/config_entries/entry`, 250 entries, 2026-11-23):

| Change (release) | Do we run it? | Verdict |
|---|---|---|
| MQTT: validate the `encoding` option, reject unknown encodings at discovery (#190539, 11.1) | `mqtt` loaded; 321 enabled MQTT registry rows (Zigbee2MQTT, teslamate, solarfocus, zero-export feed) | Only a discovery payload with an invalid `encoding` is newly rejected (that entity would then be missing). Z2M/teslamate publish default utf-8. Caught by 4.1 (entity set difference) and 4.4 (per-platform registry counts) |
| MQTT: reload loop on duplicate unique ID of a disabled entity fixed (#192176), unsubscribe callback after reload (#192440), ignore self-referencing `via_device` (#192776), 11.2 | yes | Fixes only |
| Hue: migration failing for multi-channel Zigbee devices fixed (#191719, 11.2) | `hue` loaded, 98 enabled rows | Fix |
| UniFi: aiounifi v98 (#190145, 11.1), options flow for unloaded entries (#191684, 11.2) | `unifi` x2; one entry (`default (2a00:6020:...)`) is `not_loaded` in the baseline | Baseline-relative; 4.1 compares per entry |
| Shelly: add new entities to restored sleeping RPC devices on wake (#190447), RPC cover at position 0 (#191287) | 59 `shelly` entries, 529 enabled rows | May ADD entities; gates 4.1/4.4 allow increases |
| alexa_devices bumps (aioamazondevice 17.2.7, voice event replay, redaction; 11.1/11.2) | `alexa_devices` is the CUSTOM fork (0.0.3-pr171136-on-2026.6.0 in `/config/custom_components`), which shadows the core integration | Core changes do not apply to it; the domain is in the 4.1 must-load list because it is the likeliest canary for any HA-core API change |
| ZHA 2.4.3 (#190645, 11.1) | 10 `zha` entries, ALL `not_loaded` in the baseline (SLZB hubs run Zigbee2MQTT instead) | Not exercised; unchanged baseline state |
| input_text: reject `set_value` values violating the pattern (#192100, 11.2) | 3 `input_text` helpers, none with a `pattern` (read `/config/.storage/input_text` in-pod: `[]`); automations/scripts call `input_text.set_value` with templates for `music_follow_*` and `radio_now` | Not affected: no pattern set, nothing can be rejected |
| Reolink / Axis / ONVIF / webOS / Midea / Fritz / SmartThings / SolarEdge / Tibber-adjacent fixes | no such core entries (domain list 2026-11-23); `frigate` and `teslafi`, `tibber` (core, 1 entry) are present | Tibber: no change in either release. Frigate/teslafi are custom components |
| Marketplace: rate-limit log text, README refetch (#191093, #191129, 11.1) | `marketplace` loaded (migrated from HACS in 2026.11.0) | Cosmetic |
| Frontend 20261028.5 / .6, `holidays` 0.108, Todoist SDK, aioftp 0.28.3 (security) | dashboards, `holiday` helpers used indirectly | Dependency bumps; 4.2 opens the UI path |
| Custom component API surface | 33 custom components | No developer-API change in 11.1/11.2 (the DeviceInfo / RestoreStateData changes were 2026.11.0, already live and loaded) |

### 1.2 DB / storage migration verdict: none

`SCHEMA_VERSION = 53` identical at all three tags (read 2026-11-23). No entry in either release body touches the
recorder schema, the entity/device registry versions or config-entry versions. 2026.11.0 -- the release that DID run the
forward-only migrations (HACS -> Marketplace, entity registry minor 24) -- is already live and settled since
2026-11-12, so those are not re-run. Gate 4.5 turns this verdict into a measured assertion (it fails if any `core.*`
storage file or config-entry version differs between the pre and post tarballs).

### 1.3 Memory-leak-vs-uptime context

The pod has run since 2026-11-12T07:49Z (11 days). The operator's update restarts are what cap HA's slow memory leak;
an uptime-based alert (> 4 d) is a known pattern, not a new problem. This roll resets uptime: do not read the
post-roll memory drop as an effect of 2026.11.2, and an update restart is expected and fine.

## 2) Pre-checks

All read-only. Run from the repo root. Any FAIL in section 2 means STOP, change nothing, report. Operator is present
(on-demand NOW run). `hactl` is at `/Users/mu/code/hactl` (`mise exec -- python3`, `hactl.core.load_config` /
`make_api_request(url, token, method='GET', data=None)`, signature read 2026-11-23).

### 2.1 Gates

```bash
.venv/bin/python3 runbooks/plan-premises.py home-assistant-2026.11.2 --require-premises
# PASS: all six premises pass, no REFUSED line.
gh pr view 508 --json state,mergeable --jq '.state + " " + .mergeable'
# PASS: OPEN MERGEABLE (2026-11-23). FAIL looks like: CLOSED / CONFLICTING -> use the fallback sed in step 2 of section 3.
T=$(curl -s "https://ghcr.io/token?scope=repository:home-assistant/home-assistant:pull" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -sI -H "Authorization: Bearer $T" -H 'Accept: application/vnd.oci.image.index.v1+json' https://ghcr.io/v2/home-assistant/home-assistant/manifests/2026.11.2 | grep -iE '^HTTP|docker-content-digest'
# PASS: HTTP/2 200 and docker-content-digest sha256:493a07e8f6530fc640223f4a0a5248f20a61ca2f718bb1d31efbf08a2c5ea28f.
# FAIL looks like: HTTP/2 404 (tag 2026.11.3 returns 404 with the same call, measured 2026-11-23) -> ImagePullBackOff after the Recreate; or a DIFFERENT digest -> the tag was re-pushed, STOP and re-assess.
for t in 2026.11.0 2026.11.2; do curl -fsS https://raw.githubusercontent.com/home-assistant/core/$t/homeassistant/components/recorder/db_schema.py | grep -m1 '^SCHEMA_VERSION'; done
# PASS: two identical lines (SCHEMA_VERSION = 53 both). FAIL: different numbers -> STOP, the no-migration verdict (1.2) is void.
gh api repos/home-assistant/core/releases --jq '[.[]|select(.prerelease==false)][0].tag_name'
# PASS: 2026.11.2. A newer STABLE (e.g. 2026.11.3) -> STOP: refresh this plan in place (README "When the held target MOVES");
# never bump to an unread version.
kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'
# PASS: ...@sha256:c6c1ca9931036bf3a2c4cc088d8db25dfea3b33935a5ecc83c40349462e2f69e (the PRE digest; saved in 3.3). FAIL: anything else -> the live pod is not what this plan describes.
```

Slot hygiene: no `conflicts_with` plan may be in flight. Step 0 of a window (safe-update apply) may roll other
home-automation images: take the 3.3 baselines AFTER it.

No automation mid-run: do not call any state-changing HA service, edit anything in `/config`, or install/update
anything in the Marketplace. The only mutation is the image tag in git.

### 2.2 Longhorn backup freshness gate

```bash
.venv/bin/python3 runbooks/longhorn-backup-age.py home-assistant-config --max-hours 26
# PASS: "home-assistant-config <age>h FRESH via backup-cr backup=..." (2026-11-23: 1.5h FRESH, backup-ae7b6f000e804923 at 2026-11-22T23:07:12Z).
# FAIL: "... STALE ..." exit 1 -> STOP and ask cberg-agent for a manual run of the existing CronJob
#   kubectl create job --from=cronjob/daily-backup-all-volumes manual-backup-$(date +%Y%m%d-%H%M) -n storage
#   (cronjob storage/daily-backup-all-volumes exists, schedule 0 23 * * *, heavy: all volumes).
kubectl get backups.longhorn.io -n storage -l backup-volume=home-assistant-config --sort-by=.metadata.creationTimestamp -o jsonpath='{range .items[?(@.status.state=="Completed")]}{.metadata.name}{" "}{.status.size}{"\n"}{end}' | tail -1
# PASS: a name and a size > 1000000000. FAIL: empty output, or size 0 -> STOP.
kubectl exec deploy/home-assistant -c app -n home-automation -- sh -c "find /config/backups -name '*.tar' -mmin -1500 -size +1000000k | wc -l"
# ADVISORY: >= 1 (HA's own daily Automatic_backup tar, 2026-11-22_05.08 on 2026-11-23). 0 is a warning, not a stop.
```

### 2.3 Settle check: HA is not mid-restart

```bash
kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].status.containerStatuses[0].ready}{" "}{.items[0].status.containerStatuses[0].restartCount}{"\n"}'
# PASS: "true <n>" (the live pod shows 1 restart 10+ days ago; a restart in the last hour is a FAIL: baselines would capture a half-started HA).
```

## 3) Steps

GitOps only. No `flux reconcile` unless the Flux webhook does not fire (SOP). Stop on any FAIL.

### 3.1 Confirm sections 2.1-2.3 are green.

### 3.2 (covered by 2.2) Fresh Longhorn backup gate passed.

### 3.3 Pre-change tarball (the 5.2 restore source) and baselines

```bash
S=/private/tmp/ha-pre-2026.11.2; test -e "$S" && echo "EXISTS: another session's files? list, do not delete"; mkdir -p $S
kubectl exec deploy/home-assistant -c app -n home-automation -- tar czf - -C /config --exclude=__pycache__ .storage .HA_VERSION configuration.yaml automations.yaml scripts.yaml scenes.yaml secrets.yaml packages custom_sentences > $S/config-pre.tgz
```

Write the three gate scripts into `$S` (each was dry-run on 2026-11-23, results quoted after each):

```bash
cat > $S/gate_tar.py <<'PY'
import tarfile, json, sys
p, want = sys.argv[1], sys.argv[2]
t = tarfile.open(p); names = t.getnames()          # a truncated gzip stream raises EOFError here
assert len(names) > 100, "CONTROL FAILED: tarball has %d entries" % len(names)
assert t.extractfile('.HA_VERSION').read().decode().strip() == want, ".HA_VERSION is not %s" % want
for f in ('.storage/core.config_entries', '.storage/core.entity_registry', '.storage/core.device_registry', '.storage/core.restore_state', 'automations.yaml', 'configuration.yaml', 'scripts.yaml', 'secrets.yaml'):
    assert f in names, "FAIL: %s missing from tarball" % f
bad = []
for m in t.getmembers():
    if m.isfile() and m.name.startswith('.storage/') and '/' not in m.name[9:] and not m.name.endswith(('.pem', '.ics', '.pickle')):
        try: json.load(t.extractfile(m))
        except Exception: bad.append(m.name)
assert not bad, "FAIL: unparsable .storage files: %s" % bad[:5]
ce = json.load(t.extractfile('.storage/core.config_entries'))['data']['entries']
assert len(ce) >= 200, "CONTROL FAILED: core.config_entries has %d entries" % len(ce)
print('OK entries', len(names), 'config_entries', len(ce))
PY
cat > $S/snap.py <<'PY'
import sys, json
sys.path.insert(0, '/Users/mu/code/hactl')
from hactl.core import load_config, make_api_request
out = sys.argv[1]
u, t = load_config()
states = make_api_request(u + '/api/states', t)
entries = make_api_request(u + '/api/config/config_entries/entry', t)
cfg = make_api_request(u + '/api/config', t)
assert len(states) >= 2000, "CONTROL FAILED: /api/states returned %d" % len(states)
assert len(entries) >= 200, "CONTROL FAILED: config_entries returned %d" % len(entries)
json.dump({'version': cfg['version'], 'state': cfg['state'],
           'states': {s['entity_id']: s['state'] for s in states},
           'entries': {e['entry_id']: [e['domain'], e['title'], e['state']] for e in entries}}, open(out, 'w'))
print('snap', out, 'version', cfg['version'], cfg['state'], 'states', len(states), 'entries', len(entries))
PY
cat > $S/regcount.py <<'PY'
import json, collections
e = json.load(open('/config/.storage/core.entity_registry'))['data']['entities']
assert len(e) >= 2000, "CONTROL FAILED: registry has %d rows" % len(e)
c = collections.Counter(x['platform'] for x in e if not x.get('disabled_by'))
print(json.dumps({k: c[k] for k in ('mqtt', 'zha', 'hue', 'shelly', 'esphome', 'homematicip_cloud', 'tibber', 'ollama', 'marketplace', 'template')} | {'total_enabled': sum(c.values())}))
PY
python3 -I $S/gate_tar.py $S/config-pre.tgz 2026.11.0
# PASS: "OK entries 179 config_entries 250" (4.6 MB, 2026-11-23). FAIL: AssertionError, or EOFError on a truncated exec stream -> STOP, retake.
# The tarball holds tokens and credentials: local only, never committed, never copied elsewhere.
```

Baselines (pre-change; the NEW numbers are the baseline, the figures after each are 2026-11-23 reference values):

```bash
cd /Users/mu/code/hactl && mise exec -- python3 $S/snap.py $S/pre.json
# PASS: "snap ... version 2026.11.0 RUNNING states 4206 entries 250" (a control inside the script aborts on < 2000 states).
cd /Users/mu/code/cberg-home-nextgen
kubectl exec -i deploy/home-assistant -c app -n home-automation -- python3 - < $S/regcount.py > $S/reg-pre.json; cat $S/reg-pre.json
# PASS: {"mqtt": 321, "zha": 75, "hue": 98, "shelly": 529, "esphome": 1370, ..., "total_enabled": 4191}
kubectl logs deploy/home-assistant -c app -n home-automation | sed $'s/\x1b\\[[0-9;]*m//g' > $S/halog-pre.log; wc -l < $S/halog-pre.log
# CONTROL: >= 1000 lines (54810 on 2026-11-23) or the 4.3 comparison compares nothing.
kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}' > $S/digest-pre.txt; cat $S/digest-pre.txt
# expect ...@sha256:c6c1ca9931036bf3a2c4cc088d8db25dfea3b33935a5ecc83c40349462e2f69e
cd /Users/mu/code/hactl && mise exec -- python3 - <<'PY'
import sys; sys.path.insert(0,'.')
from hactl.core import load_config, make_api_request
u,t=load_config()
r=make_api_request(u+'/api/config/core/check_config',t,method='POST',data={})
assert r.get('result')=='valid', "FAIL: check_config BEFORE the change is %s -- fix first, otherwise 4.2 cannot attribute it" % str(r)[:300]
print('PASS pre check_config valid')
PY
```

Reference baseline measured 2026-11-23: 4206 states (391 `unavailable`), 101 automations, 15 calendars, 250 config
entries = 234 loaded + 15 `not_loaded` (home_connect, smlight x2, trmnl, unifi `default (2a00:...)`, xbox, zha x9) +
1 `setup_retry` (WLED-Gledopto), z2m bridge `on` at 2.14.3, `input_boolean.hmip_sustained_outage` off. These
`not_loaded` entries are the baseline: gates compare per entry, never against an absolute "all loaded".

### 3.4 Land the tag (two lines, nothing else)

```bash
gh pr merge 508 --squash && git pull --ff-only
git show --stat HEAD | tail -3
# PASS: exactly one file changed, 2 insertions(+), 2 deletions(-). FAIL: more files (a foreign hunk) -> stop.
MERGE_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "$MERGE_AT"
```

Fallback if the PR went stale (macOS BSD sed; dry-tested 2026-11-23 on a scratch copy of the file, diff printed):

```bash
sed -i '' 's/^\([[:space:]]*tag: \)2026\.11\.0$/\12026.11.2/' kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml
git diff -U0 -- kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml | grep '^[-+] '
# dry-test diff: 49c49 "tag: 2026.11.0" -> "tag: 2026.11.2" and 74c74 the same (two lines each side, nothing else)
git commit --only kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml -m 'feat(home-assistant): 2026.11.0 -> 2026.11.2 (plan home-assistant-2026.11.2)'
git log -1 --format=%s   # confirm the subject is YOURS before pushing (shared worktree), then git push
```

### 3.5 Wait for the roll

Recreate: the old pod is deleted first, so HA is DOWN until the new pod passes readiness (pull of a ~1 GB image, pip
reinstall of custom-component requirements on first start; allow up to 15 minutes).

```bash
kubectl rollout status deploy/home-assistant -n home-automation --timeout=15m
kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].spec.containers[0].image}{" "}{.items[0].status.startTime}{" "}{.items[0].status.containerStatuses[0].imageID}{"\n"}'
# PASS: image ...:2026.11.2, startTime newer than $MERGE_AT, imageID ...@sha256:493a07e8f6530fc640223f4a0a5248f20a61ca2f718bb1d31efbf08a2c5ea28f.
# FAIL: image 2026.11.0 (rollout status green-lights the OLD generation), the c6c1ca99 digest, or ImagePullBackOff.
# Right after the merge the image may still read 2026.11.0: Flux has not reconciled yet; wait (flux get hr home-assistant -n home-automation) and re-check. Only a persistent mismatch after 5 minutes is a FAIL.
```

One restart by construction. Do NOT restart again; per-integration `reload` only with the operator's say-so.

## 4) Verification

Settle floor: wait 5 minutes after the pod is Ready (certifi-patch init, requirement reinstall, cloud re-auth, BLE
re-scan). Every gate prints PASS or FAIL; one FAIL moves to section 5, it never retries silently (except where one
re-run is stated).

```bash
S=/private/tmp/ha-pre-2026.11.2
POD_START=$(kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].status.startTime}'); echo "$POD_START"
```

### 4.0 Pod on the NEW digest (not rollout status)

```bash
kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{" "}{.items[0].status.initContainerStatuses[0].imageID}{" ready="}{.items[0].status.containerStatuses[0].ready}{" restarts="}{.items[0].status.containerStatuses[0].restartCount}{"\n"}'
# PASS: both imageIDs end @sha256:493a07e8f6530fc640223f4a0a5248f20a61ca2f718bb1d31efbf08a2c5ea28f, ready=true restarts=0.
# FAIL: either imageID still c6c1ca99 (old generation), restarts>=1 (crash-loop after start).
```

### 4.1 API, version, core config check, certifi init, entity + integration + automation comparison

```bash
cat > $S/compare.py <<'PY'
import sys, json
pre = json.load(open(sys.argv[1])); post = json.load(open(sys.argv[2])); want = sys.argv[3]
assert len(pre['states']) >= 2000 and len(post['states']) >= 2000, "CONTROL FAILED: snapshot too small (%d/%d)" % (len(pre['states']), len(post['states']))
assert post['version'] == want, "FAIL: API reports %s, expected %s (old generation or wrong target)" % (post['version'], want)
assert post['state'] == 'RUNNING', "FAIL: core state %s" % post['state']
ps, qs = pre['states'], post['states']
missing = sorted(set(ps) - set(qs))
newly = sorted(e for e in ps if ps[e] != 'unavailable' and qs.get(e) == 'unavailable')
print('entities', len(ps), '->', len(qs), '| missing', len(missing), '| newly unavailable', len(newly), '| unavailable', sum(v == 'unavailable' for v in ps.values()), '->', sum(v == 'unavailable' for v in qs.values()))
for e in missing[:20]: print('  MISSING', e)
for e in newly[:30]: print('  NEWLY-UNAVAILABLE', e)
assert len(missing) <= 10, "FAIL: %d entities lost (limit 10)" % len(missing)
assert len(newly) <= 15, "FAIL: %d entities newly unavailable (limit 15)" % len(newly)
au0 = {e for e in ps if e.startswith('automation.')}; au1 = {e for e in qs if e.startswith('automation.')}
assert len(au0) >= 90, "CONTROL FAILED: only %d automations in the pre snapshot" % len(au0)
assert au0 <= au1 and len(au1) == len(au0), "FAIL: automations %d -> %d, missing %s" % (len(au0), len(au1), sorted(au0 - au1)[:5])
assert not [e for e in au0 if qs[e] == 'unavailable' and ps[e] != 'unavailable'], "FAIL: automation(s) went unavailable"
off = [(post['entries'][k][0], post['entries'][k][1], v[2], post['entries'][k][2]) for k, v in pre['entries'].items() if k in post['entries'] and v[2] == 'loaded' and post['entries'][k][2] != 'loaded']
gone = [v[0] for k, v in pre['entries'].items() if k not in post['entries']]
print('entries loaded', sum(v[2] == 'loaded' for v in pre['entries'].values()), '->', sum(v[2] == 'loaded' for v in post['entries'].values()), '| moved off loaded', len(off), '| gone', gone)
for o in off: print('  OFF-LOADED', o)
must = ['mqtt', 'hue', 'shelly', 'tibber', 'homematicip_cloud', 'alexa_devices', 'ollama', 'telegram_bot', 'marketplace', 'esphome', 'matter', 'frigate', 'nodered', 'custom_conversation', 'dwd_weather', 'teslafi', 'traeger', 'tibber_prices', 'google', 'mobile_app']
ld0 = {v[0] for v in pre['entries'].values() if v[2] == 'loaded'}; ld1 = {v[0] for v in post['entries'].values() if v[2] == 'loaded'}
assert set(must) <= ld0, "CONTROL FAILED: %s not loaded BEFORE the change (fix the list, not the gate)" % sorted(set(must) - ld0)
assert set(must) <= ld1, "FAIL: not loaded after: %s" % sorted(set(must) - ld1)
assert not off and not gone, "FAIL: integration entry moved off loaded or disappeared"
assert qs.get('binary_sensor.zigbee2mqtt_bridge_connection_state') == 'on', "FAIL: Zigbee2MQTT bridge not online (%s)" % qs.get('binary_sensor.zigbee2mqtt_bridge_connection_state')
assert qs.get('sensor.zigbee2mqtt_bridge_version') not in (None, 'unavailable', 'unknown'), "FAIL: z2m bridge version sensor not republished"
assert qs.get('input_boolean.hmip_sustained_outage') == 'off', "FAIL: HmIP sustained-outage flag is on"
print('PASS compare: version', post['version'], '| automations', len(au1), '| z2m', qs['sensor.zigbee2mqtt_bridge_version'])
PY
kubectl logs deploy/home-assistant -c certifi-patch -n home-automation | grep -c 'redirected OK'
kubectl exec deploy/home-assistant -c app -n home-automation -- cat /config/.HA_VERSION
cd /Users/mu/code/hactl && mise exec -- python3 $S/snap.py $S/post.json
mise exec -- python3 - <<'PY'
import sys; sys.path.insert(0,'.')
from hactl.core import load_config, make_api_request
u,t=load_config()
r=make_api_request(u+'/api/config/core/check_config',t,method='POST',data={})
assert r.get('result')=='valid', "FAIL: check_config %s" % str(r)[:300]
print('PASS check_config valid')
PY
python3 -I $S/compare.py $S/pre.json $S/post.json 2026.11.2
```

CONTENTS ASSERTION: the set of entity IDs, the per-entry integration states and the 101 automations after the roll
equal the baseline (within stated tolerances), measured from `/api/states` and `/api/config/config_entries/entry`.
PASS prints `PASS compare: version 2026.11.2 | automations 101 | z2m 2.14.x`, `.HA_VERSION` 2026.11.2, certifi grep
prints `1`, and `PASS check_config valid`. FAILs (each dry-tested 2026-11-23 against synthetic snapshots built from the
live baseline): `FAIL: API reports 2026.11.0, expected 2026.11.2` (old generation), `FAIL: 30 entities lost (limit 10)`,
`FAIL: not loaded after: ['mqtt']` (an MQTT entry in `setup_retry`), `FAIL: automations 101 -> 100, missing
['automation.open_kids_room_shades']`. `setup_retry` on a cloud session (alexa_devices, tibber, homematicip_cloud,
google) is normal for ~2 minutes: re-run `snap.py` + `compare.py` ONCE after 2 minutes, then it is a FAIL. The
`check_config` result `invalid` (a YAML/package schema problem: packages are dropped silently otherwise) is a FAIL.
Certifi count `0` means the init container did not redirect (wyzeapi TLS breaks; docs/sops/home-assistant-certifi-ca-trust.md).

### 4.2 Login flow on the public hostname

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

PASS: `PASS login flow opens ...`. FAIL: `FAIL: login_flow HTTP 400/502` (route/edge or auth broken) or the CONTROL line when
the configured base URL is an IP. No credentials are sent; the flow is deleted. Honest limit: this proves the
public-hostname path answers and can open a login, not that a user can log in; the operator opens the companion app once.

### 4.3 Logs: setup failures, error spike, new noisy loggers

```bash
cat > $S/logsig.py <<'PY'
import sys, re, collections, datetime
pre_f, post_f = sys.argv[1], sys.argv[2]
rx = re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.\d+[+-]\d\d:\d\d (ERROR|CRITICAL) \([^)]*\) \[([^\]]+)\]')
def load(p):
    rows = [m.groups() for m in map(rx.match, open(p, errors='replace')) if m]
    ts = [datetime.datetime.strptime(r[0], '%Y-%m-%d %H:%M:%S') for r in rows]
    hrs = max((max(ts) - min(ts)).total_seconds() / 3600, 1.0) if ts else 1.0
    return collections.Counter(r[2] for r in rows), len(rows), hrs
pc, pn, ph = load(pre_f); qc, qn, qh = load(post_f)
assert pn >= 200, "CONTROL FAILED: only %d ERROR lines parsed from the pre log (regex stale or log empty)" % pn
new = sorted(set(qc) - set(pc))
pre_rate = pn / ph
print('pre: %d ERROR/CRITICAL over %.1f h = %.1f/h | post: %d over %.2f h = %.1f/h' % (pn, ph, pre_rate, qn, qh, qn / qh))
for l in new: print('  NEW-LOGGER', l, qc[l])
cap = 5 * pre_rate * qh + 100
assert qn <= cap, "FAIL: ERROR spike %d lines in post log > cap %.0f" % (qn, cap)
bad = [l for l in new if qc[l] >= 5]
assert not bad, "FAIL: logger(s) with >=5 ERRORs that never errored before: %s" % bad
print('PASS logs: no error spike, no new noisy logger (new loggers with <5 lines listed above for review)')
PY
kubectl logs deploy/home-assistant -c app -n home-automation --since-time="$POD_START" | sed $'s/\x1b\\[[0-9;]*m//g' > $S/halog-post.log
wc -l < $S/halog-post.log      # CONTROL: >= 500 lines (a started HA logs far more); less means the pod barely started or the read failed
grep -ciE 'unable to install|setup failed|error setting up|migration handler not found' $S/halog-post.log
echo "ERROR (MainThread) [homeassistant.setup] Setup failed for custom integration 'x': boom" | grep -ciE 'unable to install|setup failed|error setting up|migration handler not found'
# CONTROL: the echo line must print 1 (the pattern matches HA's real mixed-case text); the real-log grep above it must print 0. A control of 0 voids the gate.
python3 -I $S/logsig.py $S/halog-pre.log $S/halog-post.log
```

PASS: real-log grep prints `0`, control prints `1`, `logsig.py` prints `PASS logs`. Chronic noise in this install
(hass_nabucasa SniTun, homematicip websocket, resmed_myair, dirigera_platform, frigate API) is in the pre log too (1221
ERROR/CRITICAL over 53.6 h = 22.8/h on 2026-11-23) and does not trip it. FAIL: a non-zero first count, `FAIL: ERROR
spike ...`, or `FAIL: logger(s) with >=5 ERRORs that never errored before: [...]` (dry-tested: ten lines from a
synthetic `custom_components.boom` logger fail it; an empty pre log trips the CONTROL). Deprecation WARNINGs from
custom components are expected and are not errors.

### 4.4 MQTT and Zigbee entities present (registry counts, with control)

```bash
kubectl exec -i deploy/home-assistant -c app -n home-automation -- python3 - < $S/regcount.py > $S/reg-post.json; cat $S/reg-post.json
cat > $S/gate_regcount.py <<'PY'
import sys, json
a, b = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
assert a['mqtt'] >= 100 and a['total_enabled'] >= 2000, "CONTROL FAILED: pre registry counts implausible %s" % a
low = {k: (a[k], b.get(k)) for k in a if b.get(k, 0) < a[k]}
print('registry pre', a, '\nregistry post', b)
assert not low, "FAIL: enabled registry rows dropped (pre, post): %s" % low
print('PASS registry: no platform lost enabled entities (mqtt %d -> %d, zha %d -> %d, hue %d -> %d)' % (a['mqtt'], b['mqtt'], a['zha'], b['zha'], a['hue'], b['hue']))
PY
python3 -I $S/gate_regcount.py $S/reg-pre.json $S/reg-post.json
kubectl get deploy zigbee2mqtt mosquitto zero-export-controller teslamate -n home-automation -o jsonpath='{range .items[*]}{.metadata.name}={.status.readyReplicas} {end}'; echo
```

CONTENTS ASSERTION: the enabled entity-registry rows per platform (mqtt 321 = Zigbee2MQTT + teslamate + solarfocus +
zero-export discovery, zha 75, hue 98, shelly 529, homematicip_cloud 52, ...) did not drop, read from
`/config/.storage/core.entity_registry` in-pod (the bridge-online and MQTT-entry-loaded checks are in 4.1, the per-entity
presence is the 4.1 set difference). PASS prints `PASS registry: ...` and all four feed deployments `=1`. FAIL prints
`FAIL: enabled registry rows dropped (pre, post): {'mqtt': (321, 318)}` (dry-tested), which is exactly the shape an
MQTT discovery payload newly rejected by the 11.1 `encoding` validation would produce; investigate with
`grep -i 'encoding' $S/halog-post.log`. Increases are allowed (Shelly may add entities on wake, 11.1).

### 4.5 No storage or config-entry migration ran (turns 1.2 into a measurement)

```bash
kubectl exec deploy/home-assistant -c app -n home-automation -- tar czf - -C /config --exclude=__pycache__ .storage .HA_VERSION configuration.yaml automations.yaml scripts.yaml scenes.yaml secrets.yaml packages custom_sentences > $S/config-post.tgz
python3 -I $S/gate_tar.py $S/config-post.tgz 2026.11.2
cat > $S/gate_storagever.py <<'PY'
import tarfile, json, sys, collections
def vers(p):
    t = tarfile.open(p); out = {}
    for m in t.getmembers():
        if m.isfile() and m.name.startswith('.storage/core.') and '/' not in m.name[9:]:
            d = json.load(t.extractfile(m)); out[m.name] = (d.get('version'), d.get('minor_version'))
    ce = json.load(t.extractfile('.storage/core.config_entries'))['data']['entries']
    assert len(ce) >= 200, "CONTROL FAILED: config_entries did not load"
    cv = collections.defaultdict(set)
    for e in ce: cv[e['domain']].add((e['version'], e.get('minor_version')))
    return out, cv
(a, ac), (b, bc) = vers(sys.argv[1]), vers(sys.argv[2])
assert len(a) >= 8, "CONTROL FAILED: only %d core.* storage files in the pre tarball" % len(a)
d1 = {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}
d2 = {k: (sorted(ac.get(k, [])), sorted(bc.get(k, []))) for k in set(ac) | set(bc) if ac.get(k) != bc.get(k)}
print('core.* storage files compared', len(a), '| version changes', d1, '| config-entry version changes', d2)
assert not d1 and not d2, "FAIL: a forward-only storage/config-entry migration ran (%s %s) -> rollback needs the 3.3 tarball restore, not just git revert" % (d1, d2)
print('PASS no storage or config-entry migration')
PY
python3 -I $S/gate_storagever.py $S/config-pre.tgz $S/config-post.tgz
```

CONTENTS ASSERTION: no `core.*` storage file (21 compared) and no config-entry (domain, version, minor_version) differs
between the pre and post tarballs. PASS prints `PASS no storage or config-entry migration` and `OK entries ... config_entries 250`
for the post tarball. FAIL prints `FAIL: a forward-only storage/config-entry migration ran ({'.storage/core.entity_registry':
((1, 24), (1, 99))} {}) -> rollback needs the 3.3 tarball restore` (dry-tested with a doctored tarball: the entity registry
minor bumped to 99). A FAIL here changes the rollback in section 5 from 5.1 to 5.2.

### 4.6 Prometheus (secondary; skip if kube-prometheus-stack is rolling)

CONTROL: metric kube_pod_container_status_restarts_total -- `{namespace="home-automation",pod=~"home-assistant-.*"}` is
0 for the new pod; the same query with `pod=~"mosquitto-.*"` must return a series (proves the metric is scraped; an
empty result on the HA query alone is meaningless).

### 4.7 Security motivation (advisory, not a gate)

After the next sweep, `runbooks/policy-cli.py finding list --grep home-assistant` should no longer show F-f6c312c2 open
for `:2026.11.0`. A finding re-keyed to `:2026.11.2` with the same fixable items means upstream did not ship the fix
(no further action for a third-party image: we bump, never rebuild).

### 4.8 Operator follow-up (not gates)

`ha-agent` may run the SOP step 5 deep regression (custom sentences vs intent schema, `vacation_ai` /
`central_water_daily` packages) if the operator wants it; mark the bump verified in the report only after 4.0-4.5 all PASS.

## 5) Rollback

Triggers: any FAIL in 4.0, 4.1 (after its one re-run), 4.2, 4.3, 4.4 or 4.5.

### 5.1 Default: git revert (no migration ran, gate 4.5 PASS)

```bash
git revert --no-edit <merge-sha-of-PR-508>      # sha: git log --oneline -3 -- kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml
git log -1 --format=%s                           # confirm the subject is the revert before pushing
git show --stat HEAD | tail -3                   # PASS: 1 file, 2 insertions, 2 deletions (both tag lines back to 2026.11.0)
git push
kubectl rollout status deploy/home-assistant -n home-automation --timeout=15m
```

Confirm the cluster is back: pod imageID `...@sha256:c6c1ca9931036bf3a2c4cc088d8db25dfea3b33935a5ecc83c40349462e2f69e`,
`/config/.HA_VERSION` 2026.11.0, then re-run `snap.py` + `compare.py $S/pre.json $S/post2.json 2026.11.0` (PASS line
prints version 2026.11.0). The recorder DB is untouched by this plan (schema 53 on both sides) so a downgrade reads it
unchanged.

### 5.2 Only if gate 4.5 FAILED (a storage/config-entry version moved): file-level restore (cberg-agent, operator present)

```bash
S=/private/tmp/ha-pre-2026.11.2
python3 -I $S/gate_tar.py $S/config-pre.tgz 2026.11.0     # re-prove the restore source first: must print OK
git revert --no-edit <merge-sha-of-PR-508> && git log -1 --format=%s && git push
flux suspend hr home-assistant -n home-automation
kubectl scale deploy/home-assistant --replicas=0 -n home-automation
kubectl wait --for=delete pod -l app.kubernetes.io/name=home-assistant -n home-automation --timeout=5m
kubectl get volumeattachment -o jsonpath='{range .items[*]}{.spec.source.persistentVolumeName}{" "}{.status.attached}{"\n"}{end}' | grep home-assistant-config   # expect nothing (detached)
kubectl run ha-restore -n home-automation --restart=Never --image=ghcr.io/home-assistant/home-assistant:2026.11.0 \
  --overrides='{"spec":{"containers":[{"name":"ha-restore","image":"ghcr.io/home-assistant/home-assistant:2026.11.0","command":["sleep","3600"],"volumeMounts":[{"name":"config","mountPath":"/config"}]}],"volumes":[{"name":"config","persistentVolumeClaim":{"claimName":"home-assistant-config"}}]}}'
kubectl wait --for=condition=Ready pod/ha-restore -n home-automation --timeout=5m
kubectl cp $S/config-pre.tgz home-automation/ha-restore:/tmp/config-pre.tgz
kubectl exec ha-restore -n home-automation -- sh -c 'cd /config && tar czf /tmp/config-failed-2026.11.2.tgz .storage .HA_VERSION && tar xzf /tmp/config-pre.tgz -C /config && cat /config/.HA_VERSION'
# PASS: prints 2026.11.0. (The failed state is kept in the pod at /tmp only for diagnosis: kubectl cp it out before deleting the pod if wanted.)
kubectl delete pod ha-restore -n home-automation
flux resume hr home-assistant -n home-automation
kubectl get deploy home-assistant -n home-automation -o jsonpath='{.spec.replicas}{"\n"}'   # must print 1; if 0: kubectl scale deploy/home-assistant --replicas=1 -n home-automation
kubectl rollout status deploy/home-assistant -n home-automation --timeout=15m
```

Cost: helper values, automation `last_triggered` and registry edits between the 3.3 tarball and the restore are lost.

### 5.3 Only if the recorder DB itself migrated (it should not: schema 53 both sides): Longhorn restore

Restore `home-assistant-config` from the newest Completed Backup CR (2.2; docs/sops/longhorn.md, restore under the SAME
speaking name because `volumeHandle` is immutable); loses up to the time since the 23:00Z backup (2026-11-22T23:07Z).
Needs the pod at 0 replicas as in 5.2. Delegate to cberg-agent with the operator present.

## 6) Interference notes

- Whole-house impact during the Recreate gap (~3-8 min: pull + start): every automation and script is off, including
  irrigation and the solar helpers; zigbee/matter/ESPHome hubs stay up and re-sync. Do not combine with a node reboot
  (`talos-linux-1.14.6`) or storage work (`longhorn-1.13.0`): the restore in 5.2/5.3 depends on Longhorn attach/detach and
  `flux suspend/resume hr home-assistant`.
- `flux-reconciler-impersonation`, `helm-drift-detection`, `flux-oci-chart-sources` rewrite this HelmRelease or the
  identity that applies it: not in the same slot.
- Same-namespace siblings (`otbr-0.4.0`, `otbr-thread-rcp-recovery`, `n8n-2.47.7`, `teslamate-4.5`, `trmnl-ha-0.15.1`,
  `dashcast-1.6.48`, `frigate-reolink-go2rtc-flv`, `postgres-digest-refresh-2026-11`) feed entities into gates 4.1/4.4:
  serialise them to keep a regression attributable. `conflicts_with` carries all of them; the reciprocal entries on
  those plans are not guaranteed (`--validate` checks that refs resolve, not reciprocity).
- No `kube-prometheus-stack` bump may run the same night (4.6 reads Prometheus; `kube-prometheus-stack-93.3.0` is
  listed). The window's primary instrument is the HA API and `kubectl logs`, which a Prometheus restart does not affect.
- PR #508 touches the same two lines as any other HA bump: do not merge another HA PR in this window.
- Step 0 of any window (safe-update apply) may roll other home-automation images first: take the 3.3 baselines AFTER it.
- On-demand NOW fit: 45 min is well inside the 480 min ceiling, no reboot, `risk: medium`, `capability_change: false`,
  `rollback_class: git-revert`. The operator-given GO is the gate; `review: null` until a plan-reviewer verdict.
- After the run: close the finding rows with `policy-cli.py finding close <id> --commit <sha>` only after the next
  scan shows the image no longer carries F-f6c312c2 (4.7); F-5654e431 closes on the version snapshot.
