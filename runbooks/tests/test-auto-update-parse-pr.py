"""parse_pr: real Renovate titles (fetched with `gh pr view N --json title,labels`
on 2026-11-25) must be classified by their REAL update type, never "unparseable".

The 14 titles the old parser could not read: majors with `!`, `Update` capitalised,
grouped PRs, titles with no version span, `docker tag to vX`, multi-word deps.
Same-tag digest rebuilds are typed `digest`, not `unknown`.

Hermetic. Run:  python3 runbooks/tests/test-auto-update-parse-pr.py
"""
from __future__ import annotations
import importlib.util, os, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
spec = importlib.util.spec_from_file_location("au_parse", REPO / "runbooks/auto-update.py")
au = importlib.util.module_from_spec(spec)
spec.loader.exec_module(au)

FAILS = []
def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok: FAILS.append(name)

def pr(title, *labels):
    return {"title": title, "labels": [{"name": l} for l in labels]}

# (number, title, labels, dep, cur, new, update_type, flags)
REAL = [
 (576, "feat(container)!: Update postgres", ["type/major"], "postgres", "?", "?", "major", {"versionless": True}),
 (575, "feat(container)!: Update docker.io/library/postgres ( 18.7 → 19.0 )", ["type/major"], "docker.io/library/postgres", "18.7", "19.0", "major", {}),
 (574, "feat(container)!: Update adguard/adguardhome ( v0.107.80 → v1.0.0 )", ["type/major"], "adguard/adguardhome", "v0.107.80", "v1.0.0", "major", {}),
 (522, "feat(container)!: Update node ( 24.22.3 → 26.13.1 )", ["type/major"], "node", "24.22.3", "26.13.1", "major", {}),
 (514, "chore(deps): update n8nio/n8n docker tag to v2.49.6", ["type/minor"], "n8nio/n8n", "?", "v2.49.6", "minor", {}),
 (503, "feat(github-release): update flate group (minor)", ["type/minor"], "flate group", "?", "?", "minor", {"grouped": True, "versionless": True}),
 (501, "feat(container)!: Update kube-prometheus-stack ( 92.22.0 → 93.10.1 )", ["type/major"], "kube-prometheus-stack", "92.22.0", "93.10.1", "major", {}),
 (480, "feat(helm)!: Update open-webui ( 17.5.0 → 18.4.0 )", ["type/major"], "open-webui", "17.5.0", "18.4.0", "major", {}),
 (297, "feat(github-release)!: Update aqua:helmfile/helmfile ( 0.171.0 → 1.8.5 )", ["type/major"], "aqua:helmfile/helmfile", "0.171.0", "1.8.5", "major", {}),
 (296, "feat(github-release)!: Update aqua:helm/helm ( 3.22.1 → 4.3.2 )", ["type/major"], "aqua:helm/helm", "3.22.1", "4.3.2", "major", {}),
 (282, "feat(container)!: Update ghcr.io/immich-app/postgres ( 14 → 16 )", ["type/major"], "ghcr.io/immich-app/postgres", "14", "16", "major", {}),
 (271, "feat(github-release): update python", ["type/minor"], "python", "?", "?", "minor", {"versionless": True}),
 (253, "chore(deps): update terraform cloudflare to v5.29.0", ["type/minor"], "terraform cloudflare", "?", "v5.29.0", "minor", {}),
 (227, "chore(container): update postgres", [], "postgres", "?", "?", "unknown", {"versionless": True}),
 # not in the 14, but the shapes around them
 (577, "feat(container): update flux operator group ( 0.62.1 → 0.63.1 )", ["type/minor"], "flux operator group", "0.62.1", "0.63.1", "minor", {"grouped": True}),
 (593, "chore(container): update python ( 65a65fc → 63bb298 )", [], "python", "65a65fc", "63bb298", "digest", {"digest_only": True}),
 (559, "chore(container): update docker.io/library/postgres ( b6972e1 → 0115267 )", [], "docker.io/library/postgres", "b6972e1", "0115267", "digest", {"digest_only": True}),
 (504, "feat(container): update postgres ( 18.6 → 18.7 )", ["type/major"], "postgres", "18.6", "18.7", "major", {}),
 (583, "fix(container): update ghcr.io/home-assistant/home-assistant ( 2026.11.2 → 2026.11.3 )", ["type/patch"], "ghcr.io/home-assistant/home-assistant", "2026.11.2", "2026.11.3", "patch", {}),
]
for n, title, labels, dep, cur, new, ut, flags in REAL:
    r = au.parse_pr(pr(title, *labels))
    ok = "parse_error" not in r and (r["dep"], r["cur"], r["new"], r["update_type"]) == (dep, cur, new, ut)
    for k, v in flags.items():
        ok = ok and r.get(k) == v
    check(f"#{n} {title[:60]}", ok, r)

# a `!` outranks a lower label: the more dangerous reading wins
check("bang beats a minor label", au.parse_pr(pr("feat(container)!: Update x ( 1.2 → 1.3 )", "type/minor"))["update_type"] == "major")
# all-numeric 7-char pairs are not digests (build numbers)
r = au.parse_pr(pr("chore: update thing ( 1234567 → 1234568 )"))
check("numeric build numbers are NOT a digest pair", r.get("digest_only") is False and r["update_type"] == "unknown", r)
# no dependency at all => the ONLY parse_error left
check("title with no `update <dep>` clause is a parse_error", "parse_error" in au.parse_pr(pr("Merge branch main")))

# classify() routes: majors => PLAN with a major reason; grouped => PLAN; none is 'unparseable'
POL = {"deny": [], "digest_bumps": {"stateless": ["python"], "stateful": [{"match": "*postgres*", "reason": "pg"}]}}
class Chk: pass
for n, title, labels, *_ in REAL:
    c = au.classify({"number": n, "title": title, "labels": [{"name": l} for l in labels],
                     "isDraft": False}, POL, Chk())
    if n in (576, 575, 574, 522, 501, 480, 297, 296, 282, 504):
        check(f"#{n} classify -> PLAN lane, reason names MAJOR",
              c["verdict"] == "hold" and c["lane"] == "PLAN" and "MAJOR" in c["reason"], c)
    if n in (577, 503):
        check(f"#{n} grouped -> PLAN, not unparseable", c["lane"] == "PLAN" and c["gate"] == "grouped", c)
    check(f"#{n} never held as 'unparseable'", "not in `update" not in c["reason"], c["reason"])

# digest classification
check("python digest = stateless", au.digest_class(POL, "docker.io/library/python")[0] == "stateless")
check("exact match: python-tools is NOT stateless", au.digest_class(POL, "ghcr.io/x/python-tools")[0] == "unclassified")
check("postgres digest = stateful", au.digest_class(POL, "docker.io/library/postgres")[0] == "stateful")
c = au.classify({"number": 559, "title": "chore(container): update docker.io/library/postgres ( b6972e1 → 0115267 )",
                 "labels": [], "isDraft": False}, POL, Chk())
check("stateful digest -> PLAN with precise reason", c["lane"] == "PLAN" and "stateful" in c["reason"] and "unknown" not in c["reason"], c)

print("\nFAILED: %d" % len(FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)
