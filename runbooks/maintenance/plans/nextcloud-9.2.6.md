---
plan_id: nextcloud-9.2.6
component: nextcloud
pr: null                              # no open Renovate PR found for this bump (checked
                                       # `gh pr list --state open`); auto-updater held it on
                                       # policy (chart+image coupling rule), not on a live PR
kind: chart
current: "9.2.5"
target: "9.2.6"
update_type: patch
risk: low                             # see Summary — investigation found the app-version
                                       # component of the hold does not apply to this bump
est_duration_min: 20
needs_reboot: false
capability_change: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud            # chart.spec.version 9.2.5 -> 9.2.6 (values untouched)
    - deployment/nextcloud             # helm upgrade bumps the helm.sh/chart label -> pod
                                        # template hash changes -> ONE rolling restart even
                                        # though image.tag is not changing
    - cronjob/nextcloud-cron           # same label churn; restarts on next tick
    - deployment/nextcloud-notify-push # NOT restarted by this chart values (unaffected;
                                        # image tag pinned independently in notify-push.yaml)
  shared: []                           # no ingress/cert-manager/cilium/coredns/shared-DB/
                                        # storage perturbation — externalDatabase (mariadb
                                        # subchart) and redis are untouched by this bump
depends_on: []
conflicts_with: [bitnamilegacy-exit-nextcloud-db]
                                       # that plan replaces the bundled mariadb subchart with
                                       # an external Deployment via THE SAME HelmRelease file;
                                       # it is currently `status: blocked` / `window: null`
                                       # (rolled back 2026-08-19, not re-armed as of 2026-09-05)
                                       # so there is no live collision today, but if it is ever
                                       # rescheduled it MUST NOT share a window with this plan —
                                       # both edit helmrelease.yaml and both restart
                                       # deployment/nextcloud
security_ref: null
rollback_class: git-revert
finding_refs: []
status: draft
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
generated: "2026-09-05"
---

## 1. Summary & why held

The auto-updater's policy gate for `nextcloud` treats every chart bump as
non-safe by rule ("chart+image must bump together and run occ migrations —
Mail custom_app trap"), because in general a nextcloud chart release also
moves the bundled `appVersion` default, which changes the running Nextcloud
image, which runs `occ upgrade` on next pod start. That migration path has
bitten this cluster twice before (see `project_nextcloud_upgrade_mailapp.md`):
on the 33.0.0→33.0.4 image bump, the `mail` app's vendor dir came out
incomplete and broke *every* `occ`/cron invocation, and the readiness probe
restarted the pod mid-`occ upgrade`, leaving maintenance mode stuck on. A
second bump silently force-disabled `google_synchronization` because
`occ upgrade` re-validates app compatibility.

**Investigation shows this specific bump does not actually trigger that
path.** Verified facts:

- The chart's own appVersion does move: chart 9.2.5 ships appVersion
  `34.0.2`, chart 9.2.6 ships appVersion `34.0.3` (verified against
  `https://nextcloud.github.io/helm/index.yaml`, chart entries dated
  2026-07-26 and 2026-08-17 respectively).
- **But this HelmRelease does not use the chart's appVersion default** — it
  pins `image.tag: 34.0.3` explicitly (and the `worker` extraSidecar image is
  separately pinned to `nextcloud:34.0.3` too). Both are already at the value
  chart 9.2.6 would default to.
- Live cluster check confirms the running pod is **already**
  `docker.io/nextcloud:34.0.3` with `php occ status` reporting
  `versionstring: 34.0.3`, `maintenance: false`, `needsDbUpgrade: false`.
- Diff of the upstream chart between the `nextcloud-9.2.5` and
  `nextcloud-9.2.6` tags (`gh api repos/nextcloud/helm/compare/...`) touches
  only `charts/nextcloud/Chart.yaml` (version/appVersion bump), two GitHub
  Actions workflow files, `charts/nextcloud/README.md`, and removes
  `charts/nextcloud/values-metrics.yaml` as part of a docs restructuring that
  renames `metrics.serviceMonitor.*` → `prometheus.serviceMonitor.*` in the
  README. **No template, no values-schema, no cronjob/upgrade logic changed.**
  This HelmRelease does not set a `prometheus.serviceMonitor.*` or
  `metrics.serviceMonitor.*` key at all (metrics block only configures the
  exporter sidecar image/service), so the doc rename has zero effect here.

Net effect: bumping `chart.spec.version` to `9.2.6` with `image.tag` left at
`34.0.3` changes **no running software** — the Nextcloud application version,
the notify-push binary, the mariadb/redis wiring, and the metrics exporter are
all untouched. The only observable effect is a `helm.sh/chart` label bump on
the rendered Deployment/CronJob, which forces one ordinary rolling restart
(no image change, no `occ upgrade`, no migration).

**Verdict: the hold's own premise (chart+image coupling forcing an occ
migration) is a false positive for this specific target.** `risk: low` is set
accordingly. The plan still routes through a window (not fully unattended)
because this repo's default posture for any nextcloud touch is attended, and
because the Mail-app/maintenance-mode trap is real for *this component* in
general — Verification below treats it as a first-class check rather than an
afterthought, and Rollback carries the full recovery recipe in case a future
occ_upgrade path fires unexpectedly (e.g. if Flux ever reconciles with
`image.tag` unset, falling through to the chart default).

## 2. Pre-checks

```bash
# 0. Confirm target chart version is actually published
curl -s https://nextcloud.github.io/helm/index.yaml | python3 -c "
import sys, yaml
d = yaml.safe_load(sys.stdin)
for e in d['entries']['nextcloud']:
    if e['version'] in ('9.2.5', '9.2.6'):
        print(e['version'], e.get('appVersion'), e.get('created'))
"
# expect: 9.2.6 34.0.3 ...   and   9.2.5 34.0.2 ...

# 1. HelmRelease currently healthy, on the expected starting version
kubectl get helmrelease -n office nextcloud \
  -o jsonpath='{.spec.chart.spec.version}{"  live="}{.status.history[0].chartVersion}{"  ready="}{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
# expect: 9.2.5  live=9.2.5  ready=True

# 2. App is healthy and NOT already mid-migration/maintenance before we touch anything
kubectl -n office exec deploy/nextcloud -c nextcloud -- php occ status
# expect: maintenance: false, needsDbUpgrade: false, versionstring: 34.0.3

# 3. Backups are fresh for both PVCs this Deployment depends on
kubectl get volumes -n storage \
  -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt --no-headers \
  | grep -E 'nextcloud-config|nextcloud-mariadb'
# expect: both timestamps within the last 24h (daily 03:00 Longhorn backup cycle).
# If either is stale, trigger a manual backup first (docs/sops/backup.md Example 1)
# and re-check before proceeding — this is the household's file/mail/contacts store.

# 4. No in-flight related reconcile and no conflicting plan armed
flux get helmrelease -n office nextcloud
grep -n '^status:\|^window:' runbooks/maintenance/plans/bitnamilegacy-exit-nextcloud-db.md
# expect: status: blocked, window: null (i.e. NOT scheduled into this or any window —
# if that ever changes, do not run this plan in the same window; see conflicts_with)

# 5. Nextcloud-cron is currently completing cleanly (baseline for post-upgrade check)
kubectl get jobs -n office -l app.kubernetes.io/component=cronjob --sort-by=.status.startTime | tail -3
```

## 3. Steps

```bash
# 1. Bump the chart version only — image.tag stays 34.0.3 (already matches
#    chart 9.2.6's appVersion default; do NOT remove or change the explicit
#    image.tag override).
#    File: kubernetes/apps/office/nextcloud/app/helmrelease.yaml
```

Edit:
```yaml
  chart:
    spec:
      chart: *app
      version: 9.2.6      # was 9.2.5
```

```bash
# 2. Diff to confirm this is the ONLY line changed
git diff kubernetes/apps/office/nextcloud/app/helmrelease.yaml

# 3. Commit + push (operator commits — this plan file does not)
git add kubernetes/apps/office/nextcloud/app/helmrelease.yaml
git commit -m "chore(nextcloud): bump chart 9.2.5 -> 9.2.6 (appVersion default 34.0.3, already pinned)"
git push

# 4. Let Flux reconcile normally — no forced reconcile needed for a patch chart bump
flux get helmrelease -n office nextcloud --watch
```

No alert silence or `update-marker.sh` is required per §1's risk assessment
(no image change, no occ migration expected) — but if the operator prefers
defense-in-depth given the component's history, a short 30 min silence is
harmless:
```bash
runbooks/update-marker.sh add nextcloud office 1 "chart 9.2.5->9.2.6 (no app version change)"
```

## 4. Verification

```bash
# HelmRelease reconciled to 9.2.6 and Ready
kubectl get helmrelease -n office nextcloud \
  -o jsonpath='{.status.history[0].chartVersion}{"  ready="}{.status.conditions[?(@.type=="Ready")].status}{"\n"}'
# expect: 9.2.6  ready=True

# Pod rolled (new pod, template hash changed) and stable
kubectl get pods -n office -l app.kubernetes.io/component=app
kubectl get pods -n office -l app.kubernetes.io/component=app \
  -o jsonpath='{.items[0].spec.containers[?(@.name=="nextcloud")].image}{"\n"}'
# expect: docker.io/nextcloud:34.0.3 (UNCHANGED from pre-check — proves no image bump rode along)

# CONTENTS ASSERTION (auth/app-health class): occ status is healthy AND the
# Mail app + our custom openclaw_mail app are both loaded and enabled — this is
# the exact property the historical trap breaks (occ working at all, and the
# Mail app surviving app-compat re-validation), not a proxy for it.
kubectl -n office exec deploy/nextcloud -c nextcloud -- php occ status
# expect: maintenance: false, needsDbUpgrade: false, versionstring: 34.0.3 (unchanged)

kubectl -n office exec deploy/nextcloud -c nextcloud -- php occ app:list | grep -A2 '^Enabled:' | grep -i mail
# expect: mail app listed under Enabled (official Nextcloud "Mail" app — the
# component that broke in the 2026-06-06 incident)

kubectl -n office exec deploy/nextcloud -c nextcloud -- php occ app:list | grep -i openclaw_mail
# expect: openclaw_mail listed under Enabled (our custom draft-attachment app)

# cron still completing (not stuck on a broken occ)
kubectl create job --from=cronjob/nextcloud-cron -n office nextcloud-cron-verify-$(date +%H%M)
kubectl get jobs -n office | grep nextcloud-cron-verify
# expect: Completed, not Error, within ~1-2 min

# Functional smoke test: log into https://drive.${SECRET_DOMAIN} and open Mail
# (both the official Mail app tab and confirm a draft with attachment still
# works via openclaw_mail) — the occ-level checks above prove the app is
# loaded; this proves it actually serves.
```

## 5. Rollback

Since `image.tag` does not change, rollback is a plain chart-version revert —
no data migration to undo:

```bash
git revert --no-edit <commit-sha-from-step-3>
git push
flux get helmrelease -n office nextcloud --watch
# expect: chartVersion back to 9.2.5, Ready=True, same image:34.0.3 pod
```

**If, contrary to this investigation, an occ migration DID fire** (e.g. Flux
picked up a values change that let `image.tag` fall through to the chart
default, or a future re-run of this plan targets a chart version whose
appVersion genuinely differs from the pinned tag), use the full recovery
recipe before reverting git, because an interrupted `occ upgrade` must be
finished, not rolled back underneath:

```sh
kubectl -n office exec -it deploy/nextcloud -c nextcloud -- sh
# 1. move the broken app aside so occ can load at all
mv /var/www/html/custom_apps/mail /var/www/html/custom_apps/mail.broken
php occ status                       # confirms occ works again
# 2. finish the interrupted upgrade (runs pending migrations, exits maintenance)
php occ upgrade
php occ maintenance:mode --off
# 3. reinstall Mail cleanly
rm -rf /var/www/html/custom_apps/mail.broken
php occ app:install mail
# 4. re-force-enable anything occ upgrade silently disabled (seen before:
#    google_synchronization — check compat-disabled apps)
php occ app:list | grep -B5 '^Disabled:'
php occ app:enable --force <app>     # for anything that shouldn't be disabled
# 5. re-enable our custom app if it also dropped out
php occ app:enable openclaw_mail
```
Then verify per §4, and only revert the git commit once `occ status` is clean
(reverting git while maintenance mode is stuck does not fix a half-run
migration — finish or explicitly abort it first).

## 6. Interference notes

- **`conflicts_with: [bitnamilegacy-exit-nextcloud-db]`** — that plan replaces
  the bundled `mariadb` subchart with an external `nextcloud-db` Deployment by
  editing this SAME `helmrelease.yaml` (`mariadb.enabled: false` +
  `externalDatabase.host`) and fully restarts `deployment/nextcloud`. It is
  currently `status: blocked` (rolled back 2026-08-19 after a 4-byte-charset
  dump issue) with `window: null` — not armed for any upcoming window as of
  2026-09-05. If it is ever re-armed, do not schedule it in the same window as
  this plan: sequence this chart bump first (it's a no-op restart) or defer it
  until after the DB replatform lands, to avoid two `helmrelease.yaml` edits
  racing through Flux reconciliation in the same window.
- **`bitnamilegacy-exit-nextcloud-redis` is `status: executed`** (2026-08-19)
  — no interference; redis is already on the standalone `nextcloud-redis`
  Deployment and this plan's values diff doesn't touch redis wiring at all.
- No shared infra (ingress, cert-manager, cilium, coredns, a shared DB,
  Longhorn) is perturbed — `touches.shared: []`. `nextcloud-data` (CIFS,
  `cifs-nextcloud-data`, `Retain`) is not touched by this plan; storage-safety
  pre-flight does not apply here since no PVC operation occurs.
- Biggest danger if this plan is ever reused as a template for a REAL
  nextcloud image bump: do not copy §3's "no silence needed" shortcut forward
  — that judgment is specific to this bump having zero app-version delta. Any
  future bump that actually changes `image.tag` must follow the full attended
  procedure in `docs/sops/application-update.md` (silence, disable rollback,
  watch the occ upgrade) and the recovery recipe in §5 should be treated as
  the expected path, not a break-glass exception.
