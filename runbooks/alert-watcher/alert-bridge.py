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
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import websockets

WS_PORT = int(os.environ.get("WS_PORT", "8787"))
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8788"))

_loop = asyncio.new_event_loop()
_clients: set = set()
_queue: "asyncio.Queue" = asyncio.Queue()


def _ts():
    return datetime.now(timezone.utc).strftime("%H:%M:%SZ")


async def _ws_handler(ws):
    _clients.add(ws)
    # greet so the Monitor shows the watcher is live and connected
    await ws.send(json.dumps({"source": "bridge", "event": "connected", "ts": _ts(),
                              "note": "alert-bridge WS ready; awaiting pushed alerts"}))
    try:
        await ws.wait_closed()
    finally:
        _clients.discard(ws)


async def _fanout():
    while True:
        item = await _queue.get()
        data = json.dumps(item)
        for ws in list(_clients):
            try:
                await ws.send(data)
            except Exception:
                _clients.discard(ws)


class _Webhook(BaseHTTPRequestHandler):
    def do_POST(self):
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
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"alert-bridge ok")

    def log_message(self, *a):
        pass


def _http_thread():
    ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), _Webhook).serve_forever()


async def _main():
    threading.Thread(target=_http_thread, daemon=True).start()
    asyncio.create_task(_fanout())
    print(f"[{_ts()}] alert-bridge up: webhook http://0.0.0.0:{HTTP_PORT}/alertmanager "
          f"| ws ws://127.0.0.1:{WS_PORT}/", flush=True)
    async with websockets.serve(_ws_handler, "127.0.0.1", WS_PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.set_event_loop(_loop)
    _loop.run_until_complete(_main())
