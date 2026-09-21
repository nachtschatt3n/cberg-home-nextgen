#!/usr/bin/env python3
"""Regression test: a Renovate PR covers an ARTIFACT, not a name.

F-ebd51739, verified 2026-09-10 by replaying the parser against a freshly
generated version-check-current.md. `parse_renovate_prs()` keyed a plain dict
on the LAST path segment of the dependency name, so two open PRs reduced to the
same key `cloudflared`:

  #214  docker.io/cloudflare/cloudflared  2026.8.3 -> 2026.9.0   the cluster
                                                                 tunnel CONTAINER
  #215  aqua:cloudflare/cloudflared       2026.8.2 -> 2026.9.0   the local CLI
                                                                 pin in .mise.toml

The snapshot lists them in ascending PR order, so #215 overwrote #214 and the
lane table named the WRONG artifact for a change to an internet-facing tunnel.
Both converge on 2026.9.0, which is what masked it — the sibling case
(F-9a58f400, `aqua:siderolabs/talos` attributed to the Talos NODE image) was
only caught because the two versions differed.

The second consequence is the dangerous one: if #215 merged first, the
component key would have read as COVERED while helmrelease.yaml still ran
2026.8.3 — a false negative in the CRACK detector, whose zero is only a safety
property if this mapping is sound.

Run: python3 runbooks/tests/test-coverage-renovate-pr-attribution.py
"""

from __future__ import annotations

import importlib.util
import re
import tempfile
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


# The two live PR rows, in the snapshot's own table shape and ascending order.
SNAPSHOT = """## Renovate PRs

| PR | Title | Type | Status |
|----|-------|------|--------|
| [#214](https://github.com/o/r/pull/214) | feat(container): update docker.io/cloudflare/cloudflared ( 2026.8.3 → 2026.9.0 ) | 🟡 MINOR | ✅ Ready |
| [#215](https://github.com/o/r/pull/215) | feat(mise): update aqua:cloudflare/cloudflared ( 2026.8.2 → 2026.9.0 ) | 🟡 MINOR | ✅ Ready |
| [#212](https://github.com/o/r/pull/212) | feat(github-release): update aqua:siderolabs/talos ( 1.13.10 → 1.14.1 ) | 🟡 MINOR | ✅ Ready |
"""

CONTAINER = {"component": "cloudflared", "namespace": "network", "kind": "image",
             "current": "2026.8.3", "target": "2026.9.0", "type": "minor",
             "image_repos": ["docker.io/cloudflare/cloudflared"]}
# The Talos NODE image: the version report carries no repository for it.
TALOS = {"component": "Talos Linux", "namespace": "external", "kind": "image",
         "current": "v1.13.10", "target": "v1.14.1", "type": "minor",
         "image_repos": []}


def with_snapshot(fn):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "version-check-current.md"
        p.write_text(SNAPSHOT)
        orig = cov.VERSION_MD
        cov.VERSION_MD = p
        try:
            return fn()
        finally:
            cov.VERSION_MD = orig


def main() -> int:
    print("test-coverage-renovate-pr-attribution")

    prs = with_snapshot(cov.parse_renovate_prs)

    # ── nothing is silently discarded ──────────────────────────────────
    all_nums = {r["number"] for recs in prs.values() for r in recs}
    check("every open PR survives parsing (no last-wins collapse)",
          all_nums == {"212", "214", "215"}, f"got {sorted(all_nums)}")
    check("the colliding basename keeps BOTH records, so the collision is "
          "visible instead of discarded",
          len({r["number"] for r in prs.get("cloudflared", [])}) == 2,
          f"got {prs.get('cloudflared')}")

    # ── THE defect: the container is attributed to the container's PR ──
    num, note = cov.renovate_pr_for(prs, CONTAINER, {"cloudflared"})
    check("the tunnel CONTAINER is attributed to #214, not the CLI pin #215",
          num == "214", f"got {num!r} ({note})")

    # ── the CLI pin never covers an image ──────────────────────────────
    num, note = cov.renovate_pr_for(prs, TALOS, {"talos linux", "talos"})
    check("an `aqua:` CLI pin does NOT cover the Talos NODE image "
          "(the F-9a58f400 shape)", num is None, f"got {num!r}")
    check("...and the mismatch is REPORTED, not silent",
          "DIFFERENT artifact" in note and "212" in note, f"note={note!r}")

    # ── an image whose repo we could not resolve is never 'covered' ────
    norepo = dict(CONTAINER, image_repos=[])
    num, _ = cov.renovate_pr_for(prs, norepo, {"cloudflared"})
    check("an image with NO resolved repository is never claimed by a PR "
          "(unattributable is not covered)", num is None, f"got {num!r}")

    # ── ambiguity is surfaced, never resolved by picking one ───────────
    twins = {"app": [{"number": "300", "dep": "ghcr.io/o/app", "manager": None,
                      "path": "ghcr.io/o/app"},
                     {"number": "301", "dep": "docker.io/o/app", "manager": None,
                      "path": "docker.io/o/app"}]}
    it = {"component": "app", "kind": "image", "current": "1.0", "target": "1.1",
          "type": "minor", "image_repos": ["ghcr.io/o/app", "docker.io/o/app"]}
    num, note = cov.renovate_pr_for(twins, it, {"app"})
    check("two PRs both naming this artifact -> AMBIGUOUS, no PR claimed",
          num is None and "AMBIGUOUS" in note, f"got {num!r} {note!r}")
    check("...and the note names both PRs", "300" in note and "301" in note)

    # ── backwards compatibility with the legacy {name: number} shape ───
    num, _ = cov.renovate_pr_for({"cloudflared": "215"}, CONTAINER, {"cloudflared"})
    check("a legacy {name: number} map still attributes by name "
          "(hand-built fixtures keep working)", num == "215", f"got {num!r}")

    # ── a chart PR still matches by name ───────────────────────────────
    chart_prs = {"grafana": [{"number": "400", "dep": "grafana", "manager": None,
                              "path": "grafana"}]}
    chart = {"component": "grafana", "kind": "chart", "current": "13.2.1",
             "target": "13.2.2", "type": "patch"}
    num, _ = cov.renovate_pr_for(chart_prs, chart, {"grafana"})
    check("a CHART PR still matches on the name (charts have no image repo)",
          num == "400", f"got {num!r}")

    # ── end to end: the lane reason names the right artifact ───────────
    cov._release_tags_between = lambda *a, **k: ([], "stubbed")
    cov._prerelease_digest_twin = lambda *a, **k: (None, "")
    lane, reason, _ = cov.assign_lane(CONTAINER, {"deny": []}, prs, [])
    check("assign_lane names PR #214 for the container", lane == "AUTO"
          and reason == "Renovate PR #214", f"{lane}: {reason}")

    # ── COMMISSIONING: the pre-fix parser must fail the key assertion ──
    def straw_basename_lastwins(text):
        """The pre-fix parser, transcribed: one PR per dep basename."""
        out = {}
        for line in text.splitlines():
            m = re.search(r"\[#(\d+)\].*?update\s+(.+?)\s*\(", line)
            if m:
                out[m.group(2).strip().split("/")[-1].lower()] = m.group(1)
        return out

    old = straw_basename_lastwins(SNAPSHOT)
    check("commissioning: the PRE-FIX parser is caught — it maps `cloudflared` "
          "to the CLI pin #215 and loses #214 entirely",
          old.get("cloudflared") == "215" and "214" not in old.values(),
          f"straw produced {old}")
    num, _ = cov.renovate_pr_for(old, CONTAINER, {"cloudflared"})
    check("commissioning: fed the pre-fix map, attribution IS the wrong PR — so "
          "this file discriminates the fix from the bug", num == "215",
          f"got {num!r}")

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
