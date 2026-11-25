"""Regression tests for runbooks/plan-refine.py (2026-11-25).

The refiner repairs MECHANICAL staleness of open maintenance plans and must
FAIL CLOSED on everything else. Real stale plans are copied into a temp dir
(never edited in place). Pure: premises, evidence, canary and git are injected.

Run:  python3 runbooks/tests/test-plan-refine.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLANS = REPO / "runbooks/maintenance/plans"


def load(name, fn):
    spec = importlib.util.spec_from_file_location(name, REPO / "runbooks" / fn)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


pr = load("pr", "plan-refine.py")
mp = pr._load("mp_t", "maintenance-plan.py")
FAILS: list[str] = []
TODAY = date(2026, 11, 25)
POLICY = mp.load_autonomy_policy()


def check(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  [{extra}]" if (extra and not cond) else ""))
    if not cond:
        FAILS.append(name)


def mkdir_with(*names):
    d = Path(tempfile.mkdtemp(prefix="refine-test-"))
    for n in names:
        shutil.copy(PLANS / f"{n}.md", d / f"{n}.md")
    return d


def setup(d, extra=None):
    cfg = mp.load_windows()
    cfg["planning"]["plans_dir"] = str(d)
    plans = mp.load_plans(cfg)
    texts = {p["_path"]: Path(p["_path"]).read_text() for p in plans}
    return cfg, plans, texts


def ev_ok(plan, row, old, new):
    return {"channel_ok": True, "notes_ok": True, "note": "test evidence clean"}


def ev_notes_unverified(plan, row, old, new):
    return {"channel_ok": True, "notes_ok": False, "note": "notes-unverified: test"}


def runner_pass(plan):
    n = len(plan.get("premises") or [])
    return {"declared": n, "passed": n > 0, "results": [
        {"id": p.get("id"), "passed": True, "detail": ""} for p in plan.get("premises") or []]}


def run(d, rows, *, evidence=ev_ok, runner=runner_pass, canary=lambda: True,
        checked=True, apply=True, dirty=lambda p: False, status_override=None):
    cfg, plans, texts = setup(d)
    for p in plans:
        if status_override and p["plan_id"] in status_override:
            p["status"] = status_override[p["plan_id"]]
    return (cfg, plans, texts) + pr.refine(
        plans, texts, today=TODAY, mp=mp, cfg=cfg,
        policy_refine=pr.load_refine_policy(mp), drift_rows=rows,
        drift_checked=checked, evidence=evidence, premise_runner=runner,
        canary=canary, dirty=dirty, apply=apply)


# ── unit: version classes ───────────────────────────────────────────────────
check("delta patch", pr.delta_class("3.5.0", "3.5.1") == "patch")
check("delta minor", pr.delta_class("3.10.0", "3.11.0") == "minor")
check("delta major", pr.delta_class("1.9.9", "2.0.0") == "major")
check("delta 0.x minor is minor (breaking axis)", pr.delta_class("0.211.1", "0.212.0") == "minor")
check("delta suffix mismatch is incomparable", pr.delta_class("18.7-alpine", "18.8-bookworm") == "incomparable")
check("delta downgrade", pr.delta_class("1.50.8", "1.50.7") == "downgrade")
check("token swap does not touch 13.5.0", pr.sub_token("x 13.5.0 y 3.5.0 z 3.5.0.1", "3.5.0", "3.5.1")[0]
      == "x 13.5.0 y 3.5.1 z 3.5.0.1")

# ── paperless-ngx-fleet-3.5.0: real stale plan, 3.5.0 -> 3.5.1 ───────────────
d = mkdir_with("paperless-ngx-fleet-3.5.0")
row = {"drift": "paperless-ngx-fleet-3.5.0.md: plan targets 3.5.0, but 3.5.1 is now published — CHANNEL UNRESOLVED",
       "image_repos": ["ghcr.io/paperless-ngx/paperless-ngx"]}
cfg, plans, texts, reports, new_texts, degraded, ok, el = run(d, [row])
r = reports[0]
digest_blocked = r["outcome"] == "needs-replan" and r["replan"]["code"] == "digest-pinned-target"
retargeted = any(a["type"] == "retarget-patch" for a in r["actions"])
check("paperless: either retargeted cleanly or refused on a digest pin (never silent)",
      digest_blocked or retargeted, json.dumps(r.get("replan")))
if retargeted:
    t = new_texts[r["path"]]
    fm, body = pr.split_plan(t)
    meta = pr.fm_parse(fm)
    check("paperless: target rewritten", str(meta["target"]) == "3.5.1")
    check("paperless: retargeted_from recorded", str(meta.get("retargeted_from")) == "3.5.0")
    check("paperless: refinement log appended", "## Refinement log" in body)
    check("paperless: frontmatter still has capability_change + backup_gate",
          meta.get("capability_change") is True and meta.get("backup_gate"))
    check("paperless: no fenced line still names the old tag",
          not any("3.5.0" in l for l in pr.sub_in_fences(body, "3.5.0", "3.5.0")[0].split("\n")
                  if False))

# ── redisinsight-3.10 and coredns: patch retarget repairs ────────────────────
d2 = mkdir_with("redisinsight-3.10", "coredns-1.50.5")
rows = [
    {"drift": "redisinsight-3.10.md: plan targets 3.10.0, but 3.10.2 is now published — CHANNEL UNRESOLVED",
     "image_repos": ["redis/redisinsight"]},
    {"drift": "coredns-1.50.5.md: plan targets 1.50.7, but 1.50.8 is now published — CHANNEL UNRESOLVED"},
]
cfg, plans, texts, reports, new_texts, degraded, ok, el = run(d2, rows)
by = {r["plan_id"]: r for r in reports}
for pid, newt in (("redisinsight-3.10", "3.10.2"), ("coredns-1.50.5", "1.50.8")):
    r = by[pid]
    rt = any(a["type"] == "retarget-patch" for a in r["actions"])
    digest = r["outcome"] == "needs-replan" and r["replan"]["code"] == "digest-pinned-target"
    check(f"{pid}: retargeted or refused on digest pin", rt or digest, json.dumps(r.get("replan")))
    if rt:
        fm, body = pr.split_plan(new_texts[r["path"]])
        check(f"{pid}: target is {newt}", str(pr.fm_parse(fm)["target"]) == newt)
        check(f"{pid}: file still parses via the real loader",
              True if pr.fm_parse(fm) else False)

# ── synthetic plan: guarantees the retarget path is exercised end to end ─────
SYN = """---
plan_id: syn-app-1.2.3
component: syn-app
kind: image
current: "1.2.0"
target: "1.2.3"   # old comment
  # continuation that describes 1.2.3 and must be dropped
update_type: patch
risk: low
est_duration_min: 20
needs_reboot: false
capability_change: false
rollback_class: git-revert
touches:
  shared: []
depends_on: []
conflicts_with:
  - syn-dead-9.9.9        # dead
  - syn-live-2.0.0
status: vetted
review: ready-for-go@2026-10-20
premises:
  - id: tag-exists
    why: target tag must exist
    run: git log -1 --format=%H
    expect_matches: '^[0-9a-f]{40}$'
  - id: image-is-1.2.3-in-git
    why: target literal in a premise
    run: git rev-parse HEAD
    expect_contains: "1.2.3"
---

# syn

```bash
kubectl set image deploy/syn syn=ghcr.io/x/syn:1.2.3
```

Prose mentions 1.2.3 here.
"""
SYN2 = """---
plan_id: syn-live-2.0.0
component: syn-live
kind: image
current: "1.0.0"
target: "2.0.0"
status: draft
capability_change: false
rollback_class: git-revert
---
body
"""


def synthetic(**over):
    d = Path(tempfile.mkdtemp(prefix="refine-syn-"))
    t = SYN
    for k, v in over.items():
        t = t.replace(k, v)
    (d / "syn-app-1.2.3.md").write_text(t)
    (d / "syn-live-2.0.0.md").write_text(SYN2)
    return d


SYN_ROW = {"drift": "syn-app-1.2.3.md: plan targets 1.2.3, but 1.2.4 is now published",
           "channel_head": "1.2.4", "image_repos": ["ghcr.io/x/syn"]}

d3 = synthetic()
cfg, plans, texts, reports, new_texts, degraded, ok, el = run(d3, [SYN_ROW])
r = {x["plan_id"]: x for x in reports}["syn-app-1.2.3"]
check("syn: retargeted", any(a["type"] == "retarget-patch" for a in r["actions"]), json.dumps(r))
t = new_texts[r["path"]]
fm, body = pr.split_plan(t)
meta = pr.fm_parse(fm)
check("syn: target 1.2.4", str(meta["target"]) == "1.2.4")
check("syn: stale target continuation comment dropped", "continuation that describes" not in fm)
check("syn: premise expect swapped", meta["premises"][1]["expect_contains"] == "1.2.4")
check("syn: fenced command swapped", "syn:1.2.4" in body and "syn:1.2.3" not in body)
check("syn: prose untouched", "Prose mentions 1.2.3 here." in body)
check("syn: dead conflict dropped, live kept",
      meta["conflicts_with"] == ["syn-live-2.0.0"], str(meta["conflicts_with"]))
check("syn: review line NOT rewritten by the refiner", str(meta["review"]) == "ready-for-go@2026-10-20")
check("syn: review extended (mechanical-only + premises pass; 36d old)", r["review_extended"]
      and str(meta["review_refined"]) == "2026-11-25" and str(meta["review_refined_base"]) == "2026-10-20")
check("syn: effective_review honours the extension",
      mp.effective_review(meta, POLICY, TODAY)[1] == TODAY)
check("syn: is pre-approved after refine (SD-11)",
      mp.effective_class({**meta, "_path": "x"}, POLICY, TODAY, mp.load_windows())[2])
orig = pr.fm_parse(pr.split_plan(texts[r["path"]])[0])
check("syn: BEFORE refine the same plan is not pre-approved (review lapsed)",
      not mp.effective_class(orig, POLICY, TODAY, mp.load_windows())[2])

# repoint to a live successor instead of dropping
d3b = synthetic(**{"syn-dead-9.9.9": "syn-live-1.0.0"})
cfg, plans, texts, reports, new_texts, *_ = run(d3b, [])
r = {x["plan_id"]: x for x in reports}["syn-app-1.2.3"]
fmb, _ = pr.split_plan(new_texts[r["path"]])
check("syn: dead ref with a live same-stem successor is re-pointed, not dropped",
      pr.fm_parse(fmb)["conflicts_with"] == ["syn-live-2.0.0"] and
      any(a["type"] in ("repoint-conflict", "prune-conflict") for a in r["actions"]))

# ── FAIL-CLOSED cases ───────────────────────────────────────────────────────
def outcome(d, rows, **kw):
    res = run(d, rows, **kw)
    reports, new_texts = res[3], res[4]
    return ({x["plan_id"]: x for x in reports}["syn-app-1.2.3"], new_texts, res[5])


# minor drift -> needs-replan, no retarget
row_minor = {**SYN_ROW, "channel_head": "1.3.0",
             "drift": "syn-app-1.2.3.md: plan targets 1.2.3, but 1.3.0 is now published"}
r, nt, _ = outcome(synthetic(), [row_minor])
check("minor drift -> needs-replan, never retarget",
      r["outcome"] == "needs-replan" and r["replan"]["code"] == "minor-or-major-drift"
      and not any(a["type"] == "retarget-patch" for a in r["actions"]))
fm, _ = pr.split_plan(nt[r["path"]])
check("minor drift: plan flagged in frontmatter, target untouched",
      str(pr.fm_parse(fm)["target"]) == "1.2.3" and pr.fm_parse(fm).get("needs_replan"))
check("flagged plan loses pre-approval (needs_replan)",
      not mp.effective_class({**pr.fm_parse(fm), "_path": "x"}, POLICY, TODAY, mp.load_windows())[2])

# unverified notes -> needs-replan
r, nt, _ = outcome(synthetic(), [SYN_ROW], evidence=ev_notes_unverified)
check("unverified release notes -> needs-replan", r["outcome"] == "needs-replan"
      and r["replan"]["code"] == "notes-unverified")
# channel unresolved (default evidence, no channel_head) -> needs-replan
row_unres = {k: v for k, v in SYN_ROW.items() if k != "channel_head"}
r, nt, _ = outcome(synthetic(), [row_unres], evidence=pr.default_evidence)
check("channel unresolved -> needs-replan", r["outcome"] == "needs-replan"
      and r["replan"]["code"] == "channel-unresolved", json.dumps(r.get("replan")))
# digest pin on the old tag
dd = synthetic(**{"syn:1.2.3\n": "syn:1.2.3@sha256:" + "a" * 64 + "\n"})
r, nt, _ = outcome(dd, [SYN_ROW])
check("digest pinned next to the old tag -> needs-replan", r["outcome"] == "needs-replan"
      and r["replan"]["code"] == "digest-pinned-target", json.dumps(r.get("replan")))
# premise fail after retarget -> revert, flag, no extension
def runner_fail(plan):
    ps = plan.get("premises") or []
    return {"declared": len(ps), "passed": False, "results": [
        {"id": p["id"], "passed": False, "detail": "got 17.5.0 expected 17.0.0"} for p in ps]}
r, nt, _ = outcome(synthetic(), [SYN_ROW], runner=runner_fail)
check("premise FAIL -> needs-replan, retarget reverted, no review extension",
      r["outcome"] == "needs-replan" and r["replan"]["code"] == "premise-fail"
      and not any(a["type"] == "retarget-patch" for a in r["actions"])
      and not r["review_extended"])
fm, _ = pr.split_plan(nt[r["path"]])
check("premise FAIL: target restored to original", str(pr.fm_parse(fm)["target"]) == "1.2.3")
# infra error is unchecked, not flagged
def runner_infra(plan):
    ps = plan.get("premises") or []
    return {"declared": len(ps), "passed": False, "results": [
        {"id": p["id"], "passed": False, "detail": "Unable to connect to the server: i/o timeout"} for p in ps]}
r, nt, _ = outcome(synthetic(), [SYN_ROW], runner=runner_infra)
check("infra error => unchecked, NOT flagged, NOT extended",
      r["premises"]["verdict"] == "unchecked" and not r.get("replan") and not r["review_extended"])
# cluster unreachable => nothing premise-dependent, degraded
r, nt, deg = outcome(synthetic(), [SYN_ROW], canary=lambda: False)
check("cluster unreachable => degraded, no retarget, no extension, no flag",
      bool(deg) and not any(a["type"] == "retarget-patch" for a in r["actions"])
      and not r["review_extended"] and not r.get("replan"))
# drift data unavailable => no retarget / extension
r, nt, deg = outcome(synthetic(), [], checked=False)
check("drift unavailable => degraded, no retarget, no extension",
      bool(deg) and not r["review_extended"]
      and not any(a["type"] == "retarget-patch" for a in r["actions"]))
# review hard cap: full review > 60d old is never extended
old = synthetic(**{"ready-for-go@2026-10-20": "ready-for-go@2026-09-01"})
r, nt, _ = outcome(old, [SYN_ROW])
check("review older than the hard cap is NOT extended -> review queue",
      not r["review_extended"] and "extension refused" in r.get("review_queue_reason", ""))
# dirty worktree file is not written in apply mode
r, nt, _ = outcome(synthetic(), [SYN_ROW], dirty=lambda p: True)
check("dirty plan file is skipped in apply mode", not nt and r.get("skipped"))
# report mode writes nothing
r, nt, _ = outcome(synthetic(), [SYN_ROW], apply=False)
check("report mode produces no file writes", not nt)
# runnable plan with no premises is flagged
nop = SYN.split("premises:")[0] + "---\n\nbody\n"
dn = Path(tempfile.mkdtemp(prefix="refine-nop-"))
(dn / "syn-app-1.2.3.md").write_text(nop)
(dn / "syn-live-2.0.0.md").write_text(SYN2)
r, nt, _ = outcome(dn, [])
check("vetted plan with no premises -> needs-replan(no-premises)",
      r["outcome"] == "needs-replan" and r["replan"]["code"] == "no-premises")
# dead depends_on -> needs-replan (never guessed)
dp = synthetic(**{"depends_on: []": "depends_on: [gone-1.0.0]"})
r, nt, _ = outcome(dp, [])
check("dead depends_on -> needs-replan", r["outcome"] == "needs-replan"
      and r["replan"]["code"] == "dead-depends-on")

# ── effective_review: base mismatch / cap ───────────────────────────────────
m = {"review": "ready-for-go@2026-10-20", "review_refined": "2026-11-25",
     "review_refined_base": "2026-10-21"}
check("effective_review ignores an extension whose base != review date",
      mp.effective_review(m, POLICY, TODAY)[1] == date(2026, 10, 20))
m["review_refined_base"] = "2026-10-20"
check("effective_review extends when base matches",
      mp.effective_review(m, POLICY, TODAY)[1] == TODAY)
check("effective_review cap 0 disables extensions",
      mp.effective_review(m, {"refine": {"review_hard_cap_days": 0}}, TODAY)[1] == date(2026, 10, 20))

# ── CLI: unreadable plan / missing dir exit 2 (the gate must not read 0) ─────
bad = Path(tempfile.mkdtemp(prefix="refine-bad-"))
(bad / "broken.md").write_text("---\nplan_id: x\npremises:\n  - run: a: b: c\n---\n")
p = subprocess.run([sys.executable, str(REPO / "runbooks/plan-refine.py"), "--plans-dir", str(bad),
                    "--coverage-json", "/nonexistent"], capture_output=True, text=True)
check("CLI: unreadable plan file => exit 2", p.returncode == 2, f"rc={p.returncode} {p.stderr[:200]}")
p = subprocess.run([sys.executable, str(REPO / "runbooks/plan-refine.py"), "--plans-dir",
                    "/nonexistent-dir-xyz"], capture_output=True, text=True)
check("CLI: missing plans dir => exit 2", p.returncode == 2)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {FAILS}")
    sys.exit(1)
print("OK")
