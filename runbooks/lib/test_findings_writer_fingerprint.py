"""Unit tests for finding IDENTITY — `fingerprint()` / `_stable_anchor()`.

The contract in one line: **a finding's identity is what it is about, never how
it is currently presented.**

Presentation includes the `[AR-0NN]` suppression tags. Folding them into the
fingerprint is what produced the 2026-08-18 defect: F-094be167 was born 08-16,
"resolved" 08-17 when AR-063 started matching (forking F-e14cda04), and
re-appeared 08-18 when AR-063's wording lapsed — one problem, three rows, and an
auto-close that read the abandoned row as fixed. A policy edit must not be able
to do that.

The tags were doing one real job: keeping an image's "there is a fix" line apart
from its "there is no fix" line. That distinction is genuine identity, so it is
now carried explicitly by `_KIND_MARKERS` instead of implicitly by whichever AR
happened to be attached.

Run:  python3 runbooks/lib/test_findings_writer_fingerprint.py
  or: python3 -m pytest runbooks/lib/test_findings_writer_fingerprint.py -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "findings_writer", str(Path(__file__).with_name("findings_writer.py")))
fw = importlib.util.module_from_spec(_spec)
sys.modules["findings_writer"] = fw
_spec.loader.exec_module(fw)

SEC, SUB = "security", "s4_cve_check"

# The two title families that collided in production, verbatim in shape.
NOFIX = ("`ghcr.io/example/app:1.2.3`: 19 CRITICAL + 31 HIGH CVE(s) with no "
         "upstream fix (accepted — unpatchable until upstream ships)")
FIXABLE = ("`ghcr.io/example/app:1.2.3`: 5 fixable CRITICAL CVE(s) — newer "
           "upstream tag available, bump the image")
REBUILD = ("`ghcr.io/example/app:1.2.3`: 27 CRITICAL + 246 HIGH fixable CVE(s) "
           "but already on the newest upstream tag — needs an upstream rebuild")


def fp(title, section=SEC, sub=SUB):
    return fw.fingerprint(section, sub, title)


# --------------------------------------------------------------------------
# The defect
# --------------------------------------------------------------------------

def test_ar_tagging_does_not_change_identity():
    """The whole point. Tagging is a suppression decision, not a new finding."""
    base = fp(FIXABLE)
    for variant in (
            "[AR-903] " + FIXABLE,
            "[AR-906] [AR-903] " + FIXABLE,
            "[AR-903][AR-906] " + FIXABLE,
            "[ar-029] " + FIXABLE,            # case-insensitive
    ):
        assert fp(variant) == base, f"AR tagging changed identity: {variant[:50]}"


def test_untagging_restores_the_same_identity():
    """The 08-18 half of the incident: an AR lapsing must not resurrect a row
    under a new id."""
    assert fp("[AR-905] " + NOFIX) == fp(NOFIX)


def test_retagging_to_a_different_ar_is_identity_preserving():
    """Re-wording an AR so a DIFFERENT one matches is still the same finding."""
    assert fp("[AR-903] " + NOFIX) == fp("[AR-904] " + NOFIX)


def test_prose_shaped_findings_are_also_ar_stable():
    """Titles with no backticked span take the _normalize() fallback, which had
    the same bug: the tag was part of the hashed prose."""
    msg = "Cluster has an unexpected externally reachable ingress"
    assert fp(msg, "security", "s8") == fp("[AR-902] " + msg, "security", "s8")


# --------------------------------------------------------------------------
# What must STILL be distinguished (the job the AR tags were doing)
# --------------------------------------------------------------------------

def test_nofix_and_fixable_remain_distinct():
    """Same image, genuinely different findings. Collapsing these would hide a
    fixable vulnerability behind an accepted unfixable one."""
    assert fp(NOFIX) != fp(FIXABLE)


def test_rebuild_is_distinct_from_both():
    assert len({fp(NOFIX), fp(FIXABLE), fp(REBUILD)}) == 3


def test_kind_survives_the_ar_tag_that_used_to_encode_it():
    """The pairing seen in production: the no-fix line carries [AR-903] and the
    fixable line does not. Identity must come from the KIND, not the tag."""
    assert fp("[AR-903] " + NOFIX) != fp(FIXABLE)
    assert fp("[AR-903] " + NOFIX) == fp(NOFIX)


# --------------------------------------------------------------------------
# Pre-existing guarantees that must not regress
# --------------------------------------------------------------------------

def test_version_is_part_of_identity():
    a = "`example-org/widget:1.2.3`: fixable CRITICAL CVE(s)"
    b = "`example-org/widget:1.2.4`: fixable CRITICAL CVE(s)"
    assert fp(a) != fp(b)


def test_reword_does_not_fork():
    """The bug _stable_anchor was originally introduced to fix."""
    a = "`example-org/widget:1.2.3`: fixable HIGH CVE(s) — newer upstream tag available"
    b = "`example-org/widget:1.2.3`: fixable HIGH CVE(s) — bump the image, newer tag exists"
    assert fp(a) == fp(b)


def test_section_and_subsection_still_scope_identity():
    assert fp(FIXABLE, "security", "s4_cve_check") != fp(FIXABLE, "version", "s4_cve_check")
    assert fp(FIXABLE, SEC, "s4_cve_check") != fp(FIXABLE, SEC, "helmrelease_image")


def test_finding_id_is_derived_and_stable():
    f = fp(FIXABLE)
    assert fw.finding_id_from_fp(f) == f"F-{f[:8]}"
    assert fw.finding_id_from_fp(fp("[AR-903] " + FIXABLE)) == fw.finding_id_from_fp(f)


# --------------------------------------------------------------------------
# Helper surface
# --------------------------------------------------------------------------

def test_strip_ar_tags_is_exported_and_total():
    assert fw.strip_ar_tags("[AR-907] [AR-908] hello") == "hello"
    assert fw.strip_ar_tags("hello") == "hello"
    assert fw.strip_ar_tags("") == ""


def test_kind_markers_are_ordered_most_specific_first():
    """`_kind_token` returns the FIRST match, so a marker that is a substring of
    another must not shadow it. Guards the ordering contract in the comment."""
    tokens = [t for t, _ in fw._KIND_MARKERS]
    assert len(tokens) == len(set(tokens)), "duplicate kind tokens"
    for i, (_, markers) in enumerate(fw._KIND_MARKERS):
        for later_token, later_markers in fw._KIND_MARKERS[i + 1:]:
            for m in markers:
                for lm in later_markers:
                    assert lm not in m, (
                        f"marker {lm!r} ({later_token}) is shadowed by {m!r}")


def _main() -> int:
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
