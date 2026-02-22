# Weekly Health Check Report
**Date:** Sunday, February 22, 2026
**Status:** 🟡 GOOD

## Executive Summary
The cluster is overall healthy with no critical service outages. A few minor maintenance tasks are required.

## 🔍 Findings

### 1. Stuck Jobs (Minor)
- **Job:** `kube-system/descheduler-29528880`
- **Status:** Running for 8 hours (stuck)
- **Recommendation:** Delete the stuck job to allow the next schedule to run cleanly.
  ```bash
  kubectl delete job -n kube-system descheduler-29528880
  ```

### 2. Flux Kustomization Failures (Minor)
- **Issue:** `ImagePolicy/absenty` resource validation failed.
- **Error:** `no matches for kind "ImagePolicy" in version "image.toolkit.fluxcd.io/v1"`
- **Affected Components:**
  - `my-software-development/absenty`
  - `my-software-production/absenty`
- **Cause:** Deprecated API version in manifest.
- **Recommendation:** Update manifests to use `image.toolkit.fluxcd.io/v1beta1` or `v1beta2`.

### 3. Node Alerts (False Positive)
- **Node:** 192.168.55.12
- **Alert:** "High hardware errors" (155 count)
- **Analysis:** Logs show `[talos] error serving dns request ... context deadline exceeded`.
- **Conclusion:** These are transient DNS timeouts from Feb 19th, not physical hardware failures. No action needed.

## ✅ Healthy Components
- **Core:** All nodes, deployments, and statefulsets (except noted) are healthy.
- **Storage:** Longhorn volumes are healthy.
- **Monitoring:** Prometheus/Alertmanager operational.
- **Home Automation:** Frigate, MQTT, and Zigbee devices are functioning normally.

## 📋 Action Plan
1.  [ ] Clean up stuck descheduler job.
2.  [ ] Fix `absenty` ImagePolicy API version.
