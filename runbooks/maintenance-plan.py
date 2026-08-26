#!/usr/bin/env python3
"""maintenance-plan — reconcile held updates ↔ plans ↔ maintenance windows.

The auto-updater HOLDS every non-safe update; each such update is supposed to
get an executable plan (written by an upgrade-planner-agent) that runs in one of
the scheduled maintenance windows (runbooks/maintenance-windows.yaml). This
script is the glue + the read the SWEEP uses to "check the schedule":

  * which held updates still have NO plan  → the sweep dispatches a planner
  * which plans are stale (PR moved/closed since the plan was written)
  * which window is next, and what's queued for it
  * capacity / reboot / interference warnings per window

It changes NOTHING (no merges, no git). Read-only reporting + JSON.

Usage:
    python3 runbooks/maintenance-plan.py            # human schedule report
    python3 runbooks/maintenance-plan.py --json     # machine-readable
"""
from __future__ import annotations

import argparse
import json
import re
import pathlib
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from lib.plan_matching import match_held_to_plan, target_covers  # noqa: E402

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
WINDOWS_YAML = SCRIPT_DIR / "maintenance-windows.yaml"
RISK_WEIGHT = {"low": 1, "medium": 2, "high": 3}
_WD = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
       "friday": 4, "saturday": 5, "sunday": 6}


def load_windows():
    return yaml.safe_load(WINDOWS_YAML.read_text())


def plans_dir(cfg):
    return REPO_ROOT / cfg.get("planning", {}).get("plans_dir", "runbooks/maintenance/plans")


def load_plans(cfg):
    """Parse frontmatter of every plan file. Returns list of dicts (+ _path)."""
    out = []
    d = plans_dir(cfg)
    for p in sorted(d.glob("*.md")):
        if p.name.lower() == "readme.md":
            continue
        text = p.read_text()
        if not text.startswith("---"):
            continue
        try:
            fm = text.split("---", 2)[1]
            meta = yaml.safe_load(fm) or {}
        except Exception:
            continue
        meta["_path"] = str(p.relative_to(REPO_ROOT))
        out.append(meta)
    return out


def _last_json_object(text: str):
    """The last top-level JSON object in `text`, or None.

    Belt-and-braces for the 2026-08-18 bug: auto-update.py now fences its
    stdout (see its `emit_json`), but a plain `json.loads` on that stdout meant
    ANY future library print silently degraded this to `0 held update(s)` — a
    number the sweep reports as fact. Scanning back from the last `{` recovers
    the payload instead.
    """
    depth = start = 0
    for i in range(len(text) - 1, -1, -1):
        if text[i] == "}":
            if depth == 0:
                start = i
            depth += 1
        elif text[i] == "{":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[i:start + 1])
                except Exception:
                    return None
    return None


def get_held():
    """(held, error) — held (non-safe) updates from the auto-updater, decoupled
    via subprocess. `error` is non-None when the count is UNKNOWN, which must
    never be rendered as zero."""
    try:
        p = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "auto-update.py"), "--json"],
            capture_output=True, text=True, timeout=300,
        )
    except Exception as e:
        return [], f"auto-update.py did not run: {type(e).__name__}: {e}"
    data = _last_json_object(p.stdout or "")
    if data is None:
        tail = (p.stderr or "").strip().splitlines()[-1:] or [""]
        return [], (f"auto-update.py --json produced no parseable JSON "
                    f"(rc={p.returncode}; last stderr: {tail[0][:120]})")
    return data.get("held", []), None


def next_occurrence(day_name, start_hhmm, today, now=None):
    """The next date this window runs — TIME-AWARE (fixed 2026-08-18, F-f95a8b52).

    `start_hhmm` was accepted and ignored, so a same-weekday window was always
    scheduled for TODAY regardless of the clock: at 23:17 on a Tuesday the tool
    announced "next window: tue-early 2026-08-18 05:00", ~18h in the PAST. That
    is not a cosmetic slip — the window agent and the sweep both read this to
    decide what is due, and a window in the past reads as "now".
    """
    if str(day_name).lower() == "daily":
        now2 = now or datetime.now()
        try:
            hh, mm = (int(x) for x in str(start_hhmm).split(":")[:2])
        except (TypeError, ValueError):
            return today
        if now2.date() == today and (now2.hour, now2.minute) >= (hh, mm):
            return today + timedelta(days=1)
        return today
    wd = _WD[day_name.lower()]
    delta = (wd - today.weekday()) % 7
    d = today + timedelta(days=delta)
    if delta == 0:
        now = now or datetime.now()
        try:
            hh, mm = (int(x) for x in str(start_hhmm).split(":")[:2])
        except (TypeError, ValueError):
            return d                      # unparseable start → keep old behaviour
        if now.date() == today and (now.hour, now.minute) >= (hh, mm):
            d += timedelta(days=7)        # today's slot has already started
    return d


def upcoming_windows(cfg, today, horizon_days=14, now=None):
    """List concrete window occurrences within the horizon, soonest first."""
    occ = []
    for w in cfg["windows"]:
        d = next_occurrence(w["day"], w["start"], today, now)
        step = 1 if str(w.get("day", "")).lower() == "daily" else 7
        bumps = range(0, horizon_days + 1, step) if step == 1 else (0, 7)
        for bump in bumps:  # daily: every day; weekly: this week + next
            dd = d + timedelta(days=bump)
            if (dd - today).days <= horizon_days:
                occ.append({**w, "date": dd.isoformat(),
                            "slot": f"{w['id']}:{dd.isoformat()}"})
    occ.sort(key=lambda x: (x["date"], x["start"]))
    return occ


def held_key(h):
    """Stable id for a held update: prefer PR number, else dep."""
    return f"pr{h['number']}" if h.get("number") else h.get("dep", "?")


def reconcile(cfg, today):
    held, held_error = get_held()
    plans = load_plans(cfg)
    validation_errors = validate_plans(cfg, plans)
    liveness_missing, liveness_verified = window_liveness(cfg, today)
    parity_errors, parity_verified = cron_parity(cfg)
    autonomy = load_autonomy_policy()
    exec_classes = []
    for p in plans:
        if p.get("status") in ("executed", "superseded", "reference"):
            continue
        cls, why = execution_class(p, autonomy)
        exec_classes.append({"plan_id": p.get("plan_id"), "class": cls,
                             "reason": why, "window": p.get("window")})

    # 1) held updates lacking a fresh plan.
    # Matching via lib/plan_matching (PR number / normalized names / version
    # pair). The previous inline lookup keyed plans by PR and by the held dep's
    # IMAGE BASENAME — the talos plan (pr: null, component "Talos Linux" vs dep
    # ghcr.io/siderolabs/installer) missed both, was reported NEEDS A PLAN
    # every sweep, and got a redundant planner dispatched every cycle.
    needs_plan, stale, ambiguous = [], [], []
    for h in held:
        plan, others = match_held_to_plan(h, plans)
        if others:
            ambiguous.append({"held": held_key(h),
                              "picked": plan.get("_path"),
                              "also_matched": [o.get("_path") for o in others]})
        if not plan:
            needs_plan.append({"key": held_key(h), "dep": h.get("dep"),
                               "pr": h.get("number"), "cur": h.get("cur"),
                               "new": h.get("new"), "gate": h.get("gate"),
                               "reason": h.get("reason")})
            continue
        # stale if the plan's target no longer covers the held bump. Version-
        # TOKEN comparison, not string equality: a prose target like
        # "talosVersion v1.13.9" is the same target as "v1.13.9".
        if plan.get("target") and h.get("new") and not target_covers(plan, h):
            stale.append({"plan": plan["_path"], "plan_target": plan.get("target"),
                          "now_target": h.get("new"), "component": plan.get("component")})
        # stale by age
        gen = plan.get("generated")
        if gen:
            try:
                age = (today - date.fromisoformat(str(gen))).days
                if age > cfg["planning"]["stale_after_days"] and plan.get("status") not in {"executed", "superseded"}:
                    stale.append({"plan": plan["_path"], "age_days": age,
                                  "component": plan.get("component"), "reason": "unused > stale_after_days"})
            except Exception:
                pass

    # plans whose PR is no longer held (merged elsewhere / closed) → superseded
    held_prs = {str(h.get("number")) for h in held}
    orphan = [p["_path"] for p in plans
              if p.get("pr") and str(p["pr"]) not in held_prs
              and p.get("status") not in {"executed", "superseded"}]

    # 2) window occupancy + warnings
    occ = upcoming_windows(cfg, today)
    win_by_slot = {w["slot"]: w for w in occ}
    # Capacity/over-time/interference are properties of the window ID (its
    # duration + risk budget), NOT of a specific dated occurrence. Keying those
    # checks on `occ` — which only spans horizon_days (14) — silently skipped
    # EVERY plan scheduled further out: media-naming-p3 at 240m in a 90m window
    # on a date 20 days away tripped nothing. A validation that quietly does not
    # run for two-thirds of the queue is the same silent-skip class as the ES
    # field bugs. Resolve the window def by id so the checks cover all plans.
    win_by_id = {w["id"]: w for w in cfg["windows"]}
    scheduled = {}
    for p in plans:
        slot = p.get("window")
        if slot:
            scheduled.setdefault(slot, []).append(p)

    warnings = []
    for slot, ps in scheduled.items():
        w = win_by_slot.get(slot) or win_by_id.get(slot.split(":", 1)[0])
        # missed window (date in the past, not executed)
        try:
            wdate = date.fromisoformat(slot.split(":", 1)[1])
            if wdate < today and any(p.get("status") != "executed" for p in ps):
                warnings.append(f"MISSED window {slot}: {sum(1 for p in ps if p.get('status')!='executed')} plan(s) not executed")
        except Exception:
            wdate = None
        if not w:
            continue
        load = sum(RISK_WEIGHT.get(p.get("risk", "medium"), 2) for p in ps)
        if load > w.get("capacity_risk", 4):
            warnings.append(f"OVER-CAPACITY {slot}: risk-load {load} > {w['capacity_risk']}")
        # TIME capacity — distinct from risk-load, and previously unchecked.
        # risk-load is a coarse "how much can go wrong" budget; it says nothing
        # about whether the work FITS. On 2026-08-15 four windows were silently
        # over-committed on time, including envoy-gateway-phase2 alone at 120m in
        # a 60m slot and the next morning's window at 120m in 90m. A plan that
        # cannot fit either overruns into the day or gets abandoned half-done,
        # which is worse than not starting it.
        mins = sum(int(p.get("est_duration_min") or 0) for p in ps)
        wmins = int(w.get("duration_min") or 0)
        if wmins and mins > wmins:
            warnings.append(
                f"OVER-TIME {slot}: est {mins}m of work in a {wmins}m window "
                f"(+{mins - wmins}m) — {', '.join(p.get('plan_id','?') for p in ps)}")
        elif wmins and mins > wmins * 0.9:
            warnings.append(
                f"TIGHT {slot}: est {mins}m of {wmins}m used — no slack for a "
                f"rollback if something goes wrong")
        if any(p.get("needs_reboot") for p in ps) and not w.get("allow_reboot"):
            warnings.append(f"REBOOT-IN-NONREBOOT {slot}: a needs_reboot plan is in a window with allow_reboot:false")
        # shallow interference flag (the window agent does the deep check)
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                a, b = ps[i], ps[j]
                sa = set((a.get("touches") or {}).get("namespaces", [])) & set((b.get("touches") or {}).get("namespaces", []))
                sh = set((a.get("touches") or {}).get("shared", [])) & set((b.get("touches") or {}).get("shared", []))
                if sa or sh:
                    warnings.append(f"INTERFERENCE {slot}: {a.get('plan_id')} ⋂ {b.get('plan_id')} share {sorted(sa|sh)}")

    # DEAD CROSS-REFERENCES. A depends_on/conflicts_with naming a plan_id that does
    # not exist is silently UNENFORCED — the sequencer finds nothing to order against
    # and proceeds as if the constraint were satisfied. It reads as a guard while
    # being no guard at all, and it appears NATURALLY: retiring an executed plan (as
    # the transient-plan convention requires) orphans every reference to it.
    # Found 2026-08-15: app-template-5.0 still guarded against `talos-v1.13.7`, long
    # since executed and deleted — so the rule stopping a mass workload churn from
    # landing on top of node drains had quietly stopped applying.
    # Same shape as the rest of this month's audit fixes: an unresolvable reference
    # scored as a satisfied one. See docs/sops/audit-script-correctness.md.
    known_ids = {p.get("plan_id") for p in plans if p.get("plan_id")}
    for p in plans:
        for key in ("depends_on", "conflicts_with"):
            refs = p.get(key) or []
            if isinstance(refs, str):
                refs = [refs]
            for r in refs:
                if not isinstance(r, str) or not r.strip():
                    continue
                if r.strip() not in known_ids:
                    warnings.append(
                        f"DEAD-REF {p.get('plan_id')}: {key} -> '{r.strip()}' names no "
                        f"existing plan — this guard is NOT enforced")

    # plans stuck waiting for an operator go/no-go — routed to OpenClaw home-operation
    # (keyed on plan_id), which owns the reminder cadence until answered.
    awaiting_go = [{"plan_id": p.get("plan_id"), "plan": p["_path"],
                    "component": p.get("component"), "target": p.get("target"),
                    "window": p.get("window")}
                   for p in plans if p.get("status") == "awaiting-go"]
    # Keys that must stay OPEN in OpenClaw's home-operation store, for the
    # sweep's `reconcile` call. This is EVERY non-terminal plan — not just
    # awaiting-go. Critically it includes SCHEDULED plans whose decision is
    # approved-and-pending-execution (e.g. an approved Talos upgrade queued for
    # its reboot window): reconcile must NOT auto-close those before the window
    # agent executes + resolves them, or the approval is lost. Only
    # executed/superseded plans drop out of the set (and get auto-closed).
    open_issue_keys = [p.get("plan_id") for p in plans
                       if p.get("plan_id") and p.get("status") not in ("executed", "superseded")]

    return {
        "today": today.isoformat(),
        "held_count": len(held),
        # non-None => held_count is NOT a fact; render it as unknown
        "held_error": held_error,
        "needs_plan": needs_plan,
        "ambiguous_matches": ambiguous,
        "validation_errors": validation_errors,
        "window_liveness": {"missing": liveness_missing,
                            "verified": liveness_verified},
        "cron_parity": {"errors": parity_errors, "verified": parity_verified},
        "execution_classes": exec_classes,   # REPORT-ONLY until P2.1b
        "stale": stale,
        "orphan_plans": orphan,
        "awaiting_go": awaiting_go,
        "open_issue_keys": open_issue_keys,
        "next_windows": occ[:6],
        "scheduled": {k: [p.get("plan_id") for p in v] for k, v in scheduled.items()},
        "warnings": warnings,
        "plan_status": {s: sum(1 for p in plans if p.get("status") == s)
                        for s in ["draft", "vetted", "scheduled", "awaiting-go", "executed", "blocked", "superseded"]},
    }


def human(r, cfg):
    held_txt = (f"{r['held_count']} held update(s)" if not r.get("held_error")
                else "held updates UNKNOWN ⚠")
    L = [f"== maintenance schedule · {r['today']} · {held_txt} =="]
    if r.get("held_error"):
        L.append(f"!! held-update lookup failed — count is NOT zero, it is unknown: {r['held_error']}")
    nxt = r["next_windows"][0] if r["next_windows"] else None
    if nxt:
        L.append(f"next window: {nxt['slot']} {nxt['start']} {cfg['timezone']} "
                 f"({nxt['duration_min']}m, cap {nxt['capacity_risk']}, reboot={'yes' if nxt.get('allow_reboot') else 'no'})")
    if r["needs_plan"]:
        L.append(f"\nNEEDS A PLAN ({len(r['needs_plan'])}) — dispatch an upgrade-planner-agent for each:")
        for n in r["needs_plan"]:
            L.append(f"  • {n['dep']} {n['cur']}→{n['new']} (PR #{n['pr']}, held:{n['gate']}) — {n['reason'][:80]}")
    else:
        L.append("\nall held updates have a plan ✅")
    ec = r.get("execution_classes") or []
    if ec:
        L.append("\nexecution classes (REPORT-ONLY — enforcement lands with P2.1b):")
        for e in ec:
            L.append(f"  {e['class']:<18} {e['plan_id']:<34} {e['reason']}")
    cp = r.get("cron_parity") or {}
    if not cp.get("verified", True):
        L.append("\n⚠️  cron↔YAML parity NOT VERIFIED (cron list unreadable) — the schedule's executor is unconfirmed")
    elif cp.get("errors"):
        L.append(f"\n❌ CRON↔YAML PARITY FAILURES ({len(cp['errors'])}):")
        for e in cp["errors"]:
            L.append(f"  ! {e}")
    wl = r.get("window_liveness") or {}
    if not wl.get("verified", True):
        L.append("\n⚠️  window liveness NOT VERIFIED (no DB access) — absence of findings here is not evidence the windows ran")
    elif wl.get("missing"):
        L.append(f"\n❌ WINDOWS DECLARED BUT NEVER RAN ({len(wl['missing'])}) — the schedule is fictional for these slots:")
        for m in wl["missing"]:
            L.append(f"  ! {m} — no window_runs row; check the OpenClaw cron and the window agent")
    if r.get("validation_errors"):
        L.append(f"\n❌ PLAN FRONTMATTER ERRORS ({len(r['validation_errors'])}) — fix before these plans can be trusted:")
        for e in r["validation_errors"]:
            L.append(f"  ! {e}")
    if r.get("ambiguous_matches"):
        L.append(f"\n⚠️  AMBIGUOUS plan matches ({len(r['ambiguous_matches'])}) — one held update matched several plans; picked the first, verify:")
        for a in r["ambiguous_matches"]:
            L.append(f"  • {a['held']}: picked {a['picked']}, also matched {a['also_matched']}")
    if r["stale"]:
        L.append(f"\nSTALE plans ({len(r['stale'])}) — re-investigate:")
        for s in r["stale"]:
            L.append(f"  • {s.get('component')}: {s}")
    if r["orphan_plans"]:
        L.append(f"\nORPHAN plans (PR no longer held) → mark superseded/delete: {r['orphan_plans']}")
    if r.get("awaiting_go"):
        L.append(f"\n🔔 AWAITING YOUR GO/NO-GO ({len(r['awaiting_go'])}) — re-remind the operator:")
        for a in r["awaiting_go"]:
            L.append(f"  • {a['component']} → {a['target']} (window {a.get('window')}) [{a['plan']}]")
    if r["scheduled"]:
        L.append("\nscheduled:")
        for slot, ids in r["scheduled"].items():
            L.append(f"  {slot}: {ids}")
    if r["warnings"]:
        L.append("\n⚠️  WARNINGS:")
        for w in r["warnings"]:
            L.append(f"  ! {w}")
    L.append(f"\nplan status: {r['plan_status']}")
    return "\n".join(L)




_VER_RE = re.compile(r'\bv?\d+\.\d+(?:\.\d+)?\b')


def already_done_suspects(cfg) -> list:
    """Plans whose TARGET version already appears pinned in the manifests.

    A plan can outlive its own work. flux-stack-v0.57 sat `scheduled` holding an
    operator-present, reboot-capable window for an upgrade that had executed
    eight days earlier — its file was simply never retired. Nothing surfaced it;
    it was found by accident during a manual vetting pass.

    This is a HEURISTIC, deliberately worded as "verify", not "stale": it greps
    the repo for the plan's target version. False positives are expected (a
    version string can appear in a comment). The point is to make the question
    get asked every run instead of never.

    STAGE-AWARENESS matters and is why this skips plans with unmet depends_on.
    A staged plan's `current:` describes its PREDECESSOR's end state, not today
    — grafana-chart-12 legitimately says "chart 11.6.1" while 10.5.15 is live.
    Comparing those against the cluster manufactures a false stale signal, which
    would be worse than no check at all.
    """
    plans = load_plans(cfg)
    done = {p.get("plan_id") for p in plans if p.get("status") == "executed"}
    out = []
    for pl in plans:
        if pl.get("status") in ("executed", "superseded"):
            continue
        deps = pl.get("depends_on") or []
        if isinstance(deps, str):
            deps = [deps]
        if any(d and d not in done for d in deps):
            continue  # staged: its `current` describes a future state
        tgt = str(pl.get("target") or "")
        vers = _VER_RE.findall(tgt)
        if not vers:
            continue
        # Scope the search to THIS component's own manifests. Searching the whole
        # repo matched `8.10.0` from an unrelated redis and `17.11` from another
        # postgres — 8 suspects, nearly all noise. A check that cries wolf gets
        # ignored, which is worse than no check.
        comp = str(pl.get("component") or "")
        if not comp:
            continue
        # Resolve the component to files by PATH SUBSTRING anywhere under
        # kubernetes/, not just kubernetes/apps/*/<component>/. That narrower
        # form looked right and was inert: `flux-stack` has no app directory
        # (flux lives in kubernetes/flux/ and apps/flux-system/), so the one
        # real already-done case this check exists for did not fire. Caught only
        # by re-injecting that plan as a ground-truth test.
        stem = comp.replace("-stack", "").replace("-", "")
        dirs = {f for f in pathlib.Path("kubernetes").rglob("*.yaml")
                if comp in str(f) or (len(stem) > 3 and stem in str(f).replace("-", ""))}
        if not dirs:
            continue
        blob = ""
        for f in dirs:
            try:
                blob += f.read_text()
            except Exception:
                pass
        hit = [v for v in vers if v in blob]
        if hit and len(hit) == len(vers):
            out.append((pl.get("plan_id"), tgt[:56], hit[:3]))
    return out

# ---------------------------------------------------------------------------
# Frontmatter invariants (P0.4). These exist because contradictions were being
# FILED, not caught: five plans carried `status: scheduled` with
# `window: null` (a plan that believes it is scheduled but names no slot is
# exactly how work silently never runs), one plan's depends_on named a plan
# file that has never existed (a guard that could not guard), and nothing
# checked that a window id in a plan corresponds to a window that exists.
# ---------------------------------------------------------------------------

_WINDOW_REF = __import__("re").compile(r"^([a-z0-9-]+):(\d{4}-\d{2}-\d{2})$")

# `reference` is the new legal status for plans deliberately OUTSIDE the
# window system (break-glass contingencies, attended projects). Named exactly
# what open_queue's tier already called them.
VALID_STATUSES = {
    "draft", "vetted", "scheduled", "awaiting-go", "approved", "awaiting-soak",
    "blocked", "executed", "superseded", "reference",
}


def validate_plans(cfg, plans=None) -> list[str]:
    """Machine-checkable frontmatter invariants. Returns error strings."""
    import datetime as _dt
    plans = plans if plans is not None else load_plans(cfg)
    win = {w["id"]: w for w in cfg.get("windows", [])}
    ids = {p.get("plan_id") for p in plans}
    errs = []
    for pl in plans:
        pid = pl.get("plan_id") or pl.get("_path")
        st = str(pl.get("status") or "").strip()
        w = pl.get("window")
        if st and st not in VALID_STATUSES:
            errs.append(f"{pid}: unknown status {st!r}")
        # a plan that claims a slot must name a real, dated, weekday-consistent one
        if st in ("scheduled", "awaiting-go", "approved"):
            if not w:
                errs.append(f"{pid}: status:{st} but window is null — "
                            f"a slotless '{st}' plan silently never runs "
                            f"(use status: reference if it is deliberately unwindowed)")
            else:
                m = _WINDOW_REF.match(str(w))
                if not m:
                    errs.append(f"{pid}: window {w!r} is not <window-id>:<YYYY-MM-DD>")
                elif m.group(1) not in win:
                    errs.append(f"{pid}: window id {m.group(1)!r} not declared in "
                                f"maintenance-windows.yaml — plans scheduled into "
                                f"nonexistent windows are how the sat-early backlog happened")
                else:
                    wd = _dt.date.fromisoformat(m.group(2)).strftime("%A").lower()
                    if win[m.group(1)]["day"] != "daily" and wd != win[m.group(1)]["day"]:
                        errs.append(f"{pid}: window {w} dates a {wd}, but "
                                    f"{m.group(1)} runs on {win[m.group(1)]['day']}")
                    dur = pl.get("est_duration_min")
                    if isinstance(dur, (int, float)) and dur > win[m.group(1)]["duration_min"]:
                        errs.append(f"{pid}: est_duration_min {dur} can never fit "
                                    f"{m.group(1)} ({win[m.group(1)]['duration_min']}m)")
        # reference plans must NOT name a window — that is the other half of the contract
        if st == "reference" and w:
            errs.append(f"{pid}: status:reference must not carry a window ({w})")
        # autonomy facts (P2.1): free-form values here would silently derive
        # HUMAN-GATED forever (fail-safe eats typos), so malformed = error.
        rc = pl.get("rollback_class")
        if rc is not None and rc not in ("git-revert", "backup-restore", "one-way"):
            errs.append(f"{pid}: rollback_class {rc!r} not in git-revert|backup-restore|one-way")
        cc = pl.get("capability_change")
        if cc is not None and not isinstance(cc, bool):
            errs.append(f"{pid}: capability_change must be a bare boolean, got {cc!r}")
        ao = pl.get("autonomy_override")
        if ao is not None and ao != "human-gated":
            errs.append(f"{pid}: autonomy_override may only RESTRICT (only legal value: human-gated)")
        # finding_refs bind a plan to the sweep findings it answers — the
        # plan-or-page pass (finding-triage.py) joins on them, so a malformed
        # ref silently un-plans a finding. Format-checked here.
        for ref in (pl.get("finding_refs") or []):
            if not __import__("re").fullmatch(r"F-[0-9a-f]{8}", str(ref)):
                errs.append(f"{pid}: finding_refs entry {ref!r} is not F-xxxxxxxx")
        # dependency refs must resolve. DEAD-REF is an ERROR, not a warning:
        # a guard pointing at nothing enforces nothing.
        for field in ("depends_on", "conflicts_with"):
            for ref in (pl.get(field) or []):
                if ref not in ids:
                    errs.append(f"{pid}: {field} -> {ref!r} names no existing plan "
                                f"— this guard is not enforced; resolve or delete "
                                f"the ref with a dated comment")
    return errs


# ---------------------------------------------------------------------------
# Window liveness (P1.3). Asserts every dated slot the YAML declares actually
# RAN, using the window_runs rows the window agent writes at close-out.
# Four of seven declared windows had no driving cron for weeks and nothing
# could notice: the only artifact of a window was its commits, so an idle
# window that ran and a window that never ran were indistinguishable.
# ---------------------------------------------------------------------------

# Occurrences before this date predate the window_runs mechanism and are not
# asserted — otherwise the check would fire for all of history on day one.
WINDOW_LIVENESS_EPOCH = date(2026, 8, 27)


def expected_slots(cfg, today, lookback_days=7):
    """Every (slot, date) the YAML says should have run: fully-past days only
    (today's window may legitimately not have fired yet), since the epoch."""
    days = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6}
    out = []
    for w in cfg.get("windows", []):
        day = str(w.get("day", "")).lower()
        wd = days.get(day)
        if wd is None and day != "daily":
            continue
        for back in range(1, lookback_days + 1):
            d = today - timedelta(days=back)
            if (day == "daily" or d.weekday() == wd) and d >= WINDOW_LIVENESS_EPOCH:
                out.append((w["id"], d.isoformat()))
    return sorted(out)


def missing_window_runs(expected, run_rows):
    """Pure logic, DB-free: expected (slot,date) pairs minus recorded ones."""
    have = {(str(s), str(d)) for s, d in run_rows}
    return [f"{s}:{d}" for s, d in expected if (s, d) not in have]


def window_liveness(cfg, today):
    """(missing, verified). verified=False when the DB is unreachable —
    an unreadable ledger must render as NOT CHECKED, never as all-clear."""
    expected = expected_slots(cfg, today)
    if not expected:
        return [], True
    dsn = __import__("os").environ.get("SWEEP_PG_DSN")
    if not dsn:
        return [], False
    try:
        import psycopg
        with psycopg.connect(dsn, connect_timeout=10) as c, c.cursor() as cur:
            cur.execute("SELECT slot, run_date::text FROM window_runs "
                        "WHERE run_date >= %s", (min(d for _, d in expected),))
            rows = cur.fetchall()
    except Exception:
        return [], False
    return missing_window_runs(expected, rows), True


# ---------------------------------------------------------------------------
# Execution classes (P2.1a — REPORT-ONLY until P2.1b flips enforcement).
# Derived from declared plan facts against runbooks/autonomy-policy.yaml.
# A plan cannot claim a class; it declares capability_change / rollback_class
# and the policy decides. Fail-safe: no policy, or missing facts => HUMAN-GATED.
# ---------------------------------------------------------------------------

AUTONOMY_POLICY_PATH = SCRIPT_DIR / "autonomy-policy.yaml"


def load_autonomy_policy(path=AUTONOMY_POLICY_PATH):
    try:
        d = yaml.safe_load(path.read_text()) or {}
        if not d.get("classes"):
            return None
        return d
    except Exception:
        return None


def execution_class(plan: dict, policy: dict | None) -> tuple[str, str]:
    """(class, reason). HUMAN-GATED unless the policy affirmatively says
    otherwise — absence of facts is absence of pre-approval."""
    if not policy:
        return "HUMAN-GATED", "autonomy policy missing/unparseable (fail-safe)"
    if str(plan.get("autonomy_override") or "").strip() == "human-gated":
        return "HUMAN-GATED", "plan restricts itself via autonomy_override"
    facts = {
        "capability_change": plan.get("capability_change"),
        "rollback_class": plan.get("rollback_class"),
        "needs_reboot": plan.get("needs_reboot"),
    }
    if facts["capability_change"] is True:
        # decisive on its own — no other fact can rescue a capability change
        return "HUMAN-GATED", "capability-changing — human-gated by policy"
    if facts["capability_change"] is None or facts["rollback_class"] is None:
        return "HUMAN-GATED", "facts not declared (capability_change/rollback_class)"
    shared = {str(x).lower() for x in ((plan.get("touches") or {}).get("shared") or [])}
    for cname, spec in policy.get("classes", {}).items():
        req = spec.get("require", {})
        if any(facts.get(k) != v for k, v in req.items()):
            continue
        if shared & {str(x).lower() for x in spec.get("forbid_shared", [])}:
            continue
        if spec.get("require_backup_gate") and not plan.get("backup_gate"):
            return "HUMAN-GATED", (f"matches {cname} but names no backup_gate — "
                                   f"an ungated backup-restore plan is not pre-approved")
        return cname.upper(), f"policy class {cname}"
    return "HUMAN-GATED", "matches no pre-approved class (default)"


def cron_parity(cfg):
    """(errors, verified) via window-crons.py --check --json. Unreachable
    cron list => verified=False — parity NOT checked is not parity held."""
    import subprocess
    try:
        pr = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "window-crons.py"), "--check", "--json"],
            capture_output=True, text=True, timeout=90)
        d = json.loads(pr.stdout or "{}")
        return d.get("errors", []), bool(d.get("verified"))
    except Exception:
        return [], False


def open_queue(cfg) -> str:
    """The canonical answer to "what plans are open?".

    Separates three things a flat file count conflates:
      EXECUTABLE  a unit of work someone can actually run in a window
      PROGRAMME   a parent/index doc whose stages are the executable units;
                  status:superseded, carries the goal and total duration
      REFERENCE   deliberately unwindowed — break-glass contingencies, or
                  attended projects that do not belong in the window system
    Counting all three together is how "33 plans" becomes a misleading answer.
    """
    plans = load_plans(cfg)
    ex, prog, ref = [], [], []
    for pl in plans:
        st, w = pl.get("status"), pl.get("window")
        if st in ("executed",):
            continue
        if st == "superseded":
            (ref if not _has_stages(pl, plans) else prog).append(pl)
        elif st == "reference":
            ref.append(pl)
        elif w:
            ex.append(pl)
        else:
            ref.append(pl)
    out = ["== open plans ==", ""]
    out.append(f"EXECUTABLE ({len(ex)}) — scheduled into a window")
    for pl in sorted(ex, key=lambda x: (str(x.get("window")), x.get("plan_id") or "")):
        out.append(f"  {str(pl.get('window')):<22} {pl.get('plan_id'):<36} "
                   f"{str(pl.get('status')):<10} {str(pl.get('risk')):<7} "
                   f"{pl.get('est_duration_min')}min")
    out += ["", f"PROGRAMME ({len(prog)}) — index docs; their stages are above"]
    for pl in sorted(prog, key=lambda x: x.get("plan_id") or ""):
        out.append(f"  {pl.get('plan_id'):<36} total {pl.get('est_duration_min')}min")
    out += ["", f"REFERENCE / UNWINDOWED ({len(ref)}) — deliberately not in a window"]
    for pl in sorted(ref, key=lambda x: x.get("plan_id") or ""):
        out.append(f"  {pl.get('plan_id'):<36} {str(pl.get('status')):<11} "
                   f"{pl.get('est_duration_min')}min")
    out += ["", f"total files {len(plans)}  |  executable {len(ex)}  "
                f"programme {len(prog)}  reference {len(ref)}"]
    return "\n".join(out)


def _has_stages(parent, plans) -> bool:
    """True if this plan is a PARENT INDEX whose work was split into stages.

    Keyed on the authoring convention: a parent's `target` says "delivered in
    N stages". Deliberately NOT "some other plan mentions this id" — that also
    matches a superseded plan referenced by whatever replaced it, which is a
    different thing entirely. ingress-nginx-1.15.6 is the case in point: it is
    superseded by the Envoy migration and kept as a BREAK-GLASS contingency,
    not split into stages of itself, so it belongs under reference.
    """
    return "delivered in" in str(parent.get("target") or "").lower()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="plans whose target version already appears pinned — verify whether the work is done")
    ap.add_argument("--validate", action="store_true",
                    help="check plan frontmatter invariants and exit (rc 1 on errors)")
    ap.add_argument("--open", action="store_true",
                    help="canonical open-plan queue, split executable/programme/reference")
    args = ap.parse_args(argv)
    cfg = load_windows()
    today = datetime.now().date()
    r = reconcile(cfg, today)
    if args.verify:
        sus = already_done_suspects(cfg)
        if not sus:
            print("no plans look already-done")
        else:
            print("VERIFY — target version already present in manifests:")
            for pid, tgt, hit in sus:
                print(f"  {pid:<34} target={tgt}  matched={hit}")
        return 0
    if args.validate:
        errs = validate_plans(cfg)
        if errs:
            print(f"PLAN FRONTMATTER ERRORS ({len(errs)}):")
            for e in errs:
                print(f"  ! {e}")
            return 1
        print("all plan frontmatter invariants hold")
        return 0
    if args.open:
        print(open_queue(cfg))
        return 0
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(human(r, cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
