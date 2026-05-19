"""Backend clients for the SLO calculator.

Each client implements two methods:

    ratio(numerator_q, denominator_q, window) -> RatioResult
    instant_ratio(numerator_q, denominator_q) -> RatioResult

The Prom client is the only one with a real implementation in v1; ES and
hactl raise NotImplementedError so the multi-backend skeleton is wired
but the partial-readiness entries from sli-catalog.md don't accidentally
emit garbage SLOs.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .catalog import EsQuery, HactlQuery, PromQuery


@dataclass(frozen=True)
class RatioResult:
    """Result of a numerator/denominator measurement.

    `ratio` is good_events / total_events in [0.0, 1.0]. `numerator` and
    `denominator` are kept as raw counters for evidence rows in
    slo_snapshots. `ok` is False when the underlying query returned no
    data — caller skips DB write in that case.
    """
    ratio: float | None
    numerator: float | None
    denominator: float | None
    ok: bool


# ---------------------------------------------------------------------------
# Prometheus
# ---------------------------------------------------------------------------


class PromClient:
    """Minimal Prometheus HTTP API client. No external deps."""

    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        self.base_url = (base_url or os.environ.get("SLO_PROM_URL") or "").rstrip("/")
        if not self.base_url:
            raise RuntimeError(
                "Prometheus URL required — pass base_url or set SLO_PROM_URL"
            )
        self.timeout = timeout

    def _query(self, expr: str) -> float | None:
        """Run an instant `?query=<expr>` and return the scalar value or None."""
        url = f"{self.base_url}/api/v1/query?query={urllib.parse.quote(expr)}"
        with urllib.request.urlopen(url, timeout=self.timeout) as resp:
            payload = json.loads(resp.read())
        if payload.get("status") != "success":
            return None
        result = payload.get("data", {}).get("result") or []
        if not result:
            return None
        # `vector` shape: [{"metric": {...}, "value": [ts, "1.234"]}, ...]
        # Take the first sample's value. SLI queries should aggregate to
        # a single sample (count() / scalar()).
        try:
            value = float(result[0]["value"][1])
        except (KeyError, IndexError, ValueError):
            return None
        if value != value:  # NaN
            return None
        return value

    def instant_ratio(self, q: PromQuery) -> RatioResult:
        num = self._query(q.numerator)
        den = self._query(q.denominator)
        if num is None or den is None or den == 0:
            return RatioResult(None, num, den, ok=False)
        return RatioResult(ratio=num / den, numerator=num, denominator=den, ok=True)

    def windowed_ratio(self, q: PromQuery, window: str) -> RatioResult:
        """Time-averaged ratio over a window.

        The subquery `[<window>:]` goes INSIDE the avg_over_time() call so
        the inner instant-vector expression `(NUM)/(DEN)` is converted to a
        range vector that avg_over_time can integrate over.

        The numerator and denominator we return for evidence are the
        current instant samples — they're not time-averaged but they're a
        useful sanity check when the operator is reading the snapshot.
        """
        ratio_expr = (
            f"avg_over_time((({q.numerator}) / ({q.denominator}))[{window}:])"
        )
        ratio = self._query(ratio_expr)
        num = self._query(q.numerator)
        den = self._query(q.denominator)
        if ratio is None:
            return RatioResult(None, num, den, ok=False)
        return RatioResult(ratio=ratio, numerator=num, denominator=den, ok=True)


# ---------------------------------------------------------------------------
# Elasticsearch — stub until a partial-readiness SLO needs it
# ---------------------------------------------------------------------------


class EsClient:
    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        raise NotImplementedError(
            "ES client not implemented in v1 — see docs/sops/sli-catalog.md "
            "for the partial-readiness SLOs that will drive this work"
        )

    def instant_ratio(self, q: EsQuery) -> RatioResult:  # pragma: no cover
        raise NotImplementedError

    def windowed_ratio(self, q: EsQuery, window: str) -> RatioResult:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# hactl — stub until home-assistant-core SLO is promoted from partial
# ---------------------------------------------------------------------------


class HactlClient:
    def __init__(self, timeout: float = 30.0):
        raise NotImplementedError(
            "hactl client not implemented in v1 — see docs/sops/sli-catalog.md "
            "for the path-to-pilot-ready notes"
        )

    def instant_ratio(self, q: HactlQuery) -> RatioResult:  # pragma: no cover
        raise NotImplementedError

    def windowed_ratio(self, q: HactlQuery, window: str) -> RatioResult:  # pragma: no cover
        raise NotImplementedError
