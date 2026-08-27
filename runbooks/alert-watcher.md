# Runbook: Claude push-alert watcher (Alertmanager + Kuma → one WebSocket)

> **Mode change 2026-08-17 — the watcher is now PERSISTENT.** The bridge runs as
> a launchd KeepAlive service (`com.cberg.alert-bridge`, plist in this dir;
> restarts on crash, starts on login) and the Alertmanager receiver is
> Flux-managed in `kubernetes/apps/monitoring/kube-prometheus-stack/app/`.
> `alert-watch-up.sh` / `alert-watch-down.sh` are no longer needed per-session —
> only the Monitor `ws` source (ws://127.0.0.1:8787/) is started per-session by
> the assistant. To retire the persistent mode: `launchctl bootout
> gui/$UID/com.cberg.alert-bridge`, remove the plist, delete the Flux manifest
> (same change), and revert to the ephemeral flow below.


A **session-scoped** watcher that pushes every cluster/Kuma alert to a Claude
Code `Monitor` `ws` source in real time — no polling, no missed flaps. Stand it up
when you want Claude actively watching alerts during a work session; tear it down
when done. Files live in `runbooks/alert-watcher/`.

## Why it exists / when to use
Polling Alertmanager (port-forward + `curl` every 30s) is fragile: it misses
short-lived/flapping alerts (e.g. `etcdDatabaseHighFragmentationRatio`) and fails
silently if the port-forward dies. Push fixes all of that — Alertmanager POSTs the
instant an alert fires or resolves.

## Architecture
```
cluster alerts ─┐
                ├─► Alertmanager ─► webhook_config ─► alert-bridge (Mac) ─► ONE WebSocket ─► Monitor `ws`
Uptime Kuma  ───┘   (push, 1s grp)   (HTTP POST)      :8788 → :8787         (JSON frames)    (Claude notifications)
   via KumaMonitorDown rule
```
- **`alert-bridge.py`** (Mac, `websockets` + stdlib HTTP; runs from the repo
  `.venv`): receives Alertmanager webhooks on `:8788`, relays each alert as a WS
  frame on `:8787`. Frames carry `{source,status,severity,alertname,namespace,
  pod,instance,summary}` for both `firing` and `resolved`.
- **`claude-watch-webhook.yaml`** — the `AlertmanagerConfig` that makes
  Alertmanager push every alert to the bridge, in parallel with the existing
  `telegram` receiver (the operator sets `continue:true` per config, so nothing
  else is affected). **Since 2026-08-17 the live copy is Flux-managed** in
  `kubernetes/apps/monitoring/kube-prometheus-stack/app/`; the copy in
  `runbooks/alert-watcher/` is SUPERSEDED and kept only for the ephemeral-mode
  fallback (do NOT `kubectl apply` it — Flux owns the object).
- **`KumaMonitorDown`** PrometheusRule (this IS in git —
  `kube-prometheus-stack/app/uptime-kuma-alerts.yaml`): turns Kuma's 69
  `monitor_status` series into alerts so Kuma-tracked endpoints flow through the
  same pipe (and telegram). Permanent improvement, independent of the watcher.

## The smart half — `alert-triage-agent`
The bridge only *relays*; the judgment lives in `.claude/agents/alert-triage-agent.md`.
On each Monitor `ws` event, the main session hands the alert to that agent, which
decides EXPECTED vs SURFACE and **conservatively auto-silences only clear matches**:
1. an **active-update marker** (`runbooks/update-marker.sh check <app> <ns>`) — the
   update SOP drops one via `update-marker.sh add <app> <ns> <hours>`;
2. the **`noise_suppressions`** policy table (`runbooks/policy-cli.py noise`);
3. a **documented recurrence** (e.g. UniFi GC spiral).
It NEVER auto-silences `critical`/security alerts, scopes silences to the specific
alert with a short TTL, and SURFACEs everything else. Since P4.1.2 every
SURFACE verdict is also **persisted** via `runbooks/alert-record.py` — one
`sweep_findings` row (section `alert`, fingerprint = alert identity, re-fires
dedupe) plus one `home-operation` reminder issue keyed on the finding id — and
the matching Alertmanager `resolved` frame closes both (`--resolved`). A
SURFACE that lived only in a session report used to die with the session; now
it has the same owner/SLA substrate as every other finding. (`ws_clients: 0`
stays a WARNING by design: no session listening is a routine state and the
Alertmanager→Telegram receiver runs in parallel, so paging on it would be
alert-fatigue, not signal.) The main loop keeps owning
the `ws` listen (the agent only rules on what it's handed — see the sub-agent note
below for why the listen can't move into an agent). Note Alertmanager doesn't even
notify on *already-silenced* alerts, so the update SOP's pre-silence step keeps the
watcher quiet during planned updates; the agent handles the leftovers.

## Why session-scoped (not an in-cluster Deployment) — SUPERSEDED, ephemeral-fallback rationale
The consumer is Claude via the `Monitor` tool, which only exists while a session
is alive. A permanent in-cluster bridge would push into the void when no session
is watching, and a permanently-committed webhook receiver would trip
`AlertmanagerFailedToSendAlerts` whenever the bridge is down. So the bridge + the
webhook receiver are ephemeral and torn down with the session.

## Stand up (ephemeral fallback mode — NOT needed while persistent mode is active)
```bash
runbooks/alert-watcher/alert-watch-up.sh
```
This starts the bridge, applies the ephemeral webhook receiver, and verifies
cluster→Mac reachability. Then the **assistant** starts the Monitor push source:

> Monitor  ws = { url: "ws://127.0.0.1:8787/" }  · persistent: true

Prove it end-to-end (optional) — fire a synthetic alert; the Monitor should emit a
`firing` then `resolved` frame:
```bash
kubectl -n monitoring exec deploy/kube-prometheus-stack-operator -- true  # ensure ctx
# or POST to /api/v2/alerts via a port-forward (see git history 2026-07-18).
```

## Tear down (ephemeral fallback mode only — do NOT run against the persistent setup)
```bash
runbooks/alert-watcher/alert-watch-down.sh   # deletes the AM receiver + stops the bridge
```
And the assistant `TaskStop`s the Monitor ws watch. Leaving the receiver up while
the bridge is down will eventually raise a failed-notification alert.

## Verification / health

`GET /` returns a JSON health object (it used to answer the bare string
`alert-bridge ok`, which was true whenever the PROCESS was alive and therefore
could not distinguish a working pager from a dead one — a dead bridge looked
exactly like a quiet cluster):

```bash
curl -s http://127.0.0.1:8788/
# {"ok": true, "ws_clients": 1, "last_post_age_s": 1701.2,
#  "last_watchdog_age_s": 1701.2, "uptime_s": 239462.9}
```

| Field | Meaning | Bad when |
|---|---|---|
| `ws_clients` | operator sessions attached to the websocket | `0` — alerts arrive and are dropped on the floor |
| `last_post_age_s` | seconds since Alertmanager last POSTed anything | tracks `last_watchdog_age_s` in a healthy system |
| `last_watchdog_age_s` | seconds since the **Watchdog** dead-man's switch last arrived | `> 18000` (5h), or `null` once uptime exceeds one 4h `repeat_interval` |
| `uptime_s` | bridge process uptime | needed to interpret a `null` watchdog — a recent restart is not a failure |

**The Watchdog is the liveness proof.** Watchdog is Alertmanager's always-firing
dead-man's switch, and the `claude` route has no matchers, so it arrives here
like any other alert. The bridge records it and discards it. Because it re-sends
on the route's 4h `repeat_interval`, a fresh `last_watchdog_age_s` proves the
whole chain — Alertmanager → network → bridge — was working minutes ago. Nothing
else on this path produces traffic on a schedule: the bridge logs only startups,
never a forwarded alert, so without the Watchdog there is no signal at all
between real alerts.

This is checked automatically by **`runbooks/health-check.sh` Section 41 "Alert
Bridge Liveness"**, which criticals on unreachable, on a watchdog older than 5h,
and on never-seen once uptime passes 4.5h; and warns on `ws_clients: 0`. Until
2026-08-20 nothing checked it and it could not be checked — the log holds 4,582
`alert-bridge up` lines from a bind crash-loop during which alerts were dropped
and nothing said so. That is the silent-zero class from
`docs/sops/audit-script-correctness.md`, applied to the pager itself.

- Receiver merged: the generated secret
  `alertmanager-kube-prometheus-stack-generated` contains `192.168.30.111:8788`.
- Monitor emits a `{"source":"bridge","event":"connected"}` frame on connect; if
  the bridge dies, the WS closes and the Monitor watch ends (your liveness signal).

## Troubleshooting
| Symptom | Cause | Action |
|---|---|---|
| No events ever | receiver not merged yet | wait ~30s for prometheus-operator; check the generated secret |
| `reach: HTTP 000` in up.sh | Mac unreachable from cluster (firewall / IP changed) | verify Mac IP, macOS firewall allows `:8788`, VLAN routing |
| Monitor watch ended unexpectedly | bridge crashed | persistent mode: `~/.claude/logs/alert-bridge.log` (launchd KeepAlive restarts it — just restart Monitor ws); ephemeral mode: `/tmp/alert-bridge.log`, re-run up.sh |
| launchd `runs` climbing, exit 1, `EADDRINUSE` in log | an orphan bridge process holds :8787/:8788 (e.g. leftover nohup instance) | `lsof -nP -i :8788` → kill the orphan; launchd binds on next respawn |
| `AlertmanagerFailedToSendAlerts` firing | receiver left up with bridge down | run `alert-watch-down.sh` |
| `ws_clients: 0` but bridge healthy | no operator session attached | alerts are accepted and discarded — restart the Monitor ws watch |
| `last_watchdog_age_s` null and `uptime_s` > 4.5h | Alertmanager cannot reach the bridge at all | check the `claude-watch-webhook` receiver URL, the Mac's IP, and the macOS firewall on `:8788` |
| `last_watchdog_age_s` > 5h, bridge reachable | Alertmanager stopped posting | pages are being lost silently — check Alertmanager's own health and the route config |
| Bridge answers a bare `alert-bridge ok` string | very old bridge build predating the JSON health surface | Section 41 cannot parse it; update the bridge |

## Should this be a sub-agent? — No (design note)
Asked 2026-07-18. A sub-agent is the **wrong tool** here:
- Sub-agents are **task-scoped workers**: they execute and return. They are not
  long-lived daemons, so one cannot "run and maintain" a background bridge any
  better than a detached process + this runbook can.
- `Monitor` notifications flow to whoever started the watch. If a sub-agent started
  it, the alert events would land in the **sub-agent's** context, not the main
  loop — i.e. you'd stop seeing them. The watch must be owned by the main session.
- The whole stand-up/tear-down is two scripts + one Monitor call. That's a
  **runbook**, not an agent's job.

If you want auto-restart-on-crash of the bridge, that's a **supervisor** concern —
wrap it in `while true; do <bridge>; sleep 1; done`, or a macOS `launchd` user
agent — not a Claude sub-agent. The Monitor already gives you the crash signal
(the WS closes → the watch ends → you're notified), which is usually enough.
