"""Contextual risk-scoring model for the security sweep — PHASE 1 (additive).

Severity today is INTRINSIC: Trivy says CRITICAL, the finding is tagged
critical. The operator's real risk model is CONTEXTUAL:

    tier = f(exposure, exploited, nature)

  CRITICAL  external-UNAUTH  AND  exploited-in-the-wild  AND  real vuln
            (pages the operator; on this homelab it should usually be zero)
  HIGH      external + real vuln but NOT exploited  — OR — internal + exploited
  MEDIUM    internal, real open issue, not exploited  ("open but internal")
  LOW       policy / hygiene: floating tags, drift, convention  ("against policy")

The whole point: a Trivy-CRITICAL on an internal, never-exploited image is a
MEDIUM; the SAME CVE on a public ingress that is in CISA KEV is the real
CRITICAL. Today they score identically.

THREE AXES
----------
* exposure  — external-unauth / external-auth / internal / cluster-only.
              Reuses the AR-059 posture logic (an ingress whose backend routes
              to a `*-authentik-outpost` / `ak-outpost-*-forward-auth` service
              is Authentik-gated → external-auth). Factored here so s8 and the
              risk model share ONE classifier (see build_exposure_index).
* exploited — CISA KEV cross-reference on the finding's CVE IDs. TRUE / FALSE /
              None(UNKNOWN). Fails SOFT and VISIBLE: a KEV-feed outage or a
              finding with no recorded CVE IDs is UNKNOWN, never silently FALSE
              (that is the silent-zero class we have fought all week). The label
              is honestly "exploited-in-the-wild", never "exploited against us".
* nature    — real vuln/exposure vs policy/hygiene, from an explicit
              section→nature table (NATURE_BY_SECTION), with two narrow,
              documented s4 marker overrides (floating-tag / scan-coverage-gap
              → policy).

PURITY / TESTABILITY
--------------------
`tier_for(exposure, exploited, nature)` is a pure matrix — unit-tested cell by
cell. `score(finding, ...)` composes the three axis computations and returns a
ScoreResult carrying the tier PLUS an auditable rationale string explaining WHY.

This module does NOT change what security-check.py emits or suppresses. It is a
standalone scorer consumed by rescore-findings.py (the proof harness). Live
routing is PHASE 2.

PUBLIC-REPO RULE: this module READS CVE IDs (from finding titles + the DB
`metadata.security_detail`, where the disclosure policy keeps them) but never
WRITES CVE IDs, KEV detail, or per-image counts anywhere. Callers must keep it
that way.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Axis vocabularies (string constants — cheap to compare, easy to print)
# ---------------------------------------------------------------------------

# exposure
EXTERNAL_UNAUTH = "external-unauth"
EXTERNAL_AUTH = "external-auth"
INTERNAL = "internal"
CLUSTER_ONLY = "cluster-only"

# nature
VULN = "vuln"
POLICY = "policy"

# tiers
CRITICAL = "critical"
HIGH = "high"
MEDIUM = "medium"
LOW = "low"

# exploited is a tri-state: True / False / None(unknown). The REASON is carried
# separately so the board can show WHY something is unknown.
EXPLOITED_KEV = "cve-in-kev"
NOT_EXPLOITED = "cves-not-in-kev"
UNKNOWN_NO_CVE = "no-cve-ids-recorded"
UNKNOWN_FEED = "kev-feed-unavailable"


# ---------------------------------------------------------------------------
# nature: explicit section → nature table (NOT heuristics on prose)
# ---------------------------------------------------------------------------
#
# Each security-check.py section slug maps to whether its findings are, by
# nature, a real vulnerability/exposure (an attacker exploits it) or a
# policy/hygiene item (it is "against policy"). The task fixes s2/s3/s4 =
# vuln and s10/floating-tag/stale-chart/drift = policy; the rest are assigned
# here with the reasoning inline.
NATURE_BY_SECTION: dict[str, str] = {
    "s1_sops_coverage":      VULN,    # unencrypted secret material = real exposure
    "s2_sensitive_exposure": VULN,    # (task: real exposure)
    "s3_git_history":        VULN,    # (task: real exposure) leaked-secret pattern
    "s4_cve_check":          VULN,    # (task: real vuln) — S4_POLICY_MARKERS override below
    "s5_authentik_logins":   VULN,    # active auth-attack detection
    "s6_attack_patterns":    VULN,    # active external attack detection
    "s6a_error_rate_spikes": POLICY,  # operational anomaly, not a vuln/exposure
    "s7_rbac_pod_security":  POLICY,  # hardening / config hygiene
    "s8_external_exposure":  VULN,    # an UNEXPECTED external ingress is a real exposure
    "s9_certificates":       POLICY,  # expiry / rotation hygiene (AR-018 fp handled upstream)
    "s10_flux_posture":      POLICY,  # (task: policy/hygiene)
    "s11_unifi":             VULN,    # IPS/IDS + rogue-AP threat alarms
    "s13_wazuh_siem":        VULN,    # SIEM alerts (level>=12 bypass suppression upstream)
}

# Within s4_cve_check a finding may be about tag HYGIENE (a floating/mutable
# tag) or a Trivy SCAN-COVERAGE gap rather than a concrete vulnerability. These
# are policy/hygiene, not vulns. Detected by a small set of STABLE markers the
# CVE check emits verbatim — this is one explicit marker match, deliberately
# NOT general prose parsing.
S4_POLICY_MARKERS = (
    "floating tag",
    "posture is unknowable",
    "posture unknowable",
    "scan coverage gap",
    "coverage gap",
    "pin an immutable version",
    "pin it",
)

# Sections whose exposure surface is the PUBLIC GIT REPO itself, not a cluster
# component. A credential pattern in public history is world-readable.
_PUBLIC_REPO_SECTIONS = {"s2_sensitive_exposure", "s3_git_history"}

# AR-004: these external apps enforce their OWN robust auth layer, so an
# unauthenticated external attacker is gated exactly like an Authentik outpost
# fronts the others. Sourced verbatim from the AR-004 accepted risk; kept
# narrow and explicit so the assumption is visible on the board.
#
# THIS SET IS THE ALLOWLIST MECHANISM. To bless another app's own login as a
# verified security boundary (dropping it from external-unauth→HIGH to
# external-auth→MEDIUM), the operator adds its token HERE — a code change that
# is reviewed, exactly like an AR entry. It is deliberately NOT auto-populated:
# assuming an app's login is a real boundary, unverified, is the error class we
# refuse to make.
SELF_AUTH_APPS = {"open-webui", "n8n", "iobroker", "home-assistant"}

# CANDIDATES for the allowlist above — apps we OBSERVE on external ingress that
# ship their own login screen and would be plausible additions to SELF_AUTH_APPS,
# but which the operator has NOT blessed. They stay external-unauth (→ HIGH); the
# model will NOT silently downgrade them. Their only effect is a rationale note
# and a report call-out so the blessing decision is surfaced, never assumed.
SELF_AUTH_CANDIDATES = {"immich", "nextcloud", "paperless", "paperless-ngx",
                        "jellyfin", "traccar"}


# ---------------------------------------------------------------------------
# Finding — the unit the scorer consumes
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """A single sweep finding, normalized for scoring.

    Only `subsection` and `message` are strictly required; the rest are filled
    when available (image/CVE IDs from the title backticks or the DB
    metadata.security_detail; component/namespace from metadata).
    """

    subsection: str                       # section slug, e.g. "s4_cve_check"
    message: str                          # the finding title / raw message
    component: Optional[str] = None       # app/component name if known
    namespace: Optional[str] = None
    image: Optional[str] = None           # image ref if any
    cve_ids: list[str] = field(default_factory=list)
    intrinsic_severity: Optional[str] = None   # critical|warning|accepted (before)
    accepted: bool = False                # operator-accepted (AR-tagged / accepted sev)
    finding_id: Optional[str] = None

    # --- parsing helpers -----------------------------------------------------

    _CVE_RE = re.compile(r"CVE-\d{4}-\d{3,7}")
    _BACKTICK_RE = re.compile(r"`([^`]+)`")

    @classmethod
    def from_db_row(cls, row: dict) -> "Finding":
        """Build a Finding from a sweep_findings DB row (dict_row).

        Extracts CVE IDs from BOTH the title and metadata.security_detail, and
        the image ref from the first backticked span in the title.
        """
        md = row.get("metadata") or {}
        title = row.get("title") or ""
        detail = str(md.get("security_detail") or "")
        cve_set = set(cls._CVE_RE.findall(title + " " + detail))
        # Machine-readable CVE list attached at write time by s4_cve_check
        # (metadata.cve_ids — DB-only, per the disclosure policy). Merged here so
        # KEV can assess a finding whose TITLE carries no CVE ID (the Phase-1 gap:
        # 122/199 scored exploited=UNKNOWN purely because the IDs lived only in a
        # transient Trivy report, never on the finding). Kept out of the title on
        # purpose — the title is what lands in committed files.
        extra = md.get("cve_ids")
        if isinstance(extra, (list, tuple)):
            for c in extra:
                if isinstance(c, str) and cls._CVE_RE.fullmatch(c):
                    cve_set.add(c)
        cves = sorted(cve_set)

        # Only the CVE section names container images in its first backtick.
        # Other sections put code snippets / resource names there (e.g. an
        # s3_git_history finding backticks a shell command containing '/' and
        # ':'), which must NOT be mistaken for an image ref.
        image = None
        subsection = md.get("subsection") or ""
        if subsection == "s4_cve_check":
            backticks = cls._BACKTICK_RE.findall(title)
            if backticks:
                first = backticks[0].strip()
                if "/" in first or ":" in first:
                    image = first

        sev = row.get("severity")
        accepted = sev == "accepted" or "[AR-" in title.upper().replace(" ", "")
        # simpler, robust AR detection:
        accepted = (sev == "accepted") or bool(re.search(r"\[AR-\d+\]", title, re.I))

        return cls(
            subsection=subsection,
            message=title,
            component=md.get("component"),
            namespace=md.get("namespace"),
            image=image,
            cve_ids=cves,
            intrinsic_severity=sev,
            accepted=accepted,
            finding_id=row.get("finding_id"),
        )

    def app_tokens(self) -> list[str]:
        """Candidate app-name tokens for exposure lookup.

        Derived from component + the image's last path segment (tag stripped).
        e.g. `registry.librechat.ai/danny-avila/librechat:v0.8.7` -> "librechat".
        """
        toks: list[str] = []
        if self.component:
            toks.append(self.component.strip().lower())
        if self.image:
            ref = self.image.split("@")[0]          # drop digest
            path = ref.rsplit(":", 1)[0] if ":" in ref.rsplit("/", 1)[-1] else ref
            last = path.rsplit("/", 1)[-1]
            if last:
                toks.append(last.strip().lower())
        # dedupe, keep order
        seen: set[str] = set()
        out: list[str] = []
        for t in toks:
            if t and t not in seen:
                seen.add(t)
                out.append(t)
        return out


# ---------------------------------------------------------------------------
# Exposure classifier — factored from s8_external_exposure + AR-059 posture
# ---------------------------------------------------------------------------

_OUTPOST_SVC_RE = re.compile(r"(-authentik-outpost$|^ak-outpost-)")


def _strip_outpost(svc_name: str) -> str:
    t = re.sub(r"-authentik-outpost$", "", svc_name)
    t = re.sub(r"^ak-outpost-", "", t)
    t = re.sub(r"-forward-auth$", "", t)
    return t


@dataclass
class ExposureIndex:
    """App-token → exposure classification, built once from cluster state.

    external_auth  : app tokens whose external ingress host is Authentik-gated
                     (root path routes to a *-authentik-outpost service) OR a
                     known self-auth app (AR-004).
    external_unauth: app tokens with an external ingress, not gated.
    internal_apps  : app tokens that have only an internal (non-external) ingress.
    All token sets also include backend-service-derived tokens so an image name
    that differs from the ingress name still resolves.
    """

    external_auth: set[str] = field(default_factory=set)
    external_unauth: set[str] = field(default_factory=set)
    internal_apps: set[str] = field(default_factory=set)

    def classify(self, tokens: Iterable[str]) -> tuple[str, str]:
        """Return (exposure, note) for the first token that resolves.

        Matching is exact-or-prefix on the registered app tokens (so image
        token "librechat" resolves ingress "librechat-librechat"). Unresolved
        tokens default to INTERNAL (conservative: not public, not dismissed).
        """
        toks = [t for t in tokens if t]
        for t in toks:
            for tier, pool in (
                (EXTERNAL_UNAUTH, self.external_unauth),
                (EXTERNAL_AUTH, self.external_auth),
                (INTERNAL, self.internal_apps),
            ):
                if _token_matches(t, pool):
                    # SELF_AUTH override: an external-unauth app that enforces
                    # its own login is effectively gated (AR-004).
                    if tier == EXTERNAL_UNAUTH and t in SELF_AUTH_APPS:
                        return EXTERNAL_AUTH, f"'{t}': external + own auth layer (AR-004)"
                    # CANDIDATE: ships its own login but NOT operator-blessed —
                    # stays external-unauth (no downgrade), just flagged so the
                    # blessing decision is visible on the board.
                    if tier == EXTERNAL_UNAUTH and t in SELF_AUTH_CANDIDATES:
                        return EXTERNAL_UNAUTH, (
                            f"'{t}': external-unauth — ships own login but NOT "
                            f"operator-blessed (self-auth CANDIDATE, not AR-004)")
                    return tier, f"'{t}' matched {tier} ingress"
        if toks:
            return INTERNAL, f"no external ingress for {toks!r} → internal (ClusterIP/internal)"
        return INTERNAL, "no component/image → internal (default)"


def _token_matches(token: str, pool: set[str]) -> bool:
    """Exact, or the registered app token is a MORE-specific form of `token`.

    We deliberately match only two shapes:
      * exact           token == p
      * ingress-longer   p.startswith(token + "-")   e.g. image "librechat"
                         resolves ingress "librechat-librechat".

    We do NOT match the reverse (`token.startswith(p + "-")`, i.e. the finding's
    token is LONGER than the ingress name). That direction elevates internal
    sidecars/exporters — `nextcloud-exporter`, `nextcloud-mcp-server` — to their
    parent app's external exposure purely on a shared prefix, which is wrong:
    those run on their own ClusterIP service and are not externally reachable.
    """
    if token in pool:
        return True
    for p in pool:
        if p == token or p.startswith(token + "-"):
            return True
    return False


def build_exposure_index(ingress_items: list[dict], svc_items: list[dict] | None = None) -> ExposureIndex:
    """Pure builder: cluster ingress/service JSON items → ExposureIndex.

    Mirrors s8_external_exposure's `ingressClassName == "external"` enumeration
    and adds the AR-059 posture step (outpost-backed root path = gated).
    """
    idx = ExposureIndex()

    # First pass: which hosts are Authentik-gated?
    gated_hosts: set[str] = set()
    for ing in ingress_items:
        spec = ing.get("spec", {})
        if spec.get("ingressClassName") != "external":
            continue
        for rule in spec.get("rules", []) or []:
            host = rule.get("host", "")
            for path in ((rule.get("http") or {}).get("paths") or []):
                svc = ((path.get("backend") or {}).get("service") or {}).get("name", "")
                p = path.get("path", "/")
                if _OUTPOST_SVC_RE.search(svc) and p in ("/", "/outpost.goauthentik.io"):
                    gated_hosts.add(host)

    # Second pass: register app tokens per external ingress.
    external_hosts: set[str] = set()
    for ing in ingress_items:
        spec = ing.get("spec", {})
        name = ing.get("metadata", {}).get("name", "").lower()
        if spec.get("ingressClassName") != "external":
            continue
        tokens = {name}
        gated_here = False
        for rule in spec.get("rules", []) or []:
            host = rule.get("host", "")
            external_hosts.add(host)
            if host in gated_hosts:
                gated_here = True
            for path in ((rule.get("http") or {}).get("paths") or []):
                svc = ((path.get("backend") or {}).get("service") or {}).get("name", "")
                if svc:
                    tokens.add(_strip_outpost(svc).lower())
        # the outpost helper ingress itself carries no real app; skip its tokens
        # from the unauth pool but its presence already marked the host gated.
        tokens = {t for t in tokens if t}
        if gated_here:
            idx.external_auth |= tokens
        else:
            idx.external_unauth |= tokens

    # Internal ingresses (non-external class) → internal app tokens.
    for ing in ingress_items:
        spec = ing.get("spec", {})
        cls = spec.get("ingressClassName")
        if cls == "external":
            continue
        name = ing.get("metadata", {}).get("name", "").lower()
        if name:
            idx.internal_apps.add(name)
        for rule in spec.get("rules", []) or []:
            for path in ((rule.get("http") or {}).get("paths") or []):
                svc = ((path.get("backend") or {}).get("service") or {}).get("name", "")
                if svc:
                    idx.internal_apps.add(_strip_outpost(svc).lower())

    # Don't let an app appear in both external and internal pools; external wins.
    idx.internal_apps -= (idx.external_auth | idx.external_unauth)
    return idx


def load_exposure_index() -> ExposureIndex:
    """Impure: read live ingress/service JSON via kubectl and build the index."""
    def _kubectl_json(args: list[str]) -> dict:
        out = subprocess.check_output(["kubectl", *args, "-o", "json"],
                                      stderr=subprocess.DEVNULL)
        return json.loads(out)

    ing = _kubectl_json(["get", "ingress", "-A"]).get("items", [])
    try:
        svc = _kubectl_json(["get", "svc", "-A"]).get("items", [])
    except Exception:
        svc = []
    return build_exposure_index(ing, svc)


# ---------------------------------------------------------------------------
# KEV index — exploited-in-the-wild cross-reference (fail-soft, visible)
# ---------------------------------------------------------------------------

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
_DEFAULT_CACHE = Path(os.environ.get("SWEEP_KEV_CACHE",
                                     str(Path.home() / ".cache" / "sweep" / "kev.json")))
_CACHE_TTL_S = 24 * 3600


@dataclass
class KevIndex:
    """CISA KEV catalog membership. Loads once, caches ~1/day, fails soft.

    `loaded` is False when the feed could not be fetched AND no usable cache
    exists — every lookup then returns UNKNOWN (never a silent FALSE).
    """

    cve_ids: set[str] = field(default_factory=set)
    loaded: bool = False
    source: str = "unloaded"      # "network" | "cache" | "cache-stale" | "unavailable"
    catalog_version: Optional[str] = None

    @classmethod
    def load(cls, *, url: str = KEV_URL, cache_path: Path = _DEFAULT_CACHE,
             ttl_s: int = _CACHE_TTL_S, timeout: int = 25) -> "KevIndex":
        # 1. Fresh cache?
        try:
            if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < ttl_s:
                data = json.loads(cache_path.read_text())
                return cls(cve_ids={v["cveID"] for v in data.get("vulnerabilities", [])},
                           loaded=True, source="cache",
                           catalog_version=data.get("catalogVersion"))
        except Exception:
            pass
        # 2. Network fetch.
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sweep-risk-model/1.0"})
            raw = urllib.request.urlopen(req, timeout=timeout).read()
            data = json.loads(raw)
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(raw)
            except Exception:
                pass
            return cls(cve_ids={v["cveID"] for v in data.get("vulnerabilities", [])},
                       loaded=True, source="network",
                       catalog_version=data.get("catalogVersion"))
        except Exception:
            pass
        # 3. Stale cache is better than nothing — but flagged as stale.
        try:
            if cache_path.exists():
                data = json.loads(cache_path.read_text())
                return cls(cve_ids={v["cveID"] for v in data.get("vulnerabilities", [])},
                           loaded=True, source="cache-stale",
                           catalog_version=data.get("catalogVersion"))
        except Exception:
            pass
        # 4. Nothing. Every lookup is UNKNOWN.
        return cls(loaded=False, source="unavailable")

    def is_exploited(self, cve_ids: Iterable[str]) -> tuple[Optional[bool], str]:
        """(state, reason). state is True / False / None(unknown).

        UNKNOWN when the feed is unavailable OR the finding has no CVE IDs to
        check — either way the caller must render it visibly, never as safe.
        """
        if not self.loaded:
            return None, UNKNOWN_FEED
        ids = [c for c in cve_ids if c]
        if not ids:
            return None, UNKNOWN_NO_CVE
        hits = [c for c in ids if c in self.cve_ids]
        if hits:
            return True, EXPLOITED_KEV
        return False, NOT_EXPLOITED


# ---------------------------------------------------------------------------
# The scorer
# ---------------------------------------------------------------------------


def compute_nature(finding: Finding) -> tuple[str, str]:
    """(nature, note) from the explicit section table + s4 marker overrides."""
    slug = finding.subsection
    base = NATURE_BY_SECTION.get(slug, VULN)  # unknown slug → VULN (don't hide)
    if slug == "s4_cve_check":
        low = finding.message.lower()
        for marker in S4_POLICY_MARKERS:
            if marker in low:
                return POLICY, f"s4 hygiene marker '{marker}' → policy"
    note = f"{slug} → {base}"
    if slug not in NATURE_BY_SECTION:
        note = f"unknown section {slug!r} → {base} (default)"
    return base, note


def compute_exposure(finding: Finding, exposure_index: Optional[ExposureIndex]) -> tuple[str, str]:
    """(exposure, note)."""
    if finding.subsection in _PUBLIC_REPO_SECTIONS:
        return EXTERNAL_UNAUTH, "public git repo is world-readable → external-unauth"
    if exposure_index is None:
        return INTERNAL, "no exposure index available → internal (default)"
    return exposure_index.classify(finding.app_tokens())


def compute_exploited(finding: Finding, kev_index: Optional[KevIndex]) -> tuple[Optional[bool], str]:
    """(state, reason)."""
    if kev_index is None:
        return None, UNKNOWN_FEED
    return kev_index.is_exploited(finding.cve_ids)


# effective-exposure collapse used by the tier matrix: an Authentik-gated
# external service presents the SAME surface to an UNauthenticated attacker as
# an internal one (the gate blocks it), so external-auth collapses onto internal
# for tiering — the external reachability is still recorded in the rationale.
def _effective(exposure: str) -> str:
    if exposure == EXTERNAL_UNAUTH:
        return "public"
    if exposure == EXTERNAL_AUTH:
        return "gated"     # == internal for tiering, see below
    return "internal"      # internal + cluster-only


def tier_for(exposure: str, exploited: Optional[bool], nature: str) -> str:
    """PURE tier matrix. Unit-tested cell by cell.

    nature == policy                                            -> LOW
    nature == vuln:
      public  + exploited=True                                 -> CRITICAL
      public  + exploited in {False, None}                     -> HIGH
      gated/internal + exploited=True                          -> HIGH
      gated/internal + exploited in {False, None}              -> MEDIUM

    exploited=None (UNKNOWN) lands at the not-exploited tier; the UNKNOWN state
    is surfaced separately (rationale + harness callout), never silently safe.
    """
    if nature == POLICY:
        return LOW
    eff = _effective(exposure)
    if eff == "public":
        return CRITICAL if exploited is True else HIGH
    # gated / internal
    return HIGH if exploited is True else MEDIUM


def matched_self_auth_candidate(finding: Finding) -> Optional[str]:
    """The candidate token this finding maps to, or None.

    Matches exact OR image-longer (`immich-server` → candidate `immich`), the
    same prefix shape the exposure classifier uses, so an app whose image name
    carries a `-server`/`-ngx` suffix still surfaces under its base name.
    Blessed apps (SELF_AUTH_APPS) are excluded — they are already external-auth.
    """
    toks = finding.app_tokens()
    if any(t in SELF_AUTH_APPS for t in toks):
        return None
    # exact match first (canonical), then prefix.
    for t in toks:
        if t in SELF_AUTH_CANDIDATES:
            return t
    for t in toks:
        for c in SELF_AUTH_CANDIDATES:
            if t.startswith(c + "-"):
                return c
    return None


def is_self_auth_candidate(finding: Finding) -> bool:
    """True when the finding's app is an un-blessed self-auth CANDIDATE.

    Used by the report to LIST (never downgrade) apps the operator could move
    into SELF_AUTH_APPS.
    """
    return matched_self_auth_candidate(finding) is not None


@dataclass
class ScoreResult:
    tier: str
    rationale: str
    exposure: str
    exploited: Optional[bool]
    exploited_reason: str
    nature: str
    unknown_exploited: bool
    finding: Finding
    exposure_note: str = ""


def _exploited_word(state: Optional[bool]) -> str:
    return {True: "exploited-in-KEV", False: "not-in-KEV", None: "KEV-UNKNOWN"}[state]


def score(finding: Finding, *,
          exposure_index: Optional[ExposureIndex] = None,
          kev_index: Optional[KevIndex] = None) -> ScoreResult:
    """Score one finding → ScoreResult(tier, rationale, axes...).

    Pure given the two injected indexes (both optional; when omitted the axes
    degrade to their safe/visible defaults: internal exposure, UNKNOWN
    exploited). The rationale explains WHY the tier landed where it did.
    """
    nature, nnote = compute_nature(finding)
    exposure, enote = compute_exposure(finding, exposure_index)
    exploited, ereason = compute_exploited(finding, kev_index)

    tier = tier_for(exposure, exploited, nature)
    unknown = exploited is None and nature == VULN

    if nature == POLICY:
        rationale = f"{nature} ({nnote}) → LOW (against-policy / hygiene)"
    else:
        bits = [exposure, _exploited_word(exploited), "CVE/vuln"]
        rationale = f"{' + '.join(bits)} → {tier.upper()}"
        if unknown:
            rationale += f"  [exploited UNKNOWN: {ereason} — visible, not scored safe]"
        # note the gate collapse explicitly so the board is auditable
        if exposure == EXTERNAL_AUTH:
            rationale += "  (auth-gated: external reach, un-authed surface = internal)"

    return ScoreResult(
        tier=tier,
        rationale=rationale,
        exposure=exposure,
        exploited=exploited,
        exploited_reason=ereason,
        nature=nature,
        unknown_exploited=unknown,
        finding=finding,
        exposure_note=enote,
    )
