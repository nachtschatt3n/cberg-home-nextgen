"""Unit tests for the contextual risk-scoring model (risk_model.py).

Covers every cell of the exposure × exploited × nature matrix, the fail-soft
UNKNOWN behaviour, the exposure classifier (incl. the AR-059 Authentik-outpost
detection and AR-004 self-auth override), KEV membership, and the four
ground-truth scenarios the operator named (auth-gated external, plain external, a pure policy
finding, an internal DB image).

Run:  python3 -m pytest runbooks/lib/test_risk_model.py -q
  or: python3 runbooks/lib/test_risk_model.py   (falls back to a tiny runner)
"""

from __future__ import annotations

import importlib.util
import itertools
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "risk_model", str(Path(__file__).with_name("risk_model.py")))
rm = importlib.util.module_from_spec(_spec)
# Register BEFORE exec: @dataclass with `from __future__ import annotations`
# resolves the string type hints via sys.modules[cls.__module__].
sys.modules["risk_model"] = rm
_spec.loader.exec_module(rm)


# ---------------------------------------------------------------------------
# 1. The pure tier matrix — EVERY cell
# ---------------------------------------------------------------------------

EXPOSURES = [rm.EXTERNAL_UNAUTH, rm.EXTERNAL_AUTH, rm.INTERNAL, rm.CLUSTER_ONLY]
EXPLOITED = [True, False, None]

# expected tier for nature == VULN, keyed by (exposure, exploited)
_VULN_EXPECT = {
    (rm.EXTERNAL_UNAUTH, True):  rm.CRITICAL,
    (rm.EXTERNAL_UNAUTH, False): rm.HIGH,
    (rm.EXTERNAL_UNAUTH, None):  rm.HIGH,
    (rm.EXTERNAL_AUTH, True):    rm.HIGH,
    (rm.EXTERNAL_AUTH, False):   rm.MEDIUM,
    (rm.EXTERNAL_AUTH, None):    rm.MEDIUM,
    (rm.INTERNAL, True):         rm.HIGH,
    (rm.INTERNAL, False):        rm.MEDIUM,
    (rm.INTERNAL, None):         rm.MEDIUM,
    (rm.CLUSTER_ONLY, True):     rm.HIGH,
    (rm.CLUSTER_ONLY, False):    rm.MEDIUM,
    (rm.CLUSTER_ONLY, None):     rm.MEDIUM,
}


def test_matrix_vuln_every_cell():
    for exp, expl in itertools.product(EXPOSURES, EXPLOITED):
        got = rm.tier_for(exp, expl, rm.VULN)
        want = _VULN_EXPECT[(exp, expl)]
        assert got == want, f"VULN {exp}/{expl}: got {got}, want {want}"


def test_matrix_policy_every_cell_is_low():
    for exp, expl in itertools.product(EXPOSURES, EXPLOITED):
        assert rm.tier_for(exp, expl, rm.POLICY) == rm.LOW, f"POLICY {exp}/{expl} must be LOW"


def test_only_public_exploited_is_critical():
    criticals = [(e, x) for e, x in itertools.product(EXPOSURES, EXPLOITED)
                 if rm.tier_for(e, x, rm.VULN) == rm.CRITICAL]
    assert criticals == [(rm.EXTERNAL_UNAUTH, True)], criticals


# ---------------------------------------------------------------------------
# 2. nature classification (explicit table + s4 overrides)
# ---------------------------------------------------------------------------

def test_nature_table():
    assert rm.compute_nature(rm.Finding("s4_cve_check", "`x:1` 1 CRITICAL"))[0] == rm.VULN
    assert rm.compute_nature(rm.Finding("s2_sensitive_exposure", "plaintext"))[0] == rm.VULN
    assert rm.compute_nature(rm.Finding("s3_git_history", "cred"))[0] == rm.VULN
    assert rm.compute_nature(rm.Finding("s10_flux_posture", "drift"))[0] == rm.POLICY
    assert rm.compute_nature(rm.Finding("s7_rbac_pod_security", "privileged"))[0] == rm.POLICY


def test_s4_floating_tag_override_is_policy():
    n, note = rm.compute_nature(rm.Finding(
        "s4_cve_check",
        "`app:latest`: floating tag — posture is unknowable; pin an immutable version"))
    assert n == rm.POLICY, note


def test_s4_scan_coverage_gap_override_is_policy():
    n, _ = rm.compute_nature(rm.Finding(
        "s4_cve_check", "Trivy scan coverage gap: CVE status UNKNOWN"))
    assert n == rm.POLICY


def test_unknown_section_defaults_vuln_not_hidden():
    assert rm.compute_nature(rm.Finding("s99_new", "??"))[0] == rm.VULN


# ---------------------------------------------------------------------------
# 3. exposure classifier — AR-059 outpost detection + AR-004 self-auth
# ---------------------------------------------------------------------------

def _ing(name, ns, host, svc, cls="external", path="/"):
    return {
        "metadata": {"name": name, "namespace": ns},
        "spec": {
            "ingressClassName": cls,
            "rules": [{"host": host, "http": {"paths": [
                {"path": path, "backend": {"service": {"name": svc}}}]}}],
        },
    }


def _sample_index():
    items = [
        # uptime-kuma: main ingress routes / to the outpost service (gated)
        _ing("uptime-kuma", "monitoring", "kuma.d", "uptime-kuma-authentik-outpost"),
        _ing("uptime-kuma-authentik-outpost", "monitoring", "kuma.d",
             "uptime-kuma-authentik-outpost", path="/outpost.goauthentik.io"),
        # absenty: plain external, own backend (unauth structurally)
        _ing("absenty", "my-software-production", "absenty.d", "absenty"),
        # librechat: ingress name differs from image token
        _ing("librechat-librechat", "ai", "librechat.d", "librechat"),
        # open-webui: external + AR-004 self-auth
        _ing("open-webui", "ai", "open-webui.d", "open-webui"),
        # an internal ingress
        _ing("grafana", "monitoring", "grafana.internal", "grafana", cls="internal"),

        # --- synthetic entries for the SCORING tests below ---
        # The classifier tests above name real services on purpose: which
        # ingress class a service uses is topology, already public in the
        # manifests and docs/infrastructure.md, and they assert nothing about
        # its vulnerability state.
        #
        # The scoring tests are different — they combine a component with a
        # severity and an exposure tier, and "exposure combined with unfixed
        # state" is the not-publishable cell in
        # docs/sops/vulnerability-disclosure.md §2.1. They therefore run
        # against these synthetic services, which reproduce the same four
        # shapes without naming anything we run.
        _ing("svc-ext-auth", "example", "auth.example",
             "svc-ext-auth-authentik-outpost"),
        _ing("svc-ext-auth-authentik-outpost", "example", "auth.example",
             "svc-ext-auth-authentik-outpost", path="/outpost.goauthentik.io"),
        _ing("svc-ext-unauth", "example", "open.example", "svc-ext-unauth"),
        _ing("svc-internal", "example", "internal.example", "svc-internal",
             cls="internal"),
    ]
    return rm.build_exposure_index(items, [])


def test_exposure_authentik_gated_is_external_auth():
    idx = _sample_index()
    tier, note = idx.classify(["uptime-kuma"])
    assert tier == rm.EXTERNAL_AUTH, note


def test_exposure_plain_external_is_unauth():
    idx = _sample_index()
    assert idx.classify(["absenty"])[0] == rm.EXTERNAL_UNAUTH


def test_exposure_token_prefix_match():
    # image token "librechat" must resolve ingress "librechat-librechat"
    idx = _sample_index()
    assert idx.classify(["librechat"])[0] == rm.EXTERNAL_UNAUTH


def test_exposure_self_auth_override():
    idx = _sample_index()
    tier, note = idx.classify(["open-webui"])
    assert tier == rm.EXTERNAL_AUTH and "AR-004" in note, note


def test_exposure_unmatched_defaults_internal():
    idx = _sample_index()
    assert idx.classify(["postgres"])[0] == rm.INTERNAL
    assert idx.classify([])[0] == rm.INTERNAL


# ---------------------------------------------------------------------------
# 4. KEV / exploited tri-state (fail-soft VISIBLE, never silent false)
# ---------------------------------------------------------------------------

def test_kev_hit():
    kev = rm.KevIndex(cve_ids={"CVE-2099-0001"}, loaded=True, source="test")
    state, reason = kev.is_exploited(["CVE-2099-0001", "CVE-9999-0000"])
    assert state is True and reason == rm.EXPLOITED_KEV


def test_kev_miss_is_false():
    kev = rm.KevIndex(cve_ids={"CVE-2099-0001"}, loaded=True, source="test")
    assert kev.is_exploited(["CVE-9999-0000"]) == (False, rm.NOT_EXPLOITED)


def test_no_cve_ids_is_unknown_not_false():
    kev = rm.KevIndex(cve_ids={"CVE-2099-0001"}, loaded=True, source="test")
    state, reason = kev.is_exploited([])
    assert state is None and reason == rm.UNKNOWN_NO_CVE


def test_feed_unavailable_is_unknown_not_false():
    kev = rm.KevIndex(loaded=False, source="unavailable")
    state, reason = kev.is_exploited(["CVE-2099-0001"])
    assert state is None and reason == rm.UNKNOWN_FEED


# ---------------------------------------------------------------------------
# 5. Ground-truth scenarios (must pass — these are what the operator judges)
# ---------------------------------------------------------------------------

def _kev(*cves):
    return rm.KevIndex(cve_ids=set(cves), loaded=True, source="test")


def test_ground_truth_external_auth_gated_is_not_critical():
    """external BUT Authentik-gated, unpatchable, not in KEV → MEDIUM (not critical)."""
    idx = _sample_index()
    f = rm.Finding("s4_cve_check",
                   "`svc-ext-auth:1`: CRITICAL CVE(s)", component="svc-ext-auth",
                   cve_ids=["CVE-9999-1"], intrinsic_severity="critical")
    r = rm.score(f, exposure_index=idx, kev_index=_kev("CVE-2099-0001"))
    assert r.exposure == rm.EXTERNAL_AUTH
    assert r.tier in (rm.MEDIUM, rm.HIGH)
    assert r.tier != rm.CRITICAL
    assert r.tier == rm.MEDIUM   # external-auth + not-KEV → MEDIUM


def test_ground_truth_external_auth_gated_in_kev_is_high_not_critical():
    """Honest argument: even if its CVE were in KEV, an auth-gated external
    service is HIGH, not the 3am CRITICAL page."""
    idx = _sample_index()
    f = rm.Finding("s4_cve_check", "`svc-ext-auth:1`", component="svc-ext-auth",
                   cve_ids=["CVE-2099-0001"])
    r = rm.score(f, exposure_index=idx, kev_index=_kev("CVE-2099-0001"))
    assert r.tier == rm.HIGH


def test_ground_truth_external_unauth_is_high_and_kev_makes_it_critical():
    idx = _sample_index()
    # not in KEV → external-unauth + real vuln + not-exploited → HIGH
    f = rm.Finding("s4_cve_check", "`svc-ext-unauth:1`: CRITICAL",
                   component="svc-ext-unauth",
                   cve_ids=["CVE-9999-2"], intrinsic_severity="critical")
    r = rm.score(f, exposure_index=idx, kev_index=_kev("CVE-2099-0001"))
    assert r.exposure == rm.EXTERNAL_UNAUTH
    assert r.tier == rm.HIGH
    # and if KEV moved it → CRITICAL
    f2 = rm.Finding("s4_cve_check", "`svc-ext-unauth:1`", component="svc-ext-unauth",
                    cve_ids=["CVE-2099-0001"])
    assert rm.score(f2, exposure_index=idx, kev_index=_kev("CVE-2099-0001")).tier == rm.CRITICAL


def test_ground_truth_policy_finding_is_low():
    f = rm.Finding("s4_cve_check",
                   "`app:latest`: floating tag — posture is unknowable; pin it",
                   component="app")
    r = rm.score(f, exposure_index=_sample_index(), kev_index=_kev())
    assert r.tier == rm.LOW


def test_ground_truth_internal_criticals_is_medium():
    """internal-only service, fixable criticals, not exploited → MEDIUM."""
    idx = _sample_index()
    f = rm.Finding("s4_cve_check", "`svc-internal:1`: CRITICAL",
                   component="svc-internal",
                   cve_ids=["CVE-9999-3"], intrinsic_severity="critical")
    r = rm.score(f, exposure_index=idx, kev_index=_kev("CVE-2099-0001"))
    assert r.exposure == rm.INTERNAL
    assert r.tier == rm.MEDIUM


def test_internal_db_with_kev_cve_is_high():
    """The real superset/redis case: internal + KEV CVE → HIGH (not demoted to MEDIUM)."""
    idx = _sample_index()
    f = rm.Finding("s4_cve_check", "`redis:7`: CVE-2099-0001", component="redis",
                   cve_ids=["CVE-2099-0001"], intrinsic_severity="critical")
    r = rm.score(f, exposure_index=idx, kev_index=_kev("CVE-2099-0001"))
    assert r.tier == rm.HIGH


def test_unknown_exploited_flag_is_visible_in_rationale():
    idx = _sample_index()
    f = rm.Finding("s4_cve_check", "`internal-img:1`: 2 CRITICAL", component="internal-img",
                   cve_ids=[])  # no CVE ids → unknown
    r = rm.score(f, exposure_index=idx, kev_index=_kev("CVE-2099-0001"))
    assert r.unknown_exploited is True
    assert "UNKNOWN" in r.rationale


# ---------------------------------------------------------------------------
# tiny runner so `python3 test_risk_model.py` works without pytest
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
