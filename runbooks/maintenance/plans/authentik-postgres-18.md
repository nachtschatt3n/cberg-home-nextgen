---
plan_id: authentik-postgres-18
component: authentik
pr: null                              # no Renovate PR — the HR pin comment ("SAME
                                      # major only") keeps 18.x out of Renovate's
                                      # range; held update tracked as F-94ee84b5
kind: image
current: "17.11-bookworm"
target: "18.6-bookworm"
update_type: major
risk: high                            # the DB IS the SSO: a bad cutover locks every
                                      # Authentik-protected app; planned outage during quiesce
est_duration_min: 60
needs_reboot: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/authentik            # AUTHENTIK_POSTGRESQL__HOST + init-container target (server+worker)
    - deployment/authentik-server      # scaled to 0 for the dump, restarts onto the new DB
    - deployment/authentik-worker
    - "NEW: deployment/authentik-pg + service/authentik-pg (postgres:18.6-bookworm)"
    - "NEW: pvc/authentik-pg-data + pv/authentik-pg-data + longhorn:volume/authentik-pg-data"
    - "statefulset/authentik-postgresql (quiesced source, left RUNNING — it is the rollback)"
    - cronjob/authentik-channels-cleanup   # DB_HOST + client image follow the cutover
    - "ak-outpost-*-forward-auth deployments (10+): auth path DOWN during the quiesce"
  shared: [auth]                       # SSO outage window — every OIDC + forward-auth app
                                       # loses NEW logins while authentik is scaled down
depends_on: []
conflicts_with: [longhorn-1.12.1-engine]   # DB standup/restore must not run under
                                           # storage-engine work; envoy phases (shared: auth)
                                           # run attended outside windows but must not overlap either
security_ref: F-94ee84b5              # the held-update finding (version currency /
                                      # EOL runway driver — no CVE detail belongs here)
status: draft
window: "sat-early:2026-09-19"                 # SCHEDULED 2026-08-18: HIGH risk 60-90m, operator-present weekend slot; cluster-wide SSO outage during quiesce — clear of every plan needing a login to verify
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/authentik.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/storage-safety.md
generated: "2026-08-18"
---

# Authentik — migrate the bundled Postgres 17.11 to a replacement `postgres:18.6-bookworm`

## 1) Summary & why held

PostgreSQL 17 → 18 is a **major** release. Upstream release notes for 18:

> "A dump/restore using pg_dumpall or use of pg_upgrade or logical replication is
> required for those wishing to migrate data from any previous release."

So this is not a tag bump — a `tag: "18.6-bookworm"` edit on the same PVC makes
the server refuse to start ("database files are incompatible with server") and
takes SSO down with no forward path. The HR pins the image with exactly this
warning (`SAME major only: 18.x is a data-dir migration`), which is why the
auto-updater held it.

**Why not in-place `pg_upgrade`.** Two independent blockers:

- The authentik chart (2026.5.6) runs the official image inside a bitnami-style
  layout: `PGDATA=/bitnami/postgresql/data`, data volume mounted at
  `/bitnami/postgresql` (verified on the live StatefulSet). `pg_upgrade` needs
  the *old and new* binaries plus both data dirs visible to one process — not
  possible inside a chart-templated single-image pod.
- The official `postgres:18+` image restructured its layout specifically around
  pg_upgrade-between-*image*-majors: default `PGDATA` moved to
  `/var/lib/postgresql/18/docker` and the volume mount point to
  `/var/lib/postgresql` (docker-library/postgres #1259). That convention is
  incompatible with the chart's `/bitnami/postgresql` mount, so even a
  successful offline pg_upgrade would leave data where the chart can't use it.

**Chosen mechanic: the superset replacement-DB pattern** (executed 2026-08-18,
`95322f1f` + `superset-pg-cutover`): stand up a plain `postgres:18.6-bookworm`
Deployment alongside the bundled DB on a speaking-name `longhorn-static` volume,
quiesce authentik, dump with the **18** client / restore, repoint
`AUTHENTIK_POSTGRESQL__HOST`, and leave the old 17 StatefulSet **running as the
rollback**. The DB is 784 MB (measured), so unlike superset this fits one
90-minute weekend window: standup + restore + cutover together. This also
permanently exits the chart-bundled DB — the next major is a plan like this one
minus the standup.

Decommissioning the old 17 StatefulSet (`postgresql.enabled: false`) is a
**separate follow-up plan after a ~10-day soak** — same reasoning as
`superset-pg-decommission`. Not this window.

Side benefits of 18: `initdb` now enables data checksums by default (the new
volume gets them for free). No PG18 incompatibility touches authentik's usage:
the DB role credential gets created fresh as SCRAM (MD5 is only *deprecated*),
and the Django layer is version-agnostic — authentik 2026.5 supports PG 18.

**Planned outage:** authentik server+worker are scaled to 0 for the consistent
dump (~10–20 min). Every Authentik-protected app (10+ `ak-outpost-*`
forward-auth deployments, all OIDC apps) refuses NEW logins during it; existing
app-side sessions survive. Operator-present weekend window.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) authentik fully healthy before we touch it
mise exec -- flux get hr -n kube-system authentik
mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik   # 3+3+1 Running
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'

# b) FRESH Longhorn backup of the OLD volume (nightly 03:00 cron). If lastBackupAt
#    is not from today, trigger a manual backup via cberg-agent before proceeding.
mise exec -- kubectl get volume -n storage data-authentik-postgresql-0 \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt

# c) record the inventory you must see again on the NEW database (the acceptance test)
mise exec -- kubectl exec -n kube-system authentik-postgresql-0 -- sh -c '
  PGPASSWORD=$(cat /opt/bitnami/postgresql/secrets/SECRET_AUTHENTIK_DB_PASSWORD) \
  psql -U authentik -d authentik -At -c "
    select '\''users='\''||count(*) from authentik_core_user
    union all select '\''groups='\''||count(*) from authentik_core_group
    union all select '\''applications='\''||count(*) from authentik_core_application
    union all select '\''oauth2_providers='\''||count(*) from authentik_providers_oauth2_oauth2provider
    union all select '\''flows='\''||count(*) from authentik_flows_flow
    union all select '\''migrations='\''||count(*) from django_migrations
    union all select '\''tables='\''||count(*) from pg_stat_user_tables;"'

# d) DB size sanity (was 784 MB at planning time; much larger → check the
#    django_channels_postgres_message table before dumping, see §3 step 4)
mise exec -- kubectl exec -n kube-system authentik-postgresql-0 -- sh -c '
  PGPASSWORD=$(cat /opt/bitnami/postgresql/secrets/SECRET_AUTHENTIK_DB_PASSWORD) \
  psql -U authentik -d authentik -At -c "select pg_size_pretty(pg_database_size(current_database()));"'

# e) target image exists (never bump to an unverified tag)
mise exec -- crane digest docker.io/library/postgres:18.6-bookworm
```

## 3) Steps

### Phase A — stand up the replacement DB (additive, no outage)

1. **New manifests** in `kubernetes/apps/kube-system/authentik/app/` — mirror
   the superset standup (`95322f1f`), adapted to the **18 image layout** (mount
   at `/var/lib/postgresql`, image-default `PGDATA=/var/lib/postgresql/18/docker`
   — do NOT set the 17-era `PGDATA=/var/lib/postgresql/data/pgdata`):

   `pg-deployment.yaml`:
   ```yaml
   ---
   # Replacement authentik DB (plan authentik-postgres-18). Runs ALONGSIDE the
   # bundled 17.11 StatefulSet until the post-soak decommission plan retires it.
   # postgres:18+ image layout: volume mounts at /var/lib/postgresql, PGDATA
   # defaults to /var/lib/postgresql/18/docker (docker-library/postgres #1259) —
   # this is what makes the NEXT major an in-place pg_upgrade candidate.
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: authentik-pg
     namespace: kube-system
     labels:
       app: authentik-pg
   spec:
     replicas: 1
     # Recreate: single-replica Deployment on an RWO Longhorn PVC — RollingUpdate
     # would surge a second pod and deadlock on Multi-Attach.
     # See docs/sops/longhorn-rwo-multi-attach.md.
     strategy:
       type: Recreate
     selector:
       matchLabels:
         app: authentik-pg
     template:
       metadata:
         labels:
           app: authentik-pg
       spec:
         containers:
           - name: postgresql
             image: postgres:18.6-bookworm
             imagePullPolicy: IfNotPresent
             ports:
               - containerPort: 5432
                 name: postgresql
             env:
               - name: POSTGRES_USER
                 value: authentik
               - name: POSTGRES_DB
                 value: authentik
               - name: POSTGRES_PASSWORD
                 valueFrom:
                   secretKeyRef:
                     name: authentik-secret
                     key: SECRET_AUTHENTIK_DB_PASSWORD
               # no PGDATA override — 18 image default (18/docker subdir) is the point
               # no --data-checksums needed — enabled by default in PG 18 initdb
             resources:
               requests:
                 cpu: 100m
                 memory: 256Mi
               limits:
                 cpu: 1000m
                 memory: 1Gi
             volumeMounts:
               - name: data
                 mountPath: /var/lib/postgresql
             readinessProbe:
               exec:
                 command: ["/bin/sh", "-c", "exec pg_isready -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\""]
               initialDelaySeconds: 15
               timeoutSeconds: 2
               periodSeconds: 10
             livenessProbe:
               exec:
                 command: ["/bin/sh", "-c", "exec pg_isready -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\""]
               initialDelaySeconds: 30
               timeoutSeconds: 2
               periodSeconds: 10
         volumes:
           - name: data
             persistentVolumeClaim:
               claimName: authentik-pg-data
   ---
   apiVersion: v1
   kind: Service
   metadata:
     name: authentik-pg
     namespace: kube-system
     labels:
       app: authentik-pg
   spec:
     type: ClusterIP
     ports:
       - port: 5432
         targetPort: 5432
         protocol: TCP
         name: postgresql
     selector:
       app: authentik-pg
   ```

   `pg-pv.yaml` / `pg-pvc.yaml` — speaking-name `longhorn-static` per
   `docs/sops/longhorn.md` (Volume = PV = volumeHandle = PVC = `authentik-pg-data`):
   ```yaml
   ---
   apiVersion: v1
   kind: PersistentVolume
   metadata:
     name: authentik-pg-data
   spec:
     capacity:
       storage: 20Gi
     volumeMode: Filesystem
     accessModes: [ReadWriteOnce]
     persistentVolumeReclaimPolicy: Retain
     storageClassName: longhorn-static
     csi:
       driver: driver.longhorn.io
       fsType: ext4
       volumeAttributes:
         numberOfReplicas: "2"
         staleReplicaTimeout: "30"
       volumeHandle: authentik-pg-data
   ```
   ```yaml
   ---
   apiVersion: v1
   kind: PersistentVolumeClaim
   metadata:
     name: authentik-pg-data
     namespace: kube-system
   spec:
     accessModes: [ReadWriteOnce]
     resources:
       requests:
         storage: 20Gi
     storageClassName: longhorn-static
     volumeName: authentik-pg-data
   ```

   `pg-longhorn-volume.yaml` — **NOT registered in kustomization.yaml** (the app
   Kustomization's `targetNamespace: kube-system` would override
   `namespace: storage` and create a broken duplicate — see `docs/sops/longhorn.md`).
   Apply by hand once (delegate to cberg-agent):
   ```yaml
   ---
   apiVersion: longhorn.io/v1beta2
   kind: Volume
   metadata:
     name: authentik-pg-data
     namespace: storage
   spec:
     size: "21474836480"   # 20 Gi
     numberOfReplicas: 2
     dataEngine: v1
     accessMode: rwo
     frontend: blockdev
     migratable: false
     encrypted: false
   ```

   Register in `kustomization.yaml` (`./pg-deployment.yaml`, `./pg-pv.yaml`,
   `./pg-pvc.yaml` — the PV is cluster-scoped, unaffected by `targetNamespace`).

2. **Apply the Longhorn Volume by hand, then commit + push** (on `main`, stage
   only these files):
   ```bash
   mise exec -- kubectl apply -f kubernetes/apps/kube-system/authentik/app/pg-longhorn-volume.yaml
   mise exec -- kubeconform -summary -ignore-missing-schemas kubernetes/apps/kube-system/authentik
   git add kubernetes/apps/kube-system/authentik/app/pg-deployment.yaml \
           kubernetes/apps/kube-system/authentik/app/pg-pv.yaml \
           kubernetes/apps/kube-system/authentik/app/pg-pvc.yaml \
           kubernetes/apps/kube-system/authentik/app/pg-longhorn-volume.yaml \
           kubernetes/apps/kube-system/authentik/app/kustomization.yaml
   git commit -m "feat(authentik): stand up replacement postgres 18.6 alongside the bundled 17.11 (plan authentik-postgres-18, no cutover yet)"
   git push
   ```

3. **Verify the standby** before starting the outage phase:
   ```bash
   mise exec -- kubectl get pvc -n kube-system authentik-pg-data          # Bound
   mise exec -- kubectl rollout status deploy/authentik-pg -n kube-system --timeout=300s
   PGPOD=$(mise exec -- kubectl get pods -n kube-system -l app=authentik-pg -o jsonpath='{.items[0].metadata.name}')
   mise exec -- kubectl exec -n kube-system $PGPOD -- psql -U authentik -d authentik -c 'select version();'   # 18.6
   ```
   If the standby is not healthy: **stop here** — nothing has been touched,
   there is no outage, retry another window.

### Phase B — quiesce, dump/restore, cutover

4. **Marker** (a real outage is expected):
   ```bash
   runbooks/update-marker.sh add authentik kube-system 2 "authentik DB migration to postgres 18.6 (SSO down during consistent dump)"
   ```
   *Optional, if pre-check (d) showed the DB ballooned:* run the channels
   cleanup once before dumping — `mise exec -- kubectl create job -n kube-system
   ak-cleanup-predump --from=cronjob/authentik-channels-cleanup` and wait for
   Complete. It only deletes expired ephemeral messages.

5. **Quiesce authentik** so the dump is consistent (live cluster action —
   delegate to cberg-agent). SSO outage starts NOW:
   ```bash
   mise exec -- kubectl scale deploy/authentik-server deploy/authentik-worker -n kube-system --replicas=0
   mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik   # only authentik-postgresql-0 remains
   ```
   Leave the `ak-outpost-*` deployments alone — they just fail-closed until the
   server returns.

6. **Dump with the NEW (18) client against the old server** — upstream
   recommends the newer `pg_dump` for a major migration — then keep an off-pod
   copy:
   ```bash
   PGPOD=$(mise exec -- kubectl get pods -n kube-system -l app=authentik-pg -o jsonpath='{.items[0].metadata.name}')
   mise exec -- kubectl exec -n kube-system $PGPOD -- sh -c \
     'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h authentik-postgresql -U authentik -Fc authentik -f /tmp/ak17.dump && ls -l /tmp/ak17.dump'
   # not zero bytes. Off-pod safety copy:
   mise exec -- kubectl cp kube-system/$PGPOD:/tmp/ak17.dump /tmp/authentik-pg17-$(date +%F).dump
   ls -l /tmp/authentik-pg17-*.dump
   ```

7. **Restore into 18** from a clean schema:
   ```bash
   mise exec -- kubectl exec -n kube-system $PGPOD -- \
     psql -U authentik -d authentik -c 'drop schema public cascade; create schema public;'
   mise exec -- kubectl exec -n kube-system $PGPOD -- sh -c \
     'pg_restore -U authentik -d authentik --no-owner --no-privileges /tmp/ak17.dump' 2>&1 | tail -30
   ```
   **Read the output.** Ownership/extension warnings are benign; any `error:`
   line is not — **stop and roll back** (§5, cheap path: just scale authentik
   back up; nothing has been repointed yet).

8. **Compare old vs new before repointing anything**:
   ```bash
   mise exec -- kubectl exec -n kube-system $PGPOD -- psql -U authentik -d authentik -c 'analyze;'
   mise exec -- kubectl exec -n kube-system $PGPOD -- psql -U authentik -d authentik -At -c "
     select 'users='||count(*) from authentik_core_user
     union all select 'groups='||count(*) from authentik_core_group
     union all select 'applications='||count(*) from authentik_core_application
     union all select 'oauth2_providers='||count(*) from authentik_providers_oauth2_oauth2provider
     union all select 'flows='||count(*) from authentik_flows_flow
     union all select 'migrations='||count(*) from django_migrations
     union all select 'tables='||count(*) from pg_stat_user_tables;"
   # must equal pre-check (c) exactly. Mismatch → STOP, do not repoint, roll back.
   ```

9. **The cutover commit** — one commit, hunk-scoped, on `main`:
   - `kubernetes/apps/kube-system/authentik/app/helmrelease.yaml`:
     - `AUTHENTIK_POSTGRESQL__HOST: "authentik-pg"` (BOTH `server.env` and `worker.env`)
     - both `wait-for-postgresql` init containers: `nc -z authentik-pg 5432`
       (and the echo text)
     - update the `postgresql.image` pin comment: the bundled 17.11 block stays
       (it is the rollback) but note "SUPERSEDED by authentik-pg
       (postgres 18.6) since <date>; decommission = follow-up plan"
   - `kubernetes/apps/kube-system/authentik/app/cronjob-channels-cleanup.yaml`:
     - `image: postgres:18.6-alpine@sha256:<resolve + verify at execution time>`
       **Keep the ALPINE base and the digest pin** — this job was deliberately
       moved off the Debian base in `99640b4c` (`security_ref: F-31aadd6f`), and
       every image in this repo is digest-pinned (float-tag batch `cfda3ea8`).
       Writing `18.6-bookworm` here would silently revert both.
     - **Do NOT change `command:`** — it is `/bin/sh` and the script is POSIX
       sh. Alpine ships no bash; reverting the base or the interpreter breaks
       the job. Only the MAJOR/MINOR tracks the server; the base intentionally
       diverges (see the comment in the manifest and in `helmrelease.yaml`).
     - `DB_HOST: "authentik-pg"`
   ```bash
   git add -p kubernetes/apps/kube-system/authentik/app/helmrelease.yaml \
              kubernetes/apps/kube-system/authentik/app/cronjob-channels-cleanup.yaml
   git commit -m "feat(authentik): cut over to postgres 18.6 (authentik-pg); bundled 17.11 kept running as rollback"
   git push
   ```
   Leave `postgresql.enabled: true` — the old DB must keep running.

10. **Reconcile now** (justified deviation from webhook-only flow: authentik is
    scaled to 0 and every minute of waiting extends the SSO outage — this is
    the medium/high path of `docs/sops/application-update.md`):
    ```bash
    mise exec -- flux reconcile source git flux-system
    mise exec -- flux reconcile kustomization authentik -n kube-system
    mise exec -- flux reconcile hr authentik -n kube-system
    mise exec -- kubectl rollout status deploy/authentik-server -n kube-system --timeout=600s
    mise exec -- kubectl rollout status deploy/authentik-worker -n kube-system --timeout=600s
    ```
    The helm upgrade restores `replicas: 3` on both Deployments with the new
    env — no manual scale-up needed. SSO outage ends here.

11. Clear the marker only after §4 passes: `runbooks/update-marker.sh clear authentik`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) THE first check — pods really talk to the new host
mise exec -- kubectl exec -n kube-system deploy/authentik-server -- printenv AUTHENTIK_POSTGRESQL__HOST   # authentik-pg
mise exec -- kubectl exec -n kube-system deploy/authentik-worker -- printenv AUTHENTIK_POSTGRESQL__HOST   # authentik-pg

# b) pods healthy, no DB/migration errors (server runs Django migrations on boot —
#    same authentik version, so expect "no migrations to apply", not a schema change)
mise exec -- kubectl get pods -n kube-system -l app.kubernetes.io/instance=authentik   # 3+3 back, plus authentik-pg + old postgresql-0
mise exec -- kubectl logs -n kube-system deploy/authentik-server --since=15m | grep -iE 'error|migrat|could not connect' | head -20
mise exec -- kubectl logs -n kube-system deploy/authentik-worker --since=15m | tail -20

# c) data intact — same inventory as pre-check (c), now on authentik-pg;
#    old DB idle (it is the rollback — do not stop it)
PGPOD=$(mise exec -- kubectl get pods -n kube-system -l app=authentik-pg -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n kube-system $PGPOD -- psql -U authentik -d authentik -At -c \
  "select count(*) from pg_stat_activity where datname='authentik' and usename='authentik';"    # > 0 (server+worker)
mise exec -- kubectl exec -n kube-system authentik-postgresql-0 -- sh -c '
  PGPASSWORD=$(cat /opt/bitnami/postgresql/secrets/SECRET_AUTHENTIK_DB_PASSWORD) \
  psql -U authentik -d authentik -At -c "select count(*) from pg_stat_activity where datname='\''authentik'\'' and state='\''active'\'';"'   # ~0

# d) health endpoints
DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "https://auth.$DOM/-/health/live/"    # 200
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "https://auth.$DOM/-/health/ready/"   # 200

# e) outposts reconnected (they were never restarted — verify, don't assume)
mise exec -- kubectl get pods -n kube-system | grep ak-outpost                      # all Running, low restarts
mise exec -- kubectl logs -n kube-system deploy/ak-outpost-longhorn-forward-auth --since=10m | tail -5   # websocket re-established, no auth errors

# f) THE load-bearing check is human — a restored-but-wrong SSO DB is invisible
#    at pod level. Operator, end-to-end, in a fresh private browser window:
#      1. https://auth.$DOM — log in as your normal user (password + MFA).
#         Confirm your user, groups and the application tiles all survived.
#      2. FORWARD-AUTH path: open an ak-outpost app (e.g. Longhorn or Headlamp)
#         → redirected to Authentik → login → lands in the app.
#      3. OIDC path: open an OIDC app (e.g. Grafana or Immich) and complete the
#         provider login. This exercises client_id/secret + grant_types straight
#         from the restored DB (the ≥2026.5 blueprint grant_types trap lives in
#         provider rows — a failure HERE means restored config, not the pg major).
```

Success = both Deployments on `authentik-pg`, 3+3 Ready, inventory identical to
pre-check, old DB idle but running, health endpoints 200, outposts connected,
and the operator smoke test passing on BOTH the forward-auth and OIDC paths.

## 5) Rollback

**Before step 9 (nothing repointed):** scale back and walk away —
```bash
mise exec -- kubectl scale deploy/authentik-server deploy/authentik-worker -n kube-system --replicas=3
```
(or `flux reconcile hr authentik -n kube-system`, which restores the declared
replicas). The old DB was only read; the standby can be wiped and retried later.

**After the cutover commit:** the old database is still running and holds the
data exactly as of the quiesce — nothing could write to it while authentik was
scaled to 0, so the revert is lossless *except* sessions/audit events written to
the new DB after step 10 (users re-login; minutes of events):
```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <cutover-commit-sha>       # HOST back to authentik-postgresql (HR + cronjob)
git push
mise exec -- flux reconcile source git flux-system
mise exec -- flux reconcile kustomization authentik -n kube-system
mise exec -- flux reconcile hr authentik -n kube-system
mise exec -- kubectl rollout status deploy/authentik-server -n kube-system --timeout=600s
mise exec -- kubectl exec -n kube-system deploy/authentik-server -- printenv AUTHENTIK_POSTGRESQL__HOST   # authentik-postgresql
# then re-run §4 d–f against the OLD stack (health 200 + one end-to-end login).
```
Leave the Phase A standup manifests in place (additive, idle, harmless) for the
retry; note the failure on the plan and set `status: blocked`.

**Recovery floor** (only if the old DB is somehow damaged): restore Longhorn
volume `data-authentik-postgresql-0` from the pre-check backup per
`docs/sops/backup.md` + `docs/sops/longhorn.md`; `/tmp/authentik-pg17-*.dump` is
a second, independent copy of the same data.

**Storage safety:** this plan deletes NO PVC. Everything created is
`longhorn-static` + `Retain`; both volumes involved are Longhorn (not CIFS), so
the share-wipe failure mode does not apply — but run the
`docs/sops/storage-safety.md` pre-flight anyway if any later cleanup proposes
deleting `data-authentik-postgresql-0`.

## 6) Interference notes

- **`shared: [auth]` — this window blocks logins cluster-wide.** During the
  quiesce (~10–20 min) every OIDC app and all 10+ `ak-outpost-*` forward-auth
  apps refuse NEW logins; a failed cutover extends that until the revert lands.
  **Never co-schedule with any plan that needs a login to verify itself, or that
  touches ingress/auth** — in particular the envoy-gateway phases
  (`shared: [auth, dns]`, attended/out-of-window, but must not overlap in time
  either).
- **`conflicts_with: longhorn-1.12.1-engine`** — this plan creates a Longhorn
  volume and does a DB restore; no storage-engine work in the same window.
- **`kube-system` is the cluster's most loaded namespace** (cilium, coredns
  live there too). This plan touches neither, but vet any other kube-system
  plan sharing the window.
- **Do NOT fold the decommission in.** The bundled 17.11 StatefulSet stays
  running as the one-line rollback; a follow-up plan (superset-pg-decommission
  shape, ~10-day soak) flips `postgresql.enabled: false` later. That follow-up
  must ALSO migrate the monitoring wiring still keyed to the old names:
  `prometheusrule.yaml` (volume `data-authentik-postgresql-0` growth alerts) and
  `kube-prometheus-stack/app/authentik-alerts.yaml`
  (`up{job="authentik-postgresql"}`) — until then those alerts stay valid
  because the old DB stays up.
- **Outposts are deliberately untouched.** No authentik *server* version change
  happens here, so the managed-outpost auto-bump gap
  (`project_authentik_outpost_upgrade`) does not apply — do not delete or
  restart outpost Deployments; they reconnect on their own (§4e verifies).
- The `authentik-channels-cleanup` CronJob (every 6 h) must not fire mid-dump:
  its schedule (0:00/6:00/12:00/18:00) misses the 05:00/09:00 window starts, but
  if the window slips near a boundary, suspend it first
  (`kubectl patch cronjob ... -p '{"spec":{"suspend":true}}'`) and un-suspend
  after — it is part of the cutover commit either way.
- Expected alerts during the quiesce: AuthentikDown-class + blackbox probes on
  `auth.<domain>` and possibly forward-auth-protected probe targets. The
  update-marker (§3 step 4) tells the alert-triage-agent they are planned.
