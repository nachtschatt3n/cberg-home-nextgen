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

TWO TIERS. `PATTERNS` (via `scan`) is the BLOCKING tier: high-confidence
shapes, measured at a near-zero false-positive rate over the tracked tree.
`WARN_PATTERNS` (via `scan_warn`) is ADVISORY: shapes that catch real
disclosures but also fire on legitimate supply-chain prose, so they nag
instead of gating. A hook that blocks honest commits gets bypassed with
--no-verify, and a bypassed hook protects nothing -- so anything with a
material false-positive rate belongs in the warn tier, not the block tier.

ACQUITTALS. Some patterns carry a third element: a context regex that, when
found in a +/-80 char window around the match, ACQUITS it. Two things need
acquitting, both established by measurement rather than guesswork:
  * closed-gap phrasing -- "clears the last fixable CRITICAL" states a gap
    that is now SHUT, which SOP 2.1 lists as publishable;
  * scanner-tooling talk -- a commit editing security-check.py necessarily
    names the vocabulary it matches on, and cannot be written otherwise.

WHY THE RESIDUAL TIER EXISTS (2026-08-18). Every rule here originally needed
a NUMBER, a QUANTIFIER or an IMAGE_REF to fire. A purely QUALITATIVE residual
claim -- "does not close F-xxxxxxxx", "the finding stays open", "ships it
unchanged" -- carried none of those and sailed through, and one reached a
public commit body. The residual rules below therefore key on the CLAIM
SHAPE, not on a count.

This hook is a BACKSTOP against careless disclosure, never a substitute for
the author's judgement. Three structurally distinct false negatives were
found in it in a single evening (staged-diff blindness; prose-without-tokens
in plan files; qualitative-residual-without-numbers). Assume the next one
exists and has not been found yet: think before you commit, do not delegate
the boundary to this file.
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

# A component name followed by a BARE semver ("affine 0.27.4", "sure v0.7.3").
# IMAGE_REF proper requires a colon, so a bare version adjacent to a component
# name never matched it. Measured over 4823 commit messages this fires on a lot
# of ordinary "bump 1.2.3 -> 1.2.4" prose -- which SOP 2.1 lists as publishable
# supply-chain fact -- so it drives the WARN tier only. Do not promote it to
# PATTERNS without re-measuring; it was 30 of 39 new hits on its own.
BARE_VERSIONED_COMPONENT = r"\b[a-z][a-z0-9._-]{2,}[\s@]+v?\d+\.\d+\.\d+(?![\w.])"

# Context regexes that ACQUIT an otherwise-matching residual rule.
# "clears the last fixable CRITICAL" / "no fixable criticals left" describe a
# CLOSED gap; SOP 2.1 explicitly publishes those.
CLOSED_GAP = (
    r"\b(?:clears?|cleared|clearing|eliminat\w*|removes?|removed|resolves?|"
    r"resolved|closes?|closed|no|zero|none|last|left|0)\b"
)
# A commit that edits our own audit tooling has to name the vocabulary it
# matches on. Narrow on purpose: our script names plus explicit meta-words --
# NOT a general "scan"/"security" escape hatch, which would acquit real
# disclosures written by anyone who mentioned a sweep.
TOOLING_TALK = (
    r"(?:security-check\.py|check-all-versions|scan_staged_disclosure|"
    r"disclosure_patterns|auto-update\.py|coverage\.py|tally_trivy_report|"
    r"_newer_upstream_tag_exists|fix-availability|head-of-line|"
    r"false[- ]positive|kernel-header|fixture|unit[- ]test|regex|predicate|"
    r"vocabular\w*|suppress\w*|"
    # The conventional-commit SCOPE of our own audit tooling. A commit titled
    # `fix(security-check): ...` is by definition editing the scanner and has
    # to name the vocabulary it matches on. Bounded on purpose: acquittals
    # apply ONLY to the residual tier, so a real CVE ID or a non-zero count in
    # such a commit is still blocked by the un-acquitted rules above.
    r"\((?:security|security-check|version-check|sweep|maintenance)\))"
)

# Acquits the negated-closure rules. "does not reopen a closed finding" and
# "does not clear the LAST fixable critical" both put a negation next to a
# closure verb while asserting the exact OPPOSITE of a residual — that a gap
# is shut. Without this the rule reads the grammar and misses the meaning.
REOPEN_OR_CLOSED = (
    r"(?:\breopen\w*|\bclosed\b\s+(?:finding|issue|gap)|"
    + CLOSED_GAP + r"\s+(?:the\s+)?(?:last|final))"
)

# Anchors for the residual rules: a TRACKED FINDING or an unambiguous
# vulnerability word. Deliberately NOT bare SEV -- "High error count" is
# ordinary ops prose and matched SEV, which produced the only R1 false
# positive in the whole history sweep.
FINDING_ANCHOR = r"(?:F-[0-9a-f]{8}|\bfinding\b|\badvisor(?:y|ies)\b|\bcves?\b|\bvulnerabilit\w*)"

# Negation, spelled every way English actually spells it. The first draft
# covered only "does not"-style auxiliaries and missed BOTH contractions
# ("won't clear") and the passive ("is not closed by this change") — the
# passive is the more dangerous omission, because it is how a residual claim
# gets written when the author is trying to sound neutral.
NEG = (
    r"(?:(?:does|do|did|will|would|can|could|is|are|was|were|has|have|had|"
    r"should|must)\s+not"
    r"|(?:wo|ca|do|does|did|would|could|is|are|was|were|has|have|had|should|"
    r"must)n[\u2019']?t"
    r"|cannot|fails?\s+to|failed\s+to)"
)
# Closure verbs incl. past participles, so the passive voice is reachable.
CLOSURE_VERB = (
    r"(?:close[sd]?|clear(?:s|ed)?|fix(?:es|ed)?|resolve[sd]?|"
    r"remediate[sd]?|address(?:es|ed)?|patch(?:es|ed)?|mitigate[sd]?)"
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

    # ── Residual-claim tier ────────────────────────────────────────────────
    # These key on the CLAIM SHAPE and require NO number, quantifier or image
    # ref. That is the whole point: the 2026-08-18 miss was a qualitative
    # residual claim, which every rule above is structurally blind to.
    (
        # "does not close F-xxxxxxxx", "won't clear the finding",
        # "cannot fix the advisory", "fails to resolve the CVE"
        NEG + r"\s+(?:\w+\s+){0,3}?" + CLOSURE_VERB + r"\b"
        r".{0,60}?" + FINDING_ANCHOR,
        "residual claim — negated closure of a tracked finding",
        REOPEN_OR_CLOSED,
    ),
    (
        FINDING_ANCHOR + r".{0,60}?" + NEG
        + r"\s+(?:\w+\s+){0,3}?" + CLOSURE_VERB + r"\b",
        "residual claim — negated closure of a tracked finding",
        REOPEN_OR_CLOSED,
    ),
    (
        # "the finding stays open", "F-xxxxxxxx remains open", "CVE is still open"
        r"(?:" + FINDING_ANCHOR + r"|\bissue\b|\bgap\b)"
        r"\W+(?:\w+\W+){0,5}?(?:stays?|remains?|is|are|still)\s+open\b",
        "residual claim — finding left open",
        None,
    ),
    (
        r"\b(?:stays?|remains?)\s+open\b\W+(?:\w+\W+){0,5}?" + FINDING_ANCHOR,
        "residual claim — finding left open",
        None,
    ),
    (
        # "fixable-CRITICAL driver", "fixable criticals" with NO count in front.
        # The fixed-width lookbehinds keep the counted forms out: "13 fixable"
        # is the counted rule's job, and "0 fixable"/"no fixable" state a CLOSED
        # gap that SOP 2.1 publishes.
        r"(?<!\d\s)(?<!no\s)(?<!zero\s)\bfixable[-\s]+" + VULN,
        "residual claim — scanner fix-availability vocabulary",
        CLOSED_GAP + r"\s+(?:\w+\s+){0,2}?fixable|" + TOOLING_TALK,
    ),
    (
        # "ships it unchanged", "upstream has not refreshed it" — next to a
        # vulnerability or the dependency said to carry it.
        r"(?:" + VULN + r"|\bdependenc\w*).{0,60}?"
        r"(?:\b(?:ships?|shipped|shipping|leaves?|left)\s+(?:\w+\s+){0,2}?unchanged\b"
        r"|\bnot\s+(?:been\s+)?(?:refreshed|rebuilt|bumped|updated)\b)",
        "residual claim — upstream has not shipped a fix",
        TOOLING_TALK,
    ),
]

# ── WARN tier ──────────────────────────────────────────────────────────────
# Real signal, but measured at a material false-positive rate against ordinary
# supply-chain prose, so these NAG and never gate. Promoting any of them means
# re-running the measurement in runbooks/tests/ and showing the FP rate first.
WARN_PATTERNS = [
    (
        BARE_VERSIONED_COMPONENT + r".{0,80}?" + VULN,
        "vulnerability state near a bare-versioned component",
        TOOLING_TALK,
    ),
    (
        VULN + r".{0,80}?" + BARE_VERSIONED_COMPONENT,
        "vulnerability state near a bare-versioned component",
        TOOLING_TALK,
    ),
]

def _compile(rules):
    """Normalise 2- and 3-tuple rules into (regex, label, acquittal_or_None)."""
    out = []
    for rule in rules:
        pat, label = rule[0], rule[1]
        acq = rule[2] if len(rule) > 2 else None
        out.append((re.compile(pat, re.IGNORECASE), label,
                    re.compile(acq, re.IGNORECASE) if acq else None))
    return out


_COMPILED3 = _compile(PATTERNS)
_COMPILED3_WARN = _compile(WARN_PATTERNS)

# Back-compat: historical callers unpack 2-tuples. Keep the old shape exported
# so an out-of-tree consumer does not break, but note it carries NO acquittal
# information — anything enforcing policy must go through scan()/scan_warn().
COMPILED = [(rx, label) for rx, label, _ in _COMPILED3]
COMPILED_WARN = [(rx, label) for rx, label, _ in _COMPILED3_WARN]

# `security_ref: F-xxxxxxxx` is the sanctioned reference form — a pointer, not
# a disclosure.
SECURITY_REF_LINE = re.compile(r"^\s*[-+#/*\s]*security_ref:\s*F-[0-9a-f]{8}\s*$",
                               re.IGNORECASE)


ACQUITTAL_WINDOW = 80


def _scan(text: str, rules) -> list[tuple[str, str, str]]:
    """Return [(excerpt, matched_text, label)] — one entry per distinct label.

    `text` should already be whitespace-normalized by the caller: commit bodies
    are hard-wrapped, so a multi-word phrase routinely straddles a line break
    and per-line matching would miss it by accident.

    A rule carrying an acquittal regex is skipped when that regex matches
    inside a +/-ACQUITTAL_WINDOW character window around the hit. The window is
    deliberately local: a closed-gap verb three sentences away says nothing
    about THIS claim. `finditer` is used rather than `search` so one acquitted
    occurrence does not mask a second, genuinely-offending one under the same
    rule.
    """
    out, seen = [], set()
    for rx, label, acquit in rules:
        if label in seen:
            continue
        for m in rx.finditer(text):
            if acquit is not None:
                lo = max(0, m.start() - ACQUITTAL_WINDOW)
                hi = min(len(text), m.end() + ACQUITTAL_WINDOW)
                if acquit.search(text[lo:hi]):
                    continue
            s = max(0, m.start() - 40)
            e = min(len(text), m.end() + 40)
            excerpt = ("\u2026" if s else "") + text[s:e] + ("\u2026" if e < len(text) else "")
            out.append((excerpt, m.group(0), label))
            seen.add(label)
            break
    return out


def scan(text: str) -> list[tuple[str, str, str]]:
    """BLOCKING tier — a hit here must stop the commit."""
    return _scan(text, _COMPILED3)


def scan_warn(text: str) -> list[tuple[str, str, str]]:
    """ADVISORY tier — a hit here is reported but must NEVER gate."""
    return _scan(text, _COMPILED3_WARN)
