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

## Samsung FamilyHub Fridge — SmartThings auth failure *(FORK DEPLOYED, PR OPEN — USER ACTION: switch to OAuth mode)*

**Status 2026-04-18:** forked the community integration, implemented OAuth-via-HA-core-smartthings auto-refresh, deployed to the live HA pod, submitted PR upstream.

- Fork: https://github.com/nachtschatt3n/smartthings_fridge_camera (branch `feat/oauth-via-ha-core-smartthings`)
- Upstream PR: https://github.com/ibielopolskyi/smartthings_fridge_camera/pull/23
- Live HA version: `0.1.0` (synced from fork, 2026-04-18)
- Config entry: migrated v1→v2 automatically, currently `auth_mode: pat` (will keep erroring until the user switches to OAuth via UI)

**Next step for you:** HA UI → **Settings → Devices & Services → Samsung Fridge Camera → Reconfigure → choose "Reuse HA core SmartThings OAuth (recommended)"**. After saving, the integration will reuse the HA core SmartThings OAuth2 credentials (with auto-refresh) and no further token rotation is needed.



**Symptom** (HA logs, at startup or when polling tries to resume):
```
ERROR [custom_components.samsung_familyhub_fridge.api] SmartThings authentication failed
  (HTTP 401). Token may have expired — SmartThings personal access tokens expire after 24 hours
```

### Root cause — verified

**Samsung changed SmartThings PAT policy on 2024-12-30:** new PATs expire after **24 hours**; older PATs created before that date may retain expiration up to 50 years. This is an intentional Samsung policy, not an integration bug.

**Integration**: `samsung_familyhub_fridge` v0.0.1 by [@ibielopolskyi](https://github.com/ibielopolskyi/smartthings_fridge_camera) (community HACS; not HA core).

Investigation of the integration source (2026-04-18) shows:

- `auth.py` defines `SmartThingsOAuth` (PKCE flow, refreshable) and `SamsungAccountAuth` (headless email/password) classes
- **But** `config_flow.py` only accepts a plain `token` string — OAuth/Samsung Account flows are helpers not wired into the UI
- Latest (PR #17, merged 2026-04-10) adds 401/403 detection → triggers HA's built-in re-auth flow (UI prompt), but still does **not** auto-refresh tokens

So even on the newest version, the user has to manually re-enter a token whenever it expires.

### Options (in order of least-to-most work)

1. **Short-term patch** (what most users do): re-enter a PAT every 24h via HA reauth UI. Tedious but works.
2. **Use a grandfathered PAT**: if you have one created before 2024-12-30 at https://account.smartthings.com/tokens, it still honors its original expiration (up to 50 years). Check `smartthings.com/tokens` — tokens created before the policy change list their expiration date.
3. **Upgrade the custom integration to latest** (0.0.1 → main branch via HACS re-download): gets the 401 detection + re-auth UI prompt. Still manual refresh, but you get notified.
4. **Generate OAuth access token externally**, paste into HA. Requires:
   - Run `smartthings apps:create` (SmartThings CLI) → get `client_id` + `client_secret`
   - Use the integration's `SmartThingsOAuth` helper (or your own script) to do PKCE flow → get `access_token` + `refresh_token`
   - Paste `access_token` into HA. Still expires in 24h (OAuth access tokens are also short-lived); would need a cron job calling `/oauth/token` with refresh_token and updating HA config entry.
5. **Switch to HA core SmartThings integration**: OAuth with automatic refresh built-in (supported officially). **Loses**: fridge camera feed, inventory, FamilyHub-specific door sensors — these aren't in HA core's SmartThings integration.
6. **Fork and contribute auto-refresh upstream**: `auth.py` has `refresh(refresh_token)` already implemented; wire it into `DataCoordinator._async_update_data()` in `api.py` to refresh on 401 and call `update_token(...)` on the hub. Merge via PR to the repo.

### Recommendation

For now: **option 3** (upgrade to latest version) is the lowest effort — gets you notified when expiry hits instead of silent data staleness. Combine with **option 2** (hunt for a grandfathered PAT) if any of your previously-created PATs pre-date 2024-12-30.

For durable fix: **option 6** is the right investment if the fridge camera/inventory features matter — `auth.py` already has the building blocks. Otherwise option 5 accepts feature loss for reliability.

**When to revisit:** whenever the 401 returns. Sources:
- [Samsung PAT policy change discussion (SmartThings Community)](https://community.smartthings.com/t/old-personal-access-token-stopped-working-after-the-expiration-change/293450)
- [Integration repo](https://github.com/ibielopolskyi/smartthings_fridge_camera)
- [PR #17 — auth refresh & OAuth flow](https://github.com/ibielopolskyi/smartthings_fridge_camera/pull/17)

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
