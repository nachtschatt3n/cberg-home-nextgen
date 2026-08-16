#!/usr/bin/env python3
"""notify — reach the operator's phone via the existing Telegram bot.

Used whenever an unattended process needs the operator to KNOW or DECIDE
something that a sweep-DB finding alone wouldn't surface in time:
  * maintenance-window-agent: a go/no-go decision is needed, or a plan blocked
  * auto-update: a batch was auto-reverted after a bad merge

Reuses the same bot + channel Alertmanager already pages to, so it lands on the
phone regardless of whether any Claude session is being watched.

Credentials (no new secret committed):
  * bot token — env TELEGRAM_BOT_TOKEN, else `sops -d` the kube-prometheus-stack
    secret (key `bot-token`) on the Mac (local age key required).
  * chat id   — env OPERATOR_TELEGRAM_CHAT, else parsed from the committed
    AlertmanagerConfig, else the home-operation channel default.

Fail-soft: if anything is unavailable it prints a warning and returns False —
a notification failure must never crash the caller.

Usage:
    python3 runbooks/lib/notify.py "message text"          # shell / agent
    python3 runbooks/lib/notify.py --urgent "decide now"   # silent=false ping
    from runbooks.lib.notify import notify; notify("...", urgent=True)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SECRET = REPO_ROOT / "kubernetes/apps/monitoring/kube-prometheus-stack/app/secret.sops.yaml"
_AMCFG = REPO_ROOT / "kubernetes/apps/monitoring/kube-prometheus-stack/app/alertmanager-telegram-config.yaml"
_DEFAULT_CHAT = "-1003112342088"  # home-operation channel (already in the AM config)


def _bot_token():
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if tok:
        return tok.strip()
    try:
        out = subprocess.run(["sops", "-d", str(_SECRET)], capture_output=True,
                             text=True, timeout=30)
        if out.returncode != 0:
            return None
        import yaml
        d = yaml.safe_load(out.stdout) or {}
        sd = d.get("stringData") or {}
        if "bot-token" in sd:
            return str(sd["bot-token"]).strip()
        data = d.get("data") or {}
        if "bot-token" in data:
            import base64
            return base64.b64decode(data["bot-token"]).decode().strip()
    except Exception:
        return None
    return None


def _chat_id():
    cid = os.environ.get("OPERATOR_TELEGRAM_CHAT")
    if cid:
        return cid.strip()
    try:
        m = re.search(r"chatID:\s*(-?\d+)", _AMCFG.read_text())
        if m:
            return m.group(1)
    except Exception:
        pass
    return _DEFAULT_CHAT


def _post(token: str, payload_dict: dict) -> bool:
    """POST one sendMessage payload; return Telegram's `ok`. Raises on HTTP error."""
    payload = json.dumps(payload_dict).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return bool(json.loads(r.read().decode() or "{}").get("ok", False))


def notify(text: str, *, urgent: bool = False) -> bool:
    """Send `text` to the operator channel. Returns True on success.

    Sends as legacy Markdown (nice formatting when the body is valid Markdown),
    but transparently RETRIES AS PLAIN TEXT if Telegram rejects it with HTTP 400.
    Operational messages carry arbitrary technical strings (paths, version tags,
    `needs_reboot`) whose stray `_`/`*`/`` ` `` would otherwise trip the Markdown
    parser and silently drop the alert — the plain-text retry guarantees delivery.
    """
    token = _bot_token()
    if not token:
        print("notify: no Telegram bot token available — skipping", file=sys.stderr)
        return False
    base = {
        "chat_id": _chat_id(),
        "text": text,
        "disable_notification": not urgent,  # urgent → audible push
        "disable_web_page_preview": True,
    }
    # Attempt 1 — Markdown.
    try:
        if _post(token, {**base, "parse_mode": "Markdown"}):
            return True
        print("notify: Telegram ok=false with Markdown — retrying as plain text", file=sys.stderr)
    except urllib.error.HTTPError as e:
        if e.code != 400:
            print(f"notify: send failed ({e})", file=sys.stderr)
            return False
        print("notify: Telegram HTTP 400 (Markdown parse) — retrying as plain text", file=sys.stderr)
    except Exception as e:
        print(f"notify: send failed ({e})", file=sys.stderr)
        return False
    # Attempt 2 — plain text (no parse_mode); never trips a formatting parser.
    try:
        ok = _post(token, base)
        if not ok:
            print("notify: Telegram API returned ok=false (plain text)", file=sys.stderr)
        return ok
    except Exception as e:
        print(f"notify: plain-text send failed ({e})", file=sys.stderr)
        return False


# ── OpenClaw home-operation contract ─────────────────────────────────────────
# Since 2026-07-25 OpenClaw OWNS the open-issue + reminder + decision lifecycle
# (skill `home-operation`, see docs/sops/maintenance-windows.md). Emitters route
# issues to it via `kubectl exec` into the openclaw pod; this raw Telegram send
# is only the FALLBACK for when that pod is unreachable, so an alert is never
# lost. Contract owner: the openclaw-agent.
_HOME_OP_EXEC = [
    "kubectl", "-n", "ai", "exec", "deploy/openclaw", "-c", "app", "--",
    "/home/node/.openclaw/bin/home-operation",
]


def ingest_issue(payload) -> bool:
    """UPSERT one issue (or a list) into OpenClaw's home-operation store.
    `payload` follows the contract: key (plan_id|finding_id), kind, source,
    severity, title, action, + optional context. Returns True on rc 0."""
    try:
        p = subprocess.run(_HOME_OP_EXEC + ["ingest", "--json", json.dumps(payload)],
                           capture_output=True, text=True, timeout=60)
        return p.returncode == 0
    except Exception as e:
        print(f"notify: home-operation ingest failed ({e})", file=sys.stderr)
        return False


def ingest_or_notify(payload, *, fallback_text: str, urgent: bool = False) -> str:
    """Primary path: hand the issue to OpenClaw (it notifies + reminds + tracks).
    Fallback: if the pod is unreachable, send a raw Telegram so nothing is lost.
    Returns 'openclaw' or 'notify-fallback'."""
    if ingest_issue(payload):
        return "openclaw"
    notify(fallback_text, urgent=urgent)
    return "notify-fallback"


# ── Tier-based routing (Phase 2 of the contextual-risk redesign) ─────────────
# The operator's rule, stated verbatim: bother them as little as possible —
# only an external-unauth + exploited-in-the-wild finding (a CONTEXTUAL
# CRITICAL) should ever interrupt. Every other tier is surfaced WITHOUT a page.
#
#   CRITICAL → urgent=True   audible push. The ONLY tier that interrupts.
#   HIGH     → urgent=False  briefing (surfaced, not paged).
#   MEDIUM   → no notification (maintenance-window queue / dashboard).
#   LOW      → no notification (dashboard / weekly batch).
from dataclasses import dataclass

# tier → (channel, urgent, will_send). `will_send` is whether the tier notifies
# at ALL; `urgent` is the audible-push flag passed to notify()/ingest_or_notify().
_TIER_ROUTES: dict[str, tuple[str, bool, bool]] = {
    "critical": ("notify-urgent",     True,  True),
    "high":     ("briefing",          False, True),
    "medium":   ("maintenance-queue", False, False),
    "low":      ("dashboard",         False, False),
}
# Unknown/unscored tier: surface non-urgently rather than drop it, but never
# page. (Should not happen — every scored finding carries one of the four.)
_TIER_ROUTE_DEFAULT = ("dashboard", False, False)


@dataclass
class RouteDecision:
    """What routing WOULD do (and did, unless dry_run) for one scored finding."""
    tier: str
    channel: str
    urgent: bool          # the flag that WOULD be passed to notify() — True only for critical
    will_send: bool       # does this tier notify at all?
    sent: bool            # was a send actually attempted? (False on dry_run or a no-send tier)
    transport: str        # 'ingest_or_notify' | 'notify' | 'none' | 'dry-run'


def route_finding(tier: str, *, text: str, payload=None, dry_run: bool = False) -> RouteDecision:
    """Route ONE scored finding by its contextual tier.

    Pure decision + optional side-effect. Returns a RouteDecision describing the
    routing regardless of dry_run, so callers can prove the decision without
    paging. Only tier=='critical' ever sets urgent=True; medium/low never send.

    `payload` (the home-operation issue dict) routes via ingest_or_notify so
    OpenClaw owns the reminder/decision lifecycle; without one we fall back to a
    raw notify(text). A no-send tier ignores both.
    """
    channel, urgent, will_send = _TIER_ROUTES.get(
        (tier or "").lower(), _TIER_ROUTE_DEFAULT)

    if not will_send:
        return RouteDecision(tier=tier, channel=channel, urgent=urgent,
                             will_send=False, sent=False, transport="none")
    if dry_run:
        return RouteDecision(tier=tier, channel=channel, urgent=urgent,
                             will_send=True, sent=False, transport="dry-run")

    if payload is not None:
        ingest_or_notify(payload, fallback_text=text, urgent=urgent)
        transport = "ingest_or_notify"
    else:
        notify(text, urgent=urgent)
        transport = "notify"
    return RouteDecision(tier=tier, channel=channel, urgent=urgent,
                         will_send=True, sent=True, transport=transport)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    urgent = False
    if args and args[0] == "--urgent":
        urgent = True
        args = args[1:]
    if not args:
        print("usage: notify.py [--urgent] <message>", file=sys.stderr)
        return 2
    return 0 if notify(" ".join(args), urgent=urgent) else 1


if __name__ == "__main__":
    sys.exit(main())
