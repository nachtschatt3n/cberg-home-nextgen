---
plan_id: immich-server-3.3.5
component: immich-server
pr: 360                               # Renovate PR #360 (monorepo v3.3.3 -> v3.3.5, moves server+ML) OPEN 2026-10-22. Coverage lane=PLAN: G3 structural signal,
                                      # coverage.py as lane=PLAN: G3 structural signal, a new DB migration file
                                      # server/src/schema/migrations/1792213725597-AddAssetFaceAssetState.ts.
kind: image
current: "v3.3.3"                     # live 2026-10-22: deploy/immich-server image ghcr.io/immich-app/immich-server:v3.3.3,
                                      # pod imageID @sha256:bae7664ff3aa4c2c1fcbdcdd86b40b105643c5f861f3e6a770fc760089f25862
                                      # (== ghcr index digest of v3.3.3, HEAD 2026-10-22), node k8s-nuc14-01.
target: "v3.3.5"                      # ghcr index digest sha256:485d546a2e31d6a8b4db8423fcba5c109de8c218d93410af115fd1ccfc4352a6
                                      # (HEAD manifests/v3.3.5, 2026-10-22). v3.3.5 published 2026-10-21T18:12Z.
update_type: patch
risk: medium                          # forward-only schema migration on the immich DB; the 2026-10-12 incident
                                      # (a844cf8d) proved a plain git revert after migration crash-loops the server.
est_duration_min: 50                  # pre-checks 5 + fresh dump 1 (measured 20 s in-pod, 459 MB gz) + copy-off 2
                                      # + scratch restore-proof ~15 (vector indexes rebuilt; NOT measured, capped at 20)
                                      # + push/Flux/pull/Recreate/migrate ~8 + verification ~10 + slack.
needs_reboot: false
touches:
  namespaces: [media]
  resources:
    - helmrelease/immich-server               # the edit (kubernetes/apps/media/immich/app/helmrelease.yaml, main container tag)
    - deployment/immich-server                # strategy Recreate (live): one pod replaced, ~1-2 min API outage
    - service/immich-server                   # unchanged; endpoints move to the new pod
    - deployment/immich-postgres              # NOT restarted; database `immich` gets the forward migration, and a
                                              # scratch database `immich_restoretest` is created + dropped (restore proof)
    - pvc/immich-pg-data                      # longhorn 20Gi (1.4G used, 19G free 2026-10-22); scratch DB ~1.3G transient
    - pvc/immich-data                         # CIFS cifs-immich-cache: READ only (nightly dumps under /data/backups)
  shared: [igpu-i915, monitoring]             # immich-server requests+limits gpu.intel.com/i915: 1 (QSV) on k8s-nuc14-01;
                                              # Recreate frees then re-claims the slot. §4 reads Prometheus.
depends_on: []
conflicts_with:
  - kube-prometheus-stack-92.11.0     # same instrument (symmetric: that plan lists this one).
  - redis-fleet-8.10.2                # rolls media/immich-redis AND deployment/immich-server; its gates and ours would
                                      # each read the other's Recreate as their own.
  - kube-prometheus-stack-92.2.0      # §4 reads Prometheus (up{job="immich-server"}, ALERTS) — the instrument.
  - kube-prometheus-stack-92.10.1     # same instrument.
  - jellyfin-12.2.20261005            # i915 claimant on the SAME node (k8s-nuc14-01) and same namespace.
  - jellyfin-config-rwo-migration     # i915 claimant in media; two GPU Recreates in one window confound both gates.
  - node-feature-discovery-0.20.0     # a dropped GPU label leaves a RESTARTED i915 pod Pending — our Recreate is exactly that.
  - helm-drift-detection              # rolls the intel-gpu-plugin DaemonSet (i915 re-register under our new pod) and
                                      # changes how helm-controller applies this HR.
  - flux-fleet-0.60.0                 # upgrades helm-controller = this plan's apply AND rollback path.
  - flux-oci-chart-sources            # may move the bjw-s chart source under this HR mid-window.
  - talos-linux-1.14.2                # node roll (exclusive, reboots every node incl. nuc14-03 = immich-postgres).
  - talos-linux-1.14.4                # same.
  - talos-power-tuning-ab             # changes nuc14 thermal/power envelope; immich-server's cpu:4 cap is a thermal bound.
exclusive: false
security_ref: F-6318cd5c              # security driver on the CURRENT server image; detail on the DB record only.
security_driven: true
capability_change: false              # same-behaviour patch train: v3.3.4 = person-query performance fix + a
                                      # translation fix; v3.3.5 = dependency/base-image refresh (CA bundle). The
                                      # migration adds denormalised columns/triggers/an index on asset_face for
                                      # query speed; no new route, permission, API surface or exposure.
rollback_class: backup-restore        # the migration is forward-only for Immich: an older server refuses to start
                                      # against a newer schema ("Downgrades are not supported", observed 2026-10-12).
backup_gate: "§3.1 fresh plain-SQL pg_dump of database immich taken from deploy/immich-postgres AFTER the pre-checks and BEFORE the tag edit is pushed, streamed to $HOME/immich-backups/pre-3.3.5/immich.sql.gz on the Mac under set -o pipefail. PASS = gzip -t ok AND size >= 300000000 bytes (measured 458,994,958 B gzip -1 on 2026-10-22) AND the stream ends with '-- PostgreSQL database dump complete' AND the 'COPY public.' block count equals the live public BASE TABLE count (72 on 2026-10-22, 72 COPY blocks in the 02:00 nightly dump) AND the dump's newest kysely_migrations row is 1790693088454-AddPersonUserTableSharedBySharedWithConstraint. Secondary layers, both premises: Immich's own 02:00 nightly dump of today under /data/backups, and the 23:00Z Longhorn backup of pvc-34a7dcaa-1069-415b-8abb-84da7acf914e (immich-pg-data) FRESH < 26h."
restore_proof: "§3.2: the §3.1 dump is restored into a SCRATCH database immich_restoretest on the same immich-postgres instance (psql -v ON_ERROR_STOP=1, Immich's documented search_path rewrite) and, BEFORE the tag edit is pushed, count(*) of asset, asset_face, person, \"user\", album and library in immich_restoretest must equal the same counts taken from live immich in §2.5, the public BASE TABLE count must be 72, the newest kysely_migrations row must be 1790693088454-AddPersonUserTableSharedBySharedWithConstraint, and \\dx must list vchord and vector. Any mismatch or a psql error = STOP, do not push. The scratch DB is dropped at the end of §3.2 by its exact name (never DROP DATABASE immich here)."
finding_refs: [F-6318cd5c, F-eff49af5]  # F-6318cd5c: security, fixable findings on immich-server:v3.3.3 with newer tag (detail in DB).
                                        # F-eff49af5: version, "immich-server: image ... v3.3.3 -> v3.3.4 (patch)" — this bump
                                        # supersedes its target. Queried 2026-10-22 (`finding list --grep immich`).
                                        # ML findings (F-611ca4c7, F-6d0f4efc) belong to the sibling plan
                                        # immich-machine-learning-3.3.5, not here.
review: ready-for-go@2026-10-22   # plan-reviewer 2026-10-22: needs-fix with 0 blocking (ML-first ordering, helm remediation retries hazard, conflicts) -> fixed; v3.3.5 stable, single forward-only migration, dump+scratch-restore proof; premises 4/4
status: vetted
window: null
premises:
  - id: server-image-is-v3.3.3
    why: >-
      current, the baselines and the "pre-migration" expectation were captured against
      this pin. If the Deployment already moved, this plan is stale (or Step 0 already
      applied it) - stop and re-assess.
    run: |-
      kubectl get deploy -n media immich-server -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "ghcr.io/immich-app/immich-server:v3.3.3"
  - id: server-hr-ready
    why: "A HelmRelease already failing would mask whether the bump itself reconciled."
    run: |-
      kubectl get helmrelease -n media immich-server -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: server-strategy-recreate
    why: >-
      Single replica holding an i915 slot and an RWO-class claim; RollingUpdate would
      start the new pod (and its migration) while the old one still serves.
    run: |-
      kubectl get deploy -n media immich-server -o jsonpath='{.spec.strategy.type}'
    expect_exact: "Recreate"
  - id: immich-alerts-quiet
    why: "ImmichServerNotReady / ImmichPodCrashLooping must be quiet before the change, or §4 cannot attribute a firing."
    run: |-
      kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=ALERTS%7Balertname%3D~%22ImmichServerNotReady%7CImmichPodCrashLooping%22%2Calertstate%3D%22firing%22%7D'
    expect_contains: '"result":[]'
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/immich.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-22"
---

# immich-server v3.3.3 -> v3.3.5

## 1. Summary & why held

One-line image-tag bump of the Immich server container in
`kubernetes/apps/media/immich/app/helmrelease.yaml` (`controllers.main.containers.main.image.tag`).
The two `busybox:1.38.0` init containers (`wait-for-postgres`, `wait-for-redis`) in the same
pod are **unchanged** and out of scope.

**Security driver:** `security_ref: F-6318cd5c` (detail on the DB record only). This is the
"bump to a newer upstream tag" remediation. Whether the target clears the record completely
was **not measured here** (local Trivy run failed); the next sweep re-rates the finding
against v3.3.5, and anything left waits for a newer upstream tag.

**Upstream evidence** (GitHub releases `immich-app/immich`):
- `v3.3.4` (2026-10-20): "Turns out the last people performance fix wasn't quite there for
  some people. We have now finally resolved that issue." — PR #32523
  `perf(server): more efficient person queries`, plus #32485 (missing translation).
- `v3.3.5` (2026-10-21): "This version contains a fix for today's CA compromise ... we still
  recommend that you update as soon as possible." — #32635 (python docker digests),
  #32636 (certifi). The server Dockerfile moves to base images `202610211607`.

**Why held (G3 structural signal) — a TRUE positive.** `compare v3.3.3...v3.3.5` adds exactly one
migration, `server/src/schema/migrations/1792213725597-AddAssetFaceAssetState.ts`, arriving in
v3.3.4 (it backs PR #32523). Its `up()`:
- `ALTER TABLE "asset_face" ADD "ownerId" uuid / "assetVisibility" asset_visibility_enum / "assetDeletedAt" timestamptz`;
- creates functions `asset_face_set_asset_state()` / `asset_face_update_asset_state()` and
  triggers `asset_face_set_asset_state` (BEFORE INSERT on asset_face),
  `asset_face_update_asset_state` (AFTER UPDATE on asset), and rewrites `asset_face_updatedAt`;
- backfills every row: `UPDATE "asset_face" SET ... FROM "asset" WHERE "asset"."id" = "asset_face"."assetId"`;
- `ALTER COLUMN "ownerId" SET NOT NULL, ALTER COLUMN "assetVisibility" SET NOT NULL`;
- `CREATE INDEX "asset_face_personGroupId_ownerId_assetId_timeline_idx" ... WHERE (...)`, `ANALYZE`;
- five `migration_overrides` rows.

Additive and small here (asset_face = 60,410 rows / 26 MB, asset = 79,034 on 2026-10-22), so the
migration itself should take seconds. The risk is the **rollback**, not the forward step: Immich
never runs `down()` automatically, and an older server refuses a newer schema. That is not
theoretical in this cluster — on 2026-10-12 an auto-revert of v3.3.1 left v3.2.4 crash-looping
on "Downgrades are not supported" (`a844cf8d`, rolled forward). Hence `rollback_class:
backup-restore` with a fresh dump and a scratch-restore proof before the push.

**Coupling with `immich-machine-learning-3.3.5` (sibling plan):** NOT hard-coupled. Between
v3.3.3 and v3.3.5 the `machine-learning/` tree changes only `Dockerfile`, `pyproject.toml`,
`uv.lock` (dependency refresh); no server code that talks to ML changed. A v3.3.5 server
against a v3.3.3 ML (or the reverse during a rollback) is a one-patch skew of the kind that
ran for days in September. The SOP convention is "server and ML pinned identical", so
**prefer the same window, ML first, then server**, but neither plan depends on the other and they do
not conflict (different files, different pods; ML is stateless).

## 2. Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen` (zsh on the Mac mini).

2.1 Premises: `.venv/bin/python3 runbooks/plan-premises.py --require-premises immich-server-3.3.5`
→ all PASS. Any FAIL = do not run.

2.2 Flux sanity, nothing in flight in media:
```bash
flux get helmreleases -n media | grep immich      # all four Ready=True
kubectl get pods -n media -o wide | grep immich   # 4/4 Running
```

2.3 DB disk headroom for the scratch restore (needs > 5G free; 19G on 2026-10-22):
```bash
kubectl exec -n media deploy/immich-postgres -- df -h /var/lib/postgresql/data
```

2.4 No library scan / bulk job running (a backfill under heavy job load is slower and the
counts in 2.5 would drift). Check the microservices log for the last minutes:
```bash
kubectl logs -n media deploy/immich-server -c main --since=10m | grep -ciE 'library.*scan|queue.*active'
```
A non-zero count is not a stop by itself; note it, and treat asset/asset_face as ">= baseline" in §4.

2.5 Baseline counts (keep the output in the window log; §3.2 and §4 compare against it):
```bash
kubectl exec -n media deploy/immich-postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F" " \
  -c "select (select count(*) from asset),(select count(*) from asset_face),(select count(*) from person),(select count(*) from \"user\"),(select count(*) from album),(select count(*) from library)" \
  -c "select count(*) from information_schema.tables where table_schema=\$\$public\$\$ and table_type=\$\$BASE TABLE\$\$" \
  -c "select name from kysely_migrations order by name desc limit 1"' | tee /tmp/immich-baseline.txt
```
Measured 2026-10-22: `79034 60410 2330 2 0 2` / `72` / `1790693088454-AddPersonUserTableSharedBySharedWithConstraint`.

2.6 Checks that the premise runner cannot express (it refuses `kubectl exec`, `$(` and python).
ANY failure = STOP, do not push:
```bash
# (a) DB still at the v3.3.3 head (no v3.3.4+ server ever ran): §2.5 third query must read
#     1790693088454-AddPersonUserTableSharedBySharedWithConstraint. Reads ...AddAssetFaceAssetState = plan is stale.
# (b) today's Immich nightly dump exists (absence also means the job queue is unhealthy):
kubectl exec -n media deploy/immich-server -c main -- ls /data/backups | grep -c "immich-db-backup-$(TZ=Europe/Berlin date +%Y%m%d)T020000-v3.3.3"   # must print 1; 0 = STOP
# (c) Longhorn backup of the immich-pg-data volume under 26h:
.venv/bin/python3 runbooks/longhorn-backup-age.py pvc-34a7dcaa-1069-415b-8abb-84da7acf914e --max-hours 26   # must contain FRESH
```

## 3. Steps

### 3.1 Fresh pre-upgrade dump to the Mac (backup_gate)
```bash
set -o pipefail
mkdir -p "$HOME/immich-backups/pre-3.3.5" && chmod 700 "$HOME/immich-backups"
D="$HOME/immich-backups/pre-3.3.5/immich.sql.gz"
kubectl exec -n media deploy/immich-postgres -- sh -c \
  'pg_dump --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip -1' > "$D" \
  || { echo "DUMP FAILED"; exit 1; }
gzip -t "$D" && echo GZIP_OK
stat -f %z "$D"                                                        # >= 300000000
gunzip -c "$D" | tail -5 | grep -c -- '-- PostgreSQL database dump complete'   # 1
gunzip -c "$D" | grep -c '^COPY public\.'                              # == 72 (2.5 table count)
gunzip -c "$D" | awk '/^COPY public.kysely_migrations /{f=1;next} f&&/^\\\./{exit} f' | sort | tail -1
#   last line must contain 1790693088454-AddPersonUserTableSharedBySharedWithConstraint
```
Any check failing = STOP (no push). Can fail: a truncated stream fails `gzip -t` / the
"dump complete" trailer; a wrong DB prints a COPY count far from 72.

### 3.2 Restore proof into a SCRATCH database (restore_proof)
```bash
set -o pipefail
D="$HOME/immich-backups/pre-3.3.5/immich.sql.gz"
kubectl exec -n media deploy/immich-postgres -- sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE immich_restoretest OWNER \"$POSTGRES_USER\""'
gunzip -c "$D" \
 | sed "s/SELECT pg_catalog.set_config('search_path', '', false);/SELECT pg_catalog.set_config('search_path', 'public, pg_catalog', true);/g" \
 | kubectl exec -i -n media deploy/immich-postgres -- sh -c \
   'psql -U "$POSTGRES_USER" -d immich_restoretest -v ON_ERROR_STOP=1 -q' > /tmp/immich-restoretest.log 2>&1 \
 && echo RESTORE_OK || echo RESTORE_FAILED
kubectl exec -n media deploy/immich-postgres -- sh -c 'psql -U "$POSTGRES_USER" -d immich_restoretest -At -F" " \
  -c "select (select count(*) from asset),(select count(*) from asset_face),(select count(*) from person),(select count(*) from \"user\"),(select count(*) from album),(select count(*) from library)" \
  -c "select count(*) from information_schema.tables where table_schema=\$\$public\$\$ and table_type=\$\$BASE TABLE\$\$" \
  -c "select name from kysely_migrations order by name desc limit 1" \
  -c "select string_agg(extname, \$\$,\$\$ order by extname) from pg_extension where extname in (\$\$vchord\$\$,\$\$vector\$\$)"' \
  | tee /tmp/immich-restoretest.txt
diff <(head -3 /tmp/immich-baseline.txt) <(head -3 /tmp/immich-restoretest.txt) && echo COUNTS_MATCH
grep -c '^vchord,vector$' /tmp/immich-restoretest.txt   # 1
```
PASS = `RESTORE_OK`, `COUNTS_MATCH`, extensions line `1`. Note: the baseline was taken minutes
before the dump; if 2.4 showed active jobs and only `asset_face`/`asset` differ, re-take 2.5
and the restoretest counts back-to-back once; a second mismatch = STOP. A real failure prints
a psql `ERROR:` in `/tmp/immich-restoretest.log` (ON_ERROR_STOP aborts) or a count of 0.
If the restore exceeds 20 min, abort it, drop the scratch DB and STOP (window budget).

Then drop the scratch DB **by its exact name**:
```bash
kubectl exec -n media deploy/immich-postgres -- sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE immich_restoretest"'
```

### 3.3 The GitOps change
Dry-tested on a scratch copy (BSD sed, 2026-10-22); it matches exactly one line:
```bash
sed -i '' 's|^\([[:space:]]*tag: \)v3\.3\.3$|\1v3.3.5|' kubernetes/apps/media/immich/app/helmrelease.yaml
# Helm-remediation guard (see §6): same commit, upgrade block only. Dry-tested on a scratch copy, one diff line: `25c25 <       retries: 3 ---> retries: 0`
sed -i '' '/^  upgrade:/,/^  uninstall:/ s/^\([[:space:]]*retries: \)3$/\10/' kubernetes/apps/media/immich/app/helmrelease.yaml
git diff --stat -- kubernetes/apps/media/immich/app/helmrelease.yaml
```
The HR must show exactly two changed lines (tag, upgrade retries). Resulting tag diff (from the dry run): `77c77 <               tag: v3.3.3  --->               tag: v3.3.5`.
(The ML file uses `tag: v3.3.3-openvino` and is NOT matched — that line belongs to the sibling plan.)

Commit and push (shared worktree):
```bash
git commit --only kubernetes/apps/media/immich/app/helmrelease.yaml \
  -m "fix(immich): immich-server v3.3.3 -> v3.3.5 (plan immich-server-3.3.5; security_ref F-6318cd5c)"
git log -1 --format=%s     # must be the subject above; amend before push if not
git show --stat HEAD       # exactly one file
git push
```
Record the commit SHA as `$BUMP`. Flux webhook reconciles; Recreate replaces the pod; the new
server runs the migration at startup.

## 4. Verification

4.1 Rollout + digest (floor):
```bash
kubectl rollout status deploy/immich-server -n media --timeout=10m
kubectl get pod -n media -l app.kubernetes.io/instance=immich-server \
  -o jsonpath='{.items[0].status.containerStatuses[?(@.name=="main")].imageID}'
```
PASS = imageID ends `sha256:485d546a2e31d6a8b4db8423fcba5c109de8c218d93410af115fd1ccfc4352a6`
(rollout status alone can green-light the old generation).

4.2 CONTENTS ASSERTION: the migration applied and the backfill filled every face —
measured by:
```bash
kubectl exec -n media deploy/immich-postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At \
  -c "select name from kysely_migrations order by name desc limit 1" \
  -c "select count(*) from asset_face where \"ownerId\" is null or \"assetVisibility\" is null" \
  -c "select count(*) from pg_indexes where indexname=\$\$asset_face_personGroupId_ownerId_assetId_timeline_idx\$\$" \
  -c "select count(*) from pg_trigger where tgname in (\$\$asset_face_set_asset_state\$\$,\$\$asset_face_update_asset_state\$\$)"'
```
PASS = `1792213725597-AddAssetFaceAssetState` / `0` / `1` / `2`. Can fail: before the
migration the first line prints the 1790693088454 name and the second query errors
`column "ownerId" does not exist` (live pre-state 2026-10-22).

4.3 CONTENTS ASSERTION: no data lost — counts compared to the 2.5 baseline:
re-run the 2.5 count query; PASS = `person`, `user`, `album`, `library` equal; `asset` and
`asset_face` `>=` baseline (night jobs may add, never remove). Any decrease = rollback.

4.4 API answers as v3.3.5 (unauthenticated endpoint):
```bash
kubectl port-forward -n media svc/immich-server 22830:2283 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s localhost:22830/api/server/version; echo
curl -s localhost:22830/api/server/ping; echo
kill $PF 2>/dev/null
```
PASS = `{"major":3,"minor":3,"patch":5}` and `{"res":"pong"}`.

4.5 No migration/DB errors in the server log since start (case-insensitive). This ABSENCE gate only counts when paired with the positive checks 4.2-4.4 (version 3.3.5, ping, migration head `1792213725597-AddAssetFaceAssetState`); a zero from a crashed/empty log is not a pass.
```bash
kubectl logs -n media deploy/immich-server -c main --since=15m | grep -ciE 'downgrades are not supported|migration.*(fail|error)|QueryFailedError|error: relation|column .* does not exist'
```
PASS = `0`. Can fail: the 2026-10-12 incident printed "Downgrades are not supported".

4.6 Metrics still scraped after the restart:
CONTROL: metric up — `up{job="immich-server"}` returns two series (endpoints `metrics-api`,
`metrics-ms`), both `1`, at a timestamp after the push (measured 2026-10-22: two series, both 1).
```bash
kubectl get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=up%7Bjob%3D%22immich-server%22%7D'
```
CONTROL: metric immich_person_repository_get_all_faces_duration_count — present in the label
index pre-change; post-change PASS = the series query returns a non-empty result (the
person repository is the code path v3.3.4 rewrote; empty = the microservices/API metrics
exporter is not emitting).

4.7 Alerts quiet 10 min after Ready:
CONTROL: alertname ImmichServerNotReady — not firing.
CONTROL: alertname ImmichPodCrashLooping — not firing.
(Same query as the `immich-alerts-quiet` premise; PASS = `"result":[]`.)

4.8 Read-only originals still read-only (SOP T2):
`kubectl exec -n media deploy/immich-server -c main -- touch /libraries/x` → must fail with
`Read-only file system`.

4.9 Post-window: the next sweep re-rates `F-6318cd5c` against v3.3.5; close it with
`policy-cli.py finding close F-6318cd5c --commit $BUMP` only if the sweep agrees.

## 5. Rollback

**Decision first:** if v3.3.5 boots and serves (4.1/4.4 pass) but something minor is off,
**roll forward / leave it** — a DB restore loses the minutes of job output since the dump
and costs ~20 min. Restore only if the server cannot serve on the migrated DB.

**Never just `git revert $BUMP`.** v3.3.3 against the migrated DB crash-loops on
"Downgrades are not supported" (2026-10-12). The rollback is this procedure, in order:

5.1 Stop the server so nothing migrates mid-restore (rollback-only direct actions):
```bash
flux suspend helmrelease immich-server -n media
kubectl scale deploy/immich-server -n media --replicas=0
kubectl get pods -n media -l app.kubernetes.io/instance=immich-server   # none
```

5.2 Replace database `immich` from the §3.1 dump (validated by §3.2):
```bash
set -o pipefail
D="$HOME/immich-backups/pre-3.3.5/immich.sql.gz"
kubectl exec -n media deploy/immich-postgres -- sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE \"$POSTGRES_DB\" WITH (FORCE)" -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\""'
gunzip -c "$D" \
 | sed "s/SELECT pg_catalog.set_config('search_path', '', false);/SELECT pg_catalog.set_config('search_path', 'public, pg_catalog', true);/g" \
 | kubectl exec -i -n media deploy/immich-postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q' \
 && echo RESTORE_OK
```
Then re-run the 2.5 query: PASS = identical to `/tmp/immich-baseline.txt` (newest migration
back to `1790693088454-...`).
Fallbacks if the Mac dump is unusable: today's `/data/backups/immich-db-backup-<today>T020000-v3.3.3-pg14.19.sql.gz`
(same restore pipe via `kubectl exec -n media deploy/immich-server -c main -- cat <file>`), or
the Longhorn backup of `pvc-34a7dcaa-1069-415b-8abb-84da7acf914e` per `docs/sops/backup.md`
(restore to a NEW volume; never delete `immich-pg-data`).

5.3 Revert the tag in git and resume:
```bash
git revert --no-edit $BUMP
git log -1 --format=%s && git show --stat HEAD
git push
flux resume helmrelease immich-server -n media
kubectl get deploy -n media immich-server -o jsonpath='{.spec.replicas}'   # 1; if 0: kubectl scale ... --replicas=1
```

5.4 Confirm back: image `...immich-server:v3.3.3`, imageID `sha256:bae7664f...`,
`/api/server/version` = `{"major":3,"minor":3,"patch":3}`, 4.5 grep = 0, 4.7 alerts quiet,
HR Ready. ML is unaffected by any of this.

Data-loss bound: only DB writes between §3.1 and the restore (face/job results on a
read-only viewer — regenerable by re-queuing jobs). Originals are on a `ro` mount and
never at risk; no PVC is deleted at any point (see `docs/sops/storage-safety.md`).

Cleanup after a successful window (any time later): `rm -rf "$HOME/immich-backups/pre-3.3.5"`
once the plan is executed and soaked 7 days.

## 6. Interference notes

- **Helm remediation hazard (2026-10-12 shape).** `helmrelease.yaml` sets `upgrade.remediation.retries: 3`
  and no `strategy`; the Flux helm-controller default strategy is `rollback`, so a v3.3.5 startup that fails
  (timeout 20m) would make Helm roll the Deployment back to v3.3.3 ON THE ALREADY-MIGRATED DB, where the old
  server refuses to start ("Downgrades are not supported") and the HR flaps. Mitigation (in §3.3): the same
  commit sets `upgrade.remediation.retries: 0`, so a failed upgrade stays failed with the new pod visible
  instead of auto-rolling back. After §4 PASSES, restore `retries: 3` in a follow-up commit (`git revert`-style
  one-line edit, no pod change). If the upgrade fails: do NOT let Flux retry blindly; `flux suspend hr -n media
  immich-server`, then follow §5 (restore the §3.1 dump into `immich`, revert the tag + retries commit, resume).
- **Forward-only DB step.** The window agent must not let Step 0 / auto-update.py batch an
  immich bump into a health-gated batch that can auto-revert (the exact 2026-10-12 failure,
  finding F-2efa3b1f). If Step 0 already applied v3.3.4/v3.3.5 the `server-image-is-v3.3.3`
  premise fails and this plan is stale.
- **Sibling `immich-machine-learning-3.3.5`:** same window preferred, ML first then server, no hard
  dependency, not in `conflicts_with` (stateless, separate file and pod).
- **i915 / nuc14-01:** Recreate frees and re-claims a `gpu.intel.com/i915` slot on
  k8s-nuc14-01 (shared with jellyfin, makemkv, immich-ml). Hence the jellyfin / NFD /
  helm-drift-detection conflicts.
- **thermal:** the `cpu: "4"` limit is a standing thermal bound (SOP §4) — do not touch it.
- **immich-postgres on nuc14-03** takes the scratch restore load (CPU for index builds);
  no other plan in this window should be measuring nuc14-03 thermals.
- **Public route** (`envoy-external`) is unchanged; users see a 1-2 min outage only.
- **Prometheus** is this plan's instrument — kube-prometheus-stack plans conflict.
