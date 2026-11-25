#!/usr/bin/env python3
"""plan-refine — keep open maintenance plans FRESH, automatically.

WHY THIS EXISTS (operator, 2026-11-25)
"Stale plans must be refined automatically — start every maintenance window by
looking at open plans, refining them, then starting the maintenance."
Measured the same day: the executor was never the bottleneck, plan FRESHNESS
was. Plans rot three ways, all mechanical to detect:

  * TARGET DRIFT   a patch landed upstream after the plan was written (plan
                   targets 3.5.0, 3.5.1 is out), so the plan's commands and
                   premises name a tag nobody wants any more;
  * DEAD REFS      `conflicts_with` names a plan that was retired, so the
                   guard enforces nothing (maintenance-plan.py: "NOT enforced");
  * STALE REVIEW   a `ready-for-go` review ages past 30 days and the plan
                   silently stops being pre-approved although nothing changed;
  * FAILED PREMISE the world moved (a PR head, a chart version) and the plan
                   is un-runnable, which nothing surfaced until the window.

WHAT IT DOES (report mode is the default and is READ-ONLY)
For every OPEN plan (draft|vetted|scheduled|awaiting-go):

  MECHANICAL repairs (applied only with --apply; each is in MECHANICAL below):
    retarget-patch      plan target T -> N when N is a PATCH on the same
                        major.minor line, N is confirmed on the stable channel,
                        the release notes + structural diff T..N carry no
                        breaking signal, the plan pins no digest for T, and the
                        plan's premises PASS against the retargeted text.
                        Rewrites `target:`, premise `run:`/`expect_*` and
                        FENCED COMMAND BLOCKS only; prose keeps naming T and a
                        "Refinement log" section says so. Execution steps are
                        never re-written beyond that literal token swap.
    prune-conflict      a dead `conflicts_with` ref is re-pointed at the live
                        successor plan(s) of the same component stem, else
                        dropped (it enforced nothing anyway).
    extend-review       a ready-for-go review that is about to lapse is
                        extended (`review_refined`) when EVERY change this run
                        was mechanical and premises PASS. Capped by
                        autonomy-policy `refine.review_hard_cap_days` after the
                        last full review. The refiner NEVER writes `review:` —
                        only a reviewer's verdict first marks a plan
                        ready-for-go.

  NON-MECHANICAL => `needs_replan: "<code>: <detail>"` + a `planner_queue`
  entry; the plan is NOT edited otherwise and loses pre-approval at once
  (maintenance-plan.py refuses `needs_replan` for SD-10/SD-11). Codes:
    minor-or-major-drift, channel-unresolved, notes-unverified,
    digest-pinned-target, premise-fail, no-premises, dead-depends-on,
    unreadable-target.

FAIL CLOSED
  * unreadable plan file / unreadable plans dir        -> exit 2
  * cluster canary fails                               -> no premise-dependent
    action at all (no retarget, no extension, no flag), exit 3 (degraded)
  * coverage drift data unavailable                    -> no retarget, no
    extension, exit 3
  * premises not run inside the time budget            -> that plan is
    `unchecked`: never extended, never retargeted
  * a premise whose failure is an INFRA error (timeout/connection) is
    `unchecked`, never `premise-fail` (no mass-flagging on a flaky API)
  * apply mode skips any plan file with uncommitted changes or untracked
    (the shared worktree: another session may be mid-edit)
  * every write is re-parsed (YAML) and verified before it lands; a repair
    that does not round-trip is abandoned.

    plan-refine.py                         # report, JSON to stdout with --json
    plan-refine.py --apply --json          # repair + flag; prints changed_paths
    plan-refine.py --coverage-json F --budget-sec 240 --apply

Exit: 0 ok | 2 bad input / unreadable plan | 3 degraded (see report.degraded).
The window agent commits `changed_paths` itself (git commit --only).
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import copy
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

OPEN_STATUSES = ("draft", "vetted", "scheduled", "awaiting-go")
# Actions that count as MECHANICAL for the review-extension rule. Anything
# else recorded in a plan's action list disqualifies the extension.
MECHANICAL = frozenset({"retarget-patch", "prune-conflict", "repoint-conflict",
                        "premises-rerun", "extend-review"})
INFRA_RE = re.compile(r"timed out|timeout|unable to connect|connection refused|"
                      r"no route to host|i/o timeout|tls handshake|context deadline|"
                      r"temporary failure|could not resolve|server is currently unable",
                      re.I)
VERSION_RE = re.compile(r"^v?\d+(?:\.\d+){1,3}(?:-[A-Za-z][A-Za-z0-9]*)?$")
DEFAULTS = {"review_extension_days": 30, "review_hard_cap_days": 60,
            "extend_lead_days": 7, "retarget": "patch-only"}


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ───────────────────────── version helpers ─────────────────────────

def vparts(v):
    """((ints...), suffix) or None. 'v1.2.3-alpine' -> ((1,2,3), '-alpine')."""
    s = str(v or "").strip().strip("\"'")
    if not VERSION_RE.match(s):
        return None
    s = s.lstrip("v")
    m = re.match(r"^(\d+(?:\.\d+)*)(-.*)?$", s)
    return tuple(int(x) for x in m.group(1).split(".")), (m.group(2) or "")


def delta_class(old, new):
    """'patch' | 'minor' | 'major' | 'same' | 'downgrade' | 'incomparable'."""
    a, b = vparts(old), vparts(new)
    if not a or not b or a[1] != b[1]:
        return "incomparable"
    x, y = a[0], b[0]
    n = max(len(x), len(y))
    x, y = x + (0,) * (n - len(x)), y + (0,) * (n - len(y))
    if x == y:
        return "same"
    if y < x:
        return "downgrade"
    if x[0] != y[0]:
        return "major"
    if x[1] != y[1]:
        return "minor"
    return "patch"


# ───────────────────────── frontmatter text surgery ─────────────────────────

_FM_RE = re.compile(r"\A---\n(.*?\n)---[ \t]*(?:\n|\Z)", re.S)


def split_plan(text):
    """(fm_text, body_text) with exact bytes preserved, or None."""
    m = _FM_RE.match(text)
    if not m:
        return None
    return m.group(1), text[m.end():]


def join_plan(fm, body):
    return "---\n" + fm + "---\n" + body


def fm_parse(fm):
    d = yaml.safe_load(fm)
    if not isinstance(d, dict):
        raise ValueError("frontmatter is not a mapping")
    return d


def _key_re(key):
    return re.compile(r"^" + re.escape(key) + r":[ \t]*.*$", re.M)


def fm_set(fm, key, value_yaml, comment=None):
    """Replace (or append) a single-line top-level key. Following comment-only
    continuation lines of the OLD value are dropped (they describe it)."""
    line = f"{key}: {value_yaml}" + (f"   # {comment}" if comment else "")
    m = _key_re(key).search(fm)
    if not m:
        return fm.rstrip("\n") + "\n" + line + "\n"
    end = m.end()
    rest = fm[end:]
    drop = re.match(r"(?:\n[ \t]+#[^\n]*)*", rest)
    end += drop.end() if drop else 0
    return fm[:m.start()] + line + fm[end:]


def fm_drop(fm, key):
    m = _key_re(key).search(fm)
    if not m:
        return fm
    end = m.end()
    drop = re.match(r"(?:\n[ \t]+#[^\n]*)*\n?", fm[end:])
    end += drop.end() if drop else 0
    return fm[:m.start()] + fm[end:]


def yq(s):
    return json.dumps(str(s))


def _block_span(fm, key):
    """(start, end) char span of a top-level block key, or None."""
    m = _key_re(key).search(fm)
    if not m:
        return None
    nxt = re.compile(r"^[A-Za-z_][\w-]*:", re.M).search(fm, m.end())
    return m.start(), (nxt.start() if nxt else len(fm))


def sub_token(text, old, new):
    """Replace the version token `old` (not part of a longer dotted/number run)."""
    pat = re.compile(r"(?<![0-9.])" + re.escape(old) + r"(?![0-9]|\.[0-9])")
    return pat.subn(new, text)


FENCE_RE = re.compile(r"^(```|~~~)")


def sub_in_fences(body, old, new):
    out, n, infence = [], 0, False
    for line in body.split("\n"):
        if FENCE_RE.match(line.strip()):
            infence = not infence
            out.append(line)
            continue
        if infence:
            line, k = sub_token(line, old, new)
            n += k
        out.append(line)
    return "\n".join(out), n


def digest_pinned(fm, body, token):
    """True when a command/premise line naming `token` also pins a sha256."""
    lines = [l for l in fm.split("\n") if not l.lstrip().startswith("#")]
    infence = False
    for l in body.split("\n"):
        if FENCE_RE.match(l.strip()):
            infence = not infence
            continue
        if infence:
            lines.append(l)
    pat = re.compile(r"(?<![0-9.])" + re.escape(token) + r"(?![0-9]|\.[0-9])")
    return any(pat.search(l) and "sha256:" in l for l in lines)


# ───────────────────────── policy ─────────────────────────

def load_refine_policy(mp):
    pol = mp.load_autonomy_policy() or {}
    r = dict(DEFAULTS)
    r.update((pol.get("refine") or {}))
    return r


# ───────────────────────── evidence (injectable) ─────────────────────────

def default_evidence(plan, drift_row, old, new):
    """{'channel_ok','notes_ok','note'} for a patch retarget old->new.

    Channel: coverage already resolved the stable-channel head and it equals
    `new`. Notes: coverage.py's G3 engines (release notes + structural diff),
    images only. Anything unreadable is NOT ok — the caller fails closed.
    """
    ev = {"channel_ok": False, "notes_ok": False, "note": ""}
    head = (drift_row or {}).get("channel_head")
    ev["channel_ok"] = bool(head) and head == new
    if not ev["channel_ok"]:
        ev["note"] = ("channel-unresolved: coverage could not confirm "
                      f"{new} is the stable-channel head")
        return ev
    try:
        cov = _load("cov_for_refine", "coverage.py")
        repos = (drift_row or {}).get("image_repos") or []
        if str(plan.get("kind")) != "image" or not repos:
            ev["note"] = "notes-unverified: no image repo for a release-notes read"
            return ev
        repo = [r for r in repos if r not in ("busybox",)] or repos
        brk, note = cov.breaking_change_signal(repo[0], new, old)
        if brk or not str(note).startswith("clean"):
            ev["note"] = f"notes-unverified: {note}"
            return ev
        st, snote = cov.structural_change_signal(repo[0], old, new)
        if st or str(snote).startswith("unverified"):
            ev["note"] = f"notes-unverified: structural {snote}"
            return ev
        ev["notes_ok"] = True
        ev["note"] = "release notes + structural diff clean"
    except Exception as e:  # noqa: BLE001 — fail closed
        ev["note"] = f"notes-unverified: evidence read failed ({type(e).__name__})"
    return ev


# ───────────────────────── premises (injectable) ─────────────────────────

def default_canary():
    try:
        p = subprocess.run(["kubectl", "get", "ns", "kube-system", "-o", "name",
                            "--request-timeout=15s"], capture_output=True,
                           text=True, timeout=30)
        return p.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def default_premise_runner(plan, timeout=45):
    pp = _load("pp_for_refine", "plan-premises.py")
    return pp.check_plan(plan, timeout)


def premise_verdict(report):
    """('pass'|'fail'|'none'|'unchecked', [failing ids], detail)."""
    if not report or not report.get("declared"):
        return "none", [], "declares no premises"
    bad = [r for r in report.get("results", []) if not r.get("passed")]
    if not bad:
        return "pass", [], ""
    infra = [r for r in bad if INFRA_RE.search(str(r.get("detail") or ""))]
    if len(infra) == len(bad):
        return "unchecked", [r.get("id") for r in bad], "infra error: " + str(bad[0].get("detail"))[:100]
    real = [r for r in bad if r not in infra]
    return "fail", [r.get("id") for r in real], "; ".join(
        f"{r.get('id')}: {str(r.get('detail'))[:90]}" for r in real[:3])


# ───────────────────────── core ─────────────────────────

def drift_for_plan(path, drift_rows):
    base = Path(path).name
    for row in drift_rows or []:
        if str(row.get("drift") or "").startswith(base + ":"):
            return row
    return None


def newest_target(row):
    """The version a plan should aim at: stable-channel head if coverage
    resolved one, else the newest published version named in the drift text."""
    if row.get("channel_head"):
        return str(row["channel_head"])
    m = re.search(r"but (\S+) is now published", str(row.get("drift") or ""))
    return m.group(1) if m else None


def stem(plan_id):
    return re.sub(r"[-_]v?\d[\w.\-]*$", "", str(plan_id))


def live_successors(dead_id, plans, self_id):
    s = stem(dead_id)
    out = []
    for p in plans:
        pid = p.get("plan_id")
        if (pid and pid != self_id and pid != dead_id and stem(pid) == s
                and str(p.get("status")) not in ("executed", "superseded", "reference")):
            out.append(pid)
    return sorted(out)


def prune_conflicts(fm, plan, all_plans, ids):
    """(new_fm, actions). Handles block-list and flow-list conflicts_with."""
    actions = []
    refs = list(plan.get("conflicts_with") or [])
    dead = [r for r in refs if r not in ids]
    if not dead:
        return fm, actions
    span = _block_span(fm, "conflicts_with")
    if not span:
        return fm, actions
    block = fm[span[0]:span[1]]
    live = [r for r in refs if r in ids]
    add = []
    for d in dead:
        succ = [s for s in live_successors(d, all_plans, plan.get("plan_id")) if s not in live + add]
        if succ:
            add.extend(succ)
            actions.append({"type": "repoint-conflict", "mechanical": True,
                            "detail": f"{d} -> {', '.join(succ)}"})
        else:
            actions.append({"type": "prune-conflict", "mechanical": True,
                            "detail": f"dropped dead ref {d}"})
    today = date.today().isoformat()
    if re.match(r"^conflicts_with:[ \t]*\[", block):
        newlist = live + add
        nb = "conflicts_with: [" + ", ".join(newlist) + "]   # plan-refine " + today + \
             ": dead ref(s) " + ", ".join(dead) + " pruned\n"
    else:
        keep = []
        _im = re.search(r"^([ \t]*)-[ \t]", block, re.M)
        ind = _im.group(1) if _im else "  "
        for line in block.split("\n"):
            m = re.match(r"^(\s*)-\s*([^\s#]+)", line)
            if m and m.group(2) in dead:
                continue
            keep.append(line)
        nb = "\n".join(keep).rstrip("\n") + "\n"
        for a in add:
            nb += f"{ind}- {a}   # plan-refine {today}: successor of a dead ref\n"
        nb += f"{ind}# plan-refine {today}: dead ref(s) {', '.join(dead)} pruned\n"
    return fm[:span[0]] + nb + fm[span[1]:], actions


def try_retarget(fm, body, plan, row, old, new, evidence, today_s):
    """(fm, body, action|None, replan_code|None, detail)."""
    dc = delta_class(old, new)
    if dc in ("same",):
        return fm, body, None, None, ""
    if dc != "patch":
        return fm, body, None, "minor-or-major-drift", \
            f"upstream moved {old} -> {new} ({dc}); a re-assessment is needed"
    if digest_pinned(fm, body, old):
        return fm, body, None, "digest-pinned-target", \
            f"plan pins a sha256 next to {old}; the digest of {new} cannot be re-derived here"
    ev = evidence(plan, row, old, new)
    if not ev.get("channel_ok"):
        return fm, body, None, "channel-unresolved", ev.get("note") or "channel not confirmed"
    if not ev.get("notes_ok"):
        return fm, body, None, "notes-unverified", ev.get("note") or "release notes not verified"
    nfm = fm_set(fm, "target", yq(new),
                 f"plan-refine {today_s}: retargeted from {old} (patch, same line; {ev.get('note')})")
    span = _block_span(nfm, "premises")
    n_prem = 0
    if span:
        blk, n_prem = sub_token(nfm[span[0]:span[1]], old, new)
        nfm = nfm[:span[0]] + blk + nfm[span[1]:]
    nbody, n_body = sub_in_fences(body, old, new)
    nfm = fm_set(nfm, "retargeted_from", yq(old))
    nbody = nbody.rstrip("\n") + (
        f"\n\n## Refinement log (plan-refine, {today_s})\n"
        f"- target `{old}` -> `{new}` (patch on the same line; {ev.get('note')}). "
        f"`target:`, premises ({n_prem} token swap(s)) and fenced command blocks "
        f"({n_body}) now name `{new}`; prose above still describes the originally "
        f"reviewed `{old}`.\n")
    return nfm, nbody, {"type": "retarget-patch", "mechanical": True,
                        "detail": f"{old} -> {new}; premises/commands swapped "
                                  f"({n_prem}/{n_body})"}, None, ""


def git_dirty(path):
    """True when the plan file has uncommitted/untracked state (or git fails)."""
    try:
        p = subprocess.run(["git", "status", "--porcelain", "--", str(path)],
                           capture_output=True, text=True, cwd=REPO_ROOT, timeout=30)
        return p.returncode != 0 or bool(p.stdout.strip())
    except Exception:  # noqa: BLE001
        return True


def refine(plans_meta, texts, *, today, mp, cfg, policy_refine, drift_rows,
           drift_checked, evidence, premise_runner, canary, budget_sec=240,
           workers=6, per_plan_timeout=45, dirty=lambda p: False, apply=False):
    """Pure-ish engine. plans_meta: list of frontmatter dicts (with _path);
    texts: {_path: text}. Returns (report, new_texts {path: text})."""
    t0 = time.monotonic()
    today_s = today.isoformat()
    ids = {p.get("plan_id") for p in plans_meta}
    open_plans = [p for p in plans_meta if str(p.get("status")) in OPEN_STATUSES]
    # runnable statuses first: they are the ones that can lose pre-approval
    order = {"scheduled": 0, "awaiting-go": 1, "vetted": 2, "draft": 3}
    open_plans.sort(key=lambda p: (order.get(str(p.get("status")), 9), str(p.get("plan_id"))))

    cluster_ok = bool(canary())
    degraded = []
    if not cluster_ok:
        degraded.append("cluster-unreachable: premises not run; no retarget/extension/flag")
    if not drift_checked:
        degraded.append("drift-unavailable: coverage plan_drift not read; no retarget/extension")

    reports, new_texts = [], {}
    policy = mp.load_autonomy_policy()
    max_age = int(((policy or {}).get("interruption_tolerant") or {}).get("max_review_age_days") or 30)

    # --- phase 1: static analysis + candidate text -------------------------
    work = []
    for p in open_plans:
        path = p["_path"]
        pid = p.get("plan_id")
        rep = {"plan_id": pid, "path": path, "status": p.get("status"),
               "component": p.get("component"), "findings": [], "actions": [],
               "outcome": "clean", "review_extended": False}
        reports.append(rep)
        text = texts.get(path)
        sp = split_plan(text) if text else None
        if not sp:
            rep["outcome"] = "unreadable"
            rep["findings"].append("unreadable-plan")
            continue
        fm, body = sp
        meta = dict(p)
        # dead refs
        for r in (p.get("depends_on") or []):
            if r not in ids:
                rep["findings"].append(f"dead-depends-on:{r}")
        nfm = fm
        nfm, acts = prune_conflicts(nfm, p, plans_meta, ids)
        rep["actions"].extend(acts)
        replan = None
        for r in (p.get("depends_on") or []):
            if r not in ids:
                replan = replan or ("dead-depends-on", f"depends_on -> {r} names no existing plan")
        # target drift
        row = drift_for_plan(path, drift_rows)
        nbody = body
        retargeted = False
        if row and drift_checked:
            old = str(p.get("target") or "").strip()
            new = newest_target(row)
            rep["findings"].append(f"target-drift:{old}->{new}")
            if not vparts(old) or not new:
                replan = replan or ("unreadable-target",
                                    f"target {old!r} is not a single version token")
            elif cluster_ok:
                nfm2, nbody2, act, code, detail = try_retarget(
                    nfm, nbody, p, row, old, new, evidence, today_s)
                if code:
                    replan = replan or (code, detail)
                elif act:
                    nfm, nbody, retargeted = nfm2, nbody2, True
                    rep["actions"].append(act)
        if rep["actions"] and not retargeted and not replan:
            pass
        rep["_replan"] = replan
        rep["_nfm"], rep["_nbody"] = nfm, nbody
        rep["_meta"] = meta
        work.append(rep)

    # --- phase 2: premises on the candidate text (parallel, budgeted) -------
    def run_one(rep):
        if time.monotonic() - t0 > budget_sec:
            return rep, None
        try:
            cand = fm_parse(rep["_nfm"])
            cand["_path"] = rep["path"]
        except Exception as e:  # noqa: BLE001
            return rep, {"_error": f"candidate frontmatter unparseable: {e}"}
        try:
            return rep, premise_runner(cand)
        except Exception as e:  # noqa: BLE001
            return rep, {"_error": f"premise runner raised {type(e).__name__}: {e}"}

    results = {}
    if cluster_ok:
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for rep, res in ex.map(run_one, work):
                results[rep["plan_id"]] = res
        # one retry of real failures (transient cluster flaps must not flag)
        for rep in work:
            res = results.get(rep["plan_id"])
            v = premise_verdict(res)[0] if res and "_error" not in res else None
            if v == "fail" and time.monotonic() - t0 <= budget_sec:
                _, res2 = run_one(rep)
                results[rep["plan_id"]] = res2

    # --- phase 3: decide ----------------------------------------------------
    for rep in work:
        p, meta = rep.pop("_meta"), None
        meta = p
        nfm, nbody, replan = rep.pop("_nfm"), rep.pop("_nbody"), rep.pop("_replan")
        res = results.get(rep["plan_id"])
        retargeted = any(a["type"] == "retarget-patch" for a in rep["actions"])
        status = str(meta.get("status"))
        if not cluster_ok:
            verdict, bad, pdetail = "unchecked", [], "cluster unreachable"
        elif res is None:
            verdict, bad, pdetail = "unchecked", [], "premises not run inside the time budget"
        elif "_error" in res:
            verdict, bad, pdetail = "unchecked", [], res["_error"]
        else:
            verdict, bad, pdetail = premise_verdict(res)
        rep["premises"] = {"verdict": verdict, "failing": bad, "detail": pdetail}
        if cluster_ok and verdict != "unchecked":
            rep["actions"].append({"type": "premises-rerun", "mechanical": True,
                                   "detail": verdict})
        if verdict == "fail":
            rep["findings"].append("premise-fail:" + ",".join(str(b) for b in bad))
            if retargeted:
                # the retarget did not make the plan runnable: revert to the
                # original text and flag — never leave a half-fixed plan.
                rep["actions"] = [a for a in rep["actions"] if a["type"] != "retarget-patch"]
                nfm, nbody = split_plan(texts[rep["path"]])
                nfm, _ = prune_conflicts(nfm, meta, plans_meta, ids)
                retargeted = False
            replan = replan or ("premise-fail", pdetail)
        elif verdict == "none" and status in ("vetted", "scheduled", "awaiting-go"):
            rep["findings"].append("no-premises")
            replan = replan or ("no-premises", "runnable plan declares no premises")
        had_flag = bool(meta.get("needs_replan"))

        rep["since"] = str(meta.get("needs_replan_since") or today_s)
        if replan:
            code, detail = replan
            rep["outcome"] = "needs-replan"
            rep["replan"] = {"code": code, "detail": detail}
        else:
            rep["outcome"] = "repaired" if any(
                a["type"] in ("retarget-patch", "prune-conflict", "repoint-conflict")
                for a in rep["actions"]) else "clean"
        if verdict == "unchecked":
            rep["outcome"] = "unchecked" if not replan else rep["outcome"]

        # flag management (premise-only flags clear themselves when the
        # premises pass again; every other code needs a planner)
        if replan and not had_flag:
            nfm = fm_set(nfm, "needs_replan", yq(f"{replan[0]}: {replan[1]}"[:300]))
            nfm = fm_set(nfm, "needs_replan_since", yq(today_s))
        elif (not replan and had_flag and verdict == "pass"
              and str(meta.get("needs_replan")).startswith("premise-fail")):
            nfm = fm_drop(fm_drop(nfm, "needs_replan"), "needs_replan_since")
            rep["actions"].append({"type": "clear-premise-flag", "mechanical": False,
                                   "detail": "premises pass again"})

        # review extension
        rv = mp.parse_review(meta.get("review"))
        if rv and rv[0] == "ready-for-go" and status in ("vetted", "scheduled", "awaiting-go"):
            eff = mp.effective_review(meta, policy, today)
            age = (today - eff[1]).days if eff else None
            lead = int(policy_refine["extend_lead_days"])
            if age is not None and age > max_age - lead:
                base_age = (today - rv[1]).days
                ok = (not replan and verdict == "pass" and drift_checked and cluster_ok
                      and all(a["mechanical"] for a in rep["actions"])
                      and base_age <= int(policy_refine["review_hard_cap_days"]))
                if ok:
                    nfm = fm_set(nfm, "review_refined", yq(today_s),
                                 "plan-refine: mechanical-only refresh, premises PASS "
                                 "(full review date unchanged)")
                    nfm = fm_set(nfm, "review_refined_base", yq(rv[1].isoformat()))
                    rep["review_extended"] = True
                    rep["actions"].append({"type": "extend-review", "mechanical": True,
                                           "detail": f"effective review {today_s} (base {rv[1]})"})
                else:
                    why = ("needs-replan" if replan else
                           "hard cap reached" if base_age > int(policy_refine["review_hard_cap_days"])
                           else "premises/drift not verified" if not (verdict == "pass" and drift_checked)
                           else "non-mechanical change")
                    rep["review_queue_reason"] = f"review {age}d old; extension refused: {why}"

        # write out only when text changed
        new_text = join_plan(nfm, nbody)
        old_text = texts[rep["path"]]
        if new_text != old_text:
            try:
                chk = fm_parse(nfm)
                assert chk.get("plan_id") == meta.get("plan_id")
                if retargeted:
                    assert str(chk.get("target")) == str(newest_target(
                        drift_for_plan(rep["path"], drift_rows)))
                rep["_new_text"] = new_text
                rep["_post_meta"] = {**chk, "_path": rep["path"]}
            except Exception as e:  # noqa: BLE001 — abandon, never write a bad plan
                rep["outcome"] = "unreadable"
                rep["findings"].append(f"repair-did-not-roundtrip:{e}")
                rep["actions"] = []
                rep["review_extended"] = False
        rep["changed"] = "_new_text" in rep
        if rep["changed"] and apply:
            if dirty(rep["path"]):
                rep["changed"] = False
                rep["skipped"] = "uncommitted or untracked plan file (shared worktree)"
                rep.pop("_new_text", None)
                rep.pop("_post_meta", None)
            else:
                new_texts[rep["path"]] = rep["_new_text"]

    return reports, new_texts, degraded, cluster_ok, time.monotonic() - t0


def tally(plans_meta, post_by_path, mp, policy, today, cfg):
    st, pre = {}, []
    for p in plans_meta:
        q = post_by_path.get(p["_path"], p)
        st[str(q.get("status"))] = st.get(str(q.get("status")), 0) + 1
        if str(q.get("status")) in ("executed", "superseded", "reference"):
            continue
        cls, _, ok, _ = mp.effective_class(q, policy, today, cfg)
        if ok:
            pre.append(q.get("plan_id"))
    return st, sorted(pre)


def build_report(reports, new_texts, plans_meta, mp, cfg, today, degraded, cluster_ok,
                 drift_checked, elapsed, apply, policy):
    post = {}
    for r in reports:
        if r.get("_post_meta") is not None:
            post[r["path"]] = r["_post_meta"]
    # report-mode and apply-mode both show the POST-REFINE state; dirty-skipped
    # plans keep their old meta (r["changed"] False).
    for r in reports:
        if not r.get("changed"):
            post.pop(r["path"], None)
    before_st, before_pre = tally(plans_meta, {}, mp, policy, today, cfg)
    after_st, after_pre = tally(plans_meta, post, mp, policy, today, cfg)
    # a needs-replan flag removes pre-approval even when the text could not be
    # written (dirty skip / report mode) — the flag is the intent.
    flagged = {r["plan_id"] for r in reports if r["outcome"] == "needs-replan"}
    after_pre = sorted(x for x in after_pre if x not in flagged)
    # A premise failure seen for the FIRST time today may be transient cluster
    # state (a Flux reconcile in flight): it is flagged but only DISPATCHABLE to
    # a planner from the next day on. Every other code is dispatchable at once.
    queue = []
    for r in reports:
        if r["outcome"] != "needs-replan":
            continue
        since = str(r.get("since") or today.isoformat())
        first_day = r["replan"]["code"] == "premise-fail" and since >= today.isoformat()
        queue.append({"plan_id": r["plan_id"], "component": r.get("component"),
                      "code": r["replan"]["code"], "detail": r["replan"]["detail"],
                      "since": since, "dispatchable": not first_day})
    rq = [{"plan_id": r["plan_id"], "reason": r["review_queue_reason"]}
          for r in reports if r.get("review_queue_reason")]
    for r in reports:
        for k in [k for k in r if k.startswith("_")]:
            r.pop(k)
    cnt = {}
    for r in reports:
        cnt[r["outcome"]] = cnt.get(r["outcome"], 0) + 1
    return {
        "schema": 1, "today": today.isoformat(), "mode": "apply" if apply else "report",
        "cluster_reachable": cluster_ok, "drift_checked": drift_checked,
        "degraded": degraded, "elapsed_sec": round(elapsed, 1),
        "open_plans": len(reports), "outcomes": cnt,
        "plan_status_before": before_st, "plan_status_after": after_st,
        "preapproved_before": before_pre, "preapproved_after": after_pre,
        "planner_queue": queue, "review_queue": rq,
        "changed_paths": sorted(new_texts),
        "plans": reports,
    }


def write_atomic(path, text):
    p = REPO_ROOT / path if not os.path.isabs(path) else Path(path)
    tmp = p.with_suffix(p.suffix + ".refine-tmp")
    tmp.write_text(text)
    os.replace(tmp, p)


def read_drift(args):
    """(rows, checked). Unreadable/absent => (None, False): fail closed."""
    try:
        if args.coverage_json:
            text = Path(args.coverage_json).read_text()
        else:
            p = subprocess.run([sys.executable, str(SCRIPT_DIR / "coverage.py"), "--json"],
                               capture_output=True, text=True, timeout=420)
            text = p.stdout
        d = json.loads(text[text.index("{"):])
        if not isinstance(d.get("plan_drift"), list):
            return None, False
        return d["plan_drift"], True
    except Exception:  # noqa: BLE001
        return None, False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--coverage-json")
    ap.add_argument("--budget-sec", type=int, default=240)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--plans-dir", help="override (tests)")
    ap.add_argument("--only", nargs="*", help="restrict to these plan ids")
    args = ap.parse_args(argv)

    mp = _load("mp_for_refine", "maintenance-plan.py")
    cfg = mp.load_windows()
    if args.plans_dir:
        cfg.setdefault("planning", {})["plans_dir"] = args.plans_dir
    d = mp.plans_dir(cfg)
    if not d.is_dir():
        print(f"plan-refine: plans dir {d} missing", file=sys.stderr)
        return 2
    plans = mp.load_plans(cfg)
    if mp.PLAN_LOAD_ERRORS:
        for e in mp.PLAN_LOAD_ERRORS:
            print(f"plan-refine: UNREADABLE {e}", file=sys.stderr)
        return 2
    texts = {}
    for p in plans:
        fp = REPO_ROOT / p["_path"] if not os.path.isabs(p["_path"]) else Path(p["_path"])
        texts[p["_path"]] = fp.read_text()
    if args.only:
        keep = set(args.only)
        plans_open = [p for p in plans if p.get("plan_id") in keep]
        missing = keep - {p.get("plan_id") for p in plans_open}
        if missing:
            print(f"plan-refine: unknown plan id(s): {sorted(missing)}", file=sys.stderr)
            return 2
    today = date.fromisoformat(os.environ.get("REFINE_TODAY", date.today().isoformat()))
    policy = mp.load_autonomy_policy()
    rows, checked = read_drift(args)
    rep, new_texts, degraded, cluster_ok, el = refine(
        plans, texts, today=today, mp=mp, cfg=cfg,
        policy_refine=load_refine_policy(mp), drift_rows=rows or [],
        drift_checked=checked, evidence=default_evidence,
        premise_runner=default_premise_runner, canary=default_canary,
        budget_sec=args.budget_sec, workers=args.workers,
        dirty=git_dirty, apply=args.apply)
    if args.only:
        rep = [r for r in rep if r["plan_id"] in set(args.only)]
        new_texts = {k: v for k, v in new_texts.items() if any(r["path"] == k for r in rep)}
    report = build_report(rep, new_texts, plans, mp, cfg, today, degraded,
                          cluster_ok, checked, el, args.apply, policy)
    if args.apply:
        for path, text in new_texts.items():
            write_atomic(path, text)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"plan-refine [{report['mode']}] open={report['open_plans']} "
              f"outcomes={report['outcomes']} elapsed={report['elapsed_sec']}s")
        for dgr in degraded:
            print(f"  DEGRADED {dgr}")
        for r in report["plans"]:
            if r["outcome"] != "clean" or r["actions"]:
                print(f"  {r['outcome']:12} {r['plan_id']}  "
                      + "; ".join(a["type"] for a in r["actions"]))
        print(f"  preapproved {len(report['preapproved_before'])} -> "
              f"{len(report['preapproved_after'])}; planner_queue={len(report['planner_queue'])} "
              f"review_queue={len(report['review_queue'])}")
    return 3 if degraded else 0


if __name__ == "__main__":
    raise SystemExit(main())
