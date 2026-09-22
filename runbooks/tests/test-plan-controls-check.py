#!/usr/bin/env python3
"""Regression tests: a plan's gate may only name instruments that EXIST.

F-ab84875b — plan-premises.py had zero mentions of `alertname` or `metric`:
a premise or a §4 gate could name a metric that Prometheus has never scraped
or an alert no PrometheusRule declares, and PASS — an empty PromQL result is
not an error, and a matcher on nothing is not an error. The edot-collector
plan's own negative control proved it (the identical pipeline pointed at a
nonexistent metric printed INGEST_LOW).

Pinned here:
  * promql_metric_names() harvests the selected metrics and NOT labels,
    functions, keywords or durations — including URL-encoded queries and
    dotted `__name__` matchers;
  * alertnames_in() splits regex alternatives and keeps only identifiers;
  * gate_names() reads CONTROL: lines, premise PromQL and body matchers,
    attributing each name to its source;
  * check_controls() FAILS CLOSED: an unknown metric oracle, an empty alert
    oracle, a missing instrument, or no CONTROL: line at all — each fails;
  * repo_alertnames() reads only PrometheusRule manifests (an `alert:` key in
    some other YAML is not a declaration).

Two straws: a fail-OPEN check_controls (the pre-fix "no check" semantics)
and a promql harvester that does not blank label groups.

Hermetic except for one read of the repo's own tracked manifests
(repo_alertnames must be validated on real input, see tests/README.md).

Run: python3 runbooks/tests/test-plan-controls-check.py
"""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pp", REPO / "runbooks/plan-premises.py")
pp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pp)

FAILURES: list[str] = []
ERROR_MARKS = ("Traceback", "Exception:", "Error:")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"  {detail}"))
    if not ok:
        FAILURES.append(name)


def count(population, pred) -> int:
    items = list(population)
    if not items:
        raise AssertionError("count(): EMPTY population — nothing was observed")
    joined = "\n".join(str(x) for x in items)
    if any(m in joined for m in ERROR_MARKS):
        raise AssertionError(f"count(): population carries error text: {joined[:120]!r}")
    return sum(1 for x in items if pred(x))


PROXY = "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query"
RUN_PLAIN = (f"kubectl get --raw '{PROXY}?query=sum(increase(otelcol_exporter_sent_log_records_total[15m]))'"
             " | sed -E 's/.*\"value\":\\[[0-9.]+,\"([0-9]+).*/\\1/' | awk '{print ($1+0<1000)?\"LOW\":\"OK\"}'")
RUN_ENCODED = (f"kubectl get --raw \"{PROXY}?query=sum%20by%20(outcome)%20(increase(%7B__name__%3D%22"
               "otelcol.elasticsearch.docs.processed_total%22%7D%5B15m%5D))\"")
BODY = """
## 4. Verification

CONTENTS ASSERTION: records still arrive — measured by the query below, compared to the §2 baseline.
CONTROL: metric otelcol_exporter_sent_log_records_total — the 15m increase, floor 1000
- **CONTROL:** alertname EdotCollectorDown — must NOT be firing after the roll
> CONTROL: alert OtelCollectorExportFailed — silenced for the window only

silence: {"matchers":[{"name":"alertname","value":"EdotCollectorDown|OtelCollectorQueueFull","isRegex":true}]}
"""


def plan(**kw):
    base = {"plan_id": "edot-collector-0.161.0", "status": "vetted",
            "premises": [{"id": "ingest-ok", "run": RUN_PLAIN, "expect_exact": "OK"},
                         {"id": "es-ok", "run": RUN_ENCODED, "expect_contains": "success"}]}
    base.update(kw)
    return base


ALERTS = {"EdotCollectorDown", "OtelCollectorExportFailed", "OtelCollectorQueueFull"}
METRICS = {"otelcol_exporter_sent_log_records_total", "otelcol.elasticsearch.docs.processed_total", "up"}


def scenarios(check_controls=None, harvest=None) -> dict:
    cc = check_controls or pp.check_controls
    names = harvest or pp.promql_metric_names
    out = {}
    # --- PromQL harvest --------------------------------------------------------
    out["promql: a plain aggregation yields the one selected metric"] = (
        names("sum(increase(otelcol_exporter_sent_log_records_total[15m]))")
        == {"otelcol_exporter_sent_log_records_total"})
    enc = names("sum%20by%20(outcome)%20(increase(%7B__name__%3D%22otelcol.elasticsearch.docs.processed_total%22%7D%5B15m%5D))")
    out["promql: URL-encoded dotted __name__ matcher yields the dotted metric, NOT the by-label"] = (
        enc == {"otelcol.elasticsearch.docs.processed_total"})
    out["promql: labels inside {} and by() are never metrics"] = (
        names('sum by (namespace) (rate(http_requests_total{code=~"5..",job="x"}[5m])) > bool 0')
        == {"http_requests_total"})
    out["promql: functions, keywords and durations are excluded"] = (
        names('time() - kube_cronjob_status_last_successful_time{namespace="databases"} > 8 * 3600')
        == {"kube_cronjob_status_last_successful_time"})
    out["promql: `up == 1 and on() vector(1)` selects only `up`"] = names("up == 1 and on() vector(1)") == {"up"}
    out["promql: empty expression yields nothing"] = names("") == set()

    # --- alertnames -------------------------------------------------------------
    out["alertnames: regex alternatives are split, anchors stripped"] = (
        pp.alertnames_in('alertname=~"^EdotCollectorDown|OtelCollectorQueueFull$"')
        == {"EdotCollectorDown", "OtelCollectorQueueFull"})
    out["alertnames: the silence JSON matcher form is read"] = (
        pp.alertnames_in('{"name":"alertname","value":"A_1|B_2","isRegex":true}') == {"A_1", "B_2"})
    out["alertnames: a wildcard is not an alert"] = pp.alertnames_in('alertname=~".*"') == set()

    # --- gate_names -------------------------------------------------------------
    g = pp.gate_names(plan(), BODY)
    out["gate_names: three CONTROL lines in three markdown shapes are all read"] = g["control_lines"] == 3
    out["gate_names: metrics come from CONTROL lines AND premise PromQL, attributed"] = (
        set(g["metrics"]) == {"otelcol_exporter_sent_log_records_total",
                              "otelcol.elasticsearch.docs.processed_total"}
        and "CONTROL line" in g["metrics"]["otelcol_exporter_sent_log_records_total"]
        and "premise ingest-ok" in g["metrics"]["otelcol_exporter_sent_log_records_total"]
        and g["metrics"]["otelcol.elasticsearch.docs.processed_total"] == ["premise es-ok"])
    out["gate_names: alertnames come from CONTROL lines AND body matchers"] = (
        set(g["alertnames"]) == ALERTS
        and "body matcher" in g["alertnames"]["OtelCollectorQueueFull"])

    # --- check_controls: fail closed in every direction ------------------------
    r = cc(plan(), BODY, ALERTS, METRICS)
    out["controls: every instrument present + CONTROL lines => PASS"] = r["passed"] is True and not r["problems"]
    r = cc(plan(), BODY, ALERTS - {"OtelCollectorQueueFull"}, METRICS)
    out["controls: an undeclared alertname FAILS and is named"] = (
        r["passed"] is False and count(r["problems"], lambda p: "OtelCollectorQueueFull" in p and "NOT declared" in p) == 1)
    r = cc(plan(), BODY, ALERTS, METRICS - {"otelcol.elasticsearch.docs.processed_total"})
    out["controls: a metric absent from the label index FAILS and is named"] = (
        r["passed"] is False and count(r["problems"], lambda p: "processed_total" in p and "NOT in the Prometheus" in p) == 1)
    r = cc(plan(), BODY, ALERTS, None)
    out["controls: no metric oracle => every metric UNVERIFIED => FAIL (never pass)"] = (
        r["passed"] is False and count(r["problems"], lambda p: "UNVERIFIED" in p and "metric" in p) == 2)
    r = cc(plan(), BODY, ALERTS, set())
    out["controls: an EMPTY label index is UNVERIFIED, not 'nothing exists'"] = (
        r["passed"] is False and count(r["problems"], lambda p: "EMPTY" in p) == 2)
    r = cc(plan(), BODY, set(), METRICS)
    out["controls: an empty alert oracle => alertnames UNVERIFIED => FAIL"] = (
        r["passed"] is False and count(r["problems"], lambda p: "UNVERIFIED" in p and "alertname" in p) == 3)
    r = cc(plan(), "## 4. Verification\n\npods Ready, HR Ready.\n", ALERTS, METRICS)
    out["controls: no CONTROL: line => FAIL even with nothing else to check"] = (
        r["passed"] is False and count(r["problems"], lambda p: "no CONTROL: line" in p) == 1)
    r = cc(plan(premises=[]), BODY, ALERTS, METRICS)
    out["controls: a plan with no premises but CONTROL lines is judged on the lines"] = r["passed"] is True

    # --- repo_alertnames: only PrometheusRule manifests count -------------------
    with tempfile.TemporaryDirectory() as td:
        k = Path(td) / "kubernetes" / "apps" / "monitoring"
        k.mkdir(parents=True)
        (k / "rules.yaml").write_text(
            "apiVersion: monitoring.coreos.com/v1\nkind: PrometheusRule\nspec:\n  groups:\n"
            "    - name: g\n      rules:\n        - alert: RealAlertOne\n          expr: up == 0\n"
            "        - alert: \"RealAlertTwo\"\n          expr: up == 0\n")
        (k / "notarule.yaml").write_text("kind: ConfigMap\ndata:\n  alert: NotAnAlert\n")
        found = pp.repo_alertnames(Path(td))
    out["repo_alertnames: reads alert: keys from PrometheusRule manifests only"] = (
        found == {"RealAlertOne", "RealAlertTwo"})
    out["repo_alertnames: no kubernetes/ dir => empty (UNVERIFIED downstream), not a crash"] = (
        pp.repo_alertnames(Path(tempfile.gettempdir()) / "definitely-not-a-repo-x") == set())
    real = pp.repo_alertnames()
    out["repo_alertnames: the real repo declares alerts, including the frigate mitigation guard"] = (
        len(real) > 100 and "ContainerRestartMitigationStale" in real)
    return out


# ---------------------------------------------------------------------------
# straws
# ---------------------------------------------------------------------------
def straw_fail_open(plan_, body, alert_oracle, metric_oracle):
    """Pre-fix semantics: nothing is checked, so nothing can fail."""
    names = pp.gate_names(plan_, body)
    results = [{"kind": "alertname", "name": a, "passed": True} for a in names["alertnames"]] + \
              [{"kind": "metric", "name": m, "passed": True} for m in names["metrics"]]
    return {"plan_id": plan_.get("plan_id"), "control_lines": names["control_lines"],
            "results": results, "problems": [], "passed": True}


def straw_no_label_blanking(expr):
    """A harvester that forgets to blank label groups: `outcome` leaks in."""
    import re
    import urllib.parse
    expr = urllib.parse.unquote(expr or "")
    names = set(pp._NAME_LABEL_RE.findall(expr))
    stripped = re.sub(r'"[^"]*"', ' ', expr)
    for m in pp._IDENT_RE.finditer(stripped):
        tok = m.group(1)
        if tok in pp.PROMQL_WORDS or stripped[m.end():].lstrip().startswith("("):
            continue
        names.add(tok)
    return names


MUST_FAIL_OPEN = [
    "controls: an undeclared alertname FAILS and is named",
    "controls: a metric absent from the label index FAILS and is named",
    "controls: no metric oracle => every metric UNVERIFIED => FAIL (never pass)",
    "controls: an EMPTY label index is UNVERIFIED, not 'nothing exists'",
    "controls: an empty alert oracle => alertnames UNVERIFIED => FAIL",
    "controls: no CONTROL: line => FAIL even with nothing else to check",
]
MUST_FAIL_HARVEST = [
    "promql: URL-encoded dotted __name__ matcher yields the dotted metric, NOT the by-label",
    "promql: labels inside {} and by() are never metrics",
]


def main() -> int:
    print("test-plan-controls-check")
    for name, ok in scenarios().items():
        check(name, ok)

    print("  -- commissioning straw: a fail-OPEN check (the pre-fix 'no check')")
    under = scenarios(check_controls=straw_fail_open)
    failed = [n for n in MUST_FAIL_OPEN if under.get(n) is False]
    check("straw: every fail-closed check FAILS under the fail-open straw",
          len(failed) == len(MUST_FAIL_OPEN), f"still passing: {sorted(set(MUST_FAIL_OPEN) - set(failed))}")
    check("straw: the all-present control still passes under the straw",
          under.get("controls: every instrument present + CONTROL lines => PASS") is True)

    print("  -- commissioning straw: a harvester that does not blank label groups")
    under2 = scenarios(harvest=straw_no_label_blanking)
    failed2 = [n for n in MUST_FAIL_HARVEST if under2.get(n) is False]
    check("straw: the label-leak checks FAIL under the naive harvester",
          len(failed2) == len(MUST_FAIL_HARVEST), f"still passing: {sorted(set(MUST_FAIL_HARVEST) - set(failed2))}")

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("all plan-controls-check tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
