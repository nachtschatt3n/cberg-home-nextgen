"""Regression test: G3s scans only the image's own BUILD CONTEXT (2026-09-26).

G3s (auto-update.py structural_signal) scanned the WHOLE source repository
diff. MQTTX builds the `emqx/mqttx-web` image from `web/` (upstream
deploy_web.yaml, `context: ./web`), and a TypeORM migration ADDED under the
Electron DESKTOP tree (`src/database/migration/...`) held the web image, which
has no database. check-all-versions.py IMAGE_BUILD_CONTEXTS now names the
context for monorepo images; unlisted images keep the whole-repo scan.

Hermetic: auto-update.py's GitHub seam (`_gh_api_json`) is a route table.

Run:  python3 runbooks/tests/test-g3s-build-context.py
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


cav = _load("cav_ctx_under_test", "runbooks/check-all-versions.py")
au = _load("au_distro_under_test", "runbooks/auto-update.py")

FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {str(detail)[:300]}"))
    if not ok:
        FAILURES.append(name)


print("G3s scoped to the build context")


class FakeGitHub:
    def __init__(self, routes):
        self.routes = routes

    def __call__(self, path, timeout=15):
        return self.routes.get(path, au._NOT_FOUND)


class Ck:
    def __init__(self, ctx):
        self.ctx = ctx

    def get_release_notes_project(self, dep):
        return ("emqx", "MQTTX")

    def get_chart_repo_info(self, *a, **k):
        return None

    def get_image_build_context(self, dep):
        return self.ctx


DESKTOP_MIGRATION = {"filename": "src/database/migration/1783562195464-koLang.ts",
                     "status": "added", "patch": "+export class KoLang"}
WEB_FILE = {"filename": "web/src/lang/ko.ts", "status": "modified", "patch": "+x"}
ROUTES = {
    "repos/emqx/MQTTX/releases?per_page=100": [{"tag_name": "v1.13.1", "prerelease": False},
                                                {"tag_name": "v1.13.0", "prerelease": False}],
    "repos/emqx/MQTTX/compare/v1.13.0...v1.13.1": {"files": [DESKTOP_MIGRATION, WEB_FILE],
                                                   "total_commits": 32},
}


def struct(ctx, files=None):
    routes = dict(ROUTES)
    if files is not None:
        routes["repos/emqx/MQTTX/compare/v1.13.0...v1.13.1"] = {"files": files, "total_commits": 1}
    au._gh_api_json = FakeGitHub(routes)
    au._STRUCTURAL_CACHE.clear()
    au._RELEASES_CACHE.clear()
    return au.structural_signal(Ck(ctx), "emqx/mqttx-web", "v1.13.1", cur_tag="v1.13.0")


sig, res, note = struct(None)
check("CONTROL: with no build context the desktop migration still HOLDS",
      bool(sig) and "koLang" in sig[0], (sig, note))
sig, res, note = struct("web/")
check("with build context web/ the desktop migration does NOT hold",
      sig == [] and res, (sig, res, note))
check("... and the note says the scan was scoped", "build context web/" in note, note)
sig, res, note = struct("web/", files=[{"filename": "web/migrations/0002_x.sql", "status": "added"}])
check("a migration INSIDE the build context still holds (the gate is not blinded)",
      bool(sig), (sig, note))
check("the live map carries emqx/mqttx-web -> web/ (docker.io spelling too)",
      cav.VersionChecker.get_image_build_context("docker.io/emqx/mqttx-web") == "web/")
check("an unlisted image keeps the whole-repository scan",
      cav.VersionChecker.get_image_build_context("o/r") is None)

print()
if FAILURES:
    print(f"FAILED {len(FAILURES)}: {FAILURES}")
    sys.exit(1)
print("ALL PASS")
