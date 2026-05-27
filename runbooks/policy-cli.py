#!/usr/bin/env python3
"""policy-cli — operator interface for sweep_history policy tables.

Edits the four operator-curated policy tables (accepted_risks,
slo_definitions, noise_suppressions, security_acceptances) that
replaced the four git-tracked source files during the 2026-05-27
policy-in-DB migration.

Auto-port-forwards postgresql + decodes the WRITER_DSN secret — same
mechanic as runbooks/sweep-run.py. Use sweep_writer DSN (DML only, no
DDL).

Usage examples:

  # Accepted risks
  policy-cli risk list
  policy-cli risk show AR-001
  policy-cli risk add AR-028 --description 'New risk' --severity informational \\
                              --justification 'why we accept it'
  policy-cli risk review AR-001         # bumps last_reviewed_at to now
  policy-cli risk disable AR-001        # soft-disable (enabled=false)
  policy-cli risk delete AR-001         # hard delete

  # SLO definitions
  policy-cli slo list
  policy-cli slo show NAME
  policy-cli slo add NAME --source prom --target 0.99 --window 30d \\
                          --numerator 'sum(up{job=...})' --denominator 'count(up{job=...})' \\
                          [--tag pilot --tag storage]
  policy-cli slo disable NAME
  policy-cli slo delete NAME

  # Noise suppressions
  policy-cli noise list [--category X]
  policy-cli noise add --category flaky_iot_devices --match-key name \\
                       --match-value 'Soil sensor 3' --note 'WiFi flap'
  policy-cli noise add --category known_ha_error_sources --match-key integration \\
                       --match-value miele --threshold 100 --note 'upstream'
  policy-cli noise disable <id>
  policy-cli noise delete <id>

  # Security acceptances
  policy-cli sec list [--category X]
  policy-cli sec add --category git_history_cred --pattern 'ROT|placeholder' --note 'ROTATED'
  policy-cli sec add --category external_ingress_accepted --pattern 'flux-webhook' --ar-id AR-012
  policy-cli sec disable <id>
  policy-cli sec delete <id>

  # Cross-table
  policy-cli stats                          # row counts per table
  policy-cli export [--out path/]           # snapshot DB → flat-files for backup
"""
from __future__ import annotations

import argparse
import base64
import datetime as _dt
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent.resolve()


def _activate_mise() -> None:
    if os.environ.get("_MISE_ACTIVATED"):
        return
    repo_root = SCRIPT_DIR.parent
    if not (repo_root / ".mise.toml").is_file():
        return
    mise = next(
        (Path(p) / "mise" for p in os.environ.get("PATH", "").split(os.pathsep)
         if (Path(p) / "mise").is_file()),
        None,
    )
    if not mise:
        return
    os.environ["_MISE_ACTIVATED"] = "1"
    os.execvp(str(mise), [str(mise), "-C", str(repo_root), "exec", "--",
                          sys.executable, *sys.argv])


_activate_mise()


# ---------------------------------------------------------------------------
# Port-forward + DSN derivation (mirrors sweep-run.py)
# ---------------------------------------------------------------------------


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _kubectl_secret_dsn() -> str | None:
    try:
        out = subprocess.check_output(
            ["kubectl", "get", "secret", "-n", "databases", "sweep-history",
             "-o", "json"],
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    try:
        return base64.b64decode(json.loads(out)["data"]["WRITER_DSN"]).decode()
    except (KeyError, json.JSONDecodeError):
        return None


def _start_pf(ns: str, svc: str, local: int, remote: int) -> subprocess.Popen:
    pf = subprocess.Popen(
        ["kubectl", "port-forward", "-n", ns, f"svc/{svc}", f"{local}:{remote}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid if os.name != "nt" else None,
    )
    deadline = time.time() + 6
    while time.time() < deadline:
        with socket.socket() as s:
            try:
                s.settimeout(0.4)
                s.connect(("127.0.0.1", local))
                return pf
            except OSError:
                time.sleep(0.2)
    pf.terminate()
    raise SystemExit(f"port-forward {svc}:{remote} timed out")


def _stop(pf: subprocess.Popen | None) -> None:
    if pf is None:
        return
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(pf.pid), signal.SIGTERM)
        else:
            pf.terminate()
    except (ProcessLookupError, PermissionError):
        pass


def _resolve_dsn(explicit: str | None) -> tuple[str, subprocess.Popen | None]:
    """Return (dsn, port_forward_handle_to_stop_later)."""
    dsn = explicit or os.environ.get("SWEEP_PG_DSN")
    if dsn:
        return dsn, None
    port = _free_port()
    pf = _start_pf("databases", "postgresql", port, 5432)
    raw = _kubectl_secret_dsn()
    if not raw:
        _stop(pf)
        raise SystemExit("could not decode sweep-history WRITER_DSN")
    fqdn = "@postgresql." + "databases.svc.cluster.local:5432"
    return raw.replace(fqdn, f"@127.0.0.1:{port}"), pf


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _connect(dsn: str):
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(dsn, row_factory=dict_row, autocommit=False)


def _print_table(rows: list[dict], cols: list[tuple[str, str, int]]) -> None:
    """cols = list of (column_key, header, width)."""
    if not rows:
        print("(no rows)")
        return
    header = "  ".join(h.ljust(w) for _, h, w in cols)
    print(header)
    print("-" * len(header))
    for r in rows:
        line = []
        for key, _, w in cols:
            v = r.get(key)
            if v is None:
                s = ""
            elif isinstance(v, bool):
                s = "✓" if v else "✗"
            elif isinstance(v, _dt.datetime):
                s = v.strftime("%Y-%m-%d")
            elif isinstance(v, list):
                s = ",".join(str(x) for x in v)
            else:
                s = str(v)
            line.append(s[:w].ljust(w) if w > 0 else s)
        print("  ".join(line))


# ---- risk ----

def cmd_risk_list(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        where, params = "WHERE 1=1", []
        if args.severity:
            where += " AND severity = %s"
            params.append(args.severity)
        cur.execute(
            f"SELECT ar_id, severity, status, enabled, description, last_reviewed_at "
            f"FROM accepted_risks {where} ORDER BY ar_id", params
        )
        _print_table(cur.fetchall(), [
            ("ar_id", "AR ID", 8),
            ("severity", "Severity", 14),
            ("status", "Status", 10),
            ("enabled", "On", 3),
            ("last_reviewed_at", "Reviewed", 10),
            ("description", "Description", 60),
        ])


def cmd_risk_show(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM accepted_risks WHERE ar_id = %s", (args.ar_id,))
        row = cur.fetchone()
        if not row:
            print(f"AR {args.ar_id} not found", file=sys.stderr); return 1
        for k, v in row.items():
            print(f"  {k:18s}  {v}")


def cmd_risk_add(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO accepted_risks (ar_id, severity, description, justification) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (ar_id) DO NOTHING",
            (args.ar_id, args.severity, args.description, args.justification),
        )
        if cur.rowcount == 0:
            print(f"AR {args.ar_id} already exists — use `risk delete` first or rename")
            return 1
        conn.commit()
        print(f"added {args.ar_id}")


def cmd_risk_review(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE accepted_risks SET last_reviewed_at = now() WHERE ar_id = %s",
            (args.ar_id,),
        )
        if cur.rowcount == 0:
            print(f"AR {args.ar_id} not found", file=sys.stderr); return 1
        conn.commit()
        print(f"reviewed {args.ar_id}")


def cmd_risk_disable(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE accepted_risks SET enabled = false WHERE ar_id = %s",
            (args.ar_id,),
        )
        if cur.rowcount == 0:
            print(f"AR {args.ar_id} not found", file=sys.stderr); return 1
        conn.commit()
        print(f"disabled {args.ar_id}")


def cmd_risk_delete(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM accepted_risks WHERE ar_id = %s", (args.ar_id,))
        if cur.rowcount == 0:
            print(f"AR {args.ar_id} not found", file=sys.stderr); return 1
        conn.commit()
        print(f"deleted {args.ar_id}")


# ---- slo ----

def cmd_slo_list(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT name, source, target, window_size, enabled, tags "
            "FROM slo_definitions ORDER BY name"
        )
        rows = []
        for r in cur.fetchall():
            r["target"] = f"{float(r['target']) * 100:.2f}%"
            rows.append(r)
        _print_table(rows, [
            ("name", "Name", 32),
            ("source", "Source", 8),
            ("target", "Target", 8),
            ("window_size", "Window", 8),
            ("enabled", "On", 3),
            ("tags", "Tags", 30),
        ])


def cmd_slo_show(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM slo_definitions WHERE name = %s", (args.name,))
        row = cur.fetchone()
        if not row:
            print(f"SLO {args.name} not found", file=sys.stderr); return 1
        for k, v in row.items():
            if isinstance(v, dict):
                v = json.dumps(v, indent=2)
            print(f"  {k:18s}  {v}")


def cmd_slo_add(args, dsn):
    query_json = {"numerator": args.numerator, "denominator": args.denominator}
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO slo_definitions (name, description, source, kind, "
            "target, window_size, query_json, tags) "
            "VALUES (%s, %s, %s, 'ratio', %s, %s, %s::jsonb, %s) "
            "ON CONFLICT (name) DO NOTHING",
            (args.name, args.description or "", args.source,
             args.target, args.window, json.dumps(query_json), args.tag or []),
        )
        if cur.rowcount == 0:
            print(f"SLO {args.name} already exists — use `slo delete` first")
            return 1
        conn.commit()
        print(f"added {args.name}")


def cmd_slo_disable(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE slo_definitions SET enabled = false, updated_at = now() "
            "WHERE name = %s", (args.name,),
        )
        if cur.rowcount == 0:
            print(f"SLO {args.name} not found", file=sys.stderr); return 1
        conn.commit()
        print(f"disabled {args.name}")


def cmd_slo_delete(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM slo_definitions WHERE name = %s", (args.name,))
        if cur.rowcount == 0:
            print(f"SLO {args.name} not found", file=sys.stderr); return 1
        conn.commit()
        print(f"deleted {args.name}")


# ---- noise ----

def cmd_noise_list(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        where, params = "WHERE 1=1", []
        if args.category:
            where += " AND category = %s"
            params.append(args.category)
        cur.execute(
            f"SELECT id, category, match_key, match_value, threshold, enabled, note "
            f"FROM noise_suppressions {where} ORDER BY category, id", params
        )
        _print_table(cur.fetchall(), [
            ("id", "ID", 5),
            ("category", "Category", 32),
            ("match_key", "Key", 14),
            ("match_value", "Value", 30),
            ("threshold", "Thr", 6),
            ("enabled", "On", 3),
            ("note", "Note", 40),
        ])


def cmd_noise_add(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO noise_suppressions (category, match_key, match_value, "
            "threshold, note) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (args.category, args.match_key, args.match_value,
             args.threshold, args.note),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        print(f"added noise suppression #{new_id}")


def cmd_noise_disable(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("UPDATE noise_suppressions SET enabled = false WHERE id = %s", (args.id,))
        if cur.rowcount == 0:
            print(f"noise #{args.id} not found", file=sys.stderr); return 1
        conn.commit()
        print(f"disabled noise #{args.id}")


def cmd_noise_delete(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM noise_suppressions WHERE id = %s", (args.id,))
        if cur.rowcount == 0:
            print(f"noise #{args.id} not found", file=sys.stderr); return 1
        conn.commit()
        print(f"deleted noise #{args.id}")


# ---- sec ----

def cmd_sec_list(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        where, params = "WHERE 1=1", []
        if args.category:
            where += " AND category = %s"
            params.append(args.category)
        cur.execute(
            f"SELECT id, category, pattern, note, ar_id, enabled "
            f"FROM security_acceptances {where} ORDER BY category, id", params
        )
        _print_table(cur.fetchall(), [
            ("id", "ID", 5),
            ("category", "Category", 28),
            ("pattern", "Pattern", 50),
            ("ar_id", "AR", 8),
            ("enabled", "On", 3),
            ("note", "Note", 40),
        ])


def cmd_sec_add(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO security_acceptances (category, pattern, note, ar_id) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (args.category, args.pattern, args.note, args.ar_id),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        print(f"added sec acceptance #{new_id}")


def cmd_sec_disable(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("UPDATE security_acceptances SET enabled = false WHERE id = %s", (args.id,))
        if cur.rowcount == 0:
            print(f"sec #{args.id} not found", file=sys.stderr); return 1
        conn.commit()
        print(f"disabled sec #{args.id}")


def cmd_sec_delete(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM security_acceptances WHERE id = %s", (args.id,))
        if cur.rowcount == 0:
            print(f"sec #{args.id} not found", file=sys.stderr); return 1
        conn.commit()
        print(f"deleted sec #{args.id}")


# ---- cross-table ----

def cmd_stats(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        for table in ("accepted_risks", "slo_definitions",
                      "noise_suppressions", "security_acceptances"):
            cur.execute(
                f"SELECT COUNT(*) AS total, "
                f"SUM(CASE WHEN enabled THEN 1 ELSE 0 END) AS enabled FROM {table}"
            )
            r = cur.fetchone()
            print(f"  {table:24s}  total={r['total']:>4}  enabled={int(r['enabled'] or 0):>4}")


def cmd_export(args, dsn):
    """Snapshot all 4 tables to flat files for backup / inspection."""
    out_dir = Path(args.out or "policy-export")
    out_dir.mkdir(parents=True, exist_ok=True)
    import yaml as _yaml
    with _connect(dsn) as conn, conn.cursor() as cur:
        for table in ("accepted_risks", "slo_definitions",
                      "noise_suppressions", "security_acceptances"):
            cur.execute(f"SELECT * FROM {table} ORDER BY 1")
            rows = []
            for r in cur.fetchall():
                # Convert datetimes + Decimals to strings/floats for YAML
                for k, v in list(r.items()):
                    if isinstance(v, _dt.datetime):
                        r[k] = v.isoformat()
                    elif hasattr(v, "__float__"):
                        try: r[k] = float(v)
                        except Exception: r[k] = str(v)
                rows.append(dict(r))
            path = out_dir / f"{table}.yaml"
            path.write_text(_yaml.safe_dump(rows, sort_keys=False, allow_unicode=True))
            print(f"  wrote {len(rows):>3} rows → {path}")


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Operator policy CLI for sweep_history.")
    p.add_argument("--postgres-dsn", default=None,
                   help="DSN override; otherwise port-forwards postgresql.")
    sub = p.add_subparsers(dest="cmd", required=True)

    # risk
    risk = sub.add_parser("risk", help="accepted_risks table").add_subparsers(dest="op", required=True)
    rl = risk.add_parser("list");  rl.add_argument("--severity")
    rl.set_defaults(handler=cmd_risk_list)
    rs = risk.add_parser("show");  rs.add_argument("ar_id")
    rs.set_defaults(handler=cmd_risk_show)
    ra = risk.add_parser("add")
    ra.add_argument("ar_id")
    ra.add_argument("--description", required=True)
    ra.add_argument("--severity", default="informational")
    ra.add_argument("--justification")
    ra.set_defaults(handler=cmd_risk_add)
    rv = risk.add_parser("review"); rv.add_argument("ar_id")
    rv.set_defaults(handler=cmd_risk_review)
    rd = risk.add_parser("disable"); rd.add_argument("ar_id")
    rd.set_defaults(handler=cmd_risk_disable)
    rD = risk.add_parser("delete"); rD.add_argument("ar_id")
    rD.set_defaults(handler=cmd_risk_delete)

    # slo
    slo = sub.add_parser("slo", help="slo_definitions table").add_subparsers(dest="op", required=True)
    sl = slo.add_parser("list");  sl.set_defaults(handler=cmd_slo_list)
    ss = slo.add_parser("show");  ss.add_argument("name");  ss.set_defaults(handler=cmd_slo_show)
    sa = slo.add_parser("add")
    sa.add_argument("name")
    sa.add_argument("--source", choices=["prom", "es", "hactl"], default="prom")
    sa.add_argument("--target", type=float, required=True)
    sa.add_argument("--window", required=True)
    sa.add_argument("--numerator", required=True)
    sa.add_argument("--denominator", required=True)
    sa.add_argument("--description")
    sa.add_argument("--tag", action="append")
    sa.set_defaults(handler=cmd_slo_add)
    sd = slo.add_parser("disable"); sd.add_argument("name"); sd.set_defaults(handler=cmd_slo_disable)
    sD = slo.add_parser("delete"); sD.add_argument("name"); sD.set_defaults(handler=cmd_slo_delete)

    # noise
    noise = sub.add_parser("noise", help="noise_suppressions table").add_subparsers(dest="op", required=True)
    nl = noise.add_parser("list"); nl.add_argument("--category"); nl.set_defaults(handler=cmd_noise_list)
    na = noise.add_parser("add")
    na.add_argument("--category", required=True)
    na.add_argument("--match-key")
    na.add_argument("--match-value", required=True)
    na.add_argument("--threshold", type=int)
    na.add_argument("--note")
    na.set_defaults(handler=cmd_noise_add)
    nd = noise.add_parser("disable"); nd.add_argument("id", type=int); nd.set_defaults(handler=cmd_noise_disable)
    nD = noise.add_parser("delete"); nD.add_argument("id", type=int); nD.set_defaults(handler=cmd_noise_delete)

    # sec
    sec = sub.add_parser("sec", help="security_acceptances table").add_subparsers(dest="op", required=True)
    secl = sec.add_parser("list"); secl.add_argument("--category"); secl.set_defaults(handler=cmd_sec_list)
    seca = sec.add_parser("add")
    seca.add_argument("--category", required=True,
                      choices=["git_history_cred", "git_history_secret_file",
                               "external_ingress_accepted"])
    seca.add_argument("--pattern", required=True)
    seca.add_argument("--note")
    seca.add_argument("--ar-id")
    seca.set_defaults(handler=cmd_sec_add)
    secd = sec.add_parser("disable"); secd.add_argument("id", type=int); secd.set_defaults(handler=cmd_sec_disable)
    secD = sec.add_parser("delete"); secD.add_argument("id", type=int); secD.set_defaults(handler=cmd_sec_delete)

    # cross-table
    sub.add_parser("stats").set_defaults(handler=cmd_stats)
    exp = sub.add_parser("export"); exp.add_argument("--out"); exp.set_defaults(handler=cmd_export)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    dsn, pf = _resolve_dsn(args.postgres_dsn)
    try:
        return args.handler(args, dsn) or 0
    finally:
        _stop(pf)


if __name__ == "__main__":
    sys.exit(main())
