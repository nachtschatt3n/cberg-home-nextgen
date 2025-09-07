# Tube Archivist

Tube Archivist is a self-hosted YouTube media server that downloads and indexes YouTube videos and channels.

## Architecture

This deployment consists of three main components:

1. **Tube Archivist** - Main application (bbilly1/tubearchivist)
2. **Redis** - Queue and cache storage (redis/redis-stack-server:7.2.0-v7)
3. **Elasticsearch** - Video metadata indexing (docker.elastic.co/elasticsearch/elasticsearch:8.16.0)

## Storage

- **Media Volume**: CIFS share mounted at `/youtube` for downloaded videos
- **Cache Volume**: Longhorn storage for application cache
- **Redis Data**: Longhorn storage for Redis persistence
- **Elasticsearch Data**: Longhorn storage for search index

## Environment Variables

The following environment variables are configured in the SOPS-encrypted secret `tube-archivist-secrets`:

- `TUBE_ARCHIVIST_USERNAME` - Initial admin username (default: admin)
- `TUBE_ARCHIVIST_PASSWORD` - Initial admin password (default: changeme)
- `TUBE_ARCHIVIST_ELASTIC_PASSWORD` - Elasticsearch password (default: changeme)

**⚠️ Security Note**: Change the default passwords before deploying to production!

### Modifying Secrets

To change the default passwords, decrypt the secret file, modify the values, and re-encrypt:

```bash
# Decrypt the secret
sops --decrypt kubernetes/apps/download/tube-archivist/app/secret.sops.yaml > temp-secret.yaml

# Edit the values in temp-secret.yaml
vim temp-secret.yaml

# Re-encrypt the secret
sops --encrypt temp-secret.yaml > kubernetes/apps/download/tube-archivist/app/secret.sops.yaml

# Clean up
rm temp-secret.yaml
```

## Access

Tube Archivist will be available at: `https://tube-archivist.${SECRET_DOMAIN}`

## Dependencies

- Cloudflared (for external access)
- CIFS CSI driver (for media storage)
- Longhorn (for cache and database storage)
- Cert-manager (for TLS certificates)

## Resources

- **Tube Archivist**: 200m CPU, 1-2Gi memory
- **Redis**: 100m CPU, 256-512Mi memory
- **Elasticsearch**: 500m CPU, 1-2Gi memory

## Storage Requirements

- **YouTube Media**: 1Ti (CIFS)
- **Cache**: 50Gi (Longhorn)
- **Redis Data**: 10Gi (Longhorn)
- **Elasticsearch Data**: 100Gi (Longhorn)
