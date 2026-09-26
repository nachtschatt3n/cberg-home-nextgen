---
plan_id: authentik-pg17-decommission
component: authentik
pr: null
kind: config
current: "bundled bitnami postgresql 17.11 StatefulSet still RUNNING alongside authentik-pg (18.6), holding the pre-cutover data"
target: "postgresql.enabled: false — the 17.11 StatefulSet and its PVC retired"
update_type: cleanup
risk: medium                          # low blast radius, but it destroys the rollback
est_duration_min: 20
needs_reboot: false
touches:
  namespaces: [kube-system]
  resources:
    - helmrelease/authentik
    - statefulset/authentik-postgresql
    - "pv/data-authentik-postgresql-0 + volumes.longhorn.io/data-authentik-postgresql-0 (PVC deleted 2026-09-24; PV Released + Retain, volume detached — KEPT, not modified by the residual)"
    - "~/db-dumps/authentik-pg17-2026-08-20.dump on the Mac mini (step 5, operator hands)"
    - "cronjob/authentik-db-probe (audit-trail control — NOT modified, but it lives
       in the same kustomization.yaml this plan edits, so a window agent must see it)"
  shared: []
depends_on: []
conflicts_with:
  - authentik-2026.8.3              # its §2.7 requires this plan `executed` first; R1 (forward-auth
                                    # proof) must not straddle its server roll + outpost push
  - wazuh-2xx-edge-coverage         # restarts authentik-server; R1 must not straddle it
  - prometheus-pushgateway-3.9.0    # declared by that plan (pushed authentik_audit_* series); reciprocal
finding_refs: [F-8ab2ee07]
capability_change: false
rollback_class: one-way    # DECLARED 2026-09-06. The plan's own risk note says
                          # it "destroys the rollback": this retires the bundled
                          # 17.11 StatefulSet that still holds the pre-cutover
                          # data and exists precisely as the fallback. Once gone,
                          # recovery is a restore, not a commit. Same shape as
                          # superset-pg-decommission, which used one-way.
                          # Correctly stays HUMAN-GATED, and is awaiting-soak.
status: awaiting-go   # steps 1-4 DONE: 1, 2, 4 in the now:2026-09-24 run (5f162456, AR-080 disabled);
                      # step 3 (PVC delete) by the operator in the coordinating session, PV Released
                      # at 2026-09-24T17:41:36Z (recorded in e6e31d44). RESIDUAL: R1 forward-auth
                      # proof, then R2 = step 5 (dump purge, operator hands) — see "Residual" below.
window: "now:2026-09-26"   # residual R1+R2 only (was sat-attended:2026-09-26; steps 1-4 ran now:2026-09-24)
# auto_execute RETIRED 2026-08-26 (P2.1b) — execution class is now DERIVED
# from capability_change/rollback_class per runbooks/autonomy-policy.yaml.
# (original rationale: destroys the rollback path)
security_ref: null
premises:
  # RESIDUAL-run premises (rewritten 2026-09-26 by plan review). Steps 1-4 are
  # done; these assert the state R1/R2 start from. Pipe-free jq stages
  # (plan-premises splits on | and refuses > <). Each new one was dry-run on
  # 2026-09-26 against a negative control, named in its `why`.
  - id: soak-7d-on-authentik-pg
    why: "Gate 1: authentik-pg has served for >= 7 days (cutover 2026-08-20)."
    run: kubectl get deploy -n kube-system authentik-pg -o jsonpath='{.metadata.creationTimestamp}' | jq -R 'now - fromdate' | jq '. / 86400' | jq floor
    expect_matches: '^([7-9]|[1-9][0-9]+)$'
  - id: every-authentik-pod-uses-authentik-pg
    why: >-
      No server or worker pod still points at the bundled DB. Prints the unique
      set of AUTHENTIK_POSTGRESQL__HOST values; any second value (or none) fails.
    run: kubectl get pods -n kube-system -l app.kubernetes.io/name=authentik -o json | jq -c '.items[].spec.containers[].env[]?' | grep AUTHENTIK_POSTGRESQL__HOST | sort -u
    expect_exact: '{"name":"AUTHENTIK_POSTGRESQL__HOST","value":"authentik-pg"}'
  - id: old-pvc-gone-pv-released-retain
    why: >-
      Step 3 is done: the PVC is deleted (phase Released, not Bound) and the PV
      is still Retain on longhorn-static. Control: the same read on
      pv/authentik-pg-data prints "Bound Retain longhorn-static" and fails.
    run: kubectl get pv data-authentik-postgresql-0 -o jsonpath='{.status.phase} {.spec.persistentVolumeReclaimPolicy} {.spec.storageClassName}'
    expect_exact: Released Retain longhorn-static
  - id: old-volume-detached-and-kept
    why: >-
      The Longhorn volume still exists, detached, and sees its PV as Released.
      Control: volume authentik-pg-data prints "attached Bound" and fails.
    run: kubectl get volume -n storage data-authentik-postgresql-0 -o jsonpath='{.status.state} {.status.kubernetesStatus.pvStatus}'
    expect_exact: detached Released
  - id: old-volume-preflight-backup-completed
    why: >-
      The recovery floor that outlives the dump: the operator's on-demand backup
      of the final state is Completed and belongs to the old volume. Control:
      the unsynced CR backup-3b5a596123494c59 prints "Completed" alone and fails;
      a missing CR fails on NotFound.
    run: kubectl get backups.longhorn.io -n storage authentik-pg17-decommission-preflight-20260926 -o jsonpath='{.status.state} {.status.volumeName}'
    expect_exact: Completed data-authentik-postgresql-0
  - id: new-volume-backed-up-within-26h
    why: >-
      Gate 2: authentik-pg-data has a backup newer than 26h. Reads the VOLUME's
      lastBackupAt, not Backup CR status: on 2026-09-26 the 03:01Z Backup CR was
      Completed with EMPTY status.volumeName/backupCreatedAt, so the previous
      CR-status grep fell back to the day before and FAILED ('26') at 05:07Z on
      a healthy volume. lastBackupAt may lag a cycle, which fails closed.
      Control: a nonexistent volume fails on NotFound.
    run: kubectl get volume -n storage authentik-pg-data -o jsonpath='{.status.lastBackupAt}' | jq -R 'now - fromdate' | jq '. / 3600' | jq floor
    expect_matches: '^([0-9]|1[0-9]|2[0-5])$'
  - id: pg17-dump-still-present
    why: >-
      R2 (step 5) has something to purge; false by design after R2. Control: an
      unmatched glob echoes the literal pattern (with the *), which fails.
    run: echo ~/db-dumps/authentik-pg17-*.dump
    expect_matches: '/db-dumps/authentik-pg17-[0-9-]+[.]dump$'
sops_refs:
  - docs/sops/longhorn.md
  - docs/sops/backup.md
generated: "2026-08-20"
---

# Retire the bundled 17.11 authentik DB

## Residual (updated 2026-09-26) — READ FIRST

Steps 1, 2 and 4 ran in the now:2026-09-24 window: `5f162456` set
`postgresql.enabled: false` (StatefulSet, Services, ConfigMaps gone;
authentik-server/worker templates byte-identical, no restart), rewrote the docs
this plan owns, and AR-080 was disabled. The OIDC path and the audit-trail
probe verified that day.

**Step 3 is ALSO DONE.** The operator deleted PVC `data-authentik-postgresql-0`
in the coordinating session after the storage pre-flight (Longhorn, no subdir,
PV `Retain`, no mounting pod); the PV went `Released` at 2026-09-24T17:41:36Z
(`e6e31d44`). PV and Longhorn volume are kept (Released / detached). The old
volume has 9 Completed backups, newest the operator's on-demand
`authentik-pg17-decommission-preflight-20260926` (2026-09-26 05:02Z), taken
because a detached volume is skipped by the daily job.

Left, in this order, with the operator IN-SESSION (not a relayed GO):

- **R1 — forward-auth proof (Gate 3).** The only login path not yet proven on
  the new DB since the change. Take it BEFORE any authentik roll
  (`authentik-2026.8.3`, `wazuh-2xx-edge-coverage`). The operator logs out,
  then signs in to a forward-auth app in a fresh private window. For that
  app's outpost `<o>` (e.g. `gods-eye-view`):
  ```
  kubectl logs -n kube-system deploy/ak-outpost-<o>-forward-auth --since=30m | grep '"path":"/outpost.goauthentik.io/auth/envoy' | grep -c '"status":200,'
  kubectl logs -n kube-system deploy/ak-outpost-<o>-forward-auth --since=30m | grep '"path":"/outpost.goauthentik.io/auth/envoy' | grep -c '"status":302,'
  kubectl exec -n kube-system deploy/authentik-pg -- psql -U authentik -d authentik -Atc "select created, context->'authorized_application'->>'name' from authentik_events_event where action='authorize_application' and created > now() - interval '30 minutes' order by created desc limit 5"
  ```
  PASS: the 200-count is >= 1 AND the event query lists the forward-auth app.
  The 302-count is the CONTROL and must also be >= 1 (the unauthenticated
  redirect before sign-in): it proves the grep reads this outpost's request
  log. If the control is 0 the query is blind — STOP; never read a 0 as a
  result. Measured 2026-09-26 05:10Z: gods-eye-view had 302s and no 200 in
  40h (no forward-auth sign-in yet); homepage, longhorn and headlamp outposts
  logged no ext-auth request at all in 40h. The 200 line format is NOT yet
  demonstrated; if the app page loads but the 200-count stays 0, the event
  query decides.
- **R2 — step 5** (below), only after R1 passes.

Then `policy-cli.py finding close F-8ab2ee07 --commit <sha>` and status
`executed`. Steps 1, 2 and 4 are idempotent no-ops if re-run; step 3 cannot be
re-run (the PVC is gone) and must not be.


Follow-up to `authentik-postgres-18` (cutover executed 2026-08-20, ~6m43s SSO
outage). The bundled StatefulSet was deliberately left running: it is the
rollback and still holds the pre-cutover data.

**This plan owns the 17.11 pin's disposition, and it is the ONLY thing that may
touch it.** While this StatefulSet exists, `coverage.py` keeps reporting
`authentik image 17.11-bookworm → 18.6-bookworm` as needing a plan — a phantom:
it reads the manifest pin and cannot see that `deployment/authentik-pg` has
served on 18.6 since the cutover. Applying that "bump" would migrate the data
directory of the rollback itself. Do not write a plan for it; retire the
StatefulSet here and the pin (and the phantom) disappear together. Listed in
`README.md` → "Known phantoms"; diagnosed by `F-8ab2ee07`.

## Gate — do not run this early

**This plan's only real risk is running it too soon.** It converts a
one-command rollback into a restore-from-backup. Require all of:

1. **≥7 days** on `authentik-pg` with no auth incident.
2. **The new volume has its own verified Longhorn backup** — not the old one.
   The dump under `~/db-dumps` is the recovery floor until then and must not be
   deleted before this is true:
   ```
   kubectl get volume -n storage authentik-pg-data \
     -o custom-columns=NAME:.metadata.name,LASTBACKUP:.status.lastBackupAt
   ```
3. A login verified through **both** paths on the new DB — an OIDC app
   (Grafana/Superset/Immich/LibreChat) and a forward-auth app — since they fail
   differently.
4. AR-080 (`postgres:17.`) is still enabled while the 17.11 image runs; retiring
   it is part of THIS plan, not the cutover.

## Steps

1. `helmrelease.yaml`: `postgresql.enabled: false`, and delete the superseded
   pin block + its comment. Leave `AUTHENTIK_POSTGRESQL__HOST: authentik-pg`.
2. Push, let Flux reconcile, confirm authentik stays healthy (it is not touching
   the old DB, so this should be a no-op for the app).
3. DONE 2026-09-24 (PV `Released` at 17:41:36Z; recorded in `e6e31d44`): PVC
   `data-authentik-postgresql-0` deleted by the operator after the
   storage-safety pre-flight (Longhorn, no subdir, PV `Retain`). The PV and
   the Longhorn volume are KEPT, detached, as the frozen pre-cutover copy —
   `docs/applications.md`, `docs/sops/authentik.md` and
   `docs/sops/disaster-recovery.md` all say so. NEVER delete its Longhorn
   backups: once step 5 purges the dump they are the only recovery floor for
   the pre-cutover data. Retiring the PV + volume is NOT part of the residual;
   see "Known consequence" for why the operator may still want it.
4. Disable AR-080 (`postgres:17.`) once no 17.11 image runs anywhere.
   AR-112 (`postgres:18.`) stays — it carries the same gosu argument forward.
5. `rm ~/db-dumps/authentik-pg17-2026-08-20.dump` (operator hands). It holds
   password hashes, MFA secrets and session tokens. This removes the live
   plaintext copy on the Mac; it is NOT a secure erase: `-P` is a no-op on this
   macOS (`man rm`: "This flag has no effect"), and `~/db-dumps` is INCLUDED in
   Time Machine (`tmutil isexcluded ~/db-dumps` → `[Included]`; destination the
   NAS `backups` share, hourly local snapshots), so copies persist until Time
   Machine ages them out. The same data also lives, by design, in the kept
   Longhorn backups of `data-authentik-postgresql-0`.
   Verify: `ls ~/db-dumps | grep -c '^authentik-pg17-'` → `0`. The non-zero
   control is premise `pg17-dump-still-present`, read before this step.

## Verification

- `kubectl get sts -n kube-system` — no `authentik-postgresql`.
- authentik still serves logins (both paths again).
- No pod references `authentik-postgresql`:
  `kubectl get pods -n kube-system -o yaml | grep -c authentik-postgresql` → 0.
- **The audit-trail control survived.** This plan edits the same
  `kustomization.yaml` that registers `cronjob/authentik-db-probe`, so a
  fat-fingered resource list can silently delete the only thing asserting the
  audit log is being written — and a dead probe looks exactly like a quiet one.
  Assert positively, not by absence:
  - `kubectl get cronjob -n kube-system authentik-db-probe` still present, and
    its next scheduled Job Succeeds.
  - `authentik_audit_newest_event_timestamp_seconds` still advancing after
    reconcile, and neither `AuthentikAuditFreshnessProbeMissing` nor
    `AuthentikAuditFreshnessProbeStale` firing.
  - This is also the positive proof the plan removed only the ROLLBACK: the probe
    targets `deploy/authentik-pg`, which this plan must not touch. If the metric
    keeps advancing, the live DB was not disturbed.

## Also owned by this plan (do not skip — it prevents a stale warning)

Once the StatefulSet is gone the two-database ambiguity ceases to exist, so the
documentation written for it becomes actively misleading — a reader will go
hunting for a pod that no longer exists. In the SAME change:

- Rewrite `docs/sops/authentik.md` §"Two databases answer to
  `-U authentik -d authentik`" into past tense (or fold it into cutover history).
- Drop the `Rollback DB` row from that SOP's settings table.
- Re-check `docs/sops/disaster-recovery.md` §4.9 and
  `docs/sops/container-dependencies.md` — both were corrected to name
  `authentik-pg` on 2026-09-12 and must not drift back.
- `docs/sops/longhorn.md` cites `data-authentik-postgresql-0` as a UUID-PV
  example; pick a surviving example.

## Rollback

Steps 1-4 are not revertable by commit: `5f162456` also deleted the 17.11
image pin and the `auth`/`primary` blocks, so flipping `postgresql.enabled`
back would render the chart's DEFAULT postgresql image with no
`existingSecret` — not the rollback DB. Recovery of the pre-cutover data is
data-level: restore a kept Longhorn backup of `data-authentik-postgresql-0`
(newest `authentik-pg17-decommission-preflight-20260926`) into a new volume,
or rebind the Released PV (clear `spec.claimRef` first) to a hand-made PVC,
and read it with a scratch `postgres:17` pod. Never point authentik at it: it
is frozen at the 2026-08-20 cutover. Step 5 has no rollback beyond Time
Machine (`~/db-dumps` is included) until those snapshots age out.

## Known consequence — snapshot-chain alert on the kept volume (2026-09-26)

The on-demand backup `authentik-pg17-decommission-preflight-20260926` added a
second snapshot to `data-authentik-postgresql-0` (beside the 2026-09-24 daily
one). The volume is detached and `allow-recurring-job-while-volume-detached`
is `false`, so the 02:30 snapshot cleanup never prunes it. Measured
2026-09-26 05:1xZ: `count by (volume) (longhorn_snapshot_actual_size_bytes{volume="data-authentik-postgresql-0"})`
= 2, its 30h `count_over_time` = 180. `LonghornVolumeSnapshotChainNotPruned`
(30h `min_over_time` >= 2, `for: 30m`) therefore starts firing around
2026-09-27 11:30Z and stays firing while the volume is kept — the
superset-postgresql-data shape (F-ec968c4d). The operator decides at GO and
the choice is recorded here before status `executed`:
- (a) keep PV + volume (the documented intent) and accept the alert under a
  scoped, recorded suppression; or
- (b) retire the PV + Longhorn volume in a follow-up (Longhorn backups survive
  a volume delete; recovery is then "restore the kept backup into a new
  volume", as above) and update the three docs that say "kept".
The volume's `recurring-job-group.longhorn.io/default` label is harmless (the
job skips detached volumes); do not edit it under this plan.
