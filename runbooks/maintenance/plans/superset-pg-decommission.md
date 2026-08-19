---
plan_id: superset-pg-decommission
component: superset
pr: null
kind: chart
current: "bundled bitnamilegacy/postgresql 14.17.0 still running (idle) alongside the live postgres:17.11-alpine"
target: "postgresql.enabled:false — the archived-registry image is gone from the namespace"
update_type: major
risk: medium                          # removes the rollback path; the live DB is not touched
est_duration_min: 30
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - helmrelease/superset             # postgresql.enabled: false
    - "REMOVES: statefulset/superset-postgresql + its service"
    - pvc/superset-postgresql-data     # RETAINED, not deleted (see §3 step 5)
    - "longhorn:volume/superset-postgresql-data"   # kept + final backup
  shared: []
depends_on: [superset-pg-cutover]
conflicts_with: []
status: draft
window: "sat-early:2026-09-05"                 # RESHUFFLED 2026-08-16 onto the daily-window cadence
                                      # (7 windows/week, was 4). Deliberate soaks are
                                      # preserved, not compressed — see the windows YAML.
auto_execute: false
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/storage-safety.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
generated: "2026-08-15"
---

# Superset stage 4/4 — retire the bundled `bitnamilegacy` Postgres

## 1) Summary & why held

Final stage. Superset has been running on `postgres:17.11-alpine` since
`superset-pg-cutover` (`sat-early:2026-09-12`); the old bundled Postgres has been
sitting idle as the rollback. This stage turns it off, which is what actually
clears **F-937701ef** from the namespace — the finding does not close until the
image stops running.

**Scheduled 10 days after the cutover, deliberately.** The soak is the point: any
metadata problem that survived verification (a missing saved query, a lost role, a
dashboard nobody opened during the window) shows up in normal use, and while the old
DB exists the fix is a one-line revert. After this stage, recovery is
restore-from-dump/backup.

**What this stage does NOT do: it does not delete data.** `postgresql.enabled: false`
removes the StatefulSet; the PVC `superset-postgresql-data` and its PV
(`persistentVolumeReclaimPolicy: Retain`) and Longhorn volume are **kept**. Reclaiming
that 20Gi is a separate, later, explicitly-decided cleanup — not window work, and not
worth the risk of doing it in the same breath as the cutoff.

**Ordering caution.** This is also the stage that asserts the whole migration is
complete: after it, **no `bitnamilegacy` image may remain in the `databases`
namespace for Superset**. If `superset-redis-official` (stage 1) has not run, that
assertion fails — the Redis half is still on the archived registry.

## 1a) FIDELITY AUDIT OF THE CUTOVER — done 2026-08-19, result: CLEAN

This plan deletes the source. Before that is acceptable, the cutover it follows
has to be shown faithful, not merely complete — see
`docs/sops/verification-contents-not-shape.md` §2a, added the same day after a
sibling migration was rolled back for a dump that was lossy while every row
count matched.

Audited retrospectively against the live pair while both were still up (the old
server is still running, which is what made a true A/B possible):

| check | old | new |
|---|---|---|
| encoding | UTF8 | UTF8 |
| collation | `en_US.UTF-8` | `en_US.utf8` (same collation, different spelling) |
| rows carrying multi-byte characters | **3** | **3** |
| `md5(string_agg(slice_name order by id))` | `7de3fadd…` | `7de3fadd…` — identical |
| `dashboards` / `tables` text md5 | identical | identical |
| slice names, row-for-row with ids | byte-identical | byte-identical |

**Conclusion: no transcoding or truncation occurred. The cutover is faithful and
this plan may proceed on that basis.**

One methodological note, because it nearly produced a false alarm: the first
comparison used `string_agg(name order by name)` and returned *different*
hashes over byte-identical data. The two images spell the collation differently,
so `ORDER BY` on text sorted the multi-byte values differently and changed the
concatenation order. **Order by the primary key, not by the text you are
hashing.** A fidelity check that false-alarms costs nearly as much as one that
misses — it burns the rollback window chasing a phantom.

**Re-run the multi-byte and md5 rows above immediately before the delete**, not
just once here. They are cheap, and this plan's whole risk is that the source
disappears afterwards.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) the cutover really is live and has soaked
mise exec -- kubectl exec -n databases deploy/superset -- printenv DB_HOST        # superset-pg
mise exec -- kubectl get deploy -n databases superset-pg \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"  ready="}{.status.readyReplicas}{"\n"}'
mise exec -- kubectl get pods -n databases | grep superset                        # note ages/restarts

# b) THE gate — the old DB has been idle since the cutover, i.e. nothing quietly
#    reconnected to it
mise exec -- kubectl exec -n databases superset-postgresql-0 -- psql -U superset -d superset -At -c "
  select coalesce(sum(numbackends),0) from pg_stat_database where datname='superset';"
mise exec -- kubectl exec -n databases superset-postgresql-0 -- psql -U superset -d superset -At -c "
  select xact_commit, xact_rollback from pg_stat_database where datname='superset';"
# Near-zero backends. If something IS connected, find out what before removing it.

# c) the LIVE database still matches what the cutover verified, plus normal growth
NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n databases $NEW -- psql -U superset -d superset -At -c "
  select 'dashboards='||count(*) from dashboards
  union all select 'slices='||count(*) from slices
  union all select 'saved_query='||count(*) from saved_query
  union all select 'dbs='||count(*) from dbs
  union all select 'ab_user='||count(*) from ab_user;" | tee /tmp/superset-decom-before.txt
#    KEEP this file — §4(c) diffs against it. "Counts look about right" is not a
#    comparison; a recorded baseline is (docs/sops/verification-contents-not-shape.md).
#    Values must be >= the cutover's numbers (normal growth is fine, shrinkage is not).

# d) FINAL dump + fresh backup of the DB you are about to switch off. This replaces
#    the running instance as the recovery floor, so it is mandatory.
mise exec -- kubectl exec -n databases superset-postgresql-0 -- \
  pg_dump -U superset -Fc superset > /tmp/superset-legacy-final-$(date +%F).dump
ls -l /tmp/superset-legacy-final-*.dump                                            # not zero bytes
mise exec -- kubectl get volume -n storage superset-postgresql-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUST:.status.robustness,LASTBACKUP:.status.lastBackupAt
# require lastBackupAt within the hour. Store the dump somewhere that survives /tmp.

# e) stage 1 landed (otherwise the "no bitnamilegacy left" assertion in §4 will fail)
mise exec -- kubectl get pods -n databases -o json | python3 -c "
import sys, json
for p in json.load(sys.stdin)['items']:
    if 'superset' in p['metadata']['name']:
        for c in p['spec']['containers']: print(p['metadata']['name'], c['image'])"

# f) no in-flight reconcile
mise exec -- flux get kustomizations -A | awk 'NR==1 || $5!="True"'
```

## 3) Steps

1. **Marker**:
   ```bash
   runbooks/update-marker.sh add superset databases 1 "retire bundled bitnamilegacy postgres (data retained)"
   ```
2. **Disable the bundled Postgres** in
   `kubernetes/apps/databases/superset/app/helmrelease.yaml` — replace the whole
   `postgresql:` values block with:
   ```yaml
       # Bundled Bitnami postgres retired 2026-09-22. bitnamilegacy is an ARCHIVED
       # registry (last push 2025-08-28; security driver F-937701ef; chart 0.22.4 pins
       # bitnamilegacy/postgresql:14.17.0-debian-12-r3 itself, so no chart bump can
       # fix it). The metadata DB is now postgres:17.11-alpine — pg-deployment.yaml
       # in this folder — reached via DB_HOST in superset-secrets.
       postgresql:
         enabled: false
   ```
3. **Keep the old storage declarations.** Do **not** remove `pv.yaml`,
   `data-pvc.yaml` or `longhorn-volume.yaml` for `superset-postgresql-data` from the
   folder or from `kustomization.yaml` in this stage. The PVC becomes unbound-from-a-pod
   but stays; that is intended.
4. **Render-check + validate before pushing**:
   ```bash
   cd /tmp && rm -rf ssdec && mkdir ssdec && cd ssdec
   curl -sSL -o s.tgz https://github.com/apache/superset/releases/download/superset-helm-chart-0.22.4/superset-0.22.4.tgz
   tar xzf s.tgz
   cd /Users/mu/code/cberg-home-nextgen
   mise exec -- yq '.spec.values' kubernetes/apps/databases/superset/app/helmrelease.yaml \
     | sed 's/\${SECRET_DOMAIN}/example.invalid/g' > /tmp/ssdec/values.yaml
   mise exec -- helm template superset /tmp/ssdec/superset -n databases -f /tmp/ssdec/values.yaml \
     | grep -c 'bitnamilegacy' || echo "no bitnamilegacy in the render (expected)"
   mise exec -- kubeconform -summary -exit-on-error -ignore-missing-schemas kubernetes/apps/databases/superset
   ```
5. **Commit + push** (on `main`, stage only this file):
   ```bash
   git add kubernetes/apps/databases/superset/app/helmrelease.yaml
   git commit -m "feat(superset): retire bundled bitnamilegacy postgres (metadata DB now postgres 17.11)"
   git push
   ```
   Flux removes the `superset-postgresql` StatefulSet and Service. The RUNNING pods do
   not restart on account of `DB_HOST` — theirs did not change.

   **But the no-restart claim was materially wrong about this plan's blast radius, and
   was corrected 2026-08-19 (found by the post-cutover doc audit). Do not run this plan
   until the step below is done.** The chart's `wait-for-postgres` init container gets
   **only** the chart-generated `superset-env` Secret — `superset-secrets` reaches the
   main containers, not the init containers — and `superset-env.DB_HOST` is still
   `superset-postgresql`, because `superset.db.host` in `_helpers.tpl` coalesces
   `.Values.database.host` first and falls through to `<release>-postgresql`:

   ```bash
   mise exec -- kubectl get secret -n databases superset-env     -o jsonpath='{.data.DB_HOST}' | base64 -d   # superset-postgresql  <- STALE
   mise exec -- kubectl get secret -n databases superset-secrets -o jsonpath='{.data.DB_HOST}' | base64 -d   # superset-pg
   mise exec -- kubectl get deploy -n databases superset -o jsonpath='{.spec.template.spec.initContainers[0].envFrom}'
   ```

   The init container opens `/dev/tcp/$DB_HOST/$DB_PORT`, loops for 120 s, then
   `exit 1`. While the old Service exists the gate passes and nothing is visible. **The
   moment this plan deletes that Service, every subsequent restart of `superset`,
   `superset-worker` and `superset-celerybeat` fails** — a latent outage armed by the
   stage-3 cutover, detonated by stage 4. The same init block is injected into the
   `superset-init-db` post-upgrade hook Job, so the hook that runs *during* this very
   upgrade is a candidate to hang on it too.

   **Required, BEFORE `postgresql.enabled: false`** — set the DB equivalent of the
   `cache.host` fix the HelmRelease already carries for Redis (added for exactly this
   trap during the 2026-08-17 redis cutover):

   ```yaml
   # kubernetes/apps/databases/superset/app/helmrelease.yaml, under spec.values
   database:
     host: superset-pg
   ```

   Land it as its own commit and let it settle, **not** folded into the decommission
   commit: it is a `spec.values` change, so it fires the `superset-init-db` post-upgrade
   hook, and you want that hook to run while the old Service is still up and the
   rollback is still one revert away. Then assert before proceeding:

   ```bash
   mise exec -- kubectl get secret -n databases superset-env -o jsonpath='{.data.DB_HOST}' | base64 -d   # superset-pg
   mise exec -- kubectl delete pod -n databases -l app.kubernetes.io/name=superset   # deliberate restart: prove the init gate passes
   mise exec -- kubectl rollout status deploy/superset -n databases --timeout=600s
   ```

   Only once a *deliberately restarted* Superset comes up clean is it safe to remove the
   old Service. If it does restart during the decommission itself, that is the reloader
   reacting to the release; confirm it comes back on `superset-pg`.
6. Clear the marker: `runbooks/update-marker.sh clear superset`.

## 4) Verification

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) the old StatefulSet is gone, the app is unaffected
mise exec -- kubectl get sts -n databases | grep superset-postgresql || echo "old STS gone (expected)"
mise exec -- kubectl get pods -n databases | grep superset
mise exec -- kubectl exec -n databases deploy/superset -- printenv DB_HOST         # superset-pg

# b) THE assertion this whole migration exists for — no archived-registry image left
mise exec -- kubectl get pods -n databases -o json | python3 -c "
import sys, json
bad = []
for p in json.load(sys.stdin)['items']:
    for c in p['spec'].get('initContainers', []) + p['spec']['containers']:
        if 'bitnamilegacy' in c['image']:
            bad.append((p['metadata']['name'], c['image']))
print('bitnamilegacy images still running:', bad or 'NONE')"
# Expect NONE for the superset stack. (Other apps — nextcloud-mariadb,
# paperless-ngx-mariadb, the one unpinned office/ mariadb image — are out of scope here and
# are their own hygiene item; note them, do not fix them in this window.)

# c) CONTENTS ASSERTION — the data is still there, DIFFED against the recorded
#    baseline, and still served. Turning off the old server must not perturb the
#    live one; "the numbers look plausible" is not a comparison.
NEW=$(mise exec -- kubectl get pods -n databases -l app=superset-pg -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n databases $NEW -- psql -U superset -d superset -At -c "
  select 'dashboards='||count(*) from dashboards
  union all select 'slices='||count(*) from slices
  union all select 'saved_query='||count(*) from saved_query
  union all select 'dbs='||count(*) from dbs
  union all select 'ab_user='||count(*) from ab_user;" > /tmp/superset-decom-after.txt
diff /tmp/superset-decom-before.txt /tmp/superset-decom-after.txt \
  && echo "IDENTICAL to the pre-check baseline"
# Any output: STOP. This step only disables a server nothing was using — a count
# that MOVED means something was still reading or writing it, i.e. pre-check (b)
# was wrong. Revert (§5) before investigating.

DOM=$(mise exec -- kubectl get secret -n flux-system cluster-secrets -o jsonpath='{.data.SECRET_DOMAIN}' | base64 -d)
curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "https://superset.$DOM/health"     # 200
# `/health` 200 is the FLOOR, not the assertion: Superset answers 200 against an
# empty metadata DB just as happily (this is the paperless-db failure shape).
# Operator, LOAD-BEARING: log in, open a dashboard and confirm the panels paint
# REAL NUMBERS, and run a saved query. Same smoke test as the cutover.

# d) the retained data is genuinely retained (this is the recovery floor now)
mise exec -- kubectl get pvc -n databases superset-postgresql-data     # still present
mise exec -- kubectl get pv superset-postgresql-data \
  -o jsonpath='{.spec.persistentVolumeReclaimPolicy}{"\n"}'           # Retain
mise exec -- kubectl get volume -n storage superset-postgresql-data \
  -o custom-columns=NAME:.metadata.name,STATE:.status.state,LASTBACKUP:.status.lastBackupAt

# e) the CVE finding actually closes
mise exec -- trivy image postgres:17.11-alpine --severity CRITICAL --ignore-unfixed | tail -20
```

Success = old StatefulSet gone, no `bitnamilegacy` image running for Superset, HR
Ready, **the row-count diff against the pre-check baseline silent** and a dashboard
rendering real data in the browser, and the old PVC/PV/Longhorn volume still present
with `Retain` and a fresh backup.

## 5) Rollback

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <decommission-commit-sha>    # postgresql.enabled: true
git push
mise exec -- kubectl get pods -n databases | grep superset-postgresql   # StatefulSet returns
mise exec -- kubectl exec -n databases superset-postgresql-0 -- psql -U superset -d superset -c 'select 1;'
```

The StatefulSet re-binds the retained PVC `superset-postgresql-data`, so the old
database comes back with its data as of the moment it was switched off. **Note what
this rollback does and does not give you:** it restores the *old* server, but Superset
still points at `superset-pg` (`DB_HOST` was not changed by this stage). To fall all
the way back, also revert the `superset-pg-cutover` commit — and accept that anything
written since the cutover lives only in the new DB.

If the retained volume were ever lost, restore from the final dump taken in
pre-check (d) or from the Longhorn backup of `superset-postgresql-data`
(`docs/sops/backup.md`, `docs/sops/longhorn.md`).

**Storage safety:** everything here is `longhorn-static` with `Retain`. This plan
performs **no PVC deletion of any kind**. If a later cleanup proposes deleting
`superset-postgresql-data`, run the `docs/sops/storage-safety.md` pre-flight first —
and note it is a Longhorn volume, not a CIFS/SMB class, so the catastrophic
share-wipe failure mode does not apply, but the data is still gone.

## 6) Interference notes

- **Out of order:** running this before `superset-pg-cutover` deletes the database
  Superset is actively using — an immediate outage plus a restore-from-backup. This
  is the one stage in the set whose out-of-order failure is genuinely destructive;
  the window agent must treat `depends_on` as hard.
- **This stage removes the cheap rollback for the cutover.** That is its cost and the
  reason for the 10-day gap. Do not compress it into the cutover window.
- The `databases` namespace still hosts other `bitnamilegacy` users
  (`nextcloud-mariadb`, `paperless-ngx-mariadb`, and one unpinned
  `bitnamilegacy/mariadb:latest` floating tag under `office/` — both office Redis
  instances left the registry 2026-08-18/19). They are
  **out of scope** for this plan set and should get their own hygiene item — at
  minimum a pin. Do not opportunistically fix them in this window.
- Superset's chart stays at 0.22.4. The chart hold (AR-050 class) and its
  immutable-selector delete-recreate requirement are untouched by this plan set.
