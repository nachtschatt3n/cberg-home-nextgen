# SOP: Homepage Dashboard Integration

> Standard Operating Procedures for integrating services with the Homepage dashboard.
> Reference: `docs/integration.md` for Homepage overview and group list.
> Description: Registering and validating service discovery entries in Homepage via ingress metadata.
> Version: `2026.03.01`
> Last Updated: `2026-03-01`
> Owner: `Platform`

---

## Description

This SOP ensures applications with web UIs are consistently exposed in Homepage and remain correctly
grouped, discoverable, and accessible through GitOps-managed ingress metadata.

---

## Overview

Homepage auto-discovers services via Kubernetes ingress annotations using RBAC.
Every app with a web UI that should appear in the dashboard needs both annotations and labels.

**Deployment:** `kubernetes/apps/default/homepage/`
**Group source of truth:** `kubernetes/apps/default/homepage/app/helmrelease.yaml`

---

## Blueprints

N/A for dedicated Authentik-style blueprints.

Declarative source-of-truth:
- App ingress manifests/Helm values in `kubernetes/apps/**/app/`
- Homepage layout/group definitions in `kubernetes/apps/default/homepage/app/helmrelease.yaml`

---

## Operational Instructions

1. Add required Homepage annotations and labels on the target ingress.
2. Select valid group/icon values from the Homepage source-of-truth.
3. Commit/push and wait for reconciliation.
4. Validate ingress metadata and Homepage discovery logs.

---

## Examples

### Example 1: Minimal Homepage-Enabled Ingress Metadata

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

### Example 2: Excluding Utility Ingress

```yaml
annotations:
  gethomepage.dev/enabled: "false"
```

---

## Verification Tests

### Test 1: Ingress Metadata Is Correct

```bash
kubectl get ingress {name} -n {namespace} -o yaml | rg "gethomepage.dev/"
```

Expected:
- Both annotation and label `gethomepage.dev/enabled: "true"` exist for included services.

If failed:
- Patch ingress metadata and reconcile.

### Test 2: Homepage Discovery

```bash
kubectl logs -n default -l app.kubernetes.io/name=homepage --tail=50 | rg -i "{app-name}|error"
```

Expected:
- Service appears without discovery errors.

If failed:
- Re-check group name and icon format.

---

## Required Annotations and Labels

Both `annotations` and `labels` must include `gethomepage.dev/enabled: "true"`.

```yaml
ingress:
  main:
    annotations:
      gethomepage.dev/enabled: "true"           # Enables the service
      gethomepage.dev/name: "My App Name"        # Display name
      gethomepage.dev/group: "Group Name"        # Dashboard group
      gethomepage.dev/icon: "app-icon.png"       # Icon name
      gethomepage.dev/description: "Brief description"
    labels:
      gethomepage.dev/enabled: "true"            # REQUIRED for discovery!
```

**The label is critical.** Without `labels.gethomepage.dev/enabled: "true"`, the service will not
appear even if annotations are correct.

---

## Homepage Groups

Use the exact group names defined in the Homepage layout:

| Group Name | For Apps Like |
|-----------|--------------|
| `AI` | Open WebUI, Langfuse, OpenClaw, AI-SRE |
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

### 2. Add Annotations to Ingress

```yaml
# In your ingress.yaml or helmrelease.yaml ingress values:
metadata:
  annotations:
    gethomepage.dev/enabled: "true"
    gethomepage.dev/name: "Your App Name"
    gethomepage.dev/group: "Group Name"
    gethomepage.dev/icon: "your-app.png"
    gethomepage.dev/description: "Brief one-line description"
  labels:
    gethomepage.dev/enabled: "true"
```

### 3. Explicitly Exclude Apps That Should NOT Appear

For ingresses that should not show in Homepage (e.g., internal utility ingresses):

```yaml
annotations:
  gethomepage.dev/enabled: "false"
```

### 4. Commit and Deploy

```bash
git add kubernetes/apps/{namespace}/{app}/
git commit -m "feat({app}): add homepage integration"
git push
```

### 5. Verify

```bash
# Wait for Flux reconciliation (~2 minutes)
flux reconcile kustomization {app-kustomization} -n flux-system

# Check ingress has both annotations and labels
kubectl get ingress {name} -n {namespace} -o yaml | grep -A10 "annotations:"
kubectl get ingress {name} -n {namespace} -o yaml | grep -A5 "labels:"

# Check Homepage discovered the service
kubectl logs -n default -l app.kubernetes.io/name=homepage --tail=20 | grep -i {app-name}

# Open the dashboard and verify
# https://homepage.${SECRET_DOMAIN}
```

---

## Ensure Existing Apps Have Homepage Annotations

The `tools/ensure-longhorn-homepage-annotations.sh` script can help add missing annotations.
For a general audit:

```bash
# Find ingresses missing homepage annotations
kubectl get ingress -A -o json | python3 -c "
import sys, json
ingresses = json.load(sys.stdin)['items']
for ing in ingresses:
    ns = ing['metadata']['namespace']
    name = ing['metadata']['name']
    annotations = ing['metadata'].get('annotations', {})
    labels = ing['metadata'].get('labels', {})
    enabled_annotation = annotations.get('gethomepage.dev/enabled', 'missing')
    enabled_label = labels.get('gethomepage.dev/enabled', 'missing')
    if enabled_annotation == 'missing' and enabled_label == 'missing':
        print(f'{ns}/{name}: no homepage integration')
"
```

---

## Troubleshooting

### Service Not Appearing in Dashboard

1. **Check both annotation AND label:**
   ```bash
   kubectl get ingress {name} -n {ns} -o yaml | grep "gethomepage.dev/enabled"
   ```
   Both annotation and label must be `"true"`.

2. **Check ingress exists:**
   ```bash
   kubectl get ingress -n {namespace}
   ```

3. **Check Homepage logs:**
   ```bash
   kubectl logs -n default -l app.kubernetes.io/name=homepage --tail=50 | grep -i error
   ```

4. **Check group name is exactly correct:**
   The group must exactly match a group defined in the Homepage layout (case-sensitive).

5. **Restart Homepage if needed:**
   ```bash
   kubectl rollout restart deployment/homepage -n default
   ```

### Service Appearing in Wrong Group

Update the `gethomepage.dev/group` annotation to match the correct group name exactly.

### Icon Not Loading

- Verify the icon filename matches a file in the Dashboard Icons repository
- Try a different icon format (`mdi-` or `si-` prefix)
- Check the icon URL is accessible from the Homepage pod

### Service Shows but Link Doesn't Work

Check that the `href` or the ingress host is configured correctly. Homepage uses the ingress host
by default; you can override with:
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
kubectl get ingress {name} -n {namespace} -o yaml | rg "gethomepage.dev/enabled|gethomepage.dev/group"
kubectl logs -n default -l app.kubernetes.io/name=homepage --tail=100
```

Expected:
- Metadata is present and logs show successful discovery.

If unclear:
- Verify group exists in `homepage` HelmRelease values.

### Diagnose Example 2: Service in Wrong Group

```bash
kubectl get ingress {name} -n {namespace} -o yaml | rg "gethomepage.dev/group"
```

Expected:
- Group exactly matches a defined group (case-sensitive).

If unclear:
- Compare with `kubernetes/apps/default/homepage/app/helmrelease.yaml`.

---

## Health Check

```bash
kubectl get ingress -A -o json | python3 -c "
import sys, json
items=json.load(sys.stdin)['items']
for i in items:
    a=i['metadata'].get('annotations',{})
    l=i['metadata'].get('labels',{})
    if a.get('gethomepage.dev/enabled')=='true' and l.get('gethomepage.dev/enabled')!='true':
        print('MISSING LABEL:',i['metadata']['namespace']+'/'+i['metadata']['name'])"
```

Expected:
- No entries missing the required label when annotation is enabled.

---

## Security Check

```bash
# Ensure no sensitive values are stored in homepage annotations
kubectl get ingress -A -o yaml | rg -i "password|token|apikey|secret" | head -20
```

Expected:
- No sensitive credentials embedded in ingress annotations/labels.

---

## Rollback Plan

```bash
# Revert ingress metadata changes if discovery/regression occurs
git log -- kubernetes/apps
git revert <commit-sha>
git push
```

Rollback validation:
- Re-run `Verification Tests` and `Health Check`.
