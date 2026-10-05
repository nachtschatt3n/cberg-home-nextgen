---
plan_id: sure-0.7.5
component: sure                       # HelmRelease office/sure (chart `sure`, HelmRepository
                                      # flux-system/sure -> https://we-promise.github.io/sure/)
pr: null                              # no Renovate PR; lands via the coverage.py PLAN lane (hand edit)
kind: chart
current: "0.7.4"                      # MEASURED live 2026-10-03: HR history[0] chartVersion 0.7.4,
                                      # deployed, helm revision 50 (2026-09-28)
target: "0.7.5"
update_type: patch
risk: low                             # MEASURED, not assumed: the 0.7.4 -> 0.7.5 chart tarballs differ
                                      # ONLY in Chart.yaml version/appVersion + a CHANGELOG heading;
                                      # `helm template` with our exact values differs ONLY in the
                                      # helm.sh/chart + app.kubernetes.io/version metadata labels of
                                      # 5 objects; no pod template changes, image is pinned by us (§1).
est_duration_min: 15                  # 3 pre-checks + baselines, 2 edit/commit/push, ~4 reconcile +
                                      # post-upgrade migrate hook Job, 4 verification, 2 buffer
needs_reboot: false
touches:
  namespaces: [office]
  resources:                          # every object verified to EXIST live 2026-10-03 (kubectl get)
    - helmrelease/sure                # the only object this plan EDITS (spec.chart.spec.version)
    - deployment/sure-web             # metadata labels only; pod template identical -> NO roll
    - deployment/sure-worker          # metadata labels only; pod template identical -> NO roll
    - service/sure                    # metadata labels only
    - job/sure-migrate                # helm post-upgrade hook: created, runs `rake db:prepare` with the
                                      # UNCHANGED image (no-op), deleted on success (hook-succeeded)
  shared:
    - monitoring                      # §4 reads Prometheus (sure-alerts rules + kube-state-metrics)
depends_on: []
conflicts_with:
  - kube-prometheus-stack-91.9.0      # 2026-10-05 review (blocking): §4.6 reads Prometheus; kps added 2026-10-05
  - nextcloud-fleet-35.0.1            # 2026-10-05 review: reciprocity (office-wide silence; does not blind §4.6)
  - app-template-5.2.1                # upgrades helmrelease/sure-pg + sure-redis, which helmrelease/sure
                                      # dependsOn; a same-night failure there blocks/obscures this one
  - redis-fleet-8.10.2                # rolls deployment/sure-redis and REQUIRES a sure-worker restart
                                      # (its §1.4 sidekiq-cron trap); its §4 must not race this upgrade
  - helm-drift-detection              # adds spec.driftDetection to every HR incl. helmrelease/sure
  - flux-oci-chart-sources            # stage 7 rewrites the `sure` chart source (same spec.chart block)
  - pgvector-fleet-0.8.7              # rolls deployment/sure-pg; a pg restart mid sure-migrate (db:prepare)
                                      # breaks the Job — serialize (see §6). Listed back in that plan.
exclusive: false
security_ref: null
capability_change: false              # chart diff is version metadata only; the app image is OUR fork,
                                      # pinned by sha in values.image.tag and NOT changed by this plan.
                                      # Upstream app 0.7.5 features (§1.3) do NOT arrive with this bump.
rollback_class: git-revert            # nothing forward-only happens: the migrate hook re-runs db:prepare
                                      # with the identical image that revision 50 already migrated, so
                                      # schema_migrations does not move (asserted in §4.3)
finding_refs: [F-adff57e0]            # version finding "sure: chart 0.7.4 -> 0.7.5 (patch)"
review: ready-for-go@2026-10-05   # plan-reviewer 2026-10-05: needs-fix (sole blocker: undeclared kps-91.9.0 conflict) -> fixed by coordinator per the exact correction
premises:
  - id: hr-deployed-on-0.7.4-at-current-generation
    why: >-
      The HR must be Ready with its CURRENT spec (incl. whatever image tag git pins
      today) fully applied: generation == observedGeneration == lastAttemptedGeneration
      and history[0] = 0.7.4 deployed. That is what makes the post-upgrade db:prepare a
      no-op (its image was already migrated by the deployed revision) and what makes
      git revert land on a known-good revision. If sure-agent bumped the fork image and
      it has not yet reconciled, this fails — do not stack the chart bump on it.
    run: kubectl get helmrelease sure -n office -o jsonpath='{.metadata.generation}={.status.observedGeneration}={.status.lastAttemptedGeneration}={.status.history[0].chartVersion}={.status.history[0].status}={.status.conditions[?(@.type=="Ready")].status}'
    expect_matches: '^(\d+)=\1=\1=0\.7\.4=deployed=True$'
  - id: repo-pins-0.7.4-once
    why: "§3's sed assumes exactly one `      version: 0.7.4` line in the HR file (run from the repo root)."
    run: "grep -c '^      version: 0.7.4$' kubernetes/apps/office/sure/app/helmrelease.yaml"
    expect_exact: "1"
  - id: no-failed-migrate-job-left
    why: >-
      A leftover job/sure-migrate means a previous hook FAILED (hook-delete-policy deletes it
      only on success). §4.2 uses the Job's absence as its gate, so it must start absent.
    run: kubectl get job -n office -o name | grep -c 'job.batch/sure-migrate$'
    expect_exact: "0"
status: vetted
window: "nightly:2026-10-12"   # scheduled 2026-10-05: AUTO-NIGHT (chart graduated); with descheduler-0.37.0 (35+15 = 50 of 70)
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-10-03"
---

# sure: Helm chart 0.7.4 -> 0.7.5 (label-only render; forked image unchanged)

## 1) Summary & why held

`office/sure` HelmRelease pins chart `sure` 0.7.4 from `flux-system/sure`. Target 0.7.5
(published in the repo index, appVersion 0.7.5). Answers finding `F-adff57e0`.

**Why held:** coverage gate G3 could not read release notes for the chart (the chart
CHANGELOG for 0.7.5 is literally an empty `## [Unreleased] / Add here` stub), and the
component has 0 green / 0 revert autonomy history in 90 days, so it needs an assessed
window. **On investigation the hold is a false positive for risk**: this is a version-label
bump.

### 1.1 Chart diff (measured 2026-10-03, both tarballs pulled from the repo index)

`diff -r 0.7.4/sure 0.7.5/sure` prints exactly three hunks:

- `Chart.yaml`: `version: 0.7.4 -> 0.7.5`, `appVersion: 0.7.4 -> 0.7.5`
- `CHANGELOG.md`: `## [0.7.4] - 2026-08-31` -> `## [Unreleased]`

No template, `values.yaml`, schema or dependency (`cloudnative-pg ~0.27`, `redis-operator
~0.23.0`, both disabled by us) changed.

### 1.2 Rendered diff with OUR values

`helm template sure <chart> -n office -f <values from helmrelease.yaml>` for both versions:
560 lines each; the only differing lines are `helm.sh/chart` and `app.kubernetes.io/version`
in the top-level `metadata.labels` of `Service/sure`, `Deployment/sure-web`,
`Deployment/sure-worker`, `Pod/sure-test-connection` (test hook, never run: the HR has no
`test:` block) and `Job/sure-migrate`. The Deployments' `spec.template.metadata.labels`
(`component/name/instance`) and annotations (`{}`) are identical, so **neither Deployment
rolls**. The postRenderer patches (wait-for-pg / wait-for-redis initContainers) target
`sure-web`/`sure-worker` by name and still match.

### 1.3 The image, migrations, and upstream release notes

- `values.image.repository/tag` = `ghcr.io/nachtschatt3n/sure:sha-1a9ff4a7…` (our fork) is
  set explicitly, so the chart's `appVersion` default is never used. This plan does not touch
  the image. Live web/worker image == that pin (measured).
- Migrations: the chart runs them only as `Job/sure-migrate` (`helm.sh/hook:
  post-install,post-upgrade`, command `bundle exec rake db:prepare`). It fires on EVERY helm
  upgrade, so it fires here — with the same image that revision 50 (2026-09-28, values
  verified via `helm get values --revision 50`) already migrated. `db:prepare` on an
  up-to-date DB applies nothing: one-way risk is nil, asserted by §4.3 (schema_migrations
  count and max version unchanged; baseline today `407 | 20260824010000`).
- Upstream GitHub release `v0.7.5` is a large APP release (Bills, new bank integrations,
  loan amortization, FinanceKit foundations — with many schema migrations). None of that
  arrives with this chart bump; it arrives only when the fork rebases onto upstream and a new
  `sha-…` image is pinned (sure-agent territory, separate change). Do not confuse the two.
- sure-pg (`pgvector/pgvector:0.8.6-pg16`, app-template) and sure-redis are separate
  HelmReleases; this plan touches neither.

## 2) Pre-checks

Run from `/Users/mu/code/cberg-home-nextgen`.

```bash
# 2.1 premises (the run-time gate)
.venv/bin/python3 runbooks/plan-premises.py sure-0.7.5

# 2.2 target published in the repo the HelmRepository reads
curl -s https://we-promise.github.io/sure/index.yaml | grep -c 'sure-0.7.5.tgz'
# PASS: >=1   FAIL guards against a yanked tag (HR would go Ready=False / chart not found)

# 2.3 no other change in flight on the sure stack
kubectl -n office get helmrelease sure sure-pg sure-redis
# PASS: all three READY True; none "Reconciling"/"upgrade in progress"
kubectl -n office get pods -l app.kubernetes.io/instance=sure
# PASS: sure-web-* and sure-worker-* 1/1 Running

# 2.4 backup freshness (belt only: no data step happens, see rollback_class)
kubectl -n storage get volume "$(kubectl -n office get pvc sure-pg-data -o jsonpath='{.spec.volumeName}')" \
  -o jsonpath='{.status.lastBackupAt}{"\n"}'
# PASS: within the last ~26h. lastBackupAt can lag one cycle — if it looks stale, cross-check the
# newest Completed Backup CR per docs/sops/backup.md ("lastBackupAt Can Lag") before aborting.
# (Daily job: cronjob storage/daily-backup-all-volumes @ 03:00 — verified to exist.)

# 2.5 BASELINES — record these; §4 compares against them
kubectl -n office get deploy sure-web sure-worker \
  -o 'custom-columns=N:.metadata.name,GEN:.metadata.generation,CHART:.metadata.labels.helm\.sh/chart'
kubectl -n office get pods -l app.kubernetes.io/instance=sure \
  -o 'custom-columns=N:.metadata.name,UID:.metadata.uid,RESTARTS:.status.containerStatuses[0].restartCount'
kubectl -n office exec deploy/sure-pg -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select count(*), max(version) from schema_migrations; select count(*) from entries; select count(*) from accounts;"'
# measured 2026-10-03: GEN web=39 worker=50, CHART sure-0.7.4; schema 407|20260824010000;
# entries 15424; accounts 11. Re-measure at run time — the fork image may have moved since.
```

## 3) Steps

Application-update SOP Step 1 (alert silence) and Step 2 (remediation retries 0) are
deliberately NOT taken: no pod rolls, and if the migrate hook failed, Flux's
`upgrade.remediation` rollback lands on revision 50, which is content-identical.

```bash
cd /Users/mu/code/cberg-home-nextgen

# 3.1 bump (dry-tested on a scratch copy with BSD sed; resulting diff:
#   12c12
#   <       version: 0.7.4
#   ---
#   >       version: 0.7.5
sed -i '' 's/^      version: 0\.7\.4$/      version: 0.7.5/' kubernetes/apps/office/sure/app/helmrelease.yaml
git diff kubernetes/apps/office/sure/app/helmrelease.yaml   # exactly the one line above

# 3.2 commit (shared worktree: --only) and verify before push
git commit --only kubernetes/apps/office/sure/app/helmrelease.yaml \
  -m "chore(sure): chart 0.7.4 -> 0.7.5 (label-only render; image unchanged)"
git show --stat HEAD            # exactly one file
git log -1 --format=%s          # the subject above — amend before push if not
git push
```

Flux webhook reconciles; no manual `flux reconcile` needed. Expect within ~5 min: HR
upgrade to revision 51, a short-lived `sure-migrate-*` pod (Completed, then the Job is
deleted by the hook policy).

## 4) Verification

```bash
# 4.1 HR on target, Ready
kubectl -n office get helmrelease sure -o jsonpath='{.status.history[0].chartVersion}={.status.history[0].status}={.status.conditions[?(@.type=="Ready")].status}{"\n"}'
# PASS: 0.7.5=deployed=True
# FAIL prints e.g. 0.7.4=deployed=True (not reconciled / remediated back) or 0.7.5=failed=False

# 4.2 migrate hook succeeded (hook-delete-policy deletes it ONLY on success)
kubectl -n office get job sure-migrate 2>&1
# PASS: Error from server (NotFound)
# FAIL: the Job object is listed (hook failed; inspect `kubectl -n office logs job/sure-migrate`)

# 4.3 CONTENTS ASSERTION: the database schema and data are unchanged — measured by
#     schema_migrations count+max and entries/accounts counts, compared to the §2.5 baseline.
kubectl -n office exec deploy/sure-pg -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select count(*), max(version) from schema_migrations; select count(*) from entries; select count(*) from accounts;"'
# PASS: schema line IDENTICAL to baseline (e.g. 407|20260824010000); entries >= baseline and > 0
#       (the worker may import new transactions); accounts == baseline.
# FAIL guards against: the hook running a different image (new migrations = one-way change,
#       treat as §5.2), or a db:prepare that hit an empty/wrong DB (entries/accounts 0).

# 4.4 CONTENTS ASSERTION: the change is label-only — the Deployments did NOT roll and carry the
#     new chart label. Measured by generation + pod UIDs, compared to the §2.5 baseline.
kubectl -n office get deploy sure-web sure-worker \
  -o 'custom-columns=N:.metadata.name,GEN:.metadata.generation,CHART:.metadata.labels.helm\.sh/chart'
kubectl -n office get pods -l app.kubernetes.io/instance=sure \
  -o 'custom-columns=N:.metadata.name,UID:.metadata.uid,RESTARTS:.status.containerStatuses[0].restartCount'
# PASS: CHART=sure-0.7.5 on both; GEN unchanged; same pod names/UIDs; RESTARTS unchanged.
# FAIL: CHART still sure-0.7.4 (upgrade not applied), or GEN moved / new pod UID (the render
#       was NOT label-only — investigate before closing; not a rollback trigger by itself if 4.5 passes).

# 4.5 app answers through its Service (Rails health + login page render, which needs DB + OIDC config)
kubectl -n office port-forward svc/sure 18080:80 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -o /dev/null -w 'up=%{http_code}\n'    http://localhost:18080/up
curl -s -o /dev/null -w 'login=%{http_code}\n' http://localhost:18080/sessions/new
kill $PF 2>/dev/null
# PASS: up=200 login=200 (both measured 200 on 2026-10-03). FAIL prints 000 (no endpoint) or 5xx.

# 4.6 alerts + availability from Prometheus
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF2=$!; sleep 3
curl -s http://localhost:19090/api/v1/rules | python3 -c "
import sys,json;d=json.load(sys.stdin)
r=[x['name']+':'+x['state'] for g in d['data']['groups'] if g['name'].startswith('sure.') for x in g['rules']]
print(len(r), r)"
curl -s http://localhost:19090/api/v1/query --data-urlencode 'query=kube_deployment_status_replicas_available{namespace="office",deployment=~"sure-web|sure-worker"}' \
  | python3 -c "import sys,json;print([(x['metric']['deployment'],x['value'][1]) for x in json.load(sys.stdin)['data']['result']])"
kill $PF2 2>/dev/null
# PASS: 5 rules, all :inactive; two series, both value 1.
# FAIL: fewer than 5 rules (rules not loaded — the gate would be blind, do not read it as green),
#       any :pending/:firing, or an empty series list (kube-state-metrics not scraped -> blind, not green).
```

CONTROL: alertname SurePodNotReady — must be inactive after the upgrade (rule loaded: 5 `sure.*` rules present, measured 2026-10-03).
CONTROL: alertname SurePodCrashLooping — must be inactive.
CONTROL: alertname SurePodRestarted — must be inactive (a roll or crash would trip it within 1m).
CONTROL: metric kube_deployment_status_replicas_available — sure-web and sure-worker both == 1 (two non-empty series).

Note: `SurePodNotReady` also matches the transient `sure-migrate-*` pod (`pod=~"sure-.*"`), but
its `for: 5m` outlasts a no-op db:prepare; a firing on that pod means the hook hung — treat as 4.2 FAIL.

## 5) Rollback

5.1 **Normal case (nothing forward-only happened; 4.3 schema line identical):**

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-3.2>
git show --stat HEAD && git log -1 --format=%s
git push
# confirm:
kubectl -n office get helmrelease sure -o jsonpath='{.status.history[0].chartVersion}={.status.history[0].status}={.status.conditions[?(@.type=="Ready")].status}{"\n"}'
# -> 0.7.4=deployed=True, then re-run §4.2–4.5 (CHART label back to sure-0.7.4).
```

If helm is wedged `pending-upgrade` (application-update SOP §11):
`helm -n office history sure` → `helm -n office rollback sure <last deployed rev> --wait=false`,
then let the revert reconcile.

5.2 **If 4.3 shows the schema moved** (should be impossible with an unchanged image — it means the
image was not what §2 measured): a git revert does NOT undo Rails migrations. Stop, do not
revert blindly; restore path is the Longhorn backup of the sure-pg data volume per
docs/sops/backup.md (the §2.4 backup is the restore point), operator present. Escalate rather
than improvise.

## 6) Interference notes

- **Self-contained and quiet**: one HR, no pod roll, no route/Gateway/Authentik/storage change.
  Safe for the unattended nightly window on its own merits.
- **sure-pg / pgvector-fleet-0.8.7**: that plan (being written 2026-10-03) rolls
  `deployment/sure-pg` (Recreate). If it runs in the same window, the `sure-migrate` hook's
  db:prepare can hit a restarting DB (the hook waits on `pg_isready`, but a restart mid-run fails
  the Job → helm remediation). Serialize: **pgvector-fleet-0.8.7 must list `sure-0.7.5` in its
  `conflicts_with`, and this plan must add it back once that file exists** (cannot be listed now:
  DEAD-REF).
- **app-template-5.2.1 / redis-fleet-8.10.2**: both upgrade the sure-pg/sure-redis HRs that
  `helmrelease/sure` dependsOn; redis-fleet also requires a sure-worker restart. Listed in
  `conflicts_with`; neither currently lists this plan back — the reciprocal entries should be
  added on their side.
- **helm-drift-detection / flux-oci-chart-sources**: both edit `helmrelease/sure`'s spec
  (driftDetection; chart source in stage 7). Listed to keep attribution clean.
- **Monitoring**: §4.6 reads Prometheus; do not share a window with a kube-prometheus-stack bump
  (none open as of 2026-10-03; `kube-prometheus-stack-91.4.1` is executed).
