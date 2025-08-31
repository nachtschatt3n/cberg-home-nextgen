# Default Namespace Deployments

This directory contains the deployments for the default namespace in the cberg-home-nextgen cluster.

## Deployments

### 1. Homepage
- **Chart**: jameswynn/homepage
- **Version**: 2.1.0 (updated from 2.0.2)
- **App Version**: v1.2.0 (updated from v1.0.3)
- **Purpose**: Modern, secure application dashboard

### 2. Echo Server
- **Chart**: bjw-s/app-template
- **Version**: 3.7.1
- **Purpose**: Simple HTTP echo server for testing and monitoring

## Recent Improvements

### Security Enhancements
- ✅ Added comprehensive security contexts
- ✅ Implemented NetworkPolicies for both deployments
- ✅ Added PodSecurityContext configurations
- ✅ Dropped unnecessary capabilities
- ✅ Set non-root user execution

### Resource Management
- ✅ Added resource requests and limits for homepage
- ✅ Implemented HorizontalPodAutoscalers (HPA)
- ✅ Added PodDisruptionBudgets for availability
- ✅ Optimized rolling update strategies

### Monitoring & Observability
- ✅ Added ServiceMonitor for homepage
- ✅ Enhanced Prometheus metrics collection
- ✅ Improved health check configurations

### High Availability
- ✅ Zero-downtime rolling updates (maxUnavailable: 0)
- ✅ Minimum availability guarantees via PDBs
- ✅ Optimized scaling policies

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

## Network Policies

Both deployments now have restrictive NetworkPolicies that:
- Allow ingress only from ingress controllers
- Restrict egress to necessary services (DNS, HTTP/HTTPS)
- Prevent unnecessary network access

## Horizontal Pod Autoscalers

- **CPU Threshold**: 70% utilization
- **Memory Threshold**: 80% utilization
- **Scale Range**: 1-3 replicas
- **Stabilization Windows**: 60s scale-up, 300s scale-down

## Monitoring

- **Homepage**: New ServiceMonitor for Prometheus metrics
- **Echo Server**: Existing ServiceMonitor maintained
- **Metrics Path**: `/metrics` endpoint
- **Scrape Interval**: 30 seconds

## Deployment Strategy

- **Type**: RollingUpdate
- **Max Surge**: 1 (ensures only one extra pod during updates)
- **Max Unavailable**: 0 (zero-downtime deployments)
- **Min Ready Seconds**: 10 (ensures pod stability before marking ready)
- **Revision History**: 3 (keeps last 3 revisions for rollback)

## Security Context

### Container Security
- `runAsNonRoot: true`
- `runAsUser: 1000`
- `runAsGroup: 1000`
- `allowPrivilegeEscalation: false`
- `capabilities.drop: ["ALL"]`
- `seccompProfile.type: RuntimeDefault`

### Pod Security
- `fsGroup: 1000`
- `runAsNonRoot: true`
- `runAsUser: 1000`
- `runAsGroup: 1000`

## Maintenance Notes

- **Chart Updates**: Monitor for new versions via Flux
- **Security**: Regular security context reviews
- **Monitoring**: Verify metrics collection in Grafana
- **Scaling**: Monitor HPA behavior and adjust thresholds as needed

## Flux GitOps Integration

All configurations are managed via Flux:
- **Reconciliation Interval**: 30 minutes
- **Source**: Git repository
- **Pruning**: Enabled for cleanup
- **Timeout**: 5 minutes
- **Wait**: Disabled for non-blocking deployments
