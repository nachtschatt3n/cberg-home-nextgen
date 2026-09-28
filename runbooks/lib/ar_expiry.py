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

  * ABSENT means NO DEADLINE *for suppression* — a hand-inserted row must not
    flip a class of findings at once. It is no longer a sanctioned state,
    though: since F-d5486ff1 (2026-09-28) every AR must carry an expiry, the
    CLI cannot create or clear one without, and `risk lint` / the sweep board
    name any that lack it. (Until then condition-based acceptances were left
    open-ended; that is withdrawn — the condition is re-checked on a date.)
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

Consumers: runbooks/sweep-run.py (the suppressor + the auto-disable),
runbooks/security-check.py (the second, emit-time suppressor),
runbooks/policy-cli.py (`risk add/edit/renew/lint`), runbooks/render-board.py
and runbooks/ops-retro.py (the 14-day renewal warning).
Tested by runbooks/tests/test-ar-expiry-gate.py and
runbooks/tests/test-ar-systematic-expiry.py.
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


# ---------------------------------------------------------------------------
# Systematic expiry (F-d5486ff1, operator request 2026-09-28)
# ---------------------------------------------------------------------------
# The gate above made a RECORDED deadline binding, but left three holes the
# operator named: most ARs recorded no deadline at all (so nothing ever came
# back up for review), an expired AR stayed `enabled=true` in the register
# (the register kept claiming a decision nobody had renewed), and nothing
# warned BEFORE the date, so a lapse always arrived as a surprise.
#
# The contract now:
#   * every AR carries `accepted_at` (the column, NOT NULL — the "created"
#     date) and `metadata.expires_at`;
#   * `risk add` / `risk edit --expires` / `risk renew` refuse a date further
#     out than MAX_HORIZON_DAYS, and refuse clearing it — an acceptance is
#     re-decided at least twice a year, whatever its nature;
#   * `auto_disable_expired()` runs every sweep (sweep-run.py, before AR
#     suppression) and flips an expired AR to `enabled=false`, recording WHY
#     in metadata — so the register tells the truth and the findings it masked
#     re-surface at their own severity on the same pass;
#   * `expiry_report()` names ARs expiring within WARN_DAYS (and those
#     auto-disabled recently) for the sweep board and the weekly ops retro.
#
# Absence is still "no deadline" for SUPPRESSION (is_expired(None) is False):
# a row inserted by hand must not flip a whole class of findings at once. It is
# reported instead (`missing` in expiry_report, `risk lint`), because since
# 2026-09-28 no sanctioned path can produce it.

DEFAULT_HORIZON_DAYS = 90
MAX_HORIZON_DAYS = 180
WARN_DAYS = 14

DISABLED_REASON_KEY = "disabled_reason"
DISABLED_AT_KEY = "disabled_at"
DISABLED_BY_KEY = "disabled_by"
EXPIRED_REASON = "expired"


def horizon_problem(day, today: "_dt.date | None" = None,
                    max_days: int = MAX_HORIZON_DAYS) -> "str | None":
    """Why `day` is not an acceptable new expiry, or None if it is.

    Past dates are refused by the callers separately (they have an explicit
    override for recording an already-lapsed decision); this is the ceiling."""
    today = today or _dt.date.today()
    limit = today + _dt.timedelta(days=max_days)
    if day > limit:
        return (f"--expires {day} is {(day - today).days} days out; the maximum "
                f"horizon is {max_days} days ({limit}). An acceptance is "
                f"re-decided at least that often — renew it when it comes up.")
    return None


def default_expiry(today: "_dt.date | None" = None,
                   days: int = DEFAULT_HORIZON_DAYS) -> "_dt.date":
    return (today or _dt.date.today()) + _dt.timedelta(days=days)


def days_left(value, today: "_dt.date | None" = None) -> "int | None":
    """Days until the last day in force (0 = expires today), or None when the
    value is absent or unreadable."""
    day = as_date(value)
    if day is None:
        return None
    return (day - (today or _dt.date.today())).days


def _meta(m) -> dict:
    if isinstance(m, dict):
        return m
    if isinstance(m, str) and m.strip():
        import json
        try:
            v = json.loads(m)
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}
    return {}


def expiry_report(rows, today: "_dt.date | None" = None,
                  warn_days: int = WARN_DAYS, recent_days: int = 7) -> dict:
    """Classify the register for operator-facing surfaces. Pure.

    rows: iterable of (ar_id, enabled, description, metadata) — metadata as a
    dict or JSON text.

    Returns {"expiring": [...], "expired_enabled": [...], "missing": [...],
             "recently_disabled": [...]}:
      expiring          enabled, expires within `warn_days` (inclusive, today=0)
      expired_enabled   enabled but already past — the auto-disable has not run
                        yet (or failed): the board must say so, not hide it
      missing           enabled with no expires_at recorded at all
      recently_disabled auto-disabled for expiry within `recent_days`
    """
    today = today or _dt.date.today()
    out = {"expiring": [], "expired_enabled": [], "missing": [],
           "recently_disabled": []}
    for ar_id, enabled, desc, meta in rows:
        m = _meta(meta)
        exp = m.get(EXPIRY_KEY)
        if enabled:
            if exp is None:
                out["missing"].append({"ar_id": ar_id, "description": desc})
            elif is_expired(exp, today):
                out["expired_enabled"].append(
                    {"ar_id": ar_id, "expires": exp, "description": desc})
            else:
                left = days_left(exp, today)
                if left is not None and left <= warn_days:
                    out["expiring"].append({"ar_id": ar_id, "expires": exp,
                                            "days_left": left, "description": desc})
        elif m.get(DISABLED_REASON_KEY) == EXPIRED_REASON:
            at = as_date(str(m.get(DISABLED_AT_KEY) or "")[:10])
            if at is not None and (today - at).days <= recent_days:
                out["recently_disabled"].append(
                    {"ar_id": ar_id, "expires": exp, "disabled_at": at.isoformat(),
                     "description": desc})
    for k in out:
        out[k].sort(key=lambda r: (r.get("days_left", 0), r["ar_id"]))
    return out


def select_expired(rows, today: "_dt.date | None" = None) -> list:
    """(ar_id, expires) for the ENABLED rows that have lapsed. Pure — the
    decision the auto-disable acts on, testable without a database.

    rows: iterable of (ar_id, expires_value)."""
    return [(a, e) for a, e in rows if is_expired(e, today)]


def auto_disable_expired(conn, today: "_dt.date | None" = None,
                         actor: str = "sweep-run") -> list:
    """Disable every enabled AR whose expiry has passed. Returns the
    [(ar_id, expires)] it disabled. Commits.

    The comparison is Python (select_expired) for the reasons in the module
    docstring; the UPDATE is per ar_id and re-checks `enabled = true`, so two
    concurrent sweeps cannot double-stamp a row. Nothing is deleted: the row,
    its justification and its history stay in the register with
    disabled_reason='expired', and `policy-cli risk renew` brings it back as a
    conscious decision."""
    import json
    today = today or _dt.date.today()
    with conn.cursor() as cur:
        cur.execute("SELECT ar_id, " + EXPIRY_SELECT + " FROM accepted_risks "
                    "WHERE enabled = true AND status = 'accepted' ORDER BY ar_id")
        lapsed = select_expired([(r[0], r[1]) for r in cur.fetchall()], today)
        done = []
        for ar_id, exp in lapsed:
            stamp = {DISABLED_REASON_KEY: EXPIRED_REASON,
                     DISABLED_AT_KEY: today.isoformat(),
                     DISABLED_BY_KEY: actor}
            cur.execute(
                "UPDATE accepted_risks SET enabled = false, "
                "metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb "
                "WHERE ar_id = %s AND enabled = true",
                (json.dumps(stamp), ar_id))
            if cur.rowcount:
                done.append((ar_id, exp))
    conn.commit()
    return done
