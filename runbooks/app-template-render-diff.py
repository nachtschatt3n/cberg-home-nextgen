#!/usr/bin/env python3
"""Fleet rendered-diff gate for a bjw-s app-template chart bump.

For every HelmRelease on `app-template`, render the release's LIVE values
(`helm get values`, i.e. what Flux actually handed helm, valuesFrom merged and
postBuild-substituted) with the OLD and the NEW chart version, diff the
rendered objects, and classify each consumer:

  LABEL_ONLY     only the `helm.sh/chart` label moves -> no pod restart
  POD_TEMPLATE   a Deployment/StatefulSet/DaemonSet pod template changes -> restart
  CRON_TEMPLATE  only a CronJob/Job template changes -> no restart, next run differs
  OTHER          any other rendered difference (Service, HTTPRoute, PVC, ...)
  RENDER_FAIL    a render (or the values fetch) failed -> gate fails

and raises per-consumer REVIEW flags that force individual review:

  TPL        the values contain `{{` (5.2 templates string fields globally)
  ESCAPED    --escape was given: the new render used `{{ "{{" }}`-escaped values
  TSC        topologySpreadConstraints appear in either render
  SELECTOR   a spec.selector changed (immutable -> helm upgrade fails)
  ADD/DEL    an object appears/disappears between the two renders
  FIDELITY   the OLD render does not equal the live release manifest
             (`helm get manifest`), so the diff is not trustworthy for it

Fidelity is the check that makes every other column mean something: if the
old-version render of the live values does not reproduce what is deployed,
the values or capabilities are wrong and a "no diff" reading proves nothing.

Read-only against the cluster (kubectl get, helm get). Values and diffs can
contain real hostnames -> they are written ONLY under --out (a scratch dir);
stdout carries object kinds/names and field PATHS, never values.

Usage:
  runbooks/app-template-render-diff.py --snapshot-workloads <file>   # pre-change baseline
  runbooks/app-template-render-diff.py --compare-workloads <file> [--expect-labels 'app-template-5.2.1=81']
                                                                     # SAME_GEN / COMPARE_FAIL
  (workloads = Deployment/StatefulSet/DaemonSet; CronJobs are covered by the render gate only)
  runbooks/app-template-render-diff.py --from 5.1.0 --to 5.2.1 --out <scratch>
  runbooks/app-template-render-diff.py --from 5.1.0 --to 5.2.1 --out <scratch> \
      --only media/plex --only default/echo --expect LABEL_ONLY
Exit: 0 = every selected consumer rendered, fidelity held, and (with --expect)
every consumer is in an expected class with no REVIEW flag;
1 = anything else; 2 = usage/tooling error.
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write("PyYAML required: run with .venv/bin/python3\n")
    sys.exit(2)

CHART_REPO = "oci://ghcr.io/bjw-s-labs/helm/app-template"
FLUX_LABELS = ("helm.toolkit.fluxcd.io/name", "helm.toolkit.fluxcd.io/namespace")
CHART_LABEL = "helm.sh/chart"
WORKLOADS = ("Deployment", "StatefulSet", "DaemonSet")
BATCHY = ("CronJob", "Job")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def pull_chart(version, dest):
    path = os.path.join(dest, version, "app-template")
    if os.path.isdir(path):
        return path
    os.makedirs(os.path.join(dest, version), exist_ok=True)
    r = run(["helm", "pull", CHART_REPO, "--version", version, "--untar", "-d", os.path.join(dest, version)])
    if r.returncode != 0 or not os.path.isdir(path):
        sys.stderr.write(f"helm pull {version} failed: {r.stderr.strip()}\n")
        sys.exit(2)
    return path


def _drop(labels_holder, keys):
    lb = labels_holder.get("labels")
    if isinstance(lb, dict):
        for k in keys:
            lb.pop(k, None)
        if not lb:
            labels_holder.pop("labels")


def strip_flux(obj):
    """Flux's origin labels, at any level (only present on the live manifest)."""
    if isinstance(obj, dict):
        _drop(obj, FLUX_LABELS)
        for v in obj.values():
            strip_flux(v)
    elif isinstance(obj, list):
        for v in obj:
            strip_flux(v)
    return obj


def strip_labels(doc):
    """Drop the chart label from the OBJECT's own metadata only. A chart label that
    moves inside .spec.template / .spec.jobTemplate / volumeClaimTemplates is a
    pod-template change and must stay visible to the diff (it rolls pods)."""
    strip_flux(doc)
    md = doc.get("metadata")
    if isinstance(md, dict):
        _drop(md, (CHART_LABEL,))
    return doc


def parse(manifest, default_ns):
    out = {}
    for doc in yaml.safe_load_all(manifest):
        if not isinstance(doc, dict) or "kind" not in doc:
            continue
        md = doc.get("metadata", {})
        key = (doc["kind"], md.get("namespace") or default_ns, md.get("name"))
        out[key] = strip_labels(doc)
    return out


def paths(a, b, p=""):
    """Leaf paths where a and b differ (no values emitted)."""
    if type(a) is not type(b):
        return [p or "."]
    if isinstance(a, dict):
        res = []
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                res.append(f"{p}.{k}")
            else:
                res += paths(a[k], b[k], f"{p}.{k}")
        return res
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{p}[len]"]
        res = []
        for i, (x, y) in enumerate(zip(a, b)):
            res += paths(x, y, f"{p}[{i}]")
        return res
    return [] if a == b else [p]


def has_key(obj, key):
    if isinstance(obj, dict):
        return key in obj or any(has_key(v, key) for v in obj.values())
    if isinstance(obj, list):
        return any(has_key(v, key) for v in obj)
    return False


def render(rel, ns, chart, values_file, kube_version, api_versions):
    cmd = ["helm", "template", rel, chart, "-n", ns, "-f", values_file, "--kube-version", kube_version]
    for av in api_versions:
        cmd += ["--api-versions", av]
    return run(cmd)


def escape_braces(o):
    """Model the repo edit `{{` -> `{{ "{{" }}` on every string value (literal braces
    that 5.2's global string templating would otherwise evaluate)."""
    if isinstance(o, dict):
        return {k: escape_braces(v) for k, v in o.items()}
    if isinstance(o, list):
        return [escape_braces(v) for v in o]
    if isinstance(o, str):
        return o.replace("{{", '{{ "{{" }}')
    return o


def analyse(hr, charts, out, kube_version, api_versions, frm, to, escape=()):
    ns_hr, name = hr["metadata"]["namespace"], hr["metadata"]["name"]
    hist = (hr.get("status", {}).get("history") or [{}])[0]
    rel = hist.get("name") or hr["spec"].get("releaseName") or name
    rns = hist.get("namespace") or hr["spec"].get("targetNamespace") or ns_hr
    live_ver = hr["spec"]["chart"]["spec"].get("version")
    res = {"ns": ns_hr, "name": name, "release": f"{rns}/{rel}", "live_chart": live_ver,
           "class": None, "flags": [], "changed": [], "restarts": [], "error": None}
    d = os.path.join(out, "consumers", f"{ns_hr}__{name}")
    os.makedirs(d, exist_ok=True)
    vf = os.path.join(d, "values.json")
    r = run(["helm", "get", "values", rel, "-n", rns, "-o", "json"])
    if r.returncode != 0 or not r.stdout.strip() or r.stdout.strip() in ("null", "{}"):
        res["class"], res["error"] = "RENDER_FAIL", f"helm get values: {r.stderr.strip()[:200] or 'empty'}"
        return res
    with open(vf, "w") as f:
        f.write(r.stdout)
    if "{{" in r.stdout:
        res["flags"].append("TPL")
    live = run(["helm", "get", "manifest", rel, "-n", rns])
    vfs = {frm: vf, to: vf}
    if f"{ns_hr}/{name}" in escape:
        # new-version render uses the values AS THEY WILL BE after the escape edit
        vfe = os.path.join(d, "values-escaped.json")
        with open(vfe, "w") as f:
            json.dump(escape_braces(json.loads(r.stdout)), f)
        vfs[to] = vfe
        res["flags"].append("ESCAPED")
    renders = {}
    for v in (frm, to):
        rr = render(rel, rns, charts[v], vfs[v], kube_version, api_versions)
        if rr.returncode != 0 or "kind:" not in rr.stdout:
            # helm embeds the offending VALUE text in tpl errors (it names the template
            # after it), which can carry real hostnames -> full stderr to scratch only,
            # stdout gets the error class.
            with open(os.path.join(d, f"render-{v}.err"), "w") as f:
                f.write(rr.stderr)
            m = re.search(r'(function "[^"]+" not defined|nil pointer evaluating [^\n]{0,80}|'
                          r'can.t evaluate field \w+|YAML parse error|execution error at \([^)]{0,120}\))', rr.stderr)
            why = m.group(1) if m else "see " + os.path.join(d, f"render-{v}.err")
            res["class"], res["error"] = "RENDER_FAIL", f"render {v}: {why}"
            return res
        with open(os.path.join(d, f"render-{v}.yaml"), "w") as f:
            f.write(rr.stdout)
        renders[v] = rr.stdout
    old, new = parse(renders[frm], rns), parse(renders[to], rns)
    res["objects"] = len(old)
    # fidelity: only meaningful when the live release IS the old version
    if live_ver == frm and (live.returncode != 0 or "kind:" not in live.stdout):
        # fail CLOSED: an unverifiable fidelity is not a pass
        res["flags"].append("FIDELITY")
        res["fidelity_paths"] = ["helm get manifest failed"]
    elif live_ver == frm:
        lv = parse(live.stdout, rns)
        if lv != old:
            res["flags"].append("FIDELITY")
            fp = []
            for k in sorted(set(lv) | set(old), key=str):
                if k not in lv or k not in old:
                    fp.append(f"{k[0]}/{k[2]}:{'missing-live' if k not in lv else 'missing-render'}")
                else:
                    fp += [f"{k[0]}/{k[2]}:{p}" for p in paths(lv[k], old[k])]
            res["fidelity_paths"] = fp[:20]
    elif live_ver != frm:
        res["flags"].append(f"LIVE={live_ver}")
    if has_key(list(old.values()), "topologySpreadConstraints") or has_key(list(new.values()), "topologySpreadConstraints"):
        res["flags"].append("TSC")
    workload_change = batch_change = other_change = False
    for k in sorted(set(old) | set(new), key=str):
        tag = f"{k[0]}/{k[2]}"
        if k not in old:
            res["flags"].append("ADD")
            res["changed"].append(f"{tag}:+added")
            other_change = True
            continue
        if k not in new:
            res["flags"].append("DEL")
            res["changed"].append(f"{tag}:-removed")
            other_change = True
            continue
        for p in paths(old[k], new[k]):
            res["changed"].append(f"{tag}:{p}")
            if p.startswith(".spec.selector"):
                res["flags"].append("SELECTOR")
            if "topologySpreadConstraints" in p and "TSC" not in res["flags"]:
                res["flags"].append("TSC")
            if k[0] in WORKLOADS and p.startswith(".spec.template"):
                workload_change = True
                if tag not in res["restarts"]:
                    res["restarts"].append(tag)
            elif k[0] in BATCHY and (p.startswith(".spec.jobTemplate") or p.startswith(".spec.template")):
                batch_change = True
            else:
                other_change = True
    if workload_change:
        res["class"] = "POD_TEMPLATE"
    elif other_change:
        res["class"] = "OTHER"
    elif batch_change:
        res["class"] = "CRON_TEMPLATE"
    else:
        res["class"] = "LABEL_ONLY"
    res["flags"] = sorted(set(res["flags"]))
    diff = difflib.unified_diff(renders[frm].splitlines(), renders[to].splitlines(), f"render-{frm}", f"render-{to}", lineterm="")
    with open(os.path.join(d, "render.diff"), "w") as f:
        f.write("\n".join(diff) + "\n")
    return res


def workload_snapshot():
    """Every Deployment/StatefulSet/DaemonSet carrying an app-template chart label:
    generation (bumps iff the spec -- incl. the pod template -- changed), chart label,
    and the UIDs of the pods its selector matches. Label-only upgrades change the
    label and nothing else (measured on paperclip 2026-09-26: generation 8 -> 8)."""
    r = run(["kubectl", "get", "deploy,sts,ds", "-A", "-o", "json"])
    p = run(["kubectl", "get", "pods", "-A", "-o", "json"])
    if r.returncode != 0 or p.returncode != 0:
        sys.stderr.write("kubectl get failed\n")
        sys.exit(2)
    pods = json.loads(p.stdout)["items"]
    snap = {}
    for w in json.loads(r.stdout)["items"]:
        md = w["metadata"]
        chart = (md.get("labels") or {}).get("helm.sh/chart", "")
        if not chart.startswith("app-template-"):
            continue
        sel = (w["spec"].get("selector") or {}).get("matchLabels") or {}
        uids = sorted(
            f'{x["metadata"]["name"]}={x["metadata"]["uid"]}' for x in pods
            if x["metadata"]["namespace"] == md["namespace"] and sel
            and all((x["metadata"].get("labels") or {}).get(k) == v for k, v in sel.items())
            and x["status"].get("phase") in ("Running", "Pending"))
        snap[f'{md["namespace"]}/{w["kind"]}/{md["name"]}'] = {
            "generation": md.get("generation"), "chart": chart, "pods": uids}
    return snap


def main():
    if len(sys.argv) >= 3 and sys.argv[1] in ("--snapshot-workloads", "--compare-workloads"):
        snap = workload_snapshot()
        if sys.argv[1] == "--snapshot-workloads":
            with open(sys.argv[2], "w") as f:
                json.dump(snap, f, indent=1, sort_keys=True)
            print(f"SNAPSHOT workloads={len(snap)} -> {sys.argv[2]}")
            return 0 if snap else 1
        with open(sys.argv[2]) as f:
            base = json.load(f)
        if not base:
            print("COMPARE_FAIL empty baseline")
            return 1
        gen_changed = [k for k in base if k in snap and base[k]["generation"] != snap[k]["generation"]]
        gone = [k for k in base if k not in snap]
        new = [k for k in snap if k not in base]
        pods_changed = [k for k in base if k in snap and base[k]["pods"] != snap[k]["pods"]
                        and k not in gen_changed]
        from collections import Counter
        print("CHART_LABELS " + " ".join(f"{c}={n}" for c, n in sorted(Counter(v["chart"] for v in snap.values()).items())))
        for k in gen_changed:
            print(f"GEN_CHANGED {k} {base[k]['generation']} -> {snap[k]['generation']}")
        for k in gone:
            print(f"GONE {k}")
        for k in new:
            print(f"NEW {k}")
        for k in pods_changed:
            print(f"POD_REPLACED_SAME_GEN {k}  (not chart-caused: generation unchanged -- eviction/crash/node; inspect)")
        extra = sys.argv[3:]
        if extra and (extra[0] != "--expect-labels" or len(extra) != 2 or not extra[1].strip()):
            print("COMPARE_FAIL usage: --compare-workloads <file> [--expect-labels '<chart>=<n> ...']")
            return 2
        want = extra[1] if extra else None
        got = " ".join(f"{c}={n}" for c, n in sorted(Counter(v["chart"] for v in snap.values()).items()))
        label_bad = False
        if want is not None and got != want:
            print(f"LABELS_MISMATCH want '{want}' got '{got}'")
            label_bad = True
        if gen_changed or gone or new or label_bad:
            print("COMPARE_FAIL")
            return 1
        print(f"SAME_GEN workloads={len(base)} pods_replaced_same_gen={len(pods_changed)}")
        return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", required=True)
    ap.add_argument("--out", required=True, help="scratch dir (values/renders/diffs land here; never commit)")
    ap.add_argument("--only", action="append", default=[], help="ns/name (repeatable)")
    ap.add_argument("--only-file", help="file with one ns/name per line")
    ap.add_argument("--expect", action="append", default=[], help="allowed class (repeatable); any REVIEW flag also fails")
    ap.add_argument("--allow-flag", action="append", default=[], help="REVIEW flag tolerated by --expect (e.g. TSC)")
    ap.add_argument("--escape", action="append", default=[],
                    help="ns/name: render the NEW version with every `{{` in its values escaped "
                         "(models the planned repo edit; the OLD render keeps the live values)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("-j", "--jobs", type=int, default=8)
    a = ap.parse_args()
    only = set(a.only)
    if a.only_file:
        with open(a.only_file) as f:
            only |= {l.strip() for l in f if l.strip() and not l.startswith("#")}
    os.makedirs(a.out, exist_ok=True)

    r = run(["kubectl", "get", "helmrelease", "-A", "-o", "json"])
    if r.returncode != 0:
        sys.stderr.write(f"kubectl get helmrelease failed: {r.stderr}\n")
        return 2
    hrs = [h for h in json.loads(r.stdout)["items"]
           if h["spec"].get("chart", {}).get("spec", {}).get("chart") == "app-template"]
    if only:
        hrs = [h for h in hrs if f'{h["metadata"]["namespace"]}/{h["metadata"]["name"]}' in only]
        found = {f'{h["metadata"]["namespace"]}/{h["metadata"]["name"]}' for h in hrs}
        missing = only - found
        if missing:
            sys.stderr.write(f"--only names no app-template HelmRelease: {sorted(missing)}\n")
            return 2
    if not hrs:
        sys.stderr.write("no app-template HelmReleases selected\n")
        return 2
    kv = json.loads(run(["kubectl", "version", "-o", "json"]).stdout)["serverVersion"]["gitVersion"]
    avs = [l for l in run(["kubectl", "api-versions"]).stdout.split() if l]
    # The chart probes `.Capabilities.APIVersions.Has "<group/version>/<Kind>"` (e.g. the
    # HTTPRoute apiVersion pick in classes/_route.tpl); `helm template` only knows what we
    # pass, so add the resource-qualified form too. Without it every route renders as
    # v1alpha2 and the FIDELITY check fails (measured 2026-09-27: 45 routes).
    for line in run(["kubectl", "api-resources", "--no-headers"]).stdout.splitlines():
        t = line.split()
        if len(t) >= 4:
            avs.append(f"{t[-3]}/{t[-1]}")
    if not avs:
        sys.stderr.write("kubectl api-versions/api-resources returned nothing\n")
        return 2
    charts = {v: pull_chart(v, os.path.join(a.out, "charts")) for v in (a.frm, a.to)}

    with ThreadPoolExecutor(a.jobs) as ex:
        results = list(ex.map(lambda h: analyse(h, charts, a.out, kv, avs, a.frm, a.to, set(a.escape)), hrs))
    results.sort(key=lambda x: (x["class"], x["ns"], x["name"]))
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(results, f, indent=1)

    if a.json:
        print(json.dumps(results, indent=1))
    else:
        print(f"app-template {a.frm} -> {a.to}   consumers={len(results)}   kube={kv}   out={a.out}")
        print(f"{'NAMESPACE/NAME':44} {'CLASS':13} {'FLAGS':18} RESTARTS / CHANGED PATHS")
        for x in results:
            detail = ",".join(x["restarts"]) or (x["error"] or "")
            if x["class"] not in ("LABEL_ONLY", "RENDER_FAIL"):
                detail += "  " + "; ".join(x["changed"][:4]) + (f" (+{len(x['changed'])-4})" if len(x["changed"]) > 4 else "")
            print(f"{x['ns'] + '/' + x['name']:44} {x['class']:13} {','.join(x['flags']) or '-':18} {detail}")
        from collections import Counter
        c = Counter(x["class"] for x in results)
        fl = Counter(f for x in results for f in x["flags"])
        print("TOTALS " + " ".join(f"{k}={v}" for k, v in sorted(c.items())) + "   FLAGS " + (" ".join(f"{k}={v}" for k, v in sorted(fl.items())) or "none"))

    bad = [x for x in results if x["class"] == "RENDER_FAIL" or "FIDELITY" in x["flags"]]
    if a.expect:
        allowed_flags = set(a.allow_flag)
        bad += [x for x in results if x["class"] not in a.expect
                or any(f not in allowed_flags for f in x["flags"])]
    if bad:
        print("GATE_FAIL " + " ".join(sorted({f"{x['ns']}/{x['name']}" for x in bad})))
        return 1
    print("GATE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
