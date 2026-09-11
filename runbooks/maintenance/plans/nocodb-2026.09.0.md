---
plan_id: nocodb-2026.09.0
component: nocodb
pr: null                              # no open Renovate PR — nocodb is on the auto-update
                                      # deny-list (max: patch, `*nocodb*` rule added
                                      # 2026-08-19); coverage.py's direct-bump lane
                                      # surfaced this as F-ca5c5597, not a PR.
kind: image
current: "2026.08.2"                  # verified live 2026-09-11: manifest tag AND
                                      # running pod image both read nocodb/nocodb:2026.08.2
target: "2026.09.0"
update_type: minor                    # calver month hop; classifier reads it as `minor`
                                      # but per the policy deny rule it is treated as a
                                      # FEATURE release with a migration-boot risk profile,
                                      # never unattended. See §1.
risk: medium
est_duration_min: 35
needs_reboot: false
touches:
  namespaces: [databases]
  resources:
    - helmrelease/nocodb
    - deployment/nocodb
    - pvc/nocodb-data                  # near-empty (lost+found only); all real state is in PG
    - database/nocodb@postgresql       # nocodb's own DB inside the shared instance
  shared: [postgresql]                 # SAME token as nocodb-calver used — the shared
                                      # `postgresql` deployment in ns `databases`. It is not
                                      # restarted by this change, but nocodb's boot-time
                                      # migration runner writes into a database living
                                      # inside it, so it shares that instance's CPU/disk.
depends_on: []
conflicts_with: []                    # CHECKED 2026-09-11 via `maintenance-plan.py --open`:
                                      # no open EXECUTABLE/REFERENCE plan declares
                                      # `shared: [postgresql]` against THIS instance.
                                      # authentik-pg18-lockstep and superset-pg-decommission
                                      # touch their OWN dedicated postgres deployments
                                      # (authentik's bundled/pg18, superset-pg/-pg18) —
                                      # different instances, not this one. Re-check
                                      # `--open` before scheduling in case a new plan lands.
security_ref: F-ca5c5597
capability_change: true               # 2026.09.0 adds user-visible surface: Claude
                                      # Connector marketplace listing, MCP tool count
                                      # 11->149, workflow email rich-text formatting,
                                      # interface header/toolbar/dashboard buttons. Not
                                      # cosmetic-only — say so, don't round down to false.
rollback_class: backup-restore        # NOT git-revert. Upstream documents no downgrade
                                      # path across a knex-migrated boot; a bare tag
                                      # revert would run 2026.09.0's superstructure
                                      # against a DB the older code has never migrated
                                      # forward from and may not read correctly. See §5.
backup_gate: "pg_dump of the nocodb metadata database (DB name resolved from the live
  NC_DB secret's d= param, not hardcoded) taken from the LIVE postgresql pod BEFORE the
  tag edit is pushed, verified gzip-valid and non-trivial size, with a pre-upgrade
  information_schema.tables count recorded for the §4 contents comparison."
finding_refs: [F-ca5c5597]
status: draft
window: null                          # see §6 for the recommended slot and why it is
                                      # not assigned here
premises:
  - id: live-image-is-still-2026.08.2
    why: >-
      `current:` claims 2026.08.2. If the cluster already moved (e.g. someone
      hand-applied a bump, or a later coverage.py direct-bump ran), this plan's
      target/diff and its §4 rollback baseline are stale and must be re-derived
      before executing.
    run: kubectl get deploy -n databases nocodb -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: nocodb/nocodb:2026.08.2
  - id: db-secret-still-wired-to-nocodb-env
    why: >-
      `touches.resources` names `database/nocodb@postgresql` because NC_DB is
      supplied via envFrom secretRef `nocodb`. If the secretRef name changed,
      the DB-name resolution shell snippet in §2f/§3 (which reads this same
      secret) and the dump/restore commands would be pointed at the wrong
      object or fail closed — better that than silently dumping nothing.
    run: kubectl get deploy -n databases nocodb -o jsonpath='{.spec.template.spec.containers[0].envFrom[0].secretRef.name}'
    expect_exact: nocodb
  - id: shared-postgresql-instance-still-present
    why: >-
      `touches.shared` declares `[postgresql]` against `deployment/postgresql`
      in `databases`. If that workload were renamed/replaced (e.g. a future
      superset-pg-style cutover to a dedicated instance), the dump/restore
      commands in §2f/§5, which `kubectl exec` into `deploy/postgresql`, would
      silently target the wrong database server.
    run: kubectl get deploy -n databases postgresql -o jsonpath='{.metadata.name}'
    expect_exact: postgresql
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
generated: "2026-09-11"
---

# nocodb 2026.08.2 → 2026.09.0

## 1) Summary & why held

This is the **first monthly calver bump since the semver→calver migration**
executed by `nocodb-calver.md` (0.301.5 → 2026.08.0, 2026-08-19, retained
verbatim — do not edit or delete that file; it is the historical record of the
scheme-switch execution and still holds the live rollback facts for that
event). That plan's target (2026.08.0) is now two patch releases behind live
(2026.08.2), and it does not cover this month's bump — which is exactly why
`coverage.py` surfaced nocodb again as needing a plan (F-ca5c5597, cycle
`0e37c7d3-fac2-4534-a776-04b9cba03c9b`). **This is a fresh plan, not a
retarget of the old file**: the old file's `status: executed` record and its
retention rationale describe a completed, different event (the scheme
boundary itself); reusing its `plan_id` for a new, unexecuted bump would
overwrite that record. The operational knowledge it captured (DB-name
resolution from the live secret, one-way-migration framing, dump-then-restore
rollback shape) is carried forward below rather than re-derived.

**Why this is held at all**: `runbooks/auto-update-policy.yaml` denies
`*nocodb*` down to `max: patch` (rule added 2026-08-19, see lines 132-145).
The classifier reads a calver month hop (`2026.08.x -> 2026.09.0`) as
`minor`, which G1 would otherwise wave through unattended — the policy rule
exists precisely to override that misclassification: **every monthly nocodb
release runs its knex migration framework on boot, into the shared
`postgresql` instance, and upstream documents no downgrade.** That reasoning
is a property of the release cadence, not of any one month's diff, so it
applies here even though this specific release turns out to be lighter than
the scheme-switch bump.

**Verified upstream evidence for 2026.09.0** (GitHub release notes +
`https://nocodb.com/docs/self-hosting/maintenance/upgrading`, fetched
2026-09-11):

- **No database migration is documented for this release.** Unlike 2026.06.0
  (which explicitly called out new tables/columns), 2026.09.0's notes list no
  schema change. Read this as *not proven risk-free*, not as *proven safe* —
  nocodb's migration runner (knex) still executes unconditionally on every
  boot regardless of whether the release notes mention a new migration, so
  the boot-time risk and the mandatory pre-dump gate stay in force as a matter
  of policy, independent of this release's specific diff.
- **New capability surface** (why `capability_change: true`): Claude
  Connectors marketplace listing (149 MCP tools, up from 11), workflow email
  rich-text formatting (headings/lists/colors/anchor text in Send Email/SMTP/
  Gmail/Outlook nodes), interface header/toolbar/dashboard buttons,
  drag-and-drop List View, inline linked-record field creation, Kanban-default
  + streamed Excel export performance changes. None of these require config
  changes on our side (no new required env vars found in the diff we could
  inspect); they are additive UI/API surface.
- **A breaking change is ANNOUNCED but not yet implemented in this tag**: a
  planned PostgreSQL/SQLite datetime precision change (second -> millisecond,
  e.g. `...12:34:56+00:00` -> `...12:34:56.000+00:00`), first announced in
  2026.08.2's notes, explicitly **not yet shipped**. It will affect exact-match
  datetime filters, webhooks, and exports once it lands. Flag for the *next*
  bump's planner — nothing to do about it in this one.
- **Upgrade doc**: "Pull the latest image and restart. Your data and config
  are preserved" for routine bumps, and "Always back up before a major version
  upgrade" — no downgrade/rollback procedure is documented at any tier. Treat
  the migration chain as one-way, as `nocodb-calver.md` already established.

**Registry verification** (2026-09-11, Docker Hub API, not `docker` CLI —
`docker` is not installed on this Mac):
- `nocodb/nocodb:2026.09.0` **exists**: multi-arch (amd64 `sha256:5c9296e0…`,
  arm64 `sha256:d380fceb…`), `tag_last_pushed: 2026-09-10T11:30:48.709134Z`.
- **No newer tag exists** as of 2026-09-11T02:24Z: querying Docker Hub for
  `name=2026.09` returns exactly one result (`2026.09.0`); `name=2026.10`
  returns zero. This is the newest published release.
- **48h release-age cooldown (`minimum_release_age_hours: 48`, G5) has NOT
  yet elapsed**: at check time the tag was ~15h old. G5 formally gates only
  the *unattended* auto-update lane (`auto-update.py` / `coverage.py`'s
  direct-bump path) — this plan was never eligible for that lane anyway
  (denied to `max: patch`), so G5 does not block scheduling this plan.
  Applying the same supply-chain-hygiene logic anyway: **do not execute
  before 2026-09-12T11:31 UTC** (48h from `tag_last_pushed`). See §6 for the
  recommended window, which clears this with room to spare.

**Why risk is `medium`, not `low` or `high`:** the deployment shape is the
same low-blast-radius one `nocodb-calver.md` verified — single replica,
`strategy` effectively `Recreate`-safe (RWO PVC, `nocodb-data` holds only
`lost+found`), all real state in the external `postgresql` instance, fresh
Longhorn backups nightly. It is not `low` because a boot-time migration
runner against a shared DB instance is exactly the shape that has bitten this
component before (the deny rule exists because of it), and there is no
vendor-documented downgrade. It is not `high` because this release's own
notes show no destructive schema change and the blast radius, if the upgrade
misbehaves, is contained to nocodb's own database and its own pod.

`security_ref` / `finding_refs`: `F-ca5c5597` (version-currency finding,
section `version`, cycle `0e37c7d3-fac2-4534-a776-04b9cba03c9b`) — no
vulnerability detail applies; this is a version-currency bump.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) nocodb + shared PG healthy, HR Ready on app-template 5.1.0, live tag matches `current:`
kubectl get pods -n databases | grep -E 'nocodb|^postgresql'
kubectl get hr -n databases nocodb -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
kubectl get pods -n databases -l app.kubernetes.io/name=nocodb \
  -o jsonpath='{.items[0].spec.containers[0].image}{"\n"}'
  # expect: nocodb/nocodb:2026.08.2 — if it does not match `current:`, STOP, this plan is stale

# b) target tag still resolves (re-verify at execution time, not just at plan-write time)
curl -s "https://hub.docker.com/v2/repositories/nocodb/nocodb/tags/2026.09.0" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['name'], d['tag_last_pushed'])"
  # expect: 2026.09.0 2026-09-10T11:30:48.709134Z

# c) still nothing newer published (re-check — a later tag would change the target)
curl -s "https://hub.docker.com/v2/repositories/nocodb/nocodb/tags/?page_size=10&name=2026.09" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])"   # expect 1
curl -s "https://hub.docker.com/v2/repositories/nocodb/nocodb/tags/?page_size=10&name=2026.10" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])"   # expect 0

# d) 48h cooldown has cleared (informational, not gating — see §1)
python3 -c "
from datetime import datetime, timezone
pushed = datetime.fromisoformat('2026-09-10T11:30:48.709134+00:00')
print('age_hours:', (datetime.now(timezone.utc) - pushed).total_seconds()/3600)
"   # proceed only if >= 48

# e) Longhorn backups fresh (last nightly 03:00 run succeeded for both volumes)
kubectl get volume -n storage nocodb-data postgresql-data-5g \
  -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt --no-headers

# f) MANDATORY point-in-time dump of the nocodb metadata DB — the backup_gate.
#    DB name comes from the d= param of NC_DB in the app secret — never hardcode it,
#    it has already been the one variable across bumps.
NCDB_NAME=$(sops -d kubernetes/apps/databases/nocodb/app/secret.sops.yaml \
  | python3 -c "import sys,yaml,urllib.parse as u; s=yaml.safe_load(sys.stdin)['stringData']['NC_DB']; print(u.parse_qs(u.urlsplit(s).query)['d'][0])")
echo "resolved DB name: $NCDB_NAME"   # expect: nocodb
mkdir -p ~/backups/nocodb
kubectl exec -n databases deploy/postgresql -- sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d '"$NCDB_NAME"' --clean --if-exists' \
  | gzip > ~/backups/nocodb/nocodb-pre-2026.09.0-$(date +%F).sql.gz
gzip -t ~/backups/nocodb/nocodb-pre-2026.09.0-$(date +%F).sql.gz && \
  ls -lh ~/backups/nocodb/nocodb-pre-2026.09.0-$(date +%F).sql.gz
  # GATE: non-trivial size (compare to the 13.3MB the calver dump produced —
  # a dump orders of magnitude smaller than that is a fingerprint of a bad
  # export, not proof of a shrinking dataset), gzip valid. Do NOT proceed past
  # this step without a verified-good dump.

# g) pre-upgrade data fingerprint to compare in §4 (CONTENTS assertion baseline)
kubectl exec -n databases deploy/postgresql -- sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d '"$NCDB_NAME"' -tAc \
  "select count(*) from information_schema.tables where table_schema='"'"'public'"'"'"'
# note the table count

# h) no in-flight flux reconcile on databases apps
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
```

## 3) Steps

1. **Silence + marker** (attended-tier update per `application-update.md` §4):
   ```bash
   runbooks/update-marker.sh add nocodb databases 4 "2026.08.2 -> 2026.09.0 monthly calver bump"
   ```

2. **Disable HR rollback for the attempt** — a Flux remediation rollback
   mid-migration would flip the image back while knex is writing schema. Edit
   `kubernetes/apps/databases/nocodb/app/helmrelease.yaml`:
   ```yaml
     upgrade:
       cleanupOnFail: true
       remediation:
         retries: 0
         remediateLastFailure: false   # TEMP for this bump — restore after §3.4
   ```

3. **Bump the image tag** in the same file:
   ```yaml
               image:
                 repository: nocodb/nocodb
                 tag: 2026.09.0
   ```

4. **Commit + push** (hunk-scoped — shared worktree, per CLAUDE.md):
   ```bash
   git commit --only kubernetes/apps/databases/nocodb/app/helmrelease.yaml \
     -m "feat(nocodb): 2026.08.2 -> 2026.09.0 (monthly calver bump; plan nocodb-2026.09.0)"
   git push
   git show --stat HEAD   # confirm only the nocodb helmrelease is in this commit
   ```

5. **Watch the migration boot**:
   ```bash
   flux reconcile source git flux-system   # only if the webhook lags
   kubectl get pods -n databases -w | grep nocodb
   kubectl logs -n databases deploy/nocodb -f | grep -iE 'migrat|xc-|error|listen'
   ```

6. **On success:** restore `retries: 3` / remove `remediateLastFailure: false`,
   commit + push, clear the marker:
   ```bash
   git commit --only kubernetes/apps/databases/nocodb/app/helmrelease.yaml \
     -m "chore(nocodb): restore HR remediation retries after 2026.09.0 bump"
   git push
   runbooks/update-marker.sh clear nocodb
   ```

## 4) Verification

```bash
# HR Ready, pod on new image, stable
kubectl get hr -n databases nocodb -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
kubectl get pods -n databases -l app.kubernetes.io/name=nocodb \
  -o jsonpath='{.items[0].spec.containers[0].image} {.items[0].status.containerStatuses[0].restartCount}{"\n"}'
# expect nocodb/nocodb:2026.09.0, 0 restarts after settle (~5 min)

# app answers (Authentik forward-auth in front → expect 302 to outpost, not 5xx)
curl -sk -o /dev/null -w '%{http_code}\n' https://nocodb.${SECRET_DOMAIN}/   # 302/200, NOT 502/503

# migrations completed cleanly (whether or not this release added a new one)
kubectl logs -n databases deploy/nocodb | grep -iE 'migrat' | tail -20   # no errors/rollbacks

# CONTENTS ASSERTION: table count on the nocodb database is >= the §2g baseline,
# measured with the same count(*) query, not a proxy like "pod Ready" or "HR Ready" —
# those would stay green even if the DB were emptied.
kubectl exec -n databases deploy/postgresql -- sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d '"$NCDB_NAME"' -tAc \
  "select count(*) from information_schema.tables where table_schema='"'"'public'"'"'"'
# expect: >= the count recorded in §2g

# no new firing alerts (ignore Watchdog/InfoInhibitor)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
curl -s http://localhost:9090/api/v1/alerts | grep -o '"alertname":"[^"]*"' \
  | grep -vE 'Watchdog|InfoInhibitor' | sort -u

# OPERATOR: log in via browser, open each existing base, confirm tables/views/records
# render and a test edit saves. This is the real acceptance gate — the same one
# nocodb-calver.md used, and the same reason this stays attended.
```

## 5) Rollback

**A bare tag revert is NOT a rollback.** Even though this release's own notes
document no new migration, nocodb's knex runner executes unconditionally on
boot; if it wrote anything at all, `2026.08.2`'s code has no guarantee it can
read the result, and upstream documents no downgrade path at any tier.
Rollback is **revert + restore**, exactly the shape `nocodb-calver.md`
established:

```bash
# 1) revert the bump commit(s) — git push
git revert <bump-commit-sha> && git push
# wait for flux; fence the pod BEFORE it can serve the old code against the new schema:
kubectl scale deploy -n databases nocodb --replicas=0

# 2) restore the pre-upgrade dump (drops+recreates objects via --clean --if-exists)
gunzip -c ~/backups/nocodb/nocodb-pre-2026.09.0-<date>.sql.gz | \
  kubectl exec -i -n databases deploy/postgresql -- sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d '"$NCDB_NAME"''

# 3) bring nocodb back and confirm
kubectl scale deploy -n databases nocodb --replicas=1
kubectl get pods -n databases | grep nocodb          # Running, image 2026.08.2
curl -sk -o /dev/null -w '%{http_code}\n' https://nocodb.${SECRET_DOMAIN}/   # 302/200
# OPERATOR: open a base, confirm pre-upgrade data is back
```

(The scale commands are the one sanctioned direct-cluster action, fencing the
restore; Flux's desired state is restored by the git revert itself. The
`postgresql-data-5g` Longhorn backup from that morning's 03:0x run is the
disaster fallback if the dump itself is bad — but restoring THAT rolls back
every database in the shared instance, not just nocodb's, and is a last
resort coordinated per `docs/sops/backup.md`.)

## 6) Interference notes

- **Shared `postgresql` instance is the interference surface** (same token
  `nocodb-calver.md` used). The `postgresql` pod itself is not restarted, but
  the migration runner writes into nocodb's database inside it, sharing that
  instance's CPU/disk with every other tenant DB. Checked 2026-09-11 via
  `maintenance-plan.py --open`: no other open plan currently declares
  `shared: [postgresql]` against *this* instance — `authentik-pg18-lockstep`
  and `superset-pg-decommission` touch their own separate postgres
  deployments. Re-check `--open` immediately before scheduling, since new
  plans land between now and any window.
- `nocodb-data` PVC is Longhorn RWO but effectively empty (`lost+found` only);
  no storage-class hazard (`longhorn-static`, `Retain`).
- Expected user-visible downtime ~1-3 min (pod replace + migration boot).
  Homepage tile + Authentik forward-auth are unaffected — routing is
  untouched by this plan.
- **Release-age cooldown**: do not run before **2026-09-12T11:31 UTC**
  (~13:31 Europe/Berlin) — 48h from the target tag's `tag_last_pushed`. This
  is not a hard gate on this attended lane (G5 only binds unattended apply),
  but there is no reason to burn the margin the operator built into G5 for
  exactly this class of risk.
- **Recommended window (not assigned — `window: null`)**: `sun-attended:
  2026-09-13` has capacity — currently holds `authentik-pg18-lockstep`
  (medium, 35min) + `absenty-drop-npm-runtime` (low, 60min) = risk-load 3 /
  95min against `capacity_risk: 6` / `duration_min: 150`. Adding this plan
  (medium, ~35min) brings it to risk-load 5 / ~130min — both within capacity —
  and 2026-09-13T09:00 Europe/Berlin is safely past the cooldown above.
  `sat-attended:2026-09-12` is explicitly NOT proposed: it is already at
  risk-load 7 against a capacity of 6 and ~100min against a 90min window
  (`edot-collector-0.160.0` + `grafana-orphan-dashboard-uid` +
  `mcpo-python-3.14` + `scrypted-0.145.0`), so it is over-committed before
  this plan is even considered, and its date is also before the cooldown
  clears. The window agent makes the final call; this is a recommendation,
  not an assignment.
- One-way boundary: once §4's operator acceptance gate passes and the window
  closes, **the pre-upgrade dump is the only way back** — keep
  `~/backups/nocodb/nocodb-pre-2026.09.0-<date>.sql.gz` until at least the
  next nightly Longhorn backup after sign-off.
- Attended preferred: the acceptance gate (bases/tables render, edit saves) is
  a human check, same as `nocodb-calver.md`.
