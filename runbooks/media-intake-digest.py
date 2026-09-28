#!/usr/bin/env python3
"""media-intake-digest.py — daily summary of the automatic media intake,
delivered to the operator through the OpenClaw briefing (NOT Telegram).

Why a Mac-side script: the in-cluster watcher (CronJob media/
media-intake-watcher) would need `pods/exec` into the OpenClaw pod to call
home-operation, which is far more privilege than a file mover should hold.
Instead the watcher pushes gauges to prometheus-pushgateway and this script,
run once a day from the nightly maintenance-window close-out, reads them
through the API-server service proxy and ingests ONE ack-only issue:

    key       media-intake-<YYYY-MM-DD>
    kind      window_warning      source maintenance      severity info
    action    ack

Per the IT-ops-only alert rule, failures/stale-ambiguous items page through
Alertmanager (media-intake-alerts.yaml); this digest is the business summary
("12 moved, 2 duplicates, 1 replaced, 1 left ambiguous (youtube)").

ORDER: the maintenance source is reconciled against PLAN ids by
openclaw-sync.py, so ingest this AFTER that reconcile (same rule as the
morning report) or it is auto-closed seconds after it is created.

Privacy: the gauges carry counts and reason codes only — no titles.

Usage:
    python3 runbooks/media-intake-digest.py            # ingest
    python3 runbooks/media-intake-digest.py --dry-run  # print the payload
Exit: 0 ok / nothing-to-report, 2 ingest failed or metrics unreadable.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PROXY = "/api/v1/namespaces/monitoring/services/prometheus-pushgateway:9091/proxy/metrics"
LINE = re.compile(r'^(media_intake_[a-z0-9_]+)(?:\{([^}]*)\})?\s+(\S+)$')


def parse(text: str) -> dict:
    """{metric: {frozenset(labels): value}} for media_intake_* only."""
    out: dict = {}
    for ln in text.splitlines():
        m = LINE.match(ln)
        if not m:
            continue
        labels = dict(re.findall(r'(\w+)="([^"]*)"', m.group(2) or ""))
        if labels.get("job") not in (None, "media-intake-watcher"):
            continue
        labels.pop("job", None)
        labels.pop("instance", None)
        out.setdefault(m.group(1), {})[tuple(sorted(labels.items()))] = float(m.group(3))
    return out


def get(metrics, name, **labels):
    return metrics.get(name, {}).get(tuple(sorted(labels.items())), 0.0)


def build(metrics: dict, today: str) -> dict | None:
    if "media_intake_items" not in metrics:
        return None
    a = {k: int(get(metrics, "media_intake_actions_24h", action=k))
         for k in ("moved", "duplicate", "replaced", "cleaned", "failed")}
    amb = int(get(metrics, "media_intake_items", state="ambiguous"))
    pend = int(get(metrics, "media_intake_items", state="pending"))
    failed = int(get(metrics, "media_intake_items", state="failed"))
    reasons = sorted((dict(k).get("reason"), int(v))
                     for k, v in metrics.get("media_intake_ambiguous_items", {}).items()
                     if v and dict(k).get("reason") not in (None, "none"))
    apply_on = bool(get(metrics, "media_intake_apply_enabled"))
    title = (f"Media intake 24h: {a['moved']} sorted, {a['duplicate']} duplicate(s), "
             f"{a['replaced']} replaced; {amb} ambiguous, {failed} failed")
    detail = (f"24h actions: {json.dumps(a, sort_keys=True)}. "
              f"Now in intake: ambiguous={amb} pending={pend} failed={failed}. "
              f"Ambiguous reasons: {', '.join(f'{r}={n}' for r, n in reasons) or 'none'}. "
              f"Apply {'ON' if apply_on else 'OFF (kill switch INTAKE_APPLY=0)'}. "
              "Displaced copies are in <Section>/_duplicates/ (nothing deleted).")
    return {"key": f"media-intake-{today}", "kind": "window_warning",
            "source": "maintenance", "severity": "info" if not failed else "warning",
            "action": "ack", "component": "media-intake", "title": title,
            "detail": detail}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        raw = subprocess.run(["kubectl", "get", "--raw", PROXY], capture_output=True,
                             text=True, timeout=60, check=True).stdout
    except Exception as e:
        print(f"media-intake-digest: cannot read pushgateway ({type(e).__name__})", file=sys.stderr)
        return 2
    payload = build(parse(raw), datetime.date.today().isoformat())
    if payload is None:
        print("media-intake-digest: no media_intake_* series (watcher never ran?)", file=sys.stderr)
        return 2
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0
    from lib import notify
    if not notify.ingest_issue(payload):
        print("media-intake-digest: home-operation ingest FAILED", file=sys.stderr)
        return 2
    print(f"media-intake-digest: ingested {payload['key']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
