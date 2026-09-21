#!/usr/bin/env python3
"""Regression test: max_rule_fallbacks() documents every status it emits.

F-7b04b03f. The docstring enumerated three result statuses — candidate, hold,
up-to-date — while the function also emits `already-enumerated`, which
downstream code BRANCHES on (the human report's tag map, and the lane
stamp-back loop). `docs/sops/auto-update.md` documented all four.

Low impact, unusual direction: the SOP was right and the source comment was
wrong, so the ordinary "trust the code, the docs rot" reflex gives the wrong
answer here. A future caller writing an exhaustive switch off this docstring
would silently mishandle the fourth status.

This test is written against the SOURCE rather than a hardcoded list, so it
fails for a FIFTH status added without documenting it — which is the failure
mode worth guarding, not the one already fixed.

Run: python3 runbooks/tests/test-max-rule-fallback-statuses.py
"""

from __future__ import annotations

import importlib.util
import inspect
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("cov", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def emitted_statuses(src: str) -> set:
    """Every literal the function assigns to a record's "status" key."""
    return set(re.findall(r'"status":\s*"([a-z][a-z-]*)"', src))


def documented_statuses(doc: str) -> set:
    """Status names listed in the docstring's status table.

    An entry is `name — description`, or a name alone on its line whose
    description is continued by an em-dash on the NEXT line (which is how a
    long name such as `already-enumerated` is laid out). Requiring the em-dash
    in both shapes is what keeps ordinary prose words out of the set — an
    earlier draft of this parser admitted a stray `it` and would therefore have
    reported a phantom status for any docstring.
    """
    lines = (doc or "").splitlines()
    out = set()
    for i, line in enumerate(lines):
        m = re.match(r"\s{4,}([a-z][a-z0-9-]*)\s{2,}—", line)
        if m:
            out.add(m.group(1))
            continue
        m = re.match(r"\s{4,}([a-z][a-z0-9-]*)\s*$", line)
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if m and re.match(r"\s+—", nxt):
            out.add(m.group(1))
    return out


def main() -> int:
    print("test-max-rule-fallback-statuses")

    src = inspect.getsource(cov.max_rule_fallbacks)
    doc = cov.max_rule_fallbacks.__doc__ or ""
    emitted = emitted_statuses(src)
    documented = documented_statuses(doc)

    check("the function emits the four statuses this repo relies on",
          emitted == {"candidate", "hold", "up-to-date", "already-enumerated"},
          f"emitted {sorted(emitted)}")
    check("every EMITTED status is documented in the docstring "
          "(THE defect: `already-enumerated` was not)",
          emitted <= documented,
          f"undocumented: {sorted(emitted - documented)}")
    check("the docstring invents no status the function cannot emit",
          documented <= emitted, f"phantom: {sorted(documented - emitted)}")

    # The SOP was the correct side and must stay that way.
    sop = (REPO / "docs/sops/auto-update.md").read_text()
    check("docs/sops/auto-update.md still names all four", all(
        s in sop for s in emitted), f"missing from SOP: "
        f"{sorted(s for s in emitted if s not in sop)}")

    # Downstream really does branch on the fourth one — if that stops being
    # true the docstring requirement is arguing about nothing.
    rec = inspect.getsource(cov.reconcile) + inspect.getsource(cov.human)
    check("`already-enumerated` is branched on downstream, so documenting it "
          "is load-bearing rather than decorative",
          "already-enumerated" in rec or "already enumerated" in rec)

    # ── COMMISSIONING ──────────────────────────────────────────────────
    straw_doc = doc.replace("already-enumerated", "").replace(
        "— the stable head is in the actionable universe in its own", "")
    check("commissioning: a docstring with the fourth status removed IS caught",
          not emitted <= documented_statuses(straw_doc),
          "the parser cannot see the status list — it would pass any docstring")
    straw_src = src + '\n    out.append({"status": "brand-new"})\n'
    check("commissioning: a FIFTH undocumented status would be caught too",
          not emitted_statuses(straw_src) <= documented)

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
