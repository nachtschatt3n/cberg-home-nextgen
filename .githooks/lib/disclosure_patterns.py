"""Shared vulnerability-disclosure pattern library for the git hooks.

SINGLE SOURCE OF TRUTH. Both `.githooks/commit-msg` (commit messages) and
`.githooks/pre-commit` (staged added lines) import this. It used to live only
inside the commit-msg heredoc, which is why the pre-commit side had no
boundary matching at all — and why the same fixture defect shipped twice on
2026-08-18 before a human-run audit caught it. A second copy would drift; this
codebase has already been bitten by a duplicated predicate once tonight.

Policy: docs/sops/vulnerability-disclosure.md

The two-part test a pattern encodes: does this line say what is currently
UNFIXED, on a SPECIFIC service we run? Both halves -> not publishable.
"""

from __future__ import annotations

import re

# Severity tokens are guarded so ordinary hyphenated adjectives
# ("high-availability", "low-latency", "critical-path") never match.
# NB: the optional plural must sit INSIDE the lookahead's scope — i.e.
# `...s?(?![-\w])`, never `...(?![-\w])s?`. With the lookahead first,
# "criticals"/"highs" can never match (the trailing "s" is a word char and
# trips the lookahead), which silently defeats every counted-phrasing rule.
SEV = r"(?:critical|high|medium|low)s?(?![-\w])"
# "vulns" is included because the abbreviation is at least as common as the
# full word in practice, and omitting it left an accidental bypass.
# "will_not_fix" lives here rather than as a standalone reject: bare, it is
# legitimate tooling talk ("the parser should honour will_not_fix"), but tied
# to a count, a quantifier or a named image it states unfixed fleet state.
VULN = (
    r"(?:" + SEV + r"|vulns?\b|vulnerabilit\w*|advisor(?:y|ies)|cves?"
    r"|will[_ -]not[_ -]fix)"
)

# A literal 0 is explicitly NOT a disclosure — the SOP (§2.1) lists
# "post-rebuild: 0 fixable CRITICAL" as publishable, because it states a
# CLOSED gap. Only non-zero counts are blocked.
NONZERO = r"(?!0+\b)\d+"

# repo/name:tag, or name:semver — a concrete artifact we run.
IMAGE_REF = (
    r"(?:[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._/-]*:[a-zA-Z0-9][\w.-]*"
    r"|\b[a-z][a-z0-9-]{2,}:\d+\.\d+[\w.-]*)"
)

PATTERNS = [
    (
        r"\bCVE-\d{4}-\d{4,}\b",
        "CVE identifier",
    ),
    (
        r"\bGHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}\b",
        "GHSA advisory identifier",
    ),
    (
        # "13 fixable criticals", "clears 4 CVEs", "19 CRITICAL"
        r"\b" + NONZERO + r"\s+(?:\w+[- ]){0,2}?" + VULN,
        "counted vulnerability phrasing",
    ),
    (
        # "one critical remains", "most fixable criticals", "several CVEs".
        # "no"/"zero" are deliberately absent — those state a closed gap.
        r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|dozens|"
        r"several|multiple|most|some|few|many|handful|residual|remaining|"
        r"outstanding)\s+(?:\w+[- ]){0,2}?" + VULN,
        "quantified vulnerability phrasing",
    ),
    (
        r"\bvulnerable\s+to\b",
        "unfixed-vulnerability statement",
    ),
    (
        r"\bunpatched\b",
        "unfixed-vulnerability statement",
    ),
    (
        r"\bunfixed\b",
        "unfixed-vulnerability statement",
    ),
    (
        # "the remaining issues have no upstream fix" — a paraphrase that says
        # exactly what the scanner vocabulary would have said.
        r"\bno\s+(?:\w+\s+){0,2}?upstream\s+fix\b",
        "unfixed-vulnerability statement",
    ),
    (
        r"\bexploitab\w*\b",
        "exploitability detail",
    ),
    (
        r"\b(?:zero|0)[- ]day\b",
        "exploitability detail",
    ),
    (
        r"\bscan surface\b",
        "residual-exposure statement",
    ),
    (
        # "... critical remains", "... CVE is still open"
        VULN + r"\W+(?:\w+\W+){0,4}?"
        r"(?:remains?|residual|outstanding|still\s+open)\b",
        "residual-exposure statement",
    ),
    (
        # "remains one critical", "residual fixable critical"
        r"\b(?:remains?|residual|outstanding)\W+(?:\w+\W+){0,4}?" + VULN,
        "residual-exposure statement",
    ),
    (
        # "postgres:17.11-bookworm carries 19 CRITICAL" — a vuln term tied to
        # a concrete artifact on the same line.
        IMAGE_REF + r".{0,80}?" + VULN,
        "vulnerability state tied to a named image",
    ),
    (
        VULN + r".{0,80}?" + IMAGE_REF,
        "vulnerability state tied to a named image",
    ),
]

COMPILED = [(re.compile(p, re.IGNORECASE), label) for p, label in PATTERNS]

# `security_ref: F-xxxxxxxx` is the sanctioned reference form — a pointer, not
# a disclosure.
SECURITY_REF_LINE = re.compile(r"^\s*[-+#/*\s]*security_ref:\s*F-[0-9a-f]{8}\s*$",
                               re.IGNORECASE)


def scan(text: str) -> list[tuple[str, str, str]]:
    """Return [(excerpt, matched_text, label)] — one entry per distinct label.

    `text` should already be whitespace-normalized by the caller: commit bodies
    are hard-wrapped, so a multi-word phrase routinely straddles a line break
    and per-line matching would miss it by accident.
    """
    out, seen = [], set()
    for rx, label in COMPILED:
        m = rx.search(text)
        if not m or label in seen:
            continue
        seen.add(label)
        s = max(0, m.start() - 40)
        e = min(len(text), m.end() + 40)
        excerpt = ("…" if s else "") + text[s:e] + ("…" if e < len(text) else "")
        out.append((excerpt, m.group(0), label))
    return out
