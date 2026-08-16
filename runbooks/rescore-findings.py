#!/usr/bin/env python3
"""Re-scoring proof harness — PHASE 1 of the sweep risk-model redesign.

Pulls TODAY's real open security findings from the sweep_history Postgres,
runs each through runbooks.lib.risk_model.score(), and prints the BEFORE/AFTER
board so the operator can judge the contextual model before we wire routing.

  BEFORE : intrinsic severity distribution (critical / warning / accepted)
  AFTER  : contextual tier distribution (critical / high / medium / low)
  DELTA  : which currently-`critical` findings drop to medium/low (+ rationale)
           and which — if any — are genuine external+exploited CRITICALs.

This harness READS ONLY. It does NOT change what security-check.py emits or
suppresses (that is Phase 2). It prints to stdout for the operator and
PERSISTS NOTHING — no CVE IDs, KEV detail, or per-image counts leave this
process (public-repo rule).

Usage:
    python3 runbooks/rescore-findings.py            # auto port-forwards the DB
    SWEEP_PG_DSN=... python3 runbooks/rescore-findings.py
    python3 runbooks/rescore-findings.py --no-kev   # force KEV-unavailable demo
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rm = _load("risk_model", _REPO / "runbooks" / "lib" / "risk_model.py")
_policy = _load("policycli", _REPO / "runbooks" / "policy-cli.py")


# ---------------------------------------------------------------------------
# ANSI (board is for a human at a terminal)
# ---------------------------------------------------------------------------
class C:
    R = "\033[31m"; Y = "\033[33m"; G = "\033[32m"; B = "\033[34m"
    MAG = "\033[35m"; CYN = "\033[36m"; BOLD = "\033[1m"; DIM = "\033[2m"; X = "\033[0m"


TIER_COLOR = {rm.CRITICAL: C.R, rm.HIGH: C.MAG, rm.MEDIUM: C.Y, rm.LOW: C.G}
SEV_COLOR = {"critical": C.R, "warning": C.Y, "accepted": C.DIM}


def _resolve_dsn(explicit):
    return _policy._resolve_dsn(explicit)


def fetch_open_security_findings(dsn):
    import psycopg
    from psycopg.rows import dict_row
    conn = psycopg.connect(dsn, row_factory=dict_row)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT finding_id, severity, title, metadata
          FROM sweep_findings
         WHERE section = 'security' AND resolved_at IS NULL
         ORDER BY metadata->>'subsection', severity, title
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--postgres-dsn", default=os.environ.get("SWEEP_PG_DSN"))
    ap.add_argument("--no-kev", action="store_true",
                    help="simulate KEV feed unavailable (fail-soft demo)")
    ap.add_argument("--all-detail", action="store_true",
                    help="print every finding's tier, not just the delta")
    args = ap.parse_args(argv)

    # --- KEV (fail soft, visible) -------------------------------------------
    if args.no_kev:
        kev = rm.KevIndex(loaded=False, source="unavailable (--no-kev)")
    else:
        kev = rm.KevIndex.load()
    idx = rm.load_exposure_index()

    dsn, pf = _resolve_dsn(args.postgres_dsn)
    try:
        rows = fetch_open_security_findings(dsn)
    finally:
        _policy._stop(pf)

    findings = [rm.Finding.from_db_row(r) for r in rows]
    results = [(f, rm.score(f, exposure_index=idx, kev_index=kev)) for f in findings]

    # --- header --------------------------------------------------------------
    print(f"{C.BOLD}{C.B}{'='*74}{C.X}")
    print(f"{C.BOLD}{C.B} Contextual Re-Scoring Board — {len(findings)} open security findings{C.X}")
    print(f"{C.BOLD}{C.B}{'='*74}{C.X}")
    kw = C.G if kev.loaded else C.R
    print(f"KEV feed: {kw}{kev.source}{C.X}"
          + (f"  catalog {kev.catalog_version}  ({len(kev.cve_ids)} CVEs)" if kev.loaded else
             f"  {C.R}→ every exploited-axis is UNKNOWN (visible, not scored safe){C.X}"))
    print(f"Exposure index: {len(idx.external_unauth)} external-unauth apps, "
          f"{len(idx.external_auth)} external-auth (Authentik/self-auth), "
          f"{len(idx.internal_apps)} internal.\n")

    # --- BEFORE --------------------------------------------------------------
    before = Counter(f.intrinsic_severity for f in findings)
    print(f"{C.BOLD}BEFORE — intrinsic severity (what the sweep tags today){C.X}")
    for sev in ("critical", "warning", "accepted", "clean", "monitor", "deferred"):
        if before.get(sev):
            col = SEV_COLOR.get(sev, "")
            print(f"  {col}{sev:9}{C.X} {before[sev]}")
    print()

    # --- AFTER ---------------------------------------------------------------
    after = Counter(r.tier for _, r in results)
    print(f"{C.BOLD}AFTER — contextual tier (exposure × exploited × nature){C.X}")
    for tier in (rm.CRITICAL, rm.HIGH, rm.MEDIUM, rm.LOW):
        col = TIER_COLOR[tier]
        n = after.get(tier, 0)
        route = {rm.CRITICAL: "pages operator", rm.HIGH: "dashboard/briefing",
                 rm.MEDIUM: "maintenance queue", rm.LOW: "weekly batch"}[tier]
        print(f"  {col}{tier:9}{C.X} {n:4}   {C.DIM}({route}){C.X}")
    print()

    # --- exploited-axis honesty ---------------------------------------------
    unknowns = [(f, r) for f, r in results if r.unknown_exploited]
    kev_hits = [(f, r) for f, r in results if r.exploited is True]
    print(f"{C.BOLD}Exploited-axis coverage (honesty check){C.X}")
    with_cve = sum(1 for f in findings if f.cve_ids)
    print(f"  findings with parseable CVE IDs on record: {with_cve}/{len(findings)}")
    print(f"  {C.MAG}exploited-in-KEV: {len(kev_hits)}{C.X}   "
          f"{C.Y}UNKNOWN (no CVE recorded / feed down): {len(unknowns)}{C.X}")
    print(f"  {C.DIM}UNKNOWN is surfaced, never scored as safe — Phase-2 gap: the CVE\n"
          f"  check should record CVE IDs on every finding so KEV can assess them.{C.X}\n")

    # --- DELTA: currently-critical → lower -----------------------------------
    crit_before = [(f, r) for f, r in results if f.intrinsic_severity == "critical"]
    demoted = [(f, r) for f, r in crit_before if r.tier != rm.CRITICAL]
    survived = [(f, r) for f, r in crit_before if r.tier == rm.CRITICAL]

    print(f"{C.BOLD}DELTA — the {len(crit_before)} findings the sweep calls CRITICAL today{C.X}")
    if not crit_before:
        print("  (none)")
    for f, r in crit_before:
        arrow = f"{C.R}critical{C.X} → {TIER_COLOR[r.tier]}{r.tier.upper()}{C.X}"
        img = _img(f)
        print(f"  {f.finding_id}  {arrow}   {C.DIM}{img}{C.X}")
        print(f"      {r.rationale}")
    print()

    # --- genuine contextual criticals ---------------------------------------
    genuine = [(f, r) for f, r in results if r.tier == rm.CRITICAL]
    print(f"{C.BOLD}Genuine contextual CRITICALs (external-unauth + KEV + real vuln){C.X}")
    if not genuine:
        print(f"  {C.G}NONE.{C.X} No finding is externally-exposed AND exploited-in-the-wild "
              f"AND a real vuln.\n  On this homelab that is the expected, healthy state.")
    else:
        for f, r in genuine:
            print(f"  {C.R}{C.BOLD}{f.finding_id}{C.X}  {_img(f)}")
            print(f"      {r.rationale}")
    print()

    # --- notable elevations (accepted / warning that score spicy) -----------
    elevated = [(f, r) for f, r in results
                if f.intrinsic_severity in ("accepted", "warning")
                and r.tier in (rm.CRITICAL, rm.HIGH)]
    if elevated:
        print(f"{C.BOLD}Notable elevations — accepted/warning that score HIGH+ by context{C.X}")
        for f, r in sorted(elevated, key=lambda x: x[1].tier):
            tag = f"{SEV_COLOR.get(f.intrinsic_severity,'')}{f.intrinsic_severity}{C.X}"
            acc = " [accepted]" if f.accepted else ""
            print(f"  {f.finding_id}  {tag} → {TIER_COLOR[r.tier]}{r.tier.upper()}{C.X}{acc}   "
                  f"{C.DIM}{_img(f)}{C.X}")
            print(f"      {r.rationale}")
        print()

    if args.all_detail:
        print(f"{C.BOLD}All findings (tier | exposure | exploited | section){C.X}")
        for f, r in sorted(results, key=lambda x: (
                [rm.CRITICAL, rm.HIGH, rm.MEDIUM, rm.LOW].index(x[1].tier))):
            print(f"  {TIER_COLOR[r.tier]}{r.tier:8}{C.X} {r.exposure:15} "
                  f"{rm._exploited_word(r.exploited):18} {f.subsection:22} {f.finding_id}")

    return 0


def _img(f):
    return f.image or f.component or f.subsection


if __name__ == "__main__":
    raise SystemExit(main())
