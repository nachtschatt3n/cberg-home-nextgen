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
  policy-cli risk edit AR-047 --description 'openclaw: image node'
  policy-cli risk lint                  # descriptions that will drift out of matching
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

  # Findings (vulnerability detail — DB-only, never committed; see
  # docs/sops/vulnerability-disclosure.md)
  policy-cli finding list --section security --grep ingress-nginx
  policy-cli finding show F-35f34061          # incl. the private security_detail
  policy-cli finding ref  F-35f34061          # publish-safe block for a plan file
  policy-cli finding detail F-35f34061 --plan ingress-nginx-1.15.6 \\
                                       --detail-file /tmp/detail.md
  policy-cli finding add --title 'absenty: image rebuild required' \\
                         --plan absenty-rebuild --detail-file /tmp/detail.md

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
import re
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


# An AR's `description` is used as a SUBSTRING needle against open finding
# titles (see _apply_ar_suppression in sweep-run.py). A needle that pins a
# PATCH-level version therefore stops matching the moment the underlying
# component drifts one patch — the suppression silently lapses and the
# finding re-surfaces as an unsuppressed duplicate. Operator memory
# `project_sweep_ar_version_drift` records this exact failure (AR-030
# pinned "→ 5.0.0"; the target moved to 5.0.1). Descriptions must be
# DRIFT-STABLE: name the component, not the patch.
_DRIFT_PIN_RE = re.compile(r"\b\d+\.\d+\.\d+")          # x.y.z anywhere
_DRIFT_COUNT_RE = re.compile(r"\b\d+\s+(?:HIGH|CRITICAL|devices?|CVEs?)\b", re.I)


def _drift_warnings(desc: str) -> list:
    """Reasons `desc` is not drift-stable. Empty list = stable."""
    out = []
    if _DRIFT_PIN_RE.search(desc or ""):
        out.append("contains a patch-level version (x.y.z) — drifts on the next patch bump")
    if _DRIFT_COUNT_RE.search(desc or ""):
        out.append("contains a volatile COUNT (CVE/device tally) — drifts on every rescan")
    return out


def cmd_risk_edit(args, dsn):
    """Update an existing AR in place. This is the sanctioned way to make a
    description drift-stable without delete+re-add (which loses accepted_at).
    """
    sets, params = [], []
    for col in ("description", "severity", "justification"):
        val = getattr(args, col, None)
        if val is not None:
            sets.append(f"{col} = %s")
            params.append(val)
    if not sets:
        print("nothing to change — pass at least one of "
              "--description/--severity/--justification", file=sys.stderr)
        return 1
    if args.description is not None:
        warn = _drift_warnings(args.description)
        if warn and not args.allow_drift:
            print(f"REFUSING: proposed description is not drift-stable:", file=sys.stderr)
            for w in warn:
                print(f"  - {w}", file=sys.stderr)
            print("  (see operator memory project_sweep_ar_version_drift; "
                  "pass --allow-drift to override)", file=sys.stderr)
            return 2
    sets.append("last_reviewed_at = now()")
    params.append(args.ar_id)
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT description FROM accepted_risks WHERE ar_id = %s", (args.ar_id,))
        row = cur.fetchone()
        if not row:
            print(f"AR {args.ar_id} not found", file=sys.stderr); return 1
        before = row["description"]
        cur.execute(
            f"UPDATE accepted_risks SET {', '.join(sets)} WHERE ar_id = %s", params)
        conn.commit()
    print(f"edited {args.ar_id}")
    if args.description is not None:
        print(f"  description: {before!r}")
        print(f"           -> {args.description!r}")
    return 0


def _near_miss(cur, desc: str):
    """Empirical drift probe for a description that matches NOTHING.

    Progressively drops trailing whitespace-separated tokens from the needle
    and re-tests. If a SHORTER prefix of the description matches an open
    finding, the AR is not merely quiet — the tail of its description (the
    version/count that drifted) is what stopped it matching. Returns
    (surviving_prefix, finding_id, finding_title) or None.

    This is the check that a static "does it contain x.y.z" rule cannot make:
    AR-047 pinned `node 22-bookworm` (no patch digit at all, so statically
    clean) yet stopped matching the moment the pin moved to 22.23.2-bookworm.
    """
    toks = (desc or "").strip().split()
    for cut in range(len(toks) - 1, 1, -1):
        prefix = " ".join(toks[:cut])
        cur.execute(
            "SELECT finding_id, title FROM sweep_findings "
            "WHERE resolved_at IS NULL AND position(%s in lower(title)) > 0 "
            "ORDER BY last_seen DESC LIMIT 1",
            (prefix.lower(),))
        row = cur.fetchone()
        if row:
            return prefix, row["finding_id"], row["title"]
    return None


def cmd_risk_lint(args, dsn):
    """Report ARs whose description has stopped (or will stop) matching.

    Two independent signals:
      STATIC  — the description embeds a patch-level version or a volatile
                count, so it WILL drift out of matching on the next bump.
      DRIFTING NOW — the description matches zero open findings, but a
                shorter PREFIX of it does. That is proof the tail drifted.
    """
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT ar_id, description FROM accepted_risks "
            "WHERE enabled = true AND status = 'accepted' ORDER BY ar_id")
        ars = [(r["ar_id"], r["description"]) for r in cur.fetchall()]
        rows = []
        for ar_id, desc in ars:
            warn = _drift_warnings(desc or "")
            cur.execute(
                "SELECT count(*) AS n FROM sweep_findings "
                "WHERE resolved_at IS NULL AND position(%s in lower(title)) > 0",
                ((desc or "").strip().lower(),))
            matches = cur.fetchone()["n"]
            miss = _near_miss(cur, desc) if matches == 0 else None
            if warn or miss or args.all:
                rows.append((ar_id, desc, matches, warn, miss))
    if not rows:
        print("all enabled AR descriptions are drift-stable and matching")
        return 0
    print(f"{'AR':<8} {'open-match':>10}  description")
    for ar_id, desc, matches, warn, miss in rows:
        if miss:
            flag = "DRIFTING NOW"
        elif warn:
            flag = "at risk"
        else:
            flag = "ok"
        print(f"{ar_id:<8} {matches:>10}  {desc!r}  [{flag}]")
        for w in warn:
            print(f"{'':<21}! {w}")
        if miss:
            prefix, fid, title = miss
            print(f"{'':<21}! description matches 0 open findings, but the prefix "
                  f"{prefix!r} matches {fid}:")
            print(f"{'':<23}{title[:100]}")
    return 0


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


def cmd_slo_update(args, dsn):
    """Patch an existing SLO in place, preserving every field not passed.

    Editing the query (numerator/denominator) is the common case — e.g. fixing
    a `sum`-over-replicas numerator that can exceed 1.0 during a rollout to a
    bounded `max(...)` form — without losing the row's description, tags,
    burn-rate windows or created_at (which a delete+add would reset).
    """
    sets, params = [], []
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT query_json FROM slo_definitions WHERE name = %s", (args.name,))
        row = cur.fetchone()
        if not row:
            print(f"SLO {args.name} not found", file=sys.stderr); return 1
        if args.numerator is not None or args.denominator is not None:
            q = dict(row["query_json"] or {})
            if args.numerator is not None:
                q["numerator"] = args.numerator
            if args.denominator is not None:
                q["denominator"] = args.denominator
            sets.append("query_json = %s::jsonb"); params.append(json.dumps(q))
        if args.target is not None:
            sets.append("target = %s"); params.append(args.target)
        if args.window is not None:
            sets.append("window_size = %s"); params.append(args.window)
        if args.description is not None:
            sets.append("description = %s"); params.append(args.description)
        if not sets:
            print("nothing to update — pass --numerator/--denominator/--target/"
                  "--window/--description", file=sys.stderr)
            return 1
        sets.append("updated_at = now()")
        params.append(args.name)
        cur.execute(
            f"UPDATE slo_definitions SET {', '.join(sets)} WHERE name = %s", params,
        )
        conn.commit()
        print(f"updated {args.name}: {', '.join(s.split(' = ')[0] for s in sets)}")


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


# ---- finding (sweep_findings: vulnerability detail lives HERE, not in git) ----
#
# Public-repo rule (docs/sops/vulnerability-disclosure.md): CVE IDs, per-image
# vulnerability counts, exploitability notes and exposure detail must NOT be
# committed to this repo. They belong on the sweep_findings row, which is
# private (cluster-internal Postgres + authenticated dashboard). A maintenance
# plan cites the finding_id; `finding ref` prints the block to paste.
#
# Severity note: use `deferred` (or `monitor`) for hand-authored plan drivers.
# `critical`/`warning` feed sweep-run.py's verdict reconciliation and a
# hand-written row in a section the sweep never re-runs would pin the cycle
# verdict red forever (it is also never auto-closed — auto-close only touches
# sections that reported in the cycle).

_PLAN_SECTION = "plan"


def _finding_fingerprint(section: str, subsection: str | None, title: str) -> tuple[str, str]:
    """(fingerprint, finding_id) using the same contract as lib/findings_writer."""
    sys.path.insert(0, str(SCRIPT_DIR / "lib"))
    import findings_writer as fw  # noqa: PLC0415
    fp = fw.fingerprint(section, subsection, title)
    return fp, fw.finding_id_from_fp(fp)


def _finding_row(cur, finding_id: str):
    """Resolve a finding by id, falling back to its historical ids.

    `finding_id` is derived from the fingerprint, so any change to the identity
    function renames rows (the 2026-08-18 AR-independent-fingerprint migration
    renamed 179). Committed `security_ref: F-xxxxxxxx` lines and plan files are
    immutable, so the old id has to keep resolving or every reference in git
    history silently rots. `runbooks/refingerprint-findings.py` records the old
    ids in `metadata.prior_finding_ids`; this is the read side of that.

    Current id wins; a prior id only resolves when nothing owns it today.
    """
    # A LIVE row always beats a dead one, whether it is reached by the current
    # id or by an alias. Exact-then-alias alone is not enough: a superseded row
    # KEEPS its finding_id when it is resolved, so an exact match can return a
    # closed stub while the keeper that inherited its alias is open. That
    # matters because this function feeds `finding detail`, which WRITES the
    # private vulnerability payload to `row["id"]` — attaching it to a stub
    # loses it from the live register with no error.
    for open_only in (True, False):
        clause = " AND resolved_at IS NULL" if open_only else ""
        for by_alias in (False, True):
            pred = ("metadata->'prior_finding_ids' ? %s" if by_alias
                    else "finding_id = %s")
            cur.execute(
                f"SELECT * FROM sweep_findings WHERE {pred}{clause} "
                f"ORDER BY last_seen DESC LIMIT 1",
                (finding_id,),
            )
            row = cur.fetchone()
            if row is None:
                continue
            if row["finding_id"] != finding_id:
                print(f"note: {finding_id} was renamed to {row['finding_id']} "
                      f"(fingerprint migration); showing the current row.",
                      file=sys.stderr)
            return row
    return None


def _ref_block(row: dict) -> str:
    """The canonical, publish-safe reference to paste into a plan file."""
    plans = (row.get("metadata") or {}).get("plans") or []
    return (
        f"> **Security driver — detail withheld from this public repo.**\n"
        f"> Tracked as **{row['finding_id']}** "
        f"(`{row['section']}` / severity `{row['severity']}`).\n"
        f"> Full detail (CVE IDs, counts, exposure, exploitability) lives on the\n"
        f"> finding record — it is deliberately not reproduced here.\n"
        f">\n"
        f"> - Dashboard: `https://sweep.<DOMAIN>/findings/{row['finding_id']}`\n"
        f"> - CLI: `runbooks/policy-cli.py finding show {row['finding_id']}`\n"
        + (f"> - Plans: {', '.join(plans)}\n" if plans else "")
        + f">\n"
        f"> See `docs/sops/vulnerability-disclosure.md` before adding any\n"
        f"> vulnerability detail to a committed file."
    )


def cmd_finding_list(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        where, params = ["1=1"], []
        if not args.all:
            where.append("resolved_at IS NULL")
        if args.section:
            where.append("section = %s"); params.append(args.section)
        if args.severity:
            where.append("severity = %s"); params.append(args.severity)
        if args.grep:
            where.append("title ILIKE %s"); params.append(f"%{args.grep}%")
        params.append(args.limit)
        cur.execute(
            "SELECT finding_id, section, severity, status, last_seen, title "
            f"FROM sweep_findings WHERE {' AND '.join(where)} "
            "ORDER BY last_seen DESC LIMIT %s", params
        )
        _print_table(cur.fetchall(), [
            ("finding_id", "Finding", 10),
            ("section", "Section", 9),
            ("severity", "Severity", 9),
            ("status", "Status", 9),
            ("last_seen", "Last seen", 10),
            ("title", "Title", 90),
        ])


def cmd_finding_show(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        row = _finding_row(cur, args.finding_id)
        if not row:
            print(f"finding {args.finding_id} not found", file=sys.stderr); return 1
        meta = row.get("metadata") or {}
        for k, v in row.items():
            if k == "metadata":
                continue
            print(f"  {k:16s}  {v}")
        detail = meta.pop("security_detail", None)
        if meta:
            print(f"  {'metadata':16s}  {json.dumps(meta, ensure_ascii=False)}")
        if detail:
            print("\n  --- security_detail (DO NOT COPY INTO A COMMITTED FILE) ---")
            for line in str(detail).splitlines():
                print(f"  {line}")


def cmd_finding_ref(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        row = _finding_row(cur, args.finding_id)
        if not row:
            print(f"finding {args.finding_id} not found", file=sys.stderr); return 1
        print(_ref_block(row))


def _read_detail(args) -> str | None:
    if args.detail_file:
        return Path(args.detail_file).read_text()
    return args.detail


def _policy_cli_cycle(cur) -> str:
    """Find-or-create the single sentinel sweep_cycles row that hand-authored
    findings hang off. sweep_findings.cycle_id has an FK to sweep_cycles, and a
    real sweep cycle would be a lie about provenance; one reused sentinel keeps
    the cycle list uncluttered."""
    cur.execute(
        "SELECT cycle_id FROM sweep_cycles WHERE trigger = 'policy-cli' "
        "ORDER BY started_at LIMIT 1"
    )
    row = cur.fetchone()
    if row:
        return str(row["cycle_id"])
    cur.execute(
        "INSERT INTO sweep_cycles (cycle_id, started_at, finished_at, trigger, notes) "
        "VALUES (gen_random_uuid(), now(), now(), 'policy-cli', %s) RETURNING cycle_id",
        ("Sentinel cycle for hand-authored findings created via policy-cli "
         "finding add. Not a real sweep run.",),
    )
    return str(cur.fetchone()["cycle_id"])


def cmd_finding_add(args, dsn):
    """Create a hand-authored finding for a security driver the sweep does not
    (yet) emit — e.g. an image the scanner could not reach, or a residual CVE
    after a partial remediation. Idempotent on the title fingerprint."""
    fp, fid = _finding_fingerprint(args.section, args.subsection, args.title)
    detail = _read_detail(args)
    meta = {"authored_by": "policy-cli", "subsection": args.subsection or "plan_driver"}
    if detail:
        meta["security_detail"] = detail
        meta["detail_updated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    if args.plan:
        meta["plans"] = args.plan
    if args.component:
        meta["component"] = args.component
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT finding_id FROM sweep_findings "
            "WHERE fingerprint = %s AND resolved_at IS NULL LIMIT 1", (fp,)
        )
        if cur.fetchone():
            print(f"{fid} already open — use `finding detail {fid}` to update it")
            return 1
        cycle = _policy_cli_cycle(cur)
        cur.execute(
            """
            INSERT INTO sweep_findings (
                finding_id, fingerprint, section, severity, title, status,
                action, evidence_path, first_seen, last_seen, cycle_id, metadata
            ) VALUES (%s, %s, %s, %s, %s, 'new', %s, NULL,
                      now(), now(), %s, %s::jsonb)
            """,
            (fid, fp, args.section, args.severity, args.title,
             args.action, cycle, json.dumps(meta)),
        )
        conn.commit()
        row = _finding_row(cur, fid)
    print(f"added {fid}\n")
    print(_ref_block(row))


def cmd_finding_detail(args, dsn):
    """Attach/replace the private vulnerability detail and plan linkage on an
    EXISTING finding (typically one the CVE check already emits)."""
    detail = _read_detail(args)
    if detail is None and not args.plan and not args.action:
        print("nothing to do: pass --detail/--detail-file, --plan, or --action",
              file=sys.stderr)
        return 1
    with _connect(dsn) as conn, conn.cursor() as cur:
        row = _finding_row(cur, args.finding_id)
        if not row:
            print(f"finding {args.finding_id} not found", file=sys.stderr); return 1
        meta = dict(row.get("metadata") or {})
        if detail is not None:
            meta["security_detail"] = detail
            meta["detail_updated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        if args.plan:
            meta["plans"] = sorted(set(meta.get("plans") or []) | set(args.plan))
        if args.component:
            meta["component"] = args.component
        cur.execute(
            "UPDATE sweep_findings SET metadata = %s::jsonb, "
            "action = COALESCE(%s, action) WHERE id = %s",
            (json.dumps(meta, ensure_ascii=False), args.action, row["id"]),
        )
        conn.commit()
        row = _finding_row(cur, args.finding_id)
    print(f"updated {args.finding_id}\n")
    print(_ref_block(row))


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
    re_ = risk.add_parser("edit", help="update an existing AR in place")
    re_.add_argument("ar_id")
    re_.add_argument("--description")
    re_.add_argument("--severity")
    re_.add_argument("--justification")
    re_.add_argument("--allow-drift", action="store_true",
                     help="accept a description that pins a patch version / count")
    re_.set_defaults(handler=cmd_risk_edit)
    rlint = risk.add_parser("lint", help="report AR descriptions that are not drift-stable")
    rlint.add_argument("--all", action="store_true", help="include drift-stable ARs too")
    rlint.set_defaults(handler=cmd_risk_lint)
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
    su = slo.add_parser("update", help="patch an existing SLO in place")
    su.add_argument("name")
    su.add_argument("--numerator")
    su.add_argument("--denominator")
    su.add_argument("--target", type=float)
    su.add_argument("--window")
    su.add_argument("--description")
    su.set_defaults(handler=cmd_slo_update)
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

    # finding (sweep_findings) — vulnerability detail lives in the DB, not git
    fnd = sub.add_parser(
        "finding",
        help="sweep_findings table — the private home for vulnerability detail",
    ).add_subparsers(dest="op", required=True)
    fl = fnd.add_parser("list")
    fl.add_argument("--section")
    fl.add_argument("--severity")
    fl.add_argument("--grep", help="ILIKE match on title")
    fl.add_argument("--all", action="store_true", help="include resolved rows")
    fl.add_argument("--limit", type=int, default=40)
    fl.set_defaults(handler=cmd_finding_list)
    fs = fnd.add_parser("show"); fs.add_argument("finding_id")
    fs.set_defaults(handler=cmd_finding_show)
    fr = fnd.add_parser("ref", help="print the publish-safe block to paste into a plan")
    fr.add_argument("finding_id"); fr.set_defaults(handler=cmd_finding_ref)
    fa = fnd.add_parser("add", help="hand-author a driver the sweep does not emit")
    fa.add_argument("--title", required=True,
                    help="PUBLISH-SAFE one-liner (it shows on the dashboard list)")
    fa.add_argument("--section", default=_PLAN_SECTION,
                    help="default 'plan' — a section the sweep never re-runs, so "
                         "the row is never auto-closed")
    fa.add_argument("--subsection")
    fa.add_argument("--severity", default="deferred",
                    choices=["deferred", "monitor", "accepted"],
                    help="NOT critical/warning — those pin the sweep verdict")
    fa.add_argument("--action")
    fa.add_argument("--detail", help="private vulnerability detail (never committed)")
    fa.add_argument("--detail-file")
    fa.add_argument("--plan", action="append", help="plan_id this drives; repeatable")
    fa.add_argument("--component")
    fa.set_defaults(handler=cmd_finding_add)
    fd = fnd.add_parser("detail", help="attach private detail / plan linkage to a finding")
    fd.add_argument("finding_id")
    fd.add_argument("--detail")
    fd.add_argument("--detail-file")
    fd.add_argument("--action")
    fd.add_argument("--plan", action="append")
    fd.add_argument("--component")
    fd.set_defaults(handler=cmd_finding_detail)

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
