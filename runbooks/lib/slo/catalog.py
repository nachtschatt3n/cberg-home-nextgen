"""Read the SLO catalog YAML into typed dataclasses.

The catalog file is `runbooks/slo-catalog.yaml` by default. Each `slos[i]`
entry becomes one `SloDef`. Unknown top-level keys are tolerated so the
schema can grow without breaking old loaders.
"""
from __future__ import annotations

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


def load(path: Path | str) -> Catalog:
    path = Path(path)
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
