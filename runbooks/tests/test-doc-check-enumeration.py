#!/usr/bin/env python3
"""
Regression tests for doc-check.py's app enumeration (2026-08-22).

Two blind spots, opposite directions:

  1. find_helmrelease_apps() enumerates DIRECTORIES, so a workload authored
     inside another app's folder never entered the denominator. authentik-pg --
     an entire postgres Deployment -- was never examined while section 3
     reported "all cluster apps appear documented".

  2. Nothing checked the reverse: the section printed "Apps in cluster: N"
     without ever contacting the cluster, so a workload applied by hand and
     never committed ran indefinitely with no signal.

These tests guard the fix AND, more importantly, that the new drift detector
can still SEE -- narrowing a detector to kill false positives has repeatedly
created false negatives in this repo.

Run: python3 runbooks/tests/test-doc-check-enumeration.py
"""
import importlib.util
import json
import os
import pathlib
import sys

os.environ["_MISE_ACTIVATED"] = "1"
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.chdir(ROOT)
spec = importlib.util.spec_from_file_location("dc", ROOT / "runbooks" / "doc-check.py")
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r}\n        want {want!r}")
        FAIL += 1


def fake_cluster(items):
    dc.run_cmd = lambda *a, **k: (0, json.dumps({"items": items}), "")


def W(ns, n, **md):
    return {"metadata": dict(namespace=ns, name=n, **md)}


print("doc-check enumeration tests\n")

# --- direction 1: repo sub-workloads are enumerated at all -----------------
subs = dc.find_repo_subworkloads()
names = {n for _ns, _p, n, _k in subs}
check("authentik-pg is enumerated (was invisible)", "authentik-pg" in names, True)
check("sub-workloads found in repo", len(subs) > 0, True)
# postRenderer patches parse as kind: Deployment but carry no image -- they are
# modifications of an existing workload, not new components to document.
check("every enumerated sub-workload has a parent app",
      all(p for _ns, p, _n, _k in subs), True)

# --- direction 2: the drift detector must actually fire --------------------
fake_cluster([W("office", "hand-applied-thing")])
check("hand-applied workload is flagged",
      dc.find_unexplained_workloads("t")[0], ["office/hand-applied-thing"])

fake_cluster([W("office", "x", annotations={"meta.helm.sh/release-name": "r"})])
check("Helm-created workload is not flagged", dc.find_unexplained_workloads("t")[0], [])

fake_cluster([W("office", "x", ownerReferences=[{"kind": "ReplicaSet"}])])
check("controller-owned workload is not flagged", dc.find_unexplained_workloads("t")[0], [])

fake_cluster([W("kube-system", "ak-outpost-foo-forward-auth")])
check("authentik outpost is not flagged", dc.find_unexplained_workloads("t")[0], [])

fake_cluster([W("flux-system", "source-controller")])
check("bootstrap component is not flagged", dc.find_unexplained_workloads("t")[0], [])

fake_cluster([W("kube-system", "authentik-pg")])
check("repo-declared sub-workload is not flagged", dc.find_unexplained_workloads("t")[0], [])

# --- the control: a broken query must never read as a clean cluster --------
dc.run_cmd = lambda *a, **k: (1, "", "connection refused")
check("kubectl failure reports 0 examined, not a clean zero",
      dc.find_unexplained_workloads("t")[1], 0)

dc.run_cmd = lambda *a, **k: (0, "not json", "")
check("unparseable output reports 0 examined",
      dc.find_unexplained_workloads("t")[1], 0)

print(f"\n  {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
