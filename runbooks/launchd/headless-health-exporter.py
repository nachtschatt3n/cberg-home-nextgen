#!/usr/bin/env python3
"""Prometheus exporter for the Mac-side cron path (2026-11-08).

The OpenClaw crons (maintenance windows, version snapshot, retro) reach the Mac
through (1) the iterm2-harness HTTP API on :6770 and (2) a `headless-dispatcher`
pane running runbooks/headless-dispatcher.py inside iTerm. On 2026-11-08 both
the nightly and the Sunday attended window failed with HEADLESS_UNAVAILABLE
because the dispatcher pane was gone for ~14 h and nothing told anyone.
This tiny stdlib server publishes that state on :9103 so Prometheus (ScrapeConfig
`headless-cron-path`, rules in kubernetes/.../headless-cron-path-alerts.yaml)
can alert. Probes run per scrape (no cache): ps + one localhost HTTP GET.

Metrics (1 = healthy):
  cberg_headless_dispatcher_up        a python runbooks/headless-dispatcher.py
                                      with a controlling tty exists (same test
                                      as headless-dispatcher-keeper.sh)
  cberg_iterm2_harness_up             GET 127.0.0.1:6770/api/v1/health -> 200
  cberg_iterm_running                 the iTerm2 app process exists
  cberg_iterm_dispatcher_keeper_up    the iTerm-side keeper holds its flock
Binds 0.0.0.0 like the other Mac exporters (:9100-:9102); read-only, no secrets.
"""
import fcntl
import http.server
import os
import subprocess
import urllib.request

PORT = int(os.environ.get("EXPORTER_PORT", "9103"))
HEALTH_URL = os.environ.get("HARNESS_HEALTH_URL", "http://127.0.0.1:6770/api/v1/health")
LOCK = os.path.expanduser("~/Library/Logs/cberg-headless/iterm-keeper.lock")


def ps_lines():
    out = subprocess.run(["ps", "-axo", "pid=,tty=,command="], capture_output=True,
                         text=True, timeout=10).stdout
    return [l.strip() for l in out.splitlines() if l.strip()]


def dispatcher_up(lines):
    for l in lines:
        parts = l.split(None, 2)
        if len(parts) < 3:
            continue
        _, tty, cmd = parts
        if tty == "??" or "runbooks/headless-dispatcher.py" not in cmd or "--self-test" in cmd:
            continue
        return 1
    return 0


def iterm_running(lines):
    return int(any("/iTerm.app/Contents/MacOS/iTerm2" in l for l in lines))


def harness_up():
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as r:
            return int(r.status == 200)
    except Exception:  # noqa: BLE001
        return 0


def keeper_up():
    """The keeper holds an exclusive flock for its whole life; if we can take
    it, nobody holds it. (A missing lock file also means no keeper ever ran.)"""
    try:
        fh = open(LOCK, "r")
    except OSError:
        return 0
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 1
    finally:
        fh.close()  # closing drops any lock we just took
    return 0


def render():
    try:
        lines = ps_lines()
        disp, itr = dispatcher_up(lines), iterm_running(lines)
        scraped = 1
    except Exception:  # noqa: BLE001
        disp = itr = scraped = 0
    rows = [
        ("cberg_headless_dispatcher_up", "dispatcher process with a tty exists", disp),
        ("cberg_iterm2_harness_up", "iterm2-harness /api/v1/health answers 200", harness_up()),
        ("cberg_iterm_running", "iTerm2 app process exists", itr),
        ("cberg_iterm_dispatcher_keeper_up", "iTerm-side keeper holds its lock", keeper_up()),
        ("cberg_headless_exporter_probe_ok", "the ps probe itself worked", scraped),
    ]
    out = []
    for name, helptext, val in rows:
        out += [f"# HELP {name} {helptext}", f"# TYPE {name} gauge", f"{name} {val}"]
    return "\n".join(out) + "\n"


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.split("?")[0] != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        body = render().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # keep launchd logs quiet
        pass


if __name__ == "__main__":
    if os.environ.get("EXPORTER_ONESHOT"):
        print(render(), end="")
    else:
        http.server.ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
