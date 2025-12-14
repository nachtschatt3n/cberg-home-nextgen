# Longhorn v1.10.1-hotfix-1 Status

## Current State (2025-12-14)

**Status:** ✅ **APPLIED - Manual kubectl Method**

### Applied Images
- `longhorn-manager` DaemonSet: `longhornio/longhorn-manager:v1.10.1-hotfix-1`
- `longhorn-driver-deployer` Deployment: `longhornio/longhorn-manager:v1.10.1-hotfix-1`

### Application Method
Applied manually via `kubectl set image` commands:
```bash
kubectl set image daemonset/longhorn-manager -n storage \
  longhorn-manager=longhornio/longhorn-manager:v1.10.1-hotfix-1

kubectl set image deployment/longhorn-driver-deployer -n storage \
  longhorn-driver-deployer=longhornio/longhorn-manager:v1.10.1-hotfix-1
```

### Why Manual Application?

The Longhorn Helm chart v1.10.1 has hardcoded image tags in templates, and attempts to use Flux HelmRelease `postRenderers` encountered issues:
1. postRenderers with JSON patches initially failed due to targeting non-existent paths
2. HelmRelease entered a failed uninstall loop
3. Manual recovery was necessary to restore cluster health

**Trade-off:** Manual application means the hotfix will be overwritten on the next Helm upgrade. This is acceptable because:
- v1.10.1-hotfix-1 is temporary (waiting for official v1.10.2 or v1.11.0)
- The hotfix addresses a critical nil-pointer dereference bug
- Cluster stability takes precedence over GitOps purity

### Hotfix Purpose

**Critical Bug:** Nil-pointer dereference in `longhorn-manager:v1.10.1` causing unexpected crashes
**Reference:** https://github.com/longhorn/longhorn/issues/12233
**Release Notes:** https://github.com/longhorn/longhorn/releases/tag/v1.10.1

### Current Health Status
- HelmRelease: ✅ Ready (v35)
- Longhorn Manager Pods: ✅ 3/3 running with hotfix
- Volumes: ✅ All healthy
- Admission Webhook: ✅ Operational

### Future Upgrades

When upgrading Longhorn in the future:
1. Check if v1.10.2+ or v1.11.0+ includes the hotfix
2. If upgrading to v1.10.x, reapply hotfix after Helm upgrade
3. If upgrading to v1.11.0+, hotfix should be included in base release

### Reapply Commands (if needed after Helm upgrade)
```bash
kubectl set image daemonset/longhorn-manager -n storage \
  longhorn-manager=longhornio/longhorn-manager:v1.10.1-hotfix-1

kubectl set image deployment/longhorn-driver-deployer -n storage \
  longhorn-driver-deployer=longhornio/longhorn-manager:v1.10.1-hotfix-1
```

---
**Last Updated:** 2025-12-14
**Applied By:** Claude Code (AI Agent)
