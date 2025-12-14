# Longhorn v1.10.1-hotfix-1 Status

## Current State (2025-12-14)

**Status:** ❌ **CANNOT BE APPLIED - Version Check Prevents Hotfix**

### Why Hotfix Cannot Be Applied

The v1.10.1-hotfix-1 image **cannot be applied** due to Longhorn's internal version checking logic:

```
Error starting manager: failed to upgrade since downgrading from v1.10.1 to v1.10.1-hotfix-1 is not supported
```

**Root Cause:**
- Longhorn stores the current version in a `Setting` resource: `current-longhorn-version: v1.10.1`
- Semantic versioning treats `-hotfix-1` suffix as a **pre-release identifier**
- In semver, `v1.10.1-hotfix-1 < v1.10.1` (pre-release is "less than" release)
- Longhorn's upgrade path validator rejects this as a "downgrade"

**Attempted Solution:**
We tried manually setting the image to `longhornio/longhorn-manager:v1.10.1-hotfix-1`, but this caused all longhorn-manager pods to enter CrashLoopBackOff state.

**Reverted to:** `longhornio/longhorn-manager:v1.10.1`

### Hotfix Purpose

**Critical Bug:** Nil-pointer dereference in `longhorn-manager:v1.10.1` causing unexpected crashes
**Reference:** https://github.com/longhorn/longhorn/issues/12233
**Release Notes:** https://github.com/longhorn/longhorn/releases/tag/v1.10.1

### Current Health Status (2025-12-14 16:08 CET)
- HelmRelease: ✅ Ready
- Longhorn Manager Pods: ✅ 3/3 running (v1.10.1)
- Volumes: ✅ 50/50 healthy
- Admission Webhook: ✅ Operational

**Risk Assessment:**
- The nil-pointer bug may still occur, but volumes are currently healthy
- No crashes observed in current workload
- Monitoring via weekly health checks

### Future Upgrades

**Recommended Path:**
1. Wait for official **v1.10.2** or **v1.11.0** release (includes hotfix)
2. Upgrade via Helm chart to supported version
3. Monitor https://github.com/longhorn/longhorn/releases for official releases

**DO NOT:**
- Attempt to manually apply v1.10.1-hotfix-1 (will cause crash loop)
- Try to modify `current-longhorn-version` setting (unsupported, may corrupt state)

---
**Last Updated:** 2025-12-14
**Applied By:** Claude Code (AI Agent)
