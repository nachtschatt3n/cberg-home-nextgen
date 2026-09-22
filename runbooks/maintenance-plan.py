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
from datetime import date, datetime, timedelta, timezone
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


def on_demand_slot(cfg) -> dict | None:
    """The top-level `on_demand:` slot (the operator-triggered NOW run), or None.

    Deliberately NOT part of `windows:` (see the YAML comment): cron parity,
    per-occurrence liveness and the scheduler all read `windows:` and must
    never see a slot that has no schedule. Consumers that DO need it — plan
    window-ref validation, stuck-row detection, the reconciler's per-slot
    checks, run-now.py — ask for it here. A block without an `id` is treated
    as absent (fail closed: a `now:` ref then fails validation as undeclared).
    """
    od = (cfg or {}).get("on_demand")
    if not isinstance(od, dict) or not str(od.get("id") or "").strip():
        return None
    return {**od, "id": str(od["id"]).strip()}


def plans_dir(cfg):
    return REPO_ROOT / cfg.get("planning", {}).get("plans_dir", "runbooks/maintenance/plans")


# Files in the plans directory that load_plans() could NOT turn into a plan,
# as "<relative path>: <why>". Reset on every load. F-6a398b8b (2026-09-15):
# the loader used to `continue` past an unparseable frontmatter, so a plan
# with one unquoted `: ` inside a `premises.run:` value vanished from
# --validate ("all invariants hold"), --open and the premises gate ("no
# matching plans") at once — a BROKEN plan read as NO plan, which is the
# plan-or-page gap wearing a different hat. A scheduled plan that becomes
# unparseable would silently drop out of every window. Callers surface this
# list: validate_plans() turns it into errors, reconcile() carries it in
# validation_errors, plan-premises.py refuses to treat a named-but-unreadable
# plan as absent.
PLAN_LOAD_ERRORS: list[str] = []


def load_plans(cfg):
    """Parse frontmatter of every plan file. Returns list of dicts (+ _path).

    Populates PLAN_LOAD_ERRORS with every file it had to skip and why.
    """
    out = []
    PLAN_LOAD_ERRORS.clear()
    d = plans_dir(cfg)
    for p in sorted(d.glob("*.md")):
        if p.name.lower() == "readme.md":
            continue
        rel = str(p.relative_to(REPO_ROOT)) if str(p).startswith(str(REPO_ROOT)) else str(p)
        text = p.read_text()
        if not text.startswith("---"):
            PLAN_LOAD_ERRORS.append(f"{rel}: no frontmatter (file does not start with '---')")
            continue
        try:
            fm = text.split("---", 2)[1]
            meta = yaml.safe_load(fm) or {}
        except Exception as e:
            first = (str(e).splitlines() or [""])[0][:160]
            PLAN_LOAD_ERRORS.append(f"{rel}: frontmatter unparseable — {type(e).__name__}: {first}")
            continue
        if not isinstance(meta, dict):
            PLAN_LOAD_ERRORS.append(f"{rel}: frontmatter is not a mapping ({type(meta).__name__})")
            continue
        meta["_path"] = rel
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


# A plan in one of these states can never run again: `executed` is done,
# `superseded` was deliberately replaced by a newer plan, `reference` is
# deliberately outside the window system. Matching a held update against one is
# WORSE than finding nothing — it RESOLVES the update against a dead file, so
# the live plan is never seen and the "needs a plan" question stops being asked.
# Measured 2026-09-22 (F-9ec14462): held PR #212 (aqua:siderolabs/talos
# 1.13.10 -> 1.14.1) matched BOTH talos plans on the name key `talos`, and load
# order handed it talos-1.14.0 (superseded, target v1.14.0) over the live
# talos-1.14.1 (draft, the actual 1.14.1 plan). The bump was then filed STALE
# against a plan that will never run, and reported AMBIGUOUS every sweep, while
# the plan that will actually execute went unmentioned.
TERMINAL_PLAN_STATUSES = ("executed", "superseded", "reference")

# auto-update.py's G5 cooldown gate (`classify` -> gate "age"). A hold at this
# gate has already PASSED the type and policy gates: it is safe-lane work whose
# only impediment is a timer, and the maintenance-window agent merges it at
# Step 0 once the cooldown elapses. It needs no upgrade plan and no planner
# agent (F-50f5de70) — the gates are evaluated in order, so `age` is reached
# only by an update the policy has already cleared.
AGE_COOLDOWN_GATE = "age"

_FETCH_DECISIONS = object()   # "caller supplied nothing" — reconcile fetches


def reconcile(cfg, today, decisions=_FETCH_DECISIONS):
    held, held_error = get_held()
    plans = load_plans(cfg)
    validation_errors = validate_plans(cfg, plans)
    liveness = window_liveness_report(cfg, today)
    parity_errors, parity_verified = cron_parity(cfg)
    autonomy = load_autonomy_policy()
    exec_classes = []
    for p in plans:
        if p.get("status") in TERMINAL_PLAN_STATUSES:
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
    # The candidate set EXCLUDES terminal plans (see TERMINAL_PLAN_STATUSES):
    # a dead file must not absorb a live held update. This narrows the MATCH
    # SET only — the files stay on disk, `retired_still_windowed` and the
    # orphan/validation passes below still read them — and a held update whose
    # only plan is terminal now surfaces as NEEDS A PLAN, which is the truth.
    matchable = [p for p in plans if p.get("status") not in TERMINAL_PLAN_STATUSES]
    needs_plan, stale, ambiguous, cooling = [], [], [], []
    for h in held:
        plan, others = match_held_to_plan(h, matchable)
        if others:
            ambiguous.append({"held": held_key(h),
                              "picked": plan.get("_path"),
                              "also_matched": [o.get("_path") for o in others]})
        if not plan:
            row = {"key": held_key(h), "dep": h.get("dep"),
                   "pr": h.get("number"), "cur": h.get("cur"),
                   "new": h.get("new"), "gate": h.get("gate"),
                   "reason": h.get("reason")}
            # An age-cooldown hold is WAITING ON A TIMER, not missing a plan
            # (F-50f5de70). Dispatching a planner for it burns an agent on work
            # the safe lane performs by itself, and files a plan nobody will
            # ever run. It is bucketed rather than dropped: the same gate also
            # holds an update whose age is UNKNOWN on both measures, which
            # clears only when a human looks — invisible is not the fix for
            # mis-labelled.
            if str(h.get("gate") or "").strip().lower() == AGE_COOLDOWN_GATE:
                cooling.append(row)
            else:
                needs_plan.append(row)
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
    # The on-demand slot joins the per-slot checks (OVER-TIME against its
    # ceiling, REBOOT-IN-NONREBOOT, INTERFERENCE, RISK-CLASS STACKING) but NOT
    # the risk-load budget: an on-demand run is operator-chosen, attended and
    # strictly serial, so a capacity_risk it never declared must not invent an
    # OVER-CAPACITY warning. It is NOT added to `occ`/next_windows.
    _od = on_demand_slot(cfg)
    if _od and _od["id"] not in win_by_id:
        win_by_id[_od["id"]] = {**_od, "_on_demand": True}
    # A plan in a TERMINAL state (executed / superseded) is not schedulable
    # work — but it stays in this map if its file still carries a `window:`,
    # and then it inflates that slot's risk-load and time budget and lists as
    # though it were queued. Both live cases did exactly that:
    # superset-pg-decommission (executed 2026-09-05) held sat-attended:2026-09-05
    # and talos-1.13.9 (superseded) held sun-attended:2026-08-30, a slot whose
    # date had long passed. `unrun_plans` already exempts these two statuses
    # from the MISSED warning, but nothing kept them out of OCCUPANCY.
    # Excluding them silently would trade a false capacity signal for an
    # invisible file-hygiene miss, so the exclusion is paired with its own
    # warning below — the detector must not go blind to fix the symptom.
    retired = retired_still_windowed(plans)
    scheduled = {}
    for p in plans:
        slot = p.get("window")
        if slot and p.get("status") not in MISSED_EXEMPT_STATUSES:
            scheduled.setdefault(slot, []).append(p)

    warnings = []
    for p in retired:
        warnings.append(
            f"RETIRED PLAN STILL WINDOWED: {p.get('plan_id')} "
            f"(status {p.get('status')}) still names {p.get('window')} — "
            f"retire the file (plans/README.md: delete once executed)")
    for slot, ps in scheduled.items():
        w = win_by_slot.get(slot) or win_by_id.get(slot.split(":", 1)[0])
        # missed window (date in the past, plan neither ran nor was retired).
        # `superseded` is NOT a miss: the plan was deliberately replaced by a
        # newer one and will never run, so counting it warns forever about
        # work that no longer exists (talos-1.13.9, superseded by
        # talos-1.13.10, warned on sun-attended:2026-08-30 indefinitely).
        # Everything else that is not `executed` — including `blocked` — stays
        # a warning on purpose: those are open items, and narrowing this
        # predicate further would trade a false positive for a false negative.
        try:
            wdate = date.fromisoformat(slot.split(":", 1)[1])
            unrun = unrun_plans(ps)
            if wdate < today and unrun:
                if _od and slot.split(":", 1)[0] == _od["id"]:
                    # stamped for an on-demand run that did not execute them —
                    # the stamp is stale and home-operation tick will expire
                    # the GO; re-stamp or clear the window.
                    warnings.append(f"STALE ON-DEMAND stamp {slot}: {len(unrun)} "
                                    f"plan(s) stamped for a NOW run not executed — "
                                    f"re-run or clear their window")
                else:
                    warnings.append(f"MISSED window {slot}: {len(unrun)} plan(s) "
                                    f"not executed")
        except Exception:
            wdate = None
        if not w:
            continue
        load = sum(RISK_WEIGHT.get(p.get("risk", "medium"), 2) for p in ps)
        if not w.get("_on_demand") and load > w.get("capacity_risk", 4):
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

        # RISK-CLASS STACKING. The check above keys on shared namespaces/infra,
        # which cannot see the most dangerous collision there is: two
        # IRREVERSIBLE plans in one slot. The four database-engine majors in
        # flight on 2026-09-05 (paperclip-postgresql `ai`, superset-pg
        # `databases`, paperless-db `office`, authentik-pg `kube-system`) all
        # sit in DIFFERENT namespaces with empty `shared`, so they intersect on
        # nothing and the interference check stays silent — while stacking any
        # two of them means a window that cannot be rolled back if the second
        # one fails. Two planner agents independently warned about exactly this
        # in prose, and paperless-db-12.3.3.md already documents it, but no
        # check enforced it. Blast radius is set by reversibility, not by
        # namespace.
        irreversible = [p for p in ps
                        if p.get("rollback_class") in IRREVERSIBLE_ROLLBACK]
        if len(irreversible) > 1:
            ids = ", ".join(sorted(str(p.get("plan_id")) for p in irreversible))
            warnings.append(
                f"RISK-CLASS STACKING {slot}: {len(irreversible)} irreversible "
                f"plans in one slot ({ids}) — if the second fails there is no "
                f"rollback path for the window. Serialize across slots.")

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
    #
    # A plan the operator has ALREADY approved is NOT awaiting a go/no-go: it
    # keeps `status: awaiting-go` until the window agent executes it, because
    # the GO is the recorded home-operation decision and NEVER a status value
    # (see the VALID_STATUSES note). Status alone cannot tell the two apart, so
    # every sweep re-asked for a decision already given (F-0c639ada). Do NOT be
    # misled by nextcloud-34.0.4, which is also approved yet correctly absent
    # here: that is an accident of ITS lifecycle status (`vetted`), not evidence
    # that status encodes approval — approval has to be asked for, keyed on
    # plan_id, against the ledger that holds it.
    #
    # `decisions` is injectable so this stays testable without a cluster.
    # None = NOT READABLE, which must never read as "nobody has decided" (see
    # answered_plan_ids). Asked for only when there is something to cross-check:
    # this is a kubectl exec, and with no awaiting-go plan it cannot change any
    # output.
    if decisions is _FETCH_DECISIONS:
        decisions = (fetch_recorded_decisions()
                     if any(p.get("status") == "awaiting-go" for p in plans)
                     else [])
    answered = answered_plan_ids(decisions)
    approved_pending_exec = sorted(
        str(p.get("plan_id")) for p in plans
        if p.get("status") == "awaiting-go" and str(p.get("plan_id")) in answered)
    awaiting_go = [{"plan_id": p.get("plan_id"), "plan": p["_path"],
                    "component": p.get("component"), "target": p.get("target"),
                    "window": p.get("window")}
                   for p in plans if p.get("status") == "awaiting-go"
                   and str(p.get("plan_id")) not in answered]
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
        # held only by the release-age cooldown: no plan, no planner dispatch
        "age_cooldown": cooling,
        "ambiguous_matches": ambiguous,
        "validation_errors": validation_errors,
        "window_liveness": {"missing": liveness["missing"],
                            "stuck": liveness["stuck"],
                            "verified": liveness["verified"]},
        "cron_parity": {"errors": parity_errors, "verified": parity_verified},
        "execution_classes": exec_classes,   # ENFORCED since P2.1b (a39d8766)
        "stale": stale,
        "orphan_plans": orphan,
        "awaiting_go": awaiting_go,
        # awaiting-go plans the operator ALREADY approved (decision recorded,
        # execution pending) — suppressed from awaiting_go, surfaced here so
        # the suppression is legible instead of silent.
        "approved_pending_exec": approved_pending_exec,
        # False => the decision ledger could NOT be read, so awaiting_go is
        # un-cross-checked and may re-ask an answered question.
        "decisions_readable": decisions is not None,
        "open_issue_keys": open_issue_keys,
        "next_windows": occ[:6],
        "scheduled": {k: [p.get("plan_id") for p in v] for k, v in scheduled.items()},
        "retired_windowed": [{"plan_id": p.get("plan_id"), "status": p.get("status"),
                              "window": p.get("window")} for p in retired],
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
    cooling = r.get("age_cooldown") or []
    if r["needs_plan"]:
        L.append(f"\nNEEDS A PLAN ({len(r['needs_plan'])}) — dispatch an upgrade-planner-agent for each:")
        for n in r["needs_plan"]:
            L.append(f"  • {n['dep']} {n['cur']}→{n['new']} (PR #{n['pr']}, held:{n['gate']}) — {n['reason'][:80]}")
    elif cooling:
        L.append("\nevery held update that needs a plan has one ✅")
    else:
        L.append("\nall held updates have a plan ✅")
    if cooling:
        L.append(f"\nCOOLING OFF ({len(cooling)}) — held ONLY by the release-age gate; "
                 f"no plan and no planner needed, the next window merges them once "
                 f"the timer elapses:")
        for c in cooling:
            L.append(f"  • {c['dep']} {c['cur']}→{c['new']} (PR #{c['pr']}) — "
                     f"{(c['reason'] or '')[:80]}")
    ec = r.get("execution_classes") or []
    if ec:
        L.append("\nexecution classes (ENFORCED — window agent executes AUTO-* only, P2.1b):")
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
        stuck = set(wl.get("stuck") or [])
        L.append(f"\n❌ WINDOWS DECLARED BUT NEVER RAN ({len(wl['missing'])}) — the schedule is fictional for these slots:")
        for m in wl["missing"]:
            if m in stuck:
                L.append(f"  ! {m} — opened (running) but never finalized; the run died mid-window")
            else:
                L.append(f"  ! {m} — no window_runs row; check the OpenClaw cron and the window agent")
    if wl.get("verified", True) and wl.get("stuck"):
        L.append(f"\n❌ WINDOW RUNS STUCK OPEN ({len(wl['stuck'])}) — started, never finalized past duration+{WINDOW_STUCK_GRACE_MIN}m grace:")
        for s in wl["stuck"]:
            L.append(f"  ! {s} — window-run-record.py --finalize with the real outcome (aborted if unknown)")
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
        if not r.get("decisions_readable", True):
            L.append("  (decision ledger UNREADABLE — this list is NOT cross-checked "
                     "against recorded approvals; some of these may already be answered)")
    if r.get("approved_pending_exec"):
        L.append(f"\nGO ALREADY GIVEN ({len(r['approved_pending_exec'])}) — approved, "
                 f"waiting for their window; not re-asked: "
                 f"{', '.join(r['approved_pending_exec'])}")
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
# `approved` was removed (P4.0.4): no loader ever read it — a plan could sit
# in `approved` forever, seen by neither the awaiting-go reminder path nor the
# window agent's Step 1 candidate set. The GO state is `awaiting-go` + a
# recorded home-operation decision, never a status value.
VALID_STATUSES = {
    "draft", "vetted", "scheduled", "awaiting-go", "awaiting-soak",
    "blocked", "executed", "superseded", "reference",
}


def validate_plans(cfg, plans=None) -> list[str]:
    """Machine-checkable frontmatter invariants. Returns error strings."""
    import datetime as _dt
    plans = plans if plans is not None else load_plans(cfg)
    win = {w["id"]: w for w in cfg.get("windows", [])}
    od = on_demand_slot(cfg)
    ids = {p.get("plan_id") for p in plans}
    # A file the loader could not parse is a validation ERROR, not an absence
    # (F-6a398b8b). It comes first: every other invariant below is about plans
    # that exist, and "all invariants hold" must never be printed over a file
    # nobody could read.
    errs = [f"UNREADABLE plan file — {e}" for e in PLAN_LOAD_ERRORS]
    # The on-demand id sharing a scheduled window's id would make every ref to
    # that id ambiguous (weekday-checked or not? cron-driven or not?).
    if od and od["id"] in win:
        errs.append(f"maintenance-windows.yaml: on_demand id {od['id']!r} collides "
                    f"with a scheduled window id — on-demand refs would be ambiguous")
    for pl in plans:
        pid = pl.get("plan_id") or pl.get("_path")
        st = str(pl.get("status") or "").strip()
        w = pl.get("window")
        if st and st not in VALID_STATUSES:
            errs.append(f"{pid}: unknown status {st!r}")
        # a plan that claims a slot must name a real, dated, weekday-consistent one
        if st in ("scheduled", "awaiting-go"):
            if not w:
                errs.append(f"{pid}: status:{st} but window is null — "
                            f"a slotless '{st}' plan silently never runs "
                            f"(use status: reference if it is deliberately unwindowed)")
            else:
                m = _WINDOW_REF.match(str(w))
                if not m:
                    errs.append(f"{pid}: window {w!r} is not <window-id>:<YYYY-MM-DD>")
                elif od and m.group(1) == od["id"] and m.group(1) not in win:
                    # ON-DEMAND ref (`now:<date>`): no weekday — the slot has no
                    # schedule — but the plan must still fit the on-demand
                    # ceiling, and a reboot-bearing plan may not be stamped for
                    # it (node rolls keep the reboot-capable Sunday window and
                    # its sized rollback budget).
                    try:
                        _dt.date.fromisoformat(m.group(2))
                    except ValueError:
                        errs.append(f"{pid}: window {w} carries an invalid date")
                    dur = pl.get("est_duration_min")
                    ceiling = int(od.get("duration_min") or 0)
                    if isinstance(dur, (int, float)) and ceiling and dur > ceiling:
                        errs.append(f"{pid}: est_duration_min {dur} can never fit "
                                    f"the on-demand {od['id']} ceiling ({ceiling}m)")
                    if pl.get("needs_reboot") and not od.get("allow_reboot"):
                        errs.append(f"{pid}: needs_reboot plan may not carry an "
                                    f"on-demand window ({w}) — on_demand.allow_reboot "
                                    f"is false; reboot plans run in a reboot-capable "
                                    f"scheduled window")
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
        if "auto_execute" in pl:
            errs.append(f"{pid}: auto_execute is RETIRED (P2.1b) — declare "
                        f"capability_change/rollback_class and let the policy derive the class")
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
    (today's window may legitimately not have fired yet), since the epoch.

    Reads `windows:` ONLY. The `on_demand:` slot is never expected: it has no
    schedule, so an on-demand run can be used or not, never "missed" — a `now`
    window_runs row is simply an extra completed row nothing asserts on."""
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


# Rollback classes with no cheap undo. `git-revert` is reversible by design;
# these are not — once the data directory is migrated or the dump is restored
# over, getting back costs a restore from backup, not a commit.
IRREVERSIBLE_ROLLBACK = ("one-way", "backup-restore")


# A plan in one of these states is NOT a missed occurrence: `executed` ran,
# and `superseded` was deliberately replaced by a newer plan and will never
# run — counting it warns forever about work that no longer exists.
# Everything else (scheduled/draft/awaiting-go/vetted/blocked) IS a real miss.
MISSED_EXEMPT_STATUSES = ("executed", "superseded")


def unrun_plans(plans):
    """Pure logic: the plans at a past slot that genuinely did not run."""
    return [p for p in plans
            if p.get("status") not in MISSED_EXEMPT_STATUSES]


def retired_still_windowed(plans):
    """Pure logic: plans in a terminal state that STILL name a window.

    Their work is done or abandoned, so they must not consume window
    occupancy — but the stale `window:` is itself the finding (the file was
    never retired), so this is reported rather than silently dropped."""
    return [p for p in plans
            if p.get("window") and p.get("status") in MISSED_EXEMPT_STATUSES]


def missing_window_runs(expected, run_rows):
    """Pure logic, DB-free: expected (slot,date) pairs minus recorded ones."""
    have = {(str(s), str(d)) for s, d in run_rows}
    return [f"{s}:{d}" for s, d in expected if (s, d) not in have]


# A window whose row was opened (`--outcome running`, 2026-09-14 two-phase
# recording) but never finalized. The window agent's close-out is the only
# thing that writes finished_at, so a row still open this long after the
# window's own duration means the run died mid-flight — not "still going".
# Grace absorbs a slow close-out (health-gate retries, an operator reading
# the report) without hiding a dead run for a day.
WINDOW_STUCK_GRACE_MIN = 60
_WINDOW_RUNNING = "running"


def _is_open_run(row) -> bool:
    """A window_runs row that has started and not finished.
    row: (slot, run_date, started_at, finished_at, outcome, ...)."""
    return row[4] == _WINDOW_RUNNING and row[3] is None


def completed_run_rows(run_rows):
    """Pure: the (slot, date) pairs that satisfy the liveness assertion.

    An OPEN row is excluded on purpose — "the window started" is not "the
    window ran". Counting it would turn a crash after the open into a
    verified occurrence, the exact blind spot the two-phase recording exists
    to close. Terminal rows count whatever their finished_at (pre-2026-09-14
    rows all have one; a future terminal row without one is still terminal).
    """
    return [(str(r[0]), str(r[1])) for r in run_rows if not _is_open_run(r)]


def _as_utc(ts):
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def stuck_window_runs(windows, run_rows, now, grace_min=WINDOW_STUCK_GRACE_MIN,
                      on_demand=None):
    """Pure, DB-free: 'slot:date' for every OPEN row older than its window's
    duration_min + grace. A window id the YAML no longer declares gets no
    duration (grace only) — a stale open row for a retired slot is still a
    row nobody will ever close.

    windows:   the `windows:` list from maintenance-windows.yaml (id, duration_min)
    run_rows:  (slot, run_date, started_at, finished_at, outcome, ...)
    now:       tz-aware datetime; naive timestamps are read as UTC
    on_demand: the top-level `on_demand:` block (optional). An open row for
               its slot (`now`) uses ITS duration_min ceiling — without it an
               attended on-demand run would read as stuck after grace alone
               (60 min), which is shorter than most single plans.
    """
    durations = {str(w.get("id")): int(w.get("duration_min") or 0)
                 for w in windows or []}
    if isinstance(on_demand, dict) and on_demand.get("id") \
            and str(on_demand["id"]) not in durations:
        durations[str(on_demand["id"])] = int(on_demand.get("duration_min") or 0)
    now = _as_utc(now)
    out = []
    for r in run_rows:
        if not _is_open_run(r):
            continue
        slot, run_date, started_at = str(r[0]), str(r[1]), r[2]
        if started_at is None:
            continue
        deadline = _as_utc(started_at) + timedelta(
            minutes=durations.get(slot, 0) + grace_min)
        if now > deadline:
            out.append(f"{slot}:{run_date}")
    return sorted(out)


def window_liveness_report(cfg, today, now=None):
    """{"missing": [...], "stuck": [...], "verified": bool}.

    verified=False when the DB is unreachable — an unreadable ledger must
    render as NOT CHECKED, never as all-clear. `missing` and `verified` keep
    the shape every consumer has read since P1.3; `stuck` is additive.
    """
    unverified = {"missing": [], "stuck": [], "verified": False}
    expected = expected_slots(cfg, today)
    dsn = __import__("os").environ.get("SWEEP_PG_DSN")
    if not dsn:
        return unverified
    # Stuck detection must see TODAY's rows too (a nightly opened at 03:30 and
    # dead by 06:00 is today's problem), so the read floor is the earlier of
    # the liveness lookback and the expected-slot floor.
    floor = min([d for _, d in expected]
                + [(today - timedelta(days=7)).isoformat()])
    try:
        import psycopg
        with psycopg.connect(dsn, connect_timeout=10) as c, c.cursor() as cur:
            cur.execute("SELECT slot, run_date::text, started_at, finished_at,"
                        " outcome FROM window_runs WHERE run_date >= %s",
                        (floor,))
            rows = cur.fetchall()
    except Exception:
        return unverified
    now = now or datetime.now(timezone.utc)
    return {"missing": missing_window_runs(expected, completed_run_rows(rows)),
            "stuck": stuck_window_runs(cfg.get("windows", []), rows, now,
                                       on_demand=on_demand_slot(cfg)),
            "verified": True}


def window_liveness(cfg, today):
    """(missing, verified) — the original two-value contract, kept for the
    callers and tests that unpack it; `window_liveness_report` adds `stuck`."""
    r = window_liveness_report(cfg, today)
    return r["missing"], r["verified"]


# ---------------------------------------------------------------------------
# Execution classes (P2.1a derivation; ENFORCED since P2.1b, a39d8766).
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


# The shared-infrastructure FLOOR: keys that are never unattended, whatever the
# policy file happens to list. A policy class may WIDEN this (its own
# forbid_shared is unioned in); it may not narrow it. It lives here rather than
# only in the YAML because a guard is only as good as its vocabulary, and
# [storage, longhorn] missed the substrates the plans in this repo actually
# name: cni/cilium, gateway/envoy, etcd, dns. (The YAML stays the place to add
# more, and emptying `classes:` is still the kill switch — a plan that matches
# no class never reaches this check.)
SHARED_INFRA_FLOOR = ("storage", "longhorn", "cni", "gateway", "etcd", "dns")

_SHARED_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def shared_tokens(values) -> set[str]:
    """Every matchable token in a plan's `touches.shared` list.

    `touches.shared` is an INTERSECTION KEY, and the house spells it COMPOUND:
    `storage/longhorn`, `gateway/envoy`, `cni/cilium`, `dns-internal`,
    `k8s-gateway DNS`. A bare set intersection against ["storage", "longhorn"]
    therefore matched exactly ONE of the 19 distinct values in the plan corpus
    (measured 2026-09-22, F-724dc4df): the guard meant to keep shared
    infrastructure out of unattended windows was inert for every key that
    qualified itself. wazuh-2xx-edge-coverage (shared: [gateway/envoy]) derived
    AUTO-NIGHT on mechanics, held back only by a hand-written
    autonomy_override — i.e. by an author remembering, which is what a guard is
    for.

    Returns the whole value AND its alphanumeric tokens, so a literal policy
    entry (`storage`, or even `storage/longhorn`) still matches while
    `gateway/envoy` now also matches `gateway`. Over-matching is the SAFE
    direction: a hit means HUMAN-GATED, the default this module fails toward.
    """
    out: set[str] = set()
    for v in values or []:
        if v is None:                 # else str(None) -> the token "none"
            continue
        s = str(v).strip().lower()
        if not s:
            continue
        out.add(s)
        out.update(t for t in _SHARED_TOKEN_SPLIT.split(s) if t)
    return out


def forbidden_shared(spec) -> set[str]:
    """A class's forbid_shared, widened by the floor it may not narrow."""
    return ({str(x).strip().lower() for x in (spec.get("forbid_shared") or [])}
            | set(SHARED_INFRA_FLOOR))


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
    shared = shared_tokens((plan.get("touches") or {}).get("shared"))
    # `risk:` frequently carries a trailing comment in these files, so take the
    # first token. `.split()` on an empty/absent value yields [], NOT [""] --
    # indexing it raised IndexError for every plan without a risk (caught by
    # test-autonomy-class.py on the first run of this code).
    _risk_tokens = str(plan.get("risk") or "").split()
    risk = _risk_tokens[0].strip().lower() if _risk_tokens else None
    for cname, spec in policy.get("classes", {}).items():
        req = spec.get("require", {})
        if any(facts.get(k) != v for k, v in req.items()):
            continue
        if shared & forbidden_shared(spec):
            continue
        # A declared risk level can VETO an otherwise-matching class, but never
        # grant one. See the `risk: high` note in autonomy-policy.yaml: the
        # mechanical fact set cannot express "moves live data between two
        # systems", and `risk: high` is where the operator says so.
        forbidden = {str(x).lower() for x in spec.get("forbid_risk", [])}
        if risk is not None and risk in forbidden:
            return "HUMAN-GATED", (f"matches {cname} on mechanics but is "
                                   f"risk: {risk}, which that class forbids")
        if spec.get("require_backup_gate") and not plan.get("backup_gate"):
            return "HUMAN-GATED", (f"matches {cname} but names no backup_gate — "
                                   f"an ungated backup-restore plan is not pre-approved")
        return cname.upper(), f"policy class {cname}"
    return "HUMAN-GATED", "matches no pre-approved class (default)"


# ---------------------------------------------------------------------------
# Recorded operator decisions (F-0c639ada).
#
# The GO state is `status: awaiting-go` PLUS a recorded home-operation
# decision — never a status value (see the VALID_STATUSES note). The two are
# ORTHOGONAL: nextcloud-34.0.4 carries a recorded operator GO while sitting at
# `status: vetted`, and an approved plan keeps `awaiting-go` until the window
# agent executes it. So the reminder list cannot be derived from the plan files
# alone, and "approval" cannot be read off a status — it has to be asked for.
# Same command run-now.py uses, so "approved" means ONE thing in this repo.
# ---------------------------------------------------------------------------

HOME_OP_DECISIONS_CMD = [
    "kubectl", "-n", "ai", "exec", "deploy/openclaw", "-c", "app", "--",
    "/home/node/.openclaw/bin/home-operation", "--json",
    "decisions", "--pending-exec",
]


def parse_decisions(returncode, stdout) -> list | None:
    """The decision rows, or None when they could NOT be read.

    None is "unknown", never "none recorded": an exec that failed (pod
    mid-roll, no kubeconfig, running off-cluster) must not read as "nobody has
    decided", or the go/no-go reminder would vanish exactly when the ledger is
    unreadable — the unreadable-ledger-is-not-all-clear rule this module
    already applies to window liveness and cron parity.
    """
    if returncode != 0:
        return None
    try:
        doc = json.loads(stdout or "")
    except ValueError:
        return None
    rows = doc.get("decisions") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        return None
    return [r for r in rows if isinstance(r, dict)]


def fetch_recorded_decisions(runner=subprocess.run, timeout=60) -> list | None:
    """Pending-exec decisions from OpenClaw's home-operation store, or None."""
    try:
        p = runner(HOME_OP_DECISIONS_CMD, capture_output=True, text=True,
                   timeout=timeout)
    except Exception:
        return None
    return parse_decisions(p.returncode, p.stdout)


def answered_plan_ids(decisions) -> set[str]:
    """plan_ids whose go/no-go the operator has ALREADY answered with a GO.

    `approve` + `exec_state: pending` only — run-now.py's own predicate. NOT
    `deny`: a denied plan still needs its file moved to blocked/superseded, and
    the reminder is the only thing carrying that; suppressing it would retire
    the nag and leave the plan sitting at `awaiting-go` forever.

    Unreadable decisions (None) yield an EMPTY set, so every reminder keeps
    firing — fail toward asking twice, never toward a go/no-go that silently
    stops being asked.
    """
    return {str(d.get("key")) for d in (decisions or [])
            if d.get("key") and d.get("decision") == "approve"
            and d.get("exec_state") == "pending"}


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
    out.append(f"EXECUTABLE ({len(ex)}) — scheduled into a window "
               f"(or stamped now:<date> for an on-demand NOW run)")
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
