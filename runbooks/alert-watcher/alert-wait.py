#!/usr/bin/env python3
"""Block silently on the alert-bridge WebSocket; print ONE line and exit on the
first NEW actionable alert (firing, not replayed, severity != info), so a quiet
cluster costs the assistant zero turns. Reconnects on drops; prints a line and
exits non-zero only if the bridge is unreachable for --give-up seconds."""
import argparse
import asyncio
import json
import time

import websockets


async def wait(url: str, give_up: float) -> int:
    down_since = None
    while True:
        try:
            async with websockets.connect(url, open_timeout=10) as ws:
                down_since = None
                async for raw in ws:
                    try:
                        ev = json.loads(raw)
                    except ValueError:
                        print(raw)
                        return 0
                    if ev.get("source") == "bridge" or ev.get("replayed"):
                        continue
                    if ev.get("status") != "firing" or ev.get("severity") == "info":
                        continue
                    print(json.dumps(ev))
                    return 0
        except (OSError, websockets.WebSocketException):
            down_since = down_since or time.monotonic()
            if time.monotonic() - down_since > give_up:
                print(json.dumps({"source": "alert-wait", "event": "bridge-unreachable", "url": url}))
                return 2
            await asyncio.sleep(5)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://127.0.0.1:8787/")
    ap.add_argument("--give-up", type=float, default=300)
    a = ap.parse_args()
    raise SystemExit(asyncio.run(wait(a.url, a.give_up)))
