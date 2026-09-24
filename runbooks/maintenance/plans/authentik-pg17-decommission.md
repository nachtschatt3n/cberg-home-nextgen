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
    - "pvc/data-authentik-postgresql-0 (Longhorn, keep Retain)"
    - "cronjob/authentik-db-probe (audit-trail control — NOT modified, but it lives
       in the same kustomization.yaml this plan edits, so a window agent must see it)"
  shared: []
depends_on: []
conflicts_with: []
capability_change: false
rollback_class: one-way    # DECLARED 2026-09-06. The plan's own risk note says
                          # it "destroys the rollback": this retires the bundled
                          # 17.11 StatefulSet that still holds the pre-cutover
                          # data and exists precisely as the fallback. Once gone,
                          # recovery is a restore, not a commit. Same shape as
                          # superset-pg-decommission, which used one-way.
                          # Correctly stays HUMAN-GATED, and is awaiting-soak.
status: awaiting-go   # 2026-09-24: gates 1, 2 encoded as premises (gate 3 is the post-step login check, gate 4 AR-080 is enabled);
                      # operator asked for the StatefulSet AND the PVC to go (2026-09-23). Soak long satisfied.
window: "sat-attended:2026-09-26"   # slotted 2026-09-24 so awaiting-go is valid; operator asked for it now, so a NOW run may take it first
# auto_execute RETIRED 2026-08-26 (P2.1b) — execution class is now DERIVED
# from capability_change/rollback_class per runbooks/autonomy-policy.yaml.
# (original rationale: destroys the rollback path)
security_ref: null
premises:
  # Gates 1-4 of the plan body, machine-checked (added 2026-09-24; pipe-free jq
  # stages because plan-premises splits on | and refuses > <). Run ONCE,
  # before step 1: after step 1 the StatefulSet is gone and premise 3's PVC
  # read fails by design.
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
  - id: no-other-pod-references-the-old-db
    why: >-
      Nothing else in the cluster (probes, cronjobs, apps) carries the old
      service name in its env. Counts pods other than the StatefulSet's own.
    run: kubectl get pods -A -o json | jq -c '.items[]' | grep -v '"name":"authentik-postgresql-0"' | grep -c authentik-postgresql
    expect_exact: "0"
  - id: old-volume-retain-and-backed-up-within-26h
    why: >-
      Gate for deleting the PVC in the same run: the old volume is Retain on
      longhorn-static AND has a Completed Longhorn backup newer than 26h (the
      daily 03:00 job plus slack). Without it the PVC stays one more cycle.
    run: kubectl get backups.longhorn.io -n storage -o json | jq -c '.items[].status' | grep '"volumeName":"data-authentik-postgresql-0"' | grep '"state":"Completed"' | jq -r .backupCreatedAt | sort | tail -1 | jq -R 'now - fromdate' | jq '. / 3600' | jq floor
    expect_matches: '^([0-9]|1[0-9]|2[0-5])$'
  - id: old-pv-is-retain
    why: "Deleting the PVC must leave the PV and the Longhorn volume intact."
    run: kubectl get pv data-authentik-postgresql-0 -o jsonpath='{.spec.persistentVolumeReclaimPolicy} {.spec.storageClassName}'
    expect_exact: Retain longhorn-static
  - id: new-volume-backed-up-within-26h
    why: "Gate 2: authentik-pg-data has its own Completed backup newer than 26h."
    run: kubectl get backups.longhorn.io -n storage -o json | jq -c '.items[].status' | grep '"volumeName":"authentik-pg-data"' | grep '"state":"Completed"' | jq -r .backupCreatedAt | sort | tail -1 | jq -R 'now - fromdate' | jq '. / 3600' | jq floor
    expect_matches: '^([0-9]|1[0-9]|2[0-5])$'
sops_refs:
  - docs/sops/longhorn.md
  - docs/sops/backup.md
generated: "2026-08-20"
---

# Retire the bundled 17.11 authentik DB

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
3. Delete the PVC `data-authentik-postgresql-0` in this run (operator ask,
   2026-09-23) — gated by premise `old-volume-retain-and-backed-up-within-26h`:
   the PV is `Retain`, so the PV and the Longhorn volume survive the PVC delete,
   and a Completed backup newer than 26h exists. Run the storage-safety
   pre-flight one-liner from CLAUDE.md first (Longhorn, no subdir). Delete the
   PV and the Longhorn volume only after the next daily backup of NOTHING else
   is needed: leave them, and NEVER delete the backup — it is the recovery
   floor once `~/db-dumps` is purged in step 5.
4. Disable AR-080 (`postgres:17.`) once no 17.11 image runs anywhere.
   AR-112 (`postgres:18.`) stays — it carries the same gosu argument forward.
5. `rm -P ~/db-dumps/authentik-pg17-*.dump` — it holds password hashes, MFA
   secrets and session tokens.

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

Set `postgresql.enabled: true` again. The PV is `Retain`, so the data survives;
after the PVC delete, re-create the PVC bound to the Released PV (clear its
`claimRef` first) or restore the kept Longhorn backup into a new volume.
