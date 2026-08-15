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


def get_held():
    """Held (non-safe) updates from the auto-updater, decoupled via subprocess."""
    try:
        p = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "auto-update.py"), "--json"],
            capture_output=True, text=True, timeout=120,
        )
        data = json.loads(p.stdout or "{}")
        return data.get("held", [])
    except Exception as e:
        print(f"!! could not read held updates: {e}", file=sys.stderr)
        return []


def next_occurrence(day_name, start_hhmm, today):
    wd = _WD[day_name.lower()]
    delta = (wd - today.weekday()) % 7
    # if it's the same weekday, still schedule the upcoming one (today counts as 0)
    d = today + timedelta(days=delta)
    return d


def upcoming_windows(cfg, today, horizon_days=14):
    """List concrete window occurrences within the horizon, soonest first."""
    occ = []
    for w in cfg["windows"]:
        d = next_occurrence(w["day"], w["start"], today)
        for bump in (0, 7):  # this week + next, to fill the horizon
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
    held = get_held()
    plans = load_plans(cfg)
    plans_by_pr = {str(p.get("pr")): p for p in plans if p.get("pr")}
    plans_by_comp = {}
    for p in plans:
        plans_by_comp.setdefault(str(p.get("component", "")).lower(), []).append(p)

    # 1) held updates lacking a fresh plan
    needs_plan, stale = [], []
    for h in held:
        pr = str(h.get("number", ""))
        comp = (h.get("dep", "").split("/")[-1] or "").lower()
        plan = plans_by_pr.get(pr) or (plans_by_comp.get(comp, [None])[0])
        if not plan:
            needs_plan.append({"key": held_key(h), "dep": h.get("dep"),
                               "pr": h.get("number"), "cur": h.get("cur"),
                               "new": h.get("new"), "gate": h.get("gate"),
                               "reason": h.get("reason")})
            continue
        # stale if the plan's target no longer matches the held PR's target
        if plan.get("target") and h.get("new") and str(plan["target"]) != str(h["new"]):
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
    scheduled = {}
    for p in plans:
        slot = p.get("window")
        if slot:
            scheduled.setdefault(slot, []).append(p)

    warnings = []
    for slot, ps in scheduled.items():
        w = win_by_slot.get(slot)
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
        "needs_plan": needs_plan,
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
    L = [f"== maintenance schedule · {r['today']} · {r['held_count']} held update(s) =="]
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
