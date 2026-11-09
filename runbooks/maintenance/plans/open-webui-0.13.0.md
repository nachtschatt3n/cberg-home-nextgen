---
plan_id: open-webui-0.13.0
component: open-webui
pr: 334                               # Renovate PR for the CHART half (17.0.0 -> 17.5.0). The image half (v0.12.5 -> v0.13.0)
                                      # has no PR (coverage.py PLAN lane, no Renovate PR). Both land in ONE commit here (§1.2).
kind: image                           # image + chart in one plan; image is the migrating half
current: "image ghcr.io/open-webui/open-webui:v0.12.5 + chart open-webui 17.0.0 (redis sidecar 8.10.1-alpine and pipelines main@sha256:b48e9bc3... stay pinned)"
target: "image ghcr.io/open-webui/open-webui:v0.13.0 + chart open-webui 17.5.0 (redis sidecar tag and pipelines digest NOT moved by this plan, see §1.5)"
update_type: minor                    # semver minor at app major 0 = the breaking axis. 3 new forward-only alembic revisions.
risk: medium                          # Additive-only migrations (2 CREATE TABLE sets + 1 ADD COLUMN with a default, no backfill, no table
                                      # copy), but they run in place on the only copy of every chat/model/user (sqlite on
                                      # pvc open-webui-20g), the release is HOURS old (tag published 2026-11-03T12:23Z, no soak,
                                      # no patch release yet) and its security advisories are not yet published.
est_duration_min: 40                  # pre-checks + DB copy 10 · commit/reconcile/pull 8 · migrations <1 · verification 15 ·
                                      # retries-restore commit 3 · attended browser check 4
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/open-webui
    - statefulset/open-webui            # image v0.12.5 -> v0.13.0 AND pod-template labels (chart); runs alembic on start (init copy-app-data too)
    - deployment/open-webui-redis       # ROLLS: its pod-template labels (helm.sh/chart, app.kubernetes.io/version) change with the chart
                                        # (helm template 17.0.0 vs 17.5.0, §1.2). Image tag 8.10.1-alpine unchanged. No PVC, no auth.
    - pvc/open-webui-20g                # webui.db migrated in place; pre-copy written beside it (§3.2)
    # NOT rolled: deployment/open-webui-pipelines (pod template byte-identical across 17.0.0/17.5.0/18.0.0 in the render),
    # pvc/open-webui-pipelines-new, httproute/open-webui, service/open-webui (LB 192.168.55.28), secret/open-webui-tts-secret.
  shared: [monitoring]                  # §4.3 reads Prometheus (kube-state-metrics), the window's instrument. The public route is only READ
                                        # through envoy-external in §4.6; no gateway/storage-class/DNS/CNI change.
depends_on: []
conflicts_with:
  - redis-fleet-8.10.3                  # EDITS THE SAME FILE (websocket.redis.image.tag) and rolls the same redis Deployment + restarts
                                        # open-webui's redis in its leg 4; its prose still says "chart 17.0.0 / app v0.12.5 untouched".
                                        # Never the same window; whichever runs second must re-read the live pins (§6).
  - flux-oci-chart-sources              # sun-attended:2026-12-13 - re-points the open-webui chart source and rolls statefulset/open-webui
                                        # (its inventory pins the chart version this plan changes).
  - helm-drift-detection                # sat-attended:2026-11-28 - asserts Helm revisions identical across releases; this plan makes
                                        # open-webui revisions N+1 (and N+2 in §3.5).
  # 2026-11-06: removed python-fleet-3.15.2 - plan executed in the NOW run 2026-11-06 and retired (dead ref in maintenance-plan.py --validate).
                                        # restart during §4 confounds the tool-path checks.
  - openclaw-2026.11.1                  # blocked - namespace ai roll; listed so an unblock cannot co-schedule.
  - longhorn-1.13.0                     # sun-attended:2026-11-15 - open-webui-20g is the volume we copy and may restore from.
  - talos-linux-1.14.5                  # sun-attended:2026-11-22 - node drains/reboots would confound the single-replica pod gates.
  - flux-reconciler-impersonation       # blocked - changes WHO applies the HelmRelease this plan relies on.
  - envoy-proxy-config-distroless-v1.40.0  # blocked - rolls the proxies §4.6 reads the app through.
  - envoy-proxy-config-distroless-v1.40.2  # blocked - same.
  - grafana-chart-14.4.0                      # vetted - monitoring; Grafana is the operator's second instrument for the §4.3 controls.
  # No kube-prometheus-stack-* plan is open (it rides the auto lane). If Step 0 lands a kube-prometheus-stack bump the same night,
  # serialise it: §4.3 reads Prometheus.
exclusive: false
security_ref: null                    # NOT security-driven (operator brief). Upstream says v0.13.0 carries unlisted security fixes;
                                      # the current-image findings (policy-cli finding list --grep open-webui, e.g. F-54a5f1f7) are
                                      # DB-only and are not claimed by this plan.
capability_change: true               # user-visible: comments (off by default), notification Inbox (ENABLE_NOTIFICATIONS defaults ON),
                                      # tabbed side panel / Controls moved into the model menu, tool on/off switch, higher tool-call
                                      # limit (1024) and no sub-agent limits by default (§1.4).
rollback_class: backup-restore        # FORWARD-ONLY schema: v0.12.5's run_migrations() would not find revision e42c8f710a36 in its image.
                                      # Rollback = restore webui.db.pre-0.13.0 (§5), not a git revert alone.
restore_proof: "3.2 gate (copy checked for alembic head, chat count, integrity_check) + 5.2 sha256 equality to PRE_SHA + 5.2 PASS line RESTORED_ALEMBIC/CHATS/INTEGRITY"   # SD-11 field, reviewer 2026-11-03
backup_gate: "Completed Longhorn backup of open-webui-20g < 26h (runbooks/longhorn-backup-age.py --max-hours 26 open-webui-20g exits 0, 22.5h on 2026-11-03), PLUS the in-pod sqlite online-backup copy /app/backend/data/webui.db.pre-0.13.0 taken in §3.2 immediately before the commit, with COPY_ALEMBIC 0bd252b206fb, COPY_CHATS equal to the live count and COPY_INTEGRITY ok."
finding_refs:
  - F-31c19a7f                        # version: chart open-webui 17.0.0 -> 17.5.0 (this plan's chart half)
                                      # F-e8a41b1b (open-webui redis sidecar 8.10.1 -> 8.10.3) is owned by redis-fleet-8.10.3, NOT claimed here.
                                      # No version finding for the IMAGE v0.12.5 -> 0.13.0 exists yet (policy-cli finding list --grep open-webui,
                                      # 2026-11-03); add its id here once the sweep files it.
review: ready-for-go@2026-11-03   # plan-reviewer 2026-11-03: needs-fix (restore pod spawned 2 containers, restore_proof missing), fixed, delta re-review ready-for-go; HUMAN-GATED, soak a few days / prefer v0.13.1, window null until operator GO
status: awaiting-go                 # go_no_go ingested by sat-attended:2026-11-07 (HUMAN-GATED, unattended run)
window: "now:2026-11-09"   # ON-DEMAND NOW run 2026-11-09 (run-now.py stamp; was 'sat-attended:2026-11-14')
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-11-03"
premises:
  # Read-verb only. Each was run 2026-11-03 and returned the expected value.
  - id: app-image-current
    why: >-
      current: claims v0.12.5 on the StatefulSet. v0.13.0 (or anything else) means the alembic baseline in §2.3, the migration
      list and the rollback image are wrong. Stop and re-plan.
    run: kubectl get sts open-webui -n ai -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/open-webui/open-webui:v0.12.5
  - id: chart-current
    why: >-
      The HelmRelease must still pin chart 17.0.0. 17.5.0 or 18.0.0 means the chart half already ran (or Renovate PR 334 was merged
      ahead of the image) and §3.3's sed anchors match nothing.
    run: kubectl get helmrelease open-webui -n ai -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: 17.0.0
  - id: repo-image-pin-unique
    why: §3.3 edits by exact-line sed. The image tag line must occur exactly once or the sed misses or double-hits.
    run: 'grep -c -E ''^      tag: v0\.12\.5$'' kubernetes/apps/ai/open-webui/app/helmrelease.yaml'
    expect_exact: "1"
  - id: repo-chart-pin-unique
    why: Same, for the chart version line.
    run: 'grep -c -E ''^      version: 17\.0\.0$'' kubernetes/apps/ai/open-webui/app/helmrelease.yaml'
    expect_exact: "1"
  - id: redis-sidecar-pin
    why: >-
      This plan does not move the redis tag. 8.10.3-alpine here means redis-fleet-8.10.3 ran first (fine, but then the chart-label
      redis roll in §1.2 is the only redis restart left and §4.5 still applies). Anything else is an unknown edit: stop.
    run: 'grep -c -E ''^          tag: 8\.10\.1-alpine$'' kubernetes/apps/ai/open-webui/app/helmrelease.yaml'
    expect_exact: "1"
  - id: hr-ready
    why: A HelmRelease that is already failing would mask whether this upgrade broke it.
    run: kubectl get helmrelease open-webui -n ai -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: volume-healthy
    why: The migration writes the only copy of the DB. Do not run it on a degraded volume.
    run: kubectl get volume open-webui-20g -n storage -o jsonpath='{.status.robustness}'
    expect_exact: healthy
  - id: longhorn-backup-exists
    why: >-
      A Completed Longhorn backup must exist. Freshness (< 26h) is the §2.2 longhorn-backup-age.py gate, because the premise
      runner refuses python3.
    run: kubectl get backups.longhorn.io -n storage -o jsonpath='{.items[?(@.status.volumeName=="open-webui-20g")].status.state}'
    expect_contains: Completed
---

# open-webui app v0.12.5 -> v0.13.0 + chart 17.0.0 -> 17.5.0 (one commit, one migration, one roll)

## 1. Summary & why held

### 1.1 What changes

One commit to `kubernetes/apps/ai/open-webui/app/helmrelease.yaml`:

- `spec.values.image.tag: v0.12.5 -> v0.13.0` (no Renovate PR; coverage PLAN lane)
- `spec.chart.spec.version: 17.0.0 -> 17.5.0` (Renovate PR 334)
- `spec.upgrade.remediation.retries: 1 -> 0` for the attempt only (application-update SOP Step 2), restored to `1` in a second
  commit after §4 passes.

Held by `coverage.py` as PLAN: "0.x release-line move (0.12 -> 0.13), at major 0 the minor IS the breaking axis". The chart bump is
held only by lockstep with the image ("a chart bump must move WITH it in the same window").

### 1.2 Image and chart: do they have to move in lockstep? Measured answer

**Not for correctness, only for ordering.** The chart does not drive the app here, because `values.image.tag` is pinned. Evidence
(2026-11-03, chart tarballs from the chart repo index, `helm template` with this release's exact `spec.values`, ollama/pipelines/terminals
subcharts built):

- 17.0.0 vs 17.5.0 vs 18.0.0: `diff` of the three renders shows ONLY `helm.sh/chart` and `app.kubernetes.io/version` label values
  (appVersion 0.12.0 / 0.12.5 / 0.13.0). Templates, values schema and subcharts are byte-identical. 17.1.0 to 17.5.0 CHANGELOG entries are
  all "Updated chart appVersion to ..." and nothing else.
- Those two labels sit in the pod templates of `statefulset/open-webui` AND `deployment/open-webui-redis`, so the chart bump **rolls both**.
  `deployment/open-webui-pipelines` does not roll (its pod template is unchanged). That is why the chart change belongs in the same commit
  as the image: one StatefulSet roll instead of two, and the redis restart is a known, expected part of this plan.
- The one real ordering hazard is the reverse: a chart-only move that dropped the `image.tag` pin would fall back to the chart default
  appVersion and could START an older image against a migrated DB (or the new image on an un-snapshotted DB). Never merge Renovate PR 334
  alone without the §3.2 copy; this plan keeps the tag pinned in the same edit.
- **Chart 18.0.0 exists** (appVersion 0.13.0, published 2026-11-03; CHANGELOG marks it BREAKING only as a "0.x major app, read the notes"
  warning; the render shows no template change). Renovate PR 334 and the held `new:` are 17.5.0, so this plan targets 17.5.0 to match the
  coverage record. If the operator prefers the chart that matches the image, 18.0.0 is a same-effect substitution in §3.3 (one token);
  otherwise expect Renovate to open 18.0.0 next and it is again a label-only roll (a PLAN-lane lockstep item until retired).

### 1.3 Why held: 3 new forward-only DB migrations

Live head read read-only from `webui.db` on 2026-11-03: **`0bd252b206fb`** (the 0.12.1 head). Migration directory listings via the GitHub
contents API: **66 files at v0.12.5, 69 at v0.13.0**; the only additions (`diff` of the two listings) are a linear chain from our head:

| revision | from | what it does on our SQLite |
|---|---|---|
| `c41f8d9e2a10` add_resource_comments | `0bd252b206fb` | CREATE TABLE `comment` (+3 indexes), `comment_reaction` (+1 index). Empty tables. |
| `6f8c2a91d4e7` add_tool_is_active | `c41f8d9e2a10` | `tool` += `is_active` BOOLEAN NOT NULL DEFAULT true (ADD COLUMN; 0 tool rows here). |
| `e42c8f710a36` add_notification_inbox | `6f8c2a91d4e7` | CREATE TABLE `notification` (+4 indexes, 3 CHECK constraints). Empty. **New head.** |

All three are additive (no backfill, no `batch_alter_table` table copy, no data rewrite), unlike the 0.12.x chain. `upgrade()` bodies
were read in full at tag v0.13.0. Their `downgrade()` functions drop the tables/column, but the OLD image does not contain these revision
files, so a plain revert makes v0.12.5 fail at start with alembic "Can't locate revision e42c8f710a36" (same failure class as the 0.12.3
plan). Hence `rollback_class: backup-restore` and §5 is a procedure.

Upstream's own warning (v0.13.0 release notes, "Changed", verbatim):

> Database Migrations: This release includes database schema changes; we strongly recommend backing up your database and all associated
> data before upgrading in production environments. If you are running a multi-worker, multi-server, or load-balanced deployment, all
> instances must be updated simultaneously, rolling updates are not supported and will cause application failures due to schema
> incompatibility.

We run one replica in a StatefulSet (RollingUpdate, partition 0): the old pod is deleted before `-0` is recreated, so there is no
mixed-version window. `values.replicaCount: 1`.

### 1.4 v0.13.0 behaviour changes checked against our wiring

Source: release notes v0.13.0 (published 2026-11-03T12:23Z) and the `v0.12.5...v0.13.0` compare (300 files). The compare touches **no**
`requirements.txt`, `pyproject.toml` or `Dockerfile`; `backend/start.sh`, `backend/open_webui/env.py` and the pre-existing migration files
show comment-banner-only edits in their patches (`env.py`, `start.sh` read), `package.json` is frontend. No dependency or image-build change
was found.

- **Security fixes, unlisted.** Upstream: "This release contains security fixes. We strongly recommend updating ... as soon as possible"
  (advisories to follow). Not detailed here; the operator should expect the contextual-tier findings on v0.12.x to re-form against the new tag
  on the next sweep.
- **ENABLE_NOTIFICATIONS defaults to True** (config.py at v0.13.0: `os.getenv('ENABLE_NOTIFICATIONS', 'True')`): an Inbox appears in the
  sidebar for all 3 users. Harmless; no env set here. **ENABLE_COMMENTS defaults False**, **USER_PERMISSIONS_CHAT_SIDE_CHAT defaults False**
  (Side chat off). We set none of these (live env on `open-webui-0` contains `WEBUI_SECRET_KEY`, `ENABLE_WEBSOCKET_SUPPORT`, the TTS
  variables from `open-webui-tts-secret` and the `extraEnvVars` in the HelmRelease).
- **Higher tool-call limit** 256 -> 1024 per response and **sub-agent limits default to none** (were 20/20/30/30000). With local Ollama
  models and one tool (`function` 1 row, `tool` 0 rows) this only matters for a runaway agent loop; revert with
  `CHAT_RESPONSE_MAX_TOOL_CALL_ITERATIONS=256` if wanted. Not set by this plan.
- **UI moves** (Controls into the model menu; Overview as a full-screen window from the chat menu): operator-visible only.
- **"File processing alerts removed"**: no notification webhooks configured here.
- **Open Terminal Desktop/Browser tabs** require a separate Open Terminal connection; the chart's `terminals` subchart is not enabled in
  our values (the render contains no terminals workload). No effect.
- **OAuth provider settings now load at start**: no OAuth/OIDC env on the pod and no Authentik policy on the route (local auth).
- **Redis**: no change called out for 0.13.0 in the notes. The 0.12.3 requirement that a redis user hold PUBLISH/SUBSCRIBE/UNSUBSCRIBE/PING
  on `&socketio*` is unchanged and satisfied (no ACL on our redis); §4.4 still greps for `noperm`.

### 1.5 What this plan deliberately does not move

- **Redis sidecar tag** (`websocket.redis.image.tag: 8.10.1-alpine`, coverage member "redis 8.10.1 -> 8.10.3-alpine", finding F-e8a41b1b):
  already covered by the vetted plan `redis-fleet-8.10.3` (its leg 4, sun-attended:2026-11-29). Taking it here would collide with that plan's
  sed and premises (`conflicts_with` above). The redis pod does restart in this plan, but only because the chart labels change.
- **Pipelines** (`ghcr.io/open-webui/pipelines:main@sha256:b48e9bc3...`): digest-pinned float of `main`; coverage lists the repo as an image
  member but there is no versioned target (no tag other than the floating `main`), and its image findings are AR-029 accepted. Pin handling
  belongs to the `float-tag-pinning` programme. Subchart unchanged across the chart bump. No pipelines pod restart expected.

### 1.6 Live facts (2026-11-03)

- `sts/open-webui` 1/1 on image v0.12.5, up 3d19h, 0 restarts. **No readiness, liveness or startup probe** on the app container - "Ready"
  is meaningless as a gate; §4 never uses it. `deploy/open-webui-redis` 1/1, `deploy/open-webui-pipelines` 1/1.
- Helm release `open-webui` revision 60 `deployed` (chart 17.0.0, history `appVersion` 0.12.0; the image is overridden to v0.12.5), `maxHistory: 1`.
- Data (read-only sqlite URI): alembic `0bd252b206fb`; user 3, chat 135, model 127, file 7, knowledge 0, tool 0, function 1.
  `/app/backend/data` is 4.2 GiB on a 20 GiB volume (vector_db, cache, uploads); `webui.db` is 88.7 MB with WAL; earlier copies
  `webui.db.pre-0.12.3` and `webui.db.bak-mlx-migration-20260904214756` already sit there (~177 MB combined).
- Newest Longhorn backup at 2026-11-02T23:08Z (22.5 h at check time): `longhorn-backup-age.py --max-hours 26` exits 0. The volume has 2
  replicas.
- HTTPRoute `open-webui` parents `envoy-external`; Service type LoadBalancer 192.168.55.28 (LAN). No in-cluster consumer calls open-webui's
  API (mcpo is a tool server it calls OUT to).

### 1.7 Timing recommendation

v0.13.0 is hours old. Prior patterns: 0.12.x shipped five patch releases in two weeks. Prefer a window that opens after a soak of a few days
(or after v0.13.1 appears) and re-run §2.6; a retarget is a DRIFT refresh of THIS file (README "When the held target MOVES"), not a new plan.

## 2. Pre-checks

**Unattended / operator-away rule (stop-safe).** If the operator is absent, any FAIL in §3.4 or §4 (except the host-side Ollama drift note in
§4.6) runs §5 immediately and stops with the result recorded. A failed pre-check before §3.3 simply STOPs with nothing changed. The restore
uses ONLY the in-window pre-copy from §3.2; the §2.2 Longhorn backup is the last resort.

Run from `/Users/mu/code/cberg-home-nextgen` in zsh. Any FAIL means do not proceed.

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.1 premises (read-only)
.venv/bin/python3 runbooks/plan-premises.py open-webui-0.13.0 --require-premises
#   PASS: all premises PASS, no REFUSED line.

# 2.2 backup freshness (Longhorn daily-backup-all-volumes lands ~23:00 UTC)
.venv/bin/python3 runbooks/longhorn-backup-age.py --max-hours 26 open-webui-20g; echo "exit=$?"
#   PASS: "open-webui-20g <N>h FRESH ..." and exit=0. FAIL prints STALE/MISSING and exits non-zero.

# 2.3 alembic baseline + row-count snapshot (read-only sqlite URI)
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "
import sqlite3; c=sqlite3.connect('file:/app/backend/data/webui.db?mode=ro',uri=True)
print('ALEMBIC', c.execute('select version_num from alembic_version').fetchone()[0])
for t in ('user','auth','chat','model','tool','function','skill','group','file','knowledge','channel','channel_member','message'):
    print('COUNT', t, c.execute(f'select count(*) from \"{t}\"').fetchone()[0])
print('USERS_NO_AUTH', c.execute('select count(*) from user u left join auth a on a.id=u.id where a.id is null').fetchone()[0])
print('HAS_COMMENT', c.execute(\"select count(*) from sqlite_master where name in ('comment','comment_reaction','notification')\").fetchone()[0])
" | tee /tmp/owui-pre-counts.txt
#   PASS: ALEMBIC 0bd252b206fb, USERS_NO_AUTH 0 and HAS_COMMENT 0. Any other head (e.g. e42c8f710a36 = already migrated, or an older
#   head) or HAS_COMMENT > 0: STOP, §1.3 and §5 no longer describe this DB.

# 2.4 baseline: app answers and logs are clean
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8080/api/version').read().decode())"
#   PASS: {"version":"0.12.5",...}
kubectl logs -n ai open-webui-0 -c open-webui --since=24h | grep -i -c -E "error running migrations|can't locate revision|traceback|noperm"
#   PASS: 0. This is the baseline §4.4 compares against. A non-zero count is not a stop but is recorded and §4.4 compares to it.

# 2.5 nothing in flight on the release / Flux
helm history open-webui -n ai --max 1          # PASS: STATUS deployed
flux get helmreleases -n ai open-webui         # PASS: READY True, no "in progress"
git fetch -q && git status -sb | head -1       # main not behind origin

# 2.6 target still the newest stable, artifacts exist (not premise-able: gh/curl)
gh api repos/open-webui/open-webui/releases/latest --jq '.tag_name+" "+(.prerelease|tostring)'   # PASS: v0.13.0 false (2026-11-03)
gh pr view 334 --json state,title -q '.state+" "+.title'      # PASS: OPEN ... ( 17.0.0 -> 17.5.0 ) - leave it UNMERGED
#   If a newer v0.13.x is latest: STOP, refresh THIS file in place (re-list the migrations; do not just bump the number).
#   Registry check: an HTTP 200 on the v-prefixed tag manifest (TOKEN from https://ghcr.io/token?scope=repository:open-webui/open-webui:pull):
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" -H 'Accept: application/vnd.oci.image.index.v1+json' https://ghcr.io/v2/open-webui/open-webui/manifests/v0.13.0   # PASS: 200
#   Record the index digest for §4.1: curl -sI the same URL and read docker-content-digest (not captured here, v0.13.0 was hours old).

# 2.7 stop-safe unattended: the Ollama host answers and the model list is the known baseline (§4.6 compares)
curl -s -m 10 http://192.168.30.111:11434/api/tags | python3 -c "import sys,json;print(sorted(m['name'] for m in json.load(sys.stdin)['models']))"
#   Record the list as OLLAMA_BASE. Host unreachable/other list is NOT a stop for the upgrade; §4.6 then records "baseline differs".

# 2.8 no overlapping plan is stamped into this window (conflicts_with in the frontmatter, enforced by the scheduler); and the
#     reciprocal check: none of redis-fleet-8.10.3 / flux-oci-chart-sources / helm-drift-detection is mid-run.
.venv/bin/python3 runbooks/maintenance-plan.py --open | grep -E 'redis-fleet-8.10.3|flux-oci-chart-sources|helm-drift-detection|python-fleet-3.15.2'
```

## 3. Steps

### 3.1 Update marker (application-update SOP Step 1)

```bash
runbooks/update-marker.sh add open-webui ai 2 "open-webui 0.12.5->0.13.0 + chart 17.5.0"
```

The Alertmanager silence from the SOP is optional: no app-specific PrometheusRule exists; expected restarts are the StatefulSet pod and the
redis pod once each.

### 3.2 Pre-change DB copy (the rollback artifact, taken immediately before the commit)

The sqlite online-backup API is WAL-safe while the app runs:

```bash
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "
import sqlite3, os
p='/app/backend/data/webui.db.pre-0.13.0'
s=sqlite3.connect('/app/backend/data/webui.db'); d=sqlite3.connect(p)
s.backup(d); d.close()
c=sqlite3.connect('file:'+p+'?mode=ro',uri=True)
print('COPY_BYTES', os.path.getsize(p))
print('COPY_ALEMBIC', c.execute('select version_num from alembic_version').fetchone()[0])
print('COPY_CHATS', c.execute('select count(*) from chat').fetchone()[0])
print('COPY_INTEGRITY', c.execute('pragma integrity_check').fetchone()[0])"
PRE_SHA=$(kubectl exec -n ai open-webui-0 -c open-webui -- sha256sum /app/backend/data/webui.db.pre-0.13.0 | cut -d' ' -f1); echo "PRE_SHA=$PRE_SHA"
```

- **PASS** requires all of: `COPY_BYTES` > 0; `COPY_ALEMBIC 0bd252b206fb`; `COPY_CHATS` equal to the `COUNT chat` line of
  `/tmp/owui-pre-counts.txt`; `COPY_INTEGRITY ok`; and a non-empty 64-hex `PRE_SHA`.
- Anything else: **STOP before the §3.3 edit** (nothing changed yet). Without this file there is no rollback.
- `COPY_BYTES` may be smaller than the source (the backup compacts it). If a chat was written between §2.3 and here, `COPY_CHATS`
  exceeds the §2.3 number; re-take the §2.3 snapshot and compare against that.

### 3.3 The edit (image + chart + retries 0)

Dry-tested 2026-11-03 on a scratch copy of the live file on macOS (BSD sed). The resulting `diff` is exactly these three hunks
(`diff hr-orig.yaml hr-scratch.yaml`):

```
11c11   <       version: 17.0.0     >       version: 17.5.0
25c25   <       retries: 1          >       retries: 0        (upgrade: block only; install retries: 3 untouched)
120c120 <       tag: v0.12.5        >       tag: v0.13.0
```

`yq` on the scratch copy then printed `17.5.0 / v0.13.0 / 0 / 3 / 8.10.1-alpine / main@sha256:b48e9bc3...` (chart, image, upgrade retries,
install retries, redis tag, pipelines tag), i.e. redis and pipelines pins are untouched.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/ai/open-webui/app/helmrelease.yaml
sed -i '' \
  -e 's/^      version: 17\.0\.0$/      version: 17.5.0/' \
  -e 's/^      tag: v0\.12\.5$/      tag: v0.13.0/' \
  -e '/^  upgrade:$/,/^  uninstall:$/s/^      retries: 1$/      retries: 0/' \
  "$F"
git diff --stat -- "$F"         # PASS: 1 file, 3 insertions(+), 3 deletions(-)
yq '.spec.chart.spec.version, .spec.values.image.tag, .spec.upgrade.remediation.retries, .spec.install.remediation.retries, .spec.values.websocket.redis.image.tag' "$F"
#   PASS, in order: 17.5.0 / v0.13.0 / 0 / 3 / 8.10.1-alpine
#   (Alternative chart 18.0.0: replace the first sed replacement with 18.0.0 and expect 18.0.0 in the first yq line.)

MSG=$(mktemp /tmp/owui-msg.XXXXXX)
cat > "$MSG" <<'EOF'
feat(open-webui): app v0.12.5 -> v0.13.0, chart 17.0.0 -> 17.5.0

Plan open-webui-0.13.0. 3 additive forward-only alembic migrations
(head 0bd252b206fb -> e42c8f710a36). Chart bump is label-only (render diff
verified) and rolls the sts + redis pod template once. Pre-change copy
webui.db.pre-0.13.0 taken in-pod. upgrade.remediation.retries 0 for the
attempt (restored after verification). Satisfies Renovate #334.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012bXdxrZGGHNy5e4RnF6seD
EOF
git commit --only "$F" -F "$MSG"
git log -1 --format=%s          # MUST be the subject above (shared-worktree message-swap guard); amend before push if not
git show --stat HEAD            # exactly that one file
git push; rm -f "$MSG"
```

Flux applies via the push webhook. No manual reconcile unless nothing happened after 10 minutes; then
`flux reconcile helmrelease -n ai open-webui --with-source`.

### 3.4 Watch the roll

```bash
for i in $(seq 1 40); do
  IMG=$(kubectl get pod -n ai open-webui-0 -o jsonpath='{.spec.containers[0].image}' 2>/dev/null)
  PH=$(kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.phase}' 2>/dev/null)
  echo "$IMG $PH"; [ "$IMG" = "ghcr.io/open-webui/open-webui:v0.13.0" ] && [ "$PH" = "Running" ] && break
  sleep 15
done
kubectl logs -n ai open-webui-0 -c open-webui --since=10m | grep -i -E "running migrations|running upgrade|error" | head -20
#   Expect alembic "Running upgrade 0bd252b206fb -> c41f8d9e2a10", "-> 6f8c2a91d4e7", "-> e42c8f710a36".
```

If the pod is not on v0.13.0 and Running after 10 min, or the log shows `Error running migrations`, go to §5.

### 3.5 After §4 passes: restore remediation retries (second commit)

```bash
sed -i '' -e '/^  upgrade:$/,/^  uninstall:$/s/^      retries: 0$/      retries: 1/' "$F"
git diff -- "$F" | grep -E '^[-+] '   # PASS: exactly "-      retries: 0" / "+      retries: 1" (dry-tested 2026-11-03)
MSG=$(mktemp /tmp/owui-msg.XXXXXX); printf 'chore(open-webui): restore upgrade remediation retries after 0.13.0\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_012bXdxrZGGHNy5e4RnF6seD\n' > "$MSG"
git commit --only "$F" -F "$MSG"; git log -1 --format=%s; git show --stat HEAD; git push; rm -f "$MSG"
runbooks/update-marker.sh clear open-webui
```

This changes only HelmRelease spec fields that do not render into the manifest: a Helm revision, no pod roll. Confirm afterwards that
`open-webui-0` startTime is unchanged.

Then: confirm Renovate closes PR 334 on its next run (close by hand only if still open after 24 h); retire this plan file in the commit that
records execution; close the version finding it owns with `runbooks/policy-cli.py finding close F-31c19a7f --commit <sha>`; check on the next
sweep that the v0.12.x security rows clear or re-form against v0.13.0 (DB only, nothing to commit).

## 4. Verification

Run every gate after §3.4. Each gate can FAIL; the failure output is noted.

**4.0 Timing guard (run first; later gates are vacuous before this passes).**
```bash
S=$(kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.startTime}')
AGE=$(python3 -c "import sys,datetime as d;print(int((d.datetime.now(d.timezone.utc)-d.datetime.fromisoformat(sys.argv[1].replace('Z','+00:00'))).total_seconds()))" "$S")
echo "POD_AGE_S $AGE"
[ "$AGE" -ge 600 ] || { echo "WAIT $((600-AGE))s"; sleep $((600-AGE)); }
```
PASS: the pod is at least 600 s old before 4.3/4.4 are read; an early read of the restart counter or logs would pass vacuously.

**4.1 Version actually served**
```bash
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8080/api/version').read().decode())"
kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.containerStatuses[0].imageID}'
kubectl get sts -n ai open-webui -o jsonpath='{.spec.template.metadata.labels.helm\.sh/chart}'
```
- PASS: `"version":"0.13.0"`, an imageID that differs from the pre-roll v0.12.5 digest (record it in §2.4: `kubectl get pod -n ai open-webui-0 -o
  jsonpath='{.status.containerStatuses[0].imageID}'`) and equals the index digest recorded in §2.6, and chart label `open-webui-17.5.0`.
- FAIL: `"version":"0.12.5"` (stale pod / image edit lost), `"0.12.0"` (chart default leaked: tag pin lost), chart label still `open-webui-17.0.0`
  (chart edit not applied).

**4.2 Schema migrated and data intact** (the CONTENTS assertion)
```bash
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "
import sqlite3; c=sqlite3.connect('file:/app/backend/data/webui.db?mode=ro',uri=True)
print('ALEMBIC', c.execute('select version_num from alembic_version').fetchone()[0])
for t in ('user','auth','chat','model','tool','function','skill','group','file','knowledge','channel','channel_member','message'):
    print('COUNT', t, c.execute(f'select count(*) from \"{t}\"').fetchone()[0])
print('USERS_NO_AUTH', c.execute('select count(*) from user u left join auth a on a.id=u.id where a.id is null').fetchone()[0])
print('TABLES', sorted(r[0] for r in c.execute(\"select name from sqlite_master where type='table' and name in ('comment','comment_reaction','notification')\")))
print('TOOL_IS_ACTIVE', int('is_active' in [r[1] for r in c.execute('pragma table_info(tool)')]))
print('TOOL_INACTIVE', c.execute('select count(*) from tool where is_active = 0').fetchone()[0])
print('MODEL_HISTORY', c.execute('select count(*) from model_history').fetchone()[0])
print('INTEGRITY', c.execute('pragma integrity_check').fetchone()[0])" | tee /tmp/owui-post-counts.txt
diff <(grep -E '^(COUNT|USERS_NO_AUTH)' /tmp/owui-pre-counts.txt) <(grep -E '^(COUNT|USERS_NO_AUTH)' /tmp/owui-post-counts.txt)
```
- PASS needs all of: `ALEMBIC e42c8f710a36`; the `diff` empty or differing only by chat/file growth during the window (`user`, `auth`, `model`,
  `function`, `group` identical); `TABLES ['comment', 'comment_reaction', 'notification']`; `TOOL_IS_ACTIVE 1`; `TOOL_INACTIVE 0`;
  `MODEL_HISTORY` equal to COUNT model (127 on 2026-11-03, history untouched by this release); `INTEGRITY ok`.
- FAIL looks like: `ALEMBIC 0bd252b206fb` (no migration ran); `ALEMBIC c41f8d9e2a10` or `6f8c2a91d4e7` (chain stopped half-way);
  `TABLES []` or a short list (a CREATE did not apply); `TOOL_IS_ACTIVE 0`; a shrunken COUNT (data loss: §5 immediately).
- A chat-count-only check would stay green on a DB whose model registry was emptied; hence model, model_history and user/auth are asserted.

**4.3 No crash loop.** The pod has no probes, so this is the only liveness evidence.

CONTROL: metric kube_pod_container_status_restarts_total - `{namespace="ai",pod="open-webui-0",container="open-webui"}` must read 0 at least 10 min after the new pod started. FAIL: >=1, which is how an import-time migration crash shows on a probe-less pod.

CONTROL: metric kube_statefulset_status_replicas_ready - `{namespace="ai",statefulset="open-webui"}` == 1. Shape check only, kept to catch a pod that never started.

CONTROL: metric kube_deployment_status_replicas_available - `{namespace="ai",deployment="open-webui-redis"}` == 1 (the redis pod rolls in this plan; this proves it came back) and `{namespace="ai",deployment="open-webui-pipelines"}` == 1 (it must not have been disturbed).

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for q in 'kube_pod_container_status_restarts_total{namespace="ai",pod="open-webui-0",container="open-webui"}' \
         'kube_statefulset_status_replicas_ready{namespace="ai",statefulset="open-webui"}' \
         'kube_deployment_status_replicas_available{namespace="ai",deployment="open-webui-redis"}' \
         'kube_deployment_status_replicas_available{namespace="ai",deployment="open-webui-pipelines"}'; do
  curl -s -G localhost:19090/api/v1/query --data-urlencode "query=$q" | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('N',len(r),[x['value'][1] for x in r])"
done
kill $PF 2>/dev/null
```
- PASS: `N 1 ['0']`, then `N 1 ['1']`, `N 1 ['1']`, `N 1 ['1']`.
- `N 0 []` is a FAIL (the instrument read nothing), never a pass: the parser prints the series count separately from the value.

**4.4 Logs clean, with a positive control**
```bash
kubectl logs -n ai open-webui-0 -c open-webui --since=30m | grep -i -c -E "error running migrations|can't locate revision|traceback|noperm"
kubectl logs -n ai open-webui-0 -c open-webui --since=30m | grep -i -c "running upgrade"
```
- PASS: first count 0 (baseline §2.4) AND second count >= 3 (the three revisions). A 0/0 means the log window missed the start or logs
  rotated: a FAIL, not a pass. Case-insensitive because upstream mixes `Error`/`ERROR`; `noperm` catches the room-channels redis permission
  message should the redis ACL ever differ from the measured `+@all`.

**4.5 Websocket redis reachable after the redis pod was replaced**
```bash
kubectl get pod -n ai -l app.kubernetes.io/component=open-webui-redis -o jsonpath='{.items[0].metadata.creationTimestamp}'   # newer than the §3.3 push
kubectl exec -n ai deploy/open-webui-redis -- redis-cli set owui-plan-probe ok EX 60
kubectl exec -n ai deploy/open-webui-redis -- redis-cli get owui-plan-probe
kubectl exec -n ai deploy/open-webui-redis -- redis-cli --scan --pattern 'open-webui:*' | wc -l
```
- PASS: pod creationTimestamp after the push (the roll happened: if it is older, the chart label roll did not reach redis and §1.2's claim
  needs re-checking), `OK`, `ok`, then >= 1 open-webui key 5 min after the app start.
- FAIL: 0 `open-webui:*` keys 5 min after app start (the app is not talking to redis); a bare `PONG` would not reveal that.
  The selector is app.kubernetes.io/component=open-webui-redis (verified live 2026-11-03).

**4.6 Real path through the public edge, and Ollama reachability**
```bash
H=$(kubectl get httproute -n ai open-webui -o jsonpath='{.spec.hostnames[0]}')
curl -s -o /dev/null -w '%{http_code}\n' "https://$H/health"
curl -s "https://$H/api/version"
curl -s "https://$H/api/config" | python3 -c "
import sys,json; d=json.load(sys.stdin)
print('VERSION', d.get('version')); print('AUTH', d['features']['auth']); print('OAUTH', sorted(d.get('oauth',{}).get('providers',{}).keys()))"
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "
import urllib.request,json,os
u=os.environ['OLLAMA_BASE_URLS'].split(';')[0].rstrip('/')
print('OLLAMA_MODELS', sorted(m['name'] for m in json.load(urllib.request.urlopen(u+'/api/tags',timeout=10))['models']))"
```
- PASS: `200`; `"version":"0.13.0"` from the public route; `VERSION 0.13.0 / AUTH True / OAUTH []`; `OLLAMA_MODELS` equals the §2.7 baseline.
- FAIL: a 5xx from envoy (backend down), `"version":"0.12.5"` (stale pod behind the route), non-JSON `/api/config` (app broken), `AUTH False`
  (auth disabled: open instance, roll back), a non-empty OAUTH list (config leaked), or a connection error to Ollama (network/ollamaUrls
  broken). Host-side Ollama drift when §2.7 already differed is recorded, not a failure.

Operator/Chrome check (attended windows; nightly records it as pending for the morning report):
1. Log in with the existing session cookie; it must still be valid.
2. Open an existing chat; its history must render.
3. Send one short prompt to an Ollama model; it must stream a reply.
4. The sidebar shows the new Inbox; Controls now live in the model menu. Reload once: no reconnect loop.

## 5. Rollback

**Decision rule:**
- If §4.2 shows ALEMBIC `0bd252b206fb` (no migration ran), a plain revert of the §3.3 commit (plus the §3.5 commit if landed) is a complete
  rollback.
- In every other failure case the schema has moved forward and the DB restore below is **required** before v0.12.5 can start.

Chats written between the §3.2 copy and the restore are lost; tell the users (typically minutes).

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/ai/open-webui/app/helmrelease.yaml

# 5.1 stop Flux from re-applying 0.13.0 and release the RWO volume
flux suspend helmrelease -n ai open-webui
kubectl scale sts -n ai open-webui --replicas=0
kubectl wait -n ai pod/open-webui-0 --for=delete --timeout=180s

# 5.2 restore through a throw-away pod mounting the PVC (open-webui-0 does NOT exist at replicas 0)
kubectl run -n ai owui-restore --restart=Never --image=ghcr.io/open-webui/open-webui:v0.12.5 \
  --overrides='{"apiVersion":"v1","spec":{"containers":[{"name":"owui-restore","image":"ghcr.io/open-webui/open-webui:v0.12.5","command":["sleep","3600"],"volumeMounts":[{"name":"d","mountPath":"/app/backend/data"}]}],"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"open-webui-20g"}}]}}'
kubectl wait -n ai pod/owui-restore --for=condition=Ready --timeout=300s
kubectl exec -n ai owui-restore -c owui-restore -- sha256sum /app/backend/data/webui.db.pre-0.13.0
#   PASS: equals PRE_SHA from §3.2. Different = the copy changed; STOP and use the Last resort below.
kubectl exec -n ai owui-restore -c owui-restore -- python3 -c "
import sqlite3, os, shutil, time
src='/app/backend/data/webui.db.pre-0.13.0'; dst='/app/backend/data/webui.db'
shutil.copy2(dst, dst+'.failed-0.13.0.'+time.strftime('%Y%m%d_%H%M%S'))   # keep the migrated DB for diagnosis
for ext in ('-wal','-shm'):
    p=dst+ext
    if os.path.exists(p): os.remove(p)                                   # app is down; stale WAL must not replay onto the restored file
s=sqlite3.connect(src); d=sqlite3.connect(dst); s.backup(d); d.close()
c=sqlite3.connect('file:'+dst+'?mode=ro',uri=True)
print('RESTORED_ALEMBIC', c.execute('select version_num from alembic_version').fetchone()[0])
print('RESTORED_CHATS', c.execute('select count(*) from chat').fetchone()[0])
print('RESTORED_INTEGRITY', c.execute('pragma integrity_check').fetchone()[0])"
#   PASS: RESTORED_ALEMBIC 0bd252b206fb, RESTORED_CHATS == COPY_CHATS from §3.2, RESTORED_INTEGRITY ok
kubectl delete pod -n ai owui-restore --wait=true

# 5.3 revert the manifest (image + chart + retries) and resume
SHA=$(git log -1 --format=%H --grep='^feat(open-webui): app v0.12.5 -> v0.13.0, chart 17.0.0 -> 17.5.0$' -- "$F")
SHA2=$(git log -1 --format=%H --grep='^chore(open-webui): restore upgrade remediation retries after 0.13.0$' -- "$F")   # empty if §3.5 never landed
git show --stat "$SHA"          # confirm it is the §3.3 commit and ONLY that file
MSG=$(mktemp /tmp/owui-revert.XXXXXX); printf 'revert: open-webui back to v0.12.5 / chart 17.0.0 (plan open-webui-0.13.0 rollback)\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_012bXdxrZGGHNy5e4RnF6seD\n' > "$MSG"
# if §3.5 landed, revert BOTH, newest first (a lone revert of the first hunk conflicts with the retries hunk)
git revert --no-commit ${SHA2:+$SHA2} "$SHA" && git commit --only "$F" -F "$MSG"
git log -1 --format=%s; git show --stat HEAD; git push; rm -f "$MSG"
yq '.spec.chart.spec.version, .spec.values.image.tag, .spec.upgrade.remediation.retries' "$F"   # expect 17.0.0 / v0.12.5 / 1
flux resume helmrelease -n ai open-webui        # the reconcile restores replicas 1 on v0.12.5 (the label roll of redis reverts too)
```

If `retries` prints 0, fix it in the same commit before pushing (the plan's prior-state value is 1).

**5.4 Confirm the cluster is back.**
- Re-run §4.1: expect `0.12.5`, chart label `open-webui-17.0.0`, and the pre-roll imageID recorded in §2.4.
- Re-run §4.2: expect ALEMBIC `0bd252b206fb` and COUNT lines equal to the §2.3 snapshot; the `TABLES`/`TOOL_IS_ACTIVE` lines are expected to read
  `[]` / `0` (old schema).
- Re-run §4.3/§4.4: 0 restarts, 0 error lines; and the `kubectl get sts,deploy,pod -n ai | grep open-webui` shows 1/1 on all three.

**Last resort** (the pre-0.13.0 copy is missing or fails integrity): restore volume `open-webui-20g` from the §2.2 Longhorn backup per
`docs/sops/backup.md` "Restore from Backup" (loses up to ~24 h of chats).

**Helm wedged `pending-upgrade`:** application-update SOP. `helm rollback open-webui <prev> -n ai --wait=false` only if the previous revision
still exists (`maxHistory: 1` may have pruned it). A Helm rollback restores the manifest only, **never** the DB, so 5.1-5.2 still apply.

**Cleanup after success (not a rollback):** keep `webui.db.pre-0.13.0` for 7 days, then
`kubectl exec -n ai open-webui-0 -c open-webui -- rm /app/backend/data/webui.db.pre-0.13.0`. The older `webui.db.pre-0.12.3` and
`webui.db.bak-mlx-migration-20260904214756` (88.7 MB each) are past their usefulness and can be removed in the same sitting by the operator.

## 6. Interference notes

- **Biggest gotcha: the migration is forward-only; take the §3.2 in-pod copy BEFORE the commit and keep `retries: 0` for the attempt.** With
  `retries: 1` Helm would auto-roll back the manifest to v0.12.5 against a migrated DB and crash-loop on "Can't locate revision".
- **Same file as `redis-fleet-8.10.3`** (leg 4 edits `websocket.redis.image.tag`). Different lines, so no textual merge conflict, but the
  redis plan's prose, `touches` and gate ("chart 17.0.0 / app v0.12.5 untouched", open-webui StatefulSet "asserted unchanged") become stale
  once this plan runs, and the other way round this plan's `redis-sidecar-pin` premise reads `8.10.3-alpine`. `conflicts_with` keeps them in
  separate windows; the second to run re-reads live pins first. The redis plan's reciprocal `conflicts_with: open-webui-0.13.0` should be
  added by whoever next amends it (this planner does not edit other plans).
- **Redis restarts (chart label roll) and the app pod restarts once each**: websocket/streaming sessions drop for about a minute; chats are
  persisted in sqlite. No in-cluster consumer is affected. The LB IP 192.168.55.28 (Service) is unchanged.
- **Window sizing**: 40 min fits a `sat-attended` slot (70 schedulable after Step 0) and the `nightly` slot. Because `capability_change: true`
  the execution class derives to HUMAN-GATED, so an operator GO is required either way; there is no SD-10 pre-approval route.
- **Do not co-schedule** with the plans in `conflicts_with`. In particular `python-fleet-3.15.2` (sat-attended:2026-11-14) rolls `ai/mcpo`;
  `flux-oci-chart-sources` (sun-attended:2026-12-13) re-points this chart source and will re-roll `statefulset/open-webui` and redis again
  (a no-migration restart); `helm-drift-detection` asserts identical Helm revisions across releases.
- **Chart 18.0.0** will appear as the next Renovate chart PR (label-only, no template change). It is a coverage PLAN item purely through
  lockstep; after this plan it should be treated as a plain chart label bump.
- **Repo corrections noticed (not applied):** none in SOPs. The previous plan's note that the pods carry no probes still holds.
