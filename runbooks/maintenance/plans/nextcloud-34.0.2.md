---
plan_id: nextcloud-34.0.2
component: nextcloud
pr: null                            # no open Renovate PR found via gh at plan time
                                    # (2026-08-02); version-check-current lists the
                                    # available bump (chart 9.2.2→9.2.5 / image
                                    # 34.0.1→34.0.2). Fill in if/when Renovate opens one.
kind: chart                         # chart bump (9.2.2→9.2.5) that carries the server
                                    # image bump (34.0.1→34.0.2) — move both together
current: "9.2.2 / 34.0.1"           # chart / image
target: "9.2.5 / 34.0.2"            # chart / image
update_type: patch                  # upstream is a genuine patch (see §1); hold is
                                    # about THIS cluster's occ-migration trap, not the diff
risk: medium                        # occ upgrade runs on pod start → the documented
                                    # Mail-app / stuck-maintenance-mode trap on this cluster
est_duration_min: 40
needs_reboot: false                 # pods roll in place (Recreate); no node reboot
touches:
  namespaces: [office]
  resources:
    - helmrelease/nextcloud
    - deployment/nextcloud                     # main app pod — Recreate; runs `occ upgrade`
                                               # on start (brief maintenance mode)
    - deployment/nextcloud-notify-push         # sidecar Deployment, image must match server
    - statefulset/nextcloud-mariadb            # occ migrations run AGAINST it (NOT upgraded)
    - deployment/nextcloud-redis-master        # bounced only if chart re-renders redis; auth off
    - cronjob/nextcloud-cron                    # runs `occ` each tick — breaks if mail app corrupts
    - pvc/nextcloud-config                      # Longhorn — holds custom_apps + config + themes
    - pvc/nextcloud-mariadb                     # Longhorn — the DB the migration mutates
    - pvc/nextcloud-data                        # CIFS/NAS (cifs-nextcloud-data, 300Gi) — user files;
                                               # NOT touched by the schema migration, NOT Longhorn-backed
  shared: []                        # self-contained in `office`: own mariadb + redis, own login
                                    # (NOT behind authentik forward-auth). Uses the `external`
                                    # ingress class + Cloudflare tunnel but does NOT perturb the
                                    # ingress-controller. See Interference notes for DEPENDENTS
                                    # (nextcloud-mcp, whiteboard-proxy, openclaw mail-draft API).
depends_on: []
conflicts_with: []                  # none hard; do NOT co-schedule a nextcloud-mcp upgrade or
                                    # anything that depends on nextcloud being reachable (see §6)
status: draft
window: "thu-early:2026-08-13"      # no-reboot ⇒ weekday. SOLO — do NOT co-schedule
                                    # the nextcloud-mcp bump here (isolate the occ
                                    # migration; mcp follows in the NEXT window once
                                    # this nextcloud is verified healthy).
auto_execute: false                 # medium + occ-migration trap → operator go/no-go always
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
generated: "2026-08-02"
---

# nextcloud 9.2.2 → 9.2.5 (server 34.0.1 → 34.0.2) — chart + image, moved together

## 1. Summary & why held

**What changes:** a coordinated patch bump in
`kubernetes/apps/office/nextcloud/app/`:
- `helmrelease.yaml` `spec.chart.spec.version: 9.2.2 → 9.2.5` (chart line 11)
- `helmrelease.yaml` `image.tag: 34.0.1 → 34.0.2` (server image, line 34)
- `helmrelease.yaml` `worker` extraSidecar `image: nextcloud:34.0.1 → 34.0.2` (line 276)
- `notify-push.yaml` Deployment `image: nextcloud:34.0.1 → 34.0.2` (line 38)

**Why chart AND image must move together (not just the chart):** the HelmRelease
**explicitly pins `image.tag` in values**, which overrides the chart's default
appVersion. Chart 9.2.5's only material change over 9.2.2 is bumping its default
image tag to `34.0.2` (per the 9.2.5 release: *"Updated docker.io/library/nextcloud
image tag to 34.0.2"*). Because our explicit pin wins, **bumping the chart alone
would leave the server on 34.0.1** — and conversely bumping the image without the
chart drifts from the chart's tested pairing. The `worker` sidecar and the
`notify-push` Deployment both run the **same `nextcloud:<tag>` binary** against the
same PVCs, and the `notify_push` binary must match the server version
(notify-push.yaml already carries the "keep in lockstep" note — it caused ~12
fixable CRITICAL CVEs when it lagged the server on 2026-07-31). So all four pins
move to `34.0.2` / `9.2.5` in one commit.

**Target verified published (2026-08-02):**
- `docker.io/library/nextcloud:34.0.2` → HTTP 200.
- Chart `nextcloud-9.2.5` present on GitHub releases; its default appVersion is
  exactly `34.0.2` (so chart + our pin agree).

**Upstream is a genuine patch — no breaking change, no documented migration.**
Nextcloud **34.0.2** (released 2026-07-23) is a **maintenance + security patch** in
the 34.x line: DAV PROPFIND streaming perf, carddav photocache disk reduction, IP
check caching, code-signing revocation + CA-bundle updates, assorted sharing/CalDAV/
preview/UI fixes and dependency bumps. The changelog notes **no breaking changes and
no new database migrations**. The chart 9.2.3→9.2.5 range is image-tag bumps with no
values-schema or template breakage. So the **content risk is low**.

**Why it was held (this is not a false positive):** on THIS cluster, bumping the
nextcloud **image tag** runs `occ upgrade` on pod start, and that has a documented
history of biting (memory `project_nextcloud_upgrade_mailapp`, incidents 2026-06-06
and 2026-06-11):
1. **The appstore `mail` app's bundled `vendor/` can come out incomplete** after an
   `occ upgrade` (`Failed opening required '.../mail/vendor/.../utf8.php'`). Because
   app registration runs on every `occ`/cron init, this makes **all `occ` commands
   and every `nextcloud-cron` pod fail** — the web `status.php` still returns 200, so
   it silently rots rather than paging.
2. **Maintenance mode can stick ON** if the readiness/startup probe restarts the pod
   mid-`occ upgrade` (the exit-maintenance + app migrations never finish).
3. **Force-enabled apps get silently re-disabled** by `occ upgrade` (last time it
   disabled `google_synchronization`, surfaced 4 days later as a stale-OAuth finding).

None of that is auto-detectable as safe, so the auto-updater correctly routed it to a
window. `risk: medium` is set by this occ-migration trap, **not** by the upstream diff.

## 2. Pre-checks

Run from repo root (`cd /Users/mu/code/cberg-home-nextgen`). **All must pass before
the bump.**

```bash
# 2.1 nextcloud currently healthy on 9.2.2 / 34.0.1 — HR Ready, app pod Running
mise exec -- kubectl get helmrelease -n office nextcloud \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# Expected: "True 9.2.2"
mise exec -- kubectl get pods -n office -l app.kubernetes.io/instance=nextcloud
# Expected: nextcloud app pod Running (0 restarts), nextcloud-mariadb-0 Running,
#           nextcloud-redis-master-0 Running, nextcloud-notify-push Running.

# 2.2 occ baseline: NOT already in maintenance mode, and NO in-flight occ upgrade.
POD=$(mise exec -- kubectl get pods -n office -l app.kubernetes.io/component=app \
  -o jsonpath='{.items[0].metadata.name}')
mise exec -- kubectl exec -n office "$POD" -c nextcloud -- php occ status
# Expected: installed: true, maintenance: false, needsDbUpgrade: false,
#           versionstring 34.0.1. If maintenance:true or needsDbUpgrade:true → STOP
#           (a prior upgrade didn't finish; resolve that first, see §5 recovery).

# 2.3 The Mail app + custom apps load cleanly RIGHT NOW (so a post-upgrade break is
#     attributable, and so we know the pre-state is good).
mise exec -- kubectl exec -n office "$POD" -c nextcloud -- php occ app:list \
  | sed -n '1,120p'
# Expected: `occ app:list` returns WITHOUT an autoload/vendor fatal. Note whether the
#           appstore `mail` app and `openclaw_mail` are in the Enabled section, and
#           whether `google_synchronization` is Enabled (it is force-enabled — record
#           it; occ upgrade may silently disable it, §4.4).

# 2.4 nextcloud-cron is currently succeeding (Completed, not Error) — the canary for
#     the mail-app-corrupts-occ trap.
mise exec -- kubectl get pods -n office -l app.kubernetes.io/component=cron \
  --sort-by=.metadata.creationTimestamp | tail -3
# Expected: recent cron pods Completed, none Error.

# 2.5 FRESH Longhorn backup (< 24h) of the DB + config volumes — the recovery floor
#     for the schema migration. The migration mutates the MariaDB schema; custom_apps
#     + config live on nextcloud-config. BOTH are Longhorn-backed.
mise exec -- kubectl get volumes -n storage \
  -o custom-columns=NAME:.metadata.name,LAST_BACKUP:.status.lastBackupAt --no-headers \
  | grep -Ei 'nextcloud-mariadb|nextcloud-config'
# Expected: both show a lastBackupAt within 24h. If not, trigger one and WAIT for it
#           (docs/sops/backup.md §Pre-Upgrade):
#   mise exec -- kubectl create job --from=cronjob/backup-of-all-volumes \
#     pre-nc-34-0-2-$(date +%Y%m%d-%H%M) -n storage
#   mise exec -- kubectl wait --for=condition=complete \
#     job/pre-nc-34-0-2-<stamp> -n storage --timeout=3600s
# NOTE: user file DATA is on the NAS SMB share (cifs-nextcloud-data, 300Gi) and is
#       NOT covered by Longhorn backup — but the occ SCHEMA migration does not touch
#       file bytes, only the DB. The DB + config backup is the correct recovery floor
#       here. (NAS-side data protection is a separate, out-of-scope concern.)

# 2.6 No in-flight Flux reconcile, and current HRs/KSs all Ready
mise exec -- flux get helmreleases -A | grep -vE "True|^NAMESPACE"   # empty
mise exec -- flux get kustomizations -A | grep -vE "True|^NAMESPACE" # empty

# 2.7 Zero firing alerts (Watchdog/InfoInhibitor excluded)
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &>/dev/null &
sleep 2
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)[\"data\"][\"alerts\"] if x[\"state\"]==\"firing\" and x[\"labels\"][\"alertname\"] not in (\"Watchdog\",\"InfoInhibitor\")]
print(f\"Firing: {len(a)}\")"
kill %1 2>/dev/null'
# Expected: Firing: 0
```

**Go criteria:** HR Ready on 9.2.2; app + mariadb + redis + notify-push Running;
`occ status` maintenance:false / needsDbUpgrade:false on 34.0.1; `occ app:list` loads
without a vendor fatal (mail + openclaw_mail + google_synchronization states recorded);
cron pods Completed; Longhorn backup of nextcloud-mariadb + nextcloud-config < 24h; all
Flux Ready; 0 firing alerts. Any failure → **stop and surface**.

## 3. Steps

GitOps only. The maintenance-window-agent delegates the git changes to `cberg-agent`;
the occ recovery actions in §5 are in-cluster `kubectl exec` (operator-present) used
ONLY if verification fails.

### 3a. Silence rollout noise + drop an active-update marker

The Recreate roll (app pod down→up) + notify-push roll will fire `KubePod*` /
`nextcloud*` noise (and `KubeDeploymentReplicasMismatch` while the single app pod is
recreating). Suppress it (application-update.md §Step 1):

```bash
cd /Users/mu/code/cberg-home-nextgen
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &>/dev/null &
sleep 2
NOW=$(python3 -c "from datetime import *;print(datetime.now(timezone.utc).strftime(\"%Y-%m-%dT%H:%M:%S.000Z\"))")
END=$(python3 -c "from datetime import *;print((datetime.now(timezone.utc)+timedelta(hours=2)).strftime(\"%Y-%m-%dT%H:%M:%S.000Z\"))")
curl -s -X POST localhost:9093/api/v2/silences -H "Content-Type: application/json" -d "{
  \"matchers\":[{\"name\":\"namespace\",\"value\":\"office\",\"isRegex\":false,\"isEqual\":true},
              {\"name\":\"alertname\",\"value\":\"nextcloud.*|Kube(Pod|Deployment).*\",\"isRegex\":true,\"isEqual\":true}],
  \"startsAt\":\"$NOW\",\"endsAt\":\"$END\",\"createdBy\":\"operator\",
  \"comment\":\"nextcloud 9.2.2/34.0.1->9.2.5/34.0.2 upgrade — rollout noise. auto-expires 2h\"}"
kill %1 2>/dev/null'

runbooks/update-marker.sh add nextcloud office 2 "9.2.2/34.0.1->9.2.5/34.0.2 chart+image"
```

### 3b. Bump the chart + all three image pins in git (move together)

```bash
cd /Users/mu/code/cberg-home-nextgen

# chart version (1 hit) + image tag/worker sidecar (2 hits) in the HelmRelease
sed -i '' 's/version: 9\.2\.2/version: 9.2.5/' \
  kubernetes/apps/office/nextcloud/app/helmrelease.yaml
sed -i '' 's/34\.0\.1/34.0.2/g' \
  kubernetes/apps/office/nextcloud/app/helmrelease.yaml
# notify-push Deployment image (1 hit) — must match the server
sed -i '' 's/34\.0\.1/34.0.2/g' \
  kubernetes/apps/office/nextcloud/app/notify-push.yaml

# Verify EXACTLY the intended lines changed: chart 9.2.5 (x1), 34.0.2 (x3 total)
grep -n "9.2.5"  kubernetes/apps/office/nextcloud/app/helmrelease.yaml   # 1 hit (chart version)
grep -rn "34.0.2" kubernetes/apps/office/nextcloud/app/                  # 3 hits total
grep -rn "34.0.1\|9.2.2" kubernetes/apps/office/nextcloud/app/           # MUST be empty
git diff kubernetes/apps/office/nextcloud/app/helmrelease.yaml \
         kubernetes/apps/office/nextcloud/app/notify-push.yaml

git add kubernetes/apps/office/nextcloud/app/helmrelease.yaml \
        kubernetes/apps/office/nextcloud/app/notify-push.yaml
git commit -m "feat(nextcloud): update chart + image ( 9.2.2 → 9.2.5 / 34.0.1 → 34.0.2 )"
git push
```

> If a Renovate PR is opened later, confirm it bumps **all four** pins (chart version,
> `image.tag`, the `worker` sidecar `nextcloud:` image, and the `notify-push`
> Deployment image). Renovate has historically bumped only the chart/tag lines and
> left the sidecar/notify-push images behind — do not merge a PR that leaves any of
> them on `34.0.1`.

### 3c. Reconcile and watch the occ upgrade complete (do NOT let the pod thrash)

```bash
mise exec -- flux reconcile helmrelease -n office nextcloud --with-source
# Recreate strategy: old app pod terminates, new one starts and runs `occ upgrade`.
# Watch the NEW app pod's logs for the migration to finish and maintenance to clear:
mise exec -- kubectl logs -n office -l app.kubernetes.io/component=app -c nextcloud -f \
  | grep -iE "maintenance|upgrade|migrat|error|Init"
# Look for: "Turned on maintenance mode" → migrations → "Turned off maintenance mode"
#           → "Update successful". Ctrl-C once it settles Running/Ready.
```

The app pod's `startupProbe` allows ~5 min (10×30s) before it kills the pod, which
should be enough for a patch `occ upgrade`. If the migration is slow and the pod is
about to be killed mid-upgrade (the exact cause of a stuck maintenance mode), **do not
let it loop** — jump to §5 recovery (finish the upgrade by hand inside the pod).
`upgrade.remediation.retries: 3` + `cleanupOnFail: true` stay as-is (a patch does not
justify disabling rollback), but if you see a rollback thrash, disable it per
application-update.md §Step 2 and retry.

## 4. Verification

```bash
POD=$(mise exec -- kubectl get pods -n office -l app.kubernetes.io/component=app \
  -o jsonpath='{.items[0].metadata.name}')

# 4.1 HR reconciled + Ready on the new chart
mise exec -- kubectl get helmrelease -n office nextcloud \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].chartVersion}{"\n"}'
# Expected: "True 9.2.5"

# 4.2 NOT stuck in maintenance mode; DB upgrade done; version is 34.0.2
mise exec -- kubectl exec -n office "$POD" -c nextcloud -- php occ status
# Expected: maintenance: false, needsDbUpgrade: false, versionstring 34.0.2.
#           If maintenance:true → §5 recovery.

# 4.3 occ commands + app registration work (the mail-app-vendor canary): app:list
#     must load WITHOUT an autoload/vendor fatal.
mise exec -- kubectl exec -n office "$POD" -c nextcloud -- php occ app:list | sed -n '1,120p'
# Expected: returns cleanly. Confirm the appstore `mail` app AND `openclaw_mail` are
#           in Enabled (not errored). If a "Failed opening required .../mail/vendor/..."
#           fatal appears → §5 recovery (move mail aside, reinstall).

# 4.4 Force-enabled apps NOT silently disabled by occ upgrade. Compare to the Pre-check
#     2.3 baseline — re-enable anything that moved to Disabled (esp. google_synchronization):
mise exec -- kubectl exec -n office "$POD" -c nextcloud -- php occ app:list \
  | sed -n '/Disabled:/,$p'
# If google_synchronization (or another previously-enabled app) is now Disabled:
#   mise exec -- kubectl exec -n office "$POD" -c nextcloud -- \
#     php occ app:enable --force google_synchronization
# CAVEAT (memory): re-enabling does NOT recreate per-user sync jobs — if the OAuth
# token_expires_at stays frozen >1h, the operator must open Nextcloud → Settings →
# Google synchronization once to re-register the sync (stored token survives).

# 4.5 openclaw_mail custom app materialized + enabled (init container re-copies it from
#     the ConfigMap every boot; the worker sidecar enables it):
mise exec -- kubectl exec -n office "$POD" -c nextcloud -- \
  ls /var/www/html/custom_apps/openclaw_mail/appinfo/info.xml
mise exec -- kubectl exec -n office "$POD" -c nextcloud -- \
  php occ app:list | grep -i openclaw_mail
# Expected: info.xml present; openclaw_mail Enabled.

# 4.6 nextcloud-cron succeeds post-upgrade (proves occ init is healthy):
mise exec -- kubectl create job --from=cronjob/nextcloud-cron nc-cron-check-$(date +%H%M) -n office
mise exec -- kubectl get pods -n office -l app.kubernetes.io/component=cron \
  --sort-by=.metadata.creationTimestamp | tail -2
# Expected: the check job pod reaches Completed (not Error).

# 4.7 All three images actually rolled to 34.0.2 (server + worker sidecar + notify-push):
mise exec -- kubectl get deploy -n office nextcloud nextcloud-notify-push \
  -o custom-columns=NAME:.metadata.name,IMAGES:'.spec.template.spec.containers[*].image'
# Expected: nextcloud (app+worker) and nextcloud-notify-push all on nextcloud:34.0.2.
mise exec -- kubectl get pods -n office -l app.kubernetes.io/name=nextcloud-notify-push
# Expected: notify-push Running on the new image.

# 4.8 App reachable + data intact: log in at https://drive.<DOMAIN>, confirm files
#     list loads (NAS data intact), and the notify-push websocket connects (Files app
#     shows live updates / no "notify_push" admin warning). Send a test via the Mail
#     app to confirm the mail path works.

# 4.9 Zero firing alerts once the silence is dropped
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &>/dev/null &
sleep 2
curl -s http://localhost:9090/api/v1/alerts | python3 -c "
import sys,json
a=[x for x in json.load(sys.stdin)[\"data\"][\"alerts\"] if x[\"state\"]==\"firing\" and x[\"labels\"][\"alertname\"] not in (\"Watchdog\",\"InfoInhibitor\")]
print(f\"Firing: {len(a)}\")"
kill %1 2>/dev/null'
# Expected: Firing: 0
```

**Success =** HR Ready on 9.2.5; `occ status` maintenance:false / needsDbUpgrade:false
on 34.0.2; `occ app:list` loads cleanly with mail + openclaw_mail enabled and no
force-enabled app dropped; a fresh nextcloud-cron job Completes; all three images on
34.0.2; login + file list + notify-push + Mail all work; 0 firing alerts.

### On success — clear silence + marker

```bash
runbooks/update-marker.sh clear nextcloud
mise exec -- bash -c 'kubectl port-forward -n monitoring svc/kube-prometheus-stack-alertmanager 9093:9093 &>/dev/null &
sleep 2
curl -s localhost:9093/api/v2/silences | python3 -c "
import sys,json
for s in json.load(sys.stdin):
  if \"nextcloud 9.2.2/34.0.1->9.2.5/34.0.2\" in s.get(\"comment\",\"\"): print(s[\"id\"])" | \
  xargs -I{} curl -s -X DELETE localhost:9093/api/v2/silences/{}
kill %1 2>/dev/null'
```

## 5. Rollback / recovery

Two distinct failure modes. **Try the in-place occ recovery FIRST for a stuck
maintenance mode / broken Mail app** (a full git revert re-runs the same occ path and
usually will not un-stick it) — reserve the git revert for a genuinely bad chart roll.

### 5a. Stuck maintenance mode / broken Mail app (the documented trap) — recover in place

From memory `project_nextcloud_upgrade_mailapp`. Exec into the running app pod,
container `nextcloud`:

```bash
POD=$(mise exec -- kubectl get pods -n office -l app.kubernetes.io/component=app \
  -o jsonpath='{.items[0].metadata.name}')

# 1. If the appstore `mail` app's vendor/ is corrupt (occ commands fatal), move it
#    aside so occ can load at all:
mise exec -- kubectl exec -n office "$POD" -c nextcloud -- \
  mv /var/www/html/custom_apps/mail /var/www/html/custom_apps/mail.broken
mise exec -- kubectl exec -n office "$POD" -c nextcloud -- php occ status   # should work now

# 2. Finish the interrupted upgrade (runs pending migrations, exits maintenance):
mise exec -- kubectl exec -n office "$POD" -c nextcloud -- php occ upgrade
mise exec -- kubectl exec -n office "$POD" -c nextcloud -- php occ maintenance:mode --off

# 3. Reinstall the Mail app cleanly (re-downloads from appstore, re-enables):
mise exec -- kubectl exec -n office "$POD" -c nextcloud -- \
  rm -rf /var/www/html/custom_apps/mail.broken
mise exec -- kubectl exec -n office "$POD" -c nextcloud -- php occ app:install mail

# 4. Re-force-enable anything occ upgrade dropped (see Verification 4.4), then re-run
#    Verification 4.2–4.6 (occ status clean, app:list loads, cron Completes).
```
> `custom_apps` lives on the persistent `nextcloud-config` (Longhorn) PVC, so these
> edits survive pod restarts. `openclaw_mail` does NOT need this dance — the init
> container re-materializes it from the ConfigMap on every boot; if it's missing,
> just restart the pod.

### 5b. Bad chart roll (HR won't go Ready / app crash-loops on something other than the
occ trap) — git revert

```bash
cd /Users/mu/code/cberg-home-nextgen
git log --oneline -5 -- kubernetes/apps/office/nextcloud/app/helmrelease.yaml
git revert --no-edit <bump-commit-sha>      # restores chart 9.2.2 + all 3 image pins to 34.0.1
git push
mise exec -- flux reconcile helmrelease -n office nextcloud --with-source
mise exec -- kubectl rollout status deploy/nextcloud -n office --timeout=10m

# If helm is wedged pending-upgrade after a failed migration:
#   mise exec -- helm rollback nextcloud <last-deployed-rev> -n office --wait=false
#   mise exec -- flux reconcile helmrelease -n office nextcloud --force
```

> **Caveat — downgrade + the DB:** `occ upgrade` migrations are generally not
> reversible. If 34.0.2 migrations ran and then you revert the image to 34.0.1, the
> 34.0.1 binary may refuse to start against a newer schema. If that happens, the
> **Longhorn backup of nextcloud-mariadb + nextcloud-config from Pre-check 2.5 is the
> recovery floor** — restore both volumes together (docs/sops/backup.md §Restore) to
> the pre-upgrade point, then reconcile on 34.0.1. This is why the fresh backup is a
> hard go-criterion. In practice, prefer §5a (finish forward) over downgrading.

**Confirm cluster is back:** HR Ready (on 9.2.5 after 5a, or 9.2.2 after 5b),
`occ status` maintenance:false / needsDbUpgrade:false, `occ app:list` loads, a fresh
nextcloud-cron job Completes, login + file list work. Clear the update marker and drop
the silence.

## 6. Interference notes

- **Operator-present, non-reboot window.** `needs_reboot: false`. Risk weight 2, but
  the occ-migration trap needs a human at the keyboard to run §5a if maintenance mode
  sticks — assign to an **attended** slot, not an unattended one. ~40 min budget
  (backup check + bump + reconcile + occ-upgrade watch + the app-list/cron/mail
  verification + interactive login). `auto_execute: false` is deliberate.
- **`shared: []` — self-contained.** nextcloud runs its own MariaDB + Redis in
  `office`, uses its own login (NOT behind authentik forward-auth), and does not
  perturb the ingress-controller or any shared DB. No cluster-wide blast radius.
- **Brief self-outage during the Recreate roll.** `strategy: Recreate` means the
  single app pod is fully down for the ~1–3 min the new pod takes to start + run
  `occ upgrade` (longer if §5a is needed). During that window `drive.<DOMAIN>` returns
  502/maintenance. Schedule accordingly.
- **DEPENDENTS in the same namespace break transiently — do NOT co-schedule their
  upgrades in this window:**
  - `nextcloud-mcp` (office) talks to the nextcloud API — a pending
    `nextcloud-mcp` **major** bump (3.7.3→5.0.0) exists; keep it in a **separate**
    window and run it *after* this one is verified.
  - `whiteboard-proxy` and the `openclaw_mail` draft API (POST
    `/apps/openclaw_mail/api/draft`, used by OpenClaw) depend on nextcloud being up —
    they'll error during the roll and recover on their own once nextcloud is Ready.
    If OpenClaw is mid-task, expect draft/mail failures during the window.
- **notify-push must not be forgotten.** A "successful" server bump that leaves
  `nextcloud-notify-push` on `34.0.1` re-opens the exact CVE lag that was fixed on
  2026-07-31 (Verification 4.7 gates this). The window agent must not mark the plan
  executed until all three images read `34.0.2`.
- **The occ trap is the whole reason this is a plan and not an auto-merge.** After the
  roll, `occ status` (maintenance flag) + `occ app:list` (mail vendor) + a fresh cron
  job (Completed, not Error) are the three signals that distinguish "done" from the
  silent-rot failure where `status.php` still returns 200 while every `occ`/cron run
  fails. Do not declare success on HR-Ready alone.
