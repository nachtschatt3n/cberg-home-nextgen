# SOP: Longhorn v2 Data Engine Benchmark + Rollout

> Description: Procedure for enabling Longhorn v2 data engine on a small subset of test volumes, running fio benchmarks against v1 and v2, and deciding whether to migrate production volumes. The OS prerequisites (hugepages=1024, vfio_pci, uio_pci_generic kernel modules) are already in place from the 2026-04-30 Talos v1.13 upgrade.
> Version: `2026.04.30`
> Last Updated: `2026-04-30`
> Owner: `cluster-ops`

---

## 1) Description

Longhorn v2 data engine uses SPDK (Storage Performance Development Kit) instead of the v1 data engine's tgt+iSCSI stack. v2 promises significantly better IOPS and lower latency, especially for small random I/O typical of databases.

Status as of 2026-04-30 (cluster on Longhorn v1.11.1):
- v1 data engine: GA, all production volumes use this
- v2 data engine: still **Technical Preview** in Longhorn 1.11.x — not recommended for production data, but safe for benchmarking
- v2 missing features: online replica rebuild, replica count adjustment, RWX access mode

**Goal**: prove the perf delta on this hardware (NUC14 Core Ultra 5 + Crucial NVMe), document, decide on migration path.

- Scope: test volumes only (1 fresh PVC per data engine, ephemeral)
- Prerequisites: Longhorn v1.11.x deployed, OS prereqs satisfied (verified below)
- Out of scope: migrating existing production volumes

---

## 2) Overview

| Setting | Value |
|---------|-------|
| Cluster Longhorn version | v1.11.1 |
| Hugepages required | 1024 × 2 MiB (2 GiB per node) |
| Hugepage state on cluster | 1024 on each of 3 nodes ✅ (verified post-Talos-v1.13 upgrade) |
| Required modules | `vfio_pci`, `uio_pci_generic` ✅ (loaded via `machine.kernel.modules`) |
| SPDK target | spdk_tgt (one per node, runs in instance-manager) |
| CPU reserved per node for spdk_tgt | 1 (default `data-engine-cpu-mask: 0x1`) |
| Test volume size | 1 GiB |
| fio job mix | seq read/write, rand read/write IOPS, latency |

---

## 3) Operational Instructions

### Step 0 — Pre-flight verify

```bash
# Verify hugepages on each node (need 1024)
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo -n "  $ip: HugePages_Total="
  mise exec -- talosctl -n $ip read /proc/meminfo | grep "HugePages_Total:" | awk '{print $2}'
done

# Verify modules loaded
for ip in 192.168.55.11 192.168.55.12 192.168.55.13; do
  echo -n "  $ip: vfio_pci+uio_pci="
  mise exec -- talosctl -n $ip read /proc/modules | grep -cE "^vfio_pci|^uio_pci"
done

# Verify cluster healthy before turning on a new data engine
mise exec -- kubectl -n storage get volumes.longhorn.io -o json | python3 -c "
import sys, json, collections
d = json.load(sys.stdin)
c = collections.Counter(v['status'].get('robustness', '?') for v in d['items'])
print('Longhorn:', dict(c))"
# All should be healthy. Don't proceed if any volumes are degraded/faulted/unknown.
```

### Step 1 — Enable v2 data engine in Longhorn settings

```bash
# Patch settings via kubectl (less risky than helmrelease change for an experiment)
mise exec -- kubectl -n storage patch settings v2-data-engine --type='merge' -p '{"value":"true"}'

# Wait for instance managers to restart with v2 capability
sleep 30
mise exec -- kubectl -n storage get instancemanager
# Look for new IM pods with `dataEngine: v2` (in addition to existing v1 IMs)
```

### Step 2 — Create v2 StorageClass

```bash
cat <<'EOF' | mise exec -- kubectl apply -f -
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: longhorn-v2-test
provisioner: driver.longhorn.io
allowVolumeExpansion: true
reclaimPolicy: Delete
volumeBindingMode: Immediate
parameters:
  numberOfReplicas: "2"
  staleReplicaTimeout: "30"
  fsType: "ext4"
  dataEngine: "v2"
EOF
```

### Step 3 — Provision two PVCs (one v1, one v2) and run fio

```bash
cat <<'EOF' | mise exec -- kubectl apply -f -
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: fio-v1, namespace: default }
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn
  resources: { requests: { storage: 1Gi } }
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: fio-v2, namespace: default }
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn-v2-test
  resources: { requests: { storage: 1Gi } }
---
apiVersion: batch/v1
kind: Job
metadata: { name: fio-bench-v1, namespace: default }
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: fio
          image: ghcr.io/dvob/fio:latest
          command: [sh, -c]
          args:
            - |
              cd /data
              fio --name=seqwrite --rw=write --bs=1M --size=512M --numjobs=1 --runtime=30 --time_based
              fio --name=seqread  --rw=read  --bs=1M --size=512M --numjobs=1 --runtime=30 --time_based
              fio --name=randwrite --rw=randwrite --bs=4k --size=512M --iodepth=32 --numjobs=4 --runtime=30 --time_based
              fio --name=randread  --rw=randread  --bs=4k --size=512M --iodepth=32 --numjobs=4 --runtime=30 --time_based
          volumeMounts:
            - { name: data, mountPath: /data }
      volumes:
        - { name: data, persistentVolumeClaim: { claimName: fio-v1 } }
---
apiVersion: batch/v1
kind: Job
metadata: { name: fio-bench-v2, namespace: default }
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: fio
          image: ghcr.io/dvob/fio:latest
          command: [sh, -c]
          args:
            - |
              cd /data
              fio --name=seqwrite --rw=write --bs=1M --size=512M --numjobs=1 --runtime=30 --time_based
              fio --name=seqread  --rw=read  --bs=1M --size=512M --numjobs=1 --runtime=30 --time_based
              fio --name=randwrite --rw=randwrite --bs=4k --size=512M --iodepth=32 --numjobs=4 --runtime=30 --time_based
              fio --name=randread  --rw=randread  --bs=4k --size=512M --iodepth=32 --numjobs=4 --runtime=30 --time_based
          volumeMounts:
            - { name: data, mountPath: /data }
      volumes:
        - { name: data, persistentVolumeClaim: { claimName: fio-v2 } }
EOF

# Watch jobs
mise exec -- kubectl -n default wait --for=condition=complete job/fio-bench-v1 --timeout=10m
mise exec -- kubectl -n default wait --for=condition=complete job/fio-bench-v2 --timeout=10m

# Capture results
mise exec -- kubectl -n default logs job/fio-bench-v1 > /tmp/fio-v1.txt
mise exec -- kubectl -n default logs job/fio-bench-v2 > /tmp/fio-v2.txt
```

### Step 4 — Compare key metrics

```bash
for f in /tmp/fio-v1.txt /tmp/fio-v2.txt; do
  echo "=== $f ==="
  grep -E "BW=|IOPS=|lat \(usec\):" $f | head -8
done
```

Expected v2 advantage: 2-5x random IOPS, 30-50% lower latency on small random I/O. Sequential throughput similar.

### Step 5 — Cleanup

```bash
mise exec -- kubectl -n default delete job fio-bench-v1 fio-bench-v2
mise exec -- kubectl -n default delete pvc fio-v1 fio-v2
mise exec -- kubectl delete sc longhorn-v2-test
# Optionally disable v2 again until ready for production:
mise exec -- kubectl -n storage patch settings v2-data-engine --type='merge' -p '{"value":"false"}'
```

---

## 6) Verification Tests

- **Test 1**: post-fio, both PVCs are unbound and the underlying Longhorn volumes are deleted (`reclaimPolicy: Delete`).
- **Test 2**: `kubectl -n storage get volumes.longhorn.io` shows no leftover test volumes.
- **Test 3**: cluster perf baseline unchanged: `flux get kustomizations -A` all Ready, no firing alerts beyond the steady-state.

---

## 7) Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| v2 setting won't accept `true` | Hugepages not 1024 | Verify Step 0; reboot node if missing |
| v2 instance-manager pod CrashLoopBackOff | spdk_tgt failed to start | `kubectl -n storage logs <im-pod>`; common cause: kernel modules missing or hugepages not reserved |
| v2 PVC stuck in Pending | StorageClass `dataEngine: v2` parameter typo | Verify SC matches schema |
| fio reports "permission denied" | NS PSA = restricted | Run in `default` NS (privileged) or label NS |

---

## 11) Rollback Plan

The benchmark uses fresh PVCs with `reclaimPolicy: Delete`. Cleanup in Step 5 removes both volumes and the test SC. Setting `v2-data-engine: false` after the test stops new v2 IMs.

No production volumes are touched. Rollback is "delete the test artifacts."

If v2 IM startup destabilizes the cluster: `kubectl -n storage patch settings v2-data-engine --type='merge' -p '{"value":"false"}'` and the v2 IMs will scale down.

---

## Version History

- `2026.04.30`: Initial SOP — written after the v1.13 upgrade put OS prereqs in place. Actual benchmark run deferred to a less-stressful maintenance window (cluster has gone through 4 restoration cycles today; data engines should sit quiet for 24h before adding new variables).
