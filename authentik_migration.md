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
- Forward Auth: `kubernetes/apps/home-automation/frigate-nvr/app/authentik-blueprint.yaml`, `kubernetes/apps/storage/longhorn/app/authentik-blueprint.yaml`
- Proxy Mode: `kubernetes/apps/monitoring/uptime-kuma/app/authentik-blueprint.yaml`

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
-   ✅ **DO** use proxy mode (`mode: proxy`) for applications with native login pages that can't be bypassed (e.g., Uptime Kuma).
-   ✅ **DO** prefer `internal` ingress class for forward auth integrations when external access isn't required.
-   ✅ **DO** ensure all secrets (OIDC client secrets, credentials) are SOPS-encrypted before committing to the public repository.

-   ❌ **DON'T** use the Authentik UI for configuration. Always use blueprints for GitOps compatibility.
-   ❌ **DON'T** use forward auth mode for applications with native login screens - use proxy mode instead to avoid double login.
-   ❌ **DON'T** use slugs for flow references. Use hardcoded UUIDs for default flows.
-   ❌ **DON'T** use string names for provider references. Use `!KeyOf` syntax instead.
-   ❌ **DON'T** attempt to integrate Plex. Its reliance on its own cloud authentication makes standard SSO integration extremely difficult and brittle.
-   ❌ **DON'T** change an application's existing authentication method until you have successfully tested the new Authentik flow.
-   ❌ **DON'T** forget to configure appropriate user and group permissions within Authentik to control who can access which applications.
-   ❌ **DON'T** forget to remove blueprint files when removing an app (both from app directory and authentik directory).

---

## Recommended Migration Strategy

1.  **Priority 1 (Critical Security):** ✅ **COMPLETED**
    -   **Longhorn:** ✅ Secured with Forward Auth blueprint (converted from proxy mode for reliability)
    -   **Frigate NVR:** ✅ Secured with Forward Auth blueprint
    -   **phpMyAdmin:** ✅ Secured with Forward Auth blueprint

2.  **Priority 2 (Easy Wins - Native OIDC):** 🔄 **IN PROGRESS**
    -   Integrate applications with native OIDC support to build momentum and familiarity:
        -   `Grafana` ❌ (postponed - see security incident note below)
        -   `Langfuse` 🔄 (deployed, OIDC investigation pending)
        -   `pgAdmin` ✅ (completed; see case study below)
        -   `Home Assistant` (home automation - commonly accessed)
        -   `Nextcloud` (file sharing - high value)
        -   `Paperless-ngx` (document management)
        -   `Open WebUI` (AI interface - simple OIDC)

3.  **Priority 3 (Standard Forward Auth):** ✅ **PARTIALLY COMPLETED**
    -   Work through applications that require forward authentication:
        -   `ESPHome` ✅ (completed - forward auth)
        -   `Uptime Kuma` ✅ (completed - proxy mode, see notes below)
        -   `Homepage` ✅ (completed - forward auth)
        -   `Prometheus` ✅ (completed - forward auth)
        -   `Alertmanager` ✅ (completed - forward auth)
        -   `Zigbee2MQTT` (home automation - basic auth to replace)
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
| [❌] | **Langfuse** | `ai` | Native OIDC | **Easy** |
| [ ] | **InfluxDB** | `databases` | Native OIDC | **Easy** |
| [x] | **Homepage** | `default` | Forward Auth | **Easy** |
| [ ] | **JDownloader** | `download` | Forward Auth | **Medium** |
| [ ] | **Tube Archivist** | `download` | Forward Auth | **Medium** |
| [x] | **ESPHome** | `home-automation` | Forward Auth | **Easy** |
| [x] | **Frigate NVR** | `home-automation` | Forward Auth | **Easy** |
| [ ] | **Home Assistant** | `home-automation` | Native OIDC | **Easy** |
| [ ] | **n8n** | `home-automation` | Native OIDC (Paid) / Forward Auth | **Medium** |
| [ ] | **Node-RED** | `home-automation` | Native OIDC | **Easy** |
| [ ] | **Scrypted NVR** | `home-automation` | Native OIDC | **Easy** |
| [ ] | **Zigbee2MQTT** | `home-automation` | Forward Auth | **Easy** |
| [ ] | **Jellyfin** | `media` | Forward Auth (with caveats) | **Medium** |
| [ ] | **Plex** | `media` | Not Recommended | **Hard** |
| [!] | **Grafana** | `monitoring` | ~~Native OIDC~~ Postponed | **Hard** |
| [ ] | **Kibana** | `monitoring` | Native OIDC (Paid) / Forward Auth | **Medium** |
| [ ] | **Kubernetes Dashboard** | `monitoring` | Native OIDC | **Medium** |
| [x] | **Uptime Kuma** | `monitoring` | Proxy Mode | **Medium** |
| [x] | **Prometheus** | `monitoring` | Forward Auth | **Easy** |
| [x] | **Alertmanager** | `monitoring` | Forward Auth | **Easy** |
| [ ] | **Nextcloud** | `office` | Native OIDC | **Easy** |
| [ ] | **Paperless-ngx** | `office` | Native OIDC | **Easy** |
| [x] | **Longhorn** | `storage` | Forward Auth | **Easy** |

### Application Details

-   **Open WebUI:** Configure OIDC via environment variables (`OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_ISSUER_URL`, etc.) in the deployment.
-   **Langfuse:** Enable SSO by configuring the `LANGFUSE_OIDC_*` environment variables.
-   **pgAdmin:** Configure `PGADMIN_CONFIG_AUTHENTICATION_SOURCES`/`PGADMIN_CONFIG_OAUTH2_CONFIG` in the secret; see the pgAdmin case study.
-   **phpMyAdmin:** ✅ Secured with Authentik forward auth via blueprint. See `kubernetes/apps/databases/phpmyadmin/app/authentik-blueprint.yaml` for reference.
-   **InfluxDB:** Configure the InfluxDB instance to use OIDC for authenticating users to the UI.
-   **Homepage:** As a static dashboard, it has no built-in authentication. Use a forward auth proxy to protect it.
-   **JDownloader:** The MyJDownloader web interface can be secured with a forward auth proxy.
-   **Tube Archivist:** Has its own user system. Use forward auth to protect the entire application.
-   **ESPHome:** ✅ Secured with Authentik forward auth via blueprint. The UI has no authentication, so forward auth proxy is required. See `kubernetes/apps/home-automation/esphome/app/authentik-blueprint.yaml` for reference.
-   **Frigate NVR:** ✅ Secured with Authentik forward auth via blueprint. See `kubernetes/apps/home-automation/frigate-nvr/app/authentik-blueprint.yaml` for reference.
-   **Home Assistant:** Configure the `oidc` integration in Home Assistant's `configuration.yaml` with details from Authentik.
-   **n8n:** The community version requires forward auth. Native OIDC is available on paid/enterprise tiers.
-   **Node-RED:** Configure the `adminAuth` section in its `settings.js` file to use a generic OIDC strategy.
-   **Scrypted NVR:** Scrypted has built-in support for OIDC, which can be configured in its management console.
-   **Zigbee2MQTT:** The web UI has basic auth; disable it and protect the service with a forward auth proxy.
-   **Jellyfin:** Use forward auth for the web UI. API access for mobile/TV clients may require custom Authentik rules or be bypassed.
-   **Plex:** Plex is tightly integrated with its own cloud authentication (plex.tv), making standard SSO integration very difficult and unreliable.
-   **Grafana:** Excellent OIDC support. Configure the `[auth.generic_oauth]` section in the `grafana.ini` file. **NOTE:** Grafana OIDC integration attempted but postponed due to Helm chart limitations with secret handling. The chart's `env` map doesn't properly support Kubernetes `valueFrom` syntax, and alternative approaches (envFromSecrets, extraConfigmapMounts) also had issues. A security incident occurred where OIDC credentials were accidentally committed unencrypted to the public repository (commit c85f058). Credentials were deleted and the integration rolled back. **Recommendation:** Use Grafana's built-in admin authentication for now, or wait for better Helm chart support for secret management.
-   **Kibana:** OIDC is a paid feature in the Elastic Stack. For the open-source version, use a forward auth proxy.
-   **Kubernetes Dashboard:** Requires passing specific OIDC flags to the dashboard's deployment arguments, which is slightly more complex than environment variables.
-   **Uptime Kuma:** ✅ Secured with Authentik proxy mode via blueprint. Has no multi-user login, and forward auth mode causes double login (Authentik + Uptime Kuma native). **Important:** Must use `mode: proxy` (not `forward_single`) AND enable "Disable Auth" in Uptime Kuma's Settings > Advanced UI to eliminate the double login issue. The ingress routes directly to the Authentik outpost, which then proxies to Uptime Kuma. After enabling "Disable Auth", only Authentik login is required. See `kubernetes/apps/monitoring/uptime-kuma/app/authentik-blueprint.yaml` for reference.
-   **Prometheus:** ✅ Secured with Authentik forward auth via blueprint. See `kubernetes/apps/monitoring/kube-prometheus-stack/app/prometheus-ingress.yaml` for reference.
-   **Alertmanager:** ✅ Secured with Authentik forward auth via blueprint. See `kubernetes/apps/monitoring/kube-prometheus-stack/app/alertmanager-ingress.yaml` for reference.
-   **Homepage:** ✅ Secured with Authentik forward auth via blueprint. As a static dashboard, it has no built-in authentication, so forward auth proxy is required. See `kubernetes/apps/default/homepage/app/authentik-blueprint.yaml` for reference.
-   **Langfuse:** ❌ Authentik OIDC blueprint deployed, OIDC environment variables configured. **Issue**: Internal server error when clicking Authentik button - OIDC callback not working. Pending investigation. See `kubernetes/apps/ai/langfuse/app/authentik-blueprint.yaml` for reference.
-   **Nextcloud:** Install the "Social Login" app from the Nextcloud app store and configure it for OIDC.
-   **Paperless-ngx:** Natively supports OIDC by configuring the `PAPERLESS_OIDC_*` environment variables.
-   **Longhorn:** ✅ Secured with Authentik forward auth via blueprint. Converted from proxy mode to forward auth mode for better maintainability. Uses `forward_single` mode with manual ingress configuration matching the Frigate pattern. See `kubernetes/apps/storage/longhorn/app/authentik-blueprint.yaml` and `kubernetes/apps/storage/longhorn/app/ingress.yaml` for reference.

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

**Important**: All blueprints are stored in a **SOPS-encrypted ConfigMap** (`configmap.sops.yaml`), which is the **source of truth** that Authentik loads.

- **Source of Truth**: `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml` (SOPS-encrypted, contains all blueprints)
- **Deployment**: Flux decrypts and applies the ConfigMap, init containers copy blueprints to `/blueprints` for Authentik to load

### When Adding a New App

1. Decrypt the ConfigMap: `sops -d kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml > /tmp/configmap.yaml`
2. Add your blueprint to the `data` section in `/tmp/configmap.yaml`:
   ```yaml
   data:
     your-app-blueprint.yaml: |
       version: 1
       entries:
         # ... your blueprint content ...
   ```
3. Re-encrypt: `sops -e /tmp/configmap.yaml > kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`
4. Update `helmrelease.yaml` to copy your blueprint in the init containers (both server and worker sections)
5. Commit and push - Flux will decrypt and apply automatically

### When Removing an App

1. Decrypt the ConfigMap: `sops -d kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml > /tmp/configmap.yaml`
2. Remove the blueprint entry from the `data` section
3. Re-encrypt: `sops -e /tmp/configmap.yaml > kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`
4. Update `helmrelease.yaml` to remove the blueprint copy command from init containers
5. Commit and push

### Key Blueprint Patterns

### Important Note About Blueprint Files

The **SOPS-encrypted ConfigMap** (`configmap.sops.yaml`) is the **source of truth** - it's what Authentik loads and uses at runtime. All blueprints are stored directly in this ConfigMap, eliminating the need for duplicate files in app directories.

- **Security**: Actual domains (not placeholders) are stored safely in the encrypted ConfigMap
- **Simplicity**: Single source of truth, no manual syncing required
- **Version Control**: All blueprints tracked in Git via the encrypted ConfigMap

**Forward Auth Pattern** (see Frigate, phpMyAdmin, ESPHome, Homepage, Prometheus, Alertmanager):
- Provider mode: `forward_single`
- Requires ingress annotations and separate outpost ingress
- Uses NGINX auth annotations (`auth-url`, `auth-signin`, `auth-response-headers`, `auth-snippet`)
- Works best with `internal` ingress class
- Application handles its own authentication after Authentik authorization

**Proxy Mode Pattern** (see Uptime Kuma):
- Provider mode: `proxy`
- Authentik outpost acts as a full reverse proxy
- Ingress routes directly to outpost service (not the app)
- No NGINX auth annotations needed
- **Use when:** Application has its own login that can't be bypassed with headers (e.g., Uptime Kuma)
- **Eliminates double login:** Authentik handles the session, app sees authenticated proxy requests

**Note:** Longhorn was previously using proxy mode with auto-ingress creation (`kubernetes_ingress_class_name: "internal"`), but this was unreliable. It has been converted to forward auth mode with manual ingress for better maintainability. See `kubernetes/apps/storage/longhorn/app/ingress.yaml` for the current implementation.

**OIDC Pattern** (see pgAdmin case study):
- OAuth2/OIDC provider
- Application links to provider
- Requires OIDC configuration in app deployment

For detailed blueprint documentation, see `AGENTS.md` and `CLAUDE.md`.
