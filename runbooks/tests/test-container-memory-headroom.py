#!/usr/bin/env python3
"""
Regression test for the per-container memory-headroom check in health-check.sh
(added 2026-08-24 to close a coverage gap).

Nothing in the sweep or in the alert rules watched a container walking into its
OWN cgroup limit. health-check.sh measured memory only per NODE; Prometheus has
105 rule groups and 8 memory-related alert rules, none of them
container-vs-its-limit.

Found the hard way: frigate leaked 5683 -> 8078 MiB against an 8Gi limit over
seven days. It never OOMKilled -- the main process is not what trips the cgroup
-- so `restarts: 0` and the "No OOM kills" assertion both stayed green while its
ffmpeg children died with ENOMEM and camera detect threads dropped. The only
trace in the whole sweep was six log lines scored MINOR.

The interesting half is the discriminator. LEVEL ALONE IS NOT THE SIGNAL:
penpot-frontend sits flat at 98.5% of a 512Mi limit indefinitely -- reclaimable
page cache, entirely benign. A ratio-only assertion would have made that a
permanent unclearable MAJOR, which is the anti-pattern this repo has shipped
three times (see docs/sops/audit-script-correctness.md). The check therefore
requires level AND 24h growth: a plateau is fine, a climb is a leak with a
deadline.

The classifier is extracted from health-check.sh so behaviour, not a copy, runs.

Run: python3 runbooks/tests/test-container-memory-headroom.py
"""
import json
import pathlib
import re
import subprocess
import sys

HC = pathlib.Path(__file__).resolve().parents[1] / "health-check.sh"
src = HC.read_text()
PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}\n        got {got!r} want {want!r}")
        FAIL += 1


m = re.search(r'MEM_HEADROOM=\$\(MEM_RATIO_JSON=.*?python3 -c "\n(.*?)\n" '
              r'2>/dev/null', src, re.S)
check("classifier is extractable from health-check.sh", m is not None, True)
if not m:
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1)
classifier = m.group(1)


def prom(points):
    return json.dumps({"status": "success", "data": {"result": [
        {"metric": {"namespace": ns, "pod": pod, "container": c},
         "value": [0, str(v)]}
        for (ns, pod, c), v in points.items()]}})


def run(ratio, delta, limit):
    r = subprocess.run(
        [sys.executable, "-c", classifier], capture_output=True, text=True,
        env={"MEM_RATIO_JSON": ratio, "MEM_DELTA_JSON": delta,
             "MEM_LIMIT_JSON": limit, "PATH": "/usr/bin:/bin"})
    return r.stdout.strip().splitlines()


GI = 1024 ** 3
FRIGATE = ("home-automation", "frigate", "frigate")
PENPOT = ("office", "penpot-frontend", "penpot-frontend")

# ------------------------------------------------ the leak must be caught
out = run(prom({FRIGATE: 98.6}),
          prom({FRIGATE: 0.031 * 8 * GI}),      # +3.1% of limit in 24h
          prom({FRIGATE: 8 * GI}))
check("a container climbing into its limit is CRITICAL",
      [l.split()[0] for l in out], ["EXAMINED", "CRIT"])

# ------------------------------------- the benign plateau must NOT be caught
out = run(prom({PENPOT: 98.5}), prom({PENPOT: 0}), prom({PENPOT: 512 * 2 ** 20}))
check("a flat plateau at 98.5% is not flagged", out, ["EXAMINED 1 0 0"])

# A plateau that wobbles slightly must also stay quiet.
out = run(prom({PENPOT: 98.5}),
          prom({PENPOT: 0.004 * 512 * 2 ** 20}),
          prom({PENPOT: 512 * 2 ** 20}))
check("sub-threshold drift at a plateau is not flagged", out, ["EXAMINED 1 0 0"])

# ------------------------------------------------------ graded severities
out = run(prom({FRIGATE: 92.0}),
          prom({FRIGATE: 0.03 * 8 * GI}),
          prom({FRIGATE: 8 * GI}))
check("rising but below 95% is MAJOR, not CRITICAL",
      [l.split()[0] for l in out], ["EXAMINED", "MAJOR"])

out = run(prom({FRIGATE: 80.0}),
          prom({FRIGATE: 0.10 * 8 * GI}),
          prom({FRIGATE: 8 * GI}))
check("fast growth well below the limit is not yet a finding",
      out, ["EXAMINED 1 0 0"])

# ------------------------------- a pod younger than the window is not silent
out = run(prom({FRIGATE: 97.0}), prom({}), prom({FRIGATE: 8 * GI}))
check("at-limit with no 24h baseline is MAJOR with the gap stated",
      [l.split()[0] for l in out], ["EXAMINED", "MAJOR", "INFO"])
check("the missing-baseline case says so in the text",
      any("no 24h baseline" in l for l in out), True)

# ------------------------------------------------ identity, not pod identity
# The finding must key on namespace/container. A pod name carries the
# ReplicaSet hash, so keying on it forks a new finding row on every restart --
# and digit-stripping in the fingerprinter does not save it, because the hash
# is alphanumeric.
out = run(prom({FRIGATE: 98.6}),
          prom({FRIGATE: 0.031 * 8 * GI}),
          prom({FRIGATE: 8 * GI}))
crit_line = next(l for l in out if l.startswith("CRIT "))
ident = crit_line[len("CRIT "):].split("|", 1)[0]
check("the CRIT identity is namespace/container, not the pod",
      ident, "home-automation/frigate")
check("the pod is still named, in the detail half",
      "pod frigate" in crit_line.split("|", 1)[1], True)

# ------------------------------------------------- not-measured is not a pass
check("both queries empty -> NOT-MEASURED", run("", "", ""),
      ["NOT-MEASURED query-failed"])
check("a Prometheus error status -> NOT-MEASURED",
      run('{"status":"error"}', prom({}), prom({})),
      ["NOT-MEASURED query-failed"])
check("non-JSON body -> NOT-MEASURED",
      run("<html>502</html>", prom({}), prom({})),
      ["NOT-MEASURED query-failed"])
check("an empty ratio series is not a healthy zero",
      run(prom({}), prom({}), prom({})),
      ["NOT-MEASURED no-container-has-a-memory-limit"])

# ------------------------------------------------------------- denominator
many = {(f"ns{i}", f"pod{i}", "c"): 10.0 for i in range(208)}
out = run(prom(many), prom({}), prom({}))
check("the examined count is reported as the control",
      out, ["EXAMINED 208 0 0"])

# --------------------------------------------------------- wiring assertions
check("the check raises a CRITICAL finding, not just a log line",
      "add_critical_issue \"Container" in src, True)
check("the finding explains why restarts/OOMKill stay green",
      "child allocations fail with ENOMEM first" in src, True)
check("the not-measured branch raises its own finding",
      "leak-into-limit unverified this cycle" in src, True)
check("the green branch names its denominator",
      "limited containers examined" in src, True)
check("the finding backticks the identity so it survives rewording",
      "add_critical_issue \"Container \\`$ident\\`" in src, True)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
