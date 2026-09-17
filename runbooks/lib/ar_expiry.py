"""Expiry semantics for accepted risks — ONE definition, three consumers.

An AR may carry an operator-stated deadline in `metadata.expires_at`
('YYYY-MM-DD' = the LAST day it is in force). Past it the AR stops suppressing
and the findings it masked re-surface at their own severity.

Why (F-da238139): AR-042 said "accept until 2026-09-03" in justification PROSE.
Nothing parsed that sentence — `_apply_ar_suppression` filtered on
status/enabled only — so it masked a genuinely flat cell for 14 days past the
operator's own deadline. A deadline only a human can read is a comment, not
policy.

THREE RULES, ALL LOAD-BEARING:

  * ABSENT means NO DEADLINE and stays silent forever. Condition-based
    acceptances (AR-053/054 "until upstream ships a fix") and permanent
    decisions must not be nagged.
  * UNPARSEABLE means EXPIRED. A value we cannot read stops the suppression
    rather than extending it: un-suppressing is noisy and self-announcing,
    silently continuing to suppress is how this bug class hides.
  * THE COMPARISON IS PYTHON, NOT SQL. An earlier draft put the rule in a SQL
    fragment. Two things went wrong and both are why this module has no SQL:
      1. `(metadata->>'expires_at')::date` RAISES on a value that passes a
         YYYY-MM-DD regex but is not a date. Measured live against
         PostgreSQL 16: '2026-13-45' and '2026-02-30' both raise
         DatetimeFieldOverflow. No month/day regex can express calendar
         validity. That exception propagates to
         `_apply_ar_suppression`'s `except Exception: return 0` (the cycle
         applies ZERO suppression) and to security-check.py's
         `_POLICY_LOAD_FAILED` (the whole audit prints ABORT and exits 2).
      2. The regression suite could not execute SQL, so a 30-day silent grace,
         an inverted comparison and a `->` / `->>` typo ALL passed it. A
         predicate no test can run is a predicate with no test.
    115 rows is not a query-planner problem. Filter in Python, where the tests
    can see it.

Consumers: runbooks/sweep-run.py (the suppressor), runbooks/security-check.py
(the second, emit-time suppressor), runbooks/policy-cli.py (`risk lint`).
Tested by runbooks/tests/test-ar-expiry-gate.py.
"""

from __future__ import annotations

import datetime as _dt
import re

EXPIRY_KEY = "expires_at"

# The column expression every consumer selects, so the three stay in step.
EXPIRY_SELECT = "metadata->>'expires_at'"

# EXACT shape, deliberately not whitespace-tolerant. The CLI normalises on
# write, so a padded or malformed value can only arrive via hand-written SQL —
# and is then unparseable, i.e. expired, i.e. visible.
_RE_EXPIRY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def as_date(value) -> "_dt.date | None":
    """The expiry as a date, or None if absent / not exactly YYYY-MM-DD /
    not a real calendar date (2026-02-30)."""
    if value is None:
        return None
    if isinstance(value, _dt.date):
        return value
    text = str(value)
    if not _RE_EXPIRY.match(text):
        return None
    try:
        return _dt.date.fromisoformat(text)
    except ValueError:          # e.g. 2026-13-45, 2026-02-30
        return None


def is_expired(value, today: "_dt.date | None" = None) -> bool:
    """Has it lapsed?

    absent (None)        -> False   no deadline was ever recorded
    future / today       -> False   inclusive: "accept until the 3rd" holds ON the 3rd
    past                 -> True
    anything unreadable  -> True    ('', 'whenever', '2026-02-30', ' 2026-09-03 ')

    Note the asymmetry: only a literal absence means "no deadline". An empty
    string is a RECORDED value we cannot read, and fails toward visibility.
    """
    if value is None:
        return False
    day = as_date(value)
    if day is None:
        return True
    return day < (today or _dt.date.today())


def lapse_note(ar_id: str, value, today: "_dt.date | None" = None) -> "str | None":
    """One operator-facing sentence for an AR that has stopped suppressing, or
    None if it has not. Quotes a readable date as a date and an unreadable
    value verbatim — the draft printed nothing at all for the unreadable case,
    which is the silent half of the bug being fixed."""
    if not is_expired(value, today):
        return None
    day = as_date(value)
    what = (f"EXPIRED {day}" if day is not None
            else f"has an UNREADABLE expiry {str(value)!r}, treated as EXPIRED")
    return (f"==> AR-suppression: {ar_id} {what} — its suppression has LAPSED. "
            f"Findings it masked will re-surface at their own severity; review "
            f"with `runbooks/policy-cli.py risk lint`")


def parse_expiry(value):
    """Validate an operator-supplied --expires. Returns a date, or None for the
    clearing words. Raises ValueError otherwise, so a typo can never be stored
    as an unreadable deadline."""
    text = "" if value is None else str(value).strip()
    if text.lower() in ("", "none", "never", "clear"):
        return None
    day = as_date(text)
    if day is None:
        raise ValueError(
            f"--expires {value!r} is not a date. Use YYYY-MM-DD (the last day "
            f"the acceptance is in force), or 'none' to clear it.")
    return day


# A deadline written in PROSE, which this gate cannot enforce. This is the
# control against the gate being blind: it binds only on a recorded
# metadata.expires_at, so without this an AR whose deadline lives in its
# justification lapses in exactly the way AR-042 did, unseen.
#
# Anchored on a deadline PHRASE that is FOLLOWED BY A DATE, which is what makes
# it usable. Measured over the 105 live enabled ARs on 2026-09-17:
#   * this needle                       ->  6 ARs (042, 050, 051, 058, 059, 108)
#     — every one a genuine unenforced deadline, on inspection;
#   * "any past date in the justification" -> 61 ARs, ~58 of them merely quoting
#     a provenance date ("Verified 2026-08-19"): an alert nobody would read,
#     which is why the first draft gave up on prose entirely;
#   * the phrase WITHOUT requiring a date -> 12 sentences across 10 ARs,
#     wrongly including the condition-based acceptances AR-053/054/111/113
#     ("Accepted until a fixed tag is published", "lapse trigger"), which are
#     legitimately open-ended and must NOT be nagged.
# Both over- and under-inclusive alternatives are pinned in the test.
_RE_PROSE_DEADLINE = re.compile(
    r"(?i)(accept(?:ed)?[ -]until|revisit after(?:[ -]window)?|re-?view by|"
    r"re-?review by)[^.\n]{0,40}?(\d{4}-\d{2}-\d{2})")


def prose_deadline(justification: str):
    """(phrase, 'YYYY-MM-DD') if the justification states a DATED deadline that
    only a human can read, else None."""
    m = _RE_PROSE_DEADLINE.search(justification or "")
    return (m.group(1), m.group(2)) if m else None
