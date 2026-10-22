---
plan_id: open-webui-0.12.3
component: open-webui
pr: 333                               # image PR: v0.11.4 -> v0.12.3 (retargeted from v0.12.2). The chart half
                                      # (Renovate PR 334, 16.6.0 -> 17.0.0) is the SEPARATE plan
                                      # open-webui-17.0.0, which depends_on this one (2026-10-22 split).
kind: image
current: "image ghcr.io/open-webui/open-webui:v0.11.4 (chart open-webui 16.6.0, untouched)"
target: "image ghcr.io/open-webui/open-webui:v0.12.3 (newest stable, verified 2026-10-22)"
update_type: minor                    # semver minor at app major 0, but the breaking axis: 8 forward-only
                                      # alembic revisions (§1.3)
risk: medium                          # The app runs 8 forward-only alembic
                                      # migrations on the only copy of every chat/model/user (sqlite on
                                      # open-webui-20g). Single household app, no in-cluster consumers.
est_duration_min: 45                  # pre-checks+snapshot 10, commit+reconcile+image pull 10,
                                      # migrations <1, verification 15, retries-restore commit 5, slack 5
needs_reboot: false
touches:
  namespaces: [ai]
  resources:
    - helmrelease/open-webui
    - statefulset/open-webui            # rolls to v0.12.3; runs alembic on start (init copy-app-data too)
    - pvc/open-webui-20g                # webui.db migrated in place; pre-copy written beside it (§3.2)
    # NOT touched: deployment/open-webui-redis (image-only change; pod template of redis unchanged),
    # deployment/open-webui-pipelines, pvc/open-webui-pipelines-new, httproute/open-webui, service/open-webui.
  shared: [monitoring]                  # §4.3 reads Prometheus (kube-state-metrics), the window's instrument.
                                        # No gateway/envoy change; §4.6 only READS through envoy-external.
depends_on: []
conflicts_with:
  - open-webui-0.12.2                   # SUPERSEDED by this plan (§6): same file, same lines, same 8
                                        # migrations, older target. Never both, never in one window.
  - redis-fleet-8.10.2                  # edits the SAME file (websocket.redis.image.tag) and rolls the same
                                        # StatefulSet + redis; its open-webui leg is stale (§6).
  - flux-oci-chart-sources              # re-points the open-webui chart source (pins 16.5.0 in its
                                        # inventory) and rolls statefulset/open-webui.
  - helm-drift-detection                # its §4.1 asserts Helm revisions identical before/after; this
                                        # plan creates open-webui revision 57 (and 58 in §3.5).
  - kube-prometheus-stack-92.2.0        # §4.3 reads kube-state-metrics through Prometheus.
  - kube-prometheus-stack-92.10.1       # same instrument, same-night bump.
  - flux-reconciler-impersonation       # changes WHO applies the HelmRelease this plan relies on.
  - flux-fleet-0.60.0                   # Flux controller upgrade under this plan's GitOps step.
  - flux-distribution-2.9.6             # same, distribution-wide (it is also exclusive).
  - envoy-proxy-config-distroless-v1.39.3  # rolls the envoy proxies §4.6 reads the app through.
  - envoy-proxy-config-distroless-v1.39.4  # same.
  - envoy-proxy-config-distroless-v1.40.0  # same (blocked today; listed so an unblock cannot co-schedule).
exclusive: false
security_ref: F-f3caadda              # security driver: the image-scan finding on v0.11.4. Detail stays
                                      # in sweep_history (policy-cli finding show); nothing restated here.
capability_change: true               # 0.12.0 adds user-visible features (Realtime voice, MFA, model/tool/
                                      # function/skill version history, group hierarchy); 0.12.1 adds
                                      # Apps-in-channels (off by default) and changes the default follow-up
                                      # prompt; 0.12.3 adds workspace search, live collaborators and
                                      # end-to-end encrypted channel chats (off by default), and changes
                                      # how model-attached skills are sent (§1.4).
rollback_class: backup-restore        # FORWARD-ONLY: 8 alembic migrations. v0.11.4's run_migrations() runs
                                      # command.upgrade('head') and RE-RAISES, and its image does not ship
                                      # the 8 new revision files, so a plain git revert crash-loops on
                                      # "Can't locate revision 0bd252b206fb". Rollback = restore
                                      # webui.db.pre-0.12.3 (§5).
backup_gate: "Completed Longhorn backup of open-webui-20g < 26h (runbooks/longhorn-backup-age.py --max-hours 26 open-webui-20g exits 0), PLUS the in-pod sqlite online-backup copy /app/backend/data/webui.db.pre-0.12.3 taken in §3.2 immediately before the commit, with COPY_ALEMBIC d4c1a8e37b62, COPY_CHATS equal to the live count and COPY_INTEGRITY ok."
finding_refs:
  - F-c4303aae                        # version: image v0.11.4 -> 0.12.x (title still reads 0.12.2 on
                                      # 2026-10-17; the next version sweep retitles it to 0.12.3)
  - F-f3caadda                        # security: image-scan finding on v0.11.4 (security_ref above)
review: ready-for-go@2026-10-22   # plan-reviewer 2026-10-22: needs-fix with 0 blocking technical issues; 4 nonblocking fixes applied by planner (restart wait, positive control, revert both SHAs, conflict ref); migrations/rollback/gates verified; premises 6/6
status: executed
window: "now:2026-10-22"   # ON-DEMAND NOW run 2026-10-22 (run-now.py stamp; was None)
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn-rwo-multi-attach.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-22"                # refreshed in place 2026-10-22: split image/chart, re-verified newest stable
premises:
  # Read-verb only. Each was run 2026-10-17 and returned the expected value.
  - id: app-image-current
    why: >-
      current: claims v0.11.4 on the StatefulSet. If open-webui-0.12.2 / open-webui-17.0.0 (or anything
      else) ran first, the alembic baseline (§2.3), the migration list and the rollback image are wrong.
      Stop and re-plan.
    run: kubectl get sts -n ai open-webui -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: ghcr.io/open-webui/open-webui:v0.11.4
  - id: chart-current
    why: >-
      The HelmRelease must still pin chart 16.6.0. This plan does NOT touch the chart; if the chart plan
      (open-webui-17.0.0) already ran, the order was violated and this plan's baseline is wrong. Stop.
    run: kubectl get helmrelease -n ai open-webui -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: 16.6.0
  - id: repo-pins-unique
    why: >-
      §3.3 edits by exact-line sed. The tag line must occur exactly once in the file, or the sed either
      misses or double-hits.
    run: 'grep -c -E "^      tag: v0\.11\.4$" kubernetes/apps/ai/open-webui/app/helmrelease.yaml'
    expect_exact: "1"
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
      A Completed Longhorn backup must exist. Freshness (< 26h) is the §2.2 longhorn-backup-age.py
      gate, because plan-premises refuses python3.
    run: kubectl get backups.longhorn.io -n storage -o jsonpath='{.items[?(@.status.volumeName=="open-webui-20g")].status.state}'
    expect_contains: Completed
---

# open-webui app v0.11.4 → v0.12.3 (image only; chart 17 is the separate plan open-webui-17.0.0)

## 1. Summary & why held

### 1.1 What changes, and what this plan supersedes

One commit to `kubernetes/apps/ai/open-webui/app/helmrelease.yaml`:

- `spec.values.image.tag: v0.11.4 → v0.12.3` (Renovate PR 333)
- `spec.upgrade.remediation.retries: 1 → 0` for the attempt only (application-update SOP Step 2),
  restored to `1` in a second commit after §4 passes.

The chart (16.6.0 → 17.0.0, PR 334) is NOT in this commit. Split 2026-10-22 on operator request: it is
the separate plan `open-webui-17.0.0`, `depends_on` this one (§1.2).

**This plan supersedes `open-webui-0.12.2` (2026-10-15).** Never-reviewed draft, no window, no GO, so
nothing is lost; set it `status: superseded` (§6). The research of `open-webui-0.12.2` was re-verified
against v0.12.3 and carried over where it still holds. What changed:

- **v0.12.3 adds no migrations.** The migrations directory lists 66 files at both v0.12.2 and v0.12.3,
  and the listings are identical (GitHub contents API, both tags, `diff` printed nothing). The 8-step
  chain in §1.3 and the rollback in §5 are therefore unchanged apart from the copy name.
- **v0.12.3 changes no dependencies or image build.** The v0.12.2...v0.12.3 compare touches 209
  files; none is `backend/requirements.txt`, `pyproject.toml`, a `Dockerfile`, `env.py`, `start.sh`
  or anything under `migrations/` (grep over the full file list printed nothing).
- **Newest stable re-verified 2026-10-22**: GitHub releases list v0.12.3 (2026-10-16, prerelease=false)
  as latest; no v0.12.4.

Artifacts verified published on 2026-10-17:

- `ghcr.io/open-webui/open-webui:v0.12.3` returns HTTP 200 with index digest
  `sha256:a537bbe1e6b428820f52ed4a029d7fff97062e24d5cf32c365fba36fd0542def`. The unprefixed `0.12.3`
  tag is the same digest; `v0.12.4` returns 404.
- The live v0.11.4 pod's imageID is `sha256:9591b13f13843c7721c2b8eaf7382846c81b3ffe126526d1888d1fed50c6a33f`.
- The repo pins the `v`-prefixed form and PR 333 keeps it, so the plan uses `v0.12.3`.

Two pins are **not** changed: the redis sidecar (`websocket.redis.image.tag: 8.10.1-alpine`; that is
`F-e8a41b1b` / `redis-fleet-8.10.2`) and the pipelines digest pin (`main@sha256:b48e9bc3…`; subchart
byte-identical between 16.6.0 and 17.0.0, its image findings are AR-029 accepted).

### 1.2 Why the chart is a separate, later plan (rendered 2026-10-22)

Chart 17.0.0 changes only labels: `helm.sh/chart` and `app.kubernetes.io/version` (appVersion 0.12.0).
`helm template` with our exact `spec.values`, 16.6.0 vs 17.0.0, differ in those 7 label pairs only;
the values schema (`helm show values` diff) is empty; subcharts unchanged. Since our `image.tag` is
pinned, the chart does not drive the app. Consequence: the chart can run on v0.11.4 or v0.12.3 with
the same effect, but it MUST run after this plan, because a chart-only move that also reset the tag
to the chart default (v0.12.0) would downgrade across the migrations. Hence `depends_on` in the chart
plan, and a separate commit/Helm revision here (one extra STS roll, accepted for clean rollback
boundaries: the DB-migrating step is isolated from the label-only step).

The two pins NOT changed here: the redis sidecar (`8.10.1-alpine`, `redis-fleet-8.10.2`) and the
pipelines digest.

### 1.3 Why held: 8 forward-only DB migrations in the app half

Live head read read-only from `webui.db` on 2026-10-17: **`d4c1a8e37b62`**. The new revisions
(listed per tag through the GitHub API; 58 files at v0.11.4, 64 at v0.12.0, 66 at v0.12.1/.2/.3)
form a linear chain from it:

| revision | from | what it does on our SQLite |
|---|---|---|
| `a7d3e9f2b641` add_mfa_and_session_stamp | 0.12.0 | `auth` += `mfa` JSON, `session_stamp` TEXT (nullable) |
| `b8e4f0a3c752` add_group_hierarchy | 0.12.0 | `batch_alter_table('group')` += `parent_group_id` FK + index (table copy on SQLite) |
| `d6a8c3f912ab` add_skill_history | 0.12.0 | `skill` += version cols; `skill_history`, backfilled per row (0 skills here) |
| `e7b9d4a023bc` add_model_history | 0.12.0 | `model` += `version_id`; `model_history`, **backfilled one row per model** (127 here) |
| `f8c0e5b134cd` add_tool_history_and_function_history | 0.12.0 | same for `tool` (0) and `function` (1) |
| `b8f2c6d91a04` add_postgres_pending_files_index | 0.12.0 | **no-op on SQLite** |
| `c92da83b017f` add_apps | 0.12.1 | new `app` table; `batch_alter_table('channel_member')` (table copy, 0 rows); `message` += `app_id` (0 rows) |
| `0bd252b206fb` add_missing_auth_rows | 0.12.1 | inserts an `auth` row for every `user` lacking one. **No-op here** (USERS_NO_AUTH 0, measured 2026-10-17). **New head.** |

Upstream's own warning (v0.12.1 notes, verbatim):

> ⚠️ **Database Migrations**: This release includes database schema changes; we strongly recommend
> backing up your database … rolling updates are not supported and will cause application failures
> due to schema incompatibility.

We run one replica in a StatefulSet (RollingUpdate, partition 0): the old pod is deleted before `-0`
is recreated, so no mixed-version window exists.

**Why a revert alone cannot roll this back.** v0.11.4's `run_migrations()` calls
`command.upgrade(alembic_cfg, 'head')` in `try/except` and **re-raises**. A v0.11.4 pod against a DB
at `0bd252b206fb` fails at import with alembic "Can't locate revision". `0bd252b206fb.downgrade()` is
`pass`, `c92da83b017f.downgrade()` raises if any app message exists. Hence
`rollback_class: backup-restore` and §5 is a procedure (same failure class as immich 2026-10-12,
`a844cf8d`).

### 1.4 v0.12.3 upstream changes checked against our wiring

From the v0.12.3 release notes (2026-10-16) and the v0.12.2...v0.12.3 source diff. There is no
Breaking/Removed section; the two "Changed" items:

- **"Redis permissions for room channels. With "WEBSOCKET_REDIS_ROOM_CHANNELS" on, the Redis user now
  needs the PUBLISH, SUBSCRIBE, UNSUBSCRIBE and PING permissions and access to the "&socketio" and
  "&socketio#\*" channels, while PSUBSCRIBE is no longer used; a missing permission is logged."**
  Room channels default on since 0.12.0. Our redis has no ACL: `redis-cli acl list` printed
  `user default on nopass sanitize-payload ~* &* +@all` on 2026-10-17, so every command and channel
  is permitted. No-op here; §4.4 still greps for `noperm` in case it is not.
- **"Model skills now load their full instructions"** when attached to a model. `skill` has 0 rows
  here. No effect.
- **Redis streaming storage change ("Much lighter streaming with Redis")**: replies are stored under
  per-reply keys; upstream states "replies started on older instances are still read during an
  upgrade". Irrelevant here anyway, because the redis pod does not roll in this plan (it keeps its keys).
- **New config (config.py diff)**: `ENABLE_ENCRYPTED_CHANNELS` and
  `USER_PERMISSIONS_FEATURES_ENCRYPTED_CHANNELS` default `False`; `SKILL_CONTENT_MAX_CHARS` /
  `SKILL_PREVIEW_MAX_CHARS` raise `ValueError` only when set to ≤0. We set none of them (live env:
  `OLLAMA_BASE_URLS, OPENAI_API_BASE_URL, OPENAI_API_KEY, ENABLE_WEBSOCKET_SUPPORT, WEBSOCKET_MANAGER,
  REDIS_URL, WEBSOCKET_REDIS_URL, WEBUI_URL, GLOBAL_LOG_LEVEL, AUDIO_TTS_*`).
- **OAuth/Google Drive/audit-log fixes** do not apply (local auth, no OAuth env, no Drive).

Carried over from the 0.12.0–0.12.2 review (still valid, code paths unchanged in that diff's scope):

- **Sessions are not invalidated.** 0.12.0 `utils/auth.py` compares `decoded.get('session_stamp') !=
  auth.session_stamp`; pre-upgrade JWTs carry no stamp and the new column is NULL, so both are None.
- **Apps-in-channels (0.12.1) is off by default** (`ENABLE_APPS` default `False`, unset here).
  Channels are unused (channel/channel_member/message = 0 rows).
- **The DB is SQLite** (no `DATABASE_URL`), so PostgreSQL-only migration branches do not run.
- **0.12.1 fixed a 0.12.0 reconnect loop** ("No reconnect loop after sign-in … since 0.12.0 it
  reconnected several times per second"). v0.12.3 carries that fix; §4.6 step 4 checks it.

### 1.5 Live facts (2026-10-17)

- `sts/open-webui` 1/1 on k8s-nuc14-01, image v0.11.4, pod started 2026-10-09T01:41:52Z, **no
  readiness, liveness or startup probe** — "Ready" is meaningless as a gate; §4 never uses it.
- Data: user 3, auth 3, chat 134, model 127, function 1, tool 0, skill 0, group 2, file 7,
  knowledge 0, channel/channel_member/message 0, USERS_NO_AUTH 0. `webui.db` is ~89 MB; the PVC is
  `open-webui-20g` (longhorn-static), volume healthy/attached — the §3.2 copy fits easily.
- Helm history: rev 56 `deployed` (16.6.0/0.11.4), rev 55 superseded; `maxHistory: 1`.
- Newest Longhorn backup `backup-37e437ec12a34269` at 2026-10-16T23:02Z;
  `longhorn-backup-age.py` printed "3.1h FRESH" and exit=0.
- Baselines: 0 migration/traceback log lines over 72 h; 4 `open-webui:*` redis keys.
- HTTPRoute `open-webui` parents on `envoy-external`. No in-cluster consumer calls open-webui's API;
  blast radius = the household's browser users.
- Security driver F-f3caadda: the board's contextual tier is **medium** (`risk_tier` on the record;
  the raw `severity` column reads critical). It is routed to this pipeline (`triage_lane COVERED`).
  Detail stays in the DB.

## 2. Pre-checks

**Unattended / operator-away rule (stop-safe).** If the operator is absent, no gate waits for a person:
any FAIL in §3.4 or §4 (except the host-side Ollama drift note in §4.6) runs §5 immediately and then
stops with the result recorded. A failed pre-check before §3.3 simply STOPs with nothing changed. The
restore uses ONLY the in-window pre-copy taken in §3.2; the §2.2 Longhorn backup is the last resort.

Run from `/Users/mu/code/cberg-home-nextgen` in zsh. Any FAIL means do not proceed.

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.0 neither superseded sibling may have run (premise app-image-current also guards this)
for p in open-webui-0.12.2; do
  printf '%s ' "$p"; grep -m1 '^status:' "runbooks/maintenance/plans/$p.md" 2>/dev/null || echo "retired"
done
#   PASS: each prints "retired", draft, or superseded. If either is executed/awaiting-soak, STOP: the
#   DB is no longer at d4c1a8e37b62 and this plan's baseline, copy and rollback image are wrong.

# 2.1 premises (read-only)
.venv/bin/python3 runbooks/plan-premises.py open-webui-0.12.3

# 2.2 backup freshness (Longhorn daily-backup-all-volumes lands ~23:00 UTC)
.venv/bin/python3 runbooks/longhorn-backup-age.py --max-hours 26 open-webui-20g; echo "exit=$?"
#   PASS: "open-webui-20g <N>h FRESH ..." and exit=0 (3.1h/exit=0 on 2026-10-17).
#   FAIL prints STALE/MISSING and exits non-zero.

# 2.3 alembic baseline + row-count snapshot (read-only sqlite URI)
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "
import sqlite3; c=sqlite3.connect('file:/app/backend/data/webui.db?mode=ro',uri=True)
print('ALEMBIC', c.execute('select version_num from alembic_version').fetchone()[0])
for t in ('user','auth','chat','model','tool','function','skill','group','file','knowledge','channel','channel_member','message'):
    print('COUNT', t, c.execute(f'select count(*) from \"{t}\"').fetchone()[0])
print('USERS_NO_AUTH', c.execute('select count(*) from user u left join auth a on a.id=u.id where a.id is null').fetchone()[0])
" | tee /tmp/owui-pre-counts.txt
#   PASS: ALEMBIC d4c1a8e37b62 and USERS_NO_AUTH 0 (both measured 2026-10-17). Any other head: STOP,
#   §1.3 and §5 no longer describe this DB. USERS_NO_AUTH > 0 is not a stop, but then expect §4.2
#   COUNT auth to grow by exactly that number.

# 2.4 baseline: app answers and logs are clean
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8080/api/version').read().decode())"
#   PASS: {"version":"0.11.4",...}
kubectl logs -n ai open-webui-0 -c open-webui --since=24h | grep -i -c -E "error running migrations|can't locate revision|traceback|noperm"
#   PASS: 0 (0 over 72h on 2026-10-17). This is the baseline §4.4 compares against.

# 2.5 nothing in flight on the release / Flux
helm history open-webui -n ai --max 1          # PASS: STATUS deployed (rev 56 on 2026-10-17)
flux get helmreleases -n ai open-webui         # PASS: READY True, no "in progress"
git fetch -q && git status -sb | head -1       # main not behind origin

# 2.6 the Renovate PR is still the expected one (stays UNMERGED)
gh pr view 333 --json state,title -q '.state+" "+.title'   # OPEN feat(container): ... ( v0.11.4 → v0.12.3 )
gh api repos/open-webui/open-webui/releases/latest --jq .tag_name   # PASS: v0.12.3
#   If 333 was retargeted again or a newer stable exists, STOP: DRIFTED plan. Refresh THIS file in
#   place (README "When the held target MOVES"): re-list the migrations, do not just bump the number.

# 2.7 stop-safe unattended: the Ollama host answers and the model list is the known pair (§4.6 compares)
curl -s -m 10 http://192.168.30.111:11434/api/tags | python3 -c "import sys,json;print(sorted(m['name'] for m in json.load(sys.stdin)['models']))"
#   PASS: ['gemma4:26b-mlx', 'nomic-embed-text:latest'] (2026-10-22). Host unreachable/other list is NOT
#   a stop for the upgrade, but then §4.6 step 3 is recorded "baseline differs", not failed.
```

## 3. Steps

### 3.1 Update marker (application-update SOP Step 1)

```bash
runbooks/update-marker.sh add open-webui ai 2 "open-webui 0.11.4->0.12.3"
```

The Alertmanager silence from the SOP is optional: the app has no app-specific PrometheusRule and the
expected restart count is 0.

### 3.2 Pre-change DB copy (the rollback artifact, taken immediately before the commit)

The sqlite online-backup API is WAL-safe while the app runs:

```bash
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "
import sqlite3, os
p='/app/backend/data/webui.db.pre-0.12.3'
s=sqlite3.connect('/app/backend/data/webui.db'); d=sqlite3.connect(p)
s.backup(d); d.close()
c=sqlite3.connect('file:'+p+'?mode=ro',uri=True)
print('COPY_BYTES', os.path.getsize(p))
print('COPY_ALEMBIC', c.execute('select version_num from alembic_version').fetchone()[0])
print('COPY_CHATS', c.execute('select count(*) from chat').fetchone()[0])
print('COPY_INTEGRITY', c.execute('pragma integrity_check').fetchone()[0])"
```

- **PASS** requires all four: `COPY_BYTES` > 0; `COPY_ALEMBIC d4c1a8e37b62`; `COPY_CHATS` equal to
  the `COUNT chat` line in `/tmp/owui-pre-counts.txt`; `COPY_INTEGRITY ok`.
- Anything else: **STOP before the §3.3 edit** (nothing changed yet). Without this file there is no rollback.
- Integrity proof of the copy, taken now and re-checked at restore time (§5.2): record
  `PRE_SHA=$(kubectl exec -n ai open-webui-0 -c open-webui -- sha256sum /app/backend/data/webui.db.pre-0.12.3 | cut -d' ' -f1)`
  and `echo "$PRE_SHA"`; the empty string or an exec error also means STOP before the edit.
- `COPY_BYTES` may be smaller than the source (the backup compacts it).

### 3.3 The image edit

One commit: image tag plus `retries: 0`. Dry-tested on a scratch copy of the live file on macOS
(BSD sed) on 2026-10-22 (same lines as 2026-10-17); the resulting `diff` is exactly:

```
25c25   <       retries: 1          >       retries: 0      (upgrade: block; install retries: 3 untouched)
120c120 <       tag: v0.11.4        >       tag: v0.12.3
```

`yq` on the scratch copy then printed `16.6.0 / v0.12.3 / 0 / 3 / 8.10.1-alpine`.

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/ai/open-webui/app/helmrelease.yaml
sed -i '' \
  -e 's/^      tag: v0\.11\.4$/      tag: v0.12.3/' \
  -e '/^  upgrade:$/,/^  uninstall:$/s/^      retries: 1$/      retries: 0/' \
  "$F"
git diff --stat -- "$F"         # PASS: 1 file, 2 insertions(+), 2 deletions(-)
yq '.spec.chart.spec.version, .spec.values.image.tag, .spec.upgrade.remediation.retries, .spec.install.remediation.retries, .spec.values.websocket.redis.image.tag' "$F"
#   PASS, in order: 16.6.0 / v0.12.3 / 0 / 3 / 8.10.1-alpine (chart and sidecar untouched)

MSG=$(mktemp /tmp/owui-msg.XXXXXX)
cat > "$MSG" <<'EOF'
feat(open-webui): app v0.11.4 -> v0.12.3

Plan open-webui-0.12.3 (supersedes open-webui-0.12.2; chart 17 is the
separate plan open-webui-17.0.0). App runs 8 forward-only
alembic migrations (head d4c1a8e37b62 -> 0bd252b206fb). Pre-change copy
webui.db.pre-0.12.3 taken in-pod. upgrade.remediation.retries 0 for the
attempt (restored after verification). Satisfies Renovate #333.
security_ref F-f3caadda.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
git commit --only "$F" -F "$MSG"
git log -1 --format=%s          # MUST be the subject above (shared-worktree message-swap guard)
git show --stat HEAD            # exactly that one file
git push; rm -f "$MSG"
```

Flux applies via the push webhook. No manual reconcile unless nothing happened after 10 minutes; then
`flux reconcile helmrelease -n ai open-webui --with-source`.

### 3.4 Watch the roll

```bash
# wait for the NEW image on the live pod (rollout status can green-light the old generation)
for i in $(seq 1 40); do
  IMG=$(kubectl get pod -n ai open-webui-0 -o jsonpath='{.spec.containers[0].image}' 2>/dev/null)
  PH=$(kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.phase}' 2>/dev/null)
  echo "$IMG $PH"; [ "$IMG" = "ghcr.io/open-webui/open-webui:v0.12.3" ] && [ "$PH" = "Running" ] && break
  sleep 15
done
kubectl logs -n ai open-webui-0 -c open-webui --since=10m | grep -i -E "running migrations|running upgrade|error" | head -20
#   Expect "Running migrations" and alembic "Running upgrade d4c1a8e37b62 -> a7d3e9f2b641" ...
#   "-> c92da83b017f" ... "-> 0bd252b206fb".
```

If the pod is not on v0.12.3 and Running after 10 min, or the log shows `Error running migrations`,
go to §5.

### 3.5 After §4 passes: restore remediation retries (second commit)

```bash
sed -i '' -e '/^  upgrade:$/,/^  uninstall:$/s/^      retries: 0$/      retries: 1/' "$F"
git diff -- "$F" | grep -E '^[-+] ' # PASS: exactly "-      retries: 0" / "+      retries: 1" (dry-tested 2026-10-17)
MSG=$(mktemp /tmp/owui-msg.XXXXXX); printf 'chore(open-webui): restore upgrade remediation retries after 0.12.3\n\nCo-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>\n' > "$MSG"
git commit --only "$F" -F "$MSG"; git log -1 --format=%s; git show --stat HEAD; git push; rm -f "$MSG"
runbooks/update-marker.sh clear open-webui   # skip if open-webui-17.0.0 runs next in this window
```

Do NOT clear the update marker here if open-webui-17.0.0 is scheduled in the same window; the chart plan clears it. This changes only HelmRelease spec fields that do not render into the manifest: a Helm revision, no
pod roll. Confirm afterwards that the `open-webui-0` startTime is unchanged.

Then:

1. Retire `open-webui-0.12.2.md` (status `superseded` or delete) if it still exists.
2. Confirm Renovate closed PR 333 on its next run; close by hand only if still open after 24 h. PR 334
   stays open for the chart plan.
3. Close the version finding this plan owns:
   `policy-cli.py finding close F-c4303aae --commit <sha>`. Check on the next sweep that
   F-f3caadda clears, or re-forms against v0.12.3.

## 4. Verification

Run every gate after §3.4. Each gate can FAIL; the failure output is noted.

**4.0 Timing guard (run first; later gates are vacuous before this passes).**
```bash
S=$(kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.startTime}')
AGE=$(python3 -c "import sys,datetime as d;print(int((d.datetime.now(d.timezone.utc)-d.datetime.fromisoformat(sys.argv[1].replace('Z','+00:00'))).total_seconds()))" "$S")
echo "POD_AGE_S $AGE"
[ "$AGE" -ge 600 ] || { echo "WAIT $((600-AGE))s"; sleep $((600-AGE)); }
```
PASS: the pod is at least 600 s old before 4.3/4.4 are read (the sleep enforces it). An early read of the
restart counter or the logs would otherwise pass vacuously.

**4.1 Version actually served**
```bash
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8080/api/version').read().decode())"
kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.containerStatuses[0].imageID}'
```

- PASS: `"version":"0.12.3"`, and an imageID ending
  `a537bbe1e6b428820f52ed4a029d7fff97062e24d5cf32c365fba36fd0542def`.
- FAIL: `"version":"0.11.4"` (the live reading on 2026-10-17) or digest `9591b13f…`.
  `"version":"0.12.0"` means the chart default leaked (image.tag edit lost): also FAIL.

**4.2 Schema migrated and data intact** (the CONTENTS assertion)
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

- PASS needs all of: `ALEMBIC 0bd252b206fb`; the `diff` empty or differing only by chat/file growth
  during the window (`user`, `auth`, `model`, `group` identical; `auth` stays 3); `MODEL_HISTORY` ==
  COUNT model (127 on 2026-10-17); `MODEL_UNVERSIONED 0`; `FUNCTION_HISTORY` == COUNT function (1);
  `APP_TABLE 0` and `CM_APP_COL 1`; `INTEGRITY ok`.
- FAIL looks like: `ALEMBIC d4c1a8e37b62` (no migration ran); `ALEMBIC b8f2c6d91a04` (0.12.1
  revisions failed); `no such table: model_history` / `no such table: app` (a revision did not
  apply); `MODEL_HISTORY 0` or `MODEL_UNVERSIONED` > 0 (backfill skipped/partial); `CM_APP_COL 0`
  (table copy incomplete); a shrunken COUNT (data loss → §5 immediately).
- A chat-count-only check would stay green on a DB whose model registry was emptied; hence model and
  model_history are asserted.

**4.3 No crash loop.** The pod has no probes, so this is the only liveness evidence.

CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="ai",pod="open-webui-0",container="open-webui"}` must read 0 at least 10 min after the new pod started. The STS pod is recreated, so the counter starts at 0. FAIL: ≥1, which is how an import-time migration crash shows on a probe-less pod.

CONTROL: metric kube_statefulset_status_replicas_ready — `{namespace="ai",statefulset="open-webui"}` == 1. Without probes this is a shape check, kept only to catch a pod that never started (ImagePull/Pending).

CONTROL: metric kube_deployment_status_replicas_available — `{namespace="ai",deployment="open-webui-redis"}` == 1. The redis pod does not roll in this plan; this guards that it stayed up.

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
- `N 0 []` is a FAIL (the instrument read nothing), never a pass. The parser distinguishes "no
  series" from "0" (negative control `pod="open-webui-nonexistent"` printed `N 0 []`, 2026-10-15).

**4.4 Logs clean**
```bash
kubectl logs -n ai open-webui-0 -c open-webui --since=30m | grep -i -c -E "error running migrations|can't locate revision|traceback|noperm"
# POSITIVE CONTROL over the same window: the 8 migrations must have logged (matches §3.4)
kubectl logs -n ai open-webui-0 -c open-webui --since=30m | grep -i -c "running upgrade"
```

- PASS: first count 0 (baseline 0 over 72 h, §2.4) AND second count >= 8. A 0 with a control of 0 means the log
  window missed the start (or logs rotated), which is a FAIL, not a pass. Any error hit is new. Case-insensitive because upstream mixes
  `Error`/`ERROR`; `noperm` catches the 0.12.3 room-channels permission message (§1.4) should the
  redis ACL ever differ from the measured `+@all`.

**4.5 Websocket redis consumer reconnected** (the app pod restarted against a redis that kept running)
```bash
kubectl exec -n ai deploy/open-webui-redis -- redis-cli set owui-plan-probe ok EX 60
kubectl exec -n ai deploy/open-webui-redis -- redis-cli get owui-plan-probe
kubectl exec -n ai deploy/open-webui-redis -- redis-cli --scan --pattern 'open-webui:*' | wc -l
```

- PASS: `OK`, `ok`, then ≥1 (baseline 4 keys on 2026-10-17).
- FAIL: 0 `open-webui:*` keys 5 min after the app start → the app is not talking to redis (baseline 4). A bare
  `PONG` would not reveal that.

**4.6 Real path through the public edge, and Ollama reachability**
```bash
H=$(kubectl get httproute -n ai open-webui -o jsonpath='{.spec.hostnames[0]}')
curl -s -o /dev/null -w '%{http_code}\n' "https://$H/health"
curl -s "https://$H/api/version"
```

- PASS: `200` and `"version":"0.12.3"`.
- FAIL: a 5xx from envoy (backend down), or `"version":"0.11.4"` (stale pod behind the route).

Behaviour gates that run unattended (each can FAIL):

```bash
# (a) login surface: local auth only. There is NO OAuth/OIDC env on the pod (live env listing
# 2026-10-22: no OAUTH/OIDC vars) and no Authentik SecurityPolicy on the route, so there is no
# Authentik redirect to test; the check below asserts the sign-in config is served and OAuth stays absent.
curl -s "https://$H/api/config" | python3 -c "
import sys,json; d=json.load(sys.stdin)
print('VERSION', d.get('version')); print('AUTH', d['features']['auth']); print('OAUTH', sorted(d.get('oauth',{}).get('providers',{}).keys()))"
#   PASS: VERSION 0.12.3 / AUTH True / OAUTH []. FAIL: non-JSON (500/HTML, app broken), AUTH False
#   (auth disabled -> open instance, roll back), or a non-empty OAUTH list (config leaked/changed).
# (b) model list from the Ollama host as seen BY the app: unauthenticated /api/models is 401 by design,
# so ask the app container to call the backend it is configured with:
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "
import urllib.request,json,os
u=os.environ['OLLAMA_BASE_URLS'].split(';')[0].rstrip('/')
print('OLLAMA_MODELS', sorted(m['name'] for m in json.load(urllib.request.urlopen(u+'/api/tags',timeout=10))['models']))"
#   PASS: ['gemma4:26b-mlx', 'nomic-embed-text:latest'] (the §2.7 baseline). FAIL: connection error
#   (network/ollamaUrls broken) or a different list while §2.7 matched. Host-side drift is not an upgrade
#   failure: if §2.7 already differed, record only.
```

Operator/Chrome check (attended windows; a nightly run records it as pending for the morning report):

1. Log in with the existing session cookie; it must still be valid (§1.4).
2. Open an existing chat; its history must render.
3. Send one short prompt to an Ollama model; it must stream a reply (`ollamaUrls` → 192.168.30.111:11434).
4. Reload the tab once; it must NOT reconnect-loop (0.12.0 regression, fixed 0.12.1).

## 5. Rollback

**Decision rule:**

- If §4.2 shows ALEMBIC `d4c1a8e37b62` (no migration ran), a plain revert of the §3.3 commit is a
  complete rollback.
- In every other failure case the schema has moved forward and the DB restore below is **required**
  before v0.11.4 can start.

Chats written between the §3.2 copy and the restore are lost; tell the users (typically minutes).

```bash
cd /Users/mu/code/cberg-home-nextgen
F=kubernetes/apps/ai/open-webui/app/helmrelease.yaml

# 5.1 stop Flux from re-applying 0.12.3 and release the RWO volume
flux suspend helmrelease -n ai open-webui
kubectl scale sts -n ai open-webui --replicas=0
kubectl wait -n ai pod/open-webui-0 --for=delete --timeout=180s

# 5.2 restore through a throw-away pod mounting the PVC (open-webui-0 does NOT exist at replicas 0)
kubectl run -n ai owui-restore --restart=Never --image=ghcr.io/open-webui/open-webui:v0.11.4 \
  --overrides='{"apiVersion":"v1","spec":{"containers":[{"name":"r","image":"ghcr.io/open-webui/open-webui:v0.11.4","command":["sleep","3600"],"volumeMounts":[{"name":"d","mountPath":"/app/backend/data"}]}],"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"open-webui-20g"}}]}}'
kubectl wait -n ai pod/owui-restore --for=condition=Ready --timeout=300s
kubectl exec -n ai owui-restore -c r -- sha256sum /app/backend/data/webui.db.pre-0.12.3
#   PASS: equals PRE_SHA from §3.2. Different = the copy changed; STOP and use the Last resort below.
kubectl exec -n ai owui-restore -c r -- python3 -c "
import sqlite3, os, shutil, time
src='/app/backend/data/webui.db.pre-0.12.3'; dst='/app/backend/data/webui.db'
shutil.copy2(dst, dst+'.failed-0.12.3.'+time.strftime('%Y%m%d_%H%M%S'))   # keep the migrated DB for diagnosis
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

# 5.3 revert the manifest (image + retries) and resume
SHA=$(git log -1 --format=%H --grep='^feat(open-webui): app v0.11.4 -> v0.12.3$' -- "$F")
SHA2=$(git log -1 --format=%H --grep='^chore(open-webui): restore upgrade remediation retries after 0.12.3$' -- "$F")   # empty if §3.5 never landed
git show --stat "$SHA"          # confirm it is the §3.3 commit and ONLY that file
MSG=$(mktemp /tmp/owui-revert.XXXXXX); printf 'revert: open-webui back to v0.11.4 (plan open-webui-0.12.3 rollback)\n\nCo-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>\n' > "$MSG"
# if §3.5 landed its retries hunk conflicts with a lone revert: revert BOTH, newest first
git revert --no-commit ${SHA2:+$SHA2} "$SHA" && git commit --only "$F" -F "$MSG"
git log -1 --format=%s; git show --stat HEAD; git push; rm -f "$MSG"
flux resume helmrelease -n ai open-webui        # the reconcile restores replicas 1 on v0.11.4
```

If §3.5 had already landed, the revert must also restore `retries: 1`: check
`yq '.spec.upgrade.remediation.retries' "$F"` and fix it in the same commit.

**5.4 Confirm the cluster is back.**

- Re-run §4.1: expect `0.11.4` with digest `9591b13f…`.
- Re-run §4.2: expect ALEMBIC `d4c1a8e37b62` and COUNT lines equal to the §2.3 snapshot; the
  model_history/app lines error with "no such table" (expected on the old schema).
- Re-run §4.3/§4.4: 0 restarts, 0 error lines.

**Last resort** (the pre-0.12.3 copy is missing or fails integrity): restore volume `open-webui-20g`
from the §2.2 Longhorn backup per `docs/sops/backup.md` "Restore from Backup" (loses up to ~24 h of
chats).

**Helm wedged `pending-upgrade`:** application-update SOP §7/§11. `helm rollback open-webui 56 -n ai
--wait=false` only if revision 56 still exists (`maxHistory: 1` may have pruned it). A Helm rollback
restores the manifest only, **never** the DB, so 5.1–5.2 still apply.

**Cleanup after success (not a rollback):** keep `webui.db.pre-0.12.3` for 7 days, then
`kubectl exec -n ai open-webui-0 -c open-webui -- rm /app/backend/data/webui.db.pre-0.12.3`.
`webui.db.bak-mlx-migration-20260904214756` is unrelated; leave it to its owner.

## 6. Interference notes

- **Supersedes `open-webui-0.12.2`** (set it `status: superseded` before vetting; it targets the same
  line one patch older and would be a downgrade across the migration chain: "Can't locate revision").
  **Chain:** `open-webui-17.0.0` (chart) `depends_on` this plan. If this plan fails and is rolled back,
  the chart plan must not run; its premise `image-migrated` fails closed.
- **Process note:** README says a moved target is refreshed IN PLACE. This file was refreshed in place
  on 2026-10-22 (split + re-verified newest stable); `open-webui-17.0.0` was rewritten as the chart-only
  plan, same id, so `envoy-proxy-config-distroless-v1.39.4`'s reference stays valid.
- **`redis-fleet-8.10.2` is stale on its open-webui leg** (vetted, `sun-attended:2026-10-25`).
  - Its leg 3 moves open-webui 0.11.3→0.11.4 and chart 16.5.0→16.6.0; both landed 2026-10-09, so its
    open-webui premise fails as written. It edits the same file → `conflicts_with`.
  - If this plan runs first, its leg 3 shrinks to the sidecar tag alone, and its pre-copy name,
    alembic expectation and restore image are wrong for a DB at `0bd252b206fb`; its rollback must use
    this plan's §5 (v0.12.3 image for the post-state, `webui.db.pre-0.12.3`). Its owner needs a delta
    re-review either way. Reciprocal entries are not written (a planner writes only its own file).
- **`flux-oci-chart-sources`** (`sun-attended:2026-11-22`) inventories open-webui at OCI chart 16.5.0.
  After the chart plan (open-webui-17.0.0) it must pin 17.0.0, otherwise its source move is a chart **downgrade** (not of the
  image, which is pinned in values).
- **`kube-prometheus-stack-92.2.0`**: §4.3 reads kube-state-metrics through Prometheus → in
  `conflicts_with` (window instrument = shared infra).
- **Envoy proxy plans** (`…-v1.39.3`, `…-v1.39.4`, `…-v1.40.0`): §4.6 reads the app through
  envoy-external; do not co-schedule.
- **Shared infra perturbed: none.** HTTPRoute, Gateway, Service selector/port and LB unchanged. The
  no other pod rolls (redis and pipelines untouched). Ollama
  on the Mac mini is only read. Other ns-`ai` plans (`anythingllm-1.18`, `next-ai-draw-io-0.5.0`,
  `python-fleet-3.15.0`/`-3.14.8` mcpo init) share only the namespace: no shared objects, PVCs or files.
- **Execution class:** `capability_change: true` + `rollback_class: backup-restore` →
  **HUMAN-GATED** (operator GO). It fits a nightly window (45 of 70 schedulable min) once GO is
  recorded; an attended sat/sun slot is preferable so the §4.6 Chrome check (incl. the reconnect-loop
  reload) happens in the window. No reboot needed, so it does not need the Sunday slot.
- Run it **after the Longhorn daily backup** (any window ≥ 03:30 satisfies §2.2).
- Security note: F-f3caadda's contextual tier is medium (external-auth, not in KEV). The prior draft
  called it `critical`, quoting the raw severity column — not this household's tier. It is still the
  reason not to let this plan sit unscheduled. Detail stays in the DB.
