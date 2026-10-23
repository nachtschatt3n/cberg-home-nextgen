---
plan_id: home-assistant-2026.10.2
component: home-assistant              # Deployment home-automation/home-assistant (app-template HelmRelease, image pinned TWICE: containers.app + initContainers.certifi-patch)
pr: 375                                # Renovate "update ghcr.io/home-assistant/home-assistant 2026.10.1 -> 2026.10.2", OPEN MERGEABLE (gh pr view 375, 2026-10-22)
kind: image
current: "2026.10.1"                   # MEASURED live 2026-10-22: deploy image + /config/.HA_VERSION both 2026.10.1 (PR #310 already landed; plan home-assistant-2026.10.1 is stale/superseded)
target: "2026.10.2"                    # newest STABLE: gh releases list 2026-10-22 = 2026.10.2 (prerelease=false, published 2026-10-16); newer tags are only betas
update_type: patch                     # second patch of the 2026.10 monthly train; 53 commits from 2026.10.1, no breaking-changes section
risk: medium                           # patch with no breaking change and no recorder schema bump, but HA itself restarts: the whole smart home is down for the Recreate gap and 31 custom_components reinstall pip requirements on boot (aiohttp 3.14.5 and a pycares pin ride in this patch)
est_duration_min: 60                   # pre-checks 15 + merge/roll 10 + settle 10 (floor) + verification 20 + buffer 5
needs_reboot: false                    # pod restart only, no node reboot
touches:
  namespaces: [home-automation]
  resources:
    - "helmrelease/home-automation/home-assistant (image tag x2: containers.app + initContainers.certifi-patch), kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml"
    - "deployment/home-automation/home-assistant (strategy Recreate, verified live 2026-10-22) -> ONE pod replacement, hostNetwork on k8s-nuc14-01"
    - "pvc/home-automation/home-assistant-config (longhorn-static, RWO): /config/.storage, /config/.HA_VERSION and the recorder DB are rewritten by the new version"
    - "/config/custom_components/* pip requirements are reinstalled on first boot (needs outbound PyPI; boot time rises)"
  shared:
    - home-assistant-smarthome          # every HA automation/script is DOWN for the restart (Recreate, no overlap): lights, climate, solar helpers, presence
    - mqtt                              # HA is a client of home-automation/mosquitto; discovery entities are re-published on start (zigbee2mqtt devices, teslamate, zero-export-controller feed)
    - zigbee-matter-hubs                # zigbee2mqtt / matter-server / otbr stay up but their HA entities flap to unavailable during the restart
    - alexa-cloud-and-hmip-cloud        # alexa_media / alexa_devices and homematicip_cloud re-authenticate on start
    - ollama-host                       # HA voice pipelines call the shared Mac mini Ollama host (192.168.30.111:11434); the conversation test loads gemma4:26b-mlx there
    - monitoring                        # Prometheus is a secondary instrument (restartCount)
depends_on: []                          # the previous plan's otel-operator gate is NOT carried over: it guarded a high-risk minor with a batch-revert concern; a patch needs no such reference point
conflicts_with:                         # every id below exists in runbooks/maintenance/plans/ on 2026-10-22 (dead refs pruned: kube-prometheus-stack-92.2.0, app-template-5.x, otel-operator-0.23.0, edot-collector-0.162.0 file is blocked-but-present and kept out)
  - talos-linux-1.14.2                  # node reboots (HA is hostNetwork on nuc14-01; a drain mid-start strands the pod)
  - talos-linux-1.14.4
  - longhorn-1.13.0                     # storage engine under the volume HA's config + recorder DB live on
  - cilium-1.20.3                       # CNI roll; hostNetwork pod still depends on the node datapath for the cluster-service backchannels (mosquitto, postgres)
  - spegel-0.8.0                        # image-pull mirror: a half-rolled mirror can strand the new image pull on nuc14-01
  - kube-prometheus-stack-92.11.0       # section 4.7 reads Prometheus; the shared instrument must not be rolling
  - flux-distribution-2.9.6             # a Flux controller roll mid-reconcile makes the HR result unattributable
  - flux-fleet-0.60.0
  - flux-reconciler-impersonation       # rewires the helm-controller identity for this HelmRelease
  - helm-drift-detection                # adds spec.driftDetection to this HelmRelease
  - flux-oci-chart-sources              # rewrites the HelmRelease chart source block
  - otbr-0.4.0                          # Thread border router in the same namespace feeding Matter/Thread entities; keep regressions attributable
  - teslamate-4.3                       # home-automation sibling feeding HA entities
  - n8n-chart-2.1.1                     # home-automation sibling with HA webhooks
  - edot-collector-0.163.1              # log shipper roll drops pod logs in Elasticsearch while the 4.3 evidence is collected
exclusive: false
security_ref: F-4a4ebf8a               # fixable-critical finding on the 2026.10.1 image; detail stays in the DB (CLAUDE.md "Information Security")
capability_change: false               # patch release: bug fixes and dependency bumps only, no new integration/feature/permission that we adopt
rollback_class: git-revert             # image revert is sufficient while 4.6 shows no config-entry migration; if 4.6 FAILS the class becomes backup-restore (5.2)
finding_refs: [F-4a4ebf8a, F-5654e431, F-b4372efb]   # F-4a4ebf8a security row for 2026.10.1 (the bump closes it if upstream 10.2 carries the fixes: re-scan after), F-5654e431 version-monitor row, F-b4372efb the older 2026.9.4 security row (stale after the 10.1 bump; closes on the next sweep)
premises:
  - id: live-is-2026-10-1-and-strategy-recreate
    why: "The plan assumes the 2026.10.1 -> 2026.10.2 delta and a Recreate strategy (single-replica RWO Longhorn volume, docs/sops/longhorn-rwo-multi-attach.md). Read from the RENDERED Deployment, not the HelmRelease."
    run: >-
      kubectl get deploy home-assistant -n home-automation -o jsonpath='{.spec.template.spec.containers[0].image}{" "}{.spec.strategy.type}'
    expect_exact: "ghcr.io/home-assistant/home-assistant:2026.10.1 Recreate"
  - id: git-still-pins-2026-10-1-twice
    why: "PR #375 changes exactly the two tag lines. If git no longer holds exactly two 2026.10.1 pins (already bumped, or a third pin added), the merge/sed step is wrong."
    run: >-
      grep -c 'tag: 2026.10.1' kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml
    expect_exact: "2"
  - id: home-assistant-config-volume-healthy
    why: "The rollback depends on the Longhorn volume and its 03:00 backup; a degraded volume weakens it."
    run: >-
      kubectl get volume home-assistant-config -n storage -o jsonpath='{.status.robustness}'
    expect_exact: "healthy"
  - id: mqtt-and-z2m-ready
    why: "The MQTT/Zigbee2MQTT verification compares against a healthy broker and bridge; a broker already down makes every post-roll entity read ambiguous."
    run: >-
      kubectl get deploy mosquitto zigbee2mqtt -n home-automation -o jsonpath='{range .items[*]}{.metadata.name}={.status.readyReplicas} {end}'
    expect_exact: "mosquitto=1 zigbee2mqtt=1"
status: executed
window: "now:2026-10-23"   # ON-DEMAND NOW run 2026-10-23 (run-now.py stamp; was None)
review: ready-for-go@2026-10-22   # plan-reviewer 2026-10-22: ready-for-go, 0 blocking; 2026.10.2 newest stable; premises 4/4
sops_refs: [docs/sops/home-assistant-updates.md, docs/sops/application-update.md, docs/sops/longhorn-rwo-multi-attach.md, docs/sops/backup.md, docs/sops/verification-contents-not-shape.md]
backup_gate: "Two independent backups before the merge. (1) A pre-change config tarball of /config/.storage + .HA_VERSION taken with kubectl exec, integrity-checked locally (section 2.3; PASS prints OK with every .storage JSON parsed, FAIL on a truncated stream). (2) The 03:00 Longhorn backup of home-assistant-config, PASS = `.venv/bin/python3 runbooks/longhorn-backup-age.py home-assistant-config --max-hours 26` prints FRESH (measured 2026-10-22: 19.4h FRESH; the same call with --max-hours 1 prints STALE). The built-in HA backup tar (/config/backups, daily ~05:00, encrypted) is a third copy but is NOT required unattended because the operator is away and `backup.create` cannot be called without a token-bearing call (section 2.2 explains the optional, token-authenticated path)."
restore_proof: "Full scratch-volume restore (the 10.1 plan's section 2.4) is NOT repeated for this patch: no recorder schema change (SCHEMA_VERSION 53 at 2026.10.1 and 2026.10.2, measured 2026-10-22) and the config volume is unchanged in kind. In its place: (a) the pre-change tarball is extracted and every .storage JSON is parsed (a restore-shaped read of the config that matters, 2.3), and (b) the newest Longhorn Completed Backup CR must exist with a non-empty size (2.2). DECISION FOR THE OPERATOR: if a scratch-volume restore within the last 30 days is required before any HA roll, run the 10.1 plan's section 2.4 recipe (git show 655b59be^:runbooks/maintenance/plans/home-assistant-2026.10.1.md has it) the day before."
---

# Home Assistant 2026.10.1 -> 2026.10.2 (PR #375)

## 1) Summary & why held

Home Assistant is on a monthly release train; 2026.10.2 is the second patch of the 2026.10 line (stable, published
2026-10-16; this plan checked `gh api repos/home-assistant/core/releases` on 2026-10-22: 2026.10.2 `prerelease=false`,
no newer stable). It is held out of the unattended lanes because `home-assistant` is on the auto-update deny list
(the whole house restarts) and because a Recreate restart of a 2.6k-entity, 31-custom-component install is never a
zero-risk step. The security motivation is `F-4a4ebf8a` (fixable critical findings on the 2026.10.1 image: upstream
ships a newer tag, we bump). Whether 2026.10.2 actually clears them is verified by the next scan, not assumed
(4.8). Operator note (2026-10-22): the earlier plan `home-assistant-2026.10.1` is superseded by the merge of PR #310
(live is already 2026.10.1) and should be marked executed; its scratch restore-proof objects and
`/private/tmp/ha-pre-2026.10.1/` were checked on 2026-10-22: no `restoretest` Volume/Job/PV exists in the cluster and
the directory is gone, so nothing needs cleaning. Do not create `/private/tmp/ha-pre-2026.10.1` again: this plan uses
its own scratch dir (2.3), and if any other session's file is found in it, say so instead of deleting it.

### 1.1 Release-note scan (2026.10.2 patch notes, read in full: 52 entries, 0 breaking changes)

Source: the GitHub release body for 2026.10.2 (`gh api repos/home-assistant/core/releases/tags/2026.10.2 --jq .body`).
No "Breaking changes" section. Entries that touch what this home runs:

- MQTT: "Fix MQTT device triggers and tags firing twice after reload" (#185998). Zigbee2MQTT devices are MQTT discovery;
  expect no behavioural regression, this removes a double-fire. Verify bridge + one device (4.4).
- aiohttp 3.14.5 (#185746) and a pycares 5.0.1 pin (#186164): shared network stack. The custom integrations that talk
  out (alexa_media, alexa_devices, wyzeapi, tibber_prices, teslafi, tesla_custom, resmed_myair) must still load: the
  4.4 gate compares each custom domain's load state against the pre-change baseline.
- Frontend 20260930.4 (#186813): UI only. "Revoke refresh tokens when removing a user" (#186558): applies only when a
  user is deleted; the long-lived token used by hactl is untouched unless someone is removed (do not remove a user in the window).
- Tesla Fleet heater-level fix (#178049), Teslemetry/Tesla Fleet diagnostics redaction: our Tesla data comes from
  `tesla_custom` and `teslafi` (custom) and TeslaMate over MQTT, none of which this touches; listed because the
  operator asked.
- Group sensor no-members crash fix (#185931), state-condition-with-duration list form (#186165, additive, our
  automations use the single-entity form, so no change).
- NOT in the notes (checked by grep on the body, 0 hits each): Ollama, Shelly, UniFi, Mealie, CalDAV/Google Calendar,
  Nextcloud, recorder, template, zha. Hoymiles/zero-export-controller and TeslaMate reach HA only through MQTT and the
  REST API (no HA core integration changed).

### 1.2 DB migration verdict: no recorder schema migration

`SCHEMA_VERSION = 53` at both 2026.10.1 and 2026.10.2 (measured 2026-10-22 from
`homeassistant/components/recorder/db_schema.py` at each tag; gate 2.1 re-runs it). Config-entry migrations are still
possible in a patch, hence the forward-only check in 4.6 that decides revert-vs-restore.

### 1.3 Custom components (31, read from /config/custom_components/*/manifest.json on 2026-10-22)

alexa_devices 0.0.3-pr171136-on-2026.6.0, alexa_media 5.17.1, awtrix 0.7.0, bambu_lab 2.2.26, bermuda 0.8.7, bps 0.2.1,
custom_conversation 1.7.0, dirigera_platform 0.0.1, dwd_precipitation_forecast 0.2.0, dwd_weather 5.2.0,
dynamic_energy_cost 1.2.4, dyson_local 1.5.7, flichub v1.0.28, frigate 5.15.6, gruenbeck_cloud 1.0.5, ha_hatch 1.31.8,
ha_washdata 0.5.8, hacs 2.0.5, haghs 2.3.0, homeconnect_ws 1.0.6, icloud3 3.7.7, nodered 4.3.2, openai_tts 3.8,
resmed_myair v0.2.7, samsung_familyhub_fridge 0.1.0, solarfocus 7.0.1, tesla_custom 3.27.0, teslafi 2.13.0,
tibber_prices 0.36.0, traeger 2026.09.08, trmnl 1.0.0, wyzeapi 0.1.39.

Honest limit: none of these manifests carries a minimum-HA field, and HACS's `hacs.json` (which holds it) is not on
disk (`/config/hacs.json` absent), so a per-component "min HA" cannot be read here. The compatibility evidence is
empirical instead: every one of them already loads on 2026.10.1, a patch does not change the custom-integration API
(no breaking section), and gate 4.4 fails the plan if any custom domain that was `loaded` before is not `loaded`
after. `alexa_devices` is a PR-based fork pinned to a 2026.6.0 core: it is the likeliest canary and is asserted by name.

## 2) Pre-checks

All read-only. Run from the repo root. `hactl` is at `/Users/mu/code/hactl` (`mise exec -- hactl ...`; it reads
HASS_URL/HASS_TOKEN through `hactl.core.load_config`). Unattended and stop-safe: any FAIL in section 2 means STOP, change nothing, report.

### 2.1 Gates

```bash
gh pr view 375 --json state,mergeable --jq '.state + " " + .mergeable'
# PASS: OPEN MERGEABLE (measured 2026-10-22). FAIL looks like: CLOSED / CONFLICTING -> use the fallback sed in step 2.
T=$(curl -s "https://ghcr.io/token?scope=repository:home-assistant/home-assistant:pull" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $T" -H 'Accept: application/vnd.oci.image.index.v1+json' https://ghcr.io/v2/home-assistant/home-assistant/manifests/2026.10.2
# PASS: 200 (measured 2026-10-22). FAIL looks like: 404 (a nonexistent tag returns 404 with the same call) -> ImagePullBackOff after Recreate.
for t in 2026.10.1 2026.10.2; do curl -fsS https://raw.githubusercontent.com/home-assistant/core/$t/homeassistant/components/recorder/db_schema.py | grep -m1 '^SCHEMA_VERSION'; done
# PASS: two identical lines (SCHEMA_VERSION = 53 both, 2026-10-22). FAIL looks like: different numbers -> STOP, the no-DB-migration verdict is void.
gh api repos/home-assistant/core/releases --jq '[.[]|select(.prerelease==false)][0].tag_name'
# PASS: 2026.10.2 (or a newer STABLE: then STOP and re-plan; do not bump to an unread version). A beta tag can never print here (prerelease filter).
.venv/bin/python3 runbooks/plan-premises.py home-assistant-2026.10.2
# PASS: all four premises pass.
```

Slot hygiene: `.venv/bin/python3 runbooks/maintenance-plan.py --open | grep -E '<this-slot-id>'` must list only this plan
among the `conflicts_with` ids (slow, about 2 minutes; run it once). Operator absence: the run needs no human input
anywhere below.

No automation mid-run: do not call any HA service, do not edit anything in `/config`, do not remove a user. The
only mutation is the image tag in git. `hactl` is used read-only (`get`, `doctor`).

### 2.2 Backups

```bash
.venv/bin/python3 runbooks/longhorn-backup-age.py home-assistant-config --max-hours 26
# PASS: "home-assistant-config <age>h FRESH via backup-cr backup=..." (2026-10-22: 19.4h FRESH, backup-b05fb8c8726048f1).
# FAIL looks like: "... STALE ..." exit 1 -> STOP and ask cberg-agent for: kubectl create job --from=cronjob/daily-backup-all-volumes manual-backup-$(date +%Y%m%d-%H%M) -n storage (cronjob exists in ns storage; heavy, all volumes)
kubectl get backups.longhorn.io -n storage -l backup-volume=home-assistant-config --sort-by=.metadata.creationTimestamp -o jsonpath='{range .items[?(@.status.state=="Completed")]}{.metadata.name}{" "}{.status.size}{"\n"}{end}' | tail -1
# PASS: a name and a size > 1000000000 bytes (a live ~7 GB volume). FAIL looks like: empty output, or size 0 -> STOP.
```

The HA built-in backup tar (daily ~05:00, `/config/backups`, encrypted) exists as a third copy. Freshness check (can fail:
the same find with `-mmin -1` prints 0):

```bash
kubectl exec deploy/home-assistant -c app -n home-automation -- sh -c "find /config/backups -name '*.tar' -mmin -1500 -size +1000000k | wc -l"
# PASS (advisory): >= 1. A 0 here is a WARNING, not a stop, because the two backups above are the gate. Taking a fresh one needs the
# `backup.create` action (operator-driven; hactl has no action-call verb): skip when unattended.
```

### 2.3 Pre-change config tarball with integrity check, plus baselines

```bash
S=/private/tmp/ha-pre-2026.10.2; test -e "$S" && echo "EXISTS: another session's files? list, do not delete" ; mkdir -p $S
kubectl exec deploy/home-assistant -c app -n home-automation -- tar czf - -C /config .storage .HA_VERSION > $S/storage-pre.tgz
python3 - <<PY
import tarfile, json
t=tarfile.open('$S/storage-pre.tgz'); names=t.getnames()      # a truncated gzip stream raises here
assert len(names)>50, "CONTROL FAILED: tarball has %d entries (expected ~91)" % len(names)
assert t.extractfile('.HA_VERSION').read().decode().strip()=='2026.10.1', ".HA_VERSION is not 2026.10.1"
bad=[]
for m in t.getmembers():
    if m.isfile() and m.name.startswith('.storage/'):
        try: json.load(t.extractfile(m))
        except Exception as e: bad.append(m.name)
ce=json.load(t.extractfile('.storage/core.config_entries'))['data']['entries']
assert len(ce)>=200, "CONTROL FAILED: core.config_entries has %d entries (live 215)" % len(ce)
assert not bad, "FAIL: unparsable .storage files: %s" % bad[:5]
print('OK entries',len(names),'config_entries',len(ce))
PY
# PASS: prints "OK entries ~91 config_entries ~215". FAIL: an AssertionError / tarfile.ReadError (truncated exec stream) -> STOP.
# The tarball holds tokens: local only, never committed, never copied elsewhere.
cd /Users/mu/code/hactl
mise exec -- hactl get states --format json > $S/states-pre.json
mise exec -- hactl get error-log --format json > $S/errorlog-pre.json
mise exec -- hactl get integrations --format json > $S/integrations-pre.json
mise exec -- hactl doctor --format json > $S/doctor-pre.json
kubectl logs deploy/home-assistant -c app -n home-automation > $S/halog-pre.log
kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}' > $S/digest-pre.txt
python3 - <<PY
import json
S='$S'
st=json.load(open(S+'/states-pre.json')); el=json.load(open(S+'/errorlog-pre.json')); ig=json.load(open(S+'/integrations-pre.json'))
assert st['total_entities']>=2000, "CONTROL FAILED: states payload empty/wrong shape"
assert len(el['unavailable_entities'])>0 and ig['summary']['total']==len(ig['integrations'])>=200, "CONTROL FAILED: payload empty"
print('entities',st['total_entities'],'unavailable(states)',st['unavailable_count'],'unavailable(error-log full list)',len(el['unavailable_entities']),'integrations',ig['summary']['by_state'])
PY
wc -l < $S/halog-pre.log      # CONTROL: must be >= 1000 or the 4.3 signature diff compares nothing
cat $S/digest-pre.txt         # expect @sha256:130241f28d01fa80dfa3b44f7d89781c188d8642ecab9024f079f19f9f82baa0 (2026-10-22)
```

Reference baseline measured 2026-10-22 (re-measure at run time; the NEW numbers are the baseline): 2616 entities, 300
unavailable in `get states` (317 in the error-log full list: use the SAME source on both sides), integrations loaded
203 / not_loaded 12 (the 12 are the 8 disabled `zha` entries, the `unifi` entry for the gateway IPv6 address, and
others that are intentionally off), pod uptime 10 days (the leak-vs-uptime pattern: the operator's update restart
resets it; an alert at uptime > 4 d is not a new problem).

## 3) Steps

GitOps only. No `flux reconcile` unless the Flux webhook does not fire (SOP).

1. Confirm 2.1-2.3 are green. Stop here (and say so) on any FAIL.
2. Merge PR #375 (two `tag:` lines in `kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml`, +2/-2).

```bash
gh pr merge 375 --squash && git pull --ff-only
git show --stat HEAD | tail -3
# PASS: exactly one file changed, 2 insertions/2 deletions. FAIL looks like: more files (a foreign hunk) -> stop.
```

   Fallback if the PR went stale (macOS BSD sed, dry-tested 2026-10-22 on a scratch copy; changes lines 49 and 74 only):

```bash
sed -i '' 's/^\([[:space:]]*tag: \)2026\.10\.1$/\12026.10.2/' kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml
git diff -U0 | grep '^[-+] '
# dry-test result: 49c49 "tag: 2026.10.1" -> "tag: 2026.10.2" and 74c74 the same (two lines each side)
# commit with: git commit --only kubernetes/apps/home-automation/home-assistant/app/helmrelease.yaml -m '...'; then
# git log -1 --format=%s  (confirm the subject is YOURS before pushing)
```

3. Wait for the roll. Recreate: the old pod is deleted first, so HA is DOWN until the new pod passes readiness
   (pip installs for custom components make first boot slow; allow several minutes).

```bash
kubectl rollout status deploy/home-assistant -n home-automation --timeout=15m
kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].spec.containers[0].image}{" "}{.items[0].status.startTime}{" "}{.items[0].status.containerStatuses[0].imageID}{"\n"}'
# PASS: image ...:2026.10.2, startTime newer than the merge time, imageID digest DIFFERENT from digest-pre.txt.
# FAIL looks like: image 2026.10.1 (rollout status green-lights the OLD generation), same digest, or ImagePullBackOff.
```

4. A restart by construction. Do NOT restart again; use per-integration `reload` only if the operator is present (CLAUDE.md rule 4). Do nothing else in the pod until section 4 is done.

## 4) Verification

Settle floor: wait 10 minutes after the pod is Ready (certifi-patch initContainer, HACS pip reinstall, cloud re-auth,
BLE re-scan). An earlier read counts half-started integrations as `unavailable` and fails for the wrong reason.
Stop-safe: every gate below prints PASS or FAIL; one FAIL moves to section 5, it never retries silently.

```bash
S=/private/tmp/ha-pre-2026.10.2
POD_START=$(kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].status.startTime}'); echo "$POD_START"
```

### 4.1 Version, digest, API and core config check

```bash
kubectl exec deploy/home-assistant -c app -n home-automation -- cat /config/.HA_VERSION ; echo
kubectl get pod -l app.kubernetes.io/name=home-assistant -n home-automation -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}{"\n"}'
cd /Users/mu/code/hactl && mise exec -- python3 - <<'PY'
import sys; sys.path.insert(0,'.')
from hactl.core import load_config, make_api_request
u,t=load_config()
c=make_api_request(u+'/api/config',t)
assert c['version']=='2026.10.2', "FAIL: API reports %s (old generation or wrong target)" % c['version']
assert c['state']=='RUNNING', "FAIL: core state %s" % c['state']
r=make_api_request(u+'/api/config/core/check_config',t,method='POST',data={})
assert r.get('result')=='valid', "FAIL: check_config %s" % str(r)[:300]
print('PASS api version',c['version'],'check_config valid, components',len(c['components']))
PY
# PASS: .HA_VERSION 2026.10.2, restartCount 0, the python line prints PASS. FAIL looks like: "FAIL: API reports 2026.10.1", state NOT_RUNNING/STARTING (re-run once after 2 minutes),
# or check_config result "invalid" with the errors (a YAML/config-entry problem; an exit code alone proves nothing, the assertions read the content).
```

(`POST /api/config/core/check_config` is the endpoint HA's own "Check configuration" button uses; it returns
`{"result": "valid"|"invalid", "errors": ...}`. Confirm `make_api_request` takes `method=`/`data=` in this hactl
checkout before the run: it does as of 2026-10-22, signature `make_api_request(url, token, method='GET', ...)`; if
the keyword is named differently the script raises TypeError, which is a loud FAIL, not a pass.)

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
byd=collections.Counter(e.split('.',1)[1].split('_')[0] for e in new)
print('entities',st0['total_entities'],'->',st1['total_entities'],'| unavailable',len(pre),'->',len(post),'| NEW unavailable',len(new))
for e in new[:30]: print('  NEW',e)
N=15
assert st1['total_entities']>=st0['total_entities']-20, "FAIL: lost %d entities" % (st0['total_entities']-st1['total_entities'])
assert len(new)<=N, "FAIL: %d newly unavailable (limit %d)" % (len(new),N)
print('PASS')
PY
```

PASS prints `PASS` (N = 15 new unavailables tolerated: the baseline is churny BLE/Z2M sleepers; entities may not fall by
more than 20). FAIL prints `FAIL: ... newly unavailable` with the `NEW` list (look for a whole integration's prefix =
a setup failure) or `FAIL: lost N entities`. CONTROL FAILED = payload shape wrong; fix the read, do not pass.

### 4.3 Logs: new error signatures in the real pod log

```bash
kubectl logs deploy/home-assistant -c app -n home-automation --since-time="$POD_START" | sed $'s/\x1b\\[[0-9;]*m//g' > $S/halog-post.log
wc -l < $S/halog-post.log      # CONTROL: >= 1000
grep -ciE 'setup failed|migrat|traceback' $S/halog-post.log
sed $'s/\x1b\\[[0-9;]*m//g' $S/halog-pre.log | grep -E ' (ERROR|CRITICAL) ' | sed -E 's/^[0-9-]+ [0-9:.]+ //' | cut -c1-90 | sort -u > $S/sig-pre.txt
grep -E ' (ERROR|CRITICAL) ' $S/halog-post.log | sed -E 's/^[0-9-]+ [0-9:.]+ //' | cut -c1-90 | sort -u > $S/sig-post.txt
comm -13 $S/sig-pre.txt $S/sig-post.txt | head -30
# PASS: the grep count is 0 for 'setup failed' (migrat/traceback lines are reviewed, see 4.6) and comm prints no line that names a setup failure or a loaded
# integration. Chronic baseline noise (resmed_myair, dirigera_platform, frigate API, websocket) appears in both files and is removed by comm.
# FAIL looks like: "ERROR (MainThread) [homeassistant.setup] Setup failed for custom integration 'alexa_devices'..." in the comm output.
# Case-insensitive on purpose (mixed-case upstream output).
```

### 4.4 Key integrations and the voice pipeline

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
gone=[was[k]['domain'] for k in was if k not in now]
print('loaded',pre['summary']['by_state'].get('loaded'),'->',post['summary']['by_state'].get('loaded'),'| moved off loaded',len(bad),'| gone',len(gone))
for b in bad: print('  OFF-LOADED',b)
must={'mqtt','ollama','shelly','unifi','hacs','google','alexa_devices','custom_conversation','dirigera_platform','dwd_weather','teslafi','tesla_custom'}
ld={i['domain'] for i in post['integrations'] if i['state']=='loaded'}
assert must<=ld, "FAIL: not loaded: %s" % sorted(must-ld)
assert not bad and not gone, "FAIL: integration(s) moved off loaded or disappeared"
u,t=load_config()
sts={s['entity_id']:s for s in make_api_request(u+'/api/states',t)}
assert sts['binary_sensor.zigbee2mqtt_bridge_connection_state']['state']=='on', "FAIL: Zigbee2MQTT bridge not online"
assert sts['sensor.zigbee2mqtt_bridge_version']['state']=='2.14.2', "FAIL: z2m bridge version sensor not republished"
print('PASS integrations + z2m bridge online')
PY
```

PASS prints `PASS integrations + z2m bridge online`. FAIL names the domain/state (`setup_retry` for cloud sessions is
normal for ~2 minutes: re-run once; `migration_error` is forward-only, go to 5.2). The `unifi` and `google` entries
that matter are the loaded ones (the gateway-IPv6 `unifi` entry was `not_loaded` before and is ignored by the diff).
`must` is a domain set, so an `unifi` entry loaded in the baseline keeps the assertion satisfiable; if the domain were
fully absent it FAILs.

Voice pipeline conversation test (answers with the 26b; Ollama host serialises requests, expect up to ~90 s queued latency):

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
ps=json.load(urllib.request.urlopen('http://192.168.30.111:11434/api/ps', timeout=20))
names=[m['name'] for m in ps['models']]
assert 'gemma4:26b-mlx' in names, "FAIL: 26b not resident on the Ollama host: %s" % names
assert not any(n.startswith('gemma4:e2b') for n in names), "FAIL: an e2b model answered/resident: %s" % names
print('PASS voice + ollama', names)
PY
```

PASS: both agents return a non-error reply containing "pong" and `/api/ps` lists `gemma4:26b-mlx` (the entity name
"Voice Gemma e2b" is cosmetic; its subentry model is `gemma4:26b-mlx`, read from `core.config_entries` 2026-10-22). FAIL
looks like `response_type: error` ("Sorry, I had a problem talking to the Ollama server"), a timeout (urllib raises: loud),
or an `/api/ps` without the 26b. The conversation call sends no device commands (no exposed-entity intent in the sentence).
Other conversation entities (OpenClaw, OpenAI, Gemini) are NOT exercised: they cost money / hit external services.

Per-feed spot checks (read-only, can FAIL):

```bash
kubectl get deploy zigbee2mqtt mosquitto zero-export-controller teslamate -n home-automation -o jsonpath='{range .items[*]}{.metadata.name}={.status.readyReplicas} {end}'; echo
# PASS: all =1. These pods were not touched; this proves HA's restart did not take a feed down.
cd /Users/mu/code/hactl && mise exec -- python3 - <<'PY'
import sys; sys.path.insert(0,'.')
from hactl.core import load_config, make_api_request
import datetime
u,t=load_config(); s=make_api_request(u+'/api/states',t)
cal=[x for x in s if x['entity_id'].startswith('calendar.')]
assert len(cal)>=7 and not [x for x in cal if x['state'] in ('unavailable',)], "FAIL: calendar entities missing/unavailable: %s" % [x['entity_id'] for x in cal if x['state']=='unavailable']
sol=[x for x in s if x['entity_id'].startswith('sensor.solar_') and x['state'] not in ('unavailable','unknown')]
assert len(sol)>=4, "FAIL: only %d solar_* sensors have values (baseline 7 exist)" % len(sol)
print('PASS calendars',len(cal),'solar sensors with value',len(sol))
PY
```

The calendar entities cover Nextcloud/CalDAV and Google (the Google config entry is also asserted loaded above); the
solar helpers are the zero-export-controller feed. Mealie sync is untouched by this patch; run the SOP check only if
the operator is present (`kubectl create job ha-sync-check -n office --from=cronjob/mealie-shopping-sync`, cronjob exists).

### 4.5 Automations, repairs, doctor

```bash
cd /Users/mu/code/hactl
mise exec -- hactl doctor --format json > $S/doctor-post.json
mise exec -- hactl get automations > $S/auto-post.txt ; wc -l $S/auto-post.txt      # CONTROL: non-empty
python3 - <<PY
import json
a=json.load(open('$S/doctor-pre.json')); b=json.load(open('$S/doctor-post.json'))
print(json.dumps(b.get('summary',b))[:500]); print('pre ',json.dumps(a.get('summary',a))[:500])
PY
```

PASS: `post` shows no failed check that `pre` did not also fail, and the automation list is non-empty (baseline 69
automations). FAIL: a configuration-check failure (an invalid YAML load turns automations `unavailable`) or an
automation count well below baseline. Cross-check with `get states` domain counts: `automation` must be within 2 of the pre count.

### 4.6 Forward-only damage check (decides revert vs restore)

```bash
kubectl exec deploy/home-assistant -c app -n home-automation -- tar czf - -C /config .storage .HA_VERSION > $S/storage-post.tgz
cat > $S/gate46.py <<'PY'
import json, sys, tarfile, collections
D=sys.argv[1]
def vers(tgz):
    ent=json.load(tarfile.open(tgz).extractfile('.storage/core.config_entries'))['data']['entries']
    assert len(ent)>150, "CONTROL FAILED: config_entries did not load"
    m=collections.defaultdict(set)
    for e in ent: m[e['domain']].add((e['version'],e.get('minor_version')))
    return {k:sorted(v) for k,v in m.items()}
pm,qm=vers(D+'/storage-pre.tgz'),vers(D+'/storage-post.tgz')
moved={k:(pm.get(k),qm.get(k)) for k in set(pm)|set(qm) if pm.get(k)!=qm.get(k)}
for k,(a,b) in sorted(moved.items()): print('  MIGRATED',k,a,'->',b)
assert not moved, "FAIL: a config-entry version moved = forward-only migration ran -> image revert is no longer clean, use 5.2"
print('PASS no config-entry migration')
PY
python3 $S/gate46.py $S
```

PASS = `PASS no config-entry migration`: an image revert (5.1) is still clean. FAIL (`MIGRATED <domain> (1, 3) -> (1, 4)`)
does not mean the upgrade failed; it means the revert path becomes restore-class (5.2). Pre/post both come from this plan's
own tarballs (2.3 and above). A short or missing file trips the CONTROL assertion.

### 4.7 Prometheus (secondary; skip if kube-prometheus-stack is rolling)

`kube_pod_container_status_restarts_total{namespace="home-automation",pod=~"home-assistant-.*"}` is 0 for the new pod.
CONTROL: the same query for `pod=~"mosquitto-.*"` returns a series (proves the metric is scraped); an empty result on
the HA query alone is meaningless.

### 4.8 Security motivation (advisory, not a gate)

After the next sweep, `runbooks/policy-cli.py finding list --grep home-assistant` should no longer show F-4a4ebf8a
open for `:2026.10.1`; a finding re-keyed to `:2026.10.2` with the same fixable CVEs means upstream did not ship the fix in
this patch (no further action available for a third-party image: we bump, never rebuild).

## 5) Rollback

Decide with 4.6. HA is `hostNetwork` on k8s-nuc14-01 with a Recreate Deployment and an RWO Longhorn PVC: a revert is
another full restart, and a data restore needs the Longhorn backup or the tarball, not git alone.

### 5.1 Image revert (clean ONLY if 4.6 passed and no entity loss)

```bash
git revert --no-edit <merge-sha-of-PR-375>   # restores both tag lines to 2026.10.1
git push
kubectl rollout status deploy/home-assistant -n home-automation --timeout=15m
kubectl exec deploy/home-assistant -c app -n home-automation -- cat /config/.HA_VERSION
# PASS: image 2026.10.1 live (kubectl get deploy ... jsonpath image) AND 4.1, 4.2 and 4.4 re-run green against the saved baseline in $S.
# HA logs a "downgrade" warning on seeing .HA_VERSION 2026.10.2: expected, not a failure by itself.
```

### 5.2 Restore (a config entry migrated, or any custom integration is `migration_error`)

1. Revert the image as in 5.1 and let the pod come up (it may report degraded integrations).
2. Ask cberg-agent to stop the pod so files are quiescent: `flux suspend hr home-assistant -n home-automation` then `kubectl scale deploy/home-assistant --replicas=0 -n home-automation`.
3. Restore `.storage` from `$S/storage-pre.tgz` (taken in 2.3 BEFORE the roll) into the `home-assistant-config` PVC via a one-off job
   that mounts the PVC (static PV, RWO: the HA pod must be at 0 replicas or the mount will not attach): `tar xzf storage-pre.tgz -C /config`.
   The recorder DB is not migrated (schema 53 both sides), so no DB restore is needed.
4. Last resort: Longhorn restore of `home-assistant-config` from the newest Completed Backup CR (2.2; docs/sops/longhorn.md; restore under the SAME speaking
   name, `volumeHandle` is immutable). Loses up to the time since the 03:00 backup.
5. `flux resume hr home-assistant -n home-automation`; verify 4.1-4.5 against the baseline.

Cost of restore: automations triggered, helper values and recorder history written since the backup are lost.

## 6) Interference notes

- Whole-house impact during the Recreate gap (~5-10 min, longer on a cold pip cache): every automation and script is off;
  zigbee/matter/ESPHome hubs stay up and re-sync. Window is unattended-capable but do not combine with a node reboot.
- Do not share the slot with `talos-linux-*` (node drain strands a hostNetwork pod), `longhorn-1.13.0` (single-attach
  PVC), `cilium-1.20.3` or `spegel-0.8.0` (datapath / image pull), or a Flux controller roll.
- `kube-prometheus-stack-92.11.0` must not roll the same night (4.7 reads Prometheus); `edot-collector-0.163.1` drops
  Elasticsearch log shipping while it rolls (the 4.3 evidence here uses `kubectl logs`, unaffected).
- The Ollama host (192.168.30.111) is shared infrastructure: the 4.4 conversation test makes two short requests; do not run it
  while another heavy Ollama job (e.g. a nightly briefing) is queued, because requests serialise (NUM_PARALLEL=1).
- Step 0 of the window (safe-update apply) may also touch home-automation images: it runs first; re-take 2.3 baselines AFTER it, never before.
