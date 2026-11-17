# SOP: Total-Loss Recovery (house, cluster, NAS and Mac mini all gone)

> Description: Numbered, ordered rebuild of the whole homelab from the off-site
> restic repository (hosted storage box) plus the offline-held secrets, after
> losing the cluster nodes, the NAS and the Mac mini at once. Complements
> `docs/sops/disaster-recovery.md` (single-failure scenarios) and
> `docs/sops/backup.md` (how the copies are made).
> Version: `2026.11.17`
> Last Updated: `2026-11-17`
> Owner: `Platform (operator)`

---

## 0) Break-glass page (print this section)

If you read nothing else:

1. **The only things that cannot be rebuilt are held outside the house**:
   the SOPS age key (external password manager) and the storage-box account.
   With the age key you can decrypt every `*.sops.yaml` in the GitHub repo,
   including the three Secrets that hold the storage-box host, user, SSH keys
   and the two restic repository passwords
   (`kubernetes/apps/backup/offsite-backup/secrets/`).
2. Get a laptop with `git`, `mise`, `restic >= 0.17` and `ssh`. Clone the repo
   (public, HTTPS). Put the age key at the repo root as `age.key`.
3. Recover the restic credentials from SOPS (section 4.1), restore the tier
   `core` paths in the order of section 4.2 onto a NEW NAS, THEN rebuild Talos
   (section 5), Flux (section 6) and restore Longhorn volumes BEFORE the apps
   start (section 7).
4. Databases: prefer the Longhorn volume; fall back to the nightly logical dump
   (section 8).
5. Order of household value: DNS and network, Home Assistant, Authentik,
   password vault, Nextcloud, Paperless (section 9).
6. If the age key itself is not recoverable: stop, go to
   `docs/sops/disaster-recovery.md` section 4.4 (rotate everything), and note
   that the restic passwords are then unreadable unless they are ALSO in the
   password manager (section 3.1, rows 2 and 3, UNVERIFIED).

Dependency graph (arrow = "needs"):

```
age key (offline) ──► clone repo ──► decrypt SOPS ──► storage-box creds + restic passwords
                                                              │
                          new NAS + shares (sec. 4.3) ◄───────┤
                                    │                         ▼
                                    │            restic restore, tier core (sec. 4.2)
                                    │             backupstore, db-dumps, unifi, ...
                                    ▼                         │
 hardware ► Talos (sec. 5) ► Cilium/Flux (sec. 6) ► Longhorn Ready ──► volume restore (sec. 7)
                                                              │
                                              release cluster-apps ► apps (sec. 9)
                                                              │
                  UniFi controller restore (sec. 11)  ◄── independent of the cluster,
                  but needed for VLAN 55 / DHCP / WiFi before nodes can have addresses
```

Network first: nodes live on VLAN 55 and need the UniFi gateway configured
(section 11) before anything else can talk. Restic restore needs only the
internet and a laptop, so it runs in parallel with the hardware work.

---

## 1) Description

Scenario "total loss": every node, the NAS (including the Longhorn backup
store), the Mac mini and the gateway disk are unusable (fire, theft, flood).
What survives by design: GitHub (repo), the hosted storage box (restic repos
`core` and `apps`), and secrets held outside the house.

This SOP is an order-of-operations runbook. Per-engine and per-tool details are
linked, not repeated.

Scope: cluster, NAS, UniFi gateway, Mac mini. Out of scope: rebuilding the
operator's client devices (section 12.2 lists the open gap).

## 2) Overview

| Layer | Source of truth for the rebuild | Where |
|---|---|---|
| Desired cluster state | GitHub repo (also monthly bare mirror in tier `core`) | sec. 4.1 |
| Secrets | SOPS files in the repo + age key (offline) | sec. 3.1 |
| Talos machine config | `talconfig.yaml` + `schematic.yaml` + SOPS `talsecret` | sec. 5 |
| NAS data (app data shares, curated media) | restic tier `core` / `apps` | sec. 4 |
| PV data (all Longhorn volumes) | Longhorn backupstore, restored from restic `core` | sec. 7 |
| Databases | Longhorn volumes, fallback nightly dumps (in `core`) | sec. 8 |
| UniFi network config | newest `.unf` in `core` | sec. 11 |
| Bulk media, derived photo cache, transcode scratch | NOT backed up | sec. 14 |

### Realistic recovery time objective (RTO)

Derived from measured numbers; everything else is labelled as an assumption.

Measured:

- Core tier at the 2026-11-16 snapshot: 1.27 TiB (about 1.39 TB), made of
  Longhorn backupstore 510 GiB, phone-cloud backups 335 GiB, one laptop backup
  directory 220 GiB, other backup folders 164 GiB, Nextcloud data 45 GiB, and
  small trees. The Time Machine sparsebundles (about 1.9 TiB, added 2026-11-16)
  are uploaded after that snapshot and were still in their first upload when
  this SOP was written, so the final core size is about 3.3 TB.
- First-night core upload: 859 GB added in about 8 h at a 40 MB/s cap
  (approx. 30 MB/s achieved).
- Restore drill 2026-11-16: restic read speed was only ever measured at the
  25 MB/s drill cap (705 packs in 8 min 37 s). **Uncapped download throughput
  from the storage box has NOT been measured.**
- Longhorn volume restore: about 40 MB/s sustained, 2 to 3 h for the 271 GiB of
  newest backups (`docs/sops/longhorn.md` "Total-loss Longhorn restore").
- Flux first-time reconcile: 15 to 45 min (`docs/sops/disaster-recovery.md`
  section 4.3, an estimate, not a timed rebuild).

Computed download times (data / throughput; the throughput row is the unknown):

| Data set | 25 MB/s | 40 MB/s | 100 MB/s |
|---|---|---|---|
| Priority set: backupstore + db-dumps + unifi + github-mirror + k8s (about 0.6 TB) | 6.7 h | 4.2 h | 1.7 h |
| Whole core as of 2026-11-16 snapshot (1.39 TB) | 15.5 h | 9.7 h | 3.9 h |
| Whole core including Time Machine images (about 3.3 TB) | 36 h | 23 h | 9 h |

Critical path (serial): priority restore, then Longhorn restore (2 to 3 h),
then app start and verification. Talos and Flux (about 1 to 2 h, an assumption,
never timed end to end) run in parallel with the restore.

**Estimate: household core services (network, Home Assistant, Authentik,
Nextcloud, Paperless) are back 6 to 10 h after replacement hardware and a NAS
are in place and powered, if the box delivers 100 MB/s; 12 to 16 h at
25 MB/s. Everything incl. Time Machine images: 1 to 2 more days. The hardware
lead time (NUCs, NAS, gateway) is NOT included and is the dominant unknown.**
Assumptions: age key and storage-box account are reachable on day 0; a
replacement UniFi gateway and switch exist; replacement NAS has at least 5 TB
usable; the internet line is not the limit.

## 3) Blueprints

N/A as declarative config: this is a procedural runbook. The declarative sources it
rebuilds from are `kubernetes/bootstrap/talos/talconfig.yaml`,
`kubernetes/bootstrap/talos/schematic.yaml`, `kubernetes/bootstrap/apps/helmfile.yaml`
and `kubernetes/flux/`.

### 3.1 Credentials and attestation inventory (BEFORE the disaster)

No values here, ever. "Attested" means the repo or a dated operator statement
proves it; everything else must be confirmed by the operator and written back
into this table with a date.

| # | Item | Why needed | Where the offline copy is held | Attestation |
|---|---|---|---|---|
| 1 | SOPS age private key | Decrypts every `*.sops.yaml`, including the storage-box credentials | Operator's external hosted password manager; a second real copy sits on the Mac mini (and dies with it) | Vault copy: operator-attested 2026-09-14 (not cluster-verifiable). The local key decrypts current files (checked 2026-11-17). **Vault copy still decrypts: UNVERIFIED - operator to confirm at the quarterly drill** |
| 2 | Storage-box host, port, account, host-key line, SSH keys (append-only `core`, append-only `apps`, admin) | Reach the restic repos | In SOPS (`offsite-backup-write`, `offsite-backup-prune`) in git, so only the age key is needed. `docs/sops/backup.md` says they MUST also be in the password manager | In git: attested (Secret key names checked 2026-11-17). Password-manager copy: **UNVERIFIED - operator to confirm** |
| 3 | restic repository passwords (`core`, `apps`) | Without them the off-site data is unreadable ciphertext | Same as row 2 (SOPS in git) | In git: attested (keys exist). Independent copy outside SOPS: **UNVERIFIED - operator to confirm** (if the age key is lost and no independent copy exists, the off-site data is lost too) |
| 4 | Storage-box provider account login and 2FA recovery, cloud API token | Re-provision a box, rotate keys, provider-side snapshots | API token in SOPS (`hetzner-credentials`); account login/2FA: **UNVERIFIED - operator to confirm** | Token: in git. Account recovery: UNVERIFIED |
| 5 | restic REST/rclone config | None needed on a client: the box runs `rclone serve restic --stdio` as a forced SSH command, the client only needs `ssh` and restic | N/A (no rclone.conf exists) | Attested by `kubernetes/apps/backup/offsite-backup/app/script.sh` |
| 6 | Talos secrets (`talsecret`, `talenv`) | Same cluster PKI and node join | `kubernetes/bootstrap/talos/talsecret.sops.yaml`, `talenv.sops.yaml` in git | Attested: `talhelper genconfig` from these reproduced all three node configs byte-identical to the running ones and an identical Talos CA (2026-11-17) |
| 7 | `talosconfig`, `kubeconfig` | Client auth to nodes and API | NOT in git (gitignored). Regenerated: `talosconfig` by `talhelper genconfig`, kubeconfig by `talosctl kubeconfig` | Attested (2026-11-17, genconfig into a scratch dir) |
| 8 | GitHub account login, 2FA recovery codes, SSH key | Clone/push the repo; re-issue tokens | Disaster-recovery table says "Offsite". The repo is public over HTTPS, so cloning needs no login | **UNVERIFIED - operator to confirm** |
| 9 | GitHub PATs: Flux pull (`flux-system-git-auth`), mirror token, CI | Flux writes (image automation); monthly mirror | SOPS in git. The mirror token is a fine-grained PAT with an expiry | In git. Expiry date: UNVERIFIED |
| 10 | Domain registrar and Cloudflare account login, 2FA recovery | DNS, tunnel, certificates | "Offsite" per disaster-recovery table (AR-020) | **UNVERIFIED - operator to confirm** |
| 11 | Cloudflare tunnel credentials and API token | External reachability | SOPS in git | In git (attested) |
| 12 | Terraform state: Cloudflare zone | `./tf plan` without re-import | Lives only in a cluster Secret (`flux-system`), **no off-site copy found** | Gap: after a rebuild run `terraform import` or accept re-import (section 10) |
| 13 | Terraform state: storage box | Manage the box | Encrypted copy in `offsite-backup-tfstate-copy` (SOPS, not applied by Flux) | Attested; refresh after every apply is a manual note in the Secret |
| 14 | UniFi: gateway admin, Ubiquiti SSO account, local `cli-adm` | Restore `.unf`, re-adopt | Gateway/SSO: **UNVERIFIED - operator to confirm**. `unifictl` login lives in the Mac mini's gitignored `.unifictl.yaml` (lost with it) | UNVERIFIED |
| 15 | NAS admin login and SMB user for the cluster | New NAS must expose the same shares to the same user | SMB credentials for the cluster in SOPS (`csi-driver-smb`, `longhorn-backup-credentials`); NAS admin login: **UNVERIFIED** | Partly in git |
| 16 | Authentik bootstrap | Application SSO | Blueprints and `SECRET_AUTHENTIK_SECRET_KEY` in SOPS; users/groups live in the database (restored in sections 7 and 8). A recovery flow exists (`docs/sops/authentik.md`) | In git |
| 17 | Apple ID passwords + 2FA devices for the two iCloud instances | Re-create `icloud-docker-*` sessions if the `*-session` volumes are lost | Held by the account owners. **UNVERIFIED - operator to confirm** | UNVERIFIED |
| 18 | Password manager itself (master secret, emergency kit, 2FA) | Holds rows 1, 3, 4, 8, 10, 14, 17 | **UNVERIFIED - operator to confirm that an emergency kit exists outside the house** | UNVERIFIED |
| 19 | Mac-mini-only secrets: Claude Code login, bank-refresh credentials, ARAG scraper token/emulator state, Ollama host config | Ops console and the Mac-side apps | Not in git; see section 12 | UNVERIFIED |

Row 1 and row 3 are the two single points of failure. A 5-minute test belongs
in every quarterly drill: from a clean shell with only the password manager
(not the Mac mini), fetch the age key and decrypt
`kubernetes/apps/backup/offsite-backup/secrets/secret-write.sops.yaml`, and
check that the printed key names (names only, never values) match section 4.1.

## 4) Operational Instructions

Steps run in section order 4 to 13. Section numbers in the break-glass page
refer to these sections.

### 4.1 Recover the vault and clone the repo (steps 1 to 3)

1. Install tools on any machine: `git`, `mise`, `ssh`, `restic >= 0.17` (the
   cluster jobs run restic 0.19.1). **`restic` is not pinned in `.mise.toml`**:
   install it by package manager and note the version.
2. Clone: `git clone https://github.com/<owner>/<repo>.git cberg-home-nextgen`
   and `cd` into it, then `mise install` and `mise exec -- task install-hooks`.
   If GitHub is unavailable, take the monthly bare mirror from the restic
   restore of `/src/1/github-mirror` (section 4.2) and push it to a new remote
   (`docs/sops/backup.md` "GitHub Mirror" Restore). Note the mirror carries
   issues and pull requests as JSON only.
3. Put the age key at `./age.key` (mode 600). Proof: `mise exec -- sops -d
   kubernetes/flux/components/common/sops-age.sops.yaml >/dev/null && echo OK`.
4. Materialise the restic access files into a private temp dir without printing
   anything (key names in `secret-write`: `KNOWN_HOSTS`, `SFTP_HOST`,
   `SFTP_PORT`, `SFTP_USER`, `SSH_KEY`, `SSH_KEY_APPS`, `RESTIC_PASSWORD_CORE`,
   `RESTIC_PASSWORD_APPS`):

```bash
cd cberg-home-nextgen && umask 077 && export R=$(mktemp -d)
mise exec -- sops -d kubernetes/apps/backup/offsite-backup/secrets/secret-write.sops.yaml \
  | python3 -c '
import sys, yaml, os
d = yaml.safe_load(sys.stdin)["stringData"]; r = os.environ["R"]
for k in ("KNOWN_HOSTS", "SSH_KEY", "SSH_KEY_APPS"):
    open(f"{r}/{k}", "w").write(d[k] if d[k].endswith("\n") else d[k] + "\n")
    os.chmod(f"{r}/{k}", 0o600)
open(f"{r}/env", "w").write("".join(f"{k}={d[k]}\n" for k in ("SFTP_HOST", "SFTP_PORT", "SFTP_USER", "RESTIC_PASSWORD_CORE", "RESTIC_PASSWORD_APPS")))
'
set -a; . "$R/env"; set +a
# Same program string the cluster jobs use (script.sh); the append-only key's
# forced command fixes the repository directory, so the repo is just "rclone:".
rr() {  # usage: rr <core|apps> <restic args...>
  t=$1; shift
  case $t in core) K=SSH_KEY; export RESTIC_PASSWORD=$RESTIC_PASSWORD_CORE;;
             apps) K=SSH_KEY_APPS; export RESTIC_PASSWORD=$RESTIC_PASSWORD_APPS;; esac
  restic -o rclone.program="ssh -F /dev/null -p $SFTP_PORT -i $R/$K -o IdentitiesOnly=yes -o UserKnownHostsFile=$R/KNOWN_HOSTS -o StrictHostKeyChecking=yes -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=10 $SFTP_USER@$SFTP_HOST" \
    -r rclone: --no-lock "$@"
}
rr core snapshots --host offsite --tag core     # newest snapshot id/time; expect daily snapshots
```

The append-only keys can READ and restore; they cannot delete or prune. Do not
use the admin key (`offsite-backup-prune`) for a restore.
Delete `$R` when finished (`rm -rf "$R"`), do not put it on a synced folder.

Status of these commands: the Secret key names, the program string and the
`rclone:` repo form are taken from the running jobs (`script.sh`,
`contents.sh`) and were checked against the live Secrets on 2026-11-17 (key
names only). The wrapper above was NOT executed end to end in this session:
`restic` is not installed on the workstation that wrote this SOP and no
cluster Job was created (read-only rule). The first quarterly drill must run
it and correct this section.

### 4.2 Restic restore of tier core (step 4)

Snapshot paths are mount-relative. Mapping (from `offsite-backup-sources`, share
names are the ones already published in `docs/sops/storage-safety.md`):

| In snapshot | NAS share | Contents |
|---|---|---|
| `/src/1/...` | `backups` | `backupstore` (Longhorn), `db-dumps`, `unifi`, `github-mirror`, `icloud-backup`, other backup folders, laptop backup directory, Time Machine images |
| `/src/2` | `nextcloud` | Nextcloud data |
| `/src/3/...` | `paperless_ngx` | selected paperless trees (media, export) |
| `/src/6..9` | `media` subpaths | curated music, books, audiobooks, archive |

Confirmed 2026-11-17 via the weekly contents exporter (Prometheus series
`offsite_backup_path_bytes{tier="core"}`, no new Job created): the Longhorn
backup store is **`/src/1/backupstore`** (509.6 GiB in the 2026-11-16
snapshot), i.e. the `backupstore/` directory in the root of the `backups`
share, which is exactly where the Longhorn BackupTarget
(`cifs://<NAS>/backups`, `kubernetes/apps/storage/longhorn/app/backup-target.yaml`)
looks. The include list (`FILES_CORE`, in the encrypted sources Secret) also
carries `/src/1/db-dumps`, `/src/1/unifi`, `/src/1/github-mirror` and
`/src/1/icloud-backup` (checked 2026-11-17). Those four directories did not
yet appear in the 2026-11-16 contents view (they are newer than that
snapshot): confirm with `rr core ls latest:/src/1 --host offsite --tag core | head`
before relying on them.

Restore into the new NAS shares mounted on the restore workstation. The
`snapshot:subfolder` form strips the `/src/1` prefix so files land directly in
the share:

```bash
M=/mnt/nas-backups     # new NAS share "backups", mounted read-write (SMB)
# Priority 1: Longhorn backup store (largest, gates every volume restore)
rr core restore latest:/src/1 --host offsite --tag core --target "$M" --include /backupstore
# Priority 2: logical DB dumps, UniFi autobackups, GitHub mirror, k8s dir (small)
for p in db-dumps unifi github-mirror k8s; do
  rr core restore latest:/src/1 --host offsite --tag core --target "$M" --include /$p
done
# Priority 3: app-data shares (mount each new share the same way)
rr core restore latest:/src/2 --host offsite --tag core --target /mnt/nas-nextcloud   # share root of nextcloud
# Priority 4: phone-cloud backups, laptop and other backup folders, Time Machine images
rr core restore latest:/src/1 --host offsite --tag core --target "$M" --include /icloud-backup
# Priority 5 (last): tier apps
rr apps restore latest --host offsite --tag apps --target /mnt/apps-staging
```

Notes and gotchas:

- `latest:<subfolder>` with `--host`/`--tag` is restic's documented
  `snapshotID[:subfolder]` form; **not executed in this session** (no restic
  binary). If the form is rejected, restore to a staging directory and `rsync`.
  The priority 2 to 4 commands must be corrected during the first drill if
  restic complains. `/src/3` (paperless trees) is restored the
  same way with `--include /media` and `--include /export`.
- Restore is read-only against the box. Throughput uncapped is unmeasured
  (section 2); add `--limit-download <KiB/s>` only if the line is shared.
- Ownership: the sources were mounted with fixed uid/gid 1000 (`noperm`), so the
  data has no meaningful original owner; set ownership on the new NAS to the
  cluster's SMB user. The 2026-11-16 drill container needed `CHOWN FOWNER
  DAC_OVERRIDE FSETID` added back to restore at all (`docs/sops/backup.md`
  "Restore drill record"); on a workstation run the restore as root (or on the
  NAS) so `lchown` succeeds, otherwise restic exits non-zero even though the data
  is correct. Verify with a file count and a sha256 sample, not the exit code.
- A restore may be interrupted and re-run; restic skips files that already match.
- Time Machine images are crash-consistent only; attach, let macOS verify, fall
  back to an older snapshot (`rr core snapshots`) if it will not mount.

Expected sizes (2026-11-16 snapshot): `backupstore` 510 GiB, `icloud-backup`
335 GiB, laptop backup directory 220 GiB, other `backup` folders 164 GiB,
Nextcloud data 45 GiB, `k8s` 17 GiB, paperless trees about 3 GiB, rest small.
Measured 2026-11-16 drill: 327 files / 62 MiB restored in 12 s, sha256 327/327
equal (cap 25 MB/s, peak memory 509 MB).

### 4.3 New NAS and storage prerequisites (step 5)

Replacement NAS: same name and address if possible (`UNAS-CBERG`,
192.168.55.240 on VLAN 55, `docs/infrastructure.md`) so no manifest changes are
needed; otherwise change the `NAS_HOSTNAME` Flux variable in
`cluster-secrets.sops.yaml` and the PV sources. Reserve the physical-server
range .240 to .254 on VLAN 55; keep the Cilium LB pool free.

Shares and directories the cluster expects (derived from the StorageClass and
PV manifests in `kubernetes/apps/**` and `docs/sops/storage-safety.md`):

| Share | Directories used | Consumers |
|---|---|---|
| `backups` | `backupstore` (Longhorn), `db-dumps`, `unifi`, `github-mirror`, `icloud-backup/mu`, `icloud-backup/andrea`, others | Longhorn target, dump/mirror/unifi jobs, iCloud instances, Immich read-only |
| `nextcloud` | `data` | Nextcloud |
| `paperless_ngx` | `consume`, `export`, `inbox`, `log`, `media` | Paperless |
| `penpot` | `assets` | Penpot |
| `opencode` | `andrea-opencode` | OpenCode (apps tier) |
| `frigate` | `media` | Frigate recordings |
| `media` | `/` (Plex, Jellyfin), `downloads/jdownloader`, `downloads/tube-archivist`, `Transcode`, `immich-cache`, plus the four curated trees | Media apps |

Rules: one SMB user the cluster can authenticate as (credentials are in SOPS:
`csi-driver-smb`, `longhorn-backup-credentials`); SMB 3.1.1 with multichannel as
in the PV `mountOptions`; every CIFS StorageClass is `Retain`. Two classes use
subdir `/` on the media share (`cifs-jellyfin-media`, `cifs-plex-media`):
never delete those PVCs (`docs/sops/storage-safety.md`). The `media` share can
start empty: the bulk library is not backed up (section 14). Dynamic CIFS
classes create their subdirectories on first mount.

## 5) Talos rebuild (step 6)

What is in git (verified 2026-11-17):

- `kubernetes/bootstrap/talos/talconfig.yaml`: node names, VIP, disk serials,
  MACs, patches, and the installer `talosImageURL` (schematic ID
  `43b3cbfc...cb99a3`, extension set and kernel args below).
- `kubernetes/bootstrap/talos/schematic.yaml`: the schematic document itself
  (added 2026-11-17). Before that the ID existed only inside a commit message and
  the Image Factory's memory. **Proof**: POSTing this file to the factory
  returned exactly the ID in `talconfig.yaml` (the file with its comments also
  returns it). Extensions: i915, intel-ice-firmware, intel-npu, intel-ucode,
  iscsi-tools, mei, thunderbolt, util-linux-tools, v4l-uvc-drivers; 11 kernel
  args. These match `talosctl get extensions` and `/proc/cmdline` on the live
  nodes.
- `talsecret.sops.yaml`, `talenv.sops.yaml`: cluster PKI and tokens (SOPS).
- `clusterconfig/` (generated configs and `talosconfig`) is gitignored on
  purpose. **Correction of an earlier claim**: `docs/sops/disaster-recovery.md`
  said the `talosconfig` lives in git; it does not. It is regenerated:
  `task talos:generate-config` (`talhelper genconfig`) rebuilt the three node
  configs byte-identical and the same Talos CA on 2026-11-17 (run into a scratch
  `--out-dir`, repository untouched). `talhelper` still prints a "might not be
  compatible" warning for `v1.14.1`; it is cosmetic since the multi-document
  migration landed.

Procedure (hardware in place, nodes reachable on VLAN 55):

```bash
# 1. Boot each NUC from an Image Factory ISO built from schematic.yaml
#    (factory UI: paste schematic.yaml, platform metal, amd64, v1.14.1; or use the
#    installer image URL from talconfig). The ISO URL was NOT downloaded in this
#    session (the on-demand build timed out); the installer manifest for the
#    schematic and tag resolves (HTTP 200).
# 2. Generate configs (needs age.key) and bootstrap. This is the repo task:
mise exec -- task bootstrap:talos
#    = talhelper genconfig; gencommand apply --insecure (all 3 nodes);
#      talhelper gencommand bootstrap (retried); gencommand kubeconfig (retried)
#    Dry check that costs nothing: `cd kubernetes/bootstrap/talos &&
#    mise exec -- talhelper gencommand apply --extra-flags=--insecure` prints the
#    three apply-config commands (verified 2026-11-17).
mise exec -- kubectl get nodes        # 3 NotReady (no CNI yet) is expected
```

Cilium is disabled in the Talos config (`cniConfig: none`), so nodes stay
NotReady until step 6 installs Cilium. Existing single-node recovery steps:
`docs/sops/disaster-recovery.md` 4.1 to 4.3. Later machine-config changes follow
`docs/sops/talos-upgrade.md` (section 14: use the existing configs).

## 6) Cilium and Flux bootstrap (step 7)

```bash
mise exec -- task bootstrap:apps
```

`task bootstrap:apps` runs `kubernetes/bootstrap/apps/resources/prepare.sh`
(Prometheus CRDs, a namespace per `kubernetes/apps/*` directory, the
`cluster-settings` ConfigMap, then the SOPS secrets `cluster-secrets` and
`sops-age` from `kubernetes/flux/components/common/`) and then
`helmfile apply` with this fixed order: Cilium, CoreDNS, cert-manager,
flux-operator, flux-instance (`kubernetes/bootstrap/apps/helmfile.yaml`).
This creates the `sops-age` Secret from git, so the manual
`kubectl create secret ... --from-file=age.agekey` of the older DR text is
not needed. Needs `gum`, `jq`, `kubectl`, `kustomize`, `sops`, `yq`, `helmfile`
(all in `.mise.toml`). `prepare.sh` warns and continues if
`bootstrap/apps/resources/github-deploy-key.sops.yaml` is missing; that file does
not exist in the repo (Flux pulls the public repo anonymously, the writer secret
`flux-system-git-auth` is applied by Flux itself from SOPS).

Not exercised in this session (it mutates the cluster); only the task graph,
`prepare.sh` and `helmfile.yaml` were read.

Ordering once Flux runs (`kubernetes/flux/cluster/ks.yaml`): `cluster-meta`
(sources) then `cluster-apps` (everything in `kubernetes/apps`, with SOPS and
`cluster-secrets` substitution patched into every child). What stays Pending
until storage exists:

- Everything on a `longhorn` or `longhorn-static` PVC (static PVCs wait for their
  hand-applied Longhorn `Volume`; dynamic PVCs would create EMPTY volumes).
- Everything on a CIFS PVC until the NAS and its shares exist (sec. 4.3).
- The monitoring stack, databases, apps.

Therefore, as soon as `storage/longhorn` is Ready and BEFORE other apps
reconcile, `flux suspend kustomization cluster-apps -n flux-system`
(`docs/sops/longhorn.md`). If `cluster-apps` has already created dynamic empty
volumes, delete those PVCs/volumes by exact name before restoring (the
restore tool refuses to overwrite an existing volume).

## 7) Longhorn restore (step 8)

Follow `docs/sops/longhorn.md` "Total-loss Longhorn restore" verbatim. Summary
of the rule: **volumes before apps**; `runbooks/longhorn-bulk-restore.py` is
dry-run by default and recreates each volume under its ORIGINAL name from the
newest Completed backup; `--parallel 1`; critical state first
(`authentik-pg-data`, `postgresql-data-5g`, `mariadb-data-5g`, `vaultwarden-data`,
`home-assistant-config`, paperless volumes), then the rest; skip rebuildable
data (`prometheus-tsdb`, Elasticsearch data, caches, `*-redis*`); never skip
`*-session` volumes. Measured: about 2 h for 76 volumes (up to 3 h).
Longhorn `Volume` CRs for `longhorn-static` volumes are not owned by Flux; the
restore tool creates them with `--create-pv`.

Gate (from the Longhorn SOP): no volume that is not `healthy`, no PVC `Pending`
or `Lost`, then `flux resume kustomization cluster-apps -n flux-system`. Watch
`etcd_server_leader_changes_seen_total` during restores (etcd shares the NVMe
with Longhorn).

## 8) Databases (step 9)

Default: **the Longhorn volume restore already brings the databases back**
(`authentik-pg-data`, `postgresql-data-5g`, `mariadb-data-5g`, and the per-app
databases). It is the fastest path and keeps users, grants and extensions
exact. Prefer it.

Fall back to the nightly logical dump (`/src/1/db-dumps`, in `core`) when: the
database volume was lost or restored corrupt (a corrupted volume is backed up as
a corrupted volume), the volume backup is older than the dump, or the engine
version changed. Dumps cover 14 instances (Postgres 14/16/18 incl. pgvector and
vectorchord, MariaDB 11.8/13.0/13.1), one directory per instance and database,
with a `.sha256` sidecar; roles live in `_globals` / `_users`. Restore is always
into a scratch instance first, then repoint; commands and the 2026-11-17 restore
proof (Postgres and MariaDB, row counts identical) are in
`docs/sops/backup.md` "Database Dumps" -> "Restore".

Order for a real dump restore: roles (`_globals` / `_users`), then each database,
extensions present in the target image first. Stop the owning app, restore,
compare row counts, start the app.

## 9) Apps by household priority (step 10)

| Tier | App | Data source | Notes |
|---|---|---|---|
| 0 | UniFi gateway/switches/APs, VLANs, DHCP | `.unf` from restic (sec. 11) | Before the nodes can have addresses |
| 0 | AdGuard Home DNS (192.168.55.5) | Longhorn volume | DHCP DNS option must point to it |
| 0 | Envoy gateways, cloudflared, external-dns | git (SOPS) | New tunnel ID if Cloudflare was recreated (disaster-recovery 4.8) |
| 1 | Authentik | `authentik-pg-data` volume; dump `authentik-pg` fallback; blueprints in git | Recovery flow exists |
| 1 | Home Assistant, Zigbee2MQTT, Mosquitto | Longhorn volumes (`home-assistant-config`, `zigbee2mqtt-data`) | HA `/config` has no GitOps path; the volume is the only copy besides Longhorn backups. Zigbee pairing keys live in the Z2M volume and the coordinator |
| 1 | Vaultwarden (in-cluster vault) | `vaultwarden-data` volume | Not the external vault from section 3 |
| 2 | Nextcloud + MariaDB | `/src/2` data (restic) + `nextcloud-mariadb` volume or dump | Run `occ` checks (`docs/sops/` upgrade notes on Mail) |
| 2 | Paperless | `/src/3` trees (restic) + `paperless-db` volume or dump | `docs/sops/paperless.md` |
| 3 | Monitoring, Grafana, Elasticsearch | git; history is rebuildable, Grafana volume optional | Telemetry history is not restored |
| 3 | Sure, Mealie, Actual, Affine, Penpot, teslamate, traccar | Longhorn volumes / dumps | Per-app |
| 4 | Immich | Derived from the iCloud backups; rebuildable | Restore `icloud-backup`, let it re-index |
| 4 | iCloud backup instances | `*-session` volumes; else 2FA re-auth (`docs/sops/icloud-docker-reauth.md`) | |
| 5 | Plex, Jellyfin, downloads, Frigate recordings | Recreatable or lost (sec. 14) | Curated music/books/audiobooks/archive ARE restored |

## 10) External services

- **Cloudflare**: tunnel credentials and token are in SOPS. If the account is
  intact, the zone settings are Terraform-managed (`terraform/cloudflare/tf`)
  but its state lives only in a cluster Secret that was lost; either
  `terraform import` the zone settings or accept that the live settings stay as
  they are (see `docs/sops/cloudflare.md`). Account compromise path:
  `docs/sops/disaster-recovery.md` 4.8.
- **Storage box**: unaffected by the loss; if the box account must be
  re-provisioned, `terraform/hetzner/tf` and its state copy (section 3 row 13).
- **GitHub**: if the account is gone, restore the repo from the mirror and update
  `instance.sync.url` (disaster-recovery 4.7).

## 11) UniFi controller restore (step 11)

The controller is the UniFi OS gateway, not a cluster app, so it is rebuilt
first. The gateway writes autobackups only to its own disk; the weekly
`backup/unifi-backup` job copies the newest `.unf` (newest 8 kept) to
`backups/unifi` on the NAS, and the nightly core job carries that directory
off-site (`/src/1/unifi`).

1. Restore `/src/1/unifi` (section 4.2) and pick the newest `.unf`
   (restore is not blocked by the Longhorn target).
2. New gateway: factory state, adopt/set up locally, then Settings, System,
   Restore with that file (`docs/sops/backup.md` "UniFi Controller Backup",
   `docs/sops/disaster-recovery.md` 4.10).
3. Devices: switches and APs normally re-adopt on their own with the restored
   site; any that do not need a factory reset and re-adoption
   (`unifictl local device adopt-all` after the Mac mini is rebuilt).
4. Without a `.unf`: rebuild VLANs, WiFi, mDNS and DHCP from `CLAUDE.md`
   "Network Architecture" (do NOT recreate retired VLAN 10).
5. Residual risk: the weekly copy job was verified against a stub, not yet
   against the live controller at the time of the backup SOP; confirm one real
   `.unf` exists in `backups/unifi` and its size in the drill.

## 12) Mac mini, laptops, desktops

### 12.1 Mac mini rebuild (step 12)

What runs there (from the repo): the ops console and headless dispatcher
(`runbooks/launchd/*.plist`, `runbooks/headless-dispatcher.py`, the
`daily-operation` Claude session), the sweep tooling, the shared Ollama host
(models, `ollama-toolfix`), the ARAG scraper and menubar app, bank-refresh,
findmy-traccar-sync, the iterm2-harness, and the repo checkout with the local
`age.key`.

In git (rebuilt by cloning): the repo, `runbooks/`, launchd plists, `.mise.toml`
(tools), `.sops.yaml`. Other repos under `~/code` are on GitHub and thus in the
monthly mirror (anything unpushed is lost).

Only on the machine (NOT in git, NOT confirmed backed up): `age.key` (vault copy
exists), `kubeconfig`/`talosconfig` (regenerable), `.unifictl.yaml`, Claude Code
login and the project memory under `~/.claude/` (including the operator's
memory index), `~/Library/Logs/cberg-headless`, Ollama model store (re-pullable,
hours of download), ARAG scraper data (`arag.sqlite`, menubar config with its
Paperless token, the rooted Android emulator image), bank-refresh credentials and
sessions, iTerm layouts. **Which Macs the two Time Machine images in the core
tier belong to is UNVERIFIED - operator to confirm**; if the Mac mini is one of
them its machine state is recoverable from there (crash-consistent only).

Rebuild order: install `mise`, clone, restore `age.key`, `mise install`,
regenerate client configs with `talhelper genconfig` and `talosctl kubeconfig`, re-pull Ollama models via `ollama-agent`, restore ARAG and
bank-refresh state from their own sources, re-create the headless dispatcher
via the plists, then re-assert crons with `window-crons.py --check`. The
cluster crons (OpenClaw) only trigger; they do nothing until the Mac mini
exists again.

### 12.2 Windows desktop, MacBooks, Omarchy laptop (OPEN GAP, NOT BUILT)

The operator's stated intent: borg backups of client devices should live on the
cluster. **That is not built.** `grep -ri borg` over `docs/`, `kubernetes/` and
`runbooks/` finds nothing deployable (only an unrelated SOPS blob). What
exists today:

- The Omarchy laptop writes its own borg repository to a directory on the
  NAS `backups` share; that directory (about 220 GiB) is carried off-site by
  the core tier. It is a NAS-hosted copy, not a cluster service; nothing
  monitors it and there is no restore procedure in this repo.
- Two Time Machine sparsebundle images on the NAS are in the core tier (first
  upload in progress).
- The Windows desktop: no backup of any kind is documented. UNVERIFIED.

So there is no procedure here; it is an open gap tracked below.

## 13) Verification Tests (checklist after rebuild)

- [ ] `kubectl get nodes` 3/3 Ready; Talos version and extensions match
      `talconfig.yaml` / `schematic.yaml` (`talosctl get extensions`).
- [ ] `flux get kustomizations -A | awk '$5 != "True"'` and the same for
      helmreleases show only the header.
- [ ] `kubectl get volumes.longhorn.io -n storage` all `healthy`; `kubectl get pvc -A`
      none `Pending`/`Lost`; every restored volume has the original name.
- [ ] Backup target `available: true`; the next nightly Longhorn backup (23:00 UTC)
      completes.
- [ ] Off-site jobs run (00:30/00:40 UTC); `OffsiteBackup*` alerts quiet; DB dump
      jobs succeed; `unifi-backup` and `github-mirror` not stale.
- [ ] DNS answers from 192.168.55.5; DHCP hands out that DNS; UniFi device list
      complete (`unifictl local device list`).
- [ ] Authentik login works; Home Assistant entities present; Nextcloud files
      and Mail; Paperless search returns documents; Vaultwarden vault opens.
- [ ] Sample sha256 of restored files against an earlier manifest (none exists
      today: see drills).
- [ ] `runbooks/health-check.sh` clean; AlertManager firing set is Watchdog only.
- [ ] Elasticsearch ingestion in `logs-generic-default` (new cluster, empty
      history is expected).
- [ ] Immediately re-seed the off-site jobs and re-run `restic check` weekly.
- [ ] Security: rotate anything that was exposed during the event; re-run
      `runbooks/security-check.py`.

## 14) What is permanently lost (honest table)

| Item | Why | Mitigation |
|---|---|---|
| Bulk media library (movies, TV, downloads, transcode scratch) | Deliberately not backed up (operator decision 2026-11-15/16); the older vendor cloud upload is an unverified second copy | Re-acquire; curated music/books/audiobooks/archive ARE in core |
| Derived photo cache (Immich), thumbnails, ML caches | Derived, rebuildable | Re-index |
| Data newer than the last nightly run | Longhorn 23:00 UTC, restic 00:30/00:40 UTC, dumps 21:15 UTC | Up to ~24 h |
| Prometheus/Elasticsearch history | Excluded as rebuildable | Starts fresh |
| Terraform state for Cloudflare | Only in a cluster Secret, no off-site copy | Re-import |
| Issues/PR history of mirrored repos as live objects | JSON only, no GitHub import API | Reference JSON |
| Mac mini local-only state (section 12.1) | Not in git, backup not confirmed | See open gaps |
| Windows desktop contents | No backup documented | Open gap |
| Retention beyond 7 daily / 4 weekly / 12 monthly | By policy | |
| Anything if age key AND the independent restic-password copy are both lost | Ciphertext only | Section 3 rows 1, 3, 18 |

## 15) Fire drills

### 15.1 Monthly (light, mostly automated)

Automated today: weekly `offsite-backup-check` (5% read-data subset, Wed 04:30
UTC), weekly contents exporter, per-job metrics and alerts, nightly Longhorn
backups. Manual monthly proof (about 30 minutes, no cluster writes):

1. `rr core snapshots` / `rr apps snapshots` shows a snapshot from the last 36 h
   (60 h for core while the first Time Machine upload runs).
2. Restore 10 random files from each tier into a scratch directory and compare
   sha256 against the live NAS (the 2026-11-15/16 drill method).
3. GitHub mirror drill (`docs/sops/backup.md` "Monthly fire-drill").
4. One database dump restored into a scratch instance (`docs/sops/backup.md`).
5. `runbooks/backup-restore-proof.py` for one critical volume (the quarterly
   probe, run monthly for one volume).
6. Row 1 test of section 3 (age key from the password manager only).

**Not built:** a scheduled CronJob that performs the restic restore proof
automatically; the 2026-11-16 drill was a one-off Job whose manifest is not
kept in git. Building that CronJob (read-only key, 2Gi limit, `CHOWN FOWNER
DAC_OVERRIDE FSETID` added) is the recommended next step.

### 15.2 Quarterly (full)

- [ ] Fresh machine, only password manager + internet: sections 4.1 and 4.2.
- [ ] Restore the whole priority set to scratch storage and time it. Record
      uncapped throughput in section 2 (replaces the assumptions).
- [ ] Mount-test a restored Time Machine image.
- [ ] Restore `backupstore` into a scratch NAS directory and run
      `longhorn-bulk-restore.py` against a scratch cluster or with a
      `restoretest-` prefix (`docs/sops/longhorn.md`).
- [ ] `talhelper genconfig --out-dir <scratch>` byte-compare with live configs;
      POST `schematic.yaml` to the factory and compare the ID.
- [ ] Confirm every UNVERIFIED row of section 3 and write the date back.
- [ ] Check restic and the restic image version still match; check the mirror
      token expiry; confirm the Cloudflare and registrar recovery codes.
- [ ] Update this SOP's measured numbers and the drill record in `backup.md`.

## 16) Open gaps and UNVERIFIED items (as of 2026-11-17)

Unverified (operator to confirm): vault copy of the age key still decrypts;
storage-box credentials and restic passwords have a copy outside SOPS; storage-box
account recovery; GitHub, Cloudflare, registrar and UniFi/Ubiquiti account
recovery; NAS admin login; Apple ID credentials; password manager emergency kit;
which Macs the Time Machine images belong to; Windows desktop backup; Mac mini
non-git state; real `.unf` present in `backups/unifi`.

Open gaps: client borg-on-cluster (not built); automated restic restore-proof
CronJob (not built); `restic` not pinned in `.mise.toml`; uncapped restore
throughput unmeasured; Cloudflare Terraform state has no off-site copy;
no end-to-end timed rebuild has ever been performed.

Claims verified 2026-11-17: schematic ID reproduces from `schematic.yaml`;
extensions and cmdline match live nodes; `talhelper genconfig` reproduces node
configs and CA; task names `bootstrap:talos`, `bootstrap:apps`,
`talos:generate-config`; `/src/1/backupstore` path; SOPS Secret key names; share
mapping `/src/1`=backups, `/src/2`=nextcloud, `/src/3`=paperless_ngx.

## 17) Examples

```bash
# Five-minute vault test (quarterly): proves the age key and the storage-box
# credentials are usable from the password-manager copy alone.
mise exec -- sops -d kubernetes/apps/backup/offsite-backup/secrets/secret-write.sops.yaml \
  | python3 -c 'import sys,yaml; print(sorted(yaml.safe_load(sys.stdin)["stringData"]))'   # key names only
# Talos reproducibility proof (writes only into a scratch dir):
(cd kubernetes/bootstrap/talos && mise exec -- talhelper genconfig --out-dir "$(mktemp -d)")
curl -s -X POST --data-binary @kubernetes/bootstrap/talos/schematic.yaml https://factory.talos.dev/schematics
```

## 18) Troubleshooting

- `Fatal: wrong password or no key found`: the tier/password pairing is wrong
  (`core` key with the `apps` password, or the other way round).
- `Permission denied (publickey)`: wrong key for the tier; the key is locked
  to one repo directory.
- `host key verification failed`: keep `StrictHostKeyChecking=yes` and use the
  `KNOWN_HOSTS` line from the Secret; do not accept an unknown key during a
  disaster.
- Restore exits non-zero but data is present: ownership (`lchown`) failures,
  section 4.2.
- Longhorn BackupTarget `available: false`: share not mounted/reachable or the
  `backupstore` directory is not at the share root.
- A PVC Pending after Flux: static volume not applied or restored yet.

## 19) Diagnose Examples

```bash
rr core snapshots --host offsite --tag core | tail -5
rr core stats latest --mode raw-data
mise exec -- kubectl -n storage get backuptargets.longhorn.io default -o jsonpath='{.status.available}{"\n"}'
mise exec -- flux get kustomizations -A | awk '$5 != "True"'
```

## 20) Health Check

The verification checklist above is the health check; add `runbooks/health-check.sh`.

## 21) Security Check

Security: the restic credentials are materialised only in a
mode-700 temp directory, removed afterwards; never paste values; the repository
is public, so nothing in this SOP names hosts, accounts or paths beyond what
`docs/sops/storage-safety.md` already publishes. Do not use the admin key for a
restore. After the event rotate every credential that was copied to a
workstation.

## 22) Rollback Plan

A rebuild has no rollback; the old environment is gone. Within the rebuild: Flux
state rolls back with `git revert`; a bad Longhorn restore is removed by exact
volume name and redone from an earlier backup; a bad restic restore is repeated
(it is read-only against the box); the append-only keys cannot damage the
off-site copy.

## 23) References

`docs/sops/disaster-recovery.md`, `docs/sops/backup.md`, `docs/sops/longhorn.md`,
`docs/sops/storage-safety.md`, `docs/sops/talos-upgrade.md`,
`docs/sops/authentik.md`, `docs/sops/cloudflare.md`, `docs/sops/sops-encryption.md`,
`docs/sops/vulnerability-disclosure.md`, `kubernetes/bootstrap/talos/`,
`kubernetes/bootstrap/apps/`, `kubernetes/apps/backup/offsite-backup/`.

## Version History

- `2026.11.17`: First version. Recorded the Talos schematic in git, corrected
  the `talosconfig` claim, confirmed the backupstore path in the core snapshot.
