# Home Assistant — Known Integration Issues

Tracks HA integration errors that are either **upstream service problems** (no local action possible) or **known issues requiring user action** (integration config change, token refresh, etc.). These all noise up the health check's error count.

**Last reviewed:** 2026-04-18 (HA Core 2026.4.2)

> **Quick summary**: sections below marked *(UPSTREAM — ACCEPTED)* need no action. Sections marked *(USER ACTION NEEDED)* require a manual fix.

---

## Tesla Wall Connector — Intermittent timeouts *(UPSTREAM — ACCEPTED)*

**Symptom** (HA logs):
```
ERROR (MainThread) [backoff] Giving up async_request(...) after 3 tries
  (tesla_wall_connector.exceptions.WallConnectorConnectionTimeoutError:
   Timeout while connecting to Wall Connector at 192.168.32.146)
ERROR (MainThread) [homeassistant.components.tesla_wall_connector.coordinator]
  Error fetching tesla-wallconnector data: ... Timeout
```

**Root cause:** Device is at the **edge of WiFi coverage**. When RSSI drops, polling requests time out before backoff retries succeed. Device remains functional for charging (ESS over powerline/local network), just loses HA telemetry briefly.

**Verification** (2026-04-17):
- Device IP `192.168.32.146` reachable via ping (24-97ms RTT, no loss)
- HTTP API responds 200 on `/api/1/vitals`
- Error clusters (~2h windows) — not continuous failure

**Decision:** **Accepted.** No local action — WiFi reception improvement would require relocating the AP. Impact: occasional gaps in HA dashboard telemetry, not charging functionality.

**When to revisit:** If error rate climbs above ~30/day sustained (indicates RSSI further degraded or AP issue), consider:
- Move U7 Pro / Hallway-AP-U6 Pro closer to garage
- Add dedicated AP in garage
- Switch to ethernet via power-line adapter

---

## Miele — pymiele SSE TransferEncodingError *(UPSTREAM BUG, NO FIX YET — ACCEPTED)*

**Symptom** (HA logs):
```
ERROR (MainThread) [pymiele.pymiele] Listen_event: Response payload is not completed:
  <TransferEncodingError: 400, message='Not enough data to satisfy transfer length header.'>
ERROR (MainThread) [homeassistant.components.miele.coordinator] Timeout fetching miele data
```

**Root cause:** Miele Cloud SSE (Server-Sent Events) endpoint closes connections abruptly without flushing the transfer-encoding frame. `pymiele` reports this as an error on every close, but the library does reconnect. Coordinator timeout errors are secondary — they fire when pymiele is mid-reconnect.

**Current state:**
- Deployed: **pymiele 0.6.1** (latest on PyPI as of 2026-04-17)
- HA Core: 2026.4.2
- No fix available upstream

**Decision:** **Accept until pymiele releases a fix.** Devices continue to work — state updates arrive eventually via polling fallback.

**When to revisit:**
- **Next HA Core release** — check if `pymiele` bumped beyond `0.6.1`
- `pip index versions pymiele` or check `https://pypi.org/pypi/pymiele/json`
- Also check https://github.com/astrandb/pymiele/issues for active PRs
- If fixed: upgrade triggers via HA Core bump (Renovate / manual image rollout)

---

## Tibber Realtime — 502 Bad Gateway *(UPSTREAM BACKEND — ACCEPTED)*

**Symptom** (HA logs):
```
ERROR (MainThread) [tibber.home] Error in rt_subscribe
  gql.transport.exceptions.TransportQueryError:
  {'message': 'http://iot-api.prod.tibber.cloud/homes/.../active-iot-device
  Response code 502 (Bad Gateway)', ...}
ERROR (MainThread) [tibber.realtime] Watchdog: Connection is down
```

**Root cause:** **Tibber backend problem, not an integration bug.**
- `iot-api.prod.tibber.cloud` returns HTTP 502 (Bad Gateway) — this is a server-side error from Tibber's IoT API.
- The `pytibber` library (0.37.0 deployed, 0.37.1 latest on PyPI) correctly surfaces the upstream error.
- Watchdog fires when the realtime websocket subscription has been down → reconnect loops.

**Verification this is backend, not integration:**
- 502 status originates from Tibber's reverse proxy, not from our client
- Errors correlate with Tibber status page incidents when checked historically
- `pytibber` reconnects automatically once upstream recovers — no manual intervention needed

**Decision:** **Accept — no local fix possible.** Tibber's Pulse Bridge (192.168.32.229) continues pushing data via MQTT Home assistant integration as the primary path; realtime API is a secondary source.

**When to revisit:**
- If errors persist >24h without recovery → check https://status.tibber.com/
- If pytibber bumps to a major version (0.38+) that changes API contract
- If MQTT Pulse feed also drops (then investigate local — MQTT broker, Pulse bridge power)

---

## Samsung FamilyHub Fridge — SmartThings auth failure *(USER ACTION NEEDED)*

**Symptom** (HA logs, only at startup — no polling retry between restarts):
```
ERROR [custom_components.samsung_familyhub_fridge.api] SmartThings authentication failed
  (HTTP 401). Token may have expired — SmartThings personal access tokens expire after 24 hours
ERROR [custom_components.samsung_familyhub_fridge.api] Authentication failed while fetching
  File ID refresher data: SmartThings token expired or is invalid. Please re-authenticate
  with a new token.
```

**Root cause:** the `samsung_familyhub_fridge` custom integration (community-maintained, not HA core) uses a **SmartThings Personal Access Token (PAT)** for auth. Samsung's PATs expire after **24 hours** — the integration has no refresh flow, so every HA restart >24h after token generation fails auth and the integration runs with stale data.

**Why this can't be "accepted":** the integration isn't actually polling — fridge camera feed, inventory, and sensor data are all stale until the token is refreshed. Not a noise issue; it's a real functional break.

**Fix:**
1. Generate a new PAT at https://account.smartthings.com/tokens (scope: `r:devices:*` + `r:locations:*`)
2. Home Assistant → **Settings → Devices & Services** → Samsung FamilyHub Fridge → **Reconfigure**
3. Paste the new PAT
4. Restart HA and verify no 401 errors in logs

**Longer term:** replace with the official SmartThings integration (HA core) which uses OAuth with automatic refresh — supports most SmartThings-paired Samsung appliances but may lack FamilyHub-specific features (camera feed). Or fork the custom integration to implement OAuth flow.

**When to revisit:** every PAT refresh cycle (manual — there is no notification). Consider setting a 21-day calendar reminder.

---

## Historical HA long-lived token leak *(REVOKED — NOT AN ONGOING ISSUE)*

A HA long-lived access token (`iss: bc0e1bf629c84ee288eb0a1cf3eb6609`) was committed in plaintext in a now-deleted script `add_shelly_devices_to_hass.sh` (commit `2b0665fd`, 2025-04-17). The repo is public.

**Verification (2026-04-18):** HA → Profile → Security shows only 2 long-lived tokens (`ai-harness`, `ai-harness-test`, both created last week). The leaked token is **not present** — either revoked or never re-created after the HA rebuild. No action required.

Security scanner `runbooks/security-check.py` has the token's iss claim in `ACCEPTED_CRED_PATTERNS` so the pattern doesn't flag on every scan.

---

## Health check impact

These three upstream issues accounted for **~58 of the 74 HA errors** flagged as MAJOR on 2026-04-17:
- Tesla Wall Connector: 24
- Miele SSE: 19
- Tibber realtime: 15

The `HA_FALSE_POSITIVES` allowlist in `runbooks/health-check.sh:132` is **intentionally not** expanded to cover these — we want visibility when the error rate spikes, even if the root cause is upstream. The health check threshold (>50 major = MAJOR issue) is the right tripwire.

If upstream issues cause false MAJOR alerts too often, revisit by either:
- Raising the threshold
- Splitting upstream-dependent errors from local-infra errors (future work)
