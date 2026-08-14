---
plan_id: mariadb-27
component: mariadb
pr: null                            # No open Renovate PR at plan time (gh: none).
                                    # Hold originates from the auto-update deny-list
                                    # rule "*mariadb*" (max: patch) in
                                    # runbooks/auto-update-policy.yaml — a chart
                                    # major is denied by policy, not by a PR gate.
kind: chart                         # Bitnami mariadb Helm chart (OCI)
current: "25.1.1"                   # appVersion MariaDB 12.2.2
target: "27.0.1"                    # appVersion MariaDB 13.0.1  (TWO chart majors)
update_type: major
risk: high                          # DATA. server-major 12→13 datadir migration is
                                    # ONE-WAY (no MariaDB downgrade); rollback = restore
                                    # the Longhorn volume from backup, not git revert.
est_duration_min: 60
needs_reboot: false                 # pods roll in place; no node reboot
touches:
  namespaces: [databases]
  resources:
    - helmrelease/mariadb
    - statefulset/mariadb                 # primary StatefulSet rolls → pod recreate →
                                          # re-pull of floating bitnami/mariadb:latest
    - pod/mariadb-0
    - pvc/mariadb-data-5g                 # existingClaim; longhorn-static, RWO
    - pv/mariadb-data-5g                  # reclaim: Retain
    - service/mariadb
    - ingress/mariadb                     # mariadb.${SECRET_DOMAIN}, internal class, Homepage-registered
    - "longhorn:volume/mariadb-data-5g"   # the datadir volume — its backup is the recovery floor
  shared: []                        # No cluster-wide shared infra perturbed (does NOT
                                    # bump the ingress-controller, cert-manager, cni,
                                    # coredns, or longhorn itself). BUT there is one
                                    # in-namespace data dependent — phpMyAdmin — that
                                    # loses its backend during the roll (see Interference).
depends_on: []
conflicts_with: []                  # nothing competes for the same resources; but do NOT
                                    # co-schedule a phpMyAdmin upgrade in the same window
                                    # (its only backend is this DB) — see Interference.
status: blocked
window: "sat-early:2026-09-12"       # MOVED 2026-08-15 off tue-early:2026-08-25 on CAPACITY,
                                      # not preference: this plan is est 60m and absenty-rebuild
                                      # is 45m, in a 60m window — a 105m overrun. absenty keeps
                                      # the slot (51 fixable CRITICAL, externally exposed).
                                      # Moved to a 90m sat-early rather than another 60m slot so a
                                      # high-risk two-major data-engine bump has 30m of slack;
                                      # 09-12 is the next free sat-early (08-22 kps, 08-29
                                      # app-template, 09-05 longhorn).
                                      # window was MISSED (plan never executed, still draft).
                                    # migration); do NOT co-schedule phpMyAdmin.
auto_execute: false                 # high + data + one-way migration → operator go/no-go always
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
  - docs/sops/longhorn.md
generated: "2026-08-02"
---

# mariadb 25.1.1 → 27.0.1 — Bitnami chart two-major + MariaDB server 12→13

## 1. Summary & why held

**What changes:** the shared `databases/mariadb` HelmRelease
(`kubernetes/apps/databases/mariadb/app/helmrelease.yaml`) chart version
`25.1.1 → 27.0.1`. This is **two chart majors** (25 → 26 → 27) and, per the OCI
chart metadata, bumps the declared **appVersion `MariaDB 12.2.2 → 13.0.1` — a
server major**. The `bitnami` HelmRepository is OCI
(`oci://registry-1.docker.io/bitnamicharts`).

**Why it was held:** the auto-updater's deny-list rule `*mariadb*`
(`max: patch`, reason *"MariaDB chart major (25→26) + bitnami-legacy posture; a
DB-engine bump is never unattended-safe"*) blocks any chart major. That is
correct — this is a stateful DB engine and the change is **irreversible at the
data layer**. This is **not** a false-positive; if anything the hold understates
it (it's two majors + a server major, not one).

**What this DB actually holds / blast radius (contained but real):**
- Databases on the server (verified live): `my_database` (user data) plus the
  MariaDB system DBs (`mysql`, `information_schema`, `performance_schema`, `sys`,
  `test`). There **is** real user data, not just system tables.
- **Only consumer is phpMyAdmin** (`databases/phpmyadmin`,
  `PMA_HOST: mariadb.databases.svc.cluster.local`, root creds from the `mariadb`
  secret). It is the web admin UI onto this DB and has no other backend.
- **Not** the Nextcloud or Paperless databases — those run their **own** bundled
  subchart instances (`nextcloud-mariadb`, `paperless-ngx-mariadb`, both already
  pinned to `bitnamilegacy/mariadb`) and are **untouched** by this plan.

**The breaking changes that make it non-safe (quote + evidence):**

1. **MariaDB server major 12 → 13 is a one-way datadir migration.** Chart 27.0.1
   `appVersion: 13.0.1` (verified via `helm show chart … --version 27.0.1`).
   MariaDB does **not support datadir downgrade** — once a 13.x binary opens and
   upgrades the on-disk system tables, a 12.2.2 binary will refuse to start on
   that datadir. Therefore **a git revert of the chart is NOT a valid rollback
   once the new server has started.** The only real rollback is restoring the
   Longhorn volume from a pre-upgrade backup (§5).

2. **A latent, already-drifted datadir makes the jump riskier than a clean
   12→13.** Live inspection: the running binary is **`12.2.2-MariaDB`**, but the
   datadir marker `/bitnami/mariadb/data/mysql_upgrade_info` reads
   **`10.11.5-MariaDB`** — i.e. `mariadb-upgrade` has **never been run** since the
   floating image drifted the binary 10.11 → 12.2. The system tables are still in
   10.11 format under a 12.2 binary. Pushing a 13.x binary onto a datadir that was
   never upgraded past 10.11 is exactly the scenario that fails to start or corrupts
   system tables. This must be cleaned up (run `mariadb-upgrade` on 12.2.2 first)
   **before** any server-major jump.

3. **Bitnami image posture — no reproducible/reversible free image (Aug 28 2025
   catalog change, [bitnami/charts#35164](https://github.com/bitnami/charts/issues/35164)).**
   After 2025-08-28 the free `docker.io/bitnami/*` catalog is **latest-only,
   hardened**: all versioned tags were moved to `docker.io/bitnamilegacy/*`
   (frozen, no updates). Verified:
   - `docker.io/bitnami/mariadb` free-tier named tags = **only `latest`** (no
     `13.0.1-…`, no `12.2.2-…`; everything else is sha256 digests).
   - `docker.io/bitnamilegacy/mariadb` newest tag = **`12.0.2` (frozen 2025-08-23)**
     — it has **no 12.2.2 and no 13.x**.

   Consequences the executor must internalise:
   - This HelmRelease has **no `image` override** → it inherits the chart default
     `bitnami/mariadb:latest`, a **floating** tag. The live pod is literally running
     `registry-1.docker.io/bitnami/mariadb:latest` (today that resolves to 12.2.2).
     **Any pod roll re-pulls `:latest`** — which will be **whatever MariaDB the
     hardened `latest` is at window time (very likely 13.x)**. So the server-major
     jump can happen on the roll **regardless of the chart version**, and is not
     even fully under our control while the tag floats.
   - There is **no free tag to pin the OLD 12.2.2 back to** for rollback (legacy
     stops at 12.0.2). This is the second reason rollback = **data restore**, not
     image-pin-back.

**Net verdict / recommendation to the window agent:** treat this as an
**operator-decision (go/no-go) plan, not a routine merge.** The safe, GitOps-clean
outcome of the window is most likely **one of**:
  - **(A) Proceed to MariaDB 13** — accept the one-way migration, after a full
    backup + a `mariadb-upgrade` cleanup on 12.2.2, pin the image by **digest** for
    reproducibility, verify data integrity, keep the volume-restore rollback armed. (Steps below cover A.)
  - **(B) Defer the chart bump and first fix the drift** — pin the image to a
    digest so the server stops floating, run `mariadb-upgrade` on 12.2.2, and
    re-evaluate 13 later. (This de-risks the real fragility without the one-way jump.)
  - **(C) Migrate this low-value shared DB off the Bitnami chart** (only phpMyAdmin
    + one small DB depend on it) — out of scope for one window, note for the operator.

Steps §3 execute **Path A** (the full upgrade) because that is what the held PR
represents; Pre-checks §2 include a hard **go/no-go gate** so the window agent
surfaces the decision before mutating anything.

## 2. Pre-checks

Run from repo root (`cd /Users/mu/code/cberg-home-nextgen`). **Every check must
pass; the last one is an explicit operator go/no-go.**

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.1 HR currently Ready on 25.1.1, pod 1/1 Running, 0 restarts
mise exec -- kubectl get helmrelease -n databases mariadb \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# Expected: "True 25.1.1"
mise exec -- kubectl get pod -n databases mariadb-0 \
  -o custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,IMG:.spec.containers[0].image
# Expected: mariadb-0  true  <low>  registry-1.docker.io/bitnami/mariadb:latest

# 2.2 Capture the CURRENT running server version, datadir marker, and the exact
#     image DIGEST behind :latest (needed to pin, and as the rollback reference).
RP=$(sops -d kubernetes/apps/databases/mariadb/app/secret.sops.yaml | awk '/mariadb-root-password:/{print $2}')
mise exec -- kubectl exec -n databases mariadb-0 -c mariadb -- \
  bash -c "mariadb -uroot -p'$RP' -N -e 'SELECT VERSION();'"
# Record. Expected today: 12.2.2-MariaDB
mise exec -- kubectl exec -n databases mariadb-0 -c mariadb -- \
  cat /bitnami/mariadb/data/mysql_upgrade_info
# Record. Expected today: 10.11.5-MariaDB  (the drift — this is why step 3d exists)
mise exec -- kubectl get pod -n databases mariadb-0 \
  -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
# Record the sha256 digest of the CURRENT (12.2.2) image — this is the only way to
# pin/return to 12.2.2 (no free 12.2.2 tag exists). Keep it with this plan.

# 2.3 Baseline the data: per-DB table counts + a consistency check, so a post-
#     upgrade comparison is meaningful.
mise exec -- kubectl exec -n databases mariadb-0 -c mariadb -- bash -c "mariadb -uroot -p'$RP' -N -e \"
  SELECT table_schema, COUNT(*) FROM information_schema.tables
  WHERE table_schema NOT IN ('information_schema','performance_schema') GROUP BY table_schema;\""
# Record the counts. Also confirm phpMyAdmin can reach it right now (open
# phpmyadmin.\${SECRET_DOMAIN} and log in) — baseline so a post-roll failure is attributable.

# 2.4 TWO fresh backups (belt + suspenders). This is the recovery floor for a
#     one-way migration — do NOT proceed without both.
#   (a) Logical dump, streamed OFF the pod to the repo host:
mise exec -- kubectl exec -n databases mariadb-0 -c mariadb -- \
  bash -c "mariadb-dump -uroot -p'$RP' --single-transaction --routines --triggers --events \
           --all-databases" > /tmp/mariadb-pre27-$(date +%Y%m%d).sql
ls -la /tmp/mariadb-pre27-*.sql   # must be non-empty and end with "-- Dump completed"
#   (b) Fresh Longhorn volume backup of the datadir (docs/sops/backup.md):
mise exec -- kubectl create job --from=cronjob/backup-of-all-volumes \
  mariadb-pre27-$(date +%Y%m%d-%H%M) -n storage
mise exec -- kubectl get volume -n storage mariadb-data-5g \
  -o custom-columns=NAME:.metadata.name,ROBUSTNESS:.status.robustness,LAST_BACKUP:.status.lastBackupAt
# Expected: robustness=healthy AND lastBackupAt within the last few minutes.
# RECORD the backup name/timestamp — §5 restores from exactly this.

# 2.5 No in-flight Flux reconcile; zero firing alerts (Watchdog/InfoInhibitor excluded)
mise exec -- flux get helmreleases -A | grep -vE "True|^NAMESPACE"   # empty
mise exec -- flux get kustomizations -A | grep -vE "True|^NAMESPACE" # empty

# 2.6 GO/NO-GO (operator decision, required before Step 3):
#   Confirm the operator intends Path A (proceed to MariaDB 13, accept the one-way
#   migration). If the operator prefers Path B (pin + upgrade, defer 13) or C
#   (migrate off Bitnami), STOP here and record the decision — do not run Step 3.
```

**Go criteria (Path A):** HR Ready on 25.1.1; pod 1/1, low restarts; running
version + datadir marker + current image digest all recorded; data baseline +
phpMyAdmin login captured; **logical dump AND fresh Longhorn backup both
confirmed**; Flux all-Ready; 0 firing alerts; **operator has explicitly approved
the MariaDB 13 one-way migration.** Any failure → stop and surface.

## 3. Steps (Path A — GitOps; cberg-agent executes the git changes)

DB-engine migration = attended per `application-update.md` §Overview. Silence
noise, **disable Flux rollback for the attempt** (a crash-looping migrating pod
must not be auto-rolled back mid-`mariadb-upgrade`), drive it, then restore.

### 3a. Silence rollout noise + active-update marker

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &>/dev/null &
sleep 2
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime(\"%Y-%m-%dT%H:%M:%S.000Z\"))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=3)).strftime(\"%Y-%m-%dT%H:%M:%S.000Z\"))")
curl -s -X POST localhost:9093/api/v2/silences -H "Content-Type: application/json" -d "{
  \"matchers\":[{\"name\":\"namespace\",\"value\":\"databases\",\"isRegex\":false,\"isEqual\":true},
              {\"name\":\"alertname\",\"value\":\"mariadb.*|Kube(Pod|StatefulSet).*\",\"isRegex\":true,\"isEqual\":true}],
  \"startsAt\":\"$NOW\",\"endsAt\":\"$END\",\"createdBy\":\"operator\",
  \"comment\":\"mariadb 25.1.1->27.0.1 (MariaDB 12->13) upgrade — rollout noise. auto-expires 3h\"}"
kill %1 2>/dev/null'

runbooks/update-marker.sh add mariadb databases 3 "25.1.1->27.0.1 chart major + MariaDB 12->13"
```

### 3b. (Path-A cleanup, on 12.2.2 FIRST) Run `mariadb-upgrade` to clear the datadir drift

Before changing any version, bring the datadir marker up to the running 12.2.2
binary so the subsequent 13.x start has a clean, current datadir to migrate from.
This is a pure `mariadb-upgrade` run against the *current* pod — no manifest change:

```bash
RP=$(sops -d kubernetes/apps/databases/mariadb/app/secret.sops.yaml | awk '/mariadb-root-password:/{print $2}')
mise exec -- kubectl exec -n databases mariadb-0 -c mariadb -- \
  bash -c "mariadb-upgrade -uroot -p'$RP' --force"
mise exec -- kubectl exec -n databases mariadb-0 -c mariadb -- \
  cat /bitnami/mariadb/data/mysql_upgrade_info
# Expected now: 12.2.2-MariaDB (marker advanced from 10.11.5). If mariadb-upgrade
# errors, STOP — do not proceed to 13; surface (this is the pre-existing drift biting).
```

### 3c. Disable Flux rollback + pin the image by digest, then bump the chart

Edit `kubernetes/apps/databases/mariadb/app/helmrelease.yaml`:

1. Chart version `25.1.1 → 27.0.1`.
2. Add `upgrade.remediation.retries: 0` + `remediateLastFailure: false` (restore
   `retries: 3` after success).
3. **Pin the image by digest** so the server version is reproducible and does not
   silently float to a *newer* 13.x mid-window. Use the digest of the intended
   target `bitnami/mariadb:latest` (confirm it is a MariaDB 13.x hardened image
   first) under `values.image`:

```yaml
  values:
    image:
      registry: registry-1.docker.io
      repository: bitnami/mariadb
      digest: "sha256:<the-13.x-latest-digest-confirmed-at-window-time>"
    auth:
      usePasswordFiles: false
    # …existing primary/service/ingress values unchanged…
  upgrade:
    cleanupOnFail: true
    remediation:
      retries: 0
      remediateLastFailure: false
```

> Confirm the digest actually is MariaDB 13.x before pinning:
> `mise exec -- crane digest registry-1.docker.io/bitnami/mariadb:latest` (or
> `docker manifest inspect`), and validate its version label. Pinning by digest is
> the only reproducible option — there is no free `13.0.1` **tag**.

Then commit + push:

```bash
cd /Users/mu/code/cberg-home-nextgen
git add kubernetes/apps/databases/mariadb/app/helmrelease.yaml
git diff --cached kubernetes/apps/databases/mariadb/app/helmrelease.yaml   # review
git commit -m "feat(mariadb): update chart ( 25.1.1 → 27.0.1 ) + pin MariaDB 13 image by digest"
git push
```

### 3d. Reconcile and watch the datadir migration to MariaDB 13

```bash
mise exec -- flux reconcile helmrelease -n databases mariadb --with-source
# Watch mariadb-0 restart onto the 13.x image and run its startup migration:
mise exec -- kubectl logs -n databases mariadb-0 -c mariadb -f | grep -iE "upgrad|migrat|version|ready for connections|error|corrupt"
# Success signal: server logs "ready for connections" on 13.x with no upgrade/corruption error.
mise exec -- kubectl rollout status statefulset/mariadb -n databases --timeout=10m
```

**If `helm upgrade` fails `spec.selector … is immutable`** (possible across two
chart majors — StatefulSet selector labels changed): orphan-delete the StatefulSet
so Helm recreates it; the **PVC/PV and datadir are retained**:

```bash
mise exec -- kubectl delete statefulset mariadb -n databases --cascade=orphan
mise exec -- flux reconcile helmrelease -n databases mariadb --force
```
Do **not** delete the PVC/PV. (`persistentVolumeReclaimPolicy: Retain`, but never
rely on that for a delete — see `docs/sops/storage-safety.md`.)

If the pod crash-loops on the migration, do **not** let it thrash — go to §5.

### 3e. Restore rollback guard + clear silence/marker on success

After Verification (§4) is green: set `upgrade.remediation.retries: 3` back,
remove `remediateLastFailure`, commit + push; then
`runbooks/update-marker.sh clear mariadb` and delete the Alertmanager silence.

## 4. Verification

```bash
cd /Users/mu/code/cberg-home-nextgen
RP=$(sops -d kubernetes/apps/databases/mariadb/app/secret.sops.yaml | awk '/mariadb-root-password:/{print $2}')

# 4.1 HR reconciled + Ready on 27.0.1
mise exec -- kubectl get helmrelease -n databases mariadb \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# Expected: "True 27.0.1"

# 4.2 Pod 1/1, server now on 13.x, datadir marker advanced to 13.x
mise exec -- kubectl exec -n databases mariadb-0 -c mariadb -- bash -c "mariadb -uroot -p'$RP' -N -e 'SELECT VERSION();'"
# Expected: 13.0.x-MariaDB
mise exec -- kubectl exec -n databases mariadb-0 -c mariadb -- cat /bitnami/mariadb/data/mysql_upgrade_info
# Expected: 13.0.x-MariaDB

# 4.3 DATA INTEGRITY — table counts match the §2.3 baseline, and every table checks OK
mise exec -- kubectl exec -n databases mariadb-0 -c mariadb -- bash -c "mariadb -uroot -p'$RP' -N -e \"
  SELECT table_schema, COUNT(*) FROM information_schema.tables
  WHERE table_schema NOT IN ('information_schema','performance_schema') GROUP BY table_schema;\""
# Expected: identical to §2.3. Then a physical consistency check on user data:
mise exec -- kubectl exec -n databases mariadb-0 -c mariadb -- bash -c "mariadb-check -uroot -p'$RP' --all-databases --check"
# Expected: every table reports OK (no "corrupt"/"needs upgrade").

# 4.4 The only consumer works: phpMyAdmin connects + lists the databases
#   Open phpmyadmin.${SECRET_DOMAIN}, log in (root creds), confirm `my_database`
#   and its tables render and are queryable. This is the real success signal.
mise exec -- kubectl get pods -n databases -l app.kubernetes.io/name=phpmyadmin   # Running, unchanged

# 4.5 Ingress still serves + Flux/alerts clean
mise exec -- kubectl get ingress -n databases mariadb
mise exec -- flux get helmreleases -A | grep -vE "True|^NAMESPACE"   # empty
```

**Success =** HR Ready on 27.0.1; server + datadir marker on 13.x; §4.3 table
counts identical to baseline and `mariadb-check` all-OK; phpMyAdmin reads
`my_database`; 0 firing alerts.

## 5. Rollback

**Critical: git revert alone is NOT sufficient once the 13.x server has started —
MariaDB has no datadir downgrade.** A 12.2.2 binary will refuse the 13.x-upgraded
datadir. Rollback = **restore the pre-upgrade Longhorn volume** (or logical dump).

### 5a. If the migration failed BEFORE the 13.x server successfully wrote/upgraded the datadir
(e.g. ImagePull, crash before `mariadb-upgrade`): a plain revert is safe.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <bump-commit-sha>   # restores chart 25.1.1 + drops the digest pin
git push
mise exec -- flux reconcile helmrelease -n databases mariadb --with-source
# If helm is wedged pending-upgrade:
mise exec -- helm rollback mariadb <last-deployed-rev> -n databases --wait=false
mise exec -- flux reconcile helmrelease -n databases mariadb --force
```

### 5b. If the 13.x server DID start (datadir is now 13-format) — restore from backup
This is the expected rollback for a genuine migration failure/regression.

```bash
cd /Users/mu/code/cberg-home-nextgen
# 1. Revert the chart+digest to 25.1.1/12.2.2 in git first (so Flux won't re-push 13):
git revert --no-edit <bump-commit-sha> && git push

# 2. Scale the StatefulSet to 0 so nothing holds the volume:
mise exec -- kubectl scale statefulset mariadb -n databases --replicas=0
mise exec -- kubectl wait --for=delete pod/mariadb-0 -n databases --timeout=120s

# 3. Restore the pre-upgrade datadir. PREFERRED: restore the Longhorn volume backup
#    taken in §2.4(b) (docs/sops/backup.md → "Restore from Backup"):
#      Longhorn UI → Backup → mariadb-data-5g → the §2.4 timestamp → Restore
#      (restore as a new volume, then rebind PV/PVC to it — the PV uses
#       volumeHandle: mariadb-data-5g; either restore in-place over the same
#       volume while detached, or repoint the PV volumeHandle to the restored name).
#    This returns the exact 12.2.2 (post-3b, pre-3c) datadir.

# 4. Bring it back up on 12.2.2 (the reverted manifest pins the §2.2 digest / :latest@12.2.2):
mise exec -- flux reconcile helmrelease -n databases mariadb --with-source
mise exec -- kubectl scale statefulset mariadb -n databases --replicas=1
mise exec -- kubectl rollout status statefulset/mariadb -n databases --timeout=10m
```

### 5c. Last-resort: rebuild from the logical dump
If the volume backup is unusable, recreate a fresh 12.2.2 datadir and load
`/tmp/mariadb-pre27-*.sql` from §2.4(a):
```bash
mise exec -- kubectl exec -i -n databases mariadb-0 -c mariadb -- \
  bash -c "mariadb -uroot -p'$RP'" < /tmp/mariadb-pre27-YYYYMMDD.sql
```

**Confirm cluster is back:** HR Ready on 25.1.1; `SELECT VERSION()` = 12.2.2-MariaDB;
§4.3 data-integrity check matches the §2.3 baseline; phpMyAdmin reads
`my_database`. Clear the marker + drop the silence.

## 6. Interference notes

- **Weekday-capable, non-reboot, but HIGH-risk + operator-present.** `needs_reboot:
  false` — pods roll in place. But `risk: high` (one-way data migration) + the §2.6
  go/no-go means this must go to an **operator-present** window with time budget
  (~60 min: dump + Longhorn backup + `mariadb-upgrade` + roll + integrity verify,
  with headroom for a volume restore). Not an unattended slot.
- **`shared: []` but there IS one in-namespace dependent: phpMyAdmin.** phpMyAdmin's
  *only* backend is this DB; it will lose its connection during the pod roll and
  fail while the 13.x server migrates. **Do NOT co-schedule a phpMyAdmin upgrade in
  the same window** (its verification would flap on the DB roll and be misread).
  No cluster-wide infra (ingress-controller, cert-manager, cilium, coredns, longhorn
  itself) is perturbed — this does not touch shared infra beyond its own volume.
- **Not the Nextcloud/Paperless DBs.** Those are separate bundled
  `nextcloud-mariadb` / `paperless-ngx-mariadb` instances (already on
  `bitnamilegacy/mariadb`). A reader must not confuse them with this shared
  `databases/mariadb` — this plan touches only the latter.
- **The floating `:latest` tag is the sharp edge.** With no `image` override the
  server version is not pinned; pinning by **digest** (Step 3c) is mandatory so the
  target 13.x is reproducible and doesn't drift again mid-window. There is **no free
  versioned tag** and `bitnamilegacy` stops at 12.0.2 — so **you cannot pin BACK to
  12.2.2 by tag**; the §2.2 current-image **digest** is the only image reference for
  a 12.2.2 return, and the §2.4 backups are the real rollback.
- **Storage-safety:** the datadir volume `mariadb-data-5g` is `longhorn-static`,
  reclaim `Retain`. Never `kubectl delete` the PVC/PV during any selector-immutability
  workaround — orphan-delete the StatefulSet only (Step 3d). Follow
  `docs/sops/storage-safety.md`.
- **cberg-agent** performs the GitOps edits/commits (3a, 3c, 3e). The
  `mariadb-upgrade` / `mariadb-dump` / `mariadb-check` `kubectl exec` calls and the
  interactive phpMyAdmin checks are the operator-present in-cluster actions; the
  Longhorn restore (§5b) is operator-driven via the Longhorn UI.

---

## 7. Execution log — 2026-08-15 (attempted unattended run) → **BLOCKED, not executed**

Attempted as an unattended run outside the assigned window
(`sat-early:2026-09-12`). **No cluster mutation was performed.** Nothing was
committed to `helmrelease.yaml`; the HelmRelease remains Ready on **25.1.1** and
`mariadb-0` still runs the 12.2.2 image. Backups were taken (read-only side
effect only). Findings below **materially change this plan** and it must be
re-approved by the operator before any future window picks it up.

### 7.1 The plan's central premise is factually wrong — there is NO user data

§1 asserts *"There **is** real user data, not just system tables."* Verified live
tonight — that is **false**:

| schema | tables | data+index |
|---|---|---|
| `my_database` | **0** | — |
| `test` | **0** | — |
| `mysql` | 31 | 3.35 MB |
| `sys` | 101 (views) | 0.03 MB |

`my_database` and `test` are **empty**. All 30 `CREATE TABLE` statements in the
logical dump belong to `mysql` (MariaDB's own system tables). This instance holds
**no application data whatsoever** — it is an empty MariaDB behind a phpMyAdmin
UI. The `risk: high` rating and the entire volume-restore rollback design exist
to protect data that does not exist. **Re-rate before executing.**

### 7.2 The urgent finding — the 12→13 migration is ALREADY ARMED and unguarded

Neither chart version pins the image. `helm template` of **both** 25.1.1 and
27.0.1 renders `registry-1.docker.io/bitnami/mariadb:latest`. Registry inspection:

| reference | digest | image version | built |
|---|---|---|---|
| running `mariadb-0` | `sha256:7156c5d6…` | **12.2.2** | 2026-04-24 |
| `bitnami/mariadb:latest` **today** | `sha256:47bdb03b…` | **13.0.1** | **2026-08-14** |

`:latest` flipped to 13.0.1 **yesterday**. The pod is still on 12.2.2 only
because it has not restarted in 12 days. Therefore **the one-way MariaDB 12→13
datadir migration will fire on the next pod restart from ANY cause** — eviction,
node drain, OOM, Longhorn maintenance, node reboot — with no operator present,
onto a datadir whose `mysql_upgrade_info` marker still reads `10.11.5-MariaDB`.

That is a strictly worse, uncontrolled version of the event this plan exists to
manage. **Path B (pin `image.digest`) is now the urgent action and should be
decided ahead of the chart bump.** Confirmed `image.digest` is a valid key in
both chart versions. The current 12.2.2 digest `sha256:7156c5d6…` is the only
reference that can hold the server at 12.2.2 (no free versioned tag exists).

### 7.3 Risks the plan feared that are RETIRED by evidence

- **StatefulSet selector immutability trap: does NOT apply.** Rendered
  `spec.selector.matchLabels` is byte-identical in 25.1.1 and 27.0.1
  (`instance/name/part-of/component`). Step 3d's `--cascade=orphan` workaround is
  not needed.
- **Values-key breakage: none.** Diff of `helm show values` 25.1.1 → 27.0.1 =
  **0 removed keys**, 4 added (`metrics.auth.*`). Every key this HelmRelease sets
  still exists in 27.0.1.
- **Full rendered-manifest diff = 33 lines**, entirely cosmetic (NetworkPolicy
  `podSelector` narrowed, a whitespace fix, `checksum/configuration`). Same 8
  object kinds both versions.
- **Multi-major skip is NOT unsupported.** Upstream: *"Skipping intermediate
  major or LTS versions is fully supported and tested for standalone servers"* —
  with the caveat that Incompatible Changes must be reviewed for every major in
  between. §1's framing overstates this.

### 7.4 Pre-existing manifest drift found (unrelated to the bump)

- The HelmRelease's `ingress:` block (incl. the `gethomepage.dev/*` annotations)
  is **inert**. The bitnami mariadb chart renders **no Ingress**, and there is no
  `mariadb` Ingress in the cluster. `touches: ingress/mariadb` and verification
  step §4.5 are wrong and would mislead an executor.
- The top-level `service:` block is likewise ignored (the chart reads
  `primary.service`). Neither is caused by this upgrade; both should be cleaned
  up or moved to the correct keys separately.

### 7.5 Why this was not executed unattended (gates that could not be cleared)

1. **§2.6 is an explicit operator go/no-go between Paths A / B / C**, and
   `auto_execute: false`. A generic "run unattended" authorisation does not
   select a strategy — least of all now that 7.1 likely flips the choice.
2. **The documented rollback is not machine-executable.** §5b/§6: *"the Longhorn
   restore (§5b) is operator-driven via the Longhorn UI."* Performing a one-way
   migration without the ability to execute its own rollback is not acceptable.
3. **The success criterion is not machine-verifiable.** §4.4 names an interactive
   phpMyAdmin browser login as *"the real success signal."*
4. **The post-change health gate was unattributable.** Four other agents were
   running concurrently in `monitoring` / `ai`; 4 Kustomizations, 1 HelmRelease
   and 3 pods were not-Ready in those namespaces, so a "0 unhealthy cluster-wide"
   gate could neither be met nor attributed. (`databases` itself was clean:
   11/11 Kustomizations, 7/7 HelmReleases Ready.)
5. **Off-window** — plan was `draft`, scheduled `sat-early:2026-09-12`.

### 7.6 Backups taken (valid for a future window, subject to freshness)

- **Logical dump:** `~/mariadb-backups/mariadb-pre27-20260815-0110.sql` —
  2,490,223 B (2.4 MB), 30 tables, terminates with `-- Dump completed`. Covers
  `--all-databases --single-transaction --routines --triggers --events`.
  Kept **outside the repo** (public repo).
- **Longhorn volume backup:** `mariadb-data-5g` `lastBackupAt`
  `2026-08-14T23:07:39Z`, robustness `healthy`, state `attached` — taken by the
  nightly `storage/backup-of-all-volumes` CronJob ~3 min before the dump. No job
  was created by this run (the `storage` namespace was out of scope).

### 7.7 Recommended next actions for the operator

1. **Decide Path B first, soon** — pin `image.digest` to the running 12.2.2
   image to disarm 7.2. Full (public) digest, for `values.image.digest`:
   `sha256:7156c5d6865f5bcebeac4c7055898c916c445b9cba008a70ed7d608156f89d1f`. Low risk, pure GitOps, `git revert`-able. Note it does
   force one StatefulSet roll, onto the identical image already running.
2. Then re-rate this plan given 7.1 (no user data). With an empty user schema and
   the selector/values risks retired, the realistic options become *"let it go to
   13 deliberately, in-window"* or **Path C** (retire this instance entirely —
   an empty MariaDB whose only consumer is its own admin UI is a candidate for
   deletion rather than a 60-minute high-risk migration).
3. Fix the inert `ingress:` / `service:` blocks (7.4) in a separate change.
