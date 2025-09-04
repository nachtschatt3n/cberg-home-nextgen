# Homepage Configuration Improvements

## Overview
This document outlines the improvements made to your Homepage configuration to fix Kubernetes service discovery issues and enhance the widget setup.

## Key Changes Made

### 1. Fixed Kubernetes Service Discovery
- **Problem**: Services were showing as "NOT FOUND" despite being running
- **Solution**: Enhanced Kubernetes configuration with proper service discovery settings
- **Changes**:
  - Enabled service discovery for ingresses with `gethomepage.dev/enabled=true` labels
  - Added namespace discovery for multiple namespaces
  - Enabled services, pods, and nodes discovery

### 2. Added Missing Services
Based on your dashboard screenshot, added all missing services:
- **AI**: Open WebUI
- **Databases**: InfluxDB, phpMyAdmin
- **System**: Homepage itself
- **Network Services**: AdGuard, Echo, Unifi, Brother
- **Home Automation**: Frigate, Home Assistant, IoBroker, Music Assistant, Node-RED, Scrypted, Zigbee2MQTT, n8n
- **Monitoring**: Alertmanager, Uptime Kuma, Grafana, Prometheus

### 3. Enhanced Widget Configuration
- Added proper service widgets for monitoring and status checking
- Configured iframe widgets for services that don't have specific integrations
- Added resource monitoring widgets (CPU, memory, storage, network)
- Enhanced Kubernetes cluster monitoring with pod-level metrics

### 4. Improved Layout Organization
- Optimized column layouts for better visual organization
- AI and Databases: 2 columns each
- System: 1 column (single service)
- Network Services, Home Automation, Monitoring: 4 columns each
- Infrastructure: 3 columns

## Required Secrets Setup

To enable the service widgets with authentication, you'll need to create the following secrets:

### 1. AdGuard Secret
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: adguard-secret
  namespace: default
type: Opaque
data:
  password: <base64-encoded-password>
```

### 2. Unifi Secret
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: unifi-secret
  namespace: default
type: Opaque
data:
  password: <base64-encoded-password>
```

### 3. Frigate Secret
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: frigate-secret
  namespace: default
type: Opaque
data:
  api-key: <base64-encoded-api-key>
```

### 4. Home Assistant Secret
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: homeassistant-secret
  namespace: default
type: Opaque
data:
  token: <base64-encoded-long-lived-access-token>
```

### 5. Uptime Kuma Secret
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: uptime-kuma-secret
  namespace: default
type: Opaque
data:
  password: <base64-encoded-password>
```

### 6. Grafana Secret
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: grafana-secret
  namespace: default
type: Opaque
data:
  password: <base64-encoded-password>
```

## Service Discovery Labels

To enable automatic service discovery for your other services, add these labels to your ingress resources:

```yaml
metadata:
  labels:
    gethomepage.dev/enabled: "true"
    gethomepage.dev/name: "Service Name"
    gethomepage.dev/description: "Service Description"
    gethomepage.dev/group: "Group Name"
    gethomepage.dev/icon: "icon-name.png"
```

## Environment Variables

The configuration uses `${SECRET_DOMAIN}` for service URLs. Make sure this environment variable is properly set in your Flux configuration.

## Next Steps

1. **Apply the updated configuration** to your cluster
2. **Create the required secrets** for service authentication
3. **Add the discovery labels** to your ingress resources
4. **Verify service discovery** is working by checking the Homepage dashboard
5. **Customize icons** by adding the appropriate icon files to your Homepage configuration

## Troubleshooting

If services still show as "NOT FOUND":
1. Check that the ingress has the correct labels
2. Verify the service is in one of the monitored namespaces
3. Ensure the service URL is accessible from the Homepage pod
4. Check the Homepage logs for any discovery errors

## Additional Resources

- [Homepage Documentation](https://gethomepage.dev/configs/)
- [Service Widgets Guide](https://gethomepage.dev/configs/services/)
- [Kubernetes Integration](https://gethomepage.dev/configs/kubernetes/)
