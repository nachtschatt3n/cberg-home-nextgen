# Runbook: Claude push-alert watcher (Alertmanager + Kuma → one WebSocket)

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
- **`claude-watch-webhook.yaml`** — an **ephemeral** `AlertmanagerConfig` (applied
  with `kubectl`, NOT committed to Flux) that makes Alertmanager push every alert
  to the bridge, in parallel with the existing `telegram` receiver (the operator
  sets `continue:true` per config, so nothing else is affected).
- **`KumaMonitorDown`** PrometheusRule (this IS in git —
  `kube-prometheus-stack/app/uptime-kuma-alerts.yaml`): turns Kuma's 69
  `monitor_status` series into alerts so Kuma-tracked endpoints flow through the
  same pipe (and telegram). Permanent improvement, independent of the watcher.

## Why session-scoped (not an in-cluster Deployment)
The consumer is Claude via the `Monitor` tool, which only exists while a session
is alive. A permanent in-cluster bridge would push into the void when no session
is watching, and a permanently-committed webhook receiver would trip
`AlertmanagerFailedToSendAlerts` whenever the bridge is down. So the bridge + the
webhook receiver are ephemeral and torn down with the session.

## Stand up
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

## Tear down (ALWAYS when done watching)
```bash
runbooks/alert-watcher/alert-watch-down.sh   # deletes the AM receiver + stops the bridge
```
And the assistant `TaskStop`s the Monitor ws watch. Leaving the receiver up while
the bridge is down will eventually raise a failed-notification alert.

## Verification / health
- Bridge up: `curl -s http://127.0.0.1:8788/` → `alert-bridge ok`.
- Receiver merged: the generated secret
  `alertmanager-kube-prometheus-stack-generated` contains `192.168.30.111:8788`.
- Monitor emits a `{"source":"bridge","event":"connected"}` frame on connect; if
  the bridge dies, the WS closes and the Monitor watch ends (your liveness signal).

## Troubleshooting
| Symptom | Cause | Action |
|---|---|---|
| No events ever | receiver not merged yet | wait ~30s for prometheus-operator; check the generated secret |
| `reach: HTTP 000` in up.sh | Mac unreachable from cluster (firewall / IP changed) | verify Mac IP, macOS firewall allows `:8788`, VLAN routing |
| Monitor watch ended unexpectedly | bridge crashed | check `/tmp/alert-bridge.log`, re-run up.sh, restart Monitor ws |
| `AlertmanagerFailedToSendAlerts` firing | receiver left up with bridge down | run `alert-watch-down.sh` |

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
