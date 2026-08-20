#!/usr/bin/env python3
"""Unified push event-bridge for a Claude Monitor `ws` watcher.

Two ingress paths -> one WebSocket the Monitor subscribes to:
  * HTTP POST /alertmanager  <- Alertmanager webhook_config (every alert, push)
  * (Uptime Kuma monitor-down flows in via the KumaMonitorDown alert rule,
    i.e. through the same Alertmanager webhook — no separate Kuma client needed.)
The WS at ws://127.0.0.1:$WS_PORT/  streams one JSON frame per alert transition
(firing AND resolved). See runbooks/alert-watcher.md for the full setup.

Env: WS_PORT (default 8787), HTTP_PORT (default 8788). Deps: stdlib + `websockets`.
Run from the repo venv (has websockets):  .venv/bin/python3 runbooks/alert-watcher/alert-bridge.py
"""
import asyncio
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import websockets

WS_PORT = int(os.environ.get("WS_PORT", "8787"))
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8788"))
REPLAY_SECS = int(os.environ.get("REPLAY_SECS", "300"))  # replay recent alerts on (re)connect

_loop = asyncio.new_event_loop()
_clients: set = set()
_queue: "asyncio.Queue" = asyncio.Queue()
# ring buffer of (monotonic_ts, event) so a reconnecting Monitor isn't blind to
# alerts that fired during a brief WS idle-drop.
_recent: "deque" = deque(maxlen=200)


def _ts():
    return datetime.now(timezone.utc).strftime("%H:%M:%SZ")


async def _ws_handler(ws):
    _clients.add(ws)
    # greet so the Monitor shows the watcher is live and connected
    await ws.send(json.dumps({"source": "bridge", "event": "connected", "ts": _ts(),
                              "note": "alert-bridge WS ready; awaiting pushed alerts"}))
    # Replay alerts from the last REPLAY_SECS so a reconnect after an idle-drop
    # doesn't miss anything that fired in the gap. Marked replayed to avoid alarm.
    cutoff = time.monotonic() - REPLAY_SECS
    for mono, evt in list(_recent):
        if mono >= cutoff:
            try:
                await ws.send(json.dumps({**evt, "replayed": True}))
            except Exception:
                break
    try:
        await ws.wait_closed()
    finally:
        _clients.discard(ws)


async def _fanout():
    while True:
        item = await _queue.get()
        _recent.append((time.monotonic(), item))
        data = json.dumps(item)
        for ws in list(_clients):
            try:
                await ws.send(data)
            except Exception:
                _clients.discard(ws)


# Liveness state. The bridge carries every critical page, and until 2026-08-20
# nothing could tell "no alerts are firing" from "the bridge stopped forwarding":
# do_GET answered "ok" whenever the PROCESS was alive, health-check.sh did not
# reference the bridge at all, and the log records only startups (4,582 of them
# from the historical bind crash-loop) -- never a forwarded alert. Alertmanager
# already sends Watchdog here on every cycle and the handler drops it, so the
# dead-man's switch was arriving and being thrown away. Record it instead.
_last_post = 0.0        # any webhook POST reached us
_last_watchdog = 0.0    # the always-firing heartbeat specifically
_started = time.time()  # so a checker can tell "not yet" from "stopped arriving":
                        # Alertmanager re-sends Watchdog on repeat_interval (4h
                        # for the claude route), so a bridge younger than that
                        # legitimately has no heartbeat yet.


class _Webhook(BaseHTTPRequestHandler):
    def do_POST(self):
        global _last_post, _last_watchdog
        _last_post = time.time()
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            return
        # Alertmanager v4 webhook: {alerts:[{status,labels,annotations,...}]}
        # Drop synthetic control-plane alerts that carry no real condition
        # (Watchdog = always-firing heartbeat; InfoInhibitor = fires to drive
        # info-level inhibition). Both are routed to "null" in the telegram config.
        _SYNTHETIC = {"Watchdog", "InfoInhibitor"}
        for a in payload.get("alerts", []):
            lbl = a.get("labels", {})
            if lbl.get("alertname") in _SYNTHETIC:
                if lbl.get("alertname") == "Watchdog":
                    # Still NOT forwarded -- it carries no condition. But its
                    # arrival proves Alertmanager can still reach us, which is
                    # the only evidence that silence means "nothing firing".
                    _last_watchdog = time.time()
                continue
            evt = {
                "source": "alertmanager",
                "status": a.get("status"),               # firing | resolved
                "severity": lbl.get("severity", "?"),
                "alertname": lbl.get("alertname", "?"),
                "namespace": lbl.get("namespace", ""),
                "pod": lbl.get("pod", ""),
                "instance": lbl.get("instance", ""),
                "summary": (a.get("annotations", {}) or {}).get("summary", "")[:160],
                "ts": _ts(),
            }
            _loop.call_soon_threadsafe(_queue.put_nowait, evt)

    def do_GET(self):  # health probe
        now = time.time()
        body = json.dumps({
            "ok": True,
            "ws_clients": len(_clients),
            # null = never seen since this process started, which for the
            # watchdog means Alertmanager is NOT reaching us.
            "last_post_age_s": round(now - _last_post, 1) if _last_post else None,
            "last_watchdog_age_s": round(now - _last_watchdog, 1) if _last_watchdog else None,
            "uptime_s": round(now - _started, 1),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _bind_retry(factory, what, attempts=15, delay=2.0):
    """Bind with retry: when launchd's KeepAlive respawn races the dying
    predecessor (TIME_WAIT / not-yet-released socket), an immediate one-shot
    bind fails with EADDRINUSE, the new instance exits 1, and launchd + a
    surviving half-dead process settle into the orphan-holds-ports pattern
    seen twice on 2026-08-17/18. Retrying for ~30s lets the predecessor
    finish dying so exactly one instance ends up bound AND launchd-owned."""
    import time as _time
    last = None
    for _ in range(attempts):
        try:
            return factory()
        except OSError as e:
            last = e
            print(f"[{_ts()}] {what} bind busy ({e}); retrying...", flush=True)
            _time.sleep(delay)
    raise last


def _http_thread():
    srv = _bind_retry(lambda: ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), _Webhook), "http")
    srv.serve_forever()


async def _main():
    threading.Thread(target=_http_thread, daemon=True).start()
    asyncio.create_task(_fanout())
    print(f"[{_ts()}] alert-bridge up: webhook http://0.0.0.0:{HTTP_PORT}/alertmanager "
          f"| ws ws://127.0.0.1:{WS_PORT}/", flush=True)
    # ping_interval keeps the connection warm through quiet stretches (control
    # frames, not data — so they don't become Monitor events). ping_timeout=None:
    # the Monitor WS client does NOT send pong replies, so any finite pong-timeout
    # made the server tear the socket down every ~ping_interval+timeout (~80s → the
    # observed recurring 1006 close). Disable the pong deadline so a non-ponging but
    # otherwise-live client isn't killed; liveness still comes from TCP + the
    # per-client send-failure discard in _fanout, and reconnect+REPLAY covers any gap.
    for attempt in range(15):
        try:
            async with websockets.serve(_ws_handler, "127.0.0.1", WS_PORT,
                                        ping_interval=20, ping_timeout=None):
                await asyncio.Future()
        except OSError as e:
            print(f"[{_ts()}] ws bind busy ({e}); retrying...", flush=True)
            await asyncio.sleep(2.0)


if __name__ == "__main__":
    asyncio.set_event_loop(_loop)
    _loop.run_until_complete(_main())
