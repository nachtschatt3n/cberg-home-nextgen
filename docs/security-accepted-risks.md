# Security Accepted Risks

> Risks reviewed and explicitly accepted. Do not surface these in automated audits as actionable items.
> Last reviewed: 2026-05-04

---

## AR-001 — Plaintext Secrets in Public Git History

**Severity at time of discovery:** Critical
**Status:** Accepted — all secrets rotated or services decommissioned

Six secrets were committed in plaintext to the public repository history. All have been remediated:

| Commit | Service | Secret | Remediation |
|--------|---------|--------|-------------|
| `883de1d2` | Langfuse MinIO | `minioadmin`/`minioadmin` (default) | Rotated 2026-03-20 |
| `1f9319c0` | Kopia backup | Encryption + server password | Service decommissioned |
| `bb2bf972` | pgAdmin | Admin + master password | Rotated 2026-03-19, pod restarted 2026-03-20 |
| `6b335828` | Rybbit | `BETTER_AUTH_SECRET` JWT key | Service decommissioned |
| `6b335828` | Rybbit ClickHouse | Admin password (`kubernetes/apps/monitoring/rybbit/clickhouse/secret.yaml`) | Service decommissioned |
| `4aa30e55` | Bytebot | PostgreSQL password + DB URL | Service decommissioned |
| `0f86a14a` | Longhorn | Telegram bot token | Rotated 2026-04-05 via BotFather |
| `00580874` | UniFi Controller (`cli-adm`) | Controller admin password | Rotation confirmed (current credential differs); file gitignored 2026-03-09 |

History cannot be rewritten on a public repo with potential clones. Rotation is the remediation. Risk accepted.

**Root cause:** Files named `.sops.tmp.yaml` committed before encryption ran, or files committed before SOPS encryption was applied. Mitigated by `.gitignore` rule covering `*.sops.tmp.yaml`.

---

## AR-002 — Mosquitto MQTT `allow_anonymous true`

**Severity at time of discovery:** Warning
**Status:** Accepted — IoT network, internal only

Mosquitto is configured with `allow_anonymous true` alongside a `password_file`. This means the password file is not enforced and any client can connect without credentials.

**Why accepted:** Mosquitto is only accessible within the IoT VLAN (192.168.32.0/23) and the Kubernetes cluster network (192.168.55.0/24). No external exposure. All IoT devices are on a segmented VLAN with restricted inter-VLAN routing. Anonymous MQTT is standard practice in private IoT deployments.

---

## AR-003 — echo-server on External Ingress Without Auth

**Severity at time of discovery:** Warning
**Status:** Accepted — debug tool, intentional exposure

`default/echo-server` is exposed on the external ingress class without Authentik forward auth. It reflects all HTTP request headers to the caller.

**Why accepted:** This is an intentional debug/testing endpoint. No sensitive data is stored or processed. Header reflection is the design purpose. Accepted as a low-risk operational tool.

---

## AR-004 — External Apps Without Authentik Forward Auth

**Severity at time of discovery:** Warning
**Status:** Accepted — each app has its own authentication layer

The following apps are on the external ingress class without Authentik forward auth:

| App | Namespace | Own Auth |
|-----|-----------|----------|
| open-webui | ai | Built-in user auth with admin-controlled access |
| n8n | home-automation | Built-in user auth + 2FA support |
| iobroker | home-automation | Built-in user auth |
| home-assistant | home-automation | Built-in user auth with MFA support |
| nextcloud-notify-push | office | Companion WebSocket endpoint for the Nextcloud client push protocol — Authentik forward-auth would break the long-lived WS handshake that mobile/desktop clients require. Auth is enforced upstream by Nextcloud (token-bound to user session). |
| nextcloud-whiteboard-proxy | office | Internal Yjs/CRDT websocket relay for the Nextcloud Whiteboard app — token-gated by Nextcloud session; Authentik forward-auth incompatible with the protocol upgrade. |
| music-assistant-alexa-api | home-automation | Smart-speaker companion endpoint expected to be reachable by Alexa cloud webhooks — adding Authentik would block the upstream callback. Requests are HMAC-validated by the app. |
| music-assistant-alexa-stream | home-automation | Audio stream endpoint consumed by Alexa devices over HTTP range requests — must remain unauthenticated at the proxy layer; bound to ephemeral signed URLs by the app. |

**Why accepted:** The first four apps have robust application-level authentication and adding Authentik would double-prompt without security gain. The four `nextcloud-*` / `music-assistant-*` endpoints are protocol/companion endpoints where forward-auth would break the upstream integration; auth is enforced one layer up (Nextcloud session, signed URL, or HMAC).

---

## AR-005 — Uptime-Kuma External Ingress Without Authentik Forward Auth

**Severity at time of discovery:** Warning
**Status:** Accepted — application has its own authentication layer

Uptime-Kuma is exposed on the external ingress class. The companion `uptime-kuma-authentik-outpost` ingress handles the Authentik callback path only and does not gate the main app.

**Why accepted:** Uptime-Kuma has its own built-in user authentication (username + password required on first access). No sensitive infrastructure data is exposed without login. The status page feature, if used, is intentionally public by design. Risk is limited to information disclosure of service names/URLs to unauthenticated internet users.

---

## AR-006 — Node-RED Running as Root and Without Authentik on Internal Ingress

**Severity at time of discovery:** Warning
**Status:** Accepted — application has its own authentication; root justified by PVC compatibility

Node-RED runs as `uid=0` with the internal ingress lacking Authentik forward auth annotations.

**Investigation result (2026-03-27):** Installed extensions (`node-red-contrib-home-assistant-websocket`, `node-red-contrib-cron-plus`, and utility libraries) do not require root privileges. Root is set for PVC data volume permission compatibility and was not introduced for a specific extension requirement.

**Why accepted:**
- Node-RED has its own built-in admin authentication (`adminAuth`). Access requires credentials.
- Internal ingress only — not reachable from the internet; only accessible within the cluster network and trusted VLANs.
- Root on PVC volumes is a common pattern in homelab deployments where fsGroup/runAsUser migration would require chown of existing data.

---

## AR-007 — Additional External Services Without Authentik Forward Auth

**Severity at time of discovery:** Warning
**Status:** Accepted — each service has its own authentication or is intentionally public

The following services are on the external ingress class without Authentik forward auth, in addition to those covered by AR-004:

| App | Namespace | Own Auth / Justification |
|-----|-----------|--------------------------|
| librechat | ai | Built-in user auth (registration controlled by admin) |
| tube-archivist | download | Built-in user auth required |
| traccar | home-automation | Built-in user auth; GPS data access requires login |
| penpot | office | Built-in user auth; registration disabled (`disable-registration` flag), only pre-existing accounts can log in |
| jellyfin | media | Built-in user auth required before any media access |
| absenty (dev) | my-software-development | Built-in app auth; development instance |
| absenty (prod) | my-software-production | Built-in app auth; employee-facing service |
| andreamosteller (prod) | my-software-production | Intentionally public portfolio/website — no auth required |
| langfuse | ai | Built-in user auth; SSO/email login required before any project/observability data access |
| paperless-ngx | office | Built-in user auth; document library inaccessible without login |
| nextcloud | office | Built-in user auth with MFA support, brute-force protection, and account lockout. Authentik forward-auth would conflict with CalDAV/CardDAV/WebDAV/desktop-sync clients that use Basic Auth or app passwords — those clients cannot complete an OAuth redirect flow. |
| rainbow-rescue | my-software-production | Intentionally public PWA — offline-capable kids party hunt app with no user data or login surface. |

**Why accepted:** All services with private data require authentication before access. `andreamosteller` and `rainbow-rescue` are intentionally public-facing apps with no user data or authentication surface by design. `langfuse`, `paperless-ngx`, and `nextcloud` ship robust first-party auth and adding Authentik on top would double-prompt with no incremental security benefit (same rationale as AR-004). `nextcloud` additionally cannot use Authentik forward-auth because it would break protocol clients (CalDAV/CardDAV/WebDAV/desktop sync) that use Basic Auth or app passwords.

**Last reviewed:** 2026-05-06

---

## AR-008 — Headlamp cluster-admin ClusterRoleBinding

**Severity at time of discovery:** Warning
**Status:** Accepted — administrative tool by design

The `headlamp` ServiceAccount is bound to `cluster-admin` via `clusterrolebinding/headlamp-admin`. No long-lived token Secret exists in the cluster.

**Why accepted:** Headlamp is a Kubernetes cluster administration UI. Full cluster read/write access is the intended and required permission scope for the tool to function. The ingress is protected by Authentik forward auth on the internal ingress class, limiting access to authenticated users only. The risk surface is equivalent to granting a cluster admin user access to the dashboard.

---

## AR-009 — Privileged Containers (otbr, frigate, scrypted-nvr, jellyfin, makemkv) and hostNetwork Pods for Hardware Access

**Severity at time of discovery:** Warning
**Status:** Accepted — hardware device access required by design

The following containers run with elevated privileges or `hostNetwork: true`:

| App | Namespace | Privilege Level | Justification |
|-----|-----------|----------------|---------------|
| frigate-nvr | home-automation | Privileged | Direct access to capture cards (`/dev/video*`) and GPU for NVR hardware transcoding |
| otbr | home-automation | Privileged | Network interface manipulation required for OpenThread Border Router (Thread radio) |
| scrypted-nvr | home-automation | Privileged + uid=0 | Hardware transcoding, device passthrough, and SYS_ADMIN for camera NVR/proxy |
| jellyfin | media | Privileged + SYS_ADMIN | iGPU hardware transcoding via Intel Quick Sync |
| makemkv | media | Privileged | Raw device access for Blu-ray/DVD drive passthrough |
| node-red | home-automation | uid=0 | PVC volume permission compatibility (see AR-006) |
| icloud-docker-mu | backup | uid=0 | File operations on mounted iCloud sync volume |

**hostNetwork pods** (home-assistant, esphome, matter-server, music-assistant-server, otbr): Required for LAN device discovery protocols (mDNS, multicast, Zigbee/Thread/Matter device communication). Standard pattern for home-automation workloads.

| openclaw | ai | uid=0 init container | Init container `install-openclaw` runs as root for package installation; main app runs as uid=1000 |
| paperclip | ai | uid=0 (tools container) | Sidecar `tools` container runs as root for system utilities |
| memgraph | databases | Privileged init container | `init-sysctl` sets vm.max_map_count; requires privilege escalation for kernel tuning |

**Why accepted:** All privileged containers are in `home-automation`, `media`, `ai`, and `databases` namespaces where direct hardware access or system tuning is a functional requirement. All pods are on the internal cluster network with no direct external exposure.

---

## AR-011 — flux-operator cluster-admin ClusterRoleBinding

**Severity at time of discovery:** Warning
**Status:** Accepted — standard GitOps pattern

The `flux-operator` ServiceAccount is bound to `cluster-admin`. This is surfaced by RBAC audits as a wildcard permission finding.

**Why accepted:** Flux requires cluster-wide read/write access to reconcile all namespaces and resource types. This is the standard and recommended Flux deployment pattern. The operator only acts on git-committed manifests gated by branch protection and webhook authentication. The risk surface is equivalent to any GitOps controller and is mitigated by the Flux webhook `secretRef` and GitHub branch protections.

---

## AR-010 — Bundled MariaDB Instances Using Frozen Legacy Image

**Severity at time of discovery:** Warning
**Status:** Accepted — functional, internal-only, migration deferred

Application charts bundle database/cache sub-charts using `bitnamilegacy/*` images — a frozen archive registry that will never receive security patches:

| App | Namespace | Pod | Image | Version | Database |
|-----|-----------|-----|-------|---------|----------|
| Nextcloud | office | `nextcloud-mariadb-0` | `bitnamilegacy/mariadb` | 11.8.2 | nextcloud (199 tables) |
| Paperless-NGX | office | `paperless-ngx-mariadb-0` | `bitnamilegacy/mariadb` | 11.8.2 | paperless (72 tables) |
| Superset | databases | `superset-postgresql-0` | `bitnamilegacy/postgresql` | bundled | superset metadata |
| Superset | databases | `superset-redis-master-0` | `bitnamilegacy/redis` | bundled | superset task queue |

**Why accepted:**
- All instances are internal-only with no external ingress exposure
- Legacy images are frozen but stable — no new vulnerabilities introduced by code changes
- MariaDB: migration requires 11.8 → 12.x major version jump with dump/restore (Nextcloud, Paperless-NGX)
- Superset: bundled sub-charts are upstream chart defaults; overriding to `bitnami/*` requires chart values changes and data migration
- The standalone MariaDB in `databases/` was upgraded to chart 25.0.6 (MariaDB 12.0.2) in February 2026

**Future action:** Migrate all four bundled instances to `bitnami/*` equivalents during planned maintenance windows. MariaDB instances require mysqldump + restore; Superset instances require pg_dump + Redis flush + sub-chart image override.

---

## AR-015 — Superset Root Containers and Longhorn Bench DaemonSet (Undeployed)

**Severity at time of discovery:** Warning
**Status:** Accepted — internal-only exposure; bench manifest is not Flux-managed

**Superset root containers:** Apache Superset (`databases/superset`) deploys four pod variants (`superset`, `superset-celerybeat`, `superset-worker`, `superset-init-db`) using `apache/superset:5.0.0`, which runs as root (uid=0) by default. This is the upstream chart default and matches the same pattern as AR-006 (Node-RED) and AR-009 (privileged containers for hardware access).

**Why accepted:**
- Superset is on `internal` ingress only — no external exposure.
- Root is the upstream image default; overriding requires custom entrypoint or init-container chown, adding maintenance overhead disproportionate to the risk.
- Internal network access is required to reach Superset; no anonymous or unauthenticated path exists.

**Longhorn bench DaemonSet:** `kubernetes/apps/storage/longhorn/bench/loopback-daemonset.yaml` exists in the public repo and contains a privileged DaemonSet with `hostPID: true` and hostPath mounts to `/dev` and `/var`. The file header documents it as NOT auto-deployed; it is not referenced in any Kustomization and cannot be applied by Flux reconciliation.

**Why accepted:**
- The manifest is excluded from all Kustomization entrypoints — Flux cannot apply it.
- It requires an explicit `kubectl apply -f` with cluster access to take effect.
- The risk is limited to insider/contributor misuse, not external attack surface.
- File is retained as an operational reference for Longhorn v2 SPDK benchmarking.

---

## AR-012 — flux-webhook External Ingress Without Authentik Forward Auth

**Severity at time of discovery:** Warning
**Status:** Accepted — HMAC-gated by design; Authentik forward auth would break webhook delivery

The `flux-webhook` ingress (`flux-system/webhook-receiver`) is exposed on the external ingress class without Authentik forward auth.

**Why accepted:**
- The webhook must be reachable by GitHub's outbound webhook delivery system. Authentik forward auth would intercept the request with a 302 to the IdP login page, which GitHub's webhook poster cannot follow — every push event would fail.
- Authentication is enforced at the application layer by the Flux Receiver: each request is validated against an HMAC-SHA256 signature using a shared secret bound to the GitHub repository's webhook configuration. Requests with missing or invalid `X-Hub-Signature-256` headers are rejected before any reconciliation runs.
- Path is scoped: the receiver only accepts pushes that match the configured GitRepository resource and triggers a reconcile of the configured Kustomization tree. No arbitrary command execution, no payload introspection beyond the commit SHA.
- Risk surface: an attacker would need both the public webhook URL and the HMAC secret to forge a request, at which point they could only trigger an early reconcile of the already-committed `main` — not inject code.

**Mitigation:** Rotate the HMAC secret if the repo or webhook configuration is compromised. Webhook secret stored encrypted in `kubernetes/apps/flux-system/webhooks/app/*.sops.yaml`.

---

## AR-013 — `monitoring` Namespace PSA Enforced by Multiple Independent Kustomizations

**Severity at time of discovery:** Informational
**Status:** Accepted — structural consequence of OTel DaemonSet hostPath requirement

The `monitoring` namespace carries `pod-security.kubernetes.io/enforce: privileged` because the `edot-collector` DaemonSet mounts `hostPath` volumes for log and metric collection. This label is set redundantly by three independent Flux Kustomizations (`eck-operator`, `elasticsearch`, `kibana`) in addition to the top-level `monitoring/kustomization.yaml`.

**Why accepted:**
- The `privileged` PSA level is required by design — edot-collector's hostPath mounts are blocked by `baseline` PSA.
- The redundancy was introduced deliberately in commit `6ee8fbc3` (2026-05-02) to prevent a Flux reconcile-ordering race condition: whichever Kustomization reconciles last wins the namespace label. Without the redundancy, any of the three ECK Kustomizations could silently revert the label to `baseline`, breaking the DaemonSet.
- The `monitoring` namespace has no external exposure; all privileged pods are for internal observability only (see AR-009 for the hardware-access justified privileged pods).

**Invariant to enforce:** Any new Kustomization added to the `monitoring` namespace must include the `pod-security.kubernetes.io/enforce: privileged` patch. See `docs/sops/monitoring.md` troubleshooting section for the full procedure if the label is reset.

---

## AR-014 — `ai-sre` Cluster-Wide Secret Read and SOPS Age Key Mount

**Severity at time of discovery:** Warning
**Status:** Accepted — internal-only, no external ingress

The `ai-sre` ClusterRole grants `get/list/watch` on `secrets` across all namespaces, and the HelmRelease mounts the SOPS age private key at `/app/secrets/age-key.txt`. The MCP API endpoint runs with `REQUIRE_AUTH: false`.

**Why accepted:**
- Ingress is `enabled: false` — the MCP endpoint is reachable only cluster-internally at `ai-sre.ai.svc.cluster.local:8080`. No external or internal-ingress exposure.
- The SRE agent requires cluster-wide diagnostic access by design, including Secret metadata. The SOPS age key enables the agent to decrypt secrets for diagnostic SOPS operations.
- `REQUIRE_AUTH: false` is intentional for local in-cluster MCP use; the blast radius is limited to other pods in the cluster that can reach the ai namespace.
- No NetworkPolicy currently restricts ingress to `ai-sre` — this is the open item if the risk posture tightens.

**Mitigations in place:** No external exposure; cluster-internal access only. If the `ai` namespace is compromised, this is an escalation path to all cluster secrets.

**Future remediation if needed:** Enable `REQUIRE_AUTH: true` using the MCP_AUTH_TOKEN already in the SOPS secret, and add a NetworkPolicy restricting ingress to known MCP client pods only.

---

## AR-016 — Personal Domain in Git History (AdGuard Home + Superset)

**Severity at time of discovery:** Info
**Status:** Accepted — informational exposure only; all live manifests use `${SECRET_DOMAIN}`

The personal domain name was committed in plaintext in two separate HelmReleases, both subsequently remediated:

1. **AdGuard Home** (`upstream_dns` block, commit `8eab2f60`, 2026-02-XX): two split-horizon DNS routing entries (`[/kuma.${SECRET_DOMAIN}/]` and `[/${SECRET_DOMAIN}/]`). Replaced with `${SECRET_DOMAIN}` substitutions in commit `<current>` (2026-05-04).

2. **Superset** (OIDC metadata URL + admin email field, commits `5bd295dd` and `c3b9694d`, 2026-04-18): original deploy used the literal domain in the OIDC configuration. Fixed the same day in commit `c3b9694d`. Current file is clean.

**Why accepted:** The exposure is informational — the personal domain is not a credential and does not enable any direct attack. Git history cannot be rewritten on a public repo with potential clones. All live manifests now use `${SECRET_DOMAIN}` substitution.

**Last reviewed:** 2026-05-06

---

## AR-017 — Template Secret Files Without SOPS Path Coverage

**Severity at time of discovery:** Info
**Status:** Accepted — placeholder values only; warning comments added

Two template files in the `my-software-development/_template/` directory contain `kind: Secret` scaffolding with placeholder values:
- `kubernetes/apps/my-software-development/_template/app/secrets.example.yaml`
- `kubernetes/apps/my-software-development/_template/app/ghcr-secret.example.yaml`

These files are named `*.example.yaml`, not `*.sops.yaml`, so they are not covered by the SOPS `kubernetes/.*\.sops\.ya?ml` path rule. A developer could fill in real values and accidentally commit the `.example.yaml` file unencrypted.

**Why accepted:** All current values are placeholders (`<github-personal-access-token>`, `<base64-encoded-docker-config>`, etc.) — no credentials are exposed. The files are not referenced by any Flux Kustomization and cannot be applied to the cluster. Warning comments were added to both files (2026-05-05) directing developers to copy-then-rename to `.sops.yaml` before filling in real values.

**Last reviewed:** 2026-05-05

---

## AR-018 — KubeClientCertificateExpiration False Positive (Prometheus Histogram Artifact)

**Severity at time of discovery:** Info
**Status:** Accepted — false positive, all actual client certificates are valid

The `KubeClientCertificateExpiration` Prometheus alert fires against all three apiserver instances because the `apiserver_client_certificate_expiration_seconds` histogram permanently accumulates observations across the lifetime of the Prometheus pod. When the kubelet client certificate is auto-rotated by Kubernetes (which it is, automatically, before 80% of its 1-year validity), the final seconds of the old certificate's validity are recorded as histogram samples in the low-expiry buckets. These samples are never evicted. The alert expression checks if any bucket `le < 86400` has non-zero count, which is always true after the first rotation cycle.

**Evidence (verified 2026-05-05):** All actual client certificates valid:
- Kubelet client cert on all 3 nodes (`system:node:k8s-nuc14-0{1,2,3}`): expires Jan 5, 2027
- Admin kubeconfig cert: expires Jan 5, 2027
- Apiserver TLS cert: expires May 4, 2027
- Prometheus histogram count: 600,453 accumulated observations on nuc14-03

**Why accepted:** Well-known upstream kube-prometheus-stack false positive. Fixing it requires overriding the built-in PrometheusRule with a custom `increase()`-based expression. For this homelab, the alert is permanent noise — treat as accepted. To verify real cert health use `talosctl -n <ip> read /var/lib/kubelet/pki/kubelet-client-current.pem | openssl x509 -noout -dates`.

**Security agent note:** Do not surface this as a finding. Verify actual cert expiry directly via talosctl when assessing certificate health.

**Last reviewed:** 2026-05-05

---

## AR-019 — CVE-2024-42025 UniFi Network Application (Not Applicable)

**Severity at time of discovery:** Info (version scanner false positive)
**Status:** Accepted — not applicable to this installation

CVE-2024-42025 (CVSS 7.8) is a command-injection privilege escalation in UniFi Network Application versions prior to 8.4.59. Automated version scanners flag this because the UniFi controller's Network Application version is not directly exposed via the `unifictl` API — the `version` field returns the UniFi OS version, which cannot be trivially compared to the Network Application versioning scheme.

**Why not applicable:** The gateway `DMP-CBERG` (UDMPRO) runs UniFi OS **5.0.16.30692** (verified 2026-05-05 via `unifictl local device list`). UniFi OS 5.x ships with Network Application 9.x, which is well above the 8.4.59 patched version. The CVE is not present.

**Mapping:**
- UniFi OS 4.x → Network App 8.x (vulnerable if < 4.0.21 / Network App 8.4.59)
- UniFi OS 5.x → Network App 9.x → **not vulnerable**

**Version agent note:** Do not escalate CVE-2024-42025 as a finding. The automated check in `runbooks/security-check.md` §11.1 evaluates the OS version and confirms patched status automatically.

**Last reviewed:** 2026-05-06
