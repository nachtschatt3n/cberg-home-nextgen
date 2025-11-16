# Authentik Integration Guide

This document provides a roadmap for integrating applications within the `cberg-home-nextgen` repository with Authentik for centralized Single Sign-On (SSO). It is kept up to date with recent integrations so future work can follow established patterns.

## Integration Patterns

There are two primary methods for integrating applications with Authentik. The method you choose depends on the application's capabilities.

### 1. Native OIDC/SAML Integration
This is the preferred and most seamless method. The application itself supports modern authentication protocols like OpenID Connect (OIDC) or SAML.

**General Steps:**
1.  **In Your Repository:** Create an `authentik-blueprint.yaml` file in your app's `app/` directory (e.g., `kubernetes/apps/{namespace}/{app}/app/authentik-blueprint.yaml`).
2.  **Blueprint Definition:** Define an OAuth2/OpenID Provider, Application, and optionally an Outpost in the blueprint file.
3.  **In Your Repository:** Copy the blueprint file to `kubernetes/apps/kube-system/authentik/app/{app-name}-blueprint.yaml`.
4.  **Update Kustomization:** Add the blueprint file to `kubernetes/apps/kube-system/authentik/app/kustomization.yaml` in the `configMapGenerator.files` list.
5.  **In Your Repository:** Update the application's Helm values or Kubernetes manifests to include OIDC configuration (typically via environment variables like `OIDC_CLIENT_ID`, `OIDC_ISSUER_URL`).
6.  **Secrets Management:** Store the Client Secret in a SOPS-encrypted secret file and reference it in the deployment.
7.  **Deploy:** Commit and push changes. Flux will reconcile and Authentik will load the blueprints automatically.
8.  **Test:** Verify the "Login with SSO" flow on the application.

**Important:** Always use blueprints for Authentik configuration, never the UI. This ensures version-controlled, GitOps-compatible authentication setup.

### 2. Forward Authentication
This method is used for applications that do not support modern authentication. You place the application behind a reverse proxy that is managed by Authentik.

**General Steps:**
1.  **In Your Repository:** Create an `authentik-blueprint.yaml` file in your app's `app/` directory with:
    - A Proxy Provider (mode: `forward_single` or `proxy`)
    - An Application linking to the provider
    - An Outpost with Kubernetes integration
2.  **Blueprint Configuration:** Set `external_host` and `internal_host`, use default flow UUIDs, and include the service connection UUID for Kubernetes deployments.
3.  **In Your Repository:** Copy the blueprint file to `kubernetes/apps/kube-system/authentik/app/{app-name}-blueprint.yaml`.
4.  **Update Kustomization:** Add the blueprint file to `kubernetes/apps/kube-system/authentik/app/kustomization.yaml`.
5.  **In Your Repository:** Update the application's `Ingress` resource with Authentik forward auth annotations:
    - `nginx.ingress.kubernetes.io/auth-url`
    - `nginx.ingress.kubernetes.io/auth-signin`
    - `nginx.ingress.kubernetes.io/auth-response-headers`
    - `nginx.ingress.kubernetes.io/auth-snippet` (with `X-Proxy-Secret` header)
6.  **Create Outpost Ingress:** Add a separate ingress for `/outpost.goauthentik.io/*` paths using an ExternalName service.
7.  **Deploy:** Commit and push changes. Flux will reconcile, Authentik will load blueprints, and the outpost will create Kubernetes resources.
8.  **Test:** Access the application URL and verify Authentik login flow.

**Reference Implementations:**
- Forward Auth: `kubernetes/apps/home-automation/frigate-nvr/app/authentik-blueprint.yaml`
- Proxy Mode: `kubernetes/apps/storage/longhorn/app/authentik-blueprint.yaml`

**See Also:** `AGENTS.md` and `CLAUDE.md` for detailed blueprint documentation and best practices.

---

## Best Practices: Dos and Don'ts

-   ✅ **DO** use blueprints for all Authentik configuration (never the UI). This ensures version control and GitOps compatibility.
-   ✅ **DO** create blueprint files in each app's directory (`{app}/app/authentik-blueprint.yaml`). This keeps authentication config with the app for easy removal.
-   ✅ **DO** copy blueprint files to `kubernetes/apps/kube-system/authentik/app/` for Kustomize to include in the ConfigMap.
-   ✅ **DO** start with one or two "Easy" applications to familiarize yourself with the OIDC and forward auth workflows.
-   ✅ **DO** prioritize securing critical UIs that have no authentication, like **Longhorn** (already completed).
-   ✅ **DO** store all client secrets and other sensitive values in SOPS-encrypted files.
-   ✅ **DO** test each application thoroughly after integration, especially for services like Jellyfin where mobile or third-party clients need to maintain access.
-   ✅ **DO** migrate applications one by one to isolate any potential issues.
-   ✅ **DO** use UUIDs for flow references (not slugs) and `!KeyOf` for cross-references in blueprints.
-   ✅ **DO** hardcode domains in blueprints (Flux substitution doesn't work in ConfigMap `data` fields).

-   ❌ **DON'T** use the Authentik UI for configuration. Always use blueprints for GitOps compatibility.
-   ❌ **DON'T** use slugs for flow references. Use hardcoded UUIDs for default flows.
-   ❌ **DON'T** use string names for provider references. Use `!KeyOf` syntax instead.
-   ❌ **DON'T** attempt to integrate Plex. Its reliance on its own cloud authentication makes standard SSO integration extremely difficult and brittle.
-   ❌ **DON'T** change an application's existing authentication method until you have successfully tested the new Authentik flow.
-   ❌ **DON'T** forget to configure appropriate user and group permissions within Authentik to control who can access which applications.
-   ❌ **DON'T** forget to remove blueprint files when removing an app (both from app directory and authentik directory).

---

## Recommended Migration Strategy

1.  **Priority 1 (Critical Security):** ✅ **COMPLETED**
    -   **Longhorn:** ✅ Secured with Proxy Mode blueprint
    -   **Frigate NVR:** ✅ Secured with Forward Auth blueprint
    -   **phpMyAdmin:** ✅ Secured with Forward Auth blueprint

2.  **Priority 2 (Easy Wins - Native OIDC):**
    -   Integrate applications with native OIDC support to build momentum and familiarity. Recommended next candidates:
        -   `Grafana` (monitoring dashboard - high visibility)
        -   `Home Assistant` (home automation - commonly accessed)
        -   `Nextcloud` (file sharing - high value)
        -   `Paperless-ngx` (document management)
        -   `Open WebUI` (AI interface - simple OIDC)
        -   `Langfuse` (AI observability - simple OIDC)
        -   `pgAdmin` ✅ (completed; see case study below)

3.  **Priority 3 (Standard Forward Auth):**
    -   Work through applications that require forward authentication:
        -   `ESPHome` (home automation - no auth)
        -   `Zigbee2MQTT` (home automation - basic auth to replace)
        -   `Uptime Kuma` (monitoring - no multi-user)
        -   `Homepage` (dashboard - no auth)
        -   `JDownloader` (download manager)

4.  **Priority 4 (Complex Integrations):**
    -   Applications requiring special consideration:
        -   `Jellyfin` (forward auth with API bypass for clients)
        -   `Kibana` (OIDC paid feature, use forward auth for open-source)
        -   `Kubernetes Dashboard` (OIDC with specific flags)
        -   `n8n` (community: forward auth, paid: OIDC)

5.  **Postpone / Avoid:**
    -   **Plex:** Do not attempt (cloud authentication dependency).

---

## Application Integration Assessment

Here is a detailed breakdown of your user-facing applications and the recommended integration approach.

| Status | Application | Category | Integration | Difficulty |
| :--- | :--- | :--- | :--- | :--- |
| [x] | **pgAdmin** | `databases` | Native OIDC | **Medium** |
| [x] | **phpMyAdmin** | `databases` | Forward Auth | **Medium** |
| [ ] | **Open WebUI** | `ai` | Native OIDC | **Easy** |
| [ ] | **Langfuse** | `ai` | Native OIDC | **Easy** |
| [ ] | **InfluxDB** | `databases` | Native OIDC | **Easy** |
| [ ] | **Homepage** | `default` | Forward Auth | **Easy** |
| [ ] | **JDownloader** | `download` | Forward Auth | **Medium** |
| [ ] | **Tube Archivist** | `download` | Forward Auth | **Medium** |
| [ ] | **ESPHome** | `home-automation` | Forward Auth | **Easy** |
| [x] | **Frigate NVR** | `home-automation` | Forward Auth | **Easy** |
| [ ] | **Home Assistant** | `home-automation` | Native OIDC | **Easy** |
| [ ] | **n8n** | `home-automation` | Native OIDC (Paid) / Forward Auth | **Medium** |
| [ ] | **Node-RED** | `home-automation` | Native OIDC | **Easy** |
| [ ] | **Scrypted NVR** | `home-automation` | Native OIDC | **Easy** |
| [ ] | **Zigbee2MQTT** | `home-automation` | Forward Auth | **Easy** |
| [ ] | **Jellyfin** | `media` | Forward Auth (with caveats) | **Medium** |
| [ ] | **Plex** | `media` | Not Recommended | **Hard** |
| [ ] | **Grafana** | `monitoring` | Native OIDC | **Easy** |
| [ ] | **Kibana** | `monitoring` | Native OIDC (Paid) / Forward Auth | **Medium** |
| [ ] | **Kubernetes Dashboard** | `monitoring` | Native OIDC | **Medium** |
| [ ] | **Uptime Kuma** | `monitoring` | Forward Auth | **Easy** |
| [ ] | **Nextcloud** | `office` | Native OIDC | **Easy** |
| [ ] | **Paperless-ngx** | `office` | Native OIDC | **Easy** |
| [x] | **Longhorn** | `storage` | Proxy Mode | **Easy** |

### Application Details

-   **Open WebUI:** Configure OIDC via environment variables (`OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_ISSUER_URL`, etc.) in the deployment.
-   **Langfuse:** Enable SSO by configuring the `LANGFUSE_OIDC_*` environment variables.
-   **pgAdmin:** Configure `PGADMIN_CONFIG_AUTHENTICATION_SOURCES`/`PGADMIN_CONFIG_OAUTH2_CONFIG` in the secret; see the pgAdmin case study.
-   **phpMyAdmin:** ✅ Secured with Authentik forward auth via blueprint. See `kubernetes/apps/databases/phpmyadmin/app/authentik-blueprint.yaml` for reference.
-   **InfluxDB:** Configure the InfluxDB instance to use OIDC for authenticating users to the UI.
-   **Homepage:** As a static dashboard, it has no built-in authentication. Use a forward auth proxy to protect it.
-   **JDownloader:** The MyJDownloader web interface can be secured with a forward auth proxy.
-   **Tube Archivist:** Has its own user system. Use forward auth to protect the entire application.
-   **ESPHome:** The UI has no authentication. Use a forward auth proxy to secure it.
-   **Frigate NVR:** ✅ Secured with Authentik forward auth via blueprint. See `kubernetes/apps/home-automation/frigate-nvr/app/authentik-blueprint.yaml` for reference.
-   **Home Assistant:** Configure the `oidc` integration in Home Assistant's `configuration.yaml` with details from Authentik.
-   **n8n:** The community version requires forward auth. Native OIDC is available on paid/enterprise tiers.
-   **Node-RED:** Configure the `adminAuth` section in its `settings.js` file to use a generic OIDC strategy.
-   **Scrypted NVR:** Scrypted has built-in support for OIDC, which can be configured in its management console.
-   **Zigbee2MQTT:** The web UI has basic auth; disable it and protect the service with a forward auth proxy.
-   **Jellyfin:** Use forward auth for the web UI. API access for mobile/TV clients may require custom Authentik rules or be bypassed.
-   **Plex:** Plex is tightly integrated with its own cloud authentication (plex.tv), making standard SSO integration very difficult and unreliable.
-   **Grafana:** Excellent OIDC support. Configure the `[auth.generic_oauth]` section in the `grafana.ini` file.
-   **Kibana:** OIDC is a paid feature in the Elastic Stack. For the open-source version, use a forward auth proxy.
-   **Kubernetes Dashboard:** Requires passing specific OIDC flags to the dashboard's deployment arguments, which is slightly more complex than environment variables.
-   **Uptime Kuma:** Has no multi-user login. Protect the entire application with a forward auth proxy.
-   **Nextcloud:** Install the "Social Login" app from the Nextcloud app store and configure it for OIDC.
-   **Paperless-ngx:** Natively supports OIDC by configuring the `PAPERLESS_OIDC_*` environment variables.
-   **Longhorn:** ✅ Secured with Authentik proxy mode via blueprint. See `kubernetes/apps/storage/longhorn/app/authentik-blueprint.yaml` for reference. The outpost creates its own ingress for the application.

## Case Study: pgAdmin Native OIDC

pgAdmin now authenticates exclusively through Authentik using OpenID Connect. Use this checklist when applying or revisiting the integration:

-   **Application & Provider:** In Authentik, create an Application with an OAuth2/OIDC provider. Set the redirect URI to `https://pgadmin.example.com/oauth2/callback`.
-   **Secrets Management:** Store the provider `client_id` and `client_secret` in `kubernetes/apps/databases/pgadmin/app/secret.sops.yaml`. Install `sops` first (`aqua install getsops/sops`) and confirm the repository `.sops.yaml` has matching `creation_rules`.
-   **pgAdmin Settings:** Set `PGADMIN_CONFIG_AUTHENTICATION_SOURCES` to `["oauth2"]`, define `PGADMIN_CONFIG_OAUTH2_CONFIG` with all required endpoints, and keep compatibility variables (`PGADMIN_CONFIG_OAUTH_*`) for older code paths.
-   **Critical Fields:** Include `OAUTH2_SERVER_METADATA_URL` to avoid metadata parsing errors, list scopes individually, and set `OAUTH2_USERNAME_CLAIM` to `preferred_username` for stable identities.
-   **Quoting Requirements:** pgAdmin parses the values with Python. Wrap scalar strings in double quotes inside the YAML (e.g., `PGADMIN_CONFIG_OAUTH_CLIENT_ID: '"<value>"'`) to prevent `SyntaxError: invalid decimal literal`.
-   **Verification:** Commit/push to trigger Flux, wait for the deployment to roll out, validate the Authentik login button text, complete a login, and tail pod logs to ensure no residual Python errors appear.

Follow the same pattern for future native OIDC integrations to minimize guesswork.

## Blueprint-Based Configuration (Default)

**All Authentik resources are now managed via blueprints stored in Git**, not through the UI. This ensures:
- Version-controlled authentication configuration
- GitOps-compatible deployment
- Reproducible authentication setup across environments
- No manual UI configuration that can drift

### Blueprint File Structure

Each app that uses Authentik should have an `authentik-blueprint.yaml` file in its `app/` directory:
- **Location**: `kubernetes/apps/{namespace}/{app}/app/authentik-blueprint.yaml`
- **Source of Truth**: This file in the app directory
- **Copy for Kustomize**: Also copied to `kubernetes/apps/kube-system/authentik/app/{app-name}-blueprint.yaml`

### When Adding a New App

1. Create `authentik-blueprint.yaml` in your app's `app/` directory
2. Copy it to `kubernetes/apps/kube-system/authentik/app/{app-name}-blueprint.yaml`
3. Add it to `kubernetes/apps/kube-system/authentik/app/kustomization.yaml` in the `configMapGenerator.files` list
4. Commit and push - Flux will reconcile and Authentik will load the blueprint

### When Removing an App

1. Remove the blueprint file from the app directory
2. Remove the copy from `kubernetes/apps/kube-system/authentik/app/`
3. Remove the reference from `kustomization.yaml`
4. The blueprint will be automatically removed from the ConfigMap

### Key Blueprint Patterns

**Forward Auth Pattern** (see Frigate or phpMyAdmin):
- Provider mode: `forward_single`
- Requires ingress annotations and separate outpost ingress
- Uses NGINX auth annotations

**Proxy Mode Pattern** (see Longhorn):
- Provider mode: `proxy`
- Outpost creates its own ingress
- No NGINX auth annotations needed

**OIDC Pattern** (see pgAdmin case study):
- OAuth2/OIDC provider
- Application links to provider
- Requires OIDC configuration in app deployment

For detailed blueprint documentation, see `AGENTS.md` and `CLAUDE.md`.
