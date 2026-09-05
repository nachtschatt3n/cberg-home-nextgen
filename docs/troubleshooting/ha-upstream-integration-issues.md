# Home Assistant — Known Integration Issues

Tracks HA integration errors that are either **upstream service problems** (no local action possible) or **known issues requiring user action** (integration config change, token refresh, etc.). These all noise up the health check's error count.

**Last reviewed:** 2026-09-05 (HA Core 2026.9.0)

> **Quick summary**: sections below marked *(UPSTREAM — ACCEPTED)* need no action. Sections marked *(USER ACTION NEEDED)* require a manual fix.
>
> **2026-09-05 re-review (closes sweep finding F-d9bbd8ff):** re-checked all 5 tracked sections against the live `/api/error_log` on HA Core 2026.9.0 (up from 2026.4.2 in April — 5 releases). **4 of 5 have cleared** and were removed: Miele SSE, ha_hatch MQTT, Tibber Realtime 502s, and the Samsung FamilyHub OAuth 401s. Only the **Tesla Wall Connector WiFi-edge timeout** is still live. Full verification detail is under that section below.

---

## Tesla Wall Connector — Intermittent timeouts *(UPSTREAM — ACCEPTED)*

**Symptom** (HA logs):
```
ERROR (MainThread) [homeassistant.components.tesla_wall_connector.coordinator]
  Error fetching tesla-wallconnector data: Could not fetch data from
  Tesla WallConnector at 192.168.32.146: Timeout
```

**Root cause:** Device is at the **edge of WiFi coverage**. When RSSI drops, polling requests time out before backoff retries succeed. Device remains functional for charging (ESS over powerline/local network), just loses HA telemetry briefly.

**Verification (2026-09-05, HA Core 2026.9.0):** Still live, unchanged symptom/text from the April finding.
- `/api/error_log` since the last HA core restart (2026-09-04 23:55 → 2026-09-05 19:11, ~19.3h of runtime) shows **29 `tesla_wall_connector.coordinator` timeout errors**, clustered between 00:09 and 12:49 — same intermittent-cluster pattern as April, not continuous failure.
- The Wall Connector's own entities are **not** in HA's "truly unavailable" list — confirms the outage is telemetry-poll-only, not a lost connection to the device.
- Integration config entry state: `loaded` (no `setup_error`).
- **Note for the operator:** 29 errors in a 19.3h window extrapolates close to or above the doc's own "~30/day sustained" revisit trigger from April (this was ~24/day back then). Worth a look at RSSI next time you're near the garage, even though nothing here requires action today.

**Smarthome impact:** Home Assistant dashboard/history telemetry for the Wall Connector (charging session state, live power draw) shows intermittent gaps during these clusters. Actual EV charging is unaffected — the connector operates on its own local/powerline control path, not through HA. Any automation keyed off Wall Connector sensors (state-of-charge notifications, "charging started/stopped" triggers) can see a stale or `unavailable` reading during a gap window and may fire late or not at all until the next successful poll.

**Decision:** **Accepted.** No local action — WiFi reception improvement would require relocating the AP. Impact: occasional gaps in HA dashboard telemetry, not charging functionality.

**When to revisit:** If error rate climbs above ~30/day sustained (indicates RSSI further degraded or AP issue), consider:
- Move U7 Pro / Hallway-AP-U6 Pro closer to garage
- Add dedicated AP in garage
- Switch to ethernet via power-line adapter

---

## Historical HA long-lived token leak *(REVOKED — NOT AN ONGOING ISSUE)*

A HA long-lived access token was committed in plaintext in a now-deleted script `add_shelly_devices_to_hass.sh` (commit `2b0665fd`, 2025-04-17). The repo is public.

**Verification (2026-04-18):** HA → Profile → Security showed only 2 long-lived tokens (`ai-harness`, `ai-harness-test`), both created that week. The leaked token was **not present** — either revoked or never re-created after the HA rebuild.

**Re-check (2026-09-05):** searched the current `/api/error_log` for any reference to the leaked token or the deleted script name — zero hits, consistent with the token being dead/unused. (The HA token list itself isn't exposed via `hactl`/REST — this is a log-based sanity check, not a re-enumeration of active tokens. No new evidence contradicts the April finding.) No action required.

Security scanner `runbooks/security-check.py` has the token's `iss` claim in `ACCEPTED_CRED_PATTERNS` so the pattern doesn't flag on every scan.

---

## Health check impact

**2026-09-05:** Of the original 3 upstream sources tracked here (Tesla Wall Connector, Miele SSE, Tibber Realtime), only **Tesla Wall Connector remains live** — it accounted for 29 of the 71 strict `ERROR`-level lines in the current retained log (Miele and Tibber contributed 0). The other two cleared upstream sometime in the 5 HA Core releases since April and their sections were removed above.

The current top error sources in `/api/error_log` are `tesla_wall_connector.coordinator` (29), `custom_components.frigate.api` (13), and `custom_components.teslafi` (8) — the last two are **not** covered by this doc (they weren't part of the original 2026-04-18 tracking and haven't been root-caused here). If they persist, they need their own investigation/doc rather than being folded into this one silently.

The `HA_FALSE_POSITIVES` allowlist in `runbooks/health-check.sh:132` is **intentionally not** expanded to cover the Tesla Wall Connector errors — we want visibility when the error rate spikes, even if the root cause is upstream. The health check threshold (>50 major = MAJOR issue) is the right tripwire.

If upstream issues cause false MAJOR alerts too often, revisit by either:
- Raising the threshold
- Splitting upstream-dependent errors from local-infra errors (future work)
