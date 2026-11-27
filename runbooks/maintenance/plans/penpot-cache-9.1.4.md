---
plan_id: penpot-cache-9.1.4
component: penpot-cache
pr: 561                               # renovate/valkey-valkey-9.1.x "update valkey/valkey ( 9.1.3 → 9.1.4 )", opened
                                      # 2026-11-19T02:51Z; one file (penpot-cache/app/helmrelease.yaml), MERGEABLE, CI green
                                      # (Flate Render Gate, Flux Local Diff x2, Labeler). Held ONLY by the `*valkey*` deny rule.
                                      # Steps edit main directly; Renovate auto-closes the PR once main carries 9.1.4.
kind: image
current: "9.1.3"                      # live 2026-11-19: deploy spec valkey/valkey:9.1.3, INFO server valkey_version:9.1.3,
                                      # pod imageID sha256:3add1a33... (= registry index digest of 9.1.3)
target: "9.1.4"                       # fixed GA patch on the SAME 9.1 line; NOT the floating 9.2 (rc) series
update_type: patch
risk: low                             # stateless cache (--save "" / --appendonly no, no PVC, DBSIZE 0), standalone
                                      # (cluster_enabled:0), one consumer app, no schema, no persistence to migrate
est_duration_min: 12
needs_reboot: false
touches:
  namespaces: [office]
  resources:
    - helmrelease/penpot-cache        # image tag edit (the only file changed)
    - deployment/penpot-cache         # strategy Recreate -> ~10-30 s cache outage
    - deployment/penpot-backend       # NOT edited; lettuce client drops + reconnects
    - deployment/penpot-exporter      # NOT edited; holds client connections, reconnects
  shared: [monitoring]                # no PVC, no route, not a shared redis. `monitoring` only because §4 CONTROLs
                                      # read Prometheus (the window instrument), never perturbed by this change.
depends_on: []
conflicts_with: [penpot-cache-9.2, kube-prometheus-stack-93.3.0, flux-reconciler-impersonation]
  # penpot-cache-9.2 (blocked): same file, same line. Its premise manifest-pin-still-9.1.2 already fails
  #   (pin is 9.1.3 since 1453e114d); reciprocal conflict added there 2026-11-19; when refreshed, its baseline and rollback target must read 9.1.4.
  # kube-prometheus-stack-93.3.0 (draft): §4 CONTROLs read kube-state-metrics through Prometheus. That plan
  #   lists penpot-cache-9.2 but not this id; reciprocity added there 2026-11-19.
  # flux-reconciler-impersonation (blocked): changes how helm/kustomize controllers apply in every namespace
  #   incl. office; a same-night change would make a failed apply here ambiguous.
exclusive: false
security_ref: F-a7f596b9              # AR-029 register row for valkey/valkey:9.1.3 (the CURRENT tag). Upstream marks
                                      # 9.1.4 urgency SECURITY. Detail stays in the DB; no IDs or counts in this file.
capability_change: false              # same-behaviour bug/security patch on the same minor line; no new
                                      # command, config, route, permission or exposure
rollback_class: git-revert            # no persistence: nothing on disk 9.1.3 could fail to read
finding_refs: []                      # No version finding exists yet: `finding list --grep penpot --all` and
                                      # `--grep 9.1.4 --all` (2026-11-19) return none for penpot-cache 9.1.3 -> 9.1.4;
                                      # the last sweep (2026-11-18 03:11Z) predates the upstream release (20:29Z).
                                      # When the next sweep files "penpot-cache: image valkey/valkey 9.1.3 → 9.1.4
                                      # (patch)", ADD its F-id here or the plan-or-page pass reads it as unplanned.
review: null
status: draft
window: null
premises:
  - id: live-image-still-9.1.3
    why: >-
      `current:` claims 9.1.3. If the deployment already moved (Step 0 or a manual
      bump), the baseline and rollback target are wrong and the step-1 sed is a no-op.
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
      If someone enabled persistence, a revert could face a file written by 9.1.4.
      (Reads the declared command; §2.4 confirms live with INFO persistence, since the runner refuses kubectl exec.)
    run: kubectl get helmrelease penpot-cache -n office -o jsonpath="{.spec.values.controllers['penpot-cache'].containers.app.command}"
    expect_exact: '["valkey-server","--save","","--appendonly","no"]'
sops_refs:
  - docs/sops/application-update.md
generated: "2026-11-19"
needs_replan: "minor-or-major-drift: upstream moved 9.1.4 -> 9.2.1 (minor); a re-assessment is needed"
needs_replan_since: "2026-11-27"
---

# penpot-cache: valkey 9.1.3 -> 9.1.4 (GA patch on the pinned line; held only by the interim `*valkey*` rule)

## 1. Summary & why held

`penpot-cache` (namespace `office`) is a cache-only Valkey (bjw-s app-template 5.3.0,
`strategy: Recreate`, `--save ""`, `--appendonly no`, no PVC, no auth, standalone, `DBSIZE 0`)
serving Penpot's backend and exporter on Service `penpot-cache:6379`. The previous hop on this
line (9.1.2 -> 9.1.3) ran through the identical plan shape and landed unattended in the nightly
window on 2026-11-06 (`1453e114d`, SD-10).

**9.1.4 is a stable GA, not the digest-twin the hold was written about.** Measured 2026-11-19:

| Probe | Result |
|---|---|
| `valkey/valkey:9.1.4` | HTTP 200, index digest `sha256:3ab0eca8...` |
| `valkey/valkey:9.1` (floating) | HTTP 200, **same** `sha256:3ab0eca8...` (expected: the 9.1 pointer moved to the newest 9.1 GA) |
| `valkey/valkey:9.1.3` (current) | HTTP 200, `sha256:3add1a33...` (= live pod imageID) |
| `valkey/valkey:9.2.0-rc1` / `9.2.0-rc2` / `9.2` | `92f726cf...` / `2aff0c1e...` / `247b5e73...`, all different from 9.1.4 |
| `valkey/valkey:9.1.4-rc1`, `9.1.5`, `9.2.0` | 404 |
| GitHub `valkey-io/valkey` release `9.1.4` | `isPrerelease:false`, **Latest**, published 2026-11-18T20:29Z |

**Why held.** The `*valkey*` deny rule (interim, 2026-09-21) in
`runbooks/auto-update-policy.yaml` blocks every valkey update in both lanes, Renovate PR #561
included. It was written about the floating `9.2` = `9.2.0-rc1` pre-release; a fixed patch on the
already-pinned 9.1 line is not that hazard. This is the second consecutive 9.1.x patch the rule
has pushed into the plan queue (9.1.3 was the first).

**Upstream evidence (9.1.4 release notes, GitHub release body).** "Upgrade urgency SECURITY: This
release includes security fixes we recommend you apply as soon as possible." One security fix
plus ~70 bug fixes: crash/overflow fixes in eviction, HyperLogLog, Lua/scripting, SORT, streams,
modules, cluster bus and Sentinel; command-metadata corrections; memory-leak fixes; credential
redaction for rejected AUTH/HELLO/MIGRATE in MONITOR/commandlog. **There is no "Behavior Change"
section, no config rename, no removed command and no new required flag.** Nothing touches the
plain RESP standalone path Penpot's lettuce client uses. Vulnerability detail is on the DB record
(`security_ref`), not here.

**Coverage's `security_driven` flag is a false positive by provenance** (repo correction, see §6):
the "security marker in reason" match comes from the deny rule's own reason text, which contains
`security_ref: F-aff597aa, ...` (`coverage.py::_GROUP_SEC_MARKERS` substring-matches "security").
It happens to coincide with a real upstream SECURITY urgency this time, but the signal would fire
on any valkey hop, including a pure bug-fix release.

**Deny-rule narrowing (recommendation for the operator, NOT done by this plan).** The rule has no
`max:`, so it blocks patch, minor and major alike. Both gates already support `max:`
(`auto-update.py::policy_block` and `coverage.py::deny_rule_for` in lockstep: a matching rule with
`max: patch` blocks only an update ranked above patch and is a decisive allow otherwise). Adding
`max: patch` to the `*valkey*` rule would:
- let a 9.1.x patch like this one take the normal safe lane (G3 release-note scan, G4 CI, 24 h
  patch cooldown, Step 0 health gate + auto-revert);
- keep blocking 9.1.x -> 9.2 / 9.2.0 (minor) in both lanes, which is exactly the RC hazard the rule
  names, and coverage's floating-series arity check still independently routes `9.2` to PLAN.
Its residual gap: a patch-ranked tag that is itself an RC twin would pass. Valkey publishes RCs
only for new minors (`9.2.0-rc*`); no `9.1.x-rc*` tag exists (`9.1.4-rc1` -> 404). Also update the
rule's stale fact line ("9.1.3, 9.1.4 and 9.2.0 all return HTTP 404": 9.1.3 and 9.1.4 now exist)
and bump the policy `version`. A separate, reviewed policy change; out of this window.

**Release age.** Published 2026-11-18T20:29Z. The patch cooldown (`minimum_release_age_hours_by_type.patch: 24`)
is a gate of the unattended lanes, not of a plan, but the window agent should not run this before
2026-11-19T20:29Z unless it deliberately waives age for a SECURITY release; the nightly of
2026-11-20 (03:30) is already past it.

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen

# 2.1 (replaces a premise: the runner refuses gh/curl) target is GA and not an RC twin
gh release view 9.1.4 -R valkey-io/valkey --json isPrerelease,publishedAt
# PASS: "isPrerelease":false. FAIL: true, or "release not found".
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:valkey/valkey:pull" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
for t in 9.1.4 9.2.0-rc1 9.2.0-rc2; do
  printf '%-12s ' "$t"
  curl -s -I -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json" \
    "https://registry-1.docker.io/v2/valkey/valkey/manifests/$t" \
    | grep -i -E '^HTTP|docker-content-digest' | tr -d '\r' | tr '\n' ' '; echo
done
# PASS: 9.1.4 -> HTTP/2 200 with digest sha256:3ab0eca823eb... and NOT equal to either rc line.
# FAIL: 404, or a digest equal to an rc line, or a digest other than 3ab0eca8... (tag re-pushed:
#   STOP and re-plan; §4.1 pins this digest).

# 2.2 PR still targets 9.1.4 and is green (a Renovate retarget would change the target)
gh pr view 561 --json title,state,mergeable -q '.title+" "+.state+" "+.mergeable'
# PASS: "fix(container): update valkey/valkey ( 9.1.3 → 9.1.4 ) OPEN MERGEABLE". FAIL: a different target -> re-plan.

# 2.3 premises
.venv/bin/python3 runbooks/plan-premises.py penpot-cache-9.1.4 --require-premises

# 2.4 baseline (2026-11-19: valkey_version:9.1.3, DBSIZE 0,
#     CLIENT LIST = backend 10.69.2.196 x4, exporter 10.69.2.117 x2, local cli 127.0.0.1 x1)
kubectl exec deploy/penpot-cache -n office -- valkey-cli INFO server | grep -i valkey_version
kubectl exec deploy/penpot-cache -n office -- valkey-cli INFO persistence | grep -i -E 'aof_enabled|rdb_changes_since_last_save'
# PASS: aof_enabled:0 (2026-11-19: aof_enabled:0, rdb_changes_since_last_save:0). FAIL: aof_enabled:1 -> STOP, re-plan rollback_class.
kubectl exec deploy/penpot-cache -n office -- valkey-cli CLIENT LIST | awk '{print $2}' | cut -d= -f2 | cut -d: -f1 | sort | uniq -c
kubectl get pod -n office -l app.kubernetes.io/name=penpot-backend \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.podIP}{" restarts="}{.status.containerStatuses[0].restartCount}{"\n"}{end}'
kubectl get pod -n office -l app.kubernetes.io/name=penpot-exporter \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.podIP}{" restarts="}{.status.containerStatuses[0].restartCount}{"\n"}{end}'
# RECORD both pod names + restart counts (2026-11-19: penpot-backend-684f5f4f55-68hrc 0, penpot-exporter-578d54fc6-wrvsv 0).

# 2.5 baseline redis error noise in the backend (2026-11-19, 24 h: 0)
kubectl logs deploy/penpot-backend -n office -c penpot-backend --since=30m | grep -i -c -E 'RedisCommandTimeout|RedisConnectionException|Connection refused'

# 2.6 Flux healthy for the release
flux get helmreleases -n office | grep -E 'NAME|penpot'
# PASS: penpot-cache READY True (2026-11-19: v16, app-template@5.3.0).
```

No backup step: the cache holds no durable state (`--save ""`, `aof_enabled:0`, no PVC, `DBSIZE 0`).
No storage operation of any kind is in this plan (the namespace's CIFS PVC `penpot-assets` is not
touched; nothing is deleted).

## 3. Steps

1. Edit the pin. Dry-tested 2026-11-19 on a scratch copy with BSD sed; resulting diff was exactly
   `38c38` / `<               tag: "9.1.3"` / `>               tag: "9.1.4"` (one line changed).

   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   sed -i '' 's/tag: "9\.1\.3"/tag: "9.1.4"/' kubernetes/apps/office/penpot-cache/app/helmrelease.yaml
   git diff kubernetes/apps/office/penpot-cache/app/helmrelease.yaml   # exactly one changed line
   grep -n 'tag: "9\.' kubernetes/apps/office/penpot-cache/app/helmrelease.yaml   # must read "9.1.4", never bare 9.1 / 9.2
   ```

2. Commit only that file and push (`--only` because the worktree is shared):

   ```bash
   git commit --only kubernetes/apps/office/penpot-cache/app/helmrelease.yaml \
     -m "chore(penpot-cache): valkey 9.1.3 -> 9.1.4 (plan penpot-cache-9.1.4, closes PR #561)"
   git log -1 --format=%s          # confirm the subject is YOURS before pushing; amend if not
   git show --stat HEAD            # exactly one file
   git push
   ```

3. Let the Flux webhook reconcile (no manual reconcile). `Recreate` means a 10-30 s window where
   Penpot's backend logs redis connection errors while lettuce reconnects. Penpot sessions are
   not stored in this cache; open editors may see a brief realtime-sync hiccup.

4. If PR #561 did not auto-close within one Renovate run:
   `gh pr close 561 --comment "landed via plan penpot-cache-9.1.4"`.

## 4. Verification

Run from T+3 min after the new pod is Ready (lettuce reconnect grace).

```bash
# 4.1 running binary is the pinned patch (contents, not the tag)
kubectl get deploy penpot-cache -n office -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl get pod -n office -l app.kubernetes.io/name=penpot-cache \
  -o jsonpath='{range .items[*]}{.status.containerStatuses[0].image}{" "}{.status.containerStatuses[0].imageID}{"\n"}{end}'
kubectl exec deploy/penpot-cache -n office -- valkey-cli INFO server | grep -i valkey_version
# PASS: deploy spec == valkey/valkey:9.1.4; exactly ONE pod line, image docker.io/valkey/valkey:9.1.4 and
#   imageID ending sha256:3ab0eca823ebbf0fe352476ebac330ac9e5f14b592b9a954eab296d341e81b0e; INFO prints
#   valkey_version:9.1.4.
# The digest gate is valid now: on 2026-11-19 the live 9.1.3 pod's imageID (sha256:3add1a33...) EQUALS the
#   registry index digest of 9.1.3, so the same comparison against 3ab0eca8... can pass and can fail.
# FAIL shapes: valkey_version:9.1.3 / imageID 3add1a33... = Recreate did not happen or HR stuck;
#   two pod lines = old pod still terminating (wait, re-run); any 9.2.* = wrong tag (rollback).

# 4.2 real round-trip on a scratch DB (penpot uses db 0)
kubectl exec deploy/penpot-cache -n office -- valkey-cli -n 15 SET plan:penpot-cache-9.1.4 ok EX 60
kubectl exec deploy/penpot-cache -n office -- valkey-cli -n 15 GET plan:penpot-cache-9.1.4
# PASS: GET prints `ok`. FAIL: (nil) or an error.

# 4.3 consumers reconnected (the load-bearing consumer gate)
kubectl exec deploy/penpot-cache -n office -- valkey-cli CLIENT LIST | awk '{print $2}' | cut -d= -f2 | cut -d: -f1 | sort | uniq -c
kubectl get pod -n office -l app.kubernetes.io/name=penpot-backend -o jsonpath='{.items[0].status.podIP}{"\n"}'
kubectl get pod -n office -l app.kubernetes.io/name=penpot-exporter -o jsonpath='{.items[0].status.podIP}{"\n"}'
# PASS: the backend pod IP appears with >= 1 connection AND the exporter pod IP with >= 1
#   (baseline 2026-11-19: backend 10.69.2.196 x4, exporter 10.69.2.117 x2, cli 127.0.0.1 x1).
# FAIL: only 127.0.0.1 listed -> the apps never reconnected. If still failing at T+10 min, rollback (§5)
#   does not fix a client that will not reconnect; restart the consumer is a cberg-agent action to raise,
#   not part of this plan.

# 4.4 POSITIVE gate: the exporter's pub/sub subscription is re-established on the new server, and the backend's Lettuce
#   clients are attached and issuing commands (the penpot backend emits NO redis success log line: measured 2026-11-19, a
#   1 h backend log window held no redis/lettuce line at all, so an absence-of-errors grep reads zero on a dead link too).
kubectl exec deploy/penpot-cache -n office -- valkey-cli PUBSUB NUMSUB penpot.exporter.default.job-cancel
kubectl exec deploy/penpot-cache -n office -- valkey-cli CLIENT LIST | grep -c 'lib-name=Lettuce'
kubectl exec deploy/penpot-cache -n office -- valkey-cli INFO stats | grep -E 'total_commands_processed|total_connections_received'
# PASS (all three, re-run at T+5 and T+10 min): line 2 of NUMSUB prints exactly 1 (baseline 2026-11-19 on 9.1.3: 1);
#   the Lettuce count is >= 1 (baseline 4); total_commands_processed is > 0 and GROWS between the two runs (a fresh process
#   starts at ~0 and the clients' PING/BLPOP traffic is continuous: 554k commands in 145 d on 9.1.3).
# FAIL: NUMSUB prints 0 (exporter never re-subscribed; control measured 2026-11-19: `PUBSUB NUMSUB nosuch.channel` prints 0),
#   the Lettuce count is 0 (backend did not reconnect), or total_commands_processed does not grow.
# Secondary, informational only (NOT a gate): backend redis errors during the 10-30 s Recreate are EXPECTED:
#   kubectl logs deploy/penpot-backend -n office -c penpot-backend --since=5m | grep -i -c -E 'RedisCommandTimeout|RedisConnectionException|Connection refused'
#   Pattern proven able to match (case-insensitive):
#   echo 'io.lettuce.core.RedisCommandTimeoutException: Command timed out' | grep -i -c -E 'RedisCommandTimeout|RedisConnectionException|Connection refused'  -> 1

# 4.5 floor, not the gate
kubectl get deploy penpot-backend penpot-frontend penpot-exporter -n office
flux get helmreleases -n office | grep penpot
```

CONTENTS ASSERTION: the cache serves reads and writes on the 9.1.4 binary and Penpot's clients are
attached to it, measured by 4.1 (`valkey_version:9.1.4` reported by the running process plus pod
imageID == registry digest `3ab0eca8...`), 4.2 (SET/GET round-trip returns `ok`) and 4.3 (backend
and exporter pod IPs present in `CLIENT LIST`), against the 2026-11-19 baseline of 4 backend + 2
exporter connections on 9.1.3.

CONTROL: metric kube_pod_container_info - `{namespace="office",container="app",pod=~"penpot-cache.*"}` must return exactly one series whose `image` label is `docker.io/valkey/valkey:9.1.4` (a stale `docker.io/valkey/valkey:9.1.3` series FAILS the gate).
CONTROL: metric kube_deployment_status_replicas_available - `{namespace="office",deployment="penpot-cache"}` must be 1 for 10 min after rollout (baseline 1).
CONTROL: metric kube_pod_container_status_restarts_total - `{namespace="office",pod=~"penpot-(backend|exporter).*"}`: compare per pod name against the §2.4 record (2026-11-19: both 0); PASS = unchanged. A consumer crash-looping on reconnect shows here first.

## 5. Rollback

Stateless and forward-safe: the cache writes no RDB/AOF (premise `cache-is-still-non-persistent`),
so 9.1.3 has nothing to be unable to load. No forward-only step exists in this plan.

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
then re-run §4.2-4.4 against 9.1.3. If the HelmRelease is stuck `pending-upgrade` or remediation
has already rolled back, follow `docs/sops/application-update.md`
(`helm rollback penpot-cache <last-deployed> -n office --wait=false`) before the revert lands.
A revert leaves PR #561 open (or re-opens Renovate's proposal); the deny rule holds it again.

## 6. Interference notes

- Only Penpot depends on this cache (penpot HelmRelease `config.redis.host: penpot-cache`; live
  client list shows backend + exporter only). penpot-backend also has a `wait-for-redis` init
  container: if the backend pod happens to restart during the Recreate, it waits for the cache
  instead of crash-looping. nextcloud/affine/sure/paperless redis are separate Deployments.
- Shares the same file and line as `penpot-cache-9.2` (blocked): serialize, never same window.
  That plan's baseline/rollback target (9.1.2) is already stale; after this lands it must read 9.1.4.
- `kube-prometheus-stack-93.3.0` (draft) is the window instrument for §4 CONTROLs; do not stack. Its
  `conflicts_with` names `penpot-cache-9.2` but not this id: add `penpot-cache-9.1.4` there
  (reciprocity added 2026-11-19 in that plan's conflicts_with). If Step 0 lands any kube-prometheus-stack bump the same night,
  run this plan's CONTROLs only after Prometheus is back, or treat them as unavailable and rely on
  4.1-4.3.
- The `*valkey*` deny rule stays in place through this window; this manual, reviewed bump is
  unaffected by it.
- Repo corrections (none performed here; raise each separately):
  1. `runbooks/auto-update-policy.yaml` `*valkey*`: add `max: patch` and refresh the stale
     "9.1.3, 9.1.4 ... 404" fact line, bump `version` (§1). Without it every future 9.1.x patch
     lands in the plan queue.
  2. `runbooks/coverage.py::_member_security` (`_GROUP_SEC_MARKERS`) matches "security" inside a
     deny-rule reason that merely cites `security_ref:` F-ids, so every valkey hop is reported
     `security_driven` regardless of the release. The marker scan should not read deny-rule reason
     text (or should strip `security_ref:` citations first).
  3. The header comment of `kubernetes/apps/office/penpot-cache/app/helmrelease.yaml` said the
     Service is `penpot-cache-primary`; the live Service is `penpot-cache` and no `-primary` object
     exists. Comment corrected in the same commit as this plan revision (comment only, renders identically).
  4. The floating `valkey/valkey:9.2` digest (`247b5e73...`) no longer equals `9.2.0-rc1`
     (`92f726cf...`, re-pushed) nor `9.2.0-rc2` (`2aff0c1e...`); the 9.2 plan's table is out of date.
     Still no GA 9.2.N (`9.2.0` -> 404), so its block stands.
