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
  shared: []
depends_on: []
conflicts_with: []
status: awaiting-soak                 # do NOT run until the soak below is satisfied
window: null
# auto_execute RETIRED 2026-08-26 (P2.1b) — execution class is now DERIVED
# from capability_change/rollback_class per runbooks/autonomy-policy.yaml.
# (original rationale: destroys the rollback path)
security_ref: null
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
3. The PVC `data-authentik-postgresql-0` is Longhorn with `Retain` — deleting the
   StatefulSet does not delete the data. Keep the PV for one more backup cycle,
   then remove it deliberately.
4. Disable AR-080 (`postgres:17.`) once no 17.11 image runs anywhere.
   AR-112 (`postgres:18.`) stays — it carries the same gosu argument forward.
5. `rm -P ~/db-dumps/authentik-pg17-*.dump` — it holds password hashes, MFA
   secrets and session tokens.

## Verification

- `kubectl get sts -n kube-system` — no `authentik-postgresql`.
- authentik still serves logins (both paths again).
- No pod references `authentik-postgresql`:
  `kubectl get pods -n kube-system -o yaml | grep -c authentik-postgresql` → 0.

## Rollback

Set `postgresql.enabled: true` again. The PV is `Retain`, so the data survives;
the StatefulSet re-binds it. This is why step 3 keeps the PV.
