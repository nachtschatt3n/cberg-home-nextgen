"""Regression tests for home-operation's reminder digest (2026-10-02).

The operator got 116 one-issue-per-message Telegram pushes in 48h — 24
REBUILD reminders inside one minute at 23:55, go/no-go reminders at 04:25 —
and Juno could not map a bare "Approve" to an issue. Pinned here:

  * a tick sends ONE digest for every due non-critical issue, numbered;
  * non-critical reminders inside quiet hours (21:30-07:30 Europe/Berlin)
    are held to the quiet-hours end and nothing is pushed;
  * critical issues still push immediately, individually, even at night;
  * `decide --issue 2` resolves against the LAST digest; with no digest on
    record a number matches nothing (never guesses);
  * an issue offering only defer/deny refuses approve (exit 5) and records
    nothing (app-template-5.2.1 re-plan item).

home-operation ships SOPS-encrypted in the openclaw skills configmap, so this
decrypts it like test-openclaw-run-now-skill.py; no age key -> loud SKIP.

Run:  python3 runbooks/tests/test-home-operation-digest.py
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIGMAP = REPO / "kubernetes/apps/ai/openclaw/app/skills-configmap.sops.yaml"
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def load_hop(state_dir: Path):
    if not shutil.which("sops"):
        return None, "sops binary not found"
    r = subprocess.run(["sops", "-d", "--extract", '["data"]["home-operation.py"]', str(CONFIGMAP)],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return None, f"sops could not decrypt home-operation.py: {r.stderr.strip()[:160]}"
    src = state_dir / "home_operation.py"
    src.write_text(r.stdout)
    os.environ["HOME_OP_STATE_DIR"] = str(state_dir)
    spec = importlib.util.spec_from_file_location("home_operation", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, None


def at(hop, y, mo, d, hh, mm):
    """Freeze hop.now() at a Europe/Berlin wall-clock time."""
    t = datetime(y, mo, d, hh, mm, tzinfo=hop.LOCAL_TZ).astimezone(timezone.utc)
    hop.now = lambda: t
    return t


def issue(hop, key, severity="warning", action="approve,deny,defer", needs=1,
          component=None, title=None, window=None):
    c = hop.db()
    c.execute("INSERT OR REPLACE INTO issues(key,kind,severity,title,component,window,action,"
              "needs_decision,status,reminder_count,next_remind_at,opened_at) "
              "VALUES(?,?,?,?,?,?,?,?,'open',0,'2026-01-01T00:00:00Z','2026-10-01T00:00:00Z')",
              (key, "go_no_go" if needs else "finding", severity, title or f"GO/NO-GO: {key}",
               component or key, window, action, needs))
    c.commit()


def tick(hop):
    sent = []
    hop._push = lambda text, urgent=False, dry=False: sent.append((text, urgent)) or True
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        hop.cmd_tick(argparse.Namespace(no_push=False, json_out=True))
    return sent, json.loads(out.getvalue())


def decide(hop, needle, decision):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = hop.cmd_decide(argparse.Namespace(issue=needle, decision=decision, until=None,
                                               note="", by="test", json_out=True))
    return rc or 0, out.getvalue()


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        hop, skip = load_hop(Path(td))
        if hop is None:
            print(f"SKIP test-home-operation-digest: {skip}")
            return 0
        issue(hop, "n8n-2.39.8", component="n8n", window="sat-attended:2026-10-17")
        issue(hop, "app-template-5.2.1", action="defer,deny", component="app-template",
              title="app-template-5.2.1 deferred: premise FAILING - re-plan needed")
        for i in range(5):
            issue(hop, f"rebuild:img{i}", action="ack", needs=0, component=f"img{i}",
                  title=f"REBUILD: img{i}")

        at(hop, 2026, 10, 1, 23, 55)
        sent, res = tick(hop)
        check("quiet hours: nothing pushed at 23:55 Berlin", sent == [], str(sent))
        check("quiet hours: all 7 held", len(res["held_quiet_hours"]) == 7, str(res))
        nxt = hop.db().execute("SELECT next_remind_at FROM issues WHERE key='n8n-2.39.8'").fetchone()[0]
        check("quiet hours: held to 07:30 Berlin (05:30Z in October)",
              nxt == "2026-10-02T05:30:00Z", nxt)

        at(hop, 2026, 10, 2, 7, 31)
        sent, res = tick(hop)
        check("digest: exactly one message for 7 due issues", len(sent) == 1, str(len(sent)))
        text = sent[0][0] if sent else ""
        check("digest: not urgent", sent and sent[0][1] is False)
        check("digest: defer/deny-only item is labelled", "[deny/defer only]" in text, text)
        check("digest: 5 rebuilds collapse into one line", "5× REBUILD" in text
              and text.count("REBUILD: img") == 0, text)
        check("digest: every issue counted as reminded", len(res["reminded"]) == 7, str(res))

        nums = json.loads(Path(td, "last-digest.json").read_text())["numbers"]
        n8n = next(k for k, v in nums.items() if v == "n8n-2.39.8")
        apt = next(k for k, v in nums.items() if v == "app-template-5.2.1")
        check("digest: the number shown is the number recorded",
              f"\n{n8n}. n8n-2.39.8" in text, text)
        rc, out = decide(hop, apt, "approve")
        check("guard: approve on a defer/deny-only item exits 5", rc == 5, f"{rc} {out}")
        row = hop.db().execute("SELECT decision FROM issues WHERE key='app-template-5.2.1'").fetchone()
        check("guard: nothing recorded", row[0] is None, str(row[0]))
        rc, out = decide(hop, n8n, "approve")
        row = hop.db().execute("SELECT decision FROM issues WHERE key='n8n-2.39.8'").fetchone()
        check("numbers: `decide --issue <n>` approves the digest's item",
              rc == 0 and row[0] == "approve", f"{rc} {out}")
        rc, out = decide(hop, "99", "approve")
        check("numbers: an unknown number matches nothing", rc == 3, f"{rc} {out}")

        Path(td, "last-digest.json").unlink()
        rc, out = decide(hop, "1", "defer")
        check("numbers: no digest on record -> no match, no guess", rc == 3, f"{rc} {out}")

        issue(hop, "auto-update-revert-x", severity="critical", action="ack", needs=0,
              title="REVERTED: batch x")
        at(hop, 2026, 10, 3, 2, 0)
        sent, res = tick(hop)
        check("critical: pushes at 02:00 Berlin, urgent, on its own",
              len(sent) == 1 and sent[0][1] is True and "REVERTED" in sent[0][0], str(sent))

    print(f"\n{'FAILED' if FAILURES else 'OK'}: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
