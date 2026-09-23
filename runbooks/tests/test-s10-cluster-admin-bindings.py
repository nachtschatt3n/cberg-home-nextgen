"""Regression: every non-Flux cluster-admin ClusterRoleBinding produces a WARNING
title the register can accept (F-eb998107, 2026-09-23).

The loop in s10_flux_posture had an `if any("flux" ...)` with no else, so the
headlamp-admin and longhorn-support-bundle bindings never produced a line and
AR-008 / AR-022 accepted titles nothing emitted. Measured live 2026-09-23: five
cluster-admin bindings (bootstrap system:masters, cluster-reconciler-flux-system,
flux-operator, headlamp-admin, longhorn-support-bundle), two invisible.

Run:  python3 runbooks/tests/test-s10-cluster-admin-bindings.py
"""
from __future__ import annotations
import importlib.util, os, sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))
_spec = importlib.util.spec_from_file_location("seccheck", _REPO / "runbooks" / "security-check.py")
sc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(sc)

FAIL: list[str] = []
def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok: FAIL.append(name)

def crb(name, kind, subj, role="cluster-admin", ns=None):
    s = {"kind": kind, "name": subj}
    if ns: s["namespace"] = ns
    return {"metadata": {"name": name}, "roleRef": {"name": role}, "subjects": [s]}

LIVE_SHAPE = {"items": [
    crb("cluster-admin", "Group", "system:masters"),
    crb("cluster-reconciler-flux-system", "ServiceAccount", "kustomize-controller", ns="flux-system"),
    crb("flux-operator", "ServiceAccount", "flux-operator", ns="flux-system"),
    crb("headlamp-admin", "ServiceAccount", "headlamp", ns="monitoring"),
    crb("longhorn-support-bundle", "ServiceAccount", "longhorn-support-bundle", ns="storage"),
    crb("something-view", "ServiceAccount", "viewer", role="view"),
    crb("flux-reconciler-cluster-admin-ai", "ServiceAccount", "flux-reconciler", ns="ai"),
]}

def main() -> int:
    print(__doc__.strip().splitlines()[0]); print()
    rows = sc._cluster_admin_bindings(LIVE_SHAPE)
    by = {r[0]: r[3] for r in rows}
    check("only cluster-admin bindings are classified (view binding ignored)", "something-view" not in by and len(rows) == 6, str(by))
    check("a per-namespace tenant reconciler binding is 'tenant', not 'flux' by name accident",
          by.get("flux-reconciler-cluster-admin-ai") == "tenant")
    check("bootstrap system:masters is 'bootstrap'", by.get("cluster-admin") == "bootstrap")
    check("both flux bindings are 'flux'", by.get("cluster-reconciler-flux-system") == "flux" and by.get("flux-operator") == "flux")
    check("headlamp-admin and longhorn-support-bundle are 'other' (they were invisible)",
          by.get("headlamp-admin") == "other" and by.get("longhorn-support-bundle") == "other")
    # the emitted title shape must carry the subject AND the binding so a register needle can be stable
    others = [r for r in rows if r[3] == "other"]
    titles = [f"{', '.join(r[2])} cluster-admin ClusterRoleBinding `{r[0]}`" for r in others]
    check("titles carry subject + binding", any("headlamp cluster-admin ClusterRoleBinding `headlamp-admin`" in t for t in titles)
          and any("longhorn-support-bundle cluster-admin ClusterRoleBinding `longhorn-support-bundle`" in t for t in titles), str(titles))
    # commissioning straw: the pre-fix loop, transcribed -- zero non-flux lines
    def old_loop(crbs):
        seen = []
        for b in crbs.get("items", []):
            if b["roleRef"]["name"] == "cluster-admin":
                subjects = [s.get("name", "?") for s in b.get("subjects", [])]
                if any("flux" in s.lower() for s in subjects):
                    seen.append(("flux", b["metadata"]["name"]))
        return seen
    # The old loop matched "flux" in SUBJECT NAMES only: the reconciler binding's
    # subjects are kustomize-controller / helm-controller (namespace flux-system),
    # so it was silent too -- three of five bindings produced no line at all.
    check("commissioning: the pre-fix loop names flux-operator and (by name accident) a tenant "
          "binding; the reconciler, headlamp and longhorn bindings were all invisible",
          {n for _, n in old_loop(LIVE_SHAPE)} == {"flux-operator", "flux-reconciler-cluster-admin-ai"})
    check("the fixed loop is wired (the source uses the helper in s10_flux_posture)",
          "for b in _cluster_admin_bindings(crbs):" in (_REPO / "runbooks" / "security-check.py").read_text())
    print(); print("FAILED: " + ", ".join(FAIL) if FAIL else "all tests passed"); return 1 if FAIL else 0

def test_pytest_entry(): assert main() == 0
if __name__ == "__main__": raise SystemExit(main())
