"""Unit tests for `_is_structurally_slow` — the image-tag oracle's
structural-vs-transient discriminator.

Why it exists. For three consecutive cycles the sweep declared its security
section INCOMPLETE, and every degradation came from the s4 image-tag oracle:
`docker.elastic.co` elasticsearch and kibana, plus Docker Hub 429s. Because a
degradation vetoes stale-finding auto-close for the whole section, 33 stale
rows accumulated and the estate was overstated by ~12%. The Trivy scan itself
was never degraded (184/184), so CVE counts stayed current while
remediation-availability verdicts went undetermined.

The elastic half of that is not an outage. Measured 2026-08-18,
`docker.elastic.co` serves a 1000-tag page in 14.2-14.5s and has thousands of
tags: elasticsearch reached 5 pages / 5000 tags in 72.5s, kibana 5 pages in
70.9s, both still paginating. No acceptable budget completes that, so it fails
the veto's only question — "could this differ on the next run?" — and belongs
on the same non-recording branch as the page cap.

The discriminator is a MEASUREMENT, deliberately not a host allowlist: if
Elastic speeds their registry up the veto re-arms by itself, and any other
registry that degrades into the same state is covered with no code change.

Run:  python3 runbooks/tests/test-tag-oracle-veto-discriminator.py
  or: python3 -m pytest runbooks/tests/test-tag-oracle-veto-discriminator.py -q
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))
_spec = importlib.util.spec_from_file_location(
    "cav_under_test", _REPO / "runbooks" / "check-all-versions.py")
_cav = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cav)

slow = _cav._is_structurally_slow

# (elapsed_s, pages, expected_structural, provenance)
CASES = [
    # --- structural: measured, reproducible, no budget would help -----------
    (72.5, 5, True, "docker.elastic.co/elasticsearch 5 pages, 14.51 s/page"),
    (70.9, 5, True, "docker.elastic.co/kibana 5 pages, 14.19 s/page"),
    (60.0, 6, True, "10.0 s/page"),
    # --- transient: a normal registry that merely ran out of wall clock -----
    (30.0, 194, False, "ghcr.io immich-machine-learning ~194k tags, 0.15 s/page"),
    (4.0, 3, False, "ghcr.io frigate ~20k tags at n=1000"),
    (61.0, 20, False, "large repo at 3.05 s/page — a bigger budget WOULD finish"),
    # --- no completed page: no rate to measure, so err toward vetoing -------
    (61.0, 0, False, "single hung request; indistinguishable from a network fault"),
    (15.0, 0, False, "first request timed out before any page returned"),
]


def main() -> int:
    failures = []
    for elapsed, pages, expected, why in CASES:
        got = slow(elapsed, pages)
        rate = elapsed / max(pages, 1)
        if got != expected:
            failures.append(
                f"{elapsed}s / {pages} pages ({rate:.2f} s/page): "
                f"expected {'STRUCTURAL' if expected else 'TRANSIENT'}, "
                f"got {'STRUCTURAL' if got else 'TRANSIENT'}  [{why}]")
    for msg in failures:
        print(f"FAIL: {msg}")
    print(f"{len(CASES) - len(failures)}/{len(CASES)} assertions passed")
    return 1 if failures else 0


def test_discriminator():
    for elapsed, pages, expected, why in CASES:
        assert slow(elapsed, pages) is expected, why


def test_threshold_sits_between_the_measured_populations():
    """Nothing in the real inventory lands near the threshold."""
    assert 1.33 < _cav._STRUCTURAL_S_PER_PAGE < 14.18


if __name__ == "__main__":
    sys.exit(main())
