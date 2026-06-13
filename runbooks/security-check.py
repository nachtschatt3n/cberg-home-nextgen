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
    FindingsWriter, cycle_id_from_env, trigger_from_env, git_head,
)


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

    Empty result on every failure path — the audit proceeds without
    accepted-risk filtering rather than blocking on policy loader errors.
    """
    dsn = os.environ.get("SWEEP_PG_DSN")
    if dsn:
        return _load_accepted_risks_from_db(dsn)
    return _load_accepted_risks_from_markdown()


def _load_accepted_risks_from_db(dsn: str) -> dict[str, str]:
    try:
        import psycopg  # lazy: degrade if psycopg isn't available
    except ImportError:
        cprint(C.YELLOW, "  ⚠ psycopg not installed — skipping accepted-risk load")
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
        cprint(C.YELLOW, f"  ⚠ could not load accepted_risks from DB: {e}")
        return {}


def _load_accepted_risks_from_markdown() -> dict[str, str]:
    if not ACCEPTED_RISKS_DOC.exists():
        cprint(C.YELLOW, f"  ⚠ accepted-risks doc not found: {ACCEPTED_RISKS_DOC}")
        return {}
    try:
        text = ACCEPTED_RISKS_DOC.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        cprint(C.YELLOW, f"  ⚠ could not read accepted-risks doc: {e}")
        return {}
    if not text.strip():
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd: str, timeout: int = 30) -> str:
    """Run a shell command, return stdout (empty string on error)."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def run_cmd(cmd: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run command and return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
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
    return out


def run_lines(cmd: str, timeout: int = 30) -> list[str]:
    out = run(cmd, timeout=timeout)
    return [l for l in out.splitlines() if l.strip()]


def kubectl(args: str, timeout: int = 30) -> str:
    return run(f"kubectl {args}", timeout=timeout)


def kubectl_json(args: str, timeout: int = 30) -> dict | list | None:
    out = kubectl(args + " -o json", timeout=timeout)
    try:
        return json.loads(out)
    except Exception:
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
    _sensitive["EMAIL"]  = git_email
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
        self._items: list[tuple[str, str]] = []   # (severity, message)

    def add(self, severity: str, msg: str) -> None:
        self._items.append((severity, redact(msg)))

    def worst(self) -> str:
        for sev in (CRITICAL, WARNING):
            if any(s == sev for s, _ in self._items):
                return sev
        return OK

    def markdown(self) -> str:
        if not self._items:
            return f"{OK} No findings\n"
        return "\n".join(f"- {s} {m}" for s, m in self._items) + "\n"

    def count(self, severity: str) -> int:
        return sum(1 for s, _ in self._items if s == severity)

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
        new_items: list[tuple[str, str]] = []
        for sev, msg in self._items:
            matched_id: str | None = None
            haystack = msg.lower()
            for ar_id, desc in accepted_risks.items():
                needle = desc.lower().strip()
                if needle and needle in haystack:
                    matched_id = ar_id
                    break
            if matched_id:
                new_items.append((ACCEPTED, f"[{matched_id}] {msg}"))
            else:
                new_items.append((sev, msg))
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

def _exec_search(ns: str, pod: str, container: str, userpass: str | None,
                 index: str, body: dict, timeout: int) -> dict | None:
    """Run an _search against the indexer from inside its own pod.

    JSON body is piped to curl via stdin (`-d @-`) so there's no shell
    quoting of the query. Returns parsed JSON, or None on any failure.
    """
    if not userpass or not pod:
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
        except Exception:
            self._password = None
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
        except Exception:
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
    cprint(C.BLUE, f"\n[{n}/13] {title}")


def s1_sops_coverage() -> tuple[str, Findings, str]:
    section_header(1, "SOPS Encryption Coverage")
    f = Findings()
    lines = []

    # Unencrypted kind:Secret files
    unenc = run_lines(
        "grep -rl 'kind: Secret' kubernetes/ --include='*.yaml' | grep -v '\\.sops\\.yaml$'"
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
        # Bare or quoted shell variables like $DB_PASSWORD, "$ICLOUD_PASSWORD":
        "| grep -vE 'PGPASSWORD=\\$|password=\"?\\$[A-Z_]+|token=\"?\\$[A-Z_]+|api.?key=\"?\\$[A-Z_]+' "
        "| grep -vE '^[+-]?\\s*#|description:' "
        "| grep -v '\"replace-me\"\\|\"my-strong-password\"\\|\"my-api-key\"\\|\"your-api-key-here\"\\|openssl rand' "
        # Template/doc placeholders like <github-personal-access-token>, <web-ui-password>:
        "| grep -v '<[a-z][a-z0-9-]*>' "
        # Shell commands that reference secrets by name, not value:
        "| grep -vE 'kubectl (edit|get|describe) secret|`kubectl edit secret' "
        # Shell command substitution — value captured at runtime, never hardcoded:
        "| grep -vE '[a-zA-Z_]+=\"\\$\\(' "
        # Python f-string interpolation (e.g., X-Plex-Token={token}) — variable, not a value:
        "| grep -ivE '(token|password|secret|api.?key)=\\{[a-zA-Z_]+\\}' "
    )
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
        non_sops = run("git ls-files | grep -v '\\.sops\\.yaml$'")
        count = run(f"git log --all -p -S '{domain}' -- {non_sops} 2>/dev/null "
                    f"| grep '^+.*{domain}' | grep -v 'sops\\|ENC\\[' | wc -l").strip()
        try:
            n = int(count)
        except ValueError:
            n = 0
        if n > 0:
            f.add(WARNING, f"Domain literal found in {n} deleted lines of non-sops history")
            cprint(C.YELLOW, f"  🟡 Domain in {n} lines of non-sops git history (deleted content)")
        else:
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
        return f.worst(), f, f.markdown()

    content = version_file.read_text()
    rows = re.findall(r'\|\s*`([^`]+)`\s*\|\s*`([^`\s]+)', content)
    seen: set[str] = set()
    unique = [(n, v) for n, v in rows if not (n in seen or seen.add(n))]  # type: ignore[func-returns-value]

    cprint(C.CYAN, f"  Checking {min(len(unique), 25)} components against OSV.dev...")
    found_vulns = False
    for name, ver in unique[:25]:
        clean = re.sub(r'[-_](alpine|bookworm|bullseye|jammy|focal|slim|rootless).*', '', ver).lstrip('v')
        payload = json.dumps({"version": clean, "package": {"name": name, "ecosystem": "Helm"}}).encode()
        req = urllib.request.Request(
            "https://api.osv.dev/v1/query", data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=6) as r:
                data = json.load(r)
            vulns = data.get("vulns", [])
            if vulns:
                ids = [v["id"] for v in vulns]
                f.add(CRITICAL, f"`{name}` {ver}: {len(vulns)} CVE(s) — {ids}")
                cprint(C.RED, f"  🔴 {name} {ver}: {ids}")
                found_vulns = True
        except Exception:
            pass
        time.sleep(0.15)

    if not found_vulns:
        cprint(C.GREEN, "  🟢 No CVEs found for checked components")

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
        return f.worst(), f, f.markdown()

    trivy_cache = Path(os.environ.get("TMPDIR", "/tmp")) / "cberg-trivy-cve-cache.json"
    cache_age_sec = 86400  # 24h

    cached: dict | None = None
    if trivy_cache.exists():
        try:
            age = time.time() - trivy_cache.stat().st_mtime
            if age < cache_age_sec:
                cached = json.loads(trivy_cache.read_text())
                cprint(C.DIM if hasattr(C, "DIM") else C.CYAN,
                       f"  · using cached Trivy results "
                       f"({int(cache_age_sec - age)}s until refresh)")
        except Exception:
            cached = None

    # Pull every distinct running image once
    images_raw = kubectl(
        "get pods -A -o jsonpath="
        "'{range .items[*].spec.containers[*]}{.image}{\"\\n\"}{end}"
        "{range .items[*].spec.initContainers[*]}{.image}{\"\\n\"}{end}'",
    )
    distinct_images = sorted({i.strip().strip("'") for i in images_raw.splitlines() if i.strip()})

    findings_per_image: dict[str, dict] = {}
    if cached is not None:
        findings_per_image = cached.get("results", {})
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # Skip well-known bases that AR docs accept or that don't add useful
        # signal (Bitnami images tracked by Renovate; Wazuh internal images).
        def _should_skip(img: str) -> bool:
            return any(skip in img.lower() for skip in (
                "bitnami/", "wazuh/wazuh-",
            ))

        scan_targets = [i for i in distinct_images if not _should_skip(i)]
        cprint(C.CYAN, f"  Scanning {len(scan_targets)} distinct images "
                       "with trivy (parallel, cached 24h)...")

        def _scan_one(img: str) -> tuple[str, dict | None]:
            rc, stdout, _stderr = run_cmd(
                f"trivy image --severity CRITICAL,HIGH --exit-code 0 "
                f"--quiet --format json --timeout 30s {img}",
                timeout=45,
            )
            if rc != 0 or not stdout:
                return img, None
            try:
                report = json.loads(stdout)
            except Exception:
                return img, None
            crit = high = 0
            sample_ids: list[str] = []
            for tgt in report.get("Results", []) or []:
                for v in tgt.get("Vulnerabilities", []) or []:
                    sev = v.get("Severity", "")
                    if sev == "CRITICAL":
                        crit += 1
                    elif sev == "HIGH":
                        high += 1
                    if (crit + high) <= 5 and v.get("VulnerabilityID"):
                        sample_ids.append(v["VulnerabilityID"])
            if crit or high:
                return img, {"critical": crit, "high": high, "sample": sample_ids[:5]}
            return img, None

        # 6 parallel scans is enough to overlap registry latency without
        # hammering the local Trivy DB lock.
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(_scan_one, img): img for img in scan_targets}
            for fut in as_completed(futures):
                img, result = fut.result()
                if result:
                    findings_per_image[img] = result
        try:
            trivy_cache.write_text(json.dumps({"results": findings_per_image}))
        except Exception:
            pass

    # Drop any cached findings whose image:tag is no longer running in the
    # cluster. Without this, fixed/replaced images linger as findings until
    # the 24h cache expires (e.g. an ai-sre 2.1.0 entry persists after a
    # rollout to 2.1.4 even though the vulnerable image has been pulled).
    findings_per_image = {
        img: r for img, r in findings_per_image.items()
        if img in distinct_images
    }

    # Surface findings: any image with >0 CRITICAL = CRITICAL audit finding;
    # >5 HIGH on a single image = WARNING (noise floor for CVE accumulation).
    if findings_per_image:
        for img, r in sorted(findings_per_image.items()):
            tag = img.split("@")[0]  # strip digest if present
            sample = ", ".join(r["sample"][:3]) + ("…" if len(r["sample"]) > 3 else "")
            if r["critical"] > 0:
                f.add(CRITICAL, f"`{tag}`: {r['critical']} CRITICAL + {r['high']} HIGH CVEs — {sample}")
                cprint(C.RED, f"  🔴 {tag}: {r['critical']}C/{r['high']}H — {sample}")
            elif r["high"] > 5:
                f.add(WARNING, f"`{tag}`: {r['high']} HIGH CVEs — {sample}")
                cprint(C.YELLOW, f"  🟡 {tag}: {r['high']} HIGH — {sample}")
        cprint(C.CYAN, f"  Trivy: {len(findings_per_image)} of {len(distinct_images)} images "
                       f"with CRITICAL or >5 HIGH CVEs")
    else:
        cprint(C.GREEN, f"  🟢 Trivy: no CRITICAL CVEs in {len(distinct_images)} running images "
                       "(no images had >5 HIGH either)")

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
    }
    ACCEPTED_ROOT_UID = {
        "ai/openclaw",                    # install-openclaw init container
        "ai/paperclip",                   # tools container
        "backup/icloud-docker-mu",        # iCloud sync agent (requires root for keychain)
        "home-automation/node-red",       # legacy image design
        "home-automation/scrypted",       # same as privileged rationale
        "media/jellyfin",                 # same as privileged rationale
        "media/makemkv",                  # same as privileged rationale
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
    except Exception:
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
        f.add(WARNING, "unifictl session expired — re-run `unifictl local configure`")
        cprint(C.YELLOW, "  🟡 unifictl session expired")
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

    # Attempt 2: direct HTTPS sysinfo
    if not unifi_version:
        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(
                "https://192.168.30.1:8443/api/s/default/stat/sysinfo",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                sdata = json.load(resp)
                items = sdata.get("data", [])
                if items:
                    unifi_version = items[0].get("version")
        except Exception:
            pass

    # Attempt 3: parse UDM/gateway firmware version from device list table output
    if not unifi_version and devices_raw:
        for line in devices_raw.splitlines():
            if "udm" in line.lower().split():
                parts = line.split()
                # Table columns: name model type ip mac version state adopted
                # Find the version field (format: X.X.X.NNNNN)
                for part in parts:
                    if re.match(r'\d+\.\d+\.\d+\.\d+', part):
                        unifi_version = part
                        break
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
    lines.append(f"WAN health: **{'OK' if wan_ok else wan}**\n")
    if not wan_ok:
        f.add(WARNING, f"WAN health not OK: `{wan}`")
        cprint(C.YELLOW, f"  🟡 WAN: {wan}")
    else:
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

    # Events / IDS
    events_raw = run("unifictl local event list -o json 2>/dev/null", timeout=15)
    if not events_raw or not events_raw.strip():
        # Empty output usually means unifictl session expired or the
        # controller is briefly unreachable (e.g., during a UniFi
        # Network application auth-API hang). Section 12 will already
        # have surfaced the broader connectivity gap; don't double-emit
        # a parse-failure warning here — the prior version flagged it
        # as a sweep warning even when there was nothing to parse.
        pass
    else:
        try:
            events = json.loads(events_raw)
            if isinstance(events, dict):
                events = events.get("data", [])
            threats = [e for e in events if any(k in str(e).upper()
                       for k in ["IDS", "IPS", "THREAT", "INTRUSION", "MALWARE"])]
            if threats:
                for t in threats[:5]:
                    f.add(CRITICAL, f"IDS/IPS event: `{str(t)[:100]}`")
                    cprint(C.RED, f"  🔴 Threat event: {str(t)[:80]}")
            else:
                cprint(C.GREEN, "  🟢 No IDS/IPS events")
            lines.append(f"IDS/IPS events: **{len(threats)}**\n")
        except Exception:
            # Output was non-empty but didn't parse as JSON — real
            # ergonomics issue worth flagging.
            cprint(C.YELLOW, "  🟡 Could not parse event list")

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

    # --- Slice 3a: UniFi events (any level — they're already filtered) -------
    body = {
        "size": 0,
        "query": {"bool": {"must": [
            {"range": {"@timestamp": {"gte": "now-24h"}}},
            {"match": {"decoder.name": "unifi"}},
        ]}},
        "aggs": {"by_rule": {"terms": {"field": "rule.description", "size": 10}}},
    }
    data = wz.query(body)
    unifi_total = data["hits"]["total"]["value"] if data else 0
    lines.append(f"\nUniFi events (24h): **{unifi_total}**\n")
    if unifi_total > 0 and data:
        lines.append("Top UniFi rules:\n")
        for b in data["aggregations"]["by_rule"]["buckets"][:3]:
            lines.append(f"- {b['key']}: {b['doc_count']}\n")
    if unifi_total == 0:
        cprint(C.YELLOW, "  🟡 0 UniFi events ingested (24h) — verify SIEM Server is forwarding")
        f.add(WARNING, "Wazuh: 0 UniFi events in 24h — UniFi syslog flow may be broken")
    else:
        cprint(C.GREEN, f"  🟢 UniFi events flowing ({unifi_total} in 24h)")

    # --- Slice 3b: K8s container alerts (level >= 5, location *containers*) --
    body = {
        "size": 0,
        "query": {"bool": {"must": [
            {"range": {"@timestamp": {"gte": "now-24h"}}},
            {"wildcard": {"location": "*containers*"}},
            {"range": {"rule.level": {"gte": 5}}},
        ]}},
        "aggs": {"by_rule": {"terms": {"field": "rule.description", "size": 10}}},
    }
    data = wz.query(body)
    k8s_total = data["hits"]["total"]["value"] if data else 0
    lines.append(f"\nK8s container alerts (level≥5, 24h): **{k8s_total}**\n")
    if k8s_total > 100:
        f.add(WARNING, f"Wazuh: high K8s container alert volume ({k8s_total}/24h, level≥5) — possible noisy app or rule mis-tune")
        cprint(C.YELLOW, f"  🟡 K8s container alerts elevated ({k8s_total}/24h)")
    else:
        cprint(C.GREEN, f"  🟢 K8s container alert volume normal ({k8s_total}/24h)")

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


def write_report(
    timestamp: str,
    results: list[tuple[str, Findings, str]],
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

    # Priority actions
    criticals = [(SECTION_NAMES[i], f) for i, (s, f, _) in enumerate(results) if s == CRITICAL]
    warnings  = [(SECTION_NAMES[i], f) for i, (s, f, _) in enumerate(results) if s == WARNING]

    if criticals or warnings:
        doc.append("\n## Priority Actions\n\n")
        if criticals:
            doc.append("### 🔴 Critical\n\n")
            for name, f in criticals:
                for sev, msg in f._items:
                    if sev == CRITICAL:
                        doc.append(f"- **{name}**: {msg}\n")
        if warnings:
            doc.append("\n### 🟡 Warning\n\n")
            for name, f in warnings:
                for sev, msg in f._items:
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


def _emit_findings(writer: FindingsWriter, results: list) -> None:
    """Persist each (section, Findings, body) tuple to sweep-history.

    No-op when the writer is disabled (no DSN).
    """
    if not writer.enabled:
        return
    for idx, (_status, findings, _body) in enumerate(results):
        subsection = _SECTION_SLUGS[idx] if idx < len(_SECTION_SLUGS) else f"s{idx}"
        section_title = SECTION_NAMES[idx] if idx < len(SECTION_NAMES) else subsection
        for sev_emoji, msg in findings._items:
            writer.emit(
                severity=sev_emoji,
                title=msg,
                subsection=subsection,
                # OUTPUT may be outside REPO_ROOT when SWEEP_SNAPSHOTS_DIR is
                # set (e.g. /tmp/snapshots in the in-cluster collector).
                evidence_path=(
                    str(OUTPUT.relative_to(REPO_ROOT))
                    if str(OUTPUT).startswith(str(REPO_ROOT))
                    else str(OUTPUT)
                ),
                metadata={"section_title": section_title},
            )


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
    if _ACCEPTED_RISKS:
        cprint(C.CYAN, f"Accepted risks loaded — {len(_ACCEPTED_RISKS)} entries: "
                       f"{', '.join(sorted(_ACCEPTED_RISKS.keys()))}")

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

    # Write report
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    write_report(timestamp, results)

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
        _emit_findings(writer, results)
        writer.close(verdict=verdict)

    print()
    cprint(C.BOLD + C.BLUE, "=" * 60)
    cprint(C.BOLD, f" Results: {total_crit} critical  {total_warn} warning  {total_ok} ok")
    cprint(C.BOLD + C.BLUE, "=" * 60)
    print(f"\nReport written to: {OUTPUT}\n")

    return 1 if total_crit > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
