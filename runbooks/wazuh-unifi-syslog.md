# Wazuh — UniFi Syslog/CEF Integration

Configure the UniFi Network controller to forward security events to Wazuh as CEF over UDP/514. The `wazuh-syslog-unifi` LoadBalancer service exposes the manager's syslog listener at `192.168.55.27:514/UDP` on the `k8s-network` VLAN; the UniFi controller (`192.168.30.1` on the Trusted VLAN) reaches it via inter-VLAN routing.

## Prerequisites

- Wazuh manager running and the syslog listener bound on UDP/514 (verify with `kubectl exec -n security wazuh-manager-master-0 -- ss -lun | grep :514`).
- LoadBalancer IP `192.168.55.27` reachable from UniFi: `unifictl local diagnose network` should show no routing issues; or verify directly with `ping 192.168.55.27` from a Trusted-VLAN host.
- UniFi gateway firewall: cross-VLAN routing from VLAN 1 (Trusted, 192.168.30.0/24) to VLAN 55 (k8s-network, 192.168.55.0/24) on UDP/514 is allowed by the default permissive policy. Confirm if you've tightened policies.

## Configuration

UniFi Network → Settings → System → Application Configuration → Remote Logging:

| Field | Value |
|---|---|
| **Enable Syslog Server** | On |
| **Server Address** | `192.168.55.27` |
| **Server Port** | `514` |
| **Format** | `Standard syslog` (the Halino UniFi decoders handle the CEF-like format) |
| **Include device events** | On |
| **Include client events** | On |
| **Include security events** | On |

Save. UniFi pushes a test event immediately, then continuously forwards new events.

## Verification

```bash
# Tail the manager's archived syslog feed for events from the UniFi gateway IP
kubectl exec -n security wazuh-manager-master-0 -- \
  tail -f /var/ossec/logs/archives/archives.log | grep "192.168.30.1"

# Or check via the dashboard:
# https://wazuh.uhl.cool → Security Events → filter `agent.name: <unifi-gw-ip>`
# UniFi-specific decoder rules surface as `rule.groups: unifi`
```

You should see entries like:
```
2026 May 07 21:00:01 192.168.30.1 unifi-gw: <134>2026-05-07T21:00:01+02:00 ...
```

within ~30 seconds of saving the UniFi syslog config.

## Troubleshooting

**No events arriving:**
1. Confirm the manager is listening: `kubectl exec -n security wazuh-manager-master-0 -- ss -lun | grep :514`. Expect `UNCONN ... :514`.
2. Confirm LB IP advertised: `kubectl get svc -n security wazuh-syslog-unifi -o wide`. Should show `EXTERNAL-IP 192.168.55.27`.
3. Confirm reachability from UniFi gateway: `unifictl local diagnose network` — look for routing errors to 192.168.55.0/24.
4. Check `<allowed-ips>` in `wazuh-config-configmap.yaml` includes `192.168.30.0/24` (UniFi gateway VLAN).
5. Check manager logs: `kubectl logs -n security wazuh-manager-master-0 | grep -i syslog`.

**Events arrive but don't classify as `unifi`:**
- The Halino UniFi decoders/rules are mounted from `unifi-decoder-configmap.yaml` at `/var/ossec/etc/decoders/unifi/` and `/var/ossec/etc/rules/unifi/`. Verify they exist inside the pod and that `<ruleset>` in `master.conf` includes `etc/decoders` and `etc/rules` user dirs (it does).

**Disable syslog forwarding:**
- UniFi → Remote Logging → Off. The Wazuh listener stays running but receives nothing.
