---
plan_id: python-fleet-3.15.2-alpine
component: python                     # image fleet keyed on the Docker Official Image `python`, ALPINE variant
also_covers: [icloud-sync-probe, crash-ghost-reaper, elasticsearch-obs-recovery]
pr: null                              # direct-bump lane (coverage.py needs_plan_groups group python-fleet-3.15.2-alpine) - no Renovate PR
kind: image
current: "docker.io/library/python:3.14.10-alpine (alpine 3.24; two members digest-pinned @sha256:eb2c62658b8d51bff0acc408504b76521d02030de56a8a3c1e830083e89b89d2, crash-ghost-reaper tag-only) - live and in git 2026-11-03"
target: "docker.io/library/python:3.15.2-alpine, index digest sha256:20a82dbc2783112ddb91d1534603f802d222a3e63e593cd002eb2ac534e70211 (alpine 3.24, same base as today), on the same 3 consumers in one commit"
update_type: minor                    # CPython feature release 3.14 -> 3.15; Alpine base unchanged (3.14.10-alpine == 3.14.10-alpine3.24, 3.15.2-alpine == 3.15.2-alpine3.24, measured 2026-11-03)
risk: low                             # stdlib-only scripts, short CronJobs, no PVC/schema/state; the 3.15 removals touch no import they use (§1.2)
est_duration_min: 30                  # pre-checks 5 - edit/commit/push 3 - Flux apply 2 - wait for one tick of the slowest member (*/15) up to 15 - gates 5
needs_reboot: false
touches:
  namespaces: [backup, kube-system, monitoring]
  resources:
    - cronjob/icloud-sync-probe           # backup - Flux Kustomization backup/icloud-backup-freshness; CronJob only, sibling cronjob/icloud-backup-freshness NOT touched
    - cronjob/crash-ghost-reaper          # kube-system - Flux Kustomization kube-system/crash-ghost-reaper; the node-loss ghost-pod reaper (DRY_RUN=false, deletes pods)
    - cronjob/elasticsearch-obs-recovery  # monitoring - Flux Kustomization monitoring/elasticsearch; only this CronJob changes, statefulset elasticsearch-es-default NOT rolled
  shared: [monitoring]                    # elasticsearch-obs-recovery is the ES self-heal job and icloud-sync-probe pushes to the Pushgateway; both are the window's instruments (§4 reads them). No gateway, DNS, CNI, storage or Authentik surface.
depends_on: [python-fleet-3.15.2]         # soak ordering: the slim canary (openclaw-probe, mcpo init, mealie sync) goes first (§1.4); soft, a failed canary STOPs this plan
conflicts_with:
  # Re-read every non-terminal plan frontmatter 2026-11-03.
  - python-fleet-3.15.2                   # different slot, AFTER the canary (not a deadlock with depends_on); same interpreter move, same Flux commit stream; keep rollout cause singular (reciprocal entry is NOT in that plan: see §6)
  - icloud-drive-fleet-2.3.0              # rolls the icloud-docker pods whose logs icloud-sync-probe reads; a roll mid-gate reads as a sync outage
  - talos-linux-1.14.5                    # node reboot: CronJob ticks missed, gates in §4 would read stale
  - grafana-14.1.0                        # reads Prometheus in monitoring, same instrument as §4.4; window noise
  - edot-collector-0.164.0                # ES/otel ingestion restarts in monitoring blind the obs-recovery log read
  - tube-archivist-elasticsearch-9.5.5    # ES-family plan in the same instrument family; serialize
exclusive: false
autonomy_override: human-gated            # RESTRICTS only: a minor interpreter move is an attended-window item (same call as python-fleet-3.15.2)
capability_change: false                  # same scripts, same behaviour, new interpreter
rollback_class: git-revert                # nothing forward-only: ConfigMap scripts unchanged, no PVC, no schema
finding_refs: [F-6bf5a0aa, F-302480e4, F-eb7756e8, F-a9351f4e]   # version rows icloud-sync-probe / crash-ghost-reaper / elasticsearch-obs-recovery "3.14.10-alpine -> 3.15.2-alpine (minor)" (policy-cli finding list --grep, 2026-11-03), plus F-a9351f4e (coverage group id drops the tag variant)
premises:
  - id: sync-probe-on-3.14.10-alpine
    why: "`current:` claims icloud-sync-probe runs the digest-pinned 3.14.10-alpine. Any other value means 3.15 is already applied or the file moved shape (the section 3 sed would not match)."
    run: kubectl get cronjob icloud-sync-probe -n backup -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_matches: '^docker\.io/library/python:3\.14\.\d+-alpine@sha256:[0-9a-f]{64}$'
  - id: reaper-on-3.14.10-alpine
    why: "crash-ghost-reaper is the tag-only member (no digest)."
    run: kubectl get cronjob crash-ghost-reaper -n kube-system -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_matches: '^docker\.io/library/python:3\.14\.\d+-alpine$'
  - id: obs-recovery-on-3.14.10-alpine
    why: "elasticsearch-obs-recovery, digest-pinned."
    run: kubectl get cronjob elasticsearch-obs-recovery -n monitoring -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'
    expect_matches: '^docker\.io/library/python:3\.14\.\d+-alpine@sha256:[0-9a-f]{64}$'
review: ready-for-go@2026-11-03   # plan-reviewer 2026-11-03: needs-fix (4.1 zsh word-split loop), fixed, delta re-review ready-for-go; HUMAN-GATED, window null, after the python-fleet-3.15.2 canary
status: vetted
window: null
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/auto-update.md
  - docs/sops/verification-contents-not-shape.md
generated: "2026-11-03"
---

# python-fleet-3.15.2-alpine - python:3.14.10-alpine -> 3.15.2-alpine on icloud-sync-probe, crash-ghost-reaper, elasticsearch-obs-recovery

## 1. Summary & why held

One commit moves three inline `docker.io/library/python:3.14.10-alpine` pins to `3.15.2-alpine`
(digest-pinned where they were digest-pinned):

| Consumer | Object | What python does there | File |
|---|---|---|---|
| backup/icloud-sync-probe | CronJob `*/10` | `icloud_sync_probe.py`: reads icloud-docker pod logs via the K8s API, POSTs per-account gauges to the Pushgateway (`ssl`, `urllib`, `re`, `calendar`, `time.strptime`) | `kubernetes/apps/backup/icloud-backup-freshness/app/sync-probe-cronjob.yaml` |
| kube-system/crash-ghost-reaper | CronJob `*/15`, `DRY_RUN=false` | `reap.py`: lists all pods, force-deletes node-loss ghosts (`ssl`, `urllib`, `datetime.fromisoformat`) | `kubernetes/apps/kube-system/crash-ghost-reaper/app/cronjob.yaml` |
| monitoring/elasticsearch-obs-recovery | CronJob `*/10` | `obs_recovery.py`: ES health, rollover/delete of corrupt obs indices, Alertmanager notify (`ssl` with the ES CA, `urllib`) | `kubernetes/apps/monitoring/elasticsearch/app/obs-recovery-cronjob.yaml` |

**Why held.** `coverage.py` group `python-fleet-3.15.2-alpine`, reason: G3 breaking-change signal. The matched
text ("Migration/Upgrade Guide ... pyperformance ... 7-8% geometric mean") is the What's New performance
paragraph, a G3 false positive on wording, the same one recorded for the slim fleet. The real reason this still
needs a plan is that it is a CPython **minor** (3.14 -> 3.15). Not security-driven; no `security_ref`.

### 1.1 Relation to the existing plan `python-fleet-3.15.2` (read first, reconciled)

`runbooks/maintenance/plans/python-fleet-3.15.2.md` (vetted, `sat-attended:2026-11-14`) covers the **slim** variant
on a **different** set: ai/openclaw-probe, ai/mcpo init, office/mealie-shopping-sync. Its section 1.5 states
explicitly that these three alpine consumers are NOT covered (it names the same three version rows, F-6bf5a0aa,
F-302480e4, F-eb7756e8) and plans them as a "third step" after the slim canary soaks. So:

- **No overlap in edited files or objects.** The two plans are complementary, not duplicates.
- **The only collision is the group id**: `coverage.py` drops the tag variant (F-a9351f4e), so `3.15.2-alpine`
  and `3.15.2-slim` read as one group and the alpine trio looks "planned" by the slim plan. This plan is what
  actually plans them. Once it is filed, the trio stops reading as unplanned.
- **Repo correction**: the slim plan's `conflicts_with` does not (and should not need to) list this plan; the
  edge is declared one-way here via `depends_on` + `conflicts_with`. Add the reciprocal entry to the slim plan if
  the scheduler needs it (I did not touch that file).

### 1.2 Upstream evidence (3.15 / 3.15.2)

Sources: docs.python.org/3.15/whatsnew/3.15.html and the 3.15.2 changelog, as already read and recorded in the
slim plan section 1.2 (re-used, not re-fetched; the 3.15.2 tag content is unchanged).

- **Removed in 3.15** (none used by these scripts): `ast` strictness, `collections.abc.ByteString`,
  `ctypes.SetPointerType`, `datetime.strptime` with `%d` but no year, `glob.glob0/1`, `CGIHTTPRequestHandler`,
  `Loader.load_module`, `importlib.resources.files(package=)`, `PurePath.is_reserved`, `platform.java_ver`,
  `sre_*`, `RLock` extra args, `co_lnotab`, `typing.ByteString`, `zipimporter.load_module`.
  Checked against the three scripts' imports (`json os ssl sys re time calendar hashlib base64 urllib.* datetime`):
  the only date parsing is `time.strptime(head, "%Y-%m-%dT%H:%M:%S")` in the probe (has a year, unaffected by the
  year-less `%d` removal) and `datetime.fromisoformat(...)` in the reaper/recovery (unchanged API).
- **UTF-8 mode default (PEP 686)**: the scripts open only the ServiceAccount token/CA and a JSON known-file with
  no `encoding=`; all are ASCII/UTF-8 already. No effect.
- **3.15.2 fixes** include a 3.15.0 threaded-import regression (irrelevant, single-threaded) and an `ssl`
  change rejecting a set of compromised eMudhra intermediate CA keys. The reaper talks to the in-cluster API
  with its own cluster CA, obs-recovery to ES with the ES-issued CA, the probe to the API server and plain-http
  Pushgateway. None of these chains is a public CA, so the ssl change cannot apply. The gates in section 4 would
  catch it anyway (TLS failure => non-zero exit / `cannot reach ES` / `cannot list pods`).
- **Alpine**: both tags resolve to `alpine3.24` (digests of `3.14.10-alpine` and `3.14.10-alpine3.24` are identical,
  `eb2c6265...`; `3.15.2-alpine` equals `3.15.2-alpine3.24`, `20a82dbc...`). This is an interpreter-only change;
  musl/OpenSSL stay as they are. Image runs as uid 1000, `readOnlyRootFilesystem: true`; all three scripts write
  nothing to disk (the probe sets `PYTHONDONTWRITEBYTECODE=1`; the other two never need write access).
- **Tag facts**: `3.15.2-alpine` last_updated 2026-10-29T17:08Z, far past the 48 h minor cooldown (G5). 3.15.2 is
  still the newest 3.15 tag (3.15.1 and 3.15.0 only below it, 2026-11-03).

### 1.3 Blast radius

- **crash-ghost-reaper** is the only member that mutates the cluster (force-deletes node-loss ghost pods).
  A broken interpreter would silently stop reaping, which only matters after an ungraceful node loss. Not
  data-bearing. It deletes nothing on a healthy cluster (live 2026-11-03 21:30Z: `done - 0 pod(s) reaped`).
- **elasticsearch-obs-recovery** self-heals RED shards by rollover+delete on `.ds-(metrics|logs|traces)-*` only.
  On a green cluster it only reads health and checks write windows (live: `cluster status=green unassigned=0`).
  A failed run changes nothing; the failure mode is "no self-heal during the gap".
- **icloud-sync-probe**: monitoring-only; a failed run leaves the last pushed gauges ageing, which is exactly
  what its alerts watch. Baseline today: `account=andrea {'icloud_auth_required': 1}` (existing, unrelated).
- No member has a PVC, no HTTPRoute, no SSO path. No reboot.

### 1.4 Ordering

`depends_on: [python-fleet-3.15.2]`. The slim canary exercises the same interpreter on the same nodes first
(sat-attended:2026-11-14 suggestion); this plan should run after that has soaked at least one nightly. If the
canary is rolled back for an interpreter reason, STOP this plan. If the operator wants to run both in one window,
they are in different namespaces except `monitoring` (reads) and share no object, but keep them as two commits.

## 2. Pre-checks

Run from the repo root on the Mac mini. All read-only.

```bash
cd /Users/mu/code/cberg-home-nextgen
.venv/bin/python3 runbooks/plan-premises.py python-fleet-3.15.2-alpine --require-premises   # all 3 PASS

# 2.0 baseline: each file has exactly one 3.14.N-alpine python line. Prints "ok 3" or "STOP baseline-moved N=<n>".
N=$(grep -hcE 'docker\.io/library/python:3\.14\.[0-9]+-alpine(@sha256:[0-9a-f]{64})?$' \
  kubernetes/apps/kube-system/crash-ghost-reaper/app/cronjob.yaml \
  kubernetes/apps/monitoring/elasticsearch/app/obs-recovery-cronjob.yaml \
  kubernetes/apps/backup/icloud-backup-freshness/app/sync-probe-cronjob.yaml | paste -sd+ - | bc)
[ "$N" = 3 ] && echo "ok $N" || echo "STOP baseline-moved N=$N"
#   Fails (prints STOP) if any file is already on 3.15 or the line changed shape: that file counts 0.

# 2.1 target tag still resolves to the recorded index digest and is still alpine 3.24.
#     "ok-digest-matches" => proceed. "STOP-DIGEST-CHANGED <new>" => the tag was re-pushed (it was for the slim tag
#     once): STOP, re-measure, update NEW in section 3 and here, have the plan re-reviewed.
REC=sha256:20a82dbc2783112ddb91d1534603f802d222a3e63e593cd002eb2ac534e70211
GOT=$(curl -s https://hub.docker.com/v2/repositories/library/python/tags/3.15.2-alpine | python3 -c "import sys,json;print(json.load(sys.stdin)['digest'])")
[ "$GOT" = "$REC" ] && echo ok-digest-matches || echo "STOP-DIGEST-CHANGED $GOT"
A24=$(curl -s https://hub.docker.com/v2/repositories/library/python/tags/3.15.2-alpine3.24 | python3 -c "import sys,json;print(json.load(sys.stdin)['digest'])")
[ "$A24" = "$REC" ] && echo ok-alpine-3.24 || echo "STOP-BASE-MOVED $A24"
#   Measured 2026-11-03: both print ok.

# 2.2 no newer 3.15 bugfix (else retarget). Prints "ok-newest-3.15.2" or "STOP-NEWER <tag>".
curl -s "https://hub.docker.com/v2/repositories/library/python/tags/?name=3.15&page_size=100" | python3 -c "
import sys,json,re
t=[r['name'] for r in json.load(sys.stdin)['results'] if re.fullmatch(r'3\.15\.\d+-alpine',r['name'])]
m=max(t,key=lambda s:int(s.split('.')[2].split('-')[0]))
print('ok-newest-3.15.2' if m=='3.15.2-alpine' else 'STOP-NEWER '+m)"

# 2.3 the canary (python-fleet-3.15.2) is not rolled back and its members are healthy on 3.15.x-slim, or the operator waived it.
kubectl get cronjob openclaw-probe -n ai -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'; echo
#   Expect python:3.15.2-slim. If it still reads 3.14.x the canary has not run: operator decides to proceed or wait.

# 2.4 baselines to compare against in section 4 (save to the window log).
kubectl get cronjob icloud-sync-probe -n backup -o jsonpath='{.status.lastSuccessfulTime}{"\n"}'
kubectl get cronjob crash-ghost-reaper -n kube-system -o jsonpath='{.status.lastSuccessfulTime}{"\n"}'
kubectl get cronjob elasticsearch-obs-recovery -n monitoring -o jsonpath='{.status.lastSuccessfulTime}{"\n"}'

# 2.5 ES is green and no ghost pods pending before touching their healers (do not change the healer while it is needed).
kubectl logs -n monitoring "$(kubectl get pods -n monitoring -o name | grep elasticsearch-obs-recovery | tail -1)" | grep -E "cluster status="
#   Expect status=green. status=red => STOP: obs-recovery is actively working; do not swap its interpreter now.
```

If `ElasticsearchClusterRed` is firing in Alertmanager, STOP (the recovery job is actively needed).

## 3. Steps

GitOps only. Edit three lines, one commit.

```bash
cd /Users/mu/code/cberg-home-nextgen
OLD=sha256:eb2c62658b8d51bff0acc408504b76521d02030de56a8a3c1e830083e89b89d2
NEW=sha256:20a82dbc2783112ddb91d1534603f802d222a3e63e593cd002eb2ac534e70211   # = REC from 2.1

# reaper: tag-only line
sed -i '' -E 's#(docker\.io/library/python:)3\.14\.10-alpine$#\13.15.2-alpine#' \
  kubernetes/apps/kube-system/crash-ghost-reaper/app/cronjob.yaml
# digest-pinned lines (probe + obs-recovery): tag AND digest move together
sed -i '' -E "s#(docker\.io/library/python:)3\.14\.10-alpine@${OLD}\$#\13.15.2-alpine@${NEW}#" \
  kubernetes/apps/monitoring/elasticsearch/app/obs-recovery-cronjob.yaml \
  kubernetes/apps/backup/icloud-backup-freshness/app/sync-probe-cronjob.yaml
git diff --stat   # exactly 3 files, 1 line each
```

Dry-run on scratch copies (BSD sed, macOS, 2026-11-03) produced exactly:

```
31c31   -  image: docker.io/library/python:3.14.10-alpine
        +  image: docker.io/library/python:3.15.2-alpine
34c34   -  image: docker.io/library/python:3.14.10-alpine@sha256:eb2c6265...b89d2
        +  image: docker.io/library/python:3.15.2-alpine@sha256:20a82dbc...e70211     (obs-recovery-cronjob.yaml)
58c58   same digest swap                                                          (sync-probe-cronjob.yaml)
```

Note the comment in `sync-probe-cronjob.yaml` ("Same digest-pinned image as monitoring/elasticsearch-obs-recovery")
stays true because both move together. Do not edit any ConfigMap script.

```bash
git diff | grep -E '^[-+][^-+]' | grep -c 'python:'     # expect 6 (3 removed, 3 added)
git commit --only \
  kubernetes/apps/kube-system/crash-ghost-reaper/app/cronjob.yaml \
  kubernetes/apps/monitoring/elasticsearch/app/obs-recovery-cronjob.yaml \
  kubernetes/apps/backup/icloud-backup-freshness/app/sync-probe-cronjob.yaml \
  -m "chore(deps): python 3.14.10-alpine -> 3.15.2-alpine on icloud-sync-probe, crash-ghost-reaper, elasticsearch-obs-recovery"
git log -1 --format=%s        # confirm the subject is YOURS before pushing (shared worktree)
git show --stat HEAD          # exactly the 3 files
PY_SHA=$(git rev-parse HEAD); echo "$PY_SHA"      # keep for section 5
git push
```

Flux applies via the webhook; no manual reconcile. The CronJob template change takes effect on the NEXT tick of
each member; running Jobs are not interrupted. Wait for ticks (<= 15 min); do NOT `kubectl create job --from`
(that is a direct cluster mutation outside GitOps).

## 4. Verification

Every gate states what a failure prints. Run after the first tick of each CronJob following the push (up to 15 min).

**4.0 Live templates updated** (fails if Flux has not applied, or applied the wrong digest):

```bash
kubectl get cronjob icloud-sync-probe -n backup -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'; echo
kubectl get cronjob crash-ghost-reaper -n kube-system -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'; echo
kubectl get cronjob elasticsearch-obs-recovery -n monitoring -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}'; echo
```

PASS: `...python:3.15.2-alpine@sha256:20a82dbc...` (probe, recovery) and `...python:3.15.2-alpine` (reaper). Any `3.14.10` => not applied; check `flux get ks` for the three Kustomizations (`backup/icloud-backup-freshness`, `kube-system/crash-ghost-reaper`, `monitoring/elasticsearch`).

**4.1 The new interpreter actually ran** (a green Job on the OLD image would pass any exit-code check; the imageID is the proof; measured 2026-11-03: imageID shows the INDEX digest `docker.io/library/python@sha256:eb2c6265...` for the current pods, so it compares directly to the target index digest):

```bash
NEW=sha256:20a82dbc2783112ddb91d1534603f802d222a3e63e593cd002eb2ac534e70211
while read -r NS NAME; do
  set -- "$NS" "$NAME"
  kubectl get pods -n "$1" --sort-by=.metadata.creationTimestamp -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.phase}{" "}{.status.containerStatuses[0].imageID}{"\n"}{end}' | grep "$2" | tail -1 | tee /dev/stderr | grep -q "Succeeded .*@${NEW}$" && echo "PASS $2" || echo "FAIL-OR-NOT-YET $2"
done <<'EOF_MEMBERS'
backup icloud-sync-probe
kube-system crash-ghost-reaper
monitoring elasticsearch-obs-recovery
EOF_MEMBERS
```

PASS per member: the NEWEST pod is `Succeeded` and its imageID ends `@sha256:20a82dbc...`. `FAIL-OR-NOT-YET` with a
`3.14` digest (`eb2c6265...`) means no tick has happened since the apply: wait and re-run. `Failed`/`Error` with the new
digest is a real failure (go to 4.2 logs).

**4.2 Logs contain the success markers, not just exit 0** (case-insensitive; each marker is emitted only after the
script's real work, so an ssl/urllib break prints the failure line instead):

```bash
kubectl logs -n kube-system "$(kubectl get pods -n kube-system -o name | grep crash-ghost-reaper | tail -1)" | grep -iE "done|cannot list pods"
kubectl logs -n monitoring "$(kubectl get pods -n monitoring -o name | grep elasticsearch-obs-recovery | tail -1)" | grep -iE "cluster status=|done|cannot reach ES|Traceback"
kubectl logs -n backup -l app=icloud-sync-probe --tail=40 | grep -iE "pushed|FAILED|Traceback"
```

PASS: reaper prints `done - N pod(s) reaped` (N=0 on a healthy cluster) and NOT `cannot list pods` (that line is
the TLS/auth failure path, exit 1); recovery prints `cluster status=green ...` then `done`, NOT `cannot reach ES`;
probe prints `account=mu ... pushed` AND `account=andrea ... pushed` (two accounts) and no `FAILED:`/`Traceback`
(a TLS or urllib break prints `FAILED: SSLError/URLError`, exit 1). The andrea `icloud_auth_required: 1` line is the
pre-existing baseline, not a regression.

**4.3 Pushgateway got a fresh push from the new probe** (the probe's own heartbeat gauge; fails if the push broke
and the gauge is stale). Port-forward the Pushgateway:

```bash
kubectl port-forward -n monitoring svc/prometheus-pushgateway 9091:9091 &
sleep 3; curl -s http://localhost:9091/metrics | grep -E '^icloud_sync_probe_last_success_timestamp_seconds'; kill %1
python3 -c "import time;print('now',int(time.time()))"
```

PASS: for BOTH accounts the value is within 15 min (900 s) of `now` AND after the push time of the commit. A value
older than the commit (or only one account) => the new probe did not push.

**4.4 Settle: a second consecutive tick still passes** (one tick can be luck): re-run 4.1/4.2 after the next
tick of each member. Do not read Prometheus if a kube-prometheus-stack plan is also in the slot (none is open).
Finally no new failed jobs: `kubectl get jobs -A --field-selector status.successful=0 | grep -E "sync-probe|reaper|obs-recovery"` should list nothing newer than the apply.

## 5. Rollback

Nothing is forward-only: the ConfigMap scripts are untouched, nothing persists from the interpreter.

```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit "$PY_SHA"
git show --stat HEAD            # the same 3 files, tags and digests back to 3.14.10-alpine
git log -1 --format=%s          # Revert "chore(deps): python 3.14.10-alpine -> 3.15.2-alpine ..."
git push
```

Partial rollback is preferred if only one member fails: `git checkout "$PY_SHA"~1 -- <that file>`, commit with
`--only <file>`, push, leave the others on 3.15. The old digest `eb2c6265...b89d2` is still pullable (it is the
current live pin), so the revert re-pins exactly the previous image.

**Confirm the cluster is back:** 4.0 prints `3.14.10-alpine` (digest `eb2c6265...` on probe and recovery); the next
tick of each member passes 4.2 with imageID `@sha256:eb2c6265...`. If `ElasticsearchClusterRed` was missed during a
failed window it re-fires on the next recovery run (Alertmanager dedups); no manual action.

## 6. Interference notes

- **Same fleet, other variant**: `python-fleet-3.15.2` (slim). Disjoint objects (ai, office vs backup, kube-system,
  monitoring); `depends_on` orders it after the canary. Add the reciprocal `conflicts_with` there if the scheduler
  requires symmetry (not edited here).
- **Shared instruments (`touches.shared: [monitoring]`)**: obs-recovery IS the ES self-heal and the probe feeds
  the Pushgateway; a same-night `kube-prometheus-stack`, `grafana-14.1.0`, `edot-collector-0.164.0` or ES-family
  plan in monitoring would blind or confuse 4.2/4.3. None of the first is open; the others are listed in
  `conflicts_with`.
- **icloud-drive-fleet-2.3.0**: rolling the icloud-docker pods changes what the probe reads (restart counters, missing
  "Photos synced" lines); keep out of the same slot.
- **talos-linux-1.14.5** (node reboot): CronJob ticks are missed during the reboot; do not gate in the same slot.
- **Flux ks health**: `backup/icloud-docker-mu` currently reads `Unknown / Reconciliation in progress` (2026-11-03);
  unrelated to `backup/icloud-backup-freshness` (Ready), but note it so a stray Flux warning is not blamed on this commit.
- **Alerts**: no silences needed; none of the three has a firing alert tied to the image. Mixed 3.14/3.15 across
  independent CronJobs is harmless, so the rollout can stop after any member.
