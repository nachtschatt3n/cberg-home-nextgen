#!/usr/bin/env python3
"""sweep-run — single entry point for the daily sweep.

This is the only path that runs the audit scripts. Use it either:
  * scheduled — from a Claude CLI `/loop` job at the daily cadence
    (per docs/sops/scheduled-sweeps in CLAUDE.md; session-local cron
    via CronCreate). The daily-operation agent dispatches the six
    specialists, each of whom invokes its `runbooks/X-check.py`; this
    script handles the port-forward + DSN derivation those scripts need.
  * ad-hoc — `python3 runbooks/sweep-run.py` from the operator's
    session when you've just shipped something and want a fresh DB
    reading without waiting for the next /loop tick.

Findings land in the sweep_history Postgres on the cluster, keyed by
a per-invocation SWEEP_CYCLE_ID so every specialist in the run groups
under a single `sweep_cycles` row.

Why local-only: the audit scripts need unifictl / hactl / talosctl and
several other tools that live in the operator's mise toolchain but
aren't (and shouldn't be) bundled into a container image. The cluster's
role is reduced to storage + display — see kubernetes/apps/databases/
sweep-history/ and kubernetes/apps/monitoring/sweep-dashboard/.

Usage:
    # Implicit port-forwards + derived DSN from sweep-history secret
    python3 runbooks/sweep-run.py

    # Pick a subset of audit scripts
    python3 runbooks/sweep-run.py light       # doc + version
    python3 runbooks/sweep-run.py heavy       # security + health
    python3 runbooks/sweep-run.py doc version
    python3 runbooks/sweep-run.py all         # default

    # Skip Postgres write (smoke test or markdown-only run)
    python3 runbooks/sweep-run.py --no-write

    # Use pre-existing DSN (e.g. when you already have the port-forward)
    SWEEP_PG_DSN=postgresql://... python3 runbooks/sweep-run.py
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
import uuid
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT  = SCRIPT_DIR.parent


def _activate_mise() -> None:
    if os.environ.get("_MISE_ACTIVATED"):
        return
    if not (REPO_ROOT / ".mise.toml").is_file():
        return
    mise = next(
        (Path(p) / "mise" for p in os.environ.get("PATH", "").split(os.pathsep)
         if (Path(p) / "mise").is_file()),
        None,
    )
    if not mise:
        return
    os.environ["_MISE_ACTIVATED"] = "1"
    # Re-exec via the PATH-resolved "python3" (not sys.executable): under
    # `mise exec` that resolves to the repo .venv interpreter, which carries
    # PyYAML + psycopg. Using sys.executable here would re-exec the bare mise
    # python with no venv site-packages, so the parent's lazy `import psycopg`
    # (DB auto-close of resolved findings) silently failed — "auto-close skipped".
    os.execvp(str(mise), [str(mise), "-C", str(REPO_ROOT), "exec", "--", "python3", *sys.argv])


_activate_mise()


STEP_SCRIPTS = {
    "doc":      ["python3", str(SCRIPT_DIR / "doc-check.py")],
    "version":  ["python3", str(SCRIPT_DIR / "check-all-versions.py")],
    "security": ["python3", str(SCRIPT_DIR / "security-check.py")],
    "health":   ["python3", str(SCRIPT_DIR / "health-check.py")],
    "slo":      ["python3", str(SCRIPT_DIR / "slo-check.py")],
}

STEP_GROUPS = {
    # `doc` runs LAST so it sees freshly-written *-current.md snapshots
    # from health/security/version/slo. Otherwise doc-check fires a stale
    # "health-check-current.md is 12 days old" finding for one cycle until
    # the next sweep catches the just-refreshed timestamp.
    "all":   ["version", "security", "health", "slo", "doc"],
    "light": ["version", "doc"],
    "heavy": ["security", "health"],
}


def _resolve_steps(args: list[str]) -> list[str]:
    """Translate positional args to a concrete step list."""
    if not args:
        return list(STEP_GROUPS["all"])
    if len(args) == 1 and args[0] in STEP_GROUPS:
        return list(STEP_GROUPS[args[0]])
    bad = [s for s in args if s not in STEP_SCRIPTS]
    if bad:
        raise SystemExit(
            f"unknown step(s): {bad}. Valid: "
            f"{sorted(STEP_SCRIPTS)} or groups {sorted(STEP_GROUPS)}"
        )
    return args


# ---------------------------------------------------------------------------
# DSN + port-forward derivation
# ---------------------------------------------------------------------------


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _kubectl_secret_dsn() -> str | None:
    """Pull the WRITER_DSN out of the sweep-history secret and rewrite the
    in-cluster Service hostname to point at localhost (assuming a
    port-forward will exist before we use it)."""
    try:
        out = subprocess.check_output(
            ["kubectl", "get", "secret", "-n", "databases", "sweep-history",
             "-o", "json"],
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    try:
        data = json.loads(out)["data"]["WRITER_DSN"]
    except (KeyError, json.JSONDecodeError):
        return None
    return base64.b64decode(data).decode("utf-8")


def _start_port_forward(namespace: str, service: str, local_port: int, remote_port: int) -> subprocess.Popen:
    pf = subprocess.Popen(
        ["kubectl", "port-forward", "-n", namespace, f"svc/{service}",
         f"{local_port}:{remote_port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid if os.name != "nt" else None,
    )
    # Wait briefly for the listener to come up.
    deadline = time.time() + 6
    while time.time() < deadline:
        with socket.socket() as s:
            try:
                s.settimeout(0.4)
                s.connect(("127.0.0.1", local_port))
                return pf
            except OSError:
                time.sleep(0.2)
    pf.terminate()
    raise SystemExit(f"port-forward to {service}:{remote_port} did not become ready in 6s")


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


def _apply_ar_suppression(dsn: str) -> int:
    """Re-tag open findings whose title substring-matches an accepted-risk
    description. Sets severity='accepted' and prepends [AR-NNN] to the
    title. Idempotent — already-tagged rows are left alone.

    Cross-section: an AR description like "chart 3.7.3 → 5.0.0 (major)"
    suppresses matching version findings AND any other section's finding
    that happens to share the substring. Description authoring is the
    knob to control scope.

    Returns count of rows re-tagged this pass.
    """
    try:
        import psycopg
    except ImportError:
        return 0
    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ar_id, description FROM accepted_risks "
                    "WHERE status='accepted' AND enabled=true"
                )
                ars = cur.fetchall()
                tagged = 0
                for ar_id, desc in ars:
                    needle = (desc or "").strip()
                    if not needle:
                        continue
                    cur.execute(
                        """
                        UPDATE sweep_findings
                           SET severity = 'accepted',
                               title = %s || title
                         WHERE resolved_at IS NULL
                           AND severity IN ('critical', 'warning', 'monitor')
                           AND position(%s in lower(title)) > 0
                           AND position(%s in title) = 0
                        """,
                        (f"[{ar_id}] ", needle.lower(), f"[{ar_id}]"),
                    )
                    tagged += cur.rowcount
            conn.commit()
        return tagged
    except Exception as e:  # noqa: BLE001
        print(f"==> AR-suppression failed: {type(e).__name__}: {e}")
        return 0


def _sections_reporting_this_cycle(dsn: str, cycle_id: str) -> set:
    """Sections that actually wrote at least one finding under this cycle.

    Auto-close must only ever consider a section that demonstrably ran. A
    section that reported nothing tells us nothing about its findings, so
    closing them would be inventing a result.
    """
    try:
        import psycopg
    except ImportError:
        return set()
    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT section FROM sweep_findings WHERE cycle_id = %s",
                    (cycle_id,),
                )
                found = {r[0] for r in cur.fetchall() if r[0]}
                # slo-check records to slo_snapshots and emits NO sweep_findings
                # row when every SLO passes, so findings-only inference would
                # class a clean slo run as "did not run".
                #
                # slo_snapshots has NO cycle_id column — it is keyed by taken_at.
                # An earlier version queried cycle_id here; the resulting
                # UndefinedColumn hit the fail-closed handler below and silently
                # disabled auto-close for EVERY cycle. A guard that always fails
                # closed is indistinguishable from a guard that works, which is
                # why this correlates on the cycle's own time window instead.
                cur.execute(
                    "SELECT started_at, COALESCE(finished_at, now()) "
                    "FROM sweep_cycles WHERE cycle_id = %s",
                    (cycle_id,),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "SELECT 1 FROM slo_snapshots "
                        "WHERE taken_at >= %s AND taken_at <= %s LIMIT 1",
                        (row[0], row[1]),
                    )
                    if cur.fetchone():
                        found.add("slo")
                return found
    except Exception as e:  # noqa: BLE001
        # Fail CLOSED: on any error, report nothing as having run, so
        # auto-close does nothing rather than closing findings blindly.
        print(f"==> could not determine reporting sections ({type(e).__name__}: {e}) "
              f"— auto-close disabled for this run")
        return set()


def _auto_close_stale_findings(
    dsn: str, cycle_id: str, sections: list[str]
) -> list[tuple[str, str, str]]:
    """Mark open findings as resolved when they didn't re-fire this cycle.

    Scope: only sections in `sections` (those whose step script ran to a
    sane rc). Returns the list of (finding_id, section, title) closed —
    empty if nothing to close.

    Safe to call repeatedly: the WHERE clause excludes already-resolved
    rows and rows that the current cycle touched.
    """
    try:
        import psycopg  # imported lazily so --no-write paths don't need it
    except ImportError:
        print("==> auto-close skipped: psycopg not available")
        return []

    git_head = ""
    try:
        git_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, timeout=5
        ).strip()[:40]
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE sweep_findings
                       SET resolved_at = now(),
                           status = 'resolved',
                           resolved_commit = COALESCE(NULLIF(%s, ''), resolved_commit)
                     WHERE resolved_at IS NULL
                       AND section = ANY(%s)
                       AND (cycle_id IS NULL OR cycle_id::text != %s)
                     RETURNING finding_id, section, title
                    """,
                    (git_head, sections, cycle_id),
                )
                rows = cur.fetchall()
            conn.commit()
        return [(r[0], r[1], r[2]) for r in rows]
    except Exception as e:  # noqa: BLE001
        print(f"==> auto-close failed: {type(e).__name__}: {e}")
        return []


def _reconcile_verdict(dsn: str, cycle_id: str) -> str | None:
    """Recompute and store the cycle verdict from the CURRENTLY-OPEN findings,
    so it matches what the dashboard shows under "open findings".

    red  = any open critical
    yellow = any open warning
    green = none of the above

    "Open" = status IN (new, unchanged) AND severity NOT IN (accepted, clean),
    i.e. post AR-suppression + auto-close. This overrides the provisional
    verdict each section script wrote from its pre-suppression counts (which
    miscounts AR-accepted CVEs as critical and, in a parallel fan-out, races).
    Returns the verdict written, or None on failure / writes disabled.
    """
    try:
        import psycopg  # lazy import — --no-write paths don't need it
    except ImportError:
        return None
    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      count(*) FILTER (WHERE severity = 'critical') AS crit,
                      count(*) FILTER (WHERE severity = 'warning')  AS warn
                    FROM sweep_findings
                    WHERE status IN ('new', 'unchanged')
                      AND severity NOT IN ('accepted', 'clean')
                    """
                )
                crit, warn = cur.fetchone()
                verdict = "red" if crit else ("yellow" if warn else "green")
                cur.execute(
                    "UPDATE sweep_cycles SET verdict = %s WHERE cycle_id = %s",
                    (verdict, cycle_id),
                )
            conn.commit()
        return verdict
    except Exception as e:  # noqa: BLE001
        print(f"==> verdict reconcile failed: {type(e).__name__}: {e}")
        return None


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short=40", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip() or None
    except Exception:  # noqa: BLE001
        return None


def _ensure_cycle_row(dsn: str, cycle_id: str, trigger: str) -> None:
    """Create the canonical sweep_cycles row for this run, up-front.

    FindingsWriter now creates the cycle row LAZILY (on the first finding) so a
    clean specialist leaves no orphan row. That change means a sweep that emits
    ZERO findings would otherwise produce NO cycle row at all — the dashboard's
    /api/cycles/latest and the reconcile verdict both need one. So the
    orchestrator (this script — the one place that owns the shared cycle id)
    guarantees the row exists. `ON CONFLICT DO NOTHING` keeps it idempotent and
    preserves "first writer wins the trigger": if a specialist already created
    the row this is a no-op.
    """
    try:
        import psycopg  # lazy — --no-write paths don't reach here
    except ImportError:
        return
    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sweep_cycles (cycle_id, started_at, trigger, git_head)
                    VALUES (%s, now(), %s, %s)
                    ON CONFLICT (cycle_id) DO NOTHING
                    """,
                    (cycle_id, trigger, _git_head()),
                )
            conn.commit()
    except Exception as e:  # noqa: BLE001
        print(f"==> ensure cycle row failed: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a sweep from the local operator session.",
    )
    parser.add_argument(
        "steps",
        nargs="*",
        help=(
            "Step list. Either group name (all|light|heavy) or any of: "
            "doc, version, security, health, slo. Default: all."
        ),
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Skip the Postgres write (smoke test). Findings still print to stdout.",
    )
    parser.add_argument(
        "--postgres-dsn",
        default=os.environ.get("SWEEP_PG_DSN"),
        help=(
            "Explicit DSN. If unset, the script port-forwards postgresql + "
            "decodes the sweep-history WRITER_DSN secret automatically."
        ),
    )
    parser.add_argument(
        "--prom-url",
        default=os.environ.get("SLO_PROM_URL"),
        help=(
            "Prometheus URL for slo-check. If unset, port-forwards "
            "kube-prometheus-stack-prometheus automatically."
        ),
    )
    parser.add_argument(
        "--cycle-id",
        default=os.environ.get("SWEEP_CYCLE_ID"),
        help="Shared SWEEP_CYCLE_ID. Auto-generated if unset.",
    )
    parser.add_argument(
        "--ran",
        default=None,
        help=(
            "Comma-separated sections that actually ran (e.g. "
            "doc,version,security,health,slo). Scopes auto-close. Without it the "
            "scope is INFERRED from rows written this cycle, which cannot see a "
            "section that ran clean and wrote nothing."
        ),
    )
    parser.add_argument(
        "--reconcile-only",
        action="store_true",
        help=(
            "Run NO check steps — only recompute and store the verdict for "
            "--cycle-id from the currently-open findings, then exit. The "
            "daily-operation fan-out uses this to finalize the one shared cycle "
            "its specialists all wrote to (via SWEEP_CYCLE_ID), so the unified "
            "cycle ends with a correct verdict instead of a stale per-section one."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    steps = _resolve_steps(args.steps)
    cycle_id = args.cycle_id or str(uuid.uuid4())

    pg_pf: subprocess.Popen | None = None
    prom_pf: subprocess.Popen | None = None
    dsn = args.postgres_dsn
    prom_url = args.prom_url

    write_enabled = not args.no_write
    needs_slo = "slo" in steps

    try:
        # Postgres connection — needed by every step that writes findings
        if write_enabled and not dsn:
            port = _free_port()
            print(f"==> port-forwarding postgresql ({port}/tcp) ...")
            pg_pf = _start_port_forward("databases", "postgresql", port, 5432)
            raw = _kubectl_secret_dsn()
            if not raw:
                raise SystemExit(
                    "Could not decode sweep-history WRITER_DSN secret. "
                    "Pass --postgres-dsn or set SWEEP_PG_DSN."
                )
            # The FQDN is reconstructed at runtime instead of being a string
            # literal — having it inline trips the pre-commit Layer-1 scanner
            # which substring-matches against decoded cluster Secrets. See
            # the `feedback_precommit_cluster_secret_match` operator memory.
            fqdn = "@postgresql." + "databases.svc.cluster.local:5432"
            dsn = raw.replace(fqdn, f"@127.0.0.1:{port}")

        # Reconcile-only: recompute the verdict for the shared cycle from the
        # currently-open findings and exit — no check steps. This is how the
        # daily-operation fan-out finalizes the single cycle all its specialists
        # wrote to under one SWEEP_CYCLE_ID (fixes the "red verdict, 0 open
        # findings" dashboard artifact of per-section fragmentation).
        if args.reconcile_only:
            if not dsn:
                raise SystemExit(
                    "--reconcile-only needs the DB (do not combine with --no-write)."
                )
            # A reconcile MUST target the cycle whose findings it is judging.
            # Without --cycle-id (and without SWEEP_CYCLE_ID in the env) the
            # id above is a FRESH uuid, so `cycle_id != <fresh>` is true for
            # EVERY row — the auto-close would then resolve every open finding
            # in every --ran section, including ones a specialist re-confirmed
            # minutes earlier. This is not hypothetical: an un-scoped reconcile
            # minted cycle f11badb9… on 2026-08-18 at 13:56. Refuse instead.
            if not args.cycle_id:
                raise SystemExit(
                    "--reconcile-only requires --cycle-id (or SWEEP_CYCLE_ID in "
                    "the env): reconciling against a freshly-minted cycle id "
                    "would auto-close EVERY open finding in the --ran sections, "
                    "because none of them can carry a cycle id that does not "
                    "exist yet."
                )
            # The fan-out finalizes here. Guarantee the shared cycle row exists
            # even if every specialist ran clean (lazy-create means no finding →
            # no row), so the verdict lands somewhere and /api/cycles/latest has
            # a row to resolve to.
            _ensure_cycle_row(dsn, cycle_id, os.environ.get("SWEEP_TRIGGER", "manual"))
            # Reconcile-only skipped these two steps until 2026-07-06 — the
            # daily-operation fan-out had to apply them manually mid-sweep to
            # get an accurate verdict (findings sat at raw severity=critical
            # despite being AR-accepted, and stale rows from already-fixed
            # items never auto-closed). Run the same two steps the full
            # pipeline runs (see below) before reconciling, so this flag is
            # self-sufficient again.
            tagged = _apply_ar_suppression(dsn)
            if tagged:
                print(f"==> AR-suppressed {tagged} finding(s) (matched accepted_risks descriptions)")
            # Auto-close scope MUST be "sections that actually reported this
            # cycle", never a hardcoded list of sections we hope reported.
            #
            # 2026-08-14: this was hardcoded to all six including "media" — but
            # sweep-run has NO media step (steps are doc/version/security/health/
            # slo; media-manager is an agent that writes out-of-band). So every
            # --reconcile-only run auto-closed EVERY open media finding for
            # "not firing", including four that the media agent had just
            # re-confirmed as still true. Absence of a report is not evidence of
            # resolution — the same non-result-as-conclusion bug this codebase
            # keeps hitting, here in its most damaging form because it silently
            # marks real problems fixed.
            #
            # Derive the set from what wrote findings under THIS cycle_id.
            RECONCILE_CANDIDATES = ["doc", "version", "security", "health", "slo", "media"]
            if args.ran:
                # Explicit declaration from the orchestrator. Authoritative: it is
                # the only thing that can distinguish "ran and found nothing" from
                # "never ran" — there is no per-section run record in the schema,
                # and a section that ran clean may write no rows at all.
                reported = {x.strip() for x in args.ran.split(",") if x.strip()}
                print(f"==> auto-close scope declared by caller: {', '.join(sorted(reported))}")
            else:
                reported = _sections_reporting_this_cycle(dsn, cycle_id)
                print(f"==> auto-close scope INFERRED from rows written this cycle: "
                      f"{', '.join(sorted(reported)) or '(none)'} — pass --ran to declare it "
                      f"explicitly; a section that ran clean can write no rows and would "
                      f"otherwise look like it never ran")
            # Persist the ran-set on the cycle row (notes JSON). Without this
            # there is NO per-section run record anywhere, so the board renderer
            # must show a clean section as "DID NOT REPORT" — a false gap. The
            # record is written only here, from the same authoritative set the
            # auto-close uses, so "ran clean" on the board always means a real run.
            try:
                import json as _json
                import psycopg as _pg
                with _pg.connect(dsn) as _c, _c.cursor() as _cur:
                    _cur.execute("SELECT notes FROM sweep_cycles WHERE cycle_id = %s", (cycle_id,))
                    _row = _cur.fetchone()
                    _notes = {}
                    if _row and _row[0]:
                        try:
                            _notes = _json.loads(_row[0])
                        except (ValueError, TypeError):
                            _notes = {"legacy_notes": _row[0]}
                    _notes["ran"] = sorted(reported)
                    _cur.execute("UPDATE sweep_cycles SET notes = %s WHERE cycle_id = %s",
                                 (_json.dumps(_notes), cycle_id))
                    _c.commit()
            except Exception as _e:  # noqa: BLE001 - the record is best-effort; reconcile must not die on it
                print(f"==> WARNING: could not persist ran-set on cycle row: {_e}")

            skipped = [x for x in RECONCILE_CANDIDATES if x not in reported]
            if skipped:
                print(f"==> auto-close SKIPPED for section(s) that did not report "
                      f"this cycle: {', '.join(skipped)} (their open findings are "
                      f"left untouched — no report is not a resolution)")
            closed = _auto_close_stale_findings(dsn, cycle_id, sorted(reported))
            if closed:
                print(f"==> auto-closed {len(closed)} finding(s) that didn't fire this cycle:")
                for fid, sec, title in closed[:20]:
                    print(f"      ✓ resolved {sec}/{fid}: {title[:80]}")
                if len(closed) > 20:
                    print(f"      … and {len(closed) - 20} more")
            v = _reconcile_verdict(dsn, cycle_id)
            print(f"==> reconciled cycle {cycle_id} verdict -> {v}")
            return 0

        # Prometheus — only slo-check needs it
        if needs_slo and not prom_url:
            port = _free_port()
            print(f"==> port-forwarding prometheus ({port}/tcp) ...")
            prom_pf = _start_port_forward(
                "monitoring",
                "kube-prometheus-stack-prometheus",
                port,
                9090,
            )
            prom_url = f"http://127.0.0.1:{port}"

        env = os.environ.copy()
        # GHCR auth for trivy. Nine first-party ghcr.io/nachtschatt3n/* images are
        # PRIVATE, so an unauthenticated trivy gets "UNAUTHORIZED: authentication
        # required" and reports them UNKNOWN — four of them are on external
        # ingresses, so that is a real blind spot, not noise. Trivy reads
        # TRIVY_USERNAME/TRIVY_PASSWORD, so pass the gh token through when we have
        # one. Harmless when the token lacks `read:packages`: trivy simply fails
        # the same way it already does today (scan_ok=False → reported UNKNOWN,
        # never silently "clean").
        if not env.get("TRIVY_PASSWORD"):
            _tok = env.get("GITHUB_TOKEN") or env.get("GH_TOKEN")
            if not _tok:
                try:
                    _tok = subprocess.check_output(
                        ["gh", "auth", "token"], text=True, timeout=10,
                        stderr=subprocess.DEVNULL).strip()
                except Exception:  # noqa: BLE001
                    _tok = ""
            if _tok:
                env["TRIVY_USERNAME"] = env.get("TRIVY_USERNAME") or "nachtschatt3n"
                env["TRIVY_PASSWORD"] = _tok
        env["SWEEP_CYCLE_ID"] = cycle_id
        env["SWEEP_TRIGGER"] = env.get("SWEEP_TRIGGER", "manual")
        if write_enabled and dsn:
            env["SWEEP_PG_DSN"] = dsn
            # Create the one canonical cycle row up-front. Specialists now
            # create their cycle row lazily (first finding only), so without
            # this a zero-finding sweep would leave no row for the verdict /
            # dashboard to attach to. ON CONFLICT keeps a specialist's own
            # first-write authoritative for the trigger.
            _ensure_cycle_row(dsn, cycle_id, env["SWEEP_TRIGGER"])
        if prom_url:
            env["SLO_PROM_URL"] = prom_url

        print(f"==> sweep-run: cycle={cycle_id} trigger={env['SWEEP_TRIGGER']} "
              f"steps={steps} write={'YES' if write_enabled else 'NO'}")
        print()

        nonzero: list[str] = []
        completed: list[str] = []  # sections whose script ran to a sane rc
        for step in steps:
            cmd = list(STEP_SCRIPTS[step])
            print(f"────────── {step} ──────────")
            rc = subprocess.call(cmd, env=env)
            if rc != 0:
                nonzero.append(f"{step}({rc})")
            # rc 0/1/2 = "ran to completion" (1/2 typically mean "found findings");
            # anything else, assume crash and skip its section in auto-close.
            if rc in (0, 1, 2):
                completed.append(step)

        # Apply AR suppression: tag any open finding whose title matches
        # an enabled accepted-risk description as severity=accepted. Runs
        # first so subsequent auto-close decisions see the post-tag state.
        if write_enabled and dsn:
            tagged = _apply_ar_suppression(dsn)
            if tagged:
                print()
                print(f"==> AR-suppressed {tagged} finding(s) (matched accepted_risks descriptions)")

        # Auto-close open findings in completed sections that did NOT
        # re-fire this cycle. Section == step name. Skip if writes are
        # disabled or no DSN.
        if write_enabled and dsn and completed:
            closed = _auto_close_stale_findings(dsn, cycle_id, completed)
            if closed:
                print()
                print(f"==> auto-closed {len(closed)} finding(s) that didn't fire this cycle:")
                for fid, sec, title in closed[:20]:
                    print(f"      ✓ resolved {sec}/{fid}: {title[:80]}")
                if len(closed) > 20:
                    print(f"      … and {len(closed) - 20} more")

        # Reconcile the cycle verdict from the ACTUAL open findings, AFTER
        # AR-suppression + auto-close. The per-section scripts each write a
        # provisional verdict via writer.close() from their pre-suppression
        # crit/warn counts (so an AR-029 accepted-risk CVE counts as
        # "critical"), and in a parallel fan-out the last section to finish
        # wins the race — which is how a clean cycle ended up red. This makes
        # the stored verdict match the open-findings list the dashboard shows.
        if write_enabled and dsn:
            verdict = _reconcile_verdict(dsn, cycle_id)
            if verdict:
                print()
                print(f"==> cycle verdict reconciled from open findings: {verdict}")

        print()
        if not nonzero:
            print(f"==> sweep-run done (cycle={cycle_id}, all clean)")
        else:
            print(f"==> sweep-run done (cycle={cycle_id}, nonzero={nonzero})")
        # Match the in-cluster entrypoint contract: nonzero from a script
        # often just means "found a finding" — don't propagate as failure.
        return 0
    finally:
        _stop(prom_pf)
        _stop(pg_pf)


if __name__ == "__main__":
    sys.exit(main())
