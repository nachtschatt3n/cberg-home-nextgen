"""Regression test: a fixable CVE in an image WE build is never an AR-029
acceptance (F-3355f834 / F-4677123a, 2026-09-22).

AR-029 accepts a fixable CVE when no newer upstream tag exists, on the stated
grounds that it "needs an upstream rebuild we don't do". For
`ghcr.io/nachtschatt3n/**` that rationale is inverted: those images are built
and published by the operator's own app repos, so we ARE upstream, a rebuild is
exactly the remedy, and it is entirely within our control. CLAUDE.md states this
as a hard rule. The branch absorbed them anyway, which filed a fixable CVE in an
image we build as unactionable BECAUSE we build it.

It compounded. The version side's REBUILD lane is fed only by "a newer tag
exists", which is never true for an image already on its newest self-built tag,
so these rows reached neither the security board nor the rebuild queue.
Measured when the guard was added: 53 open accepted rows named this namespace,
against 125 third-party rows that must keep their acceptance.

THE TRAP THIS TEST PINS HARDEST. `_is_permanently_unscannable()` looks like an
ownership predicate and is not — it is `startswith(PREFIX) and not
_trivy_has_private_creds()`, i.e. a statement about SCAN COVERAGE. Under the
orchestrated sweep, which passes a gh token through as TRIVY_PASSWORD, it
returns False for every self-built image. Wiring the guard to it would have made
the fix silently inert in the only run that matters, while reading as correct.

TWO DELIBERATE NON-CHANGES, asserted below so a later edit cannot quietly undo
the reasoning:
  * the NO-UPSTREAM-FIX branch keeps accepting our images. When no patched
    version exists anywhere, owning the Dockerfile does not help.
  * the FLOATING branch is untouched. "Pin an immutable tag" is good advice for
    our images too.

THESE ARE STRUCTURAL ASSERTIONS. The branch chain lives deep inside a long
function with no seam to call it through, and refactoring production code purely
to make it testable would be a larger and riskier change than the fix. The
assertions therefore read the source. That is weaker than a behavioural test and
is stated plainly rather than dressed up; the predicate itself IS exercised
behaviourally below.

Run:  python3 runbooks/tests/test-security-check-self-built-not-accepted.py
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))
SRC = (_REPO / "runbooks" / "security-check.py").read_text()

_spec = importlib.util.spec_from_file_location(
    "seccheck", _REPO / "runbooks" / "security-check.py")
_sec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sec)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def _fixable_branch() -> str:
    """The fixable-CVE decision chain only (not the no-upstream-fix branch).

    Anchored on the lookup call that OPENS the chain, not on
    `_UNBUMPABLE_CRIT_ESCALATE`: that name also appears at its own definition
    and in the long comment above it, so slicing from there would start ~1300
    lines earlier and swallow the definition of `_is_permanently_unscannable` —
    making the "the guard does not use it" assertion below pass or fail for
    entirely the wrong reason. This already broke once, when wrapping the
    escalate condition across two lines took its trailing colon with it.
    """
    start = SRC.index("newer = _newer_upstream_tag_exists(img)")
    end = SRC.index("NO UPSTREAM FIX at all")
    return SRC[start:end]


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # --- the predicate, exercised for real -----------------------------------
    pfx = _sec._PRIVATE_REGISTRY_PREFIX
    check("the ownership prefix is our own registry namespace",
          pfx == "ghcr.io/nachtschatt3n/", f"got {pfx!r}")
    check("a self-built image matches it",
          "ghcr.io/nachtschatt3n/absenty:production-20260818185444".startswith(pfx))
    check("a third-party image does NOT match it",
          not "ghcr.io/paperless-ngx/paperless-ngx:3.1.3".startswith(pfx))
    check("a lookalike outside our namespace does NOT match",
          not "ghcr.io/nachtschatt3n-fork/thing:1.0".startswith(pfx))

    # --- THE TRAP: ownership must not be wired to scan coverage --------------
    branch = _fixable_branch()
    check("the guard does NOT use _is_permanently_unscannable (that is a "
          "SCAN-COVERAGE predicate and returns False for every self-built image "
          "whenever registry creds are present, i.e. under the real sweep)",
          "_is_permanently_unscannable" not in branch)
    check("the guard tests the registry prefix directly",
          "_PRIVATE_REGISTRY_PREFIX" in branch)

    # Prove the trap is real rather than hypothetical: with creds set, the
    # scan-coverage predicate answers False for a self-built image.
    os.environ["TRIVY_PASSWORD"] = "x"
    try:
        check("commissioning: _is_permanently_unscannable is False for a "
              "self-built image when creds exist (so it would have made the "
              "guard inert under the orchestrated sweep)",
              _sec._is_permanently_unscannable(
                  "ghcr.io/nachtschatt3n/absenty:production-1") is False)
    finally:
        os.environ.pop("TRIVY_PASSWORD", None)

    # --- the branch exists, and routes away from ACCEPTED --------------------
    check("a self-built branch exists in the fixable chain",
          "OUR OWN image" in branch)
    # Scope to the self-built block ONLY. The first version of this assertion
    # searched non-greedily from the `elif` to the first `f.add(ACCEPTED` and
    # matched straight through into the `else:` branch that follows it —
    # reporting a failure while the code was correct. Slice on the real block
    # boundary rather than pattern-matching across it.
    _sb = branch[branch.index("elif img.startswith(_PRIVATE_REGISTRY_PREFIX):"):]
    _sb = _sb[:_sb.index("\n                    else:")]
    check("...and it does not tag the finding ACCEPTED",
          "f.add(ACCEPTED" not in _sb)
    check("commissioning: that slice is really the self-built block and is not "
          "empty (an empty slice would make the assertion above pass vacuously)",
          "n_rebuild += 1" in _sb and len(_sb) > 400, f"len={len(_sb)}")
    check("...and it counts into its own bucket, not the accepted one",
          "n_rebuild += 1" in branch)
    check("the summary reports the self-built bucket",
          "n_rebuild} SELF-BUILT" in SRC)
    check("n_rebuild is initialised",
          re.search(r"n_rebuild\s*=\s*0", SRC) is not None)

    # --- third-party behaviour must be untouched -----------------------------
    check("third-party already-newest images still land in AR-029",
          "[AR-029] `{tag}`: {r['crit_fix']} CRITICAL" in branch
          and "needs an upstream rebuild we don't do (accepted)" in branch)
    check("the floating branch is left intact (pinning advice is right for our "
          "images too)", "floating tag — upstream re-publishes it in place" in branch)

    # --- the escalate branch must not capture our images ---------------------
    # Measured 2026-09-22: no self-built image carries >= 50 fixable criticals
    # (highest was 23), so this is latent rather than live — but the escalate
    # message says "no bump can fix this", which is false for an image we build.
    check("the escalate branch excludes self-built images",
          re.search(r"_UNBUMPABLE_CRIT_ESCALATE\s*\n?\s*and not "
                    r"img\.startswith\(_PRIVATE_REGISTRY_PREFIX\)", SRC) is not None)

    # --- the deliberate NON-change ------------------------------------------
    nofix = SRC[SRC.index("NO UPSTREAM FIX at all"):]
    nofix = nofix[:nofix.index("n_accepted += 1") + 20]
    check("the NO-UPSTREAM-FIX branch still accepts our images too (owning the "
          "Dockerfile cannot help when no patched version exists anywhere)",
          "_PRIVATE_REGISTRY_PREFIX" not in nofix and "[AR-029]" in nofix)

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
