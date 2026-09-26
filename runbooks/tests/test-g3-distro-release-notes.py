"""Regression test: G3 reads Alpine + Python release notes (2026-09-26).

1. ALPINE publishes no GitHub releases. Its release notes are news posts that
   usually name SEVERAL branches at once
   (`Alpine-3.21.8-3.22.6-3.23.6-3.24.2-released.html`), so a lookup for one
   version must parse the multi-version slug. Before this fix every
   `library/alpine` bump was "release notes unavailable" and coverage.py
   routed it to an assessed window as unverified (icloud-backup-freshness
   3.24.1 -> 3.24.2).
2. PYTHON publishes no GitHub releases either; the notes are the "What's New
   In Python X.Y" pages, whose "Notable changes in X.Y.N" sections cover the
   patch releases. Every `library/python` minor was held the same way
   (crash-ghost-reaper 3.12 -> 3.14).

Hermetic: the web seam (`VersionChecker._http_get_text`) is a route table.
Every assertion calls the real functions.

Run:  python3 runbooks/tests/test-g3-distro-release-notes.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(REPO / "runbooks"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


cav = _load("cav_distro_under_test", "runbooks/check-all-versions.py")
au = _load("au_distro_under_test", "runbooks/auto-update.py")
cov = _load("cov_distro_under_test", "runbooks/coverage.py")

FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {str(detail)[:300]}"))
    if not ok:
        FAILURES.append(name)


# ── fake web ─────────────────────────────────────────────────────────────────
ALPINE_INDEX = """
<ul>
<li><a href="Alpine-3.21.8-3.22.6-3.23.6-3.24.2-released.html">x</a></li>
<li><a href="Alpine-3.22.5-3.23.5-released.html">x</a></li>
<li><a href="Alpine-3.24.1-released.html">x</a></li>
<li><a href="Alpine-3.24.0-released.html">x</a></li>
<li><a href="Alpine-3.23.2-released.html">x</a></li>
</ul>"""


def _post(title, body):
    return (f"<html><nav>About Downloads</nav><h1>Small. Simple. Secure.</h1>"
            f"<h1>{title}</h1>{body}</html>")


PAGES = {
    "https://alpinelinux.org/posts/": ALPINE_INDEX,
    "https://alpinelinux.org/posts/Alpine-3.21.8-3.22.6-3.23.6-3.24.2-released.html":
        _post("Alpine 3.21.8, 3.22.6, 3.23.6 and 3.24.2 released",
              "<p>These releases fix all known high and medium severity OpenSSL "
              "vulnerabilities, along with other security and bug fixes.</p>"),
    "https://alpinelinux.org/posts/Alpine-3.24.1-released.html":
        _post("Alpine 3.24.1 released", "<p>Bug fix release.</p>"),
    "https://alpinelinux.org/posts/Alpine-3.24.0-released.html":
        _post("Alpine Linux 3.24.0 Released",
              "<h2>Highlights</h2><p>stuff</p>"
              "<h2>Upgrade notes</h2><p>As always, make sure to use apk upgrade "
              "--available when switching between major versions.</p>"),
    "https://docs.python.org/3/whatsnew/3.13.html":
        "<h1>What’s New In Python 3.13<a>¶</a></h1><h2>Removed</h2><p>old modules</p>",
    "https://docs.python.org/3/whatsnew/3.14.html":
        ("<h1>What’s New In Python 3.14<a>¶</a></h1>"
         "<h2>Porting to Python 3.14</h2><p>port</p>"
         "<h2>Notable changes in 3.14.1<a class=\"headerlink\">¶</a></h2>"
         "<h3>os</h3><p>fix one</p>"
         "<h2>Notable changes in 3.14.5<a class=\"headerlink\">¶</a></h2>"
         "<h3>email</h3><p>header folding tightened for five-five-five</p>"),
}


def checker(pages=PAGES):
    ck = cav.VersionChecker.__new__(cav.VersionChecker)
    ck.github_cache = {}
    ck._http_get_text = lambda url, timeout=20: pages.get(url)
    return ck


print("1. Alpine multi-version posts")
ck = checker()
n = ck.fetch_distro_release_notes("docker.io/library/alpine", "3.24.1", "3.24.2")
check("3.24.1 -> 3.24.2 resolves through the MULTI-version slug",
      bool(n) and "3.21.8-3.22.6-3.23.6-3.24.2" in n["source"], n)
check("... and the post body is the notes", bool(n) and "OpenSSL" in n["body"], n)
check("... and a patch post is clean", bool(n) and ck.detect_breaking_changes(n["body"], "minor") == [])
check("... and the site chrome ahead of the title is dropped",
      bool(n) and "Small. Simple" not in n["body"], n and n["body"][:120])
n = ck.fetch_distro_release_notes("alpine", "3.23.6", "3.24.2")
check("3.23.6 -> 3.24.2 reads EVERY post in the range (3.24.0, 3.24.1, 3.24.2)",
      bool(n) and all(s in n["source"] for s in ("3.24.0-released", "3.24.1-released", "3.24.2-released")),
      n and n["source"])
check("... and the 3.24.0 'Upgrade notes' section is a G3 signal (a real hold, with a reason)",
      bool(n) and any("Upgrade" in d for d in ck.detect_breaking_changes(n["body"], "minor")))
check("a target with NO post is UNKNOWABLE (None), never clean",
      ck.fetch_distro_release_notes("alpine", "3.24.2", "3.24.3") is None)
check("a floating 2-component target is not a release (None)",
      ck.fetch_distro_release_notes("alpine", "3.23.6", "3.24") is None)
check("an unreadable index is None",
      checker({}).fetch_distro_release_notes("alpine", "3.24.1", "3.24.2") is None)

print("2. Python What's New")
n = ck.fetch_distro_release_notes("docker.io/library/python", "3.12-alpine", "3.14.7-alpine")
check("3.12 -> 3.14 reads the What's New page of EVERY minor it enters (3.13, 3.14)",
      bool(n) and "whatsnew/3.13.html" in n["source"] and "whatsnew/3.14.html" in n["source"], n)
check("... and the section text is readable (no mojibake heading marks)",
      bool(n) and "Â" not in n["body"] and "# Notable changes in 3.14.5" in n["body"])
n = ck.fetch_distro_release_notes("python", "3.14.4-alpine", "3.14.7-alpine")
check("patch hop 3.14.4 -> 3.14.7 reads the 'Notable changes in 3.14.5' section",
      bool(n) and "five-five-five" in n["body"], n)
check("... cut at its own level: 3.14.1 (outside the range) is excluded",
      bool(n) and "fix one" not in n["body"], n)
n = ck.fetch_distro_release_notes("python", "3.14.5", "3.14.6")
check("patch hop with no notable section resolves and SAYS so",
      bool(n) and "documents no notable change" in n["body"], n)
check("an unreadable page is None",
      checker({}).fetch_distro_release_notes("python", "3.12", "3.14.7") is None)
check("key normalisation: docker.io/library/python:3.12-alpine is a python image",
      cav.VersionChecker.distro_notes_source("docker.io/library/python:3.12-alpine") == "python")
check("... and ghcr.io/foo/python is NOT (only Docker Hub official images)",
      cav.VersionChecker.distro_notes_source("ghcr.io/foo/python") is None)

print("3. auto-update.breaking_signal + coverage wiring")
notes, resolved = au.breaking_signal(ck, "docker.io/library/alpine", "3.24.2", cur_tag="3.24.1")
check("breaking_signal: alpine patch is resolved + clean", resolved and notes == [], (notes, resolved))
notes, resolved = au.breaking_signal(checker({}), "docker.io/library/alpine", "3.24.2", cur_tag="3.24.1")
check("breaking_signal: unreadable notes stay UNRESOLVED (G3 asymmetry kept)",
      not resolved and notes == [], (notes, resolved))
check("distro_range_read true for python, false for a GitHub image",
      au.distro_range_read(ck, "python") and not au.distro_range_read(ck, "o/r"))

cov._auto_update_module = lambda: au
cov._load_checker = lambda: ck
cov._G3_CACHE.clear()
item = {"component": "icloud-backup-freshness", "kind": "image", "current": "3.24.1",
        "target": "3.24.2", "type": "patch", "image_repo": "docker.io/library/alpine"}
is_b, note = cov._direct_bump_breaking_gate(item)
check("coverage G3: alpine 3.24.1 -> 3.24.2 is 'checked', not 'release notes unavailable'",
      not is_b and "checked" in note, note)
item_py = {"component": "crash-ghost-reaper", "kind": "image", "current": "3.12-alpine",
           "target": "3.14.7-alpine", "type": "minor", "image_repo": "docker.io/library/python"}
is_b, note = cov._direct_bump_breaking_gate(item_py)
check("coverage G3: python 3.12 -> 3.14.7 is 'checked'", not is_b and "checked" in note, note)
st, rnote = cov._g3_range_gate(item_py)
check("coverage range gate: a distro image is NOT 'unreadable' across the minor boundary",
      st == "n/a", (st, rnote))

print()
if FAILURES:
    print(f"FAILED {len(FAILURES)}: {FAILURES}")
    sys.exit(1)
print("ALL PASS")
