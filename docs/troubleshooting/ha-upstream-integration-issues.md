# Home Assistant — Known Upstream Integration Issues

Tracks integration errors that are **not cluster issues** — either upstream service problems or known integration bugs. These noise up the health check's error count but require no local action beyond awareness.

**Last reviewed:** 2026-04-17 (HA Core 2026.4.2)

---

## Tesla Wall Connector — Intermittent timeouts (ACCEPTED)

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

## Miele — pymiele SSE TransferEncodingError (UPSTREAM BUG, NO FIX YET)

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

## Tibber Realtime — 502 Bad Gateway (UPSTREAM BACKEND)

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

## Health check impact

These three upstream issues accounted for **~58 of the 74 HA errors** flagged as MAJOR on 2026-04-17:
- Tesla Wall Connector: 24
- Miele SSE: 19
- Tibber realtime: 15

The `HA_FALSE_POSITIVES` allowlist in `runbooks/health-check.sh:132` is **intentionally not** expanded to cover these — we want visibility when the error rate spikes, even if the root cause is upstream. The health check threshold (>50 major = MAJOR issue) is the right tripwire.

If upstream issues cause false MAJOR alerts too often, revisit by either:
- Raising the threshold
- Splitting upstream-dependent errors from local-infra errors (future work)
