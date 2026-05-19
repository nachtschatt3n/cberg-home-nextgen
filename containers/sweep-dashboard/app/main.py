"""sweep-dashboard — read-only FastAPI + HTMX view over sweep-history."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

import db


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.pool.open(wait=True, timeout=10)
    yield
    db.pool.close()


app = FastAPI(
    title="sweep-dashboard",
    description="Read-only view of cberg-home-nextgen daily-sweep findings.",
    lifespan=lifespan,
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _verdict_emoji(verdict: str | None) -> str:
    return {"green": "✅", "yellow": "⚠️", "red": "🚨"}.get(verdict or "", "—")


def _severity_emoji(severity: str | None) -> str:
    return {
        "critical": "🚨",
        "warning":  "⚠️",
        "monitor":  "🟡",
        "deferred": "⏸️",
        "clean":    "✅",
        "accepted": "🛡️",
    }.get(severity or "", "—")


def _section_emoji(section: str | None) -> str:
    return {
        "health":    "🩺",
        "security":  "🛡️",
        "version":   "🔢",
        "doc":       "📄",
        "media":     "🎬",
        "smarthome": "🏠",
        "slo":       "🎯",
        "infra":     "🔧",
        "carry":     "📌",
    }.get(section or "", "—")


def _burn_badge(burn_rate_1h: float | None, burn_rate_6h: float | None) -> dict[str, str]:
    """Map burn-rate thresholds to a colour-coded UI badge.

    Threshold tiers match the burn_rate_windows defaults in
    runbooks/slo-catalog.yaml:
        burn >= 14.4 over 1h  → 🔴 fast burn (paging)
        burn >=  6.0 over 6h  → 🟡 medium burn (warning)
        otherwise              → 🟢 healthy
        burn is None           → ⚪ no data
    """
    if burn_rate_1h is None and burn_rate_6h is None:
        return {"emoji": "⚪", "label": "no data", "css": "sev-deferred"}
    if burn_rate_1h is not None and burn_rate_1h >= 14.4:
        return {"emoji": "🔴", "label": "fast burn", "css": "sev-critical"}
    if burn_rate_6h is not None and burn_rate_6h >= 6.0:
        return {"emoji": "🟡", "label": "medium burn", "css": "sev-warning"}
    return {"emoji": "🟢", "label": "healthy", "css": "sev-clean"}


def _common() -> dict[str, Any]:
    """Template-context globals injected into every render."""
    return {
        "v_emoji": _verdict_emoji,
        "s_emoji": _severity_emoji,
        "sec_emoji": _section_emoji,
        "burn_badge": _burn_badge,
    }


# ---------------------------------------------------------------------------
# HTML routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    cycle = db.latest_cycle()
    counts = db.open_findings_counts()
    # Pivot counts into a {section: {severity: n}} dict for the template.
    grid: dict[str, dict[str, int]] = {}
    for row in counts:
        grid.setdefault(row["section"], {})[row["severity"]] = row["n"]
    return templates.TemplateResponse(
        request=request, name="index.html",
        context={**_common(), "cycle": cycle, "grid": grid},
    )


@app.get("/findings", response_class=HTMLResponse)
def findings(request: Request, section: str | None = None, severity: str | None = None):
    rows = db.open_findings(section=section, severity=severity)
    return templates.TemplateResponse(
        request=request, name="findings.html",
        context={**_common(), "rows": rows, "section": section, "severity": severity},
    )


@app.get("/findings/{finding_id}", response_class=HTMLResponse)
def finding_detail(request: Request, finding_id: str):
    history = db.finding_history(finding_id)
    if not history:
        raise HTTPException(404, f"finding {finding_id} not found")
    return templates.TemplateResponse(
        request=request, name="finding_detail.html",
        context={**_common(), "finding_id": finding_id, "history": history},
    )


@app.get("/cycles", response_class=HTMLResponse)
def cycles(request: Request):
    rows = db.recent_cycles()
    return templates.TemplateResponse(
        request=request, name="cycles.html",
        context={**_common(), "rows": rows},
    )


@app.get("/slos", response_class=HTMLResponse)
def slos(request: Request):
    rows = db.latest_slo_snapshots()
    return templates.TemplateResponse(
        request=request, name="slos.html",
        context={**_common(), "rows": rows},
    )


@app.get("/slos/{name}", response_class=HTMLResponse)
def slo_detail(request: Request, name: str):
    history = db.slo_history(name)
    if not history:
        raise HTTPException(404, f"SLO {name} not found")
    return templates.TemplateResponse(
        request=request, name="slo_detail.html",
        context={**_common(), "name": name, "history": history},
    )


# ---------------------------------------------------------------------------
# JSON API — consumed by the daily-operation orchestrator and Homepage card
# ---------------------------------------------------------------------------


@app.get("/api/cycles/latest", response_class=JSONResponse)
def api_latest_cycle():
    cycle = db.latest_cycle()
    if not cycle:
        return {"cycle": None, "findings": [], "counts": {}}
    findings_list = db.open_findings()
    counts: dict[str, dict[str, int]] = {}
    for row in db.open_findings_counts():
        counts.setdefault(row["section"], {})[row["severity"]] = row["n"]
    return {"cycle": cycle, "findings": findings_list, "counts": counts}


@app.get("/api/findings", response_class=JSONResponse)
def api_findings(section: str | None = None, severity: str | None = None):
    return db.open_findings(section=section, severity=severity)


@app.get("/api/slos", response_class=JSONResponse)
def api_slos():
    return db.latest_slo_snapshots()


@app.get("/api/slos/{name}", response_class=JSONResponse)
def api_slo_detail(name: str, limit: int = 200):
    history = db.slo_history(name, limit=limit)
    if not history:
        raise HTTPException(404, f"SLO {name} not found")
    return history


@app.get("/api/health", response_class=PlainTextResponse)
def api_health():
    if db.health():
        return "ok"
    raise HTTPException(503, "db unreachable")


@app.get("/api/ready", response_class=PlainTextResponse)
def api_ready():
    return api_health()
