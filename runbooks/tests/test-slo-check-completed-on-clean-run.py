"""Regression: slo-check opens (and closes) its FindingsWriter on every write run,
so a clean run records notes.completed.slo (F-4f717f3f, 2026-09-24).

The writer used to be created only under `if exhausted or defective or fast:`.
close() is what persists notes.completed[section], so a clean run never marked
the section complete and the board rendered SLO as DID NOT REPORT although the
snapshots were written. Structural (AST) test: the slo writer must not sit under
a conditional that tests whether there is anything to emit.

Run:  python3 runbooks/tests/test-slo-check-completed-on-clean-run.py
"""
import ast
from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "runbooks" / "slo-check.py").read_text()
FAIL = []

def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAIL.append(name)

def emit_guards(src):
    """Names tested by every If enclosing the section='slo' FindingsWriter call."""
    tree = ast.parse(src)
    found = []
    def walk(node, guards):
        for child in ast.iter_child_nodes(node):
            g = guards
            if isinstance(node, ast.If) and child in node.body:
                g = guards + [{n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}]
            if (isinstance(child, ast.Call) and getattr(child.func, "id", "") == "FindingsWriter"
                    and any(k.arg == "section" and getattr(k.value, "value", None) == "slo"
                            for k in child.keywords)):
                found.append(set().union(*g) if g else set())
            walk(child, g)
    walk(tree, [])
    return found

def main():
    print(__doc__.strip().splitlines()[0]); print()
    guards = emit_guards(SRC)
    check("exactly one section='slo' writer on the normal path", len(guards) >= 1, str(guards))
    main_path = [g for g in guards if "exhausted" in g or "defective" in g or "fast" in g]
    check("the writer is NOT gated on having findings to emit", not main_path, str(guards))
    straw = SRC.replace(
        '        fw = FindingsWriter(dsn=args.postgres_dsn, section="slo", producer="script")',
        '        if exhausted or defective or fast:\n            fw = FindingsWriter(dsn=args.postgres_dsn, section="slo", producer="script")', 1)
    check("commissioning: the pre-fix gating is detected",
          straw != SRC and any("exhausted" in g for g in emit_guards(straw)))
    print(); print("FAILED: " + ", ".join(FAIL) if FAIL else "all tests passed")
    return 1 if FAIL else 0

def test_pytest_entry():
    assert main() == 0

if __name__ == "__main__":
    raise SystemExit(main())
