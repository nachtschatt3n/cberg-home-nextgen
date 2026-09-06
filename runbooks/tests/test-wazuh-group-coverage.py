"""Regression tests for the Wazuh rule.groups triage (security-check.py s13).

GROUND TRUTH, aggregated from our OWN indexer on 2026-09-06 over 7 days. These
counts are why this test exists -- every one of these groups is real traffic in
this cluster, and the triage set named none of them:

    attack                2267   (was in the set)
    agent_flooding          20   MISSING
    attacks                 19   MISSING  <-- the plural. Wazuh ships BOTH.
    configuration_failure    5   MISSING
    recon                    1   MISSING, and below any volume floor
    web_scan                 1   MISSING, and below any volume floor

`attacks` being absent while `attack` was present is the headline: an attacks
burst scored GREEN. `recon`/`web_scan` are the subtler half -- adding them to a
set with a `> 5` floor would still never have reported them.

Run:  python3 runbooks/tests/test-wazuh-group-coverage.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("sc", REPO / "runbooks/security-check.py")
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


CONCERNING = {"authentication_failed", "authentication_failures", "web_attack",
              "attack", "attacks", "rootcheck", "syscheck", "ids", "ipsec",
              "agent_flooding", "configuration_failure"}
RARE = {"intrusion_detection", "privilege_escalation", "recon", "web_scan"}


def buckets(**kw):
    return [{"key": k, "doc_count": n} for k, n in kw.items()]


def flag(**kw):
    return dict(sc.flag_wazuh_groups(buckets(**kw), CONCERNING, RARE))


def main() -> int:
    print("wazuh group coverage:")

    # --- the bug this file is named for ---------------------------------------
    check("`attacks` (plural) is triaged, not silently dropped",
          "attacks" in flag(attacks=19), str(flag(attacks=19)))
    check("`attack` (singular) still works — the fix did not swap one for the other",
          "attack" in flag(attack=2267))
    check("both plural and singular survive in one batch",
          set(flag(attack=2267, attacks=19)) == {"attack", "attacks"})

    # --- the groups the live aggregation proved we emit ------------------------
    check("agent_flooding is triaged (a dropping agent is a BLIND siem)",
          "agent_flooding" in flag(agent_flooding=20))
    check("configuration_failure is triaged",
          "configuration_failure" in flag(configuration_failure=6))

    # --- the two-tier floor ----------------------------------------------------
    # A single recon or web_scan event is the whole signal; a volume floor
    # designed for 2,267 `attack` events erases it.
    check("a SINGLE recon event is reported (rare tier ignores the volume floor)",
          flag(recon=1) == {"recon": 1}, str(flag(recon=1)))
    check("a SINGLE web_scan event is reported",
          flag(web_scan=1) == {"web_scan": 1})
    check("a low-volume noisy group stays below the floor",
          flag(attack=3) == {}, str(flag(attack=3)))
    check("the floor is exclusive, not inclusive, at the boundary",
          flag(attack=5) == {} and flag(attack=6) == {"attack": 6},
          f"5->{flag(attack=5)} 6->{flag(attack=6)}")

    # --- discrimination --------------------------------------------------------
    # A triage that flags everything is as useless as one that flags nothing.
    check("unlisted benign groups are NOT flagged at any volume",
          flag(homelab=4270, web=3044, ingress=2846, falco=1424) == {},
          str(flag(homelab=4270, web=3044)))
    check("an empty aggregation yields nothing (and does not raise)",
          sc.flag_wazuh_groups([], CONCERNING, RARE) == [])

    # --- the live shape, end to end -------------------------------------------
    live = flag(homelab=4270, web=3044, ingress=2846, attack=2267, falco=1424,
                ossec=1179, accesslog=197, access_control=113,
                authentication_failed=113, agent_flooding=20, attacks=19,
                configuration_failure=5, recon=1, web_scan=1)
    check("on the real 7d aggregation, the previously-invisible groups surface",
          {"attacks", "agent_flooding", "recon", "web_scan"} <= set(live),
          str(sorted(live)))
    # configuration_failure=5 is AT the floor, so it must not appear — the live
    # data sits exactly on the boundary, which is worth pinning deliberately.
    check("configuration_failure at exactly 5 stays below the volume floor",
          "configuration_failure" not in live, str(sorted(live)))

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all wazuh group-coverage tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
