# Elastic Observability Stack - Deployment Status

**Date**: 2025-11-06
**Cluster**: cberg-home-nextgen
**Namespace**: monitoring

## Executive Summary

The Elastic Observability Stack has been deployed with the following status:
- ✅ **Core Stack**: Fully operational (Elasticsearch, Kibana, APM Server)
- ✅ **OpenTelemetry**: Operator and Collector deployed and working
- ⚠️  **Metricbeat**: Deployed but authentication issue preventing data flow
- ✅ **Uptime Kuma**: Integration configured (requires API key setup)

## Component Status

### ✅ FULLY OPERATIONAL

#### 1. ECK Operator
- **Version**: 2.14.0
- **Status**: Healthy
- **Purpose**: Manages Elasticsearch, Kibana, and APM Server CRDs

#### 2. Elasticsearch
- **Version**: 8.15.3
- **Health**: GREEN
- **Nodes**: 3 (elasticsearch-es-default-0/1/2)
- **Storage**: 100Gi Longhorn per node (dynamic provisioning)
- **Resources**: 2-6Gi RAM, 500m CPU per pod
- **Endpoint**: `https://elasticsearch-es-http.monitoring.svc:9200`
- **Credentials**: User `elastic`, password in secret `elasticsearch-es-elastic-user`

#### 3. Kibana
- **Version**: 8.15.3
- **Health**: GREEN
- **Replicas**: 1
- **Ingress**: `kibana.${SECRET_DOMAIN}` (internal class)
- **Homepage Integration**: ✅ Configured
- **Endpoint**: `https://kibana-kb-http.monitoring.svc:5601`

#### 4. APM Server
- **Version**: 8.15.3
- **Health**: GREEN
- **Replicas**: 2
- **Endpoint**: `https://apm-apm-http.monitoring.svc:8200`
- **Integration**: Connected to Elasticsearch and Kibana
- **Secret Token**: Configured in `apm-secrets`

#### 5. OpenTelemetry Operator
- **Chart Version**: 0.66.0
- **Status**: Running (2/2)
- **CRDs Installed**: ✅ (instrumentations.opentelemetry.io)
- **Configuration**: Uses `otel/opentelemetry-collector-k8s` image

#### 6. OpenTelemetry Collector
- **Version**: 0.92.0 (chart)
- **Replicas**: 2
- **Mode**: Deployment
- **Endpoints**:
  - OTLP gRPC: 4317
  - OTLP HTTP: 4318
  - Prometheus scrape: 9090
  - Metrics: 8888
- **Exporters**: Configured to send to APM Server via OTLP HTTP
- **ServiceMonitor**: ✅ Created for Prometheus scraping

#### 7. OpenTelemetry Auto-Instrumentation
- **Status**: ✅ Deployed
- **Resource**: `Instrumentation/monitoring/default`
- **Endpoint**: `http://otel-collector.monitoring.svc:4317`
- **Sampler**: parentbased_traceidratio (100%)
- **Languages Supported**: Java, Node.js, Python, .NET, Go

---

### ⚠️  PARTIALLY WORKING

#### Metricbeat
- **Version**: 8.15.3
- **Status**: ⚠️  Running but unable to authenticate to Elasticsearch
- **Issue**: `envsubst` in init container not properly substituting credentials
- **Current State**:
  - Init container completes successfully
  - Main container starts and scrapes Prometheus (534 events collected)
  - Authentication to Elasticsearch fails with 401 Unauthorized
  - Config shows empty username/password after templating
- **Next Steps**:
  - Debug `envsubst` variable substitution in init container
  - Alternative: Use Elastic Agent or Filebeat with simpler config
  - Consider using Kubernetes ConfigMap with literal credentials (less secure)

---

### ✅ CONFIGURED (Requires Manual Setup)

#### Uptime Kuma Integration
- **ServiceMonitor**: ✅ Created with label `release: kube-prometheus-stack`
- **Endpoint**: `/metrics` on port 3001
- **Authentication**: Basic Auth configured
- **Secret**: `uptime-kuma-metrics-auth` created
- **Manual Step Required**:
  1. Log into Uptime Kuma UI at `kuma.${SECRET_DOMAIN}`
  2. Generate API key in Settings → Security
  3. Update secret: `kubectl edit secret -n monitoring uptime-kuma-metrics-auth`
  4. Set `password` field to the API key value
- **Data Flow**: Uptime Kuma → Prometheus → Elasticsearch (via Metricbeat when fixed)

---

## Data Flow Architecture

### Traces
```
Application (auto-instrumented)
  → OpenTelemetry Collector (OTLP :4317/4318)
    → APM Server (:8200)
      → Elasticsearch
        → Kibana (APM UI)
```

### Metrics (Designed Flow)
```
Prometheus
  → Metricbeat (scrapes /federate)
    → Elasticsearch
      → Kibana (Metrics UI)

OTel Collector
  → Self-scrape (:8888)
    → APM Server
      → Elasticsearch
```

### Logs (Available but not configured)
```
Application
  → OpenTelemetry Collector (OTLP)
    → APM Server
      → Elasticsearch
        → Kibana (Logs UI)
```

### Uptime Monitoring
```
Uptime Kuma
  → Prometheus (scrapes /metrics with API key)
    → Metricbeat
      → Elasticsearch
        → Kibana
```

---

## Open Source vs Enterprise Limitations

### ✅ Available in Basic (Open Source) License

- Elasticsearch core search and aggregations
- Kibana dashboards, visualizations, Discover
- APM (Application Performance Monitoring)
- Basic authentication and HTTPS
- Role-Based Access Control (RBAC)
- Index Lifecycle Management (ILM)
- Snapshots and restore
- Basic alerting
- Canvas (basic)
- Maps (basic)
- Observability apps (APM, Metrics, Logs, Uptime)

### ❌ NOT Available (Require Platinum/Enterprise)

- Machine Learning and anomaly detection
- Advanced security (field-level, document-level security)
- Audit logging
- SAML/OIDC authentication
- Cross-cluster replication and search
- Searchable snapshots
- Advanced PDF/CSV reporting
- Advanced Canvas features
- Advanced APM features (ML-based anomaly detection)
- Data tiers and frozen indices

---

## File Locations

### Kustomizations
- Main: `kubernetes/apps/monitoring/kustomization.yaml`
- ECK Operator: `kubernetes/apps/monitoring/eck-operator/`
- Elasticsearch: `kubernetes/apps/monitoring/elasticsearch/`
- Kibana: `kubernetes/apps/monitoring/kibana/`
- APM Server: `kubernetes/apps/monitoring/apm-server/`
- OpenTelemetry Operator: `kubernetes/apps/monitoring/opentelemetry-operator/`
- OpenTelemetry Instrumentation: `kubernetes/apps/monitoring/opentelemetry-operator/instrumentation/`
- OTel Collector: `kubernetes/apps/monitoring/otel-collector/`
- Metricbeat: `kubernetes/apps/monitoring/metricbeat/`
- Uptime Kuma: `kubernetes/apps/monitoring/uptime-kuma/`

### Secrets (SOPS-encrypted)
- Elasticsearch credentials: Auto-generated by ECK in `elasticsearch-es-elastic-user`
- APM Server: `kubernetes/apps/monitoring/apm-server/app/secret.sops.yaml`
- Metricbeat: `kubernetes/apps/monitoring/metricbeat/app/secret.sops.yaml`
- Uptime Kuma metrics auth: `kubernetes/apps/monitoring/uptime-kuma/app/metrics-secret.sops.yaml`

---

## Known Issues and Resolutions

### 1. ✅ RESOLVED: Metricbeat Init Container Crash
- **Issue**: Init container used `busybox` image but tried to run Alpine `apk` command
- **Resolution**: Changed image to `alpine:latest` in helmrelease.yaml:31
- **Commit**: `5489481`

### 2. ✅ RESOLVED: OpenTelemetry Operator CRD Chicken-Egg Problem
- **Issue**: Instrumentation CRD applied before Operator installed CRDs
- **Resolution**: Split into two kustomizations with dependency
  - `opentelemetry-operator/ks.yaml`: Operator HelmRelease
  - `opentelemetry-operator/instrumentation-ks.yaml`: Instrumentation resource (depends on operator)
- **Commit**: `91e5cc1`

### 3. ✅ RESOLVED: OpenTelemetry Operator Helm Chart Breaking Changes
- **Issue 1**: Chart 0.66.0 doesn't support `admissionWebhooks.enabled`
- **Resolution**: Removed unsupported config
- **Commit**: `c2b325c`

- **Issue 2**: Chart requires `manager.collectorImage.repository`
- **Resolution**: Set to `otel/opentelemetry-collector-k8s`
- **Commit**: `50396e0`

### 4. ⚠️  ONGOING: Metricbeat Elasticsearch Authentication
- **Issue**: `envsubst` not substituting environment variables in config template
- **Root Cause**: Environment variables added to init container, but substitution still produces empty values
- **Current Investigation**: Debugging why `envsubst` isn't working despite variables being present
- **Workaround Options**:
  - Use Elastic Agent instead (simpler, more modern)
  - Mount credentials directly in config (less flexible)
  - Use external config management

---

## Access Information

### Kibana UI
- **URL**: `https://kibana.${SECRET_DOMAIN}`
- **Username**: `elastic`
- **Password**: Get from secret
  ```bash
  kubectl get secret -n monitoring elasticsearch-es-elastic-user \
    -o jsonpath='{.data.elastic}' | base64 -d
  ```

### Elasticsearch API
```bash
# Get password
ES_PASSWORD=$(kubectl get secret -n monitoring elasticsearch-es-elastic-user \
  -o jsonpath='{.data.elastic}' | base64 -d)

# Test connection
kubectl run curl --rm -i --tty --image=curlimages/curl -- \
  curl -k -u "elastic:$ES_PASSWORD" \
  https://elasticsearch-es-http.monitoring.svc:9200/_cluster/health?pretty
```

### APM Server
```bash
# Get secret token
kubectl get secret -n monitoring apm-secrets \
  -o jsonpath='{.data.apm_secret_token}' | base64 -d
```

---

## Next Steps

### Immediate (Critical)
1. **Fix Metricbeat authentication** - Debug envsubst or implement alternative
2. **Configure Uptime Kuma API key** - Generate in UI and update secret

### Short Term (Enhancement)
3. **Add ServiceMonitors for Elastic Stack components**
   - Elasticsearch metrics
   - Kibana metrics
   - APM Server metrics
4. **Configure log collection** - Use OTel Collector or Filebeat for pod logs
5. **Set up Elasticsearch ILM policies** - Manage data retention

### Long Term (Optimization)
6. **Implement proper backup strategy** - Elasticsearch snapshots to S3/MinIO
7. **Add Grafana dashboards** - Visualize Elastic Stack metrics in existing Grafana
8. **Document runbooks** - Common operations and troubleshooting
9. **Performance tuning** - Optimize Elasticsearch heap, storage, and query performance

---

## Lessons Learned

1. **Helm Chart Breaking Changes**: Always check chart UPGRADING.md and changelogs when updating versions
2. **CRD Installation Order**: Use Flux kustomization dependencies when resources depend on CRDs
3. **Init Container Environment**: Environment variables must be explicitly defined in init containers, not inherited
4. **Metricbeat Complexity**: Consider simpler alternatives (Elastic Agent) for modern deployments
5. **Open Source Limitations**: Verify feature availability before architectural decisions

---

## References

- [Elastic Cloud on Kubernetes (ECK) Documentation](https://www.elastic.co/guide/en/cloud-on-k8s/current/index.html)
- [OpenTelemetry Operator Documentation](https://opentelemetry.io/docs/kubernetes/operator/)
- [Metricbeat Reference](https://www.elastic.co/guide/en/beats/metricbeat/current/index.html)
- [Elasticsearch Open Source vs Licensed Features](https://www.elastic.co/subscriptions)
