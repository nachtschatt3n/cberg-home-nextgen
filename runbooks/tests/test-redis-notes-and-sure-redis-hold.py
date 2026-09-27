"""Regression tests for two fixes from the redis fleet planner (plan
redis-fleet-8.10.2, 2026-09-27):

  1. G3 could never read notes for `redis:*-alpine`: no image->project mapping
     and a `-alpine` flavour suffix the GitHub release tag does not carry. Every
     redis bump was "release notes unavailable" by construction. Now
     IMAGE_RELEASE_NOTES_PROJECTS maps `redis -> redis/redis` and
     IMAGE_TAG_FLAVOUR_SUFFIXES strips the suffix for the TARGET read.
  2. sure-redis must never move unattended: sidekiq-cron registers sure's cron
     jobs only at worker start, so a redis roll can silently empty the schedule
     (`cron_jobs:default`, 11 members). The Renovate depName is the SHARED
     `redis`, so a depName glob cannot see it: the deny rule carries `paths:`
     and the PR lane holds a PR changing that file. The direct-bump lane holds
     the component key.

Hermetic: no network, no gh.

Run:  python3 runbooks/tests/test-redis-notes-and-sure-redis-hold.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
os.environ.pop("SWEEP_PG_DSN", None)
sys.path.insert(0, str(_REPO / "runbooks"))


def _load(name, rel):
    s = importlib.util.spec_from_file_location(name, _REPO / rel)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


cav = _load("cav", "runbooks/check-all-versions.py")
au = _load("au", "runbooks/auto-update.py")
cov = _load("cov", "runbooks/coverage.py")
POLICY = au.load_policy()
FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


class FakeChecker:
    def __init__(self):
        self.asked = []

    def get_release_notes_project(self, dep):
        return cav.VersionChecker.get_release_notes_project(self, dep)

    def get_repo_info_from_image(self, dep):
        return None

    def get_chart_repo_info(self, *a):
        return None

    _DOCKERHUB_HOSTS = ("docker.io", "index.docker.io", "registry-1.docker.io")

    def distro_notes_source(self, dep):
        return None

    def fetch_release_notes(self, owner, repo, tag):
        self.asked.append((owner, repo, tag))
        if (owner, repo, tag) == ("redis", "redis", "8.10.2"):
            return {"body": "Bug fixes. Security fixes.", "published_at": "2026-09-17T15:06:56Z"}
        return None

    def detect_breaking_changes(self, body, _t):
        return ["BREAKING"] if "BREAKING" in body else []


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print("\nredis release notes:")
    check("redis maps to the redis/redis project",
          cav.IMAGE_RELEASE_NOTES_PROJECTS.get("redis") == ("redis", "redis"))
    for ref in ("redis", "docker.io/library/redis", "library/redis"):
        check(f"{ref}: 8.10.2-alpine -> release tag 8.10.2",
              cav.release_tag_for(ref, "8.10.2-alpine") == "8.10.2")
    check("an UNLISTED image keeps its suffix (no guessing)",
          cav.release_tag_for("example-org/app", "1.2.3-alpine") == "1.2.3-alpine")
    check("a redis tag with no listed suffix is unchanged",
          cav.release_tag_for("redis", "8.10.2") == "8.10.2")
    fc = FakeChecker()
    au._RELEASES_CACHE["redis"] = []          # release list read, nothing in between
    notes, resolved = au.breaking_signal(fc, "redis", "8.10.2-alpine", cur_tag="8.10.1-alpine")
    check("G3 reads the TARGET notes at the stripped tag and resolves",
          resolved and ("redis", "redis", "8.10.2") in fc.asked, repr((resolved, fc.asked)))
    check("...clean notes => no breaking signal", notes == [], repr(notes))
    fc2 = FakeChecker()
    fc2.fetch_release_notes = lambda o, r, t: ({"body": "BREAKING: x"} if t == "8.10.2" else None)
    notes, _ = au.breaking_signal(fc2, "redis", "8.10.2-alpine", cur_tag="8.10.1-alpine")
    check("a breaking note at the stripped tag is attributed to the TARGET (not a skipped release)",
          notes == ["BREAKING"], repr(notes))

    print("\nsure-redis hold:")
    rule = next((r for r in POLICY.get("deny", []) if r.get("match") == "*sure-redis*"), None)
    check("LIVE policy has a *sure-redis* rule with no max (blanket hold)",
          rule is not None and rule.get("max") is None)
    check("...naming the worker restart and the cron_jobs:default key (not cron_jobs)",
          rule and "sure-worker" in rule["reason"] and "cron_jobs:default" in rule["reason"])
    check("...and a paths: entry for the sure redis HelmRelease",
          rule and "kubernetes/apps/office/sure/app/redis-helmrelease.yaml" in rule.get("paths", []))
    check("the file the rule names exists",
          (_REPO / "kubernetes/apps/office/sure/app/redis-helmrelease.yaml").exists())
    check("depName-level: a shared `redis` PR is NOT blocked by name alone",
          au.policy_block(POLICY, "redis", "patch") is None)
    hold = au.path_block(POLICY, ["kubernetes/apps/office/paperless/app/helmrelease.yaml",
                                  "kubernetes/apps/office/sure/app/redis-helmrelease.yaml"])
    check("PR lane: a redis PR that CHANGES the sure redis file is held", bool(hold), repr(hold))
    check("PR lane: a redis PR that does not touch it passes the path rule",
          au.path_block(POLICY, ["kubernetes/apps/office/paperless/app/helmrelease.yaml"]) is None)
    check("PR lane: an unreadable file list HOLDS (fail-safe)",
          bool(au.path_block(POLICY, None)))
    check("control: a policy with no path rules never fetches or holds",
          au.path_block({"deny": [{"match": "*x*"}]}, None) is None)
    item = {"component": "sure-redis", "kind": "image", "current": "8.10.1-alpine",
            "target": "8.10.2-alpine", "type": "patch", "image_repo": "redis"}
    check("direct-bump lane: the sure-redis COMPONENT is denied",
          bool(cov.denied_for_item(POLICY, item, "sure-redis", "patch")))
    other = {**item, "component": "paperless-redis"}
    check("direct-bump lane: another redis consumer is NOT held by this rule",
          not cov.denied_for_item(POLICY, other, "paperless-redis", "patch"))

    print()
    print("FAILED: " + ", ".join(FAILURES) if FAILURES else "all tests passed")
    return 1 if FAILURES else 0


def test_pytest_entry():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
