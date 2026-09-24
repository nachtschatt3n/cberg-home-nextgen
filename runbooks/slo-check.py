#!/usr/bin/env python3
"""SLO check — read the catalog, query each backend, write snapshots.

One row per catalog SLO per run lands in `sweep_history.slo_snapshots`.
Existing markdown/JSON output is intentionally minimal — this script is
collector-shaped, not specialist-shaped.

Usage:
    python3 runbooks/slo-check.py
    python3 runbooks/slo-check.py --postgres-dsn "$WRITER_DSN" \
        --prom-url http://localhost:9090
    SLO_PROM_URL=...  SWEEP_PG_DSN=...  python3 runbooks/slo-check.py
    python3 runbooks/slo-check.py --once --no-write   # smoke test
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT  = SCRIPT_DIR.parent

# Self-activate mise toolchain so $SLO_PROM_URL etc are resolvable from any shell.
def _activate_mise() -> None:
    if os.environ.get("_MISE_ACTIVATED"):
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isfile(os.path.join(repo_root, ".mise.toml")):
        return
    mise = next(
        (os.path.join(p, "mise") for p in os.environ.get("PATH", "").split(os.pathsep)
         if os.path.isfile(os.path.join(p, "mise"))),
        None,
    )
    if not mise:
        return
    os.environ["_MISE_ACTIVATED"] = "1"
    os.execvp(mise, [mise, "-C", repo_root, "exec", "--", sys.executable, *sys.argv])

_activate_mise()

sys.path.insert(0, str(SCRIPT_DIR))
from lib.slo.catalog import load as load_catalog, SloDef  # noqa: E402
from lib.slo.clients import PromClient                    # noqa: E402
from lib.slo.calc    import compute, defects              # noqa: E402
from lib.slo.writer  import SloWriter                     # noqa: E402
from lib.findings_writer import (                          # noqa: E402
    FindingsWriter, cycle_id_from_env, trigger_from_env, git_head,
)


DEFAULT_CATALOG = REPO_ROOT / "runbooks" / "slo-catalog.yaml"

IN_CLUSTER_PROM = "http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090"
LOCAL_PROM      = "http://localhost:9090"  # sweep-run port-forward convention


def _default_prom_url() -> str:
    """In-cluster service DNS when resolvable, else the port-forward URL.

    Running on the Mac (the normal sweep case) the *.svc.cluster.local name
    never resolves, which used to force every caller to pass --prom-url
    manually. Explicit --prom-url / SLO_PROM_URL always win over this probe.
    """
    import socket
    try:
        socket.getaddrinfo(
            "kube-prometheus-stack-prometheus.monitoring.svc.cluster.local",
            9090,
        )
        return IN_CLUSTER_PROM
    except OSError:
        return LOCAL_PROM


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute SLO compliance + burn rates and persist to sweep-history.",
    )
    parser.add_argument(
        "--catalog",
        default=str(DEFAULT_CATALOG),
        help="Path to SLO catalog YAML (default: runbooks/slo-catalog.yaml)",
    )
    parser.add_argument(
        "--postgres-dsn",
        default=os.environ.get("SWEEP_PG_DSN"),
        help="DSN for sweep-history writer. Falls back to SWEEP_PG_DSN env.",
    )
    parser.add_argument(
        "--prom-url",
        default=os.environ.get("SLO_PROM_URL") or _default_prom_url(),
        help="Prometheus base URL (default: in-cluster service when its DNS "
             "resolves, else http://localhost:9090 for Mac-side runs)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print evaluation table and exit (no infinite loop — there is no loop yet).",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Compute but skip DB write. Useful with --once for smoke tests.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Restrict to this SLO name (repeatable).",
    )
    return parser.parse_args(argv)


def burn_window_labels(slo: SloDef) -> list[str]:
    """Every window the catalog DECLARES for this SLO — long AND short of each
    burn-rate pair — de-duplicated, in declaration order.

    Until 2026-09-22 this script queried a hardcoded `1h` and `6h` while
    `slo_definitions.burn_rate_windows` (1h/5m@14.4, 6h/30m@6.0, 3d/6h@1.0)
    was parsed by lib/slo/catalog.py and consumed by nothing: the per-SLO
    thresholds AND the declared 3d slow-burn window were read and never
    evaluated (F-7f596ea3). The windows evaluated are now the declared ones.
    """
    labels: list[str] = []
    for w in slo.burn_rate_windows:
        for label in (w.long, w.short):
            if label and label not in labels:
                labels.append(label)
    return labels


def _evaluate_prom(slo: SloDef, prom: PromClient) -> dict:
    """Run the long-window query plus one per DECLARED burn window."""
    q = slo.prom
    long_r = prom.windowed_ratio(q, slo.window)
    short = {label: prom.windowed_ratio(q, label).ratio for label in burn_window_labels(slo)}
    return {
        "long_compliance":   long_r.ratio,
        "raw_numerator":     long_r.numerator,
        "raw_denominator":   long_r.denominator,
        "short_compliances": short,
    }


def fast_burns(slo: SloDef, snap) -> list[dict]:
    """Declared burn-rate pairs whose LONG-window burn exceeds the declared
    threshold, with the short window's state alongside.

    The sweep is a point-in-time reading at 48h cadence, so it flags on the
    long window alone — that is the budget actually consumed — and reports
    whether the short window says the burn is still going or has subsided.
    (A PrometheusRule is what evaluates the two-window AND continuously; that
    half of F-7f596ea3 is a manifest, not this script.)
    """
    out: list[dict] = []
    rates = snap.burn_rates or {}
    for w in slo.burn_rate_windows:
        bl = rates.get(w.long)
        if bl is None or bl <= w.threshold:
            continue
        bs = rates.get(w.short)
        out.append({
            "long": w.long, "short": w.short, "threshold": w.threshold,
            "burn_long": bl, "burn_short": bs,
            "state": ("unknown" if bs is None else
                      "still burning" if bs > w.threshold else "subsided"),
        })
    return out


def main(argv: list[str] | None = None) -> int:
    """Crash veto — docs/sops/audit-script-correctness.md, incident 2026-08-24.

    sweep-run.py scores a step "completed" on rc in (0, 1, 2) -- 1/2 normally
    meaning "found findings". An uncaught Python traceback ALSO exits 1, so
    without this wrapper a mid-run crash reads as a clean pass and the
    auto-close step resolves every open slo finding this run never
    re-examined. Return 3 on purpose -- outside the "completed" set.
    """
    args = _parse_args(argv)
    try:
        return _main_impl(args)
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        try:
            with FindingsWriter(
                dsn=args.postgres_dsn,
                section="slo",
                cycle_id=cycle_id_from_env(),
                trigger=trigger_from_env(),
                git_head=git_head(),
                producer="script",
            ) as writer:
                writer.mark_incomplete(f"slo-check aborted: {type(exc).__name__}: {exc}")
                writer.close(verdict="red")
        except Exception as veto_exc:  # noqa: BLE001
            print(f"CRITICAL: the crash veto could not be recorded "
                  f"({type(veto_exc).__name__}: {veto_exc}) — open slo "
                  f"findings may be auto-closed by this cycle and must be "
                  f"re-verified by hand")
        return 3


def _main_impl(args) -> int:
    # Pass DSN explicitly so the loader uses the DB path. Falls back to the
    # legacy YAML when DSN is unset AND the file is still present.
    catalog = load_catalog(args.catalog, dsn=args.postgres_dsn)

    only = set(args.only)
    slos = [s for s in catalog.slos if (not only or s.name in only)]
    if not slos:
        print("No SLOs matched filter — nothing to do.", file=sys.stderr)
        return 0

    prom = PromClient(base_url=args.prom_url)
    write = not args.no_write and bool(args.postgres_dsn)

    print(f"SLO check — {len(slos)} SLO(s) · prom={args.prom_url} · "
          f"write={'YES' if write else 'no'}")
    print()

    snaps = []
    burning: dict[str, list[dict]] = {}
    for slo in slos:
        if slo.source != "prom":
            print(f"  · {slo.name}: source={slo.source} not implemented yet — skipping")
            continue
        if slo.prom is None:
            print(f"  · {slo.name}: missing prom: block — skipping")
            continue
        try:
            raw = _evaluate_prom(slo, prom)
        except Exception as exc:
            print(f"  ✗ {slo.name}: query error: {exc}", file=sys.stderr)
            continue

        snap = compute(
            slo_name=slo.name,
            target=slo.target,
            window=slo.window,
            source=slo.source,
            **raw,
        )
        snaps.append(snap)
        burning[slo.name] = fast_burns(slo, snap)
        c = f"{snap.compliance_pct:.3f}%" if snap.compliance_pct is not None else "—"
        b = f"{snap.budget_remaining_pct:+.1f}%" if snap.budget_remaining_pct is not None else "—"
        burns = "  ".join(
            f"burn{label}={('—' if br is None else f'{br:.2f}'):>5s}"
            for label, br in snap.burn_rates.items())
        print(f"  · {slo.name:36s}  compliance={c:>10s}  target={snap.target_pct:.2f}%  "
              f"budget={b:>7s}  {burns}")
        for fb in burning[slo.name]:
            bs = "—" if fb["burn_short"] is None else f"{fb['burn_short']:.2f}"
            print(f"    ⚠ FAST BURN [{slo.name}]: {fb['burn_long']:.2f}x over {fb['long']} "
                  f"(declared threshold {fb['threshold']}x; {fb['short']} window "
                  f"{bs}x, {fb['state']})", file=sys.stderr)
        for d in defects(snap):
            print(f"    ‼ DEFECT [{slo.name}]: {d}", file=sys.stderr)

    if write:
        with SloWriter(dsn=args.postgres_dsn) as w:
            for snap in snaps:
                w.emit(snap)
        print(f"\nWrote {len(snaps)} snapshot(s) to sweep-history.")

        # Exhausted error budgets must ALSO land in sweep_findings — snapshots
        # alone are invisible to the sweep's open-findings triage (the
        # 2026-07-12 unifi-device-availability incident produced snapshots but
        # no finding row, so the sweep report had to hand-assign N-01/N-02).
        exhausted = [
            s for s in snaps
            if s.budget_remaining_pct is not None and s.budget_remaining_pct <= 0
        ]
        # Snapshots whose math is impossible (compliance >100% or a negative
        # burn rate) — a broken SLO DEFINITION, not a service outage. These must
        # surface as findings instead of being published silently (F-1fb11f2e:
        # a sum-over-replicas numerator read burn -11.67, masking the real ~10).
        defective = [(s, ds) for s in snaps if (ds := defects(s))]
        # A burn above a DECLARED threshold is a finding in its own right: the
        # budget may still be positive, yet it is being spent faster than the
        # catalog says is acceptable (F-7f596ea3). Title carries only the
        # backticked name and the window, so it fingerprints stably per SLO
        # and window; the numbers live in action + metadata.
        fast = [(s, fb) for s in snaps for fb in burning.get(s.slo_name, [])]
        # Open the writer on EVERY write run, not only when there is something
        # to emit (F-4f717f3f): close() is what records notes.completed.slo, so
        # a clean run that never opened it left the board rendering the SLO
        # section as DID NOT REPORT despite the snapshots written above. A
        # clean close also auto-resolves last cycle's SLO findings, which is
        # the correct reading of "section ran, nothing to report".
        fw = FindingsWriter(dsn=args.postgres_dsn, section="slo", producer="script")
        try:
            for s, fb in fast:
                fid = fw.emit(
                    "warning",
                    f"SLO fast burn: `{s.slo_name}` over {fb['long']} exceeds "
                    f"its declared burn-rate threshold",
                    action=(
                        f"Investigate {s.slo_name}: burning {fb['burn_long']:.2f}x "
                        f"the budget rate over {fb['long']} (declared threshold "
                        f"{fb['threshold']}x); the {fb['short']} window reads "
                        f"{'—' if fb['burn_short'] is None else f'{fb['burn_short']:.2f}x'} "
                        f"({fb['state']}). Compliance {s.compliance_pct:.3f}% vs target "
                        f"{s.target_pct:.2f}% over {s.window_size}; budget "
                        f"{s.budget_remaining_pct:+.1f}%."
                    ),
                    subsection=s.slo_name,
                    metadata={
                        "window_long": fb["long"], "window_short": fb["short"],
                        "threshold": fb["threshold"],
                        "burn_long": fb["burn_long"], "burn_short": fb["burn_short"],
                        "state": fb["state"],
                        "burn_rates": s.burn_rates,
                        "compliance_pct": s.compliance_pct,
                        "budget_remaining_pct": s.budget_remaining_pct,
                        "window": s.window_size,
                    },
                )
                print(f"  ⚠ finding {fid}: fast burn over {fb['long']} for {s.slo_name}")
            for s in exhausted:
                fid = fw.emit(
                    "warning",
                    f"SLO error budget exhausted: {s.slo_name}",
                    action=(
                        f"Investigate {s.slo_name}: compliance "
                        f"{s.compliance_pct:.3f}% vs target {s.target_pct:.2f}% "
                        f"over {s.window_size}; budget {s.budget_remaining_pct:+.1f}%."
                    ),
                    subsection=s.slo_name,
                    metadata={
                        "compliance_pct": s.compliance_pct,
                        "target_pct": s.target_pct,
                        "budget_remaining_pct": s.budget_remaining_pct,
                        "burn_rate_1h": s.burn_rate_1h,
                        "burn_rate_6h": s.burn_rate_6h,
                        "window": s.window_size,
                    },
                )
                print(f"  ⚠ finding {fid}: budget exhausted for {s.slo_name}")
            for s, ds in defective:
                fid = fw.emit(
                    "warning",
                    # Backticked name → stable fingerprint across cycles.
                    f"SLO definition defect: `{s.slo_name}` produced an "
                    f"impossible value",
                    action=(
                        f"Fix the SLO query for {s.slo_name}: "
                        + "; ".join(ds)
                        + ". Bound the numerator (e.g. max(...) not "
                        "sum(...) across replicas) so compliance stays in "
                        "[0,1]. Edit via runbooks/policy-cli.py slo update."
                    ),
                    subsection=s.slo_name,
                    metadata={
                        "defects": ds,
                        "compliance_pct": s.compliance_pct,
                        "burn_rate_1h": s.burn_rate_1h,
                        "burn_rate_6h": s.burn_rate_6h,
                        "raw_numerator": s.raw_numerator,
                        "raw_denominator": s.raw_denominator,
                        "window": s.window_size,
                    },
                )
                print(f"  ‼ finding {fid}: definition defect for {s.slo_name}")
        finally:
            # A verdict is what marks the section complete (section_complete defaults
            # to verdict is not None): a bare close() records nothing and auto-closes
            # nothing (F-7be10f2c). yellow when anything was emitted, else green.
            fw.close(verdict="yellow" if (exhausted or defective or fast) else "green")
    elif args.no_write:
        print(f"\n--no-write set, {len(snaps)} snapshot(s) computed but NOT persisted.")
    else:
        print(f"\nNo DSN provided ({len(snaps)} snapshot(s) computed but NOT persisted).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
