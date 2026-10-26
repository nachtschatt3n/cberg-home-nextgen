"""Regression tests for the post-apply SETTLE gate (F-6c3043f9, 2026-10-23).

Incident: concurrent pushes to main made Flux Kustomizations read "dependency
revision not up to date" / ReconciliationFailed; the old single-reading gate
reverted six healthy merges. Must hold:
  * transient state that clears on re-poll -> NO revert
  * failure that persists across the settle window -> revert
  * a real hard signal (crashloop) persisting -> revert (early, after confirm)
  * mixed: transient clears but a real one persists -> revert, naming only the real one
  * a single bad reading at the window's end is never enough
  * main() wiring: the revert path is gated on settle_health

Hardening 2026-10-26 (must hold too):
  * ONE clean reading is not "settled": CLEAN_READINGS_REQUIRED consecutive
  * a pod Running + not-ready, or whose restartCount rose vs the PRE-APPLY
    baseline, is not clean (liveness kill / crash 20-60 s after start)
  * HR Reconciling=True / Ready=Unknown is not yet clean
  * HR remediation exhaustion is read from Stalled/RetriesExceeded (v2)
  * an unreadable pod list / bad JSON / a raising reading is a failure key
  * objects already failing before the apply are excluded (and reported)
  * any exception after merging reverts the batch or names what is left merged

No network/cluster: collect/sleep/clock are injected. Any git-driving test would
scrub GIT_* env; none is needed here, but we scrub anyway.
Run:  python3 runbooks/tests/test-auto-update-settle-gate.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

for k in [k for k in os.environ if k.startswith("GIT_")]:
    del os.environ[k]
_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
os.environ.pop("SWEEP_PG_DSN", None)
sys.path.insert(0, str(_REPO / "runbooks"))
sys.path.insert(0, str(_REPO / "runbooks" / "lib"))
s = importlib.util.spec_from_file_location("au", _REPO / "runbooks" / "auto-update.py")
au = importlib.util.module_from_spec(s)
s.loader.exec_module(au)

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


DEP = {"kustomization:a/x": "flux kustomization not ready: a/x [ReconciliationFailed] dependency 'a/y' revision is not up to date"}
CRASH = {"pod:a/p:CrashLoopBackOff": "a/p: CrashLoopBackOff"}


def run_seq(readings, timeout=600, poll=30, baseline=None):
    """readings: list of (hard, soft); the last repeats forever."""
    calls = {"n": 0}
    clock = {"t": 0.0}

    def collect(_ns):
        r = readings[min(calls["n"], len(readings) - 1)]
        calls["n"] += 1
        if isinstance(r, Exception):
            raise r
        return dict(r[0]), dict(r[1]), {}

    def sleep(sec):
        clock["t"] += sec

    ok, probs, info = au.settle_health({"a"}, collect=collect, sleep=sleep,
                                       now=lambda: clock["t"], timeout=timeout, poll=poll,
                                       baseline=baseline)
    return ok, probs, calls["n"], info


EMPTY = ({}, {})
REQ = au.CLEAN_READINGS_REQUIRED
check("two consecutive clean readings are required", REQ >= 2, REQ)

# 1. transient dependency-revision state that clears -> no revert (2026-10-23 incident)
ok, probs, n, _ = run_seq([({}, DEP), ({}, DEP), EMPTY])
check("transient dependency-revision clears -> ok", ok and not probs and n == 2 + REQ, (ok, probs, n))

# 2. a single bad reading then clean -> ok
ok, probs, n, _ = run_seq([({}, DEP), EMPTY])
check("single bad reading never reverts", ok and n == 1 + REQ, (ok, n))

# 2b. the very first reading clean is NOT enough on its own
ok, probs, n, _ = run_seq([EMPTY])
check("first clean reading alone is not 'settled' (needs REQ)", ok and n == REQ, (ok, n))

# 3. persistent soft failure across the whole window -> revert
ok, probs, n, _ = run_seq([({}, DEP)])
check("persistent ReconciliationFailed across window -> not ok", (not ok) and probs and n >= 10, (ok, probs, n))

# 4. real hard signal persisting -> revert after confirmation, not instantly
ok, probs, n, _ = run_seq([(CRASH, {})])
check("persistent crashloop -> not ok after confirm polls",
      (not ok) and n == au.HARD_CONFIRM_POLLS and any("CrashLoop" in p for p in probs), (ok, probs, n))

# 5. crashloop "clearing" for ONE reading then failing again: the old gate
#    returned OK on that single clean reading and the bad batch stayed. Now one
#    clean reading is not settled -> it must keep waiting and then revert.
ok, probs, n, _ = run_seq([(CRASH, {}), (CRASH, {}), EMPTY, (CRASH, {})])
check("crashloop with one clean gap -> NOT ok (wait, then revert)", not ok, (ok, probs, n))
check("...and it did not stop at the single clean reading (n > 3)", n > 3, n)
# 5b. after a crash the container's restartCount stays risen vs the baseline:
#     that is a not-clean key forever, so the batch is reverted at window end.
RESTARTED = {"pod:a/p:restarted": "a/p[app]: restartCount 0->2 since the pre-apply baseline"}
ok, probs, n, _ = run_seq([(CRASH, {}), (CRASH, {}), ({}, RESTARTED)])
check("crash then Running with risen restartCount -> not ok", (not ok)
      and any("restartCount" in p for p in probs), (ok, probs, n))
# 5c. Running but not-ready persisting (liveness kills, restartCount < 5) -> not ok
NOTREADY = {"pod:a/p:notready": "a/p: not ready (phase=Running)"}
ok, probs, n, _ = run_seq([({}, NOTREADY)])
check("Running + not-ready persisting -> not ok", (not ok) and any("not ready" in p for p in probs), (ok, probs))

# 6. mixed: transient clears, real one persists -> revert, and reason names the real one
ok, probs, n, _ = run_seq([(CRASH, DEP), (CRASH, {}), (CRASH, {})])
check("mixed: real persists -> not ok", not ok and any("CrashLoop" in p for p in probs), (ok, probs, n))

# 7. problem appears only at the very end of the window (single reading) -> not reverted
calls = {"n": 0}


def collect_late(_ns):
    calls["n"] += 1
    # bad on call 1 only, then clean on the confirming polls
    return ({}, DEP if calls["n"] == 1 else {}, {})


clock = {"t": 0.0}
ok, probs, _info = au.settle_health({"a"}, collect=collect_late,
                                    sleep=lambda x: clock.__setitem__("t", clock["t"] + x),
                                    now=lambda: clock["t"], timeout=0, poll=30)
check("bad only in final single reading -> ok (needs persistence)", ok, (ok, probs))

# 7b. flapping (never two clean, never the same key twice) -> fail closed after grace
K1, K2 = ({}, {"x:1": "flap one"}), ({}, {"x:2": "flap two"})
ok, probs, n, _ = run_seq([K1, EMPTY, K2, EMPTY, K1, EMPTY, K2, EMPTY], timeout=0)
check("flapping past the window -> fail closed ('did not settle')",
      (not ok) and any("did not settle" in p for p in probs), (ok, probs, n))

# 7c. a reading that RAISES (e.g. json ValueError) is a failure, never healthy
ok, probs, n, _ = run_seq([ValueError("Expecting value: line 1 column 1")])
check("raising reading persisting -> not ok", (not ok) and any("reading failed" in p for p in probs),
      (ok, probs))
ok, probs, n, _ = run_seq([ValueError("blip"), EMPTY])
check("one raising reading then clean -> ok (transient)", ok and n == 1 + REQ, (ok, n))

# 8. pre-existing failures (cluster-wide Flux keys) are excluded but reported
PRE = {"kustomization:other/z": "flux kustomization not ready: other/z [BuildFailed] broken since last week"}
base = {"keys": set(PRE), "pods": set(), "restarts": {}}
ok, probs, n, info = run_seq([({}, PRE)], baseline=base)
check("pre-existing not-Ready object does not revert", ok and n == REQ, (ok, probs, n))
check("...and it is reported", any("broken since last week" in p for p in info["preexisting"]), info)
ok, probs, n, info = run_seq([({}, {**PRE, **NOTREADY})], baseline=base)
check("pre-existing excluded, NEW failure still reverts",
      (not ok) and any("not ready (phase" in p for p in probs)
      and not any("broken since" in p for p in probs), (ok, probs))
# a pod already unhealthy before the apply is excluded as an OBJECT
base_pod = {"keys": {"pod:a/old:notready"}, "pods": {"pod:a/old"}, "restarts": {}}
ok, probs, n, info = run_seq([({}, {"pod:a/old:restarted": "a/old: restartCount 3->9"})], baseline=base_pod)
check("pod unhealthy pre-apply: its later restart keys are excluded", ok, (ok, probs))
# escalation of a pre-existing soft HR to Stalled is NOT excluded (distinct key)
base_hr = {"keys": {"helmrelease:a/r"}, "pods": set(), "restarts": {}}
ok, probs, n, info = run_seq([({"helmrelease:a/r:stalled": "stalled RetriesExceeded"}, {})],
                             baseline=base_hr)
check("pre-existing not-Ready HR escalating to Stalled still reverts", not ok, (ok, probs))

# ── collect_health against canned kubectl JSON (au.run patched) ──────────────
import json as _json


def fake_cluster(hrs=(), kss=(), pods=None, fail=()):
    """pods: {ns: [pod dicts]}; fail: resource names whose kubectl returns rc!=0
    or 'BADJSON' for unparseable output."""
    pods = pods or {}

    def run(cmd, timeout=60, check=False):
        if cmd[:2] == ["kubectl", "get"]:
            res = cmd[2]
            ns = cmd[cmd.index("-n") + 1] if "-n" in cmd else None
            tag = ns if res == "pods" else res
            if tag in fail:
                return 1, "", "boom"
            if ("BADJSON:" + str(tag)) in fail:
                return 0, "{not json", ""
            if res.startswith("helmreleases"):
                return 0, _json.dumps({"items": list(hrs)}), ""
            if res.startswith("kustomizations"):
                return 0, _json.dumps({"items": list(kss)}), ""
            if res == "pods":
                return 0, _json.dumps({"items": pods.get(ns, [])}), ""
        return 0, "", ""
    return run


def hr(name, *conds, ns="a"):
    return {"metadata": {"namespace": ns, "name": name},
            "status": {"conditions": [dict(type=t, status=s, reason=r, message=m) for t, s, r, m in conds]}}


def pod(name, ready=True, restarts=0, phase="Running", waiting=None):
    cs = {"name": "app", "ready": ready, "restartCount": restarts,
          "state": {"waiting": {"reason": waiting}} if waiting else {"running": {}}}
    return {"metadata": {"name": name},
            "status": {"phase": phase, "containerStatuses": [cs],
                       "conditions": [{"type": "Ready", "status": "True" if ready else "False"}]}}


_real_run = au.run
try:
    # (2) helm-controller v2: RetriesExceeded lives on Stalled; Ready carries UpgradeFailed
    au.run = fake_cluster(hrs=[hr("r", ("Ready", "False", "UpgradeFailed", "Helm upgrade failed"),
                                  ("Stalled", "True", "RetriesExceeded", "Failed to upgrade after 3 attempt(s)"))])
    h, sft, _ = au.collect_health(set(), {"restarts": {}})
    check("HR Stalled/RetriesExceeded -> HARD", any(k.endswith(":stalled") for k in h), (h, sft))
    au.run = fake_cluster(hrs=[hr("r", ("Ready", "False", "RollbackSucceeded", "rolled back"),
                                  ("Stalled", "True", "MissingRollbackTarget", "no target"))])
    h, sft, _ = au.collect_health(set(), {"restarts": {}})
    check("HR Stalled/MissingRollbackTarget -> HARD", any(k.endswith(":stalled") for k in h), h)
    au.run = fake_cluster(hrs=[hr("r", ("Ready", "False", "RetriesExceeded", "old-style"))])
    h, sft, _ = au.collect_health(set(), {"restarts": {}})
    check("Ready reason alone (no Stalled) is soft, not hard", not h and "helmrelease:a/r" in sft, (h, sft))
    # HR not settled yet
    au.run = fake_cluster(hrs=[hr("r", ("Ready", "Unknown", "Progressing", "upgrading"))])
    h, sft, _ = au.collect_health(set(), {"restarts": {}})
    check("HR Ready=Unknown -> not clean", "helmrelease:a/r:settling" in sft, sft)
    au.run = fake_cluster(hrs=[hr("r", ("Ready", "True", "UpgradeSucceeded", ""),
                                  ("Reconciling", "True", "Progressing", "upgrading"))])
    h, sft, _ = au.collect_health(set(), {"restarts": {}})
    check("HR Reconciling=True -> not clean", "helmrelease:a/r:settling" in sft, sft)
    # pods: Running + not-ready, restart rise vs baseline
    au.run = fake_cluster(pods={"a": [pod("p", ready=False, restarts=2)]})
    h, sft, _ = au.collect_health({"a"}, {"restarts": {}})
    check("Running not-ready pod (restarts<5) -> not clean",
          "pod:a/p:notready" in sft and "pod:a/p:restarted" in sft and not h, (h, sft))
    au.run = fake_cluster(pods={"a": [pod("p", ready=True, restarts=3)]})
    h, sft, _ = au.collect_health({"a"}, {"restarts": {("a", "p", "app"): 1}})
    check("ready pod whose restartCount rose vs baseline -> not clean", "pod:a/p:restarted" in sft, sft)
    h, sft, _ = au.collect_health({"a"}, {"restarts": {("a", "p", "app"): 3}})
    check("ready pod with unchanged restartCount -> clean", not h and not sft, (h, sft))
    # baseline capture from the same reader
    base = au.capture_baseline({"a"})
    check("baseline records restart counts", base["restarts"].get(("a", "p", "app")) == 3, base)
    check("baseline readable", not base["unreadable"], base)
    # (3) unreadable pod list is a failure key, not healthy
    au.run = fake_cluster(pods={"a": [pod("p")]}, fail={"a"})
    h, sft, _ = au.collect_health({"a"}, {"restarts": {}})
    check("kubectl get pods failing -> 'unreadable' soft key", "pods:a:unreadable" in sft, sft)
    # (4) bad JSON from kubectl is unreadable, never an exception / healthy
    au.run = fake_cluster(pods={"a": [pod("p")]}, fail={"BADJSON:a"})
    try:
        h, sft, _ = au.collect_health({"a"}, {"restarts": {}})
        check("pods bad JSON -> 'unreadable' soft key (no raise)", "pods:a:unreadable" in sft, sft)
    except ValueError as e:
        check("pods bad JSON -> 'unreadable' soft key (no raise)", False, e)
    # (5) unreadable baseline -> flagged so main() does not merge
    au.run = fake_cluster(fail={"helmreleases.helm.toolkit.fluxcd.io"})
    base = au.capture_baseline({"a"})
    check("unreadable baseline is flagged", bool(base["unreadable"]), base)
    # pre-existing failures captured in the baseline
    au.run = fake_cluster(kss=[hr("z", ("Ready", "False", "BuildFailed", "broken"), ns="other")])
    base = au.capture_baseline({"a"})
    check("baseline captures pre-existing not-Ready Flux object",
          "kustomization:other/z" in base["keys"] and not base["unreadable"], base)
    # end-to-end: that pre-existing object does not fail the real collect path
    ok, probs, info = au.settle_health({"a"}, sleep=lambda x: None, now=lambda: 0.0,
                                       timeout=600, poll=30, baseline=base)
    check("real collect path: pre-existing excluded -> ok, reported",
          ok and any("broken" in p for p in info["preexisting"]), (ok, probs, info))
finally:
    au.run = _real_run

# 8b. revert_batch: newest first, unknown sha resolved from origin/main, push failure is LOUD
def fake_git(push_rc=0, log_out=""):
    calls = []

    def run(cmd, timeout=60, check=False):
        calls.append(cmd)
        if "log" in cmd:
            return 0, log_out, ""
        if "push" in cmd:
            return push_rc, "", "rejected" if push_rc else ""
        return 0, "", ""
    return run, calls


_real_run, _real_sync = au.run, au.git_sync
try:
    au.git_sync = lambda: None
    au.run, calls = fake_git(log_out="ffff111 fix(container): update z ( 1 → 2 ) (#9)\n")
    rev, failed = au.revert_batch([{"number": 8, "merge_sha": "aaaa111"}, {"number": 9, "merge_sha": "unknown"}])
    order = [c[-1] for c in calls if "revert" in c]
    check("revert_batch reverts newest first", order == ["ffff111", "aaaa111"], order)
    check("unknown merge sha resolved via '(#N)' subject on origin/main", rev == ["ffff111", "aaaa111"]
          and not failed, (rev, failed))
    au.run, calls = fake_git(push_rc=1)
    rev, failed = au.revert_batch([{"number": 8, "merge_sha": "aaaa111"}])
    check("revert push failure -> nothing counted reverted, failure named",
          rev == [] and failed and "not pushed" in failed[0]["reason"], (rev, failed))
    au.run, calls = fake_git(log_out="")
    rev, failed = au.revert_batch([{"number": 8, "merge_sha": "unknown"}])
    check("unresolvable sha -> LEFT MERGED with reason", failed and failed[0]["reason"] == "merge sha unknown",
          failed)
finally:
    au.run, au.git_sync = _real_run, _real_sync

# 9. wiring: main() must route the revert through settle (post_apply_health -> settle_health)
import inspect
check("post_apply_health delegates to settle_health",
      "settle_health(" in inspect.getsource(au.post_apply_health))
src_main = inspect.getsource(au.main)
check("main() still reverts on a failed gate", "_revert_and_alert(" in src_main
      and "revert_batch(" in inspect.getsource(au._revert_and_alert)
      and "post_apply_health(" in src_main)
check("main() captures a PRE-APPLY baseline before merging",
      0 <= src_main.find("capture_baseline(") < src_main.find("merge_pr("))


# 10. fail closed: an exception AFTER merging reverts the batch (main() driven)
class _Args:
    pass


def drive_main(raise_in, revert_result=None):
    """Run main(--apply) with one safe PR, patching I/O. `raise_in` names the
    step that raises. Returns (rc, events, result)."""
    ev = []
    saved = {k: getattr(au, k) for k in ("load_policy", "_load_version_checker", "list_renovate_prs",
                                         "classify", "affected_apps", "capture_baseline", "merge_pr",
                                         "git_sync", "reconcile", "post_apply_health", "revert_batch",
                                         "record_autonomy", "_writer", "age_waivers", "RECONCILE_WAIT_S",
                                         "emit_json")}
    out = {}
    saved_notify = None
    try:
        au.load_policy = lambda: {"version": "t"}
        au._load_version_checker = lambda: None
        au.list_renovate_prs = lambda: [{"number": 7}]
        au.classify = lambda pr, p, c: {"number": 7, "verdict": "safe", "dep": "x/y", "new": "1.0.1",
                                        "cur": "1.0.0", "reason": "t"}
        au.age_waivers = lambda p: ([], [], [])
        au.affected_apps = lambda n: {("a", "app")}
        au.capture_baseline = lambda ns: {"keys": set(), "pods": set(), "restarts": {}, "report": {},
                                          "unreadable": []}
        au.merge_pr = lambda n: (ev.append("merge") or ("abc1234", None))

        def boom(step):
            def f(*a, **k):
                ev.append(step)
                if raise_in == step:
                    raise ValueError(f"{step} exploded")
                return (True, [], {"readings": 2, "preexisting": []}) if step == "gate" else None
            return f
        au.git_sync = boom("sync")
        au.reconcile = boom("reconcile")
        au.post_apply_health = lambda ns, baseline=None: boom("gate")()
        au.revert_batch = lambda merged: (ev.append("revert") or (revert_result or (["abc1234"], [])))
        au.record_autonomy = lambda m, o: ev.append(f"autonomy:{o}") or []
        au._writer = lambda: None
        au.RECONCILE_WAIT_S = 0
        au.emit_json = lambda r: out.update(r)
        # NEVER reach the real notifier: _revert_and_alert imports
        # `notify.ingest_or_notify`, which UPSERTs a critical issue into the
        # live OpenClaw store (it did once, 2026-10-26, before this stub).
        fake_notify = types.ModuleType("notify")
        fake_notify.ingest_or_notify = lambda payload, **kw: (ev.append("notify") or "stub")
        saved_notify = sys.modules.get("notify")
        sys.modules["notify"] = fake_notify
        os.environ["AUTO_UPDATE_APPLY"] = "1"
        rc = au.main(["--apply", "--json"])
    finally:
        if saved_notify is not None:
            sys.modules["notify"] = saved_notify
        else:
            sys.modules.pop("notify", None)
        sys.stdout = sys.__stdout__
        for k, v in saved.items():
            setattr(au, k, v)
        os.environ.pop("AUTO_UPDATE_APPLY", None)
    return rc, ev, out


rc, ev, out = drive_main("gate")
check("exception in the gate after merge -> batch reverted (rc 2)",
      rc == 2 and "revert" in ev and "autonomy:reverted" in ev, (rc, ev))
check("revert path alerted through the STUB notifier (never the live one)", "notify" in ev, ev)
rc, ev, out = drive_main("sync")
check("exception in git sync after merge -> batch reverted", rc == 2 and "revert" in ev, (rc, ev))
rc, ev, out = drive_main("gate", revert_result=([], [{"number": 7, "sha": None, "reason": "merge sha unknown"}]))
check("revert impossible -> rc 3 and LEFT MERGED recorded with a reason",
      rc == 3 and out.get("left_merged") and out["left_merged"][0]["reason"], (rc, out.get("left_merged")))
rc, ev, out = drive_main(None)
check("healthy path still merges and records green", rc == 0 and "autonomy:green" in ev and "revert" not in ev,
      (rc, ev))

print(f"\n{'FAILED: ' + ', '.join(FAILURES) if FAILURES else 'ALL PASS'}")
sys.exit(1 if FAILURES else 0)
