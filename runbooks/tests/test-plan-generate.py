"""Regression tests for runbooks/plan-generate.py (2026-11-25).

Template plans for the mechanical classes. Must refuse everything outside the
class, produce frontmatter the REAL validator accepts, carry premises + a
verification control that can fail, and never self-approve.

Run:  python3 runbooks/tests/test-plan-generate.py
"""

from __future__ import annotations

import importlib.util
import tempfile
from datetime import date
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pg", REPO / "runbooks/plan-generate.py")
pg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pg)
mp = pg._load("mp_t2", "maintenance-plan.py")
FAILS = []
TODAY = date(2026, 11, 25)


def check(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


DEPLOY = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo
  namespace: apps
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: demo
          image: ghcr.io/o/demo:1.4.2
"""
PG = DEPLOY.replace("demo", "pgdemo").replace("ghcr.io/o/pgdemo:1.4.2", "postgres:18.6-alpine")


def tree(files):
    root = Path(tempfile.mkdtemp(prefix="gen-"))
    (root / "runbooks/maintenance/plans").mkdir(parents=True)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


INP = {"component": "demo", "namespace": "apps", "repo": "ghcr.io/o/demo",
       "current": "1.4.2", "target": "1.4.3"}


def refused(inp, tpl, root, needle=""):
    try:
        pg.generate(inp, tpl, root, TODAY)
    except pg.Refuse as e:
        return needle in str(e)
    return False


root = tree({"kubernetes/apps/apps/demo/app/deployment.yaml": DEPLOY})
pid, text, meta = pg.generate(INP, "stateless", root, TODAY)
check("stateless: plan id", pid == "demo-1.4.3")
check("stateless: draft, never self-reviewed", meta["status"] == "draft" and "review" not in meta)
check("stateless: git-revert, no capability change, no reboot",
      meta["rollback_class"] == "git-revert" and meta["capability_change"] is False
      and meta["needs_reboot"] is False)
check("stateless: premises declared and each carries a runnable read-only command",
      len(meta["premises"]) >= 3 and all(
          pg._load("pp_t", "plan-premises.py").command_is_readonly(p["run"])[0]
          for p in meta["premises"] if p["run"].startswith(("kubectl", "git"))))
check("stateless: verification has a control that can fail", "V1-CONTROL" in text and "nonexistent" in text)
check("stateless: SD-11 shape (no review yet => not pre-approved)",
      not mp.effective_class({**meta, "_path": "x"}, mp.load_autonomy_policy(), TODAY, mp.load_windows())[2])
ok_meta = {**meta, "status": "vetted", "review": "ready-for-go@2026-11-24"}
check("stateless: SD-11 pre-approves it once a reviewer says ready-for-go",
      mp.effective_class(ok_meta, mp.load_autonomy_policy(), TODAY, mp.load_windows())[2])
check("validator: zero errors for the generated frontmatter",
      not [e for e in mp.validate_plans(mp.load_windows(), [{**meta, "_path": "p/demo-1.4.3.md"}])
           if "names no existing plan" not in e])

# refusals
check("refuse: stateful app dir", refused(INP, "stateless", tree({
    "kubernetes/apps/apps/demo/app/deployment.yaml": DEPLOY,
    "kubernetes/apps/apps/demo/app/pvc.yaml": "kind: PersistentVolumeClaim\n"}), "persistent storage"))
check("refuse: major bump", refused({**INP, "target": "2.0.0"}, "stateless", root, "major"))
check("refuse: 0.x minor", refused({**INP, "current": "0.4.2", "target": "0.5.0"}, "stateless",
      tree({"kubernetes/apps/apps/demo/app/deployment.yaml": DEPLOY.replace("1.4.2", "0.4.2")}), "0.x"))
check("refuse: downgrade/same", refused({**INP, "target": "1.4.2"}, "stateless", root, "not newer"))
check("refuse: digest-pinned current", refused(INP, "stateless", tree({
    "kubernetes/apps/apps/demo/app/deployment.yaml": DEPLOY.replace("1.4.2", "1.4.2@sha256:" + "a" * 64)}), "digest"))
check("refuse: ambiguous pin (two files)", refused(INP, "stateless", tree({
    "kubernetes/apps/apps/demo/app/a.yaml": DEPLOY, "kubernetes/apps/apps/demo/app/b.yaml": DEPLOY}), "need exactly 1"))
check("refuse: cluster-core component", refused({**INP, "component": "cilium-agent"}, "stateless", root, "cluster-core"))
check("refuse: no manifest", refused({**INP, "namespace": "nope"}, "stateless", root, ""))

# db-backed
proot = tree({"kubernetes/apps/apps/pgdemo/app/deployment.yaml": PG,
              "kubernetes/apps/apps/pgdemo/app/volume.yaml": "kind: Volume\n"})
pin = {"component": "pgdemo", "namespace": "apps", "repo": "postgres", "current": "18.6-alpine",
       "target": "18.7-alpine", "volume": "pgdemo-data"}
check("db-backed: refused without a volume", refused({k: v for k, v in pin.items() if k != "volume"},
      "db-backed", proot, "--volume"))
pid, text, meta = pg.generate(pin, "db-backed", proot, TODAY)
check("db-backed: backup-restore with BOTH gates", meta["rollback_class"] == "backup-restore"
      and meta["backup_gate"] and meta["restore_proof"])
check("db-backed: gates are the real restore probe, INCONCLUSIVE stops the plan",
      "backup-restore-proof.py --volume pgdemo-data" in meta["restore_proof"]
      and "INCONCLUSIVE" in meta["backup_gate"])
sd = mp.sd11_eligibility({**meta, "status": "vetted", "review": "ready-for-go@2026-11-24"},
                         mp.load_autonomy_policy(), TODAY, 70)
check("db-backed: SD-11 eligible only because backup_gate + restore_proof exist", sd[0], str(sd[1]))
nogate = {**meta, "status": "vetted", "review": "ready-for-go@2026-11-24", "restore_proof": ""}
check("db-backed: dropping restore_proof makes it ineligible (data-loss protection intact)",
      not mp.sd11_eligibility(nogate, mp.load_autonomy_policy(), TODAY, 70)[0])
check("db-backed: refuses a non-postgres engine", refused({**pin, "repo": "mariadb"}, "db-backed", proot, ""))

# write never overwrites
root2 = tree({"kubernetes/apps/apps/demo/app/deployment.yaml": DEPLOY})
pg.write_plan(pid="demo-1.4.3", text=text, root=root2)
try:
    pg.write_plan("demo-1.4.3", text, root2)
    check("write refuses to overwrite an existing plan", False)
except pg.Refuse:
    check("write refuses to overwrite an existing plan", True)

# deterministic review
pidr, textr, metar = pg.generate(INP, "stateless", root, TODAY)
pp = root / "runbooks/maintenance/plans" / f"{pidr}.md"
pp.write_text(textr)
ok, why = pg.deterministic_review(pp, mp.load_autonomy_policy(), root, TODAY)
check("review: unregistered template NEVER self-approves", not ok and "not registered" in why, why)
pol = {"generated_plans": {"reviewed_templates": ["stateless@1"]}}
ok, why = pg.deterministic_review(pp, pol, root, TODAY)
check("review: registered template + untouched plan is approved", ok, why)
pp.write_text(textr.replace("risk: low", "risk: low\nextra_field: 1"))
ok, why = pg.deterministic_review(pp, pol, root, TODAY)
check("review: a hand edit drops it back to the LLM reviewer", not ok, why)

# scan
cov = {"needs_plan": [
    {"component": "demo", "namespace": "apps", "kind": "image", "image_repos": ["ghcr.io/o/demo"],
     "current": "1.4.2", "target": "1.4.3"},
    {"component": "x", "namespace": "apps", "kind": "chart", "current": "1", "target": "2"}]}
made, refd = pg.scan(cov, tree({"kubernetes/apps/apps/demo/app/deployment.yaml": DEPLOY}), TODAY, set())
check("scan: generates the eligible row, refuses the chart row with a reason",
      len(made) == 1 and len(refd) == 1)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: {FAILS}")
    raise SystemExit(1)
print("OK")
