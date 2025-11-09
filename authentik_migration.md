# Authentik Integration Guide

This document provides a roadmap for integrating applications within the `cberg-home-nextgen` repository with Authentik for centralized Single Sign-On (SSO). It is kept up to date with recent integrations so future work can follow established patterns.

## Integration Patterns

There are two primary methods for integrating applications with Authentik. The method you choose depends on the application's capabilities.

### 1. Native OIDC/SAML Integration
This is the preferred and most seamless method. The application itself supports modern authentication protocols like OpenID Connect (OIDC) or SAML.

**General Steps:**
1.  **In Authentik:** Create an OAuth2/OpenID Provider.
2.  **In Authentik:** Create an Application, linking it to the provider you just created. Note the **Client ID**, **Client Secret**, and **OpenID Configuration URL**.
3.  **In Your Repository:** For the target application, update its Helm values or Kubernetes manifests to include the OIDC configuration. This is typically done via environment variables (e.g., `OIDC_CLIENT_ID`, `OIDC_ISSUER_URL`).
4.  **Secrets Management:** Store the Client Secret in a SOPS-encrypted secret file and reference it in the deployment.
5.  **Deploy:** Apply the changes and test the "Login with SSO" flow on the application.

### 2. Forward Authentication
This method is used for applications that do not support modern authentication. You place the application behind a reverse proxy that is managed by Authentik.

**General Steps:**
1.  **In Authentik:** Create a "Forward auth (single application)" Provider.
2.  **In Authentik:** Create an Application, linking it to the forward auth provider.
3.  **In Authentik:** Create a Proxy Outpost, linking it to the provider and selecting the Kubernetes integration. This will generate the YAML for a Kubernetes `Secret`.
4.  **In Your Repository:** Apply the generated `Secret` to your cluster (and encrypt it with SOPS).
5.  **In Your Repository:** In the application's `Ingress` resource, add the `authentik.goauthentik.io/outpost` annotation, pointing to the outpost you created.
6.  **Deploy:** Apply the changes. When you access the application's URL, you will be redirected to Authentik for login before you can proceed.

---

## Best Practices: Dos and Don'ts

-   ✅ **DO** start with one or two "Easy" applications to familiarize yourself with the OIDC and forward auth workflows.
-   ✅ **DO** prioritize securing critical UIs that have no authentication, like **Longhorn**.
-   ✅ **DO** store all client secrets and other sensitive values in SOPS-encrypted files.
-   ✅ **DO** test each application thoroughly after integration, especially for services like Jellyfin where mobile or third-party clients need to maintain access.
-   ✅ **DO** migrate applications one by one to isolate any potential issues.

-   ❌ **DON'T** attempt to integrate Plex. Its reliance on its own cloud authentication makes standard SSO integration extremely difficult and brittle.
-   ❌ **DON'T** change an application's existing authentication method until you have successfully tested the new Authentik flow.
-   ❌ **DON'T** forget to configure appropriate user and group permissions within Authentik to control who can access which applications.

---

## Recommended Migration Strategy

1.  **Priority 1 (Critical Security):**
    -   **Longhorn:** This UI has no authentication and provides direct access to your storage. Secure it immediately using the **Forward Auth** pattern.

2.  **Priority 2 (Easy Wins - Native OIDC):**
    -   Integrate applications with native OIDC support to build momentum and familiarity. Good candidates are:
        -   `Grafana`
        -   `Nextcloud`
        -   `Paperless-ngx`
        -   `Home Assistant`
        -   `pgAdmin` (completed; see case study below)

3.  **Priority 3 (Standard Forward Auth):**
    -   Work through the list of other applications that require forward authentication.
        -   `Uptime Kuma`
        -   `phpMyAdmin`
        -   `ESPHome` / `Zigbee2MQTT`

4.  **Postpone / Avoid:**
    -   **Plex:** Do not attempt.

---

## Application Integration Assessment

Here is a detailed breakdown of your user-facing applications and the recommended integration approach.

| Status | Application | Category | Integration | Difficulty |
| :--- | :--- | :--- | :--- | :--- |
| [x] | **pgAdmin** | `databases` | Native OIDC | **Medium** |
| [ ] | **phpMyAdmin** | `databases` | Forward Auth | **Medium** |
| [ ] | **Open WebUI** | `ai` | Native OIDC | **Easy** |
| [ ] | **Langfuse** | `ai` | Native OIDC | **Easy** |
| [ ] | **InfluxDB** | `databases` | Native OIDC | **Easy** |
| [ ] | **Homepage** | `default` | Forward Auth | **Easy** |
| [ ] | **JDownloader** | `download` | Forward Auth | **Medium** |
| [ ] | **Tube Archivist** | `download` | Forward Auth | **Medium** |
| [ ] | **ESPHome** | `home-automation` | Forward Auth | **Easy** |
| [ ] | **Frigate NVR** | `home-automation` | Forward Auth | **Easy** |
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
| [ ] | **Longhorn** | `storage` | Forward Auth | **Easy** |

### Application Details

-   **Open WebUI:** Configure OIDC via environment variables (`OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_ISSUER_URL`, etc.) in the deployment.
-   **Langfuse:** Enable SSO by configuring the `LANGFUSE_OIDC_*` environment variables.
-   **pgAdmin:** Configure `PGADMIN_CONFIG_AUTHENTICATION_SOURCES`/`PGADMIN_CONFIG_OAUTH2_CONFIG` in the secret; see the pgAdmin case study.
-   **phpMyAdmin:** Secure with Authentik forward auth. Create an Authentik application + forward-auth provider, bind it to a Kubernetes proxy outpost, apply the generated secret, and annotate the phpMyAdmin ingress with `authentik.goauthentik.io/outpost` plus the NGINX auth URL/sign-in headers.
-   **InfluxDB:** Configure the InfluxDB instance to use OIDC for authenticating users to the UI.
-   **Homepage:** As a static dashboard, it has no built-in authentication. Use a forward auth proxy to protect it.
-   **JDownloader:** The MyJDownloader web interface can be secured with a forward auth proxy.
-   **Tube Archivist:** Has its own user system. Use forward auth to protect the entire application.
-   **ESPHome:** The UI has no authentication. Use a forward auth proxy to secure it.
-   **Frigate NVR:** The UI has no authentication. Use a forward auth proxy to secure it.
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
-   **Longhorn:** The Longhorn UI has no authentication and provides direct access to storage. It is **critical** to protect it with a forward auth proxy.

## Case Study: pgAdmin Native OIDC

pgAdmin now authenticates exclusively through Authentik using OpenID Connect. Use this checklist when applying or revisiting the integration:

-   **Application & Provider:** In Authentik, create an Application with an OAuth2/OIDC provider. Set the redirect URI to `https://pgadmin.example.com/oauth2/callback`.
-   **Secrets Management:** Store the provider `client_id` and `client_secret` in `kubernetes/apps/databases/pgadmin/app/secret.sops.yaml`. Install `sops` first (`aqua install getsops/sops`) and confirm the repository `.sops.yaml` has matching `creation_rules`.
-   **pgAdmin Settings:** Set `PGADMIN_CONFIG_AUTHENTICATION_SOURCES` to `["oauth2"]`, define `PGADMIN_CONFIG_OAUTH2_CONFIG` with all required endpoints, and keep compatibility variables (`PGADMIN_CONFIG_OAUTH_*`) for older code paths.
-   **Critical Fields:** Include `OAUTH2_SERVER_METADATA_URL` to avoid metadata parsing errors, list scopes individually, and set `OAUTH2_USERNAME_CLAIM` to `preferred_username` for stable identities.
-   **Quoting Requirements:** pgAdmin parses the values with Python. Wrap scalar strings in double quotes inside the YAML (e.g., `PGADMIN_CONFIG_OAUTH_CLIENT_ID: '"<value>"'`) to prevent `SyntaxError: invalid decimal literal`.
-   **Verification:** Commit/push to trigger Flux, wait for the deployment to roll out, validate the Authentik login button text, complete a login, and tail pod logs to ensure no residual Python errors appear.

Follow the same pattern for future native OIDC integrations to minimize guesswork.
