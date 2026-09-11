# SOP: Authentik Identity Provider

> Standard Operating Procedures for Authentik authentication and authorization management.
> Reference: `docs/security.md` for security overview, Authentik blueprint pattern details.
> Description: Managing Authentik forward-auth, OIDC and SAML integrations through GitOps blueprints.
> Version: `2026.09.12`
> Last Updated: `2026-09-12`
> Owner: `Platform`

---

## Description

This SOP defines the required blueprint-driven workflow for Authentik integrations, including
provider/application/outpost wiring, HTTPRoute integration, and post-deploy validation.

---

## Overview

Authentik provides unified SSO and forward-auth proxy for all cluster services.

| Setting | Value |
|---------|-------|
| Namespace | `kube-system` |
| Deployment | `kubernetes/apps/kube-system/authentik/` |
| Blueprint source | `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml` (SOPS-encrypted) |
| Config approach | Blueprints only — never use UI |
| Auth flow | Forward auth proxy via per-app outposts |
| Core database | Standalone `authentik-pg` Deployment — Docker Official `postgres:18.6-bookworm`, `longhorn-static` volume `authentik-pg-data` (20Gi) |
| Rollback DB | Bundled bitnamilegacy PostgreSQL 17.11 StatefulSet `authentik-postgresql`, still running until plan `authentik-pg17-decommission` |

### Two databases answer to `-U authentik -d authentik` — read the right one

**This has already produced one false alarm, ranked as the household's
highest-priority security item for a day.** On 2026-09-11 Authentik's audit log
was reported dead since 2026-08-19 — 23 days with no record of any login,
failure, or admin action, on the SSO server that fronts private
health-insurance data. Measured: `authentik_events_event` held 11,375 rows with
a hard stop at 2026-08-19 22:26 UTC.

That reading was taken from the **wrong database**. Both of these are Running in
`kube-system`, both accept the *same* user, the *same* database name and the
*same* password out of `authentik-secret`, and their pod names differ by one
word:

| Pod | Role | `max(created)` in `authentik_events_event` |
|-----|------|--------------------------------------------|
| `deployment/authentik-pg` (postgres 18.6) | **LIVE** — what `AUTHENTIK_POSTGRESQL__HOST` points at | current |
| `statefulset/authentik-postgresql` → `authentik-postgresql-0` (17.11) | frozen pre-cutover rollback, kept by plan `authentik-pg17-decommission` | **permanently 2026-08-19 22:26 UTC** |

The rollback DB stopped receiving writes at the 2026-08-20 05:10 cutover
(`05843b7f`). Its copy of the audit table is a snapshot, and it will read as
"dead for N days" forever, with N growing by one every day. Nothing about the
query, the credentials, or the output signals that you hit the wrong instance.

Always name the host explicitly, and always `deploy/authentik-pg`:

```bash
# CORRECT — the live database
kubectl -n kube-system exec deploy/authentik-pg -- \
  psql -U authentik -d authentik -c \
  'select count(*), min(created), max(created) from authentik_events_event;'

# WRONG — succeeds, looks authoritative, returns a frozen snapshot
kubectl -n kube-system exec authentik-postgresql-0 -- psql -U authentik -d authentik ...
```

**Do not rely on this note alone** — it is the third place the live host is
documented, and the false alarm happened anyway. The structural guard is
`CronJob/authentik-db-probe` (`app/cronjob-db-probe.yaml`), which publishes
`authentik_audit_newest_event_timestamp_seconds` from the live DB hourly via
Pushgateway, with `AuthentikAuditLogStale` /
`AuthentikAuditFreshnessProbeMissing` in
`kubernetes/apps/monitoring/kube-prometheus-stack/app/authentik-alerts.yaml`.
Check the metric before believing any claim about audit-log freshness: it names
its source in the manifest, a human query does not.

**Related gap, deliberately NOT closed here:** there is no IP-based lockout
policy at all (`authentik_policies_reputation_reputationpolicy` has 0 rows and
0 bindings, and the reputation table is empty). Reputation scoring derives from
these same events, so the two interact — a genuinely frozen event log would also
starve any lockout policy that existed. Closing the lockout gap is its own
change.

### Database: `max_connections` parity is mandatory

The standalone `authentik-pg` Deployment passes `-c max_connections=500`, which
**must match what the bundled Bitnami DB was configured with**. Authentik runs
3 server + 3 worker replicas, each holding a pool; together they open far more
than PostgreSQL's default of 100. A parity miss does NOT fail at cutover — the
new DB accepts the first connections fine — it surfaces later as intermittent
login failures and worker errors once the pools fill under load, which is a much
harder signal to trace back to the migration. Verify before and after any change
to the DB manifest:

```bash
kubectl -n kube-system exec deploy/authentik-pg -- \
  psql -U authentik -c 'SHOW max_connections;'
```

The general procedure for this class of migration (bundled subchart datastore →
standalone manifests) is in
[`docs/sops/bundled-datastore-exit.md`](bundled-datastore-exit.md).

**CRITICAL:** All Authentik configuration MUST be done via blueprints, never the UI.
Blueprints are version-controlled, GitOps-compatible, and reproducible.
Workflow: decrypt ConfigMap -> edit blueprint entry -> re-encrypt -> commit -> push.

---

## Blueprints

Auth configuration source-of-truth:
- `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`

App-level blueprint source files (optional — some apps keep a local copy):
- `kubernetes/apps/{namespace}/{app}/app/authentik-blueprint.yaml` (if present)

The central ConfigMap is the source of truth. A per-app file is optional documentation.
All Authentik changes must be declarative and committed to Git (no UI-only configuration).

---

## Operational Instructions

Operational flow:
1. Create or update app blueprint manifest.
2. Merge blueprint entry into Authentik SOPS ConfigMap.
3. Add the app HTTPRoute, the `/outpost.goauthentik.io` callback HTTPRoute, the `SecurityPolicy`, and the `ReferenceGrant`; set `kubernetes_disabled_components: [ingress]` on the outpost.
4. Commit/push and verify outpost resources and login flow.

Detailed implementation steps are in `Integrating a New Application` below.

---

## Examples

### Example 1: Provider to Application Reference

```yaml
- id: my-app-application
  model: authentik_core.application
  attrs:
    provider: !KeyOf my-app-provider
```

### Example 2: Outpost with Kubernetes Service Connection

```yaml
- id: my-app-outpost
  model: authentik_outposts.outpost
  attrs:
    service_connection: "162f6c4f-053d-4a1a-9aa6-d8e590c49d70"
    providers:
      - !KeyOf my-app-provider
    config:
      # MANDATORY. Without it the outpost controller publishes its own Ingress
      # holding the app's hostname. See "Outpost-published Ingress" below.
      kubernetes_disabled_components:
        - ingress
```

---

## Key UUIDs (Hardcode These in Blueprints)

| Name | UUID |
|------|------|
| default-provider-authorization-implicit-consent | `0cdf1b8c-88f9-4b90-a063-a14e18192f74` |
| default-provider-invalidation-flow | `b8a97e00-f02f-48d9-b854-b26bf837779c` |
| Local Kubernetes Cluster service connection | `162f6c4f-053d-4a1a-9aa6-d8e590c49d70` |

---

## SAML SSO Provider Pattern

Most apps in this cluster use the forward-auth proxy outpost pattern (see "Integrating a New Application" below). Apps that handle their own auth chain natively (e.g. OpenSearch Dashboards, Wazuh) should use a **SAML provider** instead — the dashboard renders its own login page with a "Sign in with SSO" button that redirects to Authentik.

**Canonical example:** `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`, search for `id: wazuh-saml-provider`.

### Blueprint shape

```yaml
- id: wazuh-saml-provider
  model: authentik_providers_saml.samlprovider
  state: present
  identifiers:
    name: wazuh-saml
  attrs:
    name: wazuh-saml
    authorization_flow: "0cdf1b8c-88f9-4b90-a063-a14e18192f74"
    invalidation_flow: "b8a97e00-f02f-48d9-b854-b26bf837779c"
    acs_url: "https://wazuh.${SECRET_DOMAIN}/_opendistro/_security/saml/acs"
    audience: "wazuh-saml"
    issuer: "https://auth.${SECRET_DOMAIN}"
    sp_binding: "post"
    sign_assertion: true
    sign_response: false
    name_id_mapping: !Find [authentik_providers_saml.samlpropertymapping, [managed, "goauthentik.io/providers/saml/upn"]]
    property_mappings:
      - !Find [authentik_providers_saml.samlpropertymapping, [managed, "goauthentik.io/providers/saml/username"]]
      - !Find [authentik_providers_saml.samlpropertymapping, [managed, "goauthentik.io/providers/saml/upn"]]
      - !Find [authentik_providers_saml.samlpropertymapping, [managed, "goauthentik.io/providers/saml/email"]]
      - !Find [authentik_providers_saml.samlpropertymapping, [managed, "goauthentik.io/providers/saml/name"]]
      - !Find [authentik_providers_saml.samlpropertymapping, [managed, "goauthentik.io/providers/saml/groups"]]
    signing_kp: !Find [authentik_crypto.certificatekeypair, [name, "authentik Self-signed Certificate"]]

- id: wazuh-application
  model: authentik_core.application
  state: present
  identifiers:
    slug: wazuh
  attrs:
    name: Wazuh
    slug: wazuh
    provider: !KeyOf wazuh-saml-provider
    meta_launch_url: "https://wazuh.${SECRET_DOMAIN}"
    meta_icon: "https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/png/wazuh.png"
    meta_description: "XDR/SIEM platform"
```

### App-side configuration (OpenSearch / Wazuh dashboard example)

1. **`opensearch_dashboards.yml`** (mounted from SOPS secret):
   ```yaml
   opensearch_security.auth.type: ["basicauth", "saml"]
   opensearch_security.auth.multiple_auth_enabled: true
   server.xsrf.allowlist:
     - /_opendistro/_security/saml/acs
     - /_opendistro/_security/saml/acs/idpinitiated
     - /_opendistro/_security/saml/logout
   ```
   `multiple_auth_enabled: true` is required when `auth.type` is an array — otherwise the dashboard crashes with `Multiple Authentication Mode is disabled`.

2. **OpenSearch Security `config.yml`** (mounted from SOPS secret):
   ```yaml
   saml_auth_domain:
     http_enabled: true
     order: 1
     http_authenticator:
       type: saml
       challenge: true
       config:
         idp:
           # Use the PK-based URL, NOT /application/saml/<slug>/metadata/.
           # Authentik returns a 302 redirect on the slug path and the
           # OpenSearch SAML library doesn't follow redirects.
           metadata_url: "https://auth.${SECRET_DOMAIN}/api/v3/providers/saml/<PK>/metadata/?download"
           entity_id: "https://auth.${SECRET_DOMAIN}"
         sp:
           entity_id: "wazuh-saml"
         kibana_url: "https://wazuh.${SECRET_DOMAIN}"
         roles_key: "http://schemas.xmlsoap.org/claims/Group"
         subject_key: "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"
         exchange_key: "<URL-safe base64 random ≥32 bytes — see gotcha below>"
     authentication_backend:
       type: noop
   ```
   After editing `config.yml` / `roles_mapping.yml`, run `securityadmin.sh -cd .../opensearch-security/` to push to the `.opendistro_security` index.

3. **`roles_mapping.yml`** — map SAML users / Authentik backend roles to indexer roles:
   ```yaml
   all_access:
     reserved: false
     backend_roles:
       - "authentik Admins"
     users:
       - "mu"
   ```

4. **Routing** — drop the forward-auth wiring (the `SecurityPolicy` and the `/outpost.goauthentik.io` callback route; historically the nginx `auth-url`/`auth-signin`/`auth-response-headers` annotations). The dashboard handles auth itself once SAML is wired.

### Gotchas

- **SAML providers have no `grant_types` field** — the OIDC rule under
  "Rules & gotchas" does not apply here. Do not add one.
- **`exchange_key` must be URL-safe base64** (RFC 4648 §5: `-` and `_`, no `+` or `/`). Generate with `openssl rand -base64 64 | tr -d '\n=' | tr '+/' '-_'`. Wrong alphabet → `Illegal base64 character 2f`. Wrong padding → `Last unit does not have enough valid bits`.
- **Use the PK URL** for `idp.metadata_url`, not the application slug URL — Authentik 302-redirects the slug path and the SAML library does not follow redirects.
- **Provider PK is stable** across blueprint reapplications, but if you delete + recreate the SAML provider, the PK changes and the metadata URL needs updating.

### Migration: forward-auth → SAML

When migrating an existing forward-auth app to SAML, the old `proxyprovider` and its `outpost` need to be torn down explicitly so Authentik cleans up the deployed proxy outpost pod:

```yaml
- id: app-forward-auth-provider-removed
  model: authentik_providers_proxy.proxyprovider
  state: absent
  identifiers:
    name: app-forward-auth
- id: app-forward-auth-outpost-removed
  model: authentik_outposts.outpost
  state: absent
  identifiers:
    name: app-forward-auth
```

The `wazuh-blueprint.yaml` entry in the configmap shows this migration end-to-end.

---

## OIDC / OAuth2 Provider Pattern

Use OIDC (not forward-auth, not SAML) when the app **has its own user model** and
speaks OpenID Connect — e.g. Grafana, pgAdmin, Superset, Sure, **Immich**, **LibreChat**. The app
redirects to Authentik, gets an ID token, and provisions/logs in its own user.

### Blueprint shape

An OIDC integration is two entries in a single `*-oauth2-blueprint.yaml` data key:
an `oauth2provider` and an `application` that references it. Modeled on the
existing `grafana-oauth2-blueprint.yaml` / `immich-oauth2-blueprint.yaml` /
`librechat-oauth2-blueprint.yaml` (the last two were authored blueprint-only with
`grant_types` set from the start, so they are the cleanest references to copy):

```yaml
- id: <app>-oauth2-provider
  model: authentik_providers_oauth2.oauth2provider
  state: present
  identifiers:
    name: <app>
  attrs:
    name: <app>
    client_id: "<43-char alphanumeric, unique per app>"     # openssl rand
    client_secret: "<128-char alphanumeric>"                # openssl rand
    client_type: confidential
    grant_types:                     # REQUIRED for blueprint-only providers (see gotchas)
      - authorization_code
      - refresh_token
    authorization_flow: "0cdf1b8c-88f9-4b90-a063-a14e18192f74"   # default-provider-authorization-implicit-consent
    invalidation_flow: "b8a97e00-f02f-48d9-b854-b26bf837779c"    # default-provider-invalidation-flow
    redirect_uris:
      - matching_mode: strict
        url: "https://<app>.<SECRET_DOMAIN>/<the app's exact callback path>"
      # add more strict URIs for extra callbacks (e.g. mobile custom schemes)
    signing_key: !Find [authentik_crypto.certificatekeypair, [name, "authentik Self-signed Certificate"]]
    property_mappings:
      - !Find [authentik_providers_oauth2.scopemapping, [managed, "goauthentik.io/providers/oauth2/scope-openid"]]
      - !Find [authentik_providers_oauth2.scopemapping, [managed, "goauthentik.io/providers/oauth2/scope-email"]]
      - !Find [authentik_providers_oauth2.scopemapping, [managed, "goauthentik.io/providers/oauth2/scope-profile"]]

- id: <app>-application
  model: authentik_core.application
  state: present
  identifiers:
    slug: <app>
  attrs:
    name: <App>
    slug: <app>
    provider: !KeyOf <app>-oauth2-provider
    meta_launch_url: "https://<app>.<SECRET_DOMAIN>"
    meta_icon: "https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/png/<app>.png"
```

### Rules & gotchas

- **`grant_types` MUST be set explicitly** (Authentik ≥2026.5). A blueprint that
  omits it leaves the field **empty `[]`**, and then EVERY authorize request fails
  with `invalid_request` / "The request is otherwise malformed" (rejected at
  `authorize.py`: `grant_type not in provider.grant_types`).
  **Every blueprint-declared OIDC provider must set it — no exceptions.**
  A provider that was UI-created first and is only *imported* by
  `identifiers.name` is **NOT** structurally safe: it keeps working purely
  because the live DB row still holds the legacy default set the UI seeded, and
  the very first blueprint re-apply that touches it (a **server upgrade** being
  the obvious trigger) overwrites that row with the empty default. Four
  providers sat in exactly that state until 2026-08-19 and would have lost SSO
  simultaneously on the next upgrade. All six in-repo OIDC providers now set the
  field explicitly — copy any of them.
  Set `[authorization_code, refresh_token]`
  (add `implicit`/`hybrid` only if the app needs them). Symptom is identical to a
  redirect-uri problem but the redirect_uri is fine — confirm with
  `ak shell -c "from authentik.providers.oauth2.models import OAuth2Provider; print(OAuth2Provider.objects.get(name='<app>').grant_types)"`.
  **You cannot detect this by curling the authorize endpoint.** The authorize
  view is login-gated, so an unauthenticated request is redirected to
  `/accounts/login/` *before* `check_grant()` ever runs — a broken provider and a
  healthy one both return the same `302`. A probe built that way silently always
  passes. Verify against the DB row (above) or with a real browser login.

#### Which provider types need this

| Provider model | `grant_types` required? | Why |
|---|---|---|
| `authentik_providers_oauth2.oauth2provider` (OIDC) | **YES — always** | Blueprint omission ⇒ empty list ⇒ every login fails. |
| `authentik_providers_proxy.proxyprovider` (forward-auth) | **No — immune** | `ProxyProvider.set_oauth_defaults()` (`providers/proxy/models.py`) rewrites the grant types on every save, and is called from the serializer's `create()` **and** `update()` (`providers/proxy/api.py`) — the path blueprints use — plus at app startup. A blueprint cannot leave them empty. |
| `authentik_providers_saml.samlprovider` (SAML) | **No — N/A** | The SAML model has no `grant_types` field at all. |

So the rule is **OIDC-only**. Do not add `grant_types` to a proxy or SAML
blueprint entry.
- **`client_id` must be unique** across all providers. Reusing one throws a
  provider-collision error that leaves the blueprint in `errored` state (the
  whole app then fails SSO). Generate a fresh one: `openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c 43`.
- **`client_secret` is committed in TWO places** — the blueprint here *and* the
  app's own `secret.sops.yaml` (both SOPS-encrypted). They MUST match; rotate
  together in one commit. The app reads its copy at runtime.
- **`redirect_uris` are literal** — `${SECRET_DOMAIN}` does **not** substitute
  inside ConfigMap data, so write the real `SECRET_DOMAIN` value literally in the
  blueprint (the encrypted ConfigMap keeps it out of plaintext). Each callback URL the app can
  use needs its own `strict` entry (web login, settings page, mobile scheme…).
  A missing/wrong redirect URI is the #1 cause of a `redirect_uri mismatch` error.
- **Auto-provisioning is app-side**, not Authentik-side. The blueprint only makes
  Authentik willing to issue tokens; the app decides whether to create a local
  user (e.g. Immich's "Auto Register" toggle, Grafana's `allow_sign_up`).
- **The `groups` claim rides on the managed `profile` scope mapping** — there is no
  separate "groups" scope to add to `property_mappings`. The managed
  `goauthentik.io/providers/oauth2/scope-profile` expression already returns
  `"groups": [group.name for group in request.user.groups.all()]`, so binding the
  usual openid/email/profile trio is enough for an app to do group→role mapping off
  the userinfo response. LibreChat uses this to promote members of the
  `authentik Admins` group (`OPENID_ADMIN_ROLE` + `OPENID_ADMIN_ROLE_PARAMETER_PATH:
  groups` + `OPENID_ADMIN_ROLE_TOKEN_KIND: userinfo`). Verify what a provider will
  actually emit with
  `ak shell -c "from authentik.providers.oauth2.models import ScopeMapping; print(ScopeMapping.objects.get(managed='goauthentik.io/providers/oauth2/scope-profile').expression)"`.
- **The app must be running when the provider is created, or restarted after.** An app
  that discovers OIDC once at boot (LibreChat's `setupOpenId()`, for one) caches the
  failure if the provider did not exist yet — Flux applies the blueprint and the app
  pod in whatever order it likes. Symptom: the app's own config endpoint still
  advertises SSO as enabled (it only checks that env vars are non-empty) while the
  login route 500s. Check the app log for a discovery error at startup and restart the
  pod after the blueprint reports `successful`.
- **Reuse the flow UUIDs** in `## Key UUIDs` above and the shared self-signed
  signing key via `!Find` — do not create per-app flows or keys.
- Adding the data key is enough — the init container `cp /blueprints-source/*.yaml`
  wildcard picks it up and Reloader rolls the pods. No `helmrelease.yaml` edit.

Verify a new OIDC blueprint loaded without error:

```bash
kubectl exec -n kube-system deploy/authentik-server -- \
  ak show_blueprints | grep -i <app>      # state should be "present"/successful, not "errored"
```

---

## Outpost-published Ingress — the invisible object that steals a hostname

**Read this before converting, moving, or debugging any Authentik-protected
host.** This mechanism has mis-routed a hostname three times, most expensively
on headlamp: a 404 that took 40 minutes to explain, because every artifact an
operator would normally consult said the config was correct.

### The mechanism

Authentik's **Kubernetes outpost controller** reconciles a set of Kubernetes
objects for each outpost — Deployment, Service, Secret **and an `Ingress`**.
That Ingress carries the **application's own hostname**, on the **default
ingress class**, holding the `/outpost.goauthentik.io` path.

Two properties make it nearly undiscoverable:

- **It exists in no git repository.** It is created by the authentik server at
  runtime from the blueprint's `config`, so `rg` across this repo returns
  nothing and the GitOps model gives you no hint it exists.
- **It carries no `ownerReferences`.** Nothing garbage-collects it, and it does
  not show up as owned by the app, the HelmRelease, or the outpost Deployment.

While ingress-nginx was alive, `internal` was the default class, so these
Ingresses resolved their host to `192.168.55.100`. When an app's own Ingress
was withdrawn during the Envoy migration, the outpost's Ingress **silently
became the only remaining record for that hostname** — and because k8s-gateway
watches `Ingress` as well as `HTTPRoute`, it kept answering `.100`. The app's
new HTTPRoute on `.103` never won. The app looked correctly configured at every
layer except DNS.

> **Deleting the Ingress does not hold — the outpost recreates it.
> Disabling the component does.**

### The fix

Set `kubernetes_disabled_components: [ingress]` in the outpost's `config`
block in `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`:

```yaml
entries:
  - id: <app>-outpost
    model: authentik_outposts.outpost
    state: present
    identifiers:
      name: <app>-forward-auth
    attrs:
      name: <app>-forward-auth
      type: proxy
      providers:
        - !KeyOf <app>-forward-auth-provider
      service_connection: "162f6c4f-053d-4a1a-9aa6-d8e590c49d70"
      config:
        # In-cluster service, NOT the public ingress hostname (backchannel fix
        # 8c3059bf). Shown in the short `.svc` form, which resolves identically;
        # the live blueprint spells out the fully-qualified name.
        authentik_host: "http://authentik-server.kube-system.svc"
        authentik_host_browser: "https://auth.${SECRET_DOMAIN}"
        kubernetes_namespace: kube-system
        kubernetes_replicas: 1
        kubernetes_ingress_class_name: ""
        kubernetes_service_type: "ClusterIP"
        # THE KEY. Stops the controller managing an Ingress for this outpost.
        kubernetes_disabled_components:
          - ingress
        container_network: null
```

Three rules that are easy to get wrong:

1. **REPLACE the existing key, never append a second one.** Every outpost block
   in this repo already ships `kubernetes_disabled_components: []`. YAML is
   last-wins, so adding a second key with the same name is silently discarded
   and you will believe you fixed something you did not. *(Every outpost block
   in this repo has always shipped the key as `[]`, so here it is always an
   edit, never an addition. If you ever author an outpost block from scratch,
   include it. Deliberately no count: the blueprint set moves — the embedded
   outpost was adopted in `820a2fb8` and `kubernetes-dashboard` was deleted on
   2026-09-09 — and a stale number stamped "verified" is worse than none. To
   count, read the live list, not the file.)*
2. **Disabling stops MANAGEMENT; it does not DELETE the existing object.** The
   already-published Ingress stays until you remove it once by hand. After the
   component is disabled, that delete sticks:
   ```bash
   kubectl delete ingress -n <app-namespace> <outpost-ingress-name>
   ```
   Do the delete **after** the blueprint change has reconciled, not before, or
   the outpost simply recreates it.
3. **`kubernetes_ingress_class_name: ""` is the trap, not a safe default.**
   Empty string means "default class" — it does not mean "no Ingress". Only
   `kubernetes_disabled_components` suppresses the object.

### The rule covers MANAGED/SYSTEM outposts too — not just the ones with blueprints

The rule above was originally written assuming every outpost is one *we* declared
in `configmap.sops.yaml`. That assumption left a hole, and one object fell
straight through it: the **`authentik Embedded Outpost`**.

It is a `managed:` system object (`goauthentik.io/outposts/embedded`) that
authentik creates for itself in code — `AuthentikOutpostConfig.embedded_outpost`
in `authentik/outposts/apps.py`. Nobody wrote a blueprint for it, so it never
appeared in a repo grep, it was never audited, and it shipped with
`kubernetes_disabled_components: []`. It sits on the **`Local Kubernetes Cluster`
service connection**, which means its ingress reconciler is *live*: the moment a
provider is assigned to it, it publishes its own `Ingress` holding that app's
hostname — the exact failure documented above.

> **Audit outposts from the LIVE object list, never from the blueprint files.**
> `rg kubernetes_disabled_components` over this repo enumerates the outposts we
> declared. It does not enumerate the outposts that exist.
>
> ```bash
> POD=$(kubectl get pod -n kube-system -l app.kubernetes.io/component=worker \
>   -o jsonpath='{.items[0].metadata.name}')
> kubectl exec -n kube-system $POD -i -- ak shell -c "
> from authentik.outposts.models import Outpost
> for o in Outpost.objects.all().order_by('name'):
>     print(o.name, '| managed=', o.managed,
>           '| svc_conn=', o.service_connection,
>           '| providers=', o.providers.count(),
>           '| disabled=', o._config.get('kubernetes_disabled_components'))
> "
> ```
> Anything with a Kubernetes service connection and `disabled=[]` is a latent
> hostname hijack, whether or not it has a blueprint. Fix it while its provider
> count is still 0 — that is when the change is free.

**This audit is now automated** (2026-09-09, F-0e2c62ad). `runbooks/security-check.py`
section `s12_authentik_outposts` — printed as header §13 "Authentik Outpost Ingress
Suppression", and the slug findings are recorded under, which do not match because
the slug list is index-aligned and 0-based against 1-based headers — runs the probe
above on every sweep and
raises a finding for any outpost on a Kubernetes service connection that is missing
`kubernetes_disabled_components: [ingress]` — CRITICAL once it has a provider,
WARNING while it is still latent at 0 providers. Outposts on other service-connection
types are out of scope (no Kubernetes controller, so no Ingress to publish). The
section also flags a surviving `ak-outpost-*` Ingress, because disabling the
component stops management but does not delete an already-published object.

The check reads the LIVE outpost list and must keep doing so;
`runbooks/tests/test-outpost-ingress-suppression.py` fails if it is ever rewritten
as a repo grep, if it exempts `managed` outposts, or if an empty/failed probe is
allowed to read as a clean result. Run it with
`python3 runbooks/tests/test-outpost-ingress-suppression.py`.

#### A managed outpost CAN be blueprinted — verify these three things first

Adopting a system object with a blueprint is normally risky, because authentik
may reconcile it back and the two writers then fight every boot. For the
embedded outpost specifically it is safe, and the reasoning generalises — check
the same three points before adopting any managed object:

1. **Does authentik's own reconciler write the field you want to own?** Here it
   does not. The reconciler is
   `Outpost.objects.update_or_create(defaults={"type": ..., "name": ...},
   managed=MANAGED_OUTPOST)` — `defaults` holds only `type` and `name`, so
   `config` is never touched by authentik and there is nothing to fight.
2. **Does the blueprint importer overwrite `.managed`?** It does not. The marker
   authentik looks itself up by survives the apply, so no duplicate object is
   created on the next boot.
3. **Does the serializer accept the state you are declaring?**
   `OutpostSerializer` special-cases this object twice: `validate_name` rejects
   any name other than `authentik Embedded Outpost`, and `validate_providers`
   permits an **empty** provider list for it (every other outpost requires at
   least one). Declare it exactly as live or the apply fails.

Bind on `managed:`, not on `name:` — it is the field authentik itself keys on,
it cannot be edited from the UI, and a display name is precisely the thing that
drifted and left the pgAdmin blueprint inert for five months.

Prove it before you commit, with `Importer.validate()` — it runs the real import
in a transaction and rolls back, so it tells you whether the entry binds to the
existing pk (UPDATE) or falls through to a CREATE:

```bash
kubectl cp <blueprint>.yaml kube-system/$POD:/tmp/bp.yaml -c worker
kubectl exec -n kube-system $POD -i -- ak shell -c "
from authentik.blueprints.v1.importer import Importer
print(Importer.from_string(open('/tmp/bp.yaml').read()).validate())
"
```
Then re-read the live object and confirm the dry run left it untouched.

**The `config` dict is REPLACED wholesale on apply, never merged.** Capture the
complete live `config` first (`o._config`) and declare every key at its live
value, changing only `kubernetes_disabled_components`. A partial `config` block
silently resets every key you omitted.

The live blueprint for this is `embedded-outpost-blueprint.yaml` in
`kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`.

**Re-check this object after every authentik upgrade.** It is created by
application code, so a future release can change its defaults or its reconciler
without any signal in this repo. The `ak shell` audit above is the check.


### The two provider modes behave completely differently

Whether removing that Ingress is a no-op or a traffic change depends entirely
on the proxy provider's `mode`. Check it before you touch anything:

| `mode` | Who enforces auth | What the outpost Ingress/route served | Removing it |
|---|---|---|---|
| `forward_single` | the **gateway/proxy** in front of the app, by calling out to the outpost | the `/outpost.goauthentik.io` **callback path only** | safe once the app's own HTTPRoute serves the callback path |
| `proxy` | the **outpost itself** — it is the reverse proxy and fronts the whole app | **`/` for the app as well** as the callback | must be replaced by a route pointing at the **outpost Service**, not at the app |

In this cluster `uptime-kuma` is the **only** `mode: proxy` provider. Its
replacement HTTPRoute therefore has two rules, **both backed by
`ak-outpost-uptime-kuma-forward-auth`** (`/outpost.goauthentik.io` and `/`), so
authentication is preserved exactly and only the fronting proxy changed. Point
a `mode: proxy` app's route at the app Service instead and you publish it
**unauthenticated**.

Every other provider here is `forward_single`, where the outpost enforces
nothing on its own: the protected route must actively invoke it (see Step 3's
`SecurityPolicy`). A `forward_single` outpost with nothing calling it is dead
weight — which was the case for `arag-web` (AR-118) until 2026-09-11: the
wiring was never completed, so removing its Ingress changed no behaviour at
all. `d1440d50` completed it, and the shape is worth copying when an app has
machine clients: the `SecurityPolicy` targets only the UI route, while a
separate `PathPrefix /api` route is left ungated because its caller
authenticates with a Bearer token and cannot complete an interactive login.
A `SecurityPolicy` targets a whole `HTTPRoute`, not one rule inside it, which
is why that exemption has to be its own route.

### Auditing

```bash
# Any outpost still publishing an Ingress? (expect: No resources found)
kubectl get ingress -A

# Which outposts exist, vs which are blueprint-managed?
kubectl get deploy -n kube-system -o name | grep ak-outpost
```

**Not every live outpost is in the blueprints — do not assume the blueprint
file is a complete inventory.** The worked example was
`kubernetes-dashboard-forward-auth`: it ran in `kube-system` with no blueprint
entry, no Service behind it and no route, so it was unmanaged by GitOps and
could not be fixed by editing the ConfigMap. It was an orphan of the app removed
in `dbbacb10` and was **deleted on 2026-09-09** together with its application
and provider, so that specific object is gone — but the rule it demonstrates is
not, and it is exactly why the audit above enumerates the live outpost list
rather than the blueprint files.

---

## Integrating a New Application

### Step 1: Create Blueprint File

Create `kubernetes/apps/{namespace}/{app}/app/authentik-blueprint.yaml`:
This file is the app-level source blueprint that should also be copied into the Authentik SOPS ConfigMap.

```yaml
version: 1
entries:
  # --- Proxy Provider ---
  - id: my-app-provider
    model: authentik_providers_proxy.proxyprovider
    state: present
    attrs:
      name: my-app-forward-auth
      mode: forward_single
      external_host: "https://myapp.domain.com"
      internal_host: "http://myapp.{namespace}.svc.cluster.local:{PORT}"
      internal_host_ssl_validation: false
      authorization_flow: "0cdf1b8c-88f9-4b90-a063-a14e18192f74"
      invalidation_flow: "b8a97e00-f02f-48d9-b854-b26bf837779c"

  # --- Application ---
  - id: my-app-application
    model: authentik_core.application
    state: present
    attrs:
      name: My App
      slug: my-app
      provider: !KeyOf my-app-provider
      meta_launch_url: "https://myapp.domain.com"
      meta_icon: "https://myapp.domain.com/favicon.ico"

  # --- Outpost ---
  - id: my-app-outpost
    model: authentik_outposts.outpost
    state: present
    attrs:
      name: my-app-forward-auth
      type: proxy
      service_connection: "162f6c4f-053d-4a1a-9aa6-d8e590c49d70"
      providers:
        - !KeyOf my-app-provider
      config:
        authentik_host: "https://auth.domain.com"
        authentik_host_insecure: false
        kubernetes_namespace: kube-system
        kubernetes_replicas: 1
```

**Key rules:**
- Use hardcoded UUIDs for flows (not slugs)
- Use `!KeyOf` to reference other blueprint entries (not strings)
- Use SOPS-encrypted ConfigMap for actual domain values (Flux substitution doesn't work in ConfigMap data)
- `kubernetes_namespace: kube-system` is standard for all outposts

### Step 2: Add Blueprint to Authentik ConfigMap

The ConfigMap is the source Authentik reads. It's SOPS-encrypted.

```bash
# Decrypt ConfigMap
sops -d kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml > /tmp/configmap.yaml

# Edit /tmp/configmap.yaml — add your blueprint as a new data entry:
# data:
#   existing-blueprint.yaml: |
#     ...existing content...
#   my-app-blueprint.yaml: |
#     <paste your blueprint content here>

# Copy to repo path (must be in kubernetes/ for SOPS path rules)
cp /tmp/configmap.yaml kubernetes/apps/kube-system/authentik/app/configmap-new.sops.yaml

# Encrypt in place
sops -e -i kubernetes/apps/kube-system/authentik/app/configmap-new.sops.yaml

# Replace old file
mv kubernetes/apps/kube-system/authentik/app/configmap-new.sops.yaml \
   kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml

# Clean up
rm /tmp/configmap.yaml
```

### Step 3: Route the app and attach forward-auth (`SecurityPolicy`)

**There is no Ingress in this cluster** — ingress-nginx was deleted on
2026-09-07 (`ad1ea7c2`). The `nginx.ingress.kubernetes.io/auth-*` annotation
pattern that used to live in this step is gone with it: those annotations are
inert, and an `Ingress` carrying them routes nothing. Forward-auth is now
expressed as an Envoy Gateway **`SecurityPolicy`** with `extAuth`.

Three objects per protected app, all in the app's namespace:

```yaml
---
# 1) The app route. Homepage metadata (annotations AND label) goes HERE.
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: my-app
  namespace: my-namespace
  labels:
    gethomepage.dev/enabled: "true"
  annotations:
    gethomepage.dev/enabled: "true"
    gethomepage.dev/name: "My App"
    gethomepage.dev/group: "Group Name"
    gethomepage.dev/icon: "my-app.png"
    gethomepage.dev/description: "Description"
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: envoy-internal          # or envoy-external
      namespace: network
      sectionName: https            # the http listener is the cluster-wide redirect
  hostnames:
    - "myapp.${SECRET_DOMAIN}"
  rules:
    - matches:
        - path: { type: PathPrefix, value: / }
      backendRefs:
        - group: ""
          kind: Service
          name: my-app
          port: 8080
---
# 2) The callback route — SEPARATE, and more specific than `/`.
# Gateway API resolves by longest match, so folding it into the app route
# would loop the login callback back into the application.
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: my-app-authentik-outpost
  namespace: my-namespace
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: envoy-internal
      namespace: network
      sectionName: https
  hostnames:
    - "myapp.${SECRET_DOMAIN}"
  rules:
    - matches:
        - path: { type: PathPrefix, value: /outpost.goauthentik.io }
      backendRefs:
        # A REAL cross-namespace Service, never an ExternalName shim — Envoy
        # resolves backends via EndpointSlices and ExternalName has none.
        - group: ""
          kind: Service
          name: ak-outpost-my-app-forward-auth
          namespace: kube-system
          port: 9000
---
# 3) The enforcement. Without this, a `forward_single` outpost enforces
# NOTHING and the app is published unauthenticated.
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: SecurityPolicy
metadata:
  name: my-app-forward-auth
  namespace: my-namespace
spec:
  targetRefs:                    # the app route ONLY, never the callback route
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: my-app
  extAuth:
    failOpen: false              # outpost down => deny, never publish
    # MANDATORY. For an HTTP ext-auth service Envoy forwards ONLY Host, Method,
    # Path, Content-Length and Authorization unless this list says otherwise — so
    # without `cookie` the outpost never sees `authentik_proxy_*`, can never tell
    # the client is logged in, and the app answers HTTP 400 to every browser.
    # Do NOT add x-forwarded-for/-proto: Envoy appends to XFF instead of
    # sanitising it, so the header reaching the outpost still carries whatever the
    # client sent — regardless of the gateway's own client-IP trust list. Full
    # reasoning: docs/sops/gateway-api-httproute.md §4.3.
    headersToExtAuth:
      - cookie
      - accept
      - user-agent
    http:
      backendRefs:
        - group: ""
          kind: Service
          name: ak-outpost-my-app-forward-auth
          namespace: kube-system
          port: 9000
      path: /outpost.goauthentik.io/auth/envoy   # /auth/nginx 500s here
      headersToBackend:
        - Set-Cookie
        - X-authentik-username
        - X-authentik-groups
        - X-authentik-email
        - X-authentik-name
        - X-authentik-uid
```

Non-obvious points, each of which has cost time:

- **`path` must be `/auth/envoy`, not `/auth/nginx`.** The nginx variant
  returns 500 against this outpost.
- **`targetRefs` must exclude the callback route.** Targeting both makes the
  callback require the auth it is supposed to establish — an instant redirect
  loop.
- **`failOpen: false` is deliberate.** If the outpost is unavailable the app
  must 403, never fall open to the internet.
- **Cross-namespace backendRefs require a `ReferenceGrant`** in `kube-system`
  permitting the app namespace to reference the outpost Services. They are
  maintained one-per-app in
  `kubernetes/apps/kube-system/authentik/app/referencegrants.yaml` — add yours
  there in the same commit, or the backend silently fails to resolve.
- A `mode: proxy` provider does NOT use this shape — see the mode table in
  "Outpost-published Ingress" above; there the route points at the outpost.

Reference implementation: `kubernetes/apps/default/homepage/app/httproute.yaml`
(all three objects in one file). Full routing pattern:
`docs/sops/gateway-api-httproute.md`.

### Step 4: Disable the outpost's self-published Ingress

The outpost Service (`ak-outpost-my-app-forward-auth`) is created automatically
in `kube-system` when the blueprint runs. What is **not** automatic is stopping
the outpost from also publishing its own `Ingress` for your app's hostname.

Set this in the outpost's `config` block in the blueprint ConfigMap — replacing
the existing `kubernetes_disabled_components: []`, never appending a second key:

```yaml
        kubernetes_disabled_components:
          - ingress
```

Then, once the blueprint has reconciled, delete the already-published object
once by hand (disabling the component stops management but does not delete it):

```bash
kubectl get ingress -A                      # find it; expect none afterwards
kubectl delete ingress -n my-namespace <outpost-ingress-name>
```

**Why this is a required step and not a tidy-up:** that Ingress holds your app's
hostname, exists in no git repo, and has no ownerRefs — it will quietly outrank
your HTTPRoute in DNS. Full mechanism and the three-times-bitten history:
"Outpost-published Ingress" above.

### Step 5: Commit and Verify

```bash
# Commit changes. `--only` with explicit paths, never `git add`: the worktree
# index is SHARED between concurrent sessions, so a bare `git add` lets another
# agent's staged hunk ride into your commit (see AGENTS.md).
git commit --only \
  kubernetes/apps/{namespace}/{app}/httproute.yaml \
  kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml \
  kubernetes/apps/kube-system/authentik/app/referencegrants.yaml \
  -F msg.txt
git show --stat HEAD    # is every file here actually yours?
git push

# Wait for Flux reconciliation, then verify
kubectl exec -n kube-system deployment/authentik-server -- \
  python3 manage.py show_blueprints

# Check outpost was created
kubectl get deployment -n kube-system ak-outpost-my-app-forward-auth
kubectl get svc -n kube-system ak-outpost-my-app-forward-auth

# The outpost must NOT have published an Ingress (expect: No resources found)
kubectl get ingress -A

# Resolve the real hostname — do NOT curl with --resolve pinned to the gateway
# IP, which bypasses the DNS record that actually decides where traffic lands.
# That exact shortcut is why the headlamp misroute passed its verification gate.
dig +short @192.168.55.101 myapp.${SECRET_DOMAIN} A    # expect .103 or .104
```

---

## Removing an Application Integration

```bash
# 1. Decrypt ConfigMap, remove the blueprint entry, re-encrypt
sops -d kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml > /tmp/configmap.yaml
# Remove the app's blueprint data entry from /tmp/configmap.yaml
cp /tmp/configmap.yaml kubernetes/apps/kube-system/authentik/app/configmap-new.sops.yaml
sops -e -i kubernetes/apps/kube-system/authentik/app/configmap-new.sops.yaml
mv kubernetes/apps/kube-system/authentik/app/configmap-new.sops.yaml \
   kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml
rm /tmp/configmap.yaml

# 2. If a per-app blueprint file exists, remove it
# rm kubernetes/apps/{namespace}/{app}/app/authentik-blueprint.yaml  # only if present

# 3. Remove the SecurityPolicy that invoked the outpost
# 4. Remove the /outpost.goauthentik.io callback HTTPRoute and the ReferenceGrant
# 5. Commit and push
```

---

## Upgrading Authentik

A server version bump is **three coordinated changes**, not one. Doing only the
first takes the whole auth plane down.

### 1. Move all THREE version strings in one commit

In `kubernetes/apps/kube-system/authentik/app/helmrelease.yaml`:

| What | Where |
|---|---|
| chart version | `spec.chart.spec.version` |
| server init image | `server.initContainers[patch-session-settings].image` |
| worker init image | `worker.initContainers[patch-session-settings].image` |

The two `patch-session-settings` init containers copy `settings.py` **out of
their own image** and mount it over the main container. If they stay on the old
tag while the chart moves, the new server runs an old `settings.py` that imports
modules the new release dropped (2026.5.6 → 2026.8.0 replaced
`drf_orjson_renderer` with `msgspec`) — Django fails at import and **every
server and worker replica crashloops simultaneously**. There is no partial
outage here; SSO is fully down and most of the estate's routing with it.

Pre-flight the new image before committing — a moved path fails the `cp` and
blocks startup just as hard, and a renamed setting makes the `sed` silently
no-op:

```bash
mise exec -- kubectl run ak-preflight --rm -i --restart=Never -n kube-system \
  --image=ghcr.io/goauthentik/server:<NEW_TAG> --command -- sh -c '
  test -f /authentik/root/settings.py && echo settings.py OK
  grep -c "SESSION_EXPIRE_AT_BROWSER_CLOSE = True" /authentik/root/settings.py'
```

### 2. Managed outposts do NOT follow the server

A server upgrade leaves every managed proxy outpost pinned at the **old** image.
They must be pushed:

```bash
POD=$(mise exec -- kubectl get pods -n kube-system \
  -l app.kubernetes.io/component=server --field-selector=status.phase=Running \
  -o jsonpath='{.items[0].metadata.name}')

mise exec -- kubectl exec -n kube-system $POD -c server -- ak shell -c "
from authentik.outposts.models import Outpost
from authentik.outposts.controllers.kubernetes import KubernetesController
for o in Outpost.objects.all():
    if not o.service_connection: continue
    try: KubernetesController(o, o.service_connection).up()
    except Exception as e: print('partial', o.name, e)
"
```

**NEVER `kubectl delete` an outpost Deployment** to force this — that is the
documented way to break it.

Two things to expect, both benign:

- A bulk `o.save()` alone may enqueue controller tasks that finish `exc: null`
  and change nothing. The explicit `up()` above is what actually reconciles.
- Each `up()` raises `ControllerException (403)` — authentik's controller runs
  as `kube-system:default`, which lacks `get secrets`, so the reconcile updates
  the Deployment and then aborts at the Secret comparison. The **image bump
  still lands**. (Granting that RBAC is an open improvement.)

### 3. Verify — and verify the right things

```bash
# every pod on the new tag AND ready (checking readyReplicas alone is NOT enough:
# it counts old-ReplicaSet pods and will report a completed rollout that has not happened)
mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik \
  -o custom-columns='NAME:.metadata.name,IMAGE:.spec.containers[0].image,READY:.status.containerStatuses[0].ready'

# outposts: ask the SERVER what version each one reports back over its websocket,
# rather than trusting pod readiness
mise exec -- kubectl exec -n kube-system $POD -c server -- ak shell -c "
from authentik.outposts.models import Outpost, OutpostState
for o in Outpost.objects.all():
    print(o.name, [s.version for s in OutpostState.for_outpost(o)])
"

# OIDC providers kept their grant_types across the upgrade's blueprint re-apply
# (see the grant_types rule above — this is the field an upgrade can silently zero)
```

**Log-scanning traps.** authentik core emits `"level": "warning"` **with a space
after the colon**, and its server/worker value is `warn`, not `warning` — a naive
`"level":"error"` grep returns a meaningless zero. Since 2026.8 the proxy outpost
is a **Rust rewrite** with a completely different JSON schema
(`filename`/`line_number`/`spans`/`target`) and its own level vocabulary, so
parse structurally per-format rather than grepping for the old strings. The Rust
outpost also logs a benign `error` ("failed to detect a forward URL from
nginx") for any request lacking `X-Forwarded-*` headers — including your own
`curl` probes.

## Blueprint Reference: DO's and DON'Ts

### ✅ DO

- Use hardcoded flow UUIDs (not slug names)
- Use `!KeyOf` for cross-entry references
- Use SOPS-encrypted ConfigMap for actual domain values
- Include `service_connection` for Kubernetes outposts
- Create a dedicated outpost per application

### ❌ DON'T

- Use UI for any Authentik configuration
- Use slug names for flow references (will fail)
- Use string names for provider references (use `!KeyOf`)
- Use Flux substitution in ConfigMap data fields (doesn't work)
- Omit `service_connection` from outposts
- Bind to the embedded outpost

---

## Blueprint Entry Checklist

Before deploying a new Authentik integration, verify:

1. Proxy Provider
   - Uses flow UUIDs, not slug names
   - `external_host` is an actual domain value (stored in SOPS ConfigMap)
   - `internal_host` points to the correct in-cluster service and port
   - No `grant_types` entry needed — Authentik rewrites them on every save
     (OIDC providers are the ones that require it; see "Rules & gotchas")
2. Application
   - Uses `provider: !KeyOf <provider-id>` (not a string name)
   - Launch URL and icon URL use actual domain values
3. Outpost
   - Uses `providers: [!KeyOf <provider-id>]`
   - Includes `service_connection: "162f6c4f-053d-4a1a-9aa6-d8e590c49d70"`
   - Sets `kubernetes_namespace: kube-system`
   - Sets `kubernetes_disabled_components: [ingress]` (REPLACING the existing
     `[]`, not appended alongside it) — otherwise the outpost publishes an
     Ingress that steals the app's hostname
4. Routing
   - App `HTTPRoute` parented to `envoy-internal`/`envoy-external` in ns `network`, `sectionName: https`
   - Separate, more-specific `HTTPRoute` for `/outpost.goauthentik.io` backed by the outpost Service
   - `SecurityPolicy` with `extAuth` targeting the APP route only, `path: /outpost.goauthentik.io/auth/envoy`, `failOpen: false`, and `headersToExtAuth` containing `cookie` (without it every request 400s)
   - `ReferenceGrant` in `kube-system` for the app namespace
   - `kubectl get ingress -A` returns nothing
5. Verification
   - `show_blueprints` includes the new blueprint
   - `ak-outpost-{app}-forward-auth` deployment and service exist in `kube-system`

---

## Reference Implementations

The separate `authentik-outpost-ingress.yaml` files these entries used to point
at **no longer exist** — the callback is now a second HTTPRoute inside each
app's `httproute.yaml`, alongside the app route and the `SecurityPolicy`.

- Homepage — the fullest `forward_single` example, all three objects in one file:
  - `kubernetes/apps/default/homepage/app/httproute.yaml`
- Frigate NVR (blueprint in central ConfigMap only):
  - `kubernetes/apps/home-automation/frigate-nvr/app/httproute.yaml`
- phpMyAdmin (blueprint in central ConfigMap only):
  - `kubernetes/apps/databases/phpmyadmin/app/httproute.yaml`
- Uptime Kuma — the ONLY `mode: proxy` provider; both rules point at the
  outpost Service, not at the app:
  - `kubernetes/apps/monitoring/uptime-kuma/app/httproute.yaml`
- Longhorn (blueprint in central ConfigMap only — under the
  `longhorn-forward-auth-blueprint.yaml` key):
  - `kubernetes/apps/storage/longhorn/app/httproute.yaml`
- ReferenceGrants for every app's cross-namespace outpost backend:
  - `kubernetes/apps/kube-system/authentik/app/referencegrants.yaml`

For all apps: blueprint entry is in `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`.

---

## Verification Tests

### Test 1: Blueprint Loaded

```bash
kubectl exec -n kube-system deployment/authentik-server -- \
  python3 manage.py show_blueprints
```

Expected:
- New/updated blueprint appears in output without load errors.

If failed:
- Decrypt and validate `configmap.sops.yaml` structure and re-apply via GitOps.

### Test 2: Outpost Resources Created

```bash
kubectl get deployment -n kube-system ak-outpost-{app}-forward-auth
kubectl get svc -n kube-system ak-outpost-{app}-forward-auth
```

Expected:
- Deployment and service exist and are `Ready`.

If failed:
- Check Authentik logs for service connection or blueprint reference errors.

---

## Troubleshooting

```bash
# Check blueprints loaded
kubectl exec -n kube-system deployment/authentik-server -- \
  python3 manage.py show_blueprints

# Authentik server logs
kubectl logs -n kube-system -l app.kubernetes.io/name=authentik --tail=100

# Filter blueprint logs
kubectl logs -n kube-system -l app.kubernetes.io/name=authentik --tail=200 | grep -i blueprint

# Filter outpost logs
kubectl logs -n kube-system -l app.kubernetes.io/name=authentik --tail=200 | grep -i outpost

# Check all outpost deployments
kubectl get deployments -n kube-system -l app.kubernetes.io/managed-by=goauthentik.io

# Check outpost services
kubectl get svc -n kube-system | grep ak-outpost

# Check if outpost service exists for a specific app
kubectl get svc -n kube-system ak-outpost-{app}-forward-auth

# Full outpost resources
kubectl get all -n kube-system -l goauthentik.io/outpost-name={app}-forward-auth
```

### Common Issues

| Issue | Likely Cause | Fix |
|-------|-------------|-----|
| Blueprint not loading | ConfigMap not updated | Verify blueprint in decrypted ConfigMap |
| Outpost deployment not created | Missing `service_connection` | Add `service_connection: "162f6c4f-..."` |
| Auth redirect loop | Callback route missing, or the `SecurityPolicy` also targets the callback route | Add a separate, more-specific `/outpost.goauthentik.io` HTTPRoute; `targetRefs` must list the app route only |
| Host resolves to a dead IP / 404 after a routing change, config looks correct everywhere | Outpost published its own Ingress holding the hostname — in no git repo, no ownerRefs | `kubectl get ingress -A`; set `kubernetes_disabled_components: [ingress]`, then delete the object once (deleting alone does not hold) |
| 401 on auth-url | Wrong outpost service name | Check `ak-outpost-{app}-forward-auth.kube-system.svc.cluster.local` |
| Blueprint fails with UUID error | Using slug instead of UUID | Replace slug with UUID in blueprint |

---

## Diagnose Examples

### Diagnose Example 1: Redirect Loop After Login

```bash
kubectl get httproute -n {namespace} -o yaml | rg "outpost.goauthentik.io|hostnames|sectionName"
kubectl get securitypolicy -n {namespace} -o yaml | rg "targetRefs|path:|failOpen" -A2
kubectl get svc -n kube-system ak-outpost-{app}-forward-auth
```

Expected:
- A separate, more-specific `/outpost.goauthentik.io` route exists, and the
  `SecurityPolicy` targets the APP route ONLY. Targeting the callback route too
  makes the callback require the auth it is meant to establish — that is the
  redirect loop.
- `path` is `/auth/envoy`, not `/auth/nginx` (the nginx variant 500s here).

If unclear:
- Check outpost logs with `kubectl logs -n kube-system -l app.kubernetes.io/name=authentik --tail=200 | grep -i outpost`.

### Diagnose Example 2: Blueprint Applies But No Outpost Deployment

```bash
kubectl logs -n kube-system -l app.kubernetes.io/name=authentik --tail=200 | grep -Ei "blueprint|service_connection|error"
```

Expected:
- No errors for missing `service_connection` or invalid references.

If unclear:
- Verify `service_connection` UUID and `!KeyOf` references in blueprint.

---

## Health Check

```bash
kubectl exec -n kube-system deployment/authentik-server -- \
  python3 manage.py show_blueprints
kubectl get deployments -n kube-system -l app.kubernetes.io/managed-by=goauthentik.io
kubectl get svc -n kube-system | grep ak-outpost
```

Expected:
- Blueprints load cleanly and expected outpost resources remain healthy.

---

## Security Check

```bash
# Auth blueprint source remains encrypted
head -20 kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml | rg "sops:"

# Check no plaintext auth secrets accidentally committed
rg -n --glob '*.yaml' 'client_secret|password|token' kubernetes/apps/kube-system/authentik kubernetes/apps/*/*/app | head -40
```

Expected:
- Secrets stay SOPS-encrypted and no plaintext credentials are introduced.

---

## Rollback Plan

```bash
# Roll back the blueprint/config changes by reverting commit(s)
git log -- kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml
git revert <commit-sha>
git push
```

Rollback validation:
- Re-run `Verification Tests`.
