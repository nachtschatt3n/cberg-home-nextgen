# Home Assistant mDNS/Multicast Discovery Options

## Problem Statement

Home Assistant running in Kubernetes cannot discover devices via mDNS/Bonjour across VLANs. This affects:
- Apple TV discovery
- AirPlay devices
- Chromecast
- ESPHome devices
- Many IoT integrations that rely on mDNS (224.0.0.251:5353)

### Root Cause

1. **Cilium CNI with Native Routing**: Cilium in `routingMode: native` does not support multicast traffic between pods and the physical network
2. **Pod Network Isolation**: Multicast traffic from pods doesn't traverse the `cilium_host` interface properly
3. **Cross-VLAN mDNS**: Even with UniFi's mDNS proxy configured correctly, pods can't receive the proxied mDNS traffic

### Current Network Setup

| Component | Configuration |
|-----------|---------------|
| Cilium Version | 1.17.1 |
| Routing Mode | Native |
| Load Balancer | L2 Announcements + DSR |
| UniFi mDNS Proxy | Custom scope (6 VLANs) |
| MetalLB/Cilium LB | Active for HA failover |

### VLANs in mDNS Scope

| VLAN | Name | Subnet | mDNS Enabled |
|------|------|--------|--------------|
| 1 | Trusted | 192.168.30.0/24 | Yes |
| 10 | Servers | 192.168.31.0/24 | Yes |
| 20 | Trusted-Devices | 192.168.50.0/24 | Yes |
| 30 | IoT | 192.168.32.0/23 | Yes |
| 55 | k8s-network | 192.168.55.0/24 | Yes |
| 2 | USA-Peer | 192.168.60.0/24 | Yes |

---

## Solution Options

### Option 1: Enable Cilium Multicast (VXLAN Mode)

**Status**: Not recommended for this use case

#### Required Changes

```yaml
# kubernetes/apps/kube-system/cilium/app/helm-values.yaml

# CHANGE: Switch routing mode
routingMode: vxlan          # Currently: native

# ADD: Enable multicast
multicast:
  enabled: true

# RECOMMENDED: Enable jumbo frames to reduce overhead
# mtu: 9000  # Only if physical network supports it
```

After deployment:
```bash
# Register mDNS multicast group on all nodes
cilium multicast add --group-ip 224.0.0.251
```

#### Performance Implications

| Aspect | Native Routing (Current) | VXLAN (Required) |
|--------|-------------------------|------------------|
| Overhead | None | ~50 bytes/packet |
| Latency | Lower | Slightly higher |
| Throughput | Higher | ~3-5% reduction |
| Effective MTU | 1500 bytes | 1450 bytes |
| CPU Usage | Lower | Higher |

#### Pros
- Native multicast/mDNS support for all pods
- No hostNetwork hacks needed
- MetalLB failover preserved
- Simpler network topology

#### Cons
- Performance overhead on ALL pod traffic
- Disruptive change (Cilium restart required)
- Multicast feature is Beta in Cilium
- DSR load balancer mode may need reconfiguration
- Overkill - changes entire network stack for one feature

#### Migration Risk: Medium
- Rolling restart of Cilium + all pods required
- Rollback is easy (revert config, restart)

---

### Option 2: Multus CNI (Secondary Network Interface)

**Status**: Recommended approach

#### Concept

Add a second network interface to Home Assistant that connects directly to the physical network (macvlan/ipvlan), while keeping the primary Cilium interface for cluster communication.

#### Prerequisites

Already configured:
```yaml
# Cilium helm-values.yaml
cni:
  exclusive: false  # Allows Multus
```

#### Implementation Steps

1. **Install Multus CNI** (if not already installed)

2. **Create NetworkAttachmentDefinition**:
```yaml
apiVersion: k8s.cni.cncf.io/v1
kind: NetworkAttachmentDefinition
metadata:
  name: macvlan-k8s-network
  namespace: home-automation
spec:
  config: |
    {
      "cniVersion": "0.3.1",
      "type": "macvlan",
      "master": "enp86s0",
      "mode": "bridge",
      "ipam": {
        "type": "static",
        "addresses": [
          {
            "address": "192.168.55.50/24",
            "gateway": "192.168.55.1"
          }
        ]
      }
    }
```

3. **Update Home Assistant HelmRelease**:
```yaml
controllers:
  home-assistant:
    pod:
      annotations:
        k8s.v1.cni.cncf.io/networks: macvlan-k8s-network
```

#### Pros
- Surgical fix - only affects Home Assistant
- Keeps optimized native routing for all other workloads
- MetalLB failover still works (primary interface)
- Full mDNS/multicast access via secondary interface

#### Cons
- Additional complexity (two network interfaces)
- Need to manage static IP for secondary interface
- macvlan has limitations (can't communicate with host on same interface)

#### Migration Risk: Low
- Only affects Home Assistant pod
- Easy to test and rollback

---

### Option 3: hostNetwork Mode

**Status**: Currently implemented for **Matter Server** (and temporarily for Home Assistant)

#### Configuration

```yaml
# kubernetes/apps/home-automation/matter-server/app/helmrelease.yaml
controllers:
  matter-server:
    pod:
      hostNetwork: true
      dnsPolicy: ClusterFirstWithHostNet
```

#### Pros
- Simple to implement
- Full network access including mDNS (Essential for Matter/Thread)
- Works immediately

#### Cons
- **Breaks MetalLB failover** - pod uses node IP, not LoadBalancer IP
- Pod is tied to specific node's network
- Port conflicts possible with host services
- Less isolation

#### Implementation Note for Matter
The **Matter Server** requires robust mDNS access to discover Thread Border Routers (like SLZB-06P7) and Matter devices. Using `hostNetwork: true` combined with defining the primary interface (e.g., `args: ["--primary-interface", "enp86s0"]`) ensures reliable discovery across VLANs when the upstream gateway (UniFi) has an mDNS reflector enabled. This is the **production** configuration for `matter-server` in this cluster.

#### When to Use
- Quick testing
- Single-node clusters
- When failover is not critical
- **Required for Matter/Thread discovery** in complex network topologies without Multus

---

### Option 4: mDNS Proxy Sidecar

**Status**: Alternative approach

#### Concept

Run an mDNS proxy as a sidecar container with hostNetwork that forwards discovery results to the main container via localhost/shared volume.

#### Implementation

```yaml
controllers:
  home-assistant:
    containers:
      app:
        # Main HA container (normal pod network)
        ...
      mdns-proxy:
        image: appropriate-mdns-proxy-image
        # Sidecar with hostNetwork access
        ...
    pod:
      # Note: Can't mix hostNetwork per-container in k8s
      # Would need a separate proxy deployment
```

**Note**: Kubernetes doesn't support per-container hostNetwork, so this would require:
- Separate mDNS proxy Deployment with hostNetwork
- Communication via Service or shared storage

#### Pros
- Keeps HA in normal pod network
- Dedicated component for mDNS handling

#### Cons
- Complex architecture
- Additional component to maintain
- May not work for all integrations (some need direct network access)

---

### Option 5: Static Device Configuration

**Status**: Workaround, not a solution

#### Approach

Manually configure discovered devices by IP address in Home Assistant, bypassing mDNS discovery entirely.

#### Example

```yaml
# configuration.yaml
apple_tv:
  - host: 192.168.30.179
    name: Living Room
```

#### Pros
- No infrastructure changes needed
- Works with current setup

#### Cons
- Manual maintenance
- Doesn't work for integrations that require mDNS
- New devices must be added manually
- Some integrations don't support manual IP entry

---

## Recommendation

### For This Cluster

**Recommended: Option 2 (Multus CNI)**

Reasons:
1. Preserves optimized native routing performance
2. Surgical fix that only affects Home Assistant
3. Maintains MetalLB failover capability
4. `cni.exclusive: false` already configured

### Implementation Priority

1. **Short-term**: Keep hostNetwork (Option 3) for immediate functionality
2. **Medium-term**: Implement Multus (Option 2) for proper HA support
3. **Long-term**: Monitor Cilium multicast development for native solution

---

## Firewall Rules Required

Regardless of solution chosen, these UniFi firewall rules are needed:

### Policy: Home-Assistant Detection IoT (MDNS)

| Setting | Value |
|---------|-------|
| Type | Firewall |
| Action | Allow |
| Source Zone | Internal |
| Source Network | k8s-network |
| Destination Zone | Internal |
| Destination Networks | IoT, Trusted, Servers, Trusted-Devices |
| Protocol | All |
| Auto Allow Return Traffic | Yes |

**Description**: Enables Home Assistant on k8s to discover and control IoT devices via mDNS, SSDP, MQTT, and HTTP protocols.

---

## Testing Commands

### Verify mDNS Discovery (from HA pod)

```bash
kubectl exec -n home-automation deployment/home-assistant -- python3 -c "
import asyncio
import pyatv

async def scan():
    atvs = await pyatv.scan(asyncio.get_event_loop(), timeout=10)
    for atv in atvs:
        print(f'{atv.name} at {atv.address}')

asyncio.run(scan())
"
```

### Test Network Connectivity

```bash
# Test IoT VLAN gateway
kubectl exec -n home-automation deployment/home-assistant -- ping -c 2 192.168.33.1

# Test specific device (Apple TV)
kubectl exec -n home-automation deployment/home-assistant -- ping -c 2 192.168.30.179
```

### Check mDNS Traffic (from host network)

```bash
kubectl exec -n home-automation -l app.kubernetes.io/name=mdns-repeater -- \
  timeout 5 python3 -c "
import socket, struct
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(('', 5353))
mreq = struct.pack('4sl', socket.inet_aton('224.0.0.251'), socket.INADDR_ANY)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
sock.settimeout(1)
for _ in range(5):
    try:
        data, addr = sock.recvfrom(2048)
        print(f'mDNS from {addr[0]}')
    except: pass
"
```

---

## References

- [Cilium Multicast Documentation](https://docs.cilium.io/en/stable/network/multicast/)
- [Cilium Routing Modes](https://docs.cilium.io/en/stable/network/concepts/routing/)
- [Multus CNI](https://github.com/k8snetworkplumbingwg/multus-cni)
- [Home Assistant Apple TV Integration](https://www.home-assistant.io/integrations/apple_tv/)

---

## Document History

| Date | Change |
|------|--------|
| 2025-12-06 | Initial analysis and documentation |
