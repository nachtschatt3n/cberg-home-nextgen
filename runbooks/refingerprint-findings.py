#!/usr/bin/env python3
"""Re-fingerprint sweep_findings after a change to the identity function.

WHY THIS EXISTS
---------------
`_stable_anchor()` used to fold the `[AR-0NN]` tag set into the fingerprint
basis. An AR tag is a SUPPRESSION DECISION — presentation applied on top of a
finding — so that made a finding's IDENTITY depend on its suppression state.
Adding, removing or re-wording an accepted risk silently forked a new row for
an unchanged problem, and "resolved" the old one.

Observed on the live register, 2026-08-18:

    F-094be167  born 08-16
                "resolved" 08-17 when AR-063 started matching -> forked F-e14cda04
                re-appeared 08-18 when AR-063's wording lapsed

One problem, three rows, nothing changed in the world. Auto-close then treats
the abandoned row as fixed, which is the exact "absence means fixed" failure
the findings lifecycle SOP exists to prevent — here triggered by a policy edit
rather than by a broken check.

The fix strips AR tags before anchoring and replaces the AR-tag component with
an explicit KIND token (see `_KIND_MARKERS` in findings_writer.py). Existing
rows carry fingerprints computed the old way, so without this migration every
open finding forks ONE MORE TIME on the next sweep — the very thing being
fixed. Run this once, immediately after deploying the writer change.

WHAT IT DOES
------------
1. Recomputes the fingerprint of every row with the CURRENT identity function.
2. Groups OPEN rows by new fingerprint. Where a group has more than one row the
   old function was over-splitting: keeps the earliest-`first_seen` row (so the
   age of the finding survives), widens its first_seen/last_seen to cover the
   whole group, and resolves the rest as migration duplicates.
3. Writes the new fingerprint + derived finding_id.
4. Ensures the partial UNIQUE index on `finding_id WHERE resolved_at IS NULL`
   — opportunistically, since creating it needs table ownership that the
   sweep_writer role lacks. Its real home is the sweep-history init Job
   (schema-configmap.yaml); this is belt-and-braces for an owner-DSN run.

On (4): `finding_id` was never unique — the live table holds two F-094be167
rows, one resolved and one open, because a recycled fingerprint re-derives the
same id. Every consumer that looks a finding up by id is therefore a latent
wrong-row bug unless it also qualifies on `resolved_at IS NULL`. Making it
unique among OPEN rows removes the trap where it matters while still letting a
genuinely recurring problem reuse its id after being resolved.

SAFETY
------
Dry-run by default; `--apply` is required to write. --apply runs in ONE
transaction and rolls back on any error. Nothing is deleted: superseded rows
are resolved with an explanatory `action`, never removed.

Usage:
    python3 runbooks/refingerprint-findings.py             # dry run
    python3 runbooks/refingerprint-findings.py --apply
    SWEEP_PG_DSN=... python3 runbooks/refingerprint-findings.py --apply
"""

from __future__ import annotations

import argparse
import importlib.util
import json as _json
import sys
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fw = _load("findings_writer", _REPO / "runbooks" / "lib" / "findings_writer.py")
pc = _load("policy_cli", _REPO / "runbooks" / "policy-cli.py")

MIGRATION_NOTE = (
    "Superseded by {keep} during the 2026-08-18 AR-independent fingerprint "
    "migration: the old identity function folded the [AR-nnn] tag set into the "
    "fingerprint, so these rows are the same finding split by suppression-state "
    "changes rather than by anything in the world."
)

INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_findings_open_finding_id
    ON sweep_findings(finding_id)
 WHERE resolved_at IS NULL
"""


def plan(rows: list[dict]) -> tuple[list[dict], list[tuple[dict, dict]], list[str]]:
    """Return (updates, supersedes, warnings) without touching the DB."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        r["_new_fp"] = fw.fingerprint(
            r["section"], (r["metadata"] or {}).get("subsection"), r["title"])
        groups[r["_new_fp"]].append(r)

    updates: list[dict] = []
    supersedes: list[tuple[dict, dict]] = []
    warnings: list[str] = []

    for fp, members in groups.items():
        members.sort(key=lambda x: x["first_seen"])
        keep = members[0]
        keep["_first_seen"] = min(m["first_seen"] for m in members)
        keep["_last_seen"] = max(m["last_seen"] for m in members)
        updates.append(keep)
        for dup in members[1:]:
            supersedes.append((dup, keep))

    # finding_id is derived from the first 8 hex of the fingerprint. Distinct
    # fingerprints colliding there is astronomically unlikely, but the partial
    # unique index would reject it at 3am rather than here, so check.
    by_id: dict[str, set] = defaultdict(set)
    for u in updates:
        by_id[fw.finding_id_from_fp(u["_new_fp"])].add(u["_new_fp"])
    for fid, fps in by_id.items():
        if len(fps) > 1:
            warnings.append(
                f"finding_id {fid} would be shared by {len(fps)} distinct "
                f"fingerprints — the unique index will reject this")
    return updates, supersedes, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    ap.add_argument("--postgres-dsn")
    args = ap.parse_args()

    dsn, pf = pc._resolve_dsn(args.postgres_dsn)
    try:
        with pc._connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, finding_id, fingerprint, section, title, metadata,
                           first_seen, last_seen, resolved_at, action
                      FROM sweep_findings
                     WHERE resolved_at IS NULL
                """)
                open_rows = [dict(r) for r in cur.fetchall()]
                cur.execute("SELECT count(*) n FROM sweep_findings WHERE resolved_at IS NOT NULL")
                n_closed = cur.fetchone()["n"]

            updates, supersedes, warnings = plan(open_rows)
            changed = [u for u in updates if u["_new_fp"] != u["fingerprint"]]

            print(f"open rows                  : {len(open_rows)}")
            print(f"resolved rows (untouched)  : {n_closed}")
            print(f"distinct new fingerprints  : {len(updates)}")
            print(f"identity changes to write  : {len(changed)}")
            print(f"rows superseded as dupes   : {len(supersedes)}")
            for w in warnings:
                print(f"  !! {w}")
            if supersedes:
                print("\nsupersede plan:")
                for dup, keep in supersedes:
                    print(f"  {dup['finding_id']} -> kept as "
                          f"{fw.finding_id_from_fp(keep['_new_fp'])}"
                          f"  :: {dup['title'][:70]}")
            if changed:
                print("\nsample identity changes (first 8):")
                for u in changed[:8]:
                    print(f"  {u['finding_id']} -> {fw.finding_id_from_fp(u['_new_fp'])}"
                          f"  :: {u['title'][:70]}")

            if warnings:
                print("\nREFUSING to apply while warnings are present.")
                return 1
            if not args.apply:
                print("\nDRY RUN — nothing written. Re-run with --apply.")
                return 0

            with conn.cursor() as cur:
                # Serialise against a concurrently running sweep. Without this
                # the plan is computed from a snapshot, a sweep can insert a
                # row whose fingerprint collides with one being rewritten, and
                # the post-check below only REPORTS the collision — it runs
                # after commit and cannot prevent it. Transaction-scoped, so it
                # releases on commit or rollback with no cleanup path to miss.
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('sweep_findings_refingerprint'))")
                for dup, keep in supersedes:
                    # `status` MUST move with `resolved_at`. The two columns are
                    # read by different consumers — the writer and every
                    # fingerprint query test `resolved_at`, render-board.py and
                    # the dashboard filter on `status != 'resolved'` — so setting
                    # one alone yields a row that auto-close treats as closed
                    # while the board still shows it as a live action item, and
                    # which sits outside uq_findings_open_finding_id so a later
                    # sweep can open a SECOND row with the same id. Enforced by
                    # ck_findings_resolved_status since init Job v5; kept
                    # explicit here so the intent survives a constraint drop.
                    cur.execute(
                        """UPDATE sweep_findings
                              SET resolved_at = now(),
                                  status = 'resolved',
                                  action = coalesce(action || ' | ', '') || %s
                            WHERE id = %s""",
                        (MIGRATION_NOTE.format(
                            keep=fw.finding_id_from_fp(keep["_new_fp"])), dup["id"]))
                for u in updates:
                    new_id = fw.finding_id_from_fp(u["_new_fp"])
                    # Keep every id this row has ever answered to. Committed
                    # `security_ref:` lines and plan files are immutable, so a
                    # rename must not orphan them — policy-cli._finding_row
                    # falls back to this list.
                    # Union of: ids this row already answered to, the ids of
                    # every row it supersedes AND the aliases THOSE rows had
                    # accumulated, plus this row's outgoing id. Taking only the
                    # dup's derived id would break the chain on a second
                    # migration — every alias earned in the first would be
                    # dropped, silently orphaning the oldest committed refs,
                    # which are the ones most likely to still be cited.
                    inherited: set[str] = set()
                    for d, k in supersedes:
                        if k["id"] != u["id"]:
                            continue
                        inherited.add(d["finding_id"])
                        inherited.update((d["metadata"] or {}).get(
                            "prior_finding_ids") or [])
                    priors = sorted({
                        *((u["metadata"] or {}).get("prior_finding_ids") or []),
                        *inherited,
                        u["finding_id"],
                    } - {new_id})
                    cur.execute(
                        """UPDATE sweep_findings
                              SET fingerprint = %s,
                                  finding_id  = %s,
                                  first_seen  = %s,
                                  last_seen   = %s,
                                  metadata    = coalesce(metadata, '{}'::jsonb)
                                                || jsonb_build_object(
                                                     'prior_finding_ids', %s::jsonb)
                            WHERE id = %s""",
                        (u["_new_fp"], new_id, u["_first_seen"], u["_last_seen"],
                         _json.dumps(priors), u["id"]))
            # The index is owned by the init Job (schema-configmap.yaml), which
            # runs as the table owner. Attempt it opportunistically: if this
            # migration is ever run with an owner DSN it lands immediately,
            # otherwise the Job delivers it. Failing the whole re-fingerprint
            # over a missing grant would be the wrong trade — the identity fix
            # is the urgent half.
            try:
                with conn.cursor() as cur:
                    cur.execute("SAVEPOINT idx")
                    cur.execute(INDEX_SQL)
                    cur.execute("RELEASE SAVEPOINT idx")
                index_note = "created/verified"
            except Exception as e:  # noqa: BLE001
                with conn.cursor() as cur:
                    cur.execute("ROLLBACK TO SAVEPOINT idx")
                index_note = (f"NOT created ({type(e).__name__}) — delivered by the "
                              f"sweep-history init Job instead; verify after it runs")
            conn.commit()
            print(f"\nAPPLIED: {len(changed)} identity change(s), "
                  f"{len(supersedes)} superseded.")
            print(f"unique index: {index_note}")

            with conn.cursor() as cur:
                cur.execute("""SELECT finding_id, count(*) n FROM sweep_findings
                                WHERE resolved_at IS NULL
                                GROUP BY 1 HAVING count(*) > 1""")
                dupes = cur.fetchall()
            print(f"post-check duplicate open finding_ids: {len(dupes)} (must be 0)")
            return 1 if dupes else 0
    finally:
        pc._stop(pf)


if __name__ == "__main__":
    raise SystemExit(main())
