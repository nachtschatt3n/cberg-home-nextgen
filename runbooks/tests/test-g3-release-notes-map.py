#!/usr/bin/env python3
"""Regression test: G3 reads release notes from the PROJECT that publishes them.

F-d6f1b7c7, measured 2026-09-22 by calling the real functions:

    VersionChecker.get_repo_info_from_image('memgraph/memgraph-mage')
        -> ('memgraph', 'memgraph-mage')          # github.com 404
    VersionChecker.fetch_release_notes('memgraph', 'memgraph-mage', '3.13.1')
        -> None
    coverage.breaking_change_signal('memgraph/memgraph-mage', '3.13.1')
        -> (False, 'unverified (release notes unavailable)')

The gate derives a GitHub project from the IMAGE repository string and there
was no image-repo -> project mapping anywhere for it to consult, so a memgraph
bump could never be verified — and the lane's documented fail-OPEN asymmetry
("unverified does not hold") waved every one through unread. The notes live
in memgraph/memgraph, whose v3.13.x tags are exactly the image tags; after the
fix the same call returns 'clean (release notes checked)' for 3.13.1 and a
positive breaking signal for 3.13.0.

An audit over the repo's whole image universe (116 repos) found 79 in the
same shape. Two root causes and one map:
  * `docker.io/<owner>/<repo>` derived ('docker.io', repo) — the registry host
    was taken as the owner, so EVERY explicit-host Docker Hub pin resolved to
    a nonexistent project (cloudflared, jellyfin, ...). Fixed in the deriver.
  * projects whose name differs from the image (memgraph-mage -> memgraph,
    vaultwarden/server -> dani-garcia/vaultwarden, ...). Seeded into the
    git-tracked IMAGE_RELEASE_NOTES_PROJECTS map, each row only after the tag
    pinned in git resolved to a release body in the named project.

THE ASYMMETRY IS PRESERVED and pinned here: an image that is neither mapped
nor derivable, or whose notes cannot be fetched, is still `unverified` — the
map only lets the gate READ notes it previously could not, it never turns
"unknown" into "verified safe". And the G5 age measure deliberately keeps the
registry-path deriver: a project's release date is not the image's publish
date.

Hermetic: the checker's GitHub fetch is replaced by a recorder; nothing on the
network. Run: python3 runbooks/tests/test-g3-release-notes-map.py
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


cav = _load("cav", "runbooks/check-all-versions.py")
cov = _load("cov", "runbooks/coverage.py")
au = cov._auto_update_module()          # the SAME module object coverage.py uses

FAILURES: list[str] = []
CLEAN_BODY = "## What's Changed\n- Fix a typo in the docs\n"
BREAKING_BODY = "## Breaking changes\n- The config file format changed; migrate before upgrading.\n"


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def counted(population, what: str) -> int:
    """A count that refuses to be zero for a broken instrument."""
    n = len(population)
    if n == 0:
        raise SystemExit(f"ABORT: empty population for {what} — instrument broken, not 'zero'")
    return n


class Recorder:
    """Stands in for VersionChecker.fetch_release_notes: records the project it
    was asked for and answers from a canned table, never the network."""

    def __init__(self, table):
        self.table = table
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, owner, repo, tag):
        self.calls.append((owner, repo, tag))
        body = self.table.get((owner, repo, tag))
        return {"body": body, "prerelease": False, "published_at": ""} if body else None


def fresh_checker(table):
    ck = cav.VersionChecker(str(REPO))
    rec = Recorder(table)
    ck.fetch_release_notes = rec
    cov._CHECKER = ck            # what coverage's _load_checker() hands the engine
    cov._G3_CACHE.clear()
    au._RELEASES_CACHE.clear()
    return ck, rec


def main() -> int:
    print("test-g3-release-notes-map")

    # ── the resolver itself ────────────────────────────────────────────
    ck = cav.VersionChecker(str(REPO))
    check("memgraph-mage maps to the memgraph/memgraph project",
          ck.get_release_notes_project("memgraph/memgraph-mage") == ("memgraph", "memgraph"))
    check("a docker.io/ prefix and a library/ prefix normalise onto the same map key",
          ck.get_release_notes_project("docker.io/memgraph/memgraph-mage") == ("memgraph", "memgraph")
          and ck.get_release_notes_project("index.docker.io/library/memgraph/memgraph-mage")
          == ("memgraph", "memgraph"))
    check("a digest on the repo string does not defeat the lookup",
          ck.get_release_notes_project("memgraph/memgraph-mage@sha256:" + "a" * 64)
          == ("memgraph", "memgraph"))
    check("an UNMAPPED image still derives from the registry path (fallback intact)",
          ck.get_release_notes_project("ghcr.io/foo/bar") == ("foo", "bar"))
    check("an image with no derivation is None, not a guess",
          ck.get_release_notes_project("redis") is None)

    # the second root cause: the registry host was taken as the owner
    check("docker.io/<owner>/<repo> derives (<owner>, <repo>), not ('docker.io', <repo>)",
          ck.get_repo_info_from_image("docker.io/cloudflare/cloudflared") == ("cloudflare", "cloudflared"),
          str(ck.get_repo_info_from_image("docker.io/cloudflare/cloudflared")))
    check("...and the bare owner/repo form is unchanged",
          ck.get_repo_info_from_image("cloudflare/cloudflared") == ("cloudflare", "cloudflared"))
    check("...and ghcr.io derivation is unchanged",
          ck.get_repo_info_from_image("ghcr.io/foo/bar") == ("foo", "bar"))

    # the map is real data, lowercase, and every value is an (owner, repo) pair
    n = counted(cav.IMAGE_RELEASE_NOTES_PROJECTS, "IMAGE_RELEASE_NOTES_PROJECTS")
    check(f"map has {n} entries, all lowercase keys with (owner, repo) values",
          all(k == k.lower() and isinstance(v, tuple) and len(v) == 2 and all(v)
              for k, v in cav.IMAGE_RELEASE_NOTES_PROJECTS.items()))
    check("no map key carries a registry prefix the lookup would strip anyway",
          not any(k.startswith(("docker.io/", "index.docker.io/", "library/"))
                  for k in cav.IMAGE_RELEASE_NOTES_PROJECTS))

    # ── THE defect, through the real gate ──────────────────────────────
    ck, rec = fresh_checker({("memgraph", "memgraph", "3.13.1"): CLEAN_BODY,
                             ("memgraph", "memgraph", "3.13.0"): BREAKING_BODY})
    verdict = cov.breaking_change_signal("memgraph/memgraph-mage", "3.13.1")
    check("breaking_change_signal asks the MAPPED project for memgraph-mage's notes",
          rec.calls and rec.calls[0][:2] == ("memgraph", "memgraph"), str(rec.calls))
    check("...and the 3.13.1 notes read CLEAN (checked), no longer unverified",
          verdict == (False, "clean (release notes checked)"), str(verdict))
    verdict = cov.breaking_change_signal("memgraph/memgraph-mage", "3.13.0")
    check("...and a breaking note in the mapped project HOLDS",
          verdict[0] is True and "breaking-change signal" in verdict[1], str(verdict))

    # ── the asymmetry the docstring promises, still in force ───────────
    ck, rec = fresh_checker({})
    verdict = cov.breaking_change_signal("memgraph/memgraph-mage", "9.9.9")
    check("mapped project but NO fetchable notes -> unverified, does not hold",
          verdict == (False, "unverified (release notes unavailable)"), str(verdict))
    verdict = cov.breaking_change_signal("ghcr.io/nobody/nothing", "1.0.0")
    check("unmapped + unfetchable -> unverified (the map never manufactures 'safe')",
          verdict == (False, "unverified (release notes unavailable)"), str(verdict))
    check("...and the unmapped image was still asked about under its DERIVED project",
          ("nobody", "nothing", "1.0.0") in rec.calls, str(rec.calls))

    # ── wiring: G3 uses the map, G5's age measure does NOT ─────────────
    src = inspect.getsource(au._owner_repo)
    check("auto-update._owner_repo resolves images via get_release_notes_project",
          "get_release_notes_project(" in src)
    age_src = inspect.getsource(au.upstream_release_age_hours)
    check("the G5 age measure keeps the registry-path deriver (a project's release "
          "date is not the image's publish date)",
          "get_repo_info_from_image(" in age_src and "get_release_notes_project(" not in age_src)
    for site in ("get_release_notes_project(img['repository'])",):
        check("check-all-versions' own image release-note lookup uses the map",
              site in inspect.getsource(cav.VersionChecker.check_all))

    # ── COMMISSIONING STRAW: an empty map is the pre-fix world ─────────
    saved = dict(cav.IMAGE_RELEASE_NOTES_PROJECTS)
    try:
        cav.IMAGE_RELEASE_NOTES_PROJECTS.clear()
        ck, rec = fresh_checker({("memgraph", "memgraph", "3.13.1"): CLEAN_BODY})
        straw = cov.breaking_change_signal("memgraph/memgraph-mage", "3.13.1")
        straw_caught = (rec.calls and rec.calls[0][:2] == ("memgraph", "memgraph-mage")
                        and straw == (False, "unverified (release notes unavailable)"))
        check("commissioning: with the map emptied the gate asks the nonexistent "
              "memgraph/memgraph-mage project again and reads unverified — i.e. the "
              "assertions above would FAIL", bool(straw_caught),
              f"calls={rec.calls} verdict={straw}")
    finally:
        cav.IMAGE_RELEASE_NOTES_PROJECTS.clear()
        cav.IMAGE_RELEASE_NOTES_PROJECTS.update(saved)
        cov._CHECKER = None
        cov._G3_CACHE.clear()

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
