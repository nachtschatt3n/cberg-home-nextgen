---
plan_id: penpot-chart-1.10.0
component: penpot
pr: null                              # no Renovate PR; routed to PLAN by the sweep (cycle 58d45ed0),
                                      # re-dispatched for the 1.11.1 retarget by cycle 481b9c1f
kind: chart
current: "chart 1.9.0 (app 2.17.2)"   # live 2026-10-05: HR penpot Ready "penpot@1.9.0" (helm rev 30),
                                      # all three Deployments on penpotapp/*:2.17.2, migrations 161
target: "chart 1.11.1 (app 2.18.1)"   # RETARGETED 2026-10-05 from "chart 1.10.0 (app 2.18.0)";
                                      # plan_id kept per plans/README "refresh in place". One hop
                                      # 1.9.0 -> 1.11.1 (no intermediate stop at 1.10.0, §1).
update_type: minor
risk: medium                          # forward DB migration (benign for 2.17.2, see §1) +
                                      # base-image switch ubuntu -> Docker Hardened Images on all
                                      # three images (2.18.0) + internet-facing app. Single-user
                                      # instance. The 1.10.0 -> 1.11.1 delta adds no risk (§1.B).
est_duration_min: 45
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/penpot                  # the one-line chart version edit
    - deployment/penpot-backend           # image 2.18.1, runs DB migration 0152 on start
    - deployment/penpot-frontend          # image 2.18.1, PENPOT_INTERNAL_RESOLVER env removed by chart
    - deployment/penpot-exporter          # image 2.18.1
    - statefulset/penpot-db               # NOT edited: pg_dump read in §3, schema migration by backend
    - pvc/penpot-db-data                  # NOT edited (Longhorn volume pvc-280be202-...)
    - pvc/penpot-assets                   # NOT edited: CIFS RWX, mounted by backend+frontend. NO deletes.
    - httproute/penpot                    # NOT edited: its backend Service `penpot` rolls
    - deployment/penpot-cache             # NOT edited: backend+exporter reconnect to it on roll
  shared: [gateway/envoy-external, cifs/penpot-assets, monitoring]
                                      # envoy-external: public route's backend rolls (brief 5xx);
                                      # cifs: the share is mounted by the new pods (read/write);
                                      # monitoring: §4 CONTROL lines read Prometheus.
depends_on: []
conflicts_with:
  - penpot-cache-9.2                  # both perturb backend/exporter <-> cache connections (§6)
  - kube-prometheus-stack-91.4.1      # §4 CONTROL metrics read through it
  - flux-reconciler-impersonation     # changes helm-controller's apply identity incl. office
  - flux-oci-chart-sources            # rewrites penpot spec.chart (mirror track)
  - helm-drift-detection              # adds spec.driftDetection to every HR incl. penpot
  - app-template-5.2.1                # helm-upgrades penpot-db + penpot-cache, which penpot dependsOn (committed 5eca9410, vetted)
  - paperless-db-13.0.2               # reciprocal (office namespace; that plan lists us) — review 2026-09-28
  - chart-patches-coredns-reloader-blackbox  # coredns roll; 1.10.0+ frontend nginx resolver = cluster DNS
  # ADDED 2026-10-05 (retarget): reciprocals — each of these already lists this plan; serialize.
  - coredns-1.48.1                    # same coredns-resolver reason as the chart-patches plan
  - envoy-proxy-config-distroless-v1.39.2  # rolls envoy-external proxies; its per-host diff + our public route
  - mariadb-28.1.1                    # lists us (reciprocity; one failing restore at a time)
  - nextcloud-fleet-35.0.1            # office-wide silence would hide this plan's failures
  - nocodb-2026.09.1                  # lists us (backup-restore set, same window family)
exclusive: false
security_ref: F-4c3c5206              # exporter image finding; 2.18.x answers it (see §1, measured)
capability_change: true               # 2.18.0 changes user-visible behaviour (new drawing tools,
                                      # comments in workspace, backend password-complexity enforcement);
                                      # 2.18.1 adds a frontend stub_status listener on :8082 (§1.B)
rollback_class: backup-restore        # migration 0152 is forward-only; primary rollback is still a
                                      # git revert (2.17.2 tolerates the migrated schema, §5 A), the
                                      # pg_dump restore (§5 B) is the floor if data is damaged.
backup_gate: "plain-SQL pg_dump of database penpot taken from pod penpot-db-0 (container app) to $HOME/penpot-backups/pre-2.18.1/penpot.sql BEFORE the chart edit is pushed, verified non-empty + contains '-- PostgreSQL database dump complete' + >= 50 'COPY public.' blocks, with the §2.4 baseline counts captured beside it; plus the nightly Longhorn backup of pvc-280be202-dcc0-4eb6-b959-58ab70711d78 (penpot-db-data) Completed < 26h"
finding_refs: [F-922ffce7, F-4c3c5206]
                                      # F-922ffce7: "penpot: chart 1.9.0 -> 1.11.1 (minor)" (title
                                      #   re-read 2026-10-05; the same record moved with the target) — this plan.
                                      # F-4c3c5206: exporter image finding — 2.18.x measured to answer it (§1.C).
                                      # NOT claimed: F-220e7d7b (backend) and F-9ac47520 (frontend) —
                                      #   re-rated by the sweep after landing; detail on the records.
status: draft        # RESET 2026-10-05 by the 1.11.1 retarget (was awaiting-go / review ready-for-go@2026-09-28
                     # for 1.10.0). A retarget voids the old review AND the old GO: needs a fresh
                     # plan-reviewer pass, then a NEW operator GO (HUMAN-GATED, capability_change: true).
review: null
window: "sat-attended:2026-10-31"   # KEPT on the 2026-10-05 retarget (flux-fleet-0.60.0 precedent); the slot only runs if the re-review passes and a new GO is recorded first (status is draft). Originally SCHEDULED 2026-09-28 by maintenance-window-agent (moved off sun 10-25: shares monitoring+office with redis-fleet)
premises:
  - id: live-backend-still-2.17.2
    why: "current: claims 2.17.2; if the backend already moved, the dump/baseline and rollback target are wrong."
    run: kubectl get deploy -n office penpot-backend -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: penpotapp/backend:2.17.2
  - id: manifest-pin-still-1.9.0
    why: "§3 sed anchors on the exact line `version: 1.9.0`; a changed pin makes it a silent no-op."
    run: grep -c 'version. 1[.]9[.]0$' /Users/mu/code/cberg-home-nextgen/kubernetes/apps/office/penpot/app/helmrelease.yaml
    expect_exact: "1"
  - id: postrenderer-target-rendered
    why: >-
      The postRenderers kustomize patch targets Deployment penpot-backend. 1.10.0 still renders
      that name (helm template diff, §1); this proves the patch is live today so §4.1 can compare.
    run: kubectl get deploy -n office penpot-backend -o jsonpath='{.spec.template.spec.initContainers[*].name}'
    expect_exact: wait-for-postgresql wait-for-redis
  - id: penpot-cache-hr-ready
    why: >-
      The cache must be settled before this plan rolls its clients (§4.7 counts reconnects).
      Version-agnostic on purpose, so it does not break once penpot-cache-9.2 lands.
    run: kubectl get helmrelease -n office penpot-cache -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: penpot-cache-on-fixed-pin
    why: >-
      The live cache image must be a fixed X.Y.Z pin (never the floating 9.2 / an rc). The
      runner cannot compare two commands, so equality with the tag in
      penpot-cache/app/helmrelease.yaml is asserted by hand in §2.2.
    run: kubectl get deploy -n office penpot-cache -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_matches: '^valkey/valkey:[0-9]+[.][0-9]+[.][0-9]+$'
  - id: penpot-hr-ready
    why: "Never start from a failed/pending release — a remediation rollback mid-window hides the upgrade result."
    run: kubectl get helmrelease -n office penpot -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md
generated: "2026-10-05"     # refreshed (retarget 1.10.0 -> 1.11.1, sweep cycle 481b9c1f); first written 2026-09-27
---

# penpot: chart 1.9.0 -> 1.11.1 (app 2.17.2 -> 2.18.1)

> **Retarget note (2026-10-05).** This plan was written and reviewed for chart
> 1.10.0 / app 2.18.0. coverage.py now holds 1.9.0 -> 1.11.1 ("G3 could not
> verify the release notes"). The 2.17.2 -> 2.18.0 analysis in §1.A is
> unchanged and still governs the risky part; §1.B is the new 1.10.0 -> 1.11.1
> delta, read from the chart tarballs and the upstream 2.18.0...2.18.1 compare.
> Verdict: take 1.11.1 directly — it is a bug-fix patch on top of 1.10.0 with
> no new migration, no values change, and a byte-identical render apart from
> image tags/labels. Stopping at 1.10.0 would buy nothing and leave a second
> bump owed.

## 1. Summary & why held

One-line chart bump in `kubernetes/apps/office/penpot/app/helmrelease.yaml`
(`spec.chart.spec.version`). The chart pins all three images, so this moves
`penpotapp/{backend,frontend,exporter}` 2.17.2 -> 2.18.1. Standalone
`penpot-db` (postgres 18.6 StatefulSet) and `penpot-cache` (valkey 9.1.2) are
separate HelmReleases and are NOT edited.

### 1.A — 2.17.2 -> 2.18.0 / chart 1.9.0 -> 1.10.0 (evidence gathered 2026-09-27, still valid)

Why it is not auto-safe:

1. **Forward-only DB migration.** `backend/src/app/migrations.clj@2.18.0` adds
   exactly one step over 2.17.2 (161 -> 162):
   `0152-improve-uuid-defaults-and-drop-extension`. Its SQL
   (`migrations/sql/0152-...sql`, 29 lines) is only
   `ALTER TABLE <21 tables> ALTER COLUMN id SET DEFAULT gen_random_uuid();` —
   despite the name it contains no `DROP EXTENSION` (live DB has `uuid-ossp 1.1`,
   it stays). Upstream comment: *"The application already generates IDs
   explicitly via uuid/next in all code paths; this migration adds
   gen_random_uuid() as a safety-net default"*. The runner
   (`app/util/migrations.clj@2.17.2`, `impl-migrate-single`) applies only steps
   *not* registered and never validates unknown rows, so 2.17.2 starts cleanly on
   the migrated schema. Rollback is therefore git-revert in practice; the dump is
   the floor (§5).
2. **Base-image switch on all three images** — CHANGES.md 2.18.0: *"Migrate
   Docker images to Docker Hardened Images (DHI)"* (PRs #10732-#10734):
   ubuntu:26.04 / nginx-unprivileged -> `dhi.io/debian-base:trixie-debian13-dev`,
   `dhi.io/nginx:1.31.1-debian13-dev`, `dhi.io/node:24.20.0-debian13-dev`.
   Checked the 2.18.0 Dockerfiles: all three still create user `penpot` **uid
   1001** (matches the chart's `runAsUser: 1001` / `fsGroup: 1001`) and keep
   `/bin/bash` (the `-dev` variants). Asset files on the CIFS share are
   `penpot:penpot` 1001 today, so no ownership change expected — but it is the
   thing most likely to surprise, hence §4.4 reads the share through the new pod.
3. **Chart 1.10.0 adds `values.schema.json`.** `helm template` with our values
   **fails** locally on `config.publicUri` (`${SECRET_DOMAIN}` is not a valid
   URI). In-cluster this is fine: Kustomization `penpot` has
   `postBuild.substituteFrom cluster-settings/cluster-secrets`, and the live HR's
   `publicUri` is already substituted (checked: no `${`, scheme https). Any
   *local* render must substitute a placeholder domain first (§2.6).

Chart diff 1.9.0..1.10.0 rendered with OUR values (placeholder domain):
image tags + labels only, plus (a) frontend env `PENPOT_INTERNAL_RESOLVER`
(fieldRef podIP) **removed** — the 2.18.0 `nginx-entrypoint.sh` now defaults it
to the `/etc/resolv.conf` nameserver; backend/exporter `proxy_pass` targets are
envsubst'd static names, so unaffected; (b) a `helm.sh/hook: test` Pod
(`penpot-test-connection`), which Flux does not run (HR has no `spec.test`).
No values renames. Admin Console is added but gated on `enable-admin-console`
in `config.flags`; **our flags do not contain it**, so nothing new deploys
(render: still exactly 3 Deployments, 3 Services, 1 ServiceAccount). The
postRenderers target `Deployment/penpot-backend` still exists in the 1.10.0
render. The chart's own `gateway.enabled` stays default false, so no chart
HTTPRoute collides with our `httproute/penpot`.

**Redis/valkey:** no redis/valkey version requirement in 2.18.0 CHANGES.md or
the chart; `PENPOT_REDIS_URI` rendering is byte-identical. 2.18.0 runs against
the current valkey 9.1.2 — this plan does not depend on `penpot-cache-9.2`.

### 1.B — the retarget delta: chart 1.10.0 -> 1.11.1 / app 2.18.0 -> 2.18.1 (gathered 2026-10-05)

Why coverage held it: G3 found no release notes, not a breaking change. The
notes exist — they are in `CHANGES.md` at tag 2.18.1, not a GitHub release
body. Read from primary sources:

- **App 2.18.1 is a bug-fix patch.** `CHANGES.md@2.18.1` has only a
  ":bug: Bugs fixed" section, four items: workspace stack overflow on a
  context menu for an off-page shape; repeated error toasts from injected
  third-party scripts; register flow from a workspace URL; empty response when
  exporting a binfile via the API. None is a migration or config change.
- **No new DB migration.** `backend/src/app/migrations.clj` is byte-identical
  between tags 2.18.0 and 2.18.1 (`diff` empty; 162 `:name "0...` entries in
  both). So the schema end state is still 162 with `0152` the only new step
  over our 161 — §4.2 and §5 A are unchanged.
- **Upstream compare 2.18.0...2.18.1** (18 commits, 52 files): the
  deploy-relevant ones are
  (a) `Dockerfile.backend` adds `jdk.management` to the jlink module list (so
  JVM process metrics appear) — no user/uid/entrypoint change; frontend and
  exporter Dockerfiles untouched, so uid 1001 and `/bin/bash` hold as in §1.A;
  (b) `backend/src/app/http.clj` + `main.clj` add an Undertow metrics sampler
  (`penpot_http_worker_*`, `penpot_http_connector_*`) — we scrape no penpot
  `/metrics`, so inert here; it does log `unexpected error on http metrics
  sampling` on a sampler failure, which §4.7's error grep would NOT hide;
  (c) `docker/images/files/nginx.conf.template` (the frontend) changes
  `access_log` to a `penpot_upstream` format and adds a **second `server`
  block `listen 8082` serving only `location = /stub_status`**. That is the
  one capability change in the delta: an nginx connection-count page bound on
  every pod interface. Our Service `penpot` exposes only 8080 (the chart
  render below has no 8082 port) and `httproute/penpot` targets the Service, so
  it is not reachable from the edge — only pod-IP-to-pod-IP inside the cluster.
  It reveals connection counters, no data. Recorded, not mitigated; §4.1b
  asserts the Service still has exactly one port so a future chart that
  publishes it fails loudly;
  (d) `srepl/main.clj` adds `delete-profiles-by-email!` helpers to the admin
  REPL (we run `enable-prepl-server`, localhost-only) — additive, nothing calls
  it; (e) `frontend` auth/register/verify-token fixes (the CHANGES items).
  `exporter/` is untouched between the tags, so the §4.7 (b) log string
  `redis connection established` is still emitted.
- **Chart 1.10.0 -> 1.11.0 -> 1.11.1** (tarballs diffed with `diff -r`):
  1.11.0 = image tags 2.18.0 -> 2.18.1 only; 1.11.1 = refactor of the
  `PENPOT_REDIS_URI` env into a `penpot.redisUriEnv` helper (same output) plus
  `PENPOT_MCP_REDIS_URI` on the MCP deployment, which we do not render
  (the MCP and Admin Console Deployments are gated on `penpot.mcpEnabled` /
  `penpot.adminConsoleEnabled`, i.e. on flags we do not set — neither renders
  with our values). No values keys added/renamed; `values.schema.json`
  identical (`diff -r` lists no change to it).
- **Rendered with OUR values** (`helm template` 1.10.0 vs 1.11.1, placeholder
  domain): both rc 0, both `3 Deployment, 3 Service, 1 ServiceAccount, 1 Pod
  (helm test hook)`; the diff is exclusively `helm.sh/chart`,
  `app.kubernetes.io/version` labels and the three `image:` lines
  2.18.0 -> 2.18.1. `PENPOT_REDIS_URI` renders identically (value
  `redis://penpot-cache:6379/0`).

Conclusion: no reason to stop at 1.10.0. Every 1.10.0 gate below applies
unchanged with `2.18.1` substituted; the only addition is §4.1b (Service
port set). Baselines re-measured live 2026-10-05 and unchanged from
2026-09-27: migrations 161; profile 1 / team 1 / project 1 / file_live 1 /
storage_object_live 66 / file_media_object 6; probe asset
`de519720-...` 1788 image/jpeg; cache CLIENT LIST 4 backend + 1 exporter +
1 cli; HR history rev 30 = penpot-1.9.0.

**Security findings** (cited, detail on the records): images scanned locally
with trivy 0.70.0 (`--scanners vuln --severity CRITICAL,HIGH --ignore-unfixed`),
2.17.2 as the control that the method reproduces the findings.
- `F-4c3c5206` (exporter): **answered** — `penpotapp/exporter:2.18.0` (2026-09-27)
  and `penpotapp/exporter:2.18.1` (re-scanned 2026-10-05, same method) both
  show 0 fixable CRITICAL. Claimed in `finding_refs`, cited as `security_ref`.
- `F-220e7d7b` (backend) and `F-9ac47520` (frontend): not claimed — the
  2026-10-05 re-scan of 2.18.1 does not let this plan claim them; the sweep
  re-rates them after this lands (detail on the records only).

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.1 premises (all 6 must PASS)
.venv/bin/python3 runbooks/plan-premises.py penpot-chart-1.10.0

# 2.2 Flux + pods healthy, nothing in flight
flux get helmreleases -n office | grep -E 'NAME|penpot'
kubectl -n office get deploy penpot-backend penpot-frontend penpot-exporter penpot-cache
kubectl -n office get sts penpot-db
# PASS: 3 HRs Ready True; every deploy 1/1; sts 1/1.
kubectl -n office get deploy penpot-cache -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
grep -n 'tag:' kubernetes/apps/office/penpot-cache/app/helmrelease.yaml
# PASS: the live tag equals the manifest tag (2026-09-27: 9.1.2 / tag: "9.1.2").

# 2.2b reconnect baseline for §4.7 (source IPs connected to the cache)
kubectl -n office exec deploy/penpot-cache -- valkey-cli CLIENT LIST | awk '{print $2}' | cut -d= -f2 | cut -d: -f1 | sort | uniq -c
kubectl -n office get pod -l app.kubernetes.io/name=penpot-backend -o jsonpath='{.items[0].status.podIP}{"\n"}'
kubectl -n office get pod -l app.kubernetes.io/name=penpot-exporter -o jsonpath='{.items[0].status.podIP}{"\n"}'
# 2026-09-27: 4 from the backend pod IP, 1 from the exporter pod IP, 1 from 127.0.0.1 (the cli).

# 2.3 nightly Longhorn backup of the DB volume is fresh (floor under the dump)
kubectl -n storage get volume pvc-280be202-dcc0-4eb6-b959-58ab70711d78 -o jsonpath='{.status.lastBackupAt}{"\n"}'
kubectl -n storage get backups.longhorn.io -l backup-volume=pvc-280be202-dcc0-4eb6-b959-58ab70711d78 \
  --sort-by=.metadata.creationTimestamp -o custom-columns='NAME:.metadata.name,STATE:.status.state,CREATED:.metadata.creationTimestamp' | tail -2
# PASS: newest Completed < 26h (2026-09-27 reading: lastBackupAt 2026-09-27T03:07:35Z).
# (cronjob/daily-backup-all-volumes in ns storage — live-checked — produces it.)

# 2.4 BASELINE (contents) — captured to a file the §4 diff reads
B=$HOME/penpot-backups/pre-2.18.1; mkdir -p "$B"
kubectl -n office exec penpot-db-0 -c app -- psql -U penpot -d penpot -At -c "
 select 'profile',count(*) from profile union all
 select 'team',count(*) from team union all
 select 'project',count(*) from project union all
 select 'file_live',count(*) from file where deleted_at is null union all
 select 'storage_object_live',count(*) from storage_object where deleted_at is null union all
 select 'file_media_object',count(*) from file_media_object;" > "$B/counts.txt"
cat "$B/counts.txt"
kubectl -n office exec penpot-db-0 -c app -- psql -U penpot -d penpot -At -c "select count(*) from migrations;"
# Reading 2026-09-27: profile 1, team 1, project 1, file_live 1, storage_object_live 66; migrations 161.
# If migrations is already 162, STOP: something ran 2.18.x already.

# 2.5 the asset-fetch probe object (oldest live file-media-object) + its size/type
kubectl -n office exec penpot-db-0 -c app -- psql -U penpot -d penpot -At -F' ' -c "
 select id, size, metadata->>'~:content-type' from storage_object
 where deleted_at is null and metadata->>'~:bucket'='file-media-object'
 order by created_at limit 1;" | tee "$B/asset-probe.txt"
# 2026-09-27: de519720-cecd-4ec6-983e-9d1e07a1afe5 1788 image/jpeg
read AID ASIZE ATYPE < "$B/asset-probe.txt"
kubectl -n office port-forward svc/penpot 18080:8080 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -o "$B/asset-pre.bin" -w 'code=%{http_code} bytes=%{size_download} ctype=%{content_type}\n' \
  -L "http://127.0.0.1:18080/assets/by-id/$AID"
kill $PF 2>/dev/null
# 2026-09-27 baseline: code=200 bytes=1788 ctype=image/jpeg, first bytes ff d8 ff.

# 2.6 (optional) re-render proof — schema needs a real-looking URI locally
S=$(mktemp -d); yq '.spec.values' kubernetes/apps/office/penpot/app/helmrelease.yaml \
  | sed 's/\${SECRET_DOMAIN}/example.com/' > "$S/v.yaml"
helm template penpot penpot/penpot --version 1.11.1 -n office -f "$S/v.yaml" | grep -E '^kind:' | sort | uniq -c
# PASS: 3 Deployment, 3 Service, 1 ServiceAccount, 1 Pod (helm test hook, not run by Flux).
```

## 3. Steps

1. **T0 + dump (backup_gate).** Plain SQL with `--clean --if-exists` so the
   restore in §5 B is one `psql -f`. Dry-run 2026-09-27: rc=0, ~5.1 MB,
   59 `COPY public.` blocks, completion marker present (PG18 appends a
   `\unrestrict` line after the marker, so grep the whole file, not `tail -1`).

   ```bash
   B=$HOME/penpot-backups/pre-2.18.1
   date -u +%Y-%m-%dT%H:%M:%SZ > "$B/T0"; cat "$B/T0"
   kubectl -n office exec penpot-db-0 -c app -- pg_dump -U penpot -d penpot --clean --if-exists > "$B/penpot.sql"
   echo "rc=$? bytes=$(wc -c < "$B/penpot.sql")"
   grep -c 'PostgreSQL database dump complete' "$B/penpot.sql"   # must be 1
   grep -c '^COPY public\.' "$B/penpot.sql"                      # must be >= 50 (59 on 2026-09-27)
   ```
   Any of: rc != 0, bytes < 1000000, marker != 1, COPY < 50 -> **STOP**, do not push.

2. **Edit the pin** (dry-tested on a scratch copy with BSD sed 2026-10-05;
   resulting diff exactly `<       version: 1.9.0` / `>       version: 1.11.1`):

   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' 's/^\([[:space:]]*\)version: 1\.9\.0$/\1version: 1.11.1/' kubernetes/apps/office/penpot/app/helmrelease.yaml
   git diff --stat kubernetes/apps/office/penpot/app/helmrelease.yaml    # 1 file, 1+/1-
   yq '.spec.chart.spec.version' kubernetes/apps/office/penpot/app/helmrelease.yaml   # 1.11.1
   ```

3. **Commit only that file, verify, push.**

   ```bash
   git commit --only kubernetes/apps/office/penpot/app/helmrelease.yaml \
     -m "feat(penpot): chart 1.9.0 -> 1.11.1 (app 2.18.1) (plan penpot-chart-1.10.0)"
   git log -1 --format=%s     # must be YOUR subject (shared-worktree message swap)
   git show --stat HEAD       # exactly one file
   git push
   ```

4. **Let the webhook reconcile** (no manual reconcile). Rolling update of three
   Deployments; backend start runs migration 0152 (sub-second, 21 ALTERs) and
   has a 300 s startupProbe budget. Expect up to ~2-4 min of degraded Penpot.
   RollingUpdate is safe here: the only PVC mounted is CIFS RWX
   (`smb.csi.k8s.io`, attachRequired false) — no Multi-Attach.

## 4. Verification

Start once `flux get hr -n office penpot` shows `penpot@1.11.1` Ready.

```bash
B=$HOME/penpot-backups/pre-2.18.1; T0=$(cat "$B/T0"); read AID ASIZE ATYPE < "$B/asset-probe.txt"

# 4.1 all three run 2.18.1, old pods gone, postRenderer patch survived
kubectl -n office get pods -l app.kubernetes.io/instance=penpot \
  -o 'custom-columns=POD:.metadata.name,IMG:.status.containerStatuses[0].image,READY:.status.containerStatuses[0].ready,RST:.status.containerStatuses[0].restartCount'
kubectl -n office get deploy penpot-backend -o jsonpath='{.spec.template.spec.initContainers[*].name}{"\n"}'
kubectl -n office get deploy -l app.kubernetes.io/instance=penpot -o name | wc -l
# PASS: exactly 3 pods, each penpotapp/<c>:2.18.1, READY true, RST 0; initContainers
#   "wait-for-postgresql wait-for-redis"; exactly 3 Deployments (no admin-console).
# FAIL shapes: a 2.17.2 row = roll incomplete; empty initContainers = postRenderer
#   target no longer matched; 4 deployments = admin console appeared (flags changed).

# 4.1b the 2.18.1 frontend stub_status listener (:8082) is NOT published by a Service (§1.B c)
kubectl -n office get svc -l app.kubernetes.io/instance=penpot \
  -o jsonpath='{range .items[*]}{.metadata.name}={range .spec.ports[*]}{.port}{","}{end}{"\n"}{end}'
# PASS: exactly "penpot=8080," "penpot-backend=6060," "penpot-exporter=6061," (read live
#   2026-10-05 for svc/penpot: "8080"; the 1.11.1 render has no 8082 anywhere).
# FAIL: any 8082 in the output = the chart started publishing nginx stub_status; that is a
#   new in-cluster surface this plan did not assess — STOP and surface, do not proceed.

# 4.2 migration applied (contents of the schema, not "backend Ready")
kubectl -n office exec penpot-db-0 -c app -- psql -U penpot -d penpot -At -c \
 "select count(*), count(*) filter (where step='0152-improve-uuid-defaults-and-drop-extension') from migrations;"
kubectl -n office exec penpot-db-0 -c app -- psql -U penpot -d penpot -At -c \
 "select column_default from information_schema.columns where table_name='file' and column_name='id';"
# PASS: "162|1" and "gen_random_uuid()". FAIL: "161|0" (backend never migrated) or
#   uuid_generate_v4() default.

# 4.3 data survived — exact diff against the §2.4 baseline
kubectl -n office exec penpot-db-0 -c app -- psql -U penpot -d penpot -At -c "
 select 'profile',count(*) from profile union all
 select 'team',count(*) from team union all
 select 'project',count(*) from project union all
 select 'file_live',count(*) from file where deleted_at is null union all
 select 'storage_object_live',count(*) from storage_object where deleted_at is null union all
 select 'file_media_object',count(*) from file_media_object;" > "$B/counts-post.txt"
diff "$B/counts.txt" "$B/counts-post.txt" && echo COUNTS_IDENTICAL
# PASS: COUNTS_IDENTICAL. storage_object_live may be HIGHER only if 4.5/4.6 already
#   ran (new thumbnails/tempfiles) — run 4.3 first. Any LOWER count = FAIL -> §5.

# 4.4 an asset is served with real bytes through the new frontend -> backend -> CIFS
kubectl -n office port-forward svc/penpot 18080:8080 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -o "$B/asset-post.bin" -w 'code=%{http_code} bytes=%{size_download} ctype=%{content_type}\n' \
  -L "http://127.0.0.1:18080/assets/by-id/$AID"
cmp "$B/asset-pre.bin" "$B/asset-post.bin" && echo ASSET_BYTES_IDENTICAL
kill $PF 2>/dev/null
# PASS: code=200, bytes=$ASIZE (1788), ctype=$ATYPE, ASSET_BYTES_IDENTICAL.
# Why this can fail and still be the right probe: in 2.18.0 (unchanged in 2.18.1) assets.clj `objects-handler`
#   returns 401 for any bucket NOT in `public-buckets`; file-media-object IS in that set,
#   so anonymous 200 is the correct expectation. A DHI uid/permission regression on the
#   CIFS share prints 404/500 with a small JSON/HTML body and cmp differs.

# 4.5 LOGIN (operator, attended): open https://penpot.<domain> in a PRIVATE window,
#   log in with the existing account, open the one project/file. Then:
kubectl -n office exec penpot-db-0 -c app -- psql -U penpot -d penpot -At -c \
 "select count(*) from http_session_v2 where created_at > '$T0';"
# PASS: >= 1 (a session row was minted by the new backend). FAIL: 0 = the login never
#   reached the backend / was rejected. A non-private window can reuse an old cookie
#   and mint nothing — that is why the private window is required.

# 4.6 EXPORTER renders: in the open file, select a board -> Export -> PNG -> download.
kubectl -n office exec penpot-db-0 -c app -- psql -U penpot -d penpot -At -c \
 "select count(*) from storage_object where metadata->>'~:bucket'='tempfile' and created_at > '$T0';"
kubectl -n office logs deploy/penpot-exporter --since=15m | grep -i -c -E 'error|exception'   # ADVISORY
# PASS: tempfile count >= 1 (backend/src/app/rpc/management/exporter.clj `upload-tempfile`
#   stores the exporter's rendered result in bucket "tempfile") AND the downloaded file
#   starts with the PNG magic (`head -c 8 <file> | od -An -tx1` -> 89 50 4e 47 ...).
#   FAIL: count 0 (render never uploaded) or not a PNG.
#   The error/exception grep is ADVISORY only (never measured against a clean baseline);
#   a non-zero count is read, not gated on.

# 4.7 backend + exporter RECONNECTED to penpot-cache (positive evidence, not absence)
NB=$(kubectl -n office get pod -l app.kubernetes.io/name=penpot-backend -o jsonpath='{.items[0].status.podIP}')
NE=$(kubectl -n office get pod -l app.kubernetes.io/name=penpot-exporter -o jsonpath='{.items[0].status.podIP}')
echo "new backend=$NB new exporter=$NE"
kubectl -n office exec deploy/penpot-cache -- valkey-cli CLIENT LIST | awk '{print $2}' | cut -d= -f2 | cut -d: -f1 | sort | uniq -c
# (a) PASS: >= 1 connection from $NB AND >= 1 from $NE (baseline §2.2b: 4 backend, 1 exporter;
#     the NEW pod IPs read 0 before the roll). FAIL: either new IP absent — the client never
#     reconnected (only 127.0.0.1 / stale IPs listed). Run only once exactly one pod per
#     component exists (the jsonpath takes items[0]).
kubectl -n office logs deploy/penpot-exporter | grep -c 'redis connection established'
# (b) PASS: >= 1 (string logged by exporter/src/app/redis.cljs@2.18.0, exporter/ untouched in 2.18.1, on connect; present in
#     the 2.17.2 exporter log 2026-09-27 = 1). FAIL: 0 = exporter never connected.
kubectl -n office logs deploy/penpot-backend --since=10m | grep -i -c -E 'RedisCommandTimeout|RedisConnectionException|Connection refused'
# Extra FAIL signal only: a non-zero count from T+3 min is a FAIL; a zero proves nothing by itself.

# 4.8 floor
flux get helmreleases -n office | grep penpot
kubectl -n office get httproute penpot -o jsonpath='{.status.parents[0].conditions[?(@.type=="Accepted")].status}{"\n"}'   # True
```

CONTENTS ASSERTION: Penpot's data and assets survive the migration and the new
images serve them — measured by 4.3 (exact per-table count diff vs the §2.4
baseline: profile 1, team 1, project 1, file_live 1, storage_object_live 66 on
2026-09-27), 4.4 (the probe asset returns 200 with byte-identical content to
the pre-change fetch), 4.2 (migration count 161 -> 162 with the 0152 step
present), 4.5 (a new `http_session_v2` row after T0 from a real login) and 4.6
(a `tempfile` storage object after T0 from a real exporter render).

CONTROL: metric kube_pod_container_info — `{namespace="office",pod=~"penpot-(backend|frontend|exporter).*"}` must return exactly three series, each with `image` ending `:2.18.1` (read 2026-09-27: three series on `:2.17.2`).
CONTROL: metric kube_deployment_status_replicas_available — `{namespace="office",deployment=~"penpot-(backend|frontend|exporter)"}` must be 1 for each for 10 min after the roll (baseline 1/1/1).
CONTROL: metric kube_pod_container_status_restarts_total — `{namespace="office",pod=~"penpot-(backend|frontend|exporter).*"}` must not increase during the 10 min after the roll (baseline 0); a DHI permission or migration crash-loop shows here first.

## 5. Rollback

### A — primary: git revert (schema-compatible, measured from upstream code)

2.17.2's migration runner applies only unregistered steps and ignores the extra
`0152-improve-uuid-...` row; the migration only changed column DEFAULTs to
`gen_random_uuid()` (built into PG18) and the app sets ids explicitly. So the
old images run on the migrated DB.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-§3-step-3>
git log -1 --format=%s ; git show --stat HEAD      # one file, the revert
git push
```
If the HR is stuck `pending-upgrade` / remediation-looping, clear it first per
`docs/sops/application-update.md` §11:
`helm rollback penpot <last-deployed-revision> -n office --wait=false`
(`helm history penpot -n office` for the number; v30 was 1.9.0 on 2026-09-27).

Confirm back: §4.1 shows `:2.17.2` on all three; §4.3 diff = COUNTS_IDENTICAL;
§4.4 asset 200 + identical bytes; one private-window login works.

### B — floor: restore the pre-upgrade dump (only if data is wrong/damaged)

**UNTESTED END TO END.** The dump command was dry-run (2026-09-27, rc 0, marker
present); the restore sequence below has NOT been exercised against this
database. It is the floor, not a proven path — expect to read errors and adapt.

Loses anything written after T0 (new files/assets metadata; asset blobs written
after T0 stay on the CIFS share as orphans — harmless; **never delete anything
on `penpot-assets`**, see `docs/sops/storage-safety.md`).

```bash
B=$HOME/penpot-backups/pre-2.18.1
flux suspend helmrelease penpot -n office          # stop helm-controller re-scaling
kubectl -n office scale deploy penpot-backend penpot-exporter --replicas=0
kubectl -n office get pods -l app.kubernetes.io/instance=penpot   # backend/exporter gone
kubectl cp "$B/penpot.sql" office/penpot-db-0:/tmp/penpot-pre-2.18.1.sql -c app
kubectl -n office exec penpot-db-0 -c app -- psql -U penpot -d penpot -v ON_ERROR_STOP=1 -q -f /tmp/penpot-pre-2.18.1.sql
kubectl -n office exec penpot-db-0 -c app -- psql -U penpot -d penpot -At -c "select count(*) from migrations;"   # 161
kubectl -n office exec penpot-db-0 -c app -- rm -f /tmp/penpot-pre-2.18.1.sql
# then do rollback A (git revert + push), then:
flux resume helmrelease penpot -n office           # re-applies replicas: 1 with 2.17.2
```
Confirm: §2.4 query output `diff`s silent against `$B/counts.txt`, migrations
161, §4.4 asset fetch 200/identical, login works. If the dump itself is bad,
the Longhorn backup from §2.3 restores `penpot-db-data` (`docs/sops/backup.md`,
Longhorn restore). Suspend the DB release first so helm-controller does not
re-scale it, then scale down:
```bash
flux suspend helmrelease penpot-db -n office
kubectl -n office scale sts penpot-db --replicas=0
# ... Longhorn restore per docs/sops/backup.md ...
flux resume helmrelease penpot-db -n office
```

## 6. Interference notes

- **Never in the same window as `penpot-cache-9.2`** (in `conflicts_with`). This
  plan rolls penpot-backend/exporter, which drop and re-open their connections to
  `penpot-cache`; that plan restarts the cache (Recreate) and verifies by counting
  exactly those reconnects (`CLIENT LIST` backend + exporter IPs) and the backend's
  redis-error log count. Run together, a reconnect or redis-error failure has two
  possible causes and neither plan's rollback is attributable. Penpot 2.18.0/2.18.1 have
  **no** redis/valkey version requirement (CHANGES.md 2.18.0 + 2.18.1 and the chart
  render are silent; `PENPOT_REDIS_URI` is unchanged), so there is no ordering
  dependency either way — they simply must not share a night. `penpot-cache-9.2`
  is `blocked` (no GA valkey 9.2.N) and this plan does not wait for it. That
  plan's `conflicts_with` now lists `penpot-chart-1.10.0` back (re-read
  2026-10-05; reciprocity is not checked by `--validate`).
- `kube-prometheus-stack-91.4.1` (status executed; ref kept while the file
  exists) — §4 CONTROL metrics read through it.
- `flux-oci-chart-sources` rewrites penpot's `spec.chart` (mirror track) — the
  same field this plan edits; `helm-drift-detection` adds `spec.driftDetection`
  to every HR including penpot; `app-template-5.2.1` helm-upgrades `penpot-db`
  and `penpot-cache`, which penpot `dependsOn`. Each would make a failure here
  unattributable.
- `chart-patches-coredns-reloader-blackbox` rolls coredns. From 1.10.0 on (so in 1.11.1) the
  frontend nginx `resolver` is the pod's `/etc/resolv.conf` nameserver (cluster
  DNS) instead of the pod IP, so a coredns disturbance the same night lands on
  the path this plan just changed.
- `flux-reconciler-impersonation` is `exclusive: true` and changes the identity
  helm-controller applies with in `office`; a failed apply here would be
  ambiguous that night.
- Public edge: `httproute/penpot` on `envoy-external` keeps serving; its backend
  Service `penpot` rolls, so external users see a short outage. Homepage widget
  uses pod-selector `app.kubernetes.io/name=penpot-backend` — label unchanged.
- Other `office` apps (nextcloud, paperless, ...) share only the namespace; no
  shared DB/cache/PVC with penpot.
- CIFS: `pvc/penpot-assets` (class `cifs-penpot-assets`, severe tier) is only
  re-mounted by the new pods. Nothing in this plan deletes a PVC; the rollback
  explicitly forbids cleaning orphan blobs.
- Step 0 of the window must not touch penpot's siblings: `penpot-db`/`penpot-cache`
  chart bumps are AR-accepted (`F-434c3acd` under AR-038, `F-afc9bd6a` under
  AR-039; both re-read 2026-10-05: accepted, expire 2026-12-27) and the `*valkey*`
  deny rule holds the cache image. No interaction with this retarget: AR-038/039
  freeze the app-template chart under `penpot-db`/`penpot-cache` only; penpot
  1.11.1 needs no newer postgres or valkey (CHANGES.md 2.18.0/2.18.1 silent,
  render unchanged). If an AR lapses and `app-template-5.2.1` runs, it is already
  in `conflicts_with`. `penpot-cache-9.2` is still `blocked` (no GA 9.2.N) and
  remains a never-same-night conflict, not a dependency.
