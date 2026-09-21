"""Regression test: CronJob and Job images are in the version universe
(F-b6a4bf95, 2026-09-21).

`find_raw_manifest_workloads()` closes the gap where a workload authored as a
plain manifest never entered version tracking at all. But its kind list was
("Deployment", "StatefulSet", "DaemonSet"), so ~20 CronJobs and 2 Jobs — 22
container images — were still never looked at. Not "checked and clean": never
enumerated, and therefore invisible to BOTH the version detector and the
security detector that reads from it.

TWO THINGS MUST HOLD, and the second is the one that silently breaks.

1. The kinds must be in `_RAW_WORKLOAD_KINDS`.
2. CronJob nests its pod template ONE LEVEL DEEPER than every other kind:
   `spec.jobTemplate.spec.template` rather than `spec.template`. Read the
   shallow path on a CronJob and you get an empty pod spec, therefore zero
   images, therefore an entry that looks exactly like "this workload has
   nothing to track". Adding the kind WITHOUT fixing the nesting would make
   this test's kind assertion pass while changing nothing at all — so the
   extraction is asserted directly, and a straw below proves it.

Run:  python3 runbooks/tests/test-version-check-cronjob-coverage.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))
_spec = importlib.util.spec_from_file_location(
    "cav", _REPO / "runbooks" / "check-all-versions.py")
cav = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cav)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


CRONJOB = """apiVersion: batch/v1
kind: CronJob
metadata:
  name: nightly-thing
spec:
  schedule: "0 3 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: app
              image: python:3.11-slim
"""

JOB = """apiVersion: batch/v1
kind: Job
metadata:
  name: one-shot-thing
spec:
  template:
    spec:
      containers:
        - name: app
          image: pgvector/pgvector:0.8.6-pg16
"""

# A CronJob whose image sits at the SHALLOW path is not a real Kubernetes
# object; it exists only to prove the test reads the deep one.
CRONJOB_SHALLOW = """apiVersion: batch/v1
kind: CronJob
metadata:
  name: wrong-shape
spec:
  template:
    spec:
      containers:
        - name: app
          image: neverreadthis:1.0.0
"""


def workloads_for(files: dict):
    """Run the REAL enumerator over a throwaway tree."""
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    ns = root / "kubernetes" / "apps" / "testns"
    ns.mkdir(parents=True)
    (root / "kubernetes" / "flux" / "meta" / "repositories" / "helm").mkdir(parents=True)
    for n, t in files.items():
        (ns / n).write_text(t)
    chk = cav.VersionChecker(str(root))
    out = chk.find_raw_manifest_workloads()
    tmp.cleanup()
    return out


def images(out):
    return {(i["repository"], i["tag"]) for w in out for i in w["images"]}


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    check("CronJob is in the enumerated kinds",
          "CronJob" in cav.VersionChecker._RAW_WORKLOAD_KINDS)
    check("Job is in the enumerated kinds",
          "Job" in cav.VersionChecker._RAW_WORKLOAD_KINDS)
    check("the original three kinds are untouched",
          all(k in cav.VersionChecker._RAW_WORKLOAD_KINDS
              for k in ("Deployment", "StatefulSet", "DaemonSet")))

    # --- THE NESTING, asserted directly -------------------------------------
    got = images(workloads_for({"cronjob.yaml": CRONJOB}))
    check("a CronJob's image is extracted from spec.jobTemplate.spec.template",
          ("python", "3.11-slim") in got, f"got {got!r}")

    got = images(workloads_for({"job.yaml": JOB}))
    check("a Job's image is extracted from spec.template",
          ("pgvector/pgvector", "0.8.6-pg16") in got, f"got {got!r}")

    got = images(workloads_for({"both.yaml": CRONJOB, "j.yaml": JOB}))
    check("both kinds enumerate together", len(got) == 2, f"got {got!r}")

    # A CronJob with its containers at the shallow path must yield NOTHING:
    # this is what the pre-fix code effectively saw for every real CronJob.
    got = images(workloads_for({"shallow.yaml": CRONJOB_SHALLOW}))
    check("the shallow path is NOT read for a CronJob (pre-fix behaviour "
          "produced exactly this empty result for every real CronJob)",
          ("neverreadthis", "1.0.0") not in got, f"got {got!r}")

    # --- COMMISSIONING STRAW ------------------------------------------------
    # Drop CronJob from the kind list and the image must vanish. Without this,
    # the suite would still pass with the whole change reverted.
    orig = cav.VersionChecker._RAW_WORKLOAD_KINDS
    try:
        cav.VersionChecker._RAW_WORKLOAD_KINDS = ("Deployment", "StatefulSet",
                                                  "DaemonSet")
        got = images(workloads_for({"cronjob.yaml": CRONJOB}))
        check("commissioning: with CronJob removed the image is invisible "
              "again (the pre-fix gap, reproduced)",
              ("python", "3.11-slim") not in got, f"got {got!r}")
    finally:
        cav.VersionChecker._RAW_WORKLOAD_KINDS = orig

    # --- THE LIVE TREE: the images the finding named must now be visible -----
    live = cav.VersionChecker(str(_REPO)).find_raw_manifest_workloads()
    names = {w["name"] for w in live}
    for want in ("tube-archivist-image-sync", "crash-ghost-reaper",
                 "elasticsearch-obs-recovery", "paperclip-backup-cleanup"):
        check(f"live tree enumerates {want}", want in names)
    check("live tree yields more images than workloads with none",
          len(images(live)) > 0)

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} -> {', '.join(FAILURES)}")
        return 1
    print("all tests passed")
    return 0


def test_pytest_entry() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
