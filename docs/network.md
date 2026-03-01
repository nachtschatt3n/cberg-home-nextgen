# Network Reference

> Maintained manually. Update after VLAN changes, device additions, or WiFi config changes.
> Validate against live UniFi config with `python3 runbooks/doc-check.py`.

---

## Overview

Network built on UniFi equipment with a 10 GbE backbone. Dual WAN with ISP failover.
Multiple VLANs segment traffic by trust level. Kubernetes cluster on dedicated VLAN 55.

**Internet Connections:**
- WAN1: 84.143.63.97 (Telekom) — Port 9
- WAN2: 100.93.84.20 (Deutsche Glasfaser) — IPv6: `2a00:6020:1000:6c::5253` — Port 8

---

## Physical Topology

```
Internet (Telekom / Deutsche Glasfaser)
         │
    [DMP-CBERG] — router/gateway (192.168.30.1, GbE uplink)
         │ 10 GbE SFP+
   [Basement-SW-48 PoE] (192.168.30.118)
         │ 10 GbE SFP+
   [Basement-SW-24 PoE] (192.168.30.220)
    /    │    \
NUC-01  NUC-02  NUC-03   (k8s nodes, 2.5 GbE)
```

**Basement-SW-48 PoE** (192.168.30.118) also connects:
- Upstairs-AP-UAP AC LR (192.168.30.200)
- Hallway-AP-U6 Pro (192.168.30.205)
- Basement-AP-U6+ (192.168.30.212)
- U7 Pro (192.168.30.148)
- Living Room-01-SW-5 (192.168.30.115, GbE)
- Living Room-02-SW-5 (192.168.30.100, GbE)
- Guest Room USW SW-8 (192.168.30.165, GbE)

**Additional:**
- UNAS-CBERG (192.168.31.230) — 10 GbE SFP+, Servers VLAN
- Mac Mini M4 Pro (192.168.30.111) — Ollama AI inference host

---

## VLAN Table

| VLAN ID | Name | Subnet | IPv6 Subnet | DHCP Range | Purpose |
|---------|------|--------|-------------|------------|---------|
| 1 ¹ | Trusted | 192.168.30.0/24 | 2a00:6020:ad52:4300::/64 | 14/101 leases | Network infra, trusted admin devices |
| 2 | USA-Peer | 192.168.60.0/24 | — | 1/249 leases | VPN/peering connections |
| 10 | Servers | 192.168.31.0/24 | 2a00:6020:ad52:4301::/64 | 10/249 leases | NAS, server infrastructure |
| 20 | Trusted-Devices | 192.168.50.0/24 | 2a00:6020:ad52:4302::/64 | 7/101 leases | Trusted client devices |
| 30 | IoT | 192.168.32.0/23 | 2a00:6020:ad52:4303::/64 | 102/499 leases | IoT devices, smart home |
| 40 | Clients-Guests-Untrusted | 192.168.34.0/24 | — | 1/191 leases | Guest and untrusted devices |
| 55 | k8s-network | 192.168.55.0/24 | 2a00:6020:ad52:4304::/64 | 0/11 leases | Kubernetes cluster nodes |

IPv6 is dual-stack on VLANs 1, 10, 20, 30, 55. VLANs 2 and 40 are IPv4-only.

¹ VLAN 1 is the default untagged management network. The UniFi API does not return it as a numbered
VLAN entry — this is expected behaviour, not a configuration gap.

---

## WiFi Networks

| SSID | Network (VLAN) | Bands | Security | Notes |
|------|----------------|-------|----------|-------|
| cberg-trusted-clients | Trusted-Devices (20) | 2.4 / 5 / 6 GHz | WPA2/WPA3 | Primary client WiFi |
| cberg-guests | Clients-Guests-Untrusted (40) | 2.4 / 5 GHz | WPA2 | Isolated guest network |
| cberg-iot | IoT (30) | 2.4 GHz | WPA2 | IoT devices (74 clients) |
| Cberg-usa | USA-Peer (2) | 2.4 / 5 / 6 GHz | WPA2/WPA3 | VPN peering |

---

## Access Points

| Name | IP | Generation | Connected to |
|------|----|------------|-------------|
| Upstairs-AP-UAP AC LR | 192.168.30.200 | WiFi 5 (AC) | Basement-SW-48 PoE |
| Hallway-AP-U6 Pro | 192.168.30.205 | WiFi 6 | Basement-SW-48 PoE |
| Basement-AP-U6+ | 192.168.30.212 | WiFi 6 | Basement-SW-48 PoE |
| U7 Pro | 192.168.30.148 | WiFi 7 | Basement-SW-48 PoE |

---

## Kubernetes Cluster Network

Nodes connect on VLAN 55 (k8s-network, 192.168.55.0/24).

**Key Kubernetes IPs:**
| Service | IP | Port | Purpose |
|---------|----|------|---------|
| AdGuard Home | 192.168.55.5 | 53 / 853 / 443 | DNS + ad blocking |
| k8s-gateway | 192.168.55.101 | 53 | Internal service DNS |
| External Ingress | 192.168.55.x | 80 / 443 | External-facing services |
| Internal Ingress | 192.168.55.x | 80 / 443 | Internal-only services |

**Inter-VLAN Access:**
- Kubernetes → Servers VLAN (10): NAS at 192.168.31.230
- Kubernetes → IoT VLAN (30): Home automation integrations
- Kubernetes → Trusted VLAN (1): Network management (UniFi at 192.168.30.1)
- Gateway routing and firewall rules control all cross-VLAN access

---

## DNS Architecture

```
LAN Clients → AdGuard Home (192.168.55.5)
  ├── Internal *.domain → k8s-gateway (192.168.55.101) → Internal Ingress → App
  └── External domains → Cloudflare / Quad9 (1.1.1.1 / 9.9.9.9)

Internet → Cloudflare DNS
  → Cloudflare CDN (proxied)
  → Cloudflare Tunnel (QUIC/TLS)
  → cloudflared pod → External Ingress → App
```

**Components:**
- **AdGuard Home** (192.168.55.5) — network-wide ad blocking, DNS upstream proxy, split-DNS
- **k8s-gateway** (192.168.55.101) — resolves `*.domain` to internal ingress IP
- **external-dns** — manages Cloudflare CNAME records for external ingresses automatically
- **cloudflared** — Cloudflare Tunnel outbound connection; no inbound firewall ports required

---

## mDNS Configuration

**Gateway mDNS Proxy:** Custom scope enabled for cross-VLAN mDNS resolution.

**VLANs with mDNS bridging enabled:**
- Trusted (1)
- Servers (10)
- Trusted-Devices (20)
- IoT (30)
- k8s-network (55)
- USA-Peer (2)

**Excluded from mDNS:**
- Clients-Guests-Untrusted (40) — isolated guest network, no mDNS bridging

---

## Network Security Posture

| Category | Posture |
|---------|---------|
| Default internal routing | Allow All (permissive within VLANs) |
| Guest network (VLAN 40) | Isolated — no access to internal VLANs |
| IoT (VLAN 30) | Segmented but accessible for integrations |
| Kubernetes (VLAN 55) | Dedicated segment, controlled inter-VLAN |
| External access | Cloudflare Tunnel only — no open inbound ports |
| VPN | UniFi WireGuard on DMP-CBERG |
| Gateway security | IDS/IPS, Threat Management on DMP-CBERG |

---

## Network Diagnostic Commands

### Basic Connectivity
```bash
ping 192.168.30.1       # Gateway
ping 192.168.31.230     # NAS
ping 192.168.55.5       # AdGuard Home
ping 192.168.30.111     # Mac Mini (Ollama)

traceroute {destination-ip}
nslookup {hostname}
dig {hostname}
```

### UniFi CLI (unifictl)

Configure once:
```bash
cd /home/mu/code/unifictl
unifictl local configure \
  --url https://192.168.30.1:8443 \
  --username admin \
  --password '<PASSWORD>' \
  --site default \
  --scope local \
  --verify-tls false
```

Common commands:
```bash
unifictl local health               # Overall network health
unifictl local wan                  # WAN connectivity status
unifictl local devices              # All network devices
unifictl local clients --wired      # Wired clients
unifictl local clients --wireless   # Wireless clients
unifictl local networks             # VLAN/network list
unifictl local wlans                # WiFi networks
unifictl local events               # Recent network events
unifictl local top-clients --limit 10  # Top bandwidth users

# Output formats
unifictl local devices -o json      # JSON for scripting
unifictl local devices -o csv       # CSV for reports
```

### Kubernetes Network
```bash
kubectl exec -n {ns} {pod} -- ip addr
kubectl exec -n {ns} {pod} -- ip route
kubectl get svc -A -o wide

# Check ingress LoadBalancer IPs
kubectl get svc -n network -o wide
```
