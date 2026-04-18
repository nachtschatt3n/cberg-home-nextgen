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
from __future__ import annotations

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
            "https://localhost:9200/logs-generic-default/_search",
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
    cprint(C.BLUE, f"\n[{n}/12] {title}")


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
                    "longhorn/app/helmrelease.yaml",
                    "talos/clusterconfig/",  # Talos node configs contain expected inline certs/keys
                    "factory.talos.dev",     # Talos installer image URLs
                    "ghcr.io/siderolabs/installer",  # Talos installer images
                    "nodeAffinityPreset", "podAffinityPreset",  # Bitnami chart affinity YAML keys
                    "requiredDuringSchedulingIgnoredDuringExecution",  # K8s podAffinity field name
                    "preferredDuringSchedulingIgnoredDuringExecution", # K8s podAffinity field name
                    "/paperclip/instances/default/data/backups",  # shell path in backup-cleanup.yaml
                    "terminationGracePeriodSeconds",  # K8s pod spec field in JSON patch path
                    ]
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

    # Accepted risks: patterns in git history that have been reviewed and accepted
    ACCEPTED_CRED_PATTERNS = [
        'apiKey: "ollama"',            # Not a real secret — Ollama local API key placeholder
        'api_key: "ollama"',           # Same, snake_case variant
        "backupTargetCredentialSecret", # SecretRef name, not an actual secret value
        "bot-token: 6597763731",       # Telegram bot token — rotated, old value in history
        'os.environ.get(',             # Python env var read, never a value
        "existingSecret",              # Helm chart secretKeyRef field (existingSecret, existingSecretApiKey)
        "existingMaster",              # Helm chart existingMasterKeySecret field
        "envFromSecret:",              # Grafana Helm field referencing a secret name, not value
        "apiKey: ollamaKey",           # Python variable reference (ollamaKey is a var, not a value)
        "database.password=$DATABASE_PASS",  # Shell var expansion, not the value
        "=$(kubectl",                  # Shell pipeline reading from K8s (value retrieved at runtime, not in source)
        'token_resp.json().get(',      # Python code extracting token from response
        '"password:|api',              # grep regex search strings (not credential values)
        'kubectl create token',        # kubectl command that generates a token at runtime
        '--token="$TOKEN"',            # kubectl using shell $TOKEN var (value elsewhere)
        '--token=$TOKEN',              # Same, unquoted form
        "Mmih1SVbxAJMQY36",            # unpoller InfluxDB token — ROTATED in commit 74dec616
        "wN_jWa6cq00Ma1hOi",           # unpoller InfluxDB token — ROTATED in commit 74dec616
        "PC2kxlwtIRDd3teGNUKVm",       # unpoller InfluxDB token — ROTATED in commit d5be84ec
        "password: clickhouse123",     # langfuse clickhouse — rotated via SOPS
        "POSTGRES_PASSWORD: langfuse", # langfuse postgres — rotated via SOPS
        "X-Proxy-Secret",              # Nginx ingress header name (not a secret value, but matches "Secret")
        "KYmG4q@Vn366#_",              # OLD UniFi cli-adm password — ROTATED to new value
        "Secret: adguard-home-tls",    # TLS cert secret NAME reference, not a value
        "MC3lY6PQ2lkhP2z70Q1pw373",    # OLD Elasticsearch password — ES volume recreated since (2026-02)
        "github_token: Optional",      # Python function param type annotation (check-all-versions.py)
        "github_token=github_token",   # Python function call kwarg passing (not a value)
        "Uw04r2oij23oju2efji4ro834jri", # OLD SMB service worker password — moved to SOPS (commit 2b9e9469)
        "JTKQ8Qu69KNu1lWrs9tzMa75Vup", # OLD penpot DB password — moved to SOPS (commit 5668a907)
        "TebAWN8h2M3xGHkIUTH60",       # OLD Grafana OIDC client_secret — ROTATED 2026-04-18
        "0v0zon0PrpoHZt5yDdz5LXvJu",   # OLD pgadmin password — ROTATED 2026-04-17
        "IJGEQTcvzxEnFeDeCFJ8uMem",    # rybbit/clickhouse historical password — app removed
        "POSTGRES_PASSWORD: linkwarden123", # linkwarden historical password — moved to SOPS
        "POSTGRES_PASSWORD: bytebotpgpass2024secure", # bytebot historical — app removed
        "BETTER_AUTH_SECRET: ZtVI0L26IRoUi4S34Ki", # rybbit historical — app removed
        "better-auth-secret: ZtVI0L26IRoUi4S34Ki", # rybbit historical — app removed
        "rybbit-postgres-password",    # rybbit historical (secret-name placeholder ref) — app removed
        "rybbit-clickhouse-password",  # rybbit historical (secret-name placeholder ref) — app removed
        "GI6EWiGrGnOYg0kwLt75",        # k8s-mcp-server token — service replaced by ai-sre (commit 2703a173)
        "VXcwNHIyb2lqMjNvanUy",        # base64 of SMB password — accepted (same as Uw04r2oij above)
        "VXUwNHIyb2lqMjNvanUy",        # base64 typo variant of same — accepted
        "OWgzZm84aDNnZm8zaWhq",        # kopia KOPIA_PASSWORD/SERVER_PASSWORD base64 — kopia removed
        "credentialsSecret: aws-credentials-secret", # commented-out SecretRef, not a value
        "eyJpc3MiOiJiYzBlMWJmNjI5Yzg0ZWUyODhlYjBhMWNmM2ViNjYw", # HA long-lived token from deleted script commit 2b0665fd — CONFIRMED REVOKED 2026-04-18 (verified via HA UI)
        "serviceAccountSecret: influxdb-backup-key",   # commented-out SecretRef
        "storageAccountSecret: influxdb-backup-azure", # commented-out SecretRef
        'api_key: "{FRIGATE_GENAI_API_KEY}"',          # commented-out templated reference
    ]
    ACCEPTED_SECRET_FILES = {
        "templates/config/",           # Jinja2 templates, not actual secrets
        "kubernetes/flux/meta/repositories/helm/external-secrets.yaml",  # HelmRepository, not a secret
        "kubernetes/apps/download/icloud-docker/app-secrets/kustomization.yaml",  # Kustomization ref
        "kubernetes/apps/download/icloud-docker/secrets-ks.yaml",  # Kustomization ref
        # Historical secret-named files (reviewed 2026-04-17): all deleted from current tree
        "kubernetes/apps/ai/bytebot/app/secret.sops.tmp.yaml",  # Bytebot not deployed; creds not reused
        "kubernetes/apps/ai/langfuse/app/s3-credentials.yaml",  # Rotated in s3-credentials.sops.yaml
        "kubernetes/apps/backup/kopia/app/secret.yaml",  # Kopia not deployed
        "kubernetes/apps/databases/pgadmin/app/secret.sops.yaml.bak",  # Was sops-encrypted
        "kubernetes/apps/databases/pgadmin/app/secret.yaml",  # Rotated 2026-04-17 in secret.sops.yaml
        "kubernetes/apps/monitoring/headlamp/app/token-secret.yaml",  # ServiceAccountToken type, no value in file
        "kubernetes/apps/monitoring/rybbit/app/secret.sops.tmp.yaml",  # Rybbit not deployed
        "kubernetes/apps/monitoring/rybbit/clickhouse/secret.yaml",  # Rybbit not deployed
        "kubernetes/flux/meta/repositories/git/github-k8s-self-ai-ops-secret-temp.yaml",  # Placeholder only
    }

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

    return f.worst(), f, "\n".join(lines)


def s6a_error_rate_spikes(es: ElasticPortForward) -> tuple[str, Findings, str]:
    section_header(7, "Error Rate Spike Detection (ES)")
    f = Findings()
    lines: list[str] = []

    body = {
        "size": 0,
        "query": {"bool": {
            "should": [
                {"wildcard": {"body.text": "*ERROR*"}},
                {"wildcard": {"body.text": "*FATAL*"}},
            ],
            "minimum_should_match": 1,
            "filter": [{"range": {"@timestamp": {"gte": "now-7d"}}}],
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

    total_7d = data["hits"]["total"]["value"]
    hourly_avg = total_7d / 168 if total_7d > 0 else 0  # 7 days = 168 hours
    buckets = data.get("aggregations", {}).get("by_namespace", {}).get("buckets", [])

    spiking = []
    for b in buckets:
        ns = b["key"]
        ns_total = b["doc_count"]
        ns_last_1h = b["last_1h"]["doc_count"]
        ns_hourly_avg = ns_total / 168
        if ns_hourly_avg > 0 and ns_last_1h > 3 * ns_hourly_avg and ns_last_1h > 10:
            spiking.append((ns, ns_last_1h, ns_hourly_avg))

    if spiking:
        lines.append(f"**Error rate spikes detected** (last 1h vs 7d hourly avg):\n")
        for ns, last_1h, avg in spiking:
            ratio = last_1h / avg if avg > 0 else 0
            f.add(WARNING, f"Error spike in `{ns}`: {last_1h} errors/1h vs {avg:.1f}/h avg ({ratio:.1f}x)")
            cprint(C.YELLOW, f"  🟡 Spike: {ns} — {last_1h} errors/h (avg {avg:.1f}/h, {ratio:.1f}x)")
            lines.append(f"- `{ns}`: {last_1h} errors/1h vs {avg:.1f}/h avg ({ratio:.1f}x)\n")
    else:
        cprint(C.GREEN, f"  🟢 No error rate spikes (total 7d errors: {total_7d}, avg {hourly_avg:.0f}/h)")
        lines.append(f"No spikes. Total 7d errors: {total_7d}, avg {hourly_avg:.0f}/h\n")

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

    # Known accepted externals (without domain prefix)
    ACCEPTED = {
        "authentik-server", "flux-webhook", "langfuse", "uptime-kuma",
        "uptime-kuma-authentik-outpost", "nextcloud", "nextcloud-notify-push",
        "nextcloud-whiteboard", "paperless-ngx", "music-assistant-alexa-api",
        "music-assistant-alexa-stream", "absenty", "absenty-dev", "andreamosteller",
        "echo-server",  # accepted: intentional test endpoint
        "open-webui", "n8n", "iobroker", "tube-archivist", "jellyfin", "penpot",
        "home-assistant", "traccar", "librechat-librechat",
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
    devices_raw = run("unifictl local device list 2>/dev/null", timeout=15)
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
    "Error Rate Spike Detection (ES)",
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
        results.append(s6a_error_rate_spikes(es))

    # Sections 8-12: no Elasticsearch
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
