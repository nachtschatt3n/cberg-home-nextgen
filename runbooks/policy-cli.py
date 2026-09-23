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
  policy-cli risk match --description 'node:22.'   # PREVIEW what a needle would suppress
                                        # — run this BEFORE `risk add`
  policy-cli risk lint                  # descriptions that drifted, went inert, or EXPIRED
  policy-cli risk edit AR-042 --expires 2026-12-01   # last day in force
  policy-cli risk edit AR-042 --expires none         # clear it (open-ended)
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
sys.path.insert(0, str(SCRIPT_DIR))

from lib.ar_expiry import (  # noqa: E402
    EXPIRY_KEY, EXPIRY_SELECT, is_expired, parse_expiry, prose_deadline,
)


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
            f"SELECT ar_id, severity, status, enabled, description, last_reviewed_at, "
            f"       {EXPIRY_SELECT} AS expires_at "
            f"FROM accepted_risks {where} ORDER BY ar_id", params
        )
        _print_table(cur.fetchall(), [
            ("ar_id", "AR ID", 8),
            ("severity", "Severity", 14),
            ("status", "Status", 10),
            ("enabled", "On", 3),
            ("last_reviewed_at", "Reviewed", 10),
            ("expires_at", "Expires", 10),
            ("description", "Description", 50),
        ])


def cmd_risk_show(args, dsn):
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM accepted_risks WHERE ar_id = %s", (args.ar_id,))
        row = cur.fetchone()
        if not row:
            print(f"AR {args.ar_id} not found", file=sys.stderr); return 1
        for k, v in row.items():
            print(f"  {k:18s}  {v}")


# The suppressor's own exemptions, restated as SQL so the preview and the
# `risk add` gate cannot disagree with what _apply_ar_suppression (sweep-run.py)
# will actually do. Kept as one string used by both callers: two copies of this
# predicate drifting apart is the same class of bug the preview exists to catch.
_SUPPRESSIBLE_SQL = """
      severity IN ('critical', 'warning', 'monitor')
  AND position('[AR-' in title) = 0
  AND coalesce(metadata->>'risk_nature', '') <> ALL(%s)
  AND coalesce(metadata->>'subsection', '') !~* '^audit[-_]'
"""
_AUDIT_INTEGRITY_NATURES = [
    "policy-drift", "audit-coverage-gap", "audit-integrity", "meta",
]


def _would_match(cur, desc: str) -> list:
    """Open findings an AR description would touch, as
    (finding_id, severity, title, suppressible).

    Needle semantics are the suppressor's: a case-insensitive SUBSTRING of the
    finding title. `suppressible` additionally applies the exemptions
    _apply_ar_suppression enforces — eligible severity, not already AR-tagged,
    not an audit-integrity row. A hit that is NOT suppressible is shown by the
    preview (it tells you the needle reaches further than you think) but does
    NOT satisfy the `risk add` gate, or the gate could be cleared by rows the
    suppressor will never act on.

    This exists because an AR is written blind otherwise. A description is not
    prose for a reader; it is a needle, and prose is almost never a substring
    of a generated finding title — an AR written as a reason suppresses nothing
    while reporting success. See AR-080 (security_ref F-6a941c93) for the third
    instance; the detail lives on the finding record, not here.
    """
    needle = (desc or "").strip().lower()
    if not needle:
        return []
    cur.execute(
        "SELECT finding_id, severity, title, (" + _SUPPRESSIBLE_SQL + ") AS ok "
        "  FROM sweep_findings "
        " WHERE resolved_at IS NULL "
        "   AND severity IN ('critical','warning','monitor','accepted','deferred') "
        "   AND position(%s in lower(title)) > 0 "
        " ORDER BY severity, finding_id",
        (_AUDIT_INTEGRITY_NATURES, needle))
    return [(r["finding_id"], r["severity"], r["title"], bool(r["ok"]))
            for r in cur.fetchall()]


# An AR needle is matched against EVERY future sweep, so breadth is a standing
# liability, not a one-time one: a short needle permanently accepts findings
# nobody has decided to accept yet. `risk match` can only ever show today's
# rows, so the ceiling is the guard for the ones that do not exist yet.
_BREADTH_CEILING = 12


def cmd_risk_match(args, dsn):
    """Dry-run a candidate AR description against the open findings.

    Write the AR only after this prints the rows you meant to cover, and
    nothing you did not. Exit 1 = matches nothing; exit 3 = over-broad.
    """
    with _connect(dsn) as conn, conn.cursor() as cur:
        hits = _would_match(cur, args.description)
        warn = _drift_warnings(args.description)
    print(f"needle: {args.description!r}")
    for w in warn:
        print(f"  ! not drift-stable: {w}")
    live = [h for h in hits if h[3]]
    inert = [h for h in hits if not h[3]]
    if not hits:
        print("  MATCHES NOTHING — this description would suppress no finding. "
              "Name the component as it appears in the finding title rather than "
              "the reason you are accepting it; the reason belongs in "
              "--justification.")
        return 1
    print(f"  would suppress {len(live)} open finding(s):")
    for fid, sev, title, _ in live:
        print(f"    {fid}  {sev:<13} {title[:110]}")
    if inert:
        print(f"  matches {len(inert)} further row(s) the suppressor EXEMPTS "
              f"(already AR-tagged, audit-integrity, or not an eligible "
              f"severity) — they do not count toward the gate:")
        for fid, sev, title, _ in inert:
            print(f"    {fid}  {sev:<13} {title[:110]}")
    if len(live) > _BREADTH_CEILING:
        print(f"  ! OVER-BROAD: {len(live)} live matches (ceiling "
              f"{_BREADTH_CEILING}). This needle is matched against every "
              f"future sweep too — prefer the NARROWEST needle that covers "
              f"your rows.")
        return 3
    return 0


def cmd_risk_add(args, dsn):
    # Forward-only ratchet: every NEW acceptance states a deadline or says
    # explicitly that it has none. The 105 pre-existing ARs are untouched —
    # back-filling by parsing justification prose was measured and rejected as
    # policy (see lib/ar_expiry.prose_deadline, which REPORTS them instead).
    if args.expires is None and not args.no_expiry:
        print("REFUSING: state how long this acceptance is good for.",
              file=sys.stderr)
        print("  --expires YYYY-MM-DD   last day in force; the sweep stops "
              "suppressing after it and the finding re-surfaces.", file=sys.stderr)
        print("  --no-expiry            open-ended: accepted until a CONDITION "
              "changes (upstream ships a fix), not until a date. Name the "
              "condition in --justification.", file=sys.stderr)
        return 2
    try:
        expiry = parse_expiry(args.expires) if args.expires is not None else None
    except ValueError as exc:
        print(f"REFUSING: {exc}", file=sys.stderr)
        return 2
    # An already-past deadline is inert the instant it is written — the same
    # failure the needle gate below refuses, wearing a date. Refuse it here
    # rather than print "added AR-xxx — suppresses N open finding(s)" for an
    # acceptance that suppresses nothing.
    if expiry is not None and is_expired(expiry.isoformat()):
        print(f"REFUSING: --expires {expiry} is already past, so this AR would "
              f"suppress nothing from the moment it is written.", file=sys.stderr)
        print("  Pick a future date, or --no-expiry for a condition-based "
              "acceptance. Use --allow-expired only to record a decision that "
              "has already lapsed.", file=sys.stderr)
        if not args.allow_expired:
            return 2
    warn = _drift_warnings(args.description)
    if warn and not args.allow_drift:
        print("REFUSING: proposed description is not drift-stable:", file=sys.stderr)
        for w in warn:
            print(f"  - {w}", file=sys.stderr)
        print("  (see operator memory project_sweep_ar_version_drift; "
              "pass --allow-drift to override)", file=sys.stderr)
        return 2
    anchor = getattr(args, "register_only", None)
    if anchor is not None:
        if anchor.strip().lower() == _CLEAR:
            print(f"REFUSING: --register-only {_CLEAR} clears a pointer, and a new "
                  f"AR has none to clear. Name what enforces it "
                  f"(<file>:<SYMBOL> or {POSTURE_ANCHOR}).", file=sys.stderr)
            return 2
        problem = _anchor_problem(anchor)
        if problem:
            print(f"REFUSING: --register-only {problem}", file=sys.stderr)
            return 2
        anchor = anchor.strip()
    with _connect(dsn) as conn, conn.cursor() as cur:
        live = [h for h in _would_match(cur, args.description) if h[3]]
        # An AR that matches nothing is inert. Refuse by default rather than
        # report success on a suppression that will never fire. A register-only
        # AR is enforced elsewhere and matches nothing BY DESIGN, so the anchor
        # satisfies this gate on its own.
        if not live and not args.allow_nomatch and anchor is None:
            print(f"REFUSING: {args.description!r} would suppress no open "
                  f"finding, so this AR is inert.", file=sys.stderr)
            print("  Preview with `policy-cli.py risk match --description ...`. "
                  "Name the component as it appears in the finding title, not "
                  "the reason (that belongs in --justification). Pass "
                  "--allow-nomatch for a genuinely forward-looking AR.",
                  file=sys.stderr)
            return 2
        # ... and one that matches far too much is worse than inert: the needle
        # is re-applied every sweep, so it silently accepts findings nobody has
        # decided to accept yet.
        if len(live) > _BREADTH_CEILING and not args.allow_broad:
            print(f"REFUSING: {args.description!r} would suppress {len(live)} "
                  f"open findings (ceiling {_BREADTH_CEILING}) — and it is "
                  f"re-applied to every future sweep.", file=sys.stderr)
            print("  Review them with `policy-cli.py risk match`, then pick the "
                  "narrowest needle that covers the rows you mean. Pass "
                  "--allow-broad if the breadth really is intended.",
                  file=sys.stderr)
            return 2
        meta = {EXPIRY_KEY: expiry.isoformat()} if expiry else {}
        if anchor:
            meta.update({REGISTER_ONLY_KEY: True, ENFORCED_IN_KEY: anchor})
        cur.execute(
            "INSERT INTO accepted_risks "
            "(ar_id, severity, description, justification, metadata) "
            "VALUES (%s, %s, %s, %s, %s::jsonb) ON CONFLICT (ar_id) DO NOTHING",
            (args.ar_id, args.severity, args.description, args.justification,
             json.dumps(meta)),
        )
        if cur.rowcount == 0:
            print(f"AR {args.ar_id} already exists — use `risk delete` first or rename")
            return 1
        conn.commit()
        if anchor:
            print(f"added {args.ar_id} — register-only, enforced by {anchor} "
                  f"(suppresses {len(live)} open finding(s); a title match is "
                  f"not expected)")
        else:
            print(f"added {args.ar_id} — suppresses {len(live)} open finding(s)")


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


# ---- register-only acceptances (F-5c48a0fc) --------------------------------
#
# Not every AR is a needle. Some register entries are enforced SOMEWHERE ELSE:
# a `security_acceptances` row that cites the AR (the ingress allowlist), an
# exemption set coded into security-check.py (ACCEPTED_PRIVILEGED,
# ACCEPTED_ROOT_UID), or an operator posture decision no detector exists for.
# Their description is a heading the operator reads; it is never matched
# against a finding title, BY DESIGN. `risk lint` used to read every one of
# them as INERT — 21 of 22 INERT rows on 2026-09-22 — which buried the one row
# that really was inert among twenty doing exactly what they should, and told
# the operator to rewrite headings as needles. A register-only AR records
# WHERE it is enforced (`metadata.enforced_in`) so the lint can say so.
#
# A `security_acceptances` citation is DERIVED from that table on every run,
# never copied onto the AR: the row is the enforcement, and a copy of that
# fact on the AR would be one more thing to drift (a disabled row anchors
# nothing, and the derivation sees that; a copied flag would not).
REGISTER_ONLY_KEY = "register_only"
ENFORCED_IN_KEY = "enforced_in"
POSTURE_ANCHOR = "register-only:posture"   # operator decision; no detector exists
_CLEAR = "none"                            # `--register-only none`, like `--expires none`


def _anchor_problem(anchor: str) -> str | None:
    """Why `anchor` is not an acceptable `enforced_in` pointer, or None if it is.

    Accepted forms:
      register-only:posture    an operator decision nothing detects
      <file>:<SYMBOL>          e.g. security-check.py:ACCEPTED_PRIVILEGED — the
                               file must exist under runbooks/ (or the repo
                               root) and SYMBOL must occur in it.

    The symbol check is the point. A pointer to a set that was renamed or
    deleted is the inert AR again, one indirection further away.
    """
    anchor = (anchor or "").strip()
    if not anchor:
        return "empty anchor"
    if anchor == POSTURE_ANCHOR:
        return None
    path, sep, symbol = anchor.partition(":")
    symbol = symbol.strip()
    if not sep or not symbol or " " in path or "/" in symbol:
        return (f"{anchor!r} — use `{POSTURE_ANCHOR}` or `<file>:<SYMBOL>` "
                f"(e.g. security-check.py:ACCEPTED_PRIVILEGED)")
    for base in (SCRIPT_DIR, SCRIPT_DIR.parent):
        candidate = base / path
        if candidate.is_file():
            break
    else:
        return f"{path!r} not found under runbooks/ or the repo root"
    if symbol not in candidate.read_text(encoding="utf-8", errors="replace"):
        return (f"{symbol!r} does not occur in {path} — a pointer to nothing "
                f"enforces nothing")
    return None


def register_only_anchors(ar_meta: dict, sec_rows: list) -> dict:
    """ar_id -> human-readable anchor, for every AR enforced outside the
    needle. Pure, so the derivation is testable without a database.

    ar_meta:  {ar_id: metadata dict or None}   (accepted_risks.metadata)
    sec_rows: [{id, category, ar_id}]           (ENABLED security_acceptances)

    A metadata anchor needs BOTH keys: `register_only` without an
    `enforced_in` pointer is not an anchor, it is a claim with no address, and
    the AR stays INERT (the lint says why).
    """
    parts: dict[str, list[str]] = {}
    cited: dict[str, dict[str, list]] = {}
    for r in sec_rows:
        ar = r.get("ar_id")
        if not ar:
            continue
        cited.setdefault(ar, {}).setdefault(r.get("category") or "?", []).append(r.get("id"))
    for ar, cats in cited.items():
        for cat, ids in cats.items():
            ids = sorted(i for i in ids if i is not None)
            parts.setdefault(ar, []).append(
                f"security_acceptances:{cat} (id {','.join(str(i) for i in ids)})")
    for ar, meta in ar_meta.items():
        meta = meta or {}
        pointer = str(meta.get(ENFORCED_IN_KEY) or "").strip()
        if meta.get(REGISTER_ONLY_KEY) in (True, "true") and pointer:
            parts.setdefault(ar, []).append(f"{pointer} (metadata.{ENFORCED_IN_KEY})")
    return {ar: " + ".join(v) for ar, v in parts.items()}


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
    # Every metadata change is folded into ONE `metadata = <expr>` assignment:
    # Postgres rejects two assignments to the same column in one UPDATE, so
    # `--expires` and `--register-only` in the same call must compose.
    meta_expr, meta_params = "COALESCE(metadata, '{}'::jsonb)", []
    expiry = _UNSET = object()
    if getattr(args, "expires", None) is not None:
        try:
            expiry = parse_expiry(args.expires)
        except ValueError as exc:
            print(f"REFUSING: {exc}", file=sys.stderr)
            return 2
        if expiry is None:
            meta_expr += " - %s"
            meta_params.append(EXPIRY_KEY)
        else:
            # `|| %s::jsonb` with ONE json-encoded parameter, the idiom
            # `risk add` already uses. NOT jsonb_build_object(%s, %s): psycopg
            # sends str with an unknown OID, so Postgres cannot resolve
            # jsonb_build_object("any","any") and the UPDATE fails with
            # IndeterminateDatatype — measured by EXPLAIN against the live DB.
            meta_expr += " || %s::jsonb"
            meta_params.append(json.dumps({EXPIRY_KEY: expiry.isoformat()}))
    anchor = getattr(args, "register_only", None)
    clear_anchor = anchor is not None and anchor.strip().lower() == _CLEAR
    if clear_anchor:
        meta_expr += " - %s - %s"
        meta_params.extend([REGISTER_ONLY_KEY, ENFORCED_IN_KEY])
    elif anchor is not None:
        problem = _anchor_problem(anchor)
        if problem:
            print(f"REFUSING: --register-only {problem}", file=sys.stderr)
            return 2
        anchor = anchor.strip()
        meta_expr += " || %s::jsonb"
        meta_params.append(json.dumps({REGISTER_ONLY_KEY: True, ENFORCED_IN_KEY: anchor}))
    if meta_params:
        sets.append(f"metadata = {meta_expr}")
        params.extend(meta_params)
    if not sets:
        print("nothing to change — pass at least one of "
              "--description/--severity/--justification/--expires/--register-only",
              file=sys.stderr)
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
    if expiry is not _UNSET and expiry is not None and is_expired(expiry.isoformat()):
        print(f"  NOTE: {args.ar_id} is now EXPIRED ({expiry}) — it suppresses "
              f"nothing from this moment, and the findings it masked re-surface "
              f"at their own severity on the next sweep.")
    if args.description is not None:
        print(f"  description: {before!r}")
        print(f"           -> {args.description!r}")
    if clear_anchor:
        print(f"  register-only: cleared — {args.ar_id} lints as a needle again")
    elif anchor is not None:
        print(f"  register-only: enforced by {anchor} — `risk lint` reports it "
              f"REGISTER-ONLY instead of INERT while the description matches "
              f"no title")
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


def lint_flag(open_matches: int, warn, miss, total_matches: int,
              expired: bool = False, register_only: "str | None" = None) -> str:
    """Classify one AR for `risk lint`. Pure, so the precedence is testable.

    Precedence matters and is not arbitrary:

      INERT        beats everything. A description that never matched anything
                   is not "drifting" and not "at risk" — it never worked, and
                   telling the operator to watch it for future drift would
                   describe the wrong problem entirely.
      REGISTER-ONLY sits exactly where INERT would: the description has never
                   matched a title and is not meant to — `register_only` names
                   what enforces the AR instead (a security_acceptances row, a
                   coded exemption set, an operator posture decision). ONLY the
                   never-matched case is reclassified: a register-only AR that
                   does match a title is a needle whatever its metadata says,
                   and lints as one (ok / at risk / DRIFTING NOW as usual).
      DRIFTING NOW beats `at risk`: the drift already happened, so a warning
                   that it MIGHT happen is stale news.
      at risk      the description still matches, but embeds something volatile.

    `total_matches` counts ALL findings including resolved ones, which is what
    separates INERT from merely DORMANT: an AR whose finding is currently
    resolved is doing its job and waiting, and must not be flagged.
    """
    if expired:
        # Outranks everything, INERT included. The others describe a needle that
        # may not do what the register claims; EXPIRED means the operator's own
        # deadline passed, so the entry is no longer a decision anyone has
        # made — renew-or-retire, now, whatever the needle does.
        return "EXPIRED"
    if open_matches == 0 and not miss and total_matches == 0:
        return "REGISTER-ONLY" if register_only else "INERT"
    if miss:
        return "DRIFTING NOW"
    if warn:
        return "at risk"
    return "ok"


def cmd_risk_lint(args, dsn):
    """Report ARs whose description has stopped (or will stop) matching.

    Three independent signals:
      STATIC  — the description embeds a patch-level version or a volatile
                count, so it WILL drift out of matching on the next bump.
      DRIFTING NOW — the description matches zero open findings, but a
                shorter PREFIX of it does. That is proof the tail drifted.
      INERT   — the description has NEVER matched any finding, open or
                resolved, and no prefix of it does either. Added 2026-09-06.

    INERT is the one that hid. The other two both require the description to
    have worked at some point; a description written as PROSE ("Headlamp
    cluster-admin ClusterRoleBinding") never matches anything at any prefix, so
    it slipped past both checks in silence while reading as active policy.
    Measured when this was added: 29 of 101 enabled acceptances were inert.
    AR-016 was one of them — it had suppressed nothing since 2026-05-27, which
    only surfaced because a finding it was supposed to cover came up for
    triage.

    An inert AR is not merely useless. The register is what the operator reads
    to answer "what have we accepted", so an inert entry is a claim that
    something is handled when nothing is.

      REGISTER-ONLY — never matched a title either, and is not meant to: the
                AR is enforced elsewhere and the line names where. Two anchors
                count (F-5c48a0fc, 2026-09-23): an ENABLED security_acceptances
                row citing the AR (derived from the table every run), or
                metadata.register_only=true with an enforced_in pointer that
                `risk add/edit --register-only <anchor>` records. Everything
                else keeps INERT semantics; a register-only AR whose
                description DOES match a title lints as a needle.

    Before that class existed, 21 of the 22 INERT rows were enforced elsewhere
    — the ingress allowlist, ACCEPTED_PRIVILEGED / ACCEPTED_ROOT_UID in
    security-check.py, operator posture decisions — and the lint told the
    operator to rewrite every one of them as a needle. The one genuinely inert
    row was indistinguishable from the twenty that were doing their job.
    """
    with _connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT ar_id, description, justification, {EXPIRY_SELECT} AS expires_at, "
            f"       metadata "
            f"FROM accepted_risks "
            f"WHERE enabled = true AND status = 'accepted' ORDER BY ar_id")
        ars = [(r["ar_id"], r["description"], r["justification"], r["expires_at"],
                r["metadata"]) for r in cur.fetchall()]
        # What anchors an AR outside the needle. Derived, not trusted: a
        # DISABLED security_acceptances row enforces nothing, so it anchors
        # nothing — filter here, where the derivation can see it.
        cur.execute(
            "SELECT id, category, ar_id FROM security_acceptances "
            "WHERE enabled = true AND ar_id IS NOT NULL ORDER BY category, id")
        anchors = register_only_anchors(
            {ar_id: meta for ar_id, _d, _j, _e, meta in ars}, cur.fetchall())
        rows = []
        for ar_id, desc, just, expires, meta in ars:
            expired = is_expired(expires)
            # The gate binds ONLY on a recorded date, so an AR whose deadline
            # lives in prose lapses unseen — which is exactly how AR-042 ran 14
            # days over. This is the control that keeps that class visible.
            unrecorded = prose_deadline(just) if not expires else None
            warn = _drift_warnings(desc or "")
            cur.execute(
                "SELECT count(*) AS n FROM sweep_findings "
                "WHERE resolved_at IS NULL AND position(%s in lower(title)) > 0",
                ((desc or "").strip().lower(),))
            matches = cur.fetchone()["n"]
            miss = _near_miss(cur, desc) if matches == 0 else None
            # INERT: never matched ANY finding, resolved ones included. Checked
            # against the full table on purpose — an AR whose finding is
            # currently resolved is dormant, not inert, and must not be flagged.
            inert = False
            if matches == 0 and not miss:
                cur.execute(
                    "SELECT count(*) AS n FROM sweep_findings "
                    "WHERE position(%s in lower(title)) > 0",
                    ((desc or "").strip().lower(),))
                inert = cur.fetchone()["n"] == 0
            if warn or miss or inert or expired or unrecorded or args.all:
                rows.append((ar_id, desc, matches, warn, miss, inert,
                             expired, expires, unrecorded, anchors.get(ar_id),
                             meta))
    if not rows:
        print("all enabled AR descriptions are drift-stable and matching")
        return 0
    print(f"{'AR':<8} {'open-match':>10}  description")
    attention = register_only = 0
    for (ar_id, desc, matches, warn, miss, inert, expired, expires, unrecorded,
         anchor, meta) in rows:
        flag = lint_flag(matches, warn, miss, 0 if inert else 1, expired=expired,
                         register_only=anchor)
        if flag == "REGISTER-ONLY":
            register_only += 1
        if flag not in ("ok", "REGISTER-ONLY") or unrecorded:
            attention += 1
        print(f"{ar_id:<8} {matches:>10}  {desc!r}  [{flag}]")
        if expired:
            print(f"{'':<21}! stated expiry {expires!r} has passed — it no "
                  f"longer suppresses anything (the sweep skips it).")
            print(f"{'':<23}Renew: `risk edit {ar_id} --expires <date>`; "
                  f"retire: `risk disable {ar_id}`; or `--expires none` if "
                  f"the deadline was never real.")
        if unrecorded:
            _phrase, _date = unrecorded
            print(f"{'':<21}! justification states a deadline ({_phrase} "
                  f"{_date}) that NOTHING ENFORCES — no metadata.expires_at is "
                  f"recorded, so this AR suppresses indefinitely.")
            print(f"{'':<23}Record it: `risk edit {ar_id} --expires {_date}` "
                  f"(or a renewed date), or `--no-expiry` semantics: reword the "
                  f"justification as a CONDITION, not a date.")
        for w in warn:
            print(f"{'':<21}! {w}")
        if miss:
            prefix, fid, title = miss
            print(f"{'':<21}! description matches 0 open findings, but the prefix "
                  f"{prefix!r} matches {fid}:")
            print(f"{'':<23}{title[:100]}")
        if inert and anchor:
            print(f"{'':<21}! register-only — enforced by {anchor}. The "
                  f"description is a heading, not a needle; it is not expected "
                  f"to match a finding title.")
        elif inert:
            print(f"{'':<21}! has NEVER matched any finding (open or resolved) — "
                  f"it suppresses nothing while reading as accepted policy.")
            print(f"{'':<23}Rewrite it as a SUBSTRING of the finding title it "
                  f"should cover (preview with `risk match`), or retire it if "
                  f"the risk is gone.")
            if (meta or {}).get(REGISTER_ONLY_KEY) and not anchor:
                print(f"{'':<23}metadata.{REGISTER_ONLY_KEY} is set but there is "
                      f"no {ENFORCED_IN_KEY} pointer, so nothing anchors it — "
                      f"`risk edit {ar_id} --register-only <anchor>` records both.")
    if register_only and not attention and not args.all:
        # Every listed row is enforced elsewhere: say so, or a clean register
        # reads as twenty-one problems.
        print(f"all other enabled AR descriptions are drift-stable and matching "
              f"({register_only} register-only, enforced elsewhere)")
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


def _redirect_banner(row: dict, asked: str) -> str:
    """A provenance line for STDOUT when a lookup was redirected.

    The stderr note alone is not enough on the read path: `finding show` writes
    the private detail to stdout, so anything capturing stdout only — a pipe, a
    paste into a document, a `2>/dev/null` in a loop — gets the payload with no
    indication it came from a row the caller did not name.
    """
    if row["finding_id"] == asked:
        return ""
    adopted = (row.get("metadata") or {}).get("adopted_finding_ids") or []
    kind = "ADOPTED id" if asked in adopted else "rename"
    return (f"# NOTE: you asked for {asked}; this is {row['finding_id']} "
            f"(via {kind}).\n")


def _finding_row(cur, finding_id: str):
    """Resolve a finding by id, falling back to its historical ids.

    `finding_id` is derived from the fingerprint, so any change to the identity
    function renames rows (the 2026-08-18 AR-independent-fingerprint migration
    renamed 179). Committed `security_ref: F-xxxxxxxx` lines and plan files are
    immutable, so the old id has to keep resolving or every reference in git
    history silently rots. `runbooks/refingerprint-findings.py` records the old
    ids in `metadata.prior_finding_ids`; this is the read side of that.

    Resolution order is (open, exact) -> (open, alias) -> (any, exact) ->
    (any, alias): a LIVE row always beats a dead one, and within each liveness
    tier the current id beats an alias.
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
            # `id DESC` is the tie-break, not decoration: uq_findings_open_finding_id
            # bounds the exact/open pass to one row, but NOTHING constrains
            # `prior_finding_ids` — no index, no uniqueness — and the migration's
            # union logic makes alias sets grow, so two rows sharing an alias is
            # an expected future state. `last_seen` ties are routine (a sweep
            # stamps now() across a batch), which would make the winner
            # arbitrary.
            cur.execute(
                f"SELECT * FROM sweep_findings WHERE {pred}{clause} "
                f"ORDER BY last_seen DESC, id DESC LIMIT 1",
                (finding_id,),
            )
            row = cur.fetchone()
            if row is None:
                continue
            if row["finding_id"] != finding_id:
                # Deliberately does NOT assert a cause. prior_finding_ids
                # holds two kinds of entry: ids a row was RENAMED from (a
                # fingerprint migration), and ids a row has ADOPTED (a
                # committed ref that was authored without the record ever
                # being created — F-4c1f9ab2). Claiming "renamed" for the
                # second kind invents a migration that never happened.
                adopted = ((row.get("metadata") or {})
                           .get("adopted_finding_ids") or [])
                kind = ("an ADOPTED id (the original was never created)"
                        if finding_id in adopted else "a rename")
                print(f"note: {finding_id} resolves to {row['finding_id']} "
                      f"via {kind}; showing that row.", file=sys.stderr)
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
        # On STDOUT, alongside the detail — see _redirect_banner.
        sys.stdout.write(_redirect_banner(row, args.finding_id))
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
    # `producer` is what the auto-close ownership gate reads
    # (lib/findings_writer.foreign_candidates). This path INSERTs directly
    # rather than going through FindingsWriter.emit(), so it used to set
    # `authored_by` alone — leaving the row indistinguishable from an untagged
    # legacy row, which the gate deliberately lets a script run close. A
    # hand-authored driver in a script-owned section was therefore auto-closed
    # by the next sweep of that section (F-d93b2328). Both keys are written:
    # `authored_by` stays for render-board.py, which reads it to separate
    # hand-authored rows from script ones.
    meta = {"authored_by": "policy-cli", "producer": "policy-cli",
            "subsection": args.subsection or "plan_driver"}
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


def cmd_finding_close(args, dsn):
    """Close a finding that no automated closer is allowed to touch.

    WHY THIS EXISTS (F-94d62930). The auto-close producer gate is deliberately
    strict: a run may only close rows IT could have re-emitted, so
    `check-all-versions.py` (producer 'script') correctly refuses to close rows
    stamped 'version-check-agent', and the reconcile backstop correctly refuses
    to speak for agent rows at all. Both refusals are right.

    The consequence nobody planned for: those rows became uncloseable. On
    2026-09-06 version/F-42f5913e and F-8730d341 were genuinely stale — the
    plans they referenced had been retired and coverage.py reported plan_drift
    empty — and there was no way to retire them. `finding` had list/show/ref/
    add/detail and no close, and a direct SQL UPDATE was blocked by the
    permission classifier. A correctly-scoped gate that strands rows forever
    just relocates the problem.

    This is the HUMAN path, so it demands what an automated closer cannot
    supply: an explicit reason, recorded on the row. A close with no stated
    reason is indistinguishable from the silent false-closes this gate exists to
    prevent.
    """
    with _connect(dsn) as conn, conn.cursor() as cur:
        row = _finding_row(cur, args.finding_id)
        if not row:
            print(f"finding {args.finding_id} not found", file=sys.stderr); return 1

        # Same two consent conditions as `detail`, for the same reason: closing
        # the wrong row is a silent loss, and both can occur independently.
        redirected = row["finding_id"] != args.finding_id
        if redirected and not args.follow_rename:
            print(f"{args.finding_id} resolves to {row['finding_id']} via a "
                  f"recorded prior id. Re-run against {row['finding_id']}, or "
                  f"pass --follow-rename to accept the redirect.", file=sys.stderr)
            return 1
        if row["resolved_at"] is not None:
            print(f"{row['finding_id']} is already resolved "
                  f"({row['resolved_at']}) — nothing to do.", file=sys.stderr)
            return 1

        # status and resolved_at are a SYMMETRIC pair under
        # ck_findings_resolved_status: resolved_at IS NULL <=> status <> 'resolved'.
        # Setting one without the other is rejected by the database, which is
        # exactly the split-state bug that constraint was added for.
        cur.execute(
            """UPDATE sweep_findings
                  SET status = 'resolved',
                      resolved_at = now(),
                      resolved_commit = %s,
                      metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object(
                          'closed_by', 'policy-cli',
                          'close_reason', %s::text,
                          'closed_at', now()::text)
                WHERE id = %s
             RETURNING finding_id, severity, title""",
            (args.commit, args.reason, row["id"]))
        # NOTE: this cursor uses a dict row factory (see _finding_row, which
        # indexes by name). Positional access raises KeyError: 0 — and because
        # the UPDATE has already committed by then, the row IS closed while the
        # command exits non-zero. Caught exactly that way on first use.
        out = cur.fetchone()
    print(f"closed {out['finding_id']} [{out['severity']}] {out['title'][:70]}")
    print(f"  reason: {args.reason}")
    return 0


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
        # A WRITE is materially different from a read: `security_detail` is the
        # private vulnerability payload, and filing it somewhere the operator
        # did not intend loses it from the live register with no error. TWO
        # independent conditions need explicit consent, and they are checked
        # separately because either can occur without the other.
        redirected = row["finding_id"] != args.finding_id
        dead = row["resolved_at"] is not None
        if redirected or dead:
            print(f"{args.finding_id} resolves to {row['finding_id']} "
                  f"(id={row['id']}, {'RESOLVED' if dead else 'open'})"
                  f"{' via a recorded prior id' if redirected else ''}.",
                  file=sys.stderr)
        # (a) The target is not the finding that was named.
        if redirected and not args.follow_rename:
            print(f"refusing to write private detail to a different finding "
                  f"than the one named. Re-run against {row['finding_id']}, "
                  f"or pass --follow-rename to accept the redirect.",
                  file=sys.stderr)
            return 1
        # (b) The target is CLOSED. Gating this on the id mismatch alone was a
        # hole: when every row under the named id is resolved, the exact-match
        # pass returns a closed stub, the ids agree, and the payload was filed
        # onto a dead row in silence — the precise outcome _finding_row's own
        # docstring says the liveness ordering exists to prevent. That ordering
        # only helps when a live row exists SOMEWHERE; it cannot help when none
        # does. Resolved duplicates are routine here (id groups with a dozen-plus
        # rows), so which stub wins is a `last_seen DESC, id DESC` tiebreak the
        # operator never chose.
        if dead and not args.allow_resolved:
            print(f"refusing to write private detail to a RESOLVED finding "
                  f"(id={row['id']}, resolved {row['resolved_at']:%Y-%m-%d}). "
                  f"Detail filed here is invisible on the board and will not "
                  f"be carried forward. Pass --allow-resolved if you are "
                  f"deliberately annotating history.", file=sys.stderr)
            return 1
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
    # Print the id actually WRITTEN. Echoing the requested id concealed the
    # redirect in exactly the case where it matters.
    print(f"updated {row['finding_id']}\n")
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
    ra.add_argument("--expires", metavar="YYYY-MM-DD",
                    help="last day this acceptance is in force")
    ra.add_argument("--no-expiry", action="store_true",
                    help="open-ended (condition-based) acceptance")
    ra.add_argument("--allow-expired", action="store_true",
                    help="record an acceptance whose deadline has already passed")
    ra.add_argument("--allow-drift", action="store_true",
                    help="accept a description that pins a patch version / count")
    ra.add_argument("--allow-nomatch", action="store_true",
                    help="accept a description that currently matches no open finding")
    ra.add_argument("--allow-broad", action="store_true",
                    help=f"accept a description matching more than "
                         f"{_BREADTH_CEILING} open findings")
    ra.add_argument("--register-only", metavar="ANCHOR",
                    help=f"this AR is enforced elsewhere, not by title match: "
                         f"<file>:<SYMBOL> (security-check.py:ACCEPTED_PRIVILEGED) "
                         f"or {POSTURE_ANCHOR}; implies --allow-nomatch")
    ra.set_defaults(handler=cmd_risk_add)
    rm = risk.add_parser("match",
                         help="preview which open findings a description would suppress")
    rm.add_argument("--description", required=True)
    rm.set_defaults(handler=cmd_risk_match)
    re_ = risk.add_parser("edit", help="update an existing AR in place")
    re_.add_argument("ar_id")
    re_.add_argument("--description")
    re_.add_argument("--severity")
    re_.add_argument("--justification")
    re_.add_argument("--expires", metavar="YYYY-MM-DD",
                     help="set the last day in force; 'none' clears it")
    re_.add_argument("--allow-drift", action="store_true",
                     help="accept a description that pins a patch version / count")
    re_.add_argument("--register-only", metavar="ANCHOR",
                     help=f"record where this AR is enforced (<file>:<SYMBOL> or "
                          f"{POSTURE_ANCHOR}); '{_CLEAR}' clears it")
    re_.set_defaults(handler=cmd_risk_edit)
    rlint = risk.add_parser("lint", help="report AR descriptions that are not drift-stable, "
                                         "inert, expired, or register-only (enforced elsewhere)")
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
    fc = fnd.add_parser("close", help="retire a finding no automated closer may touch")
    fc.add_argument("finding_id")
    fc.add_argument("--reason", required=True,
                    help="WHY it is being closed. Required: a close with no "
                         "stated reason is indistinguishable from the silent "
                         "false-closes the producer gate exists to prevent.")
    fc.add_argument("--commit", help="commit sha that resolved it, if any")
    fc.add_argument("--follow-rename", action="store_true",
                    help="accept closing the finding this id was RENAMED to")
    fc.set_defaults(handler=cmd_finding_close)
    fd = fnd.add_parser("detail", help="attach private detail / plan linkage to a finding")
    fd.add_argument("finding_id")
    fd.add_argument("--detail")
    fd.add_argument("--detail-file")
    fd.add_argument("--action")
    fd.add_argument("--plan", action="append")
    fd.add_argument("--component")
    fd.add_argument("--follow-rename", action="store_true",
                    help="accept writing the private detail to the finding this "
                         "id was RENAMED to, rather than refusing")
    fd.add_argument("--allow-resolved", action="store_true",
                    help="accept writing the private detail to a RESOLVED "
                         "finding (deliberately annotating history)")
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
