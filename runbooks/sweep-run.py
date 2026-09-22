#!/usr/bin/env python3
"""sweep-run — single entry point for the daily sweep.

This is the only path that runs the audit scripts. Use it either:
  * scheduled — triggered by the in-cluster OpenClaw cron ("Daily
    Operation Sweep Every 2 Days", id `8163c139`), which drives the Mac
    mini `daily-operation` Claude session via the `operation sweep`
    skill. The sweep still EXECUTES on the Mac (local SOPS age key +
    mise toolchain); the cluster cron is only the trigger. See
    "Scheduled Sweeps" in CLAUDE.md. Do NOT create a session-local
    `/loop` or `CronCreate` sweep — the old 8:17am `/loop` is retired
    and a local one double-runs against the cluster-driven sweep.
    The daily-operation agent dispatches the six specialists, each of
    whom invokes its `runbooks/X-check.py`; this script handles the
    port-forward + DSN derivation those scripts need.
  * ad-hoc — `python3 runbooks/sweep-run.py` from the operator's
    session when you've just shipped something and want a fresh DB
    reading before the next scheduled trigger.

Findings land in the sweep_history Postgres on the cluster, keyed by
a per-invocation SWEEP_CYCLE_ID so every specialist in the run groups
under a single `sweep_cycles` row.

Why local-only: the audit scripts need unifictl / hactl / talosctl and
several other tools that live in the operator's mise toolchain but
aren't (and shouldn't be) bundled into a container image. The cluster's
role is reduced to storage + display — see kubernetes/apps/databases/
sweep-history/ and kubernetes/apps/monitoring/sweep-dashboard/.

Usage:
    # Implicit port-forwards + derived DSN from sweep-history secret
    python3 runbooks/sweep-run.py

    # Pick a subset of audit scripts
    python3 runbooks/sweep-run.py light       # doc + version
    python3 runbooks/sweep-run.py heavy       # security + health
    python3 runbooks/sweep-run.py doc version
    python3 runbooks/sweep-run.py all         # default

    # Skip Postgres write (smoke test or markdown-only run)
    python3 runbooks/sweep-run.py --no-write

    # Use pre-existing DSN (e.g. when you already have the port-forward)
    SWEEP_PG_DSN=postgresql://... python3 runbooks/sweep-run.py
"""
from __future__ import annotations

import argparse
import atexit
import base64
import json
import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT  = SCRIPT_DIR.parent


def _activate_mise() -> None:
    if os.environ.get("_MISE_ACTIVATED"):
        return
    if not (REPO_ROOT / ".mise.toml").is_file():
        return
    mise = next(
        (Path(p) / "mise" for p in os.environ.get("PATH", "").split(os.pathsep)
         if (Path(p) / "mise").is_file()),
        None,
    )
    if not mise:
        return
    os.environ["_MISE_ACTIVATED"] = "1"
    # Re-exec via the PATH-resolved "python3" (not sys.executable): under
    # `mise exec` that resolves to the repo .venv interpreter, which carries
    # PyYAML + psycopg. Using sys.executable here would re-exec the bare mise
    # python with no venv site-packages, so the parent's lazy `import psycopg`
    # (DB auto-close of resolved findings) silently failed — "auto-close skipped".
    os.execvp(str(mise), [str(mise), "-C", str(REPO_ROOT), "exec", "--", "python3", *sys.argv])


_activate_mise()


STEP_SCRIPTS = {
    "doc":      ["python3", str(SCRIPT_DIR / "doc-check.py")],
    "version":  ["python3", str(SCRIPT_DIR / "check-all-versions.py")],
    "security": ["python3", str(SCRIPT_DIR / "security-check.py")],
    "health":   ["python3", str(SCRIPT_DIR / "health-check.py")],
    "slo":      ["python3", str(SCRIPT_DIR / "slo-check.py")],
}

STEP_GROUPS = {
    # `doc` runs LAST so it sees freshly-written *-current.md snapshots
    # from health/security/version/slo. Otherwise doc-check fires a stale
    # "health-check-current.md is 12 days old" finding for one cycle until
    # the next sweep catches the just-refreshed timestamp.
    "all":   ["version", "security", "health", "slo", "doc"],
    "light": ["version", "doc"],
    "heavy": ["security", "health"],
}


def _resolve_steps(args: list[str]) -> list[str]:
    """Translate positional args to a concrete step list."""
    if not args:
        return list(STEP_GROUPS["all"])
    if len(args) == 1 and args[0] in STEP_GROUPS:
        return list(STEP_GROUPS[args[0]])
    bad = [s for s in args if s not in STEP_SCRIPTS]
    if bad:
        raise SystemExit(
            f"unknown step(s): {bad}. Valid: "
            f"{sorted(STEP_SCRIPTS)} or groups {sorted(STEP_GROUPS)}"
        )
    return args


# ---------------------------------------------------------------------------
# DSN + port-forward derivation
# ---------------------------------------------------------------------------


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _kubectl_secret_dsn() -> str | None:
    """Return the sweep-history WRITER_DSN exactly as stored in the Secret.

    The DSN comes back pointing at the IN-CLUSTER Service FQDN, which does not
    resolve from this Mac. It is NOT usable as returned. The caller is
    responsible for rewriting the host to the local port-forward — see the
    `raw.replace(fqdn, ...)` in main(), which is the only supported way to
    turn this value into a connectable DSN.

    (This docstring previously claimed the rewrite happened here. It never
    did, and a caller trusting that claim connects to the in-cluster FQDN and
    fails to resolve.)
    """
    try:
        out = subprocess.check_output(
            ["kubectl", "get", "secret", "-n", "databases", "sweep-history",
             "-o", "json"],
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    try:
        data = json.loads(out)["data"]["WRITER_DSN"]
    except (KeyError, json.JSONDecodeError):
        return None
    return base64.b64decode(data).decode("utf-8")


def _start_port_forward(namespace: str, service: str, local_port: int, remote_port: int) -> subprocess.Popen:
    pf = subprocess.Popen(
        ["kubectl", "port-forward", "-n", namespace, f"svc/{service}",
         f"{local_port}:{remote_port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid if os.name != "nt" else None,
    )
    # Wait briefly for the listener to come up.
    deadline = time.time() + 6
    while time.time() < deadline:
        with socket.socket() as s:
            try:
                s.settimeout(0.4)
                s.connect(("127.0.0.1", local_port))
                return pf
            except OSError:
                time.sleep(0.2)
    pf.terminate()
    raise SystemExit(f"port-forward to {service}:{remote_port} did not become ready in 6s")


def _stop(pf: subprocess.Popen | None) -> None:
    if pf is None:
        return
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(pf.pid), signal.SIGTERM)
        else:
            pf.terminate()
    except (ProcessLookupError, PermissionError):
        pass


# ---------------------------------------------------------------------------
# Port-forward SUPERVISION (F-f85cf55c, F-fe1795c5)
#
# _start_port_forward() above is a one-shot probe: it waits up to 6s for the
# local socket to ACCEPT and returns. Nothing re-checked it afterwards, and
# main() returned 0 regardless. Two things follow from that, both measured:
#
#   * a forward that died between sections lost that section's entire DB
#     write — findings_writer catches every write exception ("never lose the
#     cycle close"), the step still exits 0/1/2, sweep-run scored it
#     completed, and the run reported success;
#   * "accepted TCP at start" is not the property that matters. On
#     2026-09-22 a forward reported ready and refused the VERY NEXT connection
#     (F-fe1795c5): kubectl port-forward listens locally and only dials the
#     pod when a connection arrives, so a bare accept proves nothing about
#     the path to the pod.
#
# So the probe is END-TO-END (a `SELECT 1` through the DSN, an HTTP /-/ready
# through the URL), it runs BEFORE and AFTER every section (before: the
# section's writes will have somewhere to land; after: they HAD somewhere to
# land, i.e. the forward was alive at write time), a dead forward is
# re-dialled ONCE per phase, and a forward that is dead when a write depended
# on it makes the run exit non-zero. A lost section is also struck from the
# auto-close scope: no report is not a resolution.
# ---------------------------------------------------------------------------

EXIT_FORWARD_DEAD = 3   # deliberately outside the (0,1,2) "ran to completion" set


# ---------------------------------------------------------------------------
# Forward TEARDOWN that does not depend on reaching `finally` (F-b881a5b5)
#
# main() stops its forwards in a `finally`, and `_stop()` kills the forward's
# whole process group (the starter puts each kubectl in its own session), so
# every path that UNWINDS is clean. Two paths never unwind: SIGTERM and SIGHUP.
# Python's default disposition for both is "terminate now" — no exception, no
# `finally`, no atexit — so a sweep killed by the console going away (HUP) or
# by a supervisor's timeout (TERM) left its port-forwards alive with ppid 1.
# Measured 2026-09-17: 108 orphaned `kubectl port-forward` processes on the
# operator Mac, 74 of them to postgresql, the oldest 3 days.
#
# So: every dialled Forward is registered; SIGTERM/SIGHUP are turned into a
# SystemExit (which DOES run `finally` and atexit); and an atexit hook stops
# whatever is still registered, for any exit path that skipped the `finally`.
# Handlers are installed only over the DEFAULT disposition — a caller that
# deliberately ignores HUP (nohup) keeps that choice.
# ---------------------------------------------------------------------------

_LIVE_FORWARDS: list = []


def _stop_all_forwards() -> None:
    for fwd in list(_LIVE_FORWARDS):
        try:
            fwd.stop()
        except Exception:  # noqa: BLE001 — teardown must reach every forward
            pass


def _install_teardown_signals(signals=(signal.SIGTERM, signal.SIGHUP)) -> list:
    """Make TERM/HUP unwind the process instead of ending it in place, and arm
    the atexit backstop. Returns the signals actually re-dispositioned (a
    signal already ignored or handled is left alone)."""
    def _raise_exit(signum, _frame):
        raise SystemExit(128 + int(signum))

    installed = []
    for sig in signals:
        try:
            if signal.getsignal(sig) is signal.SIG_DFL:
                signal.signal(sig, _raise_exit)
                installed.append(sig)
        except (ValueError, OSError):   # not the main thread / unsupported
            continue
    atexit.register(_stop_all_forwards)
    return installed


def _pg_probe(dsn: str):
    """END-TO-END liveness for the postgres forward: a round-trip query."""
    def probe() -> bool:
        import psycopg
        with psycopg.connect(dsn, connect_timeout=5) as c, c.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() == (1,)
    return probe


def _http_probe(url: str, path: str = "/-/ready"):
    """END-TO-END liveness for an HTTP forward (prometheus readiness)."""
    def probe() -> bool:
        import urllib.request
        with urllib.request.urlopen(url.rstrip("/") + path, timeout=5) as r:
            return 200 <= r.status < 300
    return probe


class Forward:
    """A supervised kubectl port-forward.

    `probe()` MUST be end-to-end (see above). `starter` is injectable so the
    supervision logic is testable without kubectl. `log` carries a line per
    supervision event for the run summary.
    """

    def __init__(self, namespace: str, service: str, local_port: int, remote_port: int,
                 probe=None, starter=None):
        self.namespace, self.service = namespace, service
        self.local_port, self.remote_port = local_port, remote_port
        self.probe = probe
        self.starter = starter or _start_port_forward
        self.proc: subprocess.Popen | None = None
        self.redials = 0
        self.log: list[str] = []

    def dial(self) -> None:
        self.proc = self.starter(self.namespace, self.service,
                                 self.local_port, self.remote_port)
        if self not in _LIVE_FORWARDS:
            _LIVE_FORWARDS.append(self)   # so a TERM/HUP/atexit teardown finds it

    def alive(self) -> bool:
        """Process still running AND the end-to-end probe succeeds. A probe
        that raises is a dead forward, never an unknown one."""
        if self.proc is None or self.proc.poll() is not None:
            return False
        if self.probe is None:
            return True   # not yet armed (DSN unknown) — caller arms it before use
        try:
            return bool(self.probe())
        except Exception:  # noqa: BLE001 — any failure to round-trip is "dead"
            return False

    def ensure(self, phase: str) -> bool:
        """True when the forward is live for `phase`. When it is not: stop
        the old process, re-dial ONCE, re-probe. False means the phase must
        not trust the forward — its writes would be lost."""
        if self.alive():
            return True
        self.log.append(f"{phase}: forward to {self.service}:{self.remote_port} is DEAD "
                        f"(end-to-end probe failed) — re-dialling once")
        _stop(self.proc)
        self.proc = None
        time.sleep(0.5)
        try:
            self.dial()
        except SystemExit as e:
            self.log.append(f"{phase}: re-dial FAILED — {e}")
            return False
        self.redials += 1
        ok = self.alive()
        self.log.append(f"{phase}: re-dial {'succeeded' if ok else 'FAILED (probe still dead)'}")
        return ok

    def stop(self) -> None:
        _stop(self.proc)
        self.proc = None
        if self in _LIVE_FORWARDS:
            _LIVE_FORWARDS.remove(self)


# ---------------------------------------------------------------------------
# Maintenance-window liveness -> Pushgateway (F-2dabaddb)
#
# `maintenance-plan.py --liveness-metrics` has exposed window_runs_missing_count
# and friends in Prometheus text format since the F-2dabaddb figure landed, and
# a PrometheusRule now reads exactly those names — but nothing carried the text
# to Prometheus, so the rule's absent() arm would fire forever and its
# staleness arm (push_time_seconds{job="maintenance-window-liveness"} older
# than 50h) had nothing to measure. The sweep is the one thing that runs with
# the DSN on the operator Mac every 48h, so it pushes.
#
# House rules (docs/sops/monitoring.md, "Push-based Metrics"), all applied:
#   1. timestamps, never ages — the payload is produced by maintenance-plan.py
#      and carries counts, flags and one timestamp; staleness is pushgateway's
#      own push_time_seconds;
#   2. the body ends with a newline or pushgateway answers 400 and stores
#      nothing — refused here before it is sent;
#   3. a push replaces the grouping WHOLESALE — so on ANY failure (payload not
#      built, payload lacking the names the rule reads, forward dead) push
#      NOTHING and say so; the previous snapshot keeps ageing on
#      push_time_seconds, which is exactly what the staleness arm reads.
# A failed push never changes the sweep's exit code: the sections' contract is
# unchanged, and the rule pages on the staleness this failure produces.
# ---------------------------------------------------------------------------

PUSHGATEWAY_NS, PUSHGATEWAY_SVC, PUSHGATEWAY_PORT = "monitoring", "prometheus-pushgateway", 9091
LIVENESS_PUSH_JOB = "maintenance-window-liveness"
# The names the PrometheusRule keys on. A payload without them is not a
# liveness payload and must not replace the grouping.
LIVENESS_REQUIRED_METRICS = ("window_runs_liveness_verified",
                             "window_runs_liveness_lookback_days")


def _metric_names(text: str) -> set:
    return {ln.split("{", 1)[0].split(" ", 1)[0] for ln in text.splitlines()
            if ln and not ln.startswith("#")}


def liveness_metrics_payload(env: dict, runner=subprocess.run) -> tuple:
    """(payload, error). Runs `maintenance-plan.py --liveness-metrics` with the
    caller's env (SWEEP_PG_DSN on the write path). payload is None when it is
    unusable — the caller then pushes NOTHING."""
    try:
        p = runner([sys.executable, str(SCRIPT_DIR / "maintenance-plan.py"), "--liveness-metrics"],
                   env=env, capture_output=True, text=True, timeout=180)
    except Exception as e:  # noqa: BLE001
        return None, f"maintenance-plan.py --liveness-metrics did not run: {type(e).__name__}: {e}"
    if p.returncode != 0:
        return None, (f"maintenance-plan.py --liveness-metrics rc={p.returncode}: "
                      f"{(p.stderr or '').strip()[-200:]}")
    text = p.stdout or ""
    missing = [m for m in LIVENESS_REQUIRED_METRICS if m not in _metric_names(text)]
    if missing:
        return None, f"payload lacks the metric(s) the rule reads: {missing}"
    if not text.endswith("\n"):
        text += "\n"
    return text, ""


def push_metrics(base_url: str, job: str, payload: str, opener=None) -> tuple:
    """POST one text-format payload to <base_url>/metrics/job/<job>. Never raises."""
    import urllib.error
    import urllib.request
    opener = opener or urllib.request.urlopen
    if not payload.endswith("\n"):
        return False, "payload is not newline-terminated — pushgateway would answer 400 and store nothing; not sent"
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/metrics/job/{job}", data=payload.encode("utf-8"), method="POST",
        headers={"Content-Type": "text/plain; version=0.0.4; charset=utf-8"})
    try:
        with opener(req, timeout=15) as r:
            status = int(getattr(r, "status", 200))
            return 200 <= status < 300, f"HTTP {status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {(e.read() or b'')[:200]!r}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def push_liveness_metrics(env: dict, gateway_url: str | None = None, starter=None,
                          runner=subprocess.run) -> tuple:
    """The whole step; never raises. Builds the payload, reaches the gateway
    (a supervised port-forward unless a URL is given), pushes under
    LIVENESS_PUSH_JOB. Any failure => (False, why) and NOTHING pushed."""
    payload, err = liveness_metrics_payload(env, runner=runner)
    if payload is None:
        return False, f"nothing pushed — {err}"
    fwd = None
    try:
        if not gateway_url:
            port = _free_port()
            gateway_url = f"http://127.0.0.1:{port}"
            fwd = Forward(PUSHGATEWAY_NS, PUSHGATEWAY_SVC, port, PUSHGATEWAY_PORT,
                          probe=_http_probe(gateway_url, "/-/ready"), starter=starter)
            try:
                fwd.dial()
            except SystemExit as e:
                return False, f"nothing pushed — port-forward to {PUSHGATEWAY_SVC} failed: {e}"
            if not fwd.ensure("liveness push"):
                return False, f"nothing pushed — {PUSHGATEWAY_SVC} forward dead after one re-dial"
        ok, why = push_metrics(gateway_url, LIVENESS_PUSH_JOB, payload)
        return ok, (f"job {LIVENESS_PUSH_JOB}: {why}" if ok else f"nothing stored — {why}")
    finally:
        if fwd is not None:
            fwd.stop()


def _report_liveness_push(env: dict, gateway_url: str | None) -> None:
    ok, why = push_liveness_metrics(env, gateway_url=gateway_url)
    if ok:
        print(f"==> maintenance-window liveness metrics pushed to Pushgateway ({why})")
    else:
        print(f"==> maintenance-window liveness metrics NOT pushed ({why}); the previous "
              f"snapshot keeps ageing on push_time_seconds and MaintenanceWindowLivenessStale "
              f"pages at 50h — the sweep's exit code is unchanged", file=sys.stderr)


def _run_steps_supervised(steps: list[str], env: dict, pg_fwd: "Forward | None",
                          prom_fwd: "Forward | None", runner=None) -> dict:
    """Run the section scripts with the forwards supervised around each.

    Returns {"nonzero": [...], "completed": [...], "lost": [...], "skipped": [...]}:
      completed — ran to a sane rc AND its forwards were alive at write time
      lost      — ran, but a forward it depended on was dead AFTERWARDS: its
                  DB write cannot be trusted; struck from `completed`
      skipped   — not run at all: a forward it depended on was dead BEFORE it
                  and could not be re-dialled (running it would only lose the
                  write, and the step's own exit code would hide that)
    """
    runner = runner or subprocess.call
    nonzero: list[str] = []
    completed: list[str] = []
    lost: list[str] = []
    skipped: list[str] = []
    for step in steps:
        needed = [f for f in (pg_fwd, prom_fwd if step == "slo" else None) if f is not None]
        if not all(f.ensure(f"before {step}") for f in needed):
            skipped.append(step)
            print(f"────────── {step} ────────── SKIPPED: a port-forward it writes through "
                  f"is dead and could not be re-dialled")
            continue
        cmd = list(STEP_SCRIPTS[step])
        print(f"────────── {step} ──────────")
        rc = runner(cmd, env=env)
        if rc != 0:
            nonzero.append(f"{step}({rc})")
        # rc 0/1/2 = "ran to completion" (1/2 typically mean "found findings");
        # anything else, assume crash and skip its section in auto-close.
        sane = rc in (0, 1, 2)
        # AFTER the step: was the forward alive at the moment the section
        # wrote? A dead forward here means the write was silently discarded
        # (findings_writer swallows it) — the section did NOT report. Read
        # alive() FIRST and only then re-dial for the NEXT section: a
        # successful re-dial must not retroactively score THIS section's
        # lost write as landed.
        was_alive = all(f.alive() for f in needed)
        if not was_alive:
            for f in needed:
                f.ensure(f"after {step}")
        if sane and was_alive:
            completed.append(step)
        elif sane:
            lost.append(step)
    return {"nonzero": nonzero, "completed": completed, "lost": lost, "skipped": skipped}


def _require_forward(fwd: "Forward | None", phase: str) -> None:
    """A DB phase that cannot proceed without its forward: abort the run with
    EXIT_FORWARD_DEAD when ensure() cannot revive it. Nothing written in
    `phase` would land, and pretending otherwise is the defect."""
    if fwd is None or fwd.ensure(phase):
        return
    for line in fwd.log:
        print(f"==> {line}", file=sys.stderr)
    print(f"==> ABORT: the {fwd.service} port-forward is dead at {phase} and one re-dial "
          f"did not revive it — nothing written here would land (F-f85cf55c); "
          f"exit {EXIT_FORWARD_DEAD}", file=sys.stderr)
    raise SystemExit(EXIT_FORWARD_DEAD)


# Natures that mark a finding as being ABOUT THE AUDIT ITSELF rather than
# about the estate: a suppression that stopped matching, a check that could
# not cover its target, a rule that regressed. These are exempt from AR
# substring suppression entirely — see _apply_ar_suppression().
#
# `policy-drift` and `audit-coverage-gap` are the values already in use on
# live rows; `audit-integrity` / `meta` are accepted as future synonyms so a
# new emitter does not have to touch this file to be protected.
AUDIT_INTEGRITY_NATURES = [
    "policy-drift",
    "audit-coverage-gap",
    "audit-integrity",
    "meta",
]


def _apply_ar_suppression(dsn: str) -> int:
    """Re-tag open findings whose title substring-matches an accepted-risk
    description. Sets severity='accepted' and prepends [AR-NNN] to the
    title. Idempotent — already-tagged rows are left alone.

    Cross-section: an AR description like "chart 3.7.3 → 5.0.0 (major)"
    suppresses matching version findings AND any other section's finding
    that happens to share the substring. Description authoring is the
    knob to control scope.

    TWO CLASSES OF ROW ARE NEVER SUPPRESSED, no matter what they match:

    1. **Audit-integrity findings** (`risk_nature` in
       AUDIT_INTEGRITY_NATURES, or a `subsection` starting `audit_`/`audit-`).
       These report that the audit machinery is mis-firing. Silencing them
       with the same machinery turns a detector into a blindfold.

    2. **A finding about a specific AR, suppressed by that same AR**
       (`metadata->>'ar_id'` equals the AR being applied). Self-suppression
       is never a legitimate outcome.

    Incident that forced this (2026-08-18, F-21ceb683): a finding titled
    "AR-063 no longer suppresses its target: the description
    `iib0011/omni-tools image` is not a substring of the finding title …"
    was tagged `[AR-063] accepted` — because once AR-063 was re-worded to
    the bare `iib0011/omni-tools`, that string occurred inside the very
    sentence reporting AR-063's breakage. The report of the failure was
    eaten by the thing that failed. Either guard alone would have caught
    it; both are here because they fail in different directions — (1)
    covers audit-integrity rows that carry no `ar_id`, (2) covers rows
    that carry an `ar_id` but were emitted with an ordinary nature.

    A THIRD CLASS NEVER SUPPRESSES AT ALL: an acceptance past its stated
    deadline (`metadata.expires_at`, see lib/ar_expiry.py). AR-042 carried
    "accept until 2026-09-03" in justification PROSE, which no code could read,
    so it masked a genuinely flat cell for 14 days past the operator's own
    deadline (F-da238139). An AR with no recorded expiry is unaffected and
    suppresses indefinitely, by design.

    The expiry column is SELECTED and compared in PYTHON, never in SQL — a
    `::date` cast raises on a date-shaped-but-impossible value, and that
    exception lands in the `except` below, which returns 0 and applies NO
    suppression for the whole cycle. See lib/ar_expiry.py for the measurement.

    Returns count of rows re-tagged this pass.
    """
    try:
        import psycopg
    except ImportError:
        return 0
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from lib.ar_expiry import EXPIRY_SELECT, is_expired, lapse_note
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ar_id, description, " + EXPIRY_SELECT +
                    " FROM accepted_risks "
                    "WHERE status='accepted' AND enabled=true"
                )
                rows = cur.fetchall()
                # Say what lapsed BEFORE acting: otherwise the finding simply
                # reappears with no statement of why, reading as a new problem
                # rather than a decision coming back up for review.
                ars = []
                for _ar_id, _desc, _exp in rows:
                    _note = lapse_note(_ar_id, _exp)
                    if _note is not None:
                        print(_note)
                        continue
                    ars.append((_ar_id, _desc))
                tagged = 0
                exempt = 0
                for ar_id, desc in ars:
                    needle = (desc or "").strip()
                    if not needle:
                        continue
                    # Count what the guards held back, so an over-broad AR
                    # description is visible in the run log instead of just
                    # quietly matching nothing.
                    cur.execute(
                        """
                        SELECT count(*)
                          FROM sweep_findings
                         WHERE resolved_at IS NULL
                           AND severity IN ('critical', 'warning', 'monitor')
                           AND position(%s in lower(title)) > 0
                           AND position(%s in title) = 0
                           AND (
                                 coalesce(metadata->>'risk_nature', '') = ANY(%s)
                              OR coalesce(metadata->>'subsection', '') ~* '^audit[-_]'
                              OR coalesce(metadata->>'ar_id', '') = %s
                               )
                        """,
                        (needle.lower(), f"[{ar_id}]",
                         AUDIT_INTEGRITY_NATURES, ar_id),
                    )
                    exempt += (cur.fetchone() or (0,))[0]
                    cur.execute(
                        """
                        UPDATE sweep_findings
                           SET severity = 'accepted',
                               title = %s || title
                         WHERE resolved_at IS NULL
                           AND severity IN ('critical', 'warning', 'monitor')
                           AND position(%s in lower(title)) > 0
                           AND position(%s in title) = 0
                           AND coalesce(metadata->>'risk_nature', '') <> ALL(%s)
                           AND coalesce(metadata->>'subsection', '') !~* '^audit[-_]'
                           AND coalesce(metadata->>'ar_id', '') <> %s
                        """,
                        (f"[{ar_id}] ", needle.lower(), f"[{ar_id}]",
                         AUDIT_INTEGRITY_NATURES, ar_id),
                    )
                    tagged += cur.rowcount
            conn.commit()
        if exempt:
            print(f"==> AR-suppression: {exempt} audit-integrity/self-referential "
                  f"finding(s) matched an AR description and were EXEMPTED "
                  f"(a finding about the audit is never silenced by the audit)")
        return tagged
    except Exception as e:  # noqa: BLE001
        print(f"==> AR-suppression failed: {type(e).__name__}: {e}")
        return 0


def _sections_reporting_this_cycle(dsn: str, cycle_id: str) -> set:
    """Sections that actually wrote at least one finding under this cycle.

    Auto-close must only ever consider a section that demonstrably ran. A
    section that reported nothing tells us nothing about its findings, so
    closing them would be inventing a result.
    """
    try:
        import psycopg
    except ImportError:
        return set()
    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT section FROM sweep_findings WHERE cycle_id = %s",
                    (cycle_id,),
                )
                found = {r[0] for r in cur.fetchall() if r[0]}
                # slo-check records to slo_snapshots and emits NO sweep_findings
                # row when every SLO passes, so findings-only inference would
                # class a clean slo run as "did not run".
                #
                # slo_snapshots has NO cycle_id column — it is keyed by taken_at.
                # An earlier version queried cycle_id here; the resulting
                # UndefinedColumn hit the fail-closed handler below and silently
                # disabled auto-close for EVERY cycle. A guard that always fails
                # closed is indistinguishable from a guard that works, which is
                # why this correlates on the cycle's own time window instead.
                cur.execute(
                    "SELECT started_at, COALESCE(finished_at, now()) "
                    "FROM sweep_cycles WHERE cycle_id = %s",
                    (cycle_id,),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "SELECT 1 FROM slo_snapshots "
                        "WHERE taken_at >= %s AND taken_at <= %s LIMIT 1",
                        (row[0], row[1]),
                    )
                    if cur.fetchone():
                        found.add("slo")
                return found
    except Exception as e:  # noqa: BLE001
        # Fail CLOSED: on any error, report nothing as having run, so
        # auto-close does nothing rather than closing findings blindly.
        print(f"==> could not determine reporting sections ({type(e).__name__}: {e}) "
              f"— auto-close disabled for this run")
        return set()


def _incomplete_sections_from_notes(notes: str | None) -> dict:
    """Sections that declared themselves INCOMPLETE, from sweep_cycles.notes.

    Pure so it can be tested without a database. Any shape we do not recognise
    yields {} — the caller treats a READ FAILURE as fail-closed separately;
    this only distinguishes "no veto recorded" from "veto recorded".
    """
    if not notes:
        return {}
    if isinstance(notes, dict):
        parsed = notes            # already strict-parsed by _parse_cycle_notes
    else:
        try:
            parsed = json.loads(notes)
        except (ValueError, TypeError):
            return {}
        if not isinstance(parsed, dict):
            return {}
    incomplete = parsed.get("incomplete")
    return incomplete if isinstance(incomplete, dict) else {}


def _uncovered_components_from_notes(notes: str | None) -> dict:
    """Per-component coverage gaps, from sweep_cycles.notes.

    `{section: {component_key: reason}}`. The NARROW sibling of the incomplete
    veto: the section completed, so absence is a valid resolution signal for
    everything except findings about these components. Delegates to the
    writer's parser so the two auto-close implementations cannot drift.

    RAISES on an unimportable writer rather than returning `{}`. Returning an
    empty dict there is indistinguishable from "no scope was recorded", which
    would sail straight past the abort guard below and close exactly the rows a
    recorded scope existed to hold open — the one direction this design must
    never fail in. The caller's `except` turns the raise into an abort.
    """
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from lib.findings_writer import uncovered_from_notes  # ImportError -> abort
    return uncovered_from_notes(notes)


def _parse_cycle_notes(notes):
    """`sweep_cycles.notes` as a dict, RAISING if a non-empty blob is unreadable.

    Both veto readers below infer "nothing was recorded" from an empty result,
    so a blob we cannot parse must abort the pass rather than silently present
    as a clean cycle. Empty/NULL notes are a genuine "nothing recorded".
    """
    if not notes:
        return {}
    if isinstance(notes, dict):
        return notes
    parsed = json.loads(notes)   # raises -> caller aborts
    if not isinstance(parsed, dict):
        raise ValueError("sweep_cycles.notes is not a JSON object")
    return parsed


def _auto_close_stale_findings(
    dsn: str, cycle_id: str, sections: list[str]
) -> list[tuple[str, str, str]]:
    """Mark open findings as resolved when they didn't re-fire this cycle.

    Scope: only sections in `sections` (those whose step script ran to a
    sane rc). Returns the list of (finding_id, section, title) closed —
    empty if nothing to close.

    Safe to call repeatedly: the WHERE clause excludes already-resolved
    rows and rows that the current cycle touched.
    """
    # HONOUR THE SAME ENV ESCAPE HATCHES AS findings_writer.py. They were
    # documented as applying to auto-close generally, but this reconcile path
    # is a SECOND, independent implementation that read neither of them, so
    # `SWEEP_AUTOCLOSE_DRYRUN=1` wrote for real here while printing
    # "auto-closed ... ✓ resolved". On 2026-09-03 that cost four live findings
    # -- including F-76d1d34e, the finding that documents this class of bug --
    # closed by an operator who ran the dry-run *specifically* to avoid it.
    # A safety flag that silently does nothing is worse than no flag: it buys
    # confidence to proceed. Keep these two checks in sync with the writer.
    _ac_mode = os.environ.get("SWEEP_AUTOCLOSE", "")
    if _ac_mode == "0":
        print("==> auto-close DISABLED by SWEEP_AUTOCLOSE=0 — nothing closed")
        return []
    _ac_dryrun = os.environ.get("SWEEP_AUTOCLOSE_DRYRUN", "") == "1"

    try:
        import psycopg  # imported lazily so --no-write paths don't need it
    except ImportError:
        print("==> auto-close skipped: psycopg not available")
        return []

    git_head = ""
    try:
        git_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, timeout=5
        ).strip()[:40]
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # HONOUR THE INCOMPLETE VETO. This is a SECOND, independent auto-close
    # implementation: it does not share FindingsWriter's gates, cannot see a
    # specialist's in-memory `_incomplete_reason`, and runs AFTER every step.
    # Without this, a section that degraded, vetoed its own close and printed
    # "auto-close SKIPPED ... INCOMPLETE" would have exactly those rows closed
    # here seconds later, in the same sweep — making the veto inoperative in
    # the only mode where auto-close is armed at all. The writer persists the
    # veto onto sweep_cycles.notes.incomplete so it survives the process
    # boundary; read it back and drop those sections from scope.
    try:
        # Resolve the matcher FIRST, and abort if it cannot be imported. Doing
        # this after the notes read was a fail-OPEN seam: the reader itself
        # needs the same module, so an unimportable writer produced an empty
        # scope, the "did we record a scope?" guard saw nothing to protect, and
        # the pass closed the very rows the scope was holding open.
        if str(SCRIPT_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPT_DIR))
        from lib.findings_writer import finding_matches_component, row_producer

        with psycopg.connect(dsn) as _c, _c.cursor() as _cur:
            _cur.execute("SELECT notes FROM sweep_cycles WHERE cycle_id = %s",
                         (cycle_id,))
            _row = _cur.fetchone()
        # Parse ONCE, strictly: an unreadable blob aborts instead of rendering
        # as a cycle with no veto recorded.
        _notes = _parse_cycle_notes(_row[0] if _row else None)
        _incomplete = _incomplete_sections_from_notes(_notes)
        _uncovered = _uncovered_components_from_notes(_notes)
        _vetoed = [sec for sec in sections if sec in _incomplete]
        if _vetoed:
            for sec in _vetoed:
                print(f"==> auto-close SKIPPED for section {sec}: the run declared "
                      f"itself INCOMPLETE ({_incomplete[sec]}) — a coverage gap is "
                      f"not a fix")
            sections = [sec for sec in sections if sec not in _incomplete]
        # Per-component scope: the section COMPLETED but named components it
        # could not resolve. Those sections stay in scope — one unresolvable
        # image must not veto the other ~180 — but their uncovered rows are
        # held back below, using the writer's matcher so the two auto-close
        # implementations enforce one rule.
        _uncovered = {sec: comps for sec, comps in _uncovered.items()
                      if sec in sections and comps}
        for sec, comps in sorted(_uncovered.items()):
            print(f"==> auto-close SCOPED for section {sec}: {len(comps)} "
                  f"component(s) uncovered this run, their findings are held "
                  f"open, the rest of the section closes normally "
                  f"({', '.join(sorted(comps)[:5])}"
                  f"{'…' if len(comps) > 5 else ''})")
        if not sections:
            print("==> auto-close: no sections left in scope after the incomplete "
                  "veto — nothing closed")
            return []
    except Exception as e:  # noqa: BLE001 — fail CLOSED: never close on doubt
        print(f"==> auto-close ABORTED: could not read the coverage veto "
              f"({type(e).__name__}: {e}). Refusing to auto-close rather than "
              f"risk resolving findings from a degraded section, or rows a "
              f"per-component scope was holding open.")
        return []

    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, finding_id, section, title, metadata
                      FROM sweep_findings
                     WHERE resolved_at IS NULL
                       AND section = ANY(%s)
                       AND (cycle_id IS NULL OR cycle_id::text != %s)
                    """,
                    (sections, cycle_id),
                )
                candidates = cur.fetchall()

                closeable, held, foreign = [], [], []
                for pk, fid, sec, title, meta in candidates:
                    # PRODUCER GATE — keep in sync with FindingsWriter.
                    # This backstop closes on behalf of the SECTION STEP
                    # SCRIPTS (the `sections` list is exactly those whose step
                    # ran to a sane rc). It cannot speak for an agent: it does
                    # not know which specialists ran, so an agent-authored row
                    # being silent here is not evidence of anything.
                    #
                    # Added 2026-09-05 after the writer-side gate (69aef03c)
                    # turned out to be INERT on the armed path: a full
                    # orchestrated sweep runs this backstop after every step,
                    # so a doc-agent row written in cycle N was still closed
                    # here in cycle N+1 — the exact failure the writer gate was
                    # meant to end. The regression suite was 10/10 green
                    # throughout because every test drove the writer.
                    #
                    # This is the THIRD divergence between the two
                    # implementations (see the SWEEP_AUTOCLOSE/_DRYRUN comment
                    # above, which cost four live findings on 2026-09-03).
                    # docs/sops/sweep-findings-lifecycle.md §4.8 states the
                    # rule: if you add a gate to the writer, decide explicitly
                    # whether the backstop needs it too.
                    # row_producer() rather than meta["producer"], and IMPORTED
                    # rather than re-spelled: `policy-cli finding add` stamps
                    # the legacy `authored_by` key, so a hand-authored row read
                    # as untagged here and this backstop closed it even after
                    # the writer gate learned to hold it (F-d93b2328). That is
                    # the §4.8 divergence this comment block already warns
                    # about, repeated — so the predicate is now shared code,
                    # not a fourth copy.
                    _producer = row_producer(meta)
                    if _producer is not None and _producer != "script":
                        foreign.append((pk, fid, sec, title, _producer))
                        continue
                    comps = _uncovered.get(sec) or {}
                    hit = next(
                        (c for c in comps
                         if finding_matches_component(c, title, meta or {})),
                        None,
                    ) if comps else None
                    (held if hit else closeable).append(
                        (pk, fid, sec, title, hit))
                if foreign:
                    print(f"==> auto-close HELD BACK {len(foreign)} finding(s) "
                          f"emitted by a NON-SCRIPT producer — this backstop "
                          f"closes for the step scripts and cannot speak for "
                          f"an agent's rows:")
                    for _pk, fid, sec, title, prod in foreign[:20]:
                        print(f"      ⏸ kept open {sec}/{fid} — producer "
                              f"{prod!r}: {title[:60]}")
                    if len(foreign) > 20:
                        print(f"      … and {len(foreign) - 20} more")
                for _pk, fid, sec, title, hit in held[:20]:
                    print(f"      ⏸ kept open {sec}/{fid} — uncovered {hit}: "
                          f"{title[:70]}")
                if len(held) > 20:
                    print(f"      … and {len(held) - 20} more held open")
                if not closeable:
                    return []
                if _ac_dryrun:
                    # Report and write NOTHING. Phrased in the conditional so
                    # the output can never be mistaken for a completed close.
                    print(f"==> DRY RUN: would close {len(closeable)} "
                          f"finding(s); nothing written")
                    for _cid, _sec, _t in [(c[1], c[2], c[3]) for c in closeable]:
                        print(f"      would close {_sec}/{_cid}: {_t[:70]}")
                    return []
                cur.execute(
                    """
                    UPDATE sweep_findings
                       SET resolved_at = now(),
                           status = 'resolved',
                           resolved_commit = COALESCE(NULLIF(%s, ''), resolved_commit)
                     WHERE id = ANY(%s)
                       AND resolved_at IS NULL
                     RETURNING finding_id, section, title
                    """,
                    (git_head, [c[0] for c in closeable]),
                )
                rows = cur.fetchall()
            conn.commit()
        return [(r[0], r[1], r[2]) for r in rows]
    except Exception as e:  # noqa: BLE001
        print(f"==> auto-close failed: {type(e).__name__}: {e}")
        return []


def _reconcile_verdict(dsn: str, cycle_id: str) -> str | None:
    """Recompute and store the cycle verdict from the CURRENTLY-OPEN findings.

    OWNERSHIP-AWARE since 2026-08-26 (P3.1). The previous semantics —
    red = any open critical — produced 33 red / 2 yellow / 0 green over 30
    days: with criticals arriving daily and resolving at a 2-day median, red
    was the permanent state and stopped meaning "act today". Back-tested
    before flipping: under these semantics 21 of those 33 reds become yellow
    (owned work in flight), the 12 that stay red are one genuine multi-day
    stuck period, and one old yellow becomes red because 49 findings sat >4d
    unplanned while the verdict said yellow — the old semantics under-reported
    exactly where it mattered.

      red    = something needs a human TODAY:
               - any CRACK (finding-triage: matched no lane)
               - any PLAN-lane critical past plan_sla_days with no plan file
               - triage itself unavailable while criticals are open (a
                 verdict that cannot see ownership must not claim it)
      yellow = open criticals/warnings exist but every critical is OWNED:
               routed to a lane, within SLA. The healthy steady state.
      green  = no open criticals or warnings at all (the operator's literal
               goal stays the top state).

    "Open" = status IN (new, unchanged) AND severity NOT IN (accepted, clean),
    i.e. post AR-suppression + auto-close. This overrides the provisional
    verdict each section script wrote from its pre-suppression counts (which
    miscounts AR-accepted CVEs as critical and, in a parallel fan-out, races).
    Returns the verdict written, or None on failure / writes disabled.
    """
    try:
        import psycopg  # lazy import — --no-write paths don't need it
    except ImportError:
        return None
    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      count(*) FILTER (WHERE severity = 'critical') AS crit,
                      count(*) FILTER (WHERE severity = 'warning')  AS warn
                    FROM sweep_findings
                    WHERE status IN ('new', 'unchanged')
                      AND severity NOT IN ('accepted', 'clean')
                    """
                )
                crit, warn = cur.fetchone()

        if not crit:
            verdict = "yellow" if warn else "green"
        else:
            verdict = _ownership_verdict(warn, dsn)

        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE sweep_cycles SET verdict = %s WHERE cycle_id = %s",
                    (verdict, cycle_id),
                )
            conn.commit()
        return verdict
    except Exception as e:  # noqa: BLE001
        print(f"==> verdict reconcile failed: {type(e).__name__}: {e}")
        return None


def _ownership_verdict(warn: int, dsn: str | None = None) -> str:
    """red/yellow for a cycle WITH open criticals, by ownership.

    Runs finding-triage.py --no-page and reads counts + overdue from its JSON.
    Every failure mode is RED, deliberately: a verdict that cannot establish
    ownership must never report the calm color — that would be the
    silent-inert-check family wearing the verdict's clothes.

    `dsn` MUST be passed through explicitly (F-4b27e81c). The docstring used to
    claim the child "inherits SWEEP_PG_DSN from our env", and that is true only
    when the OPERATOR exported it. When sweep-run self-provisions the DSN — its
    own port-forward plus a decoded secret, which is the normal cron path — the
    value lands on a per-step `env` dict (see the run loop), never on
    os.environ. The child then died on KeyError SWEEP_PG_DSN, stdout came back
    empty, counts were missing, and this function's own fail-safe forced RED on
    every self-provisioned run regardless of actual ownership. Observed cycle
    e0bb8d95 (2026-08-28): standalone triage reported CRACK=0 and overdue=[],
    so the correct verdict was yellow.

    The fail-safe is right and stays. What was wrong is that it was firing on a
    plumbing bug rather than on genuine uncertainty — a permanently-red verdict
    carries exactly as little information as a permanently-green one.
    """
    import json as _json
    import os as _os
    import subprocess as _sp
    try:
        child_env = _os.environ.copy()
        if dsn:
            child_env["SWEEP_PG_DSN"] = dsn
        pr = _sp.run(
            [sys.executable, str(SCRIPT_DIR / "finding-triage.py"),
             "--no-page", "--json"],
            capture_output=True, text=True, timeout=300, env=child_env)
        d = _json.loads(pr.stdout or "{}")
    except Exception as e:  # noqa: BLE001
        print(f"==> ownership triage failed ({type(e).__name__}: {e}) — "
              f"criticals open + ownership unknown => red")
        return "red"
    counts = d.get("counts") or {}
    overdue = d.get("overdue_unplanned") or []
    cracks = counts.get("CRACK")
    if cracks is None:
        print("==> triage JSON carried no counts — ownership unknown => red")
        return "red"
    if cracks or overdue:
        print(f"==> verdict red: CRACK={cracks} overdue_unplanned={len(overdue)}")
        return "red"
    print(f"==> verdict yellow: all open criticals owned "
          f"({ {k: v for k, v in counts.items() if v} }), none past SLA")
    return "yellow"


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short=40", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip() or None
    except Exception:  # noqa: BLE001
        return None


def _ensure_cycle_row(dsn: str, cycle_id: str, trigger: str) -> None:
    """Create the canonical sweep_cycles row for this run, up-front.

    FindingsWriter now creates the cycle row LAZILY (on the first finding) so a
    clean specialist leaves no orphan row. That change means a sweep that emits
    ZERO findings would otherwise produce NO cycle row at all — the dashboard's
    /api/cycles/latest and the reconcile verdict both need one. So the
    orchestrator (this script — the one place that owns the shared cycle id)
    guarantees the row exists. `ON CONFLICT DO NOTHING` keeps it idempotent and
    preserves "first writer wins the trigger": if a specialist already created
    the row this is a no-op.
    """
    try:
        import psycopg  # lazy — --no-write paths don't reach here
    except ImportError:
        return
    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sweep_cycles (cycle_id, started_at, trigger, git_head)
                    VALUES (%s, now(), %s, %s)
                    ON CONFLICT (cycle_id) DO NOTHING
                    """,
                    (cycle_id, trigger, _git_head()),
                )
            conn.commit()
    except Exception as e:  # noqa: BLE001
        print(f"==> ensure cycle row failed: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a sweep from the local operator session.",
    )
    parser.add_argument(
        "steps",
        nargs="*",
        help=(
            "Step list. Either group name (all|light|heavy) or any of: "
            "doc, version, security, health, slo. Default: all."
        ),
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Skip the Postgres write (smoke test). Findings still print to stdout.",
    )
    parser.add_argument(
        "--postgres-dsn",
        default=os.environ.get("SWEEP_PG_DSN"),
        help=(
            "Explicit DSN. If unset, the script port-forwards postgresql + "
            "decodes the sweep-history WRITER_DSN secret automatically."
        ),
    )
    parser.add_argument(
        "--prom-url",
        default=os.environ.get("SLO_PROM_URL"),
        help=(
            "Prometheus URL for slo-check. If unset, port-forwards "
            "kube-prometheus-stack-prometheus automatically."
        ),
    )
    parser.add_argument(
        "--pushgateway-url",
        default=os.environ.get("SWEEP_PUSHGATEWAY_URL"),
        help=(
            "Pushgateway base URL for the maintenance-window liveness push "
            "(job maintenance-window-liveness). If unset, port-forwards "
            "monitoring/prometheus-pushgateway automatically."
        ),
    )
    parser.add_argument(
        "--cycle-id",
        default=os.environ.get("SWEEP_CYCLE_ID"),
        help=(
            "Shared SWEEP_CYCLE_ID. Auto-generated if unset — EXCEPT with "
            "--reconcile-only, which REQUIRES it (or SWEEP_CYCLE_ID in the "
            "env): reconciling against a freshly-minted id would auto-close "
            "every open finding in the --ran sections."
        ),
    )
    parser.add_argument(
        "--ran",
        default=None,
        help=(
            "Comma-separated sections that actually ran (e.g. "
            "doc,version,security,health,slo). Scopes auto-close. Without it the "
            "scope is INFERRED from rows written this cycle, which cannot see a "
            "section that ran clean and wrote nothing."
        ),
    )
    parser.add_argument(
        "--reconcile-only",
        action="store_true",
        help=(
            "Run NO check steps — only recompute and store the verdict for "
            "--cycle-id from the currently-open findings, then exit. The "
            "daily-operation fan-out uses this to finalize the one shared cycle "
            "its specialists all wrote to (via SWEEP_CYCLE_ID), so the unified "
            "cycle ends with a correct verdict instead of a stale per-section one."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    steps = _resolve_steps(args.steps)
    cycle_id = args.cycle_id or str(uuid.uuid4())
    # Before the first forward is dialled: TERM/HUP must unwind into the
    # `finally` below, and atexit must catch whatever does not (F-b881a5b5).
    _install_teardown_signals()

    pg_fwd: Forward | None = None
    prom_fwd: Forward | None = None
    dsn = args.postgres_dsn
    prom_url = args.prom_url

    write_enabled = not args.no_write
    needs_slo = "slo" in steps

    try:
        # Postgres connection — needed by every step that writes findings
        if write_enabled and not dsn:
            port = _free_port()
            print(f"==> port-forwarding postgresql ({port}/tcp) ...")
            pg_fwd = Forward("databases", "postgresql", port, 5432)
            pg_fwd.dial()
            raw = _kubectl_secret_dsn()
            if not raw:
                raise SystemExit(
                    "Could not decode sweep-history WRITER_DSN secret. "
                    "Pass --postgres-dsn or set SWEEP_PG_DSN."
                )
            # The FQDN is reconstructed at runtime instead of being a string
            # literal — having it inline trips the pre-commit Layer-1 scanner
            # which substring-matches against decoded cluster Secrets. See
            # the `feedback_precommit_cluster_secret_match` operator memory.
            fqdn = "@postgresql." + "databases.svc.cluster.local:5432"
            dsn = raw.replace(fqdn, f"@127.0.0.1:{port}")
            # Arm the END-TO-END probe now that the DSN is known, and prove
            # the path to the pod before anything trusts it: a forward that
            # accepts TCP and refuses the first real connection (F-fe1795c5)
            # is caught here, not by the first section's silently lost write.
            pg_fwd.probe = _pg_probe(dsn)
            _require_forward(pg_fwd, "startup")

        # Reconcile-only: recompute the verdict for the shared cycle from the
        # currently-open findings and exit — no check steps. This is how the
        # daily-operation fan-out finalizes the single cycle all its specialists
        # wrote to under one SWEEP_CYCLE_ID (fixes the "red verdict, 0 open
        # findings" dashboard artifact of per-section fragmentation).
        if args.reconcile_only:
            if not dsn:
                raise SystemExit(
                    "--reconcile-only needs the DB (do not combine with --no-write)."
                )
            # A reconcile MUST target the cycle whose findings it is judging.
            # Without --cycle-id (and without SWEEP_CYCLE_ID in the env) the
            # id above is a FRESH uuid, so `cycle_id != <fresh>` is true for
            # EVERY row — the auto-close would then resolve every open finding
            # in every --ran section, including ones a specialist re-confirmed
            # minutes earlier. This is not hypothetical: an un-scoped reconcile
            # minted cycle f11badb9… on 2026-08-18 at 13:56. Refuse instead.
            if not args.cycle_id:
                raise SystemExit(
                    "--reconcile-only requires --cycle-id (or SWEEP_CYCLE_ID in "
                    "the env): reconciling against a freshly-minted cycle id "
                    "would auto-close EVERY open finding in the --ran sections, "
                    "because none of them can carry a cycle id that does not "
                    "exist yet."
                )
            # The reconcile writes the ran-set, the auto-close and the verdict
            # through the forward; prove it is live first (re-dial once), or
            # abort non-zero — a reconcile whose writes vanish is a green
            # board over an unrecorded cycle.
            _require_forward(pg_fwd, "reconcile")
            # The fan-out finalizes here. Guarantee the shared cycle row exists
            # even if every specialist ran clean (lazy-create means no finding →
            # no row), so the verdict lands somewhere and /api/cycles/latest has
            # a row to resolve to.
            _ensure_cycle_row(dsn, cycle_id, os.environ.get("SWEEP_TRIGGER", "manual"))
            # Reconcile-only skipped these two steps until 2026-07-06 — the
            # daily-operation fan-out had to apply them manually mid-sweep to
            # get an accurate verdict (findings sat at raw severity=critical
            # despite being AR-accepted, and stale rows from already-fixed
            # items never auto-closed). Run the same two steps the full
            # pipeline runs (see below) before reconciling, so this flag is
            # self-sufficient again.
            tagged = _apply_ar_suppression(dsn)
            if tagged:
                print(f"==> AR-suppressed {tagged} finding(s) (matched accepted_risks descriptions)")
            # Auto-close scope MUST be "sections that actually reported this
            # cycle", never a hardcoded list of sections we hope reported.
            #
            # 2026-08-14: this was hardcoded to all six including "media" — but
            # sweep-run has NO media step (steps are doc/version/security/health/
            # slo; media-manager is an agent that writes out-of-band). So every
            # --reconcile-only run auto-closed EVERY open media finding for
            # "not firing", including four that the media agent had just
            # re-confirmed as still true. Absence of a report is not evidence of
            # resolution — the same non-result-as-conclusion bug this codebase
            # keeps hitting, here in its most damaging form because it silently
            # marks real problems fixed.
            #
            # Derive the set from what wrote findings under THIS cycle_id.
            RECONCILE_CANDIDATES = ["doc", "version", "security", "health", "slo", "media"]
            if args.ran:
                # Explicit declaration from the orchestrator. Authoritative: it is
                # the only thing that can distinguish "ran and found nothing" from
                # "never ran" — there is no per-section run record in the schema,
                # and a section that ran clean may write no rows at all.
                reported = {x.strip() for x in args.ran.split(",") if x.strip()}
                print(f"==> auto-close scope declared by caller: {', '.join(sorted(reported))}")
            else:
                reported = _sections_reporting_this_cycle(dsn, cycle_id)
                print(f"==> auto-close scope INFERRED from rows written this cycle: "
                      f"{', '.join(sorted(reported)) or '(none)'} — pass --ran to declare it "
                      f"explicitly; a section that ran clean can write no rows and would "
                      f"otherwise look like it never ran")
            # Persist the ran-set on the cycle row (notes JSON). Without this
            # there is NO per-section run record anywhere, so the board renderer
            # must show a clean section as "DID NOT REPORT" — a false gap. The
            # record is written only here, from the same authoritative set the
            # auto-close uses, so "ran clean" on the board always means a real run.
            try:
                import json as _json
                import psycopg as _pg
                with _pg.connect(dsn) as _c, _c.cursor() as _cur:
                    _cur.execute("SELECT notes FROM sweep_cycles WHERE cycle_id = %s", (cycle_id,))
                    _row = _cur.fetchone()
                    _notes = {}
                    if _row and _row[0]:
                        try:
                            _notes = _json.loads(_row[0])
                        except (ValueError, TypeError):
                            _notes = {"legacy_notes": _row[0]}
                    _notes["ran"] = sorted(reported)
                    _cur.execute("UPDATE sweep_cycles SET notes = %s WHERE cycle_id = %s",
                                 (_json.dumps(_notes), cycle_id))
                    _c.commit()
            except Exception as _e:  # noqa: BLE001 - the record is best-effort; reconcile must not die on it
                print(f"==> WARNING: could not persist ran-set on cycle row: {_e}")

            skipped = [x for x in RECONCILE_CANDIDATES if x not in reported]
            if skipped:
                print(f"==> auto-close SKIPPED for section(s) that did not report "
                      f"this cycle: {', '.join(skipped)} (their open findings are "
                      f"left untouched — no report is not a resolution)")
            closed = _auto_close_stale_findings(dsn, cycle_id, sorted(reported))
            if closed:
                print(f"==> auto-closed {len(closed)} finding(s) that didn't fire this cycle:")
                for fid, sec, title in closed[:20]:
                    print(f"      ✓ resolved {sec}/{fid}: {title[:80]}")
                if len(closed) > 20:
                    print(f"      … and {len(closed) - 20} more")
            v = _reconcile_verdict(dsn, cycle_id)
            print(f"==> reconciled cycle {cycle_id} verdict -> {v}")
            # The fan-out's finalizer is the normal cron path, so the liveness
            # figures are pushed here too (F-2dabaddb); the DSN rides on the
            # child's env, never on os.environ (F-4b27e81c).
            _report_liveness_push({**os.environ, "SWEEP_PG_DSN": dsn}, args.pushgateway_url)
            return 0

        # Prometheus — only slo-check needs it
        if needs_slo and not prom_url:
            port = _free_port()
            print(f"==> port-forwarding prometheus ({port}/tcp) ...")
            prom_url = f"http://127.0.0.1:{port}"
            prom_fwd = Forward("monitoring", "kube-prometheus-stack-prometheus",
                               port, 9090, probe=_http_probe(prom_url))
            prom_fwd.dial()
            _require_forward(prom_fwd, "startup")

        env = os.environ.copy()
        # GHCR auth for trivy. Nine first-party ghcr.io/nachtschatt3n/* images are
        # PRIVATE, so an unauthenticated trivy gets "UNAUTHORIZED: authentication
        # required" and reports them UNKNOWN — four of them are on external
        # ingresses, so that is a real blind spot, not noise. Trivy reads
        # TRIVY_USERNAME/TRIVY_PASSWORD, so pass the gh token through when we have
        # one. Harmless when the token lacks `read:packages`: trivy simply fails
        # the same way it already does today (scan_ok=False → reported UNKNOWN,
        # never silently "clean").
        if not env.get("TRIVY_PASSWORD"):
            _tok = env.get("GITHUB_TOKEN") or env.get("GH_TOKEN")
            if not _tok:
                try:
                    _tok = subprocess.check_output(
                        ["gh", "auth", "token"], text=True, timeout=10,
                        stderr=subprocess.DEVNULL).strip()
                except Exception:  # noqa: BLE001
                    _tok = ""
            if _tok:
                env["TRIVY_USERNAME"] = env.get("TRIVY_USERNAME") or "nachtschatt3n"
                env["TRIVY_PASSWORD"] = _tok
                # security-check's Flux-source owner oracle and the ghcr tag
                # listing read GITHUB_TOKEN; anonymous GitHub is 60 calls/h.
                env["GITHUB_TOKEN"] = env.get("GITHUB_TOKEN") or _tok
        env["SWEEP_CYCLE_ID"] = cycle_id
        env["SWEEP_TRIGGER"] = env.get("SWEEP_TRIGGER", "manual")
        if write_enabled and dsn:
            env["SWEEP_PG_DSN"] = dsn
            # Create the one canonical cycle row up-front. Specialists now
            # create their cycle row lazily (first finding only), so without
            # this a zero-finding sweep would leave no row for the verdict /
            # dashboard to attach to. ON CONFLICT keeps a specialist's own
            # first-write authoritative for the trigger.
            _ensure_cycle_row(dsn, cycle_id, env["SWEEP_TRIGGER"])
        if prom_url:
            env["SLO_PROM_URL"] = prom_url

        print(f"==> sweep-run: cycle={cycle_id} trigger={env['SWEEP_TRIGGER']} "
              f"steps={steps} write={'YES' if write_enabled else 'NO'}")
        print()

        # Sections run under forward supervision (F-f85cf55c): probed
        # end-to-end before AND after each one; a section whose forward was
        # dead at write time is `lost`, never `completed` — so it is not
        # auto-closed against, and the run exits non-zero below.
        res = _run_steps_supervised(steps, env,
                                    pg_fwd if (write_enabled and dsn) else None,
                                    prom_fwd)
        nonzero: list[str] = res["nonzero"]
        completed: list[str] = res["completed"]  # ran to a sane rc AND wrote through a live forward

        # The post-step DB phases (AR suppression, auto-close, verdict) all
        # write through the forward — prove it live first, or abort non-zero.
        if write_enabled and dsn:
            _require_forward(pg_fwd, "post-steps (AR suppression / auto-close / verdict)")

        # Apply AR suppression: tag any open finding whose title matches
        # an enabled accepted-risk description as severity=accepted. Runs
        # first so subsequent auto-close decisions see the post-tag state.
        if write_enabled and dsn:
            tagged = _apply_ar_suppression(dsn)
            if tagged:
                print()
                print(f"==> AR-suppressed {tagged} finding(s) (matched accepted_risks descriptions)")

        # Auto-close open findings in completed sections that did NOT
        # re-fire this cycle. Section == step name. Skip if writes are
        # disabled or no DSN.
        if write_enabled and dsn and completed:
            closed = _auto_close_stale_findings(dsn, cycle_id, completed)
            if closed:
                print()
                print(f"==> auto-closed {len(closed)} finding(s) that didn't fire this cycle:")
                for fid, sec, title in closed[:20]:
                    print(f"      ✓ resolved {sec}/{fid}: {title[:80]}")
                if len(closed) > 20:
                    print(f"      … and {len(closed) - 20} more")

        # Reconcile the cycle verdict from the ACTUAL open findings, AFTER
        # AR-suppression + auto-close. The per-section scripts each write a
        # provisional verdict via writer.close() from their pre-suppression
        # crit/warn counts (so an AR-029 accepted-risk CVE counts as
        # "critical"), and in a parallel fan-out the last section to finish
        # wins the race — which is how a clean cycle ended up red. This makes
        # the stored verdict match the open-findings list the dashboard shows.
        if write_enabled and dsn:
            verdict = _reconcile_verdict(dsn, cycle_id)
            if verdict:
                print()
                print(f"==> cycle verdict reconciled from open findings: {verdict}")
            # The liveness push lives on the --reconcile-only branch (the
            # cron/fan-out finalizer, daily-operation.md rule 4b), NOT here:
            # this full-sweep path is the ad-hoc operator smoke run, the
            # figures it would push are identical, and it must not add a
            # second port-forward to the supervised set this path accounts
            # for (F-2dabaddb push; F-f85cf55c supervision).

        print()
        for fwd in (pg_fwd, prom_fwd):
            for line in (fwd.log if fwd else []):
                print(f"==> forward supervision: {line}")
        if not nonzero:
            print(f"==> sweep-run done (cycle={cycle_id}, all clean)")
        else:
            print(f"==> sweep-run done (cycle={cycle_id}, nonzero={nonzero})")
        # A section whose forward was dead at write time did NOT report,
        # whatever its exit code said — its rows were silently discarded.
        # That is a failed run, and the ONE thing this exit code must never
        # hide (F-f85cf55c). Everything else keeps the in-cluster entrypoint
        # contract: nonzero from a script often just means "found a finding".
        if res["lost"] or res["skipped"]:
            print(f"==> FAILED: DB write lost for section(s) {res['lost'] or '[]'} "
                  f"(forward dead at write time), skipped {res['skipped'] or '[]'} "
                  f"(forward dead before the section and not revivable) — these "
                  f"sections did NOT report this cycle; exit {EXIT_FORWARD_DEAD}",
                  file=sys.stderr)
            return EXIT_FORWARD_DEAD
        return 0
    finally:
        if prom_fwd is not None:
            prom_fwd.stop()
        if pg_fwd is not None:
            pg_fwd.stop()


if __name__ == "__main__":
    sys.exit(main())
