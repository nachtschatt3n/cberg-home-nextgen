---
plan_id: jellyfin-config-rwo-migration
component: jellyfin
pr: null                              # Not a version bump — a storage re-platform. No Renovate PR exists or can.
kind: config
current: "pvc/media/jellyfin-config -> PV jellyfin-config -> Longhorn Volume storage/jellyfin-config, accessMode rwx (2 replicas, 25Gi, ~5.8G used per df), served to the pod over NFS by share-manager-jellyfin-config; /config mount source is `<share-manager-svc>:/jellyfin-config` — re-measured live 2026-09-28"
target: "new speaking-name static Longhorn volume jellyfin-config-rwo (Volume CR + PV + PVC, all the same identifier), accessMode rwo, ext4 on a Longhorn block device mounted directly by the pod — no NFS hop under SQLite WAL; HelmRelease persistence.config.existingClaim -> jellyfin-config-rwo; the old RWX volume is kept UNTOUCHED and unmounted as the rollback source"
update_type: storage-migration
risk: medium                          # One app, one config volume, copy-then-switch with the
                                      # original volume left intact: nothing is written to the
                                      # old volume, so the worst case is a git revert back onto
                                      # it. Not `low` because it is the household's actively used
                                      # media server's whole state (jellyfin.db 68 MB + metadata
                                      # 2.4G) and it allocates a new Longhorn volume by hand.
est_duration_min: 75                  # premises+baseline 10 · backup gate ~12 (the trigger backs up
                                      # EVERY volume, ~11.5 min) · restore proof 15
                                      # (runs in parallel with the copy) · stop 5 · copy+compare 15
                                      # · cutover commit+reconcile 10 · verification 20.
                                      # Measured volume: ~5.8G.
needs_reboot: false
touches:
  namespaces: [media, storage]
  resources:
    - helmrelease/jellyfin             # replicaCount 1->0->1 and persistence.config.existingClaim
    - deployment/jellyfin
    - pvc/jellyfin-config              # OLD, RWX — read (copy source) only, never written, never deleted here
    - pv/jellyfin-config               # OLD — untouched
    - volume.longhorn.io/jellyfin-config          # OLD — untouched, kept as rollback source
    - pvc/jellyfin-config-rwo          # NEW
    - pv/jellyfin-config-rwo           # NEW
    - volume.longhorn.io/jellyfin-config-rwo      # NEW, applied by hand (Flux cannot own it)
    - volume.longhorn.io/jellyfin-config-restoretest   # SCRATCH restore-proof volume (+ its PV/PVC, Job jf-restoretest), deleted at the end of §3.4
    - job/jf-rwo-copy                  # one-off copy Job, §3.6
    - cronjob/media-intake-watcher     # intake-cronjob.yaml (dfc7ee20): kill switch INTAKE_APPLY=0 during the window (§3.5-3.8); it calls Jellyfin rescans
  shared: [storage/longhorn, igpu-i915]   # igpu-i915: the Jellyfin pod requests+limits
                                       # gpu.intel.com/i915: 1 (k8s-nuc14-03, live 2026-09-28); the
                                       # stop/start re-allocates it — same token as jellyfin-12.1.
                                       # storage/longhorn: allocates a new 2-replica Longhorn volume + a scratch
                                       # restore; SD-11 floor ("longhorn"/"storage") applies — this
                                       # plan is deliberately NOT eligible for unattended nights.
depends_on: []
conflicts_with:
  - jellyfin-12.1                      # sat-attended:2026-10-10 — same helmrelease/jellyfin and
                                       # pvc/jellyfin-config; its backup_gate/restore steps name the
                                       # OLD volume `jellyfin-config`. This plan is placed AFTER it
                                       # (2026-10-25) so 12.1's reviewed plan stays valid. If the
                                       # order is ever swapped, 12.1's backup_gate, premises and §5
                                       # must be re-derived for jellyfin-config-rwo BEFORE it runs.
  - helm-drift-detection               # touches helmrelease/media/jellyfin
  - flux-oci-chart-sources             # mirrors the jellyfin chart source (touches helmrelease/jellyfin)
capability_change: false              # same app, same image, same data; only the block device
                                      # under /config changes. No user-visible feature change.
rollback_class: git-revert            # The OLD volume is never written by this plan (copy source
                                      # mounted readOnly), so `git revert` of the cutover commit
                                      # puts Jellyfin back on its pre-window state (file-level identical). The
                                      # only thing a revert gives up is state Jellyfin wrote to the
                                      # NEW volume after cutover (watch progress since then) —
                                      # interruption-class, not data loss. backup_gate + restore_proof
                                      # are declared anyway as the second line of defence.
backup_gate: "on-demand Longhorn backup of volume jellyfin-config, triggered IN-WINDOW (§3.2)
  while Jellyfin is still running (the volume must be attached — this cluster has
  allow-recurring-job-while-volume-detached=false, so a backup of the stopped, detached RWX
  volume would never run). PASS = `runbooks/longhorn-backup-age.py jellyfin-config --max-hours 1`
  prints FRESH AND the named Completed Backup CR's creationTimestamp is after GATE_START.
  Triggered via cronjob/daily-backup-all-volumes (ns storage)."
restore_proof: "§3.4: restore the backup_gate backup into a SCRATCH Longhorn volume
  jellyfin-config-restoretest (spec.fromBackup = that Backup CR's .status.url), mount it
  read-only in a one-off Job, copy jellyfin.db + -wal + -shm into an emptyDir, open THAT copy
  normally (so the WAL is replayed, not ignored), and require `PRAGMA integrity_check` == ok
  plus a non-zero BaseItems row count. A backup that exists is not a backup that restores;
  this proves the restore path end to end before the app is stopped."
finding_refs: []
status: awaiting-go   # plan-reviewer 2026-09-28: needs-fix (B1-B4) -> fixed -> re-review needs-fix (liveness wording) -> fixed -> ready-for-go. Longhorn/storage => outside SD-11 (floor), so it is GO-pending regardless of review.
review: ready-for-go@2026-09-28
window: "sun-attended:2026-10-25"     # after jellyfin-12.1 (sat 10-10) so that plan stays valid; co-tenant
                                      # redis-fleet-8.10.2 (85m) + this (75m) = 160m <= 180m schedulable.
premises:
  - id: config-pvc-is-still-rwx-longhorn-static
    why: >-
      The whole plan assumes jellyfin-config is still the RWX longhorn-static claim. If
      it is already RWO (someone migrated it) or on another class, this plan is stale.
    run: kubectl get pvc -n media jellyfin-config -o jsonpath='{.spec.storageClassName} {.spec.accessModes[0]}'
    expect_exact: longhorn-static ReadWriteMany
  - id: helmrelease-still-mounts-jellyfin-config
    why: >-
      §3.8 edits existingClaim from jellyfin-config to jellyfin-config-rwo. If the HR
      already points elsewhere, the edit and the rollback are both wrong.
    run: kubectl get helmrelease -n media jellyfin -o jsonpath='{.spec.values.persistence.config.existingClaim}'
    expect_exact: jellyfin-config
  - id: deployment-strategy-is-recreate
    why: >-
      RWO + replicas 1 + RollingUpdate = Multi-Attach deadlock
      (docs/sops/longhorn-rwo-multi-attach.md). The rendered Deployment must already be
      Recreate; this plan does not change it and must not proceed if it drifted.
    run: kubectl get deploy -n media jellyfin -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: new-volume-name-free
    why: >-
      jellyfin-config-rwo must not already exist — applying the Volume CR over an existing
      one (or binding an existing PV) would mix states.
    run: kubectl get volumes.longhorn.io -n storage -o jsonpath='{.items[*].metadata.name}'
    expect_matches: '^(?!.*\bjellyfin-config-rwo\b).*$'
  - id: old-volume-healthy
    why: >-
      The backup_gate needs the old volume attached and healthy to snapshot it.
    run: kubectl get volumes.longhorn.io -n storage jellyfin-config -o jsonpath='{.status.state} {.status.robustness}'
    expect_exact: attached healthy
  - id: old-volume-backups-exist
    why: >-
      Independent of the in-window gate, the nightly chain must be working; a stale nightly
      means Longhorn backups are broken and the in-window gate would likely fail too.
      FRESHNESS itself is checked in §2.2 G1b with runbooks/longhorn-backup-age.py —
      plan-premises.py's read-only allowlist refuses `python3`, so the premise can only
      assert that Completed backups exist for this volume (label-matched, which also
      catches the unsynced nightly CR — F-a915dd47).
    run: kubectl get backups.longhorn.io -n storage -l backup-volume=jellyfin-config -o jsonpath='{.items[*].status.state}'
    expect_contains: Completed
  - id: backup-on-detached-still-disabled
    why: >-
      §3.2 takes the gate backup BEFORE the stop precisely because this setting is false.
      If it flipped to true the plan is still correct, but re-read §3.2's rationale.
    run: kubectl get settings.longhorn.io -n storage allow-recurring-job-while-volume-detached -o jsonpath='{.value}'
    expect_exact: "false"
sops_refs: []
generated: "2026-09-28"
---

# jellyfin-config: Longhorn RWX (NFS) -> Longhorn RWO

## 1. Summary & why

`jellyfin-config` (jellyfin.db, metadata, plugins, users) is a Longhorn **RWX**
volume. Longhorn serves RWX through a per-volume `share-manager` pod exporting
the ext4 filesystem over **NFSv4**; the Jellyfin pod mounts
`<share-manager-svc>:/jellyfin-config` (verified 2026-09-28 via `df /config` in
the pod). SQLite in WAL mode relies on shared-memory (`-shm`) and POSIX byte
range locks, which are unreliable over NFS. The symptom is `database is
locked` during library scans (5 occurrences in the previous container's log,
measured 2026-09-28, all during FULL library scans) and liveness kills mid-scan
(pod restartCount 1, last terminated `Error` 2026-09-28T05:52Z). The liveness
probe's failure budget was raised to 20 x 30s = 10 min (httpGet /health,
failureThreshold 20, `3b68337d`) as the immediate mitigation; a tcpSocket swap
(`ceda2aa3`) was rejected by the API server ("more than 1 handler") and
superseded. This plan removes the cause.

Jellyfin is a single-replica Deployment (`replicaCount: 1`, strategy
`Recreate`, rendered live) — it never needed RWX. Nothing else mounts
`jellyfin-config` (only `share-manager-jellyfin-config` + the Jellyfin pod).

**Why a new volume and not an in-place access-mode flip:** PVC/PV
`accessModes` are immutable, so an in-place change means deleting and
re-creating the bound PV/PVC objects around the only copy of the data. A copy
into a new speaking-name volume keeps the original untouched (never mounted
read-write) and unmounted, which is what makes `rollback_class: git-revert` honest.

**Why this is GO-pending, not SD-11:** it touches `storage/longhorn`, which is
in the SD-11 floor (`runbooks/maintenance-plan.py` `SD11_FLOOR`). Interruption
(~30 min of Jellyfin downtime) is the only intended cost, but storage plans
need an operator GO by policy.


## 2. Pre-checks

### 2.1 State snapshot (re-measure at window start; figures from 2026-09-28)

| Item | 2026-09-28 |
|---|---|
| Old Longhorn volume | `jellyfin-config`, rwx, 2 replicas, 25Gi, attached/healthy |
| Used (df in pod) | 5.8G (data 3.4G, metadata 2.4G) |
| jellyfin.db | 68 MB (+ WAL 4 MB); legacy `library.db.old` files present |
| Newest nightly backup | Completed 2026-09-28T03:03Z (~10.8 GB backup size) |
| Rendered strategy | `Recreate`, replicas 1 |
| Liveness probe | httpGet /health, failureThreshold 20, period 30s (`3b68337d`) |
| Items/Counts | Movies 501 · Series 47 · Episodes 2473 · Songs 631 · Albums 40 · BoxSets 78 |
| share-manager | `share-manager-jellyfin-config` Running in ns storage |
| "database is locked" | 5 lines in the previous container's lifetime (~21.5h, during FULL scans); 0 in the current container (3h) |

### 2.2 Commands (G1–G3 are ABORT gates)

All temp files go to a per-run scratch dir, never `/tmp`:

```bash
cd /Users/mu/code/cberg-home-nextgen
S=$(mktemp -d "${TMPDIR:-$HOME}/jf-rwo.XXXXXX"); echo "S=$S"

# G1 — premises + backup freshness
mise exec -- .venv/bin/python3 runbooks/plan-premises.py jellyfin-config-rwo-migration        # all PASS
mise exec -- .venv/bin/python3 runbooks/longhorn-backup-age.py jellyfin-config --max-hours 26    # G1b: FRESH

# G2 — API baseline (port-forward; key stays in-shell, never echoed)
JF_KEY=$(mise exec -- kubectl -n media get secret media-manager-tokens -o jsonpath='{.data.JELLYFIN_API_KEY}' | base64 -d)
mise exec -- kubectl port-forward -n media svc/jellyfin 8097:8096 >/dev/null 2>&1 & PF=$!
sleep 3
H="Authorization: MediaBrowser Token=\"$JF_KEY\""
curl -s -H "$H" http://localhost:8097/Items/Counts > "$S/counts-before.json"
curl -s -H "$H" http://localhost:8097/Users | python3 -c "import sys,json;print(len(json.load(sys.stdin)))" > "$S/users-before.txt"
curl -s -H "$H" http://localhost:8097/System/Info | python3 -c "import sys,json;print(json.load(sys.stdin)['Version'])" > "$S/version-before.txt"
cat "$S/counts-before.json" "$S/users-before.txt" "$S/version-before.txt"
#   G2 PASS = all three non-empty (counts JSON parses, users >= 1, a version string).
kill $PF

# Baselines recorded for §4 (evidence, not gates)
mise exec -- kubectl get pods -n storage -o name | grep -c 'share-manager-jellyfin-config$' > "$S/share-manager-before.txt"   # expect 1
mise exec -- kubectl logs -n media deploy/jellyfin | grep -c 'database is locked' > "$S/locked-before.txt"; cat "$S/locked-before.txt"
mise exec -- kubectl logs -n media deploy/jellyfin --previous 2>/dev/null | grep -c 'database is locked' >> "$S/locked-before.txt"

# G3 — Longhorn free space: 2 replicas x 25Gi (new) + 1 x 25Gi (scratch)
mise exec -- kubectl get nodes.longhorn.io -n storage -o jsonpath='{range .items[*]}{.metadata.name}{range .status.diskStatus.*} avail={.storageAvailable} sched={.storageScheduled} max={.storageMaximum}{end}{"\n"}{end}'
#   G3 PASS = at least 2 nodes with (max - sched) >= 30 GB AND avail >= 0.25*max + 30 GB
#   (over-provisioning 100%, minimal-available 25% — live settings 2026-09-28; measured then:
#   max-sched 238–351 GB, avail 392–463 GB of ~998 GB per node).

# G4 — every manifest in §3 passes a server-side dry run BEFORE the window starts
#   (write the §3.1/§3.4/§3.6 YAML blocks to $S first). The Longhorn webhook REJECTS a
#   fromBackup URL whose backup does not exist, so dry-run the restoretest template with
#   the newest REAL backup's URL (3.4 re-renders it with GATE_BACKUP).
NEWEST=$(mise exec -- kubectl get backups.longhorn.io -n storage -l backup-volume=jellyfin-config --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}')
URL=$(mise exec -- kubectl get backups.longhorn.io -n storage "$NEWEST" -o jsonpath='{.status.url}')
sed "s#__BACKUP_URL__#$URL#" "$S/restoretest.yaml.tmpl" > "$S/restoretest-dry.yaml"
for f in "$S"/restoretest-dry.yaml "$S"/jf-restoretest-job.yaml "$S"/jf-rwo-copy-job.yaml \
         kubernetes/apps/media/jellyfin/app/longhorn-volume-rwo.yaml \
         kubernetes/apps/media/jellyfin/app/config-pv-rwo.yaml kubernetes/apps/media/jellyfin/app/config-pvc-rwo.yaml; do
  mise exec -- kubectl apply --dry-run=server -f "$f" || echo "G4 FAIL: $f"
done
#   G4 PASS = no "G4 FAIL" line. Verified at authoring (2026-09-28): all six blocks in this
#   plan pass `--dry-run=server` (restoretest with a real backup URL; a bogus backup name is
#   rejected by the webhook, which is the desired behaviour). The Jobs' PVCs need not exist
#   for a server dry-run of a Job.
```

## 3. Steps

**Ordering (binding):** 3.1 → 3.2 → 3.3; 3.4 (restore proof — reads the
BACKUP, not the live volume) starts after 3.2 and runs in parallel with
3.5–3.7; **do not push commit A (3.5) until 3.2 has PASSED**, and **3.4 must
PASS before 3.8**.

### 3.1 Prepare commit A locally (do NOT push yet)

New file `kubernetes/apps/media/jellyfin/app/longhorn-volume-rwo.yaml` —
**NOT listed in `kustomization.yaml`** (Flux's `targetNamespace: media` would
override `namespace: storage` and create a broken duplicate). Applied by hand in 3.3.

```yaml
---
# APPLY BY HAND: kubectl apply -f longhorn-volume-rwo.yaml  (see docs/sops/longhorn.md)
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: jellyfin-config-rwo
  namespace: storage
  labels:
    recurring-job-group.longhorn.io/default: enabled   # nightly daily-backup-all-volumes
spec:
  size: "26843545600"   # 25Gi, same as the old volume
  numberOfReplicas: 2   # the old volume's live CR has 2 (the old PV's "3" attribute is not what Longhorn uses)
  staleReplicaTimeout: 30
  dataEngine: v1
  accessMode: rwo
  frontend: blockdev
  migratable: false
  encrypted: false
```

New `config-pv-rwo.yaml` and `config-pvc-rwo.yaml`, both added to `kustomization.yaml`:

```yaml
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: jellyfin-config-rwo
spec:
  capacity:
    storage: 25Gi
  volumeMode: Filesystem
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: longhorn-static
  csi:
    driver: driver.longhorn.io
    fsType: ext4
    volumeAttributes:
      numberOfReplicas: "2"
      staleReplicaTimeout: "30"
    volumeHandle: jellyfin-config-rwo
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: jellyfin-config-rwo
  namespace: media
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 25Gi
  storageClassName: longhorn-static
  volumeName: jellyfin-config-rwo
```

Keep the old `config-pv.yaml` / `config-pvc.yaml` in place (rollback source).

Commit A also edits:
- `kubernetes/apps/media/jellyfin/app/helmrelease.yaml`: `replicaCount: 1` → `0`.
  The chart renders `replicas: {{ .Values.replicaCount }}` (chart 3.2.0
  `templates/deployment.yaml`), so the stop is Flux's DESIRED state and cannot be
  drift-corrected back to 1 (`kubectl scale --replicas=0` does not hold — lesson
  from `bitnamilegacy-exit-nextcloud-db`).
- `kubernetes/apps/media/library-tools/app/intake-cronjob.yaml` (committed in
  `dfc7ee20`): the `INTAKE_APPLY` env value `"1"` → `"0"` (the file's documented
  kill switch; the job then only plans/logs/pushes metrics). It calls Jellyfin
  `/Library/Media/Updated` after moves, which would fail while Jellyfin is down.

Write the commit message to a unique file now: `$S/msg-commit-a.txt`.

### 3.2 backup_gate — on-demand backup while Jellyfin is still running

The old volume must be attached: `allow-recurring-job-while-volume-detached`
is `false`, so a backup of the stopped, detached RWX volume would never run.

```bash
GATE_START=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "GATE_START=$GATE_START"
mise exec -- kubectl create job -n storage --from=cronjob/daily-backup-all-volumes pre-jf-rwo-$(date +%Y%m%d-%H%M)
# poll every 60s, up to 20 min:
mise exec -- kubectl get backups.longhorn.io -n storage -l backup-volume=jellyfin-config \
  --sort-by=.metadata.creationTimestamp -o custom-columns=N:.metadata.name,S:.status.state,C:.metadata.creationTimestamp | tail -2
mise exec -- .venv/bin/python3 runbooks/longhorn-backup-age.py jellyfin-config --max-hours 1
```

PASS = a Completed backup with creationTimestamp > GATE_START **and** the
helper prints `FRESH`. Record it: `GATE_BACKUP=<name>`. Not Completed in 20
min => **STOP** (nothing has been changed; abandon this plan's run).

Side effects to expect: the trigger is the all-volumes RecurringJob, so it
backs up **every** Longhorn volume (~11.5 min measured) and each volume's
retention window shifts by one backup (one day of history trimmed). The
backup is crash-consistent (app running), which SQLite WAL tolerates by
design; the quiesced copy is the old volume itself, never written by this plan.

### 3.3 Create the new volume by hand

```bash
mise exec -- kubectl apply -f kubernetes/apps/media/jellyfin/app/longhorn-volume-rwo.yaml
mise exec -- kubectl get volumes.longhorn.io -n storage jellyfin-config-rwo -o jsonpath='{.status.state} {.spec.accessMode}{"\n"}'   # detached rwo
```

### 3.4 restore_proof — restore GATE_BACKUP into a scratch volume and prove it

```bash
URL=$(mise exec -- kubectl get backups.longhorn.io -n storage "$GATE_BACKUP" -o jsonpath='{.status.url}')
test -n "$URL" || echo "STOP: backup has no .status.url"
sed "s#__BACKUP_URL__#$URL#" "$S/restoretest.yaml.tmpl" > "$S/restoretest.yaml"
mise exec -- kubectl apply -f "$S/restoretest.yaml"
# poll every 60s up to 20 min until the restore finished:
mise exec -- kubectl get volumes.longhorn.io -n storage jellyfin-config-restoretest -o jsonpath='{.status.restoreRequired} {.status.state} {.status.robustness}{"\n"}'
#   wait for: "false detached ..." (restore done, volume released)
mise exec -- kubectl apply -f "$S/jf-restoretest-job.yaml"
mise exec -- kubectl wait -n media job/jf-restoretest --for=condition=complete --timeout=15m
mise exec -- kubectl logs -n media job/jf-restoretest
```

`$S/restoretest.yaml.tmpl` (the URL contains the backup target host — it is
substituted at run time and never committed):

```yaml
---
apiVersion: longhorn.io/v1beta2
kind: Volume
metadata:
  name: jellyfin-config-restoretest
  namespace: storage
spec:
  size: "26843545600"
  numberOfReplicas: 1
  staleReplicaTimeout: 30
  dataEngine: v1
  accessMode: rwo
  frontend: blockdev
  migratable: false
  encrypted: false
  fromBackup: "__BACKUP_URL__"
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: jellyfin-config-restoretest
spec:
  capacity:
    storage: 25Gi
  volumeMode: Filesystem
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: longhorn-static
  csi:
    driver: driver.longhorn.io
    fsType: ext4
    volumeAttributes:
      numberOfReplicas: "1"
      staleReplicaTimeout: "30"
    volumeHandle: jellyfin-config-restoretest
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: jellyfin-config-restoretest
  namespace: media
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 25Gi
  storageClassName: longhorn-static
  volumeName: jellyfin-config-restoretest
```

`$S/jf-restoretest-job.yaml`:

```yaml
---
apiVersion: batch/v1
kind: Job
metadata:
  name: jf-restoretest
  namespace: media
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 1800
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      restartPolicy: Never
      securityContext:
        runAsUser: 0
        runAsGroup: 0
      containers:
        - name: check
          image: python:3.14.7-slim
          command:
            - python3
            - -c
            - |
              import shutil, sqlite3, os, sys
              for suf in ("", "-wal", "-shm"):
                  src = "/r/data/jellyfin.db" + suf
                  if os.path.exists(src):
                      shutil.copy2(src, "/work/jellyfin.db" + suf)
              c = sqlite3.connect("/work/jellyfin.db")   # normal open: WAL is replayed
              ic = c.execute("PRAGMA integrity_check").fetchone()[0]
              tables = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
              n = c.execute("select count(*) from BaseItems").fetchone()[0] if "BaseItems" in tables else -1
              print("integrity", ic); print("baseitems", n); print("tables", len(tables))
              sys.exit(0 if ic == "ok" and n > 0 else 1)
          volumeMounts:
            - name: restored
              mountPath: /r
              readOnly: true
            - name: work
              mountPath: /work
          resources:
            requests: {cpu: 100m, memory: 256Mi}
            limits: {memory: 1Gi}
      volumes:
        - name: restored
          persistentVolumeClaim:
            claimName: jellyfin-config-restoretest
            readOnly: true
        - name: work
          emptyDir: {}
```

PASS = Job Complete, log shows `integrity ok` and `baseitems` > 0. FAIL
=> **STOP** before 3.8 (revert commit A per §5 R1 if already pushed): the
backup chain for this volume does not restore; open a finding.

**Schema note:** `BaseItems` is the 10.11 EF-Core table name, verified only
against 10.11.11. This plan runs after `jellyfin-12.1`; once 12.1 has executed,
re-check the table name on the live DB before the window (if it changed, pin the
new name here — the gate is "the restored DB opens, passes integrity_check, and
its main item table is non-empty", and `baseitems -1` means "table not found" =
FAIL, never pass).

Cleanup — scratch objects only, one delete per exact kind/name (this plan
created them; never delete anything named `jellyfin-config` or `jellyfin-config-rwo`):

```bash
mise exec -- kubectl delete job -n media jf-restoretest --ignore-not-found
mise exec -- kubectl delete pvc -n media jellyfin-config-restoretest --ignore-not-found
mise exec -- kubectl delete pv jellyfin-config-restoretest --ignore-not-found
mise exec -- kubectl delete volumes.longhorn.io -n storage jellyfin-config-restoretest --ignore-not-found
```

### 3.5 Stop Jellyfin — push commit A (only after 3.2 PASSED)

```bash
git commit --only \
  kubernetes/apps/media/jellyfin/app/helmrelease.yaml \
  kubernetes/apps/media/jellyfin/app/kustomization.yaml \
  kubernetes/apps/media/jellyfin/app/config-pv-rwo.yaml \
  kubernetes/apps/media/jellyfin/app/config-pvc-rwo.yaml \
  kubernetes/apps/media/jellyfin/app/longhorn-volume-rwo.yaml \
  kubernetes/apps/media/library-tools/app/intake-cronjob.yaml \
  -F "$S/msg-commit-a.txt"
git show --stat HEAD          # exactly these 6 files
git log -1 --format=%s        # your subject, not another session's
git push
# poll every 30s, up to 10 min:
mise exec -- kubectl get deploy -n media jellyfin -o jsonpath='{.spec.replicas} {.status.replicas}{"\n"}'   # "0 " or "0 0"
mise exec -- kubectl get pods -n media -l app.kubernetes.io/name=jellyfin                                  # none
mise exec -- kubectl get pvc -n media jellyfin-config-rwo -o jsonpath='{.status.phase}{"\n"}'             # Bound
mise exec -- kubectl get cronjob -n media media-intake-watcher -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].env[?(@.name=="INTAKE_APPLY")].value}{"\n"}'   # 0
```

### 3.6 Copy (one-off Job; old PVC readOnly, new PVC RW)

`$S/jf-rwo-copy-job.yaml`:

```yaml
---
apiVersion: batch/v1
kind: Job
metadata:
  name: jf-rwo-copy
  namespace: media
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 3600
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      restartPolicy: Never
      securityContext:
        runAsUser: 0        # Jellyfin's files are root-owned; cp -a must preserve ownership
        runAsGroup: 0
      containers:
        - name: copy
          image: python:3.14.7-slim
          command:
            - /bin/sh
            - -ec
            - |
              if ls -A /new | grep -qv '^lost+found$'; then echo "REFUSED: /new not empty"; exit 1; fi
              cp -a /old/. /new/
              python3 - <<'EOF'
              import os, hashlib, sys
              def walk(root):
                  out = {}
                  for d, dirs, fs in os.walk(root):
                      for f in fs + [x for x in dirs if os.path.islink(os.path.join(d, x))]:
                          p = os.path.join(d, f); r = os.path.relpath(p, root)
                          if r.startswith("lost+found"): continue
                          st = os.lstat(p)
                          if os.path.islink(p): h = "link:" + os.readlink(p)
                          else:
                              h = hashlib.sha256()
                              with open(p, "rb") as fh:
                                  for chunk in iter(lambda: fh.read(1 << 20), b""): h.update(chunk)
                              h = h.hexdigest()
                          out[r] = (st.st_size, st.st_uid, st.st_gid, st.st_mode, h)
                  return out
              a, b = walk("/old"), walk("/new")
              print("files old", len(a), "new", len(b))
              print("bytes old", sum(v[0] for v in a.values()), "new", sum(v[0] for v in b.values()))
              diff = [k for k in a if a[k] != b.get(k)] + [k for k in b if k not in a]
              print("mismatches", len(diff)); sys.exit(1 if diff else 0)
              EOF
              python3 -c "import sqlite3;c=sqlite3.connect('/new/data/jellyfin.db');print('integrity',c.execute('PRAGMA integrity_check').fetchone()[0])"
          volumeMounts:
            - name: old
              mountPath: /old
              readOnly: true
            - name: new
              mountPath: /new
          resources:
            requests: {cpu: 200m, memory: 256Mi}
            limits: {memory: 1Gi}
      volumes:
        - name: old
          persistentVolumeClaim:
            claimName: jellyfin-config
            readOnly: true
        - name: new
          persistentVolumeClaim:
            claimName: jellyfin-config-rwo
```

```bash
mise exec -- kubectl apply -f "$S/jf-rwo-copy-job.yaml"
mise exec -- kubectl wait -n media job/jf-rwo-copy --for=condition=complete --timeout=60m
mise exec -- kubectl logs -n media job/jf-rwo-copy
```

The integrity check opens the COPY read-write AFTER the compare, so a WAL
checkpoint it may perform cannot mask a copy difference. The compare is
file-level identity (size, owner, mode, sha256 per file), not block identity.

PASS = Job Complete, `mismatches 0`, equal file and byte counts, `integrity ok`.
FAIL => §5 R1 (revert commit A); Jellyfin comes back on the untouched old volume.
Then `kubectl delete job -n media jf-rwo-copy --ignore-not-found`.

### 3.7 Verify the new volume's backup membership

```bash
mise exec -- kubectl get volumes.longhorn.io -n storage jellyfin-config-rwo -o jsonpath='{.metadata.labels}{"\n"}'
#   must contain recurring-job-group.longhorn.io/default: enabled
```

### 3.8 Cutover — commit B (only after 3.4 AND 3.6 PASSED)

- `helmrelease.yaml`: `persistence.config.existingClaim: 'jellyfin-config'` →
  `'jellyfin-config-rwo'`; `replicaCount: 0` → `1`.
- `intake-cronjob.yaml`: `INTAKE_APPLY` `"0"` → `"1"`.

```bash
git commit --only kubernetes/apps/media/jellyfin/app/helmrelease.yaml \
  kubernetes/apps/media/library-tools/app/intake-cronjob.yaml -F "$S/msg-commit-b.txt"
git show --stat HEAD && git log -1 --format=%s && git push
# poll every 30s, up to 15 min, until the new pod is Running and Ready:
mise exec -- kubectl get pods -n media -l app.kubernetes.io/name=jellyfin -o wide
```

## 4. Verification

**THE pass/fail gate is 4.2** (the pod's /config is a Longhorn block device,
not NFS) — that is the causal change this plan exists to make. 4.1, 4.3, 4.4
are also gates (any failure => §5 R2). 4.5 is evidence only; 4.6 is the
post-window follow-through.

Re-open the port-forward first — the §2.2 one died with the old pod:

```bash
mise exec -- kubectl port-forward -n media svc/jellyfin 8097:8096 >/dev/null 2>&1 & PF=$!; sleep 3
```

1. **Rendered strategy (gate)** — `kubectl get deploy -n media jellyfin -o jsonpath='{.spec.strategy.type}'` == `Recreate`.
2. **No NFS under /config (THE gate)**
   ```bash
   mise exec -- kubectl exec -n media deploy/jellyfin -- df /config | tail -1        # source /dev/longhorn/jellyfin-config-rwo
   mise exec -- kubectl exec -n media deploy/jellyfin -- grep ' /config ' /proc/mounts   # must NOT contain nfs/nfs4
   mise exec -- kubectl get pvc -n media jellyfin-config-rwo -o jsonpath='{.status.phase} {.status.accessModes[0]}{"\n"}'   # Bound ReadWriteOnce
   # share-manager for the OLD volume must go away (baseline: 1 running). Poll every 30s up to 5 min:
   mise exec -- kubectl get pods -n storage -o name | grep -c 'share-manager-jellyfin-config$'   # -> 0
   ```
3. **Contents (gate)** — `/Items/Counts` equals `$S/counts-before.json` field for field; `/Users` count equals `$S/users-before.txt`; `/System/Info` `Version` equals `$S/version-before.txt`. Any drop => §5 R2.
4. **Login (gate)** — the operator signs in once in the web UI (attended window) and plays 10 s of any item.
5. **Lock errors (EVIDENCE, NOT A GATE).** The measured baseline is 5 lines per ~21.5h container
   lifetime and **only during FULL library scans**; the current container showed 0 in 3h. A
   15-minute watch after a folder-scoped scan would read 0 on RWX too, so it cannot fail and
   is deliberately not a gate. Record instead: `kubectl logs -n media deploy/jellyfin | grep -c 'database is locked'`
   now, and repeat the §4.6 comparison.
6. **Post-window follow-through (next morning and day 7)**
   - Next morning: `runbooks/longhorn-backup-age.py jellyfin-config-rwo --max-hours 26` → FRESH (the new volume is in the nightly chain).
   - Day 7: sum of `database is locked` lines across the Jellyfin container's lifetime(s) since cutover, and restartCount, compared to the RWX baseline in `$S/locked-before.txt` (5 per ~21.5h). Expected 0 locks and 0 restarts; a non-zero lock count on RWO means the NFS hop was not the (only) cause — open a finding, do not roll back for it (the migration itself is still sound).
   - Expected noise for 14 days: the detached OLD volume `jellyfin-config` is no longer backed up (detached + `allow-recurring-job-while-volume-detached=false`), so `longhorn-backup-age.py jellyfin-config` and the sweep's backup-age check will read it STALE. That is expected until the old volume is retired; do not "fix" it by re-attaching.

`kill $PF` when done; `rm -rf "$S"` after the window log is written.

## 5. Rollback

- **R1 (before commit B — backup gate, restore proof or copy failed):** `git revert <commit A>` + push → `replicaCount` back to 1 on the untouched old volume, `INTAKE_APPLY` back to 1. Flux prunes the new PV/PVC (Retain: the Longhorn volume survives). The hand-applied Longhorn Volume `jellyfin-config-rwo` stays; delete it only after the operator confirms, by exact name.
- **R2 (after commit B — a §4 gate failed):** one revert commit covering B then A (`git revert --no-commit <B> <A> && git commit -F <msg>`), push. Jellyfin returns to `jellyfin-config` exactly as it was at the stop. Loses only state written to the new volume since cutover (watch progress).
- **R3 (old volume damaged — should be impossible, it is only ever mounted readOnly):** restore `GATE_BACKUP` per `docs/sops/backup.md` "Restore from Backup" into `restored-jellyfin-config` and bind it via git; 3.4 already proved this backup restores.
- **Retention:** the old Volume/PV/PVC `jellyfin-config` stay, unmounted, for **14 days** after a green §4.6 next-morning check. Deleting them is a SEPARATE, operator-approved follow-up plan — never part of this one (storage-safety rule: no storage delete without an explicit go/no-go).

## 6. Interference notes

- **jellyfin-12.1** (sat-attended:2026-10-10) touches the same HR and PVC, and its backup gate names the OLD volume `jellyfin-config`. This plan runs AFTER it; on the day, confirm 12.1 is `executed` and green (its DB migration then lives on the old volume and is what gets copied) and re-check the §3.4 schema note. If 12.1 is still pending, do not run both in one window; re-slot one.
- **redis-fleet-8.10.2** shares sun-attended:2026-10-25 and touches ns media (a redis leg), not Jellyfin or Longhorn volumes: independent; run this plan first or last, not interleaved with a media redis leg.
- **igpu-i915**: the stop releases and the start re-requests one `gpu.intel.com/i915` slot; if another GPU plan is in the same slot, sequence them.
- **library-tools CronJobs** (`media-metadata-coverage` hourly, `media-per-item-refresh` 6-hourly) read Jellyfin's API; during the ~30 min stop they log fetch errors and exit — tolerated, read-only. `media-intake-watcher` is held by its kill switch (3.5 → 3.8).
- **Longhorn**: one extra 25Gi 2-replica volume permanently (+ ~5.8G actual), a 1-replica scratch restore for ~15 min, and an all-volumes backup run (3.2). G3 checks free space.
