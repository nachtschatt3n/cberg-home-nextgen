# SOP: Home Assistant post-update / post-restart checklist

> Description: Mandatory checks after ANY Home Assistant restart, image update,
> or Talos rolling reboot that recreates the HA pod. Institutionalizes the
> 2026-08-02 certifi/EBUSY incident, the recurring HmIP cloud-session wedge, and
> the custom-code regression surface that core version bumps can silently break.
> Version: `2026.08.02`
> Last Updated: `2026-08-02`
> Owner: `sre`

---

## 1) Description

Home Assistant re-installs HACS custom-integration requirements with pip/uv on
**every boot**. That makes each restart — planned image bump, Talos rolling
reboot, or crash — a fresh chance for boot-time breakage that a green pod status
does NOT catch (`1/1 Running` with four integrations failed is a real, observed
state). This SOP is the checklist to run after any event that recreates the HA
pod, plus the extra regression list for **core version bumps**.

- Scope: `home-automation/home-assistant`
- Prerequisites: repo `/Users/mu/code/cberg-home-nextgen`, `mise` tooling; an HA
  long-lived token for API checks (env-provided, never committed)
- Related SOPs: `docs/sops/home-assistant-certifi-ca-trust.md` (TLS/certifi
  pattern), `docs/sops/zigbee2mqtt.md` (Z2M device triage)

---

## 2) Overview

| Check | Canary | Failure mode it catches |
|-------|--------|-------------------------|
| 1. Boot requirements install | HACS integrations `alexa_devices`, `dirigera_platform`, `dwd_weather`, `custom_conversation` | pip/uv failures at boot (e.g. certifi EBUSY 2026-08-02) — all four fail setup on every boot |
| 2. certifi/site-packages rule | init `certifi-patch` log + no site-packages mounts | Mount over `site-packages` blocking runtime pip upgrades |
| 3. HmIP cloud session | `homematicip_cloud` entities available ≤ 15 min post-boot | HA restart wedges the eQ-3 cloud session (HA core bug #155194) |
| 4. Custom-code regression (version bumps) | custom_sentences, packages, scripts, prompts, automations, dashboards | Core schema/behaviour changes silently disabling local customizations |
| 5. Z2M `unavailable` triage | Z2M logs + database `lastSeen` | Misreading a sleeping battery device as dead (July 2026 valve lesson) |

---

## 3) Blueprints

N/A — this SOP is a checklist; manifests live in
`kubernetes/apps/home-automation/home-assistant/app/` and the TLS/certifi
pattern is specified in `docs/sops/home-assistant-certifi-ca-trust.md`.

---

## 4) Operational Instructions

Run top-to-bottom after ANY HA pod recreation. Steps 4 applies only to core
version bumps.

### Step 1 — boot requirements install (ALWAYS)

HACS custom integrations pip-install their requirements at boot; they are the
canary for boot-time package breakage.

```bash
POD=$(mise exec -- kubectl get pods -n home-automation -l app.kubernetes.io/name=home-assistant \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
# No output = healthy:
mise exec -- kubectl logs -n home-automation "$POD" -c app \
  | grep -E "Unable to install package|Resource busy|os error 16|Setup failed for custom integration"
```

Then confirm the four canary config entries reach `loaded` (via
`/api/config/config_entries/entry` with an HA token, or the ha-agent):
`alexa_devices`, `dirigera_platform`, `dwd_weather`, `custom_conversation`.
Also check `/api/error_log` for anything new.

### Step 2 — certifi / site-packages hard rule (ALWAYS)

**Never subPath-mount anything over files in `site-packages`.** pip/uv replaces
files by atomic rename; a rename over a mounted file fails with EBUSY
(os error 16) and cascades into requirements failures for every integration
whose chain pulls the mounted package (this is exactly what certifi `2026.7.22`
triggered on 2026-08-02).

The patched CA bundle (base certifi + **DigiCert Global Root CA** — the legacy
2006 root that new certifi/Alpine dropped but which `api.wyzecam.com`'s chain
still terminates at, so the `wyzeapi` integration needs it) must stay at the
**neutral path** `/patched-ca/cacert.pem`, wired via `SSL_CERT_FILE` +
`REQUESTS_CA_BUNDLE` env plus the `certifi.where()` shim. Full pattern and
rationale: `docs/sops/home-assistant-certifi-ca-trust.md`.

```bash
mise exec -- kubectl logs -n home-automation "$POD" -c certifi-patch   # expect "... redirected OK"
mise exec -- kubectl exec -n home-automation "$POD" -c app -- sh -c \
  'mount | grep -c site-packages'                                     # expect 0
```

### Step 3 — HmIP cloud session (ALWAYS)

HA restarts tend to wedge the HomematicIP (eQ-3) cloud session — HA core bug
#155194. The self-heal automation `automation.hmip_cloud_session_self_heal`
handles it by reloading config entry `01JRZY6QRWHRW34RP7ZPASGKTS`; do not fix
by hand first.

Within ~15 min of boot, verify (template API or ha-agent):

- `integration_entities('homematicip_cloud')` → 0 unavailable
- `input_boolean.hmip_sustained_outage` is `off`
- If entities are still unavailable after 15 min AND the self-heal
  `last_triggered` is stale, only then investigate (entry reload is the fix; the
  automation should have done it).

### Step 4 — custom-code regression list (CORE VERSION BUMPS)

Spot-check after any `ghcr.io/home-assistant/home-assistant` version bump
(minor or major — patch bumps at your discretion):

| Area | Location | What breaks |
|------|----------|-------------|
| Custom sentences | `/config/custom_sentences/{en,de}/` | HassGetState intent overrides + response templates vs. new core intent schemas |
| Packages | `/config/packages/vacation_ai.yaml` (shell_commands), `/config/packages/central_water_daily.yaml` (utility_meter) | Schema validation changes drop the whole package silently |
| AI vision scripts | `/config/scripts/ai_person_check*.py` (Ollama gemma vision) | Python/API drift in the container runtime |
| custom_conversation options | Config-entry options — `instructions_prompt` carries a household-specific fact | Re-setup/migration resets options; the prompt must survive |
| Runtime automations | Vacation stack incl. the hmip self-heal pair (`hmip_cloud_session_self_heal` + `hmip_sustained_outage_alert`), kids AI-gate in `vacation_motion_ai_assessment` | Trigger/condition schema changes disable automations |
| Dashboards | `/vacation-mode` | Card/resource deprecations |

Deep regression is the **ha-agent**'s job — dispatch it after any core bump;
this table is the minimum spot-check list.

### Step 5 — Z2M `unavailable` triage rule (WHEN APPLICABLE)

HA `unavailable` on a Zigbee2MQTT **battery** device does NOT mean the device is
dead — sleepy end devices check in rarely. Before concluding hardware failure:
check Z2M `/data/log/` and the Z2M `database.db` `lastSeen` for the device
(July 2026 valve lesson). Escalate to `docs/sops/zigbee2mqtt.md` /
zigbee-agent only if `lastSeen` is genuinely stale.

---

## 5) Examples

### Example A: routine Talos rolling reboot (no HA version change)

```bash
# Steps 1-3 only; total ~5 min
POD=$(mise exec -- kubectl get pods -n home-automation -l app.kubernetes.io/name=home-assistant \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl logs -n home-automation "$POD" -c app | grep -cE "Unable to install|Setup failed" # 0
mise exec -- kubectl logs -n home-automation "$POD" -c certifi-patch                                   # redirected OK
# + config entries loaded, HmIP available, sustained-outage boolean off (Step 1/3)
```

### Example B: HA core version bump (e.g. 2026.7 → 2026.8)

Steps 1–3, then Step 4's full table, then dispatch the ha-agent for deep
custom-code regression. Only mark the bump verified after both report clean.

---

## 6) Verification Tests

### Test 1: no boot-time install failures

```bash
mise exec -- kubectl logs -n home-automation "$POD" -c app \
  | grep -cE "Unable to install package|Setup failed for custom integration"
```

Expected: `0`. If not, capture `/api/error_log`, see Troubleshooting.

### Test 2: canary config entries loaded

Query `/api/config/config_entries/entry`; `alexa_devices`,
`dirigera_platform`, `dwd_weather`, `custom_conversation` (and `wyzeapi`,
`homematicip_cloud`) all `state=loaded`.

### Test 3: HmIP availability

Template API: `integration_entities('homematicip_cloud') | select('is_state',
'unavailable') | list | length` → `0` within 15 min of boot;
`input_boolean.hmip_sustained_outage` → `off`.

---

## 7) Troubleshooting

| Symptom | Likely Cause | First Fix |
|---------|--------------|-----------|
| `Unable to install package …: Resource busy (os error 16)` | Something mounted over site-packages again | `docs/sops/home-assistant-certifi-ca-trust.md` HARD RULE — neutral-path pattern |
| Canary entries `setup_retry`/`setup_error` but no install error | Integration-specific breakage (API change, credentials) | Check `/api/error_log` for that domain; treat per-integration |
| HmIP unavailable > 15 min, self-heal not triggered | Automation disabled/broken by an update | Verify `automation.hmip_cloud_session_self_heal` is `on`; check its trace; reload entry `01JRZY6QRWHRW34RP7ZPASGKTS` manually only as last resort |
| Custom sentences stop matching after bump | Core intent schema change | Compare against release notes; adjust `/config/custom_sentences/` |
| Z2M battery device `unavailable` | Sleepy device, not dead | Step 5 triage BEFORE replacing hardware |

---

## 8) Diagnose Examples

### Diagnose Example 1: which integration killed which package install

```bash
mise exec -- kubectl logs -n home-automation "$POD" -c app \
  | grep -B1 -A2 "Unable to install package" | head -40
# The "Setup failed for custom integration 'X': Requirements for X not found"
# line names the victim; the "Caused by:" line names the real blocker.
```

### Diagnose Example 2: HmIP wedge vs. real outage

```bash
# Entry state + self-heal trigger time tell the story:
# loaded + entities unavailable + last_triggered recent  -> self-heal ran, wait
# loaded + entities unavailable + last_triggered stale   -> self-heal broken
# setup_retry                                            -> eQ-3 cloud outage (check upstream status)
```

---

## 9) Health Check

```bash
mise exec -- kubectl get pods -n home-automation -l app.kubernetes.io/name=home-assistant
mise exec -- flux get helmreleases -n home-automation home-assistant
# + /api/config returns state RUNNING (with token)
```

---

## 10) Security Check

```bash
# Post-update checks use a long-lived HA token from env (.env / SOPS) — never
# commit it, never echo it. Nothing in this checklist writes to the cluster.
grep -rE "Bearer [A-Za-z0-9._-]{20,}" docs/sops/home-assistant-updates.md && echo "LEAK" || echo "OK: no tokens in SOP"
```

---

## 11) Rollback Plan

This SOP is read-only verification. For a failed HA image bump:

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert <bump-sha>
git push   # Flux rolls HA back; then re-run Steps 1-3 of this SOP
```

---

## 12) References

- `docs/sops/home-assistant-certifi-ca-trust.md` — TLS/certifi neutral-path pattern + EBUSY incident
- `docs/sops/zigbee2mqtt.md` — Z2M device triage
- `kubernetes/apps/home-automation/home-assistant/app/` — manifests
- HA core bug #155194 — HmIP cloud session wedge on restart

---

## Version History

- `2026.08.02`: Initial SOP — born from the certifi 2026.7.22 EBUSY incident
  (four HACS integrations failing setup every boot), the HmIP restart wedge
  pattern, and the vacation-stack custom-code regression surface.
