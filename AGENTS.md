# Agent-Specific Guidelines

## Scheduled Sweeps — run on the Mac, triggered by the cluster cron

Recurring health/security/version/doc/media sweeps **must execute on this Mac mini** (in the `daily-operation` Claude session), **never** in an Anthropic cloud sandbox. Reasons:

1. **Private cluster network**: All Kubernetes nodes are on VLAN 55 (192.168.55.0/24), unreachable from the internet. `kubectl`, `talosctl`, and Longhorn/Flux APIs are LAN-only.
2. **Local SOPS age key**: The age key (`~/.config/sops/age/keys.txt`) used to decrypt all cluster secrets is stored on this machine only. Cloud agents cannot decrypt `.sops.yaml` files.
3. **Local tool binaries**: `kubectl`, `talosctl`, `talhelper`, `unifictl`, `mise`, `flux` are installed locally via mise. Not available in Anthropic cloud sandboxes.
4. **UniFi controller**: Reachable only at 192.168.30.1 (Trusted VLAN). No internet exposure.
5. **Home Assistant / Zigbee2MQTT**: Internal services on private VLANs only.

**How it's scheduled (current, 2026-06-27)**: An in-cluster OpenClaw cron — "Daily Operation Sweep Every 2 Days" (id `8163c139`), every 48h anchored 04:00 Europe/Berlin — **triggers** the sweep by driving the Mac mini `daily-operation` Claude session via the `operation sweep` skill (over iterm2-harness). The sweep still **runs on the Mac** (local SOPS key, `kubectl`, mise tooling all required), so the reasons above still hold — the cluster cron is only the trigger, not a cloud sandbox.

**Do NOT create session-local `/loop` sweeps.** The old 8:17am `/loop` (CronCreate `de44f77b`) is retired and confirmed gone (2026-06-28). A local loop would double-run the sweep and clash with the cluster-driven one. For an ad-hoc sweep, send `operation sweep` (or type "run a sweep" into the `daily-operation` session) — **once**, never on a `/loop` or `CronCreate` schedule.

## Build/Lint/Test Commands
- Validate cluster manifests: `task template:configure -- --strict`
- Lint Kubernetes manifests: `kubeconform -summary -fail-on error kubernetes/apps/`
- Validate Talos configs: `talhelper validate kubernetes/bootstrap/talos/clusterconfig/`
- Run all tests: `task test` (checks template rendering, config validation)
- Test single component: `kubeconform -summary kubernetes/apps/[category]/[app]`
- Run specific task: `task [task-name]`

## Code Style
- Imports: Prefer relative imports for local files, absolute for standard libraries
- Formatting: 2-space indentation (except Python/Shell at 4), LF line endings
- Types: Use YAML schemas for configuration, JSON schema where needed
- Naming: Use kebab-case for files/directories, snake_case for variables/functions
- Error handling: Use Kubernetes pod logs for debugging, not console output
- Secrets: Never commit unencrypted; always use `.sops.yaml` with age encryption

## GitOps Workflow
- All changes must be made through the GitOps Flux workflow
- Modify configuration in the git repository
- Push changes to GitHub which triggers a webhook to reconcile the cluster
- Monitor reconciliation events in the Flux system
- Do not make direct modifications to the Kubernetes cluster

## SOPS Encryption Rules

### File Naming Convention
- When encrypting files with sops, filenames must end with `.sops` extension
- Example: `config.sops.yaml`, `secret.sops.json`
- Never commit unencrypted secrets to the repository

### SOPS Configuration Overview
The repository uses path-based encryption rules defined in `.sops.yaml`:
- **Kubernetes secrets**: `kubernetes/**/*.sops.yaml` - encrypts only `data` and `stringData` fields
- **Talos configs**: `talos/**/*.sops.yaml` - encrypts entire file
- **Age key**: `age1nw624gkjpl0sattullahnekdswjcvsgarf8gwwyf9jdqc0zm9enqyp2pf6`

### Correct Workflow for Encrypting Secrets

**CRITICAL**: SOPS creation rules are path-based. You MUST encrypt files that are already in the correct repository path.

#### ❌ WRONG: Encrypting from /tmp
```bash
# DON'T: This will fail with "error loading config: no matching creation rules found"
sops -d kubernetes/apps/namespace/app/secret.sops.yaml > /tmp/secret.yaml
# Edit /tmp/secret.yaml
sops -e /tmp/secret.yaml > kubernetes/apps/namespace/app/secret.sops.yaml
# ❌ FAILS: /tmp/secret.yaml doesn't match any path_regex rules
```

#### ✅ CORRECT: Encrypt in Repository Path
```bash
# Method 1: Edit encrypted file directly (preferred for small changes)
sops kubernetes/apps/namespace/app/secret.sops.yaml
# Opens in $EDITOR, auto-encrypts on save

# Method 2: Decrypt, copy to repo path, encrypt in place (for complex edits)
sops -d kubernetes/apps/namespace/app/secret.sops.yaml > /tmp/secret.yaml
# Edit /tmp/secret.yaml with your changes
cp /tmp/secret.yaml kubernetes/apps/namespace/app/secret-new.sops.yaml
sops -e -i kubernetes/apps/namespace/app/secret-new.sops.yaml
mv kubernetes/apps/namespace/app/secret-new.sops.yaml kubernetes/apps/namespace/app/secret.sops.yaml
rm /tmp/secret.yaml  # Clean up
```

#### Example: Updating pgAdmin Secret
```bash
# Step 1: Decrypt to temporary location for editing
sops -d kubernetes/apps/databases/pgadmin/app/secret.sops.yaml > /tmp/pgadmin-secret.yaml

# Step 2: Edit the decrypted file
# (Make your changes to /tmp/pgadmin-secret.yaml)

# Step 3: Copy to repository path with .sops.yaml extension
cp /tmp/pgadmin-secret.yaml kubernetes/apps/databases/pgadmin/app/secret-new.sops.yaml

# Step 4: Encrypt in place (file must be in kubernetes/ path)
sops -e -i kubernetes/apps/databases/pgadmin/app/secret-new.sops.yaml

# Step 5: Replace old encrypted file
mv kubernetes/apps/databases/pgadmin/app/secret-new.sops.yaml kubernetes/apps/databases/pgadmin/app/secret.sops.yaml

# Step 6: Clean up temporary files
rm -f /tmp/pgadmin-secret.yaml
```

### Common SOPS Errors and Solutions

#### Error: "error loading config: no matching creation rules found"
**Cause**: Trying to encrypt a file outside the `kubernetes/` or `talos/` directory paths.

**Solution**: Copy the file to the correct repository path before encrypting:
```bash
# Wrong: sops -e /tmp/file.yaml > kubernetes/apps/...
# Right: cp /tmp/file.yaml kubernetes/apps/... && sops -e -i kubernetes/apps/...
```

#### Error: "sops metadata not found"
**Cause**: Trying to use `sops --set` on a file that isn't encrypted yet.

**Solution**: Use direct editing or the encrypt-in-place workflow above.

#### Error: File encrypted but Flux can't decrypt
**Cause**: Age key not available in Flux namespace or incorrect encryption regex.

**Solution**:
- Verify age key secret exists: `kubectl get secret sops-age -n flux-system`
- Check encryption regex matches: Kubernetes secrets should only encrypt `data` and `stringData` fields

### Quick Reference Commands

```bash
# Edit encrypted file directly (opens in editor)
sops kubernetes/apps/namespace/app/secret.sops.yaml

# View encrypted file contents without editing
sops -d kubernetes/apps/namespace/app/secret.sops.yaml

# Verify file is properly encrypted
head -20 kubernetes/apps/namespace/app/secret.sops.yaml | grep "sops:"

# Re-encrypt file with updated keys (if age key changes)
sops updatekeys kubernetes/apps/namespace/app/secret.sops.yaml
```

## Information Security
- This repository is public, so never commit secret domains, URLs, or other sensitive information
- All secrets and sensitive data must be encrypted using SOPS before committing
- Ensure no credentials, API keys, or configuration details are exposed in the repository

## Operator-Curated Policy lives in sweep_history Postgres

Since 2026-05-27, four categories of operator decisions live in the cluster
DB, **not** in git:

| Table | What | Edit |
|---|---|---|
| `accepted_risks` | AR-NNN risk register (was `docs/security-accepted-risks.md`) | `runbooks/policy-cli.py risk` |
| `slo_definitions` | SLO targets (was `runbooks/slo-catalog.yaml`) | `runbooks/policy-cli.py slo` |
| `noise_suppressions` | known-recurring noise (was `runbooks/noise_allowlist.yaml`) | `runbooks/policy-cli.py noise` |
| `security_acceptances` | git-history + ingress allowlists (was `runbooks/security_check_acceptances.py`) | `runbooks/policy-cli.py sec` |

Browse: `https://sweep.<DOMAIN>/policies/`. JSON API at
`/api/policies/{accepted-risks,slos,noise,security}`.

Audit scripts (security-check.py, slo-check.py, health-check.sh) load policy
via the `SWEEP_PG_DSN` env var that `runbooks/sweep-run.py` sets up
automatically (port-forwards postgresql, decodes the secret). No need to
pass DSN manually unless you're running a script in isolation.

## Storage Safety — DESTRUCTIVE PVC OPERATIONS

**Source of truth: `docs/sops/storage-safety.md`. Read it before any storage delete.**

On 2026-04-26, a routine `kubectl delete pvc` on a `cifs-jellyfin-media`-class PVC (subdir=`/`, reclaim=`Delete`) recursively wiped ~4.7 TB of the SMB share in 17 minutes. This must not happen again.

**Hard rules (verbatim in `.claude/agents/cluster-ops-agent.md` and the SOP):**

1. **No CIFS/SMB/NFS PVC deletes without 3-step pre-flight.** Inspect `spec.csi.volumeAttributes.subdir`, `spec.persistentVolumeReclaimPolicy`, and the StorageClass before the action. If `subdir` is `/`/empty/`..`-traversed AND `reclaimPolicy` is `Delete`: **STOP**. Patch the PV to `Retain` first, or surface to the user with inventory and ask explicit go/no-go.
2. **"Tear down the Job + PVC" is not routine for shared-fs PVCs.** Blast radius is set by the StorageClass, not the brief.
3. **Catastrophic classes** (full share wipe on PVC delete): `cifs-jellyfin-media`, `cifs-plex-media`. **Severe** (per-app share wipe): `cifs-frigate-media`, `cifs-scrypted-media`, `cifs-icloud-docker-mu`, `cifs-jdownloader-media`, `cifs-makemkv-media`, `cifs-tube-archivist-media`, `cifs-nextcloud-data`, `cifs-paperless-{consume,export,log,media}`. Full table with sources/subdirs in `docs/sops/storage-safety.md`.
4. **Sub-agent dispatch propagates these rules verbatim.** Do not assume a sub-agent will self-discover the risk.
5. **New StorageClasses must not pair `subdir: /` with `reclaim: Delete`.** Prefer `Retain` for any class pointing at user data. Update the table in `docs/sops/storage-safety.md` in the same PR.

Pre-flight one-liner:

```bash
PV=$(kubectl -n $NS get pvc $PVC -o jsonpath='{.spec.volumeName}') && \
  kubectl get pv $PV -o jsonpath='{.spec.csi.volumeAttributes}' | jq && \
  echo "reclaim=$(kubectl get pv $PV -o jsonpath='{.spec.persistentVolumeReclaimPolicy}')"
```

## Best Practices
- Use kubectl and talosctl commands to debug cluster state rather than console output
- Prefer YAML schemas for configuration files over JSON where possible
- Follow kebab-case naming for files and directories, snake_case for variables/functions
- Use task commands for common operations like validating templates or running tests

## AI & App/Infra References

Detailed AI/Ollama operational guidance has been moved to:
- `docs/sops/ai-integration.md`

Application inventory and service-level context:
- `docs/applications.md`

Infrastructure and topology reference:
- `docs/infrastructure.md`

Zigbee2MQTT operations (permit_join API, device removal pre-flight, DB-injection recovery for CC2652-class router interview failures, backup/restore):
- `docs/sops/zigbee2mqtt.md`

Media library curation (Plex / Jellyfin / Tube Archivist layout, naming, sidecar standards, intake-from-jdownloader workflow, audit thresholds):
- `docs/sops/media-library-standards.md`
- Sub-agent: `.claude/agents/media-manager.md`
- Operator runbook: `runbooks/media-manager.md`

**Media privacy rule (public repo):** never name specific media titles (movies, TV shows, music artists/albums/tracks, YouTube channels) in any committed artifact — commit messages, docs, runbook outputs, audit reports, PR bodies. Use placeholders (`<movie>`, `<show>`, `Title (Year)`, `Show - SXXEYY`). Counts (`+26 episodes`) are fine; names are not.

## New Deployment Blueprint

Use `docs/sops/new-deployment-blueprint.md` as the default SOP for any new application rollout.

Minimum mandatory rules:
- Use GitOps only: change manifests in git, push, and rely on Flux webhook flow (no direct cluster edits and no manual reconcile by default)
- Follow code/style standards from this file (naming, formatting, schema-first config, secret handling)
- Follow namespace placement and directory structure rules from `docs/applications.md` and `docs/infrastructure.md`
- Register all user-facing web apps in Homepage via ingress annotations + labels
- Apply Longhorn storage-class rules (`longhorn` vs `longhorn-static`) from `docs/sops/longhorn.md`
- Execute rollout verification using the SOP test structure (deployment checks, health checks, security checks, rollback path)

## Network Architecture

### Physical Topology

**Internet Connection:**
- ISP: Deutsche Glasfaser (fiber)
- WAN1: 84.143.63.97 (Telekom) - Port 9
- WAN2: 100.93.84.20 (Glasfaser) - IPv6: 2a00:6020:1000:6c::5253 - Port 8

**Core Network Infrastructure:**
- **DMP-CBERG**: Main router/gateway (192.168.30.1, GbE uplink)
  - Connected to: Basement-SW-48 PoE via 10 GbE SFP+

**Switching Infrastructure:**
- **Basement-SW-48 PoE** (192.168.30.118) - 10 GbE SFP+ uplink
  - Provides PoE to access points and connects downstream switches
  - Connected devices:
    - Upstairs-AP-UAP AC LR (192.168.30.200)
    - Hallway-AP-U6 Pro (192.168.30.205)
    - Guest Room USW SW-8 (192.168.30.165, GbE)
    - Basement-SW-24-PoE (192.168.30.220, 10 GbE SFP+)
    - Basement-AP-U6+ (192.168.30.212)
    - U7 Pro (192.168.30.148)
    - Living Room-01-SW-5 (192.168.30.115, GbE)
    - Living Room-02-SW-5 (192.168.30.100, GbE)

- **Basement-SW-24-PoE** (192.168.30.220) - 10 GbE SFP+ uplink
  - Connected Kubernetes cluster nodes:
    - K8s-nuc14-01
    - K8s-nuc14-02
    - K8s-nuc14-03

**Storage:**
- **UNAS-CBERG** (192.168.55.240) - 10 GbE SFP+ connection, **k8s-network VLAN 55** (moved off Servers VLAN 10 on 2026-06-07 so NAS↔node storage is L2-switched, not routed through the gateway — fixed the ~1 Gbit inter-VLAN cap, now 2.5 GbE line rate. See `docs/sops/cifs-mount-options.md`.)

### VLAN and Network Segmentation

| VLAN ID | Network Name | Subnet | IPv6 Subnet | DHCP Range | Purpose |
|---------|--------------|--------|-------------|------------|---------|
| 1 | Trusted | 192.168.30.0/24 | 2a00:6020:ad52:4300::/64 | 14/101 leases | Network infrastructure, trusted admin devices |
| 2 | USA-Peer | 192.168.60.0/24 | - | 1/249 leases | VPN/peering connections |
| ~~10~~ | ~~Servers~~ | ~~192.168.31.0/24~~ | — | — | **RETIRED 2026-06-07** — folded into VLAN 55. NAS + SolarFocus heater moved to VLAN 55 (.240/.241); old K3s pi-cluster, AdGuard@NAS, old PiKVM, CC2652 zigbee hub decommissioned. Kept here for history. |
| 20 | Trusted-Devices | 192.168.50.0/24 | 2a00:6020:ad52:4302::/64 | 7/101 leases | Trusted client devices |
| 30 | IoT | 192.168.32.0/23 | 2a00:6020:ad52:4303::/64 | 102/499 leases | IoT devices, smart home |
| 40 | Clients-Guests-Untrusted | 192.168.34.0/24 | - | 1/191 leases | Guest and untrusted devices |
| 55 | k8s-network | 192.168.55.0/24 | 2a00:6020:ad52:4304::/64 | 0/11 leases | Kubernetes cluster nodes + storage servers (NAS @ .240). Cilium LB pool .2-.10/.14-.199/.211-.239; nodes .11-.13; DHCP .200-.210; **physical servers reserved .240-.254** |

### WiFi Networks

| SSID | Network (VLAN) | Bands | Clients | Security |
|------|----------------|-------|---------|----------|
| cberg-trusted-clients | Trusted-Devices (20) | 2.4 GHz, 5 GHz, 6 GHz | 6 | WPA2/WPA3 |
| cberg-guests | Clients-Guests-Untrusted (40) | 2.4 GHz, 5 GHz | 1 | WPA2 |
| cberg-iot | IoT (30) | 2.4 GHz | 74 | WPA2 |
| Cberg-usa | USA-Peer (2) | 2.4 GHz, 5 GHz, 6 GHz | 1 | WPA2/WPA3 |

**Access Points:**
- Upstairs-AP-UAP AC LR (192.168.30.200) - GbE, legacy AC
- Hallway-AP-U6 Pro (192.168.30.205) - GbE, WiFi 6
- Basement-AP-U6+ (192.168.30.212) - GbE, WiFi 6
- U7 Pro (192.168.30.148) - GbE, WiFi 7

### mDNS Configuration

**Gateway mDNS Proxy:** Custom scope enabled for cross-VLAN mDNS resolution

**VLAN Scope (mDNS bridging enabled):**
- Trusted (1)
- Servers (10)
- Trusted-Devices (20)
- IoT (30)
- k8s-network (55)
- USA-Peer (2)

**Excluded from mDNS:**
- Clients-Guests-Untrusted (40) - isolated guest network

### Kubernetes Cluster Network

**Cluster Nodes:**
- All three nodes connected to Basement-SW-24-PoE via GbE
- Node IPs assigned from k8s-network (192.168.55.0/24, VLAN 55)
- Dedicated network segment isolated from other VLANs

**Inter-VLAN Access:**
- NAS storage (192.168.55.240) is **on VLAN 55 itself** — node↔NAS traffic is L2-switched (no gateway hop). Do NOT put bulk storage behind inter-VLAN routing: the UDM-Pro caps a routed flow at ~1 Gbit/s (CPU routing, offload off), which is why the NAS was moved onto VLAN 55.
- Kubernetes services still routed cross-VLAN to:
  - IoT VLAN (30) - for home automation integrations
  - Trusted VLAN (1) - for network management
  - Servers VLAN (10) - remaining legacy devices until retired
- Gateway routing and firewall rules control cross-VLAN access

### Network Security Posture

**Default Security:** Allow All (permissive internal routing)

**Network Isolation:**
- Guest network (VLAN 40) isolated from internal networks
- IoT devices (VLAN 30) segmented but accessible for integrations
- Kubernetes cluster (VLAN 55) on dedicated segment with controlled access
- Server infrastructure (VLAN 10) on separate segment

**IPv6:**
- Dual-stack enabled on most networks (Trusted, Servers, IoT, Trusted-Devices, k8s-network)
- Guest and USA-Peer networks IPv4-only

### Network Debugging Commands

#### Basic Network Connectivity
```bash
# Check UniFi controller connectivity
ping 192.168.30.1

# Check Kubernetes node connectivity
ping 192.168.55.{node-ip}

# Check NAS connectivity
ping 192.168.55.240

# Verify cross-VLAN routing
traceroute {destination-ip}

# Check DNS resolution (default DNS server: AdGuard Home at 192.168.55.5)
nslookup {hostname}
dig {hostname}
dig @192.168.55.5 {hostname}

# Check network interfaces on nodes (via kubectl exec or talosctl)
kubectl exec -n {namespace} {pod} -- ip addr
kubectl exec -n {namespace} {pod} -- ip route
```

#### UniFi Network Diagnostics (unifictl)

**Prerequisites:**
```bash
# Configure unifictl for local controller access (run once)
unifictl login \
  --controller-url https://192.168.30.1:8443 \
  --username cli-adm \
  --site default \
  --scope user
# (enter password when prompted)
```

**Network Health & Status:**
```bash
# Overall network health
unifictl local health get

# WAN connectivity status
unifictl local wan get

# Network events (alerts, warnings)
unifictl local event list

# Recent events filtered
unifictl local event list -o json | jq '.[] | select(.key | contains("EVT_"))'

# Comprehensive network diagnostics (multi-endpoint)
unifictl local diagnose network

# WiFi performance diagnostics
unifictl local diagnose wifi

# System log critical entries
unifictl local log critical
```

**Device Monitoring:**
```bash
# List all network devices (switches, APs, gateway)
unifictl local device list

# Filter by device type
unifictl local device list --filter "SW"      # Switches
unifictl local device list --filter "AP"      # Access Points
unifictl local device list --filter "UDM"     # Gateway

# Watch devices in real-time (refresh every 5s)
unifictl local device list --watch 5

# Export device inventory to CSV
unifictl local device list -o csv > /tmp/devices.csv

# Rogue AP detection (returns ALL neighbour APs — hundreds; only an
# evil-twin broadcasting one of OUR SSIDs is a real finding)
unifictl local stat rogueap

# IPS/IDS threat-management alarms (the main UniFi threat signal; 5.5.0+)
unifictl local stat alarm                    # active alarms
unifictl local stat alarm --archived         # include archived

# Controller admin-access audit trail — who logged in, source IP, platform (5.5.0+)
unifictl local log admin-activity --limit 20

# System logs (modern UniFi-OS endpoints, fixed in 5.5.0+)
unifictl local log critical
unifictl local log device-alert
unifictl local event list
```

> UniFi is **not** ingested into Wazuh (no `unifi` decoder), so UniFi threat
> monitoring is done natively via unifictl in the sweep's security-check
> (`stat alarm` IPS/IDS · `stat rogueap` evil-twin · `log admin-activity`
> audit). Requires unifictl ≥ 5.5.0 (`.mise.toml` pin); the legacy
> `event list`/`log` endpoints 404 on this firmware before that release.

**Client Connectivity:**
```bash
# List all connected clients (default limit 30)
unifictl local client list

# Filter by connection type
unifictl local client list --wired
unifictl local client list --wireless

# Show blocked clients
unifictl local client list --blocked

# Watch clients in real-time
unifictl local client list --watch 5

# Top bandwidth consumers
unifictl local top-client list --limit 20
unifictl local top-device list --limit 10

# Correlate all data for a specific client
unifictl local correlate client <MAC>

# Diagnose a specific client's connectivity
unifictl local diagnose client <MAC>
```

**Network Configuration:**
```bash
# List VLANs/networks
unifictl local network list

# List WiFi networks (SSIDs)
unifictl local wlan list

# List firewall rules
unifictl local firewall-rule list

# List firewall groups
unifictl local firewall-group list

# Port profiles (switch port configurations)
unifictl local port-profile list

# Security settings
unifictl local security get
```

**Traffic Analysis:**
```bash
# DPI (Deep Packet Inspection) summary
unifictl local dpi get

# Top clients by traffic
unifictl local top-client list --limit 10 -o json

# WiFi connectivity statistics
unifictl local wifi connectivity

# Time-series traffic data for trend analysis
unifictl local time-series traffic
unifictl local time-series wifi
```

**Device Management:**
```bash
# Get specific device details
unifictl local device get <MAC>

# Restart a device
unifictl local device restart <MAC>

# Adopt an unadopted device
unifictl local device adopt <MAC>

# Upgrade device firmware
unifictl local device upgrade <MAC>

# Bulk adopt all unadopted devices
unifictl local device adopt-all

# Correlate all data for a device or AP
unifictl local correlate device <MAC>
unifictl local correlate ap <MAC>
```

**Client Management:**
```bash
# Block a client
unifictl local client block <MAC>

# Unblock a client
unifictl local client unblock <MAC>

# Force reconnect a client
unifictl local client reconnect <MAC>

# View client connection history
unifictl local client history <MAC>
```

**Troubleshooting Workflows:**
```bash
# Check for network issues
unifictl local health get -o json | jq '.subsystems[] | select(.status != "ok")'

# Find offline devices
unifictl local device list -o json | jq -r '.[] | select(.state != 1) | "\(.name): \(.state_txt)"'

# Check for high client count on specific AP
unifictl local device list --filter "Hallway-AP" -o json | jq '.[].num_sta'

# Export all configuration for backup
unifictl local network list -o csv > /tmp/networks-backup.csv
unifictl local wlan list -o csv > /tmp/wlans-backup.csv
unifictl local firewall-rule list -o csv > /tmp/firewall-backup.csv
```

**Output Formats:**
```bash
# Pretty table (default, human-readable)
unifictl local device list

# JSON (for scripting and jq processing)
unifictl local device list -o json

# CSV (for spreadsheets and reporting)
unifictl local device list -o csv

# Raw API response
unifictl local device list -o raw

# LLM-optimized (schema + summaries)
unifictl local device list -o llm
```

## Longhorn Storage Management

Full SOP (storage class selection, dynamic vs static volume creation,
volumeHandle patterns, common mistakes, debugging commands):
**[`docs/sops/longhorn.md`](docs/sops/longhorn.md)**.

Quick agent rules (anything more, read the SOP):

- **Use `longhorn`** for app databases, growing data, caches, StatefulSet
  PVCs. PV name is auto-generated UUID. Default choice.
- **Use `longhorn-static`** ONLY for small config volumes that must
  survive namespace deletion AND need clean PV names. Requires manually
  pre-creating the Longhorn `Volume` CRD with `frontend: blockdev`
  before the PV/PVC. **Do NOT create longhorn-static if dynamic
  provisioning works** — the manual-Volume step is the most common
  failure source.
- PVC naming pattern: `{app}-{purpose}` (e.g. `postgres-data`,
  `home-assistant-config`).
- Storage Debugging entry point:
  ```bash
  kubectl get volume -n storage              # all Longhorn volumes
  kubectl get pv,pvc -A | grep <app>         # bindings
  ```

For destructive operations on CIFS/SMB/NFS PVCs see "Storage Safety"
above and the full procedure in
[`docs/sops/storage-safety.md`](docs/sops/storage-safety.md).

## Monitoring & Debugging

Full SOP (Prometheus access, Grafana, Alertmanager, ELK stack, Uptime
Kuma, Headlamp, Unpoller, plus Event Log / JSON Parsing / Flux
debugging patterns):
**[`docs/sops/monitoring.md`](docs/sops/monitoring.md)**.

Agent quick-reference (the recipes I actually use mid-session):

```bash
# Port-forward Prometheus + list firing alerts (sans Watchdog noise)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s http://localhost:9090/api/v1/alerts | grep -o '"alertname":"[^"]*"' | grep -vE 'Watchdog|InfoInhibitor' | sort -u

# Scrape-target health one-liner
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import sys, json
t = json.load(sys.stdin)['data']['activeTargets']
print(f'Total: {len(t)}, Up: {sum(1 for x in t if x[\"health\"]==\"up\")}')"

# Recent cluster warnings
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -30

# Flux sanity (one-liner each)
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'

# Longhorn backup state (from CronJob `storage/backup-of-all-volumes` @ 03:00)
kubectl get volumes -n storage -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt --no-headers
```

### Always-on rules (do not move these to a SOP)

- **Prefer Python over jq** in pipes — jq's shell-escaping rules bite
  every time. `python3 -c "import sys, json; ..."` is more reliable.
- **Minimal container caveat**: `edot-collector` and similar slim
  images have no `cat` / `curl` / `wget`. Use `kubectl port-forward`
  + local curl instead of `kubectl exec -- curl ...`.

## Authentik Blueprint Management

Detailed Authentik blueprint workflows, UUIDs, ingress patterns, and troubleshooting are documented in:
- `docs/sops/authentik.md`

Required policy in this AGENTS file:
- Always use blueprints (GitOps), never UI-only configuration.
- Keep Authentik blueprint data in `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`.

## Documentation Conventions

### Folder Structure

```
runbooks/                        # Recurring operational procedures + their scripts
  version-check.md               # How to run the version check tool
  health-check.md                # Cluster health check procedure
  check-all-versions.py          # Version check script (primary tool)
  extract-current-versions.sh    # Basic extraction script (no update checking)
  check-versions.sh              # Legacy bash version check script
  version-check-current.md       # Auto-generated by runbooks/check-all-versions.py (do not hand-edit)
  health-check-current.md        # Latest health check output (do not hand-edit)
docs/
  troubleshooting/               # Active investigations — delete when resolved
    <topic>-plan.md              # Analysis and options for an ongoing issue
    <topic>-setup.md             # Reference/setup guide for a specific integration
```

### When to Create a Doc

| Situation | Where |
|-----------|-------|
| Recurring task that needs a procedure + script | `runbooks/<name>.md` (+ script alongside) |
| Active investigation or open issue (multi-session) | `docs/troubleshooting/<topic>-plan.md` |
| Integration reference guide with ongoing value | `docs/troubleshooting/<topic>-setup.md` |
| One-time migration, completed cleanup, resolved incident | Don't create — use a commit message |
| Auto-generated current state snapshot | `runbooks/*-current.md` (script-owned) |

### Lifecycle Rules

- **Runbooks**: permanent, updated in-place as procedures evolve
- **Troubleshooting docs**: delete when the issue is resolved or the integration is stable
- **`*-current.md` files**: auto-generated, never hand-edited; overwritten on next run
- **Do NOT create** point-in-time status reports, per-session health snapshots, or migration logs — use git commit messages instead

### Current Progress / Session Notes

Do not create session-specific docs. Use:
- Git commit messages for decisions and completed steps
- `runbooks/health-check-current.md` for current cluster state
- `runbooks/version-check-current.md` for current version/Renovate PR status
- `docs/troubleshooting/` only for issues that span multiple sessions and need structured analysis

### Canonical Reference Docs

Use these docs as source-of-truth references instead of duplicating large operational detail in AGENTS:
- `docs/applications.md` for application inventory and app-level context
- `docs/infrastructure.md` for infrastructure, topology, and platform reference
- `docs/sops/` for operational SOPs (including new deployment blueprint, AI integration, and Authentik blueprint workflows)

### SOP Default Structure

All SOP documents under `docs/sops/` must follow the template at:
- `docs/sops/SOP-TEMPLATE.md`

Required sections in every SOP:
- Description
- Overview
- Blueprints (or `N/A` if not applicable)
- Operational Instructions
- Examples
- Verification Tests (to confirm it worked)
- Troubleshooting
- Diagnose Examples
- Health Check
- Security Check
- Rollback Plan

Versioning requirement:
- Use date versioning format `YYYY.MM.DD` (example: `2026.02.04`)
- Include `Version` and `Last Updated` fields in the SOP header

### SOP Discovery And Usage

Before implementing operational changes, discover and apply existing SOPs:
- List SOPs: `ls docs/sops/`
- Search by topic: `rg -n "<keyword>" docs/sops/*.md`
- View SOP titles: `rg -n "^# SOP:" docs/sops/*.md`

When using an SOP:
- Follow `Operational Instructions`
- Run `Verification Tests`
- Run `Health Check` and `Security Check`
- Keep a rollback path from `Rollback Plan`

If a reusable solution is found and no matching SOP exists:
- Create a new SOP in `docs/sops/<topic>.md` using `docs/sops/SOP-TEMPLATE.md`
- Fill all required sections
- Set date-based version (`YYYY.MM.DD`)

## Special Notes
- Cursor rules: Environment configurations from .cursor/rules/env.mdc
- Copilot instructions: Not found - follow general GitHub guidelines
- always generate strong passwords when you setup secrets
