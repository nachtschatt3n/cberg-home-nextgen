"""Regression test: a FLOATING tag must be compared against upstream's newest
RELEASE, not against itself (F-b2c35615, 2026-10-03).

Before this fix both audits ended the question at `is_rolling_tag()`:
check-all-versions.py printed "rolling tag — skipped" and security-check.py's
`_newer_upstream_tag_lookup()` returned False ("as current as the tag allows"),
the already-newest answer. Live case: `mandarons/icloud-drive:main@sha256:91486ec1…`
(built 2026-06-06) read as already-newest while upstream had shipped v1.26.0,
v2.0.0 and v2.1.0.

BOTH-WAYS. The fix must surface a floating pin that is behind a release AND
must not invent updates for:
  * a plain semver pin                       (assess -> None, old path)
  * a digest-pinned semver pin               (assess -> None, old path)
  * a floating tag with NO semver releases   (no-release -> old False)
  * a floating tag that IS the newest release (digest equal -> False)
  * a floating tag built AFTER the newest release (ahead -> False)
  * git-sha pins (self-built, no release line) — out of scope, old path
and an uncomparable case must be surfaced (None), never accepted (False).

Hermetic: registry calls are stubbed on a real VersionChecker.

Run:  python3 runbooks/tests/test-floating-tag-vs-release.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(_REPO / "runbooks"))

_cspec = importlib.util.spec_from_file_location(
    "cav_floating_under_test", _REPO / "runbooks" / "check-all-versions.py")
_cav = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(_cav)

_sspec = importlib.util.spec_from_file_location(
    "sec_floating_under_test", _REPO / "runbooks" / "security-check.py")
_sec = importlib.util.module_from_spec(_sspec)
_sspec.loader.exec_module(_sec)

FAILURES: list[str] = []
D_RUN = "sha256:" + "a" * 64
D_REL = "sha256:" + "b" * 64


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def make_vc(release, refs):
    """VersionChecker with the registry stubbed.

    release: what get_latest_image_tag returns for ANY query.
    refs:    {ref: (digest, created)} for _ref_digest_and_created.
    """
    vc = _cav.VersionChecker(str(_REPO))
    calls = []

    def _latest(repo, current_tag=""):
        calls.append(("latest", repo, current_tag))
        return release

    def _ref(repo, ref, timeout=15):
        calls.append(("ref", repo, ref))
        return refs.get(ref, (None, None))

    vc.get_latest_image_tag = _latest
    vc._ref_digest_and_created = _ref
    vc._calls = calls
    return vc


def sec_verdict(vc, image_ref):
    _sec._VER_CHECKER = vc
    return _sec._newer_upstream_tag_lookup(image_ref)


# ── 1. plain semver pin: untouched old path ─────────────────────────────────
vc = make_vc("2.1.0", {})
check("semver pin: assess returns None", vc.assess_floating_tag("x/y", "2.1.0") is None)
check("semver pin: not rolling", not vc.is_rolling_tag("2.1.0"))
check("semver pin: no registry call from assess",
      not [c for c in vc._calls if c[0] == "ref"], str(vc._calls))

# ── 2. digest-pinned semver pin: untouched old path ─────────────────────────
t = f"2.1.0@{D_RUN}"
check("digest-pinned semver: assess returns None", vc.assess_floating_tag("x/y", t) is None)
check("digest-pinned semver: not rolling", not vc.is_rolling_tag(t))

# ── 3. floating, digest-pinned, BEHIND newest release (the icloud-drive case) ─
vc = make_vc("2.1.0", {
    "2.1.0": (D_REL, "2026-10-01T05:55:15Z"),
    D_RUN:   (D_RUN, "2026-06-06T02:50:52Z"),
})
a = vc.assess_floating_tag("mandarons/icloud-drive", f"main@{D_RUN}")
check("floating behind: state behind-release", a and a["state"] == "behind-release", str(a))
check("floating behind: names release 2.1.0", a and a["newest_release"] == "2.1.0", str(a))
check("floating behind: running digest is the PIN, not the live tag",
      ("ref", "mandarons/icloud-drive", D_RUN) in vc._calls, str(vc._calls))
check("floating behind: release looked up with the floating NAME (plain variant line)",
      ("latest", "mandarons/icloud-drive", "main") in vc._calls, str(vc._calls))
check("floating behind: security says a newer tag exists (not already-newest)",
      sec_verdict(vc, f"mandarons/icloud-drive:main@{D_RUN}") is True)

# ── 4. floating with NO semver releases ─────────────────────────────────────
vc = make_vc(None, {})
a = vc.assess_floating_tag("ghcr.io/o/pipelines", f"main@{D_RUN}")
check("no releases: state no-release", a and a["state"] == "no-release", str(a))
check("no releases: security keeps old False", sec_verdict(vc, f"ghcr.io/o/pipelines:main@{D_RUN}") is False)
# a non-semver answer from the resolver is not a release either
vc = make_vc("nightly-2026", {})
a = vc.assess_floating_tag("x/y", "latest")
check("non-semver resolver answer: no-release", a and a["state"] == "no-release", str(a))

# ── 5. floating that IS the newest release (digest equal) ───────────────────
vc = make_vc("1.38.0", {
    "1.38.0": (D_REL, "2026-05-13T02:21:49Z"),
    "stable": (D_REL, "2026-05-13T02:21:49Z"),
})
a = vc.assess_floating_tag("busybox", "stable")
check("at release: state at-release", a and a["state"] == "at-release", str(a))
check("at release: security False (already newest)", sec_verdict(vc, "busybox:stable") is False)

# ── 6. floating built AFTER the newest release (dev branch ahead) ───────────
vc = make_vc("1.0.0", {
    "1.0.0": (D_REL, "2021-01-01T00:00:00Z"),
    "latest": (D_RUN, "2026-09-01T00:00:00Z"),
})
a = vc.assess_floating_tag("x/y", "latest")
check("ahead: state ahead-of-release", a and a["state"] == "ahead-of-release", str(a))
check("ahead: security False (no release to move to)", sec_verdict(vc, "x/y:latest") is False)

# ── 7. release exists but nothing comparable: surface, never accept ─────────
vc = make_vc("2.0.0", {})
a = vc.assess_floating_tag("x/y", f"edge@{D_RUN}")
check("uncomparable: state unverified", a and a["state"] == "unverified", str(a))
check("uncomparable: security None (surface)", sec_verdict(vc, f"x/y:edge@{D_RUN}") is None)
# equal build dates order nothing either
vc = make_vc("2.0.0", {"2.0.0": (D_REL, "2026-01-01T00:00:00Z"),
                        D_RUN: (D_RUN, "2026-01-01T00:00:00Z")})
a = vc.assess_floating_tag("x/y", f"main@{D_RUN}")
check("equal dates, different digests: unverified", a and a["state"] == "unverified", str(a))

# ── 8. scope stays narrow ───────────────────────────────────────────────────
vc = make_vc("9.9.9", {})
for t in ("sha-8b38e12", "8b38e12f", "latest-alpine", "18", "lts-alpine"):
    check(f"not a named floating tag: {t}", vc.floating_tag_parts(t) is None)
check("floating_tag_parts parses digest", vc.floating_tag_parts(f"LATEST@{D_RUN}") == ("latest", D_RUN))
check("git-sha pin: security old False, no release lookup",
      sec_verdict(vc, "ghcr.io/o/app:sha-8b38e12") is False
      and not [c for c in vc._calls if c[0] == "latest"], str(vc._calls))

# ── 9. epoch-stamped (reproducible) build dates are not dates ───────────────
check("bogus epoch created rejected", bool(_cav.VersionChecker._BOGUS_CREATED_RE.match("1970-01-01T00:00:00Z")))
check("real created accepted", not _cav.VersionChecker._BOGUS_CREATED_RE.match("2026-06-06T02:50:52Z"))

# ── 10. finding emission: warning for behind, never a lane-shaped bump ──────
class FakeWriter:
    enabled = True

    def __init__(self):
        self.rows = []

    def emit(self, **kw):
        self.rows.append(kw)


class FakeChecker:
    unresolved_chart_sources = []
    unresolved_rendered_images = []
    external_infra_results = []

    def __init__(self, fa):
        self.results = [{
            "name": "icloud-docker-mu", "namespace": "backup",
            "chart": {"current_version": "5.1.0", "latest_version": "5.1.0"},
            "images": [{"repository": "mandarons/icloud-drive",
                        "current_tag": f"main@{D_RUN}", "latest_tag": None,
                        "path": "x", "rolling": True, "floating": fa}],
        }]


_cav.load_update_policy = lambda: None
for state, sev in (("behind-release", "warning"), ("unverified", "monitor")):
    w = FakeWriter()
    fa = {"floating_name": "main", "pinned_digest": D_RUN, "newest_release": "2.1.0",
          "state": state, "running_created": "2026-06-06", "release_created": "2026-10-01"}
    try:
        _cav._emit_findings(w, FakeChecker(fa), "evidence.md")
    except Exception as e:  # pragma: no cover - surfaced as a failure
        check(f"emit {state}: no exception", False, repr(e))
        continue
    rows = [r for r in w.rows if "icloud-drive" in r["title"]]
    check(f"emit {state}: exactly one row", len(rows) == 1, str(w.rows))
    if rows:
        check(f"emit {state}: severity {sev}", rows[0]["severity"] == sev, rows[0]["severity"])
        check(f"emit {state}: type=floating, not a minor/patch lane shape",
              rows[0]["metadata"].get("type") == "floating"
              and "(minor)" not in rows[0]["title"] and "(patch)" not in rows[0]["title"],
              rows[0]["title"])
for state in ("at-release", "ahead-of-release", "no-release"):
    w = FakeWriter()
    fa = {"floating_name": "main", "pinned_digest": D_RUN,
          "newest_release": None if state == "no-release" else "2.1.0", "state": state}
    _cav._emit_findings(w, FakeChecker(fa), "evidence.md")
    check(f"emit {state}: no row", not [r for r in w.rows if "icloud-drive" in r["title"]],
          str(w.rows))

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s)")
    sys.exit(1)
print("all checks passed")
