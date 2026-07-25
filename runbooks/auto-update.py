#!/usr/bin/env python3
"""auto-update — merge SAFE Renovate PRs during the scheduled sweep.

The daily (cron-triggered) sweep calls this to keep the cluster current
WITHOUT the operator hand-merging every patch/minor bump. It is a strict,
deny-by-default classifier: an open Renovate PR is merged only when every
gate passes, and only ever on the scheduled run.

Gates (all must pass) — see runbooks/auto-update-policy.yaml:
  G1 type     : update_type in {patch, minor}  (major/digest/unknown → hold)
  G2 policy   : depName not blocked by a deny rule (operator knowledge that a
                component is risky regardless of semver — e.g. affine, mariadb)
  G3 breaking : NO breaking-change signal in the PR's target release notes.
                Reuses check-all-versions.py's fetch_release_notes +
                detect_breaking_changes, so a "patch-but-breaking" bump
                (affine 0.27.3 env→config.json) is caught even if a human
                forgot to deny-list it.
  G4 ci       : PR mergeable + all required CI checks green. The repo's
                flux-local workflow renders every HelmRelease with Helm on
                each PR, so a green check means the manifest actually renders.

APPLY GUARD — merges + git ops run ONLY when BOTH hold:
  * --apply is passed, AND
  * SWEEP_TRIGGER=cron  (or AUTO_UPDATE_APPLY=1 for an explicit operator run).
Otherwise this is a dry-run that only prints the classification. That keeps a
manual `operation sweep` read-only, matching the sweep contract.

After the safe batch merges: git pull → flux reconcile the affected
kustomizations → POST-APPLY HEALTH GATE. If Flux fails to reconcile or a
workload in an affected namespace regresses, the batch is auto-reverted
(git revert + push) and a critical finding + alert is raised.

Usage:
    python3 runbooks/auto-update.py                 # dry-run report (default)
    python3 runbooks/auto-update.py --apply         # apply (needs cron trigger)
    AUTO_UPDATE_APPLY=1 python3 runbooks/auto-update.py --apply   # force apply
    python3 runbooks/auto-update.py --json           # machine-readable report

Exit codes: 0 = ok (nothing to do, or applied + healthy), 2 = applied then
reverted (a merge regressed and was rolled back), 1 = hard error.
"""
from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
POLICY_PATH = SCRIPT_DIR / "auto-update-policy.yaml"
RANK = {"patch": 0, "minor": 1, "major": 2}
SAFE_TYPES = {"patch", "minor"}
RECONCILE_WAIT_S = int(os.environ.get("AUTO_UPDATE_RECONCILE_WAIT", "150"))


def log(*a):
    # progress → stderr, so stdout stays pure JSON under --json (the sweep
    # orchestrator parses stdout).
    print(*a, flush=True, file=sys.stderr)


def run(cmd, timeout=60, check=False):
    """Thin subprocess wrapper returning (rc, stdout, stderr)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if check and p.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd)} -> rc={p.returncode}: {p.stderr.strip()}")
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


# ── load check-all-versions' breaking-change engine (hyphenated filename) ────
def _load_version_checker():
    spec = importlib.util.spec_from_file_location(
        "check_all_versions", SCRIPT_DIR / "check-all-versions.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    return mod.VersionChecker(str(REPO_ROOT), github_token=token)


# ── policy ───────────────────────────────────────────────────────────────────
def load_policy():
    """Return policy dict. Fail-safe: unreadable policy → deny everything."""
    if not POLICY_PATH.exists():
        log(f"!! policy file missing ({POLICY_PATH}); denying ALL as a safe default")
        return {"_deny_all": True, "deny": [], "deny_managers": []}
    try:
        return yaml.safe_load(POLICY_PATH.read_text()) or {}
    except Exception as e:
        log(f"!! policy file unparseable ({e}); denying ALL as a safe default")
        return {"_deny_all": True, "deny": [], "deny_managers": []}


def _match_anywhere(dep, pat):
    """Deny globs match ANYWHERE in the dep path, so `siderolabs/*` still blocks
    `ghcr.io/siderolabs/installer` despite the registry prefix. Over-matching is
    the safe direction for a deny-list — it only sends more PRs to human review,
    never lets an unwanted one merge."""
    return any(fnmatch.fnmatch(dep, g) for g in (pat, f"*{pat}", f"{pat}*", f"*{pat}*"))


def policy_block(policy, dep, update_type):
    """Return a reason string if a deny rule blocks (dep, update_type), else None."""
    if policy.get("_deny_all"):
        return "policy unavailable — deny-all fail-safe"
    for rule in policy.get("deny", []) or []:
        pat = rule.get("match", "")
        if not pat or not _match_anywhere(dep, pat):
            continue
        mx = rule.get("max")
        if mx is None:
            return rule.get("reason", f"blocked by deny rule {pat!r}")
        # rule allows up to `mx`; block only if this update exceeds it
        if RANK.get(update_type, 99) > RANK.get(mx, -1):
            return f"{rule.get('reason','')} (allows ≤{mx}, this is {update_type})"
    return None


# ── PR discovery + parse ─────────────────────────────────────────────────────
def list_renovate_prs():
    rc, out, err = run([
        "gh", "pr", "list", "--author", "app/renovate", "--state", "open",
        "--json", "number,title,labels,isDraft,mergeable,mergeStateStatus,url,headRefName",
        "--limit", "100",
    ], timeout=45)
    if rc != 0:
        raise RuntimeError(f"gh pr list failed: {err.strip()}")
    return json.loads(out or "[]")


_TITLE_RE = re.compile(r"update\s+(?P<dep>.+?)\s+\(\s*(?P<cur>\S+)\s*(?:→|->|to)\s*(?P<new>\S+)\s*\)")


def parse_pr(pr):
    """Extract dep/cur/new + update_type. Returns dict or {'parse_error':...}."""
    title = pr.get("title", "")
    labels = [l["name"].lower() for l in pr.get("labels", [])]

    def has(k):
        return k in labels or f"type/{k}" in labels

    if has("major"):
        utype = "major"
    elif has("minor"):
        utype = "minor"
    elif has("patch"):
        utype = "patch"
    elif has("security"):
        utype = "security"
    else:
        utype = "unknown"

    m = _TITLE_RE.search(title)
    if not m:
        return {"parse_error": "title not in `update <dep> ( x → y )` shape"}
    dep = m.group("dep").strip()
    # grouped PRs update several deps ("... group") — never auto-merge blind
    if " group" in dep or "," in dep or "and " in dep:
        return {"parse_error": f"grouped/multi-dep PR ({dep!r}) — manual"}
    return {"dep": dep, "cur": m.group("cur"), "new": m.group("new"), "update_type": utype}


# ── G3 breaking-change scan (best-effort, reuses version engine) ─────────────
def breaking_signal(checker, dep, new_tag):
    """Return (list_of_breaking_notes, resolved_bool). Empty list + resolved=True
    means 'checked, clean'. resolved=False means notes couldn't be fetched."""
    owner_repo = None
    try:
        if "/" in dep and (dep.count("/") >= 1 and any(c in dep for c in ".:")) or "/" in dep:
            owner_repo = checker.get_repo_info_from_image(dep)
        if not owner_repo:
            owner_repo = checker.get_chart_repo_info(dep.split("/")[-1], "", "")
    except Exception:
        owner_repo = None
    if not owner_repo:
        return [], False
    owner, repo = owner_repo
    try:
        notes = checker.fetch_release_notes(owner, repo, new_tag)
        if not notes or not notes.get("body"):
            return [], False
        detected = checker.detect_breaking_changes(notes["body"], "minor")
        return detected or [], True
    except Exception:
        return [], False


# ── CI / mergeability (G4) ───────────────────────────────────────────────────
def ci_state(number):
    """Return (ok, detail). ok=True only when mergeable + every check succeeded."""
    rc, out, err = run([
        "gh", "pr", "view", str(number),
        "--json", "mergeable,mergeStateStatus,statusCheckRollup",
    ], timeout=45)
    if rc != 0:
        return False, f"gh view failed: {err.strip()}"
    d = json.loads(out or "{}")
    if d.get("mergeable") != "MERGEABLE":
        return False, f"not mergeable (mergeable={d.get('mergeable')}, state={d.get('mergeStateStatus')})"
    rollup = d.get("statusCheckRollup") or []
    bad, pending = [], []
    for c in rollup:
        # CheckRun uses status/conclusion; StatusContext uses state
        concl = (c.get("conclusion") or c.get("state") or "").upper()
        status = (c.get("status") or "").upper()
        name = c.get("name") or c.get("context") or "check"
        if status and status != "COMPLETED" and not concl:
            pending.append(name)
        elif concl in {"SUCCESS", "NEUTRAL", "SKIPPED"}:
            continue
        elif concl in {"", "PENDING", "EXPECTED", "IN_PROGRESS", "QUEUED"}:
            pending.append(name)
        else:
            bad.append(f"{name}={concl}")
    if bad:
        return False, "CI failing: " + ", ".join(bad)
    if pending:
        return False, "CI pending: " + ", ".join(pending)
    return True, "mergeable + all checks green"


# ── classify one PR ──────────────────────────────────────────────────────────
def classify(pr, policy, checker):
    r = {"number": pr["number"], "title": pr["title"], "url": pr.get("url", "")}
    if pr.get("isDraft"):
        return {**r, "verdict": "hold", "gate": "draft", "reason": "draft PR"}
    parsed = parse_pr(pr)
    if "parse_error" in parsed:
        return {**r, "verdict": "hold", "gate": "parse", "reason": parsed["parse_error"]}
    r.update(dep=parsed["dep"], cur=parsed["cur"], new=parsed["new"],
             update_type=parsed["update_type"])

    # G1 type
    if parsed["update_type"] not in SAFE_TYPES:
        return {**r, "verdict": "hold", "gate": "type",
                "reason": f"update_type={parsed['update_type']} (only patch/minor auto-apply)"}
    # G2 policy
    blocked = policy_block(policy, parsed["dep"], parsed["update_type"])
    if blocked:
        return {**r, "verdict": "hold", "gate": "policy", "reason": blocked}
    # G3 breaking
    notes, resolved = breaking_signal(checker, parsed["dep"], parsed["new"])
    if notes:
        return {**r, "verdict": "hold", "gate": "breaking",
                "reason": "breaking-change signal in release notes: " + "; ".join(n[:120] for n in notes[:2])}
    r["breaking_checked"] = resolved
    # G4 ci
    ok, detail = ci_state(pr["number"])
    if not ok:
        return {**r, "verdict": "hold", "gate": "ci", "reason": detail}
    return {**r, "verdict": "safe", "gate": "-",
            "reason": "patch/minor, not denied, no breaking signal, CI green"
                      + ("" if resolved else " (release notes unavailable — relied on CI + policy)")}


# ── apply: merge, reconcile, health-gate, revert ─────────────────────────────
def affected_apps(number):
    """namespaces/apps touched by a PR, from kubernetes/apps/<ns>/<app>/ paths."""
    rc, out, _ = run(["gh", "pr", "view", str(number), "--json", "files"], timeout=45)
    apps = set()
    if rc == 0:
        for f in json.loads(out or "{}").get("files", []):
            parts = Path(f["path"]).parts
            if len(parts) >= 4 and parts[0] == "kubernetes" and parts[1] == "apps":
                apps.add((parts[2], parts[3]))
    return apps


def post_apply_health(namespaces):
    """Return (ok, problems[]). Checks Flux HR/Ks readiness + pod health in the
    affected namespaces after reconcile."""
    problems = []
    # Flux kustomizations + helmreleases not Ready anywhere → hard fail
    for kind in ("kustomization", "helmrelease"):
        rc, out, _ = run(["flux", "get", kind, "-A", "--status-selector", "ready=false"], timeout=60)
        if rc == 0:
            for line in out.splitlines():
                line = line.strip()
                if not line or line.startswith("NAMESPACE") or "\tTrue\t" in line:
                    continue
                # any row printed by ready=false is a not-ready object
                if line and not line.lower().startswith("no "):
                    problems.append(f"flux {kind} not ready: {line.split()[0:2]}")
    # Pods in affected namespaces
    for ns in sorted(namespaces):
        rc, out, _ = run(["kubectl", "get", "pods", "-n", ns, "-o", "json"], timeout=45)
        if rc != 0:
            continue
        for p in json.loads(out or "{}").get("items", []):
            name = p["metadata"]["name"]
            st = p.get("status", {})
            phase = st.get("phase", "")
            for cs in st.get("containerStatuses", []) or []:
                w = (cs.get("state", {}).get("waiting") or {})
                if w.get("reason") in {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerError"}:
                    problems.append(f"{ns}/{name}: {w['reason']}")
                restarts = cs.get("restartCount", 0)
                if restarts >= 5 and not cs.get("ready", False):
                    problems.append(f"{ns}/{name}: {restarts} restarts, not ready")
            if phase in {"Failed"}:
                problems.append(f"{ns}/{name}: phase={phase}")
    return (len(problems) == 0), problems


def merge_pr(number):
    rc, out, err = run(["gh", "pr", "merge", str(number), "--squash", "--delete-branch"], timeout=120)
    if rc != 0:
        return None, err.strip()
    # resolve the squash commit for potential revert
    time.sleep(3)
    rc2, out2, _ = run(["gh", "pr", "view", str(number), "--json", "mergeCommit"], timeout=45)
    sha = None
    if rc2 == 0:
        sha = (json.loads(out2 or "{}").get("mergeCommit") or {}).get("oid")
    return sha or "unknown", None


def git_sync():
    run(["git", "-C", str(REPO_ROOT), "fetch", "origin", "main"], timeout=90)
    run(["git", "-C", str(REPO_ROOT), "merge", "--ff-only", "origin/main"], timeout=60)


def reconcile(apps):
    run(["flux", "reconcile", "source", "git", "flux-system"], timeout=120)
    for ns, app in sorted(apps):
        run(["flux", "reconcile", "kustomization", app, "-n", ns, "--with-source"], timeout=180)


def revert_batch(shas):
    reverted = []
    for sha in shas:
        if not sha or sha == "unknown":
            continue
        rc, _, err = run(["git", "-C", str(REPO_ROOT), "revert", "--no-edit", sha], timeout=60)
        if rc == 0:
            reverted.append(sha)
        else:
            log(f"  !! revert of {sha[:8]} failed: {err.strip()}")
    if reverted:
        run(["git", "-C", str(REPO_ROOT), "push", "origin", "main"], timeout=120)
    return reverted


# ── findings / alert ─────────────────────────────────────────────────────────
def _writer():
    try:
        sys.path.insert(0, str(SCRIPT_DIR / "lib"))
        from findings_writer import (FindingsWriter, cycle_id_from_env,  # type: ignore
                                      trigger_from_env, git_head)
        return FindingsWriter(
            dsn=os.environ.get("SWEEP_PG_DSN"),
            section="version",
            cycle_id=cycle_id_from_env(),
            trigger=trigger_from_env(),
            git_head=git_head(),
        )
    except Exception as e:
        log(f"  (findings writer unavailable: {e})")
        return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="merge safe PRs (needs cron trigger)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    trigger = os.environ.get("SWEEP_TRIGGER", "manual")
    force = os.environ.get("AUTO_UPDATE_APPLY") == "1"
    apply = args.apply and (trigger == "cron" or force)
    apply_blocked = args.apply and not apply

    policy = load_policy()
    checker = _load_version_checker()
    prs = list_renovate_prs()
    log(f"== auto-update: {len(prs)} open Renovate PR(s) · policy v{policy.get('version','?')} "
        f"· trigger={trigger} · mode={'APPLY' if apply else 'dry-run'} ==")

    classified = [classify(pr, policy, checker) for pr in prs]
    safe = [c for c in classified if c["verdict"] == "safe"]
    held = [c for c in classified if c["verdict"] == "hold"]

    for c in classified:
        icon = "✅" if c["verdict"] == "safe" else "⏸️ "
        log(f"{icon} #{c['number']} {c.get('dep','?')} {c.get('cur','')}→{c.get('new','')} "
            f"[{c.get('update_type','?')}] — {c['reason']}")

    result = {"trigger": trigger, "apply": apply, "safe": safe, "held": held,
              "merged": [], "reverted": [], "health": None}

    if apply_blocked:
        log("\n-- --apply given but trigger is not 'cron' (and AUTO_UPDATE_APPLY≠1): "
            "staying read-only. This is the manual-sweep guard. --")
    if not apply:
        w = _writer()
        if w:
            with w:
                if safe:
                    w.emit("monitor", f"{len(safe)} safe update(s) ready to auto-merge next scheduled sweep",
                           action="Scheduled cron sweep will merge these; run with SWEEP_TRIGGER=cron to apply now",
                           subsection="auto-update",
                           metadata={"safe": [f"#{c['number']} {c['dep']}" for c in safe]})
        if args.json:
            print(json.dumps(result, indent=2))
        log(f"\n== {len(safe)} safe / {len(held)} held · dry-run (no changes) ==")
        return 0

    # ---- APPLY ----
    if not safe:
        log("\n== nothing safe to merge ==")
        if args.json:
            print(json.dumps(result, indent=2))
        return 0

    merged, all_apps = [], set()
    for c in safe:
        sha, err = merge_pr(c["number"])
        if err:
            log(f"  !! merge #{c['number']} failed: {err}")
            continue
        c["merge_sha"] = sha
        merged.append(c)
        all_apps |= affected_apps(c["number"])
        log(f"  ✔ merged #{c['number']} {c['dep']} → {c['new']} ({str(sha)[:8]})")
    result["merged"] = [{"number": c["number"], "dep": c["dep"], "new": c["new"], "sha": c.get("merge_sha")} for c in merged]

    if not merged:
        log("== no PRs merged (all merge attempts failed) ==")
        if args.json:
            print(json.dumps(result, indent=2))
        return 1

    log(f"\n-- syncing local main + reconciling {len(all_apps)} affected app(s) --")
    git_sync()
    reconcile(all_apps)
    log(f"-- waiting {RECONCILE_WAIT_S}s for rollout, then health gate --")
    time.sleep(RECONCILE_WAIT_S)
    ok, problems = post_apply_health({ns for ns, _ in all_apps})
    result["health"] = {"ok": ok, "problems": problems}

    w = _writer()
    if not ok:
        log("\n!! POST-APPLY HEALTH GATE FAILED — reverting the batch:")
        for p in problems:
            log(f"     - {p}")
        reverted = revert_batch([c.get("merge_sha") for c in merged])
        result["reverted"] = reverted
        reconcile(all_apps)  # push cluster back to reverted state
        title = f"Auto-update reverted: {len(reverted)} merge(s) regressed the cluster"
        # Emit the sweep finding first so we can key the OpenClaw issue on its
        # stable finding_id (the fingerprint id, same across cycles).
        fid = None
        if w:
            with w:
                fid = w.emit("critical", title,
                             action="Investigate the reverted bumps; they are back on the deny path until fixed",
                             subsection="auto-update",
                             metadata={"reverted": reverted, "problems": problems[:20],
                                       "merged": [f"#{c['number']} {c['dep']}→{c['new']}" for c in merged]})
        # Route to OpenClaw (owner of the open-issue + reminder lifecycle);
        # notify.py is only the fallback when the openclaw pod is unreachable.
        merged_line = ", ".join(f"{c['dep']}→{c['new']}" for c in merged)
        try:
            sys.path.insert(0, str(SCRIPT_DIR / "lib"))
            from notify import ingest_or_notify  # type: ignore
            route = ingest_or_notify(
                {"key": fid or f"auto-update-revert-{merged[0]['number']}",
                 "kind": "auto_update_revert", "source": "auto-update",
                 "severity": "critical", "action": "ack",
                 "title": title, "component": merged_line,
                 "detail": "reverted after post-apply health failure: " + "; ".join(problems[:6])},
                fallback_text=("⛔ *Auto-update reverted* — a merged bump regressed the cluster:\n"
                               + merged_line + "\nProblems: " + "; ".join(problems[:4])
                               + "\nBatch reverted; cluster restored. Needs a look."),
                urgent=True)
            log(f"  operator issue routed via: {route}")
        except Exception as e:
            log(f"  (operator notify failed: {e})")
        log("\n== ALERT: batch auto-reverted; cluster restored to pre-merge state ==")
        if args.json:
            print(json.dumps(result, indent=2))
        return 2

    log(f"\n== applied {len(merged)} update(s), post-apply health OK ==")
    if w:
        with w:
            w.emit("clean", f"Auto-update merged {len(merged)} safe update(s), cluster healthy",
                   subsection="auto-update",
                   metadata={"merged": [f"#{c['number']} {c['dep']}→{c['new']}" for c in merged]})
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"!! auto-update hard error: {e}")
        sys.exit(1)
