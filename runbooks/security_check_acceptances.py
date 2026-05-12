"""Accepted exceptions for security-check.py.

Kept separate from the main 1700-line audit script so credential rotations,
false-positive whitelists, and intentionally-public ingress lists can be
edited without touching the scanner code.

Each constant has a corresponding section in security-check.py:

  GIT_HISTORY_CRED_PATTERNS  -> s3_git_history (section 3)
  GIT_HISTORY_SECRET_FILES   -> s3_git_history (section 3)
  EXTERNAL_INGRESS_ACCEPTED  -> s8_external_exposure (section 9)

When you add an entry, also link the matching AR-ID from
docs/security-accepted-risks.md in the inline comment so future operators
can see why something is whitelisted.
"""
from __future__ import annotations


# ─── Section 3 (git history) — credential-shaped strings that are exceptions ──
# Reasons fall into three groups:
#   (a) ROTATED — value was a real credential at some point but has since
#       been rotated; old value lives in commit history but is dead.
#   (b) PLACEHOLDER — string looks like a secret but is a config marker
#       (Ollama API key, kubectl-create-token output template, etc.).
#   (c) CODE PATTERN — Python/shell code referring to a secret variable,
#       not the value itself (env var read, kwarg passing, regex search).
GIT_HISTORY_CRED_PATTERNS: list[str] = [
    'apiKey: "ollama"',                               # PLACEHOLDER — Ollama local API key marker
    'api_key: "ollama"',                              # PLACEHOLDER — same, snake_case variant
    "backupTargetCredentialSecret",                   # CODE PATTERN — SecretRef name, not a value
    "bot-token: 6597763731",                          # ROTATED — Telegram bot token
    'os.environ.get(',                                # CODE PATTERN — Python env var read
    "existingSecret",                                 # CODE PATTERN — Helm chart secretKeyRef field
    "existingMaster",                                 # CODE PATTERN — Helm existingMasterKeySecret field
    "envFromSecret:",                                 # CODE PATTERN — Grafana Helm field
    "apiKey: ollamaKey",                              # CODE PATTERN — Python variable reference
    "database.password=$DATABASE_PASS",               # CODE PATTERN — shell var expansion
    "=$(kubectl",                                     # CODE PATTERN — shell pipeline reading from K8s
    'token_resp.json().get(',                         # CODE PATTERN — Python extracting token from response
    '"password:|api',                                 # CODE PATTERN — grep regex search
    'kubectl create token',                           # CODE PATTERN — kubectl runtime command
    '--token="$TOKEN"',                               # CODE PATTERN — kubectl using shell var
    '--token=$TOKEN',                                 # CODE PATTERN — same, unquoted
    "Mmih1SVbxAJMQY36",                               # ROTATED — unpoller InfluxDB token (commit 74dec616)
    "wN_jWa6cq00Ma1hOi",                              # ROTATED — unpoller InfluxDB token (commit 74dec616)
    "PC2kxlwtIRDd3teGNUKVm",                          # ROTATED — unpoller InfluxDB token (commit d5be84ec)
    "password: clickhouse123",                        # ROTATED — langfuse clickhouse, moved to SOPS
    "POSTGRES_PASSWORD: langfuse",                    # ROTATED — langfuse postgres, moved to SOPS
    "X-Proxy-Secret",                                 # PLACEHOLDER — Nginx ingress header name
    "KYmG4q@Vn366#_",                                 # ROTATED — UniFi cli-adm password
    "Secret: adguard-home-tls",                       # CODE PATTERN — TLS cert secret name reference
    "MC3lY6PQ2lkhP2z70Q1pw373",                       # ROTATED — Elasticsearch password (volume recreated 2026-02)
    "github_token: Optional",                         # CODE PATTERN — Python type annotation
    "github_token=github_token",                      # CODE PATTERN — Python kwarg passing
    "Uw04r2oij23oju2efji4ro834jri",                   # ROTATED — SMB service worker (commit 2b9e9469)
    "JTKQ8Qu69KNu1lWrs9tzMa75Vup",                    # ROTATED — penpot DB (commit 5668a907)
    "TebAWN8h2M3xGHkIUTH60",                          # ROTATED — Grafana OIDC client_secret (2026-04-18)
    "0v0zon0PrpoHZt5yDdz5LXvJu",                      # ROTATED — pgadmin password (2026-04-17)
    "IJGEQTcvzxEnFeDeCFJ8uMem",                       # APP-REMOVED — rybbit/clickhouse historical
    "POSTGRES_PASSWORD: linkwarden123",               # ROTATED — linkwarden, moved to SOPS
    "POSTGRES_PASSWORD: bytebotpgpass2024secure",     # APP-REMOVED — bytebot historical
    "BETTER_AUTH_SECRET: ZtVI0L26IRoUi4S34Ki",        # APP-REMOVED — rybbit historical
    "better-auth-secret: ZtVI0L26IRoUi4S34Ki",        # APP-REMOVED — rybbit historical
    "rybbit-postgres-password",                       # APP-REMOVED — secret-name placeholder ref
    "rybbit-clickhouse-password",                     # APP-REMOVED — secret-name placeholder ref
    "GI6EWiGrGnOYg0kwLt75",                           # SERVICE-REPLACED — k8s-mcp-server token (commit 2703a173)
    "VXcwNHIyb2lqMjNvanUy",                           # ROTATED — base64 of SMB password (same as Uw04r2oij)
    "VXUwNHIyb2lqMjNvanUy",                           # ROTATED — base64 typo variant of same
    "OWgzZm84aDNnZm8zaWhq",                           # APP-REMOVED — kopia KOPIA_PASSWORD/SERVER_PASSWORD base64
    "credentialsSecret: aws-credentials-secret",      # CODE PATTERN — commented-out SecretRef
    "eyJpc3MiOiJiYzBlMWJmNjI5Yzg0ZWUyODhlYjBhMWNmM2ViNjYw",  # REVOKED — HA long-lived token (verified via HA UI 2026-04-18)
    "serviceAccountSecret: influxdb-backup-key",      # CODE PATTERN — commented-out SecretRef
    "storageAccountSecret: influxdb-backup-azure",    # CODE PATTERN — commented-out SecretRef
    'api_key: "{FRIGATE_GENAI_API_KEY}"',             # CODE PATTERN — commented-out templated reference
    'VNC_PASSWORD = env(',                            # CODE PATTERN — solarfocus-scraper env var read
    'password=VNC_PASSWORD',                          # CODE PATTERN — solarfocus-scraper variable reference
]

# Files whose names match secret-named patterns but are not actual secret
# storage. Either Helm/Kustomize references, deleted historical files, or
# Jinja2 templates.
GIT_HISTORY_SECRET_FILES: set[str] = {
    "templates/config/",                                                    # Jinja2 templates
    "kubernetes/flux/meta/repositories/helm/external-secrets.yaml",         # HelmRepository, not a secret
    "kubernetes/apps/download/icloud-docker/app-secrets/kustomization.yaml",  # Kustomization ref
    "kubernetes/apps/download/icloud-docker/secrets-ks.yaml",               # Kustomization ref
    # Historical secret-named files (reviewed 2026-04-17): all deleted from current tree
    "kubernetes/apps/ai/bytebot/app/secret.sops.tmp.yaml",                  # APP-REMOVED — bytebot
    "kubernetes/apps/ai/langfuse/app/s3-credentials.yaml",                  # ROTATED — in s3-credentials.sops.yaml
    "kubernetes/apps/backup/kopia/app/secret.yaml",                         # APP-REMOVED — kopia
    "kubernetes/apps/databases/pgadmin/app/secret.sops.yaml.bak",           # PLACEHOLDER — was sops-encrypted
    "kubernetes/apps/databases/pgadmin/app/secret.yaml",                    # ROTATED — 2026-04-17 in secret.sops.yaml
    "kubernetes/apps/monitoring/headlamp/app/token-secret.yaml",            # CODE PATTERN — ServiceAccountToken type, no value
    "kubernetes/apps/monitoring/rybbit/app/secret.sops.tmp.yaml",           # APP-REMOVED — rybbit
    "kubernetes/apps/monitoring/rybbit/clickhouse/secret.yaml",             # APP-REMOVED — rybbit
    "kubernetes/flux/meta/repositories/git/github-k8s-self-ai-ops-secret-temp.yaml",  # PLACEHOLDER
}

# ─── Section 9 (external ingress) — intentionally-public apps ────────────────
# Each entry has a matching rationale in docs/security-accepted-risks.md.
# AR-003: debug/test endpoints (echo-server)
# AR-004: apps with their own MFA-capable native auth (open-webui, n8n, etc.)
# AR-007: apps with non-Authentik-compatible protocol clients (nextcloud,
#         jellyfin, paperless, etc.) OR explicitly public-facing (rainbow-rescue,
#         andreamosteller).
# AR-012: HMAC-validated webhook receivers (flux-webhook).
EXTERNAL_INGRESS_ACCEPTED: set[str] = {
    "authentik-server",                  # AR-004 — IdP itself
    "flux-webhook",                      # AR-012 — HMAC-validated GitHub webhook
    "langfuse",                          # AR-007 — app-native NextAuth.js
    "uptime-kuma",                       # AR-005 — app-native auth
    "uptime-kuma-authentik-outpost",     # AR-005 — outpost path only
    "nextcloud",                         # AR-007 — protocol clients (CalDAV/CardDAV/WebDAV/Basic-Auth)
    "nextcloud-notify-push",             # AR-007 — same as nextcloud
    "nextcloud-whiteboard",              # AR-007 — same as nextcloud
    "paperless-ngx",                     # AR-007 — app-native auth
    "music-assistant-alexa-api",         # AR-004 — HMAC-validated Alexa webhook
    "music-assistant-alexa-stream",      # AR-004 — ephemeral signed URLs
    "absenty",                           # AR-007 — app-native auth (employee portal)
    "absenty-dev",                       # AR-007 — same as absenty
    "andreamosteller",                   # AR-007 — intentionally public portfolio
    "echo-server",                       # AR-003 — intentional debug test endpoint
    "open-webui",                        # AR-004 — app-native auth
    "n8n",                               # AR-004 — app-native + 2FA
    "iobroker",                          # AR-004 — app-native auth
    "tube-archivist",                    # AR-007 — app-native auth
    "jellyfin",                          # AR-007 — app-native auth
    "penpot",                            # AR-007 — app-native auth (registration disabled)
    "home-assistant",                    # AR-007 — app-native + MFA
    "traccar",                           # AR-007 — app-native auth
    "librechat-librechat",               # AR-007 — app-native auth
    "rainbow-rescue",                    # AR-007 line 123 — intentionally public PWA, no user data
    "gas-price-monitor",                 # AR-027 — read-only public-data ETL output, no PII
}
