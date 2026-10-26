"""Regression tests for push-alerts-into-the-ops-console (runbooks/alert-watcher/console_push.py).

Pins: the classifier copy still equals the OpenClaw skills' block (skipped loudly when
sops/age is unavailable), event filtering, line shape + injection hygiene, coalescing,
dedupe, hourly cap, delivery only into an IDLE EMPTY pane, retry/backoff, the single
Telegram fallback after the deadline, pane-identity refusal, dry-run.

Run:  python3 runbooks/tests/test-console-push.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cp = load("console_push_under_test", REPO / "runbooks/alert-watcher/console_push.py")
dl = load("console_delivery_fixtures", REPO / "runbooks/tests/test-openclaw-console-delivery.py")
S, EXPECT, check, FAILURES = dl.S, dl.EXPECT, dl.check, dl.FAILURES


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeHarness:
    """Echoes typed text into a (77-col, soft-wrapped) input box like the real
    pane, so the pre-Enter re-read sees what Claude Code would show. `mutate`
    rewrites what the re-read sees (operator typing between type and Enter)."""
    selector = "ai-server-ops"

    def __init__(self, screen="idle", sessions=None):
        self.screen_key = screen
        self.sess = sessions if sessions is not None else [
            {"session_id": "SID-1", "path": cp.REPO}]
        self.calls = []
        self.input = None
        self.mutate = None

    def sessions(self):
        return self.sess

    def screen(self, sid, limit=40):
        self.calls.append(("screen", sid))
        if self.input is not None:
            txt = self.mutate(self.input) if self.mutate else self.input
            return input_pane(txt)
        return S[self.screen_key]

    def send_text(self, sid, text):
        self.calls.append(("text", sid, text))
        self.input = text

    def send_key(self, sid, key):
        self.calls.append(("key", sid, key))
        if key == "enter":
            self.input = None


def input_pane(text, width=74):
    rows = textwrap.wrap(text, width=width, break_long_words=True) or [""]
    box = "\n".join([f"❯{dl.NB}{rows[0]}"] + [f"  {r}" for r in rows[1:]])
    return dl._pane("⏺ Done. Pushed the fix.", box, dl.FOOT)


def evt(name="FooDown", sev="warning", status="firing", ns="apps", pod="foo-1", summary="foo is down"):
    return {"source": "alertmanager", "status": status, "severity": sev, "alertname": name,
            "namespace": ns, "pod": pod, "instance": "", "summary": summary}


def mk(screen="idle", notify_ok=True, logs=None, **kw):
    """notify fake mirrors runbooks/lib/notify.py: returns True/False, never raises.
    `notify_ok` may be a one-element list so a test can flip it mid-run."""
    clk, notes = Clock(), []
    ok = notify_ok if isinstance(notify_ok, list) else [notify_ok]

    def notify(m):
        if ok[0]:
            notes.append(m)
        return ok[0]
    h = FakeHarness(screen, kw.pop("sessions", None))
    p = cp.Pusher(h, notify=notify, clock=clk, sleep=clk.sleep,
                  log=(logs.append if logs is not None else lambda m: None), **kw)
    return p, h, clk, notes


def typed(h):
    return [c for c in h.calls if c[0] in ("text", "key")]


def test_pin():
    """Decrypts the skills ONCE into a private TemporaryDirectory that is
    overwritten and removed on every exit path -- an earlier version leaked two
    plaintext copies per run into mkdtemp() dirs (18 found, 2026-10-26)."""
    with tempfile.TemporaryDirectory(prefix="console-push-pin-") as td:
        d = Path(td)
        d.chmod(0o700)
        try:
            err = dl.decrypt_into(d)
            if err:
                print(f"  SKIP  classifier pin vs OpenClaw skills: {err}")
                return
            orig = dl.shared_block((d / "operation.py").read_text())
        finally:
            for f in d.iterdir():
                try:
                    f.write_bytes(b"\0" * f.stat().st_size)
                except OSError:
                    pass
    check("pin: no plaintext left behind", not Path(td).exists())
    mine = dl.shared_block(Path(cp.__file__).read_text())
    check("classifier block byte-identical to the operation skill's", bool(orig) and orig == mine)


def test_classifier():
    for name, want in EXPECT.items():
        check(f"classify {name} -> {want}", cp.classify_pane(S[name]) == want)


def test_filter_and_line():
    check("firing warning wanted", cp.wanted(evt()))
    check("firing critical wanted", cp.wanted(evt(sev="critical")))
    check("NEG: info never wanted", not cp.wanted(evt(sev="info")))
    check("NEG: resolved warning never wanted", not cp.wanted(evt(status="resolved")))
    check("NEG: critical resolved off by default", not cp.wanted(evt(sev="critical", status="resolved")))
    check("critical resolved opt-in", cp.wanted(evt(sev="critical", status="resolved"), True))
    check("NEG: non-alertmanager source", not cp.wanted({**evt(), "source": "bridge"}))
    line = cp.build_line([evt(summary="line1\nline2\x1b[31m `rm -rf /` \r")], 0)
    check("line is single-line, no control chars/backticks",
          "\n" not in line and "\r" not in line and "\x1b" not in line and "`" not in line, repr(line))
    check("line carries the recognisable prefix", line.startswith(cp.PREFIX))
    check("line points at the runbook + triage agent",
          "runbooks/alert-watcher.md" in line and "alert-triage-agent" in line)
    big = cp.build_line([evt(name=f"A{i}", summary="x" * 500) for i in range(20)], 3)
    check("line length capped", len(big) <= cp.MAX_LINE + 40, str(len(big)))
    check("hold-back count is reported", "3 of them held back" in big)


def test_delivery():
    p, h, clk, _ = mk()
    p.submit(evt())
    check("not typed before the coalesce window", p.tick() == "wait" and not typed(h))
    clk.t += cp.COALESCE_S + 1
    check("idle pane -> typed", p.tick() == "typed")
    t = [c for c in h.calls if c[0] == "text"]
    check("exactly one text then Enter", len(t) == 1 and typed(h)[-1][2] == "enter" and len(typed(h)) == 2)
    check("typed text is the [ALERT-PUSH] line", t[0][2].startswith(cp.PREFIX) and "FooDown" in t[0][2])

    p, h, clk, _ = mk()
    for i in range(4):
        p.submit(evt(name=f"Burst{i}"))
    clk.t += cp.COALESCE_S + 1
    p.tick()
    check("burst of 4 coalesced into ONE line", len([c for c in h.calls if c[0] == "text"]) == 1
          and "4 alerts" in [c for c in h.calls if c[0] == "text"][-1][2])

    p, h, clk, _ = mk()
    p.submit(evt())
    check("NEG: duplicate firing deduped", p.submit(evt()) is False)
    clk.t += cp.COALESCE_S + 1
    p.tick()
    clk.t += 3600
    check("NEG: same alert 1h later still deduped (flap guard)", p.submit(evt()) is False)
    clk.t += 6 * 3600
    check("same alert after the dedupe window accepted", p.submit(evt()) is True)

    p, h, clk, notes = mk()
    for i in range(cp.MAX_LINES_PER_HOUR + 2):
        p.submit(evt(name=f"Cap{i}"))
        clk.t += cp.COALESCE_S + 1
        p.tick()
    n = len([c for c in h.calls if c[0] == "text"])
    check("hourly cap enforced", n == cp.MAX_LINES_PER_HOUR, str(n))
    check("cap hit sends ONE Telegram notice", len(notes) == 1 and "cap" in notes[0])
    held = [f"Cap{i}" for i in range(cp.MAX_LINES_PER_HOUR, cp.MAX_LINES_PER_HOUR + 2)]
    check("capped alerts stay PENDING (not dropped)",
          [e["alertname"] for e in p.pending] == held, str([e["alertname"] for e in p.pending]))
    check("cap notice NAMES the held alert(s)", held[0] in notes[0], notes[0])
    check("NEG: held alerts are not marked delivered",
          all(cp.alert_key(evt(name=x)) not in p.seen for x in held))
    clk.t += 3600
    r = p.tick()
    last = [c for c in h.calls if c[0] == "text"][-1][2]
    check("after the hour the held alerts are TYPED with the held-back count",
          r == "typed" and all(x in last for x in held) and "2 of them held back" in last, last)


def test_not_deliverable():
    for key in ("busy-spinner", "busy-bg-agents", "menu-question", "menu-permission",
                "menu-resume-list", "idle-draft", "exhausted-unclear"):
        p, h, clk, notes = mk(key)
        p.submit(evt())
        clk.t += cp.COALESCE_S + 1
        r = p.tick()
        check(f"NEG: {key} -> nothing typed (not even ctrl+u), retried", not typed(h)
              and r.startswith("retry") and not notes, r)
    for key in ("exhausted-idle", "exhausted-draft", "exhausted-busy"):
        p, h, clk, notes = mk(key)
        p.submit(evt())
        clk.t += cp.COALESCE_S + 1
        r = p.tick()
        check(f"NEG: {key} -> not typed, one Telegram notice", not typed(h) and r == "notified"
              and len(notes) == 1, r)

    p, h, clk, notes = mk("busy-spinner")
    p.submit(evt())
    clk.t += cp.COALESCE_S + 1
    waits = []
    while clk.t < 1000 + cp.COALESCE_S + 1 + cp.DEADLINE_S + 400 and not notes:
        r = p.tick()
        waits.append(r)
        clk.t += 5
    check("busy -> retries then ONE Telegram notice after the deadline",
          len(notes) == 1 and not typed(h) and any(w.startswith("retry") for w in waits), str(waits[-3:]))
    for _ in range(30):
        clk.t += 60
        p.tick()
    check("NEG: no repeat notice / no typing after giving up", len(notes) == 1 and not typed(h))

    p, h, clk, notes = mk("busy-spinner")
    p.submit(evt())
    clk.t += cp.COALESCE_S + 1
    p.tick()
    h.screen_key = "idle"
    clk.t += 20
    check("busy then idle within the deadline -> typed, no Telegram", p.tick() == "typed" and not notes)


def test_notify_failure_keeps_batch():
    """Regression (2026-10-26): notify() returns False under launchd (no token) and
    _give_up() dropped the batch anyway -- 41 batches lost, logged as 'gave up'."""
    ok, logs = [False], []
    p, h, clk, notes = mk("exhausted-idle", notify_ok=ok, logs=logs)
    p.submit(evt())
    clk.t += cp.COALESCE_S + 1
    r = p.tick()
    check("notify False -> batch KEPT pending", r == "notify-failed" and len(p.pending) == 1, r)
    check("notify False -> logged as ERROR naming the alert",
          any(m.startswith("ERROR") and "FooDown" in m for m in logs), str(logs))
    check("NEG: notify False -> alert NOT recorded as delivered", not p.seen)
    check("NEG: no 'gave up' claim when nothing was delivered",
          not any("gave up" in m for m in logs))
    clk.t += 5
    check("failed notice is not hammered every tick", p.tick() == "wait")
    ok[0] = True
    clk.t += cp.NOTIFY_RETRY_S
    r = p.tick()
    check("notify recovers -> notice sent, batch cleared", r == "notified" and not p.pending
          and len(notes) == 1 and "FooDown" in notes[0], r)
    check("delivered (notified) alert is now deduped", p.submit(evt()) is False)

    # busy past the deadline with a broken notifier, then the pane frees up:
    # the kept batch is TYPED -- nothing was lost.
    ok, logs = [False], []
    p, h, clk, notes = mk("busy-spinner", notify_ok=ok, logs=logs)
    p.submit(evt())
    clk.t += cp.COALESCE_S + 1
    rs = []
    while clk.t < 1000 + cp.COALESCE_S + 1 + cp.DEADLINE_S + 400:
        rs.append(p.tick())
        clk.t += 5
    check("busy past deadline + notify False -> still pending", "notify-failed" in rs
          and len(p.pending) == 1, str(rs[-3:]))
    h.screen_key = "idle"
    clk.t += cp.NOTIFY_RETRY_S
    check("...and typed once the pane is idle", p.tick() == "typed" and not p.pending)

    # notify raising is treated the same as False
    logs = []
    clk = Clock()
    p = cp.Pusher(FakeHarness("exhausted-busy"), notify=lambda m: 1 / 0, clock=clk,
                  sleep=clk.sleep, log=logs.append)
    p.submit(evt())
    clk.t += cp.COALESCE_S + 1
    check("notify raising -> batch kept", p.tick() == "notify-failed" and len(p.pending) == 1)


def test_exhausted_unclear_retries():
    p, h, clk, notes = mk("exhausted-unclear")
    p.submit(evt())
    clk.t += cp.COALESCE_S + 1
    rs = []
    while clk.t < 1000 + cp.COALESCE_S + 1 + cp.DEADLINE_S + 400 and not notes:
        rs.append(p.tick())
        clk.t += 5
    check("exhausted-unclear -> retried like busy, notice only after the deadline",
          rs[0] == "retry:exhausted-unclear" and len(notes) == 1 and not typed(h)
          and clk.t >= 1000 + cp.COALESCE_S + cp.DEADLINE_S, str(rs[:2]))
    p, h, clk, notes = mk("exhausted-unclear")
    p.submit(evt())
    clk.t += cp.COALESCE_S + 1
    p.tick()
    h.screen_key = "idle"
    clk.t += 20
    check("exhausted-unclear then idle -> typed, no Telegram", p.tick() == "typed" and not notes)


def test_dedupe_after_delivery():
    p, h, clk, notes = mk("busy-spinner")
    check("queued", p.submit(evt()) is True)
    check("NEG: queueing alone records nothing for dedupe", not p.seen)
    clk.t += cp.COALESCE_S + 1
    p.tick()
    check("NEG: a retry records nothing for dedupe", not p.seen)
    check("re-fire while pending is merged, not duplicated",
          p.submit(evt()) is False and len(p.pending) == 1)
    h.screen_key = "idle"
    clk.t += 60
    check("typed", p.tick() == "typed")
    check("typed alert recorded for dedupe", cp.alert_key(evt()) in p.seen)
    clk.t += 60
    check("NEG: delivered alert re-firing is deduped", p.submit(evt()) is False)


def test_enter_guard():
    # long batch -> wraps over several rows; the re-read must still confirm it
    p, h, clk, notes = mk()
    for i in range(5):
        p.submit(evt(name=f"LongAlertName{i}", summary="s" * 60))
    clk.t += cp.COALESCE_S + 1
    check("wrapped multi-row input line confirmed -> Enter", p.tick() == "typed"
          and typed(h)[-1][2] == "enter")
    line = [c for c in h.calls if c[0] == "text"][-1][2]
    check("pane_input_text joins the soft-wrapped rows",
          cp._squash(cp.pane_input_text(input_pane(line))) == cp._squash(line))

    for label, mut in (("operator appended text", lambda t: t + " also check x"),
                       ("operator typed before it", lambda t: "yes " + t),
                       ("input replaced", lambda t: "do #4 next")):
        logs = []
        p, h, clk, notes = mk(logs=logs)
        h.mutate = mut
        p.submit(evt())
        clk.t += cp.COALESCE_S + 1
        r = p.tick()
        check(f"NEG: {label} -> Enter NOT pressed", not [c for c in h.calls if c[0] == "key"]
              and r == "retry:aborted", r)
        check(f"NEG: {label} -> not recorded as delivered, logged ERROR", p.pending and not p.seen
              and not p.typed and any(m.startswith("ERROR") and "Enter NOT pressed" in m for m in logs))

    # slow render: the first re-read shows only a prefix -> keep polling, then Enter
    p, h, clk, notes = mk()
    seen = {"n": 0}

    def slow(t):
        seen["n"] += 1
        return t[:40] if seen["n"] == 1 else t
    h.mutate = slow
    p.submit(evt())
    clk.t += cp.COALESCE_S + 1
    check("partial render then full -> Enter", p.tick() == "typed" and typed(h)[-1][2] == "enter")
    calls = [c[0] for c in h.calls]
    check("the screen is re-read AFTER typing and right before Enter",
          calls[-3:] == ["screen", "screen", "key"] and calls.index("text") < len(calls) - 2,
          str(calls))


def test_startup_selftest():
    with tempfile.TemporaryDirectory() as td:
        stamp, logs, t = Path(td) / "stamp", [], [5000.0]
        r = cp.startup_selftest(logs.append, notify=lambda m: False, stamp=stamp,
                                min_gap_s=3600, now=lambda: t[0])
        check("startup notify False -> 'failed' + ERROR logged, no stamp",
              r == "failed" and any(m.startswith("ERROR") for m in logs) and not stamp.exists())
        sent = []
        r = cp.startup_selftest(logs.append, notify=lambda m: sent.append(m) or True,
                                stamp=stamp, min_gap_s=3600, now=lambda: t[0])
        check("startup notify OK -> 'ok', one message, OK logged", r == "ok" and len(sent) == 1
              and any("startup notification OK" in m for m in logs))
        check("NEG: startup message carries no token-like secret", "bot" not in sent[0].lower())
        t[0] += 60
        r = cp.startup_selftest(logs.append, notify=lambda m: sent.append(m) or True,
                                stamp=stamp, min_gap_s=3600, now=lambda: t[0])
        check("crash-loop respawn within the gap -> skipped, no second page",
              r == "skipped" and len(sent) == 1)


def test_identity_and_dry_run():
    p, h, clk, notes = mk(sessions=[{"session_id": "X", "path": "/Users/mu/other-repo"}])
    p.submit(evt())
    clk.t += cp.COALESCE_S + 1
    check("NEG: pane outside the ops repo -> nothing typed", p.tick().startswith("retry") and not typed(h))
    p, h, clk, notes = mk(sessions=[{"session_id": "A", "path": cp.REPO},
                                    {"session_id": "B", "path": cp.REPO + "/x"}])
    p.submit(evt())
    clk.t += cp.COALESCE_S + 1
    check("NEG: ambiguous (2 panes) -> nothing typed", p.tick().startswith("retry") and not typed(h))
    p, h, clk, notes = mk(sessions=[])
    p.submit(evt())
    clk.t += cp.COALESCE_S + 1
    check("NEG: no pane -> nothing typed", not typed(h))

    logs = []
    clk = Clock()
    h = FakeHarness("idle")
    p = cp.Pusher(h, notify=lambda m: None, clock=clk, sleep=clk.sleep, dry_run=True, log=logs.append)
    p.submit(evt())
    clk.t += cp.COALESCE_S + 1
    check("dry-run: prints the line, types nothing",
          p.tick() == "typed" and not typed(h) and any("would type" in m for m in logs))


def main() -> int:
    print("test-console-push")
    test_classifier()
    test_pin()
    test_filter_and_line()
    test_delivery()
    test_not_deliverable()
    test_notify_failure_keeps_batch()
    test_exhausted_unclear_retries()
    test_dedupe_after_delivery()
    test_enter_guard()
    test_startup_selftest()
    test_identity_and_dry_run()
    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all console-push tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
