---
plan_id: penpot-cache-9.1.3
component: penpot-cache
pr: 450                               # renovate/valkey-valkey-9.1.x, CI green (Flate Render Gate, Flux Local Diff x2). Held ONLY by the
                                      # `*valkey*` deny rule in runbooks/auto-update-policy.yaml (see §1). Steps edit main directly; the PR
                                      # closes itself once main carries 9.1.3.
kind: image
current: "9.1.2"                      # live 2026-11-03: deploy image valkey/valkey:9.1.2, INFO server valkey_version:9.1.2
target: "9.1.3"                       # fixed GA patch tag on the SAME 9.1 line; NOT the floating 9.2 (rc) series
update_type: patch
risk: low                             # stateless cache (--save "" / --appendonly no, no PVC, DBSIZE 0), one consumer app, no schema
est_duration_min: 12
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/penpot-cache        # image tag edit
    - deployment/penpot-cache         # strategy Recreate -> ~10-30s cache outage
    - deployment/penpot-backend       # NOT edited; lettuce client drops + reconnects
    - deployment/penpot-exporter      # NOT edited; one client connection, reconnects
  shared: []                          # dedicated cache, no PVC, no route; not a shared redis. Reads Prometheus in §4 (window instrument).
depends_on: []
conflicts_with: [penpot-cache-9.2, flux-reconciler-impersonation]
  # penpot-cache-9.2: same file, same line (`tag: "9.1.2"`). Its premise manifest-pin-still-9.1.2 anchors on the old
  #   pin and will FAIL after this lands; that plan is blocked anyway (no GA 9.2.N). When it is refreshed its baseline
  #   and rollback target must read 9.1.3.
  # flux-reconciler-impersonation: changes how kustomize/helm controllers apply in every namespace incl. office; a
  #   same-night change would make a failed apply here ambiguous.
  # No kube-prometheus-stack plan is open; if Step 0 lands a kube-prometheus-stack bump the same night, serialize
  #   (§4 reads Prometheus).
exclusive: false
security_ref: F-8b7f72a0              # AR-029 acceptance row for valkey/valkey; upstream marks 9.1.3 urgency SECURITY. Detail stays in the DB.
capability_change: false              # same-behaviour patch on the same minor line
rollback_class: git-revert            # no persistence: nothing on disk for 9.1.2 to be unable to read
finding_refs: [F-cfbc2a5f]            # "penpot-cache: image valkey/valkey 9.1.2 -> 9.1.3 (patch)"
review: ready-for-go@2026-11-03   # plan-reviewer 2026-11-03: needs-fix (imageID digest gate false-FAIL, unfailable absence gate), fixed, delta re-review ready-for-go
status: vetted
window: null
premises:
  - id: live-image-still-9.1.2
    why: >-
      `current:` claims 9.1.2. If the deployment already moved, the baseline and
      rollback target are wrong and the sed in step 1 is a no-op.
    run: kubectl get deploy penpot-cache -n office -o jsonpath='{.spec.template.spec.containers[0].image}'
    expect_exact: valkey/valkey:9.1.2
  - id: manifest-pin-still-9.1.2
    why: "The step-1 sed anchors on the exact string `tag: \"9.1.2\"`; a changed pin makes it a silent no-op."
    run: grep -c 'tag. "9.1.2"' /Users/mu/code/cberg-home-nextgen/kubernetes/apps/office/penpot-cache/app/helmrelease.yaml
    expect_exact: "1"
  - id: penpot-backend-points-at-penpot-cache
    why: "The consumer the §4 reconnect gate counts; if the redis host moved, that gate measures the wrong thing."
    run: kubectl get helmrelease penpot -n office -o jsonpath='{.spec.values.config.redis.host}'
    expect_exact: penpot-cache
sops_refs:
  - docs/sops/application-update.md
generated: "2026-11-03"
---

# penpot-cache: valkey 9.1.2 -> 9.1.3 (stable GA now exists; only the interim deny rule holds it)

## 1. Summary & why held

`penpot-cache` (namespace `office`) is a cache-only Valkey (bjw-s app-template 5.3.0,
`strategy: Recreate`, `--save ""`, `--appendonly no`, no PVC, no auth, standalone not cluster)
serving Penpot's backend and exporter on `penpot-cache:6379`.

**Question asked: does 9.1.3 exist as a stable tag and does the hold still apply?**

- **9.1.3 is a stable GA.** Measured 2026-11-03: Docker Hub `valkey/valkey:9.1.3` (also
  `-alpine`, `-trixie`) pushed 2026-10-27, index digest `sha256:3add1a336a92...`; GitHub release
  `9.1.3` is `Latest`, not a pre-release (published 2026-10-26). The digest differs from
  `9.2.0-rc1` (`sha256:92f726cf...`) and from `9.2` (still the RC line), so it is not the
  digest-twin the hold was written about. The 2026-09-21 reason ("GA list ends at 9.1.2; 9.1.3
  returns 404") is **no longer true**.
- **The hold still mechanically applies.** The `*valkey*` glob in
  `runbooks/auto-update-policy.yaml` blocks Renovate PR #450 (`9.1.2 -> 9.1.3`, CI green) and the
  coverage direct-bump lane. That is why this is a plan, not an auto-merge.
- **The hold is over-broad for this hop (repo correction, not done by this plan).** Its own
  removal condition is "a GA 9.2.x appears"; its target hazard is the floating 9.2 RC. A fixed
  patch tag on the already-pinned 9.1 line is neither. Recommend the operator narrow the rule in a
  separate reviewed policy change (for example deny only a target whose minor differs from the pin)
  so future 9.1.x patches stop landing in the plan queue. Not part of this window.

Why bump: upstream release notes (`00-RELEASENOTES`, 9.1 branch) mark 9.1.3 urgency **SECURITY**
(one security fix in cluster Pub/Sub message construction; this instance is not in cluster mode)
plus ~17 bug fixes (WATCH/tracking invalidation for stream group commands, RESTORE overflow
rejection, expire overflow rejection, a 9.0 -> 9.1.x listpack RDB compatibility fix, module/ACL
crash fixes). No *Behavior Change* section for 9.1.3, no config renames, no new required flags.
Nothing touches the plain RESP path Penpot's lettuce client uses. Vulnerability detail is on
`security_ref` in the DB, not here.

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.1 (replaces a premise: the runner refuses `gh`) the tag is GA and is not an RC twin
gh release view 9.1.3 -R valkey-io/valkey --json isPrerelease,publishedAt
# PASS: "isPrerelease":false. FAIL: true, or "release not found".
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:valkey/valkey:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in 9.1.3 9.2.0-rc1; do
  printf '%-12s ' "$t"
  curl -s -I -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json" \
    "https://registry-1.docker.io/v2/valkey/valkey/manifests/$t" \
    | grep -i -E '^HTTP|docker-content-digest' | tr -d '\r' | tr '\n' ' '; echo
done
# PASS: 9.1.3 -> HTTP 200 and a digest that is NOT equal to the 9.2.0-rc1 line. FAIL: 404, or equal digests.

# 2.2 premises
.venv/bin/python3 runbooks/plan-premises.py penpot-cache-9.1.3 --require-premises

# 2.3 baseline (2026-11-03: valkey_version:9.1.2, DBSIZE 0, CLIENT LIST = 4 backend + 1 exporter + 1 local cli)
kubectl exec deploy/penpot-cache -n office -- valkey-cli INFO server | grep -i valkey_version
kubectl exec deploy/penpot-cache -n office -- valkey-cli CLIENT LIST | awk '{print $2}' | cut -d= -f2 | cut -d: -f1 | sort | uniq -c

# 2.4 baseline redis error noise in backend (expect 0 outside bursts)
kubectl logs deploy/penpot-backend -n office --since=30m | grep -i -c -E 'RedisCommandTimeout|RedisConnectionException|Connection refused'

# 2.5 Flux healthy
flux get helmreleases -n office | grep -E 'NAME|penpot'
```

No backup step: the cache holds no durable state (`--save ""`, no PVC, keyspace empty).

## 3. Steps

1. Edit the pin. Dry-tested 2026-11-03 on a scratch copy with BSD sed; resulting diff was exactly
   `<               tag: "9.1.2"` / `>               tag: "9.1.3"` (line 38, one line changed).

   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' 's/tag: "9\.1\.2"/tag: "9.1.3"/' kubernetes/apps/office/penpot-cache/app/helmrelease.yaml
   git diff kubernetes/apps/office/penpot-cache/app/helmrelease.yaml   # exactly one changed line
   grep -n 'tag: "9\.' kubernetes/apps/office/penpot-cache/app/helmrelease.yaml   # must read "9.1.3", never bare 9.2
   ```

2. Commit only that file and push (message file written before the gate; `--only` because the
   worktree is shared):

   ```bash
   git commit --only kubernetes/apps/office/penpot-cache/app/helmrelease.yaml \
     -m "chore(penpot-cache): valkey 9.1.2 -> 9.1.3 (plan penpot-cache-9.1.3, closes PR #450)"
   git log -1 --format=%s          # confirm the subject is yours before pushing
   git show --stat HEAD            # exactly one file
   git push
   ```

3. Let the Flux webhook reconcile (no manual reconcile). `Recreate` means a 10-30 s window where
   Penpot's backend logs redis connection errors while lettuce reconnects. Penpot sessions are not
   stored in this cache.

4. Close the superseded Renovate PR if it did not auto-close: `gh pr close 450 --comment "landed via plan penpot-cache-9.1.3"`.

## 4. Verification

Run from T+3 min after the new pod is Ready (lettuce reconnect grace).

```bash
# 4.1 running binary is the pinned patch (contents, not the tag)
kubectl get deploy penpot-cache -n office -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl get pod -n office -l app.kubernetes.io/name=penpot-cache \
  -o jsonpath='{range .items[*]}{.status.containerStatuses[0].image}{" "}{.status.containerStatuses[0].imageID}{"\n"}{end}'
kubectl exec deploy/penpot-cache -n office -- valkey-cli INFO server | grep -i valkey_version
# PASS: deploy spec image == valkey/valkey:9.1.3; exactly one pod line whose image ENDS in valkey/valkey:9.1.3 (live prints a docker.io/ prefix);
#   INFO prints valkey_version:9.1.3 (the running binary reports its own version).
# NO imageID digest gate: the live 9.1.2 pod's imageID (sha256:a91d34ab...) was read 2026-11-03 and is NOT
#   the registry index digest (418652cf...) and was not reconciled with the amd64 platform manifest; I could
#   not explain it, so a digest compare would false-FAIL. Just RECORD the new pod's imageID for the log.
# FAIL shapes: valkey_version:9.1.2 = Recreate did not happen / HelmRelease stuck; two pod lines = old pod
#   still terminating (wait, re-run); a 9.2.* version = wrong tag pinned (rollback).

# 4.2 real round-trip on a scratch DB (penpot uses db 0)
kubectl exec deploy/penpot-cache -n office -- valkey-cli -n 15 SET plan:penpot-cache-9.1.3 ok EX 60
kubectl exec deploy/penpot-cache -n office -- valkey-cli -n 15 GET plan:penpot-cache-9.1.3
# PASS: GET prints `ok`. FAIL: (nil) or an error.

# 4.3 consumers reconnected (THIS is the load-bearing consumer gate)
kubectl exec deploy/penpot-cache -n office -- valkey-cli CLIENT LIST | awk '{print $2}' | cut -d= -f2 | cut -d: -f1 | sort | uniq -c
kubectl get pod -n office -l app.kubernetes.io/name=penpot-backend -o jsonpath='{.items[0].status.podIP}{"\n"}'
kubectl get pod -n office -l app.kubernetes.io/name=penpot-exporter -o jsonpath='{.items[0].status.podIP}{"\n"}'
# PASS: the backend pod IP appears with >= 1 connection AND the exporter IP with >= 1
#   (baseline 2026-11-03: backend 10.69.2.42 x4, exporter 10.69.0.155 x1, plus the cli's own 127.0.0.1).
# FAIL: only 127.0.0.1 listed -> the app never reconnected.

# 4.4 FLOOR only (an absence check): backend redis errors; window must cover the Recreate, so --since=15m
kubectl logs deploy/penpot-backend -n office --since=15m | grep -i -c -E 'RedisCommandTimeout|RedisConnectionException|Connection refused'
# Informational, not a pass/fail gate: errors during the 10-30 s Recreate are EXPECTED; read the count together
#   with 4.3. Only a count still rising after T+5 min (re-run, compare) is a FAIL signal.
# Pattern check: live 24h backend log on 2026-11-03 had zero redis/lettuce lines, so a real-world match could
#   not be observed; the 2026-09-24 burst was RedisCommandTimeoutException. Known-bad demo, run 2026-11-03:
#   echo 'io.lettuce.core.RedisCommandTimeoutException: Command timed out' | grep -i -c -E '<same pattern>'  -> 1

# 4.5 floor, not the gate
kubectl get deploy penpot-backend penpot-frontend penpot-exporter -n office
flux get helmreleases -n office | grep penpot
```

CONTENTS ASSERTION: the cache serves reads and writes on the 9.1.3 binary and Penpot's clients are
attached to it, measured by 4.1 (version plus image digest), 4.2 (SET/GET round-trip returns `ok`)
and 4.3 (backend and exporter pod IPs present in `CLIENT LIST`), against the 2026-11-03 baseline of
4 backend + 1 exporter connections on 9.1.2.

CONTROL: metric kube_pod_container_info - `{namespace="office",container="app",pod=~"penpot-cache.*"}` must return exactly one series whose `image` label is `docker.io/valkey/valkey:9.1.3` (read live 2026-11-03: one series, image `docker.io/valkey/valkey:9.1.2`, so a stale 9.1.2 series FAILS the gate).
CONTROL: metric kube_deployment_status_replicas_available - `{namespace="office",deployment="penpot-cache"}` must be 1 for 10 min after rollout.
CONTROL: metric kube_pod_container_status_restarts_total - `{namespace="office",pod=~"penpot-backend.*"}`: RECORD the reading BEFORE step 2 (live 2026-11-03: pod penpot-backend-7bb5c58999-rpqc6 = 0); PASS = unchanged after the rollout (a crash-looping backend on reconnect shows here first; a pod replaced meanwhile makes a new series, so compare per pod name).

## 5. Rollback

Stateless and forward-safe: the cache writes no RDB/AOF, so 9.1.2 has nothing to be unable to load.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-step-2>
git log -1 --format=%s ; git show --stat HEAD   # one file, the revert
git push
```

Confirm back:

```bash
kubectl get deploy penpot-cache -n office -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'   # valkey/valkey:9.1.2
kubectl exec deploy/penpot-cache -n office -- valkey-cli INFO server | grep -i valkey_version              # 9.1.2
```
then re-run §4.2-4.4 against 9.1.2. If the HelmRelease is stuck `pending-upgrade` or remediation has
already rolled back, follow `docs/sops/application-update.md` (`helm rollback penpot-cache <last-deployed> -n office --wait=false`)
before the revert lands. Note: a revert re-opens PR #450's trigger; Renovate will re-propose it and the deny rule will hold it again.

## 6. Interference notes

- Only Penpot depends on this cache (penpot HelmRelease `config.redis.host: penpot-cache`; client list shows backend + exporter only). The n8n `valkey:` values block is `enabled: false`; nextcloud/affine/sure/paperless redis are separate Deployments and untouched.
- Shares the same file and line as `penpot-cache-9.2` (blocked); serialize. `penpot-cache-9.2` should list `penpot-cache-9.1.3` in its own `conflicts_with` (reciprocity; that file was not edited here), and after this lands its baseline must be refreshed to 9.1.3.
- `*valkey*` deny rule stays in place through this window. This is a manual reviewed bump and is unaffected by it. Narrowing the rule is a separate policy change (§1).
- Repo correction noted, out of scope: the header comment in `kubernetes/apps/office/penpot-cache/app/helmrelease.yaml` says the Service is `penpot-cache-primary`; the live Service is `penpot-cache` and no `-primary` object exists.
- Window instrument: §4 CONTROLs read Prometheus (monitoring); do not stack with a same-night kube-prometheus-stack bump.
