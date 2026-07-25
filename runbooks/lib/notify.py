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


def notify(text: str, *, urgent: bool = False) -> bool:
    """Send `text` to the operator channel. Returns True on success."""
    token = _bot_token()
    if not token:
        print("notify: no Telegram bot token available — skipping", file=sys.stderr)
        return False
    payload = json.dumps({
        "chat_id": _chat_id(),
        "text": text,
        "parse_mode": "Markdown",
        "disable_notification": not urgent,  # urgent → audible push
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ok = json.loads(r.read().decode() or "{}").get("ok", False)
            if not ok:
                print("notify: Telegram API returned ok=false", file=sys.stderr)
            return bool(ok)
    except Exception as e:
        print(f"notify: send failed ({e})", file=sys.stderr)
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
