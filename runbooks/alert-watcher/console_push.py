#!/usr/bin/env python3
"""console_push -- type actionable alerts straight into the ops console pane.

Replaces the pull-style Monitor/ws watcher: the alert-bridge hands each
Alertmanager event to Pusher.submit(); the Pusher coalesces/dedupes and TYPES
ONE `[ALERT-PUSH] ...` line into the ai-server-ops iTerm pane through the local
iterm2-harness (the same path the OpenClaw crons use), only when the pane is
idle with an empty input. A quiet cluster therefore costs the console zero turns.

Safety rules (each pinned by runbooks/tests/test-console-push.py):
  * only firing warning/critical (critical resolved is opt-in); never info
  * never types into busy / menu / exhausted panes or over an operator draft
  * pane identity: cwd must be the operations repo, exactly one match
  * not deliverable -> retry with backoff; after DEADLINE_S ONE Telegram notice
  * burst coalescing, per-alert dedupe, per-hour line cap (overflow is counted
    into the next line, never silently dropped)
  * alert text is data: control chars stripped, length capped

The pane classifier below is copied byte-for-byte from the `operation` /
`maintenance-window` skills; test-openclaw-console-delivery.py pins the
original, test-console-push.py pins this copy against it.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# BEGIN shared pane-state block — kept byte-identical in operation.py and
# maintenance-window.py; runbooks/tests/test-openclaw-console-delivery.py pins it.
#
# One pure classifier decides what an unattended delivery may do with the pane:
#   idle               at an empty-or-drafted input prompt, nothing running -> deliverable
#   busy               a turn is executing, or background agents are in flight
#   menu               a question menu / permission prompt / session list owns the
#                      keyboard, or no input prompt is visible at all
#   exhausted-idle     context exhausted, otherwise idle, EMPTY input -> a cron may
#                      /clear it, wait for a fresh prompt, then deliver
#   exhausted-draft    context exhausted and idle, but text sits in the input: refuse
#                      (the wedged TUI can ignore ctrl+u while Enter still submits, so
#                      /clear would be appended to — and submit — a stale draft)
#   exhausted-busy     context exhausted AND busy or in a menu: refuse
#   exhausted-unclear  exhaustion text is on screen but not in the footer (it may be
#                      transcript text): refuse, as before
#
# Why not the old `" esc to "` busy marker alone: it also matched menus ("Esc to
# cancel") and missed "Waiting for N background agents" (live 2026-09-25), which
# shows no "esc to interrupt" and which `openclaude status` reports as idle.
PANE_BUSY_MARKERS = ("esc to interrupt", "interrupt)")
PANE_BUSY_RE = re.compile(r"waiting for \d+ background|\d+ background (?:agents?|tasks?) running")
PANE_AGENT_TRAY_RE = re.compile(r"\bfor agents\b")
PANE_MENU_MARKERS = (
    "enter to select", "enter to confirm", "↑/↓ to", "↑↓ to", "esc to cancel",
    "esc to exit", "esc to go back", "esc to close", "do you want to proceed",
    "resume session", "type to search",
)
PANE_MENU_ITEM_RE = re.compile(r"^\s*[│|]?\s*[❯>›]\s*\d+\.\s")
PANE_INPUT_RE = re.compile(r"^\s*[│|]?\s*[❯>](?:\s(.*?))?\s*[│|]?\s*$")
PANE_EXHAUSTED_RE = re.compile(r"/clear to save \d|100% context used")
PANE_PLACEHOLDER_RE = re.compile(r'^try "')
PANE_FOOTER_FALLBACK_LINES = 10
PANE_STATES = ("idle", "busy", "menu", "exhausted-idle", "exhausted-draft",
               "exhausted-busy", "exhausted-unclear")


def _pane_lines(screen_text):
    return (screen_text or "").replace("\xa0", " ").splitlines()


def _pane_input_index(lines):
    """Index of the LAST input-prompt line (`❯ …` / `│ > … │`), or None.
    A numbered menu cursor (`❯ 1. Yes`) is not an input line."""
    for i in range(len(lines) - 1, -1, -1):
        ln = lines[i]
        if PANE_MENU_ITEM_RE.match(ln):
            continue
        if PANE_INPUT_RE.match(ln):
            return i
    return None


def pane_draft(screen_text):
    """Pure: the text sitting in the input line ('' when empty or placeholder)."""
    lines = _pane_lines(screen_text)
    i = _pane_input_index(lines)
    if i is None:
        return ""
    m = PANE_INPUT_RE.match(lines[i])
    txt = (m.group(1) or "").strip() if m else ""
    if PANE_PLACEHOLDER_RE.match(txt.lower()):
        return ""
    return txt


def classify_pane(screen_text):
    """Pure: one of PANE_STATES for a Claude Code pane's visible screen."""
    lines = _pane_lines(screen_text)
    low = [ln.lower() for ln in lines]
    whole = "\n".join(low)
    i = _pane_input_index(lines)
    footer = low[i:] if i is not None else low[-PANE_FOOTER_FALLBACK_LINES:]
    busy = (any(m in whole for m in PANE_BUSY_MARKERS)
            or bool(PANE_BUSY_RE.search(whole))
            or any(PANE_AGENT_TRAY_RE.search(ln) for ln in footer))
    menu = (i is None
            or any(m in whole for m in PANE_MENU_MARKERS)
            or any(PANE_MENU_ITEM_RE.match(ln) for ln in lines)
            or " esc to " in whole.replace("esc to interrupt", ""))
    if PANE_EXHAUSTED_RE.search(whole):
        if not any(PANE_EXHAUSTED_RE.search(ln) for ln in footer):
            return "exhausted-unclear"
        if busy or menu:
            return "exhausted-busy"
        if pane_draft(screen_text):
            return "exhausted-draft"
        return "exhausted-idle"
    if busy:
        return "busy"
    if menu:
        return "menu"
    return "idle"


def console_busy(screen_text):
    """Pure: True when the console is NOT at a deliverable prompt — a turn in
    progress, background agents in flight, a menu/list open, or any exhausted
    state. Nothing may be typed (not even ctrl+u) into such a pane."""
    return classify_pane(screen_text) != "idle"


PANE_RECOVERED = {"cleared": False}
PANE_CLEAR_WAIT_S = 30


def recover_exhausted_pane(sid, label, screen_fn, oc_fn, sleep_fn, tag):
    """Operator decision F-7d9b201b (2026-09-25): an exhausted pane that is
    otherwise IDLE with an EMPTY input gets /clear, then we wait for a fresh
    idle prompt. Returns (ok, reason). Never types into any other state."""
    st = classify_pane(screen_fn(sid))
    if st != "exhausted-idle":
        return False, f"pane state is {st!r}, not exhausted-idle -- not clearing"
    msg = (f"CONSOLE_AUTO_CLEARED: {tag}: the {label} pane ({sid[:8]}) was at context "
           f"exhaustion and IDLE with an empty input -- sending /clear (its conversation "
           f"context is discarded; the transcript is kept on disk) at "
           f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(msg)
    sys.stderr.write(msg + "\n")
    r = oc_fn("send", sid, "/clear", "--enter")
    if r is None or r.returncode != 0:
        return False, "sending /clear failed: " + ((getattr(r, "stderr", "") or "").strip()[:200])
    st = "unknown"
    for _ in range(max(1, PANE_CLEAR_WAIT_S // 2)):
        sleep_fn(2)
        scr = screen_fn(sid)
        st = classify_pane(scr)
        if st == "idle" and not pane_draft(scr):
            PANE_RECOVERED["cleared"] = True
            done = f"{tag}: /clear took -- fresh idle prompt on {label}; proceeding"
            print(done)
            sys.stderr.write(done + "\n")
            return True, "cleared"
    return False, (f"/clear was sent but no fresh idle prompt appeared within "
                   f"{PANE_CLEAR_WAIT_S}s (last state {st!r})")
# END shared pane-state block


# ---- push layer -------------------------------------------------------------
PREFIX = "[ALERT-PUSH]"
REPO = os.environ.get("OPERATION_REPO", "/Users/mu/code/cberg-home-nextgen").rstrip("/")
HARNESS_URL = os.environ.get("ITERM2_HARNESS_URL", "http://127.0.0.1:6770")
SELECTOR = os.environ.get("ALERT_PUSH_SESSION", "ai-server-ops")
TOKENS_FILE = Path(os.environ.get("ITERM2_HARNESS_TOKENS",
                                  str(Path.home() / ".iterm2-harness" / "tokens.json")))
TOKEN_DEVICE = os.environ.get("ITERM2_HARNESS_DEVICE", "this-mac")

PUSH_SEVERITIES = ("warning", "critical")
COALESCE_S = float(os.environ.get("ALERT_PUSH_COALESCE_S", "20"))
DEDUPE_S = {"critical": 2 * 3600, "warning": 6 * 3600}
MAX_LINES_PER_HOUR = int(os.environ.get("ALERT_PUSH_MAX_PER_HOUR", "6"))
DEADLINE_S = float(os.environ.get("ALERT_PUSH_DEADLINE_S", "900"))
BACKOFF_S = (15, 30, 60, 120, 180)
MAX_LINE = 420
MAX_PER_ALERT = 110

INSTRUCTION = ("triage per runbooks/alert-watcher.md via alert-triage-agent; automated push, "
               "not operator input; never silence critical")


def _clean(s, cap):
    s = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", str(s or ""))
    s = re.sub(r"\s+", " ", s).strip().replace("`", "'")
    return s[:cap]


def alert_key(evt):
    return (evt.get("alertname", ""), evt.get("namespace", ""), evt.get("pod", ""),
            evt.get("instance", ""))


def wanted(evt, critical_resolved=False):
    """Pure: should this bridge event ever be typed into the console?"""
    if evt.get("source") != "alertmanager":
        return False
    sev, status = evt.get("severity"), evt.get("status")
    if status == "firing":
        return sev in PUSH_SEVERITIES
    if status == "resolved":
        return critical_resolved and sev == "critical"
    return False


def build_line(items, suppressed=0):
    """Pure: ONE single-line prompt for a batch of events."""
    parts = []
    for e in items:
        where = "/".join(x for x in (e.get("namespace"), e.get("pod") or e.get("instance")) if x)
        tag = "RESOLVED " if e.get("status") == "resolved" else ""
        txt = f"{tag}{e.get('severity')} {_clean(e.get('alertname'), 60)}"
        if where:
            txt += f" ({_clean(where, 50)})"
        if e.get("summary"):
            txt += f" '{_clean(e['summary'], 70)}'"
        parts.append(txt[:MAX_PER_ALERT])
    head = f"{PREFIX} {len(items)} alert{'s' if len(items) != 1 else ''}"
    if suppressed:
        head += f" (+{suppressed} more held back by the hourly cap)"
    line = f"{head}: " + "; ".join(parts)
    tail = f" -- {INSTRUCTION}"
    if len(line) + len(tail) > MAX_LINE:
        line = line[:MAX_LINE - len(tail) - 1].rstrip() + "…"
    return line + tail


class Harness:
    """Thin client for the LOCAL iterm2-harness (the OpenClaw crons use the same one)."""

    def __init__(self, base=HARNESS_URL, selector=SELECTOR, token=None):
        self.base, self.selector, self._token = base.rstrip("/"), selector, token

    def token(self):
        if self._token:
            return self._token
        d = json.loads(TOKENS_FILE.read_text())
        for tok, meta in d.items():
            if (meta or {}).get("device_name") == TOKEN_DEVICE:
                self._token = tok
                return tok
        raise RuntimeError(f"no harness token for device {TOKEN_DEVICE!r}")

    def _req(self, method, path, body=None, timeout=10):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")

    def sessions(self):
        q = urllib.parse.quote(self.selector)
        return self._req("GET", f"/api/v1/sessions?name={q}").get("sessions", [])

    def screen(self, sid, limit=40):
        return "\n".join(self._req("GET", f"/api/v1/sessions/{sid}/screen?limit={limit}")
                         .get("lines", []))

    def send_text(self, sid, text):
        return self._req("POST", f"/api/v1/sessions/{sid}/send-text", {"text": text})

    def send_key(self, sid, key):
        return self._req("POST", f"/api/v1/sessions/{sid}/send-key", {"key": key})


import urllib.parse  # noqa: E402  (used by Harness.sessions)


def resolve_console(h, repo=REPO):
    """(sid, None) for the single ops-console pane, else (None, reason)."""
    try:
        cands = [s for s in h.sessions()
                 if str(s.get("path", "")).rstrip("/") == repo
                 or str(s.get("path", "")).startswith(repo + "/")]
    except Exception as e:  # noqa: BLE001
        return None, f"harness unreachable: {type(e).__name__}: {e}"
    if len(cands) != 1:
        return None, f"{len(cands)} panes match {h.selector!r} in {repo} (need exactly 1)"
    return cands[0]["session_id"], None


def default_notify(text):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from runbooks.lib.notify import notify
    return notify(text, urgent=False)


class Pusher:
    def __init__(self, harness=None, notify=None, clock=time.monotonic, sleep=time.sleep,
                 dry_run=False, critical_resolved=False, log=print):
        self.h = harness or Harness()
        self.notify = notify or default_notify
        self.clock, self.sleep, self.dry_run = clock, sleep, dry_run
        self.critical_resolved, self.log = critical_resolved, log
        self.lock = threading.Lock()
        self.pending = []          # events waiting to be typed
        self.first_seen = None     # clock() of oldest pending event
        self.seen = {}             # key -> last accepted clock()
        self.sent_at = []          # clock() of each typed line (hour cap)
        self.suppressed = 0
        self.typed = []            # lines actually typed (test + audit)
        self.attempt = 0
        self.next_try = 0.0
        self.notified = False
        self.cap_notified = False

    # -- ingest ---------------------------------------------------------------
    def submit(self, evt):
        """Thread-safe; returns True if the event was queued."""
        if not wanted(evt, self.critical_resolved):
            return False
        now, key = self.clock(), alert_key(evt)
        with self.lock:
            if evt.get("status") == "firing":
                last = self.seen.get(key)
                if last is not None and now - last < DEDUPE_S.get(evt["severity"], 6 * 3600):
                    return False
                self.seen[key] = now
            if any(alert_key(p) == key and p.get("status") == evt.get("status")
                   for p in self.pending):
                return False
            if not self.pending:
                self.first_seen, self.attempt, self.next_try, self.notified = now, 0, now + COALESCE_S, False
            self.pending.append(evt)
            return True

    # -- delivery -------------------------------------------------------------
    def tick(self):
        """Advance the state machine once. Returns a short status string."""
        now = self.clock()
        with self.lock:
            if not self.pending or now < self.next_try:
                return "wait"
            batch = list(self.pending)
        self.sent_at = [t for t in self.sent_at if now - t < 3600]
        if len(self.sent_at) >= MAX_LINES_PER_HOUR:
            with self.lock:
                self.suppressed += len(batch)
                self.pending = self.pending[len(batch):]
            if not self.cap_notified:
                self.cap_notified = True
                try:
                    self.notify(f"alert-bridge hourly console cap ({MAX_LINES_PER_HOUR}) reached; "
                                f"further alerts this hour are NOT typed into the console")
                except Exception as e:  # noqa: BLE001
                    self.log(f"console_push notify failed: {e}")
            return "capped"
        self.cap_notified = False
        sid, why = resolve_console(self.h)
        state = None
        if sid:
            try:
                scr = self.h.screen(sid)
                state = classify_pane(scr)
                if state == "idle" and pane_draft(scr):
                    state = "draft"
            except Exception as e:  # noqa: BLE001
                why = f"screen read failed: {type(e).__name__}: {e}"
        if state == "idle":
            line = build_line(batch, self.suppressed)
            if self.dry_run:
                self.log(f"[console_push dry-run] would type: {line}")
            else:
                try:
                    self.h.send_text(sid, line)
                    self.sleep(0.4)
                    self.h.send_key(sid, "enter")
                except Exception as e:  # noqa: BLE001
                    why = f"send failed: {type(e).__name__}: {e}"
                    state = None
            if state == "idle":
                self.typed.append(line)
                self.sent_at.append(now)
                with self.lock:
                    self.pending = self.pending[len(batch):]
                    self.suppressed = 0
                    self.first_seen = now if self.pending else None
                    self.attempt, self.next_try = 0, now + COALESCE_S
                return "typed"
        if state in ("exhausted-idle", "exhausted-draft", "exhausted-busy", "exhausted-unclear"):
            return self._give_up(batch, now, f"pane state {state}")
        if now - (self.first_seen or now) >= DEADLINE_S:
            return self._give_up(batch, now, why or f"pane not idle for {int(DEADLINE_S)}s (state {state})")
        delay = BACKOFF_S[min(self.attempt, len(BACKOFF_S) - 1)]
        self.attempt += 1
        self.next_try = now + delay
        return f"retry:{state or 'error'}"

    def _give_up(self, batch, now, why):
        text = (f"alert-bridge could not type {len(batch)} alert(s) into the ops console "
                f"({why}): " + "; ".join(
                    f"{e.get('severity')} {e.get('alertname')}" for e in batch)[:600])
        try:
            self.notify(text)
        except Exception as e:  # noqa: BLE001
            self.log(f"console_push notify failed: {e}")
        with self.lock:
            self.pending = self.pending[len(batch):]
            self.first_seen = None
            self.attempt = 0
        self.log(f"console_push gave up: {why}")
        return "notified"

    def run_forever(self, interval=5.0):
        while True:
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001
                self.log(f"console_push tick error: {type(e).__name__}: {e}")
            self.sleep(interval)


def main(argv=None):
    """CLI: `console_push.py --dry-run 'warning FooDown ns/pod summary'` prints the line
    (and, unless --dry-run, types it if the pane is idle)."""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--classify", action="store_true", help="print the console pane state")
    ap.add_argument("alert", nargs="*", help="severity alertname [ns/pod] [summary...]")
    a = ap.parse_args(argv)
    h = Harness()
    sid, why = resolve_console(h)
    if a.classify:
        print(f"{sid}: {classify_pane(h.screen(sid))}" if sid else f"unresolved: {why}")
        return 0 if sid else 2
    if len(a.alert) < 2:
        ap.error("need: severity alertname [ns/pod] [summary...]")
    ns_pod = a.alert[2] if len(a.alert) > 2 else ""
    ns, _, pod = ns_pod.partition("/")
    evt = {"source": "alertmanager", "status": "firing", "severity": a.alert[0],
           "alertname": a.alert[1], "namespace": ns, "pod": pod,
           "summary": " ".join(a.alert[3:])}
    p = Pusher(h, dry_run=a.dry_run, sleep=time.sleep)
    p.submit(evt)
    p.next_try = 0
    print(p.tick())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
