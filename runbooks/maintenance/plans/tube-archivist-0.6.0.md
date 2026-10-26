---
plan_id: tube-archivist-0.6.0
component: tube-archivist
pr: 432                               # Renovate "update bbilly1/tubearchivist ( v0.5.12 → v0.6.0 )", 1 file (helmrelease.yaml tag).
                                      # NOT merged as-is: the tag alone crash-loops the pod (§1.3). This plan lands two
                                      # direct commits (probes, then tag + image-sync); Renovate auto-closes #432
                                      # once main carries v0.6.0 (§3.6) — it is never closed or merged by hand.
kind: image
current: "bbilly1/tubearchivist:v0.5.12 (sha256:ba1c846d…)"
target: "v0.6.0"                      # Docker Hub index digest sha256:0cbc18aa953c72ec7dfdd6f8fa7c2fe89b5d04489857d7baa354fecbd6181e69
                                      # (GitHub release v0.6.0: prerelease=false, draft=false, published 2026-10-25T08:00:35Z)
update_type: minor
risk: medium                          # the bare tag bump is a guaranteed crash-loop (every probe gets HTTP 400, §1.3) and
                                      # silently corrupts Jellyfin artwork for any new channel (§1.4); both are fixed by this
                                      # plan's edits and both are reversible by git revert. No DB/ES schema change (§1.5).
est_duration_min: 55                  # pre-checks 10 · commit A (probes) + Flux + verify on v0.5.12 10 ·
                                      # pre-roll gate control 3 · commit B + Flux + pull/start 12 · verification 18 (incl. the
                                      # real-script gate, its control and the enforced observation waits) · close-out 2.
                                      # sat-attended budget is 70 (90 - 20 Step 0).
needs_reboot: false
touches:
  namespaces: [download]
  resources:                          # every object verified to EXIST live 2026-10-26 (kubectl get)
    - helmrelease/tube-archivist                  # EDITED twice (probes; tag)
    - deployment/tube-archivist                   # Recreate strategy: ~1-3 min UI/API outage per roll (two rolls)
    - configmap/tube-archivist-image-sync         # EDITED (artwork URL, Host header, content-type guard, fail-loud)
    - cronjob/tube-archivist-image-sync           # consumes the configmap; not edited
    - httproute/tube-archivist                    # not edited; backend behind it changes from nginx to Django/uvicorn
    - pvc/tube-archivist-cache-2g                 # longhorn-static, remounted; holds db.sqlite3 + artwork cache; not modified by schema
    - pvc/tube-archivist-youtube                  # cifs-tube-archivist-media (SEVERE tier), remounted only. NO PVC operations.
                                                  # The §4.5 gate writes only to a scratch dir under /tmp INSIDE the app pod.
  shared: [gateway/envoy-external, monitoring, media/jellyfin-tubearchivist-plugin, cifs-tube-archivist-media]
                                      # envoy-external: the route is public; what answers behind it changes.
                                      # monitoring: §4 reads Prometheus (TubeArchivist* alerts, kube-state-metrics).
                                      # jellyfin plugin: reads TA API + artwork through the public host (§1.6).
                                      # CIFS share: remounted by the Recreate roll; nothing written by this plan.
depends_on:
  - tube-archivist-elasticsearch-9.5.5  # PR #433, ES 8.19.0 → 9.5.5. ES first under v0.5.12, then this on a LATER night.
                                      # Not a hard technical prerequisite (both app tags accept ES majors 8..9) but one
                                      # agreed order keeps the two plans attributable (§6). Enforced by the scheduler
                                      # (unmet depends_on) and by the §2.1 gate that requires ES 9.5.5 to be live.
conflicts_with:
  - tube-archivist-elasticsearch-9.5.5  # and NOT the same window: same namespace, same app pod restarts; §4 must be
                                      # attributable to one change. Run on a later night than the ES plan.
  - redis-fleet-8.10.2                # restarts download/tube-archivist-redis and deployment/tube-archivist (its leg list);
                                      # two causes for one TA restart make §4 unattributable. Reciprocity owed in that plan.
  - flux-reconciler-impersonation     # uses kustomization/tube-archivist + its HelmReleases as the canary; changing WHO
                                      # applies them in the same window as a content change makes a failure unattributable.
  - media-naming-p3                   # renames on the shared media surface Jellyfin/TA read; §4.6 artwork/plugin checks
                                      # would not be attributable.
  - helm-drift-detection              # its gate asserts identical Helm revisions; this plan creates two new revisions of
                                      # helmrelease/tube-archivist and edits a configmap in the same kustomization.
  - flux-oci-chart-sources            # re-points the app-template chart sources this HelmRelease renders from.
  - envoy-proxy-config-distroless-v1.39.4   # §4.6 reads the public path through envoy-external; a proxy roll in the same
                                      # window makes a 5xx there unattributable.
exclusive: false
security_ref: null                    # not security-driven
capability_change: false              # same app, same features in use, same exposure and auth settings (no env change, the route is
                                      # untouched, we do NOT adopt the new optional non-root mode, no new credential or secret key).
                                      # Upstream moved its internal artwork/media URL paths and dropped nginx; our only consumer of a
                                      # hard-coded path (image-sync) is adapted to keep doing exactly what it does today. The class stays
                                      # HUMAN-GATED anyway (medium risk / no pre-approved class): confirmed with
                                      # maintenance-plan.py --json --skip-coverage.
rollback_class: git-revert            # nothing forward-only: v0.6.0 adds no Django migrations (diff of migrations/ v0.5.12..
                                      # v0.6.0 is empty), the ES index_mapping.json is byte-identical, and file ownership is not
                                      # touched (we stay root; v0.6.0 no longer chowns at all). Upstream: "you can revert to
                                      # v0.5.12". Pre-change Longhorn backup of the cache volume + ES daily snapshot are the
                                      # belt-and-braces (§2.4), not a required restore path.
finding_refs: [F-ea63179f, F-145b1d1e] # `finding list --grep tube` 2026-10-26: the two AR-029 register rows on the v0.5.12
                                      # image ("already newest" — no longer true since v0.6.0 shipped 2026-10-25). This bump
                                      # is what moves them; whether they clear is for the next sweep's scan to MEASURE. Detail
                                      # stays on the records.
review: ready-for-go@2026-10-26   # plan-reviewer 2026-10-26: needs-fix on one blocker (false static-auth token premise), token machinery removed + stub-tested; HUMAN-GATED, window null
status: vetted
window: null                          # recommended: sat-attended:2026-12-05 (§6), AFTER the ES plan's night; not stamped while draft
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/storage-safety.md       # CIFS PVC is severe tier — remount only, no PVC/PV operations
  - docs/sops/longhorn-rwo-multi-attach.md   # strategy: Recreate already set and kept
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/vulnerability-disclosure.md
  - docs/sops/auto-update.md
generated: "2026-10-26"
premises:
  # Read-verb only. Each run live 2026-10-26 and returned the expected value.
  - id: ta-running-v0512
    why: >-
      current: claims the live app runs v0.5.12. If it already runs v0.6.0 someone merged #432 bare — the pod is then
      crash-looping (§1.3) and this plan becomes an incident fix (apply commit A immediately), not a scheduled bump.
    run: kubectl get deploy tube-archivist -n download -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: "bbilly1/tubearchivist:v0.5.12"
  - id: ta-ready
    why: >-
      Pre-state healthy: one ready replica. A pod already not-ready would mask (or be blamed on) the probe change.
    run: kubectl get deploy tube-archivist -n download -o jsonpath='{.status.readyReplicas}'
    expect_exact: "1"
  - id: ta-hr-ready
    why: >-
      The HelmRelease is Ready before the change; a failed/pending release would swallow commit A.
    run: kubectl get hr tube-archivist -n download -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: es-on-supported-major
    why: >-
      v0.6.0 accepts ES majors 8..9 (ta_connection MIN_MAJOR, MAX_MAJOR = 8, 9), so this premise passes on 8.19.0 too and
      does NOT enforce ordering: ordering is enforced by `depends_on` (window-scheduler.py skips a plan with an unmet
      depends_on) and by the explicit must-read-9.5.5 gate in §2.1, which is a pre-check that FAILS on 8.19.0. This premise
      only catches drift to some third value.
    run: kubectl get deploy tube-archivist-elasticsearch -n download -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_matches: 'tubearchivist-es:(8\.19\.0|9\.5\.5)$'
  - id: no-removed-env-vars
    why: >-
      v0.6.0 ta_envcheck raises CommandError (pod never starts) if HOST_UID, HOST_GID or TA_BACKEND_PORT is set. Must be 0.
    run: grep -c -e HOST_UID -e HOST_GID -e TA_BACKEND_PORT kubernetes/apps/download/tube-archivist/app/helmrelease.yaml
    expect_exact: "0"
  - id: probes-not-yet-fixed-or-fixed
    why: >-
      Startup probe path is "/" (commit A not yet landed) or "/api/health/" (commit A already landed in a previous
      attempt — skip §3.2). Any other value means someone changed the probes; re-review.
    run: kubectl get deploy tube-archivist -n download -o jsonpath='{.spec.template.spec.containers[0].startupProbe.httpGet.path}'
    expect_matches: '^(/|/api/health/)$'
  - id: image-sync-on-old-path
    why: >-
      The image-sync script still fetches /cache/channels/ (exactly one occurrence) — the anchor patch_bump.py rewrites.
      0 means it was already adapted; re-review instead of re-patching.
    run: grep -c cache/channels kubernetes/apps/download/tube-archivist/app/image-sync-configmap.yaml
    expect_exact: "1"
  - id: deny-rule-present
    why: >-
      The auto-update deny rule for this image (`match: "*bbilly1/tubearchivist*"`, `max: patch`, policy 2026.10.26) is what
      stops a bare minor bump of the app from auto-merging at Step 0. This plan does NOT remove it. 0 = the rule was lost: stop.
    run: grep -c -E '^[[:space:]]+-[[:space:]]+match:.*bbilly1/tubearchivist' runbooks/auto-update-policy.yaml
    expect_exact: "1"
---

# tube-archivist-0.6.0 — Tube Archivist v0.5.12 → v0.6.0 (nginx removed; probes + image-sync must change with it)

## 1. Summary & why held

### 1.1 Why #432 is held, what is verified, what is not

Verified against primary sources 2026-10-26:

| Source | Result |
|---|---|
| Docker Hub tags API (`hub.docker.com/v2/repositories/bbilly1/tubearchivist/tags`) | `v0.6.0`, `unstable` **and `latest`** all = `sha256:0cbc18aa953c72ec…`, pushed within 6 s of each other (08:45:34–08:45:40Z 2026-10-25) |
| GitHub `releases/tags/v0.6.0` (`tubearchivist/tubearchivist`) | `prerelease: false`, `draft: false`, published 2026-10-25T08:00:35Z |

v0.6.0 is a stable release; `unstable == latest == v0.6.0` on release day is how upstream's pipeline pushes tags.

**What I could NOT verify: what held #432 before today.** Until 2026-10-26 `runbooks/auto-update-policy.yaml` had NO
deny rule naming this image, so nothing in the policy was holding a minor bump of it: the PR could have merged
unattended at Step 0 of any window. Why it stayed open is not established by anything I could read, so the earlier
"target == unstable == latest is a false-positive hold" explanation and the repo correction that went with it are
DROPPED: that correction would only be safe once the image is protected by a rule, and relaxing a channel gate on
one release's evidence is not proposed here.

**The protection that exists now (policy version 2026.10.26):** deny rule `*bbilly1/tubearchivist*`, `max: patch`.
Verified with `auto-update.policy_block` on 2026-10-26: `bbilly1/tubearchivist` patch allowed, minor BLOCK,
major BLOCK. **This plan's execution does NOT remove or loosen that rule** (premise `deny-rule-present` asserts
it exists): v0.6.x patches stay AUTO, minor and above stay in the PLAN lane. The glob also matches
`bbilly1/tubearchivist-es` (same method: patch allowed, minor+ blocked); that is harmless for the Elasticsearch plan
(its 9.5.5 bump is a major and was held anyway) and sensible for future ES minors, but the rule's comment says the
ES image "is NOT matched", which is inaccurate. Reported as a repo correction, not changed here.

The update is also correctly non-safe on its own merits: it has breaking changes that hit this deployment (below).

### 1.2 Upstream breaking changes (release notes v0.6.0, verbatim)

> - To support this, the bundled nginx server has been removed. All media and artwork are now served directly by the application.
> - There are breaking changes. Read the migration guide before updating.
> - If you are not yet ready, you can revert to v0.5.12 once you see the startup error, no state will have changed at that point.
>
> 1. Remove `HOST_UID` and `HOST_GID` from your environment variables. [...] Setting a user is optional. Without it, the container continues to run as root. Tube Archivist no longer changes file ownership itself.
> - Remove `TA_BACKEND_PORT` if you have set it. [...] The default remains `8000`.
> **Media URLs** — Video, subtitle and artwork URLs have changed. If you use saved direct links, custom integrations or reverse proxy rules for these paths, update them to use the URLs returned by the API.
> **Upgrading from older releases** — Update older installations to v0.5.12 and let startup complete before moving to v0.6.0.
> **Elasticsearch** — The Elasticsearch update path is from `8.19.0` to `9.5.5`. If you use `bbilly1/tubearchivist-es`, update it together with Tube Archivist.

Not applicable here (checked): no `HOST_UID`/`HOST_GID`/`TA_BACKEND_PORT`/`TA_PORT` in the HelmRelease or live env
(premise `no-removed-env-vars`); we are on v0.5.12 with startup completed (28 d uptime); we do not adopt the optional
non-root user (no chown of the CIFS share — out of scope, and it would be a behaviour change). Snapshot behaviour
change ("Disabling snapshots now deletes existing snapshots") does not bite: `ta_config` has `enable_snapshot: true`
(read live), and this plan does not touch it.

### 1.3 What breaks in OUR wiring — the pod would never become Ready (proved from code + live measurement)

In v0.5.12 nginx served `/` directly from `/app/static` (`docker_assets/nginx.conf`, `location / { try_files ... }`)
regardless of the Host header. In v0.6.0 there is no nginx; uvicorn/Django answers everything
(`docker_assets/backend_start.py`), `/` is `views_frontend.frontend_index` (catch-all `re_path` in
`backend/config/urls.py`), and every request passes `django.middleware.common.CommonMiddleware`
(`config/settings.py` MIDDLEWARE), which rejects a Host not in `ALLOWED_HOSTS` with **HTTP 400**.
`ALLOWED_HOSTS` = `["localhost", "tubearchivist", <TA_HOST hostname>]` (`common/src/helper.py` `ta_host_parser`).

Our probes, as deployed:

| Probe | Request | Host header sent | v0.6.0 result |
|---|---|---|---|
| startup / readiness | kubelet `httpGet /` port 8000 | `<podIP>:8000` | 400 → probe fails |
| liveness (exec) | `urlopen("http://127.0.0.1:8000/")` | `127.0.0.1:8000` | 400 → `HTTPError` → exit 1 |

Live proof of the Django behaviour on today's v0.5.12 (its `/api/` already goes to Django), 2026-10-26, inside the pod:
`GET 127.0.0.1:8000/api/ping/` with `Host: 127.0.0.1:8000` → **400**; `Host: tube-archivist:8000` → **400**;
`Host: localhost` → **403** (passes host validation, then auth). So the bare tag bump = startup probe fails 30×10 s
→ container restarted → CrashLoopBackOff, `TubeArchivistPodNotReady`/`CrashLooping` fire.

**Fix (commit A, compatible with BOTH versions):** probe `GET /api/health/` with `Host: localhost`.
`/api/health/` is `common.views.HealthCheck` — `"health check view, no auth needed"`, returns `"OK"` 200 — present
in v0.5.12 and v0.6.0 alike, and is what upstream's own docker-compose healthcheck uses
(`curl -f http://localhost:8000/api/health/`). Measured live on v0.5.12: `Host: localhost` → `200 b'"OK"'`.
The liveness probe keeps its second half (celery worker present in `/proc/*/cmdline`; v0.6.0 `run.sh` still starts
`celery -A task.celery worker`).

### 1.4 What breaks silently — image-sync would write HTML into Jellyfin artwork

`cronjob/tube-archivist-image-sync` (hourly :30) copies channel art into each channel folder on the CIFS share for
Jellyfin (`folder.jpg`, `backdrop.jpg`, `banner.jpg`) from `http://tube-archivist:8000/cache/channels/<id>_<art>.jpg`.
In v0.6.0:
- `/cache/...` matches the frontend catch-all → **200 `text/html` (the SPA index.html)**. The script only checks
  `status == 200`, so it would write an HTML page as `folder.jpg` for every newly subscribed channel. Silent: the
  Job completes, the counter reads "copied".
- The new artwork route is `/media/thumb/channel/<channel_id>/<thumb|tvart|banner>.jpg`
  (`common/urls_static.py`, `views_static.ChannelArtView`; content-type `image/jpeg`, 404 when the file is absent).
- Its Host `tube-archivist:8000` is not in `ALLOWED_HOSTS` → 400 (the hyphenated Service name ≠ `tubearchivist`).

Today the job reads `copied=0 skipped(existing)=81 source-missing/404=0` (last run, 2026-10-26), so nothing is
corrupt yet and **no request is made at all** (every channel folder already has all three files); the damage would
appear with the next new channel. **Fix (commit B, same commit as the tag):** new URL, `Host: localhost`, refuse any
non-`image/*` body, and exit non-zero on any non-404 error so a future regression fails the Job instead of reading as
"404". The request shape is otherwise unchanged (no new credential, no new secret, no CronJob edit). It must ship in the
same commit as the tag: on v0.5.12 the new path is not an image, so a revert of commit B restores tag and sync together.

### 1.5 Data / schema — nothing forward-only

- Django: `diff` of every `*/migrations/0*.py` between the v0.5.12 and v0.6.0 trees is **empty**. `db.sqlite3` lives on
  `pvc/tube-archivist-cache-2g` (`DB_PATH = CACHE_DIR/db.sqlite3`).
- ES: `appsettings/index_mapping.json` is byte-identical between the tags; `ta_startup` `_index_setup` validates the
  same mappings. Index state 2026-10-26: `ta_video 1669`, `ta_channel 33`, `ta_playlist 6`, all green.
- ES compatibility: both v0.5.12 and v0.6.0 have `MIN_MAJOR, MAX_MAJOR = 8, 9` in `ta_connection.py`, so neither app
  version is blocked by either ES version — but this plan runs after the ES plan by design (§6).

### 1.6 Other consumers checked

- **Jellyfin TubeArchivistMetadata plugin** builds image URLs from API-returned paths (`_taApi.BuildImageUrl(channel.ThumbUrl)`,
  `tubearchivist-jf-plugin` `Providers/*.cs`), i.e. "the URLs returned by the API" the migration guide asks for, and its
  configured base URL is the public host (in `ALLOWED_HOSTS`). Compatible.
- **nfo-sync** (`cronjob/tube-archivist-nfo-sync`, hourly :00) reads ES directly (`ta_video/_search`); ES and its
  mapping are unchanged by this plan.
- **HTTPRoute** `tube-archivist` → Service :8000 with the public Host → allowed. Port stays 8000 (`TA_PORT` default).
- **library-tools** only mentions the TA folder in a comment ("Not audited here").

## 2. Pre-checks

Run from the repo root on the Mac mini (zsh). **Shell state does not persist between Bash calls**: state lives in
`/tmp/ta-060/env.sh` (mode 600, no secret in it); every later block starts with `source /tmp/ta-060/env.sh` and uses
`need VAR` (fails closed, `ENV_MISSING_STOP`) before relying on a variable.

```bash
cd /Users/mu/code/cberg-home-nextgen
umask 077; mkdir -p /tmp/ta-060
cat > /tmp/ta-060/env.sh <<'ENVEOF'
ta_pod() { kubectl get pods -n download -l app.kubernetes.io/name=tube-archivist --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}'; }
tapersist() { echo "export $1=$2" >> /tmp/ta-060/env.sh; export "$1=$2"; }   # values: no spaces, no secrets
need() { for v in "$@"; do eval "val=\${$v:-}"; test -n "$val" || { echo "ENV_MISSING_STOP: $v"; return 1; }; done; }
ENVEOF
source /tmp/ta-060/env.sh; test -n "$(ta_pod)" && echo "ta_pod=$(ta_pod)"        # EXPECT the live pod name

# 2.1 premises (must print PASS, no REFUSED), then the ORDERING GATE: the ES plan must already have landed on an earlier night.
.venv/bin/python3 runbooks/plan-premises.py tube-archivist-0.6.0 --require-premises
kubectl get deploy tube-archivist-elasticsearch -n download -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
#   PASS only if it prints bbilly1/tubearchivist-es:9.5.5. "8.19.0" = the ES plan has not run: STOP (this is the check that
#   enforces depends_on at execution time; the premise above accepts both majors). Also confirm that plan's 4.2-4.4 passed.

# 2.2 upstream still says stable, digest unchanged since planning (network checks live here, not in premises)
curl -s https://api.github.com/repos/tubearchivist/tubearchivist/releases/tags/v0.6.0 \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['tag_name'], 'prerelease=', r['prerelease'], 'draft=', r['draft'])"
#   PASS: "v0.6.0 prerelease= False draft= False"
curl -s 'https://hub.docker.com/v2/repositories/bbilly1/tubearchivist/tags/v0.6.0' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['digest'])"
#   PASS: sha256:0cbc18aa953c72ec7dfdd6f8fa7c2fe89b5d04489857d7baa354fecbd6181e69
#   A different digest = upstream re-pushed the tag: STOP, re-read release notes, re-review.

# 2.3 no newer patch superseding the target (if v0.6.1 exists, retarget — see plans/README "When the held target MOVES")
curl -s 'https://api.github.com/repos/tubearchivist/tubearchivist/releases?per_page=3' \
  | python3 -c "import sys,json; print([r['tag_name'] for r in json.load(sys.stdin)])"

# 2.4 backups fresh (belt-and-braces; rollback is git revert)
kubectl get volume tube-archivist-cache-2g -n storage -o 'custom-columns=N:.metadata.name,LAST_BACKUP:.status.lastBackupAt,ROBUST:.status.robustness'
#   PASS: LAST_BACKUP within 26 h, ROBUST healthy. (Volume CR, PV and PVC all named tube-archivist-cache-2g.)
kubectl exec -n download deploy/tube-archivist-elasticsearch -c app -- sh -c \
  'curl -s -u "elastic:$ELASTIC_PASSWORD" "localhost:9200/_snapshot/ta_snapshot/_all?filter_path=snapshots.end_time" | tail -c 120'
#   PASS: newest end_time within 26 h (SLM ta_daily, cron 10:00 UTC).

# 2.5 baselines for §4 (taken on the night: the ES plan has changed the numbers since 2026-10-26)
kubectl exec -n download deploy/tube-archivist-elasticsearch -c app -- sh -c \
  'curl -s -u "elastic:$ELASTIC_PASSWORD" "localhost:9200/_cat/indices/ta_*?h=index,docs.count,health&s=index"' | tee /tmp/ta-060/baseline-indices.txt
#   record (2026-10-26: ta_channel 33, ta_playlist 6, ta_video 1669, all green); the file is the baseline §4.3 compares to
test -s /tmp/ta-060/baseline-indices.txt && echo BASELINE_FILE_OK || echo BASELINE_EMPTY_STOP
J=$(kubectl get jobs -n download -o name --sort-by=.metadata.creationTimestamp | grep image-sync | tail -1); kubectl logs -n download "$J" | tail -1
#   record (2026-10-26: "Done. copied=0  skipped(existing)=81  source-missing/404=0")

# 2.6 not mid-download: a Recreate kills a running download (it re-queues). yt-dlp keeps in-progress files in /cache/download:
kubectl exec -n download deploy/tube-archivist -c app -- sh -c 'find /cache/download -type f -mmin -10 | wc -l'    # EXPECT 0 (>0 = wait)

# 2.7 conflicts: the scheduler is the control, this is a supporting read. CONTROL: the filter must print THIS plan's own
#     line; if it prints nothing the grep is blind and the check means nothing.
.venv/bin/python3 runbooks/maintenance-plan.py --open | grep -i -e tube-archivist -e redis-fleet -e media-naming -e flux-reconciler -e helm-drift -e flux-oci -e envoy-proxy
#   PASS: this plan's line is present AND no conflicts_with plan shares its slot.

# 2.8 Prometheus is the §4 instrument and kube-prometheus-stack PR #428 (92.11.1 -> 92.13.1) is OPEN, parked by the 48 h age
#     gate; Step 0 of tonight's window may apply it right before §4.
gh pr view 428 --json state,title -q '.state + " " + .title'
kubectl get hr -n monitoring kube-prometheus-stack -o jsonpath='{.spec.chart.spec.version}{"\n"}'
#   If Step 0 applied it, Prometheus restarted: §4.5 waits for it to settle (it fails closed on a young Prometheus) or the plan moves.
```

## 3. Steps

GitOps only. The patch scripts below were dry-run on scratch copies of the three files on macOS 2026-10-26 (anchors
matched exactly once each; a second run aborts; the patched YAML parses and the patched `sync_images.py` parses as
Python). The patched script and the gate driver were additionally run end to end against a local stub server for three cases
(correct server, Host header removed, old-server HTML) and printed `copied=3 skipped=0 source-missing/404=3 errors=0` /
`errors=6` as designed. Each script ABORTS without writing if an anchor does not match exactly once.

### 3.1 Write the patch scripts and the gate driver (scratch dir, outside the repo)

```bash
source /tmp/ta-060/env.sh; cd /tmp/ta-060
cat > patch_probes.py <<'EOF'
import pathlib, sys
p = pathlib.Path("kubernetes/apps/download/tube-archivist/app/helmrelease.yaml")
s = p.read_text()
edits = [
    ('                        urllib.request.urlopen("http://127.0.0.1:8000/", timeout=5).read(1)\n',
     '                        # v0.6.0 serves / from Django: Host must be in ALLOWED_HOSTS (localhost is)\n'
     '                        req = urllib.request.Request("http://127.0.0.1:8000/api/health/", headers={"Host": "localhost"})\n'
     '                        urllib.request.urlopen(req, timeout=5).read(1)\n'),
    ('                  httpGet:\n                    path: /\n                    port: 8000\n                  initialDelaySeconds: 60\n                  periodSeconds: 10\n',
     '                  httpGet:\n                    path: /api/health/\n                    port: 8000\n                    httpHeaders:\n                      - name: Host\n                        value: localhost\n                  initialDelaySeconds: 60\n                  periodSeconds: 10\n'),
    ('                  httpGet:\n                    path: /\n                    port: 8000\n                  failureThreshold: 30\n',
     '                  httpGet:\n                    path: /api/health/\n                    port: 8000\n                    httpHeaders:\n                      - name: Host\n                        value: localhost\n                  failureThreshold: 30\n'),
]
for old, new in edits:
    n = s.count(old)
    if n != 1:
        sys.exit(f"ABORT: anchor matched {n}x (expected 1): {old[:60]!r}")
    s = s.replace(old, new)
p.write_text(s)
print("probes patched")
EOF
cat > patch_bump.py <<'EOF'
import pathlib, sys
def sub(path, old, new):
    p = pathlib.Path(path); s = p.read_text(); n = s.count(old)
    if n != 1:
        sys.exit(f"ABORT {path}: anchor matched {n}x: {old[:60]!r}")
    p.write_text(s.replace(old, new))
base = "kubernetes/apps/download/tube-archivist/app/"
hr, cm = base + "helmrelease.yaml", base + "image-sync-configmap.yaml"
sub(hr, "              tag: v0.5.12\n", "              tag: v0.6.0\n")
sub(cm, '    MAPPING = {\n        "_thumb.jpg":  "folder.jpg",\n        "_tvart.jpg":  "backdrop.jpg",\n        "_banner.jpg": "banner.jpg",\n    }\n',
        '    # v0.6.0: artwork is served by Django at /media/thumb/channel/<id>/<art>.jpg\n'
        '    # (nginx and its /cache/ alias are gone; /cache/... now returns the SPA index.html with HTTP 200)\n'
        '    MAPPING = {\n        "thumb":  "folder.jpg",\n        "tvart":  "backdrop.jpg",\n        "banner": "banner.jpg",\n    }\n')
sub(cm, '            with urllib.request.urlopen(url, timeout=30) as r:\n                if r.status != 200:\n                    return False\n',
        '            # Host must be in TA ALLOWED_HOSTS (localhost is; the Service name is not -> HTTP 400)\n'
        '            req = urllib.request.Request(url, headers={"Host": "localhost"})\n'
        '            with urllib.request.urlopen(req, timeout=30) as r:\n                if r.status != 200:\n                    return False\n'
        '                ctype = r.headers.get("Content-Type", "")\n'
        '                if not ctype.lower().startswith("image/"):\n'
        '                    print(f"  NOT-AN-IMAGE ({ctype}) {url}")\n'
        '                    ERRORS.append(url)\n'
        '                    return False\n')
sub(cm, '            if e.code != 404:\n                print(f"  HTTP {e.code} fetching {url}")\n',
        '            if e.code != 404:\n                print(f"  HTTP {e.code} fetching {url}")\n                ERRORS.append(url)\n')
sub(cm, '            print(f"  ERR {url}: {e}")\n', '            print(f"  ERR {url}: {e}")\n            ERRORS.append(url)\n')
sub(cm, '    YOUTUBE_ROOT = os.environ.get("YOUTUBE_ROOT", "/youtube")\n',
        '    YOUTUBE_ROOT = os.environ.get("YOUTUBE_ROOT", "/youtube")\n    ERRORS = []\n')
sub(cm, '            for src_suffix, dst_name in MAPPING.items():\n', '            for art_type, dst_name in MAPPING.items():\n')
sub(cm, '                src_url = f"{TA_URL}/cache/channels/{entry}{src_suffix}"\n',
        '                src_url = f"{TA_URL}/media/thumb/channel/{entry}/{art_type}.jpg"\n')
sub(cm, '        print(f"Done. copied={copied}  skipped(existing)={skipped}  source-missing/404={missing_src}")\n',
        '        print(f"Done. copied={copied}  skipped(existing)={skipped}  source-missing/404={missing_src}  errors={len(ERRORS)}")\n'
        '        if ERRORS:\n            sys.exit(1)  # fail loud: a Host/route regression must fail the Job, not read as 404\n')
print("bump + image-sync patched")
EOF
cat > gate_driver.py <<'EOF'
"""ta image-sync real-script gate. argv: MODE (real|nohost) EXPECT (pass|fail). No credentials are involved.
Env overrides (defaults are the in-pod paths): GATE_DIR GATE_CACHE GATE_YT GATE_TA_URL."""
import os, re, shutil, subprocess, sys
mode, expect = sys.argv[1], sys.argv[2]
gd = os.environ.get("GATE_DIR", "/tmp/ta-sync-gate")
cache = os.environ.get("GATE_CACHE", "/cache/channels")
yt = os.environ.get("GATE_YT", "/youtube")
ta_url = os.environ.get("GATE_TA_URL", "http://tube-archivist:8000")
src = open(f"{gd}/sync_images.py").read()
if mode == "nohost":
    old = 'headers={"Host": "localhost"}'
    if src.count(old) != 1:
        sys.exit("GATE_SETUP_FAIL: Host anchor not found exactly once")
    src = src.replace(old, "headers={}")
open(f"{gd}/run.py", "w").write(src)
arts = ("thumb", "tvart", "banner")
def has_art(i): return all(os.path.exists(f"{cache}/{i}_{a}.jpg") for a in arts)
real = next((d for d in sorted(os.listdir(yt)) if d.startswith("UC") and os.path.isdir(f"{yt}/{d}") and has_art(d)), None)
if not real:
    sys.exit("GATE_SETUP_FAIL: no channel folder with all three cached artwork files")
bad = "UC" + "A" * 22                       # well-formed (UC + 22), not a channel -> 404
root = f"{gd}/root"
shutil.rmtree(root, ignore_errors=True)
os.makedirs(f"{root}/{real}"); os.makedirs(f"{root}/{bad}")
env = dict(os.environ, TA_URL=ta_url, YOUTUBE_ROOT=root)
r = subprocess.run([sys.executable, f"{gd}/run.py"], env=env, capture_output=True, text=True)
out = (r.stdout + r.stderr).replace(real, "<real>")
print("\n".join(out.strip().splitlines()[-8:]))
m = re.search(r"copied=(\d+)\s+skipped\(existing\)=(\d+)\s+source-missing/404=(\d+)\s+errors=(\d+)", out)
copied, skipped, missing, errors = (int(x) for x in m.groups()) if m else (-1, -1, -1, -1)
dst = {"thumb": "folder.jpg", "tvart": "backdrop.jpg", "banner": "banner.jpg"}
files_ok = True
for a, name in dst.items():
    p = f"{root}/{real}/{name}"
    if not os.path.isfile(p): files_ok = False; continue
    b = open(p, "rb").read()
    if b[:2] != b"\xff\xd8" or b != open(f"{cache}/{real}_{a}.jpg", "rb").read(): files_ok = False
bad_empty = os.listdir(f"{root}/{bad}") == []
print(f"mode={mode} rc={r.returncode} copied={copied} missing404={missing} errors={errors} real_files_identical_jpeg={files_ok} invalid_id_empty={bad_empty}")
passed = r.returncode == 0 and copied == 3 and missing == 3 and errors == 0 and files_ok and bad_empty
if expect == "pass":
    print("GATE_PASS" if passed else "GATE_FAIL")
    sys.exit(0 if passed else 1)
failed_loud = r.returncode != 0 and errors > 0 and copied == 0
print("CONTROL_FAILED_AS_EXPECTED" if failed_loud else "CONTROL_DID_NOT_FAIL_GATE_IS_BLIND")
sys.exit(0 if failed_loud else 1)
EOF
python3 -c "import ast;[ast.parse(open(f).read()) for f in ('patch_probes.py','patch_bump.py','gate_driver.py')];print('scripts parse OK')"
```

### 3.2 Commit A — probes only, still v0.5.12

Skip if premise `probes-not-yet-fixed-or-fixed` read `/api/health/`.

```bash
source /tmp/ta-060/env.sh; cd /Users/mu/code/cberg-home-nextgen
python3 /tmp/ta-060/patch_probes.py          # prints "probes patched"
git diff --stat -- kubernetes/apps/download/tube-archivist/app/helmrelease.yaml   # expect: 1 file, 11 insertions(+), 3 deletions(-)
```

Expected diff (from the dry run):

```diff
-                        urllib.request.urlopen("http://127.0.0.1:8000/", timeout=5).read(1)
+                        # v0.6.0 serves / from Django: Host must be in ALLOWED_HOSTS (localhost is)
+                        req = urllib.request.Request("http://127.0.0.1:8000/api/health/", headers={"Host": "localhost"})
+                        urllib.request.urlopen(req, timeout=5).read(1)
@@ readiness / startup (both)
-                    path: /
+                    path: /api/health/
                     port: 8000
+                    httpHeaders:
+                      - name: Host
+                        value: localhost
```

```bash
source /tmp/ta-060/env.sh; cd /Users/mu/code/cberg-home-nextgen
cat > /tmp/ta-060/msgA.txt <<'EOF'
fix(tube-archivist): probe /api/health/ with Host localhost (prep for v0.6.0)

v0.6.0 drops the bundled nginx; Django then answers "/" and rejects the
kubelet/127.0.0.1 Host headers with 400 (ALLOWED_HOSTS). /api/health/ is
the no-auth health view in both v0.5.12 and v0.6.0. Plan tube-archivist-0.6.0.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
tapersist OLD_TA_A "$(ta_pod)"; tapersist COMMIT_A_AT "$(date -u +%Y-%m-%dT%H:%M:%SZ)"     # recorded BEFORE the push
git commit --only kubernetes/apps/download/tube-archivist/app/helmrelease.yaml -F /tmp/ta-060/msgA.txt
git log -1 --format=%s          # MUST be the subject above; amend before push if not (shared worktree)
git show --stat HEAD            # exactly 1 file
git push
```

Wait for Flux (webhook; no manual reconcile), then gate on v0.5.12 BEFORE the bump. `rollout status` can green-light the
OLD generation, so the gate is a scripted comparison: a pod other than `OLD_TA_A`, created AFTER the push, whose Deployment
spec carries the new probe path, Ready with 0 restarts:

```bash
source /tmp/ta-060/env.sh; need OLD_TA_A COMMIT_A_AT || exit 1
for n in $(seq 1 60); do
  path=$(kubectl get deploy tube-archivist -n download -o jsonpath='{.spec.template.spec.containers[0].startupProbe.httpGet.path}')
  new=$(kubectl get pods -n download -l app.kubernetes.io/name=tube-archivist -o json | OLD=$OLD_TA_A AT=$COMMIT_A_AT python3 -c '
import json,os,sys
for p in json.load(sys.stdin)["items"]:
    if p["metadata"]["name"]==os.environ["OLD"] or p["metadata"].get("deletionTimestamp") or p["metadata"]["creationTimestamp"]<=os.environ["AT"]: continue
    cs=[c for c in p.get("status",{}).get("containerStatuses",[]) if c["name"]=="app"]
    if cs and cs[0].get("ready") and cs[0].get("restartCount")==0: print(p["metadata"]["name"]); sys.exit(0)')
  echo "$n probe_path=$path new_ready_pod=${new:-none}"
  if [ "$path" = "/api/health/" ] && [ -n "$new" ]; then break; fi; sleep 10; done
if [ "$path" = "/api/health/" ] && [ -n "$new" ]; then echo COMMIT_A_NEW_GENERATION_OK; else echo COMMIT_A_GATE_FAIL_REVERT; fi
kubectl get deploy tube-archivist -n download -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'     # PASS: bbilly1/tubearchivist:v0.5.12
#   How it fails: before Flux rolls, the probe path is still "/" and the only pod is OLD_TA_A (or created before the push) -> the loop
#   runs out and prints COMMIT_A_GATE_FAIL_REVERT. A not-ready or restarting new pod never matches. FAIL → git revert HEAD, push, stop
#   (probe syntax problem, not the bump).
```

### 3.3 Commit B — tag + image-sync together (with a pre-roll control on v0.5.12)

```bash
source /tmp/ta-060/env.sh; cd /Users/mu/code/cberg-home-nextgen
python3 /tmp/ta-060/patch_bump.py            # prints "bump + image-sync patched"
python3 -c "import yaml,ast; d=yaml.safe_load(open('kubernetes/apps/download/tube-archivist/app/image-sync-configmap.yaml')); ast.parse(d['data']['sync_images.py']); print('configmap+script parse OK')"
git diff --stat -- kubernetes/apps/download/tube-archivist/app/
#   expect: helmrelease.yaml 1 +/- (tag), image-sync-configmap.yaml ~21 insertions, 7 deletions (the CronJob is NOT edited)
```

Key diff lines (full diff matches §1.4):

```diff
-              tag: v0.5.12
+              tag: v0.6.0
-                src_url = f"{TA_URL}/cache/channels/{entry}{src_suffix}"
+                src_url = f"{TA_URL}/media/thumb/channel/{entry}/{art_type}.jpg"
+            req = urllib.request.Request(url, headers={"Host": "localhost"})
+                if not ctype.lower().startswith("image/"):
```

**Pre-roll control (the gate must be able to FAIL).** Before committing, run the patched script from the working tree
against the still-running v0.5.12 server: there the new route is not an image, so the gate must report failure
(`NOT-AN-IMAGE`, `errors=6`; a replay against v0.5.12 printed exactly this). The gate procedure is §4.5; here it runs
with the working-tree script and `expect fail`:

```bash
source /tmp/ta-060/env.sh; cd /Users/mu/code/cberg-home-nextgen
python3 -c "import yaml;open('/tmp/ta-060/sync_images.worktree.py','w').write(yaml.safe_load(open('kubernetes/apps/download/tube-archivist/app/image-sync-configmap.yaml'))['data']['sync_images.py'])"
kubectl exec -i -n download deploy/tube-archivist -c app -- sh -c 'mkdir -p /tmp/ta-sync-gate && cat > /tmp/ta-sync-gate/gate_driver.py' < /tmp/ta-060/gate_driver.py
kubectl exec -i -n download deploy/tube-archivist -c app -- sh -c 'cat > /tmp/ta-sync-gate/sync_images.py' < /tmp/ta-060/sync_images.worktree.py
kubectl exec -n download deploy/tube-archivist -c app -- python /tmp/ta-sync-gate/gate_driver.py real fail
#   EXPECT the last line CONTROL_FAILED_AS_EXPECTED (errors=6, copied=0). CONTROL_DID_NOT_FAIL_GATE_IS_BLIND = the gate cannot
#   tell v0.5.12 from v0.6.0: STOP, do not commit B. (Channel ids are masked in the output; the real one is never printed.)
kubectl exec -n download deploy/tube-archivist -c app -- rm -rf /tmp/ta-sync-gate      # exact path, inside the pod only
```

```bash
source /tmp/ta-060/env.sh; cd /Users/mu/code/cberg-home-nextgen
tapersist OLD_TA "$(ta_pod)"; tapersist COMMIT_B_AT "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > /tmp/ta-060/msgB.txt <<'EOF'
feat(tube-archivist): v0.5.12 -> v0.6.0, move image-sync to the /media/thumb route

v0.6.0 removes nginx; /cache/channels/... now falls through to the SPA
index (200 text/html). image-sync fetches /media/thumb/channel/<id>/<art>.jpg
with Host localhost, refuses non-image bodies, and fails the Job on any
non-404 error. Renovate closes #432 itself once main carries v0.6.0.
Plan tube-archivist-0.6.0.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
git commit --only kubernetes/apps/download/tube-archivist/app/helmrelease.yaml \
  kubernetes/apps/download/tube-archivist/app/image-sync-configmap.yaml -F /tmp/ta-060/msgB.txt
git log -1 --format=%s ; git show --stat HEAD     # subject is ours; exactly these 2 files
git push
```

### 3.4 Watch the roll — new generation only, positive log lines

`rollout status` and `logs --tail` can both describe the OLD generation, so the gate accepts only a pod that is not
`OLD_TA`, is newer than the push, and whose `imageID` ends with the v0.6.0 digest:

```bash
source /tmp/ta-060/env.sh; need OLD_TA COMMIT_B_AT || exit 1
D=sha256:0cbc18aa953c72ec7dfdd6f8fa7c2fe89b5d04489857d7baa354fecbd6181e69
for n in $(seq 1 90); do
  new=$(kubectl get pods -n download -l app.kubernetes.io/name=tube-archivist -o json | OLD_TA=$OLD_TA D=$D AT=$COMMIT_B_AT python3 -c '
import json,os,sys
for p in json.load(sys.stdin)["items"]:
    if p["metadata"]["name"]==os.environ["OLD_TA"] or p["metadata"].get("deletionTimestamp") or p["metadata"]["creationTimestamp"]<=os.environ["AT"]: continue
    for c in p.get("status",{}).get("containerStatuses",[]):
        if c["name"]=="app" and c.get("imageID","").endswith(os.environ["D"]): print(p["metadata"]["name"]); sys.exit(0)')
  echo "$n new_pod=${new:-none}"; [ -n "$new" ] && break; sleep 10; done
if [ -n "$new" ]; then tapersist TA "$new"; echo NEW_GENERATION_FOUND; else echo NEW_GENERATION_NOT_FOUND_GO_TO_5; fi
kubectl wait -n download pod/$TA --for=condition=Ready --timeout=10m && tapersist ROLL_READY_AT "$(date +%s)"
kubectl logs -n download $TA -c app | grep -ciE 'es version check passed'           # EXPECT >= 1 (the positive startup line)
kubectl logs -n download $TA -c app | grep -ciE 'CommandError|🗙'                    # EXPECT 0
```

The positive line is the gate (an empty log, or a log that only shows the old pod, prints 0 and fails). A `🗙`/`CommandError`
line = startup refused → §5 Case 1 (upstream: no state changed at that point).

### 3.5 Let the next scheduled jobs run

image-sync runs at :30, nfo-sync at :00. §4.5 reads the first post-change image-sync run **in addition to** the
real-script gate (which does not wait for :30). **Expected noise:** if a newly subscribed channel exists at the :30 that
falls between the Flux apply of commit B and the v0.6.0 pod becoming Ready, that one image-sync Job can fail (the new
script against a restarting server counts the connection error). One failed Job in that gap is expected and is not a
gate failure; a failure after `ROLL_READY_AT` is.

### 3.6 Renovate PR #432: do NOT close or merge it by hand

Renovate auto-closes #432 once `main` carries v0.6.0 (the ES plan's #433 behaves the same way). A manually closed
Renovate PR is IGNORED for that version, so closing it by hand would also hide the update from Renovate. Check on the
next sweep: `gh pr view 432 --json state -q .state` should read `CLOSED` by Renovate's next run; if it is still OPEN
after that, leave it for the sweep. The deny rule (§1.1) is untouched either way.

## 4. Verification

Instruments: kube-state-metrics via Prometheus (`kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!`; `kill $PF` at the end), the ES API, the app itself.

**Gates vs supporting reads.** The gating checks (they have a defined failure) are §4.1 (imageID + ready + restarts=0),
§4.2 (positive + negative controls), §4.3 (counts vs baseline), §4.5 (the real-script gate plus its two controls) and the
restart-counter metric. The alert controls below are ABSENCE checks with no known-bad baseline on this cluster; they are
supporting reads and never the only evidence. Their known-bad behaviour is the §1.3 failure measured in §4.2.

CONTROL (supporting): alertname TubeArchivistPodNotReady — must NOT be firing 10 min after the roll (it is exactly what the bare tag bump would fire, §1.3).
CONTROL (supporting): alertname TubeArchivistPodCrashLooping — must NOT be firing.
CONTROL (supporting): alertname TubeArchivistPodRestarted — must NOT be firing 15 min after the roll (the probe-400 failure restarts the container at ~5 min, so this goes pending inside the window if the fix is wrong).
CONTROL: metric kube_pod_container_status_restarts_total — `increase(kube_pod_container_status_restarts_total{namespace="download",pod=~"tube-archivist-[a-z0-9]+-[a-z0-9]+"}[15m])` = 0 for the new pod; the series must be NON-EMPTY (an empty result means the selector or scrape is wrong, not success).
CONTROL: metric kube_pod_status_ready — `kube_pod_status_ready{namespace="download",pod=~"tube-archivist-[a-z0-9]+-[a-z0-9]+",condition="true"}` = 1 (non-empty).

**Prometheus must have settled.** If Step 0 applied the kube-prometheus-stack bump (PR #428) tonight, Prometheus
restarted and an `increase()` over a window it has not covered reads 0. Before reading any metric:

```bash
source /tmp/ta-060/env.sh
PST=$(kubectl get pod -n monitoring prometheus-kube-prometheus-stack-0 -o jsonpath='{.status.startTime}')
python3 -c "
from datetime import datetime,timezone,timedelta
t=datetime.strptime('$PST','%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc); age=datetime.now(timezone.utc)-t
print('prometheus up',age); import sys; sys.exit(0 if age>timedelta(minutes=20) else 'PROMETHEUS_TOO_YOUNG_WAIT_OR_MOVE')"
```

### 4.1 Running the right image (scripted wait, then read)

```bash
source /tmp/ta-060/env.sh; need TA ROLL_READY_AT || exit 1
while [ $(( $(date +%s) - ROLL_READY_AT )) -lt 600 ]; do sleep 30; done; echo "10 min observation elapsed"
kubectl get pod -n download $TA -o json | python3 -c '
import json,sys
p=json.load(sys.stdin); c=[x for x in p["status"]["containerStatuses"] if x["name"]=="app"][0]
d="sha256:0cbc18aa953c72ec7dfdd6f8fa7c2fe89b5d04489857d7baa354fecbd6181e69"
print(c["imageID"][-20:], "ready=",c["ready"], "restarts=",c["restartCount"])
sys.exit(0 if c["imageID"].endswith(d) and c["ready"] and c["restartCount"]==0 else "IMAGE_READY_RESTARTS_FAIL")'
```
PASS: imageID ends `@sha256:0cbc18aa953c72ec7dfdd6f8fa7c2fe89b5d04489857d7baa354fecbd6181e69`, `ready=True restarts=0` after the
enforced 10 minutes (foreground waits may be blocked by the harness: run the loop under `Monitor` with the same condition). FAIL looks like:
`ready=false` with events `Startup probe failed: HTTP probe failed with statuscode: 400`
(`kubectl get events -n download --field-selector involvedObject.kind=Pod | grep -i probe`) — that is the §1.3 failure; a wrong image or any
restart exits non-zero. The 15-minute alert/restart reads below wait until `ROLL_READY_AT + 900 s` the same way.

### 4.2 Probes actually pass on v0.6.0 (and the gate can fail)

```bash
kubectl exec -n download deploy/tube-archivist -c app -- python -c "
import urllib.request as u, urllib.error as e
for h in ['localhost','127.0.0.1:8000']:
    try: r=u.urlopen(u.Request('http://127.0.0.1:8000/api/health/',headers={'Host':h}),timeout=10); print(h, r.status, r.read(10))
    except e.HTTPError as x: print(h, 'HTTP', x.code)
"
```
PASS: `localhost 200 b'"OK"'` AND `127.0.0.1:8000 HTTP 400`. The second line is the negative control: it proves the
Host header is what makes the probe pass (if it also read 200, Host validation changed and §1.3's premise is wrong —
fine for the app, but re-check the image-sync reasoning).

### 4.3 CONTENTS — the index survived startup

CONTENTS ASSERTION: ES document counts per `ta_*` index are >= the §2.5 baseline file `/tmp/ta-060/baseline-indices.txt`:
```bash
source /tmp/ta-060/env.sh
kubectl exec -n download deploy/tube-archivist-elasticsearch -c app -- sh -c \
  'curl -s -u "elastic:$ELASTIC_PASSWORD" "localhost:9200/_cat/indices/ta_*?h=index,docs.count,health&s=index"' > /tmp/ta-060/after-indices.txt
python3 - <<'EOF'
import sys
def rd(f): return {l.split()[0]:(int(l.split()[1]),l.split()[2]) for l in open(f) if len(l.split())>=3}
b=rd("/tmp/ta-060/baseline-indices.txt"); a=rd("/tmp/ta-060/after-indices.txt")
bad=[]
if not b: sys.exit("BASELINE_EMPTY_FAIL")
for k,(n,_) in b.items():
    an,h=a.get(k,(0,"missing"))
    print(k,"before",n,"after",an,h)
    if an<n or an==0 or h not in("green","yellow"): bad.append(k)
sys.exit("COUNTS_FAIL: "+",".join(bad) if bad else 0)
EOF
```
PASS: no `COUNTS_FAIL`; `ta_video`, `ta_channel`, `ta_playlist` present and >= baseline (a new download may add). FAIL: any count lower,
a missing index, or an empty baseline (a re-created empty index is also green — that is why the count is the gate).

### 4.4 Supporting read — the new route and the old route on the new server

Supporting evidence only; the gate is §4.5. A channel id is picked at runtime and never printed.

```bash
kubectl exec -n download deploy/tube-archivist -c app -- python -c "
import os, urllib.request as u, urllib.error as e
f=sorted(x for x in os.listdir('/cache/channels') if x.endswith('_thumb.jpg'))[0]; cid=f[:-len('_thumb.jpg')]
disk=open('/cache/channels/'+f,'rb').read()
def get(path, host):
    try:
        r=u.urlopen(u.Request('http://tube-archivist:8000'+path,headers={'Host':host}),timeout=15); b=r.read()
        return r.status, r.headers.get('Content-Type'), b
    except e.HTTPError as x: return x.code, None, b''
s,ct,b=get('/media/thumb/channel/%s/thumb.jpg'%cid,'localhost'); print('NEW', s, ct, 'jpeg_magic', b[:2]==b'\xff\xd8', 'identical', b==disk, len(b))
s,ct,b=get('/cache/channels/%s'%f,'localhost');                  print('OLD', s, ct)
s,ct,b=get('/media/thumb/channel/%s/thumb.jpg'%cid,'tube-archivist:8000'); print('SVCHOST', s)
"
```
Expected: `NEW 200 image/jpeg jpeg_magic True identical True <n>`, `OLD 200 text/html…` (the old script WOULD have written HTML), `SVCHOST 400`.
The OLD line comes from reading the code; if it reads 404 instead, that is better, not a failure.

### 4.5 GATE — the shipped image-sync script, run for real

The previous version of this gate was vacuous: every channel folder already has all three artwork files (27 channels,
0 missing; last Job `copied=0 skipped=81`), so the patched script makes no request and "errors=0, skipped >= 81" is green even
when broken. This gate runs the **script the cluster actually ships** (read from the live ConfigMap, not the working
tree) against a SCRATCH `YOUTUBE_ROOT` under `/tmp` inside the app pod (nothing is written to the CIFS share) holding
one folder named after a real channel id (picked at runtime, never printed) and one well-formed but invalid id.

```bash
source /tmp/ta-060/env.sh
kubectl exec -i -n download deploy/tube-archivist -c app -- sh -c 'mkdir -p /tmp/ta-sync-gate && cat > /tmp/ta-sync-gate/gate_driver.py' < /tmp/ta-060/gate_driver.py
kubectl get cm tube-archivist-image-sync -n download -o jsonpath='{.data.sync_images\.py}' \
  | kubectl exec -i -n download deploy/tube-archivist -c app -- sh -c 'cat > /tmp/ta-sync-gate/sync_images.py'
kubectl exec -n download deploy/tube-archivist -c app -- grep -c 'media/thumb/channel/{entry}' /tmp/ta-sync-gate/sync_images.py   # EXPECT 1 (the shipped script is the patched one)
# the gate
kubectl exec -n download deploy/tube-archivist -c app -- python /tmp/ta-sync-gate/gate_driver.py real pass
#   PASS (last line GATE_PASS): rc=0 copied=3 missing404=3 errors=0, real_files_identical_jpeg=True (each of folder.jpg, backdrop.jpg,
#   banner.jpg starts with the JPEG magic bytes AND is byte-identical to the app's cached file), invalid_id_empty=True.
# control: Host header removed -> HTTP 400 x6, errors=6
kubectl exec -n download deploy/tube-archivist -c app -- python /tmp/ta-sync-gate/gate_driver.py nohost fail
#   must print CONTROL_FAILED_AS_EXPECTED; CONTROL_DID_NOT_FAIL_GATE_IS_BLIND = the gate cannot see the regression it guards against
#   -> treat the whole gate as FAILED. The pre-roll control in §3.3 (same driver, v0.5.12, errors=6 NOT-AN-IMAGE) shows the same
#   gate distinguishes the old server from the new one.
kubectl exec -n download deploy/tube-archivist -c app -- rm -rf /tmp/ta-sync-gate      # exact scratch path, inside the pod only
```

Then the scheduled job as a second, weaker read (it exercises the cluster path: ConfigMap -> CronJob):

```bash
source /tmp/ta-060/env.sh; need ROLL_READY_AT || exit 1
J=$(kubectl get jobs -n download -o name --sort-by=.metadata.creationTimestamp | grep image-sync | tail -1)
kubectl get -n download "$J" -o jsonpath='{.metadata.creationTimestamp} {.status.succeeded}{"\n"}'; kubectl logs -n download "$J" | tail -3
J2=$(kubectl get jobs -n download -o name --sort-by=.metadata.creationTimestamp | grep nfo-sync | tail -1); kubectl get -n download "$J2" -o jsonpath='{.metadata.creationTimestamp} {.status.succeeded}{"\n"}'
```
PASS: an image-sync Job created AFTER the roll, `succeeded=1`, last line `Done. copied=0 … skipped(existing)=81 … errors=0`. This read is
weak by itself (it makes no request), which is why §4.5's gate above is the gating evidence; a Job failing now (`HTTP 400`, `NOT-AN-IMAGE`)
is a real failure → §5 Case 1. nfo-sync: a post-roll Job with `succeeded=1`.
If the window must close before :30, the executor may trigger one run: `kubectl create job --from=cronjob/tube-archivist-image-sync ta-image-sync-verify-060 -n download` (delete it after).

### 4.6 Public path + Jellyfin plugin

```bash
H=$(kubectl get httproute tube-archivist -n download -o jsonpath='{.spec.hostnames[0]}')
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' "https://$H/api/health/"   # PASS: 200 application/json
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' "https://$H/"              # PASS: 200 text/html
```
Then in Chrome: log in to Tube Archivist, open a channel page — channel banner and video thumbnails render (they now
come from `/media/thumb/...`), and one video plays (now streamed by Django `RangedFileResponse`; seeking must work =
206 range responses). In Jellyfin, open the Tube Archivist library and "Refresh metadata" on one channel: the plugin
log (`Dashboard → Logs`) shows no TubeArchivist HTTP errors and artwork stays.
FAIL: broken images in TA UI = media URL change not handled → §5.

## 5. Rollback

Nothing forward-only happens (§1.5), so rollback is a revert — but revert in the RIGHT order.

**Case 1 — v0.6.0 refuses to start or §4 fails (most likely):** revert commit B only. The pod returns to v0.5.12
with the new probes (proved working on v0.5.12 in §3.2) and the old image-sync.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-commit-B>      # restores tag v0.5.12 AND the /cache/channels image-sync together
git log -1 --format=%s ; git show --stat HEAD   # 2 files, subject "Revert \"feat(tube-archivist): v0.5.12 -> v0.6.0 …\""
git push
kubectl rollout status deploy/tube-archivist -n download --timeout=10m
kubectl get pod -n download -l app.kubernetes.io/name=tube-archivist -o 'jsonpath={range .items[*]}{.spec.containers[0].image} ready={.status.containerStatuses[0].ready}{"\n"}{end}'
#   CONFIRMED BACK: "bbilly1/tubearchivist:v0.5.12 ready=true" on a pod started AFTER the revert push, §4.3 counts = baseline,
#   next image-sync "Done" line without "errors" and with "source-missing/404=0".
```

If any image-sync run during the failed attempt wrote files, find them: `kubectl exec -n download deploy/tube-archivist -c app -- sh -c 'find /youtube -maxdepth 2 \( -name folder.jpg -o -name backdrop.jpg -o -name banner.jpg \) -newermt "<commit-B push time>"'` — with the content-type guard none can be HTML; any listed file is a real JPEG from the new route. (Read-only listing; do NOT delete anything on the CIFS share without the storage-safety pre-flight.)

**Case 2 — the probe change itself misbehaves (only possible in §3.2):** `git revert <sha-of-commit-A>`, push, confirm
`startupProbe.httpGet.path` reads `/` and the pod is ready. Do not proceed to commit B.

**Case 3 — something corrupted state despite §1.5 (not expected):** the sqlite DB is on `tube-archivist-cache-2g` —
restore from its Longhorn backup taken by `storage/daily-backup-all-volumes` (§2.4) per `docs/sops/backup.md`; the ES
index from the newest `ta_snapshot` daily snapshot via TA Settings → Application → Snapshots → Restore. Both were
confirmed fresh in §2.4.

**Renovate after a rollback:** do not assume #432 re-opens. If Renovate auto-closed it when main carried v0.6.0, whether it
re-proposes v0.6.0 after the revert is not something this plan can promise; check `gh pr list --search "tubearchivist"` on the
next sweep. Whatever it opens, the deny rule (§1.1) holds a minor bump in the PLAN lane. Leave this plan `blocked` with the reason.

Clean up when done: `rm -rf /tmp/ta-060` (scratch scripts and env file; none holds a secret).

## 6. Interference notes

- **Order with the ES 9.5.5 plan (PR #433), and windows:** upstream says "update it together with Tube Archivist", but both app
  versions accept ES 8 and 9 (`MIN_MAJOR, MAX_MAJOR = 8, 9` in both tags), so "together" means the same upgrade cycle,
  not the same commit or night. **ES first, this plan on a LATER night, never the same window:** the ES plan's §4.4
  restarts this app, and this plan's two Recreate rolls would confound the ES plan's checks (both plans declare each other in
  `conflicts_with`; this one also `depends_on` the ES plan). Both are HUMAN-GATED. sat-attended budget is 70 min (90 - 20
  Step 0): the ES plan (65) needs a Saturday alone, this plan (60) likewise. **Recommended: ES on `sat-attended:2026-11-28`,
  this plan on `sat-attended:2026-12-05`** (after `redis-fleet-8.10.2` on 2026-11-29 has restarted this app, so its restart is not
  mixed into §4). Avoid the night after the Talos roll (`nightly:2026-11-02`) and any slot within 24 h of a Longhorn or Talos roll;
  2026-11-14 is also out (python-fleet 35 min + 60 > 70, and 23 h before the Longhorn roll). `window` stays null while `draft`.
  This plan's rollback stays a free git revert on ES 9: v0.5.12 also accepts ES 9, and §1.5 holds there too. The §4.3 baseline is
  taken on the night (§2.5), never copied from 2026-10-26.
- **Two Recreate rolls** of `deployment/tube-archivist` (commit A, commit B): UI/API down ~1–3 min each; a running
  download task is cut and re-queued (§2.6). Redis and ES pods are not restarted by this plan. The scratch gate in §4.5
  runs inside the app pod and is removed afterwards.
- **CIFS share (`cifs-tube-archivist-media`, severe tier):** remounted by each roll; this plan performs NO PVC/PV
  operation of any kind. The gate writes only under `/tmp` in the pod. Storage-safety rules from CLAUDE.md apply
  verbatim to anyone acting on this plan.
- **Prometheus is the §4 instrument:** `kube-prometheus-stack` PR #428 (92.11.1 -> 92.13.1) is OPEN, parked by the 48 h age gate,
  and Step 0 of the window can apply it right before §4. §4 refuses to read from a Prometheus younger than 20 minutes
  (`PROMETHEUS_TOO_YOUNG_WAIT_OR_MOVE`): wait for it to settle or move this plan. (92.11.1 landed as `d997b0fa`.)
- **redis-fleet-8.10.2** restarts `tube-archivist-redis` and this deployment (its leg 4 restarts `deployment/tube-archivist`);
  **flux-reconciler-impersonation** uses tube-archivist as its canary; **media-naming-p3** renames on the shared media
  surface; **helm-drift-detection** asserts identical Helm revisions; **flux-oci-chart-sources** re-points the chart sources;
  **envoy-proxy-config-distroless-v1.39.4** perturbs the public path §4.6 reads. All in `conflicts_with`; reciprocity in those
  plans is owed (this planner writes only this file; `--validate` does not check reciprocity).
- **A failed image-sync Job at :30 near the roll is expected** if a new channel exists (§3.5).
- The deny rule in `runbooks/auto-update-policy.yaml` is not touched by this plan (§1.1).
