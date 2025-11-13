# Homepage Widget Recommendations for Your Setup

Based on your infrastructure, here are widget recommendations that would work well with your current services.

## Currently Configured Widgets
- ✅ **datetime** - Date and time display
- ✅ **resources** - Kubernetes cluster resources (CPU, memory, network, storage)
- ✅ **kubernetes** - Kubernetes cluster info (nodes, pods)
- ✅ **openmeteo** - Weather widget (Berlin, Germany)

## Recommended Additional Widgets

### 1. **Prometheus Metric Widget** ⭐ Highly Recommended
Since you have Prometheus running, you can add custom metrics widgets:

```yaml
widgets:
  - prometheusmetric:
      url: https://prometheus.${SECRET_DOMAIN}
      refreshInterval: 10000
      metrics:
        - label: Active Alerts
          query: alertmanager_alerts{state="active"}
        - label: Cluster CPU Usage
          query: avg(rate(container_cpu_usage_seconds_total[5m])) * 100
          format:
            type: number
            suffix: "%"
        - label: Cluster Memory Usage
          query: avg(container_memory_usage_bytes) / avg(container_spec_memory_limit_bytes) * 100
          format:
            type: number
            suffix: "%"
        - label: Longhorn Volume Count
          query: count(longhorn_volume_state)
        - label: Pod Count
          query: count(kube_pod_info)
```

### 2. **Uptime Kuma Widget** ⭐ Highly Recommended
You already have Uptime Kuma - add widgets to services:

```yaml
- Prometheus:
    icon: prometheus.png
    href: https://prometheus.${SECRET_DOMAIN}
    widget:
      type: uptimekuma
      url: https://kuma.${SECRET_DOMAIN}
      slug: your-prometheus-slug
```

### 3. **Service-Specific Widgets**

#### Plex Widget
```yaml
- Plex:
    icon: plex.png
    href: https://plex.${SECRET_DOMAIN}
    widget:
      type: plex
      url: https://plex.${SECRET_DOMAIN}
      key: your-plex-api-key
```

#### Jellyfin Widget
```yaml
- Jellyfin:
    icon: jellyfin.png
    href: https://jellyfin.${SECRET_DOMAIN}
    widget:
      type: jellyfin
      url: https://jellyfin.${SECRET_DOMAIN}
      key: your-jellyfin-api-key
```

#### Home Assistant Widget
```yaml
- Home Assistant:
    icon: home-assistant.png
    href: https://hass.${SECRET_DOMAIN}
    widget:
      type: homeassistant
      url: https://hass.${SECRET_DOMAIN}
      key: your-home-assistant-long-lived-token
```

### 4. **Info Widgets (Header Section)**

#### Glances Widget (if you have Glances installed)
```yaml
widgets:
  - glances:
      url: http://glances.host.or.ip:61208
      version: 4
      cpu: true
      mem: true
      disk: /
      cputemp: true
      uptime: true
      expanded: true
      label: Main Server
```

#### Search Widget
```yaml
widgets:
  - search:
      provider: google  # or duckduckgo, bing, brave
      focus: true
      showSearchSuggestions: true
      target: _blank
```

#### Stocks Widget (if interested)
```yaml
widgets:
  - stocks:
      provider: finnhub
      color: true
      cache: 1
      watchlist:
        - NVDA
        - AMD
        - TSLA
        - AAPL
        - MSFT
```

### 5. **Enhanced Kubernetes Widget**
You can expand your current Kubernetes widget:

```yaml
widgets:
  - kubernetes:
      cluster:
        show: true  # Enable cluster info
      nodes:
        show: true
        showLabel: true
        cpu: true
        memory: true
      pods:
        show: true  # Enable pod display
        showLabel: true
```

### 6. **Additional Service Widgets**

#### AdGuard Home Widget
```yaml
- AdGuard Home:
    icon: adguard-home.png
    href: https://adguard.${SECRET_DOMAIN}
    widget:
      type: adguard
      url: https://adguard.${SECRET_DOMAIN}
      username: admin
      password: your-password
```

#### Nextcloud Widget
```yaml
- Nextcloud:
    icon: nextcloud.png
    href: https://drive.${SECRET_DOMAIN}
    widget:
      type: nextcloud
      url: https://drive.${SECRET_DOMAIN}
      username: admin
      password: your-password
```

## Widget Categories

### Info Widgets (Header/Top Section)
- `datetime` ✅ (already configured)
- `resources` ✅ (already configured)
- `kubernetes` ✅ (already configured)
- `openmeteo` ✅ (already configured)
- `glances` - System monitoring
- `search` - Search bar
- `stocks` - Stock prices
- `logo` - Custom logo with link

### Service Widgets (Attached to Services)
- `prometheusmetric` - Custom Prometheus queries
- `uptimekuma` - Service uptime status
- `plex` - Plex server stats
- `jellyfin` - Jellyfin server stats
- `homeassistant` - Home Assistant entities
- `adguard` - AdGuard Home stats
- `nextcloud` - Nextcloud stats
- `iframe` - Embed any webpage

## Implementation Priority

1. **High Priority:**
   - Prometheus Metric Widget (great for cluster monitoring)
   - Uptime Kuma widgets on critical services
   - Enhanced Kubernetes widget (show pods)

2. **Medium Priority:**
   - Service widgets (Plex, Jellyfin, Home Assistant)
   - Search widget

3. **Low Priority:**
   - Glances widget (if you install Glances)
   - Stocks widget (if interested)
   - Other service-specific widgets

## Notes

- Most widgets require API keys or authentication tokens
- Service widgets attach to individual services in your services.yaml
- Info widgets go in the widgets.yaml section
- Prometheus widget requires Prometheus to be accessible (you have it at `https://prometheus.${SECRET_DOMAIN}`)
- Uptime Kuma widgets require status page slugs from your Uptime Kuma instance

## Next Steps

1. Start with Prometheus Metric Widget - it's the most powerful for your Kubernetes setup
2. Add Uptime Kuma widgets to your critical services
3. Add service-specific widgets to Plex, Jellyfin, and Home Assistant
4. Consider adding a search widget for quick access

Would you like me to help implement any of these widgets?
