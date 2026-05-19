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
from lib.slo.calc    import compute                       # noqa: E402
from lib.slo.writer  import SloWriter                     # noqa: E402


DEFAULT_CATALOG = REPO_ROOT / "runbooks" / "slo-catalog.yaml"


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
        default=os.environ.get("SLO_PROM_URL", "http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090"),
        help="Prometheus base URL (default: in-cluster service)",
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


def _evaluate_prom(slo: SloDef, prom: PromClient) -> dict:
    """Run all three queries (long window + 1h + 6h) and return raw numbers."""
    q = slo.prom
    long_r = prom.windowed_ratio(q, slo.window)
    short_1h = prom.windowed_ratio(q, "1h")
    short_6h = prom.windowed_ratio(q, "6h")
    return {
        "long_compliance":      long_r.ratio,
        "raw_numerator":        long_r.numerator,
        "raw_denominator":      long_r.denominator,
        "short_compliance_1h":  short_1h.ratio,
        "short_compliance_6h":  short_6h.ratio,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    catalog = load_catalog(args.catalog)

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
        c = f"{snap.compliance_pct:.3f}%" if snap.compliance_pct is not None else "—"
        b = f"{snap.budget_remaining_pct:+.1f}%" if snap.budget_remaining_pct is not None else "—"
        br1 = f"{snap.burn_rate_1h:.2f}" if snap.burn_rate_1h is not None else "—"
        br6 = f"{snap.burn_rate_6h:.2f}" if snap.burn_rate_6h is not None else "—"
        print(f"  · {slo.name:36s}  compliance={c:>10s}  target={snap.target_pct:.2f}%  "
              f"budget={b:>7s}  burn1h={br1:>5s}  burn6h={br6:>5s}")

    if write:
        with SloWriter(dsn=args.postgres_dsn) as w:
            for snap in snaps:
                w.emit(snap)
        print(f"\nWrote {len(snaps)} snapshot(s) to sweep-history.")
    elif args.no_write:
        print(f"\n--no-write set, {len(snaps)} snapshot(s) computed but NOT persisted.")
    else:
        print(f"\nNo DSN provided ({len(snaps)} snapshot(s) computed but NOT persisted).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
