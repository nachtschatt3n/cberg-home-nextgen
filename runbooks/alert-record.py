#!/usr/bin/env python3
"""alert-record.py — persist a SURFACE'd alert as a finding + OpenClaw issue (P4.1.2).

Why: the alert-triage-agent's most valuable output (SURFACE — "this alert is
real, here's why, here's who owns it") was its least durable. It existed as
prose in a session report; if nobody read that session, the analysis was
gone, and the alert had no owner, no SLA and no reminder — the same
"no owner, sits and re-fires" shape the finding-triage lanes were built to
kill. This script gives a SURFACE verdict the same substrate every other
piece of work has: a `sweep_findings` row (fingerprint = alert identity, so
4-hourly Alertmanager re-fires dedupe onto ONE row) plus a `home-operation`
issue keyed on the finding id (source "alert").

The ad-hoc cycle semantics of FindingsWriter are exactly right here: the
writer mints its own cycle and auto-closes nothing — an alert writer must
never conclude anything about other findings.

Usage (invoked by the alert-triage-agent):
    # on SURFACE:
    alert-record.py --alertname ContainerMemoryLeakPredicted \\
        --namespace home-automation --severity warning \\
        --why "real leak ~19MiB/h, OOM ETA ~40h, no owner" \\
        --owner ha-agent [--instance-key <discriminator>] [--pod <pod>]
    # on the Alertmanager resolve event (same identity args):
    alert-record.py --alertname ... --namespace ... [--instance-key ...] --resolved

--instance-key: alert identity here is (alertname, namespace, instance-key).
Pass a discriminator when one alertname covers many subjects (KumaMonitorDown
fires per monitor — pass the monitor name). Pod names are NOT identity (they
churn on restart); pass --pod for the record only.

DSN: uses $SWEEP_PG_DSN when set; otherwise self-resolves exactly like
runbooks/lib/sweep-pg-dsn.sh — guaranteed-free local port (NEVER 5432: the
Mac runs a local postgres that would silently shadow the cluster db) and a
to_regclass('public.sweep_findings') sanity check before any write.

Fail direction: DB unreachable → exit 2 after a raw-Telegram fallback note,
never a silent success. The OpenClaw ingest failing alone is exit 2 too —
the finding row still exists, but the reminder does not, and the caller must
say so in its report.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import notify  # noqa: E402
from lib.findings_writer import FindingsWriter, fingerprint, finding_id_from_fp  # noqa: E402

SECTION = "alert"


def make_title(alertname: str, namespace: str, instance_key: str | None) -> str:
    """Stable identity title — no pod, no severity, no free-text summary."""
    t = f"Alert {alertname} firing in {namespace}"
    if instance_key:
        t += f" [{instance_key}]"
    return t


def identity(alertname: str, namespace: str, instance_key: str | None):
    title = make_title(alertname, namespace, instance_key)
    fp = fingerprint(SECTION, alertname, title)
    return title, fp, finding_id_from_fp(fp)


# ── DSN self-resolution (mirrors runbooks/lib/sweep-pg-dsn.sh) ───────────────

def _free_port() -> int:
    while True:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        if port != 5432:          # never squat the Mac's local postgres port
            return port


def _self_dsn():
    """Returns (dsn, port_forward_popen|None). Raises on failure."""
    if os.environ.get("SWEEP_PG_DSN"):
        return os.environ["SWEEP_PG_DSN"], None
    raw = subprocess.check_output(
        ["kubectl", "get", "secret", "-n", "databases", "sweep-history",
         "-o", "jsonpath={.data.WRITER_DSN}"], text=True, timeout=30)
    dsn_raw = base64.b64decode(raw).decode()
    port = _free_port()
    pf = subprocess.Popen(
        ["kubectl", "port-forward", "-n", "databases", "svc/postgresql",
         f"{port}:5432"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid if os.name != "nt" else None)
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), 0.3).close()
            break
        except OSError:
            time.sleep(0.2)
    dsn = dsn_raw.replace("@postgresql.databases.svc.cluster.local:5432",
                          f"@127.0.0.1:{port}")
    # sanity: the CLUSTER db, not a local shadow
    import psycopg
    with psycopg.connect(dsn, connect_timeout=5) as c, c.cursor() as cur:
        cur.execute("select to_regclass('public.sweep_findings') is not null")
        if not cur.fetchone()[0]:
            _stop_pf(pf)
            raise RuntimeError("DSN did not reach the cluster sweep_history db")
    return dsn, pf


def _stop_pf(pf) -> None:
    if pf is None:
        return
    try:
        os.killpg(os.getpgid(pf.pid), signal.SIGTERM)
    except Exception:
        pf.terminate()


# ── record / resolve ─────────────────────────────────────────────────────────

def record(args, dsn) -> tuple[str, bool]:
    title, fp, fid = identity(args.alertname, args.namespace, args.instance_key)
    action = f"SURFACE'd by alert-triage: {args.why or 'no rationale given'}"
    if args.owner:
        action += f" — owner: {args.owner}"
    w = FindingsWriter(dsn=dsn, section=SECTION, trigger="alert")
    try:
        emitted = w.emit(
            args.severity, title,
            action=action,
            subsection=args.alertname,
            metadata={"alertname": args.alertname, "namespace": args.namespace,
                      "pod": args.pod, "instance_key": args.instance_key,
                      "owner": args.owner, "source": "alert-bridge"})
    finally:
        w.close()
    assert emitted == fid, f"finding id drifted: {emitted} != {fid}"
    issue = {
        "key": fid,
        "kind": "finding",
        "source": "alert",
        "severity": args.severity,
        "title": f"ALERT {args.alertname} ns={args.namespace}"
                 + (f" [{args.instance_key}]" if args.instance_key else "")
                 + f" — {(args.why or '')[:120]}",
        "component": args.owner,
        "action": "ack",
        "detail": args.why,
    }
    ok = notify.ingest_issue(issue)
    return fid, ok


def resolve(args, dsn) -> tuple[str, bool]:
    _, fp, fid = identity(args.alertname, args.namespace, args.instance_key)
    import psycopg
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE sweep_findings
                  SET resolved_at = now(), status = 'resolved'
                WHERE fingerprint = %s AND resolved_at IS NULL
            RETURNING finding_id""", (fp,))
        rows = cur.fetchall()
        conn.commit()
    # closing the reminder is best-effort; the DB row is the record
    p = subprocess.run(notify._HOME_OP_EXEC
                       + ["resolve", "--issue", fid, "--by", "cleared",
                          "--note", "alert resolved in Alertmanager"],
                       capture_output=True, text=True, timeout=60)
    return fid, bool(rows) and p.returncode == 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--alertname", required=True)
    ap.add_argument("--namespace", required=True)
    ap.add_argument("--instance-key", default=None,
                    help="discriminator when one alertname covers many subjects")
    ap.add_argument("--pod", default=None, help="for the record; NOT identity")
    ap.add_argument("--severity", default="warning",
                    choices=["warning", "critical"])
    ap.add_argument("--why", default=None, help="triage evidence, one line")
    ap.add_argument("--owner", default=None,
                    help="owning agent named by triage (ha-agent, cberg-agent, …)")
    ap.add_argument("--resolved", action="store_true",
                    help="close the finding + reminder (same identity args)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print identity + payload, write nothing")
    args = ap.parse_args(argv)

    title, fp, fid = identity(args.alertname, args.namespace, args.instance_key)
    if args.dry_run:
        print(json.dumps({"dry_run": True, "title": title, "fingerprint": fp,
                          "finding_id": fid,
                          "mode": "resolve" if args.resolved else "record"},
                         indent=1))
        return 0

    pf = None
    try:
        dsn, pf = _self_dsn()
    except Exception as e:
        notify.notify(f"🔔 alert-record: DB unreachable — alert "
                      f"{args.alertname} ns={args.namespace} NOT persisted ({e})")
        print(f"alert-record: DSN resolution failed: {e}", file=sys.stderr)
        return 2

    try:
        if args.resolved:
            fid, ok = resolve(args, dsn)
            print(json.dumps({"resolved": fid, "clean": ok}))
        else:
            fid, ok = record(args, dsn)
            print(json.dumps({"recorded": fid, "reminder": ok}))
        return 0 if ok else 2
    finally:
        _stop_pf(pf)


if __name__ == "__main__":
    sys.exit(main())
