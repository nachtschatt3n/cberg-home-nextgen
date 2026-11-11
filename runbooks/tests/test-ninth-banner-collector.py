#!/usr/bin/env python3
"""Tests for the collector in scripts/ninth-banner-test.sh (CI runner results).

No cluster and no Job: a fake kubectl (TNB_KUBECTL) replays saved Job and pod
states, one per look of the collector, and the script runs with `--collect` on
a job.yaml rendered from the real job template. Pins:
- summary.txt holds exactly one `CI-RESULT ... shard=i/N` line per shard, in
  shard order, for every way a shard can end: its own PASS / FAIL rc=<n>, pod
  killed at its deadline, clone failed, out of memory, evicted, Job deadline
  (was running, was starting, never scheduled, never started, found over by a
  collector that came later), Job gone, pod gone, collector stopped, cluster
  unreadable;
- a shard the Job's deadline removed says how long it had: with (nearly) its
  whole pod deadline the advice is a longer deadline, not a rerun; a collector
  that came after the deadline never says that no pod was created;
- a lost shard is `result=FAIL rc=?` and nothing in its line reads as a
  verdict (the caller's wait tool counts result=PASS, takes result=FAIL
  rc=<number> as a real red and everything else as lost);
- a kubectl read that fails is "not readable in this look", never "no pod";
- the summary is written in one step, also when a signal stops the collector
  and when its stdout is a closed pipe; a second collector is refused;
- sims deadlines: pod 12600 s, Job = rounds x (pod deadline + 300 s), shown by
  DRY_RUN=1 without one kubectl call.
Runs under every bash found (/bin/bash 3.2 on macOS is the production one).
"""
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(ROOT, "scripts", "ninth-banner-test.sh")
TEMPLATE = os.path.join(ROOT, "kubernetes", "apps", "ci-runner", "the-ninth-banner-tests", "job-template.yaml.tpl")
SHA = "0123456789abcdef0123456789abcdef01234567"

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# One state file per look: job.<n>, pods.<n>, logs-<pod>-<container>.<n>; the
# newest one at or before the current look counts. `get job` starts a look.
FAKE_KUBECTL = r'''
import os, sys
d = os.environ["FAKE_KUBE_DIR"]
a = sys.argv[1:]
with open(os.path.join(d, "calls.log"), "a") as f:
    f.write(" ".join(a[:6]) + "\n")
def look():
    try:
        return int(open(os.path.join(d, "look")).read())
    except (OSError, ValueError):
        return 0
def state(kind, n):
    best = None
    for name in os.listdir(d):
        if name.startswith(kind + "."):
            try:
                k = int(name[len(kind) + 1:])
            except ValueError:
                continue
            if k <= n and (best is None or k > best):
                best = k
    return None if best is None else open(os.path.join(d, "%s.%d" % (kind, best))).read()
def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)
if a[:2] == ["get", "job"]:
    n = look() + 1
    open(os.path.join(d, "look"), "w").write(str(n))
    s = state("job", n)
    if s is None or s == "ERROR":
        fail("Unable to connect to the server: dial tcp: i/o timeout")
    if s == "NOTFOUND":
        fail('Error from server (NotFound): jobs.batch "%s" not found' % a[4])
    sys.stderr.write("mise WARN  a warning of the tool wrapper Failed:NotACondition\n")
    sys.stdout.write(s)
elif a[:2] == ["get", "pods"]:
    s = state("pods", look())
    if s is None or s == "ERROR":
        fail("Unable to connect to the server: dial tcp: i/o timeout")
    sys.stdout.write(s)
elif a[0] == "logs":
    s = state("logs-%s-%s" % (a[3], a[5]), look())
    if s is None or s == "ERROR":
        fail('Error from server (BadRequest): container "%s" in pod "%s" is not available' % (a[5], a[3]))
    sys.stdout.write(s)
elif a[0] == "cp":
    if os.path.exists(os.path.join(d, "cp-fails")):
        fail("error: cannot exec into a container in a completed pod")
elif a[0] == "exec":
    pass
else:
    fail("fake kubectl: unexpected call " + " ".join(a))
'''

FAKE_GH = '''#!/bin/sh
# fake gh: resolves a ref to a sha; every other read fails (no runner.json)
echo "$*" >> "$FAKE_GH_LOG"
case "$1 $2" in
    "api repos/"*"/commits/"*) echo %s ;;
    *) exit 1 ;;
esac
''' % SHA

RENDER = {
    "JOB_NAME": None, "REF": SHA, "SUITE": None, "SUBMITTER": "test", "SHARDS": None, "PARALLELISM": None,
    "DEADLINE": None, "POD_DEADLINE": None, "WORKERS": "2", "COLLECT_WAIT": "900", "CPU_REQ": "1",
    "CPU_LIM": "1.5", "GPU_RES": "", "LANE": "cpu", "MEM_REQ": "1Gi", "MEM_LIM": "3Gi", "EPH_REQ": "2Gi",
    "EPH_LIM": "8Gi", "CHROMIUM_ARGS": "", "SPECS": "", "PROJECT": "",
}


def pod(idx, name, phase, reason="", node="", sched="", iwait="", iexit="", cwait="", cterm="", cexit="", message="",
        started=""):
    """One line of the collector's pod read (the fields of pod_fields in the script)."""
    return "|".join([str(idx), name, phase, reason, node, sched, iwait, str(iexit), cwait, cterm, str(cexit), started,
                     message])


def result(suite, n, of, verdict="PASS", rc=0):
    """What app/scripts/run.sh prints when a shard has staged its results."""
    return ("sims output of shard %d\nCI-RESULT suite=%s shard=%d/%d result=%s rc=%d test_seconds=5012 total_seconds=5100\n"
            "CI-RESULTS-READY\n" % (n, suite, n, of, verdict, rc))


class Farm:
    """A results folder with a rendered job.yaml, and the saved cluster states of one scenario."""

    def __init__(self, tmp, shards, suite="sims", parallelism=2, deadline=38700, pod_deadline=12600, age=60,
                 job="tnb-sims-0123456-1111091057", job_yaml=None):
        self.tmp, self.job, self.suite, self.shards = tmp, job, suite, shards
        self.results = os.path.join(tmp, "results")
        self.dest = os.path.join(self.results, job)
        self.kube = os.path.join(tmp, "kube")
        os.makedirs(self.dest)
        os.makedirs(self.kube)
        self.fake = os.path.join(tmp, "fake-kubectl.py")
        with open(self.fake, "w") as f:
            f.write(FAKE_KUBECTL)
        if job_yaml is None:
            job_yaml = open(TEMPLATE).read()
            values = dict(RENDER, JOB_NAME=job, SUITE=suite, SHARDS=shards, PARALLELISM=parallelism,
                          DEADLINE=deadline, POD_DEADLINE=pod_deadline)
            for key, value in values.items():
                job_yaml = job_yaml.replace("__%s__" % key, str(value))
        with open(os.path.join(self.dest, "job.yaml"), "w") as f:
            f.write(job_yaml)
        t = time.time() - age
        os.utime(os.path.join(self.dest, "job.yaml"), (t, t))
        self.start = int(os.path.getmtime(os.path.join(self.dest, "job.yaml")))   # as the collector reads it

    def at(self, seconds):
        """The cluster's timestamp for a pod that started that long after the Job."""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.start + seconds))

    def pod_name(self, idx):
        return "%s-%d-%s" % (self.job, idx, "abcdefgh"[idx % 8] * 5)

    def look(self, n, job_state, pods):
        """From look n on: the Job's conditions ('' = active, 'NOTFOUND', 'ERROR') and its pod lines (or 'ERROR')."""
        with open(os.path.join(self.kube, "job.%d" % n), "w") as f:
            f.write(job_state)
        with open(os.path.join(self.kube, "pods.%d" % n), "w") as f:
            f.write(pods if isinstance(pods, str) else "".join(p + "\n" for p in pods))

    def logs(self, idx, text, container="runner", n=1):
        with open(os.path.join(self.kube, "logs-%s-%s.%d" % (self.pod_name(idx), container, n)), "w") as f:
            f.write(text)

    def reset_cluster(self):
        shutil.rmtree(self.kube)
        os.makedirs(self.kube)

    def env(self, poll="0"):
        return dict(os.environ, RESULTS_DIR=self.results, FAKE_KUBE_DIR=self.kube, TNB_COLLECT_POLL=poll,
                    TNB_KUBECTL="%s -S %s" % (sys.executable, self.fake))

    def cmd(self, bash):
        return [bash, SCRIPT, "--collect", self.job]

    def collect(self, bash, poll="0"):
        return subprocess.run(self.cmd(bash), env=self.env(poll), capture_output=True, text=True, timeout=180)

    def read(self, name):
        try:
            return open(os.path.join(self.dest, name)).read()
        except OSError:
            return None

    def summary(self):
        text = self.read("summary.txt")
        return None if text is None else text.splitlines()

    def looks(self):
        try:
            return int(open(os.path.join(self.kube, "look")).read())
        except (OSError, ValueError):
            return 0

    def calls(self):
        try:
            return open(os.path.join(self.kube, "calls.log")).read().splitlines()
        except OSError:
            return []

    def leftovers(self):
        return sorted(n for n in os.listdir(self.dest)
                      if n.endswith(".tmp") or n in ("collector.pid", "collector.err"))


LOST = re.compile(r"^CI-RESULT suite=\S+ shard=\d+/\d+ result=FAIL rc=\? "
                  r"\(lost: ([a-z ]+): (.+); partial log, if any, in shard-\d+\.log\)$")


def verdicts(lines):
    """(pass, real red, lost): counted exactly as the caller's wait tool counts summary.txt."""
    p = sum(1 for line in lines if "result=PASS" in line)
    f = sum(1 for line in lines if re.search(r"result=FAIL rc=[0-9]", line))
    return p, f, len(lines) - p - f


def shape_ok(farm, lines):
    """One line per shard, in shard order; a lost line is rc=? and holds no second verdict."""
    if lines is None or len(lines) != farm.shards:
        return False
    for i, line in enumerate(lines):
        if not line.startswith("CI-RESULT suite=%s shard=%d/%d result=" % (farm.suite, i + 1, farm.shards)):
            return False
        if line.count("result=") != 1 or line.count("rc=") != 1:
            return False
        if "rc=?" in line and not LOST.match(line):
            return False
    return True


def kinds(lines):
    out = []
    for line in lines or []:
        m = LOST.match(line)
        out.append(m.group(1) if m else ("PASS" if "result=PASS" in line else "RED"))
    return out


def ends_with_its_line(farm, lines, shard):
    """The shard's own log on the Mac ends with the line that went into the summary."""
    text = farm.read("shard-%d.log" % shard) or ""
    return bool(lines) and text.rstrip("\n").split("\n")[-1] == lines[shard - 1] and text.count("rc=? (lost: ") == 1


def wait_for(cond, seconds=30):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


# ---------------------------------------------------------------- scenarios

def a_normal_job(bash, tag):
    """8 shards as the cluster showed them on 2026-11-11 (indexes 0, 6 and 7 are that read, verbatim)."""
    with tempfile.TemporaryDirectory() as tmp:
        farm = Farm(tmp, 8, parallelism=6, deadline=25800, age=7200)
        pods = [pod(0, farm.pod_name(0), "Succeeded", node="k8s-nuc14-01", iexit=0, cterm="Completed", cexit=0)]
        pods += [pod(i, farm.pod_name(i), "Succeeded", node="k8s-nuc14-02", iexit=0, cterm="Completed", cexit=0)
                 for i in range(1, 6)]
        pods += [pod(6, farm.pod_name(6), "Failed", node="k8s-nuc14-03", iexit=0, cterm="Error", cexit=1),
                 pod(7, farm.pod_name(7), "Running", node="k8s-nuc14-01", iexit=0)]
        farm.look(1, "", pods)
        farm.look(2, "Failed:FailedIndexes ", pods[:7] + [pod(7, farm.pod_name(7), "Succeeded", node="k8s-nuc14-01",
                                                              iexit=0, cterm="Completed", cexit=0)])
        for i in range(6):
            farm.logs(i, result("sims", i + 1, 8))
        farm.logs(6, result("sims", 7, 8, "FAIL", 1))
        farm.logs(7, "sims output of shard 8, still running\n")
        farm.logs(7, result("sims", 8, 8), n=2)
        r = farm.collect(bash)
        lines = farm.summary()
        check(tag + "normal job: one line per shard, in shard order", shape_ok(farm, lines))
        check(tag + "normal job: 7 pass, 1 real red, 0 lost; exit 1", verdicts(lines or []) == (7, 1, 0) and r.returncode == 1)
        check(tag + "normal job: no lost line, nothing left behind",
              "lost" not in (farm.read("summary.txt") or "lost") and farm.leftovers() == [])
        check(tag + "normal job: the red is the shard's own rc", bool(lines) and "shard=7/8 result=FAIL rc=1 " in lines[6])
        check(tag + "normal job: two looks, results copied from each pod once",
              farm.looks() == 2 and sum(1 for c in farm.calls() if c.startswith("cp ")) == 8)
        check(tag + "normal job: final report names the count", "1/8 shards failed, 0 of them lost" in r.stdout)
        # a re-attached collector first sees a pod long after it started: the window to read
        # its log from Elastic has to open at the Job's submit time, not at this collector's start
        submitted = os.path.getmtime(os.path.join(farm.dest, "job.yaml"))
        opens = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(submitted) - 300))
        check(tag + "normal job: the log recovery window opens 5 min before the Job was submitted",
              "shard 1/8 logs: scripts/ninth-banner-logs.sh %s %s " % (farm.pod_name(0), opens) in r.stdout
              and "logs shard 8/8: scripts/ninth-banner-logs.sh %s %s " % (farm.pod_name(7), opens) in r.stdout)


def b_dead_pods(bash, tag):
    """Every way one pod ends without results, next to a real PASS and a real red."""
    with tempfile.TemporaryDirectory() as tmp:
        farm = Farm(tmp, 6, parallelism=6, deadline=12900)
        n = farm.pod_name
        farm.look(1, "", [
            pod(0, n(0), "Running", node="k8s-nuc14-01", iexit=0),
            pod(1, n(1), "Failed", node="k8s-nuc14-03", iexit=0, cterm="Error", cexit=1),
            # killed at activeDeadlineSeconds of the pod: phase Failed, reason DeadlineExceeded, pod stays
            pod(2, n(2), "Failed", "DeadlineExceeded", "k8s-nuc14-02", iexit=0, cterm="Error", cexit=137,
                message="Pod was active on the node longer than the specified deadline"),
            pod(3, n(3), "Failed", node="k8s-nuc14-01", iexit=128, cwait="PodInitializing"),
            pod(4, n(4), "Failed", node="k8s-nuc14-02", iexit=0, cterm="OOMKilled", cexit=137),
            pod(5, n(5), "Failed", "Evicted", "k8s-nuc14-03", iexit=0, cterm="Error", cexit=137,
                message="The node was low on resource: ephemeral-storage. Threshold quantity: 10Gi, rc=1 result=PASS"),
        ])
        farm.logs(0, result("sims", 1, 6))
        farm.logs(1, result("sims", 2, 6, "FAIL", 1))
        farm.logs(2, "sims output of shard 3, cut at the deadline\n")
        farm.logs(3, "Cloning...\nfatal: Authentication failed\n", container="clone")
        farm.logs(4, "sims output of shard 5\n")
        farm.logs(5, "sims output of shard 6\n")
        r = farm.collect(bash)
        lines = farm.summary()
        check(tag + "dead pods: one line per shard, in shard order", shape_ok(farm, lines))
        check(tag + "dead pods: 1 pass, 1 real red, 4 lost; exit 1", verdicts(lines or []) == (1, 1, 4) and r.returncode == 1)
        check(tag + "dead pods: kinds", kinds(lines) == ["PASS", "RED", "pod deadline", "clone failed", "out of memory", "evicted"])
        check(tag + "dead pods: the deadline line names the value and what to do",
              bool(lines) and "ran past pod_deadline=12600s" in lines[2] and "TNB_POD_DEADLINE" in lines[2]
              and "k8s-nuc14-02" in lines[2])
        check(tag + "dead pods: clone exit code, and the clone output in the shard's log",
              bool(lines) and "exit code 128" in lines[3] and "Authentication failed" in (farm.read("shard-4.log") or ""))
        check(tag + "dead pods: a verdict inside a pod message is defused",
              bool(lines) and "low on resource" in lines[5] and "rc 1 result PASS" in lines[5])
        check(tag + "dead pods: each lost shard's own log ends with its line",
              all(ends_with_its_line(farm, lines, s) for s in (3, 4, 5, 6)))
        check(tag + "dead pods: the partial log is kept", "cut at the deadline" in (farm.read("shard-3.log") or ""))
        check(tag + "dead pods: a log read that fails gets three looks", farm.looks() == 3)
        check(tag + "dead pods: final report", "5/6 shards failed, 4 of them lost" in r.stdout and farm.leftovers() == [])


def c_job_deadline(bash, tag, job_yaml):
    """The Job hits its own deadline: its pods are deleted, pending indexes never start."""
    with tempfile.TemporaryDirectory() as tmp:
        farm = Farm(tmp, 6, job_yaml=job_yaml)   # the script's own dry render: parallel 3, 25800 s
        n = farm.pod_name
        pods = [pod(0, n(0), "Running", node="k8s-nuc14-01", iexit=0, started=farm.at(20000)),   # waited long for a node
                pod(1, n(1), "Pending", sched="Unschedulable"),
                pod(2, n(2), "Pending", node="k8s-nuc14-02", cwait="PodInitializing")]
        farm.look(1, "", pods)
        farm.look(2, "FailureTarget:DeadlineExceeded ", pods)          # pods still being removed
        farm.look(3, "Failed:DeadlineExceeded ", [])
        farm.logs(0, "sims output of shard 1, cut by the Job\n")
        r = farm.collect(bash)
        lines = farm.summary()
        check(tag + "job deadline: one line per shard, all lost; exit 1",
              shape_ok(farm, lines) and verdicts(lines or []) == (0, 0, 6) and r.returncode == 1)
        check(tag + "job deadline: kinds",
              kinds(lines) == ["job deadline", "never scheduled", "never started", "never started", "never started", "never started"])
        check(tag + "job deadline: the lines name the Job's deadline from job.yaml",
              bool(lines) and all("deadline of 25800s" in line for line in lines))
        check(tag + "job deadline: the running shard's pod and node are named, its log kept",
              bool(lines) and "last seen Running on k8s-nuc14-01" in lines[0] and ends_with_its_line(farm, lines, 1)
              and "cut by the Job" in (farm.read("shard-1.log") or ""))
        check(tag + "job deadline: a shard that started late says how long it had, and to rerun",
              bool(lines) and "did not start until 20000s into the Job, so it had 5800s instead of pod_deadline=12600s: rerun;"
              in lines[0] and "TNB_POD_DEADLINE" not in lines[0])
        check(tag + "job deadline: never scheduled says where to look",
              bool(lines) and "Unschedulable" in lines[1] and "ci-runner quota" in lines[1])
        check(tag + "job deadline: a shard without a slot: no pod of it was seen",
              bool(lines) and all("before a slot was free for this shard (parallel 3), no pod of it was seen: rerun;" in line
                                  for line in lines[3:]))
        check(tag + "job deadline: three looks", farm.looks() == 3 and farm.leftovers() == [])


def c2_job_deadline_full_time(bash, tag):
    """A suite whose Job and pod deadline are the same: the Job's fires first and removes the pod
    (2026-11-11, tnb-unit-6a1c032-1111133959: started 1 s into the Job, needed more than 5400 s)."""
    with tempfile.TemporaryDirectory() as tmp:
        farm = Farm(tmp, 3, suite="unit", parallelism=3, deadline=5400, pod_deadline=5400, job="tnb-unit-0123456-1111133959")
        n = farm.pod_name
        pods = [pod(0, n(0), "Running", node="k8s-nuc14-01", iexit=0, started=farm.at(1)),
                pod(1, n(1), "Running", node="k8s-nuc14-02", iexit=0),                        # no start time in the read
                pod(2, n(2), "Running", node="k8s-nuc14-03", iexit=0, started=farm.at(-2))]   # cluster clock behind the Mac's
        farm.look(1, "", pods)
        farm.look(2, "Failed:DeadlineExceeded ", [])
        for i in range(3):
            farm.logs(i, "unit output of shard %d, cut by the Job\n" % (i + 1))
        r = farm.collect(bash)
        lines = farm.summary()
        check(tag + "full time: one line per shard, all lost as job deadline; exit 1",
              shape_ok(farm, lines) and verdicts(lines or []) == (0, 0, 3) and kinds(lines) == ["job deadline"] * 3
              and r.returncode == 1)
        check(tag + "full time: the shard had its whole pod deadline: a longer deadline, not a rerun",
              bool(lines) and "had started 1s into the Job, so it had 5399s (pod_deadline=5400s) and did not finish" in lines[0]
              and "a rerun gets little or no more time: it needs a longer deadline (TNB_POD_DEADLINE) or less work;" in lines[0]
              and "started too late" not in lines[0] and ": rerun;" not in lines[0])
        check(tag + "full time: a start time that cannot be read is said, both ways out named",
              bool(lines) and "when the shard started is not known: rerun; if it had run from the Job's start" in lines[1]
              and "TNB_POD_DEADLINE" in lines[1])
        check(tag + "full time: a pod start before the Job's (clock skew) counts as the Job's start",
              bool(lines) and "had started 0s into the Job, so it had 5400s (pod_deadline=5400s)" in lines[2])
        check(tag + "full time: each shard's log is kept and ends with its line",
              all(ends_with_its_line(farm, lines, s) and "cut by the Job" in (farm.read("shard-%d.log" % s) or "")
                  for s in (1, 2, 3)) and farm.leftovers() == [])


def c3_after_job_deadline(bash, tag):
    """A collector that attaches after the Job's deadline finds no pod: it must not say that none was created
    (2026-11-11: said 'never started ... no pod was created' of a shard that had run for 90 min)."""
    with tempfile.TemporaryDirectory() as tmp:
        farm = Farm(tmp, 3, suite="unit", parallelism=2, deadline=5400, pod_deadline=5400, age=5460,
                    job="tnb-unit-0123456-1111133959")
        stopped = ("CI-RESULT suite=unit shard=%d/3 result=FAIL rc=? (lost: collector stopped: the collector on this Mac "
                   "ended (exit code 143) before this shard reported; partial log, if any, in shard-%d.log)\n")
        with open(os.path.join(farm.dest, "shard-1.log"), "w") as f:     # an earlier collector saw this shard run
            f.write("unit output of shard 1, up to the earlier collector's last look\n" + stopped % (1, 1))
        with open(os.path.join(farm.dest, "shard-2.log"), "w") as f:     # ... and saw nothing of this one
            f.write(stopped % (2, 2))
        farm.look(1, "Failed:DeadlineExceeded ", [])
        r = farm.collect(bash)
        lines = farm.summary()
        check(tag + "after the deadline: one line per shard, all lost as job deadline; exit 1",
              shape_ok(farm, lines) and verdicts(lines or []) == (0, 0, 3) and kinds(lines) == ["job deadline"] * 3
              and r.returncode == 1)
        check(tag + "after the deadline: never 'no pod was created', never 'never started'",
              bool(lines) and not any("no pod was created" in line or "never started" in line or "no pod of it was seen" in line
                                      for line in lines))
        check(tag + "after the deadline: a shard with saved output had run",
              bool(lines) and "the shard had run (an earlier collector saved its output)" in lines[0]
              and "TNB_POD_DEADLINE" in lines[0])
        check(tag + "after the deadline: without saved output it says what it cannot tell",
              bool(lines) and all("cannot tell a shard that was removed at the deadline from one that never got a slot (parallel 2)"
                                  in line and "TNB_POD_DEADLINE" in line for line in lines[1:]))
        check(tag + "after the deadline: the saved output stays, each log ends with the new line only",
              "up to the earlier collector's last look" in (farm.read("shard-1.log") or "")
              and all(ends_with_its_line(farm, lines, s) for s in (1, 2, 3)))
        check(tag + "after the deadline: decided at the first look", farm.looks() == 1 and farm.leftovers() == [])


def d_job_gone(bash, tag):
    """The Job is deleted while shards still run (two jobs 'vanished')."""
    with tempfile.TemporaryDirectory() as tmp:
        farm = Farm(tmp, 3)
        n = farm.pod_name
        farm.look(1, "", [pod(0, n(0), "Running", node="k8s-nuc14-01", iexit=0),
                          pod(1, n(1), "Running", node="k8s-nuc14-02", iexit=0)])
        farm.look(2, "", [])            # deleted between the Job read and the pod read
        farm.look(3, "NOTFOUND", [])
        farm.logs(0, "sims output of shard 1\n")
        farm.logs(1, "sims output of shard 2\n")
        r = farm.collect(bash)
        lines = farm.summary()
        check(tag + "job gone: one line per shard, all lost; exit 1",
              shape_ok(farm, lines) and verdicts(lines or []) == (0, 0, 3) and r.returncode == 1)
        check(tag + "job gone: kinds", kinds(lines) == ["job gone"] * 3)
        check(tag + "job gone: what was last seen of each shard",
              bool(lines) and "last seen Running on k8s-nuc14-01" in lines[0] and "no pod of this shard was seen" in lines[2])
        check(tag + "job gone: decided at the look that saw the Job gone", farm.looks() == 3 and farm.leftovers() == [])


def e_transient_reads(bash, tag):
    """kubectl fails for a while: nothing is decided on a read that failed."""
    with tempfile.TemporaryDirectory() as tmp:
        farm = Farm(tmp, 2)
        n = farm.pod_name
        pods = [pod(0, n(0), "Running", node="k8s-nuc14-01", iexit=0),
                pod(1, n(1), "Succeeded", node="k8s-nuc14-01", iexit=0, cterm="Completed", cexit=0)]
        farm.look(1, "ERROR", "ERROR")
        farm.look(2, "", "ERROR")
        farm.look(3, "ERROR", [])
        # the Job has ended and the pod list cannot be read: not "no pod"
        farm.look(4, "SuccessCriteriaMet:CompletionsReached Complete:CompletionsReached ", "ERROR")
        farm.look(5, "SuccessCriteriaMet:CompletionsReached Complete:CompletionsReached ", pods)
        farm.logs(0, result("sims", 1, 2), n=5)
        farm.logs(1, "ERROR", n=5)      # an ended pod whose log read fails once
        farm.logs(1, result("sims", 2, 2), n=6)
        r = farm.collect(bash)
        lines = farm.summary()
        check(tag + "transient reads: both shards pass, nothing lost; exit 0",
              shape_ok(farm, lines) and verdicts(lines or []) == (2, 0, 0) and r.returncode == 0)
        check(tag + "transient reads: six looks", farm.looks() == 6 and farm.leftovers() == [])
        check(tag + "transient reads: PASS report", "PASS  sims @ 0123456789ab: 2/2 shards passed" in r.stdout)


def f_pod_gone(bash, tag):
    """A pod is deleted while the Job goes on; a pod list that is behind for one look loses nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        farm = Farm(tmp, 3)
        n = farm.pod_name
        p = [pod(i, n(i), "Running", node="k8s-nuc14-0%d" % (i + 1), iexit=0) for i in range(3)]
        farm.look(1, "", p)
        farm.look(2, "", [p[0], p[2]])      # shard 2's pod missing for one look
        farm.look(3, "", p)
        farm.look(4, "ERROR", p[:2])        # shard 3's pod gone; the Job not readable in this look
        farm.look(5, "", p[:2])
        farm.look(7, "", p[:2])
        for i in range(3):
            farm.logs(i, "sims output of shard %d\n" % (i + 1))
        farm.logs(0, result("sims", 1, 3), n=7)
        farm.logs(1, result("sims", 2, 3), n=7)
        r = farm.collect(bash)
        lines = farm.summary()
        check(tag + "pod gone: 2 pass, 1 lost; exit 1",
              shape_ok(farm, lines) and verdicts(lines or []) == (2, 0, 1) and r.returncode == 1)
        check(tag + "pod gone: kind and the pod named", kinds(lines) == ["PASS", "PASS", "pod gone"]
              and bool(lines) and n(2) in lines[2] and "was deleted before its result was read" in lines[2])
        check(tag + "pod gone: three readable looks without the pod (looks 5, 6, 7)", farm.looks() == 7)
        check(tag + "pod gone: the log ends with the line", ends_with_its_line(farm, lines, 3) and farm.leftovers() == [])


def g_odd_endings(bash, tag):
    with tempfile.TemporaryDirectory() as tmp:
        farm = Farm(tmp, 4, parallelism=6, deadline=12900)
        n = farm.pod_name
        farm.look(1, "", [
            pod(0, n(0), "Running", node="k8s-nuc14-01", iexit=0),
            pod(1, n(1), "Succeeded", node="k8s-nuc14-01", iexit=0, cterm="Completed", cexit=0),
            # deadline while the clone step still ran
            pod(2, n(2), "Failed", "DeadlineExceeded", "k8s-nuc14-02", cwait="PodInitializing"),
            # deadline seen before the kubelet reported the runner's end
            pod(3, n(3), "Failed", "DeadlineExceeded", "k8s-nuc14-03", iexit=0),
        ])
        farm.logs(0, "sims output\nCI-RESULTS-READY\n")
        farm.logs(1, "sims output, no marker\n")
        farm.logs(2, "Cloning...\n", container="clone")
        farm.logs(3, "sims output of shard 4\n")
        r = farm.collect(bash)
        lines = farm.summary()
        check(tag + "odd endings: one line per shard, all lost; exit 1",
              shape_ok(farm, lines) and verdicts(lines or []) == (0, 0, 4) and r.returncode == 1)
        check(tag + "odd endings: kinds", kinds(lines) == ["no result line", "pod died", "pod deadline", "pod deadline"])
        check(tag + "odd endings: deadline before the tests started / after",
              bool(lines) and "before its tests started (PodInitializing)" in lines[2] and "ran past pod_deadline=12600s" in lines[3])
        check(tag + "odd endings: pod died names phase and exit code",
              bool(lines) and "ended Succeeded, runner Completed with exit code 0" in lines[1] and farm.leftovers() == [])


def h_stopped_and_reattached(bash, tag, sig, code):
    """A signal stops the collector: the summary is there; --collect finishes the job later."""
    with tempfile.TemporaryDirectory() as tmp:
        farm = Farm(tmp, 2)
        n = farm.pod_name
        farm.look(1, "", [pod(0, n(0), "Running", node="k8s-nuc14-01", iexit=0),
                          pod(1, n(1), "Running", node="k8s-nuc14-02", iexit=0)])
        farm.logs(0, result("sims", 1, 2))
        farm.logs(1, "sims output of shard 2, running\n")
        p = subprocess.Popen(farm.cmd(bash), env=farm.env(poll="1"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        up = wait_for(lambda: farm.looks() >= 2 and farm.read("collector.pid") is not None)
        check(tag + "stopped: the collector runs and wrote its pid", up and (farm.read("collector.pid") or "").strip() == str(p.pid))
        check(tag + "stopped: no summary while shards are out", farm.read("summary.txt") is None)
        second = farm.collect(bash)
        check(tag + "stopped: a second collector is refused (exit 2) and leaves the first alone",
              second.returncode == 2 and "not starting a second one" in second.stdout
              and (farm.read("collector.pid") or "").strip() == str(p.pid) and farm.read("summary.txt") is None)
        p.send_signal(sig)
        out, _ = p.communicate(timeout=60)
        lines = farm.summary()
        check(tag + "stopped: exit code %d" % code, p.returncode == code)
        check(tag + "stopped: summary has the pass and one lost line",
              shape_ok(farm, lines) and kinds(lines) == ["PASS", "collector stopped"])
        check(tag + "stopped: the line says how to re-attach",
              bool(lines) and "--collect " + farm.job in lines[1] and "exit code %d" % code in lines[1])
        check(tag + "stopped: nothing left behind, the stop is announced",
              farm.leftovers() == [] and "collector stopped (exit code %d)" % code in out)
        # later: the Job is gone; shard 1's result is on disk, shard 2 gets its real reason
        farm.reset_cluster()
        farm.look(1, "NOTFOUND", [])
        r = farm.collect(bash)
        lines = farm.summary()
        check(tag + "re-attached: shard 1 from the log on disk, shard 2 lost with the new reason; exit 1",
              shape_ok(farm, lines) and kinds(lines) == ["PASS", "job gone"] and r.returncode == 1)
        check(tag + "re-attached: the earlier lost line is replaced in the shard's log, the output kept",
              ends_with_its_line(farm, lines, 2) and "running" in (farm.read("shard-2.log") or "") and farm.leftovers() == [])


def i_closed_stdout(bash, tag):
    """The session that started the collector is gone: every write to stdout fails."""
    def closed_pipe():
        r, w = os.pipe()
        os.close(r)
        return w

    with tempfile.TemporaryDirectory() as tmp:
        farm = Farm(tmp, 2)
        n = farm.pod_name
        farm.look(1, "", [pod(0, n(0), "Running", node="k8s-nuc14-01", iexit=0),
                          pod(1, n(1), "Running", node="k8s-nuc14-02", iexit=0)])
        farm.look(3, "", [pod(0, n(0), "Running", node="k8s-nuc14-01", iexit=0),
                          pod(1, n(1), "Failed", "DeadlineExceeded", "k8s-nuc14-02", iexit=0, cterm="Error", cexit=137)])
        farm.logs(0, "sims output of shard 1\n")
        farm.logs(1, "sims output of shard 2\n")
        farm.logs(0, result("sims", 1, 2), n=3)
        farm.logs(1, "clone output of shard 2\n", container="clone")
        w = closed_pipe()
        p = subprocess.Popen(farm.cmd(bash), env=farm.env(), stdout=w, stderr=w)
        os.close(w)
        rc = p.wait(timeout=120)
        lines = farm.summary()
        check(tag + "closed stdout: the collector finishes; exit 1 (one shard lost), not a signal", rc == 1)
        check(tag + "closed stdout: clean summary", shape_ok(farm, lines) and kinds(lines) == ["PASS", "pod deadline"])
        check(tag + "closed stdout: no stray output in the files",
              (farm.read("shard-2.log") or "").startswith("clone output of shard 2\nsims output of shard 2\n")
              and (farm.read("shard-1.log") or "").startswith("sims output of shard 1\n") and farm.leftovers() == [])

    with tempfile.TemporaryDirectory() as tmp:
        farm = Farm(tmp, 2)
        n = farm.pod_name
        farm.look(1, "", [pod(0, n(0), "Running", node="k8s-nuc14-01", iexit=0),
                          pod(1, n(1), "Running", node="k8s-nuc14-02", iexit=0)])
        farm.logs(0, "sims output of shard 1\n")
        farm.logs(1, "sims output of shard 2\n")
        w = closed_pipe()
        p = subprocess.Popen(farm.cmd(bash), env=farm.env(poll="1"), stdout=w, stderr=w)
        os.close(w)
        up = wait_for(lambda: farm.looks() >= 2 and farm.read("collector.pid") is not None)
        check(tag + "closed stdout + HUP: the pid file holds the pid only", up and farm.read("collector.pid") == "%d\n" % p.pid)
        p.send_signal(signal.SIGHUP)
        rc = p.wait(timeout=60)
        lines = farm.summary()
        check(tag + "closed stdout + HUP: exit 129, a line for every shard",
              rc == 129 and shape_ok(farm, lines) and kinds(lines) == ["collector stopped"] * 2 and farm.leftovers() == [])


def j_give_up(bash, tag):
    """Past the Job's latest end plus its TTL nothing can report any more."""
    with tempfile.TemporaryDirectory() as tmp:
        farm = Farm(tmp, 1, suite="unit", parallelism=1, deadline=5400, pod_deadline=5400, age=100000,
                    job="tnb-unit-0123456-1110000000")
        farm.look(1, "ERROR", "ERROR")
        r = farm.collect(bash)
        lines = farm.summary()
        check(tag + "give up: cluster unreadable, one look; exit 1",
              shape_ok(farm, lines) and kinds(lines) == ["cluster unreadable"] and farm.looks() == 1 and r.returncode == 1)
    with tempfile.TemporaryDirectory() as tmp:
        old = open(TEMPLATE).read()
        for key, value in dict(RENDER, JOB_NAME="x", SUITE="sims", SHARDS=1, PARALLELISM=1, DEADLINE=10800).items():
            old = old.replace("__%s__" % key, str(value))
        old = "".join(line + "\n" for line in old.split("\n")[:-1] if not line.startswith("      activeDeadlineSeconds:"))
        farm = Farm(tmp, 1, age=100000, job_yaml=old)     # a job.yaml from before the pod deadline existed
        farm.look(1, "", [pod(0, farm.pod_name(0), "Running", node="k8s-nuc14-01", iexit=0)])
        farm.logs(0, "sims output\n")
        r = farm.collect(bash)
        lines = farm.summary()
        check(tag + "give up: no end state, the pod named; exit 1",
              shape_ok(farm, lines) and kinds(lines) == ["no end state"] and farm.pod_name(0) in lines[0] and r.returncode == 1)
        check(tag + "give up: a job.yaml without a pod deadline falls back to the Job's",
              "deadline=10800s pod_deadline=10800s" in r.stdout)


def k_usage(bash, tag):
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, RESULTS_DIR=tmp, TNB_KUBECTL="false")
        r = subprocess.run([bash, SCRIPT], env=env, capture_output=True, text=True, timeout=60)
        check(tag + "usage: exit 2, both forms, cut before the notes",
              r.returncode == 2 and "--collect <job>" in r.stdout and "<ref> <unit|e2e" in r.stdout
              and "Admission (" not in r.stdout and "# " not in r.stdout)
        r = subprocess.run([bash, SCRIPT, "--collect", "tnb-sims/../x"], env=env, capture_output=True, text=True, timeout=60)
        check(tag + "usage: --collect refuses a name that is not a job", r.returncode == 2 and "not a job name" in r.stdout)
        r = subprocess.run([bash, SCRIPT, "--collect", "tnb-sims-0000000-0101000000"], env=env, capture_output=True, text=True, timeout=60)
        check(tag + "usage: --collect without a job.yaml", r.returncode == 2 and "job.yaml" in r.stdout and os.listdir(tmp) == [])


def l_dry_render(bash, tag):
    """DRY_RUN=1: the Job as it would be created, for every parallelism; no kubectl, no Job, no results folder.
    -> the rendered sims Job at parallelism 3 (used as job.yaml by the Job deadline scenario)."""
    rendered = None
    with tempfile.TemporaryDirectory() as tmp:
        bindir = os.path.join(tmp, "bin")
        os.makedirs(bindir)
        with open(os.path.join(bindir, "gh"), "w") as f:
            f.write(FAKE_GH)
        os.chmod(os.path.join(bindir, "gh"), 0o755)
        kube = os.path.join(tmp, "kube")
        os.makedirs(kube)
        fake = os.path.join(tmp, "fake-kubectl.py")
        with open(fake, "w") as f:
            f.write(FAKE_KUBECTL)
        results = os.path.join(tmp, "results")
        os.makedirs(results)
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ.get("PATH", ""), DRY_RUN="1", SUBMITTER="dry-render",
                   RESULTS_DIR=results, FAKE_KUBE_DIR=kube, FAKE_GH_LOG=os.path.join(tmp, "gh.log"),
                   TNB_KUBECTL="%s -S %s" % (sys.executable, fake), TMPDIR=tmp)
        env.pop("TNB_POD_DEADLINE", None)

        def dry(*args, **more):
            r = subprocess.run([bash, SCRIPT] + list(args), env=dict(env, **more), capture_output=True, text=True, timeout=120)
            rows = re.findall(r"^dry render: suite (\S+)  shards (\d+)  parallel (\d+) = (\d+) round\(s\)  "
                              r"deadline=(\d+)s pod_deadline=(\d+)s  -> (\S+)$", r.stdout, re.M)
            return r, [(int(p), int(rounds), int(d), int(pd), path) for _, _, p, rounds, d, pd, path in rows]

        r, rows = dry("main", "sims", "6")
        check(tag + "dry render sims 6: pod 12600 s; Job 12900 / 25800 / 38700 s at parallelism 6 / 3 / 2",
              r.returncode == 0 and [row[:4] for row in rows] == [(6, 1, 12900, 12600), (3, 2, 25800, 12600), (2, 3, 38700, 12600)])
        check(tag + "dry render: three rounds of 12600 s fit the Job deadline at parallelism 2",
              bool(rows) and rows[-1][2] >= 3 * 12600)
        ok = bool(rows)
        for par, _, deadline, pod_deadline, path in rows:
            text = open(path).read()
            body = "".join(line + "\n" for line in text.split("\n") if not line.lstrip().startswith("#"))
            ok = ok and ("\n  activeDeadlineSeconds: %d\n" % deadline) in text \
                and ("\n      activeDeadlineSeconds: %d\n" % pod_deadline) in text \
                and ("\n  parallelism: %d\n" % par) in text and "__" not in body \
                and 'ci.cberg.home/ref: "%s"' % SHA in text
            if par == 3:
                rendered = text
        check(tag + "dry render: the rendered Jobs carry both deadlines and no placeholder", ok)
        check(tag + "dry render: says that nothing was created", "DRY_RUN=1: no Job was created" in r.stdout)
        r, rows = dry("main", "sims", "8")
        check(tag + "dry render sims 8: Job 25800 / 38700 / 51600 s",
              [row[:3] for row in rows] == [(6, 2, 25800), (3, 3, 38700), (2, 4, 51600)])
        r, rows = dry("main", "unit")
        check(tag + "dry render unit: 5400 s for both, as before", [row[:4] for row in rows] == [(1, 1, 5400, 5400)])
        r, rows = dry("main", "unit", TNB_POD_DEADLINE="60")
        check(tag + "dry render unit, TNB_POD_DEADLINE=60: pod 60 s, Job 5400 s", [row[:4] for row in rows] == [(1, 1, 5400, 60)])
        r, rows = dry("main", "sims", TNB_POD_DEADLINE="2h")
        check(tag + "TNB_POD_DEADLINE must be whole seconds (exit 2)", r.returncode == 2 and rows == [])
        check(tag + "dry render: no kubectl call, no results folder, gh only read",
              not os.path.exists(os.path.join(kube, "calls.log")) and os.listdir(results) == []
              and all(line.startswith("api repos/") and " -f " not in line and "-X" not in line
                      for line in open(os.path.join(tmp, "gh.log")).read().splitlines()))
    return rendered


bashes = []
for candidate in ("/bin/bash", "/opt/homebrew/bin/bash", "/usr/local/bin/bash", shutil.which("bash")):
    if candidate and os.path.exists(candidate) and os.path.realpath(candidate) not in [os.path.realpath(b) for b in bashes]:
        bashes.append(candidate)
check("a bash to run the script with", bool(bashes))
seen_versions = []
for bash in bashes:
    version = subprocess.run([bash, "-c", "echo $BASH_VERSION"], capture_output=True, text=True).stdout.strip()
    if version in seen_versions:
        continue
    seen_versions.append(version)
    tag = "[bash %s] " % version.split("(")[0]
    check(tag + "bash -n", subprocess.run([bash, "-n", SCRIPT]).returncode == 0)
    k_usage(bash, tag)
    job_yaml = l_dry_render(bash, tag)
    a_normal_job(bash, tag)
    b_dead_pods(bash, tag)
    if job_yaml:
        c_job_deadline(bash, tag, job_yaml)
    else:
        check(tag + "job deadline: needs the dry render", False)
    c2_job_deadline_full_time(bash, tag)
    c3_after_job_deadline(bash, tag)
    d_job_gone(bash, tag)
    e_transient_reads(bash, tag)
    f_pod_gone(bash, tag)
    g_odd_endings(bash, tag)
    h_stopped_and_reattached(bash, tag, signal.SIGTERM, 143)
    i_closed_stdout(bash, tag)
    j_give_up(bash, tag)

print("%d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
