#!/usr/bin/env python3
"""auto-update — merge SAFE Renovate PRs at Step 0 of a maintenance window.

The maintenance-window-agent calls this to keep the cluster current
WITHOUT the operator hand-merging every patch/minor bump. It is a strict,
deny-by-default classifier: an open Renovate PR is merged only when every
gate passes, and only ever on the scheduled run.

Gates (all must pass) — see runbooks/auto-update-policy.yaml:
  G1 type     : update_type in {patch, minor}  (major/digest/unknown → hold)
  G2 policy   : depName not blocked by a deny rule (operator knowledge that a
                component is risky regardless of semver — e.g. affine, mariadb)
  G3 breaking : NO breaking-change signal in the PR's target release notes.
                Reuses check-all-versions.py's fetch_release_notes +
                detect_breaking_changes, so a "patch-but-breaking" bump
                (affine 0.27.3 env→config.json) is caught even if a human
                forgot to deny-list it.
  G3s struct  : NO migration/schema signal in the DIFF between the current
                and target tags (F-ea1000ff). G3 reads release-note PROSE, so
                it holds when upstream writes "breaking" and passes when
                upstream does not; this companion reads the compare API for
                files ADDED under a migrations directory and for a bumped
                SCHEMA_VERSION-style constant. Same asymmetry as G3: a
                positive signal holds, an unreadable diff is reported.
  G5 age      : the TARGET RELEASE is at least `minimum_release_age_hours`
                old (policy; operator set 48h). Supply-chain cooldown:
                poisoned releases are usually yanked within days, so an
                unattended merge WAITS unless the bump is security-driven
                (CVE fixes merge at age 0 — a known-bad current version
                outranks an unknown-new one).
                Measured from the UPSTREAM release timestamp of the target
                version (GitHub release published_at, else the registry tag
                publish date). Until 2026-09-04 it was measured from the
                PR's newest Renovate commit — but fast-shipping upstreams
                (n8n releases every ~1-2 days) force-push the PR on every
                retarget, resetting that clock: PR #210 starved 9 days
                without ever being "48h old". The cooldown defends against
                a poisoned RELEASE, so the release's own age is the honest
                measure; a retarget still restarts the clock because the
                NEW target release is itself young. When the upstream date
                cannot be determined we FALL BACK to the PR's newest commit
                (the stricter measure — fail-closed) and say so in the log.
                Unknown age on both measures HOLDS — a cooldown that cannot
                be proven has not elapsed.
  G4 ci       : PR mergeable + EVERY check in the PR's rollup green. No
                check is required BY NAME and none is ignored by name. The
                render check is the "Flate Render Gate" job of
                .github/workflows/flux-local.yaml (flate renders every
                HelmRelease/Kustomization on each PR; the EOL flux-local test
                job was retired 2026-09-23, F-6b1dd22b), so a green rollup
                means the manifest actually renders. A check run already on
                a PR's head SHA outlives the job that produced it, so a
                retired-and-red check keeps holding that PR until a fresh run
                (reopen/rebase) — the hold reason names that case.

APPLY GUARD — merges + git ops run ONLY when BOTH hold:
  * --apply is passed, AND
  * SWEEP_TRIGGER=cron  (or AUTO_UPDATE_APPLY=1 for an explicit operator run).
Otherwise this is a dry-run that only prints the classification. That keeps a
manual `operation sweep` read-only, matching the sweep contract.

After the safe batch merges: git pull → flux reconcile the affected
kustomizations → POST-APPLY HEALTH GATE. If Flux fails to reconcile or a
workload in an affected namespace regresses, the batch is auto-reverted
(git revert + push) and a critical finding + alert is raised.

Usage:
    python3 runbooks/auto-update.py                 # dry-run report (default)
    python3 runbooks/auto-update.py --apply         # apply (needs cron trigger)
    AUTO_UPDATE_APPLY=1 python3 runbooks/auto-update.py --apply   # force apply
    python3 runbooks/auto-update.py --json           # machine-readable report

Exit codes: 0 = ok (nothing to do, or applied + healthy), 2 = applied then
reverted (a merge regressed and was rolled back), 1 = hard error.
"""
from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
POLICY_PATH = SCRIPT_DIR / "auto-update-policy.yaml"
RANK = {"patch": 0, "minor": 1, "major": 2}
SAFE_TYPES = {"patch", "minor"}
RECONCILE_WAIT_S = int(os.environ.get("AUTO_UPDATE_RECONCILE_WAIT", "150"))


# The REAL stdout, captured before --json mode reroutes sys.stdout. Only the
# machine-readable payload is ever written here.
_JSON_OUT = sys.stdout


def log(*a):
    # progress → stderr, so stdout stays pure JSON under --json (the sweep
    # orchestrator parses stdout).
    print(*a, flush=True, file=sys.stderr)


def emit_json(result) -> None:
    """Write the ONLY thing --json mode may put on stdout.

    `log()` alone was not enough to keep that promise: FindingsWriter prints its
    auto-close/incomplete diagnostics (`==> …`) with a plain `print`, and in the
    sweep — the one context that parses this — SWEEP_PG_DSN is set, so those
    lines land on stdout AHEAD of the payload. maintenance-plan.py's `get_held()`
    then failed `json.loads` on every single run and silently reported
    `0 held update(s)` forever. Fixing the contract at the source beats teaching
    each caller to strip banners: any future library print is caught too.
    """
    print(json.dumps(result, indent=2), file=_JSON_OUT, flush=True)


def run(cmd, timeout=60, check=False):
    """Thin subprocess wrapper returning (rc, stdout, stderr)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if check and p.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd)} -> rc={p.returncode}: {p.stderr.strip()}")
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


# ── load check-all-versions' breaking-change engine (hyphenated filename) ────
def _load_version_checker():
    spec = importlib.util.spec_from_file_location(
        "check_all_versions", SCRIPT_DIR / "check-all-versions.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    return mod.VersionChecker(str(REPO_ROOT), github_token=token)


# ── policy ───────────────────────────────────────────────────────────────────
def load_policy():
    """Return policy dict. Fail-safe: unreadable policy → deny everything."""
    if not POLICY_PATH.exists():
        log(f"!! policy file missing ({POLICY_PATH}); denying ALL as a safe default")
        return {"_deny_all": True, "deny": [], "deny_managers": []}
    try:
        return yaml.safe_load(POLICY_PATH.read_text()) or {}
    except Exception as e:
        log(f"!! policy file unparseable ({e}); denying ALL as a safe default")
        return {"_deny_all": True, "deny": [], "deny_managers": []}


def _match_anywhere(dep, pat):
    """Deny globs match ANYWHERE in the dep path, so `siderolabs/*` still blocks
    `ghcr.io/siderolabs/installer` despite the registry prefix. Over-matching is
    the safe direction for a deny-list — it only sends more PRs to human review,
    never lets an unwanted one merge."""
    return any(fnmatch.fnmatch(dep, g) for g in (pat, f"*{pat}", f"{pat}*", f"*{pat}*"))


def policy_block(policy, dep, update_type):
    """Return a reason string if a deny rule blocks (dep, update_type), else None."""
    if policy.get("_deny_all"):
        return "policy unavailable — deny-all fail-safe"
    for rule in policy.get("deny", []) or []:
        pat = rule.get("match", "")
        if not pat or not _match_anywhere(dep, pat):
            continue
        mx = rule.get("max")
        if mx is None:
            return rule.get("reason", f"blocked by deny rule {pat!r}")
        # rule allows up to `mx`; block only if this update exceeds it
        if RANK.get(update_type, 99) > RANK.get(mx, -1):
            return f"{rule.get('reason','')} (allows ≤{mx}, this is {update_type})"
        # Matched and permitted => decisive ALLOW; stop scanning. The first
        # matching rule decides (2026-09-12). Kept in lockstep with
        # coverage.py::deny_rule_for, whose docstring carries the reasoning.
        return None
    return None


# ── PR discovery + parse ─────────────────────────────────────────────────────
def list_renovate_prs():
    rc, out, err = run([
        "gh", "pr", "list", "--author", "app/renovate", "--state", "open",
        "--json", "number,title,labels,isDraft,mergeable,mergeStateStatus,url,headRefName",
        "--limit", "100",
    ], timeout=45)
    if rc != 0:
        raise RuntimeError(f"gh pr list failed: {err.strip()}")
    return json.loads(out or "[]")


# Renovate emits two title shapes in this repo, both of which must be
# attributable to exactly ONE component and ONE full target version.
#
#  (A) SPANNED — `.github/renovate.json5` sets a custom `commitMessageExtra`
#      of "( {{currentVersion}} → {{newVersion}} )" for the docker/helm/
#      github-release packageRules. Example:
#          feat(container): update postgres ( 17.9 → 17.11 )
#
#  (B) BARE — any dep NOT covered by one of those packageRules falls back to
#      Renovate's DEFAULT commitMessageExtra, which renders
#      "to {{newValue}}" (or "to v{{newMajor}}" for a major). Example:
#          feat(container): update busybox to v1.38.0
#      PR #205 was a genuine, green, version-only patch bump that got held
#      purely because shape (B) has no "( x → y )" span. The current version
#      is simply not in the title for this shape — that is a Renovate
#      rendering fact, not a signal that the bump is unattributable.
#
# SAFETY (memory: feedback_version_attribution — never bump from an unlabeled
# version line). Shape (B) is only accepted when BOTH hold:
#   1. the dep is a SINGLE token (no spaces) — so a grouped title such as
#      "update Flux Operator group to v1.2.3" can never match, and
#   2. the target is a FULL version with at least one dot ("1.38.0", "v1.38"),
#      never a bare major ("v2"). Renovate renders majors as "to v<major>",
#      which names no concrete target — exactly the unattributable case, and
#      majors are held by the update_type gate anyway.
# `cur` is therefore UNKNOWN for shape (B); it is reported as such rather
# than guessed, and nothing downstream gates on it (the safe/unsafe decision
# comes from the PR's update-type LABEL, not from diffing cur→new).
_TITLE_RE = re.compile(
    r"update\s+(?P<dep>.+?)\s+\(\s*(?P<cur>\S+)\s*(?:→|->|to)\s*(?P<new>\S+)\s*\)"
)
_TITLE_BARE_RE = re.compile(
    r"update\s+(?P<dep>\S+)\s+to\s+(?P<new>v?\d+(?:\.\d+)+[\w.+-]*)\s*$"
)


def parse_pr(pr):
    """Extract dep/cur/new + update_type. Returns dict or {'parse_error':...}."""
    title = pr.get("title", "")
    labels = [l["name"].lower() for l in pr.get("labels", [])]

    def has(k):
        return k in labels or f"type/{k}" in labels

    if has("major"):
        utype = "major"
    elif has("minor"):
        utype = "minor"
    elif has("patch"):
        utype = "patch"
    elif has("security"):
        utype = "security"
    else:
        utype = "unknown"

    m = _TITLE_RE.search(title)
    cur = None
    if m:
        dep, cur, new = m.group("dep").strip(), m.group("cur"), m.group("new")
    else:
        m = _TITLE_BARE_RE.search(title)
        if not m:
            return {"parse_error": (
                "title not in `update <dep> ( x → y )` nor "
                "`update <dep> to <x.y.z>` shape"
            )}
        dep, new = m.group("dep").strip(), m.group("new")
    # grouped PRs update several deps ("... group") — never auto-merge blind
    if " group" in dep or "," in dep or "and " in dep:
        return {"parse_error": f"grouped/multi-dep PR ({dep!r}) — manual"}
    return {
        "dep": dep,
        # None (not "") when Renovate did not render the current version, so
        # the report shows "?" instead of implying a known 0-length version.
        "cur": cur if cur is not None else "?",
        "cur_known": cur is not None,
        "new": new,
        "update_type": utype,
    }


# ── G3 breaking-change scan (best-effort, reuses version engine) ─────────────
def _owner_repo(checker, dep):
    """(owner, repo) on GitHub for a dep, or None. Image first, then chart.

    Images go through the checker's RELEASE-NOTES resolver, which consults the
    git-tracked IMAGE_RELEASE_NOTES_PROJECTS map before deriving a project
    from the registry path (F-d6f1b7c7: `memgraph/memgraph-mage` derives a
    project that does not exist; its notes live in memgraph/memgraph). This
    is G3's resolver and the release-range walk's; G5's age measure keeps its
    own (registry-dated) path on purpose.
    """
    try:
        owner_repo = None
        if "/" in dep and (dep.count("/") >= 1 and any(c in dep for c in ".:")) or "/" in dep:
            owner_repo = checker.get_release_notes_project(dep)
        if not owner_repo:
            owner_repo = checker.get_chart_repo_info(dep.split("/")[-1], "", "")
        return owner_repo
    except Exception:
        return None


def _vt(tag):
    """(a, b, c, ...) numeric tuple for a tag, or None. `v` and any
    `-suffix`/`+build` are dropped, exactly like the version report does."""
    t = str(tag or "").lstrip("vV").split("-")[0].split("+")[0].split("@")[0]
    nums = [int(x) for x in re.findall(r"\d+", t)]
    return tuple(nums) if nums else None


def _cmp_pad(a, b):
    n = max(len(a), len(b), 3)
    return a + (0,) * (n - len(a)), b + (0,) * (n - len(b))


_RELEASES_CACHE: dict = {}

# Definitive HTTP 404 from GitHub, as distinct from "unknowable". A missing
# repository, tag or compare range is a fact the caller can act on (skip the
# next spelling, stop probing); an auth wall, a rate limit or a network
# failure is not. Callers that do not care treat it like None.
_NOT_FOUND = object()


def _gh_api_json(path: str, timeout: int = 15):
    """Parsed JSON for a GitHub REST `path` (`repos/o/r/...`), `_NOT_FOUND`
    for a definitive HTTP 404, or None when UNKNOWABLE.

    `gh api` first (authenticated, no anonymous rate limit), then a direct
    request with GITHUB_TOKEN/GH_TOKEN when set. A 404 from `gh` is returned
    as `_NOT_FOUND` WITHOUT the direct retry: the retry used to run anonymously
    against the same missing URL, spending the 60/hour bucket on an answer
    already known. ONE seam for every GitHub read in this file (releases,
    compare, trees, contents), so a test fakes all of them in one place and
    no lane can disagree with another about what GitHub said.
    """
    data = None
    try:
        p = subprocess.run(["gh", "api", "-X", "GET", path],
                           capture_output=True, text=True, timeout=timeout)
        if p.returncode == 0:
            data = json.loads(p.stdout)
        elif "HTTP 404" in (p.stderr or ""):
            return _NOT_FOUND
    except Exception:
        data = None
    if data is None:
        try:
            import urllib.error
            import urllib.request
            hdrs = {"User-Agent": "cberg-auto-update",
                    "Accept": "application/vnd.github+json"}
            tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
            if tok:
                hdrs["Authorization"] = f"Bearer {tok}"
            req = urllib.request.Request(f"https://api.github.com/{path}", headers=hdrs)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = json.loads(r.read())
            except urllib.error.HTTPError as e:
                return _NOT_FOUND if e.code == 404 else None
        except Exception:
            return None
    return data


def github_releases(checker, dep, timeout: int = 15):
    """[(tag, is_prerelease)] newest-first for `dep`'s GitHub repo, or None.

    None means UNKNOWABLE (no repo mapping, no `gh`, API error) — callers must
    not read it as "no releases".
    """
    key = str(dep)
    if key in _RELEASES_CACHE:
        return _RELEASES_CACHE[key]
    _RELEASES_CACHE[key] = None
    owner_repo = _owner_repo(checker, dep)
    if not owner_repo:
        return None
    owner, repo = owner_repo
    path = f"repos/{owner}/{repo}/releases?per_page=100"
    data = _gh_api_json(path, timeout)
    if data is _NOT_FOUND or not isinstance(data, list):
        return None
    out = [(str(d.get("tag_name") or ""), bool(d.get("prerelease")))
           for d in data if d.get("tag_name")]
    _RELEASES_CACHE[key] = out
    return out


def release_tags_between(checker, dep, cur_tag, new_tag, timeout: int = 15):
    """(tags_strictly_between, note) — the releases a hop LEAPFROGS, or (None, why).

    F-51728488: G3 read the TARGET tag's notes alone, so a breaking change
    announced in a release we skip over was never evaluated. Live instance:
    paperless-ngx 3.1.3 -> 3.2.1 skips 3.2.0, whose notes carry "update
    ng-select to v24, handle breaking changes" — the gate read as a
    breaking-change check while being a breaking-change check for exactly one
    version. Pre-releases are excluded: they are not on the upgrade path.

    `None` is UNKNOWABLE and must never be read as "nothing was skipped".
    """
    a, b = _vt(cur_tag), _vt(new_tag)
    if not a or not b:
        return None, f"unparseable version pair ({cur_tag} -> {new_tag})"
    a, b = _cmp_pad(a, b)
    rels = github_releases(checker, dep, timeout)
    if rels is None:
        return None, f"release list for {dep} unreadable"
    n = max(len(a), len(b), 3)

    def pad(t):
        return tuple(t) + (0,) * (n - len(t)) if len(t) < n else tuple(t)

    lo, hi = pad(a), pad(b)
    between = []
    for tag, pre in rels:
        if pre:
            continue
        t = _vt(tag)
        if not t:
            continue
        tp = pad(t)
        if lo < tp < hi:
            between.append(tag)
    ordered = sorted(set(between), key=lambda x: pad(_vt(x) or (0,)))
    return ordered, (f"{len(ordered)} intermediate release(s) read between "
                     f"{cur_tag} and {new_tag}")


def breaking_signal(checker, dep, new_tag, cur_tag=None):
    """Return (list_of_breaking_notes, resolved_bool). Empty list + resolved=True
    means 'checked, clean'. resolved=False means notes couldn't be fetched.

    When `cur_tag` is supplied the scan covers the whole RANGE cur..new, not
    the target tag alone (F-51728488) — a breaking change announced in a
    release the hop leapfrogs is exactly as breaking as one in the target.
    An unreadable release LIST degrades to the single-tag scan and says so via
    resolved=False, preserving this gate's documented asymmetry.

    Images whose notes are NOT GitHub releases (alpine, python — see
    check-all-versions.py DISTRO_RELEASE_NOTES) are read from their
    first-party source instead, over the same cur..new range. Without this
    every such bump was "release notes unavailable" by construction.
    """
    distro = _distro_source(checker, dep)
    if distro:
        return _distro_breaking_signal(checker, dep, new_tag, cur_tag)
    owner_repo = _owner_repo(checker, dep)
    if not owner_repo:
        return [], False
    owner, repo = owner_repo
    tags, resolved_range = [new_tag], True
    if cur_tag and str(cur_tag) not in ("", "?"):
        between, _why = release_tags_between(checker, dep, cur_tag, new_tag)
        if between is None:
            resolved_range = False
        else:
            tags = between + [new_tag]
    found, any_resolved = [], False
    for tag in tags:
        try:
            notes = checker.fetch_release_notes(owner, repo, tag)
            if not notes or not notes.get("body"):
                continue
            any_resolved = True
            for d in checker.detect_breaking_changes(notes["body"], "minor") or []:
                found.append(d if tag == new_tag else f"[skipped release {tag}] {d}")
        except Exception:
            continue
    return found, bool(any_resolved and resolved_range)


def _distro_source(checker, dep):
    """'alpine'/'python' when `dep` reads its notes from a non-GitHub source."""
    try:
        fn = getattr(checker, "distro_notes_source", None)
        return fn(dep) if fn else None
    except Exception:
        return None


def _distro_breaking_signal(checker, dep, new_tag, cur_tag=None):
    """G3 for a DISTRO_RELEASE_NOTES image. The fetcher reads the whole range
    cur..new itself (every Alpine post naming a release in the range; every
    Python "What's New" page the hop enters, or the target minor's "Notable
    changes in X.Y.N" sections for a patch hop), so there is no separate
    release-list walk. Unfetchable => ([], False), the same "not read" G3
    reports for a GitHub project it cannot reach."""
    try:
        notes = checker.fetch_distro_release_notes(dep, cur_tag, new_tag)
    except Exception:
        return [], False
    if not notes or not notes.get("body"):
        return [], False
    return list(checker.detect_breaking_changes(notes["body"], "minor") or []), True


def distro_range_read(checker, dep):
    """True when G3 for `dep` already covers the whole cur..new RANGE, so the
    GitHub release-list range walk has nothing to add (and could only report
    "unreadable" — these projects publish no GitHub releases)."""
    return bool(_distro_source(checker, dep))


def _build_context(checker, dep):
    """Repository-relative build-context prefix for `dep`, or None."""
    try:
        fn = getattr(checker, "get_image_build_context", None)
        ctx = fn(dep) if fn else None
    except Exception:
        ctx = None
    if not ctx:
        return None
    ctx = str(ctx).strip().lstrip("./").strip("/")
    return (ctx + "/") if ctx else None


def _in_context(path, ctx):
    return ctx is None or str(path or "").startswith(ctx)


# ── G3s: the STRUCTURAL companion gate — the DIFF, not the prose ─────────────
# WHY THIS EXISTS (F-ea1000ff, 2026-09-20). G3 reads release-note PROSE. It
# therefore holds when upstream happens to write the word "breaking" and
# passes when upstream does not — the presence of the hazard and the presence
# of the sentence are two different things. In the measured case the held
# bump's stated reason was a frontend-dependency note that could not touch the
# workload's data path, while the SAME diff carried a new database migration
# and a bumped search-index schema constant: a blocking full-index rebuild at
# container start plus a migration on the app's database, with nobody
# watching had the prose been one adjective quieter. The hold was correct by
# accident. This gate asks the question the prose cannot answer: WHAT CHANGED
# in the tree between the two tags.
#
# Two structural signals, both mechanical and both cheap to state:
#   * a file ADDED under a migrations directory — django/alembic/rails/prisma/
#     flyway/liquibase layouts and the plain `migrations/`, at any depth
#     (prisma nests `migrations/<stamp>/migration.sql`);
#   * an ADDED line assigning an UPPER-CASE `*_VERSION` / `*_REVISION`
#     constant whose stem names a schema, index, database, migration or
#     storage format — the `SCHEMA_VERSION = 2` shape. Comparisons (`==`) and
#     documentation/test paths are excluded.
#
# The compare API caps its file list at 300, and the measured diff was exactly
# that size — sorted by path, with the migration and the schema file sitting
# AFTER the 300th entry. So a truncated compare is NOT read as "nothing more":
# the two git trees are diffed for the path signal (no cap) and the changed
# files whose NAME suggests a schema or version constant are fetched for the
# constant signal, bounded by _TREE_FETCH_CAP; anything beyond that bound is
# reported as an incomplete scan, never as clean.
#
# Same asymmetry as G3, stated once: a POSITIVE signal holds. An unreadable
# diff is returned as `resolved=False` with the reason and does NOT hold on
# its own — the PR lane already relies on CI + policy for the unverified case
# and says so in its verdict; the direct-bump lane in coverage.py mirrors this
# gate with the same hold-or-annotate contract. Lower-case constants
# (`schema_version = 2`) are a known gap of the constant rule; the path rule
# does not depend on naming.
_STRUCTURAL_PATH_RE = re.compile(
    r"(?:^|/)(?:migrations?|migrate|alembic/versions|db/migrate|prisma/migrations|"
    r"database/migrations|schema/migrations|flyway|liquibase)/.+$", re.IGNORECASE)
_STRUCTURAL_CONST_RE = re.compile(
    r"^\+(?!\+\+).*?\b_?(?:[A-Z0-9]+_)*(?:SCHEMA|INDEX|DB|DATABASE|MIGRATION|STORAGE)"
    r"_(?:VERSION|REVISION)\b\s*(?::[^=\n]{0,40})?=(?!=)", re.MULTILINE)
# Paths whose constants are not the running code: docs, tests, examples.
_STRUCTURAL_EXCLUDE_RE = re.compile(
    r"(?:^|/)(?:docs?|tests?|__tests__|spec|examples?|fixtures?)/|\.(?:md|rst|txt)$",
    re.IGNORECASE)
# Files worth fetching when the compare response is TRUNCATED: changed files
# whose NAME suggests a schema/version constant lives there.
_SCHEMA_FILE_RE = re.compile(
    r"(?:^|/)[^/]*(?:schema|migrat|version|const|settings|config|index)[^/]*"
    r"\.(?:py|ts|js|mjs|cjs|go|rs|rb|java|kt|cs|php|ex|exs|json|ya?ml|toml)$",
    re.IGNORECASE)
_COMPARE_FILE_CAP = 300     # GitHub's documented ceiling for compare `files`
_TREE_FETCH_CAP = 8         # content fetches per truncated compare, at most
_STRUCTURAL_CACHE: dict = {}


def _numeric_tag(tag):
    """`v0.143.0-noble-full` -> `0.143.0`; None when the tag has no digits."""
    t = _vt(tag)
    return ".".join(str(x) for x in t) if t else None


def _tag_pair_candidates(checker, dep, cur_tag, new_tag):
    """Ordered (base, head) git-ref pairs for the compare call.

    Docker tags and git tags disagree about the `v` prefix and about build
    suffixes. The release list this file already fetches names the REAL tags,
    so an exact numeric match there (stable releases first) comes first; the
    raw pair and the bare/`v` numeric pairs follow for tags-only repositories.
    """
    exact = {}
    rels = github_releases(checker, dep) or []
    want = {"cur": _vt(cur_tag), "new": _vt(new_tag)}
    for prefer_stable in (True, False):
        for tag, pre in rels:
            if pre == prefer_stable:
                continue
            vt = _vt(tag)
            for k, v in want.items():
                if v and vt == v and k not in exact:
                    exact[k] = tag
    pairs = []
    if "cur" in exact and "new" in exact:
        pairs.append((exact["cur"], exact["new"]))
    raw = (str(cur_tag).split("@")[0], str(new_tag).split("@")[0])
    c, n = _numeric_tag(cur_tag), _numeric_tag(new_tag)
    for pair in (raw, (c, n), (f"v{c}", f"v{n}")):
        if all(pair) and pair not in pairs:
            pairs.append(pair)
    return pairs


def _compare_changed_files(owner, repo, base, head, timeout: int = 25):
    """{'files', 'truncated', 'commits'} for base...head, `_NOT_FOUND` when a
    ref does not exist, None when unknowable."""
    data = _gh_api_json(f"repos/{owner}/{repo}/compare/{base}...{head}", timeout)
    if data is _NOT_FOUND or data is None or not isinstance(data, dict):
        return data if data is _NOT_FOUND else None
    files = [f for f in (data.get("files") or []) if isinstance(f, dict)]
    return {"files": files, "truncated": len(files) >= _COMPARE_FILE_CAP,
            "commits": data.get("total_commits")}


def _scan_structural_files(files):
    """Signals from compare `files` entries (filename/status/patch)."""
    out = []
    for f in files:
        name = str(f.get("filename") or "")
        status = str(f.get("status") or "")
        if status in ("added", "renamed", "copied") and _STRUCTURAL_PATH_RE.search(name):
            out.append(f"new migration file {name}")
            continue
        if _STRUCTURAL_EXCLUDE_RE.search(name):
            continue
        m = _STRUCTURAL_CONST_RE.search(str(f.get("patch") or ""))
        if m:
            out.append(f"{name}: {m.group(0).lstrip('+').strip()[:80]}")
    return out


def _tree_blobs(owner, repo, ref, timeout: int = 40):
    """{path: blob sha} for a ref's full tree, or None (missing/unknowable/
    truncated — a truncated tree cannot prove a path absent)."""
    data = _gh_api_json(f"repos/{owner}/{repo}/git/trees/{ref}?recursive=1", timeout)
    if data is _NOT_FOUND or not isinstance(data, dict) or data.get("truncated"):
        return None
    return {str(e.get("path")): e.get("sha") for e in (data.get("tree") or [])
            if isinstance(e, dict) and e.get("type") == "blob" and e.get("path")}


def _file_lines(owner, repo, path, ref, timeout: int = 20):
    """Text lines of `path` at `ref`, or None."""
    import base64
    import urllib.parse
    data = _gh_api_json(
        f"repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}?ref={ref}", timeout)
    if not isinstance(data, dict) or data.get("encoding") != "base64":
        return None
    try:
        return base64.b64decode(data.get("content") or "").decode("utf-8", "replace").splitlines()
    except Exception:
        return None


def structural_signal(checker, dep, new_tag, cur_tag=None):
    """(signals, resolved, note) — migration/schema changes in the DIFF
    cur_tag..new_tag of `dep`'s source repository.

    `signals` non-empty means HOLD. `resolved` True means the whole scan
    completed (a clean verdict is meaningful); False means the diff could not
    be read completely and `note` says why — callers annotate, they do not
    hold on it (see the block comment above). Cached per (dep, cur, new).
    """
    key = (str(dep), str(cur_tag), str(new_tag))
    if key in _STRUCTURAL_CACHE:
        return _STRUCTURAL_CACHE[key]
    try:
        out = _structural_signal_uncached(checker, dep, new_tag, cur_tag)
    except Exception as e:  # a gate failure is reported, never read as clean
        out = ([], False, f"structural scan failed ({type(e).__name__})")
    _STRUCTURAL_CACHE[key] = out
    return out


def _structural_signal_uncached(checker, dep, new_tag, cur_tag):
    if not cur_tag or str(cur_tag) in ("", "?"):
        return [], False, "current version unknown — no base ref for the compare"
    owner_repo = _owner_repo(checker, dep)
    if not owner_repo:
        return [], False, "no source repository resolved for the compare"
    owner, repo = owner_repo
    if github_releases(checker, dep) is None:
        # Tags-only repositories have no releases; a MISSING repository has no
        # tags either, and probing it four ways would spend four calls on a
        # fact one call settles.
        probe = _gh_api_json(f"repos/{owner}/{repo}", 15)
        if probe is _NOT_FOUND:
            return [], False, f"source repository {owner}/{repo} not found on GitHub"
        if probe is None:
            return [], False, f"GitHub unreachable for {owner}/{repo} (compare not attempted)"
    cmp = used = None
    pairs = _tag_pair_candidates(checker, dep, cur_tag, new_tag)
    for base, head in pairs:
        r = _compare_changed_files(owner, repo, base, head)
        if r is _NOT_FOUND:
            continue
        if r is None:
            return [], False, f"compare {base}...{head} unreadable for {owner}/{repo}"
        cmp, used = r, (base, head)
        break
    if cmp is None:
        return [], False, (f"compare refs unresolved for {owner}/{repo} "
                           f"(tried {len(pairs)} tag spelling(s))")
    # BUILD-CONTEXT SCOPE (2026-09-26). A monorepo ships several products from
    # one tree; only files inside the image's own build context can be in the
    # image. mqttx-web was held for a TypeORM migration under the Electron
    # DESKTOP tree (`src/`) while the image builds from `web/` and carries no
    # database. Unlisted images keep the whole-repository scan.
    ctx = _build_context(checker, dep)
    scope = f" (scoped to build context {ctx})" if ctx else ""
    in_ctx = [f for f in cmp["files"] if _in_context(f.get("filename"), ctx)]
    signals = _scan_structural_files(in_ctx)
    span = f"{used[0]}...{used[1]}"
    if not cmp["truncated"]:
        return _dedupe(signals), True, (f"diff {span} read{scope}: {len(in_ctx)} of "
                                        f"{len(cmp['files'])} file(s), "
                                        f"{cmp.get('commits')} commit(s)")
    # TRUNCATED: the 300 files seen are a prefix of the diff, not the diff.
    base_t, head_t = _tree_blobs(owner, repo, used[0]), _tree_blobs(owner, repo, used[1])
    if base_t is None or head_t is None:
        return _dedupe(signals), False, (
            f"diff {span} truncated at {_COMPARE_FILE_CAP} files and the trees could "
            f"not be read — structural scan INCOMPLETE")
    added = [p for p in head_t if p not in base_t and _in_context(p, ctx)]
    changed = [p for p, sha in head_t.items()
               if p in base_t and base_t[p] != sha and _in_context(p, ctx)]
    signals += [f"new migration file {p}" for p in added if _STRUCTURAL_PATH_RE.search(p)]
    cands = [p for p in added + changed
             if _SCHEMA_FILE_RE.search(p) and not _STRUCTURAL_EXCLUDE_RE.search(p)]
    complete = len(cands) <= _TREE_FETCH_CAP
    fetched = 0
    for path in cands[:_TREE_FETCH_CAP]:
        head_lines = _file_lines(owner, repo, path, used[1])
        if head_lines is None:
            complete = False
            continue
        base_lines = _file_lines(owner, repo, path, used[0]) if path in base_t else []
        if base_lines is None:
            complete = False
            base_lines = []
        fetched += 1
        for ln in sorted(set(head_lines) - set(base_lines)):
            if _STRUCTURAL_CONST_RE.search("+" + ln):
                signals.append(f"{path}: {ln.strip()[:80]}")
                break
    note = (f"diff {span}{scope} truncated at {_COMPARE_FILE_CAP} files; trees diffed "
            f"({len(added)} added, {len(changed)} changed), {fetched}/{len(cands)} "
            f"schema-named file(s) read")
    if not complete:
        note += " — structural scan INCOMPLETE"
    return _dedupe(signals), complete, note


def _dedupe(items):
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ── G5 release-age cooldown ──────────────────────────────────────────────────
_SEC_MARKERS = ("cve", "security", "vulnerability", "ghsa")


def age_waivers(policy, today=None):
    """(active_globs, expired, malformed) from the policy's `age_waive` list.

    Two entry shapes, both git-tracked in auto-update-policy.yaml:

      - "*mealie*"                          plain glob — PERMANENT until removed
                                            (the only shape before 2026-09-22;
                                            still honoured unchanged)
      - {match: "*mealie*", until: 2026-12-31, reason: "..."}
                                            glob with an EXPIRY. `until` is an
                                            inclusive UTC date; the waiver is
                                            in force through that day and
                                            stops waiving the day after.

    F-7eaae066: the plain form was the only one, and the policy's own comment
    says it waives the cooldown for ALL future bumps of the component. For two
    externally exposed services that turned a one-day CVE decision into a
    permanent supply-chain exemption nobody re-decides. A dated waiver lapses
    on its own; the lapse is the re-review trigger.

    FAIL-CLOSED on the waiver's own defects: an entry whose `until` cannot be
    read, or whose `match` is missing, is returned in `malformed` and does NOT
    waive — a relaxation that cannot be read must not relax. An `until` in the
    past lands in `expired` (as `(glob, until)`), also not waiving. `today` is
    injectable for tests.

    Both lanes consume THIS function (auto-update.py's PR lane via
    security_waived(), coverage.py's direct-bump lane via
    _active_age_waivers()), so they cannot disagree about whether a waiver has
    lapsed.
    """
    import datetime as _dt
    today = today or _dt.datetime.now(_dt.timezone.utc).date()
    active, expired, malformed = [], [], []
    for entry in (policy or {}).get("age_waive") or []:
        if isinstance(entry, str):
            if entry.strip():
                active.append(entry)
            else:
                malformed.append("empty glob string")
            continue
        if not isinstance(entry, dict):
            malformed.append(f"unsupported entry shape {type(entry).__name__}: {entry!r}"[:120])
            continue
        pat = entry.get("match")
        if not isinstance(pat, str) or not pat.strip():
            malformed.append(f"mapping entry without a `match` glob: {entry!r}"[:120])
            continue
        until = entry.get("until")
        if until is None or (isinstance(until, str) and not until.strip()):
            active.append(pat)            # a mapping with no expiry is the plain form
            continue
        try:
            if isinstance(until, _dt.datetime):
                until_d = until.date()
            elif isinstance(until, _dt.date):
                until_d = until
            else:
                until_d = _dt.date.fromisoformat(str(until).strip()[:10])
        except (ValueError, TypeError):
            malformed.append(f"age_waive {pat!r}: unreadable `until` {until!r} — not waiving")
            continue
        if today > until_d:
            expired.append((pat, until_d))
        else:
            active.append(pat)
    return active, expired, malformed


def security_waived(pr, policy):
    """CVE-driven bumps skip the age cooldown (operator: 0 days for CVE fixes).
    Signals: security markers in the PR title or labels, or an operator
    `age_waive` glob on the dep that is still IN FORCE (see age_waivers():
    an expired or unreadable waiver does not waive)."""
    hay = (pr.get("title") or "").lower() + " " + " ".join(
        (l.get("name") or "").lower() if isinstance(l, dict) else str(l).lower()
        for l in (pr.get("labels") or []))
    if any(m in hay for m in _SEC_MARKERS):
        return "security-marked PR"
    dep = (pr.get("_dep") or "").lower()
    active, _expired, _malformed = age_waivers(policy)
    for pat in active:
        if fnmatch.fnmatch(dep, str(pat).lower()):
            return f"age_waive glob {pat!r}"
    return None


def newest_commit_age_hours(number):
    """Hours since the PR's newest commit, or None when unknowable."""
    rc, out, _ = run(["gh", "pr", "view", str(number),
                      "--json", "commits"], timeout=45)
    if rc != 0:
        return None
    try:
        commits = json.loads(out or "{}").get("commits", [])
        newest = max(c.get("committedDate") or c.get("authoredDate") or ""
                     for c in commits)
        if not newest:
            return None
        from datetime import datetime, timezone
        ts = datetime.fromisoformat(newest.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    except Exception:
        return None


_COVERAGE_MOD = None


def _load_coverage():
    """coverage.py's registry-date helper (image_publish_age_hours), lazily.
    Loaded by file path (same trick as _load_version_checker) so the shared
    OCI/Docker-Hub date code has ONE home instead of a copy here."""
    global _COVERAGE_MOD
    if _COVERAGE_MOD is None:
        spec = importlib.util.spec_from_file_location(
            "cberg_coverage", SCRIPT_DIR / "coverage.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore
        _COVERAGE_MOD = mod
    return _COVERAGE_MOD


def _hours_since_iso(ts):
    """Hours since an ISO-8601 timestamp string, or None."""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return None


def upstream_release_age_hours(checker, dep, new_tag):
    """(age_hours, source) from the UPSTREAM publish time of `new_tag`, else
    (None, None).

    This is the clock G5 actually cares about: the PR-commit measure resets on
    every Renovate force-push, so a component that ships faster than the
    cooldown (n8n, every ~1-2 days) could NEVER pass it — PR #210 sat 9 days
    while each retarget restarted the clock. The release's own publish
    timestamp ages monotonically; a retarget still restarts the cooldown, but
    only because the new target release genuinely IS young.

    Two sources, tried in order:
      1. the GitHub release `published_at` for the tag (works for charts and
         images with a resolvable source repo — same resolution as G3);
      2. the registry publish date of the image tag (coverage.py's
         image_publish_age_hours: Docker Hub last_updated / OCI config created).
    """
    # 1. GitHub release published_at (chart or image with a known source repo)
    owner_repo = None
    try:
        if "/" in dep:
            owner_repo = checker.get_repo_info_from_image(dep)
        if not owner_repo:
            owner_repo = checker.get_chart_repo_info(dep.split("/")[-1], "", "")
    except Exception:
        owner_repo = None
    if owner_repo:
        try:
            notes = checker.fetch_release_notes(owner_repo[0], owner_repo[1], new_tag)
            age = _hours_since_iso((notes or {}).get("published_at"))
            if age is not None:
                return age, f"upstream GitHub release ({owner_repo[0]}/{owner_repo[1]} {new_tag})"
        except Exception:
            pass
    # 2. registry tag publish date (image-shaped deps only)
    if "/" in dep:
        try:
            cov = _load_coverage()
            for tag in (new_tag, new_tag.lstrip("vV"), f"v{new_tag.lstrip('vV')}"):
                age = cov.image_publish_age_hours(dep, tag)
                if age is not None:
                    return age, f"registry publish date ({dep}:{tag})"
        except Exception:
            pass
    return None, None


def age_gate(pr, parsed, policy, checker=None):
    """None = pass; else (gate, reason) hold tuple. Fail-safe: unknown HOLDS.

    Prefers the upstream release timestamp; falls back to the PR's newest
    commit (the stricter, force-push-resettable measure) when upstream is
    unknowable, and names the measure used either way."""
    min_age = policy.get("minimum_release_age_hours") or 0
    if not min_age:
        return None
    waiver = security_waived({**pr, "_dep": parsed["dep"]}, policy)
    if waiver:
        return None
    age = source = None
    if checker is not None:
        age, source = upstream_release_age_hours(checker, parsed["dep"], parsed["new"])
    if age is None:
        age = newest_commit_age_hours(pr["number"])
        source = "PR newest commit (upstream release date unavailable — stricter fallback)"
    if age is None:
        return ("age", f"release age UNKNOWN on both measures (cannot prove the "
                       f"{min_age}h cooldown elapsed) — holding")
    log(f"   G5 #{pr['number']}: age {age:.0f}h via {source}")
    if age < min_age:
        return ("age", f"release only {age:.0f}h old via {source} (< {min_age}h "
                       f"cooldown); auto-merges after the cooldown or on a security signal")
    return None


# ── CI / mergeability (G4) ───────────────────────────────────────────────────
# G4 names NO required check: it holds on ANY non-green entry in the rollup
# (fail-closed — a check nobody anticipated can only hold, never pass). The one
# way a check that "no longer runs" can still hold a PR is a check run already
# attached to the PR's head SHA by a job that has since been removed from its
# workflow file: GitHub keeps it until a fresh run replaces the rollup, and
# nothing re-runs PR workflows when main changes. That is exactly what the
# flux-local retirement left behind (F-6b1dd22b): PR #219 carried
# `Flux Local Test=FAILURE` beside a green `Flate Render Gate` on the SAME SHA.
# The verdict stays hold (no green CI = hold) — teaching G4 to ignore a name
# would be a silent-green — but the reason names the cause and the remedy, so
# the hold cannot pass for a legitimate per-PR CI failure for days (F-00235e5c).
WORKFLOW_DIR = Path(__file__).resolve().parents[1] / ".github/workflows"


def workflow_check_names(workflow_dir=WORKFLOW_DIR):
    """{workflow display name: {job display names}} read from the repo's own
    workflow files. A rollup entry whose (workflowName, name) pair is not in
    here was produced by a job that no longer exists in that workflow."""
    out = {}
    for f in sorted(Path(workflow_dir).glob("*.y*ml")):
        try:
            wf = yaml.safe_load(f.read_text()) or {}
        except Exception:
            continue
        jobs = wf.get("jobs") if isinstance(wf, dict) else None
        if not isinstance(jobs, dict):
            continue
        out[str(wf.get("name") or f.stem)] = {
            str(j.get("name") or jid) for jid, j in jobs.items() if isinstance(j, dict)}
    return out


def stale_check_note(check, defined):
    """Pure. '' when the check's job still exists in its workflow file, or when
    the check did not come from one of our workflows (nothing to judge); else a
    diagnosis to append to the hold reason. Matrix legs report as 'Name (leg)'."""
    wf = check.get("workflowName")
    if not wf or wf not in defined:
        return ""
    name = str(check.get("name") or "")
    if any(name == n or name.startswith(n + " (") for n in defined[wf]):
        return ""
    return (f" [no job named that in the '{wf}' workflow any more — a stale check run "
            f"on this head SHA; reopen or rebase the PR for a fresh run]")


def ci_state(number, defined=None):
    """Return (ok, detail). ok=True only when mergeable + every check succeeded."""
    rc, out, err = run([
        "gh", "pr", "view", str(number),
        "--json", "mergeable,mergeStateStatus,statusCheckRollup",
    ], timeout=45)
    if rc != 0:
        return False, f"gh view failed: {err.strip()}"
    d = json.loads(out or "{}")
    if d.get("mergeable") != "MERGEABLE":
        return False, f"not mergeable (mergeable={d.get('mergeable')}, state={d.get('mergeStateStatus')})"
    rollup = d.get("statusCheckRollup") or []
    if defined is None:
        defined = workflow_check_names()
    bad, pending = [], []
    for c in rollup:
        # CheckRun uses status/conclusion; StatusContext uses state
        concl = (c.get("conclusion") or c.get("state") or "").upper()
        status = (c.get("status") or "").upper()
        name = c.get("name") or c.get("context") or "check"
        note = stale_check_note(c, defined)
        if status and status != "COMPLETED" and not concl:
            pending.append(name + note)
        elif concl in {"SUCCESS", "NEUTRAL", "SKIPPED"}:
            continue
        elif concl in {"", "PENDING", "EXPECTED", "IN_PROGRESS", "QUEUED"}:
            pending.append(name + note)
        else:
            bad.append(f"{name}={concl}" + note)
    if bad:
        return False, "CI failing: " + ", ".join(bad)
    if pending:
        return False, "CI pending: " + ", ".join(pending)
    return True, "mergeable + all checks green"


# ── classify one PR ──────────────────────────────────────────────────────────
def classify(pr, policy, checker):
    r = {"number": pr["number"], "title": pr["title"], "url": pr.get("url", "")}
    if pr.get("isDraft"):
        return {**r, "verdict": "hold", "gate": "draft", "reason": "draft PR"}
    parsed = parse_pr(pr)
    if "parse_error" in parsed:
        return {**r, "verdict": "hold", "gate": "parse", "reason": parsed["parse_error"]}
    r.update(dep=parsed["dep"], cur=parsed["cur"], new=parsed["new"],
             cur_known=parsed.get("cur_known", True),
             update_type=parsed["update_type"])

    # G1 type
    if parsed["update_type"] not in SAFE_TYPES:
        return {**r, "verdict": "hold", "gate": "type",
                "reason": f"update_type={parsed['update_type']} (only patch/minor auto-apply)"}
    # G2 policy
    blocked = policy_block(policy, parsed["dep"], parsed["update_type"])
    if blocked:
        return {**r, "verdict": "hold", "gate": "policy", "reason": blocked}
    # G5 age (before the expensive gates; cheap policy checks already passed)
    held = age_gate(pr, parsed, policy, checker)
    if held:
        return {**r, "verdict": "hold", "gate": held[0], "reason": held[1]}
    # G3 breaking
    notes, resolved = breaking_signal(
        checker, parsed["dep"], parsed["new"],
        cur_tag=parsed["cur"] if parsed.get("cur_known") else None)
    if notes:
        return {**r, "verdict": "hold", "gate": "breaking",
                "reason": "breaking-change signal in release notes: " + "; ".join(n[:120] for n in notes[:2])}
    r["breaking_checked"] = resolved
    # G3s structural — the DIFF, not the prose (F-ea1000ff)
    s_sigs, s_resolved, s_note = structural_signal(
        checker, parsed["dep"], parsed["new"],
        cur_tag=parsed["cur"] if parsed.get("cur_known") else None)
    if s_sigs:
        return {**r, "verdict": "hold", "gate": "structural",
                "reason": "structural change in the diff (migration/schema): "
                          + "; ".join(str(x)[:120] for x in s_sigs[:2])}
    r["structural_checked"] = s_resolved
    r["structural_note"] = s_note
    # G4 ci
    ok, detail = ci_state(pr["number"])
    if not ok:
        return {**r, "verdict": "hold", "gate": "ci", "reason": detail}
    return {**r, "verdict": "safe", "gate": "-",
            "reason": "patch/minor, not denied, no breaking signal, CI green"
                      + ("" if resolved else " (release notes unavailable — relied on CI + policy)")
                      + ("" if s_resolved else f" (diff not inspected for migrations/schema — {s_note})")}


# ── apply: merge, reconcile, health-gate, revert ─────────────────────────────
def affected_apps(number):
    """namespaces/apps touched by a PR, from kubernetes/apps/<ns>/<app>/ paths."""
    rc, out, _ = run(["gh", "pr", "view", str(number), "--json", "files"], timeout=45)
    apps = set()
    if rc == 0:
        for f in json.loads(out or "{}").get("files", []):
            parts = Path(f["path"]).parts
            if len(parts) >= 4 and parts[0] == "kubernetes" and parts[1] == "apps":
                apps.add((parts[2], parts[3]))
    return apps


def post_apply_health(namespaces):
    """Return (ok, problems[]). Checks Flux HR/Ks readiness + pod health in the
    affected namespaces after reconcile."""
    problems = []
    # Flux kustomizations + helmreleases not Ready anywhere → hard fail
    for kind in ("kustomization", "helmrelease"):
        rc, out, _ = run(["flux", "get", kind, "-A", "--status-selector", "ready=false"], timeout=60)
        if rc == 0:
            for line in out.splitlines():
                line = line.strip()
                if not line or line.startswith("NAMESPACE") or "\tTrue\t" in line:
                    continue
                # any row printed by ready=false is a not-ready object
                if line and not line.lower().startswith("no "):
                    problems.append(f"flux {kind} not ready: {line.split()[0:2]}")
    # Pods in affected namespaces
    for ns in sorted(namespaces):
        rc, out, _ = run(["kubectl", "get", "pods", "-n", ns, "-o", "json"], timeout=45)
        if rc != 0:
            continue
        for p in json.loads(out or "{}").get("items", []):
            name = p["metadata"]["name"]
            st = p.get("status", {})
            phase = st.get("phase", "")
            for cs in st.get("containerStatuses", []) or []:
                w = (cs.get("state", {}).get("waiting") or {})
                if w.get("reason") in {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerError"}:
                    problems.append(f"{ns}/{name}: {w['reason']}")
                restarts = cs.get("restartCount", 0)
                if restarts >= 5 and not cs.get("ready", False):
                    problems.append(f"{ns}/{name}: {restarts} restarts, not ready")
            if phase in {"Failed"}:
                problems.append(f"{ns}/{name}: phase={phase}")
    return (len(problems) == 0), problems


def merge_pr(number):
    rc, out, err = run(["gh", "pr", "merge", str(number), "--squash", "--delete-branch"], timeout=120)
    if rc != 0:
        return None, err.strip()
    # resolve the squash commit for potential revert
    time.sleep(3)
    rc2, out2, _ = run(["gh", "pr", "view", str(number), "--json", "mergeCommit"], timeout=45)
    sha = None
    if rc2 == 0:
        sha = (json.loads(out2 or "{}").get("mergeCommit") or {}).get("oid")
    return sha or "unknown", None


def git_sync():
    run(["git", "-C", str(REPO_ROOT), "fetch", "origin", "main"], timeout=90)
    run(["git", "-C", str(REPO_ROOT), "merge", "--ff-only", "origin/main"], timeout=60)


def reconcile(apps):
    run(["flux", "reconcile", "source", "git", "flux-system"], timeout=120)
    for ns, app in sorted(apps):
        run(["flux", "reconcile", "kustomization", app, "-n", ns, "--with-source"], timeout=180)


def revert_batch(shas):
    reverted = []
    for sha in shas:
        if not sha or sha == "unknown":
            continue
        rc, _, err = run(["git", "-C", str(REPO_ROOT), "revert", "--no-edit", sha], timeout=60)
        if rc == 0:
            reverted.append(sha)
        else:
            log(f"  !! revert of {sha[:8]} failed: {err.strip()}")
    if reverted:
        run(["git", "-C", str(REPO_ROOT), "push", "origin", "main"], timeout=120)
    return reverted


# ── findings / alert ─────────────────────────────────────────────────────────
def _writer():
    try:
        sys.path.insert(0, str(SCRIPT_DIR / "lib"))
        from findings_writer import (FindingsWriter, cycle_id_from_env,  # type: ignore
                                      trigger_from_env, git_head)
        return FindingsWriter(
            dsn=os.environ.get("SWEEP_PG_DSN"),
            section="version",
            cycle_id=cycle_id_from_env(),
            trigger=trigger_from_env(),
            git_head=git_head(),
            producer="script",
        )
    except Exception as e:
        log(f"  (findings writer unavailable: {e})")
        return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="merge safe PRs (needs cron trigger)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    if args.json:
        # Fence stdout for the whole run: anything printed by a library (the
        # findings writer, an imported module's banner) goes to stderr, and only
        # emit_json() reaches the real stdout. See emit_json's docstring.
        sys.stdout = sys.stderr

    trigger = os.environ.get("SWEEP_TRIGGER", "manual")
    force = os.environ.get("AUTO_UPDATE_APPLY") == "1"
    apply = args.apply and (trigger == "cron" or force)
    apply_blocked = args.apply and not apply

    policy = load_policy()
    checker = _load_version_checker()
    prs = list_renovate_prs()
    log(f"== auto-update: {len(prs)} open Renovate PR(s) · policy v{policy.get('version','?')} "
        f"· trigger={trigger} · mode={'APPLY' if apply else 'dry-run'} ==")
    # A lapsed or unreadable waiver is reported ONCE per run, so the operator
    # sees the cooldown is back in force and prunes the entry — silently
    # ignoring it would look identical to the waiver still working.
    _act, _exp, _mal = age_waivers(policy)
    for _pat, _until in _exp:
        log(f"   age_waive {_pat!r} EXPIRED {_until} — cooldown back in force; prune it")
    for _why in _mal:
        log(f"!! age_waive entry ignored (fail-closed, does NOT waive): {_why}")

    classified = [classify(pr, policy, checker) for pr in prs]
    safe = [c for c in classified if c["verdict"] == "safe"]
    held = [c for c in classified if c["verdict"] == "hold"]

    for c in classified:
        icon = "✅" if c["verdict"] == "safe" else "⏸️ "
        log(f"{icon} #{c['number']} {c.get('dep','?')} {c.get('cur','')}→{c.get('new','')} "
            f"[{c.get('update_type','?')}] — {c['reason']}")

    result = {"trigger": trigger, "apply": apply, "safe": safe, "held": held,
              "merged": [], "reverted": [], "health": None}

    if apply_blocked:
        log("\n-- --apply given but trigger is not 'cron' (and AUTO_UPDATE_APPLY≠1): "
            "staying read-only. This is the manual-sweep guard. --")
    if not apply:
        w = _writer()
        if w:
            with w:
                if safe:
                    w.emit("monitor", f"{len(safe)} safe update(s) ready to auto-merge at the next maintenance window",
                           action="The maintenance-window-agent applies these at Step 0 of the next window (nightly 03:30 daily, or sat/sun 09:00). The sweep is read-only and will NOT merge them. To apply now, run with AUTO_UPDATE_APPLY=1 --apply.",
                           subsection="auto-update",
                           metadata={"safe": [f"#{c['number']} {c['dep']}" for c in safe]})
        if args.json:
            emit_json(result)
        log(f"\n== {len(safe)} safe / {len(held)} held · dry-run (no changes) ==")
        return 0

    # ---- APPLY ----
    if not safe:
        log("\n== nothing safe to merge ==")
        if args.json:
            emit_json(result)
        return 0

    merged, all_apps = [], set()
    for c in safe:
        sha, err = merge_pr(c["number"])
        if err:
            log(f"  !! merge #{c['number']} failed: {err}")
            continue
        c["merge_sha"] = sha
        merged.append(c)
        all_apps |= affected_apps(c["number"])
        log(f"  ✔ merged #{c['number']} {c['dep']} → {c['new']} ({str(sha)[:8]})")
    result["merged"] = [{"number": c["number"], "dep": c["dep"], "new": c["new"], "sha": c.get("merge_sha")} for c in merged]

    if not merged:
        log("== no PRs merged (all merge attempts failed) ==")
        if args.json:
            emit_json(result)
        return 1

    log(f"\n-- syncing local main + reconciling {len(all_apps)} affected app(s) --")
    git_sync()
    reconcile(all_apps)
    log(f"-- waiting {RECONCILE_WAIT_S}s for rollout, then health gate --")
    time.sleep(RECONCILE_WAIT_S)
    ok, problems = post_apply_health({ns for ns, _ in all_apps})
    result["health"] = {"ok": ok, "problems": problems}

    w = _writer()
    if not ok:
        log("\n!! POST-APPLY HEALTH GATE FAILED — reverting the batch:")
        for p in problems:
            log(f"     - {p}")
        reverted = revert_batch([c.get("merge_sha") for c in merged])
        result["reverted"] = reverted
        reconcile(all_apps)  # push cluster back to reverted state
        title = f"Auto-update reverted: {len(reverted)} merge(s) regressed the cluster"
        # Emit the sweep finding first so we can key the OpenClaw issue on its
        # finding_id. Stable across cycles, but fingerprint-DERIVED: it is
        # re-derived if the identity function changes, so a long-lived issue key
        # can go stale (see docs/sops/sweep-findings-lifecycle.md §4.1b).
        fid = None
        if w:
            with w:
                fid = w.emit("critical", title,
                             action="Investigate the reverted bumps; they are back on the deny path until fixed",
                             subsection="auto-update",
                             metadata={"reverted": reverted, "problems": problems[:20],
                                       "merged": [f"#{c['number']} {c['dep']}→{c['new']}" for c in merged]})
        # Route to OpenClaw (owner of the open-issue + reminder lifecycle);
        # notify.py is only the fallback when the openclaw pod is unreachable.
        merged_line = ", ".join(f"{c['dep']}→{c['new']}" for c in merged)
        try:
            sys.path.insert(0, str(SCRIPT_DIR / "lib"))
            from notify import ingest_or_notify  # type: ignore
            route = ingest_or_notify(
                {"key": fid or f"auto-update-revert-{merged[0]['number']}",
                 "kind": "auto_update_revert", "source": "auto-update",
                 "severity": "critical", "action": "ack",
                 "title": title, "component": merged_line,
                 "detail": "reverted after post-apply health failure: " + "; ".join(problems[:6])},
                fallback_text=("⛔ *Auto-update reverted* — a merged bump regressed the cluster:\n"
                               + merged_line + "\nProblems: " + "; ".join(problems[:4])
                               + "\nBatch reverted; cluster restored. Needs a look."),
                urgent=True)
            log(f"  operator issue routed via: {route}")
        except Exception as e:
            log(f"  (operator notify failed: {e})")
        log("\n== ALERT: batch auto-reverted; cluster restored to pre-merge state ==")
        if args.json:
            emit_json(result)
        return 2

    log(f"\n== applied {len(merged)} update(s), post-apply health OK ==")
    if w:
        with w:
            w.emit("clean", f"Auto-update merged {len(merged)} safe update(s), cluster healthy",
                   subsection="auto-update",
                   metadata={"merged": [f"#{c['number']} {c['dep']}→{c['new']}" for c in merged]})
    if args.json:
        emit_json(result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"!! auto-update hard error: {e}")
        sys.exit(1)
