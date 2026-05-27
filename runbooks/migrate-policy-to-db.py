#!/usr/bin/env python3
"""One-shot migration: source files → sweep_history policy tables.

Runs once during the policy-in-DB cutover (Plan Phase 1.2). Parses:

  docs/security-accepted-risks.md       → accepted_risks         (27)
  runbooks/slo-catalog.yaml             → slo_definitions        (3)
  runbooks/noise_allowlist.yaml         → noise_suppressions     (18)
  runbooks/security_check_acceptances.py → security_acceptances  (123)

Idempotent: TRUNCATEs each target table before INSERTs, so re-running
is safe. Source files are NOT modified by this script.

Usage:
    python3 runbooks/migrate-policy-to-db.py --confirm
    python3 runbooks/migrate-policy-to-db.py --dry-run    # parse only

Auto-port-forwards postgresql + derives the WRITER_DSN secret — same
mechanic as runbooks/sweep-run.py.

After verifying row counts, this script and the four source files
are deleted in Plan Phase 2.
"""
from __future__ import annotations

import argparse
import ast
import base64
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
REPO_ROOT  = SCRIPT_DIR.parent

ACCEPTED_RISKS_DOC = REPO_ROOT / "docs" / "security-accepted-risks.md"
SLO_CATALOG_YAML   = SCRIPT_DIR / "slo-catalog.yaml"
NOISE_ALLOWLIST    = SCRIPT_DIR / "noise_allowlist.yaml"
SEC_ACCEPTANCES    = SCRIPT_DIR / "security_check_acceptances.py"


# ---------------------------------------------------------------------------
# Port-forward + DSN derivation (same shape as sweep-run.py)
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
        return base64.b64decode(json.loads(out)["data"]["WRITER_DSN"]).decode("utf-8")
    except (KeyError, json.JSONDecodeError):
        return None


def _start_pf(namespace: str, service: str, local: int, remote: int) -> subprocess.Popen:
    pf = subprocess.Popen(
        ["kubectl", "port-forward", "-n", namespace, f"svc/{service}",
         f"{local}:{remote}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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
    raise SystemExit(f"port-forward to {service}:{remote} did not come up in 6s")


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


# ---------------------------------------------------------------------------
# Parsers — one per source file
# ---------------------------------------------------------------------------

_AR_PATTERN = re.compile(r"\b(AR-\d{3})\s*[:—\-]\s+(.+?)\s*$")
_SEVERITY_RE = re.compile(r"\*\*Severity[^:*]*\*\*\s*[:—]\s*(.+?)\s*$", re.IGNORECASE)
_STATUS_RE   = re.compile(r"\*\*Status\*\*\s*[:—]\s*(.+?)\s*$", re.IGNORECASE)


def parse_accepted_risks() -> list[dict]:
    """Walk the markdown; one entry per `## AR-NNN — TITLE` header.

    description ← title text after the em-dash (matches what
    security-check.py:load_accepted_risks() returns today).
    severity / status ← from the per-entry `**Severity ...:** X` and
    `**Status:** X` lines that follow each header. Defaults if missing.
    """
    if not ACCEPTED_RISKS_DOC.exists():
        return []
    text = ACCEPTED_RISKS_DOC.read_text(encoding="utf-8")
    entries: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.lstrip("# ").rstrip()
        m = _AR_PATTERN.match(line)
        if m:
            if current is not None:
                entries.append(current)
            current = {
                "ar_id":       m.group(1),
                "description": m.group(2).strip(),
                "severity":    "informational",
                "status":      "accepted",
            }
            continue
        if current is None:
            continue
        if not current.get("severity_seen"):
            m2 = _SEVERITY_RE.search(raw)
            if m2:
                first_word = m2.group(1).strip().split()[0].rstrip(",.").lower()
                current["severity"] = first_word
                current["severity_seen"] = True
                continue
        if not current.get("status_seen"):
            m3 = _STATUS_RE.search(raw)
            if m3:
                first_word = m3.group(1).strip().split("—")[0].strip().split()[0].lower()
                current["status"] = first_word
                current["status_seen"] = True
    if current is not None:
        entries.append(current)
    for e in entries:
        e.pop("severity_seen", None)
        e.pop("status_seen", None)
    return entries


def parse_slo_catalog() -> list[dict]:
    if not SLO_CATALOG_YAML.exists():
        return []
    import yaml
    data = yaml.safe_load(SLO_CATALOG_YAML.read_text(encoding="utf-8"))
    defaults = data.get("defaults") or {}
    default_brws = defaults.get("burn_rate_windows")
    out = []
    for entry in data.get("slos", []) or []:
        source = entry.get("source", "prom")
        query_block = entry.get(source) or {}
        out.append({
            "name":              entry["name"],
            "description":       (entry.get("description") or "").strip(),
            "source":            source,
            "kind":              entry.get("kind", "ratio"),
            "target":            float(entry["target"]),
            "window_size":       entry["window"],
            "query_json":        query_block,
            "burn_rate_windows": entry.get("burn_rate_windows") or default_brws,
            "tags":              entry.get("tags") or [],
        })
    return out


def parse_noise_allowlist() -> list[dict]:
    if not NOISE_ALLOWLIST.exists():
        return []
    import yaml
    data = yaml.safe_load(NOISE_ALLOWLIST.read_text(encoding="utf-8"))
    out: list[dict] = []
    for category, items in (data or {}).items():
        if not isinstance(items, list):
            continue
        for it in items:
            if isinstance(it, str):
                out.append({"category": category, "match_value": it,
                            "match_key": None, "threshold": None, "note": None})
            elif isinstance(it, dict):
                match_key = None
                match_value = None
                threshold = it.get("threshold_per_cycle") or it.get("threshold")
                note = it.get("note")
                for k in ("alertname", "integration", "service", "name",
                          "prefix", "workload"):
                    if k in it:
                        match_key = k
                        match_value = it[k]
                        break
                if match_value is None:
                    for k, v in it.items():
                        if k not in ("note", "threshold", "threshold_per_cycle"):
                            match_key = k
                            match_value = v
                            break
                out.append({"category": category,
                            "match_key": match_key,
                            "match_value": str(match_value) if match_value is not None else None,
                            "threshold": threshold,
                            "note": note})
    return out


def parse_security_acceptances() -> list[dict]:
    """AST-parse the python module; extract 3 list/set assignments + comments."""
    if not SEC_ACCEPTANCES.exists():
        return []
    src = SEC_ACCEPTANCES.read_text(encoding="utf-8")
    src_lines = src.splitlines()
    tree = ast.parse(src)

    targets = {
        "GIT_HISTORY_CRED_PATTERNS":   "git_history_cred",
        "GIT_HISTORY_SECRET_FILES":    "git_history_secret_file",
        "EXTERNAL_INGRESS_ACCEPTED":   "external_ingress_accepted",
    }
    out: list[dict] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name):
                continue
            name = node.target.id
            value = node.value
        elif isinstance(node, ast.Assign):
            if not node.targets or not isinstance(node.targets[0], ast.Name):
                continue
            name = node.targets[0].id
            value = node.value
        else:
            continue
        if name not in targets:
            continue
        category = targets[name]
        elts = []
        if isinstance(value, (ast.List, ast.Set)):
            elts = value.elts
        for elt in elts:
            if not isinstance(elt, ast.Constant):
                continue
            pattern = elt.value
            if not isinstance(pattern, str):
                continue
            line_no = elt.lineno - 1
            note = None
            if 0 <= line_no < len(src_lines):
                line = src_lines[line_no]
                hash_idx = line.find("#")
                # Only treat as comment if # is past the string literal
                if hash_idx != -1:
                    # Verify the literal occurs before the # (basic heuristic)
                    quoted = repr(pattern)
                    plain_q = "'" + pattern.replace("'", "\\'") + "'"
                    dq = '"' + pattern.replace('"', '\\"') + '"'
                    pos = max(line.find(plain_q), line.find(dq), line.find(pattern))
                    if pos != -1 and pos < hash_idx:
                        note = line[hash_idx + 1:].strip()
            ar_id = None
            if note:
                m = re.search(r"\b(AR-\d{3})\b", note)
                if m:
                    ar_id = m.group(1)
            out.append({"category": category, "pattern": pattern,
                        "note": note, "ar_id": ar_id})
    return out


# ---------------------------------------------------------------------------
# DB writer
# ---------------------------------------------------------------------------

def migrate(dsn: str, dry_run: bool) -> int:
    risks   = parse_accepted_risks()
    slos    = parse_slo_catalog()
    noise   = parse_noise_allowlist()
    secacc  = parse_security_acceptances()

    print(f"parsed: {len(risks)} risks, {len(slos)} SLOs, "
          f"{len(noise)} noise rows, {len(secacc)} security acceptances")

    # Sample preview
    print("\n  sample accepted_risks (first 3):")
    for r in risks[:3]:
        print(f"    {r['ar_id']:8s} sev={r['severity']:14s} {r['description'][:60]}")
    print("\n  sample security_acceptances (first 3 per category):")
    by_cat: dict = {}
    for sa in secacc:
        by_cat.setdefault(sa["category"], []).append(sa)
    for cat, rows in by_cat.items():
        print(f"    {cat} ({len(rows)}):")
        for r in rows[:3]:
            note = (r["note"] or "")[:50]
            print(f"      {r['pattern'][:50]:50s}  | {note}")

    if dry_run:
        print("\n--dry-run set; no DB writes.")
        return 0

    import psycopg
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        # DELETE FROM (not TRUNCATE) because sweep_writer has DML but not
        # OWNER privilege on the policy tables (the tables are owned by
        # the postgres admin role per the init-Job ownership model).
        print("\n→ clearing policy tables ...")
        for table in ("accepted_risks", "slo_definitions",
                      "noise_suppressions", "security_acceptances"):
            cur.execute(f"DELETE FROM {table}")

        print(f"→ inserting {len(risks)} accepted_risks ...")
        for r in risks:
            cur.execute(
                "INSERT INTO accepted_risks (ar_id, severity, description, status) "
                "VALUES (%s, %s, %s, %s)",
                (r["ar_id"], r["severity"], r["description"], r["status"]),
            )

        print(f"→ inserting {len(slos)} slo_definitions ...")
        for s in slos:
            cur.execute(
                "INSERT INTO slo_definitions "
                "(name, description, source, kind, target, window_size, "
                " query_json, burn_rate_windows, tags) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)",
                (s["name"], s["description"], s["source"], s["kind"],
                 s["target"], s["window_size"],
                 json.dumps(s["query_json"]),
                 json.dumps(s["burn_rate_windows"]) if s["burn_rate_windows"] else None,
                 s["tags"]),
            )

        print(f"→ inserting {len(noise)} noise_suppressions ...")
        for n in noise:
            cur.execute(
                "INSERT INTO noise_suppressions "
                "(category, match_key, match_value, threshold, note) "
                "VALUES (%s, %s, %s, %s, %s)",
                (n["category"], n["match_key"], n["match_value"],
                 n["threshold"], n["note"]),
            )

        print(f"→ inserting {len(secacc)} security_acceptances ...")
        for sa in secacc:
            cur.execute(
                "INSERT INTO security_acceptances "
                "(category, pattern, note, ar_id) VALUES (%s, %s, %s, %s)",
                (sa["category"], sa["pattern"], sa["note"], sa["ar_id"]),
            )
        conn.commit()

        print("\n→ verifying row counts ...")
        fail = 0
        for table, expected in [
            ("accepted_risks",       len(risks)),
            ("slo_definitions",      len(slos)),
            ("noise_suppressions",   len(noise)),
            ("security_acceptances", len(secacc)),
        ]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            actual = cur.fetchone()[0]
            status = "✓" if actual == expected else "✗"
            print(f"   {status} {table:24s} expected={expected}  actual={actual}")
            if actual != expected:
                fail = 1
        return fail


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="One-shot policy migration to DB")
    p.add_argument("--confirm", action="store_true",
                   help="Required to actually write to the DB.")
    p.add_argument("--dry-run", action="store_true",
                   help="Parse only, no DB writes.")
    p.add_argument("--postgres-dsn",
                   default=os.environ.get("SWEEP_PG_DSN"),
                   help="DSN override; otherwise port-forwards postgresql.")
    args = p.parse_args(argv)

    if not args.confirm and not args.dry_run:
        print("Refusing to run without --confirm. Use --dry-run to test parsing.",
              file=sys.stderr)
        return 2

    dsn = args.postgres_dsn
    pf = None
    if not args.dry_run and not dsn:
        port = _free_port()
        print(f"→ port-forwarding postgresql ({port}/tcp) ...")
        pf = _start_pf("databases", "postgresql", port, 5432)
        raw = _kubectl_secret_dsn()
        if not raw:
            raise SystemExit("could not decode sweep-history WRITER_DSN")
        fqdn = "@postgresql." + "databases.svc.cluster.local:5432"
        dsn = raw.replace(fqdn, f"@127.0.0.1:{port}")

    try:
        rc = migrate(dsn or "", dry_run=args.dry_run)
    finally:
        _stop(pf)
    return rc


if __name__ == "__main__":
    sys.exit(main())
