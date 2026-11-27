---
plan_id: penpot-cache-9.1.4                # plan_id KEPT on a retarget (re-plan in place 2026-11-27); the id is
                                           # historical, the target below is 9.2.1. Renaming is not the planner's call.
component: penpot-cache
pr: 615                               # renovate "feat(container): update valkey/valkey ( 9.1.4 → 9.2.1 )", opened
                                      # 2026-11-26T04:55Z; one file (penpot-cache/app/helmrelease.yaml), CI green
                                      # (Flate Render Gate, Flux Local Diff x2, Labeler), but CONFLICTING: its base line
                                      # is `tag: "9.1.4"`, and main went back to 9.1.3 when Step 0 auto-reverted #561 on
                                      # 2026-11-27. Steps edit main directly; Renovate closes #615 once main carries 9.2.1.
                                      # Previous PR #561 (9.1.3 -> 9.1.4) is MERGED + REVERTED (56ed46904 / 11c586064).
kind: image
current: "9.1.3"                      # live 2026-11-27 02:49Z: deploy spec valkey/valkey:9.1.3, INFO server
                                      # valkey_version:9.1.3, pod penpot-cache-64989dfd55-qbwb5 imageID sha256:3add1a33...
                                      # (= registry index digest of 9.1.3), manifest line 39 `tag: "9.1.3"`
target: "9.2.1"
retargeted_from: "9.1.4"              # 2026-11-27 re-plan (needs_replan minor-or-major-drift); reasoning in §1
update_type: minor
risk: low                             # stateless cache (--save "" / --appendonly no, no PVC, DBSIZE 0), standalone,
                                      # one consumer app whose command set avoids every 9.2 behaviour change (§1);
                                      # 9.2.0 already ran ~10 min in prod on 2026-11-26 with 0 consumer restarts
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/penpot-cache        # image tag edit (the only file changed)
    - deployment/penpot-cache         # strategy Recreate -> ~10-30 s cache outage
    - deployment/penpot-backend       # NOT edited; lettuce client drops + reconnects
    - deployment/penpot-exporter      # NOT edited; holds client connections + one pub/sub subscription, reconnects
  shared: [monitoring]                # no PVC, no route, not a shared redis. `monitoring` only because §4 CONTROLs
                                      # read Prometheus (the window instrument), never perturbed by this change.
depends_on: []
conflicts_with: [penpot-cache-9.2, kube-prometheus-stack-93.3.0, flux-reconciler-impersonation]
  # penpot-cache-9.2 (blocked): same file, same line, and now the SAME target series. This plan supersedes it (§6);
  #   until it is retired, never run both. Reciprocal entry already present there.
  # kube-prometheus-stack-93.3.0 (draft): §4 CONTROLs read kube-state-metrics through Prometheus; reciprocal
  #   entry present there.
  # flux-reconciler-impersonation (blocked): changes how helm/kustomize controllers apply in every namespace
  #   incl. office; a same-night change would make a failed apply here ambiguous.
exclusive: false
security_ref: F-a7f596b9              # AR-029 register row for valkey/valkey:9.1.3 (the CURRENT tag). The one security fix
                                      # 9.1.4 shipped is also in 9.2.0's fix list (§1). Detail stays in the DB.
capability_change: false              # no config, flag, route, permission, auth or exposure changes; the new 9.2
                                      # commands/configs are all opt-in and nothing here enables them; Penpot's fixed
                                      # command set (§1) uses none of them. Same service behaviour for its one consumer.
rollback_class: git-revert            # no persistence: nothing on disk 9.1.3 could fail to read
finding_refs: [F-fe71a06e, F-4a592cd2]
  # F-fe71a06e "penpot-cache: image valkey/valkey 9.1.3 → 9.2 (minor)" (version, open; also carried by penpot-cache-9.2)
  # F-4a592cd2 "valkey 9.2.0 GA now exists upstream - plan penpot-cache-9.2 blocker premise ..." (plan, open)
  # F-cfbc2a5f (9.1.3 -> 9.1.4) is resolved; not carried.
status: draft
window: null
premises:
  - id: live-image-still-9.1.3
    why: >-
      `current:` claims 9.1.3. If the deployment already moved (Step 0 auto-merging
      #615 once Renovate rebases it, or a manual bump), the baseline and rollback
      target are wrong and the step-1 sed is a no-op. Live 9.2.1 = already applied: retire.
    run: kubectl get deploy penpot-cache -n office -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: valkey/valkey:9.1.3
  - id: manifest-pin-still-9.1.3
    why: "The step-1 sed anchors on the exact string `tag: \"9.1.3\"`; a changed pin makes it a silent no-op."
    run: grep -c 'tag. "9.1.3"' /Users/mu/code/cberg-home-nextgen/kubernetes/apps/office/penpot-cache/app/helmrelease.yaml
    expect_exact: "1"
  - id: penpot-backend-points-at-penpot-cache
    why: "The consumer the §4.3 reconnect gate counts; if penpot's redis host moved, that gate measures the wrong thing."
    run: kubectl get helmrelease penpot -n office -o jsonpath='{.spec.values.config.redis.host}'
    expect_exact: penpot-cache
  - id: cache-is-still-non-persistent
    why: >-
      risk low and rollback_class git-revert rest on the cache writing no RDB/AOF.
      If someone enabled persistence, a revert could face a file written by 9.2.1
      (9.2 adds new RDB encodings). Reads the declared command; §2.4 confirms live
      with INFO persistence, since the runner refuses kubectl exec.
    run: kubectl get helmrelease penpot-cache -n office -o jsonpath="{.spec.values.controllers['penpot-cache'].containers.app.command}"
    expect_exact: '["valkey-server","--save","","--appendonly","no"]'
sops_refs:
  - docs/sops/application-update.md
generated: "2026-11-27"
---

# penpot-cache: valkey 9.1.3 -> 9.2.1 (re-planned in place from 9.1.4; plan_id kept)

## 1. Summary & why held

`penpot-cache` (namespace `office`) is a cache-only Valkey (bjw-s app-template 5.3.0,
`strategy: Recreate`, `--save ""`, `--appendonly no`, no PVC, no auth, standalone, `DBSIZE 0`)
serving Penpot's backend and exporter on Service `penpot-cache:6379`.

**RETARGET 9.1.4 -> 9.2.1 (2026-11-27).** `plan-refine` flagged
`needs_replan: minor-or-major-drift` (upstream moved 9.1.4 -> 9.2.1). What happened since the
first draft (2026-11-19):

- Commit `66c8ea0c1` (2026-11-25) **retired the interim `*valkey*` deny rule** that was this plan's
  only hold reason (its removal condition, a real GA above 9.1.2, was met). `valkey` now appears in
  `runbooks/auto-update-policy.yaml` only under `digest_bumps.stateful`, which governs same-tag
  rebuilds, not tag moves.
- So Step 0 auto-merged both hops and the engine auto-reverted both **as part of whole-batch
  reverts caused by an unrelated health-gate trip** (mealie shopping-sync failing while Home
  Assistant restarted; F-5c26f490, recurred as F-004234b4):
  - 2026-11-26: #572 9.1.3 -> **9.2.0** merged `7831b084c`, reverted `5e8408a0d`. Prometheus shows
    pod `penpot-cache-695d8bf9f5-wpv7r` on `docker.io/valkey/valkey:9.2.0` from 02:38 to 02:47Z.
    penpot-backend/exporter restarts stayed 0 -> 0 through it.
  - 2026-11-27: #561 9.1.3 -> **9.1.4** merged `56ed46904`, reverted `11c586064` (9.1.4 pod
    02:36 to 02:41Z, again 0 consumer restarts).
- Upstream now ships 9.2.1 (GA, `Latest`, 2026-11-26T06:15Z). Renovate's live proposal is PR #615
  (-> 9.2.1). #561 is closed as merged.

**Why 9.2.1 and not 9.1.4:**
1. The one security fix that made 9.1.4 SECURITY-urgency is in 9.2.0's bug-fix list too: same
   upstream PR. Taking 9.2.1 closes the same gap. Detail is on `security_ref`.
2. 9.1.4 is no longer anyone's proposal. It is not Renovate's open PR, and `plan-refine` would
   re-flag a 9.1.4 target as drift every night, so the plan could never run.
3. **All three 9.2.0 "Behavior Changes" miss this workload:**

   | 9.2.0 behaviour change | Why it does not touch us |
   |---|---|
   | `ZRANGEBYSCORE`/`ZREVRANGEBYSCORE`/`ZCOUNT`/`ZRANGESTORE` reject a bare `(` or empty score bound | Penpot uses no sorted sets (see below) |
   | Path Hash deletes the key with the last path | Path Hash is a new type, unused |
   | Active expiration increments the dirty counter, so save points may trigger BGSAVE more often | `--save ""`: there are no save points |

   - Other 9.2.0 items that could matter, checked: the renamed config
     `bgsave-default-method`→`forkless-policy` is not set here, and the removed `INFO` hotkeys
     section existed only in RCs.
   - 9.2.1 (urgency MODERATE) is bug fixes only: TLS-loading regression, IO-thread, replication,
     cluster-bus and module fixes. None of them is on our path (no TLS, no replica, no cluster,
     no modules).
4. **Penpot's command set (penpot 2.19.3, verified against source at tag `2.19.3`):**
   - `backend/src/app/redis.clj` issues only `get set del ping publish subscribe unsubscribe rpush
     blpop scan hget evalsha scriptLoad`.
   - Its Lua scripts call only `incr expire` (`rpc/rlimit/window.lua`), `hget hset expire`
     (`rpc/rlimit/bucket.lua`) and `GET SET` (`auth/login_lockout.lua`).
   - There are no sorted-set calls anywhere: a GitHub code search of penpot/penpot for
     ZRANGEBYSCORE / ZCOUNT returns 0 hits.
   - The rlimit feature is not even enabled. `PENPOT_FLAGS` is `disable-registration
     enable-login-with-password disable-email-verification enable-prepl-server`.
   - `maxmemory-clients` is `0` live, so the eviction path behind the security fix is not armed.

**Registry and release evidence (measured 2026-11-27):**

| Probe | Result |
|---|---|
| `valkey/valkey:9.2.1` | HTTP 200, index digest `sha256:169567d6288e...` |
| `valkey/valkey:9.2` (floating) | HTTP 200, **same** `169567d6...` (the floating tag moved to the newest 9.2 GA, as expected) |
| `valkey/valkey:9.2.0` | `1c2b25b0...` |
| `valkey/valkey:9.2.0-rc2` | `2aff0c1e...`, different from 9.2.1, so 9.2.1 is not an RC twin |
| `valkey/valkey:9.1.3` (current) | `3add1a33...` = live pod imageID |
| `9.2.2`, `9.2.1-rc1` | 404 |
| GitHub release `9.2.1` | `isPrerelease:false`, Latest, 2026-11-26T06:15Z |

**Why it still sits in the plan lane and is not left to Step 0:** this plan was flagged
`needs_replan`. PR #615 cannot merge while it conflicts. And Step 0 has reverted every valkey hop
so far through unrelated batch failures. If #615 gets rebased and Step 0 lands it first, the
premise `live-image-still-9.1.3` fails with the live image at `valkey/valkey:9.2.1`. That means
the work is already applied: the sweep retires this plan, and nobody re-plans it.

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.1 (replaces a premise: the runner refuses gh/curl) target is GA and not an RC twin
gh release view 9.2.1 -R valkey-io/valkey --json isPrerelease,publishedAt
# PASS: "isPrerelease":false. FAIL: true, or "release not found".
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:valkey/valkey:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in 9.2.1 9.2.0-rc2 9.2.2; do
  printf '%-12s ' "$t"
  curl -s -I -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json" \
    "https://registry-1.docker.io/v2/valkey/valkey/manifests/$t" \
    | grep -i -E '^HTTP|docker-content-digest' | tr -d '\r' | tr '\n' ' '; echo
done
# PASS: 9.2.1 -> HTTP/2 200 with digest sha256:169567d6288e5f08... and != the 9.2.0-rc2 line (2aff0c1e...).
# FAIL: 404, a digest equal to the rc line, or a 9.2.1 digest other than 169567d6... (tag re-pushed: STOP,
#   re-plan; §4.1 pins this digest). If 9.2.2 now returns 200, a newer patch exists: STOP and let
#   plan-refine / a re-plan move the target (do not run a superseded patch).

# 2.2 PR #615 still proposes 9.2.1 (a Renovate retarget would change the target)
gh pr view 615 --json title,state -q '.title+" "+.state'
# PASS: "feat(container): update valkey/valkey ( 9.1.4 → 9.2.1 ) OPEN" (the "9.1.4" left side is Renovate's
#   stale base; CONFLICTING is expected and irrelevant, the steps edit main). Also PASS: "... → 9.2.1" with a 9.1.3
#   left side after a rebase. FAIL: a target other than 9.2.1 -> re-plan. MERGED -> check premise 1 (already applied?).

# 2.3 premises
.venv/bin/python3 runbooks/plan-premises.py penpot-cache-9.1.4 --require-premises

# 2.4 baseline (2026-11-27 02:49Z: valkey_version:9.1.3, DBSIZE 0, aof_enabled:0, maxmemory-clients 0,
#     CLIENT LIST = backend 10.69.2.118 x4, exporter 10.69.2.185 x2, local cli 127.0.0.1 x1)
kubectl exec deploy/penpot-cache -n office -- valkey-cli INFO server | grep -i valkey_version
kubectl exec deploy/penpot-cache -n office -- valkey-cli INFO persistence | grep -i -E 'aof_enabled|rdb_changes_since_last_save'
# PASS: aof_enabled:0. FAIL: aof_enabled:1 -> STOP, re-plan rollback_class (9.2 RDB/AOF may not load on 9.1).
kubectl exec deploy/penpot-cache -n office -- valkey-cli CONFIG GET save
# PASS: the value line is empty. FAIL: any "N M" save point -> STOP (persistence enabled behind the declared command).
kubectl exec deploy/penpot-cache -n office -- valkey-cli CLIENT LIST | awk '{print $2}' | cut -d= -f2 | cut -d: -f1 | sort | uniq -c
kubectl get pod -n office -l app.kubernetes.io/name=penpot-backend \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.podIP}{" restarts="}{.status.containerStatuses[0].restartCount}{"\n"}{end}'
kubectl get pod -n office -l app.kubernetes.io/name=penpot-exporter \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.podIP}{" restarts="}{.status.containerStatuses[0].restartCount}{"\n"}{end}'
# RECORD both pod names + restart counts (2026-11-27: penpot-backend-74865bfd9-6wwx6 0, penpot-exporter-7b54b7fd74-cxrr8 0).

# 2.5 baseline redis error noise in the backend. NOTE 2026-11-27 02:49Z: 44 in 30 min, ALL from that night's
#   Step 0 bump+revert (two Recreates at 02:36Z and 02:41Z); a quiet night reads 0. Record the number, it is
#   informational, not a gate.
kubectl logs deploy/penpot-backend -n office -c penpot-backend --since=30m | grep -i -c -E 'RedisCommandTimeout|RedisConnectionException|Connection refused'

# 2.6 Flux healthy for the release
flux get helmreleases -n office | grep -E 'NAME|penpot'
# PASS: penpot-cache READY True (2026-11-27: app-template@5.3.0, release v20).
```

No backup step: the cache holds no durable state (`--save ""`, `aof_enabled:0`, no PVC, `DBSIZE 0`).
No storage operation of any kind is in this plan (the namespace's CIFS PVC `penpot-assets` is not
touched; nothing is deleted).

## 3. Steps

1. Edit the pin. Dry-tested 2026-11-27 on a scratch copy with BSD sed. The resulting diff was
   exactly `39c39` / `<               tag: "9.1.3"` / `>               tag: "9.2.1"`, one line.

   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' 's/tag: "9\.1\.3"/tag: "9.2.1"/' kubernetes/apps/office/penpot-cache/app/helmrelease.yaml
   git diff kubernetes/apps/office/penpot-cache/app/helmrelease.yaml   # exactly one changed line
   grep -n 'tag: "9\.' kubernetes/apps/office/penpot-cache/app/helmrelease.yaml   # must read "9.2.1", never bare 9.2
   ```

2. Commit only that file and push. Use `--only` because the worktree is shared.

   ```bash
   git commit --only kubernetes/apps/office/penpot-cache/app/helmrelease.yaml \
     -m "chore(penpot-cache): valkey 9.1.3 -> 9.2.1 (plan penpot-cache-9.1.4, closes PR #615)"
   git log -1 --format=%s          # confirm the subject is YOURS before pushing; amend if not
   git show --stat HEAD            # exactly one file
   git push
   ```

3. Let the Flux webhook reconcile; do not reconcile manually. With `Recreate` there is a 10-30 s
   gap where Penpot's backend logs redis connection errors while lettuce reconnects. Penpot
   sessions are not stored in this cache. Open editors may see a brief realtime-sync hiccup.

4. If PR #615 has not auto-closed after one Renovate run, close it:
   `gh pr close 615 --comment "landed via plan penpot-cache-9.1.4 (retargeted to 9.2.1)"`.

## 4. Verification

Start at T+3 min after the new pod is Ready, which gives lettuce time to reconnect.

```bash
# 4.1 running binary is the pinned release (contents, not the tag)
kubectl get deploy penpot-cache -n office -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl get pod -n office -l app.kubernetes.io/name=penpot-cache \
  -o jsonpath='{range .items[*]}{.status.containerStatuses[0].image}{" "}{.status.containerStatuses[0].imageID}{"\n"}{end}'
kubectl exec deploy/penpot-cache -n office -- valkey-cli INFO server | grep -i valkey_version
# PASS: deploy spec == valkey/valkey:9.2.1; exactly ONE pod line, image docker.io/valkey/valkey:9.2.1 and
#   imageID ending sha256:169567d6288e5f08aa141847c0c3e0864a32e727682ca6f052a20567c7103ef8; INFO prints
#   valkey_version:9.2.1.
# The digest gate can fail: on 2026-11-27 the live 9.1.3 pod's imageID (3add1a33...) EQUALS the registry index
#   digest of 9.1.3, so the same comparison is meaningful for 169567d6....
# FAIL shapes: valkey_version:9.1.3 / imageID 3add1a33... = Recreate did not happen or HR stuck;
#   two pod lines = old pod still terminating (wait, re-run); 9.2.0 / any other digest = wrong tag (rollback).

# 4.2 real round-trip on a scratch DB (penpot uses db 0)
kubectl exec deploy/penpot-cache -n office -- valkey-cli -n 15 SET plan:penpot-cache-9.2.1 ok EX 60
kubectl exec deploy/penpot-cache -n office -- valkey-cli -n 15 GET plan:penpot-cache-9.2.1
# PASS: GET prints `ok`. FAIL: (nil) or an error.

# 4.2b Lua path Penpot depends on (EVALSHA of its rlimit/lockout scripts): same primitives on the new engine
kubectl exec deploy/penpot-cache -n office -- valkey-cli -n 15 EVAL "redis.call('set',KEYS[1],'1','EX',60); return redis.call('incr',KEYS[1])" 1 plan:penpot-cache-lua
# PASS: prints (integer) 2. FAIL: an ERR line (scripting broken on the new binary) or any other value.

# 4.3 consumers reconnected (the load-bearing consumer gate)
kubectl exec deploy/penpot-cache -n office -- valkey-cli CLIENT LIST | awk '{print $2}' | cut -d= -f2 | cut -d: -f1 | sort | uniq -c
kubectl get pod -n office -l app.kubernetes.io/name=penpot-backend -o jsonpath='{.items[0].status.podIP}{"\n"}'
kubectl get pod -n office -l app.kubernetes.io/name=penpot-exporter -o jsonpath='{.items[0].status.podIP}{"\n"}'
# PASS: the backend pod IP appears with >= 1 connection AND the exporter pod IP with >= 1
#   (baseline 2026-11-27: backend 10.69.2.118 x4, exporter 10.69.2.185 x2, cli 127.0.0.1 x1).
# FAIL: only 127.0.0.1 listed -> the apps never reconnected. If still failing at T+10 min, roll back (§5);
#   restarting a consumer is a cberg-agent action to raise, not part of this plan.

# 4.4 POSITIVE gate: exporter pub/sub re-established, backend Lettuce clients attached and issuing commands
#   (the penpot backend emits NO redis success log line, so an absence-of-errors grep reads zero on a dead link too).
kubectl exec deploy/penpot-cache -n office -- valkey-cli PUBSUB NUMSUB penpot.exporter.default.job-cancel
kubectl exec deploy/penpot-cache -n office -- valkey-cli CLIENT LIST | grep -c 'lib-name=Lettuce'
kubectl exec deploy/penpot-cache -n office -- valkey-cli INFO stats | grep -E 'total_commands_processed|total_connections_received'
# PASS (all three, re-run at T+5 and T+10 min): line 2 of NUMSUB prints exactly 1 (baseline 2026-11-27 on 9.1.3: 1);
#   the Lettuce count is >= 1 (baseline 4); total_commands_processed is > 0 and GROWS between the two runs
#   (2026-11-27: 503 commands ~9 min after a fresh start, i.e. continuous PING/BLPOP traffic).
# FAIL: NUMSUB prints 0 (control: `PUBSUB NUMSUB nosuch.channel` prints 0), Lettuce count 0, or no growth.
# Secondary, informational only (NOT a gate): backend redis errors during the Recreate are EXPECTED:
#   kubectl logs deploy/penpot-backend -n office -c penpot-backend --since=5m | grep -i -c -E 'RedisCommandTimeout|RedisConnectionException|Connection refused'
#   Pattern proven to match live output on 2026-11-27 (44 hits from that night's two Recreates).

# 4.5 floor, not the gate
kubectl get deploy penpot-backend penpot-frontend penpot-exporter -n office
flux get helmreleases -n office | grep penpot
```

CONTENTS ASSERTION: the cache serves reads and writes on the 9.2.1 binary, and Penpot's clients
are attached to it. Measured by:
- 4.1: the running process reports `valkey_version:9.2.1`, and the pod imageID equals registry
  digest `169567d6...`;
- 4.2/4.2b: the SET/GET round-trip returns `ok`, and the Lua `incr` returns 2;
- 4.3/4.4: the backend and exporter pod IPs are present in `CLIENT LIST`, and the exporter
  subscription NUMSUB is 1.

The baseline is 2026-11-27 on 9.1.3: 4 backend connections, 2 exporter connections, NUMSUB 1.

CONTROL: metric kube_pod_container_info - `{namespace="office",container="app",pod=~"penpot-cache.*"}` must return exactly one series whose `image` label is `docker.io/valkey/valkey:9.2.1` (a stale `docker.io/valkey/valkey:9.1.3` series FAILS the gate; this exact query showed the 9.2.0 and 9.1.4 pods on 2026-11-26/27, so it can tell versions apart).
CONTROL: metric kube_deployment_status_replicas_available - `{namespace="office",deployment="penpot-cache"}` must be 1 for 10 min after rollout (baseline 1).
CONTROL: metric kube_pod_container_status_restarts_total - `{namespace="office",pod=~"penpot-(backend|exporter).*"}`: compare per pod name against the §2.4 record (2026-11-27: both 0); PASS = unchanged. A consumer crash-looping on reconnect shows here first.

## 5. Rollback

The change is stateless and forward-safe. The cache writes no RDB/AOF (premise
`cache-is-still-non-persistent`, plus the §2.4 `CONFIG GET save` check), so 9.1.3 has nothing on
disk it could fail to load. No step in this plan is forward-only. The rollback target is **9.1.3**
(live), not 9.1.4. The 9.2.0 -> 9.1.3 direction was exercised in production on 2026-11-26
(`5e8408a0d`) with no consumer restart.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-step-2>
git log -1 --format=%s ; git show --stat HEAD   # one file, the revert, subject is yours
git push
```

Confirm back:

```bash
kubectl get deploy penpot-cache -n office -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # valkey/valkey:9.1.3
kubectl get pod -n office -l app.kubernetes.io/name=penpot-cache -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'  # ...sha256:3add1a33...
kubectl exec deploy/penpot-cache -n office -- valkey-cli INFO server | grep -i valkey_version              # valkey_version:9.1.3
```

Then re-run §4.2-4.4 against 9.1.3. If the HelmRelease is stuck `pending-upgrade`, or remediation
has already rolled it back, follow `docs/sops/application-update.md`
(`helm rollback penpot-cache <last-deployed> -n office --wait=false`) before the revert lands.
After a revert, Renovate keeps #615 open (or re-proposes it). With the deny rule gone, Step 0 may
retry it on a later night. If a rollback was for a valkey-caused reason, add a deny rule for
`valkey/valkey` in the same session so the retry does not happen.

## 6. Interference notes

- Only Penpot depends on this cache. The penpot HelmRelease has `config.redis.host:
  penpot-cache`, and the live client list shows only the backend and the exporter.
  penpot-backend also has a `wait-for-redis` init container. If the backend pod happens to
  restart during the Recreate, it waits for the cache instead of crash-looping. The
  nextcloud/affine/sure/paperless redis instances are separate Deployments. No redis-fleet or
  redisinsight plan names penpot-cache.
- **This plan supersedes `penpot-cache-9.2` (blocked).** Both plans now aim at the 9.2 series
  through the same file and line. That plan's blocker has been gone since 9.2.0 shipped
  (F-4a592cd2), but its baseline is 9.1.2. Never run both. Recommend retiring it as superseded by
  this plan (not done here: this re-plan edits only its own file).
- `kube-prometheus-stack-93.3.0` (draft) is the window instrument for the §4 CONTROLs, so do not
  stack them. If Step 0 lands any kube-prometheus-stack bump the same night, run this plan's
  CONTROLs only after Prometheus is back, or treat them as unavailable and rely on 4.1-4.4.
- **Step 0 interaction.** The `*valkey*` hold is gone, so a rebased #615 is AUTO-eligible.
  - If Step 0 merges it in the same window before this plan runs, premise 1 fails with the live
    image at 9.2.1. Treat that as already applied: skip this plan and let the sweep retire it. Do
    not re-run.
  - If Step 0's batch revert hits it again for an unrelated reason (F-004234b4), this plan is the
    reviewed path that lands it outside the batch.
- Repo corrections (none performed here; raise each separately):
  1. `runbooks/maintenance/plans/penpot-cache-9.2.md` should be retired as superseded by this plan
     (same line, same target series, stale 9.1.2 baseline).
  2. The coverage/version-check finding F-fe71a06e names the floating `9.2` as the target.
     `target_covers()` intersects version tokens, so this plan's fixed `9.2.1` does not textually
     cover a held `new: 9.2`. If coverage keeps holding `9.2`, it will read this plan as
     non-covering. The checker should resolve the floating tag to the fixed GA it points at
     (digest `169567d6...` = 9.2.1).
  3. Step 0 has whole-batch-reverted a valkey bump two nights running for a non-valkey gate trip
     (F-5c26f490 / F-004234b4). Until the gate is fixed, unrelated cheap patches keep churning
     through Recreate restarts (four penpot-cache restarts across 2026-11-26/27).
