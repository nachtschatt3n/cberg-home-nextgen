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
    selector = "ai-server-ops"

    def __init__(self, screen="idle", sessions=None):
        self.screen_key = screen
        self.sess = sessions if sessions is not None else [
            {"session_id": "SID-1", "path": cp.REPO}]
        self.calls = []

    def sessions(self):
        return self.sess

    def screen(self, sid, limit=40):
        self.calls.append(("screen", sid))
        return S[self.screen_key]

    def send_text(self, sid, text):
        self.calls.append(("text", sid, text))

    def send_key(self, sid, key):
        self.calls.append(("key", sid, key))


def evt(name="FooDown", sev="warning", status="firing", ns="apps", pod="foo-1", summary="foo is down"):
    return {"source": "alertmanager", "status": status, "severity": sev, "alertname": name,
            "namespace": ns, "pod": pod, "instance": "", "summary": summary}


def mk(screen="idle", **kw):
    clk, notes = Clock(), []
    h = FakeHarness(screen, kw.pop("sessions", None))
    p = cp.Pusher(h, notify=notes.append, clock=clk, sleep=clk.sleep, log=lambda m: None, **kw)
    return p, h, clk, notes


def typed(h):
    return [c for c in h.calls if c[0] in ("text", "key")]


def test_pin():
    err = dl.decrypt_into(Path(tempfile.mkdtemp()))
    if err:
        print(f"  SKIP  classifier pin vs OpenClaw skills: {err}")
        return
    d = Path(tempfile.mkdtemp())
    dl.decrypt_into(d)
    orig = dl.shared_block((d / "operation.py").read_text())
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
    check("hold-back count is reported", "+3 more" in big)


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
          and "4 alerts" in h.calls[-2][2])

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


def test_not_deliverable():
    for key in ("busy-spinner", "busy-bg-agents", "menu-question", "menu-permission",
                "menu-resume-list", "idle-draft"):
        p, h, clk, notes = mk(key)
        p.submit(evt())
        clk.t += cp.COALESCE_S + 1
        r = p.tick()
        check(f"NEG: {key} -> nothing typed (not even ctrl+u)", not typed(h) and r.startswith("retry"), r)
    for key in ("exhausted-idle", "exhausted-draft", "exhausted-busy", "exhausted-unclear"):
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
