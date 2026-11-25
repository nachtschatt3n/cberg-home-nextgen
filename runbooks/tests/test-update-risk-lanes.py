"""Graded risk model (lib/update_risk.py + auto-update.py::classify): every lane,
and every FAIL-CLOSED branch, must hold with hermetic inputs.

Proves (and a gate that only prints is not a gate, so each is asserted on bad AND
good input):
  * an EMPTY "Breaking Changes" heading is not a signal; a LISTED item is
  * a removal item whose tokens are absent from our manifests is cleared (patch
    only); an obligation item ("unless X is set") is NEVER cleared that way
  * `breaking_ack` clears one item, needs evidence + an unexpired `until`, and
    does not cover a different item
  * release notes unreadable => PLAN (breaking-unverified), never AUTO — the
    authentik fail-open, closed
  * migration + declared tracked protection => AUTO-BACKUP-GATED; migration with
    no protection => PLAN; a protection entry whose dump job is not in git => PLAN
  * a deny rule with `lane: weekend-attended` => WEEKEND-ATTENDED
  * the real policy: valkey/otel holds gone, authentik reason current, core
    components weekend-attended, longhorn V2-clone ack present and dated

Run: python3 runbooks/tests/test-update-risk-lanes.py
"""
from __future__ import annotations
import datetime as dt, importlib.util, os, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.environ.setdefault("_MISE_ACTIVATED", "1")
sys.path.insert(0, str(REPO / "runbooks" / "lib"))
import update_risk as ur  # noqa: E402

spec = importlib.util.spec_from_file_location("au_risk", REPO / "runbooks/auto-update.py")
au = importlib.util.module_from_spec(spec)
spec.loader.exec_module(au)

FAILS = []
def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {str(detail)[:300]}"))
    if not ok: FAILS.append(name)

def grade(body, utype="patch", corpus=None, acks=None, today=None):
    return ur.assess_notes(body, dep="acme/app", version="1.2.3", utype=utype,
                           corpus=corpus, acks=acks, today=today)

# ── notes reading ─────────────────────────────────────────────────────────────
check("empty Breaking Changes heading does not block",
      grade("## Breaking Changes\n\n## Fixes\n- a thing")["blocking"] == [])
check("'None' under Breaking Changes does not block",
      grade("## Breaking Changes\n\nNone\n\n## Fixes\n- a")["blocking"] == [])
check("a LISTED item blocks",
      len(grade("## Breaking Changes\n- the API was reshaped\n")["blocking"]) == 1)
check("empty body is UNREAD (caller must fail closed)", grade("")["read"] is False)
check("conventional `feat!:` line outside any section blocks",
      len(grade("## Changes\n- feat(api)!: drop v1")["blocking"]) == 1)
removal = "### Breaking changes\n- `OLD_OPT` was removed in favour of `NEW_OPT`\n"
check("removal item with tokens absent from our manifests is cleared on a PATCH",
      grade(removal, corpus="env:\n  FOO: 1")["blocking"] == [])
check("...but NOT on a minor", len(grade(removal, utype="minor", corpus="FOO")["blocking"]) == 1)
check("...and NOT when our manifests use the token",
      len(grade(removal, corpus="env: OLD_OPT=1")["blocking"]) == 1)
check("...and NOT when the corpus is unknown (None)", len(grade(removal, corpus=None)["blocking"]) == 1)
oblig = "### Breaking changes\n- Server-initiated HTTP now refuses private targets unless HTTP_ALLOW_LIST is set\n"
check("OBLIGATION item (token absent but we must ADD it) is never cleared",
      len(grade(oblig, corpus="FOO")["blocking"]) == 1)
check("upgrade-guide section is advisory on a patch",
      grade("## Upgrade\n- Ensure Kubernetes 1.25+ before upgrading\n")["blocking"] == [])
check("upgrade-guide section demanding action blocks a minor",
      len(grade("## Upgrade\n- You must run the migration tool before upgrading\n", utype="minor")["blocking"]) == 1)

check("a lowercase 'breaking' inside an ordinary fix bullet is NOT a signal",
      grade("## Fixes\n- [BACKPORT][v1.2.3][BUG] default policies broke a legitimate path (breaking scrapes)\n")["blocking"] == [])
check("an upper-case BREAKING marker line IS a signal", len(grade("BREAKING: dropped x")["blocking"]) == 1)

# ── acks ──────────────────────────────────────────────────────────────────────
body = "## Breaking Changes\n### Deprecation of Legacy V2 Linked Clone Volumes\nLegacy volumes cannot be operated on.\n"
ack = {"match": "*acme*", "needle": "Legacy V2 Linked Clone", "until": dt.date(2027, 1, 1), "evidence": "measured"}
T = dt.date(2026, 11, 25)
check("unacked listed item blocks", len(grade(body)["blocking"]) == 1)
check("acked item clears", grade(body, acks=[ack], today=T)["blocking"] == [])
check("expired ack is inert", len(grade(body, acks=[{**ack, "until": dt.date(2026, 1, 1)}], today=T)["blocking"]) == 1)
check("ack without evidence is inert", len(grade(body, acks=[{**ack, "evidence": ""}], today=T)["blocking"]) == 1)
check("ack without `until` is inert", len(grade(body, acks=[{k: v for k, v in ack.items() if k != "until"}], today=T)["blocking"]) == 1)
check("ack does not cover a DIFFERENT item",
      len(grade(body + "\n### Another thing\nremoved the `export` command\n", acks=[ack], today=T)["blocking"]) == 1)

# ── lanes ─────────────────────────────────────────────────────────────────────
prot = {"dump_job": "d.yaml", "restore_proof": "proof"}
check("clean => AUTO", ur.decide_lane()[0] == "AUTO")
check("blocking evidence => PLAN", ur.decide_lane(blocking=["x"])[0] == "PLAN")
check("notes unread => PLAN (fail closed)", ur.decide_lane(notes_read=False)[0] == "PLAN")
check("notes unread but EARNED => proceeds", ur.decide_lane(notes_read=False, earned_ok=True)[0] == "AUTO")
check("migration + protection => AUTO-BACKUP-GATED", ur.decide_lane(migration=True, protection=prot)[0] == "AUTO-BACKUP-GATED")
check("migration, NO protection => PLAN", ur.decide_lane(migration=True)[0] == "PLAN")
check("migration + protection but breaking evidence => PLAN", ur.decide_lane(migration=True, protection=prot, blocking=["x"])[0] == "PLAN")
check("weekend rule wins over everything", ur.decide_lane(rule_lane="weekend-attended", blocking=["x"])[0] == "WEEKEND-ATTENDED")

# ── protection must be REAL (dump job tracked in git) ─────────────────────────
POL = au.load_policy()
e, why = ur.protection_for(POL, ["teslamate/teslamate"], REPO)
check("teslamate has a tracked dump + restore proof", e is not None and e["volume"] == "teslamate-db", why)
e, why = ur.protection_for(POL, ["ghcr.io/open-webui/open-webui"], REPO)
check("open-webui has NO declared protection", e is None, why)
fake = {"data_protection": [{"match": "ghost", "volume": "v", "dump_job": "kubernetes/nope.yaml", "restore_proof": "p"}]}
e, why = ur.protection_for(fake, ["ghost"], REPO)
check("entry naming an untracked dump job is refused", e is None and "not tracked" in why, why)
e, why = ur.protection_for({"data_protection": [{"match": "g", "volume": "v", "dump_job": "runbooks/auto-update.py"}]}, ["g"], REPO)
check("entry without a restore_proof is refused", e is None, why)

# ── classify(): the fail-closed branch, with the network stubbed ──────────────
au.pr_files = lambda n: ["kubernetes/apps/kube-system/authentik/app/helmrelease.yaml"]
au.ci_state = lambda n: (True, "green")
au.age_gate = lambda *a, **k: None
au.structural_signal = lambda *a, **k: ([], True, "clean")
au.fast_lane.earned = lambda policy, keys: (False, "no track record")
PR = {"number": 1, "title": "fix(container): update goauthentik/server ( 2026.8.5 → 2026.8.6 )",
      "labels": [{"name": "type/patch"}], "isDraft": False}
NOPOL = {"deny": []}
au.breaking_signal = lambda *a, **k: ([], False)
c = au.classify(PR, NOPOL, object())
check("notes UNREADABLE => hold, lane PLAN, gate breaking-unverified (authentik fail-open closed)",
      c["verdict"] == "hold" and c["lane"] == "PLAN" and c["gate"] == "breaking-unverified", c)
au.breaking_signal = lambda *a, **k: ([], True)
c = au.classify(PR, NOPOL, object())
check("notes read + clean => safe AUTO", c["verdict"] == "safe" and c["lane"] == "AUTO", c)
au.breaking_signal = lambda *a, **k: (["Breaking Changes: x [listed breaking item]"], True)
c = au.classify(PR, NOPOL, object())
check("listed breaking item => PLAN", c["verdict"] == "hold" and c["gate"] == "breaking", c)
au.breaking_signal = lambda *a, **k: ([], True)
au.structural_signal = lambda *a, **k: (["new migration file x"], True, "")
c = au.classify({**PR, "title": "fix(container): update teslamate/teslamate ( 4.4.0 → 4.4.1 )"}, NOPOL, object())
POL2 = {"deny": [], "data_protection": POL["data_protection"]}
c = au.classify({**PR, "title": "fix(container): update teslamate/teslamate ( 4.4.0 → 4.4.1 )"}, POL2, object())
check("migration + declared restore path => AUTO-BACKUP-GATED hold (never merged by auto-update)",
      c["verdict"] == "hold" and c["lane"] == "AUTO-BACKUP-GATED" and c.get("backup_gate"), c)
c = au.classify({**PR, "title": "fix(container): update some/unprotected ( 1.0.0 → 1.0.1 )"}, POL2, object())
check("migration, no protection => PLAN", c["verdict"] == "hold" and c["lane"] == "PLAN", c)
au.structural_signal = lambda *a, **k: ([], True, "clean")
RULE = {"deny": [{"match": "*cilium*", "lane": "weekend-attended", "reason": "cni"}]}
c = au.classify({**PR, "title": "fix(container): update cilium ( 1.20.4 → 1.20.5 )"}, RULE, object())
check("deny rule lane: weekend-attended is carried", c["lane"] == "WEEKEND-ATTENDED", c)
c = au.classify({**PR, "title": "feat(container)!: Update cilium ( 1.20.4 → 2.0.0 )", "labels": [{"name": "type/major"}]}, RULE, object())
check("a MAJOR of a core component is WEEKEND-ATTENDED too", c["lane"] == "WEEKEND-ATTENDED", c)

# ── the REAL policy ───────────────────────────────────────────────────────────
matches = [r["match"] for r in POL["deny"]]
check("valkey interim hold retired (GA 9.1.3/9.1.4/9.2.0 published, digest != rc1)", "*valkey*" not in matches)
check("otel-kube-stack hold retired (gate arg live, 0 NetworkPolicy rendered)", "*opentelemetry-kube-stack*" not in matches)
check("otel collector config hold KEPT", "otel/opentelemetry-collector-contrib" in matches)
ha = next(r for r in POL["deny"] if "home-assistant" in r["match"])
check("HA: patches allowed ONLY behind the integration gate (max patch + post_apply_gate)",
      ha.get("max") == "patch" and ha.get("post_apply_gate") == "ha-integration", ha)
check("HA: a minor is still blocked (PLAN)", au.policy_block(POL, "ghcr.io/home-assistant/home-assistant", "minor") is not None)
check("HA: a patch is not blocked by the rule", au.policy_block(POL, "ghcr.io/home-assistant/home-assistant", "patch") is None)
check("rule_gate reads the gate even for an allowed type",
      au.rule_gate(POL, "ghcr.io/home-assistant/home-assistant", "patch") == "ha-integration")
import inspect
_main_src = inspect.getsource(au.main)
check("apply path snapshots BEFORE merging and compares AFTER (wired, not just documented)",
      _main_src.index("ha_gate_snapshot(") < _main_src.index("merge_pr(") < _main_src.index("ha_gate_compare("))
check("a failed HA compare flips ok to False (revert path)", "HA integration gate FAILED" in _main_src)
check("an unreadable snapshot drops the HA PR from the merge plan", "NOT merging" in _main_src and "snapshot unavailable" in _main_src)
cspec = importlib.util.spec_from_file_location("cov_risk", REPO / "runbooks/coverage.py")
cov = importlib.util.module_from_spec(cspec); cspec.loader.exec_module(cov)
_it = {"component": "home-assistant", "kind": "image", "type": "patch", "current": "2026.11.2",
       "target": "2026.11.3", "image_repo": "ghcr.io/home-assistant/home-assistant"}
cov.direct_bump_age_gate = lambda item, policy: None
cov._direct_bump_breaking_gate = lambda item: (False, "clean (release notes checked)")
cov._direct_bump_structural_gate = lambda item: (False, "clean (diff checked: stub)")
cov._g3_range_gate = lambda item: ("n/a", "")
cov.prerelease_target_hold = lambda item: None
lane, why, _ = cov.assign_lane(dict(_it), POL, {}, [])
check("direct-bump HA patch WITHOUT a PR => PLAN (no post-apply hook there)", lane == "PLAN" and "post-apply" in why, (lane, why))
lane, why, _ = cov.assign_lane(dict(_it), POL, {"home-assistant": [cov._pr_record(583, "ghcr.io/home-assistant/home-assistant")]}, [])
check("HA patch WITH a Renovate PR => AUTO via the gated PR path", lane == "AUTO", (lane, why))
for core in ("*cilium*", "*gateway-helm*", "*coredns*", "*longhorn*", "*external-dns*", "siderolabs/*", "*talos*", "*flux-operator*"):
    r = next(x for x in POL["deny"] if x["match"] == core)
    check(f"core rule {core} is weekend-attended", r.get("lane") == "weekend-attended", r)
auth = next(x for x in POL["deny"] if x["match"] == "*authentik*")
check("authentik reason is current (split PRs, fail-closed resolved)", "SEPARATE PRs" in auth["reason"] and "RESOLVED" in auth["reason"])
lh = [a for a in POL.get("breaking_ack", []) if "longhorn" in a["match"]]
check("longhorn V2-clone ack is dated + has evidence", bool(lh) and lh[0].get("until") and lh[0].get("evidence"), lh)
check("policy parses and is not deny-all", not POL.get("_deny_all"))

print("\nFAILED: %d" % len(FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)
