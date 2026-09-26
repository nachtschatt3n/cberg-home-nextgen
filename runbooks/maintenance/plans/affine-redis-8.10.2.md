---
plan_id: affine-redis-8.10.2
component: affine-redis
pr: null                          # coverage.py needs_plan (direct-bump lane) — no Renovate PR
kind: image
current: "8.10.1-alpine"
target: "8.10.2-alpine"
update_type: patch
risk: low
est_duration_min: 15
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/affine-redis
    - deployment/affine-redis
    - service/affine-redis          # unchanged; endpoints flip to the new pod
    - deployment/affine             # transient reconnect only (ioredis); NOT restarted
  shared: []                        # dedicated redis, single consumer; no PVC, no gateway/route change
depends_on: []
conflicts_with:
  - helm-drift-detection            # its §4.1 asserts Helm revision numbers are IDENTICAL across
                                    # all releases before/after; an affine-redis upgrade (rev 14 -> 15)
                                    # in the same window would fail that gate and mis-attribute.
                                    # Reciprocal entry added to helm-drift-detection 2026-09-26 (review).
exclusive: false
security_ref: null
capability_change: false
rollback_class: git-revert          # redis is non-persistent; nothing forward-only happens
finding_refs: [F-d40c9c12]          # version finding "affine-redis: image redis 8.10.1-alpine → 8.10.2-alpine (patch)"
status: vetted   # 2026-09-26 plan-reviewer needs-fix -> 5 edits applied (cooldown exits 1 on TOO_NEW, V6 log grep informational, V7 asserts /info body); NOT before 2026-09-26T21:05Z -> 03:30 nightly (AUTO-NIGHT)
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-09-25"
premises:
  - id: live-image-is-current
    why: >-
      `current:` claims redis:8.10.1-alpine on the serving Deployment. If the
      nightly direct-bump lane or a hand edit already moved it, this plan is a
      no-op and must be retired, not executed.
    run: kubectl get deploy -n office affine-redis -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: redis:8.10.1-alpine
  - id: manifest-pin-is-current
    why: >-
      The §3 sed is anchored on the literal `tag: 8.10.1-alpine` line. If the
      manifest pin moved (or gained a digest), the sed matches nothing and the
      commit would be empty — re-derive §3 instead.
    run: 'grep -c "tag: 8.10.1-alpine" kubernetes/apps/office/affine/app/redis-helmrelease.yaml'
    expect_exact: "1"
  - id: redis-is-non-persistent
    why: >-
      The whole low-risk / git-revert rating rests on this redis holding NO
      durable state (no RDB, no AOF), so a Recreate loses nothing that the
      AFFiNE crons do not rebuild from Postgres within ~30 s (§1). If someone
      turned persistence on, the rollback class and §4 change.
    run: kubectl get deploy -n office affine-redis -o jsonpath='{.spec.template.spec.containers[0].command}'
    expect_exact: '["redis-server","--save","","--appendonly","no"]'
  - id: redis-mounts-no-volume
    why: >-
      Companion to the above: no PVC/volume on the redis pod, so storage-safety
      pre-flight is N/A. The literal prefix keeps the output non-empty (an
      empty result fails closed); anything after `volumes=` means a volume
      appeared and the plan must be re-assessed.
    run: kubectl get deploy -n office affine-redis -o jsonpath='{"volumes="}{.spec.template.spec.volumes}'
    expect_exact: volumes=
  - id: affine-redis-release-ready
    why: >-
      Start from a Ready release, otherwise a post-change Ready=False cannot be
      attributed to this bump.
    run: kubectl get helmrelease -n office affine-redis -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
---

# affine-redis 8.10.1-alpine → 8.10.2-alpine

## 1) Summary & why held

`affine-redis` is AFFiNE's **dedicated stock Docker Hub `redis` cache/queue**
(its own app-template HelmRelease `office/affine-redis`, ClusterIP
`affine-redis:6379`, `strategy: Recreate`). Only its image tag moves:
`redis:8.10.1-alpine → 8.10.2-alpine`, a same-minor upstream patch. Tag verified
on Docker Hub 2026-09-25: `8.10.2-alpine` exists, digest
`sha256:3811787313eba226a2ef38658c6ccb91cd5e110edc89c37767de373120a0e5a0`,
published **2026-09-24T21:05Z**. The AFFiNE application image
(`ghcr.io/toeverything/affine:0.27.4`) is **not touched**.

**Why held — a policy false positive.** No Renovate PR; `coverage.py` routed it
to needs_plan because the `*affine*` deny rule in
`runbooks/auto-update-policy.yaml` matches the component name `affine-redis`:

> "affine chart/image bumps carry breaking env→config.json changes even on patch
> tags (0.27.3) — hold for manual review."

That reason is about the AFFiNE **server** image's env → `config.json`
migration surface. **The redis bump is not coupled to the AFFiNE app**, checked
three ways:
- Separate HelmRelease, separate image (`redis`, not `toeverything/affine`),
  separate Deployment; no AFFiNE config/env value changes in this plan.
- The only coupling is the client protocol (AFFiNE uses ioredis/BullMQ against
  `REDIS_SERVER_HOST=affine-redis`, port 6379). A redis same-minor patch does
  not move the RESP protocol or command set. Upstream's 8.10.2 notes list
  fixes (core, TimeSeries, RedisSearch, Vector Sets) and one new config option,
  `cluster-bus-port-protected-mode`, which **defaults to `no`** — i.e. no
  behaviour change, and it concerns cluster mode, which this single-node redis
  does not run. Item-level detail stays upstream (public-repo rule,
  `docs/sops/vulnerability-disclosure.md`).
- The same `8.10.1 → 8.10.2` bump is pending for eight other redis instances
  here (findings F-3a75c9aa, F-3fcdca7b, F-8c50c463, F-2e326f86, F-c637a09a,
  F-625d3a3f, F-d2bb762b, F-e8a41b1b) that are **not** denied; they will land
  through the nightly safe lane once the G5 48 h release-age cooldown lapses
  (~2026-09-26T21:05Z). Only the glob singles this one out.

**What a restart of this redis actually costs AFFiNE (read from upstream
source, `toeverything/AFFiNE` tag `v0.27.4`).** Redis is non-persistent here
(`--save "" --appendonly "no"`, no volume) and holds only BullMQ queue state in
**db 4** (measured: 22 keys, all `affine_job:<queue>:…`). Every producer that
matters re-enqueues from **in-process `@nestjs/schedule` crons**, not from
redis-stored repeatables:
- `core/doc-service/job.ts`: `@Cron(EVERY_30_SECONDS) schedule()` rebuilds the
  `doc.mergePendingDocUpdates` jobs from `models.doc.groupedUpdatesCount()` —
  i.e. from **Postgres**. Pending doc updates live in the DB, so a dropped
  queue is re-derived within 30 s; no document data is in redis.
- same file: `scheduleRecordPendingDocUpdatesCount` and
  `scheduleFindEmptySummaryDocs` re-add every 30 s.
- `core/doc/job.ts`, `plugins/payment/cron.ts`: nightly jobs enqueued by
  `@Cron(EVERY_DAY_AT_MIDNIGHT)`.
So the loss is bounded to in-flight jobs at the instant of the swap, all of
which are re-derived. Empirical support: the 8.10.0 → 8.10.1 bump of this same
redis (2026-09-05, `ea99ab5d`) completed with AFFiNE reconnecting
(`connected_clients` back to baseline) and the AFFiNE pod **not** restarting.

Net: `risk: low`. It is held only because the window is the only lane the deny
rule leaves open. **Repo correction (policy, out of scope here):** the
`*affine*` glob should be narrowed to the app image (e.g.
`*toeverything/affine*`) or exempt `affine-redis`; this is the second
consecutive redis patch it has diverted into a plan.

## 2) Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# a) premises (read-only, fail closed)
.venv/bin/python3 runbooks/plan-premises.py affine-redis-8.10.2

# b) G5 supply-chain cooldown — do NOT execute before the tag is 48 h old,
#    even attended: the fleet's other eight redis instances wait for the same
#    gate. PASS prints AGE_OK; a tag younger than 48 h prints TOO_NEW (or the
#    fetch failing prints FETCH_FAILED — also a stop).
curl -s https://hub.docker.com/v2/repositories/library/redis/tags/8.10.2-alpine | python3 -c '
import sys, json, datetime as d
try:
    t = json.load(sys.stdin)["last_updated"]
except Exception:
    print("FETCH_FAILED"); sys.exit(1)
age = (d.datetime.now(d.timezone.utc) - d.datetime.fromisoformat(t.replace("Z","+00:00"))).total_seconds()/3600
ok = age >= 48
print(("AGE_OK" if ok else "TOO_NEW"), round(age,1), "h", t); sys.exit(0 if ok else 1)'
#    Docker Hub last_updated 2026-09-24T21:05Z. That is a RE-PUSH (upstream
#    released 8.10.2 on 2026-09-17); coverage.py's G5 keys on last_updated
#    too, so this mirrors the fleet gate. Earliest AGE_OK 2026-09-26T21:05Z;
#    nightly 2026-09-27 03:30 (01:30Z, ~52 h) or any later slot is fine.
#    A further re-push of the tag resets the clock: TOO_NEW then is a STOP.

# c) target tag still resolvable AND no newer 8.10.x has superseded it
#    (8.10.2 -> 200; 8.10.3 -> 404 expected; a 200 there means refresh the plan)
for t in 8.10.2-alpine 8.10.3-alpine; do
  curl -s -o /dev/null -w "$t -> %{http_code}\n" https://hub.docker.com/v2/repositories/library/redis/tags/$t
done

# d) baseline — record these three numbers; §4 compares against them
POD=$(kubectl get pod -n office -l app.kubernetes.io/instance=affine-redis -o name); POD=${POD##*/}; echo $POD
kubectl exec -n office $POD -- redis-cli info server | grep -i '^redis_version'      # 8.10.1
kubectl exec -n office $POD -- redis-cli info clients | grep '^connected_clients'    # measured 14 on 2026-09-25
kubectl exec -n office $POD -- redis-cli info keyspace                               # measured db4:keys=22
#    NOTE: `redis-cli dbsize` reads db0 and prints 0 here — AFFiNE uses db4.
#    That is why the 8.10.0 plan's "dbsize must be > 0" gate misread a
#    healthy baseline. Use `info keyspace` / `-n 4`.

# e) AFFiNE app pod identity + restart count (must be unchanged by §3)
kubectl get pod -n office -l app.kubernetes.io/instance=affine \
  -o 'custom-columns=NAME:.metadata.name,RESTARTS:.status.containerStatuses[0].restartCount,START:.status.startTime'

# f) steady-state redis connection-error rate in AFFiNE logs is zero right now
#    (a 3-minute ETIMEDOUT burst WAS seen 2026-09-24 ~22:27 local, unrelated to
#    any change — so measure fresh; if non-zero now, stop and investigate first)
kubectl logs -n office deploy/affine -c main --since=10m | grep -ciE 'ETIMEDOUT|ECONNREFUSED'   # expect 0

# g) no other plan in this window touches office/affine or asserts Helm revisions
python3 runbooks/maintenance-plan.py --open | grep -iE 'affine|helm-drift' || true
```

Proceed only if (a) all premises PASS, (b) prints AGE_OK, (c) shows 200/404,
and (f) prints 0.

## 3) Steps (GitOps)

`docs/sops/application-update.md` §5 Example A (low-risk image patch): no
remediation change needed. Silence optional — the swap takes seconds and the
redis `Recreate` does not trip Kube* alerts at that duration; if the window
agent silences by default, use the SOP §4 Step 1 recipe with `namespace=office`
and a 1 h TTL.

1. Edit the tag (dry-tested on a scratch copy, macOS BSD sed, 2026-09-25):
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' 's/^\([[:space:]]*tag:[[:space:]]*\)8\.10\.1-alpine$/\18.10.2-alpine/' \
     kubernetes/apps/office/affine/app/redis-helmrelease.yaml
   git diff kubernetes/apps/office/affine/app/redis-helmrelease.yaml
   ```
   Expected diff (exactly one line, verified on the scratch copy):
   ```
   -              tag: 8.10.1-alpine
   +              tag: 8.10.2-alpine
   ```

2. Commit only that path, verify, push:
   ```bash
   git commit --only kubernetes/apps/office/affine/app/redis-helmrelease.yaml \
     -m "chore(affine): redis sidecar 8.10.1-alpine -> 8.10.2-alpine (plan affine-redis-8.10.2)"
   git log -1 --format=%s          # must be THIS subject (shared-worktree message swap guard)
   git show --stat HEAD            # exactly one file
   git push
   ```

3. Let the Flux webhook reconcile (no manual `flux reconcile`). `Recreate`
   terminates the old pod, then starts the new one: a few seconds with no
   redis. Do not delete pods by hand.

## 4) Verification

Re-resolve the pod name after the swap (it changes on Recreate).

```bash
cd /Users/mu/code/cberg-home-nextgen

# V1 — release upgraded and Ready. FAILS as: Ready=False, or revision still 14
#      (no upgrade happened — e.g. the push never reconciled).
kubectl get helmrelease -n office affine-redis \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} rev={.status.history[0].version}{"\n"}'
#      PASS: "True rev=15" (baseline rev 14 measured 2026-09-25)

# V2 — the RUNNING container is the new digest, not just the spec.
#      FAILS as: imageID still sha256:becdda6c… (old 8.10.1 pod still serving)
POD=$(kubectl get pod -n office -l app.kubernetes.io/instance=affine-redis -o name); POD=${POD##*/}; echo $POD
kubectl get pod -n office $POD -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
kubectl exec -n office $POD -- redis-cli info server | grep -i '^redis_version'
#      PASS: imageID is a redis@sha256 digest != becdda6c… AND redis_version:8.10.2
#      (the Docker Hub digest 3811787… is the multi-arch INDEX; the pod may
#      report the per-arch manifest digest, so compare "changed + version",
#      not string-equal to 3811787…)
```

### CONTENTS ASSERTION — `PONG` is not verification

A fresh, empty redis that AFFiNE is not talking to answers `PING` and passes
every probe. The contents property for this non-persistent queue is **"AFFiNE
reconnected and is writing to it again"**, measured three ways, each of which
has a concrete failing output:

```bash
# V3 — raw write/read round-trip on the new server.
#      FAILS as: (nil) or an error instead of "ok".
kubectl exec -n office $POD -- redis-cli -n 15 set __plan_verify ok EX 60
kubectl exec -n office $POD -- redis-cli -n 15 get __plan_verify     # MUST print: ok
kubectl exec -n office $POD -- redis-cli -n 15 del __plan_verify

# V4 — AFFiNE's own queue keys REAPPEAR in db4. Poll up to 3 min (the 30 s
#      crons in core/doc-service/job.ts re-add them). Right after the swap db4
#      is empty — that is correct; staying empty is the failure (AFFiNE not
#      using this redis: wrong host/db, dead client).
for i in $(seq 1 18); do
  N=$(kubectl exec -n office $POD -- redis-cli -n 4 --scan --pattern 'affine_job:*' | wc -l | tr -d ' ')
  echo "t=$((i*10))s affine_job keys in db4: $N"; [ "$N" -ge 10 ] && break; sleep 10
done
#      PASS: >= 10 (baseline 22). FAIL: still < 10 after 180 s -> STOP, rollback.
kubectl exec -n office $POD -- redis-cli -n 4 --scan --pattern 'affine_job:doc:*' | head
#      expect the doc queue keys (meta / id / events / findEmptySummaryDocs)

# V5 — clients reconnected. A fresh redis with no AFFiNE shows 1 (our own
#      redis-cli). FAIL: < 10.
kubectl exec -n office $POD -- redis-cli info clients | grep '^connected_clients'
#      PASS: >= 10 (baseline 14)

# V6 — the consumer side: AFFiNE did NOT restart and stopped erroring.
kubectl get pod -n office -l app.kubernetes.io/instance=affine \
  -o 'custom-columns=NAME:.metadata.name,RESTARTS:.status.containerStatuses[0].restartCount,START:.status.startTime'
#      PASS: same NAME/START/RESTARTS as pre-check (e). A new pod or a
#      restart increment means ioredis did not recover in-process -> investigate.
#      Then, at least 3 min after the new redis pod went Ready. INFORMATIONAL,
#      NOT a PASS criterion (review 2026-09-26): its PASS is an absence (0) and
#      no non-zero reading of this exact command is demonstrated. The
#      2026-09-24 burst is outside kubelet log retention (~11 h at this pod's
#      VERBOSE rate; `--since=40h` matched 0 lines on 2026-09-26). The
#      "client reconnected" property is gated by V4 and V5, which both FAIL
#      on a dead client.
kubectl logs -n office deploy/affine -c main --since=2m | grep -ciE 'ETIMEDOUT|ECONNREFUSED'
#      Record the count. Also record the same grep with --since=6m right after
#      V4 (it spans the swap): a non-zero reading there is the positive
#      control this query lacks; cite it in the run record if it fires.

# V7 — end-to-end app answer via the service (no public hostname needed).
kubectl port-forward -n office svc/affine 13010:3010 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s http://127.0.0.1:13010/info | grep -c '"message":"AFFiNE 0.27.4 Server"'   # PASS: 1
#      (a status code alone cannot fail: the SPA fallback answers 200 on ANY
#      path, measured 2026-09-26; the JSON body is served only by the API.)
kill $PF 2>/dev/null
#      Attended: also open AFFiNE in a browser and load one existing doc;
#      content must render (not an empty shell) and an edit must persist
#      after reload.
```

Success = V1–V7 all PASS. V4 and V5 are the load-bearing gates; V1/V2 are
shape checks that only prove the new image runs.

## 5) Rollback

Nothing forward-only happens (no persistence, no migration, no volume), so a
revert is the complete procedure. Queue state is rebuilt by AFFiNE's crons
from Postgres either way.

```bash
cd /Users/mu/code/cberg-home-nextgen
SHA=$(git log -1 --format=%H -- kubernetes/apps/office/affine/app/redis-helmrelease.yaml)
git show --stat $SHA          # confirm it is the 8.10.2 bump commit
git revert --no-edit $SHA
git log -1 --format=%s        # confirm it is YOUR revert subject
git push
```

Confirm the cluster is back:
```bash
kubectl get deploy -n office affine-redis -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # redis:8.10.1-alpine
POD=$(kubectl get pod -n office -l app.kubernetes.io/instance=affine-redis -o name); POD=${POD##*/}
kubectl get pod -n office $POD -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'                # …sha256:becdda6c…
kubectl get helmrelease -n office affine-redis -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}{"\n"}'  # True
```
Then re-run V4 and V5 against the reverted pod — a rollback is only done when
AFFiNE is writing to it again.

If Helm is wedged `pending-upgrade`, follow `docs/sops/application-update.md`
§11 (`helm rollback affine-redis <rev> -n office --wait=false`, then
`flux reconcile helmrelease -n office affine-redis --force`).

## 6) Interference notes

- **Blast radius: one app.** `affine-redis` is consumed only by
  `deployment/affine` (and its `predeploy` init container at pod start). No
  other `office` workload uses it; nothing shared → `shared: []`.
- **No storage risk.** No volume on the redis pod (premise
  `redis-mounts-no-volume`). AFFiNE's Longhorn volumes and `affine-pg` are not
  touched. Storage-safety pre-flight N/A.
- **AFFiNE is not restarted.** The `wait-for-redis` init container only gates
  a fresh AFFiNE pod; this change does not roll AFFiNE. Keep this plan out of
  any window that also bumps the AFFiNE app image, so each is verified alone
  (no such plan exists today).
- **`conflicts_with: [helm-drift-detection]`**: that plan's §4.1 compares Helm
  revision numbers across all releases and would fail on this upgrade. The
  reciprocal entry should be added to `helm-drift-detection` (not edited here —
  planner writes only its own file).
- **Not Prometheus-verified** — §4 reads redis and AFFiNE directly, so no
  conflict with `kube-prometheus-stack-91.4.1` is needed.
- **Timing:** not before 2026-09-26T21:05Z (G5 cooldown, pre-check b). No
  reboot, low risk weight, ~15 min. The plan derives **AUTO-NIGHT**
  (`maintenance-plan.py --json` execution_classes, 2026-09-26), so once
  vetted it may run in any window after the cooldown; the first is nightly
  2026-09-27 03:30. It does NOT become a Step-0 AUTO item after the
  cooldown: the `*affine*` deny rule has no `max:`, so coverage.py's
  `deny_rule_for('affine-redis', 'patch')` still blocks it (verified
  2026-09-26). Narrowing that glob is the only way to retire this plan in
  favour of Step 0.
- **Same HelmRelease, second held item:** F-e4bffed7 (affine-redis chart
  5.1.0 -> 5.2.1, held by the same glob) has no plan yet. Any plan for it
  touches `helmrelease/affine-redis` and must be serialized with this one.
