# SOP: Homepage Dashboard Integration

> Standard Operating Procedures for integrating services with the Homepage dashboard.
> Reference: `docs/integration.md` for Homepage overview and group list.
> Routing model (how routes are written at all): `docs/sops/gateway-api-httproute.md`.
> Description: Registering and validating service discovery entries in Homepage via `HTTPRoute` metadata.
> Version: `2026.09.08`
> Last Updated: `2026-09-08`
> Owner: `Platform`

---

## Description

This SOP ensures applications with web UIs are consistently exposed in Homepage and remain correctly
grouped, discoverable, and accessible through GitOps-managed **`HTTPRoute`** metadata.

> **Read this first — the discovery surface changed on 2026-09-07.**
> Homepage used to discover services from `Ingress` annotations. The Envoy Gateway
> migration completed in `ad1ea7c2` and **deleted every `Ingress` and `IngressClass`
> in the cluster**; `4de88601` then removed the now-inert `ingress` source from
> Homepage's config. Homepage runs with `sources: { ingress: false, gateway: true }`.
>
> **Consequence: annotating an `Ingress` registers nothing.** There is no `Ingress`
> for Flux to reconcile and no source watching for one. Every `gethomepage.dev/*`
> annotation and the `gethomepage.dev/enabled` label now belong on the app's
> **`HTTPRoute`**.
>
> Measured 2026-09-08: 73 of 103 `HTTPRoute`s carry `gethomepage.dev/*` annotations
> (72 enabled, 1 — Homepage's own route — deliberately `"false"`), and Homepage
> discovers all of them through the gateway source.

---

## Overview

Homepage auto-discovers services from **`HTTPRoute` annotations**, using RBAC granted
explicitly in its HelmRelease. Every app with a web UI that should appear in the
dashboard needs **both** the annotations and the label.

**Deployment:** `kubernetes/apps/default/homepage/`
**Group source of truth:** `kubernetes/apps/default/homepage/app/helmrelease.yaml`

Two config blocks in that HelmRelease make discovery work. Neither is optional:

```yaml
# 1. Discovery sources — the `ingress` source is OFF because the cluster
#    holds zero Ingress objects, so it would discover nothing.
kubernetes:
  mode: cluster
  ingress: false
  gateway: true
  services: true

# 2. RBAC — the chart's built-in ClusterRole only covers Ingress. Without
#    this, gateway discovery logs an RBAC error on every refresh and the
#    dashboard silently stays empty.
extraClusterRoles:
  - apiGroups: [gateway.networking.k8s.io]
    resources: [httproutes, gateways]
    verbs: [get, list, watch]
```

---

## Blueprints

N/A for dedicated Authentik-style blueprints.

Declarative source-of-truth:
- App `HTTPRoute` manifests / Helm `route:` values in `kubernetes/apps/**/app/`
- Homepage layout/group definitions in `kubernetes/apps/default/homepage/app/helmrelease.yaml`

---

## Operational Instructions

1. Add the required Homepage annotations **and** the label on the target `HTTPRoute`.
2. Select valid group/icon values from the Homepage source-of-truth.
3. Set `gethomepage.dev/pod-selector` if the route name does not match the pod's
   `app.kubernetes.io/name` (see the gotcha below).
4. Commit/push and wait for reconciliation.
5. Validate route metadata and Homepage discovery.

### Where the metadata goes — the two route shapes

The app's chart decides which shape you write. Both end up as the same object.

**Shape A — bjw-s `app-template` charts:** the chart's `route:` values key. The
`annotations:` and `labels:` blocks sit *inside the route entry*, siblings of
`hostnames:`/`parentRefs:` — **not** in the HelmRelease's own `metadata:`.

```yaml
# kubernetes/apps/ai/next-ai-draw-io/app/helmrelease.yaml
route:
  main:
    kind: HTTPRoute
    hostnames:
      - "next-ai-draw-io.${SECRET_DOMAIN}"
    parentRefs:
      - group: gateway.networking.k8s.io
        kind: Gateway
        name: envoy-internal
        namespace: network
        sectionName: https
    annotations:
      gethomepage.dev/enabled: "true"
      gethomepage.dev/name: "AI Draw.io"
      gethomepage.dev/description: "Create and edit diagrams using natural language AI"
      gethomepage.dev/group: "AI"
      gethomepage.dev/icon: "draw-io.png"
      gethomepage.dev/pod-selector: app.kubernetes.io/name=next-ai-draw-io
    labels:
      gethomepage.dev/enabled: "true"     # REQUIRED for discovery
```

**Shape B — any other chart:** a standalone `httproute.yaml` in the app directory
(and its `kustomization.yaml`), with the chart's own `ingress.enabled: false`.

```yaml
# kubernetes/apps/monitoring/uptime-kuma/app/httproute.yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: uptime-kuma
  namespace: monitoring
  labels:
    gethomepage.dev/enabled: "true"       # REQUIRED for discovery
  annotations:
    gethomepage.dev/enabled: "true"
    gethomepage.dev/name: "Uptime Kuma"
    gethomepage.dev/description: "Uptime monitoring tool"
    gethomepage.dev/group: "Monitoring"
    gethomepage.dev/icon: "uptime-kuma.png"
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: envoy-external
      namespace: network
      sectionName: https                   # http is owned by https-redirect
  hostnames:
    - "kuma.${SECRET_DOMAIN}"
```

Do not invent route structure here — `docs/sops/gateway-api-httproute.md` owns the
routing model, the `sectionName: https` rule, forward-auth apps, and the
verification gate. This SOP only covers the Homepage metadata on top of it.

---

## Examples

### Example 1: Minimal Homepage-Enabled HTTPRoute Metadata

```yaml
annotations:
  gethomepage.dev/enabled: "true"
  gethomepage.dev/name: "My App"
  gethomepage.dev/group: "Office"
  gethomepage.dev/icon: "my-app.png"
  gethomepage.dev/description: "My app description"
labels:
  gethomepage.dev/enabled: "true"
```

### Example 2: Excluding a Utility Route

```yaml
annotations:
  gethomepage.dev/enabled: "false"
labels:
  gethomepage.dev/enabled: "false"
```

Homepage's own route (`default/homepage`) is the live example of this.

---

## Verification Tests

### Test 1: Route Metadata Is Correct

```bash
kubectl -n {namespace} get httproute {name} -o yaml | rg "gethomepage.dev/"
```

Expected:
- Both annotation and label `gethomepage.dev/enabled: "true"` exist for included services.

If failed:
- Fix the manifest in git and reconcile. Note the object name: for Shape A charts the
  route is named `<release>-<routeKey>` (e.g. `hermes-agent-dashboard`), not `<release>`.

### Test 2: Homepage Discovery

```bash
kubectl logs -n default -l app.kubernetes.io/name=homepage --tail=50 | rg -i "{app-name}|error|forbidden"
```

Expected:
- Service appears without discovery or RBAC errors.

If failed:
- Re-check the group name and icon format, then confirm the `extraClusterRoles`
  block above is still present (a `forbidden ... httproutes` line means it is not).

---

## Required Annotations and Labels

Both `annotations` and `labels` must include `gethomepage.dev/enabled: "true"`.

**The label is critical.** Without `labels.gethomepage.dev/enabled: "true"`, the
service will not appear even if the annotations are correct.

### The pod-selector gotcha

Homepage guesses the status-probe pod selector **from the route name**. For Shape A
charts the route name is `<release>-<routeKey>`, which usually is *not* the pod's
`app.kubernetes.io/name` — the probe then resolves to nothing and the tile shows no
status. Set it explicitly whenever the two differ:

```yaml
gethomepage.dev/pod-selector: "app.kubernetes.io/name=hermes-agent"
```

---

## Homepage Groups

Use the exact group names defined in the Homepage layout:

| Group Name | For Apps Like |
|-----------|--------------|
| `AI` | Open WebUI, OpenClaw, AI-SRE |
| `Databases` | pgAdmin, phpMyAdmin, NocoDB, RedisInsight |
| `System` | Authentik, Longhorn, Headlamp |
| `Network Services` | AdGuard Home, Grafana (network context) |
| `Home Automation` | Home Assistant, Frigate, Zigbee2MQTT, Node-RED, n8n |
| `Monitoring` | Grafana, Prometheus, Uptime Kuma, Kibana |
| `Infrastructure` | openDTU, PiKVM, Awtrix |
| `Office` | Nextcloud, Paperless-ngx, Vaultwarden, Penpot |
| `Media` | Jellyfin, Plex |
| `Download` | TubeArchivist, JDownloader |

**Note:** Group names are case-sensitive and must match exactly.

---

## Icon Selection

### Dashboard Icons (recommended)

Browse: https://github.com/walkxcode/dashboard-icons/tree/main/png

Use the filename without path:
```yaml
gethomepage.dev/icon: "home-assistant.png"
gethomepage.dev/icon: "grafana.png"
gethomepage.dev/icon: "nextcloud.png"
```

### Material Design Icons

```yaml
gethomepage.dev/icon: "mdi-monitor-dashboard"
gethomepage.dev/icon: "mdi-database"
gethomepage.dev/icon: "mdi-robot"
```

### Simple Icons (brand icons)

```yaml
gethomepage.dev/icon: "si-postgresql"
gethomepage.dev/icon: "si-redis"
gethomepage.dev/icon: "si-elasticsearch"
```

---

## Step-by-Step Integration Checklist

When deploying a new app with a web UI:

### 1. Determine Group and Icon

- Check the [Dashboard Icons repository](https://github.com/walkxcode/dashboard-icons) for your app
- Choose the appropriate group from the list above

### 2. Add Annotations and Labels to the HTTPRoute

Pick Shape A or Shape B from *Operational Instructions* above, matching the app's chart.

### 3. Explicitly Exclude Routes That Should NOT Appear

For utility routes (callbacks, redirects, API-only hosts):

```yaml
annotations:
  gethomepage.dev/enabled: "false"
```

### 4. Commit and Deploy

Shared git index — stage explicit paths only:

```bash
git commit --only kubernetes/apps/{namespace}/{app}/ -F msg.txt
git show --stat HEAD    # confirm no foreign hunk rode along
git push
```

### 5. Verify

```bash
# Wait for Flux reconciliation (~2 minutes)
flux reconcile kustomization {app-kustomization} -n flux-system

# Route carries both annotation and label
kubectl -n {namespace} get httproute {name} \
  -o jsonpath='{.metadata.annotations}{"\n"}{.metadata.labels}{"\n"}' | tr ',' '\n' | grep gethomepage

# Homepage discovered the service
kubectl logs -n default -l app.kubernetes.io/name=homepage --tail=20 | grep -i {app-name}

# Open the dashboard and verify
# https://homepage.${SECRET_DOMAIN}
```

---

## Audit: Which Routes Are Registered

```bash
# Every HTTPRoute's homepage state, and any annotation/label mismatch
kubectl get httproute -A -o json | python3 -c "
import sys, json
items = json.load(sys.stdin)['items']
enabled = excluded = none = 0
for r in items:
    ns   = r['metadata']['namespace']
    name = r['metadata']['name']
    ann  = r['metadata'].get('annotations', {}).get('gethomepage.dev/enabled')
    lab  = r['metadata'].get('labels', {}).get('gethomepage.dev/enabled')
    if ann == 'true':
        enabled += 1
        if lab != 'true':
            print(f'MISSING LABEL: {ns}/{name}')
    elif ann == 'false':
        excluded += 1
    else:
        none += 1
        print(f'no homepage integration: {ns}/{name}')
print(f'--- {enabled} enabled, {excluded} explicitly excluded, {none} unannotated')
"
```

Expected (2026-09-08 baseline): 72 enabled, 1 explicitly excluded, 0 missing labels.
Unannotated routes are not automatically wrong — callback routes, API endpoints and
`https-redirect` legitimately have no dashboard tile.

---

## Troubleshooting

### Service Not Appearing in Dashboard

1. **You annotated an `Ingress`.** This is now the most likely cause. There are no
   `Ingress` objects in the cluster and Homepage's `ingress` source is off, so an
   Ingress-based annotation is inert and produces no error anywhere. Move the
   metadata to the `HTTPRoute`.

2. **Check both annotation AND label:**
   ```bash
   kubectl -n {ns} get httproute {name} -o yaml | grep "gethomepage.dev/enabled"
   ```
   Both must be `"true"`.

3. **Check the route exists — and under the name you expect:**
   ```bash
   kubectl -n {namespace} get httproute
   ```
   Shape A charts name it `<release>-<routeKey>`.

4. **Check Homepage logs for RBAC failures:**
   ```bash
   kubectl logs -n default -l app.kubernetes.io/name=homepage --tail=50 | grep -iE "error|forbidden"
   ```
   `forbidden ... httproutes` means the `extraClusterRoles` block was lost.

5. **Check the group name is exactly correct** (case-sensitive, must exist in the layout).

6. **Restart Homepage if needed:**
   ```bash
   kubectl rollout restart deployment/homepage -n default
   ```

### Service Appearing in Wrong Group

Update the `gethomepage.dev/group` annotation to match the correct group name exactly.

### Tile Shows No Pod Status

Set `gethomepage.dev/pod-selector` — see the pod-selector gotcha above.

### Icon Not Loading

- Verify the icon filename matches a file in the Dashboard Icons repository
- Try a different icon format (`mdi-` or `si-` prefix)
- Check the icon URL is accessible from the Homepage pod

### Service Shows but Link Doesn't Work

Homepage uses the route's first `hostname` by default; override with:
```yaml
gethomepage.dev/href: "https://custom-url.${SECRET_DOMAIN}"
```

---

## Manual Service Configuration

For services not on Kubernetes (e.g., router UI, NAS, PiKVM), configure them directly in the
Homepage helmrelease values:

```yaml
# In kubernetes/apps/default/homepage/app/helmrelease.yaml
config:
  services:
    - Infrastructure:
        - My Device:
            href: http://192.168.30.x
            icon: my-device.png
            description: My device description
            ping: 192.168.30.x
```

The helmrelease already includes entries for:
- UniFi Controller
- openDTU (Solar inverter)
- Awtrix (LED display)
- PiKVM
- Zigbee Router
- Brother Printer

---

## Diagnose Examples

### Diagnose Example 1: Service Missing from Homepage

```bash
kubectl -n {namespace} get httproute {name} -o yaml | rg "gethomepage.dev/enabled|gethomepage.dev/group"
kubectl logs -n default -l app.kubernetes.io/name=homepage --tail=100
```

Expected:
- Metadata present on the **route**, and logs show no RBAC or discovery error.

If the route has no `gethomepage.dev/*` at all, check whether the metadata was left
behind on a deleted `Ingress`:

```bash
rg -n "gethomepage.dev" kubernetes/apps/{namespace}/{app}/
rg -n "ingress:" kubernetes/apps/{namespace}/{app}/app/helmrelease.yaml
```

### Diagnose Example 2: Service in Wrong Group

```bash
kubectl -n {namespace} get httproute {name} -o yaml | rg "gethomepage.dev/group"
```

If unclear:
- Compare with `kubernetes/apps/default/homepage/app/helmrelease.yaml`.

---

## Health Check

```bash
# 1. Discovery source config is still gateway-based
kubectl -n default get deploy homepage -o yaml >/dev/null && \
rg -n "ingress: false|gateway: true" kubernetes/apps/default/homepage/app/helmrelease.yaml

# 2. No enabled route is missing its label
kubectl get httproute -A -o json | python3 -c "
import sys, json
items = json.load(sys.stdin)['items']
bad = [f\"{i['metadata']['namespace']}/{i['metadata']['name']}\"
       for i in items
       if i['metadata'].get('annotations', {}).get('gethomepage.dev/enabled') == 'true'
       and i['metadata'].get('labels', {}).get('gethomepage.dev/enabled') != 'true']
print('MISSING LABEL:', bad if bad else 'none')"

# 3. Homepage can actually read the Gateway API
kubectl auth can-i list httproutes.gateway.networking.k8s.io \
  --as=system:serviceaccount:default:homepage -A
```

Expected:
- `ingress: false` / `gateway: true` present; no missing labels; `can-i` returns `yes`.

---

## Security Check

```bash
# Ensure no sensitive values are stored in homepage annotations
kubectl get httproute -A -o yaml | rg -i "password|token|apikey|secret" | head -20
```

Expected:
- No sensitive credentials embedded in route annotations/labels.

Note that a `gethomepage.dev/*` annotation is world-readable to anyone with route
read access and is rendered into the dashboard — never put a widget API key there
inline; use the Homepage secret referenced from the HelmRelease.

---

## Rollback Plan

```bash
# Revert route metadata changes if discovery regresses
git log -- kubernetes/apps/{namespace}/{app}/
git revert <commit-sha>
git push
```

Rollback validation:
- Re-run `Verification Tests` and `Health Check`.
