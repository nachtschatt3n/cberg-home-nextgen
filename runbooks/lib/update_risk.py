"""update_risk — the graded risk model for unattended updates (2026-11-25 rebuild).

WHY. The old gates were blunt: a literal "Breaking Changes" heading held a bump
whether or not it listed anything, any new migration file held it whatever
backup protected the data, and a G3 that could not read the notes passed the
bump as "relied on CI + policy". This module replaces those with SIGNALS and
OUTCOME LANES. Pure functions, no network, no cluster: the callers fetch the
evidence (release-note bodies, PR files, policy) and hand it in, so every
branch is testable and every missing input has an explicit fail-closed answer.

OUTCOME LANES (the only values `decide_lane` returns)
  AUTO               no breaking evidence, reversible by `git revert`. The
                     nightly window applies it.
  AUTO-BACKUP-GATED  a schema/data migration is present, but the component has
                     a declared data-protection entry (nightly dump + a restore
                     proof tool). Routed to the PLAN pipeline, which runs the
                     named gate at runtime and applies only when it PASSES.
                     auto-update.py never merges these itself.
  PLAN               a real breaking item that touches us (or cannot be proven
                     not to), an unreadable evidence source, an unknown class.
  WEEKEND-ATTENDED   cluster core: reboots, quorum, storage engine, CNI/DNS,
                     GitOps controllers. Set by a deny rule's `lane:` field.
  (WAIT is not a risk lane: cooldown / CI / draft. The caller emits it.)

STANDING RULE (operator, do not weaken): interruption and downtime are fine;
DATA LOSS and FEATURE LOSS are not. Every irreversible data step needs a
VERIFIED restore path. Hence: a migration with NO declared protection is PLAN,
never AUTO-BACKUP-GATED, and "release notes unavailable" is PLAN, never AUTO.

BREAKING EVIDENCE is read from the notes themselves:
  * a "Breaking Changes" heading with NO items under it (or "None"/"N/A") is
    boilerplate and does not hold;
  * items listed under it are classified one by one: ACKED (policy
    `breaking_ack`, dated, with evidence), UNTOUCHED (a removal/rename item
    whose config tokens appear nowhere in this component's manifests; patch
    bumps only), or BLOCKING (everything else - including every item we
    cannot prove irrelevant);
  * an Upgrade/Migration section is advisory on a patch bump and blocking on a
    minor+ bump when it demands action.
"""
from __future__ import annotations

import datetime as _dt
import fnmatch
import re
from pathlib import Path

LANES = ("AUTO", "AUTO-BACKUP-GATED", "PLAN", "WEEKEND-ATTENDED")

_HEADING = re.compile(r"^(?P<h>#{1,6})\s*(?P<t>.+?)\s*#*\s*$")
_BREAK_TITLE = re.compile(r"breaking|⚠️\s*breaking|🚨\s*breaking", re.IGNORECASE)
_UPGRADE_TITLE = re.compile(r"^(?:upgrade|migration|upgrading|migrating)\b", re.IGNORECASE)
_BOLD_LINE = re.compile(r"^\s*(?:\*\*|__)\s*(?P<t>[^*_]+?)\s*:?\s*(?:\*\*|__)\s*:?\s*$")
_EMPTY_BODY = re.compile(
    r"^\W*(?:none|n/?a|nothing|no\s+(?:known\s+)?breaking(?:\s+changes?)?(?:\s+in\s+this\s+release)?)\W*$",
    re.IGNORECASE)
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<t>.+)$")
# conventional-commit "feat!:" / "BREAKING CHANGE:" lines outside any section
_INLINE_BREAK = re.compile(r"(?:^|\W)(?:[a-z]+(?:\([^)]*\))?!:|BREAKING[ -]CHANGES?\b)|(?-i:\bBREAKING\b)", re.IGNORECASE)
# wording that makes an item about REMOVAL (config we can prove we do not use)
_REMOVAL = re.compile(r"\b(?:remov(?:ed|al)|renam(?:ed|ing)|deprecat(?:ed|ion)|dropp(?:ed|ing)|"
                      r"no longer (?:supported|available|exists?)|replaced by|discontinued)\b",
                      re.IGNORECASE)
# wording that means the OPERATOR MUST DO or ADD something, or behaviour moved
# under us: absence of the token in our config does NOT prove we are fine
_OBLIGATION = re.compile(r"\b(?:must|required?|requires?|unless|only if|default(?:s|ed)?|now (?:rejects?|refuses?|"
                         r"requires?|enforces?)|stricter|opt[- ]in|need(?:s)? to|manual(?:ly)?|before upgrading|"
                         r"after upgrading|migrat(?:e|ion)|set\b)", re.IGNORECASE)
_ACTION = re.compile(r"\b(?:must|required?|requires?|before upgrading|manual(?:ly)?|you (?:need|have) to|"
                     r"ensure|run\b|back ?up)", re.IGNORECASE)
_TOKEN = re.compile(r"`([^`\n]{2,80})`|\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b")


class Item:
    __slots__ = ("text", "heading", "kind")

    def __init__(self, text, heading, kind):
        self.text, self.heading, self.kind = text.strip(), heading, kind

    def __repr__(self):  # pragma: no cover
        return f"Item({self.kind}:{self.heading!r}:{self.text[:40]!r})"


def _sections(body: str):
    """[(level, title, [lines])] for every markdown heading, plus bold-line
    pseudo-headings (level 7) so `**Breaking changes**` opens a section."""
    out, cur = [], None
    fence = False
    for raw in body.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if line.lstrip().startswith("```"):
            fence = not fence
        m = None if fence else _HEADING.match(line)
        if m:
            cur = [len(m.group("h")), m.group("t"), []]
            out.append(cur)
            continue
        b = None if fence else _BOLD_LINE.match(line)
        if b and (_BREAK_TITLE.search(b.group("t")) or _UPGRADE_TITLE.match(b.group("t"))):
            cur = [7, b.group("t"), []]
            out.append(cur)
            continue
        if cur is not None:
            cur[2].append(line)
    return out


def _items_from_lines(lines, heading, kind):
    """Items = sub-headings' text excluded (handled by the caller), bullets,
    else paragraphs. Blockquote markers and alert tags are stripped."""
    items, para = [], []

    def flush():
        if para:
            items.append(Item(" ".join(para), heading, kind))
            para.clear()

    for ln in lines:
        s = re.sub(r"^\s*>\s?", "", ln).strip()
        s = re.sub(r"^\[!(?:NOTE|IMPORTANT|WARNING|CAUTION|TIP)\]\s*", "", s, flags=re.IGNORECASE)
        if not s:
            flush()
            continue
        b = _BULLET.match(s)
        if b:
            flush()
            items.append(Item(b.group("t"), heading, kind))
        else:
            para.append(s)
    flush()
    return [i for i in items if i.text]


def read_notes(body):
    """Parse one release body. Returns a dict:
      items      list[Item] kind 'breaking' | 'upgrade' | 'inline'
      boilerplate  count of breaking-titled sections that list nothing
    `body` empty/None => ValueError-free {"items": [], "boilerplate": 0, "empty": True}
    so the caller can tell 'nothing to read' from 'read, clean'."""
    if not body or not str(body).strip():
        return {"items": [], "boilerplate": 0, "empty": True}
    body = str(body)
    secs = _sections(body)
    items, boiler = [], 0
    covered = set()
    for idx, (lvl, title, lines) in enumerate(secs):
        if not (_BREAK_TITLE.search(title) or _UPGRADE_TITLE.match(title)):
            continue
        kind = "breaking" if _BREAK_TITLE.search(title) else "upgrade"
        # the section runs to the next heading of the SAME OR HIGHER level;
        # deeper headings are its items (each sub-heading + its text is ONE item)
        j = idx + 1
        sub = []
        while j < len(secs) and secs[j][0] > lvl and lvl != 7:
            sub.append(secs[j])
            j += 1
        covered.update(range(idx, j))
        own = [x for x in lines if x.strip()]
        text_own = " ".join(re.sub(r"^\s*>\s?", "", x).strip() for x in own)
        got = []
        if sub:
            for (_l, t, ls) in sub:
                got.append(Item((t + ". " + " ".join(x.strip() for x in ls if x.strip())).strip(". "),
                                title, kind))
            got += _items_from_lines(lines, title, kind)
        else:
            if _EMPTY_BODY.match(text_own or ""):
                got = []
            else:
                got = _items_from_lines(lines, title, kind)
        if kind == "breaking" and not got:
            boiler += 1
        items += got
    # inline markers outside any captured section
    seen = {x.strip() for i in covered for x in secs[i][2]}
    for raw in body.split("\n"):
        st = raw.strip()
        if not st or st in seen or _HEADING.match(st) or _BOLD_LINE.match(raw):
            continue
        if _INLINE_BREAK.search(raw):
            items.append(Item(re.sub(r"^[-*+]\s+", "", st), "(inline)", "inline"))
    return {"items": items, "boilerplate": boiler, "empty": False}


def tokens_of(text: str):
    """Config-like identifiers an item names: `backticked` spans and UPPER_SNAKE
    names. Short or purely numeric spans are dropped."""
    out = []
    for m in _TOKEN.finditer(text):
        t = (m.group(1) or m.group(2) or "").strip()
        if len(t) >= 3 and not re.fullmatch(r"[\d.vV]+", t) and t not in out:
            out.append(t)
    return out


def _ack_for(item_text, dep, version, acks, today):
    """The first live, in-scope `breaking_ack` whose needle matches the item."""
    today = today or _dt.date.today()
    for a in acks or []:
        pat, needle = a.get("match"), (a.get("needle") or "").lower()
        if not pat or not needle or needle not in item_text.lower():
            continue
        if not any(fnmatch.fnmatch(dep, g) for g in (pat, f"*{pat}", f"*{pat}*")):
            continue
        until = a.get("until")
        if until is None or not a.get("evidence"):
            continue          # an ack with no expiry or no evidence is inert
        try:
            if isinstance(until, str):
                until = _dt.date.fromisoformat(until)
            if today > until:
                continue
        except Exception:
            continue
        return a
    return None


def classify_item(item, *, dep, version, utype, corpus, acks=None, today=None):
    """('acked'|'untouched'|'advisory'|'blocking', why) for ONE listed item."""
    ack = _ack_for(item.text, dep, version, acks, today)
    if ack:
        return "acked", f"acked until {ack.get('until')}: {str(ack.get('evidence'))[:100]}"
    if item.kind == "upgrade":
        if utype == "patch":
            return "advisory", "upgrade-guide note on a patch bump"
        if not _ACTION.search(item.text):
            return "advisory", "upgrade-guide note demanding no action"
        return "blocking", "upgrade guide demands action on a minor+ bump"
    # breaking / inline items
    if utype == "patch" and corpus is not None and _REMOVAL.search(item.text) \
            and not _OBLIGATION.search(item.text):
        toks = tokens_of(item.text)
        if toks:
            hit = next((t for t in toks if t.lower() in corpus.lower()), None)
            if hit is None:
                return "untouched", f"removal/rename item; none of {toks[:4]} appears in our manifests"
            return "blocking", f"item names `{hit}` which our manifests use"
        return "blocking", "removal item names no config token — cannot prove we do not use it"
    return "blocking", "listed breaking item not proven irrelevant to this deployment"


def assess_notes(body, *, dep, version, utype, corpus=None, acks=None, today=None):
    """Grade one release body. Returns dict:
      blocking  [str]  items that hold the bump (empty => no break evidence)
      cleared   [str]  items cleared with the reason (acked/untouched/advisory)
      boilerplate int  empty 'Breaking Changes' headings ignored
      read      bool   False when the body was empty (caller fails CLOSED)"""
    r = read_notes(body)
    if r["empty"]:
        return {"blocking": [], "cleared": [], "boilerplate": 0, "read": False}
    blocking, cleared = [], []
    for it in r["items"]:
        v, why = classify_item(it, dep=dep, version=version, utype=utype,
                               corpus=corpus, acks=acks, today=today)
        label = f"{it.heading}: {it.text[:110]}"
        (blocking if v == "blocking" else cleared).append(f"{label} [{why}]")
    return {"blocking": blocking, "cleared": cleared,
            "boilerplate": r["boilerplate"], "read": True}


# ── component evidence ───────────────────────────────────────────────────────
def corpus_from_files(repo_root: Path, files):
    """Concatenated text of every YAML/JSON/TOML file under the kubernetes/apps
    app directories the PR files live in. None when it cannot be built (no
    file under kubernetes/apps) — the caller then cannot prove 'untouched'."""
    root = Path(repo_root)
    dirs = set()
    for f in files or []:
        parts = Path(f).parts
        if len(parts) >= 4 and parts[0] == "kubernetes" and parts[1] == "apps":
            dirs.add(root / parts[0] / parts[1] / parts[2] / parts[3])
    return _read_dirs(dirs)


def corpus_for_component(repo_root: Path, component: str):
    """Same corpus for a no-PR item, located by directory name. None if absent."""
    root = Path(repo_root) / "kubernetes" / "apps"
    c = (component or "").lower()
    dirs = {d for d in root.glob("*/*") if d.is_dir() and d.name.lower() == c}
    return _read_dirs(dirs)


def _read_dirs(dirs):
    if not dirs:
        return None
    buf = []
    for d in sorted(dirs):
        for p in d.rglob("*"):
            if p.is_file() and p.suffix in (".yaml", ".yml", ".json", ".toml", ".env", ".conf", ".ini"):
                if ".sops." in p.name:
                    continue          # never read encrypted/secret material
                try:
                    buf.append(p.read_text(errors="ignore"))
                except Exception:
                    continue
    return "\n".join(buf) if buf else None


# ── data protection ──────────────────────────────────────────────────────────
def protection_for(policy, names, repo_root: Path):
    """The `data_protection` entry covering any of `names` whose dump CronJob
    manifest EXISTS in the repo, else (None, reason). The entry declares the
    runtime gate (`restore_proof`) the plan pipeline must PASS; this function
    proves only that the declared dump job is real and tracked."""
    for e in (policy or {}).get("data_protection") or []:
        pat = e.get("match")
        if not pat:
            continue
        if not any(fnmatch.fnmatch(str(n).lower(), g) for n in names or []
                   for g in (pat, f"*{pat}", f"*{pat}*")):
            continue
        dump = e.get("dump_job")
        if not dump or not (Path(repo_root) / dump).is_file():
            return None, f"data_protection entry {pat!r} names a dump job that is not tracked ({dump})"
        if not e.get("restore_proof") or not e.get("volume"):
            return None, f"data_protection entry {pat!r} declares no restore_proof/volume"
        return e, "declared"
    return None, "no data_protection entry (no verified dump + restore path declared)"


# ── the lane decision ────────────────────────────────────────────────────────
def decide_lane(*, rule_lane=None, notes_read=True, blocking=(), migration=False,
                protection=None, earned_ok=False, structural_read=True):
    """(lane, reason). Order matters: the first decisive signal wins.

      1. a deny rule with `lane: weekend-attended` => WEEKEND-ATTENDED
      2. blocking breaking evidence                => PLAN
      3. notes could not be read                   => PLAN (unless earned autonomy)
      4. migration present                         => AUTO-BACKUP-GATED when a
         declared, tracked protection entry exists; else PLAN (data-loss rule)
      5. diff unreadable                           => annotate only (never AUTO-blocking:
         the pre-existing G3s asymmetry), but only AFTER 1-4
      6. otherwise AUTO
    """
    if rule_lane == "weekend-attended":
        return "WEEKEND-ATTENDED", "cluster-core component: reboots/quorum/storage/network engine"
    if blocking:
        return "PLAN", "breaking-change evidence: " + "; ".join(str(b)[:140] for b in list(blocking)[:2])
    if not notes_read and not earned_ok:
        return "PLAN", ("release notes could not be read — an unverified bump is never "
                        "AUTO (fail-closed)")
    if migration:
        if protection:
            return "AUTO-BACKUP-GATED", (
                f"schema/data migration with a declared restore path: dump {protection.get('dump_job')}, "
                f"gate `{protection.get('restore_proof')}` must PASS at runtime")
        return "PLAN", ("schema/data migration and NO verified dump + restore proof declared "
                        "for this component (data-loss rule)")
    return "AUTO", "no breaking evidence, reversible by git revert"
