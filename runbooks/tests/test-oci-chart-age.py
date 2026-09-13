#!/usr/bin/env python3
"""F-88bf8743 — an oci:// chart source must produce a MEASURABLE age.

Before this fix, chart_publish_age_hours() short-circuited every oci:// source
to None. Because unknown age is hold-fail-safe, that turned the G5 cooldown into
a PERMANENT hold instead of a wait: kube-prometheus-stack could never elapse it,
no matter how old the release became.

The two properties that matter, and the reason both are asserted here:
  1. oci:// is RESOLVED, not skipped  -> the hold becomes a bounded wait
  2. an unresolvable source is None   -> the fail-safe hold is PRESERVED

(2) is the dangerous direction. A future refactor that makes the resolver
"helpful" by returning 0.0 or time.now() on failure would silently convert every
unreachable registry into an instant cooldown PASS -- the exact inversion this
gate exists to prevent. Offline by design: no network, so it cannot flake.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import coverage

failures = []

# 1. Unresolvable sources must stay None (fail-safe hold preserved).
for url, chart, ver in [
    ("oci://nonexistent.invalid/ns", "chart", "1.0.0"),
    ("oci://", "chart", "1.0.0"),
    ("oci://ghcr.io/definitely/not/a/real/chart/path", "nope", "0.0.0"),
]:
    got = coverage._oci_chart_created(url, chart, ver)
    if got is not None:
        failures.append(f"unresolvable {url!r} returned {got!r}, expected None "
                        f"(fail-safe hold lost)")

# 2. The oci:// branch must be WIRED into chart_publish_age_hours -- i.e. the
#    function must consult the resolver rather than short-circuit to None.
called = {}
orig = coverage._oci_chart_created
try:
    coverage._oci_chart_created = lambda u, c, v, **kw: called.setdefault("hit", (u, c, v)) and 123.0 or 123.0
    coverage._CHART_AGE_CACHE.clear()
    item = {"namespace": "monitoring", "component": "kube-prometheus-stack", "target": "90.2.0"}
    orig_src = coverage._chart_source_for
    coverage._chart_source_for = lambda i: ("kube-prometheus-stack",
                                            "oci://ghcr.io/prometheus-community/charts")
    age = coverage.chart_publish_age_hours(item)
    if "hit" not in called:
        failures.append("chart_publish_age_hours did NOT consult the oci resolver "
                        "-- oci:// is being skipped again, hold is permanent")
    if age != 123.0:
        failures.append(f"chart_publish_age_hours returned {age!r}, expected the "
                        f"resolver's 123.0")
finally:
    coverage._oci_chart_created = orig
    coverage._chart_source_for = orig_src
    coverage._CHART_AGE_CACHE.clear()

if failures:
    print("FAIL test-oci-chart-age")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("PASS test-oci-chart-age")
