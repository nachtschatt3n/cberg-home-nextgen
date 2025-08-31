# Default Namespace Deployments

This directory contains the deployments for the default namespace in the cberg-home-nextgen cluster, optimized for homelab use.

## Deployments

### 1. Homepage 🏠
- **Chart**: jameswynn/homepage
- **Version**: 2.1.0 (updated from 2.0.2)
- **App Version**: v1.2.0 (updated from v1.0.3)
- **Purpose**: Comprehensive homelab dashboard and service directory

### 2. Echo Server 🛠️
- **Chart**: bjw-s/app-template
- **Version**: 3.7.1
- **Purpose**: Simple HTTP echo server for testing and monitoring

## Recent Improvements

### 🎯 **Enhanced Dashboard Experience**
- ✅ **Comprehensive Service Directory**: All cluster services organized by category
- ✅ **Smart Grouping**: Services grouped by function (Home Automation, Media, Office, etc.)
- ✅ **Enhanced Widgets**: Kubernetes resources, system monitoring, weather, datetime
- ✅ **Better Layout**: Optimized column layouts for different service categories

### 🔒 **Security Enhancements (Homelab-Optimized)**
- ✅ Added security contexts with non-root user execution
- ✅ Implemented PodDisruptionBudgets for availability
- ✅ Added ServiceMonitor for Prometheus metrics
- ✅ **Removed**: Overly complex network policies and HPAs (not needed for homelab)

### 📊 **Resource Management**
- ✅ Added resource limits and requests for homepage
- ✅ Optimized rolling update strategies
- ✅ Zero-downtime deployments

## 🏠 **Homepage Dashboard Features**

### **Service Categories**
1. **🏠 Home Automation** (4 columns)
   - Home Assistant, Frigate NVR, Node-RED, n8n, Zigbee2MQTT, Scrypted, IoBroker

2. **📺 Media & Entertainment** (3 columns)
   - Plex, Jellyfin, MakeMKV

3. **💾 Office & Productivity** (3 columns)
   - Nextcloud, Nextcloud Whiteboard, Paperless-ngx

4. **🔧 System & Infrastructure** (3 columns)
   - Grafana, Prometheus, Alertmanager, Uptime Kuma, Longhorn UI

5. **🌐 Network Services** (2 columns)
   - AdGuard Home, Flux Webhook

6. **🤖 AI & Development** (2 columns)
   - Open WebUI

7. **📥 Download & Backup** (3 columns)
   - JDownloader, YouTube-DL Material, Kopia

8. **🗄️ Databases** (2 columns)
   - InfluxDB, phpMyAdmin

9. **🛠️ Utilities** (2 columns)
   - Echo Server

### **Enhanced Widgets**
- **Kubernetes Resources**: Real-time cluster resource monitoring
- **System Information**: Host details, OS, uptime, CPU, memory, disk
- **Weather**: OpenMeteo integration for local weather
- **DateTime**: Current date and time display
- **Search**: Quick access to search engines

## Configuration Details

### Homepage Improvements
- **Chart Update**: 2.0.2 → 2.1.0
- **Resource Limits**: 256Mi memory, 200m CPU
- **Resource Requests**: 64Mi memory, 25m CPU
- **Rolling Update**: maxSurge: 1, maxUnavailable: 0
- **Security**: Non-root user (1000:1000), dropped capabilities

### Echo Server Improvements
- **Rolling Update**: maxSurge: 1, maxUnavailable: 0
- **Security**: Already had good security context
- **Monitoring**: Existing ServiceMonitor maintained

## 🎨 **Dashboard Layout**

The homepage now features a clean, organized layout with:
- **Emojis**: Visual category identification
- **Smart Grouping**: Logical service organization
- **Responsive Columns**: Optimized for different screen sizes
- **Professional Appearance**: Clean, modern interface

## 📊 **Monitoring & Observability**

- **Homepage**: New ServiceMonitor for Prometheus metrics
- **Echo Server**: Existing ServiceMonitor maintained
- **Metrics Path**: `/metrics` endpoint
- **Scrape Interval**: 30 seconds
- **Kubernetes Integration**: Real-time cluster resource monitoring

## 🚀 **Deployment Strategy**

- **Type**: RollingUpdate
- **Max Surge**: 1 (ensures only one extra pod during updates)
- **Max Unavailable**: 0 (zero-downtime deployments)
- **Min Ready Seconds**: 10 (ensures pod stability before marking ready)
- **Revision History**: 3 (keeps last 3 revisions for rollback)

## 🔒 **Security Context (Homelab-Optimized)**

### Container Security
- `runAsNonRoot: true`
- `runAsUser: 1000`
- `runAsGroup: 1000`
- `allowPrivilegeEscalation: false`
- `capabilities.drop: ["ALL"]`

### Pod Security
- `fsGroup: 1000`
- `runAsNonRoot: true`
- `runAsUser: 1000`
- `runAsGroup: 1000`

## 🏠 **Homelab Philosophy**

This configuration is designed for homelab environments where:
- **Simplicity**: Focus on functionality over enterprise complexity
- **Reliability**: Stable, zero-downtime deployments
- **Monitoring**: Essential metrics without overwhelming complexity
- **Security**: Good security practices without over-engineering
- **Maintainability**: Easy to understand and modify

## 📝 **Maintenance Notes**

- **Chart Updates**: Monitor for new versions via Flux
- **Service Discovery**: New services are automatically detected via Kubernetes integration
- **Monitoring**: Verify metrics collection in Grafana
- **Customization**: Easy to add new services or modify existing ones

## 🔄 **Flux GitOps Integration**

All configurations are managed via Flux:
- **Reconciliation Interval**: 30 minutes
- **Source**: Git repository
- **Pruning**: Enabled for cleanup
- **Timeout**: 5 minutes
- **Wait**: Disabled for non-blocking deployments

## 🎯 **Next Steps**

1. **Commit and Deploy**: Push changes to trigger Flux reconciliation
2. **Customize Icons**: Add custom icons for services (optional)
3. **Add Services**: New services automatically appear via Kubernetes integration
4. **Monitor**: Watch the dashboard in action
5. **Enjoy**: Your comprehensive homelab dashboard is ready!
