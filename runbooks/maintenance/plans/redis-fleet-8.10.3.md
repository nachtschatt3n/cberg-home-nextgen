---
plan_id: redis-fleet-8.10.3
component: redis                      # coverage group redis-fleet-8.10.3 (image-fleet, 9 members). `component: redis` is also the
                                      # coverage key of databases/redis, which this plan now genuinely moves (leg 1); the 3-member
                                      # draft of 2026-10-27 carried the same key without ever touching that Deployment.
supersedes: redis-fleet-8.10.2        # vetted 8-consumer plan (ready-for-go@2026-10-25), retargeted 8.10.2 -> 8.10.3 and RE-WIDENED to
                                      # all 9 consumers 2026-11-02 (reviewer option A; §1.0). Its legs are reused, re-verified live.
pr: null                              # coverage.py needs_plan (direct-bump lane) — no Renovate PR
kind: image
current: "redis:8.10.1-alpine on 8 consumers (databases/redis, databases/superset-redis-official, download/tube-archivist-redis, media/immich-redis, office/nextcloud-redis, office/paperless-redis, office/sure-redis, ai/open-webui-redis sidecar of chart open-webui 17.0.0) and redis:8.10.2-alpine on office/affine-redis"
target: "redis:8.10.3-alpine on all 9 redis consumers: databases/redis, superset-redis-official, tube-archivist-redis, immich-redis, nextcloud-redis, paperless-redis, sure-redis, affine-redis and the open-webui redis sidecar (the open-webui APP v0.12.5 and chart 17.0.0 are NOT part of this plan)"
update_type: patch
risk: medium                          # Each leg alone is low (same-minor patch; 8.10.2->8.10.3 is 6 commits, the only
                                      # server-behaviour change is gated on cluster_enabled; RDB_VERSION 15 unchanged).
                                      # Medium because (a) nextcloud-redis signs every user out; (b) the sure-redis leg
                                      # SILENTLY EMPTIES Sure's sidekiq-cron schedule unless sure-worker is restarted (§1.4);
                                      # (c) nine restarts of shared session/broker stores in one slot, two of them with
                                      # durable state (databases/redis AOF, tube-archivist RDB incl. the durable ta:cookie).
est_duration_min: 80                  # pre-checks 12 · 9 legs x ~5 = 45 · sure-worker restart +3 · waits the gates absorb
                                      # (nextcloud-cron <=5, immich poll <=3, notify-push <=3, open-webui <=2, affine <=3) ·
                                      # attended checks (paperless PDF, open-webui chat, Nextcloud login) ~8. 80 exceeds the
                                      # 70-min sat-attended budget, so this plan takes a SUNDAY slot (180 schedulable).
needs_reboot: false
touches:
  namespaces: [databases, download, media, office, ai]
  resources:
    - helmrelease/redis                         # databases — app-template 5.3.0, AOF on pvc/redis-data
    - deployment/redis
    - pvc/redis-data                            # remounted by the Recreate, AOF re-loaded; not modified
    - deployment/superset-redis-official        # databases — plain manifest (superset Kustomization), requirepass
    - helmrelease/affine-redis                  # office — app-template 5.3.0, non-persistent BullMQ store (8.10.2 -> 8.10.3)
    - deployment/affine-redis
    - helmrelease/open-webui                    # ai — ONLY the redis sidecar tag changes (chart 17.0.0, app v0.12.5 untouched)
    - deployment/open-webui-redis
    - helmrelease/tube-archivist-redis          # download — RDB on pvc/tube-archivist-redis-data
    - deployment/tube-archivist-redis
    - pvc/tube-archivist-redis-data             # remounted, dump.rdb re-loaded; not modified
    - helmrelease/immich-redis                  # media — app-template 5.3.0, non-persistent BullMQ store
    - deployment/immich-redis
    - helmrelease/sure-redis                    # office — app-template 5.3.0, non-persistent
    - deployment/sure-redis
    - deployment/sure-worker                    # office — ROLLOUT RESTART after the swap (§3 leg 7)
    - deployment/paperless-redis                # office — plain manifest (paperless-ngx Kustomization), requirepass
    - deployment/nextcloud-redis                # office — plain manifest (nextcloud Kustomization), requirepass wrapper
    - secret/nextcloud-config                   # read-only reference (redis auth key); not modified, never printed
    # consumers that reconnect in-process and are NOT restarted (asserted in §4 v_cons):
    - deployment/superset-worker
    - deployment/superset-celerybeat
    - deployment/affine
    - statefulset/open-webui                    # asserted unchanged by its own leg-4 gate (not in the v_cons set)
    - deployment/tube-archivist
    - deployment/immich-server
    - deployment/sure-web
    - deployment/paperless-ngx
    - deployment/nextcloud
    - deployment/nextcloud-notify-push          # may restart itself on redis loss (did twice 2026-09-27)
    - cronjob/nextcloud-cron                    # next tick after the swap is the leg-9 contents gate
  shared: [monitoring]                  # §4 reads Prometheus (the window's instrument). No gateway, storage-class,
                                        # DNS or CNI change; the two PVCs are only remounted by their own pod.
depends_on: []
conflicts_with:
  # Same consumers / same files (reciprocity must be added on their side, see the §6 hand-off list):
  - postgres-digest-refresh-2026-11   # reciprocal, added 2026-11-08 (DB-restart plan; sun-attended:2026-12-20)
  - tube-archivist-0.6.0                # restarts deployment/tube-archivist, the consumer of leg 5; its gates call into it
  - tube-archivist-elasticsearch-9.5.5  # same app, same namespace; never stack on a broker swap
  - nextcloud-mcp-0.203.0               # blocked — every gate calls into Nextcloud; lists nextcloud-redis restart
  - nextcloud-mcp-0.204.0               # blocked — successor chain of 0.203.0, same
  - bitnamilegacy-exit-nextcloud-db     # blocked — quiesces Nextcloud; never stack a session-store restart on a DB cutover
  # 2026-11-06: removed python-fleet-3.15.2 - plan executed in the NOW run 2026-11-06 and retired (dead ref in maintenance-plan.py --validate).
  - openclaw-2026.11.1                  # blocked — namespace ai (leg 4 restarts the open-webui redis pod)
  # Platform serialisation (a roll of these confounds every reconnect gate in §4):
  - helm-drift-detection                # sat-attended:2026-11-28 — asserts Helm revisions IDENTICAL across releases; this plan upgrades 6 releases
  - flux-oci-chart-sources              # sun-attended:2026-12-13 — re-points app-template + open-webui chart sources
  - flux-reconciler-impersonation       # blocked — changes WHO applies the Kustomizations/HelmReleases this plan relies on
  - talos-linux-1.14.5                  # node reboots (successor of talos-linux-1.14.4, which its own header supersedes)
  - longhorn-1.13.0                     # sun-attended:2026-11-15 — two Longhorn PVCs are remounted here; never stack on a storage upgrade
  - envoy-proxy-config-distroless-v1.40.0  # public edge roll hides app reachability gates
  - envoy-proxy-config-distroless-v1.40.2  # same
  - etcd-timeouts-5000-500              # sun-attended:2026-11-08 — control-plane timing change under nine rolling Deployments
  # The window's instrument (§4 reads Prometheus; a Grafana/operator/collector roll in the same slot confounds the controls):
  - grafana-chart-14.4.0                      # vetted — monitoring; the controls read Prometheus, Grafana is the operator's second instrument
  # REMOVED 2026-11-03 (plan retired cdf1cf53, chart live via 5aa609d5; dead ref) - otel-operator-0.26.1                # draft — monitoring; §4 reads Prometheus too
  # No kube-prometheus-stack-* plan is open (it rides the auto lane). If one is filed, or Step 0 lands a kube-prometheus-stack
  # bump the same night, add/serialize it: §4 reads Prometheus.
  # Dropped as dead refs (2026-11-02): authentik-web-max-requests (status executed), nextcloud-9.4.1 and nextcloud-whiteboard-2.1.2 (executed 2026-10-29, no plan file),
  # nextcloud-mcp-0.202.1 (superseded by 0.203.0), talos-linux-1.14.4 (superseded by 1.14.5), immich-server-3.3.5 /
  # paperless-db-13.0.2 / bitnamilegacy-exit-nextcloud-redis (executed), coredns-1.48.1 (superseded, successor has no file).
exclusive: false
capability_change: false                # same-behaviour patch bump on all nine; nextcloud-redis auth/config untouched
autonomy_override: human-gated          # nextcloud-redis logs every user out and the sure-worker restart needs a human
                                        # reading the §4 leg-7 schedule gate (policy rule *sure-redis*); legs 4/5/8 have attended checks
rollback_class: git-revert              # one commit per leg; RDB/AOF format unchanged (RDB_VERSION 15), no schema/app migration.
                                        # tube-archivist leg also takes a dump.rdb copy + Longhorn backup gate (§2 g, §3 leg 5).
backup_gate: "Completed Longhorn backup < 26h for volume tube-archivist-redis-data and for the volume behind pvc databases/redis-data (§2 g, longhorn-backup-age.py); PLUS a local copy of tube-archivist dump.rdb taken in §3 leg 5 immediately before that leg (byte count compared)."
finding_refs: [F-d2bb762b, F-8c50c463, F-d40c9c12, F-e8a41b1b, F-625d3a3f, F-c637a09a, F-2e326f86, F-3a75c9aa, F-3fcdca7b]
                                        # the 9 per-consumer redis image findings (policy-cli finding list --grep redis, 2026-11-02):
                                        # redis, superset-redis-official, affine-redis, open-webui, tube-archivist-redis,
                                        # immich-redis, sure-redis, paperless-redis, nextcloud-redis -> 8.10.3-alpine.
                                        # Related, NOT closed by this plan: F-8792dba3 (coverage.py lockstep scope), see §6.
status: vetted                    # human-gated; window null until the operator GO (suggested sun-attended:2026-11-29, 80 of 180 min)
review: ready-for-go@2026-11-02   # plan-reviewer 2026-11-02: needs-fix (fleet scope split, orphaned GO, stale digest, unfailable slot grep), rewritten to 9 consumers, delta re-review ready-for-go; HUMAN-GATED: a fresh operator GO on this plan_id is required (no earlier GO carries over)
                                        # leg 3 (affine) is new. Needs a fresh plan-reviewer pass.
window: "sun-attended:2026-11-29"      # OPERATOR GO 2026-11-02 (chat: do all of this now). Was SUGGESTION: "sun-attended:2026-11-29" (alternative sat-attended:2026-11-28 does NOT fit: 80 min > 70).
                                        # Do NOT use 11-07/08/14/15/21/22 (each holds a conflicts_with plan). Re-stamp after review.
                                        # NOTE 2026-11-02: sun-attended:2026-11-29 is the RESERVED CONTINUATION slot for
                                        # talos-linux-1.14.5 (this plan names it in conflicts_with) if that roll's canary stops
                                        # part-rolled on 11-22 (Longhorn rebuild time at limit 2 unmeasured). If so, THIS plan
                                        # must be moved to the next free Sunday by the coordinator.
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/verification-contents-not-shape.md
  - docs/sops/backup.md
  - docs/sops/storage-safety.md               # read-only relevance: two Longhorn PVCs remounted, none deleted
  - docs/sops/paperless.md
  - docs/sops/immich.md
  - docs/sops/vulnerability-disclosure.md
generated: "2026-10-27"
replanned: "2026-11-02"
premises:
  # Read-verb only. Each was measured 2026-11-02 and returned the expected value.
  - id: databases-images-current
    why: >-
      `current:` claims 8.10.1-alpine on both databases redis Deployments (order redis,
      superset). A different value means the nightly lane or a hand edit moved one: that
      leg is a no-op and its sed matches nothing. Drop the leg, do not force it. 8.10.3
      means someone already did it (and the fleet is split, so STOP and re-plan).
    run: kubectl get deploy -n databases redis superset-redis-official -o jsonpath='{.items[*].spec.template.spec.containers[0].image}'
    expect_exact: redis:8.10.1-alpine redis:8.10.1-alpine
  - id: office-images-current
    why: Same, for nextcloud, paperless and sure (order as listed).
    run: kubectl get deploy -n office nextcloud-redis paperless-redis sure-redis -o jsonpath='{.items[*].spec.template.spec.containers[0].image}'
    expect_exact: redis:8.10.1-alpine redis:8.10.1-alpine redis:8.10.1-alpine
  - id: affine-redis-image-current
    why: >-
      affine-redis is the one consumer already on 8.10.2 (its manifest line ends in
      8.10.2-alpine, not 8.10.1). A different value means the leg's sed (anchored on
      8.10.2) would match nothing.
    run: kubectl get deploy -n office affine-redis -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: redis:8.10.2-alpine
  - id: immich-redis-image-current
    why: Same, for immich-redis.
    run: kubectl get deploy -n media immich-redis -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: redis:8.10.1-alpine
  - id: tube-archivist-redis-image-current
    why: Same, for tube-archivist-redis.
    run: kubectl get deploy -n download tube-archivist-redis -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: redis:8.10.1-alpine
  - id: open-webui-redis-image-current
    why: Same, for the open-webui redis sidecar (rendered by the chart from redis.image.tag).
    run: kubectl get deploy -n ai open-webui-redis -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: redis:8.10.1-alpine
  - id: open-webui-app-is-a-0-12-release
    why: >-
      Leg 4 must change ONLY the sidecar tag. The app is v0.12.5 today (commit ab0c0636;
      the earlier "held on cooldown for 0.12.4" premise is stale). Any v0.12.x passes here
      because Step 0 may legitimately land a patch first; §2 j then proves git and the
      live StatefulSet agree, which is what actually keeps leg 4 from rolling the app.
      A v0.13 or other major/minor shift fails and means re-plan.
    run: kubectl get sts -n ai open-webui -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_matches: '^ghcr\.io/open-webui/open-webui:v0\.12\.\d+$'
  - id: open-webui-chart-current
    why: Leg 4 must not carry a chart bump; chart 17.0.0 is the live release.
    run: kubectl get hr -n ai open-webui -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: 17.0.0
  - id: open-webui-redis-default-config
    why: >-
      The sidecar runs the image defaults (no command override, no volume, RDB snapshots to the
      container filesystem). The literal prefix keeps output non-empty; a command after `cmd=`
      means someone changed persistence and the leg-4 reasoning (nothing durable) changes.
    run: kubectl get deploy -n ai open-webui-redis -o jsonpath='{"cmd="}{.spec.template.spec.containers[0].command}'
    expect_exact: cmd=
  - id: databases-redis-is-aof
    why: >-
      databases/redis is the canary BECAUSE it is the one AOF-persistent instance (it
      exercises the new binary loading a persisted file). If persistence changed, the leg
      order and rollback reasoning change.
    run: kubectl get deploy -n databases redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_exact: '["redis-server","--appendonly","yes","--save",""]'
  - id: tube-archivist-redis-default-config-on-pvc
    why: >-
      tube-archivist-redis runs the image's DEFAULT config (RDB snapshots, no command
      override) with /data on a PVC: the only consumer whose contents survive a restart. The
      literal prefix keeps output non-empty; a command after `cmd=` means someone changed
      persistence.
    run: kubectl get deploy -n download tube-archivist-redis -o jsonpath='{"cmd="}{.spec.template.spec.containers[0].command}{" claim="}{.spec.template.spec.volumes[?(@.persistentVolumeClaim)].persistentVolumeClaim.claimName}'
    expect_exact: cmd= claim=tube-archivist-redis-data
  - id: immich-redis-non-persistent
    why: >-
      §1.2 rules out the inherited "forward-only DB migrations" hold reason because
      immich-redis is a non-persistent BullMQ store with no volume. If persistence were
      turned on, the rollback reasoning (nothing to load) changes.
    run: kubectl get deploy -n media immich-redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_exact: '["redis-server","--save","","--appendonly","no"]'
  - id: affine-redis-non-persistent
    why: >-
      affine-redis is non-persistent (no volume); its repeatable jobs are re-seeded by the
      app's own 30-second in-process cron (§1.6), which is why leg 3 needs no consumer restart.
      If persistence were turned on, or the command changed, that reasoning needs a re-read.
    run: kubectl get deploy -n office affine-redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_exact: '["redis-server","--save","","--appendonly","no"]'
  - id: nextcloud-redis-requirepass-wrapper
    why: >-
      nextcloud-redis starts through an sh wrapper that refuses an empty REDIS_PASSWORD and
      runs --requirepass. §4 leg 9 relies on REDISCLI_AUTH and on the NOAUTH control. The
      pattern appears only in the wrapper command.
    run: kubectl get deploy -n office nextcloud-redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_contains: 'exec redis-server --save'
  - id: nextcloud-redis-auth-env-from-secret
    why: >-
      REDIS_PASSWORD and REDISCLI_AUTH both come from the nextcloud-config Secret (the
      redis auth item). The output shows NAMES only; the value is never printed. (Output is
      deliberately NOT shaped as an assignment: the earlier `secret=... key=...` form tripped
      the git-history credential scan, finding F-fe355b6d.)
    run: kubectl get deploy -n office nextcloud-redis -o jsonpath='{"ref="}{.spec.template.spec.containers[0].env[*].valueFrom.secretKeyRef.name}{" item="}{.spec.template.spec.containers[0].env[*].valueFrom.secretKeyRef.key}'
    expect_exact: 'ref=nextcloud-config nextcloud-config item=redis-password redis-password'
  - id: sure-redis-non-persistent
    why: >-
      The sure-worker restart in §3 leg 7 is required precisely because this redis loses
      everything (including the sidekiq-cron schedule) on restart. If persistence were turned
      on, the restart becomes unnecessary.
    run: kubectl get deploy -n office sure-redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_exact: '["redis-server","--save","","--appendonly","no"]'
  - id: sure-worker-surge-zero
    why: >-
      §3 leg 7 rollout-restarts sure-worker. maxSurge 0 guarantees no second Sidekiq process
      registers the cron schedule concurrently and that its RWO uploads volume is not
      double-attached.
    run: kubectl get deploy -n office sure-worker -o jsonpath='{.spec.strategy.rollingUpdate.maxSurge}'
    expect_exact: "0"
  - id: tube-archivist-redis-backed-up
    why: The one redis whose contents are persistent. Freshness is asserted in §2 g.
    run: kubectl get backups.longhorn.io -n storage -o jsonpath='{.items[?(@.status.volumeName=="tube-archivist-redis-data")].status.state}'
    expect_contains: Completed   # existence only; freshness is the §2 g longhorn-backup-age.py gate
  - id: manifest-pins-current
    why: >-
      §3's seds are anchored on these exact literals; each of the eight files must hold exactly
      one line ENDING in 8.10.1-alpine (the open-webui comment line ends in "is", so it is not
      counted; its own sed handles it). 0 = that leg's commit would be empty; 2 = a second pin
      the sed would also rewrite.
    run: grep -c "8\.10\.1-alpine$" kubernetes/apps/databases/redis/app/helmrelease.yaml kubernetes/apps/databases/superset/app/redis-deployment.yaml kubernetes/apps/ai/open-webui/app/helmrelease.yaml kubernetes/apps/download/tube-archivist/app/redis-helmrelease.yaml kubernetes/apps/media/immich/app/redis-helmrelease.yaml kubernetes/apps/office/sure/app/redis-helmrelease.yaml kubernetes/apps/office/paperless-ngx/app/redis-deployment.yaml kubernetes/apps/office/nextcloud/app/redis-deployment.yaml
    expect_matches: '(?s)^(?:\S+:1\n?){8}$'
  - id: affine-manifest-pin-current
    why: >-
      Leg 3's sed is anchored on 8.10.2-alpine: the affine file must hold exactly one line
      ENDING in it.
    run: grep -c "8\.10\.2-alpine$" kubernetes/apps/office/affine/app/redis-helmrelease.yaml
    expect_matches: '(?s)^1$'
---

# redis fleet to 8.10.3-alpine (all 9 consumers; supersedes redis-fleet-8.10.2)

> **GO RESET (2026-11-02).** Any operator go/no-go recorded against `redis-fleet-8.10.2`, or
> against the earlier 3-consumer draft of THIS plan_id, does **not** carry over. Both the target
> (8.10.2 -> 8.10.3) and the scope (3 -> 9 consumers, three of them stateful or attended) changed.
> After the plan-reviewer pass a fresh `home-operation decide` is needed on `redis-fleet-8.10.3`.
> `docs/sops/maintenance-windows.md` section 7 applies: a drifted plan KEEPS its plan_id, so the
> go/no-go issue key is the same string, and an old answer filed under it must not be read as
> consent for this scope.

## 1. Summary & why held

### 1.0 What changed vs the 2026-10-27 draft (and why it was wrong)

1. **The 10-27 draft assumed five consumers plus affine-redis would land through the Step 0
   direct-bump lane** once the G5 cooldown cleared. Live `coverage.py` (2026-11-02) shows the
   opposite: they are ALL in lane PLAN. `_apply_lockstep` (`runbooks/coverage.py`, ~line 2867)
   pulls an AUTO item back to PLAN when a sibling on the SAME image at the SAME target is held,
   because "applying this half alone splits one deployable unit across two versions". The
   `databases/redis` row is itself PLAN ("plan exists: redis-fleet-8.10.3") on the same image at the
   same target, and immich-redis, sure-redis and nextcloud-redis are held by their own deny rules, so
   the rest are pulled back behind them: superset-redis-official, tube-archivist-redis,
   paperless-redis, affine-redis and the open-webui sidecar (coverage `lockstep` list, 5 rows;
   `lanes.PLAN` carries them with `lockstep_with: image 8.10.1->8.10.3 [PLAN]`). Executing the 3-member draft would
   have left the fleet split across 8.10.1 / 8.10.2 (affine) / 8.10.3 with nothing to move the
   rest. (`databases/redis` showed "plan exists: redis-fleet-8.10.3" only because this plan's
   `component: redis` collided with that component's name; it never touched it.)
2. **Scope restored to all 9 consumers at 8.10.3-alpine** (reviewer option A), reusing the legs
   of the superseded `redis-fleet-8.10.2` that were reviewed ready-for-go on 2026-10-25 (canary
   AOF, superset, open-webui sidecar, tube-archivist RDB with the dump.rdb copy and the
   `ta:cookie` gate, paperless, with backup gates), each re-verified against the live cluster
   on 2026-11-02. New vs 8.10.2: leg 3 (affine-redis, 8.10.2 -> 8.10.3), and the open-webui leg
   is now against app v0.12.5.
3. **Target.** Upstream `redis/redis` 8.10.3 was published 2026-10-26T11:56Z (`gh release list`:
   Latest; 8.12-rc1/rc2 are pre-releases and not a candidate). Docker Hub `redis:8.10.3-alpine`:
   `8.10.4-alpine` and `8.11.0-alpine` -> 404. **The tag was RE-PUSHED on 2026-10-29T03:05Z**
   (a `riscv64` manifest was added; the 10-27 draft recorded index digest `896f241f...`, the
   index is now `sha256:21090af93f83...`). The amd64 manifest (the only architecture this
   cluster runs: three amd64 NUCs) is UNCHANGED since the first push:
   `sha256:be7c1cada5a6eb1656adfa2635b99296af725881301b21f84f35a71fac072c7f`.
   §2 b therefore pins and compares the **amd64 manifest digest**, not the index digest, and
   prints a STOP token on mismatch.
4. **The immich hold reason is inherited and false for this member** (§1.2).
5. **Reviewer-driven gate fixes** carried here: the slot check (§2 e) is now a real check that can
   fail; the Nextcloud cache gate is loosened to what was actually measured (§4 leg 9); the
   tube-archivist gate no longer hard-codes a key count that has drifted from 65 to 23.

### 1.1 What moves

Nine Docker Hub `redis` instances move to `8.10.3-alpine`, one commit per consumer, in
ascending blast radius (§3): databases/redis (leg 1, AOF canary), superset-redis-official (2),
affine-redis (3), open-webui redis sidecar (4), tube-archivist-redis (5, RDB), immich-redis (6),
sure-redis + sure-worker restart (7), paperless-redis (8), nextcloud-redis (9, last). The
open-webui leg is a one-line values change in the open-webui HelmRelease; the Helm upgrade
re-renders the StatefulSet from identical values, so no pod-template change is expected (§4
asserts it).

### 1.2 Why held, per member, and which reasons are real

Upstream delta, read from `gh api repos/redis/redis/compare/8.10.2...8.10.3` (6 commits on top
of the 6 of 8.10.2 already reviewed in the superseded plan):

- `src/pubsub.c`: PUBLISH/SPUBLISH now reject a message too large for cluster-bus propagation.
  **The new check is inside `if (server.cluster_enabled)`**; none of these instances runs
  cluster mode, so PUBLISH behaviour is unchanged for BullMQ, Sidekiq, Celery and Nextcloud.
- `src/cluster.h`, `src/cluster_legacy.c`: cluster mode only. `src/tls.c`: cert-field parsing;
  no instance here uses TLS.
- Build/CI/module Makefiles, version bump. **No `rdb.c`/`aof.c` change; `RDB_VERSION` is 15 in
  8.10.1, 8.10.2 and 8.10.3** (`src/rdb.h`), so the AOF of databases/redis and the dump.rdb of
  tube-archivist-redis load unchanged forward AND backward. That is the property the rollback
  relies on.
- Update urgency SECURITY; the item is cluster-bus-only. Item-level detail stays upstream
  (`docs/sops/vulnerability-disclosure.md`).

Per-member status (coverage.py 2026-11-02, plus the superseded plan's §1.2):

| Member | Why it is not Step-0-safe | Real? |
|---|---|---|
| databases/redis | lockstep with the held siblings (same image, same target) | Mechanical; the canary leg is still useful (only AOF instance) |
| superset-redis-official, paperless-redis, affine-redis, open-webui sidecar | lockstep only | Mechanical, but each leg carries a real consumer re-attach gate |
| tube-archivist-redis | lockstep; also the one persistent RDB with a durable app value (`ta:cookie`) | **Yes** for the data gate; the old plan's dump.rdb copy + cookie gate are reinstated |
| immich-redis | `*immich*`: "Immich server applies forward-only DB migrations ... dump + scratch-restore proof first" | **No, inherited from immich-server by the glob.** immich-redis holds no database and no schema: it is a non-persistent BullMQ queue (premise `immich-redis-non-persistent`; 66 keys, 19 blocking workers on 2026-11-02). A redis swap runs no Immich code and no migration. Real cost: queued/active jobs are dropped (re-runnable from the admin Jobs page), interruption not data loss (SD-11). No dump is taken because there is nothing to dump. Repo correction §6.1 |
| sure-redis | `*sure-redis*`: swap silently empties the sidekiq-cron schedule | **Yes** (§1.4) |
| nextcloud-redis | `*nextcloud-redis*`: every user signed out, locks dropped | **Yes**, user impact; accepted interruption under SD-11 |

### 1.3 Nextcloud redis auth path (unchanged by this plan)

The container command is an `sh -c` wrapper that exits if `REDIS_PASSWORD` is empty and runs
`redis-server --save "" --appendonly no --requirepass "$REDIS_PASSWORD"`; both `REDIS_PASSWORD`
and `REDISCLI_AUTH` come from the nextcloud-config Secret; a NetworkPolicy admits only
Nextcloud app/cronjob pods and `nextcloud-notify-push`. The image swap touches none of these,
so the password path survives by construction; §4 leg 9 proves it (auth round trip AND an
unauthenticated `NOAUTH` control; the pre-roll pair read `NOAUTH Authentication required. /
PONG` on 2026-11-02).

### 1.4 The trap this plan exists to catch: Sure's cron schedule

`sure-redis` is non-persistent. Sure's recurring jobs (bank sync, market data, cleanups:
`SCARD cron_jobs:default` = **11** on 2026-11-02) live ONLY in that redis and are written there
ONLY at Sidekiq startup (sidekiq-cron 2.3.0, `lib/sidekiq/cron/schedule_loader.rb`,
`config.on(:startup) { ... load_schedule }`; Sure's `AutoSyncScheduler.sync!` is likewise an
`on(:startup)` hook). Swapping the redis under a running `sure-worker` leaves a healthy worker
with an **empty schedule**: no error, no alert, pods Ready. Leg 7 restarts `sure-worker` after
the new redis is Ready and §4 asserts the count returns to 11.

### 1.5 open-webui leg (sidecar only)

Only the sidecar changes. It runs the image defaults (no `command`, no volume, RDB snapshots to
the container filesystem; premise `open-webui-redis-default-config`) and holds websocket/pubsub
state (7 keys, 13 app connections on 2026-11-02). Upstream evidence for in-process re-attach
(open-webui `v0.12.3`, `backend/open_webui/socket/main.py`, read 2026-10-25; unchanged
structure expected in 0.12.5 but NOT re-read): the websocket manager is
`socketio.AsyncRedisManager`, and `redis_event_listener()` runs `pubsub.subscribe`/`listen()`
inside a `while True` that catches every exception, logs `Redis event listener failed.
Retrying.`, sleeps `REDIS_PUBSUB_RECONNECT_INTERVAL` and doubles it up to
`REDIS_PUBSUB_MAX_RECONNECT_INTERVAL`. That is source reading, not a measurement on this
cluster, so §4 leg 4 measures it (client count returns) and gives the fallback
(`kubectl rollout restart sts/open-webui -n ai`: image and DB unchanged, so safe, but it ends
sessions on that pod briefly). The app is **v0.12.5** (commit ab0c0636); the old premise that
open-webui is "held on cooldown for 0.12.4" is stale and removed.

### 1.6 affine-redis (new leg, 8.10.2 -> 8.10.3)

affine-redis is a non-persistent BullMQ store (`--save "" --appendonly no`, Recreate, no volume):
8 blocking workers (`affine_job:*` queues) and 30 keys in db4 on 2026-11-02. Unlike Sure, a wipe
**self-heals**: read from the live app bundle (`/app/dist/main.js`, affine 0.27.4), the repeating
jobs are seeded by in-process `@Cron(EVERY_30_SECONDS)` handlers (`scheduleFindEmptySummaryDocs`,
`scheduleRecordPendingDocUpdatesCount`) that `job.add(..., {jobId: ...})` every 30 s, and a
finished repeat job re-adds itself through `handleJobReturn`. So no consumer restart is planned;
the gate (§4 leg 3) waits for the workers and the db4 keyspace to come back, with a
`rollout restart deploy/affine` fallback (Recreate, state in affine-pg). 8.10.2 is the in-cluster
proof of the same server line for the other members.

### 1.7 Members (re-measured 2026-11-02; redis_version 8.10.1 except affine 8.10.2)

| Leg | Instance | Persistence | Holds | Consumers | Restart cost |
|---|---|---|---|---|---|
| 1 | databases/redis | **AOF on PVC** | nothing (0 keys, 1 client = our own cli) | none | none: canary for the persisted-load path |
| 2 | databases/superset-redis-official | none, `requirepass` | celery broker + results (1444 keys, 15 clients) | superset-worker, superset-celerybeat | in-flight celery results lost; reconnect in-process (celery `inspect ping` pong now) |
| 3 | office/affine-redis | none | BullMQ queues (db4, 30 keys, 8 `bzpopmin` workers) | affine | queued jobs dropped; cron re-seeds in <= 30 s (§1.6) |
| 4 | ai/open-webui-redis (sidecar) | RDB defaults, no volume | websocket/pubsub (7 keys, 13 app connections) | open-webui-0 | brief pubsub gap; app NOT rolled |
| 5 | download/tube-archivist-redis | **RDB on PVC** | celery broker + **durable app state** (`ta:cookie`, no TTL; 23 keys, dump.rdb 6188 B) | tube-archivist | none if dump.rdb reloads |
| 6 | media/immich-redis | none | BullMQ queues (66 keys) | immich-server (19 blocking workers) | queued/active jobs dropped; workers reconnect in-process |
| 7 | office/sure-redis | none | sidekiq queues + **cron schedule** + Rails cache (761 keys) | sure-worker, sure-web | **schedule lost, worker restart required** |
| 8 | office/paperless-redis | none, `requirepass` | celery broker + channels (13 keys) | paperless-ngx | an in-flight consume task is lost, drain first |
| 9 | office/nextcloud-redis | none, `requirepass` | PHP sessions (58), mail cache, locks (534 keys) | nextcloud, notify-push, nextcloud-cron Jobs | **every logged-in user signed out** |

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) premises (read-only, fail closed)
.venv/bin/python3 runbooks/plan-premises.py redis-fleet-8.10.3 --require-premises

# b) target still current, cooldown satisfied, AMD64 MANIFEST digest unchanged since planning.
#    PASS prints AGE_OK ... and DIGEST_MATCH. Anything else is a STOP.
#    (The INDEX digest is printed for the record and saved for §4 v_fleet; it is NOT the pin:
#    the index was re-pushed 2026-10-29 when riscv64 was added, the amd64 manifest was not.)
WANT_AMD64=sha256:be7c1cada5a6eb1656adfa2635b99296af725881301b21f84f35a71fac072c7f
curl -s https://hub.docker.com/v2/repositories/library/redis/tags/8.10.3-alpine | WANT_AMD64="$WANT_AMD64" python3 -c '
import sys, json, os, datetime as d
try:
    j = json.load(sys.stdin); t = j["last_updated"]
    amd = [i["digest"] for i in j["images"] if i.get("architecture") == "amd64" and i.get("os") == "linux"]
except Exception:
    print("FETCH_FAILED redis"); sys.exit(1)
a = (d.datetime.now(d.timezone.utc) - d.datetime.fromisoformat(t.replace("Z", "+00:00"))).total_seconds() / 3600
print(("AGE_OK" if a >= 48 else "TOO_NEW"), round(a, 1), "h", t, "INDEX", j.get("digest"), "AMD64", amd)
open("/tmp/redis-fleet3-index", "w").write(str(j.get("digest")))
match = amd == [os.environ["WANT_AMD64"]]
print("DIGEST_MATCH" if match else "STOP_DIGEST_CHANGED amd64=%s" % amd)
sys.exit(0 if (a >= 48 and match) else 1)'
#    Measured 2026-11-02: "AGE_OK 99.9 h 2026-10-29T03:05:12.925646Z INDEX sha256:21090af9...2883537 AMD64 ['sha256:be7c1cad...072c7f']"
#    then "DIGEST_MATCH". Negative control (WANT_AMD64=sha256:deadbeef): prints "STOP_DIGEST_CHANGED amd64=[...]", exit 1.
#    FAILS as TOO_NEW (a re-push inside 48 h), STOP_DIGEST_CHANGED (the amd64 bits changed: re-read the compare in §1.2
#    and re-pin), or FETCH_FAILED. A changed INDEX alone with DIGEST_MATCH is benign (another architecture was pushed).

# c) nothing newer superseding the target. EXPECT EXACTLY: 8.10.3 -> 200, 8.10.4 -> 404, 8.11.0 -> 404
for t in 8.10.3-alpine 8.10.4-alpine 8.11.0-alpine; do
  curl -s -o /dev/null -w "$t -> %{http_code}\n" https://hub.docker.com/v2/repositories/library/redis/tags/$t
done
#    FAILS as 8.10.3 -> 404 (withdrawn) or a newer tag -> 200 (refresh this plan; do not apply a superseded target).

# d) Flux sane
flux get kustomizations -A | awk 'NR==1 || $5 != "True"'
flux get helmreleases -A   | awk 'NR==1 || $5 != "True"'
#    PASS: header line only (or unrelated rows you have explained).

# e) this plan is alone in its slot. Reads the scheduler's own conflict-aware table (~35 s); the old
#    `--open | grep ... || true` always matched this plan itself and could not fail. SLOT = the `window:` value
#    stamped on this plan after review (suggestion: sun-attended:2026-11-29).
SLOT=sun-attended:2026-11-29; ME=redis-fleet-8.10.3
python3 runbooks/maintenance-plan.py --json --skip-coverage | SLOT="$SLOT" ME="$ME" python3 -c '
import sys, json, os
d = json.load(sys.stdin)
got = d.get("scheduled", {}).get(os.environ["SLOT"])
if got is None: print("SLOT_NOT_FOUND", os.environ["SLOT"], "(plan not stamped, or wrong key)"); sys.exit(1)
others = [p for p in got if p != os.environ["ME"]]
ok = os.environ["ME"] in got and not others
print("SLOT_CLEAR" if ok else "SLOT_SHARED %s" % others); sys.exit(0 if ok else 1)'
#    PASS: SLOT_CLEAR. FAILS as SLOT_SHARED [...] (another plan stamped for the slot: STOP, see conflicts_with) or
#    SLOT_NOT_FOUND. Controls measured 2026-11-02: SLOT=sat-attended:2026-11-07 printed "SLOT_SHARED ['helm-drift-detection']";
#    SLOT=sun-attended:2026-12-06 printed SLOT_NOT_FOUND. Also confirm no kube-prometheus-stack bump landed at Step 0
#    tonight (flux get helmreleases -n monitoring kube-prometheus-stack): §4 reads Prometheus.

# f) BASELINE: record every number; §4 compares against them. [2026-11-02 values in brackets]
for x in databases/redis databases/superset-redis-official download/tube-archivist-redis media/immich-redis \
         office/nextcloud-redis office/paperless-redis office/sure-redis office/affine-redis ai/open-webui-redis; do
  ns=${x%/*}; d=${x#*/}
  echo "## $x $(kubectl exec -n $ns deploy/$d -- sh -c 'redis-cli info server | grep ^redis_version; redis-cli info clients | grep ^connected_clients; redis-cli dbsize' | tr '\r\n' '  ')"
done
#    [redis 1 client/0 keys · superset 15/1444 · tube-archivist 6/23 · immich 81/66 · nextcloud 14/534 ·
#     paperless 18/13 · sure 24/761 · affine 14/0 (its keys are in db4) · open-webui-redis 14/7] — floors-with-slack, not exact.
kubectl exec -n office deploy/sure-redis -- redis-cli scard cron_jobs:default                                 # [11]
kubectl exec -n download deploy/tube-archivist-redis -- redis-cli exists ta:cookie                            # [1]
kubectl exec -n media deploy/immich-redis -- sh -c 'redis-cli client list | grep -c "cmd=bzpopmin"'          # [19]
kubectl exec -n office deploy/affine-redis -- sh -c 'redis-cli client list | grep -c "cmd=bzpopmin"; redis-cli -n 4 dbsize'   # [8, 30]
kubectl exec -n ai deploy/open-webui-redis -- redis-cli client list | grep -c 'addr=10\.'                      # [13] app-side connections
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8080/api/version').read())" | tee /tmp/redis-fleet3-owui-version   # [{"version":"0.12.5",...}]
kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.startTime}{" restarts="}{.status.containerStatuses[0].restartCount}{"\n"}' | tee /tmp/redis-fleet3-owui0   # [2026-10-31T02:34:09Z restarts=0] — §4 leg 4 compares
# nextcloud-redis: AUTH control BEFORE the roll, so the post-roll NOAUTH result is not first-time evidence
kubectl exec -n office deploy/nextcloud-redis -- sh -c 'env -u REDISCLI_AUTH redis-cli ping; redis-cli ping' # [NOAUTH Authentication required. / PONG]
# AOF baseline on the canary
kubectl exec -n databases deploy/redis -- sh -c 'redis-cli info persistence | grep -E "^(aof_enabled|loading|aof_last_write_status|aof_last_bgrewrite_status):"; ls /data/appendonlydir'
#    [aof_enabled:1 loading:0 both statuses ok; appendonly.aof.1.base.rdb appendonly.aof.1.incr.aof appendonly.aof.manifest]

# f2) CONSUMER BASELINE: the "not restarted" criterion of every leg compares against this file.
T0=$(date -u +%s); echo "$T0" > /tmp/redis-fleet3-T0; echo "T0=$T0"
BASE=/tmp/redis-fleet3-consumers-$T0.txt
# Shell state does NOT survive separate tool calls: in every later call run
#   T0=$(cat /tmp/redis-fleet3-T0); BASE=/tmp/redis-fleet3-consumers-$T0.txt
# and re-define the helpers (cons_snap, wait_img, v_floor, v_rt, v_cons, v_fleet, leg_commit).
cons_snap() {   # prints: ns/pod restartCount startTime, one line per consumer pod
  for x in databases/superset-worker databases/superset-celerybeat download/tube-archivist media/immich-server \
           office/paperless-ngx office/nextcloud office/sure-web office/affine; do
    ns=${x%/*}; d=${x#*/}
    sel=$(kubectl get deploy -n $ns $d -o json | python3 -c 'import sys,json; print(",".join(f"{k}={v}" for k,v in json.load(sys.stdin)["spec"]["selector"]["matchLabels"].items()))')
    kubectl get pod -n $ns -l "$sel" -o json | python3 -c '
import sys, json
for p in json.load(sys.stdin)["items"]:
    if p["metadata"].get("deletionTimestamp") or p["status"].get("phase") != "Running": continue
    r = sum(c.get("restartCount", 0) for c in p["status"].get("containerStatuses", []))
    print(sys.argv[1] + "/" + p["metadata"]["name"], r, p["status"]["startTime"])' "$ns"
  done
}
cons_snap | tee "$BASE"; [ "$(wc -l < "$BASE" | tr -d ' ')" -ge 8 ] || { echo "BASELINE_INCOMPLETE"; exit 1; }
#    >= 8 lines (one per consumer Deployment, measured 8 on 2026-11-02). An empty baseline would make v_cons pass unchecked.
#    sure-worker and open-webui-0 are deliberately NOT in the set (restarted on purpose / asserted by their own leg gates).

# g) backups fresh (< 26 h): ground truth is the newest Completed Backup CR
python3 runbooks/longhorn-backup-age.py tube-archivist-redis-data \
  $(kubectl get pvc -n databases redis-data -o jsonpath='{.spec.volumeName}') --max-hours 26 \
  || { echo "ABORT: a volume has no confirmed backup < 26h"; exit 1; }
#    PASS: two FRESH lines (measured 2026-11-02: both 7.8h FRESH via backup-cr), exit 0. FAILS as "ERROR: no Longhorn volume named ..."
#    (rc 2, measured with a bogus name) or a STALE line. NB: pass the PV name for databases/redis-data, not the PVC name.
#    (Daily job: CronJob storage/daily-backup-all-volumes, schedule "0 23 * * *"; the RecurringJob owns it.)

# h) drain checks: record; each is re-run immediately before its own leg.
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- celery --app paperless inspect active 2>&1 | tail -5
kubectl exec -n download deploy/tube-archivist -- sh -c 'cd /app && celery -A task inspect active 2>&1 | tail -5'
#    PASS: "- empty -" for each node (both read empty on 2026-11-02). A running consume/download task means WAIT, not proceed.

# i) Prometheus reachable for §4 (the controls read it)
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s -G http://127.0.0.1:9090/api/v1/query --data-urlencode 'query=count(kube_pod_container_status_restarts_total{namespace="office"})' | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print("PROM_OK" if r and float(r[0]["value"][1])>0 else "PROM_EMPTY")'
kill $PF 2>/dev/null

# j) open-webui: git and the live StatefulSet agree on the APP tag, so leg 4's HelmRelease upgrade cannot roll the app.
GIT=$(grep -E '^[[:space:]]*tag:[[:space:]]*v[0-9]' kubernetes/apps/ai/open-webui/app/helmrelease.yaml | awk '{print $2}')
LIVE=$(kubectl get sts -n ai open-webui -o jsonpath='{.spec.template.spec.containers[0].image}' | sed 's/.*://')
echo "git=[$GIT] live=[$LIVE]"; if [ -n "$GIT" ] && [ "$GIT" = "$LIVE" ]; then echo OWUI_APP_IN_SYNC; else echo STOP_OWUI_APP_DRIFT; fi
#    PASS: OWUI_APP_IN_SYNC (measured 2026-11-02: git=[v0.12.5] live=[v0.12.5]). FAILS as STOP_OWUI_APP_DRIFT (an open-webui bump is
#    merged but not rolled: leg 4 would roll the app too; let it settle first). The grep matches exactly one line (the app tag).
```

Proceed only if (a) all premises PASS, (b) AGE_OK + DIGEST_MATCH, (c) 200/404/404, (d) clean,
(e) SLOT_CLEAR, (f) the pre-roll NOAUTH/PONG pair, AOF baseline and schedule 11, (g) FRESH x2,
(i) PROM_OK, (j) OWUI_APP_IN_SYNC. For (h), proceed per leg when that leg's drain check is empty.
**Announce** the Nextcloud sign-out before starting (the policy rule's attended-slot condition).

Optional silence (SOP §4 Step 1), one per namespace, 2 h TTL. Silences affect only Alertmanager
notifications; the §4 alert gates read Prometheus `/api/v1/alerts`, which a silence does not change.

## 3. Steps (GitOps, one commit per leg, in this order)

Order = ascending blast radius; each leg's §4 gates must PASS before the next leg starts. Every
leg is its own commit so a failure reverts one consumer. Do NOT `flux reconcile` by hand: the
webhook applies it. Step 0 of the window (safe-update apply) runs first as always; it cannot touch
these nine (all are PLAN lane via lockstep).

```bash
cd /Users/mu/code/cberg-home-nextgen
leg_commit() {   # needs LEG, FILE, SUBJ set; message file unique (shared worktree). Append the executing agent's
                 # attribution trailer to the message per the session's commit rules.
  local MSG; MSG=$(mktemp /tmp/redis-fleet3-leg$LEG.XXXXXX)
  printf '%s\n\n%s\n' "$SUBJ" "Plan redis-fleet-8.10.3, leg $LEG." > "$MSG"
  git diff -- "$FILE"                  # must be exactly the one-line diff shown for the leg
  git commit --only "$FILE" -F "$MSG" || { echo COMMIT_FAILED; return 1; }
  [ "$(git log -1 --format=%s)" = "$SUBJ" ] || { echo "SUBJECT_MISMATCH — amend before push"; return 1; }
  git show --stat HEAD                 # exactly one file
  git push && rm -f "$MSG"
}
wait_img() {   # wait_img <ns> <deploy>/<name> <expected spec image>  (zsh-safe: no variable named `path`)
  local ns=$1 obj=$2 want=$3 i got
  for i in $(seq 1 30); do
    got=$(kubectl get -n $ns $obj -o jsonpath='{.spec.template.spec.containers[0].image}')
    [ "$got" = "$want" ] && kubectl rollout status -n $ns $obj --timeout=180s && echo "ROLLED $obj" && return 0
    sleep 10
  done
  echo "NOT_ROLLED $obj (spec=$got)"; return 1
}
```

Tag edits were dry-run on scratch copies of every target file on macOS (BSD sed), 2026-11-02; the
diff lines shown are that output.

### Leg 1: databases/redis (canary: AOF-persistent, no consumers)

```bash
sed -i '' 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.1-alpine$/\18.10.3-alpine/' kubernetes/apps/databases/redis/app/helmrelease.yaml
#   32c32
#   <               tag: 8.10.1-alpine
#   >               tag: 8.10.3-alpine
LEG=1 FILE=kubernetes/apps/databases/redis/app/helmrelease.yaml
SUBJ="chore(redis): databases/redis 8.10.1-alpine -> 8.10.3-alpine (plan redis-fleet-8.10.3 leg 1)"
leg_commit
wait_img databases deploy/redis redis:8.10.3-alpine
```
Then §4 leg 1.

### Leg 2: databases/superset-redis-official

```bash
sed -i '' 's/^\([[:space:]]*image:[[:space:]]*redis:\)8\.10\.1-alpine$/\18.10.3-alpine/' kubernetes/apps/databases/superset/app/redis-deployment.yaml
#   37c37
#   <         image: redis:8.10.1-alpine
#   >         image: redis:8.10.3-alpine
LEG=2 FILE=kubernetes/apps/databases/superset/app/redis-deployment.yaml
SUBJ="chore(superset): redis 8.10.1-alpine -> 8.10.3-alpine (plan redis-fleet-8.10.3 leg 2)"
leg_commit
wait_img databases deploy/superset-redis-official redis:8.10.3-alpine
```

### Leg 3: office/affine-redis (the only member on 8.10.2; sed anchored on 8.10.2)

```bash
sed -i '' 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.2-alpine$/\18.10.3-alpine/' kubernetes/apps/office/affine/app/redis-helmrelease.yaml
#   36c36
#   <               tag: 8.10.2-alpine
#   >               tag: 8.10.3-alpine
LEG=3 FILE=kubernetes/apps/office/affine/app/redis-helmrelease.yaml
SUBJ="chore(affine): redis 8.10.2-alpine -> 8.10.3-alpine (plan redis-fleet-8.10.3 leg 3)"
leg_commit
wait_img office deploy/affine-redis redis:8.10.3-alpine
```

### Leg 4: ai/open-webui, redis sidecar tag ONLY (chart 17.0.0 and app v0.12.5 untouched)

No sqlite pre-copy and no alembic assertion are needed: the app image and DB are not touched.
Two substitutions in one file (the comment line keeps the file honest):
```bash
sed -i '' -e 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.1-alpine$/\18.10.3-alpine/' \
          -e 's/ 8\.10\.1-alpine is$/ 8.10.3-alpine is/' kubernetes/apps/ai/open-webui/app/helmrelease.yaml
#   100c100
#   <       # only — no persistence, no ACL/auth, no modules. 8.10.1-alpine is
#   >       # only — no persistence, no ACL/auth, no modules. 8.10.3-alpine is
#   106c106
#   <           tag: 8.10.1-alpine
#   >           tag: 8.10.3-alpine
#   (`tag: v0.12.5` at the app image is NOT matched: it has no 8.10.1 text)
LEG=4 FILE=kubernetes/apps/ai/open-webui/app/helmrelease.yaml
SUBJ="chore(open-webui): redis sidecar 8.10.1-alpine -> 8.10.3-alpine (plan redis-fleet-8.10.3 leg 4)"
leg_commit
wait_img ai deploy/open-webui-redis redis:8.10.3-alpine
```
(open-webui-redis is `RollingUpdate 25%`: a new pod may briefly coexist with the old; harmless for an
ephemeral pubsub store with no volume.) The Helm release moves from revision 60 to 61.

### Leg 5: download/tube-archivist-redis (persistent RDB)

Re-run the TA drain check from §2 h (must be empty). Then record the pre-swap key count and copy
the snapshot out (read-only against the pod):
```bash
kubectl exec -n download deploy/tube-archivist-redis -- redis-cli dbsize | tee /tmp/redis-fleet3-ta-pre     # [23]
B=/tmp/ta-dump-$(date +%Y%m%d_%H%M%S).rdb
kubectl exec -n download deploy/tube-archivist-redis -- cat /data/dump.rdb > "$B"
LIVE=$(kubectl exec -n download deploy/tube-archivist-redis -- sh -c 'wc -c < /data/dump.rdb' | tr -d ' ')
echo "live=$LIVE copy=$(wc -c < "$B" | tr -d ' ') file=$B"     # PASS: equal and > 0 (6188 on 2026-11-02)
sed -i '' 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.1-alpine$/\18.10.3-alpine/' kubernetes/apps/download/tube-archivist/app/redis-helmrelease.yaml
#   39c39
#   <               tag: 8.10.1-alpine
#   >               tag: 8.10.3-alpine
LEG=5 FILE=kubernetes/apps/download/tube-archivist/app/redis-helmrelease.yaml
SUBJ="chore(tube-archivist): redis 8.10.1-alpine -> 8.10.3-alpine (plan redis-fleet-8.10.3 leg 5)"
leg_commit
wait_img download deploy/tube-archivist-redis redis:8.10.3-alpine
```
The `Recreate` sends SIGTERM; with `save` configured redis writes a final snapshot on shutdown and
the new pod loads it. (The copy is the byte-exact pre-change snapshot for the §5 restore path. The
dump on the PVC may lag live state by up to an hour; the copy is a fallback, not the primary.)

### Leg 6: media/immich-redis

```bash
sed -i '' 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.1-alpine$/\18.10.3-alpine/' kubernetes/apps/media/immich/app/redis-helmrelease.yaml
#   40c40
#   <               tag: 8.10.1-alpine
#   >               tag: 8.10.3-alpine
LEG=6 FILE=kubernetes/apps/media/immich/app/redis-helmrelease.yaml
SUBJ="chore(immich): redis 8.10.1-alpine -> 8.10.3-alpine (plan redis-fleet-8.10.3 leg 6)"
leg_commit
wait_img media deploy/immich-redis redis:8.10.3-alpine
```

### Leg 7: office/sure-redis, THEN restart sure-worker

```bash
sed -i '' 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.1-alpine$/\18.10.3-alpine/' kubernetes/apps/office/sure/app/redis-helmrelease.yaml
#   36c36
#   <               tag: 8.10.1-alpine
#   >               tag: 8.10.3-alpine
LEG=7 FILE=kubernetes/apps/office/sure/app/redis-helmrelease.yaml
SUBJ="chore(sure): redis 8.10.1-alpine -> 8.10.3-alpine (plan redis-fleet-8.10.3 leg 7)"
leg_commit
wait_img office deploy/sure-redis redis:8.10.3-alpine

# The schedule is now EMPTY (§1.4). Positive control for the §4 gate:
kubectl exec -n office deploy/sure-redis -- redis-cli scard cron_jobs:default     # expect 0
# Re-register it: restart the worker ONCE, only after the new redis is Ready.
# (The one imperative step: there is no GitOps way to order a restart AFTER another Deployment's
# rollout; same pattern as docs/sops/secret-rotation.md consumer roll. maxSurge 0 — premise sure-worker-surge-zero.)
kubectl rollout restart deploy/sure-worker -n office
kubectl rollout status deploy/sure-worker -n office --timeout=300s
```

### Leg 8: office/paperless-redis

Re-run the paperless drain check from §2 h (must be `- empty -`); also confirm the broker queue is empty:
```bash
kubectl exec -n office deploy/paperless-redis -- redis-cli llen celery     # PASS: 0 (measured 0 on 2026-11-02)
sed -i '' 's/^\([[:space:]]*image:[[:space:]]*redis:\)8\.10\.1-alpine$/\18.10.3-alpine/' kubernetes/apps/office/paperless-ngx/app/redis-deployment.yaml
#   37c37
#   <         image: redis:8.10.1-alpine
#   >         image: redis:8.10.3-alpine
LEG=8 FILE=kubernetes/apps/office/paperless-ngx/app/redis-deployment.yaml
SUBJ="chore(paperless): redis 8.10.1-alpine -> 8.10.3-alpine (plan redis-fleet-8.10.3 leg 8)"
leg_commit
wait_img office deploy/paperless-redis redis:8.10.3-alpine
```

### Leg 9: office/nextcloud-redis (last; signs every user out)

Announce first. The password, wrapper and NetworkPolicy are NOT edited: only the image line
changes, so `requirepass` is re-applied by the same wrapper from the same Secret item (never print
it). Pick a moment right AFTER a `nextcloud-cron` Job completed (schedule `*/5`), so the next tick
lands on the new redis:
```bash
kubectl get jobs -n office --sort-by=.metadata.creationTimestamp | grep nextcloud-cron | tail -2
sed -i '' 's/^\([[:space:]]*image:[[:space:]]*redis:\)8\.10\.1-alpine$/\18.10.3-alpine/' kubernetes/apps/office/nextcloud/app/redis-deployment.yaml
#   52c52
#   <         image: redis:8.10.1-alpine
#   >         image: redis:8.10.3-alpine
LEG=9 FILE=kubernetes/apps/office/nextcloud/app/redis-deployment.yaml
SUBJ="chore(nextcloud): redis 8.10.1-alpine -> 8.10.3-alpine (plan redis-fleet-8.10.3 leg 9)"
leg_commit
wait_img office deploy/nextcloud-redis redis:8.10.3-alpine
```

## 4. Verification (per leg, before the next leg starts)

`PONG` and Ready are what an EMPTY redis nobody talks to also shows, so each leg's contents gate is
the consumer's own state reappearing in the new server, and each names what it prints when it fails
(`docs/sops/verification-contents-not-shape.md`).

**Floor for every leg** (shape only: proves the new binary runs, nothing more):
```bash
v_floor() {   # v_floor <ns> <deploy> — selects pods by the Deployment's OWN selector
  local ns=$1 d=$2 sel             # (a name-prefix match would also catch redisinsight-* for "redis")
  sel=$(kubectl get deploy -n $ns $d -o json | python3 -c 'import sys,json; print(",".join(f"{k}={v}" for k,v in json.load(sys.stdin)["spec"]["selector"]["matchLabels"].items()))')
  kubectl get pod -n $ns -l "$sel" -o json | python3 -c '
import sys, json
ps = [p for p in json.load(sys.stdin)["items"]
      if p["status"].get("phase") == "Running" and not p["metadata"].get("deletionTimestamp")]
imgs = sorted({c["image"] for p in ps for c in p["status"].get("containerStatuses", [])})
print("PODS", len(ps), imgs)
ok = len(ps) == 1 and imgs == ["docker.io/library/redis:8.10.3-alpine"]
print("FLOOR_OK" if ok else "FLOOR_FAIL"); sys.exit(0 if ok else 1)' \
  && kubectl exec -n $ns deploy/$d -- redis-cli info server | grep -i '^redis_version'
}
# PASS: "PODS 1 ['docker.io/library/redis:8.10.3-alpine']", FLOOR_OK, "redis_version:8.10.3".
# FAILS as PODS 2 (old pod still serving), an 8.10.1/8.10.2 status image (the live form is
# docker.io/library/redis:8.10.1-alpine, measured 2026-11-02), or redis_version:8.10.1/8.10.2.
```

Round trip (scratch db 15, 60 s TTL). FAILS as `(nil)` / `NOAUTH` / connection refused instead of `ok`:
```bash
v_rt() { kubectl exec -n $1 deploy/$2 -- sh -c 'redis-cli -n 15 set __plan_verify ok EX 60 >/dev/null; redis-cli -n 15 get __plan_verify; redis-cli -n 15 del __plan_verify >/dev/null'; }
```
(superset, paperless and nextcloud carry `REDISCLI_AUTH` in the container env, so the same command
authenticates there; `env -u REDISCLI_AUTH redis-cli ping` prints `NOAUTH Authentication required.`
on superset and paperless too, measured 2026-11-02.)

Consumers NOT restarted (end of EVERY leg). PASS `CONSUMERS_UNCHANGED`; FAILS as
`CONSUMERS_CHANGED` with the diff lines (a recreated pod or a raised restartCount):
```bash
v_cons() { cons_snap > /tmp/redis-fleet3-consumers-now.txt; if diff "$BASE" /tmp/redis-fleet3-consumers-now.txt; then echo CONSUMERS_UNCHANGED; else echo CONSUMERS_CHANGED; fi; }
```
Non-zero control: two snapshots across the 2026-09-27 node roll differ on every line (all consumers
carried new startTimes), so the diff is not structurally blind. If a consumer is restarted
deliberately under a leg's fallback, record it and re-baseline (`cons_snap > "$BASE"`) before the
next leg.

### CONTENTS ASSERTIONS, per leg

**Leg 1: databases/redis.** `v_floor databases redis; v_rt databases redis`, then the AOF was
loaded and is still being written:
```bash
kubectl exec -n databases deploy/redis -- sh -c 'redis-cli info persistence | grep -E "^(aof_enabled|loading|aof_last_write_status|aof_last_bgrewrite_status):"; ls /data/appendonlydir'
```
PASS: `aof_enabled:1`, `loading:0`, both statuses `ok`, and `appendonly.aof.manifest` present (all
read this way on 8.10.1, 2026-11-02). FAILS as `aof_enabled:0` (config lost), an `err` status, or an
empty dir (AOF not on the PVC any more). The AOF holds 0 keys, so this leg proves the AOF LOAD PATH
and config survive, not data survival; leg 5 (tube-archivist, durable key) is the persisted-DATA
proof. Then `v_cons`.

**Leg 2: superset.** `v_floor databases superset-redis-official; v_rt databases superset-redis-official`, then
the celery worker reconnected in-process and re-declared its queue:
```bash
kubectl exec -n databases deploy/superset-worker -c superset -- celery --app=superset.tasks.celery_app:app inspect ping 2>&1 | grep -c pong   # PASS: >= 1 (1 on 2026-11-02)
kubectl exec -n databases deploy/superset-redis-official -- redis-cli exists _kombu.binding.celery                                       # PASS: 1
kubectl exec -n databases deploy/superset-redis-official -- redis-cli info clients | grep ^connected_clients                            # PASS: >= 8 [15]
```
FAILS as `inspect ping` printing `Error: No nodes replied within time constraint` (0 pong), `exists`
-> 0 (worker not bound to this broker), clients 1-2. Then `v_cons`.

**Leg 3: affine.** `v_floor office affine-redis; v_rt office affine-redis`, then the BullMQ
workers re-attached and the queue keyspace is back (db4 holds the `affine_job:*` keys; a freshly
started redis has 0 there). Poll up to 3 min:
```bash
for i in $(seq 1 18); do
  W=$(kubectl exec -n office deploy/affine-redis -- sh -c 'redis-cli client list | grep -c "cmd=bzpopmin"')
  K=$(kubectl exec -n office deploy/affine-redis -- redis-cli -n 4 dbsize | tr -d ' ')
  echo "t=$((i*10))s blocking_workers=$W db4_keys=$K"; [ "$W" -ge 6 ] && [ "$K" -ge 10 ] && { echo AFFINE_GATE_PASS; break; }; sleep 10
done
[ "$W" -ge 6 ] && [ "$K" -ge 10 ] || echo AFFINE_GATE_FAIL
#   PASS: workers >= 6 [8] AND db4 keys >= 10 [30]. FAILS as workers 0 / db4_keys 0 (the app did not reconnect, or its
#   cron did not re-seed the queues) -> `kubectl rollout restart deploy/affine -n office` ONCE (Recreate; state lives in
#   affine-pg), re-baseline `cons_snap > "$BASE"`, re-run this loop; still failing -> §5.
kubectl port-forward -n office svc/affine 13010:3010 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s http://127.0.0.1:13010/info; echo      # PASS: JSON containing "AFFiNE" ("compatibility":"0.27.4" on 2026-11-02). FAILS as empty / connection refused
kill $PF 2>/dev/null
```
Then `v_cons`.

**Leg 4: open-webui (sidecar only).** `v_floor ai open-webui-redis; v_rt ai open-webui-redis`, then
```bash
kubectl exec -n ai open-webui-0 -c open-webui -- python3 -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8080/api/version').read())" | diff - /tmp/redis-fleet3-owui-version && echo OWUI_VERSION_UNCHANGED
#   PASS: OWUI_VERSION_UNCHANGED (same version as the §2 f baseline, 0.12.5). FAILS as a diff / connection error (app rolled or down).
kubectl get pod -n ai open-webui-0 -o jsonpath='{.status.startTime}{" restarts="}{.status.containerStatuses[0].restartCount}{"\n"}' | diff - /tmp/redis-fleet3-owui0 && echo OWUI_APP_UNCHANGED
#   PASS: OWUI_APP_UNCHANGED (the HR upgrade re-rendered identical StatefulSet values). FAILS as a diff: the app pod was
#   recreated — acceptable only if /api/version above is unchanged (record it); a restart-count increase is a FAIL.
for i in $(seq 1 12); do
  C=$(kubectl exec -n ai deploy/open-webui-redis -- redis-cli client list | grep -c 'addr=10\.')
  echo "t=$((i*10))s app_connections=$C"; [ "$C" -ge 8 ] && { echo OWUI_REATTACHED; break; }; sleep 10
done; [ "$C" -ge 8 ] || echo OWUI_NOT_REATTACHED
#   PASS: OWUI_REATTACHED within 2 min (baseline 13 app connections on 2026-11-02; floor 8, since a fresh redis starts at 0
#   so the floor cannot pass by itself). FAILS as OWUI_NOT_REATTACHED / app_connections=0: the app did not reconnect
#   in-process -> `kubectl rollout restart sts/open-webui -n ai` once (image/DB unchanged), re-run the loop; still failing -> §5.
```
CONTENTS ASSERTION, attended: sign in, open an existing chat (its history renders; an empty chat list
for an existing user is a FAIL), send one message to an Ollama model and receive a streamed reply
(the websocket -> redis path).

**Leg 5: tube-archivist.** `v_floor download tube-archivist-redis; v_rt download tube-archivist-redis`, then
the persisted state came back:
```bash
PRE=$(cat /tmp/redis-fleet3-ta-pre); : "${PRE:?pre-swap dbsize file missing}"
C=$(kubectl exec -n download deploy/tube-archivist-redis -- redis-cli exists ta:cookie | tr -d ' ')
POST=$(kubectl exec -n download deploy/tube-archivist-redis -- redis-cli dbsize | tr -d ' ')
kubectl exec -n download deploy/tube-archivist-redis -- sh -c 'redis-cli info persistence | grep -E "^(loading|rdb_last_bgsave_status):"'
echo "cookie=$C pre=$PRE post=$POST floor=$((PRE*7/10))"
if [ "$C" = 1 ] && [ "$POST" -ge $((PRE*7/10)) ]; then echo TA_STATE_RESTORED; else echo TA_STATE_LOST; fi
#   PASS: TA_STATE_RESTORED (cookie=1, post >= 70% of the pre-swap count [pre 23 -> floor 16]), loading:0, rdb_last_bgsave_status:ok.
#   The old fixed ">= 55" gate is dropped: the key count drifted 65 -> 23 as TTL'd handle-search keys expired, so a fixed number
#   was both stale and unmeasured. A relative floor keeps the gate able to fail: a dump.rdb that did NOT load leaves ~3-6 fresh
#   celery keys, far below 16, and cookie=0.
#   FAILS as TA_STATE_LOST / cookie=0 -> §5 leg-5 restore.
kubectl exec -n download deploy/tube-archivist -- sh -c 'cd /app && celery -A task inspect ping 2>&1' | grep -c pong   # PASS: >= 1
```
Then `v_cons`.

**Leg 6: immich.** `v_floor media immich-redis; v_rt media immich-redis`, then BullMQ workers
re-attached to the new server. Poll up to 3 min:
```bash
for i in $(seq 1 18); do
  W=$(kubectl exec -n media deploy/immich-redis -- sh -c 'redis-cli client list | grep -c "cmd=bzpopmin"')
  S=$(kubectl exec -n media deploy/immich-redis -- sh -c 'redis-cli --scan --pattern "immich_bull:*:stalled-check" | wc -l' | tr -d ' ')
  echo "t=$((i*10))s blocking_workers=$W stalled_check_keys=$S"; [ "$W" -ge 15 ] && [ "$S" -ge 10 ] && { echo IMMICH_GATE_PASS; break; }; sleep 10
done
[ "$W" -ge 15 ] && [ "$S" -ge 10 ] || echo IMMICH_GATE_FAIL
#   PASS: workers >= 15 [19] and stalled-check keys >= 10 [19, three samples 2026-11-02]. Stalled-check keys carry a ~30 s TTL
#   (single samples read 6..19 on 2026-09-27), hence a poll with a floor.
#   FAILS as workers 0 (ioredis did not reconnect) -> `kubectl rollout restart deploy/immich-server -n media` ONCE,
#   re-baseline, re-run; still failing -> §5.
kubectl port-forward -n media svc/immich-server 12283:2283 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s http://127.0.0.1:12283/api/server/ping; echo    # PASS: {"res":"pong"}. FAILS as empty / connection refused
kill $PF 2>/dev/null
```
Attended (optional): Immich admin -> Jobs shows queues with workers; if a thumbnail or metadata job
was mid-flight at the swap, run "Missing" for it. Then `v_cons`.

**Leg 7: sure.** `v_floor office sure-redis; v_rt office sure-redis`, then the schedule is
re-registered and a worker heartbeats:
```bash
kubectl exec -n office deploy/sure-redis -- redis-cli scard cron_jobs:default    # PASS: 11 (§2 f). FAILS as 0: worker restart missing / did not load the schedule
kubectl exec -n office deploy/sure-redis -- redis-cli scard processes            # PASS: >= 1 (Sidekiq heartbeat) [1]. FAILS as 0
kubectl exec -n office deploy/sure-redis -- redis-cli exists cron_job:default:sync_all_accounts   # PASS: 1 [1] (AutoSyncScheduler on(:startup))
kubectl port-forward -n office svc/sure 18085:80 >/dev/null 2>&1 & PF=$!; sleep 5
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18085/up                # PASS: 200 (measured 200)
kill $PF 2>/dev/null
```
The positive control for the 11 is the `0` printed in §3 leg 7 before the restart; if that read 11
instead of 0, stop and find out why before trusting the gate. Then `v_cons`.

**Leg 8: paperless.** `v_floor office paperless-redis; v_rt office paperless-redis`, then the
consumer is bound to the new broker:
```bash
kubectl exec -n office deploy/paperless-ngx -c paperless-ngx -- celery --app paperless inspect ping 2>&1 | grep -c pong   # PASS: >= 1 (1 on 2026-11-02)
kubectl exec -n office deploy/paperless-redis -- redis-cli exists _kombu.binding.celery                                  # PASS: 1
```
Attended: drop one test PDF into the consume path per `docs/sops/paperless.md` (or re-run a pending
one) and confirm it becomes a document: the end-to-end job round-trip through this broker.
`inspect ping` alone does not prove a task is delivered. Then `v_cons`.

**Leg 9: nextcloud.** `v_floor office nextcloud-redis; v_rt office nextcloud-redis` (`v_rt`
authenticates through the container's `REDISCLI_AUTH`, so `ok` proves the password in the Secret
matches the one the server enforces), then the AUTH CONTROL pair:
```bash
kubectl exec -n office deploy/nextcloud-redis -- sh -c 'env -u REDISCLI_AUTH redis-cli ping'
#   PASS: "NOAUTH Authentication required." (the requirement survived the swap).
#   FAILS as PONG: the server came up unauthenticated (wrapper/args lost) — STOP, §5 leg 9.
#   Positive control: the same command printed NOAUTH on the 8.10.1 pod in §2 f.
kubectl exec -n office deploy/nextcloud-redis -- redis-cli ping    # PASS: PONG (auth'd). FAILS as NOAUTH: password mismatch with the Secret.
```
Notify-push reconnect: the absence grep is paired with a POSITIVE signal (its logs are normally
silent, so a clean log alone proves nothing). Run in ONE call (shell variables do not survive
separate calls):
```bash
SINCE=$(kubectl get pod -n office -l app=nextcloud-redis -o jsonpath='{.items[0].status.startTime}')   # new redis pod start = swap time
NPIP=$(kubectl get pod -n office -l app=nextcloud-notify-push -o jsonpath='{.items[0].status.podIP}')
echo "since=$SINCE notify-push-ip=$NPIP"
for i in $(seq 1 18); do
  C=$(kubectl exec -n office deploy/nextcloud-redis -- redis-cli client list | grep -c "addr=$NPIP:")
  echo "t=$((i*10))s notify_push_clients=$C"; [ "$C" -ge 1 ] && { echo NOTIFY_PUSH_CONNECTED; break; }; sleep 10
done; [ "$C" -ge 1 ] || echo NOTIFY_PUSH_NOT_CONNECTED
kubectl logs -n office deploy/nextcloud-notify-push --since-time="$SINCE" | grep -ciE 'NOAUTH|WRONGPASS|AUTH failed|connection refused'
#   PASS: NOTIFY_PUSH_CONNECTED within 3 min AND the grep prints 0. FAILS as NOTIFY_PUSH_NOT_CONNECTED or a non-zero grep.
#   If notify-push restarted itself on redis loss, the labelled lookup takes the NEW pod's IP.
```
HTTP + readiness:
```bash
kubectl port-forward -n office svc/nextcloud 18082:8080 >/dev/null 2>&1 & PF=$!; sleep 5
curl -s http://127.0.0.1:18082/status.php     # PASS: "installed":true,"maintenance":false (measured 2026-11-02, version 35.0.2.2)
kill $PF 2>/dev/null
kubectl get deploy -n office nextcloud-notify-push -o jsonpath='{.status.readyReplicas}{"\n"}'   # PASS: 1 within 3 min
#   FAILS as status.php empty or "maintenance":true; readyReplicas empty. (One self-restart of notify-push is expected; CrashLoop is not.)
```
CONTENTS ASSERTION (loosened to what was measured; the old `dbsize >= 10` had no evidence). On
2026-11-02 the 534 keys are 424 `mail_attachment_names` cache entries, 58 `PHPREDIS_SESSION:*`
sessions and ~50 misc cache/rate-limit/notify-push keys; how many of those one cron tick alone
rewrites was NOT measured (it needs a restart to observe). So the gate asserts only what can be
shown to come from live Nextcloud traffic, in three steps:
1. The first `nextcloud-cron` Job created after `$SINCE` completes (compare its `.metadata.creationTimestamp` to `$SINCE`,
   not just the newest line, or the previous Job's `1/1` passes for the wrong reason):
   `kubectl get jobs -n office --sort-by=.metadata.creationTimestamp | grep nextcloud-cron | tail -1` shows `1/1` COMPLETIONS
   (cron.php takes its file locks in this redis; a failed Job is the failure).
2. Then `kubectl exec -n office deploy/nextcloud-redis -- redis-cli dbsize` reads `>= 1`. A new
   server starts at 0, so 0 after a completed cron Job + the notify-push client means Nextcloud is not
   writing to this redis at all (FAILS as `0`).
3. Attended: sign in to Nextcloud and open one file, then
   `kubectl exec -n office deploy/nextcloud-redis -- sh -c 'redis-cli --scan --pattern "PHPREDIS_SESSION:*" | wc -l'`
   reads `>= 1` (baseline 58). FAILS as `0` after a successful sign-in (sessions are not reaching
   redis). Record the post-roll `dbsize` in the report: it becomes the measured baseline this plan lacked.

Then `v_cons` (nextcloud and sure-web pods unchanged; notify-push is not in the set).

### CONTROLS, window-wide

- CONTROL: **fleet uniformity.** All nine redis pods must run the same bytes. A mid-window tag
  re-push, or a node holding an older cached 8.10.3-alpine, would split the fleet while every
  per-leg gate stays green. Positive control: on 2026-11-02, before any leg, this printed
  `FLEET_IMAGE_SPLIT` with two distinct imageIDs (8x one digest, 1x another), so it is not blind.
  Run after leg 9: PASS `FLEET_IMAGE_UNIFORM` and `FLEET_MATCHES_PRECHECK_INDEX`. FAILS as
  `FLEET_IMAGE_SPLIT` (two digests: a re-push or stale cache; STOP and decide whether to re-pull the
  odd pod) or `FLEET_INDEX_DIFFERS_FROM_PRECHECK` (the tag moved since §2 b; re-run §2 b's amd64 check).

```bash
v_fleet() {
  for x in databases/redis databases/superset-redis-official download/tube-archivist-redis media/immich-redis office/nextcloud-redis \
           office/paperless-redis office/sure-redis office/affine-redis ai/open-webui-redis; do
    ns=${x%/*}; d=${x#*/}
    sel=$(kubectl get deploy -n $ns $d -o json | python3 -c 'import sys,json; print(",".join(f"{k}={v}" for k,v in json.load(sys.stdin)["spec"]["selector"]["matchLabels"].items()))')
    kubectl get pod -n $ns -l "$sel" -o json | python3 -c '
import sys, json
for p in json.load(sys.stdin)["items"]:
    if p["metadata"].get("deletionTimestamp") or p["status"].get("phase") != "Running": continue
    for c in p["status"].get("containerStatuses", []): print(c["imageID"])'
  done | sort | uniq -c | tee /tmp/redis-fleet3-fleet.txt
  if [ "$(wc -l < /tmp/redis-fleet3-fleet.txt | tr -d ' ')" = 1 ] && grep -q "^ *9 docker.io/library/redis@sha256:" /tmp/redis-fleet3-fleet.txt; then echo FLEET_IMAGE_UNIFORM; else echo FLEET_IMAGE_SPLIT; fi
  # guard: a missing/empty index file would make `grep -q ""` always match (reviewer reproduced it in zsh)
  if [ -s /tmp/redis-fleet3-index ] && grep -q "$(cat /tmp/redis-fleet3-index)" /tmp/redis-fleet3-fleet.txt; then echo FLEET_MATCHES_PRECHECK_INDEX; else echo FLEET_INDEX_DIFFERS_OR_UNRECORDED; fi
}
```

- CONTROL: metric `kube_pod_container_status_restarts_total` over the whole run (range = minutes
  since `T0`). PASS `NO_RESTARTS` or only `nextcloud-notify-push-*` (<= 2). FAILS as any other
  `RESTARTED <ns> <pod> <n>` line — explain it (predates T0 or unrelated by its logs) or treat as
  this plan's failure. The deliberate sure-worker roll creates a NEW pod (restartCount 0) and does not
  show. Non-zero control: the same expression with `[24h] > 0` returned rows on 2026-09-27.
  ```bash
  kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
  T0=$(cat /tmp/redis-fleet3-T0); M=$(( ( $(date -u +%s) - T0 ) / 60 + 5 ))
  curl -s -G http://127.0.0.1:9090/api/v1/query \
    --data-urlencode "query=increase(kube_pod_container_status_restarts_total{namespace=~\"databases|download|media|office|ai\"}[${M}m]) > 0" \
    | python3 -c '
import sys, json
r = json.load(sys.stdin)["data"]["result"]
for x in r: print("RESTARTED", x["metric"]["namespace"], x["metric"]["pod"], round(float(x["value"][1]), 1))
print("NO_RESTARTS") if not r else None'
  kill $PF 2>/dev/null
  ```
- CONTROL: each of the nine redis pods `kube_pod_status_ready{condition="true"}` = 1 at the end.
- CONTROL: alerts `SupersetRedisDown` (10 min after leg 2), `TubeArchivistPodRestarted` (after leg 5),
  `ImmichPodRestarted` + `ImmichRedisNotReady` (after leg 6), `SureRedisDown` + `SurePodRestarted`
  (10 min after leg 7) not firing. All six exist in `/api/v1/rules` with state inactive (measured
  2026-11-02); confirm LOADED below, because a rule Prometheus never loaded is silent forever.
  `SurePodRestarted` is expected to stay silent: `rollout restart` creates a NEW pod (restartCount 0),
  so it firing means a crash. There is no dedicated alert for databases/redis, affine, paperless,
  open-webui or nextcloud redis; those legs are covered by their own gates.
  ```bash
  kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
  curl -s http://127.0.0.1:9090/api/v1/rules | python3 -c '
import sys, json
names = {"SupersetRedisDown","TubeArchivistPodRestarted","ImmichPodRestarted","ImmichRedisNotReady","SureRedisDown","SurePodRestarted"}
got = {r["name"] for g in json.load(sys.stdin)["data"]["groups"] for r in g["rules"] if r.get("name") in names}
print("RULES_LOADED", len(got))'                       # PASS: RULES_LOADED 6 (fewer = NONE_FIRING below is not evidence)
  curl -s http://127.0.0.1:9090/api/v1/alerts | python3 -c '
import sys, json
names = {"SupersetRedisDown","TubeArchivistPodRestarted","ImmichPodRestarted","ImmichRedisNotReady","SureRedisDown","SurePodRestarted"}
a = [x for x in json.load(sys.stdin)["data"]["alerts"] if x["labels"].get("alertname") in names and x["state"] == "firing"]
print("FIRING", [(x["labels"]["alertname"], x["labels"].get("pod")) for x in a]) if a else print("NONE_FIRING")'
  kill $PF 2>/dev/null
  ```

Success = every leg's floor + round trip + contents assertion PASS, `CONSUMERS_UNCHANGED` after each
leg, `FLEET_IMAGE_UNIFORM`, and the controls clean.

## 5. Rollback

Per leg, newest first. Nothing forward-only happens in any leg: RDB/AOF format is unchanged
(RDB_VERSION 15 on both sides, §1.2) and no app or schema is touched (the open-webui leg is
sidecar-only). Seven of the nine instances are non-persistent, so a rollback is a revert plus the
same consumer re-attach work as the forward leg. The two durable ones (databases/redis AOF,
tube-archivist RDB) load the file the 8.10.3 server wrote with the 8.10.1 server; that is the
property to confirm, with the backups below as the last resort.

```bash
cd /Users/mu/code/cberg-home-nextgen
FILE=kubernetes/apps/media/immich/app/redis-helmrelease.yaml   # set to THAT leg's file (do not paste a placeholder)
SHA=$(git log -1 --format=%H -- "$FILE")
git show --stat $SHA          # confirm it is that leg's 8.10.3 commit (and ONLY that file)
MSG=$(mktemp /tmp/redis-fleet3-revert.XXXXXX); printf 'revert: %s\n' "$(git log -1 --format=%s $SHA)" > "$MSG"
git revert --no-commit $SHA && git commit --only "$FILE" -F "$MSG"
git log -1 --format=%s        # confirm it is YOUR revert subject
git show --stat HEAD          # exactly that one file
git push; rm -f "$MSG"
# then: wait_img <ns> deploy/<that redis> redis:8.10.1-alpine     (affine: redis:8.10.2-alpine)
```
Then re-run that leg's §4 CONTENTS ASSERTION against the reverted pod (`v_floor` will correctly print
FLOOR_FAIL because it expects 8.10.3; check `redis_version:` 8.10.1 / 8.10.2 instead). A rollback is
done only when the consumer is back on it.

Leg-specific additions:
- **Leg 7 (sure):** the revert swaps redis again, so the schedule is empty again:
  `kubectl rollout restart deploy/sure-worker -n office` once more, then assert
  `scard cron_jobs:default` = 11. Forgetting this is the one way a rollback here causes silent
  harm (no bank sync until the next worker restart).
- **Leg 5 (tube-archivist):** 8.10.1 loads the 8.10.3-written dump.rdb (same RDB_VERSION 15). If after
  either direction `exists ta:cookie` = 0 (snapshot not loaded): the only durable app value is the
  YouTube cookie, so re-import it in Tube Archivist's settings UI (operator); the celery keys
  regenerate. Last resort for the whole volume: restore `tube-archivist-redis-data` from the §2 g
  Longhorn backup per `docs/sops/backup.md` "Restore from Backup"; the local copy from §3 leg 5
  (`/tmp/ta-dump-*.rdb`) is the byte-exact pre-change snapshot to compare against.
- **Leg 1 (databases/redis, AOF):** if the reverted 8.10.1 pod does not load the AOF (`loading:1`
  never clears, or `aof_enabled:0`), the AOF holds 0 keys, so nothing is lost by recreating it;
  otherwise restore the volume behind pvc `databases/redis-data` from the §2 g backup.
- **Leg 4 (open-webui):** the revert is complete (sidecar has no volume, app/DB never touched). After
  it re-run the §4 leg-4 re-attach loop; if the app is stuck, `kubectl rollout restart sts/open-webui -n ai`.
  No sqlite restore path exists or is needed.
- **Leg 3 (affine):** revert, then re-run the §4 leg-3 loop; a `kubectl rollout restart deploy/affine -n office`
  is safe (Recreate, state in affine-pg).
- **Leg 9 (nextcloud-redis, auth path):** the revert swaps only the image line, so the wrapper, Secret
  and NetworkPolicy are identical on both sides. After it, assert the same checks as §4 leg 9 (NOAUTH
  unauth'd, PONG auth'd, notify-push CONNECTED). If the server is up but `PONG` fails with NOAUTH
  while auth'd, the Secret and the running server disagree:
  `kubectl rollout restart deploy/nextcloud-redis -n office` (re-reads the Secret); never disable
  `requirepass`. Sessions/locks are lost either way (non-persistent); users sign in again. Do not
  edit or print the Secret in a rollback.
- **Helm wedged `pending-upgrade`** on any app-template leg: `docs/sops/application-update.md` §11
  (`helm rollback <rel> <rev> -n <ns> --wait=false`, then `flux reconcile helmrelease -n <ns> <rel> --force`).
  Revisions on 2026-11-02 (chart app-template 5.3.0): redis 16, tube-archivist-redis 17, immich-redis 13,
  sure-redis 15, affine-redis 16, open-webui 60 (chart open-webui-17.0.0). Read them fresh at the
  window (helm-drift-detection / flux-oci-chart-sources may have moved them).

Cleanup after a successful window (not a rollback): `rm -f /tmp/ta-dump-*.rdb /tmp/redis-fleet3-*`.

## 6. Interference notes

- **Blast radius is strictly per leg**: each redis serves one app (CLIENT LIST). No shared storage,
  no gateway/DNS/CNI change. Two Longhorn PVCs are remounted by their own Recreate; no delete, so the
  storage-safety pre-flight is N/A.
- **Nextcloud users are signed out** at leg 9: announce; SD-11 would allow the nightly slot for that
  leg alone, but the sure schedule gate, the tube-archivist data gate and the attended checks keep the
  plan HUMAN-GATED and in an attended slot.
- **Window.** Suggestion `sun-attended:2026-11-29` (80 min against the 180-min schedulable Sunday
  budget); alternative `sat-attended:2026-11-28` does NOT fit (70-min budget). Do not use 11-07, 11-08,
  11-14, 11-15, 11-21, 11-22: each holds a plan in `conflicts_with` (helm-drift/otel-operator-0.26.1,
  etcd, python-fleet, longhorn, authentik, flux-oci-chart-sources). §2 e reads the scheduler and fails
  loudly if the slot is shared. The `window:` stamp was set at the operator GO (2026-11-02).
- **Same-night Prometheus consumers.** §4 reads Prometheus: a same-night `kube-prometheus-stack` bump
  (auto lane, no plan file, so it cannot be named in `conflicts_with`) would confound the controls.
  Check Step 0's applied list before leg 1 (§2 e note).
- **Order of work around Nextcloud:** the executed nextcloud-9.4.1 / whiteboard-2.1.2 plans no longer
  exist as files; any new Nextcloud chart/server plan filed before the window must be serialized BEFORE
  leg 9, never in the same hour.
- **Tube Archivist plans.** `tube-archivist-0.6.0` and `tube-archivist-elasticsearch-9.5.5` previously
  recorded that this fleet "no longer touches tube-archivist". That is no longer true (leg 5 restarts
  `download/tube-archivist-redis`; the TA app reconnects in-process). Their sequencing prose
  ("after redis-fleet-8.10.2 on 2026-11-29 has restarted this app") should now name this plan.
- **helm-drift-detection**: if it adds a field to every HelmRelease before this slot, the seds are
  unaffected (they touch only tag lines); the §5 revision numbers move.
- **Not in scope, same HelmReleases:** app-template chart bumps for redis / tube-archivist-redis /
  immich-redis / sure-redis / affine-redis, and any open-webui chart bump: serialize with this plan.
- **No reboot, no PVC/storage operation.**
- **Repo corrections found while planning (not made here — planner writes only plan files):**
  1. **Shared-image lockstep is coarser than the unit it protects (F-8792dba3).** `_apply_lockstep`
     treats nine independent redis Deployments as one "deployable unit" because they share an image
     and target, which froze six of them in PLAN with no planner from 10-27 to 11-02. This plan is
     correct either way (it carries all nine). If the operator narrows the lockstep to one HelmRelease/
     app, the six lockstep-only members could ride Step 0 again, but only AFTER this plan is re-scoped
     deliberately; do not narrow it while this plan is executing.
  2. **`*immich*` deny rule gives immich-redis a false hold reason** (`runbooks/auto-update-policy.yaml`):
     the glob also matches `immich-redis`, so every redis patch sends it to PLAN citing "dump +
     scratch-restore proof" for a store with no database and no persistence. Fix: add, ABOVE
     `*immich*` (first match wins), a `- match: "*immich-redis*"` rule with its own true reason
     (non-persistent BullMQ; swap drops queued jobs, re-runnable) and `max: patch`. Also check `*immich*`
     against `immich-machine-learning`.
  3. **README vs coverage on retargets.** README says KEEP the plan_id on a refresh; coverage names
     image-fleet groups `redis-fleet-<target>`, so every fleet retarget forks a plan_id and orphans the
     go/no-go. One of them should change (the GO RESET banner above is the cost of the current rule).
  4. **Premise output must not look like a credential assignment.** The superseded plans' premise
     `expect_exact: 'secret=... key=redis-password ...'` is what `security-check.py` reports as
     F-fe355b6d ("Credential-like pattern in history"; `_CRED_ASSIGNMENT` matches `secret=<value>`).
     The premise here uses `ref=` / `item=`. The same string still sits in the history and in the
     superseded `redis-fleet-8.10.2.md`; rewording that file's premise does not clear history, so the
     finding needs an explicit acceptance, not a code change.
  5. **`docs/sops/backup.md` / backup cron schedule.** The Longhorn backup CronJob
     `storage/daily-backup-all-volumes` runs at `0 23 * * *` (measured 2026-11-02), not 03:00 as
     CLAUDE.md and older plans say.
