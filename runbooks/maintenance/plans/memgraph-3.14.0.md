---
plan_id: memgraph-3.14.0
component: memgraph
pr: 405                               # renovate/memgraph-memgraph-mage-3.x, CI green (Flate Render Gate, Flux Local Diff x2)
kind: image
current: "3.13.2"                     # memgraph/memgraph-mage, live digest sha256:e28eea42... (== Docker Hub 3.13.2 index digest)
target: "3.14.0"                      # memgraph/memgraph-mage index digest sha256:2ad342a011fb463c43af821f72ca627eee2b63a39dc663f5928355a9fd01d20a (amd64+arm64, pushed 2026-10-21)
update_type: minor
risk: low                             # no consumer besides the bundled Lab; on-disk formats unchanged (see §1); revert is clean
est_duration_min: 30                  # ~5 min change + rollout, 15 min restart-settle gate, ~10 min verification
needs_reboot: false
touches:
  namespaces: [databases]
  resources: [helmrelease/memgraph, deployment/memgraph, pvc/memgraph-data, service/memgraph]
  shared: [monitoring]                # READ-only: §4 reads Prometheus (kube-state-metrics + rule state). No gateway,
                                      # CNI, DNS or shared DB touched; deployment/memgraph-lab spec is unchanged by
                                      # this diff (lab was bumped separately in PR #404) so it does not roll.
depends_on: []
conflicts_with: [longhorn-1.13.0, flux-oci-chart-sources]
                                      # longhorn-1.13.0: Recreate detaches/re-attaches memgraph-data; never during a
                                      #   storage-engine upgrade (that plan is also exclusive: true).
                                      # flux-oci-chart-sources: moves the bjw-s app-template source this HR renders from;
                                      #   a chart-source swap in the same window would confound §4.
                                      # kube-prometheus-stack: no plan file exists, but Renovate PR #428 (92.11.0 -> 92.13.1)
                                      #   is OPEN and, if Step 0 auto-applies it the same night, it restarts Prometheus
                                      #   and perturbs the instrument §4.5 reads (a plan_id cannot be named here without a
                                      #   DEAD-REF, so premise kps-chart-unchanged fails the plan if it already landed;
                                      #   the window agent must also not co-schedule it with §4.5, see §6).
exclusive: false
security_ref: null                    # not security-driven
capability_change: true               # 3.14.0 changes user-visible Cypher semantics (NaN/null comparisons, bound-variable
                                      # MATCH, collections map equality, temporal index ranges) and adds new statements
                                      # (SHOW SESSIONS / TERMINATE SESSIONS, transactional auth queries, label
                                      # expressions, CALL ... WHEN). That is new API + changed behaviour by definition,
                                      # even though no consumer here exercises any of it (§1).
rollback_class: git-revert            # durability format version (src/storage/v2/durability/version.hpp) and the auth
                                      # KV store version (V5) are byte-identical between v3.13.2 and v3.14.0, so a
                                      # 3.14.0-written snapshot is readable by 3.13.2. Longhorn backup is the fallback (§5.3).
finding_refs: []                      # `policy-cli.py finding list --grep memgraph` (2026-10-24) shows no finding for
                                      # 3.13.2 -> 3.14.0; the two rows it returns name the retired 3.13.1 image.
premises:
  - id: mage-pin-is-3.13.2
    why: "Step 3 (fallback edit) anchors on this exact line; 0 means the bump already landed or the file moved."
    run: >-
      grep -c '^[[:space:]]*tag: "3\.13\.2"$' kubernetes/apps/databases/memgraph/app/helmrelease.yaml
    expect_exact: "1"
  - id: live-image-is-3.13.2
    why: "current: and every §4 baseline (2677 nodes / 11967 rels / 12 index rows / 3 MAGE procs) were measured on this image."
    run: kubectl get deploy -n databases memgraph -o jsonpath='{.spec.template.spec.containers[?(@.name=="app")].image}'
    expect_exact: "memgraph/memgraph-mage:3.13.2"
  - id: hr-ready
    why: "A HelmRelease already failing would mask whether the bump itself reconciled (and its upgrade remediation is the first-line rollback)."
    run: kubectl get helmrelease -n databases memgraph -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
    expect_exact: "True"
  - id: strategy-recreate
    why: "Single replica on an RWO Longhorn PVC; RollingUpdate would risk Multi-Attach (docs/sops/longhorn-rwo-multi-attach.md). Live 2026-10-24: Recreate."
    run: kubectl get deploy -n databases memgraph -o jsonpath='{.spec.strategy.type}'
    expect_exact: Recreate
  - id: data-volume-healthy
    why: "The Recreate detaches and re-attaches memgraph-data; it must be healthy before we bounce it."
    run: kubectl get volumes.longhorn.io -n storage pvc-2455ee11-6ed4-4d6d-bc5e-f98ec7701b5b -o jsonpath='{.status.state}/{.status.robustness}'
    expect_exact: attached/healthy
  - id: kps-chart-unchanged
    why: "§4.5 reads Prometheus. Renovate PR #428 (kube-prometheus-stack 92.11.0 -> 92.13.1) is open; if it has landed (live chart != 92.11.0) the instrument was restarted/changed and §4.5 baselines are void. Fails by design then: re-run after the stack settles."
    run: kubectl get helmrelease -n monitoring kube-prometheus-stack -o jsonpath='{.spec.chart.spec.version}'
    expect_exact: "92.11.0"
sops_refs:
  - docs/sops/application-update.md
  - docs/sops/backup.md
  - docs/sops/longhorn-rwo-multi-attach.md
review: ready-for-go@2026-10-25   # plan-reviewer 2026-10-25: 0 blocking, premises 6/6
status: vetted
window: nightly:2026-11-04   # human-gated: needs operator GO; not same night as wazuh (11-03) or kps #428
generated: "2026-10-24"
---

# memgraph (database server) 3.13.2 -> 3.14.0

## 1. Summary & why held

Bumps the `memgraph` controller's `app` container in `kubernetes/apps/databases/memgraph/app/helmrelease.yaml`
from `memgraph/memgraph-mage:3.13.2` to `3.14.0` (Renovate PR #405, one-line diff, CI green). The `lab`
controller in the same HelmRelease is already on `memgraph/lab:3.14.0` (PR #404) and is not changed here;
after this plan, server and Lab are on the matching release.

**Why held:** coverage.py G3 found a breaking-change signal. The upstream v3.14.0 release notes
(github.com/memgraph/memgraph/releases/tag/v3.14.0, published 2026-10-21; MAGE now ships from the
memgraph repo, so this one release-notes file covers the `-mage` image) have a "Breaking changes" section. The first item is the one coverage.py quoted:

> A user or tenant profile change inside an explicit transaction is refused. It previously applied
> immediately and was not undone by `ROLLBACK`. Run profile changes as a single query. (#4524)

The full list also includes: a `database` column added to `SHOW TRANSACTIONS` (#4571); edge-index operator
metric renames (#4671); edge-property type-mismatch comparisons return no rows instead of raising (#4671);
bound-variable patterns become node tests, including after `OPTIONAL MATCH` (#4707); `collections` module
map equality, plus "Custom C++ query modules need to be recompiled" (#4783); list/map-with-null
comparisons return `null` (#4794); `NaN > x` is false and unordered pairs return null instead of erroring
(#4816); indexed temporal ranges no longer return the other temporal kinds (#4816); uniqueness
constraints admit nested nulls (#4836).

**Does anything here rely on that behaviour? No. Each item was checked against the live instance
(read-only, 2026-10-24):**

- **Auth/profile item (#4524):** `SHOW USERS` and `SHOW ROLES` return **zero rows**, so auth is not in use.
  No user or tenant profiles exist and nothing changes them. Multi-tenancy is not licensed
  (`SHOW DATABASES` refuses with an enterprise-license error), so there are no tenant profiles either.
- **Consumers:** no object in the cluster except Lab references memgraph. A live scan of every pod spec,
  ConfigMap and Secret for `memgraph`, `7687` and `bolt://` found only the PrometheusRule rulefile. The
  repo has no reference to `memgraph.databases` or `bolt://` outside the app folder. The only client is
  Memgraph Lab, used interactively by the operator (`QUICK_CONNECT_MG_HOST`).
- **Data:** a 6-label sample dataset (`Character`, `Death`, `Episode`, `Allegiance`, `Location`, `Season`),
  with 2677 nodes, 11967 relationships and 12 index entries. The newest snapshots are all
  `..._timestamp_237`, and the WAL file is `from_181_to_237` dated 2026-04-04. **No write has been
  committed since April.**
- **Triggers / streams / custom modules:** `SHOW TRIGGERS` and `SHOW STREAMS` are empty. The only query
  modules are MAGE's own, shipped in the image, so the "recompile custom C++ modules" note does not apply.
  The six "requires a valid enterprise license" module-load warnings are present at baseline and expected.
- **Metric renames (#4671):** nothing scrapes Memgraph metrics. The `--metrics-port` HTTP endpoint is not
  configured, and `memgraph-alerts` reads only kube-state-metrics series.

**Storage / snapshot format compatibility.** The tags were compared at source:

- `src/storage/v2/durability/version.hpp` is **byte-identical** between `v3.13.2` and `v3.14.0`, with the
  same `kVersion` and `kOldestSupportedVersion{14}`. A snapshot or WAL that 3.14.0 writes, including the
  `--storage-snapshot-on-exit=true` snapshot it writes during a rollback, is readable by 3.13.2.
- `src/auth/auth.cpp` declares the same KV-store versions in both tags (`kStoreV1`..`kStoreV5`, no V6).
  The file is NOT byte-identical: the only diff is a `storage_` -> `durability_` member rename around
  `MigrateVersions` / `kStoreVersionKey` (a refactor; `kCurrentStoreVersion` is unchanged). The auth store is
  not migrated.
- Primary sources (re-fetched 2026-10-25): `https://raw.githubusercontent.com/memgraph/memgraph/<tag>/src/storage/v2/durability/version.hpp`
  has the same checksum at `v3.13.2` and `v3.14.0` (`kWalHeader{37}`, `kVersion{kWalHeader}`,
  `kOldestSupportedVersion{14}`); `.../src/auth/auth.cpp` at both tags for the store constants.

**Verdict:** the hold is a correct signal, but in practice it is a false positive for this deployment.
`risk: low`. The plan is still human-gated only because `capability_change: true` is the honest value:
the release changes query semantics and adds statements.

## 2. Pre-checks

```bash
cd /Users/mu/code/cberg-home-nextgen
# 2.1 premises (all 6 must PASS)
.venv/bin/python3 runbooks/plan-premises.py memgraph-3.14.0

# 2.2 PR still the one-line mage bump and green
gh pr view 405 --json state,files,statusCheckRollup -q '{s:.state, f:[.files[].path], c:[.statusCheckRollup[]|.conclusion]}'
#   expect: s=OPEN, f=[".../memgraph/app/helmrelease.yaml"], all c=SUCCESS
gh pr diff 405 | grep -E '^[-+][[:space:]]+tag:'
#   expect exactly: -  tag: "3.13.2"  /  +  tag: "3.14.0"

# 2.3 fresh backup of memgraph-data (daily RecurringJob storage/daily-backup-all-volumes, 23:00)
kubectl get backups.longhorn.io -n storage -l backup-volume=pvc-2455ee11-6ed4-4d6d-bc5e-f98ec7701b5b \
  --sort-by=.status.backupCreatedAt -o custom-columns='N:.metadata.name,S:.status.state,T:.status.backupCreatedAt' | tail -1
#   expect: state Completed, backupCreatedAt within the last 26 h. RECORD the name as $BK for §5.3
#   (2026-10-24 baseline: backup-8a4770f076994cd2, 2026-10-23T23:04:01Z). Stale or not Completed -> ABORT.

# 2.4 auth still unused (the one breaking item that could bite)
kubectl exec -n databases deploy/memgraph -c app -- sh -c \
  'echo "SHOW USERS; SHOW ROLES; SHOW TRIGGERS; SHOW STREAMS;" | mgconsole --host 127.0.0.1 --port 7687 --output-format=csv' | wc -l
#   expect: 0 (all four empty print nothing). Any output -> STOP. Someone has started using auth,
#   triggers or streams since 2026-10-24, so the §1 analysis no longer holds and must be redone.

# 2.5 record the contents baseline (the same command as §4.3; must print the 2026-10-24 numbers)
```

## 3. Steps

1. **Silence + marker** (application-update.md Step 1). Create a 4 h Alertmanager silence on
   `namespace=databases, alertname=~"MemgraphPod.*|KubePod.*|KubeDeployment.*"`, then:
   `runbooks/update-marker.sh add memgraph databases 4 "mage 3.13.2->3.14.0"`.
   Do NOT change `upgrade.remediation`. Leave `retries: 3` in place: there is no migration to protect, and
   Helm's automatic rollback to 3.13.2 is the format-safe first line of defence (§1).
2. **Land the bump (preferred: merge the Renovate PR):**
   ```bash
   cd /Users/mu/code/cberg-home-nextgen
   gh pr merge 405 --squash --delete-branch && git pull --ff-only
   git show --stat HEAD | grep -c 'kubernetes/apps/databases/memgraph/app/helmrelease.yaml'   # expect 1
   ```
   **Fallback, if #405 is closed, unmergeable, or retargeted.** Do a direct edit. This sed was dry-tested
   on a scratch copy (BSD sed, macOS, 2026-10-24); it changes exactly one line:
   `51c51  <  tag: "3.13.2"  ---  >  tag: "3.14.0"`.
   ```bash
   sed -i '' 's/^\([[:space:]]*tag: \)"3\.13\.2"$/\1"3.14.0"/' kubernetes/apps/databases/memgraph/app/helmrelease.yaml
   git diff --stat   # 1 file, 1 insertion, 1 deletion
   git commit --only kubernetes/apps/databases/memgraph/app/helmrelease.yaml \
     -m "fix(container): update memgraph/memgraph-mage ( 3.13.2 -> 3.14.0 )"
   git log -1 --format=%s   # confirm the subject is THIS commit before pushing (shared worktree)
   git push
   ```
3. Let the Flux webhook reconcile; no manual `flux reconcile`. Watch:
   `kubectl get pods -n databases -l app.kubernetes.io/controller=memgraph -w` (interactive watch only; not
   a gate). Expect the old pod to terminate first (Recreate), then `init-sysctl` and `init-chown` to run,
   and the new pod to reach `1/1`. Memgraph needs about 10 s to load the MAGE modules and recover the
   1.1 MB snapshot.
4. When §4 passes: delete the silence, run `runbooks/update-marker.sh clear memgraph`, and close the
   Renovate branch if the fallback path was used.

## 4. Verification

All mgconsole calls go through the **Service DNS name**, so they also prove the `service/memgraph` endpoint
re-bound to the new pod. Each command was run against the live 3.13.2 pod on 2026-10-24 to capture its
baseline and to show that it can fail.

**4.1 Running version, not just a green rollout.** `rollout status` can green-light the old generation.
```bash
kubectl get pod -n databases -l app.kubernetes.io/controller=memgraph -o jsonpath='{.items[*].status.containerStatuses[?(@.name=="app")].imageID}'; echo
#   PASS: exactly one pod, ending in sha256:2ad342a011fb463c43af821f72ca627eee2b63a39dc663f5928355a9fd01d20a
#   FAIL prints sha256:e28eea42... (still 3.13.2, == Docker Hub 3.13.2 index digest, verified), or two IDs (old pod stuck).
set -o pipefail; kubectl exec -n databases deploy/memgraph -c app -- sh -c \
  'echo "SHOW VERSION;" | mgconsole --host memgraph.databases.svc.cluster.local --port 7687 --output-format=csv' | tr -d '"' | tail -1
#   PASS: 3.14.0     FAIL: 3.13.2 (baseline today), or a non-zero exit (bolt not serving).
```

**4.2 HelmRelease reconciled to the new revision, Lab untouched.**
```bash
kubectl get helmrelease -n databases memgraph -o jsonpath='{.status.conditions[?(@.type=="Ready")].status} {.status.history[0].status}'; echo
#   PASS: "True deployed". FAIL: False, or "failed" / "uninstalled" (Helm remediation rolled it back; see §5.1).
kubectl get deploy -n databases memgraph-lab -o jsonpath='{.spec.template.spec.containers[0].image}'; echo
#   PASS: memgraph/lab:3.14.0 (unchanged)
```

**4.3 CONTENTS ASSERTION: the graph, its indexes and the MAGE modules survived recovery on 3.14.0.**
Measured by the command below and compared to the 2026-10-24 baseline (`nodes 2677`, `rels 11967`,
12 index rows, `mage 3`, `IN_MEMORY_TRANSACTIONAL`, negative control `neg 0`).
```bash
MG=$(mktemp) && set -o pipefail; kubectl exec -n databases deploy/memgraph -c app -- sh -c 'echo "MATCH (n) RETURN count(n) AS nodes; MATCH ()-[r]->() RETURN count(r) AS rels; SHOW INDEX INFO; CALL mg.procedures() YIELD name WITH name WHERE name IN [\"pagerank.get\",\"community_detection.get\",\"betweenness_centrality.get\"] RETURN count(name) AS mage; SHOW STORAGE INFO;" | mgconsole --host memgraph.databases.svc.cluster.local --port 7687 --output-format=csv' | tr -d '"' > "$MG"; echo rc=$?
grep -A1 -x 'nodes' "$MG" | tail -1      # PASS: 2677
grep -A1 -x 'rels'  "$MG" | tail -1      # PASS: 11967
grep -cE '^label(\+property)?,' "$MG"    # PASS: 12
grep -A1 -x 'mage'  "$MG" | tail -1      # PASS: 3
grep -ci 'global_storage_mode,IN_MEMORY_TRANSACTIONAL' "$MG"   # PASS: 1
rm -f "$MG"
```
Failure modes this catches:

- A snapshot that failed to recover. With `--data-recovery-on-startup=true` this can come up as an empty
  graph, which would print `nodes 0` while the pod reads `1/1 Ready`.
- Lost indexes: fewer than 12 rows.
- A MAGE Python/C++ module that no longer loads: `mage` < 3.
- A changed default storage mode.

Control re-run 2026-10-25 against live 3.13.2: the block printed `rc=0`, `2677`, `11967`, `12`, `3`, `1`
(all PASS values, so the greps parse the real output), and the same greps over an EMPTY file printed
nothing / `0` / `0`, so a failed or empty read cannot satisfy a gate. Negative control, run on 2026-10-24: the same pipeline with `MATCH (n:NoSuchLabelX)` printed `0`, so the
count path can report a loss. `rc` must be 0. mgconsole exits 1 on any failed query (observed 2026-10-24
on `SHOW DATABASES`).

**4.4 No new module-load failures.**
```bash
kubectl logs -n databases deploy/memgraph -c app | grep -ciE 'failed to load query module'
#   PASS: <= 6 (baseline 6 = the enterprise-licensed *_online/cross_database modules). More -> a MAGE regression.
kubectl logs -n databases deploy/memgraph -c app | grep -iE '\[(error|critical)\]' | head
#   PASS: no output (baseline: none)
```

**4.5 Stable after settle (15 min after the new pod went Ready), read from Prometheus.**
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
curl -s localhost:19090/api/v1/query --data-urlencode 'query=kube_pod_status_ready{namespace="databases",pod=~"memgraph-[a-z0-9]+-[a-z0-9]+",condition="true"}' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(len(r),[x['value'][1] for x in r])"
#   PASS: "1 ['1']"   (the regex excludes memgraph-lab-*; an empty result "0 []" is a FAIL, not a pass)
curl -s localhost:19090/api/v1/query --data-urlencode 'query=sum(increase(kube_pod_container_status_restarts_total{namespace="databases",container="app",pod=~"memgraph-[a-z0-9]+-[a-z0-9]+"}[15m]))' \
  | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(r[0]['value'][1] if r else 'EMPTY')"
#   PASS: 0 (or 0.0). EMPTY = FAIL (series missing -> instrument broken, not "no restarts")
curl -s localhost:19090/api/v1/rules | python3 -c "import sys,json;print([r['name']+':'+r['state'] for g in json.load(sys.stdin)['data']['groups'] for r in g['rules'] if r['name'].startswith('Memgraph')])"
#   PASS: all three listed AND all 'inactive' (baseline 2026-10-24). Fewer than 3 names = rule not loaded = FAIL.
kill $PF 2>/dev/null
```
CONTROL: metric kube_pod_status_ready: exactly one memgraph server pod, with value 1.
CONTROL: metric kube_pod_container_status_restarts_total: the 15 m increase for the server container is 0, and the series must be present.
CONTROL: alertname MemgraphPodNotReady: rule loaded and `inactive`.
CONTROL: alertname MemgraphPodCrashLooping: rule loaded and `inactive`.

## 5. Rollback

**5.1 Automatic.** If the new pod never becomes Ready, the HelmRelease upgrade remediation (`retries: 3`)
rolls the release back to the previous revision, which runs 3.13.2. §1 shows that is format-safe.
Git still says 3.14.0, though, so do 5.2 to stop it retrying.

**5.2 Git revert (the standard path).** This works because the snapshot/WAL durability format and the
auth store version are identical between the two tags.
```bash
cd /Users/mu/code/cberg-home-nextgen
git revert --no-edit <sha-of-the-#405-squash-or-fallback-commit>
git log -1 --format=%s     # confirm it is the revert of the memgraph bump
git push
```
3.14.0 writes an on-exit snapshot when it stops (`--storage-snapshot-on-exit=true`), and 3.13.2 recovers
from it. To confirm the cluster is back, re-run §4.1 expecting `3.13.2` and imageID
`sha256:e28eea424e4fe2af3d20435d266de14daa33466c2d492de65bda67b36a6ae3c5`, then §4.3 (same baseline
numbers) and §4.5.

**5.3 Backup restore (only if 5.2 comes back with §4.3 failing, i.e. data lost or corrupted).**
The graph has not changed since April, so the §2.3 backup `$BK` holds exactly the current contents.

1. Keep git at 3.13.2 (5.2). Scale the server to 0 via git (`controllers.memgraph.replicas: 0`), commit
   and push, then wait until volume `pvc-2455ee11-6ed4-4d6d-bc5e-f98ec7701b5b` is `detached`.
2. Restore `$BK` into the same volume through the Longhorn UI/API. Follow `docs/sops/backup.md` (restore
   section). Note that the PV is dynamic (`longhorn` class, UUID-named), so restoring into a NEW volume
   would need a new PV/PVC binding, while restoring in place keeps the `volumeHandle`.
3. Remove the `replicas: 0` override, commit and push. Re-run §4.3 against the baseline.

## 6. Interference notes

- **Scope:** one Deployment in `databases`, with a single RWO Longhorn volume (`memgraph-data`). Downtime
  is about 30-60 s of Bolt and Lab connectivity. There is no household-facing consumer; Lab is
  operator-interactive only.
- **Same Helm release as Lab.** This diff touches only the `memgraph` controller, so
  `deployment/memgraph-lab` keeps its pod. Do not batch any Lab change into the same commit: the §4.2
  "Lab unchanged" assertion relies on it.
- **conflicts_with:** `longhorn-1.13.0` (volume re-attach during a storage-engine upgrade) and
  `flux-oci-chart-sources` (changes the chart source this HR renders from).
- **kube-prometheus-stack (shared instrument for §4.5):** Renovate PR #428 (92.11.0 -> 92.13.1) is open and
  has no plan file, so it cannot be a `conflicts_with` id. If Step 0 applies it before this plan runs,
  premise `kps-chart-unchanged` FAILS (expected) and §4.5 must wait until Prometheus has been up 15 min
  on the new chart, or be taken the next night. Never run §4.5 while the stack is mid-roll.
- **Not reboot-capable work; no node changes.** `init-sysctl` (privileged, `vm.max_map_count`) is
  unchanged and already applied on the node.
- **Nightly suitability:** `risk: low`, `rollback_class: git-revert`, no reboot, no storage-wide surface.
  Only `capability_change: true` keeps it out of AUTO-NIGHT, so the operator GO is a formality.
- Memgraph's own ingress is the Lab HTTPRoute on `envoy-internal`. It is unchanged, and there is no
  Authentik or Homepage change.
