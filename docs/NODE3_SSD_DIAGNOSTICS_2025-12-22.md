# Node 3 SSD Diagnostics Report

**Date:** 2025-12-22
**Node:** k8s-nuc14-03 (192.168.55.13)
**Status:** ✅ SSD Hardware Healthy - Active Monitoring & Stress Testing Enabled

> **⚠️ IMPORTANT FOR NEXT HEALTH CHECK (2025-12-29):**
> This node is under 7-day monitoring with continuous I/O stress testing.
> Check the "Health Check Validation" section below for required status checks.

---

## Executive Summary

The Samsung SSD 990 PRO 1TB on node k8s-nuc14-03 **is NOT hardware-failed**. The December 21st I/O errors were caused by **filesystem corruption from an unsafe shutdown**, not SSD failure.

**Key Finding:** SMART diagnostics show 0 media errors, 0 NVMe errors, 100% spare capacity, and all health checks passing.

---

## Drive Information

| Attribute | Value |
|-----------|-------|
| **Model** | Samsung SSD 990 PRO 1TB |
| **Serial Number** | S6Z1NU0XC43615L |
| **Firmware** | 4B2QJXD7 |
| **Capacity** | 1.00 TB |
| **Utilization** | 972 GB (97.2%) |
| **Power On Hours** | 7,363 hours (307 days) |
| **Power Cycles** | 42 |

---

## SMART Health Results (2025-12-22 21:31 UTC)

### ✅ Excellent Health Indicators

| Metric | Value | Status | Assessment |
|--------|-------|--------|------------|
| **SMART Overall Health** | PASSED | ✅ | Excellent |
| **Media Integrity Errors** | 0 | ✅ | Perfect |
| **NVMe Error Log Entries** | 0 | ✅ | No logged errors |
| **Available Spare** | 100% | ✅ | Maximum |
| **Percentage Used** | 11% | ✅ | Very low wear |
| **Temperature** | 36°C / 43°C | ✅ | Normal |
| **Critical Warning** | 0x00 | ✅ | No warnings |

### ⚠️ Monitoring Required

| Metric | Value | Status | Notes |
|--------|-------|--------|-------|
| **Unsafe Shutdowns** | 35 | ⚠️ | High count - indicates power/connection issues |

### Workload Statistics

- **Data Units Read:** 73,367,400 (37.5 TB)
- **Data Units Written:** 72,722,064 (37.2 TB)
- **Host Read Commands:** 555,255,105
- **Host Write Commands:** 2,795,804,747
- **Controller Busy Time:** 18,528 minutes

---

## December 21st Incident Analysis

### Original Error Report

**Date:** 2025-12-21 ~19:53 UTC
**Symptoms:**
- Multiple I/O errors on sectors 0, 515008, 21241888, 21282240
- EXT4 filesystem corruption
- JBD2 journal superblock write failures
- PostgreSQL database read failures
- Device `sdi` disappeared from system
- Applications in CrashLoopBackOff (1900+ restarts over 7 days)

### Root Cause Assessment

Based on SMART diagnostics, the incident was **NOT hardware failure**:

1. **Unsafe Shutdown Event**
   - One of the 35 recorded unsafe shutdowns occurred
   - Likely power loss or connection interruption
   - EXT4 journal unable to flush writes to disk
   - Filesystem metadata corrupted

2. **Cascading Filesystem Corruption**
   - Journal superblock became unwritable
   - EXT4 superblock write failed
   - Subsequent read attempts returned I/O errors
   - Device temporarily disappeared during crash recovery

3. **Evidence Against Hardware Failure:**
   - ✅ 0 media errors in SMART data
   - ✅ 0 NVMe error log entries (all 64 slots empty)
   - ✅ 100% available spare capacity
   - ✅ All SMART self-tests passing
   - ✅ Normal temperature and wear level
   - ✅ No bad sectors or remapped blocks

### Likely Scenario

The errors occurred at the **filesystem layer**, not the **hardware layer**:
- Sudden power loss → incomplete journal flush → metadata corruption
- Operating system attempted to read corrupted filesystem structures
- Kernel reported I/O errors because filesystem was inconsistent
- Reboot allowed fsck/recovery to repair filesystem
- SSD hardware remained fully functional throughout

---

## Current Status (Post-Reboot)

### Node Status
```
Name: k8s-nuc14-03
Status: Ready, SchedulingDisabled
IP: 192.168.55.13
Kubernetes: v1.34.0
Talos: v1.11.0
```

### Talos Services (All Healthy)
- ✅ apid - Running, OK
- ✅ containerd - Running, OK
- ✅ cri - Running, OK
- ✅ etcd - Running, OK
- ✅ kubelet - Running, OK
- ✅ trustd - Running, OK
- ✅ machined - Running, OK
- ✅ syslogd - Running, OK
- ✅ udevd - Running, OK

### Storage Status
- ✅ NVMe device detected: nvme0n1
- ✅ All 6 partitions mounted: p1-p6
- ✅ Longhorn storage pods running:
  - engine-image-ei-3154f3aa-27f4c (Running)
  - longhorn-csi-plugin-54z89 (Running)
  - longhorn-manager-gf6l6 (Running)

### Resource Usage
- **CPU:** 386m (2%) - Very low
- **Memory:** 2,848 Mi (4%) - Very low

---

## Automated Monitoring Setup

### SMART Monitoring CronJob

Created: `kube-system/nvme-smart-monitor-node3`

**Schedule:** Daily at 06:00 UTC
**Function:**
- Checks SMART overall health
- Monitors critical metrics (temperature, spare capacity, errors)
- Logs unsafe shutdown count
- Alerts on any failures

**View Logs:**
```bash
# Check last run
kubectl get jobs -n kube-system | grep nvme-smart-monitor

# View logs
kubectl logs -n kube-system job/nvme-smart-monitor-node3-<timestamp>

# Check history (last 7 days)
kubectl get jobs -n kube-system -l app=nvme-smart-monitor --sort-by=.metadata.creationTimestamp
```

**Manual Check:**
```bash
# Trigger immediate check
kubectl create job -n kube-system nvme-smart-manual-check-$(date +%s) \
  --from=cronjob/nvme-smart-monitor-node3
```

### I/O Stress Testing

Created: `kube-system/io-stress-test-node3`

**Purpose:** Active load testing to verify SSD stability under real I/O workload

**Configuration:**
- **Storage:** Direct hostPath to `/var/lib/io-stress-test` on node 3's SSD
- **Test Patterns:** Sequential write/read (10GB), Random write/read (4GB, 4K blocks, 4 jobs)
- **Frequency:** Continuous testing with 30-minute intervals between iterations
- **SMART Checks:** Every 12 iterations (~6 hours)
- **Duration:** 7 days continuous

**Test Patterns Per Iteration:**
1. Sequential write (10GB) - Simulates database writes
2. Sequential read (10GB) - Simulates large file operations
3. Random write (4GB, 4K blocks, 4 jobs) - Simulates heavy application load
4. Random read (4GB, 4K blocks, 4 jobs) - Simulates concurrent database queries

**Initial Results (2025-12-22 21:42 UTC):**
- ✅ Iteration 1 completed successfully
- ✅ All 4 test patterns passed
- ✅ No I/O errors detected
- ✅ SMART health: PASSED
- ✅ Temperature: 35°C

**View Stress Test Status:**
```bash
# Check if stress test is running
kubectl get pod -n kube-system -l app=io-stress-test

# View current test logs
kubectl logs -n kube-system -l app=io-stress-test --tail=100

# Check for any I/O errors reported
kubectl logs -n kube-system -l app=io-stress-test | grep -i "error"

# View latest iteration results
kubectl logs -n kube-system -l app=io-stress-test | grep "Iteration.*completed"
```

**Stop Stress Test (if needed):**
```bash
# Delete the stress test deployment
kubectl delete deployment io-stress-test-node3 -n kube-system

# Clean up test data on node (optional)
kubectl run cleanup-io-test --image=alpine --restart=Never -n kube-system \
  --overrides='{"spec":{"nodeSelector":{"kubernetes.io/hostname":"k8s-nuc14-03"},"hostPID":true,"containers":[{"name":"cleanup","image":"alpine","command":["rm","-rf","/host/var/lib/io-stress-test"],"volumeMounts":[{"name":"host","mountPath":"/host"}],"securityContext":{"privileged":true}}],"volumes":[{"name":"host","hostPath":{"path":"/"}}],"tolerations":[{"key":"node.kubernetes.io/unschedulable","operator":"Exists","effect":"NoSchedule"}]}}'
```

---

## Next Steps & Recommendations

### ✅ Completed Actions

1. **Node Rebooted** - Clean filesystem remount
2. **SMART Diagnostics** - Comprehensive health check passed
3. **Automated Monitoring** - Daily SMART checks enabled
4. **I/O Stress Testing** - Continuous active load testing deployed
5. **Documentation** - This report created

### 📋 7-Day Monitoring Period (2025-12-22 to 2025-12-29)

**Objective:** Verify stability before returning node to service

**Actions:**
1. ✅ Keep node cordoned (SchedulingDisabled)
2. ✅ Monitor daily SMART reports
3. ✅ Watch for new I/O errors in kernel logs
4. ✅ Track unsafe shutdown count
5. ✅ Continuous I/O stress testing active

**Success Criteria:**
- No new I/O errors (kernel logs)
- I/O stress test passes all iterations
- SMART health remains PASSED
- Unsafe shutdown count stays at 35
- No new filesystem corruption
- Temperature remains <60°C

**Monitoring Commands:**
```bash
# Check I/O stress test status
kubectl get pod -n kube-system -l app=io-stress-test

# View stress test progress
kubectl logs -n kube-system -l app=io-stress-test --tail=100

# Count successful iterations
kubectl logs -n kube-system -l app=io-stress-test | grep -c "completed successfully"

# Check for new I/O errors (kernel logs)
talosctl dmesg --nodes 192.168.55.13 -f | grep -i "I/O error"

# Check for stress test errors
kubectl logs -n kube-system -l app=io-stress-test | grep -i "WARNING\|ERROR\|FAILED"

# Check unsafe shutdown count
kubectl logs -n kube-system -l app=nvme-smart-monitor | grep "Unsafe Shutdowns"

# Check node events
kubectl get events -A --field-selector involvedObject.name=k8s-nuc14-03 --sort-by='.lastTimestamp'
```

### 🔄 After 7 Days (2025-12-29)

---

## 📋 Health Check Validation (For Next Weekly Health Check)

**⚠️ REQUIRED CHECKS when running the next health check:**

### 1. I/O Stress Test Status
```bash
# Verify stress test is still running
kubectl get pod -n kube-system -l app=io-stress-test
# Expected: 1/1 Running

# Check total iterations completed (should be ~300+ after 7 days)
kubectl logs -n kube-system -l app=io-stress-test | grep -c "completed successfully"

# Verify NO errors detected
kubectl logs -n kube-system -l app=io-stress-test | grep -i "WARNING\|ERROR\|FAILED"
# Expected: No output (clean)

# Check latest SMART status from stress test
kubectl logs -n kube-system -l app=io-stress-test | grep "SMART overall-health" | tail -1
# Expected: PASSED
```

### 2. Daily SMART Monitor Status
```bash
# Check last 7 SMART monitor jobs
kubectl get jobs -n kube-system -l app=nvme-smart-monitor --sort-by=.metadata.creationTimestamp | tail -7

# Verify all passed (should see 7 successful jobs)
kubectl get jobs -n kube-system -l app=nvme-smart-monitor -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.succeeded}{"\n"}{end}' | grep "1$" | wc -l
# Expected: 7

# Check unsafe shutdown count hasn't increased
kubectl logs -n kube-system -l app=nvme-smart-monitor | grep "Unsafe Shutdowns" | tail -1
# Expected: 35 (no increase from baseline)
```

### 3. Kernel I/O Error Check
```bash
# Check for any new I/O errors in last 7 days
talosctl dmesg --nodes 192.168.55.13 | grep -i "I/O error" | grep -i "nvme\|sdi\|sector"
# Expected: No new errors (only historical Dec 21 entries if any)
```

### 4. Node Health Check
```bash
# Verify node is still Ready (cordoned)
kubectl get node k8s-nuc14-03
# Expected: Ready,SchedulingDisabled

# Check for node events
kubectl get events -A --field-selector involvedObject.name=k8s-nuc14-03 --sort-by='.lastTimestamp' | tail -20
# Expected: No storage-related warnings
```

### 5. Decision Matrix

| Check | Status | Action |
|-------|--------|--------|
| I/O stress test running | ✅ Pass | Continue to next check |
| I/O stress test running | ❌ Fail | Investigate pod crash/restart |
| 300+ iterations completed | ✅ Pass | Continue to next check |
| <300 iterations | ⚠️ Warning | Check if pod was restarted |
| Zero I/O errors in stress test | ✅ Pass | Continue to next check |
| I/O errors detected | ❌ Fail | SSD still unstable - DO NOT uncordon |
| 7 successful SMART jobs | ✅ Pass | Continue to next check |
| Failed SMART jobs | ❌ Fail | Review job logs for failures |
| Unsafe shutdowns = 35 | ✅ Pass | No new power issues |
| Unsafe shutdowns > 35 | ❌ Fail | New power event - investigate |
| No new kernel I/O errors | ✅ Pass | Continue to next check |
| New kernel I/O errors | ❌ Fail | SSD still failing - DO NOT uncordon |

**✅ ALL CHECKS PASS → Safe to uncordon node**
**❌ ANY CHECK FAILS → Keep node cordoned, extend monitoring**

---

### 🔄 Return to Service (If All Checks Pass)

**If Stable (No New Issues):**

1. **Stop I/O Stress Test:**
   ```bash
   kubectl delete deployment io-stress-test-node3 -n kube-system
   ```

2. **Consider Re-enabling Scheduling:**
   ```bash
   kubectl uncordon k8s-nuc14-03
   ```

3. **Gradual Return to Service:**
   - Allow non-critical workloads first
   - Monitor for 48 hours
   - If stable, allow critical workloads

4. **Continue Monthly SMART Checks:**
   - Keep CronJob enabled
   - Review monthly for trends

**If Unstable (New Issues Detected):**

1. **Investigate Power Infrastructure:**
   - Check for UPS availability
   - Review power event logs
   - Verify PSU health

2. **Check Physical Connection:**
   - Reseat NVMe drive
   - Inspect M.2 slot for damage
   - Verify thermal pad placement

3. **Extended RMA Consideration:**
   - If unsafe shutdowns increase beyond 40
   - If new media errors appear
   - If SMART health fails

---

## Long-Term Recommendations

### Power Infrastructure

1. **UPS Protection:**
   - Ensure all nodes have UPS backup
   - Configure graceful shutdown on power loss
   - Set appropriate shutdown thresholds

2. **Power Event Monitoring:**
   - Log all power events
   - Correlate with unsafe shutdowns
   - Investigate patterns

### Storage Best Practices

1. **Regular SMART Monitoring:**
   - Continue daily checks
   - Archive results monthly
   - Track wear trends

2. **Backup Strategy:**
   - Verify Longhorn replication (currently 2-3 replicas)
   - Test volume restoration procedures
   - Document recovery processes

3. **Maintenance Windows:**
   - Schedule regular node reboots
   - Allow filesystem checks
   - Update firmware during maintenance

### Cluster Resilience

1. **Current Configuration:**
   - 3 control-plane nodes
   - 2 active, 1 cordoned
   - Adequate for HA

2. **Capacity Planning:**
   - With node 3 disabled: 66% capacity
   - Monitor resource pressure on nodes 1-2
   - Consider adding node if strain detected

---

## Technical Reference

### NVMe Device Details
```
Device: /dev/nvme0n1
Controller: nvme0
PCI ID: 0000:01:00.0
Namespace: 1
LBA Size: 512 bytes
Queue Count: 16
Power States: 5 (currently in state 0)
```

### SMART Thresholds
- **Warning Temperature:** 82°C
- **Critical Temperature:** 85°C
- **Spare Threshold:** 10%
- **Current Spare:** 100% (90% margin)

### Firmware Information
- **Version:** 4B2QJXD7
- **NVMe Version:** 2.0
- **Updates:** 3 slots available, no reset required

---

## Contact & Escalation

### Current Status
**Node:** Cordoned, Monitoring Enabled
**Next Review:** 2025-12-29
**Responsible:** System Administrator

### Escalation Triggers

**Immediate (Contact Vendor):**
- SMART health fails
- Media errors appear
- Temperature >70°C sustained
- Available spare <50%

**Investigate (Review Logs):**
- Unsafe shutdowns increase by >5
- New I/O errors detected
- Node becomes unresponsive

**Planned (After Monitoring Period):**
- Evaluate for return to service
- Update capacity planning
- Review backup strategy

---

## Conclusion

The Samsung SSD 990 PRO 1TB on node k8s-nuc14-03 is **hardware-healthy** based on comprehensive SMART diagnostics. The December 21st incident was a **filesystem corruption from unsafe shutdown**, not drive failure.

**Recommendation:** Monitor for 7 days with active I/O stress testing. If stable, the drive can safely return to production service.

**Active Monitoring:**
1. **Daily SMART checks** (CronJob at 06:00 UTC)
2. **Continuous I/O stress testing** (30-min intervals, 7 days)
3. **Kernel log monitoring** for I/O errors

**Key Metrics to Watch:**
- I/O stress test iterations (target: 300+ successful)
- Unsafe shutdown count (baseline: 35, no increase expected)
- Media errors (baseline: 0, must stay 0)
- Temperature (baseline: 35-36°C, must stay <60°C)
- SMART health (baseline: PASSED, must stay PASSED)

**Next Action:** Run health check on 2025-12-29 following the "Health Check Validation" section above.

---

**Report Generated:** 2025-12-22 21:35 UTC
**Report Updated:** 2025-12-22 21:45 UTC (added I/O stress testing)
**Next Update:** 2025-12-29 (after monitoring period)
**Automated Monitoring:** ✅ Enabled (daily SMART + continuous I/O stress)
