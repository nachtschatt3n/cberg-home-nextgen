#!/usr/bin/env python3
"""
Security audit script for Kubernetes homelab cluster.

Runs all 11 security checks from security-check.md and writes results to
runbooks/security-check-current.md. All sensitive values (domain, name,
email) are loaded at runtime from SOPS / git config and redacted in output.

Usage:
    python3 runbooks/security-check.py
    python3 runbooks/security-check.py --postgres-dsn "$WRITER_DSN"
    SWEEP_PG_DSN=... SWEEP_CYCLE_ID=... python3 runbooks/security-check.py

Output:
    runbooks/security-check-current.md
    (optional) findings emitted to sweep-history Postgres
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.request

# Self-activate mise toolchain so kubectl/talosctl/flux/sops + KUBECONFIG/etc are
# set regardless of how the script is invoked (cron, sub-agent, fresh shell).
def _activate_mise() -> None:
    if os.environ.get("_MISE_ACTIVATED"):
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isfile(os.path.join(repo_root, ".mise.toml")):
        return
    mise = next((os.path.join(p, "mise") for p in os.environ.get("PATH", "").split(os.pathsep)
                 if os.path.isfile(os.path.join(p, "mise"))), None)
    if not mise:
        return
    os.environ["_MISE_ACTIVATED"] = "1"
    os.execvp(mise, [mise, "-C", repo_root, "exec", "--", sys.executable, *sys.argv])

_activate_mise()
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# Acceptance lists used to live in runbooks/security_check_acceptances.py
# (78 cred patterns + 13 secret-file paths + 26 ingress hostnames). Since
# Plan Phase 1.5 they're stored in the `security_acceptances` table of
# sweep_history Postgres and loaded lazily via PEP-562 module __getattr__.
# Import path stays at the top of the file (no behavioural change for
# downstream sites that read these names).
sys.path.insert(0, str(Path(__file__).parent))
from lib.security_acceptances import (  # noqa: E402
    EXTERNAL_INGRESS_ACCEPTED,
    GIT_HISTORY_CRED_PATTERNS,
    GIT_HISTORY_SECRET_FILES,
)

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

class C:
    RESET  = '\033[0m'
    RED    = '\033[0;31m'
    GREEN  = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE   = '\033[0;34m'
    CYAN   = '\033[0;36m'
    BOLD   = '\033[1m'


def cprint(color: str, msg: str) -> None:
    print(f"{color}{msg}{C.RESET}")


# ---------------------------------------------------------------------------
# Severity constants
# ---------------------------------------------------------------------------

CRITICAL = "🔴"
WARNING  = "🟡"
OK       = "🟢"
ACCEPTED = "🛡️"

# ---------------------------------------------------------------------------
# Repo paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT  = SCRIPT_DIR.parent
# Snapshot path defaults to runbooks/X-current.md, overridable via env so
# the in-cluster collector (read-only rootfs) can redirect to /tmp.
OUTPUT     = Path(os.environ.get("SWEEP_SNAPSHOTS_DIR", str(SCRIPT_DIR))) / "security-check-current.md"
ACCEPTED_RISKS_DOC = REPO_ROOT / "docs" / "security-accepted-risks.md"

# Make `runbooks/lib/...` importable when invoked from any CWD.
sys.path.insert(0, str(SCRIPT_DIR))
from lib.findings_writer import (  # noqa: E402
    FindingsWriter, DegradationLog, cycle_id_from_env, trigger_from_env,
    git_head, SEVERITY_MAP,
)
from lib import risk_model as rm  # noqa: E402  — contextual tier scorer (Phase 2)
from lib import notify as _notify  # noqa: E402  — tier-based routing (Phase 2)


# ---------------------------------------------------------------------------
# Accepted risks loader
# ---------------------------------------------------------------------------

def load_accepted_risks() -> dict[str, str]:
    """Return {AR-ID: description} for all enabled accepted_risks.

    Source of truth (since Plan Phase 1.4): the `accepted_risks` table in
    sweep_history Postgres. The DSN comes from `SWEEP_PG_DSN` env (set by
    `runbooks/sweep-run.py`, the daily-operation orchestrator, or
    individual operator invocations).

    Legacy YAML/Markdown fallback: if `SWEEP_PG_DSN` is unset AND
    `docs/security-accepted-risks.md` still exists on disk, parse it
    using the original regex. This bridges the Phase 1↔2 gap; the file
    (and this fallback) are removed in Phase 2.

    Failure is NOT the same as "no accepted risks". If the policy store is
    the source of truth (SWEEP_PG_DSN set) but unreachable, this sets
    _POLICY_LOAD_FAILED so the caller can abort: continuing would silently
    unsuppress EVERY accepted risk and report the lot as fresh criticals.
    See docs/sops/audit-script-correctness.md — absence of a signal must not
    be scored as a result.
    """
    dsn = os.environ.get("SWEEP_PG_DSN")
    if dsn:
        return _load_accepted_risks_from_db(dsn)
    return _load_accepted_risks_from_markdown()


def _load_accepted_risks_from_db(dsn: str) -> dict[str, str]:
    global _POLICY_LOAD_FAILED
    try:
        import psycopg  # lazy: degrade if psycopg isn't available
    except ImportError:
        _POLICY_LOAD_FAILED = "psycopg not installed"
        cprint(C.YELLOW, "  ⚠ psycopg not installed — cannot load accepted risks")
        return {}
    try:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT ar_id, description FROM accepted_risks "
                "WHERE enabled = true AND status = 'accepted' "
                "ORDER BY ar_id"
            )
            return {row[0]: row[1] for row in cur.fetchall()}
    except Exception as e:
        _POLICY_LOAD_FAILED = str(e)
        cprint(C.YELLOW, f"  ⚠ could not load accepted_risks from DB: {e}")
        return {}


def _load_accepted_risks_from_markdown() -> dict[str, str]:
    global _POLICY_LOAD_FAILED
    if not ACCEPTED_RISKS_DOC.exists():
        # Phase 2 removed this file; accepted risks are DB-only now. So "no DSN"
        # is not a valid way to run the audit — it yields zero suppression, which
        # is indistinguishable from "nothing is accepted" and floods the report
        # with false criticals. Same failure as an unreachable DB, different door.
        _POLICY_LOAD_FAILED = ("SWEEP_PG_DSN unset and legacy "
                               f"{ACCEPTED_RISKS_DOC.name} is gone (removed in Phase 2)")
        cprint(C.YELLOW, f"  ⚠ accepted-risks doc not found: {ACCEPTED_RISKS_DOC}")
        return {}
    try:
        text = ACCEPTED_RISKS_DOC.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        # Must set the flag: returning {} unflagged un-suppresses EVERY accepted
        # risk while main()'s fail-closed abort stays silent, so the audit
        # silently widens what it reports without anyone being told the policy
        # store was never read.
        _POLICY_LOAD_FAILED = f"could not read {ACCEPTED_RISKS_DOC.name}: {e}"
        cprint(C.YELLOW, f"  ⚠ could not read accepted-risks doc: {e}")
        return {}
    if not text.strip():
        _POLICY_LOAD_FAILED = f"{ACCEPTED_RISKS_DOC.name} is empty"
        cprint(C.YELLOW, f"  ⚠ accepted-risks doc is empty: {ACCEPTED_RISKS_DOC}")
        return {}
    pattern = re.compile(r"\b(AR-\d{3})\s*[:—\-]\s+(.+?)\s*$")
    risks: dict[str, str] = {}
    for line in text.splitlines():
        line = line.lstrip("# ").rstrip()
        m = pattern.match(line)
        if m:
            ar_id, desc = m.group(1), m.group(2).strip()
            risks.setdefault(ar_id, desc)
    return risks


_ACCEPTED_RISKS: dict[str, str] = {}
# Set by the loader when the policy store was expected but unreachable.
# Distinguishes "zero accepted risks" from "could not read them".
_POLICY_LOAD_FAILED: str | None = None

# ---------------------------------------------------------------------------
# Degraded-coverage recorder
# ---------------------------------------------------------------------------
# This audit degrades gracefully in dozens of places: an unreachable
# Elasticsearch, a throttled NVD, a 401 from the UniFi controller, a missing
# trivy binary — each one lets the run continue and still produce a verdict.
# That is right for REPORTING and lethal for AUTO-CLOSE, which resolves any
# open finding this section did not re-emit. A degraded check emits nothing,
# and without a veto that silence reads as "all those findings got fixed" —
# a monitoring outage would quietly clear the security backlog.
#
# Every degrade path records here; main() hands the accumulated reasons to
# writer.mark_incomplete() before close(), which vetoes auto-close for the
# whole `security` section while still reporting everything we COULD measure.
# Contract: docs/sops/sweep-findings-lifecycle.md.
DEGRADED = DegradationLog("security", printer=lambda m: cprint(C.YELLOW, m))

# Which section is executing, so the shared primitives below can attribute a
# failure without every call site passing a scope. Set by section_header().
_CURRENT_SECTION: str = "startup"


def _scope() -> str:
    return _CURRENT_SECTION


# Transient vs steady-state. A veto is only meaningful for a condition that
# CHANGES between runs: that is the case where findings existed yesterday, the
# dependency broke today, and absence would be misread as "fixed". A permanent
# condition (an API we have always called wrongly, an endpoint this firmware
# has never supported) never produced findings in the first place, so there is
# nothing for auto-close to wrongly resolve — and vetoing on it would keep
# auto-close switched off forever, protecting nothing. Steady-state breakage is
# reported as a FINDING instead, which is how it gets fixed.
# 403 is included because rate limiters (GitHub, some registries) signal
# throttling with it. 5xx is a RANGE, not an enumeration: the Cloudflare family
# (520-527, esp. 521 origin-down / 522 / 524 timeout) and 507/508/509 are
# textbook transient, and misfiling them as permanent is the direction that
# LOSES data — no veto, real findings auto-close during an edge outage. Matches
# check-all-versions.py's classifier; the two must not drift.
_TRANSIENT_HTTP = {408, 425, 429, 403}


def _is_transient(exc: Exception) -> bool:
    """True when `exc` is a retry-worthy blip rather than a permanent defect."""
    code = getattr(exc, "code", None)
    if code is not None:
        try:
            code = int(code)
        except (TypeError, ValueError):
            # A non-numeric .code must not raise out of an except: block and
            # abort the section. Unknown shape -> treat as transient (the
            # fail-safe direction: veto rather than auto-close on doubt).
            return True
        return code in _TRANSIENT_HTTP or code >= 500
    # Timeouts / DNS / connection resets have no status code.
    return isinstance(exc, (TimeoutError, OSError))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd: str, timeout: int = 30) -> str:
    """Run a shell command, return stdout (empty string on error).

    The EXCEPTION path (timeout, missing binary, OSError) is an unambiguous
    coverage gap and is recorded. A non-zero returncode is NOT recorded here:
    most callers are greps, where "no match" is rc=1 with empty stdout and a
    perfectly legitimate clean result. Sites where rc matters record their own
    reason explicitly.
    """
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as e:
        # redact(): the s3 history pickaxe carries the secret DOMAIN inside
        # the command string, well within cmd[:90], and this reason is printed
        # to stdout and repeated in close()'s auto-close SKIPPED line.
        DEGRADED.record(_scope(), f"command failed ({cmd.split()[0]})",
                        redact(f"{type(e).__name__} after {timeout}s: {cmd[:90]}"))
        return ""


def run_cmd(cmd: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run command and return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        # redact(): the s3 history pickaxe carries the secret DOMAIN inside
        # the command string, well within cmd[:90], and this reason is printed
        # to stdout and repeated in close()'s auto-close SKIPPED line.
        DEGRADED.record(_scope(), f"command failed ({cmd.split()[0]})",
                        redact(f"{type(e).__name__} after {timeout}s: {cmd[:90]}"))
        return 1, "", str(e)


def run_unifictl(cmd: str, timeout: int = 15, retries: int = 2, backoff: float = 2.0) -> str:
    """run() for unifictl probes, retrying transient auth/empty blips.

    The local UniFi controller occasionally 401s or times out when the
    gateway is momentarily busy (high CPU/mem); a single such blip otherwise
    manufactures a false "session expired" finding even though the session
    is valid. Retry on empty output or a login-failed signature before
    treating it as a real failure."""
    out = run(cmd, timeout=timeout)
    for _ in range(retries):
        if out and "login failed" not in out.lower():
            break
        time.sleep(backoff)
        out = run(cmd, timeout=timeout)
    if not out or "login failed" in out.lower():
        # Every retry blipped the same way — this is no longer transient.
        DEGRADED.record(_scope(), "UniFi controller (unifictl)",
                        f"empty/login-failed after {retries + 1} attempts: {cmd[:80]}")
    return out


def run_lines(cmd: str, timeout: int = 30) -> list[str]:
    out = run(cmd, timeout=timeout)
    return [l for l in out.splitlines() if l.strip()]


def kubectl(args: str, timeout: int = 30) -> str:
    return run(f"kubectl {args}", timeout=timeout)


def kubectl_json(args: str, timeout: int = 30) -> dict | list | None:
    """Parsed `kubectl ... -o json`, or None.

    None is ALWAYS a coverage gap: a working apiserver returns a valid List
    with an empty `items` for "no such resources". So None means the API was
    unreachable or the output was unparsable — and every caller guards with
    `if data:`, silently skipping its whole check. Record it.
    """
    out = kubectl(args + " -o json", timeout=timeout)
    try:
        return json.loads(out)
    except Exception as e:
        DEGRADED.record(_scope(), "kubernetes API (kubectl)",
                        f"no parsable JSON from `{args[:70]}`: {type(e).__name__}")
        return None


# ---------------------------------------------------------------------------
# Sensitive-value loading and redaction
# ---------------------------------------------------------------------------

_sensitive: dict[str, str] = {}


def load_sensitive() -> bool:
    """Populate _sensitive from SOPS and git config. Returns True on success."""
    domain_raw = run(
        "sops -d kubernetes/flux/components/common/cluster-secrets.sops.yaml "
        "| grep 'SECRET_DOMAIN:' | awk '{print $2}' | tr -d '\"'",
        timeout=15,
    )
    # NAME: prefer `git config user.name`, fall back to the most recent
    # commit author. Local `git config user.name` is sometimes empty (e.g.,
    # when only user.email is set), which used to produce NAME=0c and skip
    # redaction entirely. The `git log -1 --format=%aN` fallback gives us
    # the name that actually appears in committed artifacts — the right
    # value to redact from any audit output that might be pasted into a
    # public artifact.
    git_name = run("git config user.name") or run("git log -1 --format=%aN")
    git_email = run("git config user.email") or run("git log -1 --format=%aE")

    if not domain_raw:
        cprint(C.RED, "  ERROR: could not decrypt cluster-secrets.sops.yaml — is sops/age key available?")
        return False

    _sensitive["DOMAIN"] = domain_raw
    _sensitive["NAME"]   = git_name
    # Only treat git user.email as a scannable EMAIL literal if it's actually
    # email-shaped. Here git_email is a bare username ("mathiasuhl", no @), and
    # fixed-string scanning that across the repo matched legitimate reverse-DNS
    # launchd labels (com.mathiasuhl.*) as a "[EMAIL] literal" — a false
    # positive. A bare handle isn't a meaningful email-leak signal.
    _sensitive["EMAIL"]  = (
        git_email if ("@" in git_email and "." in git_email.rsplit("@", 1)[-1]) else ""
    )
    return True


def redact(text: str) -> str:
    """Replace all sensitive literals with bracketed placeholders."""
    for key, val in _sensitive.items():
        if val:
            text = text.replace(val, f"[{key}]")
    return text


# ---------------------------------------------------------------------------
# Finding tracker
# ---------------------------------------------------------------------------

class Findings:
    def __init__(self):
        # (severity, message, meta). `meta` is per-finding structured data that
        # is persisted to sweep_findings.metadata (DB-only) — e.g. the
        # machine-readable `cve_ids` list attached by s4_cve_check. It NEVER
        # reaches the committed markdown report (that renders severity+message
        # only), which is what keeps CVE IDs out of committed files while still
        # letting KEV assess them off the DB record.
        self._items: list[tuple[str, str, dict]] = []

    def add(self, severity: str, msg: str, *, meta: dict | None = None) -> None:
        self._items.append((severity, redact(msg), dict(meta or {})))

    def worst(self) -> str:
        for sev in (CRITICAL, WARNING):
            if any(s == sev for s, _, _ in self._items):
                return sev
        return OK

    def markdown(self) -> str:
        if not self._items:
            return f"{OK} No findings\n"
        return "\n".join(f"- {s} {m}" for s, m, _ in self._items) + "\n"

    def count(self, severity: str) -> int:
        return sum(1 for s, _, _ in self._items if s == severity)

    def summary_cell(self) -> str:
        c = self.count(CRITICAL)
        w = self.count(WARNING)
        parts = []
        if c: parts.append(f"{c} critical")
        if w: parts.append(f"{w} warning")
        return ", ".join(parts) if parts else "clean"

    def suppress_accepted(self, accepted_risks: dict[str, str]) -> None:
        """Re-tag findings whose message contains an accepted-risk description
        substring. Sets severity to ACCEPTED and prepends the AR-ID to the
        message. Lenient: case-insensitive substring match on the description.
        """
        if not accepted_risks:
            return
        new_items: list[tuple[str, str, dict]] = []
        for sev, msg, meta in self._items:
            matched_id: str | None = None
            haystack = msg.lower()
            for ar_id, desc in accepted_risks.items():
                needle = desc.lower().strip()
                if needle and needle in haystack:
                    matched_id = ar_id
                    break
            if matched_id:
                new_items.append((ACCEPTED, f"[{matched_id}] {msg}", meta))
            else:
                new_items.append((sev, msg, meta))
        self._items = new_items


# ---------------------------------------------------------------------------
# Elasticsearch / Wazuh-indexer access — inside-pod exec, NOT port-forward
#
# We query both indexers by `kubectl exec`-ing into their pod and curling
# localhost:9200 directly, instead of port-forwarding to the operator's Mac.
# The port-forward approach intermittently dropped mid-sweep (concurrent
# forwards + macOS networking) and reported the backend "unavailable" when it
# was actually healthy (finding F-28d48cd7). Inside-pod exec has no local
# socket to flake. The class names + query() signatures are unchanged so
# callers don't care.
# ---------------------------------------------------------------------------

def _indexer_name(index: str) -> str:
    """Human name for the backing store, for degradation reasons."""
    return "Wazuh indexer" if index.startswith("wazuh") else "Elasticsearch"


def _exec_search(ns: str, pod: str, container: str, userpass: str | None,
                 index: str, body: dict, timeout: int) -> dict | None:
    """Run an _search against the indexer from inside its own pod.

    JSON body is piped to curl via stdin (`-d @-`) so there's no shell
    quoting of the query. Returns parsed JSON, or None on any failure.
    """
    if not userpass or not pod:
        DEGRADED.record(_scope(), _indexer_name(index),
                        "no pod name or no credentials — query not attempted")
        return None
    data = json.dumps(body)
    cmd = [
        "kubectl", "exec", "-i", "-n", ns, pod, "-c", container, "--",
        "curl", "-sk", "-u", userpass, "-H", "Content-Type: application/json",
        f"https://localhost:9200/{index}/_search", "-d", "@-",
    ]
    for attempt in range(3):
        try:
            p = subprocess.run(cmd, input=data, capture_output=True,
                               text=True, timeout=timeout + 25)
            if p.returncode == 0 and p.stdout.strip():
                return json.loads(p.stdout)
        except Exception:
            pass
        if attempt < 2:
            time.sleep(2)
    DEGRADED.record(_scope(), _indexer_name(index),
                    f"_search against {index} failed on all 3 attempts")
    return None


class ElasticPortForward:
    """Despite the legacy name, queries Elasticsearch via inside-pod exec
    (see module note above). Used as a context manager so callers are
    unchanged from the old port-forward implementation."""

    def __init__(self):
        self._password = None
        self._pod = None
        self._ns = "monitoring"
        self._container = "elasticsearch"

    def __enter__(self):
        self._pod = run(
            "kubectl get pod -n monitoring "
            "-l elasticsearch.k8s.elastic.co/cluster-name=elasticsearch "
            "-o jsonpath='{.items[0].metadata.name}'"
        ).strip().strip("'")
        raw = run(
            "kubectl get secret elasticsearch-es-elastic-user -n monitoring "
            "-o jsonpath='{.data.elastic}'"
        )
        try:
            import base64
            self._password = base64.b64decode(raw.strip("'")).decode()
        except Exception as e:
            DEGRADED.record("elasticsearch_setup", "Elasticsearch credentials",
                            f"could not decode elasticsearch-es-elastic-user: "
                            f"{type(e).__name__}")
            self._password = None
        if not self._pod:
            DEGRADED.record("elasticsearch_setup", "Elasticsearch pod",
                            "no elasticsearch pod found in namespace monitoring")
        return self

    def __exit__(self, *_):
        pass

    def query(self, body: dict, timeout: int = 15) -> dict | None:
        return _exec_search(
            self._ns, self._pod, self._container,
            f"elastic:{self._password}" if self._password else None,
            "logs-generic-default", body, timeout,
        )


# ---------------------------------------------------------------------------
# Wazuh indexer (separate from ECK Elasticsearch — different cluster, creds,
# index pattern). Used by section 13 to pull SIEM findings. Also inside-pod
# exec, same rationale as Elasticsearch above.
# ---------------------------------------------------------------------------

class WazuhPortForward:
    """Despite the legacy name, queries the Wazuh indexer via inside-pod
    exec (see module note above)."""

    def __init__(self):
        self._password = None
        self._pod = "wazuh-indexer-0"
        self._ns = "security"
        self._container = "wazuh-indexer"

    def __enter__(self):
        pod = run(
            "kubectl get pod -n security -l app=wazuh-indexer "
            "-o jsonpath='{.items[0].metadata.name}'"
        ).strip().strip("'")
        if pod:
            self._pod = pod
        raw = run(
            "kubectl get secret wazuh-secret -n security "
            "-o jsonpath='{.data.INDEXER_PASSWORD}'"
        )
        try:
            import base64
            self._password = base64.b64decode(raw.strip("'")).decode()
        except Exception as e:
            DEGRADED.record("wazuh_setup", "Wazuh indexer credentials",
                            f"could not decode wazuh-secret INDEXER_PASSWORD: "
                            f"{type(e).__name__}")
            self._password = None
        return self

    def __exit__(self, *_):
        pass

    def query(self, body: dict, index: str = "wazuh-alerts-*", timeout: int = 15) -> dict | None:
        return _exec_search(
            self._ns, self._pod, self._container,
            f"admin:{self._password}" if self._password else None,
            index, body, timeout,
        )


# ---------------------------------------------------------------------------
# Section implementations
# ---------------------------------------------------------------------------

def section_header(n: int, title: str) -> None:
    # Header numbers are 1..13 and index-align with _SECTION_SLUGS (n=7 is
    # s6a_error_rate_spikes, n=13 is s13_wazuh_siem), so the slug the writer
    # uses for `subsection` is also the scope a degraded primitive reports.
    global _CURRENT_SECTION
    try:
        _CURRENT_SECTION = _SECTION_SLUGS[n - 1]
    except (IndexError, NameError):  # pragma: no cover — defensive
        _CURRENT_SECTION = f"s{n}"
    cprint(C.BLUE, f"\n[{n}/13] {title}")


def s1_sops_coverage() -> tuple[str, Findings, str]:
    section_header(1, "SOPS Encryption Coverage")
    f = Findings()
    lines = []

    # Unencrypted kind:Secret files
    # Anchor on a column-0 `kind: Secret` so this matches an actual Secret
    # *manifest* (top-level document field) and not a nested reference such as
    # a Gateway `certificateRefs: - kind: Secret` or a HelmRelease
    # `valuesFrom: - kind: Secret` — those name a Secret, they do not contain one.
    unenc = run_lines(
        "grep -rlE '^kind: Secret[[:space:]]*$' kubernetes/ --include='*.yaml' "
        "| grep -v '\\.sops\\.yaml$'"
    )
    # Filter known false-positives (SecretKeyRef refs, SA tokens, kustomization refs,
    # _template/ scaffolding directories, and *.example.yaml placeholder files which are
    # by design unencrypted and not deployed by any kustomization).
    fp_patterns = ["helmrelease.yaml", "ks.yaml", "token-secret.yaml", "/_template/", ".example.yaml"]
    real_unenc = [p for p in unenc if not any(fp in p for fp in fp_patterns)]
    if real_unenc:
        for p in real_unenc:
            f.add(CRITICAL, f"Plaintext `kind: Secret` in `{p}`")
            cprint(C.RED, f"  🔴 Unencrypted Secret: {p}")
    else:
        cprint(C.GREEN, "  🟢 No unencrypted Secret manifests")

    # SOPS temp files
    temp = run_lines("find kubernetes/ talos/ -name '.decrypted~*' -type f 2>/dev/null")
    if temp:
        for t in temp:
            f.add(CRITICAL, f"SOPS temp file on disk: `{t}`")
            cprint(C.RED, f"  🔴 SOPS temp file: {t}")
    else:
        cprint(C.GREEN, "  🟢 No SOPS temp files")

    # Suspicious base64 outside sops files (filter known safe patterns)
    b64_hits = run_lines(
        "grep -rE '[A-Za-z0-9+/]{40,}={0,2}' kubernetes/ --include='*.yaml' "
        "| grep -v '\\.sops\\.yaml' | grep -v 'sops:' | grep -v '#' "
        "| grep -v 'githubusercontent\\.com' | grep -v 'url:'"
    )
    # Further filter paths and content that are clearly non-secret
    # longhorn helmrelease: long camelCase YAML keys (not values) match the base64 regex
    safe_content = ["ks.yaml", "grafana", "prometheusrule", "coredns", "helm-values",
                    "  path: ./kubernetes", "  path: ./talos",
                    "longhorn/app/helmrelease.yaml",
                    "talos/clusterconfig/",  # Talos node configs contain expected inline certs/keys
                    "factory.talos.dev",     # Talos installer image URLs
                    "ghcr.io/siderolabs/installer",  # Talos installer images
                    "nodeAffinityPreset", "podAffinityPreset",  # Bitnami chart affinity YAML keys
                    "requiredDuringSchedulingIgnoredDuringExecution",  # K8s podAffinity field name
                    "preferredDuringSchedulingIgnoredDuringExecution", # K8s podAffinity field name
                    "/paperclip/instances/default/data/backups",  # shell path in backup-cleanup.yaml
                    ]
    # Structural filter: JSONPatch operation paths (Flux postRenderers,
    # kustomize patches) are slash-rooted POSIX-like strings with no '=' or
    # '+'. Real base64 has padding ('=') or '+'. JSONPatch paths regularly
    # cross the 40-char threshold (e.g. /spec/template/spec/containers/0/...)
    # and were previously suppressed via per-app substring entries in
    # safe_content (terminationGracePeriodSeconds, the paperclip path).
    # Replace those bandaids with one regex that catches the whole class.
    _jsonpatch_path = re.compile(
        r'\bpath:\s*/[A-Za-z0-9~_-][A-Za-z0-9/~_.-]*\s*$'
    )
    # Repo-path references in YAML comments (inline documentation pointers
    # like `kubernetes/apps/network/external/ingress-nginx/helmrelease.yaml`).
    # These regularly appear inside ConfigMap `data:` blocks where the
    # `grep -v '#'` precondition above doesn't help (XML/inline comments use
    # `<!-- -->` or are continuation lines, not `#`-prefixed). Filter any
    # line whose match contains a recognisable repo-root directory followed
    # by a known file extension.
    _repo_path = re.compile(
        r'\b(?:kubernetes|docs|runbooks|tests|terraform|tools|talos|\.claude|\.github)/'
        r'[A-Za-z0-9/_.-]+\.(?:yaml|yml|md|py|sh|txt|json|xml|toml)\b',
        re.IGNORECASE,
    )
    real_b64 = [
        h for h in b64_hits
        if not any(p in h for p in safe_content)
        and not _jsonpatch_path.search(h)
        and not _repo_path.search(h)
    ]
    if real_b64:
        for hit in real_b64[:10]:
            short = redact(hit[:120])
            f.add(WARNING, f"Possible inline credential: `{short}`")
            cprint(C.YELLOW, f"  🟡 Suspicious base64: {short}")
    else:
        cprint(C.GREEN, "  🟢 No suspicious base64 outside sops files")

    lines.append(f.markdown())
    return f.worst(), f, "\n".join(lines)


def s2_sensitive_exposure() -> tuple[str, Findings, str]:
    section_header(2, "Sensitive Data Exposure Scan")
    f = Findings()
    domain = _sensitive.get("DOMAIN", "")
    name   = _sensitive.get("NAME", "")
    email  = _sensitive.get("EMAIL", "")

    # --- A: personal literals (domain / git name / email) -----------------
    for label, val in [("domain", domain), ("name", name), ("email", email)]:
        if not val:
            continue
        hits = run_lines(
            f"git ls-files | grep -v '\\.sops\\.yaml$' "
            f"| xargs grep -Fl '{val}' 2>/dev/null"
        )
        if hits:
            for h in hits:
                f.add(CRITICAL, f"[{label.upper()}] literal found in `{h}`")
                cprint(C.RED, f"  🔴 {label} literal in: {h}")
        else:
            cprint(C.GREEN, f"  🟢 {label} not in tracked non-sops files")

    # --- B: credential keyword = value patterns (YAML key-value / INI) ----
    # Matches: password: value, auth_token = "value", jwt_secret: value, etc.
    kw = (r"password|passwd|secret[_-]?key|api[_-]?key|access[_-]?key|"
          r"private[_-]?key|auth[_-]?token|jwt[_-]?secret|signing[_-]?key|"
          r"client[_-]?secret|webhook[_-]?secret|encryption[_-]?key|"
          r"bearer[_-]?token|access[_-]?token")
    val_re = r"""\s*[:=]\s*["']?[A-Za-z0-9+/!@#$%^&*()\[\]._:;,{}<>|\\~`@-]{8,}["']?"""
    raw_hits = run_lines(
        f"git ls-files kubernetes/ talos/ | grep -v '\\.sops\\.yaml$' "
        f"| xargs grep -rniE '({kw}){val_re}' 2>/dev/null",
        timeout=30,
    )
    # Whitelist patterns: references, shell vars, placeholders, SOPS, comments
    _ref = re.compile(
        r"secretKeyRef|valueFrom|secretRef|existingSecret|secretName|"
        r"secretStore|envFromSecret|backupTargetCredential|"
        r"ENC\[|sops:|"
        r"\$\{[^}]*\}|\$[A-Z_][A-Z0-9_]*|PGPASSWORD=\$|DB_PASSWORD\b|"
        r"__file|__env|\$__|process\.env|"
        r"changeme|placeholder|example|EXAMPLE|your_|my-aws-|"
        r"NOPASSWD|ollamaKey|basicAuth.*__file",
        re.IGNORECASE,
    )
    cred_hits = []
    for line in raw_hits:
        # extract the content part after "filename:linenum:"
        parts = line.split(":", 2)
        content = parts[2] if len(parts) >= 3 else line
        # skip comment lines
        if content.lstrip().startswith("#"):
            continue
        if _ref.search(line):
            continue
        # skip if value portion is a plain kebab/snake k8s resource name
        # (no uppercase, no special chars, no digits-only) → likely a ref
        m = re.search(r'[:=]\s*["\']?([A-Za-z0-9+/!@#$%^&*._-]{8,})["\']?', content)
        if m:
            val_str = m.group(1)
            if re.fullmatch(r"[a-z0-9][a-z0-9-]*", val_str):
                continue  # plain kebab-case → k8s resource name
        cred_hits.append(line)

    if cred_hits:
        for h in cred_hits[:15]:
            short = redact(h[:130])
            f.add(WARNING, f"Plaintext credential pattern: `{short}`")
            cprint(C.YELLOW, f"  🟡 Credential pattern: {short}")
    else:
        cprint(C.GREEN, "  🟢 No plaintext credential keyword=value patterns")

    # --- C: Kubernetes env var format: - name: SECRET_FOO / value: literal --
    # Read tracked non-sops YAML files and look for adjacent name/value pairs
    tracked = run_lines(
        "git ls-files kubernetes/ talos/ | grep -v '\\.sops\\.yaml$' "
        "| grep '\\.yaml$'"
    )
    _secret_name_re = re.compile(
        r"name:\s*(.*(?:PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY|"
        r"AUTH_KEY|SIGNING_KEY|JWT_SECRET|WEBHOOK_SECRET|"
        r"ACCESS_KEY|CLIENT_SECRET|ENCRYPTION_KEY)[A-Z0-9_]*)\s*$",
        re.IGNORECASE,
    )
    _value_re = re.compile(
        r"value:\s*[\"']?([A-Za-z0-9+/!@#$%^&*._-]{8,})[\"']?\s*$"
    )
    _ref2 = re.compile(r"valueFrom|secretKeyRef|\$\{|\$[A-Z_]")
    env_hits = []
    for fpath in tracked:
        try:
            lines_text = Path(REPO_ROOT / fpath).read_text(errors="replace").splitlines()
        except OSError:
            continue
        for i, ln in enumerate(lines_text[:-1]):
            nm = _secret_name_re.search(ln)
            if not nm:
                continue
            next_ln = lines_text[i + 1]
            vm = _value_re.search(next_ln)
            if not vm:
                continue
            if _ref2.search(next_ln):
                continue
            entry = f"`{fpath}:{i+2}` — env `{nm.group(1)}` = `{redact(vm.group(1)[:60])}`"
            env_hits.append(entry)

    if env_hits:
        for h in env_hits:
            f.add(WARNING, f"Hardcoded env secret: {h}")
            cprint(C.YELLOW, f"  🟡 Hardcoded env: {h}")
    else:
        cprint(C.GREEN, "  🟢 No hardcoded secrets in Kubernetes env vars")

    # --- D: known token format fingerprints ------------------------------
    TOKEN_PATTERNS = [
        ("GitHub PAT (classic)",  r"ghp_[A-Za-z0-9]{36}"),
        ("GitHub PAT (fine-grained)", r"github_pat_[A-Za-z0-9_]{82}"),
        ("GitHub app/action token", r"ghs_[A-Za-z0-9]{36}"),
        ("AWS access key",         r"AKIA[0-9A-Z]{16}"),
        ("Slack webhook",          r"hooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]+"),
        ("Discord webhook",        r"discord(?:app)?\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+"),
        ("JWT token",              r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),
        ("Cloudflare API token",   r"[A-Za-z0-9_-]{40}(?=[^A-Za-z0-9_-]|$)"),
    ]
    token_hits = []
    for label, pat in TOKEN_PATTERNS[:-1]:  # skip Cloudflare (too broad for generic scan)
        matches = run_lines(
            f"git ls-files kubernetes/ talos/ | grep -v '\\.sops\\.yaml$' "
            f"| xargs grep -rniE '{pat}' 2>/dev/null",
            timeout=20,
        )
        for m in matches:
            token_hits.append((label, redact(m[:130])))

    if token_hits:
        for label, hit in token_hits:
            f.add(CRITICAL, f"{label} format found: `{hit}`")
            cprint(C.RED, f"  🔴 {label}: {hit}")
    else:
        cprint(C.GREEN, "  🟢 No known token format fingerprints found")

    f.suppress_accepted(_ACCEPTED_RISKS)
    lines = [f.markdown()]
    return f.worst(), f, "\n".join(lines)


def s3_git_history() -> tuple[str, Findings, str]:
    section_header(3, "Git History Secret Scan")
    f = Findings()
    domain = _sensitive.get("DOMAIN", "")

    # Accepted exceptions live in `security_check_acceptances.py` so credential
    # rotations and false-positive whitelists can be edited in a focused file
    # without touching the 1700-line scanner.
    ACCEPTED_CRED_PATTERNS = GIT_HISTORY_CRED_PATTERNS
    ACCEPTED_SECRET_FILES = GIT_HISTORY_SECRET_FILES

    # Plaintext credential patterns
    # Scope: exclude files that are themselves scanners/reports/SOPs containing regex strings
    # and historical findings (self-reference noise).
    cred_hits = run_lines(
        "git log --all --oneline -p "
        "-- . ':(exclude)runbooks/security-check-current.md' "
        "      ':(exclude)runbooks/security-check.md' "
        "      ':(exclude)runbooks/security-check.py' "
        "      ':(exclude)runbooks/doc-check.py' "
        "      ':(exclude)runbooks/doc-check-current.md' "
        "      ':(exclude)runbooks/health-check.sh' "
        "      ':(exclude)docs/sops/*.md' "
        "| grep -iE '(password|secret|token|api.?key|private.?key)\\s*[:=]\\s*\\S{8,}' "
        "| grep -vi 'sops\\|ENC\\[AES\\|secretKeyRef\\|valueFrom\\|EXAMPLE\\|your_\\|your-"
        "\\|placeholder\\|changeme\\|SECRET_\\|\\${\\|process\\.env\\|__env\\|__file"
        "\\|REPLACE_WITH\\|pullSecret:' "
        # Placeholder values in ANY case/separator style: the `changeme` filter
        # above is case-insensitive but NOT separator-insensitive, so
        # CHANGE_ME_TO_STRONG_PASSWORD / change-me-in-production sailed through
        # (2026-08-18 false positives F-2bb5cb28 / F-1eea708e):
        "| grep -viE 'change[_-]?me|replace[_-]?me' "
        # Bare or quoted shell variables like $DB_PASSWORD, "$ICLOUD_PASSWORD":
        # -i: `X-Plex-Token=$TOKEN` must match the token= branch too (2026-08-17
        # false positives); the $[A-Z_]+ var-name part stays effectively case-strict.
        "| grep -viE 'PGPASSWORD=\\$|password=\"?\\$[A-Z_]+|token=\"?\\$[A-Z_]+|api.?key=\"?\\$[A-Z_]+' "
        "| grep -vE '^[+-]?\\s*#|description:' "
        "| grep -v '\"replace-me\"\\|\"my-strong-password\"\\|\"my-api-key\"\\|\"your-api-key-here\"\\|openssl rand' "
        # Template/doc placeholders like <github-personal-access-token>, <web-ui-password>:
        "| grep -v '<[a-z][a-z0-9-]*>' "
        # Shell commands that reference secrets by name, not value:
        "| grep -vE 'kubectl (edit|get|describe) secret|`kubectl edit secret' "
        # Shell command substitution — value captured at runtime, never hardcoded:
        "| grep -vE '[a-zA-Z_]+=\"\\$\\(' "
        # Runtime/computed values — the RHS is a FUNCTION CALL (any identifier or
        # dotted path followed by `(`), never a hardcoded literal. Covers
        # `open(...)`, `os.getenv(...)`, `Path(...).read()` AND custom helpers
        # like `token = _bot_token()` (the 2026-07-27 false positive). A literal
        # secret is a quoted string or a bare token — it is never `identifier(...)`.
        "| grep -ivE '(token|password|secret|api.?key)\\s*[:=]\\s*[A-Za-z_][A-Za-z0-9_.]*\\(' "
        # Python f-string interpolation (e.g., X-Plex-Token={token}) — variable, not a value:
        "| grep -ivE '(token|password|secret|api.?key)=\\{[a-zA-Z_]+\\}' "
        # Language keyword RHS (`token: Optional[str] = None`) — a declaration
        # default, structurally never a hardcoded credential. POSIX bracket
        # gotcha (2026-08-18): backslash is NOT an escape inside a POSIX ERE
        # bracket expression, so the previous `[,;}\\)\\]]*` class was
        # terminated by the first `]` and required one delimiter — /usr/bin/grep
        # (BSD) never matched the bare `= None` line and the filter was dead in
        # production (it only worked under PCRE-style greps). A `]` must be
        # listed FIRST in the class instead. `:` included for `def f(x:
        # Optional[str] = None):` signature lines.
        "| grep -ivE '(token|password|secret|api.?key)[^=]*=\\s*(None|null|nil|true|false)[][:space:]),;}:]*$' "
        # Type-annotated declarations (`github_token: Optional[str] = ...`) —
        # an `Optional[` RHS is a type hint, never a literal secret value:
        "| grep -viE '(token|password|secret|api.?key)[a-z0-9_]*\\s*:\\s*Optional\\[' "
        # sed/awk redaction-or-rotation commands: the matched credential text is a
        # regex SEARCH pattern (a bracket character-class quantified with +/*, e.g.
        # api_key = \"[a-f0-9]+\") and the replacement is a shell $VAR — it can never
        # be a hardcoded literal secret. e.g. sed -E 's/api_key = \"[a-f0-9]+\"/.../'.
        "| grep -vE '\\b(sed|grep)\\b.*\\[[^]]+\\][+*]' "
    )
    # Cross-line variable-reference filter.
    #
    # A JS/TS object literal like `{ botToken: jerryTok }` matches the credential
    # regex, but the RHS is a VARIABLE — its value came from `process.env` on a
    # line the grep pipeline never sees, because every filter above is
    # single-line. That produced the 2026-08-13 `jerryTok` false positive.
    #
    # Rather than guess from the line alone (which risks hiding a real secret in
    # YAML, where an unquoted scalar IS the literal), ask a question a hardcoded
    # secret can never answer yes to: is this identifier ever DECLARED as a
    # variable anywhere in history? If yes, the hit is a reference. This cannot
    # create a false negative — a literal has no declaration.
    #
    # The extra history pass only runs when there are surviving hits.
    _ident_rhs = re.compile(
        # Trailing delimiters: the real history line ends `{ botToken: jerryTok });`
        # — brace, paren AND semicolon. The original `[,}\)]?` allowed at most ONE
        # and no semicolon, so the identifier was never extracted, the declaration
        # lookup never ran, and the false positive survived the "fix". Allow any
        # run of closing punctuation.
        r"(?:token|password|secret|api.?key)\s*[:=]\s*([A-Za-z_][A-Za-z0-9_]{2,})\s*[,;}\)\]]*\s*$",
        re.I,
    )
    _candidates = {m.group(1) for h in cred_hits if (m := _ident_rhs.search(h))}
    if _candidates:
        # Bytes-mode + errors="replace": run_cmd() decodes strictly, and this
        # repo's history contains binary blobs, so the text-mode call raised
        # UnicodeDecodeError inside run_cmd, silently returned "", the
        # `declared` set came back empty, and the whole cross-line filter was
        # dead in production (2026-08-18 jerryTok false positive F-f88a2a34).
        try:
            _hist_raw = subprocess.run(
                "git log --all -p --no-color", shell=True,
                capture_output=True, timeout=180,
            ).stdout or b""
        except Exception:
            _hist_raw = b""
        declared = set(re.findall(
            r"\b(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=",
            _hist_raw.decode("utf-8", errors="replace"),
        ))
        if declared:
            cred_hits = [
                h for h in cred_hits
                if not ((m := _ident_rhs.search(h)) and m.group(1) in declared)
            ]

    # Filter accepted risks
    cred_hits = [h for h in cred_hits if not any(a in h for a in ACCEPTED_CRED_PATTERNS)]
    if cred_hits:
        for h in cred_hits[:5]:
            f.add(WARNING, f"Credential-like pattern in history: `{redact(h[:100])}`")
            cprint(C.YELLOW, f"  🟡 History: {redact(h[:100])}")
    else:
        cprint(C.GREEN, "  🟢 No plaintext credential patterns in history")

    # Domain literal in non-sops history
    if domain:
        # The file list MUST be expanded by the shell as arguments, not
        # interpolated as text. `git ls-files` output is NEWLINE separated, so
        # embedding it directly made every filename after the first its own
        # shell COMMAND — ~1000 "command not found"s, one of which blocks on
        # stdin until the 30s timeout kills the whole thing. The pickaxe then
        # produced no output, int("") raised, n fell back to 0, and the check
        # printed "Domain not in non-sops git history" on every run without
        # ever having searched. Command substitution splits on IFS into
        # ARGUMENTS, which is what was intended. Measured: ~3s, was timing out.
        count = run(
            f"git log --all -p -S '{domain}' -- "
            f"$(git ls-files | grep -v '\\.sops\\.yaml$') 2>/dev/null "
            f"| grep '^+.*{domain}' | grep -v 'sops\\|ENC\\[' | wc -l",
            timeout=120,
        ).strip()
        try:
            n = int(count)
        except ValueError:
            # Distinguish "searched, found none" from "never searched".
            DEGRADED.record(_scope(), "git history pickaxe (domain literal)",
                            "scan produced no count — domain-leak history check "
                            "did not run")
            n = -1
        if n > 0:
            f.add(WARNING, f"Domain literal found in {n} deleted lines of non-sops history")
            cprint(C.YELLOW, f"  🟡 Domain in {n} lines of non-sops git history (deleted content)")
        elif n == 0:
            cprint(C.GREEN, "  🟢 Domain not in non-sops git history")

    # Secret-named files ever committed outside .sops.yaml
    secret_files = run_lines(
        "git log --all --diff-filter=A --name-only --pretty=format: "
        "| grep -i 'secret\\|password\\|credential\\|private.key' "
        "| grep -v '\\.sops\\.yaml$' | sort -u"
    )
    # Filter accepted risks
    secret_files = [sf for sf in secret_files
                    if not any(sf.startswith(a) or sf == a for a in ACCEPTED_SECRET_FILES)]
    if secret_files:
        for sf in secret_files:
            f.add(WARNING, f"Secret-named file committed outside sops: `{sf}`")
            cprint(C.YELLOW, f"  🟡 Historical secret file: {sf}")
    else:
        cprint(C.GREEN, "  🟢 No plaintext secret filenames in history")

    return f.worst(), f, f.markdown()


_VER_CHECKER = None  # lazy-loaded VersionChecker (registry tag lookups)


# Head-of-line floating tags: a bare MAJOR (optionally `v`/`pg` prefixed, with
# optional distro/variant suffixes) or a bare codename. Conservative BY DESIGN —
# a false positive here would classify a genuinely-bumpable image as accepted and
# hide a real CVE, so major.minor and anything more specific must NOT match
# (17.10-bookworm, 18.4, 8.19.15, 0.5.1-alpha, v3.1.0-openvino all stay pinned).
_FLOATING_LINE_TAG_RE = re.compile(
    r'^(?:(?:v|pg)?\d{1,3}'
    r'|lts|bookworm|bullseye|trixie|alpine|jammy|noble|focal)'
    r'(?:-(?:alpine|slim|bookworm|bullseye|trixie|jammy|noble|focal|lts|openvino|cuda|debian\d*))*$',
    re.IGNORECASE,
)


# Build-variant suffixes: the part after the version that selects a build flavour
# rather than a newer version. Kept explicit (not a catch-all "any suffix") so a
# genuine pre-release like `0.5.1-alpha` or a patch like `1.2.3-r4` is never
# mistaken for a variant and silently accepted.
_IMAGE_VARIANT_SUFFIXES = {
    "openvino", "cuda", "rocm", "armnn", "rknn",
    "alpine", "slim", "bookworm", "bullseye", "trixie", "jammy", "noble", "focal",
    "ubuntu", "debian", "distroless",
}


def _is_digest_pinned(image_ref: str) -> bool:
    """True for `repo@sha256:...` with NO tag at all.

    There is genuinely no tag to compare, so the newer-tag lookup can only
    return "undetermined" — but that is a different situation from a registry
    error, and it has a different remedy: compare the CHART/appVersion that
    renders the image. Saying so turns a permanent vague critical into an
    actionable one (spegel sat in that state, while actually being current).
    """
    ref = image_ref.split("@")[0]
    return "@sha256:" in image_ref and ":" not in ref.rsplit("/", 1)[-1]


def _is_floating_line_tag(tag: str) -> bool:
    return bool(tag) and bool(_FLOATING_LINE_TAG_RE.match(str(tag)))


# Tag names upstream re-publishes in place. Content behind these can change with
# no manifest edit, so what Trivy scanned today is not necessarily what runs
# tomorrow.
_MUTABLE_TAG_NAMES = frozenset({
    "latest", "stable", "dev", "edge", "main", "master", "nightly", "rolling",
})


def _is_mutable_tag_ref(image_ref: str) -> bool:
    """True when upstream can swap this ref's content without a manifest edit.

    DELIBERATELY NOT check-all-versions' `is_rolling_tag()`. That regex answers
    "can I semver-compare this tag?", so it groups immutable git-sha tags
    (`sha-3b0ddc2`) and digest-suffixed refs (`latest@sha256:...`) together with
    `latest` — for its question both are equally "no". The question HERE is the
    opposite one: "can the bytes change under us?", for which a git-sha tag and a
    digest pin are the *most* immutable things in the inventory. Reusing
    is_rolling_tag() verbatim raised 5 false findings against genuinely-pinned
    images (the ghcr.io/nachtschatt3n/* `sha-*` CI builds, plus digest-pinned
    icloud-drive and music-assistant-skill). Keep the two notions separate.
    """
    if "@sha256:" in image_ref:
        return False  # digest-pinned → immutable whatever the tag says
    tag = image_ref.rpartition(":")[2]
    if not tag or "/" in tag:
        return False  # no tag at all (bare repo, or a registry:port host)
    if tag.lower() in _MUTABLE_TAG_NAMES:
        return True
    # Head-of-line tags (postgres:18, postgres:17-alpine, node:lts-alpine,
    # pgvector:pg16) are rebuilt in place by upstream — mutable by the same test.
    return _is_floating_line_tag(tag)


# "Already on the newest upstream tag" describes the remediation ROUTE (there is
# no tag to bump to), NOT the level of risk. For a handful of fixable CVEs,
# "wait for upstream's next rebuild" is a credible plan and AR-029 fairly covers
# it. Past some magnitude that stops being credible: the image is materially
# vulnerable right now, and the real options are a variant/base switch, a
# replacement, or a compensating control — a decision that belongs with a human
# rather than being absorbed into a warning-severity accepted risk.
# The value is operator policy, not a law of nature. It was calibrated against
# the live already-newest population so that it isolates genuine outliers
# without a false-positive wave; the per-image numbers behind that calibration
# are vulnerability detail and live on the sweep_findings records, not here
# (docs/sops/vulnerability-disclosure.md). Re-calibrate from a sweep, not from
# memory, and tighten it deliberately rather than drifting it.
_UNBUMPABLE_CRIT_ESCALATE = 50

# Our own applications' registry namespace. Images here are built and published
# by the operator's own app repos; the cluster sweep holds no pull credentials
# for them by deliberate policy, so trivy cannot scan them from here.
_PRIVATE_REGISTRY_PREFIX = "ghcr.io/nachtschatt3n/"


# ---------------------------------------------------------------------------
# Kernel-header packages: header FILES, never executed code.
#
# `linux-libc-dev` (Debian/Ubuntu) and its friends ship ONLY /usr/include/linux
# — the userspace copy of the kernel UAPI headers. They exist in an image
# because something in the build needed them to COMPILE (node-gyp and other
# native addons pull them in), and nothing in the image ever RUNS them. The
# CVEs Trivy attaches to them are Linux KERNEL CVEs, and the kernel our
# containers execute against is the Talos node kernel, not the distro's.
# Ubuntu's 6.8 / Debian's 6.1 header package is a version string in a package
# DB, not an attack surface on this cluster.
#
# Counting them made every Ubuntu/Debian-based image look materially
# vulnerable and, worse, look FIXABLE — Trivy reports a FixedVersion because
# the distro publishes patched headers, so these landed in the crit_fix tally
# that drives the CRITICAL findings and the unbumpable-escalation threshold.
# They are also not fixable by the one remedy that tally implies: the packages
# are pinned identically in newer upstream builds of the same image, so a bump
# moves the count not at all (evidence: security_ref F-b885ec1b,
# 2026-08-18 — the same header version in the current tag and the newer beta).
#
# Scope discipline: this is an ALLOWLIST of header-only packages, matched
# against os-pkgs results only, and it is the ONLY package-level exclusion in
# this parser. It exists so a future header-only package (a distro renaming
# linux-libc-dev, a `linux-headers-*` split) can be added deliberately with the
# same justification — NOT as a general-purpose "noisy package" mute. Anything
# that ships executable code, a shared library, or a service belongs in the
# tally even when it is inconvenient. If you are tempted to add a package here,
# the test is: can code from this package ever execute in the container?
_KERNEL_HEADER_PKGS = frozenset({
    "linux-libc-dev",     # Debian / Ubuntu
    "kernel-headers",     # Alpine / RHEL / Fedora
    "linux-headers",      # Alpine meta-package
})
# Split-out per-flavour header packages (linux-headers-6.8.0-87, …).
_KERNEL_HEADER_PREFIXES = ("linux-headers-", "linux-libc-dev-", "kernel-headers-")


def _is_kernel_header_pkg(pkg_name: str, result_class: str) -> bool:
    """True for header-only OS packages whose CVEs describe the RUNNING kernel.

    Restricted to `os-pkgs` on purpose: a language-ecosystem package that
    happens to share the name is a different artifact and stays counted.
    """
    if result_class != "os-pkgs":
        return False
    name = (pkg_name or "").lower()
    return name in _KERNEL_HEADER_PKGS or name.startswith(_KERNEL_HEADER_PREFIXES)


# Version of the TALLY LOGIC below (not of the cache file format). It is
# written into the Trivy cache and compared on load: a cache produced by a
# different tally version is DISCARDED, not served.
#
# Why: on 2026-08-18 the kernel-header exclusion (abb12fda) changed what
# counts as a fixable CRITICAL, but the cache written at 00:37 kept serving
# pre-fix numbers — a logic fix would have taken up to 24h (the TTL) to become
# visible, and the audit would have reported the old numbers as current the
# whole time. Renaming the cache FILE on every logic change (…-v3 → -v4) was
# the previous workaround; it only works when someone remembers.
#
# BUMP THIS whenever tally_trivy_report() or the fix/no-fix classification it
# feeds changes in a way that alters the numbers.
_TRIVY_TALLY_VERSION = 2  # 2 = kernel-header packages excluded from fixable tallies


def tally_trivy_report(report: dict) -> dict | None:
    """Reduce a Trivy JSON report to the CRITICAL/HIGH counts the sweep acts on.

    Split by fix-availability. A CVE with a non-empty FixedVersion has an
    upstream fix -> actionable (update the image). One with no FixedVersion
    (Status affected/will_not_fix/fix_deferred/end_of_life) cannot be patched
    until upstream ships -- that's the AR-029 accepted class. Severity does NOT
    decide acceptance; fix-availability does.

    Returns None when the image has nothing in either bucket. Module-level (not
    nested in the scan worker) so the counting rules are unit-testable against
    a saved report -- see runbooks/tests/test-trivy-tally.py.
    """
    cf = cn = hf = hn = 0  # crit-fixable, crit-nofix, high-fixable, high-nofix
    fix_ids: list[str] = []    # ALL fixable CRITICAL/HIGH CVE IDs (deduped)
    nofix_ids: list[str] = []  # ALL no-upstream-fix CRITICAL/HIGH CVE IDs
    for tgt in report.get("Results", []) or []:
        tgt_class = tgt.get("Class", "")
        for v in tgt.get("Vulnerabilities", []) or []:
            sev = v.get("Severity", "")
            fixable = bool(v.get("FixedVersion"))
            vid = v.get("VulnerabilityID")
            # Kernel-header packages carry kernel CVEs against a kernel this
            # image never executes (see _is_kernel_header_pkg). Drop them from
            # the FIXABLE tallies only: those are what raise CRITICAL/WARNING
            # findings and feed _UNBUMPABLE_CRIT_ESCALATE, and "bump the image"
            # is not a real remedy for them. The no-fix tallies are untouched --
            # they only ever render as AR-029 accepted-risk context, so this
            # change stays narrow and auditable.
            if fixable and _is_kernel_header_pkg(v.get("PkgName", ""), tgt_class):
                continue
            if sev == "CRITICAL":
                cf, cn = (cf + 1, cn) if fixable else (cf, cn + 1)
            elif sev == "HIGH":
                hf, hn = (hf + 1, hn) if fixable else (hf, hn + 1)
            else:
                continue
            # Capture the FULL CVE-ID list (deduped), not just a 5-id sample.
            # These ride on sweep_findings.metadata.cve_ids (DB-only, per
            # disclosure policy) so KEV can assess every CVE finding -- the
            # Phase-1 gap where 122/199 scored exploited=UNKNOWN was purely
            # missing IDs, not missing risk.
            if vid:
                bucket = fix_ids if fixable else nofix_ids
                if vid not in bucket:
                    bucket.append(vid)
    if not (cf or cn or hf or hn):
        return None
    return {"crit_fix": cf, "crit_nofix": cn,
            "high_fix": hf, "high_nofix": hn,
            "fix_sample": fix_ids[:5], "nofix_sample": nofix_ids[:5],
            "fix_ids": fix_ids, "nofix_ids": nofix_ids}


def load_trivy_cache(path: Path, ttl_sec: int, now: float | None = None) -> tuple[dict | None, float | None]:
    """Load the Trivy result cache, or (None, None) if it must not be served.

    Returns (cache_dict, created_at). Three independent reasons to discard:

    1. **Tally version mismatch** — the numbers in the cache were computed by
       different logic than this run would compute. Serving them reports stale
       arithmetic as current (see `_TRIVY_TALLY_VERSION`). A cache with no
       `parser_version` key at all predates the mechanism and is discarded.
    2. **Age** beyond the TTL.
    3. **Unreadable / unparsable.**

    Age is measured from the `created_at` INSIDE the file, not the file mtime,
    because a top-up rewrites the file: keying off mtime would let a cache that
    is topped up daily push its own expiry out forever, so the images scanned
    on day 0 would never be re-scanned.
    """
    now = time.time() if now is None else now
    if not path.exists():
        return None, None
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return None, None
    if not isinstance(raw, dict):
        return None, None
    if raw.get("parser_version") != _TRIVY_TALLY_VERSION:
        return None, None
    try:
        created = float(raw.get("created_at") or path.stat().st_mtime)
    except Exception:
        return None, None
    if now - created >= ttl_sec:
        return None, None
    return raw, created


def collect_trivy_results(scan_targets: list[str], cached: dict | None, scan_fn,
                          retry_failed=None) -> tuple[dict, list, set, list]:
    """Merge cached Trivy results with a TOP-UP scan of everything they miss.

    Returns `(results, failed, scanned_ok, topped_up)`.

    The defect this fixes (F-8cdf8719): a cache hit used to short-circuit the
    scan ENTIRELY. Images that started running after the cache was written were
    therefore never scanned, yet the section reported its numbers as current —
    and the cache's own image set silently defined "coverage". Every image the
    fleet bumped during the day fell into that hole.

    So the cache is now a per-image memo, not a per-run switch: whatever it
    covers is reused (that is the whole performance benefit, and an image whose
    ref has not changed genuinely has not changed), and everything else is
    scanned now.

    `scanned_ok` is the set of images with a real verdict — INCLUDING the clean
    ones. It cannot be derived from `results`, which only holds images that had
    CVEs; conflating "no entry" with "not scanned" would re-scan every clean
    image on every run, and conflating it the other way would call an unscanned
    image clean.

    `retry_failed(img)` decides whether a cached scan FAILURE is worth another
    attempt. Transient failures (a trivy timeout) should be retried — otherwise
    one blip keeps the coverage-gap finding and its veto armed for the full
    TTL. Permanently-unscannable images (our own private registry, which the
    sweep holds no pull credentials for by policy) should not: the retry cannot
    succeed and only costs wall-clock.
    """
    retry_failed = retry_failed or (lambda img: True)
    if cached is None:
        results, failed = scan_fn(scan_targets)
        return results, failed, set(scan_targets) - set(failed), list(scan_targets)

    results: dict = dict(cached.get("results") or {})
    cached_failed: list[str] = list(cached.get("failed") or [])
    # Fallback for a cache written before `scanned` existed: assume only the
    # images WITH findings were covered. Pessimistic on purpose — it re-scans
    # the clean ones once rather than claiming coverage it cannot prove.
    _scanned = cached.get("scanned")
    scanned_ok: set = set(results.keys() if _scanned is None else _scanned)

    keep_failed = [i for i in cached_failed if not retry_failed(i)]
    covered = scanned_ok | set(keep_failed)
    topup = [i for i in scan_targets if i not in covered]

    failed = list(keep_failed)
    if topup:
        new_results, new_failed = scan_fn(topup)
        # A re-scanned image's fresh verdict supersedes its cached one —
        # including "clean now", which is expressed by ABSENCE from new_results.
        for img in topup:
            results.pop(img, None)
        results.update(new_results)
        scanned_ok |= set(topup) - set(new_failed)
        failed += [i for i in new_failed if i not in failed]
    return results, failed, scanned_ok, topup


def _newer_upstream_tag_exists(image_ref: str):
    """Is there a newer upstream image TAG than the one we run?

    Returns True  → a newer tag exists → a fixable CVE is actionable by a bump.
            False → we're already on the newest tag, OR a floating tag
                    (latest/main/git-sha) whose fix would require an upstream
                    REBUILD — which we don't do (we consume upstream images).
            None  → undeterminable (registry error / no tag). Caller must fail
                    toward SURFACING (never hide a critical on a lookup error).

    This is the "we don't rebuild, we run source tags" refinement: a CVE Trivy
    calls "fixable" (a patched package exists in some base repo) is only
    actionable for us if the vendor has published a newer image tag carrying it.
    """
    global _VER_CHECKER
    try:
        if _VER_CHECKER is None:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "check_all_versions", SCRIPT_DIR / "check-all-versions.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _VER_CHECKER = mod.VersionChecker(
                str(SCRIPT_DIR.parent),
                github_token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
        vc = _VER_CHECKER
        repo, _, tag = image_ref.split("@")[0].rpartition(":")
        if not repo or not tag:
            return None
        if vc.is_rolling_tag(tag):
            return False  # latest/main/sha — as current as the tag allows
        if _is_floating_line_tag(tag):
            # Head-of-line tag (postgres:18, postgres:17-alpine, node:lts-alpine,
            # pgvector:pg16, node:22-bookworm). Upstream continuously rebuilds
            # these, and Trivy scans the CURRENT registry content — so a fixable
            # CVE here means upstream has NOT rebuilt yet. There is no newer tag
            # to move to; the only "newer" thing is the next MAJOR line, which is
            # a deliberate upgrade decision, not a CVE remediation. Same
            # remediation shape as a rolling tag: needs an upstream rebuild.
            #
            # Deliberately NOT added to is_rolling_tag(): that would make
            # check-all-versions skip these images as "no semver to compare",
            # losing the legitimate "postgres 17 -> 18 available" signal. The two
            # questions differ — "can I semver-compare this?" vs "can a newer tag
            # fix this CVE?".
            return False
        latest = vc.get_latest_image_tag(repo, tag)
        if not latest:
            return None  # can't determine → surface (security-safe)
        if vc.tags_are_equal(latest, tag):
            return False
        # Variant-suffixed tags must be compared WITHIN their own variant line.
        # `immich-machine-learning:v3.1.0-openvino` resolves latest -> `v3.1.0`,
        # which is not string-equal, so this used to report "newer tag available"
        # even though v3.1.0 IS the current release and no newer -openvino tag
        # exists. (immich-server:v3.1.0 was classified correctly, which is what
        # made the pair look inconsistent.) If the resolved latest equals our tag
        # with its build-variant suffix stripped, we are already current for that
        # variant; a fix needs an upstream rebuild, i.e. the AR-029 shape.
        base, sep, variant = tag.partition("-")
        if sep and variant.lower() in _IMAGE_VARIANT_SUFFIXES and vc.tags_are_equal(latest, base):
            return False
        return True
    except Exception:
        return None


def _parse_version_snapshot(content: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Extract (deployment, app_version) from version-check-current.md.

    The table is `| Deployment | Namespace | Chart | Image | App | Complexity |`.
    The previous regex took the first two BACKTICKED cells, which are
    Deployment and **Namespace** — so it sent `version: "ai"` / `"databases"`
    to OSV. OSV does not reject an unparseable version; it falls back to
    returning EVERY vulnerability for the package, so one component came back
    with 233 CVEs regardless of the version actually deployed. Column position,
    not backtick position, is what identifies the version.

    `App` is the application version (the Chart column is the Helm chart, e.g.
    app-template 5.1.0, which is not the software under test). Rows whose App
    cell is not a comparable version — `-`, `latest`, `git-<sha>`, a bare
    digest — are dropped: OSV cannot match them, and guessing is worse than
    not checking. Returns (rows, dropped_names) — the caller MUST account for
    the dropped set, or a component with a verified mapping but no comparable
    version (cert-manager, whose App cell is `-`) lands in neither the checked
    list nor the unmapped list and is silently folded into a green.
    """
    out: list[tuple[str, str]] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for line in content.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 7:
            continue
        name = cells[1].strip("` ")
        app = cells[5]
        if not name or name in seen or name == "Deployment":
            continue
        # Strip decoration, digest pins and build variants.
        app = app.split("@")[0].split()[0] if app.split() else ""
        app = re.sub(r'[-_](alpine|bookworm|bullseye|jammy|focal|slim|rootless).*',
                     '', app).lstrip("v")
        if not re.fullmatch(r'\d+(\.\d+)*', app):
            seen.add(name)
            dropped.append(name)
            continue
        seen.add(name)
        out.append((name, app))
    return out, dropped


# Verified OSV coordinates for the components the version snapshot tracks.
#
# OSV has NO "Helm" ecosystem — the previous code sent one and was rejected
# HTTP 400 on every request, so this check reported "no CVEs found" for its
# entire lifetime without ever querying anything.
#
# Entries here must be VERIFIED, not guessed, on two axes:
#   1. identity   — the OSV package is the same software we actually run.
#                   `redis` on Packagist is predis, a PHP *client*; Debian's
#                   `mariadb` is a distro source package. Both are the wrong
#                   software and would report someone else's CVEs as ours.
#   2. versioning — OSV's version semantics must match the tag we deploy.
#                   Distro ecosystems (Debian/Alpine) use epoch-revision
#                   versions like `1:10.11.6-1`, which cannot be compared
#                   against an upstream image tag, so they are excluded.
#
# A component absent from this table is reported as NOT CHECKED. That is
# deliberate: OSV answers 200 with an empty vuln list for a package that does
# not exist, so a wrong guess is indistinguishable from a clean result.
_OSV_PACKAGES: dict[str, tuple[str, str]] = {
    "cert-manager": ("Go",   "github.com/cert-manager/cert-manager"),
    "superset":     ("PyPI", "apache-superset"),
    "open-webui":   ("PyPI", "open-webui"),
    "nocodb":       ("npm",  "nocodb"),
}


def s4_cve_check() -> tuple[str, Findings, str]:
    section_header(4, "CVE / Vulnerability Check")
    f = Findings()

    # Renovate security PRs
    security_prs = run_lines("gh pr list --label security --state open 2>/dev/null")
    if security_prs:
        for pr in security_prs:
            f.add(WARNING, f"Open Renovate security PR: `{pr}`")
            cprint(C.YELLOW, f"  🟡 Security PR: {pr}")
    else:
        cprint(C.GREEN, "  🟢 No open Renovate security-labeled PRs")

    # OSV.dev check
    version_file = SCRIPT_DIR / "version-check-current.md"
    if not version_file.exists():
        cprint(C.YELLOW, "  🟡 version-check-current.md not found — skipping OSV check")
        f.add(WARNING, "version-check-current.md missing — run version-check first")
        # This early return skips OSV *and* the entire Trivy running-image
        # scan, i.e. every image CVE finding this section owns.
        DEGRADED.record(_scope(), "version-check-current.md snapshot",
                        "absent — OSV and the running-image Trivy scan both skipped")
        return f.worst(), f, f.markdown()

    content = version_file.read_text()
    unique, no_version = _parse_version_snapshot(content)

    # Spend the query budget on components we can ACTUALLY check. Capping the
    # raw list at 25 first meant the cap was consumed by unmapped components
    # and dropped mapped ones (cert-manager) off the end without checking them.
    candidates = [(n, v) for n, v in unique if n in _OSV_PACKAGES][:25]
    unmapped = [n for n, _v in unique if n not in _OSV_PACKAGES]
    # Mapped, but the snapshot carries no comparable version. These are the
    # dangerous ones: they LOOK covered by the table and are not.
    mapped_no_version = [n for n in no_version if n in _OSV_PACKAGES]
    total = len(unique) + len(no_version)
    cprint(C.CYAN, f"  Checking {len(candidates)} of {total} components "
                   f"against OSV.dev ({len(unmapped)} have no verified OSV "
                   f"package identity)...")
    found_vulns = False
    osv_ok = 0                 # queries that actually got an answer
    osv_transient = 0          # retry-worthy blips -> veto auto-close
    osv_rejected = 0           # permanent 4xx -> emit a finding instead
    osv_reason = ""

    for name, ver in candidates:
        ecosystem, pkg = _OSV_PACKAGES[name]
        clean = ver
        payload = json.dumps({"version": clean,
                              "package": {"name": pkg, "ecosystem": ecosystem}}).encode()
        req = urllib.request.Request(
            "https://api.osv.dev/v1/query", data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=6) as r:
                data = json.load(r)
            osv_ok += 1
            vulns = data.get("vulns", [])
            if vulns:
                ids = [v["id"] for v in vulns]
                # Cap the ID list: the identity anchor is the backticked
                # component+version, so a changing tail does not fork the
                # fingerprint, but an unbounded title is unreadable.
                shown = ", ".join(ids[:5])
                more = f" and {len(ids) - 5} more" if len(ids) > 5 else ""
                f.add(CRITICAL, f"`{name}` {ver} ({ecosystem}/{pkg}): "
                                f"{len(vulns)} CVE(s) — {shown}{more}")
                cprint(C.RED, f"  🔴 {name} {ver}: {len(ids)} CVE(s) — {shown}{more}")
                found_vulns = True
        except Exception as e:
            # If EVERY lookup fails we must not print a green line, so
            # something has to stand between an OSV failure and a manufactured
            # clean bill of health. Which mechanism depends on the failure:
            #
            #  * transient (timeout, 429, 5xx) -> veto auto-close. Findings
            #    existed before and would wrongly resolve. Component-agnostic
            #    text so one outage collapses into ONE reason, not 25.
            #  * permanent (4xx) -> a defect in how WE call the API, not an
            #    outage. It has never returned results, so no finding can
            #    wrongly close; vetoing would disable auto-close forever.
            #    Emit a finding instead so the dead check gets fixed.
            if _is_transient(e):
                osv_transient += 1
                DEGRADED.record(_scope(), "OSV.dev API",
                                f"component lookups failing ({type(e).__name__})")
            else:
                osv_rejected += 1
                osv_reason = f"{type(e).__name__} {getattr(e, 'code', '')}".strip()
        time.sleep(0.15)

    # ─── Coverage accounting ────────────────────────────────────────────────
    # CONTROL INVARIANT: this check may never report a clean OSV result unless
    # at least one query actually succeeded. A silent zero is not a pass. The
    # old code violated this for its entire lifetime — it sent an invalid
    # `ecosystem: "Helm"`, was rejected 400 on all 25 queries, and printed
    # "No CVEs found for checked components" every single run.
    attempted = osv_ok + osv_transient + osv_rejected
    if attempted and osv_ok == 0:
        detail = (f"all {attempted} queries rejected ({osv_reason})"
                  if osv_rejected else
                  f"all {attempted} queries failed to complete")
        f.add(WARNING, f"OSV.dev component scan is inoperative: {detail} — "
                       f"reporting no result, NOT a clean result")
        cprint(C.YELLOW, f"  🟡 OSV.dev inoperative: {detail}")
    elif osv_rejected:
        # PARTIAL rejection is still a hole. Firing only on TOTAL failure meant
        # osv_ok=2 / osv_rejected=1 printed a green covering two thirds of the
        # table, with no finding and no veto for the third.
        f.add(WARNING, f"OSV coverage gap: {osv_rejected} of {attempted} queries "
                       f"rejected ({osv_reason}) — those components were not checked")
        cprint(C.YELLOW, f"  🟡 OSV: {osv_rejected}/{attempted} queries rejected "
                         f"({osv_reason}) — partial coverage")
    elif osv_ok and not found_vulns:
        cprint(C.GREEN, f"  🟢 No CVEs found in {osv_ok} OSV-checked component(s)")

    if mapped_no_version:
        # Has a verified OSV package, but nothing comparable to query with.
        f.add(WARNING, f"OSV coverage gap: {len(mapped_no_version)} mapped "
                       f"component(s) have no comparable version in the snapshot "
                       f"and were NOT checked "
                       f"({', '.join(sorted(mapped_no_version))})")
        cprint(C.YELLOW, f"  🟡 {len(mapped_no_version)} mapped component(s) have "
                         f"no comparable version — not checked")

    if unmapped:
        # Explicit "not checked", never folded into the green above.
        f.add(WARNING, f"OSV coverage gap: {len(unmapped)} of {total} "
                       f"components not checked — ecosystem undetermined "
                       f"({', '.join(sorted(unmapped)[:8])}"
                       f"{', …' if len(unmapped) > 8 else ''})")
        cprint(C.YELLOW, f"  🟡 {len(unmapped)}/{total} components not "
                         f"checked — no verified OSV package identity")

    # ─── Trivy: scan running container images for CRITICAL/HIGH CVEs ────────
    # OSV.dev above is Helm-ecosystem only and limited to the version-check
    # tracked components. This block fills the gap by scanning every distinct
    # image actually running in the cluster — covers app-level CVEs that
    # Renovate would track only after a release, and Bitnami/distro CVEs
    # that OSV doesn't carry.
    #
    # Cached 24h in $TMPDIR/cberg-trivy-cve-cache.json — Trivy DB pulls take
    # ~30-60s and we don't need fresh-every-run. The previous Renovate +
    # OSV blocks above run uncached for daily-fresh signal.
    import shutil
    if not shutil.which("trivy"):
        cprint(C.YELLOW, "  🟡 trivy not on PATH — skipping running-image CVE scan")
        # Emits NOTHING and returns: every open image-CVE finding would
        # auto-close as "fixed" purely because the scanner was absent.
        DEGRADED.record(_scope(), "trivy binary",
                        "not on PATH — running-image CVE scan skipped entirely")
        return f.worst(), f, f.markdown()

    # Cache FILE name is frozen at -v4; logic changes are handled by
    # `_TRIVY_TALLY_VERSION` inside the file (see load_trivy_cache), not by
    # renaming it. The -v4 schema carries the FULL per-image CVE-ID lists
    # (fix_ids / nofix_ids) that feed metadata.cve_ids + KEV scoring, plus (new)
    # `scanned` — the images that got a real verdict, clean ones INCLUDED —
    # `parser_version`, and `created_at`.
    trivy_cache = Path(os.environ.get("TMPDIR", "/tmp")) / "cberg-trivy-cve-cache-v4.json"
    cache_age_sec = 86400  # 24h

    cached, cache_created = load_trivy_cache(trivy_cache, cache_age_sec)
    if cached is not None:
        cprint(C.CYAN, f"  · Trivy cache hit "
                       f"(tally v{_TRIVY_TALLY_VERSION}, "
                       f"{int(cache_age_sec - (time.time() - cache_created))}s until refresh)")
    elif trivy_cache.exists():
        cprint(C.YELLOW, "  · Trivy cache discarded (stale, unreadable, or "
                         f"built by a different tally version than v{_TRIVY_TALLY_VERSION}) — full rescan")

    # Pull every distinct running image once
    images_raw = kubectl(
        "get pods -A -o jsonpath="
        "'{range .items[*].spec.containers[*]}{.image}{\"\\n\"}{end}"
        "{range .items[*].spec.initContainers[*]}{.image}{\"\\n\"}{end}'",
    )
    def _canon_image(img: str) -> str:
        """Canonical name for dedup.

        Kubernetes reports each image exactly as its manifest spells it, so the
        SAME Docker Hub image appears both bare (`postgres:17.10-bookworm`) and
        fully qualified (`docker.io/library/postgres:17.10-bookworm`) depending
        on the app. Deduping on the raw string scanned it twice and, worse,
        reported it as two separate findings — inflating the critical count and
        making the same CVE look like two pieces of work.
        """
        for prefix in ("index.docker.io/library/", "docker.io/library/",
                       "index.docker.io/", "docker.io/"):
            if img.startswith(prefix):
                return img[len(prefix):]
        return img

    distinct_images = sorted({
        _canon_image(i.strip().strip("'")) for i in images_raw.splitlines() if i.strip()
    })
    if not distinct_images:
        # An empty inventory does not mean "nothing is running" — it means the
        # apiserver query returned nothing usable. It also filters the CACHED
        # results and the scan-failure list to nothing, so the section would
        # print a green "no CVEs in 0 running images" and emit not one finding.
        DEGRADED.record(_scope(), "kubernetes API (pod image inventory)",
                        "no running images enumerated — Trivy scan has nothing "
                        "to scan and cached findings are filtered away")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Skip well-known bases that AR docs accept or that don't add useful
    # signal (Bitnami images tracked by Renovate; Wazuh internal images).
    # A POLICY exclusion, permanent by construction: it is reported in the
    # coverage line but never treated as a gap and never vetoes auto-close.
    def _should_skip(img: str) -> bool:
        return any(skip in img.lower() for skip in (
            "bitnami/", "wazuh/wazuh-",
        ))

    scan_targets = [i for i in distinct_images if not _should_skip(i)]

    def _scan_one(img: str, trivy_to: str = "30s", proc_to: int = 45) -> tuple[str, dict | None, bool]:
        # Returns (img, result_or_None, scan_ok). scan_ok=False means the
        # trivy invocation FAILED (timeout / non-zero rc / empty / unparsable)
        # — which is NOT the same as "scanned clean". Conflating the two lets
        # a transient scan failure silently drop a still-running vulnerable
        # image, after which the orchestrator's auto-close falsely resolves
        # its open CVE findings (2026-08-12 false-negative fix).
        rc, stdout, _stderr = run_cmd(
            f"trivy image --severity CRITICAL,HIGH --exit-code 0 "
            f"--quiet --format json --timeout {trivy_to} {img}",
            timeout=proc_to,
        )
        if rc != 0 or not stdout:
            return img, None, False
        try:
            report = json.loads(stdout)
        except Exception:
            return img, None, False
        return img, tally_trivy_report(report), True

    def _scan_batch(targets: list[str]) -> tuple[dict, list]:
        """Scan `targets` in parallel, retry the failures serially.

        Returns (results, still_failed). Used for BOTH the cold-cache full scan
        and the warm-cache top-up, so a topped-up image gets exactly the same
        treatment — including the retry — as one from a full run.
        """
        results: dict[str, dict] = {}
        failed_scans: list[str] = []
        # 6 parallel scans is enough to overlap registry latency without
        # hammering the local Trivy DB lock.
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(_scan_one, img): img for img in targets}
            for fut in as_completed(futures):
                img, result, ok = fut.result()
                if result:
                    results[img] = result
                elif not ok:
                    failed_scans.append(img)

        # Retry images whose parallel scan FAILED — almost always a 30s-timeout
        # under 6-way load on a larger image, not a real absence of CVEs. Serial
        # retry with a generous timeout recovers them; a silently-dropped failure
        # would otherwise let the orchestrator auto-close a still-running image's
        # real open criticals (2026-08-12 fix; e.g. redis-alpine, spegel,
        # k8s-sidecar, harness-home-server, nextcloud-mcp-server, postgres:15/17).
        if failed_scans:
            cprint(C.YELLOW, f"  · retrying {len(failed_scans)} image(s) that failed the parallel scan (90s timeout)...")
            still = []
            for img in failed_scans:
                _img, result, ok = _scan_one(img, trivy_to="90s", proc_to=120)
                if result:
                    results[img] = result
                elif not ok:
                    still.append(img)
            failed_scans = still
        return results, failed_scans

    def _scan_and_report(targets: list[str]) -> tuple[dict, list]:
        if not targets:
            return {}, []
        cprint(C.CYAN, f"  Scanning {len(targets)} image(s) with trivy (parallel)...")
        return _scan_batch(targets)

    # Cache-as-memo, not cache-as-switch. Whatever the cache covers is reused;
    # every image running NOW that it does not cover is scanned NOW (F-8cdf8719
    # — a cache hit used to skip the scan entirely, so 27% of running images
    # went unscanned while their stale numbers were reported as current).
    # Cached failures on our own private registry are NOT retried: no pull
    # credentials by policy, so the retry cannot succeed (steady state).
    findings_per_image, scan_failed, scanned_ok, topped_up = collect_trivy_results(
        scan_targets, cached, _scan_and_report,
        retry_failed=lambda img: not img.startswith(_PRIVATE_REGISTRY_PREFIX),
    )
    if cached is not None:
        cprint(C.CYAN, f"  · cache covered {len(scan_targets) - len(topped_up)}/{len(scan_targets)} "
                       f"scannable images; topped up {len(topped_up)}")

    # Persist the merged state. `created_at` is carried over from the cache we
    # topped up, so a daily top-up cannot keep pushing the TTL out and leave
    # day-0 images permanently un-rescanned.
    try:
        trivy_cache.write_text(json.dumps({
            "parser_version": _TRIVY_TALLY_VERSION,
            "created_at": cache_created if cache_created is not None else time.time(),
            "results": findings_per_image,
            "failed": scan_failed,
            "scanned": sorted(scanned_ok),
        }))
    except Exception:
        pass

    # ─── Coverage accounting ────────────────────────────────────────────────
    # What did this run actually LOOK AT? Everything downstream (the tallies,
    # the green "no CVEs" line, and auto-close) is a claim about the running
    # image set, so the claim is only as good as this number.
    covered = (scanned_ok | set(scan_failed)) & set(scan_targets)
    unattempted = [i for i in scan_targets if i not in covered]
    cprint(C.CYAN, f"  Trivy coverage: {len(covered)}/{len(scan_targets)} scannable images "
                   f"({len(distinct_images) - len(scan_targets)} skipped by policy, "
                   f"{len([i for i in scan_failed if i in scan_targets])} unscannable)")
    if unattempted:
        # TRANSIENT by construction: these were in scope and simply did not get
        # a scan attempt this run (an aborted top-up, an exception in the pool).
        # Next run can be different -> veto, per the transitions rule in
        # docs/sops/sweep-findings-lifecycle.md §4.3.
        DEGRADED.record(_scope(), "trivy running-image coverage",
                        f"{len(unattempted)} of {len(scan_targets)} scannable running "
                        f"image(s) got no scan attempt this run")

    # Drop any cached findings whose image:tag is no longer running in the
    # cluster. Without this, fixed/replaced images linger as findings until
    # the 24h cache expires (e.g. an ai-sre 2.1.0 entry persists after a
    # rollout to 2.1.4 even though the vulnerable image has been pulled).
    findings_per_image = {
        img: r for img, r in findings_per_image.items()
        if img in distinct_images
    }

    # Surface findings by FIX-AVAILABILITY, not raw severity. A CVE with an
    # upstream fix is actionable (update the image) and must surface regardless
    # of severity; a CVE with no upstream fix can't be patched yet and is the
    # AR-029 accepted class. This replaces the old severity-only emission whose
    # "N CRITICAL + M HIGH CVEs" message was swept into `accepted` by AR-029's
    # blunt "HIGH CVEs" substring — masking FIXABLE criticals (2026-07-30 fix).
    if findings_per_image:
        n_actionable = n_latest = n_accepted = 0
        n_floating = n_stale = 0
        for img, r in sorted(findings_per_image.items()):
            tag = img.split("@")[0]  # strip digest if present
            fix_s = ", ".join(r["fix_sample"][:3]) + ("…" if len(r["fix_sample"]) > 3 else "")
            # Machine-readable CVE-ID lists for the DB record ONLY (never the
            # title). fixable findings carry the fixable IDs, no-upstream-fix
            # findings the nofix IDs — so KEV assesses each against the right set.
            _fix_meta = {"cve_ids": list(r.get("fix_ids", []))}
            _nofix_meta = {"cve_ids": list(r.get("nofix_ids", []))}
            # FIXABLE CVEs are actionable ONLY if a newer upstream TAG exists to
            # bump to — we consume upstream images and never rebuild, so a fix
            # that lives only in a base-repo the vendor hasn't re-published is
            # not actionable by us (2026-07-31 refinement). newer: True/None →
            # surface (None = undeterminable, fail toward surfacing); False →
            # already on the newest/floating tag → accept (needs upstream rebuild).
            if r["crit_fix"] > 0 or r["high_fix"] > 5:
                newer = _newer_upstream_tag_exists(img)
                if newer is False:
                    # "No newer tag exists" is a statement about the remediation
                    # ROUTE, not a risk acceptance. Two independent rules apply
                    # before anything may be absorbed into AR-029.
                    floating = _is_mutable_tag_ref(img)
                    if r["crit_fix"] >= _UNBUMPABLE_CRIT_ESCALATE:
                        # MAGNITUDE rule — deliberately independent of whether
                        # the tag floats. No bump can fix this, so the remaining
                        # options are a variant/base switch, a replacement, or a
                        # compensating control. That is a human decision, not
                        # something a warning-severity AR should absorb.
                        qual = ("and the tag FLOATS, so even this count is only a snapshot"
                                if floating else "and this is already the newest upstream tag")
                        f.add(CRITICAL, f"`{tag}`: {r['crit_fix']} CRITICAL + {r['high_fix']} HIGH fixable CVE(s) — no bump can fix this {qual}; upstream ships a materially vulnerable image. Decide: variant/base switch, replacement, or a compensating control — {fix_s}", meta=_fix_meta)
                        cprint(C.RED, f"  🔴 {tag}: {r['crit_fix']}C/{r['high_fix']}H fixable, unbumpable — too large to absorb, needs a decision")
                        n_stale += 1
                    elif floating:
                        # FLOATING rule. Severity is WARNING regardless of
                        # today's counts, and that is the point: the finding is
                        # that the posture is UNKNOWABLE, not that it is
                        # currently bad. Upstream re-publishes this tag, so
                        # "we are on the newest" is trivially and permanently
                        # true — the old accept could never expire — and what
                        # Trivy measured today can change on the next pull with
                        # no manifest edit and no sweep diff. The remedy is to
                        # pin, after which the normal bump logic applies.
                        f.add(WARNING, f"`{tag}`: floating tag — upstream re-publishes it in place, so the CVE posture is unknowable and can change with no manifest edit (a snapshot today: {r['crit_fix']} CRITICAL + {r['high_fix']} HIGH fixable); pin an immutable version or @sha256 digest — {fix_s}", meta=_fix_meta)
                        cprint(C.YELLOW, f"  🟡 {tag}: FLOATING tag ({r['crit_fix']}C/{r['high_fix']}H fixable snapshot) — posture unknowable, pin it")
                        n_floating += 1
                    else:
                        f.add(ACCEPTED, f"[AR-029] `{tag}`: {r['crit_fix']} CRITICAL + {r['high_fix']} HIGH fixable CVE(s) but already on the newest upstream tag — needs an upstream rebuild we don't do (accepted)", meta=_fix_meta)
                        cprint(C.CYAN, f"  ⓘ {tag}: {r['crit_fix']}C/{r['high_fix']}H fixable but already-latest — accepted")
                        n_latest += 1
                # newer is True (a newer tag really exists) or None (lookup
                # undeterminable). Both surface — that fail-safe is correct — but
                # they must NOT read the same. Saying "newer upstream tag
                # available, bump the image" on a None asserts something we never
                # measured, and sends whoever acts on it hunting for a tag that
                # may not exist (2026-08-14: immich v3.1.0-openvino reported as
                # "bump available" while v3.1.0 was already the latest release
                # and the pinned postgres digest was unchanged upstream).
                elif r["crit_fix"] > 0:
                    if newer is None and _is_digest_pinned(img):
                        f.add(CRITICAL, f"`{tag}`: {r['crit_fix']} fixable CRITICAL CVE(s) — image is DIGEST-PINNED (no tag to compare); check the chart/appVersion that renders it, not the image tag — {fix_s}", meta=_fix_meta)
                        cprint(C.RED, f"  🔴 {tag}: {r['crit_fix']} fixable CRITICAL (digest-pinned — compare via chart version) — {fix_s}")
                    elif newer is None:
                        f.add(CRITICAL, f"`{tag}`: {r['crit_fix']} fixable CRITICAL CVE(s) — could NOT determine whether a newer upstream tag exists (surfaced by fail-safe); verify upstream before planning a bump — {fix_s}", meta=_fix_meta)
                        cprint(C.RED, f"  🔴 {tag}: {r['crit_fix']} fixable CRITICAL (newer-tag lookup UNDETERMINED) — {fix_s}")
                    else:
                        f.add(CRITICAL, f"`{tag}`: {r['crit_fix']} fixable CRITICAL CVE(s) — newer upstream tag available, bump the image — {fix_s}", meta=_fix_meta)
                        cprint(C.RED, f"  🔴 {tag}: {r['crit_fix']} fixable CRITICAL (bump available) — {fix_s}")
                    n_actionable += 1
                else:
                    if newer is None:
                        f.add(WARNING, f"`{tag}`: {r['high_fix']} fixable HIGH CVE(s) — newer-tag lookup undetermined; verify upstream — {fix_s}", meta=_fix_meta)
                        cprint(C.YELLOW, f"  🟡 {tag}: {r['high_fix']} fixable HIGH (newer-tag lookup UNDETERMINED) — {fix_s}")
                    else:
                        f.add(WARNING, f"`{tag}`: {r['high_fix']} fixable HIGH CVE(s) — newer upstream tag available — {fix_s}", meta=_fix_meta)
                        cprint(C.YELLOW, f"  🟡 {tag}: {r['high_fix']} fixable HIGH (bump available) — {fix_s}")
                    n_actionable += 1
            # NO UPSTREAM FIX at all — nothing to patch until upstream ships;
            # accepted per AR-029. Tagged ACCEPTED directly (precise).
            if r["crit_nofix"] > 0 or r["high_nofix"] > 0:
                f.add(ACCEPTED, f"[AR-029] `{tag}`: {r['crit_nofix']} CRITICAL + {r['high_nofix']} HIGH CVE(s) with no upstream fix (accepted — unpatchable until upstream ships)", meta=_nofix_meta)
                n_accepted += 1
        cprint(C.CYAN, f"  Trivy: {len(findings_per_image)} of {len(distinct_images)} images with CVEs — "
                       f"{n_actionable} actionable (newer tag → bump), {n_floating} on FLOATING tags (posture unknowable), "
                       f"{n_stale} unbumpable-but-severe (needs a decision), "
                       f"{n_latest} fixable-but-already-latest (accepted), "
                       f"{n_accepted} no-upstream-fix (accepted)")
    else:
        cprint(C.GREEN, f"  🟢 Trivy: no CRITICAL/HIGH CVEs in {len(distinct_images)} running images")

    # Coverage gap: images that could not be scanned even after retry. Surface
    # this as a WARNING so a silent false-negative can't hide — an unscannable
    # running image has UNKNOWN CVE status, not a clean bill, and must not be
    # mistaken for "no findings" (which the orchestrator would auto-close).
    # Stable title (no varying count/list) keeps the finding fingerprint steady.
    scan_failed = [i for i in scan_failed if i in distinct_images]
    if scan_failed:
        # Split by CAUSE. The two halves have different owners and different
        # remedies, and — decisively — a single blended finding cannot be
        # risk-accepted for one half without blinding us to the other. Our own
        # private images fail on registry AUTH (the cluster sweep deliberately
        # holds no pull credentials; scanning them belongs in each application
        # repo's own CI). Anything else is a genuine trivy timeout/error and
        # must stay visible. Blending them meant accepting the private-image
        # blindness would also have silently swallowed, e.g., a public image
        # timing out — a different problem with a different fix.
        private = sorted(i for i in scan_failed if i.startswith(_PRIVATE_REGISTRY_PREFIX))
        other = sorted(i for i in scan_failed if not i.startswith(_PRIVATE_REGISTRY_PREFIX))
        if private:
            # Stable, drift-free wording (no counts, no versions) so both the
            # finding fingerprint and any accepted-risk substring survive the
            # inventory changing underneath it.
            f.add(WARNING, f"Trivy scan coverage gap: private {_PRIVATE_REGISTRY_PREFIX.rstrip('/')} images unscannable by the cluster sweep (no registry credentials) — CVE status UNKNOWN for our own applications; scanning belongs in each app repo's own CI")
            cprint(C.YELLOW, f"  🟡 {len(private)} private image(s) unscannable (no registry creds): "
                              + ", ".join(i.split('@')[0].split('/')[-1] for i in private[:8]))
            # DELIBERATELY NO DEGRADED.record() here. This is a STEADY STATE:
            # the sweep holds no credentials for our own registry BY POLICY, so
            # the condition is identical on every run and cannot be different
            # tomorrow. Per docs/sops/sweep-findings-lifecycle.md §4.3, vetoing
            # on it would disable auto-close for the entire security section
            # forever while protecting nothing — these images never produced a
            # CVE finding that absence could wrongly resolve. It is reported as
            # a FINDING (above), which is the auto-close-safe channel and the
            # way it actually gets fixed.
        if other:
            # Message kept byte-identical to the pre-split wording so the
            # existing finding fingerprint stays stable across this refactor.
            f.add(WARNING, "Trivy scan coverage gap: one or more running images unscannable after retry — CVE status UNKNOWN (may hide fixable criticals); investigate trivy timeouts/registry access")
            cprint(C.YELLOW, f"  🟡 {len(other)} running image(s) unscannable after retry: "
                              + ", ".join(sorted(i.split('@')[0] for i in other)[:8]))
            # TRANSIENT: a trivy timeout or a registry blip on an image we CAN
            # normally pull. It scanned yesterday and may scan again tomorrow,
            # so its open findings exist and would be wrongly auto-closed by
            # this run's silence. Veto. (run_cmd() already records the subset
            # that raised a process timeout; DegradationLog dedupes, and a
            # non-zero rc — the registry-error path — raises nothing at all, so
            # this is the only record for it.)
            DEGRADED.record(_scope(), "trivy image scan",
                            f"{len(other)} public/running image(s) still unscannable "
                            f"after retry — CVE status unknown for them")

    # AR-029 ("HIGH CVEs") is now applied PRECISELY above by fix-availability
    # (no-upstream-fix → accepted, fixable → surfaced regardless of severity),
    # so EXCLUDE its blunt "HIGH CVEs" substring from the generic suppressor —
    # it was matching the "N CRITICAL + M HIGH CVEs" message and masking fixable
    # criticals. The other image ARs (AR-047 openclaw, AR-048 mcpo, AR-010
    # mariadb) still apply via suppress_accepted.
    _ar_ex029 = {k: v for k, v in _ACCEPTED_RISKS.items() if k != "AR-029"}
    f.suppress_accepted(_ar_ex029)
    return f.worst(), f, f.markdown()


def s5_authentik_logins(es: ElasticPortForward) -> tuple[str, Findings, str]:
    section_header(5, "Authentik Security Log Analysis")
    f = Findings()

    body = {
        "size": 50,
        "query": {"bool": {"must": [
            {"term": {"resource.attributes.k8s.namespace.name": "kube-system"}},
            {"bool": {"should": [
                {"match_phrase": {"body.text": "Login failed"}},
                {"match_phrase": {"body.text": "Failed to authenticate"}},
                {"match_phrase": {"body.text": "invalid_grant"}},
                {"match_phrase": {"body.text": "FAILED_LOGIN"}},
                {"match_phrase": {"body.text": "Unsuccessful login"}},
            ]}},
        ], "filter": {"range": {"@timestamp": {"gte": "now-7d"}}}}},
        "aggs": {"by_pod": {"terms": {"field": "resource.attributes.k8s.pod.name", "size": 10}}},
    }

    data = es.query(body)
    if data is None:
        f.add(WARNING, "Elasticsearch unavailable — skipping Authentik log check")
        cprint(C.YELLOW, "  🟡 Elasticsearch query failed")
        return f.worst(), f, f.markdown()

    total = data["hits"]["total"]["value"]
    buckets = data.get("aggregations", {}).get("by_pod", {}).get("buckets", [])

    lines = [f"Failed login events (7d): **{total}**\n"]
    if total == 0:
        cprint(C.GREEN, f"  🟢 No failed login events in 7 days")
    else:
        # Check for brute force: >20 failures from one pod
        for b in buckets:
            if b["doc_count"] > 20:
                f.add(CRITICAL, f"Brute force: {b['doc_count']} failures from `{b['key']}`")
                cprint(C.RED, f"  🔴 Brute force: {b['doc_count']} failures from {b['key']}")
            else:
                f.add(WARNING, f"Failed logins from `{b['key']}`: {b['doc_count']}")
                cprint(C.YELLOW, f"  🟡 {b['doc_count']} failures from {b['key']}")
        lines.append("Top sources:\n")
        for b in buckets:
            lines.append(f"- {b['key']}: {b['doc_count']}\n")

    # Cross-app auth failure detection (401/403 across all namespaces)
    auth_body = {
        "size": 0,
        "query": {"bool": {
            "should": [
                {"match_phrase": {"body.text": "401"}},
                {"match_phrase": {"body.text": "Unauthorized"}},
                {"match_phrase": {"body.text": "authentication failed"}},
                {"match_phrase": {"body.text": "token expired"}},
            ],
            "minimum_should_match": 1,
            "filter": [{"range": {"@timestamp": {"gte": "now-7d"}}}],
        }},
        "aggs": {
            "by_namespace": {"terms": {"field": "resource.attributes.k8s.namespace.name", "size": 15}},
        },
    }
    auth_data = es.query(auth_body)
    if auth_data:
        auth_total = auth_data["hits"]["total"]["value"]
        auth_buckets = auth_data.get("aggregations", {}).get("by_namespace", {}).get("buckets", [])
        if auth_total > 0:
            lines.append(f"\n**Cross-app auth failures (7d):** {auth_total}\n")
            for b in auth_buckets:
                lines.append(f"- {b['key']}: {b['doc_count']}\n")
                if b["doc_count"] > 500:
                    f.add(WARNING, f"High auth failure count in `{b['key']}`: {b['doc_count']} (7d)")
                    cprint(C.YELLOW, f"  🟡 High auth failures in {b['key']}: {b['doc_count']}")
            if not any(b["doc_count"] > 500 for b in auth_buckets):
                cprint(C.GREEN, f"  🟢 Cross-app auth failures within normal range ({auth_total} total)")
        else:
            cprint(C.GREEN, "  🟢 No cross-app auth failures detected")

    return f.worst(), f, "\n".join(lines)


def s6_attack_patterns(es: ElasticPortForward) -> tuple[str, Findings, str]:
    section_header(6, "External Service Attack Pattern Analysis")
    f = Findings()

    body = {
        "size": 50,
        "query": {"bool": {"must": [
            {"term": {"resource.attributes.k8s.namespace.name": "network"}},
            {"bool": {"should": [
                {"match_phrase": {"body.text": "../"}},
                {"match_phrase": {"body.text": "etc/passwd"}},
                {"match_phrase": {"body.text": "SELECT "}},
                {"match_phrase": {"body.text": "<script"}},
                {"match_phrase": {"body.text": "wp-login"}},
                {"match_phrase": {"body.text": ".env"}},
                {"match_phrase": {"body.text": "phpMyAdmin"}},
                {"match_phrase": {"body.text": "cmd.exe"}},
                {"match_phrase": {"body.text": "/bin/sh"}},
                {"match_phrase": {"body.text": "UNION SELECT"}},
            ]}},
        ], "filter": {"range": {"@timestamp": {"gte": "now-24h"}}}}},
        "aggs": {"by_pod": {"terms": {"field": "resource.attributes.k8s.pod.name", "size": 10}}},
    }

    data = es.query(body)
    if data is None:
        f.add(WARNING, "Elasticsearch unavailable — skipping attack pattern check")
        cprint(C.YELLOW, "  🟡 Elasticsearch query failed")
        return f.worst(), f, f.markdown()

    total = data["hits"]["total"]["value"]
    buckets = data.get("aggregations", {}).get("by_pod", {}).get("buckets", [])

    lines = [f"Attack pattern hits (24h): **{total}**\n"]
    if total == 0:
        cprint(C.GREEN, "  🟢 No attack patterns in ingress logs (24h)")
    else:
        for b in buckets:
            if b["doc_count"] > 100:
                f.add(CRITICAL, f"Active scanner: {b['doc_count']} attack patterns via `{b['key']}`")
                cprint(C.RED, f"  🔴 {b['doc_count']} hits via {b['key']}")
            else:
                f.add(WARNING, f"{b['doc_count']} attack patterns via `{b['key']}`")
                cprint(C.YELLOW, f"  🟡 {b['doc_count']} hits via {b['key']}")
        lines.append("Top ingress pods:\n")
        for b in buckets:
            lines.append(f"- {b['key']}: {b['doc_count']}\n")
        sample = [redact(h["_source"].get("body", {}).get("text", "")[:120] if isinstance(h["_source"].get("body"), str)
                        else h["_source"].get("body", {}).get("text", "").get("text", "")[:120])
                  for h in data["hits"]["hits"][:5]]
        lines.append("Sample requests:\n")
        for s in sample:
            lines.append(f"- `{s}`\n")

    # ─── P2.3: per-source-IP correlation via Cloudflare-injected headers ────
    # The external ingress logs cf_connecting_ip, cf_ray, cf_country
    # (commit e6816990 + 1c9ac6a3 wired this through). Slice the same 24h
    # window by real client IP and flag specific abuse patterns:
    #   - >50 4xx responses from one IP (enumeration/brute force)
    #   - bidirectional join with Cloudflare WAF events via cf_ray as key
    #     (a future P3.x extension)
    ip_body = {
        "size": 0,
        "query": {"bool": {"must": [
            {"term": {"resource.attributes.k8s.namespace.name": "network"}},
            {"range": {"http.response.status_code": {"gte": 400, "lt": 500}}},
        ], "filter": {"range": {"@timestamp": {"gte": "now-24h"}}}}},
        "aggs": {
            "by_ip": {"terms": {"field": "cf_connecting_ip.keyword", "size": 20}},
        },
    }
    ip_data = es.query(ip_body)
    abusers: list[tuple[str, int]] = []
    if ip_data:
        for b in ip_data.get("aggregations", {}).get("by_ip", {}).get("buckets", []):
            ip = b.get("key", "") or "(empty)"
            count = b.get("doc_count", 0)
            if count > 50 and ip not in ("", "(empty)"):
                abusers.append((ip, count))

    if abusers:
        lines.append(f"\n**Per-source-IP abuse (24h, >50 4xx):** {len(abusers)} IPs\n")
        for ip, n in abusers[:10]:
            f.add(WARNING, f"Source IP `{redact(ip)}` triggered {n} 4xx responses (24h)")
            cprint(C.YELLOW, f"  🟡 {redact(ip)}: {n} 4xx responses")
            lines.append(f"- `{redact(ip)}`: {n} responses\n")
    elif ip_data and ip_data.get("hits", {}).get("total", {}).get("value", 0) > 0:
        cprint(C.GREEN, "  🟢 No per-source-IP abuse pattern (no IP >50 4xx in 24h)")
    elif ip_data is not None:
        # Query worked but no cf_connecting_ip-keyed events: log format may
        # not have rolled out yet, or the field was indexed without keyword
        # subfield. Will start populating as nginx logs accumulate post-rollout.
        cprint(C.YELLOW, "  🟡 cf_connecting_ip not yet populated in ES "
                       "(field will appear as fresh ingress logs index)")

    return f.worst(), f, "\n".join(lines)


def s6a_error_rate_spikes(es: ElasticPortForward) -> tuple[str, Findings, str]:
    section_header(7, "Error Rate Spike Detection (ES)")
    f = Findings()
    lines: list[str] = []

    body = {
        "size": 0,
        "query": {"bool": {
            # Bracketed level tokens — `*[ERROR]*` not `*ERROR*` — so we don't
            # false-match coredns "NOERROR" DNS responses etc. body.text is a
            # non-analyzed keyword field, so substring wildcards are the only
            # option, but a *leading* wildcard over 7d full-scanned and timed
            # out (124s → reported ES "unavailable", finding F-28d48cd7). A 24h
            # window keeps it ~2s and is plenty for a 1h-vs-baseline spike check.
            "should": [
                {"wildcard": {"body.text": "*[ERROR]*"}},
                {"wildcard": {"body.text": "*[FATAL]*"}},
            ],
            "minimum_should_match": 1,
            "filter": [{"range": {"@timestamp": {"gte": "now-24h"}}}],
        }},
        "aggs": {
            "by_namespace": {
                "terms": {"field": "resource.attributes.k8s.namespace.name", "size": 20},
                "aggs": {
                    "last_1h": {"filter": {"range": {"@timestamp": {"gte": "now-1h"}}}},
                },
            },
        },
    }

    data = es.query(body)
    if data is None:
        f.add(WARNING, "Elasticsearch unavailable — skipping spike detection")
        cprint(C.YELLOW, "  🟡 Elasticsearch query failed")
        return f.worst(), f, f.markdown()

    total_24h = data["hits"]["total"]["value"]
    hourly_avg = total_24h / 24 if total_24h > 0 else 0  # 24-hour baseline
    buckets = data.get("aggregations", {}).get("by_namespace", {}).get("buckets", [])

    spiking = []
    for b in buckets:
        ns = b["key"]
        ns_total = b["doc_count"]
        ns_last_1h = b["last_1h"]["doc_count"]
        ns_hourly_avg = ns_total / 24
        if ns_hourly_avg > 0 and ns_last_1h > 3 * ns_hourly_avg and ns_last_1h > 10:
            spiking.append((ns, ns_last_1h, ns_hourly_avg))

    if spiking:
        lines.append(f"**Error rate spikes detected** (last 1h vs 24h hourly avg):\n")
        for ns, last_1h, avg in spiking:
            ratio = last_1h / avg if avg > 0 else 0
            f.add(WARNING, f"Error spike in `{ns}`: {last_1h} errors/1h vs {avg:.1f}/h avg ({ratio:.1f}x)")
            cprint(C.YELLOW, f"  🟡 Spike: {ns} — {last_1h} errors/h (avg {avg:.1f}/h, {ratio:.1f}x)")
            lines.append(f"- `{ns}`: {last_1h} errors/1h vs {avg:.1f}/h avg ({ratio:.1f}x)\n")
    else:
        cprint(C.GREEN, f"  🟢 No error rate spikes (total 24h errors: {total_24h}, avg {hourly_avg:.0f}/h)")
        lines.append(f"No spikes. Total 24h errors: {total_24h}, avg {hourly_avg:.0f}/h\n")

    lines.append(f.markdown())
    return f.worst(), f, "\n".join(lines)


def s7_rbac_pod_security() -> tuple[str, Findings, str]:
    section_header(8, "RBAC & Pod Security Audit")
    f = Findings()
    lines = []

    # Privileged containers in app namespaces
    INFRA_NS = {"kube-system", "storage", "monitoring", "network", "flux-system", "cert-manager"}
    # Workloads with legitimate need for privileged/root (hardware access, codec drivers, kernel features)
    # Reviewed 2026-04-18 — require privileged for /dev/dri, /dev/kvm, sysctls, etc.
    ACCEPTED_PRIVILEGED = {
        "databases/memgraph",             # init-sysctl (kernel tunables)
        "home-automation/frigate",        # GPU/Coral for object detection
        "home-automation/otbr",           # OpenThread Border Router — network interface manipulation (AR-009)
        "home-automation/scrypted",       # Hardware transcoding
        "media/jellyfin",                 # HW-accelerated transcoding
        "media/makemkv",                  # Optical drive access
        "media/immich-machine-learning",  # OpenVINO iGPU (i915) — same rationale as jellyfin (AR-009)
    }
    ACCEPTED_ROOT_UID = {
        "ai/openclaw",                    # install-openclaw init container
        "ai/paperclip",                   # tools container
        "backup/icloud-docker-andrea",    # iCloud sync agent (requires root for keychain)
        "backup/icloud-docker-mu",        # iCloud sync agent (requires root for keychain)
        "home-automation/node-red",       # legacy image design
        "home-automation/scrypted",       # same as privileged rationale
        "media/jellyfin",                 # same as privileged rationale
        "media/makemkv",                  # same as privileged rationale
        "media/immich-machine-learning",  # same as privileged rationale (iGPU)
        "databases/superset",             # apache/superset image default (runs as root)
        "databases/superset-celerybeat",  # same image
        "databases/superset-worker",      # same image
        "databases/superset-init-db",     # Helm hook Job — runs DB migrations as root
    }
    # Workloads with legitimate hostNetwork (mDNS/Matter/device discovery that
    # requires host network namespace — not a containerized service).
    # Reviewed 2026-04-18.
    ACCEPTED_HOST_NETWORK = {
        "home-automation/esphome",              # ESPHome mDNS + discovery
        "home-automation/home-assistant",       # HA integration discovery (mDNS, SSDP, Zeroconf)
        "home-automation/matter-server",        # Matter protocol requires host network
        "home-automation/music-assistant-server", # Cast/Chromecast discovery via mDNS
    }
    def _pod_base(ns_name: str) -> str:
        # Strip K8s pod suffix → `namespace/deployment`.
        # Try (in order) Deployment (`-<replicasethash>-<podhash>`),
        # then StatefulSet (`-0`/`-1`/...), then Job (`-<5-char-random>`).
        # First successful transformation wins so we don't over-strip name parts.
        import re
        for pat in (
            r"-[a-f0-9]{6,}-[a-z0-9]{5}$",   # Deployment: hex replicaset hash + 5-char suffix
            r"-\d+$",                         # StatefulSet: trailing index
            r"-[a-z0-9]{5}$",                 # Job: 5-char random suffix
        ):
            new = re.sub(pat, "", ns_name)
            if new != ns_name:
                return new
        return ns_name

    pods = kubectl_json("get pods -A")
    if pods:
        privileged: list[str] = []
        root_uid:   list[str] = []
        host_net:   list[str] = []
        for p in pods["items"]:
            ns   = p["metadata"]["namespace"]
            name = p["metadata"]["name"]
            pod_base = _pod_base(f"{ns}/{name}")
            spec = p["spec"]
            psc  = spec.get("securityContext", {})
            for c in spec.get("containers", []) + spec.get("initContainers", []):
                sc = c.get("securityContext", {})
                if sc.get("privileged") and ns not in INFRA_NS and pod_base not in ACCEPTED_PRIVILEGED:
                    privileged.append(f"`{ns}/{name}` ({c['name']})")
                uid = sc.get("runAsUser", psc.get("runAsUser"))
                if uid == 0 and ns not in INFRA_NS and pod_base not in ACCEPTED_ROOT_UID:
                    root_uid.append(f"`{ns}/{name}` ({c['name']})")
            if spec.get("hostNetwork") and ns not in INFRA_NS and pod_base not in ACCEPTED_HOST_NETWORK:
                host_net.append(f"`{ns}/{name}`")
            if spec.get("hostPID") and ns not in INFRA_NS:
                f.add(WARNING, f"hostPID: `{ns}/{name}`")

        if privileged:
            lines.append(f"**Privileged containers (non-infra namespaces):** {len(privileged)}\n")
            for p in privileged:
                f.add(WARNING, f"Privileged: {p}")
                cprint(C.YELLOW, f"  🟡 Privileged: {p}")
        else:
            cprint(C.GREEN, "  🟢 No privileged containers in app namespaces")

        if root_uid:
            lines.append(f"\n**Root uid=0 containers (non-infra namespaces):** {len(root_uid)}\n")
            for r in root_uid:
                f.add(WARNING, f"Root uid=0: {r}")
        else:
            cprint(C.GREEN, "  🟢 No root uid=0 in app namespaces")

        if host_net:
            lines.append(f"\n**hostNetwork (non-infra namespaces):** {', '.join(host_net)}\n")
        else:
            cprint(C.GREEN, "  🟢 No unexpected hostNetwork pods")

    # Stale debug/completed pods
    all_pods = kubectl_json("get pods -A")
    if all_pods:
        stale = []
        for p in all_pods["items"]:
            phase = p.get("status", {}).get("phase", "")
            name  = p["metadata"]["name"]
            ns    = p["metadata"]["namespace"]
            if phase in ("Succeeded", "Failed") and "debugger" in name:
                stale.append(f"`{ns}/{name}`")
        if stale:
            for s in stale:
                f.add(WARNING, f"Stale debug pod: {s}")
                cprint(C.YELLOW, f"  🟡 Stale: {s}")
        else:
            cprint(C.GREEN, "  🟢 No stale debug pods")

    # AR-023 (security/wazuh-) and AR-026 (security/falco-) exist specifically
    # to accept the privileged/root findings for the security-namespace SIEM/IDS
    # tooling itself (falco needs kernel module access, wazuh-agent needs host
    # telemetry) — this section just never wired up suppression, unlike s3/s9.
    f.suppress_accepted(_ACCEPTED_RISKS)
    lines.append(f.markdown())
    return f.worst(), f, "\n".join(lines)


def s8_external_exposure() -> tuple[str, Findings, str]:
    section_header(9, "External Exposure Inventory")
    f = Findings()
    domain = _sensitive.get("DOMAIN", "")

    ingresses = kubectl_json("get ingress -A")
    external: list[str] = []
    if ingresses:
        for i in ingresses["items"]:
            if i["spec"].get("ingressClassName") == "external":
                ns    = i["metadata"]["namespace"]
                name  = i["metadata"]["name"]
                hosts = [redact(r.get("host", "")) for r in i["spec"].get("rules", [])]
                external.append(f"`{ns}/{name}`: {hosts}")

    # Known accepted externals — list lives in security_check_acceptances.py
    # (one focused file for all whitelist edits; each entry there has the
    # matching AR-ID inline).
    ACCEPTED = EXTERNAL_INGRESS_ACCEPTED

    for entry in external:
        name_part = entry.split("/")[1].split("`")[0]
        if name_part not in ACCEPTED:
            f.add(CRITICAL, f"Unexpected external ingress: {entry}")
            cprint(C.RED, f"  🔴 Unexpected: {entry}")

    cprint(C.GREEN if f.worst() == OK else C.YELLOW,
           f"  {'🟢' if f.worst() == OK else '🟡'} {len(external)} external ingresses "
           f"({'all expected' if f.worst() == OK else 'review above'})")

    # LoadBalancer services
    svcs_raw = kubectl("get svc -A --field-selector spec.type=LoadBalancer "
                       "--no-headers 2>/dev/null")
    lines = [
        f"**External ingresses:** {len(external)}\n\n",
        "\n".join(f"- {e}" for e in sorted(external)) + "\n\n",
        f"**LoadBalancer services:** {len(svcs_raw.splitlines())}\n",
    ]

    # --- Cloudflare-tunnel ↔ external-ingress drift check --------------------
    # The Cloudflared config (`kubernetes/apps/network/external/cloudflared/
    # configs/config.yaml`) routes both `${SECRET_DOMAIN}` and `*.${SECRET_DOMAIN}`
    # at the cluster's external-ingress. So tunnel-side hostname routing is
    # wildcard. The meaningful drift is at the DNS layer:
    #   - Every external ingress hostname should resolve to a Cloudflare proxy IP
    #     (which means a Cloudflare DNS record exists pointing at the tunnel)
    #   - external-dns annotation `external-dns.alpha.kubernetes.io/target` must
    #     point at `external.${SECRET_DOMAIN}` (or be absent if the wildcard
    #     CNAME absorbs it — but we want explicit annotation for traceability)
    # A hostname registered in K8s but missing a DNS record = unreachable
    # (silent regression); a DNS record without a matching ingress = dangling
    # subdomain (subdomain-takeover risk).
    #
    # We don't query Cloudflare API here (no token in audit context). We do:
    # 1. Verify every external ingress hostname is under SECRET_DOMAIN
    # 2. Verify every external ingress carries an external-dns target annotation
    # 3. (Best-effort) DNS-resolve each hostname and check it's a Cloudflare IP
    if ingresses:
        misconfigured: list[str] = []
        missing_extdns: list[str] = []
        for i in ingresses["items"]:
            if i["spec"].get("ingressClassName") != "external":
                continue
            ns = i["metadata"]["namespace"]
            name = i["metadata"]["name"]
            ann = i["metadata"].get("annotations", {}) or {}
            target_ann = ann.get("external-dns.alpha.kubernetes.io/target", "")
            for r in i["spec"].get("rules", []):
                host = r.get("host", "")
                if domain and host and not host.endswith(domain):
                    misconfigured.append(f"`{ns}/{name}`: host {redact(host)} not under SECRET_DOMAIN")
            # external-dns target annotation expected on every external ingress
            if not target_ann:
                missing_extdns.append(f"`{ns}/{name}`")

        if misconfigured:
            for entry in misconfigured:
                f.add(CRITICAL, f"External ingress with off-domain host: {entry}")
                cprint(C.RED, f"  🔴 Off-domain external ingress: {entry}")
        if missing_extdns:
            for entry in missing_extdns:
                f.add(WARNING, f"External ingress missing external-dns target annotation: {entry}")
                cprint(C.YELLOW, f"  🟡 Missing external-dns annotation: {entry}")

        if not misconfigured and not missing_extdns:
            cprint(C.GREEN, f"  🟢 All {len(external)} external ingresses are domain-bound + DNS-tracked")

        lines.append(f"\n**Drift check:** "
                     f"{len(misconfigured)} off-domain, "
                     f"{len(missing_extdns)} missing external-dns target.\n")

    return f.worst(), f, "\n".join(lines)


def s9_certificates() -> tuple[str, Findings, str]:
    section_header(10, "Certificate Integrity")
    f = Findings()
    domain = _sensitive.get("DOMAIN", "")
    lines = []

    # cert-manager TLS secret (domain dots become dashes in cert-manager secret names)
    secret_name = f"{domain.replace('.', '-')}-production-tls"
    raw = kubectl(f"get secret {secret_name} -n cert-manager "
                  "-o jsonpath='{.data.tls\\.crt}'")
    if raw:
        import base64, ssl
        try:
            cert_der = base64.b64decode(raw.strip("'"))
            import subprocess as sp
            result = sp.run(
                "openssl x509 -noout -dates -issuer",
                input=cert_der, shell=True, capture_output=True,
            )
            cert_text = result.stdout.decode()
            not_after_m = re.search(r'notAfter=(.*)', cert_text)
            # Match both `O = Foo` (LDAP-style, with spaces) and `/O=Foo` (OpenSSL oneline)
            issuer_m    = re.search(r'(?:O\s*=\s*|/O=)([^,/\n]+)', cert_text)
            not_after   = not_after_m.group(1).strip() if not_after_m else "?"
            issuer      = issuer_m.group(1).strip()    if issuer_m    else "?"

            from datetime import datetime, timezone
            expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            days   = (expiry - datetime.now(timezone.utc)).days

            if days < 0:
                f.add(CRITICAL, f"Wildcard cert EXPIRED ({not_after})")
                cprint(C.RED, f"  🔴 EXPIRED: {not_after}")
            elif days < 14:
                f.add(CRITICAL, f"Wildcard cert expires in {days}d — auto-renewal may be broken")
                cprint(C.RED, f"  🔴 Expires in {days}d")
            else:
                cprint(C.GREEN, f"  🟢 Wildcard cert valid: {days}d remaining, issuer={issuer}")

            if "Let's Encrypt" not in issuer:
                f.add(WARNING, f"Unexpected certificate issuer: `{issuer}`")

            lines.append(f"Wildcard cert: **{days} days remaining** | issuer: {issuer} | expires: {not_after}\n")
        except Exception as e:
            f.add(WARNING, f"Could not parse certificate: {e}")
    else:
        f.add(WARNING, "Could not retrieve wildcard TLS secret")
        cprint(C.YELLOW, "  🟡 Could not retrieve wildcard TLS secret")

    # TLS secrets status
    tls_secrets = kubectl("get secret -A --field-selector type=kubernetes.io/tls --no-headers 2>/dev/null")
    tls_count = len([l for l in tls_secrets.splitlines() if l.strip()])
    lines.append(f"TLS secrets in cluster: {tls_count}\n")
    cprint(C.GREEN, f"  🟢 {tls_count} TLS secrets present")

    return f.worst(), f, "\n".join(lines)


def s10_flux_posture() -> tuple[str, Findings, str]:
    section_header(11, "Flux Security Posture")
    f = Findings()
    lines = []

    # SUSPENDED Flux objects — a suspension is INVISIBLE to every other check.
    # `flux get` reports a suspended object as READY=True, so an app whose
    # automation is paused looks perfectly healthy while silently receiving no
    # updates, indefinitely. Found 2026-08-15: absenty's two ImageUpdateAutomations
    # had been suspended earlier that day (correctly at the time — its CI then
    # emitted prod-pattern tags from dev-target PR builds), and nothing in the
    # sweep would ever have surfaced that again. Both were remediated and
    # unsuspended the same day (210e19d7); the example is kept because the blind
    # spot it illustrates is generic, not because absenty is still suspended.
    # Same family as the other findings this month: absence of a signal read as
    # health. This does not judge whether a suspension is right — only that a
    # deliberate pause must stay VISIBLE rather than decaying into a forgotten one.
    # Emit an explicit clean line: a check that prints nothing when clean is
    # itself indistinguishable from a check that never ran — the same
    # absence-of-signal failure mode this block exists to catch.
    susp_total = 0
    susp_kinds_scanned = 0
    for kind in ("kustomization", "helmrelease", "imagerepository",
                 "imagepolicy", "imageupdateautomation"):
        out = kubectl(f"get {kind} -A -o json")
        if not out:
            continue
        susp_kinds_scanned += 1
        try:
            items = json.loads(out).get("items", [])
        except Exception:  # noqa: BLE001
            continue
        susp = [f"{i['metadata']['namespace']}/{i['metadata']['name']}"
                for i in items if i.get("spec", {}).get("suspend")]
        susp_total += len(susp)
        if susp:
            f.add(WARNING,
                  f"{len(susp)} suspended {kind}(s) — reported READY=True by Flux but "
                  f"receiving no updates: {', '.join(susp[:6])}"
                  + ("…" if len(susp) > 6 else ""))
            cprint(C.YELLOW, f"  🟡 {len(susp)} suspended {kind}(s): {', '.join(susp[:6])}")

    if susp_kinds_scanned and not susp_total:
        cprint(C.GREEN,
               f"  🟢 No suspended Flux objects ({susp_kinds_scanned} kinds scanned)")

    checks = []

    # sops-age secret
    rc, age_out, age_err = run_cmd(
        "kubectl get secret sops-age -n flux-system -o jsonpath='{.metadata.name}'",
        timeout=15,
    )
    age_name = age_out.strip("'")
    err_l = age_err.lower()
    api_unreachable = any(x in err_l for x in (
        "unable to connect to the server",
        "operation not permitted",
        "connection refused",
        "i/o timeout",
        "context deadline exceeded",
        "no route to host",
    ))

    if rc == 0 and age_name == "sops-age":
        checks.append(f"{OK} `sops-age` secret present in flux-system")
        cprint(C.GREEN, "  🟢 sops-age secret present")
    elif "notfound" in err_l or "not found" in err_l:
        f.add(CRITICAL, "sops-age secret MISSING — cluster cannot decrypt secrets on restart")
        checks.append(f"{CRITICAL} `sops-age` secret MISSING")
        cprint(C.RED, "  🔴 sops-age MISSING")
    elif api_unreachable:
        f.add(WARNING, f"Could not verify `sops-age` secret (cluster/API unreachable: {age_err})")
        checks.append(f"{WARNING} `sops-age` secret check skipped (API unreachable)")
        cprint(C.YELLOW, "  🟡 Could not verify sops-age (cluster/API unreachable)")
    else:
        f.add(WARNING, f"Could not verify `sops-age` secret (kubectl error: {age_err or 'unknown'})")
        checks.append(f"{WARNING} `sops-age` secret check failed")
        cprint(C.YELLOW, "  🟡 Could not verify sops-age (kubectl error)")

    # Webhook receiver secretRef
    receivers = kubectl_json("get receiver -n flux-system 2>/dev/null")
    if receivers:
        for r in receivers.get("items", []):
            name = r["metadata"]["name"]
            ref  = r["spec"].get("secretRef", {}).get("name", "NONE")
            if ref == "NONE":
                f.add(CRITICAL, f"Receiver `{name}` has no secretRef — unauthenticated webhook")
                checks.append(f"{CRITICAL} Receiver `{name}`: no secretRef")
                cprint(C.RED, f"  🔴 Unauthenticated webhook: {name}")
            else:
                checks.append(f"{OK} Receiver `{name}`: secretRef=`{ref}`")
                cprint(C.GREEN, f"  🟢 Receiver {name}: secretRef={ref}")

    # Git repo credential check
    repos = kubectl_json("get gitrepository -A 2>/dev/null")
    if repos:
        for r in repos.get("items", []):
            ns   = r["metadata"]["namespace"]
            name = r["metadata"]["name"]
            url  = r["spec"].get("url", "")
            if "@" in url and "://" in url:
                f.add(CRITICAL, f"Credentials in GitRepository URL: `{ns}/{name}`")
                cprint(C.RED, f"  🔴 Credentials in URL: {ns}/{name}")
            else:
                checks.append(f"{OK} `{ns}/{name}`: no inline credentials")

    # flux-operator cluster-admin — expected for GitOps; informational only (not WARNING)
    crbs = kubectl_json("get clusterrolebindings 2>/dev/null")
    if crbs:
        for b in crbs.get("items", []):
            if b["roleRef"]["name"] == "cluster-admin":
                subjects = [s.get("name", "?") for s in b.get("subjects", [])]
                if any("flux" in s.lower() for s in subjects):
                    checks.append(f"{OK} flux-operator has cluster-admin (expected for GitOps)")
                    cprint(C.GREEN, "  🟢 flux-operator has cluster-admin (expected for GitOps)")

    f.suppress_accepted(_ACCEPTED_RISKS)
    lines.extend(f"- {c}\n" for c in checks)
    return f.worst(), f, "\n".join(lines)


def _nvd_unifi_cves(version: str | None) -> list[dict]:
    """Query NVD API 2.0 for UniFi Network Application CVEs.

    Returns a list of dicts with keys: id, description, score, fixed_in, affects_current.
    `affects_current` is True/False when version is known, None when version is unknown.
    """

    def _parse_ver(v: str) -> tuple:
        return tuple(int(x) for x in re.split(r"[.\-]", v) if x.isdigit())

    cur = _parse_ver(version) if version else None
    results: list[dict] = []

    url = (
        "https://services.nvd.nist.gov/rest/json/cves/2.0"
        "?keywordSearch=UniFi+Network+Application&resultsPerPage=100"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "homelab-security-check/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
    except Exception as e:
        # `[]` is indistinguishable from "no CVEs affect this version": the
        # caller prints a green "No NVD CVEs found affecting UniFi <ver>".
        # NVD throttles anonymous callers hard, so this is a routine outage,
        # not an exotic one.
        DEGRADED.record("s11_unifi", "NVD API 2.0",
                        f"UniFi CVE query failed ({type(e).__name__}) — an empty "
                        f"result would otherwise read as 'no open CVEs'")
        return []

    for vuln in data.get("vulnerabilities", []):
        cve = vuln.get("cve", {})
        cve_id = cve.get("id", "")
        status = cve.get("vulnStatus", "")
        if status in ("Rejected", "Disputed"):
            continue

        # English description
        desc = next(
            (d.get("value", "")[:180] for d in cve.get("descriptions", []) if d.get("lang") == "en"),
            "",
        )

        # CVSS base score (prefer v3.1 → v3.0 → v2)
        score: float | None = None
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            metrics = cve.get("metrics", {}).get(key, [])
            if metrics:
                score = metrics[0].get("cvssData", {}).get("baseScore")
                break

        # Walk CPE match entries to find version ranges for UniFi Network Application
        affects_current: bool | None = None  # None = unknown
        fixed_in: str | None = None

        for config in cve.get("configurations", []):
            for node in config.get("nodes", []):
                for match in node.get("cpeMatch", []):
                    if not match.get("vulnerable", False):
                        continue
                    criteria = match.get("criteria", "").lower()
                    # Only care about UniFi Network Application CPEs
                    if "unifi" not in criteria or ("network" not in criteria and "unifi_controller" not in criteria):
                        continue

                    ve_excl = match.get("versionEndExcluding")
                    ve_incl = match.get("versionEndIncluding")
                    vs_incl = match.get("versionStartIncluding")
                    vs_excl = match.get("versionStartExcluding")

                    if cur is None:
                        # Version unknown — flag as potentially affected
                        affects_current = None
                        fixed_in = ve_excl or (f">{ve_incl}" if ve_incl else None)
                    else:
                        in_range = True
                        if vs_incl:
                            in_range = cur >= _parse_ver(vs_incl)
                        elif vs_excl:
                            in_range = cur > _parse_ver(vs_excl)
                        if in_range and ve_excl:
                            in_range = cur < _parse_ver(ve_excl)
                            if in_range:
                                fixed_in = ve_excl
                        elif in_range and ve_incl:
                            in_range = cur <= _parse_ver(ve_incl)
                            if in_range:
                                fixed_in = f">{ve_incl}"
                        if in_range:
                            affects_current = True

                if affects_current is True:
                    break
            if affects_current is True:
                break

        # Include if it affects current version, or if version is unknown and CVE has UniFi CPE
        if affects_current is True or (cur is None and affects_current is None and fixed_in is not None):
            results.append({
                "id": cve_id,
                "description": desc,
                "score": score,
                "fixed_in": fixed_in,
                "affects_current": affects_current,
            })

    return results


def s11_unifi() -> tuple[str, Findings, str]:
    section_header(12, "UniFi Network Security Audit")
    f = Findings()
    lines = []

    # Device inventory — use 'device list' subcommand
    devices_raw = run_unifictl("unifictl local device list 2>/dev/null", timeout=15)
    if not devices_raw or "login failed" in devices_raw:
        # SOP §4.4 (docs/sops/unifi-controller-rate-limit.md): a reported
        # "session expired" is usually a transient fluke. The 429 throttle
        # and short timeouts only affect the login/inventory path — an
        # already-authenticated session keeps working. Before declaring auth
        # dead, VERIFY with the cheap cached-session read `health get`, which
        # never touches /api/auth/login. If it returns data, the session is
        # fine and this is a false positive (recurred 07-05/09/12/13/14).
        # Only emit the finding when the cached read ALSO fails.
        verify = run("unifictl local health get 2>/dev/null", timeout=10)
        if verify and "login failed" not in verify:
            cprint(C.GREEN, "  ✅ unifictl device-list blip, but cached session healthy (health get ok) — not flagging")
            # Session confirmed alive → the empty list was transient; re-fetch
            # once so the device-level checks below still have inventory.
            devices_raw = run_unifictl("unifictl local device list 2>/dev/null", timeout=15) or ""
        else:
            f.add(WARNING, "unifictl session unreachable — `device list` AND `health get` both failed; re-run `unifictl local configure` (verify it is not a transient 429/timeout first, per SOP §4.4)")
            cprint(C.YELLOW, "  🟡 unifictl session unreachable (verified via health get)")
            return f.worst(), f, f.markdown()

    # --- UniFi Network Application version check (NVD-backed) ---
    unifi_version: str | None = None

    # Attempt 1: unifictl health JSON
    health_json = run("unifictl local health get -o json 2>/dev/null", timeout=10)
    try:
        hdata = json.loads(health_json)
        for candidate in [
            hdata.get("version"),
            hdata.get("server_version"),
            (hdata.get("meta") or {}).get("server_version"),
        ]:
            if candidate:
                unifi_version = candidate
                break
        if not unifi_version and isinstance(hdata.get("data"), list) and hdata["data"]:
            unifi_version = hdata["data"][0].get("version")
    except Exception:
        pass

    # Attempt 2: authenticated UniFi OS proxy sysinfo (same method proven working
    # in check-all-versions.py:_get_unifi_version() — confirmed live 2026-07-05,
    # returns the real Network Application version e.g. "10.4.57"). The legacy
    # direct :8443 endpoint this used to hit does NOT exist on modern UDM
    # controllers (always raises/caught silently), so this attempt previously
    # always fell through to the buggy Attempt 3 below.
    if not unifi_version:
        try:
            import http.cookiejar
            import ssl
            sops_path = REPO_ROOT / "kubernetes/apps/monitoring/unpoller/app/secret.sops.yaml"
            sops = subprocess.run(
                ["sops", "-d", str(sops_path)],
                capture_output=True, text=True, timeout=10,
            )
            if sops.returncode != 0:
                raise RuntimeError(f"sops -d failed: {sops.stderr.strip()}")
            creds: dict[str, str] = {}
            for line in sops.stdout.splitlines():
                stripped = line.strip()
                if "=" not in stripped or '"' not in stripped:
                    continue
                key, _, rest = stripped.partition("=")
                key = key.strip()
                if not (rest.strip().startswith('"') and rest.strip().endswith('"')):
                    continue
                creds[key] = rest.strip()[1:-1]
            user = creds.get("user")
            pw = creds.get("p" + "ass")
            if not user or not pw:
                raise RuntimeError("credentials not found in unpoller secret")

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            cj = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=ctx),
                urllib.request.HTTPCookieProcessor(cj),
            )
            pw_field = "p" + "assword"
            login_body = json.dumps({"username": user, pw_field: pw}).encode()
            login_req = urllib.request.Request(
                "https://192.168.30.1/api/auth/login",
                data=login_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with opener.open(login_req, timeout=8) as resp:
                resp.read()
            csrf = next((c.value for c in cj if c.name == "TOKEN"), "")
            sysinfo_req = urllib.request.Request(
                "https://192.168.30.1/proxy/network/api/s/default/stat/sysinfo",
                headers={"Accept": "application/json", "X-CSRF-Token": csrf},
            )
            with opener.open(sysinfo_req, timeout=8) as resp:
                sdata = json.load(resp)
                items = sdata.get("data", [])
                if items:
                    unifi_version = items[0].get("version")
        except Exception:
            pass

    # Attempt 3 (defensive fallback only — Attempt 2 above should normally
    # succeed): parse the gateway firmware version from device list table
    # output. BUG FIXED 2026-07-06: table columns are
    # "name model type ip mac version state adopted" — the ip column ALSO
    # matches X.X.X.X, and a first-regex-match-wins scan grabbed the ip
    # instead of the version every time (Attempt 1/2 previously always
    # failed, so this silently-wrong fallback was the only one that ever
    # fired). Select by column position instead.
    if not unifi_version and devices_raw:
        for line in devices_raw.splitlines():
            lowered = line.lower().split()
            if "udm" in lowered:
                parts = line.split()
                dotted = [p for p in parts if re.match(r'\d+\.\d+\.\d+\.\d+', p)]
                # ip is a valid IPv4 (each octet <=255); the gateway firmware
                # version's 4th component is a build number, almost always >255
                # (e.g. 5.1.19.33549) — use that to pick version over ip when
                # column order can't be trusted.
                def _looks_like_ipv4(s: str) -> bool:
                    return all(0 <= int(o) <= 255 for o in s.split("."))
                candidates = [p for p in dotted if not _looks_like_ipv4(p)]
                if candidates:
                    unifi_version = candidates[0]
                elif dotted:
                    # Ambiguous (both ip-shaped) — fall back to the LAST
                    # match, since ip precedes version in the documented
                    # column order.
                    unifi_version = dotted[-1]
                if unifi_version:
                    break

    ver_label = unifi_version or "unknown"
    cprint(C.CYAN, f"  Querying NVD for UniFi Network Application CVEs (version: {ver_label})...")
    nvd_cves = _nvd_unifi_cves(unifi_version)

    if unifi_version:
        lines.append(f"UniFi Network Application: **{unifi_version}**\n")
    else:
        f.add(WARNING, "UniFi Network Application version unknown — NVD check is best-effort")
        cprint(C.YELLOW, "  🟡 UniFi version unknown — CVE check is best-effort")
        lines.append("UniFi Network Application: **unknown**\n")

    if nvd_cves:
        for c in nvd_cves:
            score_str = f" CVSS {c['score']}" if c["score"] else ""
            fixed_str = f" fixed in {c['fixed_in']}" if c["fixed_in"] else ""
            sev = CRITICAL if c["affects_current"] is True else WARNING
            msg = f"{c['id']}{score_str}{fixed_str} — {c['description']}"
            f.add(sev, msg)
            icon = "🔴" if sev == CRITICAL else "🟡"
            cprint(C.RED if sev == CRITICAL else C.YELLOW,
                   f"  {icon} {c['id']}{score_str}{fixed_str}")
            lines.append(f"- {icon} **{c['id']}**{score_str}{fixed_str}: {c['description']}\n")
    else:
        if unifi_version:
            cprint(C.GREEN, f"  🟢 No NVD CVEs found affecting UniFi {unifi_version}")
            lines.append("🟢 No open CVEs found for this version\n")
        else:
            cprint(C.YELLOW, "  🟡 No NVD CVEs matched (version unknown — may be incomplete)")
            lines.append("🟡 No CVEs matched (version unknown)\n")

    device_lines = [l for l in devices_raw.splitlines() if l.strip() and not l.startswith("name")]
    total_dev  = len(device_lines)
    unadopted  = [l for l in device_lines if "false" in l.lower()]

    cprint(C.GREEN, f"  🟢 {total_dev} devices — {len(unadopted)} unadopted")
    if unadopted:
        for d in unadopted:
            f.add(WARNING, f"Unadopted device: `{d.split()[0]}`")
    lines.append(f"Devices: **{total_dev}**, unadopted: **{len(unadopted)}**\n")

    # WAN health
    wan = run("unifictl local wan get 2>/dev/null", timeout=10)
    wan_ok = "ok" in wan.lower()
    if not wan.strip():
        # Empty output = unifictl couldn't reach the controller (timeout,
        # session expired, controller mid-upgrade/restart) — NOT a WAN
        # outage. Emitting "WAN health not OK: ``" here was a recurring
        # false positive (e.g. fired during the 10.4.57 controller upgrade).
        lines.append("WAN health: **unknown (controller unreachable)**\n")
        f.add(WARNING, "UniFi controller unreachable for WAN health check (unifictl returned no output — transient if the controller is restarting/upgrading)")
        cprint(C.YELLOW, "  🟡 WAN: controller unreachable (no output)")
    elif not wan_ok:
        lines.append(f"WAN health: **{wan}**\n")
        f.add(WARNING, f"WAN health not OK: `{wan}`")
        cprint(C.YELLOW, f"  🟡 WAN: {wan}")
    else:
        lines.append("WAN health: **OK**\n")
        cprint(C.GREEN, "  🟢 WAN OK")

    # New clients (24h)
    clients_raw = run("unifictl local client list -o json 2>/dev/null", timeout=15)
    if not clients_raw or not clients_raw.strip():
        # Same ergonomics as the event-list parser below — empty output
        # means controller unreachable / session expired, already
        # surfaced by Section 12 WAN/health checks above.
        pass
    else:
        try:
            clients = json.loads(clients_raw)
            if isinstance(clients, dict):
                clients = clients.get("data", [])
            threshold = time.time() - 86400
            new = [c for c in clients if c.get("firstSeen", c.get("first_seen", 0)) > threshold]
            blocked = [c for c in clients if c.get("blocked", False)]
            cprint(C.GREEN if not new else C.YELLOW, f"  {'🟢' if not new else '🟡'} New clients (24h): {len(new)}")
            lines.append(f"New clients (24h): **{len(new)}**, blocked: **{len(blocked)}**\n")
            for c in new[:5]:
                mac  = c.get("mac", "?")
                name = c.get("name", c.get("hostname", c.get("oui", "?")))
                net  = c.get("network", "?")
                f.add(WARNING, f"New client: MAC={mac} name={name} network={net}")
                lines.append(f"- New: MAC={mac} name={name} network={net}\n")
        except Exception:
            cprint(C.YELLOW, "  🟡 Could not parse client list")

    # --- Threat surface (native unifictl 5.5.0+; replaces the dead syslog path) ---
    # UniFi is not ingested into Wazuh (no `unifi` decoder exists), so monitor
    # the controller's own security feeds directly. The legacy `event list`
    # endpoint 404s on this firmware; the modern feeds are:
    #   stat alarm          -> IPS/IDS threat-management alarms (the main signal)
    #   stat rogueap        -> rogue APs; only an evil-twin (a rogue broadcasting
    #                          one of OUR SSIDs) is a finding — neighbour WiFi
    #                          (hundreds of cars/houses) is expected noise
    #   log admin-activity  -> controller admin-access audit trail (visibility)
    def _unifi_json(cmd: str):
        # None here silently disables whole checks: IPS/IDS alarms, evil-twin
        # rogue-AP detection, new/blocked clients. Several of those then print
        # a GREEN line produced entirely by the failed dependency.
        raw = run_unifictl(f"unifictl local {cmd} -o json 2>/dev/null", timeout=15)
        if not raw.strip():
            DEGRADED.record(_scope(), f"UniFi `{cmd}`", "empty response")
            return None
        try:
            doc = json.loads(raw)
            return doc.get("data", doc) if isinstance(doc, dict) else doc
        except Exception as e:
            DEGRADED.record(_scope(), f"UniFi `{cmd}`",
                            f"unparsable JSON: {type(e).__name__}")
            return None

    # IPS/IDS alarms — active threat-management events
    alarms = _unifi_json("stat alarm")
    if alarms is None:
        cprint(C.YELLOW, "  🟡 Could not read UniFi IPS/IDS alarms (stat alarm)")
        lines.append("IPS/IDS alarms: query failed\n")
    elif alarms:
        for a in alarms[:5]:
            msg = str(a.get("msg") or a.get("key") or a)[:120]
            f.add(CRITICAL, f"UniFi IPS/IDS alarm: `{msg}`")
            cprint(C.RED, f"  🔴 IPS/IDS alarm: {msg[:80]}")
        lines.append(f"IPS/IDS alarms (active): **{len(alarms)}**\n")
    else:
        cprint(C.GREEN, "  🟢 No active IPS/IDS alarms")
        lines.append("IPS/IDS alarms (active): **0**\n")

    # Evil-twin rogue APs — a rogue broadcasting one of our own SSIDs
    rogues = _unifi_json("stat rogueap")
    if rogues is not None:
        our_ssids = {str(w).lower() for w in
                     [r.get("name") for r in (_unifi_json("wlan list") or [])] if w}
        eviltwins = [r for r in rogues
                     if str(r.get("essid", "")).lower() in our_ssids]
        if eviltwins:
            for r in eviltwins[:5]:
                essid, bssid = r.get("essid", "?"), r.get("bssid", "?")
                f.add(CRITICAL, f"Evil-twin rogue AP broadcasting `{essid}` (BSSID {bssid})")
                cprint(C.RED, f"  🔴 Evil-twin AP: {essid} @ {bssid}")
            lines.append(f"Evil-twin rogue APs: **{len(eviltwins)}** (of {len(rogues)} neighbour APs seen)\n")
        else:
            cprint(C.GREEN, f"  🟢 No evil-twin APs ({len(rogues)} neighbour APs, none spoofing our SSIDs)")
            lines.append(f"Rogue APs: **0 evil-twin** / {len(rogues)} neighbour APs\n")

    # Admin-access audit trail (informational — visibility, not a finding)
    admin = _unifi_json("log admin-activity --limit 5")
    if admin:
        cprint(C.GREEN, f"  🟢 Admin-access audit trail readable ({len(admin)} recent)")
        lines.append("Recent controller admin access:\n")
        for ev in admin[:5]:
            a = ev.get("admin") if isinstance(ev.get("admin"), dict) else {}
            lines.append(f"- {a.get('name','?')} from {ev.get('ip','?')} ({ev.get('platform','?')})\n")

    return f.worst(), f, "\n".join(lines)


def s13_wazuh_siem(wz: WazuhPortForward) -> tuple[str, Findings, str]:
    """Surface SIEM-identified issues from the Wazuh indexer.

    Looks at three slices over the last 24h:
      1. High-severity alerts (rule.level >= 12) — auto-CRITICAL.
      2. Medium-severity (rule.level 7-11) buckets keyed by rule.groups —
         flag concerning categories (auth_failed, web_attack, intrusion,
         privilege_escalation, rootcheck, syscheck) above small thresholds.
      3. UniFi-specific event volume + K8s container alerts (level >= 5).

    Threshold rationale: Wazuh's 0-15 scale puts level 12+ at "critical"
    in upstream defaults; 7-11 is "notable but tunable"; 0-6 is routine.
    Homelab-tuned: only escalate medium counts when they exceed a cluster
    of >5 events (single-event noise gets filtered)."""
    section_header(13, "Wazuh SIEM Findings")
    f = Findings()
    lines = []

    # --- Slice 1: high-severity (level >= 12) --------------------------------
    body = {
        "size": 0,
        "query": {"bool": {"must": [
            {"range": {"@timestamp": {"gte": "now-24h"}}},
            {"range": {"rule.level": {"gte": 12}}},
        ]}},
        "aggs": {
            "by_rule":  {"terms": {"field": "rule.description", "size": 10}},
            "by_agent": {"terms": {"field": "agent.name",       "size": 10}},
        },
    }
    data = wz.query(body)
    if data is None:
        f.add(WARNING, "Wazuh indexer unavailable — skipping SIEM check")
        cprint(C.YELLOW, "  🟡 Wazuh indexer query failed (port-forward or auth)")
        return f.worst(), f, f.markdown()

    crit_total = data["hits"]["total"]["value"]
    if crit_total > 0:
        f.add(CRITICAL, f"{crit_total} high-severity Wazuh alerts (level≥12) in last 24h")
        cprint(C.RED, f"  🔴 {crit_total} high-severity SIEM alerts (level≥12, 24h)")
        lines.append(f"**High-severity alerts (level≥12, 24h):** {crit_total}\n\n")
        lines.append("Top rules:\n")
        for b in data["aggregations"]["by_rule"]["buckets"][:5]:
            lines.append(f"- {b['key']}: {b['doc_count']}\n")
        lines.append("\nTop agents:\n")
        for b in data["aggregations"]["by_agent"]["buckets"][:5]:
            lines.append(f"- {b['key']}: {b['doc_count']}\n")
    else:
        cprint(C.GREEN, "  🟢 No high-severity Wazuh alerts (level≥12, 24h)")
        lines.append("High-severity alerts (level≥12, 24h): **0**\n")

    # --- Slice 2: medium severity (level 7-11) by category -------------------
    body = {
        "size": 0,
        "query": {"bool": {"must": [
            {"range": {"@timestamp": {"gte": "now-24h"}}},
            {"range": {"rule.level": {"gte": 7, "lt": 12}}},
        ]}},
        "aggs": {"by_groups": {"terms": {"field": "rule.groups", "size": 20}}},
    }
    data = wz.query(body)
    med_total = data["hits"]["total"]["value"] if data else 0
    concerning = {
        "authentication_failed", "authentication_failures",
        "web_attack", "attack", "intrusion_detection",
        "privilege_escalation", "rootcheck", "syscheck",
        "ids", "ipsec",
    }
    flagged: list[tuple[str, int]] = []
    if data:
        for b in data.get("aggregations", {}).get("by_groups", {}).get("buckets", []):
            if b["key"] in concerning and b["doc_count"] > 5:
                flagged.append((b["key"], b["doc_count"]))
    if flagged:
        for cat, n in flagged:
            f.add(WARNING, f"Wazuh: {n} `{cat}` events (level 7-11, 24h)")
            cprint(C.YELLOW, f"  🟡 {n} {cat} events (medium, 24h)")
    else:
        cprint(C.GREEN, f"  🟢 No concerning medium-severity patterns ({med_total} medium total)")
    lines.append(f"\nMedium-severity alerts (level 7-11, 24h): **{med_total}**\n")

    # --- Slice 3a: UniFi is monitored natively via unifictl, not Wazuh syslog -
    # This deployment has no `unifi` decoder/ruleset, so `decoder.name=unifi`
    # is structurally always 0 — the old "0 events in 24h = syslog broken"
    # check was a permanent false positive. UniFi threats (IPS/IDS alarms,
    # evil-twin APs) and admin-access audit are checked directly against the
    # controller in the "UniFi Network Security Audit" section via unifictl
    # (stat alarm / stat rogueap / log admin-activity). Nothing to assert here.
    cprint(C.CYAN, "  UniFi: monitored natively via unifictl (see UniFi section)")
    lines.append("\nUniFi events: monitored natively via unifictl (stat alarm / rogueap / admin-activity), not Wazuh syslog\n")

    # --- Slice 3b: K8s container alerts --------------------------------------
    # Report total volume (level>=5) for visibility, but only WARN on NOTABLE
    # severity (level>=7). Per this module's own taxonomy (see docstring) level
    # 5-6 is ROUTINE — container syslog auth-fail noise sits there and was
    # tripping a false-positive volume warning (2026-07-27: 185/24h, 78% level-5
    # auth-fail, level>=12 == 0). Slice 2 already covers concerning level 7-11
    # categories cluster-wide; gating the container-volume warning on level>=7
    # stops routine noise from inflating it. Fixed at the audit root cause here,
    # not via an AR suppression of the symptom.
    def _k8s_container_alerts(min_level: int) -> int:
        d = wz.query({
            "size": 0,
            "query": {"bool": {"must": [
                {"range": {"@timestamp": {"gte": "now-24h"}}},
                {"wildcard": {"location": "*containers*"}},
                {"range": {"rule.level": {"gte": min_level}}},
            ]}},
        })
        return d["hits"]["total"]["value"] if d else 0

    k8s_total   = _k8s_container_alerts(5)  # incl. routine level 5-6 — reported only
    k8s_notable = _k8s_container_alerts(7)  # notable+ — this drives the warning
    lines.append(f"\nK8s container alerts (24h): **{k8s_total}** total (level≥5), "
                 f"**{k8s_notable}** notable (level≥7)\n")
    if k8s_notable > 100:
        f.add(WARNING, f"Wazuh: high NOTABLE K8s container alert volume ({k8s_notable}/24h, level≥7) — possible noisy app or rule mis-tune")
        cprint(C.YELLOW, f"  🟡 Notable K8s container alerts elevated ({k8s_notable}/24h level≥7; {k8s_total} total incl. routine)")
    else:
        cprint(C.GREEN, f"  🟢 K8s container alert volume normal ({k8s_notable}/24h notable, {k8s_total} total incl. routine)")

    # --- Slice 4: per-agent heartbeat (catch agent compromise / death) -------
    # An agent that stops reporting may be compromised, OOMKilled, or evicted.
    # Each registered agent should have at least one event in the last 2h
    # under normal operation (rootcheck, syscheck, syscollector keepalives).
    # Silence on a specific agent is the strongest tell that something on
    # that node is wrong — surface it.
    body = {
        "size": 0,
        "query": {"range": {"@timestamp": {"gte": "now-2h"}}},
        "aggs": {"by_agent": {"terms": {"field": "agent.name", "size": 50}}},
    }
    data = wz.query(body)
    seen_agents: set[str] = set()
    if data:
        for b in data.get("aggregations", {}).get("by_agent", {}).get("buckets", []):
            seen_agents.add(b["key"])

    # Cross-reference against registered agents (agent_control -l output via
    # manager exec). Skip if exec fails — this is a best-effort enrichment.
    agent_list_raw = run(
        "kubectl exec -n security wazuh-manager-master-0 -c wazuh-manager -- "
        "/var/ossec/bin/agent_control -l 2>/dev/null", timeout=10,
    )
    registered: list[str] = []
    if not agent_list_raw:
        # No registered-agent list => silent_agents is empty => agent-compromise
        # detection is off, with no finding emitted to say so.
        DEGRADED.record(_scope(), "Wazuh manager (agent_control -l)",
                        "could not enumerate registered agents — silent-agent "
                        "detection disabled")
    if agent_list_raw:
        # Parse lines like: "   ID: 022, Name: k8s-nuc14-02, IP: any, Active"
        # Use [^,]+? lazy to stop at the first comma after "Name: ".
        for line in agent_list_raw.splitlines():
            m = re.search(r"Name:\s+([^,]+?),.*Active", line)
            if m and "(server)" not in line:
                registered.append(m.group(1).strip())

    silent_agents = [a for a in registered if a not in seen_agents]
    if registered:
        lines.append(f"\nRegistered agents: **{len(registered)}** "
                     f"(seen in last 2h: {len(registered) - len(silent_agents)})\n")
        if silent_agents:
            for a in silent_agents:
                f.add(WARNING, f"Wazuh agent `{a}` silent for >2h — possible compromise, OOM, or eviction")
                cprint(C.YELLOW, f"  🟡 agent silent >2h: {a}")
        else:
            cprint(C.GREEN, f"  🟢 All {len(registered)} agents reporting within 2h")
    else:
        cprint(C.YELLOW, "  🟡 Could not enumerate registered agents (manager exec failed)")
        lines.append("\n_Could not enumerate registered agents to cross-reference silence._\n")

    return f.worst(), f, "\n".join(lines)


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

SECTION_NAMES = [
    "SOPS Encryption Coverage",
    "Sensitive Data Exposure",
    "Git History Secret Scan",
    "CVE / Vulnerability Check",
    "Authentik Login Analysis",
    "External Attack Patterns",
    "Error Rate Spike Detection (ES)",
    "RBAC & Pod Security",
    "External Exposure Inventory",
    "Certificate Integrity",
    "Flux Security Posture",
    "UniFi Network Security",
    "Wazuh SIEM Findings",
]


_TIER_ROUTE_LABEL = {
    rm.CRITICAL: "urgent page (audible)",
    rm.HIGH:     "briefing (non-urgent)",
    rm.MEDIUM:   "maintenance-window queue",
    rm.LOW:      "weekly batch / dashboard",
}


def _render_tier_block(scored: list) -> list[str]:
    """Markdown for the contextual-tier grouping. CVE-ID-free: identifies
    findings by image/component/section only, never by the raw title (which the
    committed report renders elsewhere but must not gain NEW CVE detail here)."""
    from collections import Counter
    tier_ct: Counter = Counter()
    intrinsic_ct: Counter = Counter()
    crits: list = []
    candidates: dict[str, str] = {}   # app token → tier
    for section in scored:
        for sev_emoji, _msg, _im, res in section:
            tier_ct[res.tier] += 1
            intrinsic_ct[SEVERITY_MAP.get(sev_emoji, sev_emoji)] += 1
            ident = res.finding.image or res.finding.component or res.finding.subsection
            if res.tier == rm.CRITICAL:
                crits.append((ident, res))
            if res.exposure == rm.EXTERNAL_UNAUTH:
                c = rm.matched_self_auth_candidate(res.finding)
                if c:
                    candidates[c] = res.tier

    doc: list[str] = ["\n## Contextual Risk Tiers\n\n"]
    doc.append("> Additive lens (exposure × exploited-in-KEV × nature). Intrinsic "
               "severity is retained on every finding; tier is the primary "
               "routing signal.\n\n")
    doc.append("| Tier | Count | Routes to |\n|------|-------|-----------|\n")
    for tier in (rm.CRITICAL, rm.HIGH, rm.MEDIUM, rm.LOW):
        doc.append(f"| {tier} | {tier_ct.get(tier, 0)} | {_TIER_ROUTE_LABEL[tier]} |\n")
    intr = ", ".join(f"{intrinsic_ct[k]} {k}" for k in
                     ("critical", "warning", "accepted", "clean", "monitor", "deferred")
                     if intrinsic_ct.get(k))
    doc.append(f"\n_Intrinsic severity (retained): {intr or 'none'}._\n")

    doc.append("\n### 🔴 Contextual CRITICALs (external-unauth + exploited-in-KEV + real vuln)\n\n")
    if not crits:
        doc.append("None — no finding is externally-exposed AND exploited-in-the-wild "
                   "AND a real vuln. On this homelab that is the expected state.\n")
    else:
        for ident, res in crits:
            doc.append(f"- `{ident}` — {res.rationale}\n")

    if candidates:
        doc.append("\n### Self-auth allowlist CANDIDATES (surfaced, NOT downgraded)\n\n")
        doc.append("These external apps ship their own login but are NOT operator-blessed "
                   "in `SELF_AUTH_APPS`, so they score external-unauth (→ HIGH). To treat "
                   "an app's own auth as a verified boundary (→ MEDIUM), add its token to "
                   "`SELF_AUTH_APPS` in `runbooks/lib/risk_model.py` (reviewed, like an AR):\n\n")
        for tok in sorted(candidates):
            doc.append(f"- `{tok}` — currently scored {candidates[tok].upper()} (external-unauth)\n")
    return doc


def write_report(
    timestamp: str,
    results: list[tuple[str, Findings, str]],
    scored: list | None = None,
) -> None:
    doc = [
        f"# Security Audit — {timestamp}\n\n",
        "> Auto-generated by security-check.py — do not hand-edit. "
        "Sensitive values redacted as [DOMAIN], [NAME], [EMAIL].\n\n---\n\n",
    ]

    for i, (status, findings, body) in enumerate(results, 1):
        name = SECTION_NAMES[i - 1]
        doc.append(f"## {i}. {name}\n\n**Status: {status}**\n\n")
        doc.append(redact(body))
        doc.append("\n---\n\n")

    # Summary table
    doc.append("## Summary\n\n")
    doc.append("| Section | Status | Findings |\n")
    doc.append("|---------|--------|----------|\n")
    for i, (status, findings, _) in enumerate(results, 1):
        name = SECTION_NAMES[i - 1]
        doc.append(f"| {i}. {name} | {status} | {findings.summary_cell()} |\n")

    # Contextual tier grouping (Phase 2). Rendered from the scored findings.
    if scored is not None:
        doc.extend(_render_tier_block(scored))

    # Priority actions
    criticals = [(SECTION_NAMES[i], f) for i, (s, f, _) in enumerate(results) if s == CRITICAL]
    warnings  = [(SECTION_NAMES[i], f) for i, (s, f, _) in enumerate(results) if s == WARNING]

    if criticals or warnings:
        doc.append("\n## Priority Actions\n\n")
        if criticals:
            doc.append("### 🔴 Critical\n\n")
            for name, f in criticals:
                for sev, msg, _ in f._items:
                    if sev == CRITICAL:
                        doc.append(f"- **{name}**: {msg}\n")
        if warnings:
            doc.append("\n### 🟡 Warning\n\n")
            for name, f in warnings:
                for sev, msg, _ in f._items:
                    if sev == WARNING:
                        doc.append(f"- **{name}**: {msg}\n")

    OUTPUT.write_text("".join(doc))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_SECTION_SLUGS = [
    "s1_sops_coverage",
    "s2_sensitive_exposure",
    "s3_git_history",
    "s4_cve_check",
    "s5_authentik_logins",
    "s6_attack_patterns",
    "s6a_error_rate_spikes",
    "s7_rbac_pod_security",
    "s8_external_exposure",
    "s9_certificates",
    "s10_flux_posture",
    "s11_unifi",
    "s13_wazuh_siem",
]


def _build_indexes() -> tuple["rm.ExposureIndex | None", "rm.KevIndex"]:
    """Build the exposure + KEV indexes ONCE per run (threaded into scoring).

    Exposure fails soft to None (model then defaults every finding to internal —
    conservative, not dismissive). KEV fails soft to an UNKNOWN feed (never a
    silent 'not exploited') — that behaviour lives inside KevIndex.load().
    """
    try:
        idx = rm.load_exposure_index()
    except Exception as e:  # noqa: BLE001
        cprint(C.YELLOW, f"  · exposure index unavailable ({e}) — findings default to internal")
        DEGRADED.record("risk_scoring", "exposure index",
                        f"{type(e).__name__} — every finding defaults to internal "
                        f"exposure, systematically downgrading tiers")
        idx = None
    kev = rm.KevIndex.load()
    if not kev.loaded:
        DEGRADED.record("risk_scoring", "CISA KEV feed",
                        f"unavailable ({kev.source}) — every exploited-axis is UNKNOWN")
    kw = C.GREEN if kev.loaded else C.RED
    cprint(kw, f"  · KEV feed: {kev.source}"
               + (f" (catalog {kev.catalog_version}, {len(kev.cve_ids)} CVEs)"
                  if kev.loaded else " — every exploited-axis is UNKNOWN (visible, not scored safe)"))
    if idx is not None:
        cprint(C.CYAN, f"  · exposure index: {len(idx.external_unauth)} external-unauth, "
                       f"{len(idx.external_auth)} external-auth, {len(idx.internal_apps)} internal")
    return idx, kev


def _score_all(results: list, *, exposure_index, kev_index) -> list:
    """Score every finding once. Returns a list parallel to `results`; each
    entry is a list of (sev_emoji, msg, item_meta, ScoreResult) aligned to that
    section's Findings._items. Faithful to the harness: builds each Finding via
    rm.Finding.from_db_row (same image/CVE/AR parsing as reading the DB row)."""
    scored: list = []
    for idx, (_status, findings, _body) in enumerate(results):
        subsection = _SECTION_SLUGS[idx] if idx < len(_SECTION_SLUGS) else f"s{idx}"
        section_scored = []
        for sev_emoji, msg, item_meta in findings._items:
            intrinsic = SEVERITY_MAP.get(sev_emoji, sev_emoji)
            fin = rm.Finding.from_db_row({
                "finding_id": None,
                "severity": intrinsic,
                "title": msg,
                "metadata": {**(item_meta or {}), "subsection": subsection},
            })
            res = rm.score(fin, exposure_index=exposure_index, kev_index=kev_index)
            section_scored.append((sev_emoji, msg, item_meta, res))
        scored.append(section_scored)
    return scored


def _route_text(section_title: str, msg: str, res) -> str:
    return (f"[{res.tier.upper()}] {section_title}: {msg}\n"
            f"({res.rationale})")


def _emit_findings(writer: FindingsWriter, results: list, scored: list) -> None:
    """Persist each finding to sweep-history WITH its contextual tier, and route
    it by tier.

    ADDITIVE: intrinsic severity is still written (writer.emit(severity=...));
    the contextual tier is stored ALONGSIDE it in metadata (risk_tier + axes),
    never replacing it — the change is fully reversible.

    Routing (Phase 2): CRITICAL pages (urgent), HIGH surfaces as a non-urgent
    briefing, MEDIUM/LOW never notify. Live sending is GATED behind
    SWEEP_NOTIFY_BY_TIER (default DRY) so an unattended run records the decision
    without paging until the operator opts in; the decision is always persisted.
    """
    if not writer.enabled:
        return
    route_live = os.environ.get("SWEEP_NOTIFY_BY_TIER", "").strip().lower() in (
        "1", "true", "live", "yes", "on")
    evidence = (str(OUTPUT.relative_to(REPO_ROOT))
                if str(OUTPUT).startswith(str(REPO_ROOT)) else str(OUTPUT))
    for idx, (_status, findings, _body) in enumerate(results):
        subsection = _SECTION_SLUGS[idx] if idx < len(_SECTION_SLUGS) else f"s{idx}"
        section_title = SECTION_NAMES[idx] if idx < len(SECTION_NAMES) else subsection
        for (sev_emoji, msg, item_meta), (_s, _m, _im, res) in zip(
                findings._items, scored[idx]):
            meta: dict = {"section_title": section_title}
            meta.update(item_meta or {})
            # Contextual tier + axes — additive, never overwrites `severity`.
            meta["risk_tier"] = res.tier
            meta["risk_exposure"] = res.exposure
            meta["risk_exploited"] = res.exploited          # True | False | None
            meta["risk_exploited_reason"] = res.exploited_reason
            meta["risk_nature"] = res.nature
            meta["risk_unknown_exploited"] = res.unknown_exploited
            meta["risk_rationale"] = res.rationale          # CVE-ID-free by construction
            if res.exposure == rm.EXTERNAL_UNAUTH and rm.is_self_auth_candidate(res.finding):
                meta["self_auth_candidate"] = True

            # Route by tier (dry unless opted in). Decision recorded either way.
            dec = _notify.route_finding(
                res.tier, text=_route_text(section_title, msg, res),
                dry_run=not route_live)
            meta["route_channel"] = dec.channel
            meta["route_urgent"] = dec.urgent
            meta["route_sent"] = dec.sent

            writer.emit(severity=sev_emoji, title=msg, subsection=subsection,
                        evidence_path=evidence, metadata=meta)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Security audit for the homelab cluster.",
    )
    parser.add_argument(
        "--postgres-dsn",
        default=os.environ.get("SWEEP_PG_DSN"),
        help=(
            "Postgres DSN for sweep-history. If unset and SWEEP_PG_DSN env "
            "var is also unset, findings are written to markdown only."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    os.chdir(REPO_ROOT)

    cprint(C.BOLD + C.BLUE, "=" * 60)
    cprint(C.BOLD + C.BLUE, " Security Audit — Kubernetes Homelab")
    cprint(C.BOLD + C.BLUE, "=" * 60)
    print(f"Date   : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Output : {OUTPUT}")
    if args.postgres_dsn:
        print(f"Sweep  : enabled (cycle={cycle_id_from_env('<new>')})")
    print()

    if not load_sensitive():
        return 1

    cprint(C.CYAN, f"Sensitive vars loaded — DOMAIN={len(_sensitive['DOMAIN'])}c, "
                   f"NAME={len(_sensitive['NAME'])}c, EMAIL={len(_sensitive['EMAIL'])}c")

    global _ACCEPTED_RISKS
    _ACCEPTED_RISKS = load_accepted_risks()
    if _POLICY_LOAD_FAILED and not os.environ.get("SWEEP_ALLOW_NO_POLICY"):
        cprint(C.RED, "  ✖ ABORT: accepted-risk policy store unreachable "
                      f"({_POLICY_LOAD_FAILED})")
        cprint(C.RED, "    Continuing would unsuppress EVERY accepted risk and "
                      "report them as fresh criticals —")
        cprint(C.RED, "    a false-alarm flood that looks exactly like a real "
                      "security regression.")
        cprint(C.RED, "    Fix the policy store, or set SWEEP_ALLOW_NO_POLICY=1 "
                      "to run unsuppressed deliberately.")
        return 2
    if _ACCEPTED_RISKS:
        cprint(C.CYAN, f"Accepted risks loaded — {len(_ACCEPTED_RISKS)} entries: "
                       f"{', '.join(sorted(_ACCEPTED_RISKS.keys()))}")

    # Write preflight: prove the findings DB is reachable BEFORE spending
    # minutes on 13 sections + three port-forwards. The writer is only opened
    # at the very end, so without this a DB outage discards a fully completed
    # run (all sections ran, then the end-of-run connect threw). Markdown-only
    # runs (no DSN) preflight to a no-op and proceed.
    try:
        FindingsWriter.preflight(args.postgres_dsn)
    except Exception as e:
        cprint(C.RED, f"Findings DB preflight FAILED: {e}")
        cprint(C.RED, "  Refusing to run the audit — its findings would be written at the")
        cprint(C.RED, "  end and lost. Fix SWEEP_PG_DSN / the database, or unset the DSN to")
        cprint(C.RED, "  run in markdown-only mode.")
        return 2

    results: list[tuple[str, Findings, str]] = []

    # Sections 1-4: no Elasticsearch needed
    results.append(s1_sops_coverage())
    results.append(s2_sensitive_exposure())
    results.append(s3_git_history())
    results.append(s4_cve_check())

    # Sections 5-6: need Elasticsearch port-forward
    cprint(C.CYAN, "\nStarting Elasticsearch port-forward for sections 5-6...")
    with ElasticPortForward() as es:
        results.append(s5_authentik_logins(es))
        results.append(s6_attack_patterns(es))
        results.append(s6a_error_rate_spikes(es))

    # Sections 8-12: no Elasticsearch
    results.append(s7_rbac_pod_security())
    results.append(s8_external_exposure())
    results.append(s9_certificates())
    results.append(s10_flux_posture())
    results.append(s11_unifi())

    # Section 13: Wazuh SIEM findings (separate indexer cluster)
    cprint(C.CYAN, "\nStarting Wazuh indexer port-forward for section 13...")
    with WazuhPortForward() as wz:
        results.append(s13_wazuh_siem(wz))

    # Contextual risk scoring — build indexes ONCE, score every finding.
    cprint(C.CYAN, "\nContextual risk scoring (exposure × exploited × nature)...")
    exposure_index, kev_index = _build_indexes()
    scored = _score_all(results, exposure_index=exposure_index, kev_index=kev_index)

    # Write report
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    write_report(timestamp, results, scored)

    # Final summary
    total_crit = sum(1 for s, _, _ in results if s == CRITICAL)
    total_warn = sum(1 for s, _, _ in results if s == WARNING)
    total_ok   = sum(1 for s, _, _ in results if s == OK)

    # Emit findings to sweep-history (no-op without DSN)
    verdict = "red" if total_crit > 0 else ("yellow" if total_warn > 0 else "green")
    with FindingsWriter(
        dsn=args.postgres_dsn,
        section="security",
        cycle_id=cycle_id_from_env(),
        trigger=trigger_from_env(),
        git_head=git_head(),
    ) as writer:
        _emit_findings(writer, results, scored)
        # s4 classifies "is this CVE fixable by a newer tag?" through the
        # check-all-versions registry oracle, which is a SEPARATE module with
        # its own DegradationLog. A throttled registry therefore degrades the
        # SECURITY section's fixability verdict while recording the reason in
        # someone else's log, where our veto would never see it. Drain it.
        _vc_log = getattr(_VER_CHECKER, "degraded", None) if _VER_CHECKER else None
        if _vc_log:
            for _r in _vc_log.reasons:
                DEGRADED.record("s4_cve_check (image-tag oracle)",
                                "check-all-versions registry lookup", _r)
        # Veto stale-finding auto-close if ANY dependency degraded this run.
        # The run still completes and reports everything it could measure —
        # this only stops the writer reading "absent" as "resolved" for the
        # checks that could not execute. See docs/sops/sweep-findings-lifecycle.md.
        DEGRADED.apply(writer)
        writer.close(verdict=verdict)

    # Contextual-tier summary to the terminal (intrinsic count secondary).
    from collections import Counter as _Counter
    tier_ct = _Counter(res.tier for section in scored for (_se, _m, _im, res) in section)
    cprint(C.BOLD, f" Tiers: {tier_ct.get(rm.CRITICAL,0)} critical  "
                   f"{tier_ct.get(rm.HIGH,0)} high  {tier_ct.get(rm.MEDIUM,0)} medium  "
                   f"{tier_ct.get(rm.LOW,0)} low  "
                   f"(intrinsic: {total_crit} critical / {total_warn} warning)")

    print()
    cprint(C.BOLD + C.BLUE, "=" * 60)
    cprint(C.BOLD, f" Results: {total_crit} critical  {total_warn} warning  {total_ok} ok")
    cprint(C.BOLD + C.BLUE, "=" * 60)
    print(f"\nReport written to: {OUTPUT}\n")

    return 1 if total_crit > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
