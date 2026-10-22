---
plan_id: open-webui-0.12.2
component: open-webui
pr: 333                               # image PR, now retargeted: v0.11.4 -> v0.12.2. The chart half is
                                      # Renovate PR 334 (feat(helm)!: 16.6.0 -> 17.0.0). Neither PR is
                                      # merged. Both halves land in ONE direct commit (§3.3), and
                                      # Renovate then closes both PRs as satisfied.
kind: image
current: "chart open-webui 16.6.0 + image ghcr.io/open-webui/open-webui:v0.11.4"
target: "image ghcr.io/open-webui/open-webui:v0.12.2 + chart open-webui 17.0.0 (lockstep, one commit)"
update_type: major                    # chart 16 -> 17 is a semver major; the app 0.11 -> 0.12 is the
                                      # breaking axis at major 0 (8 forward-only alembic revisions, §1.3)
risk: medium                          # chart is appVersion-only (rendered diff = labels + image, §1.2).
                                      # The app runs 8 forward-only alembic migrations on the only copy of
                                      # every chat/model/user (sqlite on open-webui-20g). It is a single
                                      # household app with no in-cluster consumers, so not high.
est_duration_min: 45                  # pre-checks+snapshot 10, commit+reconcile+image pull 10,
                                      # migrations <1, verification 15, retries-restore commit 5, slack 5
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/open-webui
    - statefulset/open-webui            # rolls to v0.12.2; runs alembic on start (init copy-app-data too)
    - deployment/open-webui-redis       # rolls ONLY because the chart's pod-template labels change
                                        # (helm.sh/chart, app.kubernetes.io/version); image unchanged
    - pvc/open-webui-20g                # webui.db migrated in place; pre-copy written beside it (§3.2)
    # NOT touched: deployment/open-webui-pipelines (subcharts byte-identical 16.6.0 vs 17.0.0; its
    # rendered manifest does not change), pvc/open-webui-pipelines-new, httproute/open-webui,
    # service/open-webui (labels only, no selector/port change).
  shared: [monitoring]                  # §4.3 reads Prometheus (kube-state-metrics), the window's instrument.
                                        # No gateway/envoy change. The HTTPRoute is untouched; §4.6 only READS
                                        # through envoy-external.
depends_on: []
conflicts_with:
  - open-webui-17.0.0                   # SUPERSEDED by this plan (§6): same file, same lines, same migration
                                        # chain, older target. Never both, never in one window.
  - redis-fleet-8.10.2                  # edits the SAME file (websocket.redis.image.tag) and rolls the same
                                        # StatefulSet + redis; its open-webui leg is stale (§6).
  - flux-oci-chart-sources              # re-points the open-webui chart source (pins 16.5.0 in its
                                        # inventory) and rolls statefulset/open-webui.
  - helm-drift-detection                # its §4.1 asserts Helm revisions identical before/after; this
                                        # plan creates open-webui revision 57 (and 58 in §3.5).
  - kube-prometheus-stack-92.2.0        # §4.3 reads kube-state-metrics through Prometheus.
  - flux-reconciler-impersonation       # changes WHO applies the HelmRelease this plan relies on.
  - flux-fleet-0.60.0                   # Flux controller upgrade under this plan's GitOps step.
  - flux-distribution-2.9.6             # same, distribution-wide (it is also exclusive).
  - envoy-proxy-config-distroless-v1.39.3  # rolls the envoy proxies §4.6 reads the app through.
  - envoy-proxy-config-distroless-v1.39.4  # same; it already lists open-webui-17.0.0 (rename its ref, §6).
exclusive: false
security_ref: F-f3caadda              # security driver: the image-scan finding on v0.11.4. Detail stays
                                      # in sweep_history (policy-cli finding show); nothing restated here.
capability_change: true               # 0.12.0 adds user-visible features (Realtime voice, MFA, model/tool/
                                      # function/skill version history, group hierarchy); 0.12.1 adds the
                                      # Apps-in-channels feature (off by default, ENABLE_APPS=False) and
                                      # changes the default follow-up prompt (§1.1).
rollback_class: backup-restore        # FORWARD-ONLY: 8 alembic migrations. v0.11.4's run_migrations() runs
                                      # command.upgrade('head') and RE-RAISES, and its image does not ship
                                      # the 8 new revision files, so a plain git revert crash-loops on
                                      # "Can't locate revision 0bd252b206fb". Rollback = restore
                                      # webui.db.pre-0.12.2 (§5).
backup_gate: "Completed Longhorn backup of open-webui-20g < 26h (runbooks/longhorn-backup-age.py --max-hours 26 open-webui-20g exits 0), PLUS the in-pod sqlite online-backup copy /app/backend/data/webui.db.pre-0.12.2 taken in §3.2 immediately before the commit, with COPY_ALEMBIC d4c1a8e37b62, COPY_CHATS equal to the live count and COPY_INTEGRITY ok."
finding_refs:
  - F-c4303aae                        # version: image v0.11.4 -> 0.12.2 (this target)
  - F-3cdb3585                        # version: chart 16.6.0 -> 17.0.0 (carried in lockstep here)
  - F-f3caadda                        # security: image-scan finding on v0.11.4 (security_ref above)
review: null
status: superseded
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-15"
premises:
  # Read-verb only. Each was run 2026-10-15 and returned the expected value.
  - id: app-image-current
    why: >-
      current: claims v0.11.4 on the StatefulSet. If open-webui-17.0.0 (or anything else) ran first,
      the alembic baseline (§2.3), the migration list and the rollback image are wrong. Stop and re-plan.
    run: kubectl get sts -n ai open-webui -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/open-webui/open-webui:v0.11.4
  - id: chart-current
    why: The HelmRelease must still pin chart 16.6.0. The §3.3 sed matches only that line.
    run: kubectl get helmrelease -n ai open-webui -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: 16.6.0
  - id: repo-pins-unique
    why: >-
      §3.3 edits by exact-line sed. Each pin must occur exactly once in git, or the sed either
      misses or double-hits. One file means grep -c prints a single total, which must be 2.
    run: 'grep -c -E "^      (version: 16\.6\.0|tag: v0\.11\.4)$" kubernetes/apps/ai/open-webui/app/helmrelease.yaml'
    expect_exact: "2"
  - id: hr-ready
    why: A HelmRelease that is already failing would mask whether this upgrade broke it.
    run: kubectl get helmrelease -n ai open-webui -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: volume-healthy
    why: The migration writes the only copy of the DB. Do not run it on a degraded volume.
    run: kubectl get volume -n storage open-webui-20g -o jsonpath='{.status.robustness}'
    expect_exact: healthy
  - id: longhorn-backup-exists
    why: >-
      A Completed Longhorn backup must exist (3 Completed 2026-10-13..14 on 2026-10-15). Freshness
      (< 26h) is the §2.2 longhorn-backup-age.py gate, because plan-premises refuses python3.
    run: kubectl get backups.longhorn.io -n storage -o jsonpath='{.items[?(@.status.volumeName=="open-webui-20g")].status.state}'
    expect_contains: Completed
---

# open-webui app v0.11.4 → v0.12.2 + chart 16.6.0 → 17.0.0 (lockstep)

## 1. Summary & why held

### 1.1 What changes

The plan makes one commit to `kubernetes/apps/ai/open-webui/app/helmrelease.yaml`:

- `spec.values.image.tag: v0.11.4 → v0.12.2` (Renovate PR 333, retargeted from v0.12.0)
- `spec.chart.spec.version: 16.6.0 → 17.0.0` (Renovate PR 334)
- `spec.upgrade.remediation.retries: 1 → 0` for the attempt only (application-update SOP
  Step 2). It is restored to `1` in a second commit after §4 passes.

**Chart and app move together. This plan supersedes `open-webui-17.0.0`.** That sibling draft
(untracked, 2026-10-12) planned the same lockstep to v0.12.0. Since then upstream shipped v0.12.1
(2026-10-14 16:06Z) and v0.12.2 (2026-10-14 21:07Z), and PR 333 was retargeted to v0.12.2. These are
the reasons to move straight to v0.12.2 in one window instead of 17.0.0/v0.12.0 now and v0.12.2 later:

- **One migration window, one rollback artifact.** 0.12.1 adds 2 more forward-only alembic
  revisions (§1.3). Two separate plans would mean two DB copies, two restore procedures, and a
  second human-gated window.
- **0.12.1 fixes a 0.12.0 regression.** The 0.12.1 Fixed section says: "No reconnect loop after
  sign-in. … where since 0.12.0 it reconnected several times per second until the page was reloaded
  and put heavy load on the server." Landing on v0.12.0 would ship that regression to the household.
- **Chart 17.0.0 is still the newest stable chart.** The helm index on 2026-10-15 lists only 17.0.0
  (appVersion 0.12.0) plus `17.0.1-dev.*` pre-releases. The image is pinned in values, so the chart's
  appVersion does not drive the image (§1.2).

Both artifacts were verified as published on 2026-10-15:

- `ghcr.io/open-webui/open-webui:v0.12.2` returns HTTP 200 with index digest
  `sha256:10e6a78ba2d172493460a9e8a92c496aaa7a64dc4d26d622a2e95e0c736081c9`. The unprefixed `0.12.2`
  tag is the same digest, and `v0.12.3` returns 404.
- The current v0.11.4 is `sha256:9591b13f13843c7721c2b8eaf7382846c81b3ffe126526d1888d1fed50c6a33f`,
  which is the live pod's imageID.
- Chart 17.0.0 is in `https://helm.openwebui.com/index.yaml` with digest `875a30fd…9835`.
- The repo pins the `v`-prefixed form (`v0.11.4`), and PR 333 keeps it, so the plan uses `v0.12.2`.

Two pins are **not** changed by this plan:

- The redis sidecar pin (`websocket.redis.image.tag: 8.10.1-alpine`). That bump is
  `F-e8a41b1b` / `redis-fleet-8.10.2`.
- The pipelines digest pin (`main@sha256:b48e9bc3…`). The pipelines subchart is byte-identical
  between 16.6.0 and 17.0.0, and its image findings are AR-029 accepted with no newer upstream tag.

The dispatch group listed the `pipelines` and `redis` repos, but neither has a leg in this plan.

### 1.2 The chart half is trivial (re-verified 2026-10-15)

The upstream chart CHANGELOG for v17.0.0 says only "Updated chart appVersion to v0.12.0", plus a
generic ⚠ BREAKING note that defers to the app release notes.

I pulled both charts and rendered them with the live values:

```
helm template open-webui <16.6.0> -n ai -f <(yq .spec.values helmrelease.yaml)
helm template open-webui <17.0.0> -n ai -f <same values with image.tag=v0.12.2>
```

The complete `diff` of the two renders was:

```
   2 <         app.kubernetes.io/version: "0.11.4"     2 >  ... "0.12.0"     (pod templates: STS + redis)
   2 <         helm.sh/chart: open-webui-16.6.0        2 >  ... 17.0.0
   2 <         image: ghcr.io/open-webui/open-webui:v0.11.4   2 > ...:v0.12.2  (main + init copy-app-data)
   5 <     app.kubernetes.io/version / helm.sh/chart   5 >  (SA, 2 Services, STS, Deployment metadata)
```

`diff -rq charts/` printed nothing (`SUBCHARTS_IDENTICAL`), so the pipelines objects do not change.

- The StatefulSet `open-webui` rolls.
- The Deployment `open-webui-redis` rolls on the label change alone. It holds only ephemeral
  websocket/lock keys and has no volume.
- Selectors are unchanged.

Cosmetic quirk: the `app.kubernetes.io/version` label will read `0.12.0` while the image is
`v0.12.2`. This is expected and harmless, because the label comes from the chart's appVersion.

### 1.3 Why held: 8 forward-only DB migrations in the app half

`backend/open_webui/migrations/versions/` holds 58 files at v0.11.4, 64 at v0.12.0, 66 at v0.12.1 and
66 at v0.12.2. I listed the directory at each tag through the GitHub API and diffed the listings.
The new revisions form a linear chain from the **live head `d4c1a8e37b62`**, which I read read-only
from the pod's webui.db on 2026-10-15:

| revision | from | what it does on our SQLite |
|---|---|---|
| `a7d3e9f2b641` add_mfa_and_session_stamp | 0.12.0 | `auth` += `mfa` JSON, `session_stamp` TEXT (nullable) |
| `b8e4f0a3c752` add_group_hierarchy | 0.12.0 | `batch_alter_table('group')` += `parent_group_id` FK + index (on SQLite this is a table copy) |
| `d6a8c3f912ab` add_skill_history | 0.12.0 | `skill` += version cols; `skill_history`, backfilled per row (0 skills here) |
| `e7b9d4a023bc` add_model_history | 0.12.0 | `model` += `version_id`; `model_history`, **backfilled one row per model** (127 here) |
| `f8c0e5b134cd` add_tool_history_and_function_history | 0.12.0 | same for `tool` (0) and `function` (1) |
| `b8f2c6d91a04` add_postgres_pending_files_index | 0.12.0 | **no-op on SQLite** (`dialect != 'postgresql': return`) |
| `c92da83b017f` add_apps | 0.12.1 | new `app` table; `batch_alter_table('channel_member')`: `user_id` nullable, `app_id` + CHECK + UNIQUE + index (table copy, 0 rows here); `message` += `app_id` + index (0 rows) |
| `0bd252b206fb` add_missing_auth_rows | 0.12.1 | inserts an `auth` row with an empty (never-verifying) password for every `user` lacking one. **No-op here**: users without an auth row = 0 (measured). **New head.** |

v0.12.2 adds no migrations. Its notes have no Breaking/Removed section. The only "Changed" item is
the Valkey vector-store client tag, which applies only to `VECTOR_DB=valkey`. We run the default
Chroma, and `requirements.txt` differs between v0.12.0 and v0.12.2 only in that commented-out
optional valkey line.

The v0.12.1 notes carry the upstream warning verbatim:

> ⚠️ **Database Migrations**: This release includes database schema changes; we strongly recommend
> backing up your database … rolling updates are not supported and will cause application failures
> due to schema incompatibility.

We run one replica in a StatefulSet. The old pod is deleted before `-0` is recreated, so no
mixed-version window exists.

**Why a revert alone cannot roll this back.**

- v0.11.4's `config.py` `run_migrations()` calls `command.upgrade(alembic_cfg, 'head')` inside
  `try/except` and **re-raises** (`log.exception(...)` then `raise`).
- A v0.11.4 pod started against a DB at head `0bd252b206fb` therefore fails at import with
  alembic's "Can't locate revision".
- `0bd252b206fb.downgrade()` is `pass`, and `c92da83b017f.downgrade()` raises if any app message
  exists.

So `rollback_class: backup-restore`, and §5 is a procedure. This is the same class of failure as
immich on 2026-10-12 (`a844cf8d`).

### 1.4 Other upstream changes checked and found harmless here

- **Sessions are not invalidated.** v0.12.0 `utils/auth.py` compares
  `decoded.get('session_stamp') != auth.session_stamp`. Pre-upgrade JWTs carry no stamp, and the new
  column is NULL, so both sides are None and existing logins survive. MFA is only enforced when an
  admin enables it.
- **Apps-in-channels (0.12.1) is off by default.** `config.py` @v0.12.2 sets
  `ENABLE_APPS = os.getenv('ENABLE_APPS', 'False')`, and we do not set it. Channels are unused here
  (channel/channel_member/message = 0 rows).
- **Changed default follow-up prompt (0.12.1).** This is a user-visible behaviour change and part of
  why `capability_change: true`. It does not affect instances with a custom prompt.
- **SCIM/SSO fixes (0.12.1) do not apply.** We use local auth: there is no OAuth/OIDC/SCIM env, and
  the extra env vars are only `WEBUI_URL`, `GLOBAL_LOG_LEVEL` and `AUDIO_TTS_*`.
- **The DB is SQLite.** There is no `DATABASE_URL`, so the PostgreSQL-only branches in
  `migrations/env.py` and `b8f2c6d91a04` do not run.
- **Redis.** v0.12.0's `WEBSOCKET_REDIS_ROOM_CHANNELS` defaults to true. With a single replica and
  `WEBSOCKET_MANAGER=redis` it has no behavioural effect. 0.12.1's Sentinel fixes are not used here.

### 1.5 Live facts (2026-10-15)

- `sts/open-webui` 1/1 on k8s-nuc14-01 runs image v0.11.4 and has **no readiness, liveness or
  startup probe**. "Ready" is therefore meaningless as a gate, because a crash-looping pod is Ready
  between crashes. §4 never uses it.
- `updateStrategy` is RollingUpdate with partition 0 and 1 replica. StatefulSets are immune to
  Multi-Attach (longhorn-rwo-multi-attach SOP).
- Data: user 3, auth 3, chat 134, model 127, function 1, tool 0, skill 0, group 2, file 7,
  knowledge 0. Users without an auth row: 0. The PVC is `open-webui-20g` (longhorn-static), and the
  Longhorn volume is healthy/attached.
- Helm history: rev 56 is `deployed` (16.6.0/0.11.4) and rev 55 is superseded, with `maxHistory: 1`.
  `helm rollback` cannot be relied on, so rollback is git plus a DB restore.
- The newest Longhorn backup is `backup-60886bb8154c4c28` at 2026-10-14T23:02Z.
  `longhorn-backup-age.py` printed "3.4h FRESH" and exit=0.
- Public edge: `https://<route host>/health` returns 200 and `/api/version` returns `{"version":"0.11.4"}`.
- Baselines: 0 migration/traceback log lines over 72 h; 4 `open-webui:*` redis keys.
- No in-cluster consumer calls open-webui's API. The blast radius is the household's browser
  users behind the HTTPRoute on `envoy-external`.

## 2. Pre-checks

Run these from `/Users/mu/code/cberg-home-nextgen` in zsh. Any FAIL means do not proceed.

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.0 the superseded sibling must NOT have run (premise app-image-current also guards this)
grep -m1 '^status:' runbooks/maintenance/plans/open-webui-17.0.0.md 2>/dev/null || echo "sibling retired"
#   PASS: "sibling retired" or a status other than executed/awaiting-soak. If it is executed, STOP:
#   the DB is at b8f2c6d91a04 and this plan's baseline, copy name and rollback image are all wrong.

# 2.1 premises (read-only)
.venv/bin/python3 runbooks/plan-premises.py open-webui-0.12.2

# 2.2 backup freshness: the window opens 03:30 and the Longhorn daily-backup-all-volumes job runs ~23:00-03:00
.venv/bin/python3 runbooks/longhorn-backup-age.py --max-hours 26 open-webui-20g; echo "exit=$?"
#   PASS: "open-webui-20g <N>h FRESH ..." and exit=0 (measured 3.4h/exit=0 on 2026-10-15).
#   FAIL prints STALE/MISSING and exits non-zero.

# 2.3 alembic baseline + row-count snapshot (read-only sqlite URI)
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "
import sqlite3; c=sqlite3.connect('file:/app/backend/data/webui.db?mode=ro',uri=True)
print('ALEMBIC', c.execute('select version_num from alembic_version').fetchone()[0])
for t in ('user','auth','chat','model','tool','function','skill','group','file','knowledge','channel','channel_member','message'):
    print('COUNT', t, c.execute(f'select count(*) from \"{t}\"').fetchone()[0])
print('USERS_NO_AUTH', c.execute('select count(*) from user u left join auth a on a.id=u.id where a.id is null').fetchone()[0])
" | tee /tmp/owui-pre-counts.txt
#   PASS: ALEMBIC d4c1a8e37b62 and USERS_NO_AUTH 0 (both measured 2026-10-15). Any other head means
#   someone already moved the schema: STOP, because §1.3 and §5 no longer describe this DB.
#   USERS_NO_AUTH > 0 is not a stop, but then expect §4.2 COUNT auth to grow by exactly that number.

# 2.4 baseline: app answers and logs are clean
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8080/api/version').read().decode())"
#   PASS: {"version":"0.11.4",...}
kubectl logs -n ai open-webui-0 -c open-webui --since=24h | grep -i -c -E "error running migrations|can't locate revision|traceback"
#   PASS: 0 (measured 0 over 72h on 2026-10-15). This is the baseline §4.4 compares against.

# 2.5 nothing in flight on the release / Flux
helm history open-webui -n ai --max 1          # PASS: STATUS deployed (rev 56 on 2026-10-15)
flux get helmreleases -n ai open-webui         # PASS: READY True, no "in progress"
git fetch -q && git status -sb | head -1       # main not behind origin

# 2.6 the Renovate PRs are still the expected two (both stay UNMERGED)
gh pr view 333 --json state,title -q '.state+" "+.title'   # OPEN feat(container): ... ( v0.11.4 → v0.12.2 )
gh pr view 334 --json state,title -q '.state+" "+.title'   # OPEN feat(helm)!: Update open-webui ( 16.6.0 → 17.0.0 )
#   If 333 was retargeted again (v0.12.3+), STOP: this is a DRIFTED plan. Refresh it in place
#   (README "When the held target MOVES"). Re-list the migrations; do not just bump the number.
```

## 3. Steps

### 3.1 Silence and update marker (application-update SOP Step 1)

```bash
runbooks/update-marker.sh add open-webui ai 2 "open-webui 0.11.4->0.12.2 + chart 17.0.0"
```

The Alertmanager silence from the SOP is optional here. The app has no app-specific PrometheusRule,
and the expected restart count is 0.

### 3.2 Pre-change DB copy (the rollback artifact, taken immediately before the commit)

The sqlite online-backup API is WAL-safe while the app runs:

```bash
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "
import sqlite3, os
p='/app/backend/data/webui.db.pre-0.12.2'
s=sqlite3.connect('/app/backend/data/webui.db'); d=sqlite3.connect(p)
s.backup(d); d.close()
c=sqlite3.connect('file:'+p+'?mode=ro',uri=True)
print('COPY_BYTES', os.path.getsize(p))
print('COPY_ALEMBIC', c.execute('select version_num from alembic_version').fetchone()[0])
print('COPY_CHATS', c.execute('select count(*) from chat').fetchone()[0])
print('COPY_INTEGRITY', c.execute('pragma integrity_check').fetchone()[0])"
```

- **PASS** requires all four:
  - `COPY_BYTES` > 0;
  - `COPY_ALEMBIC d4c1a8e37b62`;
  - `COPY_CHATS` equal to the `COUNT chat` line in `/tmp/owui-pre-counts.txt`;
  - `COPY_INTEGRITY ok`.
- Any other value means **STOP**. Without this file there is no rollback.
- `COPY_BYTES` may be smaller than the source, because the backup compacts it.

### 3.3 The lockstep edit

This is one commit with both halves plus `retries: 0`. I dry-tested it on a scratch copy of the live
file on macOS (BSD sed) on 2026-10-15. The resulting `diff` was exactly:

```
11c11  <       version: 16.6.0          >       version: 17.0.0
25c25  <       retries: 1               >       retries: 0      (the upgrade: block; install retries: 3 untouched)
120c120 <       tag: v0.11.4            >       tag: v0.12.2
```

`yq` on the scratch copy then printed `17.0.0 / v0.12.2 / 0 / 3 / 8.10.1-alpine`.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/ai/open-webui/app/helmrelease.yaml
sed -i '' \
  -e 's/^      version: 16\.6\.0$/      version: 17.0.0/' \
  -e 's/^      tag: v0\.11\.4$/      tag: v0.12.2/' \
  -e '/^  upgrade:$/,/^  uninstall:$/s/^      retries: 1$/      retries: 0/' \
  "$F"
git diff --stat -- "$F"         # PASS: 1 file, 3 insertions(+), 3 deletions(-)
yq '.spec.chart.spec.version, .spec.values.image.tag, .spec.upgrade.remediation.retries, .spec.install.remediation.retries, .spec.values.websocket.redis.image.tag' "$F"
#   PASS, in order: 17.0.0 / v0.12.2 / 0 / 3 / 8.10.1-alpine (sidecar untouched)

MSG=$(mktemp /tmp/owui-msg.XXXXXX)
cat > "$MSG" <<'EOF'
feat(open-webui): app v0.11.4 -> v0.12.2 + chart 16.6.0 -> 17.0.0 (lockstep)

Plan open-webui-0.12.2 (supersedes open-webui-17.0.0). Chart is
appVersion-only; app runs 8 forward-only alembic migrations (head
d4c1a8e37b62 -> 0bd252b206fb). Pre-change copy webui.db.pre-0.12.2 taken
in-pod. upgrade.remediation.retries 0 for the attempt (restored after
verification). Satisfies Renovate #333 + #334. security_ref F-f3caadda.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
git commit --only "$F" -F "$MSG"
git log -1 --format=%s          # MUST be the subject above (shared-worktree message-swap guard)
git show --stat HEAD            # exactly that one file
git push; rm -f "$MSG"
```

Flux applies the change through the push webhook. Do not run a manual reconcile unless nothing has
happened after 10 minutes. In that case, run `flux reconcile helmrelease -n ai open-webui --with-source`.

### 3.4 Watch the roll

```bash
# wait for the NEW image on the live pod (rollout status can green-light the old generation)
for i in $(seq 1 40); do
  IMG=$(kubectl get pod -n ai open-webui-0 -o jsonpath='{.spec.containers[0].image}' 2>/dev/null)
  PH=$(kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.phase}' 2>/dev/null)
  echo "$IMG $PH"; [ "$IMG" = "ghcr.io/open-webui/open-webui:v0.12.2" ] && [ "$PH" = "Running" ] && break
  sleep 15
done
kubectl logs -n ai open-webui-0 -c open-webui --since=10m | grep -i -E "running migrations|running upgrade|error" | head -20
#   Expect "Running migrations" and alembic "Running upgrade d4c1a8e37b62 -> a7d3e9f2b641" ...
#   "-> c92da83b017f" ... "-> 0bd252b206fb".
```

If the pod is not on v0.12.2 and Running after 10 min, or the log shows `Error running migrations`,
go to §5.

### 3.5 After §4 passes: restore remediation retries (second commit)

```bash
sed -i '' -e '/^  upgrade:$/,/^  uninstall:$/s/^      retries: 0$/      retries: 1/' "$F"
git diff -- "$F" | grep -E '^[-+] ' # PASS: exactly "-      retries: 0" / "+      retries: 1"
MSG=$(mktemp /tmp/owui-msg.XXXXXX); printf 'chore(open-webui): restore upgrade remediation retries after 0.12.2\n\nCo-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>\n' > "$MSG"
git commit --only "$F" -F "$MSG"; git log -1 --format=%s; git show --stat HEAD; git push; rm -f "$MSG"
runbooks/update-marker.sh clear open-webui
```

This commit changes only HelmRelease spec fields that do not render into the manifest. It creates a
Helm revision but no pod roll. Afterwards, confirm that the `open-webui-0` startTime is unchanged.

Then:

1. Retire `runbooks/maintenance/plans/open-webui-17.0.0.md`, in the same commit as this plan's
   retirement, if it still exists.
2. Confirm that Renovate closed PRs 333 and 334 on its next run. Close them by hand only if they are
   still open after 24 h.
3. Close the findings this plan owns:
   `policy-cli.py finding close <F-c4303aae|F-3cdb3585> --commit <sha>`.
   Then check on the next sweep that F-f3caadda clears, or re-forms against v0.12.2.

## 4. Verification

Run every gate after §3.4. Each gate below was checked to be able to FAIL; the failure output is
noted for each one.

**4.1 Version actually served**
```bash
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8080/api/version').read().decode())"
kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.containerStatuses[0].imageID}'
```

- PASS: `"version":"0.12.2"`, and an imageID ending
  `10e6a78ba2d172493460a9e8a92c496aaa7a64dc4d26d622a2e95e0c736081c9`.
- FAIL: `"version":"0.11.4"` (the live reading on 2026-10-15), or the old digest `9591b13f…`.
- `"version":"0.12.0"` would mean the 17.0.0 chart default leaked through (the image.tag edit was
  lost), and is also a FAIL.

**4.2 Schema migrated and data intact.** This is the CONTENTS assertion.
```bash
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "
import sqlite3; c=sqlite3.connect('file:/app/backend/data/webui.db?mode=ro',uri=True)
print('ALEMBIC', c.execute('select version_num from alembic_version').fetchone()[0])
for t in ('user','auth','chat','model','tool','function','skill','group','file','knowledge','channel','channel_member','message'):
    print('COUNT', t, c.execute(f'select count(*) from \"{t}\"').fetchone()[0])
print('USERS_NO_AUTH', c.execute('select count(*) from user u left join auth a on a.id=u.id where a.id is null').fetchone()[0])
print('MODEL_HISTORY', c.execute('select count(*) from model_history').fetchone()[0])
print('MODEL_UNVERSIONED', c.execute('select count(*) from model where version_id is null').fetchone()[0])
print('FUNCTION_HISTORY', c.execute('select count(*) from function_history').fetchone()[0])
print('APP_TABLE', c.execute('select count(*) from app').fetchone()[0])
print('CM_APP_COL', int('app_id' in [r[1] for r in c.execute('pragma table_info(channel_member)')]))
print('INTEGRITY', c.execute('pragma integrity_check').fetchone()[0])" | tee /tmp/owui-post-counts.txt
diff <(grep -E '^(COUNT|USERS_NO_AUTH)' /tmp/owui-pre-counts.txt) <(grep -E '^(COUNT|USERS_NO_AUTH)' /tmp/owui-post-counts.txt)
```

CONTENTS ASSERTION: every pre-existing table keeps its rows, and the new history tables are populated
from them. This is measured by the query above and compared to `/tmp/owui-pre-counts.txt` (§2.3).

- PASS needs all of these:
  - `ALEMBIC 0bd252b206fb`.
  - The `diff` is empty, or differs only by chat/file growth from live use during the window.
    `user`, `auth`, `model` and `group` must be identical. `auth` stays 3, because USERS_NO_AUTH was 0,
    so `0bd252b206fb` inserts nothing.
  - `MODEL_HISTORY` equals COUNT model (127 on 2026-10-15).
  - `MODEL_UNVERSIONED 0`.
  - `FUNCTION_HISTORY` equals COUNT function (1).
  - `APP_TABLE 0` and `CM_APP_COL 1`.
  - `INTEGRITY ok`.
- FAIL looks like this:
  - `ALEMBIC d4c1a8e37b62`: no migration ran.
  - `ALEMBIC b8f2c6d91a04`: stopped after the 0.12.0 chain, so the 0.12.1 revisions failed.
  - `no such table: model_history` / `no such table: app`: a revision did not apply.
  - `MODEL_HISTORY` 0 or `MODEL_UNVERSIONED` > 0: the backfill was skipped or partial.
  - `CM_APP_COL 0`: the channel_member table copy did not complete.
  - A shrunken COUNT: data loss, so go to §5 immediately.
- A "chat count only" check would stay green on a DB whose model registry was emptied. That is why
  model and model_history are asserted.

**4.3 No crash loop.** The pod has no probes, so this is the only liveness evidence.

CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="ai",pod="open-webui-0",container="open-webui"}` must read 0 at least 10 min after the new pod started. The STS pod is recreated, so the counter starts at 0; the series read `N 1 ['0']` live on 2026-10-15. FAIL: ≥1, which is how an import-time migration crash shows on a probe-less pod.

CONTROL: metric kube_statefulset_status_replicas_ready — `{namespace="ai",statefulset="open-webui"}` == 1 (read 1 on 2026-10-15). Without probes this alone is a shape check. It is kept only to catch a pod that never started (ImagePull/Pending).

CONTROL: metric kube_deployment_status_replicas_available — `{namespace="ai",deployment="open-webui-redis"}` == 1 (read 1 on 2026-10-15). The redis pod rolls on the label change.

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
for q in 'kube_pod_container_status_restarts_total{namespace="ai",pod="open-webui-0",container="open-webui"}' \
         'kube_statefulset_status_replicas_ready{namespace="ai",statefulset="open-webui"}' \
         'kube_deployment_status_replicas_available{namespace="ai",deployment="open-webui-redis"}'; do
  curl -s -G localhost:19090/api/v1/query --data-urlencode "query=$q" | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print('N',len(r),[x['value'][1] for x in r])"
done
kill $PF 2>/dev/null
```

- PASS: `N 1 ['0']`, then `N 1 ['1']`, then `N 1 ['1']`.
- An `N 0 []` is a FAIL (the instrument read nothing), never a pass.
- Negative control, run 2026-10-15: the same pipeline on `pod="open-webui-nonexistent"` printed
  `N 0 []`. The parser therefore distinguishes "no series" from "0".

**4.4 Logs clean**
```bash
kubectl logs -n ai open-webui-0 -c open-webui --since=15m | grep -i -c -E "error running migrations|can't locate revision|traceback"
```

- PASS: 0. The baseline was 0 over 72 h (§2.4), so any hit is new.
- The grep is case-insensitive because upstream logs mix `Error` and `ERROR`.

**4.5 Websocket redis consumer reconnected.** The redis pod rolled (§1.2) and is empty after a restart.
```bash
kubectl exec -n ai deploy/open-webui-redis -- redis-cli set owui-plan-probe ok EX 60
kubectl exec -n ai deploy/open-webui-redis -- redis-cli get owui-plan-probe
kubectl exec -n ai deploy/open-webui-redis -- redis-cli --scan --pattern 'open-webui:*' | wc -l
```

- PASS: `OK`, then `ok`, then ≥1. The baseline was 4 keys on 2026-10-15.
- FAIL: 0 `open-webui:*` keys 5 min after start means the app is not talking to the new redis.
  A bare `PONG` would not reveal that.

**4.6 Real path through the public edge, and Ollama reachability**
```bash
H=$(kubectl get httproute -n ai open-webui -o jsonpath='{.spec.hostnames[0]}')
curl -s -o /dev/null -w '%{http_code}\n' "https://$H/health"
curl -s "https://$H/api/version"
```

- PASS: `200` and `"version":"0.12.2"`.
- FAIL: a 5xx from envoy (backend down), or `"version":"0.11.4"`, which was the live reading on
  2026-10-15 (a stale pod behind the route).

Operator/Chrome check (attended windows only; a nightly run records it as pending for the morning
report):

1. Log in with the existing session cookie. It must still be valid (§1.4).
2. Open an existing chat. Its history must render.
3. Send one short prompt to an Ollama model. It must stream a reply, which proves `ollamaUrls`
   still reach 192.168.30.111:11434.
4. Reload the tab once. It must NOT reconnect-loop, which is the 0.12.0 regression fixed in 0.12.1.

## 5. Rollback

**Decision rule:**

- If §4.2 shows ALEMBIC `d4c1a8e37b62` (no migration ran), a plain revert of the §3.3 commit is a
  complete rollback.
- In every other failure case the schema has moved forward, and the DB restore below is
  **required** before v0.11.4 can start.

Chats written between the §3.2 copy and the restore are lost. Tell the users. The typical exposure is
a few minutes at 03:30.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/ai/open-webui/app/helmrelease.yaml

# 5.1 stop Flux from re-applying 0.12.2 and release the RWO volume
flux suspend helmrelease -n ai open-webui
kubectl scale sts -n ai open-webui --replicas=0
kubectl wait -n ai pod/open-webui-0 --for=delete --timeout=180s

# 5.2 restore through a throw-away pod mounting the PVC (open-webui-0 does NOT exist at replicas 0)
kubectl run -n ai owui-restore --restart=Never --image=ghcr.io/open-webui/open-webui:v0.11.4 \
  --overrides='{"apiVersion":"v1","spec":{"containers":[{"name":"r","image":"ghcr.io/open-webui/open-webui:v0.11.4","command":["sleep","3600"],"volumeMounts":[{"name":"d","mountPath":"/app/backend/data"}]}],"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"open-webui-20g"}}]}}'
kubectl wait -n ai pod/owui-restore --for=condition=Ready --timeout=300s
kubectl exec -n ai owui-restore -c r -- python3 -c "
import sqlite3, os, shutil, time
src='/app/backend/data/webui.db.pre-0.12.2'; dst='/app/backend/data/webui.db'
shutil.copy2(dst, dst+'.failed-0.12.2.'+time.strftime('%Y%m%d_%H%M%S'))   # keep the migrated DB for diagnosis
for ext in ('-wal','-shm'):
    p=dst+ext
    if os.path.exists(p): os.remove(p)                                   # app is down; stale WAL must not replay onto the restored file
s=sqlite3.connect(src); d=sqlite3.connect(dst); s.backup(d); d.close()
c=sqlite3.connect('file:'+dst+'?mode=ro',uri=True)
print('RESTORED_ALEMBIC', c.execute('select version_num from alembic_version').fetchone()[0])
print('RESTORED_CHATS', c.execute('select count(*) from chat').fetchone()[0])
print('RESTORED_INTEGRITY', c.execute('pragma integrity_check').fetchone()[0])"
#   PASS: RESTORED_ALEMBIC d4c1a8e37b62, RESTORED_CHATS == COPY_CHATS from §3.2, RESTORED_INTEGRITY ok
kubectl delete pod -n ai owui-restore --wait=true

# 5.3 revert the manifest (both halves + retries) and resume
SHA=$(git log -1 --format=%H --grep='^feat(open-webui): app v0.11.4 -> v0.12.2' -- "$F")
git show --stat "$SHA"          # confirm it is the §3.3 commit and ONLY that file
MSG=$(mktemp /tmp/owui-revert.XXXXXX); printf 'revert: open-webui back to chart 16.6.0 / v0.11.4 (plan open-webui-0.12.2 rollback)\n\nCo-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>\n' > "$MSG"
git revert --no-commit "$SHA" && git commit --only "$F" -F "$MSG"
git log -1 --format=%s; git show --stat HEAD; git push; rm -f "$MSG"
flux resume helmrelease -n ai open-webui        # the reconcile restores replicas 1 on v0.11.4
```

If §3.5 had already landed, the revert must also restore `retries: 1`. Check
`yq '.spec.upgrade.remediation.retries' "$F"` and fix it in the same commit.

**5.4 Confirm the cluster is back.**

- Re-run §4.1: expect `0.11.4` with digest `9591b13f…`.
- Re-run §4.2: expect ALEMBIC `d4c1a8e37b62` and COUNT lines equal to the §2.3 snapshot. The
  model_history/app lines will error with "no such table", which is expected on the old schema.
- Re-run §4.3/§4.4: expect 0 restarts and 0 error lines.

**Last resort** (the pre-0.12.2 copy is missing or fails integrity): restore volume `open-webui-20g`
from the §2.2 Longhorn backup, per `docs/sops/backup.md` "Restore from Backup". This loses up to
~24 h of chats.

**Helm wedged `pending-upgrade`:** follow application-update SOP §7/§11.

- Run `helm rollback open-webui 56 -n ai --wait=false` only if revision 56 still exists
  (`maxHistory: 1` may have pruned it), then reconcile.
- A Helm rollback restores the manifest only, **never** the DB, so 5.1–5.2 still apply.

**Cleanup after success (not a rollback):**

- Keep `webui.db.pre-0.12.2` for 7 days, then delete it with
  `kubectl exec -n ai open-webui-0 -c open-webui -- rm /app/backend/data/webui.db.pre-0.12.2`.
- `webui.db.bak-mlx-migration-20260904214756` is unrelated. Leave it to its owner.

## 6. Interference notes

- **This plan supersedes `open-webui-17.0.0` (repo correction for the dispatcher/window agent).**
  - That draft targets the same file, the same three lines and the first 6 of the same 8 migrations,
    but stops at v0.12.0. That version carries the reconnect-loop regression fixed in 0.12.1 (§1.1).
  - Set it to `status: superseded`, or delete it, before either plan is vetted. Do not run both: after
    it ran, this plan's premises `app-image-current`/`repo-pins-unique` would FAIL (correctly, fail-closed).
  - Its `finding_refs` was empty, so this plan carries the chart finding `F-3cdb3585` as well.
  - Plans that reference `open-webui-17.0.0` should be renamed to this plan id: the
    `envoy-proxy-config-distroless-v1.39.4` `conflicts_with` entry, and the same-namespace mentions
    in `anythingllm-1.18` and `python-fleet-3.15.0`.
    `maintenance-plan.py --validate` raises DEAD-REF once the sibling file is deleted.
- **`redis-fleet-8.10.2` is stale on its open-webui leg (repo correction for its owner;
  `sun-attended:2026-10-25`).**
  - Its leg 3 moves open-webui 0.11.3→0.11.4 and chart 16.5.0→16.6.0. Both landed on 2026-10-09.
    Its premise `open-webui-app-current` (`…:0.11.3`) will FAIL as written.
  - It edits the same file, hence `conflicts_with`.
  - If this plan runs first, its leg 3 shrinks to the sidecar tag alone. Its `webui.db.pre-0.11.4`
    copy, alembic expectation and restore image are then all wrong for a DB at `0bd252b206fb`, and
    its rollback must use this plan's §5 (v0.12.2 image, `webui.db.pre-0.12.2`).
  - Reciprocal entries are not written in other plans, because a planner writes only its own file.
- **`flux-oci-chart-sources`** (`sun-attended:2026-11-22`) inventories open-webui at OCI chart 16.5.0.
  After this plan it must pin 17.0.0. Otherwise its source move is a **downgrade** of the chart,
  though not of the image (the tag is pinned in values).
- **`kube-prometheus-stack-92.2.0`**: §4.3 reads kube-state-metrics through Prometheus, so the two
  are in `conflicts_with` (window instrument = shared infra). That plan should list this one back.
- **Shared infra perturbed: none.**
  - The HTTPRoute, Gateway, Service selector/port and LB are unchanged.
  - The only other pod that rolls is the open-webui-owned redis (ephemeral).
  - `open-webui-pipelines` does not roll.
  - Ollama on the Mac mini is only read.
  - The other ns-`ai` plans (`anythingllm-1.18`, `next-ai-draw-io-0.5.0`, `python-fleet-3.15.0` (mcpo
    init)) share only the namespace: no shared objects, PVCs or files. They are not in `conflicts_with`.
- **Execution class:** `capability_change: true` + `rollback_class: backup-restore` → **HUMAN-GATED**
  (operator GO).
  - It fits a nightly window (45 of 70 schedulable min) once GO is recorded.
  - An attended sat/sun slot is preferable, so the §4.6 Chrome check (including the
    reconnect-loop reload) happens in the window rather than the next morning.
- Run it **after the Longhorn daily backup** (any window ≥ 03:30 satisfies §2.2).
- Security note: F-f3caadda is a `critical` finding, routed to the version pipeline ("COVERED").
  It is the reason not to let this plan sit unscheduled. The detail stays in the DB.
