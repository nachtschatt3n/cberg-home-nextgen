# Security Accepted Risks

> Risks reviewed and explicitly accepted. Do not surface these in automated audits as actionable items.
> Last reviewed: 2026-03-21

---

## AR-001 — Plaintext Secrets in Public Git History

**Severity at time of discovery:** Critical
**Status:** Accepted — all secrets rotated or services decommissioned

Five secrets were committed in plaintext to the public repository history between 2025-06 and 2025-11. All have been remediated:

| Commit | Service | Secret | Remediation |
|--------|---------|--------|-------------|
| `883de1d2` | Langfuse MinIO | `minioadmin`/`minioadmin` (default) | Rotated 2026-03-20 |
| `1f9319c0` | Kopia backup | Encryption + server password | Service decommissioned |
| `bb2bf972` | pgAdmin | Admin + master password | Rotated 2026-03-19, pod restarted 2026-03-20 |
| `6b335828` | Rybbit | `BETTER_AUTH_SECRET` JWT key | Service decommissioned |
| `4aa30e55` | Bytebot | PostgreSQL password + DB URL | Service decommissioned |

History cannot be rewritten on a public repo with potential clones. Rotation is the remediation. Risk accepted.

**Root cause:** Files named `.sops.tmp.yaml` committed before encryption ran. Mitigated by `.gitignore` rule covering `*.sops.tmp.yaml`.

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

**Why accepted:** All four applications have robust application-level authentication. Adding Authentik forward auth on top would create double-auth friction for legitimate users with no meaningful security gain, as all apps require login before any functionality is accessible.

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
| absenty (dev) | my-software-development | Built-in app auth; development instance |
| absenty (prod) | my-software-production | Built-in app auth; employee-facing service |
| andreamosteller (prod) | my-software-production | Intentionally public portfolio/website — no auth required |

**Why accepted:** All services with private data require authentication before access. `andreamosteller` is a public-facing website with no authentication by design.

---

## AR-008 — Headlamp cluster-admin ClusterRoleBinding

**Severity at time of discovery:** Warning
**Status:** Accepted — administrative tool by design

The `headlamp` ServiceAccount is bound to `cluster-admin` via `clusterrolebinding/headlamp-admin`. No long-lived token Secret exists in the cluster.

**Why accepted:** Headlamp is a Kubernetes cluster administration UI. Full cluster read/write access is the intended and required permission scope for the tool to function. The ingress is protected by Authentik forward auth on the internal ingress class, limiting access to authenticated users only. The risk surface is equivalent to granting a cluster admin user access to the dashboard.
