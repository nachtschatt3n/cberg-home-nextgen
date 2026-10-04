---
plan_id: actual-budget-26.10.0
component: actual-budget
pr: null                              # no Renovate PR; surfaced by coverage.py needs_plan_groups (single)
kind: image
current: "26.9.0"                     # measured live 2026-10-04: deploy/actual-budget image + GET /info build.version
target: "26.10.0"                     # Docker Hub tag pushed 2026-10-02T15:02Z, amd64+arm64
update_type: minor
risk: low                             # server side has NO new migration; the only one-way edge is client-side (see §1, §5)
est_duration_min: 25
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/actual-budget       # the single edited line: values.controllers.main.containers.main.image.tag
    - deployment/actual-budget        # strategy Recreate, replicas 1 (verified live)
    - service/actual-budget           # not edited; sole endpoint flaps during the Recreate
    - httproute/actual-budget         # not edited; envoy-internal, LAN-only
    - pvc/actual-budget-data          # RWO longhorn-static 5Gi; server-files/account.sqlite + user-files/*
    - pv/actual-budget-data           # Retain; never modified
    - "volume/actual-budget-data (ns storage, Longhorn CR — read only)"
  shared: [monitoring]                # §4 reads Prometheus (kube-state-metrics series)
depends_on: []
conflicts_with:
  - app-template-5.2.1                # bumps the chart on every app-template HR incl. office/actual-budget
  - helm-drift-detection              # adds spec.driftDetection to every HR incl. this one
  - flux-reconciler-impersonation     # exclusive; rewires the identity every HR reconcile runs under
  - flux-oci-chart-sources            # rewrites HR chart sources across ns office
  - flux-fleet-0.60.0                 # helm-controller restart mid-rollout makes the reconcile un-attributable
  - longhorn-1.13.0                   # exclusive; storage engine under pvc/actual-budget-data
  - talos-linux-1.14.2                # exclusive; node roll
exclusive: false
security_ref: F-1b82b7ea              # security driver for the bump; detail stays on the record
capability_change: true              # 26.10.0 ships user-visible features (in-app Notifications page with
                                      # release highlights, experimental redesigned sidebar, API additions
                                      # e.g. mergeTransactions) — not a same-behaviour bump
rollback_class: backup-restore        # a bare `git revert` is not sufficient once a 26.10 browser client has
                                      # opened the budget: the 26.9.0 client hard-refuses a DB carrying the
                                      # new migration id (out-of-sync-migrations); see §5
backup_gate: "Before the tag edit is pushed (§3.1): a tar.gz of /data (.migrate, server-files/, user-files/) streamed out of the running 26.9.0 pod with set -o pipefail to ~/backups/actual-budget/pre-26.10.0/data.tgz, gated on gzip -t, a 10 MB byte floor (measured 18,061,559 B on 2026-10-04), the member list containing server-files/account.sqlite and every user-files/file-*.blob + group-*.sqlite present live, and a sha256 manifest of every blob + account.sqlite that matches the live sha256sum taken in the same step. Secondary: the nightly Longhorn Backup CR for actual-budget-data (label backup-volume=actual-budget-data) in state Completed with backupCreatedAt < 24h."
restore_proof: "§3.1d: the tarball is extracted locally and every artefact is OPENED, not just listed — sqlite3 'pragma integrity_check' prints exactly 'ok' on account.sqlite and every group-*.sqlite; every file-*.blob passes unzip -t and its inner db.sqlite passes integrity_check AND its __migrations__ max(id) is < 1788468782000 (proves the restored blob is loadable by a 26.9.0 client, which is the exact property the rollback needs); the extracted blob sha256 equals the live baseline. The single-member restore command used in §5.3 was dry-run against this tarball on 2026-10-04 (gzip -dc | tar -xf - user-files/file-<id>.blob reproduced the live sha256)."
finding_refs: [F-1b82b7ea, F-df87279b]  # queried 2026-10-04 (`finding list --grep actual`): security driver + the version row for this exact bump.
                                        # F-dda0af9f (chart 5.1.0 -> 5.2.1) belongs to app-template-5.2.1, not here.
review: null
status: draft
window: null
premises:
  - id: live-image-still-26.9.0
    why: "`current:` claims 26.9.0 and the §3.1 baselines are taken from that pod. Any other live tag means this plan is stale or already done."
    run: kubectl get deploy -n office actual-budget -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: actualbudget/actual-server:26.9.0
  - id: git-pin-still-26.9.0
    why: "The §3.2 sed must change exactly one line; if main moved, the edit is empty and §5.1's revert target is wrong."
    run: "git show HEAD:kubernetes/apps/office/actual-budget/app/helmrelease.yaml | grep -c 'tag: \"26.9.0\"'"
    expect_exact: "1"
  - id: strategy-recreate
    why: "Single replica on an RWO Longhorn PVC; anything but Recreate risks a Multi-Attach hang (docs/sops/longhorn-rwo-multi-attach.md)."
    run: kubectl get deploy -n office actual-budget -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: helmrelease-ready
    why: "Do not stack a bump on an already-failing release."
    run: kubectl get helmrelease -n office actual-budget -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: pvc-bound
    why: "All state lives on this claim; §3.1 streams it out."
    run: kubectl get pvc -n office actual-budget-data -o jsonpath='{.status.phase}'
    expect_exact: Bound
  - id: volume-healthy
    why: "The secondary rollback (§5.4) is a Longhorn backup restore; do not proceed on a degraded volume."
    run: kubectl get volume -n storage actual-budget-data -o jsonpath='{.status.robustness}'
    expect_exact: healthy
  - id: backup-recurringjob-present
    why: "The secondary backup_gate leg reads the nightly Backup CR produced by this RecurringJob."
    run: kubectl get recurringjob -n storage daily-backup-all-volumes -o jsonpath='{.spec.task}'
    expect_exact: backup
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-04"
---

# actual-budget 26.9.0 -> 26.10.0

## 1. Summary & why held

One-line image bump of `actualbudget/actual-server` in
`kubernetes/apps/office/actual-budget/app/helmrelease.yaml` (app-template
5.1.0, chart unchanged). Security-driven: `security_ref: F-1b82b7ea` (detail on
the finding record, not here).

**Hold reason (coverage G3 structural signal) — examined against the upstream
diff `v26.9.0..v26.10.0` of github.com/actualbudget/actual:**

1. `packages/ci-actions/src/news-feed/parse.ts NEWS_FEED_SCHEMA_VERSION` —
   `@actual-app/ci-actions` is a private GitHub-Actions helper package. It is
   not part of the server runtime. **False positive.**
2. `packages/loot-core/migrations/1788468782000_add_messages_pending.js` —
   **real, but client-side and additive.** loot-core migrations are applied to
   the *budget* SQLite by the client (browser) when it opens a budget, not by
   the sync server at boot. The migration body is a single
   `CREATE TABLE IF NOT EXISTS messages_pending (dataset, row, column, timestamp, value, PRIMARY KEY(dataset,row,column))`
   — an internal, non-synced table (per the new upstream
   `packages/loot-core/migrations/README.md`: "newer migrations are
   additive-only"). It adds no synced column, so sync messages written by a
   26.10 client remain readable by a 26.9 client.
3. **Server-side migrations: none added.** The only change in
   `packages/sync-server/migrations/` is `1694360000000-create-folders.js` ->
   `.ts`. Upstream handled the persisted title explicitly
   (`src/migrations.ts::loadMigrationModules`: "Migration titles are persisted
   in .migrate. Keep their original .js titles when source files are converted
   to TypeScript", with a test). Live `/data/.migrate` records
   `1694360000000-create-folders.js` and `lastRun: 1763873600000-backfill-files-owner.js`,
   which is still the last server migration in 26.10.0 — so boot should print
   `Migrations: DONE` with nothing to run.
4. Other server-relevant deltas: `better-sqlite3` ^12 -> ^13 (native module,
   same SQLite file format), new optional `ACTUAL_OPENID_CLIENT_SECRET_FILE` /
   `ACTUAL_GITHUB_TOKEN_FILE` env support (we set neither). Release notes list
   no breaking changes and no Node bump.

**Where it IS one-way (why `rollback_class: backup-restore`):** the 26.9.0
client's `checkDatabaseValidity` throws `out-of-sync-migrations` when a budget
DB has more applied migration ids than it knows. Once any browser loads the
26.10 web app and opens the budget, (a) that browser's local copy carries id
`1788468782000`, and (b) `cloudStorage.possiblyUpload()` (every 7 days per
`UPLOAD_FREQUENCY_IN_DAYS`) may push the migrated DB into
`/data/user-files/file-<id>.blob`. After that a plain image revert leaves a
budget the old client refuses to open. Measured: the active blob was last
rewritten 2026-04-19, so (b) is infrequent in practice — but the plan must not
depend on that.

**Capability:** 26.10.0 adds user-visible features (Notifications page,
experimental sidebar, API additions), so `capability_change: true` -> this
plan derives HUMAN-GATED regardless of `risk: low`.

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py --require-premises actual-budget-26.10.0   # must PASS all 7
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
kubectl get helmrelease -n office actual-budget                                     # Ready True, chart 5.1.0
kubectl get pod -n office -l app.kubernetes.io/name=actual-budget -o wide           # 1/1 Running
# Secondary backup leg: newest nightly Backup CR, must be Completed and < 24h old
kubectl get backups.longhorn.io -n storage -l backup-volume=actual-budget-data \
  --sort-by=.status.backupCreatedAt \
  -o 'custom-columns=NAME:.metadata.name,STATE:.status.state,CREATED:.status.backupCreatedAt' | tail -1
```
If the Backup CR is missing/older than 24h, continue only if §3.1 passes in
full (it is the primary rollback artefact); note it in the window report.

## 3. Steps

### 3.1 Baseline + backup (primary rollback artefact) — BEFORE any edit

```bash
set -o pipefail
B=~/backups/actual-budget/pre-26.10.0; mkdir -p $B/x
# a) stream /data out of the running 26.9.0 pod
kubectl -n office exec deploy/actual-budget -- tar -C /data -czf - .migrate server-files user-files > $B/data.tgz \
  && gzip -t $B/data.tgz && echo GZ_OK
stat -f %z $B/data.tgz        # must be > 10000000 (measured 18,061,559 B on 2026-10-04)
tar -tzf $B/data.tgz          # must list server-files/account.sqlite + every live user-files/* entry
# b) sha256 baseline, live, same moment
kubectl -n office exec deploy/actual-budget -- sh -c 'sha256sum /data/user-files/*.blob /data/server-files/account.sqlite' | tee $B/sha256.live
# c) app-level baselines
kubectl -n office port-forward svc/actual-budget 15006:5006 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://127.0.0.1:15006/info | tee $B/info.before            # build.version "26.9.0"
curl -s http://127.0.0.1:15006/account/needs-bootstrap | tee $B/bootstrap.before   # "bootstrapped":true
kill $PF 2>/dev/null
# d) RESTORE PROOF — open every artefact, not just list it
tar -C $B/x -xzf $B/data.tgz
for db in $B/x/server-files/account.sqlite $B/x/user-files/group-*.sqlite; do
  echo "$db $(sqlite3 "$db" 'pragma integrity_check')"; done                    # each must print ...  ok
sqlite3 $B/x/server-files/account.sqlite 'select id, deleted from files order by id' | tee $B/files.before
for g in $B/x/user-files/group-*.sqlite; do echo "$g $(sqlite3 "$g" 'select count(*) from messages_binary')"; done | tee $B/msgcount.before
for b in $B/x/user-files/file-*.blob; do
  unzip -tq "$b" || echo "BLOB_BAD $b"
  rm -rf $B/z; mkdir $B/z; unzip -q -o "$b" db.sqlite -d $B/z
  echo "$b integrity=$(sqlite3 $B/z/db.sqlite 'pragma integrity_check') maxmig=$(sqlite3 $B/z/db.sqlite 'select max(id) from __migrations__')"
done | tee $B/blobs.before
# PASS: integrity=ok AND maxmig < 1788468782000 for every blob (measured 1762178745667 on both, 2026-10-04)
(cd $B/x && shasum -a 256 user-files/*.blob server-files/account.sqlite)   # hashes must equal $B/sha256.live
```
Failure forms: a truncated stream fails `gzip -t` (pipefail makes a failed
`kubectl exec` non-zero); a corrupt DB prints something other than `ok`; a blob
that a 26.9.0 client could not load shows `maxmig` >= 1788468782000. Any of
these: **STOP**, do not edit.

### 3.2 Edit (dry-tested on a scratch copy with BSD sed, 2026-10-04)

```bash
cd /Users/mu/code/cberg-home-nextgen
sed -i '' 's/tag: "26\.9\.0"/tag: "26.10.0"/' kubernetes/apps/office/actual-budget/app/helmrelease.yaml
git diff kubernetes/apps/office/actual-budget/app/helmrelease.yaml
```
Expected diff (exactly one line, from the dry run):
```
<               tag: "26.9.0"
>               tag: "26.10.0"
```

### 3.3 Commit + push (shared worktree; no SWEEP_PG_DSN in this shell)

```bash
git commit --only kubernetes/apps/office/actual-budget/app/helmrelease.yaml \
  -m "chore(actual-budget): 26.9.0 -> 26.10.0 (plan actual-budget-26.10.0, security_ref F-1b82b7ea)"
git log -1 --format=%s ; git show --stat HEAD     # subject is ours, one file
git push
```
Flux webhook reconciles. Wait for the new pod (Recreate: old pod terminates first):
```bash
kubectl -n office rollout status deploy/actual-budget --timeout=5m
kubectl -n office get pod -l app.kubernetes.io/name=actual-budget \
  -o jsonpath='{.items[0].spec.containers[0].image} {.items[0].status.containerStatuses[0].imageID}{"\n"}'
# must show actualbudget/actual-server:26.10.0 and a digest != sha256:552beab3... (the 26.9.0 digest)
```

## 4. Verification

```bash
B=~/backups/actual-budget/pre-26.10.0
kubectl -n office logs deploy/actual-budget | head -5
# PASS: contains "Migrations: DONE" and "Listening on :::5006"; FAIL form: a migrate
# error/stack ("Missing migration", "Duplicate migration title") before Listening.
kubectl -n office logs deploy/actual-budget | grep -i -c -E 'error|exception'   # expect 0 at boot
kubectl -n office port-forward svc/actual-budget 15006:5006 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://127.0.0.1:15006/info              # PASS: "version":"26.10.0"  (FAIL: "26.9.0" = old pod still serving)
curl -s http://127.0.0.1:15006/health            # PASS: {"status":"UP"}
curl -s http://127.0.0.1:15006/account/needs-bootstrap
# PASS: "bootstrapped":true. FAIL form: "bootstrapped":false = server started on an EMPTY
# /data (PVC not mounted / account.sqlite not found) — the contents-loss case.
kill $PF 2>/dev/null
kubectl -n office exec deploy/actual-budget -- sh -c 'sha256sum /data/user-files/*.blob /data/server-files/account.sqlite' \
  | diff - $B/sha256.live && echo BLOBS_UNCHANGED
```

CONTENTS ASSERTION: the budget data the server holds is byte-identical after the
upgrade — measured by `sha256sum` of every `user-files/file-*.blob` and
`server-files/account.sqlite`, diffed against `$B/sha256.live` from §3.1b
(the server boot path does not write these; a missing file prints
`No such file` and fails the diff). `account.sqlite` may legitimately change if
a user logs in during the window (sessions table) — if it is the ONLY diff line,
re-check with `sqlite3 ... 'select id, deleted from files'` against
`$B/files.before` instead.

CONTENTS ASSERTION: the sync-message log is intact and not shrunk — stream the
group DBs out again and assert `messages_binary` count per group is
**>= the `$B/msgcount.before` value and > 0** (measured 201,947 on the active
group 2026-10-04):
```bash
mkdir -p $B/after && kubectl -n office exec deploy/actual-budget -- tar -C /data -czf - user-files \
  | tar -C $B/after -xzf - && for g in $B/after/user-files/group-*.sqlite; do \
  echo "$g $(sqlite3 "$g" 'select count(*) from messages_binary')"; done
```

CONTROL: metric kube_deployment_status_replicas_available — `{namespace="office",deployment="actual-budget"}` must read 1 for 10 min after rollout (measured 1 on 2026-10-04; reads 0 during a crash loop).
CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="office",container="main",pod=~"actual-budget-.*"}` must not increase over the 10 min after rollout (new pod starts at 0).

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PP=$!; sleep 3
for q in 'kube_deployment_status_replicas_available{namespace="office",deployment="actual-budget"}' \
         'increase(kube_pod_container_status_restarts_total{namespace="office",container="main",pod=~"actual-budget-.*"}[10m])'; do
  curl -s --data-urlencode "query=$q" http://127.0.0.1:19090/api/v1/query \
  | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; assert r, 'EMPTY RESULT = no instrument'; print([x['value'][1] for x in r])"
done; kill $PP 2>/dev/null
```
An empty result is treated as FAIL (assert), not as "no restarts".

**Optional, last, and only after all gates above passed:** open
`https://actual.<domain>` in Chrome, log in, open the budget, confirm the
account balances render. This applies the client migration in that browser —
from here §5.3/§5.5 apply on rollback.

## 5. Rollback

### 5.1 Image revert (always)
```bash
git revert --no-edit <sha of §3.3 commit>
git log -1 --format=%s; git show --stat HEAD; git push
kubectl -n office rollout status deploy/actual-budget --timeout=5m
# confirm: /info -> "version":"26.9.0", needs-bootstrap -> "bootstrapped":true (port-forward as in §4)
```

### 5.2 Was server data touched by a 26.10 client?
```bash
kubectl -n office exec deploy/actual-budget -- sh -c 'sha256sum /data/user-files/*.blob' \
  | diff - <(grep '\.blob' $B/sha256.live) && echo NO_BLOB_CHANGED
```
`NO_BLOB_CHANGED` -> server side is back; skip to 5.5. A differing line ->
a 26.10 client uploaded a migrated budget; do 5.3.

### 5.3 Restore the changed blob(s) from the §3.1 tarball (dry-run proven 2026-10-04)
For each differing `file-<id>.blob` only (do NOT restore `group-*.sqlite`: it
holds every edit since the upgrade, and 26.10 wrote no new synced columns into it):
```bash
gzip -dc $B/data.tgz | kubectl -n office exec -i deploy/actual-budget -- \
  tar -C /data -xf - user-files/file-<id>.blob
kubectl -n office exec deploy/actual-budget -- sha256sum /data/user-files/file-<id>.blob   # must equal $B/sha256.live
```
A restored (older) blob is a snapshot; the client replays the group's sync
messages since the blob on download, so post-upgrade edits are not lost.
If `server-files/account.sqlite`'s `files` rows also differ from
`$B/files.before` (beyond sessions), STOP and escalate to the operator with
5.4 as the option — do not overwrite account.sqlite under a running server.

### 5.4 Fallback: whole-volume restore
Restore `actual-budget-data` from the nightly Longhorn Backup identified in §2
per `docs/sops/backup.md`. Loses edits since that backup — operator decision.
Never delete the PV/PVC to do this; `pv/actual-budget-data` has an immutable
`volumeHandle` (see docs/sops/longhorn.md).

### 5.5 Browsers (operator)
Any browser that opened the budget under 26.10 keeps a migrated local copy and
will show an "out of sync migrations" error on 26.9.0. Close the budget and
remove only the LOCAL copy on that device (never "delete from server / all
devices"), then re-open it from the server list.

## 6. Interference notes

- Single namespace, single Deployment, ~1-2 min of downtime during Recreate; no
  other workload reads `actual-budget-data`. LAN-only route on envoy-internal,
  no Authentik in the path, no shared DB.
- `conflicts_with` lists every open plan that rewrites this HelmRelease or its
  reconcile path (app-template chart bump, drift detection, impersonation,
  OCI sources, Flux controllers) plus the exclusive storage/node plans. Running
  `app-template-5.2.1` the same night would make a failed reconcile
  un-attributable; order is free on other nights (no `depends_on`).
- §4 reads Prometheus (`shared: [monitoring]`); the only kube-prometheus-stack
  plan (`kube-prometheus-stack-91.4.1`) is executed, so no conflict entry is
  needed today — add one if a new kps bump plan appears.
- The §3.1 tarball contains financial data in plaintext: it stays in
  `~/backups/actual-budget/` on the Mac mini (mode 700 dir), never in the repo.
  Delete it after the soak (7 days) once the operator confirms the budget opens.
- Window fit: 25 min; HUMAN-GATED (capability_change) — needs an operator GO;
  not reboot-capable work.
