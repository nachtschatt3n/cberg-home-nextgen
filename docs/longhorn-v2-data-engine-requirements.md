# Longhorn V2 Data Engine Requirements Check

## Current State Analysis

### ✅ Already Met Requirements

1. **Kernel Version**: ✅ **PASS**
   - Current: `6.12.43-talos` (Talos v1.11.0)
   - Required: 6.7+ (recommended for stability)
   - Status: Meets requirement

2. **CPU Architecture**: ✅ **PASS**
   - Architecture: AMD64 (Intel NUC14 Pro)
   - Cores per node: 18 cores
   - Status: Sufficient (V2 engine uses 1 CPU core per instance-manager pod)

3. **Memory**: ✅ **PASS**
   - Available: ~64GB per node
   - Status: Sufficient for hugepages allocation

4. **Longhorn Version**: ✅ **PASS**
   - Current: 1.9.2
   - Status: Supports V2 data engine

### ❌ Missing Requirements

1. **Hugepages**: ❌ **NOT CONFIGURED**
   - Current: `0` hugepages available on all nodes
   - Required: 2 GiB of 2 MiB-sized pages (1024 pages = 2048 MiB)
   - Configuration needed in Talos

2. **Kernel Modules**: ❌ **NOT CONFIGURED**
   - Required modules:
     - `nvme_tcp` (NVMe over TCP support)
     - `vfio_pci` (Virtual Function I/O)
     - `uio_pci_generic` (optional, but recommended)
   - Configuration needed in Talos

3. **Longhorn V2 Data Engine**: ❌ **DISABLED**
   - Current setting: `v2DataEngine: false`
   - Configuration: `v2DataEngineHugepageLimit: 2048` (already configured)
   - Need to enable in Longhorn HelmRelease

## Required Changes

### 1. Talos Configuration - Add Hugepages and Kernel Modules

**File**: `kubernetes/bootstrap/talos/patches/global/machine-sysctls.yaml`

Add hugepages configuration:
```yaml
machine:
  sysctls:
    # ... existing sysctls ...
    vm.nr_hugepages: "1024"  # 1024 pages × 2 MiB = 2048 MiB (2 GiB)
```

**File**: `kubernetes/bootstrap/talos/patches/global/machine-intelgpu.yaml` (or create new file)

Add kernel modules:
```yaml
machine:
  kernel:
    modules:
      - name: nvme_tcp
      - name: vfio_pci
      # - name: uio_pci_generic  # Optional but recommended
```

### 2. Longhorn Configuration - Enable V2 Data Engine

**File**: `kubernetes/apps/storage/longhorn/app/helmrelease.yaml`

Change:
```yaml
v1DataEngine: true
v2DataEngine: false
```

To:
```yaml
v1DataEngine: true
v2DataEngine: true  # Enable V2 data engine
```

**⚠️ IMPORTANT WARNINGS:**

1. **DO NOT enable V2 data engine with attached volumes** - Longhorn will block this change if volumes are attached
2. **High CPU usage**: Each instance-manager pod uses 1 dedicated CPU core (100% utilization)
3. **Experimental feature**: Not recommended for production use
4. **Migration required**: Existing volumes will continue using V1 engine; new volumes can use V2

## Implementation Steps

### Step 1: Configure Talos for V2 Data Engine

1. Add hugepages sysctl to `machine-sysctls.yaml`
2. Add kernel modules to Talos configuration (create new patch file or add to existing)
3. Update `talconfig.yaml` to include the new patch file
4. Apply Talos configuration changes (requires node reboot)

### Step 2: Verify Talos Configuration

After applying Talos changes and rebooting nodes:
```bash
# Check hugepages availability
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.capacity.hugepages-2Mi}{"\n"}{end}'

# Should show: 2048Mi (or similar) for each node
```

### Step 3: Enable V2 Data Engine in Longhorn

1. Ensure no volumes are attached (or detach all volumes temporarily)
2. Update `helmrelease.yaml` to set `v2DataEngine: true`
3. Commit and push changes
4. Monitor Flux reconciliation

### Step 4: Verify V2 Data Engine

```bash
# Check V2 data engine setting
kubectl get settings.longhorn.io v2-data-engine -n storage -o jsonpath='{.value}'

# Check instance-manager pods (should see v2 pods)
kubectl get pods -n storage -l app=longhorn-instance-manager

# Check node conditions
kubectl get nodes -o json | python3 -c "
import sys, json
nodes = json.load(sys.stdin)['items']
for n in nodes:
    print(f\"{n['metadata']['name']}: hugepages-2Mi={n['status']['capacity'].get('hugepages-2Mi', 'N/A')}\")
"
```

## Performance Comparison: V1 vs V2 Data Engine

### Architectural Differences

**V1 Data Engine:**
- Traditional kernel-based I/O stack
- Uses kernel interrupts for I/O completion
- Lower CPU overhead per volume
- Good for general-purpose workloads

**V2 Data Engine (SPDK-based):**
- Userspace storage stack (SPDK - Storage Performance Development Kit)
- Polling-based I/O (no interrupts)
- Requires 1 dedicated CPU core per instance-manager pod
- Optimized for high-performance, low-latency workloads

### Expected Performance Improvements

Based on Longhorn documentation and SPDK architecture:

#### **IOPS (Input/Output Operations Per Second)**
- **V1**: Limited by kernel interrupt overhead
- **V2**: **2-4x improvement** in IOPS for random I/O workloads
- Best improvement seen in: Random read/write operations, small block sizes

#### **Throughput (Bandwidth)**
- **V1**: Good for sequential workloads
- **V2**: **1.5-3x improvement** in sequential throughput
- Best improvement seen in: Large block sequential I/O, high-bandwidth workloads

#### **Latency**
- **V1**: Kernel interrupt latency adds overhead
- **V2**: **30-50% reduction** in I/O latency
- Best improvement seen in: Low-latency requirements, database workloads

#### **CPU Efficiency**
- **V1**: Lower CPU usage per volume, but less efficient I/O processing
- **V2**: Higher CPU usage (1 core per instance-manager), but more efficient I/O per CPU cycle
- **Trade-off**: Better I/O performance at the cost of dedicated CPU cores

### Real-World Performance Characteristics

**Benchmark Environment** (from Longhorn docs):
- Hardware: Equinix m3.small.x86 (Intel Xeon E-2378G @ 2.80GHz, 64GB RAM)
- Storage: Micron 5300 SSD
- Network: 15 Gbps between nodes
- Test results show significant improvements in IOPS, bandwidth, and latency

**Your Environment** (Intel NUC14 Pro):
- 18 CPU cores per node
- ~64GB RAM per node
- NVMe SSD storage
- 2.5 GbE network (potential bottleneck for distributed storage)

### When V2 Data Engine Makes Sense

**✅ Good fit for:**
- Database workloads (PostgreSQL, MySQL, MariaDB)
- High-throughput applications (media processing, analytics)
- Low-latency requirements (real-time applications)
- I/O-intensive workloads (caching, logging)
- Applications that benefit from consistent performance

**❌ May not be worth it for:**
- Low I/O workloads (most of your volumes may not benefit)
- CPU-constrained environments (each volume needs 1 CPU core)
- General-purpose applications with moderate I/O needs
- Workloads where V1 performance is already sufficient

### Performance Considerations

- **CPU Usage**: Each V2 instance-manager pod consumes 1 full CPU core (100% utilization)
- **Memory**: 2 GiB of hugepages reserved per node (not available for other workloads)
- **Network**: Your 2.5 GbE network may limit distributed storage performance regardless of engine
- **Selective Use**: V1 and V2 engines can coexist; use V2 selectively for workloads that benefit
- **Cost-Benefit**: Consider if the performance gain justifies the CPU cost (1 core per volume)

### Recommendation for Your Cluster

With **49 volumes** currently attached:
- **Selective adoption**: Enable V2 but use it selectively for high-performance workloads
- **Migration strategy**: Keep existing volumes on V1, create new high-performance volumes with V2
- **Monitor**: Track actual performance improvements vs. CPU cost
- **Network consideration**: Your 2.5 GbE network may be the bottleneck, not the storage engine

## Rollback Plan

If issues occur:

1. **Disable V2 Data Engine**:
   - Set `v2DataEngine: false` in Longhorn HelmRelease
   - Detach any V2 volumes first

2. **Remove Talos Configuration** (if needed):
   - Remove hugepages sysctl
   - Remove kernel modules (optional, they don't hurt if unused)

## References

- [Longhorn V2 Data Engine Prerequisites](https://longhorn.io/docs/1.9.1/v2-data-engine/prerequisites/)
- [Talos Linux V2 Data Engine Support](https://longhorn.io/docs/1.9.1/advanced-resources/os-distro-specific/talos-linux-support/)
