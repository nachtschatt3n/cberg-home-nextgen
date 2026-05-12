# SOP: Disaster Recovery

> Description: Recovery procedures for cluster, node, storage, and external-
> dependency failures. Complements `docs/sops/backup.md` (preventive workflow)
> with the *when-something-broke* response runbook.
> Version: `2026.05.12`
> Last Updated: `2026-05-12`
> Owner: `Platform`

---

## 1) Description

This SOP catalogs failure scenarios from "one node died" up to "everything is
gone" and the procedure to get back to a working cluster. Every scenario has:

- **Detection** — how you notice it.
- **Blast radius** — what stops working.
- **Recovery** — concrete steps, ordered.
- **Verification** — how you know recovery worked.
- **Prereqs** — what must already exist (backups, keys, hardware).

Scope: Talos K8s cluster, Longhorn storage, CIFS NAS, GitHub repo, SOPS age
key, Cloudflare account, UniFi controller, Authentik IdP.

Out of scope: application-level data corruption (e.g., a single Postgres
table-truncate). That's handled per-app via Longhorn snapshot + restore from
`docs/sops/backup.md`.

---

## 2) Overview — recovery tier matrix

| Scenario | Tier | Time to recovery | Data loss possible? | SOP section |
|---|---|---|---|---|
| Single node loss (1-of-3) | T0 | minutes (auto) | No | §4.1 |
| Two or three node loss | T1 | hours (manual) | If backup is stale | §4.2 |
| Full cluster rebuild (new hardware) | T2 | half-day | If backup is stale | §4.3 |
| SOPS age key loss | T3 | days (rotate everything) | No data, but every secret must rotate | §4.4 |
| Longhorn volume corruption | T0/T1 | min-hours | Last backup → restore point | §4.5 |
| NAS (UNAS-CBERG) failure | T1/T2 | hours-days | Media + intake; cluster data survives | §4.6 |
| GitHub repo loss / compromise | T1 | hours | Last commit state preserved in cluster | §4.7 |
| Cloudflare account compromise | T1 | hours | DNS hijack window | §4.8 |
| Authentik database loss | T1 | hours | SSO sessions only | §4.9 |
| UniFi controller config loss | T0/T1 | min-hours | Network rules until restored | §4.10 |

**Tier semantics:**
- **T0** — cluster self-heals or one-command recovery.
- **T1** — manual procedure, all prereqs already in place.
- **T2** — full rebuild, depends on offsite backup.
- **T3** — irrecoverable without specific stored material (age key, NAS backup).

---

## 3) Blueprints

**N/A** — disaster recovery is a procedural runbook, not a declarative
configuration. Recovery steps reference declarative sources of truth that
live in other manifests (Talos `kubernetes/bootstrap/talos/clusterconfig/`,
Authentik blueprint configmap, Cloudflare Terraform), but the recovery
*procedure* itself has no blueprint artifact to maintain.

If a future scenario needs a declarative recovery aid (e.g., a saved Velero
backup CR, a pre-rendered Talos image), add it here.

---

## Critical prerequisites — verify these are valid BEFORE you need them

Most recovery procedures depend on these being current. Audit them quarterly.

| Item | Where | Failure mode if missing |
|---|---|---|
| SOPS age key (`age.key`, public id `age1nw624...`) | Offline + offsite (e.g., 1Password / Bitwarden / hardware backup) | Cannot decrypt any `*.sops.yaml`; every cluster secret must rotate (§4.4) |
| Talos `talosconfig` (auth to Talos API) | `kubernetes/bootstrap/talos/clusterconfig/` (git) | Cannot `talosctl` against nodes — but git has it |
| Cluster kubeconfig | Generated from talosconfig; not committed | Regenerate via `talosctl kubeconfig` |
| Longhorn CIFS backup target connectivity | `UNAS-CBERG/backups/longhorn` | No backups created or restored |
| NAS offsite backup | Owner-managed (external) | NAS loss = catastrophic for media; cluster data still on Longhorn replicas |
| UniFi controller backup file (`.unf`) | UniFi controller UI → Settings → System → Backup; auto-saved to NAS | Network rules rebuild from `CLAUDE.md` topology spec |
| Cloudflare account 2FA recovery codes | Offsite | Account takeover risk; see AR-020 |
| GitHub account 2FA + SSH key backups | Offsite | Cannot push fixes mid-incident |

---

## 4) Operational Instructions

### 4.1 Single node loss (1-of-3)

**Detection:**
```bash
kubectl get nodes
# One node shows NotReady, age > 5min
```

**Blast radius:**
- etcd still has quorum (2/3). Control plane operational.
- Pods on the dead node enter `Unknown` then re-schedule to surviving nodes.
- Longhorn volumes: any replica on the dead node enters `Stale`. Volumes with
  remaining live replicas stay attached and writable; new writes replicate to
  the remaining replicas. Volumes whose only live replica was on the dead node
  go `Faulted` — restore from backup (§4.5).

**Recovery:**
1. Identify what failed: hardware (NUC dead), Talos OS (`talosctl health`), or
   network (`unifictl local device get <mac>`).
2. Hardware swap if needed (PiKVM gives remote console + power; talos ISO via
   virtual media).
3. Re-provision Talos:
   ```bash
   mise exec -- talhelper genconfig
   mise exec -- talosctl apply-config --insecure -n <new-node-ip> \
     --file kubernetes/bootstrap/talos/clusterconfig/k8s-nuc14-XX.yaml
   mise exec -- talosctl bootstrap -n <new-node-ip>      # only if rebuilding control plane
   ```
4. Wait for node to join (`kubectl get nodes` → `Ready`). Cilium + Longhorn DS
   pods start automatically.
5. Longhorn replica rebuild: trigger from the Longhorn UI (Volume → Replicas →
   "Rebuild" on the failed replica), or let auto-rebalance handle it. Wait for
   `replicasReady = replicasDesired` on every volume.

**Verification:**
- `kubectl get nodes` → 3/3 Ready.
- `kubectl get volumes -n storage -o wide` → no `Faulted`, no `Degraded`.
- Re-run `runbooks/health-check.py` → no node-hardware errors, no Longhorn
  replica mismatches.

### 4.2 Two or three node loss (majority gone)

**Detection:**
- `kubectl` calls hang or return `etcdserver: request timed out`.
- Pods become unreachable, ingress 502s.

**Blast radius:**
- etcd has lost quorum. Control plane is read-only at best, dead at worst.
- Application pods on the surviving node keep running (kubelet-cached) but
  cannot be rescheduled or restarted.
- Longhorn: replicas with no live copy on a surviving node are unreachable.

**Recovery — option A: rebuild quorum if 1 node survives**
1. Reprovision the dead nodes per §4.1.
2. If etcd cannot recover automatically (rare), follow Talos's [etcd recovery
   procedure](https://www.talos.dev/v1.13/advanced/disaster-recovery/) using
   the surviving node as the seed.

**Recovery — option B: full rebuild (all 3 down or unrecoverable)**

Proceed to §4.3.

### 4.3 Full cluster rebuild (new hardware or unrecoverable cluster)

**Prereqs:** SOPS age key, GitHub repo accessible, CIFS NAS reachable, at
least 1 node of hardware.

**Steps:**

1. **Provision Talos on each NUC:**
   ```bash
   # Mount the Talos installer ISO via PiKVM (or USB)
   # IP each node into the k8s-network VLAN (192.168.55.0/24)
   mise exec -- talhelper genconfig
   mise exec -- talosctl apply-config --insecure -n <node-ip-1> \
     --file kubernetes/bootstrap/talos/clusterconfig/k8s-nuc14-01.yaml
   # repeat for nuc14-02 and nuc14-03
   mise exec -- talosctl bootstrap -n <nuc-01-ip>
   ```

2. **Get kubeconfig:**
   ```bash
   mise exec -- talosctl kubeconfig
   kubectl get nodes      # all 3 Ready
   ```

3. **Bootstrap SOPS age secret into the cluster:**
   ```bash
   kubectl create namespace flux-system
   kubectl create secret generic sops-age -n flux-system \
     --from-file=age.agekey=age.key
   ```
   Without this, Flux can decrypt nothing.

4. **Apply Cilium and Flux bootstrap:**
   The `kubernetes/bootstrap/` tree contains the minimum Cilium + Flux install.
   Follow the upstream [onedr0p/cluster-template bootstrap
   docs](https://github.com/onedr0p/cluster-template) — they're more current
   than this SOP can stay.

5. **Let Flux reconcile everything:**
   ```bash
   mise exec -- flux get kustomizations -A     # 100+ KS will appear
   mise exec -- flux get helmreleases -A       # 90+ HR will reconcile
   ```
   Wait 15–45 min for first-time reconcile. Watch `flux logs -A --tail=50`
   for errors.

6. **Restore Longhorn volumes from CIFS backup:**
   Per `docs/sops/backup.md` "Restore" procedure. The CIFS backup target
   contains the most recent daily-3am snapshot of every PV.

7. **Recreate ad-hoc secrets that are NOT in git:**
   Anything stored only in cluster Secrets (without an encrypted source in
   git) is lost. Audit with:
   ```bash
   kubectl get secrets -A -o json \
     | jq -r '.items[] | select(.metadata.ownerReferences == null and .type == "Opaque")
              | "\(.metadata.namespace)/\(.metadata.name)"'
   ```

**Verification:**
- All Flux Kustomizations + HelmReleases `READY=True`.
- `runbooks/health-check.py` reports 0 critical, 0 major.
- A user-facing service (Homepage, Authentik, Plex) loads via its external
  ingress (DNS + Cloudflare Tunnel + ingress-nginx working).

### 4.4 SOPS age key loss

**Catastrophic.** Without `age.key`, no `*.sops.yaml` file in the repo can be
decrypted. Every cluster secret must be regenerated.

**Recovery:**

1. Restore the key from offsite (1Password / Bitwarden / hardware backup).
2. If truly lost: rotate every secret end-to-end.
   - Generate a new age keypair: `age-keygen -o age.key`.
   - Update `.sops.yaml` with the new public key.
   - For each encrypted file under `kubernetes/**/*.sops.yaml`:
     a. Decrypt with the OLD key (you can't if it's truly gone — at that point
        delete the file and reconstruct from app docs).
     b. Re-encrypt with the new key: `sops -e -i <file>`.
3. Rotate the actual credential values for everything:
   - Cloudflare API token, Tunnel ID
   - All database passwords (postgres, mariadb, etc.)
   - Authentik admin password + OAuth client secrets
   - Wazuh agent + indexer + dashboard passwords
   - SMTP, OIDC, every API key

**Prevention is the only real defense.** Back up `age.key` to at least two
locations, one offsite. The public key (`age1nw624...`) lives in `.sops.yaml`
and is fine to commit.

### 4.5 Longhorn volume corruption

**Detection:**
- Pod stuck in `CreateContainerError` mounting a PVC.
- `kubectl get volumes -n storage` shows `state: faulted` or
  `state: degraded`.

**Recovery (degraded, one replica intact):**

Longhorn auto-rebuilds. Wait. If stuck:
```bash
kubectl annotate volume <name> -n storage \
  longhorn.io/replica-soft-anti-affinity=false --overwrite
```

**Recovery (faulted, all replicas lost):**

1. Identify the latest backup:
   ```bash
   kubectl get volumes -n storage <name> \
     -o jsonpath='{.status.lastBackupAt}'
   ```
2. Restore from backup per `docs/sops/backup.md` §Restore.
3. Rebind the PV/PVC if names changed.

**Data loss:** between the last backup (daily 03:00) and the failure.

### 4.6 NAS (UNAS-CBERG) failure

**Detection:**
- Pods with CIFS mounts: `MountVolume.SetUp failed` events.
- Apps with NAS-backed data (Plex, Jellyfin, JDownloader, Frigate, Tube
  Archivist, Paperless, Nextcloud, iCloud-docker) go to error state.
- Longhorn backups stop (no recent `lastBackupAt`).

**Blast radius:**
- **Lost (CIFS-only)**: media libraries, JDownloader intake, Frigate recordings,
  Tube Archivist downloads, Paperless consume/export buckets, iCloud sync,
  Nextcloud data, Longhorn backup target.
- **Survives (Longhorn replicas on K8s nodes)**: all PV data — databases,
  Home Assistant, application configs, etc. The cluster keeps running for
  everything that doesn't read/write the NAS.

**Recovery — option A: NAS hardware OK, just a config/share rebuild**
1. Rebuild SMB shares with the same paths.
2. Restore each share from offsite backup.
3. Restart pods that mount CIFS:
   ```bash
   kubectl rollout restart deployment -n <ns> <app>
   ```

**Recovery — option B: total NAS replacement**
1. Provision new NAS (same hostname/IP `UNAS-CBERG` @ `192.168.31.230` if
   possible — saves manifest changes).
2. Restore shares from offsite backup of the NAS itself (owner-managed).
3. Point CIFS PVs back at the new NAS. If hostname/IP changed, search/replace
   the StorageClass + PV manifests under `kubernetes/apps/kube-system/csi-driver-smb/`.

**Verification:**
- `kubectl get events -A --field-selector type=Warning` → no CIFS mount
  failures.
- Plex / Jellyfin libraries scan and show expected counts.
- `kubectl get cronjob backup-of-all-volumes -n storage` → next run succeeds.

### 4.7 GitHub repo loss / compromise

**The cluster keeps running** — Flux reconciles from the last fetched commit,
which is cached in `source-controller`. New changes can't deploy, but nothing
breaks until you reboot or roll a pod that requires a re-pull.

**Recovery — repo lost (deleted, account locked out):**
1. Push the local clone to a new origin (`git remote set-url origin ...`).
2. Update the Flux `GitRepository` URL:
   ```bash
   kubectl edit gitrepository flux-system -n flux-system
   # change spec.url to the new origin
   ```
3. Force reconcile: `flux reconcile source git flux-system -n flux-system`.

**Recovery — repo compromised (malicious commit pushed):**
1. Identify the bad commit: `git log --since=24h --all`.
2. Revert via PR (don't force-push — Flux watches commits).
3. SOPS-encrypted secrets are still encrypted; rotate any value that appears
   in plaintext in the bad commit.
4. Audit the 30 days of commits prior — supply-chain attack patterns
   (timing, image tag pin changes, decoder regex weakening).

### 4.8 Cloudflare account compromise

See AR-020 in `docs/security-accepted-risks.md`. Risk is documented; recovery:

1. Reset Cloudflare account password + revoke all sessions (Cloudflare
   dashboard → My Profile → Sessions).
2. Rotate the Cloudflare API token used by `cloudflared` + `external-dns` (in
   `kubernetes/apps/network/external/*/secret.sops.yaml`).
3. Regenerate the Tunnel credentials:
   ```bash
   # On the Cloudflare dashboard: Zero Trust → Networks → Tunnels →
   # delete + recreate the tunnel; copy the new credential JSON
   sops -d kubernetes/apps/network/external/cloudflared/credentials.sops.yaml
   # replace cred, re-encrypt
   ```
4. Audit DNS records: every `*.${SECRET_DOMAIN}` CNAME should point at
   `<tunnel-id>.cfargotunnel.com`. Anything else is hijacked.
5. Verify zone settings via Terraform (`terraform/cloudflare/tf plan`).

### 4.9 Authentik database loss

**Detection:** Every forward-auth-protected app returns 502/auth-loop;
Wazuh dashboard SAML SSO fails.

**Recovery — Postgres PV intact:**

```bash
kubectl rollout restart sts -n kube-system authentik-postgresql
# wait for Ready, then:
kubectl rollout restart deploy -n kube-system authentik-server
```

**Recovery — Postgres PV lost (corruption, ransomware):**

1. Restore the `authentik-postgresql` PV from Longhorn backup (§4.5).
2. If unrecoverable, accept the SSO outage and rebuild:
   - Fresh Authentik install (Flux already deploys it).
   - Apply blueprints from `kubernetes/apps/kube-system/authentik/app/configmap.sops.yaml`.
   - **All user sessions are lost.** Users re-log in. OAuth client secrets
     stay the same (they're in the blueprint). No external apps need updates.

Full workflow: `docs/sops/authentik.md`.

### 4.10 UniFi controller config loss

**Detection:**
- VLAN routing broken (inter-VLAN traffic blocked).
- WiFi SSIDs missing.
- `unifictl local device list` shows devices but no config.

**Recovery — auto-backup exists:**
- UniFi controller auto-saves `.unf` files to `Settings → System → Backups`.
  Restore the most recent.
- If the controller has `Backup to NAS` enabled, the file is also on
  `UNAS-CBERG/unifi-backups/`.

**Recovery — no backup, full rebuild:**
- Rebuild VLAN/firewall/wifi config from the topology spec in `CLAUDE.md`
  "Network Architecture" section. That file is the source of truth for:
  - VLAN IDs + subnets (Trusted 1/192.168.30.0, Servers 10/192.168.31.0,
    Trusted-Devices 20, IoT 30, Guests 40, k8s-network 55, USA-Peer 2)
  - WiFi SSIDs and VLAN bindings
  - mDNS proxy scope
  - DHCP ranges
- AdGuard DHCP DNS option must point at `192.168.55.5` for all internal VLANs.

---

## 5) Examples

### Example: Recover a single failed PV from backup

```bash
# Identify the latest backup
kubectl get volumes -n storage <volume-name> \
  -o jsonpath='{.status.lastBackupAt}'

# Trigger restore (Longhorn UI: Volume → Restore Latest Backup → New volume name)
# Or via CRD:
cat <<EOF | kubectl apply -f -
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: <new-volume-name>
  namespace: storage
spec:
  fromBackup: "s3://backups@/<volume-name>?backup=<backup-id>"
  numberOfReplicas: 2
  size: "<size-bytes>"
EOF

# Re-bind PV/PVC (see docs/sops/longhorn.md "longhorn-static")
```

### Example: Verify SOPS age key still works

```bash
sops -d kubernetes/apps/network/external/cloudflared/credentials.sops.yaml >/dev/null \
  && echo "✅ age key valid" || echo "❌ age key broken or missing"
```

### Example: Confirm Flux source-controller cache survives repo loss

```bash
kubectl get gitrepository flux-system -n flux-system \
  -o jsonpath='{.status.artifact.revision}'
# Returns the last successfully fetched commit. Cluster runs on this even
# if the GitHub remote is deleted.
```

---

## 6) Verification Tests

| After recovering from | Run this | Expected |
|---|---|---|
| Any scenario | `runbooks/health-check.py` | 0 critical, 0 failed |
| §4.3 (full rebuild) | `flux get kustomizations -A \| awk '$5 != "True"'` | only header line |
| §4.4 (SOPS rotation) | `sops -d <any .sops.yaml>` | decrypts cleanly |
| §4.5 (volume restore) | `kubectl describe pvc -n <ns> <name>` | `Bound`, no errors |
| §4.6 (NAS) | Plex/Jellyfin scan | library counts match pre-failure |
| §4.7 (repo) | `flux reconcile source git flux-system -n flux-system` | succeeds |
| §4.8 (Cloudflare) | `curl -I https://<any-app>.${SECRET_DOMAIN}` | 200/302, not 502 |
| §4.9 (Authentik) | log into Homepage, Wazuh dashboard | SSO redirect succeeds |
| §4.10 (UniFi) | `unifictl local diagnose network` | no critical findings |

---

## 7) Troubleshooting

### "talosctl bootstrap" hangs after node provision

Bootstrap can only be run once per cluster, on a control-plane node. If you
ran it during partial recovery and the cluster already exists, it returns an
error but is otherwise harmless. Use `talosctl etcd members -n <node>` to
inspect actual quorum state.

### Flux reconciles forever after rebuild

Check `flux events -A --tail=50`. Common causes:
- SOPS secret missing in `flux-system` namespace (re-create per §4.3 step 3).
- HelmRepository auth failing (rotate the relevant secret).
- An immutable field changed (StatefulSet `selector`, PV `storageClassName`).
  Delete the offending resource by hand; Flux will recreate.

### Longhorn replica rebuild stuck

```bash
# Check engine + replica status
kubectl get engine -n storage
kubectl get replica -n storage

# If a replica is stuck "Stale", delete it; Longhorn schedules a new one
kubectl delete replica -n storage <name>
```

---

## 8) Diagnose Examples

### Cluster-wide failure triage (5-minute snapshot)

```bash
kubectl get nodes -o wide
mise exec -- flux get kustomizations -A | awk '$5 != "True"'
mise exec -- flux get helmreleases -A | awk '$5 != "True"'
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -20
kubectl get volume -n storage -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUSTNESS:.status.robustness --no-headers | grep -v 'attached.*healthy'
```

### Determine if cluster is in a "Flux-frozen" survivable state

Cluster keeps serving traffic even with Flux paused or GitHub unreachable.
Quick check:

```bash
kubectl get pods -A --field-selector status.phase=Running | wc -l
# Should be in the 200+ range for this homelab; sudden drop = bigger problem
```

---

## 9) Health Check

Recovery is complete when:
- `runbooks/health-check.py` reports `EXCELLENT` (0 critical, 0 major).
- AlertManager firing set is back to `Watchdog` (+ `InfoInhibitor`) only.
- Section 13 of `runbooks/security-check.py` shows wazuh agents 3/3 reporting.
- All user-facing services reachable via external ingress (`*.${SECRET_DOMAIN}`).

---

## 10) Security Check

After §4.4 (key rotation), §4.7 (repo compromise), or §4.8 (Cloudflare):

1. Re-run `runbooks/security-check.py` end-to-end. Confirm no critical
   findings.
2. Audit `docs/security-accepted-risks.md` — any AR-* that referenced a
   rotated credential needs a date-stamp update.
3. Trivy: re-scan running images for any introduced via emergency restore.

---

## 11) Rollback Plan

Disaster recovery is itself the rollback. If a recovery procedure makes
things worse (e.g., a restored backup is also corrupted), you have two
escape hatches:

- **Step back one snapshot generation**: Longhorn retains a configurable
  number of snapshots in addition to backups. Restore the previous one.
- **Step back one cluster generation**: every git commit is a cluster
  snapshot. `git revert` and `flux reconcile` returns to a known-good state.

The only irreversible disaster is loss of the SOPS age key with no copy.
Treat it accordingly.

---

## Related SOPs

- `docs/sops/backup.md` — the preventive side; backup scheduling, validation,
  restore mechanics.
- `docs/sops/storage-safety.md` — pre-flight checks before any destructive
  CIFS/SMB/NFS PVC delete (the 2026-04-26 wipe incident).
- `docs/sops/longhorn.md` — class selection + volume sizing.
- `docs/sops/authentik.md` — IdP blueprints (referenced in §4.9).
- `docs/sops/cloudflare.md` — Cloudflare zone Terraform (referenced in §4.8).
- `docs/sops/talos-upgrade.md` — node-level upgrade procedure (related to §4.1
  hardware swap).
- `docs/security-accepted-risks.md` — risk register (AR-020 Cloudflare,
  AR-023 Wazuh, AR-026 Falco).
- `CLAUDE.md` — network topology + VLAN map (referenced in §4.10).
