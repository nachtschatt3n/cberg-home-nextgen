"""fast_lane — the earned-autonomy and security fast lanes, shared by BOTH halves
of Step 0 (auto-update.py's PR lane and coverage.py's direct-bump lane).

WHY THIS EXISTS (operator-approved throughput program, item B, 2026-09-27).
"Patches aren't keeping pace." Three things were starving the unattended lane,
and none of them was a safety property the operator wanted:

  1. "Release notes unverified" routed a patch to PLAN even for a component that
     had landed cleanly, unattended, again and again. The unverified-never-AUTO
     rule (2026-09-22) is right for a component with NO history — nothing vouches
     for it — and wrong for one with a clean record: there, the track record is
     the evidence the missing notes would have been. So a component EARNS the
     right to land an unverified patch/minor: >= `min_green` green autonomy
     records and <= `max_reverts` reverts in the last `window_days`, from the
     `component_autonomy` table in sweep_history. A POSITIVE breaking or
     structural signal still holds — earning autonomy buys "unverified is OK",
     never "breaking is OK".
  2. A 48h cooldown on a PATCH. Patches now wait `minimum_release_age_hours_by_type.patch`
     (24h); minors keep the base 48h.
  3. A CVE fix waiting out the cooldown. A non-major bump whose CURRENT tag
     carries an open, non-accepted sweep_findings security row of the shape
     "`<repo>:<tag>`: N fixable CRITICAL|HIGH CVE(s) — newer upstream tag
     available" bypasses the cooldown. The finding id is carried with the item
     so the record and the retro can cite it (the id only — never CVE detail).

FAIL-SAFE, in every direction that matters:
  * No SWEEP_PG_DSN / table missing / query error  => track record UNVERIFIED
    => not earned (today's behaviour), and no security bypass (cooldown holds).
  * `earned_autonomy` absent from the policy  => the lane does not exist.
  * `security_cooldown_bypass` not literally true => no bypass.
An unreadable ledger must never read as permission.

A REVERT RESETS EARNED AUTONOMY TO ZERO: greens are counted only AFTER the most
recent revert, and any revert inside the window disqualifies outright. The
revert row itself is the reset record; nothing else has to remember it.
"""
from __future__ import annotations

import datetime as _dt
import os
import re

FAST_LANES = ("earned", "security", "normal")
OUTCOMES = ("green", "reverted")
SECURITY_PHRASE = "newer upstream tag available"
_SEC_TITLE = re.compile(r"^\s*`([^`\s]+)`\s*:\s*(.*)$")
_SEC_KIND = re.compile(r"fixable (CRITICAL|HIGH) CVE", re.IGNORECASE)


# ── policy knobs ─────────────────────────────────────────────────────────────
def cooldown_hours(policy, update_type) -> float:
    """G5 cooldown for this update_type. `minimum_release_age_hours` is the
    base (minor, and anything unlisted); `minimum_release_age_hours_by_type`
    may LOWER it per type. A malformed per-type value falls back to the base
    (the stricter reading) rather than to 0."""
    policy = policy or {}
    try:
        base = float(policy.get("minimum_release_age_hours") or 0)
    except (TypeError, ValueError):
        base = 48.0
    by_type = policy.get("minimum_release_age_hours_by_type") or {}
    if isinstance(by_type, dict) and update_type in by_type:
        try:
            v = float(by_type[update_type])
            if v >= 0:
                return v
        except (TypeError, ValueError):
            pass
    return base


def earned_policy(policy):
    """{min_green, window_days, max_reverts} or None when the lane is off."""
    ea = (policy or {}).get("earned_autonomy")
    if not isinstance(ea, dict):
        return None
    try:
        return {"min_green": int(ea.get("min_green", 3)),
                "window_days": int(ea.get("window_days", 90)),
                "max_reverts": int(ea.get("max_reverts", 0))}
    except (TypeError, ValueError):
        return None


def security_bypass_enabled(policy) -> bool:
    return (policy or {}).get("security_cooldown_bypass") is True


# ── normalisation ────────────────────────────────────────────────────────────
def norm_repo(repo) -> str:
    r = str(repo or "").strip().lower()
    r = re.sub(r"^[a-z]+://", "", r).split("@", 1)[0]
    for pre in ("index.docker.io/", "registry-1.docker.io/", "docker.io/"):
        if r.startswith(pre):
            r = r[len(pre):]
    if r.startswith("library/"):
        r = r[len("library/"):]
    return r


def norm_tag(tag) -> str:
    return str(tag or "").strip().split("@", 1)[0].lstrip("vV").lower()


def keys_for(component=None, repos=()) -> set:
    """The identities a component's track record is keyed on: the component
    name AND every image repository it mounts, normalised. A record matches if
    its component OR its dep is in this set — so a PR-lane apply (keyed on the
    image repo) and a direct-bump apply (keyed on the app) of the same thing
    both count, and a revert of either resets both."""
    out = set()
    if component:
        out.add(str(component).strip().lower())
    for r in repos or ():
        if r:
            out.add(norm_repo(r))
    out.discard("")
    return out


# ── the track record (pure) ─────────────────────────────────────────────────
def evaluate_track_record(rows, keys, now=None, window_days=90, min_green=3,
                          max_reverts=0):
    """(earned, summary) from rows [(component, dep, outcome, recorded_at)].

    Pure so the reset rule is tested directly. Greens count only AFTER the most
    recent revert (a revert resets to zero), and only inside the window."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    floor = now - _dt.timedelta(days=window_days)
    mine = []
    for comp, dep, outcome, at in rows or ():
        if at is None:
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=_dt.timezone.utc)
        if at < floor or at > now:
            continue
        if (str(comp or "").lower() in keys) or (norm_repo(dep) in keys if dep else False):
            mine.append((at, str(outcome)))
    reverts = [at for at, o in mine if o == "reverted"]
    last_revert = max(reverts) if reverts else None
    greens = [at for at, o in mine if o == "green" and (last_revert is None or at > last_revert)]
    summary = {"green": len(greens), "reverts": len(reverts),
               "window_days": window_days, "min_green": min_green,
               "last_revert": last_revert.isoformat() if last_revert else None}
    earned = len(reverts) <= max_reverts and len(greens) >= min_green
    return earned, summary


# ── the security bypass (pure) ───────────────────────────────────────────────
def parse_security_row(title):
    """(repo, tag, level) for an actionable 'newer upstream tag available'
    fixable CRITICAL/HIGH row, else None. `[AR-…]`-prefixed (accepted) titles
    never match: an accepted risk is by definition not being hurried."""
    t = str(title or "")
    if SECURITY_PHRASE not in t:
        return None
    m = _SEC_TITLE.match(t)
    if not m:
        return None
    k = _SEC_KIND.search(m.group(2))
    if not k:
        return None
    ref = m.group(1).split("@", 1)[0]
    repo, sep, tag = ref.rpartition(":")
    if not sep or "/" in tag or not tag:
        return None
    return norm_repo(repo), norm_tag(tag), k.group(1).upper()


def match_security(rows, repos, current_tag):
    """finding_id of the first row flagging `repo:current_tag`, else None.
    rows: [(finding_id, severity, title)]."""
    want_repos = {norm_repo(r) for r in repos or () if r}
    want_tag = norm_tag(current_tag)
    if not want_repos or not want_tag:
        return None
    for fid, sev, title in rows or ():
        if str(sev or "").lower() == "accepted":
            continue
        p = parse_security_row(title)
        if p and p[0] in want_repos and p[1] == want_tag:
            return fid
    return None


# ── DB access (cached; fail-safe) ───────────────────────────────────────────
_REC_CACHE = None
_SEC_CACHE = None
SOURCE = {"track_record": "not queried", "security": "not queried"}


def _connect():
    dsn = os.environ.get("SWEEP_PG_DSN")
    if not dsn:
        return None
    try:
        import psycopg
        return psycopg.connect(dsn, connect_timeout=5)
    except Exception:
        return None


def component_rows(window_days=90):
    """[(component, dep, outcome, recorded_at)] or None when UNVERIFIED."""
    global _REC_CACHE
    if _REC_CACHE is not None:
        return _REC_CACHE[0]
    _REC_CACHE = (None,)
    conn = _connect()
    if conn is None:
        SOURCE["track_record"] = "unverified — no SWEEP_PG_DSN (earned lane OFF)"
        return None
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT component, dep, outcome, recorded_at FROM component_autonomy "
                        "WHERE recorded_at >= now() - make_interval(days => %s)",
                        (int(window_days) + 1,))
            rows = list(cur.fetchall())
    except Exception as e:
        SOURCE["track_record"] = (f"unverified — component_autonomy unreadable "
                                  f"({type(e).__name__}); earned lane OFF")
        return None
    SOURCE["track_record"] = f"component_autonomy ({len(rows)} row(s) in {window_days}d)"
    _REC_CACHE = (rows,)
    return rows


def security_rows():
    """[(finding_id, severity, title)] or None when UNVERIFIED."""
    global _SEC_CACHE
    if _SEC_CACHE is not None:
        return _SEC_CACHE
    conn = _connect()
    if conn is None:
        SOURCE["security"] = "unverified — no SWEEP_PG_DSN (security bypass OFF)"
        return None
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT finding_id, severity, title FROM sweep_findings "
                        "WHERE section = 'security' AND resolved_at IS NULL "
                        "AND severity <> 'accepted' AND title LIKE %s",
                        (f"%{SECURITY_PHRASE}%",))
            rows = list(cur.fetchall())
    except Exception as e:
        SOURCE["security"] = f"unverified — sweep_findings unreadable ({type(e).__name__}); bypass OFF"
        return None
    SOURCE["security"] = f"sweep_findings ({len(rows)} open 'newer upstream tag' row(s))"
    _SEC_CACHE = rows
    return rows


def earned(policy, keys, now=None):
    """(earned, note). Off / unverified => (False, why)."""
    ep = earned_policy(policy)
    if ep is None:
        return False, "earned autonomy disabled by policy"
    rows = component_rows(ep["window_days"])
    if rows is None:
        return False, SOURCE["track_record"]
    ok, s = evaluate_track_record(rows, keys, now=now, **ep)
    note = (f"{s['green']} green / {s['reverts']} revert(s) in {s['window_days']}d "
            f"(needs >= {s['min_green']} green, 0 reverts)")
    return ok, note


def security_bypass(policy, repos, current_tag):
    """finding_id when the cooldown is bypassed for a CVE fix, else None."""
    if not security_bypass_enabled(policy):
        return None
    rows = security_rows()
    if rows is None:
        return None
    return match_security(rows, repos, current_tag)


# ── writer ───────────────────────────────────────────────────────────────────
# The table is created by the sweep-history init Job (schema v9,
# kubernetes/apps/databases/sweep-history/app/schema-configmap.yaml) — ONE
# source of DDL. Until it has run, reads are "unverified" (lane OFF) and a
# write raises loudly.


def record(component, dep, version, lane, fast_lane, outcome, window_slot=None,
           finding_ref=None, notes=None):
    """Insert one row; returns its id. Raises on any failure — a record that
    did not land must be LOUD (the caller prints it), never swallowed."""
    if fast_lane not in FAST_LANES:
        raise ValueError(f"fast_lane must be one of {FAST_LANES}")
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}")
    if lane not in ("pr", "direct-bump"):
        raise ValueError("lane must be pr or direct-bump")
    conn = _connect()
    if conn is None:
        raise RuntimeError("SWEEP_PG_DSN unset or unreachable — component autonomy NOT recorded")
    with conn, conn.cursor() as cur:
        cur.execute("INSERT INTO component_autonomy (component, dep, version, lane, fast_lane, "
                    "outcome, window_slot, finding_ref, notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "RETURNING id",
                    (str(component).strip().lower(), norm_repo(dep) if dep else None, version,
                     lane, fast_lane, outcome, window_slot, finding_ref, notes))
        return cur.fetchone()[0]
