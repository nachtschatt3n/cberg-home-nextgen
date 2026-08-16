"""Unit tests for tier-based notification routing (notify.route_finding).

Proves the Phase-2 routing contract WITHOUT sending a real page: notify() and
ingest_or_notify() are monkeypatched to CAPTURE calls, so the test asserts the
decision — urgent=True is fired for CRITICAL only, HIGH surfaces non-urgently,
MEDIUM/LOW never notify.

Run:  python3 runbooks/lib/test_notify_routing.py
  or: python3 -m pytest runbooks/lib/test_notify_routing.py -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "notify", str(Path(__file__).with_name("notify.py")))
nt = importlib.util.module_from_spec(_spec)
sys.modules["notify"] = nt
_spec.loader.exec_module(nt)


# ── capture harness: never touches the network / Telegram ────────────────────
_calls: list[dict] = []


def _install_capture():
    _calls.clear()

    def fake_notify(text, *, urgent=False):
        _calls.append({"fn": "notify", "urgent": urgent, "text": text})
        return True

    def fake_ingest_or_notify(payload, *, fallback_text, urgent=False):
        _calls.append({"fn": "ingest_or_notify", "urgent": urgent,
                       "payload": payload})
        return "openclaw"

    nt.notify = fake_notify
    nt.ingest_or_notify = fake_ingest_or_notify


# ── decision-only (dry_run) proof — the core verification bar ────────────────

def test_dry_run_urgent_only_for_critical():
    _install_capture()
    urgent_by_tier = {}
    for tier in ("critical", "high", "medium", "low"):
        d = nt.route_finding(tier, text=f"{tier} finding", dry_run=True)
        urgent_by_tier[tier] = d.urgent
    assert urgent_by_tier == {"critical": True, "high": False,
                              "medium": False, "low": False}, urgent_by_tier
    # dry-run must NOT send anything
    assert _calls == [], _calls


def test_will_send_matrix():
    for tier, expect in (("critical", True), ("high", True),
                         ("medium", False), ("low", False)):
        d = nt.route_finding(tier, text="x", dry_run=True)
        assert d.will_send is expect, (tier, d)


# ── live-send proof (captured, no real page) — urgent fires for critical only ─

def test_live_send_critical_pages_urgent():
    _install_capture()
    d = nt.route_finding("critical", text="ext+exploited", dry_run=False)
    assert d.sent is True and d.transport == "notify"
    assert len(_calls) == 1
    assert _calls[0]["fn"] == "notify" and _calls[0]["urgent"] is True


def test_live_send_high_is_non_urgent_briefing():
    _install_capture()
    d = nt.route_finding("high", text="ext, not exploited", dry_run=False)
    assert d.sent is True
    assert len(_calls) == 1 and _calls[0]["urgent"] is False


def test_live_send_high_with_payload_uses_ingest():
    _install_capture()
    d = nt.route_finding("high", text="fallback",
                         payload={"key": "F-x", "kind": "security"}, dry_run=False)
    assert d.transport == "ingest_or_notify"
    assert _calls[0]["fn"] == "ingest_or_notify" and _calls[0]["urgent"] is False


def test_live_send_medium_low_never_notify():
    _install_capture()
    for tier in ("medium", "low"):
        d = nt.route_finding(tier, text="internal / policy", dry_run=False)
        assert d.sent is False and d.will_send is False
    assert _calls == [], _calls


def test_unknown_tier_never_pages():
    _install_capture()
    d = nt.route_finding("bogus", text="?", dry_run=False)
    assert d.urgent is False and d.sent is False
    assert _calls == [], _calls


# ── tiny runner so `python3 test_notify_routing.py` works without pytest ──────

if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
