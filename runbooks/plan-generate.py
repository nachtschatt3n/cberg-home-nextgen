#!/usr/bin/env python3
"""plan-generate — template plans for the MECHANICAL update classes (no LLM).

WHY THIS EXISTS
Plan SUPPLY was the nightly's bottleneck (2026-11-25): 5 planner dispatches per
~48h sweep against 47 PLAN-lane items. Most of those are a one-line image bump
of an app whose plan an LLM planner writes the same way every time. A template
produces that plan deterministically, with premises and verification gates that
can actually fail, so the planner agent is reserved for work that needs
judgement (migrations, stateful apps with real changes, 0.x minors, anything
G3 could not verify as clean).

TEMPLATES (the only two; anything else => `refuse`, never guess)
  stateless    one image reference in git, a Deployment/StatefulSet or an
               app-template HelmRelease, NO persistent volume anywhere in the
               app directory, patch/minor on a >=1.x line, not digest-pinned.
               rollback_class git-revert, capability_change false, risk low.
  db-backed    a postgres Deployment on a Longhorn PVC bumped within its major
               (e.g. 18.6-alpine -> 18.7-alpine). rollback_class backup-restore
               with `backup_gate` AND `restore_proof`: both are the real
               `runbooks/backup-restore-proof.py` (restore the newest Longhorn
               backup into a scratch volume, start postgres on it, query it —
               exit 0 PROVEN only; 1 FAILED and 2 INCONCLUSIVE both stop the
               plan). Postgres only: that is the engine the probe supports.

WHAT A GENERATED PLAN IS NOT
It is a `status: draft`. It never marks itself ready-for-go. A reviewer's
verdict does that — either plan-reviewer-agent, or this tool's
`review` subcommand acting as a DETERMINISTIC reviewer, which works only for a
template version the operator registered in autonomy-policy.yaml
`generated_plans.reviewed_templates` (empty by default => nothing self-approves)
AND only when the plan still equals a fresh re-generation from its recorded
inputs (so hand edits drop it back to the LLM reviewer).

    plan-generate.py generate --template stateless --component X --namespace NS \
        --repo ghcr.io/o/x --current 1.2.3 --target 1.2.4 [--write]
    plan-generate.py scan --coverage-json F [--write]     # every eligible needs_plan row
    plan-generate.py review <plan_id> [--write]           # deterministic review
Exit: 0 ok | 1 refused/nothing eligible when a plan was explicitly requested | 2 bad input
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TEMPLATE_VERSION = {"stateless": "stateless@1", "db-backed": "db-backed@1"}
PLANS_REL = "runbooks/maintenance/plans"
STATEFUL_MARKERS = ("persistentVolumeClaim", "existingClaim", "volumeClaimTemplates",
                    "kind: PersistentVolumeClaim", "kind: PersistentVolume")
# components that are cluster-core: never templated, always a human/planner.
CORE_DENY = ("longhorn", "cilium", "envoy", "coredns", "talos", "flux", "etcd",
             "cert-manager", "external-dns", "authentik", "kube-prometheus")


class Refuse(Exception):
    pass


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / fn)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def vtuple(v):
    m = re.match(r"^v?(\d+(?:\.\d+)*)(-.*)?$", str(v))
    return (tuple(int(x) for x in m.group(1).split(".")), m.group(2) or "") if m else None


def delta(cur, tgt):
    a, b = vtuple(cur), vtuple(tgt)
    if not a or not b or a[1] != b[1]:
        raise Refuse(f"versions {cur!r} -> {tgt!r} are not comparable (suffix/format)")
    x, y = a[0], b[0]
    n = max(len(x), len(y))
    x, y = x + (0,) * (n - len(x)), y + (0,) * (n - len(y))
    if y <= x:
        raise Refuse("target is not newer than current")
    if x[0] != y[0]:
        return "major"
    return "minor" if x[1] != y[1] else "patch"


def find_manifest(root: Path, namespace: str, repo: str, current: str):
    """The ONE git file pinning repo:current (or repository+tag) in the app tree."""
    base = root / "kubernetes" / "apps" / namespace
    if not base.is_dir():
        raise Refuse(f"no kubernetes/apps/{namespace}")
    ref = f"{repo}:{current}"
    hits = []
    for f in base.rglob("*.yaml"):
        t = f.read_text(errors="replace")
        if ref in t or (re.search(rf"repository:\s*{re.escape(repo)}\s*$", t, re.M)
                        and re.search(rf"tag:\s*[\"']?{re.escape(current)}[\"']?(\s|$)", t, re.M)):
            hits.append(f)
    if len(hits) != 1:
        raise Refuse(f"{len(hits)} manifest(s) pin {ref} under kubernetes/apps/{namespace} (need exactly 1)")
    return hits[0]


def classify_manifest(root: Path, f: Path, repo: str, current: str):
    """-> dict(kind, name, form, stateful, digest_pinned). Raises Refuse."""
    text = f.read_text()
    if "@sha256:" in text and f"{repo}:{current}@sha256" in text:
        raise Refuse("current reference is digest-pinned; the target digest cannot be derived here")
    docs = [d for d in yaml.safe_load_all(text) if isinstance(d, dict)]
    wl = None
    for d in docs:
        k = d.get("kind")
        if k in ("Deployment", "StatefulSet"):
            imgs = [c.get("image") for c in (((d.get("spec") or {}).get("template") or {})
                                             .get("spec") or {}).get("containers") or []]
            if any(str(i).startswith(f"{repo}:{current}") for i in imgs):
                wl = {"kind": k.lower(), "name": d["metadata"]["name"], "form": "manifest"}
        elif k == "HelmRelease":
            wl = {"kind": "helmrelease", "name": d["metadata"]["name"], "form": "helmrelease"}
    if not wl:
        raise Refuse("no Deployment/StatefulSet/HelmRelease in the pinning file references the image")
    appdir = f.parent
    # the app dir AND its parent (kustomization siblings) are inspected for volumes
    stateful = False
    for g in list(appdir.rglob("*.yaml")) + list(appdir.parent.glob("*.yaml")):
        t = g.read_text(errors="replace")
        if any(m in t for m in STATEFUL_MARKERS):
            stateful = True
            break
    wl["stateful"] = stateful
    wl["path"] = str(f.relative_to(root))
    return wl


def front(plan: dict, comments: dict | None = None) -> str:
    return yaml.safe_dump(plan, sort_keys=False, width=100, allow_unicode=True)


def kget(ns, wl, jp):
    if wl["form"] == "manifest":
        return f"kubectl get {wl['kind']} {wl['name']} -n {ns} -o jsonpath='{jp}'"
    return None


def pods_cmd(ns, wl, jp):
    if wl["form"] == "manifest":
        return f"kubectl get {wl['kind']} {wl['name']} -n {ns} -o jsonpath='{{.spec.template.spec.containers[*].image}}'" \
            if "images" == jp else None
    return None


def img_cmd(ns, wl):
    if wl["form"] == "manifest":
        return (f"kubectl get {wl['kind']} {wl['name']} -n {ns} "
                f"-o jsonpath='{{.spec.template.spec.containers[*].image}}'")
    return (f"kubectl get pods -n {ns} -l app.kubernetes.io/instance={wl['name']} "
            f"-o jsonpath='{{.items[*].spec.containers[*].image}}'")


def ready_cmd(ns, wl):
    if wl["form"] == "manifest":
        return (f"kubectl get {wl['kind']} {wl['name']} -n {ns} "
                f"-o jsonpath='{{.status.readyReplicas}}/{{.spec.replicas}}'")
    return (f"kubectl get pods -n {ns} -l app.kubernetes.io/instance={wl['name']} "
            f"-o jsonpath='{{.items[*].status.containerStatuses[*].ready}}'")


def build(template, inp, wl, today, root=REPO_ROOT):
    ns, comp, repo = inp["namespace"], inp["component"], inp["repo"]
    cur, tgt = inp["current"], inp["target"]
    ref_c, ref_t = f"{repo}:{cur}", f"{repo}:{tgt}"
    path = wl["path"]
    pid = f"{comp}-{tgt}"
    prem = [
        {"id": "current-pinned-in-git",
         "why": f"The plan edits exactly one occurrence of `{ref_c}` (or its repository+tag pair); if main no longer pins {cur} the plan is stale.",
         "run": f"git show origin/main:{path}",
         "expect_contains": cur},
        {"id": "live-runs-current",
         "why": f"Baseline: the live workload must still run {cur}; if it already moved the verification baseline is wrong.",
         "run": img_cmd(ns, wl), "expect_contains": f"{repo}:{cur}"},
        {"id": "workload-healthy",
         "why": "A plan must not start against an already-unhealthy workload (its failure would be blamed on the bump).",
         "run": ready_cmd(ns, wl),
         **({"expect_matches": r"^(\d+)/\1$"} if wl["form"] == "manifest"
            else {"expect_matches": r"^(true)( true)*$"})},
    ]
    plan = {
        "plan_id": pid, "component": comp, "pr": inp.get("pr"), "kind": "image",
        "current": cur, "target": tgt,
        "update_type": delta(cur, tgt),
        "risk": "low" if template == "stateless" else "medium",
        "est_duration_min": 15 if template == "stateless" else 40,
        "needs_reboot": False,
        "touches": {"namespaces": [ns],
                    "resources": [f"{wl['kind']}/{wl['name']}", f"image/{repo}"],
                    "shared": []},
        "depends_on": [], "conflicts_with": [], "exclusive": False,
        "capability_change": False,
        "rollback_class": "git-revert" if template == "stateless" else "backup-restore",
        "finding_refs": [], "security_ref": inp.get("security_ref"),
        "status": "draft", "window": None, "generated": today.isoformat(),
        "generated_by": f"plan-generate {TEMPLATE_VERSION[template]}",
        "generated_inputs": {k: inp[k] for k in sorted(inp) if k != "pr" or inp[k] is not None},
        "premises": prem,
    }
    if template == "db-backed":
        vol = inp["volume"]
        cmd = (f"python3 runbooks/backup-restore-proof.py --volume {vol} --image {ref_c}")
        plan["backup_gate"] = (f"fresh Longhorn backup of {vol}, then `{cmd}` exits 0 (PROVEN). "
                               f"Exit 1 (FAILED) and exit 2 (INCONCLUSIVE) both STOP the plan: "
                               f"a backup that exists is not a backup that restores.")
        plan["restore_proof"] = (f"`{cmd}` restores the newest Completed backup into a scratch volume, "
                                 f"starts {ref_c} on it, and queries a real table; run BEFORE the edit.")
        prem.append({"id": "pg-is-on-the-bumped-major",
                     "why": "Template is valid only for a minor/patch inside one postgres major (on-disk format unchanged).",
                     "run": img_cmd(ns, wl),
                     "expect_matches": rf"{re.escape(repo)}:{re.escape(re.match(r'^(\d+)', cur).group(1))}\."})
    fm = front(plan)
    b = []
    b.append(f"# {comp} {cur} -> {tgt} ({template}, generated {today.isoformat()})\n")
    b.append("## 1. Summary\n"
             f"One-line image bump `{ref_c}` -> `{ref_t}` in `{path}` ({wl['kind']}/{wl['name']}), "
             f"{plan['update_type']} on the same line. Generated by `plan-generate` template "
             f"`{TEMPLATE_VERSION[template]}`; no planner agent wrote or edited it. "
             "Everything not covered by the premises and gates below is out of this template's reach — "
             "a reviewer must refuse the plan if the release notes mention anything it does not cover.\n")
    b.append("## 2. Pre-checks (all must pass, else STOP)\n"
             "1. `python3 runbooks/plan-premises.py " + pid + " --require-premises` exits 0.\n"
             "2. `flux get kustomizations -A | awk 'NR==1 || $5 != \"True\"'` lists only the header.\n"
             + (f"3. Take a fresh Longhorn backup of `{plan.get('generated_inputs', {}).get('volume')}` and wait for Completed, "
                f"then `{cmd}`; require exit 0. STOP on exit 1 or 2 — do NOT proceed on INCONCLUSIVE.\n"
                if template == "db-backed" else ""))
    b.append("## 3. Steps\n"
             "```bash\n"
             f"python3 - <<'PY'\nfrom pathlib import Path\np = Path('{path}')\nt = p.read_text()\n"
             + (f"assert t.count('{ref_c}') >= 1 or t.count('{cur}') >= 1, 'pin not found'\n"
                f"t = t.replace('{ref_c}', '{ref_t}')\n" if wl['form'] == 'manifest' else
                f"import re\nassert re.search(r'tag:\\s*[\"\\']?{re.escape(cur)}', t), 'pin not found'\n"
                f"t = re.sub(r'(tag:\\s*[\"\\']?){re.escape(cur)}', r'\\g<1>{tgt}', t, count=1)\n")
             + "p.write_text(t)\nPY\n"
             f"git diff --stat -- {path}\n"
             f"git commit --only {path} -m 'fix(container): bump {comp} {cur} -> {tgt}'\n"
             "git pull --rebase --autostash && git push\n"
             "```\n"
             "Flux reconciles via the webhook; do not reconcile by hand. If the diff touches more than the one pin, STOP and revert the working copy.\n")
    b.append("## 4. Verification (CONTENTS, not shape)\n"
             f"V1 the running image IS the target: `{img_cmd(ns, wl)}` must contain `{ref_t}` (and no `{ref_c}`).\n"
             f"V1-CONTROL (proves V1 can fail): the same output must NOT contain `{repo}:0.0.0-nonexistent`; "
             "if the control matches, V1 is not measuring the image and the plan FAILS.\n"
             f"V2 workload ready: `{ready_cmd(ns, wl)}` shows all replicas/containers ready, polled up to 10 min.\n"
             f"V3 no restart loop: `kubectl get pods -n {ns} -o jsonpath='{{.items[*].status.containerStatuses[*].restartCount}}'` "
             "for this app's pods all <= 1, re-read 5 minutes after V2.\n"
             "V4 no new Warning events for the app's pods: `kubectl get events -n " + ns +
             " --field-selector type=Warning --sort-by=.lastTimestamp | tail -20` shows nothing newer than the commit that names this app.\n"
             "V5 app-level contents check: if the app has an HTTPRoute, curl its health/version endpoint "
             "through the Gateway and require the new version string or HTTP 200 WITH a non-empty body; a bare 200 is not accepted.\n")
    b.append("## 5. Rollback\n"
             f"`git revert <commit>` for `{path}`, push, wait for Flux, re-run V1 against `{ref_c}`. "
             + ("Data is untouched by a same-major bump; if V2/V3 show data errors, restore from the Longhorn backup "
                "proven in pre-check 3 (restore_proof) and STOP for the operator.\n" if template == "db-backed"
                else "No state is touched, so revert is complete.\n"))
    return pid, "---\n" + fm + "---\n\n" + "\n".join(b)


def eligibility(inp, wl, template):
    comp = inp["component"].lower()
    if any(c in comp for c in CORE_DENY):
        raise Refuse(f"{comp} is cluster-core / shared infra — planner + attended window")
    dc = delta(inp["current"], inp["target"])
    if dc == "major":
        raise Refuse("major bump")
    if vtuple(inp["current"])[0][0] == 0 and dc != "patch":
        raise Refuse("0.x minor: at major 0 the minor IS the breaking axis")
    if template == "stateless" and wl["stateful"]:
        raise Refuse("app directory mounts persistent storage — not stateless")
    if template == "db-backed":
        if inp["repo"] not in ("postgres", "docker.io/library/postgres"):
            raise Refuse("db-backed template supports postgres only")
        if dc != "minor" and dc != "patch":
            raise Refuse("db-backed is for minor/patch inside one major")
        if not inp.get("volume"):
            raise Refuse("db-backed needs --volume (the Longhorn volume holding PGDATA)")


def generate(inp, template, root=REPO_ROOT, today=None):
    today = today or date.today()
    f = find_manifest(root, inp["namespace"], inp["repo"], inp["current"])
    wl = classify_manifest(root, f, inp["repo"], inp["current"])
    eligibility(inp, wl, template)
    pid, text = build(template, inp, wl, today, root)
    # the produced frontmatter must satisfy the real validator
    mp = _load("mp_gen", "maintenance-plan.py")
    meta = yaml.safe_load(text.split("---", 2)[1])
    cfg = mp.load_windows()
    errs = [e for e in mp.validate_plans(cfg, [{**meta, "_path": f"{PLANS_REL}/{pid}.md"}])
            if "names no existing plan" not in e]
    if errs:
        raise Refuse("generated plan fails maintenance-plan validation: " + "; ".join(errs[:3]))
    return pid, text, meta


def write_plan(pid, text, root=REPO_ROOT):
    p = root / PLANS_REL / f"{pid}.md"
    if p.exists():
        raise Refuse(f"{p} already exists — refusing to overwrite (refresh via plan-refine)")
    p.write_text(text)
    return p


def scan(cov, root=REPO_ROOT, today=None, existing=()):
    """Eligible needs_plan rows -> [(pid, text)] and the refusals (with reasons)."""
    made, refused = [], []
    for row in cov.get("needs_plan") or []:
        if row.get("kind") != "image" or not row.get("image_repos"):
            refused.append((row.get("component"), "not a single-image row"))
            continue
        repo = [r for r in row["image_repos"] if r != "busybox"][0]
        inp = {"component": row["component"], "namespace": row["namespace"], "repo": repo,
               "current": str(row["current"]), "target": str(row["target"])}
        try:
            tpl = "stateless"
            try:
                pid, text, _ = generate(inp, tpl, root, today)
            except Refuse as e:
                if "persistent storage" in str(e) and repo in ("postgres",):
                    raise Refuse("postgres on a volume needs --volume (db-backed is explicit, not scanned)")
                raise
            if pid in existing:
                refused.append((row["component"], f"plan {pid} exists"))
                continue
            made.append((pid, text))
        except Refuse as e:
            refused.append((row["component"], str(e)))
    return made, refused


def deterministic_review(plan_path: Path, policy, root=REPO_ROOT, today=None):
    """-> (ok, why). Only for a registered template version and an unedited plan."""
    today = today or date.today()
    text = plan_path.read_text()
    meta = yaml.safe_load(text.split("---", 2)[1])
    gb = str(meta.get("generated_by") or "")
    m = re.match(r"^plan-generate (\S+)$", gb)
    if not m:
        return False, "not a generated plan"
    reg = ((policy or {}).get("generated_plans") or {}).get("reviewed_templates") or []
    if m.group(1) not in [str(x) for x in reg]:
        return False, f"template {m.group(1)} is not registered in autonomy-policy generated_plans.reviewed_templates"
    inp = meta.get("generated_inputs") or {}
    tpl = m.group(1).split("@")[0]
    gen_day = date.fromisoformat(str(meta["generated"]))
    pid, fresh, _ = generate(inp, tpl, root, gen_day)
    fm0 = yaml.safe_load(fresh.split("---", 2)[1])
    skip = {"review", "review_refined", "review_refined_base", "status", "window",
            "needs_replan", "needs_replan_since", "retargeted_from"}
    a = {k: v for k, v in fm0.items() if k not in skip}
    b = {k: v for k, v in meta.items() if k not in skip}
    if a != b:
        return False, "plan frontmatter differs from a fresh re-generation (hand-edited or inputs drifted)"
    if fresh.split("---", 2)[2].strip() != text.split("---", 2)[2].split("\n## Refinement log")[0].strip():
        return False, "plan body differs from a fresh re-generation"
    return True, f"equals re-generation from recorded inputs (template {m.group(1)})"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--template", required=True, choices=sorted(TEMPLATE_VERSION))
    for a in ("component", "namespace", "repo", "current", "target"):
        g.add_argument(f"--{a}", required=True)
    g.add_argument("--pr", type=int)
    g.add_argument("--volume")
    g.add_argument("--write", action="store_true")
    s = sub.add_parser("scan")
    s.add_argument("--coverage-json", required=True)
    s.add_argument("--write", action="store_true")
    r = sub.add_parser("review")
    r.add_argument("plan_id")
    r.add_argument("--write", action="store_true")
    ap.add_argument("--root", default=str(REPO_ROOT))
    args = ap.parse_args(argv)
    root = Path(args.root)
    try:
        if args.cmd == "generate":
            inp = {k: getattr(args, k) for k in ("component", "namespace", "repo", "current", "target")}
            if args.pr:
                inp["pr"] = args.pr
            if args.volume:
                inp["volume"] = args.volume
            pid, text, _ = generate(inp, args.template, root)
            if args.write:
                print(write_plan(pid, text, root))
            else:
                print(text)
            return 0
        if args.cmd == "scan":
            cov = json.loads(Path(args.coverage_json).read_text())
            existing = {p.stem for p in (root / PLANS_REL).glob("*.md")}
            made, refused = scan(cov, root, None, existing)
            for pid, text in made:
                if args.write:
                    write_plan(pid, text, root)
                print(f"GENERATED {pid}")
            for c, why in refused:
                print(f"refused   {c}: {why}")
            return 0
        if args.cmd == "review":
            mp = _load("mp_gen", "maintenance-plan.py")
            p = root / PLANS_REL / f"{args.plan_id}.md"
            ok, why = deterministic_review(p, mp.load_autonomy_policy(), root)
            print(("REVIEWED " if ok else "NOT-REVIEWED ") + why)
            if ok and args.write:
                t = p.read_text()
                fm, body = t.split("---", 2)[1], t.split("---", 2)[2]
                fm = re.sub(r"^review:.*\n", "", fm, flags=re.M)
                fm = fm.rstrip("\n") + f"\nreview: ready-for-go@{date.today().isoformat()}\n" \
                                       f"review_by: \"deterministic:{yaml.safe_load(fm)['generated_by']}\"\n"
                fm = fm.replace("status: draft", "status: vetted")
                p.write_text("---" + "\n" + fm.lstrip("\n") + "---" + body)
            return 0 if ok else 1
    except Refuse as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
