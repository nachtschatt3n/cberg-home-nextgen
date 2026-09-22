"""SLO compliance + burn-rate math.

Given a windowed `RatioResult` (the average good/total over the SLO
window) and the SLO target, compute:

- compliance_pct: the actual SLI as a percentage
- target_pct: the configured target
- budget_remaining_pct: how much of the error budget is still unspent
  (100% = no errors yet, 0% = budget exhausted, negative = breaching)
- burn_rate_1h / burn_rate_6h: how fast the budget is being consumed
  at those windows, expressed as a multiplier (1.0 = consuming budget
  at exactly the rate that hits zero at window end; >1.0 = will breach
  before window end; <1.0 = will end window inside budget)

The burn-rate calculation uses a separate `windowed_ratio` query at the
shorter window. Caller is responsible for running those queries and
passing the results in.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SloSnapshot:
    """Computed values ready to INSERT into the `slo_snapshots` table.

    Field names mirror the column names in
    kubernetes/apps/databases/sweep-history/app/schema-configmap.yaml.

    `burn_rates` carries the burn at EVERY window the catalog declares for
    the SLO (`burn_rate_windows`, long and short), keyed by window label.
    The two columns `burn_rate_1h` / `burn_rate_6h` are the same numbers
    looked up by label — the table has no column for the other windows, so
    they travel in finding metadata (F-7f596ea3).
    """
    slo_name: str
    compliance_pct: float | None
    target_pct: float
    budget_remaining_pct: float | None
    burn_rate_1h: float | None
    burn_rate_6h: float | None
    window_size: str
    source: str
    raw_numerator: float | None
    raw_denominator: float | None
    burn_rates: dict[str, float | None] = field(default_factory=dict)


def burn_rate(short_window_compliance: float | None, target: float) -> float | None:
    """Burn rate at a short window relative to the SLO target.

    Math: error_rate = 1 - compliance. budget_rate = 1 - target.
    burn = error_rate / budget_rate.
        burn = 1.0  → budget exhausts in exactly `window_long` time
        burn > 1.0  → budget exhausts FASTER than window_long
        burn < 1.0  → operating inside budget

    Returns None when the short-window query had no data.
    """
    if short_window_compliance is None:
        return None
    budget_rate = 1.0 - target
    if budget_rate <= 0:
        return 0.0  # target is 100% → any error is infinite burn; flat 0 keeps it sane
    error_rate = 1.0 - short_window_compliance
    return error_rate / budget_rate


def budget_remaining(compliance: float | None, target: float) -> float | None:
    """Error budget remaining as a percentage of the original budget.

    100% → no errors consumed yet
    0%   → budget exactly exhausted (compliance == target)
    <0%  → breaching (compliance < target)

    Returns None when compliance is unknown.
    """
    if compliance is None:
        return None
    budget_rate = 1.0 - target
    if budget_rate <= 0:
        return 0.0 if compliance >= 1.0 else -100.0
    consumed_rate = 1.0 - compliance
    used_fraction = consumed_rate / budget_rate
    pct = (1.0 - used_fraction) * 100.0
    # Floor the value so a pathological reading (e.g. a scrape gap driving
    # compliance to ~0 against a 99.9% target → thousands of percent breached)
    # can never overflow the slo_snapshots.budget_remaining_pct column and crash
    # the canonical write, silently emptying the cycle (F-02c920ce). The column
    # is NUMERIC(8,2); -1e5 fits with headroom and still reads as "catastrophic".
    return max(pct, -100_000.0)


# Tolerance for float noise when checking the [0,1] compliance invariant.
_EPS = 1e-6


def defects(snap: "SloSnapshot") -> list[str]:
    """Impossible values that mean the SLO's own math is broken, not the service.

    A compliance ratio > 1.0 or a NEGATIVE burn rate is arithmetically
    impossible for a well-formed good/total SLI: it only happens when the
    numerator over-counts the denominator — classically a `sum(up{...})` that
    adds the `up` gauge across N replicas (so a 2-pod rollout yields 2/1 = 200%
    compliance and a burn of (1-2)/(1-target) < 0). A negative burn does not
    just look wrong, it MASKS the real burn (a true ~10.0 renders as -11.67),
    so it must surface as a defect instead of being published silently.

    Returns a list of human-readable defect strings (empty when the snapshot
    is sane). Pure — no I/O — so it is unit-testable and reusable.
    """
    out: list[str] = []
    c = snap.compliance_pct
    if c is not None and c > 100.0 + _EPS:
        out.append(
            f"compliance {c:.3f}% exceeds 100% — numerator over-counts the "
            f"denominator (a sum-over-replicas SLI reads >1.0 during rollouts)"
        )
    checked: list[tuple[str, float | None]] = [
        (f"burn_rate_{w}", br) for w, br in (snap.burn_rates or {}).items()]
    if not checked:
        checked = [("burn_rate_1h", snap.burn_rate_1h), ("burn_rate_6h", snap.burn_rate_6h)]
    for label, br in checked:
        if br is not None and br < -_EPS:
            out.append(
                f"{label}={br:.2f} is negative — arithmetically impossible; it "
                f"masks the real burn and points to a compliance ratio >1.0"
            )
    return out


def compute(
    *,
    slo_name: str,
    target: float,
    window: str,
    source: str,
    long_compliance: float | None,
    raw_numerator: float | None,
    raw_denominator: float | None,
    short_compliance_1h: float | None = None,
    short_compliance_6h: float | None = None,
    short_compliances: dict[str, float | None] | None = None,
) -> SloSnapshot:
    """Bundle a long-window compliance result and the short-window samples
    into a snapshot row ready for the DB.

    `short_compliances` maps a window LABEL (`"1h"`, `"5m"`, `"3d"`, …) to
    the compliance measured over that window — one entry per window the
    catalog declares. The two legacy keyword arguments are accepted for
    callers that still pass exactly 1h and 6h; they never override a label
    already present in `short_compliances`.
    """
    sc: dict[str, float | None] = dict(short_compliances or {})
    if short_compliance_1h is not None:
        sc.setdefault("1h", short_compliance_1h)
    if short_compliance_6h is not None:
        sc.setdefault("6h", short_compliance_6h)
    burns = {label: burn_rate(c, target) for label, c in sc.items()}
    return SloSnapshot(
        slo_name=slo_name,
        compliance_pct=(long_compliance * 100.0) if long_compliance is not None else None,
        target_pct=target * 100.0,
        budget_remaining_pct=budget_remaining(long_compliance, target),
        burn_rate_1h=burns.get("1h"),
        burn_rate_6h=burns.get("6h"),
        window_size=window,
        source=source,
        raw_numerator=raw_numerator,
        raw_denominator=raw_denominator,
        burn_rates=burns,
    )
