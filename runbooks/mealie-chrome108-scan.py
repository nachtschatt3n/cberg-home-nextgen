#!/usr/bin/env python3
"""Scan a Mealie web frontend for JS features newer than Chrome 108.

Why: the Samsung Family Hub fridge runs Chrome 108. Mealie v3.30 (Vuetify 4.3)
calls Array.prototype.toSorted (Chrome 110) unguarded, which blanks every page.
We keep the fridge working with an Envoy Lua polyfill
(kubernetes/apps/office/mealie/app/envoyextensionpolicy.yaml) instead of a fork;
upstream declined to fix it (mealie-recipes/mealie#9178). This script is the
guard: run it against a candidate Mealie version BEFORE bumping, so a new
unpolyfilled API is found before the fridge goes blank.

Usage:  runbooks/mealie-chrome108-scan.py https://mealie.example   # live instance
Exit 0 = nothing beyond what the polyfill covers (or what the baseline accepts).
Exit 1 = new candidate API: extend the polyfill, or fork, before bumping.
Exit 2 = scan could not read the bundle (never treat as a pass).

It is a static regex scan, so it over-reports (feature-detected uses hit too).
Judge each new hit; add reviewed ones to runbooks/mealie-chrome108-baseline.json.
See docs/sops/mealie-family-hub-compat.md.
"""
import json, re, ssl, sys, urllib.request
from pathlib import Path

# feature -> (regex, first Chrome version, covered by our polyfill?)
FEATURES = {
    "Array toSorted/toReversed/toSpliced/with": (r"\.(toSorted|toReversed|toSpliced)\(|\.with\(", 110, True),
    "Object.groupBy / Map.groupBy": (r"(Object|Map)\.groupBy", 117, False),
    "Promise.withResolvers": (r"withResolvers", 119, False),
    "Set methods (union etc.)": (r"\.(union|intersection|difference|symmetricDifference|isSubsetOf|isSupersetOf|isDisjointFrom)\(", 122, False),
    "Array.fromAsync": (r"fromAsync", 121, False),
    "URL.canParse": (r"URL\.canParse", 120, False),
    "AbortSignal.any": (r"AbortSignal\.any", 116, False),
    "String isWellFormed/toWellFormed": (r"\.(isWellFormed|toWellFormed)\(", 111, False),
    "Array findLast": (r"\.findLast(Index)?\(", 97, None),  # <=108: informational, skipped
    "RegExp v flag": (r"new RegExp\([^)]*,\s*[\"'][a-z]*v[a-z]*[\"']", 112, False),
    "Intl.DurationFormat": (r"Intl\.DurationFormat", 129, False),
    "Iterator helpers": (r"Iterator\.from|\.(flatMap|take|drop)\(\s*\)", 122, False),
}
CHROME = 108
BASELINE = Path(__file__).with_name("mealie-chrome108-baseline.json")
ctx = ssl.create_default_context()


def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, context=ctx, timeout=30).read().decode("utf8", "replace")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    base = sys.argv[1].rstrip("/")
    try:
        html = get(base + "/login/")
    except Exception as e:
        print(f"ERROR: cannot read {base}/login/: {e}")
        return 2
    queue = re.findall(r"/_nuxt/[A-Za-z0-9_.\-]+\.js", html)
    seen = {}
    while queue and len(seen) < 300:
        p = queue.pop()
        if p in seen:
            continue
        try:
            seen[p] = get(base + p)
        except Exception:
            seen[p] = None
            continue
        for m in re.findall(r"[\"'`\(]\.?/?([A-Za-z0-9_\-]{6,}\.js)", seen[p]):
            queue.append("/_nuxt/" + m)
    ok = {p: t for p, t in seen.items() if t}
    if len(ok) < 10:  # control: a real Mealie bundle has dozens of chunks
        print(f"ERROR: only {len(ok)} JS chunks readable - scan is blind, not clean")
        return 2
    print(f"scanned {len(ok)} chunks, {sum(map(len, ok.values()))} bytes")
    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    new = 0
    for name, (rx, since, covered) in FEATURES.items():
        if covered is None or since <= CHROME:
            continue
        hits = sorted(p.rsplit("/", 1)[-1] for p, t in ok.items() if re.search(rx, t))
        if not hits:
            continue
        if covered:
            print(f"  covered by polyfill: {name} (Chrome {since}) in {len(hits)} chunks")
            continue
        accepted = name in baseline
        tag = "baseline" if accepted else "NEW"
        print(f"  {tag}: {name} (Chrome {since}) in {len(hits)} chunks e.g. {hits[:3]}")
        new += 0 if accepted else 1
    print("RESULT:", "NEW candidates - review before bumping" if new else "no new unpolyfilled APIs")
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
