---
plan_id: sure-0.7.3-deploy
component: sure
pr: null                            # self-built fork — no Renovate PR; image is
                                    # ghcr.io/nachtschatt3n/sure built from the
                                    # rebased deploy branch (force-pushed 2026-08-02)
kind: image
current: "sha-498fd583e2fa7977ed6d116e61819aebae315332"   # v0.7.2-era base
target:  "sha-40428d74d36e7c0ba4ba826dc5068136dbd395b5"   # rebased onto upstream v0.7.3
update_type: minor                  # app 0.7.2 → 0.7.3 (fork rebase, CI green)
risk: medium                        # additive DB migrations run on pod start; proven
                                    # clean from empty (398/398) + schema.rb loads clean,
                                    # but it's live user finance data → snapshot + go/no-go
est_duration_min: 30
needs_reboot: false                 # single Deployment rolls in place; no node reboot
touches:
  namespaces: ["office"]
  resources: [deployment/sure, sure-postgresql]     # own PG; NOT the shared mariadb
  shared: []                        # self-contained in office (own PG); nextcloud in the
                                    # same ns has its own mariadb/redis — no shared infra
depends_on: []
conflicts_with: []                  # nothing competes; do NOT co-schedule another office
                                    # DB-migrating app in the same window
window: "thu-early:2026-08-20"      # no-reboot ⇒ weekday; own slot (clear of nextcloud
                                    # Thu 08-13 / nextcloud-mcp Tue 08-18)
status: scheduled
auto_execute: false                 # medium + live-data migrations → always operator go/no-go
generated: "2026-08-02"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/longhorn.md
---

# sure — deploy the rebased 0.7.3 image (sha-498fd583 → sha-40428d74)

## 1. Summary & why held

The self-hosted **sure** finance app (fork `nachtschatt3n/sure`, deployed in
`office`) was rebased from its v0.7.2-era base onto **upstream v0.7.3** on
2026-08-02 (operator-approved full rebase). The rebase is done, force-pushed
(backups tagged `backup/preview-pre073` / `backup/deploy-pre073`), and the image
is **built + CI-green** (full `test_system` suite passed, multi-arch amd64+arm64):

```
ghcr.io/nachtschatt3n/sure:sha-40428d74d36e7c0ba4ba826dc5068136dbd395b5
```

It's held to a window (not an unattended bump) purely because **v0.7.3's new
migrations run on pod start against live finance data**. The rebase itself is
low-risk (detection layer byte-identical pre/post — the operator's contract
model + Ø/month rollup are unaffected; GHSA-xr9x Active Storage fix now in), but
a DB-migrating deploy of user financial data always gets a snapshot + go/no-go.

**Migration scope nuance (important):** the currently-deployed image
(`sha-498fd583`) already carried v0.7.2 + native-equivalent Trading 212 + the 3
contract migrations, so **those already exist in the live DB and will NOT
re-run**. The pending set is *only* v0.7.3's new-feature migrations (Insights,
Plan/Goals unification, etc.) — all additive. Proven: the full 398-migration set
applies cleanly from an empty DB and `schema.rb` loads clean.

## 2. Pre-checks (all must pass before the tag bump)

```bash
cd /Users/mu/code/cberg-home-nextgen
# 2.1 App + its PG healthy now
mise exec -- kubectl get pods -n office -l app.kubernetes.io/name=sure -o wide
mise exec -- kubectl get pods -n office -l app.kubernetes.io/name=postgresql | grep -i sure || true
# 2.2 Confirm the target image exists in GHCR (built above)
#     (the publish.yml run pushed it; visually confirm the tag resolves)
# 2.3 Confirm the EXACT pending migration count against the LIVE schema_migrations
#     (cberg-agent, at window start) so we know precisely what will run:
mise exec -- kubectl exec -n office deploy/sure -- bin/rails runner \
  'puts ActiveRecord::Base.connection.migration_context.needs_migration?; \
   puts (ActiveRecord::Base.connection.migration_context.migrations.map(&:version) - \
         ActiveRecord::SchemaMigration.all.map{|m| m.version.to_i}).size' 2>/dev/null || true
# 2.4 TAKE THE SNAPSHOT — Longhorn PG snapshot of sure's data volume BEFORE the
#     bump (this is the real rollback floor for a migrating deploy). See
#     docs/sops/longhorn.md + storage-safety.md. Do NOT proceed without it.
```

## 3. Execution (GitOps, delegate the edit to cberg-agent)

Single-line image-tag bump — repository, chart pin, pull-secret all unchanged:

```yaml
# kubernetes/apps/office/sure/app/helmrelease.yaml  (line ~121)
# from:
      tag: "sha-498fd583e2fa7977ed6d116e61819aebae315332"
# to:
      tag: "sha-40428d74d36e7c0ba4ba826dc5068136dbd395b5"
```

Commit + push → Flux reconciles → the new pod runs the additive migrations on
start. Watch the migration output complete before declaring readiness.

## 4. Verification

```bash
mise exec -- kubectl rollout status -n office deploy/sure --timeout=5m
mise exec -- kubectl logs -n office deploy/sure --tail=50 | grep -iE 'migrat|error' || true
```
- Pod Ready 1/1 on the new sha; migrations completed (no pending, no errors).
- Log in to the UI; confirm: dashboard loads, **Contracts / Verträge preview**
  works with the Ø/month rollup, transactions list intact, Insights (new v0.7.3
  feature) renders without colliding with the Contracts preview nav.
- **Stale "Technical difficulties" page after cutover = the PWA service worker**,
  not a server fault — hard-reload / clear the SW, then re-check.

## 5. Rollback

1. **Preferred (no data loss if caught fast):** `git revert` the tag bump →
   Flux rolls back to `sha-498fd583`. Safe ONLY if the additive migrations
   haven't introduced state the old image can't read — since they're additive
   (new tables/columns), the old image ignores them, so image-revert alone
   usually suffices.
2. **If the DB is wedged / data looks wrong:** restore the **Longhorn PG
   snapshot** taken in 2.4 (this is why it's mandatory). Branch backups
   `backup/deploy-pre073` also let the fork be rebuilt at the old base if needed.
3. Page the operator (URGENT via notify.py + OpenClaw) on any rollback.

## 6. Interference

`shared: []` — self-contained in `office` on its own PostgreSQL. nextcloud (same
ns) uses its own mariadb/redis and upgrades in a different window (Thu 08-13), so
no overlap. Do not co-schedule another office DB-migrating app in this slot.
