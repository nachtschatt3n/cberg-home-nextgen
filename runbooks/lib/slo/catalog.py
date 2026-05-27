"""Read the SLO catalog into typed dataclasses.

Source of truth: the `slo_definitions` table in sweep-history Postgres
(populated by Plan Phase 1.2's migration). Legacy YAML fallback at
`runbooks/slo-catalog.yaml` is retained for the Phase 1↔2 cutover; that
fallback (and the source YAML) are removed in Phase 2.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class BurnRateWindow:
    long: str           # e.g. "1h"
    short: str          # e.g. "5m"
    threshold: float    # burn-rate threshold above which we flag

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BurnRateWindow":
        return cls(long=d["long"], short=d["short"], threshold=float(d["threshold"]))


@dataclass(frozen=True)
class PromQuery:
    numerator: str
    denominator: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PromQuery":
        return cls(numerator=d["numerator"], denominator=d["denominator"])


@dataclass(frozen=True)
class EsQuery:
    # Numerator = "good" events; denominator = numerator + bad_events.
    # Each Lucene/KQL string is passed verbatim to the ES client.
    query_good: str
    query_bad: str
    index: str = "logstash-*"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EsQuery":
        return cls(
            query_good=d["query_good"],
            query_bad=d["query_bad"],
            index=d.get("index", "logstash-*"),
        )


@dataclass(frozen=True)
class HactlQuery:
    # Free-form for now — the hactl client is a stub. When wired, this
    # will reference doctor-check names and field paths.
    check: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "HactlQuery":
        return cls(check=d["check"])


@dataclass(frozen=True)
class SloDef:
    name: str
    description: str
    source: str             # "prom" | "es" | "hactl"
    kind: str               # "ratio" — only one supported in v1
    target: float           # 0.0–1.0
    window: str             # "7d", "30d", etc.
    prom: PromQuery | None = None
    es: EsQuery | None = None
    hactl: HactlQuery | None = None
    burn_rate_windows: tuple[BurnRateWindow, ...] = ()
    tags: tuple[str, ...] = ()

    def query(self) -> PromQuery | EsQuery | HactlQuery:
        """Return the source-specific query block. Raises if missing."""
        if self.source == "prom":
            if self.prom is None:
                raise ValueError(f"SLO {self.name!r} has source=prom but no `prom:` block")
            return self.prom
        if self.source == "es":
            if self.es is None:
                raise ValueError(f"SLO {self.name!r} has source=es but no `es:` block")
            return self.es
        if self.source == "hactl":
            if self.hactl is None:
                raise ValueError(f"SLO {self.name!r} has source=hactl but no `hactl:` block")
            return self.hactl
        raise ValueError(f"SLO {self.name!r} has unknown source={self.source!r}")


@dataclass(frozen=True)
class Catalog:
    version: int
    defaults: dict[str, Any]
    slos: tuple[SloDef, ...]


def _normalise_brws(raw: list[dict[str, Any]] | None) -> tuple[BurnRateWindow, ...]:
    if not raw:
        return ()
    return tuple(BurnRateWindow.from_dict(d) for d in raw)


def load(path: Path | str | None = None, *, dsn: str | None = None) -> Catalog:
    """Load the SLO catalog.

    Source-of-truth path:
      1. If `dsn` (or `SWEEP_PG_DSN` env) is set → query `slo_definitions`
         table in sweep_history. This is the canonical path after Plan
         Phase 1.3 (operator-curated policy in DB).
      2. Otherwise, if `path` is given (or default) AND the file exists →
         legacy YAML fallback. Kept for backwards compatibility during
         the cutover; this path is REMOVED in Plan Phase 2 when the
         source file is deleted.

    Burn-rate-window defaults: the YAML used a top-level `defaults` block;
    DB rows store per-SLO `burn_rate_windows` (nullable JSON). When the
    DB row's value is NULL, we fall back to a hard-coded default matching
    what the YAML's defaults block carried.
    """
    dsn = dsn or os.environ.get("SWEEP_PG_DSN")
    if dsn:
        return _load_from_db(dsn)
    # Legacy YAML path (Phase 1 ↔ Phase 2 bridge)
    yaml_path = Path(path) if path else None
    if yaml_path and yaml_path.is_file():
        return _load_from_yaml(yaml_path)
    raise RuntimeError(
        "no SLO catalog source available — set SWEEP_PG_DSN or supply a path"
    )


# Default burn-rate windows mirror what runbooks/slo-catalog.yaml's
# `defaults.burn_rate_windows` carried before Phase 1.3 migration. Used as
# fallback when a slo_definitions.burn_rate_windows column is NULL.
_DEFAULT_BRWS: tuple[BurnRateWindow, ...] = (
    BurnRateWindow(long="1h", short="5m",  threshold=14.4),
    BurnRateWindow(long="6h", short="30m", threshold=6.0),
    BurnRateWindow(long="3d", short="6h",  threshold=1.0),
)


def _load_from_db(dsn: str) -> Catalog:
    import psycopg
    from psycopg.rows import dict_row
    slos: list[SloDef] = []
    with psycopg.connect(dsn, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT name, description, source, kind, target, window_size,
                   query_json, burn_rate_windows, tags
              FROM slo_definitions
             WHERE enabled = true
             ORDER BY name
            """
        )
        for row in cur.fetchall():
            brws_raw = row["burn_rate_windows"]
            brws = _normalise_brws(brws_raw) if brws_raw else _DEFAULT_BRWS
            source = row["source"]
            q = row["query_json"] or {}
            slos.append(SloDef(
                name=row["name"],
                description=(row["description"] or "").strip(),
                source=source,
                kind=row["kind"],
                target=float(row["target"]),
                window=row["window_size"],
                prom=PromQuery.from_dict(q) if source == "prom" else None,
                es=EsQuery.from_dict(q)   if source == "es"   else None,
                hactl=HactlQuery.from_dict(q) if source == "hactl" else None,
                burn_rate_windows=brws,
                tags=tuple(row["tags"] or ()),
            ))
    return Catalog(version=3, defaults={"burn_rate_windows": [
        {"long": b.long, "short": b.short, "threshold": b.threshold}
        for b in _DEFAULT_BRWS
    ]}, slos=tuple(slos))


def _load_from_yaml(path: Path) -> Catalog:
    """Legacy YAML loader. Deleted in Plan Phase 2 along with the source file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level must be a mapping")

    version = int(data.get("version", 1))
    defaults = dict(data.get("defaults") or {})
    default_brws = _normalise_brws(defaults.get("burn_rate_windows"))

    slos_raw = data.get("slos") or []
    slos: list[SloDef] = []
    for entry in slos_raw:
        if not isinstance(entry, dict):
            continue
        name = entry["name"]
        source = entry.get("source", "prom")
        brws = _normalise_brws(entry.get("burn_rate_windows")) or default_brws
        slo = SloDef(
            name=name,
            description=(entry.get("description") or "").strip(),
            source=source,
            kind=entry.get("kind", "ratio"),
            target=float(entry["target"]),
            window=entry["window"],
            prom=PromQuery.from_dict(entry["prom"]) if "prom" in entry else None,
            es=EsQuery.from_dict(entry["es"]) if "es" in entry else None,
            hactl=HactlQuery.from_dict(entry["hactl"]) if "hactl" in entry else None,
            burn_rate_windows=brws,
            tags=tuple(entry.get("tags") or ()),
        )
        slos.append(slo)
    return Catalog(version=version, defaults=defaults, slos=tuple(slos))
