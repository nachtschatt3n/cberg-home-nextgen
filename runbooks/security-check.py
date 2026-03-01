#!/usr/bin/env python3
"""
Security audit script for Kubernetes homelab cluster.

Runs all 11 security checks from security-check.md and writes results to
runbooks/security-check-current.md. All sensitive values (domain, name,
email) are loaded at runtime from SOPS / git config and redacted in output.

Usage:
    python3 runbooks/security-check.py

Output:
    runbooks/security-check-current.md
"""

import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

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

# ---------------------------------------------------------------------------
# Repo paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT  = SCRIPT_DIR.parent
OUTPUT     = SCRIPT_DIR / "security-check-current.md"

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
    git_name  = run("git config user.name")
    git_email = run("git config user.email")

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


# ---------------------------------------------------------------------------
# Elasticsearch port-forward context manager
# ---------------------------------------------------------------------------

class ElasticPortForward:
    def __init__(self):
        self._proc = None
        self._password = None

    def __enter__(self):
        # Kill any existing port-forward on 9200
        run("fuser -k 9200/tcp 2>/dev/null || true")
        time.sleep(0.5)

        self._proc = subprocess.Popen(
            "kubectl port-forward -n monitoring svc/elasticsearch-es-http 9200:9200",
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # Wait for port to open
        for _ in range(20):
            time.sleep(0.5)
            try:
                with socket.create_connection(("127.0.0.1", 9200), timeout=1):
                    break
            except OSError:
                continue

        raw = kubectl(
            "get secret elasticsearch-es-elastic-user -n monitoring "
            "-o jsonpath='{.data.elastic}'",
        )
        try:
            import base64
            self._password = base64.b64decode(raw.strip("'")).decode()
        except Exception:
            self._password = None
        return self

    def __exit__(self, *_):
        if self._proc:
            self._proc.terminate()
            self._proc.wait()
        run("fuser -k 9200/tcp 2>/dev/null || true")

    def query(self, body: dict, timeout: int = 15) -> dict | None:
        if not self._password:
            return None
        import base64 as b64
        auth = b64.b64encode(f"elastic:{self._password}".encode()).decode()
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            "https://localhost:9200/fluent-bit-*/_search",
            data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
        )
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return json.load(r)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Section implementations
# ---------------------------------------------------------------------------

def section_header(n: int, title: str) -> None:
    cprint(C.BLUE, f"\n[{n}/11] {title}")


def s1_sops_coverage() -> tuple[str, Findings, str]:
    section_header(1, "SOPS Encryption Coverage")
    f = Findings()
    lines = []

    # Unencrypted kind:Secret files
    unenc = run_lines(
        "grep -rl 'kind: Secret' kubernetes/ --include='*.yaml' | grep -v '\\.sops\\.yaml$'"
    )
    # Filter known false-positives (SecretKeyRef refs, SA tokens, kustomization refs)
    fp_patterns = ["helmrelease.yaml", "ks.yaml", "token-secret.yaml"]
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
                    "longhorn/app/helmrelease.yaml"]
    real_b64  = [h for h in b64_hits if not any(p in h for p in safe_content)]
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

    lines = [f.markdown()]
    return f.worst(), f, "\n".join(lines)


def s3_git_history() -> tuple[str, Findings, str]:
    section_header(3, "Git History Secret Scan")
    f = Findings()
    domain = _sensitive.get("DOMAIN", "")

    # Plaintext credential patterns
    cred_hits = run_lines(
        "git log --all --oneline -p "
        "| grep -iE '(password|secret|token|api.?key|private.?key)\\s*[:=]\\s*\\S{8,}' "
        "| grep -v 'sops\\|ENC\\[AES\\|secretKeyRef\\|valueFrom\\|EXAMPLE\\|your_"
        "\\|placeholder\\|changeme\\|SECRET_\\|\\${\\|process\\.env\\|__env\\|__file' "
        "| grep -v '^#\\|description:'"
    )
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

    return f.worst(), f, f.markdown()


def s5_authentik_logins(es: ElasticPortForward) -> tuple[str, Findings, str]:
    section_header(5, "Authentik Security Log Analysis")
    f = Findings()

    body = {
        "size": 50,
        "query": {"bool": {"must": [
            {"match": {"kubernetes.namespace_name": "kube-system"}},
            {"bool": {"should": [
                {"match_phrase": {"log": "Login failed"}},
                {"match_phrase": {"log": "Failed to authenticate"}},
                {"match_phrase": {"log": "invalid_grant"}},
                {"match_phrase": {"log": "FAILED_LOGIN"}},
                {"match_phrase": {"log": "Unsuccessful login"}},
            ]}},
        ], "filter": {"range": {"@timestamp": {"gte": "now-7d"}}}}},
        "aggs": {"by_ip": {"terms": {"field": "clientAddress.keyword", "size": 10}}},
    }

    data = es.query(body)
    if data is None:
        f.add(WARNING, "Elasticsearch unavailable — skipping Authentik log check")
        cprint(C.YELLOW, "  🟡 Elasticsearch query failed")
        return f.worst(), f, f.markdown()

    total = data["hits"]["total"]["value"]
    buckets = data.get("aggregations", {}).get("by_ip", {}).get("buckets", [])

    lines = [f"Failed login events (7d): **{total}**\n"]
    if total == 0:
        cprint(C.GREEN, "  🟢 No failed login events in 7 days")
    else:
        # Check for brute force: >20 failures from one IP
        for b in buckets:
            if b["doc_count"] > 20:
                f.add(CRITICAL, f"Brute force: {b['count']} failures from `{b['key']}`")
                cprint(C.RED, f"  🔴 Brute force: {b['doc_count']} failures from {b['key']}")
            else:
                f.add(WARNING, f"Failed logins from `{b['key']}`: {b['doc_count']}")
                cprint(C.YELLOW, f"  🟡 {b['doc_count']} failures from {b['key']}")
        lines.append("Top source IPs:\n")
        for b in buckets:
            lines.append(f"- {b['key']}: {b['doc_count']}\n")

    return f.worst(), f, "\n".join(lines)


def s6_attack_patterns(es: ElasticPortForward) -> tuple[str, Findings, str]:
    section_header(6, "External Service Attack Pattern Analysis")
    f = Findings()

    body = {
        "size": 50,
        "query": {"bool": {"must": [
            {"match": {"kubernetes.namespace_name": "network"}},
            {"bool": {"should": [
                {"match_phrase": {"log": "../"}},
                {"match_phrase": {"log": "etc/passwd"}},
                {"match_phrase": {"log": "SELECT "}},
                {"match_phrase": {"log": "<script"}},
                {"match_phrase": {"log": "wp-login"}},
                {"match_phrase": {"log": ".env"}},
                {"match_phrase": {"log": "phpMyAdmin"}},
                {"match_phrase": {"log": "cmd.exe"}},
                {"match_phrase": {"log": "/bin/sh"}},
                {"match_phrase": {"log": "UNION SELECT"}},
            ]}},
        ], "filter": {"range": {"@timestamp": {"gte": "now-24h"}}}}},
        "aggs": {"by_ip": {"terms": {"field": "remote_addr.keyword", "size": 10}}},
    }

    data = es.query(body)
    if data is None:
        f.add(WARNING, "Elasticsearch unavailable — skipping attack pattern check")
        cprint(C.YELLOW, "  🟡 Elasticsearch query failed")
        return f.worst(), f, f.markdown()

    total = data["hits"]["total"]["value"]
    buckets = data.get("aggregations", {}).get("by_ip", {}).get("buckets", [])

    lines = [f"Attack pattern hits (24h): **{total}**\n"]
    if total == 0:
        cprint(C.GREEN, "  🟢 No attack patterns in ingress logs (24h)")
    else:
        for b in buckets:
            if b["doc_count"] > 100:
                f.add(CRITICAL, f"Active scanner: {b['doc_count']} attack patterns from `{b['key']}`")
                cprint(C.RED, f"  🔴 {b['doc_count']} hits from {b['key']}")
            else:
                f.add(WARNING, f"{b['doc_count']} attack patterns from `{b['key']}`")
                cprint(C.YELLOW, f"  🟡 {b['doc_count']} hits from {b['key']}")
        lines.append("Top source IPs:\n")
        for b in buckets:
            lines.append(f"- {b['key']}: {b['doc_count']}\n")
        sample = [redact(h["_source"].get("log", "")[:120]) for h in data["hits"]["hits"][:5]]
        lines.append("Sample requests:\n")
        for s in sample:
            lines.append(f"- `{s}`\n")

    return f.worst(), f, "\n".join(lines)


def s7_rbac_pod_security() -> tuple[str, Findings, str]:
    section_header(7, "RBAC & Pod Security Audit")
    f = Findings()
    lines = []

    # Privileged containers in app namespaces
    INFRA_NS = {"kube-system", "storage", "monitoring", "network", "flux-system", "cert-manager"}
    pods = kubectl_json("get pods -A")
    if pods:
        privileged: list[str] = []
        root_uid:   list[str] = []
        host_net:   list[str] = []
        for p in pods["items"]:
            ns   = p["metadata"]["namespace"]
            name = p["metadata"]["name"]
            spec = p["spec"]
            psc  = spec.get("securityContext", {})
            for c in spec.get("containers", []) + spec.get("initContainers", []):
                sc = c.get("securityContext", {})
                if sc.get("privileged") and ns not in INFRA_NS:
                    privileged.append(f"`{ns}/{name}` ({c['name']})")
                uid = sc.get("runAsUser", psc.get("runAsUser"))
                if uid == 0 and ns not in INFRA_NS:
                    root_uid.append(f"`{ns}/{name}` ({c['name']})")
            if spec.get("hostNetwork") and ns not in INFRA_NS:
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
    section_header(8, "External Exposure Inventory")
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

    # Known accepted externals (without domain prefix)
    ACCEPTED = {
        "authentik-server", "flux-webhook", "langfuse", "uptime-kuma",
        "uptime-kuma-authentik-outpost", "nextcloud", "nextcloud-notify-push",
        "nextcloud-whiteboard", "paperless-ngx", "music-assistant-alexa-api",
        "music-assistant-alexa-stream", "absenty", "absenty-dev", "andreamosteller",
        "echo-server",  # accepted: intentional test endpoint
        "open-webui", "n8n", "iobroker", "tube-archivist", "jellyfin", "penpot",
        "home-assistant",
    }

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
    return f.worst(), f, "\n".join(lines)


def s9_certificates() -> tuple[str, Findings, str]:
    section_header(9, "Certificate Integrity")
    f = Findings()
    domain = _sensitive.get("DOMAIN", "")
    lines = []

    # cert-manager TLS secret
    raw = kubectl("get secret uhl-cool-production-tls -n cert-manager "
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
            issuer_m    = re.search(r'O = ([^,\n]+)', cert_text)
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
    section_header(10, "Flux Security Posture")
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

    # flux-operator cluster-admin
    crbs = kubectl_json("get clusterrolebindings 2>/dev/null")
    if crbs:
        for b in crbs.get("items", []):
            if b["roleRef"]["name"] == "cluster-admin":
                subjects = [s.get("name", "?") for s in b.get("subjects", [])]
                if any("flux" in s.lower() for s in subjects):
                    f.add(WARNING, f"Flux subject has cluster-admin: `{b['metadata']['name']}`")
                    checks.append(f"{WARNING} flux-operator has cluster-admin (standard but broad)")
                    cprint(C.YELLOW, "  🟡 flux-operator has cluster-admin (expected for GitOps)")

    lines.extend(f"- {c}\n" for c in checks)
    return f.worst(), f, "\n".join(lines)


def s11_unifi() -> tuple[str, Findings, str]:
    section_header(11, "UniFi Network Security Audit")
    f = Findings()
    lines = []

    # Device inventory — use 'device list' subcommand
    devices_raw = run("unifictl local device list 2>/dev/null", timeout=15)
    if not devices_raw or "login failed" in devices_raw:
        f.add(WARNING, "unifictl session expired — re-run `unifictl local configure`")
        cprint(C.YELLOW, "  🟡 unifictl session expired")
        return f.worst(), f, f.markdown()

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
        cprint(C.YELLOW, "  🟡 Could not parse event list")

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
    "RBAC & Pod Security",
    "External Exposure Inventory",
    "Certificate Integrity",
    "Flux Security Posture",
    "UniFi Network Security",
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

def main() -> int:
    os.chdir(REPO_ROOT)

    cprint(C.BOLD + C.BLUE, "=" * 60)
    cprint(C.BOLD + C.BLUE, " Security Audit — Kubernetes Homelab")
    cprint(C.BOLD + C.BLUE, "=" * 60)
    print(f"Date   : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Output : {OUTPUT}")
    print()

    if not load_sensitive():
        return 1

    cprint(C.CYAN, f"Sensitive vars loaded — DOMAIN={len(_sensitive['DOMAIN'])}c, "
                   f"NAME={len(_sensitive['NAME'])}c, EMAIL={len(_sensitive['EMAIL'])}c")

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

    # Sections 7-11: no Elasticsearch
    results.append(s7_rbac_pod_security())
    results.append(s8_external_exposure())
    results.append(s9_certificates())
    results.append(s10_flux_posture())
    results.append(s11_unifi())

    # Write report
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    write_report(timestamp, results)

    # Final summary
    total_crit = sum(1 for s, _, _ in results if s == CRITICAL)
    total_warn = sum(1 for s, _, _ in results if s == WARNING)
    total_ok   = sum(1 for s, _, _ in results if s == OK)

    print()
    cprint(C.BOLD + C.BLUE, "=" * 60)
    cprint(C.BOLD, f" Results: {total_crit} critical  {total_warn} warning  {total_ok} ok")
    cprint(C.BOLD + C.BLUE, "=" * 60)
    print(f"\nReport written to: {OUTPUT}\n")

    return 1 if total_crit > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
