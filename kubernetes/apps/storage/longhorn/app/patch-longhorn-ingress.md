---
# Patch file to add Homepage annotations to Authentik-managed Longhorn ingress
# This ingress is auto-created by Authentik Outpost, so we patch it directly
# Run this command to apply: kubectl patch ingress -n kube-system ak-outpost-longhorn-proxy-outpost --type='json' -p='[{"op": "add", "path": "/metadata/annotations/gethomepage.dev~1enabled", "value": "true"}, {"op": "add", "path": "/metadata/annotations/gethomepage.dev~1name", "value": "Longhorn"}, {"op": "add", "path": "/metadata/annotations/gethomepage.dev~1description", "value": "Kubernetes storage management UI"}, {"op": "add", "path": "/metadata/annotations/gethomepage.dev~1group", "value": "System"}, {"op": "add", "path": "/metadata/annotations/gethomepage.dev~1icon", "value": "longhorn.png"}]'
#
# Note: This patch may be overwritten if Authentik Outpost reconciles.
# If that happens, you may need to configure Authentik Outpost to include
# these annotations, or re-apply this patch.
